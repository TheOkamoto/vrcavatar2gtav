#!/usr/bin/env python3
"""
modular_avatar_helper.py
========================
Layer 2 of 2 (Public Facade, Bake Plan Builder & Blender Execution).

Constructs complete NDMF bake plans (MergeArmature, BoneProxy, ScaleAdjuster,
ShapeChanger, BlendshapeSync, toggles/replacers), executes bone/mesh baking in
Blender, and re-exports all primitives from `modular_avatar_yaml_layer`.
"""

from __future__ import annotations

from collections import deque
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

COMMON_TOOLS_DIR = Path(__file__).resolve().parent
if str(COMMON_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_TOOLS_DIR))

import error_handler_helper as err_helper

try:
    import unity_scene_helper
except ImportError:
    unity_scene_helper = None

try:
    import unity_hair_helper
except ImportError:
    unity_hair_helper = None

import blendshape_unity_yaml_layer

try:
    from modular_avatar_yaml_layer import (
        COMMON_TOOLS_DIR,
    MA_MERGE_ARMATURE_GUID,
    MA_BONE_PROXY_GUID,
    MA_MESH_SETTINGS_GUID,
    MA_BLENDSHAPE_SYNC_GUID,
    MA_REPLACE_OBJECT_GUID,
    MA_OBJECT_TOGGLE_GUID,
    MA_SHAPE_CHANGER_GUID,
    MA_SCALE_ADJUSTER_GUID,
    MA_ACTIVATOR_GUID,
    VRC_PHYSBONE_GUID,
    HUMAN_BODY_BONES,
    _SKIP_SCAN_DIRS,
    _SKIP_GUID_DIRS,
    _decode_scalar,
    normalize_bone_match_key,
    infer_armature_prefix_suffix,
    resolve_ma_bone_mapping,
    _extract_inline_ref,
    _MA_PARSED_YAML_CACHE,
    parse_unity_yaml_with_ma,
    _MA_GUID_CACHE,
    _MA_GUID_SCAN_STATE,
    _is_builtin_unity_guid,
    _collect_guid_paths_for_ma,
    _is_game_object_active_in_doc,
    IDENTITY_UNITY_TRS,
    extract_transform_mod_overrides,
    extract_renderer_mod_overrides,
    resolve_overridden_renderer_mats,
    stamp_unity_mats_on_blender_objects,
    apply_unity_textures_to_blender_meshes,
    _read_fbx_meta_mesh_fids,
    compute_doc_unity_world_transforms,
    unity_trs_to_blender_matrix_rows,
    is_identity_mat4,
    compute_bone_unit_scale_correction,
    )
except ImportError:
    from common_tools.modular_avatar_yaml_layer import (
        COMMON_TOOLS_DIR,
    MA_MERGE_ARMATURE_GUID,
    MA_BONE_PROXY_GUID,
    MA_MESH_SETTINGS_GUID,
    MA_BLENDSHAPE_SYNC_GUID,
    MA_REPLACE_OBJECT_GUID,
    MA_OBJECT_TOGGLE_GUID,
    MA_SHAPE_CHANGER_GUID,
    MA_SCALE_ADJUSTER_GUID,
    MA_ACTIVATOR_GUID,
    VRC_PHYSBONE_GUID,
    HUMAN_BODY_BONES,
    _SKIP_SCAN_DIRS,
    _SKIP_GUID_DIRS,
    _decode_scalar,
    normalize_bone_match_key,
    infer_armature_prefix_suffix,
    resolve_ma_bone_mapping,
    _extract_inline_ref,
    _MA_PARSED_YAML_CACHE,
    parse_unity_yaml_with_ma,
    _MA_GUID_CACHE,
    _MA_GUID_SCAN_STATE,
    _is_builtin_unity_guid,
    _collect_guid_paths_for_ma,
    _is_game_object_active_in_doc,
    IDENTITY_UNITY_TRS,
    extract_transform_mod_overrides,
    extract_renderer_mod_overrides,
    resolve_overridden_renderer_mats,
    stamp_unity_mats_on_blender_objects,
    apply_unity_textures_to_blender_meshes,
    _read_fbx_meta_mesh_fids,
    compute_doc_unity_world_transforms,
    unity_trs_to_blender_matrix_rows,
    is_identity_mat4,
    compute_bone_unit_scale_correction,
    )


