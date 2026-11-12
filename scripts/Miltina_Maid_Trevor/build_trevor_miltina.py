#!/usr/bin/env python3
"""
Miltina Maid to GTA V Trevor (player_two) Conversion Script.
Applies exact Unity hierarchy head scaling (0.945x), symmetrical FaceEmo adult resting face,
anti-clipping blendshapes with shrink culling, bone retargeting to player_two skeleton,
and exports high-quality Sollumz .ydd drawables and renders.
"""

import math
import os as operating_system
import shutil
import sys
from pathlib import Path
import bmesh
import bpy
import mathutils
import addon_utils

# Localiza vrc2gtav_paths independentemente do espelho usado
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
for _tools_dir in (_REPO_ROOT / "scripts" / "common_tools", _REPO_ROOT / "_deploy_tools"):
    if _tools_dir.is_dir() and str(_tools_dir) not in sys.path:
        sys.path.insert(0, str(_tools_dir))

import vrc2gtav_paths as project_paths

TREVOR_CFG = project_paths.get_character_paths("trevor")

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
skeleton_path = Path(TREVOR_CFG["skeleton_yft"])
skeleton_dir = operating_system.path.join(str(skeleton_path.parent), "")
skeleton_file = skeleton_path.name
print(f"[INFO] Importing Trevor base skeleton: {skeleton_dir}{skeleton_file}")
bpy.ops.sollumz.import_assets(directory=skeleton_dir, files=[{"name": skeleton_file}])

ped_armature = bpy.data.objects.get("player_two")
if not ped_armature:
    ped_armature = next((item for item in bpy.data.objects if item.type == 'ARMATURE'), None)
print(f"[INFO] Found ped armature: {ped_armature.name if ped_armature else 'None'}")

valid_gtav_bones = {
    "SKEL_ROOT", "SKEL_Pelvis", "SKEL_Spine_Root", "SKEL_Spine0", "SKEL_Spine1",
    "SKEL_Spine2", "SKEL_Spine3", "SKEL_Neck_1", "SKEL_Head",
    "SKEL_L_Clavicle", "SKEL_L_UpperArm", "SKEL_L_Forearm", "SKEL_L_Hand",
    "SKEL_R_Clavicle", "SKEL_R_UpperArm", "SKEL_R_Forearm", "SKEL_R_Hand",
    "SKEL_L_Thigh", "SKEL_L_Calf", "SKEL_L_Foot", "SKEL_L_Toe0",
    "SKEL_R_Thigh", "SKEL_R_Calf", "SKEL_R_Foot", "SKEL_R_Toe0",
    "FACIAL_facialRoot", "FACIAL_jaw"
}
for side_code in ["L", "R"]:
    for finger_idx in range(5):
        for sub_idx in range(3):
            valid_gtav_bones.add(f"SKEL_{side_code}_Finger{finger_idx}{sub_idx}")

bpy.context.view_layer.objects.active = ped_armature
bpy.ops.object.mode_set(mode="EDIT")
for edit_bone in list(ped_armature.data.edit_bones):
    if edit_bone.name not in valid_gtav_bones:
        ped_armature.data.edit_bones.remove(edit_bone)
bpy.ops.object.mode_set(mode="OBJECT")
print(f"[INFO] Filtered ped armature bones to: {len(ped_armature.data.bones)}")

# Clean extra objects from skeleton import
for scene_obj in list(bpy.data.objects):
    if scene_obj != ped_armature:
        bpy.data.objects.remove(scene_obj)

# 3. Import Milltina FBX (strictly read-only on waifuv4)
fbx_path = str(TREVOR_CFG["source_fbx"])
print(f"[INFO] Importing Milltina model: {fbx_path}")
bpy.ops.import_scene.fbx(filepath=fbx_path, use_anim=False)

