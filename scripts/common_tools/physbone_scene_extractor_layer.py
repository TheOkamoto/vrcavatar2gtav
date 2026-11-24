"""
physbone_scene_extractor_layer.py
=================================
Layer 4 of 5 for VRChat VRCPhysBone support (`physbone_helper` architecture).

Traverses full Unity scenes (`.unity` + nested `PrefabInstance` + `Script`
components) to assemble active VRCPhysBone trees, resolve ancestor transforms,
attach Marshmallow overrides, prune orphans, and match extracted spokes to
template chain specs.
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
        resolve_parent_bone_from_unity_chain,
    )
except ImportError:
    from common_tools.physbone_presets_layer import (
        resolve_parent_bone_from_unity_chain,
    )

try:
    from physbone_unity_fbx_layer import (
        _read_unity_meta_guid,
    _inspect_fbx_weights_detailed,
    _index_unity_asset_guids,
    _stream_parse_unity_physbone_doc,
    _collect_marshmallow_pb_overrides,
    _collect_linear_spokes,
    )
except ImportError:
    from common_tools.physbone_unity_fbx_layer import (
        _read_unity_meta_guid,
    _inspect_fbx_weights_detailed,
    _index_unity_asset_guids,
    _stream_parse_unity_physbone_doc,
    _collect_marshmallow_pb_overrides,
    _collect_linear_spokes,
    )

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

    if active_scene_meshes_ci:
        excluded_meshes_ci.difference_update(active_scene_meshes_ci)

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

    if active_scene_meshes_ci:
        excluded_meshes_ci.difference_update(active_scene_meshes_ci)

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

    fbx_parent_targets_ci: Set[str] = set(fbx_parent_map.values())
    humanoid_structural_roots_ci = frozenset(
        {"hips", "pelvis", "spine", "chest", "upperchest", "upper_chest", "neck", "head"}
    )

    def _is_fbx_bone(cand_name: str) -> bool:
        if not all_fbx_bones:
            return True
        low_val = str(cand_name or "").strip().lower()
        if low_val in all_fbx_bones:
            return True
        dot_val = regex_module.sub(r"\s+(\d+)$", lambda match_obj: f".{int(match_obj.group(1)):03d}", low_val)
        space_val = regex_module.sub(r"\.(\d{3})$", lambda match_obj: f" {int(match_obj.group(1))}", low_val)
        return dot_val in all_fbx_bones or space_val in all_fbx_bones

    def _fbx_has_ancestor(child_low: str, cand_ancestor_low: str) -> bool:
        cur = child_low
        for _step in range(16):
            par_low = fbx_parent_map.get(cur, "")
            if not par_low:
                return False
            if par_low == cand_ancestor_low:
                return True
            cur = par_low
        return False

    def _unwrap_container_spokes(raw_spokes: Sequence[List[str]]) -> Tuple[List[List[str]], bool]:
        """Filter missing Unity-only transforms and strip colliding/unweighted container roots."""
        if not raw_spokes:
            return list(raw_spokes), False
        cleaned_spokes: List[List[str]] = []
        for spoke_seq in raw_spokes:
            if not all_fbx_bones:
                cleaned_spokes.append(list(spoke_seq))
                continue
            kept_fbx = [bone_nm for bone_nm in spoke_seq if _is_fbx_bone(bone_nm)]
            if not kept_fbx:
                continue
            # Drop dead branches like [UN_Ribbon, RibbonRoot] when RibbonRoot is a non-FBX
            # empty transform and UN_Ribbon already has real FBX children animating it.
            if (
                len(spoke_seq) >= 2
                and len(kept_fbx) == 1
                and kept_fbx[0].strip().lower() in fbx_parent_targets_ci
            ):
                continue
            cleaned_spokes.append(kept_fbx)
        if not cleaned_spokes:
            return [], False
        first_root = str(cleaned_spokes[0][0]).strip().lower() if cleaned_spokes[0] else ""
        if not first_root or not all(len(spk) >= 3 and str(spk[0]).strip().lower() == first_root for spk in cleaned_spokes):
            return [list(spk) for spk in cleaned_spokes], False
        child_lows = [str(spk[1]).strip().lower() for spk in cleaned_spokes]
        parent_mismatch = bool(fbx_parent_map) and any(
            child_low in fbx_parent_map and not _fbx_has_ancestor(child_low, first_root)
            for child_low in child_lows
        )
        unweighted_multi = (
            len(cleaned_spokes) >= 2
            and bool(weighted_fbx_bones)
            and first_root not in weighted_fbx_bones
            and all(child_low in weighted_fbx_bones for child_low in child_lows)
        )
        if parent_mismatch or unweighted_multi:
            return [list(spk[1:]) for spk in cleaned_spokes], True
        return [list(spk) for spk in cleaned_spokes], False

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
        if not rt_name or rt_name.strip().lower() in humanoid_structural_roots_ci:
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
        spokes, unwrapped = _unwrap_container_spokes(spokes)
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
            eff_rt_name = spoke_bones[0] if unwrapped and spoke_bones else rt_name
            extracted_spokes.append(_pb_to_record(pb_data, eff_rt_name, spoke_bones, all_desc, ancestors))

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
            if not rt_name or rt_name.strip().lower() in humanoid_structural_roots_ci:
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
            spokes, unwrapped = _unwrap_container_spokes(spokes)
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
                eff_rt_name = spoke_bones[0] if unwrapped and spoke_bones else rt_name
                extracted_spokes.append(_pb_to_record(eff_pb, eff_rt_name, spoke_bones, all_desc, anc_names))

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
            if (
                not rt_name
                or rt_name.strip().lower() in seen_root_bones_ci
                or rt_name.strip().lower() in humanoid_structural_roots_ci
            ):
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
            spokes, unwrapped = _unwrap_container_spokes(spokes)
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
                eff_rt_name = spoke_bones[0] if unwrapped and spoke_bones else rt_name
                seen_root_bones_ci.add(eff_rt_name.strip().lower())
                extracted_spokes.append(_pb_to_record(pb_raw, eff_rt_name, spoke_bones, all_desc, anc_names))

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
            if (
                not rt_name
                or rt_name.strip().lower() in seen_root_bones_ci
                or rt_name.strip().lower() in humanoid_structural_roots_ci
            ):
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
            spokes, unwrapped = _unwrap_container_spokes(spokes)
            seen_root_bones_ci.add(rt_name.strip().lower())
            ancestors = _scene_ancestor_names(rt_tid)
            for spoke_bones in spokes:
                eff_rt_name = spoke_bones[0] if unwrapped and spoke_bones else rt_name
                seen_root_bones_ci.add(eff_rt_name.strip().lower())
                extracted_spokes.append(_pb_to_record(pb_data, eff_rt_name, spoke_bones, all_desc, ancestors))

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
