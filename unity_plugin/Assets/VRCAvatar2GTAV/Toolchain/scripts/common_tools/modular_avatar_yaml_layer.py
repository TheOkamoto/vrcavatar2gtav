#!/usr/bin/env python3
"""
modular_avatar_yaml_layer.py
============================
Layer 1 of 2 for native Modular Avatar (NDMF) baking (`modular_avatar_helper`).

Owns Modular Avatar & VRChat script GUID constants, HumanBodyBones tables,
armature prefix/suffix inference, GUID asset indexing, and multi-document Unity
`.unity`/`.prefab` YAML parsing.
"""

from __future__ import annotations

from collections import deque
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time as time_mod
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

COMMON_TOOLS_DIR = Path(__file__).resolve().parent
if str(COMMON_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_TOOLS_DIR))

import error_handler_helper as err_helper

try:
    import unity_scene_helper
except ImportError:
    unity_scene_helper = None

try:
    import unity_hair_helper
except ImportError:
    unity_hair_helper = None


# Modular Avatar script GUIDs verified from Packages/nadena.dev.modular-avatar/Runtime/
MA_MERGE_ARMATURE_GUID = "2df373bf91cf30b4bbd495e11cb1a2ec"
MA_BONE_PROXY_GUID = "42581d8044b64899834d3d515ab3a144"
MA_MESH_SETTINGS_GUID = "560fdafd46c74b2db6422fdf0e7f2363"
MA_BLENDSHAPE_SYNC_GUID = "6fd7cab7d93b403280f2f9da978d8a4f"
MA_REPLACE_OBJECT_GUID = "7e949680c0864ee7b441d9b2c93b890b"
MA_OBJECT_TOGGLE_GUID = "a162bb8ec7e24a5abcf457887f1df3fa"
MA_SHAPE_CHANGER_GUID = "2db441f589c3407bb6fb5f02ff8ab541"
MA_SCALE_ADJUSTER_GUID = "09a660aa9d4e47d992adcac5a05dd808"
MA_ACTIVATOR_GUID = "e41c5d0c41074360bc33887977722a4d"
MA_MENU_ITEM_GUID = "3b29d45007c5493d926d2cd45a489529"
VRC_PHYSBONE_GUID = "2a2c05204084d904aa4945ccff20d8e5"

# Unity UnityEngine.HumanBodyBones enum -> ordered bone name aliases in VRChat/Blender rigs
HUMAN_BODY_BONES: Dict[int, Tuple[str, ...]] = {
    0: ("Hips", "hips", "Pelvis"),
    1: ("LeftUpperLeg", "UpperLeg.L", "Upper_leg_L", "Leg_L", "Thigh.L", "UpperLeg_L"),
    2: ("RightUpperLeg", "UpperLeg.R", "Upper_leg_R", "Leg_R", "Thigh.R", "UpperLeg_R"),
    3: ("LeftLowerLeg", "LowerLeg.L", "Lower_leg_L", "Knee.L", "Calf.L", "LowerLeg_L"),
    4: ("RightLowerLeg", "LowerLeg.R", "Lower_leg_R", "Knee.R", "Calf.R", "LowerLeg_R"),
    5: ("LeftFoot", "Foot.L", "Foot_L", "Ankle.L"),
    6: ("RightFoot", "Foot.R", "Foot_R", "Ankle.R"),
    7: ("Spine", "spine"),
    8: ("Chest", "chest", "Spine1", "UpperChest"),
    9: ("Neck", "neck"),
    10: ("Head", "head"),
    11: ("LeftShoulder", "Shoulder.L", "Shoulder_L"),
    12: ("RightShoulder", "Shoulder.R", "Shoulder_R"),
    13: ("LeftUpperArm", "UpperArm.L", "Upper_arm_L", "Arm.L", "UpperArm_L"),
    14: ("RightUpperArm", "UpperArm.R", "Upper_arm_R", "Arm.R", "UpperArm_R"),
    15: ("LeftLowerArm", "LowerArm.L", "Lower_arm_L", "Elbow.L", "ForeArm.L", "LowerArm_L"),
    16: ("RightLowerArm", "LowerArm.R", "Lower_arm_R", "Elbow.R", "ForeArm.R", "LowerArm_R"),
    17: ("LeftHand", "Hand.L", "Hand_L", "Wrist.L", "Left wrist"),
    18: ("RightHand", "Hand.R", "Hand_R", "Wrist.R", "Right wrist"),
    19: ("LeftToes", "Toe.L", "Toes.L", "Toe_L"),
    20: ("RightToes", "Toe.R", "Toes.R", "Toe_R"),
    21: ("LeftEye", "Eye.L", "Eye_L"),
    22: ("RightEye", "Eye.R", "Eye_R"),
    23: ("Jaw", "jaw"),
    54: ("UpperChest", "Upper_Chest", "Chest", "Spine2"),
}

_SKIP_SCAN_DIRS: Set[str] = {
    ".git",
    "library",
    "temp",
    "obj",
    "logs",
    "usersettings",
    "node_modules",
    "__pycache__",
}

_SKIP_GUID_DIRS: Set[str] = _SKIP_SCAN_DIRS | {
    "texture",
    "textures",
    "tex",
    "shader",
    "shaders",
    "animation",
    "animations",
    "anim",
    "psd",
    "audio",
    "sound",
    "sfx",
    "vfx",
    "particle",
    "particles",
    "sprites",
    "fx",
    "mask",
    "masks",
    "normal",
    "normals",
    "vrcsdk",
    "samples",
    "__backup",
}


def _decode_scalar(raw_val: str) -> str:
    """Decode YAML quotes and unicode escapes from a scalar string."""
    if unity_scene_helper is not None and hasattr(unity_scene_helper, "decode_unity_name"):
        return unity_scene_helper.decode_unity_name(raw_val)
    cleaned = raw_val.strip()
    if len(cleaned) >= 2 and cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1]
        try:
            cleaned = bytes(cleaned, "utf-8").decode("unicode_escape")
        except Exception:
            pass
    return cleaned.strip()


def normalize_bone_match_key(bone_name: str) -> str:
    """
    Produce a canonical comparison key mirroring Modular Avatar HeuristicBoneMapper:
    strips `.001` duplicates, underscores, spaces, hyphens, and canonicalizes Left/Right.
    """
    base_name = re.sub(r"\.\d{3}$", "", str(bone_name or "").strip())
    low_name = base_name.lower()
    side_tag = ""
    if low_name.startswith("left") and len(low_name) > 4:
        side_tag = "l"
        low_name = low_name[4:]
    elif low_name.startswith("right") and len(low_name) > 5:
        side_tag = "r"
        low_name = low_name[5:]
    elif low_name.endswith((".l", "_l", "-l")):
        side_tag = "l"
        low_name = low_name[:-2]
    elif low_name.endswith((".r", "_r", "-r")):
        side_tag = "r"
        low_name = low_name[:-2]

    compact = re.sub(r"[\s_\-.]+", "", low_name)
    alias_map = {
        "pelvis": "hips",
        "upperchest": "upperchest",
        "chest": "chest",
        "thigh": "upperleg",
        "calf": "lowerleg",
        "knee": "lowerleg",
        "ankle": "foot",
        "elbow": "lowerarm",
        "forearm": "lowerarm",
        "wrist": "hand",
        "toes": "toe",
    }
    compact = alias_map.get(compact, compact)
    return f"{compact}_{side_tag}" if side_tag else compact


def infer_armature_prefix_suffix(
    source_bones: Sequence[str],
    target_bones: Iterable[str],
) -> Tuple[str, str]:
    """
    Reproduce Modular Avatar's HeuristicBoneMapper prefix/suffix inference when
    MergeArmature leaves `prefix`/`suffix` empty on differently named bone hierarchies.
    """
    target_set = {str(bone_name).strip() for bone_name in target_bones if bone_name}
    common_anchors = ("Hips", "Spine", "Chest", "Neck", "Head")
    for anchor_bone in common_anchors:
        if anchor_bone not in target_set:
            continue
        for src_bone in source_bones:
            idx = src_bone.find(anchor_bone)
            if idx >= 0:
                cand_prefix = src_bone[:idx]
                cand_suffix = src_bone[idx + len(anchor_bone) :]
                if cand_prefix or cand_suffix:
                    return cand_prefix, cand_suffix
    return "", ""


