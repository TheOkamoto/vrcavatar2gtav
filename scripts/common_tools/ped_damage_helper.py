#!/usr/bin/env python3
"""
ped_damage_helper.py
====================
Shared GTA V RAGE ped blood/wound decal helper for VRChat-to-GTAV builds.

Configures Sollumz `ped.sps` materials (the GTA V ped shader that binds
`pedBloodTargetSampler` and `pedTattooTargetSampler` in `ped.fxc`), generates
the 6-zone cylindrical `UVMap 1` (`TexCoord1`) layout expected by
`peddamage.xml` (`CPedDamageCylinderInfoSet::HUMAN`), and initializes
standard ped vertex colors (`Color 1` = `#FF8000FF`, `Color 2` = `#00000000`).
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


PED_DAMAGE_SHADER_NAME = "ped.sps"
PED_NO_DAMAGE_SHADER_NAME = "ped_default.sps"

# Standard GTA V ped vertex color byte defaults (`#FF8000FF` and `#00000000`)
DEFAULT_PED_COLOR1_SRGB: Tuple[float, float, float, float] = (
    1.0,
    128.0 / 255.0,
    0.0,
    1.0,
)
DEFAULT_PED_COLOR2_SRGB: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

# Vanilla RAGE damage zone indices decoded in `ped.fxc` via:
# `zone = int((-TexCoord1.y + 0.5) * 0.5)` where `v_ydd = 1.0 - v_blender`.
DAMAGE_ZONE_NONE = -1
DAMAGE_ZONE_TORSO = 0
DAMAGE_ZONE_HEAD = 1
DAMAGE_ZONE_LEFT_ARM = 2
DAMAGE_ZONE_RIGHT_ARM = 3
DAMAGE_ZONE_LEFT_LEG = 4
DAMAGE_ZONE_RIGHT_LEG = 5

DAMAGE_ZONE_NAMES: Dict[int, str] = {
    DAMAGE_ZONE_NONE: "unmapped",
    DAMAGE_ZONE_TORSO: "torso",
    DAMAGE_ZONE_HEAD: "head",
    DAMAGE_ZONE_LEFT_ARM: "left_arm",
    DAMAGE_ZONE_RIGHT_ARM: "right_arm",
    DAMAGE_ZONE_LEFT_LEG: "left_leg",
    DAMAGE_ZONE_RIGHT_LEG: "right_leg",
}

DEFAULT_HUMAN_BONE_POSITIONS: Dict[str, Tuple[float, float, float]] = {
    "SKEL_Pelvis": (0.0, 0.0071, -0.0187),
    "SKEL_L_Thigh": (0.0961, 0.0073, -0.0922),
    "SKEL_L_Calf": (0.1274, 0.0242, -0.4972),
    "SKEL_L_Foot": (0.1585, 0.0587, -0.9075),
    "SKEL_R_Thigh": (-0.0961, 0.0073, -0.0922),
    "SKEL_R_Calf": (-0.1274, 0.0242, -0.4972),
    "SKEL_R_Foot": (-0.1585, 0.0587, -0.9075),
    "SKEL_Spine3": (0.0, 0.0319, 0.2831),
    "SKEL_Neck_1": (0.0, 0.0288, 0.5316),
    "SKEL_Head": (0.0, 0.0029, 0.6417),
    "SKEL_L_UpperArm": (0.1222, 0.0271, 0.5331),
    "SKEL_L_Forearm": (0.2956, 0.0045, 0.2865),
    "SKEL_L_Hand": (0.4704, -0.0223, 0.0376),
    "SKEL_L_Finger22": (0.5612, -0.0461, -0.0969),
    "SKEL_R_UpperArm": (-0.1222, 0.0271, 0.5331),
    "SKEL_R_Forearm": (-0.2956, 0.0045, 0.2865),
    "SKEL_R_Hand": (-0.4704, -0.0223, 0.0376),
    "SKEL_R_Finger22": (-0.5612, -0.0461, -0.0969),
}


def _vec_sub(vec_a: Sequence[float], vec_b: Sequence[float]) -> Tuple[float, float, float]:
    return (
        float(vec_a[0]) - float(vec_b[0]),
        float(vec_a[1]) - float(vec_b[1]),
        float(vec_a[2]) - float(vec_b[2]),
    )


def _vec_add(vec_a: Sequence[float], vec_b: Sequence[float]) -> Tuple[float, float, float]:
    return (
        float(vec_a[0]) + float(vec_b[0]),
        float(vec_a[1]) + float(vec_b[1]),
        float(vec_a[2]) + float(vec_b[2]),
    )


def _vec_scale(vec_a: Sequence[float], scalar: float) -> Tuple[float, float, float]:
    return (
        float(vec_a[0]) * float(scalar),
        float(vec_a[1]) * float(scalar),
        float(vec_a[2]) * float(scalar),
    )


def _vec_dot(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    return (
        float(vec_a[0]) * float(vec_b[0])
        + float(vec_a[1]) * float(vec_b[1])
        + float(vec_a[2]) * float(vec_b[2])
    )


def _vec_cross(vec_a: Sequence[float], vec_b: Sequence[float]) -> Tuple[float, float, float]:
    return (
        float(vec_a[1]) * float(vec_b[2]) - float(vec_a[2]) * float(vec_b[1]),
        float(vec_a[2]) * float(vec_b[0]) - float(vec_a[0]) * float(vec_b[2]),
        float(vec_a[0]) * float(vec_b[1]) - float(vec_a[1]) * float(vec_b[0]),
    )


def _vec_len(vec_a: Sequence[float]) -> float:
    return math.sqrt(_vec_dot(vec_a, vec_a))


def _vec_normalize(
    vec_a: Sequence[float], fallback: Tuple[float, float, float] = (0.0, 0.0, 1.0)
) -> Tuple[float, float, float]:
    length = _vec_len(vec_a)
    if length < 1e-8:
        return fallback
    return (vec_a[0] / length, vec_a[1] / length, vec_a[2] / length)


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


def _closest_point_on_polyline(
    point: Sequence[float], polyline: Sequence[Tuple[float, float, float]]
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Return closest point on a piecewise bone polyline and that segment's unit tangent."""
    if len(polyline) < 2:
        anchor = polyline[0] if polyline else (0.0, 0.0, 0.0)
        return anchor, (0.0, 0.0, 1.0)

    best_dist_sq = float("inf")
    best_closest = polyline[0]
    best_tangent = _vec_normalize(_vec_sub(polyline[1], polyline[0]))

    for seg_idx in range(len(polyline) - 1):
        seg_start = polyline[seg_idx]
        seg_end = polyline[seg_idx + 1]
        seg_delta = _vec_sub(seg_end, seg_start)
        seg_len_sq = _vec_dot(seg_delta, seg_delta)
        if seg_len_sq < 1e-10:
            continue
        proj = _clamp(_vec_dot(_vec_sub(point, seg_start), seg_delta) / seg_len_sq, 0.0, 1.0)
        cand_point = _vec_add(seg_start, _vec_scale(seg_delta, proj))
        diff = _vec_sub(point, cand_point)
        dist_sq = _vec_dot(diff, diff)
        if dist_sq < best_dist_sq:
            best_dist_sq = dist_sq
            best_closest = cand_point
            best_tangent = _vec_normalize(seg_delta)

    return best_closest, best_tangent


