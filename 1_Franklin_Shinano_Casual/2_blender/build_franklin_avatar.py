"""
build_franklin_avatar.py
========================
Assemble, rig, shade, and export Shinano Casual as GTA V drawable dictionaries
and matching fragment skeleton for Franklin Clinton (player_one).
"""

import json
import math
import os as operating_system
import re as regex_module
import struct
import sys
import zlib
from pathlib import Path

import addon_utils
import bmesh
import bpy
import mathutils

# Resolve helper directory from vrc2gtav layout (compatible with both repo mirrors)
_CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_CANDIDATE = _CURRENT_SCRIPT_DIR.parent.parent
for _tools_candidate in (
    _REPO_ROOT_CANDIDATE / "scripts" / "common_tools",
    _REPO_ROOT_CANDIDATE / "_deploy_tools",
):
    if _tools_candidate.is_dir() and str(_tools_candidate) not in sys.path:
        sys.path.insert(0, str(_tools_candidate))

import vrc2gtav_i18n as project_i18n
import vrc2gtav_paths as project_paths
import hand_skeleton_helper
import unity_scene_helper

project_i18n.set_active_language()
FRANKLIN_CFG = project_paths.get_character_paths("franklin")


def load_anim_blendshapes(anim_filepath: str) -> dict:
    """Extract static facial blendshape weights from a Unity YAML .anim file."""
    shapes_map = {}
    if not operating_system.path.exists(anim_filepath):
        return shapes_map
    with open(anim_filepath, "r", encoding="utf-8") as anim_handle:
        raw_text = anim_handle.read()
    animation_blocks = raw_text.split("  - serializedVersion: 2")
    for curve_block in animation_blocks[1:]:
        val_match = regex_module.search(r"value:\s*([-\d.]+)", curve_block)
        attr_match = regex_module.search(r"attribute:\s*([^\n]+)", curve_block)
        path_match = regex_module.search(r"path:\s*([^\n]+)", curve_block)
        if val_match and attr_match and path_match:
            raw_val = float(val_match.group(1))
            attr_name = attr_match.group(1).strip()
            shape_name = attr_name.replace("blendShape.", "").strip()
            if shape_name.startswith('"'):
                try:
                    shape_name = json.loads(shape_name)
                except Exception:
                    shape_name = shape_name.strip('"')
            if abs(raw_val) > 1e-4:
                shapes_map[shape_name] = raw_val / 100.0
            else:
                shapes_map[shape_name] = 0.0
    return shapes_map


def read_fbx_nodes(fbx_bytes: bytes) -> list:
    """Standalone binary FBX node parser supporting versions <7500 and >=7500."""
    fbx_version = struct.unpack_from("<I", fbx_bytes, 23)[0]
    is_64bit = fbx_version >= 7500
    header_fmt = "<QQQB" if is_64bit else "<IIIB"
    header_size = 25 if is_64bit else 13

    def parse_property(cursor_pos: int):
        type_char = chr(fbx_bytes[cursor_pos])
        cursor_pos += 1
        if type_char == "Y":
            return struct.unpack_from("<h", fbx_bytes, cursor_pos)[0], cursor_pos + 2
        if type_char == "C":
            return bool(fbx_bytes[cursor_pos]), cursor_pos + 1
        if type_char == "I":
            return struct.unpack_from("<i", fbx_bytes, cursor_pos)[0], cursor_pos + 4
        if type_char == "F":
            return struct.unpack_from("<f", fbx_bytes, cursor_pos)[0], cursor_pos + 4
        if type_char == "D":
            return struct.unpack_from("<d", fbx_bytes, cursor_pos)[0], cursor_pos + 8
        if type_char == "L":
            return struct.unpack_from("<q", fbx_bytes, cursor_pos)[0], cursor_pos + 8
        if type_char in ("S", "R"):
            str_len = struct.unpack_from("<I", fbx_bytes, cursor_pos)[0]
            cursor_pos += 4
            raw_slice = fbx_bytes[cursor_pos : cursor_pos + str_len]
            decoded_val = raw_slice.decode("utf-8", errors="replace") if type_char == "S" else raw_slice
            return decoded_val, cursor_pos + str_len
        if type_char in ("f", "d", "l", "i", "b"):
            arr_len, encoding_flag, comp_len = struct.unpack_from("<III", fbx_bytes, cursor_pos)
            cursor_pos += 12
            raw_slice = fbx_bytes[cursor_pos : cursor_pos + comp_len]
            cursor_pos += comp_len
            if encoding_flag == 1:
                raw_slice = zlib.decompress(raw_slice)
            type_map = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "B"}
            return struct.unpack(f"<{arr_len}{type_map[type_char]}", raw_slice), cursor_pos
        raise ValueError(project_i18n.translate("franklin.fbx_prop_unknown", prop_type=type_char))

    def parse_node(cursor_pos: int):
        end_offset, num_props, prop_len, name_len = struct.unpack_from(header_fmt, fbx_bytes, cursor_pos)
        if end_offset == 0:
            return None, cursor_pos + header_size
        cursor_pos += header_size
        node_name = fbx_bytes[cursor_pos : cursor_pos + name_len].decode("utf-8", errors="replace")
        cursor_pos += name_len
        properties_list = []
        prop_end = cursor_pos + prop_len
        for _ in range(num_props):
            prop_val, cursor_pos = parse_property(cursor_pos)
            properties_list.append(prop_val)
        cursor_pos = prop_end
        children_list = []
        while cursor_pos < end_offset:
            child_node, cursor_pos = parse_node(cursor_pos)
            if child_node is None:
                break
            children_list.append(child_node)
        return (node_name, properties_list, children_list), end_offset

    scan_pos = 27
    nodes_list = []
    while scan_pos < len(fbx_bytes) - header_size:
        parsed_node, scan_pos = parse_node(scan_pos)
        if parsed_node is None:
            break
        nodes_list.append(parsed_node)
    return nodes_list


