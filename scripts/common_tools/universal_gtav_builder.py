#!/usr/bin/env python3
"""
universal_gtav_builder.py
=========================
Layer 2 of 2 (Blender Execution, RPF Packaging & CLI Entrypoint).

Compiles arbitrary VRChat / Unity avatars into GTA V `.ydd`, `.yft`, `.ytd`,
and `GTAVPhysBones.ini` across protagonists, `streamed` story/cutscene NPCs,
and `componentpeds` street pedestrians, while re-exporting all rigging/prep
helpers from `universal_gtav_rigging_layer`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))


try:
    from universal_gtav_rigging_layer import (
        _MODULE_DIR,
    _resolve_repo_root,
    _resolve_source_path,
    _select_scene_or_prefab,
    _select_main_fbx,
    _pick_default_face_anim,
    prepare_universal_npc_build,
    _find_humanoid_bone,
    _compute_target_yft_pose_metrics,
    _pose_avatar_arms_to_gtav_a_pose,
    _compute_universal_scale_and_offset,
    _strip_object_base_name,
    _resolve_universal_target_bone,
    _compute_soft_skirt_weights,
    _extract_case_insensitive_jaw_weights,
    _inspect_componentped_drawable_keys,
    conform_tight_torso_clothing_weights,
    )
except ImportError:
    from common_tools.universal_gtav_rigging_layer import (
        _MODULE_DIR,
    _resolve_repo_root,
    _resolve_source_path,
    _select_scene_or_prefab,
    _select_main_fbx,
    _pick_default_face_anim,
    prepare_universal_npc_build,
    _find_humanoid_bone,
    _compute_target_yft_pose_metrics,
    _pose_avatar_arms_to_gtav_a_pose,
    _compute_universal_scale_and_offset,
    _strip_object_base_name,
    _resolve_universal_target_bone,
    _compute_soft_skirt_weights,
    _extract_case_insensitive_jaw_weights,
    _inspect_componentped_drawable_keys,
    conform_tight_torso_clothing_weights,
    )

def map_blender_slots_to_unity_submeshes(
    poly_material_indices: Sequence[int],
    slot_count: int,
) -> Dict[int, int]:
    """
    Map Blender FBX material slot indices onto Unity Mesh submesh order.

    Unity's FBX importer orders `Mesh` submeshes and `m_Materials` entries by
    first-polygon encounter order, whereas Blender `io_scene_fbx` preserves
    FBX `Model->Material` link order.
    """
    first_poly_order: List[int] = []
    seen_slots = set()
    for poly_mat_idx in poly_material_indices:
        slot_val = int(poly_mat_idx)
        if 0 <= slot_val < slot_count and slot_val not in seen_slots:
            seen_slots.add(slot_val)
            first_poly_order.append(slot_val)
    for slot_val in range(max(0, int(slot_count))):
        if slot_val not in seen_slots:
            seen_slots.add(slot_val)
            first_poly_order.append(slot_val)
    return {
        blender_slot: unity_submesh_idx
        for unity_submesh_idx, blender_slot in enumerate(first_poly_order)
    }


def run_in_blender_build(manifest_path: Path) -> None:
    """Execute the full Sollumz `.ydd` / `.yft` / `GTAVPhysBones.ini` build inside Blender."""
    import addon_utils
    import bmesh
    import bpy
    import mathutils

    import blender_hair_helper
    import blendshape_helper
    import eye_blink_helper
    import hand_skeleton_helper
    import modular_avatar_helper
    import ped_damage_helper
    import physbone_helper
    import vrc2gtav_paths as project_paths

    addon_utils.enable("sollumz")
    from sollumz.sollumz_properties import SollumType
    from sollumz.tools.blenderhelper import create_empty_object
    from sollumz.tools.drawablehelper import (
        convert_obj_to_model,
        set_recommended_bone_properties,
    )
    from sollumz.ydr.shader_materials import create_shader

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ped_name = str(manifest["ped_name"])
    ped_format = str(manifest["ped_format"])
    skeleton_yft_path = project_paths.to_host_path(manifest["skeleton_yft"])
    atlas_manifest = json.loads(project_paths.to_host_path(manifest["atlas_manifest"]).read_text(encoding="utf-8"))
    ma_plan_path = project_paths.to_host_path(manifest["ma_plan_path"]) if manifest.get("ma_plan_path") else None
    ma_plan = (
        json.loads(ma_plan_path.read_text(encoding="utf-8"))
        if ma_plan_path and ma_plan_path.is_file()
        else {"loaded": False}
    )
    if isinstance(ma_plan, dict):
        for list_key in ("base_fbx_paths", "extra_fbx_paths"):
            if isinstance(ma_plan.get(list_key), list):
                ma_plan[list_key] = [str(project_paths.to_host_path(item)) for item in ma_plan[list_key]]
        for inst_item in ma_plan.get("fbx_instances", ()) or ():
            if isinstance(inst_item, dict) and inst_item.get("fbx_path"):
                inst_item["fbx_path"] = str(project_paths.to_host_path(inst_item["fbx_path"]))
        for item_key in ("scene_path", "assets_root"):
            if ma_plan.get(item_key):
                ma_plan[item_key] = str(project_paths.to_host_path(ma_plan[item_key]))

    def _clear_scene() -> None:
        for obj_item in list(bpy.data.objects):
            bpy.data.objects.remove(obj_item, do_unlink=True)
        for mesh_blk in list(bpy.data.meshes):
            bpy.data.meshes.remove(mesh_blk)
        for arm_blk in list(bpy.data.armatures):
            bpy.data.armatures.remove(arm_blk)
        for mat_blk in list(bpy.data.materials):
            bpy.data.materials.remove(mat_blk)

    _clear_scene()

    comp_all_keys: List[str] = []
    comp_primary_keys: List[str] = []
    if ped_format == "componentpeds" and manifest.get("vanilla_ped_ydd"):
        comp_all_keys, comp_primary_keys = _inspect_componentped_drawable_keys(
            project_paths.to_host_path(manifest["vanilla_ped_ydd"]),
            str(manifest.get("primary_component") or "uppr"),
        )

    # 1. Import target GTA V ped .yft skeleton
    bpy.ops.sollumz.import_assets(
        directory=str(skeleton_yft_path.parent) + os.sep,
        files=[{"name": skeleton_yft_path.name}],
    )
    ped_armature = (
        bpy.data.objects.get(skeleton_yft_path.stem)
        or bpy.data.objects.get(ped_name)
        or next((arm_cand for arm_cand in bpy.data.objects if arm_cand.type == "ARMATURE"), None)
    )
    if ped_armature is None:
        raise RuntimeError(f"Failed importing skeleton .yft: {skeleton_yft_path}")

    for temp_name in (f"{skeleton_yft_path.stem}.mesh", f"{ped_name}.mesh", "SKEL_ROOT"):
        temp_obj = bpy.data.objects.get(temp_name)
        if temp_obj is not None:
            bpy.data.objects.remove(temp_obj, do_unlink=True)

    yft_metrics = _compute_target_yft_pose_metrics(ped_armature)

    target_bones = {
        "SKEL_ROOT",
        "SKEL_Pelvis",
        "SKEL_Spine_Root",
        "SKEL_Spine0",
        "SKEL_Spine1",
        "SKEL_Spine2",
        "SKEL_Spine3",
        "SKEL_Neck_1",
        "SKEL_Head",
        "SKEL_L_Clavicle",
        "SKEL_L_UpperArm",
        "SKEL_L_Forearm",
        "SKEL_L_Hand",
        "SKEL_R_Clavicle",
        "SKEL_R_UpperArm",
        "SKEL_R_Forearm",
        "SKEL_R_Hand",
        "SKEL_L_Thigh",
        "SKEL_L_Calf",
        "SKEL_L_Foot",
        "SKEL_L_Toe0",
        "SKEL_R_Thigh",
        "SKEL_R_Calf",
        "SKEL_R_Foot",
        "SKEL_R_Toe0",
        "FACIAL_facialRoot",
    }
    jaw_bone_name = next(
        (
            cand_jaw
            for cand_jaw in ("FACIAL_jaw", "FACIAL_C_Jaw", "FB_Jaw_000")
            if cand_jaw in ped_armature.data.bones
        ),
        None,
    )
    if jaw_bone_name is not None:
        target_bones.add(jaw_bone_name)
    for side_code in ("L", "R"):
        for finger_idx in range(5):
            for seg_idx in range(3):
                target_bones.add(f"SKEL_{side_code}_Finger{finger_idx}{seg_idx}")
    target_bones.update(hand_skeleton_helper.EXTRA_ARM_HELPER_BONES)

    eye_blink_mode = str(manifest.get("eye_blink", "auto")).lower()
    eye_blink_strength = float(manifest.get("eye_blink_strength", 0.80))
    mouth_open_strength = eye_blink_helper.parse_mouth_open_strength(
        manifest.get("mouth_open_strength"),
        default=eye_blink_helper.DEFAULT_MOUTH_OPEN_STRENGTH,
    )
    blink_anchors = (
        eye_blink_helper.capture_eyelid_blink_anchors(ped_armature)
        if eye_blink_mode != "off"
        else {}
    )
    target_bones, stripped_leaves = eye_blink_helper.prepare_ydd_blink_bone_set(
        target_bones,
        enable_eye_blink=(eye_blink_mode != "off"),
        custom_bone_count=physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED,
    )
    if stripped_leaves > 0:
        print(f"[EyeBlink] Trimmed {stripped_leaves} unskinned hand leaf bones for <=128 bone limit", flush=True)

    bpy.context.view_layer.objects.active = ped_armature
    bpy.ops.object.mode_set(mode="EDIT")
    for edit_bone in list(ped_armature.data.edit_bones):
        if edit_bone.name not in target_bones:
            ped_armature.data.edit_bones.remove(edit_bone)
    bpy.ops.object.mode_set(mode="OBJECT")

    # 2. Import VRChat avatar FBX and bake Modular Avatar + blendshapes
    source_fbx = str(project_paths.to_host_path(manifest["source_fbx"]))
    before_objs = {obj_item.name for obj_item in bpy.data.objects}
    bpy.ops.import_scene.fbx(filepath=source_fbx)
    src_armature = next(
        (
            obj_item
            for obj_item in bpy.data.objects
            if obj_item.name not in before_objs and obj_item.type == "ARMATURE"
        ),
        None,
    )
    if src_armature is None:
        src_armature = next(
            (obj_item for obj_item in bpy.data.objects if obj_item.type == "ARMATURE" and obj_item != ped_armature),
            None,
        )
    if src_armature is None:
        raise RuntimeError(f"Could not find imported avatar armature in {source_fbx}")

    if ma_plan.get("loaded"):
        modular_avatar_helper.apply_modular_avatar_plan_in_blender(
            bpy,
            src_armature,
            ma_plan,
            import_extra_fbx=True,
            primary_base_fbx=source_fbx,
        )

    disabled_ci = {str(name).strip().lower() for name in (manifest.get("disabled_meshes") or ())}
    active_meshes: List[Any] = []
    for obj_item in bpy.data.objects:
        if obj_item.type != "MESH" or obj_item == ped_armature:
            continue
        clean_low = _strip_object_base_name(obj_item.name).lower()
        if clean_low in disabled_ci:
            continue
        active_meshes.append(obj_item)

    if not active_meshes:
        raise RuntimeError(f"No active meshes remained in {source_fbx}")

    blendshape_weights = dict(manifest.get("blendshape_weights") or {})
    if blendshape_weights:
        blendshape_helper.apply_blendshapes_to_blender_scene(bpy, blendshape_weights)

    _pose_avatar_arms_to_gtav_a_pose(
        bpy, mathutils, src_armature, target_drop_deg=float(yft_metrics["arm_drop_deg"])
    )
    scale_factor, z_offset = _compute_universal_scale_and_offset(
        bpy, src_armature, active_meshes, yft_metrics
    )
    print(
        f"[Scale] Computed scale={scale_factor:.4f}, z_offset={z_offset:.4f} "
        f"(ground={yft_metrics['ground_z']:.4f}, head={yft_metrics['head_z']:.4f}, arm={yft_metrics['arm_drop_deg']:.1f}deg)",
        flush=True,
    )

    body_obj = next(
        (obj_item for obj_item in active_meshes if _strip_object_base_name(obj_item.name).lower() == "body"),
        active_meshes[0],
    )
    body_jaw_mask = _extract_case_insensitive_jaw_weights(body_obj)
    body_jaw_weights = (
        body_jaw_mask
        if abs(mouth_open_strength - eye_blink_helper.DEFAULT_MOUTH_OPEN_STRENGTH) < 1e-6
        else _extract_case_insensitive_jaw_weights(
            body_obj, mouth_open_strength=mouth_open_strength
        )
    )

    blink_candidates = [
        obj_item
        for obj_item in active_meshes
        if _strip_object_base_name(obj_item.name).lower() in ("body", "face", "head", "body_base")
    ]
    seen_blink_names = {item.name for item in blink_candidates}
    for obj_item in active_meshes:
        if obj_item.name not in seen_blink_names:
            blink_candidates.append(obj_item)
            seen_blink_names.add(obj_item.name)

    blink_body_obj = body_obj
    blink_rig_data: Dict[str, Any] = {"enabled": False, "reason": "no_candidates"}
    for cand_idx, cand_obj in enumerate(blink_candidates):
        cand_jaw = body_jaw_mask if cand_obj == body_obj else _extract_case_insensitive_jaw_weights(cand_obj)
        cand_weights = (
            blendshape_weights.get(cand_obj.name)
            or blendshape_weights.get(_strip_object_base_name(cand_obj.name))
            or blendshape_weights.get("Body", {})
        )
        cand_res = eye_blink_helper.extract_body_eyelid_blink_rig_data(
            bpy,
            cand_obj,
            eye_blink_mode=eye_blink_mode,
            shape_weights=cand_weights,
            exclude_vert_indices=cand_jaw.keys(),
        )
        if cand_idx == 0:
            blink_rig_data = cand_res
        if cand_res.get("enabled"):
            blink_body_obj = cand_obj
            blink_rig_data = cand_res
            print(
                f"[EyeBlink] Extracted eyelid rig from '{cand_obj.name}' (key={cand_res.get('shape_key')})",
                flush=True,
            )
            break
    if not blink_rig_data.get("enabled") and eye_blink_mode != "off":
        print(
            f"[EyeBlink] Skipped eyelid rig ({blink_rig_data.get('reason', 'unknown')})",
            flush=True,
        )

    # 3. Load resolved PhysBones config and resolve chains against current armature
    pb_cfg = physbone_helper.load_physbone_config(project_paths.to_host_path(manifest["physbones_cfg"]))
    pb_chain_specs, pb_parent_map, _pb_custom_names, pb_bmap_ci = (
        physbone_helper.build_chain_specs_from_config(pb_cfg)
    )

    # 4. Evaluate meshes, strip face alpha overlays, remap UVs/weights into GTA V space
    depsgraph_eval = bpy.context.evaluated_depsgraph_get()
    processed_objs: List[Any] = []
    parsed_mats = atlas_manifest.get("all_parsed_materials") or {}
    parsed_mats_by_path = {
        str(info.get("mat_path", "") or "").replace("\\", "/").lower(): info
        for info in parsed_mats.values()
        if isinstance(info, dict) and info.get("mat_path")
    }
    uv_regions_by_mat = atlas_manifest.get("materials") or {}
    uv_regions_by_mat_path = {
        str(key).replace("\\", "/").lower(): val
        for key, val in (atlas_manifest.get("materials_by_path") or {}).items()
    }
    uv_regions_by_stem = atlas_manifest.get("textures_by_stem") or {}
    default_region = (
        next(iter(uv_regions_by_mat.values()), None)
        or next(iter(uv_regions_by_stem.values()), None)
        or {"u_offset": 0.0, "v_offset": 0.0, "u_scale": 1.0, "v_scale": 1.0}
    )
    ma_mesh_mats_map = ma_plan.get("mesh_materials") or {}
    ma_mesh_mats_ci = {str(mesh_key).strip().lower(): val for mesh_key, val in ma_mesh_mats_map.items() if mesh_key}
    tagged_mat_cache: Dict[Tuple[str, str], Any] = {}

    def _get_tagged_unity_mat(u_spec: Dict[str, Any], fallback_label: str) -> Any:
        u_path = str(u_spec.get("mat_path", "") or "").strip()
        u_name = str(u_spec.get("name", "") or "").strip() or fallback_label
        cache_key = (u_path.replace("\\", "/").lower(), u_name)
        cached_mat = tagged_mat_cache.get(cache_key)
        if cached_mat is not None:
            return cached_mat
        bl_mat = bpy.data.materials.new(name=f"vrc_{u_name[:40]}")
        bl_mat["vrc2gtav_mat_path"] = u_path
        bl_mat["vrc2gtav_mat_name"] = u_name
        tagged_mat_cache[cache_key] = bl_mat
        return bl_mat

    for src_obj in active_meshes:
        eval_obj = src_obj.evaluated_get(depsgraph_eval)
        new_mesh = bpy.data.meshes.new_from_object(eval_obj)

        unity_mats_list: List[Dict[str, Any]] = []
        raw_mats_json = src_obj.get("vrc2gtav_unity_mats_json")
        if raw_mats_json:
            try:
                loaded_mats = json.loads(str(raw_mats_json))
                if isinstance(loaded_mats, list):
                    unity_mats_list = [item for item in loaded_mats if isinstance(item, dict)]
            except ValueError:
                pass
        if not unity_mats_list:
            base_obj_name = _strip_object_base_name(src_obj.name)
            fb_list = ma_mesh_mats_map.get(base_obj_name) or ma_mesh_mats_ci.get(base_obj_name.lower()) or []
            unity_mats_list = [item for item in fb_list if isinstance(item, dict)]

        bm_data = bmesh.new()
        bm_data.from_mesh(new_mesh)
        orig_vert_layer = bm_data.verts.layers.int.new("orig_vert_idx")
        for vert_counter, vert_elem in enumerate(bm_data.verts):
            vert_elem[orig_vert_layer] = vert_counter

        blender_to_unity_slot = map_blender_slots_to_unity_submeshes(
            [poly_elem.material_index for poly_elem in bm_data.faces],
            len(src_obj.data.materials),
        )
        strip_indices = []
        for mat_idx, mat_slot in enumerate(src_obj.data.materials):
            unity_slot_idx = blender_to_unity_slot.get(mat_idx, mat_idx)
            u_spec = unity_mats_list[unity_slot_idx] if unity_slot_idx < len(unity_mats_list) else {}
            u_path_norm = str(u_spec.get("mat_path", "") or "").replace("\\", "/").lower()
            u_name = str(u_spec.get("name", "") or "").strip()
            mat_name_check = u_name or (mat_slot.name if mat_slot is not None else "")
            if not mat_name_check:
                continue
            mat_key = _strip_object_base_name(mat_name_check)
            mat_meta = (
                parsed_mats_by_path.get(u_path_norm)
                or parsed_mats.get(mat_key)
                or parsed_mats.get(mat_name_check)
                or {}
            )
            if mat_meta.get("is_body_alpha_overlay") or (
                _strip_object_base_name(src_obj.name).lower() == "body"
                and "alpha" in mat_name_check.lower()
                and "hair" not in mat_name_check.lower()
            ):
                strip_indices.append(mat_idx)

        if strip_indices:
            del_faces = [face_elem for face_elem in bm_data.faces if face_elem.material_index in strip_indices]
            if del_faces:
                bmesh.ops.delete(bm_data, geom=del_faces, context="FACES")
                del_verts = [vert_elem for vert_elem in bm_data.verts if not vert_elem.link_faces]
                if del_verts:
                    bmesh.ops.delete(bm_data, geom=del_verts, context="VERTS")

        bmesh.ops.triangulate(bm_data, faces=bm_data.faces)
        for face_elem in bm_data.faces:
            face_elem.smooth = True
        bm_data.verts.ensure_lookup_table()
        kept_orig_indices = [vert_elem[orig_vert_layer] for vert_elem in bm_data.verts]
        bm_data.to_mesh(new_mesh)
        bm_data.free()
        new_mesh.update()

        if len(new_mesh.vertices) == 0:
            bpy.data.meshes.remove(new_mesh)
            continue

        eval_world_mat = eval_obj.matrix_world
        for vert_item in new_mesh.vertices:
            world_coord = eval_world_mat @ vert_item.co
            vert_item.co.x = world_coord.x * scale_factor
            vert_item.co.y = world_coord.y * scale_factor
            vert_item.co.z = world_coord.z * scale_factor + z_offset
        new_mesh.update()

        new_obj = bpy.data.objects.new(f"proc_{src_obj.name}", new_mesh)
        bpy.context.collection.objects.link(new_obj)
        if _strip_object_base_name(src_obj.name).lower() != "body" and new_mesh.has_custom_normals:
            bpy.context.view_layer.objects.active = new_obj
            bpy.ops.mesh.customdata_custom_splitnormals_clear()

        # Preserve Unity material assignments so every mesh/slot maps to its exact atlas tile
        kept_slots_map: Dict[int, int] = {}
        orig_poly_mats = [poly_elem.material_index for poly_elem in new_obj.data.polygons]
        if src_obj.data.materials:
            new_obj.data.materials.clear()
            for old_idx, mat_item in enumerate(src_obj.data.materials):
                if old_idx in strip_indices:
                    continue
                kept_slots_map[old_idx] = len(new_obj.data.materials)
                if unity_mats_list:
                    unity_slot_idx = blender_to_unity_slot.get(old_idx, old_idx)
                    u_spec = unity_mats_list[min(unity_slot_idx, len(unity_mats_list) - 1)]
                    fb_label = mat_item.name if mat_item is not None else src_obj.name
                    new_obj.data.materials.append(_get_tagged_unity_mat(u_spec, fb_label))
                else:
                    new_obj.data.materials.append(mat_item)
            for poly_elem, old_slot_idx in zip(new_obj.data.polygons, orig_poly_mats):
                poly_elem.material_index = kept_slots_map.get(old_slot_idx, 0)
        elif unity_mats_list:
            new_obj.data.materials.clear()
            new_obj.data.materials.append(_get_tagged_unity_mat(unity_mats_list[0], src_obj.name))
            for poly_elem in new_obj.data.polygons:
                poly_elem.material_index = 0

        src_parent_lookup = {
            bone_item.name.lower(): bone_item.parent.name
            for bone_item in src_armature.data.bones
            if bone_item.parent is not None
        }
        vgroup_names_by_idx = {vgrp.index: vgrp.name for vgrp in src_obj.vertex_groups}
        vgroup_target_names = {
            vgrp.index: _resolve_universal_target_bone(
                vgrp.name,
                src_obj.name,
                pb_bmap_ci,
                src_parent_lookup=src_parent_lookup,
            )
            for vgrp in src_obj.vertex_groups
        }

        is_skirt_mesh = "skirt" in src_obj.name.lower() or "dress" in src_obj.name.lower()
        for new_idx, orig_idx in enumerate(kept_orig_indices):
            if is_skirt_mesh:
                vert_w = _compute_soft_skirt_weights(
                    src_obj,
                    orig_idx,
                    new_mesh.vertices[new_idx].co,
                    vgroup_names_by_idx,
                    vgroup_target_names,
                )
            else:
                vert_w = {}
                if orig_idx < len(src_obj.data.vertices):
                    for grp_elem in src_obj.data.vertices[orig_idx].groups:
                        if grp_elem.weight > 0.001 and grp_elem.group in vgroup_target_names:
                            tgt_name = vgroup_target_names[grp_elem.group]
                            vert_w[tgt_name] = vert_w.get(tgt_name, 0.0) + grp_elem.weight

            total_w = sum(vert_w.values())
            if total_w > 0.0:
                for tgt_name, weight_val in vert_w.items():
                    vgroup = new_obj.vertex_groups.get(tgt_name) or new_obj.vertex_groups.new(name=tgt_name)
                    vgroup.add([new_idx], weight_val / total_w, "ADD")
            else:
                low_src_nm = src_obj.name.lower()
                is_head_mesh = src_obj == body_obj or any(
                    tok in low_src_nm
                    for tok in ("hair", "back", "side", "bang", "beret", "halo", "ear", "glasses", "pocky")
                )
                def_bone = "SKEL_Head" if is_head_mesh else "SKEL_Pelvis"
                vgroup = new_obj.vertex_groups.get(def_bone) or new_obj.vertex_groups.new(name=def_bone)
                vgroup.add([new_idx], 1.0, "REPLACE")

        if src_obj == body_obj and body_jaw_weights and jaw_bone_name is not None:
            jaw_grp = new_obj.vertex_groups.get(jaw_bone_name) or new_obj.vertex_groups.new(name=jaw_bone_name)
            head_grp = new_obj.vertex_groups.get("SKEL_Head") or new_obj.vertex_groups.new(name="SKEL_Head")
            for new_idx, orig_idx in enumerate(kept_orig_indices):
                if orig_idx in body_jaw_weights:
                    jaw_val = body_jaw_weights[orig_idx]
                    jaw_grp.add([new_idx], jaw_val, "REPLACE")
                    head_grp.add([new_idx], max(0.0, 1.0 - jaw_val), "REPLACE")

        if src_obj == blink_body_obj and blink_rig_data.get("enabled"):
            eye_blink_helper.apply_eyelid_blink_weights_to_mesh(
                new_obj,
                blink_rig_data["weights_by_orig_vert"],
                kept_orig_vert_indices=kept_orig_indices,
            )

        processed_objs.append(new_obj)

    # 5. Relocate arm/hand/finger bones + inject custom PhysBones & Blink bones
    hand_targets = hand_skeleton_helper.extract_avatar_arm_hand_targets(
        src_armature, scale_factor, z_offset
    )
    relocated_arms = hand_skeleton_helper.relocate_blender_armature_bones(
        ped_armature, hand_targets
    )
    print(f"[Skeleton] Relocated {relocated_arms} arm/hand/finger bones onto {ped_name}", flush=True)

    bpy.context.view_layer.update()
    src_bones_ci = {pose_item.name.lower(): pose_item for pose_item in src_armature.pose.bones}
    ped_world_mats = {
        bone_item.name: (ped_armature.matrix_world @ bone_item.matrix_local).copy()
        for bone_item in ped_armature.data.bones
    }

    def _map_world_mat(src_mat):
        loc = src_mat.translation
        tgt_loc = mathutils.Vector(
            (loc.x * scale_factor, loc.y * scale_factor, loc.z * scale_factor + z_offset)
        )
        return mathutils.Matrix.Translation(tgt_loc) @ src_mat.to_quaternion().to_matrix().to_4x4()

    def _resolve_pb_mat(src_bone_name: str):
        raw_low = src_bone_name.strip().lower()
        pose_item = src_bones_ci.get(raw_low)
        if pose_item is None:
            dot_alias = re.sub(r"\s+(\d+)$", lambda match_obj: f".{int(match_obj.group(1)):03d}", raw_low)
            pose_item = src_bones_ci.get(dot_alias)
        if pose_item is None:
            space_alias = re.sub(r"\.(\d{3})$", lambda match_obj: f" {int(match_obj.group(1))}", raw_low)
            pose_item = src_bones_ci.get(space_alias)
        if pose_item is None:
            return None
        return _map_world_mat(src_armature.matrix_world @ pose_item.matrix)

    custom_physbones, physbone_chain_records = physbone_helper.build_dynamic_physbone_chains(
        ped_armature=ped_armature,
        chain_specs=pb_chain_specs,
        parent_map=pb_parent_map,
        chain_cfgs=pb_cfg.get("chains", {}),
        source_world_mat_fn=_resolve_pb_mat,
        ped_world_matrices=ped_world_mats,
    )
    for chain_rec in physbone_chain_records:
        chain_rec["model"] = ped_name

    if custom_physbones:
        hand_skeleton_helper.inject_custom_bones_into_blender_armature(
            ped_armature,
            custom_physbones,
            bone_tag_fn=physbone_helper.compute_gtav_bone_tag,
        )
        target_bones.update(item["name"] for item in custom_physbones)
        print(
            f"[PhysBones] Injected {len(custom_physbones)} bones ({len(physbone_chain_records)} chains) for {ped_name}",
            flush=True,
        )

    # Guarantee no remapped vertex group references a skipped/missing PB_* bone.
    target_bones_ci = {bname.lower(): bname for bname in target_bones}
    pb_fallback_parents: Dict[str, str] = {}
    for _c_key, _c_gtav, _c_src_b, _c_gtav_b in pb_chain_specs:
        par_cand = pb_parent_map.get(_c_gtav_b[0], "SKEL_Pelvis") if _c_gtav_b else "SKEL_Pelvis"
        resolved_par = target_bones_ci.get(par_cand.lower(), "SKEL_Pelvis")
        for gt_bone_nm in _c_gtav_b:
            pb_fallback_parents[gt_bone_nm.lower()] = resolved_par
    for proc_obj in processed_objs:
        missing_vgrps = [
            vgrp for vgrp in list(proc_obj.vertex_groups)
            if vgrp.name.lower() not in target_bones_ci and vgrp.name.startswith("PB_")
        ]
        for miss_vg in missing_vgrps:
            fb_bone_name = pb_fallback_parents.get(miss_vg.name.lower(), "SKEL_Pelvis")
            fb_vg = proc_obj.vertex_groups.get(fb_bone_name) or proc_obj.vertex_groups.new(name=fb_bone_name)
            miss_idx = miss_vg.index
            for vert_elem in proc_obj.data.vertices:
                for grp_elem in vert_elem.groups:
                    if grp_elem.group == miss_idx and grp_elem.weight > 0.0:
                        fb_vg.add([vert_elem.index], grp_elem.weight, "ADD")
            proc_obj.vertex_groups.remove(miss_vg)

    custom_blink_bones = []
    blink_profiles_to_merge = []
    if blink_rig_data.get("enabled"):
        custom_blink_bones = eye_blink_helper.build_blink_custom_bone_specs(
            ped_armature,
            blink_anchors=blink_anchors,
            blink_rig_data=blink_rig_data,
            world_scale=scale_factor,
            world_z_offset=z_offset,
        )
        if custom_blink_bones:
            hand_skeleton_helper.inject_custom_bones_into_blender_armature(
                ped_armature,
                custom_blink_bones,
                bone_tag_fn=physbone_helper.compute_gtav_bone_tag,
            )
            target_bones.update(item["name"] for item in custom_blink_bones)
        bpy.context.view_layer.update()
        scaled_blink_deltas = eye_blink_helper.scale_eye_blink_deltas(
            blink_rig_data, scale_factor
        )
        blink_prof = eye_blink_helper.build_blink_profile_for_ped(
            ped_armature,
            ped_name,
            scaled_blink_deltas,
            delta_rotations_world=blink_rig_data.get("rot_quats_world"),
            enabled=True,
            max_blink=eye_blink_strength,
        )
        if blink_prof is not None:
            blink_profiles_to_merge.append(blink_prof)

    # Remove source objects before joining
    for obj_item in list(bpy.data.objects):
        if obj_item != ped_armature and obj_item not in processed_objs:
            bpy.data.objects.remove(obj_item, do_unlink=True)

    uv_regions_ci = {key.lower(): val for key, val in uv_regions_by_mat.items()}

    def _resolve_mat_region(mat_obj: Any) -> Dict[str, Any]:
        if mat_obj is not None:
            u_path = str(mat_obj.get("vrc2gtav_mat_path", "") or "").replace("\\", "/").lower()
            if u_path:
                found_path = uv_regions_by_mat_path.get(u_path)
                if found_path is not None:
                    return found_path
                try:
                    resolved_u = str(Path(u_path).resolve()).replace("\\", "/").lower()
                    if resolved_u in uv_regions_by_mat_path:
                        return uv_regions_by_mat_path[resolved_u]
                except OSError:
                    pass
            u_name = str(mat_obj.get("vrc2gtav_mat_name", "") or "").strip()
            if u_name:
                found_u = uv_regions_by_mat.get(u_name) or uv_regions_ci.get(u_name.lower())
                if found_u is not None:
                    return found_u
        mat_name_raw = _strip_object_base_name(mat_obj.name) if mat_obj else ""
        low_name = mat_name_raw.lower()
        found = uv_regions_by_mat.get(mat_name_raw) or uv_regions_ci.get(low_name)
        if found is None:
            for key_tok, reg_val in uv_regions_by_stem.items():
                if key_tok in low_name or low_name in key_tok:
                    found = reg_val
                    break
        return found or default_region

    # Mark objects containing double-sided materials BEFORE decimation so RPF7 poly
    # budget accounts for the 2x backface duplication performed below.
    for proc_obj in processed_objs:
        if getattr(proc_obj, "type", None) != "MESH" or getattr(proc_obj, "data", None) is None:
            continue
        obj_mats = list(proc_obj.data.materials)
        ds_poly_count = sum(
            1
            for poly_item in proc_obj.data.polygons
            if 0 <= poly_item.material_index < len(obj_mats)
            and bool(_resolve_mat_region(obj_mats[poly_item.material_index]).get("is_double_sided"))
        )
        proc_obj["vtoon_double_sided"] = ds_poly_count * 2 >= max(1, len(proc_obj.data.polygons))

    # 6. Join active meshes and map shader + 2x2/NxN Atlas UVs + ped blood decals
    enable_blood_decals = bool(manifest.get("blood_decals", True))
    ped_damage_helper.enforce_ped_rpf7_poly_budget(
        bpy, processed_objs, enable_blood_decals=enable_blood_decals
    )

    # Unify UV layer names before join so Blender merges all UVs into "UVMap 0"
    for proc_obj in processed_objs:
        if getattr(proc_obj, "type", None) != "MESH" or getattr(proc_obj, "data", None) is None:
            continue
        mesh_uvs = proc_obj.data.uv_layers
        if not mesh_uvs:
            mesh_uvs.new(name="UVMap 0")
            continue
        primary_uv = mesh_uvs.active or mesh_uvs[0]
        for extra_uv in list(mesh_uvs):
            if extra_uv != primary_uv:
                mesh_uvs.remove(extra_uv)
        primary_uv.name = "UVMap 0"

    conformed_cloth_verts = conform_tight_torso_clothing_weights(
        processed_objs, ped_armature
    )
    if conformed_cloth_verts:
        print(
            f"[Rigging] Conformed {conformed_cloth_verts} upper-chest torso clothing vertices.",
            flush=True,
        )

    bpy.ops.object.select_all(action="DESELECT")
    for proc_obj in processed_objs:
        proc_obj.select_set(True)
    bpy.context.view_layer.objects.active = processed_objs[0]
    bpy.ops.object.join()
    joined_mesh_obj = processed_objs[0]
    joined_mesh_obj.name = "SKEL_ROOT"

    welded_midline_pairs = blender_hair_helper.weld_symmetry_midline_seams(
        joined_mesh_obj, respect_atlas_tiles=False
    )
    if welded_midline_pairs:
        print(
            f"[VToon] Welded {welded_midline_pairs} X=0 symmetry seam vertex pairs.",
            flush=True,
        )

    for poly_face in joined_mesh_obj.data.polygons:
        poly_face.use_smooth = True
    joined_mesh_obj.data.update()

    valid_arm_bones = {bone_item.name for bone_item in ped_armature.data.bones}
    for vgroup in list(joined_mesh_obj.vertex_groups):
        if vgroup.name not in valid_arm_bones:
            joined_mesh_obj.vertex_groups.remove(vgroup)

    fallback_head_vgrp = joined_mesh_obj.vertex_groups.get("SKEL_Head") or joined_mesh_obj.vertex_groups.new(name="SKEL_Head")
    fallback_pelvis_vgrp = joined_mesh_obj.vertex_groups.get("SKEL_Pelvis") or joined_mesh_obj.vertex_groups.new(name="SKEL_Pelvis")
    for vert_item in joined_mesh_obj.data.vertices:
        total_vw = sum(grp_item.weight for grp_item in vert_item.groups)
        if total_vw < 1e-4:
            if float(vert_item.co.z) >= 0.45:
                fallback_head_vgrp.add([vert_item.index], 1.0, "REPLACE")
            else:
                fallback_pelvis_vgrp.add([vert_item.index], 1.0, "REPLACE")

    bpy.context.view_layer.objects.active = joined_mesh_obj
    bpy.ops.object.vertex_group_limit_total(limit=4)
    bpy.ops.object.vertex_group_normalize_all()

    atlas_img = bpy.data.images.load(str(project_paths.to_host_path(manifest["atlas_png"])))
    norm_host_path = project_paths.to_host_path(manifest["normal_png"])
    spec_host_path = project_paths.to_host_path(manifest["spec_png"])
    norm_dds_path = norm_host_path.with_suffix(".dds")
    spec_dds_path = spec_host_path.with_suffix(".dds")
    blender_hair_helper.ensure_solid_rgba_dds(
        norm_dds_path, rgba_color=(128, 128, 255, 255), size=32
    )
    blender_hair_helper.ensure_solid_rgba_dds(
        spec_dds_path, rgba_color=(0, 0, 0, 255), size=32
    )
    norm_img = bpy.data.images.load(str(norm_dds_path), check_existing=True)
    spec_img = bpy.data.images.load(str(spec_dds_path), check_existing=True)
    if hasattr(norm_img, "colorspace_settings"):
        norm_img.colorspace_settings.name = "Non-Color"
    if hasattr(spec_img, "colorspace_settings"):
        spec_img.colorspace_settings.name = "Non-Color"

    ped_shader_mat = ped_damage_helper.create_ped_material(
        create_shader,
        f"{ped_name}_atlas",
        enable_blood_decals=enable_blood_decals,
        diffuse_image=atlas_img,
        bump_image=norm_img,
        spec_image=spec_img,
        embed_bump_spec=True,
        bumpiness=0.0,
        specular_intensity=0.0,
        specular_falloff=1.0,
        specular_fresnel=ped_damage_helper.DEFAULT_ANIME_SPECULAR_FRESNEL,
        detail_settings=(0.0, 0.0, 0.0),
        stubble_control=(0.0, 0.0),
        um_global_params=(0.0, 0.0, 0.0, 0.0),
    )
    cutout_shader_mat = None
    alpha_shader_mat = None

    slot_regions: Dict[int, Dict[str, Any]] = {}
    slot_is_face: Dict[int, bool] = {}
    double_sided_slots: List[int] = []
    for slot_idx, mat_item in enumerate(joined_mesh_obj.data.materials):
        u_name_slot = str(mat_item.get("vrc2gtav_mat_name", "") or "").strip() if mat_item else ""
        mat_name_raw = u_name_slot or (_strip_object_base_name(mat_item.name) if mat_item else "")
        low_mat_name = mat_name_raw.lower()
        resolved_reg = _resolve_mat_region(mat_item)
        slot_regions[slot_idx] = resolved_reg
        slot_is_face[slot_idx] = "face" in low_mat_name
        alpha_mode = str(resolved_reg.get("alpha_mode", "opaque"))
        if resolved_reg.get("is_double_sided") and (alpha_mode != "transparent" or "hair" in low_mat_name):
            double_sided_slots.append(slot_idx)

        if alpha_mode == "transparent":
            if alpha_shader_mat is None:
                alpha_shader_mat = ped_damage_helper.create_ped_alpha_material(
                    create_shader,
                    f"{ped_name}_hair_alpha",
                    diffuse_image=atlas_img,
                    bump_image=norm_img,
                    spec_image=spec_img,
                    embed_bump_spec=True,
                )
            joined_mesh_obj.data.materials[slot_idx] = alpha_shader_mat
        elif alpha_mode == "cutout":
            if cutout_shader_mat is None:
                cutout_shader_mat = ped_damage_helper.create_ped_hair_cutout_material(
                    create_shader,
                    f"{ped_name}_hair_cutout",
                    diffuse_image=atlas_img,
                    bump_image=norm_img,
                    spec_image=spec_img,
                    embed_bump_spec=True,
                )
            joined_mesh_obj.data.materials[slot_idx] = cutout_shader_mat
        else:
            joined_mesh_obj.data.materials[slot_idx] = ped_shader_mat

    if double_sided_slots:
        dup_faces = blender_hair_helper.duplicate_double_sided_backfaces(
            joined_mesh_obj,
            material_indices=double_sided_slots,
            normal_offset=0.00035,
        )
        print(f"[VToon] Duplicated {dup_faces} double-sided faces for slots {double_sided_slots}", flush=True)

    # Deduplicate material slots down to active distinct GTA V shader buckets (ped / cutout / alpha)
    unique_mats = []
    mat_ptr_to_idx = {}
    slot_remap = {}
    for old_idx, mat_ref in enumerate(list(joined_mesh_obj.data.materials)):
        mat_key_name = mat_ref.name if mat_ref is not None else ""
        if mat_key_name not in mat_ptr_to_idx:
            mat_ptr_to_idx[mat_key_name] = len(unique_mats)
            unique_mats.append(mat_ref)
        slot_remap[old_idx] = mat_ptr_to_idx[mat_key_name]
    # Note: apply UVs and face flag per-original slot before collapsing material indices!

    uv_layer = joined_mesh_obj.data.uv_layers[0]
    uv_layer.name = "UVMap 0"
    poly_is_face = [False] * len(joined_mesh_obj.data.polygons)
    remapped_poly_mats: List[int] = [0] * len(joined_mesh_obj.data.polygons)
    for poly_seq_idx, poly_item in enumerate(joined_mesh_obj.data.polygons):
        orig_slot = poly_item.material_index
        reg_spec = slot_regions.get(orig_slot, default_region)
        poly_is_face[poly_seq_idx] = bool(slot_is_face.get(orig_slot))
        off_u = float(reg_spec["u_offset"])
        off_v = float(reg_spec["v_offset"])
        scl_u = float(reg_spec["u_scale"])
        scl_v = float(reg_spec["v_scale"])
        for loop_idx in poly_item.loop_indices:
            uv_coord = uv_layer.data[loop_idx].uv
            local_u = max(0.001, min(0.999, uv_coord.x % 1.0 if (uv_coord.x < 0.0 or uv_coord.x > 1.0) else uv_coord.x))
            local_v = max(0.001, min(0.999, uv_coord.y % 1.0 if (uv_coord.y < 0.0 or uv_coord.y > 1.0) else uv_coord.y))
            uv_coord.x = local_u * scl_u + off_u
            uv_coord.y = local_v * scl_v + off_v
        remapped_poly_mats[poly_seq_idx] = slot_remap.get(orig_slot, 0)

    joined_mesh_obj.data.materials.clear()
    for unique_mat in unique_mats:
        joined_mesh_obj.data.materials.append(unique_mat)
    for poly_seq_idx, poly_item in enumerate(joined_mesh_obj.data.polygons):
        poly_item.material_index = remapped_poly_mats[poly_seq_idx]

    ped_damage_res = ped_damage_helper.apply_ped_damage_attributes_in_blender(
        bpy,
        joined_mesh_obj,
        ped_armature,
        enable_blood_decals=enable_blood_decals,
    )
    print(f"[PedDamage] {ped_damage_res}", flush=True)

    # Apply soft spherical anime face normals dynamically anchored to SKEL_Head
    head_world_pos = (ped_armature.matrix_world @ ped_armature.data.bones["SKEL_Head"].head_local).copy()
    joined_mesh_obj.data.calc_normals_split()
    custom_normals = [tuple(loop_item.normal) for loop_item in joined_mesh_obj.data.loops]
    mesh_verts = joined_mesh_obj.data.vertices
    mesh_loops = joined_mesh_obj.data.loops
    for poly_seq_idx, poly_item in enumerate(joined_mesh_obj.data.polygons):
        if not poly_is_face[poly_seq_idx]:
            continue
        for loop_idx in poly_item.loop_indices:
            vpos = mesh_verts[mesh_loops[loop_idx].vertex_index].co
            if vpos.y < head_world_pos.y + 0.025 and abs(vpos.x) < 0.095:
                nx_val = vpos.x * 2.2
                ny_val = -1.0
                nz_val = (vpos.z - (head_world_pos.z + 0.05)) * 1.4
                nlen = math.sqrt(nx_val * nx_val + ny_val * ny_val + nz_val * nz_val) or 1.0
                custom_normals[loop_idx] = (nx_val / nlen, ny_val / nlen, nz_val / nlen)
    joined_mesh_obj.data.normals_split_custom_set(custom_normals)
    joined_mesh_obj.data.update()

    import sollumz.ydr.ydrexport as ydrexport
    ydrexport.triangulate_mesh = lambda mesh_data: mesh_data
    blender_hair_helper.split_oversized_material_geometries(
        joined_mesh_obj, max_vertices_per_chunk=30000
    )

    # Save debuggable assembled .blend before Sollumz export
    assembled_blend = project_paths.to_host_path(manifest["assembled_blend"])
    assembled_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(assembled_blend))

    # 7. Export Sollumz Drawable Dictionary (.ydd)
    all_custom_yft_bones = list(custom_physbones or ()) + list(custom_blink_bones)
    custom_name_set = {item["name"] for item in all_custom_yft_bones}
    for arm_bone in ped_armature.data.bones:
        if arm_bone.name not in custom_name_set:
            set_recommended_bone_properties(arm_bone)

    exported_dir = os.path.join(str(project_paths.to_host_path(manifest["exported_models_dir"])), "")
    os.makedirs(exported_dir, exist_ok=True)

    def _export_ydd_with_rpf7_guard(
        target_ydd_name: str, dict_empty: Any, mesh_targets: Sequence[Any]
    ) -> None:
        ydd_out = Path(exported_dir) / f"{target_ydd_name}.ydd"
        for attempt_idx in range(3):
            bpy.ops.object.select_all(action="DESELECT")
            dict_empty.select_set(True)
            bpy.context.view_layer.objects.active = dict_empty
            bpy.ops.sollumz.export_assets(
                directory=exported_dir,
                direct_export=True,
                use_custom_settings=True,
                target_versions={"GEN8"},
                target_formats={"NATIVE", "CWXML"},
                limit_to_selected=False,
            )
            if not ydd_out.is_file() or ydd_out.stat().st_size <= 16_400_000 or attempt_idx >= 2:
                break
            cur_bytes = ydd_out.stat().st_size
            trim_ratio = max(0.35, min(0.88, (15_000_000.0 / float(cur_bytes)) * 0.90))
            print(
                f"[RPF7 Guard] {ydd_out.name} is {cur_bytes / 1048576.0:.2f} MiB (> 16 MiB); decimating by {trim_ratio:.2f} (attempt {attempt_idx + 1}/2)...",
                flush=True,
            )
            import bmesh

            for mesh_tgt in mesh_targets:
                if mesh_tgt is None or getattr(mesh_tgt.data, "shape_keys", None):
                    continue
                bpy.context.view_layer.objects.active = mesh_tgt
                dec_mod = mesh_tgt.modifiers.new("Rpf7SizeGuardDecimate", "DECIMATE")
                blender_hair_helper.configure_rpf7_decimate_modifier(
                    dec_mod, mesh_tgt, trim_ratio
                )
                bpy.ops.object.modifier_move_to_index(modifier=dec_mod.name, index=0)
                bpy.ops.object.modifier_apply(modifier=dec_mod.name)
                if any(len(poly.vertices) != 3 for poly in mesh_tgt.data.polygons):
                    bm_tmp = bmesh.new()
                    bm_tmp.from_mesh(mesh_tgt.data)
                    bmesh.ops.triangulate(bm_tmp, faces=bm_tmp.faces)
                    bm_tmp.to_mesh(mesh_tgt.data)
                    bm_tmp.free()
                mesh_tgt.data.update()
        ped_damage_helper.validate_rpf7_resource_file(ydd_out)

    if ped_format == "componentpeds":
        drawable_dict_empty = create_empty_object(SollumType.DRAWABLE_DICTIONARY)
        drawable_dict_empty.name = ped_name
        primary_set = set(comp_primary_keys)
        first_primary = comp_primary_keys[0] if comp_primary_keys else comp_all_keys[0]
        exported_primary_meshes: List[Any] = []

        for slot_key in comp_all_keys:
            if slot_key == first_primary:
                arm_slot = ped_armature
                mesh_slot = joined_mesh_obj
                exported_primary_meshes.append(mesh_slot)
            elif slot_key in primary_set:
                arm_slot = ped_armature.copy()
                arm_slot.data = ped_armature.data.copy()
                bpy.context.collection.objects.link(arm_slot)
                mesh_slot = joined_mesh_obj.copy()
                mesh_slot.data = joined_mesh_obj.data.copy()
                bpy.context.collection.objects.link(mesh_slot)
                exported_primary_meshes.append(mesh_slot)
            else:
                arm_slot = ped_armature.copy()
                arm_slot.data = ped_armature.data.copy()
                bpy.context.collection.objects.link(arm_slot)
                dummy_mesh = bpy.data.meshes.new(f"{slot_key}_dummy_mesh")
                dummy_mesh.from_pydata(
                    [(0.0, 0.0, 0.0), (0.0001, 0.0, 0.0), (0.0, 0.0001, 0.0)],
                    [],
                    [(0, 1, 2)],
                )
                dummy_mesh.uv_layers.new(name="UVMap 0")
                if enable_blood_decals:
                    dummy_mesh.uv_layers.new(name="UVMap 1")
                for color_idx, color_rgba in ((1, (1.0, 0.5, 0.0, 1.0)), (2, (0.0, 0.0, 0.0, 1.0))):
                    col_attr = dummy_mesh.color_attributes.new(
                        name=f"Color {color_idx}",
                        type="BYTE_COLOR",
                        domain="CORNER",
                    )
                    for corner_item in col_attr.data:
                        corner_item.color = color_rgba
                dummy_mesh.materials.append(ped_shader_mat)
                mesh_slot = bpy.data.objects.new(f"SKEL_ROOT_{slot_key}", dummy_mesh)
                bpy.context.collection.objects.link(mesh_slot)
                vgrp = mesh_slot.vertex_groups.new(name="SKEL_ROOT")
                vgrp.add([0, 1, 2], 1.0, "REPLACE")

            arm_slot.sollum_type = SollumType.DRAWABLE
            arm_slot.name = slot_key
            arm_slot.parent = drawable_dict_empty
            arm_slot.drawable_properties.lod_dist_high = 9998.0
            arm_slot.drawable_properties.lod_dist_med = 9998.0
            arm_slot.drawable_properties.lod_dist_low = 9998.0
            arm_slot.drawable_properties.lod_dist_vlow = 9998.0

            convert_obj_to_model(mesh_slot)
            mesh_slot.parent = arm_slot
            mod_arm = next((mod for mod in mesh_slot.modifiers if mod.type == "ARMATURE"), None)
            if mod_arm is None:
                mod_arm = mesh_slot.modifiers.new("Armature", "ARMATURE")
            mod_arm.object = arm_slot

        _export_ydd_with_rpf7_guard(ped_name, drawable_dict_empty, exported_primary_meshes)
    else:
        export_drawables = [str(item) for item in (manifest.get("export_drawables") or ["uppr_000_u"])]
        drawable_dict_empty = create_empty_object(SollumType.DRAWABLE_DICTIONARY)
        drawable_dict_empty.name = export_drawables[0]
        ped_armature.sollum_type = SollumType.DRAWABLE
        ped_armature.name = export_drawables[0]
        ped_armature.parent = drawable_dict_empty
        ped_armature.drawable_properties.lod_dist_high = 9998.0
        ped_armature.drawable_properties.lod_dist_med = 9998.0
        ped_armature.drawable_properties.lod_dist_low = 9998.0
        ped_armature.drawable_properties.lod_dist_vlow = 9998.0

        convert_obj_to_model(joined_mesh_obj)
        joined_mesh_obj.parent = ped_armature
        arm_mod = joined_mesh_obj.modifiers.new("Armature", "ARMATURE")
        arm_mod.object = ped_armature

        primary_slot = export_drawables[0]
        drawable_dict_empty.name = primary_slot
        ped_armature.name = primary_slot
        _export_ydd_with_rpf7_guard(primary_slot, drawable_dict_empty, [joined_mesh_obj])

    # 8. Patch .yft skeleton with PyMateria
    yft_output_path = project_paths.to_host_path(manifest["target_yft"])
    updated_cnt, total_cnt, max_delta = hand_skeleton_helper.patch_yft_skeleton(
        skeleton_yft_path,
        yft_output_path,
        hand_targets,
        custom_child_bones=all_custom_yft_bones or None,
    )
    ped_damage_helper.validate_rpf7_resource_file(yft_output_path)
    print(
        f"[YFT] Exported {yft_output_path.name}: {updated_cnt}/{total_cnt} bones, max delta {max_delta:.6f}m",
        flush=True,
    )

    # 9. Export & merge GTAVPhysBones.ini scoped by `model = <ped_name>`
    should_deploy_ini = bool(manifest.get("deploy", True))
    if physbone_chain_records or blink_profiles_to_merge or eye_blink_mode == "off":
        local_ini = Path(exported_dir) / "GTAVPhysBones.ini"
        physbone_helper.export_physbone_asi_ini(
            local_ini,
            physbone_chain_records,
            target_ped_model=ped_name,
            blink_profiles=blink_profiles_to_merge,
        )
        if should_deploy_ini:
            repo_root = project_paths.get_project_root()
            gtav_root = project_paths.get_gtav_root_dir()
            if gtav_root.is_dir():
                gtav_ini = gtav_root / "GTAVPhysBones.ini"
                seed_ini = (
                    gtav_ini
                    if gtav_ini.is_file()
                    else repo_root / "2_Michael_Shinano_EternalReunion" / "5_rpf_package" / "GTAVPhysBones.ini"
                )
                primary_merge_ini = seed_ini if seed_ini.is_file() else local_ini
                physbone_helper.merge_physbone_asi_ini(
                    primary_merge_ini,
                    physbone_chain_records,
                    own_prefixes=(),
                    target_ped_model="all",
                    extra_sync_paths=[local_ini, gtav_ini],
                    blink_profiles=blink_profiles_to_merge,
                    own_blink_models=(ped_name,),
                    own_chain_models=(ped_name,),
                )
        print(
            f"[PhysBones] Merged {len(physbone_chain_records)} chains + {len(blink_profiles_to_merge)} blink profiles for model={ped_name}",
            flush=True,
        )


def build_and_deploy_npc_from_source(
    *,
    source_spec: str,
    target_ped: str,
    avatar_name: str = "",
    deploy: bool = True,
    repack_archives: bool = True,
    force_reextract: bool = False,
    blood_decals: bool = True,
    eye_blink: Optional[bool] = None,
    eye_blink_strength: Optional[float] = None,
    mouth_open_strength: Optional[float] = None,
    physbones_marshmallow: Optional[bool] = None,
    import_face_blendshapes: Optional[bool] = None,
    import_body_blendshapes: Optional[bool] = None,
    blendshapes_source: Optional[str] = None,
    physbones_source: Optional[str] = None,
    blendshapes_cfg: Optional[str] = None,
    face_anim: Optional[str] = None,
    physbones_cfg: Optional[str] = None,
    vtoon_char_id: Optional[int] = None,
    atlas_size: int = 2048,
    normal_size: int = 0,
    secondary_atlas_size: int = 0,
    texture_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Full end-to-end build pipeline: Ingest -> Atlas -> Blender -> Apply -> Deploy."""
    import npc_registry_helper
    import vrc2gtav_paths as project_paths

    manifest = prepare_universal_npc_build(
        source_spec=source_spec,
        target_ped=target_ped,
        avatar_name=avatar_name,
        force_reextract=force_reextract,
        blood_decals=blood_decals,
        eye_blink=eye_blink,
        eye_blink_strength=eye_blink_strength,
        mouth_open_strength=mouth_open_strength,
        physbones_marshmallow=physbones_marshmallow,
        import_face_blendshapes=import_face_blendshapes,
        import_body_blendshapes=import_body_blendshapes,
        blendshapes_source=blendshapes_source,
        physbones_source=physbones_source,
        blendshapes_cfg=blendshapes_cfg,
        face_anim=face_anim,
        physbones_cfg=physbones_cfg,
        vtoon_char_id=vtoon_char_id,
        atlas_size=atlas_size,
        normal_size=normal_size,
        secondary_atlas_size=secondary_atlas_size,
        texture_overrides=texture_overrides,
        deploy=deploy,
    )

    print("[4/4] Running Blender 4.0.2 + Sollumz build...", flush=True)
    blender_bin = str(project_paths.to_host_path(project_paths.get_blender_exe()) or "")
    use_win_paths = blender_bin.lower().endswith(".exe") and os.name != "nt"
    manifest_arg = (
        project_paths.to_windows_path(manifest["build_manifest_path"])
        if use_win_paths
        else manifest["build_manifest_path"]
    )
    blender_cmd, blender_env = project_paths.build_blender_command(
        Path(__file__).resolve(),
        [
            "--in-blender",
            "--manifest",
            manifest_arg,
        ],
    )
    subprocess.run(blender_cmd, env=blender_env, stdin=subprocess.DEVNULL, check=True)

    reg_data = npc_registry_helper.load_npc_registry(project_paths.get_project_root())
    npc_entry = reg_data["npcs"][manifest["ped_name"]]
    if deploy:
        apply_summary = npc_registry_helper.apply_npc_slot_replacement(
            manifest["ped_name"], npc_entry
        )
        manifest["apply_summary"] = apply_summary
        if repack_archives:
            deployed_rpfs = npc_registry_helper.repack_and_deploy_npc_entry(
                manifest["ped_name"],
                npc_entry,
                secondary_atlas_size=secondary_atlas_size,
            )
            manifest["deployed_rpfs"] = [str(pth) for pth in deployed_rpfs]
    return manifest


