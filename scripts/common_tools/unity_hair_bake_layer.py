#!/usr/bin/env python3
"""
unity_hair_bake_layer.py
========================
Layer 1 of 2 for VRChat / Unity custom hair porting (`unity_hair_helper`).

Owns GUID indexing & caching, Unity `.mat` / lilToon shader property parsing,
UV tile color-grading / edge-dilation compositing, 2x2 sub-quadrant atlas
packing, and `custom_hair_manifest.json` serialization.
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import vrc2gtav_paths as project_paths

# Modular Avatar & VRC script GUIDs verified from Packages/
MA_MERGE_ARMATURE_GUID = "2df373bf91cf30b4bbd495e11cb1a2ec"
MA_BONE_PROXY_GUID = "42581d8044b64899834d3d515ab3a144"
MA_MESH_SETTINGS_GUID = "560fdafd46c74b2db6422fdf0e7f2363"
MA_BLENDSHAPE_SYNC_GUID = "6fd7cab7d93b403280f2f9da978d8a4f"
VRC_PHYSBONE_GUID = "2a2c05204084d904aa4945ccff20d8e5"

CUSTOM_HAIR_MANIFEST_FILENAME = "custom_hair_manifest.json"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".bmp", ".webp")
SKIP_WALK_DIRS = frozenset(
    {
        "library",
        "temp",
        "logs",
        "obj",
        ".git",
        "node_modules",
        "__pycache__",
        "animation",
        "animations",
        "anim",
        "shader",
        "shaders",
        "audio",
        "sounds",
        "sfx",
        "bgm",
        "staging",
        "vrchat",
        "vrcsdk",
        "vrchat examples",
        "liltoon",
        "poiyomi",
        "modular-avatar",
        "modularavatar",
        "vrcfury",
        "textmesh pro",
    }
)
_USED_MATERIAL_TEX_PROPS = frozenset(
    {
        "_MainTex",
        "_BaseMap",
        "_BaseColorMap",
        "_Main2ndTex",
        "_Main3rdTex",
        "_Main2ndBlendMask",
        "_Main3rdBlendMask",
        "_AlphaMask",
        "_BumpMap",
        "_EmissionMap",
    }
)
_PRIMARY_MATERIAL_TEX_PROPS = frozenset({"_MainTex", "_BaseMap", "_BaseColorMap"})
HAIR_KEYWORD_TOKENS = (
    "hair",
    "bob",
    "twin",
    "pony",
    "wig",
    "yurei",
    "lazy",
    "akuma",
    "bang",
    "ahoge",
    "straight",
    "curl",
    "braid",
    "longhair",
    "shorthair",
)

_GUID_CACHE_BY_ROOT: Dict[str, Dict[str, Path]] = {}

_META_GUID_PATTERN = re.compile(r"guid:\s*([0-9a-f]{32})", re.IGNORECASE)
_FILE_ID_HEADER_PATTERN = re.compile(r"^(\d+)\s+&(-?\d+)(?:\s+(stripped))?")
_FLOAT_PATTERN = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
_VEC3_PATTERN = re.compile(
    rf"\{{\s*x:\s*({_FLOAT_PATTERN}),\s*y:\s*({_FLOAT_PATTERN}),\s*z:\s*({_FLOAT_PATTERN})\s*\}}"
)
_VEC4_PATTERN = re.compile(
    rf"\{{\s*x:\s*({_FLOAT_PATTERN}),\s*y:\s*({_FLOAT_PATTERN}),\s*z:\s*({_FLOAT_PATTERN}),\s*w:\s*({_FLOAT_PATTERN})\s*\}}"
)
_COLOR_RGBA_PATTERN = re.compile(
    rf"\{{\s*r:\s*({_FLOAT_PATTERN}),\s*g:\s*({_FLOAT_PATTERN}),\s*b:\s*({_FLOAT_PATTERN}),\s*a:\s*({_FLOAT_PATTERN})\s*\}}"
)
_VEC2_XY_PATTERN = re.compile(
    rf"\{{\s*x:\s*({_FLOAT_PATTERN}),\s*y:\s*({_FLOAT_PATTERN})\s*\}}"
)


def _normalize_guid(raw_guid: Optional[str]) -> str:
    """Return lowercase 32-char GUID string or empty string."""
    if not raw_guid:
        return ""
    return str(raw_guid).strip().lower()


def _extract_guid_from_meta_file(meta_path: Path) -> Optional[str]:
    """Read only the header of a Unity .meta file to extract its asset GUID."""
    try:
        with open(meta_path, "r", encoding="utf-8", errors="ignore") as meta_stream:
            header_chunk = meta_stream.read(256)
    except OSError:
        return None
    guid_match = _META_GUID_PATTERN.search(header_chunk)
    return guid_match.group(1).lower() if guid_match else None


def find_unity_assets_root(
    reference_path: Optional[Union[str, Path]] = None,
) -> Optional[Path]:
    """Locate the enclosing Unity Assets directory or configured unity_assets root."""
    if reference_path:
        resolved_ref = project_paths.to_host_path(reference_path)
        for parent_dir in [resolved_ref] + list(resolved_ref.parents):
            if parent_dir.name.lower() == "assets" and parent_dir.is_dir():
                return parent_dir
    try:
        configured_assets = project_paths.get_vrc_assets_dir()
        if configured_assets.is_dir():
            return configured_assets
    except Exception:
        pass
    return None


def clear_guid_cache() -> None:
    """Clear in-memory and temporary disk GUID resolution caches cleanly."""
    import tempfile

    _GUID_CACHE_BY_ROOT.clear()
    try:
        temp_dir = Path(tempfile.gettempdir())
        for cache_file in temp_dir.glob("vrc2gtav_guid_cache_*.json"):
            try:
                cache_file.unlink()
            except OSError:
                pass
    except OSError:
        pass


def _load_disk_guid_cache(root_dir: Path, max_age_sec: float = 300.0) -> Optional[Dict[str, Path]]:
    """Load persisted Assets GUID index from temp cache when fresh, complete, and matching mtime."""
    import hashlib
    import tempfile
    import time

    root_key = str(root_dir.resolve())
    cache_hash = hashlib.sha1(root_key.encode("utf-8", errors="ignore")).hexdigest()[:16]
    cache_file = Path(tempfile.gettempdir()) / f"vrc2gtav_guid_cache_{cache_hash}.json"
    if not cache_file.is_file():
        return None
    try:
        cur_mtime_ns = root_dir.stat().st_mtime_ns
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        if payload.get("root") != root_key:
            return None
        if payload.get("truncated", False):
            return None
        if int(payload.get("root_mtime_ns", -1)) != int(cur_mtime_ns):
            return None
        saved_ts = float(payload.get("saved_at", 0.0))
        if saved_ts <= 0.0 or (time.time() - saved_ts) > max_age_sec:
            return None
        return {guid_k: Path(asset_str) for guid_k, asset_str in payload.get("entries", {}).items()}
    except Exception:
        return None


def _save_disk_guid_cache(
    root_dir: Path,
    guid_map: Dict[str, Path],
    truncated: bool = False,
) -> None:
    """Persist complete scanned Assets GUID index in temp storage with mtime validation."""
    import hashlib
    import tempfile
    import time

    if truncated:
        return
    root_key = str(root_dir.resolve())
    cache_hash = hashlib.sha1(root_key.encode("utf-8", errors="ignore")).hexdigest()[:16]
    cache_file = Path(tempfile.gettempdir()) / f"vrc2gtav_guid_cache_{cache_hash}.json"
    try:
        root_mtime_ns = root_dir.stat().st_mtime_ns
        payload = {
            "root": root_key,
            "root_mtime_ns": int(root_mtime_ns),
            "saved_at": time.time(),
            "truncated": bool(truncated),
            "entries": {guid_k: str(asset_p) for guid_k, asset_p in guid_map.items()},
        }
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _read_meta_guid_pair(meta_file_path: str) -> Optional[Tuple[str, str]]:
    """Read header of a single .meta file and return (guid, asset_path) if valid."""
    try:
        with open(meta_file_path, "rb") as meta_stream:
            header_chunk = meta_stream.read(256)
    except OSError:
        return None
    text_chunk = header_chunk.decode("utf-8", errors="ignore")
    guid_match = _META_GUID_PATTERN.search(text_chunk)
    if not guid_match:
        return None
    return guid_match.group(1).lower(), meta_file_path[:-5]


def _collect_meta_files_under_dir(scan_dir: str, max_files: int) -> List[str]:
    """Collect .meta paths under one directory subtree while pruning heavy non-asset folders."""
    collected_metas: List[str] = []
    for dirpath, dirnames, filenames in os.walk(scan_dir):
        dirnames[:] = [
            folder_name
            for folder_name in dirnames
            if folder_name.lower() not in SKIP_WALK_DIRS
            and not folder_name.startswith(".")
        ]
        for file_name in filenames:
            if file_name.endswith(".meta"):
                collected_metas.append(os.path.join(dirpath, file_name))
                if len(collected_metas) >= max_files:
                    return collected_metas
    return collected_metas


def _index_meta_tree(root_dir: Path, max_files: int = 80000, use_disk_cache: bool = False) -> Dict[str, Path]:
    """Build a GUID -> asset Path map under root_dir using parallel I/O while pruning heavy folders."""
    import concurrent.futures

    cache_key = str(root_dir.resolve())
    if cache_key in _GUID_CACHE_BY_ROOT:
        return _GUID_CACHE_BY_ROOT[cache_key]

    if use_disk_cache:
        disk_cached = _load_disk_guid_cache(root_dir)
        if disk_cached is not None:
            _GUID_CACHE_BY_ROOT[cache_key] = disk_cached
            return disk_cached

    meta_paths: List[str] = []
    try:
        top_entries = list(root_dir.iterdir())
    except OSError:
        top_entries = []

    top_subdirs = [
        str(entry)
        for entry in top_entries
        if entry.is_dir() and entry.name.lower() not in SKIP_WALK_DIRS and not entry.name.startswith(".")
    ]
    for entry in top_entries:
        if entry.is_file() and entry.name.endswith(".meta"):
            meta_paths.append(str(entry))

    was_truncated = False
    if len(top_subdirs) > 2:
        per_branch_cap = max(2000, max_files // max(1, len(top_subdirs) // 2))
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as walk_executor:
            for branch_metas in walk_executor.map(
                lambda sub_path: _collect_meta_files_under_dir(sub_path, per_branch_cap),
                top_subdirs,
            ):
                if len(branch_metas) >= per_branch_cap:
                    was_truncated = True
                meta_paths.extend(branch_metas)
                if len(meta_paths) >= max_files:
                    meta_paths = meta_paths[:max_files]
                    was_truncated = True
                    break
    else:
        meta_paths.extend(_collect_meta_files_under_dir(str(root_dir), max_files))
        if len(meta_paths) >= max_files:
            was_truncated = True
        meta_paths = meta_paths[:max_files]

    guid_map: Dict[str, Path] = {}
    if meta_paths:
        worker_count = min(24, max(4, len(meta_paths) // 32))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as read_executor:
            for pair_result in read_executor.map(_read_meta_guid_pair, meta_paths, chunksize=32):
                if pair_result is not None:
                    guid_str, asset_str = pair_result
                    guid_map[guid_str] = Path(asset_str)

    _GUID_CACHE_BY_ROOT[cache_key] = guid_map
    if use_disk_cache and guid_map and not was_truncated:
        _save_disk_guid_cache(root_dir, guid_map, truncated=was_truncated)
    return guid_map


def _scan_nearby_meta_files(anchor_path: Path, target_guid: str) -> Optional[Path]:
    """Search nearby parent folders upward without re-walking already indexed child trees."""
    start_dir = anchor_path if anchor_path.is_dir() else anchor_path.parent
    candidate_dirs: List[Path] = []
    cur_dir = start_dir
    for _step in range(5):
        if not cur_dir.is_dir():
            break
        if cur_dir.name.lower() == "assets":
            break
        candidate_dirs.append(cur_dir)
        parent_dir = cur_dir.parent
        if parent_dir == cur_dir or parent_dir.name.lower() == "assets":
            break
        cur_dir = parent_dir

    prev_scanned_child: Optional[Path] = None
    for scan_dir in candidate_dirs:
        scan_key = str(scan_dir.resolve())
        if scan_key in _GUID_CACHE_BY_ROOT:
            found_path = _GUID_CACHE_BY_ROOT[scan_key].get(target_guid)
            if found_path is not None:
                return found_path
            prev_scanned_child = scan_dir
            continue

        if prev_scanned_child is None:
            local_cache = _index_meta_tree(scan_dir, max_files=12000, use_disk_cache=False)
        else:
            local_cache = dict(_GUID_CACHE_BY_ROOT.get(str(prev_scanned_child.resolve()), {}))
            try:
                sibling_dirs = [
                    sub_item
                    for sub_item in scan_dir.iterdir()
                    if sub_item.is_dir()
                    and sub_item.resolve() != prev_scanned_child.resolve()
                    and sub_item.name.lower() not in SKIP_WALK_DIRS
                    and not sub_item.name.startswith(".")
                ]
                for direct_entry in scan_dir.iterdir():
                    if direct_entry.is_file() and direct_entry.name.endswith(".meta"):
                        pair_res = _read_meta_guid_pair(str(direct_entry))
                        if pair_res is not None:
                            local_cache[pair_res[0]] = Path(pair_res[1])
                for sibling_dir in sibling_dirs:
                    local_cache.update(_index_meta_tree(sibling_dir, max_files=8000, use_disk_cache=False))
            except OSError:
                pass
            _GUID_CACHE_BY_ROOT[scan_key] = local_cache

        found_path = local_cache.get(target_guid)
        if found_path is not None:
            return found_path
        prev_scanned_child = scan_dir
    return None


def resolve_unity_guid(
    raw_guid: str,
    local_anchor: Optional[Path] = None,
    unity_assets_root: Optional[Path] = None,
    allow_full_scan: bool = True,
) -> Optional[Path]:
    """Resolve a Unity asset GUID using nearby local folders before project-wide indexing."""
    target_guid = _normalize_guid(raw_guid)
    if not target_guid or set(target_guid) == {"0"}:
        return None

    for cached_map in _GUID_CACHE_BY_ROOT.values():
        cached_path = cached_map.get(target_guid)
        if cached_path is not None and cached_path.exists():
            return cached_path

    if local_anchor is not None:
        local_match = _scan_nearby_meta_files(local_anchor, target_guid)
        if local_match is not None and local_match.exists():
            return local_match

    if not allow_full_scan:
        return None

    assets_root = unity_assets_root or find_unity_assets_root(local_anchor)
    if assets_root is not None and assets_root.is_dir():
        full_map = _index_meta_tree(assets_root, use_disk_cache=True)
        resolved = full_map.get(target_guid)
        if resolved is not None and resolved.exists():
            return resolved
    return None


def _extract_ref_guid(field_text: str) -> str:
    """Extract GUID from a Unity YAML object reference snippet."""
    guid_match = re.search(r"guid:\s*([0-9a-f]{32})", field_text, re.IGNORECASE)
    return guid_match.group(1).lower() if guid_match else ""


def parse_unity_material(
    mat_path: Union[str, Path],
    unity_assets_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Parse a Unity .mat YAML file (lilToon, Poiyomi, or Standard) into textures, colors, floats."""
    resolved_mat = project_paths.to_host_path(mat_path)
    raw_text = resolved_mat.read_text(encoding="utf-8", errors="ignore")

    name_match = re.search(r"^\s*m_Name:\s*(.*)$", raw_text, re.MULTILINE)
    mat_name = name_match.group(1).strip() if name_match else resolved_mat.stem
    shader_match = re.search(r"m_Shader:\s*\{([^\}]*)\}", raw_text)
    shader_guid = _extract_ref_guid(shader_match.group(1)) if shader_match else ""

    tex_envs: Dict[str, Dict[str, Any]] = {}
    tex_section_match = re.search(
        r"m_TexEnvs:(.*?)(?:^\s*m_Ints:|^\s*m_Floats:|^\s*m_Colors:|\Z)",
        raw_text,
        re.DOTALL | re.MULTILINE,
    )
    if tex_section_match:
        tex_entry_pattern = re.compile(
            r"-\s*(_[A-Za-z0-9_]+):\s*\n"
            r"\s*m_Texture:\s*\{([^\}]*)\}\s*\n"
            r"\s*m_Scale:\s*\{([^\}]*)\}\s*\n"
            r"\s*m_Offset:\s*\{([^\}]*)\}",
            re.MULTILINE,
        )
        for tex_match in tex_entry_pattern.finditer(tex_section_match.group(1)):
            prop_name = tex_match.group(1)
            if prop_name not in _USED_MATERIAL_TEX_PROPS:
                continue
            tex_guid = _extract_ref_guid(tex_match.group(2))
            scale_match = _VEC2_XY_PATTERN.search("{" + tex_match.group(3) + "}")
            offset_match = _VEC2_XY_PATTERN.search("{" + tex_match.group(4) + "}")
            tex_path = (
                resolve_unity_guid(
                    tex_guid,
                    resolved_mat,
                    unity_assets_root,
                    allow_full_scan=(prop_name in _PRIMARY_MATERIAL_TEX_PROPS),
                )
                if tex_guid
                else None
            )
            tex_envs[prop_name] = {
                "guid": tex_guid,
                "path": str(tex_path) if tex_path is not None else "",
                "scale": (
                    float(scale_match.group(1)) if scale_match else 1.0,
                    float(scale_match.group(2)) if scale_match else 1.0,
                ),
                "offset": (
                    float(offset_match.group(1)) if offset_match else 0.0,
                    float(offset_match.group(2)) if offset_match else 0.0,
                ),
            }

    floats_dict: Dict[str, float] = {}
    floats_section = re.search(
        r"m_Floats:(.*?)(?:^\s*m_Colors:|^\s*m_Ints:|\Z)",
        raw_text,
        re.DOTALL | re.MULTILINE,
    )
    if floats_section:
        for flt_match in re.finditer(
            rf"-\s*(_[A-Za-z0-9_]+):\s*({_FLOAT_PATTERN})", floats_section.group(1)
        ):
            floats_dict[flt_match.group(1)] = float(flt_match.group(2))

    colors_dict: Dict[str, List[float]] = {}
    colors_section = re.search(r"m_Colors:(.*)", raw_text, re.DOTALL)
    if colors_section:
        for col_match in re.finditer(
            r"-\s*(_[A-Za-z0-9_]+):\s*(\{[^\}]*\})", colors_section.group(1)
        ):
            rgba_match = _COLOR_RGBA_PATTERN.search(col_match.group(2))
            if rgba_match:
                colors_dict[col_match.group(1)] = [
                    float(rgba_match.group(1)),
                    float(rgba_match.group(2)),
                    float(rgba_match.group(3)),
                    float(rgba_match.group(4)),
                ]

    lower_label = f"{resolved_mat.parent.name} {resolved_mat.stem} {mat_name}".lower()
    word_tokens = {tok for tok in re.split(r"[^a-z0-9]+", lower_label) if tok}
    metal_words = {"metal", "metallic", "hairpin", "pin", "pins", "buckle", "velcro"}
    has_metal_word = bool(word_tokens & metal_words)
    metallic_val = max(
        floats_dict.get("_Metallic", 0.0),
        floats_dict.get("_MatCapBlend", 0.0) * 0.35 if has_metal_word else 0.0,
    )
    semantic_tokens = []
    for token in (
        "front",
        "bang",
        "side",
        "back",
        "inner",
        "uv1",
        "uv2",
        "acc",
        "pin",
        "ribbon",
        "metal",
        "halo",
        "roller",
        "post",
        "outer",
    ):
        if token in lower_label or token in str(tex_envs.get("_MainTex", {}).get("path", "")).lower():
            semantic_tokens.append(token)

    return {
        "material_id": str(resolved_mat),
        "name": mat_name,
        "mat_stem": resolved_mat.stem,
        "mat_path": str(resolved_mat),
        "shader_guid": shader_guid,
        "tex_envs": tex_envs,
        "floats": floats_dict,
        "colors": colors_dict,
        "is_metallic": metallic_val >= 0.35 or has_metal_word,
        "semantic_tokens": semantic_tokens,
    }


