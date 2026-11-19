#!/usr/bin/env python3
"""
physbone_helper.py
==================
Shared VRChat PhysBone extraction, bone-tag calculation, config I/O,
runtime .ini export, and offline Verlet+cone-limit solver for VRC2GTAV.

Starts with Michael (player_zero) neko mimi articulated ear chains
(ear.L -> PB_Ear_L_0..2, ear.R -> PB_Ear_R_0..2) parented to SKEL_Head.
"""

import collections as collections_module
from configparser import ConfigParser
import math
import os as operating_system
from pathlib import Path
import re as regex_module
import struct
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union
import zlib

_FBX_WEIGHTED_BONES_CACHE: Dict[Tuple[str, int], Tuple[Set[str], Set[str], Dict[str, str]]] = {}


SKEL_HEAD_TAG: int = 31086
SKEL_NECK_1_TAG: int = 39317
SKEL_SPINE0_TAG: int = 23553
SKEL_SPINE1_TAG: int = 24816
SKEL_SPINE2_TAG: int = 24817
SKEL_SPINE3_TAG: int = 24818
SKEL_PELVIS_TAG: int = 11816
SKEL_L_THIGH_TAG: int = 58271
SKEL_R_THIGH_TAG: int = 51826
SKEL_L_CLAVICLE_TAG: int = 64729
SKEL_R_CLAVICLE_TAG: int = 10706
SKEL_L_UPPERARM_TAG: int = 45509
SKEL_R_UPPERARM_TAG: int = 40269

MAX_CUSTOM_PHYSBONES_PER_PED: int = 63

# Ordered VRChat -> GTA V (RAGE) PhysBone prioritization tiers used when a custom
# avatar exceeds RAGE's <= 63 custom bone limit (<= 128 total .ydd skeleton bones).
# Preset avatars that already fit inside the limit keep 100% of their active chains.
PHYSBONE_PRIORITY_TIERS: Tuple[Dict[str, Any], ...] = (
    {
        "tier": 1,
        "key": "essential_ears_and_primary_hair",
        "priority": 100,
        "essential": True,
        "label": "Tier 1 - Iconic Anatomy & Primary Hair (ears, horns, bangs, front/side/back hair, twintails)",
        "keywords": (
            "kemonomimi", "nekomimi", "usagimimi", "kitsunemimi", "mimi",
            "ear", "horn", "antler", "halo",
            "bang", "bangs", "maegami", "yokogami", "ushirogami",
            "twintail", "ponytail", "pigtail", "braid", "osage", "sidetail",
        ),
        "bigrams": (
            ("front", "hair"), ("hair", "front"),
            ("side", "hair"), ("hair", "side"),
            ("back", "hair"), ("hair", "back"),
            ("hair", "base"), ("hair", "top"),
            ("twin", "tail"), ("pony", "tail"), ("side", "tail"),
            ("cat", "ear"), ("fox", "ear"), ("neko", "ear"),
            ("rabbit", "ear"), ("bunny", "ear"), ("wolf", "ear"), ("dog", "ear"),
        ),
        "head_directional_tokens": ("front", "side", "back"),
    },
    {
        "tier": 2,
        "key": "essential_tails_wings_and_skirts",
        "priority": 85,
        "essential": True,
        "label": "Tier 2 - Iconic Silhouette (tails, wings, skirts, dresses, coats, jackets, capes)",
        "keywords": (
            "tail", "shippo", "sipo", "wing", "hane",
            "skirt", "dress", "onepiece", "coat", "jacket", "cardigan", "hoodie",
            "blazer", "parka", "cape", "cloak", "mantle", "hem",
            "hakama", "furisode", "tutu", "petticoat", "capelet", "kimono",
        ),
        "bigrams": (
            ("jacket", "hem"), ("apron", "skirt"), ("coat", "tail"),
        ),
    },
    {
        "tier": 3,
        "key": "important_hair_and_major_garments",
        "priority": 70,
        "essential": True,
        "label": "Tier 3 - Secondary Hair, Sleeves, Scarves & Main Chest",
        "keywords": (
            "hair", "kami", "ahoge", "aho",
            "sleeve", "sode", "cuff", "scarf", "muffler", "shawl", "stole",
            "necktie", "tie", "apron",
            "breast", "oppai", "bust", "mune", "boob", "chest", "marshmallow",
        ),
        "bigrams": (
            ("neck", "tie"), ("collar", "flap"),
        ),
    },
    {
        "tier": 4,
        "key": "medium_ribbons_and_frills",
        "priority": 50,
        "essential": False,
        "label": "Tier 4 - Ribbons, Bows, Frills, Veils & Hat Flaps",
        "keywords": (
            "ribbon", "hrib", "rib", "bow", "frill", "lace", "ruffle",
            "veil", "hood", "hat", "beret", "choker", "collar", "sash", "obi", "flounce",
        ),
        "bigrams": (
            ("hair", "ribbon"), ("tail", "ribbon"), ("skirt", "frill"), ("chest", "bow"),
        ),
    },
    {
        "tier": 5,
        "key": "optional_straps_chains_and_belts",
        "priority": 30,
        "essential": False,
        "label": "Tier 5 - Belts, Straps, Chains, Shoelaces & Suspenders",
        "keywords": (
            "belt", "strap", "suspender", "holster", "cord", "string",
            "shoelace", "garter", "chain", "lanyard", "zipper", "tassel", "buckle",
        ),
        "bigrams": (
            ("waist", "chain"), ("shoe", "lace"), ("thigh", "belt"),
        ),
    },
    {
        "tier": 6,
        "key": "optional_micro_jiggle_and_jewelry",
        "priority": 18,
        "essential": False,
        "label": "Tier 6 - Micro Soft-Body & Jewelry (cheeks, thighs, belly, earrings, necklaces)",
        "keywords": (
            "earring", "earpiece", "pierce", "piercing", "eyelash", "matsuge",
            "cheek", "hoho", "hoppe", "thigh", "hip", "butt", "oshiri",
            "belly", "stomach", "tongue", "shita", "necklace", "pendant",
            "bell", "feather", "antenna",
        ),
        "bigrams": (
            ("ear", "ring"), ("ear", "piece"), ("choker", "bell"),
        ),
    },
    {
        "tier": 7,
        "key": "discardable_props_and_micro_decor",
        "priority": 5,
        "essential": False,
        "label": "Tier 7 - Non-Essential Props & Decor (keychains, bags, pouches, pins, plushies, watches)",
        "keywords": (
            "pouch", "bag", "backpack", "handbag", "keychain", "keyring",
            "hairpin", "hairclip", "plush", "plushie", "mascot", "nuigurumi",
            "badge", "nametag", "tag", "charm", "pin", "brooch", "button",
            "bracelet", "bangle", "pocketwatch", "wristwatch", "watch", "pocket",
            "ring", "coin", "glasses", "goggle", "prop", "deco", "ornament",
            "gimmick", "dummy", "heart", "star", "flower", "candy",
        ),
        "bigrams": (
            ("key", "chain"), ("key", "ring"), ("hair", "pin"), ("hair", "clip"),
            ("pocket", "watch"), ("name", "tag"), ("bag", "charm"),
        ),
    },
)

_PHYSBONE_TIER_BY_KEY: Dict[str, Dict[str, Any]] = {
    tier_cfg["key"]: tier_cfg for tier_cfg in PHYSBONE_PRIORITY_TIERS
}
_GARMENT_MODIFIER_TOKENS: Set[str] = {
    "skirt", "dress", "coat", "cape", "cloak", "mantle", "onepiece", "hakama", "kimono"
}
_KEEP_FINAL_S_TOKENS: Set[str] = {"dress", "hips", "bangs", "glasses"}


def _tokenize_physbone_name(raw_names: Sequence[str]) -> Tuple[List[str], Set[str]]:
    """Split camelCase/delimited PhysBone names into ordered tokens and singularized set."""
    ordered_tokens: List[str] = []
    for raw_item in raw_names:
        if not raw_item:
            continue
        spaced = regex_module.sub(r"([a-z])([A-Z])", r"\1 \2", str(raw_item))
        for tok in regex_module.findall(r"[a-z]+", spaced.lower()):
            ordered_tokens.append(tok)
    token_set: Set[str] = set(ordered_tokens)
    for tok in ordered_tokens:
        if tok not in _KEEP_FINAL_S_TOKENS:
            if len(tok) > 4 and tok.endswith("es") and tok[:-2] in ("pouch", "watch", "brooch"):
                token_set.add(tok[:-2])
            elif len(tok) > 3 and tok.endswith("s"):
                token_set.add(tok[:-1])
    return ordered_tokens, token_set


def _match_tier_tokens(
    tier_cfg: Dict[str, Any],
    ordered_tokens: Sequence[str],
    token_set: Set[str],
) -> Optional[str]:
    """Return matched rule label if ordered tokens / singularized tokens belong to `tier_cfg`."""
    for bg_first, bg_second in tier_cfg.get("bigrams", ()):
        for tok_idx in range(len(ordered_tokens) - 1):
            cur_tok = ordered_tokens[tok_idx]
            nxt_tok = ordered_tokens[tok_idx + 1]
            cur_sing = cur_tok[:-1] if (len(cur_tok) > 3 and cur_tok.endswith("s") and cur_tok not in _KEEP_FINAL_S_TOKENS) else cur_tok
            nxt_sing = nxt_tok[:-1] if (len(nxt_tok) > 3 and nxt_tok.endswith("s") and nxt_tok not in _KEEP_FINAL_S_TOKENS) else nxt_tok
            if bg_first in (cur_tok, cur_sing) and bg_second in (nxt_tok, nxt_sing):
                return f"{bg_first}_{bg_second}"
    for kw_tok in tier_cfg.get("keywords", ()):
        if kw_tok in token_set:
            return kw_tok
    return None


def score_physbone_chain_priority(
    chain_name: str,
    parent_bone_name: str = "SKEL_Pelvis",
    spoke_bones: Sequence[str] = (),
    object_name: str = "",
) -> Dict[str, Any]:
    """
    Classify and score a PhysBone chain according to RAGE prioritization tiers.

    Modifier and non-essential decor rules (Tiers 7, 6, 5, 4) are checked before
    broad anatomical base nouns so items such as `Earring_L`, `HairPin_01`,
    `KeyChain_0`, `PocketWatch`, and `Hair_Ribbon` are not inflated above core
    anatomy (`Ear.L/.R`, `Tail`, `Front_Hair`, `Skirt`).
    """
    raw_candidates = [chain_name, object_name, *list(spoke_bones)[:3]]
    _JEWELRY_OVERRIDES = frozenset(
        {"earring", "earpiece", "pierce", "piercing", "eyelash", "matsuge", "necklace", "pendant"}
    )
    _JEWELRY_BIGRAMS = (("ear", "ring"), ("ear", "piece"))
    ordered_tokens, token_set = _tokenize_physbone_name(raw_candidates)
    matched_tier: Optional[Dict[str, Any]] = None
    matched_rule = ""

    # 1. Props/decor (Tier 7) and earrings/piercings (Tier 6 jewelry) override broad nouns first
    hit_prop = _match_tier_tokens(
        _PHYSBONE_TIER_BY_KEY["discardable_props_and_micro_decor"], ordered_tokens, token_set
    )
    if hit_prop:
        matched_tier = _PHYSBONE_TIER_BY_KEY["discardable_props_and_micro_decor"]
        matched_rule = hit_prop
    else:
        jewelry_hit = None
        for bg_first, bg_second in _JEWELRY_BIGRAMS:
            for tok_idx in range(len(ordered_tokens) - 1):
                if ordered_tokens[tok_idx] == bg_first and ordered_tokens[tok_idx + 1] == bg_second:
                    jewelry_hit = f"{bg_first}_{bg_second}"
                    break
            if jewelry_hit:
                break
        if not jewelry_hit:
            for jw_tok in _JEWELRY_OVERRIDES:
                if jw_tok in token_set:
                    jewelry_hit = jw_tok
                    break
        if jewelry_hit:
            matched_tier = _PHYSBONE_TIER_BY_KEY["optional_micro_jiggle_and_jewelry"]
            matched_rule = jewelry_hit

    if matched_tier is None:
        check_order = (
            "medium_ribbons_and_frills",
            "optional_straps_chains_and_belts",
            "optional_micro_jiggle_and_jewelry",
            "essential_ears_and_primary_hair",
            "essential_tails_wings_and_skirts",
            "important_hair_and_major_garments",
        )
        for tier_key in check_order:
            tier_cfg = _PHYSBONE_TIER_BY_KEY[tier_key]
            hit_rule = _match_tier_tokens(tier_cfg, ordered_tokens, token_set)
            if hit_rule:
                matched_tier = tier_cfg
                matched_rule = hit_rule
                break

    if matched_tier is None:
        head_tier = _PHYSBONE_TIER_BY_KEY["essential_ears_and_primary_hair"]
        if (
            parent_bone_name in ("SKEL_Head", "SKEL_Neck_1")
            and not (token_set & _GARMENT_MODIFIER_TOKENS)
            and (token_set & set(head_tier.get("head_directional_tokens", ())))
        ):
            matched_tier = head_tier
            matched_rule = "head_directional_hair"

    if matched_tier is not None:
        return {
            "tier": int(matched_tier["tier"]),
            "tier_key": str(matched_tier["key"]),
            "priority": int(matched_tier["priority"]),
            "essential": bool(matched_tier["essential"]),
            "reason": f"{matched_tier['key']} ({matched_rule})",
            "matched_rule": matched_rule,
            "label": str(matched_tier["label"]),
        }

    spoke_depth = len(list(spoke_bones))
    if parent_bone_name in ("SKEL_Head", "SKEL_Neck_1") and spoke_depth >= 3:
        return {
            "tier": 4,
            "tier_key": "unclassified_head_strand",
            "priority": 42,
            "essential": False,
            "reason": f"unclassified_head_strand ({parent_bone_name}, {spoke_depth} bones)",
            "matched_rule": "head_strand_depth",
            "label": "Tier 4 - Unclassified Multi-Bone Head Strand",
        }
    if parent_bone_name in ("SKEL_Pelvis", "SKEL_Spine0", "SKEL_Spine1", "SKEL_Spine2", "SKEL_Spine3") and spoke_depth >= 4:
        return {
            "tier": 4,
            "tier_key": "unclassified_major_drape",
            "priority": 38,
            "essential": False,
            "reason": f"unclassified_major_drape ({parent_bone_name}, {spoke_depth} bones)",
            "matched_rule": "torso_drape_depth",
            "label": "Tier 4 - Unclassified Multi-Bone Garment Drape",
        }
    return {
        "tier": 7,
        "tier_key": "unclassified_minor_bone",
        "priority": 12,
        "essential": False,
        "reason": f"unclassified_minor_bone ({parent_bone_name}, {spoke_depth} bones)",
        "matched_rule": "minor_fallback",
        "label": "Tier 7 - Unclassified Minor Accessory Bone",
    }


def build_physbone_priority_report_from_chains(
    chains_map: Dict[str, Dict[str, Any]],
    discarded_chains: Sequence[Dict[str, Any]] = (),
    max_custom_bones: int = MAX_CUSTOM_PHYSBONES_PER_PED,
    strategy: str = "unity_auto_packed",
) -> Dict[str, Any]:
    """Summarize kept vs discarded PhysBone chains ranked by RAGE priority tier."""
    kept_entries: List[Dict[str, Any]] = []
    used_bones = 0
    for chain_key, cfg_data in chains_map.items():
        chain_bones = list(cfg_data.get("chain_bones") or ())
        src_bones = list(cfg_data.get("source_bones") or ())
        parent_bone = str(cfg_data.get("parent_bone") or "SKEL_Pelvis")
        gtav_name = str(cfg_data.get("gtav_chain_name") or chain_key)
        used_bones += len(chain_bones)
        score_info = score_physbone_chain_priority(
            chain_name=f"{chain_key} {gtav_name}",
            parent_bone_name=parent_bone,
            spoke_bones=src_bones,
        )
        kept_entries.append(
            {
                "chain_key": str(chain_key),
                "gtav_chain_name": gtav_name,
                "parent_bone": parent_bone,
                "bones_allocated": len(chain_bones),
                "source_bones_count": len(src_bones),
                "tier": score_info["tier"],
                "tier_key": score_info["tier_key"],
                "priority": score_info["priority"],
                "essential": score_info["essential"],
                "reason": score_info["reason"],
            }
        )
    kept_entries.sort(key=lambda item: (item["tier"], -item["priority"], item["chain_key"]))
    discarded_list = [dict(item) for item in discarded_chains]
    discarded_list.sort(key=lambda item: (item.get("tier", 7), -item.get("priority", 0), str(item.get("chain_key", ""))))
    return {
        "strategy": strategy,
        "max_custom_bones": int(max_custom_bones),
        "used_custom_bones": int(used_bones),
        "within_budget": bool(used_bones <= int(max_custom_bones)),
        "candidate_count": len(kept_entries) + len(discarded_list),
        "kept_count": len(kept_entries),
        "discarded_count": len(discarded_list),
        "kept_chains": kept_entries,
        "discarded_chains": discarded_list,
    }


def format_physbone_priority_summary(
    priority_report: Optional[Dict[str, Any]],
    max_items: int = 12,
) -> str:
    """Format a compact human-readable summary of kept/discarded PhysBone chains."""
    if not priority_report:
        return ""
    used = int(priority_report.get("used_custom_bones", 0))
    limit = int(priority_report.get("max_custom_bones", MAX_CUSTOM_PHYSBONES_PER_PED))
    kept_cnt = int(priority_report.get("kept_count", 0))
    drop_cnt = int(priority_report.get("discarded_count", 0))
    summary = f"PhysBone RAGE budget: kept {kept_cnt} chains ({used}/{limit} custom bones)"
    if drop_cnt <= 0:
        return summary + "; discarded 0 (all within limit)"
    discarded_items = list(priority_report.get("discarded_chains") or ())
    preview_tokens = [
        f"{item.get('chain_key')} [T{item.get('tier', 7)}->{item.get('fallback_bone', 'SKEL_Pelvis')}]"
        for item in discarded_items[:max_items]
    ]
    if len(discarded_items) > max_items:
        preview_tokens.append(f"+{len(discarded_items) - max_items} more")
    return summary + f"; discarded {drop_cnt} non-essential chains bound rigidly: {', '.join(preview_tokens)}"

PARENT_BONE_TAGS: Dict[str, int] = {
    "SKEL_Head": SKEL_HEAD_TAG,
    "SKEL_Neck_1": SKEL_NECK_1_TAG,
    "SKEL_Spine0": SKEL_SPINE0_TAG,
    "SKEL_Spine1": SKEL_SPINE1_TAG,
    "SKEL_Spine2": SKEL_SPINE2_TAG,
    "SKEL_Spine3": SKEL_SPINE3_TAG,
    "SKEL_Pelvis": SKEL_PELVIS_TAG,
    "SKEL_L_Thigh": SKEL_L_THIGH_TAG,
    "SKEL_R_Thigh": SKEL_R_THIGH_TAG,
    "SKEL_L_Clavicle": SKEL_L_CLAVICLE_TAG,
    "SKEL_R_Clavicle": SKEL_R_CLAVICLE_TAG,
    "SKEL_L_UpperArm": SKEL_L_UPPERARM_TAG,
    "SKEL_R_UpperArm": SKEL_R_UPPERARM_TAG,
}

UNITY_ANCESTOR_TO_GTAV_PARENT: Dict[str, str] = {
    "head": "SKEL_Head",
    "hair_root": "SKEL_Head",
    "hair root": "SKEL_Head",
    "un_hatroot": "SKEL_Head",
    "neck": "SKEL_Neck_1",
    "upperchest": "SKEL_Spine3",
    "upper_chest": "SKEL_Spine3",
    "chest": "SKEL_Spine2",
    "ribbon_root": "SKEL_Spine2",
    "ribbonroot": "SKEL_Spine2",
    "spine": "SKEL_Spine1",
    "hips": "SKEL_Pelvis",
    "pelvis": "SKEL_Pelvis",
    "skirt_root": "SKEL_Pelvis",
    "un_skirt": "SKEL_Pelvis",
    "upper_leg.l": "SKEL_L_Thigh",
    "upper_leg_l": "SKEL_L_Thigh",
    "upper_leg.r": "SKEL_R_Thigh",
    "upper_leg_r": "SKEL_R_Thigh",
    "shoulder.l": "SKEL_L_Clavicle",
    "shoulder_l": "SKEL_L_Clavicle",
    "shoulder.r": "SKEL_R_Clavicle",
    "shoulder_r": "SKEL_R_Clavicle",
    "upper_arm.l": "SKEL_L_UpperArm",
    "upper_arm_l": "SKEL_L_UpperArm",
    "upper_arm.r": "SKEL_R_UpperArm",
    "upper_arm_r": "SKEL_R_UpperArm",
}


def resolve_parent_bone_from_unity_chain(ancestor_names: Sequence[str]) -> Tuple[str, int]:
    """Resolve nearest Unity skeleton ancestor name to a GTA V parent bone + uint16 tag."""
    for raw_name in ancestor_names:
        mapped = UNITY_ANCESTOR_TO_GTAV_PARENT.get(str(raw_name).strip().lower())
        if mapped is not None:
            return mapped, PARENT_BONE_TAGS[mapped]
    return "SKEL_Pelvis", SKEL_PELVIS_TAG


def _chain_parent_map(
    chain_specs: Sequence[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]]],
    root_parents: Dict[str, str],
) -> Dict[str, str]:
    parent_map: Dict[str, str] = {}
    for chain_key, _gtav_name, _src_bones, gtav_bones in chain_specs:
        parent_map[gtav_bones[0]] = root_parents[chain_key]
        for bone_idx in range(1, len(gtav_bones)):
            parent_map[gtav_bones[bone_idx]] = gtav_bones[bone_idx - 1]
    return parent_map


# ---------------------------------------------------------------------------
# Michael (Shinano Eternal Reunion - Full Hair + Outfit + Watch; opt-in Marshmallow PB)
# ---------------------------------------------------------------------------
NEKO_MIMI_HALO_WEIGHT_SPLIT: Tuple[Tuple[str, float], ...] = (
    ("PB_Ear_L_0", 0.5),
    ("PB_Ear_L_1", 0.5),
)

MICHAEL_ER_BONE_MAP: Dict[str, str] = {
    "ear.l": "PB_Ear_L_0",
    "ear.l.001": "PB_Ear_L_1",
    "ear.l.002": "PB_Ear_L_2",
    "ear.r": "PB_Ear_R_0",
    "ear.r.001": "PB_Ear_R_1",
    "ear.r.002": "PB_Ear_R_2",
    "halo": "PB_ER_Halo_0",
    "halo.001": "PB_ER_Halo_1",
    "aho": "PB_ER_Aho_0",
    "aho.001": "PB_ER_Aho_0",
    "aho.002": "PB_ER_Aho_0",
    "aho.003": "PB_ER_Aho_0",
    "aho.004": "PB_ER_Aho_1",
    "aho.005": "PB_ER_Aho_1",
    "bangs": "PB_ER_Bang_L_0",
    "bangs.001": "PB_ER_Bang_L_1",
    "bangs.l": "PB_ER_Bang_L_0",
    "bangs.l.001": "PB_ER_Bang_L_1",
    "bangs.l.002": "PB_ER_Bang_L_1",
    "bangs.l.003": "PB_ER_Bang_L_0",
    "bangs.l.004": "PB_ER_Bang_L_1",
    "bangs.r": "PB_ER_Bang_R_0",
    "bangs.r.001": "PB_ER_Bang_R_1",
    "bangs.r.002": "PB_ER_Bang_R_0",
    "bangs.r.003": "PB_ER_Bang_R_1",
    "side.l": "PB_ER_Side_L_0",
    "side.l.001": "PB_ER_Side_L_0",
    "side.l.002": "PB_ER_Side_L_1",
    "side.l.003": "PB_ER_Side_L_1",
    "side.l.004": "PB_ER_Side_L_0",
    "side.l.005": "PB_ER_Side_L_1",
    "side.r": "PB_ER_Side_R_0",
    "side.r.001": "PB_ER_Side_R_0",
    "side.r.002": "PB_ER_Side_R_1",
    "side.r.003": "PB_ER_Side_R_0",
    "side.r.004": "PB_ER_Side_R_1",
    "back.001": "PB_ER_Back_L_0",
    "back.002": "PB_ER_Back_L_1",
    "back.l.001": "PB_ER_Back_L_0",
    "back.l.002": "PB_ER_Back_L_0",
    "back.l.003": "PB_ER_Back_L_1",
    "back.l.004": "PB_ER_Back_L_1",
    "back.l.005": "PB_ER_Back_L_0",
    "back.l.006": "PB_ER_Back_L_1",
    "back.r.001": "PB_ER_Back_R_0",
    "back.r.002": "PB_ER_Back_R_0",
    "back.r.003": "PB_ER_Back_R_0",
    "back.r.004": "PB_ER_Back_R_1",
    "back.r.005": "PB_ER_Back_R_0",
    "back.r.006": "PB_ER_Back_R_1",
    "back.r.007": "PB_ER_Back_R_0",
    "back.r.008": "PB_ER_Back_R_1",
    "back.r.009": "PB_ER_Back_R_0",
    "back.r.010": "PB_ER_Back_R_1",
    "ribbon": "PB_ER_HRib_L_0",
    "ribbon.001": "PB_ER_HRib_L_0",
    "ribbon.002": "PB_ER_HRib_L_1",
    "ribbon.005": "PB_ER_HRib_L_0",
    "ribbon.006": "PB_ER_HRib_L_1",
    "ribbon.003": "PB_ER_HRib_R_0",
    "ribbon.004": "PB_ER_HRib_R_1",
    "ribbon.007": "PB_ER_HRib_R_0",
    "ribbon.008": "PB_ER_HRib_R_1",
    "un_hatroot.001_l": "PB_ER_Hat_L_0",
    "un_hatroot.001_l.001": "PB_ER_Hat_L_1",
    "un_hat_l.001": "PB_ER_Hat_L_0",
    "un_hat_l.002": "PB_ER_Hat_L_0",
    "un_hat_l.003": "PB_ER_Hat_L_0",
    "un_hat_l.004": "PB_ER_Hat_L_1",
    "un_hat_l.005": "PB_ER_Hat_L_1",
    "un_hat_l.006": "PB_ER_Hat_L_1",
    "un_hatroot.001_r": "PB_ER_Hat_R_0",
    "un_hatroot.001_r.001": "PB_ER_Hat_R_1",
    "un_hat_r.001": "PB_ER_Hat_R_0",
    "un_hat_r.002": "PB_ER_Hat_R_0",
    "un_hat_r.003": "PB_ER_Hat_R_0",
    "un_hat_r.004": "PB_ER_Hat_R_1",
    "un_hat_r.005": "PB_ER_Hat_R_1",
    "un_hat_r.006": "PB_ER_Hat_R_1",
    "un_necklace": "PB_ER_Neck_0",
    "un_necklace.001": "PB_ER_Neck_1",
    "un_necklace.002": "PB_ER_Neck_1",
    "breast_1.l": "PB_ER_Breast_L_0",
    "breast_2.l": "PB_ER_Breast_L_1",
    "breast_1.r": "PB_ER_Breast_R_0",
    "breast_2.r": "PB_ER_Breast_R_1",
    "un_ribbon": "PB_ER_Rib_L_0",
    "un_ribbon_l.002": "PB_ER_Rib_L_0",
    "un_ribbon_l.003": "PB_ER_Rib_L_1",
    "un_ribbon.001_l.002": "PB_ER_Rib_L_0",
    "un_ribbon.001_l.003": "PB_ER_Rib_L_1",
    "un_ribbon.001_l.004": "PB_ER_Rib_L_1",
    "un_ribbon2_1_l": "PB_ER_Rib_L_0",
    "un_ribbon2_1_l.001": "PB_ER_Rib_L_1",
    "un_ribbon2_2_l": "PB_ER_Rib_L_0",
    "un_ribbon2_2_l.002": "PB_ER_Rib_L_1",
    "un_ribbon2_2_l.004": "PB_ER_Rib_L_1",
    "un_ribbon_r.002": "PB_ER_Rib_R_0",
    "un_ribbon_r.003": "PB_ER_Rib_R_1",
    "un_ribbon.001_r.002": "PB_ER_Rib_R_0",
    "un_ribbon.001_r.003": "PB_ER_Rib_R_1",
    "un_ribbon.001_r.004": "PB_ER_Rib_R_1",
    "un_ribbon2_1_r": "PB_ER_Rib_R_0",
    "un_ribbon2_1_r.001": "PB_ER_Rib_R_1",
    "un_ribbon2_2_r": "PB_ER_Rib_R_0",
    "un_ribbon2_2_r.002": "PB_ER_Rib_R_1",
    "un_ribbon2_2_r.004": "PB_ER_Rib_R_1",
    "un_bag.001": "PB_ER_Bag_0",
    "un_bag.002": "PB_ER_Bag_0",
    "un_bag_ring": "PB_ER_Bag_0",
    "un_bag": "PB_ER_Bag_0",
    "un_bagchain": "PB_ER_Bag_0",
    "un_bagchain.001": "PB_ER_Bag_0",
    "un_bagchain.002": "PB_ER_Bag_1",
    "un_bagchain.003": "PB_ER_Bag_1",
    "un_bagchain.004": "PB_ER_Bag_1",
    "un_bagchain.005": "PB_ER_Bag_1",
    "un_watchring": "PB_ER_Watch_0",
    "pocket watch_root": "PB_ER_Watch_0",
    "pocket watch_root_1": "PB_ER_Watch_0",
    "pocket watch": "PB_ER_Watch_1",
    "pocket watch_cover": "PB_ER_Watch_1",
    "pocket watch_gear_1": "PB_ER_Watch_1",
    "pocket watch_gear_2": "PB_ER_Watch_1",
    "pocket watch_gear_3": "PB_ER_Watch_1",
    "pocket watch_gear_4": "PB_ER_Watch_1",
    "pocket watch_gear_5": "PB_ER_Watch_1",
    "pocket watch_gear_6": "PB_ER_Watch_1",
    "pocket watch_gear_7": "PB_ER_Watch_1",
    "pocket watch_hourgear": "PB_ER_Watch_1",
    "pocket watch_minutegear": "PB_ER_Watch_1",
    "pocket watch_secondgear": "PB_ER_Watch_1",
    "un_sidechainleft": "PB_ER_Waist_L_0",
    "un_sidechainleft.001": "PB_ER_Waist_L_0",
    "un_sidechainleft.002": "PB_ER_Waist_L_1",
    "un_sidechain": "PB_ER_Waist_R_0",
    "un_sidechain.001": "PB_ER_Waist_R_0",
    "un_sidechain.002": "PB_ER_Waist_R_0",
    "un_sidechain.003": "PB_ER_Waist_R_1",
    "un_sidechain.004": "PB_ER_Waist_R_1",
    "un_sidechain.005": "PB_ER_Waist_R_1",
    "coin": "PB_ER_Waist_R_0",
    "coin.001": "PB_ER_Waist_R_1",
    "un_heartchain": "PB_ER_HeartCh_0",
    "un_heartchain.001": "PB_ER_HeartCh_0",
    "un_heartchain.002": "PB_ER_HeartCh_1",
    "un_heartchain.003": "PB_ER_HeartCh_1",
    "butt.l": "PB_ER_Butt_L_0",
    "butt.r": "PB_ER_Butt_R_0",
}

