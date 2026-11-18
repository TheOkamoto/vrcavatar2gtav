#!/usr/bin/env python3
"""
modular_avatar_helper.py
========================
Native Python + Blender Modular Avatar (NDMF) bake engine for vrc2gtav.

Parses Modular Avatar components from Unity scenes (`.unity`) and nested outfit
prefabs (`.prefab`), supporting arbitrary dresses, coats, ribbons, hairs, and
accessories using:
  - ModularAvatarMergeArmature (bone merge + prefix/suffix + custom child chains)
  - ModularAvatarBoneProxy (HumanBodyBones + subPath + attachmentMode)
  - ModularAvatarScaleAdjuster (local bone scale baking)
  - ModularAvatarMeshSettings (bounds/anchor tracking)
  - ModularAvatarObjectToggle & Activator (enable/disable object filtering)
  - ModularAvatarReplaceObject (replacing base avatar parts cleanly)
  - ModularAvatarShapeChanger (applying body/shrink/heels shape weights)
  - ModularAvatarBlendshapeSync (propagating synchronized blendshapes onto outfits)
  - Embedded VRCPhysBone chains & lilToon/Standard material textures on outfits

Pure standard library at module import time (`bpy` imported lazily inside Blender
bake routines), so CLI tools, Unity scanners, and unit tests run anywhere.
"""

from __future__ import annotations

from collections import deque
import os
from pathlib import Path
import re
import sys
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


