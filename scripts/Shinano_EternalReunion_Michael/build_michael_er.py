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
  3. Shrink culling and indexed Unity blendshapes + 64 facial blendshapes from
     ShinanoDefAdultNewv5.anim.
  4. Universal bone mapping onto the Michael GTA V skeleton (`player_zero.yft`)
     and 1:1 arm/hand/finger relocation for RAGE animations.
  5. Unified 4x2 Texture Atlas (`ped_default.sps`).
  6. Auto-chunking of oversized materials to respect the uint16 vertex limit.
"""

import argparse
import json
import math
import os
import re
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

import hand_skeleton_helper
import mathutils
import vrc2gtav_i18n as i18n
import vrc2gtav_paths as project_paths


# ---------------------------------------------------------------------------
# GTA V Legacy character profiles
# ---------------------------------------------------------------------------
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
# Standalone Unity .anim (YAML) parser for facial blendshapes
# ---------------------------------------------------------------------------
def load_unity_anim_blendshapes(anim_file_path):
    """Parse normalized blendshape curve weights from a Unity .anim YAML file."""
    blendshape_weights = {}
    if not anim_file_path or not os.path.exists(anim_file_path):
        return blendshape_weights

    with open(anim_file_path, "r", encoding="utf-8", errors="ignore") as anim_file:
        anim_text = anim_file.read()

    curve_blocks = anim_text.split("  - serializedVersion: 2")
    for block_text in curve_blocks[1:]:
        val_match = re.search(r"value:\s*([-\d.]+)", block_text)
        attr_match = re.search(r"attribute:\s*([^\n]+)", block_text)
        path_match = re.search(r"path:\s*([^\n]+)", block_text)
        if val_match and attr_match and path_match:
            raw_value = float(val_match.group(1))
            attr_text = attr_match.group(1).strip()
            shape_name = attr_text.replace("blendShape.", "").strip()
            if shape_name.startswith('"'):
                try:
                    shape_name = json.loads(shape_name)
                except Exception:
                    shape_name = shape_name.strip('"')
            if abs(raw_value) > 1e-4:
                blendshape_weights[shape_name] = raw_value / 100.0
            else:
                blendshape_weights[shape_name] = 0.0

    return blendshape_weights


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
    "_Halo",
    "_Pin.Back",
    "_Pin.R",
    "_Pin.L2",
})


def smoothstep_unit(scalar_val):
    """Smooth Hermite interpolation clamped to [0.0, 1.0]."""
    clamped_val = max(0.0, min(1.0, float(scalar_val)))
    return clamped_val * clamped_val * (3.0 - 2.0 * clamped_val)


def compute_pocket_watch_align_matrix(arm_outfit, arm_watch):
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

    # Normalize 3x3 rotations before inverting to isolate orientation and apply 1.10 scale
    outfit_rot_mat = outfit_matrix.to_3x3().normalized().to_4x4()
    watch_rot_mat = watch_matrix.to_3x3().normalized().to_4x4()
    watch_head_pos = arm_watch.matrix_world @ watch_bone.head_local

    # Exact Pocket Watch_Root coordinates from Shinano.unity (< 0.5 mm error to ring)
    unity_target_pos = mathutils.Vector((-0.05371, -0.07346, 0.82380))
    return (
        mathutils.Matrix.Translation(unity_target_pos)
        @ outfit_rot_mat
        @ mathutils.Matrix.Scale(1.10, 4)
        @ watch_rot_mat.inverted()
        @ mathutils.Matrix.Translation(-watch_head_pos)
    )


def compute_skirt_vertex_weights(
    source_obj,
    orig_vert_idx,
    ydd_co,
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
            if "skirt" in raw_name.lower():
                skirt_weight += grp_elem.weight
            else:
                target_bone = vgroup_target_names[grp_elem.group]
                remapped_weights[target_bone] = (
                    remapped_weights.get(target_bone, 0.0) + grp_elem.weight
                )

    if skirt_weight > 0.0:
        # Vertical ramp: waist (+0.10) anchored 100% to Pelvis; hem (<= +0.02) shares up to 28%
        vertical_ramp = smoothstep_unit((0.10 - ydd_co.z) / 0.08)
        # Front-to-back ramp: keep front (y <= -0.02) on Pelvis to prevent belly sink when sitting
        back_ramp = smoothstep_unit((ydd_co.y + 0.02) / 0.06)
        # Left/right blend across centerline (+X left thigh, -X right thigh)
        left_right_mix = smoothstep_unit((ydd_co.x + 0.035) / 0.070)

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


def resolve_gtav_target_bone(source_bone_name, mesh_name=None):
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
        # Bind bag body, rings, and chains strictly to Spine2 so straps follow the chest
        return "SKEL_Spine2"

    if source_bone_name in HUMAN_TO_GTAV_BONE_MAP:
        return HUMAN_TO_GTAV_BONE_MAP[source_bone_name]

    # 1:1 mapping of 30 finger bones and twist helper bones
    resolved_arm_or_finger = hand_skeleton_helper.resolve_finger_or_arm_bone(source_bone_name)
    if resolved_arm_or_finger is not None:
        return resolved_arm_or_finger

    # Fallback for palm bones while excluding Pocket Watch hand pointers
    lower_name = source_bone_name.lower()
    if mesh_name != "Pocket Watch" and "hand" in lower_name:
        side_code = (
            "L"
            if (".L" in source_bone_name or "Left" in source_bone_name or "_L" in source_bone_name)
            else "R"
        )
        return f"SKEL_{side_code}_Hand"

    if (
        lower_name.startswith("breast")
        or lower_name.startswith("bust")
        or "chestribbon" in lower_name
        or "un_ribbon" in lower_name
    ):
        return "SKEL_Spine2"

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


# ---------------------------------------------------------------------------
# Oversized geometry splitter for RAGE uint16 vertex limits (< 30,000 verts)
# ---------------------------------------------------------------------------
def split_oversized_material_geometries(mesh_object, max_vertices_per_chunk=30000):
    """Split dense material slots into multiple chunks under the uint16 limit."""
    mesh_data = mesh_object.data
    polys_by_material = {}
    for poly_item in mesh_data.polygons:
        polys_by_material.setdefault(poly_item.material_index, []).append(poly_item.index)

    max_polys_per_chunk = max(10000, int(max_vertices_per_chunk * 0.65))

    for mat_index, poly_indices in list(polys_by_material.items()):
        if len(poly_indices) <= max_polys_per_chunk:
            continue

        base_material = mesh_data.materials[mat_index]
        chunk_total = math.ceil(len(poly_indices) / max_polys_per_chunk)
        print(
            i18n.translate(
                "michael.build.splitting_material",
                name=base_material.name,
                count=len(poly_indices),
                chunks=chunk_total,
            )
        )

        for chunk_idx in range(1, chunk_total):
            cloned_mat = base_material.copy()
            cloned_mat.name = f"{base_material.name}_chunk{chunk_idx}"
            mesh_data.materials.append(cloned_mat)
            new_slot_index = len(mesh_data.materials) - 1

            start_pos = chunk_idx * max_polys_per_chunk
            end_pos = min(len(poly_indices), (chunk_idx + 1) * max_polys_per_chunk)
            for poly_idx in poly_indices[start_pos:end_pos]:
                mesh_data.polygons[poly_idx].material_index = new_slot_index

    mesh_data.update()


def apply_shape_key_weights_by_index(mesh_obj, weights_by_index, label):
    """Apply shape key weights by 0-based index (after Basis), zeroing others."""
    if not mesh_obj or not mesh_obj.data.shape_keys:
        raise RuntimeError(i18n.translate("michael.build.no_shape_keys", label=label))

    key_blocks = mesh_obj.data.shape_keys.key_blocks
    for key_block in key_blocks[1:]:
        key_block.value = 0.0

    applied_count = 0
    for zero_based_idx, weight_val in weights_by_index.items():
        target_slot = zero_based_idx + 1
        if target_slot >= len(key_blocks):
            raise IndexError(
                i18n.translate(
                    "michael.build.shape_key_oob",
                    index=zero_based_idx,
                    name=mesh_obj.name,
                    available=len(key_blocks) - 1,
                )
            )
        key_blocks[target_slot].value = weight_val
        applied_count += 1

    print(
        i18n.translate(
            "michael.build.applied_shape_keys", count=applied_count, name=mesh_obj.name
        )
    )


def validate_build_inputs(cli_args):
    """Verify all required FBX, skeleton, animation, and texture inputs exist."""
    required_paths = [
        (i18n.translate("michael.build.input_skeleton_label"), cli_args.skeleton_yft),
        (i18n.translate("michael.build.input_shinano_fbx_label"), cli_args.shinano_fbx),
        (i18n.translate("michael.build.input_outfit_fbx_label"), cli_args.outfit_fbx),
        (i18n.translate("michael.build.input_watch_fbx_label"), cli_args.watch_fbx),
        (i18n.translate("michael.build.input_hair_fbx_label"), cli_args.hair_fbx),
        (i18n.translate("michael.build.input_face_anim_label"), cli_args.face_anim),
    ]
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

    char_key = cli_args.target_character.lower()
    if char_key not in CHARACTER_PROFILES:
        raise ValueError(i18n.translate("michael.build.invalid_character", name=char_key))
    char_profile = CHARACTER_PROFILES[char_key]

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

    print(i18n.translate("michael.build.importing_hair", path=cli_args.hair_fbx))
    bpy.ops.import_scene.fbx(filepath=cli_args.hair_fbx)
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

    # Rotate arms to GTA V A-pose (-55 degrees) and apply Neck scale (0.90) from Shinano.unity
    arm_angle_rad = -math.radians(abs(char_profile["arm_pose_degrees"]))
    neck_scaled_armatures = {arm_obj for arm_obj in (arm_base, arm_outfit) if arm_obj}
    for arm_obj in imported_armatures:
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
        if arm_obj in neck_scaled_armatures and "Neck" in arm_obj.pose.bones:
            neck_pose_bone = arm_obj.pose.bones["Neck"]
            neck_pose_bone.scale = (0.9, 0.9, 0.9)
        bpy.ops.object.mode_set(mode="OBJECT")

    if not arm_hair or "Hair Root" not in arm_hair.data.bones:
        raise RuntimeError(i18n.translate("michael.build.hair_root_missing"))
    hair_root_rest_pos = (
        arm_hair.matrix_world @ arm_hair.data.bones["Hair Root"].head_local
    ).copy()
    watch_transform_matrix = compute_pocket_watch_align_matrix(arm_outfit, arm_watch)

    # 4. Load original Shinano FBX facial normals
    fbx_face_normals = load_fbx_face_loop_normals(cli_args.shinano_fbx)
    if fbx_face_normals:
        print(i18n.translate("michael.build.fbx_normals_loaded", count=len(fbx_face_normals)))

    # 5. Apply facial blendshapes on Body
    face_blendshapes = load_unity_anim_blendshapes(cli_args.face_anim)
    body_mesh_obj = bpy.data.objects.get("Body")
    if body_mesh_obj and body_mesh_obj.data.shape_keys:
        for key_block in body_mesh_obj.data.shape_keys.key_blocks:
            key_block.value = 0.0
        for shape_name, shape_val in face_blendshapes.items():
            key_block = body_mesh_obj.data.shape_keys.key_blocks.get(shape_name)
            if key_block:
                key_block.value = shape_val

    # 6. Apply Body_base shaping & shrink keys
    body_base_weights = {
        0: 1.0,
        6: 1.0,
        7: 1.0,
        14: 1.0,
        25: 1.0,
        26: 1.0,
        30: 1.0,
        31: 1.0,
        32: 1.0,
        33: 1.0,
        34: 1.0,
        35: 1.0,
        36: 1.0,
        41: 1.0,
        42: 1.0,
        43: 1.0,
        44: 1.0,
        45: 1.0,
        46: 1.0,
    }
    apply_shape_key_weights_by_index(
        bpy.data.objects.get("Body_base"), body_base_weights, "Body_base"
    )

    # 6A. Apply Eternal Reunion outfit & Pocket Watch blendshapes
    outfit_shape_keys_by_index = {
        "UN1_Shirt": {0: 1.0, 4: 1.0},
        "UN1_Skirt": {4: 1.0, 5: 1.0},
        "UN1_ChestRibbon": {0: 1.0},
        "UN2_Corset": {1: 1.0, 2: 1.0},
        "UN2_Stocking": {0: 1.0, 1: 1.0},
        "UN3_WaistChain": {0: 1.0, 1: 1.0},
        "Pocket Watch": {5: 1.0},
    }
    for outfit_mesh_name, outfit_weights in outfit_shape_keys_by_index.items():
        apply_shape_key_weights_by_index(
            bpy.data.objects.get(outfit_mesh_name), outfit_weights, outfit_mesh_name
        )

    # 6B. Apply indexed Neko Tied Bob hair blendshapes (Shinano.unity / MA Shinano.prefab)
    hair_shape_keys_by_index = {
        "Bangs": {9: 0.284, 17: 1.0, 22: 1.0},
        "Side Bangs": {0: 1.0, 4: 1.0},
        "Side": {
            5: 1.0,
            28: 1.0,
            31: 1.0,
            34: 0.136,
            35: 0.642,
            37: 1.0,
            40: 0.603,
            41: 1.0,
            42: 1.0,
            43: 0.328,
            44: 1.0,
            45: 1.0,
        },
        "Back": {8: 1.0, 12: 0.47, 13: 0.072},
        "Under Side": {
            8: 1.0,
            17: 0.778,
            22: 0.203,
            28: 0.788,
            33: 0.425,
            34: 1.0,
            39: 0.317,
            43: 0.510,
        },
        "In Hair": {
            4: 0.725,
            5: 0.075,
            6: 0.40,
            10: 1.0,
            11: 1.0,
            15: 1.0,
            16: 0.485,
            17: 0.796,
            19: 0.945,
            20: 0.117,
            21: 0.10,
            22: 0.315,
            23: 0.166,
            24: 0.427,
            25: 0.475,
            29: 1.0,
            30: 0.639,
            31: 1.0,
            32: 1.0,
            33: 1.0,
            37: 0.399,
            38: 0.221,
            40: 0.393,
            42: 0.126,
            44: 1.0,
            45: 1.0,
            47: 0.488,
        },
    }
    for hair_mesh_name, hair_weights in hair_shape_keys_by_index.items():
        apply_shape_key_weights_by_index(
            bpy.data.objects.get(hair_mesh_name), hair_weights, hair_mesh_name
        )

    bpy.context.view_layer.update()

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
        "Bangs": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Top Back": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Under Side": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Back": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Side Bangs": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Side": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "In Hair": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Ribbon": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Ears": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
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

    scale_factor = (char_profile["target_z_max"] - char_profile["target_z_min"]) / (1.132 - 0.106)
    vertical_offset = char_profile["target_z_min"] - (0.106 * scale_factor)

    depsgraph_eval = bpy.context.evaluated_depsgraph_get()
    processed_objects = []
    preserved_body_normals = None

    # Precompute FACIAL_jaw weights derived from the vrc.v_aa shape key
    body_jaw_weights = {}
    orig_body_obj = bpy.data.objects.get("Body")
    if orig_body_obj and orig_body_obj.data.shape_keys:
        shape_key_aa = orig_body_obj.data.shape_keys.key_blocks.get("vrc.v_aa")
        basis_key = orig_body_obj.data.shape_keys.key_blocks.get("Basis")
        if shape_key_aa and basis_key:
            for vert_item in orig_body_obj.data.vertices:
                delta_z = (
                    shape_key_aa.data[vert_item.index].co.z
                    - basis_key.data[vert_item.index].co.z
                )
                if delta_z < -0.0005:
                    jaw_weight_value = min(0.35, max(0.0, (abs(delta_z) / 0.0075) * 0.35))
                    body_jaw_weights[vert_item.index] = jaw_weight_value
            print(
                i18n.translate(
                    "michael.build.jaw_weights_mapped", count=len(body_jaw_weights)
                )
            )

    neko_hair_mesh_names = {
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
    }

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
        for vert_idx_counter, bm_vert_item in enumerate(bmesh_data.verts):
            bm_vert_item[orig_vert_layer] = vert_idx_counter

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
                bm_vert_item[orig_vert_layer] for bm_vert_item in bmesh_data.verts
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
                bm_vert_item[orig_vert_layer] for bm_vert_item in bmesh_data.verts
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

        is_neko_hair = mesh_name in neko_hair_mesh_names
        neko_target_hair_root = mathutils.Vector((0.000653, 0.010790, 1.202636))
        neko_hair_scale = 1.08696
        neko_hair_rot_matrix = mathutils.Euler((-0.001953, 0.0, 0.0), "XYZ").to_matrix()

        for vert_item in baked_mesh.vertices:
            world_co = source_obj.matrix_world @ vert_item.co
            if is_beret_mesh:
                rel_co = world_co - hat_pivot
                world_co = hat_pivot + (hat_rot_matrix @ rel_co) + hat_pos_delta
            elif is_neko_hair:
                rel_hair = (world_co - hair_root_rest_pos) * neko_hair_scale
                world_co = neko_target_hair_root + (neko_hair_rot_matrix @ rel_hair)
            elif mesh_name == "Pocket Watch":
                world_co = watch_transform_matrix @ world_co

            vert_item.co.x = (world_co.x + offset_x) * scale_factor
            vert_item.co.y = (world_co.y + offset_y) * scale_factor
            vert_item.co.z = (world_co.z + offset_z) * scale_factor + vertical_offset

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

        # Remap UVs into the target quadrant or sub-quadrant of the 4x2 Atlas
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

        if proc_obj.data.uv_layers:
            uv_layer = proc_obj.data.uv_layers[0]
            for loop_entry in uv_layer.data:
                orig_u, orig_v = loop_entry.uv
                if clamp_v_flag and orig_v > 1.0:
                    orig_v = min(1.0, max(0.0, orig_v % 1.0))
                loop_entry.uv = (u_offset + (orig_u * u_scale), v_offset + (orig_v * v_scale))

        # Assign vertex weights to valid GTA V bones
        vgroup_names_by_idx = {
            vgroup.index: vgroup.name for vgroup in source_obj.vertex_groups
        }
        vgroup_target_names = {
            vgroup.index: resolve_gtav_target_bone(vgroup.name, mesh_name)
            for vgroup in source_obj.vertex_groups
        }
        vertex_weight_map = {
            vert_idx: {} for vert_idx in range(len(baked_mesh.vertices))
        }
        if mesh_name == "UN1_Skirt":
            for new_vert_idx, orig_vert_idx in enumerate(kept_orig_vert_indices):
                ydd_vert_co = baked_mesh.vertices[new_vert_idx].co
                vertex_weight_map[new_vert_idx] = compute_skirt_vertex_weights(
                    source_obj,
                    orig_vert_idx,
                    ydd_vert_co,
                    vgroup_names_by_idx,
                    vgroup_target_names,
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
                    "SKEL_Head"
                    if (
                        "head" in mesh_name.lower()
                        or "hair" in mesh_name.lower()
                        or "glasses" in mesh_name.lower()
                        or "beret" in mesh_name.lower()
                        or mesh_name in neko_hair_mesh_names
                        or mesh_name == "Body"
                    )
                    else (
                        "SKEL_Spine2"
                        if mesh_name in ("UN3_Bag", "UN1_Shirt", "UN1_ChestRibbon")
                        else "SKEL_Pelvis"
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

        processed_objects.append(proc_obj)

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

    # 8. Remove source armatures and raw meshes
    for old_obj in list(bpy.data.objects):
        if old_obj != ped_armature and old_obj not in processed_objects:
            bpy.data.objects.remove(old_obj)

    # 9. Join all processed meshes into SKEL_ROOT
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

    # 10. Create unified ped_default.sps shader material for the 4x2 Atlas
    texture_dir = os.path.abspath(cli_args.texture_dir)
    atlas_image_path = os.path.join(texture_dir, cli_args.atlas_png)
    normal_image_path = os.path.join(texture_dir, cli_args.normal_png)
    spec_image_path = os.path.join(texture_dir, cli_args.spec_png)

    atlas_image = bpy.data.images.load(atlas_image_path)
    flat_normal_image = bpy.data.images.load(normal_image_path)
    specular_image = bpy.data.images.load(spec_image_path)

    ped_material = create_shader("ped_default.sps")
    ped_material.name = "shinano_er_mat"

    diffuse_node = ped_material.node_tree.nodes.get("DiffuseSampler")
    if diffuse_node:
        diffuse_node.image = atlas_image
        diffuse_node.texture_properties.embedded = False

    bump_node = ped_material.node_tree.nodes.get("BumpSampler")
    if bump_node:
        bump_node.image = flat_normal_image
        bump_node.texture_properties.embedded = False

    specular_node = ped_material.node_tree.nodes.get("SpecSampler")
    if specular_node:
        specular_node.image = specular_image
        specular_node.texture_properties.embedded = False

    for shader_node in ped_material.node_tree.nodes:
        if shader_node.name == "bumpiness" and hasattr(shader_node, "set_float"):
            shader_node.set_float(0.35)
        elif shader_node.name == "StubbleControl" and hasattr(shader_node, "set_vec2"):
            shader_node.set_vec2((0.0, 0.0))
        elif shader_node.name == "detailSettings" and hasattr(shader_node, "set_vec4"):
            shader_node.set_vec3((0.0, 0.0, 0.0))
        elif shader_node.name == "specularIntensityMult" and hasattr(shader_node, "set_float"):
            shader_node.set_float(0.85)
        elif shader_node.name == "specularFalloffMult" and hasattr(shader_node, "set_float"):
            shader_node.set_float(24.0)
        elif shader_node.name == "specularFresnel" and hasattr(shader_node, "set_float"):
            shader_node.set_float(0.70)

    joined_mesh_obj.data.materials.clear()
    joined_mesh_obj.data.materials.append(ped_material)

    for poly_item in joined_mesh_obj.data.polygons:
        poly_item.material_index = 0

    if joined_mesh_obj.data.uv_layers:
        joined_mesh_obj.data.uv_layers[0].name = "UVMap 0"

    bpy.context.view_layer.objects.active = joined_mesh_obj
    bpy.ops.sollumz.color_attrs_add_missing()
    bpy.ops.sollumz.uv_maps_add_missing()

    color_attr_1 = joined_mesh_obj.data.color_attributes.get("Color 1")
    if color_attr_1:
        for corner_item in color_attr_1.data:
            corner_item.color = (1.0, 1.0, 1.0, 1.0)

    color_attr_2 = joined_mesh_obj.data.color_attributes.get("Color 2")
    if color_attr_2:
        for corner_item in color_attr_2.data:
            corner_item.color = (0.0, 0.0, 0.0, 0.0)

    if fbx_face_normals and preserved_body_normals:
        joined_mesh_obj.data.use_auto_smooth = True
        joined_mesh_obj.data.calc_normals_split()
        split_normals = [tuple(loop_item.normal) for loop_item in joined_mesh_obj.data.loops]
        face_loop_count = min(len(preserved_body_normals), len(split_normals))
        split_normals[:face_loop_count] = preserved_body_normals[:face_loop_count]

        mesh_verts = joined_mesh_obj.data.vertices
        mesh_loops = joined_mesh_obj.data.loops
        for poly_item in joined_mesh_obj.data.polygons:
            for loop_idx in poly_item.loop_indices:
                vert_co = mesh_verts[mesh_loops[loop_idx].vertex_index].co
                if vert_co.y < -0.045 and 0.61 < vert_co.z < 0.77 and abs(vert_co.x) < 0.085:
                    norm_x = vert_co.x * 2.2
                    norm_y = -1.0
                    norm_z = (vert_co.z - 0.69) * 1.4
                    vec_len = math.sqrt(norm_x * norm_x + norm_y * norm_y + norm_z * norm_z)
                    split_normals[loop_idx] = (
                        norm_x / vec_len,
                        norm_y / vec_len,
                        norm_z / vec_len,
                    )
        joined_mesh_obj.data.normals_split_custom_set(split_normals)
        ydrexport.triangulate_mesh = lambda eval_mesh: eval_mesh

    # 11. Split large materials for the uint16 RAGE limit
    split_oversized_material_geometries(
        joined_mesh_obj, max_vertices_per_chunk=cli_args.max_verts_per_chunk
    )

    # 12. Build Sollumz Drawable Dictionary hierarchy
    ydd_parent_empty = create_empty_object(SollumType.DRAWABLE_DICTIONARY)
    ped_armature.sollum_type = SollumType.DRAWABLE
    ped_armature.parent = ydd_parent_empty
    ped_armature.drawable_properties.lod_dist_high = 9998.0
    ped_armature.drawable_properties.lod_dist_med = 9998.0
    ped_armature.drawable_properties.lod_dist_low = 9998.0
    ped_armature.drawable_properties.lod_dist_vlow = 9998.0

    for bone_obj in ped_armature.data.bones:
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
        print(
            i18n.translate(
                "michael.build.exported_ydd",
                name=drawable_item_name,
                status=export_status,
            )
        )

    yft_output_path = os.path.join(output_dir, f"{char_profile['ped_name']}.yft")
    updated_yft_bones, total_yft_bones, max_yft_delta = hand_skeleton_helper.patch_yft_skeleton(
        cli_args.skeleton_yft, yft_output_path, bone_world_targets
    )
    print(
        i18n.translate(
            "michael.build.exported_yft",
            path=yft_output_path,
            updated=updated_yft_bones,
            total=total_yft_bones,
            delta=max_yft_delta,
        )
    )


def extract_custom_blender_args():
    """Return CLI arguments appearing after `--` (or `sys.argv[1:]` directly)."""
    raw_arguments = sys.argv
    if "--" in raw_arguments:
        return raw_arguments[raw_arguments.index("--") + 1 :]
    return raw_arguments[1:]


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
        "--face-anim",
        default=None,
        help=i18n.translate("michael.build.arg_face_anim"),
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

    michael_cfg = project_paths.get_character_paths("michael")
    parsed_args.skeleton_yft = parsed_args.skeleton_yft or str(michael_cfg["skeleton_yft"])
    parsed_args.shinano_fbx = parsed_args.shinano_fbx or str(michael_cfg["fbx_shinano"])
    parsed_args.outfit_fbx = parsed_args.outfit_fbx or str(michael_cfg["fbx_outfit"])
    parsed_args.watch_fbx = parsed_args.watch_fbx or str(michael_cfg["fbx_watch"])
    parsed_args.hair_fbx = parsed_args.hair_fbx or str(michael_cfg["fbx_hair"])
    parsed_args.face_anim = parsed_args.face_anim or str(michael_cfg["face_anim"])
    parsed_args.texture_dir = parsed_args.texture_dir or str(michael_cfg["textures_dir"])
    parsed_args.atlas_png = parsed_args.atlas_png or Path(michael_cfg["atlas_png"]).name
    parsed_args.normal_png = parsed_args.normal_png or Path(michael_cfg["normal_png"]).name
    parsed_args.spec_png = parsed_args.spec_png or Path(michael_cfg["spec_png"]).name
    parsed_args.output_dir = parsed_args.output_dir or str(michael_cfg["exported_models_dir"])

    return parsed_args


if __name__ == "__main__":
    parsed_cli_args = parse_blender_cli_args()
    build_shinano_er_for_gtav(parsed_cli_args)
