"""
Unified Unity & .cfg blendshape importer, exporter, and Blender applier.

Provides pure-Python extraction of SkinnedMeshRenderer blendshape weights from:
  1. Unity scenes (`.unity`), prefabs (`.prefab`), and nested PrefabInstances
  2. Unity facial animation clips (`.anim`)
  3. Portable INI preset files (e.g. `configs/shinano_blendshapes.cfg`)

Also includes a fast pure-Python binary FBX Deformer parser (skipping heavy mesh
array decompression) so Unity 0-based blendshape indices map deterministically to
human-readable Shape Key names when source FBX files are present, while still
supporting `index:<N>` fallback slots inside Blender (`key_blocks[N + 1]`).
"""

import argparse
import codecs
from collections import deque
import json
import os
import re
import struct
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

COMMON_TOOLS_DIR = Path(__file__).resolve().parent
if str(COMMON_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_TOOLS_DIR))

try:
    import unity_scene_helper
except ImportError:
    unity_scene_helper = None

try:
    import vrc2gtav_i18n as project_i18n
except ImportError:
    project_i18n = None

try:
    import vrc2gtav_paths as project_paths
except ImportError:
    project_paths = None

try:
    import error_handler_helper as err_helper
except ImportError:
    err_helper = None

_FBX_BLENDSHAPE_CACHE: Dict[Tuple[str, int], Dict[str, List[str]]] = {}

MA_SHAPE_CHANGER_GUID = "2db441f589c3407bb6fb5f02ff8ab541"

_BODY_KEY_TOKENS: Tuple[str, ...] = (
    "shrink",
    "breast",
    "chest",
    "hip",
    "butt",
    "thigh",
    "calf",
    "waist",
    "shoulder",
    "belly",
    "stomach",
    "muscle",
    "fat",
    "flat",
    "chibi",
    "height",
    "torso",
    "rib",
    "sleeve",
    "skirt",
    "dress",
    "cloth",
    "collar",
    "ribbon",
    "heels",
    "heel",
    "foot",
    "feet",
    "shoe",
    "boot",
    "sock",
    "stocking",
    "glove",
    "finger",
    "arm_",
    "hand_",
    "leg_",
    "toe_",
    "ear_",
    "tail_",
    "body_",
    "bust",
    "hide_",
    "erase_",
    "off_",
)

_FACE_KEY_PREFIXES_OR_TOKENS: Tuple[str, ...] = (
    "vrc.v_",
    "vrc.blink",
    "vrc.lowerlid",
    "vrc.look",
    "eye",
    "lash",
    "lid",
    "brow",
    "mayu",
    "pupil",
    "iris",
    "hitomi",
    "highlight",
    "mouth",
    "kuchi",
    "lip",
    "tongue",
    "shita",
    "sita",
    "teeth",
    "tooth",
    "fang",
    "kiba",
    "wink",
    "smile",
    "grin",
    "laugh",
    "angry",
    "sad",
    "surpris",
    "shock",
    "tear",
    "namida",
    "blush",
    "hoho",
    "cheek",
    "nose",
    "jaw",
    "chin",
    "tareme",
    "tsurime",
    "jitome",
    "omega",
    "mabataki",
    "nagomi",
    "komaru",
    "ikari",
    "odoroki",
    "face_",
    "facial",
    "blink",
    "look_",
    "expr",
    "emo_",
    "mmd_",
)

_FACE_EXACT_TOKENS: Set[str] = {
    "a", "i", "u", "e", "o", "aa", "ch", "dd", "ee", "ff", "ih",
    "kk", "nn", "oh", "ou", "pp", "rr", "ss", "th", "sil", "neko", "o3o",
}


def is_face_blendshape_key(
    mesh_name: str,
    shape_key: str,
    extra_face_keys: Optional[Set[str]] = None,
) -> bool:
    """Classify a blendshape key as facial/expression vs body/clothing/anatomical."""
    key_clean = str(shape_key).strip()
    if extra_face_keys and key_clean in extra_face_keys:
        return True
    key_low = key_clean.lower()
    mesh_low = str(mesh_name).strip().lower()

    if any(body_tok in key_low for body_tok in _BODY_KEY_TOKENS):
        return False
    if key_low in _FACE_EXACT_TOKENS or any(key_low.startswith(tok) or tok in key_low for tok in _FACE_KEY_PREFIXES_OR_TOKENS):
        return True
    if any(mesh_tok in mesh_low for mesh_tok in ("face", "head")) and not any(
        non_face in mesh_low for non_face in ("body", "cloth", "hair", "ear", "tail", "dress", "skirt")
    ):
        return True
    return False


VALID_BLENDSHAPE_SOURCES: Tuple[str, ...] = ("auto", "unity", "cfg")

AVATAR_PRESET_RELATIVE_PATHS: Dict[str, str] = {
    "shinano_casual": "configs/shinano_blendshapes.cfg",
    "shinano_er": "configs/shinano_er_blendshapes.cfg",
    "miltina_maid": "configs/miltina_blendshapes.cfg",
}

DEFAULT_PRESET_RELATIVE_PATHS: Dict[str, str] = {
    "franklin": "configs/shinano_blendshapes.cfg",
    "michael": "configs/shinano_er_blendshapes.cfg",
    "trevor": "configs/miltina_blendshapes.cfg",
    **AVATAR_PRESET_RELATIVE_PATHS,
}

# Base Shinano.fbx meshes belonging solely to Shinano Casual (excluded when
# generating Eternal Reunion presets, which supply ER_Shi + Neko Tied Bob).
SHINANO_CASUAL_EXTRA_MESHES: Tuple[str, ...] = (
    "Cloth_under_bra",
    "Cloth_under_shorts",
    "Cloth_dress",
    "Cloth_skirt",
    "Cloth_sweater",
    "Cloth_tights",
    "Hair_back",
    "Hair_bang",
    "Hair_base",
    "Hair_side",
    "Other_ear",
)

_ARRAY_ELEMENT_SIZES: Dict[str, int] = {
    "f": 4,
    "d": 8,
    "l": 8,
    "i": 4,
    "b": 1,
}

_SKIP_SCAN_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        "library",
        "temp",
        "obj",
        "logs",
        "builds",
        "usersettings",
        ".vs",
    }
)


def _translate_msg(key_name: str, fallback_text: str, **format_kwargs: Any) -> str:
    """Translate message through project_i18n when available."""
    if project_i18n is not None and key_name in getattr(project_i18n, "MESSAGES", {}):
        return project_i18n.translate(key_name, **format_kwargs)
    return fallback_text.format(**format_kwargs) if format_kwargs else fallback_text


def _decode_unity_scalar(raw_text: str) -> str:
    """Decode YAML scalar text and Unity \\uXXXX escape sequences safely."""
    stripped = raw_text.strip()
    if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
        try:
            decoded_json = json.loads(stripped)
            if isinstance(decoded_json, str):
                return decoded_json
        except Exception:
            stripped = stripped[1:-1]
    elif stripped.startswith("'") and stripped.endswith("'") and len(stripped) >= 2:
        stripped = stripped[1:-1]

    if "\\u" in stripped or "\\U" in stripped:
        try:
            return codecs.decode(stripped, "unicode_escape")
        except Exception:
            return stripped
    return stripped


def _strip_object_suffix(object_name: str) -> str:
    """Strip Blender numeric duplicate suffix like `.001` when matching mesh names."""
    return re.sub(r"\.\d{3}$", "", object_name)


def _format_weight_value(weight_val: float) -> str:
    """Format normalized blendshape weight cleanly without float noise."""
    rounded = round(float(weight_val), 6)
    if abs(rounded) < 1e-6:
        return "0.0"
    formatted = f"{rounded:.6f}".rstrip("0").rstrip(".")
    if "." not in formatted:
        formatted += ".0"
    return formatted