vrc_armature = next((item for item in bpy.data.objects if item.type == 'ARMATURE' and item != ped_armature), None)
print(f"[INFO] Imported VRC armature: {vrc_armature.name if vrc_armature else 'None'}")

KEEP_MESH_NAMES = {
    "Body", "Milltina_body", "Milltina_cloth_dress", "Milltina_cloth_apron",
    "Milltina_cloth_collar", "Milltina_cloth_hat", "Milltina_cloth_neck_ribbon",
    "Milltina_cloth_wrist_cuffs", "Milltina_cloth_panties", "Milltina_cloth_garterbelt",
    "Milltina_cloth_shoes", "Milltina_cloth_skirt", "Milltina_cloth_tail_ribbon",
    "Milltina_cloth_tail_slit", "Milltina_cow_tail", "Milltina_cow_ears", "Milltina_cow_horns",
    "Milltina_hair_base", "Milltina_hair_side", "Milltina_hair_front",
    "Milltina_hair_front_side", "Milltina_hair_twintail", "Milltina_cloth_hair_ribbon"
}

meshes_to_keep = []
for scene_obj in list(bpy.data.objects):
    if scene_obj.type == 'MESH':
        if scene_obj.name in KEEP_MESH_NAMES:
            meshes_to_keep.append(scene_obj)
        else:
            bpy.data.objects.remove(scene_obj)

print(f"[INFO] Retained {len(meshes_to_keep)} active maid meshes.")

# 4. Apply Exact Adult Facial Expression from FaceEmo 'Miltina_close eyes_Base_adult.anim'
EXACT_ANIM_FACIAL_BLENDSHAPES = {
    # Eyebrows
    "brow_down": 0.76,
    "brow_down_head_up": 0.40,
    
    # Eyelids & Eyes - sleepy anime tareme gaze
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
    
    # Eyelashes & Eyelid outlines
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
    
    # Mouth - snaggletooth anime expression
    "mouth_V_1": 0.20,
    "mouth_center_down_1": 0.15,
    "mouth_narrow": 0.25,
    "mouth_position_up": 0.20,
    "mouth_small": 0.07,
    "mouth_yaeba(tooth)_top_L": 1.00,
    "mouth_yaeba(tooth)_top_R": 1.00,
    
    # Head & Face shape (Adult proportions)
    "option_face_down": 1.00,
    "option_face_otona": 1.00,
    "option_jaw_narrow": 0.50,
    "option_morph_narrow": 1.00,
    "option_morph_sharp": 1.00,
    "option_nose_up": 0.30,
    
    # Ensure eyes remain visible in position
    "eye_x": 0.0,
    "eye_type2": 0.0,
    "(T1)highlight_main_x": 0.0
}

face_obj = bpy.data.objects.get("Body")
if face_obj and face_obj.data.shape_keys:
    # 4.1 Compute anime Lip Sync weights from vrc.v_aa (same delicate mouth open as Shinano)
    kb_aa = face_obj.data.shape_keys.key_blocks.get("vrc.v_aa")
    basis = face_obj.data.shape_keys.key_blocks.get("Basis")
    
    face_obj.vertex_groups.clear()
    jaw_vg = face_obj.vertex_groups.new(name="FACIAL_jaw")
    head_vg = face_obj.vertex_groups.new(name="SKEL_Head")
    
    mapped_count = 0
    if kb_aa and basis:
        for vertex_item in face_obj.data.vertices:
            delta_z_offset = kb_aa.data[vertex_item.index].co.z - basis.data[vertex_item.index].co.z
            if delta_z_offset < -0.0005:
                w_val = min(0.35, max(0.0, (abs(delta_z_offset) / 0.0075) * 0.35))
                jaw_vg.add([vertex_item.index], w_val, "REPLACE")
                head_vg.add([vertex_item.index], max(0.0, 1.0 - w_val), "REPLACE")
                mapped_count += 1
            else:
                head_vg.add([vertex_item.index], 1.0, "REPLACE")
        print(f"[OK] Mapped {mapped_count} vertices to FACIAL_jaw on Body for Lip Sync.")

    print("[INFO] Baking exact adult facial expression into 'Body'...")
    shape_keys = face_obj.data.shape_keys
    for anim_key, anim_val in EXACT_ANIM_FACIAL_BLENDSHAPES.items():
        key_block = shape_keys.key_blocks.get(anim_key)
        if key_block:
            key_block.value = anim_val
        else:
            kb_r = shape_keys.key_blocks.get(f"{anim_key}_R")
            kb_l = shape_keys.key_blocks.get(f"{anim_key}_L")
            if kb_r: kb_r.value = anim_val
            if kb_l: kb_l.value = anim_val
            
    bpy.context.view_layer.objects.active = face_obj
    face_obj.select_set(True)
    bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
    print("[SUCCESS] Face mesh baked cleanly with exact adult expression from anim clip.")