def resolve_ma_bone_mapping(
    source_bones: Sequence[str],
    target_bones: Iterable[str],
    *,
    prefix: str = "",
    suffix: str = "",
) -> Dict[str, str]:
    """
    Map source armature bones to target armature bones using Modular Avatar rules:
      1. Strip `prefix` and `suffix` (explicit or heuristic inferred if empty)
      2. Exact match on stripped bone name in target armature
      3. Normalized heuristic alias match (`UpperArm.L` <-> `LeftUpperArm` <-> `Arm_L`)
    Bones not present in the return dict are outfit-only custom bones (e.g. skirts,
    ribbons, PhysBones) that should remain parented under their mapped ancestor.
    """
    target_list = [str(bone_item) for bone_item in target_bones if bone_item]
    exact_map = {bone_item: bone_item for bone_item in target_list}
    lower_map = {bone_item.lower(): bone_item for bone_item in target_list}
    norm_map: Dict[str, str] = {}
    for bone_item in target_list:
        norm_key = normalize_bone_match_key(bone_item)
        if norm_key and norm_key not in norm_map:
            norm_map[norm_key] = bone_item

    eff_prefix = prefix
    eff_suffix = suffix
    if not eff_prefix and not eff_suffix:
        has_exact_hips = any(bone_item in exact_map for bone_item in source_bones)
        if not has_exact_hips:
            eff_prefix, eff_suffix = infer_armature_prefix_suffix(source_bones, target_list)

    mapping: Dict[str, str] = {}
    for src_bone in source_bones:
        candidate = re.sub(r"\.\d{3}$", "", str(src_bone))
        if eff_prefix and candidate.startswith(eff_prefix):
            candidate = candidate[len(eff_prefix) :]
        if eff_suffix and candidate.endswith(eff_suffix) and len(candidate) > len(eff_suffix):
            candidate = candidate[: -len(eff_suffix)]

        if not candidate:
            continue
        if candidate in exact_map:
            mapping[src_bone] = exact_map[candidate]
        elif candidate.lower() in lower_map:
            mapping[src_bone] = lower_map[candidate.lower()]
        else:
            norm_cand = normalize_bone_match_key(candidate)
            if norm_cand in norm_map:
                mapping[src_bone] = norm_map[norm_cand]
    return mapping