for _er_side in ("L", "R"):
    _er_low = _er_side.lower()
    for _spoke_idx in range(1, 12):
        _quad_key = "SkirtF" if _spoke_idx <= 5 else "SkirtB"
        MICHAEL_ER_BONE_MAP[f"un_skirt_{_er_low}.{_spoke_idx:02d}"] = f"PB_ER_{_quad_key}{_er_side}_0"
        MICHAEL_ER_BONE_MAP[f"un_skirt_{_er_low}.{_spoke_idx:02d}_001"] = f"PB_ER_{_quad_key}{_er_side}_1"
        MICHAEL_ER_BONE_MAP[f"un_skirt_{_er_low}.{_spoke_idx:02d}_002"] = f"PB_ER_{_quad_key}{_er_side}_1"

MICHAEL_ER_CHAIN_SPECS: Tuple[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]], ...] = (
    ("ear.L", "PB_Ear_L", ("ear.L", "ear.L.001", "ear.L.002"), ("PB_Ear_L_0", "PB_Ear_L_1", "PB_Ear_L_2")),
    ("ear.R", "PB_Ear_R", ("ear.R", "ear.R.001", "ear.R.002"), ("PB_Ear_R_0", "PB_Ear_R_1", "PB_Ear_R_2")),
    ("Halo", "PB_ER_Halo", ("Halo", "Halo.001"), ("PB_ER_Halo_0", "PB_ER_Halo_1")),
    ("Aho", "PB_ER_Aho", ("Aho.002", "Aho.005"), ("PB_ER_Aho_0", "PB_ER_Aho_1")),
    ("Bangs.L", "PB_ER_Bang_L", ("Bangs.L", "Bangs.L.002"), ("PB_ER_Bang_L_0", "PB_ER_Bang_L_1")),
    ("Bangs.R", "PB_ER_Bang_R", ("Bangs.R", "Bangs.R.002"), ("PB_ER_Bang_R_0", "PB_ER_Bang_R_1")),
    ("Side.L", "PB_ER_Side_L", ("Side.L", "Side.L.003"), ("PB_ER_Side_L_0", "PB_ER_Side_L_1")),
    ("Side.R", "PB_ER_Side_R", ("Side.R", "Side.R.003"), ("PB_ER_Side_R_0", "PB_ER_Side_R_1")),
    ("Back.L", "PB_ER_Back_L", ("Back.L.001", "Back.L.004"), ("PB_ER_Back_L_0", "PB_ER_Back_L_1")),
    ("Back.R", "PB_ER_Back_R", ("Back.R.001", "Back.R.006"), ("PB_ER_Back_R_0", "PB_ER_Back_R_1")),
    ("Ribbon.001", "PB_ER_HRib_L", ("Ribbon.001", "Ribbon.002"), ("PB_ER_HRib_L_0", "PB_ER_HRib_L_1")),
    ("Ribbon.003", "PB_ER_HRib_R", ("Ribbon.003", "Ribbon.004"), ("PB_ER_HRib_R_0", "PB_ER_HRib_R_1")),
    ("UN_Hat.L", "PB_ER_Hat_L", ("UN_HatRoot.001_L", "UN_Hat_L.004"), ("PB_ER_Hat_L_0", "PB_ER_Hat_L_1")),
    ("UN_Hat.R", "PB_ER_Hat_R", ("UN_HatRoot.001_R", "UN_Hat_R.004"), ("PB_ER_Hat_R_0", "PB_ER_Hat_R_1")),
    ("UN_Necklace", "PB_ER_Neck", ("UN_Necklace", "UN_Necklace.002"), ("PB_ER_Neck_0", "PB_ER_Neck_1")),
    ("breast.L", "PB_ER_Breast_L", ("Breast_1.L", "Breast_2.L"), ("PB_ER_Breast_L_0", "PB_ER_Breast_L_1")),
    ("breast.R", "PB_ER_Breast_R", ("Breast_1.R", "Breast_2.R"), ("PB_ER_Breast_R_0", "PB_ER_Breast_R_1")),
    ("UN_Ribbon.L", "PB_ER_Rib_L", ("UN_Ribbon_L.002", "UN_Ribbon_L.003"), ("PB_ER_Rib_L_0", "PB_ER_Rib_L_1")),
    ("UN_Ribbon.R", "PB_ER_Rib_R", ("UN_Ribbon_R.002", "UN_Ribbon_R.003"), ("PB_ER_Rib_R_0", "PB_ER_Rib_R_1")),
    ("UN_Bag", "PB_ER_Bag", ("UN_Bag.002", "UN_Bagchain.005"), ("PB_ER_Bag_0", "PB_ER_Bag_1")),
    ("Pocket_Watch", "PB_ER_Watch", ("Pocket Watch_Root", "Pocket Watch"), ("PB_ER_Watch_0", "PB_ER_Watch_1")),
    ("UN_SideChainLeft", "PB_ER_Waist_L", ("UN_SideChainLeft", "UN_SideChainLeft.002"), ("PB_ER_Waist_L_0", "PB_ER_Waist_L_1")),
    ("UN_SideChain", "PB_ER_Waist_R", ("UN_SideChain", "UN_SideChain.004"), ("PB_ER_Waist_R_0", "PB_ER_Waist_R_1")),
    ("UN_HeartChain", "PB_ER_HeartCh", ("UN_HeartChain", "UN_HeartChain.003"), ("PB_ER_HeartCh_0", "PB_ER_HeartCh_1")),
    ("Butt.L", "PB_ER_Butt_L", ("Butt.L",), ("PB_ER_Butt_L_0", "PB_ER_Butt_L_1")),
    ("Butt.R", "PB_ER_Butt_R", ("Butt.R",), ("PB_ER_Butt_R_0", "PB_ER_Butt_R_1")),
    ("UN_SkirtFL", "PB_ER_SkirtFL", ("UN_Skirt_L.02", "UN_Skirt_L.02_002"), ("PB_ER_SkirtFL_0", "PB_ER_SkirtFL_1")),
    ("UN_SkirtFR", "PB_ER_SkirtFR", ("UN_Skirt_R.02", "UN_Skirt_R.02_002"), ("PB_ER_SkirtFR_0", "PB_ER_SkirtFR_1")),
    ("UN_SkirtBL", "PB_ER_SkirtBL", ("UN_Skirt_L.08", "UN_Skirt_L.08_002"), ("PB_ER_SkirtBL_0", "PB_ER_SkirtBL_1")),
    ("UN_SkirtBR", "PB_ER_SkirtBR", ("UN_Skirt_R.08", "UN_Skirt_R.08_002"), ("PB_ER_SkirtBR_0", "PB_ER_SkirtBR_1")),
)

MICHAEL_ER_ROOT_PARENTS: Dict[str, str] = {
    "ear.L": "SKEL_Head",
    "ear.R": "SKEL_Head",
    "Halo": "SKEL_Head",
    "Aho": "SKEL_Head",
    "Bangs.L": "SKEL_Head",
    "Bangs.R": "SKEL_Head",
    "Side.L": "SKEL_Head",
    "Side.R": "SKEL_Head",
    "Back.L": "SKEL_Head",
    "Back.R": "SKEL_Head",
    "Ribbon.001": "SKEL_Head",
    "Ribbon.003": "SKEL_Head",
    "UN_Hat.L": "SKEL_Head",
    "UN_Hat.R": "SKEL_Head",
    "UN_Necklace": "SKEL_Spine2",
    "breast.L": "SKEL_Spine2",
    "breast.R": "SKEL_Spine2",
    "UN_Ribbon.L": "SKEL_Spine2",
    "UN_Ribbon.R": "SKEL_Spine2",
    "UN_Bag": "SKEL_Spine2",
    "Pocket_Watch": "SKEL_Pelvis",
    "UN_SideChainLeft": "SKEL_Pelvis",
    "UN_SideChain": "SKEL_Pelvis",
    "UN_HeartChain": "SKEL_Pelvis",
    "Butt.L": "SKEL_Pelvis",
    "Butt.R": "SKEL_Pelvis",
    "UN_SkirtFL": "SKEL_Pelvis",
    "UN_SkirtFR": "SKEL_Pelvis",
    "UN_SkirtBL": "SKEL_Pelvis",
    "UN_SkirtBR": "SKEL_Pelvis",
}

MICHAEL_ER_CUSTOM_BONES: Tuple[str, ...] = tuple(
    bone_name
    for _key, _gtav_name, _src, gtav_bones in MICHAEL_ER_CHAIN_SPECS
    for bone_name in gtav_bones
)

MICHAEL_ER_PARENT_MAP: Dict[str, str] = _chain_parent_map(
    MICHAEL_ER_CHAIN_SPECS, MICHAEL_ER_ROOT_PARENTS
)

NEKO_MIMI_BONE_MAP: Dict[str, str] = {
    key: val for key, val in MICHAEL_ER_BONE_MAP.items() if val.startswith("PB_Ear_")
}
NEKO_MIMI_CHAIN_SPECS: Tuple[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]], ...] = MICHAEL_ER_CHAIN_SPECS[:2]
NEKO_MIMI_CUSTOM_BONES: Tuple[str, ...] = tuple(
    bone_name for _key, _gtav_name, _src, gtav_bones in NEKO_MIMI_CHAIN_SPECS for bone_name in gtav_bones
)
NEKO_MIMI_PARENT_MAP: Dict[str, str] = _chain_parent_map(
    NEKO_MIMI_CHAIN_SPECS,
    {"ear.L": "SKEL_Head", "ear.R": "SKEL_Head"},
)


# ---------------------------------------------------------------------------
# Franklin (Shinano Casual: Full Ears, Tail, BeltA, BeltB, Ribbons, Hair, Skirt; opt-in Marshmallow PB)
# ---------------------------------------------------------------------------
SHINANO_CASUAL_BONE_MAP: Dict[str, str] = {
    "hair_ear_1.l": "PB_SC_Ear_L_0",
    "hair_ear_2.l": "PB_SC_Ear_L_1",
    "hair_ear_3.l": "PB_SC_Ear_L_2",
    "hair_ear_1.r": "PB_SC_Ear_R_0",
    "hair_ear_2.r": "PB_SC_Ear_R_1",
    "hair_ear_3.r": "PB_SC_Ear_R_2",
    "tail1": "PB_SC_Tail_0",
    "tail2": "PB_SC_Tail_0",
    "tail3": "PB_SC_Tail_1",
    "tail4": "PB_SC_Tail_1",
    "tail5": "PB_SC_Tail_2",
    "tail6": "PB_SC_Tail_2",
    "tail7": "PB_SC_Tail_3",
    "tail8": "PB_SC_Tail_3",
    "belta1": "PB_SC_BeltA_0",
    "belta2": "PB_SC_BeltA_0",
    "belta3": "PB_SC_BeltA_1",
    "beltb1.l": "PB_SC_BeltB_L_0",
    "beltb2.l": "PB_SC_BeltB_L_0",
    "beltb3.l": "PB_SC_BeltB_L_0",
    "beltb4.l": "PB_SC_BeltB_L_0",
    "beltb5.l": "PB_SC_BeltB_L_0",
    "beltb6.l": "PB_SC_BeltB_L_1",
    "beltb7.l": "PB_SC_BeltB_L_1",
    "beltb8.l": "PB_SC_BeltB_L_1",
    "beltb9.l": "PB_SC_BeltB_L_1",
    "beltb10.l": "PB_SC_BeltB_L_1",
    "beltb1.r": "PB_SC_BeltB_R_0",
    "beltb2.r": "PB_SC_BeltB_R_0",
    "beltb3.r": "PB_SC_BeltB_R_0",
    "beltb4.r": "PB_SC_BeltB_R_0",
    "beltb5.r": "PB_SC_BeltB_R_0",
    "beltb6.r": "PB_SC_BeltB_R_1",
    "beltb7.r": "PB_SC_BeltB_R_1",
    "beltb8.r": "PB_SC_BeltB_R_1",
    "beltb9.r": "PB_SC_BeltB_R_1",
    "beltb10.r": "PB_SC_BeltB_R_1",
    "ribbon_a1.l": "PB_SC_Rib_L_0",
    "ribbon_a2.l": "PB_SC_Rib_L_1",
    "ribbon_b1.l": "PB_SC_Rib_L_0",
    "ribbon_b2.l": "PB_SC_Rib_L_1",
    "ribbon_a1.r": "PB_SC_Rib_R_0",
    "ribbon_a2.r": "PB_SC_Rib_R_1",
    "ribbon_b1.r": "PB_SC_Rib_R_0",
    "ribbon_b2.r": "PB_SC_Rib_R_1",
    "hair_ahogea1": "PB_SC_HAho_0",
    "hair_ahogea2": "PB_SC_HAho_0",
    "hair_ahogea3": "PB_SC_HAho_1",
    "hair_ahogeb1": "PB_SC_HAho_0",
    "hair_ahogeb2": "PB_SC_HAho_0",
    "hair_ahogeb3": "PB_SC_HAho_0",
    "hair_ahogeb4": "PB_SC_HAho_1",
    "hair_ahogeb5": "PB_SC_HAho_1",
    "hair_ahogeb6": "PB_SC_HAho_1",
    "hair_fronta1": "PB_SC_HBang_0",
    "hair_fronta2": "PB_SC_HBang_0",
    "hair_fronta3": "PB_SC_HBang_1",
    "hair_frontb1": "PB_SC_HBang_0",
    "hair_frontb2": "PB_SC_HBang_1",
    "hair_frontb3": "PB_SC_HBang_1",
    "hair_frontc1": "PB_SC_HBang_0",
    "hair_frontc2": "PB_SC_HBang_1",
    "hair_sideb1": "PB_SC_HSide_L_0",
    "hair_sideb2": "PB_SC_HSide_L_1",
    "hair_sideb3": "PB_SC_HSide_L_1",
    "hair_sideb4": "PB_SC_HSide_L_2",
    "hair_sideb5": "PB_SC_HSide_L_2",
    "hair_side_ahogea1": "PB_SC_HSide_L_0",
    "hair_side_ahogea2": "PB_SC_HSide_L_1",
    "hair_side_ahogea3": "PB_SC_HSide_L_1",
    "hair_side_ahogea4": "PB_SC_HSide_L_2",
    "hair_side_ahogeb1": "PB_SC_HSide_R_0",
    "hair_side_ahogeb2": "PB_SC_HSide_R_1",
    "hair_side_ahogeb3": "PB_SC_HSide_R_1",
    "hair_side_ahogeb4": "PB_SC_HSide_R_2",
    "hair_sidea1": "PB_SC_HSide_R_0",
    "hair_sidea2": "PB_SC_HSide_R_1",
    "hair_sidea2_sub1": "PB_SC_HSide_R_1",
    "hair_sidea2_sub2": "PB_SC_HSide_R_2",
    "hair_sidea3": "PB_SC_HSide_R_2",
    "hair_sidec1": "PB_SC_HSide_R_0",
    "hair_sidec2": "PB_SC_HSide_R_1",
    "hair_sidec2_sub1": "PB_SC_HSide_R_1",
    "hair_sidec2_sub2": "PB_SC_HSide_R_1",
    "hair_sideb2_subb1.r": "PB_SC_HSide_R_1",
    "hair_sideb2_subb2.r": "PB_SC_HSide_R_1",
    "hair_sidec3": "PB_SC_HSide_R_1",
    "hair_sidec3_sub1": "PB_SC_HSide_R_1",
    "hair_sidec3_sub2": "PB_SC_HSide_R_1",
    "hair_sidec4": "PB_SC_HSide_R_2",
    "hair_sidec4_sub1": "PB_SC_HSide_R_2",
    "hair_sidec4_sub2": "PB_SC_HSide_R_2",
    "hair_sidec5": "PB_SC_HSide_R_2",
    "hair_sidec6": "PB_SC_HSide_R_2",
    "hair_backa1": "PB_SC_HBack_L_0",
    "hair_backa2": "PB_SC_HBack_L_1",
    "hair_backa3": "PB_SC_HBack_L_2",
    "hair_backa4": "PB_SC_HBack_L_2",
    "hair_backb1": "PB_SC_HBack_R_0",
    "hair_backb2": "PB_SC_HBack_R_1",
    "hair_backb3": "PB_SC_HBack_R_2",
    "hair_backd1.l": "PB_SC_HBack_L_0",
    "hair_backc1.l": "PB_SC_HBack_L_0",
    "hair_backe1.l": "PB_SC_HBack_L_0",
    "hair_inside1.l": "PB_SC_HBack_L_0",
    "hair_backd2.l": "PB_SC_HBack_L_1",
    "hair_backc2.l": "PB_SC_HBack_L_1",
    "hair_backe2.l": "PB_SC_HBack_L_1",
    "hair_inside2.l": "PB_SC_HBack_L_1",
    "hair_backd3.l": "PB_SC_HBack_L_2",
    "hair_backd4.l": "PB_SC_HBack_L_2",
    "hair_backc3.l": "PB_SC_HBack_L_2",
    "hair_backc4.l": "PB_SC_HBack_L_2",
    "hair_backe3.l": "PB_SC_HBack_L_2",
    "hair_inside3.l": "PB_SC_HBack_L_2",
    "hair_backd1.r": "PB_SC_HBack_R_0",
    "hair_backc1.r": "PB_SC_HBack_R_0",
    "hair_backe1.r": "PB_SC_HBack_R_0",
    "hair_inside1.r": "PB_SC_HBack_R_0",
    "hair_backd2.r": "PB_SC_HBack_R_1",
    "hair_backc2.r": "PB_SC_HBack_R_1",
    "hair_backe2.r": "PB_SC_HBack_R_1",
    "hair_inside2.r": "PB_SC_HBack_R_1",
    "hair_backd3.r": "PB_SC_HBack_R_2",
    "hair_backd4.r": "PB_SC_HBack_R_2",
    "hair_backc3.r": "PB_SC_HBack_R_2",
    "hair_backc4.r": "PB_SC_HBack_R_2",
    "hair_backe3.r": "PB_SC_HBack_R_2",
    "hair_inside3.r": "PB_SC_HBack_R_2",
    "breast_1.l": "PB_SC_Breast_L_0",
    "breast_2.l": "PB_SC_Breast_L_1",
    "breast_1.r": "PB_SC_Breast_R_0",
    "breast_2.r": "PB_SC_Breast_R_1",
    "butt.l": "PB_SC_Butt_L_0",
    "butt.r": "PB_SC_Butt_R_0",
}

for _side_code in ("L", "R"):
    _side_low = _side_code.lower()
    for _prefix, _grp_code in (("fronta", "SkirtF"), ("frontb", "SkirtF"), ("frontc", "SkirtF"), ("sidea", "SkirtS"), ("sideb", "SkirtS"), ("sidec", "SkirtS"), ("sided", "SkirtS"), ("backa", "SkirtB"), ("backb", "SkirtB")):
        SHINANO_CASUAL_BONE_MAP[f"skirt_{_prefix}1.{_side_low}"] = f"PB_SC_{_grp_code}{_side_code}_0"
        SHINANO_CASUAL_BONE_MAP[f"skirt_{_prefix}2.{_side_low}"] = f"PB_SC_{_grp_code}{_side_code}_1"
        SHINANO_CASUAL_BONE_MAP[f"skirt_{_prefix}3.{_side_low}"] = f"PB_SC_{_grp_code}{_side_code}_2"
        SHINANO_CASUAL_BONE_MAP[f"skirt_{_prefix}4.{_side_low}"] = f"PB_SC_{_grp_code}{_side_code}_2"

SHINANO_CASUAL_CHAIN_SPECS: Tuple[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]], ...] = (
    ("ear.L", "PB_SC_Ear_L", ("Hair_ear_1.L", "Hair_ear_2.L", "Hair_ear_3.L"), ("PB_SC_Ear_L_0", "PB_SC_Ear_L_1", "PB_SC_Ear_L_2")),
    ("ear.R", "PB_SC_Ear_R", ("Hair_ear_1.R", "Hair_ear_2.R", "Hair_ear_3.R"), ("PB_SC_Ear_R_0", "PB_SC_Ear_R_1", "PB_SC_Ear_R_2")),
    ("tail", "PB_SC_Tail", ("Tail1", "Tail3", "Tail5", "Tail7"), ("PB_SC_Tail_0", "PB_SC_Tail_1", "PB_SC_Tail_2", "PB_SC_Tail_3")),
    ("belt_a", "PB_SC_BeltA", ("BeltA1", "BeltA3"), ("PB_SC_BeltA_0", "PB_SC_BeltA_1")),
    ("belt_b.L", "PB_SC_BeltB_L", ("BeltB1.L", "BeltB7.L"), ("PB_SC_BeltB_L_0", "PB_SC_BeltB_L_1")),
    ("belt_b.R", "PB_SC_BeltB_R", ("BeltB1.R", "BeltB7.R"), ("PB_SC_BeltB_R_0", "PB_SC_BeltB_R_1")),
    ("ribbon.L", "PB_SC_Rib_L", ("Ribbon_A1.L", "Ribbon_A2.L"), ("PB_SC_Rib_L_0", "PB_SC_Rib_L_1")),
    ("ribbon.R", "PB_SC_Rib_R", ("Ribbon_A1.R", "Ribbon_A2.R"), ("PB_SC_Rib_R_0", "PB_SC_Rib_R_1")),
    ("hair_ahoge", "PB_SC_HAho", ("Hair_ahogeB1", "Hair_ahogeB5"), ("PB_SC_HAho_0", "PB_SC_HAho_1")),
    ("hair_bang", "PB_SC_HBang", ("Hair_frontB1", "Hair_frontB3"), ("PB_SC_HBang_0", "PB_SC_HBang_1")),
    ("hair_side.L", "PB_SC_HSide_L", ("Hair_sideB1", "Hair_sideB2", "Hair_sideB4"), ("PB_SC_HSide_L_0", "PB_SC_HSide_L_1", "PB_SC_HSide_L_2")),
    ("hair_side.R", "PB_SC_HSide_R", ("Hair_sideC1", "Hair_sideC2", "Hair_sideC4"), ("PB_SC_HSide_R_0", "PB_SC_HSide_R_1", "PB_SC_HSide_R_2")),
    ("hair_back.L", "PB_SC_HBack_L", ("Hair_backD1.L", "Hair_backD2.L", "Hair_backD3.L"), ("PB_SC_HBack_L_0", "PB_SC_HBack_L_1", "PB_SC_HBack_L_2")),
    ("hair_back.R", "PB_SC_HBack_R", ("Hair_backD1.R", "Hair_backD2.R", "Hair_backD3.R"), ("PB_SC_HBack_R_0", "PB_SC_HBack_R_1", "PB_SC_HBack_R_2")),
    ("breast.L", "PB_SC_Breast_L", ("Breast_1.L", "Breast_2.L"), ("PB_SC_Breast_L_0", "PB_SC_Breast_L_1")),
    ("breast.R", "PB_SC_Breast_R", ("Breast_1.R", "Breast_2.R"), ("PB_SC_Breast_R_0", "PB_SC_Breast_R_1")),
    ("butt.L", "PB_SC_Butt_L", ("Butt.L",), ("PB_SC_Butt_L_0", "PB_SC_Butt_L_1")),
    ("butt.R", "PB_SC_Butt_R", ("Butt.R",), ("PB_SC_Butt_R_0", "PB_SC_Butt_R_1")),
    ("skirt_front.L", "PB_SC_SkirtFL", ("Skirt_FrontB1.L", "Skirt_FrontB2.L", "Skirt_FrontB4.L"), ("PB_SC_SkirtFL_0", "PB_SC_SkirtFL_1", "PB_SC_SkirtFL_2")),
    ("skirt_front.R", "PB_SC_SkirtFR", ("Skirt_FrontB1.R", "Skirt_FrontB2.R", "Skirt_FrontB4.R"), ("PB_SC_SkirtFR_0", "PB_SC_SkirtFR_1", "PB_SC_SkirtFR_2")),
    ("skirt_side.L", "PB_SC_SkirtSL", ("Skirt_SideB1.L", "Skirt_SideB2.L", "Skirt_SideB4.L"), ("PB_SC_SkirtSL_0", "PB_SC_SkirtSL_1", "PB_SC_SkirtSL_2")),
    ("skirt_side.R", "PB_SC_SkirtSR", ("Skirt_SideB1.R", "Skirt_SideB2.R", "Skirt_SideB4.R"), ("PB_SC_SkirtSR_0", "PB_SC_SkirtSR_1", "PB_SC_SkirtSR_2")),
    ("skirt_back.L", "PB_SC_SkirtBL", ("Skirt_BackB1.L", "Skirt_BackB2.L", "Skirt_BackB4.L"), ("PB_SC_SkirtBL_0", "PB_SC_SkirtBL_1", "PB_SC_SkirtBL_2")),
    ("skirt_back.R", "PB_SC_SkirtBR", ("Skirt_BackB1.R", "Skirt_BackB2.R", "Skirt_BackB4.R"), ("PB_SC_SkirtBR_0", "PB_SC_SkirtBR_1", "PB_SC_SkirtBR_2")),
)