addon_utils.enable("sollumz")
from sollumz.sollumz_properties import SollumType
from sollumz.tools.blenderhelper import create_empty_object
from sollumz.tools.drawablehelper import set_recommended_bone_properties, convert_obj_to_model
from sollumz.ydr.shader_materials import create_shader

# 1. Clear scene data blocks
for scene_obj in list(bpy.data.objects):
    bpy.data.objects.remove(scene_obj)
for mesh_block in list(bpy.data.meshes):
    bpy.data.meshes.remove(mesh_block)
for armature_block in list(bpy.data.armatures):
    bpy.data.armatures.remove(armature_block)
for mat_block in list(bpy.data.materials):
    bpy.data.materials.remove(mat_block)

# 2. Import Franklin skeleton from configured .yft
skeleton_yft_path = Path(FRANKLIN_CFG["skeleton_yft"])
print(project_i18n.translate("franklin.importing_skeleton", filename=skeleton_yft_path.name))
bpy.ops.sollumz.import_assets(
    directory=str(skeleton_yft_path.parent) + "/",
    files=[{"name": skeleton_yft_path.name}],
)
skeleton_arm_name = skeleton_yft_path.stem
franklin_armature = bpy.data.objects.get(skeleton_arm_name) or bpy.data.objects["player_one"]

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
}
for side_label in ("L", "R"):
    for finger_index in range(5):
        for segment_index in range(3):
            target_bones.add(f"SKEL_{side_label}_Finger{finger_index}{segment_index}")

target_bones.add("FACIAL_facialRoot")
target_bones.add("FACIAL_jaw")
target_bones.update(hand_skeleton_helper.EXTRA_ARM_HELPER_BONES)

bpy.context.view_layer.objects.active = franklin_armature
bpy.ops.object.mode_set(mode="EDIT")
for edit_bone_item in list(franklin_armature.data.edit_bones):
    if edit_bone_item.name not in target_bones:
        franklin_armature.data.edit_bones.remove(edit_bone_item)
bpy.ops.object.mode_set(mode="OBJECT")
print(
    project_i18n.translate(
        "franklin.skeleton_filtered", count=len(franklin_armature.data.bones)
    )
)

for cleanup_name in (f"{skeleton_arm_name}.mesh", "player_one.mesh", "SKEL_ROOT"):
    cleanup_obj = bpy.data.objects.get(cleanup_name)
    if cleanup_obj is not None:
        bpy.data.objects.remove(cleanup_obj)

# 3. Import Shinano FBX
source_fbx_path = str(FRANKLIN_CFG["source_fbx"])
print(project_i18n.translate("franklin.importing_fbx", filename=Path(source_fbx_path).name))
bpy.ops.import_scene.fbx(filepath=source_fbx_path)
shinano_armature = bpy.data.objects["Armature"]

# Load optional Unity scene overrides (defaults strictly to 1.0 when blank/absent)
unity_config = unity_scene_helper.load_unity_avatar_from_cfg(
    FRANKLIN_CFG,
    i18n_module=project_i18n,
    character_hints=("shinano", "casual"),
)

armature_override_scale = unity_config.get("armature_scale", (1.0, 1.0, 1.0))
shinano_armature.scale = (
    shinano_armature.scale.x * armature_override_scale[0],
    shinano_armature.scale.y * armature_override_scale[1],
    shinano_armature.scale.z * armature_override_scale[2],
)

