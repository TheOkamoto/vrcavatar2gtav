#!/usr/bin/env python3
"""
michael_er_geometry_layer.py
============================
Layer 1 of 2 for the Shinano Eternal Reunion Blender builder (`build_michael_er`).

Owns binary FBX custom split-normal parsing, universal bone remapping tables
(`HUMAN_TO_GTAV_BONE_MAP`), Pocket Watch matrix alignment, hip/thigh skirt
vertex weight blending, mesh inventory culling/UV/skinning baking inside
Blender, and custom anime facial split-normal restoration.
"""

import math
import os
import struct
import sys
from pathlib import Path
import zlib

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import error_handler_helper as err_helper
import eye_blink_helper
import hand_skeleton_helper
import physbone_helper
import unity_scene_helper
import blender_hair_helper
import vrc2gtav_i18n as i18n

try:
    import mathutils
except ImportError:
    mathutils = None


CHARACTER_PROFILES = {
    "michael": {
        "ped_name": "player_zero",
        "skeleton_yft": "player_zero.yft",
        "export_drawables": ["uppr_000_r", "uppr_000_u", "uppr_001_u", "uppr_004_u"],
        "target_z_min": -0.907,
        "target_z_max": 0.645,
        "arm_pose_degrees": -55.0,
    },
    "franklin": {
        "ped_name": "player_one",
        "skeleton_yft": "player_one.yft",
        "export_drawables": ["uppr_008_u", "uppr_000_u", "uppr_001_u"],
        "target_z_min": -0.907,
        "target_z_max": 0.640,
        "arm_pose_degrees": -55.0,
    },
    "trevor": {
        "ped_name": "player_two",
        "skeleton_yft": "player_two.yft",
        "export_drawables": ["uppr_000_r", "uppr_000_u", "uppr_001_u"],
        "target_z_min": -0.907,
        "target_z_max": 0.645,
        "arm_pose_degrees": -55.0,
    },
}


# ---------------------------------------------------------------------------
# Binary FBX node reader for IndexToDirect custom face normals
# ---------------------------------------------------------------------------
def parse_fbx_binary_nodes(fbx_raw_bytes):
    """Parse binary FBX node records into a nested Python list tree."""
    fbx_version = struct.unpack_from("<I", fbx_raw_bytes, 23)[0]
    is_64bit_header = fbx_version >= 7500
    header_format = "<QQQB" if is_64bit_header else "<IIIB"
    header_byte_size = 25 if is_64bit_header else 13

    def parse_single_property(byte_pos):
        """Decode one FBX node property value and return (value, next_pos)."""
        type_code = chr(fbx_raw_bytes[byte_pos])
        byte_pos += 1
        if type_code == "Y":
            return struct.unpack_from("<h", fbx_raw_bytes, byte_pos)[0], byte_pos + 2
        if type_code == "C":
            return bool(fbx_raw_bytes[byte_pos]), byte_pos + 1
        if type_code == "I":
            return struct.unpack_from("<i", fbx_raw_bytes, byte_pos)[0], byte_pos + 4
        if type_code == "F":
            return struct.unpack_from("<f", fbx_raw_bytes, byte_pos)[0], byte_pos + 4
        if type_code == "D":
            return struct.unpack_from("<d", fbx_raw_bytes, byte_pos)[0], byte_pos + 8
        if type_code == "L":
            return struct.unpack_from("<q", fbx_raw_bytes, byte_pos)[0], byte_pos + 8
        if type_code in ("S", "R"):
            str_len = struct.unpack_from("<I", fbx_raw_bytes, byte_pos)[0]
            byte_pos += 4
            raw_slice = fbx_raw_bytes[byte_pos : byte_pos + str_len]
            decoded_val = (
                raw_slice.decode("utf-8", errors="replace")
                if type_code == "S"
                else raw_slice
            )
            return decoded_val, byte_pos + str_len
        if type_code in ("f", "d", "l", "i", "b"):
            array_length, encoding_flag, compressed_len = struct.unpack_from(
                "<III", fbx_raw_bytes, byte_pos
            )
            byte_pos += 12
            raw_array = fbx_raw_bytes[byte_pos : byte_pos + compressed_len]
            byte_pos += compressed_len
            if encoding_flag == 1:
                raw_array = zlib.decompress(raw_array)
            format_map = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "B"}
            unpacked_array = struct.unpack(
                f"<{array_length}{format_map[type_code]}", raw_array
            )
            return unpacked_array, byte_pos
        raise ValueError(
            i18n.translate("michael.build.unknown_fbx_prop", type_code=type_code)
        )

    def parse_single_node(byte_pos):
        """Recursively decode one FBX node and its children."""
        end_offset, prop_count, prop_byte_len, name_len = struct.unpack_from(
            header_format, fbx_raw_bytes, byte_pos
        )
        if end_offset == 0:
            return None, byte_pos + header_byte_size
        byte_pos += header_byte_size
        node_name = fbx_raw_bytes[byte_pos : byte_pos + name_len].decode(
            "utf-8", errors="replace"
        )
        byte_pos += name_len
        prop_list = []
        prop_end_pos = byte_pos + prop_byte_len
        for _prop_index in range(prop_count):
            prop_val, byte_pos = parse_single_property(byte_pos)
            prop_list.append(prop_val)
        byte_pos = prop_end_pos
        child_nodes = []
        while byte_pos < end_offset:
            child_item, byte_pos = parse_single_node(byte_pos)
            if child_item is None:
                break
            child_nodes.append(child_item)
        return (node_name, prop_list, child_nodes), end_offset

    cursor_pos = 27
    root_nodes = []
    while cursor_pos < len(fbx_raw_bytes) - header_byte_size:
        parsed_node, cursor_pos = parse_single_node(cursor_pos)
        if parsed_node is None:
            break
        root_nodes.append(parsed_node)
    return root_nodes