def build_modular_avatar_bake_plan(
    scene_or_prefab_path: Union[str, Path],
    avatar_name: Optional[str] = None,
    *,
    assets_root: Optional[Union[str, Path]] = None,
    character_hints: Sequence[str] = (),
    resolve_materials: bool = False,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> Dict[str, Any]:
    """
    Build a complete Modular Avatar (NDMF) bake plan for a selected avatar in a Unity
    scene or prefab, including all active dresses/accessories using MA components.
    """
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="ma_plan")
    src_path = Path(scene_or_prefab_path)
    empty_plan: Dict[str, Any] = {
        "loaded": False,
        "scene_path": str(src_path),
        "avatar_name": avatar_name or "",
        "armature_merges": [],
        "bone_proxies": [],
        "scale_adjusters": [],
        "blendshape_syncs": [],
        "shape_changer_weights": {},
        "object_toggles": {},
        "disabled_meshes": [],
        "extra_fbx_paths": [],
        "base_fbx_paths": [],
        "mesh_materials": {},
        "active_meshes": [],
        "active_meshes_by_fbx": {},
        "active_mat_guids": [],
        "outfit_roots": [],
    }
    if not src_path.is_file():
        return empty_plan

    resolved_assets: Optional[Path] = Path(assets_root) if assets_root else None
    if resolved_assets is None:
        for parent_dir in src_path.parents:
            if parent_dir.name.lower() == "assets":
                resolved_assets = parent_dir
                break

    root_doc = parse_unity_yaml_with_ma(src_path)
    gameobjects = root_doc["gameobjects"]
    transforms = root_doc["transforms"]
    game_object_to_transform = root_doc["go_to_tr"]
    prefab_instances = root_doc["prefab_instances"]

    # Locate target avatar root (Transform or root PrefabInstance)
    target_transform: Optional[str] = None
    target_prefab_instance: Optional[str] = None
    resolved_avatar_name = avatar_name or ""
    norm_target = (avatar_name or "").strip().lower()
    hint_tokens = [tok.strip().lower() for tok in character_hints if tok]

    best_score = -1
    for transform_file_id, transform_info in transforms.items():
        if transform_info.get("father_tr", "0") != "0" and norm_target:
            # Allow matching direct named transform even when nested
            pass
        game_object_info = gameobjects.get(transform_info.get("go_fid", ""), {})
        game_object_name = str(game_object_info.get("name", "") or "").strip()
        if not game_object_name:
            continue
        low_name = game_object_name.lower()
        score = -1
        if norm_target and low_name == norm_target:
            score = 100
        elif norm_target and norm_target in low_name:
            score = 60
        elif not norm_target and any(tok in low_name for tok in hint_tokens):
            score = 40
        elif not norm_target and transform_info.get("father_tr", "0") == "0":
            score = 15
        if score >= 0:
            active_bonus = 5 if game_object_info.get("active", True) else 0
            if score + active_bonus > best_score:
                best_score = score + active_bonus
                target_transform = transform_file_id
                target_prefab_instance = None
                resolved_avatar_name = game_object_name

    if target_transform is None:
        for prefab_instance_file_id, prefab_instance_info in prefab_instances.items():
            if prefab_instance_info.get("parent_tr", "0") != "0" and norm_target:
                continue
            prefab_instance_name = str(prefab_instance_info.get("name", "") or "").strip()
            low_name = prefab_instance_name.lower()
            score = -1
            if norm_target and low_name == norm_target:
                score = 95
            elif norm_target and norm_target in low_name:
                score = 55
            elif not norm_target and prefab_instance_name:
                score = 20
            if score > best_score:
                best_score = score
                target_prefab_instance = prefab_instance_file_id
                resolved_avatar_name = prefab_instance_name

    # Collect subtree transforms and path strings relative to avatar root
    subtree_trs: Set[str] = set()
    rel_path_by_game_object: Dict[str, str] = {}
    if target_transform is not None:
        bfs_queue = deque([(target_transform, "")])
        while bfs_queue:
            cur_transform, cur_rel = bfs_queue.popleft()
            if cur_transform in subtree_trs:
                continue
            subtree_trs.add(cur_transform)
            transform_info = transforms.get(cur_transform)
            if not transform_info:
                continue
            game_object_file_id = transform_info.get("go_fid", "")
            if game_object_file_id:
                rel_path_by_game_object[game_object_file_id] = cur_rel
            for child_transform in transform_info.get("children", []):
                child_game_object = transforms.get(child_transform, {}).get("go_fid", "")
                child_name = gameobjects.get(child_game_object, {}).get("name", "")
                next_rel = f"{cur_rel}/{child_name}".lstrip("/") if child_name else cur_rel
                bfs_queue.append((child_transform, next_rel))

    def _is_game_object_in_avatar_subtree(game_object_file_id: str) -> bool:
        if target_transform is None and target_prefab_instance is None:
            return False
        if src_path.suffix.lower() == ".prefab":
            return True
        if target_transform is not None:
            transform_id = game_object_to_transform.get(game_object_file_id)
            return transform_id in subtree_trs if transform_id else False
        return False

    # Collect active child PrefabInstances (dresses, hairs, accessories attached inside avatar)
    child_pis: List[Tuple[str, Dict[str, Any]]] = []
    if target_prefab_instance is not None and target_prefab_instance in prefab_instances:
        child_pis.append((target_prefab_instance, prefab_instances[target_prefab_instance]))
    else:
        for prefab_instance_file_id, prefab_instance_info in prefab_instances.items():
            if not prefab_instance_info.get("active", True):
                continue
            parent_transform = prefab_instance_info.get("parent_tr", "0")
            if src_path.suffix.lower() == ".prefab" or parent_transform in subtree_trs:
                child_pis.append((prefab_instance_file_id, prefab_instance_info))

    # Gather GUIDs for source prefabs, meshes, and materials
    needed_guids: Set[str] = set()
    for _prefab_instance_file_id, prefab_instance_info in child_pis:
        if prefab_instance_info.get("source_guid"):
            needed_guids.add(prefab_instance_info["source_guid"])
    for game_object_file_id, rend_info in root_doc["renderers"].items():
        if not _is_game_object_in_avatar_subtree(game_object_file_id):
            continue
        if rend_info.get("mesh_guid"):
            needed_guids.add(rend_info["mesh_guid"])
        needed_guids.update(rend_info.get("mat_guids", []))
    for game_object_file_id, mesh_guid in root_doc["mesh_filters"].items():
        if _is_game_object_in_avatar_subtree(game_object_file_id) and mesh_guid:
            needed_guids.add(mesh_guid)

    prefab_name_hints = [
        str(prefab_instance_info.get("name", "") or "")
        for _prefab_instance_file_id, prefab_instance_info in child_pis
        if prefab_instance_info.get("name")
    ]
    if resolved_avatar_name:
        prefab_name_hints.append(resolved_avatar_name)
    guid_map = _collect_guid_paths_for_ma(
        needed_guids,
        src_path,
        resolved_assets,
        name_hints=prefab_name_hints + list(character_hints),
        budget_sec=90.0,
        include_materials=bool(resolve_materials),
    )

    armature_merges: List[Dict[str, Any]] = []
    bone_proxies: List[Dict[str, Any]] = []
    scale_adjusters: List[Dict[str, Any]] = []
    blendshape_syncs: List[Dict[str, Any]] = []
    shape_changer_weights: Dict[str, Dict[str, float]] = {}
    shape_changer_deletes: List[Dict[str, Any]] = []
    object_toggles: Dict[str, bool] = {}
    disabled_meshes: Set[str] = set()
    explicit_disabled: Set[str] = set()
    extra_fbx_paths: List[str] = []
    base_fbx_paths: List[str] = []
    mesh_materials: Dict[str, List[Dict[str, Any]]] = {}
    active_meshes: List[str] = []
    active_meshes_by_fbx: Dict[str, List[str]] = {}
    active_mat_guids_set: Set[str] = set()
    fbx_meta_fids_cache: Dict[str, Dict[str, str]] = {}
    outfit_roots: List[str] = []
    seen_fbx_strs: Set[str] = set()
    base_bone_scales: Dict[str, List[float]] = {}
    fbx_instances: List[Dict[str, Any]] = []
    humanoid_anchor_keys: Dict[str, str] = {}
    for cand_names in HUMAN_BODY_BONES.values():
        if cand_names:
            canon_name = str(cand_names[0])
            for alias_name in cand_names:
                humanoid_anchor_keys[normalize_bone_match_key(alias_name)] = canon_name
    for extra_bone in ("Hips", "Spine", "Chest", "UpperChest", "Neck", "Head"):
        humanoid_anchor_keys.setdefault(normalize_bone_match_key(extra_bone), extra_bone)

    def _register_fbx_path(cand_path: Optional[Path], *, is_outfit: bool) -> None:
        if cand_path is None or not cand_path.is_file():
            return
        if cand_path.suffix.lower() not in (".fbx", ".dae", ".obj"):
            return
        path_str = str(cand_path)
        if path_str in seen_fbx_strs:
            return
        seen_fbx_strs.add(path_str)
        if is_outfit:
            extra_fbx_paths.append(path_str)
        else:
            base_fbx_paths.append(path_str)

    def _resolve_material_dicts(
        mat_guids: Sequence[str],
        anchor_file: Path,
        known_guids: Optional[Dict[str, Path]] = None,
    ) -> List[Dict[str, Any]]:
        mat_list: List[Dict[str, Any]] = []
        if not resolve_materials or unity_hair_helper is None:
            return mat_list
        clean_mats = [str(mat_id).lower() for mat_id in mat_guids if mat_id and not _is_builtin_unity_guid(mat_id)]
        if not clean_mats:
            return mat_list
        missing_mats = {
            mat_id
            for mat_id in clean_mats
            if (known_guids is None or mat_id not in known_guids) and mat_id not in guid_map
        }
        fallback_map: Dict[str, Path] = (
            _collect_guid_paths_for_ma(
                missing_mats,
                anchor_file,
                resolved_assets,
                budget_sec=90.0,
                include_materials=True,
            )
            if missing_mats
            else {}
        )
        for mat_guid in clean_mats:
            mat_path = (
                (known_guids.get(mat_guid) if known_guids else None)
                or guid_map.get(mat_guid)
                or fallback_map.get(mat_guid)
            )
            if mat_path and mat_path.is_file():
                try:
                    mat_info = unity_hair_helper.parse_unity_material(mat_path, resolved_assets)
                    mat_info["mat_path"] = str(mat_path)
                    mat_info["mat_guid"] = mat_guid
                    mat_list.append(mat_info)
                except Exception as exc:
                    active_logger.debug(f"Material parse skip {mat_path}: {exc}")
        return mat_list

    def _find_arm_root_and_host(
        doc_data: Dict[str, Any],
        doc_transform_map: Dict[str, Dict[str, Any]],
        rend_info: Dict[str, Any],
        renderer_game_object_file_id: str,
    ) -> Tuple[str, str, str]:
        """Resolve `(arm_root_tr, host_tr, attach_parent_bone)` for a renderer via its `m_RootBone`."""
        game_object_transform = doc_data.get("go_to_tr", {}).get(renderer_game_object_file_id, "0")
        root_bone_transform = str(rend_info.get("root_bone_tr", "0") or "0")
        arm_root_transform = ""
        if rend_info.get("class_id") == "137" and root_bone_transform in doc_transform_map:
            cur_transform = root_bone_transform
            raw_trs = doc_data.get("transforms", {})
            for _step in range(10):
                transform_entry = doc_transform_map.get(cur_transform)
                if transform_entry is None:
                    break
                name_low = str(transform_entry.get("name", "") or "").lower()
                parent_transform_id = str(transform_entry.get("father_tr", "0") or "0")
                if name_low.startswith(("armature", "li-ne_")):
                    arm_root_transform = cur_transform
                    break
                raw_rot = raw_trs.get(cur_transform, {}).get("rot", (0.0, 0.0, 0.0, 1.0))
                is_arm_rot = (
                    abs(abs(raw_rot[0]) - 0.7071) < 0.02
                    and abs(raw_rot[1]) < 0.02
                    and abs(raw_rot[2]) < 0.02
                    and abs(abs(raw_rot[3]) - 0.7071) < 0.02
                )
                if is_arm_rot and cur_transform != root_bone_transform and parent_transform_id != "0":
                    arm_root_transform = cur_transform
                    break
                if parent_transform_id == "0" or parent_transform_id not in doc_transform_map:
                    break
                cur_transform = parent_transform_id

        host_transform = (
            str(doc_transform_map[arm_root_transform].get("father_tr", "0") or "0")
            if arm_root_transform and arm_root_transform in doc_transform_map
            else game_object_transform
        )
        attach_bone = ""
        walk_transform = host_transform
        for _step in range(12):
            if walk_transform not in doc_transform_map:
                break
            walk_name = str(doc_transform_map[walk_transform].get("name", "") or "")
            norm_tok = normalize_bone_match_key(walk_name)
            if norm_tok in humanoid_anchor_keys:
                attach_bone = humanoid_anchor_keys[norm_tok]
                break
            walk_transform = str(doc_transform_map[walk_transform].get("father_tr", "0") or "0")
        return arm_root_transform, host_transform, attach_bone

    def _collect_arm_subtree_matrices(
        doc_data: Dict[str, Any],
        doc_transform_map: Dict[str, Dict[str, Any]],
        arm_root_transform: str,
        stop_sub_roots: Set[str],
    ) -> Dict[str, List[List[float]]]:
        """Collect Blender-space target bone 4x4 matrices under an FBX `Armature` transform."""
        if not arm_root_transform or arm_root_transform not in doc_transform_map:
            return {}
        children_by_father: Dict[str, List[str]] = {}
        for transform_key, transform_entry in doc_transform_map.items():
            children_by_father.setdefault(str(transform_entry.get("father_tr", "0") or "0"), []).append(transform_key)
        bone_mats: Dict[str, List[List[float]]] = {}
        bfs_nodes: deque = deque(children_by_father.get(arm_root_transform, ()))
        seen_trs: Set[str] = {arm_root_transform}
        while bfs_nodes:
            cur_transform = bfs_nodes.popleft()
            if cur_transform in seen_trs or cur_transform in stop_sub_roots:
                continue
            seen_trs.add(cur_transform)
            transform_entry = doc_transform_map.get(cur_transform)
            if transform_entry is None:
                continue
            game_object_name = str(transform_entry.get("name", "") or "").strip()
            if game_object_name and game_object_name not in bone_mats:
                bone_mats[game_object_name] = unity_trs_to_blender_matrix_rows(
                    transform_entry["world"], is_bone=True
                )
            for child_transform in children_by_father.get(cur_transform, ()):
                if child_transform not in seen_trs and child_transform not in stop_sub_roots:
                    bfs_nodes.append(child_transform)
        return bone_mats

    def _ingest_doc_ma_components(
        doc_data: Dict[str, Any],
        doc_path: Path,
        *,
        filter_subtree: bool,
        is_outfit_prefab: bool,
        root_override_name: str = "",
        base_world: Any = IDENTITY_UNITY_TRS,
        transform_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
        renderer_overrides: Optional[Dict[str, Any]] = None,
        collect_base_scales: bool = False,
        owner_tag: str = "",
    ) -> Dict[str, Dict[str, Any]]:
        doc_gos = doc_data["gameobjects"]
        doc_renderers = doc_data["renderers"]
        doc_filters = doc_data["mesh_filters"]
        doc_extra_guids: Set[str] = set()
        local_fbx_paths: List[str] = []
        local_mesh_names: List[str] = []
        active_renderer_entries: List[Tuple[str, Dict[str, Any], str]] = []
        doc_stop_transform = target_transform if filter_subtree else None
        doc_transform_map = compute_doc_unity_world_transforms(
            doc_data,
            root_transform=(target_transform if collect_base_scales else None),
            base_world=base_world,
            overrides_by_transform=transform_overrides,
            treat_root_as_avatar_origin=collect_base_scales,
        )
        if collect_base_scales:
            for transform_id, transform_entry in doc_transform_map.items():
                if filter_subtree and transform_id not in subtree_trs:
                    continue
                game_object_id = doc_data["transforms"].get(transform_id, {}).get("go_fid", "")
                if not game_object_id or game_object_id in doc_renderers:
                    continue
                transform_path = str(transform_entry.get("path", "") or "")
                path_parts = transform_path.split("/") if transform_path else []
                in_primary_arm = (
                    (len(path_parts) >= 3 and path_parts[1] == "Armature")
                    or (len(path_parts) >= 2 and path_parts[0] == "Armature")
                )
                if not in_primary_arm:
                    continue
                if not _is_game_object_active_in_doc(doc_data, game_object_id, stop_transform=doc_stop_transform):
                    continue
                scale_x_val, scale_y_val, scale_z_val = transform_entry.get("local_scale", (1.0, 1.0, 1.0))
                if (
                    abs(scale_x_val - 1.0) > 1e-4
                    or abs(scale_y_val - 1.0) > 1e-4
                    or abs(scale_z_val - 1.0) > 1e-4
                ):
                    scale_bone_name = str(transform_entry.get("name", "") or "").strip()
                    if scale_bone_name and scale_bone_name not in base_bone_scales:
                        base_bone_scales[scale_bone_name] = [scale_x_val, scale_y_val, scale_z_val]

        override_active_map = (renderer_overrides or {}).get("active") or {}
        override_enabled_map = (renderer_overrides or {}).get("enabled") or {}
        eff_rend_mats: Dict[str, List[str]] = {}
        for game_object_file_id, rend_info in doc_renderers.items():
            if filter_subtree and not _is_game_object_in_avatar_subtree(game_object_file_id):
                continue
            game_object_info = doc_gos.get(game_object_file_id, {})
            game_object_name = str(game_object_info.get("name", "") or "").strip()
            comp_fid = str(rend_info.get("comp_fid", "") or "")
            is_act = (
                _is_game_object_active_in_doc(doc_data, game_object_file_id, stop_transform=doc_stop_transform)
                and bool(rend_info.get("enabled", True))
                and override_active_map.get(game_object_file_id, True)
                and override_enabled_map.get(comp_fid, True)
            )
            if not is_act:
                if game_object_name:
                    disabled_meshes.add(game_object_name)
                continue
            if game_object_name:
                active_meshes.append(game_object_name)
                local_mesh_names.append(game_object_name)
            mguid = rend_info.get("mesh_guid", "") or doc_filters.get(game_object_file_id, "")
            if mguid:
                doc_extra_guids.add(mguid)
            full_mats = resolve_overridden_renderer_mats(rend_info, renderer_overrides)
            eff_rend_mats[game_object_file_id] = full_mats
            rend_mats = [
                mat_gid
                for mat_gid in full_mats
                if mat_gid and not _is_builtin_unity_guid(mat_gid)
            ]
            active_mat_guids_set.update(rend_mats)
            doc_extra_guids.update(rend_mats)
            active_renderer_entries.append((game_object_file_id, rend_info, game_object_name))

        mesh_hints = list(hint_tokens) + [resolved_avatar_name] + local_mesh_names
        resolved_doc_guids = _collect_guid_paths_for_ma(
            doc_extra_guids,
            doc_path,
            resolved_assets,
            name_hints=mesh_hints,
            budget_sec=90.0,
            include_materials=bool(resolve_materials),
        )
        doc_sub_arm_stops: Set[Tuple[str, str]] = set()
        rend_instance_metas: List[Tuple[str, Dict[str, Any], Path, List[str], str, str, str, List[Dict[str, Any]]]] = []
        for game_object_file_id, rend_info, game_object_name in active_renderer_entries:
            mguid = rend_info.get("mesh_guid", "") or doc_filters.get(game_object_file_id, "")
            mesh_asset = resolved_doc_guids.get(mguid) or guid_map.get(mguid)
            resolved_mesh_names: List[str] = [game_object_name] if game_object_name else []
            mat_dicts = _resolve_material_dicts(
                eff_rend_mats.get(game_object_file_id, rend_info.get("mat_guids", [])),
                doc_path,
                resolved_doc_guids,
            )
            if mesh_asset is not None and mesh_asset.suffix.lower() in (".fbx", ".dae", ".obj"):
                _register_fbx_path(mesh_asset, is_outfit=is_outfit_prefab)
                fbx_str = str(mesh_asset)
                if fbx_str not in local_fbx_paths:
                    local_fbx_paths.append(fbx_str)
                fbx_fids = fbx_meta_fids_cache.get(fbx_str)
                if fbx_fids is None:
                    fbx_fids = _read_fbx_meta_mesh_fids(mesh_asset)
                    fbx_meta_fids_cache[fbx_str] = fbx_fids
                mesh_fid = str(rend_info.get("mesh_fid", "") or "").strip()
                meta_mesh_name = fbx_fids.get(mesh_fid, "") if mesh_fid else ""
                if meta_mesh_name and meta_mesh_name not in resolved_mesh_names:
                    resolved_mesh_names.append(meta_mesh_name)
                    if meta_mesh_name not in active_meshes:
                        active_meshes.append(meta_mesh_name)
                    if meta_mesh_name not in local_mesh_names:
                        local_mesh_names.append(meta_mesh_name)
                fbx_bucket = active_meshes_by_fbx.setdefault(fbx_str, [])
                for item_name in resolved_mesh_names:
                    if item_name and item_name not in fbx_bucket:
                        fbx_bucket.append(item_name)
                arm_root_transform, host_transform, attach_bone = _find_arm_root_and_host(
                    doc_data, doc_transform_map, rend_info, game_object_file_id
                )
                if arm_root_transform:
                    doc_sub_arm_stops.add((arm_root_transform, host_transform))
                rend_instance_metas.append(
                    (game_object_file_id, rend_info, mesh_asset, resolved_mesh_names, arm_root_transform, host_transform, attach_bone, mat_dicts)
                )
            if mat_dicts:
                for item_name in resolved_mesh_names:
                    if item_name:
                        mesh_materials[item_name] = mat_dicts

        inst_buckets: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for game_object_file_id, rend_info, mesh_asset, rend_names, arm_root_transform, host_transform, attach_bone, instance_rend_mats in rend_instance_metas:
            is_skinned_flag = bool(rend_info.get("class_id") == "137")
            group_transform = arm_root_transform or host_transform or doc_data.get("go_to_tr", {}).get(game_object_file_id, "0")
            bucket_key = (str(mesh_asset), group_transform)
            if bucket_key not in inst_buckets:
                use_host_mat = bool(arm_root_transform) or (not is_skinned_flag)
                host_world = (
                    doc_transform_map[host_transform]["world"]
                    if host_transform in doc_transform_map
                    else base_world
                )
                other_stops: Set[str] = set()
                for sub_arm, sub_host in doc_sub_arm_stops:
                    if sub_arm == arm_root_transform:
                        continue
                    other_stops.add(sub_arm)
                    if sub_host and sub_host != host_transform and sub_host != arm_root_transform:
                        other_stops.add(sub_host)
                bone_mats = (
                    _collect_arm_subtree_matrices(doc_data, doc_transform_map, arm_root_transform, other_stops)
                    if arm_root_transform
                    else {}
                )
                inst_buckets[bucket_key] = {
                    "instance_id": f"{doc_path.stem}_{group_transform}",
                    "fbx_path": str(mesh_asset),
                    "mesh_names": [],
                    "mesh_materials": {},
                    "attach_parent_bone": attach_bone,
                    "is_skinned": is_skinned_flag,
                    "host_matrix_rows": (
                        unity_trs_to_blender_matrix_rows(host_world, is_bone=False)
                        if use_host_mat
                        else None
                    ),
                    "bone_matrices": bone_mats,
                }
            bucket_meshes = inst_buckets[bucket_key]["mesh_names"]
            bucket_mats = inst_buckets[bucket_key]["mesh_materials"]
            for mesh_name in rend_names:
                if mesh_name and mesh_name not in bucket_meshes:
                    bucket_meshes.append(mesh_name)
                if mesh_name and instance_rend_mats:
                    bucket_mats[mesh_name] = instance_rend_mats
        fbx_instances.extend(inst_buckets.values())

        for toggle_comp in doc_data["object_toggles"]:
            if filter_subtree and not _is_game_object_in_avatar_subtree(toggle_comp["go_fid"]):
                continue
            if not _is_game_object_active_in_doc(doc_data, toggle_comp["go_fid"], stop_transform=doc_stop_transform):
                continue
            menu_info = doc_data.get("menu_items", {}).get(toggle_comp["go_fid"])
            if menu_info and not menu_info.get("is_default", False):
                continue
            for item in toggle_comp["toggles"]:
                ref_path = item["reference_path"]
                object_toggles[ref_path] = bool(item["active"])
                if not item["active"] and ref_path:
                    tail_name = ref_path.rsplit("/", 1)[-1]
                    disabled_meshes.add(tail_name)
                    explicit_disabled.add(tail_name)

        for rep_comp in doc_data["replace_objects"]:
            if filter_subtree and not _is_game_object_in_avatar_subtree(rep_comp["go_fid"]):
                continue
            if not _is_game_object_active_in_doc(doc_data, rep_comp["go_fid"], stop_transform=doc_stop_transform):
                continue
            tgt_tail = str(rep_comp["target_path"]).rsplit("/", 1)[-1].strip()
            if tgt_tail:
                disabled_meshes.add(tgt_tail)
                explicit_disabled.add(tgt_tail)

        for shp_comp in doc_data["shape_changers"]:
            if filter_subtree and not _is_game_object_in_avatar_subtree(shp_comp["go_fid"]):
                continue
            if not _is_game_object_active_in_doc(doc_data, shp_comp["go_fid"], stop_transform=doc_stop_transform):
                continue
            if not doc_data.get("menu_items", {}).get(shp_comp["go_fid"], {}).get("is_default", True):
                continue
            for item in shp_comp["shapes"]:
                mesh_tail = str(item.get("reference_path", "") or "").rsplit("/", 1)[-1].strip() or "Body"
                if int(item.get("change_type", 1)) == 0:
                    shape_changer_deletes.append(
                        {
                            "mesh": mesh_tail,
                            "shape_name": item["shape_name"],
                            "threshold": float(item.get("threshold", 0.01)),
                        }
                    )
                else:
                    shape_changer_weights.setdefault(mesh_tail, {})[item["shape_name"]] = float(item["weight"])

        for sync_comp in doc_data["blendshape_syncs"]:
            if filter_subtree and not _is_game_object_in_avatar_subtree(sync_comp["go_fid"]):
                continue
            if not _is_game_object_active_in_doc(doc_data, sync_comp["go_fid"], stop_transform=doc_stop_transform):
                continue
            local_mesh = str(doc_gos.get(sync_comp["go_fid"], {}).get("name", "") or "").strip()
            for bnd in sync_comp["bindings"]:
                src_mesh_tail = bnd["reference_mesh_path"].rsplit("/", 1)[-1].strip() or "Body"
                blendshape_syncs.append(
                    {
                        "source_mesh": src_mesh_tail,
                        "source_shape": bnd["source_shape"],
                        "target_mesh": local_mesh,
                        "target_shape": bnd["local_shape"],
                        "remap_curve": list(bnd.get("remap_curve") or ()),
                    }
                )

        for scl_comp in doc_data["scale_adjusters"]:
            if filter_subtree and not _is_game_object_in_avatar_subtree(scl_comp["go_fid"]):
                continue
            if not _is_game_object_active_in_doc(doc_data, scl_comp["go_fid"], stop_transform=doc_stop_transform):
                continue
            bone_name = str(doc_gos.get(scl_comp["go_fid"], {}).get("name", "") or "").strip()
            if bone_name:
                scale_adjusters.append({"bone_name": bone_name, "scale_xyz": scl_comp["scale"]})

        for merge_comp in doc_data["merge_armatures"]:
            if not merge_comp.get("enabled", True):
                continue
            if filter_subtree and not _is_game_object_in_avatar_subtree(merge_comp["go_fid"]):
                continue
            if not _is_game_object_active_in_doc(doc_data, merge_comp["go_fid"], stop_transform=doc_stop_transform):
                continue
            src_name = root_override_name or str(doc_gos.get(merge_comp["go_fid"], {}).get("name", "") or "").strip()
            armature_merges.append(
                {
                    "source_go": src_name,
                    "merge_target_path": merge_comp["merge_target_path"],
                    "prefix": merge_comp["prefix"],
                    "suffix": merge_comp["suffix"],
                    "mangle_names": merge_comp["mangle_names"],
                    "fbx_paths": list(local_fbx_paths),
                    "mesh_names": list(local_mesh_names),
                    "_owner_tag": owner_tag,
                }
            )
            if root_override_name and root_override_name not in outfit_roots:
                outfit_roots.append(root_override_name)

        for proxy_comp in doc_data["bone_proxies"]:
            if not proxy_comp.get("enabled", True):
                continue
            if filter_subtree and not _is_game_object_in_avatar_subtree(proxy_comp["go_fid"]):
                continue
            if not _is_game_object_active_in_doc(doc_data, proxy_comp["go_fid"], stop_transform=doc_stop_transform):
                continue
            src_name = str(doc_gos.get(proxy_comp["go_fid"], {}).get("name", "") or "").strip()
            bone_ref_id = int(proxy_comp.get("bone_reference", -1))
            candidates = list(HUMAN_BODY_BONES.get(bone_ref_id, ()))
            sub_path = str(proxy_comp.get("sub_path", "") or "").strip()
            if sub_path:
                candidates.insert(0, sub_path.rsplit("/", 1)[-1])
            bone_proxies.append(
                {
                    "source_go": src_name or root_override_name,
                    "bone_reference": bone_ref_id,
                    "target_bone_candidates": candidates,
                    "sub_path": sub_path,
                    "attachment_mode": int(proxy_comp.get("attachment_mode", 1)),
                    "match_scale": bool(proxy_comp.get("match_scale", False)),
                    "fbx_paths": list(local_fbx_paths),
                    "mesh_names": list(local_mesh_names),
                    "_owner_tag": owner_tag,
                }
            )
        return doc_transform_map

    # 1. Process components directly inside the scene avatar hierarchy
    scene_transform_map = _ingest_doc_ma_components(
        root_doc,
        src_path,
        filter_subtree=(src_path.suffix.lower() != ".prefab"),
        is_outfit_prefab=False,
        collect_base_scales=True,
    )

    # 2. Recursively process active child PrefabInstances (e.g. MA dresses / coats / accessories)
    visited_prefabs: Set[Tuple[Path, str]] = set()
    prefab_queue: deque = deque()
    for prefab_instance_file_id, prefab_instance_info in child_pis:
        prefab_path = guid_map.get(prefab_instance_info.get("source_guid", ""))
        if prefab_path and prefab_path.is_file():
            parent_transform_id = str(prefab_instance_info.get("parent_tr", "0") or "0")
            par_world = (
                scene_transform_map[parent_transform_id]["world"]
                if parent_transform_id in scene_transform_map
                else IDENTITY_UNITY_TRS
            )
            raw_mods = list(prefab_instance_info.get("mods", ()))
            src_guid_str = str(prefab_instance_info.get("source_guid", "") or "")
            prefab_instance_overrides = extract_transform_mod_overrides(raw_mods, expected_guid=src_guid_str)
            prefab_instance_rend_overrides = extract_renderer_mod_overrides(raw_mods, expected_guid=src_guid_str)
            prefab_queue.append(
                (
                    prefab_path,
                    prefab_instance_info.get("name", "") or prefab_path.stem,
                    par_world,
                    prefab_instance_overrides,
                    prefab_instance_rend_overrides,
                    raw_mods,
                    f"scene_{prefab_instance_file_id}",
                )
            )

    outfit_keywords = (
        "dress", "cloth", "outfit", "maid", "coat", "skirt", "jacket", "costume", "wear", "kisekae", "shoe", "boot", "hat", "hair",
        "ribbon", "casquette", "megane", "glass", "ring", "earring", "pierce", "pin", "nail", "circle", "radio", "eeg", "watch", "bag",
        "necklace", "choker", "collar", "wing", "horn", "tail", "accessory", "prop",
    )
    while prefab_queue:
        cur_prefab, cur_label, cur_base_world, cur_overrides, cur_rend_overrides, cur_pool_mods, visit_tag = prefab_queue.popleft()
        resolved_pref = cur_prefab.resolve()
        visit_key = (resolved_pref, visit_tag)
        label_match = any(tok in cur_label.lower() or tok in cur_prefab.stem.lower() for tok in outfit_keywords)
        if visit_key in visited_prefabs:
            continue
        if resolved_pref.suffix.lower() in (".fbx", ".dae", ".obj"):
            visited_prefabs.add(visit_key)
            has_parent_attach = any(item.get("_owner_tag") and visit_tag.startswith(item["_owner_tag"]) for item in armature_merges + bone_proxies)
            model_payload = blendshape_unity_yaml_layer.collect_model_prefab_instance_payload(
                cur_prefab, cur_pool_mods, cur_prefab,
                lambda guids, anchor: _collect_guid_paths_for_ma(guids, anchor, resolved_assets, include_materials=bool(resolve_materials)),
                _resolve_material_dicts,
            )
            plan_state = {
                "active_meshes": active_meshes, "active_meshes_by_fbx": active_meshes_by_fbx,
                "mesh_materials": mesh_materials, "active_mat_guids_set": active_mat_guids_set,
                "explicit_disabled": explicit_disabled, "fbx_instances": fbx_instances,
                "attach_items": armature_merges + bone_proxies,
            }
            blendshape_unity_yaml_layer.register_model_prefab_instance_in_plan(
                cur_prefab, visit_tag, model_payload, unity_trs_to_blender_matrix_rows(cur_base_world, is_bone=False),
                bool(has_parent_attach or label_match), _register_fbx_path, plan_state,
            )
            continue
        if resolved_pref.suffix.lower() != ".prefab":
            continue
        visited_prefabs.add(visit_key)
        pref_doc = parse_unity_yaml_with_ma(cur_prefab)
        is_outfit = label_match or bool(pref_doc["merge_armatures"] or pref_doc["bone_proxies"])
        prefab_transform_map = _ingest_doc_ma_components(
            pref_doc, cur_prefab, filter_subtree=False, is_outfit_prefab=is_outfit, root_override_name=cur_label,
            base_world=cur_base_world, transform_overrides=cur_overrides, renderer_overrides=cur_rend_overrides, owner_tag=visit_tag,
        )
        nested_guids = {
            nested_prefab_instance.get("source_guid", "")
            for nested_prefab_instance in pref_doc["prefab_instances"].values()
            if nested_prefab_instance.get("active", True) and nested_prefab_instance.get("source_guid")
        }
        nested_resolved = _collect_guid_paths_for_ma(
            nested_guids, cur_prefab, resolved_assets, name_hints=list(hint_tokens) + [resolved_avatar_name, cur_label, cur_prefab.stem],
        )
        sibling_ref_mods = [
            mod_item
            for sibling_inst in pref_doc["prefab_instances"].values()
            if sibling_inst.get("active", True)
            for mod_item in sibling_inst.get("mods", ())
            if mod_item.get("property", "").endswith((".targetObject", ".referencePath"))
        ]
        for nested_fid, nested_prefab_instance in pref_doc["prefab_instances"].items():
            if not nested_prefab_instance.get("active", True):
                continue
            nested_path = nested_resolved.get(nested_prefab_instance.get("source_guid", ""))
            if nested_path and nested_path.is_file():
                nested_parent_transform = str(nested_prefab_instance.get("parent_tr", "0") or "0")
                nested_world = prefab_transform_map[nested_parent_transform]["world"] if nested_parent_transform in prefab_transform_map else cur_base_world
                nested_src_guid = str(nested_prefab_instance.get("source_guid", "") or "")
                nested_pool_mods = list(nested_prefab_instance.get("mods", ())) + list(cur_pool_mods) + sibling_ref_mods
                nested_overrides = extract_transform_mod_overrides(nested_pool_mods, expected_guid=nested_src_guid)
                nested_rend_overrides = extract_renderer_mod_overrides(nested_pool_mods, expected_guid=nested_src_guid)
                prefab_queue.append((
                    nested_path, nested_prefab_instance.get("name", "") or nested_path.stem, nested_world,
                    nested_overrides, nested_rend_overrides, nested_pool_mods, f"{visit_tag}_{nested_fid}",
                ))

    for attach_item in armature_merges + bone_proxies:
        attach_item.pop("_owner_tag", None)
    active_low = {name.lower() for name in active_meshes}
    disabled_meshes = explicit_disabled | {name for name in disabled_meshes if name.lower() not in active_low}
    return {
        "loaded": True,
        "scene_path": str(src_path),
        "avatar_name": resolved_avatar_name,
        "armature_merges": armature_merges,
        "bone_proxies": bone_proxies,
        "scale_adjusters": scale_adjusters,
        "base_bone_scales": base_bone_scales,
        "fbx_instances": fbx_instances,
        "blendshape_syncs": blendshape_syncs,
        "shape_changer_weights": shape_changer_weights,
        "shape_changer_deletes": shape_changer_deletes,
        "object_toggles": object_toggles,
        "disabled_meshes": sorted(disabled_meshes),
        "extra_fbx_paths": extra_fbx_paths,
        "base_fbx_paths": base_fbx_paths,
        "mesh_materials": mesh_materials,
        "active_meshes": active_meshes,
        "active_meshes_by_fbx": active_meshes_by_fbx,
        "active_mat_guids": sorted(active_mat_guids_set),
        "outfit_roots": outfit_roots,
    }