# Rotate arms to GTA V A-pose (-55 degrees) and apply optional Unity bone scales
bpy.context.view_layer.objects.active = shinano_armature
bpy.ops.object.mode_set(mode="POSE")
shinano_armature.pose.bones["Upper_arm.L"].rotation_mode = "XYZ"
shinano_armature.pose.bones["Upper_arm.L"].rotation_euler = (-math.radians(55), 0, 0)
shinano_armature.pose.bones["Upper_arm.R"].rotation_mode = "XYZ"
shinano_armature.pose.bones["Upper_arm.R"].rotation_euler = (-math.radians(55), 0, 0)
applied_pose_bones = unity_scene_helper.apply_unity_bone_scales_to_pose(
    shinano_armature, unity_config
)
bpy.ops.object.mode_set(mode="OBJECT")
if applied_pose_bones:
    print(
        project_i18n.translate(
            "unity_scene.applied_bones", count=len(applied_pose_bones)
        )
    )


def load_fbx_face_loop_normals(fbx_path: str):
    """Read IndexToDirect facial loop normals directly from the binary FBX file."""
    with open(fbx_path, "rb") as fbx_file:
        fbx_bytes = fbx_file.read()
    nodes = read_fbx_nodes(fbx_bytes)
    objs = next(node_item for node_item in nodes if node_item[0] == "Objects")[2]
    for child_item in objs:
        if child_item[0] == "Geometry" and len(child_item[1]) >= 3 and child_item[1][2] == "Mesh":
            if child_item[1][1].split("\x00")[0] != "Shinano_face":
                continue
            norm_layer = next(
                (sub_child for sub_child in child_item[2] if sub_child[0] == "LayerElementNormal"),
                None,
            )
            norms = next((layer_prop[1][0] for layer_prop in norm_layer[2] if layer_prop[0] == "Normals"), [])
            norm_idx = next((layer_prop[1][0] for layer_prop in norm_layer[2] if layer_prop[0] == "NormalsIndex"), [])
            result_normals = []
            for entry_idx in norm_idx:
                result_normals.append(
                    (float(norms[entry_idx * 3]), float(norms[entry_idx * 3 + 1]), float(norms[entry_idx * 3 + 2]))
                )
            return result_normals
    return None


body_rest_loop_normals = load_fbx_face_loop_normals(source_fbx_path)
print(
    project_i18n.translate(
        "franklin.face_normals_recovered",
        count=len(body_rest_loop_normals) if body_rest_loop_normals else 0,
    )
)

# Load and apply v5 facial blendshapes onto Body
anim_path = str(FRANKLIN_CFG["face_anim"])
face_shapes = load_anim_blendshapes(anim_path)
print(
    project_i18n.translate(
        "franklin.loading_blendshapes", count=len(face_shapes), path=anim_path
    )
)

body_obj = bpy.data.objects.get("Body")
if body_obj and body_obj.data.shape_keys:
    for key_block in body_obj.data.shape_keys.key_blocks:
        key_block.value = 0.0
    active_shape_count = 0
    for shape_name, shape_val in face_shapes.items():
        key_block = body_obj.data.shape_keys.key_blocks.get(shape_name)
        if key_block:
            key_block.value = shape_val
            if shape_val > 0:
                active_shape_count += 1
    print(project_i18n.translate("franklin.applied_blendshapes", count=active_shape_count))

# Enable clothing shrink blendshapes to prevent body clipping
mesh_shape_presets = {
    "Body_base": {
        "Shrink_tights": 1.0,
        "Shrink_boots": 1.0,
        "Shrink_dress": 1.0,
        "Shrink_skirt": 1.0,
        "Shrink_sweater": 1.0,
        "Corset": 1.0,
        "Toe_heels": 1.0,
    },
    "Cloth_tights": {
        "Shrink_boots": 1.0,
        "Corset": 1.0,
        "Toe_heels": 1.0,
    },
    "Cloth_dress": {
        "Ribbon_OFF": 1.0,
        "Corset_OFF": 1.0,
    },
    "Cloth_skirt": {
        "Corset_OFF": 1.0,
    },
}
for mesh_name, shape_dict in mesh_shape_presets.items():
    target_obj = bpy.data.objects.get(mesh_name)
    if target_obj and target_obj.data.shape_keys:
        for shape_name, shape_value in shape_dict.items():
            key_block = target_obj.data.shape_keys.key_blocks.get(shape_name)
            if key_block:
                key_block.value = shape_value

bpy.context.view_layer.update()