def load_fbx_face_loop_normals(fbx_file_path, target_geometry_names=None):
    """Extract per-loop IndexToDirect facial normals from the source FBX."""
    if not os.path.exists(fbx_file_path):
        return None
    if target_geometry_names is None:
        target_geometry_names = ["Shinano_face", "Body", "Face"]

    with open(fbx_file_path, "rb") as fbx_file:
        fbx_bytes = fbx_file.read()

    fbx_nodes = parse_fbx_binary_nodes(fbx_bytes)
    objects_node = next(
        (node_item for node_item in fbx_nodes if node_item[0] == "Objects"), None
    )
    if not objects_node:
        return None

    for child_node in objects_node[2]:
        if (
            child_node[0] == "Geometry"
            and len(child_node[1]) >= 3
            and child_node[1][2] == "Mesh"
        ):
            geom_name = child_node[1][1].split("\x00")[0]
            if geom_name not in target_geometry_names:
                continue
            normal_layer = next(
                (
                    sub_node
                    for sub_node in child_node[2]
                    if sub_node[0] == "LayerElementNormal"
                ),
                None,
            )
            if not normal_layer:
                continue
            normals_flat = next(
                (
                    sub_item[1][0]
                    for sub_item in normal_layer[2]
                    if sub_item[0] == "Normals"
                ),
                [],
            )
            normals_index = next(
                (
                    sub_item[1][0]
                    for sub_item in normal_layer[2]
                    if sub_item[0] == "NormalsIndex"
                ),
                [],
            )
            if normals_flat and normals_index:
                loop_normals = []
                for normal_idx in normals_index:
                    base_idx = normal_idx * 3
                    loop_normals.append(
                        (
                            float(normals_flat[base_idx]),
                            float(normals_flat[base_idx + 1]),
                            float(normals_flat[base_idx + 2]),
                        )
                    )
                return loop_normals
    return None


# ---------------------------------------------------------------------------
# Universal GTA V bone mapper (Modular Avatar bake)
# ---------------------------------------------------------------------------
HUMAN_TO_GTAV_BONE_MAP = {
    "Hips": "SKEL_Pelvis",
    "Pelvis": "SKEL_Pelvis",
    "Spine": "SKEL_Spine1",
    "Chest": "SKEL_Spine2",
    "UpperChest": "SKEL_Spine3",
    "Upper_chest": "SKEL_Spine3",
    "Neck": "SKEL_Neck_1",
    "Head": "SKEL_Head",
    "LeftEye": "SKEL_Head",
    "RightEye": "SKEL_Head",
    "Eye.L": "SKEL_Head",
    "Eye.R": "SKEL_Head",
    "Shoulder.L": "SKEL_L_Clavicle",
    "LeftShoulder": "SKEL_L_Clavicle",
    "Upper_arm.L": "SKEL_L_UpperArm",
    "UpperArm.L": "SKEL_L_UpperArm",
    "LeftUpperArm": "SKEL_L_UpperArm",
    "Lower_arm.L": "SKEL_L_Forearm",
    "LowerArm.L": "SKEL_L_Forearm",
    "LeftLowerArm": "SKEL_L_Forearm",
    "Hand.L": "SKEL_L_Hand",
    "LeftHand": "SKEL_L_Hand",
    "Shoulder.R": "SKEL_R_Clavicle",
    "RightShoulder": "SKEL_R_Clavicle",
    "Upper_arm.R": "SKEL_R_UpperArm",
    "UpperArm.R": "SKEL_R_UpperArm",
    "RightUpperArm": "SKEL_R_UpperArm",
    "Lower_arm.R": "SKEL_R_Forearm",
    "LowerArm.R": "SKEL_R_Forearm",
    "RightLowerArm": "SKEL_R_Forearm",
    "Hand.R": "SKEL_R_Hand",
    "RightHand": "SKEL_R_Hand",
    "Upper_leg.L": "SKEL_L_Thigh",
    "UpperLeg.L": "SKEL_L_Thigh",
    "LeftUpperLeg": "SKEL_L_Thigh",
    "Lower_leg.L": "SKEL_L_Calf",
    "LowerLeg.L": "SKEL_L_Calf",
    "LeftLowerLeg": "SKEL_L_Calf",
    "Foot.L": "SKEL_L_Foot",
    "LeftFoot": "SKEL_L_Foot",
    "Toe.L": "SKEL_L_Toe0",
    "LeftToes": "SKEL_L_Toe0",
    "Upper_leg.R": "SKEL_R_Thigh",
    "UpperLeg.R": "SKEL_R_Thigh",
    "RightUpperLeg": "SKEL_R_Thigh",
    "Lower_leg.R": "SKEL_R_Calf",
    "LowerLeg.R": "SKEL_R_Calf",
    "RightLowerLeg": "SKEL_R_Calf",
    "Foot.R": "SKEL_R_Foot",
    "RightFoot": "SKEL_R_Foot",
    "Toe.R": "SKEL_R_Toe0",
    "RightToes": "SKEL_R_Toe0",
}


HEAD_ACCESSORY_MESH_NAMES = frozenset({
    "Body",
    "UN2_Beret",
    "UN3_Glasses",
    "Bangs",
    "Top Back",
    "Under Side",
    "Back",
    "Side Bangs",
    "Side",
    "In Hair",
    "Ribbon",
    "Ears",
    "Earring_L",
    "Earring_R",
    "_Halo",
    "_Pin.Back",
    "_Pin.R",
    "_Pin.L2",
    "Hair_base",
    "Hair_bang",
    "Hair_back",
    "Hair_side",
    "Other_ear",
})


def smoothstep_unit(scalar_val):
    """Smooth Hermite interpolation clamped to [0.0, 1.0]."""
    clamped_val = max(0.0, min(1.0, float(scalar_val)))
    return clamped_val * clamped_val * (3.0 - 2.0 * clamped_val)


def compute_pocket_watch_align_matrix(
    arm_outfit,
    arm_watch,
    watch_scale=1.0,
    armature_scale=(1.0, 1.0, 1.0),
):
    """Compute the 4x4 matrix aligning the Pocket Watch to the waist watch ring."""
    watch_bone_name = "Pocket Watch_Root"
    if not arm_outfit or watch_bone_name not in arm_outfit.data.bones:
        raise RuntimeError(
            i18n.translate("michael.build.watch_bone_missing_outfit", bone=watch_bone_name)
        )
    if not arm_watch or watch_bone_name not in arm_watch.data.bones:
        raise RuntimeError(
            i18n.translate("michael.build.watch_bone_missing_watch", bone=watch_bone_name)
        )

    outfit_bone = arm_outfit.data.bones[watch_bone_name]
    watch_bone = arm_watch.data.bones[watch_bone_name]

    outfit_matrix = arm_outfit.matrix_world @ outfit_bone.matrix_local
    watch_matrix = arm_watch.matrix_world @ watch_bone.matrix_local

    # Normalize 3x3 rotations before inverting to isolate orientation and apply watch scale
    outfit_rot_mat = outfit_matrix.to_3x3().normalized().to_4x4()
    watch_rot_mat = watch_matrix.to_3x3().normalized().to_4x4()
    watch_head_pos = arm_watch.matrix_world @ watch_bone.head_local

    # Target waist watch ring position aligned in Shinano rest coordinates
    unity_target_pos = mathutils.Vector(
        (
            -0.05371 * armature_scale[0],
            -0.07346 * armature_scale[1],
            0.82380 * armature_scale[2],
        )
    )
    return (
        mathutils.Matrix.Translation(unity_target_pos)
        @ outfit_rot_mat
        @ mathutils.Matrix.Scale(float(watch_scale), 4)
        @ watch_rot_mat.inverted()
        @ mathutils.Matrix.Translation(-watch_head_pos)
    )