def _extract_inline_ref(field_snippet: str) -> Tuple[str, str]:
    """Extract `(fileID, guid)` from a Unity object reference `{fileID: ..., guid: ...}`."""
    fid_m = re.search(r"fileID:\s*(-?\d+)", field_snippet)
    guid_m = re.search(r"guid:\s*([0-9a-fA-F]{32})", field_snippet)
    return (fid_m.group(1) if fid_m else "0", guid_m.group(1).lower() if guid_m else "")


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
    }
    if not resolved_path.is_file():
        return empty_doc

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
    go_to_tr: Dict[str, str] = {}
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

    for block in blocks[1:]:
        nl_idx = block.find("\n")
        if nl_idx <= 0:
            continue
        header_line = block[:nl_idx].strip()
        is_stripped = header_line.endswith("stripped")
        if " &" not in header_line:
            continue
        cls_part, fid_part = header_line.split(" &", 1)
        class_id = cls_part.strip()
        file_id = fid_part.split()[0].strip()

        if class_id == "1":
            name_m = re.search(r"^\s*m_Name:[ \t]*(.+)$", block, re.MULTILINE)
            act_m = re.search(r"^\s*m_IsActive:[ \t]*(\d+)", block, re.MULTILINE)
            pi_m = re.search(r"m_PrefabInstance:\s*\{fileID:\s*(-?\d+)", block)
            gameobjects[file_id] = {
                "name": _decode_scalar(name_m.group(1)) if name_m else "",
                "active": (int(act_m.group(1)) != 0) if act_m else True,
                "pi_fid": pi_m.group(1) if pi_m else "0",
            }
        elif class_id == "4":
            if is_stripped:
                continue
            go_m = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", block)
            father_m = re.search(r"m_Father:\s*\{fileID:\s*(-?\d+)", block)
            child_fids: List[str] = []
            if "m_Children:" in block:
                child_chunk = block.split("m_Children:", 1)[1].split("m_Father:", 1)[0]
                child_fids = re.findall(r"-\s*\{fileID:\s*(-?\d+)", child_chunk)
            if go_m:
                go_id = go_m.group(1)
                transforms[file_id] = {
                    "go_fid": go_id,
                    "father_tr": father_m.group(1) if father_m else "0",
                    "children": child_fids,
                }
                go_to_tr[go_id] = file_id
        elif class_id in ("23", "137"):
            go_m = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", block)
            en_m = re.search(r"^\s*m_Enabled:[ \t]*(\d+)", block, re.MULTILINE)
            mesh_m = re.search(r"m_Mesh:\s*\{([^\}]*)\}", block)
            mat_sec = re.search(
                r"m_Materials:(.*?)(?=^\s{2}[a-zA-Z_][a-zA-Z0-9_]*:|\Z)",
                block,
                re.DOTALL | re.MULTILINE,
            )
            mat_guids = (
                [gid.lower() for gid in re.findall(r"guid:\s*([0-9a-fA-F]{32})", mat_sec.group(1))]
                if mat_sec
                else []
            )
            mesh_fid, mesh_guid = _extract_inline_ref(mesh_m.group(1)) if mesh_m else ("0", "")
            if go_m:
                renderers[go_m.group(1)] = {
                    "go_fid": go_m.group(1),
                    "class_id": class_id,
                    "enabled": (int(en_m.group(1)) != 0) if en_m else True,
                    "mesh_fid": mesh_fid,
                    "mesh_guid": mesh_guid,
                    "mat_guids": mat_guids,
                }
        elif class_id == "33":
            go_m = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", block)
            mesh_m = re.search(r"m_Mesh:\s*\{([^\}]*)\}", block)
            if go_m and mesh_m:
                _mfid, mguid = _extract_inline_ref(mesh_m.group(1))
                if mguid:
                    mesh_filters[go_m.group(1)] = mguid
        elif class_id == "1001":
            par_m = re.search(r"m_TransformParent:\s*\{fileID:\s*(-?\d+)", block)
            src_m = re.search(
                r"m_SourcePrefab:\s*\{fileID:\s*-?\d+,\s*guid:\s*([0-9a-fA-F]{32})",
                block,
            )
            src_guid = src_m.group(1).lower() if src_m else ""
            pi_name = ""
            root_name_tid = ""
            active_by_tid: Dict[str, bool] = {}
            mods: List[Dict[str, str]] = []
            for mod_m in re.finditer(
                r"-\s*target:\s*\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-fA-F]{32}))?[^\}]*\}[ \t]*\r?\n"
                r"[ \t]*propertyPath:[ \t]*([^\r\n]+)\r?\n"
                r"[ \t]*value:[ \t]*([^\r\n]*)\r?\n"
                r"[ \t]*objectReference:[ \t]*\{([^\}]*)\}",
                block,
            ):
                tgt_fid = mod_m.group(1)
                tgt_guid = (mod_m.group(2) or "").lower()
                prop_path = mod_m.group(3).strip()
                raw_val = _decode_scalar(mod_m.group(4))
                _ref_fid, ref_guid = _extract_inline_ref(mod_m.group(5))
                if prop_path == "m_Name" and raw_val:
                    is_src = bool(src_guid and tgt_guid == src_guid)
                    if not pi_name or (is_src and not root_name_tid):
                        pi_name = raw_val
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
                        "ref_guid": ref_guid,
                    }
                )
            pi_active = True
            if root_name_tid and root_name_tid in active_by_tid:
                pi_active = active_by_tid[root_name_tid]
            elif not root_name_tid and "100000" in active_by_tid:
                pi_active = active_by_tid["100000"]

            prefab_instances[file_id] = {
                "parent_tr": par_m.group(1) if par_m else "0",
                "source_guid": src_guid,
                "name": pi_name,
                "active": pi_active,
                "mods": mods,
            }
        elif class_id == "114":
            script_m = re.search(r"m_Script:\s*\{[^\}]*guid:\s*([0-9a-fA-F]{32})", block)
            go_m = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", block)
            en_m = re.search(r"^\s*m_Enabled:[ \t]*(\d+)", block, re.MULTILINE)
            if not (script_m and go_m):
                continue
            script_guid = script_m.group(1).lower()
            go_fid = go_m.group(1)
            is_enabled = (int(en_m.group(1)) != 0) if en_m else True

            if script_guid == MA_MERGE_ARMATURE_GUID:
                ref_m = re.search(r"mergeTarget:\s*\n(?:[ \t]+[^\n]*\n)*?[ \t]*referencePath:[ \t]*([^\r\n]*)", block)
                pref_m = re.search(r"^\s*prefix:[ \t]*([^\r\n]*)", block, re.MULTILINE)
                suff_m = re.search(r"^\s*suffix:[ \t]*([^\r\n]*)", block, re.MULTILINE)
                mangle_m = re.search(r"^\s*mangleNames:[ \t]*(\d+)", block, re.MULTILINE)
                merge_armatures.append(
                    {
                        "go_fid": go_fid,
                        "enabled": is_enabled,
                        "merge_target_path": _decode_scalar(ref_m.group(1)) if ref_m else "",
                        "prefix": _decode_scalar(pref_m.group(1)) if pref_m else "",
                        "suffix": _decode_scalar(suff_m.group(1)) if suff_m else "",
                        "mangle_names": (int(mangle_m.group(1)) != 0) if mangle_m else True,
                    }
                )
            elif script_guid == MA_BONE_PROXY_GUID:
                bone_ref_m = re.search(r"boneReference:[ \t]*(-?\d+)", block)
                sub_path_m = re.search(r"subPath:[ \t]*([^\r\n]*)", block)
                att_m = re.search(r"attachmentMode:[ \t]*(-?\d+)", block)
                scale_m = re.search(r"matchScale:[ \t]*(\d+)", block)
                bone_proxies.append(
                    {
                        "go_fid": go_fid,
                        "enabled": is_enabled,
                        "bone_reference": int(bone_ref_m.group(1)) if bone_ref_m else -1,
                        "sub_path": _decode_scalar(sub_path_m.group(1)) if sub_path_m else "",
                        "attachment_mode": int(att_m.group(1)) if att_m else 1,
                        "match_scale": (int(scale_m.group(1)) != 0) if scale_m else False,
                    }
                )
            elif script_guid == MA_SCALE_ADJUSTER_GUID:
                vec_m = re.search(
                    r"m_Scale:\s*\{x:\s*([^,]+),\s*y:\s*([^,]+),\s*z:\s*([^\}]+)\}",
                    block,
                )
                if vec_m and is_enabled:
                    try:
                        scale_xyz = (
                            float(vec_m.group(1)),
                            float(vec_m.group(2)),
                            float(vec_m.group(3)),
                        )
                    except ValueError:
                        scale_xyz = (1.0, 1.0, 1.0)
                    scale_adjusters.append(
                        {"go_fid": go_fid, "enabled": is_enabled, "scale": scale_xyz}
                    )
            elif script_guid == MA_BLENDSHAPE_SYNC_GUID and is_enabled:
                bindings: List[Dict[str, str]] = []
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
                    if src_shape:
                        bindings.append(
                            {
                                "reference_mesh_path": ref_mesh,
                                "source_shape": src_shape,
                                "local_shape": local_shape,
                            }
                        )
                if bindings:
                    blendshape_syncs.append({"go_fid": go_fid, "bindings": bindings})
            elif script_guid == MA_OBJECT_TOGGLE_GUID and is_enabled:
                inv_m = re.search(r"^\s*m_inverted:[ \t]*(\d+)", block, re.MULTILINE)
                is_inverted = (int(inv_m.group(1)) != 0) if inv_m else False
                if not is_inverted:
                    toggles: List[Dict[str, Any]] = []
                    for tog_m in re.finditer(
                        r"-\s*Object:[ \t]*\r?\n"
                        r"(?:[ \t]+[^\n]*\n)*?"
                        r"[ \t]*referencePath:[ \t]*([^\r\n]*)\r?\n"
                        r"(?:[ \t]*targetObject:[ \t]*[^\r\n]*\r?\n)?"
                        r"[ \t]*Active:[ \t]*(\d+)",
                        block,
                    ):
                        toggles.append(
                            {
                                "reference_path": _decode_scalar(tog_m.group(1)),
                                "active": int(tog_m.group(2)) != 0,
                            }
                        )
                    if toggles:
                        object_toggles.append({"go_fid": go_fid, "toggles": toggles})
            elif script_guid == MA_SHAPE_CHANGER_GUID and is_enabled:
                inv_m = re.search(r"^\s*m_inverted:[ \t]*(\d+)", block, re.MULTILINE)
                is_inverted = (int(inv_m.group(1)) != 0) if inv_m else False
                if not is_inverted:
                    shapes: List[Dict[str, Any]] = []
                    for shp_m in re.finditer(
                        r"-\s*Object:[ \t]*\r?\n"
                        r"(?:[ \t]+[^\n]*\n)*?"
                        r"[ \t]*referencePath:[ \t]*([^\r\n]*)\r?\n"
                        r"(?:[ \t]*targetObject:[ \t]*[^\r\n]*\r?\n)?"
                        r"[ \t]*ShapeName:[ \t]*([^\r\n]*)\r?\n"
                        r"[ \t]*ChangeType:[ \t]*(-?\d+)\r?\n"
                        r"[ \t]*Value:[ \t]*([^\r\n]+)",
                        block,
                    ):
                        shape_name = _decode_scalar(shp_m.group(2))
                        change_type = int(shp_m.group(3))
                        try:
                            raw_num = float(shp_m.group(4).strip())
                        except ValueError:
                            continue
                        weight_norm = 1.0 if change_type == 0 else (raw_num / 100.0)
                        if shape_name:
                            shapes.append(
                                {
                                    "reference_path": _decode_scalar(shp_m.group(1)),
                                    "shape_name": shape_name,
                                    "change_type": change_type,
                                    "weight": weight_norm,
                                }
                            )
                    if shapes:
                        shape_changers.append({"go_fid": go_fid, "shapes": shapes})
            elif script_guid == MA_REPLACE_OBJECT_GUID and is_enabled:
                ref_m = re.search(
                    r"targetObject:\s*\n(?:[ \t]+[^\n]*\n)*?[ \t]*referencePath:[ \t]*([^\r\n]*)",
                    block,
                )
                if ref_m and ref_m.group(1).strip():
                    replace_objects.append(
                        {"go_fid": go_fid, "target_path": _decode_scalar(ref_m.group(1))}
                    )
            elif script_guid == MA_MESH_SETTINGS_GUID and is_enabled:
                root_m = re.search(
                    r"RootBone:\s*\n(?:[ \t]+[^\n]*\n)*?[ \t]*referencePath:[ \t]*([^\r\n]*)",
                    block,
                )
                mesh_settings.append(
                    {
                        "go_fid": go_fid,
                        "root_bone_path": _decode_scalar(root_m.group(1)) if root_m else "",
                    }
                )
            elif script_guid == MA_ACTIVATOR_GUID:
                activators.append({"go_fid": go_fid, "enabled": is_enabled})
            elif script_guid == VRC_PHYSBONE_GUID and is_enabled:
                root_m = re.search(r"rootTransform:\s*\{fileID:\s*(-?\d+)", block)
                physbones.append(
                    {
                        "go_fid": go_fid,
                        "root_tr": root_m.group(1) if root_m else "0",
                    }
                )

    return {
        "gameobjects": gameobjects,
        "transforms": transforms,
        "go_to_tr": go_to_tr,
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
    }


