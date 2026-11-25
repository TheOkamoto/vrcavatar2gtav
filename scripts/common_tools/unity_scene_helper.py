"""
Streaming Unity YAML (.unity / .prefab) parser for vrc2gtav.

Extracts optional anatomical Transform/bone scale overrides and custom hair
visibility from a user's Unity scene without requiring heavy third-party YAML
libraries. When no Unity scene is configured or present (default GitHub
setup), every anatomical bone scale defaults cleanly to (1.0, 1.0, 1.0).
"""

import json
import math
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    import error_handler_helper as err_helper
except Exception:
    err_helper = None

DEFAULT_SCALE: Tuple[float, float, float] = (1.0, 1.0, 1.0)
DEFAULT_SCALE_TOLERANCE: float = 1e-3

_IGNORED_SCALE_NAME_PREFIXES: Tuple[str, ...] = (
    "ph_",
    "pbc",
    "marshmallow_pb",
    "physbone",
    "collider",
    "circlert",
)

_DEFAULT_SHINANO_HAIR_NAMES: Tuple[str, ...] = (
    "hair_base",
    "hair_bang",
    "hair_back",
    "hair_side",
)

_DEFAULT_MILTINA_HAIR_NAMES: Tuple[str, ...] = (
    "milltina_hair_base",
    "milltina_hair_side",
    "milltina_hair_front",
    "milltina_hair_front_side",
    "milltina_hair_twintail",
)

_ALL_DEFAULT_HAIR_NAMES: Set[str] = set(_DEFAULT_SHINANO_HAIR_NAMES) | set(_DEFAULT_MILTINA_HAIR_NAMES)

_SKIP_SEARCH_DIRS: Set[str] = {
    ".git",
    "library",
    "temp",
    "obj",
    "logs",
    "usersettings",
    "textures",
    "texture",
    "materials",
    "material",
    "animations",
    "animation",
    "anim",
    "audio",
    "shaders",
    "shader",
}

_PREFAB_NODE_CACHE: Dict[str, Dict[str, str]] = {}
_GUID_ASSET_CACHE: Dict[str, Optional[Path]] = {}
_YAML_PARSE_CACHE: Dict[Tuple[str, int], Dict[str, object]] = {}


def empty_unity_avatar_config(scene_path_str: str = "") -> Dict[str, object]:
    """Return a default configuration where all anatomical scales are 1.0."""
    return {
        "loaded": False,
        "scene_path": scene_path_str,
        "avatar_name": "",
        "root_active": None,
        "root_scale": DEFAULT_SCALE,
        "armature_scale": DEFAULT_SCALE,
        "bone_scales": {},
        "node_scales": {},
        "base_hair_active": None,
        "custom_hair_names": [],
        "custom_hair_scales": {},
    }


def is_unit_scale(
    scale_xyz: Sequence[float],
    tolerance: float = DEFAULT_SCALE_TOLERANCE,
) -> bool:
    """Return True when all three scale axes are within tolerance of 1.0."""
    return all(abs(float(axis_val) - 1.0) <= tolerance for axis_val in scale_xyz)


def decode_unity_name(raw_name: str) -> str:
    """Decode optional YAML unicode escapes and quotes from a Unity m_Name value."""
    cleaned_name = str(raw_name or "").strip()
    if len(cleaned_name) >= 2 and cleaned_name.startswith('"') and cleaned_name.endswith('"'):
        try:
            decoded_json = json.loads(cleaned_name)
            if isinstance(decoded_json, str):
                return decoded_json.strip()
        except Exception:
            cleaned_name = cleaned_name[1:-1]
    elif len(cleaned_name) >= 2 and cleaned_name.startswith("'") and cleaned_name.endswith("'"):
        cleaned_name = cleaned_name[1:-1].replace("''", "'")
    if "\\u" in cleaned_name or "\\U" in cleaned_name:
        cleaned_name = re.sub(
            r"\\u([0-9a-fA-F]{4})",
            lambda hex_match: chr(int(hex_match.group(1), 16)),
            cleaned_name,
        )
        cleaned_name = re.sub(
            r"\\U([0-9a-fA-F]{8})",
            lambda hex_match: chr(int(hex_match.group(1), 16)),
            cleaned_name,
        )
    return cleaned_name.strip()


def _extract_file_id(raw_field: str) -> str:
    """Extract the integer/string fileID from a Unity YAML reference snippet."""
    if "fileID:" not in raw_field:
        return ""
    after_tag = raw_field.split("fileID:", 1)[1]
    return after_tag.split(",", 1)[0].split("}", 1)[0].strip()


def _extract_guid(raw_field: str) -> str:
    """Extract the 32-char asset guid from a Unity YAML reference snippet."""
    if "guid:" not in raw_field:
        return ""
    after_tag = raw_field.split("guid:", 1)[1]
    return after_tag.split(",", 1)[0].split("}", 1)[0].strip().lower()


def _parse_inline_vec3(raw_vec: str) -> Tuple[float, float, float]:
    """Parse Unity inline `{x: 1, y: 1, z: 1}` text into a 3-float tuple."""
    inner_text = raw_vec.strip().strip("{}")
    parsed_axes = {"x": 1.0, "y": 1.0, "z": 1.0}
    for part_str in inner_text.split(","):
        if ":" not in part_str:
            continue
        axis_key, axis_val = part_str.split(":", 1)
        axis_name = axis_key.strip()
        if axis_name in parsed_axes:
            try:
                parsed_axes[axis_name] = float(axis_val.strip())
            except ValueError:
                pass
    return (parsed_axes["x"], parsed_axes["y"], parsed_axes["z"])


def _is_ignored_scale_node(node_name: str) -> bool:
    """Return True if node_name is a PhysBone/collider helper rather than a mesh bone."""
    lower_name = node_name.strip().lower()
    if not lower_name:
        return True
    return lower_name.startswith(_IGNORED_SCALE_NAME_PREFIXES)


