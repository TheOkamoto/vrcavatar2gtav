#!/usr/bin/env python3
"""
hand_skeleton_helper.py
=======================
Shared helper for 1:1 finger rigging and skeleton relocation (.ydd in Blender
and .yft via PyMateria) across all three GTA V protagonists.

Ensures that:
  1. All 30 finger bones (SKEL_{L,R}_Finger{0..4}{0..2}) and arm/wrist helper
     bones (RB_{L,R}_ForeArmRoll, RB_{L,R}_ArmRoll, PH/IK_{L,R}_Hand) are mapped
     individually instead of collapsing into the wrist.
  2. Drawable (.ydd) and fragment (.yft) armature joints move in parallel to the
     exact VRChat avatar A-pose joint locations while preserving native local .ycd
     animation rotations.
"""

import struct
import sys
import zlib
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence, Tuple, Union


_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

from vrc2gtav_i18n import translate


# Additional arm/wrist helper bones preserved alongside the standard finger set
EXTRA_ARM_HELPER_BONES = (
    "RB_L_ArmRoll",
    "RB_R_ArmRoll",
    "RB_L_ForeArmRoll",
    "RB_R_ForeArmRoll",
    "PH_L_Hand",
    "PH_R_Hand",
    "IK_L_Hand",
    "IK_R_Hand",
)

# All 30 canonical GTA V finger bone names
GTAV_FINGER_BONE_NAMES = tuple(
    f"SKEL_{side_tag}_Finger{finger_idx}{segment_idx}"
    for side_tag in ("L", "R")
    for finger_idx in range(5)
    for segment_idx in range(3)
)

# Candidate VRChat bone names (Shinano, ER, and Milltina) for each GTA V target bone
VRC_ARM_HAND_BONE_CANDIDATES: Dict[str, Tuple[str, ...]] = {
    "SKEL_L_Clavicle": ("Shoulder.L", "Shoulder_L", "LeftShoulder"),
    "SKEL_L_UpperArm": ("Upper_arm.L", "Upper_arm_L", "UpperArm.L", "LeftUpperArm"),
    "SKEL_L_Forearm": ("Lower_arm.L", "Lower_arm_L", "LowerArm.L", "LeftLowerArm"),
    "SKEL_L_Hand": ("Hand.L", "Hand_L", "LeftHand"),
    "SKEL_R_Clavicle": ("Shoulder.R", "Shoulder_R", "RightShoulder"),
    "SKEL_R_UpperArm": ("Upper_arm.R", "Upper_arm_R", "UpperArm.R", "RightUpperArm"),
    "SKEL_R_Forearm": ("Lower_arm.R", "Lower_arm_R", "LowerArm.R", "RightLowerArm"),
    "SKEL_R_Hand": ("Hand.R", "Hand_R", "RightHand"),
}

_FINGER_NAME_BY_INDEX = ("Thumb", "Index", "Middle", "Ring", "Little")
_SEGMENT_NAME_BY_INDEX = ("Proximal", "Intermediate", "Distal")

for _side_code, _humanoid_side in (("L", "Left"), ("R", "Right")):
    for _finger_idx, _finger_label in enumerate(_FINGER_NAME_BY_INDEX):
        for _seg_idx, _seg_label in enumerate(_SEGMENT_NAME_BY_INDEX):
            _gtav_finger_name = f"SKEL_{_side_code}_Finger{_finger_idx}{_seg_idx}"
            VRC_ARM_HAND_BONE_CANDIDATES[_gtav_finger_name] = (
                f"{_finger_label} {_seg_label}.{_side_code}",
                f"{_finger_label} {_seg_label}_{_side_code}",
                f"{_finger_label}_{_seg_label}.{_side_code}",
                f"{_finger_label}_{_seg_label}_{_side_code}",
                f"{_humanoid_side}{_finger_label}{_seg_label}",
                f"{_humanoid_side} {_finger_label} {_seg_label}",
            )