# Derive FACIAL_jaw skinning weights from the vrc.v_aa shape key displacement
body_jaw_weights = {}
orig_body_obj = bpy.data.objects.get("Body")
if orig_body_obj and orig_body_obj.data.shape_keys:
    shape_key_aa = orig_body_obj.data.shape_keys.key_blocks.get("vrc.v_aa")
    basis_shape_key = orig_body_obj.data.shape_keys.key_blocks.get("Basis")
    if shape_key_aa and basis_shape_key:
        for vertex_item in orig_body_obj.data.vertices:
            delta_z = shape_key_aa.data[vertex_item.index].co.z - basis_shape_key.data[vertex_item.index].co.z
            if delta_z < -0.0005:
                jaw_weight = min(0.35, max(0.0, (abs(delta_z) / 0.0075) * 0.35))
                body_jaw_weights[vertex_item.index] = jaw_weight
        print(
            project_i18n.translate(
                "franklin.jaw_weights_mapped", count=len(body_jaw_weights)
            )
        )

include_mesh_names = [
    "Body",
    "Body_base",
    "Cloth_sweater",
    "Cloth_skirt",
    "Cloth_tights",
    "Cloth_boots",
    "Hair_back",
    "Hair_bang",
    "Hair_base",
    "Hair_side",
    "Other_ear",
    "Other_tail",
]

hair_mode, hair_reason = unity_scene_helper.resolve_hair_mode(
    FRANKLIN_CFG.get("fbx_hair", ""),
    unity_config=unity_config,
)
custom_hair_mesh_names = set()
custom_hair_armatures = []
if hair_mode == "custom":
    custom_hair_fbx = str(FRANKLIN_CFG["fbx_hair"]).strip()
    print(
        project_i18n.translate(
            "unity_scene.hair_custom_active", reason=hair_reason, path=custom_hair_fbx
        )
    )
    default_hair_material = None
    default_hair_ref = bpy.data.objects.get("Hair_base")
    if default_hair_ref and default_hair_ref.data.materials:
        default_hair_material = default_hair_ref.data.materials[0]
    for default_hair_name in ("Hair_back", "Hair_bang", "Hair_base", "Hair_side"):
        if default_hair_name in include_mesh_names:
            include_mesh_names.remove(default_hair_name)
        default_hair_obj = bpy.data.objects.get(default_hair_name)
        if default_hair_obj is not None:
            bpy.data.objects.remove(default_hair_obj)

    pre_import_objs = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=custom_hair_fbx)
    for imported_obj in bpy.data.objects:
        if imported_obj in pre_import_objs:
            continue
        if imported_obj.type == "ARMATURE":
            custom_hair_armatures.append(imported_obj)
            unity_scene_helper.apply_unity_bone_scales_to_pose(imported_obj, unity_config)
        elif imported_obj.type == "MESH":
            if "tail" in imported_obj.name.lower():
                bpy.data.objects.remove(imported_obj)
                continue
            if default_hair_material is not None:
                imported_obj.data.materials.clear()
                imported_obj.data.materials.append(default_hair_material)
            custom_hair_mesh_names.add(imported_obj.name)
            include_mesh_names.append(imported_obj.name)
else:
    print(project_i18n.translate("unity_scene.hair_fallback_default", reason=hair_reason))

bone_mapping_table = {
    "Hips": "SKEL_Pelvis",
    "Spine": "SKEL_Spine1",
    "Chest": "SKEL_Spine2",
    "Neck": "SKEL_Neck_1",
    "Head": "SKEL_Head",
    "LeftEye": "SKEL_Head",
    "RightEye": "SKEL_Head",
    "Shoulder.L": "SKEL_L_Clavicle",
    "Upper_arm.L": "SKEL_L_UpperArm",
    "Lower_arm.L": "SKEL_L_Forearm",
    "Hand.L": "SKEL_L_Hand",
    "Shoulder.R": "SKEL_R_Clavicle",
    "Upper_arm.R": "SKEL_R_UpperArm",
    "Lower_arm.R": "SKEL_R_Forearm",
    "Hand.R": "SKEL_R_Hand",
    "Upper_leg.L": "SKEL_L_Thigh",
    "Lower_leg.L": "SKEL_L_Calf",
    "Foot.L": "SKEL_L_Foot",
    "Toe.L": "SKEL_L_Toe0",
    "Upper_leg.R": "SKEL_R_Thigh",
    "Lower_leg.R": "SKEL_R_Calf",
    "Foot.R": "SKEL_R_Foot",
    "Toe.R": "SKEL_R_Toe0",
}


