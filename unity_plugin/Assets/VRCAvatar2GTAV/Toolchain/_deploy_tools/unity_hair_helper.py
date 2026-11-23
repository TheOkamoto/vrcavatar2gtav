#!/usr/bin/env python3
"""
unity_hair_helper.py
====================
Layer 2 of 2 (Public Facade & Prefab / Scene Hair Discovery).

Parses `.prefab`, `PrefabVariant`, `.fbx.meta` material maps, and `.unity`
scene hierarchies to resolve arbitrary VRChat custom hairs, and re-exports all
material baking, HSVG compositing, and manifest helpers from
`unity_hair_bake_layer`.
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import vrc2gtav_paths as project_paths

try:
    from unity_hair_bake_layer import (
        MA_MERGE_ARMATURE_GUID,
    MA_BONE_PROXY_GUID,
    MA_MESH_SETTINGS_GUID,
    MA_BLENDSHAPE_SYNC_GUID,
    VRC_PHYSBONE_GUID,
    CUSTOM_HAIR_MANIFEST_FILENAME,
    IMAGE_EXTENSIONS,
    SKIP_WALK_DIRS,
    _USED_MATERIAL_TEX_PROPS,
    _PRIMARY_MATERIAL_TEX_PROPS,
    HAIR_KEYWORD_TOKENS,
    _GUID_CACHE_BY_ROOT,
    _META_GUID_PATTERN,
    _FILE_ID_HEADER_PATTERN,
    _FLOAT_PATTERN,
    _VEC3_PATTERN,
    _VEC4_PATTERN,
    _COLOR_RGBA_PATTERN,
    _VEC2_XY_PATTERN,
    _normalize_guid,
    _extract_guid_from_meta_file,
    find_unity_assets_root,
    clear_guid_cache,
    _load_disk_guid_cache,
    _save_disk_guid_cache,
    _read_meta_guid_pair,
    _collect_meta_files_under_dir,
    _index_meta_tree,
    _scan_nearby_meta_files,
    resolve_unity_guid,
    _extract_ref_guid,
    parse_unity_material,
    make_synthetic_texture_material,
    _normalize_fbx_material_key,
    _linear_channel_to_srgb,
    _dilate_rgba_transparent_edges,
    _apply_uv_tile_transform,
    _apply_liltoon_hsvg,
    _dilate_black_uv_background_if_detected,
    composite_unity_material_textures,
    compute_quadrant_tile_entries,
    build_inmemory_manifest_fallback,
    pack_hair_materials_into_quadrant,
    save_custom_hair_manifest,
    load_custom_hair_manifest,
    resolve_tile_uv_for_mesh_slot,
    scan_custom_hair_candidates,
    )
except ImportError:
    from common_tools.unity_hair_bake_layer import (
        MA_MERGE_ARMATURE_GUID,
    MA_BONE_PROXY_GUID,
    MA_MESH_SETTINGS_GUID,
    MA_BLENDSHAPE_SYNC_GUID,
    VRC_PHYSBONE_GUID,
    CUSTOM_HAIR_MANIFEST_FILENAME,
    IMAGE_EXTENSIONS,
    SKIP_WALK_DIRS,
    _USED_MATERIAL_TEX_PROPS,
    _PRIMARY_MATERIAL_TEX_PROPS,
    HAIR_KEYWORD_TOKENS,
    _GUID_CACHE_BY_ROOT,
    _META_GUID_PATTERN,
    _FILE_ID_HEADER_PATTERN,
    _FLOAT_PATTERN,
    _VEC3_PATTERN,
    _VEC4_PATTERN,
    _COLOR_RGBA_PATTERN,
    _VEC2_XY_PATTERN,
    _normalize_guid,
    _extract_guid_from_meta_file,
    find_unity_assets_root,
    clear_guid_cache,
    _load_disk_guid_cache,
    _save_disk_guid_cache,
    _read_meta_guid_pair,
    _collect_meta_files_under_dir,
    _index_meta_tree,
    _scan_nearby_meta_files,
    resolve_unity_guid,
    _extract_ref_guid,
    parse_unity_material,
    make_synthetic_texture_material,
    _normalize_fbx_material_key,
    _linear_channel_to_srgb,
    _dilate_rgba_transparent_edges,
    _apply_uv_tile_transform,
    _apply_liltoon_hsvg,
    _dilate_black_uv_background_if_detected,
    composite_unity_material_textures,
    compute_quadrant_tile_entries,
    build_inmemory_manifest_fallback,
    pack_hair_materials_into_quadrant,
    save_custom_hair_manifest,
    load_custom_hair_manifest,
    resolve_tile_uv_for_mesh_slot,
    scan_custom_hair_candidates,
    )

def _parse_fbx_meta_external_materials(
    fbx_path: Path,
    unity_assets_root: Optional[Path] = None,
) -> Dict[str, Path]:
    """Read Unity ModelImporter externalObjects remaps from <model>.fbx.meta."""
    meta_path = Path(str(fbx_path) + ".meta")
    if not meta_path.is_file():
        return {}
    meta_text = meta_path.read_text(encoding="utf-8", errors="ignore")
    ext_section = re.search(
        r"externalObjects:(.*?)(?:^\s*materials:|\Z)",
        meta_text,
        re.DOTALL | re.MULTILINE,
    )
    if not ext_section:
        return {}
    mapped_materials: Dict[str, Path] = {}
    entry_pattern = re.compile(
        r"type:\s*UnityEngine:Material\s*\n"
        r"\s*assembly:\s*[^\n]+\n"
        r"\s*name:\s*([^\n]+)\s*\n"
        r"\s*second:\s*\{([^\}]*)\}",
        re.MULTILINE,
    )
    for ext_match in entry_pattern.finditer(ext_section.group(1)):
        raw_slot = ext_match.group(1).strip()
        if (raw_slot.startswith('"') and raw_slot.endswith('"')) or (
            raw_slot.startswith("'") and raw_slot.endswith("'")
        ):
            raw_slot = raw_slot[1:-1]
        if "\\u" in raw_slot:
            raw_slot = re.sub(
                r"\\u([0-9a-fA-F]{4})",
                lambda hex_match: chr(int(hex_match.group(1), 16)),
                raw_slot,
            )
        slot_name = raw_slot.strip()
        mat_guid = _extract_ref_guid(ext_match.group(2))
        if mat_guid:
            mat_path = resolve_unity_guid(mat_guid, fbx_path, unity_assets_root)
            if mat_path is not None and mat_path.is_file():
                mapped_materials[slot_name] = mat_path
    return mapped_materials


def _discover_nearby_materials_for_fbx(
    fbx_path: Path,
) -> Tuple[List[Path], List[Path]]:
    """Find candidate .mat files and diffuse textures near a raw .fbx hair file."""
    search_roots = [fbx_path.parent]
    if fbx_path.parent.parent.is_dir():
        search_roots.append(fbx_path.parent.parent)
    if fbx_path.parent.parent.parent.is_dir() and fbx_path.parent.parent.parent.name.lower() != "assets":
        search_roots.append(fbx_path.parent.parent.parent)

    mat_candidates: List[Path] = []
    tex_candidates: List[Path] = []
    seen_mats = set()
    seen_tex = set()
    for root_dir in search_roots:
        for sub_name in (
            "",
            "Materials",
            "Material",
            "_Mat",
            "Mat",
            "00Materials",
            "00mat",
            "00_material",
            "_Materials",
            "Textures",
            "Texture",
            "Tex",
            "_Tex",
        ):
            target_dir = root_dir / sub_name if sub_name else root_dir
            if not target_dir.is_dir():
                continue
            for item_path in sorted(target_dir.glob("*")):
                if not item_path.is_file():
                    continue
                lower_suffix = item_path.suffix.lower()
                if lower_suffix == ".mat" and str(item_path) not in seen_mats:
                    seen_mats.add(str(item_path))
                    mat_candidates.append(item_path)
                elif lower_suffix in IMAGE_EXTENSIONS and str(item_path) not in seen_tex:
                    lower_stem = item_path.stem.lower()
                    if any(skip_tok in lower_stem for skip_tok in ("normal", "_n", "_m", "_s", "mask", "ao")):
                        continue
                    seen_tex.add(str(item_path))
                    tex_candidates.append(item_path)
    return mat_candidates, tex_candidates


def _parse_unity_vec3(snippet: str, default_val: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Parse {x: ..., y: ..., z: ...} from a Unity YAML line."""
    vec_match = _VEC3_PATTERN.search(snippet)
    if not vec_match:
        return default_val
    return (float(vec_match.group(1)), float(vec_match.group(2)), float(vec_match.group(3)))


