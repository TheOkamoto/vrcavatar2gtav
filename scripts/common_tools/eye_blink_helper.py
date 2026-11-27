#!/usr/bin/env python3
"""
eye_blink_helper.py
===================
Optional natural eye-blink rigging and GTAVPhysBones.ini profile extraction for
converted VRChat avatars in GTA V.

Uses four dedicated custom eyelid bones parented directly under `SKEL_Head`
(tag `31086`) so vanilla GTA V `.ycd` facial animations and `crExpressions` never
overwrite blink motion, while still stripping unskinned `YFT_ONLY_HAND_BONES` from
the `.ydd` when needed to remain safely within RAGE's `<= 128` `.ydd` bone limit:
  - `PB_Blink_L`  (tag `44255`, parent `SKEL_Head` `31086`)
  - `PB_Blink_LO` (tag `28167`, parent `SKEL_Head` `31086`)
  - `PB_Blink_R`  (tag `44357`, parent `SKEL_Head` `31086`)
  - `PB_Blink_RO` (tag `29607`, parent `SKEL_Head` `31086`)

Automatic safety checks inspect active facial blendshapes and measured rest-to-shut
displacement so avatars with custom closed, winking, or smiling eye expressions
do not get glitched eyelids unless the user explicitly overrides with `--eye-blink`.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


VANILLA_EYELID_BLINK_BONES: Tuple[str, ...] = (
    "FACIAL_L_eyelidUpper",
    "FACIAL_L_eyelidUpperOuterSDK",
    "FACIAL_R_eyelidUpper",
    "FACIAL_R_eyelidUpperOuterSDK",
)

VANILLA_BLINK_ANCHOR_MAP: Dict[str, str] = {
    "PB_Blink_L": "FACIAL_L_eyelidUpper",
    "PB_Blink_LO": "FACIAL_L_eyelidUpperOuterSDK",
    "PB_Blink_R": "FACIAL_R_eyelidUpper",
    "PB_Blink_RO": "FACIAL_R_eyelidUpperOuterSDK",
}

EYELID_BLINK_BONE_SPECS: Tuple[Tuple[str, int, str, int], ...] = (
    ("PB_Blink_L", 44255, "SKEL_Head", 31086),
    ("PB_Blink_LO", 28167, "SKEL_Head", 31086),
    ("PB_Blink_R", 44357, "SKEL_Head", 31086),
    ("PB_Blink_RO", 29607, "SKEL_Head", 31086),
)

EYELID_BLINK_BONES: Tuple[str, ...] = tuple(spec[0] for spec in EYELID_BLINK_BONE_SPECS)
EYELID_BLINK_BONE_TAGS: Dict[str, int] = {spec[0]: spec[1] for spec in EYELID_BLINK_BONE_SPECS}

# Leaf weapon/IK helper bones retained in .yft skeletons; stripped from .ydd only
# when needed so base + PhysBones + 4 eyelid blink bones stay <= 128 in RAGE.
YFT_ONLY_HAND_BONES: Tuple[str, ...] = (
    "PH_L_Hand",
    "IK_L_Hand",
    "PH_R_Hand",
    "IK_R_Hand",
)

BLINK_SHAPE_KEY_CANDIDATES: Tuple[str, ...] = (
    "vrc.blink",
    "vrc.v_blink",
    "eye_close",
    "eyes_close",
    "close_eyes",
    "close_eye",
    "blink",
    "まばたき",
    "mabataki",
)

BLINK_SHAPE_KEY_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("vrc.blink_left", "vrc.blink_right"),
    ("vrc.v_blink_left", "vrc.v_blink_right"),
    ("eye_close_l", "eye_close_r"),
    ("eyes_close_l", "eyes_close_r"),
    ("close_eye_l", "close_eye_r"),
    ("blink_left", "blink_right"),
    ("blink_l", "blink_r"),
    ("まばたき_l", "まばたき_r"),
)

CLOSED_EYE_CONFLICT_EXACT: FrozenSet[str] = frozenset(
    {
        "vrc.blink",
        "vrc.v_blink",
        "blink",
        "blink_l",
        "blink_r",
        "eye_close",
        "eyes_close",
        "close_eye",
        "close_eyes",
        "eye_closed",
        "eyes_closed",
        "wink",
        "wink_l",
        "wink_r",
        "eye_happy",
        "eye_smile",
        "eye_><",
        "eye_^^",
        "まばたき",
        "ウィンク",
        "ｳｨﾝｸ",
        "笑い",
        "にっこり",
    }
)

CLOSED_EYE_CONFLICT_TOKENS: Tuple[str, ...] = (
    "blink",
    "wink",
    "eye_close",
    "eyes_close",
    "close_eye",
    "eye_happy",
    "happy_eye",
    "eye_smile",
    "smile_eye",
    "eye_><",
    "><",
    "nagomi",
    "まばたき",
    "ウィンク",
    "ｳｨﾝｸ",
    "笑い",
    "にっこり",
)


def parse_eye_blink_mode(raw_value: Any, default: str = "auto") -> str:
    """Normalize an eye_blink setting into 'auto', 'on', or 'off'."""
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return "on" if raw_value else "off"
    cleaned = str(raw_value).strip().lower()
    if cleaned in ("", "auto", "default"):
        return "auto"
    if cleaned in ("1", "true", "yes", "on", "enable", "enabled"):
        return "on"
    if cleaned in ("0", "false", "no", "off", "disable", "disabled"):
        return "off"
    return default


DEFAULT_BLINK_STRENGTH_BY_AVATAR: Dict[str, float] = {
    "player_one_franklin": 0.50,
    "player_zero_michael": 0.50,
    "player_two_trevor": 0.60,
}


def parse_eye_blink_strength(raw_value: Any, default: float = 1.0) -> float:
    """Normalize max blink strength into [0.0, 1.5], falling back cleanly on 'auto'/None."""
    if raw_value is None or isinstance(raw_value, bool):
        return float(default)
    cleaned = str(raw_value).strip().lower()
    if cleaned in ("", "auto", "default"):
        return float(default)
    try:
        parsed_val = float(cleaned)
    except ValueError:
        return float(default)
    if not math.isfinite(parsed_val):
        return float(default)
    return max(0.0, min(1.5, parsed_val))


def resolve_eye_blink_strength(
    cli_strength: Optional[float],
    char_cfg: Optional[Mapping[str, Any]] = None,
    *,
    avatar_id: str = "",
    default: float = 1.0,
) -> float:
    """
    Resolve effective peak blink factor (`max_blink`) from CLI override, config
    (`eye_blink_strength`), or built-in avatar preset (0.50 Shinano, 0.60 Miltina)
    without modifying any other facial blendshape weights.
    """
    if cli_strength is not None:
        return parse_eye_blink_strength(cli_strength, default=default)
    if char_cfg:
        raw_cfg_strength = char_cfg.get("eye_blink_strength")
        if raw_cfg_strength is not None and str(raw_cfg_strength).strip().lower() not in (
            "",
            "auto",
            "default",
        ):
            return parse_eye_blink_strength(raw_cfg_strength, default=default)

    candidates = [avatar_id]
    if char_cfg:
        candidates.extend(
            [
                str(char_cfg.get("avatar_id") or ""),
                str(char_cfg.get("avatar") or ""),
                str(char_cfg.get("unity_avatar_name") or ""),
            ]
        )
    for raw_cand in candidates:
        norm_cand = str(raw_cand or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not norm_cand:
            continue
        if norm_cand in DEFAULT_BLINK_STRENGTH_BY_AVATAR:
            return float(DEFAULT_BLINK_STRENGTH_BY_AVATAR[norm_cand])
        if "miltina" in norm_cand or "milltina" in norm_cand or "trevor" in norm_cand or "player_two" in norm_cand:
            return float(DEFAULT_BLINK_STRENGTH_BY_AVATAR["player_two_trevor"])
        if "shinano" in norm_cand or "franklin" in norm_cand or "michael" in norm_cand or "player_one" in norm_cand or "player_zero" in norm_cand:
            return float(DEFAULT_BLINK_STRENGTH_BY_AVATAR["player_one_franklin"])
    return float(default)


DEFAULT_MOUTH_OPEN_STRENGTH = 0.70
MOUTH_OPEN_SHAPE_KEYS = (
    "vrc.v_aa",
    "vrc.aa",
    "kuchi_a",
    "あ",
    "a",
    "aa",
    "jawopen",
    "mouthopen",
)


def parse_mouth_open_strength(
    raw_value: Any,
    default: float = DEFAULT_MOUTH_OPEN_STRENGTH,
) -> float:
    """Normalize mouth-opening max FACIAL_jaw weight into [0.0, 1.0]."""
    if raw_value is None or isinstance(raw_value, bool):
        return float(default)
    cleaned = str(raw_value).strip().lower()
    if cleaned in ("", "auto", "default"):
        return float(default)
    try:
        parsed_val = float(cleaned)
    except ValueError:
        return float(default)
    if not math.isfinite(parsed_val):
        return float(default)
    return max(0.0, min(1.0, parsed_val))


def resolve_mouth_open_strength(
    cli_strength: Optional[float],
    char_cfg: Optional[Mapping[str, Any]] = None,
    *,
    default: float = DEFAULT_MOUTH_OPEN_STRENGTH,
) -> float:
    """Resolve effective mouth opening factor (FACIAL_jaw weight ceiling) from CLI or config."""
    if cli_strength is not None:
        return parse_mouth_open_strength(cli_strength, default=default)
    if char_cfg:
        raw_cfg_strength = char_cfg.get("mouth_open_strength")
        if raw_cfg_strength is not None and str(raw_cfg_strength).strip().lower() not in (
            "",
            "auto",
            "default",
        ):
            return parse_mouth_open_strength(raw_cfg_strength, default=default)
    return float(default)


def extract_facial_jaw_weights(
    orig_body_obj: Any,
    mouth_open_strength: Optional[float] = DEFAULT_MOUTH_OPEN_STRENGTH,
    *,
    delta_z_threshold: float = -0.0004,
) -> Dict[int, float]:
    """
    Derive FACIAL_jaw vertex weights from `vrc.v_aa` (or vowel-A / JawOpen keys)
    scaled cleanly by `mouth_open_strength` in [0.0, 1.0].
    """
    strength = parse_mouth_open_strength(
        mouth_open_strength, default=DEFAULT_MOUTH_OPEN_STRENGTH
    )
    if strength <= 0.0:
        return {}
    if not orig_body_obj or not getattr(orig_body_obj.data, "shape_keys", None):
        return {}
    key_blocks = orig_body_obj.data.shape_keys.key_blocks
    key_blocks_lower = {key_block_item.name.strip().lower(): key_block_item for key_block_item in key_blocks}
    shape_anchor = next(
        (key_blocks_lower.get(cand_key) for cand_key in MOUTH_OPEN_SHAPE_KEYS if key_blocks_lower.get(cand_key)),
        None,
    )
    basis_key = key_blocks_lower.get("basis") or key_blocks[0]
    if not shape_anchor or not basis_key:
        return {}

    world_mat3 = None
    raw_world = getattr(orig_body_obj, "matrix_world", None)
    if raw_world is not None and hasattr(raw_world, "to_3x3"):
        world_mat3 = raw_world.to_3x3()

    drop_threshold = abs(float(delta_z_threshold))
    downward_drops: List[Tuple[int, float]] = []
    for vert_item in orig_body_obj.data.vertices:
        base_coord = basis_key.data[vert_item.index].co
        open_coord = shape_anchor.data[vert_item.index].co
        if world_mat3 is not None:
            delta_x = float(open_coord.x) - float(base_coord.x)
            delta_y = float(open_coord.y) - float(base_coord.y)
            delta_z = (
                float(world_mat3[2][0]) * delta_x
                + float(world_mat3[2][1]) * delta_y
                + float(world_mat3[2][2]) * (float(open_coord.z) - float(base_coord.z))
            )
        else:
            delta_z = float(open_coord.z) - float(base_coord.z)
        if delta_z < -drop_threshold:
            downward_drops.append((int(vert_item.index), abs(delta_z)))

    if not downward_drops:
        return {}
    peak_drop = max(drop_val for _, drop_val in downward_drops)
    norm_ref = min(0.0075, max(0.0025, peak_drop * 0.90))
    return {
        vert_idx: min(strength, max(0.0, (drop_val / norm_ref) * strength))
        for vert_idx, drop_val in downward_drops
    }


def resolve_effective_eye_blink_mode(
    cli_eye_blink: Optional[bool],
    char_cfg: Optional[Mapping[str, Any]] = None,
    default: str = "auto",
) -> str:
    """Resolve effective eye-blink mode from CLI override or character/avatar config."""
    if cli_eye_blink is True:
        return "on"
    if cli_eye_blink is False:
        return "off"
    cfg_raw = char_cfg.get("eye_blink") if char_cfg else None
    return parse_eye_blink_mode(cfg_raw, default=default)


def detect_custom_eye_expression_conflict(
    shape_weights: Optional[Mapping[str, float]],
    threshold: float = 0.25,
) -> Optional[str]:
    """
    Detect whether active resting blendshapes already close, wink, or squint the
    eyes (e.g., `vrc.Blink`, `eye_close`, `eye_><`, `wink`, `笑い`), making automatic
    blink animation unsafe. Returns a reason string if conflicted, else None.
    """
    if not shape_weights:
        return None
    for raw_name, raw_weight in shape_weights.items():
        try:
            weight_val = float(raw_weight)
        except (TypeError, ValueError):
            continue
        if weight_val < threshold:
            continue
        norm_name = str(raw_name).strip().lower()
        if not norm_name:
            continue
        if norm_name in CLOSED_EYE_CONFLICT_EXACT or any(
            token in norm_name for token in CLOSED_EYE_CONFLICT_TOKENS
        ):
            return f"{str(raw_name).strip()}={weight_val:.2f}"
    return None


def find_blink_shape_key_group(
    key_blocks: Sequence[Any],
    base_positions: Optional[Sequence[Tuple[float, float, float]]] = None,
    min_moved_verts: int = 10,
) -> List[Any]:
    """
    Find combined blink shape key or matching left/right blink pair in `key_blocks`,
    supporting Booth avatars with combined (`vrc.blink`) or split (`vrc.blink_left/right`) keys.
    """
    if not key_blocks:
        return []

    normalized_blocks: List[Tuple[str, Any]] = []
    block_by_norm: Dict[str, Any] = {}
    for key_item in key_blocks:
        key_name = getattr(key_item, "name", "")
        norm_name = str(key_name).strip().lower()
        if norm_name and norm_name != "basis":
            normalized_blocks.append((norm_name, key_item))
            block_by_norm.setdefault(norm_name, key_item)

    def _has_enough_motion(key_item: Any, min_req: int = min_moved_verts) -> bool:
        if not base_positions:
            return True
        key_data = getattr(key_item, "data", None)
        if not key_data or len(key_data) != len(base_positions):
            return False
        moved = 0
        for idx, base_pos in enumerate(base_positions):
            key_coord = key_data[idx].co
            diff_x = float(key_coord.x) - base_pos[0]
            diff_y = float(key_coord.y) - base_pos[1]
            diff_z = float(key_coord.z) - base_pos[2]
            if (diff_x * diff_x + diff_y * diff_y + diff_z * diff_z) >= 2.5e-7:
                moved += 1
                if moved >= min_req:
                    return True
        return False

    for candidate in BLINK_SHAPE_KEY_CANDIDATES:
        key_exact = block_by_norm.get(candidate)
        if key_exact is not None and _has_enough_motion(key_exact):
            return [key_exact]

    per_side_min = max(4, min_moved_verts // 2)
    for left_name, right_name in BLINK_SHAPE_KEY_PAIRS:
        left_key = block_by_norm.get(left_name)
        right_key = block_by_norm.get(right_name)
        if (
            left_key is not None
            and right_key is not None
            and _has_enough_motion(left_key, per_side_min)
            and _has_enough_motion(right_key, per_side_min)
        ):
            return [left_key, right_key]

    sided_tokens = ("_left", "_right", "_l", "_r", ".l", ".r")
    for candidate in BLINK_SHAPE_KEY_CANDIDATES:
        for norm_name, key_item in normalized_blocks:
            if candidate in norm_name and not any(tok in norm_name for tok in sided_tokens) and _has_enough_motion(key_item):
                return [key_item]

    for candidate in BLINK_SHAPE_KEY_CANDIDATES:
        for norm_name, key_item in normalized_blocks:
            if candidate in norm_name and _has_enough_motion(key_item):
                return [key_item]

    return []


def find_blink_shape_key(
    key_blocks: Sequence[Any],
    base_positions: Optional[Sequence[Tuple[float, float, float]]] = None,
    min_moved_verts: int = 10,
) -> Optional[Any]:
    """
    Find the primary upper-eyelid blink shape key in `key_blocks`, normalizing trailing
    spaces (e.g., Milltina's `'vrc.blink '`) and preferring canonical VRC blink keys.
    """
    group = find_blink_shape_key_group(
        key_blocks, base_positions=base_positions, min_moved_verts=min_moved_verts
    )
    return group[0] if group else None


def prepare_ydd_blink_bone_set(
    base_valid_bones: Iterable[str],
    *,
    enable_eye_blink: bool,
    custom_bone_count: int = 0,
    max_total_bones: int = 128,
) -> Tuple[Set[str], int]:
    """
    Ensure dedicated custom eyelid blink bones (`PB_Blink_*`) are included in the
    `.ydd` valid bone whitelist when eye blinking is enabled, replacing vanilla
    `FACIAL_*eyelidUpper*` slots and trimming unskinned `PH_*`/`IK_*` hand helper
    bones from the `.ydd` export if needed to stay within RAGE's 128-bone limit.
    """
    valid_bones: Set[str] = set(base_valid_bones)
    if not enable_eye_blink:
        return valid_bones, 0

    for vanilla_lid in VANILLA_EYELID_BLINK_BONES:
        valid_bones.discard(vanilla_lid)
    valid_bones.update(EYELID_BLINK_BONES)
    stripped_count = 0
    if len(valid_bones) + int(custom_bone_count) > int(max_total_bones):
        for hand_leaf in YFT_ONLY_HAND_BONES:
            if hand_leaf in valid_bones:
                valid_bones.remove(hand_leaf)
                stripped_count += 1
    return valid_bones, stripped_count


def capture_eyelid_blink_anchors(ped_armature: Any) -> Dict[str, Tuple[float, float, float]]:
    """
    Snapshot world-space rest positions for `PB_Blink_*` from the unpruned GTA V
    armature's native upper-eyelid bones (or SKEL_Head fallback offsets) before
    removing unused vanilla eyelid bones from `.ydd` export.
    """
    if ped_armature is None:
        return {}

    arm_world = ped_armature.matrix_world
    data_bones = ped_armature.data.bones
    head_bone = data_bones.get("SKEL_Head")
    head_world_pos = (
        (arm_world @ head_bone.matrix_local).translation
        if head_bone is not None
        else arm_world.translation
    )
    fallback_offsets: Dict[str, Tuple[float, float, float]] = {
        "PB_Blink_L": (0.033, -0.085, 0.035),
        "PB_Blink_LO": (0.045, -0.075, 0.035),
        "PB_Blink_R": (-0.033, -0.085, 0.035),
        "PB_Blink_RO": (-0.045, -0.075, 0.035),
    }

    anchors: Dict[str, Tuple[float, float, float]] = {}
    for blink_name, vanilla_name in VANILLA_BLINK_ANCHOR_MAP.items():
        vanilla_bone = data_bones.get(vanilla_name)
        if vanilla_bone is not None:
            world_point = (arm_world @ vanilla_bone.matrix_local).translation
            anchors[blink_name] = (float(world_point.x), float(world_point.y), float(world_point.z))
        else:
            off_xyz = fallback_offsets[blink_name]
            anchors[blink_name] = (
                float(head_world_pos.x) + off_xyz[0],
                float(head_world_pos.y) + off_xyz[1],
                float(head_world_pos.z) + off_xyz[2],
            )
    return anchors


def build_blink_custom_bone_specs(
    ped_armature: Any,
    *,
    blink_anchors: Optional[Mapping[str, Tuple[float, float, float]]] = None,
    blink_rig_data: Optional[Mapping[str, Any]] = None,
    world_scale: float = 1.0,
    world_z_offset: float = 0.0,
    world_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> List[Dict[str, object]]:
    """
    Build `custom_child_bones` descriptors for `PB_Blink_L/LO/R/RO` parented under
    `SKEL_Head`, compatible with `inject_custom_bones_into_blender_armature` and
    `patch_yft_skeleton`.

    When `blink_rig_data` includes `pivots_world`, each blink bone is placed at its
    fitted eyeball-pivot coordinate in GTA V world space so runtime blinking operates
    via pure bone rotation (`Quat`) without per-frame translation deltas.
    """
    if ped_armature is None:
        return []

    import mathutils

    pivots_world = (
        dict(blink_rig_data.get("pivots_world") or {})
        if blink_rig_data
        else {}
    )
    resolved_anchors = (
        dict(blink_anchors)
        if blink_anchors
        else capture_eyelid_blink_anchors(ped_armature)
    )
    off_x, off_y, off_z = (
        float(world_offset[0]),
        float(world_offset[1]),
        float(world_offset[2]),
    )
    specs: List[Dict[str, object]] = []
    for bone_name, bone_tag, parent_name, _ptag in EYELID_BLINK_BONE_SPECS:
        if bone_name in pivots_world:
            src_point = pivots_world[bone_name]
            anchor_xyz = (
                (float(src_point[0]) + off_x) * float(world_scale),
                (float(src_point[1]) + off_y) * float(world_scale),
                (float(src_point[2]) + off_z) * float(world_scale) + float(world_z_offset),
            )
        else:
            anchor_xyz = resolved_anchors.get(bone_name)
        if anchor_xyz is None:
            continue
        world_mat = mathutils.Matrix.Translation(mathutils.Vector(anchor_xyz))
        specs.append(
            {
                "name": bone_name,
                "parent_name": parent_name,
                "tag": int(bone_tag),
                "length": 0.02,
                "world_matrix": world_mat,
            }
        )
    return specs


def _vec_dot(vec_first: Tuple[float, float, float], vec_second: Tuple[float, float, float]) -> float:
    return vec_first[0] * vec_second[0] + vec_first[1] * vec_second[1] + vec_first[2] * vec_second[2]


def _vec_add(
    vec_first: Tuple[float, float, float], vec_second: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    return (vec_first[0] + vec_second[0], vec_first[1] + vec_second[1], vec_first[2] + vec_second[2])


def _vec_sub(
    vec_first: Tuple[float, float, float], vec_second: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    return (vec_first[0] - vec_second[0], vec_first[1] - vec_second[1], vec_first[2] - vec_second[2])


def _vec_scale(
    vec_in: Tuple[float, float, float], scale_val: float
) -> Tuple[float, float, float]:
    return (vec_in[0] * scale_val, vec_in[1] * scale_val, vec_in[2] * scale_val)


def _vec_cross(
    vec_first: Tuple[float, float, float], vec_second: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    return (
        vec_first[1] * vec_second[2] - vec_first[2] * vec_second[1],
        vec_first[2] * vec_second[0] - vec_first[0] * vec_second[2],
        vec_first[0] * vec_second[1] - vec_first[1] * vec_second[0],
    )


def _vec_len(vec_in: Tuple[float, float, float]) -> float:
    return math.sqrt(vec_in[0] * vec_in[0] + vec_in[1] * vec_in[1] + vec_in[2] * vec_in[2])


def _vec_norm(vec_in: Tuple[float, float, float]) -> Tuple[float, float, float]:
    length_val = _vec_len(vec_in)
    if length_val <= 1e-10:
        return (1.0, 0.0, 0.0)
    inv_len = 1.0 / length_val
    return (vec_in[0] * inv_len, vec_in[1] * inv_len, vec_in[2] * inv_len)


def _axis_angle_to_quat(
    axis_vec: Tuple[float, float, float], angle_rad: float
) -> Tuple[float, float, float, float]:
    axis_unit = _vec_norm(axis_vec)
    half_ang = 0.5 * float(angle_rad)
    sin_half = math.sin(half_ang)
    cos_half = math.cos(half_ang)
    if cos_half < 0.0:
        cos_half = -cos_half
        sin_half = -sin_half
    return (
        axis_unit[0] * sin_half,
        axis_unit[1] * sin_half,
        axis_unit[2] * sin_half,
        cos_half,
    )


def _quat_rotate_vec(
    quat_xyzw: Tuple[float, float, float, float], vec_in: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    quat_xyz = (quat_xyzw[0], quat_xyzw[1], quat_xyzw[2])
    quat_scalar = quat_xyzw[3]
    two_cross = _vec_scale(_vec_cross(quat_xyz, vec_in), 2.0)
    cross_quat = _vec_cross(quat_xyz, two_cross)
    return (
        vec_in[0] + quat_scalar * two_cross[0] + cross_quat[0],
        vec_in[1] + quat_scalar * two_cross[1] + cross_quat[1],
        vec_in[2] + quat_scalar * two_cross[2] + cross_quat[2],
    )


def _fit_eyeball_pivot_rotation(
    anchor_point: Tuple[float, float, float],
    delta_vec: Tuple[float, float, float],
    min_depth: float,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float, float]]:
    """
    Construct a posterior eyeball pivot point behind `anchor_pt` and an exact
    unit quaternion (XYZW) whose rigid rotation around that pivot maps `anchor_pt`
    to `anchor_pt + delta_vec`.
    """
    delta_len = _vec_len(delta_vec)
    if delta_len <= 1e-6:
        fallback_pivot = _vec_add(anchor_point, (0.0, float(min_depth), 0.0))
        return fallback_pivot, (0.0, 0.0, 0.0, 1.0)

    delta_dir = _vec_scale(delta_vec, 1.0 / delta_len)
    post_ref = (0.0, 1.0, 0.0)
    proj_post = _vec_sub(post_ref, _vec_scale(delta_dir, _vec_dot(post_ref, delta_dir)))
    if _vec_len(proj_post) < 1e-4:
        alt_ref = (1.0, 0.0, 0.0)
        proj_post = _vec_sub(alt_ref, _vec_scale(delta_dir, _vec_dot(alt_ref, delta_dir)))
    if proj_post[2] < 0.0:
        proj_post = (proj_post[0], proj_post[1], 0.0)
    if _vec_len(proj_post) < 1e-4:
        proj_post = (0.0, 1.0, 0.0)
    back_dir = _vec_norm(proj_post)

    pivot_depth = max(float(min_depth), delta_len * 1.6)
    mid_point = _vec_add(anchor_point, _vec_scale(delta_vec, 0.5))
    pivot_point = _vec_add(mid_point, _vec_scale(back_dir, pivot_depth))

    vec_r0 = _vec_sub(anchor_point, pivot_point)
    target_point = _vec_add(anchor_point, delta_vec)
    vec_r1 = _vec_sub(target_point, pivot_point)
    cross_rot = _vec_cross(vec_r0, vec_r1)
    sin_val = _vec_len(cross_rot)
    cos_val = _vec_dot(vec_r0, vec_r1)
    if sin_val <= 1e-10:
        return pivot_point, (0.0, 0.0, 0.0, 1.0)

    axis_vec = _vec_scale(cross_rot, 1.0 / sin_val)
    angle_rad = math.atan2(sin_val, cos_val)
    quat_xyzw = _axis_angle_to_quat(axis_vec, angle_rad)
    return pivot_point, quat_xyzw


def _clamp_zero_one(val: float) -> float:
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return float(val)


def solve_nonneg_two_vector_weights(
    delta_vec: Tuple[float, float, float],
    basis_center: Tuple[float, float, float],
    basis_outer: Tuple[float, float, float],
) -> Tuple[float, float]:
    """
    Solve `min ||delta_vec - (w_c * basis_center + w_o * basis_outer)||^2` over the
    2D simplex `{w_c >= 0, w_o >= 0, w_c + w_o <= 1}` in closed form.
    """
    gram_center_center = _vec_dot(basis_center, basis_center)
    gram_outer_outer = _vec_dot(basis_outer, basis_outer)
    gram_center_outer = _vec_dot(basis_center, basis_outer)
    rhs_center = _vec_dot(basis_center, delta_vec)
    rhs_outer = _vec_dot(basis_outer, delta_vec)

    candidates: List[Tuple[float, float]] = [(0.0, 0.0)]

    det = gram_center_center * gram_outer_outer - gram_center_outer * gram_center_outer
    if det > 1e-12:
        unclamped_center = (rhs_center * gram_outer_outer - rhs_outer * gram_center_outer) / det
        unclamped_outer = (gram_center_center * rhs_outer - gram_center_outer * rhs_center) / det
        if unclamped_center >= 0.0 and unclamped_outer >= 0.0 and (unclamped_center + unclamped_outer) <= 1.0:
            candidates.append((unclamped_center, unclamped_outer))

    if gram_center_center > 1e-12:
        candidates.append((_clamp_zero_one(rhs_center / gram_center_center), 0.0))
    if gram_outer_outer > 1e-12:
        candidates.append((0.0, _clamp_zero_one(rhs_outer / gram_outer_outer)))

    edge_dir = _vec_sub(basis_outer, basis_center)
    edge_norm_squared = _vec_dot(edge_dir, edge_dir)
    if edge_norm_squared > 1e-12:
        edge_weight_outer = _clamp_zero_one(
            _vec_dot(_vec_sub(delta_vec, basis_center), edge_dir) / edge_norm_squared
        )
        candidates.append((1.0 - edge_weight_outer, edge_weight_outer))

    best_weights = (0.0, 0.0)
    best_err_squared = float("inf")
    for cand_center, cand_outer in candidates:
        err_x = delta_vec[0] - (cand_center * basis_center[0] + cand_outer * basis_outer[0])
        err_y = delta_vec[1] - (cand_center * basis_center[1] + cand_outer * basis_outer[1])
        err_z = delta_vec[2] - (cand_center * basis_center[2] + cand_outer * basis_outer[2])
        err_squared = err_x * err_x + err_y * err_y + err_z * err_z
        if err_squared < best_err_squared:
            best_err_squared = err_squared
            best_weights = (cand_center, cand_outer)

    return best_weights


def _fit_one_eye_side_weights(
    side_deltas: Dict[int, Tuple[float, float, float]],
    side_coords: Dict[int, Tuple[float, float, float]],
    side_sign: float,
    upper_bone_name: str,
    outer_bone_name: str,
    min_travel: float = 0.004,
    side_brow_coords: Sequence[Tuple[float, float, float]] = (),
) -> Dict[str, Any]:
    """
    Compute per-vertex skin weights for one eye's `Upper` and `UpperOuterSDK` bones
    alongside the corresponding unscaled world-space translation vectors.
    """
    if not side_deltas:
        return {"ok": False, "max_disp": 0.0, "weights": {}, "deltas": {}}

    lengths: Dict[int, float] = {
        vert_idx: math.sqrt(dvec[0] ** 2 + dvec[1] ** 2 + dvec[2] ** 2)
        for vert_idx, dvec in side_deltas.items()
    }
    max_vert_idx = max(lengths, key=lengths.__getitem__)
    max_disp = lengths[max_vert_idx]
    if max_disp < min_travel:
        return {"ok": False, "max_disp": max_disp, "weights": {}, "deltas": {}}

    # Prefer downward upper-lid peak as center travel vector
    downward_verts = [
        vert_idx for vert_idx, dvec in side_deltas.items() if dvec[2] < -0.001
    ]
    center_idx = (
        max(downward_verts, key=lambda idx: lengths[idx])
        if downward_verts
        else max_vert_idx
    )
    peak_center = side_deltas[center_idx]

    # Use the anterior lash margin's Y travel (35th percentile across strong downward
    # movers) rather than a single deep upper-fold crease vertex so closed eyelashes stay
    # proudly visible on the eye surface instead of tucking inside the cheek geometry.
    strong_down = [
        vert_idx
        for vert_idx, dvec in side_deltas.items()
        if dvec[2] < -max(0.004, max_disp * 0.35)
    ]
    if strong_down:
        sorted_dys = sorted(side_deltas[idx][1] for idx in strong_down)
        pct_idx = max(0, min(len(sorted_dys) - 1, int(len(sorted_dys) * 0.35)))
        center_delta_y = min(peak_center[1], sorted_dys[pct_idx])
    else:
        center_delta_y = peak_center[1]
    peak_center = (peak_center[0], center_delta_y, peak_center[2])

    # Pick outermost moving vertex with significant downward blink displacement for outer corner vector
    sig_threshold = max(0.0025, max_disp * 0.28)
    outer_candidates = [
        vert_idx
        for vert_idx, dlen in lengths.items()
        if dlen >= sig_threshold
        and side_coords[vert_idx][0] * side_sign > 0.002
        and side_deltas[vert_idx][2] < -sig_threshold * 0.35
    ]
    if not outer_candidates:
        outer_candidates = [
            vert_idx
            for vert_idx, dlen in lengths.items()
            if dlen >= sig_threshold and side_coords[vert_idx][0] * side_sign > 0.002
        ]
    if outer_candidates:
        outer_idx = max(
            outer_candidates,
            key=lambda idx: side_coords[idx][0] * side_sign,
        )
        peak_outer = side_deltas[outer_idx]
    else:
        outer_idx = center_idx
        peak_outer = peak_center

    basis_center = (
        peak_center[0] * 1.15,
        peak_center[1] * 1.15,
        peak_center[2] * 1.15,
    )
    basis_outer = (
        peak_outer[0] * 1.35,
        peak_outer[1] * 1.35,
        peak_outer[2] * 1.35,
    )

    min_pivot_depth = max(0.022, max_disp * 1.6)
    pivot_center, quat_center = _fit_eyeball_pivot_rotation(
        side_coords[center_idx], basis_center, min_depth=min_pivot_depth
    )
    pivot_outer, quat_outer = _fit_eyeball_pivot_rotation(
        side_coords[outer_idx], basis_outer, min_depth=min_pivot_depth
    )

    anchor_z = side_coords[center_idx][2]
    upper_brow_coords = [
        point_coord for point_coord in side_brow_coords if point_coord[2] > (anchor_z + 0.004)
    ]
    global_min_brow_z = min(
        (point_coord[2] for point_coord in upper_brow_coords),
        default=anchor_z + 0.45 * max_disp,
    )

    weights_out: Dict[int, Dict[str, float]] = {}
    for vert_idx, dvec in side_deltas.items():
        if lengths[vert_idx] < 0.0004:
            continue
        vert_coord = side_coords[vert_idx]
        vert_x_val, _vert_y_val, vert_z_val = vert_coord
        near_brow_z_values = [
            point_coord[2]
            for point_coord in upper_brow_coords
            if abs(point_coord[0] - vert_x_val) <= 0.008
        ]
        local_brow_z = min(near_brow_z_values) if near_brow_z_values else global_min_brow_z
        default_ceil = (
            local_brow_z - 0.0010
            if (upper_brow_coords and dvec[2] < -0.004)
            else min(anchor_z + 0.45 * max_disp, local_brow_z - 0.0010)
        )
        z_ceil = default_ceil
        z_start = min(anchor_z + 0.08 * max_disp, z_ceil - 0.0030)
        if vert_z_val >= z_ceil:
            continue
        upper_fade = 1.0
        if vert_z_val > z_start:
            u_fade = (vert_z_val - z_start) / max(1e-6, z_ceil - z_start)
            upper_fade = 1.0 - (u_fade * u_fade * (3.0 - 2.0 * u_fade))

        rel_center = _vec_sub(vert_coord, pivot_center)
        rot_disp_center = _vec_sub(
            _quat_rotate_vec(quat_center, rel_center), rel_center
        )
        rel_outer = _vec_sub(vert_coord, pivot_outer)
        rot_disp_outer = _vec_sub(
            _quat_rotate_vec(quat_outer, rel_outer), rel_outer
        )
        weight_center, weight_outer = solve_nonneg_two_vector_weights(
            dvec, rot_disp_center, rot_disp_outer
        )
        weight_center *= upper_fade
        weight_outer *= upper_fade
        bone_map: Dict[str, float] = {}
        if weight_center > 0.002:
            bone_map[upper_bone_name] = weight_center
        if weight_outer > 0.002:
            bone_map[outer_bone_name] = weight_outer
        if bone_map:
            weights_out[vert_idx] = bone_map

    return {
        "ok": bool(weights_out),
        "max_disp": max_disp,
        "weights": weights_out,
        "deltas": {
            upper_bone_name: basis_center,
            outer_bone_name: basis_outer,
        },
        "pivots": {
            upper_bone_name: pivot_center,
            outer_bone_name: pivot_outer,
        },
        "quats": {
            upper_bone_name: quat_center,
            outer_bone_name: quat_outer,
        },
    }


def extract_body_eyelid_blink_rig_data(
    bpy_mod: Any,
    body_obj: Any,
    *,
    eye_blink_mode: str = "auto",
    shape_weights: Optional[Mapping[str, float]] = None,
    exclude_vert_indices: Optional[Iterable[int]] = None,
) -> Dict[str, Any]:
    """
    Extract upper-eyelid skinning weights (orig Body vertex index -> bone weight dict)
    and unscaled world-space blink delta vectors from the evaluated open-vs-shut
    `Body` mesh AFTER rest blendshapes have already been applied.
    """
    norm_mode = parse_eye_blink_mode(eye_blink_mode, default="auto")
    result: Dict[str, Any] = {
        "enabled": False,
        "mode": norm_mode,
        "reason": "disabled",
        "shape_key": None,
        "weights_by_orig_vert": {},
        "delta_vectors_world": {},
        "pivots_world": {},
        "rot_quats_world": {},
        "max_disp_l": 0.0,
        "max_disp_r": 0.0,
    }
    if norm_mode == "off":
        return result

    if body_obj is None or not getattr(body_obj.data, "shape_keys", None):
        result["reason"] = "no_body_shape_keys"
        return result

    if norm_mode == "auto":
        conflict = detect_custom_eye_expression_conflict(shape_weights)
        if conflict is not None:
            result["reason"] = f"custom_eye_expression:{conflict}"
            return result

    key_blocks = list(body_obj.data.shape_keys.key_blocks)
    if not key_blocks:
        result["reason"] = "empty_shape_keys"
        return result

    basis_block = key_blocks[0]
    brow_vert_indices: Set[int] = set()
    for key_item in key_blocks[1:]:
        key_lower = str(getattr(key_item, "name", "")).strip().lower()
        if not any(tok in key_lower for tok in ("brow", "mayu", "まゆ", "眉")):
            continue
        key_data = getattr(key_item, "data", None)
        basis_data = getattr(basis_block, "data", None)
        if not key_data or not basis_data or len(key_data) != len(basis_data):
            continue
        for v_idx in range(len(basis_data)):
            basis_coord = basis_data[v_idx].co
            key_vert_coord = key_data[v_idx].co
            delta_x_bone = float(key_vert_coord.x) - float(basis_coord.x)
            delta_y_bone = float(key_vert_coord.y) - float(basis_coord.y)
            delta_z_bone = float(key_vert_coord.z) - float(basis_coord.z)
            if (delta_x_bone * delta_x_bone + delta_y_bone * delta_y_bone + delta_z_bone * delta_z_bone) > 4.0e-8:
                brow_vert_indices.add(v_idx)

    basis_positions = [
        (float(vert.co.x), float(vert.co.y), float(vert.co.z))
        for vert in body_obj.data.vertices
    ]
    blink_keys = find_blink_shape_key_group(key_blocks, base_positions=basis_positions)
    if not blink_keys:
        result["reason"] = "no_blink_shape_key"
        return result
    result["shape_key"] = "+".join(str(blink_key_item.name) for blink_key_item in blink_keys)

    excluded_set: Set[int] = set(exclude_vert_indices or ())

    depsgraph = bpy_mod.context.evaluated_depsgraph_get()
    bpy_mod.context.view_layer.update()
    eval_open = body_obj.evaluated_get(depsgraph)
    open_world_mat = eval_open.matrix_world.copy()
    open_mesh = eval_open.to_mesh()
    try:
        if len(open_mesh.vertices) != len(body_obj.data.vertices):
            result["reason"] = "vertex_count_mismatch"
            return result
        open_coords: List[Tuple[float, float, float]] = []
        for vert_item in open_mesh.vertices:
            world_point = open_world_mat @ vert_item.co
            open_coords.append((float(world_point.x), float(world_point.y), float(world_point.z)))
    finally:
        eval_open.to_mesh_clear()

    prev_states = [(blk, float(blk.value), bool(blk.mute)) for blk in blink_keys]
    shut_coords: List[Tuple[float, float, float]] = []
    try:
        for blk in blink_keys:
            blk.mute = False
            blk.value = 1.0
        bpy_mod.context.view_layer.update()
        eval_shut = body_obj.evaluated_get(depsgraph)
        shut_world_mat = eval_shut.matrix_world.copy()
        shut_mesh = eval_shut.to_mesh()
        try:
            for vert_item in shut_mesh.vertices:
                world_point = shut_world_mat @ vert_item.co
                shut_coords.append((float(world_point.x), float(world_point.y), float(world_point.z)))
        finally:
            eval_shut.to_mesh_clear()
    finally:
        for blk, old_val, old_mute in prev_states:
            blk.value = old_val
            blk.mute = old_mute
        bpy_mod.context.view_layer.update()

    left_deltas: Dict[int, Tuple[float, float, float]] = {}
    left_coords: Dict[int, Tuple[float, float, float]] = {}
    right_deltas: Dict[int, Tuple[float, float, float]] = {}
    right_coords: Dict[int, Tuple[float, float, float]] = {}

    for vert_idx, open_point in enumerate(open_coords):
        if vert_idx in excluded_set or vert_idx in brow_vert_indices:
            continue
        shut_point = shut_coords[vert_idx]
        dvec = (
            shut_point[0] - open_point[0],
            shut_point[1] - open_point[1],
            shut_point[2] - open_point[2],
        )
        delta_len_squared = dvec[0] * dvec[0] + dvec[1] * dvec[1] + dvec[2] * dvec[2]
        if delta_len_squared < 2.5e-7:
            continue
        if open_point[0] > 0.002:
            left_deltas[vert_idx] = dvec
            left_coords[vert_idx] = open_point
        elif open_point[0] < -0.002:
            right_deltas[vert_idx] = dvec
            right_coords[vert_idx] = open_point

    left_brow_coords = [
        open_coords[v_idx]
        for v_idx in brow_vert_indices
        if v_idx < len(open_coords) and open_coords[v_idx][0] > 0.002
    ]
    right_brow_coords = [
        open_coords[v_idx]
        for v_idx in brow_vert_indices
        if v_idx < len(open_coords) and open_coords[v_idx][0] < -0.002
    ]

    left_fit = _fit_one_eye_side_weights(
        left_deltas,
        left_coords,
        side_sign=1.0,
        upper_bone_name="PB_Blink_L",
        outer_bone_name="PB_Blink_LO",
        side_brow_coords=left_brow_coords,
    )
    right_fit = _fit_one_eye_side_weights(
        right_deltas,
        right_coords,
        side_sign=-1.0,
        upper_bone_name="PB_Blink_R",
        outer_bone_name="PB_Blink_RO",
        side_brow_coords=right_brow_coords,
    )
    result["max_disp_l"] = float(left_fit["max_disp"])
    result["max_disp_r"] = float(right_fit["max_disp"])

    if not left_fit["ok"] or not right_fit["ok"]:
        result["reason"] = (
            f"eyes_already_closed_or_asymmetric(L={left_fit['max_disp']*1000:.1f}mm,"
            f"R={right_fit['max_disp']*1000:.1f}mm)"
        )
        return result

    if norm_mode == "auto":
        min_side = min(left_fit["max_disp"], right_fit["max_disp"])
        max_side = max(left_fit["max_disp"], right_fit["max_disp"])
        if max_side > 1e-6 and (min_side / max_side) < 0.45:
            result["reason"] = (
                f"asymmetric_wink_detected(L={left_fit['max_disp']*1000:.1f}mm,"
                f"R={right_fit['max_disp']*1000:.1f}mm)"
            )
            return result

    combined_weights: Dict[int, Dict[str, float]] = {}
    combined_weights.update(left_fit["weights"])
    combined_weights.update(right_fit["weights"])

    combined_deltas: Dict[str, Tuple[float, float, float]] = {}
    combined_deltas.update(left_fit["deltas"])
    combined_deltas.update(right_fit["deltas"])

    combined_pivots: Dict[str, Tuple[float, float, float]] = {}
    combined_pivots.update(left_fit.get("pivots") or {})
    combined_pivots.update(right_fit.get("pivots") or {})

    combined_quats: Dict[str, Tuple[float, float, float, float]] = {}
    combined_quats.update(left_fit.get("quats") or {})
    combined_quats.update(right_fit.get("quats") or {})

    result["enabled"] = True
    result["reason"] = "ok"
    result["weights_by_orig_vert"] = combined_weights
    result["delta_vectors_world"] = combined_deltas
    result["pivots_world"] = combined_pivots
    result["rot_quats_world"] = combined_quats
    return result


def scale_eye_blink_deltas(
    blink_rig_data: Optional[Mapping[str, Any]],
    uniform_scale: float,
) -> Dict[str, Tuple[float, float, float]]:
    """Scale world-space blink displacement vectors into GTA V ped YDD units."""
    if not blink_rig_data or not blink_rig_data.get("enabled"):
        return {}
    raw_deltas = blink_rig_data.get("delta_vectors_world") or {}
    scaled: Dict[str, Tuple[float, float, float]] = {}
    for bone_name, vec_xyz in raw_deltas.items():
        scaled[str(bone_name)] = (
            float(vec_xyz[0]) * float(uniform_scale),
            float(vec_xyz[1]) * float(uniform_scale),
            float(vec_xyz[2]) * float(uniform_scale),
        )
    return scaled


def apply_eyelid_blink_weights_to_mesh(
    target_obj: Any,
    eyelid_weights_by_orig_vert: Optional[Mapping[int, Mapping[str, float]]],
    *,
    kept_orig_vert_indices: Optional[Sequence[int]] = None,
    head_bone_name: str = "SKEL_Head",
) -> int:
    """
    Paint upper-eyelid blink weights onto `target_obj`, subtracting the eyelid share
    proportionally from `SKEL_Head` so total vertex weights remain normalized.
    Works for both pre-split `orig_vert_idx == vert.index` and post-bake meshes via
    `kept_orig_vert_indices`. Returns count of painted vertices.
    """
    if target_obj is None or not eyelid_weights_by_orig_vert:
        return 0

    head_vgroup = target_obj.vertex_groups.get(head_bone_name)
    if head_vgroup is None:
        head_vgroup = target_obj.vertex_groups.new(name=head_bone_name)

    eyelid_vgroups: Dict[str, Any] = {}
    for bone_name in EYELID_BLINK_BONES:
        vgrp = target_obj.vertex_groups.get(bone_name)
        if vgrp is None:
            vgrp = target_obj.vertex_groups.new(name=bone_name)
        eyelid_vgroups[bone_name] = vgrp

    painted_count = 0
    num_mesh_verts = len(target_obj.data.vertices)
    if kept_orig_vert_indices is None:
        index_pairs = [(idx, idx) for idx in range(num_mesh_verts)]
    else:
        index_pairs = list(enumerate(kept_orig_vert_indices))

    for mesh_vert_idx, orig_vert_idx in index_pairs:
        if mesh_vert_idx >= num_mesh_verts:
            continue
        lid_weights = eyelid_weights_by_orig_vert.get(orig_vert_idx)
        if not lid_weights:
            continue

        lid_sum = sum(float(val) for val in lid_weights.values())
        if lid_sum <= 1e-6:
            continue
        scale_factor = 1.0 / lid_sum if lid_sum > 1.0 else 1.0

        head_weight = 0.0
        for grp_elem in target_obj.data.vertices[mesh_vert_idx].groups:
            if grp_elem.group == head_vgroup.index:
                head_weight = float(grp_elem.weight)
                break
        if head_weight <= 0.0:
            head_weight = 1.0

        scaled_sum = min(1.0, lid_sum * scale_factor)
        new_head_weight = max(0.0, head_weight * (1.0 - scaled_sum))
        head_vgroup.add([mesh_vert_idx], new_head_weight, "REPLACE")

        for bone_name, raw_lid_weight in lid_weights.items():
            grp_obj = eyelid_vgroups.get(bone_name)
            if grp_obj is not None:
                final_weight = min(1.0, float(raw_lid_weight) * scale_factor * head_weight)
                if final_weight > 0.001:
                    grp_obj.add([mesh_vert_idx], final_weight, "REPLACE")
        painted_count += 1

    return painted_count


def build_blink_profile_for_ped(
    ped_armature: Any,
    ped_model_name: str,
    delta_vectors_ydd: Optional[Mapping[str, Tuple[float, float, float]]] = None,
    *,
    delta_rotations_world: Optional[
        Mapping[str, Tuple[float, float, float, float]]
    ] = None,
    enabled: bool = True,
    min_interval_sec: float = 2.6,
    max_interval_sec: float = 6.0,
    blink_duration_sec: float = 0.25,
    double_blink_chance: float = 0.18,
    max_blink: float = 1.0,
) -> Optional[Dict[str, object]]:
    """
    Build a runtime `[Blink_*]` profile for `GTAVPhysBones.ini` by expressing each
    eyelid bone's pure rotation (`delta_rot` in bone local space, keeping `local_pos`
    fixed so GTA V's runtime skeleton pipeline matches PhysBone rotation chains) or
    fallback YDD translation (`delta_pos`) relative to `SKEL_Head`.
    Returns None if required eyelid bones are absent from `ped_armature`.
    """
    has_rot_map = bool(delta_rotations_world)
    has_pos_map = bool(delta_vectors_ydd)
    if ped_armature is None or (not has_rot_map and not has_pos_map):
        return None

    import mathutils

    pose_bones = ped_armature.pose.bones
    data_bones = ped_armature.data.bones
    for bone_name, _tag, parent_name, _ptag in EYELID_BLINK_BONE_SPECS:
        if bone_name not in pose_bones or parent_name not in pose_bones:
            return None
        in_rot = bool(delta_rotations_world and bone_name in delta_rotations_world)
        in_pos = bool(delta_vectors_ydd and bone_name in delta_vectors_ydd)
        if not in_rot and not in_pos:
            return None

    arm_world = ped_armature.matrix_world
    world_mats: Dict[str, Any] = {}
    parent_names = {spec_item[2] for spec_item in EYELID_BLINK_BONE_SPECS}
    for bone_name in tuple(sorted(parent_names)) + EYELID_BLINK_BONES:
        pose_item = pose_bones.get(bone_name)
        if pose_item is None:
            return None
        world_mats[bone_name] = arm_world @ pose_item.matrix

    bone_entries: List[Dict[str, object]] = []
    for bone_name, fallback_tag, parent_name, fallback_ptag in EYELID_BLINK_BONE_SPECS:
        parent_world = world_mats[parent_name]
        cur_world = world_mats[bone_name]
        local_mat = parent_world.inverted() @ cur_world
        loc_pos, loc_rot, _unused_scale = local_mat.decompose()

        if delta_rotations_world and bone_name in delta_rotations_world:
            raw_quat = delta_rotations_world[bone_name]
            quat_world_delta = mathutils.Quaternion(
                (
                    float(raw_quat[3]),
                    float(raw_quat[0]),
                    float(raw_quat[1]),
                    float(raw_quat[2]),
                )
            ).normalized()
            cur_rot = cur_world.to_quaternion().normalized()
            quat_delta_local = (
                cur_rot.inverted() @ quat_world_delta @ cur_rot
            ).normalized()
            if quat_delta_local.w < 0.0:
                quat_delta_local.negate()
            delta_rot_tuple = (
                float(quat_delta_local.x),
                float(quat_delta_local.y),
                float(quat_delta_local.z),
                float(quat_delta_local.w),
            )
            delta_local = mathutils.Vector((0.0, 0.0, 0.0))
        else:
            target_world_delta = mathutils.Vector(
                (delta_vectors_ydd or {})[bone_name]
            )
            if delta_vectors_ydd and parent_name in delta_vectors_ydd:
                net_world_delta = target_world_delta - mathutils.Vector(
                    delta_vectors_ydd[parent_name]
                )
            else:
                net_world_delta = target_world_delta

            parent_rot_inv = parent_world.to_3x3().inverted()
            delta_local = parent_rot_inv @ net_world_delta
            delta_rot_tuple = (0.0, 0.0, 0.0, 1.0)

        bone_data = data_bones.get(bone_name)
        parent_data = data_bones.get(parent_name)
        bone_props = getattr(bone_data, "bone_properties", None)
        if bone_props is not None and getattr(bone_props, "use_manual_tag", False):
            raw_btag = int(getattr(bone_props, "manual_tag", 0) or 0)
        else:
            raw_btag = int(getattr(bone_props, "tag", 0) or 0)
        bone_tag = raw_btag or fallback_tag

        parent_props = getattr(parent_data, "bone_properties", None)
        if parent_props is not None and getattr(parent_props, "use_manual_tag", False):
            raw_ptag = int(getattr(parent_props, "manual_tag", 0) or 0)
        else:
            raw_ptag = int(getattr(parent_props, "tag", 0) or 0)
        parent_tag = raw_ptag or fallback_ptag

        bone_entries.append(
            {
                "name": bone_name,
                "tag": bone_tag,
                "parent_tag": parent_tag,
                "local_pos": (float(loc_pos.x), float(loc_pos.y), float(loc_pos.z)),
                "local_rot": (
                    float(loc_rot.x),
                    float(loc_rot.y),
                    float(loc_rot.z),
                    float(loc_rot.w),
                ),
                "delta_pos": (
                    float(delta_local.x),
                    float(delta_local.y),
                    float(delta_local.z),
                ),
                "delta_rot": delta_rot_tuple,
            }
        )

    clamped_max_blink = parse_eye_blink_strength(max_blink, default=1.0)
    return {
        "model": str(ped_model_name or "all").strip().lower(),
        "enabled": 1 if enabled else 0,
        "min_interval": float(min_interval_sec),
        "max_interval": float(max_interval_sec),
        "blink_duration": float(blink_duration_sec),
        "double_blink_chance": float(double_blink_chance),
        "max_blink": clamped_max_blink,
        "bones": bone_entries,
    }


def select_jaw_and_blink_candidates(
    active_meshes: Sequence[Any],
) -> Tuple[Any, List[Any]]:
    """Select the mesh owning mouth/jaw shape keys and ordered eyelid blink candidates cleanly."""
    import blendshape_helper

    jaw_shape_keys = {tok.lower() for tok in MOUTH_OPEN_SHAPE_KEYS}

    def _strip_num_suffix(raw_name: str) -> str:
        return re.sub(r"\.\d{3}$", "", str(raw_name or "").strip()).lower()

    def _has_mouth_keys(mesh_item: Any) -> bool:
        key_blocks = getattr(getattr(mesh_item.data, "shape_keys", None), "key_blocks", ())
        return any(key_block.name.strip().lower() in jaw_shape_keys for key_block in key_blocks)

    jaw_body_obj = (
        next((item for item in active_meshes if _strip_num_suffix(item.name) == "body" and _has_mouth_keys(item)), None)
        or next((item for item in active_meshes if _has_mouth_keys(item)), None)
        or next((item for item in active_meshes if _strip_num_suffix(item.name) == "body"), active_meshes[0])
    )
    blink_mesh_list = [
        item
        for item in active_meshes
        if blendshape_helper.is_body_or_face_skin_mesh(item)
        or any(
            "blink" in key_block.name.lower() or "eye_close" in key_block.name.lower()
            for key_block in getattr(getattr(item.data, "shape_keys", None), "key_blocks", ())
        )
    ]
    seen_mesh_names = {item.name for item in blink_mesh_list}
    for item in active_meshes:
        if item.name not in seen_mesh_names:
            blink_mesh_list.append(item)
            seen_mesh_names.add(item.name)
    return jaw_body_obj, blink_mesh_list
