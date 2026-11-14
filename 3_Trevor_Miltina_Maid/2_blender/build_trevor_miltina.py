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

import hand_skeleton_helper
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

# Exact adult resting expression from FaceEmo 'Miltina_close eyes_Base_adult.anim'
EXACT_ANIM_FACIAL_BLENDSHAPES = {
    "brow_down": 0.76,
    "brow_down_head_up": 0.40,
    "eye_big": 1.00,
    "eye_horizontal": 0.50,
    "eye_joy": 0.14,
    "eye_look_up": 0.15,
    "eye_pleasure_1": 0.70,
    "eye_position_down": 0.07,
    "eye_position_near": 0.50,
    "eye_position_up": 1.00,
    "eye_size_narrow": 0.25,
    "eye_size_small": 0.35,
    "eye_size_top_wide": 1.00,
    "eye_tsuri_1": 0.65,
    "eye_vertical": 1.00,
    "eye_zitome_1": 0.65,
    "eyelash_main_top1_big": 1.00,
    "eyelash_main_top2_big": 1.00,
    "eyelash_main_top3_big": 1.00,
    "eyelash_main_top4_big": 1.00,
    "eyelash_main_top_thin": 1.00,
    "eyelash_under_sub1_x": 1.00,
    "eyelash_under_sub2_x": 1.00,
    "eyelash_under_sub3_x": 1.00,
    "eyelid_center_down_1": 1.00,
    "eyelid_center_up_1": 0.70,
    "eyelid_down": 0.035,
    "eyelid_head_sharp": 1.00,
    "eyelid_sub1_x": 1.00,
    "eyelid_tail_long": 1.00,
    "eyelid_thin": 1.00,
    "eyelid_top_line_x": 1.00,
    "eye_under_center_up": 0.12,
    "eye_under_down": 1.00,
    "eye_under_head_up": 0.80,
    "eye_under_up": 1.00,
    "mouth_V_1": 0.20,
    "mouth_center_down_1": 0.15,
    "mouth_narrow": 0.25,
    "mouth_position_up": 0.20,
    "mouth_small": 0.07,
    "mouth_yaeba(tooth)_top_L": 1.00,
    "mouth_yaeba(tooth)_top_R": 1.00,
    "option_face_down": 1.00,
    "option_face_otona": 1.00,
    "option_jaw_narrow": 0.50,
    "option_morph_narrow": 1.00,
    "option_morph_sharp": 1.00,
    "option_nose_up": 0.30,
    "eye_x": 0.0,
    "eye_type2": 0.0,
    "(T1)highlight_main_x": 0.0,
}