def _parse_unity_quat(snippet: str) -> Tuple[float, float, float, float]:
    """Parse {x: ..., y: ..., z: ..., w: ...} quaternion from Unity YAML."""
    quat_match = _VEC4_PATTERN.search(snippet)
    if not quat_match:
        return (0.0, 0.0, 0.0, 1.0)
    return (
        float(quat_match.group(1)),
        float(quat_match.group(2)),
        float(quat_match.group(3)),
        float(quat_match.group(4)),
    )


def _unity_pos_to_blender(unity_pos: Sequence[float]) -> Tuple[float, float, float]:
    """Convert Unity (+X right, +Y up, +Z forward) position to Blender (+X right, -Y forward, +Z up)."""
    return (float(unity_pos[0]), -float(unity_pos[2]), float(unity_pos[1]))


def _parse_yaml_blocks(yaml_path: Path) -> Dict[str, Any]:
    """Stream-parse Unity .prefab or .unity blocks relevant to hair hierarchy and materials."""
    game_objects: Dict[str, Dict[str, Any]] = {}
    transforms: Dict[str, Dict[str, Any]] = {}
    renderers: Dict[str, Dict[str, Any]] = {}
    mesh_filters: Dict[str, str] = {}
    prefab_instances: Dict[str, Dict[str, Any]] = {}
    ma_merge_armatures: List[Dict[str, Any]] = []
    ma_bone_proxies: List[Dict[str, Any]] = []
    vrcfury_links: List[Dict[str, Any]] = []

    current_class: Optional[str] = None
    current_fid: Optional[str] = None
    is_stripped = False
    block_lines: List[str] = []

    def _flush_block() -> None:
        if current_class is None or current_fid is None:
            return
        body = "\n".join(block_lines)
        if current_class == "1":
            name_m = re.search(r"^\s*m_Name:\s*(.*)$", body, re.MULTILINE)
            active_m = re.search(r"^\s*m_IsActive:\s*(\d+)", body, re.MULTILINE)
            tag_m = re.search(r"^\s*m_TagString:\s*(.*)$", body, re.MULTILINE)
            corr_m = re.search(r"m_CorrespondingSourceObject:\s*\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-f]{32}))?", body)
            pi_m = re.search(r"m_PrefabInstance:\s*\{fileID:\s*(-?\d+)", body)
            game_objects[current_fid] = {
                "name": name_m.group(1).strip() if name_m else "",
                "is_active": (int(active_m.group(1)) != 0) if active_m else True,
                "tag": tag_m.group(1).strip() if tag_m else "Untagged",
                "stripped": is_stripped,
                "corr_fid": corr_m.group(1) if corr_m else "0",
                "corr_guid": (corr_m.group(2) or "").lower() if corr_m else "",
                "prefab_instance": pi_m.group(1) if pi_m else "0",
            }
        elif current_class == "4":
            go_m = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", body)
            father_m = re.search(r"m_Father:\s*\{fileID:\s*(-?\d+)", body)
            pos_m = re.search(r"m_LocalPosition:\s*(\{[^\}]*\})", body)
            rot_m = re.search(r"m_LocalRotation:\s*(\{[^\}]*\})", body)
            sca_m = re.search(r"m_LocalScale:\s*(\{[^\}]*\})", body)
            corr_m = re.search(r"m_CorrespondingSourceObject:\s*\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-f]{32}))?", body)
            transforms[current_fid] = {
                "go_fid": go_m.group(1) if go_m else "0",
                "father_tr": father_m.group(1) if father_m else "0",
                "pos": _parse_unity_vec3(pos_m.group(1), (0.0, 0.0, 0.0)) if pos_m else (0.0, 0.0, 0.0),
                "rot": _parse_unity_quat(rot_m.group(1)) if rot_m else (0.0, 0.0, 0.0, 1.0),
                "scale": _parse_unity_vec3(sca_m.group(1), (1.0, 1.0, 1.0)) if sca_m else (1.0, 1.0, 1.0),
                "stripped": is_stripped,
                "corr_fid": corr_m.group(1) if corr_m else "0",
                "corr_guid": (corr_m.group(2) or "").lower() if corr_m else "",
            }
        elif current_class in ("137", "23"):
            go_m = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", body)
            enabled_m = re.search(r"^\s*m_Enabled:\s*(\d+)", body, re.MULTILINE)
            mesh_m = re.search(r"m_Mesh:\s*\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-f]{32}))?", body)
            root_bone_m = re.search(r"m_RootBone:\s*\{fileID:\s*(-?\d+)", body)
            mat_section = re.search(
                r"m_Materials:(.*?)(?=^\s{2}[a-zA-Z_][a-zA-Z0-9_]*:|\Z)",
                body,
                re.DOTALL | re.MULTILINE,
            )
            mat_guids = (
                re.findall(r"guid:\s*([0-9a-f]{32})", mat_section.group(1), re.IGNORECASE)
                if mat_section
                else []
            )
            bs_section = re.search(
                r"m_BlendShapeWeights:(.*?)(?:^\s*[a-zA-Z0-9_]+:|\Z)",
                body,
                re.DOTALL | re.MULTILINE,
            )
            bs_weights = (
                [float(num_str) / 100.0 for num_str in re.findall(rf"-\s*({_FLOAT_PATTERN})", bs_section.group(1))]
                if bs_section
                else []
            )
            if go_m:
                renderers[go_m.group(1)] = {
                    "component_fid": current_fid,
                    "class_id": current_class,
                    "enabled": (int(enabled_m.group(1)) != 0) if enabled_m else True,
                    "mesh_guid": (mesh_m.group(2) or "").lower() if mesh_m else "",
                    "root_bone_tr": root_bone_m.group(1) if root_bone_m else "0",
                    "mat_guids": [guid_str.lower() for guid_str in mat_guids],
                    "blendshape_weights": bs_weights,
                }
        elif current_class == "33":
            go_m = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", body)
            mesh_m = re.search(r"m_Mesh:\s*\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-f]{32}))?", body)
            if go_m and mesh_m and mesh_m.group(2):
                mesh_filters[go_m.group(1)] = mesh_m.group(2).lower()
        elif current_class == "1001":
            src_m = re.search(r"m_SourcePrefab:\s*\{fileID:\s*-?\d+,\s*guid:\s*([0-9a-f]{32})", body)
            parent_m = re.search(r"m_TransformParent:\s*\{fileID:\s*(-?\d+)", body)
            mods: List[Dict[str, str]] = []
            for mod_match in re.finditer(
                r"-\s*target:\s*\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-f]{32}))?[^\}]*\}[ \t]*\r?\n"
                r"[ \t]*propertyPath:[ \t]*([^\r\n]+)\r?\n"
                r"[ \t]*value:[ \t]*([^\r\n]*)\r?\n"
                r"[ \t]*objectReference:[ \t]*\{([^\}]*)\}",
                body,
            ):
                mods.append(
                    {
                        "target_fid": mod_match.group(1),
                        "target_guid": (mod_match.group(2) or "").lower(),
                        "property": mod_match.group(3).strip(),
                        "value": mod_match.group(4).strip(),
                        "ref_guid": _extract_ref_guid(mod_match.group(5)),
                        "ref_fid": (
                            re.search(r"fileID:\s*(-?\d+)", mod_match.group(5)).group(1)
                            if re.search(r"fileID:\s*(-?\d+)", mod_match.group(5))
                            else "0"
                        ),
                    }
                )
            prefab_instances[current_fid] = {
                "source_guid": src_m.group(1).lower() if src_m else "",
                "parent_tr": parent_m.group(1) if parent_m else "0",
                "mods": mods,
            }
        elif current_class == "114":
            script_m = re.search(r"m_Script:\s*\{[^\}]*guid:\s*([0-9a-f]{32})", body)
            script_guid = script_m.group(1).lower() if script_m else ""
            if script_guid == MA_MERGE_ARMATURE_GUID:
                go_m = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", body)
                ref_path_m = re.search(r"referencePath:\s*([^\n]*)", body)
                pref_m = re.search(r"prefix:\s*([^\n]*)", body)
                suff_m = re.search(r"suffix:\s*([^\n]*)", body)
                enabled_m = re.search(r"^\s*m_Enabled:\s*(\d+)", body, re.MULTILINE)
                ma_merge_armatures.append(
                    {
                        "go_fid": go_m.group(1) if go_m else "0",
                        "enabled": (int(enabled_m.group(1)) != 0) if enabled_m else True,
                        "merge_target_path": ref_path_m.group(1).strip() if ref_path_m else "",
                        "prefix": pref_m.group(1).strip() if pref_m else "",
                        "suffix": suff_m.group(1).strip() if suff_m else "",
                    }
                )
            elif script_guid == MA_BONE_PROXY_GUID:
                go_m = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", body)
                bone_ref_m = re.search(r"boneReference:\s*(-?\d+)", body)
                sub_path_m = re.search(r"subPath:\s*([^\n]*)", body)
                att_mode_m = re.search(r"attachmentMode:\s*(-?\d+)", body)
                ma_bone_proxies.append(
                    {
                        "go_fid": go_m.group(1) if go_m else "0",
                        "bone_reference": int(bone_ref_m.group(1)) if bone_ref_m else -1,
                        "sub_path": sub_path_m.group(1).strip() if sub_path_m else "",
                        "attachment_mode": int(att_mode_m.group(1)) if att_mode_m else 1,
                    }
                )
            elif "ArmatureLink" in body or "propBone:" in body:
                go_m = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", body)
                vrcfury_links.append(
                    {
                        "go_fid": go_m.group(1) if go_m else "0",
                    }
                )

    with open(yaml_path, "r", encoding="utf-8", errors="ignore") as yaml_stream:
        for raw_line in yaml_stream:
            if raw_line.startswith("--- !u!"):
                _flush_block()
                hdr_match = _FILE_ID_HEADER_PATTERN.match(raw_line[7:].strip())
                if hdr_match:
                    current_class = hdr_match.group(1)
                    current_fid = hdr_match.group(2)
                    is_stripped = bool(hdr_match.group(3))
                else:
                    current_class = None
                    current_fid = None
                    is_stripped = False
                block_lines = []
            elif current_class is not None:
                block_lines.append(raw_line.rstrip("\r\n"))
    _flush_block()

    go_to_tr = {
        tr_info["go_fid"]: tr_fid
        for tr_fid, tr_info in transforms.items()
        if tr_info.get("go_fid")
    }

    return {
        "game_objects": game_objects,
        "transforms": transforms,
        "go_to_tr": go_to_tr,
        "renderers": renderers,
        "mesh_filters": mesh_filters,
        "prefab_instances": prefab_instances,
        "ma_merge_armatures": ma_merge_armatures,
        "ma_bone_proxies": ma_bone_proxies,
        "vrcfury_links": vrcfury_links,
    }


