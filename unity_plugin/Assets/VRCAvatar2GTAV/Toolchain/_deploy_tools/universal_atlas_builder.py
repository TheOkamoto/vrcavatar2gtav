#!/usr/bin/env python3
"""
universal_atlas_builder.py
==========================
Generic VRChat Unity material/texture -> GTA V 2K atlas + .ytd compiler.

Resolves `.mat` properties (`_MainTex`, `_Color`, `_BumpMap`, `_BumpScale`,
`_EmissionMap`, `_EmissionColor`, `_Cutoff`, `_AlphaMask`), deduplicates shared
diffuse textures into an N x N 2048x2048 texture atlas (`2x2` for <=4 textures,
`3x3` for <=9, `4x4` for <=16), writes `atlas_manifest.json`, and builds an
RPF7-safe `<ped_name>_atlas.ytd` via `rage textures build`.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as numpy_lib
from PIL import Image

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

try:
    import modular_avatar_helper
    import npc_registry_helper
    import ped_damage_helper
    import unity_hair_bake_layer as hair_bake_layer
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import modular_avatar_helper
    from common_tools import npc_registry_helper
    from common_tools import ped_damage_helper
    from common_tools import unity_hair_bake_layer as hair_bake_layer
    from common_tools import vrc2gtav_paths as project_paths


_GUID_PATTERN = re.compile(r"^guid:\s*([0-9a-fA-F]{32})\b", re.MULTILINE)


def _index_project_guids(assets_root: Path) -> Dict[str, Path]:
    """Build a `{guid: file_path}` lookup from `.meta` files under `assets_root`."""
    guid_map: Dict[str, Path] = {}
    if not assets_root.is_dir():
        return guid_map
    for dir_path, dir_names, file_names in os.walk(assets_root):
        dir_names[:] = [
            sub_dir for sub_dir in dir_names
            if sub_dir.lower() not in {"library", "temp", "obj", "logs", ".git", "__pycache__", "psd_clip", "psd"}
        ]
        for file_name in file_names:
            if not file_name.endswith(".meta"):
                continue
            meta_file = Path(dir_path) / file_name
            try:
                head_txt = meta_file.read_text(encoding="utf-8", errors="ignore")[:1024]
            except OSError:
                continue
            guid_match = _GUID_PATTERN.search(head_txt)
            if guid_match:
                asset_candidate = meta_file.with_suffix("")
                if asset_candidate.exists():
                    guid_map[guid_match.group(1).lower()] = asset_candidate
    return guid_map


def parse_unity_material_file(
    mat_path: Path,
    guid_map: Dict[str, Path],
    _visited_paths: Optional[set[str]] = None,
) -> Dict[str, Any]:
    """Extract core diffuse, normal, emission, tint, and alpha settings from a Unity `.mat`."""
    mat_text = mat_path.read_text(encoding="utf-8", errors="replace")
    name_match = re.search(r"^\s*m_Name:\s*(.+)$", mat_text, re.MULTILINE)
    mat_name = name_match.group(1).strip() if name_match else mat_path.stem

    visited_set: set[str] = set(_visited_paths or ())
    mat_key = str(mat_path.resolve()).lower()
    visited_set.add(mat_key)
    parent_info: Dict[str, Any] = {}
    parent_match = re.search(r"^\s*m_Parent:\s*\{[^}]*guid:\s*([0-9a-fA-F]{32})", mat_text, re.MULTILINE)
    if parent_match:
        parent_path = guid_map.get(parent_match.group(1).lower())
        if parent_path and parent_path.is_file():
            parent_key = str(parent_path.resolve()).lower()
            if parent_key not in visited_set and len(visited_set) <= 5:
                parent_info = parse_unity_material_file(parent_path, guid_map, visited_set)

    def _has_prop(prop_key: str) -> bool:
        return bool(re.search(rf"^\s*-\s*{re.escape(prop_key)}:", mat_text, re.MULTILINE))

    def _tex_prop(prop_key: str) -> Optional[str]:
        block_match = re.search(
            rf"-\s*{re.escape(prop_key)}:\s*\n\s*m_Texture:\s*\{{fileID:\s*\d+(?:,\s*guid:\s*([0-9a-fA-F]+))?",
            mat_text,
        )
        if block_match and block_match.group(1):
            resolved = guid_map.get(block_match.group(1).lower())
            if resolved and resolved.is_file():
                return str(resolved)
        return None

    def _color_prop(prop_key: str, default_rgba: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
        color_match = re.search(
            rf"-\s*{re.escape(prop_key)}:\s*\{{r:\s*([^,]+),\s*g:\s*([^,]+),\s*b:\s*([^,]+),\s*a:\s*([^}}]+)\}}",
            mat_text,
        )
        if color_match:
            try:
                return (
                    float(color_match.group(1)),
                    float(color_match.group(2)),
                    float(color_match.group(3)),
                    float(color_match.group(4)),
                )
            except ValueError:
                pass
        return default_rgba

    def _float_prop(prop_key: str, default_val: float) -> float:
        float_match = re.search(rf"^\s*-\s*{re.escape(prop_key)}:\s*([-0-9.eE+]+)", mat_text, re.MULTILINE)
        if float_match:
            try:
                return float(float_match.group(1))
            except ValueError:
                pass
        return default_val

    main_tex = (
        _tex_prop("_MainTex")
        if _has_prop("_MainTex")
        else (
            parent_info.get("main_tex")
            or _tex_prop("_BaseMap")
            or _tex_prop("_BaseColorMap")
            or _tex_prop("_Main2ndTex")
        )
    )
    bump_tex = _tex_prop("_BumpMap") if _has_prop("_BumpMap") else parent_info.get("bump_tex")
    emission_tex = _tex_prop("_EmissionMap") if _has_prop("_EmissionMap") else parent_info.get("emission_tex")
    alpha_mask_tex = _tex_prop("_AlphaMask") if _has_prop("_AlphaMask") else parent_info.get("alpha_mask_tex")
    parent_color = tuple(parent_info.get("color_rgba") or (1.0, 1.0, 1.0, 1.0))
    parent_emis = tuple(parent_info.get("emission_rgba") or (0.0, 0.0, 0.0, 1.0))
    parent_hsvg = tuple(parent_info.get("hsvg_rgba") or (0.0, 1.0, 1.0, 1.0))
    color_rgba = _color_prop("_Color", parent_color)  # type: ignore[arg-type]
    emission_rgba = _color_prop("_EmissionColor", parent_emis)  # type: ignore[arg-type]
    hsvg_rgba = _color_prop("_MainTexHSVG", parent_hsvg)  # type: ignore[arg-type]
    main2nd_flag = _float_prop("_UseMain2ndTex", float(parent_info.get("use_main2nd", 0.0)))
    bump_scale = _float_prop("_BumpScale", float(parent_info.get("bump_scale", 0.5)))
    cutoff_val = _float_prop("_Cutoff", float(parent_info.get("cutoff", 0.5)))
    cull_mode = _float_prop("_Cull", float(parent_info.get("cull_mode", 2.0)))
    transparent_mode = _float_prop(
        "_TransparentMode",
        float(parent_info.get("transparent_mode", -1.0)),
    )
    alpha_mask_mode = int(
        round(_float_prop("_AlphaMaskMode", float(parent_info.get("alpha_mask_mode", 0.0))))
    )
    alpha_mask_scale = _float_prop(
        "_AlphaMaskScale",
        float(parent_info.get("alpha_mask_scale", 1.0)),
    )
    alpha_mask_val = _float_prop(
        "_AlphaMaskValue",
        float(parent_info.get("alpha_mask_val", 0.0)),
    )
    shader_match = re.search(r"m_Shader:\s*\{[^}]*guid:\s*([0-9a-fA-F]{32})", mat_text)
    shader_guid = shader_match.group(1).lower() if shader_match else str(parent_info.get("shader_guid", ""))
    kw_match = re.search(r"m_ShaderKeywords:\s*(.*)$", mat_text, re.MULTILINE)
    shader_keywords = kw_match.group(1) if kw_match else ""
    render_queue_match = re.search(r"m_CustomRenderQueue:\s*(-?\d+)", mat_text)
    render_queue = int(render_queue_match.group(1)) if render_queue_match else int(parent_info.get("render_queue", 2000))
    if render_queue < 0 and parent_info:
        render_queue = int(parent_info.get("render_queue", 2000))

    # Treat pure alpha-overlay materials (e.g. Karin_Alpha on Body) as strippable
    # only when named as explicit alpha overlays and not hair transparency masks.
    low_name = mat_name.lower()
    is_body_alpha_overlay = ("alpha" in low_name and "hair" not in low_name)
    shader_is_refract = shader_guid in hair_bake_layer.LILTOON_REFRACTION_SHADER_GUIDS
    shader_is_trans = shader_guid in hair_bake_layer.LILTOON_TRANSPARENT_SHADER_GUIDS
    shader_is_cutout = shader_guid in hair_bake_layer.LILTOON_CUTOUT_SHADER_GUIDS
    if (transparent_mode == 0.0 and not shader_is_trans and not shader_is_cutout) or alpha_mask_mode == 0:
        # In lilToon, _AlphaMask is ignored when shader & _TransparentMode are Opaque, or _AlphaMaskMode is None (0)
        alpha_mask_tex = None

    unbound_alpha_eff = max(0.0, min(1.0, 1.0 * alpha_mask_scale + alpha_mask_val))
    has_unbound_alpha_fade = (
        shader_is_trans
        and (alpha_mask_mode in (1, 2))
        and (not alpha_mask_tex)
        and (unbound_alpha_eff < 0.96)
    )
    has_trans_color_alpha = shader_is_trans and (float(color_rgba[3]) < 0.96)

    if is_body_alpha_overlay:
        alpha_mode = "opaque"
    elif shader_is_refract or has_unbound_alpha_fade or has_trans_color_alpha:
        alpha_mode = "transparent"
    elif transparent_mode >= 0.0:
        if transparent_mode >= 2.0 or "_ALPHABLEND_ON" in shader_keywords:
            alpha_mode = "transparent"
        elif transparent_mode >= 1.0 or "_ALPHATEST_ON" in shader_keywords:
            alpha_mode = "cutout"
        else:
            alpha_mode = "opaque"
    elif (
        shader_is_trans
        or render_queue >= 2900
        or "_ALPHABLEND_ON" in shader_keywords
        or ("hair" in low_name and ("trans" in low_name or "alpha" in low_name or "bang" in low_name or "front" in low_name))
    ):
        alpha_mode = "transparent"
    elif "hair" in low_name or alpha_mask_tex or render_queue >= 2400 or "_ALPHATEST_ON" in shader_keywords:
        alpha_mode = "cutout"
    else:
        alpha_mode = "opaque"

    return {
        "name": mat_name,
        "raw_name": mat_name,
        "mat_path": str(mat_path),
        "main_tex": main_tex,
        "bump_tex": bump_tex,
        "emission_tex": emission_tex,
        "alpha_mask_tex": alpha_mask_tex,
        "alpha_mask_mode": alpha_mask_mode,
        "alpha_mask_scale": alpha_mask_scale,
        "alpha_mask_val": alpha_mask_val,
        "color_rgba": list(color_rgba),
        "emission_rgba": list(emission_rgba),
        "hsvg_rgba": list(hsvg_rgba),
        "use_main2nd": main2nd_flag,
        "bump_scale": bump_scale,
        "cutoff": cutoff_val,
        "cull_mode": cull_mode,
        "transparent_mode": transparent_mode,
        "is_double_sided": cull_mode < 0.5,
        "alpha_mode": alpha_mode,
        "shader_guid": shader_guid,
        "render_queue": render_queue,
        "is_body_alpha_overlay": is_body_alpha_overlay,
    }


def _collect_scoped_scene_mat_guids(
    scene_or_prefab: Path,
    guid_map: Dict[str, Path],
    avatar_name: Optional[str] = None,
) -> List[Path]:
    """Resolve material paths referenced strictly by the chosen avatar subtree & child prefabs."""
    doc_data = modular_avatar_helper.parse_unity_yaml_with_ma(scene_or_prefab)
    gameobjects = doc_data.get("gameobjects", {})
    transforms = doc_data.get("transforms", {})
    go_to_tr = doc_data.get("go_to_tr", {})
    children_by_tr: Dict[str, List[str]] = {}
    for tr_id, tr_info in transforms.items():
        children_by_tr.setdefault(str(tr_info.get("father_tr", "0")), []).append(tr_id)

    stop_tr: Optional[str] = None
    subtree_trs: Optional[set[str]] = None
    if avatar_name and scene_or_prefab.suffix.lower() == ".unity":
        wanted_low = str(avatar_name).strip().lower()
        for tr_id, tr_info in transforms.items():
            go_fid = str(tr_info.get("go_fid", ""))
            go_name = str(gameobjects.get(go_fid, {}).get("name", "") or "").strip().lower()
            if go_name == wanted_low:
                stop_tr = tr_id
                break
        if stop_tr is not None:
            subtree_trs = set()
            stack_trs = [stop_tr]
            while stack_trs:
                cur_tr = stack_trs.pop()
                if cur_tr in subtree_trs:
                    continue
                subtree_trs.add(cur_tr)
                stack_trs.extend(children_by_tr.get(cur_tr, []))

    found_mats: List[Path] = []
    seen_mat_keys: set[str] = set()

    def _push_mat(cand_path: Optional[Path]) -> None:
        if cand_path and cand_path.is_file() and cand_path.suffix.lower() == ".mat":
            key_str = str(cand_path.resolve()).lower()
            if key_str not in seen_mat_keys:
                seen_mat_keys.add(key_str)
                found_mats.append(cand_path)

    for go_fid, rend_info in doc_data.get("renderers", {}).items():
        if subtree_trs is not None and go_to_tr.get(go_fid) not in subtree_trs:
            continue
        is_act = modular_avatar_helper._is_go_active_in_doc(
            doc_data, go_fid, stop_tr=stop_tr
        ) and bool(rend_info.get("enabled", True))
        if not is_act:
            continue
        for mat_guid in rend_info.get("mat_guids", []):
            _push_mat(guid_map.get(str(mat_guid).lower()))

    prefab_queue: List[Path] = []
    for pi_info in doc_data.get("prefab_instances", {}).values():
        if not pi_info.get("active", True):
            continue
        if subtree_trs is not None and str(pi_info.get("parent_tr", "0")) not in subtree_trs:
            continue
        src_pref = guid_map.get(str(pi_info.get("source_guid", "")).lower())
        if src_pref and src_pref.suffix.lower() == ".prefab" and src_pref.is_file():
            prefab_queue.append(src_pref)

    visited_prefabs: set[str] = set()
    while prefab_queue:
        cur_pref = prefab_queue.pop(0)
        pref_key = str(cur_pref.resolve()).lower()
        if pref_key in visited_prefabs:
            continue
        visited_prefabs.add(pref_key)
        pref_doc = modular_avatar_helper.parse_unity_yaml_with_ma(cur_pref)
        for go_fid, rend_info in pref_doc.get("renderers", {}).items():
            is_act = modular_avatar_helper._is_go_active_in_doc(pref_doc, go_fid) and bool(
                rend_info.get("enabled", True)
            )
            if not is_act:
                continue
            for mat_guid in rend_info.get("mat_guids", []):
                _push_mat(guid_map.get(str(mat_guid).lower()))
        for pi_info in pref_doc.get("prefab_instances", {}).values():
            if not pi_info.get("active", True):
                continue
            src_pref = guid_map.get(str(pi_info.get("source_guid", "")).lower())
            if src_pref and src_pref.suffix.lower() == ".prefab" and src_pref.is_file():
                prefab_queue.append(src_pref)

    return found_mats


def collect_avatar_materials(
    scene_or_prefab: Optional[Path],
    project_dir: Path,
    source_fbx: Path,
    extra_fbxs: Sequence[Path] = (),
    ma_plan: Optional[Dict[str, Any]] = None,
    avatar_name: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Collect and parse `.mat` descriptors referenced strictly by the selected avatar
    (via `ma_plan` or scoped Unity subtree) or colocated near its FBX files.
    """
    guid_root = project_dir / "Assets" if (project_dir / "Assets").is_dir() else project_dir
    guid_map = _index_project_guids(guid_root)

    discovered_mat_paths: List[Path] = []
    seen_paths: set[str] = set()

    def _add_mat(candidate_path: Optional[Path]) -> None:
        if candidate_path and candidate_path.is_file() and candidate_path.suffix.lower() == ".mat":
            key_str = str(candidate_path.resolve()).lower()
            if key_str not in seen_paths:
                seen_paths.add(key_str)
                discovered_mat_paths.append(candidate_path)

    if isinstance(ma_plan, dict) and ma_plan.get("loaded"):
        for mat_list in (ma_plan.get("mesh_materials") or {}).values():
            if not isinstance(mat_list, list):
                continue
            for mat_entry in mat_list:
                if isinstance(mat_entry, dict) and mat_entry.get("mat_path"):
                    _add_mat(Path(str(mat_entry["mat_path"])))
        for inst_entry in ma_plan.get("fbx_instances") or ():
            if not isinstance(inst_entry, dict):
                continue
            for mat_list in (inst_entry.get("mesh_materials") or {}).values():
                if not isinstance(mat_list, list):
                    continue
                for mat_entry in mat_list:
                    if isinstance(mat_entry, dict) and mat_entry.get("mat_path"):
                        _add_mat(Path(str(mat_entry["mat_path"])))
        for mat_guid in ma_plan.get("active_mat_guids") or ():
            _add_mat(guid_map.get(str(mat_guid).lower()))

    resolved_avatar_label = avatar_name or (
        str(ma_plan.get("avatar_name", "") or "").strip() if isinstance(ma_plan, dict) else ""
    )
    if not discovered_mat_paths and scene_or_prefab and scene_or_prefab.is_file():
        for scoped_mat in _collect_scoped_scene_mat_guids(
            scene_or_prefab, guid_map, avatar_name=resolved_avatar_label or None
        ):
            _add_mat(scoped_mat)

    if not discovered_mat_paths:
        for anchor_fbx in [source_fbx, *list(extra_fbxs)]:
            if not anchor_fbx.exists():
                continue
            for search_dir in (anchor_fbx.parent, anchor_fbx.parent.parent):
                if not search_dir.is_dir():
                    continue
                for mat_file in search_dir.rglob("*.mat"):
                    _add_mat(mat_file)

    materials_by_name: Dict[str, Dict[str, Any]] = {}
    for mat_file in discovered_mat_paths:
        parsed_mat = parse_unity_material_file(mat_file, guid_map)
        base_key = parsed_mat["name"]
        if base_key not in materials_by_name:
            materials_by_name[base_key] = parsed_mat
        else:
            disambig = f"{base_key} ({mat_file.parent.name})"
            if disambig in materials_by_name:
                disambig = f"{base_key}_{len(materials_by_name)}"
            parsed_mat["name"] = disambig
            materials_by_name[disambig] = parsed_mat
    return materials_by_name