def _stream_parse_unity_yaml(yaml_path: Path) -> Dict[str, object]:
    """Stream-parse GameObject (!u!1), Transform (!u!4), and PrefabInstance (!u!1001) with mtime cache."""
    resolved_path = Path(yaml_path)
    try:
        mtime_ns = resolved_path.stat().st_mtime_ns
    except OSError:
        mtime_ns = -1
    cache_key = (str(resolved_path), mtime_ns)
    cached_doc = _YAML_PARSE_CACHE.get(cache_key)
    if cached_doc is not None:
        return cached_doc
    try:
        parsed_doc = _stream_parse_unity_yaml_uncached(resolved_path)
    except OSError as exc:
        if err_helper is not None:
            logger_obj = err_helper.get_active_logger_from_env(stage_name="unity_scene")
            logger_obj.warning(f"Failed to read Unity YAML {resolved_path}: {exc}")
        return {"game_objects": {}, "transforms": {}, "prefab_instances": {}}
    if mtime_ns >= 0:
        _YAML_PARSE_CACHE[cache_key] = parsed_doc
    return parsed_doc


def _stream_parse_unity_yaml_uncached(yaml_path: Path) -> Dict[str, object]:
    """Uncached streaming parser for GameObject (!u!1), Transform (!u!4), and PrefabInstance (!u!1001)."""
    game_objects: Dict[str, Dict[str, object]] = {}
    transforms: Dict[str, Dict[str, object]] = {}
    prefab_instances: Dict[str, Dict[str, object]] = {}

    current_type = ""
    current_id = ""
    current_game_object: Dict[str, object] = {}
    current_transform: Dict[str, object] = {}
    current_prefab_instance: Dict[str, object] = {}
    in_modifications = False

    def flush_block() -> None:
        if not current_id:
            return
        if current_type == "1":
            game_objects[current_id] = current_game_object
        elif current_type == "4":
            transforms[current_id] = current_transform
        elif current_type == "1001":
            prefab_instances[current_id] = current_prefab_instance

    with open(yaml_path, "r", encoding="utf-8", errors="ignore") as yaml_handle:
        for raw_line in yaml_handle:
            if raw_line.startswith("--- !u!"):
                flush_block()
                header_tokens = raw_line.strip().split()
                current_type = header_tokens[1].replace("!u!", "") if len(header_tokens) > 1 else ""
                current_id = header_tokens[2].lstrip("&") if len(header_tokens) > 2 else ""
                in_modifications = False
                if current_type == "1":
                    current_game_object = {"name": "", "active": 1}
                elif current_type == "4":
                    current_transform = {
                        "go": "",
                        "father": "0",
                        "scale": DEFAULT_SCALE,
                        "pi": "",
                        "src_file_id": "",
                        "src_guid": "",
                    }
                elif current_type == "1001":
                    current_prefab_instance = {
                        "parent": "0",
                        "source_guid": "",
                        "mods": [],
                    }
                continue

            if current_type == "1":
                if raw_line.startswith("  m_Name:"):
                    current_game_object["name"] = decode_unity_name(raw_line.split(":", 1)[1])
                elif raw_line.startswith("  m_IsActive:"):
                    raw_active = raw_line.split(":", 1)[1].strip()
                    current_game_object["active"] = 0 if raw_active == "0" else 1

            elif current_type == "4":
                if raw_line.startswith("  m_GameObject:"):
                    current_transform["go"] = _extract_file_id(raw_line)
                elif raw_line.startswith("  m_Father:"):
                    father_id = _extract_file_id(raw_line)
                    current_transform["father"] = father_id or "0"
                elif raw_line.startswith("  m_LocalScale:"):
                    current_transform["scale"] = _parse_inline_vec3(raw_line.split(":", 1)[1])
                elif raw_line.startswith("  m_PrefabInstance:"):
                    current_transform["pi"] = _extract_file_id(raw_line)
                elif raw_line.startswith("  m_CorrespondingSourceObject:"):
                    current_transform["src_file_id"] = _extract_file_id(raw_line)
                    current_transform["src_guid"] = _extract_guid(raw_line)

            elif current_type == "1001":
                if raw_line.startswith("    m_TransformParent:"):
                    parent_id = _extract_file_id(raw_line)
                    current_prefab_instance["parent"] = parent_id or "0"
                elif raw_line.startswith("  m_SourcePrefab:") or raw_line.startswith("    m_SourcePrefab:"):
                    current_prefab_instance["source_guid"] = _extract_guid(raw_line)
                elif raw_line.startswith("    m_Modifications:"):
                    in_modifications = True
                elif in_modifications:
                    if raw_line.startswith("    - target:"):
                        current_prefab_instance["mods"].append(
                            {
                                "target_id": _extract_file_id(raw_line),
                                "target_guid": _extract_guid(raw_line),
                                "prop": "",
                                "val": "",
                            }
                        )
                    elif raw_line.startswith("      propertyPath:") and current_prefab_instance["mods"]:
                        current_prefab_instance["mods"][-1]["prop"] = raw_line.split(":", 1)[1].strip()
                    elif raw_line.startswith("      value:") and current_prefab_instance["mods"]:
                        raw_val = raw_line.split(":", 1)[1].strip()
                        current_prefab_instance["mods"][-1]["val"] = decode_unity_name(raw_val)
                    elif raw_line.startswith("    m_") or raw_line.startswith("  m_"):
                        in_modifications = False

    flush_block()
    return {
        "game_objects": game_objects,
        "transforms": transforms,
        "prefab_instances": prefab_instances,
    }