def compute_skirt_vertex_weights(
    source_obj,
    orig_vert_idx,
    ydd_coord,
    vgroup_names_by_idx,
    vgroup_target_names,
):
    """Compute anatomical skirt bone weights (z_back28_high) to avoid rear clipping."""
    remapped_weights = {}
    skirt_weight = 0.0

    if orig_vert_idx < len(source_obj.data.vertices):
        src_vert = source_obj.data.vertices[orig_vert_idx]
        for grp_elem in src_vert.groups:
            if grp_elem.weight <= 0.001 or grp_elem.group not in vgroup_target_names:
                continue
            raw_name = vgroup_names_by_idx.get(grp_elem.group, "")
            target_bone = vgroup_target_names[grp_elem.group]
            if "skirt" in raw_name.lower():
                if target_bone.startswith("PB_ER_Skirt"):
                    pb_weight = grp_elem.weight * 0.75
                    remapped_weights[target_bone] = (
                        remapped_weights.get(target_bone, 0.0) + pb_weight
                    )
                    skirt_weight += grp_elem.weight * 0.25
                else:
                    skirt_weight += grp_elem.weight
            else:
                remapped_weights[target_bone] = (
                    remapped_weights.get(target_bone, 0.0) + grp_elem.weight
                )

    if skirt_weight > 0.0:
        # Vertical ramp: waist (+0.10) anchored 100% to Pelvis; hem (<= +0.02) shares up to 28%
        vertical_ramp = smoothstep_unit((0.10 - ydd_coord.z) / 0.08)
        # Front-to-back ramp: keep front (y <= -0.02) on Pelvis to prevent belly sink when sitting
        back_ramp = smoothstep_unit((ydd_coord.y + 0.02) / 0.06)
        # Left/right blend across centerline (+X left thigh, -X right thigh)
        left_right_mix = smoothstep_unit((ydd_coord.x + 0.035) / 0.070)

        thigh_cap = vertical_ramp * 0.28 * back_ramp
        thigh_weight = skirt_weight * thigh_cap
        pelvis_weight = skirt_weight - thigh_weight

        if pelvis_weight > 1e-6:
            remapped_weights["SKEL_Pelvis"] = (
                remapped_weights.get("SKEL_Pelvis", 0.0) + pelvis_weight
            )
        left_thigh_weight = thigh_weight * left_right_mix
        right_thigh_weight = thigh_weight * (1.0 - left_right_mix)
        if left_thigh_weight > 1e-6:
            remapped_weights["SKEL_L_Thigh"] = (
                remapped_weights.get("SKEL_L_Thigh", 0.0) + left_thigh_weight
            )
        if right_thigh_weight > 1e-6:
            remapped_weights["SKEL_R_Thigh"] = (
                remapped_weights.get("SKEL_R_Thigh", 0.0) + right_thigh_weight
            )

    # Enforce maximum 4 bone influences per vertex for RAGE Engine compatibility
    if len(remapped_weights) > 4:
        sorted_weights = sorted(
            remapped_weights.items(),
            key=lambda weight_entry: weight_entry[1],
            reverse=True,
        )[:4]
        remapped_weights = dict(sorted_weights)

    return remapped_weights


def resolve_gtav_target_bone(source_bone_name, mesh_name=None, bone_mapping_lower=None):
    """Map a VRChat/Unity bone name to its target GTA V RAGE skeleton bone."""
    if mesh_name == "UN3_Bag":
        lower_bone_name = source_bone_name.lower()
        if "shoulder.l" in lower_bone_name or "shoulder_l" in lower_bone_name:
            return "SKEL_L_Clavicle"
        if "shoulder.r" in lower_bone_name or "shoulder_r" in lower_bone_name:
            return "SKEL_R_Clavicle"
        if "upper_arm.l" in lower_bone_name or "upperarm.l" in lower_bone_name:
            return "SKEL_L_UpperArm"
        if "upper_arm.r" in lower_bone_name or "upperarm.r" in lower_bone_name:
            return "SKEL_R_UpperArm"
        phys_bag_bone = physbone_helper.resolve_michael_er_gtav_bone(
            source_bone_name, bone_mapping_lower=bone_mapping_lower
        )
        if phys_bag_bone is not None:
            return phys_bag_bone
        # Bind bag body, rings, and chains strictly to Spine2 so straps follow the chest
        return "SKEL_Spine2"

    if source_bone_name in HUMAN_TO_GTAV_BONE_MAP:
        return HUMAN_TO_GTAV_BONE_MAP[source_bone_name]

    # 1:1 mapping of 30 finger bones and twist helper bones
    resolved_arm_or_finger = hand_skeleton_helper.resolve_finger_or_arm_bone(source_bone_name)
    if resolved_arm_or_finger is not None:
        return resolved_arm_or_finger

    lower_name = source_bone_name.lower()
    if mesh_name in ("Nail_Ribbon", "Nail_neko", "Nail_L", "Nail_R"):
        if lower_name.startswith("bone"):
            return "SKEL_R_Finger42"
        if mesh_name == "Nail_L":
            return "SKEL_L_Hand"
        if mesh_name == "Nail_R":
            return "SKEL_R_Hand"

    # Fallback for palm bones while excluding Pocket Watch hand pointers
    if mesh_name != "Pocket Watch" and "hand" in lower_name:
        side_code = (
            "L"
            if (".L" in source_bone_name or "Left" in source_bone_name or "_L" in source_bone_name)
            else "R"
        )
        return f"SKEL_{side_code}_Hand"

    phys_er_bone = physbone_helper.resolve_michael_er_gtav_bone(
        source_bone_name, bone_mapping_lower=bone_mapping_lower
    )
    if phys_er_bone is not None:
        return phys_er_bone

    if (
        lower_name.startswith("breast")
        or lower_name.startswith("bust")
        or "chestribbon" in lower_name
        or "un_ribbon" in lower_name
    ):
        return "SKEL_Spine2"

    if mesh_name in ("Ears", "_Halo"):
        phys_ear_bone = physbone_helper.resolve_neko_mimi_gtav_bone(source_bone_name)
        if phys_ear_bone is not None:
            return phys_ear_bone

    # Restrict head keyword matching to head meshes so torso accessories ('heart', 'gear') stay safe
    allow_head_mapping = mesh_name is None or mesh_name in HEAD_ACCESSORY_MESH_NAMES
    if allow_head_mapping and (
        "hair" in lower_name
        or "cooni" in lower_name
        or "bang" in lower_name
        or "ear" in lower_name
        or "aho" in lower_name
        or "hat" in lower_name
        or "glasses" in lower_name
        or "halo" in lower_name
        or "pin" in lower_name
        or "atama" in lower_name
        or "back" in lower_name
        or "side" in lower_name
        or "ribbon" in lower_name
    ):
        return "SKEL_Head"

    if "butt.l" in lower_name or "butt_l" in lower_name:
        return "SKEL_L_Thigh"
    if "butt.r" in lower_name or "butt_r" in lower_name:
        return "SKEL_R_Thigh"

    if "support" in lower_name:
        side_code = "L" if (".l" in lower_name or "_l" in lower_name) else "R"
        if "lower" in lower_name or "support2" in lower_name or "support3" in lower_name:
            return f"SKEL_{side_code}_Forearm"
        return f"SKEL_{side_code}_UpperArm"

    if (
        "bag" in lower_name
        or "chain" in lower_name
        or "coin" in lower_name
        or "watch" in lower_name
        or "gear" in lower_name
        or "cover" in lower_name
        or "tail" in lower_name
        or "belt" in lower_name
        or "heart" in lower_name
    ):
        return "SKEL_Pelvis"

    return "SKEL_Pelvis"