def extract_fbx_blendshape_names(fbx_path: Union[str, Path]) -> Dict[str, List[str]]:
    """
    Read ordered BlendShapeChannel names per Model mesh directly from a binary FBX.

    Skips decompressing heavy geometry vertex arrays so large character FBXs parse
    in milliseconds in pure Python. Returns `{model_name: [shape_0, shape_1, ...]}`.
    """
    resolved_path = Path(fbx_path)
    if not resolved_path.is_file():
        return {}

    try:
        mtime_ns = resolved_path.stat().st_mtime_ns
        cache_key = (str(resolved_path.resolve()), mtime_ns)
    except OSError:
        cache_key = (str(resolved_path), -1)

    if cache_key[1] >= 0 and cache_key in _FBX_BLENDSHAPE_CACHE:
        return {
            mesh_key: list(shape_list)
            for mesh_key, shape_list in _FBX_BLENDSHAPE_CACHE[cache_key].items()
        }

    try:
        fbx_bytes = resolved_path.read_bytes()
    except OSError:
        return {}
    if len(fbx_bytes) < 27 or not fbx_bytes.startswith(b"Kaydara FBX Binary"):
        return {}

    try:
        fbx_version = struct.unpack_from("<I", fbx_bytes, 23)[0]
    except struct.error:
        return {}
    is_64bit = fbx_version >= 7500
    header_fmt = "<QQQB" if is_64bit else "<IIIB"
    header_size = 25 if is_64bit else 13
    sentinel_len = header_size
    total_len = len(fbx_bytes)

    def read_property_fast(cursor_pos: int) -> Tuple[Any, int]:
        type_code = chr(fbx_bytes[cursor_pos])
        cursor_pos += 1
        if type_code == "Y":
            return struct.unpack_from("<h", fbx_bytes, cursor_pos)[0], cursor_pos + 2
        if type_code == "C":
            return bool(fbx_bytes[cursor_pos]), cursor_pos + 1
        if type_code == "I":
            return struct.unpack_from("<i", fbx_bytes, cursor_pos)[0], cursor_pos + 4
        if type_code == "F":
            return struct.unpack_from("<f", fbx_bytes, cursor_pos)[0], cursor_pos + 4
        if type_code == "D":
            return struct.unpack_from("<d", fbx_bytes, cursor_pos)[0], cursor_pos + 8
        if type_code == "L":
            return struct.unpack_from("<q", fbx_bytes, cursor_pos)[0], cursor_pos + 8
        if type_code in ("S", "R"):
            byte_len = struct.unpack_from("<I", fbx_bytes, cursor_pos)[0]
            cursor_pos += 4
            if type_code == "S":
                raw_slice = fbx_bytes[cursor_pos : cursor_pos + byte_len]
                return raw_slice.decode("utf-8", errors="replace"), cursor_pos + byte_len
            return b"", cursor_pos + byte_len
        if type_code in _ARRAY_ELEMENT_SIZES:
            array_len, encoding_flag, compressed_len = struct.unpack_from(
                "<III", fbx_bytes, cursor_pos
            )
            cursor_pos += 12
            if encoding_flag == 1:
                return None, cursor_pos + compressed_len
            return None, cursor_pos + (array_len * _ARRAY_ELEMENT_SIZES[type_code])
        raise ValueError(f"Unsupported FBX property type: {type_code}")

    def parse_node_block(
        start_pos: int, end_pos: int, recurse_children: bool = True
    ) -> List[Tuple[str, List[Any], List[Any]]]:
        node_list: List[Tuple[str, List[Any], List[Any]]] = []
        cursor_pos = start_pos
        while cursor_pos + header_size <= end_pos:
            end_offset, prop_count, prop_byte_len, name_len = struct.unpack_from(
                header_fmt, fbx_bytes, cursor_pos
            )
            cursor_pos += header_size
            if end_offset == 0:
                break
            node_name = fbx_bytes[cursor_pos : cursor_pos + name_len].decode(
                "utf-8", errors="replace"
            )
            cursor_pos += name_len
            prop_end = cursor_pos + prop_byte_len
            prop_values: List[Any] = []
            while cursor_pos < prop_end and len(prop_values) < prop_count:
                parsed_val, cursor_pos = read_property_fast(cursor_pos)
                prop_values.append(parsed_val)
            cursor_pos = prop_end
            child_nodes: List[Any] = []
            if recurse_children and cursor_pos + sentinel_len <= end_offset:
                child_nodes = parse_node_block(cursor_pos, end_offset, recurse_children=True)
            cursor_pos = end_offset
            node_list.append((node_name, prop_values, child_nodes))
        return node_list

    top_cursor = 27
    object_nodes: List[Tuple[str, List[Any], List[Any]]] = []
    connection_nodes: List[Tuple[str, List[Any], List[Any]]] = []

    try:
        while top_cursor + header_size <= total_len:
            end_offset, prop_count, prop_byte_len, name_len = struct.unpack_from(
                header_fmt, fbx_bytes, top_cursor
            )
            top_cursor += header_size
            if end_offset == 0 or end_offset > total_len or end_offset < top_cursor:
                break
            section_name = fbx_bytes[top_cursor : top_cursor + name_len].decode(
                "utf-8", errors="replace"
            )
            child_start = top_cursor + name_len + prop_byte_len
            if section_name == "Objects" and child_start + sentinel_len <= end_offset:
                object_nodes = parse_node_block(child_start, end_offset, recurse_children=False)
            elif section_name == "Connections" and child_start + sentinel_len <= end_offset:
                connection_nodes = parse_node_block(
                    child_start, end_offset, recurse_children=False
                )
            top_cursor = end_offset
    except (struct.error, ValueError):
        return {}

    models_by_id: Dict[int, str] = {}
    geometry_ids: Set[int] = set()
    deformers_by_id: Dict[int, Tuple[str, str]] = {}

    for node_name, prop_values, _ in object_nodes:
        if (
            node_name == "Model"
            and len(prop_values) >= 3
            and isinstance(prop_values[0], int)
            and not isinstance(prop_values[0], bool)
        ):
            raw_model_name = str(prop_values[1]).split("\x00\x01")[0]
            models_by_id[int(prop_values[0])] = raw_model_name
        elif (
            node_name == "Geometry"
            and len(prop_values) >= 3
            and prop_values[2] == "Mesh"
            and isinstance(prop_values[0], int)
            and not isinstance(prop_values[0], bool)
        ):
            geometry_ids.add(int(prop_values[0]))
        elif (
            node_name == "Deformer"
            and len(prop_values) >= 3
            and isinstance(prop_values[0], int)
            and not isinstance(prop_values[0], bool)
        ):
            raw_deformer_name = str(prop_values[1]).split("\x00\x01")[0]
            deformers_by_id[int(prop_values[0])] = (str(prop_values[2]), raw_deformer_name)

    parent_to_children: Dict[int, List[int]] = {}
    for node_name, prop_values, _ in connection_nodes:
        if (
            node_name == "C"
            and len(prop_values) >= 3
            and prop_values[0] == "OO"
            and isinstance(prop_values[1], int)
            and isinstance(prop_values[2], int)
        ):
            child_id = int(prop_values[1])
            parent_id = int(prop_values[2])
            parent_to_children.setdefault(parent_id, []).append(child_id)

    shapes_by_model: Dict[str, List[str]] = {}
    for model_id, model_name in models_by_id.items():
        ordered_shapes: List[str] = []
        for geo_id in parent_to_children.get(model_id, []):
            if geo_id not in geometry_ids:
                continue
            for deformer_id in parent_to_children.get(geo_id, []):
                deformer_entry = deformers_by_id.get(deformer_id)
                if not deformer_entry or deformer_entry[0] != "BlendShape":
                    continue
                for channel_id in parent_to_children.get(deformer_id, []):
                    channel_entry = deformers_by_id.get(channel_id)
                    if channel_entry and channel_entry[0] == "BlendShapeChannel":
                        ordered_shapes.append(channel_entry[1])
        if ordered_shapes:
            shapes_by_model[model_name] = ordered_shapes

    if cache_key[1] >= 0:
        _FBX_BLENDSHAPE_CACHE[cache_key] = {
            mesh_key: list(shape_list) for mesh_key, shape_list in shapes_by_model.items()
        }
    return shapes_by_model


def build_fbx_blendshape_lookup(
    fbx_paths: Sequence[Union[str, Path]]
) -> Dict[str, List[str]]:
    """Combine ordered FBX shape key lists across multiple FBX paths."""
    combined_lookup: Dict[str, List[str]] = {}
    seen_paths: Set[str] = set()
    for raw_fbx_path in fbx_paths:
        if not raw_fbx_path:
            continue
        candidate_path = Path(raw_fbx_path)
        norm_key = str(candidate_path)
        if norm_key in seen_paths or not candidate_path.is_file():
            continue
        seen_paths.add(norm_key)
        per_model_shapes = extract_fbx_blendshape_names(candidate_path)
        for model_name, shape_list in per_model_shapes.items():
            combined_lookup[model_name] = shape_list
            base_model_name = _strip_object_suffix(model_name)
            if base_model_name and base_model_name not in combined_lookup:
                combined_lookup[base_model_name] = shape_list
    return combined_lookup


def collect_fbx_blendshapes(
    fbx_paths: Sequence[Union[str, Path]],
    allowed_meshes: Optional[Sequence[str]] = None,
    excluded_meshes: Sequence[str] = (),
) -> Dict[str, List[str]]:
    """Collect ordered FBX blendshape channel lists per canonical mesh name."""
    allowed_set = set(allowed_meshes) if allowed_meshes is not None else None
    excluded_set = set(excluded_meshes)
    collected_shapes: Dict[str, List[str]] = {}
    seen_paths: Set[str] = set()

    for raw_fbx_path in fbx_paths:
        if not raw_fbx_path:
            continue
        candidate_path = Path(raw_fbx_path)
        norm_key = str(candidate_path)
        if norm_key in seen_paths or not candidate_path.is_file():
            continue
        seen_paths.add(norm_key)
        per_model_shapes = extract_fbx_blendshape_names(candidate_path)
        for mesh_name, shape_list in per_model_shapes.items():
            if allowed_set is not None and mesh_name not in allowed_set:
                continue
            if mesh_name in excluded_set:
                continue
            collected_shapes[mesh_name] = list(shape_list)

    return collected_shapes