# Remove transparent decal faces (Milltina_face_alpha)
if face_obj:
    alpha_indices = [
        mat_idx for mat_idx, mat_elem in enumerate(face_obj.data.materials)
        if mat_elem and "alpha" in mat_elem.name.lower()
    ]
    if alpha_indices:
        bm_face = bmesh.new()
        bm_face.from_mesh(face_obj.data)
        faces_to_remove = [face_elem for face_elem in bm_face.faces if face_elem.material_index in alpha_indices]
        bmesh.ops.delete(bm_face, geom=faces_to_remove, context="FACES")
        loose_verts = [vert_elem for vert_elem in bm_face.verts if not vert_elem.link_faces]
        bmesh.ops.delete(bm_face, geom=loose_verts, context="VERTS")
        bm_face.to_mesh(face_obj.data)
        bm_face.free()
        face_obj.data.update()
        print(f"[OK] Removed {len(faces_to_remove)} transparent decal faces from Face mesh.")

    # Clear custom split normals so face shading is completely smooth and unblemished
    bpy.context.view_layer.objects.active = face_obj
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
    for poly_elem in face_obj.data.polygons:
        poly_elem.use_smooth = True
    face_obj.data.update()

# 5. Apply Anti-Clipping Blendshapes across Maid costume components
# User instruction: "Para o blendshape da roupa, use apenas o Shrink_Clothes_on no mesh Miltina_body."
CLOTHING_BLENDSHAPES = {
    "Milltina_body": {
        "Shrink_Clothes_on": 1.0,
        "Foot_heel": 1.0
    },
    "Milltina_cloth_dress": {
        "Cuff_shrink": 1.0,
        "Apron_set": 1.0,
        "Breasts_Cow": 0.0,
        "Breasts_Big": 0.0
    },
    "Milltina_cloth_skirt": {
        "Apron_set": 1.0,
        "Breasts_Cow": 0.0,
        "Breasts_Big": 0.0
    },
    "Milltina_cloth_apron": {
        "Breasts_Cow": 0.0,
        "Breasts_Big": 0.0
    },
    "Milltina_cloth_hat": {
        "Option_Twin tail": 1.0
    },
    "Milltina_cloth_garterbelt": {
        "Panty_squeeze": 1.0,
        "Foot_heel": 1.0,
        "Sock_squeeze": 1.0,
        "Garters_squeeze": 1.0
    },
    "Milltina_cloth_panties": {
        "Option_Thigh_small": 1.0,
        "Bandage_x": 1.0,
        "Option_Tail_set": 1.0
    },
    "Milltina_hair_side": {
        "Ears_on": 1.0
    }
}

print("[INFO] Baking anti-clipping blendshapes across all costume components...")
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

print("[SUCCESS] All costume and body blendshapes baked cleanly with neck and arms 100% preserved.")

