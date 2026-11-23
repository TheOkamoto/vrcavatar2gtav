"""
physbone_cfg_ini_layer.py
=========================
Layer 2 of 5 for VRChat VRCPhysBone support (`physbone_helper` architecture).

Handles `.cfg` preset I/O, piecewise-linear Unity curve parsing/evaluation,
scalar/quaternion/YAML vector parsing, multi-model scoped `GTAVPhysBones.ini`
merging & exporting, and the offline `PhysBoneChainSimulator`.
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
        SKEL_HEAD_TAG,
        PARENT_BONE_TAGS,
        _chain_parent_map,
        MICHAEL_ER_BONE_MAP,
        VANILLA_RESERVED_BONE_TAGS,
        VRCHAT_PHYSBONE_SCRIPT_GUID,
    )
except ImportError:
    from common_tools.physbone_presets_layer import (
        SKEL_HEAD_TAG,
        PARENT_BONE_TAGS,
        _chain_parent_map,
        MICHAEL_ER_BONE_MAP,
        VANILLA_RESERVED_BONE_TAGS,
        VRCHAT_PHYSBONE_SCRIPT_GUID,
    )

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
                "model": sec.get("model", "").strip(),
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
    own_chain_models: Sequence[str] = (),
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
    replaced_chain_models = {
        str(model_tok).strip().lower()
        for model_tok in own_chain_models
        if str(model_tok).strip()
    }
    if replaced_chain_models:
        existing_pairs = {
            (str(rec.get("name", "")), str(rec.get("model", "")).strip().lower())
            for rec in chain_records
        }
    else:
        existing_pairs = set()
    merged: List[Dict[str, object]] = []
    for rec in existing:
        rec_name = str(rec.get("name", ""))
        rec_model = str(rec.get("model", "")).strip().lower()
        # Drop any legacy wildcard chain whose root tag collides with a vanilla GTA V skeleton tag
        rec_bones = rec.get("bones") or ()
        if not rec_model and rec_bones and int(rec_bones[0].get("tag", -1)) in VANILLA_RESERVED_BONE_TAGS:
            continue
        if replaced_chain_models:
            if rec_model in replaced_chain_models or (rec_name, rec_model) in existing_pairs:
                continue
            if (not rec_model) and any(rec_name.startswith(pref) for pref in own_prefixes):
                continue
        else:
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


def remove_ped_from_physbone_ini(
    ini_path: str | Path,
    ped_model: str,
    *,
    extra_sync_paths: Sequence[str | Path] = (),
) -> Optional[Path]:
    """Remove all PhysBone chains and Blink profiles scoped to `ped_model` from `GTAVPhysBones.ini`."""
    resolved_ini = Path(ini_path)
    if not resolved_ini.is_file():
        return None
    norm_model = str(ped_model or "").strip().lower()
    if not norm_model:
        return None
    prefix_hints = {
        "player_zero": ("PB_ER_",),
        "player_one": ("PB_SC_",),
        "player_two": ("PB_MT_",),
    }.get(norm_model, ())
    existing = _load_ini_chain_records(resolved_ini)
    kept_chains: List[Dict[str, object]] = []
    for rec in existing:
        rec_model = str(rec.get("model", "")).strip().lower()
        rec_name = str(rec.get("name", ""))
        if rec_model == norm_model:
            continue
        if not rec_model and any(rec_name.startswith(pref) for pref in prefix_hints):
            continue
        kept_chains.append(rec)

    existing_blinks = _load_ini_blink_profiles(resolved_ini)
    kept_blinks = [
        prof
        for prof in existing_blinks
        if str(prof.get("model", "")).strip().lower() != norm_model
    ]
    export_physbone_asi_ini(
        resolved_ini,
        kept_chains,
        target_ped_model="all",
        blink_profiles=kept_blinks,
    )
    for sync_target in extra_sync_paths:
        sync_path = Path(sync_target)
        if sync_path.parent.is_dir() and sync_path.resolve() != resolved_ini.resolve():
            export_physbone_asi_ini(
                sync_path,
                kept_chains,
                target_ped_model="all",
                blink_profiles=kept_blinks,
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
        chain_model = str(record.get("model", "") or "").strip()
        if not chain_model and target_ped_model and target_ped_model.lower() != "all":
            chain_model = str(target_ped_model).strip()
        if chain_model:
            lines.append(f"model = {chain_model}")
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