def merge_missing_fbx_blendshapes(
    mesh_weights: Dict[str, Dict[str, float]],
    fbx_paths: Sequence[Union[str, Path]],
    default_weight: float = 0.0,
    allowed_meshes: Optional[Sequence[str]] = None,
    excluded_meshes: Sequence[str] = (),
) -> Dict[str, Dict[str, float]]:
    """
    Fill any FBX blendshape channels missing from `mesh_weights` with
    `default_weight` (0.0) without modifying or resetting existing entries.
    """
    fbx_channels = collect_fbx_blendshapes(
        fbx_paths,
        allowed_meshes=allowed_meshes,
        excluded_meshes=excluded_meshes,
    )
    if not fbx_channels:
        return {
            mesh_name: dict(shape_map)
            for mesh_name, shape_map in mesh_weights.items()
        }

    merged_weights: Dict[str, Dict[str, float]] = {}
    handled_meshes: Set[str] = set()

    for mesh_name, channel_names in fbx_channels.items():
        existing_map = mesh_weights.get(mesh_name)
        if existing_map is None:
            stripped_name = _strip_object_suffix(mesh_name)
            if stripped_name in mesh_weights:
                existing_map = mesh_weights[stripped_name]
                handled_meshes.add(stripped_name)
        else:
            handled_meshes.add(mesh_name)
        existing_map = existing_map or {}

        ordered_mesh_map: Dict[str, float] = {}
        for channel_name in channel_names:
            if channel_name in existing_map:
                ordered_mesh_map[channel_name] = float(existing_map[channel_name])
            else:
                ordered_mesh_map[channel_name] = float(default_weight)

        for extra_key, extra_val in existing_map.items():
            if extra_key not in ordered_mesh_map:
                ordered_mesh_map[extra_key] = float(extra_val)

        merged_weights[mesh_name] = ordered_mesh_map

    for mesh_name, shape_map in mesh_weights.items():
        if mesh_name not in handled_meshes and mesh_name not in merged_weights:
            merged_weights[mesh_name] = dict(shape_map)

    return merged_weights


def load_unity_anim_blendshapes(
    anim_path: Union[str, Path], include_zero: bool = True
) -> Dict[str, float]:
    """
    Extract normalized (`0.0..1.0`) blendshape weights from a Unity `.anim` file.

    Returns `{shape_name: weight}` preserving curve order from the animation asset.
    """
    resolved_path = Path(anim_path) if anim_path else None
    if not resolved_path or not resolved_path.is_file():
        return {}

    raw_text = resolved_path.read_text(encoding="utf-8", errors="replace")
    curve_blocks = raw_text.split("  - serializedVersion: 2")
    shapes_map: Dict[str, float] = {}

    for curve_block in curve_blocks[1:]:
        val_match = re.search(r"value:\s*([-+\d.eE]+)", curve_block)
        attr_match = re.search(r"attribute:\s*([^\n]+)", curve_block)
        path_match = re.search(r"path:\s*([^\n]+)", curve_block)
        if not (val_match and attr_match and path_match):
            continue

        raw_attribute = _decode_unity_scalar(attr_match.group(1))
        if raw_attribute.startswith("blendShape."):
            shape_name = raw_attribute[len("blendShape.") :].strip()
        else:
            shape_name = raw_attribute.replace("blendShape.", "").strip()
        if not shape_name:
            continue

        raw_val = float(val_match.group(1))
        normalized_val = raw_val / 100.0
        if abs(raw_val) > 1e-4:
            shapes_map[shape_name] = normalized_val
        elif include_zero:
            shapes_map[shape_name] = 0.0

    return shapes_map