def detect_bone_side_code(bone_name: str) -> Optional[str]:
    """Detect the anatomical side ('L' or 'R') from Blender/Unity naming conventions."""
    lower_name = bone_name.lower()
    if (
        bone_name.endswith(".L")
        or bone_name.endswith("_L")
        or "_l_" in lower_name
        or "left" in lower_name
    ):
        return "L"
    if (
        bone_name.endswith(".R")
        or bone_name.endswith("_R")
        or "_r_" in lower_name
        or "right" in lower_name
    ):
        return "R"
    return None


def resolve_finger_or_arm_bone(source_bone_name: str) -> Optional[str]:
    """
    Map VRChat/Shinano/Miltina finger and arm support/twist bones to their
    exact GTA V skeleton counterparts.

    Return None for unrelated bones so the character-specific mapping rules
    handle the remaining bones without regression.
    """
    if source_bone_name in GTAV_FINGER_BONE_NAMES or source_bone_name in EXTRA_ARM_HELPER_BONES:
        return source_bone_name

    side_code = detect_bone_side_code(source_bone_name)
    if side_code is None:
        return None

    lower_name = source_bone_name.lower()

    # 1. Forearm, upper arm, and sleeve twist/support bones
    if (
        "lower_arm_twist" in lower_name
        or "lower_arm_cloth_twist" in lower_name
        or "lower_arm_support" in lower_name
        or "forearm_twist" in lower_name
        or "forearm_roll" in lower_name
    ):
        return f"RB_{side_code}_ForeArmRoll"

    if (
        "upper_arm_twist" in lower_name
        or "upper_arm_cloth_twist" in lower_name
        or "upper_arm_support" in lower_name
        or "upperarm_twist" in lower_name
        or "upperarm_roll" in lower_name
    ):
        return f"RB_{side_code}_ArmRoll"

    if "costume_support2" in lower_name:
        return f"SKEL_{side_code}_Forearm"
    if "costume_support1" in lower_name or "costume_support3" in lower_name:
        return f"SKEL_{side_code}_UpperArm"

    # 2. 1:1 mapping for all 30 canonical finger bones (SKEL_{L,R}_Finger{0..4}{0..2})
    finger_keywords = (
        ("thumb", 0),
        ("index", 1),
        ("middle", 2),
        ("ring", 3),
        ("little", 4),
        ("pinky", 4),
    )
    matched_finger_idx = None
    for keyword_token, finger_idx in finger_keywords:
        if keyword_token in lower_name:
            matched_finger_idx = finger_idx
            break

    if matched_finger_idx is None:
        return None

    if "proximal" in lower_name or "1" in lower_name:
        segment_idx = 0
    elif "intermediate" in lower_name or "2" in lower_name:
        segment_idx = 1
    elif "distal" in lower_name or "3" in lower_name:
        segment_idx = 2
    else:
        return None

    return f"SKEL_{side_code}_Finger{matched_finger_idx}{segment_idx}"