def resolve_ped_shader_filename(enable_blood_decals: bool = True) -> str:
    """Return the GTA V ped shader filename for Sollumz (`ped.sps` when decals are enabled)."""
    return PED_DAMAGE_SHADER_NAME if enable_blood_decals else PED_NO_DAMAGE_SHADER_NAME


def configure_ped_shader_material(
    shader_material: Any,
    *,
    diffuse_image: Any = None,
    bump_image: Any = None,
    spec_image: Any = None,
    bumpiness: float = 0.0,
    specular_intensity: float = 0.0,
    specular_falloff: float = 1.0,
    specular_fresnel: float = 0.0,
    detail_settings: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    stubble_control: Tuple[float, float] = (0.0, 0.0),
    um_global_params: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
) -> Any:
    """Configure samplers and scalar/vector parameters on a Sollumz ped material."""
    node_tree = getattr(shader_material, "node_tree", None)
    if node_tree is None:
        return shader_material

    sampler_images = (
        ("DiffuseSampler", diffuse_image),
        ("BumpSampler", bump_image),
        ("SpecSampler", spec_image),
    )
    for sampler_name, image_obj in sampler_images:
        if image_obj is None:
            continue
        tex_node = node_tree.nodes.get(sampler_name)
        if tex_node is not None:
            tex_node.image = image_obj
            tex_props = getattr(tex_node, "texture_properties", None)
            if tex_props is not None:
                tex_props.embedded = False

    for shader_node in node_tree.nodes:
        node_name = getattr(shader_node, "name", "")
        if node_name == "bumpiness" and hasattr(shader_node, "set_float"):
            shader_node.set_float(float(bumpiness))
        elif node_name == "specularIntensityMult" and hasattr(shader_node, "set_float"):
            shader_node.set_float(float(specular_intensity))
        elif node_name == "specularFalloffMult" and hasattr(shader_node, "set_float"):
            shader_node.set_float(float(specular_falloff))
        elif node_name == "specularFresnel" and hasattr(shader_node, "set_float"):
            shader_node.set_float(float(specular_fresnel))
        elif node_name == "StubbleControl" and hasattr(shader_node, "set_vec2"):
            shader_node.set_vec2((float(stubble_control[0]), float(stubble_control[1])))
        elif node_name == "detailSettings":
            if hasattr(shader_node, "set_vec3"):
                shader_node.set_vec3(
                    (
                        float(detail_settings[0]),
                        float(detail_settings[1]),
                        float(detail_settings[2]),
                    )
                )
            elif hasattr(shader_node, "set_vec4"):
                shader_node.set_vec4(
                    (
                        float(detail_settings[0]),
                        float(detail_settings[1]),
                        float(detail_settings[2]),
                        0.0,
                    )
                )
        elif node_name == "umGlobalParams" and hasattr(shader_node, "set_vec4"):
            shader_node.set_vec4(
                (
                    float(um_global_params[0]),
                    float(um_global_params[1]),
                    float(um_global_params[2]),
                    float(um_global_params[3]),
                )
            )
    return shader_material