def save_blendshapes_cfg(
    cfg_path: Union[str, Path],
    mesh_weights: Dict[str, Dict[str, float]],
    metadata: Optional[Dict[str, str]] = None,
    header_comments: Optional[Sequence[str]] = None,
) -> Path:
    """
    Write avatar blendshape presets to a UTF-8 INI `.cfg` file.

    Uses `rsplit("=", 1)` compatible lines so special VRChat shape key characters
    like `======Nail======` or `(T1)highlight_main_x` survive round-trips safely.
    """
    output_path = Path(cfg_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_lines: List[str] = []
    if header_comments:
        for comment_line in header_comments:
            stripped = str(comment_line).strip()
            output_lines.append(stripped if stripped.startswith("#") else f"# {stripped}")
    else:
        output_lines.extend(
            [
                "# VRC2GTAV Blendshape Preset Configuration",
                "# Weights use Blender normalized range [0.0 .. 1.0] (Unity 0..100 divided by 100.0).",
                "# Keys may be Shape Key names or index:<0-based-slot>.",
            ]
        )

    if metadata:
        output_lines.append("")
        output_lines.append("[metadata]")
        for meta_key, meta_val in metadata.items():
            if meta_val is None:
                continue
            output_lines.append(f"{meta_key} = {meta_val}")

    for mesh_name, shape_dict in mesh_weights.items():
        if not shape_dict:
            continue
        output_lines.append("")
        output_lines.append(f"[{mesh_name}]")
        for shape_name, weight_val in shape_dict.items():
            output_lines.append(f"{shape_name} = {_format_weight_value(weight_val)}")

    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    return output_path


def load_blendshapes_cfg(
    cfg_path: Union[str, Path]
) -> Tuple[Dict[str, Dict[str, float]], Dict[str, str]]:
    """
    Parse a UTF-8 blendshape preset `.cfg` file safely without Python ConfigParser
    colon or multiple-equals delimiter ambiguities.

    Returns `(mesh_weights, metadata)`.
    """
    input_path = Path(cfg_path)
    if not input_path.is_file():
        raise FileNotFoundError(f"Blendshapes config file not found: {input_path}")

    raw_text = input_path.read_text(encoding="utf-8-sig")
    mesh_weights: Dict[str, Dict[str, float]] = {}
    metadata: Dict[str, str] = {}
    current_section: Optional[str] = None

    for line_num, raw_line in enumerate(raw_text.splitlines(), start=1):
        stripped_line = raw_line.strip()
        if not stripped_line or stripped_line.startswith("#") or stripped_line.startswith(";"):
            continue
        if stripped_line.startswith("[") and stripped_line.endswith("]"):
            current_section = stripped_line[1:-1].strip()
            if current_section and current_section.lower() != "metadata":
                mesh_weights.setdefault(current_section, {})
            continue
        if current_section is None or "=" not in stripped_line:
            raise ValueError(
                f"Invalid blendshapes cfg syntax at {input_path}:{line_num}: {raw_line!r}"
            )

        if current_section.lower() == "metadata":
            key_text, val_text = stripped_line.split("=", 1)
            metadata[key_text.strip()] = val_text.strip()
            continue

        key_text, val_text = stripped_line.rsplit("=", 1)
        shape_key = key_text.strip()
        if shape_key.startswith('"') and shape_key.endswith('"') and len(shape_key) >= 2:
            try:
                shape_key = json.loads(shape_key)
            except Exception:
                shape_key = shape_key[1:-1]
        weight_val = float(val_text.strip())
        mesh_weights.setdefault(current_section, {})[shape_key] = weight_val

    return mesh_weights, metadata


def _read_guid_from_meta(meta_path: Path) -> Optional[str]:
    """Read the 32-char hex GUID from the first lines of a Unity `.meta` file."""
    try:
        with meta_path.open("r", encoding="utf-8", errors="ignore") as meta_handle:
            head_chunk = meta_handle.read(300)
    except OSError:
        return None
    guid_match = re.search(r"^\s*guid:\s*([0-9a-fA-F]{32})\b", head_chunk, re.MULTILINE)
    return guid_match.group(1).lower() if guid_match else None


def _build_guid_lookup(
    tiered_roots: Sequence[Tuple[Path, Optional[int], Optional[float]]],
    needed_guids: Set[str],
    prefab_only: bool = True,
    max_dirs_per_root: Optional[int] = 400,
    shared_cache: Optional[Dict[str, Path]] = None,
) -> Dict[str, Path]:
    """
    Resolve Unity asset GUIDs to file paths in priority tiers without stalling
    on giant multi-package Asset trees over network/Windows mounts.
    Caches all scanned .meta GUIDs into shared_cache so nested prefabs resolve cleanly.
    """
    resolved_map: Dict[str, Path] = {}
    remaining = {guid_str.lower() for guid_str in needed_guids if guid_str}
    if shared_cache:
        for req_guid in list(remaining):
            cached_path = shared_cache.get(req_guid)
            if cached_path is not None and cached_path.is_file():
                resolved_map[req_guid] = cached_path
                remaining.discard(req_guid)
    if not remaining:
        return resolved_map

    visited_dirs: Set[str] = set()
    for root_dir, max_depth, time_budget_sec in tiered_roots:
        if not remaining:
            break
        if not root_dir or not root_dir.is_dir():
            continue
        resolved_root = str(root_dir.resolve())
        if resolved_root in visited_dirs:
            continue
        visited_dirs.add(resolved_root)
        root_depth = len(root_dir.resolve().parts)
        scanned_dirs = 0
        tier_start_time = time.monotonic()

        for current_dir, child_dirs, filenames in os.walk(root_dir):
            scanned_dirs += 1
            if max_dirs_per_root is not None and scanned_dirs > max_dirs_per_root:
                child_dirs[:] = []
                continue
            if (
                time_budget_sec is not None
                and scanned_dirs > 1
                and (time.monotonic() - tier_start_time) > time_budget_sec
            ):
                child_dirs[:] = []
                continue
            current_depth = len(Path(current_dir).resolve().parts) - root_depth
            if max_depth is not None and current_depth >= max_depth:
                child_dirs[:] = []
            else:
                child_dirs[:] = [
                    dir_name
                    for dir_name in child_dirs
                    if dir_name.lower() not in _SKIP_SCAN_DIR_NAMES
                ]
            for file_name in filenames:
                if not file_name.endswith(".meta"):
                    continue
                if prefab_only and not file_name.endswith(".prefab.meta"):
                    continue
                meta_file = Path(current_dir) / file_name
                guid_val = _read_guid_from_meta(meta_file)
                if not guid_val:
                    continue
                asset_path = Path(str(meta_file)[:-5])
                if not asset_path.is_file():
                    continue
                if shared_cache is not None:
                    shared_cache.setdefault(guid_val, asset_path)
                if guid_val in remaining:
                    resolved_map[guid_val] = asset_path
                    remaining.discard(guid_val)
                    if not remaining:
                        return resolved_map
    return resolved_map


def _parse_unity_yaml_components(yaml_path: Path) -> Dict[str, Any]:
    """Parse relevant GameObject, Transform, SkinnedMeshRenderer, PrefabInstance, and MA ShapeChanger data."""
    try:
        raw_text = yaml_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        if err_helper is not None:
            err_helper.get_active_logger_from_env(stage_name="blendshape").warning(
                f"Failed to read Unity YAML {yaml_path}: {exc}"
            )
        return {
            "gameobjects": {},
            "transforms": {},
            "go_to_transform": {},
            "skinned_meshes": {},
            "prefab_instances": {},
            "shape_changers": [],
        }
    yaml_blocks = raw_text.split("\n--- !u!")

    gameobjects: Dict[str, Dict[str, Any]] = {}
    transforms: Dict[str, Dict[str, Any]] = {}
    go_to_transform: Dict[str, str] = {}
    skinned_meshes: Dict[str, Dict[str, Any]] = {}
    prefab_instances: Dict[str, Dict[str, Any]] = {}
    shape_changers: List[Dict[str, Any]] = []

    for block_body in yaml_blocks[1:]:
        newline_pos = block_body.find("\n")
        if newline_pos <= 0:
            continue
        header_line = block_body[:newline_pos]
        if " &" not in header_line:
            continue
        class_part, fid_part = header_line.split(" &", 1)
        try:
            class_id = int(class_part.strip())
        except ValueError:
            continue
        file_id = fid_part.split()[0].strip()

        if class_id == 1:
            name_match = re.search(r"^\s*m_Name:\s*(.+)$", block_body, re.MULTILINE)
            active_match = re.search(r"^\s*m_IsActive:\s*(\d+)", block_body, re.MULTILINE)
            obj_name = _decode_unity_scalar(name_match.group(1)) if name_match else ""
            is_active = int(active_match.group(1)) == 1 if active_match else True
            gameobjects[file_id] = {"name": obj_name, "active": is_active}
        elif class_id == 4:
            go_match = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)\}", block_body)
            father_match = re.search(r"m_Father:\s*\{fileID:\s*(-?\d+)\}", block_body)
            child_ids: List[str] = []
            if "m_Children:" in block_body:
                children_chunk = block_body.split("m_Children:", 1)[1].split(
                    "m_Father:", 1
                )[0]
                child_ids = re.findall(r"-\s*\{fileID:\s*(-?\d+)\}", children_chunk)
            if go_match:
                go_id = go_match.group(1)
                transforms[file_id] = {
                    "gameobject": go_id,
                    "father": father_match.group(1) if father_match else "0",
                    "children": child_ids,
                }
                go_to_transform[go_id] = file_id
        elif class_id == 137:
            go_match = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)\}", block_body)
            enabled_match = re.search(r"^\s*m_Enabled:\s*(\d+)", block_body, re.MULTILINE)
            weights_list: List[float] = []
            if "m_BlendShapeWeights:\n" in block_body:
                weights_chunk = block_body.split("m_BlendShapeWeights:\n", 1)[1]
                for weight_line in weights_chunk.splitlines():
                    stripped_item = weight_line.strip()
                    if stripped_item.startswith("- "):
                        try:
                            weights_list.append(float(stripped_item[2:]) / 100.0)
                        except ValueError:
                            break
                    elif stripped_item and not stripped_item.startswith("#"):
                        break
            if go_match:
                skinned_meshes[file_id] = {
                    "gameobject": go_match.group(1),
                    "enabled": int(enabled_match.group(1)) == 1 if enabled_match else True,
                    "weights": weights_list,
                }
        elif class_id == 114:
            if MA_SHAPE_CHANGER_GUID in block_body or (
                "m_shapes:" in block_body and "ShapeName:" in block_body
            ):
                go_match = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)\}", block_body)
                enabled_match = re.search(r"^\s*m_Enabled:\s*(\d+)", block_body, re.MULTILINE)
                is_enabled = (int(enabled_match.group(1)) != 0) if enabled_match else True
                if is_enabled and go_match:
                    shape_items: List[Dict[str, Any]] = []
                    for item_match in re.finditer(
                        r"-\s*Object:[ \t]*\r?\n(?:[ \t]+[^\n]*\n)*?"
                        r"[ \t]*referencePath:[ \t]*([^\r\n]*)\r?\n"
                        r"(?:[ \t]*targetObject:[ \t]*[^\r\n]*\r?\n)?"
                        r"[ \t]*ShapeName:[ \t]*([^\r\n]*)\r?\n"
                        r"[ \t]*ChangeType:[ \t]*(-?\d+)\r?\n"
                        r"[ \t]*Value:[ \t]*([^\r\n]+)",
                        block_body,
                    ):
                        ref_path = _decode_unity_scalar(item_match.group(1))
                        shape_name = _decode_unity_scalar(item_match.group(2))
                        change_type = int(item_match.group(3))
                        try:
                            raw_val = float(item_match.group(4).strip())
                        except ValueError:
                            continue
                        weight_norm = 1.0 if change_type == 0 else (raw_val / 100.0)
                        if shape_name:
                            shape_items.append(
                                {
                                    "reference_path": ref_path,
                                    "shape_name": shape_name,
                                    "change_type": change_type,
                                    "weight": weight_norm,
                                }
                            )
                    if shape_items:
                        shape_changers.append(
                            {
                                "gameobject": go_match.group(1),
                                "shapes": shape_items,
                            }
                        )
        elif class_id == 1001:
            parent_match = re.search(
                r"m_TransformParent:\s*\{fileID:\s*(-?\d+)", block_body
            )
            source_match = re.search(
                r"m_SourcePrefab:\s*\{fileID:\s*(-?\d+),\s*guid:\s*([0-9a-fA-F]{32})",
                block_body,
            )
            mod_entries: List[Dict[str, str]] = []
            root_name_override = ""
            root_name_target_id = ""
            active_by_target: Dict[str, bool] = {}
            src_guid_str = source_match.group(2).lower() if source_match else ""
            for entry_chunk in block_body.split("    - target:")[1:]:
                header_slice = entry_chunk[:500]
                if (
                    "m_BlendShapeWeights" not in header_slice
                    and "propertyPath: m_Name" not in header_slice
                    and "propertyPath: m_IsActive" not in header_slice
                ):
                    continue
                target_match = re.search(
                    r"\{fileID:\s*(-?\d+),\s*guid:\s*([0-9a-fA-F]{32})", header_slice
                )
                prop_match = re.search(r"propertyPath:[ \t]*([^\r\n]+)", header_slice)
                val_match = re.search(r"value:[ \t]*([^\r\n]*)", header_slice)
                if not (target_match and prop_match and val_match):
                    continue
                prop_path = prop_match.group(1).strip()
                raw_val = _decode_unity_scalar(val_match.group(1))
                tgt_fid = target_match.group(1)
                tgt_guid = target_match.group(2).lower()
                if prop_path == "m_Name" and raw_val:
                    is_src_match = bool(src_guid_str and tgt_guid == src_guid_str)
                    if not root_name_override or (is_src_match and not root_name_target_id):
                        root_name_override = raw_val
                        root_name_target_id = tgt_fid
                elif prop_path == "m_IsActive" and tgt_fid:
                    if not src_guid_str or tgt_guid == src_guid_str:
                        active_by_target[tgt_fid] = (raw_val != "0")
                elif prop_path.startswith("m_BlendShapeWeights.Array.data["):
                    mod_entries.append(
                        {
                            "target_id": tgt_fid,
                            "target_guid": tgt_guid,
                            "property_path": prop_path,
                            "value": raw_val,
                        }
                    )
            pi_active = True
            if root_name_target_id and root_name_target_id in active_by_target:
                pi_active = active_by_target[root_name_target_id]
            elif not root_name_target_id and "100000" in active_by_target:
                pi_active = active_by_target["100000"]
            prefab_instances[file_id] = {
                "transform_parent": parent_match.group(1) if parent_match else "0",
                "source_guid": src_guid_str,
                "name_override": root_name_override,
                "active": pi_active,
                "modifications": mod_entries,
            }

    return {
        "gameobjects": gameobjects,
        "transforms": transforms,
        "go_to_transform": go_to_transform,
        "skinned_meshes": skinned_meshes,
        "prefab_instances": prefab_instances,
        "shape_changers": shape_changers,
    }