def extract_avatar_arm_hand_targets(
    fbx_armature_obj,
    scale_factor: float,
    z_offset: float,
    world_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Dict[str, "mathutils.Vector"]:
    """
    Extract post-pose (-55 deg) world-space coordinates of clavicle, upper arm,
    forearm, wrist, and all 30 finger joints converted into GTA V space.
    """
    import bpy
    import mathutils

    if fbx_armature_obj is None or fbx_armature_obj.type != "ARMATURE":
        raise ValueError(translate("hand.invalid_vrc_armature"))

    bpy.context.view_layer.update()

    arm_world_matrix = fbx_armature_obj.matrix_world
    offset_vector = mathutils.Vector(world_offset)
    bone_world_targets: Dict[str, mathutils.Vector] = {}

    for gtav_bone_name, candidate_names in VRC_ARM_HAND_BONE_CANDIDATES.items():
        matched_pose_bone = None
        for candidate_name in candidate_names:
            matched_pose_bone = fbx_armature_obj.pose.bones.get(candidate_name)
            if matched_pose_bone is not None:
                break
        if matched_pose_bone is None:
            continue

        raw_world_point = arm_world_matrix @ matched_pose_bone.head
        shifted_point = raw_world_point + offset_vector
        bone_world_targets[gtav_bone_name] = mathutils.Vector(
            (
                shifted_point.x * scale_factor,
                shifted_point.y * scale_factor,
                shifted_point.z * scale_factor + z_offset,
            )
        )

    required_main_bones = (
        "SKEL_L_Clavicle",
        "SKEL_L_UpperArm",
        "SKEL_L_Forearm",
        "SKEL_L_Hand",
        "SKEL_R_Clavicle",
        "SKEL_R_UpperArm",
        "SKEL_R_Forearm",
        "SKEL_R_Hand",
    )
    missing_main_bones = [
        bone_name for bone_name in required_main_bones if bone_name not in bone_world_targets
    ]
    missing_finger_bones = [
        bone_name for bone_name in GTAV_FINGER_BONE_NAMES if bone_name not in bone_world_targets
    ]
    if missing_main_bones or missing_finger_bones:
        raise RuntimeError(
            translate(
                "hand.missing_required_bones",
                main_bones=missing_main_bones,
                finger_bones=missing_finger_bones,
            )
        )

    # Compute mid-segment twist helpers (50%) and hand attachment helpers (PH/IK)
    for side_code in ("L", "R"):
        upper_arm_pos = bone_world_targets[f"SKEL_{side_code}_UpperArm"]
        forearm_pos = bone_world_targets[f"SKEL_{side_code}_Forearm"]
        hand_pos = bone_world_targets[f"SKEL_{side_code}_Hand"]

        bone_world_targets[f"RB_{side_code}_ArmRoll"] = upper_arm_pos.lerp(forearm_pos, 0.5)
        bone_world_targets[f"RB_{side_code}_ForeArmRoll"] = forearm_pos.lerp(hand_pos, 0.5)
        bone_world_targets[f"PH_{side_code}_Hand"] = hand_pos.copy()
        bone_world_targets[f"IK_{side_code}_Hand"] = hand_pos.copy()

    return bone_world_targets


def relocate_blender_armature_bones(
    ped_armature_obj,
    bone_world_targets: Dict[str, "mathutils.Vector"],
) -> int:
    """
    Translate upper-limb and finger edit bones (head/tail in parallel) on the
    GTA V Blender armature while keeping native bone orientations and roll intact.
    """
    import bpy
    import mathutils

    if ped_armature_obj is None or ped_armature_obj.type != "ARMATURE":
        raise ValueError(translate("hand.invalid_gtav_armature"))

    bpy.context.view_layer.objects.active = ped_armature_obj
    if ped_armature_obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.mode_set(mode="EDIT")

    arm_world_matrix = ped_armature_obj.matrix_world
    arm_world_inverse = arm_world_matrix.inverted()
    zero_delta = mathutils.Vector((0.0, 0.0, 0.0))
    relocated_counter = 0

    def walk_edit_bone(
        edit_bone_item,
        parent_delta_world: mathutils.Vector,
        inside_arm_subtree: bool,
    ) -> None:
        nonlocal relocated_counter
        current_subtree_flag = inside_arm_subtree or edit_bone_item.name in (
            "SKEL_L_Clavicle",
            "SKEL_R_Clavicle",
        )
        old_world_head = arm_world_matrix @ edit_bone_item.head
        tail_offset_local = (edit_bone_item.tail - edit_bone_item.head).copy()

        if edit_bone_item.name in bone_world_targets:
            new_world_head = bone_world_targets[edit_bone_item.name]
        elif current_subtree_flag:
            new_world_head = old_world_head + parent_delta_world
        else:
            new_world_head = old_world_head

        bone_delta_world = new_world_head - old_world_head
        if bone_delta_world.length > 1e-6:
            edit_bone_item.head = arm_world_inverse @ new_world_head
            edit_bone_item.tail = edit_bone_item.head + tail_offset_local
            relocated_counter += 1

        # Snapshot child references before recursion.
        child_edit_bones = list(edit_bone_item.children)
        for child_edit_bone in child_edit_bones:
            walk_edit_bone(child_edit_bone, bone_delta_world, current_subtree_flag)

    root_edit_bones = [
        edit_bone_item
        for edit_bone_item in ped_armature_obj.data.edit_bones
        if edit_bone_item.parent is None
    ]
    for root_edit_bone in root_edit_bones:
        walk_edit_bone(root_edit_bone, zero_delta, False)

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()
    return relocated_counter


def inject_custom_bones_into_blender_armature(
    armature_obj,
    custom_bones: Sequence[Dict[str, object]],
    bone_tag_fn: Optional[Callable[[str], int]] = None,
    bone_flags: Sequence[str] = ("RotX", "RotY", "RotZ", "TransX", "TransY", "TransZ"),
) -> int:
    """
    Inject custom articulated child bones (e.g., PB_Ear_L_0..2) into a Blender
    Sollumz armature in topological order and configure manual bone tags/DOFs.
    """
    import bpy
    import mathutils

    if not custom_bones:
        return 0

    arm_data = armature_obj.data
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode="EDIT")

    arm_inv_world = armature_obj.matrix_world.inverted()
    injected_count = 0

    for bone_desc in custom_bones:
        bone_name = str(bone_desc["name"])
        parent_name = str(bone_desc["parent_name"])
        parent_edit = arm_data.edit_bones.get(parent_name)
        if parent_edit is None:
            raise KeyError(f"Parent bone '{parent_name}' missing for custom bone '{bone_name}'")

        existing_edit = arm_data.edit_bones.get(bone_name)
        if existing_edit is not None:
            arm_data.edit_bones.remove(existing_edit)

        edit_bone = arm_data.edit_bones.new(bone_name)
        edit_bone.parent = parent_edit
        edit_bone.use_connect = False

        world_matrix = bone_desc["world_matrix"]
        arm_local_matrix = arm_inv_world @ world_matrix
        seg_length = max(0.01, float(bone_desc.get("length", 0.03)))

        head_vec = arm_local_matrix.translation.copy()
        rot_part = arm_local_matrix.to_3x3().normalized()
        y_dir = rot_part.col[1].normalized()
        if y_dir.length < 1e-6:
            y_dir = mathutils.Vector((0.0, 1.0, 0.0))

        edit_bone.head = head_vec
        edit_bone.tail = head_vec + y_dir * seg_length
        # Align exact 3D axes by assigning an orthonormal 4x4 local matrix
        ortho_mat = rot_part.to_4x4()
        ortho_mat.translation = head_vec
        edit_bone.matrix = ortho_mat
        injected_count += 1

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()

    for bone_desc in custom_bones:
        bone_name = str(bone_desc["name"])
        blender_bone = arm_data.bones.get(bone_name)
        if blender_bone is None:
            continue
        bone_props = blender_bone.bone_properties
        resolved_tag = int(bone_desc["tag"]) if "tag" in bone_desc else int(bone_tag_fn(bone_name))
        bone_props.manual_tag = resolved_tag
        bone_props.use_manual_tag = True
        bone_props.flags.clear()
        for flag_name in bone_flags:
            flag_item = bone_props.flags.add()
            flag_item.name = flag_name

    return injected_count