def validate_build_inputs(cli_args):
    """Verify required FBX, skeleton, texture, and blendshape inputs exist."""
    required_paths = [
        (i18n.translate("michael.build.input_skeleton_label"), cli_args.skeleton_yft),
        (i18n.translate("michael.build.input_shinano_fbx_label"), cli_args.shinano_fbx),
        (i18n.translate("michael.build.input_outfit_fbx_label"), cli_args.outfit_fbx),
        (i18n.translate("michael.build.input_watch_fbx_label"), cli_args.watch_fbx),
    ]
    has_blendshapes_cfg = bool(
        getattr(cli_args, "blendshapes_cfg", "")
        and os.path.isfile(cli_args.blendshapes_cfg)
    )
    has_unity_scene = bool(
        getattr(cli_args, "unity_scene", "")
        and os.path.isfile(cli_args.unity_scene)
    )
    if not has_blendshapes_cfg and not has_unity_scene:
        required_paths.append(
            (i18n.translate("michael.build.input_face_anim_label"), cli_args.face_anim)
        )
    for desc_label, file_path in required_paths:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(
                i18n.translate(
                    "michael.build.input_missing", label=desc_label, path=file_path
                )
            )

    texture_dir = os.path.abspath(cli_args.texture_dir)
    for tex_name in (cli_args.atlas_png, cli_args.normal_png, cli_args.spec_png):
        tex_path = os.path.join(texture_dir, tex_name)
        if not os.path.isfile(tex_path):
            raise FileNotFoundError(
                i18n.translate("michael.build.atlas_tex_missing", path=tex_path)
            )

    if not (1 <= cli_args.max_verts_per_chunk <= 65535):
        raise ValueError(
            i18n.translate("michael.build.max_verts_oob", value=cli_args.max_verts_per_chunk)
        )




NEKO_HAIR_MESH_NAMES = frozenset({
    "Bangs",
    "Top Back",
    "Under Side",
    "Back",
    "Side Bangs",
    "Side",
    "In Hair",
    "Ribbon",
    "Ears",
    "_Halo",
    "_Pin.Back",
    "_Pin.R",
    "_Pin.L2",
})