def _find_transform_for_go(parsed_yaml: Dict[str, Any], go_fid: str) -> Optional[str]:
    """Return Transform fileID owning GameObject fileID."""
    go_to_tr = parsed_yaml.get("go_to_tr")
    if isinstance(go_to_tr, dict):
        return go_to_tr.get(go_fid)
    for tr_fid, tr_info in parsed_yaml["transforms"].items():
        if tr_info["go_fid"] == go_fid:
            return tr_fid
    return None


def _is_go_hierarchy_active(parsed_yaml: Dict[str, Any], go_fid: str) -> Tuple[bool, bool]:
    """Walk parent transforms upward to check (is_active_in_hierarchy, is_editor_only)."""
    go_info = parsed_yaml["game_objects"].get(go_fid)
    if go_info is None:
        return True, False
    is_editor_only = go_info.get("tag", "") == "EditorOnly"
    if not go_info.get("is_active", True):
        return False, is_editor_only

    cur_tr = _find_transform_for_go(parsed_yaml, go_fid)
    visited = set()
    while cur_tr and cur_tr not in visited:
        visited.add(cur_tr)
        tr_info = parsed_yaml["transforms"].get(cur_tr)
        if tr_info is None:
            break
        cur_go = parsed_yaml["game_objects"].get(tr_info["go_fid"])
        if cur_go is not None:
            if cur_go.get("tag", "") == "EditorOnly":
                is_editor_only = True
            if not cur_go.get("is_active", True):
                return False, is_editor_only
        parent_tr = tr_info["father_tr"]
        if parent_tr == "0":
            break
        cur_tr = parent_tr
    return True, is_editor_only