def create_ped_material(
    shader_creator: Callable[[str], Any],
    material_name: str,
    *,
    enable_blood_decals: bool = True,
    diffuse_image: Any = None,
    bump_image: Any = None,
    spec_image: Any = None,
    bumpiness: float = 0.0,
    specular_intensity: float = 0.0,
    specular_falloff: float = 1.0,
    specular_fresnel: float = 0.0,
    detail_settings: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    stubble_control: Tuple[float, float] = (0.0, 0.0),
    um_global_params: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
) -> Any:
    """Instantiate and calibrate a Sollumz ped material with optional blood decal support."""
    shader_filename = resolve_ped_shader_filename(enable_blood_decals)
    shader_material = shader_creator(shader_filename)
    shader_material.name = material_name
    return configure_ped_shader_material(
        shader_material,
        diffuse_image=diffuse_image,
        bump_image=bump_image,
        spec_image=spec_image,
        bumpiness=bumpiness,
        specular_intensity=specular_intensity,
        specular_falloff=specular_falloff,
        specular_fresnel=specular_fresnel,
        detail_settings=detail_settings,
        stubble_control=stubble_control,
        um_global_params=um_global_params,
    )


def extract_armature_bone_positions(armature_obj: Any) -> Dict[str, Tuple[float, float, float]]:
    """Extract armature rest-pose head positions keyed by bone name."""
    positions: Dict[str, Tuple[float, float, float]] = {}
    if armature_obj is None or getattr(armature_obj, "data", None) is None:
        return positions
    bones_coll = getattr(armature_obj.data, "bones", ()) or ()
    world_mtx = getattr(armature_obj, "matrix_world", None)
    for bone_item in bones_coll:
        head_local = getattr(bone_item, "head_local", None)
        if head_local is None:
            continue
        if world_mtx is not None:
            try:
                head_world = world_mtx @ head_local
            except Exception:
                head_world = head_local
        else:
            head_world = head_local
        positions[str(bone_item.name)] = (
            float(head_world[0]),
            float(head_world[1]),
            float(head_world[2]),
        )
    return positions


def _get_bone_pos(
    bone_positions: Mapping[str, Sequence[float]], bone_name: str
) -> Tuple[float, float, float]:
    raw_val = bone_positions.get(bone_name)
    if raw_val is not None and len(raw_val) >= 3:
        return (float(raw_val[0]), float(raw_val[1]), float(raw_val[2]))
    fallback = DEFAULT_HUMAN_BONE_POSITIONS[bone_name]
    return (float(fallback[0]), float(fallback[1]), float(fallback[2]))