def process_michael_er_mesh_inventory(
    bpy_mod,
    bmesh_mod,
    mathutils_mod,
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
):
    """Bake, shrink-cull, transform, UV-map, and skin all Eternal Reunion meshes."""
    processed_objects = []
    preserved_body_normals = None
    neko_hair_mesh_names = NEKO_HAIR_MESH_NAMES
    bpy = bpy_mod
    bmesh = bmesh_mod
    mathutils = mathutils_mod

    for mesh_name, mesh_cfg in active_mesh_configs.items():
        source_obj = bpy.data.objects.get(mesh_name)
        if not source_obj or source_obj.type != "MESH":
            print(i18n.translate("michael.build.mesh_not_found", name=mesh_name))
            continue

        print(
            i18n.translate(
                "michael.build.processing_mesh",
                name=mesh_name,
                count=len(source_obj.data.vertices),
            )
        )

        # Detect vertices shrunken by active Shrink_* keys on Body_base
        shrunk_vertex_indices = set()
        if mesh_cfg["shrink_cull"] and source_obj.data.shape_keys:
            basis_block = source_obj.data.shape_keys.key_blocks[0]
            for key_block in source_obj.data.shape_keys.key_blocks[1:]:
                is_shrink_key = key_block.name.lower().startswith("shrink_")
                if is_shrink_key and key_block.value > 0.5:
                    for vert_idx in range(len(source_obj.data.vertices)):
                        delta_vec = (
                            key_block.data[vert_idx].co - basis_block.data[vert_idx].co
                        )
                        if delta_vec.length > 0.00002:
                            shrunk_vertex_indices.add(vert_idx)

        evaluated_obj = source_obj.evaluated_get(depsgraph_eval)
        baked_mesh = bpy.data.meshes.new_from_object(evaluated_obj)

        bmesh_data = bmesh.new()
        bmesh_data.from_mesh(baked_mesh)

        orig_vert_layer = bmesh_data.verts.layers.int.new("orig_vert_idx")
        for vert_idx_counter, bmesh_vert_item in enumerate(bmesh_data.verts):
            bmesh_vert_item[orig_vert_layer] = vert_idx_counter

        if mesh_name == "Body":
            alpha_mat_indices = [
                mat_idx
                for mat_idx, mat_obj in enumerate(source_obj.data.materials)
                if mat_obj and "alpha" in mat_obj.name.lower()
            ]
            orig_loop_layer = bmesh_data.loops.layers.int.new("orig_loop_idx")
            loop_counter = 0
            for face_item in bmesh_data.faces:
                for loop_item in face_item.loops:
                    loop_item[orig_loop_layer] = loop_counter
                    loop_counter += 1
            if alpha_mat_indices:
                faces_to_remove = [
                    face_item
                    for face_item in bmesh_data.faces
                    if face_item.material_index in alpha_mat_indices
                ]
                bmesh.ops.delete(bmesh_data, geom=faces_to_remove, context="FACES")
                loose_verts = [vert for vert in bmesh_data.verts if not vert.link_faces]
                bmesh.ops.delete(bmesh_data, geom=loose_verts, context="VERTS")

            bmesh.ops.triangulate(bmesh_data, faces=bmesh_data.faces)
            kept_loop_indices = []
            for face_item in bmesh_data.faces:
                face_item.smooth = True
                for loop_item in face_item.loops:
                    kept_loop_indices.append(loop_item[orig_loop_layer])
            kept_orig_vert_indices = [
                bmesh_vert_item[orig_vert_layer] for bmesh_vert_item in bmesh_data.verts
            ]
            bmesh_data.to_mesh(baked_mesh)
            bmesh_data.free()
            baked_mesh.update()
        else:
            if mesh_name == "Pocket Watch":
                # Strip opaque glass cover (Glass_Lenz) so Roman dial and gears remain visible
                watch_materials = (
                    baked_mesh.materials
                    if len(baked_mesh.materials) > 0
                    else source_obj.data.materials
                )
                glass_mat_indices = {
                    mat_idx
                    for mat_idx, mat_obj in enumerate(watch_materials)
                    if mat_obj and "glass" in mat_obj.name.lower()
                }
                if glass_mat_indices:
                    bmesh_data.verts.ensure_lookup_table()
                    glass_faces = [
                        face_item
                        for face_item in bmesh_data.faces
                        if face_item.material_index in glass_mat_indices
                    ]
                    if glass_faces:
                        bmesh.ops.delete(bmesh_data, geom=glass_faces, context="FACES")
                        loose_verts = [
                            vert for vert in bmesh_data.verts if not vert.link_faces
                        ]
                        if loose_verts:
                            bmesh.ops.delete(bmesh_data, geom=loose_verts, context="VERTS")
                        print(
                            i18n.translate(
                                "michael.build.removed_glass_faces",
                                count=len(glass_faces),
                                name=mesh_name,
                            )
                        )

            if shrunk_vertex_indices:
                bmesh_data.verts.ensure_lookup_table()
                hidden_faces = [
                    face_item
                    for face_item in bmesh_data.faces
                    if all(
                        vert_item[orig_vert_layer] in shrunk_vertex_indices
                        for vert_item in face_item.verts
                    )
                ]
                if hidden_faces:
                    bmesh.ops.delete(bmesh_data, geom=hidden_faces, context="FACES")
                    loose_verts = [
                        vert for vert in bmesh_data.verts if not vert.link_faces
                    ]
                    bmesh.ops.delete(bmesh_data, geom=loose_verts, context="VERTS")
                    print(
                        i18n.translate(
                            "michael.build.shrink_culled",
                            count=len(hidden_faces),
                            name=mesh_name,
                        )
                    )

            bmesh.ops.triangulate(bmesh_data, faces=bmesh_data.faces)
            for face_item in bmesh_data.faces:
                face_item.smooth = True
            kept_orig_vert_indices = [
                bmesh_vert_item[orig_vert_layer] for bmesh_vert_item in bmesh_data.verts
            ]
            bmesh_data.to_mesh(baked_mesh)
            bmesh_data.free()
            baked_mesh.update()

        offset_x = mesh_cfg.get("offset_x", 0.0)
        offset_y = mesh_cfg.get("offset_y", 0.0)
        offset_z = mesh_cfg.get("offset_z", 0.0)

        is_beret_mesh = mesh_name == "UN2_Beret"
        if is_beret_mesh:
            hat_pivot = mathutils.Vector((0.0, 0.0314, 1.2534))
            hat_rot_matrix = mathutils.Matrix.Rotation(math.radians(-11.464), 4, "X")
            hat_pos_delta = mathutils.Vector((0.0, 0.02655, 0.01388))

        is_neko_hair = is_calibrated_neko and (mesh_name in neko_hair_mesh_names)
        # Unity calibration for Neko BoB_Lime was measured with Neck=0.9 (Head at (0, 0.012822, 1.128282)).
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
            neko_target_hair_root = head_world_pos + (baseline_head_to_hair_offset * head_scale_ratio)
            neko_hair_scale = baseline_hair_scale * custom_hair_node_scale * head_scale_ratio
        else:
            neko_hair_scale = baseline_hair_scale * custom_hair_node_scale
        neko_hair_rot_matrix = mathutils.Euler((-0.001953, 0.0, 0.0), "XYZ").to_matrix()

        eval_world_matrix = evaluated_obj.matrix_world
        has_negative_det = eval_world_matrix.determinant() < 0.0
        for vert_item in baked_mesh.vertices:
            world_coord = eval_world_matrix @ vert_item.co
            if is_beret_mesh:
                rel_coord = world_coord - hat_pivot
                world_coord = hat_pivot + (hat_rot_matrix @ rel_coord) + hat_pos_delta
            elif is_neko_hair and hair_root_rest_pos is not None:
                rel_hair = (world_coord - hair_root_rest_pos) * neko_hair_scale
                world_coord = neko_target_hair_root + (neko_hair_rot_matrix @ rel_hair)
            elif mesh_name == "Pocket Watch":
                world_coord = watch_transform_matrix @ world_coord

            vert_item.co.x = (world_coord.x + offset_x) * scale_factor
            vert_item.co.y = (world_coord.y + offset_y) * scale_factor
            vert_item.co.z = (world_coord.z + offset_z) * scale_factor + vertical_offset

        if has_negative_det:
            # Flip winding cleanly for mirrored FBX parts such as Nail_L (det < 0)
            bmesh_flip = bmesh.new()
            bmesh_flip.from_mesh(baked_mesh)
            bmesh.ops.reverse_faces(bmesh_flip, faces=bmesh_flip.faces)
            bmesh_flip.to_mesh(baked_mesh)
            bmesh_flip.free()
            baked_mesh.update()

        if (
            mesh_name == "Body"
            and fbx_face_normals
            and len(kept_loop_indices) == len(baked_mesh.loops)
        ):
            preserved_body_normals = [
                fbx_face_normals[loop_idx] for loop_idx in kept_loop_indices
            ]
        baked_mesh.update()

        proc_obj = bpy.data.objects.new(f"proc_{mesh_name}", baked_mesh)
        bpy.context.collection.objects.link(proc_obj)
        if mesh_name != "Body" and baked_mesh.has_custom_normals:
            bpy.context.view_layer.objects.active = proc_obj
            bpy.ops.mesh.customdata_custom_splitnormals_clear()

        # Remap UVs into the target quadrant or sub-quadrant of the 4x2 Atlas
        if not mesh_cfg.get("uv_prepacked"):
            u_scale = mesh_cfg.get("u_scale", 0.25)
            v_scale = mesh_cfg.get("v_scale", 0.5)
            if "u_offset" in mesh_cfg and "v_offset" in mesh_cfg:
                u_offset = mesh_cfg["u_offset"]
                v_offset = mesh_cfg["v_offset"]
            else:
                atlas_col = mesh_cfg["atlas_col"]
                atlas_row = mesh_cfg["atlas_row"]
                u_offset = atlas_col / 4.0
                v_offset = atlas_row / 2.0

            clamp_v_flag = mesh_cfg.get("clamp_v", False)

            if not proc_obj.data.uv_layers and mesh_name in ("Nail_neko", "Nail_Ribbon", "Nail_L", "Nail_R"):
                new_uv = proc_obj.data.uv_layers.new(name="UVMap")
                for loop_uv in new_uv.data:
                    loop_uv.uv = (0.5, 0.5)

            if proc_obj.data.uv_layers:
                uv_layer = proc_obj.data.uv_layers[0]
                for loop_entry in uv_layer.data:
                    orig_u, orig_v = loop_entry.uv
                    if clamp_v_flag and orig_v > 1.0:
                        orig_v = min(1.0, max(0.0, orig_v % 1.0))
                    loop_entry.uv = (u_offset + (orig_u * u_scale), v_offset + (orig_v * v_scale))

        # Assign vertex weights to valid GTA V bones
        pb_active_bones = set(pb_resolution.get("custom_bones") or ())
        pb_bone_map_lower = pb_resolution.get("bone_mapping_ci")
        vgroup_names_by_idx = {
            vgroup.index: vgroup.name for vgroup in source_obj.vertex_groups
        }
        vgroup_target_names = {
            vgroup.index: resolve_gtav_target_bone(
                vgroup.name, mesh_name, bone_mapping_lower=pb_bone_map_lower
            )
            for vgroup in source_obj.vertex_groups
        }
        vertex_weight_map = {
            vert_idx: {} for vert_idx in range(len(baked_mesh.vertices))
        }
        if mesh_cfg.get("is_custom_hair"):
            pass
        elif mesh_name == "UN1_Skirt":
            for new_vert_idx, orig_vert_idx in enumerate(kept_orig_vert_indices):
                ydd_vert_coord = baked_mesh.vertices[new_vert_idx].co
                vertex_weight_map[new_vert_idx] = compute_skirt_vertex_weights(
                    source_obj,
                    orig_vert_idx,
                    ydd_vert_coord,
                    vgroup_names_by_idx,
                    vgroup_target_names,
                )
        elif mesh_name == "_Halo":
            use_legacy_halo_split = "PB_ER_Halo_0" not in pb_active_bones
            for new_vert_idx, orig_vert_idx in enumerate(kept_orig_vert_indices):
                if orig_vert_idx < len(source_obj.data.vertices):
                    src_vert = source_obj.data.vertices[orig_vert_idx]
                    for grp_elem in src_vert.groups:
                        if grp_elem.weight > 0.001 and grp_elem.group in vgroup_target_names:
                            src_grp_name = vgroup_names_by_idx.get(grp_elem.group, "").strip().lower()
                            if use_legacy_halo_split and src_grp_name in ("halo", "halo.001"):
                                for split_bone, split_ratio in physbone_helper.NEKO_MIMI_HALO_WEIGHT_SPLIT:
                                    cur_val = vertex_weight_map[new_vert_idx].get(split_bone, 0.0)
                                    vertex_weight_map[new_vert_idx][split_bone] = (
                                        cur_val + grp_elem.weight * split_ratio
                                    )
                            else:
                                target_bone_name = vgroup_target_names[grp_elem.group]
                                cur_val = vertex_weight_map[new_vert_idx].get(target_bone_name, 0.0)
                                vertex_weight_map[new_vert_idx][target_bone_name] = (
                                    cur_val + grp_elem.weight
                                )
        else:
            for new_vert_idx, orig_vert_idx in enumerate(kept_orig_vert_indices):
                if orig_vert_idx < len(source_obj.data.vertices):
                    src_vert = source_obj.data.vertices[orig_vert_idx]
                    for grp_elem in src_vert.groups:
                        if grp_elem.weight > 0.001 and grp_elem.group in vgroup_target_names:
                            target_bone_name = vgroup_target_names[grp_elem.group]
                            current_weight = vertex_weight_map[new_vert_idx].get(
                                target_bone_name, 0.0
                            )
                            vertex_weight_map[new_vert_idx][target_bone_name] = (
                                current_weight + grp_elem.weight
                            )

        for vert_idx, bone_weights in vertex_weight_map.items():
            weight_sum = sum(bone_weights.values())
            if weight_sum > 0.0:
                for target_bone_name, raw_weight in bone_weights.items():
                    dst_group = proc_obj.vertex_groups.get(target_bone_name)
                    if not dst_group:
                        dst_group = proc_obj.vertex_groups.new(name=target_bone_name)
                    dst_group.add([vert_idx], raw_weight / weight_sum, "ADD")
            else:
                fallback_bone = (
                    "SKEL_R_Finger42"
                    if mesh_name in ("Nail_Ribbon", "Nail_neko")
                    else (
                        "SKEL_L_Hand"
                        if mesh_name == "Nail_L"
                        else (
                            "SKEL_R_Hand"
                            if mesh_name == "Nail_R"
                            else (
                                "SKEL_Head"
                                if (
                                    mesh_cfg.get("is_custom_hair")
                                    or "head" in mesh_name.lower()
                                    or "hair" in mesh_name.lower()
                                    or "glasses" in mesh_name.lower()
                                    or "beret" in mesh_name.lower()
                                    or mesh_name in HEAD_ACCESSORY_MESH_NAMES
                                    or mesh_name == "Body"
                                )
                                else (
                                    "SKEL_Spine2"
                                    if mesh_name in ("UN3_Bag", "UN1_Shirt", "UN1_ChestRibbon")
                                    else "SKEL_Pelvis"
                                )
                            )
                        )
                    )
                )
                dst_group = proc_obj.vertex_groups.get(fallback_bone)
                if not dst_group:
                    dst_group = proc_obj.vertex_groups.new(name=fallback_bone)
                dst_group.add([vert_idx], 1.0, "REPLACE")

        if mesh_name == "Body" and body_jaw_weights:
            jaw_vgroup = proc_obj.vertex_groups.get("FACIAL_jaw")
            if not jaw_vgroup:
                jaw_vgroup = proc_obj.vertex_groups.new(name="FACIAL_jaw")
            head_vgroup = proc_obj.vertex_groups.get("SKEL_Head")
            if not head_vgroup:
                head_vgroup = proc_obj.vertex_groups.new(name="SKEL_Head")
            for new_vert_idx, orig_vert_idx in enumerate(kept_orig_vert_indices):
                if orig_vert_idx in body_jaw_weights:
                    jaw_weight = body_jaw_weights[orig_vert_idx]
                    jaw_vgroup.add([new_vert_idx], jaw_weight, "REPLACE")
                    head_vgroup.add([new_vert_idx], max(0.0, 1.0 - jaw_weight), "REPLACE")
            print(i18n.translate("michael.build.jaw_head_applied"))

        if mesh_name == "Body" and blink_rig_data.get("enabled"):
            eye_blink_helper.apply_eyelid_blink_weights_to_mesh(
                proc_obj,
                blink_rig_data["weights_by_orig_vert"],
                kept_orig_vert_indices=kept_orig_vert_indices,
            )

        proc_obj["vtoon_bucket"] = str(mesh_cfg.get("vtoon_bucket", "ped"))
        proc_obj["vtoon_double_sided"] = bool(mesh_cfg.get("double_sided"))

        processed_objects.append(proc_obj)

    return processed_objects, preserved_body_normals