def get_target_bone(source_bone_name: str) -> str:
    """Resolve a Shinano source vertex group name to its GTA V bone name."""
    if source_bone_name in bone_mapping_table:
        return bone_mapping_table[source_bone_name]
    resolved_arm_or_finger = hand_skeleton_helper.resolve_finger_or_arm_bone(source_bone_name)
    if resolved_arm_or_finger is not None:
        return resolved_arm_or_finger
    if "Hand" in source_bone_name:
        side_tag = "L" if (".L" in source_bone_name or "Left" in source_bone_name or "_L" in source_bone_name) else "R"
        return f"SKEL_{side_tag}_Hand"
    if source_bone_name.startswith("Hair_") or source_bone_name.startswith("Other_ear"):
        return "SKEL_Head"
    if source_bone_name.startswith("Breast_") or source_bone_name.startswith("Ribbon"):
        return "SKEL_Spine2"
    if source_bone_name.startswith("Butt.L"):
        return "SKEL_L_Thigh"
    if source_bone_name.startswith("Butt.R"):
        return "SKEL_R_Thigh"
    if "support" in source_bone_name:
        side_tag = "L" if (".L" in source_bone_name or "Left" in source_bone_name or "_L" in source_bone_name) else "R"
        if "Lower" in source_bone_name or "support2" in source_bone_name or "support3" in source_bone_name:
            return f"SKEL_{side_tag}_Forearm"
        return f"SKEL_{side_tag}_UpperArm"
    if source_bone_name.startswith("Skirt_"):
        if ".L" in source_bone_name:
            return "SKEL_L_Thigh"
        if ".R" in source_bone_name:
            return "SKEL_R_Thigh"
        return "SKEL_Pelvis"
    if source_bone_name.startswith("Tail") or source_bone_name.startswith("Belt"):
        return "SKEL_Pelvis"
    return "SKEL_Pelvis"


scale_factor, z_offset = unity_scene_helper.compute_gtav_height_mapping(
    bpy,
    unity_config,
    include_mesh_names,
    ("Body", "Body_base", "Cloth_boots"),
    -0.907,
    0.640,
    0.106,
    1.132,
)

depsgraph = bpy.context.evaluated_depsgraph_get()
processed_objs = []
kept_body_normals = None