def build_damage_cylinders(
    bone_positions: Optional[Mapping[str, Sequence[float]]] = None,
) -> Dict[str, Any]:
    """
    Build the 6 GTA V ped-damage projection cylinders anchored to the character's bones.
    Matches the bone associations and orientation offsets in `peddamage.xml` (HUMAN).
    """
    bones = bone_positions or {}
    pelvis = _get_bone_pos(bones, "SKEL_Pelvis")
    left_thigh = _get_bone_pos(bones, "SKEL_L_Thigh")
    left_calf = _get_bone_pos(bones, "SKEL_L_Calf")
    left_foot = _get_bone_pos(bones, "SKEL_L_Foot")
    right_thigh = _get_bone_pos(bones, "SKEL_R_Thigh")
    right_calf = _get_bone_pos(bones, "SKEL_R_Calf")
    right_foot = _get_bone_pos(bones, "SKEL_R_Foot")
    neck = _get_bone_pos(bones, "SKEL_Neck_1")
    head = _get_bone_pos(bones, "SKEL_Head")

    left_upper_arm = _get_bone_pos(bones, "SKEL_L_UpperArm")
    left_forearm = _get_bone_pos(bones, "SKEL_L_Forearm")
    left_hand = _get_bone_pos(bones, "SKEL_L_Hand")
    left_finger = bones.get("SKEL_L_Finger22")
    if left_finger is None:
        hand_dir = _vec_normalize(_vec_sub(left_hand, left_forearm), (0.6, -0.1, -0.8))
        left_finger_pt = _vec_add(left_hand, _vec_scale(hand_dir, 0.14))
    else:
        left_finger_pt = (float(left_finger[0]), float(left_finger[1]), float(left_finger[2]))

    right_upper_arm = _get_bone_pos(bones, "SKEL_R_UpperArm")
    right_forearm = _get_bone_pos(bones, "SKEL_R_Forearm")
    right_hand = _get_bone_pos(bones, "SKEL_R_Hand")
    right_finger = bones.get("SKEL_R_Finger22")
    if right_finger is None:
        hand_dir_r = _vec_normalize(_vec_sub(right_hand, right_forearm), (-0.6, -0.1, -0.8))
        right_finger_pt = _vec_add(right_hand, _vec_scale(hand_dir_r, 0.14))
    else:
        right_finger_pt = (float(right_finger[0]), float(right_finger[1]), float(right_finger[2]))

    mid_thigh = (
        0.5 * (left_thigh[0] + right_thigh[0]),
        0.5 * (left_thigh[1] + right_thigh[1]),
        0.5 * (left_thigh[2] + right_thigh[2]),
    )
    torso_delta = _vec_sub(neck, mid_thigh)
    torso_axis = _vec_normalize((0.0, torso_delta[1], torso_delta[2]), (0.0, 0.0, 1.0))
    torso_span = max(0.25, _vec_dot(torso_delta, torso_axis))

    head_delta = _vec_sub(head, neck)
    head_axis = _vec_normalize((0.0, head_delta[1], head_delta[2]), (0.0, -0.22, 0.975))
    head_span = max(0.08, _vec_dot(head_delta, head_axis))

    left_arm_delta = _vec_sub(left_upper_arm, left_finger_pt)
    left_arm_axis = _vec_normalize(left_arm_delta, (-0.57, 0.09, 0.82))
    left_arm_span = max(0.20, _vec_dot(left_arm_delta, left_arm_axis))

    right_arm_delta = _vec_sub(right_upper_arm, right_finger_pt)
    right_arm_axis = _vec_normalize(right_arm_delta, (0.57, 0.09, 0.82))
    right_arm_span = max(0.20, _vec_dot(right_arm_delta, right_arm_axis))

    left_leg_delta = _vec_sub(left_thigh, left_foot)
    left_leg_axis = _vec_normalize(left_leg_delta, (-0.07, -0.06, 0.995))
    left_leg_span = max(0.25, _vec_dot(left_leg_delta, left_leg_axis))

    right_leg_delta = _vec_sub(right_thigh, right_foot)
    right_leg_axis = _vec_normalize(right_leg_delta, (0.07, -0.06, 0.995))
    right_leg_span = max(0.25, _vec_dot(right_leg_delta, right_leg_axis))

    left_toe_pt = _vec_add(left_foot, (0.0, -0.10, -0.07))
    right_toe_pt = _vec_add(right_foot, (0.0, -0.10, -0.07))

    return {
        "pelvis_z": pelvis[2],
        "thigh_z": mid_thigh[2],
        "neck_z": neck[2],
        "head_z": head[2],
        "shoulder_x_min": min(abs(left_upper_arm[0]), abs(right_upper_arm[0])),
        DAMAGE_ZONE_TORSO: {
            "base": mid_thigh,
            "axis": torso_axis,
            "t_base": 0.20,
            "t_slope": 0.70 / torso_span,
            "polyline": (mid_thigh, (0.0, neck[1], neck[2])),
            "seam_hint": (1.0, 0.0, 0.0),
        },
        DAMAGE_ZONE_HEAD: {
            "base": neck,
            "axis": head_axis,
            "t_base": 0.05,
            "t_slope": 0.306 / head_span,
            "polyline": (neck, head, _vec_add(head, _vec_scale(head_axis, 0.25))),
            "seam_hint": (0.0, 1.0, 0.0),
        },
        DAMAGE_ZONE_LEFT_ARM: {
            "base": left_finger_pt,
            "axis": left_arm_axis,
            "t_base": 0.09,
            "t_slope": 0.84 / left_arm_span,
            "polyline": (left_finger_pt, left_hand, left_forearm, left_upper_arm),
            "seam_hint": (-0.4, 0.0, -0.9),
        },
        DAMAGE_ZONE_RIGHT_ARM: {
            "base": right_finger_pt,
            "axis": right_arm_axis,
            "t_base": 0.09,
            "t_slope": 0.84 / right_arm_span,
            "polyline": (right_finger_pt, right_hand, right_forearm, right_upper_arm),
            "seam_hint": (0.4, 0.0, -0.9),
        },
        DAMAGE_ZONE_LEFT_LEG: {
            "base": left_foot,
            "axis": left_leg_axis,
            "t_base": 0.14,
            "t_slope": 0.82 / left_leg_span,
            "polyline": (left_toe_pt, left_foot, left_calf, left_thigh),
            "seam_hint": (-1.0, 0.0, 0.0),
        },
        DAMAGE_ZONE_RIGHT_LEG: {
            "base": right_foot,
            "axis": right_leg_axis,
            "t_base": 0.14,
            "t_slope": 0.82 / right_leg_span,
            "polyline": (right_toe_pt, right_foot, right_calf, right_thigh),
            "seam_hint": (1.0, 0.0, 0.0),
        },
    }


def classify_bone_name_to_damage_zone(
    bone_name: str,
    pos_x: float = 0.0,
    pos_z: float = 0.0,
    neck_z: float = 0.5316,
) -> int:
    """Map a GTA/PhysBone vertex-group name onto one of the 6 GTA V ped damage zones."""
    low = (bone_name or "").strip().lower()
    if not low:
        return DAMAGE_ZONE_TORSO

    # Tails get no decals to avoid torso/leg blood mirroring onto fluffy tail geometry.
    if "tail" in low:
        return DAMAGE_ZONE_NONE

    # Keep long back/chest hair locks below the neck unmapped while head/ear tufts use Head.
    if "hair" in low:
        return DAMAGE_ZONE_HEAD if pos_z >= (neck_z - 0.04) else DAMAGE_ZONE_NONE

    if any(tok in low for tok in ("skel_head", "skel_neck", "facial_", "_ear", "ear_", "earl", "earr")):
        return DAMAGE_ZONE_HEAD

    # Skirt/apron/ribbon PhysBones follow Rockstar's skirt rule (Torso zone, not split across thighs).
    if any(
        tok in low
        for tok in (
            "skirt",
            "apron",
            "ribbon",
            "dress",
            "coat",
            "cape",
            "pelvis",
            "spine",
            "clavicle",
            "bumroll",
            "butt_",
            "bust",
            "breast",
            "boob",
            "chest",
            "waist",
            "heart",
            "pocket",
            "bag",
        )
    ):
        return DAMAGE_ZONE_TORSO

    is_left = (
        "_l_" in low
        or low.endswith("_l")
        or ".l" in low
        or "left" in low
    )
    is_right = (
        "_r_" in low
        or low.endswith("_r")
        or ".r" in low
        or "right" in low
    )

    if any(
        tok in low
        for tok in (
            "upperarm",
            "forearm",
            "armroll",
            "hand",
            "finger",
            "elbow",
            "wrist",
            "sleeve",
            "cuff",
            "bicep",
            "armpit",
            "wristwatch",
        )
    ):
        if is_left:
            return DAMAGE_ZONE_LEFT_ARM
        if is_right:
            return DAMAGE_ZONE_RIGHT_ARM
        return DAMAGE_ZONE_LEFT_ARM if pos_x >= 0.0 else DAMAGE_ZONE_RIGHT_ARM

    if any(
        tok in low
        for tok in (
            "thigh",
            "calf",
            "knee",
            "foot",
            "toe",
            "ankle",
            "legstrap",
            "stocking",
            "sock",
            "shoe",
            "boot",
            "heel",
            "panthem",
            "flipper",
            "flipflop",
        )
    ):
        if is_left:
            return DAMAGE_ZONE_LEFT_LEG
        if is_right:
            return DAMAGE_ZONE_RIGHT_LEG
        return DAMAGE_ZONE_LEFT_LEG if pos_x >= 0.0 else DAMAGE_ZONE_RIGHT_LEG

    return DAMAGE_ZONE_TORSO