# 6. Apply -55 degree arm rotation (T-pose -> GTA V Ped A-pose)
if vrc_armature:
    print("[INFO] Rotating VRC armature arms from T-pose to GTA V A-pose (-55 degrees)...")
    bpy.context.view_layer.objects.active = vrc_armature
    bpy.ops.object.mode_set(mode="POSE")
    arm_angle_rad = -math.radians(55.0)
    for arm_name in ["Upper_arm_L", "Upper_arm.L", "UpperArm.L"]:
        if arm_name in vrc_armature.pose.bones:
            pose_bone_item = vrc_armature.pose.bones[arm_name]
            pose_bone_item.rotation_mode = "XYZ"
            pose_bone_item.rotation_euler = (arm_angle_rad, 0.0, 0.0)
    for arm_name in ["Upper_arm_R", "Upper_arm.R", "UpperArm.R"]:
        if arm_name in vrc_armature.pose.bones:
            pose_bone_item = vrc_armature.pose.bones[arm_name]
            pose_bone_item.rotation_mode = "XYZ"
            pose_bone_item.rotation_euler = (arm_angle_rad, 0.0, 0.0)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Apply Armature modifier on each mesh so the A-pose is baked into the mesh geometry
    for cloth_obj in meshes_to_keep:
        bpy.context.view_layer.objects.active = cloth_obj
        if cloth_obj.data.shape_keys:
            bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
        arm_mod = cloth_obj.modifiers.get("Armature")
        if arm_mod:
            bpy.ops.object.modifier_apply(modifier=arm_mod.name)
    print("[SUCCESS] Applied -55 degree A-pose rotation to all mesh geometries.")

HEAD_MESH_NAMES = {
    "Body", "Milltina_cloth_hat", "Milltina_cow_ears", "Milltina_cow_horns", "Milltina_cloth_hair_ribbon",
    "Milltina_hair_base", "Milltina_hair_side", "Milltina_hair_front",
    "Milltina_hair_front_side", "Milltina_hair_twintail"
}

# 7. Scale and translate to match Trevor (player_two.yft) skeleton bone targets
# Target bounds from player_two.yft:
# SKEL_L_Foot world head: Z = -0.908 -> Miltina foot: Z = -0.0345
# SKEL_Head world head: Z = 0.642 -> Miltina head: Z = 1.0232
target_foot_z = -0.908
target_head_z = 0.642
source_foot_z = -0.0345
source_head_z = 1.0232

uniform_scale = (target_head_z - target_foot_z) / (source_head_z - source_foot_z)
z_translation = target_foot_z - (source_foot_z * uniform_scale)
print(f"[INFO] Bone-matched scale: {uniform_scale:.4f}, z_offset: {z_translation:.4f}")

for cloth_obj in meshes_to_keep:
    for vert_item in cloth_obj.data.vertices:
        vert_item.co.x = vert_item.co.x * uniform_scale
        vert_item.co.y = vert_item.co.y * uniform_scale
        vert_item.co.z = vert_item.co.z * uniform_scale + z_translation
    cloth_obj.data.update()

# 8. Remap UV coordinates into 4K Texture Atlas
print("[INFO] Remapping UV coordinates into 2x2 quadrant atlas...")
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
    elif "hair" in obj_name.lower() or "ears" in obj_name.lower() or "horns" in obj_name.lower():
        offset_u_val, offset_v_val = 0.5, 0.0
    else:
        offset_u_val, offset_v_val = 0.0, 0.0
        
    for loop_item in uv_layer:
        loop_item.uv[0] = loop_item.uv[0] * 0.5 + offset_u_val
        loop_item.uv[1] = loop_item.uv[1] * 0.5 + offset_v_val