def _select_avatar_root_target(
    parsed_doc: Dict[str, Any],
    avatar_name: Optional[str] = None,
    character_hints: Optional[Sequence[str]] = None,
) -> Tuple[str, Optional[str], str]:
    """Select root Transform or top-level PrefabInstance (`("tr"|"pi", file_id, name)`)."""
    gameobjects = parsed_doc["gameobjects"]
    transforms = parsed_doc["transforms"]
    go_to_transform = parsed_doc["go_to_transform"]
    prefab_instances = parsed_doc["prefab_instances"]

    def count_descendants(start_tr: str) -> int:
        seen: Set[str] = set()
        queue_tr = deque([start_tr])
        while queue_tr:
            current_tr = queue_tr.popleft()
            if current_tr in seen:
                continue
            seen.add(current_tr)
            tr_info = transforms.get(current_tr)
            if tr_info:
                queue_tr.extend(tr_info["children"])
        return len(seen)

    candidates: List[Tuple[int, int, int, str, str, str]] = []
    normalized_target = (avatar_name or "").strip().lower()
    hint_tokens = [token.strip().lower() for token in (character_hints or []) if token]

    for go_id, go_info in gameobjects.items():
        tr_id = go_to_transform.get(go_id)
        if not tr_id:
            continue
        go_name = go_info["name"]
        go_lower = go_name.lower()
        score = -1
        if normalized_target and go_lower == normalized_target:
            score = 100
        elif normalized_target and normalized_target in go_lower:
            score = 60
        elif any(hint_token in go_lower for hint_token in hint_tokens):
            score = 40
        elif not normalized_target and not hint_tokens:
            father_id = transforms[tr_id]["father"]
            if father_id == "0":
                score = 20
        if score >= 0:
            active_flag = 1 if go_info["active"] else 0
            candidates.append((score, active_flag, count_descendants(tr_id), "tr", tr_id, go_name))

    for pi_id, pi_info in prefab_instances.items():
        if str(pi_info.get("transform_parent", "0")) != "0":
            continue
        pi_name = str(pi_info.get("name_override", "") or "").strip()
        if not pi_name:
            continue
        pi_lower = pi_name.lower()
        score = -1
        if normalized_target and pi_lower == normalized_target:
            score = 98
        elif normalized_target and normalized_target in pi_lower:
            score = 58
        elif any(hint_token in pi_lower for hint_token in hint_tokens):
            score = 38
        elif not normalized_target and not hint_tokens:
            score = 18
        if score >= 0:
            active_flag = 1 if pi_info.get("active", True) else 0
            candidates.append((score, active_flag, 1, "pi", pi_id, pi_name))

    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        chosen = candidates[0]
        return chosen[3], chosen[4], chosen[5]

    if transforms:
        top_roots = [
            (count_descendants(tr_id), tr_id, gameobjects.get(tr_info["gameobject"], {}).get("name", ""))
            for tr_id, tr_info in transforms.items()
            if tr_info["father"] == "0"
        ]
        if top_roots:
            top_roots.sort(key=lambda item: item[0], reverse=True)
            return "tr", top_roots[0][1], top_roots[0][2]

    top_pis = [
        (pi_id, str(pi_info.get("name_override", "") or ""))
        for pi_id, pi_info in prefab_instances.items()
        if str(pi_info.get("transform_parent", "0")) == "0"
    ]
    if top_pis:
        return "pi", top_pis[0][0], top_pis[0][1]

    return "tr", None, ""


def _select_avatar_root_transform(
    parsed_doc: Dict[str, Any],
    avatar_name: Optional[str] = None,
    character_hints: Optional[Sequence[str]] = None,
) -> Tuple[Optional[str], str]:
    """Select the most appropriate root Transform fileID inside a Unity scene or prefab."""
    root_kind, root_id, root_name = _select_avatar_root_target(
        parsed_doc, avatar_name=avatar_name, character_hints=character_hints
    )
    if root_kind == "tr":
        return root_id, root_name
    return None, root_name


def _collect_descendant_transforms(
    parsed_doc: Dict[str, Any], root_transform_id: Optional[str]
) -> Set[str]:
    """Return the set of Transform fileIDs at or below `root_transform_id`."""
    transforms = parsed_doc["transforms"]
    if root_transform_id is None:
        return set(transforms.keys())
    descendants: Set[str] = set()
    queue_tr = deque([root_transform_id])
    while queue_tr:
        current_tr = queue_tr.popleft()
        if current_tr in descendants:
            continue
        descendants.add(current_tr)
        tr_info = transforms.get(current_tr)
        if tr_info:
            queue_tr.extend(tr_info["children"])
    return descendants


def _collect_prefab_blendshapes(
    prefab_path: Path,
    guid_resolver: Any,
    prefab_cache: Dict[Path, Dict[str, Any]],
    depth: int = 0,
) -> Tuple[Dict[str, str], Dict[str, Dict[int, float]]]:
    """
    Collect base SkinnedMeshRenderer blendshape weights inside a `.prefab` asset.

    Returns `(smr_file_id_to_mesh_name, mesh_name_to_slot_weights)`.
    """
    if depth > 8 or not prefab_path.is_file():
        return {}, {}

    if prefab_path not in prefab_cache:
        prefab_cache[prefab_path] = _parse_unity_yaml_components(prefab_path)
    parsed_prefab = prefab_cache[prefab_path]

    smr_id_to_name: Dict[str, str] = {}
    mesh_slots: Dict[str, Dict[int, float]] = {}

    for smr_id, smr_info in parsed_prefab["skinned_meshes"].items():
        go_id = smr_info["gameobject"]
        mesh_name = parsed_prefab["gameobjects"].get(go_id, {}).get("name", "")
        if not mesh_name:
            continue
        smr_id_to_name[smr_id] = mesh_name
        slot_weights = mesh_slots.setdefault(mesh_name, {})
        for slot_idx, weight_val in enumerate(smr_info["weights"]):
            if abs(weight_val) > 1e-6:
                slot_weights[slot_idx] = weight_val

    nested_guids = {
        pi_info["source_guid"]
        for pi_info in parsed_prefab["prefab_instances"].values()
        if pi_info["source_guid"]
    }
    nested_map = guid_resolver(nested_guids)

    for pi_info in parsed_prefab["prefab_instances"].values():
        nested_path = nested_map.get(pi_info["source_guid"])
        if not nested_path:
            continue
        nested_id_map, nested_weights = _collect_prefab_blendshapes(
            nested_path, guid_resolver, prefab_cache, depth=depth + 1
        )
        for nested_mesh, nested_slots in nested_weights.items():
            mesh_slots.setdefault(nested_mesh, {}).update(nested_slots)
        for mod_item in pi_info["modifications"]:
            slot_match = re.match(
                r"m_BlendShapeWeights\.Array\.data\[(\d+)\]",
                mod_item["property_path"],
            )
            if not slot_match:
                continue
            target_mesh = nested_id_map.get(mod_item["target_id"])
            if not target_mesh:
                continue
            slot_idx = int(slot_match.group(1))
            try:
                override_weight = float(mod_item["value"]) / 100.0
            except ValueError:
                continue
            smr_id_to_name[mod_item["target_id"]] = target_mesh
            target_dict = mesh_slots.setdefault(target_mesh, {})
            if abs(override_weight) > 1e-6:
                target_dict[slot_idx] = override_weight
            else:
                target_dict.pop(slot_idx, None)

    return smr_id_to_name, mesh_slots


