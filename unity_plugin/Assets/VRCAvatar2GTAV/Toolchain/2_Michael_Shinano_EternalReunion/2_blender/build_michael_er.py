#!/usr/bin/env python3
"""
build_michael_er.py
===================
Executed via Blender 4.0+ (background mode) with the Sollumz addon to compile
the full Shinano Eternal Reunion avatar (outfits, CooniBob custom hair, and
Pocket Watch) as an upper component (`uppr`) for Michael (`player_zero`) in
GTA V Legacy (RAGE Engine GEN8).

Technical Rules & Features:
  1. Multi-FBX assembly: Shinano Base, Eternal Reunion Outfit, Pocket Watch,
     and CooniBob / Neko Tied Bob Hair.
  2. Strict removal of EditorOnly / disabled Unity items (underwear, default
     hair, CooniBob_Tail, UN2_Beret, summer variants).
  3. Shrink culling and Unity / .cfg-driven blendshapes across body, outfit,
     accessories, and hair meshes.
  4. Universal bone mapping onto the Michael GTA V skeleton (`player_zero.yft`)
     and 1:1 arm/hand/finger relocation for RAGE animations.
  5. Unified 4x2 Texture Atlas (`ped_default.sps`).
  6. Auto-chunking of oversized materials to respect the uint16 vertex limit.
"""

import argparse
import json
import math
import os
import struct
import sys
import zlib
from pathlib import Path

import addon_utils
import bmesh
import bpy

# Locate vrc2gtav_paths / vrc2gtav_i18n regardless of repository mirror
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_CANDIDATE = _SCRIPT_DIR.parent.parent
for _tools_candidate in (
    _REPO_ROOT_CANDIDATE / "scripts" / "common_tools",
    _REPO_ROOT_CANDIDATE / "_deploy_tools",
):
    if _tools_candidate.is_dir() and str(_tools_candidate) not in sys.path:
        sys.path.insert(0, str(_tools_candidate))

import blender_hair_helper
import blendshape_helper
import eye_blink_helper
import hand_skeleton_helper
import mathutils
import ped_damage_helper
import physbone_helper
import unity_hair_helper
import unity_scene_helper
import vrc2gtav_i18n as i18n
import vrc2gtav_paths as project_paths



from michael_er_geometry_layer import (
    CHARACTER_PROFILES,
    HEAD_ACCESSORY_MESH_NAMES,
    HUMAN_TO_GTAV_BONE_MAP,
    apply_deferred_double_sided_backfaces,
    apply_michael_er_split_normals,
    compute_pocket_watch_align_matrix,
    compute_skirt_vertex_weights,
    import_and_place_er_earrings,
    load_fbx_face_loop_normals,
    parse_fbx_binary_nodes,
    process_michael_er_mesh_inventory,
    resolve_gtav_target_bone,
    smoothstep_unit,
    validate_build_inputs,
)