# Only Shrink_Clothes_on + Foot_heel are enabled on Milltina_body to preserve neck/arms
CLOTHING_BLENDSHAPES = {
    "Milltina_body": {
        "Shrink_Clothes_on": 1.0,
        "Foot_heel": 1.0,
    },
    "Milltina_cloth_dress": {
        "Cuff_shrink": 1.0,
        "Apron_set": 1.0,
        "Breasts_Cow": 0.0,
        "Breasts_Big": 0.0,
    },
    "Milltina_cloth_skirt": {
        "Apron_set": 1.0,
        "Breasts_Cow": 0.0,
        "Breasts_Big": 0.0,
    },
    "Milltina_cloth_apron": {
        "Breasts_Cow": 0.0,
        "Breasts_Big": 0.0,
    },
    "Milltina_cloth_hat": {
        "Option_Twin tail": 1.0,
    },
    "Milltina_cloth_garterbelt": {
        "Panty_squeeze": 1.0,
        "Foot_heel": 1.0,
        "Sock_squeeze": 1.0,
        "Garters_squeeze": 1.0,
    },
    "Milltina_cloth_panties": {
        "Option_Thigh_small": 1.0,
        "Bandage_x": 1.0,
        "Option_Tail_set": 1.0,
    },
    "Milltina_hair_side": {
        "Ears_on": 1.0,
    },
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


def resolve_target_bone(source_bone_name):
    """Map a Miltina FBX bone name to its corresponding GTA V RAGE bone."""
    resolved_arm_or_finger = hand_skeleton_helper.resolve_finger_or_arm_bone(source_bone_name)
    if resolved_arm_or_finger is not None:
        return resolved_arm_or_finger

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


def split_oversized_material_geometries(mesh_object, max_vertices_per_chunk=30000):
    """Split dense material slots into chunks under the RAGE uint16 vertex limit."""
    mesh_data_elem = mesh_object.data
    polys_by_material = {}
    for poly_item in mesh_data_elem.polygons:
        polys_by_material.setdefault(poly_item.material_index, []).append(poly_item.index)

    max_polys_per_chunk = max(10000, int(max_vertices_per_chunk * 0.65))

    for mat_index, poly_indices in list(polys_by_material.items()):
        if len(poly_indices) <= max_polys_per_chunk:
            continue

        base_material = mesh_data_elem.materials[mat_index]
        chunk_total = math.ceil(len(poly_indices) / max_polys_per_chunk)
        print(
            i18n.translate(
                "trevor.build.splitting_material",
                name=base_material.name,
                count=len(poly_indices),
                chunks=chunk_total,
            )
        )

        sub_materials = [base_material]
        for chunk_idx in range(1, chunk_total):
            duplicated_mat = base_material.copy()
            duplicated_mat.name = f"{base_material.name}_chunk{chunk_idx}"
            mesh_data_elem.materials.append(duplicated_mat)
            sub_materials.append(duplicated_mat)

        for poly_seq, poly_idx in enumerate(poly_indices):
            chunk_assignment = poly_seq // max_polys_per_chunk
            target_mat = sub_materials[chunk_assignment]
            mesh_data_elem.polygons[poly_idx].material_index = mesh_data_elem.materials.find(
                target_mat.name
            )


def build_trevor_miltina_avatar():
    """Compile Miltina Maid in Blender, render previews, and export .ydd / .yft."""
    trevor_cfg = project_paths.get_character_paths("trevor")

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

    # 2. Import Trevor base skeleton from vrc2gtav.cfg
    skeleton_path = Path(trevor_cfg["skeleton_yft"])
    skeleton_dir = os.path.join(str(skeleton_path.parent), "")
    skeleton_file = skeleton_path.name
    print(
        i18n.translate(
            "trevor.build.importing_skeleton", path=f"{skeleton_dir}{skeleton_file}"
        )
    )
    bpy.ops.sollumz.import_assets(directory=skeleton_dir, files=[{"name": skeleton_file}])

    ped_armature = bpy.data.objects.get("player_two")
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
    unity_config = unity_scene_helper.load_unity_avatar_from_cfg(
        trevor_cfg,
        i18n_module=i18n,
        character_hints=("milltina", "miltina"),
    )
    hair_mode, hair_reason = unity_scene_helper.resolve_hair_mode(
        trevor_cfg.get("fbx_hair", ""),
        unity_config=unity_config,
    )
    custom_hair_meshes = set()
    custom_hair_armatures = []
    if hair_mode == "custom":
        custom_hair_fbx = str(trevor_cfg["fbx_hair"]).strip()
        print(
            i18n.translate(
                "unity_scene.hair_custom_active", reason=hair_reason, path=custom_hair_fbx
            )
        )
        for default_hair_obj in list(meshes_to_keep):
            if default_hair_obj.name in MILTINA_DEFAULT_HAIR_MESHES:
                meshes_to_keep.remove(default_hair_obj)
                bpy.data.objects.remove(default_hair_obj)
        pre_import_objs = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=custom_hair_fbx, use_anim=False)
        for imported_obj in list(bpy.data.objects):
            if imported_obj in pre_import_objs:
                continue
            if imported_obj.type == "ARMATURE":
                custom_hair_armatures.append(imported_obj)
            elif imported_obj.type == "MESH":
                if "tail" in imported_obj.name.lower():
                    bpy.data.objects.remove(imported_obj)
                    continue
                custom_hair_meshes.add(imported_obj)
                meshes_to_keep.append(imported_obj)
    else:
        print(i18n.translate("unity_scene.hair_fallback_default", reason=hair_reason))

    # 4. Bake facial expression & lip-sync jaw weights on Body
    face_obj = bpy.data.objects.get("Body")
    if face_obj and face_obj.data.shape_keys:
        shape_key_aa = face_obj.data.shape_keys.key_blocks.get("vrc.v_aa")
        basis_key = face_obj.data.shape_keys.key_blocks.get("Basis")

        face_obj.vertex_groups.clear()
        jaw_vgroup = face_obj.vertex_groups.new(name="FACIAL_jaw")
        head_vgroup = face_obj.vertex_groups.new(name="SKEL_Head")

        mapped_count = 0
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
                    mapped_count += 1
                else:
                    head_vgroup.add([vertex_item.index], 1.0, "REPLACE")
            print(i18n.translate("trevor.build.jaw_mapped", count=mapped_count))

        print(i18n.translate("trevor.build.baking_face"))
        shape_keys = face_obj.data.shape_keys
        for anim_key, anim_val in EXACT_ANIM_FACIAL_BLENDSHAPES.items():
            key_block = shape_keys.key_blocks.get(anim_key)
            if key_block:
                key_block.value = anim_val
            else:
                key_block_right = shape_keys.key_blocks.get(f"{anim_key}_R")
                key_block_left = shape_keys.key_blocks.get(f"{anim_key}_L")
                if key_block_right:
                    key_block_right.value = anim_val
                if key_block_left:
                    key_block_left.value = anim_val

        bpy.context.view_layer.objects.active = face_obj
        face_obj.select_set(True)
        bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
        print(i18n.translate("trevor.build.face_baked"))

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

    # 5. Bake anti-clipping costume blendshapes
    print(i18n.translate("trevor.build.baking_clothing"))
    for mesh_name, blendshape_dict in CLOTHING_BLENDSHAPES.items():
        cloth_obj = bpy.data.objects.get(mesh_name)
        if cloth_obj and cloth_obj.data.shape_keys:
            shape_keys = cloth_obj.data.shape_keys
            for key_name, weight_val in blendshape_dict.items():
                key_block = shape_keys.key_blocks.get(key_name)
                if key_block:
                    key_block.value = weight_val

            bpy.context.view_layer.objects.active = cloth_obj
            cloth_obj.select_set(True)
            bpy.ops.object.shape_key_remove(all=True, apply_mix=True)

    print(i18n.translate("trevor.build.clothing_baked"))

    # 6. Apply -55 degree arm rotation (T-pose -> GTA V Ped A-pose) & Unity scales
    armature_override_scale = unity_config.get("armature_scale", (1.0, 1.0, 1.0))
    if vrc_armature:
        print(i18n.translate("trevor.build.rotating_arms"))
        for rig_arm in [vrc_armature] + custom_hair_armatures:
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

    # Compute height mapping while live armatures and pose scales are active
    target_foot_z = -0.908
    target_head_z = 0.642
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
                bpy.ops.object.modifier_apply(modifier=mod_item.name)
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
    for cloth_obj in meshes_to_keep:
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
            or cloth_obj in custom_hair_meshes
        ):
            offset_u_val, offset_v_val = 0.5, 0.0
        else:
            offset_u_val, offset_v_val = 0.0, 0.0

        for loop_item in uv_layer:
            loop_item.uv[0] = loop_item.uv[0] * 0.5 + offset_u_val
            loop_item.uv[1] = loop_item.uv[1] * 0.5 + offset_v_val

    # 9. Retarget vertex groups onto valid GTA V bones
    print(i18n.translate("trevor.build.retargeting_bones"))
    gtav_valid_bone_names = {bone_item.name for bone_item in ped_armature.data.bones}

    for cloth_obj in meshes_to_keep:
        if cloth_obj.name == "Body":
            print(
                i18n.translate(
                    "trevor.build.preserving_body_groups",
                    count=len(cloth_obj.data.vertices),
                )
            )
            continue

        vert_weights = {vert_idx: {} for vert_idx in range(len(cloth_obj.data.vertices))}
        for vert_group in cloth_obj.vertex_groups:
            target_bone_name = resolve_target_bone(vert_group.name)
            if target_bone_name not in gtav_valid_bone_names:
                target_bone_name = "SKEL_Pelvis"
            for vert_item in cloth_obj.data.vertices:
                for group_elem in vert_item.groups:
                    if group_elem.group == vert_group.index and group_elem.weight > 0.001:
                        vert_weights[vert_item.index][target_bone_name] = (
                            vert_weights[vert_item.index].get(target_bone_name, 0.0)
                            + group_elem.weight
                        )

        cloth_obj.vertex_groups.clear()

        for vert_idx, weight_dict in vert_weights.items():
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

    # 10. Join all kept meshes into one unified object
    for selected_obj in bpy.context.selected_objects:
        selected_obj.select_set(False)

    body_obj = bpy.data.objects.get("Body")
    bpy.context.view_layer.objects.active = body_obj
    for cloth_obj in meshes_to_keep:
        cloth_obj.select_set(True)

    bpy.ops.object.join()
    unified_obj = bpy.context.active_object
    unified_obj.name = "uppr_000_u"
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

    # Relocate GTA V arm/hand/finger bones to match Miltina proportions
    hand_bone_world_targets = {}
    if vrc_armature:
        hand_bone_world_targets = hand_skeleton_helper.extract_avatar_arm_hand_targets(
            vrc_armature, uniform_scale, vertical_translation
        )
        relocated_arm_bones = hand_skeleton_helper.relocate_blender_armature_bones(
            ped_armature, hand_bone_world_targets
        )
        print(i18n.translate("trevor.build.bones_relocated", count=relocated_arm_bones))
        bpy.data.objects.remove(vrc_armature)
    for extra_hair_arm in custom_hair_armatures:
        if extra_hair_arm.name in bpy.data.objects:
            bpy.data.objects.remove(extra_hair_arm)

    # 11. Configure ped_default.sps shader and assign textures
    atlas_img_path = str(trevor_cfg["atlas_png"])
    atlas_image = bpy.data.images.load(atlas_img_path)
    atlas_image.name = "miltina_atlas_2k"

    ped_material = create_shader("ped_default.sps")
    ped_material.name = "miltina_maid_mat"

    diffuse_node = ped_material.node_tree.nodes.get("DiffuseSampler")
    if diffuse_node:
        diffuse_node.image = atlas_image
        diffuse_node.texture_properties.embedded = False

    spec_img_path = str(trevor_cfg["spec_png"])
    if os.path.exists(spec_img_path):
        specular_node = ped_material.node_tree.nodes.get("SpecSampler")
        if specular_node:
            specular_image = bpy.data.images.load(spec_img_path)
            specular_image.name = "miltina_spec"
            specular_node.image = specular_image
            specular_node.texture_properties.embedded = False

    normal_img_path = str(trevor_cfg["normal_png"])
    if os.path.exists(normal_img_path):
        normal_node = ped_material.node_tree.nodes.get("BumpSampler")
        if normal_node:
            normal_image = bpy.data.images.load(normal_img_path)
            normal_image.name = "miltina_normal"
            normal_node.image = normal_image
            normal_node.texture_properties.embedded = False

    for shader_node in ped_material.node_tree.nodes:
        if shader_node.name == "bumpiness" and hasattr(shader_node, "set_float"):
            shader_node.set_float(0.0)
        elif shader_node.name == "StubbleControl" and hasattr(shader_node, "set_vec2"):
            shader_node.set_vec2((0.0, 0.0))
        elif shader_node.name == "detailSettings" and hasattr(shader_node, "set_vec4"):
            shader_node.set_vec3((0.0, 0.0, 0.0))
        elif shader_node.name == "specularIntensityMult" and hasattr(shader_node, "set_float"):
            shader_node.set_float(0.0)
        elif shader_node.name == "specularFalloffMult" and hasattr(shader_node, "set_float"):
            shader_node.set_float(1.0)
        elif shader_node.name == "specularFresnel" and hasattr(shader_node, "set_float"):
            shader_node.set_float(0.0)

    unified_obj.data.materials.clear()
    unified_obj.data.materials.append(ped_material)
    for poly_item in unified_obj.data.polygons:
        poly_item.material_index = 0

    if unified_obj.data.uv_layers:
        unified_obj.data.uv_layers[0].name = "UVMap 0"

    bpy.context.view_layer.objects.active = unified_obj
    bpy.ops.sollumz.color_attrs_add_missing()
    bpy.ops.sollumz.uv_maps_add_missing()

    color_attr_1 = unified_obj.data.color_attributes.get("Color 1")
    if color_attr_1:
        for corner_item in color_attr_1.data:
            corner_item.color = (1.0, 1.0, 1.0, 1.0)

    color_attr_2 = unified_obj.data.color_attributes.get("Color 2")
    if color_attr_2:
        for corner_item in color_attr_2.data:
            corner_item.color = (0.0, 0.0, 0.0, 0.0)

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
    split_oversized_material_geometries(unified_obj, max_vertices_per_chunk=30000)

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

    renders_dir = str(project_paths.get_renders_output_dir())
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

    for bone_obj in ped_armature.data.bones:
        set_recommended_bone_properties(bone_obj)

    convert_obj_to_model(unified_obj)
    unified_obj.parent = ped_armature

    armature_modifier = unified_obj.modifiers.new("Armature", "ARMATURE")
    armature_modifier.object = ped_armature

    output_dir = str(trevor_cfg["exported_models_dir"])
    os.makedirs(output_dir, exist_ok=True)

    export_drawables = [
        "uppr_000_u",
        "uppr_000_r",
        "uppr_001_u",
        "uppr_002_u",
        "uppr_003_r",
        "uppr_010_u",
        "uppr_027_u",
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
        print(
            i18n.translate(
                "trevor.build.exported_ydd", name=drawable_name, status=export_status
            )
        )

    if hand_bone_world_targets:
        yft_output_path = Path(trevor_cfg["target_yft"])
        updated_yft_bones, total_yft_bones, max_yft_delta = (
            hand_skeleton_helper.patch_yft_skeleton(
                skeleton_path, yft_output_path, hand_bone_world_targets
            )
        )
        print(
            i18n.translate(
                "trevor.build.exported_yft",
                path=yft_output_path,
                updated=updated_yft_bones,
                total=total_yft_bones,
                delta=max_yft_delta,
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
    parsed_args = parser.parse_args(custom_arguments)
    if parsed_args.lang and parsed_args.lang != "auto":
        os.environ[i18n.LANG_ENV_VAR] = parsed_args.lang
        i18n.set_active_language(parsed_args.lang)

    build_trevor_miltina_avatar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
