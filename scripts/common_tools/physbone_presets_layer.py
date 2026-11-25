"""
physbone_presets_layer.py
=========================
Layer 1 of 5 for VRChat VRCPhysBone support (`physbone_helper` architecture).

Owns canonical GTA V skeleton bone tag constants, the ordered 7-tier
PhysBone priority system (`PHYSBONE_PRIORITY_TIERS`), curated protagonist &
Marshmallow PB template tables, ELF JOAAT bone tag hashing, and per-bone
name resolution helpers.
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
SKEL_L_CALF_TAG: int = 63931
SKEL_R_CALF_TAG: int = 36864
SKEL_L_FOOT_TAG: int = 14201
SKEL_R_FOOT_TAG: int = 52301
SKEL_L_CLAVICLE_TAG: int = 64729
SKEL_R_CLAVICLE_TAG: int = 10706
SKEL_L_UPPERARM_TAG: int = 45509
SKEL_R_UPPERARM_TAG: int = 40269
SKEL_L_FOREARM_TAG: int = 61163
SKEL_R_FOREARM_TAG: int = 28252
SKEL_L_HAND_TAG: int = 18905
SKEL_R_HAND_TAG: int = 57005

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
        "label": "Tier 1 - Animal Ears (cat, dog, fox, etc.) & Primary Hair (bangs, side/back hair, twintails)",
        "keywords": (
            "kemonomimi", "nekomimi", "usagimimi", "kitsunemimi", "inumimi",
            "kumamimi", "okamimimi", "mimi",
            "ear", "horn", "antler", "halo",
            "bang", "bangs", "maegami", "yokogami", "ushirogami",
            "twintail", "ponytail", "pigtail", "braid", "osage", "sidetail",
        ),
        "bigrams": (
            ("front", "hair"), ("hair", "front"),
            ("side", "hair"), ("hair", "side"),
            ("back", "hair"), ("hair", "back"),
            ("hair", "base"), ("hair", "top"), ("long", "hair"),
            ("twin", "tail"), ("pony", "tail"), ("side", "tail"),
            ("cat", "ear"), ("fox", "ear"), ("neko", "ear"),
            ("dog", "ear"), ("puppy", "ear"), ("inu", "ear"),
            ("rabbit", "ear"), ("bunny", "ear"), ("wolf", "ear"),
            ("bear", "ear"), ("sheep", "ear"), ("kitsune", "ear"),
        ),
        "head_directional_tokens": ("front", "side", "back"),
    },
    {
        "tier": 1,
        "key": "essential_hair_strands",
        "priority": 97,
        "essential": True,
        "label": "Tier 1 - Remaining Hair Strands (hair, kami, ahoge)",
        "keywords": (
            "hair", "kami", "ahoge", "aho", "longhair", "shorthair", "hairmain",
        ),
        "bigrams": (),
    },
    {
        "tier": 1,
        "key": "essential_anatomy_breasts",
        "priority": 94,
        "essential": True,
        "label": "Tier 1 - Core Anatomy Soft-Body (breasts / chest)",
        "keywords": (
            "breast", "oppai", "bust", "mune", "boob", "marshmallow", "chest",
        ),
        "bigrams": (),
    },
    {
        "tier": 2,
        "key": "essential_tails_wings_and_skirts",
        "priority": 90,
        "essential": True,
        "label": "Tier 2 - Skirts & Dresses (skirt, dress, onepiece, hakama)",
        "keywords": (
            "skirt", "skrit", "dress", "onepiece", "hakama", "tutu", "petticoat",
        ),
        "bigrams": (
            ("apron", "skirt"),
        ),
    },
    {
        "tier": 2,
        "key": "essential_tails_and_wings",
        "priority": 82,
        "essential": True,
        "label": "Tier 2 - Tails & Wings",
        "keywords": (
            "tail", "shippo", "sipo", "wing", "hane",
        ),
        "bigrams": (
            ("coat", "tail"),
        ),
    },
    {
        "tier": 3,
        "key": "important_hair_and_major_garments",
        "priority": 68,
        "essential": False,
        "label": "Tier 3 - Secondary Garments & Outerwear (jackets, coats, capes, sleeves, scarves, ties)",
        "keywords": (
            "coat", "jacket", "cardigan", "hoodie", "blazer", "parka",
            "cape", "cloak", "mantle", "hem", "capelet", "kimono", "furisode",
            "sleeve", "sode", "cuff", "scarf", "muffler", "shawl", "stole",
            "necktie", "tie", "apron",
        ),
        "bigrams": (
            ("jacket", "hem"), ("neck", "tie"), ("collar", "flap"),
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
_CHEST_GARMENT_TOKENS: Set[str] = {
    "scarf", "apron", "tie", "necktie", "cape", "coat", "armor", "pocket", "flap"
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
    for bigram_first, bigram_second in tier_cfg.get("bigrams", ()):
        for tok_idx in range(len(ordered_tokens) - 1):
            cur_tok = ordered_tokens[tok_idx]
            nxt_tok = ordered_tokens[tok_idx + 1]
            cur_sing = cur_tok[:-1] if (len(cur_tok) > 3 and cur_tok.endswith("s") and cur_tok not in _KEEP_FINAL_S_TOKENS) else cur_tok
            nxt_sing = nxt_tok[:-1] if (len(nxt_tok) > 3 and nxt_tok.endswith("s") and nxt_tok not in _KEEP_FINAL_S_TOKENS) else nxt_tok
            if bigram_first in (cur_tok, cur_sing) and bigram_second in (nxt_tok, nxt_sing):
                return f"{bigram_first}_{bigram_second}"
    for keyword_tok in tier_cfg.get("keywords", ()):
        if keyword_tok in token_set:
            return keyword_tok
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
    root_candidates = [chain_name, *list(spoke_bones)[:1]]
    _JEWELRY_OVERRIDES = frozenset(
        {"earring", "earpiece", "pierce", "piercing", "eyelash", "matsuge", "necklace", "pendant"}
    )
    _JEWELRY_BIGRAMS = (("ear", "ring"), ("ear", "piece"))
    root_tokens, root_token_set = _tokenize_physbone_name(root_candidates)
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
        for bigram_first, bigram_second in _JEWELRY_BIGRAMS:
            for tok_idx in range(len(ordered_tokens) - 1):
                if ordered_tokens[tok_idx] == bigram_first and ordered_tokens[tok_idx + 1] == bigram_second:
                    jewelry_hit = f"{bigram_first}_{bigram_second}"
                    break
            if jewelry_hit:
                break
        if not jewelry_hit:
            for jewelry_tok in _JEWELRY_OVERRIDES:
                if jewelry_tok in token_set:
                    jewelry_hit = jewelry_tok
                    break
        if jewelry_hit:
            matched_tier = _PHYSBONE_TIER_BY_KEY["optional_micro_jiggle_and_jewelry"]
            matched_rule = jewelry_hit

    if matched_tier is None:
        core_tiers = (
            "essential_ears_and_primary_hair",
            "essential_hair_strands",
            "essential_anatomy_breasts",
            "essential_tails_wings_and_skirts",
            "essential_tails_and_wings",
        )
        modifier_tiers = (
            "medium_ribbons_and_frills",
            "optional_straps_chains_and_belts",
        )
        # Keep Tier 1-2 root bones (e.g. Skirt_4 -> sub-spoke Skirt_belt) from being demoted by child/object words
        root_has_modifier = any(
            _match_tier_tokens(_PHYSBONE_TIER_BY_KEY[mod_key], root_tokens, root_token_set)
            for mod_key in modifier_tiers
        )
        if not root_has_modifier:
            for tier_key in core_tiers:
                tier_cfg = _PHYSBONE_TIER_BY_KEY[tier_key]
                hit_rule = _match_tier_tokens(tier_cfg, root_tokens, root_token_set)
                if hit_rule and not (
                    tier_key == "essential_anatomy_breasts"
                    and hit_rule == "chest"
                    and (root_token_set & _CHEST_GARMENT_TOKENS)
                ):
                    matched_tier = tier_cfg
                    matched_rule = hit_rule
                    break

    if matched_tier is None:
        check_order = (
            "medium_ribbons_and_frills",
            "optional_straps_chains_and_belts",
            "optional_micro_jiggle_and_jewelry",
            "essential_ears_and_primary_hair",
            "essential_hair_strands",
            "essential_anatomy_breasts",
            "essential_tails_wings_and_skirts",
            "essential_tails_and_wings",
            "important_hair_and_major_garments",
        )
        for tier_key in check_order:
            tier_cfg = _PHYSBONE_TIER_BY_KEY[tier_key]
            hit_rule = _match_tier_tokens(tier_cfg, ordered_tokens, token_set)
            if hit_rule:
                if (
                    tier_key == "essential_anatomy_breasts"
                    and hit_rule == "chest"
                    and (token_set & _CHEST_GARMENT_TOKENS)
                ):
                    continue
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
    "SKEL_L_Calf": SKEL_L_CALF_TAG,
    "SKEL_R_Calf": SKEL_R_CALF_TAG,
    "SKEL_L_Foot": SKEL_L_FOOT_TAG,
    "SKEL_R_Foot": SKEL_R_FOOT_TAG,
    "SKEL_L_Clavicle": SKEL_L_CLAVICLE_TAG,
    "SKEL_R_Clavicle": SKEL_R_CLAVICLE_TAG,
    "SKEL_L_UpperArm": SKEL_L_UPPERARM_TAG,
    "SKEL_R_UpperArm": SKEL_R_UPPERARM_TAG,
    "SKEL_L_Forearm": SKEL_L_FOREARM_TAG,
    "SKEL_R_Forearm": SKEL_R_FOREARM_TAG,
    "SKEL_L_Hand": SKEL_L_HAND_TAG,
    "SKEL_R_Hand": SKEL_R_HAND_TAG,
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
    "upperleg.l": "SKEL_L_Thigh",
    "upperleg_l": "SKEL_L_Thigh",
    "leftupperleg": "SKEL_L_Thigh",
    "left_upper_leg": "SKEL_L_Thigh",
    "thigh.l": "SKEL_L_Thigh",
    "thigh_l": "SKEL_L_Thigh",
    "upper_leg.r": "SKEL_R_Thigh",
    "upper_leg_r": "SKEL_R_Thigh",
    "upperleg.r": "SKEL_R_Thigh",
    "upperleg_r": "SKEL_R_Thigh",
    "rightupperleg": "SKEL_R_Thigh",
    "right_upper_leg": "SKEL_R_Thigh",
    "thigh.r": "SKEL_R_Thigh",
    "thigh_r": "SKEL_R_Thigh",
    "lower_leg.l": "SKEL_L_Calf",
    "lower_leg_l": "SKEL_L_Calf",
    "lowerleg.l": "SKEL_L_Calf",
    "lowerleg_l": "SKEL_L_Calf",
    "leftlowerleg": "SKEL_L_Calf",
    "left_lower_leg": "SKEL_L_Calf",
    "calf.l": "SKEL_L_Calf",
    "calf_l": "SKEL_L_Calf",
    "lower_leg.r": "SKEL_R_Calf",
    "lower_leg_r": "SKEL_R_Calf",
    "lowerleg.r": "SKEL_R_Calf",
    "lowerleg_r": "SKEL_R_Calf",
    "rightlowerleg": "SKEL_R_Calf",
    "right_lower_leg": "SKEL_R_Calf",
    "calf.r": "SKEL_R_Calf",
    "calf_r": "SKEL_R_Calf",
    "foot.l": "SKEL_L_Foot",
    "foot_l": "SKEL_L_Foot",
    "leftfoot": "SKEL_L_Foot",
    "left_foot": "SKEL_L_Foot",
    "toe.l": "SKEL_L_Foot",
    "lefttoebase": "SKEL_L_Foot",
    "foot.r": "SKEL_R_Foot",
    "foot_r": "SKEL_R_Foot",
    "rightfoot": "SKEL_R_Foot",
    "right_foot": "SKEL_R_Foot",
    "toe.r": "SKEL_R_Foot",
    "righttoebase": "SKEL_R_Foot",
    "shoulder.l": "SKEL_L_Clavicle",
    "shoulder_l": "SKEL_L_Clavicle",
    "leftshoulder": "SKEL_L_Clavicle",
    "left_shoulder": "SKEL_L_Clavicle",
    "shoulder.r": "SKEL_R_Clavicle",
    "shoulder_r": "SKEL_R_Clavicle",
    "rightshoulder": "SKEL_R_Clavicle",
    "right_shoulder": "SKEL_R_Clavicle",
    "upper_arm.l": "SKEL_L_UpperArm",
    "upper_arm_l": "SKEL_L_UpperArm",
    "upperarm.l": "SKEL_L_UpperArm",
    "upperarm_l": "SKEL_L_UpperArm",
    "leftupperarm": "SKEL_L_UpperArm",
    "left_upper_arm": "SKEL_L_UpperArm",
    "upper_arm.r": "SKEL_R_UpperArm",
    "upper_arm_r": "SKEL_R_UpperArm",
    "upperarm.r": "SKEL_R_UpperArm",
    "upperarm_r": "SKEL_R_UpperArm",
    "rightupperarm": "SKEL_R_UpperArm",
    "right_upper_arm": "SKEL_R_UpperArm",
    "lower_arm.l": "SKEL_L_Forearm",
    "lower_arm_l": "SKEL_L_Forearm",
    "lowerarm.l": "SKEL_L_Forearm",
    "lowerarm_l": "SKEL_L_Forearm",
    "leftlowerarm": "SKEL_L_Forearm",
    "left_lower_arm": "SKEL_L_Forearm",
    "forearm.l": "SKEL_L_Forearm",
    "lower_arm.r": "SKEL_R_Forearm",
    "lower_arm_r": "SKEL_R_Forearm",
    "lowerarm.r": "SKEL_R_Forearm",
    "lowerarm_r": "SKEL_R_Forearm",
    "rightlowerarm": "SKEL_R_Forearm",
    "right_lower_arm": "SKEL_R_Forearm",
    "forearm.r": "SKEL_R_Forearm",
    "hand.l": "SKEL_L_Hand",
    "hand_l": "SKEL_L_Hand",
    "lefthand": "SKEL_L_Hand",
    "left_hand": "SKEL_L_Hand",
    "wrist.l": "SKEL_L_Hand",
    "hand.r": "SKEL_R_Hand",
    "hand_r": "SKEL_R_Hand",
    "righthand": "SKEL_R_Hand",
    "right_hand": "SKEL_R_Hand",
    "wrist.r": "SKEL_R_Hand",
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
    bone_map_lower = dict(loaded_data.get("bone_mapping_ci") or {})
    for src_bone, dst_bone in overlay["bone_mapping"].items():
        bone_map[src_bone] = dst_bone
        bone_map_lower[src_bone.strip().lower()] = dst_bone
    for chain_key, chain_cfg in overlay["chains"].items():
        chains_map[chain_key] = dict(chain_cfg)

    loaded_data["chains"] = chains_map
    loaded_data["bone_mapping"] = bone_map
    loaded_data["bone_mapping_ci"] = bone_map_lower
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


# Union of all vanilla Rockstar skeleton bone tags across player_zero, player_one, player_two
VANILLA_RESERVED_BONE_TAGS: Set[int] = {
    0, 445, 481, 721, 934, 1668, 1980, 2064, 2108, 2115, 2123, 2262, 2359, 2449, 2726,
    2844, 2849, 2876, 2992, 3148, 3378, 3422, 3515, 3594, 3603, 3651, 4089, 4090, 4115,
    4137, 4138, 4153, 4154, 4169, 4170, 4185, 4186, 4219, 4223, 4262, 4407, 5135, 5232,
    5285, 5749, 5892, 5956, 6004, 6035, 6286, 6442, 6468, 6621, 6779, 6783, 6905, 7153,
    7382, 8120, 8294, 8323, 8433, 8487, 8904, 8906, 9038, 9151, 9247, 9290, 9817, 10040,
    10167, 10256, 10362, 10508, 10594, 10706, 10754, 10851, 10852, 10853, 11194, 11252,
    11347, 11363, 11434, 11816, 12074, 12270, 12271, 12272, 12273, 12274, 12844, 13079,
    13090, 13806, 13807, 13808, 13809, 13810, 13823, 13919, 14079, 14201, 14286, 14382,
    14428, 14524, 14728, 15639, 15719, 15828, 15944, 15987, 16015, 16051, 16335, 16562,
    16705, 16718, 16719, 16720, 16721, 16929, 17012, 17043, 17376, 17447, 17787, 17890,
    18432, 18905, 19038, 19068, 19069, 19070, 19071, 19072, 19265, 19663, 19729, 20536,
    20603, 20635, 20781, 20899, 20943, 20970, 21159, 21699, 21755, 22084, 22122, 22367,
    22711, 22845, 22846, 22847, 22848, 22939, 22940, 23184, 23242, 23553, 23639, 23869,
    24048, 24504, 24581, 24589, 24625, 24806, 24816, 24817, 24818, 24843, 25003, 25435,
    26610, 26611, 26612, 26613, 26614, 26618, 26875, 26887, 26917, 27064, 27232, 28252,
    28422, 29222, 29317, 29474, 29564, 29881, 29957, 30083, 30332, 30364, 30464, 30468,
    30482, 30491, 30587, 30887, 30888, 30889, 31010, 31086, 31093, 31105, 31123, 31189,
    31696, 31738, 31843, 32276, 32735, 32817, 33121, 33138, 33346, 33349, 33504, 34093,
    34545, 34618, 34929, 35161, 35226, 35428, 35477, 35502, 35547, 35718, 35724, 35923,
    35939, 36029, 36299, 36656, 36811, 36864, 36917, 37119, 37400, 37547, 37596, 37692,
    37844, 37920, 38229, 38365, 38849, 39100, 39308, 39317, 39642, 39711, 39785, 39843,
    39896, 40058, 40244, 40269, 40433, 40591, 40878, 41012, 41039, 41166, 41410, 41540,
    41714, 41715, 41716, 41750, 41817, 42114, 42202, 42329, 43614, 43810, 43885, 44297,
    44575, 44821, 44825, 44921, 45075, 45333, 45509, 45519, 45786, 45876, 46078, 46456,
    46636, 46872, 46951, 47006, 47119, 47158, 47530, 47585, 48084, 48085, 48086, 48713,
    49473, 49503, 49600, 49881, 50201, 50493, 50583, 50619, 50669, 50788, 50811, 50813,
    50907, 50921, 51017, 51082, 51826, 52301, 52600, 52667, 52979, 52999, 53011, 53771,
    53791, 54081, 54337, 54352, 54533, 54593, 54814, 55286, 55675, 55853, 56604, 56642,
    56819, 57005, 57434, 57444, 57597, 57717, 57742, 57948, 58255, 58271, 58363, 58364,
    58728, 58850, 58866, 58867, 58868, 58869, 58870, 59033, 59307, 59791, 60309, 60773,
    60942, 61007, 61163, 61259, 61493, 61499, 61586, 61777, 62042, 62289, 62311, 62460,
    62491, 62895, 63446, 63769, 63931, 64016, 64017, 64064, 64065, 64080, 64081, 64096,
    64097, 64112, 64113, 64275, 64294, 64460, 64672, 64729, 65068, 65100, 65245,
}


def resolve_bone_from_mapping(
    raw_group_name: str,
    bone_mapping_lower: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Resolve a lowercase vertex group name through a dynamic bone_mapping dict."""
    if not bone_mapping_lower:
        return None
    return bone_mapping_lower.get(str(raw_group_name).strip().lower())