def _load_tinted_tile(
    tex_path: Path,
    tile_size: int,
    color_rgba: Sequence[float],
    emission_tex: Optional[str] = None,
    emission_rgba: Sequence[float] = (0.0, 0.0, 0.0, 1.0),
    alpha_mask_tex: Optional[str] = None,
    alpha_mask_scale: float = 1.0,
    alpha_mask_val: float = 0.0,
    preserve_alpha: bool = False,
) -> Image.Image:
    """Load a texture tile resized to `tile_size`, applying `_Color` and optional `_AlphaMask`."""
    tile_img = (
        Image.open(tex_path)
        .convert("RGBA")
        .resize((tile_size, tile_size), Image.Resampling.LANCZOS)
    )
    arr_float = numpy_lib.array(tile_img, dtype=numpy_lib.float32)
    for chan_idx in range(3):
        arr_float[:, :, chan_idx] *= float(color_rgba[chan_idx])
    if preserve_alpha:
        color_alpha = max(0.0, min(1.0, float(color_rgba[3]) if len(color_rgba) >= 4 else 1.0))
        arr_float[:, :, 3] *= color_alpha
        if alpha_mask_tex and Path(alpha_mask_tex).is_file():
            am_img = (
                Image.open(alpha_mask_tex)
                .convert("RGBA")
                .resize((tile_size, tile_size), Image.Resampling.LANCZOS)
            )
            am_r = numpy_lib.array(am_img, dtype=numpy_lib.float32)[:, :, 0] / 255.0
            eff_mask = numpy_lib.clip(am_r * float(alpha_mask_scale) + float(alpha_mask_val), 0.0, 1.0)
            arr_float[:, :, 3] *= eff_mask
    else:
        arr_float[:, :, 3] = 255.0

    if emission_tex and Path(emission_tex).is_file():
        em_mag = max(float(emission_rgba[0]), float(emission_rgba[1]), float(emission_rgba[2]))
        if em_mag > 0.02:
            em_img = (
                Image.open(emission_tex)
                .convert("RGBA")
                .resize((tile_size, tile_size), Image.Resampling.LANCZOS)
            )
            em_arr = numpy_lib.array(em_img, dtype=numpy_lib.float32)
            for chan_idx in range(3):
                arr_float[:, :, chan_idx] += (
                    em_arr[:, :, chan_idx] * float(emission_rgba[chan_idx]) * 0.65
                )

    clamped = numpy_lib.clip(arr_float, 0.0, 255.0).astype(numpy_lib.uint8)
    return Image.fromarray(clamped, "RGBA")