def classify_spatial_damage_zone(
    pos_x: float,
    pos_y: float,
    pos_z: float,
    cylinders: Mapping[str, Any],
) -> int:
    """Fallback 3D zone classification when a vertex has no informative bone weights."""
    del pos_y
    neck_z = float(cylinders.get("neck_z", 0.5316))
    thigh_z = float(cylinders.get("thigh_z", -0.0922))
    shoulder_x_min = float(cylinders.get("shoulder_x_min", 0.12))

    if pos_z >= (neck_z - 0.02):
        return DAMAGE_ZONE_HEAD
    if abs(pos_x) >= (shoulder_x_min + 0.08) and pos_z >= thigh_z:
        return DAMAGE_ZONE_LEFT_ARM if pos_x >= 0.0 else DAMAGE_ZONE_RIGHT_ARM
    if pos_z < (thigh_z - 0.04):
        return DAMAGE_ZONE_LEFT_LEG if pos_x >= 0.0 else DAMAGE_ZONE_RIGHT_LEG
    return DAMAGE_ZONE_TORSO


def project_point_onto_damage_zone(
    point: Sequence[float],
    zone_id: int,
    cylinders: Mapping[str, Any],
) -> Tuple[float, float]:
    """
    Project a 3D rest-pose point onto Blender `UVMap 1` `(u, v_blender)` coordinates.

    `v_blender` follows Sollumz `flip_uvs` (`v_ydd = 1.0 - v_blender`) so that:
      - zone 0 (Torso):     v_bl in [1.02, 1.98] -> v_ydd in [-0.98, -0.02]
      - zone 1 (Head):      v_bl in [3.02, 3.98] -> v_ydd in [-2.98, -2.02]
      - zone 2 (Left Arm):  v_bl in [5.02, 5.98] -> v_ydd in [-4.98, -4.02]
      - zone 3 (Right Arm): v_bl in [7.02, 7.98] -> v_ydd in [-6.98, -6.02]
      - zone 4 (Left Leg):  v_bl in [9.02, 9.98] -> v_ydd in [-8.98, -8.02]
      - zone 5 (Right Leg): v_bl in [11.02, 11.98] -> v_ydd in [-10.98, -10.02]
      - zone -1 (unmapped): (0.0, 0.0) -> (0.0, 1.0) in .ydd (skipped by ped.fxc)
    """
    if zone_id == DAMAGE_ZONE_NONE or zone_id not in cylinders:
        return (0.0, 0.0)

    spec = cylinders[zone_id]
    base_pt = spec["base"]
    axis_hat = spec["axis"]
    t_along = spec["t_base"] + spec["t_slope"] * _vec_dot(_vec_sub(point, base_pt), axis_hat)
    t_clamped = _clamp(t_along, 0.02, 0.98)

    center_pt, seg_tan = _closest_point_on_polyline(point, spec["polyline"])
    if zone_id in (DAMAGE_ZONE_TORSO, DAMAGE_ZONE_HEAD):
        seg_tan = axis_hat

    seam_hint = spec["seam_hint"]
    seam_perp = _vec_sub(seam_hint, _vec_scale(seg_tan, _vec_dot(seam_hint, seg_tan)))
    e_zero = _vec_normalize(seam_perp, (1.0, 0.0, 0.0))
    e_quarter = _vec_normalize(_vec_cross(seg_tan, e_zero), (0.0, 1.0, 0.0))

    radial_vec = _vec_sub(point, center_pt)
    radial_perp = _vec_sub(radial_vec, _vec_scale(seg_tan, _vec_dot(radial_vec, seg_tan)))
    if _vec_dot(radial_perp, radial_perp) < 1e-12:
        u_frac = 0.5
    else:
        ang = math.atan2(_vec_dot(radial_perp, e_quarter), _vec_dot(radial_perp, e_zero))
        u_frac = (ang / (2.0 * math.pi)) % 1.0

    u_val = 1.0 + u_frac
    v_blender = float(2 * zone_id + 1) + t_clamped
    return (u_val, v_blender)


