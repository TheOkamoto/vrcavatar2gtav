#!/usr/bin/env python3
"""
physbone_helper.py
==================
Layer 5 of 5 (Public Facade & Budget Packer / Blender Chain Builder).

Provides high-level VRCPhysBone packing within RAGE engine bone budgets
(`<= 63` custom / `<= 128` total per ped), Blender armature chain injection,
and unified backward-compatible re-exports of the four underlying PhysBone
architectural layers:
  - `physbone_presets_layer`: constants, priority tiers, bone maps, tag hashes
  - `physbone_cfg_ini_layer`: `.cfg` & `GTAVPhysBones.ini` I/O, curve math, sim
  - `physbone_unity_fbx_layer`: FBX weight inspection, prefab/orphan pruning
  - `physbone_scene_extractor_layer`: full Unity scene PhysBone extraction
"""

from configparser import ConfigParser
import collections as collections_module
import math
import os as operating_system
from pathlib import Path
import re as regex_module
import struct
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union
import zlib

try:
    from physbone_presets_layer import (
        _FBX_WEIGHTED_BONES_CACHE,
    SKEL_HEAD_TAG,
    SKEL_NECK_1_TAG,
    SKEL_SPINE0_TAG,
    SKEL_SPINE1_TAG,
    SKEL_SPINE2_TAG,
    SKEL_SPINE3_TAG,
    SKEL_PELVIS_TAG,
    SKEL_L_THIGH_TAG,
    SKEL_R_THIGH_TAG,
    SKEL_L_CALF_TAG,
    SKEL_R_CALF_TAG,
    SKEL_L_FOOT_TAG,
    SKEL_R_FOOT_TAG,
    SKEL_L_CLAVICLE_TAG,
    SKEL_R_CLAVICLE_TAG,
    SKEL_L_UPPERARM_TAG,
    SKEL_R_UPPERARM_TAG,
    SKEL_L_FOREARM_TAG,
    SKEL_R_FOREARM_TAG,
    SKEL_L_HAND_TAG,
    SKEL_R_HAND_TAG,
    MAX_CUSTOM_PHYSBONES_PER_PED,
    PHYSBONE_PRIORITY_TIERS,
    _PHYSBONE_TIER_BY_KEY,
    _GARMENT_MODIFIER_TOKENS,
    _KEEP_FINAL_S_TOKENS,
    _tokenize_physbone_name,
    _match_tier_tokens,
    score_physbone_chain_priority,
    build_physbone_priority_report_from_chains,
    format_physbone_priority_summary,
    PARENT_BONE_TAGS,
    UNITY_ANCESTOR_TO_GTAV_PARENT,
    resolve_parent_bone_from_unity_chain,
    _chain_parent_map,
    NEKO_MIMI_HALO_WEIGHT_SPLIT,
    MICHAEL_ER_BONE_MAP,
    MICHAEL_ER_CHAIN_SPECS,
    MICHAEL_ER_ROOT_PARENTS,
    MICHAEL_ER_CUSTOM_BONES,
    MICHAEL_ER_PARENT_MAP,
    NEKO_MIMI_BONE_MAP,
    NEKO_MIMI_CHAIN_SPECS,
    NEKO_MIMI_CUSTOM_BONES,
    NEKO_MIMI_PARENT_MAP,
    SHINANO_CASUAL_BONE_MAP,
    SHINANO_CASUAL_CHAIN_SPECS,
    SHINANO_CASUAL_ROOT_PARENTS,
    SHINANO_CASUAL_CUSTOM_BONES,
    SHINANO_CASUAL_PARENT_MAP,
    MILTINA_MAID_BONE_MAP,
    MILTINA_MAID_CHAIN_SPECS,
    MILTINA_MAID_ROOT_PARENTS,
    MILTINA_MAID_CUSTOM_BONES,
    MILTINA_MAID_PARENT_MAP,
    MILTINA_MARSHMALLOW_ONLY_CHAINS,
    CUSTOM_BONE_FLAGS,
    VRCHAT_PHYSBONE_SCRIPT_GUID,
    VRCHAT_PHYSBONE_CLASS_FILE_ID,
    VALID_PHYSBONE_SOURCES,
    DEFAULT_PHYSBONE_PRESET_RELATIVE_PATHS,
    parse_bool_flag,
    _build_marshmallow_pair_presets,
    MARSHMALLOW_PB_AVATAR_PRESETS,
    apply_marshmallow_pb_presets,
    compute_gtav_bone_tag,
    VANILLA_RESERVED_BONE_TAGS,
    resolve_bone_from_mapping,
    resolve_michael_er_gtav_bone,
    resolve_neko_mimi_gtav_bone,
    resolve_shinano_casual_gtav_bone,
    resolve_miltina_maid_gtav_bone,
    )
except ImportError:
    from common_tools.physbone_presets_layer import (
        _FBX_WEIGHTED_BONES_CACHE,
    SKEL_HEAD_TAG,
    SKEL_NECK_1_TAG,
    SKEL_SPINE0_TAG,
    SKEL_SPINE1_TAG,
    SKEL_SPINE2_TAG,
    SKEL_SPINE3_TAG,
    SKEL_PELVIS_TAG,
    SKEL_L_THIGH_TAG,
    SKEL_R_THIGH_TAG,
    SKEL_L_CALF_TAG,
    SKEL_R_CALF_TAG,
    SKEL_L_FOOT_TAG,
    SKEL_R_FOOT_TAG,
    SKEL_L_CLAVICLE_TAG,
    SKEL_R_CLAVICLE_TAG,
    SKEL_L_UPPERARM_TAG,
    SKEL_R_UPPERARM_TAG,
    SKEL_L_FOREARM_TAG,
    SKEL_R_FOREARM_TAG,
    SKEL_L_HAND_TAG,
    SKEL_R_HAND_TAG,
    MAX_CUSTOM_PHYSBONES_PER_PED,
    PHYSBONE_PRIORITY_TIERS,
    _PHYSBONE_TIER_BY_KEY,
    _GARMENT_MODIFIER_TOKENS,
    _KEEP_FINAL_S_TOKENS,
    _tokenize_physbone_name,
    _match_tier_tokens,
    score_physbone_chain_priority,
    build_physbone_priority_report_from_chains,
    format_physbone_priority_summary,
    PARENT_BONE_TAGS,
    UNITY_ANCESTOR_TO_GTAV_PARENT,
    resolve_parent_bone_from_unity_chain,
    _chain_parent_map,
    NEKO_MIMI_HALO_WEIGHT_SPLIT,
    MICHAEL_ER_BONE_MAP,
    MICHAEL_ER_CHAIN_SPECS,
    MICHAEL_ER_ROOT_PARENTS,
    MICHAEL_ER_CUSTOM_BONES,
    MICHAEL_ER_PARENT_MAP,
    NEKO_MIMI_BONE_MAP,
    NEKO_MIMI_CHAIN_SPECS,
    NEKO_MIMI_CUSTOM_BONES,
    NEKO_MIMI_PARENT_MAP,
    SHINANO_CASUAL_BONE_MAP,
    SHINANO_CASUAL_CHAIN_SPECS,
    SHINANO_CASUAL_ROOT_PARENTS,
    SHINANO_CASUAL_CUSTOM_BONES,
    SHINANO_CASUAL_PARENT_MAP,
    MILTINA_MAID_BONE_MAP,
    MILTINA_MAID_CHAIN_SPECS,
    MILTINA_MAID_ROOT_PARENTS,
    MILTINA_MAID_CUSTOM_BONES,
    MILTINA_MAID_PARENT_MAP,
    MILTINA_MARSHMALLOW_ONLY_CHAINS,
    CUSTOM_BONE_FLAGS,
    VRCHAT_PHYSBONE_SCRIPT_GUID,
    VRCHAT_PHYSBONE_CLASS_FILE_ID,
    VALID_PHYSBONE_SOURCES,
    DEFAULT_PHYSBONE_PRESET_RELATIVE_PATHS,
    parse_bool_flag,
    _build_marshmallow_pair_presets,
    MARSHMALLOW_PB_AVATAR_PRESETS,
    apply_marshmallow_pb_presets,
    compute_gtav_bone_tag,
    VANILLA_RESERVED_BONE_TAGS,
    resolve_bone_from_mapping,
    resolve_michael_er_gtav_bone,
    resolve_neko_mimi_gtav_bone,
    resolve_shinano_casual_gtav_bone,
    resolve_miltina_maid_gtav_bone,
    )