def _collect_variant_modifications(
    prefab_instances: Dict[str, Dict[str, Any]],
    fbx_or_prefab_cache: Dict[str, Any],
    prefab_path: Path,
    unity_assets_root: Optional[Path],
) -> Dict[str, Any]:
    """Extract material overrides, active toggles, transform mods, and blendshape mods from !u!1001."""
    variant_fbxs: List[Path] = []
    variant_slot_groups: List[List[str]] = []
    extra_mat_guids: List[str] = []
    root_pos = (0.0, 0.0, 0.0)
    root_rot = (0.0, 0.0, 0.0, 1.0)
    root_scale = (1.0, 1.0, 1.0)
    active_override_count_off = 0

    for pi_info in prefab_instances.values():
        src_guid = pi_info.get("source_guid", "")
        src_path = resolve_unity_guid(src_guid, prefab_path, unity_assets_root) if src_guid else None
        if src_path is not None and src_path.suffix.lower() == ".fbx":
            if src_path not in variant_fbxs:
                variant_fbxs.append(src_path)

        per_target_mats: Dict[str, Dict[int, str]] = {}
        inactive_target_fids = {
            mod_item["target_fid"]
            for mod_item in pi_info.get("mods", [])
            if mod_item["property"] == "m_IsActive" and mod_item["value"] == "0"
        }
        root_target_fid: Optional[str] = None
        for mod_item in pi_info.get("mods", []):
            prop_name = mod_item["property"]
            target_fid = mod_item["target_fid"]
            if prop_name == "m_LocalPosition.x" and root_target_fid is None:
                root_target_fid = target_fid

            mat_idx_match = re.match(r"m_Materials\.Array\.data\[(\d+)\]", prop_name)
            if mat_idx_match and mod_item["ref_guid"]:
                if target_fid in inactive_target_fids:
                    continue
                slot_idx = int(mat_idx_match.group(1))
                per_target_mats.setdefault(target_fid, {})[slot_idx] = mod_item["ref_guid"]
                if mod_item["ref_guid"] not in extra_mat_guids:
                    extra_mat_guids.append(mod_item["ref_guid"])
            elif prop_name == "m_IsActive" and mod_item["value"] == "0":
                active_override_count_off += 1
            elif target_fid == root_target_fid:
                if prop_name == "m_LocalPosition.x":
                    root_pos = (float(mod_item["value"]), root_pos[1], root_pos[2])
                elif prop_name == "m_LocalPosition.y":
                    root_pos = (root_pos[0], float(mod_item["value"]), root_pos[2])
                elif prop_name == "m_LocalPosition.z":
                    root_pos = (root_pos[0], root_pos[1], float(mod_item["value"]))
                elif prop_name == "m_LocalScale.x":
                    root_scale = (float(mod_item["value"]), root_scale[1], root_scale[2])
                elif prop_name == "m_LocalScale.y":
                    root_scale = (root_scale[0], float(mod_item["value"]), root_scale[2])
                elif prop_name == "m_LocalScale.z":
                    root_scale = (root_scale[0], root_scale[1], float(mod_item["value"]))

        for slot_dict in per_target_mats.values():
            ordered_slots = [slot_dict[slot_i] for slot_i in sorted(slot_dict)]
            if ordered_slots and ordered_slots not in variant_slot_groups:
                variant_slot_groups.append(ordered_slots)

    return {
        "variant_fbxs": variant_fbxs,
        "variant_slot_groups": variant_slot_groups,
        "extra_mat_guids": extra_mat_guids,
        "root_pos": root_pos,
        "root_rot": root_rot,
        "root_scale": root_scale,
        "active_override_count_off": active_override_count_off,
    }


