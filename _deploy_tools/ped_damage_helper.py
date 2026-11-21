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
import os
import shutil
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union


PED_DAMAGE_SHADER_NAME = "ped.sps"
PED_NO_DAMAGE_SHADER_NAME = "ped_default.sps"
# Matches `ped_default.fxc` (`mov o2.xyzw, l(0, 0, 0.98, 1.0)`) so `ped.sps` does
# not introduce mirror-like grazing specular or dark metallic tints on anime meshes.
DEFAULT_ANIME_SPECULAR_FRESNEL = 0.98

# GTA V RPF7 TOC stores a 24-bit entry size (`f_size` max = 16,777,215 bytes = 0xFFFFFF)
# and a 23-bit 512-byte sector offset (`< 0x7FFFFF * 512` ~= 4.00 GiB).
RPF7_MAX_RESOURCE_BYTES = 0xFFFFFF
RPF7_SAFE_RESOURCE_TARGET_BYTES = 15_728_640
RPF7_MAX_ARCHIVE_OFFSET_BYTES = 0x7FFFFE * 512
RPF7_ARCHIVE_WARNING_BYTES = 4_100_000_000
RSC7_RESOURCE_EXTENSIONS = frozenset(
    {
        ".ydd",
        ".ytd",
        ".yft",
        ".yld",
        ".ymt",
        ".ydr",
        ".ybn",
        ".ycd",
        ".ynv",
        ".ypt",
        ".ymap",
        ".ytyp",
        ".ymf",
    }
)

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
    specular_fresnel: float = DEFAULT_ANIME_SPECULAR_FRESNEL,
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
    specular_fresnel: float = DEFAULT_ANIME_SPECULAR_FRESNEL,
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
    enable_blood_decals: bool = True,
    max_total_polys: Optional[int] = None,
    decimate_ratio: float = 0.40,
    hair_cloth_ratio: float = 0.62,
    fallback_ratio: float = 0.72,
    min_polys_to_decimate: int = 10000,
    accessory_keywords: Tuple[str, ...] = (
        "chain",
        "bag",
        "watch",
        "pouch",
        "keychain",
        "badge",
        "buckle",
        "jewelry",
        "halo",
        "pin",
        "glasses",
        "ribbon",
    ),
    hair_cloth_keywords: Tuple[str, ...] = (
        "hair",
        "twin",
        "pony",
        "bang",
        "tail",
        "skirt",
        "dress",
        "apron",
        "coat",
        "cape",
        "sweater",
        "stocking",
        "corset",
        "shirt",
        "shoe",
        "boot",
    ),
) -> Dict[str, Any]:
    """
    Keep total unified ped triangle count safely below GTA V RPF7's 24-bit
    16,777,215-byte (`0xFFFFFF`) compressed `.ydd` resource limit for both `ped.sps`
    (72 B/vert) and `ped_default.sps` (48 B/vert), trimming heavy accessories first,
    then dense custom hair/outfit meshes iteratively while leaving `Body`/face intact.
    """
    effective_max_polys = (
        int(max_total_polys)
        if max_total_polys is not None
        else (250000 if enable_blood_decals else 380000)
    )
    valid_meshes = [
        obj
        for obj in mesh_objects
        if obj is not None
        and getattr(obj, "type", None) == "MESH"
        and getattr(obj, "data", None) is not None
    ]
    before_total = sum(len(obj.data.polygons) for obj in valid_meshes)
    if before_total <= effective_max_polys:
        return {
            "trimmed": [],
            "before_polys": before_total,
            "after_polys": before_total,
            "max_total_polys": effective_max_polys,
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
    trimmed_names: set[str] = set()
    running_total = before_total

    def _run_pass(
        candidates: Sequence[Any], ratio_val: float, label: str
    ) -> None:
        nonlocal running_total
        for candidate in candidates:
            if running_total <= effective_max_polys:
                break
            old_cnt, new_cnt = _decimate_single_object(candidate, ratio_val)
            if new_cnt < old_cnt:
                running_total -= old_cnt - new_cnt
                trimmed_records.append((candidate.name, old_cnt, new_cnt))
                trimmed_names.add(candidate.name)
                print(
                    f"[RPF7 Budget] Decimated {label} '{candidate.name}': "
                    f"{old_cnt} -> {new_cnt} polys (total={running_total}/{effective_max_polys})",
                    flush=True,
                )

    pass1_candidates = sorted(
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
    _run_pass(pass1_candidates, decimate_ratio, "heavy accessory")

    if running_total > effective_max_polys:
        pass2_candidates = sorted(
            [
                obj_item
                for obj_item in valid_meshes
                if not _is_protected_face_or_body(obj_item)
                and obj_item.name not in trimmed_names
                and len(obj_item.data.polygons) >= 15000
                and any(keyword in obj_item.name.lower() for keyword in hair_cloth_keywords)
            ],
            key=lambda obj_item: len(obj_item.data.polygons),
            reverse=True,
        )
        _run_pass(pass2_candidates, hair_cloth_ratio, "dense hair/outfit")

    for _round_idx in range(4):
        if running_total <= effective_max_polys:
            break
        pass3_candidates = sorted(
            [
                obj_item
                for obj_item in valid_meshes
                if not _is_protected_face_or_body(obj_item)
                and not getattr(obj_item.data, "shape_keys", None)
                and len(obj_item.data.polygons) >= 6000
            ],
            key=lambda obj_item: len(obj_item.data.polygons),
            reverse=True,
        )
        if not pass3_candidates:
            break
        prev_total = running_total
        _run_pass(pass3_candidates, fallback_ratio, "heavy mesh")
        if running_total >= prev_total:
            break

    return {
        "trimmed": trimmed_records,
        "before_polys": before_total,
        "after_polys": running_total,
        "max_total_polys": effective_max_polys,
    }


def decode_rsc7_page_layout(flags_value: int) -> Dict[str, Any]:
    """
    Decode GTA V RSC7 `system_flags` or `graphics_flags` into exact ordered
    virtual/physical page ranges `[page_start, page_end)`.
    """
    bucket_specs = (
        ("ss4", 4, 1, 256),
        ("ss3", 5, 2, 128),
        ("ss2", 7, 4, 64),
        ("ss1", 11, 6, 32),
        ("s0", 17, 7, 16),
        ("s1", 24, 1, 8),
        ("s2", 25, 1, 4),
        ("s3", 26, 1, 2),
        ("s4", 27, 1, 1),
    )
    base_shift = int(flags_value) & 0xF
    base_unit = 0x200 << base_shift
    top_nibble = (int(flags_value) >> 28) & 0xF
    pages_list: List[Dict[str, Any]] = []
    bucket_counts: List[int] = []
    bucket_sizes: List[int] = []
    cursor_offset = 0

    for bucket_idx, (bucket_name, bit_shift, bit_width, unit_mul) in enumerate(bucket_specs):
        bucket_mask = (1 << bit_width) - 1
        bucket_count = (int(flags_value) >> bit_shift) & bucket_mask
        page_bytes = base_unit * unit_mul
        bucket_counts.append(bucket_count)
        bucket_sizes.append(page_bytes)
        for _copy_idx in range(bucket_count):
            pages_list.append(
                {
                    "start": cursor_offset,
                    "end": cursor_offset + page_bytes,
                    "size": page_bytes,
                    "bucket_name": bucket_name,
                    "bucket_index": bucket_idx,
                }
            )
            cursor_offset += page_bytes

    return {
        "top_nibble": top_nibble,
        "base_shift": base_shift,
        "base_unit": base_unit,
        "bucket_specs": bucket_specs,
        "bucket_counts": bucket_counts,
        "bucket_sizes": bucket_sizes,
        "pages": pages_list,
        "total_bytes": cursor_offset,
    }


def encode_rsc7_page_flags(
    top_nibble: int,
    base_shift: int,
    bucket_counts: Sequence[int],
) -> int:
    """Re-encode RSC7 page bucket counts into a 32-bit `system_flags` or `graphics_flags` word."""
    bucket_specs = (
        ("ss4", 4, 1, 256),
        ("ss3", 5, 2, 128),
        ("ss2", 7, 4, 64),
        ("ss1", 11, 6, 32),
        ("s0", 17, 7, 16),
        ("s1", 24, 1, 8),
        ("s2", 25, 1, 4),
        ("s3", 26, 1, 2),
        ("s4", 27, 1, 1),
    )
    if len(bucket_counts) != len(bucket_specs):
        raise ValueError(
            f"Expected {len(bucket_specs)} RSC7 page buckets, got {len(bucket_counts)}"
        )
    packed_flags = ((int(top_nibble) & 0xF) << 28) | (int(base_shift) & 0xF)
    for count_val, (bucket_name, bit_shift, bit_width, _unit_mul) in zip(
        bucket_counts, bucket_specs
    ):
        bucket_mask = (1 << bit_width) - 1
        if int(count_val) < 0 or int(count_val) > bucket_mask:
            raise ValueError(
                f"RSC7 bucket '{bucket_name}' count {count_val} exceeds max {bucket_mask}"
            )
        packed_flags |= (int(count_val) & bucket_mask) << bit_shift
    return packed_flags


def validate_yft_rsc7_page_bounds(
    yft_file_path: Union[str, Path],
) -> Dict[str, Any]:
    """
    Validate `.yft` RSC7 virtual page sizes, `crSkeletonData` array containment,
    and `fragType::m_SharedMatrixSet` (`+0xA8`) capacity against `fragType + 0x130`
    so runtime resource placement never overflows adjacent heap allocations.
    """
    target_path = Path(yft_file_path)
    raw_container = target_path.read_bytes()
    if len(raw_container) < 16:
        raise ValueError(f"Invalid .yft resource (<16 bytes): {target_path}")
    magic_bytes, rsc_version, sys_flags, gfx_flags = struct.unpack(
        "<4sIII", raw_container[:16]
    )
    if magic_bytes != b"RSC7":
        raise ValueError(f"Invalid RSC7 magic in '{target_path.name}': {magic_bytes!r}")

    raw_bytes = zlib.decompress(raw_container[16:], -15)
    sys_layout = decode_rsc7_page_layout(sys_flags)
    gfx_layout = decode_rsc7_page_layout(gfx_flags)
    expected_raw_bytes = int(sys_layout["total_bytes"]) + int(gfx_layout["total_bytes"])
    if len(raw_bytes) != expected_raw_bytes:
        raise ValueError(
            f"RSC7 page size mismatch in '{target_path.name}': flags describe "
            f"{expected_raw_bytes} bytes, decompressed payload has {len(raw_bytes)} bytes"
        )

    sys_pages = sys_layout["pages"]

    def _find_containing_page(offset_val: int, label_text: str) -> Dict[str, Any]:
        for page_item in sys_pages:
            if page_item["start"] <= offset_val < page_item["end"]:
                return page_item
        raise ValueError(
            f"Offset 0x{offset_val:x} for {label_text} in '{target_path.name}' "
            f"does not fall inside any RSC7 virtual page"
        )

    if len(raw_bytes) >= 0x140:
        common_drawable_ptr = struct.unpack_from("<Q", raw_bytes, 0x30)[0]
        if (common_drawable_ptr >> 28) & 0xF == 5:
            common_drawable_off = common_drawable_ptr & 0x0FFFFFFF
            skel_data_ptr = struct.unpack_from("<Q", raw_bytes, common_drawable_off + 0x18)[0]
            if (skel_data_ptr >> 28) & 0xF == 5:
                skel_data_off = skel_data_ptr & 0x0FFFFFFF
                skel_bone_count = struct.unpack_from("<H", raw_bytes, skel_data_off + 0x5E)[0]
                bones_ptr = struct.unpack_from("<Q", raw_bytes, skel_data_off + 0x20)[0]
                inv_ptr = struct.unpack_from("<Q", raw_bytes, skel_data_off + 0x28)[0]
                def_ptr = struct.unpack_from("<Q", raw_bytes, skel_data_off + 0x30)[0]
                parent_idx_ptr = struct.unpack_from("<Q", raw_bytes, skel_data_off + 0x38)[0]
                skeleton_arrays = (
                    ("m_Bones", bones_ptr, skel_bone_count * 0x50),
                    ("m_DefaultTransformsInverted", inv_ptr, skel_bone_count * 0x40),
                    ("m_DefaultTransforms", def_ptr, skel_bone_count * 0x40),
                    ("m_ParentIndices", parent_idx_ptr, skel_bone_count * 2),
                )
                for array_label, array_ptr, array_bytes in skeleton_arrays:
                    if not array_ptr or array_bytes == 0:
                        continue
                    array_start = array_ptr & 0x0FFFFFFF
                    array_end = array_start + array_bytes
                    containing_page = _find_containing_page(array_start, array_label)
                    if array_end > containing_page["end"]:
                        raise ValueError(
                            f"RSC7 virtual page overflow in '{target_path.name}': "
                            f"{array_label} (0x{array_start:x}..0x{array_end:x}) exceeds "
                            f"page end 0x{containing_page['end']:x}"
                        )

    frag_bone_count = struct.unpack_from("<Q", raw_bytes, 0x130)[0] if len(raw_bytes) >= 0x138 else 0
    shared_matrix_ptr = struct.unpack_from("<Q", raw_bytes, 0xA8)[0] if len(raw_bytes) >= 0xB0 else 0
    matrix_set_off = 0
    required_matrix_end = 0
    if shared_matrix_ptr != 0:
        matrix_set_off = shared_matrix_ptr & 0x0FFFFFFF
        required_matrix_end = matrix_set_off + 0x20 + frag_bone_count * 0x30
        containing_page = _find_containing_page(matrix_set_off, "fragType::m_SharedMatrixSet")
        if required_matrix_end > containing_page["end"]:
            raise ValueError(
                f"RSC7 grmMatrixSet heap overflow in '{target_path.name}': "
                f"fragType+0xA8=0x{matrix_set_off:x} with {frag_bone_count} bones writes to "
                f"0x{required_matrix_end:x} > virtual page end 0x{containing_page['end']:x} "
                f"(+{required_matrix_end - containing_page['end']} bytes)"
            )

    return {
        "ok": True,
        "version": rsc_version,
        "system_flags": sys_flags,
        "graphics_flags": gfx_flags,
        "raw_bytes_len": len(raw_bytes),
        "frag_bone_count": frag_bone_count,
        "shared_matrix_offset": matrix_set_off,
        "required_matrix_end": required_matrix_end,
    }


def validate_rpf7_resource_file(
    file_path: Union[str, Path],
    max_bytes: int = RPF7_MAX_RESOURCE_BYTES,
) -> int:
    """
    Verify an RSC7 resource file (`.ydd`, `.ytd`, `.yft`, etc.) does not exceed
    RPF7's 24-bit entry limit (`16,777,215` bytes / `0xFFFFFF`), and validate
    `.yft` RSC7 virtual page bounds (`crSkeletonData` & `m_SharedMatrixSet`).
    """
    target_path = Path(file_path)
    if not target_path.is_file():
        raise FileNotFoundError(f"RPF7 resource file not found: {target_path}")
    file_bytes = target_path.stat().st_size
    if file_bytes > int(max_bytes):
        raise ValueError(
            f"RPF7 16 MiB limit exceeded: '{target_path.name}' is {file_bytes:,} bytes "
            f"({file_bytes / (1024.0 * 1024.0):.2f} MiB) > {int(max_bytes):,} bytes (0xFFFFFF); "
            "packing this file would silently truncate TOC f_size and crash RAGE/GTA V."
        )
    if target_path.suffix.lower() == ".yft" and file_bytes >= 16:
        with open(target_path, "rb") as magic_handle:
            if magic_handle.read(4) == b"RSC7":
                validate_yft_rsc7_page_bounds(target_path)
    return file_bytes


def inspect_rpf7_archive_limits(rpf_file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Inspect a binary RPF7 archive TOC for all size/offset/compression limits:
      - `magic == 0x52504637` (`7FPR`) and `encryption == b'OPEN'`
      - Zero resource entries clamped at 24-bit overflow `f_size == 0xFFFFFF`
      - Zero non-resource binary entries with non-zero compressed size (`ERR_GEN_ZLIB_2`)
      - Zero 23-bit 512-byte sector offsets exceeding ~4.00 GiB (`0x7FFFFE * 512`)
    """
    archive_path = Path(rpf_file_path)
    total_bytes = archive_path.stat().st_size
    with open(archive_path, "rb") as rpf_handle:
        header_data = rpf_handle.read(16)
        if len(header_data) < 16:
            raise ValueError(f"Invalid RPF7 header (<16 bytes): {archive_path}")
        magic_num, entry_count, names_len, enc_raw = struct.unpack("<IIII", header_data)
        enc_bytes = struct.pack("<I", enc_raw)
        magic_ok = magic_num == 0x52504637
        toc_bytes = rpf_handle.read(entry_count * 16)
        names_bytes = rpf_handle.read(names_len)

    resource_overflows: List[Tuple[str, int]] = []
    compressed_binaries: List[Tuple[str, int]] = []
    offset_overflows: List[Tuple[str, int]] = []
    largest_resource_name = ""
    largest_resource_bytes = 0
    max_offset_bytes = 0

    for entry_idx in range(entry_count):
        off_pos = entry_idx * 16
        d0_val, d1_val, _d2_val, _d3_val = struct.unpack(
            "<IIII", toc_bytes[off_pos : off_pos + 16]
        )
        name_off = d0_val & 0xFFFF
        f_size = (d0_val >> 16) | ((d1_val & 0xFF) << 16)
        is_dir = d1_val == 0x7FFFFF00
        is_resource = (d1_val & 0x80000000) != 0
        sector_offset = (d1_val >> 8) & 0x7FFFFF
        name_end = names_bytes.find(b"\x00", name_off)
        entry_name = names_bytes[
            name_off : (len(names_bytes) if name_end < 0 else name_end)
        ].decode("ascii", "replace")

        if is_dir:
            continue

        byte_offset = sector_offset * 512
        max_offset_bytes = max(max_offset_bytes, byte_offset)
        if byte_offset >= RPF7_MAX_ARCHIVE_OFFSET_BYTES or sector_offset >= 0x7FFFFF:
            offset_overflows.append((entry_name, byte_offset))

        if is_resource:
            if f_size > largest_resource_bytes:
                largest_resource_bytes = f_size
                largest_resource_name = entry_name
            if f_size == RPF7_MAX_RESOURCE_BYTES:
                resource_overflows.append((entry_name, f_size))
        elif f_size != 0:
            compressed_binaries.append((entry_name, f_size))

    archive_size_ok = total_bytes <= RPF7_MAX_ARCHIVE_OFFSET_BYTES
    is_ok = (
        magic_ok
        and enc_bytes == b"OPEN"
        and archive_size_ok
        and not resource_overflows
        and not compressed_binaries
        and not offset_overflows
    )
    return {
        "ok": is_ok,
        "magic_ok": magic_ok,
        "encryption": enc_bytes,
        "entry_count": entry_count,
        "total_bytes": total_bytes,
        "archive_size_ok": archive_size_ok,
        "max_offset_bytes": max_offset_bytes,
        "largest_resource_name": largest_resource_name,
        "largest_resource_bytes": largest_resource_bytes,
        "resource_overflows": resource_overflows,
        "compressed_binaries": compressed_binaries,
        "offset_overflows": offset_overflows,
    }


def find_oversized_rpf7_resources(
    source_dir: Union[str, Path],
    max_bytes: int = RPF7_MAX_RESOURCE_BYTES,
) -> List[Tuple[Path, int]]:
    """Return RSC7 resource files inside `source_dir` exceeding `max_bytes` (`0xFFFFFF`)."""
    oversized: List[Tuple[Path, int]] = []
    root_dir = Path(source_dir)
    if not root_dir.is_dir():
        return oversized
    for walk_root, dir_names, file_names in os.walk(root_dir):
        dir_names[:] = dir_names
        for single_name in file_names:
            candidate_path = Path(walk_root) / single_name
            if candidate_path.suffix.lower() not in RSC7_RESOURCE_EXTENSIONS:
                continue
            try:
                file_bytes = candidate_path.stat().st_size
            except OSError:
                continue
            if file_bytes > int(max_bytes):
                oversized.append((candidate_path, file_bytes))
    oversized.sort(key=lambda pair: pair[1], reverse=True)
    return oversized


def assert_directory_rpf7_resources_valid(
    source_dir: Union[str, Path],
    max_bytes: int = RPF7_MAX_RESOURCE_BYTES,
    warn_archive_bytes: int = RPF7_ARCHIVE_WARNING_BYTES,
    max_archive_bytes: int = RPF7_MAX_ARCHIVE_OFFSET_BYTES,
) -> Dict[str, Any]:
    """
    Pre-flight check before `rage create` blocking any >16 MiB RSC7 resource or
    >4.00 GiB archive total, while warning when approaching the 4.00 GiB RPF7 ceiling.
    """
    root_dir = Path(source_dir)
    oversized = find_oversized_rpf7_resources(root_dir, max_bytes=max_bytes)
    if oversized:
        preview = ", ".join(
            f"{item_path.name} ({item_bytes / (1024.0 * 1024.0):.2f} MiB)"
            for item_path, item_bytes in oversized[:5]
        )
        raise ValueError(
            f"Refusing to pack RPF7 from '{root_dir}': {len(oversized)} RSC7 resource(s) exceed "
            f"{max_bytes:,} bytes (16 MiB u24 limit): {preview}"
        )

    total_bytes = 0
    for walk_root, dir_names, file_names in os.walk(root_dir):
        dir_names[:] = dir_names
        for single_name in file_names:
            try:
                total_bytes += (Path(walk_root) / single_name).stat().st_size
            except OSError:
                continue

    if total_bytes > int(max_archive_bytes):
        raise ValueError(
            f"Refusing to pack RPF7 from '{root_dir}': total content {total_bytes:,} bytes "
            f"({total_bytes / (1024.0 ** 3):.3f} GiB) exceeds RPF7 4.00 GiB 23-bit sector offset limit."
        )
    if total_bytes >= int(warn_archive_bytes):
        print(
            f"[RPF7 WARNING] Directory '{root_dir.name}' is {total_bytes / (1024.0 ** 3):.3f} GiB "
            f"(nearing RPF7 4.00 GiB sector offset limit).",
            flush=True,
        )
    return {"total_bytes": total_bytes, "oversized_count": 0}


def enforce_ytd_rpf7_size_budget(
    rage_cli: Union[str, Path],
    ytd_path: Union[str, Path],
    source_image_paths: Sequence[Union[str, Path]],
    max_bytes: int = RPF7_MAX_RESOURCE_BYTES,
    target_bytes: int = RPF7_SAFE_RESOURCE_TARGET_BYTES,
) -> int:
    """
    Verify a compiled `.ytd` fits under RPF7's `16,777,215`-byte limit; if an
    oversized 4K/uncompressed atlas pushed it over 16 MiB, automatically downscale
    temporary copies by 50% and rebuild via `rage textures build` until safe.
    """
    target_ytd = Path(ytd_path)
    cur_bytes = target_ytd.stat().st_size
    if cur_bytes <= int(max_bytes):
        return cur_bytes

    from PIL import Image

    resampling_enum = getattr(Image, "Resampling", Image)
    lanczos_filter = getattr(resampling_enum, "LANCZOS", Image.LANCZOS)
    valid_sources = [Path(img_p) for img_p in source_image_paths if Path(img_p).is_file()]
    if not valid_sources:
        return validate_rpf7_resource_file(target_ytd, max_bytes=max_bytes)

    with tempfile.TemporaryDirectory(prefix="vrc2gtav_ytd_budget_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        cur_inputs: List[Path] = []
        for img_src in valid_sources:
            dst_img = tmp_dir / img_src.name
            shutil.copy2(img_src, dst_img)
            cur_inputs.append(dst_img)

        for scale_step in range(1, 4):
            for img_path_item in cur_inputs:
                with Image.open(img_path_item) as pil_img:
                    new_w = max(256, pil_img.width // 2)
                    new_h = max(256, pil_img.height // 2)
                    resized_img = pil_img.resize((new_w, new_h), lanczos_filter)
                    resized_img.save(img_path_item, format="PNG")
            print(
                f"[RPF7 Budget] '{target_ytd.name}' was {cur_bytes / (1024.0 * 1024.0):.2f} MiB "
                f"(> 16 MiB limit); downscaling textures (step {scale_step})...",
                flush=True,
            )
            subprocess.run(
                [
                    str(rage_cli),
                    "textures",
                    "build",
                    "-o",
                    str(target_ytd),
                    *[str(item_p) for item_p in cur_inputs],
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=True,
            )
            cur_bytes = target_ytd.stat().st_size
            if cur_bytes <= int(target_bytes) or cur_bytes <= int(max_bytes):
                break

    return validate_rpf7_resource_file(target_ytd, max_bytes=max_bytes)


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