def make_synthetic_texture_material(
    texture_path: Union[str, Path],
    material_name: str = "CustomHairTex",
) -> Dict[str, Any]:
    """Wrap a standalone diffuse texture path into the unified Unity material dict schema."""
    resolved_tex = project_paths.to_host_path(texture_path)
    return {
        "material_id": str(resolved_tex),
        "name": material_name,
        "mat_stem": resolved_tex.stem,
        "mat_path": "",
        "shader_guid": "",
        "tex_envs": {
            "_MainTex": {
                "guid": "",
                "path": str(resolved_tex),
                "scale": (1.0, 1.0),
                "offset": (0.0, 0.0),
            }
        },
        "floats": {"_BumpScale": 0.4},
        "colors": {"_Color": [1.0, 1.0, 1.0, 1.0]},
        "is_metallic": False,
        "semantic_tokens": [resolved_tex.stem.lower()],
    }


def _normalize_fbx_material_key(raw_name: str) -> str:
    """Normalize a Unity/Blender FBX material slot name (NFKC + unescape + lowercase)."""
    cleaned = str(raw_name or "").strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("'") and cleaned.endswith("'")
    ):
        cleaned = cleaned[1:-1]
    if "\\u" in cleaned:
        cleaned = re.sub(
            r"\\u([0-9a-fA-F]{4})",
            lambda hex_match: chr(int(hex_match.group(1), 16)),
            cleaned,
        )
    cleaned = unicodedata.normalize("NFKC", cleaned)
    cleaned = re.sub(r"\.\d{3}$", "", cleaned.strip())
    return re.sub(r"\s+", " ", cleaned).strip().lower()



