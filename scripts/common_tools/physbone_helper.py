#!/usr/bin/env python3
"""
physbone_helper.py
==================
Shared VRChat PhysBone extraction, bone-tag calculation, config I/O,
runtime .ini export, and offline Verlet+cone-limit solver for VRC2GTAV.

Starts with Michael (player_zero) neko mimi articulated ear chains
(ear.L -> PB_Ear_L_0..2, ear.R -> PB_Ear_R_0..2) parented to SKEL_Head.
"""

from configparser import ConfigParser
import math
from pathlib import Path
import re
from typing import Dict, List, Optional, Sequence, Tuple


NEKO_MIMI_BONE_MAP: Dict[str, str] = {
    "ear.l": "PB_Ear_L_0",
    "ear.l.001": "PB_Ear_L_1",
    "ear.l.002": "PB_Ear_L_2",
    "ear.r": "PB_Ear_R_0",
    "ear.r.001": "PB_Ear_R_1",
    "ear.r.002": "PB_Ear_R_2",
    "halo": "PB_Ear_L_0",
    "halo.001": "PB_Ear_L_1",
}

NEKO_MIMI_HALO_WEIGHT_SPLIT: Tuple[Tuple[str, float], ...] = (
    ("PB_Ear_L_0", 0.5),
    ("PB_Ear_L_1", 0.5),
)

NEKO_MIMI_CHAIN_SPECS: Tuple[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]], ...] = (
    (
        "ear.L",
        "PB_Ear_L",
        ("ear.L", "ear.L.001", "ear.L.002"),
        ("PB_Ear_L_0", "PB_Ear_L_1", "PB_Ear_L_2"),
    ),
    (
        "ear.R",
        "PB_Ear_R",
        ("ear.R", "ear.R.001", "ear.R.002"),
        ("PB_Ear_R_0", "PB_Ear_R_1", "PB_Ear_R_2"),
    ),
)

NEKO_MIMI_CUSTOM_BONES: Tuple[str, ...] = (
    "PB_Ear_L_0",
    "PB_Ear_L_1",
    "PB_Ear_L_2",
    "PB_Ear_R_0",
    "PB_Ear_R_1",
    "PB_Ear_R_2",
)

NEKO_MIMI_PARENT_MAP: Dict[str, str] = {
    "PB_Ear_L_0": "SKEL_Head",
    "PB_Ear_L_1": "PB_Ear_L_0",
    "PB_Ear_L_2": "PB_Ear_L_1",
    "PB_Ear_R_0": "SKEL_Head",
    "PB_Ear_R_1": "PB_Ear_R_0",
    "PB_Ear_R_2": "PB_Ear_R_1",
}

CUSTOM_BONE_FLAGS: Tuple[str, ...] = (
    "RotX",
    "RotY",
    "RotZ",
    "TransX",
    "TransY",
    "TransZ",
)

SKEL_HEAD_TAG: int = 31086
VRCHAT_PHYSBONE_SCRIPT_GUID: str = "2a2c05204084d904aa4945ccff20d8e5"


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


def resolve_neko_mimi_gtav_bone(raw_group_name: str) -> Optional[str]:
    """Map an ear.* Blender vertex group name to its PB_Ear_* GTA V bone."""
    lowered_name = raw_group_name.strip().lower()
    return NEKO_MIMI_BONE_MAP.get(lowered_name)


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


def load_physbone_config(cfg_path: str | Path) -> Dict[str, object]:
    """Load character PhysBone configuration from an INI-style .cfg file."""
    resolved_path = Path(cfg_path)
    if not resolved_path.is_file():
        raise FileNotFoundError(f"PhysBone config not found: {resolved_path}")

    parser = ConfigParser()
    parser.optionxform = str
    with resolved_path.open("r", encoding="utf-8") as cfg_file:
        parser.read_file(cfg_file)

    metadata = dict(parser["metadata"]) if parser.has_section("metadata") else {}
    bone_mapping = dict(parser["bone_mapping"]) if parser.has_section("bone_mapping") else {}

    chains: Dict[str, Dict[str, object]] = {}
    for section_name in parser.sections():
        if not section_name.startswith("chain."):
            continue
        chain_key = section_name[len("chain.") :]
        sec = parser[section_name]
        chain_bones = [item.strip() for item in sec.get("chain_bones", "").split(",") if item.strip()]
        source_bones = [item.strip() for item in sec.get("source_bones", "").split(",") if item.strip()]
        chains[chain_key] = {
            "source_key": chain_key,
            "root_bone": sec.get("root_bone", chain_bones[0] if chain_bones else ""),
            "chain_bones": chain_bones,
            "source_bones": source_bones,
            "parent_bone": sec.get("parent_bone", "SKEL_Head"),
            "parent_bone_tag": sec.getint("parent_bone_tag", SKEL_HEAD_TAG),
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
            "limit_rotation": parse_vec3_string(sec.get("limit_rotation", "14.12, 0.0, 0.0")),
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
        "chains": chains,
    }