def extract_unity_scene_blendshapes(
    unity_path: Union[str, Path],
    avatar_name: Optional[str] = None,
    character_hints: Optional[Sequence[str]] = None,
    unity_assets_root: Optional[Union[str, Path]] = None,
    fbx_paths: Sequence[Union[str, Path]] = (),
    include_zero: bool = False,
) -> Dict[str, Any]:
    """
    Extract SkinnedMeshRenderer + nested PrefabInstance blendshapes from a Unity
    `.unity` scene or `.prefab` asset.

    Maps 0-based Unity slot indices to named Shape Keys using `fbx_paths` when
    available, falling back to `index:<N>` otherwise.
    """
    resolved_unity = Path(unity_path) if unity_path else None
    empty_result: Dict[str, Any] = {
        "loaded": False,
        "source_path": str(resolved_unity) if resolved_unity else "",
        "root_name": "",
        "root_file_id": "",
        "mesh_weights": {},
        "indexed_mesh_weights": {},
        "warnings": [],
    }
    if not resolved_unity or not resolved_unity.is_file():
        return empty_result

    parsed_doc = _parse_unity_yaml_components(resolved_unity)
    root_kind, root_tr_or_pi_id, selected_root_name = _select_avatar_root_target(
        parsed_doc, avatar_name=avatar_name, character_hints=character_hints
    )
    root_tr_id = root_tr_or_pi_id if root_kind == "tr" else None
    if root_kind == "pi":
        descendant_trs: Set[str] = set()
    else:
        descendant_trs = _collect_descendant_transforms(parsed_doc, root_tr_id)

    assets_dir = Path(unity_assets_root).resolve() if unity_assets_root else None
    tiered_roots: List[Tuple[Path, Optional[int], Optional[float]]] = []
    for raw_fbx in fbx_paths:
        if not raw_fbx:
            continue
        fbx_path_obj = Path(raw_fbx).resolve()
        fbx_parent = fbx_path_obj.parent
        fbx_pkg_root = fbx_parent.parent if fbx_parent.parent != fbx_parent else fbx_parent
        if assets_dir is not None and fbx_pkg_root == assets_dir:
            tiered_roots.append((fbx_parent, 4, None))
        elif fbx_pkg_root != resolved_unity.parent.resolve():
            tiered_roots.append((fbx_pkg_root, 5, None))
        else:
            tiered_roots.append((fbx_parent, 4, None))

    tiered_roots.append((resolved_unity.parent, 1, 1.0))
    if assets_dir is not None and assets_dir.is_dir():
        tiered_roots.append((assets_dir, 4, 1.5))

    guid_cache: Dict[str, Path] = {}
    prefab_cache: Dict[Path, Dict[str, Any]] = {}
    attempted_guids: Set[str] = set()

    def resolve_guids(needed_guids: Set[str]) -> Dict[str, Path]:
        missing_guids = {
            guid_item.lower()
            for guid_item in needed_guids
            if guid_item
            and guid_item.lower() not in guid_cache
            and guid_item.lower() not in attempted_guids
        }
        if missing_guids:
            attempted_guids.update(missing_guids)
            guid_cache.update(
                _build_guid_lookup(
                    tiered_roots,
                    missing_guids,
                    prefab_only=True,
                    max_dirs_per_root=300,
                    shared_cache=guid_cache,
                )
            )
        return guid_cache

    indexed_by_mesh: Dict[str, Dict[int, float]] = {}

    if root_kind == "tr":
        for smr_info in parsed_doc["skinned_meshes"].values():
            go_id = smr_info["gameobject"]
            tr_id = parsed_doc["go_to_transform"].get(go_id)
            if tr_id is not None and tr_id not in descendant_trs:
                continue
            mesh_name = parsed_doc["gameobjects"].get(go_id, {}).get("name", "")
            if not mesh_name:
                continue
            slot_map: Dict[int, float] = {}
            for slot_idx, weight_val in enumerate(smr_info["weights"]):
                if include_zero or abs(weight_val) > 1e-6:
                    slot_map[slot_idx] = weight_val
            if slot_map:
                indexed_by_mesh[mesh_name] = slot_map

    if root_kind == "pi" and root_tr_or_pi_id in parsed_doc["prefab_instances"]:
        relevant_pis = [parsed_doc["prefab_instances"][root_tr_or_pi_id]]
    else:
        relevant_pis = [
            pi_info
            for pi_info in parsed_doc["prefab_instances"].values()
            if pi_info.get("active", True)
            and (
                resolved_unity.suffix.lower() == ".prefab"
                or pi_info["transform_parent"] in descendant_trs
                or pi_info["transform_parent"] == root_tr_id
            )
        ]
    pi_guids = {pi_info["source_guid"] for pi_info in relevant_pis if pi_info["source_guid"]}
    resolved_prefabs = resolve_guids(pi_guids)

    for pi_info in relevant_pis:
        prefab_file = resolved_prefabs.get(pi_info["source_guid"])
        if not prefab_file:
            continue
        smr_id_map, base_slots = _collect_prefab_blendshapes(
            prefab_file, resolve_guids, prefab_cache
        )
        for base_mesh, slot_dict in base_slots.items():
            if include_zero:
                indexed_by_mesh.setdefault(base_mesh, {}).update(slot_dict)
            else:
                non_zero = {
                    slot_idx: weight_val
                    for slot_idx, weight_val in slot_dict.items()
                    if abs(weight_val) > 1e-6
                }
                if non_zero:
                    indexed_by_mesh.setdefault(base_mesh, {}).update(non_zero)

        for mod_item in pi_info["modifications"]:
            slot_match = re.match(
                r"m_BlendShapeWeights\.Array\.data\[(\d+)\]",
                mod_item["property_path"],
            )
            if not slot_match:
                continue
            target_mesh = smr_id_map.get(mod_item["target_id"])
            if not target_mesh:
                continue
            slot_idx = int(slot_match.group(1))
            try:
                override_weight = float(mod_item["value"]) / 100.0
            except ValueError:
                continue
            mesh_slot_dict = indexed_by_mesh.setdefault(target_mesh, {})
            if include_zero or abs(override_weight) > 1e-6:
                mesh_slot_dict[slot_idx] = override_weight
            else:
                mesh_slot_dict.pop(slot_idx, None)

    fbx_lookup = build_fbx_blendshape_lookup(fbx_paths)
    named_by_mesh: Dict[str, Dict[str, float]] = {}

    for mesh_name, slot_dict in indexed_by_mesh.items():
        if not slot_dict:
            continue
        fbx_shape_list = fbx_lookup.get(mesh_name) or fbx_lookup.get(
            _strip_object_suffix(mesh_name)
        )
        resolved_shapes: Dict[str, float] = {}
        for slot_idx, weight_val in sorted(slot_dict.items()):
            if fbx_shape_list and 0 <= slot_idx < len(fbx_shape_list):
                resolved_shapes[fbx_shape_list[slot_idx]] = weight_val
            else:
                resolved_shapes[f"index:{slot_idx}"] = weight_val
        if resolved_shapes:
            named_by_mesh[mesh_name] = resolved_shapes

    # Apply Modular Avatar ShapeChanger weights targeting meshes in the avatar subtree
    if root_kind == "tr":
        for sc_entry in parsed_doc.get("shape_changers", []):
            go_id = sc_entry.get("gameobject", "")
            tr_id = parsed_doc["go_to_transform"].get(go_id)
            if tr_id is not None and tr_id not in descendant_trs:
                continue
            go_info = parsed_doc["gameobjects"].get(go_id, {})
            if go_info and not go_info.get("active", True):
                continue
            for shape_item in sc_entry.get("shapes", []):
                ref_path = str(shape_item.get("reference_path", "") or "").strip()
                shape_name = str(shape_item.get("shape_name", "") or "").strip()
                if not shape_name:
                    continue
                target_mesh = ref_path.rsplit("/", 1)[-1].strip() if ref_path else "Body"
                if not target_mesh:
                    target_mesh = "Body"
                weight_val = float(shape_item.get("weight", 1.0))
                if include_zero or abs(weight_val) > 1e-6:
                    named_by_mesh.setdefault(target_mesh, {})[shape_name] = weight_val

    return {
        "loaded": True,
        "source_path": str(resolved_unity),
        "root_name": selected_root_name,
        "root_file_id": root_tr_or_pi_id or "",
        "mesh_weights": named_by_mesh,
        "indexed_mesh_weights": indexed_by_mesh,
        "warnings": [],
    }


def _read_leading_cfg_comments(cfg_path: Path) -> List[str]:
    """Preserve top `#` comment lines from an existing preset `.cfg` file."""
    if not cfg_path.is_file():
        return []
    comments: List[str] = []
    for raw_line in cfg_path.read_text(encoding="utf-8-sig").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if comments:
                break
            continue
        if stripped.startswith("#"):
            comments.append(stripped)
        else:
            break
    return comments


def _coerce_optional_bool(raw_value: Any, default_value: bool = True) -> bool:
    """Coerce an optional bool/string/int setting with fallback default."""
    if raw_value is None:
        return default_value
    if isinstance(raw_value, bool):
        return raw_value
    text_val = str(raw_value).strip().lower()
    if not text_val:
        return default_value
    if text_val in ("0", "false", "no", "nao", "não", "n", "off"):
        return False
    if text_val in ("1", "true", "yes", "sim", "s", "y", "on"):
        return True
    return default_value