def _linear_channel_to_srgb(linear_val: float) -> float:
    """Convert a Unity Linear color scalar to sRGB display factor cleanly."""
    clamped = max(0.0, float(linear_val))
    if clamped >= 1.0:
        return min(1.5, clamped)
    return pow(clamped, 1.0 / 2.2)


def _dilate_rgba_transparent_edges(rgba_array: Any, passes: int = 8) -> Any:
    """Spread valid RGB edge colors into transparent pixels to avoid dark fringes under RAGE DXT5."""
    import numpy as numpy_mod

    work = rgba_array.copy()
    alpha = work[..., 3]
    valid = alpha > 20
    if bool(valid.all()) or not bool(valid.any()):
        return work

    rgb = work[..., :3].astype(numpy_mod.float32)
    filled = valid.copy()
    for _pass in range(passes):
        if bool(filled.all()):
            break
        accum = numpy_mod.zeros_like(rgb)
        counts = numpy_mod.zeros(alpha.shape, dtype=numpy_mod.float32)
        for dy_step, dx_step in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rolled_rgb = numpy_mod.roll(rgb, shift=(dy_step, dx_step), axis=(0, 1))
            rolled_mask = numpy_mod.roll(filled, shift=(dy_step, dx_step), axis=(0, 1)).astype(numpy_mod.float32)
            accum += rolled_rgb * rolled_mask[..., None]
            counts += rolled_mask
        fill_targets = (~filled) & (counts > 0)
        if not bool(fill_targets.any()):
            break
        rgb[fill_targets] = accum[fill_targets] / counts[fill_targets, None]
        filled |= fill_targets

    work[..., :3] = numpy_mod.clip(rgb, 0, 255).astype(numpy_mod.uint8)
    return work