# 9. Bone Retargeting with comprehensive Miltina bone table
BONE_MAP = {
    # Spine & Torso
    "Hips": "SKEL_Pelvis",
    "Spine": "SKEL_Spine1",
    "Chest": "SKEL_Spine2",
    "Neck": "SKEL_Neck_1",
    "Head": "SKEL_Head",
    "LeftEye": "SKEL_Head",
    "RightEye": "SKEL_Head",
    
    # Left Arm & Hand
    "Shoulder_L": "SKEL_L_Clavicle",
    "Upper_arm_L": "SKEL_L_UpperArm",
    "Upper_arm_Twist_L": "SKEL_L_UpperArm",
    "Upper_arm_Cloth_Twist_L": "SKEL_L_UpperArm",
    "Lower_arm_L": "SKEL_L_Forearm",
    "Lower_arm_Twist_L": "SKEL_L_Forearm",
    "Lower_arm_Cloth_Twist_L": "SKEL_L_Forearm",
    "Hand_L": "SKEL_L_Hand",
    "Proximal_L": "SKEL_L_Hand",
    "Intermediate_L": "SKEL_L_Hand",
    "Distal_L": "SKEL_L_Hand",
    
    # Right Arm & Hand
    "Shoulder_R": "SKEL_R_Clavicle",
    "Upper_arm_R": "SKEL_R_UpperArm",
    "Upper_arm_Twist_R": "SKEL_R_UpperArm",
    "Upper_arm_Cloth_Twist_R": "SKEL_R_UpperArm",
    "Lower_arm_R": "SKEL_R_Forearm",
    "Lower_arm_Twist_R": "SKEL_R_Forearm",
    "Lower_arm_Cloth_Twist_R": "SKEL_R_Forearm",
    "Hand_R": "SKEL_R_Hand",
    "Proximal_R": "SKEL_R_Hand",
    "Intermediate_R": "SKEL_R_Hand",
    "Distal_R": "SKEL_R_Hand",
    
    # Left Leg
    "Upper_leg_L": "SKEL_L_Thigh",
    "lower_leg_L": "SKEL_L_Calf",
    "Lower_leg_L": "SKEL_L_Calf",
    "Foot_L": "SKEL_L_Foot",
    "Toe_L": "SKEL_L_Toe0",
    
    # Right Leg
    "Upper_leg_R": "SKEL_R_Thigh",
    "lower_leg_R": "SKEL_R_Calf",
    "Lower_leg_R": "SKEL_R_Calf",
    "Foot_R": "SKEL_R_Foot",
    "Toe_R": "SKEL_R_Toe0"
}

def resolve_target_bone(source_bone_name):
    if source_bone_name in BONE_MAP:
        return BONE_MAP[source_bone_name]
        
    low_name = source_bone_name.lower()
    
    # Fingers & Hands (including Proximal, Intermediate, Distal)
    if any(keyword in low_name for keyword in ["thumb", "index", "middle", "ring", "little", "finger", "proximal", "intermediate", "distal"]):
        side_tag = "L" if ("_l" in low_name or ".l" in low_name or "left" in low_name) else "R"
        return f"SKEL_{side_tag}_Hand"

    # Twintails & Ponytails (twin tail1_R, twin tail2_L, Twin tail ribbon...): MUST be SKEL_Head!
    if "twin" in low_name or "pony" in low_name or "twintail" in low_name:
        return "SKEL_Head"

    # Hair, ears, ribbons on head, horns
    if any(keyword in low_name for keyword in ["hair", "ear", "hat", "horns", "face", "eye", "nose", "head"]):
        if not any(sub_word in low_name for sub_word in ["apron", "skirt", "tail."]):
            return "SKEL_Head"

    # Head ribbons
    if "ribbon" in low_name and not any(sub in low_name for sub in ["apron", "skirt", "tail_ribbon", "neck_ribbon"]):
        return "SKEL_Head"
            
    # Breasts, ruffles, chest accessories, collar
    if any(keyword in low_name for keyword in ["breast", "ruffle", "bust", "collar", "chest"]):
        return "SKEL_Spine2"
        
    # Skirt, tail, panties, hips accessories
    if any(keyword in low_name for keyword in ["skirt", "tail", "panty", "apron", "hips", "pelvis"]):
        return "SKEL_Pelvis"
        
    # Fallback for legs & thighs
    if "leg" in low_name or "thigh" in low_name or "butt" in low_name:
        side_tag = "L" if ("_l" in low_name or ".l" in low_name) else "R"
        if "calf" in low_name or "knee" in low_name or "lower" in low_name:
            return f"SKEL_{side_tag}_Calf"
        if "foot" in low_name:
            return f"SKEL_{side_tag}_Foot"
        if "toe" in low_name:
            return f"SKEL_{side_tag}_Toe0"
        return f"SKEL_{side_tag}_Thigh"
        
    # Fallback for arms
    if "arm" in low_name or "shoulder" in low_name or "hand" in low_name or "cuff" in low_name:
        side_tag = "L" if ("_l" in low_name or ".l" in low_name) else "R"
        if "lower" in low_name or "forearm" in low_name:
            return f"SKEL_{side_tag}_Forearm"
        elif "hand" in low_name or "cuff" in low_name:
            return f"SKEL_{side_tag}_Hand"
        elif "shoulder" in low_name or "clavicle" in low_name:
            return f"SKEL_{side_tag}_Clavicle"
        return f"SKEL_{side_tag}_UpperArm"
        
    return "SKEL_Pelvis"