try:
    from physbone_cfg_ini_layer import (
        parse_vec3_string,
    parse_curve_string,
    format_curve_string,
    evaluate_curve,
    _normalize_gtav_chain_name,
    load_physbone_config,
    build_chain_specs_from_config,
    save_physbone_config,
    _parse_yaml_scalar_vec3,
    _parse_yaml_curve,
    _parse_quat_string,
    _load_ini_chain_records,
    _load_ini_blink_profiles,
    merge_physbone_asi_ini,
    export_physbone_asi_ini,
    _vec_add,
    _vec_sub,
    _vec_scale,
    _vec_dot,
    _vec_len,
    _vec_norm,
    _quat_rotate_vec,
    _quat_mul,
    _quat_from_two_vectors,
    PhysBoneChainSimulator,
    )
except ImportError:
    from common_tools.physbone_cfg_ini_layer import (
        parse_vec3_string,
    parse_curve_string,
    format_curve_string,
    evaluate_curve,
    _normalize_gtav_chain_name,
    load_physbone_config,
    build_chain_specs_from_config,
    save_physbone_config,
    _parse_yaml_scalar_vec3,
    _parse_yaml_curve,
    _parse_quat_string,
    _load_ini_chain_records,
    _load_ini_blink_profiles,
    merge_physbone_asi_ini,
    export_physbone_asi_ini,
    _vec_add,
    _vec_sub,
    _vec_scale,
    _vec_dot,
    _vec_len,
    _vec_norm,
    _quat_rotate_vec,
    _quat_mul,
    _quat_from_two_vectors,
    PhysBoneChainSimulator,
    )

try:
    from physbone_unity_fbx_layer import (
        extract_unity_physbones_from_prefab,
    _parse_unity_yaml_ref,
    _read_unity_meta_guid,
    _inspect_fbx_weights_detailed,
    collect_fbx_weighted_bones,
    prune_orphaned_physbone_chains,
    _UNITY_GUID_CACHE,
    _UNITY_GUID_SCAN_STATE,
    _index_unity_asset_guids,
    _STREAM_PHYSBONE_DOC_CACHE,
    _stream_parse_unity_physbone_doc,
    _parse_marshmallow_asset_file,
    _collect_marshmallow_pb_overrides,
    _collect_linear_spokes,
    )
except ImportError:
    from common_tools.physbone_unity_fbx_layer import (
        extract_unity_physbones_from_prefab,
    _parse_unity_yaml_ref,
    _read_unity_meta_guid,
    _inspect_fbx_weights_detailed,
    collect_fbx_weighted_bones,
    prune_orphaned_physbone_chains,
    _UNITY_GUID_CACHE,
    _UNITY_GUID_SCAN_STATE,
    _index_unity_asset_guids,
    _STREAM_PHYSBONE_DOC_CACHE,
    _stream_parse_unity_physbone_doc,
    _parse_marshmallow_asset_file,
    _collect_marshmallow_pb_overrides,
    _collect_linear_spokes,
    )

try:
    from physbone_scene_extractor_layer import (
        extract_unity_scene_physbones,
    _match_extracted_unity_params,
    )
except ImportError:
    from common_tools.physbone_scene_extractor_layer import (
        extract_unity_scene_physbones,
    _match_extracted_unity_params,
    )