for mesh_name in include_mesh_names:
    src_obj = bpy.data.objects.get(mesh_name)
    if not src_obj:
        continue

    # Evaluate deformed geometry with pose and blendshapes applied
    eval_obj = src_obj.evaluated_get(depsgraph)
    new_mesh = bpy.data.meshes.new_from_object(eval_obj)

    # Triangulate mesh and strip alpha eye-overlay faces on Body
    bm_data = bmesh.new()
    bm_data.from_mesh(new_mesh)
    if mesh_name == "Body":
        alpha_indices = [
            mat_idx
            for mat_idx, mat_item in enumerate(src_obj.data.materials)
            if "alpha" in mat_item.name.lower()
        ]
        orig_loop_layer = bm_data.loops.layers.int.new("orig_loop_idx")
        loop_counter = 0
        for face_elem in bm_data.faces:
            for loop_item in face_elem.loops:
                loop_item[orig_loop_layer] = loop_counter
                loop_counter += 1
        if alpha_indices:
            del_faces = [face_elem for face_elem in bm_data.faces if face_elem.material_index in alpha_indices]
            bmesh.ops.delete(bm_data, geom=del_faces, context="FACES")
            del_verts = [vert_item for vert_item in bm_data.verts if not vert_item.link_faces]
            bmesh.ops.delete(bm_data, geom=del_verts, context="VERTS")
        bmesh.ops.triangulate(bm_data, faces=bm_data.faces)
        kept_loop_indices = []
        for face_elem in bm_data.faces:
            face_elem.smooth = True
            for loop_item in face_elem.loops:
                kept_loop_indices.append(loop_item[orig_loop_layer])
        bm_data.to_mesh(new_mesh)
        bm_data.free()
        new_mesh.update()
        print(
            project_i18n.translate(
                "franklin.body_triangulated", count=len(new_mesh.vertices)
            )
        )
    else:
        bmesh.ops.triangulate(bm_data, faces=bm_data.faces)
        for face_elem in bm_data.faces:
            face_elem.smooth = True
        bm_data.to_mesh(new_mesh)
        bm_data.free()
        new_mesh.update()

    # Transform evaluated mesh vertices into GTA V world space
    eval_world_matrix = eval_obj.matrix_world
    for vert_item in new_mesh.vertices:
        vert_coord = eval_world_matrix @ vert_item.co
        vert_item.co.x = vert_coord.x * scale_factor
        vert_item.co.y = vert_coord.y * scale_factor
        vert_item.co.z = vert_coord.z * scale_factor + z_offset

    if mesh_name == "Body" and body_rest_loop_normals and len(kept_loop_indices) == len(new_mesh.loops):
        kept_body_normals = [body_rest_loop_normals[entry_idx] for entry_idx in kept_loop_indices]
        print(
            project_i18n.translate(
                "franklin.body_normals_prepared", count=len(kept_body_normals)
            )
        )
    new_mesh.update()

    new_obj = bpy.data.objects.new(f"proc_{mesh_name}", new_mesh)
    bpy.context.collection.objects.link(new_obj)

    # Copy non-alpha material slots
    for mat_slot_item in src_obj.data.materials:
        if mesh_name == "Body" and "alpha" in mat_slot_item.name.lower():
            continue
        new_obj.data.materials.append(mat_slot_item)

    # Remap vertex groups to GTA V bones
    vert_weights = {vert_idx: {} for vert_idx in range(len(new_mesh.vertices))}
    for vgroup in src_obj.vertex_groups:
        target_bone_name = get_target_bone(vgroup.name)
        for src_vert in src_obj.data.vertices:
            if src_vert.index < len(new_mesh.vertices):
                for group_weight in src_vert.groups:
                    if group_weight.group == vgroup.index and group_weight.weight > 0.001:
                        vert_weights[src_vert.index][target_bone_name] = (
                            vert_weights[src_vert.index].get(target_bone_name, 0.0) + group_weight.weight
                        )

    for vertex_idx, weights in vert_weights.items():
        total_weight = sum(weights.values())
        if total_weight > 0:
            for target_bone_name, weight_val in weights.items():
                target_vgroup = new_obj.vertex_groups.get(target_bone_name)
                if not target_vgroup:
                    target_vgroup = new_obj.vertex_groups.new(name=target_bone_name)
                target_vgroup.add([vertex_idx], weight_val / total_weight, "ADD")
        else:
            default_bone = (
                "SKEL_Head"
                if mesh_name in ["Body", "Hair_bang", "Hair_side", "Hair_back", "Hair_base", "Other_ear"]
                or mesh_name in custom_hair_mesh_names
                else "SKEL_Pelvis"
            )
            default_vgroup = new_obj.vertex_groups.get(default_bone)
            if not default_vgroup:
                default_vgroup = new_obj.vertex_groups.new(name=default_bone)
            default_vgroup.add([vertex_idx], 1.0, "REPLACE")

    if mesh_name == "Body" and body_jaw_weights:
        jaw_vgroup = new_obj.vertex_groups.get("FACIAL_jaw")
        if not jaw_vgroup:
            jaw_vgroup = new_obj.vertex_groups.new(name="FACIAL_jaw")
        head_vgroup = new_obj.vertex_groups.get("SKEL_Head")
        if not head_vgroup:
            head_vgroup = new_obj.vertex_groups.new(name="SKEL_Head")
        for vertex_idx, jaw_weight in body_jaw_weights.items():
            if vertex_idx < len(new_mesh.vertices):
                jaw_vgroup.add([vertex_idx], jaw_weight, "REPLACE")
                head_vgroup.add([vertex_idx], max(0.0, 1.0 - jaw_weight), "REPLACE")
        print(project_i18n.translate("franklin.jaw_weights_applied"))

    processed_objs.append(new_obj)

# Relocate arm, hand, and 30 finger bones on Franklin's GTA V armature to match Shinano
hand_bone_world_targets = hand_skeleton_helper.extract_avatar_arm_hand_targets(
    shinano_armature, scale_factor, z_offset
)
relocated_arm_bones = hand_skeleton_helper.relocate_blender_armature_bones(
    franklin_armature, hand_bone_world_targets
)
print(project_i18n.translate("franklin.arm_bones_relocated", count=relocated_arm_bones))

# Remove temporary source meshes and armatures
for temp_obj in [shinano_armature] + custom_hair_armatures + [
    bpy.data.objects.get(mesh_name_item)
    for mesh_name_item in list(include_mesh_names)
    if bpy.data.objects.get(mesh_name_item)
]:
    bpy.data.objects.remove(temp_obj)

# 5. Join all processed meshes into a single drawable mesh
bpy.ops.object.select_all(action="DESELECT")
for proc_obj in processed_objs:
    proc_obj.select_set(True)
bpy.context.view_layer.objects.active = processed_objs[0]
bpy.ops.object.join()
joined_mesh_obj = processed_objs[0]
joined_mesh_obj.name = "SKEL_ROOT"

for poly_face in joined_mesh_obj.data.polygons:
    poly_face.use_smooth = True
joined_mesh_obj.data.update()

for vgroup in list(joined_mesh_obj.vertex_groups):
    if vgroup.name not in target_bones:
        joined_mesh_obj.vertex_groups.remove(vgroup)