def build_universal_avatar_atlas(
    *,
    ped_name: str,
    project_dir: Path,
    scene_or_prefab: Optional[Path],
    source_fbx: Path,
    extra_fbxs: Sequence[Path] = (),
    output_dir: Path,
    atlas_size: int = 2048,
    normal_size: int = 0,
    texture_overrides: Optional[Dict[str, str]] = None,
    vtoon_char_id: int = 4,
    sync_to_game: bool = True,
    ma_plan: Optional[Dict[str, Any]] = None,
    avatar_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a combined diffuse atlas (512..4096px), normal map, black spec map,
    `<ped_name>_atlas.ytd`, and `atlas_manifest.json` mapping each material name
    to its UV quadrant `(u_offset, v_offset, u_scale, v_scale)`.
    """
    atlas_size = max(256, min(4096, int(atlas_size or 2048)))
    normal_size = int(normal_size or 0)
    output_dir.mkdir(parents=True, exist_ok=True)
    textures_dir = output_dir / "textures"
    textures_dir.mkdir(parents=True, exist_ok=True)

    if ma_plan is not None or avatar_name:
        materials_map = collect_avatar_materials(
            scene_or_prefab,
            project_dir,
            source_fbx,
            extra_fbxs=extra_fbxs,
            ma_plan=ma_plan,
            avatar_name=avatar_name,
        )
    else:
        materials_map = collect_avatar_materials(
            scene_or_prefab, project_dir, source_fbx, extra_fbxs=extra_fbxs
        )

    overrides_low: Dict[str, str] = {}
    for raw_mat_key, raw_tex_val in (texture_overrides or {}).items():
        tex_raw_str = str(raw_tex_val or "").strip()
        if not tex_raw_str:
            continue
        try:
            host_tex = str(project_paths.to_host_path(tex_raw_str, project_root_dir=project_dir))
        except Exception:
            host_tex = tex_raw_str
        if Path(host_tex).is_file():
            norm_mat_key = re.sub(r"\s*\(instance\)$", "", str(raw_mat_key).strip(), flags=re.I).lower()
            if norm_mat_key:
                overrides_low[norm_mat_key] = host_tex

    if overrides_low:
        wildcard_tex = overrides_low.get("*") or overrides_low.get("__all__") or ""
        for mat_name, mat_info in materials_map.items():
            mat_key = re.sub(r"\s*\(instance\)$", "", str(mat_name).strip(), flags=re.I).lower()
            chosen_tex = overrides_low.get(mat_key) or wildcard_tex
            if chosen_tex:
                mat_info["main_tex"] = chosen_tex
                mat_info["mat_path"] = ""
                mat_info["color_rgba"] = [1.0, 1.0, 1.0, 1.0]

    # Deduplicate materials sharing identical diffuse texture + tint + HSVG/2nd-layer signature
    tile_entries: List[Dict[str, Any]] = []
    tile_key_to_idx: Dict[Tuple[Any, ...], int] = {}
    material_to_tile_idx: Dict[str, int] = {}

    for mat_name in sorted(materials_map.keys()):
        mat_info = materials_map[mat_name]
        if mat_info.get("is_body_alpha_overlay"):
            continue
        main_tex = mat_info.get("main_tex")
        tint_rgb = tuple(round(float(val), 3) for val in mat_info["color_rgba"][:3])
        hsvg_sig = tuple(round(float(val), 3) for val in (mat_info.get("hsvg_rgba") or (0.0, 1.0, 1.0, 1.0))[:4])
        use_2nd = int(round(float(mat_info.get("use_main2nd", 0.0))))
        raw_mat_p = str(mat_info.get("mat_path", "") or "").lower()
        if main_tex and Path(main_tex).is_file():
            dedup_key = (str(Path(main_tex).resolve()).lower(), tint_rgb, hsvg_sig, use_2nd)
            resolved_main_tex = main_tex
        else:
            dedup_key = ("__solid_color__", tint_rgb, raw_mat_p)
            resolved_main_tex = "__SOLID_COLOR__"
        if dedup_key not in tile_key_to_idx:
            tile_idx = len(tile_entries)
            tile_key_to_idx[dedup_key] = tile_idx
            tile_entries.append(
                {
                    "main_tex": resolved_main_tex,
                    "color_rgba": mat_info["color_rgba"],
                    "bump_tex": mat_info.get("bump_tex"),
                    "bump_scale": mat_info.get("bump_scale", 0.5),
                    "emission_tex": mat_info.get("emission_tex"),
                    "emission_rgba": mat_info.get("emission_rgba", [0.0, 0.0, 0.0, 1.0]),
                    "alpha_mask_tex": mat_info.get("alpha_mask_tex"),
                    "alpha_mask_scale": mat_info.get("alpha_mask_scale", 1.0),
                    "alpha_mask_val": mat_info.get("alpha_mask_val", 0.0),
                    "alpha_mode": mat_info.get("alpha_mode", "opaque"),
                    "is_double_sided": mat_info.get("is_double_sided", False),
                    "cull_mode": mat_info.get("cull_mode", 2.0),
                    "cutoff": mat_info.get("cutoff", 0.5),
                    "mat_path": mat_info.get("mat_path", ""),
                    "materials": [mat_name],
                }
            )
        else:
            tile_idx = tile_key_to_idx[dedup_key]
            tile_entries[tile_idx]["materials"].append(mat_name)
        material_to_tile_idx[mat_name] = tile_idx

    # Fallback scan for Texture/*.png when no .mat was discovered
    if not tile_entries:
        png_candidates = sorted(
            png_path for png_path in project_dir.rglob("*.png")
            if "mask" not in str(png_path).lower()
            and "normal" not in str(png_path).lower()
            and "matcap" not in str(png_path).lower()
        )[:4]
        for idx, png_path in enumerate(png_candidates):
            tile_entries.append(
                {
                    "main_tex": str(png_path),
                    "color_rgba": [1.0, 1.0, 1.0, 1.0],
                    "bump_tex": None,
                    "bump_scale": 0.5,
                    "emission_tex": None,
                    "emission_rgba": [0.0, 0.0, 0.0, 1.0],
                    "materials": [png_path.stem],
                }
            )
            material_to_tile_idx[png_path.stem] = idx

    if not tile_entries:
        raise FileNotFoundError(f"No diffuse textures found for avatar in {project_dir}")

    tile_count = len(tile_entries)
    if tile_count == 1:
        grid_dim = 1
    elif tile_count <= 4:
        grid_dim = 2
    elif tile_count <= 9:
        grid_dim = 3
    else:
        grid_dim = 4
        if tile_count > 16:
            tile_entries = tile_entries[:16]

    tile_size = atlas_size // grid_dim
    atlas_canvas = Image.new("RGBA", (atlas_size, atlas_size), (210, 195, 195, 255))
    normal_canvas = Image.new("RGBA", (atlas_size, atlas_size), (128, 128, 255, 255))
    has_bump_map = False

    uv_regions_by_mat: Dict[str, Dict[str, Any]] = {}
    uv_regions_by_mat_path: Dict[str, Dict[str, Any]] = {}
    uv_regions_by_tex_stem: Dict[str, Dict[str, Any]] = {}

    for tile_idx, entry_data in enumerate(tile_entries):
        col_idx = tile_idx % grid_dim
        row_idx = tile_idx // grid_dim
        paste_x = col_idx * tile_size
        paste_y = row_idx * tile_size

        entry_mat_path = entry_data.get("mat_path", "")
        is_opaque_tile = str(entry_data.get("alpha_mode", "opaque")) == "opaque"
        tile_img = None
        if entry_mat_path and Path(entry_mat_path).is_file():
            import unity_hair_bake_layer as hair_bake_layer

            assets_anchor = project_dir / "Assets" if (project_dir / "Assets").is_dir() else project_dir
            baked_res = hair_bake_layer.bake_liltoon_mat_to_image(
                entry_mat_path,
                tile_size=(tile_size, tile_size),
                preserve_alpha=(not is_opaque_tile),
                unity_assets_root=assets_anchor,
            )
            if baked_res is not None:
                tile_img = baked_res[0]
        if tile_img is None and entry_data["main_tex"] == "__SOLID_COLOR__":
            tint_vals = entry_data.get("color_rgba") or (1.0, 1.0, 1.0, 1.0)
            solid_rgb = tuple(
                max(0, min(255, int(round(float(tint_vals[chan_idx]) * 255.0))))
                for chan_idx in range(3)
            )
            tile_img = Image.new("RGBA", (tile_size, tile_size), (*solid_rgb, 255))
        if tile_img is None:
            tile_img = _load_tinted_tile(
                Path(entry_data["main_tex"]),
                tile_size,
                entry_data["color_rgba"],
                emission_tex=entry_data.get("emission_tex"),
                emission_rgba=entry_data.get("emission_rgba", (0.0, 0.0, 0.0, 1.0)),
                alpha_mask_tex=entry_data.get("alpha_mask_tex"),
                alpha_mask_scale=float(entry_data.get("alpha_mask_scale", 1.0)),
                alpha_mask_val=float(entry_data.get("alpha_mask_val", 0.0)),
                preserve_alpha=(not is_opaque_tile),
            )
        if is_opaque_tile:
            tile_img = tile_img.convert("RGB").convert("RGBA")
        atlas_canvas.paste(tile_img, (paste_x, paste_y))

        bump_tex = entry_data.get("bump_tex")
        if bump_tex and Path(bump_tex).is_file():
            bump_img = (
                Image.open(bump_tex)
                .convert("RGBA")
                .resize((tile_size, tile_size), Image.Resampling.LANCZOS)
            )
            bump_arr = numpy_lib.array(bump_img, dtype=numpy_lib.float32)
            bscale = float(entry_data.get("bump_scale", 0.5))
            bump_arr[:, :, 0] = 128.0 + (bump_arr[:, :, 0] - 128.0) * bscale
            bump_arr[:, :, 1] = 128.0 + (bump_arr[:, :, 1] - 128.0) * bscale
            bump_arr[:, :, 2] = 255.0 - (255.0 - bump_arr[:, :, 2]) * bscale
            bump_arr[:, :, 3] = 255.0
            normal_tile = Image.fromarray(
                numpy_lib.clip(bump_arr, 0.0, 255.0).astype(numpy_lib.uint8), "RGBA"
            )
            normal_canvas.paste(normal_tile, (paste_x, paste_y))
            has_bump_map = True

        # PIL top row (row_idx=0) corresponds to top V=[1 - 1/grid_dim, 1.0] in Blender/RAGE UV space
        uv_scale = 1.0 / float(grid_dim)
        u_offset = float(col_idx) * uv_scale
        v_offset = 1.0 - float(row_idx + 1) * uv_scale
        region_spec = {
            "tile_index": tile_idx,
            "grid_dim": grid_dim,
            "u_offset": u_offset,
            "v_offset": v_offset,
            "u_scale": uv_scale,
            "v_scale": uv_scale,
            "diffuse_src": "" if entry_data["main_tex"] == "__SOLID_COLOR__" else entry_data["main_tex"],
            "alpha_mode": entry_data.get("alpha_mode", "opaque"),
            "is_double_sided": bool(entry_data.get("is_double_sided", False)),
            "cull_mode": float(entry_data.get("cull_mode", 2.0)),
            "cutoff": float(entry_data.get("cutoff", 0.5)),
            "mat_path": entry_data.get("mat_path", ""),
        }
        if entry_data["main_tex"] != "__SOLID_COLOR__":
            tex_stem_low = Path(entry_data["main_tex"]).stem.lower()
            uv_regions_by_tex_stem[tex_stem_low] = region_spec
        for mat_name in entry_data["materials"]:
            uv_regions_by_mat[mat_name] = region_spec
            mat_rec = materials_map.get(mat_name) or {}
            rec_path = str(mat_rec.get("mat_path", "") or "").strip()
            if rec_path:
                uv_regions_by_mat_path[rec_path.replace("\\", "/").lower()] = region_spec
                try:
                    uv_regions_by_mat_path[str(Path(rec_path).resolve()).replace("\\", "/").lower()] = region_spec
                except OSError:
                    pass

    safe_prefix = re.sub(r"[^a-zA-Z0-9_]+", "_", ped_name.strip().lower()).strip("_") or "npc_avatar"
    atlas_png_path = textures_dir / f"{safe_prefix}_atlas_2k.png"
    normal_png_path = textures_dir / f"{safe_prefix}_flat_normal.png"
    spec_png_path = textures_dir / f"{safe_prefix}_black_spec.png"
    ytd_path = output_dir / f"{safe_prefix}_atlas.ytd"

    import vtoon_profile_helper

    if vtoon_char_id >= 1:
        atlas_canvas = vtoon_profile_helper.stamp_vtoon_watermark_block(atlas_canvas, vtoon_char_id)
        # Generate VToon LUT, MatCap, and INI entry for universal avatars cleanly
        lut_regions = []
        slot_materials = {}
        matcap_candidates = []
        for reg_name, reg_data in uv_regions_by_mat.items():
            low_mat = reg_name.lower()
            low_path = str(reg_data.get("mat_path", "") or "").replace("\\", "/").lower()
            is_hair_token = "hair" in low_mat or (
                "hair" in low_path
                and "accessories" not in low_path
                and "pin" not in low_mat
                and "halo" not in low_mat
            )
            if is_hair_token and str(reg_data.get("alpha_mode")) == "transparent":
                slot_id = vtoon_profile_helper.SLOT_HAIR_ALPHA
                rim_mask, sh_mask = 0.85, 0.90
            elif is_hair_token:
                slot_id = vtoon_profile_helper.SLOT_HAIR
                rim_mask, sh_mask = 0.85, 0.95
            elif "face" in low_mat or "head" in low_mat:
                slot_id = vtoon_profile_helper.SLOT_FACE
                rim_mask, sh_mask = 0.20, 0.88
            elif "body" in low_mat or "skin" in low_mat:
                slot_id = vtoon_profile_helper.SLOT_SKIN
                rim_mask, sh_mask = 0.25, 0.90
            else:
                slot_id = vtoon_profile_helper.SLOT_CLOTH
                rim_mask, sh_mask = 0.45, 0.95
            lut_regions.append(
                vtoon_profile_helper.blender_uv_rect_to_lut_rect(
                    reg_data["u_offset"],
                    reg_data["v_offset"],
                    reg_data["u_scale"],
                    reg_data["v_scale"],
                    slot_id=slot_id,
                    shadow_mask=sh_mask,
                    rim_mask=rim_mask,
                )
            )
            if slot_id not in slot_materials:
                mat_p = reg_data.get("mat_path")
                if mat_p:
                    matcap_candidates.append(mat_p)
                parsed_mat = vtoon_profile_helper.parse_liltoon_mat_file(
                    mat_p,
                    assets_root=project_dir / "Assets" if (project_dir / "Assets").is_dir() else project_dir,
                )
                slot_materials[slot_id] = vtoon_profile_helper.build_vtoon_slot_from_mat(
                    parsed_mat,
                    slot_type=slot_id,
                    albedo_color_already_baked=True,
                )
        pkg_dir = output_dir.parent / "5_rpf_package" if (output_dir.parent / "5_rpf_package").is_dir() else output_dir
        gtav_dir = project_paths.get_gtav_root_dir()
        sync_targets = [gtav_dir] if (sync_to_game and gtav_dir is not None and gtav_dir.is_dir()) else []
        vtoon_profile_helper.generate_character_vtoon_assets(
            char_id=vtoon_char_id,
            char_name=ped_name,
            slug=safe_prefix,
            package_dir=pkg_dir,
            lut_regions=lut_regions,
            slot_materials=slot_materials,
            mat_paths_for_matcap=matcap_candidates,
            assets_root=project_dir / "Assets" if (project_dir / "Assets").is_dir() else project_dir,
            sync_dirs=sync_targets,
        )

    resampling_enum = getattr(Image, "Resampling", Image)
    lanczos_filter = getattr(resampling_enum, "LANCZOS", Image.LANCZOS)
    flat_tex_size = max(256, min(512, atlas_size))
    spec_img = Image.new("RGBA", (flat_tex_size, flat_tex_size), (0, 0, 0, 255))
    if normal_size > 0:
        target_normal_size = min(atlas_size, normal_size)
        use_flat_normal = (not has_bump_map) or (target_normal_size <= 64)
    else:
        use_flat_normal = True
        target_normal_size = flat_tex_size
    if use_flat_normal:
        normal_canvas = Image.new("RGBA", (target_normal_size, target_normal_size), (128, 128, 255, 255))
    elif normal_canvas.width != target_normal_size:
        normal_canvas = normal_canvas.resize((target_normal_size, target_normal_size), lanczos_filter)

    has_alpha_tile = any(
        str(entry_item.get("alpha_mode", "opaque")) != "opaque"
        for entry_item in tile_entries
    )
    atlas_alpha_min = int(numpy_lib.array(atlas_canvas)[:, :, 3].min())
    diffuse_to_save = (
        atlas_canvas.convert("RGB")
        if (not has_alpha_tile or atlas_alpha_min >= 254)
        else atlas_canvas
    )
    diffuse_to_save.save(atlas_png_path, format="PNG")
    normal_canvas.save(normal_png_path, format="PNG")
    spec_img.save(spec_png_path, format="PNG")

    # Build single-texture external .ytd matching vanilla GTA V streamed ped layout
    # so DiffuseSampler (index 0) always binds the diffuse atlas reliably in-game.
    # Bump/Spec maps remain saved on disk for embedded .ydd shader export.
    build_cmd = npc_registry_helper.build_safe_rage_cmd(
        "textures", "build", "--mips", "1", "-o", str(ytd_path), str(atlas_png_path),
    )
    subprocess.run(build_cmd, stdin=subprocess.DEVNULL, check=True)
    ped_damage_helper.enforce_ytd_rpf7_size_budget(
        project_paths.get_rage_cli(),
        ytd_path,
        [atlas_png_path],
    )
    ped_damage_helper.validate_rpf7_resource_file(ytd_path)

    manifest_data = {
        "ped_name": ped_name,
        "grid_dim": grid_dim,
        "atlas_size": atlas_size,
        "atlas_png": str(atlas_png_path),
        "normal_png": str(normal_png_path),
        "spec_png": str(spec_png_path),
        "ytd_file": str(ytd_path),
        "materials": uv_regions_by_mat,
        "materials_by_path": uv_regions_by_mat_path,
        "textures_by_stem": uv_regions_by_tex_stem,
        "all_parsed_materials": materials_map,
    }
    manifest_path = output_dir / "atlas_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    manifest_data["manifest_path"] = str(manifest_path)
    return manifest_data