def _parse_unity_vec3(block: str, field_name: str, default_xyz: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Extract an `{x: ..., y: ..., z: ...}` Unity YAML vector field cleanly."""
    match_obj = re.search(rf"^\s*{re.escape(field_name)}:\s*\{{([^}}]*)\}}", block, re.MULTILINE)
    if not match_obj:
        return default_xyz
    vals = {"x": default_xyz[0], "y": default_xyz[1], "z": default_xyz[2]}
    for part in match_obj.group(1).split(","):
        if ":" not in part:
            continue
        key_tok, raw_val = part.split(":", 1)
        key_clean = key_tok.strip()
        if key_clean in vals:
            try:
                vals[key_clean] = float(raw_val.strip())
            except ValueError:
                pass
    return (vals["x"], vals["y"], vals["z"])


def _parse_unity_quat(
    block: str,
    field_name: str,
    default_xyzw: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
) -> Tuple[float, float, float, float]:
    """Extract an `{x: ..., y: ..., z: ..., w: ...}` Unity YAML quaternion field."""
    match_obj = re.search(rf"^\s*{re.escape(field_name)}:\s*\{{([^}}]*)\}}", block, re.MULTILINE)
    if not match_obj:
        return default_xyzw
    vals = {"x": default_xyzw[0], "y": default_xyzw[1], "z": default_xyzw[2], "w": default_xyzw[3]}
    for part in match_obj.group(1).split(","):
        if ":" not in part:
            continue
        key_tok, raw_val = part.split(":", 1)
        key_clean = key_tok.strip()
        if key_clean in vals:
            try:
                vals[key_clean] = float(raw_val.strip())
            except ValueError:
                pass
    return (vals["x"], vals["y"], vals["z"], vals["w"])


def _extract_inline_ref(field_snippet: str) -> Tuple[str, str]:
    """Extract `(fileID, guid)` from a Unity object reference `{fileID: ..., guid: ...}`."""
    file_id_match = re.search(r"fileID:\s*(-?\d+)", field_snippet)
    guid_match = re.search(r"guid:\s*([0-9a-fA-F]{32})", field_snippet)
    return (file_id_match.group(1) if file_id_match else "0", guid_match.group(1).lower() if guid_match else "")


_MA_PARSED_YAML_CACHE: Dict[Tuple[str, int], Dict[str, Any]] = {}


def parse_unity_yaml_with_ma(yaml_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Stream-parse a `.unity` scene or `.prefab` extracting hierarchy, renderers,
    PrefabInstances, and all Modular Avatar components cleanly.
    """
    resolved_path = Path(yaml_path)
    empty_doc: Dict[str, Any] = {
        "gameobjects": {},
        "transforms": {},
        "go_to_tr": {},
        "renderers": {},
        "mesh_filters": {},
        "prefab_instances": {},
        "merge_armatures": [],
        "bone_proxies": [],
        "scale_adjusters": [],
        "blendshape_syncs": [],
        "object_toggles": [],
        "shape_changers": [],
        "replace_objects": [],
        "mesh_settings": [],
        "activators": [],
        "physbones": [],
        "menu_items": {},
    }
    if not resolved_path.is_file():
        return empty_doc

    try:
        cache_key = (str(resolved_path.resolve()), resolved_path.stat().st_mtime_ns)
    except OSError:
        cache_key = None
    if cache_key is not None and cache_key in _MA_PARSED_YAML_CACHE:
        return _MA_PARSED_YAML_CACHE[cache_key]

    try:
        raw_text = resolved_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        err_helper.get_active_logger_from_env(stage_name="ma_parse").warning(
            f"Failed reading Unity YAML {resolved_path}: {exc}"
        )
        return empty_doc

    blocks = raw_text.split("\n--- !u!")
    gameobjects: Dict[str, Dict[str, Any]] = {}
    transforms: Dict[str, Dict[str, Any]] = {}
    game_object_to_transform: Dict[str, str] = {}
    renderers: Dict[str, Dict[str, Any]] = {}
    mesh_filters: Dict[str, str] = {}
    prefab_instances: Dict[str, Dict[str, Any]] = {}
    merge_armatures: List[Dict[str, Any]] = []
    bone_proxies: List[Dict[str, Any]] = []
    scale_adjusters: List[Dict[str, Any]] = []
    blendshape_syncs: List[Dict[str, Any]] = []
    object_toggles: List[Dict[str, Any]] = []
    shape_changers: List[Dict[str, Any]] = []
    replace_objects: List[Dict[str, Any]] = []
    mesh_settings: List[Dict[str, Any]] = []
    activators: List[Dict[str, Any]] = []
    physbones: List[Dict[str, Any]] = []
    menu_items: Dict[str, Dict[str, Any]] = {}

    for block in blocks[1:]:
        newline_idx = block.find("\n")
        if newline_idx <= 0:
            continue
        header_line = block[:newline_idx].strip()
        is_stripped = header_line.endswith("stripped")
        if " &" not in header_line:
            continue
        cls_part, fid_part = header_line.split(" &", 1)
        class_id = cls_part.strip()
        file_id = fid_part.split()[0].strip()

        if class_id == "1":
            name_match = re.search(r"^\s*m_Name:[ \t]*(.+)$", block, re.MULTILINE)
            active_match = re.search(r"^\s*m_IsActive:[ \t]*(\d+)", block, re.MULTILINE)
            tag_match = re.search(r"^\s*m_TagString:[ \t]*(.+)$", block, re.MULTILINE)
            is_editor_only = bool(tag_match and _decode_scalar(tag_match.group(1)) == "EditorOnly")
            prefab_instance_match = re.search(r"m_PrefabInstance:\s*\{fileID:\s*(-?\d+)", block)
            gameobjects[file_id] = {
                "name": _decode_scalar(name_match.group(1)) if name_match else "",
                "active": ((int(active_match.group(1)) != 0) if active_match else True) and not is_editor_only,
                "pi_fid": prefab_instance_match.group(1) if prefab_instance_match else "0",
            }
        elif class_id == "4":
            if is_stripped:
                continue
            game_object_match = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", block)
            father_match = re.search(r"m_Father:\s*\{fileID:\s*(-?\d+)", block)
            child_fids: List[str] = []
            if "m_Children:" in block:
                child_chunk = block.split("m_Children:", 1)[1].split("m_Father:", 1)[0]
                child_fids = re.findall(r"-\s*\{fileID:\s*(-?\d+)", child_chunk)
            if game_object_match:
                game_object_id = game_object_match.group(1)
                transforms[file_id] = {
                    "go_fid": game_object_id,
                    "father_tr": father_match.group(1) if father_match else "0",
                    "children": child_fids,
                    "pos": _parse_unity_vec3(block, "m_LocalPosition", (0.0, 0.0, 0.0)),
                    "rot": _parse_unity_quat(block, "m_LocalRotation", (0.0, 0.0, 0.0, 1.0)),
                    "scale": _parse_unity_vec3(block, "m_LocalScale", (1.0, 1.0, 1.0)),
                }
                game_object_to_transform[game_object_id] = file_id
        elif class_id in ("23", "137"):
            game_object_match = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", block)
            enabled_match = re.search(r"^\s*m_Enabled:[ \t]*(\d+)", block, re.MULTILINE)
            mesh_match = re.search(r"m_Mesh:\s*\{([^\}]*)\}", block)
            root_bone_match = re.search(r"m_RootBone:\s*\{fileID:\s*(-?\d+)", block)
            mat_sec = re.search(
                r"m_Materials:(.*?)(?=^\s{2}[a-zA-Z_][a-zA-Z0-9_]*:|\Z)",
                block,
                re.DOTALL | re.MULTILINE,
            )
            mat_guids = (
                [
                    _extract_inline_ref(entry_txt)[1]
                    for entry_txt in re.findall(r"-\s*\{([^}]*)\}", mat_sec.group(1))
                ]
                if mat_sec
                else []
            )
            mesh_fid, mesh_guid = _extract_inline_ref(mesh_match.group(1)) if mesh_match else ("0", "")
            if game_object_match:
                renderers[game_object_match.group(1)] = {
                    "comp_fid": file_id,
                    "go_fid": game_object_match.group(1),
                    "class_id": class_id,
                    "enabled": (int(enabled_match.group(1)) != 0) if enabled_match else True,
                    "mesh_fid": mesh_fid,
                    "mesh_guid": mesh_guid,
                    "root_bone_tr": root_bone_match.group(1) if root_bone_match else "0",
                    "mat_guids": mat_guids,
                }
        elif class_id == "33":
            game_object_match = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", block)
            mesh_match = re.search(r"m_Mesh:\s*\{([^\}]*)\}", block)
            if game_object_match and mesh_match:
                _mfid, mguid = _extract_inline_ref(mesh_match.group(1))
                if mguid:
                    mesh_filters[game_object_match.group(1)] = mguid
        elif class_id == "1001":
            parent_match = re.search(r"m_TransformParent:\s*\{fileID:\s*(-?\d+)", block)
            source_match = re.search(
                r"m_SourcePrefab:\s*\{fileID:\s*-?\d+,\s*guid:\s*([0-9a-fA-F]{32})",
                block,
            )
            src_guid = source_match.group(1).lower() if source_match else ""
            prefab_instance_name = ""
            root_name_tid = ""
            active_by_tid: Dict[str, bool] = {}
            mods: List[Dict[str, str]] = []
            for mod_match in re.finditer(
                r"-\s*target:\s*\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-fA-F]{32}))?[^\}]*\}[ \t]*\r?\n"
                r"[ \t]*propertyPath:[ \t]*([^\r\n]+)\r?\n"
                r"[ \t]*value:[ \t]*([^\r\n]*)\r?\n"
                r"[ \t]*objectReference:[ \t]*\{([^\}]*)\}",
                block,
            ):
                tgt_fid = mod_match.group(1)
                tgt_guid = (mod_match.group(2) or "").lower()
                prop_path = mod_match.group(3).strip()
                raw_val = _decode_scalar(mod_match.group(4))
                _ref_fid, ref_guid = _extract_inline_ref(mod_match.group(5))
                if prop_path == "m_Name" and raw_val:
                    is_src = bool(src_guid and tgt_guid == src_guid)
                    if not prefab_instance_name or (is_src and not root_name_tid):
                        prefab_instance_name = raw_val
                        root_name_tid = tgt_fid
                elif prop_path == "m_IsActive" and tgt_fid:
                    if not src_guid or not tgt_guid or tgt_guid == src_guid:
                        active_by_tid[tgt_fid] = raw_val != "0"
                mods.append(
                    {
                        "target_fid": tgt_fid,
                        "target_guid": tgt_guid,
                        "property": prop_path,
                        "value": raw_val,
                        "ref_fid": _ref_fid,
                        "ref_guid": ref_guid,
                    }
                )
            prefab_instance_active = True
            if root_name_tid and root_name_tid in active_by_tid:
                prefab_instance_active = active_by_tid[root_name_tid]
            elif not root_name_tid and "100000" in active_by_tid:
                prefab_instance_active = active_by_tid["100000"]

            prefab_instances[file_id] = {
                "parent_tr": parent_match.group(1) if parent_match else "0",
                "source_guid": src_guid,
                "name": prefab_instance_name,
                "active": prefab_instance_active,
                "mods": mods,
            }
        elif class_id == "114":
            script_match = re.search(r"m_Script:\s*\{[^\}]*guid:\s*([0-9a-fA-F]{32})", block)
            game_object_match = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", block)
            enabled_match = re.search(r"^\s*m_Enabled:[ \t]*(\d+)", block, re.MULTILINE)
            if not (script_match and game_object_match):
                continue
            script_guid = script_match.group(1).lower()
            game_object_file_id = game_object_match.group(1)
            is_enabled = (int(enabled_match.group(1)) != 0) if enabled_match else True

            if script_guid == MA_MERGE_ARMATURE_GUID:
                ref_match = re.search(r"mergeTarget:\s*\n(?:[ \t]+[^\n]*\n)*?[ \t]*referencePath:[ \t]*([^\r\n]*)", block)
                prefab_match = re.search(r"^\s*prefix:[ \t]*([^\r\n]*)", block, re.MULTILINE)
                suffix_match = re.search(r"^\s*suffix:[ \t]*([^\r\n]*)", block, re.MULTILINE)
                mangle_match = re.search(r"^\s*mangleNames:[ \t]*(\d+)", block, re.MULTILINE)
                merge_armatures.append(
                    {
                        "go_fid": game_object_file_id,
                        "enabled": is_enabled,
                        "merge_target_path": _decode_scalar(ref_match.group(1)) if ref_match else "",
                        "prefix": _decode_scalar(prefab_match.group(1)) if prefab_match else "",
                        "suffix": _decode_scalar(suffix_match.group(1)) if suffix_match else "",
                        "mangle_names": (int(mangle_match.group(1)) != 0) if mangle_match else True,
                    }
                )
            elif script_guid == MA_BONE_PROXY_GUID:
                bone_ref_match = re.search(r"boneReference:[ \t]*(-?\d+)", block)
                sub_path_match = re.search(r"subPath:[ \t]*([^\r\n]*)", block)
                attach_match = re.search(r"attachmentMode:[ \t]*(-?\d+)", block)
                scale_match = re.search(r"matchScale:[ \t]*(\d+)", block)
                bone_proxies.append(
                    {
                        "go_fid": game_object_file_id,
                        "enabled": is_enabled,
                        "bone_reference": int(bone_ref_match.group(1)) if bone_ref_match else -1,
                        "sub_path": _decode_scalar(sub_path_match.group(1)) if sub_path_match else "",
                        "attachment_mode": int(attach_match.group(1)) if attach_match else 1,
                        "match_scale": (int(scale_match.group(1)) != 0) if scale_match else False,
                    }
                )
            elif script_guid == MA_SCALE_ADJUSTER_GUID:
                vec_match = re.search(
                    r"m_Scale:\s*\{x:\s*([^,]+),\s*y:\s*([^,]+),\s*z:\s*([^\}]+)\}",
                    block,
                )
                if vec_match and is_enabled:
                    try:
                        scale_xyz = (
                            float(vec_match.group(1)),
                            float(vec_match.group(2)),
                            float(vec_match.group(3)),
                        )
                    except ValueError:
                        scale_xyz = (1.0, 1.0, 1.0)
                    scale_adjusters.append(
                        {"go_fid": game_object_file_id, "enabled": is_enabled, "scale": scale_xyz}
                    )
            elif script_guid == MA_BLENDSHAPE_SYNC_GUID and is_enabled:
                bindings: List[Dict[str, Any]] = []
                for bnd_match in re.finditer(
                    r"-\s*ReferenceMesh:[ \t]*\r?\n"
                    r"(?:[ \t]+[^\n]*\n)*?"
                    r"[ \t]*referencePath:[ \t]*([^\r\n]*)\r?\n"
                    r"(?:[ \t]*targetObject:[ \t]*[^\r\n]*\r?\n)?"
                    r"[ \t]*Blendshape:[ \t]*([^\r\n]*)\r?\n"
                    r"[ \t]*LocalBlendshape:[ \t]*([^\r\n]*)",
                    block,
                ):
                    ref_mesh = _decode_scalar(bnd_match.group(1))
                    src_shape = _decode_scalar(bnd_match.group(2))
                    local_shape = _decode_scalar(bnd_match.group(3)) or src_shape
                    tail_blk = block[bnd_match.end():].split("\n  - ReferenceMesh:", 1)[0]
                    remap_pts = [
                        (float(key_pair.group(1)), float(key_pair.group(2)))
                        for key_pair in re.finditer(
                            r"time:\s*([-+0-9.eE]+)\s*\r?\n\s*value:\s*([-+0-9.eE]+)",
                            tail_blk,
                        )
                    ]
                    if src_shape:
                        bindings.append(
                            {
                                "reference_mesh_path": ref_mesh,
                                "source_shape": src_shape,
                                "local_shape": local_shape,
                                "remap_curve": remap_pts,
                            }
                        )
                if bindings:
                    blendshape_syncs.append({"go_fid": game_object_file_id, "bindings": bindings})
            elif script_guid == MA_OBJECT_TOGGLE_GUID and is_enabled:
                inverted_match = re.search(r"^\s*m_inverted:[ \t]*(\d+)", block, re.MULTILINE)
                is_inverted = (int(inverted_match.group(1)) != 0) if inverted_match else False
                if not is_inverted:
                    toggles: List[Dict[str, Any]] = []
                    for toggle_match in re.finditer(
                        r"-\s*Object:[ \t]*\r?\n"
                        r"(?:[ \t]+[^\n]*\n)*?"
                        r"[ \t]*referencePath:[ \t]*([^\r\n]*)\r?\n"
                        r"(?:[ \t]*targetObject:[ \t]*[^\r\n]*\r?\n)?"
                        r"[ \t]*Active:[ \t]*(\d+)",
                        block,
                    ):
                        toggles.append(
                            {
                                "reference_path": _decode_scalar(toggle_match.group(1)),
                                "active": int(toggle_match.group(2)) != 0,
                            }
                        )
                    if toggles:
                        object_toggles.append({"go_fid": game_object_file_id, "toggles": toggles})
            elif script_guid == MA_SHAPE_CHANGER_GUID and is_enabled:
                inverted_match = re.search(r"^\s*m_inverted:[ \t]*(\d+)", block, re.MULTILINE)
                is_inverted = (int(inverted_match.group(1)) != 0) if inverted_match else False
                threshold_match = re.search(r"^\s*m_threshold:[ \t]*([-+0-9.eE]+)", block, re.MULTILINE)
                threshold = float(threshold_match.group(1)) if threshold_match else 0.01
                if not is_inverted:
                    shapes: List[Dict[str, Any]] = []
                    for shape_match in re.finditer(
                        r"-\s*Object:[ \t]*\r?\n"
                        r"(?:[ \t]+[^\n]*\n)*?"
                        r"[ \t]*referencePath:[ \t]*([^\r\n]*)\r?\n"
                        r"(?:[ \t]*targetObject:[ \t]*[^\r\n]*\r?\n)?"
                        r"[ \t]*ShapeName:[ \t]*([^\r\n]*)\r?\n"
                        r"[ \t]*ChangeType:[ \t]*(-?\d+)\r?\n"
                        r"[ \t]*Value:[ \t]*([^\r\n]+)",
                        block,
                    ):
                        shape_name = _decode_scalar(shape_match.group(2))
                        change_type = int(shape_match.group(3))
                        try:
                            raw_num = float(shape_match.group(4).strip())
                        except ValueError:
                            continue
                        weight_norm = 1.0 if change_type == 0 else (raw_num / 100.0)
                        if shape_name:
                            shapes.append(
                                {
                                    "reference_path": _decode_scalar(shape_match.group(1)),
                                    "shape_name": shape_name,
                                    "change_type": change_type,
                                    "weight": weight_norm,
                                    "threshold": threshold,
                                }
                            )
                    if shapes:
                        shape_changers.append({"go_fid": game_object_file_id, "shapes": shapes})
            elif script_guid == MA_REPLACE_OBJECT_GUID and is_enabled:
                ref_match = re.search(
                    r"targetObject:\s*\n(?:[ \t]+[^\n]*\n)*?[ \t]*referencePath:[ \t]*([^\r\n]*)",
                    block,
                )
                if ref_match and ref_match.group(1).strip():
                    replace_objects.append(
                        {"go_fid": game_object_file_id, "target_path": _decode_scalar(ref_match.group(1))}
                    )
            elif script_guid == MA_MESH_SETTINGS_GUID and is_enabled:
                root_match = re.search(
                    r"RootBone:\s*\n(?:[ \t]+[^\n]*\n)*?[ \t]*referencePath:[ \t]*([^\r\n]*)",
                    block,
                )
                mesh_settings.append(
                    {
                        "go_fid": game_object_file_id,
                        "root_bone_path": _decode_scalar(root_match.group(1)) if root_match else "",
                    }
                )
            elif script_guid == MA_ACTIVATOR_GUID:
                activators.append({"go_fid": game_object_file_id, "enabled": is_enabled})
            elif script_guid == MA_MENU_ITEM_GUID:
                def_match = re.search(r"^\s*isDefault:[ \t]*(\d+)", block, re.MULTILINE)
                menu_items[game_object_file_id] = {
                    "enabled": is_enabled,
                    "is_default": (int(def_match.group(1)) != 0) if def_match else False,
                }
            elif script_guid == VRC_PHYSBONE_GUID and is_enabled:
                root_match = re.search(r"rootTransform:\s*\{fileID:\s*(-?\d+)", block)
                physbones.append(
                    {
                        "go_fid": game_object_file_id,
                        "root_tr": root_match.group(1) if root_match else "0",
                    }
                )

    parsed_doc = {
        "gameobjects": gameobjects,
        "transforms": transforms,
        "go_to_tr": game_object_to_transform,
        "renderers": renderers,
        "mesh_filters": mesh_filters,
        "prefab_instances": prefab_instances,
        "merge_armatures": merge_armatures,
        "bone_proxies": bone_proxies,
        "scale_adjusters": scale_adjusters,
        "blendshape_syncs": blendshape_syncs,
        "object_toggles": object_toggles,
        "shape_changers": shape_changers,
        "replace_objects": replace_objects,
        "mesh_settings": mesh_settings,
        "activators": activators,
        "physbones": physbones,
        "menu_items": menu_items,
    }
    if cache_key is not None:
        _MA_PARSED_YAML_CACHE[cache_key] = parsed_doc
    return parsed_doc


_MA_GUID_CACHE: Dict[str, Optional[Path]] = {}
_MA_GUID_SCAN_STATE: Dict[str, Dict[str, Any]] = {}


def _is_builtin_unity_guid(guid_str: str) -> bool:
    """Return True for built-in Unity internal asset GUIDs that have no .meta on disk."""
    clean = guid_str.strip().lower()
    return not clean or clean.startswith(("0000000000000000", "f000000000000000"))


def _scan_single_directory_tree_guids(
    root_dir_path: str,
    meta_suffixes: Tuple[str, ...],
    skip_dirs: Set[str],
    deadline_monotonic: float,
) -> Dict[str, str]:
    """Scan one directory subtree via os.scandir without redundant stat calls."""
    found_map: Dict[str, str] = {}
    pending_dirs: List[str] = [root_dir_path]
    visited_paths: Set[str] = set()
    while pending_dirs:
        if time_mod.monotonic() > deadline_monotonic:
            break
        cur_dir_str = pending_dirs.pop()
        if cur_dir_str in visited_paths:
            continue
        visited_paths.add(cur_dir_str)
        try:
            dir_entries = list(os.scandir(cur_dir_str))
        except OSError:
            continue
        file_name_set: Set[str] = set()
        meta_paths: List[Tuple[str, str]] = []
        for entry_item in dir_entries:
            entry_name = entry_item.name
            if entry_item.is_dir(follow_symlinks=False):
                if not entry_name.startswith(".") and entry_name.lower() not in skip_dirs:
                    pending_dirs.append(entry_item.path)
            else:
                file_name_set.add(entry_name)
                if entry_name.lower().endswith(meta_suffixes):
                    meta_paths.append((entry_name, entry_item.path))
        for entry_name, meta_full_path in meta_paths:
            asset_file_name = entry_name[:-5]
            if asset_file_name not in file_name_set:
                continue
            try:
                with open(meta_full_path, "r", encoding="utf-8", errors="ignore") as meta_handle:
                    for line_idx, line_text in enumerate(meta_handle):
                        if line_text.startswith("guid:"):
                            found_guid = line_text.split(":", 1)[1].strip().lower()
                            if found_guid:
                                found_map[found_guid] = os.path.join(cur_dir_str, asset_file_name)
                            break
                        if line_idx > 6:
                            break
            except OSError:
                continue
    return found_map


def _get_guid_cache_file_path(assets_resolved: Path, include_materials: bool) -> Optional[Path]:
    """Return a stable per-project disk cache path outside temporary unit-test folders."""
    norm_str = str(assets_resolved)
    tmp_root = str(Path(tempfile.gettempdir()).resolve())
    if norm_str.startswith(tmp_root) or "/tmp/" in norm_str.replace("\\", "/"):
        return None
    cache_key = hashlib.sha1(f"{norm_str}|mats={int(include_materials)}".encode("utf-8")).hexdigest()[:12]
    cache_dir = Path.home() / ".cache" / "vrc2gtav"
    return cache_dir / f"ma_guid_index_{cache_key}.json"


def _collect_guid_paths_for_ma(
    needed_guids: Set[str],
    anchor_path: Path,
    assets_root: Optional[Path],
    *,
    name_hints: Sequence[str] = (),
    budget_sec: float = 90.0,
    include_materials: bool = False,
) -> Dict[str, Path]:
    """Resolve asset GUIDs quickly via disk cache + parallel top-level os.scandir."""
    clean_guids = {
        guid_str.lower()
        for guid_str in needed_guids
        if guid_str and not _is_builtin_unity_guid(guid_str)
    }
    resolved: Dict[str, Path] = {}
    if not clean_guids:
        return resolved

    remaining: Set[str] = set()
    for guid_str in clean_guids:
        cached = _MA_GUID_CACHE.get(guid_str)
        if cached is not None and cached.is_file():
            resolved[guid_str] = cached
        elif guid_str not in _MA_GUID_CACHE:
            remaining.add(guid_str)

    if not remaining:
        return resolved

    assets_resolved = assets_root.resolve() if (assets_root and assets_root.is_dir()) else None
    full_key = f"{assets_resolved}|mats={int(include_materials)}" if assets_resolved else ""
    scan_state = (
        _MA_GUID_SCAN_STATE.setdefault(
            full_key,
            {"seen_dirs": set(), "queue": deque(), "initialized": False, "complete": False},
        )
        if full_key
        else None
    )

    disk_cache_path = (
        _get_guid_cache_file_path(assets_resolved, include_materials)
        if assets_resolved is not None
        else None
    )
    disk_entries: Dict[str, str] = {}
    if remaining and disk_cache_path is not None and disk_cache_path.is_file():
        try:
            cache_payload = json.loads(disk_cache_path.read_text(encoding="utf-8"))
            cached_entries = cache_payload.get("entries", {})
            if isinstance(cached_entries, dict):
                for guid_key, raw_asset in cached_entries.items():
                    disk_entries[guid_key] = raw_asset
                    asset_candidate = Path(raw_asset)
                    _MA_GUID_CACHE.setdefault(guid_key, asset_candidate)
                    if guid_key in remaining and asset_candidate.is_file():
                        resolved[guid_key] = asset_candidate
                        remaining.discard(guid_key)
                if not remaining:
                    return resolved
        except (OSError, ValueError):
            pass

    if scan_state is not None and scan_state["complete"]:
        return resolved

    hint_words = {
        tok.lower()
        for raw_hint in [anchor_path.stem] + list(name_hints)
        for tok in re.split(r"[^A-Za-z0-9]+", str(raw_hint or ""))
        if len(tok) >= 3
    }
    hint_words.update(
        {
            "shinano",
            "miltina",
            "milltina",
            "retargeted",
            "converted",
            "panda",
            "nakonail",
            "nail",
            "neko",
            "tonarino",
            "prefab",
        }
    )

    search_roots: List[Path] = []
    if anchor_path:
        anchor_dir = anchor_path if anchor_path.is_dir() else anchor_path.parent
        cur_dir = anchor_dir
        for _step in range(3):
            if cur_dir.is_dir() and (
                assets_resolved is None or cur_dir.resolve() != assets_resolved
            ):
                if cur_dir not in search_roots:
                    search_roots.append(cur_dir)
            parent_dir = cur_dir.parent
            if parent_dir == cur_dir or (assets_resolved is not None and cur_dir.resolve() == assets_resolved):
                break
            cur_dir = parent_dir

    if assets_resolved is not None:
        # Match depth 1-2 package directories against avatar/mesh tokens
        def _collect_hinted_dirs(root_lvl: Path, depth_rem: int) -> None:
            if depth_rem <= 0:
                return
            try:
                entries = sorted(os.scandir(root_lvl), key=lambda ent: ent.name)
            except OSError:
                return
            for entry_item in entries:
                if not entry_item.is_dir(follow_symlinks=False) or entry_item.name.startswith("."):
                    continue
                low_name = entry_item.name.lower()
                if low_name in _SKIP_GUID_DIRS:
                    continue
                entry_path = Path(entry_item.path)
                if any(word in low_name for word in hint_words):
                    if entry_path not in search_roots:
                        search_roots.append(entry_path)
                else:
                    _collect_hinted_dirs(entry_path, depth_rem - 1)

        _collect_hinted_dirs(assets_resolved, 2)

        if unity_scene_helper is not None and hasattr(unity_scene_helper, "_priority_search_dirs"):
            for cand_dir in unity_scene_helper._priority_search_dirs(
                anchor_path, assets_resolved, [anchor_path.stem] + list(hint_words)
            ):
                if cand_dir.is_dir() and cand_dir.resolve() != assets_resolved and cand_dir not in search_roots:
                    search_roots.append(cand_dir)

    deadline = time_mod.monotonic() + max(0.5, budget_sec)
    meta_suffixes = (
        (".prefab.meta", ".fbx.meta", ".mat.meta") if include_materials else (".prefab.meta", ".fbx.meta")
    )
    local_seen: Set[str] = scan_state["seen_dirs"] if scan_state is not None else set()
    new_cache_hits = 0

    for priority_root in search_roots:
        if not remaining or time_mod.monotonic() > deadline:
            break
        root_key = str(priority_root)
        if root_key in local_seen:
            continue
        partial_map = _scan_single_directory_tree_guids(root_key, meta_suffixes, _SKIP_GUID_DIRS, deadline)
        if time_mod.monotonic() <= deadline:
            local_seen.add(root_key)
        for guid_key, asset_str in partial_map.items():
            if guid_key not in disk_entries:
                new_cache_hits += 1
            disk_entries[guid_key] = asset_str
            asset_obj = Path(asset_str)
            _MA_GUID_CACHE.setdefault(guid_key, asset_obj)
            if guid_key in remaining:
                resolved[guid_key] = asset_obj
                remaining.discard(guid_key)

    if remaining and assets_resolved is not None and time_mod.monotonic() <= deadline:
        top_subdirs: List[str] = []
        root_meta_hits: Dict[str, str] = {}
        try:
            root_entries = list(os.scandir(assets_resolved))
        except OSError:
            root_entries = []
        root_file_names: Set[str] = set()
        root_meta_items: List[Tuple[str, str]] = []
        for top_entry in sorted(root_entries, key=lambda ent: ent.name):
            if top_entry.is_dir(follow_symlinks=False) and not top_entry.name.startswith("."):
                if top_entry.name.lower() not in _SKIP_GUID_DIRS and top_entry.path not in local_seen:
                    top_subdirs.append(top_entry.path)
            else:
                root_file_names.add(top_entry.name)
                if top_entry.name.lower().endswith(meta_suffixes):
                    root_meta_items.append((top_entry.name, top_entry.path))
        for meta_name, meta_full in root_meta_items:
            asset_file_name = meta_name[:-5]
            if asset_file_name not in root_file_names:
                continue
            try:
                with open(meta_full, "r", encoding="utf-8", errors="ignore") as meta_handle:
                    for line_idx, line_text in enumerate(meta_handle):
                        if line_text.startswith("guid:"):
                            found_guid = line_text.split(":", 1)[1].strip().lower()
                            if found_guid:
                                root_meta_hits[found_guid] = os.path.join(str(assets_resolved), asset_file_name)
                            break
                        if line_idx > 6:
                            break
            except OSError:
                continue

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as dir_pool:
            future_to_dir = {
                dir_pool.submit(
                    _scan_single_directory_tree_guids,
                    subdir_path,
                    meta_suffixes,
                    _SKIP_GUID_DIRS,
                    deadline,
                ): subdir_path
                for subdir_path in top_subdirs
            }
            for fut_item in concurrent.futures.as_completed(future_to_dir):
                sub_dir = future_to_dir[fut_item]
                try:
                    sub_map = fut_item.result()
                except Exception:
                    continue
                if time_mod.monotonic() <= deadline:
                    local_seen.add(sub_dir)
                for guid_key, asset_str in sub_map.items():
                    if guid_key not in disk_entries:
                        new_cache_hits += 1
                    disk_entries[guid_key] = asset_str
                    asset_obj = Path(asset_str)
                    _MA_GUID_CACHE.setdefault(guid_key, asset_obj)
                    if guid_key in remaining:
                        resolved[guid_key] = asset_obj
                        remaining.discard(guid_key)

        for guid_key, asset_str in root_meta_hits.items():
            if guid_key not in disk_entries:
                new_cache_hits += 1
            disk_entries[guid_key] = asset_str
            asset_obj = Path(asset_str)
            _MA_GUID_CACHE.setdefault(guid_key, asset_obj)
            if guid_key in remaining:
                resolved[guid_key] = asset_obj
                remaining.discard(guid_key)

        if time_mod.monotonic() <= deadline and not remaining:
            if scan_state is not None:
                scan_state["complete"] = True
        elif time_mod.monotonic() <= deadline and len(top_subdirs) + len(search_roots) > 0:
            if scan_state is not None:
                scan_state["complete"] = True
            for missing_guid in remaining:
                _MA_GUID_CACHE.setdefault(missing_guid, None)

    if disk_cache_path is not None and disk_entries and new_cache_hits > 0:
        try:
            disk_cache_path.parent.mkdir(parents=True, exist_ok=True)
            disk_cache_path.write_text(
                json.dumps({"assets_root": str(assets_resolved), "entries": disk_entries}),
                encoding="utf-8",
            )
        except OSError:
            pass

    return resolved


def _is_game_object_active_in_doc(
    doc_data: Dict[str, Any],
    game_object_file_id: str,
    stop_transform: Optional[str] = None,
) -> bool:
    """Walk up Transforms in `doc_data` (stopping at selected avatar root `stop_tr`) to check active state."""
    visited: Set[str] = set()
    cur_game_object = game_object_file_id
    game_object_map = doc_data["gameobjects"]
    transform_map = doc_data["transforms"]
    game_object_to_transform = doc_data["go_to_tr"]
    cur_transform = game_object_to_transform.get(cur_game_object, "")

    if cur_transform and stop_transform and cur_transform == stop_transform:
        return True
    if cur_game_object in game_object_map and not game_object_map[cur_game_object].get("active", True):
        return False
    while cur_transform and cur_transform not in visited:
        if stop_transform and cur_transform == stop_transform:
            break
        visited.add(cur_transform)
        transform_info = transform_map.get(cur_transform)
        if transform_info is None:
            break
        node_game_object = transform_info.get("go_fid", "")
        if node_game_object in game_object_map and not game_object_map[node_game_object].get("active", True):
            return False
        parent_transform = transform_info.get("father_tr", "0")
        if parent_transform == "0":
            break
        cur_transform = parent_transform
    return True


IDENTITY_UNITY_TRS: Tuple[
    Tuple[float, float, float],
    Tuple[float, float, float, float],
    Tuple[float, float, float],
] = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0))