bpy.context.view_layer.objects.active = joined_mesh_obj
bpy.ops.object.vertex_group_limit_total(limit=4)
bpy.ops.object.vertex_group_normalize_all()
print(
    project_i18n.translate(
        "franklin.mesh_joined", count=len(joined_mesh_obj.data.vertices)
    )
)

# 6. Create ped_default.sps shader materials bound to the 2x2 Atlas
atlas_tex_path = str(FRANKLIN_CFG["atlas_png"])
norm_tex_path = str(FRANKLIN_CFG["normal_png"])
spec_tex_path = str(FRANKLIN_CFG["spec_png"])

atlas_img = bpy.data.images.load(atlas_tex_path)
flat_norm_img = bpy.data.images.load(norm_tex_path)
black_spec_img = bpy.data.images.load(spec_tex_path)

quadrant_map = {
    "Shinano_face": (0.0, 0.5),
    "Shinano_body": (0.5, 0.5),
    "Shinano_costume": (0.0, 0.0),
    "Shinano_hair": (0.5, 0.0),
}

shader_materials = {}
for mat_name in ["Shinano_face", "Shinano_body", "Shinano_costume", "Shinano_hair"]:
    shader_material = create_shader("ped_default.sps")
    shader_material.name = mat_name

    diff_node = shader_material.node_tree.nodes.get("DiffuseSampler")
    if diff_node:
        diff_node.image = atlas_img
        diff_node.texture_properties.embedded = False

    bump_node = shader_material.node_tree.nodes.get("BumpSampler")
    if bump_node:
        bump_node.image = flat_norm_img
        bump_node.texture_properties.embedded = False

    spec_node = shader_material.node_tree.nodes.get("SpecSampler")
    if spec_node:
        spec_node.image = black_spec_img
        spec_node.texture_properties.embedded = False

    for shader_node in shader_material.node_tree.nodes:
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

    shader_materials[mat_name] = shader_material

slot_to_key = {}
for slot_idx, mat_item in enumerate(joined_mesh_obj.data.materials):
    if not mat_item:
        continue
    matched = False
    for mat_key, shader_material in shader_materials.items():
        if mat_key.lower() in mat_item.name.lower():
            joined_mesh_obj.data.materials[slot_idx] = shader_material
            slot_to_key[slot_idx] = mat_key
            matched = True
            break
    if not matched:
        joined_mesh_obj.data.materials[slot_idx] = shader_materials["Shinano_costume"]
        slot_to_key[slot_idx] = "Shinano_costume"

# Remap UVs into the 2x2 Atlas quadrants
uv_layer = joined_mesh_obj.data.uv_layers[0]
uv_layer.name = "UVMap 0"
for poly_item in joined_mesh_obj.data.polygons:
    material_key = slot_to_key.get(poly_item.material_index, "Shinano_costume")
    uv_offset_u, uv_offset_v = quadrant_map[material_key]
    for loop_idx in poly_item.loop_indices:
        uv_coord = uv_layer.data[loop_idx].uv
        uv_coord.x = uv_coord.x * 0.5 + uv_offset_u
        uv_coord.y = uv_coord.y * 0.5 + uv_offset_v

bpy.context.view_layer.objects.active = joined_mesh_obj
bpy.ops.sollumz.color_attrs_add_missing()
bpy.ops.sollumz.uv_maps_add_missing()

color_attr_1 = joined_mesh_obj.data.color_attributes.get("Color 1")
if color_attr_1:
    for color_item in color_attr_1.data:
        color_item.color = (1.0, 1.0, 1.0, 1.0)

color_attr_2 = joined_mesh_obj.data.color_attributes.get("Color 2")
if color_attr_2:
    for color_item in color_attr_2.data:
        color_item.color = (0.0, 0.0, 0.0, 0.0)