def _collect_guid_paths_bounded(
    needed_guids: Set[str],
    search_roots: Sequence[Path],
    fallback_timeout_sec: float = 1.5,
) -> Dict[str, Path]:
    """Locate .prefab/.fbx asset paths for unresolved GUIDs with priority dirs first."""
    resolved: Dict[str, Path] = {}
    remaining: Set[str] = set()
    for guid_str in needed_guids:
        if guid_str in _GUID_ASSET_CACHE:
            cached_path = _GUID_ASSET_CACHE[guid_str]
            if cached_path is not None:
                resolved[guid_str] = cached_path
        elif guid_str:
            remaining.add(guid_str)

    if not remaining:
        return resolved

    visited_dirs: Set[str] = set()
    total_roots = len(search_roots)
    scan_deadline: Optional[float] = None
    for root_idx, root_candidate in enumerate(search_roots):
        if not remaining:
            break
        if not root_candidate or not root_candidate.is_dir():
            continue
        root_key = str(root_candidate.resolve())
        if root_key in visited_dirs:
            continue
        visited_dirs.add(root_key)

        is_broad_fallback = root_idx == total_roots - 1
        scan_deadline = time.monotonic() + fallback_timeout_sec if is_broad_fallback else None

        for current_root, dir_names, file_names in os.walk(root_candidate):
            if scan_deadline is not None and time.monotonic() > scan_deadline:
                dir_names[:] = []
                break
            dir_names[:] = [
                sub_dir
                for sub_dir in dir_names
                if sub_dir.lower() not in _SKIP_SEARCH_DIRS and not sub_dir.startswith(".")
            ]
            for file_name in file_names:
                lower_file = file_name.lower()
                if not lower_file.endswith((".prefab.meta", ".fbx.meta")):
                    continue
                meta_path = os.path.join(current_root, file_name)
                try:
                    with open(meta_path, "r", encoding="utf-8", errors="ignore") as meta_handle:
                        for idx_line, meta_line in enumerate(meta_handle):
                            if meta_line.startswith("guid:"):
                                found_guid = meta_line.split(":", 1)[1].strip().lower()
                                if found_guid:
                                    asset_path = Path(meta_path[:-5])
                                    if asset_path.is_file():
                                        _GUID_ASSET_CACHE.setdefault(found_guid, asset_path)
                                        if found_guid in remaining:
                                            resolved[found_guid] = asset_path
                                            remaining.discard(found_guid)
                                break
                            if idx_line > 8:
                                break
                except OSError:
                    continue
            if not remaining:
                break

    if scan_deadline is None or time.monotonic() <= scan_deadline:
        for missing_guid in remaining:
            _GUID_ASSET_CACHE[missing_guid] = None
    return resolved


def _load_prefab_file_id_names(asset_path: Path) -> Dict[str, str]:
    """Build a map of Transform/GameObject fileID -> node name for a .prefab or .fbx.meta."""
    cache_key = str(asset_path.resolve())
    if cache_key in _PREFAB_NODE_CACHE:
        return _PREFAB_NODE_CACHE[cache_key]

    id_to_name: Dict[str, str] = {}
    if asset_path.suffix.lower() == ".prefab" and asset_path.is_file():
        parsed = _stream_parse_unity_yaml(asset_path)
        game_object_map: Dict[str, Dict[str, object]] = parsed["game_objects"]  # type: ignore[assignment]
        transform_map: Dict[str, Dict[str, object]] = parsed["transforms"]  # type: ignore[assignment]
        for game_object_id, game_object_info in game_object_map.items():
            game_object_name = str(game_object_info.get("name", ""))
            if game_object_name:
                id_to_name[game_object_id] = game_object_name
        for transform_id, transform_info in transform_map.items():
            game_object_name = str(game_object_map.get(str(transform_info.get("go", "")), {}).get("name", ""))
            if game_object_name:
                id_to_name[transform_id] = game_object_name
    elif asset_path.suffix.lower() == ".fbx":
        meta_file = Path(f"{asset_path}.meta")
        if meta_file.is_file():
            in_recycle = False
            with open(meta_file, "r", encoding="utf-8", errors="ignore") as meta_handle:
                for meta_line in meta_handle:
                    stripped = meta_line.strip()
                    if stripped.startswith("fileIDToRecycleName:"):
                        in_recycle = True
                        continue
                    if in_recycle:
                        if not meta_line.startswith("    ") or ":" not in stripped:
                            in_recycle = False
                            continue
                        obj_id, obj_path = stripped.split(":", 1)
                        node_name = obj_path.strip().rsplit("/", 1)[-1]
                        if obj_id.strip() and node_name:
                            id_to_name[obj_id.strip()] = node_name

    _PREFAB_NODE_CACHE[cache_key] = id_to_name
    return id_to_name


def _extract_prefab_instance_identity(
    prefab_instance_info: Dict[str, object],
    root_game_object_file_id: str = "",
) -> Tuple[str, Optional[int]]:
    """Derive a PrefabInstance display name and root active state from its m_Modifications."""
    found_name = ""
    found_active: Optional[int] = None
    root_name_target = ""
    src_guid = str(prefab_instance_info.get("source_guid", "")).lower()
    active_by_target: Dict[str, int] = {}

    for mod_item in prefab_instance_info.get("mods", []):  # type: ignore[union-attr]
        prop_name = str(mod_item.get("prop", ""))
        val_str = str(mod_item.get("val", ""))
        target_id = str(mod_item.get("target_id", ""))
        target_guid = str(mod_item.get("target_guid", "")).lower()
        if prop_name == "m_Name" and val_str:
            is_src_match = bool(src_guid and target_guid == src_guid)
            if not found_name or (is_src_match and root_name_target == ""):
                found_name = val_str
                root_name_target = target_id
        elif prop_name == "m_IsActive" and target_id:
            active_val = 0 if val_str == "0" else 1
            if not src_guid or not target_guid or target_guid == src_guid:
                active_by_target[target_id] = active_val

    if root_game_object_file_id and root_game_object_file_id in active_by_target:
        found_active = active_by_target[root_game_object_file_id]
    elif root_name_target and root_name_target in active_by_target:
        found_active = active_by_target[root_name_target]
    elif not root_name_target and "100000" in active_by_target:
        # Standard Unity ModelImporter FBX root GameObject fileID when root isn't renamed.
        found_active = active_by_target["100000"]

    return found_name, found_active


