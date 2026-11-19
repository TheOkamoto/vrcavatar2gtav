#!/usr/bin/env python3
"""
build_trevor_miltina.py
=======================
Miltina Maid to GTA V Trevor (`player_two`) Blender conversion script.
Applies anti-clipping blendshapes, symmetrical adult FaceEmo resting expression,
-55 degree A-pose rotation, 1:1 arm/hand/finger skeleton relocation for RAGE,
unified 2x2 Texture Atlas (`ped_default.sps`), Blender preview renders, and
Sollumz .ydd / .yft export.
"""

import argparse
import math
import os
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy
import mathutils

# Locate vrc2gtav_paths / vrc2gtav_i18n regardless of repository mirror
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
for _tools_dir in (_REPO_ROOT / "scripts" / "common_tools", _REPO_ROOT / "_deploy_tools"):
    if _tools_dir.is_dir() and str(_tools_dir) not in sys.path:
        sys.path.insert(0, str(_tools_dir))

import blender_hair_helper
import blendshape_helper
import eye_blink_helper
import hand_skeleton_helper
import ped_damage_helper
import physbone_helper
import unity_hair_helper
import unity_scene_helper
import vrc2gtav_i18n as i18n
import vrc2gtav_paths as project_paths

MILTINA_DEFAULT_HAIR_MESHES = {
    "Milltina_hair_base",
    "Milltina_hair_side",
    "Milltina_hair_front",
    "Milltina_hair_front_side",
    "Milltina_hair_twintail",
    "Milltina_cloth_hair_ribbon",
}


KEEP_MESH_NAMES = {
    "Body",
    "Milltina_body",
    "Milltina_cloth_dress",
    "Milltina_cloth_apron",
    "Milltina_cloth_collar",
    "Milltina_cloth_hat",
    "Milltina_cloth_neck_ribbon",
    "Milltina_cloth_wrist_cuffs",
    "Milltina_cloth_panties",
    "Milltina_cloth_garterbelt",
    "Milltina_cloth_shoes",
    "Milltina_cloth_skirt",
    "Milltina_cloth_tail_ribbon",
    "Milltina_cloth_tail_slit",
    "Milltina_cow_tail",
    "Milltina_cow_ears",
    "Milltina_cow_horns",
    "Milltina_hair_base",
    "Milltina_hair_side",
    "Milltina_hair_front",
    "Milltina_hair_front_side",
    "Milltina_hair_twintail",
    "Milltina_cloth_hair_ribbon",
}

HEAD_MESH_NAMES = {
    "Body",
    "Milltina_cloth_hat",
    "Milltina_cow_ears",
    "Milltina_cow_horns",
    "Milltina_cloth_hair_ribbon",
    "Milltina_hair_base",
    "Milltina_hair_side",
    "Milltina_hair_front",
    "Milltina_hair_front_side",
    "Milltina_hair_twintail",
}

BONE_MAP = {
    "Hips": "SKEL_Pelvis",
    "Spine": "SKEL_Spine1",
    "Chest": "SKEL_Spine2",
    "Neck": "SKEL_Neck_1",
    "Head": "SKEL_Head",
    "LeftEye": "SKEL_Head",
    "RightEye": "SKEL_Head",
    "Shoulder_L": "SKEL_L_Clavicle",
    "Upper_arm_L": "SKEL_L_UpperArm",
    "Lower_arm_L": "SKEL_L_Forearm",
    "Hand_L": "SKEL_L_Hand",
    "Proximal_L": "SKEL_L_Hand",
    "Intermediate_L": "SKEL_L_Hand",
    "Distal_L": "SKEL_L_Hand",
    "Shoulder_R": "SKEL_R_Clavicle",
    "Upper_arm_R": "SKEL_R_UpperArm",
    "Lower_arm_R": "SKEL_R_Forearm",
    "Hand_R": "SKEL_R_Hand",
    "Proximal_R": "SKEL_R_Hand",
    "Intermediate_R": "SKEL_R_Hand",
    "Distal_R": "SKEL_R_Hand",
    "Upper_leg_L": "SKEL_L_Thigh",
    "lower_leg_L": "SKEL_L_Calf",
    "Lower_leg_L": "SKEL_L_Calf",
    "Foot_L": "SKEL_L_Foot",
    "Toe_L": "SKEL_L_Toe0",
    "Upper_leg_R": "SKEL_R_Thigh",
    "lower_leg_R": "SKEL_R_Calf",
    "Lower_leg_R": "SKEL_R_Calf",
    "Foot_R": "SKEL_R_Foot",
    "Toe_R": "SKEL_R_Toe0",
}


def resolve_target_bone(source_bone_name, mesh_name=None, bone_mapping_ci=None):
    """Map a Miltina FBX bone name to its corresponding GTA V RAGE bone."""
    resolved_arm_or_finger = hand_skeleton_helper.resolve_finger_or_arm_bone(source_bone_name)
    if resolved_arm_or_finger is not None:
        return resolved_arm_or_finger

    resolved_pb = physbone_helper.resolve_miltina_maid_gtav_bone(
        source_bone_name, mesh_name, bone_mapping_ci=bone_mapping_ci
    )
    if resolved_pb is not None:
        return resolved_pb

    if source_bone_name in BONE_MAP:
        return BONE_MAP[source_bone_name]

    lower_bone_name = source_bone_name.lower()

    if any(keyword in lower_bone_name for keyword in ["proximal", "intermediate", "distal"]):
        side_tag = (
            "L"
            if ("_l" in lower_bone_name or ".l" in lower_bone_name or "left" in lower_bone_name)
            else "R"
        )
        return f"SKEL_{side_tag}_Hand"

    if "twin" in lower_bone_name or "pony" in lower_bone_name or "twintail" in lower_bone_name:
        return "SKEL_Head"

    if any(
        keyword in lower_bone_name
        for keyword in ["hair", "ear", "hat", "horns", "face", "eye", "nose", "head"]
    ):
        if not any(sub_word in lower_bone_name for sub_word in ["apron", "skirt", "tail."]):
            return "SKEL_Head"

    if "ribbon" in lower_bone_name and not any(
        sub_keyword in lower_bone_name
        for sub_keyword in ["apron", "skirt", "tail_ribbon", "neck_ribbon"]
    ):
        return "SKEL_Head"

    if any(
        keyword in lower_bone_name
        for keyword in ["breast", "ruffle", "bust", "collar", "chest"]
    ):
        return "SKEL_Spine2"

    if any(
        keyword in lower_bone_name
        for keyword in ["skirt", "tail", "panty", "apron", "hips", "pelvis"]
    ):
        return "SKEL_Pelvis"

    if "leg" in lower_bone_name or "thigh" in lower_bone_name or "butt" in lower_bone_name:
        side_tag = "L" if ("_l" in lower_bone_name or ".l" in lower_bone_name) else "R"
        if "calf" in lower_bone_name or "knee" in lower_bone_name or "lower" in lower_bone_name:
            return f"SKEL_{side_tag}_Calf"
        if "foot" in lower_bone_name:
            return f"SKEL_{side_tag}_Foot"
        if "toe" in lower_bone_name:
            return f"SKEL_{side_tag}_Toe0"
        return f"SKEL_{side_tag}_Thigh"

    if (
        "arm" in lower_bone_name
        or "shoulder" in lower_bone_name
        or "hand" in lower_bone_name
        or "cuff" in lower_bone_name
    ):
        side_tag = "L" if ("_l" in lower_bone_name or ".l" in lower_bone_name) else "R"
        if "lower" in lower_bone_name or "forearm" in lower_bone_name:
            return f"SKEL_{side_tag}_Forearm"
        if "hand" in lower_bone_name or "cuff" in lower_bone_name:
            return f"SKEL_{side_tag}_Hand"
        if "shoulder" in lower_bone_name or "clavicle" in lower_bone_name:
            return f"SKEL_{side_tag}_Clavicle"
        return f"SKEL_{side_tag}_UpperArm"

    return "SKEL_Pelvis"