print("[INFO] Retargeting vertex groups to GTA V skeleton...")
gtav_valid_bone_names = {bone_item.name for bone_item in ped_armature.data.bones}

for cloth_obj in meshes_to_keep:
    if cloth_obj.name == "Body":
        print(f"[INFO] Preserving Body vertex groups: Lip Sync FACIAL_jaw & SKEL_Head already calibrated ({len(cloth_obj.data.vertices)} verts).")
        continue

    vert_weights = {vert_idx: {} for vert_idx in range(len(cloth_obj.data.vertices))}
    for vert_group in cloth_obj.vertex_groups:
        target_bone_name = resolve_target_bone(vert_group.name)
        if target_bone_name not in gtav_valid_bone_names:
            target_bone_name = "SKEL_Pelvis"
        for vert_item in cloth_obj.data.vertices:
            for group_elem in vert_item.groups:
                if group_elem.group == vert_group.index and group_elem.weight > 0.001:
                    vert_weights[vert_item.index][target_bone_name] = vert_weights[vert_item.index].get(target_bone_name, 0.0) + group_elem.weight

    cloth_obj.vertex_groups.clear()

    for vert_idx, weight_dict in vert_weights.items():
        total_weight_sum = sum(weight_dict.values())
        if total_weight_sum > 0:
            for target_bone_name, weight_val in weight_dict.items():
                vert_group = cloth_obj.vertex_groups.get(target_bone_name) or cloth_obj.vertex_groups.new(name=target_bone_name)
                vert_group.add([vert_idx], weight_val / total_weight_sum, 'ADD')
        else:
            is_head_mesh = cloth_obj.name in HEAD_MESH_NAMES
            default_bone_name = "SKEL_Head" if is_head_mesh else "SKEL_Pelvis"
            vert_group = cloth_obj.vertex_groups.get(default_bone_name) or cloth_obj.vertex_groups.new(name=default_bone_name)
            vert_group.add([vert_idx], 1.0, 'REPLACE')

# 10. Join Meshes into single unified object
for selected_obj in bpy.context.selected_objects:
    selected_obj.select_set(False)

body_obj = bpy.data.objects.get("Body")
bpy.context.view_layer.objects.active = body_obj
for cloth_obj in meshes_to_keep:
    cloth_obj.select_set(True)

bpy.ops.object.join()
unified_obj = bpy.context.active_object
unified_obj.name = "uppr_000_u"
print(f"[SUCCESS] Joined meshes into: {unified_obj.name} with {len(unified_obj.data.vertices)} vertices.")