_MA_GUID_CACHE: Dict[str, Optional[Path]] = {}


def _is_builtin_unity_guid(guid_str: str) -> bool:
    """Return True for built-in Unity internal asset GUIDs that have no .meta on disk."""
    clean = guid_str.strip().lower()
    return not clean or clean.startswith(("0000000000000000", "f000000000000000"))


def _collect_guid_paths_for_ma(
    needed_guids: Set[str],
    anchor_path: Path,
    assets_root: Optional[Path],
    *,
    name_hints: Sequence[str] = (),
    budget_sec: float = 2.0,
) -> Dict[str, Path]:
    """Resolve asset GUIDs quickly via prioritized bounded search + shared in-memory cache."""
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

    hint_words = {
        tok.lower()
        for raw_h in [anchor_path.stem] + list(name_hints)
        for tok in re.split(r"[^A-Za-z0-9]+", str(raw_h or ""))
        if len(tok) >= 3
    }

    search_roots: List[Path] = []
    if anchor_path:
        anchor_dir = anchor_path if anchor_path.is_dir() else anchor_path.parent
        cur_dir = anchor_dir
        for _step in range(3):
            if cur_dir.is_dir() and cur_dir not in search_roots:
                search_roots.append(cur_dir)
            parent_dir = cur_dir.parent
            if parent_dir == cur_dir or (assets_root and cur_dir.resolve() == assets_root.resolve()):
                break
            cur_dir = parent_dir

    if assets_root and assets_root.is_dir():
        try:
            top_assets_dirs = [
                sub_entry
                for sub_entry in sorted(assets_root.iterdir())
                if sub_entry.is_dir()
                and sub_entry.name.lower() not in _SKIP_SCAN_DIRS
                and not sub_entry.name.startswith(".")
            ]
        except OSError:
            top_assets_dirs = []
        matching_top = [
            sub_dir
            for sub_dir in top_assets_dirs
            if any(word in sub_dir.name.lower() for word in hint_words)
        ]
        for sub_dir in matching_top:
            if sub_dir not in search_roots:
                search_roots.append(sub_dir)
        if unity_scene_helper is not None and hasattr(unity_scene_helper, "_priority_search_dirs"):
            for cand_dir in unity_scene_helper._priority_search_dirs(
                anchor_path, assets_root, [anchor_path.stem] + list(hint_words)
            ):
                if cand_dir.is_dir() and cand_dir not in search_roots:
                    search_roots.append(cand_dir)
        elif assets_root not in search_roots:
            search_roots.append(assets_root)

    import time as time_mod
    deadline = time_mod.monotonic() + max(0.2, budget_sec)
    visited_dirs: Set[Path] = set()
    for root_dir in search_roots:
        if not remaining or time_mod.monotonic() > deadline:
            break
        resolved_root = root_dir.resolve()
        if resolved_root in visited_dirs:
            continue
        visited_dirs.add(resolved_root)
        for cur_root, dir_names, file_names in os.walk(resolved_root):
            if time_mod.monotonic() > deadline:
                dir_names[:] = []
                break
            dir_names[:] = [
                sub_dir
                for sub_dir in dir_names
                if sub_dir.lower() not in _SKIP_SCAN_DIRS and not sub_dir.startswith(".")
            ]
            for file_name in file_names:
                low_name = file_name.lower()
                if not low_name.endswith((".prefab.meta", ".fbx.meta", ".mat.meta")):
                    continue
                meta_file = os.path.join(cur_root, file_name)
                try:
                    with open(meta_file, "r", encoding="utf-8", errors="ignore") as meta_handle:
                        for line_idx, line_text in enumerate(meta_handle):
                            if line_text.startswith("guid:"):
                                found_guid = line_text.split(":", 1)[1].strip().lower()
                                if found_guid:
                                    asset_path = Path(meta_file[:-5])
                                    if asset_path.is_file():
                                        _MA_GUID_CACHE.setdefault(found_guid, asset_path)
                                        if found_guid in remaining:
                                            resolved[found_guid] = asset_path
                                            remaining.discard(found_guid)
                                break
                            if line_idx > 6:
                                break
                except OSError:
                    continue
            if not remaining:
                break

    if time_mod.monotonic() <= deadline:
        for missing_guid in remaining:
            _MA_GUID_CACHE[missing_guid] = None
    return resolved


def _is_go_active_in_doc(doc_data: Dict[str, Any], go_fid: str) -> bool:
    """Walk up Transforms in `doc_data` to confirm the GameObject and ancestors are active."""
    visited: Set[str] = set()
    cur_go = go_fid
    go_map = doc_data["gameobjects"]
    tr_map = doc_data["transforms"]
    go_to_tr = doc_data["go_to_tr"]
    cur_tr = go_to_tr.get(cur_go, "")

    if cur_go in go_map and not go_map[cur_go].get("active", True):
        return False
    while cur_tr and cur_tr not in visited:
        visited.add(cur_tr)
        tr_info = tr_map.get(cur_tr)
        if tr_info is None:
            break
        node_go = tr_info.get("go_fid", "")
        if node_go in go_map and not go_map[node_go].get("active", True):
            return False
        parent_tr = tr_info.get("father_tr", "0")
        if parent_tr == "0":
            break
        cur_tr = parent_tr
    return True