def apply_deferred_double_sided_backfaces(
    processed_objects,
    blender_hair_helper_mod,
    normal_offset: float = 0.00035,
) -> int:
    """Duplicate flipped backfaces after decimation so shells never collapse unevenly."""
    total_dup = 0
    for proc_obj in processed_objects:
        if bool(proc_obj.get("vtoon_double_sided", False)):
            total_dup += blender_hair_helper_mod.duplicate_double_sided_backfaces(
                proc_obj,
                normal_offset=float(normal_offset),
            )
    return total_dup



def apply_michael_er_split_normals(
    joined_mesh_obj,
    preserved_body_normals,
    fbx_face_normals,
    ydrexport,
):
    """Restore anime FBX custom facial normals and frontal shading on joined mesh."""
    if fbx_face_normals and preserved_body_normals:
        joined_mesh_obj.data.use_auto_smooth = True
        joined_mesh_obj.data.calc_normals_split()
        split_normals = [tuple(loop_item.normal) for loop_item in joined_mesh_obj.data.loops]
        face_loop_count = min(len(preserved_body_normals), len(split_normals))
        split_normals[:face_loop_count] = preserved_body_normals[:face_loop_count]

        mesh_verts = joined_mesh_obj.data.vertices
        mesh_loops = joined_mesh_obj.data.loops
        mesh_uvs = (
            joined_mesh_obj.data.uv_layers[0].data
            if joined_mesh_obj.data.uv_layers
            else None
        )
        for poly_item in joined_mesh_obj.data.polygons:
            for loop_idx in poly_item.loop_indices:
                vert_coord = mesh_verts[mesh_loops[loop_idx].vertex_index].co
                if loop_idx < face_loop_count:
                    if vert_coord.y < 0.020 and 0.60 < vert_coord.z < 0.77 and abs(vert_coord.x) < 0.085:
                        norm_x = vert_coord.x * 2.2
                        norm_y = -1.0
                        norm_z = (vert_coord.z - 0.69) * 1.4
                        vec_len = math.sqrt(norm_x * norm_x + norm_y * norm_y + norm_z * norm_z)
                        split_normals[loop_idx] = (
                            norm_x / vec_len,
                            norm_y / vec_len,
                            norm_z / vec_len,
                        )
                elif mesh_uvs is not None:
                    loop_uv = mesh_uvs[loop_idx].uv
                    if 0.25 <= loop_uv.x < 0.50 and loop_uv.y >= 0.50:
                        if vert_coord.y < 0.025 and 0.535 < vert_coord.z < 0.655 and abs(vert_coord.x) < 0.065:
                            norm_x = vert_coord.x * 3.5
                            norm_y = -1.0
                            norm_z = -0.1
                            vec_len = math.sqrt(norm_x * norm_x + norm_y * norm_y + norm_z * norm_z)
                            split_normals[loop_idx] = (
                                norm_x / vec_len,
                                norm_y / vec_len,
                                norm_z / vec_len,
                            )
        joined_mesh_obj.data.normals_split_custom_set(split_normals)
        ydrexport.triangulate_mesh = lambda eval_mesh: eval_mesh