def pack_physbone_chains_to_gtav_budget(
    extracted_spokes: Sequence[Dict[str, Any]],
    gtav_prefix: str = "PB_Auto",
    max_custom_bones: int = MAX_CUSTOM_PHYSBONES_PER_PED,
    template_chain_specs: Optional[Tuple[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]], ...]] = None,
    template_root_parents: Optional[Dict[str, str]] = None,
    template_bone_map: Optional[Dict[str, str]] = None,
    include_marshmallow_pb: bool = False,
    marshmallow_only_chains: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Pack extracted VRChat Unity PhysBone chains safely within GTA V's `<= 63` custom-bone limit.

    When a curated template matches (`>= 4` matching active source bones), populates each chain's
    exact physics parameters directly from Unity (plus optional Marshmallow PB when enabled) while
    preserving the grouped hierarchy. For arbitrary avatars, clusters spoke chains automatically
    within `<= max_custom_bones` with `>= 2` bones per chain and zero ELF tag collisions.
    """
    marsh_only_set = set(marshmallow_only_chains or ())
    if template_chain_specs and template_root_parents and template_bone_map:
        extracted_bone_lows = {
            bone_str.strip().lower()
            for rec in extracted_spokes
            for bone_str in ([rec["root_bone"]] + list(rec.get("spoke_bones", ())) + list(rec.get("all_descendants", ())))
        }
        overlap_count = sum(1 for key_name in template_bone_map if key_name in extracted_bone_lows)
        if overlap_count >= 4:
            chains_out: Dict[str, Dict[str, object]] = {}
            included_gtav_bones: List[str] = []
            excluded_gtav_bones: Set[str] = set()
            for chain_key, gtav_name, src_bones, gtav_bones in template_chain_specs:
                matched = _match_extracted_unity_params(chain_key, src_bones, extracted_spokes)
                if not include_marshmallow_pb and matched is None and (
                    chain_key in marsh_only_set or chain_key.lower().startswith("breast")
                ):
                    excluded_gtav_bones.update(gtav_bones)
                    continue
                parent_bone_name = template_root_parents.get(chain_key, "SKEL_Pelvis")
                parent_bone_tag = PARENT_BONE_TAGS.get(parent_bone_name, SKEL_PELVIS_TAG)
                base_params = matched or {}
                chains_out[chain_key] = {
                    "source_key": chain_key,
                    "gtav_chain_name": gtav_name,
                    "root_bone": gtav_bones[0],
                    "chain_bones": list(gtav_bones),
                    "source_bones": list(src_bones),
                    "parent_bone": parent_bone_name,
                    "parent_bone_tag": int(base_params.get("parent_bone_tag", parent_bone_tag)) if base_params.get("parent_bone") == parent_bone_name else parent_bone_tag,
                    "version": int(base_params.get("version", 1)),
                    "integration_type": int(base_params.get("integration_type", 0)),
                    "multi_child_type": int(base_params.get("multi_child_type", 0)),
                    "endpoint_position": tuple(base_params.get("endpoint_position", (0.0, 0.05, 0.0))),
                    "pull": float(base_params.get("pull", 0.2)),
                    "spring": float(base_params.get("spring", 0.35)),
                    "stiffness": float(base_params.get("stiffness", 0.2)),
                    "gravity": float(base_params.get("gravity", 0.1)),
                    "gravity_falloff": float(base_params.get("gravity_falloff", 0.0)),
                    "immobile_type": int(base_params.get("immobile_type", 0)),
                    "immobile": float(base_params.get("immobile", 0.3)),
                    "allow_collision": int(base_params.get("allow_collision", 1)),
                    "radius": float(base_params.get("radius", 0.025)),
                    "radius_curve": list(base_params.get("radius_curve", [])),
                    "limit_type": int(base_params.get("limit_type", 1)),
                    "max_angle_x": float(base_params.get("max_angle_x", 45.0)),
                    "max_angle_x_curve": list(base_params.get("max_angle_x_curve", [])),
                    "max_angle_z": float(base_params.get("max_angle_z", 45.0)),
                    "limit_rotation": tuple(base_params.get("limit_rotation", (0.0, 0.0, 0.0))),
                    "allow_grabbing": int(base_params.get("allow_grabbing", 1)),
                    "allow_posing": int(base_params.get("allow_posing", 1)),
                    "grab_movement": float(base_params.get("grab_movement", 0.5)),
                    "max_stretch": float(base_params.get("max_stretch", 0.0)),
                    "max_squish": float(base_params.get("max_squish", 0.0)),
                    "stretch_motion": float(base_params.get("stretch_motion", 0.0)),
                    "is_animated": int(base_params.get("is_animated", 1)),
                }
                included_gtav_bones.extend(gtav_bones)
            # Preserve exact casing for bone_mapping keys where available while dropping skipped chains
            bone_map_out = {
                src_k: dst_v
                for src_k, dst_v in template_bone_map.items()
                if dst_v not in excluded_gtav_bones
            }
            priority_report = build_physbone_priority_report_from_chains(
                chains_out,
                discarded_chains=(),
                max_custom_bones=max_custom_bones,
                strategy="unity_template_synced",
            )
            return {
                "chains": chains_out,
                "bone_mapping": bone_map_out,
                "custom_bones": included_gtav_bones,
                "strategy": "unity_template_synced",
                "kept_chains": priority_report["kept_chains"],
                "discarded_chains": [],
                "priority_report": priority_report,
            }

    # General automatic clustering + prioritized RAGE budget packing for arbitrary Unity avatars
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for rec_item in extracted_spokes:
        spokes = rec_item.get("spoke_bones") or [rec_item["root_bone"]]
        root_tok = str(spokes[0]).strip()
        low_tok = root_tok.lower()
        if (
            low_tok.endswith(".l")
            or "_l." in low_tok
            or low_tok.endswith("_l")
            or regex_module.search(r"[._](?:l|left)(?:[._]\d+)+$", low_tok)
        ):
            side_suf = "_L"
        elif (
            low_tok.endswith(".r")
            or "_r." in low_tok
            or low_tok.endswith("_r")
            or regex_module.search(r"[._](?:r|right)(?:[._]\d+)+$", low_tok)
        ):
            side_suf = "_R"
        else:
            side_suf = ""
        if side_suf:
            stem_tok = regex_module.sub(r"(?:[._]\d+)+$", "", root_tok)
            stem_tok = regex_module.sub(
                r"[._](?:[lLrR]|left|right)$", "", stem_tok, flags=regex_module.IGNORECASE
            ).strip("._ ")
        else:
            stem_tok = regex_module.sub(r"[._]?\d+(?:\.\d+)*$", "", root_tok).strip("._ ")
        if not stem_tok:
            stem_tok = root_tok
        group_key = (f"{stem_tok}{side_suf}", rec_item["parent_bone"])
        grouped.setdefault(group_key, []).append(rec_item)

    # Split unsided indexed ring spokes (e.g. Skirt_0 vs Skirt_8) so opposing panels do not merge
    split_grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for (group_stem, parent_bone_name), rec_list in grouped.items():
        if len(rec_list) >= 2 and not group_stem.endswith(("_L", "_R")):
            root_names = [
                str((item_rec.get("spoke_bones") or [item_rec["root_bone"]])[0]).strip()
                for item_rec in rec_list
            ]
            has_zero_ring = any(
                regex_module.search(r"[._]0$", root_nm) is not None for root_nm in root_names
            )
            if has_zero_ring and len(set(root_names)) == len(root_names):
                for item_rec, root_nm in zip(rec_list, root_names):
                    split_grouped[(root_nm, parent_bone_name)] = [item_rec]
                continue
        split_grouped[(group_stem, parent_bone_name)] = rec_list
    grouped = split_grouped

    raw_entries: List[Dict[str, Any]] = []
    pair_lookup: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for (group_stem, parent_bone_name), rec_list in grouped.items():
        rep_rec = rec_list[len(rec_list) // 2]
        rep_spokes = list(rep_rec.get("spoke_bones") or [rep_rec["root_bone"]])
        if group_stem.endswith("_L") or group_stem.endswith("_R"):
            side_tag = group_stem[-1]
            base_stem = group_stem[:-2] or group_stem
        else:
            side_tag = ""
            base_stem = group_stem
        score_info = score_physbone_chain_priority(
            chain_name=group_stem,
            parent_bone_name=parent_bone_name,
            spoke_bones=rep_spokes,
            object_name=str(rep_rec.get("object_name") or ""),
        )
        entry_rec: Dict[str, Any] = {
            "group_stem": group_stem,
            "base_stem": base_stem,
            "side_tag": side_tag,
            "side_order": 0 if side_tag == "L" else (1 if side_tag == "R" else 2),
            "parent_bone": parent_bone_name,
            "rec_list": rec_list,
            "rep_rec": rep_rec,
            "rep_spokes": rep_spokes,
            "score_info": score_info,
            "seg_slots": 2,
        }
        raw_entries.append(entry_rec)
        pair_lookup.setdefault((base_stem.lower(), parent_bone_name), []).append(entry_rec)

    for entry_rec in raw_entries:
        siblings = pair_lookup.get((entry_rec["base_stem"].lower(), entry_rec["parent_bone"]), [])
        sib_sides = {sib["side_tag"] for sib in siblings if sib["side_tag"] in ("L", "R")}
        entry_rec["has_bilateral_pair"] = len(sib_sides) == 2 and entry_rec["side_tag"] in ("L", "R")
        entry_rec["pair_priority"] = max(sib["score_info"]["priority"] for sib in siblings)
        entry_rec["pair_tier"] = min(sib["score_info"]["tier"] for sib in siblings)
        entry_rec["pair_spoke_len"] = max(len(sib["rep_spokes"]) for sib in siblings)
        entry_rec["pair_count"] = max(len(sib["rec_list"]) for sib in siblings)

    sorted_entries = sorted(
        raw_entries,
        key=lambda item_entry: (
            -int(item_entry["pair_priority"]),
            -min(8, int(item_entry["pair_spoke_len"])),
            -int(item_entry["pair_count"]),
            0 if item_entry["parent_bone"] in ("SKEL_Head", "SKEL_Neck_1", "SKEL_Pelvis") else 1,
            item_entry["base_stem"].lower(),
            int(item_entry["side_order"]),
            item_entry["group_stem"].lower(),
        ),
    )

    # Pass 1: Keep essential/highest-priority chains first (pairing .L/.R twins together)
    kept_units: List[List[Dict[str, Any]]] = []
    discarded_entries: List[Tuple[Dict[str, Any], str]] = []
    allocated_bones = 0
    cursor_idx = 0
    total_entries = len(sorted_entries)
    while cursor_idx < total_entries:
        cur_entry = sorted_entries[cursor_idx]
        nxt_entry = sorted_entries[cursor_idx + 1] if (cursor_idx + 1) < total_entries else None
        is_pair_unit = (
            nxt_entry is not None
            and cur_entry["base_stem"].lower() == nxt_entry["base_stem"].lower()
            and cur_entry["parent_bone"] == nxt_entry["parent_bone"]
            and {cur_entry["side_tag"], nxt_entry["side_tag"]} == {"L", "R"}
        )
        is_long_essential = (
            cur_entry["score_info"]["essential"]
            and int(cur_entry["pair_tier"]) <= 2
            and int(cur_entry["pair_spoke_len"]) >= 5
        )
        preferred_slots = 3 if is_long_essential else 2
        if is_pair_unit and nxt_entry is not None:
            pair_min_cost = preferred_slots * 2
            if allocated_bones + pair_min_cost <= max_custom_bones:
                cur_entry["seg_slots"] = preferred_slots
                nxt_entry["seg_slots"] = preferred_slots
                kept_units.append([cur_entry, nxt_entry])
                allocated_bones += pair_min_cost
            elif preferred_slots > 2 and allocated_bones + 4 <= max_custom_bones:
                kept_units.append([cur_entry, nxt_entry])
                allocated_bones += 4
            else:
                discarded_entries.append((cur_entry, "rage_budget_pair_overflow"))
                discarded_entries.append((nxt_entry, "rage_budget_pair_overflow"))
            cursor_idx += 2
        else:
            single_min_cost = preferred_slots
            if allocated_bones + single_min_cost <= max_custom_bones and (
                not discarded_entries or cur_entry["score_info"]["tier"] <= 5
            ):
                cur_entry["seg_slots"] = preferred_slots
                kept_units.append([cur_entry])
                allocated_bones += single_min_cost
            elif (
                preferred_slots > 2
                and allocated_bones + 2 <= max_custom_bones
                and (not discarded_entries or cur_entry["score_info"]["tier"] <= 5)
            ):
                kept_units.append([cur_entry])
                allocated_bones += 2
            else:
                discarded_entries.append((cur_entry, "rage_budget_overflow"))
            cursor_idx += 1

    # Pass 2: Upgrade long high-priority kept chains (up to 4 bones for >=5-spoke chains) with leftover slack
    slack_bones = max(0, int(max_custom_bones) - allocated_bones)
    for max_tier_slots in (3, 4):
        if slack_bones <= 0:
            break
        for unit_items in kept_units:
            if slack_bones <= 0:
                break
            extra_needed = len(unit_items)
            if slack_bones >= extra_needed and all(
                int(item_rec["seg_slots"]) == max_tier_slots - 1
                and len(item_rec["rep_spokes"]) >= (max_tier_slots if max_tier_slots <= 3 else 5)
                for item_rec in unit_items
            ):
                for item_rec in unit_items:
                    item_rec["seg_slots"] = max_tier_slots
                slack_bones -= extra_needed

    kept_flat = [item_rec for unit_items in kept_units for item_rec in unit_items]
    used_tags: Set[int] = set(PARENT_BONE_TAGS.values()) | set(VANILLA_RESERVED_BONE_TAGS)
    chains_out = {}
    bone_map_out: Dict[str, str] = {}
    custom_bones_out: List[str] = []

    for grp_idx, entry_rec in enumerate(kept_flat):
        group_stem = entry_rec["group_stem"]
        parent_bone_name = entry_rec["parent_bone"]
        rec_list = entry_rec["rec_list"]
        rep_rec = entry_rec["rep_rec"]
        rep_spokes = entry_rec["rep_spokes"]
        target_slots = int(entry_rec["seg_slots"])

        if target_slots >= 3 and len(rep_spokes) >= 3:
            sample_count = min(target_slots, len(rep_spokes))
            sampled_src = [
                rep_spokes[round(slot_pos * (len(rep_spokes) - 1) / (sample_count - 1))]
                for slot_pos in range(sample_count)
            ]
        elif len(rep_spokes) >= 2:
            sampled_src = [rep_spokes[0], rep_spokes[-1]]
        else:
            sampled_src = [rep_spokes[0]]

        seg_slots = max(2, len(sampled_src))
        clean_stem = regex_module.sub(r"[^A-Za-z0-9_]+", "", group_stem)[:18] or f"Ch{grp_idx}"
        gtav_chain_name = f"{gtav_prefix}_{clean_stem}"
        candidate_bones = [f"{gtav_chain_name}_{b_idx}" for b_idx in range(seg_slots)]
        # Guarantee zero ELF uint16 hash collisions
        suffix_num = 1
        while any(compute_gtav_bone_tag(bone_nm) in used_tags or bone_nm in custom_bones_out for bone_nm in candidate_bones):
            gtav_chain_name = f"{gtav_prefix}_{clean_stem}_{suffix_num}"
            candidate_bones = [f"{gtav_chain_name}_{b_idx}" for b_idx in range(seg_slots)]
            suffix_num += 1
        for bone_nm in candidate_bones:
            used_tags.add(compute_gtav_bone_tag(bone_nm))
            custom_bones_out.append(bone_nm)

        chain_key = group_stem.lower()
        while chain_key in chains_out:
            chain_key = f"{group_stem.lower()}_{grp_idx}"

        chains_out[chain_key] = {
            "source_key": chain_key,
            "gtav_chain_name": gtav_chain_name,
            "root_bone": candidate_bones[0],
            "chain_bones": candidate_bones,
            "source_bones": sampled_src,
            "parent_bone": parent_bone_name,
            "parent_bone_tag": int(rep_rec.get("parent_bone_tag", PARENT_BONE_TAGS.get(parent_bone_name, SKEL_PELVIS_TAG))),
            "version": int(rep_rec.get("version", 1)),
            "integration_type": int(rep_rec.get("integration_type", 0)),
            "multi_child_type": int(rep_rec.get("multi_child_type", 0)),
            "endpoint_position": tuple(rep_rec.get("endpoint_position", (0.0, 0.05, 0.0))),
            "pull": float(rep_rec.get("pull", 0.2)),
            "spring": float(rep_rec.get("spring", 0.35)),
            "stiffness": float(rep_rec.get("stiffness", 0.2)),
            "gravity": float(rep_rec.get("gravity", 0.1)),
            "gravity_falloff": float(rep_rec.get("gravity_falloff", 0.0)),
            "immobile_type": int(rep_rec.get("immobile_type", 0)),
            "immobile": float(rep_rec.get("immobile", 0.3)),
            "allow_collision": int(rep_rec.get("allow_collision", 1)),
            "radius": float(rep_rec.get("radius", 0.025)),
            "radius_curve": list(rep_rec.get("radius_curve", [])),
            "limit_type": int(rep_rec.get("limit_type", 1)),
            "max_angle_x": float(rep_rec.get("max_angle_x", 45.0)),
            "max_angle_x_curve": list(rep_rec.get("max_angle_x_curve", [])),
            "max_angle_z": float(rep_rec.get("max_angle_z", 45.0)),
            "limit_rotation": tuple(rep_rec.get("limit_rotation", (0.0, 0.0, 0.0))),
            "allow_grabbing": int(rep_rec.get("allow_grabbing", 1)),
            "allow_posing": int(rep_rec.get("allow_posing", 1)),
            "grab_movement": float(rep_rec.get("grab_movement", 0.5)),
            "max_stretch": float(rep_rec.get("max_stretch", 0.0)),
            "max_squish": float(rep_rec.get("max_squish", 0.0)),
            "stretch_motion": float(rep_rec.get("stretch_motion", 0.0)),
            "is_animated": int(rep_rec.get("is_animated", 1)),
        }

        for rec_item in rec_list:
            sp_list = list(rec_item.get("spoke_bones") or [rec_item["root_bone"]])
            for sp_idx, bone_item in enumerate(sp_list):
                mapped_tier = min(
                    seg_slots - 1,
                    int((sp_idx / max(1, len(sp_list) - 1)) * (seg_slots - 1) + 0.5)
                    if len(sp_list) > 1
                    else 0,
                )
                bone_map_out[bone_item.lower()] = candidate_bones[mapped_tier]

    # Bind discarded non-essential PhysBone vertices statically onto their rigid parent_bone
    discarded_report: List[Dict[str, Any]] = []
    for disc_entry, drop_reason in discarded_entries:
        parent_bone_name = disc_entry["parent_bone"]
        score_info = disc_entry["score_info"]
        rec_list = disc_entry["rec_list"]
        rep_rec = disc_entry["rep_rec"]
        rep_spokes = disc_entry["rep_spokes"]
        for rec_item in rec_list:
            bone_names_to_anchor = list(rec_item.get("spoke_bones") or [rec_item["root_bone"]]) + list(
                rec_item.get("all_descendants") or ()
            )
            for bone_item in bone_names_to_anchor:
                bone_low = str(bone_item).strip().lower()
                if bone_low:
                    bone_map_out.setdefault(bone_low, parent_bone_name)
        discarded_report.append(
            {
                "chain_key": disc_entry["group_stem"].lower(),
                "root_bone": str(rep_rec.get("root_bone") or rep_spokes[0]),
                "parent_bone": parent_bone_name,
                "fallback_bone": parent_bone_name,
                "tier": int(score_info["tier"]),
                "tier_key": str(score_info["tier_key"]),
                "priority": int(score_info["priority"]),
                "essential": bool(score_info["essential"]),
                "reason": str(score_info["reason"]),
                "source_bones_count": len(rep_spokes),
                "drop_reason": drop_reason,
            }
        )

    priority_report = build_physbone_priority_report_from_chains(
        chains_out,
        discarded_chains=discarded_report,
        max_custom_bones=max_custom_bones,
        strategy="unity_auto_packed",
    )
    return {
        "chains": chains_out,
        "bone_mapping": bone_map_out,
        "custom_bones": custom_bones_out,
        "strategy": "unity_auto_packed",
        "kept_chains": priority_report["kept_chains"],
        "discarded_chains": priority_report["discarded_chains"],
        "priority_report": priority_report,
    }


def _select_character_physbone_template(
    avatar_id_or_char: str,
) -> Tuple[
    str,
    Optional[Tuple[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]], ...]],
    Optional[Dict[str, str]],
    Optional[Dict[str, str]],
]:
    """Return `(prefix, chain_specs, root_parents, bone_map)` for built-in presets."""
    low_id = str(avatar_id_or_char).strip().lower()
    if low_id in ("shinano_er", "michael", "player_zero"):
        return "PB_ER", MICHAEL_ER_CHAIN_SPECS, MICHAEL_ER_ROOT_PARENTS, MICHAEL_ER_BONE_MAP
    if low_id in ("shinano_casual", "franklin", "player_one"):
        return "PB_SC", SHINANO_CASUAL_CHAIN_SPECS, SHINANO_CASUAL_ROOT_PARENTS, SHINANO_CASUAL_BONE_MAP
    if low_id in ("miltina_maid", "trevor", "player_two"):
        return "PB_MT", MILTINA_MAID_CHAIN_SPECS, MILTINA_MAID_ROOT_PARENTS, MILTINA_MAID_BONE_MAP
    return "PB_Auto", None, None, None


def resolve_character_physbones(
    char_cfg: Dict[str, Any],
    fbx_paths: Sequence[Union[str, Path]] = (),
    character_hints: Sequence[str] = (),
    unity_assets_root: Optional[Union[str, Path]] = None,
    override_source: Optional[str] = None,
    override_cfg_path: Optional[Union[str, Path]] = None,
    override_unity_scene: Optional[Union[str, Path]] = None,
    override_avatar_name: Optional[str] = None,
    override_marshmallow: Optional[bool] = None,
    save_cfg_path: Optional[Union[str, Path]] = None,
    max_custom_bones: int = MAX_CUSTOM_PHYSBONES_PER_PED,
    header_comments: Optional[Sequence[str]] = None,
    override_excluded_meshes: Sequence[str] = (),
    override_active_meshes: Sequence[str] = (),
    prune_orphaned: Optional[bool] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Resolve active character PhysBones from `physbones_source` (`auto | unity | cfg`).

    - `cfg`: load directly from `physbones_cfg` (or fallback built-in template).
    - `unity`: extract directly from `unity_scene` + FBXs and pack <= 63 bones.
    - `auto`: extract from `unity_scene` when configured and present on disk; else load `cfg`.

    Marshmallow PB breast overrides/additions are disabled by default and enabled only when
    `override_marshmallow=True` or `physbones_marshmallow = true` is configured.
    """
    try:
        import vrc2gtav_paths as project_paths
    except ImportError:
        project_paths = None

    requested_source = (
        override_source
        or str(char_cfg.get("physbones_source", "auto") or "auto")
    ).strip().lower()
    if requested_source not in VALID_PHYSBONE_SOURCES:
        raise ValueError(
            f"Unsupported physbones_source {requested_source!r}; expected one of {VALID_PHYSBONE_SOURCES}"
        )

    use_marshmallow = (
        bool(override_marshmallow)
        if override_marshmallow is not None
        else parse_bool_flag(char_cfg.get("physbones_marshmallow", False), default=False)
    )

    effective_cfg = (
        str(override_cfg_path)
        if override_cfg_path
        else str(char_cfg.get("physbones_cfg", "") or "")
    ).strip()
    effective_scene = (
        str(override_unity_scene)
        if override_unity_scene is not None
        else str(char_cfg.get("unity_scene", "") or "")
    ).strip()
    effective_avatar = (
        str(override_avatar_name)
        if override_avatar_name is not None
        else str(char_cfg.get("unity_avatar_name", "") or "")
    ).strip()

    if project_paths is not None:
        if effective_cfg:
            effective_cfg = str(project_paths.to_host_path(effective_cfg))
        if effective_scene:
            effective_scene = str(project_paths.to_host_path(effective_scene))
        if save_cfg_path:
            save_cfg_path = project_paths.to_host_path(str(save_cfg_path))
        if not unity_assets_root:
            try:
                unity_assets_root = project_paths.get_vrc_assets_dir()
            except Exception:
                unity_assets_root = None

    scene_exists = bool(effective_scene) and Path(effective_scene).is_file()
    cfg_exists = bool(effective_cfg) and Path(effective_cfg).is_file()

    avatar_id = str(char_cfg.get("avatar_id") or char_cfg.get("protagonist") or "shinano_er")
    prefix_tok, tmpl_specs, tmpl_parents, tmpl_bmap = _select_character_physbone_template(avatar_id)

    fallback_prefabs: List[Path] = []
    custom_hair_mode = str(char_cfg.get("custom_hair", "") or "").strip().lower()
    if unity_assets_root and custom_hair_mode == "default":
        shin_pref = Path(unity_assets_root) / "Shinano" / "Prefab" / "Shinano.prefab"
        if shin_pref.is_file():
            fallback_prefabs.append(shin_pref)

    candidate_fbxs = list(fbx_paths)
    if not candidate_fbxs:
        for fbx_key in ("source_fbx", "fbx_shinano", "fbx_outfit", "fbx_watch", "fbx_hair"):
            fbx_val = char_cfg.get(fbx_key)
            if fbx_val and fbx_val not in candidate_fbxs:
                candidate_fbxs.append(fbx_val)

    use_unity = requested_source == "unity" or (requested_source == "auto" and scene_exists)
    marsh_only_set = MILTINA_MARSHMALLOW_ONLY_CHAINS if prefix_tok == "PB_MT" else set()
    loaded_data: Dict[str, Any] = {}
    packed_priority_report: Optional[Dict[str, Any]] = None
    orphaned_physbones: List[Dict[str, Any]] = []
    excluded_meshes_used: List[str] = [
        str(mesh_item).strip() for mesh_item in override_excluded_meshes if str(mesh_item).strip()
    ]
    source_used = "builtin"

    if use_unity and scene_exists:
        extracted = extract_unity_scene_physbones(
            effective_scene,
            avatar_name=effective_avatar or None,
            unity_assets_root=unity_assets_root,
            fbx_paths=candidate_fbxs,
            fallback_prefab_paths=fallback_prefabs,
            include_marshmallow_pb=use_marshmallow,
            character_hints=character_hints,
            excluded_meshes=override_excluded_meshes,
            active_meshes=override_active_meshes,
            prune_orphaned=(True if prune_orphaned is None else bool(prune_orphaned)),
            verbose=verbose,
        )
        orphaned_physbones = list(extracted.get("orphaned_physbones") or ())
        if extracted.get("excluded_meshes"):
            excluded_meshes_used = list(extracted["excluded_meshes"])
        if extracted.get("loaded") and extracted.get("chains"):
            packed = pack_physbone_chains_to_gtav_budget(
                extracted["chains"],
                gtav_prefix=prefix_tok,
                max_custom_bones=max_custom_bones,
                template_chain_specs=tmpl_specs,
                template_root_parents=tmpl_parents,
                template_bone_map=tmpl_bmap,
                include_marshmallow_pb=use_marshmallow,
                marshmallow_only_chains=marsh_only_set,
            )
            packed_priority_report = packed.get("priority_report")
            discarded_list = list(packed.get("discarded_chains") or ())
            source_used = "unity"
            default_slot_by_avatar = {
                "shinano_er": "player_zero",
                "shinano_casual": "player_one",
                "miltina_maid": "player_two",
            }
            loaded_data = {
                "metadata": {
                    "avatar": extracted.get("root_name") or effective_avatar or avatar_id,
                    "character": str(char_cfg.get("protagonist") or avatar_id),
                    "slot": str(
                        char_cfg.get("ped_name")
                        or default_slot_by_avatar.get(avatar_id, "player_zero")
                    ),
                    "source": packed.get("strategy", "unity_scene"),
                    "unity_scene": Path(effective_scene).name,
                    "marshmallow_pb": "true" if use_marshmallow else "false",
                    "custom_bones": len(packed["custom_bones"]),
                    "custom_bones_limit": max_custom_bones,
                    "chain_count": len(packed["chains"]),
                    "discarded_non_essential_chains": len(discarded_list),
                    "orphaned_physbones_removed": len(orphaned_physbones),
                },
                "bone_mapping": packed["bone_mapping"],
                "chains": packed["chains"],
            }
            if discarded_list:
                print(f"[PHYSBONES] {format_physbone_priority_summary(packed_priority_report)}")
                if verbose:
                    for disc_item in discarded_list:
                        print(
                            f"  [DROP] {disc_item['chain_key']} -> {disc_item['fallback_bone']} "
                            f"(Tier {disc_item['tier']}, score={disc_item['priority']}, {disc_item['reason']})"
                        )

    if source_used != "unity" and cfg_exists:
        loaded_data = load_physbone_config(effective_cfg)
        source_used = "cfg"
    elif source_used != "unity" and tmpl_specs and tmpl_parents and tmpl_bmap:
        # Keep explicit fallback from builtin template when scene and cfg are both absent
        fallback_chains: Dict[str, Dict[str, object]] = {}
        excluded_fb_bones: Set[str] = set()
        for ck_str, gn_str, sb_tup, gb_tup in tmpl_specs:
            if not use_marshmallow and ck_str in marsh_only_set:
                excluded_fb_bones.update(gb_tup)
                continue
            p_name = tmpl_parents[ck_str]
            fallback_chains[ck_str] = {
                "source_key": ck_str,
                "gtav_chain_name": gn_str,
                "root_bone": gb_tup[0],
                "chain_bones": list(gb_tup),
                "source_bones": list(sb_tup),
                "parent_bone": p_name,
                "parent_bone_tag": PARENT_BONE_TAGS.get(p_name, SKEL_PELVIS_TAG),
            }
        loaded_data = {
            "metadata": {
                "avatar": effective_avatar or avatar_id,
                "source": "builtin",
                "marshmallow_pb": "true" if use_marshmallow else "false",
            },
            "bone_mapping": {
                src_k: dst_v for src_k, dst_v in tmpl_bmap.items() if dst_v not in excluded_fb_bones
            },
            "chains": fallback_chains,
        }
        source_used = "builtin"

    if source_used != "unity" and use_marshmallow and loaded_data.get("chains") is not None:
        apply_marshmallow_pb_presets(loaded_data, avatar_id)
        loaded_data.setdefault("metadata", {})["marshmallow_pb"] = "true"

    if (
        source_used != "unity"
        and loaded_data.get("chains")
        and candidate_fbxs
        and (prune_orphaned is True or bool(override_excluded_meshes) or bool(override_active_meshes))
    ):
        excluded_ci = {
            str(mesh_item).strip().lower()
            for mesh_item in override_excluded_meshes
            if str(mesh_item).strip()
        }
        active_override_ci = {
            str(mesh_item).strip().lower()
            for mesh_item in override_active_meshes
            if str(mesh_item).strip()
        }
        _all_fbx_b, _w_fbx_b, _par_fbx, mesh_w_by_file, fbx_has_skin = _inspect_fbx_weights_detailed(
            candidate_fbxs, excluded_meshes=sorted(excluded_ci)
        )
        if fbx_has_skin:
            active_w_bones: Set[str] = set()
            disabled_w_bones: Set[str] = set()
            for file_mesh_map in mesh_w_by_file.values():
                for mesh_low, weight_set in file_mesh_map.items():
                    is_excluded_mesh = mesh_low in excluded_ci or (
                        bool(active_override_ci) and mesh_low not in active_override_ci
                    )
                    if is_excluded_mesh:
                        disabled_w_bones.update(weight_set)
                    else:
                        active_w_bones.update(weight_set)
            prune_res = prune_orphaned_physbone_chains(
                loaded_data["chains"],
                active_weighted_bones_ci=active_w_bones,
                bone_mapping=loaded_data.get("bone_mapping"),
                disabled_mesh_bones_ci=(disabled_w_bones - active_w_bones),
            )
            if prune_res["orphaned_physbones"]:
                loaded_data["chains"] = prune_res["chains"]
                loaded_data["bone_mapping"] = prune_res["bone_mapping"]
                loaded_data.pop("bone_mapping_ci", None)
                orphaned_physbones.extend(prune_res["orphaned_physbones"])
                if loaded_data.get("metadata") is not None:
                    loaded_data["metadata"]["orphaned_physbones_removed"] = len(orphaned_physbones)

    chain_specs, parent_map, custom_bones, bone_mapping_ci = build_chain_specs_from_config(loaded_data)
    if loaded_data.get("metadata") is not None:
        loaded_data["metadata"]["marshmallow_pb"] = "true" if use_marshmallow else "false"
        loaded_data["metadata"]["chain_count"] = len(chain_specs)
        loaded_data["metadata"]["custom_bones"] = len(custom_bones)
        loaded_data["metadata"]["orphaned_physbones_removed"] = len(orphaned_physbones)
    effective_priority_report = packed_priority_report or build_physbone_priority_report_from_chains(
        loaded_data.get("chains") or {},
        discarded_chains=(),
        max_custom_bones=max_custom_bones,
        strategy=str((loaded_data.get("metadata") or {}).get("source") or source_used),
    )
    effective_headers = header_comments
    if effective_headers is None and (effective_priority_report.get("discarded_chains") or orphaned_physbones):
        auto_headers = [
            "# VRC2GTAV PhysBone Preset - Auto-prioritized & orphan-filtered for RAGE skeleton budget",
            f"# {format_physbone_priority_summary(effective_priority_report)}",
        ]
        for orphan_item in orphaned_physbones:
            auto_headers.append(
                f"#   ORPHANED REMOVED: {orphan_item['root_bone']} ({orphan_item['reason']})"
            )
        for disc_item in effective_priority_report.get("discarded_chains", ()):
            auto_headers.append(
                f"#   DISCARDED [Tier {disc_item['tier']} / {disc_item['priority']}]: "
                f"{disc_item['chain_key']} -> rigid parent {disc_item['fallback_bone']} ({disc_item['reason']})"
            )
        effective_headers = tuple(auto_headers)
    saved_path_str = ""
    if save_cfg_path and loaded_data.get("chains"):
        written = save_physbone_config(
            save_cfg_path,
            loaded_data["chains"],
            metadata=loaded_data.get("metadata"),
            bone_mapping=loaded_data.get("bone_mapping"),
            header_comments=effective_headers,
        )
        saved_path_str = str(written)

    return {
        "source_used": source_used,
        "mode_requested": requested_source,
        "marshmallow_pb": use_marshmallow,
        "chains": loaded_data.get("chains") or {},
        "metadata": loaded_data.get("metadata") or {},
        "bone_mapping": loaded_data.get("bone_mapping") or {},
        "bone_mapping_ci": bone_mapping_ci,
        "chain_specs": chain_specs,
        "parent_map": parent_map,
        "custom_bones": custom_bones,
        "priority_report": effective_priority_report,
        "kept_chains": effective_priority_report["kept_chains"],
        "discarded_chains": effective_priority_report["discarded_chains"],
        "orphaned_physbones": orphaned_physbones,
        "excluded_meshes": excluded_meshes_used,
        "cfg_path": effective_cfg,
        "unity_scene": effective_scene,
        "saved_cfg_path": saved_path_str,
    }