def _apply_uv_tile_transform(
    image_obj: Any,
    uv_scale: Tuple[float, float],
    uv_offset: Tuple[float, float],
) -> Any:
    """Apply Unity material m_Scale and m_Offset wrapping in pixel space cleanly."""
    scale_u, scale_v = float(uv_scale[0]), float(uv_scale[1])
    off_u, off_v = float(uv_offset[0]), float(uv_offset[1])
    if (
        abs(scale_u - 1.0) < 1e-4
        and abs(scale_v - 1.0) < 1e-4
        and abs(off_u) < 1e-4
        and abs(off_v) < 1e-4
    ):
        return image_obj

    import numpy as numpy_mod
    from PIL import Image as pil_image

    src_arr = numpy_mod.array(image_obj)
    height_px, width_px = src_arr.shape[:2]
    grid_y, grid_x = numpy_mod.meshgrid(
        numpy_mod.arange(height_px, dtype=numpy_mod.float32) / max(1, height_px),
        numpy_mod.arange(width_px, dtype=numpy_mod.float32) / max(1, width_px),
        indexing="ij",
    )
    # PIL row 0 is top (Unity v=1), so Unity v_uv = 1.0 - grid_y
    v_unity = 1.0 - grid_y
    mapped_u = (grid_x * scale_u + off_u) % 1.0
    mapped_v = (v_unity * scale_v + off_v) % 1.0
    sample_x = numpy_mod.clip((mapped_u * width_px).astype(numpy_mod.int32), 0, width_px - 1)
    sample_y = numpy_mod.clip(((1.0 - mapped_v) * height_px).astype(numpy_mod.int32), 0, height_px - 1)
    return pil_image.fromarray(src_arr[sample_y, sample_x], mode=image_obj.mode)


def _apply_liltoon_hsvg(
    srgb_rgb_255: Any,
    hsvg_vec: Sequence[float],
    numpy_mod: Any,
) -> Any:
    """Apply lilToon _MainTexHSVG (Hue shift, Saturation, Value, Gamma) in linear space."""
    hue_shift = float(hsvg_vec[0]) if len(hsvg_vec) > 0 else 0.0
    sat_scale = float(hsvg_vec[1]) if len(hsvg_vec) > 1 else 1.0
    val_scale = float(hsvg_vec[2]) if len(hsvg_vec) > 2 else 1.0
    gamma_pow = float(hsvg_vec[3]) if len(hsvg_vec) > 3 else 1.0
    if (
        abs(hue_shift) < 1e-4
        and abs(sat_scale - 1.0) < 1e-4
        and abs(val_scale - 1.0) < 1e-4
        and abs(gamma_pow - 1.0) < 1e-4
    ):
        return srgb_rgb_255

    srgb_unit = numpy_mod.clip(srgb_rgb_255 / 255.0, 0.0, 1.0)
    lin_arr = numpy_mod.power(srgb_unit, 2.2)
    lin_gamma = numpy_mod.power(numpy_mod.abs(lin_arr), max(0.05, gamma_pow))

    chan_r = lin_gamma[..., 0]
    chan_g = lin_gamma[..., 1]
    chan_b = lin_gamma[..., 2]
    max_c = numpy_mod.maximum(numpy_mod.maximum(chan_r, chan_g), chan_b)
    min_c = numpy_mod.minimum(numpy_mod.minimum(chan_r, chan_g), chan_b)
    delta_c = max_c - min_c

    hue_val = numpy_mod.zeros_like(max_c)
    non_gray = delta_c > 1e-7
    mask_r = non_gray & (max_c == chan_r)
    mask_g = non_gray & (max_c == chan_g) & (~mask_r)
    mask_b = non_gray & (~mask_r) & (~mask_g)
    hue_val[mask_r] = (((chan_g[mask_r] - chan_b[mask_r]) / delta_c[mask_r]) % 6.0) / 6.0
    hue_val[mask_g] = (((chan_b[mask_g] - chan_r[mask_g]) / delta_c[mask_g]) + 2.0) / 6.0
    hue_val[mask_b] = (((chan_r[mask_b] - chan_g[mask_b]) / delta_c[mask_b]) + 4.0) / 6.0

    sat_val = numpy_mod.clip((delta_c / (max_c + 1e-7)) * sat_scale, 0.0, 1.0)
    val_chan = numpy_mod.clip(max_c * val_scale, 0.0, 1.0)
    hue_val = (hue_val + hue_shift) % 1.0

    hue_offsets = numpy_mod.stack([hue_val + 1.0, hue_val + (2.0 / 3.0), hue_val + (1.0 / 3.0)], axis=-1)
    hue_ramp = numpy_mod.clip(numpy_mod.abs((hue_offsets % 1.0) * 6.0 - 3.0) - 1.0, 0.0, 1.0)
    out_lin = (
        val_chan[..., None]
        - val_chan[..., None] * sat_val[..., None]
        + val_chan[..., None] * sat_val[..., None] * hue_ramp
    )
    out_srgb = numpy_mod.power(numpy_mod.clip(out_lin, 0.0, 1.0), 1.0 / 2.2)
    return numpy_mod.clip(out_srgb * 255.0, 0.0, 255.0)