def _build_bone_local_matrix(bone_node, translation_vec) -> "mathutils.Matrix":
    """Construct a 4x4 local matrix from default_translation, default_rotation, and default_scale."""
    import mathutils

    rot_raw = bone_node.default_rotation
    scale_raw = bone_node.default_scale
    quat_val = mathutils.Quaternion(
        (float(rot_raw.w), float(rot_raw.x), float(rot_raw.y), float(rot_raw.z))
    )
    rot_matrix = quat_val.to_matrix().to_4x4()
    scale_matrix = mathutils.Matrix.Diagonal(
        (float(scale_raw.x), float(scale_raw.y), float(scale_raw.z), 1.0)
    )
    trans_matrix = mathutils.Matrix.Translation(translation_vec)
    return trans_matrix @ rot_matrix @ scale_matrix


def ensure_yft_shared_matrix_set_capacity(
    yft_file_path: Union[str, Path],
) -> Dict[str, int]:
    """
    Ensure an NPC/fragment `.yft`'s `fragType::m_SharedMatrixSet` (`+0xA8`) and
    its enclosing RSC7 virtual page have enough capacity for all
    `fragType + 0x130` (`crSkeletonData::m_NumBones`) skinning matrices (`0x30`
    bytes each). Prevents heap corruption / `ERR_SYS_INVALIDRESOURCE_5` when
    custom PhysBone or blink bones increase the `.yft` skeleton bone count.
    """
    import ped_damage_helper

    resolved_yft_path = Path(yft_file_path)
    raw_container = resolved_yft_path.read_bytes()
    if len(raw_container) < 16:
        raise ValueError(f"Invalid .yft resource (<16 bytes): {resolved_yft_path}")

    magic_bytes, rsc_version, sys_flags, gfx_flags = struct.unpack(
        "<4sIII", raw_container[:16]
    )
    if magic_bytes != b"RSC7":
        raise ValueError(
            f"Invalid RSC7 magic in '{resolved_yft_path.name}': {magic_bytes!r}"
        )

    raw_bytes = bytearray(zlib.decompress(raw_container[16:], -15))
    old_raw_bytes_len = len(raw_bytes)
    sys_layout = ped_damage_helper.decode_rsc7_page_layout(sys_flags)
    gfx_layout = ped_damage_helper.decode_rsc7_page_layout(gfx_flags)
    if len(raw_bytes) != int(sys_layout["total_bytes"]) + int(gfx_layout["total_bytes"]):
        raise ValueError(
            f"RSC7 page sum mismatch in '{resolved_yft_path.name}': "
            f"{sys_layout['total_bytes'] + gfx_layout['total_bytes']} != {len(raw_bytes)}"
        )

    frag_bone_count = struct.unpack_from("<Q", raw_bytes, 0x130)[0]
    shared_matrix_ptr = struct.unpack_from("<Q", raw_bytes, 0xA8)[0]
    if shared_matrix_ptr == 0:
        return {
            "shared_matrix_offset": 0,
            "bone_count": int(frag_bone_count),
            "expanded": 0,
            "old_raw_bytes": old_raw_bytes_len,
            "new_raw_bytes": old_raw_bytes_len,
        }

    matrix_set_off = int(shared_matrix_ptr) & 0x0FFFFFFF
    required_end = matrix_set_off + 0x20 + int(frag_bone_count) * 0x30
    sys_pages = sys_layout["pages"]
    containing_idx = -1
    for page_idx, page_item in enumerate(sys_pages):
        if page_item["start"] <= matrix_set_off < page_item["end"]:
            containing_idx = page_idx
            break
    if containing_idx < 0:
        raise ValueError(
            f"m_SharedMatrixSet offset 0x{matrix_set_off:x} outside RSC7 virtual pages "
            f"in '{resolved_yft_path.name}'"
        )

    containing_page = sys_pages[containing_idx]
    clamped_count = min(int(frag_bone_count), 255)
    needs_rewrite = False
    if raw_bytes[matrix_set_off + 0x10] < clamped_count:
        raw_bytes[matrix_set_off + 0x10] = clamped_count
        needs_rewrite = True
    if raw_bytes[matrix_set_off + 0x11] < clamped_count:
        raw_bytes[matrix_set_off + 0x11] = clamped_count
        needs_rewrite = True

    new_sys_flags = sys_flags
    expanded_flag = 0
    if required_end > containing_page["end"]:
        if containing_idx != len(sys_pages) - 1:
            raise ValueError(
                f"Cannot expand non-trailing virtual page {containing_idx} "
                f"(0x{containing_page['start']:x}..0x{containing_page['end']:x}) "
                f"for m_SharedMatrixSet in '{resolved_yft_path.name}'"
            )
        needed_page_bytes = required_end - int(containing_page["start"])
        old_bucket_idx = int(containing_page["bucket_index"])
        bucket_counts = list(sys_layout["bucket_counts"])
        bucket_sizes = list(sys_layout["bucket_sizes"])
        bucket_specs = sys_layout["bucket_specs"]

        if bucket_counts[old_bucket_idx] != 1:
            raise ValueError(
                f"Cannot resize trailing RSC7 page in '{resolved_yft_path.name}' "
                f"without shifting sibling pages: bucket[{old_bucket_idx}] count={bucket_counts[old_bucket_idx]}"
            )

        target_bucket_idx = -1
        for candidate_idx in range(old_bucket_idx - 1, -1, -1):
            if any(bucket_counts[mid_idx] != 0 for mid_idx in range(candidate_idx + 1, old_bucket_idx)):
                break
            max_bucket_val = (1 << int(bucket_specs[candidate_idx][2])) - 1
            if bucket_sizes[candidate_idx] >= needed_page_bytes and (
                bucket_counts[candidate_idx] + 1 <= max_bucket_val
            ):
                target_bucket_idx = candidate_idx
                break

        if target_bucket_idx < 0:
            raise ValueError(
                f"No safe RSC7 trailing page bucket can fit {needed_page_bytes} bytes "
                f"in '{resolved_yft_path.name}'"
            )

        bucket_counts[old_bucket_idx] -= 1
        bucket_counts[target_bucket_idx] += 1
        new_sys_flags = ped_damage_helper.encode_rsc7_page_flags(
            sys_layout["top_nibble"],
            sys_layout["base_shift"],
            bucket_counts,
        )
        new_page_end = int(containing_page["start"]) + int(bucket_sizes[target_bucket_idx])
        padding_bytes = new_page_end - int(containing_page["end"])
        if int(gfx_layout["total_bytes"]) == 0:
            raw_bytes.extend(b"\x00" * padding_bytes)
        else:
            sys_end = int(sys_layout["total_bytes"])
            raw_bytes[sys_end:sys_end] = b"\x00" * padding_bytes
        needs_rewrite = True
        expanded_flag = 1

    if needs_rewrite:
        compressor_obj = zlib.compressobj(level=9, wbits=-15)
        compressed_payload = compressor_obj.compress(bytes(raw_bytes)) + compressor_obj.flush()
        header_bytes = struct.pack("<4sIII", magic_bytes, rsc_version, new_sys_flags, gfx_flags)
        resolved_yft_path.write_bytes(header_bytes + compressed_payload)

    ped_damage_helper.validate_yft_rsc7_page_bounds(resolved_yft_path)
    return {
        "shared_matrix_offset": matrix_set_off,
        "bone_count": int(frag_bone_count),
        "expanded": expanded_flag,
        "old_raw_bytes": old_raw_bytes_len,
        "new_raw_bytes": len(raw_bytes),
    }