def resolve_character_blendshapes(
    char_cfg: Dict[str, Any],
    fbx_paths: Sequence[Union[str, Path]] = (),
    character_hints: Optional[Sequence[str]] = None,
    default_face_mesh: str = "Body",
    unity_assets_root: Optional[Union[str, Path]] = None,
    override_source: Optional[str] = None,
    override_cfg_path: Optional[Union[str, Path]] = None,
    override_unity_scene: Optional[Union[str, Path]] = None,
    override_avatar_name: Optional[str] = None,
    override_face_anim: Optional[Union[str, Path]] = None,
    save_cfg_path: Optional[Union[str, Path]] = None,
    exclude_meshes_when_no_custom_hair: bool = False,
    custom_hair_mesh_names: Sequence[str] = (),
    fill_missing_from_fbx: bool = True,
    fbx_allowed_meshes: Optional[Sequence[str]] = None,
    fbx_excluded_meshes: Sequence[str] = (),
    header_comments: Optional[Sequence[str]] = None,
    import_face: Optional[bool] = None,
    import_body: Optional[bool] = None,
    extra_fbx_paths: Sequence[Union[str, Path]] = (),
) -> Dict[str, Any]:
    """
    Resolve avatar blendshape weights according to `blendshapes_source` (`auto | unity | cfg`),
    separate `import_face` / `import_body` controls, and custom outfit/dress FBXs.

    Mode behavior:
      - When both `import_face` and `import_body` are False: creates/returns all-zero (`0.0`)
        weights across all meshes and channels extracted from avatar + custom dress FBXs.
      - When only one of `import_face` or `import_body` is False: imports the enabled category
        from Unity/anim/cfg and zeros (`0.0`) the disabled category while retaining all FBX keys.
      - `face_anim` keys are merged onto `default_face_mesh` without wiping non-facial keys.
    """
    requested_source = (
        override_source
        or str(char_cfg.get("blendshapes_source", "auto") or "auto")
    ).strip().lower()
    if requested_source not in VALID_BLENDSHAPE_SOURCES:
        raise ValueError(
            f"Unsupported blendshapes_source {requested_source!r}; expected one of {VALID_BLENDSHAPE_SOURCES}"
        )

    do_import_face = _coerce_optional_bool(
        import_face,
        _coerce_optional_bool(char_cfg.get("import_face_blendshapes"), True),
    )
    do_import_body = _coerce_optional_bool(
        import_body,
        _coerce_optional_bool(char_cfg.get("import_body_blendshapes"), True),
    )

    combined_fbx_paths: List[Union[str, Path]] = []
    seen_fbx_keys: Set[str] = set()
    for cand_fbx in list(fbx_paths) + list(extra_fbx_paths):
        if not cand_fbx:
            continue
        norm_key = str(cand_fbx)
        if norm_key not in seen_fbx_keys:
            seen_fbx_keys.add(norm_key)
            combined_fbx_paths.append(cand_fbx)

    effective_cfg = (
        str(override_cfg_path)
        if override_cfg_path
        else str(char_cfg.get("blendshapes_cfg", "") or "")
    ).strip()
    effective_scene = (
        str(override_unity_scene)
        if override_unity_scene is not None
        else str(char_cfg.get("unity_scene", "") or "")
    ).strip()
    effective_avatar = (
        str(override_avatar_name)
        if override_avatar_name is not None
        else str(char_cfg.get("unity_avatar_name", "") or "")
    ).strip()
    effective_face_anim = (
        str(override_face_anim)
        if override_face_anim is not None
        else str(char_cfg.get("face_anim", "") or "")
    ).strip()

    if project_paths is not None:
        if effective_cfg:
            effective_cfg = str(project_paths.to_host_path(effective_cfg))
        if effective_scene:
            effective_scene = str(project_paths.to_host_path(effective_scene))
        if effective_face_anim:
            effective_face_anim = str(project_paths.to_host_path(effective_face_anim))
        if save_cfg_path:
            save_cfg_path = project_paths.to_host_path(str(save_cfg_path))

    scene_exists = bool(effective_scene) and Path(effective_scene).is_file()
    cfg_exists = bool(effective_cfg) and Path(effective_cfg).is_file()
    anim_exists = bool(effective_face_anim) and Path(effective_face_anim).is_file()

    if not unity_assets_root and project_paths is not None:
        try:
            unity_assets_root = project_paths.get_vrc_assets_dir()
        except Exception:
            unity_assets_root = None

    use_unity = requested_source == "unity" or (
        requested_source == "auto" and scene_exists
    )

    resolved_meshes: Dict[str, Dict[str, float]] = {}
    resolved_metadata: Dict[str, str] = {}
    root_name = effective_avatar
    source_used = "none"
    anim_face_keys: Set[str] = set()

    def _merge_face_anim_into_mesh() -> None:
        nonlocal anim_face_keys
        if not anim_exists or not do_import_face:
            return
        anim_weights = load_unity_anim_blendshapes(effective_face_anim, include_zero=True)
        if anim_weights:
            anim_face_keys.update(anim_weights.keys())
            existing_face_map = dict(resolved_meshes.get(default_face_mesh, {}))
            existing_face_map.update(anim_weights)
            resolved_meshes[default_face_mesh] = existing_face_map
            resolved_metadata["face_anim"] = Path(effective_face_anim).name

    if not do_import_face and not do_import_body:
        # User chose neither face nor body blendshape import: build zeroed .cfg from FBXs
        if combined_fbx_paths:
            resolved_meshes = merge_missing_fbx_blendshapes(
                {},
                combined_fbx_paths,
                default_weight=0.0,
                allowed_meshes=fbx_allowed_meshes,
                excluded_meshes=fbx_excluded_meshes,
            )
        if not resolved_meshes and cfg_exists:
            loaded_zero, _ = load_blendshapes_cfg(effective_cfg)
            resolved_meshes = {
                mesh_k: {shape_k: 0.0 for shape_k in shape_v}
                for mesh_k, shape_v in loaded_zero.items()
            }
        source_used = "fbx_zeroed"
        resolved_metadata = {
            "avatar": root_name or "avatar",
            "source": "fbx_zeroed",
            "import_face": "0",
            "import_body": "0",
        }
    else:
        if use_unity and scene_exists:
            unity_data = extract_unity_scene_blendshapes(
                effective_scene,
                avatar_name=effective_avatar or None,
                character_hints=character_hints,
                unity_assets_root=unity_assets_root,
                fbx_paths=combined_fbx_paths,
            )
            if unity_data["loaded"]:
                resolved_meshes = unity_data["mesh_weights"]
                root_name = unity_data["root_name"] or effective_avatar
                source_used = "unity"
                resolved_metadata = {
                    "avatar": root_name,
                    "source": "unity_scene",
                    "unity_scene": Path(effective_scene).name,
                }

        if source_used == "unity":
            _merge_face_anim_into_mesh()
        elif requested_source == "unity":
            if anim_exists and do_import_face:
                _merge_face_anim_into_mesh()
                source_used = "unity"
        elif cfg_exists:
            resolved_meshes, resolved_metadata = load_blendshapes_cfg(effective_cfg)
            source_used = "cfg"
            if (
                do_import_face
                and anim_exists
                and (override_face_anim is not None or default_face_mesh not in resolved_meshes)
            ):
                _merge_face_anim_into_mesh()
        elif anim_exists and do_import_face:
            _merge_face_anim_into_mesh()
            source_used = "anim"

        if fill_missing_from_fbx and combined_fbx_paths:
            resolved_meshes = merge_missing_fbx_blendshapes(
                resolved_meshes,
                combined_fbx_paths,
                default_weight=0.0,
                allowed_meshes=fbx_allowed_meshes,
                excluded_meshes=fbx_excluded_meshes,
            )
            if source_used == "none" and resolved_meshes:
                source_used = "fbx"
                if not resolved_metadata:
                    resolved_metadata = {
                        "avatar": root_name or "avatar",
                        "source": "fbx",
                    }

        if not do_import_face or not do_import_body:
            for mesh_key, shape_dict in resolved_meshes.items():
                for shape_key in list(shape_dict.keys()):
                    is_face = is_face_blendshape_key(
                        mesh_key, shape_key, extra_face_keys=anim_face_keys
                    )
                    if (is_face and not do_import_face) or (not is_face and not do_import_body):
                        shape_dict[shape_key] = 0.0

        resolved_metadata["import_face"] = "1" if do_import_face else "0"
        resolved_metadata["import_body"] = "1" if do_import_body else "0"

    if exclude_meshes_when_no_custom_hair and custom_hair_mesh_names:
        hair_name_set = set(custom_hair_mesh_names)
        resolved_meshes = {
            mesh_key: shape_dict
            for mesh_key, shape_dict in resolved_meshes.items()
            if mesh_key not in hair_name_set
        }

    saved_path_str = ""
    if save_cfg_path and resolved_meshes:
        written_path = save_blendshapes_cfg(
            save_cfg_path,
            resolved_meshes,
            metadata=resolved_metadata or {"avatar": root_name or "avatar", "source": source_used},
            header_comments=header_comments,
        )
        saved_path_str = str(written_path)

    return {
        "source_used": source_used,
        "mode_requested": requested_source,
        "import_face": do_import_face,
        "import_body": do_import_body,
        "mesh_weights": resolved_meshes,
        "metadata": resolved_metadata,
        "cfg_path": effective_cfg,
        "unity_scene": effective_scene,
        "root_name": root_name,
        "face_anim": effective_face_anim,
        "saved_cfg_path": saved_path_str,
    }