def _quat_mul_unity(
    quat_first: Tuple[float, float, float, float],
    quat_second: Tuple[float, float, float, float],
) -> Tuple[float, float, float, float]:
    """Multiply two Unity quaternions `(x, y, z, w)` cleanly."""
    first_quat_x, first_quat_y, first_quat_z, first_quat_scalar = quat_first
    second_quat_x, second_quat_y, second_quat_z, second_quat_scalar = quat_second
    return (
        first_quat_scalar * second_quat_x + first_quat_x * second_quat_scalar + first_quat_y * second_quat_z - first_quat_z * second_quat_y,
        first_quat_scalar * second_quat_y - first_quat_x * second_quat_z + first_quat_y * second_quat_scalar + first_quat_z * second_quat_x,
        first_quat_scalar * second_quat_z + first_quat_x * second_quat_y - first_quat_y * second_quat_x + first_quat_z * second_quat_scalar,
        first_quat_scalar * second_quat_scalar - first_quat_x * second_quat_x - first_quat_y * second_quat_y - first_quat_z * second_quat_z,
    )


def _quat_rotate_vec_unity(
    quat_xyzw: Tuple[float, float, float, float],
    vec_xyz: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """Rotate 3D vector `(x, y, z)` by Unity quaternion `(x, y, z, w)`."""
    quat_x_val, quat_y_val, quat_z_val, quat_scalar_val = quat_xyzw
    vert_x_val, vert_y_val, vert_z_val = vec_xyz
    cross_x = 2.0 * (quat_y_val * vert_z_val - quat_z_val * vert_y_val)
    cross_y = 2.0 * (quat_z_val * vert_x_val - quat_x_val * vert_z_val)
    cross_z = 2.0 * (quat_x_val * vert_y_val - quat_y_val * vert_x_val)
    return (
        vert_x_val + quat_scalar_val * cross_x + (quat_y_val * cross_z - quat_z_val * cross_y),
        vert_y_val + quat_scalar_val * cross_y + (quat_z_val * cross_x - quat_x_val * cross_z),
        vert_z_val + quat_scalar_val * cross_z + (quat_x_val * cross_y - quat_y_val * cross_x),
    )


def compose_unity_trs(
    parent_trs: Tuple[
        Tuple[float, float, float],
        Tuple[float, float, float, float],
        Tuple[float, float, float],
    ],
    local_trs: Tuple[
        Tuple[float, float, float],
        Tuple[float, float, float, float],
        Tuple[float, float, float],
    ],
) -> Tuple[
    Tuple[float, float, float],
    Tuple[float, float, float, float],
    Tuple[float, float, float],
]:
    """Compose `parent_trs * local_trs` matching Unity's `Transform` hierarchy."""
    par_pos, par_rot, par_scale = parent_trs
    loc_pos, loc_rot, loc_scale = local_trs
    scaled_pos = (
        loc_pos[0] * par_scale[0],
        loc_pos[1] * par_scale[1],
        loc_pos[2] * par_scale[2],
    )
    rot_pos = _quat_rotate_vec_unity(par_rot, scaled_pos)
    return (
        (par_pos[0] + rot_pos[0], par_pos[1] + rot_pos[1], par_pos[2] + rot_pos[2]),
        _quat_mul_unity(par_rot, loc_rot),
        (
            par_scale[0] * loc_scale[0],
            par_scale[1] * loc_scale[1],
            par_scale[2] * loc_scale[2],
        ),
    )


def unity_trs_to_blender_matrix_rows(
    unity_trs: Tuple[
        Tuple[float, float, float],
        Tuple[float, float, float, float],
        Tuple[float, float, float],
    ],
    *,
    is_bone: bool = True,
) -> List[List[float]]:
    """Convert Unity world `(pos, rot, scale)` into a 4x4 Blender matrix (`F4 @ U @ J4` or `F4 @ U @ F4^T`)."""
    pos_u, rot_u, scale_u = unity_trs
    quat_x_val, quat_y_val, quat_z_val, quat_scalar_val = rot_u
    norm_squared = quat_x_val * quat_x_val + quat_y_val * quat_y_val + quat_z_val * quat_z_val + quat_scalar_val * quat_scalar_val
    if norm_squared > 1e-12:
        inv_norm = norm_squared ** -0.5
        quat_x_val *= inv_norm
        quat_y_val *= inv_norm
        quat_z_val *= inv_norm
        quat_scalar_val *= inv_norm
    quat_x_x, quat_y_y, quat_z_z = quat_x_val * quat_x_val, quat_y_val * quat_y_val, quat_z_val * quat_z_val
    quat_x_y, quat_x_z, quat_y_z = quat_x_val * quat_y_val, quat_x_val * quat_z_val, quat_y_val * quat_z_val
    scalar_x_prod, scalar_y_prod, scalar_z_prod = quat_scalar_val * quat_x_val, quat_scalar_val * quat_y_val, quat_scalar_val * quat_z_val
    scale_x_val, scale_y_val, scale_z_val = scale_u

    rot_scaled = [
        [(1.0 - 2.0 * (quat_y_y + quat_z_z)) * scale_x_val, 2.0 * (quat_x_y - scalar_z_prod) * scale_y_val, 2.0 * (quat_x_z + scalar_y_prod) * scale_z_val],
        [2.0 * (quat_x_y + scalar_z_prod) * scale_x_val, (1.0 - 2.0 * (quat_x_x + quat_z_z)) * scale_y_val, 2.0 * (quat_y_z - scalar_x_prod) * scale_z_val],
        [2.0 * (quat_x_z - scalar_y_prod) * scale_x_val, 2.0 * (quat_y_z + scalar_x_prod) * scale_y_val, (1.0 - 2.0 * (quat_x_x + quat_y_y)) * scale_z_val],
    ]
    mat_u = [
        [rot_scaled[0][0], rot_scaled[0][1], rot_scaled[0][2], pos_u[0]],
        [rot_scaled[1][0], rot_scaled[1][1], rot_scaled[1][2], pos_u[1]],
        [rot_scaled[2][0], rot_scaled[2][1], rot_scaled[2][2], pos_u[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]
    f4_mat = [
        [-1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    rhs_mat = (
        [
            [-1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        if is_bone
        else [
            [-1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, -1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )

    def _mul4(left_mat: List[List[float]], right_mat: List[List[float]]) -> List[List[float]]:
        out_mat = [[0.0, 0.0, 0.0, 0.0] for _ in range(4)]
        for row_idx in range(4):
            for col_idx in range(4):
                out_mat[row_idx][col_idx] = sum(
                    left_mat[row_idx][mid_idx] * right_mat[mid_idx][col_idx]
                    for mid_idx in range(4)
                )
        return out_mat

    return _mul4(_mul4(f4_mat, mat_u), rhs_mat)


def extract_transform_mod_overrides(
    mods_list: Sequence[Dict[str, Any]],
    expected_guid: str = "",
) -> Dict[str, Dict[str, Any]]:
    """Collect `m_LocalPosition`/`m_LocalRotation`/`m_LocalScale` overrides keyed by target `fileID`."""
    overrides: Dict[str, Dict[str, Any]] = {}
    exp_low = expected_guid.strip().lower()
    for mod_item in mods_list:
        tgt_guid = str(mod_item.get("target_guid", "") or "").lower()
        if exp_low and tgt_guid and tgt_guid != exp_low:
            continue
        tgt_fid = str(mod_item.get("target_fid", "") or "")
        prop_path = str(mod_item.get("property", "") or "")
        if not tgt_fid or "." not in prop_path:
            continue
        prefix_prop, axis_tok = prop_path.rsplit(".", 1)
        if prefix_prop not in ("m_LocalPosition", "m_LocalRotation", "m_LocalScale"):
            continue
        try:
            float_val = float(str(mod_item.get("value", "") or "").strip())
        except ValueError:
            continue
        bucket = overrides.setdefault(tgt_fid, {})
        bucket.setdefault(prefix_prop, {})[axis_tok] = float_val
    return overrides


def compute_doc_unity_world_transforms(
    doc_data: Dict[str, Any],
    *,
    root_transform: Optional[str] = None,
    base_world: Tuple[
        Tuple[float, float, float],
        Tuple[float, float, float, float],
        Tuple[float, float, float],
    ] = IDENTITY_UNITY_TRS,
    overrides_by_transform: Optional[Dict[str, Dict[str, Any]]] = None,
    treat_root_as_avatar_origin: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Compute avatar-local Unity world transforms for all `Transform` nodes in `doc_data`."""
    transform_map = doc_data.get("transforms", {})
    game_object_map = doc_data.get("gameobjects", {})
    override_map = overrides_by_transform or {}
    memo: Dict[str, Tuple[Any, str, Tuple[float, float, float]]] = {}

    def _effective_local(transform_file_id: str) -> Tuple[
        Tuple[float, float, float],
        Tuple[float, float, float, float],
        Tuple[float, float, float],
    ]:
        info = transform_map[transform_file_id]
        pos_x, pos_y, pos_z = info.get("pos", (0.0, 0.0, 0.0))
        rot_x, rot_y, rot_z, rot_scalar = info.get("rot", (0.0, 0.0, 0.0, 1.0))
        scl_x, scl_y, scl_z = info.get("scale", (1.0, 1.0, 1.0))
        transform_overrides = override_map.get(transform_file_id)
        if transform_overrides:
            pos_override = transform_overrides.get("m_LocalPosition", {})
            pos_x = pos_override.get("x", pos_x)
            pos_y = pos_override.get("y", pos_y)
            pos_z = pos_override.get("z", pos_z)
            rot_override = transform_overrides.get("m_LocalRotation", {})
            rot_x = rot_override.get("x", rot_x)
            rot_y = rot_override.get("y", rot_y)
            rot_z = rot_override.get("z", rot_z)
            rot_scalar = rot_override.get("w", rot_scalar)
            scale_override = transform_overrides.get("m_LocalScale", {})
            scl_x = scale_override.get("x", scl_x)
            scl_y = scale_override.get("y", scl_y)
            scl_z = scale_override.get("z", scl_z)
        return ((pos_x, pos_y, pos_z), (rot_x, rot_y, rot_z, rot_scalar), (scl_x, scl_y, scl_z))

    def _resolve_node(transform_file_id: str, stack_seen: Set[str]) -> Tuple[Any, str, Tuple[float, float, float]]:
        if transform_file_id in memo:
            return memo[transform_file_id]
        if transform_file_id in stack_seen or transform_file_id not in transform_map:
            return (base_world, "", (1.0, 1.0, 1.0))
        stack_seen.add(transform_file_id)
        transform_info = transform_map[transform_file_id]
        game_object_name = str(game_object_map.get(transform_info.get("go_fid", ""), {}).get("name", "") or "")
        loc_trs = _effective_local(transform_file_id)
        loc_scale = loc_trs[2]
        if root_transform and transform_file_id == root_transform:
            eff_loc = (
                ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), loc_scale)
                if treat_root_as_avatar_origin
                else loc_trs
            )
            world_val = compose_unity_trs(base_world, eff_loc)
            res = (world_val, game_object_name, loc_scale)
            memo[transform_file_id] = res
            return res

        father_fid = transform_info.get("father_tr", "0")
        if father_fid == "0" or father_fid not in transform_map:
            par_world, par_path = base_world, ""
        else:
            par_world, par_path, _ = _resolve_node(father_fid, stack_seen)
        cur_path = f"{par_path}/{game_object_name}" if (par_path and game_object_name) else (par_path or game_object_name)
        world_val = compose_unity_trs(par_world, loc_trs)
        res = (world_val, cur_path, loc_scale)
        memo[transform_file_id] = res
        return res

    out_map: Dict[str, Dict[str, Any]] = {}
    for transform_file_id, transform_info in transform_map.items():
        world_trs, node_path, loc_scale = _resolve_node(transform_file_id, set())
        game_object_name = str(game_object_map.get(transform_info.get("go_fid", ""), {}).get("name", "") or "")
        out_map[transform_file_id] = {
            "name": game_object_name,
            "path": node_path,
            "father_tr": transform_info.get("father_tr", "0"),
            "world": world_trs,
            "local_scale": loc_scale,
        }
    return out_map


def is_identity_mat4(mat_val: Any, tol: float = 1e-4) -> bool:
    """Return True when a 4x4 matrix is within `tol` of the identity matrix."""
    for row_idx in range(4):
        for col_idx in range(4):
            target_val = 1.0 if row_idx == col_idx else 0.0
            if abs(float(mat_val[row_idx][col_idx]) - target_val) > tol:
                return False
    return True


def compute_bone_unit_scale_correction(
    fbx_points_by_bone: Dict[str, Tuple[float, float, float]],
    bone_matrices: Dict[str, List[List[float]]],
    fbx_col_norm: float = 1.0,
) -> float:
    """
    Detect FBX cm-to-m unit import scale mismatch between Blender `Armature` matrix scale
    and Unity `bone_matrices` column norm relative to inter-bone spatial span, returning
    the scalar multiplier for Unity target bone 3x3 columns (`1.0` when scale already matches).
    """
    mats_low = {str(key).lower(): val for key, val in bone_matrices.items()}
    fbx_pts: List[Tuple[float, float, float]] = []
    uni_pts: List[Tuple[float, float, float]] = []
    col_norms: List[float] = []
    for bone_name, fbx_point in fbx_points_by_bone.items():
        rows = bone_matrices.get(bone_name) or mats_low.get(bone_name.lower())
        if rows is None:
            continue
        fbx_pts.append(fbx_point)
        uni_pts.append((float(rows[0][3]), float(rows[1][3]), float(rows[2][3])))
        col_norm = (rows[0][0] ** 2 + rows[1][0] ** 2 + rows[2][0] ** 2) ** 0.5
        if col_norm > 1e-6:
            col_norms.append(col_norm)
    if len(fbx_pts) < 2 or not col_norms:
        return 1.0

    def _mean_radius(pts_list: List[Tuple[float, float, float]]) -> float:
        cnt = float(len(pts_list))
        cen_x = sum(point_item[0] for point_item in pts_list) / cnt
        cen_y = sum(point_item[1] for point_item in pts_list) / cnt
        cen_z = sum(point_item[2] for point_item in pts_list) / cnt
        return sum(
            (
                (point_item[0] - cen_x) ** 2
                + (point_item[1] - cen_y) ** 2
                + (point_item[2] - cen_z) ** 2
            )
            ** 0.5
            for point_item in pts_list
        )

    radius_fbx = _mean_radius(fbx_pts)
    rad_u = _mean_radius(uni_pts)
    if radius_fbx <= 1e-4 or rad_u <= 1e-4:
        return 1.0
    spatial_scale = rad_u / radius_fbx
    col_norms.sort()
    med_col = col_norms[len(col_norms) // 2]
    if med_col <= 1e-6:
        return 1.0
    eff_fbx_scale = float(fbx_col_norm) if float(fbx_col_norm) > 1e-6 else 1.0
    expected_col = spatial_scale * eff_fbx_scale
    ratio = med_col / expected_col
    if abs(ratio - 1.0) > 0.5:
        return expected_col / med_col
    return 1.0


_MAT_MOD_PROP_RE = re.compile(r"^m_Materials\.Array\.data\[(\d+)\]$")


def extract_renderer_mod_overrides(
    mods_list: Sequence[Dict[str, Any]],
    expected_guid: str = "",
) -> Dict[str, Any]:
    """
    Collect PrefabInstance `m_Materials.Array.data[N]`, `m_Enabled`, and `m_IsActive`
    overrides matching `expected_guid` keyed by target component/GameObject `fileID`.
    """
    materials: Dict[str, Dict[int, str]] = {}
    enabled_map: Dict[str, bool] = {}
    active_map: Dict[str, bool] = {}
    exp_low = expected_guid.strip().lower()
    for mod_item in mods_list:
        tgt_guid = str(mod_item.get("target_guid", "") or "").lower()
        if exp_low and tgt_guid and tgt_guid != exp_low:
            continue
        tgt_fid = str(mod_item.get("target_fid", "") or "")
        prop_path = str(mod_item.get("property", "") or "")
        if not tgt_fid or not prop_path:
            continue
        mat_match = _MAT_MOD_PROP_RE.match(prop_path)
        if mat_match:
            ref_guid = str(mod_item.get("ref_guid", "") or "").lower()
            if ref_guid:
                materials.setdefault(tgt_fid, {})[int(mat_match.group(1))] = ref_guid
        elif prop_path == "m_Enabled":
            raw_val = str(mod_item.get("value", "1") or "1").strip()
            enabled_map[tgt_fid] = raw_val != "0"
        elif prop_path == "m_IsActive":
            raw_val = str(mod_item.get("value", "1") or "1").strip()
            active_map[tgt_fid] = raw_val != "0"
        elif prop_path == "m_TagString" and str(mod_item.get("value", "") or "").strip() == "EditorOnly":
            active_map[tgt_fid] = False
    return {"materials": materials, "enabled": enabled_map, "active": active_map}


def resolve_overridden_renderer_mats(
    rend_info: Dict[str, Any],
    renderer_overrides: Optional[Dict[str, Any]],
) -> List[str]:
    """Apply PrefabInstance `m_Materials.Array.data[N]` overrides onto `rend_info['mat_guids']`."""
    eff_mats = [str(gid or "").lower() for gid in (rend_info.get("mat_guids") or ())]
    if not renderer_overrides:
        return eff_mats
    comp_fid = str(rend_info.get("comp_fid", "") or "")
    slot_map = (renderer_overrides.get("materials") or {}).get(comp_fid)
    if not slot_map:
        return eff_mats
    max_slot = max(slot_map.keys())
    while len(eff_mats) <= max_slot:
        eff_mats.append("")
    for slot_idx, new_guid in slot_map.items():
        if 0 <= int(slot_idx) < len(eff_mats) and new_guid:
            eff_mats[int(slot_idx)] = str(new_guid).lower()
    return eff_mats


def stamp_unity_mats_on_blender_objects(
    mesh_objs: Sequence[Any],
    mesh_mats_map: Optional[Dict[str, Sequence[Dict[str, Any]]]],
) -> int:
    """Attach compact per-mesh Unity `.mat` metadata JSON to imported Blender mesh objects."""
    if not mesh_objs or not mesh_mats_map:
        return 0
    mats_lower = {str(key).strip().lower(): val for key, val in mesh_mats_map.items() if key}
    stamped = 0
    for mesh_obj in mesh_objs:
        if getattr(mesh_obj, "type", "") != "MESH":
            continue
        base_name = re.sub(r"\.\d{3}$", "", str(getattr(mesh_obj, "name", "") or "")).strip()
        mat_list = mesh_mats_map.get(base_name) or mats_lower.get(base_name.lower())
        if not mat_list:
            continue
        compact_list = [
            {
                "name": str(item.get("name", "") or ""),
                "mat_path": str(item.get("mat_path", "") or ""),
                "mat_guid": str(item.get("mat_guid", "") or ""),
            }
            for item in mat_list
            if isinstance(item, dict)
        ]
        if not compact_list:
            continue
        try:
            mesh_obj["vrc2gtav_unity_mats_json"] = json.dumps(compact_list, ensure_ascii=False)
            stamped += 1
        except (TypeError, AttributeError):
            pass
    return stamped


def apply_unity_textures_to_blender_meshes(
    bpy_mod: Any,
    mesh_objs: Sequence[Any],
    mesh_mats_map: Optional[Dict[str, Sequence[Dict[str, Any]]]],
) -> None:
    """Attach primary Unity `_MainTex` textures onto imported Blender mesh materials."""
    if not mesh_objs or not mesh_mats_map:
        return
    for mesh_obj in mesh_objs:
        clean_name = re.sub(r"\.\d{3}$", "", str(getattr(mesh_obj, "name", "") or "")).strip()
        mat_list = mesh_mats_map.get(clean_name)
        if not mat_list:
            continue
        for slot_idx, mat_info in enumerate(mat_list):
            if slot_idx >= len(mesh_obj.data.materials):
                break
            blender_mat = mesh_obj.data.materials[slot_idx]
            if blender_mat is None:
                continue
            tex_envs = mat_info.get("tex_envs", {})
            main_entry = tex_envs.get("_MainTex") or tex_envs.get("_BaseMap") or tex_envs.get("_BaseColorMap")
            tex_path = main_entry.get("path") if isinstance(main_entry, dict) else None
            if not tex_path or not os.path.isfile(tex_path):
                continue
            blender_mat.use_nodes = True
            node_tree = blender_mat.node_tree
            if node_tree is None:
                continue
            bsdf = next((node_item for node_item in node_tree.nodes if node_item.type == "BSDF_PRINCIPLED"), None)
            if bsdf is None:
                continue
            tex_node = node_tree.nodes.new("ShaderNodeTexImage")
            try:
                tex_node.image = bpy_mod.data.images.load(tex_path, check_existing=True)
            except Exception:
                continue
            node_tree.links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])


def _read_fbx_meta_mesh_fids(fbx_path: Path) -> Dict[str, str]:
    """Parse fileID->mesh name mappings from a Unity `.fbx.meta` file when present."""
    fid_map: Dict[str, str] = {}
    meta_path = Path(str(fbx_path) + ".meta")
    if not meta_path.is_file():
        return fid_map
    try:
        raw_text = meta_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return fid_map
    rec_match = re.search(
        r"fileIDToRecycleName:(.*?)(?=^\s{2}[A-Za-z_]|^\S|\Z)",
        raw_text,
        re.DOTALL | re.MULTILINE,
    )
    if rec_match:
        for row_match in re.finditer(r"^\s*(-?\d+):\s*(.+?)\s*$", rec_match.group(1), re.MULTILINE):
            fid_val = row_match.group(1).strip()
            mesh_val = row_match.group(2).strip().strip("\"'")
            if fid_val and mesh_val:
                fid_map[fid_val] = mesh_val
    tab_match = re.search(
        r"internalIDToNameTable:(.*?)(?=^\s{2}[A-Za-z_]|^\S|\Z)",
        raw_text,
        re.DOTALL | re.MULTILINE,
    )
    if tab_match and "internalIDToNameTable: []" not in tab_match.group(0):
        for entry_match in re.finditer(
            r"43:\s*(-?\d+)\s*[\r\n]+\s*second:\s*(.+?)\s*$",
            tab_match.group(1),
            re.MULTILINE,
        ):
            fid_val = entry_match.group(1).strip()
            mesh_val = entry_match.group(2).strip().strip("\"'")
            if fid_val and mesh_val:
                fid_map[fid_val] = mesh_val
    return fid_map