# ---------------------------------------------------------------------------
# Main Assembly and Export Pipeline
# ---------------------------------------------------------------------------
def build_shinano_er_for_gtav(cli_args):
    """Compile and export Shinano Eternal Reunion (.ydd + .yft) inside Blender."""
    validate_build_inputs(cli_args)
    addon_utils.enable("sollumz")
    from sollumz.sollumz_properties import SollumType
    from sollumz.tools.blenderhelper import create_empty_object
    from sollumz.tools.drawablehelper import (
        convert_obj_to_model,
        set_recommended_bone_properties,
    )
    from sollumz.ydr.shader_materials import create_shader
    import sollumz.ydr.ydrexport as ydrexport

    char_key = project_paths.normalize_protagonist_key(cli_args.target_character)
    target_cfg = getattr(cli_args, "target_cfg", None) or project_paths.get_character_paths(
        char_key, avatar_override="shinano_er"
    )
    base_profile = dict(CHARACTER_PROFILES.get(char_key, {}))
    merged_drawables = []
    for drawable_slot in list(target_cfg.get("export_drawables") or []) + list(
        base_profile.get("export_drawables") or []
    ):
        if str(drawable_slot) not in merged_drawables:
            merged_drawables.append(str(drawable_slot))
    char_profile = {
        "ped_name": str(target_cfg.get("ped_name") or base_profile.get("ped_name", "player_zero")),
        "skeleton_yft": Path(str(cli_args.skeleton_yft)).name,
        "export_drawables": merged_drawables or ["uppr_000_r", "uppr_000_u", "uppr_001_u"],
        "target_z_min": float(target_cfg.get("target_z_min", base_profile.get("target_z_min", -0.907))),
        "target_z_max": float(target_cfg.get("target_z_max", base_profile.get("target_z_max", 0.645))),
        "arm_pose_degrees": float(target_cfg.get("arm_pose_degrees", base_profile.get("arm_pose_degrees", -55.0))),
    }

    # 1. Clear current Blender scene
    for obj_item in list(bpy.data.objects):
        bpy.data.objects.remove(obj_item)
    for mesh_item in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh_item)
    for arm_item in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm_item)
    for mat_item in list(bpy.data.materials):
        bpy.data.materials.remove(mat_item)

    # 2. Import GTA V base .yft skeleton
    skel_dir = os.path.dirname(os.path.abspath(cli_args.skeleton_yft)) + "/"
    skel_filename = os.path.basename(cli_args.skeleton_yft)
    print(i18n.translate("michael.build.importing_skeleton", path=cli_args.skeleton_yft))
    bpy.ops.sollumz.import_assets(directory=skel_dir, files=[{"name": skel_filename}])

    ped_armature = bpy.data.objects.get(char_profile["ped_name"])
    if not ped_armature:
        ped_armature = next(
            (obj_item for obj_item in bpy.data.objects if obj_item.type == "ARMATURE"),
            None,
        )
    if not ped_armature:
        raise RuntimeError(
            i18n.translate("michael.build.skeleton_load_failed", path=cli_args.skeleton_yft)
        )

    valid_gtav_bones = {
        "SKEL_ROOT",
        "SKEL_Pelvis",
        "SKEL_Spine_Root",
        "SKEL_Spine0",
        "SKEL_Spine1",
        "SKEL_Spine2",
        "SKEL_Spine3",
        "SKEL_Neck_1",
        "SKEL_Head",
        "FACIAL_facialRoot",
        "FACIAL_jaw",
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
    }
    for side_code in ["L", "R"]:
        for finger_idx in range(5):
            for sub_idx in range(3):
                valid_gtav_bones.add(f"SKEL_{side_code}_Finger{finger_idx}{sub_idx}")
    valid_gtav_bones.update(hand_skeleton_helper.EXTRA_ARM_HELPER_BONES)
    eye_blink_mode = eye_blink_helper.resolve_effective_eye_blink_mode(
        getattr(cli_args, "eye_blink", None), target_cfg
    )
    eye_blink_strength = eye_blink_helper.resolve_eye_blink_strength(
        getattr(cli_args, "eye_blink_strength", None),
        target_cfg,
        avatar_id="shinano_er",
    )
    mouth_open_strength = eye_blink_helper.resolve_mouth_open_strength(
        getattr(cli_args, "mouth_open_strength", None),
        target_cfg,
    )
    blink_anchors = (
        eye_blink_helper.capture_eyelid_blink_anchors(ped_armature)
        if eye_blink_mode != "off"
        else {}
    )
    valid_gtav_bones, stripped_hand_leaves = eye_blink_helper.prepare_ydd_blink_bone_set(
        valid_gtav_bones,
        enable_eye_blink=(eye_blink_mode != "off"),
        custom_bone_count=physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED,
    )
    if stripped_hand_leaves > 0:
        print(i18n.translate("eye_blink.ydd_bones_trimmed", stripped=stripped_hand_leaves))
    valid_gtav_bones.update(physbone_helper.NEKO_MIMI_CUSTOM_BONES)
    valid_gtav_bones.update(physbone_helper.MICHAEL_ER_CUSTOM_BONES)

    bpy.context.view_layer.objects.active = ped_armature
    bpy.ops.object.mode_set(mode="EDIT")
    for edit_bone in list(ped_armature.data.edit_bones):
        if edit_bone.name not in valid_gtav_bones:
            ped_armature.data.edit_bones.remove(edit_bone)
    bpy.ops.object.mode_set(mode="OBJECT")

    for extra_obj in list(bpy.data.objects):
        if extra_obj != ped_armature:
            bpy.data.objects.remove(extra_obj)

    # 3. Import the 4 avatar & accessory FBX packages
    imported_armatures = []

    print(i18n.translate("michael.build.importing_shinano", path=cli_args.shinano_fbx))
    bpy.ops.import_scene.fbx(filepath=cli_args.shinano_fbx)
    arm_base = next(
        (
            scene_obj
            for scene_obj in bpy.data.objects
            if scene_obj.type == "ARMATURE"
            and scene_obj != ped_armature
            and scene_obj not in imported_armatures
        ),
        None,
    )
    if arm_base:
        imported_armatures.append(arm_base)

    print(i18n.translate("michael.build.importing_outfit", path=cli_args.outfit_fbx))
    bpy.ops.import_scene.fbx(filepath=cli_args.outfit_fbx)
    arm_outfit = next(
        (
            scene_obj
            for scene_obj in bpy.data.objects
            if scene_obj.type == "ARMATURE"
            and scene_obj != ped_armature
            and scene_obj not in imported_armatures
        ),
        None,
    )
    if arm_outfit:
        imported_armatures.append(arm_outfit)

    print(i18n.translate("michael.build.importing_watch", path=cli_args.watch_fbx))
    bpy.ops.import_scene.fbx(filepath=cli_args.watch_fbx)
    arm_watch = next(
        (
            scene_obj
            for scene_obj in bpy.data.objects
            if scene_obj.type == "ARMATURE"
            and scene_obj != ped_armature
            and scene_obj not in imported_armatures
        ),
        None,
    )
    if arm_watch:
        imported_armatures.append(arm_watch)

    # Import Sky Blue custom nails (NakoNail via Modular Avatar / manifest) BEFORE Neko Tied Bob hair
    # so NakoNail's "Ribbon" does not collide with Neko Tied Bob's "Ribbon".
    nails_fbx_path = ""
    nails_manifest_file = Path(os.path.abspath(cli_args.texture_dir)) / "nails_manifest.json"
    if nails_manifest_file.is_file():
        try:
            nails_fbx_path = str(json.loads(nails_manifest_file.read_text(encoding="utf-8")).get("fbx_path", ""))
        except Exception:
            nails_fbx_path = ""
    if not nails_fbx_path or not os.path.isfile(nails_fbx_path):
        unity_assets_cfg = Path(str(cli_args.shinano_fbx)).parent.parent.parent
        fallback_nail_fbx = unity_assets_cfg / "Panda Shop" / "NakoNail" / "Fbx" / "Nail_Nako_Sinano.fbx"
        if fallback_nail_fbx.is_file():
            nails_fbx_path = str(fallback_nail_fbx)

    arm_nails = None
    has_nako_nails = False
    if nails_fbx_path and os.path.isfile(nails_fbx_path):
        pre_nail_objs = set(bpy.data.objects)
        print(f"[NakoNail] Importing custom nails FBX: {nails_fbx_path}")
        bpy.ops.import_scene.fbx(filepath=nails_fbx_path)
        new_nail_objs = [obj for obj in bpy.data.objects if obj not in pre_nail_objs]
        for nobj in new_nail_objs:
            if nobj.type == "ARMATURE":
                arm_nails = nobj
                imported_armatures.append(nobj)
            elif nobj.type == "MESH":
                if nobj.name == "Ribbon":
                    nobj.name = "Nail_Ribbon"
                elif nobj.name == "neko":
                    nobj.name = "Nail_neko"
                has_nako_nails = True

    # Load optional Unity scene overrides (defaults strictly to 1.0 when blank/absent)
    target_cfg = getattr(cli_args, "target_cfg", None) or project_paths.get_character_paths(
        cli_args.target_character,
        avatar_override="shinano_er",
    )
    unity_scene_override = getattr(cli_args, "unity_scene", None)
    unity_avatar_override = getattr(cli_args, "unity_avatar_name", None)
    effective_cfg = dict(target_cfg)
    if unity_scene_override is not None:
        effective_cfg["unity_scene"] = unity_scene_override
    if unity_avatar_override is not None:
        effective_cfg["unity_avatar_name"] = unity_avatar_override

    unity_config = unity_scene_helper.load_unity_avatar_from_cfg(
        effective_cfg,
        i18n_module=i18n,
        character_hints=("shinano", "reunion"),
    )
    hair_spec_input = getattr(cli_args, "hair", None)
    if hair_spec_input is None:
        if getattr(cli_args, "cli_hair_fbx_explicit", False) and getattr(
            cli_args, "hair_fbx", None
        ):
            hair_spec_input = cli_args.hair_fbx
        else:
            hair_spec_input = (
                str(effective_cfg.get("custom_hair", "")).strip()
                or str(effective_cfg.get("fbx_hair", "")).strip()
                or "auto"
            )
    hair_mat_override = getattr(cli_args, "hair_mat", None) or str(
        effective_cfg.get("hair_mat", "") or ""
    )
    hair_tex_override = getattr(cli_args, "hair_tex", None) or str(
        effective_cfg.get("hair_tex", "") or ""
    )
    hair_spec = unity_hair_helper.resolve_custom_hair_spec(
        hair_spec_input=hair_spec_input,
        unity_scene=effective_cfg.get("unity_scene"),
        unity_avatar_name=effective_cfg.get("unity_avatar_name", ""),
        unity_assets_root=effective_cfg.get("unity_assets_root"),
        hair_mat_override=hair_mat_override,
        hair_tex_override=hair_tex_override,
        is_calibrated_er_default=True,
    )
    hair_mode = hair_spec.get("mode", "default")
    hair_reason = hair_spec.get("reason") or hair_spec.get("source_input", "") or hair_mode
    is_calibrated_neko = (hair_mode == "custom") and bool(
        hair_spec.get("is_neko_bob_calibrated", False)
    )
    is_arbitrary_custom_hair = (hair_mode == "custom") and (not is_calibrated_neko)
    custom_hair_primary_fbx = str(
        hair_spec.get("primary_fbx") or getattr(cli_args, "hair_fbx", "") or ""
    )

    arm_hair = None
    if is_calibrated_neko and custom_hair_primary_fbx:
        print(
            i18n.translate(
                "unity_scene.hair_custom_active",
                reason=hair_reason,
                path=custom_hair_primary_fbx,
            )
        )
        print(i18n.translate("michael.build.importing_hair", path=custom_hair_primary_fbx))
        bpy.ops.import_scene.fbx(filepath=custom_hair_primary_fbx)
        arm_hair = next(
            (
                scene_obj
                for scene_obj in bpy.data.objects
                if scene_obj.type == "ARMATURE"
                and scene_obj != ped_armature
                and scene_obj not in imported_armatures
            ),
            None,
        )
        if arm_hair:
            imported_armatures.append(arm_hair)
    elif not is_arbitrary_custom_hair:
        print(i18n.translate("unity_scene.hair_fallback_default", reason=hair_reason))

    # Apply Unity Armature scale, GTA V A-pose (-55 deg), and Unity bone pose scales.
    # Standalone asset armatures (arm_hair, arm_watch) keep their rest transforms here
    # because their align transforms explicitly apply target position/scale in vertex space.
    arm_angle_rad = -math.radians(abs(char_profile["arm_pose_degrees"]))
    armature_override_scale = unity_config.get("armature_scale", (1.0, 1.0, 1.0))
    pose_scaled_armatures = {arm_obj for arm_obj in (arm_base, arm_outfit, arm_nails) if arm_obj}
    for arm_obj in imported_armatures:
        if arm_obj != arm_hair:
            arm_obj.scale = (
                arm_obj.scale.x * armature_override_scale[0],
                arm_obj.scale.y * armature_override_scale[1],
                arm_obj.scale.z * armature_override_scale[2],
            )
        bpy.context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode="POSE")
        for left_arm_name in ["Upper_arm.L", "UpperArm.L", "LeftUpperArm"]:
            if left_arm_name in arm_obj.pose.bones:
                pose_bone = arm_obj.pose.bones[left_arm_name]
                pose_bone.rotation_mode = "XYZ"
                pose_bone.rotation_euler = (arm_angle_rad, 0.0, 0.0)
        for right_arm_name in ["Upper_arm.R", "UpperArm.R", "RightUpperArm"]:
            if right_arm_name in arm_obj.pose.bones:
                pose_bone = arm_obj.pose.bones[right_arm_name]
                pose_bone.rotation_mode = "XYZ"
                pose_bone.rotation_euler = (arm_angle_rad, 0.0, 0.0)
        if arm_obj in pose_scaled_armatures:
            unity_scene_helper.apply_unity_bone_scales_to_pose(arm_obj, unity_config)
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()

    hair_root_rest_pos = None
    if is_calibrated_neko:
        if not arm_hair or "Hair Root" not in arm_hair.data.bones:
            raise RuntimeError(i18n.translate("michael.build.hair_root_missing"))
        hair_root_rest_pos = (
            arm_hair.matrix_world @ arm_hair.data.bones["Hair Root"].head_local
        ).copy()

    watch_align_scale = unity_scene_helper.get_uniform_scale(
        unity_config, ("Pocket Watch_Root", "Pocket Watch"), default_scale=1.0
    )
    watch_transform_matrix = compute_pocket_watch_align_matrix(
        arm_outfit,
        arm_watch,
        watch_scale=watch_align_scale,
        armature_scale=armature_override_scale,
    )

    # 4. Load original Shinano FBX facial normals
    fbx_face_normals = load_fbx_face_loop_normals(cli_args.shinano_fbx)
    if fbx_face_normals:
        print(i18n.translate("michael.build.fbx_normals_loaded", count=len(fbx_face_normals)))

    # 5-6B. Resolve and apply blendshapes (Body, Body_base, Outfit, Watch, Hair)
    if getattr(cli_args, "face_anim", None):
        effective_cfg["face_anim"] = cli_args.face_anim
    neko_hair_mesh_names = (
        "Bangs",
        "Top Back",
        "Under Side",
        "Back",
        "Side Bangs",
        "Side",
        "In Hair",
        "Ribbon",
        "Ears",
        "_Pin.Back",
        "_Pin.R",
        "_Pin.L2",
        "_Halo",
    )
    blendshape_fbx_paths = []
    for fbx_item in (
        cli_args.shinano_fbx,
        cli_args.outfit_fbx,
        cli_args.watch_fbx,
        *(list(hair_spec.get("all_fbxs", [])) if hair_mode == "custom" else ()),
        cli_args.hair_fbx if is_calibrated_neko else "",
    ):
        if fbx_item and fbx_item not in blendshape_fbx_paths:
            blendshape_fbx_paths.append(fbx_item)
    er_excluded_fbx_meshes = (
        blendshape_helper.SHINANO_CASUAL_EXTRA_MESHES[:6]
        if hair_mode == "default"
        else blendshape_helper.SHINANO_CASUAL_EXTRA_MESHES
    )
    blendshape_resolution = blendshape_helper.resolve_character_blendshapes(
        effective_cfg,
        fbx_paths=blendshape_fbx_paths,
        character_hints=("shinano", "reunion"),
        default_face_mesh="Body",
        override_source=getattr(cli_args, "blendshapes_source", None),
        override_cfg_path=getattr(cli_args, "blendshapes_cfg", None),
        override_unity_scene=getattr(cli_args, "unity_scene", None),
        override_avatar_name=getattr(cli_args, "unity_avatar_name", None),
        override_face_anim=getattr(cli_args, "face_anim", None),
        save_cfg_path=getattr(cli_args, "save_blendshapes_cfg", None),
        exclude_meshes_when_no_custom_hair=(not is_calibrated_neko),
        custom_hair_mesh_names=neko_hair_mesh_names,
        fbx_excluded_meshes=er_excluded_fbx_meshes,
    )
    resolved_mesh_weights = blendshape_resolution["mesh_weights"]
    total_weight_entries = sum(
        len(weights_map) for weights_map in resolved_mesh_weights.values()
    )
    source_detail = (
        blendshape_resolution.get("cfg_path")
        or blendshape_resolution.get("unity_scene")
        or blendshape_resolution.get("face_anim")
        or "-"
    )
    print(
        i18n.translate(
            "blendshapes.loaded_source",
            source=blendshape_resolution["source_used"],
            meshes=len(resolved_mesh_weights),
            weights=total_weight_entries,
            detail=source_detail,
        )
    )
    if blendshape_resolution.get("saved_cfg_path"):
        print(
            i18n.translate(
                "blendshapes.saved_cfg",
                path=blendshape_resolution["saved_cfg_path"],
            )
        )

    applied_scene_summary = blendshape_helper.apply_blendshapes_to_blender_scene(
        bpy,
        resolved_mesh_weights,
        exclude_meshes=() if hair_mode == "custom" else neko_hair_mesh_names,
        lr_symmetry_meshes=(),
        reset_unlisted=True,
    )
    for mesh_label, counts_pair in applied_scene_summary.items():
        print(
            i18n.translate(
                "michael.build.applied_shape_keys",
                count=counts_pair[0],
                name=mesh_label,
            )
        )

    bpy.context.view_layer.update()

    physbone_fbx_paths = [
        cli_args.shinano_fbx,
        cli_args.outfit_fbx,
        cli_args.watch_fbx,
        cli_args.hair_fbx,
    ]
    if hair_mode == "custom":
        for extra_hair_fbx in hair_spec.get("all_fbxs", []):
            if extra_hair_fbx and extra_hair_fbx not in physbone_fbx_paths:
                physbone_fbx_paths.append(extra_hair_fbx)
    pb_resolution = physbone_helper.resolve_character_physbones(
        effective_cfg,
        fbx_paths=physbone_fbx_paths,
        character_hints=("shinano", "reunion"),
        override_source=getattr(cli_args, "physbones_source", None),
        override_cfg_path=getattr(cli_args, "physbones_cfg", None),
        override_unity_scene=getattr(cli_args, "unity_scene", None),
        override_avatar_name=getattr(cli_args, "unity_avatar_name", None),
        override_marshmallow=getattr(cli_args, "physbones_marshmallow", None),
        save_cfg_path=getattr(cli_args, "save_physbones_cfg", None),
        verbose=True,
    )
    valid_gtav_bones.update(pb_resolution.get("custom_bones") or ())
    pb_detail = pb_resolution.get("cfg_path") or pb_resolution.get("unity_scene") or "-"
    print(
        i18n.translate(
            "physbones.loaded_source",
            source=pb_resolution["source_used"],
            chains=len(pb_resolution["chain_specs"]),
            bones=len(pb_resolution["custom_bones"]),
            detail=pb_detail,
        ),
        flush=True,
    )
    if pb_resolution.get("saved_cfg_path"):
        print(
            i18n.translate("physbones.saved_cfg", path=pb_resolution["saved_cfg_path"]),
            flush=True,
        )

    # Extract deformed cranial/head reference before optionally removing default hair
    skull_ref = blender_hair_helper.extract_skull_reference(
        bpy,
        arm_base,
        [bpy.data.objects.get("Body")],
        [
            bpy.data.objects.get(hair_item)
            for hair_item in ("Hair_base", "Hair_back", "Hair_bang", "Hair_side")
        ],
    )

    if (not is_calibrated_neko) and hair_mode in ("custom", "none"):
        blender_hair_helper.remove_default_hair_meshes(
            bpy,
            "shinano_er",
            remove_shinano_ears_if_replaced=True,
        )

    # 7. Active mesh inventory and 4x2 Atlas quadrant mapping
    active_mesh_configs = {
        "Body": {"atlas_col": 0, "atlas_row": 1, "shrink_cull": False},
        "Body_base": {"atlas_col": 1, "atlas_row": 1, "shrink_cull": True},
        "UN1_Shirt": {"atlas_col": 2, "atlas_row": 1, "shrink_cull": False},
        "UN1_Skirt": {"atlas_col": 2, "atlas_row": 1, "shrink_cull": False},
        "UN1_ChestRibbon": {"atlas_col": 2, "atlas_row": 1, "shrink_cull": False},
        "UN1_Choker": {"atlas_col": 2, "atlas_row": 1, "shrink_cull": False},
        "UN2_Corset": {"atlas_col": 3, "atlas_row": 1, "shrink_cull": False},
        # UN2_Beret disabled by user preference
        "UN2_Shoes": {"atlas_col": 3, "atlas_row": 1, "shrink_cull": False},
        "UN2_Stocking": {"atlas_col": 3, "atlas_row": 1, "shrink_cull": False},
        "UN3_Bag": {"atlas_col": 0, "atlas_row": 0, "shrink_cull": False},
        "UN3_Glasses": {"atlas_col": 0, "atlas_row": 0, "shrink_cull": False},
        "UN3_WaistChain": {"atlas_col": 0, "atlas_row": 0, "shrink_cull": False},
        "Pocket Watch": {"atlas_col": 1, "atlas_row": 0, "shrink_cull": False},
    }

    if is_calibrated_neko:
        active_mesh_configs.update(
            {
                "Bangs": {
                    "atlas_col": 2,
                    "atlas_row": 0,
                    "shrink_cull": False,
                    "vtoon_bucket": "alpha",
                    "double_sided": True,
                },
                "Top Back": {
                    "atlas_col": 2,
                    "atlas_row": 0,
                    "shrink_cull": False,
                    "vtoon_bucket": "cutout",
                    "double_sided": True,
                },
                "Under Side": {
                    "atlas_col": 2,
                    "atlas_row": 0,
                    "shrink_cull": False,
                    "vtoon_bucket": "cutout",
                    "double_sided": True,
                },
                "Back": {
                    "atlas_col": 2,
                    "atlas_row": 0,
                    "shrink_cull": False,
                    "vtoon_bucket": "cutout",
                    "double_sided": True,
                },
                "Side Bangs": {
                    "atlas_col": 2,
                    "atlas_row": 0,
                    "shrink_cull": False,
                    "vtoon_bucket": "alpha",
                    "double_sided": True,
                },
                "Side": {
                    "atlas_col": 2,
                    "atlas_row": 0,
                    "shrink_cull": False,
                    "vtoon_bucket": "cutout",
                    "double_sided": True,
                },
                "In Hair": {
                    "atlas_col": 2,
                    "atlas_row": 0,
                    "shrink_cull": False,
                    "vtoon_bucket": "cutout",
                    "double_sided": True,
                },
                "Ribbon": {
                    "u_offset": 0.940,
                    "v_offset": 0.065,
                    "u_scale": 0.026,
                    "v_scale": 0.056,
                    "clamp_v": True,
                    "shrink_cull": False,
                    "vtoon_bucket": "ped",
                    "double_sided": True,
                },
                "Ears": {
                    "atlas_col": 2,
                    "atlas_row": 0,
                    "shrink_cull": False,
                    "vtoon_bucket": "cutout",
                    "double_sided": True,
                },
                "_Pin.Back": {
                    "u_offset": 0.875,
                    "v_offset": 0.25,
                    "u_scale": 0.125,
                    "v_scale": 0.25,
                    "shrink_cull": False,
                },
                "_Pin.R": {
                    "u_offset": 0.75,
                    "v_offset": 0.0,
                    "u_scale": 0.125,
                    "v_scale": 0.25,
                    "clamp_v": True,
                    "shrink_cull": False,
                },
                "_Pin.L2": {
                    "u_offset": 0.75,
                    "v_offset": 0.0,
                    "u_scale": 0.125,
                    "v_scale": 0.25,
                    "clamp_v": True,
                    "shrink_cull": False,
                },
                "_Halo": {
                    "u_offset": 0.75,
                    "v_offset": 0.25,
                    "u_scale": 0.125,
                    "v_scale": 0.25,
                    "shrink_cull": False,
                },
            }
        )
    elif is_arbitrary_custom_hair:
        print(
            i18n.translate(
                "unity_scene.hair_custom_active",
                reason=hair_reason,
                path=custom_hair_primary_fbx or hair_spec.get("source_input", ""),
            )
        )
        import_res = blender_hair_helper.import_and_filter_custom_hair_meshes(
            bpy,
            mathutils,
            hair_spec,
            unity_config=unity_config,
            resolved_mesh_weights=resolved_mesh_weights,
        )
        custom_hair_objs = import_res["meshes"]
        imported_armatures.extend(import_res["armatures"])
        eff_hair_scale = float(
            cli_args.hair_scale
            if getattr(cli_args, "hair_scale", None) is not None
            else (target_cfg.get("hair_scale") or 1.0)
        )
        eff_hair_offset = blender_hair_helper.parse_offset_triple(
            cli_args.hair_offset
            if getattr(cli_args, "hair_offset", None) is not None
            else target_cfg.get("hair_offset")
        )
        blender_hair_helper.align_custom_hair_to_avatar(
            bpy,
            mathutils,
            custom_hair_objs,
            skull_ref,
            hair_spec,
            import_res,
            hair_scale_override=eff_hair_scale,
            hair_offset_override=eff_hair_offset,
        )
        use_double_cell = len(hair_spec.get("materials", [])) >= 2
        er_quad_w = 1024 if use_double_cell else 512
        er_quad_uv = (0.5, 0.0, 0.5, 0.5) if use_double_cell else (0.5, 0.0, 0.25, 0.5)
        loaded_manifest = unity_hair_helper.load_custom_hair_manifest(cli_args.texture_dir)
        if (
            loaded_manifest is None
            or loaded_manifest.get("mode") != "custom"
            or loaded_manifest.get("source_input") != hair_spec.get("source_input")
        ):
            loaded_manifest = unity_hair_helper.build_inmemory_manifest_fallback(
                hair_spec,
                quad_size=(er_quad_w, 512),
                quad_uv_rect=er_quad_uv,
            )
        body_ref_obj = bpy.data.objects.get("Body")
        body_uv_name = (
            body_ref_obj.data.uv_layers[0].name
            if body_ref_obj and body_ref_obj.data.uv_layers
            else "UVMap"
        )
        blender_hair_helper.remap_custom_hair_uvs(
            custom_hair_objs,
            loaded_manifest,
            fallback_rect=er_quad_uv,
            target_uv_name=body_uv_name,
        )
        blender_hair_helper.retarget_custom_hair_weights_to_head(
            custom_hair_objs, "SKEL_Head"
        )
        for hair_obj in custom_hair_objs:
            low_hname = hair_obj.name.lower()
            is_bang_alpha = any(tok in low_hname for tok in ("bang", "front", "alpha", "trans"))
            active_mesh_configs[hair_obj.name] = {
                "uv_prepacked": True,
                "is_custom_hair": True,
                "shrink_cull": False,
                "vtoon_bucket": "alpha" if is_bang_alpha else "cutout",
                "double_sided": True,
            }
        print(
            i18n.translate("common.hair_aligned_summary", count=len(custom_hair_objs))
        )
    elif hair_mode == "none":
        print(i18n.translate("common.hair_none_active"))
    else:
        active_mesh_configs.update(
            {
                "Hair_base": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False, "vtoon_bucket": "cutout", "double_sided": True},
                "Hair_bang": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False, "vtoon_bucket": "alpha", "double_sided": True},
                "Hair_back": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False, "vtoon_bucket": "cutout", "double_sided": True},
                "Hair_side": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False, "vtoon_bucket": "alpha", "double_sided": True},
                "Other_ear": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False, "vtoon_bucket": "cutout", "double_sided": True},
            }
        )

    if has_nako_nails:
        nail_u_specs = {
            "Nail_L": {"u_offset": 0.875, "v_offset": 0.0, "u_scale": 0.0625, "v_scale": 0.25, "clamp_v": True, "shrink_cull": False, "vtoon_bucket": "ped", "double_sided": True},
            "Nail_R": {"u_offset": 0.875, "v_offset": 0.0, "u_scale": 0.0625, "v_scale": 0.25, "clamp_v": True, "shrink_cull": False, "vtoon_bucket": "ped", "double_sided": True},
            "Nail_Ribbon": {"u_offset": 0.9375, "v_offset": 0.125, "u_scale": 0.0625, "v_scale": 0.125, "clamp_v": True, "shrink_cull": False, "vtoon_bucket": "ped"},
            "Nail_neko": {"u_offset": 0.972, "v_offset": 0.068, "u_scale": 0.022, "v_scale": 0.052, "shrink_cull": False, "vtoon_bucket": "ped"},
        }
        for nail_key, nail_cfg in nail_u_specs.items():
            if bpy.data.objects.get(nail_key) is not None:
                active_mesh_configs[nail_key] = nail_cfg

    if is_calibrated_neko:
        import_and_place_er_earrings(
            bpy,
            bmesh,
            mathutils,
            cli_args.hair_fbx,
            arm_base,
            unity_config,
            active_mesh_configs,
        )

    scale_factor, vertical_offset = unity_scene_helper.compute_gtav_height_mapping(
        bpy,
        unity_config,
        active_mesh_configs.keys(),
        ("Body", "Body_base", "UN2_Shoes"),
        char_profile["target_z_min"],
        char_profile["target_z_max"],
        0.106,
        1.132,
    )

    depsgraph_eval = bpy.context.evaluated_depsgraph_get()
    depsgraph_eval = bpy.context.evaluated_depsgraph_get()
    # Precompute FACIAL_jaw weights derived from the vrc.v_aa shape key
    orig_body_obj = bpy.data.objects.get("Body")
    body_jaw_mask = eye_blink_helper.extract_facial_jaw_weights(
        orig_body_obj, delta_z_threshold=-0.0005
    )
    body_jaw_weights = (
        body_jaw_mask
        if abs(mouth_open_strength - eye_blink_helper.DEFAULT_MOUTH_OPEN_STRENGTH) < 1e-6
        else eye_blink_helper.extract_facial_jaw_weights(
            orig_body_obj, mouth_open_strength=mouth_open_strength, delta_z_threshold=-0.0005
        )
    )
    if body_jaw_weights:
        print(
            i18n.translate(
                "michael.build.jaw_weights_mapped", count=len(body_jaw_weights)
            )
        )

    blink_rig_data = eye_blink_helper.extract_body_eyelid_blink_rig_data(
        bpy,
        orig_body_obj,
        eye_blink_mode=eye_blink_mode,
        shape_weights=resolved_mesh_weights.get("Body", {}),
        exclude_vert_indices=body_jaw_mask.keys(),
    )
    if blink_rig_data.get("enabled"):
        print(
            i18n.translate(
                "eye_blink.applied",
                key=blink_rig_data["shape_key"],
                verts=len(blink_rig_data["weights_by_orig_vert"]),
                left_mm=blink_rig_data["max_disp_l"] * 1000.0,
                right_mm=blink_rig_data["max_disp_r"] * 1000.0,
            )
        )
    else:
        print(
            i18n.translate(
                "eye_blink.skipped",
                reason=blink_rig_data.get("reason", "disabled"),
            )
        )


    processed_objects, preserved_body_normals = process_michael_er_mesh_inventory(
        bpy,
        bmesh,
        mathutils,
        active_mesh_configs,
        depsgraph_eval,
        scale_factor,
        vertical_offset,
        is_calibrated_neko,
        arm_base,
        hair_root_rest_pos,
        unity_config,
        watch_transform_matrix,
        fbx_face_normals,
        pb_resolution,
        body_jaw_weights,
        blink_rig_data,
    )

    if arm_base is None:
        raise RuntimeError(i18n.translate("michael.build.base_armature_missing"))
    bone_world_targets = hand_skeleton_helper.extract_avatar_arm_hand_targets(
        arm_base, scale_factor, vertical_offset
    )
    relocated_armature_bones = hand_skeleton_helper.relocate_blender_armature_bones(
        ped_armature, bone_world_targets
    )
    print(
        i18n.translate("michael.build.bones_relocated", count=relocated_armature_bones)
    )

    bpy.context.view_layer.update()
    custom_ear_bones = []
    physbone_chain_records = []

    hair_bones_ci = (
        {pose_item.name.lower(): pose_item for pose_item in arm_hair.pose.bones}
        if is_calibrated_neko and arm_hair is not None and hair_root_rest_pos is not None
        else {}
    )
    outfit_bones_ci = (
        {pose_item.name.lower(): pose_item for pose_item in arm_outfit.pose.bones}
        if arm_outfit is not None
        else {}
    )
    watch_bones_ci = (
        {pose_item.name.lower(): pose_item for pose_item in arm_watch.pose.bones}
        if arm_watch is not None
        else {}
    )
    base_bones_ci = (
        {pose_item.name.lower(): pose_item for pose_item in arm_base.pose.bones}
        if arm_base is not None
        else {}
    )

    map_hair_world_fn = None
    if hair_bones_ci and hair_root_rest_pos is not None:
        baseline_neck_scale = 0.9
        baseline_hair_scale = 1.08696
        baseline_head_to_hair_offset = mathutils.Vector((0.000653, -0.002032, 0.074354))
        neko_target_hair_root = mathutils.Vector((0.000653, 0.010790, 1.202636))
        custom_hair_node_scale = unity_scene_helper.get_uniform_scale(
            unity_config,
            ("Neko BoB_Lime", "Neko Tied Bob hair", "Hair Root", "Hair_root"),
            default_scale=1.0,
        )
        head_pose_bone = arm_base.pose.bones.get("Head") if arm_base else None
        if head_pose_bone is not None and arm_base is not None:
            head_world_scale = (arm_base.matrix_world @ head_pose_bone.matrix).to_scale().x
            head_scale_ratio = head_world_scale / baseline_neck_scale
            head_world_pos = arm_base.matrix_world @ head_pose_bone.head
            neko_target_hair_root = head_world_pos + (
                baseline_head_to_hair_offset * head_scale_ratio
            )
            neko_hair_scale = (
                baseline_hair_scale * custom_hair_node_scale * head_scale_ratio
            )
        else:
            neko_hair_scale = baseline_hair_scale * custom_hair_node_scale
        neko_hair_rot_matrix = mathutils.Euler((-0.001953, 0.0, 0.0), "XYZ").to_matrix()

        def map_hair_world_mat(src_bone_pose) -> mathutils.Matrix:
            fbx_world = arm_hair.matrix_world @ src_bone_pose.matrix
            rel_pt = (fbx_world.translation - hair_root_rest_pos) * neko_hair_scale
            aligned_pt = neko_target_hair_root + (neko_hair_rot_matrix @ rel_pt)
            gtav_pos = mathutils.Vector(
                (
                    aligned_pt.x * scale_factor,
                    aligned_pt.y * scale_factor,
                    aligned_pt.z * scale_factor + vertical_offset,
                )
            )
            gtav_rot_3x3 = (neko_hair_rot_matrix @ fbx_world.to_3x3().normalized()).normalized()
            out_mat = gtav_rot_3x3.to_4x4()
            out_mat.translation = gtav_pos
            return out_mat

        map_hair_world_fn = map_hair_world_mat

    hat_pivot = mathutils.Vector((0.0, 0.0314, 1.2534))
    hat_rot_matrix = mathutils.Matrix.Rotation(math.radians(-11.464), 4, "X")
    hat_pos_delta = mathutils.Vector((0.0, 0.02655, 0.01388))

    def _to_gtav_world_mat(fbx_world):
        gtav_pos = mathutils.Vector(
            (
                fbx_world.translation.x * scale_factor,
                fbx_world.translation.y * scale_factor,
                fbx_world.translation.z * scale_factor + vertical_offset,
            )
        )
        gtav_rot = fbx_world.to_quaternion().to_matrix().to_4x4()
        gtav_rot.translation = gtav_pos
        return gtav_rot

    hair_bone_prefixes = ("ear.", "halo", "aho", "bangs.", "side.", "back.", "ribbon.00")

    def resolve_michael_er_world_mat(src_bone_name):
        src_low = src_bone_name.strip().lower()
        if map_hair_world_fn is not None and src_low.startswith(hair_bone_prefixes) and src_low in hair_bones_ci:
            return map_hair_world_fn(hair_bones_ci[src_low])
        if src_low.startswith("pocket watch") and src_low in watch_bones_ci and arm_watch is not None:
            fbx_world = watch_transform_matrix @ (arm_watch.matrix_world @ watch_bones_ci[src_low].matrix)
            return _to_gtav_world_mat(fbx_world)
        if src_low in outfit_bones_ci and arm_outfit is not None:
            fbx_world = (arm_outfit.matrix_world @ outfit_bones_ci[src_low].matrix).copy()
            if src_low.startswith(("un_hatroot", "un_hat_")):
                rel_pos = fbx_world.translation - hat_pivot
                rotated_3x3 = (hat_rot_matrix.to_3x3() @ fbx_world.to_3x3().normalized()).normalized()
                adj_mat = rotated_3x3.to_4x4()
                adj_mat.translation = hat_pivot + (hat_rot_matrix @ rel_pos) + hat_pos_delta
                fbx_world = adj_mat
            return _to_gtav_world_mat(fbx_world)
        if src_low in base_bones_ci and arm_base is not None:
            fbx_world = arm_base.matrix_world @ base_bones_ci[src_low].matrix
            return _to_gtav_world_mat(fbx_world)
        return None

    ped_world_matrices = {
        bone_item.name: (ped_armature.matrix_world @ bone_item.matrix_local).copy()
        for bone_item in ped_armature.data.bones
    }
    custom_ear_bones, physbone_chain_records = physbone_helper.build_dynamic_physbone_chains(
        ped_armature=ped_armature,
        chain_specs=pb_resolution["chain_specs"],
        parent_map=pb_resolution["parent_map"],
        chain_cfgs=pb_resolution["chains"],
        source_world_mat_fn=resolve_michael_er_world_mat,
        ped_world_matrices=ped_world_matrices,
        default_limit_rotation=(14.12, 0.0, 0.0),
    )
    if custom_ear_bones:
        injected_pb_count = hand_skeleton_helper.inject_custom_bones_into_blender_armature(
            ped_armature,
            custom_ear_bones,
            bone_tag_fn=physbone_helper.compute_gtav_bone_tag,
        )
        valid_gtav_bones.update(item["name"] for item in custom_ear_bones)
        print(
            f"[PhysBones] Injected {injected_pb_count} Eternal Reunion bones into Blender armature ({len(physbone_chain_records)} chains)",
            flush=True,
        )

    ped_model_name = str(char_profile["ped_name"])
    custom_blink_bones = []
    blink_profiles_to_merge = []
    if blink_rig_data.get("enabled"):
        custom_blink_bones = eye_blink_helper.build_blink_custom_bone_specs(
            ped_armature,
            blink_anchors=blink_anchors,
            blink_rig_data=blink_rig_data,
            world_scale=scale_factor,
            world_z_offset=vertical_offset,
        )
        if custom_blink_bones:
            hand_skeleton_helper.inject_custom_bones_into_blender_armature(
                ped_armature,
                custom_blink_bones,
                bone_tag_fn=physbone_helper.compute_gtav_bone_tag,
            )
            valid_gtav_bones.update(item["name"] for item in custom_blink_bones)
        bpy.context.view_layer.update()
        scaled_blink_deltas = eye_blink_helper.scale_eye_blink_deltas(
            blink_rig_data, scale_factor
        )
        blink_prof = eye_blink_helper.build_blink_profile_for_ped(
            ped_armature,
            ped_model_name,
            scaled_blink_deltas,
            delta_rotations_world=blink_rig_data.get("rot_quats_world"),
            enabled=True,
            max_blink=eye_blink_strength,
        )
        if blink_prof is not None:
            blink_profiles_to_merge.append(blink_prof)

    # 8. Remove source armatures and raw meshes
    for old_obj in list(bpy.data.objects):
        if old_obj != ped_armature and old_obj not in processed_objects:
            bpy.data.objects.remove(old_obj)

    # 9. Keep total unified polygon budget safely under RPF7's 16 MiB entry ceiling, then join
    ped_damage_helper.enforce_ped_rpf7_poly_budget(
        bpy,
        processed_objects,
        enable_blood_decals=bool(getattr(cli_args, "blood_decals", True)),
    )
    apply_deferred_double_sided_backfaces(
        processed_objects,
        blender_hair_helper,
        normal_offset=0.00035,
    )

    # 10. Create multi-shader VToon materials (ped / hair cutout / forward bangs alpha) BEFORE joining
    texture_dir = os.path.abspath(cli_args.texture_dir)
    atlas_image_path = os.path.join(texture_dir, cli_args.atlas_png)
    normal_image_path = os.path.join(texture_dir, cli_args.normal_png)
    spec_image_path = os.path.join(texture_dir, cli_args.spec_png)

    atlas_image = bpy.data.images.load(atlas_image_path)
    flat_normal_image = bpy.data.images.load(normal_image_path)
    specular_image = bpy.data.images.load(spec_image_path)

    enable_blood_decals = bool(getattr(cli_args, "blood_decals", True))
    ped_material = ped_damage_helper.create_ped_material(
        create_shader,
        "shinano_er_mat",
        enable_blood_decals=enable_blood_decals,
        diffuse_image=atlas_image,
        bump_image=flat_normal_image,
        spec_image=specular_image,
        bumpiness=0.0,
        specular_intensity=0.0,
        specular_falloff=1.0,
        specular_fresnel=ped_damage_helper.DEFAULT_ANIME_SPECULAR_FRESNEL,
        detail_settings=(0.0, 0.0, 0.0),
        stubble_control=(0.0, 0.0),
        um_global_params=(0.0, 0.0, 0.0, 0.0),
    )
    bucket_materials = {"ped": ped_material}
    for proc_obj in processed_objects:
        bucket_key = str(proc_obj.get("vtoon_bucket", "ped"))
        if bucket_key == "cutout" and "cutout" not in bucket_materials:
            bucket_materials["cutout"] = ped_damage_helper.create_ped_hair_cutout_material(
                create_shader,
                "shinano_er_hair_cutout",
                diffuse_image=atlas_image,
                bump_image=flat_normal_image,
                spec_image=specular_image,
            )
        elif bucket_key == "alpha" and "alpha" not in bucket_materials:
            bucket_materials["alpha"] = ped_damage_helper.create_ped_alpha_material(
                create_shader,
                "shinano_er_hair_alpha",
                diffuse_image=atlas_image,
                bump_image=flat_normal_image,
                spec_image=specular_image,
            )
        target_mat = bucket_materials.get(bucket_key, ped_material)
        proc_obj.data.materials.clear()
        proc_obj.data.materials.append(target_mat)
        for poly_item in proc_obj.data.polygons:
            poly_item.material_index = 0

    print(
        i18n.translate("michael.build.joining_meshes", count=len(processed_objects))
    )
    bpy.ops.object.select_all(action="DESELECT")
    for proc_obj in processed_objects:
        proc_obj.select_set(True)
    bpy.context.view_layer.objects.active = processed_objects[0]
    bpy.ops.object.join()
    joined_mesh_obj = processed_objects[0]
    joined_mesh_obj.name = "SKEL_ROOT"

    for poly_item in joined_mesh_obj.data.polygons:
        poly_item.use_smooth = True
    joined_mesh_obj.data.update()

    for vgroup in list(joined_mesh_obj.vertex_groups):
        if vgroup.name not in valid_gtav_bones:
            joined_mesh_obj.vertex_groups.remove(vgroup)

    bpy.context.view_layer.objects.active = joined_mesh_obj
    bpy.ops.object.vertex_group_limit_total(limit=4)
    bpy.ops.object.vertex_group_normalize_all()

    total_verts = len(joined_mesh_obj.data.vertices)
    total_polys = len(joined_mesh_obj.data.polygons)
    print(
        i18n.translate(
            "michael.build.unified_summary", verts=total_verts, polys=total_polys
        )
    )

    ped_damage_result = ped_damage_helper.apply_ped_damage_attributes_in_blender(
        bpy,
        joined_mesh_obj,
        ped_armature,
        enable_blood_decals=enable_blood_decals,
    )
    print(ped_damage_helper.format_ped_damage_summary(ped_damage_result, i18n.translate))


    apply_michael_er_split_normals(
        joined_mesh_obj,
        preserved_body_normals,
        fbx_face_normals,
        ydrexport,
    )

    # 11. Split large materials for the uint16 RAGE limit
    blender_hair_helper.split_oversized_material_geometries(
        joined_mesh_obj,
        max_vertices_per_chunk=cli_args.max_verts_per_chunk,
        log_callback=lambda mat_name, poly_count, chunk_total: print(
            i18n.translate(
                "michael.build.splitting_material",
                name=mat_name,
                count=poly_count,
                chunks=chunk_total,
            )
        ),
    )

    # 12. Build Sollumz Drawable Dictionary hierarchy
    ydd_parent_empty = create_empty_object(SollumType.DRAWABLE_DICTIONARY)
    ped_armature.sollum_type = SollumType.DRAWABLE
    ped_armature.parent = ydd_parent_empty
    ped_armature.drawable_properties.lod_dist_high = 9998.0
    ped_armature.drawable_properties.lod_dist_med = 9998.0
    ped_armature.drawable_properties.lod_dist_low = 9998.0
    ped_armature.drawable_properties.lod_dist_vlow = 9998.0

    all_custom_yft_bones = list(custom_ear_bones) + list(custom_blink_bones)
    custom_ear_name_set = {item["name"] for item in all_custom_yft_bones}
    for bone_obj in ped_armature.data.bones:
        if bone_obj.name not in custom_ear_name_set:
            set_recommended_bone_properties(bone_obj)

    convert_obj_to_model(joined_mesh_obj)
    joined_mesh_obj.parent = ped_armature

    armature_modifier = joined_mesh_obj.modifiers.new("Armature", "ARMATURE")
    armature_modifier.object = ped_armature

    output_dir = os.path.abspath(cli_args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    for drawable_item_name in char_profile["export_drawables"]:
        ydd_parent_empty.name = drawable_item_name
        ped_armature.name = drawable_item_name
        bpy.ops.object.select_all(action="DESELECT")
        ydd_parent_empty.select_set(True)
        bpy.context.view_layer.objects.active = ydd_parent_empty

        export_status = bpy.ops.sollumz.export_assets(
            directory=output_dir,
            direct_export=True,
            use_custom_settings=True,
            target_versions={"GEN8"},
            target_formats={"NATIVE", "CWXML"},
            limit_to_selected=False,
        )
        ped_damage_helper.validate_rpf7_resource_file(
            os.path.join(output_dir, f"{drawable_item_name}.ydd")
        )
        print(
            i18n.translate(
                "michael.build.exported_ydd",
                name=drawable_item_name,
                status=export_status,
            )
        )

    yft_output_path = os.path.join(output_dir, f"{char_profile['ped_name']}.yft")
    updated_yft_bones, total_yft_bones, max_yft_delta = hand_skeleton_helper.patch_yft_skeleton(
        cli_args.skeleton_yft,
        yft_output_path,
        bone_world_targets,
        custom_child_bones=all_custom_yft_bones or None,
    )
    ped_damage_helper.validate_rpf7_resource_file(yft_output_path)
    print(
        i18n.translate(
            "michael.build.exported_yft",
            path=yft_output_path,
            updated=updated_yft_bones,
            total=total_yft_bones,
            delta=max_yft_delta,
        )
    )
    if physbone_chain_records or blink_profiles_to_merge or eye_blink_mode == "off":
        out_ini_path = os.path.join(output_dir, "GTAVPhysBones.ini")
        physbone_helper.export_physbone_asi_ini(
            out_ini_path,
            physbone_chain_records,
            target_ped_model=ped_model_name,
            blink_profiles=blink_profiles_to_merge,
        )
        print(f"[PhysBones] Exported runtime INI: {out_ini_path}")
        repo_root = project_paths.get_project_root()
        sync_targets = [
            repo_root / "1_Franklin_Shinano_Casual" / "5_rpf_package" / "GTAVPhysBones.ini",
            repo_root / "2_Michael_Shinano_EternalReunion" / "5_rpf_package" / "GTAVPhysBones.ini",
            repo_root / "3_Trevor_Miltina_Maid" / "5_rpf_package" / "GTAVPhysBones.ini",
        ]
        gtav_root = project_paths.get_gtav_root_dir()
        if gtav_root.is_dir():
            sync_targets.append(gtav_root / "GTAVPhysBones.ini")
        physbone_helper.merge_physbone_asi_ini(
            sync_targets[1],
            physbone_chain_records,
            own_prefixes=("PB_Ear_", "PB_ER_"),
            target_ped_model="all",
            extra_sync_paths=sync_targets,
            blink_profiles=blink_profiles_to_merge,
            own_blink_models=(ped_model_name,),
        )
        print(f"[PhysBones] Merged & synced global INI: {sync_targets[1]}")
        print(
            i18n.translate(
                "eye_blink.profile_exported",
                model=ped_model_name,
                enabled=1 if blink_profiles_to_merge else 0,
                max_blink=eye_blink_strength,
            )
        )


def extract_custom_blender_args():
    """Return CLI arguments appearing after `--` (or standalone Python args)."""
    return project_paths.extract_custom_blender_args()


def resolve_startup_language(custom_arguments) -> None:
    """Resolve UI language before parsing Blender CLI arguments."""
    configured_language = None
    try:
        configured_language = project_paths.get_configured_language()
    except FileNotFoundError:
        configured_language = None
    i18n.set_active_language(configured_language, cli_args=custom_arguments)


def parse_blender_cli_args():
    """Parse CLI options passed to Blender and populate config defaults lazily."""
    custom_arguments = extract_custom_blender_args()
    resolve_startup_language(custom_arguments)

    argument_parser = argparse.ArgumentParser(
        description=i18n.translate("michael.build.cli_desc")
    )
    argument_parser.add_argument(
        "--lang",
        choices=list(i18n.SUPPORTED_LANGUAGES) + ["auto"],
        default=None,
        help=i18n.translate("common.language_option_help"),
    )
    argument_parser.add_argument(
        "--target-character",
        default="michael",
        choices=["michael", "franklin", "trevor"],
        help=i18n.translate("michael.build.arg_target_char"),
    )
    argument_parser.add_argument(
        "--skeleton-yft",
        default=None,
        help=i18n.translate("michael.build.arg_skeleton"),
    )
    argument_parser.add_argument(
        "--shinano-fbx",
        default=None,
        help=i18n.translate("michael.build.arg_shinano_fbx"),
    )
    argument_parser.add_argument(
        "--outfit-fbx",
        default=None,
        help=i18n.translate("michael.build.arg_outfit_fbx"),
    )
    argument_parser.add_argument(
        "--watch-fbx",
        default=None,
        help=i18n.translate("michael.build.arg_watch_fbx"),
    )
    argument_parser.add_argument(
        "--hair-fbx",
        default=None,
        help=i18n.translate("michael.build.arg_hair_fbx"),
    )
    argument_parser.add_argument(
        "--hair",
        default=None,
        help="Custom Unity hair selector (.prefab, .fbx, auto, default, none)",
    )
    argument_parser.add_argument(
        "--hair-mat",
        default=None,
        help="Optional Unity .mat override for raw FBX hair",
    )
    argument_parser.add_argument(
        "--hair-tex",
        default=None,
        help="Optional texture override for custom hair",
    )
    argument_parser.add_argument(
        "--hair-scale",
        type=float,
        default=None,
        help="Optional uniform scale multiplier for custom hair",
    )
    argument_parser.add_argument(
        "--hair-offset",
        default=None,
        help="Optional X,Y,Z Unity offset tweak for custom hair",
    )
    argument_parser.add_argument(
        "--unity-scene",
        default=None,
        help="Optional Unity scene path override for scale extraction",
    )
    argument_parser.add_argument(
        "--unity-avatar-name",
        default=None,
        help="Optional Unity root GameObject name override",
    )
    argument_parser.add_argument(
        "--face-anim",
        default=None,
        help=i18n.translate("michael.build.arg_face_anim"),
    )
    argument_parser.add_argument(
        "--blendshapes-cfg",
        default=None,
        help=i18n.translate("blendshapes.cli_cfg"),
    )
    argument_parser.add_argument(
        "--blendshapes-source",
        choices=["auto", "unity", "cfg"],
        default=None,
        help=i18n.translate("blendshapes.cli_source"),
    )
    argument_parser.add_argument(
        "--save-blendshapes-cfg",
        default=None,
        help=i18n.translate("blendshapes.cli_save_cfg"),
    )
    argument_parser.add_argument(
        "--physbones-cfg",
        default=None,
        help=i18n.translate("physbones.cli_cfg"),
    )
    argument_parser.add_argument(
        "--physbones-source",
        choices=["auto", "unity", "cfg"],
        default=None,
        help=i18n.translate("physbones.cli_source"),
    )
    argument_parser.add_argument(
        "--save-physbones-cfg",
        default=None,
        help=i18n.translate("physbones.cli_save_cfg"),
    )
    argument_parser.add_argument(
        "--physbones-marshmallow",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=i18n.translate("physbones.cli_marshmallow"),
    )
    argument_parser.add_argument(
        "--blood-decals",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=i18n.translate("ped_damage.cli_blood_decals"),
    )
    argument_parser.add_argument(
        "--eye-blink",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=i18n.translate("eye_blink.cli_opt"),
    )
    argument_parser.add_argument(
        "--eye-blink-strength",
        type=float,
        default=None,
        help=i18n.translate("eye_blink.strength_cli_opt"),
    )
    argument_parser.add_argument(
        "--mouth-open-strength",
        type=float,
        default=None,
        help=i18n.translate("eye_blink.mouth_open_cli_opt"),
    )
    argument_parser.add_argument(
        "--texture-dir",
        default=None,
        help=i18n.translate("michael.build.arg_texture_dir"),
    )
    argument_parser.add_argument(
        "--atlas-png",
        default=None,
        help=i18n.translate("michael.build.arg_atlas_png"),
    )
    argument_parser.add_argument(
        "--normal-png",
        default=None,
        help=i18n.translate("michael.build.arg_normal_png"),
    )
    argument_parser.add_argument(
        "--spec-png",
        default=None,
        help=i18n.translate("michael.build.arg_spec_png"),
    )
    argument_parser.add_argument(
        "--output-dir",
        default=None,
        help=i18n.translate("michael.build.arg_output_dir"),
    )
    argument_parser.add_argument(
        "--max-verts-per-chunk",
        type=int,
        default=30000,
        help=i18n.translate("michael.build.arg_max_verts"),
    )

    parsed_args = argument_parser.parse_args(custom_arguments)
    if parsed_args.lang and parsed_args.lang != "auto":
        os.environ[i18n.LANG_ENV_VAR] = parsed_args.lang
        i18n.set_active_language(parsed_args.lang)

    target_protagonist = project_paths.normalize_protagonist_key(
        parsed_args.target_character
    )
    parsed_args.target_character = target_protagonist
    target_cfg = project_paths.get_character_paths(
        target_protagonist,
        avatar_override="shinano_er",
    )
    parsed_args.target_cfg = target_cfg
    parsed_args.skeleton_yft = parsed_args.skeleton_yft or str(target_cfg["skeleton_yft"])
    parsed_args.shinano_fbx = parsed_args.shinano_fbx or str(
        target_cfg.get("fbx_shinano") or target_cfg.get("source_fbx", "")
    )
    parsed_args.outfit_fbx = parsed_args.outfit_fbx or str(target_cfg.get("fbx_outfit", ""))
    parsed_args.watch_fbx = parsed_args.watch_fbx or str(target_cfg.get("fbx_watch", ""))
    parsed_args.cli_hair_fbx_explicit = parsed_args.hair_fbx is not None
    parsed_args.hair_fbx = (
        parsed_args.hair_fbx
        if parsed_args.hair_fbx is not None
        else str(target_cfg.get("fbx_hair", ""))
    )
    if parsed_args.hair_mat is None:
        parsed_args.hair_mat = str(target_cfg.get("hair_mat", "") or "")
    if parsed_args.hair_tex is None:
        parsed_args.hair_tex = str(target_cfg.get("hair_tex", "") or "")
    parsed_args.unity_scene = (
        parsed_args.unity_scene
        if parsed_args.unity_scene is not None
        else str(target_cfg.get("unity_scene", ""))
    )
    parsed_args.unity_avatar_name = (
        parsed_args.unity_avatar_name
        if parsed_args.unity_avatar_name is not None
        else str(target_cfg.get("unity_avatar_name", ""))
    )
    parsed_args.face_anim = parsed_args.face_anim or str(target_cfg.get("face_anim", ""))
    parsed_args.blendshapes_cfg = (
        parsed_args.blendshapes_cfg
        if parsed_args.blendshapes_cfg is not None
        else str(target_cfg.get("blendshapes_cfg", ""))
    )
    parsed_args.blendshapes_source = (
        parsed_args.blendshapes_source
        if parsed_args.blendshapes_source is not None
        else str(target_cfg.get("blendshapes_source", "auto"))
    )
    parsed_args.physbones_cfg = (
        parsed_args.physbones_cfg
        if parsed_args.physbones_cfg is not None
        else str(target_cfg.get("physbones_cfg", ""))
    )
    parsed_args.physbones_source = (
        parsed_args.physbones_source
        if parsed_args.physbones_source is not None
        else str(target_cfg.get("physbones_source", "auto"))
    )
    parsed_args.texture_dir = parsed_args.texture_dir or str(target_cfg["textures_dir"])
    parsed_args.atlas_png = parsed_args.atlas_png or Path(target_cfg["atlas_png"]).name
    parsed_args.normal_png = parsed_args.normal_png or Path(target_cfg["normal_png"]).name
    parsed_args.spec_png = parsed_args.spec_png or Path(target_cfg["spec_png"]).name
    parsed_args.output_dir = parsed_args.output_dir or str(target_cfg["exported_models_dir"])

    def _to_optional_host_path(raw_val: str) -> str:
        trimmed = str(raw_val or "").strip()
        if not trimmed:
            return ""
        if (
            not os.path.isabs(trimmed)
            and not trimmed.startswith("/mnt/")
            and not (len(trimmed) >= 3 and trimmed[1:3] in (":/", ":\\"))
        ):
            return trimmed
        return str(project_paths.to_host_path(trimmed))

    for path_attr_name in (
        "skeleton_yft",
        "shinano_fbx",
        "outfit_fbx",
        "watch_fbx",
        "hair_fbx",
        "hair_mat",
        "hair_tex",
        "unity_scene",
        "face_anim",
        "blendshapes_cfg",
        "save_blendshapes_cfg",
        "physbones_cfg",
        "save_physbones_cfg",
        "texture_dir",
        "output_dir",
    ):
        attr_val = getattr(parsed_args, path_attr_name, None)
        if attr_val:
            setattr(parsed_args, path_attr_name, _to_optional_host_path(attr_val))

    return parsed_args


if __name__ == "__main__":
    parsed_cli_args = parse_blender_cli_args()
    build_shinano_er_for_gtav(parsed_cli_args)