def build_modular_avatar_bake_plan(
    scene_or_prefab_path: Union[str, Path],
    avatar_name: Optional[str] = None,
    *,
    assets_root: Optional[Union[str, Path]] = None,
    character_hints: Sequence[str] = (),
    resolve_materials: bool = False,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> Dict[str, Any]:
    """
    Build a complete Modular Avatar (NDMF) bake plan for a selected avatar in a Unity
    scene or prefab, including all active dresses/accessories using MA components.
    """
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="ma_plan")
    src_path = Path(scene_or_prefab_path)
    empty_plan: Dict[str, Any] = {
        "loaded": False,
        "scene_path": str(src_path),
        "avatar_name": avatar_name or "",
        "armature_merges": [],
        "bone_proxies": [],
        "scale_adjusters": [],
        "blendshape_syncs": [],
        "shape_changer_weights": {},
        "object_toggles": {},
        "disabled_meshes": [],
        "extra_fbx_paths": [],
        "base_fbx_paths": [],
        "mesh_materials": {},
        "active_meshes": [],
        "outfit_roots": [],
    }
    if not src_path.is_file():
        return empty_plan

    resolved_assets: Optional[Path] = Path(assets_root) if assets_root else None
    if resolved_assets is None:
        for parent_dir in src_path.parents:
            if parent_dir.name.lower() == "assets":
                resolved_assets = parent_dir
                break

    root_doc = parse_unity_yaml_with_ma(src_path)
    gameobjects = root_doc["gameobjects"]
    transforms = root_doc["transforms"]
    go_to_tr = root_doc["go_to_tr"]
    prefab_instances = root_doc["prefab_instances"]

    # Locate target avatar root (Transform or root PrefabInstance)
    target_tr: Optional[str] = None
    target_pi: Optional[str] = None
    resolved_avatar_name = avatar_name or ""
    norm_target = (avatar_name or "").strip().lower()
    hint_tokens = [tok.strip().lower() for tok in character_hints if tok]

    best_score = -1
    for tr_fid, tr_info in transforms.items():
        if tr_info.get("father_tr", "0") != "0" and norm_target:
            # Allow matching direct named transform even when nested
            pass
        go_info = gameobjects.get(tr_info.get("go_fid", ""), {})
        go_name = str(go_info.get("name", "") or "").strip()
        if not go_name:
            continue
        low_name = go_name.lower()
        score = -1
        if norm_target and low_name == norm_target:
            score = 100
        elif norm_target and norm_target in low_name:
            score = 60
        elif not norm_target and any(tok in low_name for tok in hint_tokens):
            score = 40
        elif not norm_target and tr_info.get("father_tr", "0") == "0":
            score = 15
        if score >= 0:
            active_bonus = 5 if go_info.get("active", True) else 0
            if score + active_bonus > best_score:
                best_score = score + active_bonus
                target_tr = tr_fid
                target_pi = None
                resolved_avatar_name = go_name

    if target_tr is None:
        for pi_fid, pi_info in prefab_instances.items():
            if pi_info.get("parent_tr", "0") != "0" and norm_target:
                continue
            pi_name = str(pi_info.get("name", "") or "").strip()
            low_name = pi_name.lower()
            score = -1
            if norm_target and low_name == norm_target:
                score = 95
            elif norm_target and norm_target in low_name:
                score = 55
            elif not norm_target and pi_name:
                score = 20
            if score > best_score:
                best_score = score
                target_pi = pi_fid
                resolved_avatar_name = pi_name

    # Collect subtree transforms and path strings relative to avatar root
    subtree_trs: Set[str] = set()
    rel_path_by_go: Dict[str, str] = {}
    if target_tr is not None:
        bfs_queue = deque([(target_tr, "")])
        while bfs_queue:
            cur_tr, cur_rel = bfs_queue.popleft()
            if cur_tr in subtree_trs:
                continue
            subtree_trs.add(cur_tr)
            tr_info = transforms.get(cur_tr)
            if not tr_info:
                continue
            go_fid = tr_info.get("go_fid", "")
            if go_fid:
                rel_path_by_go[go_fid] = cur_rel
            for child_tr in tr_info.get("children", []):
                child_go = transforms.get(child_tr, {}).get("go_fid", "")
                child_name = gameobjects.get(child_go, {}).get("name", "")
                next_rel = f"{cur_rel}/{child_name}".lstrip("/") if child_name else cur_rel
                bfs_queue.append((child_tr, next_rel))

    def _is_go_in_avatar_subtree(go_fid: str) -> bool:
        if target_tr is None and target_pi is None:
            return False
        if src_path.suffix.lower() == ".prefab":
            return True
        if target_tr is not None:
            tr_id = go_to_tr.get(go_fid)
            return tr_id in subtree_trs if tr_id else False
        return False

    # Collect active child PrefabInstances (dresses, hairs, accessories attached inside avatar)
    child_pis: List[Tuple[str, Dict[str, Any]]] = []
    if target_pi is not None and target_pi in prefab_instances:
        child_pis.append((target_pi, prefab_instances[target_pi]))
    else:
        for pi_fid, pi_info in prefab_instances.items():
            if not pi_info.get("active", True):
                continue
            parent_tr = pi_info.get("parent_tr", "0")
            if src_path.suffix.lower() == ".prefab" or parent_tr in subtree_trs:
                child_pis.append((pi_fid, pi_info))

    # Gather GUIDs for source prefabs, meshes, and materials
    needed_guids: Set[str] = set()
    for _pi_fid, pi_info in child_pis:
        if pi_info.get("source_guid"):
            needed_guids.add(pi_info["source_guid"])
    for go_fid, rend_info in root_doc["renderers"].items():
        if not _is_go_in_avatar_subtree(go_fid):
            continue
        if rend_info.get("mesh_guid"):
            needed_guids.add(rend_info["mesh_guid"])
        needed_guids.update(rend_info.get("mat_guids", []))
    for go_fid, mesh_guid in root_doc["mesh_filters"].items():
        if _is_go_in_avatar_subtree(go_fid) and mesh_guid:
            needed_guids.add(mesh_guid)

    pi_name_hints = [
        str(pi_info.get("name", "") or "")
        for _pi_fid, pi_info in child_pis
        if pi_info.get("name")
    ]
    if resolved_avatar_name:
        pi_name_hints.append(resolved_avatar_name)
    guid_map = _collect_guid_paths_for_ma(
        needed_guids,
        src_path,
        resolved_assets,
        name_hints=pi_name_hints + list(character_hints),
    )

    armature_merges: List[Dict[str, Any]] = []
    bone_proxies: List[Dict[str, Any]] = []
    scale_adjusters: List[Dict[str, Any]] = []
    blendshape_syncs: List[Dict[str, Any]] = []
    shape_changer_weights: Dict[str, Dict[str, float]] = {}
    object_toggles: Dict[str, bool] = {}
    disabled_meshes: Set[str] = set()
    extra_fbx_paths: List[str] = []
    base_fbx_paths: List[str] = []
    mesh_materials: Dict[str, List[Dict[str, Any]]] = {}
    active_meshes: List[str] = []
    outfit_roots: List[str] = []
    seen_fbx_strs: Set[str] = set()

    def _register_fbx_path(cand_path: Optional[Path], *, is_outfit: bool) -> None:
        if cand_path is None or not cand_path.is_file():
            return
        if cand_path.suffix.lower() not in (".fbx", ".dae", ".obj"):
            return
        path_str = str(cand_path)
        if path_str in seen_fbx_strs:
            return
        seen_fbx_strs.add(path_str)
        if is_outfit:
            extra_fbx_paths.append(path_str)
        else:
            base_fbx_paths.append(path_str)

    def _resolve_material_dicts(mat_guids: Sequence[str], anchor_file: Path) -> List[Dict[str, Any]]:
        mat_list: List[Dict[str, Any]] = []
        if not resolve_materials or unity_hair_helper is None:
            return mat_list
        mat_map = _collect_guid_paths_for_ma(set(mat_guids), anchor_file, resolved_assets)
        for mat_guid in mat_guids:
            mat_path = mat_map.get(mat_guid)
            if mat_path and mat_path.is_file():
                try:
                    mat_info = unity_hair_helper.parse_unity_material(mat_path, resolved_assets)
                    mat_info["mat_path"] = str(mat_path)
                    mat_list.append(mat_info)
                except Exception as exc:
                    active_logger.debug(f"Material parse skip {mat_path}: {exc}")
        return mat_list

    def _ingest_doc_ma_components(
        doc_data: Dict[str, Any],
        doc_path: Path,
        *,
        filter_subtree: bool,
        is_outfit_prefab: bool,
        root_override_name: str = "",
    ) -> None:
        doc_gos = doc_data["gameobjects"]
        doc_renderers = doc_data["renderers"]
        doc_filters = doc_data["mesh_filters"]
        doc_extra_guids: Set[str] = set()
        local_fbx_paths: List[str] = []
        local_mesh_names: List[str] = []

        for go_fid, rend_info in doc_renderers.items():
            if filter_subtree and not _is_go_in_avatar_subtree(go_fid):
                continue
            go_info = doc_gos.get(go_fid, {})
            go_name = str(go_info.get("name", "") or "").strip()
            is_act = _is_go_active_in_doc(doc_data, go_fid) and bool(rend_info.get("enabled", True))
            if not is_act:
                if go_name:
                    disabled_meshes.add(go_name)
                continue
            if go_name:
                active_meshes.append(go_name)
                local_mesh_names.append(go_name)
            mguid = rend_info.get("mesh_guid", "") or doc_filters.get(go_fid, "")
            if mguid:
                doc_extra_guids.add(mguid)
            doc_extra_guids.update(rend_info.get("mat_guids", []))

        resolved_doc_guids = _collect_guid_paths_for_ma(doc_extra_guids, doc_path, resolved_assets)
        for go_fid, rend_info in doc_renderers.items():
            if filter_subtree and not _is_go_in_avatar_subtree(go_fid):
                continue
            go_name = str(doc_gos.get(go_fid, {}).get("name", "") or "").strip()
            if not go_name or go_name in disabled_meshes:
                continue
            mguid = rend_info.get("mesh_guid", "") or doc_filters.get(go_fid, "")
            mesh_asset = resolved_doc_guids.get(mguid)
            if mesh_asset is not None and mesh_asset.suffix.lower() == ".fbx":
                _register_fbx_path(mesh_asset, is_outfit=is_outfit_prefab)
                if str(mesh_asset) not in local_fbx_paths:
                    local_fbx_paths.append(str(mesh_asset))
            mat_dicts = _resolve_material_dicts(rend_info.get("mat_guids", []), doc_path)
            if mat_dicts:
                mesh_materials[go_name] = mat_dicts

        for toggle_comp in doc_data["object_toggles"]:
            if filter_subtree and not _is_go_in_avatar_subtree(toggle_comp["go_fid"]):
                continue
            if not _is_go_active_in_doc(doc_data, toggle_comp["go_fid"]):
                continue
            for item in toggle_comp["toggles"]:
                ref_path = item["reference_path"]
                object_toggles[ref_path] = bool(item["active"])
                if not item["active"] and ref_path:
                    disabled_meshes.add(ref_path.rsplit("/", 1)[-1])

        for rep_comp in doc_data["replace_objects"]:
            if filter_subtree and not _is_go_in_avatar_subtree(rep_comp["go_fid"]):
                continue
            if not _is_go_active_in_doc(doc_data, rep_comp["go_fid"]):
                continue
            tgt_tail = str(rep_comp["target_path"]).rsplit("/", 1)[-1].strip()
            if tgt_tail:
                disabled_meshes.add(tgt_tail)

        for shp_comp in doc_data["shape_changers"]:
            if filter_subtree and not _is_go_in_avatar_subtree(shp_comp["go_fid"]):
                continue
            if not _is_go_active_in_doc(doc_data, shp_comp["go_fid"]):
                continue
            for item in shp_comp["shapes"]:
                mesh_tail = str(item.get("reference_path", "") or "").rsplit("/", 1)[-1].strip() or "Body"
                shape_changer_weights.setdefault(mesh_tail, {})[item["shape_name"]] = float(item["weight"])

        for sync_comp in doc_data["blendshape_syncs"]:
            if filter_subtree and not _is_go_in_avatar_subtree(sync_comp["go_fid"]):
                continue
            if not _is_go_active_in_doc(doc_data, sync_comp["go_fid"]):
                continue
            local_mesh = str(doc_gos.get(sync_comp["go_fid"], {}).get("name", "") or "").strip()
            for bnd in sync_comp["bindings"]:
                src_mesh_tail = bnd["reference_mesh_path"].rsplit("/", 1)[-1].strip() or "Body"
                blendshape_syncs.append(
                    {
                        "source_mesh": src_mesh_tail,
                        "source_shape": bnd["source_shape"],
                        "target_mesh": local_mesh,
                        "target_shape": bnd["local_shape"],
                    }
                )

        for scl_comp in doc_data["scale_adjusters"]:
            if filter_subtree and not _is_go_in_avatar_subtree(scl_comp["go_fid"]):
                continue
            if not _is_go_active_in_doc(doc_data, scl_comp["go_fid"]):
                continue
            bone_name = str(doc_gos.get(scl_comp["go_fid"], {}).get("name", "") or "").strip()
            if bone_name:
                scale_adjusters.append({"bone_name": bone_name, "scale_xyz": scl_comp["scale"]})

        for merge_comp in doc_data["merge_armatures"]:
            if not merge_comp.get("enabled", True):
                continue
            if filter_subtree and not _is_go_in_avatar_subtree(merge_comp["go_fid"]):
                continue
            if not _is_go_active_in_doc(doc_data, merge_comp["go_fid"]):
                continue
            src_name = root_override_name or str(doc_gos.get(merge_comp["go_fid"], {}).get("name", "") or "").strip()
            armature_merges.append(
                {
                    "source_go": src_name,
                    "merge_target_path": merge_comp["merge_target_path"],
                    "prefix": merge_comp["prefix"],
                    "suffix": merge_comp["suffix"],
                    "mangle_names": merge_comp["mangle_names"],
                    "fbx_paths": list(local_fbx_paths),
                    "mesh_names": list(local_mesh_names),
                }
            )
            if root_override_name and root_override_name not in outfit_roots:
                outfit_roots.append(root_override_name)

        for proxy_comp in doc_data["bone_proxies"]:
            if not proxy_comp.get("enabled", True):
                continue
            if filter_subtree and not _is_go_in_avatar_subtree(proxy_comp["go_fid"]):
                continue
            if not _is_go_active_in_doc(doc_data, proxy_comp["go_fid"]):
                continue
            src_name = str(doc_gos.get(proxy_comp["go_fid"], {}).get("name", "") or "").strip()
            bone_ref_id = int(proxy_comp.get("bone_reference", -1))
            candidates = list(HUMAN_BODY_BONES.get(bone_ref_id, ()))
            sub_path = str(proxy_comp.get("sub_path", "") or "").strip()
            if sub_path:
                candidates.insert(0, sub_path.rsplit("/", 1)[-1])
            bone_proxies.append(
                {
                    "source_go": src_name or root_override_name,
                    "bone_reference": bone_ref_id,
                    "target_bone_candidates": candidates,
                    "sub_path": sub_path,
                    "attachment_mode": int(proxy_comp.get("attachment_mode", 1)),
                    "match_scale": bool(proxy_comp.get("match_scale", False)),
                    "fbx_paths": list(local_fbx_paths),
                    "mesh_names": list(local_mesh_names),
                }
            )

    # 1. Process components directly inside the scene avatar hierarchy
    _ingest_doc_ma_components(
        root_doc,
        src_path,
        filter_subtree=(src_path.suffix.lower() != ".prefab"),
        is_outfit_prefab=False,
    )

    # 2. Recursively process active child PrefabInstances (e.g. MA dresses / coats / accessories)
    visited_prefabs: Set[Path] = set()
    prefab_queue: deque = deque()
    for _pi_fid, pi_info in child_pis:
        prefab_path = guid_map.get(pi_info.get("source_guid", ""))
        if prefab_path and prefab_path.is_file():
            prefab_queue.append((prefab_path, pi_info.get("name", "") or prefab_path.stem))

    while prefab_queue:
        cur_prefab, cur_label = prefab_queue.popleft()
        resolved_pref = cur_prefab.resolve()
        if resolved_pref in visited_prefabs or resolved_pref.suffix.lower() != ".prefab":
            continue
        visited_prefabs.add(resolved_pref)
        pref_doc = parse_unity_yaml_with_ma(cur_prefab)
        is_outfit = any(
            kw_tok in cur_label.lower()
            or kw_tok in cur_prefab.stem.lower()
            for kw_tok in ("dress", "cloth", "outfit", "maid", "coat", "skirt", "jacket", "costume", "wear", "kisekae", "shoe", "boot", "hat", "hair", "ribbon")
        ) or bool(pref_doc["merge_armatures"] or pref_doc["bone_proxies"])
        _ingest_doc_ma_components(
            pref_doc,
            cur_prefab,
            filter_subtree=False,
            is_outfit_prefab=is_outfit,
            root_override_name=cur_label,
        )
        nested_guids = {
            nested_pi.get("source_guid", "")
            for nested_pi in pref_doc["prefab_instances"].values()
            if nested_pi.get("active", True) and nested_pi.get("source_guid")
        }
        nested_resolved = _collect_guid_paths_for_ma(nested_guids, cur_prefab, resolved_assets)
        for nested_pi in pref_doc["prefab_instances"].values():
            if not nested_pi.get("active", True):
                continue
            nested_path = nested_resolved.get(nested_pi.get("source_guid", ""))
            if nested_path and nested_path.is_file():
                prefab_queue.append((nested_path, nested_pi.get("name", "") or nested_path.stem))

    return {
        "loaded": True,
        "scene_path": str(src_path),
        "avatar_name": resolved_avatar_name,
        "armature_merges": armature_merges,
        "bone_proxies": bone_proxies,
        "scale_adjusters": scale_adjusters,
        "blendshape_syncs": blendshape_syncs,
        "shape_changer_weights": shape_changer_weights,
        "object_toggles": object_toggles,
        "disabled_meshes": sorted(disabled_meshes),
        "extra_fbx_paths": extra_fbx_paths,
        "base_fbx_paths": base_fbx_paths,
        "mesh_materials": mesh_materials,
        "active_meshes": active_meshes,
        "outfit_roots": outfit_roots,
    }