def _extract_prefab_transform_hints(
    parsed_yaml: Dict[str, Any],
    prefab_path: Path,
) -> Dict[str, Any]:
    """Extract root transform, Head -> Hair_Root offset/scale, and Modular Avatar attachment hints."""
    transforms = parsed_yaml["transforms"]
    game_objects = parsed_yaml["game_objects"]
    tr_by_lower_name: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    root_tr_info: Optional[Dict[str, Any]] = None

    for tr_fid, tr_info in transforms.items():
        go_info = game_objects.get(tr_info["go_fid"], {})
        go_name = go_info.get("name", "")
        if tr_info["father_tr"] == "0" and root_tr_info is None:
            root_tr_info = tr_info
        if go_name:
            tr_by_lower_name[go_name.lower()] = (tr_fid, tr_info)

    head_entry = tr_by_lower_name.get("head")
    hair_root_entry = None
    for candidate_name in ("hair root", "hair_root", "hairroot", "lazy_hair_root", "hair"):
        if candidate_name in tr_by_lower_name:
            candidate_fid, candidate_tr = tr_by_lower_name[candidate_name]
            if head_entry is None or candidate_tr["father_tr"] == head_entry[0]:
                hair_root_entry = (candidate_fid, candidate_tr)
                break

    ma_merge = parsed_yaml["ma_merge_armatures"][0] if parsed_yaml["ma_merge_armatures"] else None
    ma_proxy = parsed_yaml["ma_bone_proxies"][0] if parsed_yaml["ma_bone_proxies"] else None

    return {
        "root_pos": list(root_tr_info["pos"]) if root_tr_info else [0.0, 0.0, 0.0],
        "root_rot": list(root_tr_info["rot"]) if root_tr_info else [0.0, 0.0, 0.0, 1.0],
        "root_scale": list(root_tr_info["scale"]) if root_tr_info else [1.0, 1.0, 1.0],
        "has_head_bone_in_prefab": head_entry is not None,
        "hair_root_local_scale": list(hair_root_entry[1]["scale"]) if hair_root_entry else [1.0, 1.0, 1.0],
        "hair_root_local_pos": list(hair_root_entry[1]["pos"]) if hair_root_entry else [0.0, 0.0, 0.0],
        "ma_merge_armature": ma_merge,
        "ma_bone_proxy": ma_proxy,
        "prefab_stem": prefab_path.stem,
    }


def _apply_variant_mods_to_parsed(
    parsed_yaml: Dict[str, Any],
    mods: Optional[List[Dict[str, str]]],
) -> List[Dict[str, str]]:
    """Apply PrefabVariant property modifications onto a parsed base prefab and return unmatched mods."""
    if not mods:
        return []
    game_objects = parsed_yaml["game_objects"]
    renderers = parsed_yaml["renderers"]
    renderer_by_comp = {
        rend_item["component_fid"]: rend_item
        for rend_item in renderers.values()
        if rend_item.get("component_fid")
    }
    unmatched_mods: List[Dict[str, str]] = []
    for mod_item in mods:
        prop_name = mod_item.get("property", "")
        target_fid = mod_item.get("target_fid", "")
        matched = False
        if prop_name == "m_IsActive" and target_fid in game_objects:
            game_objects[target_fid]["is_active"] = mod_item.get("value", "1") != "0"
            matched = True
        elif prop_name == "m_TagString" and target_fid in game_objects:
            game_objects[target_fid]["tag"] = mod_item.get("value", "")
            matched = True
        elif prop_name == "m_Enabled" and target_fid in renderer_by_comp:
            renderer_by_comp[target_fid]["enabled"] = mod_item.get("value", "1") != "0"
            matched = True
        else:
            mat_idx_match = re.match(r"m_Materials\.Array\.data\[(\d+)\]", prop_name)
            if mat_idx_match and mod_item.get("ref_guid") and target_fid in renderer_by_comp:
                slot_idx = int(mat_idx_match.group(1))
                mat_list = renderer_by_comp[target_fid].setdefault("mat_guids", [])
                while len(mat_list) <= slot_idx:
                    mat_list.append("")
                mat_list[slot_idx] = mod_item["ref_guid"]
                matched = True
        if not matched:
            unmatched_mods.append(mod_item)
    return unmatched_mods