def _dilate_black_uv_background_if_detected(
    rgba_img: Any,
    numpy_mod: Any,
    pil_image: Any,
    passes: int = 10,
) -> Any:
    """
    When an opaque UV hair sheet uses pure #000000 canvas padding between islands,
    dilate adjacent strand edge colors outward before downsampling to prevent black halos.
    """
    native_arr = numpy_mod.array(rgba_img)
    if native_arr.ndim != 3 or native_arr.shape[-1] < 4:
        return rgba_img
    alpha_chan = native_arr[..., 3]
    if int(alpha_chan.min()) < 245:
        return rgba_img
    rgb_chan = native_arr[..., :3]
    bright_max = rgb_chan.max(axis=-1)
    corner_max = max(
        int(bright_max[0, 0]),
        int(bright_max[0, -1]),
        int(bright_max[-1, 0]),
        int(bright_max[-1, -1]),
    )
    if corner_max > 6:
        return rgba_img
    black_frac = float((bright_max <= 8).mean())
    bright_frac = float((bright_max >= 40).mean())
    if black_frac < 0.25 or bright_frac < 0.08:
        return rgba_img
    work_arr = native_arr.copy()
    work_arr[bright_max <= 10, 3] = 0
    work_arr = _dilate_rgba_transparent_edges(work_arr, passes=passes)
    work_arr[..., 3] = 255
    return pil_image.fromarray(work_arr, mode="RGBA")


def composite_unity_material_textures(
    mat_info: Dict[str, Any],
    tile_size: Tuple[int, int] = (512, 512),
) -> Tuple[Any, Any, Any]:
    """
    Bake a single Unity hair .mat (lilToon / Standard) into (diffuse_rgba, normal_rgb, spec_rgb)
    calibrated safely for GTA V ped_default.sps.
    """
    import numpy as numpy_mod
    from PIL import Image as pil_image
    import texture_calibration_helper as calibration_helper

    target_w, target_h = int(tile_size[0]), int(tile_size[1])
    tex_envs = mat_info.get("tex_envs", {})
    floats = mat_info.get("floats", {})
    colors = mat_info.get("colors", {})

    def _load_slot_rgba(
        prop_names: Sequence[str],
        default_rgba: Tuple[int, int, int, int],
        dilate_black_bg: bool = False,
    ) -> Tuple[Any, Tuple[float, float], Tuple[float, float]]:
        for prop_key in prop_names:
            entry = tex_envs.get(prop_key)
            if entry and entry.get("path") and os.path.isfile(entry["path"]):
                with pil_image.open(entry["path"]) as raw_opened:
                    opened_img = raw_opened.convert("RGBA")
                if dilate_black_bg:
                    opened_img = _dilate_black_uv_background_if_detected(
                        opened_img, numpy_mod, pil_image, passes=10
                    )
                loaded = opened_img.resize(
                    (target_w, target_h), pil_image.Resampling.LANCZOS
                )
                return loaded, tuple(entry.get("scale", (1.0, 1.0))), tuple(entry.get("offset", (0.0, 0.0)))
        return pil_image.new("RGBA", (target_w, target_h), default_rgba), (1.0, 1.0), (0.0, 0.0)

    main_img, main_scale, main_off = _load_slot_rgba(
        ("_MainTex", "_BaseMap", "_BaseColorMap"),
        (255, 255, 255, 255),
        dilate_black_bg=True,
    )
    main_img = _apply_uv_tile_transform(main_img, main_scale, main_off)
    base_arr = numpy_mod.array(main_img, dtype=numpy_mod.float32)

    raw_main_rgb = base_arr[..., :3]
    hsvg_vec = colors.get("_MainTexHSVG", [0.0, 1.0, 1.0, 1.0])
    toned_rgb = _apply_liltoon_hsvg(raw_main_rgb, hsvg_vec, numpy_mod)
    adj_entry = tex_envs.get("_MainColorAdjustMask")
    if adj_entry and adj_entry.get("path") and os.path.isfile(adj_entry["path"]):
        adj_img, adj_scale, adj_off = _load_slot_rgba(("_MainColorAdjustMask",), (255, 255, 255, 255))
        adj_img = _apply_uv_tile_transform(adj_img, adj_scale, adj_off)
        adj_mask = numpy_mod.array(adj_img, dtype=numpy_mod.float32)[..., 0:1] / 255.0
        toned_rgb = raw_main_rgb * (1.0 - adj_mask) + toned_rgb * adj_mask

    base_color = colors.get("_Color") or colors.get("_BaseColor") or [1.0, 1.0, 1.0, 1.0]
    tint_srgb = numpy_mod.array(
        [
            _linear_channel_to_srgb(base_color[0]),
            _linear_channel_to_srgb(base_color[1]),
            _linear_channel_to_srgb(base_color[2]),
        ],
        dtype=numpy_mod.float32,
    )
    base_rgb = numpy_mod.clip(toned_rgb * tint_srgb[None, None, :], 0.0, 255.0)
    alpha_channel = base_arr[..., 3:4]

    # Composite lilToon 2nd and 3rd layers (_Main2ndTex / _Main3rdTex)
    for idx_str, use_flag, col_key, mask_key, blend_keys in (
        ("2nd", "_UseMain2ndTex", "_Color2nd", "_Main2ndBlendMask", ("_Main2ndTexBlendMode", "_Main2ndTex_BlendMode")),
        ("3rd", "_UseMain3rdTex", "_Color3rd", "_Main3rdBlendMask", ("_Main3rdTexBlendMode", "_Main3rdTex_BlendMode")),
    ):
        if floats.get(use_flag, 0.0) < 0.5:
            continue
        layer_tex_key = f"_Main{idx_str}Tex"
        layer_col = colors.get(col_key, [1.0, 1.0, 1.0, 1.0])
        layer_img, l_scale, l_off = _load_slot_rgba((layer_tex_key,), (255, 255, 255, 255))
        layer_img = _apply_uv_tile_transform(layer_img, l_scale, l_off)
        layer_arr = numpy_mod.array(layer_img, dtype=numpy_mod.float32)

        layer_tint = numpy_mod.array(
            [
                _linear_channel_to_srgb(layer_col[0]),
                _linear_channel_to_srgb(layer_col[1]),
                _linear_channel_to_srgb(layer_col[2]),
            ],
            dtype=numpy_mod.float32,
        )
        layer_rgb = numpy_mod.clip(layer_arr[..., :3] * layer_tint[None, None, :], 0.0, 255.0)
        blend_mask_img, m_scale, m_off = _load_slot_rgba((mask_key,), (255, 255, 255, 255))
        blend_mask_img = _apply_uv_tile_transform(blend_mask_img, m_scale, m_off)
        blend_mask_arr = numpy_mod.array(blend_mask_img, dtype=numpy_mod.float32)[..., 0:1] / 255.0
        layer_alpha = (layer_arr[..., 3:4] / 255.0) * blend_mask_arr * max(0.0, min(1.0, float(layer_col[3])))

        raw_blend_val = 0.0
        for b_key in blend_keys:
            if b_key in floats:
                raw_blend_val = floats[b_key]
                break
        blend_mode = int(round(raw_blend_val))
        if blend_mode == 1:  # Add
            blended = numpy_mod.clip(base_rgb + layer_rgb * layer_alpha, 0.0, 255.0)
        elif blend_mode == 2:  # Screen
            screened = 255.0 - ((255.0 - base_rgb) * (255.0 - layer_rgb) / 255.0)
            blended = base_rgb * (1.0 - layer_alpha) + screened * layer_alpha
        elif blend_mode == 3:  # Multiply
            multed = (base_rgb * layer_rgb) / 255.0
            blended = base_rgb * (1.0 - layer_alpha) + multed * layer_alpha
        else:  # Normal alpha blend
            blended = base_rgb * (1.0 - layer_alpha) + layer_rgb * layer_alpha
        base_rgb = blended

    # Optional Emission tint (subtle so pins/accents stay readable without blowing out)
    if floats.get("_UseEmission", 0.0) >= 0.5:
        em_col = colors.get("_EmissionColor", [0.0, 0.0, 0.0, 0.0])
        em_entry = tex_envs.get("_EmissionMap")
        if em_entry and em_entry.get("path") and os.path.isfile(em_entry["path"]):
            em_img, em_scale, em_off = _load_slot_rgba(("_EmissionMap",), (255, 255, 255, 255))
            em_img = _apply_uv_tile_transform(em_img, em_scale, em_off)
            em_arr = numpy_mod.array(em_img, dtype=numpy_mod.float32)[..., :3]
            em_rgb = em_arr * numpy_mod.array(em_col[:3], dtype=numpy_mod.float32)[None, None, :]
            base_rgb = numpy_mod.clip(base_rgb + em_rgb * 0.25, 0.0, 255.0)

    # Apply _AlphaMask cleanly for edge dilation while emitting opaque RGBA for ped_default.sps
    alpha_mask_entry = tex_envs.get("_AlphaMask")
    if alpha_mask_entry and alpha_mask_entry.get("path") and os.path.isfile(alpha_mask_entry["path"]):
        am_img, am_scale, am_off = _load_slot_rgba(("_AlphaMask",), (255, 255, 255, 255))
        am_img = _apply_uv_tile_transform(am_img, am_scale, am_off)
        am_val = float(floats.get("_AlphaMaskValue", 0.0))
        am_scale_f = float(floats.get("_AlphaMaskScale", 1.0))
        am_r = numpy_mod.array(am_img, dtype=numpy_mod.float32)[..., 0:1] / 255.0
        eff_mask = numpy_mod.clip(am_r * am_scale_f + am_val, 0.0, 1.0)
        alpha_channel = alpha_channel * eff_mask

    rgba_work = numpy_mod.concatenate([base_rgb, alpha_channel], axis=-1).astype(numpy_mod.uint8)
    rgba_dilated = _dilate_rgba_transparent_edges(rgba_work, passes=10)
    rgba_dilated[..., 3] = 255
    diffuse_out = pil_image.fromarray(rgba_dilated, mode="RGBA")

    # Normal tile: use _BumpMap if _UseBumpMap enabled, else generate subtle strand normal
    use_bump = floats.get("_UseBumpMap", 0.0) >= 0.5
    bump_entry = tex_envs.get("_BumpMap")
    if use_bump and bump_entry and bump_entry.get("path") and os.path.isfile(bump_entry["path"]):
        bump_img, b_scale, b_off = _load_slot_rgba(("_BumpMap",), (128, 128, 255, 255))
        bump_img = _apply_uv_tile_transform(bump_img, b_scale, b_off).convert("RGB")
        bump_arr = numpy_mod.array(bump_img, dtype=numpy_mod.float32)
        bump_str = max(0.15, min(1.25, float(floats.get("_BumpScale", 0.6))))
        neutral = numpy_mod.array([128.0, 128.0, 255.0], dtype=numpy_mod.float32)
        mixed_norm = numpy_mod.clip(neutral + (bump_arr - neutral) * bump_str, 0.0, 255.0).astype(numpy_mod.uint8)
        normal_out = pil_image.fromarray(mixed_norm, mode="RGB")
    else:
        normal_out = calibration_helper.generate_directional_hair_normal(diffuse_out.convert("L"), strength=1.15)

    # Specular tile: metallic boost for pins/ribbons/metals, subtle satin highlight for hair strands
    luma = (
        0.299 * rgba_dilated[..., 0].astype(numpy_mod.float32)
        + 0.587 * rgba_dilated[..., 1].astype(numpy_mod.float32)
        + 0.114 * rgba_dilated[..., 2].astype(numpy_mod.float32)
    ) / 255.0
    if mat_info.get("is_metallic"):
        spec_val = numpy_mod.clip(185.0 + 55.0 * luma, 0.0, 255.0).astype(numpy_mod.uint8)
    else:
        spec_val = numpy_mod.clip(28.0 + 44.0 * numpy_mod.power(luma, 1.35), 0.0, 255.0).astype(numpy_mod.uint8)
    spec_rgb = numpy_mod.stack([spec_val, spec_val, spec_val], axis=-1)
    spec_out = pil_image.fromarray(spec_rgb, mode="RGB")

    return diffuse_out, normal_out, spec_out