def _find_bone_in_armature(
    armature_obj: Any,
    candidates: Sequence[str],
) -> Optional[str]:
    """Return matching bone name inside a Blender Armature object using MA aliases."""
    bone_names = [bone.name for bone in armature_obj.data.bones]
    exact_set = set(bone_names)
    lower_map = {name.lower(): name for name in bone_names}
    norm_map = {normalize_bone_match_key(name): name for name in bone_names}

    for cand in candidates:
        if cand in exact_set:
            return cand
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
        norm_cand = normalize_bone_match_key(cand)
        if norm_cand in norm_map:
            return norm_map[norm_cand]
    return None


def _bake_merge_armature_in_blender(
    bpy_mod: Any,
    base_arm_obj: Any,
    outfit_arm_obj: Any,
    outfit_meshes: Sequence[Any],
    *,
    prefix: str = "",
    suffix: str = "",
) -> Dict[str, Any]:
    """
    Reproduce ModularAvatarMergeArmature natively in Blender:
      1. Merge matching outfit bones onto base armature vertex groups.
      2. Graft outfit-only child bones (skirts, ribbons, sleeves, PhysBones) into
         `base_arm_obj` parented under their mapped ancestor base bone.
      3. Rebind all outfit mesh Armature modifiers to `base_arm_obj` & clean helper arm.
    """
    if outfit_arm_obj is None or outfit_arm_obj == base_arm_obj:
        return {"merged_bones": 0, "grafted_bones": 0}

    base_bone_names = [bone.name for bone in base_arm_obj.data.bones]
    outfit_bone_names = [bone.name for bone in outfit_arm_obj.data.bones]
    bone_map = resolve_ma_bone_mapping(
        outfit_bone_names,
        base_bone_names,
        prefix=prefix,
        suffix=suffix,
    )

    # Remap vertex groups on every outfit mesh BEFORE modifying armatures
    for mesh_obj in outfit_meshes:
        if mesh_obj.type != "MESH":
            continue
        remapped_groups: Dict[str, List[Tuple[int, float]]] = {}
        existing_vg_names = [vgroup.name for vgroup in mesh_obj.vertex_groups]
        for vg_name in existing_vg_names:
            target_bone = bone_map.get(vg_name)
            if not target_bone or target_bone == vg_name:
                continue
            src_vg = mesh_obj.vertex_groups.get(vg_name)
            if src_vg is None:
                continue
            src_idx = src_vg.index
            weights_for_target = remapped_groups.setdefault(target_bone, [])
            for vtx in mesh_obj.data.vertices:
                for grp_elem in vtx.groups:
                    if grp_elem.group == src_idx and grp_elem.weight > 0.0:
                        weights_for_target.append((vtx.index, grp_elem.weight))
            mesh_obj.vertex_groups.remove(src_vg)

        for target_bone, pairs in remapped_groups.items():
            dst_vg = mesh_obj.vertex_groups.get(target_bone)
            if dst_vg is None:
                dst_vg = mesh_obj.vertex_groups.new(name=target_bone)
            for vtx_idx, weight_val in pairs:
                dst_vg.add([vtx_idx], weight_val, "ADD")

    # Collect world-space rest geometry for unmapped custom outfit bones
    outfit_matrix = outfit_arm_obj.matrix_world.copy()
    base_inv_matrix = base_arm_obj.matrix_world.inverted()
    custom_bone_specs: List[Dict[str, Any]] = []
    for bone in outfit_arm_obj.data.bones:
        if bone.name in bone_map:
            continue
        parent_name = bone.parent.name if bone.parent else ""
        custom_bone_specs.append(
            {
                "name": bone.name,
                "parent_src": parent_name,
                "head_world": outfit_matrix @ bone.head_local,
                "tail_world": outfit_matrix @ bone.tail_local,
                "roll": bone.matrix_local.to_3x3().to_euler().y,
            }
        )

    # Graft custom outfit bones into base_arm_obj in parent-before-child topological order
    grafted_count = 0
    if custom_bone_specs:
        bpy_mod.ops.object.select_all(action="DESELECT")
        bpy_mod.context.view_layer.objects.active = base_arm_obj
        base_arm_obj.select_set(True)
        bpy_mod.ops.object.mode_set(mode="EDIT")
        try:
            edit_bones = base_arm_obj.data.edit_bones
            for spec in custom_bone_specs:
                bname = spec["name"]
                if bname in edit_bones:
                    continue
                new_eb = edit_bones.new(bname)
                new_eb.head = base_inv_matrix @ spec["head_world"]
                tail_local = base_inv_matrix @ spec["tail_world"]
                if (tail_local - new_eb.head).length < 1e-4:
                    tail_local = new_eb.head.copy()
                    tail_local.z += 0.05
                new_eb.tail = tail_local
                new_eb.roll = spec["roll"]
                grafted_count += 1

            for spec in custom_bone_specs:
                bname = spec["name"]
                eb_cur = edit_bones.get(bname)
                if eb_cur is None:
                    continue
                parent_src = spec["parent_src"]
                resolved_parent = bone_map.get(parent_src, parent_src)
                if resolved_parent in edit_bones:
                    eb_cur.parent = edit_bones[resolved_parent]
                elif "Hips" in edit_bones:
                    eb_cur.parent = edit_bones["Hips"]
        finally:
            bpy_mod.ops.object.mode_set(mode="OBJECT")

    # Point every outfit mesh's Armature modifier at base_arm_obj and reparent cleanly
    for mesh_obj in outfit_meshes:
        if mesh_obj.type != "MESH":
            continue
        mesh_world = mesh_obj.matrix_world.copy()
        mesh_obj.parent = base_arm_obj
        mesh_obj.matrix_world = mesh_world
        arm_mod = next((mod_item for mod_item in mesh_obj.modifiers if mod_item.type == "ARMATURE"), None)
        if arm_mod is None:
            arm_mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
        arm_mod.object = base_arm_obj

    try:
        bpy_mod.data.objects.remove(outfit_arm_obj, do_unlink=True)
    except Exception:
        pass

    return {"merged_bones": len(bone_map), "grafted_bones": grafted_count}