SHINANO_CASUAL_ROOT_PARENTS: Dict[str, str] = {
    "ear.L": "SKEL_Head",
    "ear.R": "SKEL_Head",
    "tail": "SKEL_Pelvis",
    "belt_a": "SKEL_Spine2",
    "belt_b.L": "SKEL_Spine2",
    "belt_b.R": "SKEL_Spine2",
    "ribbon.L": "SKEL_Spine2",
    "ribbon.R": "SKEL_Spine2",
    "hair_ahoge": "SKEL_Head",
    "hair_bang": "SKEL_Head",
    "hair_side.L": "SKEL_Head",
    "hair_side.R": "SKEL_Head",
    "hair_back.L": "SKEL_Head",
    "hair_back.R": "SKEL_Head",
    "breast.L": "SKEL_Spine2",
    "breast.R": "SKEL_Spine2",
    "butt.L": "SKEL_Pelvis",
    "butt.R": "SKEL_Pelvis",
    "skirt_front.L": "SKEL_Pelvis",
    "skirt_front.R": "SKEL_Pelvis",
    "skirt_side.L": "SKEL_Pelvis",
    "skirt_side.R": "SKEL_Pelvis",
    "skirt_back.L": "SKEL_Pelvis",
    "skirt_back.R": "SKEL_Pelvis",
}

SHINANO_CASUAL_CUSTOM_BONES: Tuple[str, ...] = tuple(
    bone_name
    for _key, _gtav_name, _src, gtav_bones in SHINANO_CASUAL_CHAIN_SPECS
    for bone_name in gtav_bones
)

SHINANO_CASUAL_PARENT_MAP: Dict[str, str] = _chain_parent_map(
    SHINANO_CASUAL_CHAIN_SPECS, SHINANO_CASUAL_ROOT_PARENTS
)


# ---------------------------------------------------------------------------
# Trevor (Miltina Maid: Full Twintails 1&2, Front/Side Hair, Ears, Breasts, Ruffles, Ribbons, Butt, 7-Sector Skirt, Tail)
# ---------------------------------------------------------------------------
MILTINA_MAID_BONE_MAP: Dict[str, str] = {
    "cow ear_l.001": "PB_MT_Ear_L_0",
    "cow ear_l.002": "PB_MT_Ear_L_1",
    "cow ear_r.001": "PB_MT_Ear_R_0",
    "cow ear_r.002": "PB_MT_Ear_R_1",
    "front hair.001": "PB_MT_HFnt_0",
    "front hair.002": "PB_MT_HFnt_0",
    "front hair.003": "PB_MT_HFnt_1",
    "breast_l": "PB_MT_Breast_L_0",
    "breast_l.001": "PB_MT_Breast_L_1",
    "breast_l.002": "PB_MT_Breast_L_1",
    "breast_r": "PB_MT_Breast_R_0",
    "breast_r.001": "PB_MT_Breast_R_1",
    "breast_r.002": "PB_MT_Breast_R_1",
    "butt_l": "PB_MT_Butt_L_0",
    "butt_l.001": "PB_MT_Butt_L_1",
    "butt_r": "PB_MT_Butt_R_0",
    "butt_r.001": "PB_MT_Butt_R_1",
    "tail.001": "PB_MT_Tail_0",
    "tail.002": "PB_MT_Tail_0",
    "tail.003": "PB_MT_Tail_1",
    "tail.004": "PB_MT_Tail_1",
    "tail.005": "PB_MT_Tail_2",
    "tail.006": "PB_MT_Tail_2",
    "tail.007": "PB_MT_Tail_2",
    "tail.008": "PB_MT_Tail_3",
    "tail.009": "PB_MT_Tail_3",
}

for _side_code in ("L", "R"):
    _side_low = _side_code.lower()
    MILTINA_MAID_BONE_MAP[f"twin tail1_{_side_low}.001"] = f"PB_MT_Twin1_{_side_code}_0"
    MILTINA_MAID_BONE_MAP[f"twin tail1_{_side_low}.002"] = f"PB_MT_Twin1_{_side_code}_1"
    MILTINA_MAID_BONE_MAP[f"twin tail1_{_side_low}.003"] = f"PB_MT_Twin1_{_side_code}_2"
    MILTINA_MAID_BONE_MAP[f"twin tail1_{_side_low}.004"] = f"PB_MT_Twin1_{_side_code}_2"
    MILTINA_MAID_BONE_MAP[f"twin tail2_{_side_low}.001"] = f"PB_MT_Twin2_{_side_code}_0"
    MILTINA_MAID_BONE_MAP[f"twin tail2_{_side_low}.002"] = f"PB_MT_Twin2_{_side_code}_1"
    MILTINA_MAID_BONE_MAP[f"twin tail2_{_side_low}.003"] = f"PB_MT_Twin2_{_side_code}_2"
    MILTINA_MAID_BONE_MAP[f"twin tail2_{_side_low}.004"] = f"PB_MT_Twin2_{_side_code}_2"
    for _rib_grp in ("a1", "a2"):
        MILTINA_MAID_BONE_MAP[f"twin tail ribbon{_rib_grp}_{_side_low}.001"] = f"PB_MT_Twin1_{_side_code}_0"
        MILTINA_MAID_BONE_MAP[f"twin tail ribbon{_rib_grp}_{_side_low}.002"] = f"PB_MT_Twin1_{_side_code}_1"
        MILTINA_MAID_BONE_MAP[f"twin tail ribbon{_rib_grp}_{_side_low}.003"] = f"PB_MT_Twin1_{_side_code}_1"
    for _rib_grp in ("b1", "b2"):
        MILTINA_MAID_BONE_MAP[f"twin tail ribbon{_rib_grp}_{_side_low}.001"] = f"PB_MT_Twin2_{_side_code}_0"
        MILTINA_MAID_BONE_MAP[f"twin tail ribbon{_rib_grp}_{_side_low}.002"] = f"PB_MT_Twin2_{_side_code}_1"
        MILTINA_MAID_BONE_MAP[f"twin tail ribbon{_rib_grp}_{_side_low}.003"] = f"PB_MT_Twin2_{_side_code}_1"
    MILTINA_MAID_BONE_MAP[f"front hair3_{_side_low}.001"] = f"PB_MT_Side_{_side_code}_0"
    MILTINA_MAID_BONE_MAP[f"front hair3_{_side_low}.002"] = f"PB_MT_Side_{_side_code}_0"
    MILTINA_MAID_BONE_MAP[f"front hair3_{_side_low}.003"] = f"PB_MT_Side_{_side_code}_1"
    MILTINA_MAID_BONE_MAP[f"front hair3_{_side_low}.004"] = f"PB_MT_Side_{_side_code}_1"
    for _ruffle_num in range(1, 7):
        MILTINA_MAID_BONE_MAP[f"ruffle_{_side_low}.00{_ruffle_num}"] = f"PB_MT_Ruffle_{_side_code}_0"
        MILTINA_MAID_BONE_MAP[f"ruffle_{_side_low}.00{_ruffle_num}_end"] = f"PB_MT_Ruffle_{_side_code}_1"
    MILTINA_MAID_BONE_MAP[f"ribbona_{_side_low}.001"] = f"PB_MT_NRib_{_side_code}_0"
    MILTINA_MAID_BONE_MAP[f"ribbona_{_side_low}.002"] = f"PB_MT_NRib_{_side_code}_1"
    MILTINA_MAID_BONE_MAP[f"ribbonb_{_side_low}.001"] = f"PB_MT_NRib_{_side_code}_0"
    MILTINA_MAID_BONE_MAP[f"ribbonb_{_side_low}.002"] = f"PB_MT_NRib_{_side_code}_1"
    MILTINA_MAID_BONE_MAP[f"ribbonb_{_side_low}.003"] = f"PB_MT_NRib_{_side_code}_1"
    MILTINA_MAID_BONE_MAP[f"apron ribbona_{_side_low}.001"] = f"PB_MT_Apron_{_side_code}_0"
    MILTINA_MAID_BONE_MAP[f"apron ribbon_{_side_low}.001"] = f"PB_MT_Apron_{_side_code}_0"
    MILTINA_MAID_BONE_MAP[f"apron ribbon_{_side_low}.002"] = f"PB_MT_Apron_{_side_code}_1"
    MILTINA_MAID_BONE_MAP[f"apron ribbon_{_side_low}.003"] = f"PB_MT_Apron_{_side_code}_1"
    MILTINA_MAID_BONE_MAP[f"apron ribbon_{_side_low}.004"] = f"PB_MT_Apron_{_side_code}_2"
    MILTINA_MAID_BONE_MAP[f"apron ribbon_{_side_low}.005"] = f"PB_MT_Apron_{_side_code}_2"
    for _idx_num, _grp_code in ((1, "SkirtF"), (2, "SkirtF"), (3, "SkirtS"), (4, "SkirtS"), (5, "SkirtB"), (6, "SkirtB")):
        for _seg in range(1, 9):
            _tier = 0 if _seg <= 4 else 1
            MILTINA_MAID_BONE_MAP[f"skirt{_idx_num}_{_side_low}.00{_seg}"] = f"PB_MT_{_grp_code}{_side_code}_{_tier}"

for _seg7 in range(1, 9):
    MILTINA_MAID_BONE_MAP[f"skirt7.00{_seg7}"] = f"PB_MT_SkirtBC_{0 if _seg7 <= 4 else 1}"

MILTINA_MAID_CHAIN_SPECS: Tuple[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]], ...] = (
    ("twintail1.L", "PB_MT_Twin1_L", ("twin tail1_L.001", "twin tail1_L.002", "twin tail1_L.004"), ("PB_MT_Twin1_L_0", "PB_MT_Twin1_L_1", "PB_MT_Twin1_L_2")),
    ("twintail1.R", "PB_MT_Twin1_R", ("twin tail1_R.001", "twin tail1_R.002", "twin tail1_R.004"), ("PB_MT_Twin1_R_0", "PB_MT_Twin1_R_1", "PB_MT_Twin1_R_2")),
    ("twintail2.L", "PB_MT_Twin2_L", ("twin tail2_L.001", "twin tail2_L.002", "twin tail2_L.004"), ("PB_MT_Twin2_L_0", "PB_MT_Twin2_L_1", "PB_MT_Twin2_L_2")),
    ("twintail2.R", "PB_MT_Twin2_R", ("twin tail2_R.001", "twin tail2_R.002", "twin tail2_R.004"), ("PB_MT_Twin2_R_0", "PB_MT_Twin2_R_1", "PB_MT_Twin2_R_2")),
    ("hair_front", "PB_MT_HFnt", ("Front hair.001", "Front hair.003"), ("PB_MT_HFnt_0", "PB_MT_HFnt_1")),
    ("hair_side.L", "PB_MT_Side_L", ("Front hair3_L.001", "Front hair3_L.004"), ("PB_MT_Side_L_0", "PB_MT_Side_L_1")),
    ("hair_side.R", "PB_MT_Side_R", ("Front hair3_R.001", "Front hair3_R.004"), ("PB_MT_Side_R_0", "PB_MT_Side_R_1")),
    ("ear.L", "PB_MT_Ear_L", ("Cow ear_L.001", "Cow ear_L.002"), ("PB_MT_Ear_L_0", "PB_MT_Ear_L_1")),
    ("ear.R", "PB_MT_Ear_R", ("Cow ear_R.001", "Cow ear_R.002"), ("PB_MT_Ear_R_0", "PB_MT_Ear_R_1")),
    ("breast.L", "PB_MT_Breast_L", ("Breast_L", "Breast_L.001"), ("PB_MT_Breast_L_0", "PB_MT_Breast_L_1")),
    ("breast.R", "PB_MT_Breast_R", ("Breast_R", "Breast_R.001"), ("PB_MT_Breast_R_0", "PB_MT_Breast_R_1")),
    ("ruffle.L", "PB_MT_Ruffle_L", ("Ruffle_L.003", "Ruffle_L.003_end"), ("PB_MT_Ruffle_L_0", "PB_MT_Ruffle_L_1")),
    ("ruffle.R", "PB_MT_Ruffle_R", ("Ruffle_R.003", "Ruffle_R.003_end"), ("PB_MT_Ruffle_R_0", "PB_MT_Ruffle_R_1")),
    ("neck_ribbon.L", "PB_MT_NRib_L", ("RibbonB_L.001", "RibbonB_L.002"), ("PB_MT_NRib_L_0", "PB_MT_NRib_L_1")),
    ("neck_ribbon.R", "PB_MT_NRib_R", ("RibbonB_R.001", "RibbonB_R.002"), ("PB_MT_NRib_R_0", "PB_MT_NRib_R_1")),
    ("apron_ribbon.L", "PB_MT_Apron_L", ("apron ribbon_L.001", "apron ribbon_L.002", "apron ribbon_L.004"), ("PB_MT_Apron_L_0", "PB_MT_Apron_L_1", "PB_MT_Apron_L_2")),
    ("apron_ribbon.R", "PB_MT_Apron_R", ("apron ribbon_R.001", "apron ribbon_R.002", "apron ribbon_R.004"), ("PB_MT_Apron_R_0", "PB_MT_Apron_R_1", "PB_MT_Apron_R_2")),
    ("butt.L", "PB_MT_Butt_L", ("Butt_L", "Butt_L.001"), ("PB_MT_Butt_L_0", "PB_MT_Butt_L_1")),
    ("butt.R", "PB_MT_Butt_R", ("Butt_R", "Butt_R.001"), ("PB_MT_Butt_R_0", "PB_MT_Butt_R_1")),
    ("skirt_front.L", "PB_MT_SkirtFL", ("skirt1_L.002", "skirt1_L.006"), ("PB_MT_SkirtFL_0", "PB_MT_SkirtFL_1")),
    ("skirt_front.R", "PB_MT_SkirtFR", ("skirt1_R.002", "skirt1_R.006"), ("PB_MT_SkirtFR_0", "PB_MT_SkirtFR_1")),
    ("skirt_side.L", "PB_MT_SkirtSL", ("skirt3_L.002", "skirt3_L.006"), ("PB_MT_SkirtSL_0", "PB_MT_SkirtSL_1")),
    ("skirt_side.R", "PB_MT_SkirtSR", ("skirt3_R.002", "skirt3_R.006"), ("PB_MT_SkirtSR_0", "PB_MT_SkirtSR_1")),
    ("skirt_back.L", "PB_MT_SkirtBL", ("skirt5_L.002", "skirt5_L.006"), ("PB_MT_SkirtBL_0", "PB_MT_SkirtBL_1")),
    ("skirt_back.R", "PB_MT_SkirtBR", ("skirt5_R.002", "skirt5_R.006"), ("PB_MT_SkirtBR_0", "PB_MT_SkirtBR_1")),
    ("skirt_back.C", "PB_MT_SkirtBC", ("skirt7.002", "skirt7.006"), ("PB_MT_SkirtBC_0", "PB_MT_SkirtBC_1")),
    ("tail", "PB_MT_Tail", ("tail.001", "tail.003", "tail.005", "tail.008"), ("PB_MT_Tail_0", "PB_MT_Tail_1", "PB_MT_Tail_2", "PB_MT_Tail_3")),
)

MILTINA_MAID_ROOT_PARENTS: Dict[str, str] = {
    "twintail1.L": "SKEL_Head",
    "twintail1.R": "SKEL_Head",
    "twintail2.L": "SKEL_Head",
    "twintail2.R": "SKEL_Head",
    "hair_front": "SKEL_Head",
    "hair_side.L": "SKEL_Head",
    "hair_side.R": "SKEL_Head",
    "ear.L": "SKEL_Head",
    "ear.R": "SKEL_Head",
    "breast.L": "SKEL_Spine2",
    "breast.R": "SKEL_Spine2",
    "ruffle.L": "SKEL_Spine2",
    "ruffle.R": "SKEL_Spine2",
    "neck_ribbon.L": "SKEL_Spine2",
    "neck_ribbon.R": "SKEL_Spine2",
    "apron_ribbon.L": "SKEL_Pelvis",
    "apron_ribbon.R": "SKEL_Pelvis",
    "butt.L": "SKEL_Pelvis",
    "butt.R": "SKEL_Pelvis",
    "skirt_front.L": "SKEL_Pelvis",
    "skirt_front.R": "SKEL_Pelvis",
    "skirt_side.L": "SKEL_Pelvis",
    "skirt_side.R": "SKEL_Pelvis",
    "skirt_back.L": "SKEL_Pelvis",
    "skirt_back.R": "SKEL_Pelvis",
    "skirt_back.C": "SKEL_Pelvis",
    "tail": "SKEL_Pelvis",
}

MILTINA_MAID_CUSTOM_BONES: Tuple[str, ...] = tuple(
    bone_name
    for _key, _gtav_name, _src, gtav_bones in MILTINA_MAID_CHAIN_SPECS
    for bone_name in gtav_bones
)

MILTINA_MAID_PARENT_MAP: Dict[str, str] = _chain_parent_map(
    MILTINA_MAID_CHAIN_SPECS, MILTINA_MAID_ROOT_PARENTS
)

# Miltina natively has no breast VRCPhysBone; breast.L/R exist only when Marshmallow PB is enabled.
MILTINA_MARSHMALLOW_ONLY_CHAINS: Set[str] = {"breast.L", "breast.R"}

CUSTOM_BONE_FLAGS: Tuple[str, ...] = (
    "RotX",
    "RotY",
    "RotZ",
    "TransX",
    "TransY",
    "TransZ",
)

VRCHAT_PHYSBONE_SCRIPT_GUID: str = "2a2c05204084d904aa4945ccff20d8e5"
VRCHAT_PHYSBONE_CLASS_FILE_ID: str = "1661641543"
VALID_PHYSBONE_SOURCES: Tuple[str, ...] = ("auto", "unity", "cfg")

DEFAULT_PHYSBONE_PRESET_RELATIVE_PATHS: Dict[str, str] = {
    "shinano_er": "configs/michael_neko_mimi_physbones.cfg",
    "shinano_casual": "configs/shinano_casual_physbones.cfg",
    "miltina_maid": "configs/miltina_maid_physbones.cfg",
    "michael": "configs/michael_neko_mimi_physbones.cfg",
    "franklin": "configs/shinano_casual_physbones.cfg",
    "trevor": "configs/miltina_maid_physbones.cfg",
}


def parse_bool_flag(raw_value: Any, default: bool = False) -> bool:
    """Parse boolean flag values from INI strings, integers, or Python bools."""
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, (int, float)):
        return bool(raw_value)
    token = str(raw_value).strip().lower()
    if not token:
        return default
    if token in ("1", "true", "yes", "on", "sim"):
        return True
    if token in ("0", "false", "no", "off", "nao"):
        return False
    return default


