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
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import modular_avatar_helper
    from common_tools import npc_registry_helper
    from common_tools import ped_damage_helper
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
) -> Dict[str, Any]:
    """Extract core diffuse, normal, emission, tint, and alpha settings from a Unity `.mat`."""
    mat_text = mat_path.read_text(encoding="utf-8", errors="replace")
    name_match = re.search(r"^\s*m_Name:\s*(.+)$", mat_text, re.MULTILINE)
    mat_name = name_match.group(1).strip() if name_match else mat_path.stem

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

    main_tex = _tex_prop("_MainTex")
    bump_tex = _tex_prop("_BumpMap")
    emission_tex = _tex_prop("_EmissionMap")
    alpha_mask_tex = _tex_prop("_AlphaMask")
    color_rgba = _color_prop("_Color", (1.0, 1.0, 1.0, 1.0))
    emission_rgba = _color_prop("_EmissionColor", (0.0, 0.0, 0.0, 1.0))
    bump_scale = _float_prop("_BumpScale", 0.5)
    cutoff_val = _float_prop("_Cutoff", 0.5)
    cull_mode = _float_prop("_Cull", 2.0)
    shader_match = re.search(r"m_Shader:\s*\{[^}]*guid:\s*([0-9a-fA-F]{32})", mat_text)
    shader_guid = shader_match.group(1).lower() if shader_match else ""
    kw_match = re.search(r"m_ShaderKeywords:\s*(.*)$", mat_text, re.MULTILINE)
    shader_keywords = kw_match.group(1) if kw_match else ""
    render_queue_match = re.search(r"m_CustomRenderQueue:\s*(-?\d+)", mat_text)
    render_queue = int(render_queue_match.group(1)) if render_queue_match else 2000

    # Treat pure alpha-overlay materials (e.g. Karin_Alpha on Body) as strippable
    # only when named as explicit alpha overlays and not hair transparency masks.
    low_name = mat_name.lower()
    is_body_alpha_overlay = ("alpha" in low_name and "hair" not in low_name)
    trans_shader_guids = {
        "3c79b10c7e0b2784aaa4c2f8dd17d55e",
        "165365ab7100a044ca85fc8c33548a62",
        "0c762f24b85918a49812fc5690619178",
        "b269573b9937b8340b3e9e191a3ba5a8",
        "7171688840c632447b22ec14e2bdef7e",
        "6a77405f7dfdc1447af58854c7f43f39",
        "9cf054060007d784394b8b0bb703e441",
    }
    if (
        not is_body_alpha_overlay
        and (
            shader_guid in trans_shader_guids
            or render_queue >= 2900
            or "_ALPHABLEND_ON" in shader_keywords
            or ("hair" in low_name and ("trans" in low_name or "alpha" in low_name or "bang" in low_name or "front" in low_name))
        )
    ):
        alpha_mode = "transparent"
    elif (
        not is_body_alpha_overlay
        and ("hair" in low_name or alpha_mask_tex or render_queue >= 2400 or "_ALPHATEST_ON" in shader_keywords)
    ):
        alpha_mode = "cutout"
    else:
        alpha_mode = "opaque"

    return {
        "name": mat_name,
        "mat_path": str(mat_path),
        "main_tex": main_tex,
        "bump_tex": bump_tex,
        "emission_tex": emission_tex,
        "alpha_mask_tex": alpha_mask_tex,
        "alpha_mask_scale": _float_prop("_AlphaMaskScale", 1.0),
        "alpha_mask_val": _float_prop("_AlphaMaskValue", 0.0),
        "color_rgba": list(color_rgba),
        "emission_rgba": list(emission_rgba),
        "bump_scale": bump_scale,
        "cutoff": cutoff_val,
        "cull_mode": cull_mode,
        "is_double_sided": cull_mode < 0.5,
        "alpha_mode": alpha_mode,
        "shader_guid": shader_guid,
        "render_queue": render_queue,
        "is_body_alpha_overlay": is_body_alpha_overlay,
    }