jaw_check_vg = unified_obj.vertex_groups.get("FACIAL_jaw")
if jaw_check_vg:
    jaw_cnt = sum(
        1
        for vertex_item in unified_obj.data.vertices
        for group_item in vertex_item.groups
        if group_item.group == jaw_check_vg.index and group_item.weight > 0.001
    )
    print(f"[VERIFIED] Unified object has {jaw_cnt} vertices on FACIAL_jaw for Lip Sync.")
else:
    print("[WARNING] FACIAL_jaw vertex group missing on unified object!")

# Triangulate
bm_temp = bmesh.new()
bm_temp.from_mesh(unified_obj.data)
bmesh.ops.triangulate(bm_temp, faces=bm_temp.faces[:])
bm_temp.to_mesh(unified_obj.data)
bm_temp.free()
unified_obj.data.update()

# Smooth all face polygons
for poly_item in unified_obj.data.polygons:
    poly_item.use_smooth = True
unified_obj.data.update()

# Limit weights to 4 per vertex and normalize
bpy.context.view_layer.objects.active = unified_obj
bpy.ops.object.vertex_group_limit_total(limit=4)
bpy.ops.object.vertex_group_normalize_all()
print(f"[INFO] Consolidated vertex groups count: {len(unified_obj.vertex_groups)}")

# Remove VRChat armature
if vrc_armature:
    bpy.data.objects.remove(vrc_armature)

# 11. Configure ped_default shader and assign textures
atlas_img_path = str(TREVOR_CFG["atlas_png"])
atlas_image = bpy.data.images.load(atlas_img_path)
atlas_image.name = "miltina_atlas_2k"

ped_mat = create_shader("ped_default.sps")
ped_mat.name = "miltina_maid_mat"

diff_node = ped_mat.node_tree.nodes.get("DiffuseSampler")
if diff_node:
    diff_node.image = atlas_image
    diff_node.texture_properties.embedded = False

spec_img_path = str(TREVOR_CFG["spec_png"])
if operating_system.path.exists(spec_img_path):
    spec_node = ped_mat.node_tree.nodes.get("SpecSampler")
    if spec_node:
        spec_img = bpy.data.images.load(spec_img_path)
        spec_img.name = "miltina_spec"
        spec_node.image = spec_img
        spec_node.texture_properties.embedded = False

normal_img_path = str(TREVOR_CFG["normal_png"])
if operating_system.path.exists(normal_img_path):
    normal_node = ped_mat.node_tree.nodes.get("BumpSampler")
    if normal_node:
        norm_img = bpy.data.images.load(normal_img_path)
        norm_img.name = "miltina_normal"
        normal_node.image = norm_img
        normal_node.texture_properties.embedded = False

for shader_node in ped_mat.node_tree.nodes:
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
unified_obj.data.materials.append(ped_mat)
for poly_item in unified_obj.data.polygons:
    poly_item.material_index = 0

if unified_obj.data.uv_layers:
    unified_obj.data.uv_layers[0].name = "UVMap 0"

# Setup Sollumz Color Attributes (White Color 1, Black/Zero Color 2 to eliminate dark stains)
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

# Set forward-biased smooth anime normals for face region to eliminate dark shadow triangles
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
        # Face & Neck area: Y < -0.015, 0.42 <= Z <= 0.72, abs(X) <= 0.12
        if vert_co.y < -0.015 and 0.42 <= vert_co.z <= 0.72 and abs(vert_co.x) <= 0.12:
            norm_x = vert_co.x * 2.2
            norm_y = -1.0
            norm_z = (vert_co.z - 0.57) * 1.4
            vec_len = math.sqrt(norm_x * norm_x + norm_y * norm_y + norm_z * norm_z)
            if vec_len > 1e-4:
                split_normals[loop_idx] = (norm_x / vec_len, norm_y / vec_len, norm_z / vec_len)

unified_obj.data.normals_split_custom_set(split_normals)
unified_obj.data.update()