def build_trevor_miltina_avatar(cli_args=None):
    """Compile Miltina Maid in Blender, render previews, and export .ydd / .yft."""
    raw_target_character = (
        getattr(cli_args, "target_character", None) or "trevor"
        if cli_args is not None
        else "trevor"
    )
    target_protagonist = project_paths.normalize_protagonist_key(raw_target_character)
    trevor_cfg = dict(
        project_paths.get_character_paths(
            target_protagonist,
            avatar_override="miltina_maid",
        )
    )
    if cli_args is not None:
        if getattr(cli_args, "unity_scene", None):
            trevor_cfg["unity_scene"] = project_paths.to_host_path(cli_args.unity_scene)
        if getattr(cli_args, "unity_avatar_name", None):
            trevor_cfg["unity_avatar_name"] = cli_args.unity_avatar_name
        if getattr(cli_args, "face_anim", None):
            trevor_cfg["face_anim"] = project_paths.to_host_path(cli_args.face_anim)
        if getattr(cli_args, "skeleton_yft", None):
            trevor_cfg["skeleton_yft"] = project_paths.to_host_path(cli_args.skeleton_yft)
        if getattr(cli_args, "texture_dir", None):
            override_tex_dir = project_paths.to_host_path(cli_args.texture_dir)
            trevor_cfg["textures_dir"] = override_tex_dir
            for tex_key in ("atlas_png", "spec_png", "normal_png"):
                if trevor_cfg.get(tex_key):
                    trevor_cfg[tex_key] = override_tex_dir / Path(trevor_cfg[tex_key]).name
        if getattr(cli_args, "output_dir", None):
            override_output_dir = project_paths.to_host_path(cli_args.output_dir)
            trevor_cfg["exported_models_dir"] = override_output_dir
            if not getattr(cli_args, "target_yft", None):
                trevor_cfg["target_yft"] = override_output_dir / f"{trevor_cfg['ped_name']}.yft"
        if getattr(cli_args, "target_yft", None):
            trevor_cfg["target_yft"] = project_paths.to_host_path(cli_args.target_yft)

    addon_utils.enable("sollumz")
    from sollumz.sollumz_properties import SollumType
    from sollumz.tools.blenderhelper import create_empty_object
    from sollumz.tools.drawablehelper import (
        convert_obj_to_model,
        set_recommended_bone_properties,
    )
    from sollumz.ydr.shader_materials import create_shader
    import sollumz.ydr.ydrexport as ydrexport

    # 1. Clear entire Blender scene
    for scene_obj in list(bpy.data.objects):
        bpy.data.objects.remove(scene_obj)
    for scene_mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(scene_mesh)
    for scene_arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(scene_arm)
    for scene_mat in list(bpy.data.materials):
        bpy.data.materials.remove(scene_mat)

    # 2. Import protagonist base skeleton from vrc2gtav.cfg
    ped_name = str(trevor_cfg.get("ped_name", "player_two"))
    skeleton_path = Path(trevor_cfg["skeleton_yft"])
    skeleton_dir = os.path.join(str(skeleton_path.parent), "")
    skeleton_file = skeleton_path.name
    print(
        i18n.translate(
            "trevor.build.importing_skeleton", path=f"{skeleton_dir}{skeleton_file}"
        )
    )
    bpy.ops.sollumz.import_assets(directory=skeleton_dir, files=[{"name": skeleton_file}])

    ped_armature = bpy.data.objects.get(skeleton_path.stem) or bpy.data.objects.get(ped_name)
    if not ped_armature:
        ped_armature = next(
            (item for item in bpy.data.objects if item.type == "ARMATURE"), None
        )
    print(
        i18n.translate(
            "trevor.build.found_armature",
            name=ped_armature.name if ped_armature else "None",
        )
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
        "FACIAL_jaw",
    }
    for side_code in ["L", "R"]:
        for finger_idx in range(5):
            for sub_idx in range(3):
                valid_gtav_bones.add(f"SKEL_{side_code}_Finger{finger_idx}{sub_idx}")
    valid_gtav_bones.update(hand_skeleton_helper.EXTRA_ARM_HELPER_BONES)
    eye_blink_mode = eye_blink_helper.resolve_effective_eye_blink_mode(
        getattr(cli_args, "eye_blink", None), trevor_cfg
    )
    valid_gtav_bones, stripped_hand_leaves = eye_blink_helper.prepare_ydd_blink_bone_set(
        valid_gtav_bones,
        enable_eye_blink=(eye_blink_mode != "off"),
        custom_bone_count=physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED,
    )
    if stripped_hand_leaves > 0:
        print(i18n.translate("eye_blink.ydd_bones_trimmed", stripped=stripped_hand_leaves))

    bpy.context.view_layer.objects.active = ped_armature
    bpy.ops.object.mode_set(mode="EDIT")
    for edit_bone in list(ped_armature.data.edit_bones):
        if edit_bone.name not in valid_gtav_bones:
            ped_armature.data.edit_bones.remove(edit_bone)
    bpy.ops.object.mode_set(mode="OBJECT")
    print(i18n.translate("trevor.build.filtered_bones", count=len(ped_armature.data.bones)))

    for scene_obj in list(bpy.data.objects):
        if scene_obj != ped_armature:
            bpy.data.objects.remove(scene_obj)

    # 3. Import Miltina FBX
    fbx_path = str(trevor_cfg["source_fbx"])
    print(i18n.translate("trevor.build.importing_fbx", path=fbx_path))
    bpy.ops.import_scene.fbx(filepath=fbx_path, use_anim=False)

    vrc_armature = next(
        (item for item in bpy.data.objects if item.type == "ARMATURE" and item != ped_armature),
        None,
    )
    print(
        i18n.translate(
            "trevor.build.imported_vrc_armature",
            name=vrc_armature.name if vrc_armature else "None",
        )
    )

    meshes_to_keep = []
    for scene_obj in list(bpy.data.objects):
        if scene_obj.type == "MESH":
            if scene_obj.name in KEEP_MESH_NAMES:
                meshes_to_keep.append(scene_obj)
            else:
                bpy.data.objects.remove(scene_obj)

    print(i18n.translate("trevor.build.retained_meshes", count=len(meshes_to_keep)))

    # Load optional Unity scene overrides (defaults strictly to 1.0 when blank/absent)
    if cli_args is not None and getattr(cli_args, "unity_scene", None):
        trevor_cfg["unity_scene"] = cli_args.unity_scene
    if cli_args is not None and getattr(cli_args, "unity_avatar_name", None):
        trevor_cfg["unity_avatar_name"] = cli_args.unity_avatar_name

    unity_config = unity_scene_helper.load_unity_avatar_from_cfg(
        trevor_cfg,
        i18n_module=i18n,
        character_hints=("milltina", "miltina"),
    )
    hair_spec_input = (
        getattr(cli_args, "hair", None) if cli_args is not None else None
    )
    if hair_spec_input is None:
        hair_spec_input = (
            str(trevor_cfg.get("custom_hair", "")).strip()
            or str(trevor_cfg.get("fbx_hair", "")).strip()
            or "auto"
        )
    hair_mat_override = (
        getattr(cli_args, "hair_mat", None) if cli_args is not None else None
    ) or str(trevor_cfg.get("hair_mat", "") or "")
    hair_tex_override = (
        getattr(cli_args, "hair_tex", None) if cli_args is not None else None
    ) or str(trevor_cfg.get("hair_tex", "") or "")
    hair_spec = unity_hair_helper.resolve_custom_hair_spec(
        hair_spec_input=hair_spec_input,
        unity_scene=trevor_cfg.get("unity_scene"),
        unity_avatar_name=trevor_cfg.get("unity_avatar_name", ""),
        unity_assets_root=trevor_cfg.get("unity_assets_root"),
        hair_mat_override=hair_mat_override,
        hair_tex_override=hair_tex_override,
    )
    hair_mode = hair_spec.get("mode", "default")
    hair_reason = hair_spec.get("reason") or hair_spec.get("source_input", "") or hair_mode
    miltina_default_hair_objs = [
        mesh_obj for mesh_obj in meshes_to_keep if mesh_obj.name in MILTINA_DEFAULT_HAIR_MESHES
    ]
    custom_hair_meshes = set()
    custom_hair_armatures = []

    # Resolve blendshapes from Unity project or portable .cfg preset
    blendshape_fbx_paths = [fbx_path]
    if hair_mode == "custom":
        for extra_hair_fbx in hair_spec.get("all_fbxs", []):
            if extra_hair_fbx and extra_hair_fbx not in blendshape_fbx_paths:
                blendshape_fbx_paths.append(extra_hair_fbx)
    blendshape_resolution = blendshape_helper.resolve_character_blendshapes(
        trevor_cfg,
        fbx_paths=blendshape_fbx_paths,
        character_hints=("milltina", "miltina"),
        default_face_mesh="Body",
        override_source=getattr(cli_args, "blendshapes_source", None) if cli_args else None,
        override_cfg_path=getattr(cli_args, "blendshapes_cfg", None) if cli_args else None,
        override_unity_scene=getattr(cli_args, "unity_scene", None) if cli_args else None,
        override_avatar_name=getattr(cli_args, "unity_avatar_name", None) if cli_args else None,
        override_face_anim=getattr(cli_args, "face_anim", None) if cli_args else None,
        save_cfg_path=getattr(cli_args, "save_blendshapes_cfg", None) if cli_args else None,
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

    pb_resolution = physbone_helper.resolve_character_physbones(
        trevor_cfg,
        fbx_paths=blendshape_fbx_paths,
        character_hints=("milltina", "miltina"),
        override_source=getattr(cli_args, "physbones_source", None) if cli_args else None,
        override_cfg_path=getattr(cli_args, "physbones_cfg", None) if cli_args else None,
        override_unity_scene=getattr(cli_args, "unity_scene", None) if cli_args else None,
        override_avatar_name=getattr(cli_args, "unity_avatar_name", None) if cli_args else None,
        override_marshmallow=(
            getattr(cli_args, "physbones_marshmallow", None) if cli_args else None
        ),
        save_cfg_path=getattr(cli_args, "save_physbones_cfg", None) if cli_args else None,
        verbose=True,
    )
    pb_detail_str = pb_resolution.get("cfg_path") or pb_resolution.get("unity_scene") or "-"
    print(
        i18n.translate(
            "physbones.loaded_source",
            source=pb_resolution["source_used"],
            chains=len(pb_resolution["chain_specs"]),
            bones=len(pb_resolution["custom_bones"]),
            detail=pb_detail_str,
        ),
        flush=True,
    )
    if pb_resolution.get("saved_cfg_path"):
        print(
            i18n.translate("physbones.saved_cfg", path=pb_resolution["saved_cfg_path"]),
            flush=True,
        )

    # 4. Bake facial expression & lip-sync jaw weights on Body
    face_obj = bpy.data.objects.get("Body")
    blink_rig_data = {"enabled": False, "reason": "no_body_shape_keys"}
    if face_obj and face_obj.data.shape_keys:
        shape_key_aa = face_obj.data.shape_keys.key_blocks.get("vrc.v_aa")
        basis_key = face_obj.data.shape_keys.key_blocks.get("Basis")

        face_obj.vertex_groups.clear()
        jaw_vgroup = face_obj.vertex_groups.new(name="FACIAL_jaw")
        head_vgroup = face_obj.vertex_groups.new(name="SKEL_Head")

        mapped_count = 0
        jaw_excl_indices = set()
        if shape_key_aa and basis_key:
            for vertex_item in face_obj.data.vertices:
                delta_z_offset = (
                    shape_key_aa.data[vertex_item.index].co.z
                    - basis_key.data[vertex_item.index].co.z
                )
                if delta_z_offset < -0.0005:
                    jaw_weight = min(0.35, max(0.0, (abs(delta_z_offset) / 0.0075) * 0.35))
                    jaw_vgroup.add([vertex_item.index], jaw_weight, "REPLACE")
                    head_vgroup.add([vertex_item.index], max(0.0, 1.0 - jaw_weight), "REPLACE")
                    jaw_excl_indices.add(vertex_item.index)
                    mapped_count += 1
                else:
                    head_vgroup.add([vertex_item.index], 1.0, "REPLACE")
            print(i18n.translate("trevor.build.jaw_mapped", count=mapped_count))

        print(i18n.translate("trevor.build.baking_face"))
        blendshape_helper.apply_blendshapes_to_blender_object(
            face_obj,
            resolved_mesh_weights.get("Body", {}),
            reset_unlisted=True,
            allow_lr_symmetry=True,
        )
        bpy.context.view_layer.update()

        blink_rig_data = eye_blink_helper.extract_body_eyelid_blink_rig_data(
            bpy,
            face_obj,
            eye_blink_mode=eye_blink_mode,
            shape_weights=resolved_mesh_weights.get("Body", {}),
            exclude_vert_indices=jaw_excl_indices,
        )
        if blink_rig_data.get("enabled"):
            eye_blink_helper.apply_eyelid_blink_weights_to_mesh(
                face_obj,
                blink_rig_data["weights_by_orig_vert"],
            )
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

        bpy.context.view_layer.objects.active = face_obj
        face_obj.select_set(True)
        bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
        print(i18n.translate("trevor.build.face_baked"))
    else:
        print(i18n.translate("eye_blink.skipped", reason=blink_rig_data["reason"]))

    if face_obj:
        alpha_indices = [
            mat_idx
            for mat_idx, mat_elem in enumerate(face_obj.data.materials)
            if mat_elem and "alpha" in mat_elem.name.lower()
        ]
        if alpha_indices:
            bmesh_face = bmesh.new()
            bmesh_face.from_mesh(face_obj.data)
            faces_to_remove = [
                face_elem
                for face_elem in bmesh_face.faces
                if face_elem.material_index in alpha_indices
            ]
            bmesh.ops.delete(bmesh_face, geom=faces_to_remove, context="FACES")
            loose_verts = [vert_elem for vert_elem in bmesh_face.verts if not vert_elem.link_faces]
            bmesh.ops.delete(bmesh_face, geom=loose_verts, context="VERTS")
            bmesh_face.to_mesh(face_obj.data)
            bmesh_face.free()
            face_obj.data.update()
            print(
                i18n.translate(
                    "trevor.build.removed_decal_faces", count=len(faces_to_remove)
                )
            )

        bpy.context.view_layer.objects.active = face_obj
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
        for poly_elem in face_obj.data.polygons:
            poly_elem.use_smooth = True
        face_obj.data.update()

    # 5. Bake anti-clipping costume and hair blendshapes
    print(i18n.translate("trevor.build.baking_clothing"))
    for mesh_name, blendshape_dict in resolved_mesh_weights.items():
        if mesh_name == "Body":
            continue
        if hair_mode in ("custom", "none") and mesh_name in MILTINA_DEFAULT_HAIR_MESHES:
            continue
        cloth_obj = bpy.data.objects.get(mesh_name)
        if cloth_obj and cloth_obj.data.shape_keys:
            blendshape_helper.apply_blendshapes_to_blender_object(
                cloth_obj,
                blendshape_dict,
                reset_unlisted=True,
                allow_lr_symmetry=False,
            )

            bpy.context.view_layer.objects.active = cloth_obj
            cloth_obj.select_set(True)
            bpy.ops.object.shape_key_remove(all=True, apply_mix=True)

    print(i18n.translate("trevor.build.clothing_baked"))

    # 6. Apply -55 degree arm rotation (T-pose -> GTA V Ped A-pose) & Unity scales
    armature_override_scale = unity_config.get("armature_scale", (1.0, 1.0, 1.0))
    if vrc_armature:
        print(i18n.translate("trevor.build.rotating_arms"))
        for rig_arm in [vrc_armature]:
            rig_arm.scale = (
                rig_arm.scale.x * armature_override_scale[0],
                rig_arm.scale.y * armature_override_scale[1],
                rig_arm.scale.z * armature_override_scale[2],
            )
            bpy.context.view_layer.objects.active = rig_arm
            bpy.ops.object.mode_set(mode="POSE")
            arm_angle_rad = -math.radians(55.0)
            for arm_name in ["Upper_arm_L", "Upper_arm.L", "UpperArm.L"]:
                if arm_name in rig_arm.pose.bones:
                    pose_bone_item = rig_arm.pose.bones[arm_name]
                    pose_bone_item.rotation_mode = "XYZ"
                    pose_bone_item.rotation_euler = (arm_angle_rad, 0.0, 0.0)
            for arm_name in ["Upper_arm_R", "Upper_arm.R", "UpperArm.R"]:
                if arm_name in rig_arm.pose.bones:
                    pose_bone_item = rig_arm.pose.bones[arm_name]
                    pose_bone_item.rotation_mode = "XYZ"
                    pose_bone_item.rotation_euler = (arm_angle_rad, 0.0, 0.0)
            applied_bones = unity_scene_helper.apply_unity_bone_scales_to_pose(
                rig_arm, unity_config
            )
            bpy.ops.object.mode_set(mode="OBJECT")
            if applied_bones and rig_arm == vrc_armature:
                print(i18n.translate("unity_scene.applied_bones", count=len(applied_bones)))
        bpy.context.view_layer.update()

    # Resolve cranial skull target from posed Miltina before replacing default hair
    skull_ref = blender_hair_helper.extract_skull_reference(
        bpy,
        vrc_armature,
        [bpy.data.objects.get("Body"), bpy.data.objects.get("Milltina_body")],
        miltina_default_hair_objs,
    )
    if hair_mode in ("custom", "none"):
        blender_hair_helper.remove_default_hair_meshes(
            bpy,
            "miltina_maid",
            mesh_list_to_prune=meshes_to_keep,
        )

    if hair_mode == "custom":
        print(
            i18n.translate(
                "unity_scene.hair_custom_active",
                reason=hair_reason,
                path=hair_spec.get("primary_fbx") or hair_spec.get("source_input", ""),
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
        custom_hair_armatures.extend(import_res["armatures"])
        eff_hair_scale = float(
            cli_args.hair_scale
            if (cli_args is not None and getattr(cli_args, "hair_scale", None) is not None)
            else (trevor_cfg.get("hair_scale") or 1.0)
        )
        eff_hair_offset = blender_hair_helper.parse_offset_triple(
            cli_args.hair_offset
            if (cli_args is not None and getattr(cli_args, "hair_offset", None) is not None)
            else trevor_cfg.get("hair_offset")
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
        custom_hair_meshes.update(custom_hair_objs)
        meshes_to_keep.extend(custom_hair_objs)
        print(
            i18n.translate("common.hair_aligned_summary", count=len(custom_hair_objs))
        )
    elif hair_mode == "none":
        print(i18n.translate("common.hair_none_active"))
    else:
        print(i18n.translate("unity_scene.hair_fallback_default", reason=hair_reason))

    # Compute height mapping while live armatures and pose scales are active
    target_foot_z = float(trevor_cfg.get("target_z_min", -0.908))
    target_head_z = float(trevor_cfg.get("target_z_max", 0.642))
    uniform_scale, vertical_translation = unity_scene_helper.compute_gtav_height_mapping(
        bpy,
        unity_config,
        [mesh_obj.name for mesh_obj in meshes_to_keep],
        ("Body", "Milltina_body", "Milltina_cloth_shoes"),
        target_foot_z,
        target_head_z,
        -0.0345,
        1.0232,
    )
    print(
        i18n.translate(
            "trevor.build.scale_info", scale=uniform_scale, offset=vertical_translation
        )
    )

    # Bake shape keys & armature pose deformations into vertices in world space
    for cloth_obj in meshes_to_keep:
        world_xform = cloth_obj.matrix_world.copy()
        bpy.context.view_layer.objects.active = cloth_obj
        if cloth_obj.data.shape_keys:
            bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
        for mod_item in list(cloth_obj.modifiers):
            if mod_item.type == "ARMATURE":
                if mod_item.object is not None:
                    bpy.ops.object.modifier_apply(modifier=mod_item.name)
                else:
                    cloth_obj.modifiers.remove(mod_item)
        cloth_obj.parent = None
        cloth_obj.matrix_world = mathutils.Matrix.Identity(4)
        for vert_item in cloth_obj.data.vertices:
            world_coord = world_xform @ vert_item.co
            vert_item.co.x = world_coord.x * uniform_scale
            vert_item.co.y = world_coord.y * uniform_scale
            vert_item.co.z = world_coord.z * uniform_scale + vertical_translation
        cloth_obj.data.update()
    if vrc_armature:
        print(i18n.translate("trevor.build.arms_rotated"))

    # 8. Remap UVs into the 2x2 quadrant Texture Atlas
    print(i18n.translate("trevor.build.remapping_uvs"))
    if custom_hair_meshes:
        loaded_manifest = unity_hair_helper.load_custom_hair_manifest(
            trevor_cfg["textures_dir"]
        )
        if (
            loaded_manifest is None
            or loaded_manifest.get("mode") != "custom"
            or loaded_manifest.get("source_input") != hair_spec.get("source_input")
        ):
            loaded_manifest = unity_hair_helper.build_inmemory_manifest_fallback(
                hair_spec,
                quad_size=(1024, 1024),
                quad_uv_rect=(0.5, 0.0, 0.5, 0.5),
            )
        body_ref_obj = bpy.data.objects.get("Body")
        body_uv_name = (
            body_ref_obj.data.uv_layers[0].name
            if body_ref_obj and body_ref_obj.data.uv_layers
            else "UVMap"
        )
        blender_hair_helper.remap_custom_hair_uvs(
            list(custom_hair_meshes),
            loaded_manifest,
            fallback_rect=(0.5, 0.0, 0.5, 0.5),
            target_uv_name=body_uv_name,
        )

    for cloth_obj in meshes_to_keep:
        if cloth_obj in custom_hair_meshes:
            continue
        mesh_data = cloth_obj.data
        uv_layer = mesh_data.uv_layers.active.data if mesh_data.uv_layers.active else None
        if not uv_layer:
            continue

        obj_name = cloth_obj.name
        if obj_name == "Body":
            offset_u_val, offset_v_val = 0.0, 0.5
        elif obj_name == "Milltina_body":
            offset_u_val, offset_v_val = 0.5, 0.5
        elif (
            "hair" in obj_name.lower()
            or "ears" in obj_name.lower()
            or "horns" in obj_name.lower()
        ):
            offset_u_val, offset_v_val = 0.5, 0.0
        else:
            offset_u_val, offset_v_val = 0.0, 0.0

        for loop_item in uv_layer:
            loop_item.uv[0] = loop_item.uv[0] * 0.5 + offset_u_val
            loop_item.uv[1] = loop_item.uv[1] * 0.5 + offset_v_val

    # Relocate GTA V arm/hand/finger bones and inject PhysBones BEFORE Step 9 weight retargeting
    hand_bone_world_targets = {}
    custom_physbones = []
    physbone_chain_records = []
    if vrc_armature:
        hand_bone_world_targets = hand_skeleton_helper.extract_avatar_arm_hand_targets(
            vrc_armature, uniform_scale, vertical_translation
        )
        relocated_arm_bones = hand_skeleton_helper.relocate_blender_armature_bones(
            ped_armature, hand_bone_world_targets
        )
        print(i18n.translate("trevor.build.bones_relocated", count=relocated_arm_bones))

        bpy.context.view_layer.update()
        vrc_bones_ci = {
            pose_item.name.lower(): pose_item for pose_item in vrc_armature.pose.bones
        }
        ped_world_matrices = {
            bone_item.name: (ped_armature.matrix_world @ bone_item.matrix_local).copy()
            for bone_item in ped_armature.data.bones
        }

        def _map_trevor_world_mat(src_world_mat):
            loc = src_world_mat.translation
            target_loc = mathutils.Vector(
                (
                    loc.x * uniform_scale,
                    loc.y * uniform_scale,
                    loc.z * uniform_scale + vertical_translation,
                )
            )
            return (
                mathutils.Matrix.Translation(target_loc)
                @ src_world_mat.to_quaternion().to_matrix().to_4x4()
            )

        def _resolve_trevor_pb_world_mat(src_bone_name):
            pose_item = vrc_bones_ci.get(src_bone_name.strip().lower())
            if pose_item is None:
                return None
            return _map_trevor_world_mat(vrc_armature.matrix_world @ pose_item.matrix)

        custom_physbones, physbone_chain_records = physbone_helper.build_dynamic_physbone_chains(
            ped_armature=ped_armature,
            chain_specs=pb_resolution["chain_specs"],
            parent_map=pb_resolution["parent_map"],
            chain_cfgs=pb_resolution["chains"],
            source_world_mat_fn=_resolve_trevor_pb_world_mat,
            ped_world_matrices=ped_world_matrices,
        )
        if custom_physbones:
            injected_pb_count = hand_skeleton_helper.inject_custom_bones_into_blender_armature(
                ped_armature,
                custom_physbones,
                bone_tag_fn=physbone_helper.compute_gtav_bone_tag,
            )
            print(
                f"[PhysBones] Injected {injected_pb_count} Miltina Maid bones into Trevor armature ({len(physbone_chain_records)} chains)",
                flush=True,
            )
        bpy.data.objects.remove(vrc_armature)
    for extra_hair_arm in custom_hair_armatures:
        if extra_hair_arm.name in bpy.data.objects:
            bpy.data.objects.remove(extra_hair_arm)

    ped_model_name = str(trevor_cfg.get("ped_name", "player_two"))
    blink_profiles_to_merge = []
    if blink_rig_data.get("enabled"):
        bpy.context.view_layer.update()
        trevor_blink_scale = (
            uniform_scale
            * (float(armature_override_scale[2]) if armature_override_scale else 1.0)
            * unity_scene_helper.get_uniform_scale(unity_config, ("Head",), default_scale=1.0)
            * unity_scene_helper.get_uniform_scale(unity_config, ("Neck",), default_scale=1.0)
        )
        scaled_blink_deltas = eye_blink_helper.scale_eye_blink_deltas(
            blink_rig_data, trevor_blink_scale
        )
        blink_prof = eye_blink_helper.build_blink_profile_for_ped(
            ped_armature,
            ped_model_name,
            scaled_blink_deltas,
            enabled=True,
        )
        if blink_prof is not None:
            blink_profiles_to_merge.append(blink_prof)

    # 9. Retarget vertex groups onto valid GTA V bones
    print(i18n.translate("trevor.build.retargeting_bones"))
    gtav_valid_bone_names = {bone_item.name for bone_item in ped_armature.data.bones}
    skirt_meshes = {"Milltina_cloth_skirt", "Milltina_cloth_apron", "Milltina_cloth_tail_slit"}

    def _add_anatomical_skirt_follow(weight_dict, v_co, skirt_w):
        if skirt_w <= 1e-6:
            return
        vert_t = max(0.0, min(1.0, (0.05 - v_co.z) / 0.14))
        thigh_cap = vert_t * 0.45
        thigh_w = skirt_w * thigh_cap
        pelvis_w = skirt_w - thigh_w
        if pelvis_w > 1e-6:
            weight_dict["SKEL_Pelvis"] = weight_dict.get("SKEL_Pelvis", 0.0) + pelvis_w
        lr_mix = max(0.0, min(1.0, (v_co.x + 0.035) / 0.070))
        if thigh_w * lr_mix > 1e-6:
            weight_dict["SKEL_L_Thigh"] = weight_dict.get("SKEL_L_Thigh", 0.0) + thigh_w * lr_mix
        if thigh_w * (1.0 - lr_mix) > 1e-6:
            weight_dict["SKEL_R_Thigh"] = weight_dict.get("SKEL_R_Thigh", 0.0) + thigh_w * (1.0 - lr_mix)

    for cloth_obj in meshes_to_keep:
        if cloth_obj in custom_hair_meshes:
            blender_hair_helper.retarget_custom_hair_weights_to_head(
                [cloth_obj], "SKEL_Head"
            )
            continue
        if cloth_obj.name == "Body":
            print(
                i18n.translate(
                    "trevor.build.preserving_body_groups",
                    count=len(cloth_obj.data.vertices),
                )
            )
            continue

        is_skirt_mesh = cloth_obj.name in skirt_meshes
        group_names = {vgroup.index: vgroup.name for vgroup in cloth_obj.vertex_groups}
        group_targets = {}
        for vgroup in cloth_obj.vertex_groups:
            tgt = resolve_target_bone(
                vgroup.name,
                cloth_obj.name,
                bone_mapping_ci=pb_resolution.get("bone_mapping_ci"),
            )
            if tgt not in gtav_valid_bone_names:
                tgt = "SKEL_Pelvis"
            group_targets[vgroup.index] = tgt

        vert_weights = {vert_idx: {} for vert_idx in range(len(cloth_obj.data.vertices))}
        for vert_item in cloth_obj.data.vertices:
            w_map = vert_weights[vert_item.index]
            for group_elem in vert_item.groups:
                if group_elem.weight <= 0.001 or group_elem.group not in group_targets:
                    continue
                raw_name = group_names[group_elem.group]
                low_raw = raw_name.strip().lower()
                tgt_bone = group_targets[group_elem.group]
                if is_skirt_mesh and low_raw.startswith("skirt7."):
                    seg_num = int("".join(chr_item for chr_item in low_raw if chr_item.isdigit()) or "7") % 10
                    tier = 0 if seg_num <= 3 else (1 if seg_num <= 5 else 2)
                    pb_bl = f"PB_MT_SkirtBL_{tier}"
                    pb_br = f"PB_MT_SkirtBR_{tier}"
                    if pb_bl in gtav_valid_bone_names and pb_br in gtav_valid_bone_names:
                        w_map[pb_bl] = w_map.get(pb_bl, 0.0) + group_elem.weight * 0.375
                        w_map[pb_br] = w_map.get(pb_br, 0.0) + group_elem.weight * 0.375
                        _add_anatomical_skirt_follow(w_map, vert_item.co, group_elem.weight * 0.25)
                    else:
                        _add_anatomical_skirt_follow(w_map, vert_item.co, group_elem.weight)
                elif is_skirt_mesh and tgt_bone.startswith("PB_MT_Skirt"):
                    w_map[tgt_bone] = w_map.get(tgt_bone, 0.0) + group_elem.weight * 0.75
                    _add_anatomical_skirt_follow(w_map, vert_item.co, group_elem.weight * 0.25)
                else:
                    w_map[tgt_bone] = w_map.get(tgt_bone, 0.0) + group_elem.weight

        cloth_obj.vertex_groups.clear()

        for vert_idx, weight_dict in vert_weights.items():
            if len(weight_dict) > 4:
                weight_dict = dict(
                    sorted(weight_dict.items(), key=lambda item: item[1], reverse=True)[:4]
                )
            total_weight_sum = sum(weight_dict.values())
            if total_weight_sum > 0:
                for target_bone_name, weight_val in weight_dict.items():
                    vert_group = cloth_obj.vertex_groups.get(
                        target_bone_name
                    ) or cloth_obj.vertex_groups.new(name=target_bone_name)
                    vert_group.add([vert_idx], weight_val / total_weight_sum, "ADD")
            else:
                is_head_mesh = (
                    cloth_obj.name in HEAD_MESH_NAMES or cloth_obj in custom_hair_meshes
                )
                default_bone_name = "SKEL_Head" if is_head_mesh else "SKEL_Pelvis"
                vert_group = cloth_obj.vertex_groups.get(
                    default_bone_name
                ) or cloth_obj.vertex_groups.new(name=default_bone_name)
                vert_group.add([vert_idx], 1.0, "REPLACE")

    # 10. Guard RPF7 16 MiB limit on heavy accessories/hair and join kept meshes
    ped_damage_helper.enforce_ped_rpf7_poly_budget(
        bpy,
        meshes_to_keep,
        enable_blood_decals=bool(getattr(cli_args, "blood_decals", True)),
    )

    for selected_obj in bpy.context.selected_objects:
        selected_obj.select_set(False)

    body_obj = bpy.data.objects.get("Body")
    bpy.context.view_layer.objects.active = body_obj
    for cloth_obj in meshes_to_keep:
        cloth_obj.select_set(True)

    bpy.ops.object.join()
    unified_obj = bpy.context.active_object
    primary_drawable = str(trevor_cfg.get("primary_drawable", "uppr_000_u"))
    unified_obj.name = primary_drawable
    print(
        i18n.translate(
            "trevor.build.joined_mesh",
            name=unified_obj.name,
            count=len(unified_obj.data.vertices),
        )
    )

    jaw_check_vgroup = unified_obj.vertex_groups.get("FACIAL_jaw")
    if jaw_check_vgroup:
        jaw_vert_count = sum(
            1
            for vertex_item in unified_obj.data.vertices
            for group_item in vertex_item.groups
            if group_item.group == jaw_check_vgroup.index and group_item.weight > 0.001
        )
        print(i18n.translate("trevor.build.verified_jaw", count=jaw_vert_count))
    else:
        print(i18n.translate("trevor.build.missing_jaw"))

    bmesh_temp = bmesh.new()
    bmesh_temp.from_mesh(unified_obj.data)
    bmesh.ops.triangulate(bmesh_temp, faces=bmesh_temp.faces[:])
    bmesh_temp.to_mesh(unified_obj.data)
    bmesh_temp.free()
    unified_obj.data.update()

    for poly_item in unified_obj.data.polygons:
        poly_item.use_smooth = True
    unified_obj.data.update()

    bpy.context.view_layer.objects.active = unified_obj
    bpy.ops.object.vertex_group_limit_total(limit=4)
    bpy.ops.object.vertex_group_normalize_all()
    print(
        i18n.translate(
            "trevor.build.consolidated_groups", count=len(unified_obj.vertex_groups)
        )
    )

    # 11. Configure ped_default.sps shader and assign textures
    atlas_img_path = str(trevor_cfg["atlas_png"])
    atlas_image = bpy.data.images.load(atlas_img_path)
    atlas_image.name = "miltina_atlas_2k"

    enable_blood_decals = bool(getattr(cli_args, "blood_decals", True))
    specular_image = None
    spec_img_path = str(trevor_cfg["spec_png"])
    if os.path.exists(spec_img_path):
        specular_image = bpy.data.images.load(spec_img_path)
        specular_image.name = "miltina_spec"

    normal_image = None
    normal_img_path = str(trevor_cfg["normal_png"])
    if os.path.exists(normal_img_path):
        normal_image = bpy.data.images.load(normal_img_path)
        normal_image.name = "miltina_normal"

    ped_material = ped_damage_helper.create_ped_material(
        create_shader,
        "miltina_maid_mat",
        enable_blood_decals=enable_blood_decals,
        diffuse_image=atlas_image,
        bump_image=normal_image,
        spec_image=specular_image,
        bumpiness=0.0,
        specular_intensity=0.0,
        specular_falloff=1.0,
        specular_fresnel=ped_damage_helper.DEFAULT_ANIME_SPECULAR_FRESNEL,
        detail_settings=(0.0, 0.0, 0.0),
        stubble_control=(0.0, 0.0),
        um_global_params=(0.0, 0.0, 0.0, 0.0),
    )

    unified_obj.data.materials.clear()
    unified_obj.data.materials.append(ped_material)
    for poly_item in unified_obj.data.polygons:
        poly_item.material_index = 0

    ped_damage_result = ped_damage_helper.apply_ped_damage_attributes_in_blender(
        bpy,
        unified_obj,
        ped_armature,
        enable_blood_decals=enable_blood_decals,
    )
    print(ped_damage_helper.format_ped_damage_summary(ped_damage_result, i18n.translate))

    # Set forward-biased smooth anime face normals
    bpy.context.view_layer.objects.active = unified_obj
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
    unified_obj.data.use_auto_smooth = True
    unified_obj.data.auto_smooth_angle = math.radians(180.0)

    for poly_item in unified_obj.data.polygons:
        poly_item.use_smooth = True

    unified_obj.data.calc_normals_split()
    split_normals = [tuple(loop_item.normal) for loop_item in unified_obj.data.loops]
    mesh_verts = unified_obj.data.vertices
    mesh_loops = unified_obj.data.loops

    for poly_item in unified_obj.data.polygons:
        for loop_idx in poly_item.loop_indices:
            vert_co = mesh_verts[mesh_loops[loop_idx].vertex_index].co
            if vert_co.y < -0.015 and 0.42 <= vert_co.z <= 0.72 and abs(vert_co.x) <= 0.12:
                norm_x = vert_co.x * 2.2
                norm_y = -1.0
                norm_z = (vert_co.z - 0.57) * 1.4
                vec_len = math.sqrt(norm_x * norm_x + norm_y * norm_y + norm_z * norm_z)
                if vec_len > 1e-4:
                    split_normals[loop_idx] = (
                        norm_x / vec_len,
                        norm_y / vec_len,
                        norm_z / vec_len,
                    )

    unified_obj.data.normals_split_custom_set(split_normals)
    unified_obj.data.update()

    # 12. Split oversized materials for uint16 RAGE limit
    blender_hair_helper.split_oversized_material_geometries(
        unified_obj,
        max_vertices_per_chunk=30000,
        log_callback=lambda mat_name, poly_count, chunk_total: print(
            i18n.translate(
                "trevor.build.splitting_material",
                name=mat_name,
                count=poly_count,
                chunks=chunk_total,
            )
        ),
    )

    # 13. Render preview images in Blender EEVEE
    print(i18n.translate("trevor.build.rendering_blender"))
    scene_ctx = bpy.context.scene
    scene_ctx.render.engine = "BLENDER_EEVEE"
    scene_ctx.render.resolution_x = 1024
    scene_ctx.render.resolution_y = 1024

    world_ctx = scene_ctx.world or bpy.data.worlds.new("World")
    scene_ctx.world = world_ctx
    world_ctx.use_nodes = True
    background_node = world_ctx.node_tree.nodes.get("Background")
    if background_node:
        background_node.inputs["Color"].default_value = (0.9, 0.9, 0.92, 1.0)
        background_node.inputs["Strength"].default_value = 1.0

    light_data = bpy.data.lights.new(name="StudioLight", type="SUN")
    light_data.energy = 2.0
    light_obj = bpy.data.objects.new(name="StudioLight", object_data=light_data)
    scene_ctx.collection.objects.link(light_obj)
    light_obj.rotation_euler = (math.radians(-90), 0.0, 0.0)

    fill_data = bpy.data.lights.new(name="FillLight", type="SUN")
    fill_data.energy = 1.0
    fill_obj = bpy.data.objects.new(name="FillLight", object_data=fill_data)
    scene_ctx.collection.objects.link(fill_obj)
    fill_obj.rotation_euler = (math.radians(-75), math.radians(20), 0.0)

    camera_data = bpy.data.cameras.new(name="RenderCam")
    camera_data.lens = 85.0
    camera_object = bpy.data.objects.new(name="RenderCam", object_data=camera_data)
    scene_ctx.collection.objects.link(camera_object)
    scene_ctx.camera = camera_object

    renders_dir = (
        str(trevor_cfg["exported_models_dir"])
        if (cli_args is not None and getattr(cli_args, "output_dir", None))
        else str(project_paths.get_renders_output_dir())
    )
    os.makedirs(renders_dir, exist_ok=True)

    camera_data.lens = 72.0
    camera_object.location = (0.0, -0.72, 0.62)
    camera_object.rotation_euler = (math.radians(90), 0, 0)
    scene_ctx.render.filepath = f"{renders_dir}/miltina_blender_face.png"
    bpy.ops.render.render(write_still=True)
    print(i18n.translate("trevor.build.rendered_face", path=scene_ctx.render.filepath))

    camera_data.lens = 45.0
    camera_object.location = (0.0, -3.2, -0.13)
    camera_object.rotation_euler = (math.radians(90), 0, 0)
    scene_ctx.render.filepath = f"{renders_dir}/miltina_blender_full.png"
    bpy.ops.render.render(write_still=True)
    print(i18n.translate("trevor.build.rendered_full", path=scene_ctx.render.filepath))

    # 14. Build Sollumz Drawable Dictionary hierarchy and export .ydd / .yft
    print(i18n.translate("trevor.build.mounting_hierarchy"))
    ydd_parent_empty = create_empty_object(SollumType.DRAWABLE_DICTIONARY)
    ped_armature.sollum_type = SollumType.DRAWABLE
    ped_armature.parent = ydd_parent_empty
    ped_armature.drawable_properties.lod_dist_high = 9998.0
    ped_armature.drawable_properties.lod_dist_med = 9998.0
    ped_armature.drawable_properties.lod_dist_low = 9998.0
    ped_armature.drawable_properties.lod_dist_vlow = 9998.0

    custom_pb_name_set = {pb_item["name"] for pb_item in custom_physbones} if custom_physbones else set()
    for bone_obj in ped_armature.data.bones:
        if bone_obj.name not in custom_pb_name_set:
            set_recommended_bone_properties(bone_obj)

    convert_obj_to_model(unified_obj)
    unified_obj.parent = ped_armature

    armature_modifier = unified_obj.modifiers.new("Armature", "ARMATURE")
    armature_modifier.object = ped_armature

    output_dir = str(trevor_cfg["exported_models_dir"])
    os.makedirs(output_dir, exist_ok=True)

    export_drawables = [
        str(slot_item) for slot_item in (trevor_cfg.get("export_drawables") or [])
    ]
    if target_protagonist == "trevor":
        for extra_slot in (
            "uppr_000_u",
            "uppr_000_r",
            "uppr_001_u",
            "uppr_002_u",
            "uppr_003_r",
            "uppr_010_u",
            "uppr_027_u",
        ):
            if extra_slot not in export_drawables:
                export_drawables.append(extra_slot)
    if not export_drawables:
        export_drawables = [
            primary_drawable,
            "uppr_000_r",
            "uppr_001_u",
        ]
    for drawable_name in export_drawables:
        ydd_parent_empty.name = drawable_name
        ped_armature.name = drawable_name
        bpy.ops.object.select_all(action="DESELECT")
        ydd_parent_empty.select_set(True)
        bpy.context.view_layer.objects.active = ydd_parent_empty

        ydrexport.triangulate_mesh = lambda eval_mesh: eval_mesh
        export_status = bpy.ops.sollumz.export_assets(
            directory=output_dir,
            direct_export=True,
            use_custom_settings=True,
            target_versions={"GEN8"},
            target_formats={"NATIVE", "CWXML"},
            limit_to_selected=False,
        )
        ped_damage_helper.validate_rpf7_resource_file(
            Path(output_dir) / f"{drawable_name}.ydd"
        )
        print(
            i18n.translate(
                "trevor.build.exported_ydd", name=drawable_name, status=export_status
            )
        )

    if hand_bone_world_targets:
        yft_output_path = Path(trevor_cfg["target_yft"])
        updated_yft_bones, total_yft_bones, max_yft_delta = (
            hand_skeleton_helper.patch_yft_skeleton(
                skeleton_path,
                yft_output_path,
                hand_bone_world_targets,
                custom_child_bones=custom_physbones or None,
            )
        )
        ped_damage_helper.validate_rpf7_resource_file(yft_output_path)
        print(
            i18n.translate(
                "trevor.build.exported_yft",
                path=yft_output_path,
                updated=updated_yft_bones,
                total=total_yft_bones,
                delta=max_yft_delta,
            )
        )

    if physbone_chain_records or blink_profiles_to_merge or eye_blink_mode == "off":
        out_ini_path = Path(output_dir) / "GTAVPhysBones.ini"
        physbone_helper.export_physbone_asi_ini(
            out_ini_path,
            physbone_chain_records,
            target_ped_model=ped_model_name,
            blink_profiles=blink_profiles_to_merge,
        )
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
            own_prefixes=("PB_MT_",),
            target_ped_model="all",
            extra_sync_paths=sync_targets,
            blink_profiles=blink_profiles_to_merge,
            own_blink_models=(ped_model_name,),
        )
        print(
            f"[PhysBones] Exported & merged Trevor PhysBones INI ({len(physbone_chain_records)} chains)"
        )
        print(
            i18n.translate(
                "eye_blink.profile_exported",
                model=ped_model_name,
                enabled=1 if blink_profiles_to_merge else 0,
            )
        )

    print(i18n.translate("trevor.build.done"))


def extract_custom_blender_args():
    """Return CLI arguments appearing after `--` (or standalone Python args)."""
    return project_paths.extract_custom_blender_args()


def resolve_startup_language(custom_arguments) -> None:
    """Resolve UI language from CLI arguments, environment variables, or config."""
    configured_language = None
    try:
        configured_language = project_paths.get_configured_language()
    except FileNotFoundError:
        configured_language = None
    i18n.set_active_language(configured_language, cli_args=custom_arguments)


def main() -> int:
    """Parse Blender CLI options and run the Trevor Miltina build."""
    custom_arguments = extract_custom_blender_args()
    resolve_startup_language(custom_arguments)

    parser = argparse.ArgumentParser(description=i18n.translate("trevor.build.cli_desc"))
    parser.add_argument(
        "--lang",
        choices=list(i18n.SUPPORTED_LANGUAGES) + ["auto"],
        default=None,
        help=i18n.translate("common.language_option_help"),
    )
    parser.add_argument(
        "--target-character",
        default="trevor",
        help=i18n.translate("trevor.build.arg_target_char"),
    )
    parser.add_argument("--skeleton-yft", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--texture-dir", default=None)
    parser.add_argument("--target-yft", default=None)
    parser.add_argument(
        "--hair",
        default=None,
        help="Custom Unity hair selector (.prefab, .fbx, auto, default, none)",
    )
    parser.add_argument(
        "--hair-mat",
        default=None,
        help="Optional Unity .mat override for raw FBX hair",
    )
    parser.add_argument(
        "--hair-tex",
        default=None,
        help="Optional texture override for custom hair",
    )
    parser.add_argument(
        "--hair-scale",
        type=float,
        default=None,
        help="Optional uniform scale multiplier for custom hair",
    )
    parser.add_argument(
        "--hair-offset",
        default=None,
        help="Optional X,Y,Z Unity offset tweak for custom hair",
    )
    parser.add_argument(
        "--blendshapes-cfg",
        default=None,
        help=i18n.translate("blendshapes.cli_cfg"),
    )
    parser.add_argument(
        "--blendshapes-source",
        choices=["auto", "unity", "cfg"],
        default=None,
        help=i18n.translate("blendshapes.cli_source"),
    )
    parser.add_argument(
        "--save-blendshapes-cfg",
        default=None,
        help=i18n.translate("blendshapes.cli_save_cfg"),
    )
    parser.add_argument(
        "--physbones-cfg",
        default=None,
        help=i18n.translate("physbones.cli_cfg"),
    )
    parser.add_argument(
        "--physbones-source",
        choices=["auto", "unity", "cfg"],
        default=None,
        help=i18n.translate("physbones.cli_source"),
    )
    parser.add_argument(
        "--save-physbones-cfg",
        default=None,
        help=i18n.translate("physbones.cli_save_cfg"),
    )
    parser.add_argument(
        "--physbones-marshmallow",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=i18n.translate("physbones.cli_marshmallow"),
    )
    parser.add_argument(
        "--blood-decals",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=i18n.translate("ped_damage.cli_blood_decals"),
    )
    parser.add_argument(
        "--eye-blink",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=i18n.translate("eye_blink.cli_opt"),
    )
    parser.add_argument(
        "--unity-scene",
        default=None,
        help="Optional Unity scene path override",
    )
    parser.add_argument(
        "--unity-avatar-name",
        default=None,
        help="Optional Unity root GameObject name override",
    )
    parser.add_argument(
        "--face-anim",
        default=None,
        help=i18n.translate("blendshapes.cli_face_anim"),
    )
    parsed_args = parser.parse_args(custom_arguments)
    if parsed_args.lang and parsed_args.lang != "auto":
        os.environ[i18n.LANG_ENV_VAR] = parsed_args.lang
        i18n.set_active_language(parsed_args.lang)

    build_trevor_miltina_avatar(parsed_args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