def _build_marshmallow_pair_presets(
    gtav_prefix: str,
    src_left: Tuple[str, str],
    src_right: Tuple[str, str],
    bone_map_extra: Dict[str, str],
    physics_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Construct symmetric L/R Marshmallow PB breast overlay chains for offline cfg/builtin use."""
    chains_map: Dict[str, Dict[str, Any]] = {}
    for side_code, src_pair in (("L", src_left), ("R", src_right)):
        chain_key = f"breast.{side_code}"
        gtav_name = f"{gtav_prefix}_Breast_{side_code}"
        gtav_bones = [f"{gtav_name}_0", f"{gtav_name}_1"]
        chain_entry: Dict[str, Any] = {
            "source_key": chain_key,
            "gtav_chain_name": gtav_name,
            "root_bone": gtav_bones[0],
            "chain_bones": gtav_bones,
            "source_bones": list(src_pair),
            "parent_bone": "SKEL_Spine2",
            "parent_bone_tag": SKEL_SPINE2_TAG,
            "version": 1,
            "integration_type": 0,
            "multi_child_type": 0,
            "endpoint_position": (0.0, 0.08, 0.0),
            "gravity_falloff": 1.0,
            "allow_collision": 1,
            "radius": 0.06,
            "radius_curve": [],
            "limit_type": 1,
            "max_angle_x": 35.0,
            "max_angle_x_curve": [],
            "max_angle_z": 45.0,
            "limit_rotation": (-10.0, 0.0, 0.0),
            "allow_grabbing": 1,
            "allow_posing": 0,
            "grab_movement": 0.1,
            "max_stretch": 0.3,
            "max_squish": 0.6,
            "is_animated": 1,
        }
        chain_entry.update(physics_params)
        chains_map[chain_key] = chain_entry
    return {"chains": chains_map, "bone_mapping": dict(bone_map_extra)}


MARSHMALLOW_PB_AVATAR_PRESETS: Dict[str, Dict[str, Any]] = {
    "shinano_casual": _build_marshmallow_pair_presets(
        "PB_SC",
        ("Breast_1.L", "Breast_2.L"),
        ("Breast_1.R", "Breast_2.R"),
        {
            "breast_1.l": "PB_SC_Breast_L_0",
            "breast_2.l": "PB_SC_Breast_L_1",
            "breast_1.r": "PB_SC_Breast_R_0",
            "breast_2.r": "PB_SC_Breast_R_1",
        },
        {
            "pull": 0.04,
            "spring": 1.0,
            "stiffness": 0.05,
            "gravity": 0.25,
            "immobile_type": 0,
            "immobile": 0.6,
            "stretch_motion": 0.75,
        },
    ),
    "shinano_er": _build_marshmallow_pair_presets(
        "PB_ER",
        ("Breast_1.L", "Breast_2.L"),
        ("Breast_1.R", "Breast_2.R"),
        {
            "breast_1.l": "PB_ER_Breast_L_0",
            "breast_2.l": "PB_ER_Breast_L_1",
            "breast_1.r": "PB_ER_Breast_R_0",
            "breast_2.r": "PB_ER_Breast_R_1",
        },
        {
            "pull": 0.05,
            "spring": 1.0,
            "stiffness": 0.05,
            "gravity": 0.25,
            "immobile_type": 0,
            "immobile": 0.75,
            "stretch_motion": 0.6,
        },
    ),
    "miltina_maid": _build_marshmallow_pair_presets(
        "PB_MT",
        ("Breast_L", "Breast_L.001"),
        ("Breast_R", "Breast_R.001"),
        {
            "breast_l": "PB_MT_Breast_L_0",
            "breast_l.001": "PB_MT_Breast_L_1",
            "breast_l.002": "PB_MT_Breast_L_1",
            "breast_r": "PB_MT_Breast_R_0",
            "breast_r.001": "PB_MT_Breast_R_1",
            "breast_r.002": "PB_MT_Breast_R_1",
        },
        {
            "pull": 0.08,
            "spring": 0.5,
            "stiffness": 0.25,
            "gravity": 0.3,
            "immobile_type": 1,
            "immobile": 0.5,
            "stretch_motion": 0.5,
        },
    ),
}


def apply_marshmallow_pb_presets(
    loaded_data: Dict[str, Any],
    avatar_id_or_char: str,
) -> Dict[str, Any]:
    """Overlay opt-in Marshmallow PB breast presets onto a resolved PhysBones config dict."""
    preset_key = str(avatar_id_or_char).strip().lower()
    if preset_key == "franklin":
        preset_key = "shinano_casual"
    elif preset_key == "michael":
        preset_key = "shinano_er"
    elif preset_key in ("trevor", "milltina", "miltina"):
        preset_key = "miltina_maid"

    overlay = MARSHMALLOW_PB_AVATAR_PRESETS.get(preset_key)
    if not overlay:
        return loaded_data

    chains_map = dict(loaded_data.get("chains") or {})
    bone_map = dict(loaded_data.get("bone_mapping") or {})
    bone_map_ci = dict(loaded_data.get("bone_mapping_ci") or {})
    for src_bone, dst_bone in overlay["bone_mapping"].items():
        bone_map[src_bone] = dst_bone
        bone_map_ci[src_bone.strip().lower()] = dst_bone
    for chain_key, chain_cfg in overlay["chains"].items():
        chains_map[chain_key] = dict(chain_cfg)

    loaded_data["chains"] = chains_map
    loaded_data["bone_mapping"] = bone_map
    loaded_data["bone_mapping_ci"] = bone_map_ci
    return loaded_data


def compute_gtav_bone_tag(bone_name: str) -> int:
    """Compute the deterministic uint16 ELF bone tag used by Sollumz and RAGE."""
    hash_val = 0
    for char_str in str.upper(bone_name):
        hash_val = (hash_val << 4) + ord(char_str)
        high_bits = hash_val & 0xF0000000
        if high_bits != 0:
            hash_val ^= high_bits >> 24
        hash_val &= ~high_bits
    return (hash_val % 0xFE8F) + 0x170


def resolve_bone_from_mapping(
    raw_group_name: str,
    bone_mapping_ci: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Resolve a lowercase vertex group name through a dynamic bone_mapping dict."""
    if not bone_mapping_ci:
        return None
    return bone_mapping_ci.get(str(raw_group_name).strip().lower())


def resolve_michael_er_gtav_bone(
    raw_group_name: str,
    mesh_name: Optional[str] = None,
    bone_mapping_ci: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Map a Shinano Eternal Reunion + hair bone name to its PB_Ear_* or PB_ER_* bone."""
    _ = mesh_name
    lowered_name = raw_group_name.strip().lower()
    if bone_mapping_ci is not None and lowered_name in bone_mapping_ci:
        return bone_mapping_ci[lowered_name]
    return MICHAEL_ER_BONE_MAP.get(lowered_name)


def resolve_neko_mimi_gtav_bone(raw_group_name: str) -> Optional[str]:
    """Map an ear.* Blender vertex group name to its PB_Ear_* GTA V bone."""
    lowered_name = raw_group_name.strip().lower()
    return NEKO_MIMI_BONE_MAP.get(lowered_name)


def resolve_shinano_casual_gtav_bone(
    raw_group_name: str,
    mesh_name: Optional[str] = None,
    bone_mapping_ci: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Map a Shinano Casual Blender vertex group name to its PB_SC_* GTA V bone."""
    lowered_name = raw_group_name.strip().lower()
    if bone_mapping_ci is not None and lowered_name in bone_mapping_ci:
        return bone_mapping_ci[lowered_name]
    return SHINANO_CASUAL_BONE_MAP.get(lowered_name)


def resolve_miltina_maid_gtav_bone(
    raw_group_name: str,
    mesh_name: Optional[str] = None,
    bone_mapping_ci: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Map a Miltina Maid Blender vertex group name to its PB_MT_* GTA V bone."""
    lowered_name = raw_group_name.strip().lower()
    if bone_mapping_ci is not None and lowered_name in bone_mapping_ci:
        return bone_mapping_ci[lowered_name]
    return MILTINA_MAID_BONE_MAP.get(lowered_name)


def parse_vec3_string(raw_text: str, default_val: Tuple[float, float, float] = (0.0, 0.0, 0.0)) -> Tuple[float, float, float]:
    """Parse a comma-separated 3D vector string into a float tuple."""
    parts = [item.strip() for item in raw_text.split(",") if item.strip()]
    if len(parts) != 3:
        return default_val
    return (float(parts[0]), float(parts[1]), float(parts[2]))


def parse_curve_string(raw_text: str) -> List[Tuple[float, float]]:
    """Parse 't:v, t:v' curve points into sorted (time, value) tuples."""
    points: List[Tuple[float, float]] = []
    for token in raw_text.split(","):
        cleaned = token.strip()
        if ":" not in cleaned:
            continue
        left_part, right_part = cleaned.split(":", 1)
        points.append((float(left_part.strip()), float(right_part.strip())))
    points.sort(key=lambda pair_item: pair_item[0])
    return points


def format_curve_string(points: Sequence[Tuple[float, float]]) -> str:
    """Serialize curve points into 't:v, t:v' config notation."""
    return ", ".join(f"{point_time:.7g}:{point_val:.7g}" for point_time, point_val in points)


def evaluate_curve(points: Sequence[Tuple[float, float]], param_t: float, default_val: float = 1.0) -> float:
    """Evaluate a piecewise-linear normalized Unity curve at param_t in [0, 1]."""
    if not points:
        return default_val
    clamped_t = max(0.0, min(1.0, float(param_t)))
    if len(points) == 1 or clamped_t <= points[0][0]:
        return float(points[0][1])
    if clamped_t >= points[-1][0]:
        return float(points[-1][1])
    for idx in range(len(points) - 1):
        left_t, left_val = points[idx]
        right_t, right_val = points[idx + 1]
        if left_t <= clamped_t <= right_t:
            span = right_t - left_t
            if span <= 1e-8:
                return float(right_val)
            frac = (clamped_t - left_t) / span
            return float(left_val + (right_val - left_val) * frac)
    return float(points[-1][1])


def _normalize_gtav_chain_name(raw_name: str, fallback_prefix: str = "PB_Chain", index_num: int = 0) -> str:
    """Sanitize a chain section name into a valid GTA V PB_* identifier."""
    cleaned = regex_module.sub(r"[^A-Za-z0-9_]+", "_", str(raw_name).strip()).strip("_")
    if not cleaned:
        cleaned = f"{fallback_prefix}_{index_num}"
    if not cleaned.upper().startswith("PB_"):
        cleaned = f"PB_{cleaned}"
    return cleaned[:48]


def load_physbone_config(cfg_path: Union[str, Path]) -> Dict[str, Any]:
    """Load character PhysBone configuration from an INI-style .cfg file."""
    resolved_path = Path(cfg_path)
    if not resolved_path.is_file():
        raise FileNotFoundError(f"PhysBone config not found: {resolved_path}")

    parser = ConfigParser()
    parser.optionxform = str
    with resolved_path.open("r", encoding="utf-8-sig") as cfg_file:
        parser.read_file(cfg_file)

    metadata = dict(parser["metadata"]) if parser.has_section("metadata") else {}
    bone_mapping = dict(parser["bone_mapping"]) if parser.has_section("bone_mapping") else {}
    bone_mapping_ci = {
        str(src_name).strip().lower(): str(dst_name).strip()
        for src_name, dst_name in bone_mapping.items()
        if str(src_name).strip() and str(dst_name).strip()
    }

    chains: Dict[str, Dict[str, object]] = {}
    for section_name in parser.sections():
        if not section_name.startswith("chain."):
            continue
        chain_key = section_name[len("chain.") :]
        sec = parser[section_name]
        chain_bones = [item.strip() for item in sec.get("chain_bones", "").split(",") if item.strip()]
        source_bones = [item.strip() for item in sec.get("source_bones", "").split(",") if item.strip()]
        parent_bone_name = sec.get("parent_bone", "SKEL_Head").strip() or "SKEL_Head"
        default_parent_tag = PARENT_BONE_TAGS.get(parent_bone_name, SKEL_HEAD_TAG)
        gtav_chain_name = sec.get("gtav_chain_name", "").strip()
        if not gtav_chain_name and chain_bones:
            first_gtav = chain_bones[0]
            if first_gtav.endswith("_0"):
                gtav_chain_name = first_gtav[:-2]
            else:
                gtav_chain_name = _normalize_gtav_chain_name(chain_key)
        chains[chain_key] = {
            "source_key": chain_key,
            "gtav_chain_name": gtav_chain_name or _normalize_gtav_chain_name(chain_key),
            "root_bone": sec.get("root_bone", chain_bones[0] if chain_bones else ""),
            "chain_bones": chain_bones,
            "source_bones": source_bones,
            "parent_bone": parent_bone_name,
            "parent_bone_tag": sec.getint("parent_bone_tag", default_parent_tag),
            "version": sec.getint("version", 1),
            "integration_type": sec.getint("integration_type", 0),
            "multi_child_type": sec.getint("multi_child_type", 0),
            "endpoint_position": parse_vec3_string(sec.get("endpoint_position", "0, 0, 0")),
            "pull": sec.getfloat("pull", 0.2),
            "spring": sec.getfloat("spring", 0.35),
            "stiffness": sec.getfloat("stiffness", 0.2),
            "gravity": sec.getfloat("gravity", 0.0),
            "gravity_falloff": sec.getfloat("gravity_falloff", 0.0),
            "immobile_type": sec.getint("immobile_type", 0),
            "immobile": sec.getfloat("immobile", 0.3),
            "allow_collision": sec.getint("allow_collision", 1),
            "radius": sec.getfloat("radius", 0.025),
            "radius_curve": parse_curve_string(sec.get("radius_curve", "")),
            "limit_type": sec.getint("limit_type", 1),
            "max_angle_x": sec.getfloat("max_angle_x", 50.0),
            "max_angle_x_curve": parse_curve_string(sec.get("max_angle_x_curve", "0.0:1.0, 1.0:0.6")),
            "max_angle_z": sec.getfloat("max_angle_z", 45.0),
            "limit_rotation": parse_vec3_string(sec.get("limit_rotation", "0.0, 0.0, 0.0")),
            "allow_grabbing": sec.getint("allow_grabbing", 1),
            "allow_posing": sec.getint("allow_posing", 1),
            "grab_movement": sec.getfloat("grab_movement", 0.5),
            "max_stretch": sec.getfloat("max_stretch", 0.0),
            "max_squish": sec.getfloat("max_squish", 0.0),
            "stretch_motion": sec.getfloat("stretch_motion", 0.0),
            "is_animated": sec.getint("is_animated", 1),
        }

    return {
        "metadata": metadata,
        "bone_mapping": bone_mapping,
        "bone_mapping_ci": bone_mapping_ci,
        "chains": chains,
    }


def build_chain_specs_from_config(
    loaded_cfg: Dict[str, Any],
) -> Tuple[
    Tuple[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]], ...],
    Dict[str, str],
    Tuple[str, ...],
    Dict[str, str],
]:
    """Derive chain_specs, parent_map, custom_bones, and bone_mapping_ci dynamically from loaded .cfg."""
    chains = loaded_cfg.get("chains") or {}
    specs_list: List[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]]] = []
    root_parents: Dict[str, str] = {}
    for chain_idx, (chain_key, chain_data) in enumerate(chains.items()):
        gtav_bones = tuple(
            str(bone_item).strip()
            for bone_item in (chain_data.get("chain_bones") or [])
            if str(bone_item).strip()
        )
        src_bones = tuple(
            str(bone_item).strip()
            for bone_item in (chain_data.get("source_bones") or [])
            if str(bone_item).strip()
        )
        if len(gtav_bones) < 2 or not src_bones:
            continue
        gtav_chain_name = str(chain_data.get("gtav_chain_name") or "").strip()
        if not gtav_chain_name:
            first_name = gtav_bones[0]
            gtav_chain_name = (
                first_name[:-2]
                if first_name.endswith("_0")
                else _normalize_gtav_chain_name(chain_key, index_num=chain_idx)
            )
        parent_name = str(chain_data.get("parent_bone") or "SKEL_Pelvis").strip() or "SKEL_Pelvis"
        specs_list.append((chain_key, gtav_chain_name, src_bones, gtav_bones))
        root_parents[chain_key] = parent_name

    chain_specs = tuple(specs_list)
    parent_map = _chain_parent_map(chain_specs, root_parents)
    custom_bones = tuple(bone_name for _ck, _gn, _sb, gbs in chain_specs for bone_name in gbs)
    bone_mapping_ci = dict(loaded_cfg.get("bone_mapping_ci") or {})
    if not bone_mapping_ci:
        bone_mapping_ci = {
            str(src_name).strip().lower(): str(dst_name).strip()
            for src_name, dst_name in (loaded_cfg.get("bone_mapping") or {}).items()
            if str(src_name).strip() and str(dst_name).strip()
        }
    return chain_specs, parent_map, custom_bones, bone_mapping_ci


def save_physbone_config(
    cfg_path: Union[str, Path],
    chain_configs: Dict[str, Dict[str, object]],
    metadata: Optional[Dict[str, object]] = None,
    bone_mapping: Optional[Dict[str, str]] = None,
    header_comments: Optional[Sequence[str]] = None,
) -> Path:
    """Write PhysBone parameters and bone mappings to an INI-style .cfg file."""
    resolved_path = Path(cfg_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = list(
        header_comments
        if header_comments
        else ("# VRC2GTAV PhysBone Preset - Auto-generated/verified character PhysBones",)
    )
    lines.extend(["", "[metadata]"])
    meta_dict = metadata or {
        "avatar": "Shinano Eternal Reunion",
        "character": "michael",
        "slot": "player_zero",
        "target_mesh": "Ears",
        "parent_bone": "SKEL_Head",
        "parent_bone_tag": SKEL_HEAD_TAG,
    }
    for meta_key, meta_val in meta_dict.items():
        lines.append(f"{meta_key} = {meta_val}")

    lines.extend(["", "[bone_mapping]"])
    map_dict = bone_mapping or dict(MICHAEL_ER_BONE_MAP)
    for src_name, dst_name in map_dict.items():
        lines.append(f"{src_name} = {dst_name}")

    for chain_key, cfg_data in chain_configs.items():
        lines.extend(["", f"[chain.{chain_key}]"])
        if cfg_data.get("gtav_chain_name"):
            lines.append(f"gtav_chain_name = {cfg_data['gtav_chain_name']}")
        lines.append(f"root_bone = {cfg_data.get('root_bone', '')}")
        lines.append(f"chain_bones = {', '.join(cfg_data.get('chain_bones', []))}")
        lines.append(f"source_bones = {', '.join(cfg_data.get('source_bones', []))}")
        parent_bone = str(cfg_data.get("parent_bone", "SKEL_Head"))
        parent_tag = int(cfg_data.get("parent_bone_tag", PARENT_BONE_TAGS.get(parent_bone, SKEL_HEAD_TAG)))
        lines.append(f"parent_bone = {parent_bone}")
        lines.append(f"parent_bone_tag = {parent_tag}")
        lines.append(f"component_guid = {VRCHAT_PHYSBONE_SCRIPT_GUID}")
        lines.append(f"version = {int(cfg_data.get('version', 1))}")
        lines.append(f"integration_type = {int(cfg_data.get('integration_type', 0))}")
        lines.append(f"multi_child_type = {int(cfg_data.get('multi_child_type', 0))}")
        end_pt = cfg_data.get("endpoint_position", (0.0, 0.0, 0.0))
        lines.append(f"endpoint_position = {end_pt[0]}, {end_pt[1]}, {end_pt[2]}")
        for scalar_key in ("pull", "spring", "stiffness", "gravity", "gravity_falloff"):
            lines.append(f"{scalar_key} = {float(cfg_data.get(scalar_key, 0.0))}")
        lines.append(f"immobile_type = {int(cfg_data.get('immobile_type', 0))}")
        lines.append(f"immobile = {float(cfg_data.get('immobile', 0.0))}")
        lines.append(f"allow_collision = {int(cfg_data.get('allow_collision', 1))}")
        lines.append(f"radius = {float(cfg_data.get('radius', 0.025))}")
        lines.append(f"radius_curve = {format_curve_string(cfg_data.get('radius_curve', []))}")
        lines.append(f"limit_type = {int(cfg_data.get('limit_type', 1))}")
        lines.append(f"max_angle_x = {float(cfg_data.get('max_angle_x', 50.0))}")
        lines.append(f"max_angle_x_curve = {format_curve_string(cfg_data.get('max_angle_x_curve', []))}")
        lines.append(f"max_angle_z = {float(cfg_data.get('max_angle_z', 45.0))}")
        lim_rot = cfg_data.get("limit_rotation", (0.0, 0.0, 0.0))
        lines.append(f"limit_rotation = {lim_rot[0]}, {lim_rot[1]}, {lim_rot[2]}")
        lines.append(f"allow_grabbing = {int(cfg_data.get('allow_grabbing', 1))}")
        lines.append(f"allow_posing = {int(cfg_data.get('allow_posing', 1))}")
        lines.append(f"grab_movement = {float(cfg_data.get('grab_movement', 0.5))}")
        lines.append(f"max_stretch = {float(cfg_data.get('max_stretch', 0.0))}")
        lines.append(f"max_squish = {float(cfg_data.get('max_squish', 0.0))}")
        lines.append(f"stretch_motion = {float(cfg_data.get('stretch_motion', 0.0))}")
        lines.append(f"is_animated = {int(cfg_data.get('is_animated', 1))}")

    resolved_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return resolved_path


def _parse_yaml_scalar_vec3(block_text: str, field_name: str, default_val: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Extract `{x: ..., y: ..., z: ...}` from a Unity YAML MonoBehaviour block."""
    match = regex_module.search(
        rf"^\s*{regex_module.escape(field_name)}:\s*\{{x:\s*([^,]+),\s*y:\s*([^,]+),\s*z:\s*([^}}]+)\}}",
        block_text,
        regex_module.MULTILINE,
    )
    if not match:
        return default_val
    return (float(match.group(1)), float(match.group(2)), float(match.group(3)))


def _parse_yaml_curve(block_text: str, curve_field: str) -> List[Tuple[float, float]]:
    """Extract keyframe (time, value) pairs from a Unity AnimationCurve YAML block."""
    lines = block_text.splitlines()
    field_prefix = f"{curve_field}:"
    in_field = False
    in_curve = False
    field_indent = -1
    curve_indent = -1
    pairs: List[Tuple[float, float]] = []
    cur_time: Optional[float] = None

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent_len = len(raw_line) - len(raw_line.lstrip(" "))
        if not in_field:
            if stripped == field_prefix or stripped.startswith(field_prefix + " "):
                in_field = True
                field_indent = indent_len
            continue
        if indent_len <= field_indent and not stripped.startswith("-"):
            break
        if not in_curve:
            if stripped.startswith("m_Curve:"):
                if stripped.endswith("[]"):
                    return []
                in_curve = True
                curve_indent = indent_len
            continue
        if indent_len <= curve_indent and not stripped.startswith("-"):
            break
        if stripped.startswith("time:"):
            try:
                cur_time = float(stripped.split(":", 1)[1].strip())
            except ValueError:
                cur_time = None
        elif stripped.startswith("value:") and cur_time is not None:
            try:
                pairs.append((cur_time, float(stripped.split(":", 1)[1].strip())))
            except ValueError:
                pass
            cur_time = None

    return pairs


def extract_unity_physbones_from_prefab(
    prefab_path: Union[str, Path],
    target_names: Sequence[str] = ("ear.L", "ear.R"),
) -> Dict[str, Dict[str, object]]:
    """
    Parse VRCPhysBone MonoBehaviour blocks from a Unity .prefab YAML file.

    Returns a dictionary keyed by target GameObject name (`ear.L`, `ear.R`, ...)
    with exact parameters, curves, and resolved chain bone mapping.
    """
    resolved_prefab = Path(prefab_path)
    if not resolved_prefab.is_file():
        raise FileNotFoundError(f"Unity prefab not found: {resolved_prefab}")

    raw_text = resolved_prefab.read_text(encoding="utf-8", errors="replace")
    documents = regex_module.split(r"(?=^--- !u!\d+ &\d+)", raw_text, flags=regex_module.MULTILINE)

    gameobject_names: Dict[str, str] = {}
    physbone_blocks: Dict[str, str] = {}
    target_lookup = {name.lower(): name for name in target_names}

    for doc_text in documents:
        header_match = regex_module.match(r"^--- !u!(\d+) &(\d+)", doc_text)
        if not header_match:
            continue
        class_id = header_match.group(1)
        file_id = header_match.group(2)
        if class_id == "1":
            name_match = regex_module.search(r"^\s*m_Name:\s*(.+?)\s*$", doc_text, regex_module.MULTILINE)
            if name_match:
                gameobject_names[file_id] = name_match.group(1).strip()
        elif (
            class_id == "114"
            and VRCHAT_PHYSBONE_SCRIPT_GUID in doc_text
            and f"fileID: {VRCHAT_PHYSBONE_CLASS_FILE_ID}" in doc_text
        ):
            go_match = regex_module.search(r"^\s*m_GameObject:\s*\{fileID:\s*(\d+)\}", doc_text, regex_module.MULTILINE)
            if go_match:
                physbone_blocks[go_match.group(1)] = doc_text

    extracted: Dict[str, Dict[str, object]] = {}
    spec_by_key = {spec[0].lower(): spec for spec in NEKO_MIMI_CHAIN_SPECS}

    def read_float(block_text: str, key_name: str, default_val: float) -> float:
        matched = regex_module.search(rf"^\s*{regex_module.escape(key_name)}:\s*([-+0-9.eE]+)\s*$", block_text, regex_module.MULTILINE)
        return float(matched.group(1)) if matched else default_val

    def read_int(block_text: str, key_name: str, default_val: int) -> int:
        matched = regex_module.search(rf"^\s*{regex_module.escape(key_name)}:\s*([-+]?\d+)\s*$", block_text, regex_module.MULTILINE)
        return int(matched.group(1)) if matched else default_val

    for go_id, block_text in physbone_blocks.items():
        go_name = gameobject_names.get(go_id, "")
        canonical_name = target_lookup.get(go_name.lower())
        if canonical_name is None:
            continue
        spec_entry = spec_by_key.get(canonical_name.lower())
        source_bones = list(spec_entry[2]) if spec_entry else [canonical_name]
        chain_bones = list(spec_entry[3]) if spec_entry else [resolve_neko_mimi_gtav_bone(canonical_name) or canonical_name]

        extracted[canonical_name] = {
            "source_key": canonical_name,
            "root_bone": chain_bones[0],
            "chain_bones": chain_bones,
            "source_bones": source_bones,
            "parent_bone": "SKEL_Head",
            "parent_bone_tag": SKEL_HEAD_TAG,
            "version": read_int(block_text, "version", 1),
            "integration_type": read_int(block_text, "integrationType", 0),
            "multi_child_type": read_int(block_text, "multiChildType", 0),
            "endpoint_position": _parse_yaml_scalar_vec3(block_text, "endpointPosition", (0.0, 0.0, 0.0)),
            "pull": read_float(block_text, "pull", 0.2),
            "spring": read_float(block_text, "spring", 0.35),
            "stiffness": read_float(block_text, "stiffness", 0.2),
            "gravity": read_float(block_text, "gravity", 0.0),
            "gravity_falloff": read_float(block_text, "gravityFalloff", 0.0),
            "immobile_type": read_int(block_text, "immobileType", 0),
            "immobile": read_float(block_text, "immobile", 0.3),
            "allow_collision": read_int(block_text, "allowCollision", 1),
            "radius": read_float(block_text, "radius", 0.025),
            "radius_curve": _parse_yaml_curve(block_text, "radiusCurve"),
            "limit_type": read_int(block_text, "limitType", 1),
            "max_angle_x": read_float(block_text, "maxAngleX", 50.0),
            "max_angle_x_curve": _parse_yaml_curve(block_text, "maxAngleXCurve"),
            "max_angle_z": read_float(block_text, "maxAngleZ", 45.0),
            "limit_rotation": _parse_yaml_scalar_vec3(block_text, "limitRotation", (14.12, 0.0, 0.0)),
            "allow_grabbing": read_int(block_text, "allowGrabbing", 1),
            "allow_posing": read_int(block_text, "allowPosing", 1),
            "grab_movement": read_float(block_text, "grabMovement", 0.5),
            "max_stretch": read_float(block_text, "maxStretch", 0.0),
            "max_squish": read_float(block_text, "maxSquish", 0.0),
            "stretch_motion": read_float(block_text, "stretchMotion", 0.0),
            "is_animated": read_int(block_text, "isAnimated", 1),
        }

    return extracted


def _parse_unity_yaml_ref(line_val: str) -> Optional[Tuple[str, str]]:
    """Parse `{fileID: 123, guid: abc}` reference text into `(file_id, guid)`."""
    matched = regex_module.search(r"fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-fA-F]+))?", line_val)
    if not matched:
        return None
    return (matched.group(1), (matched.group(2) or "").lower())


def _read_unity_meta_guid(asset_path: Path) -> str:
    """Read Unity asset GUID string (lowercase) from sibling `<asset>.meta` if present."""
    meta_file = Path(f"{asset_path}.meta")
    if not meta_file.is_file():
        return ""
    try:
        for raw_line in meta_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("guid:"):
                return stripped.split(":", 1)[1].strip().lower()
    except OSError:
        pass
    return ""


def _inspect_fbx_weights_detailed(
    fbx_paths: Sequence[Union[str, Path]],
    excluded_meshes: Sequence[str] = (),
) -> Tuple[Set[str], Set[str], Dict[str, str], Dict[Path, Dict[str, Set[str]]], bool]:
    """
    Fast pure-Python binary FBX inspector returning:
      `(all_bones_ci, weighted_bones_ci, parent_map_ci, mesh_weights_by_file, has_skin_clusters)`.
    """
    all_bones_ci: Set[str] = set()
    weighted_bones_ci: Set[str] = set()
    parent_map_ci: Dict[str, str] = {}
    mesh_weights_by_file: Dict[Path, Dict[str, Set[str]]] = {}
    has_skin_clusters = False
    excluded_low = {str(name_item).strip().lower() for name_item in excluded_meshes if str(name_item).strip()}

    def _read_prop(
        raw_bytes: bytes, byte_pos: int, total_len: int, parse_weights_array: bool = False
    ) -> Tuple[Any, int]:
        if byte_pos >= total_len:
            raise ValueError("Truncated FBX property")
        type_code = chr(raw_bytes[byte_pos])
        byte_pos += 1
        if type_code == "Y":
            return struct.unpack_from("<h", raw_bytes, byte_pos)[0], byte_pos + 2
        if type_code == "C":
            return bool(raw_bytes[byte_pos]), byte_pos + 1
        if type_code == "I":
            return struct.unpack_from("<i", raw_bytes, byte_pos)[0], byte_pos + 4
        if type_code == "F":
            return struct.unpack_from("<f", raw_bytes, byte_pos)[0], byte_pos + 4
        if type_code == "D":
            return struct.unpack_from("<d", raw_bytes, byte_pos)[0], byte_pos + 8
        if type_code == "L":
            return struct.unpack_from("<q", raw_bytes, byte_pos)[0], byte_pos + 8
        if type_code in ("S", "R"):
            str_len = struct.unpack_from("<I", raw_bytes, byte_pos)[0]
            byte_pos += 4
            raw_slice = raw_bytes[byte_pos : byte_pos + str_len]
            val = raw_slice.decode("utf-8", errors="replace") if type_code == "S" else str_len
            return val, byte_pos + str_len
        if type_code in ("f", "d", "l", "i", "b"):
            arr_len, enc_flag, comp_len = struct.unpack_from("<III", raw_bytes, byte_pos)
            byte_pos += 12
            if parse_weights_array and type_code == "d" and arr_len > 0:
                if byte_pos + comp_len > total_len:
                    return 0.0, total_len
                buf_bytes = raw_bytes[byte_pos : byte_pos + comp_len]
                if enc_flag == 1:
                    buf_bytes = zlib.decompress(buf_bytes)
                unpack_cnt = min(arr_len, len(buf_bytes) // 8)
                if unpack_cnt <= 0:
                    return 0.0, byte_pos + comp_len
                vals = struct.unpack_from(f"<{unpack_cnt}d", buf_bytes)
                return max(vals) if vals else 0.0, byte_pos + comp_len
            elem_size = {"f": 4, "d": 8, "l": 8, "i": 4, "b": 1}[type_code]
            byte_span = comp_len if enc_flag == 1 else (arr_len * elem_size)
            return arr_len, byte_pos + byte_span
        raise ValueError(f"Unsupported FBX property code: {type_code}")

    def _read_node(
        raw_bytes: bytes,
        byte_pos: int,
        total_len: int,
        hdr_fmt: str,
        hdr_size: int,
        parse_props: bool = False,
        parse_children: bool = False,
        parse_weights: bool = False,
    ) -> Tuple[Optional[Tuple[str, List[Any], List[Any]]], int]:
        if byte_pos + hdr_size > total_len:
            return None, total_len
        end_offset, prop_cnt, prop_len, name_len = struct.unpack_from(hdr_fmt, raw_bytes, byte_pos)
        if end_offset == 0:
            return None, byte_pos + hdr_size
        if end_offset <= byte_pos or end_offset > total_len:
            return None, total_len
        byte_pos += hdr_size
        node_name = raw_bytes[byte_pos : byte_pos + name_len].decode("utf-8", errors="replace")
        byte_pos += name_len
        prop_list: List[Any] = []
        prop_end = min(end_offset, byte_pos + prop_len)
        want_weights_here = parse_weights or node_name == "Weights"
        if parse_props:
            for _prop_idx in range(prop_cnt):
                if byte_pos >= prop_end:
                    break
                prop_val, byte_pos = _read_prop(
                    raw_bytes, byte_pos, total_len, parse_weights_array=want_weights_here
                )
                prop_list.append(prop_val)
        byte_pos = prop_end
        child_list: List[Any] = []
        want_child_weights = (
            node_name == "Deformer"
            and len(prop_list) >= 3
            and prop_list[2] == "Cluster"
        )
        if parse_children:
            while byte_pos + hdr_size <= end_offset:
                child_node, next_pos = _read_node(
                    raw_bytes,
                    byte_pos,
                    total_len,
                    hdr_fmt,
                    hdr_size,
                    parse_props=True,
                    parse_children=(node_name == "Objects" or want_child_weights),
                    parse_weights=want_child_weights,
                )
                if child_node is None or next_pos <= byte_pos:
                    break
                byte_pos = next_pos
                child_list.append(child_node)
        return (node_name, prop_list, child_list), end_offset

    for raw_path in fbx_paths:
        if not raw_path:
            continue
        fbx_file = Path(raw_path)
        if not fbx_file.is_file():
            continue
        try:
            mtime_ns = fbx_file.stat().st_mtime_ns
        except OSError:
            continue

        cache_key = (str(fbx_file.resolve()), mtime_ns)
        cached_fbx = _FBX_WEIGHTED_BONES_CACHE.get(cache_key)
        if cached_fbx is not None:
            file_bones, file_mesh_weights, file_parents = cached_fbx
            all_bones_ci.update(file_bones)
            mesh_weights_by_file[fbx_file] = file_mesh_weights
            for child_k, parent_val in file_parents.items():
                parent_map_ci.setdefault(child_k, parent_val)
            for mesh_low, weight_set in file_mesh_weights.items():
                if weight_set:
                    has_skin_clusters = True
                if mesh_low not in excluded_low:
                    weighted_bones_ci.update(weight_set)
            continue

        try:
            raw_bytes = fbx_file.read_bytes()
        except OSError:
            continue
        total_len = len(raw_bytes)
        if total_len < 27 or not raw_bytes.startswith(b"Kaydara FBX Binary"):
            continue

        file_bones_ci: Set[str] = set()
        file_parents_ci: Dict[str, str] = {}
        file_mesh_weights: Dict[str, Set[str]] = {}
        try:
            fbx_ver = struct.unpack_from("<I", raw_bytes, 23)[0]
            is_64bit = fbx_ver >= 7500
            hdr_fmt = "<QQQB" if is_64bit else "<IIIB"
            hdr_size = 25 if is_64bit else 13

            cursor = 27
            models_map: Dict[int, Tuple[str, str]] = {}
            geom_ids: Set[int] = set()
            skin_ids: Set[int] = set()
            cluster_maxw: Dict[int, float] = {}
            conns_list: List[Tuple[int, int]] = []

            while cursor <= total_len - hdr_size:
                end_offset, _pc, _pl, name_len = struct.unpack_from(hdr_fmt, raw_bytes, cursor)
                if end_offset == 0 or end_offset <= cursor or end_offset > total_len:
                    break
                top_name = raw_bytes[cursor + hdr_size : cursor + hdr_size + name_len].decode(
                    "utf-8", errors="replace"
                )
                if top_name in ("Objects", "Connections"):
                    parsed_top, next_cursor = _read_node(
                        raw_bytes,
                        cursor,
                        total_len,
                        hdr_fmt,
                        hdr_size,
                        parse_props=True,
                        parse_children=True,
                    )
                    if parsed_top is None or next_cursor <= cursor:
                        break
                    cursor = next_cursor
                    if top_name == "Objects":
                        for sub_node in parsed_top[2]:
                            sub_type = sub_node[0]
                            sub_props = sub_node[1]
                            if sub_type == "Model" and len(sub_props) >= 3:
                                models_map[sub_props[0]] = (
                                    str(sub_props[1]).split("\x00")[0],
                                    str(sub_props[2]),
                                )
                            elif sub_type == "Geometry" and len(sub_props) >= 1:
                                geom_ids.add(sub_props[0])
                            elif sub_type == "Deformer" and len(sub_props) >= 3:
                                if sub_props[2] == "Skin":
                                    skin_ids.add(sub_props[0])
                                elif sub_props[2] == "Cluster":
                                    max_weight = 0.0
                                    for csub in sub_node[2]:
                                        if csub[0] == "Weights" and csub[1] and isinstance(csub[1][0], (int, float)):
                                            max_weight = float(csub[1][0])
                                    cluster_maxw[sub_props[0]] = max_weight
                    else:
                        for sub_node in parsed_top[2]:
                            if sub_node[0] == "C" and len(sub_node[1]) >= 3:
                                conns_list.append((sub_node[1][1], sub_node[1][2]))
                else:
                    cursor = end_offset

            children_of: Dict[int, List[int]] = {}
            for src_id, dst_id in conns_list:
                children_of.setdefault(dst_id, []).append(src_id)
                if src_id in models_map and dst_id in models_map:
                    src_name, src_subtype = models_map[src_id]
                    dst_name, dst_subtype = models_map[dst_id]
                    if src_subtype in ("LimbNode", "Null", "Root") and dst_subtype in ("LimbNode", "Null", "Root"):
                        file_parents_ci.setdefault(src_name.lower(), dst_name.lower())

            for model_id, (model_name, model_subtype) in models_map.items():
                if model_subtype in ("LimbNode", "Null", "Root"):
                    file_bones_ci.add(model_name.lower())
                if model_subtype != "Mesh":
                    continue
                mesh_low = model_name.strip().lower()
                mesh_w_set = file_mesh_weights.setdefault(mesh_low, set())
                for geom_id in children_of.get(model_id, []):
                    if geom_id not in geom_ids:
                        continue
                    for skin_id in children_of.get(geom_id, []):
                        if skin_id not in skin_ids:
                            continue
                        for cluster_id in children_of.get(skin_id, []):
                            if cluster_maxw.get(cluster_id, 0.0) <= 1e-4:
                                continue
                            for bone_id in children_of.get(cluster_id, []):
                                if bone_id in models_map:
                                    mesh_w_set.add(models_map[bone_id][0].lower())
        except (struct.error, ValueError, zlib.error, IndexError):
            continue

        _FBX_WEIGHTED_BONES_CACHE[cache_key] = (file_bones_ci, file_mesh_weights, file_parents_ci)
        all_bones_ci.update(file_bones_ci)
        mesh_weights_by_file[fbx_file] = file_mesh_weights
        for child_k, parent_val in file_parents_ci.items():
            parent_map_ci.setdefault(child_k, parent_val)
        for mesh_low, weight_set in file_mesh_weights.items():
            if weight_set:
                has_skin_clusters = True
            if mesh_low not in excluded_low:
                weighted_bones_ci.update(weight_set)

    return all_bones_ci, weighted_bones_ci, parent_map_ci, mesh_weights_by_file, has_skin_clusters


def collect_fbx_weighted_bones(
    fbx_paths: Sequence[Union[str, Path]],
    excluded_meshes: Sequence[str] = (),
) -> Tuple[Set[str], Set[str], Dict[str, str]]:
    """
    Fast pure-Python binary FBX inspector extracting all armature bone names (lowercase),
    nonzero vertex-weighted bone names (lowercase), and lowercase `child -> parent` map.
    """
    all_bones_ci, weighted_bones_ci, parent_map_ci, _by_file, _has_skin = _inspect_fbx_weights_detailed(
        fbx_paths, excluded_meshes=excluded_meshes
    )
    return all_bones_ci, weighted_bones_ci, parent_map_ci


def prune_orphaned_physbone_chains(
    chains_map: Dict[str, Dict[str, Any]],
    active_weighted_bones_ci: Optional[Set[str]],
    bone_mapping: Optional[Dict[str, str]] = None,
    disabled_mesh_bones_ci: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Remove orphaned PhysBone chains whose source bones have zero skin weights on active meshes
    (e.g., leftover PhysBones from an old dress deleted or toggled off after adding a custom dress).
    """
    if active_weighted_bones_ci is None:
        return {
            "chains": dict(chains_map),
            "bone_mapping": dict(bone_mapping or {}),
            "orphaned_physbones": [],
        }

    disabled_ci = set(disabled_mesh_bones_ci or ())
    kept_chains: Dict[str, Dict[str, Any]] = {}
    orphaned_records: List[Dict[str, Any]] = []
    orphan_src_fallbacks: Dict[str, str] = {}
    removed_gtav_bones: Set[str] = set()

    for chain_key, cfg_data in chains_map.items():
        src_bones = [
            str(bone_nm).strip()
            for bone_nm in (cfg_data.get("source_bones") or ())
            if str(bone_nm).strip()
        ]
        gtav_bones = [
            str(bone_nm).strip()
            for bone_nm in (cfg_data.get("chain_bones") or ())
            if str(bone_nm).strip()
        ]
        parent_bone = str(cfg_data.get("parent_bone") or "SKEL_Pelvis")
        has_active_weight = any(bone_nm.lower() in active_weighted_bones_ci for bone_nm in src_bones)
        if has_active_weight:
            kept_chains[chain_key] = cfg_data
            continue

        reason_tok = (
            "disabled_old_outfit_mesh"
            if any(bone_nm.lower() in disabled_ci for bone_nm in src_bones)
            else "no_active_mesh_weights"
        )
        removed_gtav_bones.update(gtav_bones)
        for bone_nm in src_bones:
            orphan_src_fallbacks[bone_nm.lower()] = parent_bone
        orphaned_records.append(
            {
                "chain_key": str(chain_key),
                "root_bone": src_bones[0] if src_bones else str(chain_key),
                "parent_bone": parent_bone,
                "reason": reason_tok,
                "source_bones": src_bones,
            }
        )

    cleaned_bmap: Dict[str, str] = {}
    for src_k, dst_v in (bone_mapping or {}).items():
        src_low = str(src_k).strip().lower()
        if str(dst_v).strip() in removed_gtav_bones or src_low in orphan_src_fallbacks:
            continue
        cleaned_bmap[src_k] = dst_v

    return {
        "chains": kept_chains,
        "bone_mapping": cleaned_bmap,
        "orphaned_physbones": orphaned_records,
    }


_UNITY_GUID_CACHE: Dict[str, Dict[str, Path]] = {}
_UNITY_GUID_SCAN_STATE: Dict[str, Dict[str, Any]] = {}


def _index_unity_asset_guids(
    unity_assets_root: Optional[Union[str, Path]],
    needed_guids: Set[str],
    seed_files: Sequence[Union[str, Path]] = (),
    character_hints: Sequence[str] = (),
    deadline_sec: float = 20.0,
) -> Dict[str, Path]:
    """
    Fast breadth-first GUID indexer scanning prioritized Unity asset subfolders (depth 1-3)
    with a persistent resumable scan state per `unity_assets_root` so repeated queries stay instant.
    """
    import time as time_mod

    needed_low = {guid_str.strip().lower() for guid_str in needed_guids if guid_str}
    if not needed_low:
        return {}

    try:
        import unity_scene_helper
    except ImportError:
        unity_scene_helper = None

    skip_dirs = (
        set(getattr(unity_scene_helper, "_SKIP_SEARCH_DIRS", set()))
        if unity_scene_helper
        else {".git", "Library", "Temp", "Obj", "Logs"}
    ) | {
        "texture", "textures", "tex", "material", "materials", "mat",
        "shader", "shaders", "animation", "animations", "anim", "psd",
        "audio", "sound", "sfx", "vfx", "particle", "particles", "sprites",
        "fx", "mask", "masks", "normal", "normals", "plugins", "editor",
        "vrcsdk", "samples", "__backup",
    }

    assets_dir_resolved = (
        Path(unity_assets_root).resolve()
        if unity_assets_root and Path(unity_assets_root).is_dir()
        else None
    )
    cache_key = str(assets_dir_resolved or "")
    cached_map = _UNITY_GUID_CACHE.setdefault(cache_key, {})

    try:
        import modular_avatar_helper as ma_helper_mod
        ma_shared_cache = getattr(ma_helper_mod, "_MA_GUID_CACHE", {})
    except ImportError:
        ma_shared_cache = {}
    for guid_key in needed_low:
        if guid_key not in cached_map:
            shared_p = ma_shared_cache.get(guid_key)
            if shared_p is not None and shared_p.is_file():
                cached_map[guid_key] = shared_p

    guid_map: Dict[str, Path] = {
        guid_key: cached_map[guid_key]
        for guid_key in needed_low
        if guid_key in cached_map and cached_map[guid_key].is_file()
    }
    remaining = needed_low - set(guid_map)
    scan_state = _UNITY_GUID_SCAN_STATE.setdefault(
        cache_key,
        {"seen_dirs": set(), "queue": collections_module.deque(), "initialized": False, "complete": False},
    )
    if not remaining or (assets_dir_resolved is not None and scan_state["complete"]):
        return guid_map

    def _is_safe_subdir(dir_path: Path) -> bool:
        if not dir_path.is_dir():
            return False
        res_dir = dir_path.resolve()
        if assets_dir_resolved is not None and (
            res_dir == assets_dir_resolved or res_dir in assets_dir_resolved.parents
        ):
            return False
        if res_dir == res_dir.parent:
            return False
        return True

    candidate_roots: List[Path] = []
    if assets_dir_resolved is not None:
        marsh_dir = assets_dir_resolved / "marshmallow_PB"
        if _is_safe_subdir(marsh_dir):
            candidate_roots.append(marsh_dir)

    for seed_item in seed_files:
        if not seed_item:
            continue
        seed_path = Path(seed_item).resolve()
        cur_parent = seed_path.parent
        best_pkg_dir: Optional[Path] = None
        for _step in range(5):
            if _is_safe_subdir(cur_parent):
                best_pkg_dir = cur_parent
            if assets_dir_resolved is not None and cur_parent.parent == assets_dir_resolved:
                break
            cur_parent = cur_parent.parent
        if best_pkg_dir is not None:
            candidate_roots.append(best_pkg_dir)

    if assets_dir_resolved is not None:
        pkg_keywords = {
            "shinano", "miltina", "milltina", "eternal", "reunion",
            "dolos", "vagrant", "li-ne", "marshmallow", "retargeted", "converted",
        }
        for hint_str in character_hints:
            for tok_str in regex_module.split(r"[^A-Za-z0-9]+", str(hint_str or "").lower()):
                if len(tok_str) >= 3:
                    pkg_keywords.add(tok_str)

        def _collect_depth_hints(root_dir_item: Path, rem_depth: int) -> None:
            if rem_depth <= 0:
                return
            try:
                sub_entries = list(operating_system.scandir(root_dir_item))
            except OSError:
                return
            for dir_entry in sub_entries:
                if not dir_entry.is_dir(follow_symlinks=False) or dir_entry.name.startswith("."):
                    continue
                low_name = dir_entry.name.lower()
                if low_name in skip_dirs:
                    continue
                cand_dir = Path(dir_entry.path)
                if any(word_tok in low_name for word_tok in pkg_keywords):
                    if _is_safe_subdir(cand_dir):
                        candidate_roots.append(cand_dir)
                else:
                    _collect_depth_hints(cand_dir, rem_depth - 1)

        _collect_depth_hints(assets_dir_resolved, 3)

    seen_dirs: Set[Path] = scan_state["seen_dirs"] if assets_dir_resolved is not None else set()
    bfs_queue = collections_module.deque()
    for root_dir in candidate_roots:
        res_root = root_dir.resolve()
        if res_root not in seen_dirs and _is_safe_subdir(res_root):
            bfs_queue.append((res_root, 0))

    start_time = time_mod.monotonic()

    def _scan_meta_dir(dir_queue: collections_module.deque, max_depth: int, max_dirs: int) -> bool:
        dirs_scanned = 0
        while dir_queue and remaining and dirs_scanned < max_dirs:
            if (time_mod.monotonic() - start_time) > deadline_sec:
                return False
            cur_dir, cur_depth = dir_queue.popleft()
            if cur_dir in seen_dirs:
                continue
            seen_dirs.add(cur_dir)
            dirs_scanned += 1
            try:
                dir_entries = list(operating_system.scandir(cur_dir))
            except OSError:
                continue
            for entry_item in dir_entries:
                entry_name = entry_item.name
                if entry_item.is_dir(follow_symlinks=False):
                    low_dir = entry_name.lower()
                    if (
                        cur_depth < max_depth
                        and not entry_name.startswith(".")
                        and low_dir not in skip_dirs
                    ):
                        sub_res = Path(entry_item.path).resolve()
                        if sub_res not in seen_dirs:
                            dir_queue.append((sub_res, cur_depth + 1))
                elif entry_name.endswith(".meta"):
                    base_name = entry_name[:-5]
                    if not base_name.lower().endswith((".prefab", ".fbx", ".asset")):
                        continue
                    try:
                        with open(entry_item.path, "r", encoding="utf-8", errors="ignore") as meta_file:
                            for _line_idx in range(8):
                                meta_line = meta_file.readline()
                                if not meta_line:
                                    break
                                if meta_line.startswith("guid:"):
                                    guid_val = meta_line.split(":", 1)[1].strip().lower()
                                    asset_path = Path(cur_dir) / base_name
                                    cached_map[guid_val] = asset_path
                                    if guid_val in remaining:
                                        guid_map[guid_val] = asset_path
                                        remaining.discard(guid_val)
                                    break
                    except OSError:
                        pass
        return len(dir_queue) == 0

    _scan_meta_dir(bfs_queue, max_depth=6, max_dirs=1000)

    # Resumable BFS across remaining asset folders only if GUIDs are still missing
    if remaining and assets_dir_resolved is not None and (time_mod.monotonic() - start_time) < deadline_sec:
        if not scan_state["initialized"]:
            scan_state["initialized"] = True
            try:
                for dir_entry in sorted(operating_system.scandir(assets_dir_resolved), key=lambda ent: ent.name):
                    if dir_entry.is_dir(follow_symlinks=False) and not dir_entry.name.startswith("."):
                        if dir_entry.name.lower() not in skip_dirs:
                            sub_res = Path(dir_entry.path).resolve()
                            if sub_res not in seen_dirs:
                                scan_state["queue"].append((sub_res, 0))
            except OSError:
                pass
        finished_all = _scan_meta_dir(scan_state["queue"], max_depth=6, max_dirs=10000)
        if finished_all and len(scan_state["queue"]) == 0:
            scan_state["complete"] = True

    return guid_map


_STREAM_PHYSBONE_DOC_CACHE: Dict[Tuple[str, int], Dict[str, Any]] = {}


def _stream_parse_unity_physbone_doc(doc_path: Path) -> Dict[str, Any]:
    """O(N) streaming YAML parser extracting GO, Transform, VRCPhysBone, Marshmallow PB, and PrefabInstance."""
    try:
        cache_key = (str(doc_path.resolve()), doc_path.stat().st_mtime_ns)
    except OSError:
        cache_key = None
    if cache_key is not None and cache_key in _STREAM_PHYSBONE_DOC_CACHE:
        return _STREAM_PHYSBONE_DOC_CACHE[cache_key]

    gameobjects: Dict[str, Dict[str, Any]] = {}
    transforms: Dict[str, Dict[str, Any]] = {}
    physbones: Dict[str, Dict[str, Any]] = {}
    marshmallow_setups: Dict[str, Dict[str, Any]] = {}
    skinned_meshes: Dict[str, Dict[str, Any]] = {}
    prefab_instances: Dict[str, Dict[str, Any]] = {}

    cur_cls: Optional[str] = None
    cur_id: Optional[str] = None
    cur_stripped = False
    cur_obj: Optional[Dict[str, Any]] = None
    in_ignored = False
    cur_pi_section = "none"
    cur_mod: Optional[Dict[str, Any]] = None
    cur_curve_name: Optional[str] = None
    cur_curve_time: Optional[float] = None
    cur_marsh_list: Optional[str] = None

    hdr_re = regex_module.compile(r"^--- !u!(\d+) &(-?\d+)(\s+stripped)?")

    def _flush_cur() -> None:
        nonlocal cur_obj
        if cur_obj is None or cur_id is None:
            cur_obj = None
            return
        cur_obj["stripped"] = cur_stripped
        if cur_cls == "1":
            gameobjects[cur_id] = cur_obj
        elif cur_cls == "4":
            transforms[cur_id] = cur_obj
        elif cur_cls == "137":
            skinned_meshes[cur_id] = cur_obj
        elif cur_cls == "1001":
            prefab_instances[cur_id] = cur_obj
        elif cur_cls == "114":
            if cur_obj.get("is_physbone"):
                physbones[cur_id] = cur_obj
            elif cur_obj.get("is_marshmallow"):
                marshmallow_setups[cur_id] = cur_obj
        cur_obj = None

    with doc_path.open("r", encoding="utf-8", errors="ignore") as yaml_file:
        for raw_line in yaml_file:
            if raw_line.startswith("--- !u!"):
                _flush_cur()
                matched_hdr = hdr_re.match(raw_line)
                in_ignored = False
                cur_pi_section = "none"
                cur_mod = None
                cur_curve_name = None
                cur_curve_time = None
                cur_marsh_list = None
                if not matched_hdr:
                    cur_cls = None
                    continue
                cur_cls = matched_hdr.group(1)
                cur_id = matched_hdr.group(2)
                cur_stripped = bool(matched_hdr.group(3))
                if cur_cls in ("1", "4", "114", "137", "1001"):
                    cur_obj = {"id": cur_id, "cls": cur_cls}
                    if cur_cls == "1001":
                        cur_obj["mods"] = []
                        cur_obj["removed_gos"] = []
                        cur_obj["removed_comps"] = []
                else:
                    cur_obj = None
                continue

            if cur_obj is None:
                continue

            stripped = raw_line.strip()
            if cur_cls == "1":
                if stripped.startswith("m_Name:"):
                    cur_obj["name"] = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("m_IsActive:"):
                    cur_obj["active"] = stripped.split(":", 1)[1].strip() != "0"
                elif stripped.startswith("m_TagString:"):
                    cur_obj["tag"] = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("m_PrefabInstance:"):
                    cur_obj["pi"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_CorrespondingSourceObject:"):
                    cur_obj["src"] = _parse_unity_yaml_ref(stripped)
            elif cur_cls == "4":
                if stripped.startswith("m_GameObject:"):
                    cur_obj["go"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_Father:"):
                    cur_obj["father"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_LocalPosition:"):
                    cur_obj["local_pos"] = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("m_PrefabInstance:"):
                    cur_obj["pi"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_CorrespondingSourceObject:"):
                    cur_obj["src"] = _parse_unity_yaml_ref(stripped)
            elif cur_cls == "137":
                if stripped.startswith("m_GameObject:"):
                    cur_obj["go"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_Enabled:"):
                    cur_obj["enabled"] = stripped.split(":", 1)[1].strip() != "0"
                elif stripped.startswith("m_Mesh:"):
                    cur_obj["mesh"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_PrefabInstance:"):
                    cur_obj["pi"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_CorrespondingSourceObject:"):
                    cur_obj["src"] = _parse_unity_yaml_ref(stripped)
            elif cur_cls == "1001":
                if stripped.startswith("m_TransformParent:"):
                    cur_pi_section = "none"
                    cur_obj["parent_tf"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_SourcePrefab:"):
                    cur_pi_section = "none"
                    cur_obj["source_prefab"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_Modifications:"):
                    cur_pi_section = "mods"
                    cur_mod = None
                elif stripped.startswith("m_RemovedGameObjects:"):
                    cur_pi_section = "removed_gos"
                    cur_mod = None
                elif stripped.startswith("m_RemovedComponents:"):
                    cur_pi_section = "removed_comps"
                    cur_mod = None
                elif stripped.startswith(("m_Removed", "m_Added")):
                    cur_pi_section = "none"
                    cur_mod = None
                elif cur_pi_section == "removed_gos":
                    if stripped.startswith("- ") and "fileID:" in stripped:
                        ref_item = _parse_unity_yaml_ref(stripped)
                        if ref_item:
                            cur_obj["removed_gos"].append(ref_item)
                    elif ":" in stripped and not stripped.startswith("-"):
                        cur_pi_section = "none"
                elif cur_pi_section == "removed_comps":
                    if stripped.startswith("- ") and "fileID:" in stripped:
                        ref_item = _parse_unity_yaml_ref(stripped)
                        if ref_item:
                            cur_obj["removed_comps"].append(ref_item)
                    elif ":" in stripped and not stripped.startswith("-"):
                        cur_pi_section = "none"
                elif cur_pi_section == "mods":
                    if stripped.startswith("- target:"):
                        cur_mod = {"target": _parse_unity_yaml_ref(stripped)}
                        cur_obj["mods"].append(cur_mod)
                    elif cur_mod is not None:
                        if stripped.startswith("propertyPath:"):
                            cur_mod["path"] = stripped.split(":", 1)[1].strip()
                        elif stripped.startswith("value:"):
                            cur_mod["value"] = stripped.split(":", 1)[1].strip()
                        elif stripped.startswith("objectReference:"):
                            cur_mod["objref"] = _parse_unity_yaml_ref(stripped)
            elif cur_cls == "114":
                if stripped.startswith("m_Script:"):
                    ref_val = _parse_unity_yaml_ref(stripped)
                    if (
                        ref_val
                        and ref_val[1] == VRCHAT_PHYSBONE_SCRIPT_GUID
                        and ref_val[0] == VRCHAT_PHYSBONE_CLASS_FILE_ID
                    ):
                        cur_obj["is_physbone"] = True
                elif stripped.startswith("m_GameObject:"):
                    cur_obj["go"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_Enabled:"):
                    cur_obj["enabled"] = stripped.split(":", 1)[1].strip() != "0"
                elif stripped.startswith("m_PrefabInstance:"):
                    cur_obj["pi"] = _parse_unity_yaml_ref(stripped)
                elif stripped.startswith("m_CorrespondingSourceObject:"):
                    cur_obj["src"] = _parse_unity_yaml_ref(stripped)
                elif cur_obj.get("is_physbone"):
                    if stripped.startswith("ignoreTransforms:"):
                        in_ignored = True
                        cur_obj["ignored"] = []
                        cur_curve_name = None
                    elif in_ignored:
                        if stripped.startswith("- {fileID:"):
                            cur_obj["ignored"].append(_parse_unity_yaml_ref(stripped))
                        elif ":" in stripped and not stripped.startswith("-"):
                            in_ignored = False
                    if stripped in ("radiusCurve:", "maxAngleXCurve:"):
                        cur_curve_name = stripped[:-1]
                        cur_curve_time = None
                        cur_obj.setdefault(cur_curve_name, [])
                    elif cur_curve_name is not None:
                        if stripped.startswith("time:"):
                            try:
                                cur_curve_time = float(stripped.split(":", 1)[1].strip())
                            except ValueError:
                                cur_curve_time = None
                        elif stripped.startswith("value:") and cur_curve_time is not None:
                            try:
                                cur_obj[cur_curve_name].append(
                                    (cur_curve_time, float(stripped.split(":", 1)[1].strip()))
                                )
                            except ValueError:
                                pass
                            cur_curve_time = None
                        elif (
                            ":" in stripped
                            and not stripped.startswith(("-", "serializedVersion:", "m_Curve:", "inSlope:", "outSlope:", "tangentMode:", "weightedMode:", "inWeight:", "outWeight:", "m_PreInfinity:", "m_PostInfinity:", "m_RotationOrder:"))
                        ):
                            cur_curve_name = None
                    if not in_ignored and cur_curve_name is None:
                        if stripped.startswith("rootTransform:"):
                            cur_obj["root_tf"] = _parse_unity_yaml_ref(stripped)
                        elif stripped.startswith("endpointPosition:"):
                            cur_obj["endpoint_position"] = _parse_yaml_scalar_vec3(raw_line, "endpointPosition", (0.0, 0.0, 0.0))
                        elif stripped.startswith("limitRotation:"):
                            cur_obj["limit_rotation"] = _parse_yaml_scalar_vec3(raw_line, "limitRotation", (0.0, 0.0, 0.0))
                        else:
                            for scalar_key, out_field in (
                                ("version:", "version"),
                                ("integrationType:", "integration_type"),
                                ("multiChildType:", "multi_child_type"),
                                ("pull:", "pull"),
                                ("spring:", "spring"),
                                ("stiffness:", "stiffness"),
                                ("gravity:", "gravity"),
                                ("gravityFalloff:", "gravity_falloff"),
                                ("immobileType:", "immobile_type"),
                                ("immobile:", "immobile"),
                                ("allowCollision:", "allow_collision"),
                                ("radius:", "radius"),
                                ("limitType:", "limit_type"),
                                ("maxAngleX:", "max_angle_x"),
                                ("maxAngleZ:", "max_angle_z"),
                                ("allowGrabbing:", "allow_grabbing"),
                                ("allowPosing:", "allow_posing"),
                                ("grabMovement:", "grab_movement"),
                                ("maxStretch:", "max_stretch"),
                                ("maxSquish:", "max_squish"),
                                ("stretchMotion:", "stretch_motion"),
                                ("isAnimated:", "is_animated"),
                            ):
                                if stripped.startswith(scalar_key):
                                    cur_obj[out_field] = stripped.split(":", 1)[1].strip()
                                    break
                else:
                    if stripped in ("_presets:", "_pbpresets:"):
                        cur_marsh_list = stripped[:-1]
                        cur_obj.setdefault(cur_marsh_list + "_list", [])
                    elif cur_marsh_list is not None:
                        if stripped.startswith("- {fileID:"):
                            ref_item = _parse_unity_yaml_ref(stripped)
                            cur_obj[cur_marsh_list + "_list"].append(ref_item)
                            continue
                        if ":" in stripped and not stripped.startswith("-"):
                            cur_marsh_list = None
                    if stripped.startswith("_marshmallowPBEnabled:"):
                        cur_obj["is_marshmallow"] = True
                        cur_obj[stripped.split(":", 1)[0]] = stripped.split(":", 1)[1].strip()
                    elif stripped.startswith(("_PhysBone_", "_index:", "_presets.Array.data", "_pbpresets.Array.data")):
                        key_tok, val_tok = stripped.split(":", 1)
                        cur_obj[key_tok] = val_tok.strip()
                        if "_PhysBone_Pull" in key_tok:
                            cur_obj["is_marshmallow"] = True

    _flush_cur()
    doc_result = {
        "path": doc_path,
        "gos": gameobjects,
        "tfs": transforms,
        "pbs": physbones,
        "marsh": marshmallow_setups,
        "smrs": skinned_meshes,
        "pis": prefab_instances,
    }
    if cache_key is not None:
        _STREAM_PHYSBONE_DOC_CACHE[cache_key] = doc_result
    return doc_result


def _parse_marshmallow_asset_file(asset_path: Path) -> Dict[str, Any]:
    """Read key-value fields from a Marshmallow PB `.asset` preset file."""
    if not asset_path.is_file():
        return {}
    data: Dict[str, Any] = {}
    for raw_line in asset_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        st_line = raw_line.strip()
        for fld in (
            "path_breast_L",
            "path_breast_R",
            "_PhysBone_Pull",
            "_PhysBone_Momentum",
            "_PhysBone_Stiffness",
            "_PhysBone_Gravity",
            "_PhysBone_GravityFalloff",
            "_PhysBone_Immobile",
            "_PhysBone_Immobile_type",
            "_PhysBone_Stretch_Motion",
            "_PhysBone_Max_Stretch",
            "_PhysBone_Max_Squish",
            "limit_angle_0",
            "breast_collider_radius_0",
        ):
            if st_line.startswith(f"{fld}:"):
                data[fld] = st_line.split(":", 1)[1].strip()
                break
    return data


def _collect_marshmallow_pb_overrides(
    scene_doc: Dict[str, Any],
    visited_pis: Set[str],
    guid_map: Dict[str, Path],
    doc_cache: Dict[Path, Dict[str, Any]],
    unity_assets_root: Optional[Union[str, Path]] = None,
    is_tf_active_fn: Optional[Callable[[str], bool]] = None,
) -> List[Dict[str, Any]]:
    """Extract active Marshmallow PB breast presets and overrides from PrefabInstances."""
    results: List[Dict[str, Any]] = []
    for pi_id in sorted(visited_pis, key=lambda val_str: int(val_str)):
        pi_info = scene_doc["pis"].get(pi_id)
        if not pi_info:
            continue
        ptf_ref = pi_info.get("parent_tf")
        ptf_id = ptf_ref[0] if ptf_ref else "0"
        if is_tf_active_fn is not None and not is_tf_active_fn(ptf_id):
            continue
        sp_ref = pi_info.get("source_prefab")
        src_path = guid_map.get(sp_ref[1]) if sp_ref else None
        if not src_path or "marshmallow" not in src_path.name.lower() or not src_path.is_file():
            continue
        if src_path not in doc_cache:
            doc_cache[src_path] = _stream_parse_unity_physbone_doc(src_path)
        pref_doc = doc_cache[src_path]
        base_marsh = next(iter(pref_doc["marsh"].values()), {})
        merged: Dict[str, Any] = dict(base_marsh)
        preset_refs: Dict[str, Tuple[str, str]] = {}
        pbpreset_refs: Dict[str, Tuple[str, str]] = {}
        explicit_mods: Dict[str, Any] = {}
        root_active = True
        root_tag = "Untagged"

        for mod_item in pi_info.get("mods", []):
            prop_path = mod_item.get("path", "")
            val_str = mod_item.get("value", "")
            obj_ref = mod_item.get("objref")
            if prop_path == "m_IsActive":
                root_active = val_str != "0"
            elif prop_path == "m_TagString":
                root_tag = val_str
            elif prop_path in (
                "_index",
                "_marshmallowPBEnabled",
                "_PhysBone_index",
                "_PhysBone_Pull",
                "_PhysBone_Momentum",
                "_PhysBone_Stiffness",
                "_PhysBone_Gravity",
                "_PhysBone_GravityFalloff",
                "_PhysBone_Immobile",
                "_PhysBone_Immobile_type",
                "_PhysBone_Limit_Angle",
                "_PhysBone_Stretch_Motion",
                "_PhysBone_Max_Stretch",
                "_PhysBone_Max_Squish",
                "_PhysBone_AllowCollision",
                "_PhysBone_Collision_Radius",
            ):
                explicit_mods[prop_path] = val_str
            elif prop_path.startswith("_presets.Array.data["):
                idx_token = prop_path[len("_presets.Array.data[") :].rstrip("]")
                if obj_ref and obj_ref[1]:
                    preset_refs[idx_token] = obj_ref
            elif prop_path.startswith("_pbpresets.Array.data["):
                idx_token = prop_path[len("_pbpresets.Array.data[") :].rstrip("]")
                if obj_ref and obj_ref[1]:
                    pbpreset_refs[idx_token] = obj_ref

        if not root_active or root_tag == "EditorOnly":
            continue

        # Apply _pbpresets[_PhysBone_index] only when explicitly selected via _PhysBone_index
        pb_idx_str = str(explicit_mods.get("_PhysBone_index") or merged.get("_PhysBone_index", "")).strip()
        pbpreset_data: Dict[str, Any] = {}
        if "_PhysBone_index" in explicit_mods and pb_idx_str.isdigit():
            pb_idx_num = int(pb_idx_str)
            pb_ref = pbpreset_refs.get(pb_idx_str)
            if not pb_ref:
                pb_list = base_marsh.get("_pbpresets_list", [])
                if 0 <= pb_idx_num < len(pb_list):
                    pb_ref = pb_list[pb_idx_num]
            if pb_ref and pb_ref[1]:
                pb_path = guid_map.get(pb_ref[1])
                if pb_path:
                    pbpreset_data = _parse_marshmallow_asset_file(pb_path)

        merged.update(pbpreset_data)
        merged.update(explicit_mods)

        if str(merged.get("_marshmallowPBEnabled", "1")).strip() == "0":
            continue

        preset_idx = str(merged.get("_index", "")).strip()
        preset_data: Dict[str, Any] = {}
        if preset_idx in preset_refs:
            preset_path = guid_map.get(preset_refs[preset_idx][1])
            if preset_path:
                preset_data = _parse_marshmallow_asset_file(preset_path)
        elif preset_idx.isdigit():
            preset_list = base_marsh.get("_presets_list", [])
            preset_num = int(preset_idx)
            if 0 <= preset_num < len(preset_list) and preset_list[preset_num][1]:
                preset_path = guid_map.get(preset_list[preset_num][1])
                if preset_path:
                    preset_data = _parse_marshmallow_asset_file(preset_path)
        if not preset_data and unity_assets_root and preset_idx.isdigit():
            cand_asset = (
                Path(unity_assets_root)
                / "marshmallow_PB"
                / "Setup"
                / "Preset"
                / f"{int(preset_idx):02d}.asset"
            )
            if cand_asset.is_file():
                preset_data = _parse_marshmallow_asset_file(cand_asset)

        left_path = str(preset_data.get("path_breast_L") or "").strip()
        right_path = str(preset_data.get("path_breast_R") or "").strip()
        left_bone = left_path.rsplit("/", 1)[-1] if left_path else "Breast_1.L"
        right_bone = right_path.rsplit("/", 1)[-1] if right_path else "Breast_1.R"

        def _fval(field_key: str, default_num: float) -> float:
            try:
                return float(merged.get(field_key, default_num))
            except (TypeError, ValueError):
                return default_num

        def _ival(field_key: str, default_num: int) -> int:
            try:
                return int(float(merged.get(field_key, default_num)))
            except (TypeError, ValueError):
                return default_num

        raw_radius = _fval("_PhysBone_Collision_Radius", 0.06)
        if raw_radius > 0.5:
            # Slider scale in some Marshmallow presets is serialized in cm/percent (e.g. 4 -> 0.04 m)
            raw_radius = max(0.01, min(0.15, raw_radius * 0.01))

        lim_rot = _parse_yaml_scalar_vec3(
            f"_PhysBone_Limit_Rotation: {merged.get('_PhysBone_Limit_Rotation', '{x: -10, y: 0, z: 0}')}",
            "_PhysBone_Limit_Rotation",
            (-10.0, 0.0, 0.0),
        )
        shared_params = {
            "version": 1,
            "integration_type": 0,
            "multi_child_type": 0,
            "endpoint_position": (0.0, 0.08, 0.0),
            "pull": _fval("_PhysBone_Pull", 0.08),
            "spring": _fval("_PhysBone_Momentum", 0.5),
            "stiffness": _fval("_PhysBone_Stiffness", 0.25),
            "gravity": _fval("_PhysBone_Gravity", 0.25),
            "gravity_falloff": _fval("_PhysBone_GravityFalloff", 1.0),
            "immobile_type": _ival("_PhysBone_Immobile_type", 0),
            "immobile": _fval("_PhysBone_Immobile", 0.5),
            "allow_collision": _ival("_PhysBone_AllowCollision", 1),
            "radius": raw_radius,
            "radius_curve": [],
            "limit_type": 1,
            "max_angle_x": _fval("_PhysBone_Limit_Angle", 35.0),
            "max_angle_x_curve": [],
            "max_angle_z": 45.0,
            "limit_rotation": lim_rot,
            "allow_grabbing": 1,
            "allow_posing": 0,
            "grab_movement": 0.1,
            "max_stretch": _fval("_PhysBone_Max_Stretch", 0.3),
            "max_squish": _fval("_PhysBone_Max_Squish", 0.6),
            "stretch_motion": _fval("_PhysBone_Stretch_Motion", 0.5),
            "is_animated": 1,
            "from_marshmallow_pb": True,
        }
        for side_code, root_bone_name in (("L", left_bone), ("R", right_bone)):
            entry = dict(shared_params)
            entry["source_key"] = f"breast.{side_code}"
            entry["root_bone"] = root_bone_name
            entry["parent_bone"] = "SKEL_Spine2"
            entry["parent_bone_tag"] = SKEL_SPINE2_TAG
            results.append(entry)
    return results


def _collect_linear_spokes(
    root_tf_id: str,
    children_map: Dict[str, List[str]],
    name_fn: Callable[[str], str],
    ignored_tf_ids: Set[str],
    allowed_bones_ci: Optional[Set[str]] = None,
) -> Tuple[List[List[str]], List[str]]:
    """
    Walk a Unity transform subtree from root_tf_id, returning:
      - list of linear spoke chains `[root_or_spoke, ..., leaf]`
      - flat list of all valid visited bone names in subtree
    """
    root_name = name_fn(root_tf_id)
    all_desc: List[str] = [root_name]
    spokes: List[List[str]] = []

    def _walk(cur_tf: str, cur_path: List[str], depth_val: int) -> None:
        if depth_val > 16:
            spokes.append(cur_path)
            return
        raw_children = [
            child_tf
            for child_tf in children_map.get(cur_tf, [])
            if child_tf not in ignored_tf_ids
        ]
        # Filter out pure non-bone helpers when allowed_bones_ci is given (preserving at least direct path)
        valid_children = raw_children
        if allowed_bones_ci is not None:
            filtered = [
                child_tf
                for child_tf in raw_children
                if name_fn(child_tf).strip().lower() in allowed_bones_ci
            ]
            if filtered:
                valid_children = filtered
        if not valid_children:
            spokes.append(cur_path)
            return
        for child_tf in valid_children:
            child_name = name_fn(child_tf)
            all_desc.append(child_name)
            _walk(child_tf, cur_path + [child_name], depth_val + 1)

    _walk(root_tf_id, [root_name], 0)
    return spokes, all_desc


def extract_unity_scene_physbones(
    unity_path: Union[str, Path],
    avatar_name: Optional[str] = None,
    unity_assets_root: Optional[Union[str, Path]] = None,
    fbx_paths: Sequence[Union[str, Path]] = (),
    fallback_prefab_paths: Sequence[Union[str, Path]] = (),
    include_marshmallow_pb: bool = False,
    character_hints: Sequence[str] = (),
    excluded_meshes: Sequence[str] = (),
    active_meshes: Sequence[str] = (),
    prune_orphaned: bool = True,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Fast, general O(N) VRChat Unity scene & nested-prefab VRCPhysBone extractor.

    Resolves direct `VRCPhysBone` (`fileID == 1661641543`, excluding colliders `-1631200402`),
    child `PrefabInstance` hierarchies (`m_SourcePrefab` + `m_Modification` active/tag/property overrides,
    `m_RemovedGameObjects`, and `m_RemovedComponents`), `.fbx.meta` recycle names, `ignoreTransforms`,
    Marshmallow PB presets, and prunes orphaned/unused PhysBones (e.g. old dress PhysBones whose
    meshes were disabled, toggled off via Modular Avatar, deleted, or stripped of active weights).
    """
    resolved_unity = Path(unity_path)
    if not resolved_unity.is_file():
        return {
            "loaded": False,
            "chains": [],
            "marshmallow_breasts": [],
            "orphaned_physbones": [],
            "excluded_meshes": [],
            "warnings": [f"Missing Unity file: {resolved_unity}"],
        }

    if verbose:
        print(f"[PhysBones] Scanning Unity scene {resolved_unity.name} ({avatar_name or 'auto'})...", flush=True)

    scene_doc = _stream_parse_unity_physbone_doc(resolved_unity)
    doc_cache: Dict[Path, Dict[str, Any]] = {resolved_unity: scene_doc}

    # Find target avatar root Transform
    root_tf_id: Optional[str] = None
    selected_name = str(avatar_name or "").strip()
    top_roots: List[Tuple[str, str]] = []
    for tf_id, tf_data in scene_doc["tfs"].items():
        father_ref = tf_data.get("father")
        if not father_ref or father_ref[0] == "0":
            go_ref = tf_data.get("go")
            go_name = scene_doc["gos"].get(go_ref[0], {}).get("name", "") if go_ref else ""
            top_roots.append((tf_id, go_name))

    if selected_name:
        for tf_id, go_name in top_roots:
            if go_name == selected_name:
                root_tf_id = tf_id
                break
        if root_tf_id is None:
            for tf_id, tf_data in scene_doc["tfs"].items():
                go_ref = tf_data.get("go")
                go_name = scene_doc["gos"].get(go_ref[0], {}).get("name", "") if go_ref else ""
                if go_name == selected_name:
                    root_tf_id = tf_id
                    break
    if root_tf_id is None and top_roots:
        # Prefer first root matching hints
        hint_lows = [str(hint_item).strip().lower() for hint_item in character_hints if str(hint_item).strip()]
        for tf_id, go_name in top_roots:
            if any(hint_tok in go_name.lower() for hint_tok in hint_lows):
                root_tf_id = tf_id
                selected_name = go_name
                break
        if root_tf_id is None:
            root_tf_id, selected_name = top_roots[0]

    if root_tf_id is None:
        return {
            "loaded": False,
            "chains": [],
            "marshmallow_breasts": [],
            "orphaned_physbones": [],
            "excluded_meshes": [],
            "warnings": ["Avatar root transform not found"],
        }

    children_tfs: Dict[str, List[str]] = {}
    children_pis: Dict[str, List[str]] = {}
    tfs_by_pi: Dict[str, List[str]] = {}
    for tf_id, tf_data in scene_doc["tfs"].items():
        father_ref = tf_data.get("father")
        if father_ref and father_ref[0] != "0":
            children_tfs.setdefault(father_ref[0], []).append(tf_id)
        pi_ref = tf_data.get("pi")
        if pi_ref and pi_ref[0] != "0":
            tfs_by_pi.setdefault(pi_ref[0], []).append(tf_id)
    for pi_id, pi_data in scene_doc["pis"].items():
        ptf_ref = pi_data.get("parent_tf")
        if ptf_ref and ptf_ref[0] != "0":
            children_pis.setdefault(ptf_ref[0], []).append(pi_id)

    visited_tfs: Set[str] = set()
    visited_pis: Set[str] = set()
    bfs_queue = collections_module.deque([root_tf_id])
    while bfs_queue:
        cur_tf = bfs_queue.popleft()
        if cur_tf in visited_tfs:
            continue
        visited_tfs.add(cur_tf)
        for child_tf in children_tfs.get(cur_tf, []):
            bfs_queue.append(child_tf)
        for child_pi in children_pis.get(cur_tf, []):
            if child_pi not in visited_pis:
                visited_pis.add(child_pi)
                for tf_id in tfs_by_pi.get(child_pi, []):
                    if tf_id not in visited_tfs:
                        bfs_queue.append(tf_id)

    # Collect GUIDs needed from PIs, SkinnedMeshRenderers, and FBX/prefab refs
    needed_guids: Set[str] = set()
    for pi_id in visited_pis:
        pi_entry = scene_doc["pis"][pi_id]
        sp_ref = pi_entry.get("source_prefab")
        if sp_ref and sp_ref[1]:
            needed_guids.add(sp_ref[1])
        for mod_item in pi_entry.get("mods", []):
            obj_ref = mod_item.get("objref")
            if obj_ref and obj_ref[1]:
                needed_guids.add(obj_ref[1])
            tgt_ref = mod_item.get("target")
            if tgt_ref and tgt_ref[1]:
                needed_guids.add(tgt_ref[1])
        for rem_item in list(pi_entry.get("removed_gos", ())) + list(pi_entry.get("removed_comps", ())):
            if rem_item and rem_item[1]:
                needed_guids.add(rem_item[1])
    for tf_id in visited_tfs:
        src_ref = scene_doc["tfs"][tf_id].get("src")
        if src_ref and src_ref[1]:
            needed_guids.add(src_ref[1])
    for smr_data in scene_doc.get("smrs", {}).values():
        mesh_ref = smr_data.get("mesh")
        if mesh_ref and mesh_ref[1]:
            needed_guids.add(mesh_ref[1])

    guid_map = _index_unity_asset_guids(
        unity_assets_root,
        needed_guids,
        seed_files=[resolved_unity] + list(fbx_paths) + list(fallback_prefab_paths),
        character_hints=list(character_hints) + ([selected_name] if selected_name else []),
    )

    try:
        import unity_scene_helper
    except ImportError:
        unity_scene_helper = None
    fbx_name_cache: Dict[Path, Dict[str, str]] = {}

    def _get_doc(doc_p: Path) -> Dict[str, Any]:
        if doc_p not in doc_cache:
            doc_cache[doc_p] = _stream_parse_unity_physbone_doc(doc_p)
        return doc_cache[doc_p]

    # Index any extra mesh FBX GUIDs declared inside visited child .prefab documents
    extra_prefab_guids: Set[str] = set()
    for pi_id in visited_pis:
        sp_ref = scene_doc["pis"][pi_id].get("source_prefab")
        if not sp_ref or not sp_ref[1]:
            continue
        cand_pref = guid_map.get(sp_ref[1])
        if cand_pref and cand_pref.is_file() and cand_pref.suffix.lower() == ".prefab":
            pref_doc_scan = _get_doc(cand_pref)
            for smr_item in pref_doc_scan.get("smrs", {}).values():
                m_ref = smr_item.get("mesh")
                if m_ref and m_ref[1] and m_ref[1] not in guid_map:
                    extra_prefab_guids.add(m_ref[1])
    if extra_prefab_guids:
        guid_map.update(
            _index_unity_asset_guids(
                unity_assets_root,
                extra_prefab_guids,
                seed_files=[resolved_unity] + list(fbx_paths) + list(fallback_prefab_paths),
                character_hints=character_hints,
            )
        )

    def _resolve_fbx_node_name(asset_path: Path, node_fid: str) -> str:
        if not asset_path or not asset_path.is_file() or not node_fid:
            return ""
        low_suf = asset_path.suffix.lower()
        if low_suf == ".fbx" and unity_scene_helper is not None:
            if asset_path not in fbx_name_cache:
                fbx_name_cache[asset_path] = unity_scene_helper._load_prefab_file_id_names(asset_path)
            return str(fbx_name_cache[asset_path].get(node_fid, "") or "")
        if low_suf == ".prefab":
            ext_doc = _get_doc(asset_path)
            ext_tf = ext_doc["tfs"].get(node_fid)
            if ext_tf and ext_tf.get("go"):
                return str(ext_doc["gos"].get(ext_tf["go"][0], {}).get("name", "") or "")
            ext_go = ext_doc["gos"].get(node_fid)
            if ext_go:
                return str(ext_go.get("name", "") or "")
        return ""

    def _resolve_tf_name(doc_obj: Dict[str, Any], tf_id: str) -> str:
        tf_entry = doc_obj["tfs"].get(tf_id)
        if not tf_entry:
            return ""
        go_ref = tf_entry.get("go")
        if go_ref:
            go_entry = doc_obj["gos"].get(go_ref[0])
            if go_entry and go_entry.get("name"):
                return str(go_entry["name"])
        src_ref = tf_entry.get("src")
        if src_ref and src_ref[1]:
            asset_p = guid_map.get(src_ref[1])
            if asset_p and asset_p.is_file():
                resolved_nm = _resolve_fbx_node_name(asset_p, src_ref[0])
                if resolved_nm:
                    return resolved_nm
        return ""

    def _is_scene_tf_active(tf_id: str) -> bool:
        cur_id = tf_id
        while cur_id and cur_id != "0" and cur_id != root_tf_id:
            tf_entry = scene_doc["tfs"].get(cur_id)
            if not tf_entry:
                break
            go_ref = tf_entry.get("go")
            if go_ref:
                go_entry = scene_doc["gos"].get(go_ref[0])
                if go_entry:
                    if go_entry.get("active") is False or go_entry.get("tag") == "EditorOnly":
                        return False
            father_ref = tf_entry.get("father")
            cur_id = father_ref[0] if father_ref else ""
        return True

    def _scene_ancestor_names(tf_id: str) -> List[str]:
        ancestors: List[str] = []
        cur_id = tf_id
        for _step in range(32):
            tf_entry = scene_doc["tfs"].get(cur_id)
            if not tf_entry:
                break
            father_ref = tf_entry.get("father")
            cur_id = father_ref[0] if father_ref else ""
            if not cur_id or cur_id == "0":
                break
            anc_name = _resolve_tf_name(scene_doc, cur_id)
            if anc_name:
                ancestors.append(anc_name)
        return ancestors

    # Identify disabled / replaced / MA-toggled-off / deleted old outfit meshes and removed overrides
    excluded_meshes_ci: Set[str] = {
        str(name_item).strip().lower() for name_item in excluded_meshes if str(name_item).strip()
    }
    active_scene_meshes_ci: Set[str] = {
        str(name_item).strip().lower() for name_item in active_meshes if str(name_item).strip()
    }
    active_mesh_fbx_guids: Set[str] = set()
    opaque_fbx_pi_guids: Set[str] = set()
    ma_discovered_fbxs: List[Path] = []
    orphaned_physbones: List[Dict[str, Any]] = []
    orphaned_seen_keys: Set[Tuple[str, str]] = set()

    def _record_orphan(root_name_str: str, reason_tok: str, parent_bone_str: str = "SKEL_Pelvis") -> None:
        clean_rt = str(root_name_str or "").strip() or "unknown"
        dedup_key = (clean_rt.lower(), reason_tok)
        if dedup_key in orphaned_seen_keys:
            return
        orphaned_seen_keys.add(dedup_key)
        orphaned_physbones.append(
            {
                "root_bone": clean_rt,
                "parent_bone": parent_bone_str,
                "reason": reason_tok,
            }
        )

    def _is_fallback_hair_protected(mesh_nm: str) -> bool:
        return bool(fallback_prefab_paths) and "hair" in str(mesh_nm).lower()

    try:
        import modular_avatar_helper as ma_helper
    except ImportError:
        ma_helper = None

    if ma_helper is not None:
        try:
            ma_plan = ma_helper.build_modular_avatar_bake_plan(
                resolved_unity,
                avatar_name=selected_name or avatar_name or None,
                assets_root=unity_assets_root,
                character_hints=character_hints,
                resolve_materials=False,
            )
            if ma_plan.get("loaded"):
                for dis_mesh in ma_plan.get("disabled_meshes", ()):
                    low_mesh = str(dis_mesh).strip().lower()
                    if low_mesh and not _is_fallback_hair_protected(low_mesh):
                        excluded_meshes_ci.add(low_mesh)
                for act_mesh in ma_plan.get("active_meshes", ()):
                    low_mesh = str(act_mesh).strip().lower()
                    if low_mesh:
                        active_scene_meshes_ci.add(low_mesh)
                for raw_ma_fbx in list(ma_plan.get("base_fbx_paths", ())) + list(ma_plan.get("extra_fbx_paths", ())):
                    if raw_ma_fbx:
                        fbx_obj = Path(raw_ma_fbx)
                        if fbx_obj.is_file() and fbx_obj not in ma_discovered_fbxs:
                            ma_discovered_fbxs.append(fbx_obj)
        except Exception:
            pass

    go_to_tf = {
        tf_data["go"][0]: tf_id
        for tf_id, tf_data in scene_doc["tfs"].items()
        if tf_data.get("go")
    }

    # Check direct SkinnedMeshRenderers in scene subtree
    for _smr_id, smr_data in scene_doc.get("smrs", {}).items():
        if smr_data.get("stripped"):
            continue
        smr_go = smr_data.get("go")
        if not smr_go:
            continue
        smr_tf = go_to_tf.get(smr_go[0])
        if smr_tf not in visited_tfs:
            continue
        go_info = scene_doc["gos"].get(smr_go[0], {})
        go_name = str(go_info.get("name", "") or "").strip()
        mesh_ref = smr_data.get("mesh")
        mesh_asset_nm = ""
        if mesh_ref and mesh_ref[1] and mesh_ref[1] in guid_map:
            mesh_asset_nm = _resolve_fbx_node_name(guid_map[mesh_ref[1]], mesh_ref[0])
        smr_active = _is_scene_tf_active(smr_tf) and bool(smr_data.get("enabled", True))
        if smr_active:
            for cand_nm in (go_name, mesh_asset_nm):
                if cand_nm:
                    active_scene_meshes_ci.add(cand_nm.lower())
            if mesh_ref and mesh_ref[1]:
                active_mesh_fbx_guids.add(mesh_ref[1])
        else:
            for cand_nm in (go_name, mesh_asset_nm):
                if cand_nm and not _is_fallback_hair_protected(cand_nm):
                    excluded_meshes_ci.add(cand_nm.lower())

    # Inspect PrefabInstances for opaque FBX modifications, removed GOs, and prefab SMRs
    for pi_id in sorted(visited_pis, key=lambda val_s: int(val_s)):
        pi_data = scene_doc["pis"][pi_id]
        ptf_ref = pi_data.get("parent_tf")
        ptf_id = ptf_ref[0] if ptf_ref else "0"
        if ptf_id not in visited_tfs:
            continue
        pi_parent_active = _is_scene_tf_active(ptf_id)
        sp_ref = pi_data.get("source_prefab")
        if not sp_ref or not sp_ref[1]:
            continue
        asset_target = guid_map.get(sp_ref[1])
        if not asset_target or not asset_target.is_file():
            continue

        # Record disabled/removed child nodes even on opaque .fbx PrefabInstances
        for rem_item in pi_data.get("removed_gos", ()):
            rem_guid = rem_item[1] or sp_ref[1]
            rem_asset = guid_map.get(rem_guid, asset_target)
            rem_name = _resolve_fbx_node_name(rem_asset, rem_item[0])
            if rem_name and not _is_fallback_hair_protected(rem_name):
                excluded_meshes_ci.add(rem_name.lower())

        for mod_item in pi_data.get("mods", ()):
            m_path = mod_item.get("path", "")
            m_val = mod_item.get("value", "")
            if (
                (m_path == "m_IsActive" and m_val == "0")
                or (m_path == "m_Enabled" and m_val == "0")
                or (m_path == "m_TagString" and m_val == "EditorOnly")
            ):
                tgt_ref = mod_item.get("target")
                if tgt_ref and tgt_ref[0]:
                    tgt_asset = guid_map.get(tgt_ref[1] or sp_ref[1], asset_target)
                    dis_node_nm = _resolve_fbx_node_name(tgt_asset, tgt_ref[0])
                    if dis_node_nm and not _is_fallback_hair_protected(dis_node_nm):
                        excluded_meshes_ci.add(dis_node_nm.lower())

        if asset_target.suffix.lower() == ".fbx":
            opaque_fbx_pi_guids.add(sp_ref[1])
            continue
        if asset_target.suffix.lower() != ".prefab":
            continue

        pref_scan_doc = _get_doc(asset_target)
        scan_mods_by_target: Dict[str, List[Dict[str, Any]]] = {}
        for mod_item in pi_data.get("mods", []):
            tgt_ref = mod_item.get("target")
            if tgt_ref:
                scan_mods_by_target.setdefault(tgt_ref[0], []).append(mod_item)
        scan_removed_gos = {
            (rem_ref[0], rem_ref[1] or sp_ref[1]) for rem_ref in pi_data.get("removed_gos", ())
        }
        scan_removed_go_fids = {pair[0] for pair in scan_removed_gos}
        scan_pref_go_to_tf = {
            tf_d["go"][0]: tid for tid, tf_d in pref_scan_doc["tfs"].items() if tf_d.get("go")
        }

        for _smr_id, smr_raw in pref_scan_doc.get("smrs", {}).items():
            smr_go_ref = smr_raw.get("go")
            if not smr_go_ref:
                continue
            smr_go_id = smr_go_ref[0]
            smr_go_info = pref_scan_doc["gos"].get(smr_go_id, {})
            smr_go_name = str(smr_go_info.get("name", "") or "").strip()
            mesh_ref = smr_raw.get("mesh")
            mesh_asset_nm = ""
            if mesh_ref and mesh_ref[1] and mesh_ref[1] in guid_map:
                mesh_asset_nm = _resolve_fbx_node_name(guid_map[mesh_ref[1]], mesh_ref[0])

            smr_enabled = bool(smr_raw.get("enabled", True))
            for mod_item in scan_mods_by_target.get(_smr_id, ()):
                if mod_item.get("path") == "m_Enabled":
                    smr_enabled = mod_item.get("value") != "0"

            chain_active = pi_parent_active and smr_enabled and (smr_go_id not in scan_removed_go_fids)
            cur_pt = scan_pref_go_to_tf.get(smr_go_id, "")
            while chain_active and cur_pt and cur_pt != "0":
                pt_entry = pref_scan_doc["tfs"].get(cur_pt)
                if not pt_entry:
                    break
                cgo_id = pt_entry.get("go", ("0",))[0]
                if cgo_id in scan_removed_go_fids:
                    chain_active = False
                    break
                cgo = pref_scan_doc["gos"].get(cgo_id, {})
                c_active = cgo.get("active", True)
                c_tag = cgo.get("tag", "")
                for mod_item in scan_mods_by_target.get(cgo_id, ()):
                    if mod_item.get("path") == "m_IsActive":
                        c_active = mod_item.get("value") != "0"
                    elif mod_item.get("path") == "m_TagString":
                        c_tag = mod_item.get("value", "")
                if not c_active or c_tag == "EditorOnly":
                    chain_active = False
                    break
                cur_pt = pt_entry.get("father", ("0",))[0]

            if chain_active:
                for cand_nm in (smr_go_name, mesh_asset_nm):
                    if cand_nm:
                        active_scene_meshes_ci.add(cand_nm.lower())
                if mesh_ref and mesh_ref[1]:
                    active_mesh_fbx_guids.add(mesh_ref[1])
            else:
                for cand_nm in (smr_go_name, mesh_asset_nm):
                    if cand_nm and not _is_fallback_hair_protected(cand_nm):
                        excluded_meshes_ci.add(cand_nm.lower())

    # Resolve active avatar FBXs (explicit inputs + MA outfit FBXs + active SkinnedMeshRenderer .fbx refs)
    effective_fbxs: List[Union[str, Path]] = []
    seen_fbx_resolved: Set[str] = set()

    def _add_effective_fbx(cand_item: Union[str, Path]) -> None:
        if not cand_item:
            return
        cand_obj = Path(cand_item)
        if not cand_obj.is_file() or cand_obj.suffix.lower() != ".fbx":
            return
        res_key = str(cand_obj.resolve())
        if res_key not in seen_fbx_resolved:
            seen_fbx_resolved.add(res_key)
            effective_fbxs.append(cand_obj)

    for raw_fbx_in in fbx_paths:
        _add_effective_fbx(raw_fbx_in)
    for raw_ma_fbx in ma_discovered_fbxs:
        _add_effective_fbx(raw_ma_fbx)
    for act_fguid in active_mesh_fbx_guids:
        act_asset = guid_map.get(act_fguid)
        if act_asset is not None:
            _add_effective_fbx(act_asset)
    if not effective_fbxs:
        for asset_p in guid_map.values():
            _add_effective_fbx(asset_p)

    all_fbx_bones, _init_weighted, fbx_parent_map, mesh_weights_by_file, has_skin_clusters = (
        _inspect_fbx_weights_detailed(effective_fbxs, excluded_meshes=sorted(excluded_meshes_ci))
    )

    # For YAML-expanded FBXs (e.g. inside avatar .prefab), any FBX mesh deleted from the active hierarchy
    # is also excluded so deleted old dresses do not keep their bones alive in weighted_fbx_bones.
    for fbx_item_p, file_mesh_map in mesh_weights_by_file.items():
        fbx_guid = _read_unity_meta_guid(fbx_item_p)
        if fbx_guid and fbx_guid in active_mesh_fbx_guids and fbx_guid not in opaque_fbx_pi_guids:
            for mesh_low in file_mesh_map:
                if mesh_low not in active_scene_meshes_ci and not _is_fallback_hair_protected(mesh_low):
                    excluded_meshes_ci.add(mesh_low)

    weighted_fbx_bones: Set[str] = set()
    disabled_mesh_all_bones: Set[str] = set()
    for file_mesh_map in mesh_weights_by_file.values():
        for mesh_low, weight_set in file_mesh_map.items():
            if mesh_low in excluded_meshes_ci:
                disabled_mesh_all_bones.update(weight_set)
            else:
                weighted_fbx_bones.update(weight_set)
    disabled_only_bones_ci: Set[str] = disabled_mesh_all_bones - weighted_fbx_bones

    if not prune_orphaned:
        allowed_bones_ci: Optional[Set[str]] = None
    elif has_skin_clusters:
        allowed_bones_ci = weighted_fbx_bones
    else:
        allowed_bones_ci = all_fbx_bones or None

    def _pb_to_record(
        pb_raw: Dict[str, Any],
        root_name: str,
        spoke_bones: List[str],
        all_desc: List[str],
        ancestors: List[str],
        default_parent_override: Optional[Tuple[str, int]] = None,
    ) -> Dict[str, Any]:
        parent_name, parent_tag = (
            default_parent_override
            if default_parent_override is not None
            else resolve_parent_bone_from_unity_chain(ancestors)
        )

        def _fval(field_key: str, default_num: float) -> float:
            try:
                return float(pb_raw.get(field_key, default_num))
            except (TypeError, ValueError):
                return default_num

        def _ival(field_key: str, default_num: int) -> int:
            try:
                return int(float(pb_raw.get(field_key, default_num)))
            except (TypeError, ValueError):
                return default_num

        return {
            "root_bone": root_name,
            "spoke_bones": list(spoke_bones),
            "all_descendants": list(all_desc),
            "parent_bone": parent_name,
            "parent_bone_tag": parent_tag,
            "version": _ival("version", 1),
            "integration_type": _ival("integration_type", 0),
            "multi_child_type": _ival("multi_child_type", 0),
            "endpoint_position": tuple(pb_raw.get("endpoint_position", (0.0, 0.0, 0.0))),
            "pull": _fval("pull", 0.2),
            "spring": _fval("spring", 0.35),
            "stiffness": _fval("stiffness", 0.2),
            "gravity": _fval("gravity", 0.0),
            "gravity_falloff": _fval("gravity_falloff", 0.0),
            "immobile_type": _ival("immobile_type", 0),
            "immobile": _fval("immobile", 0.3),
            "allow_collision": _ival("allow_collision", 1),
            "radius": _fval("radius", 0.025),
            "radius_curve": list(pb_raw.get("radiusCurve", [])),
            "limit_type": _ival("limit_type", 1),
            "max_angle_x": _fval("max_angle_x", 50.0),
            "max_angle_x_curve": list(pb_raw.get("maxAngleXCurve", [])),
            "max_angle_z": _fval("max_angle_z", 45.0),
            "limit_rotation": tuple(pb_raw.get("limit_rotation", (0.0, 0.0, 0.0))),
            "allow_grabbing": _ival("allow_grabbing", 1),
            "allow_posing": _ival("allow_posing", 1),
            "grab_movement": _fval("grab_movement", 0.5),
            "max_stretch": _fval("max_stretch", 0.0),
            "max_squish": _fval("max_squish", 0.0),
            "stretch_motion": _fval("stretch_motion", 0.0),
            "is_animated": _ival("is_animated", 1),
        }

    extracted_spokes: List[Dict[str, Any]] = []

    # 1. Direct scene VRCPhysBones under avatar root
    for pb_id, pb_data in scene_doc["pbs"].items():
        if pb_data.get("stripped") or pb_data.get("enabled", True) is False:
            continue
        go_ref = pb_data.get("go")
        if not go_ref:
            continue
        tf_id = go_to_tf.get(go_ref[0])
        if tf_id not in visited_tfs or not _is_scene_tf_active(tf_id):
            continue
        comp_go_name = _resolve_tf_name(scene_doc, tf_id)
        rt_ref = pb_data.get("root_tf")
        if rt_ref and rt_ref[0] != "0":
            if rt_ref[1] or rt_ref[0] not in scene_doc["tfs"]:
                _record_orphan(comp_go_name or pb_id, "dangling_root_transform")
                continue
            rt_tid = rt_ref[0]
            rt_name = _resolve_tf_name(scene_doc, rt_tid) or comp_go_name
            if rt_tid not in visited_tfs or not _is_scene_tf_active(rt_tid):
                _record_orphan(
                    rt_name or pb_id,
                    "inactive_root_transform",
                    resolve_parent_bone_from_unity_chain(_scene_ancestor_names(rt_tid))[0],
                )
                continue
        else:
            rt_tid = tf_id
            rt_name = comp_go_name
        if not rt_name:
            continue
        ignored_ids = {ref[0] for ref in pb_data.get("ignored", []) if ref and ref[0] != "0"}
        if rt_tid in ignored_ids:
            continue
        spokes, all_desc = _collect_linear_spokes(
            rt_tid,
            children_tfs,
            lambda tid_arg: _resolve_tf_name(scene_doc, tid_arg),
            ignored_ids,
            allowed_bones_ci=allowed_bones_ci,
        )
        ancestors = _scene_ancestor_names(rt_tid)
        parent_nm_diag, _parent_tag_diag = resolve_parent_bone_from_unity_chain(ancestors)
        # Skip gimmick or old-dress orphaned PBs whose bones have zero active skin weights
        if allowed_bones_ci is not None and not any(
            bone_str.strip().lower() in allowed_bones_ci for bone_str in all_desc
        ):
            orphan_reason = (
                "disabled_old_outfit_mesh"
                if any(bone_str.strip().lower() in disabled_only_bones_ci for bone_str in all_desc)
                else "no_active_mesh_weights"
            )
            _record_orphan(rt_name, orphan_reason, parent_nm_diag)
            continue
        for spoke_bones in spokes:
            if allowed_bones_ci is not None and not any(
                bone_str.strip().lower() in allowed_bones_ci for bone_str in spoke_bones
            ):
                spoke_rt = spoke_bones[0] if spoke_bones else rt_name
                orphan_reason = (
                    "disabled_old_outfit_mesh"
                    if any(bone_str.strip().lower() in disabled_only_bones_ci for bone_str in spoke_bones)
                    else "no_active_mesh_weights"
                )
                _record_orphan(spoke_rt, orphan_reason, parent_nm_diag)
                continue
            extracted_spokes.append(_pb_to_record(pb_data, rt_name, spoke_bones, all_desc, ancestors))

    # 2. Active child PrefabInstance VRCPhysBones (e.g. MA Shinano hair, outfits)
    for pi_id in sorted(visited_pis, key=lambda val_s: int(val_s)):
        pi_data = scene_doc["pis"][pi_id]
        ptf_ref = pi_data.get("parent_tf")
        ptf_id = ptf_ref[0] if ptf_ref else "0"
        if ptf_id not in visited_tfs or not _is_scene_tf_active(ptf_id):
            continue
        sp_ref = pi_data.get("source_prefab")
        if not sp_ref or not sp_ref[1]:
            continue
        prefab_path = guid_map.get(sp_ref[1])
        if not prefab_path or not prefab_path.is_file() or prefab_path.suffix.lower() != ".prefab":
            continue
        pref_doc = _get_doc(prefab_path)
        mods_by_target: Dict[str, List[Dict[str, Any]]] = {}
        for mod_item in pi_data.get("mods", []):
            target_ref = mod_item.get("target")
            if target_ref:
                mods_by_target.setdefault(target_ref[0], []).append(mod_item)
        pi_removed_go_fids = {
            rem_ref[0]
            for rem_ref in pi_data.get("removed_gos", ())
            if rem_ref and (not rem_ref[1] or rem_ref[1] == sp_ref[1])
        }
        pi_removed_comp_fids = {
            rem_ref[0]
            for rem_ref in pi_data.get("removed_comps", ())
            if rem_ref and (not rem_ref[1] or rem_ref[1] == sp_ref[1])
        }

        # Check root GO override in PI (active/EditorOnly)
        pref_root_tid = next(
            (tid for tid, tf_d in pref_doc["tfs"].items() if not tf_d.get("father") or tf_d["father"][0] == "0"),
            None,
        )
        if pref_root_tid and pref_doc["tfs"][pref_root_tid].get("go"):
            rgo_id = pref_doc["tfs"][pref_root_tid]["go"][0]
            rgo = pref_doc["gos"].get(rgo_id, {})
            root_active = rgo.get("active", True)
            root_tag = rgo.get("tag", "")
            for mod_item in mods_by_target.get(rgo_id, []):
                if mod_item.get("path") == "m_IsActive":
                    root_active = mod_item.get("value") != "0"
                elif mod_item.get("path") == "m_TagString":
                    root_tag = mod_item.get("value", "")
            if not root_active or root_tag == "EditorOnly" or rgo_id in pi_removed_go_fids:
                continue

        pref_children: Dict[str, List[str]] = {}
        for tid, tf_d in pref_doc["tfs"].items():
            fref = tf_d.get("father")
            if fref and fref[0] != "0":
                pref_children.setdefault(fref[0], []).append(tid)
        pref_go_to_tf = {
            tf_d["go"][0]: tid for tid, tf_d in pref_doc["tfs"].items() if tf_d.get("go")
        }
        pi_ancestors = [_resolve_tf_name(scene_doc, ptf_id)] + _scene_ancestor_names(ptf_id)

        def _is_pref_tf_chain_active(start_tid: str) -> bool:
            cur_pt = start_tid
            while cur_pt and cur_pt != "0":
                pt_entry = pref_doc["tfs"].get(cur_pt)
                if not pt_entry:
                    break
                cgo_id = pt_entry.get("go", ("0",))[0]
                if cgo_id in pi_removed_go_fids:
                    return False
                cgo = pref_doc["gos"].get(cgo_id, {})
                c_active = cgo.get("active", True)
                c_tag = cgo.get("tag", "")
                for mod_item in mods_by_target.get(cgo_id, []):
                    if mod_item.get("path") == "m_IsActive":
                        c_active = mod_item.get("value") != "0"
                    elif mod_item.get("path") == "m_TagString":
                        c_tag = mod_item.get("value", "")
                if not c_active or c_tag == "EditorOnly":
                    return False
                cur_pt = pt_entry.get("father", ("0",))[0]
            return True

        for pb_id, pb_raw in pref_doc["pbs"].items():
            if pb_id in pi_removed_comp_fids:
                go_ref_rem = pb_raw.get("go")
                rem_name = str(pref_doc["gos"].get(go_ref_rem[0], {}).get("name", pb_id)) if go_ref_rem else pb_id
                _record_orphan(rem_name, "removed_prefab_override")
                continue
            eff_pb = dict(pb_raw)
            eff_enabled = eff_pb.get("enabled", True)
            for mod_item in mods_by_target.get(pb_id, []):
                m_path = mod_item.get("path", "")
                if m_path == "m_Enabled":
                    eff_enabled = mod_item.get("value") != "0"
                elif m_path in (
                    "pull", "spring", "stiffness", "gravity", "immobile",
                    "limitType", "maxAngleX", "maxAngleZ",
                ):
                    key_map = {
                        "limitType": "limit_type",
                        "maxAngleX": "max_angle_x",
                        "maxAngleZ": "max_angle_z",
                    }.get(m_path, m_path)
                    eff_pb[key_map] = mod_item.get("value")
            if not eff_enabled:
                continue
            go_ref = eff_pb.get("go")
            if not go_ref:
                continue
            if go_ref[0] in pi_removed_go_fids:
                _record_orphan(str(pref_doc["gos"].get(go_ref[0], {}).get("name", pb_id)), "removed_prefab_override")
                continue
            pref_tid = pref_go_to_tf.get(go_ref[0])
            if not pref_tid or not _is_pref_tf_chain_active(pref_tid):
                continue

            comp_pref_name = _resolve_tf_name(pref_doc, pref_tid)
            rt_ref = eff_pb.get("root_tf")
            if rt_ref and rt_ref[0] != "0":
                if rt_ref[0] in {pref_doc["tfs"][tid_k].get("go", ("0",))[0] for tid_k in ()} or (
                    rt_ref[0] in pref_doc["tfs"] and pref_doc["tfs"][rt_ref[0]].get("go", ("0",))[0] in pi_removed_go_fids
                ):
                    _record_orphan(_resolve_tf_name(pref_doc, rt_ref[0]) or comp_pref_name or pb_id, "removed_prefab_override")
                    continue
                if (rt_ref[1] and rt_ref[1] != sp_ref[1]) or rt_ref[0] not in pref_doc["tfs"]:
                    _record_orphan(comp_pref_name or pb_id, "dangling_root_transform")
                    continue
                rt_tid = rt_ref[0]
                rt_name = _resolve_tf_name(pref_doc, rt_tid) or comp_pref_name
                if not _is_pref_tf_chain_active(rt_tid):
                    _record_orphan(rt_name or pb_id, "inactive_root_transform")
                    continue
            else:
                rt_tid = pref_tid
                rt_name = comp_pref_name
            if not rt_name:
                continue
            ignored_ids = {ref[0] for ref in eff_pb.get("ignored", []) if ref and ref[0] != "0"}
            if rt_tid in ignored_ids:
                continue
            spokes, all_desc = _collect_linear_spokes(
                rt_tid,
                pref_children,
                lambda tid_arg, pd_ref=pref_doc: _resolve_tf_name(pd_ref, tid_arg),
                ignored_ids,
                allowed_bones_ci=allowed_bones_ci,
            )
            anc_names: List[str] = []
            cur_anc = rt_tid
            for _step in range(16):
                cur_anc = pref_doc["tfs"].get(cur_anc, {}).get("father", ("0",))[0]
                if not cur_anc or cur_anc == "0":
                    break
                aname = _resolve_tf_name(pref_doc, cur_anc)
                if aname:
                    anc_names.append(aname)
            anc_names.extend(pi_ancestors)
            pref_parent_diag, _pref_ptag_diag = resolve_parent_bone_from_unity_chain(anc_names)
            if allowed_bones_ci is not None and not any(
                bone_str.strip().lower() in allowed_bones_ci for bone_str in all_desc
            ):
                orphan_reason = (
                    "disabled_old_outfit_mesh"
                    if any(bone_str.strip().lower() in disabled_only_bones_ci for bone_str in all_desc)
                    else "no_active_mesh_weights"
                )
                _record_orphan(rt_name, orphan_reason, pref_parent_diag)
                continue
            for spoke_bones in spokes:
                if allowed_bones_ci is not None and not any(
                    bone_str.strip().lower() in allowed_bones_ci for bone_str in spoke_bones
                ):
                    spoke_rt = spoke_bones[0] if spoke_bones else rt_name
                    orphan_reason = (
                        "disabled_old_outfit_mesh"
                        if any(bone_str.strip().lower() in disabled_only_bones_ci for bone_str in spoke_bones)
                        else "no_active_mesh_weights"
                    )
                    _record_orphan(spoke_rt, orphan_reason, pref_parent_diag)
                    continue
                extracted_spokes.append(_pb_to_record(eff_pb, rt_name, spoke_bones, all_desc, anc_names))

    # 3. Fallback prefabs (e.g. Shinano.prefab when vrc2gtav.cfg sets custom_hair = default while scene had EditorOnly hair)
    seen_root_bones_ci = {rec["root_bone"].strip().lower() for rec in extracted_spokes}
    for fb_pref_path in fallback_prefab_paths:
        fb_p = Path(fb_pref_path)
        if not fb_p.is_file():
            continue
        fb_doc = _get_doc(fb_p)
        fb_children: Dict[str, List[str]] = {}
        fb_go_to_tf: Dict[str, str] = {}
        for tid, tf_d in fb_doc["tfs"].items():
            fref = tf_d.get("father")
            if fref and fref[0] != "0":
                fb_children.setdefault(fref[0], []).append(tid)
            if tf_d.get("go"):
                fb_go_to_tf[tf_d["go"][0]] = tid
        # Also resolve .fbx.meta fileIDs used inside fallback prefab
        for tid, tf_d in fb_doc["tfs"].items():
            sref = tf_d.get("src")
            if sref and sref[1] and sref[1] not in guid_map and fbx_paths:
                for cand_fbx in fbx_paths:
                    if cand_fbx and Path(cand_fbx).is_file():
                        guid_map[sref[1]] = Path(cand_fbx)
                        break

        for pb_id, pb_raw in fb_doc["pbs"].items():
            if not pb_raw.get("enabled", True):
                continue
            go_ref = pb_raw.get("go")
            if not go_ref:
                continue
            tid = fb_go_to_tf.get(go_ref[0])
            if not tid:
                continue
            rt_ref = pb_raw.get("root_tf")
            rt_tid = rt_ref[0] if (rt_ref and rt_ref[0] != "0" and rt_ref[0] in fb_doc["tfs"]) else tid
            rt_name = _resolve_tf_name(fb_doc, rt_tid) or _resolve_tf_name(fb_doc, tid)
            if not rt_name or rt_name.strip().lower() in seen_root_bones_ci:
                continue
            if "physbone_" in rt_name.lower() or "breast" in rt_name.lower():
                continue
            spokes, all_desc = _collect_linear_spokes(
                rt_tid,
                fb_children,
                lambda tid_arg, fd_ref=fb_doc: _resolve_tf_name(fd_ref, tid_arg),
                set(),
                allowed_bones_ci=allowed_bones_ci,
            )
            if allowed_bones_ci is not None and not any(
                bone_str.strip().lower() in allowed_bones_ci for bone_str in all_desc
            ):
                continue
            seen_root_bones_ci.add(rt_name.strip().lower())
            anc_names = []
            cur_anc = rt_tid
            for _step in range(16):
                cur_anc = fb_doc["tfs"].get(cur_anc, {}).get("father", ("0",))[0]
                if not cur_anc or cur_anc == "0":
                    break
                aname = _resolve_tf_name(fb_doc, cur_anc)
                if aname:
                    anc_names.append(aname)
            for spoke_bones in spokes:
                extracted_spokes.append(_pb_to_record(pb_raw, rt_name, spoke_bones, all_desc, anc_names))

    # 3b. Recover direct base-armature PBs tagged EditorOnly when custom_hair=default fallback is active
    if fallback_prefab_paths:
        for pb_id, pb_data in scene_doc["pbs"].items():
            if pb_data.get("stripped") or pb_data.get("enabled", True) is False:
                continue
            go_ref = pb_data.get("go")
            if not go_ref:
                continue
            go_info = scene_doc["gos"].get(go_ref[0], {})
            # Only recover direct base armature objects (not disabled third-party PrefabInstance objects)
            if go_info.get("pi") and go_info["pi"][0] != "0":
                continue
            tf_id = go_to_tf.get(go_ref[0])
            if tf_id not in visited_tfs or go_info.get("active") is False:
                continue
            rt_ref = pb_data.get("root_tf")
            rt_tid = rt_ref[0] if (rt_ref and rt_ref[0] != "0" and not rt_ref[1] and rt_ref[0] in scene_doc["tfs"]) else tf_id
            rt_name = _resolve_tf_name(scene_doc, rt_tid) or _resolve_tf_name(scene_doc, tf_id)
            if not rt_name or rt_name.strip().lower() in seen_root_bones_ci:
                continue
            ignored_ids = {ref[0] for ref in pb_data.get("ignored", []) if ref and ref[0] != "0"}
            spokes, all_desc = _collect_linear_spokes(
                rt_tid,
                children_tfs,
                lambda tid_arg: _resolve_tf_name(scene_doc, tid_arg),
                ignored_ids,
                allowed_bones_ci=allowed_bones_ci,
            )
            if allowed_bones_ci is not None and not any(
                bone_str.strip().lower() in allowed_bones_ci for bone_str in all_desc
            ):
                continue
            seen_root_bones_ci.add(rt_name.strip().lower())
            ancestors = _scene_ancestor_names(rt_tid)
            for spoke_bones in spokes:
                extracted_spokes.append(_pb_to_record(pb_data, rt_name, spoke_bones, all_desc, ancestors))

    # 4. Marshmallow PB overrides (Breast_1.L/R or Breast_L/R)
    marshmallow_breasts: List[Dict[str, Any]] = []
    if include_marshmallow_pb:
        marshmallow_breasts = _collect_marshmallow_pb_overrides(
            scene_doc,
            visited_pis,
            guid_map,
            doc_cache,
            unity_assets_root=unity_assets_root,
            is_tf_active_fn=_is_scene_tf_active,
        )
        for mb_rec in marshmallow_breasts:
            mb_root_low = mb_rec["root_bone"].strip().lower()
            child_chain = [mb_rec["root_bone"]]
            for cand_b in sorted(all_fbx_bones):
                if fbx_parent_map.get(cand_b) == mb_root_low:
                    child_chain.append(cand_b)
                    break
            mb_rec["spoke_bones"] = child_chain
            mb_rec["all_descendants"] = list(child_chain)
            extracted_spokes = [
                item for item in extracted_spokes
                if item["root_bone"].strip().lower() != mb_root_low
            ]
            extracted_spokes.append(mb_rec)

    # Guarantee symmetry pair when one Breast side exists (e.g. Franklin Breast_1.R active while Breast_1.L was off)
    breast_sides = {
        ("L" if rec["root_bone"].lower().endswith((".l", "_l")) else ("R" if rec["root_bone"].lower().endswith((".r", "_r")) else "")): rec
        for rec in extracted_spokes
        if "breast" in rec["root_bone"].lower()
    }
    if "R" in breast_sides and "L" not in breast_sides:
        clone = dict(breast_sides["R"])
        clone["root_bone"] = regex_module.sub(r"([._])R$", r"\1L", clone["root_bone"])
        clone["spoke_bones"] = [regex_module.sub(r"([._])R(\b|$)", r"\1L\2", bname) for bname in clone["spoke_bones"]]
        extracted_spokes.append(clone)
    elif "L" in breast_sides and "R" not in breast_sides:
        clone = dict(breast_sides["L"])
        clone["root_bone"] = regex_module.sub(r"([._])L$", r"\1R", clone["root_bone"])
        clone["spoke_bones"] = [regex_module.sub(r"([._])L(\b|$)", r"\1R\2", bname) for bname in clone["spoke_bones"]]
        extracted_spokes.append(clone)

    if orphaned_physbones:
        preview_orphans = ", ".join(
            f"{item['root_bone']} ({item['reason']})" for item in orphaned_physbones[:8]
        )
        extra_suffix = f", +{len(orphaned_physbones) - 8} more" if len(orphaned_physbones) > 8 else ""
        print(
            f"[PHYSBONES] Excluded {len(orphaned_physbones)} orphaned/unused PhysBone chain(s): "
            f"{preview_orphans}{extra_suffix}",
            flush=True,
        )

    return {
        "loaded": True,
        "source_path": str(resolved_unity),
        "root_name": selected_name,
        "chains": extracted_spokes,
        "marshmallow_breasts": marshmallow_breasts,
        "fbx_weighted_bones": sorted(weighted_fbx_bones),
        "orphaned_physbones": orphaned_physbones,
        "excluded_meshes": sorted(excluded_meshes_ci),
        "warnings": [],
    }


def _match_extracted_unity_params(
    template_chain_key: str,
    template_src_bones: Tuple[str, ...],
    extracted_spokes: Sequence[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Find the extracted Unity PhysBone record matching a packed chain spec."""
    src_lows = [src_name.strip().lower() for src_name in template_src_bones]
    root_low = src_lows[0] if src_lows else template_chain_key.strip().lower()
    key_low = template_chain_key.strip().lower()

    for rec in extracted_spokes:
        if rec["root_bone"].strip().lower() == root_low:
            return rec
    for rec in extracted_spokes:
        if rec["root_bone"].strip().lower() == key_low:
            return rec
    for rec in extracted_spokes:
        rec_root = rec["root_bone"].strip().lower()
        if rec_root in src_lows:
            return rec
    for rec in extracted_spokes:
        desc_lows = {desc_b.strip().lower() for desc_b in rec.get("all_descendants", ())}
        spoke_lows = {spk_b.strip().lower() for spk_b in rec.get("spoke_bones", ())}
        if root_low in desc_lows or root_low in spoke_lows:
            return rec
    # Prefix match fallback (e.g. Skirt_FrontB -> Skirt)
    prefix_tok = root_low.split(".", 1)[0].rstrip("0123456789")
    if prefix_tok and len(prefix_tok) >= 2:
        for rec in extracted_spokes:
            if rec["root_bone"].strip().lower().startswith(prefix_tok):
                return rec
    return None


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
        if is_pair_unit and nxt_entry is not None:
            pair_min_cost = 4
            if allocated_bones + pair_min_cost <= max_custom_bones:
                kept_units.append([cur_entry, nxt_entry])
                allocated_bones += pair_min_cost
            else:
                discarded_entries.append((cur_entry, "rage_budget_pair_overflow"))
                discarded_entries.append((nxt_entry, "rage_budget_pair_overflow"))
            cursor_idx += 2
        else:
            single_min_cost = 2
            if allocated_bones + single_min_cost <= max_custom_bones and (
                not discarded_entries or cur_entry["score_info"]["tier"] <= 5
            ):
                kept_units.append([cur_entry])
                allocated_bones += single_min_cost
            else:
                discarded_entries.append((cur_entry, "rage_budget_overflow"))
            cursor_idx += 1

    # Pass 2: Upgrade highest-priority kept >=3-spoke chains from 2 -> 3 bones with leftover slack
    slack_bones = max(0, int(max_custom_bones) - allocated_bones)
    for unit_items in kept_units:
        if slack_bones <= 0:
            break
        extra_needed = len(unit_items)
        if slack_bones >= extra_needed and all(len(item_rec["rep_spokes"]) >= 3 for item_rec in unit_items):
            for item_rec in unit_items:
                item_rec["seg_slots"] = 3
            slack_bones -= extra_needed

    kept_flat = [item_rec for unit_items in kept_units for item_rec in unit_items]
    used_tags: Set[int] = set(PARENT_BONE_TAGS.values())
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
            sampled_src = [rep_spokes[0], rep_spokes[len(rep_spokes) // 2], rep_spokes[-1]]
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


def _parse_quat_string(raw_val: str) -> Tuple[float, float, float, float]:
    """Parse a comma-separated quaternion string (X, Y, Z, W)."""
    rot_parts = [
        float(val_str.strip())
        for val_str in str(raw_val).split(",")
        if val_str.strip()
    ]
    if len(rot_parts) >= 4:
        return (rot_parts[0], rot_parts[1], rot_parts[2], rot_parts[3])
    return (0.0, 0.0, 0.0, 1.0)


def _load_ini_chain_records(ini_path: Path) -> List[Dict[str, object]]:
    """Parse existing [Chain_*] sections from GTAVPhysBones.ini into record dicts."""
    if not ini_path.is_file():
        return []
    parser = ConfigParser()
    parser.optionxform = str
    with ini_path.open("r", encoding="utf-8", errors="replace") as handle:
        parser.read_file(handle)

    records: List[Dict[str, object]] = []
    chain_secs = [sec_item for sec_item in parser.sections() if sec_item.startswith("Chain_")]
    chain_secs.sort(key=lambda sec_item: int(sec_item.split("_", 1)[1]) if sec_item.split("_", 1)[1].isdigit() else 0)
    for sec_name in chain_secs:
        sec = parser[sec_name]
        bone_count = sec.getint("bone_count", 0)
        bones: List[Dict[str, object]] = []
        for idx in range(bone_count):
            prefix = f"bone_{idx}_"
            loc_pos = parse_vec3_string(sec.get(prefix + "local_pos", "0, 0, 0"))
            loc_rot = _parse_quat_string(sec.get(prefix + "local_rot", "0, 0, 0, 1"))
            lim_axis = parse_vec3_string(sec.get(prefix + "limit_axis", "0, 1, 0"), (0.0, 1.0, 0.0))
            bones.append(
                {
                    "name": sec.get(prefix + "name", ""),
                    "tag": sec.getint(prefix + "tag", 0),
                    "max_angle": sec.getfloat(prefix + "max_angle", 50.0),
                    "local_pos": loc_pos,
                    "local_rot": loc_rot,
                    "limit_axis_local": lim_axis,
                }
            )
        records.append(
            {
                "name": sec.get("name", sec_name),
                "parent_bone_tag": sec.getint("parent_bone_tag", SKEL_HEAD_TAG),
                "config": {
                    "integration_type": sec.getint("integration_type", 0),
                    "pull": sec.getfloat("pull", 0.2),
                    "spring": sec.getfloat("spring", 0.35),
                    "stiffness": sec.getfloat("stiffness", 0.2),
                    "gravity": sec.getfloat("gravity", 0.0),
                    "gravity_falloff": sec.getfloat("gravity_falloff", 0.0),
                    "immobile": sec.getfloat("immobile", 0.3),
                    "limit_type": sec.getint("limit_type", 1),
                    "max_angle_x": sec.getfloat("max_angle_x", 50.0),
                    "max_angle_z": sec.getfloat("max_angle_z", 45.0),
                    "is_animated": sec.getint("is_animated", 1),
                },
                "bones": bones,
            }
        )
    return records


def _load_ini_blink_profiles(ini_path: Path) -> List[Dict[str, object]]:
    """Parse existing [Blink_*] sections from GTAVPhysBones.ini into profile dicts."""
    if not ini_path.is_file():
        return []
    parser = ConfigParser()
    parser.optionxform = str
    with ini_path.open("r", encoding="utf-8", errors="replace") as handle:
        parser.read_file(handle)

    profiles: List[Dict[str, object]] = []
    blink_secs = [sec_item for sec_item in parser.sections() if sec_item.startswith("Blink_")]
    blink_secs.sort(
        key=lambda sec_item: int(sec_item.split("_", 1)[1])
        if sec_item.split("_", 1)[1].isdigit()
        else 0
    )
    for sec_name in blink_secs:
        sec = parser[sec_name]
        bone_count = sec.getint("bone_count", 0)
        bones: List[Dict[str, object]] = []
        for idx in range(bone_count):
            prefix = f"bone_{idx}_"
            loc_pos = parse_vec3_string(sec.get(prefix + "local_pos", "0, 0, 0"))
            loc_rot = _parse_quat_string(sec.get(prefix + "local_rot", "0, 0, 0, 1"))
            delta_pos = parse_vec3_string(sec.get(prefix + "delta_pos", "0, 0, 0"))
            delta_rot = _parse_quat_string(sec.get(prefix + "delta_rot", "0, 0, 0, 1"))
            bones.append(
                {
                    "name": sec.get(prefix + "name", ""),
                    "tag": sec.getint(prefix + "tag", 0),
                    "parent_tag": sec.getint(prefix + "parent_tag", 0),
                    "local_pos": loc_pos,
                    "local_rot": loc_rot,
                    "delta_pos": delta_pos,
                    "delta_rot": delta_rot,
                }
            )
        profiles.append(
            {
                "model": sec.get("model", "all").strip().lower(),
                "enabled": sec.getint("enabled", 1),
                "min_interval": sec.getfloat("min_interval", 2.6),
                "max_interval": sec.getfloat("max_interval", 6.0),
                "blink_duration": sec.getfloat("blink_duration", 0.25),
                "double_blink_chance": sec.getfloat("double_blink_chance", 0.18),
                "max_blink": sec.getfloat("max_blink", 1.0),
                "bones": bones,
            }
        )
    return profiles


def merge_physbone_asi_ini(
    ini_path: str | Path,
    chain_records: Sequence[Dict[str, object]],
    own_prefixes: Sequence[str] = (),
    target_ped_model: str = "all",
    extra_sync_paths: Sequence[str | Path] = (),
    blink_profiles: Optional[Sequence[Dict[str, object]]] = None,
    own_blink_models: Sequence[str] = (),
) -> Path:
    """
    Merge new chain_records (and optional blink_profiles) into ini_path, replacing
    chains/blink profiles belonging to the current ped while preserving other
    protagonists' entries, then sync copies across all target paths.
    """
    resolved_ini = Path(ini_path)
    existing = _load_ini_chain_records(resolved_ini)
    if not existing:
        for alt_path in extra_sync_paths:
            alt_records = _load_ini_chain_records(Path(alt_path))
            if alt_records:
                existing = alt_records
                break

    new_names = {str(rec["name"]) for rec in chain_records}
    merged: List[Dict[str, object]] = []
    for rec in existing:
        rec_name = str(rec.get("name", ""))
        if rec_name in new_names:
            continue
        if any(rec_name.startswith(pref) for pref in own_prefixes):
            continue
        merged.append(rec)
    merged.extend(chain_records)

    existing_blinks = _load_ini_blink_profiles(resolved_ini)
    if not existing_blinks:
        for alt_path in extra_sync_paths:
            alt_blinks = _load_ini_blink_profiles(Path(alt_path))
            if alt_blinks:
                existing_blinks = alt_blinks
                break

    merged_blinks: List[Dict[str, object]] = []
    if blink_profiles is None and not own_blink_models:
        merged_blinks = list(existing_blinks)
    else:
        replaced_models = {str(model_name).strip().lower() for model_name in own_blink_models if str(model_name).strip()}
        if blink_profiles:
            for prof_item in blink_profiles:
                model_key = str(prof_item.get("model", "")).strip().lower()
                if model_key:
                    replaced_models.add(model_key)
        for prof_item in existing_blinks:
            model_key = str(prof_item.get("model", "")).strip().lower()
            if model_key in replaced_models:
                continue
            merged_blinks.append(prof_item)
        if blink_profiles:
            merged_blinks.extend(blink_profiles)

    export_physbone_asi_ini(
        resolved_ini,
        merged,
        target_ped_model=target_ped_model,
        blink_profiles=merged_blinks,
    )
    for sync_target in extra_sync_paths:
        sync_path = Path(sync_target)
        if sync_path.resolve() == resolved_ini.resolve():
            continue
        if sync_path.parent.is_dir():
            export_physbone_asi_ini(
                sync_path,
                merged,
                target_ped_model=target_ped_model,
                blink_profiles=merged_blinks,
            )
    return resolved_ini


def export_physbone_asi_ini(
    ini_path: str | Path,
    chain_records: Sequence[Dict[str, object]],
    target_ped_model: str = "player_zero",
    blink_profiles: Sequence[Dict[str, object]] = (),
) -> Path:
    """
    Export runtime chain parameters, optional eye-blink profiles, and baked GTA V
    rest transforms to GTAVPhysBones.ini.

    Each entry in `chain_records` contains:
      - `name`: string identifier (`PB_Ear_L`, `PB_SC_Tail`, `PB_MT_Twin_L`, ...)
      - `parent_bone_tag`: uint16 tag (`31086` for `SKEL_Head`, `11816` for `SKEL_Pelvis`, `24817` for `SKEL_Spine2`)
      - `config`: chain physics config dict (pull, spring, max_angle_x, ...)
      - `bones`: list of dicts per joint with keys:
          `name`, `tag`, `local_pos` (3 floats), `local_rot` (4 floats XYZW),
          `limit_axis_local` (3 floats in parent/rest local space)
    """
    resolved_ini = Path(ini_path)
    resolved_ini.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = [
        "; VRC2GTAV Runtime PhysBones Configuration",
        "; Consumed by GTAVPhysBones.asi via ScriptHookV",
        "",
        "[General]",
        "enabled = 1",
        f"target_ped_model = {target_ped_model}",
        "velocity_scale = 2.5",
        "max_delta_time = 0.05",
        f"chain_count = {len(chain_records)}",
        f"blink_count = {len(blink_profiles)}",
    ]

    for chain_idx, record in enumerate(chain_records):
        cfg_data = record["config"]
        bone_list = record["bones"]
        lines.extend(["", f"[Chain_{chain_idx}]"])
        lines.append(f"name = {record['name']}")
        lines.append(f"parent_bone_tag = {int(record.get('parent_bone_tag', SKEL_HEAD_TAG))}")
        lines.append(f"bone_count = {len(bone_list)}")
        lines.append(f"integration_type = {int(cfg_data.get('integration_type', 0))}")
        lines.append(f"pull = {float(cfg_data.get('pull', 0.2)):.6f}")
        lines.append(f"spring = {float(cfg_data.get('spring', 0.35)):.6f}")
        lines.append(f"stiffness = {float(cfg_data.get('stiffness', 0.2)):.6f}")
        lines.append(f"gravity = {float(cfg_data.get('gravity', 0.0)):.6f}")
        lines.append(f"gravity_falloff = {float(cfg_data.get('gravity_falloff', 0.0)):.6f}")
        lines.append(f"immobile = {float(cfg_data.get('immobile', 0.3)):.6f}")
        lines.append(f"limit_type = {int(cfg_data.get('limit_type', 1))}")
        lines.append(f"max_angle_x = {float(cfg_data.get('max_angle_x', 50.0)):.6f}")
        lines.append(f"max_angle_z = {float(cfg_data.get('max_angle_z', 45.0)):.6f}")
        lines.append(f"is_animated = {int(cfg_data.get('is_animated', 1))}")

        seg_lengths = []
        for bone_idx in range(len(bone_list) - 1):
            next_pos = bone_list[bone_idx + 1]["local_pos"]
            seg_len = math.sqrt(next_pos[0] ** 2 + next_pos[1] ** 2 + next_pos[2] ** 2)
            seg_lengths.append(seg_len)
        total_len = sum(seg_lengths) or 1e-6

        cum_len = 0.0
        max_angle_curve = cfg_data.get("max_angle_x_curve", [])
        base_angle_x = float(cfg_data.get("max_angle_x", 50.0))

        for bone_idx, bone_entry in enumerate(bone_list):
            if "max_angle" in bone_entry and not max_angle_curve:
                node_max_angle = float(bone_entry["max_angle"])
            else:
                chain_t = min(1.0, max(0.0, cum_len / total_len))
                angle_scale = evaluate_curve(max_angle_curve, chain_t, default_val=1.0)
                node_max_angle = base_angle_x * angle_scale
            loc_pos = bone_entry["local_pos"]
            loc_rot = bone_entry["local_rot"]
            lim_axis = bone_entry.get("limit_axis_local", (0.0, 1.0, 0.0))
            lines.append(f"bone_{bone_idx}_name = {bone_entry['name']}")
            lines.append(f"bone_{bone_idx}_tag = {int(bone_entry['tag'])}")
            lines.append(f"bone_{bone_idx}_max_angle = {node_max_angle:.6f}")
            lines.append(f"bone_{bone_idx}_local_pos = {loc_pos[0]:.7f}, {loc_pos[1]:.7f}, {loc_pos[2]:.7f}")
            lines.append(f"bone_{bone_idx}_local_rot = {loc_rot[0]:.7f}, {loc_rot[1]:.7f}, {loc_rot[2]:.7f}, {loc_rot[3]:.7f}")
            lines.append(f"bone_{bone_idx}_limit_axis = {lim_axis[0]:.7f}, {lim_axis[1]:.7f}, {lim_axis[2]:.7f}")
            if bone_idx < len(seg_lengths):
                cum_len += seg_lengths[bone_idx]

    for blink_idx, blink_entry in enumerate(blink_profiles):
        blink_bones = blink_entry.get("bones") or ()
        lines.extend(["", f"[Blink_{blink_idx}]"])
        lines.append(f"model = {blink_entry.get('model', 'all')}")
        lines.append(f"enabled = {int(blink_entry.get('enabled', 1))}")
        lines.append(f"min_interval = {float(blink_entry.get('min_interval', 2.6)):.6f}")
        lines.append(f"max_interval = {float(blink_entry.get('max_interval', 6.0)):.6f}")
        lines.append(f"blink_duration = {float(blink_entry.get('blink_duration', 0.25)):.6f}")
        lines.append(f"double_blink_chance = {float(blink_entry.get('double_blink_chance', 0.18)):.6f}")
        lines.append(f"max_blink = {float(blink_entry.get('max_blink', 1.0)):.6f}")
        lines.append(f"bone_count = {len(blink_bones)}")
        for bone_idx, bone_entry in enumerate(blink_bones):
            loc_pos = bone_entry["local_pos"]
            loc_rot = bone_entry["local_rot"]
            delta_pos = bone_entry.get("delta_pos", (0.0, 0.0, 0.0))
            delta_rot = bone_entry.get("delta_rot", (0.0, 0.0, 0.0, 1.0))
            lines.append(f"bone_{bone_idx}_name = {bone_entry['name']}")
            lines.append(f"bone_{bone_idx}_tag = {int(bone_entry['tag'])}")
            lines.append(f"bone_{bone_idx}_parent_tag = {int(bone_entry.get('parent_tag', 0))}")
            lines.append(f"bone_{bone_idx}_local_pos = {loc_pos[0]:.7f}, {loc_pos[1]:.7f}, {loc_pos[2]:.7f}")
            lines.append(f"bone_{bone_idx}_local_rot = {loc_rot[0]:.7f}, {loc_rot[1]:.7f}, {loc_rot[2]:.7f}, {loc_rot[3]:.7f}")
            lines.append(f"bone_{bone_idx}_delta_pos = {delta_pos[0]:.7f}, {delta_pos[1]:.7f}, {delta_pos[2]:.7f}")
            lines.append(f"bone_{bone_idx}_delta_rot = {delta_rot[0]:.7f}, {delta_rot[1]:.7f}, {delta_rot[2]:.7f}, {delta_rot[3]:.7f}")

    resolved_ini.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return resolved_ini


def _vec_add(vec_a: Tuple[float, float, float], vec_b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (vec_a[0] + vec_b[0], vec_a[1] + vec_b[1], vec_a[2] + vec_b[2])


def _vec_sub(vec_a: Tuple[float, float, float], vec_b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (vec_a[0] - vec_b[0], vec_a[1] - vec_b[1], vec_a[2] - vec_b[2])


def _vec_scale(vec_a: Tuple[float, float, float], factor: float) -> Tuple[float, float, float]:
    return (vec_a[0] * factor, vec_a[1] * factor, vec_a[2] * factor)


def _vec_dot(vec_a: Tuple[float, float, float], vec_b: Tuple[float, float, float]) -> float:
    return vec_a[0] * vec_b[0] + vec_a[1] * vec_b[1] + vec_a[2] * vec_b[2]


def _vec_len(vec_a: Tuple[float, float, float]) -> float:
    return math.sqrt(vec_a[0] * vec_a[0] + vec_a[1] * vec_a[1] + vec_a[2] * vec_a[2])


def _vec_norm(vec_a: Tuple[float, float, float]) -> Tuple[float, float, float]:
    length_val = _vec_len(vec_a)
    if length_val <= 1e-8:
        return (0.0, 0.0, 1.0)
    inv_len = 1.0 / length_val
    return (vec_a[0] * inv_len, vec_a[1] * inv_len, vec_a[2] * inv_len)


def _quat_rotate_vec(quat_xyzw: Tuple[float, float, float, float], vec_a: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Rotate 3D vector by quaternion (x, y, z, w)."""
    qx_val, qy_val, qz_val, qw_val = quat_xyzw
    ux_val = qy_val * vec_a[2] - qz_val * vec_a[1] + qw_val * vec_a[0]
    uy_val = qz_val * vec_a[0] - qx_val * vec_a[2] + qw_val * vec_a[1]
    uz_val = qx_val * vec_a[1] - qy_val * vec_a[0] + qw_val * vec_a[2]
    cross_x = qy_val * uz_val - qz_val * uy_val
    cross_y = qz_val * ux_val - qx_val * uz_val
    cross_z = qx_val * uy_val - qy_val * ux_val
    return (
        vec_a[0] + 2.0 * cross_x,
        vec_a[1] + 2.0 * cross_y,
        vec_a[2] + 2.0 * cross_z,
    )


def _quat_mul(quat_a: Tuple[float, float, float, float], quat_b: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    """Hamilton product of two XYZW quaternions."""
    ax_val, ay_val, az_val, aw_val = quat_a
    bx_val, by_val, bz_val, bw_val = quat_b
    return (
        aw_val * bx_val + ax_val * bw_val + ay_val * bz_val - az_val * by_val,
        aw_val * by_val - ax_val * bz_val + ay_val * bw_val + az_val * bx_val,
        aw_val * bz_val + ax_val * by_val - ay_val * bx_val + az_val * bw_val,
        aw_val * bw_val - ax_val * bx_val - ay_val * by_val - az_val * bz_val,
    )


def _quat_from_two_vectors(dir_from: Tuple[float, float, float], dir_to: Tuple[float, float, float]) -> Tuple[float, float, float, float]:
    """Return shortest-arc XYZW quaternion rotating unit vector dir_from onto dir_to."""
    norm_a = _vec_norm(dir_from)
    norm_b = _vec_norm(dir_to)
    dot_val = max(-1.0, min(1.0, _vec_dot(norm_a, norm_b)))
    if dot_val > 0.999999:
        return (0.0, 0.0, 0.0, 1.0)
    if dot_val < -0.999999:
        ortho_ref = (1.0, 0.0, 0.0) if abs(norm_a[0]) < 0.9 else (0.0, 1.0, 0.0)
        axis_x = norm_a[1] * ortho_ref[2] - norm_a[2] * ortho_ref[1]
        axis_y = norm_a[2] * ortho_ref[0] - norm_a[0] * ortho_ref[2]
        axis_z = norm_a[0] * ortho_ref[1] - norm_a[1] * ortho_ref[0]
        axis_unit = _vec_norm((axis_x, axis_y, axis_z))
        return (axis_unit[0], axis_unit[1], axis_unit[2], 0.0)
    cross_x = norm_a[1] * norm_b[2] - norm_a[2] * norm_b[1]
    cross_y = norm_a[2] * norm_b[0] - norm_a[0] * norm_b[2]
    cross_z = norm_a[0] * norm_b[1] - norm_a[1] * norm_b[0]
    w_comp = 1.0 + dot_val
    norm_len = math.sqrt(cross_x * cross_x + cross_y * cross_y + cross_z * cross_z + w_comp * w_comp)
    inv_len = 1.0 / norm_len
    return (cross_x * inv_len, cross_y * inv_len, cross_z * inv_len, w_comp * inv_len)


class PhysBoneChainSimulator:
    """
    Python reference solver implementing VRC.Dynamics.PhysBoneJob Verlet + cone
    angle limits for offline Blender verification and unit testing.
    """

    def __init__(
        self,
        rest_local_positions: Sequence[Tuple[float, float, float]],
        rest_local_rotations: Sequence[Tuple[float, float, float, float]],
        config: Dict[str, object],
        limit_axes_local: Optional[Sequence[Tuple[float, float, float]]] = None,
    ) -> None:
        self.node_count = len(rest_local_positions)
        if self.node_count < 2:
            raise ValueError("PhysBoneChainSimulator requires at least 2 bones in the chain")
        self.rest_local_pos = [tuple(float(val) for val in item) for item in rest_local_positions]
        self.rest_local_rot = [tuple(float(val) for val in item) for item in rest_local_rotations]
        self.config = dict(config)
        self.limit_axes_local = (
            [tuple(float(val) for val in item) for item in limit_axes_local]
            if limit_axes_local is not None
            else [_vec_norm(pos) for pos in self.rest_local_pos[1:]] + [(0.0, 1.0, 0.0)]
        )

        self.seg_lengths = [_vec_len(self.rest_local_pos[idx + 1]) for idx in range(self.node_count - 1)]
        total_len = sum(self.seg_lengths) or 1e-6
        self.node_max_angles_rad: List[float] = []
        cum_len = 0.0
        base_angle = float(self.config.get("max_angle_x", 50.0))
        angle_curve = self.config.get("max_angle_x_curve", [])
        for idx in range(self.node_count - 1):
            frac_t = cum_len / total_len
            deg_val = base_angle * evaluate_curve(angle_curve, frac_t, default_val=1.0)
            self.node_max_angles_rad.append(math.radians(max(0.0, min(179.0, deg_val))))
            cum_len += self.seg_lengths[idx]

        self.initialized = False
        self.world_pos: List[Tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * self.node_count
        self.prev_pos: List[Tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * self.node_count
        self.prev_root_pos: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    def _compute_pose_world(
        self,
        parent_world_pos: Tuple[float, float, float],
        parent_world_rot: Tuple[float, float, float, float],
    ) -> Tuple[List[Tuple[float, float, float]], List[Tuple[float, float, float, float]]]:
        """Compute animated/rest world positions & orientations under parent_bone."""
        pose_pos: List[Tuple[float, float, float]] = []
        pose_rot: List[Tuple[float, float, float, float]] = []
        cur_pos = parent_world_pos
        cur_rot = parent_world_rot
        for idx in range(self.node_count):
            world_offset = _quat_rotate_vec(cur_rot, self.rest_local_pos[idx])
            cur_pos = _vec_add(cur_pos, world_offset)
            cur_rot = _quat_mul(cur_rot, self.rest_local_rot[idx])
            pose_pos.append(cur_pos)
            pose_rot.append(cur_rot)
        return pose_pos, pose_rot

    def reset(
        self,
        parent_world_pos: Tuple[float, float, float],
        parent_world_rot: Tuple[float, float, float, float],
    ) -> None:
        """Snap simulation buffers cleanly to the current rest pose."""
        pose_pos, _ = self._compute_pose_world(parent_world_pos, parent_world_rot)
        self.world_pos = list(pose_pos)
        self.prev_pos = list(pose_pos)
        self.prev_root_pos = pose_pos[0]
        self.initialized = True

    def step(
        self,
        parent_world_pos: Tuple[float, float, float],
        parent_world_rot: Tuple[float, float, float, float],
        delta_time: float,
    ) -> Tuple[List[Tuple[float, float, float]], List[Tuple[float, float, float, float]]]:
        """Advance chain physics by delta_time seconds and return world (positions, rotations)."""
        clamped_dt = max(1e-4, min(0.05, float(delta_time)))
        pose_pos, pose_rot = self._compute_pose_world(parent_world_pos, parent_world_rot)

        if not self.initialized:
            self.reset(parent_world_pos, parent_world_rot)
            return list(pose_pos), list(pose_rot)

        pull_val = float(self.config.get("pull", 0.2))
        spring_val = float(self.config.get("spring", 0.35))
        gravity_val = float(self.config.get("gravity", 0.0))
        gravity_falloff_val = max(0.0, min(1.0, float(self.config.get("gravity_falloff", 0.0))))
        eff_gravity_val = gravity_val * (1.0 - gravity_falloff_val)
        immobile_val = float(self.config.get("immobile", 0.3))
        limit_type = int(self.config.get("limit_type", 1))

        root_delta = _vec_sub(pose_pos[0], self.prev_root_pos)
        immobile_shift = _vec_scale(root_delta, max(0.0, min(1.0, immobile_val)))
        self.prev_root_pos = pose_pos[0]

        rate_scale = clamped_dt * 60.0
        vel_retention = pow(max(0.05, min(0.95, 0.25 + 0.65 * spring_val)), rate_scale)
        pull_factor = 1.0 - pow(max(0.0, min(1.0, 1.0 - pull_val)), rate_scale)

        self.world_pos[0] = pose_pos[0]
        self.prev_pos[0] = pose_pos[0]

        # Stage 1: Verlet prediction + immobile cancellation + pull/gravity
        for idx in range(1, self.node_count):
            shifted_prev = _vec_add(self.prev_pos[idx], immobile_shift)
            shifted_curr = _vec_add(self.world_pos[idx], immobile_shift)
            velocity_vec = _vec_scale(_vec_sub(shifted_curr, shifted_prev), vel_retention)
            gravity_disp = (0.0, 0.0, -9.81 * eff_gravity_val * clamped_dt * clamped_dt)

            self.prev_pos[idx] = shifted_curr
            predicted_pos = _vec_add(_vec_add(shifted_curr, velocity_vec), gravity_disp)
            pull_delta = _vec_scale(_vec_sub(pose_pos[idx], predicted_pos), pull_factor)
            self.world_pos[idx] = _vec_add(predicted_pos, pull_delta)

        # Stage 2: Angle cone constraints + bone segment length clamping
        parent_rot_out: List[Tuple[float, float, float, float]] = [pose_rot[0]]
        for idx in range(self.node_count - 1):
            node_pos = self.world_pos[idx]
            child_pos = self.world_pos[idx + 1]
            cur_dir = _vec_norm(_vec_sub(child_pos, node_pos))

            # Expected rest bone orientation at node idx given previous chain rotation
            expected_parent_rot = parent_world_rot if idx == 0 else parent_rot_out[idx - 1]
            rest_node_rot = _quat_mul(expected_parent_rot, self.rest_local_rot[idx])
            rest_seg_dir = _vec_norm(_quat_rotate_vec(rest_node_rot, self.rest_local_pos[idx + 1]))

            if limit_type > 0:
                lim_ref = _vec_norm(_quat_rotate_vec(rest_node_rot, self.limit_axes_local[idx]))
                cos_ang = max(-1.0, min(1.0, _vec_dot(cur_dir, lim_ref)))
                cur_ang = math.acos(cos_ang)
                max_ang = self.node_max_angles_rad[idx]
                if cur_ang > max_ang:
                    tangent_vec = _vec_sub(cur_dir, _vec_scale(lim_ref, cos_ang))
                    if _vec_len(tangent_vec) > 1e-6:
                        tangent_unit = _vec_norm(tangent_vec)
                        cur_dir = _vec_norm(
                            _vec_add(
                                _vec_scale(lim_ref, math.cos(max_ang)),
                                _vec_scale(tangent_unit, math.sin(max_ang)),
                            )
                        )

            self.world_pos[idx + 1] = _vec_add(node_pos, _vec_scale(cur_dir, self.seg_lengths[idx]))
            aim_delta_rot = _quat_from_two_vectors(rest_seg_dir, cur_dir)
            node_world_rot = _quat_mul(aim_delta_rot, rest_node_rot)
            if idx == 0:
                parent_rot_out[0] = node_world_rot
            else:
                parent_rot_out.append(node_world_rot)

        # Leaf bone preserves rest local orientation atop its animated/simulated parent
        leaf_world_rot = _quat_mul(parent_rot_out[-1], self.rest_local_rot[-1])
        parent_rot_out.append(leaf_world_rot)
        return list(self.world_pos), parent_rot_out