def unwrap_polygon_seam_u(u_values: Sequence[float]) -> List[float]:
    """Unwrap cylindrical `u` coordinates across corners of one polygon to prevent seam wrap."""
    if not u_values:
        return []
    anchor_u = float(u_values[0])
    if anchor_u == 0.0:
        return [0.0 for _ in u_values]
    unwrapped: List[float] = []
    for raw_u in u_values:
        cur_u = float(raw_u)
        while cur_u - anchor_u > 0.5:
            cur_u -= 1.0
        while cur_u - anchor_u < -0.5:
            cur_u += 1.0
        if cur_u <= 0.05:
            # Never cross u == 0.0 because `ped.fxc` treats `TexCoord1.x == 0` as no-decal.
            cur_u += 1.0
        unwrapped.append(cur_u)
    return unwrapped


def compute_mesh_damage_uvs(
    vertex_positions: Sequence[Sequence[float]],
    polygon_vert_indices: Sequence[Sequence[int]],
    vertex_bone_weights: Optional[Sequence[Mapping[str, float]]] = None,
    bone_positions: Optional[Mapping[str, Sequence[float]]] = None,
) -> Dict[str, Any]:
    """
    Compute per-face-corner `UVMap 1` coordinates and zone counts for a ped mesh.
    Operates cleanly on raw sequences in pure Python without requiring `bpy`.
    """
    cylinders = build_damage_cylinders(bone_positions)
    neck_z = float(cylinders.get("neck_z", 0.5316))

    vert_zone_scores: List[Dict[int, float]] = []
    for vert_idx, pos in enumerate(vertex_positions):
        scores: Dict[int, float] = {}
        weights_map = (
            vertex_bone_weights[vert_idx]
            if (vertex_bone_weights is not None and vert_idx < len(vertex_bone_weights))
            else None
        )
        if weights_map:
            for bone_name, weight_val in weights_map.items():
                if weight_val <= 1e-6:
                    continue
                zone_id = classify_bone_name_to_damage_zone(
                    bone_name, float(pos[0]), float(pos[2]), neck_z
                )
                scores[zone_id] = scores.get(zone_id, 0.0) + float(weight_val)
        if not scores:
            fallback_zone = classify_spatial_damage_zone(
                float(pos[0]), float(pos[1]), float(pos[2]), cylinders
            )
            scores[fallback_zone] = 1.0
        vert_zone_scores.append(scores)

    loop_uvs: List[Tuple[float, float]] = []
    zone_poly_counts: Dict[str, int] = {name: 0 for name in DAMAGE_ZONE_NAMES.values()}

    for poly_verts in polygon_vert_indices:
        poly_scores: Dict[int, float] = {}
        for v_idx in poly_verts:
            for zone_id, weight_val in vert_zone_scores[v_idx].items():
                poly_scores[zone_id] = poly_scores.get(zone_id, 0.0) + weight_val

        # Pick strongest anatomical zone; fall back to unmapped only if no mapped zone has weight.
        mapped_candidates = [
            (zone_id, score)
            for zone_id, score in poly_scores.items()
            if zone_id != DAMAGE_ZONE_NONE
        ]
        none_score = poly_scores.get(DAMAGE_ZONE_NONE, 0.0)
        if mapped_candidates:
            best_mapped_zone, best_mapped_score = max(
                mapped_candidates, key=lambda item: (item[1], -item[0])
            )
            chosen_zone = (
                DAMAGE_ZONE_NONE if none_score > best_mapped_score * 1.25 else best_mapped_zone
            )
        else:
            chosen_zone = DAMAGE_ZONE_NONE

        zone_label = DAMAGE_ZONE_NAMES.get(chosen_zone, "unmapped")
        zone_poly_counts[zone_label] = zone_poly_counts.get(zone_label, 0) + 1

        if chosen_zone == DAMAGE_ZONE_NONE:
            for _ in poly_verts:
                loop_uvs.append((0.0, 0.0))
            continue

        raw_u_list: List[float] = []
        raw_v_list: List[float] = []
        for v_idx in poly_verts:
            proj_u, proj_v = project_point_onto_damage_zone(
                vertex_positions[v_idx], chosen_zone, cylinders
            )
            raw_u_list.append(proj_u)
            raw_v_list.append(proj_v)
        clean_u_list = unwrap_polygon_seam_u(raw_u_list)
        for u_val, v_val in zip(clean_u_list, raw_v_list):
            loop_uvs.append((u_val, v_val))

    return {
        "loop_uvs": loop_uvs,
        "zone_poly_counts": zone_poly_counts,
        "total_polygons": len(polygon_vert_indices),
    }


def _srgb_to_linear_channel(srgb_val: float) -> float:
    clamped = _clamp(float(srgb_val), 0.0, 1.0)
    if clamped <= 0.04045:
        return clamped / 12.92
    return ((clamped + 0.055) / 1.055) ** 2.4


def _set_color_attribute_srgb(
    color_attr: Any, srgb_rgba: Tuple[float, float, float, float]
) -> None:
    """Populate a Blender BYTE_COLOR attribute efficiently with exact sRGB RGBA values."""
    count = len(color_attr.data)
    if count == 0:
        return
    try:
        import numpy as numpy_mod

        arr = numpy_mod.empty((count, 4), dtype=numpy_mod.float32)
        arr[:, 0] = float(srgb_rgba[0])
        arr[:, 1] = float(srgb_rgba[1])
        arr[:, 2] = float(srgb_rgba[2])
        arr[:, 3] = float(srgb_rgba[3])
        color_attr.data.foreach_set("color_srgb", arr.ravel())
        return
    except Exception:
        pass

    lin_rgba = (
        _srgb_to_linear_channel(srgb_rgba[0]),
        _srgb_to_linear_channel(srgb_rgba[1]),
        _srgb_to_linear_channel(srgb_rgba[2]),
        float(srgb_rgba[3]),
    )
    for item in color_attr.data:
        item.color = lin_rgba