def _select_target_root(
    game_objects: Dict[str, Dict[str, object]],
    transforms: Dict[str, Dict[str, object]],
    prefab_instances: Dict[str, Dict[str, object]],
    avatar_name: Optional[str],
    character_hints: Sequence[str],
) -> Tuple[str, str, str, Optional[bool]]:
    """Select the target root Transform (`xf`) or PrefabInstance (`pi`).

    Returns `(kind, block_id, resolved_name, active_flag)` where `kind` is
    `'xf'`, `'pi'`, or `''` if nothing matched.
    """
    children_map: Dict[str, List[str]] = {}
    for transform_id, transform_info in transforms.items():
        children_map.setdefault(str(transform_info.get("father", "0")), []).append(transform_id)

    candidates: List[Tuple[int, str, str, str, Optional[bool]]] = []
    normalized_target = avatar_name.strip().lower() if avatar_name else ""
    hint_tokens = [token.strip().lower() for token in character_hints if token and token.strip()]

    def score_candidate(name_val: str, is_active_val: Optional[bool], has_armature_hint: bool) -> int:
        lower_val = name_val.lower()
        if normalized_target:
            if lower_val == normalized_target:
                return 1000 + (50 if is_active_val else 0) + (20 if has_armature_hint else 0)
            if normalized_target in lower_val:
                return 600 + (50 if is_active_val else 0) + (20 if has_armature_hint else 0)
            return -1

        base_score = 0
        for hint_str in hint_tokens:
            if lower_val == hint_str:
                base_score = max(base_score, 400)
            elif hint_str in lower_val:
                base_score = max(base_score, 250)
        if base_score == 0 and not has_armature_hint:
            return -1
        if is_active_val:
            base_score += 100
        if has_armature_hint:
            base_score += 40
        return base_score

    for transform_id, transform_info in transforms.items():
        game_object_info = game_objects.get(str(transform_info.get("go", "")), {})
        game_object_name = str(game_object_info.get("name", ""))
        if not game_object_name:
            continue
        is_top_level = str(transform_info.get("father", "0")) in ("0", "")
        child_names = {
            str(game_objects.get(str(transforms[child_id].get("go", "")), {}).get("name", "")).lower()
            for child_id in children_map.get(transform_id, [])
        }
        has_armature = any(child_name.startswith("armature") for child_name in child_names)
        if not is_top_level and not has_armature and not normalized_target:
            continue
        active_flag = bool(game_object_info.get("active", 1))
        match_score = score_candidate(game_object_name, active_flag, has_armature)
        if match_score >= 0:
            if is_top_level:
                match_score += 25
            candidates.append((match_score, "xf", transform_id, game_object_name, active_flag))

    for prefab_instance_id, prefab_instance_info in prefab_instances.items():
        if str(prefab_instance_info.get("parent", "0")) not in ("0", "") and not normalized_target:
            continue
        prefab_instance_name, prefab_instance_active = _extract_prefab_instance_identity(prefab_instance_info)
        if not prefab_instance_name:
            continue
        active_flag = True if prefab_instance_active is None else bool(prefab_instance_active)
        match_score = score_candidate(prefab_instance_name, active_flag, True)
        if match_score >= 0:
            if str(prefab_instance_info.get("parent", "0")) in ("0", ""):
                match_score += 15
            candidates.append((match_score, "pi", prefab_instance_id, prefab_instance_name, active_flag))

    if not candidates:
        return ("", "", "", None)

    candidates.sort(key=lambda item: item[0], reverse=True)
    _, best_kind, best_id, best_name, best_active = candidates[0]
    return (best_kind, best_id, best_name, best_active)


def _priority_search_dirs(
    scene_path: Path,
    assets_root: Optional[Path],
    avatar_hints: Sequence[str],
) -> List[Path]:
    """Order asset search directories so likely folders are checked before full scan."""
    ordered_dirs: List[Path] = []
    assets_resolved = assets_root.resolve() if assets_root and assets_root.is_dir() else None
    if scene_path.parent.is_dir():
        scene_parent_resolved = scene_path.parent.resolve()
        if assets_resolved is None or scene_parent_resolved != assets_resolved:
            ordered_dirs.append(scene_path.parent)
    if assets_root and assets_root.is_dir():
        try:
            for child_entry in os.scandir(assets_root):
                if child_entry.is_dir():
                    child_lower = child_entry.name.lower()
                    if any(hint in child_lower for hint in avatar_hints):
                        ordered_dirs.append(Path(child_entry.path))
        except OSError:
            pass
        ordered_dirs.append(assets_root)
    return ordered_dirs


def _extract_prefab_instance_scale_mods(
    prefab_instance_info: Dict[str, object],
    tolerance: float,
) -> Tuple[Dict[Tuple[str, str], Tuple[float, float, float]], Dict[Tuple[str, str], str], Set[Tuple[str, str]]]:
    """Collect per-(guid, fileID) scale modifications, renames, and disabled states."""
    axis_groups: Dict[Tuple[str, str], Dict[str, float]] = {}
    target_names: Dict[Tuple[str, str], str] = {}
    disabled_targets: Set[Tuple[str, str]] = set()

    for mod_item in prefab_instance_info.get("mods", []):  # type: ignore[union-attr]
        target_key = (str(mod_item.get("target_guid", "")), str(mod_item.get("target_id", "")))
        prop_name = str(mod_item.get("prop", ""))
        val_str = str(mod_item.get("val", ""))
        if prop_name == "m_Name" and val_str:
            target_names[target_key] = val_str
        elif prop_name == "m_IsActive" and val_str == "0":
            disabled_targets.add(target_key)
        elif prop_name.startswith("m_LocalScale."):
            axis_char = prop_name.rsplit(".", 1)[-1]
            if axis_char in ("x", "y", "z"):
                try:
                    axis_groups.setdefault(target_key, {})[axis_char] = float(val_str)
                except ValueError:
                    pass

    scale_overrides: Dict[Tuple[str, str], Tuple[float, float, float]] = {}
    for target_key, axes_map in axis_groups.items():
        scale_tuple = (
            axes_map.get("x", 1.0),
            axes_map.get("y", 1.0),
            axes_map.get("z", 1.0),
        )
        if not is_unit_scale(scale_tuple, tolerance=tolerance):
            scale_overrides[target_key] = scale_tuple

    return scale_overrides, target_names, disabled_targets