def export_character_physbones_to_cfg(
    character_section: str,
    output_cfg_path: Optional[Union[str, Path]] = None,
    unity_scene_override: Optional[Union[str, Path]] = None,
    avatar_name_override: Optional[str] = None,
    override_marshmallow: Optional[bool] = None,
    preserve_existing_cfg: bool = True,
) -> Optional[Path]:
    """
    Export or synchronize PhysBone chains & bone mappings for a protagonist or avatar preset
    into its `configs/*_physbones.cfg` preset file.
    """
    import vrc2gtav_paths as project_paths

    resolved_avatar_id: Optional[str] = None
    try:
        resolved_avatar_id = project_paths.normalize_avatar_id(character_section)
    except KeyError:
        resolved_avatar_id = None

    if resolved_avatar_id is not None:
        char_cfg = project_paths.get_avatar_paths(resolved_avatar_id)
        avatar_id = resolved_avatar_id
    else:
        char_cfg = project_paths.get_character_paths(character_section)
        avatar_id = str(char_cfg.get("avatar_id") or character_section)

    candidate_fbxs: List[Union[str, Path]] = []
    for fbx_key in ("source_fbx", "fbx_shinano", "fbx_outfit", "fbx_watch", "fbx_hair"):
        fbx_val = char_cfg.get(fbx_key)
        if fbx_val and fbx_val not in candidate_fbxs:
            candidate_fbxs.append(fbx_val)

    target_out = output_cfg_path or char_cfg.get("physbones_cfg")
    if not target_out:
        rel_default = DEFAULT_PHYSBONE_PRESET_RELATIVE_PATHS.get(
            avatar_id
        ) or DEFAULT_PHYSBONE_PRESET_RELATIVE_PATHS.get(character_section)
        if rel_default:
            target_out = project_paths.get_project_root() / rel_default
    if not target_out:
        raise ValueError(f"No physbones_cfg output path configured for {character_section}")

    target_path_obj = Path(project_paths.to_host_path(str(target_out)))
    should_preserve = (
        preserve_existing_cfg
        and target_path_obj.is_file()
        and unity_scene_override is None
    )

    hints_by_avatar = {
        "shinano_casual": ("shinano",),
        "shinano_er": ("shinano", "reunion"),
        "miltina_maid": ("milltina", "miltina"),
        "franklin": ("shinano",),
        "michael": ("shinano", "reunion"),
        "trevor": ("milltina", "miltina"),
    }
    resolved = resolve_character_physbones(
        char_cfg,
        fbx_paths=candidate_fbxs,
        character_hints=hints_by_avatar.get(avatar_id, (character_section,)),
        override_source="cfg" if should_preserve else "unity",
        override_cfg_path=target_path_obj if should_preserve else None,
        override_unity_scene=unity_scene_override,
        override_avatar_name=avatar_name_override,
        override_marshmallow=override_marshmallow,
        save_cfg_path=target_path_obj,
    )
    return Path(resolved["saved_cfg_path"]) if resolved["saved_cfg_path"] else None


