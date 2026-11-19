#!/usr/bin/env python3
"""
eye_blink_helper.py
===================
Optional natural eye-blink rigging and GTAVPhysBones.ini profile extraction for
converted VRChat avatars in GTA V.

Uses the four native GTA V upper-eyelid facial bones already present in
`player_zero.yft`, `player_one.yft`, and `player_two.yft` without consuming any
of the 63 custom PhysBone bone slots:
  - FACIAL_L_eyelidUpper        (tag 38849, parent FACIAL_facialRoot)
  - FACIAL_L_eyelidUpperOuterSDK(tag 44821, parent FACIAL_L_eyelidUpper)
  - FACIAL_R_eyelidUpper        (tag 32276, parent FACIAL_facialRoot)
  - FACIAL_R_eyelidUpperOuterSDK(tag 45333, parent FACIAL_R_eyelidUpper)

Automatic safety checks inspect active facial blendshapes and measured rest-to-shut
displacement so avatars with custom closed, winking, or smiling eye expressions
do not get glitched eyelids unless the user explicitly overrides with `--eye-blink`.
"""

from __future__ import annotations

import math
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


EYELID_BLINK_BONE_SPECS: Tuple[Tuple[str, int, str, int], ...] = (
    ("FACIAL_L_eyelidUpper", 38849, "FACIAL_facialRoot", 65068),
    ("FACIAL_L_eyelidUpperOuterSDK", 44821, "FACIAL_L_eyelidUpper", 38849),
    ("FACIAL_R_eyelidUpper", 32276, "FACIAL_facialRoot", 65068),
    ("FACIAL_R_eyelidUpperOuterSDK", 45333, "FACIAL_R_eyelidUpper", 32276),
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
    "shinano_casual": 0.50,
    "shinano_er": 0.50,
    "miltina_maid": 0.60,
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
        if "miltina" in norm_cand or "milltina" in norm_cand:
            return float(DEFAULT_BLINK_STRENGTH_BY_AVATAR["miltina_maid"])
        if "shinano" in norm_cand:
            return float(DEFAULT_BLINK_STRENGTH_BY_AVATAR["shinano_casual"])
    return float(default)


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


def find_blink_shape_key(
    key_blocks: Sequence[Any],
    base_positions: Optional[Sequence[Tuple[float, float, float]]] = None,
    min_moved_verts: int = 10,
) -> Optional[Any]:
    """
    Find the best upper-eyelid blink shape key in `key_blocks`, normalizing trailing
    spaces (e.g., Milltina's `'vrc.blink '`) and preferring canonical VRC blink keys.
    """
    if not key_blocks:
        return None

    normalized_blocks: List[Tuple[str, Any]] = []
    for key_item in key_blocks:
        key_name = getattr(key_item, "name", "")
        norm_name = str(key_name).strip().lower()
        if norm_name and norm_name != "basis":
            normalized_blocks.append((norm_name, key_item))

    def _has_enough_motion(key_item: Any) -> bool:
        if not base_positions:
            return True
        key_data = getattr(key_item, "data", None)
        if not key_data or len(key_data) != len(base_positions):
            return False
        moved = 0
        for idx, base_pos in enumerate(base_positions):
            key_co = key_data[idx].co
            diff_x = float(key_co.x) - base_pos[0]
            diff_y = float(key_co.y) - base_pos[1]
            diff_z = float(key_co.z) - base_pos[2]
            if (diff_x * diff_x + diff_y * diff_y + diff_z * diff_z) >= 2.5e-7:
                moved += 1
                if moved >= min_moved_verts:
                    return True
        return False

    for candidate in BLINK_SHAPE_KEY_CANDIDATES:
        for norm_name, key_item in normalized_blocks:
            if norm_name == candidate and _has_enough_motion(key_item):
                return key_item

    for candidate in BLINK_SHAPE_KEY_CANDIDATES:
        for norm_name, key_item in normalized_blocks:
            if candidate in norm_name and _has_enough_motion(key_item):
                return key_item

    return None


def prepare_ydd_blink_bone_set(
    base_valid_bones: Iterable[str],
    *,
    enable_eye_blink: bool,
    custom_bone_count: int = 0,
    max_total_bones: int = 128,
) -> Tuple[Set[str], int]:
    """
    Add GTA V native upper-eyelid bones to the `.ydd` valid bone whitelist when eye
    blinking is enabled, pruning unskinned leaf hand helper bones (`PH_*`/`IK_*`) from
    the `.ydd` export only if needed to stay within RAGE's 128-bone `.ydd` limit.
    (`.yft` skeletons always retain all `PH_*`/`IK_*` bones independently.)
    """
    valid_bones: Set[str] = set(base_valid_bones)
    if not enable_eye_blink:
        return valid_bones, 0

    valid_bones.update(EYELID_BLINK_BONES)
    stripped_count = 0
    if len(valid_bones) + int(custom_bone_count) > int(max_total_bones):
        for hand_leaf in YFT_ONLY_HAND_BONES:
            if hand_leaf in valid_bones:
                valid_bones.remove(hand_leaf)
                stripped_count += 1
    return valid_bones, stripped_count


def _vec_dot(vec_a: Tuple[float, float, float], vec_b: Tuple[float, float, float]) -> float:
    return vec_a[0] * vec_b[0] + vec_a[1] * vec_b[1] + vec_a[2] * vec_b[2]


def _vec_sub(
    vec_a: Tuple[float, float, float], vec_b: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    return (vec_a[0] - vec_b[0], vec_a[1] - vec_b[1], vec_a[2] - vec_b[2])


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
    gram_cc = _vec_dot(basis_center, basis_center)
    gram_oo = _vec_dot(basis_outer, basis_outer)
    gram_co = _vec_dot(basis_center, basis_outer)
    rhs_c = _vec_dot(basis_center, delta_vec)
    rhs_o = _vec_dot(basis_outer, delta_vec)

    candidates: List[Tuple[float, float]] = [(0.0, 0.0)]

    det = gram_cc * gram_oo - gram_co * gram_co
    if det > 1e-12:
        unc_c = (rhs_c * gram_oo - rhs_o * gram_co) / det
        unc_o = (gram_cc * rhs_o - gram_co * rhs_c) / det
        if unc_c >= 0.0 and unc_o >= 0.0 and (unc_c + unc_o) <= 1.0:
            candidates.append((unc_c, unc_o))

    if gram_cc > 1e-12:
        candidates.append((_clamp_zero_one(rhs_c / gram_cc), 0.0))
    if gram_oo > 1e-12:
        candidates.append((0.0, _clamp_zero_one(rhs_o / gram_oo)))

    edge_dir = _vec_sub(basis_outer, basis_center)
    edge_norm_sq = _vec_dot(edge_dir, edge_dir)
    if edge_norm_sq > 1e-12:
        edge_weight_o = _clamp_zero_one(
            _vec_dot(_vec_sub(delta_vec, basis_center), edge_dir) / edge_norm_sq
        )
        candidates.append((1.0 - edge_weight_o, edge_weight_o))

    best_weights = (0.0, 0.0)
    best_err_sq = float("inf")
    for cand_c, cand_o in candidates:
        err_x = delta_vec[0] - (cand_c * basis_center[0] + cand_o * basis_outer[0])
        err_y = delta_vec[1] - (cand_c * basis_center[1] + cand_o * basis_outer[1])
        err_z = delta_vec[2] - (cand_c * basis_center[2] + cand_o * basis_outer[2])
        err_sq = err_x * err_x + err_y * err_y + err_z * err_z
        if err_sq < best_err_sq:
            best_err_sq = err_sq
            best_weights = (cand_c, cand_o)

    return best_weights


def _fit_one_eye_side_weights(
    side_deltas: Dict[int, Tuple[float, float, float]],
    side_coords: Dict[int, Tuple[float, float, float]],
    side_sign: float,
    upper_bone_name: str,
    outer_bone_name: str,
    min_travel: float = 0.004,
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
        center_dy = min(peak_center[1], sorted_dys[pct_idx])
    else:
        center_dy = peak_center[1]
    peak_center = (peak_center[0], center_dy, peak_center[2])

    # Pick outermost moving vertex with significant blink displacement for outer corner vector
    sig_threshold = max(0.0025, max_disp * 0.28)
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

    weights_out: Dict[int, Dict[str, float]] = {}
    for vert_idx, dvec in side_deltas.items():
        if lengths[vert_idx] < 0.0004:
            continue
        weight_c, weight_o = solve_nonneg_two_vector_weights(
            dvec, basis_center, basis_outer
        )
        bone_map: Dict[str, float] = {}
        if weight_c > 0.002:
            bone_map[upper_bone_name] = weight_c
        if weight_o > 0.002:
            bone_map[outer_bone_name] = weight_o
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

    basis_positions = [
        (float(vert.co.x), float(vert.co.y), float(vert.co.z))
        for vert in body_obj.data.vertices
    ]
    blink_key = find_blink_shape_key(key_blocks, base_positions=basis_positions)
    if blink_key is None:
        result["reason"] = "no_blink_shape_key"
        return result
    result["shape_key"] = str(blink_key.name)

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
            world_pt = open_world_mat @ vert_item.co
            open_coords.append((float(world_pt.x), float(world_pt.y), float(world_pt.z)))
    finally:
        eval_open.to_mesh_clear()

    prev_value = float(blink_key.value)
    prev_mute = bool(blink_key.mute)
    shut_coords: List[Tuple[float, float, float]] = []
    try:
        blink_key.mute = False
        blink_key.value = 1.0
        bpy_mod.context.view_layer.update()
        eval_shut = body_obj.evaluated_get(depsgraph)
        shut_world_mat = eval_shut.matrix_world.copy()
        shut_mesh = eval_shut.to_mesh()
        try:
            for vert_item in shut_mesh.vertices:
                world_pt = shut_world_mat @ vert_item.co
                shut_coords.append((float(world_pt.x), float(world_pt.y), float(world_pt.z)))
        finally:
            eval_shut.to_mesh_clear()
    finally:
        blink_key.value = prev_value
        blink_key.mute = prev_mute
        bpy_mod.context.view_layer.update()

    left_deltas: Dict[int, Tuple[float, float, float]] = {}
    left_coords: Dict[int, Tuple[float, float, float]] = {}
    right_deltas: Dict[int, Tuple[float, float, float]] = {}
    right_coords: Dict[int, Tuple[float, float, float]] = {}

    for vert_idx, open_pt in enumerate(open_coords):
        if vert_idx in excluded_set:
            continue
        shut_pt = shut_coords[vert_idx]
        dvec = (
            shut_pt[0] - open_pt[0],
            shut_pt[1] - open_pt[1],
            shut_pt[2] - open_pt[2],
        )
        dlen_sq = dvec[0] * dvec[0] + dvec[1] * dvec[1] + dvec[2] * dvec[2]
        if dlen_sq < 2.5e-7:
            continue
        if open_pt[0] > 0.002:
            left_deltas[vert_idx] = dvec
            left_coords[vert_idx] = open_pt
        elif open_pt[0] < -0.002:
            right_deltas[vert_idx] = dvec
            right_coords[vert_idx] = open_pt

    left_fit = _fit_one_eye_side_weights(
        left_deltas,
        left_coords,
        side_sign=1.0,
        upper_bone_name="FACIAL_L_eyelidUpper",
        outer_bone_name="FACIAL_L_eyelidUpperOuterSDK",
    )
    right_fit = _fit_one_eye_side_weights(
        right_deltas,
        right_coords,
        side_sign=-1.0,
        upper_bone_name="FACIAL_R_eyelidUpper",
        outer_bone_name="FACIAL_R_eyelidUpperOuterSDK",
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

    result["enabled"] = True
    result["reason"] = "ok"
    result["weights_by_orig_vert"] = combined_weights
    result["delta_vectors_world"] = combined_deltas
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

        for bone_name, raw_w in lid_weights.items():
            grp_obj = eyelid_vgroups.get(bone_name)
            if grp_obj is not None:
                final_w = min(1.0, float(raw_w) * scale_factor * head_weight)
                if final_w > 0.001:
                    grp_obj.add([mesh_vert_idx], final_w, "REPLACE")
        painted_count += 1

    return painted_count


def build_blink_profile_for_ped(
    ped_armature: Any,
    ped_model_name: str,
    delta_vectors_ydd: Optional[Mapping[str, Tuple[float, float, float]]],
    *,
    enabled: bool = True,
    min_interval_sec: float = 2.6,
    max_interval_sec: float = 6.0,
    blink_duration_sec: float = 0.215,
    double_blink_chance: float = 0.18,
    max_blink: float = 1.0,
) -> Optional[Dict[str, object]]:
    """
    Build a runtime `[Blink_*]` profile for `GTAVPhysBones.ini` by expressing each
    eyelid bone's YDD world displacement in its parent bone's rest local space.
    Returns None if required eyelid bones are absent from `ped_armature`.
    """
    if ped_armature is None or not delta_vectors_ydd:
        return None

    import mathutils

    pose_bones = ped_armature.pose.bones
    data_bones = ped_armature.data.bones
    for bone_name, _tag, parent_name, _ptag in EYELID_BLINK_BONE_SPECS:
        if bone_name not in pose_bones or parent_name not in pose_bones:
            return None
        if bone_name not in delta_vectors_ydd:
            return None

    arm_world = ped_armature.matrix_world
    world_mats: Dict[str, Any] = {}
    for bone_name in ("FACIAL_facialRoot",) + EYELID_BLINK_BONES:
        pose_item = pose_bones.get(bone_name)
        if pose_item is None:
            return None
        world_mats[bone_name] = arm_world @ pose_item.matrix

    upper_world_deltas = {
        "FACIAL_L_eyelidUpper": mathutils.Vector(delta_vectors_ydd["FACIAL_L_eyelidUpper"]),
        "FACIAL_R_eyelidUpper": mathutils.Vector(delta_vectors_ydd["FACIAL_R_eyelidUpper"]),
    }

    bone_entries: List[Dict[str, object]] = []
    for bone_name, fallback_tag, parent_name, fallback_ptag in EYELID_BLINK_BONE_SPECS:
        parent_world = world_mats[parent_name]
        cur_world = world_mats[bone_name]
        local_mat = parent_world.inverted() @ cur_world
        loc_pos, loc_rot, _unused_scale = local_mat.decompose()

        target_world_delta = mathutils.Vector(delta_vectors_ydd[bone_name])
        if bone_name == "FACIAL_L_eyelidUpperOuterSDK":
            net_world_delta = target_world_delta - upper_world_deltas["FACIAL_L_eyelidUpper"]
        elif bone_name == "FACIAL_R_eyelidUpperOuterSDK":
            net_world_delta = target_world_delta - upper_world_deltas["FACIAL_R_eyelidUpper"]
        else:
            net_world_delta = target_world_delta

        parent_rot_inv = parent_world.to_3x3().inverted()
        delta_local = parent_rot_inv @ net_world_delta

        bone_data = data_bones.get(bone_name)
        parent_data = data_bones.get(parent_name)
        bone_tag = int(
            getattr(getattr(bone_data, "bone_properties", None), "tag", 0) or fallback_tag
        )
        parent_tag = int(
            getattr(getattr(parent_data, "bone_properties", None), "tag", 0) or fallback_ptag
        )

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