def extract_unity_avatar_config(
    unity_scene_path: Optional[object],
    avatar_name: Optional[str] = None,
    character_hints: Sequence[str] = (),
    assets_root: Optional[object] = None,
    tolerance: float = DEFAULT_SCALE_TOLERANCE,
) -> Dict[str, object]:
    """Parse a Unity .unity scene and extract scales + hair flags for the chosen avatar."""
    raw_scene_str = str(unity_scene_path).strip() if unity_scene_path else ""
    if not raw_scene_str:
        return empty_unity_avatar_config("")

    scene_file = Path(raw_scene_str)
    if not scene_file.is_file():
        return empty_unity_avatar_config(raw_scene_str)

    parsed_yaml = _stream_parse_unity_yaml(scene_file)
    game_objects: Dict[str, Dict[str, object]] = parsed_yaml["game_objects"]  # type: ignore[assignment]
    transforms: Dict[str, Dict[str, object]] = parsed_yaml["transforms"]  # type: ignore[assignment]
    prefab_instances: Dict[str, Dict[str, object]] = parsed_yaml["prefab_instances"]  # type: ignore[assignment]

    root_kind, root_id, resolved_name, root_active = _select_target_root(
        game_objects=game_objects,
        transforms=transforms,
        prefab_instances=prefab_instances,
        avatar_name=avatar_name,
        character_hints=character_hints,
    )
    if not root_kind:
        return empty_unity_avatar_config(str(scene_file))

    result = empty_unity_avatar_config(str(scene_file))
    result["loaded"] = True
    result["avatar_name"] = resolved_name
    result["root_active"] = root_active

    children_map: Dict[str, List[str]] = {}
    for transform_id, transform_info in transforms.items():
        children_map.setdefault(str(transform_info.get("father", "0")), []).append(transform_id)

    bone_scales: Dict[str, Tuple[float, float, float]] = {}
    node_scales: Dict[str, Tuple[float, float, float]] = {}
    armature_scale = DEFAULT_SCALE
    root_scale = DEFAULT_SCALE

    base_hair_flags: List[bool] = []
    custom_hair_names: List[str] = []
    custom_hair_scales: Dict[str, Tuple[float, float, float]] = {}

    subtree_xforms: Set[str] = set()
    relevant_pis: List[Tuple[str, str]] = []

    if root_kind == "xf":
        # BFS from avatar root so primary Armature bones precede nested clothing Armatures.
        node_chain_scales: Dict[Tuple[str, str], List[Tuple[float, float, float]]] = {}
        queue: deque = deque([(root_id, (resolved_name,))])
        while queue:
            cur_transform_id, cur_path = queue.popleft()
            subtree_xforms.add(cur_transform_id)
            transform_info = transforms.get(cur_transform_id, {})
            game_object_info = game_objects.get(str(transform_info.get("go", "")), {})
            game_object_name = str(game_object_info.get("name", "")).strip()
            game_object_active = True if cur_transform_id == root_id else bool(game_object_info.get("active", 1))

            lower_node = game_object_name.lower()
            if lower_node in _ALL_DEFAULT_HAIR_NAMES:
                base_hair_flags.append(bool(game_object_info.get("active", 1)))

            if not game_object_active:
                continue

            node_scale = transform_info.get("scale", DEFAULT_SCALE)
            if isinstance(node_scale, tuple) and not is_unit_scale(node_scale, tolerance=tolerance):
                if not _is_ignored_scale_node(game_object_name):
                    if cur_transform_id == root_id:
                        root_scale = node_scale
                    elif lower_node in ("armature", "armature.1") and len(cur_path) <= 3:
                        if is_unit_scale(armature_scale, tolerance=tolerance):
                            armature_scale = node_scale
                    node_scales.setdefault(game_object_name, node_scale)
                    in_armature = any(segment.lower().startswith("armature") for segment in cur_path)
                    if in_armature and not lower_node.startswith("armature"):
                        arm_index = next(
                            idx for idx, segment in enumerate(cur_path) if segment.lower().startswith("armature")
                        )
                        arm_root_key = "/".join(cur_path[: arm_index + 1])
                        chain_key = (arm_root_key, game_object_name)
                        node_chain_scales.setdefault(chain_key, []).append(node_scale)

            for child_transform_id in children_map.get(cur_transform_id, []):
                child_game_object_id = str(transforms.get(child_transform_id, {}).get("go", ""))
                child_name = str(game_objects.get(child_game_object_id, {}).get("name", ""))
                queue.append((child_transform_id, cur_path + (child_name,)))

        # Collapse Marshmallow PB / PhysBone duplicate wrapper nodes (e.g., 0.5 * 2.0 == 1.0).
        for (_arm_root_key, bone_name), scale_list in node_chain_scales.items():
            net_x = 1.0
            net_y = 1.0
            net_z = 1.0
            for item_scale in scale_list:
                net_x *= item_scale[0]
                net_y *= item_scale[1]
                net_z *= item_scale[2]
            combined_scale = (net_x, net_y, net_z)
            if not is_unit_scale(combined_scale, tolerance=tolerance):
                bone_scales.setdefault(bone_name, combined_scale)

        for prefab_instance_id, prefab_instance_info in prefab_instances.items():
            parent_transform = str(prefab_instance_info.get("parent", "0"))
            if parent_transform in subtree_xforms:
                parent_game_object = game_objects.get(str(transforms.get(parent_transform, {}).get("go", "")), {})
                if parent_transform == root_id or bool(parent_game_object.get("active", 1)):
                    parent_name = str(parent_game_object.get("name", ""))
                    relevant_pis.append((prefab_instance_id, parent_name))
    else:
        relevant_pis.append((root_id, ""))

    assets_dir = Path(str(assets_root)) if assets_root else None
    if assets_dir is None:
        for ancestor_dir in scene_file.parents:
            if ancestor_dir.name.lower() == "assets":
                assets_dir = ancestor_dir
                break

    needed_guids: Set[str] = set()
    prefab_instance_name_tokens: List[str] = []
    for prefab_instance_id, _parent_name in relevant_pis:
        prefab_instance_info = prefab_instances[prefab_instance_id]
        prefab_instance_display_name, prefab_instance_active_flag = _extract_prefab_instance_identity(prefab_instance_info)
        if prefab_instance_active_flag == 0:
            continue
        scale_mods, _, _ = _extract_prefab_instance_scale_mods(prefab_instance_info, tolerance=tolerance)
        if scale_mods and prefab_instance_display_name:
            for split_part in prefab_instance_display_name.replace("_", " ").split():
                if len(split_part) >= 3:
                    prefab_instance_name_tokens.append(split_part.lower())
        for target_guid, _target_id in scale_mods:
            if target_guid:
                needed_guids.add(target_guid)
        src_guid = str(prefab_instance_info.get("source_guid", ""))
        if src_guid and (scale_mods or root_kind == "pi"):
            needed_guids.add(src_guid)

    hint_keywords = [
        word.lower()
        for word in (
            [resolved_name, avatar_name or ""]
            + list(character_hints)
            + prefab_instance_name_tokens
            + ["shinano", "milltina", "miltina", "neko"]
        )
        if word and word.strip()
    ]
    guid_paths: Dict[str, Path] = {}
    if needed_guids:
        search_dirs = _priority_search_dirs(scene_file, assets_dir, hint_keywords)
        guid_paths = _collect_guid_paths_bounded(needed_guids, search_dirs)

    for prefab_instance_id, parent_name in relevant_pis:
        prefab_instance_info = prefab_instances[prefab_instance_id]
        prefab_instance_name, prefab_instance_active = _extract_prefab_instance_identity(prefab_instance_info)
        if prefab_instance_active == 0:
            continue

        scale_mods, inline_names, disabled_targets = _extract_prefab_instance_scale_mods(prefab_instance_info, tolerance=tolerance)
        lower_parent = parent_name.lower()
        lower_prefab_instance = prefab_instance_name.lower()
        looks_like_hair_child = (
            lower_parent in ("head", "hair_root")
            and (
                "hair" in lower_prefab_instance
                or "bob" in lower_prefab_instance
                or "twin" in lower_prefab_instance
                or "ponytail" in lower_prefab_instance
                or "wig" in lower_prefab_instance
            )
        )
        if looks_like_hair_child and prefab_instance_name:
            custom_hair_names.append(prefab_instance_name)

        for target_key, scale_tuple in scale_mods.items():
            if target_key in disabled_targets:
                continue
            resolved_from_target = inline_names.get(target_key, "")
            if not resolved_from_target and target_key[0] in guid_paths:
                prefab_map = _load_prefab_file_id_names(guid_paths[target_key[0]])
                resolved_from_target = prefab_map.get(target_key[1], "")
            resolved_node = resolved_from_target or prefab_instance_name

            if not resolved_node or _is_ignored_scale_node(resolved_node):
                continue

            lower_resolved = resolved_node.lower()
            node_scales.setdefault(resolved_node, scale_tuple)
            if lower_resolved == resolved_name.lower() and root_kind == "pi":
                root_scale = scale_tuple
            elif lower_resolved in ("armature", "armature.1"):
                if is_unit_scale(armature_scale, tolerance=tolerance):
                    armature_scale = scale_tuple
            elif resolved_from_target and (root_kind == "pi" or looks_like_hair_child):
                bone_scales.setdefault(resolved_node, scale_tuple)

            if looks_like_hair_child and resolved_node:
                custom_hair_scales.setdefault(resolved_node, scale_tuple)

    base_hair_active: Optional[bool] = None
    if base_hair_flags:
        base_hair_active = any(base_hair_flags)

    result["root_scale"] = root_scale
    result["armature_scale"] = armature_scale
    result["bone_scales"] = bone_scales
    result["node_scales"] = node_scales
    result["base_hair_active"] = base_hair_active
    result["custom_hair_names"] = custom_hair_names
    result["custom_hair_scales"] = custom_hair_scales
    return result