def apply_ped_damage_attributes_in_blender(
    bpy_module: Any,
    mesh_obj: Any,
    armature_obj: Any = None,
    *,
    enable_blood_decals: bool = True,
    primary_uv_name: str = "UVMap 0",
    damage_uv_name: str = "UVMap 1",
    color1_srgb: Tuple[float, float, float, float] = DEFAULT_PED_COLOR1_SRGB,
    color2_srgb: Tuple[float, float, float, float] = DEFAULT_PED_COLOR2_SRGB,
) -> Dict[str, Any]:
    """
    Generate `UVMap 1` ped blood/damage decal UVs and ped vertex colors (`Color 1`, `Color 2`)
    on a unified Blender ped mesh ready for Sollumz `ped.sps` export.
    """
    mesh_data = mesh_obj.data
    if mesh_data.uv_layers:
        mesh_data.uv_layers[0].name = primary_uv_name

    uv1_layer = mesh_data.uv_layers.get(damage_uv_name)
    if uv1_layer is None:
        uv1_layer = mesh_data.uv_layers.new(name=damage_uv_name)

    zone_counts: Dict[str, int] = {"unmapped": len(mesh_data.polygons)}
    num_loops = len(mesh_data.loops)

    if enable_blood_decals and num_loops > 0:
        group_names = {vgroup.index: vgroup.name for vgroup in mesh_obj.vertex_groups}
        vertex_positions = [
            (float(vert.co.x), float(vert.co.y), float(vert.co.z))
            for vert in mesh_data.vertices
        ]
        vertex_bone_weights: List[Dict[str, float]] = []
        for vert in mesh_data.vertices:
            weights: Dict[str, float] = {}
            for grp in vert.groups:
                bname = group_names.get(grp.group)
                if bname and grp.weight > 1e-6:
                    weights[bname] = float(grp.weight)
            vertex_bone_weights.append(weights)

        poly_vert_indices = [list(poly.vertices) for poly in mesh_data.polygons]
        bone_positions = extract_armature_bone_positions(armature_obj)
        computed = compute_mesh_damage_uvs(
            vertex_positions,
            poly_vert_indices,
            vertex_bone_weights=vertex_bone_weights,
            bone_positions=bone_positions,
        )
        zone_counts = computed["zone_poly_counts"]
        loop_uv_pairs = computed["loop_uvs"]

        # Map computed polygon-order loops back onto Blender polygon.loop_indices order
        flat_uv1 = [0.0] * (num_loops * 2)
        pair_cursor = 0
        for poly in mesh_data.polygons:
            for loop_idx in poly.loop_indices:
                if pair_cursor < len(loop_uv_pairs):
                    u_val, v_val = loop_uv_pairs[pair_cursor]
                    flat_uv1[loop_idx * 2] = u_val
                    flat_uv1[loop_idx * 2 + 1] = v_val
                pair_cursor += 1
        uv1_layer.uv.foreach_set("vector", flat_uv1)
    elif num_loops > 0:
        uv1_layer.uv.foreach_set("vector", [0.0] * (num_loops * 2))

    # Keep UVMap 0 active at slot 0 for Sollumz tangent calculation & DiffuseSampler.
    if mesh_data.uv_layers:
        mesh_data.uv_layers.active_index = 0

    bpy_module.context.view_layer.objects.active = mesh_obj
    try:
        bpy_module.ops.sollumz.color_attrs_add_missing()
    except Exception:
        pass
    try:
        bpy_module.ops.sollumz.uv_maps_add_missing()
    except Exception:
        pass

    color_attr_1 = mesh_data.color_attributes.get("Color 1")
    if color_attr_1 is None:
        color_attr_1 = mesh_data.attributes.new(
            name="Color 1", type="BYTE_COLOR", domain="CORNER"
        )
    _set_color_attribute_srgb(color_attr_1, color1_srgb)

    color_attr_2 = mesh_data.color_attributes.get("Color 2")
    if color_attr_2 is None:
        color_attr_2 = mesh_data.attributes.new(
            name="Color 2", type="BYTE_COLOR", domain="CORNER"
        )
    _set_color_attribute_srgb(color_attr_2, color2_srgb)

    mesh_data.update()
    return {
        "enabled": bool(enable_blood_decals),
        "shader": resolve_ped_shader_filename(enable_blood_decals),
        "damage_uv_name": damage_uv_name,
        "zone_poly_counts": zone_counts,
        "total_loops": num_loops,
    }