def _resolve_prefab_hair_source(
    prefab_path: Path,
    unity_assets_root: Optional[Path],
    visited_prefabs: Optional[set] = None,
    incoming_mods: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Recursively resolve a Unity .prefab (including PrefabVariants) into FBXs and materials."""
    visited = visited_prefabs or set()
    resolved_prefab = prefab_path.resolve()
    if str(resolved_prefab) in visited:
        return {}
    visited.add(str(resolved_prefab))

    parsed = _parse_yaml_blocks(resolved_prefab)
    unmatched_mods = _apply_variant_mods_to_parsed(parsed, incoming_mods)
    game_objects = parsed["game_objects"]
    transforms = parsed["transforms"]

    fbx_sources: List[Path] = []
    active_meshes: List[str] = []
    inactive_meshes: List[str] = []
    editor_only_meshes: List[str] = []
    mesh_material_guids: Dict[str, List[str]] = {}
    mesh_root_bones: Dict[str, str] = {}
    blendshape_weights: Dict[str, Dict[str, float]] = {}
    all_mat_guids: List[str] = []

    for go_fid, rend_info in parsed["renderers"].items():
        go_info = game_objects.get(go_fid, {})
        mesh_name = go_info.get("name", "").strip()
        is_active, is_editor_only = _is_go_hierarchy_active(parsed, go_fid)
        if not rend_info.get("enabled", True):
            is_active = False

        if mesh_name:
            if is_editor_only:
                if mesh_name not in editor_only_meshes:
                    editor_only_meshes.append(mesh_name)
            elif not is_active:
                if mesh_name not in inactive_meshes:
                    inactive_meshes.append(mesh_name)
            else:
                if mesh_name not in active_meshes:
                    active_meshes.append(mesh_name)

        mesh_guid = rend_info.get("mesh_guid", "") or parsed.get("mesh_filters", {}).get(go_fid, "")
        if mesh_guid:
            mesh_fbx = resolve_unity_guid(mesh_guid, resolved_prefab, unity_assets_root)
            if mesh_fbx is not None and mesh_fbx.suffix.lower() == ".fbx" and mesh_fbx not in fbx_sources:
                fbx_sources.append(mesh_fbx)

        rb_tr = rend_info.get("root_bone_tr", "0")
        if rb_tr in transforms and mesh_name:
            rb_go = game_objects.get(transforms[rb_tr]["go_fid"], {})
            if rb_go.get("name"):
                mesh_root_bones[mesh_name.lower()] = rb_go["name"]

        mat_guids = rend_info.get("mat_guids", [])
        if is_active and not is_editor_only:
            if mesh_name and mat_guids:
                mesh_material_guids[mesh_name.lower()] = mat_guids
            for mat_guid in mat_guids:
                if mat_guid and mat_guid not in all_mat_guids:
                    all_mat_guids.append(mat_guid)

        if mesh_name and rend_info.get("blendshape_weights"):
            blendshape_weights[mesh_name] = {
                f"index:{bs_idx}": weight_val
                for bs_idx, weight_val in enumerate(rend_info["blendshape_weights"])
                if abs(weight_val) > 1e-4
            }

    variant_info = _collect_variant_modifications(
        parsed["prefab_instances"],
        {},
        resolved_prefab,
        unity_assets_root,
    )
    for var_fbx in variant_info["variant_fbxs"]:
        if var_fbx not in fbx_sources:
            fbx_sources.append(var_fbx)

    transform_hint = _extract_prefab_transform_hints(parsed, resolved_prefab)
    raw_variant_slot_groups: List[List[str]] = [
        list(group_item) for group_item in variant_info["variant_slot_groups"]
    ]

    # Also recurse into base prefabs if source_guid points to another .prefab
    for pi_info in parsed["prefab_instances"].values():
        src_guid = pi_info.get("source_guid", "")
        src_path = resolve_unity_guid(src_guid, resolved_prefab, unity_assets_root) if src_guid else None
        if src_path is not None and src_path.suffix.lower() == ".prefab":
            combined_mods = list(pi_info.get("mods", [])) + list(unmatched_mods)
            nested = _resolve_prefab_hair_source(
                src_path,
                unity_assets_root,
                visited,
                incoming_mods=combined_mods,
            )
            for nested_fbx_str in nested.get("all_fbxs", []):
                nested_fbx = Path(nested_fbx_str)
                if nested_fbx not in fbx_sources:
                    fbx_sources.append(nested_fbx)
            for nested_mat_guid in nested.get("all_mat_guids", []):
                if nested_mat_guid not in all_mat_guids:
                    all_mat_guids.append(nested_mat_guid)
            for key_name, val_slots in nested.get("mesh_material_guids", {}).items():
                mesh_material_guids.setdefault(key_name, val_slots)
            for nested_inactive in nested.get("inactive_meshes", []):
                if nested_inactive not in active_meshes and nested_inactive not in inactive_meshes:
                    inactive_meshes.append(nested_inactive)
            for nested_ed in nested.get("editor_only_meshes", []):
                if nested_ed not in editor_only_meshes:
                    editor_only_meshes.append(nested_ed)
            for mesh_key, bone_val in nested.get("mesh_root_bones", {}).items():
                mesh_root_bones.setdefault(mesh_key, bone_val)
            for mesh_key, bs_map in nested.get("blendshape_weights", {}).items():
                blendshape_weights.setdefault(mesh_key, bs_map)
            for nested_slot_group in nested.get("raw_variant_slot_groups", []):
                if nested_slot_group not in raw_variant_slot_groups:
                    raw_variant_slot_groups.append(nested_slot_group)
            nested_hint = nested.get("transform_hint", {})
            if nested_hint:
                if not transform_hint.get("ma_merge_armature") and nested_hint.get("ma_merge_armature"):
                    transform_hint["ma_merge_armature"] = nested_hint["ma_merge_armature"]
                if not transform_hint.get("ma_bone_proxy") and nested_hint.get("ma_bone_proxy"):
                    transform_hint["ma_bone_proxy"] = nested_hint["ma_bone_proxy"]
                if not transform_hint.get("has_head_bone_in_prefab") and nested_hint.get("has_head_bone_in_prefab"):
                    transform_hint["has_head_bone_in_prefab"] = True
                if transform_hint.get("root_scale") == [1.0, 1.0, 1.0] and nested_hint.get("root_scale"):
                    transform_hint["root_scale"] = nested_hint["root_scale"]
                if transform_hint.get("hair_root_local_scale") == [1.0, 1.0, 1.0] and nested_hint.get("hair_root_local_scale"):
                    transform_hint["hair_root_local_scale"] = nested_hint["hair_root_local_scale"]

    for mat_guid in variant_info["extra_mat_guids"]:
        if mat_guid not in all_mat_guids:
            all_mat_guids.append(mat_guid)

    # Heuristic gimmick suppression for known PrefabVariants that leave toggle gimmicks inactive
    if variant_info["active_override_count_off"] > 0 and variant_info["variant_fbxs"]:
        lower_prefab = resolved_prefab.name.lower()
        for gimmick_name in ("lazy_hair_hair_roller", "lazy_hair_post-it"):
            if gimmick_name not in inactive_meshes and "roller" not in lower_prefab:
                inactive_meshes.append(gimmick_name)

    parsed_materials: List[Dict[str, Any]] = []
    guid_to_material_id: Dict[str, str] = {}
    resolved_mat_paths_by_guid: Dict[str, Path] = {}
    unresolved_mat_guids: List[str] = []
    for mat_guid in all_mat_guids:
        local_mat_path = resolve_unity_guid(
            mat_guid,
            resolved_prefab,
            unity_assets_root,
            allow_full_scan=False,
        )
        if local_mat_path is not None:
            resolved_mat_paths_by_guid[mat_guid] = local_mat_path
        else:
            unresolved_mat_guids.append(mat_guid)

    # Only fall back to project-wide Assets scan if zero materials were resolved locally
    if not resolved_mat_paths_by_guid and unresolved_mat_guids:
        for mat_guid in unresolved_mat_guids:
            global_mat_path = resolve_unity_guid(
                mat_guid,
                resolved_prefab,
                unity_assets_root,
                allow_full_scan=True,
            )
            if global_mat_path is not None:
                resolved_mat_paths_by_guid[mat_guid] = global_mat_path

    for mat_guid in all_mat_guids:
        mat_path = resolved_mat_paths_by_guid.get(mat_guid)
        if mat_path is None or not mat_path.is_file() or mat_path.suffix.lower() != ".mat":
            continue
        parsed_mat = parse_unity_material(mat_path, unity_assets_root)
        # Skip gimmick materials only if no active mesh references them
        mat_lower = mat_path.name.lower()
        if any(tok in mat_lower for tok in ("hair_roller", "velcro")) or "post_it" in str(mat_path).lower():
            continue
        guid_to_material_id[mat_guid] = parsed_mat["material_id"]
        parsed_materials.append(parsed_mat)

    mesh_material_ids: Dict[str, List[str]] = {}
    for mesh_key, slot_guids in mesh_material_guids.items():
        mapped_ids = [guid_to_material_id[guid_str] for guid_str in slot_guids if guid_str in guid_to_material_id]
        if mapped_ids:
            mesh_material_ids[mesh_key] = mapped_ids

    variant_slot_id_groups: List[List[str]] = []
    for slot_guids in raw_variant_slot_groups:
        mapped_ids = [guid_to_material_id[guid_str] for guid_str in slot_guids if guid_str in guid_to_material_id]
        if mapped_ids and mapped_ids not in variant_slot_id_groups:
            variant_slot_id_groups.append(mapped_ids)

    return {
        "prefab_path": str(resolved_prefab),
        "all_fbxs": [str(fbx_item) for fbx_item in fbx_sources],
        "all_mat_guids": all_mat_guids,
        "inactive_meshes": inactive_meshes,
        "editor_only_meshes": editor_only_meshes,
        "mesh_root_bones": mesh_root_bones,
        "mesh_material_guids": mesh_material_guids,
        "mesh_material_ids": mesh_material_ids,
        "raw_variant_slot_groups": raw_variant_slot_groups,
        "variant_slot_groups": variant_slot_id_groups,
        "blendshape_weights": blendshape_weights,
        "transform_hint": transform_hint,
        "materials": parsed_materials,
    }


def _discover_scene_custom_hair(
    unity_scene_path: Path,
    unity_avatar_name: str,
    unity_assets_root: Optional[Path],
) -> Optional[Dict[str, Any]]:
    """Detect active custom hair PrefabInstance attached via Head or Modular Avatar in a .unity scene."""
    if not unity_scene_path.is_file():
        return None
    parsed = _parse_yaml_blocks(unity_scene_path)
    game_objects = parsed["game_objects"]
    transforms = parsed["transforms"]
    prefab_instances = parsed["prefab_instances"]

    # Locate avatar root transform
    avatar_root_tr: Optional[str] = None
    lower_avatar = unity_avatar_name.strip().lower()
    for tr_fid, tr_info in transforms.items():
        go_info = game_objects.get(tr_info["go_fid"], {})
        if tr_info["father_tr"] == "0" and go_info.get("name", "").strip().lower() == lower_avatar:
            avatar_root_tr = tr_fid
            break
    if avatar_root_tr is None:
        return None

    # Build subtree membership set
    children_map: Dict[str, List[str]] = {}
    for tr_fid, tr_info in transforms.items():
        children_map.setdefault(tr_info["father_tr"], []).append(tr_fid)
    subtree_trs = set()
    stack = [avatar_root_tr]
    while stack:
        cur_tr = stack.pop()
        if cur_tr in subtree_trs:
            continue
        subtree_trs.add(cur_tr)
        stack.extend(children_map.get(cur_tr, []))

    # Candidate active PrefabInstances inside the avatar's subtree whose name/source looks like hair
    ma_go_fids = {item["go_fid"] for item in parsed["ma_merge_armatures"] if item.get("enabled", True)}
    ma_go_fids.update(item["go_fid"] for item in parsed["ma_bone_proxies"])
    ma_go_fids.update(item["go_fid"] for item in parsed["vrcfury_links"])
    ma_pi_fids = {
        str(game_objects.get(go_fid, {}).get("prefab_instance", ""))
        for go_fid in ma_go_fids
    }
    ma_pi_fids.discard("")

    for pi_fid, pi_info in prefab_instances.items():
        if pi_info["parent_tr"] not in subtree_trs:
            continue
        src_guid = pi_info.get("source_guid", "")
        if not src_guid:
            continue
        pi_name = ""
        root_name_target = ""
        active_by_target: Dict[str, bool] = {}
        for mod_item in pi_info.get("mods", []):
            prop_key = mod_item.get("property", "")
            val_txt = mod_item.get("value", "")
            tgt_fid = mod_item.get("target_fid", "")
            tgt_guid = mod_item.get("target_guid", "").lower()
            if prop_key == "m_Name" and val_txt:
                is_src_match = bool(tgt_guid and tgt_guid == src_guid.lower())
                if not pi_name or (is_src_match and root_name_target == ""):
                    pi_name = val_txt
                    root_name_target = tgt_fid
            elif prop_key == "m_IsActive" and tgt_fid:
                if not tgt_guid or tgt_guid == src_guid.lower():
                    active_by_target[tgt_fid] = val_txt != "0"

        if root_name_target and root_name_target in active_by_target:
            pi_active = active_by_target[root_name_target]
        elif not root_name_target and "100000" in active_by_target:
            pi_active = active_by_target["100000"]
        else:
            pi_active = True
        if not pi_active:
            continue

        resolved_src = resolve_unity_guid(src_guid, unity_scene_path, unity_assets_root)
        candidate_label = f"{pi_name} {resolved_src.stem if resolved_src else ''}".lower()
        parent_tr_info = transforms.get(pi_info["parent_tr"], {})
        parent_go_name = game_objects.get(parent_tr_info.get("go_fid", ""), {}).get("name", "").lower()

        is_under_head = parent_go_name in ("head", "hair_root", "hair root", "hairroot")
        has_hair_keyword = any(tok in candidate_label for tok in HAIR_KEYWORD_TOKENS)
        has_ma_attachment = pi_fid in ma_pi_fids
        if resolved_src is not None and resolved_src.exists() and (is_under_head or (has_hair_keyword and (has_ma_attachment or is_under_head or pi_info["parent_tr"] == avatar_root_tr))):
            return {
                "source_path": resolved_src,
                "scene_pi_name": pi_name,
            }
    return None


def resolve_custom_hair_spec(
    hair_spec_input: Optional[Union[str, Path]] = None,
    unity_scene: Optional[Union[str, Path]] = None,
    unity_avatar_name: str = "",
    unity_assets_root: Optional[Union[str, Path]] = None,
    hair_mat_override: Optional[Union[str, Path]] = None,
    hair_tex_override: Optional[Union[str, Path]] = None,
    is_calibrated_er_default: bool = False,
) -> Dict[str, Any]:
    """
    Resolve any custom hair specification ('auto', 'default', 'none', or path to .prefab/.fbx)
    into a unified descriptor with FBXs, active/inactive filters, transform hints, and materials.
    """
    assets_root_path = (
        project_paths.to_host_path(unity_assets_root)
        if unity_assets_root
        else find_unity_assets_root()
    )
    raw_input = str(hair_spec_input).strip() if hair_spec_input is not None else ""
    normalized_token = raw_input.lower()

    if normalized_token in ("none", "bald", "no_hair"):
        return {
            "mode": "none",
            "is_neko_bob_calibrated": False,
            "source_input": raw_input,
            "prefab_path": "",
            "primary_fbx": "",
            "all_fbxs": [],
            "inactive_meshes": [],
            "editor_only_meshes": [],
            "mesh_root_bones": {},
            "mesh_material_ids": {},
            "variant_slot_groups": [],
            "blendshape_weights": {},
            "transform_hint": {},
            "materials": [],
        }

    if normalized_token == "default":
        return {
            "mode": "default",
            "is_neko_bob_calibrated": False,
            "source_input": raw_input,
            "prefab_path": "",
            "primary_fbx": "",
            "all_fbxs": [],
            "inactive_meshes": [],
            "editor_only_meshes": [],
            "mesh_root_bones": {},
            "mesh_material_ids": {},
            "variant_slot_groups": [],
            "blendshape_weights": {},
            "transform_hint": {},
            "materials": [],
        }

    resolved_target_path: Optional[Path] = None
    from_scene_discovery = False
    if normalized_token in ("", "auto"):
        if unity_scene and unity_avatar_name:
            scene_host_path = project_paths.to_host_path(unity_scene)
            scene_hit = _discover_scene_custom_hair(
                scene_host_path,
                unity_avatar_name,
                assets_root_path,
            )
            if scene_hit is not None:
                resolved_target_path = scene_hit["source_path"]
                from_scene_discovery = True
        if resolved_target_path is None:
            return {
                "mode": "default",
                "is_neko_bob_calibrated": False,
                "source_input": raw_input or "auto",
                "prefab_path": "",
                "primary_fbx": "",
                "all_fbxs": [],
                "inactive_meshes": [],
                "editor_only_meshes": [],
                "mesh_root_bones": {},
                "mesh_material_ids": {},
                "fbx_material_map": {},
                "variant_slot_groups": [],
                "blendshape_weights": {},
                "transform_hint": {},
                "materials": [],
            }
    else:
        resolved_target_path = project_paths.to_host_path(raw_input)
        if not resolved_target_path.exists():
            raise FileNotFoundError(f"Custom hair path not found: {resolved_target_path}")

    if assets_root_path is None:
        assets_root_path = find_unity_assets_root(resolved_target_path)

    suffix_lower = resolved_target_path.suffix.lower()
    if suffix_lower == ".prefab":
        prefab_data = _resolve_prefab_hair_source(resolved_target_path, assets_root_path)
        all_fbxs = prefab_data.get("all_fbxs", [])
        primary_fbx = all_fbxs[0] if all_fbxs else ""
        fbx_mat_map: Dict[str, str] = {}
        for fbx_entry in all_fbxs:
            ext_mats = _parse_fbx_meta_external_materials(Path(fbx_entry), assets_root_path)
            for raw_slot_key, mat_file in ext_mats.items():
                norm_key = _normalize_fbx_material_key(raw_slot_key)
                if norm_key and norm_key not in fbx_mat_map:
                    fbx_mat_map[norm_key] = mat_file.resolve().as_posix()
        spec = {
            "mode": "custom",
            "source_input": str(resolved_target_path),
            "prefab_path": str(resolved_target_path),
            "primary_fbx": primary_fbx,
            "all_fbxs": all_fbxs,
            "inactive_meshes": prefab_data.get("inactive_meshes", []),
            "editor_only_meshes": prefab_data.get("editor_only_meshes", []),
            "mesh_root_bones": prefab_data.get("mesh_root_bones", {}),
            "mesh_material_ids": prefab_data.get("mesh_material_ids", {}),
            "fbx_material_map": fbx_mat_map,
            "variant_slot_groups": prefab_data.get("variant_slot_groups", []),
            "blendshape_weights": prefab_data.get("blendshape_weights", {}),
            "transform_hint": prefab_data.get("transform_hint", {}),
            "materials": prefab_data.get("materials", []),
        }
    elif suffix_lower == ".fbx":
        ext_mats = _parse_fbx_meta_external_materials(resolved_target_path, assets_root_path)
        parsed_materials: List[Dict[str, Any]] = []
        mesh_mat_ids: Dict[str, List[str]] = {}
        fbx_mat_map = {}
        if ext_mats:
            for slot_name, mat_file in ext_mats.items():
                mat_info = parse_unity_material(mat_file, assets_root_path)
                parsed_materials.append(mat_info)
                norm_key = _normalize_fbx_material_key(slot_name)
                if norm_key:
                    mesh_mat_ids[norm_key] = [mat_info["material_id"]]
                    fbx_mat_map[norm_key] = str(mat_info["material_id"])
        else:
            nearby_mats, nearby_tex = _discover_nearby_materials_for_fbx(resolved_target_path)
            for mat_file in nearby_mats[:4]:
                parsed_materials.append(parse_unity_material(mat_file, assets_root_path))
            if not parsed_materials and nearby_tex:
                for tex_file in nearby_tex[:2]:
                    parsed_materials.append(make_synthetic_texture_material(tex_file, tex_file.stem))

        spec = {
            "mode": "custom",
            "source_input": str(resolved_target_path),
            "prefab_path": "",
            "primary_fbx": str(resolved_target_path),
            "all_fbxs": [str(resolved_target_path)],
            "inactive_meshes": [],
            "editor_only_meshes": [],
            "mesh_root_bones": {},
            "mesh_material_ids": mesh_mat_ids,
            "fbx_material_map": fbx_mat_map,
            "variant_slot_groups": [],
            "blendshape_weights": {},
            "transform_hint": {},
            "materials": parsed_materials,
        }
    else:
        raise ValueError(f"Unsupported custom hair file type '{resolved_target_path.suffix}'. Expected .prefab or .fbx.")

    # Apply explicit --hair-mat or --hair-tex override if supplied
    if hair_mat_override and str(hair_mat_override).strip():
        mat_override_path = project_paths.to_host_path(hair_mat_override)
        if not mat_override_path.is_file():
            raise FileNotFoundError(f"Custom hair material not found: {mat_override_path}")
        spec["materials"] = [parse_unity_material(mat_override_path, assets_root_path)]
        spec["mesh_material_ids"] = {}
        spec["fbx_material_map"] = {}
        spec["variant_slot_groups"] = []
    elif hair_tex_override and str(hair_tex_override).strip():
        tex_override_path = project_paths.to_host_path(hair_tex_override)
        if not tex_override_path.is_file():
            raise FileNotFoundError(f"Custom hair texture not found: {tex_override_path}")
        spec["materials"] = [make_synthetic_texture_material(tex_override_path, tex_override_path.stem)]
        spec["mesh_material_ids"] = {}
        spec["fbx_material_map"] = {}
        spec["variant_slot_groups"] = []

    is_neko_fbx = "neko tied bob hair" in str(spec.get("primary_fbx", "")).lower() or "neko bob" in str(spec.get("prefab_path", "")).lower()
    spec["is_neko_bob_calibrated"] = bool(
        is_neko_fbx
        and is_calibrated_er_default
        and not hair_mat_override
        and not hair_tex_override
        and not from_scene_discovery
        and not spec.get("prefab_path")
    )
    return spec