def apply_blendshapes_to_blender_object(
    mesh_obj: Any,
    shape_weights: Dict[str, float],
    reset_unlisted: bool = True,
    allow_lr_symmetry: bool = False,
) -> Tuple[int, int]:
    """
    Apply a `{shape_name_or_index: weight}` dictionary to a Blender mesh object.

    Supports exact shape key names, optional `_R`/`_L` symmetry expansion when a
    facial key lacks its unsuffixed block, and `index:<N>` 0-based fallback slots
    (`key_blocks[N + 1]`). Returns `(applied_slot_count, active_nonzero_count)`.
    """
    if not mesh_obj or not getattr(mesh_obj.data, "shape_keys", None):
        return 0, 0

    key_blocks = mesh_obj.data.shape_keys.key_blocks
    if reset_unlisted:
        for key_block in key_blocks[1:]:
            key_block.value = 0.0

    applied_count = 0
    active_count = 0

    for shape_key, raw_weight in shape_weights.items():
        weight_val = float(raw_weight)
        if shape_key.startswith("index:"):
            try:
                zero_based_idx = int(shape_key.split(":", 1)[1])
            except ValueError:
                continue
            target_slot = zero_based_idx + 1
            if 1 <= target_slot < len(key_blocks):
                key_blocks[target_slot].value = weight_val
                applied_count += 1
                if abs(weight_val) > 1e-6:
                    active_count += 1
            continue

        direct_block = key_blocks.get(shape_key)
        if direct_block is not None:
            direct_block.value = weight_val
            applied_count += 1
            if abs(weight_val) > 1e-6:
                active_count += 1
        elif allow_lr_symmetry:
            for side_suffix in ("_R", "_L"):
                side_block = key_blocks.get(f"{shape_key}{side_suffix}")
                if side_block is not None:
                    side_block.value = weight_val
                    applied_count += 1
                    if abs(weight_val) > 1e-6:
                        active_count += 1

    return applied_count, active_count


def apply_blendshapes_to_blender_scene(
    bpy_module: Any,
    mesh_weights: Dict[str, Dict[str, float]],
    exclude_meshes: Sequence[str] = (),
    include_meshes: Optional[Sequence[str]] = None,
    lr_symmetry_meshes: Sequence[str] = ("Body",),
    reset_unlisted: bool = True,
) -> Dict[str, Tuple[int, int]]:
    """Apply resolved blendshapes across matching objects in the active Blender scene."""
    excluded_set = set(exclude_meshes)
    included_set = set(include_meshes) if include_meshes is not None else None
    symmetry_set = set(lr_symmetry_meshes)
    summary_map: Dict[str, Tuple[int, int]] = {}

    for mesh_name, shape_dict in mesh_weights.items():
        if mesh_name in excluded_set:
            continue
        if included_set is not None and mesh_name not in included_set:
            continue
        target_obj = bpy_module.data.objects.get(mesh_name)
        if not target_obj or not getattr(target_obj.data, "shape_keys", None):
            continue
        counts = apply_blendshapes_to_blender_object(
            target_obj,
            shape_dict,
            reset_unlisted=reset_unlisted,
            allow_lr_symmetry=mesh_name in symmetry_set,
        )
        summary_map[mesh_name] = counts

    return summary_map


def export_character_blendshapes_to_cfg(
    character_section: str,
    output_cfg_path: Optional[Union[str, Path]] = None,
    unity_scene_override: Optional[Union[str, Path]] = None,
    avatar_name_override: Optional[str] = None,
    preserve_existing_cfg: bool = True,
    fill_missing_from_fbx: bool = True,
) -> Optional[Path]:
    """
    Export or synchronize blendshape presets for an avatar preset (`shinano_casual`,
    `shinano_er`, `miltina_maid`) or protagonist slot into a `.cfg` preset file.

    By default (`preserve_existing_cfg=True`), any existing `.cfg` values remain
    untouched while missing channels from configured FBX models are appended
    with weight `0.0`.
    """
    if project_paths is None:
        raise RuntimeError("vrc2gtav_paths is required to export character blendshapes.")

    resolved_avatar_id: Optional[str] = None
    try:
        resolved_avatar_id = project_paths.normalize_avatar_id(character_section)
    except KeyError:
        resolved_avatar_id = None

    if resolved_avatar_id is not None:
        char_cfg = project_paths.get_avatar_paths(resolved_avatar_id)
        avatar_id = resolved_avatar_id
    else:
        char_cfg = project_paths.get_character_paths(character_section)
        avatar_id = str(char_cfg.get("avatar_id") or character_section)

    candidate_fbxs: List[Union[str, Path]] = []
    for fbx_key in (
        "source_fbx",
        "fbx_shinano",
        "fbx_outfit",
        "fbx_watch",
        "fbx_hair",
    ):
        fbx_val = char_cfg.get(fbx_key)
        if fbx_val and fbx_val not in candidate_fbxs:
            candidate_fbxs.append(fbx_val)

    target_out = output_cfg_path or char_cfg.get("blendshapes_cfg")
    if not target_out:
        rel_default = AVATAR_PRESET_RELATIVE_PATHS.get(
            avatar_id
        ) or DEFAULT_PRESET_RELATIVE_PATHS.get(character_section)
        if rel_default:
            target_out = project_paths.get_project_root() / rel_default
    if not target_out:
        raise ValueError(f"No blendshapes_cfg output path configured for {character_section}")

    target_path_obj = Path(project_paths.to_host_path(str(target_out)))
    existing_comments = _read_leading_cfg_comments(target_path_obj)

    hints_by_avatar = {
        "shinano_casual": ["shinano"],
        "shinano_er": ["shinano", "reunion"],
        "miltina_maid": ["milltina", "miltina"],
        "franklin": ["shinano"],
        "michael": ["shinano", "reunion"],
        "trevor": ["milltina", "miltina"],
    }
    excluded_fbx_meshes = (
        SHINANO_CASUAL_EXTRA_MESHES if avatar_id == "shinano_er" else ()
    )
    should_preserve_cfg = (
        preserve_existing_cfg
        and target_path_obj.is_file()
        and unity_scene_override is None
    )

    resolved = resolve_character_blendshapes(
        char_cfg,
        fbx_paths=candidate_fbxs,
        character_hints=hints_by_avatar.get(
            avatar_id, hints_by_avatar.get(character_section, [character_section])
        ),
        override_source="cfg" if should_preserve_cfg else "auto",
        override_cfg_path=target_path_obj if should_preserve_cfg else None,
        override_unity_scene=unity_scene_override,
        override_avatar_name=avatar_name_override,
        save_cfg_path=target_path_obj,
        fill_missing_from_fbx=fill_missing_from_fbx,
        fbx_excluded_meshes=excluded_fbx_meshes,
        header_comments=existing_comments or None,
    )
    return Path(resolved["saved_cfg_path"]) if resolved["saved_cfg_path"] else None


def main() -> int:
    """CLI entrypoint for exporting Unity project & FBX blendshapes into `.cfg` files."""
    if project_i18n is not None:
        project_i18n.set_active_language()

    parser = argparse.ArgumentParser(
        description=_translate_msg(
            "blendshapes.cli_desc",
            "Export Unity scene/prefab, .anim, and FBX blendshapes into portable .cfg presets.",
        )
    )
    parser.add_argument(
        "--character",
        choices=[
            "franklin",
            "michael",
            "trevor",
            "shinano_casual",
            "shinano_er",
            "miltina_maid",
            "all",
        ],
        default="all",
        help="Target protagonist or avatar preset in vrc2gtav.cfg (default: all)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional explicit .cfg output path (for single-character export)",
    )
    parser.add_argument(
        "--unity-scene",
        default=None,
        help="Optional Unity scene path override",
    )
    parser.add_argument(
        "--overwrite-from-unity",
        action="store_true",
        help="Re-read active weights from Unity scene instead of keeping existing .cfg edits",
    )
    parser.add_argument(
        "--lang",
        choices=["auto", "en", "ja", "pt"],
        default="auto",
        help="Output language (auto, en, ja, pt)",
    )
    parsed_args = parser.parse_args()
    if project_i18n is not None:
        project_i18n.set_active_language(parsed_args.lang)

    targets = (
        ["shinano_casual", "shinano_er", "miltina_maid"]
        if parsed_args.character == "all"
        else [parsed_args.character]
    )
    for char_name in targets:
        out_path = parsed_args.output if len(targets) == 1 else None
        saved = export_character_blendshapes_to_cfg(
            char_name,
            output_cfg_path=out_path,
            unity_scene_override=parsed_args.unity_scene,
            preserve_existing_cfg=not parsed_args.overwrite_from_unity,
        )
        if saved:
            print(
                _translate_msg(
                    "blendshapes.exported_cfg",
                    "[Blendshapes] Exported {char} preset to {path}",
                    char=char_name,
                    path=saved,
                )
            )
        else:
            print(
                _translate_msg(
                    "blendshapes.export_skipped",
                    "[Blendshapes] No Unity blendshapes found for {char}; skipped.",
                    char=char_name,
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