def enforce_ped_rpf7_poly_budget(
    bpy_module: Any,
    mesh_objects: Sequence[Any],
    *,
    max_total_polys: int = 255000,
    decimate_ratio: float = 0.40,
    fallback_ratio: float = 0.65,
    min_polys_to_decimate: int = 12000,
    accessory_keywords: Tuple[str, ...] = (
        "chain",
        "bag",
        "watch",
        "pouch",
        "keychain",
        "badge",
        "buckle",
        "jewelry",
    ),
) -> Dict[str, Any]:
    """
    Keep total unified ped triangle count comfortably below GTA V RPF7's 24-bit
    16,777,215-byte compressed `.ydd` resource limit when `ped.sps` adds `TexCoord1`
    and `Tangent` vertex attributes, trimming only heavy high-poly accessories first.
    """
    valid_meshes = [
        obj
        for obj in mesh_objects
        if obj is not None
        and getattr(obj, "type", None) == "MESH"
        and getattr(obj, "data", None) is not None
    ]
    before_total = sum(len(obj.data.polygons) for obj in valid_meshes)
    if before_total <= int(max_total_polys):
        return {
            "trimmed": [],
            "before_polys": before_total,
            "after_polys": before_total,
        }

    def _is_protected_face_or_body(obj_item: Any) -> bool:
        low_name = str(getattr(obj_item, "name", "")).strip().lower()
        return (
            low_name in ("body", "proc_body")
            or low_name.startswith("body_baked")
            or "body_base" in low_name
        )

    def _decimate_single_object(obj_item: Any, ratio_val: float) -> Tuple[int, int]:
        orig_tris = len(obj_item.data.polygons)
        if orig_tris <= 0 or getattr(obj_item.data, "shape_keys", None):
            return (orig_tris, orig_tris)
        bpy_module.context.view_layer.objects.active = obj_item
        decimate_mod = obj_item.modifiers.new("Rpf7PolyBudgetDecimate", "DECIMATE")
        decimate_mod.decimate_type = "COLLAPSE"
        decimate_mod.ratio = float(ratio_val)
        bpy_module.ops.object.modifier_apply(modifier=decimate_mod.name)
        if any(len(poly.vertices) != 3 for poly in obj_item.data.polygons):
            import bmesh

            bmesh_tmp = bmesh.new()
            bmesh_tmp.from_mesh(obj_item.data)
            bmesh.ops.triangulate(bmesh_tmp, faces=bmesh_tmp.faces)
            bmesh_tmp.to_mesh(obj_item.data)
            bmesh_tmp.free()
        obj_item.data.update()
        return (orig_tris, len(obj_item.data.polygons))

    trimmed_records: List[Tuple[str, int, int]] = []
    running_total = before_total

    accessory_candidates = sorted(
        [
            obj_item
            for obj_item in valid_meshes
            if not _is_protected_face_or_body(obj_item)
            and len(obj_item.data.polygons) >= int(min_polys_to_decimate)
            and any(keyword in obj_item.name.lower() for keyword in accessory_keywords)
        ],
        key=lambda obj_item: len(obj_item.data.polygons),
        reverse=True,
    )
    for candidate in accessory_candidates:
        if running_total <= int(max_total_polys):
            break
        old_cnt, new_cnt = _decimate_single_object(candidate, decimate_ratio)
        if new_cnt < old_cnt:
            running_total -= old_cnt - new_cnt
            trimmed_records.append((candidate.name, old_cnt, new_cnt))
            print(
                f"[RPF7 Budget] Decimated heavy accessory '{candidate.name}': "
                f"{old_cnt} -> {new_cnt} polys (total={running_total}/{max_total_polys})",
                flush=True,
            )

    if running_total > int(max_total_polys):
        fallback_candidates = sorted(
            [
                obj_item
                for obj_item in valid_meshes
                if not _is_protected_face_or_body(obj_item)
                and len(obj_item.data.polygons) >= 20000
                and all(rec[0] != obj_item.name for rec in trimmed_records)
            ],
            key=lambda obj_item: len(obj_item.data.polygons),
            reverse=True,
        )
        for candidate in fallback_candidates:
            if running_total <= int(max_total_polys):
                break
            old_cnt, new_cnt = _decimate_single_object(candidate, fallback_ratio)
            if new_cnt < old_cnt:
                running_total -= old_cnt - new_cnt
                trimmed_records.append((candidate.name, old_cnt, new_cnt))
                print(
                    f"[RPF7 Budget] Decimated heavy mesh '{candidate.name}': "
                    f"{old_cnt} -> {new_cnt} polys (total={running_total}/{max_total_polys})",
                    flush=True,
                )

    return {
        "trimmed": trimmed_records,
        "before_polys": before_total,
        "after_polys": running_total,
    }


def format_ped_damage_summary(
    damage_result: Mapping[str, Any],
    translate_func: Optional[Callable[..., str]] = None,
) -> str:
    """Format a concise summary of configured GTA V ped blood-decal shader and UV zones."""
    zone_counts = damage_result.get("zone_poly_counts") or {}
    torso_cnt = int(zone_counts.get("torso", 0))
    head_cnt = int(zone_counts.get("head", 0))
    arms_cnt = int(zone_counts.get("left_arm", 0)) + int(zone_counts.get("right_arm", 0))
    legs_cnt = int(zone_counts.get("left_leg", 0)) + int(zone_counts.get("right_leg", 0))
    unmapped_cnt = int(zone_counts.get("unmapped", 0))
    shader_name = str(damage_result.get("shader", PED_DAMAGE_SHADER_NAME))
    if translate_func is not None:
        return translate_func(
            "ped_damage.applied",
            shader=shader_name,
            torso=torso_cnt,
            head=head_cnt,
            arms=arms_cnt,
            legs=legs_cnt,
            unmapped=unmapped_cnt,
        )
    return (
        f"[OK] Ped blood decals configured: shader={shader_name}, "
        f"torso={torso_cnt}, head={head_cnt}, arms={arms_cnt}, "
        f"legs={legs_cnt}, unmapped={unmapped_cnt}"
    )