def get_node_scale(
    unity_config: Optional[Dict[str, object]],
    node_names: Iterable[str],
    default_scale: Tuple[float, float, float] = DEFAULT_SCALE,
) -> Tuple[float, float, float]:
    """Return the first matching non-default node/bone scale from extracted Unity config."""
    if not unity_config or not unity_config.get("loaded"):
        return default_scale
    bone_map = unity_config.get("bone_scales", {}) or {}
    node_map = unity_config.get("node_scales", {}) or {}
    for candidate_name in node_names:
        if candidate_name in bone_map:
            return tuple(bone_map[candidate_name])  # type: ignore[arg-type]
        if candidate_name in node_map:
            return tuple(node_map[candidate_name])  # type: ignore[arg-type]
    return default_scale


def get_uniform_scale(
    unity_config: Optional[Dict[str, object]],
    node_names: Iterable[str],
    default_scale: float = 1.0,
) -> float:
    """Return a uniform scalar (geometric mean of x/y/z) for the named Unity node."""
    scale_xyz = get_node_scale(
        unity_config,
        node_names,
        default_scale=(default_scale, default_scale, default_scale),
    )
    product = max(1e-9, abs(scale_xyz[0] * scale_xyz[1] * scale_xyz[2]))
    return math.pow(product, 1.0 / 3.0)


def apply_unity_bone_scales_to_pose(
    armature_obj,
    unity_config: Optional[Dict[str, object]],
    excluded_bones: Iterable[str] = (),
    tolerance: float = DEFAULT_SCALE_TOLERANCE,
) -> Dict[str, Tuple[float, float, float]]:
    """Apply Unity non-unit bone scales onto matching Blender pose bones.

    By default, when unity_config is unloaded or has empty bone_scales, no pose
    bones are altered so every bone preserves its native 1.0 scale.
    """
    applied: Dict[str, Tuple[float, float, float]] = {}
    if not armature_obj or not unity_config or not unity_config.get("loaded"):
        return applied

    excluded_set = set(excluded_bones)
    bone_map: Dict[str, Tuple[float, float, float]] = unity_config.get("bone_scales", {}) or {}
    lower_lookup = {pose_bone.name.lower(): pose_bone for pose_bone in armature_obj.pose.bones}

    for bone_name, scale_xyz in bone_map.items():
        if bone_name in excluded_set or is_unit_scale(scale_xyz, tolerance=tolerance):
            continue
        pose_bone = armature_obj.pose.bones.get(bone_name) or lower_lookup.get(bone_name.lower())
        if pose_bone is not None:
            pose_bone.scale = (float(scale_xyz[0]), float(scale_xyz[1]), float(scale_xyz[2]))
            applied[pose_bone.name] = scale_xyz
    return applied