def compute_safe_local_limit_axis(
    cur_world_mat: Any,
    next_world_mat: Optional[Any],
    limit_rotation: Tuple[float, float, float],
    limit_type: int,
    node_max_angle_deg: float,
) -> Tuple[float, float, float]:
    """
    Compute `limit_axis_local` aligned to the actual child bone rest direction
    and clamped inside the node's cone limit so idle poses never flare outward.
    """
    import mathutils

    up_vec = mathutils.Vector((0.0, 1.0, 0.0))
    if next_world_mat is not None:
        local_child_vec = cur_world_mat.inverted() @ next_world_mat.translation
        local_child_dir = (
            local_child_vec.normalized()
            if local_child_vec.length > 1e-6
            else up_vec.copy()
        )
    else:
        local_child_dir = up_vec.copy()

    align_quat = up_vec.rotation_difference(local_child_dir)
    limit_euler = mathutils.Euler(
        (
            math.radians(float(limit_rotation[0])),
            math.radians(float(limit_rotation[1])),
            math.radians(float(limit_rotation[2])),
        ),
        "XYZ",
    ).to_quaternion()
    raw_axis = (align_quat @ (limit_euler @ up_vec)).normalized()

    if limit_type > 0 and next_world_mat is not None:
        if node_max_angle_deg <= 2.0:
            max_tilt_deg = 0.0
        else:
            max_tilt_deg = min(
                node_max_angle_deg * 0.78,
                max(0.0, node_max_angle_deg - 5.0),
            )
        ang_rad = local_child_dir.angle(raw_axis, 0.0)
        max_tilt_rad = math.radians(max_tilt_deg)
        if ang_rad > max_tilt_rad and ang_rad > 1e-6:
            if max_tilt_rad <= 1e-6:
                raw_axis = local_child_dir.copy()
            else:
                rot_delta = local_child_dir.rotation_difference(raw_axis)
                clamped_quat = mathutils.Quaternion(rot_delta.axis, max_tilt_rad)
                raw_axis = (clamped_quat @ local_child_dir).normalized()

    return (float(raw_axis.x), float(raw_axis.y), float(raw_axis.z))