def compute_quadrant_tile_entries(
    materials: Sequence[Dict[str, Any]],
    quad_size: Tuple[int, int],
    quad_uv_rect: Tuple[float, float, float, float],
    gutter_px: int = 4,
) -> Tuple[List[Dict[str, Any]], int, int, int, int, int, int, int]:
    """Compute grid dimensions and packed UV tile metadata without requiring PIL."""
    quad_w, quad_h = int(quad_size[0]), int(quad_size[1])
    quad_u0, quad_v0, quad_du, quad_dv = quad_uv_rect

    active_mats = list(materials) if materials else [
        {
            "material_id": "default_white",
            "name": "DefaultHair",
            "mat_stem": "DefaultHair",
            "mat_path": "",
            "tex_envs": {},
            "floats": {},
            "colors": {"_Color": [0.85, 0.85, 0.88, 1.0]},
            "is_metallic": False,
            "semantic_tokens": ["default"],
        }
    ]
    mat_total = len(active_mats)
    if mat_total <= 1:
        cols, rows = 1, 1
    elif mat_total == 2:
        cols, rows = 2, 1
    elif mat_total <= 4:
        cols, rows = 2, 2
    elif mat_total <= 6:
        cols, rows = 3, 2
    else:
        cols = math.ceil(math.sqrt(mat_total))
        rows = math.ceil(mat_total / cols)

    cell_w = max(16, quad_w // cols)
    cell_h = max(16, quad_h // rows)
    pad_px = gutter_px if mat_total > 1 else 0
    inner_w = max(8, cell_w - 2 * pad_px)
    inner_h = max(8, cell_h - 2 * pad_px)

    tile_entries: List[Dict[str, Any]] = []
    for mat_idx, mat_item in enumerate(active_mats):
        col_idx = mat_idx % cols
        row_top_idx = mat_idx // cols
        px_x0 = col_idx * cell_w
        px_y0 = row_top_idx * cell_h
        inner_x0 = px_x0 + pad_px
        inner_y0_top = px_y0 + pad_px
        inner_y1_top = inner_y0_top + inner_h
        local_u0 = inner_x0 / float(quad_w)
        local_v0 = (quad_h - inner_y1_top) / float(quad_h)
        local_du = inner_w / float(quad_w)
        local_dv = inner_h / float(quad_h)

        main_tex_info = mat_item.get("tex_envs", {}).get("_MainTex", {})
        main_tex_path = str(main_tex_info.get("path", ""))
        tile_entries.append(
            {
                "tile_index": mat_idx,
                "material_id": str(mat_item.get("material_id", mat_idx)),
                "name": str(mat_item.get("name", "")),
                "mat_stem": str(mat_item.get("mat_stem", "")),
                "tex_stem": Path(main_tex_path).stem if main_tex_path else "",
                "semantic_tokens": list(mat_item.get("semantic_tokens", [])),
                "is_metallic": bool(mat_item.get("is_metallic", False)),
                "uv_rect": [
                    round(quad_u0 + local_u0 * quad_du, 6),
                    round(quad_v0 + local_v0 * quad_dv, 6),
                    round(local_du * quad_du, 6),
                    round(local_dv * quad_dv, 6),
                ],
                "_px_x0": px_x0,
                "_px_y0": px_y0,
                "_mat_item": mat_item,
            }
        )
    return tile_entries, cols, rows, cell_w, cell_h, pad_px, inner_w, inner_h


def build_inmemory_manifest_fallback(
    hair_spec: Dict[str, Any],
    quad_size: Tuple[int, int],
    quad_uv_rect: Tuple[float, float, float, float],
    gutter_px: int = 4,
) -> Dict[str, Any]:
    """Build an in-memory manifest payload inside Blender if custom_hair_manifest.json is absent."""
    raw_tiles = compute_quadrant_tile_entries(
        hair_spec.get("materials", []),
        quad_size=quad_size,
        quad_uv_rect=quad_uv_rect,
        gutter_px=gutter_px,
    )[0]
    cleaned_tiles = [
        {k_name: v_val for k_name, v_val in tile.items() if not k_name.startswith("_")}
        for tile in raw_tiles
    ]
    merged = dict(hair_spec)
    merged["tiles"] = cleaned_tiles
    return merged


def pack_hair_materials_into_quadrant(
    materials: Sequence[Dict[str, Any]],
    quad_size: Tuple[int, int],
    quad_uv_rect: Tuple[float, float, float, float],
    gutter_px: int = 4,
) -> Tuple[Any, Any, Any, List[Dict[str, Any]]]:
    """
    Pack 1..N baked Unity hair materials cleanly into a target atlas quadrant
    with bilinear edge gutter clamping and return quad images + full-atlas UV tile entries.
    """
    import numpy as numpy_mod
    from PIL import Image as pil_image

    quad_w, quad_h = int(quad_size[0]), int(quad_size[1])
    raw_tiles, _cols, _rows, _cell_w, _cell_h, pad_px, inner_w, inner_h = (
        compute_quadrant_tile_entries(
            materials,
            quad_size=(quad_w, quad_h),
            quad_uv_rect=quad_uv_rect,
            gutter_px=gutter_px,
        )
    )

    quad_diff = pil_image.new("RGBA", (quad_w, quad_h), (128, 128, 128, 255))
    quad_norm = pil_image.new("RGB", (quad_w, quad_h), (128, 128, 255))
    quad_spec = pil_image.new("RGB", (quad_w, quad_h), (40, 40, 40))
    tile_entries: List[Dict[str, Any]] = []

    for tile_meta in raw_tiles:
        px_x0 = int(tile_meta["_px_x0"])
        px_y0 = int(tile_meta["_px_y0"])
        mat_item = tile_meta["_mat_item"]

        diff_tile, norm_tile, spec_tile = composite_unity_material_textures(
            mat_item,
            tile_size=(inner_w, inner_h),
        )

        # Pad outer gutter with clamped border pixels to eliminate bilinear seam bleeding
        for dest_canvas, src_tile in (
            (quad_diff, diff_tile),
            (quad_norm, norm_tile),
            (quad_spec, spec_tile),
        ):
            if pad_px > 0:
                tile_arr = numpy_mod.array(src_tile)
                padded_arr = numpy_mod.pad(
                    tile_arr,
                    ((pad_px, pad_px), (pad_px, pad_px), (0, 0)),
                    mode="edge",
                )
                dest_canvas.paste(
                    pil_image.fromarray(padded_arr, mode=src_tile.mode),
                    (px_x0, px_y0),
                )
            else:
                dest_canvas.paste(src_tile, (px_x0, px_y0))

        tile_entries.append(
            {
                k_name: v_val
                for k_name, v_val in tile_meta.items()
                if not k_name.startswith("_")
            }
        )

    return quad_diff, quad_norm, quad_spec, tile_entries


def save_custom_hair_manifest(
    textures_dir: Union[str, Path],
    hair_spec: Dict[str, Any],
    tile_entries: List[Dict[str, Any]],
) -> Path:
    """Persist resolved custom hair spec and packed UV tile map next to compiled atlas PNGs."""
    dest_dir = Path(textures_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dest_dir / CUSTOM_HAIR_MANIFEST_FILENAME
    payload = {
        "mode": hair_spec.get("mode", "default"),
        "is_neko_bob_calibrated": bool(hair_spec.get("is_neko_bob_calibrated", False)),
        "source_input": str(hair_spec.get("source_input", "")),
        "prefab_path": str(hair_spec.get("prefab_path", "")),
        "primary_fbx": str(hair_spec.get("primary_fbx", "")),
        "all_fbxs": list(hair_spec.get("all_fbxs", [])),
        "inactive_meshes": list(hair_spec.get("inactive_meshes", [])),
        "editor_only_meshes": list(hair_spec.get("editor_only_meshes", [])),
        "mesh_root_bones": dict(hair_spec.get("mesh_root_bones", {})),
        "mesh_material_ids": dict(hair_spec.get("mesh_material_ids", {})),
        "fbx_material_map": dict(hair_spec.get("fbx_material_map", {})),
        "variant_slot_groups": list(hair_spec.get("variant_slot_groups", [])),
        "blendshape_weights": dict(hair_spec.get("blendshape_weights", {})),
        "transform_hint": dict(hair_spec.get("transform_hint", {})),
        "tiles": list(tile_entries),
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path


def load_custom_hair_manifest(textures_dir: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """Load custom_hair_manifest.json if present in the character textures directory."""
    manifest_path = Path(textures_dir) / CUSTOM_HAIR_MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def resolve_tile_uv_for_mesh_slot(
    mesh_name: str,
    slot_index: int,
    slot_count: int,
    blender_mat_name: str,
    manifest: Optional[Dict[str, Any]],
    fallback_rect: Tuple[float, float, float, float],
) -> Tuple[float, float, float, float]:
    """
    Match a Blender hair mesh + material slot against packed manifest UV tiles cleanly,
    supporting .fbx.meta material-name maps, SMR mappings, PrefabVariants, and heuristics.
    """
    if not manifest or not manifest.get("tiles"):
        return fallback_rect

    tiles = list(manifest["tiles"])
    if len(tiles) == 1:
        rect_vals = tiles[0].get("uv_rect", list(fallback_rect))
        return (float(rect_vals[0]), float(rect_vals[1]), float(rect_vals[2]), float(rect_vals[3]))

    tile_by_id = {str(tile["material_id"]): tile for tile in tiles}
    lower_mesh = mesh_name.strip().lower()
    lower_mat = blender_mat_name.strip().lower()
    norm_blender_mat = _normalize_fbx_material_key(blender_mat_name)
    blender_mat_tokens = set(re.findall(r"[a-z0-9]+", norm_blender_mat))
    raw_fbx_map = manifest.get("fbx_material_map") or {}
    fbx_mat_map = {
        _normalize_fbx_material_key(map_key): str(map_val)
        for map_key, map_val in raw_fbx_map.items()
    }

    def _pick_tile_from_id_list(candidate_ids: Sequence[str]) -> Optional[Dict[str, Any]]:
        valid_tiles = [
            tile_by_id[str(cand_id)]
            for cand_id in candidate_ids
            if str(cand_id) in tile_by_id
        ]
        if not valid_tiles:
            return None
        distinct_ids = {str(tile_item["material_id"]) for tile_item in valid_tiles}
        if len(distinct_ids) == 1:
            return valid_tiles[0]

        if norm_blender_mat and norm_blender_mat in fbx_mat_map:
            fbx_mapped_id = fbx_mat_map[norm_blender_mat]
            if fbx_mapped_id in distinct_ids and fbx_mapped_id in tile_by_id:
                return tile_by_id[fbx_mapped_id]

        if blender_mat_tokens:
            best_tile_item = None
            best_tile_score = 0
            for cand_idx, cand_tile in enumerate(candidate_ids):
                cand_tile_obj = tile_by_id.get(str(cand_tile))
                if cand_tile_obj is None:
                    continue
                cand_tokens = {
                    str(tok_item).lower()
                    for tok_item in cand_tile_obj.get("semantic_tokens", [])
                    if tok_item
                }
                for field_key in ("mat_stem", "tex_stem", "name"):
                    field_val = str(cand_tile_obj.get(field_key, "")).lower()
                    cand_tokens.update(re.findall(r"[a-z0-9]+", field_val))
                cand_score = 0
                for matched_tok in blender_mat_tokens & cand_tokens:
                    if matched_tok in ("hair", "mat", "tex", "gold", "default"):
                        cand_score += 2
                    else:
                        cand_score += 10
                if cand_idx == slot_index:
                    cand_score += 1
                if cand_score > best_tile_score:
                    best_tile_score = cand_score
                    best_tile_item = cand_tile_obj
            if best_tile_item is not None and best_tile_score >= 10:
                return best_tile_item

        if slot_index < len(candidate_ids):
            return tile_by_id.get(str(candidate_ids[slot_index]))
        return valid_tiles[0]

    # 1. Exact mesh_material_ids lookup from Prefab / .fbx.meta (with semantic & .fbx.meta reorder safety)
    mesh_mat_ids = manifest.get("mesh_material_ids", {})
    direct_ids = mesh_mat_ids.get(lower_mesh) or mesh_mat_ids.get(lower_mat) or mesh_mat_ids.get(norm_blender_mat)
    if direct_ids:
        matched_direct = _pick_tile_from_id_list(direct_ids)
        if matched_direct is not None:
            rect_vals = matched_direct["uv_rect"]
            return (float(rect_vals[0]), float(rect_vals[1]), float(rect_vals[2]), float(rect_vals[3]))

    # 2. Unique slot-count match from PrefabVariant modifications (e.g. 3-slot roller, 2-slot mesh)
    variant_groups = [
        group_ids for group_ids in manifest.get("variant_slot_groups", []) if len(group_ids) == slot_count
    ]
    if slot_count > 1 and len(variant_groups) == 1:
        matched_variant = _pick_tile_from_id_list(variant_groups[0])
        if matched_variant is not None:
            rect_vals = matched_variant["uv_rect"]
            return (float(rect_vals[0]), float(rect_vals[1]), float(rect_vals[2]), float(rect_vals[3]))

    # 2b. Direct .fbx.meta slot-name -> material_id lookup when no SMR override matched
    if norm_blender_mat and norm_blender_mat in fbx_mat_map:
        direct_fbx_tile = tile_by_id.get(fbx_mat_map[norm_blender_mat])
        if direct_fbx_tile is not None:
            rect_vals = direct_fbx_tile["uv_rect"]
            return (float(rect_vals[0]), float(rect_vals[1]), float(rect_vals[2]), float(rect_vals[3]))

    # 3. Token & name similarity score between (mesh_name + blender_mat_name) and each baked tile
    combined_query = f"{lower_mesh} {norm_blender_mat or lower_mat}"
    best_tile = tiles[0]
    best_score = -1
    for tile in tiles:
        score = 0
        tile_tokens = [tok.lower() for tok in tile.get("semantic_tokens", [])]
        for tok in tile_tokens:
            if tok and tok in combined_query:
                score += 4
        if tile.get("mat_stem", "").lower() in combined_query:
            score += 6
        if tile.get("tex_stem", "").lower() and tile.get("tex_stem", "").lower() in combined_query:
            score += 5
        if ("back" in lower_mesh or "uv2" in lower_mat) and "back" in tile_tokens:
            score += 5
        if ("front" in lower_mesh or "side" in lower_mesh or "bang" in lower_mesh or "uv1" in lower_mat) and "front" in tile_tokens:
            score += 5
        if ("pin" in lower_mesh or "metal" in lower_mat or "acc" in lower_mat) and (
            tile.get("is_metallic") or "pin" in tile_tokens or "acc" in tile_tokens
        ):
            score += 5
        if score > best_score:
            best_score = score
            best_tile = tile

    rect_vals = best_tile.get("uv_rect", list(fallback_rect))
    return (float(rect_vals[0]), float(rect_vals[1]), float(rect_vals[2]), float(rect_vals[3]))


def scan_custom_hair_candidates(
    unity_assets_root: Optional[Union[str, Path]] = None,
    max_results: int = 80,
) -> List[Dict[str, str]]:
    """Scan Unity Assets cleanly for installable custom hair .prefab and .fbx packages."""
    root_path = (
        project_paths.to_host_path(unity_assets_root)
        if unity_assets_root
        else find_unity_assets_root()
    )
    if root_path is None or not root_path.is_dir():
        return []

    discovered: List[Dict[str, str]] = []
    seen_paths = set()
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [
            folder_name
            for folder_name in sorted(dirnames)
            if folder_name.lower() not in SKIP_WALK_DIRS
            and not folder_name.startswith(".")
        ]
        rel_dir_lower = os.path.relpath(dirpath, root_path).lower()
        for file_name in sorted(filenames):
            lower_name = file_name.lower()
            if not lower_name.endswith((".prefab", ".fbx")):
                continue
            combined = f"{rel_dir_lower}/{lower_name}"
            if not any(tok in combined for tok in HAIR_KEYWORD_TOKENS):
                continue
            if any(skip_tok in combined for skip_tok in ("gimmick", "collider", "pose", "sample", "dummy")):
                continue
            full_path = Path(dirpath) / file_name
            if str(full_path) in seen_paths:
                continue
            seen_paths.add(str(full_path))
            discovered.append(
                {
                    "path": str(full_path),
                    "relative": os.path.relpath(full_path, root_path),
                    "kind": full_path.suffix.lower().lstrip("."),
                }
            )
            if len(discovered) >= max_results:
                return discovered
    return discovered