def _compute_er_earlobe_anchors(bpy_mod, bmesh_mod, mathutils_mod, arm_base):
    """Find evaluated Left/Right earlobe pierce anchors on Shinano's deformed Body mesh."""
    head_bone = arm_base.pose.bones.get("Head") if arm_base else None
    head_pos = (
        (arm_base.matrix_world @ head_bone.head).copy()
        if head_bone is not None
        else mathutils_mod.Vector((0.0, 0.0128, 1.1283))
    )
    left_anchor = mathutils_mod.Vector((0.0600, -0.0082, head_pos.z + 0.0210))
    right_anchor = mathutils_mod.Vector((-0.0600, -0.0082, head_pos.z + 0.0210))

    body_obj = bpy_mod.data.objects.get("Body")
    if body_obj is None:
        return left_anchor, right_anchor

    depsgraph_eval = bpy_mod.context.evaluated_depsgraph_get()
    eval_body = body_obj.evaluated_get(depsgraph_eval)
    world_pts = [eval_body.matrix_world @ vert.co for vert in eval_body.data.vertices]
    # Target the outer human earlobe specifically (|x| >= 0.058 excludes jawline/cheek vertices)
    left_cands = [
        point_vec
        for point_vec in world_pts
        if 0.0580 <= point_vec.x < 0.0750
        and -0.0180 < point_vec.y < 0.0100
        and (head_pos.z + 0.0140) < point_vec.z < (head_pos.z + 0.0360)
    ]
    right_cands = [
        point_vec
        for point_vec in world_pts
        if -0.0750 < point_vec.x <= -0.0580
        and -0.0180 < point_vec.y < 0.0100
        and (head_pos.z + 0.0140) < point_vec.z < (head_pos.z + 0.0360)
    ]
    if len(left_cands) >= 3:
        low_left = sorted(left_cands, key=lambda point_vec: point_vec.z)[:4]
        mean_left_x = sum(point_vec.x for point_vec in low_left) / len(low_left)
        mean_left_y = sum(point_vec.y for point_vec in low_left) / len(low_left)
        min_left_z = min(point_vec.z for point_vec in low_left)
        left_anchor = mathutils_mod.Vector((mean_left_x, mean_left_y, min_left_z + 0.0008))
    if len(right_cands) >= 3:
        low_right = sorted(right_cands, key=lambda point_vec: point_vec.z)[:4]
        mean_right_x = sum(point_vec.x for point_vec in low_right) / len(low_right)
        mean_right_y = sum(point_vec.y for point_vec in low_right) / len(low_right)
        min_right_z = min(point_vec.z for point_vec in low_right)
        right_anchor = mathutils_mod.Vector((mean_right_x, mean_right_y, min_right_z + 0.0008))
    return left_anchor, right_anchor