def build_dynamic_physbone_chains(
    ped_armature: Any,
    chain_specs: Sequence[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]]],
    parent_map: Dict[str, str],
    chain_cfgs: Dict[str, Dict[str, object]],
    source_world_mat_fn: Callable[[str], Optional[Any]],
    ped_world_matrices: Optional[Dict[str, Any]] = None,
    default_limit_rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    """
    Build articulated PB_* bone injection descriptors and runtime chain records
    supporting multi-armature lookup and automatic 1-bone endpoint synthesis.
    """
    import mathutils

    custom_bones_out: List[Dict[str, object]] = []
    chain_records_out: List[Dict[str, object]] = []

    for chain_key, gtav_chain_name, src_chain_bones, gtav_chain_bones in chain_specs:
        if len(gtav_chain_bones) < 2 or not src_chain_bones:
            continue

        mapped_mats = []
        missing_flag = False
        for src_name in src_chain_bones:
            world_mat = source_world_mat_fn(src_name)
            if world_mat is None:
                missing_flag = True
                break
            mapped_mats.append(world_mat.copy())

        if missing_flag or not mapped_mats:
            continue

        cfg_entry = dict(chain_cfgs.get(chain_key, {}))
        # Synthesize virtual tip matrix when Unity chain has only 1 bone (e.g. Butt.L/R, UN_Bag_Ring)
        while len(mapped_mats) < len(gtav_chain_bones):
            last_mat = mapped_mats[-1]
            end_pt = cfg_entry.get("endpoint_position", (0.0, 0.04, 0.0))
            end_vec = mathutils.Vector(
                (float(end_pt[0]), float(end_pt[1]), float(end_pt[2]))
            )
            if end_vec.length < 0.015:
                end_vec = mathutils.Vector((0.0, 0.035, 0.0))
            # Respect previous world scale (~1.1x) roughly via normalized orientation offset
            world_tip_pos = last_mat.translation + (last_mat.to_3x3().normalized() @ end_vec)
            tip_mat = last_mat.to_3x3().to_4x4()
            tip_mat.translation = world_tip_pos
            mapped_mats.append(tip_mat)

        lim_rot = cfg_entry.get("limit_rotation", default_limit_rotation)
        limit_type = int(cfg_entry.get("limit_type", 1))
        max_angle_curve = cfg_entry.get("max_angle_x_curve", [])
        base_angle_x = float(cfg_entry.get("max_angle_x", 50.0))

        seg_lengths = [
            float((mapped_mats[idx + 1].translation - mapped_mats[idx].translation).length)
            for idx in range(len(mapped_mats) - 1)
        ]
        total_len = sum(seg_lengths) or 1e-6

        root_parent_name = parent_map.get(gtav_chain_bones[0], "SKEL_Pelvis")
        if ped_world_matrices and root_parent_name in ped_world_matrices:
            root_parent_world = ped_world_matrices[root_parent_name]
        else:
            parent_pose = ped_armature.pose.bones.get(root_parent_name)
            root_parent_world = (
                (ped_armature.matrix_world @ parent_pose.matrix)
                if parent_pose is not None
                else mathutils.Matrix.Identity(4)
            )

        parent_world_mat = root_parent_world
        chain_bone_records: List[Dict[str, object]] = []
        cum_len = 0.0
        for node_idx, gtav_bone_name in enumerate(gtav_chain_bones):
            cur_world_mat = mapped_mats[node_idx]
            next_world_mat = (
                mapped_mats[node_idx + 1]
                if node_idx + 1 < len(mapped_mats)
                else None
            )
            parent_name = parent_map.get(
                gtav_bone_name,
                root_parent_name if node_idx == 0 else gtav_chain_bones[node_idx - 1],
            )
            bone_tag = compute_gtav_bone_tag(gtav_bone_name)
            if node_idx < len(seg_lengths):
                seg_len = seg_lengths[node_idx]
            else:
                seg_len = 0.025

            chain_t = min(1.0, max(0.0, cum_len / total_len))
            angle_scale = evaluate_curve(max_angle_curve, chain_t, default_val=1.0)
            node_max_angle = base_angle_x * angle_scale
            lim_axis_vec = compute_safe_local_limit_axis(
                cur_world_mat,
                next_world_mat,
                lim_rot,
                limit_type,
                node_max_angle,
            )

            custom_bones_out.append(
                {
                    "name": gtav_bone_name,
                    "parent_name": parent_name,
                    "tag": bone_tag,
                    "world_matrix": cur_world_mat,
                    "length": max(0.015, float(seg_len)),
                }
            )

            local_mat = parent_world_mat.inverted() @ cur_world_mat
            loc_pos, loc_rot, _unused_scale = local_mat.decompose()
            chain_bone_records.append(
                {
                    "name": gtav_bone_name,
                    "tag": bone_tag,
                    "local_pos": (float(loc_pos.x), float(loc_pos.y), float(loc_pos.z)),
                    "local_rot": (
                        float(loc_rot.x),
                        float(loc_rot.y),
                        float(loc_rot.z),
                        float(loc_rot.w),
                    ),
                    "limit_axis_local": lim_axis_vec,
                }
            )
            if node_idx < len(seg_lengths):
                cum_len += seg_lengths[node_idx]
            parent_world_mat = cur_world_mat

        chain_records_out.append(
            {
                "name": gtav_chain_name,
                "parent_bone_tag": int(
                    cfg_entry.get(
                        "parent_bone_tag",
                        PARENT_BONE_TAGS.get(root_parent_name, SKEL_PELVIS_TAG),
                    )
                ),
                "config": cfg_entry,
                "bones": chain_bone_records,
            }
        )

    return custom_bones_out, chain_records_out