# Apply soft anime spherical face normals
if kept_body_normals:
    joined_mesh_obj.data.calc_normals_split()
    all_normals = [tuple(loop_elem.normal) for loop_elem in joined_mesh_obj.data.loops]
    num_face_loops = len(kept_body_normals)
    all_normals[:num_face_loops] = kept_body_normals

    mesh_vertices = joined_mesh_obj.data.vertices
    mesh_loops = joined_mesh_obj.data.loops
    for poly_item in joined_mesh_obj.data.polygons:
        material_key = slot_to_key.get(poly_item.material_index, "Shinano_costume")
        if material_key == "Shinano_face":
            for loop_idx in poly_item.loop_indices:
                vertex_pos = mesh_vertices[mesh_loops[loop_idx].vertex_index].co
                if vertex_pos.y < -0.045 and 0.61 < vertex_pos.z < 0.77 and abs(vertex_pos.x) < 0.085:
                    norm_x = vertex_pos.x * 2.2
                    norm_y = -1.0
                    norm_z = (vertex_pos.z - 0.69) * 1.4
                    norm_len = math.sqrt(norm_x * norm_x + norm_y * norm_y + norm_z * norm_z)
                    all_normals[loop_idx] = (norm_x / norm_len, norm_y / norm_len, norm_z / norm_len)
        elif material_key == "Shinano_body":
            for loop_idx in poly_item.loop_indices:
                vertex_pos = mesh_vertices[mesh_loops[loop_idx].vertex_index].co
                if vertex_pos.y < -0.015 and 0.55 < vertex_pos.z < 0.65 and abs(vertex_pos.x) < 0.065:
                    norm_x = vertex_pos.x * 3.5
                    norm_y = -1.0
                    norm_z = -0.1
                    norm_len = math.sqrt(norm_x * norm_x + norm_y * norm_y + norm_z * norm_z)
                    all_normals[loop_idx] = (norm_x / norm_len, norm_y / norm_len, norm_z / norm_len)

    joined_mesh_obj.data.normals_split_custom_set(all_normals)
    joined_mesh_obj.data.update()

import sollumz.ydr.ydrexport as ydrexport

ydrexport.triangulate_mesh = lambda mesh_data: mesh_data

# 7. Configure Sollumz Drawable Dictionary hierarchy
drawable_dict_empty = create_empty_object(SollumType.DRAWABLE_DICTIONARY)
drawable_dict_empty.name = "uppr_008_u"

franklin_armature.sollum_type = SollumType.DRAWABLE
franklin_armature.name = "uppr_008_u"
franklin_armature.parent = drawable_dict_empty
franklin_armature.drawable_properties.lod_dist_high = 9998.0
franklin_armature.drawable_properties.lod_dist_med = 9998.0
franklin_armature.drawable_properties.lod_dist_low = 9998.0
franklin_armature.drawable_properties.lod_dist_vlow = 9998.0

for arm_bone in franklin_armature.data.bones:
    set_recommended_bone_properties(arm_bone)

convert_obj_to_model(joined_mesh_obj)
joined_mesh_obj.parent = franklin_armature

armature_modifier = joined_mesh_obj.modifiers.new("Armature", "ARMATURE")
armature_modifier.object = franklin_armature

# 8. Export GEN8 drawables and relocated .yft skeleton
exported_dir = operating_system.path.join(str(FRANKLIN_CFG["exported_models_dir"]), "")
operating_system.makedirs(exported_dir, exist_ok=True)
print(project_i18n.translate("franklin.exporting_models"))
bpy.ops.object.select_all(action="DESELECT")
drawable_dict_empty.select_set(True)
bpy.context.view_layer.objects.active = drawable_dict_empty

export_result_008 = bpy.ops.sollumz.export_assets(
    directory=exported_dir,
    direct_export=True,
    use_custom_settings=True,
    target_versions={"GEN8"},
    target_formats={"NATIVE", "CWXML"},
    limit_to_selected=False,
)
print(
    project_i18n.translate(
        "franklin.export_result", slot_name="uppr_008_u", result=export_result_008
    )
)

drawable_dict_empty.name = "uppr_000_u"
franklin_armature.name = "uppr_000_u"
export_result_000 = bpy.ops.sollumz.export_assets(
    directory=exported_dir,
    direct_export=True,
    use_custom_settings=True,
    target_versions={"GEN8"},
    target_formats={"NATIVE", "CWXML"},
    limit_to_selected=False,
)
print(
    project_i18n.translate(
        "franklin.export_result", slot_name="uppr_000_u", result=export_result_000
    )
)

drawable_dict_empty.name = "uppr_001_u"
franklin_armature.name = "uppr_001_u"
export_result_001 = bpy.ops.sollumz.export_assets(
    directory=exported_dir,
    direct_export=True,
    use_custom_settings=True,
    target_versions={"GEN8"},
    target_formats={"NATIVE", "CWXML"},
    limit_to_selected=False,
)
print(
    project_i18n.translate(
        "franklin.export_result", slot_name="uppr_001_u", result=export_result_001
    )
)

yft_output_path = Path(FRANKLIN_CFG["target_yft"])
updated_yft_bones, total_yft_bones, max_yft_delta = hand_skeleton_helper.patch_yft_skeleton(
    skeleton_yft_path, yft_output_path, hand_bone_world_targets
)
print(
    project_i18n.translate(
        "franklin.yft_exported",
        path=yft_output_path,
        updated=updated_yft_bones,
        total=total_yft_bones,
        max_delta=max_yft_delta,
    )
)
print(project_i18n.translate("franklin.build_done"))