def resolve_hair_mode(
    hair_fbx_path: Optional[object],
    unity_config: Optional[Dict[str, object]] = None,
) -> Tuple[str, str]:
    """Decide whether to use `'custom'` external hair FBX or `'default'` base avatar hair."""
    raw_hair_path = str(hair_fbx_path).strip() if hair_fbx_path else ""
    if not raw_hair_path:
        return ("default", "unconfigured")

    hair_file = Path(raw_hair_path)
    if not hair_file.is_file():
        return ("default", "missing_file")

    if unity_config and unity_config.get("loaded"):
        base_hair_active = unity_config.get("base_hair_active")
        custom_hairs = unity_config.get("custom_hair_names") or []
        if base_hair_active is True and not custom_hairs:
            return ("default", "unity_base_hair_active")

    return ("custom", "custom_fbx_present")


def load_unity_avatar_from_cfg(
    char_cfg: Dict[str, object],
    i18n_module=None,
    character_hints: Iterable[str] = (),
) -> Dict[str, object]:
    """Load Unity scene scale overrides from character config and log status."""
    scene_path = str(char_cfg.get("unity_scene", "")).strip()
    avatar_name = str(char_cfg.get("unity_avatar_name", "")).strip() or None
    unity_config = extract_unity_avatar_config(
        scene_path,
        avatar_name=avatar_name,
        character_hints=character_hints,
    )
    has_non_unit_scale = bool(
        unity_config.get("loaded")
        and (
            unity_config.get("bone_scales")
            or not is_unit_scale(unity_config.get("armature_scale", DEFAULT_SCALE))
            or not is_unit_scale(unity_config.get("root_scale", DEFAULT_SCALE))
        )
    )
    if i18n_module is not None:
        if has_non_unit_scale:
            print(
                i18n_module.translate(
                    "unity_scene.loaded",
                    scene=unity_config["scene_path"],
                    avatar=unity_config["avatar_name"],
                    root=unity_config["root_scale"],
                    armature=unity_config["armature_scale"],
                    count=len(unity_config.get("bone_scales", {})),
                )
            )
        else:
            print(i18n_module.translate("unity_scene.default_unit_scales"))
    return unity_config


def compute_gtav_height_mapping(
    bpy_module,
    unity_config: Optional[Dict[str, object]],
    active_mesh_names: Iterable[str],
    probe_names: Iterable[str],
    target_min_z: float,
    target_max_z: float,
    rest_min_z: float,
    rest_max_z: float,
) -> Tuple[float, float]:
    """
    Compute GTA V uniform scale factor and vertical Z offset.

    Preserves calibrated resting bounds when scales are unit (1.0) or limited
    to non-height bones (e.g., Breast/Head), and dynamically fits evaluated
    foot-to-head world bounds whenever Armature or leg/spine bones scale.
    """
    default_scale = (target_max_z - target_min_z) / (rest_max_z - rest_min_z)
    default_offset = target_min_z - (rest_min_z * default_scale)
    if not unity_config or not unity_config.get("loaded"):
        return default_scale, default_offset

    arm_scale = unity_config.get("armature_scale", DEFAULT_SCALE)
    bone_map = unity_config.get("bone_scales", {}) or {}
    height_tokens = ("hips", "spine", "chest", "upper_leg", "lower_leg", "foot", "toe")
    height_changed = not is_unit_scale(arm_scale) or any(
        any(token in bone_name.lower() for token in height_tokens)
        for bone_name in bone_map
    )
    if not height_changed:
        return default_scale, default_offset

    active_set = set(active_mesh_names)
    depsgraph_eval = bpy_module.context.evaluated_depsgraph_get()
    sampled_min_z: Optional[float] = None
    sampled_max_z: Optional[float] = None

    for probe_name in probe_names:
        if active_set and probe_name not in active_set:
            continue
        probe_obj = bpy_module.data.objects.get(probe_name)
        if not probe_obj or probe_obj.type != "MESH":
            continue
        evaluated_probe = probe_obj.evaluated_get(depsgraph_eval)
        temp_mesh = bpy_module.data.meshes.new_from_object(evaluated_probe)
        world_matrix = evaluated_probe.matrix_world
        for vert_item in temp_mesh.vertices:
            world_z = (world_matrix @ vert_item.co).z
            if sampled_min_z is None or world_z < sampled_min_z:
                sampled_min_z = world_z
            if sampled_max_z is None or world_z > sampled_max_z:
                sampled_max_z = world_z
        bpy_module.data.meshes.remove(temp_mesh)

    if (
        sampled_min_z is not None
        and sampled_max_z is not None
        and (sampled_max_z - sampled_min_z) > 0.2
    ):
        computed_scale = (target_max_z - target_min_z) / (sampled_max_z - sampled_min_z)
        computed_offset = target_min_z - (sampled_min_z * computed_scale)
        return computed_scale, computed_offset

    return default_scale, default_offset