def build_avatar_physbone_chains(
    ped_armature,
    vrc_armature,
    chain_specs: Sequence[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]]],
    parent_map: Dict[str, str],
    cfg_path: Optional[str | Path] = None,
    world_transform_fn: Optional[Callable[[object], object]] = None,
    default_limit_rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    """
    Build articulated PB_* bone injection descriptors and runtime chain records
    for a posed source armature mapped onto ped_armature.
    """
    import mathutils

    loaded_cfg = (
        load_physbone_config(cfg_path)
        if cfg_path and Path(cfg_path).is_file()
        else {"chains": {}}
    )
    chain_cfgs = loaded_cfg.get("chains", {})
    vrc_bones_ci = {pbone.name.lower(): pbone for pbone in vrc_armature.pose.bones}
    identity_mat = mathutils.Matrix.Identity(4)

    custom_bones: List[Dict[str, object]] = []
    chain_records: List[Dict[str, object]] = []

    for chain_key, gtav_chain_name, src_chain_bones, gtav_chain_bones in chain_specs:
        if any(src_name.lower() not in vrc_bones_ci for src_name in src_chain_bones):
            continue
        if len(gtav_chain_bones) < 2:
            continue

        mapped_world_mats: List[mathutils.Matrix] = []
        for src_name in src_chain_bones:
            pose_bone = vrc_bones_ci[src_name.lower()]
            src_world = vrc_armature.matrix_world @ pose_bone.matrix
            tgt_world = world_transform_fn(src_world) if world_transform_fn else src_world.copy()
            mapped_world_mats.append(tgt_world)

        cfg_entry = dict(chain_cfgs.get(chain_key, {}))
        lim_rot = cfg_entry.get("limit_rotation", default_limit_rotation)
        limit_type = int(cfg_entry.get("limit_type", 1))
        max_angle_curve = cfg_entry.get("max_angle_x_curve", [])
        base_angle_x = float(cfg_entry.get("max_angle_x", 50.0))
        seg_lengths = [
            float((mapped_world_mats[idx + 1].translation - mapped_world_mats[idx].translation).length)
            for idx in range(len(mapped_world_mats) - 1)
        ]
        total_len = sum(seg_lengths) or 1e-6

        root_parent_name = parent_map[gtav_chain_bones[0]]
        root_parent_tag = int(
            cfg_entry.get("parent_bone_tag")
            or PARENT_BONE_TAGS.get(root_parent_name, SKEL_HEAD_TAG)
        )
        parent_pose = ped_armature.pose.bones.get(root_parent_name)
        parent_world_mat = (
            (ped_armature.matrix_world @ parent_pose.matrix)
            if parent_pose is not None
            else identity_mat
        )

        chain_bone_records: List[Dict[str, object]] = []
        cur_parent_world = parent_world_mat
        cum_len = 0.0
        for node_idx, gtav_bone_name in enumerate(gtav_chain_bones):
            cur_world_mat = mapped_world_mats[node_idx]
            next_world_mat = (
                mapped_world_mats[node_idx + 1]
                if node_idx + 1 < len(mapped_world_mats)
                else None
            )
            parent_name = parent_map[gtav_bone_name]
            bone_tag = compute_gtav_bone_tag(gtav_bone_name)
            if node_idx < len(seg_lengths):
                seg_len = max(0.015, seg_lengths[node_idx])
            else:
                seg_len = 0.025

            chain_t = min(1.0, max(0.0, cum_len / total_len))
            angle_scale = evaluate_curve(max_angle_curve, chain_t, default_val=1.0)
            node_max_angle = base_angle_x * angle_scale
            lim_axis_tuple = compute_safe_local_limit_axis(
                cur_world_mat,
                next_world_mat,
                lim_rot,
                limit_type,
                node_max_angle,
            )

            custom_bones.append(
                {
                    "name": gtav_bone_name,
                    "parent_name": parent_name,
                    "tag": bone_tag,
                    "world_matrix": cur_world_mat,
                    "length": seg_len,
                }
            )

            local_mat = cur_parent_world.inverted() @ cur_world_mat
            loc_pos, loc_rot, _unused_scale = local_mat.decompose()
            chain_bone_records.append(
                {
                    "name": gtav_bone_name,
                    "tag": bone_tag,
                    "local_pos": (float(loc_pos.x), float(loc_pos.y), float(loc_pos.z)),
                    "local_rot": (float(loc_rot.x), float(loc_rot.y), float(loc_rot.z), float(loc_rot.w)),
                    "limit_axis_local": lim_axis_tuple,
                }
            )
            if node_idx < len(seg_lengths):
                cum_len += seg_lengths[node_idx]
            cur_parent_world = cur_world_mat

        chain_records.append(
            {
                "name": gtav_chain_name,
                "parent_bone_tag": root_parent_tag,
                "config": cfg_entry,
                "bones": chain_bone_records,
            }
        )

    return custom_bones, chain_records
