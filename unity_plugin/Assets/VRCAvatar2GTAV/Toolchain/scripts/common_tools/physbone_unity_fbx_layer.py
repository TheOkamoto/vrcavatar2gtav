"""
physbone_unity_fbx_layer.py
===========================
Layer 3 of 5 for VRChat VRCPhysBone support (`physbone_helper` architecture).

Parses Unity `.prefab` / `.unity` PhysBone YAML streams, inspects binary/ASCII
FBX vertex bone weights to detect active skinned meshes, collects Marshmallow PB
overrides, and prunes orphaned PhysBone chains from inactive or deleted outfits.
"""

from configparser import ConfigParser
import collections as collections_module
import math
import os as operating_system
from pathlib import Path
import re as regex_module
import struct
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union
import zlib

try:
    from physbone_presets_layer import (
        _FBX_WEIGHTED_BONES_CACHE,
    SKEL_HEAD_TAG,
    SKEL_SPINE2_TAG,
    NEKO_MIMI_CHAIN_SPECS,
    VRCHAT_PHYSBONE_SCRIPT_GUID,
    VRCHAT_PHYSBONE_CLASS_FILE_ID,
    resolve_neko_mimi_gtav_bone,
    )
except ImportError:
    from common_tools.physbone_presets_layer import (
        _FBX_WEIGHTED_BONES_CACHE,
    SKEL_HEAD_TAG,
    SKEL_SPINE2_TAG,
    NEKO_MIMI_CHAIN_SPECS,
    VRCHAT_PHYSBONE_SCRIPT_GUID,
    VRCHAT_PHYSBONE_CLASS_FILE_ID,
    resolve_neko_mimi_gtav_bone,
    )

try:
    from physbone_cfg_ini_layer import (
        _parse_yaml_scalar_vec3,
    _parse_yaml_curve,
    )
except ImportError:
    from common_tools.physbone_cfg_ini_layer import (
        _parse_yaml_scalar_vec3,
    _parse_yaml_curve,
    )

def extract_unity_physbones_from_prefab(
    prefab_path: Union[str, Path],
    target_names: Sequence[str] = ("ear.L", "ear.R"),
) -> Dict[str, Dict[str, object]]:
    """
    Parse VRCPhysBone MonoBehaviour blocks from a Unity .prefab YAML file.

    Returns a dictionary keyed by target GameObject name (`ear.L`, `ear.R`, ...)
    with exact parameters, curves, and resolved chain bone mapping.
    """
    resolved_prefab = Path(prefab_path)
    if not resolved_prefab.is_file():
        raise FileNotFoundError(f"Unity prefab not found: {resolved_prefab}")

    raw_text = resolved_prefab.read_text(encoding="utf-8", errors="replace")
    documents = regex_module.split(r"(?=^--- !u!\d+ &\d+)", raw_text, flags=regex_module.MULTILINE)

    gameobject_names: Dict[str, str] = {}
    physbone_blocks: Dict[str, str] = {}
    target_lookup = {name.lower(): name for name in target_names}

    for doc_text in documents:
        header_match = regex_module.match(r"^--- !u!(\d+) &(\d+)", doc_text)
        if not header_match:
            continue
        class_id = header_match.group(1)
        file_id = header_match.group(2)
        if class_id == "1":
            name_match = regex_module.search(r"^\s*m_Name:\s*(.+?)\s*$", doc_text, regex_module.MULTILINE)
            if name_match:
                gameobject_names[file_id] = name_match.group(1).strip()
        elif (
            class_id == "114"
            and VRCHAT_PHYSBONE_SCRIPT_GUID in doc_text
            and f"fileID: {VRCHAT_PHYSBONE_CLASS_FILE_ID}" in doc_text
        ):
            game_object_match = regex_module.search(r"^\s*m_GameObject:\s*\{fileID:\s*(\d+)\}", doc_text, regex_module.MULTILINE)
            if game_object_match:
                physbone_blocks[game_object_match.group(1)] = doc_text

    extracted: Dict[str, Dict[str, object]] = {}
    spec_by_key = {spec[0].lower(): spec for spec in NEKO_MIMI_CHAIN_SPECS}

    def read_float(block_text: str, key_name: str, default_val: float) -> float:
        matched = regex_module.search(rf"^\s*{regex_module.escape(key_name)}:\s*([-+0-9.eE]+)\s*$", block_text, regex_module.MULTILINE)
        return float(matched.group(1)) if matched else default_val

    def read_int(block_text: str, key_name: str, default_val: int) -> int:
        matched = regex_module.search(rf"^\s*{regex_module.escape(key_name)}:\s*([-+]?\d+)\s*$", block_text, regex_module.MULTILINE)
        return int(matched.group(1)) if matched else default_val

    for game_object_id, block_text in physbone_blocks.items():
        game_object_name = gameobject_names.get(game_object_id, "")
        canonical_name = target_lookup.get(game_object_name.lower())
        if canonical_name is None:
            continue
        spec_entry = spec_by_key.get(canonical_name.lower())
        source_bones = list(spec_entry[2]) if spec_entry else [canonical_name]
        chain_bones = list(spec_entry[3]) if spec_entry else [resolve_neko_mimi_gtav_bone(canonical_name) or canonical_name]

        extracted[canonical_name] = {
            "source_key": canonical_name,
            "root_bone": chain_bones[0],
            "chain_bones": chain_bones,
            "source_bones": source_bones,
            "parent_bone": "SKEL_Head",
            "parent_bone_tag": SKEL_HEAD_TAG,
            "version": read_int(block_text, "version", 1),
            "integration_type": read_int(block_text, "integrationType", 0),
            "multi_child_type": read_int(block_text, "multiChildType", 0),
            "endpoint_position": _parse_yaml_scalar_vec3(block_text, "endpointPosition", (0.0, 0.0, 0.0)),
            "pull": read_float(block_text, "pull", 0.2),
            "spring": read_float(block_text, "spring", 0.35),
            "stiffness": read_float(block_text, "stiffness", 0.2),
            "gravity": read_float(block_text, "gravity", 0.0),
            "gravity_falloff": read_float(block_text, "gravityFalloff", 0.0),
            "immobile_type": read_int(block_text, "immobileType", 0),
            "immobile": read_float(block_text, "immobile", 0.3),
            "allow_collision": read_int(block_text, "allowCollision", 1),
            "radius": read_float(block_text, "radius", 0.025),
            "radius_curve": _parse_yaml_curve(block_text, "radiusCurve"),
            "limit_type": read_int(block_text, "limitType", 1),
            "max_angle_x": read_float(block_text, "maxAngleX", 50.0),
            "max_angle_x_curve": _parse_yaml_curve(block_text, "maxAngleXCurve"),
            "max_angle_z": read_float(block_text, "maxAngleZ", 45.0),
            "limit_rotation": _parse_yaml_scalar_vec3(block_text, "limitRotation", (14.12, 0.0, 0.0)),
            "allow_grabbing": read_int(block_text, "allowGrabbing", 1),
            "allow_posing": read_int(block_text, "allowPosing", 1),
            "grab_movement": read_float(block_text, "grabMovement", 0.5),
            "max_stretch": read_float(block_text, "maxStretch", 0.0),
            "max_squish": read_float(block_text, "maxSquish", 0.0),
            "stretch_motion": read_float(block_text, "stretchMotion", 0.0),
            "is_animated": read_int(block_text, "isAnimated", 1),
        }

    return extracted