def resolve_michael_er_gtav_bone(
    raw_group_name: str,
    mesh_name: Optional[str] = None,
    bone_mapping_lower: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Map a Shinano Eternal Reunion + hair bone name to its PB_Ear_* or PB_ER_* bone."""
    _ = mesh_name
    lowered_name = raw_group_name.strip().lower()
    if bone_mapping_lower is not None and lowered_name in bone_mapping_lower:
        return bone_mapping_lower[lowered_name]
    return MICHAEL_ER_BONE_MAP.get(lowered_name)


def resolve_neko_mimi_gtav_bone(raw_group_name: str) -> Optional[str]:
    """Map an ear.* Blender vertex group name to its PB_Ear_* GTA V bone."""
    lowered_name = raw_group_name.strip().lower()
    return NEKO_MIMI_BONE_MAP.get(lowered_name)


def resolve_shinano_casual_gtav_bone(
    raw_group_name: str,
    mesh_name: Optional[str] = None,
    bone_mapping_lower: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Map a Shinano Casual Blender vertex group name to its PB_SC_* GTA V bone."""
    lowered_name = raw_group_name.strip().lower()
    if bone_mapping_lower is not None and lowered_name in bone_mapping_lower:
        return bone_mapping_lower[lowered_name]
    return SHINANO_CASUAL_BONE_MAP.get(lowered_name)


def resolve_miltina_maid_gtav_bone(
    raw_group_name: str,
    mesh_name: Optional[str] = None,
    bone_mapping_lower: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Map a Miltina Maid Blender vertex group name to its PB_MT_* GTA V bone."""
    lowered_name = raw_group_name.strip().lower()
    if bone_mapping_lower is not None and lowered_name in bone_mapping_lower:
        return bone_mapping_lower[lowered_name]
    return MILTINA_MAID_BONE_MAP.get(lowered_name)