def save_physbone_config(
    cfg_path: str | Path,
    chain_configs: Dict[str, Dict[str, object]],
    metadata: Optional[Dict[str, object]] = None,
    bone_mapping: Optional[Dict[str, str]] = None,
) -> Path:
    """Write PhysBone parameters and bone mappings to an INI-style .cfg file."""
    resolved_path = Path(cfg_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = [
        "# VRC2GTAV PhysBone Preset - Auto-generated/verified character PhysBones",
        "",
        "[metadata]",
    ]
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
    map_dict = bone_mapping or {
        "ear.L": "PB_Ear_L_0",
        "ear.L.001": "PB_Ear_L_1",
        "ear.L.002": "PB_Ear_L_2",
        "ear.R": "PB_Ear_R_0",
        "ear.R.001": "PB_Ear_R_1",
        "ear.R.002": "PB_Ear_R_2",
    }
    for src_name, dst_name in map_dict.items():
        lines.append(f"{src_name} = {dst_name}")

    for chain_key, cfg_data in chain_configs.items():
        lines.extend(["", f"[chain.{chain_key}]"])
        lines.append(f"root_bone = {cfg_data.get('root_bone', '')}")
        lines.append(f"chain_bones = {', '.join(cfg_data.get('chain_bones', []))}")
        lines.append(f"source_bones = {', '.join(cfg_data.get('source_bones', []))}")
        lines.append(f"parent_bone = {cfg_data.get('parent_bone', 'SKEL_Head')}")
        lines.append(f"parent_bone_tag = {int(cfg_data.get('parent_bone_tag', SKEL_HEAD_TAG))}")
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
    match = re.search(
        rf"^\s*{re.escape(field_name)}:\s*\{{x:\s*([^,]+),\s*y:\s*([^,]+),\s*z:\s*([^}}]+)\}}",
        block_text,
        re.MULTILINE,
    )
    if not match:
        return default_val
    return (float(match.group(1)), float(match.group(2)), float(match.group(3)))


def _parse_yaml_curve(block_text: str, curve_field: str) -> List[Tuple[float, float]]:
    """Extract keyframe (time, value) pairs from a Unity AnimationCurve YAML block."""
    match = re.search(
        rf"^\s*{re.escape(curve_field)}:\s*\n\s*serializedVersion:\s*\d+\s*\n\s*m_Curve:\s*(.*?)(?=^\s*[A-Za-z_]\w*:|\Z)",
        block_text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return []
    curve_body = match.group(1)
    pairs = re.findall(r"time:\s*([^\n\r]+)\s*\n\s*value:\s*([^\n\r]+)", curve_body)
    return [(float(time_str), float(val_str)) for time_str, val_str in pairs]


def extract_unity_physbones_from_prefab(
    prefab_path: str | Path,
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
    documents = re.split(r"(?=^--- !u!\d+ &\d+)", raw_text, flags=re.MULTILINE)

    gameobject_names: Dict[str, str] = {}
    physbone_blocks: Dict[str, str] = {}
    target_lookup = {name.lower(): name for name in target_names}

    for doc_text in documents:
        header_match = re.match(r"^--- !u!(\d+) &(\d+)", doc_text)
        if not header_match:
            continue
        class_id = header_match.group(1)
        file_id = header_match.group(2)
        if class_id == "1":
            name_match = re.search(r"^\s*m_Name:\s*(.+?)\s*$", doc_text, re.MULTILINE)
            if name_match:
                gameobject_names[file_id] = name_match.group(1).strip()
        elif class_id == "114" and VRCHAT_PHYSBONE_SCRIPT_GUID in doc_text:
            go_match = re.search(r"^\s*m_GameObject:\s*\{fileID:\s*(\d+)\}", doc_text, re.MULTILINE)
            if go_match:
                physbone_blocks[go_match.group(1)] = doc_text

    extracted: Dict[str, Dict[str, object]] = {}
    spec_by_key = {spec[0].lower(): spec for spec in NEKO_MIMI_CHAIN_SPECS}

    def read_float(block_text: str, key_name: str, default_val: float) -> float:
        matched = re.search(rf"^\s*{re.escape(key_name)}:\s*([-+0-9.eE]+)\s*$", block_text, re.MULTILINE)
        return float(matched.group(1)) if matched else default_val

    def read_int(block_text: str, key_name: str, default_val: int) -> int:
        matched = re.search(rf"^\s*{re.escape(key_name)}:\s*([-+]?\d+)\s*$", block_text, re.MULTILINE)
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


def export_physbone_asi_ini(
    ini_path: str | Path,
    chain_records: Sequence[Dict[str, object]],
    target_ped_model: str = "player_zero",
) -> Path:
    """
    Export runtime chain parameters and baked GTA V rest transforms to GTAVPhysBones.ini.

    Each entry in `chain_records` contains:
      - `name`: string identifier (`PB_Ear_L`, `PB_Ear_R`)
      - `parent_bone_tag`: uint16 tag (`31086` for `SKEL_Head`)
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
            gravity_disp = (0.0, 0.0, -9.81 * gravity_val * clamped_dt * clamped_dt)

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

            if limit_type == 1:
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