def patch_yft_skeleton(
    source_yft_path: Path,
    output_yft_path: Path,
    bone_world_targets: Dict[str, "mathutils.Vector"],
    custom_child_bones: Optional[Sequence[Dict[str, object]]] = None,
) -> Tuple[int, int, float]:
    """
    Update `default_translation` entries in the .yft fragment skeleton via PyMateria,
    preserving original rotations/scales and propagating deltas to unmapped children
    inside SKEL_L_Clavicle and SKEL_R_Clavicle chains. Optionally appends custom child
    bones (e.g., articulated PhysBone ear chains under SKEL_Head).

    Also re-imports the exported .yft to verify exact round-trip target coordinates.
    """
    import mathutils
    import pymateria as pymateria_root
    import pymateria.gta5 as gta5_module
    import pymateria.gta5.gen8 as gen8_module

    resolved_source = Path(source_yft_path)
    resolved_output = Path(output_yft_path)
    if not resolved_source.is_file():
        raise FileNotFoundError(
            translate("hand.yft_source_not_found", path=resolved_source)
        )

    fragment_asset = gen8_module.Fragment.import_rsc(str(resolved_source)).result
    if fragment_asset is None or fragment_asset.drawable is None:
        raise RuntimeError(translate("hand.fragment_missing_drawable", path=resolved_source))
    skeleton_obj = fragment_asset.drawable.skeleton
    if skeleton_obj is None or skeleton_obj.root_bone is None:
        raise RuntimeError(translate("hand.fragment_missing_skeleton", path=resolved_source))

    updated_bones_count = 0
    total_bones_count = 0
    identity_matrix = mathutils.Matrix.Identity(4)
    zero_delta = mathutils.Vector((0.0, 0.0, 0.0))

    def walk_yft_bone(
        bone_node,
        old_parent_world: mathutils.Matrix,
        new_parent_world: mathutils.Matrix,
        parent_delta_world: mathutils.Vector,
        inside_arm_subtree: bool,
    ) -> None:
        nonlocal updated_bones_count, total_bones_count
        total_bones_count += 1
        current_subtree_flag = inside_arm_subtree or bone_node.name in (
            "SKEL_L_Clavicle",
            "SKEL_R_Clavicle",
        )

        old_trans_raw = bone_node.default_translation
        old_local_trans = mathutils.Vector(
            (float(old_trans_raw.x), float(old_trans_raw.y), float(old_trans_raw.z))
        )
        old_local_matrix = _build_bone_local_matrix(bone_node, old_local_trans)
        old_world_matrix = old_parent_world @ old_local_matrix
        old_world_pos = old_world_matrix.translation.copy()

        if bone_node.name in bone_world_targets:
            target_point = bone_world_targets[bone_node.name]
            new_world_pos = mathutils.Vector(
                (float(target_point.x), float(target_point.y), float(target_point.z))
            )
        elif current_subtree_flag:
            new_world_pos = old_world_pos + parent_delta_world
        else:
            new_world_pos = old_world_pos

        delta_world = new_world_pos - old_world_pos
        new_local_trans = new_parent_world.inverted() @ new_world_pos
        if delta_world.length > 1e-6:
            bone_node.default_translation = pymateria_root.Vector4f(
                float(new_local_trans.x),
                float(new_local_trans.y),
                float(new_local_trans.z),
                float(old_trans_raw.w),
            )
            updated_bones_count += 1

        new_local_matrix = _build_bone_local_matrix(bone_node, new_local_trans)
        new_world_matrix = new_parent_world @ new_local_matrix

        for child_bone_node in bone_node.children:
            walk_yft_bone(
                child_bone_node,
                old_world_matrix,
                new_world_matrix,
                delta_world,
                current_subtree_flag,
            )

    walk_yft_bone(
        skeleton_obj.root_bone,
        identity_matrix,
        identity_matrix,
        zero_delta,
        False,
    )

    expected_custom_positions: Dict[str, mathutils.Vector] = {}
    if custom_child_bones:
        bones_by_name: Dict[str, object] = {}
        world_matrices: Dict[str, mathutils.Matrix] = {}
        custom_names = {str(item["name"]) for item in custom_child_bones}

        def index_skeleton_node(bone_node, parent_world: mathutils.Matrix) -> None:
            # Prune pre-existing custom bones on re-runs for idempotency
            kept_children = [
                child_node
                for child_node in bone_node.children
                if child_node.name not in custom_names
            ]
            if len(kept_children) != len(bone_node.children):
                bone_node.children[:] = kept_children
            trans_raw = bone_node.default_translation
            local_trans = mathutils.Vector(
                (float(trans_raw.x), float(trans_raw.y), float(trans_raw.z))
            )
            world_mat = parent_world @ _build_bone_local_matrix(bone_node, local_trans)
            bones_by_name[bone_node.name] = bone_node
            world_matrices[bone_node.name] = world_mat
            for child_node in bone_node.children:
                index_skeleton_node(child_node, world_mat)

        index_skeleton_node(skeleton_obj.root_bone, identity_matrix)
        parent_set = {str(item["parent_name"]) for item in custom_child_bones}

        for bone_desc in custom_child_bones:
            bone_name = str(bone_desc["name"])
            parent_name = str(bone_desc["parent_name"])
            parent_bone = bones_by_name.get(parent_name)
            parent_world = world_matrices.get(parent_name)
            if parent_bone is None or parent_world is None:
                raise KeyError(
                    f"Cannot attach custom YFT bone '{bone_name}': parent '{parent_name}' missing"
                )
            parent_bone.degrees_of_freedom = int(parent_bone.degrees_of_freedom) | 0x1000
            target_world = bone_desc["world_matrix"]
            local_mat = parent_world.inverted() @ target_world
            local_pos, local_rot, _local_scale = local_mat.decompose()

            new_bone = gta5_module.Bone()
            new_bone.name = bone_name
            new_bone.id = int(bone_desc["tag"])
            new_bone.degrees_of_freedom = 0x1077 if bone_name in parent_set else 0x0077
            new_bone.default_translation = pymateria_root.Vector4f(
                float(local_pos.x), float(local_pos.y), float(local_pos.z), 0.0
            )
            new_bone.default_rotation = pymateria_root.Quaternion(
                float(local_rot.x), float(local_rot.y), float(local_rot.z), float(local_rot.w)
            )
            new_bone.default_scale = pymateria_root.Vector4f(1.0, 1.0, 1.0, 1.0)
            parent_bone.children.append(new_bone)

            bones_by_name[bone_name] = new_bone
            world_matrices[bone_name] = target_world.copy()
            expected_custom_positions[bone_name] = target_world.translation.copy()
            total_bones_count += 1
            updated_bones_count += 1

    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    gen8_module.Fragment.export_rsc(fragment_asset, str(resolved_output))
    ensure_yft_shared_matrix_set_capacity(resolved_output)

    # Round-trip validation after binary export
    verify_fragment = gen8_module.Fragment.import_rsc(str(resolved_output)).result
    verify_positions: Dict[str, mathutils.Vector] = {}
    verify_tags: Dict[str, int] = {}

    def collect_verified_positions(bone_node, parent_world: mathutils.Matrix) -> None:
        trans_raw = bone_node.default_translation
        local_trans = mathutils.Vector(
            (float(trans_raw.x), float(trans_raw.y), float(trans_raw.z))
        )
        world_matrix = parent_world @ _build_bone_local_matrix(bone_node, local_trans)
        verify_positions[bone_node.name] = world_matrix.translation.copy()
        verify_tags[bone_node.name] = int(bone_node.id)
        for child_bone_node in bone_node.children:
            collect_verified_positions(child_bone_node, world_matrix)

    collect_verified_positions(
        verify_fragment.drawable.skeleton.root_bone, identity_matrix
    )

    combined_targets = dict(bone_world_targets)
    combined_targets.update(expected_custom_positions)

    max_roundtrip_error = 0.0
    for bone_name, expected_vec in combined_targets.items():
        if bone_name not in verify_positions:
            raise RuntimeError(
                translate(
                    "hand.target_bone_disappeared",
                    bone_name=bone_name,
                    path=resolved_output,
                )
            )
        target_vec = mathutils.Vector(
            (float(expected_vec.x), float(expected_vec.y), float(expected_vec.z))
        )
        diff_len = (verify_positions[bone_name] - target_vec).length
        if diff_len > max_roundtrip_error:
            max_roundtrip_error = diff_len

    for bone_desc in custom_child_bones or ():
        bone_name = str(bone_desc["name"])
        if verify_tags.get(bone_name) != int(bone_desc["tag"]):
            raise RuntimeError(
                f"Custom YFT bone '{bone_name}' tag mismatch after export: "
                f"expected {bone_desc['tag']}, got {verify_tags.get(bone_name)}"
            )

    if max_roundtrip_error > 1e-3:
        raise RuntimeError(
            translate(
                "hand.roundtrip_error_excessive",
                filename=resolved_output.name,
                error_meters=max_roundtrip_error,
            )
        )

    return updated_bones_count, total_bones_count, max_roundtrip_error