def apply_modular_avatar_plan_in_blender(
    bpy_mod: Any,
    base_arm_obj: Any,
    bake_plan: Dict[str, Any],
    *,
    import_extra_fbx: bool = True,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> Dict[str, Any]:
    """
    Execute the complete Modular Avatar NDMF bake inside Blender:
      1. Apply ObjectToggles / disabled_meshes on base objects.
      2. Import extra outfit FBXs belonging to active MergeArmature / BoneProxy outfits.
      3. Apply ShapeChanger overrides and BlendshapeSync bindings.
      4. Bake MergeArmature & BoneProxy rigs onto `base_arm_obj` cleanly.
      5. Bind missing Unity/lilToon material textures onto imported outfit meshes.
      6. Apply ScaleAdjusters cleanly.
    """
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="ma_blender_bake")
    summary: Dict[str, Any] = {
        "imported_fbxs": [],
        "merged_armatures": 0,
        "grafted_bones": 0,
        "bound_proxies": 0,
        "synced_blendshapes": 0,
        "hidden_meshes": 0,
    }
    if not bake_plan or not bake_plan.get("loaded"):
        return summary

    # 1. Remove / hide disabled or replaced base objects
    disabled_lower = {str(name).strip().lower() for name in bake_plan.get("disabled_meshes", ())}
    for obj_key, is_active in bake_plan.get("object_toggles", {}).items():
        if not is_active and obj_key:
            disabled_lower.add(str(obj_key).rsplit("/", 1)[-1].strip().lower())

    for scene_obj in list(bpy_mod.data.objects):
        if scene_obj.type != "MESH":
            continue
        clean_low = re.sub(r"\.\d{3}$", "", scene_obj.name).strip().lower()
        if clean_low in disabled_lower and scene_obj.parent == base_arm_obj:
            bpy_mod.data.objects.remove(scene_obj, do_unlink=True)
            summary["hidden_meshes"] += 1

    # 2. Import missing extra outfit FBX files & track imported objects
    imported_by_fbx: Dict[str, List[Any]] = {}
    if import_extra_fbx:
        base_fbx_set = {str(Path(fbx_item)) for fbx_item in bake_plan.get("base_fbx_paths", ())}
        for raw_fbx in bake_plan.get("extra_fbx_paths", ()):
            fbx_file = Path(raw_fbx)
            if not fbx_file.is_file() or str(fbx_file) in base_fbx_set:
                continue
            before_names = {obj.name for obj in bpy_mod.data.objects}
            try:
                bpy_mod.ops.import_scene.fbx(
                    filepath=str(fbx_file),
                    use_anim=False,
                    automatic_bone_orientation=True,
                )
            except Exception as exc:
                active_logger.warning(f"Failed importing MA outfit FBX {fbx_file}: {exc}")
                continue
            newly_imported = [obj for obj in bpy_mod.data.objects if obj.name not in before_names]
            imported_by_fbx[str(fbx_file)] = newly_imported
            summary["imported_fbxs"].append(str(fbx_file))

            # Filter out disabled sub-meshes inside newly imported outfit FBX
            for imp_obj in list(newly_imported):
                if imp_obj.type == "MESH":
                    clean_low = re.sub(r"\.\d{3}$", "", imp_obj.name).strip().lower()
                    if clean_low in disabled_lower:
                        bpy_mod.data.objects.remove(imp_obj, do_unlink=True)
                        newly_imported.remove(imp_obj)

    # 3. Bake MergeArmature rigs onto base_arm_obj
    all_imported_meshes: List[Any] = []
    for imp_list in imported_by_fbx.values():
        arm_objs = [obj for obj in imp_list if obj.type == "ARMATURE"]
        mesh_objs = [obj for obj in imp_list if obj.type == "MESH"]
        all_imported_meshes.extend(mesh_objs)
        for outfit_arm in arm_objs:
            merge_meta = next(
                (
                    entry
                    for entry in bake_plan.get("armature_merges", ())
                    if any(obj.name.split(".")[0] in entry.get("mesh_names", ()) for obj in mesh_objs)
                    or outfit_arm.name.split(".")[0] in entry.get("source_go", "")
                ),
                {},
            )
            res = _bake_merge_armature_in_blender(
                bpy_mod,
                base_arm_obj,
                outfit_arm,
                mesh_objs,
                prefix=str(merge_meta.get("prefix", "")),
                suffix=str(merge_meta.get("suffix", "")),
            )
            summary["merged_armatures"] += 1
            summary["grafted_bones"] += res["grafted_bones"]

    # 4. Bake BoneProxy attachments (rigid props / hair accessories / unskinned parts)
    for proxy_spec in bake_plan.get("bone_proxies", ()):
        target_bone_name = _find_bone_in_armature(
            base_arm_obj, proxy_spec.get("target_bone_candidates", ())
        )
        if not target_bone_name:
            continue
        target_mesh_names = {
            name.lower() for name in proxy_spec.get("mesh_names", ()) if name
        }
        src_go_low = str(proxy_spec.get("source_go", "") or "").lower()
        for mesh_obj in all_imported_meshes:
            clean_low = re.sub(r"\.\d{3}$", "", mesh_obj.name).strip().lower()
            if clean_low not in target_mesh_names and src_go_low not in clean_low:
                continue
            if not mesh_obj.vertex_groups:
                vgroup = mesh_obj.vertex_groups.new(name=target_bone_name)
                vtx_indices = [vtx.index for vtx in mesh_obj.data.vertices]
                if vtx_indices:
                    vgroup.add(vtx_indices, 1.0, "REPLACE")
                arm_mod = next((mod_item for mod_item in mesh_obj.modifiers if mod_item.type == "ARMATURE"), None)
                if arm_mod is None:
                    arm_mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
                arm_mod.object = base_arm_obj
                mesh_obj.parent = base_arm_obj
                summary["bound_proxies"] += 1

    # 5. Apply ShapeChanger weights & BlendshapeSync propagation across all meshes
    mesh_by_name_low: Dict[str, Any] = {}
    for obj in bpy_mod.data.objects:
        if obj.type == "MESH":
            mesh_by_name_low[re.sub(r"\.\d{3}$", "", obj.name).strip().lower()] = obj

    for mesh_key, shape_dict in bake_plan.get("shape_changer_weights", {}).items():
        target_obj = mesh_by_name_low.get(mesh_key.lower()) or mesh_by_name_low.get("body")
        if target_obj and getattr(target_obj.data, "shape_keys", None):
            kblocks = target_obj.data.shape_keys.key_blocks
            for shp_name, w_val in shape_dict.items():
                if shp_name in kblocks:
                    kblocks[shp_name].value = float(w_val)

    for sync_item in bake_plan.get("blendshape_syncs", ()):
        src_obj = (
            mesh_by_name_low.get(str(sync_item.get("source_mesh", "")).lower())
            or mesh_by_name_low.get("body")
            or mesh_by_name_low.get("body_base")
        )
        dst_obj = mesh_by_name_low.get(str(sync_item.get("target_mesh", "")).lower())
        if not (src_obj and dst_obj):
            continue
        if not (getattr(src_obj.data, "shape_keys", None) and getattr(dst_obj.data, "shape_keys", None)):
            continue
        src_key = sync_item.get("source_shape", "")
        dst_key = sync_item.get("target_shape", "")
        if src_key in src_obj.data.shape_keys.key_blocks and dst_key in dst_obj.data.shape_keys.key_blocks:
            dst_obj.data.shape_keys.key_blocks[dst_key].value = (
                src_obj.data.shape_keys.key_blocks[src_key].value
            )
            summary["synced_blendshapes"] += 1

    # 6. Apply ScaleAdjusters to pose bones when present
    if bake_plan.get("scale_adjusters") and base_arm_obj.pose:
        for scl_item in bake_plan["scale_adjusters"]:
            bone_match = _find_bone_in_armature(base_arm_obj, [scl_item["bone_name"]])
            if bone_match and bone_match in base_arm_obj.pose.bones:
                scale_x, scale_y, scale_z = scl_item["scale_xyz"]
                base_arm_obj.pose.bones[bone_match].scale = (scale_x, scale_y, scale_z)

    # 7. Attach Unity material textures onto newly imported outfit meshes
    mesh_mats_map = bake_plan.get("mesh_materials", {})
    for mesh_obj in all_imported_meshes:
        clean_name = re.sub(r"\.\d{3}$", "", mesh_obj.name).strip()
        mat_list = mesh_mats_map.get(clean_name)
        if not mat_list:
            continue
        for slot_idx, mat_info in enumerate(mat_list):
            if slot_idx >= len(mesh_obj.data.materials):
                break
            bl_mat = mesh_obj.data.materials[slot_idx]
            if bl_mat is None:
                continue
            tex_envs = mat_info.get("tex_envs", {})
            main_entry = tex_envs.get("_MainTex") or tex_envs.get("_BaseMap") or tex_envs.get("_BaseColorMap")
            tex_path = main_entry.get("path") if isinstance(main_entry, dict) else None
            if not tex_path or not os.path.isfile(tex_path):
                continue
            bl_mat.use_nodes = True
            node_tree = bl_mat.node_tree
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

    return summary