def collect_avatar_materials(
    scene_or_prefab: Optional[Path],
    project_dir: Path,
    source_fbx: Path,
    extra_fbxs: Sequence[Path] = (),
) -> Dict[str, Dict[str, Any]]:
    """
    Collect and parse all `.mat` descriptors referenced by the avatar prefab/scene
    or colocated near its FBX files.
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

    if scene_or_prefab and scene_or_prefab.is_file():
        doc_data = modular_avatar_helper.parse_unity_yaml_with_ma(scene_or_prefab)
        for rend_info in doc_data.get("renderers", {}).values():
            for mat_guid in rend_info.get("mat_guids", []):
                _add_mat(guid_map.get(str(mat_guid).lower()))

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
        materials_by_name[parsed_mat["name"]] = parsed_mat
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
    vtoon_char_id: int = 4,
) -> Dict[str, Any]:
    """
    Build a combined 2048x2048 diffuse atlas, normal map, black spec map,
    `<ped_name>_atlas.ytd`, and `atlas_manifest.json` mapping each material name
    to its UV quadrant `(u_offset, v_offset, u_scale, v_scale)`.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    textures_dir = output_dir / "textures"
    textures_dir.mkdir(parents=True, exist_ok=True)

    materials_map = collect_avatar_materials(
        scene_or_prefab, project_dir, source_fbx, extra_fbxs=extra_fbxs
    )

    # Deduplicate materials sharing identical diffuse texture + tint
    tile_entries: List[Dict[str, Any]] = []
    tile_key_to_idx: Dict[Tuple[str, Tuple[float, float, float]], int] = {}
    material_to_tile_idx: Dict[str, int] = {}

    for mat_name in sorted(materials_map.keys()):
        mat_info = materials_map[mat_name]
        if mat_info.get("is_body_alpha_overlay"):
            continue
        main_tex = mat_info.get("main_tex")
        if not main_tex or not Path(main_tex).is_file():
            continue
        tint_rgb = tuple(round(float(val), 3) for val in mat_info["color_rgba"][:3])
        dedup_key = (str(Path(main_tex).resolve()).lower(), tint_rgb)
        if dedup_key not in tile_key_to_idx:
            tile_idx = len(tile_entries)
            tile_key_to_idx[dedup_key] = tile_idx
            tile_entries.append(
                {
                    "main_tex": main_tex,
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

    uv_regions_by_mat: Dict[str, Dict[str, Any]] = {}
    uv_regions_by_tex_stem: Dict[str, Dict[str, Any]] = {}

    for tile_idx, entry_data in enumerate(tile_entries):
        col_idx = tile_idx % grid_dim
        row_idx = tile_idx // grid_dim
        paste_x = col_idx * tile_size
        paste_y = row_idx * tile_size

        entry_mat_path = entry_data.get("mat_path", "")
        tile_img = None
        if entry_mat_path and Path(entry_mat_path).is_file():
            import unity_hair_bake_layer as hair_bake_layer

            assets_anchor = project_dir / "Assets" if (project_dir / "Assets").is_dir() else project_dir
            baked_res = hair_bake_layer.bake_liltoon_mat_to_image(
                entry_mat_path,
                tile_size=(tile_size, tile_size),
                preserve_alpha=(entry_data.get("alpha_mode", "opaque") != "opaque"),
                unity_assets_root=assets_anchor,
            )
            if baked_res is not None:
                tile_img = baked_res[0]
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
                preserve_alpha=(entry_data.get("alpha_mode", "opaque") != "opaque"),
            )
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
            "diffuse_src": entry_data["main_tex"],
            "alpha_mode": entry_data.get("alpha_mode", "opaque"),
            "is_double_sided": bool(entry_data.get("is_double_sided", False)),
            "cull_mode": float(entry_data.get("cull_mode", 2.0)),
            "cutoff": float(entry_data.get("cutoff", 0.5)),
            "mat_path": entry_data.get("mat_path", ""),
        }
        tex_stem_low = Path(entry_data["main_tex"]).stem.lower()
        uv_regions_by_tex_stem[tex_stem_low] = region_spec
        for mat_name in entry_data["materials"]:
            uv_regions_by_mat[mat_name] = region_spec

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
            if "hair" in low_mat and str(reg_data.get("alpha_mode")) == "transparent":
                slot_id = vtoon_profile_helper.SLOT_HAIR_ALPHA
                rim_mask, sh_mask = 0.85, 0.90
            elif "hair" in low_mat:
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
        repo_root = project_paths.get_project_root()
        sync_targets = [
            cand
            for cand in (
                project_paths.get_gtav_root_dir(),
                repo_root / "1_Franklin_Shinano_Casual" / "5_rpf_package",
                repo_root / "2_Michael_Shinano_EternalReunion" / "5_rpf_package",
                repo_root / "3_Trevor_Miltina_Maid" / "5_rpf_package",
            )
            if cand is not None and cand.is_dir()
        ]
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

    spec_img = Image.new("RGBA", (atlas_size, atlas_size), (0, 0, 0, 255))
    atlas_canvas.save(atlas_png_path, format="PNG")
    normal_canvas.save(normal_png_path, format="PNG")
    spec_img.save(spec_png_path, format="PNG")

    build_cmd = npc_registry_helper.build_safe_rage_cmd(
        "textures",
        "build",
        "-o",
        str(ytd_path),
        str(atlas_png_path),
        str(spec_png_path),
        str(normal_png_path),
    )
    subprocess.run(build_cmd, stdin=subprocess.DEVNULL, check=True)
    ped_damage_helper.enforce_ytd_rpf7_size_budget(
        project_paths.get_rage_cli(),
        ytd_path,
        [atlas_png_path, spec_png_path, normal_png_path],
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