def _read_fbx_global_settings_properties(fbx_path: Path) -> Dict[str, float]:
    """Read `UnitScaleFactor` and axis ints from binary or ASCII FBX `GlobalSettings`."""
    props_out: Dict[str, float] = {
        "UnitScaleFactor": 1.0,
        "UpAxis": 1.0,
        "UpAxisSign": 1.0,
        "FrontAxis": 2.0,
        "FrontAxisSign": 1.0,
        "CoordAxis": 0.0,
        "CoordAxisSign": 1.0,
    }
    try:
        raw_bytes = fbx_path.read_bytes()
    except OSError:
        return props_out

    if len(raw_bytes) < 27 or not raw_bytes.startswith(b"Kaydara FBX Binary"):
        text_head = raw_bytes[:32768].decode("utf-8", errors="ignore")
        for key_name in props_out:
            match_val = re.search(rf'P:\s*"{key_name}"[^,\n]*,[^,\n]*,[^,\n]*,[^,\n]*,\s*([-+0-9.eE]+)', text_head)
            if match_val:
                try:
                    props_out[key_name] = float(match_val.group(1))
                except ValueError:
                    pass
        return props_out

    import struct

    fbx_ver = struct.unpack_from("<I", raw_bytes, 23)[0]
    hdr_fmt = "<QQQB" if fbx_ver >= 7500 else "<IIIB"
    hdr_size = 25 if fbx_ver >= 7500 else 13
    total_len = len(raw_bytes)

    def _read_prop_value(pos_cur: int) -> Tuple[object, int]:
        type_code = chr(raw_bytes[pos_cur])
        pos_cur += 1
        if type_code == "Y":
            return struct.unpack_from("<h", raw_bytes, pos_cur)[0], pos_cur + 2
        if type_code == "C":
            return bool(raw_bytes[pos_cur]), pos_cur + 1
        if type_code == "I":
            return struct.unpack_from("<i", raw_bytes, pos_cur)[0], pos_cur + 4
        if type_code == "F":
            return struct.unpack_from("<f", raw_bytes, pos_cur)[0], pos_cur + 4
        if type_code == "D":
            return struct.unpack_from("<d", raw_bytes, pos_cur)[0], pos_cur + 8
        if type_code == "L":
            return struct.unpack_from("<q", raw_bytes, pos_cur)[0], pos_cur + 8
        if type_code in ("S", "R"):
            str_len = struct.unpack_from("<I", raw_bytes, pos_cur)[0]
            pos_cur += 4
            txt_val = raw_bytes[pos_cur : pos_cur + str_len].decode("utf-8", errors="replace") if type_code == "S" else ""
            return txt_val, pos_cur + str_len
        if type_code in ("f", "d", "l", "i", "b"):
            arr_len, enc_flag, comp_len = struct.unpack_from("<III", raw_bytes, pos_cur)
            elem_size = {"f": 4, "d": 8, "l": 8, "i": 4, "b": 1}[type_code]
            return None, pos_cur + 12 + (comp_len if enc_flag == 1 else arr_len * elem_size)
        raise ValueError(type_code)

    def _scan_props(start_pos: int, end_pos: int) -> None:
        pos_cur = start_pos
        while pos_cur + hdr_size <= end_pos:
            end_off, prop_cnt, prop_len, name_len = struct.unpack_from(hdr_fmt, raw_bytes, pos_cur)
            pos_cur += hdr_size
            if end_off == 0 or end_off > end_pos:
                break
            node_name = raw_bytes[pos_cur : pos_cur + name_len].decode("utf-8", errors="replace")
            pos_cur += name_len
            prop_end = pos_cur + prop_len
            vals: List[object] = []
            while pos_cur < prop_end and len(vals) < prop_cnt:
                parsed_val, pos_cur = _read_prop_value(pos_cur)
                vals.append(parsed_val)
            pos_cur = prop_end
            if node_name == "P" and len(vals) >= 5 and isinstance(vals[0], str) and vals[0] in props_out:
                if isinstance(vals[4], (int, float)) and not isinstance(vals[4], bool):
                    props_out[vals[0]] = float(vals[4])
            elif node_name == "Properties70" and pos_cur + hdr_size <= end_off:
                _scan_props(pos_cur, end_off)
            pos_cur = end_off

    top_pos = 27
    try:
        while top_pos + hdr_size <= total_len:
            end_off, _cnt, prop_len, name_len = struct.unpack_from(hdr_fmt, raw_bytes, top_pos)
            top_pos += hdr_size
            if end_off == 0 or end_off > total_len or end_off < top_pos:
                break
            sec_name = raw_bytes[top_pos : top_pos + name_len].decode("utf-8", errors="replace")
            if sec_name == "GlobalSettings":
                _scan_props(top_pos + name_len + prop_len, end_off)
                break
            top_pos = end_off
    except (struct.error, ValueError):
        pass
    return props_out


def compute_fbx_mesh_import_matrix_rows(fbx_path: object) -> List[List[float]]:
    """
    Compute the 4x4 Blender-space import matrix Unity `ModelImporter` applies to a raw
    `Mesh` asset (`m_Mesh` in `MeshFilter`), excluding any FBX scene-node `Lcl` transform.
    """
    resolved_fbx = Path(str(fbx_path))
    meta_global_scale = 1.0
    meta_use_file_scale = True
    meta_path = Path(str(resolved_fbx) + ".meta")
    if meta_path.is_file():
        try:
            meta_txt = meta_path.read_text(encoding="utf-8", errors="ignore")
            scl_match = re.search(r"^\s*globalScale:\s*([-+0-9.eE]+)", meta_txt, re.MULTILINE)
            if scl_match:
                meta_global_scale = float(scl_match.group(1))
            ufs_match = re.search(r"^\s*useFileScale:\s*(\d+)", meta_txt, re.MULTILINE)
            if ufs_match:
                meta_use_file_scale = int(ufs_match.group(1)) != 0
        except (OSError, ValueError):
            pass

    fbx_props = _read_fbx_global_settings_properties(resolved_fbx) if resolved_fbx.is_file() else {}
    unit_scale = float(fbx_props.get("UnitScaleFactor", 1.0))
    eff_scale = meta_global_scale * ((unit_scale * 0.01) if meta_use_file_scale else 1.0)
    if abs(eff_scale) < 1e-8:
        eff_scale = 0.01

    coord_idx = max(0, min(2, int(round(fbx_props.get("CoordAxis", 0.0)))))
    front_idx = max(0, min(2, int(round(fbx_props.get("FrontAxis", 2.0)))))
    up_idx = max(0, min(2, int(round(fbx_props.get("UpAxis", 1.0)))))
    if len({coord_idx, front_idx, up_idx}) != 3:
        coord_idx, up_idx, front_idx = 0, 1, 2
    coord_sign = -1.0 if fbx_props.get("CoordAxisSign", 1.0) < 0 else 1.0
    front_sign = -1.0 if fbx_props.get("FrontAxisSign", 1.0) < 0 else 1.0
    up_sign = -1.0 if fbx_props.get("UpAxisSign", 1.0) < 0 else 1.0

    rows = [[0.0, 0.0, 0.0, 0.0] for _ in range(4)]
    rows[0][coord_idx] = coord_sign * eff_scale
    rows[1][front_idx] = -front_sign * eff_scale
    rows[2][up_idx] = up_sign * eff_scale
    rows[3][3] = 1.0
    return rows