def _cli_main() -> int:
    """CLI entrypoint supporting direct invocation or `--in-blender --manifest ...`."""
    if "--in-blender" in sys.argv:
        import vrc2gtav_paths as project_paths
        custom_args = project_paths.extract_custom_blender_args()
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--in-blender", action="store_true")
        parser.add_argument("--manifest", required=True)
        parsed = parser.parse_args(custom_args)
        run_in_blender_build(project_paths.to_host_path(parsed.manifest))
        return 0

    parser = argparse.ArgumentParser(
        description="Build and deploy any Unity/VRChat avatar onto GTA V protagonist/NPC slots."
    )
    parser.add_argument("--source", default="", help="Path to .zip/.unitypackage/.prefab/.unity or folder")
    parser.add_argument(
        "--target-ped",
        default="",
        help="GTA V ped/protagonist name or comma-separated list (e.g. player_zero,player_one or ig_lamardavis)",
    )
    parser.add_argument("--avatar-name", default="")
    parser.add_argument("--no-deploy", action="store_true")
    parser.add_argument("--no-repack", action="store_true")
    parser.add_argument("--force-reextract", action="store_true")
    parser.add_argument("--blood-decals", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--eye-blink", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--eye-blink-strength", type=float, default=None)
    parser.add_argument("--mouth-open-strength", type=float, default=None)
    parser.add_argument("--physbones-marshmallow", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--import-face-blendshapes", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--import-body-blendshapes", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--blendshapes-source", choices=["auto", "unity", "cfg"], default=None)
    parser.add_argument("--physbones-source", choices=["auto", "unity", "cfg"], default=None)
    parser.add_argument("--blendshapes-cfg", default=None)
    parser.add_argument("--face-anim", default=None)
    parser.add_argument("--physbones-cfg", default=None)
    parser.add_argument("--vtoon-char-id", type=int, default=None)
    parser.add_argument("--atlas-size", type=int, default=2048)
    parser.add_argument("--normal-size", type=int, default=0)
    parser.add_argument("--secondary-atlas-size", type=int, default=0)
    parser.add_argument("--texture-overrides", default=None)
    parser.add_argument("--texture-override", action="append", default=[])
    parser.add_argument("--slots-json", default=None, help="JSON file/payload defining multiple ped->avatar slots")
    parser.add_argument("--restore-peds", default=None, help="Comma-separated peds to restore to vanilla")
    parser.add_argument("--restore-all", action="store_true", help="Restore all modded peds to Rockstar vanilla")
    parser.add_argument("--lang", choices=["auto", "en", "ja", "pt"], default="auto")
    parsed = parser.parse_args()

    resolved_tex_overrides: Dict[str, str] = {}
    if parsed.texture_overrides:
        import vrc2gtav_paths as project_paths_cfg

        json_path = project_paths_cfg.to_host_path(parsed.texture_overrides)
        if json_path.is_file():
            loaded_ovr = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(loaded_ovr, dict):
                resolved_tex_overrides.update(
                    {
                        str(mat_key): str(tex_val)
                        for mat_key, tex_val in loaded_ovr.items()
                        if str(tex_val).strip()
                    }
                )
    for pair_raw in parsed.texture_override or ():
        if "=" in str(pair_raw):
            mat_key_tok, tex_val_tok = str(pair_raw).split("=", 1)
            if mat_key_tok.strip() and tex_val_tok.strip():
                resolved_tex_overrides[mat_key_tok.strip()] = tex_val_tok.strip()

    try:
        import vrc2gtav_i18n as project_i18n
        project_i18n.set_active_language(parsed.lang)
    except Exception:
        pass

    should_deploy = not parsed.no_deploy
    should_repack = should_deploy and (not parsed.no_repack)

    if parsed.restore_all or parsed.restore_peds:
        import restore_vanilla_helper

        restore_targets = [
            tok.strip() for tok in str(parsed.restore_peds or "").split(",") if tok.strip()
        ]
        restore_vanilla_helper.restore_peds_to_vanilla(
            restore_targets,
            restore_all=bool(parsed.restore_all),
            deploy=should_deploy,
        )
        return 0

    if parsed.slots_json:
        import restore_vanilla_helper
        import vrc2gtav_paths as project_paths_cfg

        slots_path = project_paths_cfg.to_host_path(parsed.slots_json)
        shared_defaults = {
            "source": parsed.source,
            "force_reextract": parsed.force_reextract,
            "blood_decals": parsed.blood_decals,
            "eye_blink": parsed.eye_blink,
            "eye_blink_strength": parsed.eye_blink_strength,
            "mouth_open_strength": parsed.mouth_open_strength,
            "physbones_marshmallow": parsed.physbones_marshmallow,
            "import_face_blendshapes": parsed.import_face_blendshapes,
            "import_body_blendshapes": parsed.import_body_blendshapes,
            "blendshapes_source": parsed.blendshapes_source,
            "physbones_source": parsed.physbones_source,
            "blendshapes_cfg": parsed.blendshapes_cfg,
            "face_anim": parsed.face_anim,
            "physbones_cfg": parsed.physbones_cfg,
            "atlas_size": parsed.atlas_size,
            "normal_size": parsed.normal_size,
            "secondary_atlas_size": parsed.secondary_atlas_size,
            "texture_overrides": resolved_tex_overrides or None,
        }
        restore_vanilla_helper.run_multi_slot_builds(
            slots_path if slots_path.is_file() else parsed.slots_json,
            shared_defaults=shared_defaults,
            deploy=should_deploy,
            repack_and_deploy=should_repack,
            secondary_atlas_size=parsed.secondary_atlas_size,
        )
        return 0

    if not str(parsed.source or "").strip():
        raise ValueError("--source is required unless --slots-json, --restore-peds, or --restore-all is used")

    ped_targets = [
        tok.strip() for tok in str(parsed.target_ped or "").split(",") if tok.strip()
    ]
    if not ped_targets:
        raise ValueError("--target-ped must specify at least one target")

    built_peds: List[str] = []
    for idx_ped, ped_slot in enumerate(ped_targets):
        result = build_and_deploy_npc_from_source(
            source_spec=parsed.source,
            target_ped=ped_slot,
            avatar_name=parsed.avatar_name,
            deploy=should_deploy,
            repack_archives=False,
            force_reextract=(parsed.force_reextract if idx_ped == 0 else False),
            blood_decals=parsed.blood_decals,
            eye_blink=parsed.eye_blink,
            eye_blink_strength=parsed.eye_blink_strength,
            mouth_open_strength=parsed.mouth_open_strength,
            physbones_marshmallow=parsed.physbones_marshmallow,
            import_face_blendshapes=parsed.import_face_blendshapes,
            import_body_blendshapes=parsed.import_body_blendshapes,
            blendshapes_source=parsed.blendshapes_source,
            physbones_source=parsed.physbones_source,
            blendshapes_cfg=parsed.blendshapes_cfg,
            face_anim=parsed.face_anim,
            physbones_cfg=parsed.physbones_cfg,
            vtoon_char_id=parsed.vtoon_char_id if len(ped_targets) == 1 else None,
            atlas_size=parsed.atlas_size,
            normal_size=parsed.normal_size,
            secondary_atlas_size=parsed.secondary_atlas_size,
            texture_overrides=resolved_tex_overrides or None,
        )
        built_peds.append(str(result["ped_name"]))
        print(f"[DONE] Build complete: {result['ped_name']} -> {result['avatar_name']}", flush=True)

    if should_repack and built_peds:
        import restore_vanilla_helper

        restore_vanilla_helper.repack_and_deploy_built_peds(
            built_peds,
            secondary_atlas_size=parsed.secondary_atlas_size,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