def _parse_unity_yaml_ref(line_val: str) -> Optional[Tuple[str, str]]:
    """Parse `{fileID: 123, guid: abc}` reference text into `(file_id, guid)`."""
    matched = regex_module.search(r"fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-fA-F]+))?", line_val)
    if not matched:
        return None
    return (matched.group(1), (matched.group(2) or "").lower())


def _read_unity_meta_guid(asset_path: Path) -> str:
    """Read Unity asset GUID string (lowercase) from sibling `<asset>.meta` if present."""
    meta_file = Path(f"{asset_path}.meta")
    if not meta_file.is_file():
        return ""
    try:
        for raw_line in meta_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("guid:"):
                return stripped.split(":", 1)[1].strip().lower()
    except OSError:
        pass
    return ""


def _inspect_fbx_weights_detailed(
    fbx_paths: Sequence[Union[str, Path]],
    excluded_meshes: Sequence[str] = (),
) -> Tuple[Set[str], Set[str], Dict[str, str], Dict[Path, Dict[str, Set[str]]], bool]:
    """
    Fast pure-Python binary FBX inspector returning:
      `(all_bones_ci, weighted_bones_ci, parent_map_ci, mesh_weights_by_file, has_skin_clusters)`.
    """
    all_bones_lower: Set[str] = set()
    weighted_bones_lower: Set[str] = set()
    parent_map_lower: Dict[str, str] = {}
    mesh_weights_by_file: Dict[Path, Dict[str, Set[str]]] = {}
    has_skin_clusters = False
    excluded_low = {str(name_item).strip().lower() for name_item in excluded_meshes if str(name_item).strip()}

    def _read_prop(
        raw_bytes: bytes, byte_pos: int, total_len: int, parse_weights_array: bool = False
    ) -> Tuple[Any, int]:
        if byte_pos >= total_len:
            raise ValueError("Truncated FBX property")
        type_code = chr(raw_bytes[byte_pos])
        byte_pos += 1
        if type_code == "Y":
            return struct.unpack_from("<h", raw_bytes, byte_pos)[0], byte_pos + 2
        if type_code == "C":
            return bool(raw_bytes[byte_pos]), byte_pos + 1
        if type_code == "I":
            return struct.unpack_from("<i", raw_bytes, byte_pos)[0], byte_pos + 4
        if type_code == "F":
            return struct.unpack_from("<f", raw_bytes, byte_pos)[0], byte_pos + 4
        if type_code == "D":
            return struct.unpack_from("<d", raw_bytes, byte_pos)[0], byte_pos + 8
        if type_code == "L":
            return struct.unpack_from("<q", raw_bytes, byte_pos)[0], byte_pos + 8
        if type_code in ("S", "R"):
            str_len = struct.unpack_from("<I", raw_bytes, byte_pos)[0]
            byte_pos += 4
            raw_slice = raw_bytes[byte_pos : byte_pos + str_len]
            val = raw_slice.decode("utf-8", errors="replace") if type_code == "S" else str_len
            return val, byte_pos + str_len
        if type_code in ("f", "d", "l", "i", "b"):
            arr_len, enc_flag, comp_len = struct.unpack_from("<III", raw_bytes, byte_pos)
            byte_pos += 12
            if parse_weights_array and type_code == "d" and arr_len > 0:
                if byte_pos + comp_len > total_len:
                    return 0.0, total_len
                buf_bytes = raw_bytes[byte_pos : byte_pos + comp_len]
                if enc_flag == 1:
                    buf_bytes = zlib.decompress(buf_bytes)
                unpack_cnt = min(arr_len, len(buf_bytes) // 8)
                if unpack_cnt <= 0:
                    return 0.0, byte_pos + comp_len
                vals = struct.unpack_from(f"<{unpack_cnt}d", buf_bytes)
                return max(vals) if vals else 0.0, byte_pos + comp_len
            elem_size = {"f": 4, "d": 8, "l": 8, "i": 4, "b": 1}[type_code]
            byte_span = comp_len if enc_flag == 1 else (arr_len * elem_size)
            return arr_len, byte_pos + byte_span
        raise ValueError(f"Unsupported FBX property code: {type_code}")

    def _read_node(
        raw_bytes: bytes,
        byte_pos: int,
        total_len: int,
        hdr_fmt: str,
        hdr_size: int,
        parse_props: bool = False,
        parse_children: bool = False,
        parse_weights: bool = False,
    ) -> Tuple[Optional[Tuple[str, List[Any], List[Any]]], int]:
        if byte_pos + hdr_size > total_len:
            return None, total_len
        end_offset, prop_cnt, prop_len, name_len = struct.unpack_from(hdr_fmt, raw_bytes, byte_pos)
        if end_offset == 0:
            return None, byte_pos + hdr_size
        if end_offset <= byte_pos or end_offset > total_len:
            return None, total_len
        byte_pos += hdr_size
        node_name = raw_bytes[byte_pos : byte_pos + name_len].decode("utf-8", errors="replace")
        byte_pos += name_len
        prop_list: List[Any] = []
        prop_end = min(end_offset, byte_pos + prop_len)
        want_weights_here = parse_weights or node_name == "Weights"
        if parse_props:
            for _prop_idx in range(prop_cnt):
                if byte_pos >= prop_end:
                    break
                prop_val, byte_pos = _read_prop(
                    raw_bytes, byte_pos, total_len, parse_weights_array=want_weights_here
                )
                prop_list.append(prop_val)
        byte_pos = prop_end
        child_list: List[Any] = []
        want_child_weights = (
            node_name == "Deformer"
            and len(prop_list) >= 3
            and prop_list[2] == "Cluster"
        )
        if parse_children:
            while byte_pos + hdr_size <= end_offset:
                child_node, next_pos = _read_node(
                    raw_bytes,
                    byte_pos,
                    total_len,
                    hdr_fmt,
                    hdr_size,
                    parse_props=True,
                    parse_children=(node_name == "Objects" or want_child_weights),
                    parse_weights=want_child_weights,
                )
                if child_node is None or next_pos <= byte_pos:
                    break
                byte_pos = next_pos
                child_list.append(child_node)
        return (node_name, prop_list, child_list), end_offset

    for raw_path in fbx_paths:
        if not raw_path:
            continue
        fbx_file = Path(raw_path)
        if not fbx_file.is_file():
            continue
        try:
            mtime_ns = fbx_file.stat().st_mtime_ns
        except OSError:
            continue

        cache_key = (str(fbx_file.resolve()), mtime_ns)
        cached_fbx = _FBX_WEIGHTED_BONES_CACHE.get(cache_key)
        if cached_fbx is not None:
            file_bones, file_mesh_weights, file_parents = cached_fbx
            all_bones_lower.update(file_bones)
            mesh_weights_by_file[fbx_file] = file_mesh_weights
            for child_key, parent_val in file_parents.items():
                parent_map_lower.setdefault(child_key, parent_val)
            for mesh_low, weight_set in file_mesh_weights.items():
                if weight_set:
                    has_skin_clusters = True
                if mesh_low not in excluded_low:
                    weighted_bones_lower.update(weight_set)
            continue

        try:
            raw_bytes = fbx_file.read_bytes()
        except OSError:
            continue
        total_len = len(raw_bytes)
        if total_len < 27 or not raw_bytes.startswith(b"Kaydara FBX Binary"):
            continue

        file_bones_lower: Set[str] = set()
        file_parents_lower: Dict[str, str] = {}
        file_mesh_weights: Dict[str, Set[str]] = {}
        try:
            fbx_ver = struct.unpack_from("<I", raw_bytes, 23)[0]
            is_64bit = fbx_ver >= 7500
            hdr_fmt = "<QQQB" if is_64bit else "<IIIB"
            hdr_size = 25 if is_64bit else 13

            cursor = 27
            models_map: Dict[int, Tuple[str, str]] = {}
            geom_ids: Set[int] = set()
            skin_ids: Set[int] = set()
            cluster_maxw: Dict[int, float] = {}
            conns_list: List[Tuple[int, int]] = []

            while cursor <= total_len - hdr_size:
                end_offset, _pc, _pl, name_len = struct.unpack_from(hdr_fmt, raw_bytes, cursor)
                if end_offset == 0 or end_offset <= cursor or end_offset > total_len:
                    break
                top_name = raw_bytes[cursor + hdr_size : cursor + hdr_size + name_len].decode(
                    "utf-8", errors="replace"
                )
                if top_name in ("Objects", "Connections"):
                    parsed_top, next_cursor = _read_node(
                        raw_bytes,
                        cursor,
                        total_len,
                        hdr_fmt,
                        hdr_size,
                        parse_props=True,
                        parse_children=True,
                    )
                    if parsed_top is None or next_cursor <= cursor:
                        break
                    cursor = next_cursor
                    if top_name == "Objects":
                        for sub_node in parsed_top[2]:
                            sub_type = sub_node[0]
                            sub_props = sub_node[1]
                            if sub_type == "Model" and len(sub_props) >= 3:
                                models_map[sub_props[0]] = (
                                    str(sub_props[1]).split("\x00")[0],
                                    str(sub_props[2]),
                                )
                            elif sub_type == "Geometry" and len(sub_props) >= 1:
                                geom_ids.add(sub_props[0])
                            elif sub_type == "Deformer" and len(sub_props) >= 3:
                                if sub_props[2] == "Skin":
                                    skin_ids.add(sub_props[0])
                                elif sub_props[2] == "Cluster":
                                    max_weight = 0.0
                                    for csub in sub_node[2]:
                                        if csub[0] == "Weights" and csub[1] and isinstance(csub[1][0], (int, float)):
                                            max_weight = float(csub[1][0])
                                    cluster_maxw[sub_props[0]] = max_weight
                    else:
                        for sub_node in parsed_top[2]:
                            if sub_node[0] == "C" and len(sub_node[1]) >= 3:
                                conns_list.append((sub_node[1][1], sub_node[1][2]))
                else:
                    cursor = end_offset

            children_of: Dict[int, List[int]] = {}
            for src_id, dst_id in conns_list:
                children_of.setdefault(dst_id, []).append(src_id)
                if src_id in models_map and dst_id in models_map:
                    src_name, src_subtype = models_map[src_id]
                    dst_name, dst_subtype = models_map[dst_id]
                    if src_subtype in ("LimbNode", "Null", "Root") and dst_subtype in ("LimbNode", "Null", "Root"):
                        file_parents_lower.setdefault(src_name.lower(), dst_name.lower())

            for model_id, (model_name, model_subtype) in models_map.items():
                if model_subtype in ("LimbNode", "Null", "Root"):
                    file_bones_lower.add(model_name.lower())
                if model_subtype != "Mesh":
                    continue
                mesh_low = model_name.strip().lower()
                mesh_weight_set = file_mesh_weights.setdefault(mesh_low, set())
                for geom_id in children_of.get(model_id, []):
                    if geom_id not in geom_ids:
                        continue
                    for skin_id in children_of.get(geom_id, []):
                        if skin_id not in skin_ids:
                            continue
                        for cluster_id in children_of.get(skin_id, []):
                            if cluster_maxw.get(cluster_id, 0.0) <= 1e-4:
                                continue
                            for bone_id in children_of.get(cluster_id, []):
                                if bone_id in models_map:
                                    mesh_weight_set.add(models_map[bone_id][0].lower())
        except (struct.error, ValueError, zlib.error, IndexError):
            continue

        _FBX_WEIGHTED_BONES_CACHE[cache_key] = (file_bones_lower, file_mesh_weights, file_parents_lower)
        all_bones_lower.update(file_bones_lower)
        mesh_weights_by_file[fbx_file] = file_mesh_weights
        for child_key, parent_val in file_parents_lower.items():
            parent_map_lower.setdefault(child_key, parent_val)
        for mesh_low, weight_set in file_mesh_weights.items():
            if weight_set:
                has_skin_clusters = True
            if mesh_low not in excluded_low:
                weighted_bones_lower.update(weight_set)

    return all_bones_lower, weighted_bones_lower, parent_map_lower, mesh_weights_by_file, has_skin_clusters


def collect_fbx_weighted_bones(
    fbx_paths: Sequence[Union[str, Path]],
    excluded_meshes: Sequence[str] = (),
) -> Tuple[Set[str], Set[str], Dict[str, str]]:
    """
    Fast pure-Python binary FBX inspector extracting all armature bone names (lowercase),
    nonzero vertex-weighted bone names (lowercase), and lowercase `child -> parent` map.
    """
    all_bones_lower, weighted_bones_lower, parent_map_lower, _by_file, _has_skin = _inspect_fbx_weights_detailed(
        fbx_paths, excluded_meshes=excluded_meshes
    )
    return all_bones_lower, weighted_bones_lower, parent_map_lower


def prune_orphaned_physbone_chains(
    chains_map: Dict[str, Dict[str, Any]],
    active_weighted_bones_lower: Optional[Set[str]],
    bone_mapping: Optional[Dict[str, str]] = None,
    disabled_mesh_bones_lower: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Remove orphaned PhysBone chains whose source bones have zero skin weights on active meshes
    (e.g., leftover PhysBones from an old dress deleted or toggled off after adding a custom dress).
    """
    if active_weighted_bones_lower is None:
        return {
            "chains": dict(chains_map),
            "bone_mapping": dict(bone_mapping or {}),
            "orphaned_physbones": [],
        }

    disabled_lower = set(disabled_mesh_bones_lower or ())
    kept_chains: Dict[str, Dict[str, Any]] = {}
    orphaned_records: List[Dict[str, Any]] = []
    orphan_src_fallbacks: Dict[str, str] = {}
    removed_gtav_bones: Set[str] = set()

    for chain_key, cfg_data in chains_map.items():
        src_bones = [
            str(bone_name).strip()
            for bone_name in (cfg_data.get("source_bones") or ())
            if str(bone_name).strip()
        ]
        gtav_bones = [
            str(bone_name).strip()
            for bone_name in (cfg_data.get("chain_bones") or ())
            if str(bone_name).strip()
        ]
        parent_bone = str(cfg_data.get("parent_bone") or "SKEL_Pelvis")
        has_active_weight = any(bone_name.lower() in active_weighted_bones_lower for bone_name in src_bones)
        if has_active_weight:
            kept_chains[chain_key] = cfg_data
            continue

        reason_tok = (
            "disabled_old_outfit_mesh"
            if any(bone_name.lower() in disabled_lower for bone_name in src_bones)
            else "no_active_mesh_weights"
        )
        removed_gtav_bones.update(gtav_bones)
        for bone_name in src_bones:
            orphan_src_fallbacks[bone_name.lower()] = parent_bone
        orphaned_records.append(
            {
                "chain_key": str(chain_key),
                "root_bone": src_bones[0] if src_bones else str(chain_key),
                "parent_bone": parent_bone,
                "reason": reason_tok,
                "source_bones": src_bones,
            }
        )

    cleaned_bmap: Dict[str, str] = {}
    for source_key, dst_v in (bone_mapping or {}).items():
        src_low = str(source_key).strip().lower()
        if str(dst_v).strip() in removed_gtav_bones or src_low in orphan_src_fallbacks:
            continue
        cleaned_bmap[source_key] = dst_v

    return {
        "chains": kept_chains,
        "bone_mapping": cleaned_bmap,
        "orphaned_physbones": orphaned_records,
    }


_UNITY_GUID_CACHE: Dict[str, Dict[str, Path]] = {}
_UNITY_GUID_SCAN_STATE: Dict[str, Dict[str, Any]] = {}


def _index_unity_asset_guids(
    unity_assets_root: Optional[Union[str, Path]],
    needed_guids: Set[str],
    seed_files: Sequence[Union[str, Path]] = (),
    character_hints: Sequence[str] = (),
    deadline_sec: float = 20.0,
) -> Dict[str, Path]:
    """
    Fast breadth-first GUID indexer scanning prioritized Unity asset subfolders (depth 1-3)
    with a persistent resumable scan state per `unity_assets_root` so repeated queries stay instant.
    """
    import time as time_mod

    needed_low = {guid_str.strip().lower() for guid_str in needed_guids if guid_str}
    if not needed_low:
        return {}

    try:
        import unity_scene_helper
    except ImportError:
        unity_scene_helper = None

    skip_dirs = (
        set(getattr(unity_scene_helper, "_SKIP_SEARCH_DIRS", set()))
        if unity_scene_helper
        else {".git", "Library", "Temp", "Obj", "Logs"}
    ) | {
        "texture", "textures", "tex", "material", "materials", "mat",
        "shader", "shaders", "animation", "animations", "anim", "psd",
        "audio", "sound", "sfx", "vfx", "particle", "particles", "sprites",
        "fx", "mask", "masks", "normal", "normals", "plugins", "editor",
        "vrcsdk", "samples", "__backup",
    }

    assets_dir_resolved = (
        Path(unity_assets_root).resolve()
        if unity_assets_root and Path(unity_assets_root).is_dir()
        else None
    )
    cache_key = str(assets_dir_resolved or "")
    cached_map = _UNITY_GUID_CACHE.setdefault(cache_key, {})

    try:
        import modular_avatar_helper as ma_helper_mod
        ma_shared_cache = getattr(ma_helper_mod, "_MA_GUID_CACHE", {})
    except ImportError:
        ma_shared_cache = {}
    for guid_key in needed_low:
        if guid_key not in cached_map:
            shared_path = ma_shared_cache.get(guid_key)
            if shared_path is not None and shared_path.is_file():
                cached_map[guid_key] = shared_path

    guid_map: Dict[str, Path] = {
        guid_key: cached_map[guid_key]
        for guid_key in needed_low
        if guid_key in cached_map and cached_map[guid_key].is_file()
    }
    remaining = needed_low - set(guid_map)
    scan_state = _UNITY_GUID_SCAN_STATE.setdefault(
        cache_key,
        {"seen_dirs": set(), "queue": collections_module.deque(), "initialized": False, "complete": False},
    )
    if not remaining or (assets_dir_resolved is not None and scan_state["complete"]):
        return guid_map

    def _is_safe_subdir(dir_path: Path) -> bool:
        if not dir_path.is_dir():
            return False
        res_dir = dir_path.resolve()
        if assets_dir_resolved is not None and (
            res_dir == assets_dir_resolved or res_dir in assets_dir_resolved.parents
        ):
            return False
        if res_dir == res_dir.parent:
            return False
        return True

    candidate_roots: List[Path] = []
    if assets_dir_resolved is not None:
        marsh_dir = assets_dir_resolved / "marshmallow_PB"
        if _is_safe_subdir(marsh_dir):
            candidate_roots.append(marsh_dir)

    for seed_item in seed_files:
        if not seed_item:
            continue
        seed_path = Path(seed_item).resolve()
        cur_parent = seed_path.parent
        best_pkg_dir: Optional[Path] = None
        for _step in range(5):
            if _is_safe_subdir(cur_parent):
                best_pkg_dir = cur_parent
            if assets_dir_resolved is not None and cur_parent.parent == assets_dir_resolved:
                break
            cur_parent = cur_parent.parent
        if best_pkg_dir is not None:
            candidate_roots.append(best_pkg_dir)

    if assets_dir_resolved is not None:
        pkg_keywords = {
            "shinano", "miltina", "milltina", "eternal", "reunion",
            "dolos", "vagrant", "li-ne", "marshmallow", "retargeted", "converted",
        }
        for hint_str in character_hints:
            for tok_str in regex_module.split(r"[^A-Za-z0-9]+", str(hint_str or "").lower()):
                if len(tok_str) >= 3:
                    pkg_keywords.add(tok_str)

        def _collect_depth_hints(root_dir_item: Path, rem_depth: int) -> None:
            if rem_depth <= 0:
                return
            try:
                sub_entries = list(operating_system.scandir(root_dir_item))
            except OSError:
                return
            for dir_entry in sub_entries:
                if not dir_entry.is_dir(follow_symlinks=False) or dir_entry.name.startswith("."):
                    continue
                low_name = dir_entry.name.lower()
                if low_name in skip_dirs:
                    continue
                cand_dir = Path(dir_entry.path)
                if any(word_tok in low_name for word_tok in pkg_keywords):
                    if _is_safe_subdir(cand_dir):
                        candidate_roots.append(cand_dir)
                else:
                    _collect_depth_hints(cand_dir, rem_depth - 1)

        _collect_depth_hints(assets_dir_resolved, 3)

    seen_dirs: Set[Path] = scan_state["seen_dirs"] if assets_dir_resolved is not None else set()
    bfs_queue = collections_module.deque()
    for root_dir in candidate_roots:
        res_root = root_dir.resolve()
        if res_root not in seen_dirs and _is_safe_subdir(res_root):
            bfs_queue.append((res_root, 0))

    start_time = time_mod.monotonic()

    def _scan_meta_dir(dir_queue: collections_module.deque, max_depth: int, max_dirs: int) -> bool:
        dirs_scanned = 0
        while dir_queue and remaining and dirs_scanned < max_dirs:
            if (time_mod.monotonic() - start_time) > deadline_sec:
                return False
            cur_dir, cur_depth = dir_queue.popleft()
            if cur_dir in seen_dirs:
                continue
            seen_dirs.add(cur_dir)
            dirs_scanned += 1
            try:
                dir_entries = list(operating_system.scandir(cur_dir))
            except OSError:
                continue
            for entry_item in dir_entries:
                entry_name = entry_item.name
                if entry_item.is_dir(follow_symlinks=False):
                    low_dir = entry_name.lower()
                    if (
                        cur_depth < max_depth
                        and not entry_name.startswith(".")
                        and low_dir not in skip_dirs
                    ):
                        sub_res = Path(entry_item.path).resolve()
                        if sub_res not in seen_dirs:
                            dir_queue.append((sub_res, cur_depth + 1))
                elif entry_name.endswith(".meta"):
                    base_name = entry_name[:-5]
                    if not base_name.lower().endswith((".prefab", ".fbx", ".asset")):
                        continue
                    try:
                        with open(entry_item.path, "r", encoding="utf-8", errors="ignore") as meta_file:
                            for _line_idx in range(8):
                                meta_line = meta_file.readline()
                                if not meta_line:
                                    break
                                if meta_line.startswith("guid:"):
                                    guid_val = meta_line.split(":", 1)[1].strip().lower()
                                    asset_path = Path(cur_dir) / base_name
                                    cached_map[guid_val] = asset_path
                                    if guid_val in remaining:
                                        guid_map[guid_val] = asset_path
                                        remaining.discard(guid_val)
                                    break
                    except OSError:
                        pass
        return len(dir_queue) == 0

    _scan_meta_dir(bfs_queue, max_depth=6, max_dirs=1000)

    # Resumable BFS across remaining asset folders only if GUIDs are still missing
    if remaining and assets_dir_resolved is not None and (time_mod.monotonic() - start_time) < deadline_sec:
        if not scan_state["initialized"]:
            scan_state["initialized"] = True
            try:
                for dir_entry in sorted(operating_system.scandir(assets_dir_resolved), key=lambda ent: ent.name):
                    if dir_entry.is_dir(follow_symlinks=False) and not dir_entry.name.startswith("."):
                        if dir_entry.name.lower() not in skip_dirs:
                            sub_res = Path(dir_entry.path).resolve()
                            if sub_res not in seen_dirs:
                                scan_state["queue"].append((sub_res, 0))
            except OSError:
                pass
        finished_all = _scan_meta_dir(scan_state["queue"], max_depth=6, max_dirs=10000)
        if finished_all and len(scan_state["queue"]) == 0:
            scan_state["complete"] = True

    return guid_map


_STREAM_PHYSBONE_DOC_CACHE: Dict[Tuple[str, int], Dict[str, Any]] = {}


def _stream_parse_unity_physbone_doc(doc_path: Path) -> Dict[str, Any]:
    """O(N) streaming YAML parser extracting GO, Transform, VRCPhysBone, Marshmallow PB, and PrefabInstance."""
    try:
        cache_key = (str(doc_path.resolve()), doc_path.stat().st_mtime_ns)
    except OSError:
        cache_key = None
    if cache_key is not None and cache_key in _STREAM_PHYSBONE_DOC_CACHE:
        return _STREAM_PHYSBONE_DOC_CACHE[cache_key]

    gameobjects: Dict[str, Dict[str, Any]] = {}
    transforms: Dict[str, Dict[str, Any]] = {}
    physbones: Dict[str, Dict[str, Any]] = {}
    marshmallow_setups: Dict[str, Dict[str, Any]] = {}
    skinned_meshes: Dict[str, Dict[str, Any]] = {}
    prefab_instances: Dict[str, Dict[str, Any]] = {}

    cur_cls: Optional[str] = None
    cur_id: Optional[str] = None
    cur_stripped = False
    cur_obj: Optional[Dict[str, Any]] = None
    in_ignored = False
    cur_prefab_instance_section = "none"
    cur_mod: Optional[Dict[str, Any]] = None
    cur_curve_name: Optional[str] = None
    cur_curve_time: Optional[float] = None
    cur_marsh_list: Optional[str] = None

    header_regex = regex_module.compile(r"^--- !u!(\d+) &(-?\d+)(\s+stripped)?")

    def _flush_cur() -> None:
        nonlocal cur_obj
        if cur_obj is None or cur_id is None:
            cur_obj = None
            return
        cur_obj["stripped"] = cur_stripped
        if cur_cls == "1":
            gameobjects[cur_id] = cur_obj
        elif cur_cls == "4":
            transforms[cur_id] = cur_obj
        elif cur_cls == "137":
            skinned_meshes[cur_id] = cur_obj
        elif cur_cls == "1001":
            prefab_instances[cur_id] = cur_obj
        elif cur_cls == "114":
            if cur_obj.get("is_physbone"):
                physbones[cur_id] = cur_obj
            elif cur_obj.get("is_marshmallow"):
                marshmallow_setups[cur_id] = cur_obj
        cur_obj = None

    with doc_path.open("r", encoding="utf-8", errors="ignore") as yaml_file:
        for raw_line in yaml_file:
            if raw_line.startswith("--- !u!"):
                _flush_cur()
                matched_hdr = header_regex.match(raw_line)
                in_ignored = False
                cur_prefab_instance_section = "none"
                cur_mod = None
                cur_curve_name = None
                cur_curve_time = None
                cur_marsh_list = None
                if not matched_hdr:
                    cur_cls = None
                    continue
                cur_cls = matched_hdr.group(1)
                cur_id = matched_hdr.group(2)
                cur_stripped = bool(matched_hdr.group(3))
                if cur_cls in ("1", "4", "114", "137", "1001"):
                    cur_obj = {"id": cur_id, "cls": cur_cls}
                    if cur_cls == "1001":
                        cur_obj["mods"] = []
                        cur_obj["removed_gos"] = []
                        cur_obj["removed_comps"] = []
                else:
                    cur_obj = None
                continue

            if cur_obj is None:
                continue

            stripped = raw_line.strip()
            if cur_cls == "1":
                if stripped.startswith("m_Name:"):
                    cur_obj["name"] = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("m_IsActive:"):
                    cur_obj["active"] = stripped.split(":", 1)[1].strip() != "0"
                elif stripped.startswith("m_TagString:"):
                    cur_obj["tag"] = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("m_PrefabInstance:"):
                    cur_obj["pi"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_CorrespondingSourceObject:"):
                    cur_obj["src"] = _parse_unity_yaml_ref(stripped)
            elif cur_cls == "4":
                if stripped.startswith("m_GameObject:"):
                    cur_obj["go"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_Father:"):
                    cur_obj["father"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_LocalPosition:"):
                    cur_obj["local_pos"] = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("m_PrefabInstance:"):
                    cur_obj["pi"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_CorrespondingSourceObject:"):
                    cur_obj["src"] = _parse_unity_yaml_ref(stripped)
            elif cur_cls == "137":
                if stripped.startswith("m_GameObject:"):
                    cur_obj["go"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_Enabled:"):
                    cur_obj["enabled"] = stripped.split(":", 1)[1].strip() != "0"
                elif stripped.startswith("m_Mesh:"):
                    cur_obj["mesh"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_PrefabInstance:"):
                    cur_obj["pi"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_CorrespondingSourceObject:"):
                    cur_obj["src"] = _parse_unity_yaml_ref(stripped)
            elif cur_cls == "1001":
                if stripped.startswith("m_TransformParent:"):
                    cur_prefab_instance_section = "none"
                    cur_obj["parent_tf"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_SourcePrefab:"):
                    cur_prefab_instance_section = "none"
                    cur_obj["source_prefab"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_Modifications:"):
                    cur_prefab_instance_section = "mods"
                    cur_mod = None
                elif stripped.startswith("m_RemovedGameObjects:"):
                    cur_prefab_instance_section = "removed_gos"
                    cur_mod = None
                elif stripped.startswith("m_RemovedComponents:"):
                    cur_prefab_instance_section = "removed_comps"
                    cur_mod = None
                elif stripped.startswith(("m_Removed", "m_Added")):
                    cur_prefab_instance_section = "none"
                    cur_mod = None
                elif cur_prefab_instance_section == "removed_gos":
                    if stripped.startswith("- ") and "fileID:" in stripped:
                        ref_item = _parse_unity_yaml_ref(stripped)
                        if ref_item:
                            cur_obj["removed_gos"].append(ref_item)
                    elif ":" in stripped and not stripped.startswith("-"):
                        cur_prefab_instance_section = "none"
                elif cur_prefab_instance_section == "removed_comps":
                    if stripped.startswith("- ") and "fileID:" in stripped:
                        ref_item = _parse_unity_yaml_ref(stripped)
                        if ref_item:
                            cur_obj["removed_comps"].append(ref_item)
                    elif ":" in stripped and not stripped.startswith("-"):
                        cur_prefab_instance_section = "none"
                elif cur_prefab_instance_section == "mods":
                    if stripped.startswith("- target:"):
                        cur_mod = {"target": _parse_unity_yaml_ref(stripped)}
                        cur_obj["mods"].append(cur_mod)
                    elif cur_mod is not None:
                        if stripped.startswith("propertyPath:"):
                            cur_mod["path"] = stripped.split(":", 1)[1].strip()
                        elif stripped.startswith("value:"):
                            cur_mod["value"] = stripped.split(":", 1)[1].strip()
                        elif stripped.startswith("objectReference:"):
                            cur_mod["objref"] = _parse_unity_yaml_ref(stripped)
            elif cur_cls == "114":
                if stripped.startswith("m_Script:"):
                    ref_val = _parse_unity_yaml_ref(stripped)
                    if (
                        ref_val
                        and ref_val[1] == VRCHAT_PHYSBONE_SCRIPT_GUID
                        and ref_val[0] == VRCHAT_PHYSBONE_CLASS_FILE_ID
                    ):
                        cur_obj["is_physbone"] = True
                elif stripped.startswith("m_GameObject:"):
                    cur_obj["go"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_Enabled:"):
                    cur_obj["enabled"] = stripped.split(":", 1)[1].strip() != "0"
                elif stripped.startswith("m_PrefabInstance:"):
                    cur_obj["pi"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_CorrespondingSourceObject:"):
                    cur_obj["src"] = _parse_unity_yaml_ref(stripped)
                elif cur_obj.get("is_physbone"):
                    if stripped.startswith("ignoreTransforms:"):
                        in_ignored = True
                        cur_obj["ignored"] = []
                        cur_curve_name = None
                    elif in_ignored:
                        if stripped.startswith("- {fileID:"):
                            cur_obj["ignored"].append(_parse_unity_yaml_ref(stripped))
                        elif ":" in stripped and not stripped.startswith("-"):
                            in_ignored = False
                    if stripped in ("radiusCurve:", "maxAngleXCurve:"):
                        cur_curve_name = stripped[:-1]
                        cur_curve_time = None
                        cur_obj.setdefault(cur_curve_name, [])
                    elif cur_curve_name is not None:
                        if stripped.startswith("time:"):
                            try:
                                cur_curve_time = float(stripped.split(":", 1)[1].strip())
                            except ValueError:
                                cur_curve_time = None
                        elif stripped.startswith("value:") and cur_curve_time is not None:
                            try:
                                cur_obj[cur_curve_name].append(
                                    (cur_curve_time, float(stripped.split(":", 1)[1].strip()))
                                )
                            except ValueError:
                                pass
                            cur_curve_time = None
                        elif (
                            ":" in stripped
                            and not stripped.startswith(("-", "serializedVersion:", "m_Curve:", "inSlope:", "outSlope:", "tangentMode:", "weightedMode:", "inWeight:", "outWeight:", "m_PreInfinity:", "m_PostInfinity:", "m_RotationOrder:"))
                        ):
                            cur_curve_name = None
                    if not in_ignored and cur_curve_name is None:
                        if stripped.startswith("rootTransform:"):
                            cur_obj["root_tf"] = _parse_unity_yaml_ref(stripped)
                        elif stripped.startswith("endpointPosition:"):
                            cur_obj["endpoint_position"] = _parse_yaml_scalar_vec3(raw_line, "endpointPosition", (0.0, 0.0, 0.0))
                        elif stripped.startswith("limitRotation:"):
                            cur_obj["limit_rotation"] = _parse_yaml_scalar_vec3(raw_line, "limitRotation", (0.0, 0.0, 0.0))
                        else:
                            for scalar_key, out_field in (
                                ("version:", "version"),
                                ("integrationType:", "integration_type"),
                                ("multiChildType:", "multi_child_type"),
                                ("pull:", "pull"),
                                ("spring:", "spring"),
                                ("stiffness:", "stiffness"),
                                ("gravity:", "gravity"),
                                ("gravityFalloff:", "gravity_falloff"),
                                ("immobileType:", "immobile_type"),
                                ("immobile:", "immobile"),
                                ("allowCollision:", "allow_collision"),
                                ("radius:", "radius"),
                                ("limitType:", "limit_type"),
                                ("maxAngleX:", "max_angle_x"),
                                ("maxAngleZ:", "max_angle_z"),
                                ("allowGrabbing:", "allow_grabbing"),
                                ("allowPosing:", "allow_posing"),
                                ("grabMovement:", "grab_movement"),
                                ("maxStretch:", "max_stretch"),
                                ("maxSquish:", "max_squish"),
                                ("stretchMotion:", "stretch_motion"),
                                ("isAnimated:", "is_animated"),
                            ):
                                if stripped.startswith(scalar_key):
                                    cur_obj[out_field] = stripped.split(":", 1)[1].strip()
                                    break
                else:
                    if stripped in ("_presets:", "_pbpresets:"):
                        cur_marsh_list = stripped[:-1]
                        cur_obj.setdefault(cur_marsh_list + "_list", [])
                    elif cur_marsh_list is not None:
                        if stripped.startswith("- {fileID:"):
                            ref_item = _parse_unity_yaml_ref(stripped)
                            cur_obj[cur_marsh_list + "_list"].append(ref_item)
                            continue
                        if ":" in stripped and not stripped.startswith("-"):
                            cur_marsh_list = None
                    if stripped.startswith("_marshmallowPBEnabled:"):
                        cur_obj["is_marshmallow"] = True
                        cur_obj[stripped.split(":", 1)[0]] = stripped.split(":", 1)[1].strip()
                    elif stripped.startswith(("_PhysBone_", "_index:", "_presets.Array.data", "_pbpresets.Array.data")):
                        key_tok, val_tok = stripped.split(":", 1)
                        cur_obj[key_tok] = val_tok.strip()
                        if "_PhysBone_Pull" in key_tok:
                            cur_obj["is_marshmallow"] = True

    _flush_cur()
    doc_result = {
        "path": doc_path,
        "gos": gameobjects,
        "tfs": transforms,
        "pbs": physbones,
        "marsh": marshmallow_setups,
        "smrs": skinned_meshes,
        "pis": prefab_instances,
    }
    if cache_key is not None:
        _STREAM_PHYSBONE_DOC_CACHE[cache_key] = doc_result
    return doc_result


def _parse_marshmallow_asset_file(asset_path: Path) -> Dict[str, Any]:
    """Read key-value fields from a Marshmallow PB `.asset` preset file."""
    if not asset_path.is_file():
        return {}
    data: Dict[str, Any] = {}
    for raw_line in asset_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped_line = raw_line.strip()
        for fld in (
            "path_breast_L",
            "path_breast_R",
            "_PhysBone_Pull",
            "_PhysBone_Momentum",
            "_PhysBone_Stiffness",
            "_PhysBone_Gravity",
            "_PhysBone_GravityFalloff",
            "_PhysBone_Immobile",
            "_PhysBone_Immobile_type",
            "_PhysBone_Stretch_Motion",
            "_PhysBone_Max_Stretch",
            "_PhysBone_Max_Squish",
            "limit_angle_0",
            "breast_collider_radius_0",
        ):
            if stripped_line.startswith(f"{fld}:"):
                data[fld] = stripped_line.split(":", 1)[1].strip()
                break
    return data


def _collect_marshmallow_pb_overrides(
    scene_doc: Dict[str, Any],
    visited_pis: Set[str],
    guid_map: Dict[str, Path],
    doc_cache: Dict[Path, Dict[str, Any]],
    unity_assets_root: Optional[Union[str, Path]] = None,
    is_transform_active_func: Optional[Callable[[str], bool]] = None,
) -> List[Dict[str, Any]]:
    """Extract active Marshmallow PB breast presets and overrides from PrefabInstances."""
    results: List[Dict[str, Any]] = []
    for prefab_instance_id in sorted(visited_pis, key=lambda val_str: int(val_str)):
        prefab_instance_info = scene_doc["pis"].get(prefab_instance_id)
        if not prefab_instance_info:
            continue
        ptf_ref = prefab_instance_info.get("parent_tf")
        ptf_id = ptf_ref[0] if ptf_ref else "0"
        if is_transform_active_func is not None and not is_transform_active_func(ptf_id):
            continue
        stripped_prefab_ref = prefab_instance_info.get("source_prefab")
        src_path = guid_map.get(stripped_prefab_ref[1]) if stripped_prefab_ref else None
        if not src_path or "marshmallow" not in src_path.name.lower() or not src_path.is_file():
            continue
        if src_path not in doc_cache:
            doc_cache[src_path] = _stream_parse_unity_physbone_doc(src_path)
        pref_doc = doc_cache[src_path]
        base_marsh = next(iter(pref_doc["marsh"].values()), {})
        merged: Dict[str, Any] = dict(base_marsh)
        preset_refs: Dict[str, Tuple[str, str]] = {}
        pbpreset_refs: Dict[str, Tuple[str, str]] = {}
        explicit_mods: Dict[str, Any] = {}
        root_active = True
        root_tag = "Untagged"

        for mod_item in prefab_instance_info.get("mods", []):
            prop_path = mod_item.get("path", "")
            val_str = mod_item.get("value", "")
            obj_ref = mod_item.get("objref")
            if prop_path == "m_IsActive":
                root_active = val_str != "0"
            elif prop_path == "m_TagString":
                root_tag = val_str
            elif prop_path in (
                "_index",
                "_marshmallowPBEnabled",
                "_PhysBone_index",
                "_PhysBone_Pull",
                "_PhysBone_Momentum",
                "_PhysBone_Stiffness",
                "_PhysBone_Gravity",
                "_PhysBone_GravityFalloff",
                "_PhysBone_Immobile",
                "_PhysBone_Immobile_type",
                "_PhysBone_Limit_Angle",
                "_PhysBone_Stretch_Motion",
                "_PhysBone_Max_Stretch",
                "_PhysBone_Max_Squish",
                "_PhysBone_AllowCollision",
                "_PhysBone_Collision_Radius",
            ):
                explicit_mods[prop_path] = val_str
            elif prop_path.startswith("_presets.Array.data["):
                idx_token = prop_path[len("_presets.Array.data[") :].rstrip("]")
                if obj_ref and obj_ref[1]:
                    preset_refs[idx_token] = obj_ref
            elif prop_path.startswith("_pbpresets.Array.data["):
                idx_token = prop_path[len("_pbpresets.Array.data[") :].rstrip("]")
                if obj_ref and obj_ref[1]:
                    pbpreset_refs[idx_token] = obj_ref

        if not root_active or root_tag == "EditorOnly":
            continue

        # Apply _pbpresets[_PhysBone_index] only when explicitly selected via _PhysBone_index
        pb_idx_str = str(explicit_mods.get("_PhysBone_index") or merged.get("_PhysBone_index", "")).strip()
        pbpreset_data: Dict[str, Any] = {}
        if "_PhysBone_index" in explicit_mods and pb_idx_str.isdigit():
            pb_idx_num = int(pb_idx_str)
            pb_ref = pbpreset_refs.get(pb_idx_str)
            if not pb_ref:
                pb_list = base_marsh.get("_pbpresets_list", [])
                if 0 <= pb_idx_num < len(pb_list):
                    pb_ref = pb_list[pb_idx_num]
            if pb_ref and pb_ref[1]:
                pb_path = guid_map.get(pb_ref[1])
                if pb_path:
                    pbpreset_data = _parse_marshmallow_asset_file(pb_path)

        merged.update(pbpreset_data)
        merged.update(explicit_mods)

        if str(merged.get("_marshmallowPBEnabled", "1")).strip() == "0":
            continue

        preset_idx = str(merged.get("_index", "")).strip()
        preset_data: Dict[str, Any] = {}
        if preset_idx in preset_refs:
            preset_path = guid_map.get(preset_refs[preset_idx][1])
            if preset_path:
                preset_data = _parse_marshmallow_asset_file(preset_path)
        elif preset_idx.isdigit():
            preset_list = base_marsh.get("_presets_list", [])
            preset_num = int(preset_idx)
            if 0 <= preset_num < len(preset_list) and preset_list[preset_num][1]:
                preset_path = guid_map.get(preset_list[preset_num][1])
                if preset_path:
                    preset_data = _parse_marshmallow_asset_file(preset_path)
        if not preset_data and unity_assets_root and preset_idx.isdigit():
            cand_asset = (
                Path(unity_assets_root)
                / "marshmallow_PB"
                / "Setup"
                / "Preset"
                / f"{int(preset_idx):02d}.asset"
            )
            if cand_asset.is_file():
                preset_data = _parse_marshmallow_asset_file(cand_asset)

        left_path = str(preset_data.get("path_breast_L") or "").strip()
        right_path = str(preset_data.get("path_breast_R") or "").strip()
        left_bone = left_path.rsplit("/", 1)[-1] if left_path else "Breast_1.L"
        right_bone = right_path.rsplit("/", 1)[-1] if right_path else "Breast_1.R"

        def _fval(field_key: str, default_num: float) -> float:
            try:
                return float(merged.get(field_key, default_num))
            except (TypeError, ValueError):
                return default_num

        def _ival(field_key: str, default_num: int) -> int:
            try:
                return int(float(merged.get(field_key, default_num)))
            except (TypeError, ValueError):
                return default_num

        raw_radius = _fval("_PhysBone_Collision_Radius", 0.06)
        if raw_radius > 0.5:
            # Slider scale in some Marshmallow presets is serialized in cm/percent (e.g. 4 -> 0.04 m)
            raw_radius = max(0.01, min(0.15, raw_radius * 0.01))

        lim_rot = _parse_yaml_scalar_vec3(
            f"_PhysBone_Limit_Rotation: {merged.get('_PhysBone_Limit_Rotation', '{x: -10, y: 0, z: 0}')}",
            "_PhysBone_Limit_Rotation",
            (-10.0, 0.0, 0.0),
        )
        shared_params = {
            "version": 1,
            "integration_type": 0,
            "multi_child_type": 0,
            "endpoint_position": (0.0, 0.08, 0.0),
            "pull": _fval("_PhysBone_Pull", 0.08),
            "spring": _fval("_PhysBone_Momentum", 0.5),
            "stiffness": _fval("_PhysBone_Stiffness", 0.25),
            "gravity": _fval("_PhysBone_Gravity", 0.25),
            "gravity_falloff": _fval("_PhysBone_GravityFalloff", 1.0),
            "immobile_type": _ival("_PhysBone_Immobile_type", 0),
            "immobile": _fval("_PhysBone_Immobile", 0.5),
            "allow_collision": _ival("_PhysBone_AllowCollision", 1),
            "radius": raw_radius,
            "radius_curve": [],
            "limit_type": 1,
            "max_angle_x": _fval("_PhysBone_Limit_Angle", 35.0),
            "max_angle_x_curve": [],
            "max_angle_z": 45.0,
            "limit_rotation": lim_rot,
            "allow_grabbing": 1,
            "allow_posing": 0,
            "grab_movement": 0.1,
            "max_stretch": _fval("_PhysBone_Max_Stretch", 0.3),
            "max_squish": _fval("_PhysBone_Max_Squish", 0.6),
            "stretch_motion": _fval("_PhysBone_Stretch_Motion", 0.5),
            "is_animated": 1,
            "from_marshmallow_pb": True,
        }
        for side_code, root_bone_name in (("L", left_bone), ("R", right_bone)):
            entry = dict(shared_params)
            entry["source_key"] = f"breast.{side_code}"
            entry["root_bone"] = root_bone_name
            entry["parent_bone"] = "SKEL_Spine2"
            entry["parent_bone_tag"] = SKEL_SPINE2_TAG
            results.append(entry)
    return results


def _collect_linear_spokes(
    root_transform_id: str,
    children_map: Dict[str, List[str]],
    name_func: Callable[[str], str],
    ignored_transform_ids: Set[str],
    allowed_bones_lower: Optional[Set[str]] = None,
) -> Tuple[List[List[str]], List[str]]:
    """
    Walk a Unity transform subtree from root_tf_id, returning:
      - list of linear spoke chains `[root_or_spoke, ..., leaf]`
      - flat list of all valid visited bone names in subtree
    """
    root_name = name_func(root_transform_id)
    all_desc: List[str] = [root_name]
    spokes: List[List[str]] = []

    def _walk(cur_transform: str, cur_path: List[str], depth_val: int) -> None:
        if depth_val > 16:
            spokes.append(cur_path)
            return
        raw_children = [
            child_transform
            for child_transform in children_map.get(cur_transform, [])
            if child_transform not in ignored_transform_ids
        ]
        # Filter out pure non-bone helpers when allowed_bones_ci is given (preserving at least direct path)
        valid_children = raw_children
        if allowed_bones_lower is not None:
            filtered = [
                child_transform
                for child_transform in raw_children
                if name_func(child_transform).strip().lower() in allowed_bones_lower
            ]
            if filtered:
                valid_children = filtered
        if not valid_children:
            spokes.append(cur_path)
            return
        for child_transform in valid_children:
            child_name = name_func(child_transform)
            all_desc.append(child_name)
            _walk(child_transform, cur_path + [child_name], depth_val + 1)

    _walk(root_transform_id, [root_name], 0)
    return spokes, all_desc