def _find_bone_in_armature(
    armature_obj: Any,
    candidates: Sequence[str],
) -> Optional[str]:
    """Return matching bone name inside a Blender Armature object using MA aliases."""
    bone_names = [bone.name for bone in armature_obj.data.bones]
    exact_set = set(bone_names)
    lower_map = {name.lower(): name for name in bone_names}
    norm_map = {normalize_bone_match_key(name): name for name in bone_names}

    for cand in candidates:
        if cand in exact_set:
            return cand
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
        norm_cand = normalize_bone_match_key(cand)
        if norm_cand in norm_map:
            return norm_map[norm_cand]
    return None


def _apply_unity_transform_deltas_to_outfit(
    outfit_arm_obj: Any,
    outfit_meshes: Sequence[Any],
    bone_map: Dict[str, str],
    base_arm_obj: Any,
    *,
    instance_spec: Optional[Dict[str, Any]] = None,
    pose_delta_inv: Optional[Dict[str, Any]] = None,
    existing_base_bones: Optional[Set[str]] = None,
    instance_tag: str = "inst",
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Transform imported outfit/hair armature bones & meshes into Unity Avatar-Local
    world pose (compensating any parent pose scale like `Neck=0.9`), and return
    `(delta_by_outfit_bone, custom_bone_renames)`.
    """
    delta_by_bone: Dict[str, Any] = {}
    custom_renames: Dict[str, str] = {}
    if not instance_spec:
        return delta_by_bone, custom_renames
    try:
        import bmesh
        import mathutils
    except ImportError:
        return delta_by_bone, custom_renames

    pose_inv_map = pose_delta_inv or {}
    base_names_set = existing_base_bones or {bone.name for bone in base_arm_obj.data.bones}
    bone_mats = instance_spec.get("bone_matrices") or {}
    host_rows = instance_spec.get("host_matrix_rows")
    attach_bone = str(instance_spec.get("attach_parent_bone", "") or "")
    ident_mat = mathutils.Matrix.Identity(4)

    bone_mats_lower = {str(key).lower(): val for key, val in bone_mats.items()}
    outfit_mat_world = outfit_arm_obj.matrix_world.copy()
    fbx_pts_map = {
        bone.name: tuple(float(axis_val) for axis_val in (outfit_mat_world @ bone.head_local))
        for bone in outfit_arm_obj.data.bones
    }
    arm_scale = outfit_mat_world.to_scale()
    fbx_col_norm = max(1e-6, (abs(float(arm_scale[0])) + abs(float(arm_scale[1])) + abs(float(arm_scale[2]))) / 3.0)
    unit_corr = compute_bone_unit_scale_correction(fbx_pts_map, bone_mats, fbx_col_norm=fbx_col_norm)

    def _find_anchor_pose_inv(bone_obj: Any) -> Any:
        cur_bone = bone_obj
        while cur_bone is not None:
            if cur_bone.name in bone_map:
                mapped_name = bone_map[cur_bone.name]
                if mapped_name in pose_inv_map:
                    return pose_inv_map[mapped_name]
                return ident_mat
            cur_bone = cur_bone.parent
        if attach_bone and attach_bone in pose_inv_map:
            return pose_inv_map[attach_bone]
        return ident_mat

    for bone in outfit_arm_obj.data.bones:
        parent_inv = _find_anchor_pose_inv(bone)
        raw_rows = bone_mats.get(bone.name) or bone_mats_lower.get(bone.name.lower())
        if raw_rows is not None:
            raw_mat = mathutils.Matrix(raw_rows)
            if abs(unit_corr - 1.0) > 1e-4:
                for row_idx in range(3):
                    for col_idx in range(3):
                        raw_mat[row_idx][col_idx] *= unit_corr
            tgt_mat = parent_inv @ raw_mat
            fbx_mat = outfit_mat_world @ bone.matrix_local
            try:
                delta_by_bone[bone.name] = tgt_mat @ fbx_mat.inverted()
            except ValueError:
                delta_by_bone[bone.name] = ident_mat
        elif bone.parent and bone.parent.name in delta_by_bone:
            delta_by_bone[bone.name] = delta_by_bone[bone.parent.name]
        elif host_rows is not None:
            delta_by_bone[bone.name] = parent_inv @ mathutils.Matrix(host_rows)

    host_fallback = ident_mat
    if host_rows is not None:
        host_parent_inv = pose_inv_map.get(attach_bone, ident_mat) if attach_bone else ident_mat
        host_fallback = host_parent_inv @ mathutils.Matrix(host_rows)
    elif delta_by_bone:
        host_fallback = next(iter(delta_by_bone.values()))

    # Only skip transformation when every computed delta matrix is close to Identity
    has_non_ident = any(not is_identity_mat4(mat_val) for mat_val in delta_by_bone.values())
    if not has_non_ident and is_identity_mat4(host_fallback):
        return {}, {}

    # Disambiguate unmapped custom bone names colliding with already-grafted bones
    used_names = set(base_names_set)
    for bone in outfit_arm_obj.data.bones:
        if bone.name in bone_map:
            continue
        if bone.name in used_names:
            cand_name = f"{bone.name}__{instance_tag}"
            suffix_idx = 2
            while cand_name in used_names:
                cand_name = f"{bone.name}__{instance_tag}_{suffix_idx}"
                suffix_idx += 1
            custom_renames[bone.name] = cand_name
            used_names.add(cand_name)
        else:
            used_names.add(bone.name)

    zero_mat = mathutils.Matrix(((0.0, 0.0, 0.0, 0.0),) * 4)
    for mesh_obj in outfit_meshes:
        if mesh_obj.type != "MESH":
            continue
        mesh_mat_world = mesh_obj.matrix_world.copy()
        mesh_mwi = mesh_mat_world.inverted()
        mesh_rot_world = mesh_mat_world.to_3x3()
        mesh_rot_world_inv = mesh_mwi.to_3x3()
        vgroup_names = [vgrp.name for vgrp in mesh_obj.vertex_groups]

        per_vert_mats: List[Any] = []
        for vtx in mesh_obj.data.vertices:
            acc_mat = zero_mat.copy()
            total_weight = 0.0
            for grp_elem in vtx.groups:
                if grp_elem.weight <= 0.0 or grp_elem.group >= len(vgroup_names):
                    continue
                vgroup_bone_name = vgroup_names[grp_elem.group]
                if vgroup_bone_name in delta_by_bone:
                    acc_mat += delta_by_bone[vgroup_bone_name] * grp_elem.weight
                    total_weight += grp_elem.weight
            mat_v = (acc_mat * (1.0 / total_weight)) if total_weight > 1e-6 else host_fallback
            per_vert_mats.append(mat_v)

        shape_keys_obj = getattr(mesh_obj.data, "shape_keys", None)
        key_blocks = list(shape_keys_obj.key_blocks) if shape_keys_obj else []
        if key_blocks:
            basis_blk = key_blocks[0]
            orig_basis_local = [basis_blk.data[idx].co.copy() for idx in range(len(mesh_obj.data.vertices))]
            new_basis_local: List[Any] = []
            for idx, orig_coord in enumerate(orig_basis_local):
                new_coord = mesh_mwi @ (per_vert_mats[idx] @ (mesh_mat_world @ orig_coord))
                new_basis_local.append(new_coord)
                basis_blk.data[idx].co = new_coord
                mesh_obj.data.vertices[idx].co = new_coord
            for key_block_item in key_blocks[1:]:
                for idx in range(len(orig_basis_local)):
                    disp_world = mesh_rot_world @ (key_block_item.data[idx].co - orig_basis_local[idx])
                    key_block_item.data[idx].co = new_basis_local[idx] + mesh_rot_world_inv @ (
                        per_vert_mats[idx].to_3x3() @ disp_world
                    )
        else:
            for idx, vtx in enumerate(mesh_obj.data.vertices):
                vtx.co = mesh_mwi @ (per_vert_mats[idx] @ (mesh_mat_world @ vtx.co))

        sample_det = host_fallback.to_3x3().determinant()
        if sample_det < 0.0:
            bmesh_flip = bmesh.new()
            bmesh_flip.from_mesh(mesh_obj.data)
            bmesh.ops.reverse_faces(bmesh_flip, faces=bmesh_flip.faces)
            bmesh_flip.normal_update()
            bmesh_flip.to_mesh(mesh_obj.data)
            bmesh_flip.free()
        mesh_obj.data.update()

        if custom_renames:
            for vgrp in mesh_obj.vertex_groups:
                if vgrp.name in custom_renames:
                    vgrp.name = custom_renames[vgrp.name]

    return delta_by_bone, custom_renames


def _bake_merge_armature_in_blender(
    bpy_mod: Any,
    base_arm_obj: Any,
    outfit_arm_obj: Any,
    outfit_meshes: Sequence[Any],
    *,
    prefix: str = "",
    suffix: str = "",
    instance_spec: Optional[Dict[str, Any]] = None,
    pose_delta_inv: Optional[Dict[str, Any]] = None,
    instance_tag: str = "inst",
) -> Dict[str, Any]:
    """
    Reproduce ModularAvatarMergeArmature natively in Blender:
      1. Apply Unity Transform/Prefab deltas onto outfit meshes, ShapeKeys & bones.
      2. Merge matching outfit bones onto base armature vertex groups.
      3. Graft outfit-only child bones (skirts, ribbons, sleeves, hair, earrings) into
         `base_arm_obj` parented under their mapped ancestor base bone.
      4. Rebind all outfit mesh Armature modifiers to `base_arm_obj` & clean helper arm.
    """
    if outfit_arm_obj is None or outfit_arm_obj == base_arm_obj:
        return {"merged_bones": 0, "grafted_bones": 0}

    base_bone_names = [bone.name for bone in base_arm_obj.data.bones]
    outfit_bone_names = [bone.name for bone in outfit_arm_obj.data.bones]
    bone_map = resolve_ma_bone_mapping(
        outfit_bone_names,
        base_bone_names,
        prefix=prefix,
        suffix=suffix,
    )

    delta_by_bone, custom_renames = _apply_unity_transform_deltas_to_outfit(
        outfit_arm_obj,
        outfit_meshes,
        bone_map,
        base_arm_obj,
        instance_spec=instance_spec,
        pose_delta_inv=pose_delta_inv,
        existing_base_bones=set(base_bone_names),
        instance_tag=instance_tag,
    )

    # Remap vertex groups on every outfit mesh BEFORE modifying armatures
    for mesh_obj in outfit_meshes:
        if mesh_obj.type != "MESH":
            continue
        remapped_groups: Dict[str, List[Tuple[int, float]]] = {}
        existing_vgroup_names = [vgroup.name for vgroup in mesh_obj.vertex_groups]
        for vgroup_name in existing_vgroup_names:
            target_bone = bone_map.get(vgroup_name)
            if not target_bone or target_bone == vgroup_name:
                continue
            src_vgroup = mesh_obj.vertex_groups.get(vgroup_name)
            if src_vgroup is None:
                continue
            src_idx = src_vgroup.index
            weights_for_target = remapped_groups.setdefault(target_bone, [])
            for vtx in mesh_obj.data.vertices:
                for grp_elem in vtx.groups:
                    if grp_elem.group == src_idx and grp_elem.weight > 0.0:
                        weights_for_target.append((vtx.index, grp_elem.weight))
            mesh_obj.vertex_groups.remove(src_vgroup)

        for target_bone, pairs in remapped_groups.items():
            dst_vgroup = mesh_obj.vertex_groups.get(target_bone)
            if dst_vgroup is None:
                dst_vgroup = mesh_obj.vertex_groups.new(name=target_bone)
            for vtx_idx, weight_val in pairs:
                dst_vgroup.add([vtx_idx], weight_val, "ADD")

    # Collect world-space rest geometry for unmapped custom outfit bones
    outfit_matrix = outfit_arm_obj.matrix_world.copy()
    base_inv_matrix = base_arm_obj.matrix_world.inverted()
    attach_parent_bone = str((instance_spec or {}).get("attach_parent_bone", "") or "")
    custom_bone_specs: List[Dict[str, Any]] = []
    for bone in outfit_arm_obj.data.bones:
        if bone.name in bone_map:
            continue
        parent_name = bone.parent.name if bone.parent else ""
        head_world = outfit_matrix @ bone.head_local
        tail_weight = outfit_matrix @ bone.tail_local
        bone_delta = delta_by_bone.get(bone.name)
        if bone_delta is not None:
            head_world = bone_delta @ head_world
            tail_weight = bone_delta @ tail_weight
        custom_bone_specs.append(
            {
                "name": custom_renames.get(bone.name, bone.name),
                "parent_src": parent_name,
                "head_world": head_world,
                "tail_world": tail_weight,
                "roll": bone.matrix_local.to_3x3().to_euler().y,
            }
        )

    # Graft custom outfit bones into base_arm_obj in parent-before-child topological order
    grafted_count = 0
    if custom_bone_specs:
        bpy_mod.ops.object.select_all(action="DESELECT")
        bpy_mod.context.view_layer.objects.active = base_arm_obj
        base_arm_obj.select_set(True)
        bpy_mod.ops.object.mode_set(mode="EDIT")
        try:
            edit_bones = base_arm_obj.data.edit_bones
            for spec in custom_bone_specs:
                bname = spec["name"]
                if bname in edit_bones:
                    continue
                new_edit_bone = edit_bones.new(bname)
                new_edit_bone.head = base_inv_matrix @ spec["head_world"]
                tail_local = base_inv_matrix @ spec["tail_world"]
                if (tail_local - new_edit_bone.head).length < 1e-4:
                    tail_local = new_edit_bone.head.copy()
                    tail_local.z += 0.05
                new_edit_bone.tail = tail_local
                new_edit_bone.roll = spec["roll"]
                grafted_count += 1

            for spec in custom_bone_specs:
                bname = spec["name"]
                edit_bone_cur = edit_bones.get(bname)
                if edit_bone_cur is None:
                    continue
                parent_src = spec["parent_src"]
                resolved_parent = custom_renames.get(parent_src) or bone_map.get(parent_src, parent_src)
                if resolved_parent in edit_bones:
                    edit_bone_cur.parent = edit_bones[resolved_parent]
                elif attach_parent_bone and attach_parent_bone in edit_bones:
                    edit_bone_cur.parent = edit_bones[attach_parent_bone]
                elif "Hips" in edit_bones:
                    edit_bone_cur.parent = edit_bones["Hips"]
        finally:
            bpy_mod.ops.object.mode_set(mode="OBJECT")

    # Point every outfit mesh's Armature modifier at base_arm_obj and reparent cleanly
    for mesh_obj in outfit_meshes:
        if mesh_obj.type != "MESH":
            continue
        mesh_world = mesh_obj.matrix_world.copy()
        mesh_obj.parent = base_arm_obj
        mesh_obj.matrix_world = mesh_world
        arm_mod = next((mod_item for mod_item in mesh_obj.modifiers if mod_item.type == "ARMATURE"), None)
        if arm_mod is None:
            arm_mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
        arm_mod.object = base_arm_obj

    try:
        bpy_mod.data.objects.remove(outfit_arm_obj, do_unlink=True)
    except Exception:
        pass

    return {"merged_bones": len(bone_map), "grafted_bones": grafted_count}


def apply_modular_avatar_plan_in_blender(
    bpy_mod: Any,
    base_arm_obj: Any,
    bake_plan: Dict[str, Any],
    *,
    import_extra_fbx: bool = True,
    primary_base_fbx: Optional[Union[str, Path]] = None,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> Dict[str, Any]:
    """
    Execute the complete Modular Avatar NDMF bake inside Blender:
      1. Apply ObjectToggles / disabled_meshes on base objects.
      2. Import extra outfit FBXs belonging to active MergeArmature / BoneProxy outfits.
      3. Apply ShapeChanger overrides and BlendshapeSync bindings.
      4. Bake MergeArmature & BoneProxy rigs onto `base_arm_obj` cleanly.
      5. Bind missing Unity/lilToon material textures onto imported outfit meshes.
      6. Apply ScaleAdjusters cleanly.
    """
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="ma_blender_bake")
    summary: Dict[str, Any] = {
        "imported_fbxs": [],
        "merged_armatures": 0,
        "grafted_bones": 0,
        "bound_proxies": 0,
        "synced_blendshapes": 0,
        "hidden_meshes": 0,
    }
    if not bake_plan or not bake_plan.get("loaded"):
        return summary

    # 1. Remove / hide disabled, replaced, or unreferenced meshes
    disabled_lower = {str(name).strip().lower() for name in bake_plan.get("disabled_meshes", ())}
    for obj_key, is_active in bake_plan.get("object_toggles", {}).items():
        if not is_active and obj_key:
            disabled_lower.add(str(obj_key).rsplit("/", 1)[-1].strip().lower())

    fbx_allow_map: Dict[str, Set[str]] = {}
    fbx_basename_buckets: Dict[str, List[Set[str]]] = {}
    for raw_fbx_key, val_list in (bake_plan.get("active_meshes_by_fbx") or {}).items():
        low_set = {str(item_name).strip().lower() for item_name in val_list if str(item_name).strip()}
        if not low_set:
            continue
        norm_fbx = str(raw_fbx_key).replace("\\", "/").strip().lower()
        fbx_allow_map[norm_fbx] = low_set
        base_name_key = norm_fbx.rsplit("/", 1)[-1]
        fbx_basename_buckets.setdefault(base_name_key, []).append(low_set)

    def _resolve_allowed_for_fbx(fbx_hint_str: Optional[str]) -> Set[str]:
        if not fbx_hint_str:
            return set()
        norm_key = str(fbx_hint_str).replace("\\", "/").strip().lower()
        if norm_key in fbx_allow_map:
            return fbx_allow_map[norm_key]
        base_key = norm_key.rsplit("/", 1)[-1]
        bucket = fbx_basename_buckets.get(base_key, [])
        if len(bucket) == 1:
            return bucket[0]
        return set()

    def _prune_mesh_list(
        mesh_list: List[Any],
        fbx_hint_str: Optional[str] = None,
        explicit_allowed: Optional[Sequence[str]] = None,
    ) -> None:
        surviving_objs: List[Any] = []
        for imp_obj in list(mesh_list):
            if imp_obj.type != "MESH":
                continue
            clean_low = re.sub(r"\.\d{3}$", "", imp_obj.name).strip().lower()
            if clean_low in disabled_lower:
                bpy_mod.data.objects.remove(imp_obj, do_unlink=True)
                if imp_obj in mesh_list:
                    mesh_list.remove(imp_obj)
                summary["hidden_meshes"] += 1
            else:
                surviving_objs.append(imp_obj)
        allowed_set = (
            {str(name).strip().lower() for name in explicit_allowed if name}
            if explicit_allowed
            else _resolve_allowed_for_fbx(fbx_hint_str)
        )
        if not allowed_set or not surviving_objs:
            return
        matched_objs: List[Any] = []
        for cand_obj in surviving_objs:
            clean_low = re.sub(r"\.\d{3}$", "", cand_obj.name).strip().lower()
            data_name = str(getattr(getattr(cand_obj, "data", None), "name", "") or "")
            data_low = re.sub(r"\.\d{3}$", "", data_name).strip().lower()
            if clean_low in allowed_set or (data_low and data_low in allowed_set):
                matched_objs.append(cand_obj)
        if not matched_objs:
            return
        for cand_obj in surviving_objs:
            if not any(cand_obj is kept_obj for kept_obj in matched_objs):
                bpy_mod.data.objects.remove(cand_obj, do_unlink=True)
                if cand_obj in mesh_list:
                    mesh_list.remove(cand_obj)
                summary["hidden_meshes"] += 1

    raw_base_paths = list(bake_plan.get("base_fbx_paths", ()))
    primary_hint_str = (
        str(primary_base_fbx)
        if primary_base_fbx is not None
        else (str(raw_base_paths[0]) if raw_base_paths else "")
    )
    base_children = [
        scene_obj
        for scene_obj in list(bpy_mod.data.objects)
        if scene_obj.type == "MESH" and scene_obj.parent == base_arm_obj
    ]
    _prune_mesh_list(base_children, primary_hint_str or None)

    # 1.5 Apply base scene non-unit bone scales & ScaleAdjusters before baking offsets
    pose_delta_inv: Dict[str, Any] = {}
    if getattr(base_arm_obj, "pose", None) is not None:
        base_scales_map = bake_plan.get("base_bone_scales") or {}
        for bone_key, scale_xyz in base_scales_map.items():
            bone_match = _find_bone_in_armature(base_arm_obj, [bone_key])
            if bone_match and bone_match in base_arm_obj.pose.bones:
                base_arm_obj.pose.bones[bone_match].scale = (
                    float(scale_xyz[0]),
                    float(scale_xyz[1]),
                    float(scale_xyz[2]),
                )
        for scl_item in bake_plan.get("scale_adjusters", ()):
            bone_match = _find_bone_in_armature(base_arm_obj, [scl_item["bone_name"]])
            if bone_match and bone_match in base_arm_obj.pose.bones:
                scale_x, scale_y, scale_z = scl_item["scale_xyz"]
                base_arm_obj.pose.bones[bone_match].scale = (scale_x, scale_y, scale_z)
        if hasattr(bpy_mod.context, "view_layer") and hasattr(bpy_mod.context.view_layer, "update"):
            bpy_mod.context.view_layer.update()
        try:
            armature_mat_world = base_arm_obj.matrix_world.copy()
            for bone_item in base_arm_obj.data.bones:
                pose_bone = base_arm_obj.pose.bones.get(bone_item.name)
                if pose_bone is None:
                    continue
                rest_world = armature_mat_world @ bone_item.matrix_local
                pose_world = armature_mat_world @ pose_bone.matrix
                pose_delta_inv[bone_item.name] = (pose_world @ rest_world.inverted()).inverted()
        except Exception:
            pose_delta_inv = {}

    # 2. Import missing extra outfit FBX files & track imported objects per instance
    imported_entries: List[Tuple[str, List[Any], Optional[Dict[str, Any]]]] = []
    if import_extra_fbx:
        if primary_base_fbx is not None:
            skip_paths = {str(Path(primary_base_fbx).resolve())}
        else:
            skip_paths = {str(Path(raw_base_paths[0]).resolve())} if raw_base_paths else set()
        covered_fbx_paths = set(skip_paths)

        for inst_idx, inst_spec in enumerate(bake_plan.get("fbx_instances", ())):
            fbx_file = Path(str(inst_spec.get("fbx_path", "") or ""))
            if not fbx_file.is_file():
                continue
            resolved_str = str(fbx_file.resolve())
            if resolved_str in skip_paths:
                stamp_unity_mats_on_blender_objects(list(bpy_mod.data.objects), inst_spec.get("mesh_materials"))
                continue
            covered_fbx_paths.add(resolved_str)
            before_names = {obj.name for obj in bpy_mod.data.objects}
            try:
                bpy_mod.ops.import_scene.fbx(
                    filepath=str(fbx_file),
                    use_anim=False,
                    automatic_bone_orientation=False,
                )
            except Exception as exc:
                active_logger.warning(f"Failed importing MA outfit FBX {fbx_file}: {exc}")
                continue
            newly_imported = [obj for obj in bpy_mod.data.objects if obj.name not in before_names]
            _prune_mesh_list(
                newly_imported,
                str(fbx_file),
                explicit_allowed=inst_spec.get("mesh_names") or None,
            )
            stamp_unity_mats_on_blender_objects(
                newly_imported, inst_spec.get("mesh_materials") or bake_plan.get("mesh_materials")
            )
            inst_payload = dict(inst_spec)
            inst_payload.setdefault("instance_tag", f"inst{inst_idx + 1}")
            imported_entries.append((str(fbx_file), newly_imported, inst_payload))
            if str(fbx_file) not in summary["imported_fbxs"]:
                summary["imported_fbxs"].append(str(fbx_file))

        seen_fallback_paths = set(covered_fbx_paths)
        for raw_fbx in (*raw_base_paths, *bake_plan.get("extra_fbx_paths", ())):
            fbx_file = Path(raw_fbx)
            if not fbx_file.is_file():
                continue
            resolved_str = str(fbx_file.resolve())
            if resolved_str in seen_fallback_paths:
                continue
            seen_fallback_paths.add(resolved_str)
            before_names = {obj.name for obj in bpy_mod.data.objects}
            try:
                bpy_mod.ops.import_scene.fbx(
                    filepath=str(fbx_file),
                    use_anim=False,
                    automatic_bone_orientation=False,
                )
            except Exception as exc:
                active_logger.warning(f"Failed importing MA outfit FBX {fbx_file}: {exc}")
                continue
            newly_imported = [obj for obj in bpy_mod.data.objects if obj.name not in before_names]
            _prune_mesh_list(newly_imported, str(fbx_file))
            imported_entries.append((str(fbx_file), newly_imported, None))
            summary["imported_fbxs"].append(str(fbx_file))

    # 3. Bake MergeArmature rigs onto base_arm_obj
    all_imported_meshes: List[Any] = []
    for _fbx_str, imp_list, inst_spec in imported_entries:
        arm_objs = [obj for obj in imp_list if obj.type == "ARMATURE"]
        mesh_objs = [obj for obj in imp_list if obj.type == "MESH"]
        all_imported_meshes.extend(mesh_objs)
        inst_tag = str((inst_spec or {}).get("instance_tag", "inst"))
        for outfit_arm in arm_objs:
            merge_meta = next(
                (
                    entry
                    for entry in bake_plan.get("armature_merges", ())
                    if any(obj.name.split(".")[0] in entry.get("mesh_names", ()) for obj in mesh_objs)
                    or outfit_arm.name.split(".")[0] in entry.get("source_go", "")
                ),
                {},
            )
            res = _bake_merge_armature_in_blender(
                bpy_mod,
                base_arm_obj,
                outfit_arm,
                mesh_objs,
                prefix=str(merge_meta.get("prefix", "")),
                suffix=str(merge_meta.get("suffix", "")),
                instance_spec=inst_spec,
                pose_delta_inv=pose_delta_inv,
                instance_tag=inst_tag,
            )
            summary["merged_armatures"] += 1
            summary["grafted_bones"] += res["grafted_bones"]
        if not arm_objs and mesh_objs and inst_spec and inst_spec.get("host_matrix_rows") and not inst_spec.get("is_skinned", True):
            attach_bone = _find_bone_in_armature(
                base_arm_obj, [str(inst_spec.get("attach_parent_bone", "") or ""), "Head", "Hips"]
            )
            try:
                import bmesh
                import mathutils
                host_mat = mathutils.Matrix(inst_spec["host_matrix_rows"])
                if attach_bone and attach_bone in pose_delta_inv:
                    host_mat = pose_delta_inv[attach_bone] @ host_mat
                if not is_identity_mat4(host_mat):
                    det_val = host_mat.to_3x3().determinant()
                    for mesh_obj in mesh_objs:
                        mesh_mat_world = mesh_obj.matrix_world.copy()
                        mesh_mwi = mesh_mat_world.inverted()
                        for vtx in mesh_obj.data.vertices:
                            vtx.co = mesh_mwi @ (host_mat @ (mesh_mat_world @ vtx.co))
                        if det_val < 0.0:
                            bmesh_flip = bmesh.new()
                            bmesh_flip.from_mesh(mesh_obj.data)
                            bmesh.ops.reverse_faces(bmesh_flip, faces=bmesh_flip.faces)
                            bmesh_flip.normal_update()
                            bmesh_flip.to_mesh(mesh_obj.data)
                            bmesh_flip.free()
                        mesh_obj.data.update()
            except ImportError:
                pass
            if attach_bone:
                for mesh_obj in mesh_objs:
                    if not mesh_obj.vertex_groups:
                        vgroup = mesh_obj.vertex_groups.new(name=attach_bone)
                        vtx_indices = [vtx.index for vtx in mesh_obj.data.vertices]
                        if vtx_indices:
                            vgroup.add(vtx_indices, 1.0, "REPLACE")
                        arm_mod = next((modifier_item for modifier_item in mesh_obj.modifiers if modifier_item.type == "ARMATURE"), None)
                        if arm_mod is None:
                            arm_mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
                        arm_mod.object = base_arm_obj
                        mesh_obj.parent = base_arm_obj
                        summary["bound_proxies"] += 1

    # 4. Bake BoneProxy attachments (rigid props / hair accessories / unskinned parts)
    for proxy_spec in bake_plan.get("bone_proxies", ()):
        target_bone_name = _find_bone_in_armature(
            base_arm_obj, proxy_spec.get("target_bone_candidates", ())
        )
        if not target_bone_name:
            continue
        target_mesh_names = {
            name.lower() for name in proxy_spec.get("mesh_names", ()) if name
        }
        source_game_object_lower = str(proxy_spec.get("source_go", "") or "").lower()
        for mesh_obj in all_imported_meshes:
            clean_low = re.sub(r"\.\d{3}$", "", mesh_obj.name).strip().lower()
            if clean_low not in target_mesh_names and source_game_object_lower not in clean_low:
                continue
            if not mesh_obj.vertex_groups:
                vgroup = mesh_obj.vertex_groups.new(name=target_bone_name)
                vtx_indices = [vtx.index for vtx in mesh_obj.data.vertices]
                if vtx_indices:
                    vgroup.add(vtx_indices, 1.0, "REPLACE")
                arm_mod = next((mod_item for mod_item in mesh_obj.modifiers if mod_item.type == "ARMATURE"), None)
                if arm_mod is None:
                    arm_mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
                arm_mod.object = base_arm_obj
                mesh_obj.parent = base_arm_obj
                summary["bound_proxies"] += 1

    # 5. Apply ShapeChanger weights & BlendshapeSync propagation across all meshes
    import blendshape_helper

    blendshape_helper.apply_ma_shape_changers_and_syncs(
        bpy_mod,
        bake_plan,
        allow_set=True,
        summary=summary,
    )

    # 6. Attach Unity material textures onto newly imported outfit meshes
    apply_unity_textures_to_blender_meshes(bpy_mod, all_imported_meshes, bake_plan.get("mesh_materials", {}))
    return summary