def _stamp_earring_slot_uvs(ear_obj, mathutils_mod) -> None:
    """Assign compact atlas palette UVs per Earring material slot inside [0.9375..0.96875, 0..0.0625]."""
    mesh_data = ear_obj.data
    if not mesh_data.uv_layers:
        mesh_data.uv_layers.new(name="UVMap")
    uv_layer = mesh_data.uv_layers[0].data
    # Left half: bronze filigree; top-right: silver-pearl stud; bottom-right: sapphire chain
    slot_boxes = {
        0: (0.941, 0.008, 0.949, 0.054),
        3: (0.941, 0.008, 0.949, 0.054),
        2: (0.957, 0.036, 0.965, 0.058),
        1: (0.957, 0.005, 0.965, 0.026),
    }
    for poly_item in mesh_data.polygons:
        u0_val, v0_val, u1_val, v1_val = slot_boxes.get(
            poly_item.material_index, (0.941, 0.008, 0.949, 0.054)
        )
        mid_u = 0.5 * (u0_val + u1_val)
        mid_v = 0.5 * (v0_val + v1_val)
        span_u = (u1_val - u0_val) * 0.35
        span_v = (v1_val - v0_val) * 0.35
        for loop_pos, loop_idx in enumerate(poly_item.loop_indices):
            angle_offset = (loop_pos % 3) - 1
            uv_layer[loop_idx].uv = (
                mid_u + angle_offset * span_u * 0.25,
                mid_v + angle_offset * span_v * 0.25,
            )


def import_and_place_er_earrings(
    bpy_mod,
    bmesh_mod,
    mathutils_mod,
    hair_fbx_path,
    arm_base,
    unity_config,
    active_mesh_configs,
):
    """Import Earring.fbx (Left & Right) from Neko Tied Bob assets and mount on earlobes."""
    earring_cands = []
    if hair_fbx_path:
        earring_cands.append(Path(str(hair_fbx_path)).parent / "Earring.fbx")
    earring_cands.append(
        Path(r"E:\waifuv4\Assets\Li-ne\Neko Tied Bob hair\_Fbx\Earring.fbx")
    )
    resolved_earring = next((cand for cand in earring_cands if cand.is_file()), None)
    if resolved_earring is None:
        print("[ER Earrings] Earring.fbx not found; skipping.")
        return

    pre_objs = set(bpy_mod.data.objects)
    err_helper.import_fbx_safely(bpy_mod, filepath=str(resolved_earring))
    new_objs = [obj for obj in bpy_mod.data.objects if obj not in pre_objs]
    raw_ear_mesh = next((obj for obj in new_objs if obj.type == "MESH"), None)
    extra_ear_objs = [obj for obj in new_objs if obj != raw_ear_mesh]
    if raw_ear_mesh is None:
        for rem_obj in extra_ear_objs:
            bpy_mod.data.objects.remove(rem_obj)
        return

    neck_scale = unity_scene_helper.get_uniform_scale(unity_config, ("Neck",), default_scale=0.9)
    ear_scale = 1.631313 * (float(neck_scale) if float(neck_scale) >= 1.0 else 0.96)

    # Strip Armature modifier and FBX shape keys before editing vertices so Basis never snaps Earring_L back
    raw_ear_world_mat = raw_ear_mesh.matrix_world.copy()
    raw_ear_mesh.modifiers.clear()
    if raw_ear_mesh.data.shape_keys is not None:
        for key_block in reversed(list(raw_ear_mesh.data.shape_keys.key_blocks)):
            raw_ear_mesh.shape_key_remove(key_block)

    # Bake raw transform cleanly into vertices, center stud at top origin, slight outward yaw (+25 deg L)
    raw_verts = [raw_ear_world_mat @ vert.co for vert in raw_ear_mesh.data.vertices]
    stud_verts = [
        raw_ear_world_mat @ raw_ear_mesh.data.vertices[vertex_index].co
        for poly_item in raw_ear_mesh.data.polygons
        if poly_item.material_index == 2
        for vertex_index in poly_item.vertices
    ]
    anchor_src = stud_verts if stud_verts else raw_verts
    stud_center = mathutils_mod.Vector(
        (
            sum(point_vec.x for point_vec in anchor_src) / len(anchor_src),
            sum(point_vec.y for point_vec in anchor_src) / len(anchor_src),
            sum(point_vec.z for point_vec in anchor_src) / len(anchor_src),
        )
    )
    outward_yaw = mathutils_mod.Matrix.Rotation(math.radians(25.0), 3, "Z")

    left_earlobe, right_earlobe = _compute_er_earlobe_anchors(
        bpy_mod, bmesh_mod, mathutils_mod, arm_base
    )

    raw_ear_mesh.parent = None
    raw_ear_mesh.matrix_world = mathutils_mod.Matrix.Identity(4)
    raw_ear_mesh.vertex_groups.clear()
    for extra_arm in extra_ear_objs:
        bpy_mod.data.objects.remove(extra_arm)

    for vert_idx, vert_item in enumerate(raw_ear_mesh.data.vertices):
        rel_vec = outward_yaw @ ((raw_verts[vert_idx] - stud_center) * ear_scale)
        vert_item.co = rel_vec + left_earlobe
    raw_ear_mesh.data.update()
    raw_ear_mesh.name = "Earring_L"
    _stamp_earring_slot_uvs(raw_ear_mesh, mathutils_mod)

    right_mesh_data = raw_ear_mesh.data.copy()
    right_ear_obj = bpy_mod.data.objects.new("Earring_R", right_mesh_data)
    bpy_mod.context.collection.objects.link(right_ear_obj)
    for vert_idx, vert_item in enumerate(right_ear_obj.data.vertices):
        rel_vec = outward_yaw @ ((raw_verts[vert_idx] - stud_center) * ear_scale)
        vert_item.co = mathutils_mod.Vector((-rel_vec.x, rel_vec.y, rel_vec.z)) + right_earlobe
    bmesh_flip = bmesh_mod.new()
    bmesh_flip.from_mesh(right_ear_obj.data)
    bmesh_mod.ops.reverse_faces(bmesh_flip, faces=bmesh_flip.faces)
    bmesh_flip.to_mesh(right_ear_obj.data)
    bmesh_flip.free()
    right_ear_obj.data.update()
    _stamp_earring_slot_uvs(right_ear_obj, mathutils_mod)

    for side_name in ("Earring_L", "Earring_R"):
        active_mesh_configs[side_name] = {
            "uv_prepacked": True,
            "shrink_cull": False,
            "vtoon_bucket": "ped",
            "double_sided": False,
        }
    print(
        f"[ER Earrings] Mounted Earring_L={tuple(round(val, 4) for val in left_earlobe)} "
        f"Earring_R={tuple(round(val, 4) for val in right_earlobe)} scale={ear_scale:.4f}",
        flush=True,
    )