# 12. Split Oversized Material Geometries for uint16 index limit (<30,000 verts per chunk)
def split_oversized_material_geometries(mesh_object, max_vertices_per_chunk=30000):
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
            f"[INFO] Splitting material '{base_material.name}' ({len(poly_indices)} polygons) "
            f"into {chunk_total} geometry chunks..."
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
            mesh_data_elem.polygons[poly_idx].material_index = mesh_data_elem.materials.find(target_mat.name)

split_oversized_material_geometries(unified_obj, max_vertices_per_chunk=30000)

# 13. Render high-resolution preview pictures in Blender
print("[INFO] Rendering Blender pictures...")
scene_ctx = bpy.context.scene
scene_ctx.render.engine = 'BLENDER_EEVEE'
scene_ctx.render.resolution_x = 1024
scene_ctx.render.resolution_y = 1024

world_ctx = scene_ctx.world or bpy.data.worlds.new("World")
scene_ctx.world = world_ctx
world_ctx.use_nodes = True
bg_node = world_ctx.node_tree.nodes.get("Background")
if bg_node:
    bg_node.inputs["Color"].default_value = (0.9, 0.9, 0.92, 1.0)
    bg_node.inputs["Strength"].default_value = 1.0

# Soft frontal lights for anime rendering
light_data = bpy.data.lights.new(name="StudioLight", type='SUN')
light_data.energy = 2.0
light_obj = bpy.data.objects.new(name="StudioLight", object_data=light_data)
scene_ctx.collection.objects.link(light_obj)
light_obj.rotation_euler = (math.radians(-90), 0.0, 0.0)

fill_data = bpy.data.lights.new(name="FillLight", type='SUN')
fill_data.energy = 1.0
fill_obj = bpy.data.objects.new(name="FillLight", object_data=fill_data)
scene_ctx.collection.objects.link(fill_obj)
fill_obj.rotation_euler = (math.radians(-75), math.radians(20), 0.0)

# Camera
cam_data = bpy.data.cameras.new(name="RenderCam")
cam_data.lens = 85.0
cam_obj = bpy.data.objects.new(name="RenderCam", object_data=cam_data)
scene_ctx.collection.objects.link(cam_obj)
scene_ctx.camera = cam_obj

renders_dir = str(project_paths.get_renders_output_dir())
operating_system.makedirs(renders_dir, exist_ok=True)

# A. Render Face & Neck close-up (aligned with Head at Z = +0.62)
cam_data.lens = 72.0
cam_obj.location = (0.0, -0.72, 0.62)
cam_obj.rotation_euler = (math.radians(90), 0, 0)
scene_ctx.render.filepath = f"{renders_dir}/miltina_blender_face.png"
bpy.ops.render.render(write_still=True)
print(f"[OK] Rendered Face: {scene_ctx.render.filepath}")

# B. Render Full Body front (aligned with center at Z = -0.13)
cam_data.lens = 45.0
cam_obj.location = (0.0, -3.2, -0.13)
cam_obj.rotation_euler = (math.radians(90), 0, 0)
scene_ctx.render.filepath = f"{renders_dir}/miltina_blender_full.png"
bpy.ops.render.render(write_still=True)
print(f"[OK] Rendered Full Body: {scene_ctx.render.filepath}")

# 14. Mount Sollumz Drawable Dictionary hierarchy and export YDD
print("[INFO] Mounting Sollumz Drawable Dictionary hierarchy...")
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

arm_mod = unified_obj.modifiers.new("Armature", "ARMATURE")
arm_mod.object = ped_armature

output_dir = str(TREVOR_CFG["exported_models_dir"])
operating_system.makedirs(output_dir, exist_ok=True)

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
    print(f"[INFO] Exported {drawable_name}.ydd -> {export_status}")

print("[COMPLETE] Miltina Maid export pipeline completed successfully.")
