#!/usr/bin/env python3
"""
blendshape_helper.py
====================
Layer 2 of 2 (Public Facade, Classifier & Blender Application).

Provides face-vs-body blendshape classification, `auto | unity | cfg` source
resolution, live Blender shape-key baking, `.cfg` preset exporting, and
full backward-compatible re-exports of `blendshape_unity_yaml_layer`.
"""

import argparse
import codecs
from collections import deque
import json
import os
import re
import struct
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

COMMON_TOOLS_DIR = Path(__file__).resolve().parent
if str(COMMON_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_TOOLS_DIR))

try:
    import unity_scene_helper
except ImportError:
    unity_scene_helper = None

try:
    import vrc2gtav_i18n as project_i18n
except ImportError:
    project_i18n = None

try:
    import vrc2gtav_paths as project_paths
except ImportError:
    project_paths = None

try:
    import error_handler_helper as err_helper
except ImportError:
    err_helper = None


_BODY_KEY_TOKENS: Tuple[str, ...] = (
    "shrink",
    "breast",
    "chest",
    "hip",
    "butt",
    "thigh",
    "calf",
    "waist",
    "shoulder",
    "belly",
    "stomach",
    "muscle",
    "fat",
    "flat",
    "chibi",
    "height",
    "torso",
    "rib",
    "sleeve",
    "skirt",
    "dress",
    "cloth",
    "collar",
    "ribbon",
    "heels",
    "heel",
    "foot",
    "feet",
    "shoe",
    "boot",
    "sock",
    "stocking",
    "glove",
    "finger",
    "arm_",
    "hand_",
    "leg_",
    "toe_",
    "ear_",
    "tail_",
    "body_",
    "bust",
    "hide_",
    "erase_",
    "off_",
)

_FACE_KEY_PREFIXES_OR_TOKENS: Tuple[str, ...] = (
    "vrc.v_",
    "vrc.blink",
    "vrc.lowerlid",
    "vrc.look",
    "eye",
    "lash",
    "lid",
    "brow",
    "mayu",
    "pupil",
    "iris",
    "hitomi",
    "highlight",
    "mouth",
    "kuchi",
    "lip",
    "tongue",
    "shita",
    "sita",
    "teeth",
    "tooth",
    "fang",
    "kiba",
    "wink",
    "smile",
    "grin",
    "laugh",
    "angry",
    "sad",
    "surpris",
    "shock",
    "tear",
    "namida",
    "blush",
    "hoho",
    "cheek",
    "nose",
    "jaw",
    "chin",
    "tareme",
    "tsurime",
    "jitome",
    "omega",
    "mabataki",
    "nagomi",
    "komaru",
    "ikari",
    "odoroki",
    "face_",
    "facial",
    "blink",
    "look_",
    "expr",
    "emo_",
    "mmd_",
)

_FACE_EXACT_TOKENS: Set[str] = {
    "a", "i", "u", "e", "o", "aa", "ch", "dd", "ee", "ff", "ih",
    "kk", "nn", "oh", "ou", "pp", "rr", "ss", "th", "sil", "neko", "o3o",
}


def is_face_blendshape_key(
    mesh_name: str,
    shape_key: str,
    extra_face_keys: Optional[Set[str]] = None,
) -> bool:
    """Classify a blendshape key as facial/expression vs body/clothing/anatomical."""
    key_clean = str(shape_key).strip()
    if extra_face_keys and key_clean in extra_face_keys:
        return True
    key_low = key_clean.lower()
    mesh_low = str(mesh_name).strip().lower()

    if any(body_tok in key_low for body_tok in _BODY_KEY_TOKENS):
        return False
    if key_low in _FACE_EXACT_TOKENS or any(key_low.startswith(tok) or tok in key_low for tok in _FACE_KEY_PREFIXES_OR_TOKENS):
        return True
    if any(mesh_tok in mesh_low for mesh_tok in ("face", "head")) and not any(
        non_face in mesh_low for non_face in ("body", "cloth", "hair", "ear", "tail", "dress", "skirt")
    ):
        return True
    return False



try:
    from blendshape_unity_yaml_layer import (
        COMMON_TOOLS_DIR,
    _FBX_BLENDSHAPE_CACHE,
    MA_SHAPE_CHANGER_GUID,
    _ARRAY_ELEMENT_SIZES,
    _SKIP_SCAN_DIR_NAMES,
    _translate_msg,
    _decode_unity_scalar,
    _strip_object_suffix,
    _format_weight_value,
    extract_fbx_blendshape_names,
    build_fbx_blendshape_lookup,
    collect_fbx_blendshapes,
    merge_missing_fbx_blendshapes,
    load_unity_anim_blendshapes,
    save_blendshapes_cfg,
    load_blendshapes_cfg,
    _read_guid_from_meta,
    _build_guid_lookup,
    _parse_unity_yaml_components,
    _select_avatar_root_target,
    _select_avatar_root_transform,
    _collect_descendant_transforms,
    _collect_prefab_blendshapes,
    extract_unity_scene_blendshapes,
    _read_leading_cfg_comments,
    _coerce_optional_bool,
    is_nipple_blendshape_key,
    )
except ImportError:
    from common_tools.blendshape_unity_yaml_layer import (
        COMMON_TOOLS_DIR,
    _FBX_BLENDSHAPE_CACHE,
    MA_SHAPE_CHANGER_GUID,
    _ARRAY_ELEMENT_SIZES,
    _SKIP_SCAN_DIR_NAMES,
    _translate_msg,
    _decode_unity_scalar,
    _strip_object_suffix,
    _format_weight_value,
    extract_fbx_blendshape_names,
    build_fbx_blendshape_lookup,
    collect_fbx_blendshapes,
    merge_missing_fbx_blendshapes,
    load_unity_anim_blendshapes,
    save_blendshapes_cfg,
    load_blendshapes_cfg,
    _read_guid_from_meta,
    _build_guid_lookup,
    _parse_unity_yaml_components,
    _select_avatar_root_target,
    _select_avatar_root_transform,
    _collect_descendant_transforms,
    _collect_prefab_blendshapes,
    extract_unity_scene_blendshapes,
    _read_leading_cfg_comments,
    _coerce_optional_bool,
    is_nipple_blendshape_key,
    )

VALID_BLENDSHAPE_SOURCES: Tuple[str, ...] = ("auto", "unity", "cfg")

AVATAR_PRESET_RELATIVE_PATHS: Dict[str, str] = {
    "shinano_casual": "configs/shinano_blendshapes.cfg",
    "shinano_er": "configs/shinano_er_blendshapes.cfg",
    "miltina_maid": "configs/miltina_blendshapes.cfg",
}

DEFAULT_PRESET_RELATIVE_PATHS: Dict[str, str] = {
    "franklin": "configs/shinano_blendshapes.cfg",
    "michael": "configs/shinano_er_blendshapes.cfg",
    "trevor": "configs/miltina_blendshapes.cfg",
    **AVATAR_PRESET_RELATIVE_PATHS,
}

# Base Shinano.fbx meshes belonging solely to Shinano Casual (excluded when
# generating Eternal Reunion presets, which supply ER_Shi + Neko Tied Bob).
SHINANO_CASUAL_EXTRA_MESHES: Tuple[str, ...] = (
    "Cloth_under_bra",
    "Cloth_under_shorts",
    "Cloth_dress",
    "Cloth_skirt",
    "Cloth_sweater",
    "Cloth_tights",
    "Hair_back",
    "Hair_bang",
    "Hair_base",
    "Hair_side",
    "Other_ear",
)


def resolve_character_blendshapes(
    char_cfg: Dict[str, Any],
    fbx_paths: Sequence[Union[str, Path]] = (),
    character_hints: Optional[Sequence[str]] = None,
    default_face_mesh: str = "Body",
    unity_assets_root: Optional[Union[str, Path]] = None,
    override_source: Optional[str] = None,
    override_cfg_path: Optional[Union[str, Path]] = None,
    override_unity_scene: Optional[Union[str, Path]] = None,
    override_avatar_name: Optional[str] = None,
    override_face_anim: Optional[Union[str, Path]] = None,
    save_cfg_path: Optional[Union[str, Path]] = None,
    exclude_meshes_when_no_custom_hair: bool = False,
    custom_hair_mesh_names: Sequence[str] = (),
    fill_missing_from_fbx: bool = True,
    fbx_allowed_meshes: Optional[Sequence[str]] = None,
    fbx_excluded_meshes: Sequence[str] = (),
    header_comments: Optional[Sequence[str]] = None,
    import_face: Optional[bool] = None,
    import_body: Optional[bool] = None,
    extra_fbx_paths: Sequence[Union[str, Path]] = (),
) -> Dict[str, Any]:
    """
    Resolve avatar blendshape weights according to `blendshapes_source` (`auto | unity | cfg`),
    separate `import_face` / `import_body` controls, and custom outfit/dress FBXs.

    Mode behavior:
      - When both `import_face` and `import_body` are False: creates/returns all-zero (`0.0`)
        weights across all meshes and channels extracted from avatar + custom dress FBXs.
      - When only one of `import_face` or `import_body` is False: imports the enabled category
        from Unity/anim/cfg and zeros (`0.0`) the disabled category while retaining all FBX keys.
      - `face_anim` keys are merged onto `default_face_mesh` without wiping non-facial keys.
    """
    requested_source = (
        override_source
        or str(char_cfg.get("blendshapes_source", "auto") or "auto")
    ).strip().lower()
    if requested_source not in VALID_BLENDSHAPE_SOURCES:
        raise ValueError(
            f"Unsupported blendshapes_source {requested_source!r}; expected one of {VALID_BLENDSHAPE_SOURCES}"
        )

    do_import_face = _coerce_optional_bool(
        import_face,
        _coerce_optional_bool(char_cfg.get("import_face_blendshapes"), True),
    )
    do_import_body = _coerce_optional_bool(
        import_body,
        _coerce_optional_bool(char_cfg.get("import_body_blendshapes"), True),
    )

    combined_fbx_paths: List[Union[str, Path]] = []
    seen_fbx_keys: Set[str] = set()
    for cand_fbx in list(fbx_paths) + list(extra_fbx_paths):
        if not cand_fbx:
            continue
        norm_key = str(cand_fbx)
        if norm_key not in seen_fbx_keys:
            seen_fbx_keys.add(norm_key)
            combined_fbx_paths.append(cand_fbx)

    effective_cfg = (
        str(override_cfg_path)
        if override_cfg_path
        else str(char_cfg.get("blendshapes_cfg", "") or "")
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
    effective_face_anim = (
        str(override_face_anim)
        if override_face_anim is not None
        else str(char_cfg.get("face_anim", "") or "")
    ).strip()

    if project_paths is not None:
        if effective_cfg:
            effective_cfg = str(project_paths.to_host_path(effective_cfg))
        if effective_scene:
            effective_scene = str(project_paths.to_host_path(effective_scene))
        if effective_face_anim:
            effective_face_anim = str(project_paths.to_host_path(effective_face_anim))
        if save_cfg_path:
            save_cfg_path = project_paths.to_host_path(str(save_cfg_path))

    scene_exists = bool(effective_scene) and Path(effective_scene).is_file()
    cfg_exists = bool(effective_cfg) and Path(effective_cfg).is_file()
    anim_exists = bool(effective_face_anim) and Path(effective_face_anim).is_file()

    if not unity_assets_root and project_paths is not None:
        try:
            unity_assets_root = project_paths.get_vrc_assets_dir()
        except Exception:
            unity_assets_root = None

    use_unity = requested_source == "unity" or (
        requested_source == "auto" and scene_exists
    )

    resolved_meshes: Dict[str, Dict[str, float]] = {}
    resolved_metadata: Dict[str, str] = {}
    root_name = effective_avatar
    source_used = "none"
    anim_face_keys: Set[str] = set()

    def _merge_face_anim_into_mesh() -> None:
        nonlocal anim_face_keys
        if not anim_exists or not do_import_face:
            return
        anim_weights = load_unity_anim_blendshapes(effective_face_anim, include_zero=True)
        if anim_weights:
            anim_face_keys.update(anim_weights.keys())
            target_mesh_key = next(
                (key for key in resolved_meshes if key.lower() == default_face_mesh.lower()),
                default_face_mesh,
            )
            existing_face_map = dict(resolved_meshes.get(target_mesh_key, {}))
            existing_face_map.update(anim_weights)
            resolved_meshes[target_mesh_key] = existing_face_map
            resolved_metadata["face_anim"] = Path(effective_face_anim).name

    if not do_import_face and not do_import_body:
        # User chose neither face nor body blendshape import: build zeroed .cfg from FBXs
        if combined_fbx_paths:
            resolved_meshes = merge_missing_fbx_blendshapes(
                {},
                combined_fbx_paths,
                default_weight=0.0,
                allowed_meshes=fbx_allowed_meshes,
                excluded_meshes=fbx_excluded_meshes,
            )
        if not resolved_meshes and cfg_exists:
            loaded_zero, _ = load_blendshapes_cfg(effective_cfg)
            resolved_meshes = {
                mesh_k: {shape_k: 0.0 for shape_k in shape_v}
                for mesh_k, shape_v in loaded_zero.items()
            }
        source_used = "fbx_zeroed"
        resolved_metadata = {
            "avatar": root_name or "avatar",
            "source": "fbx_zeroed",
            "import_face": "0",
            "import_body": "0",
        }
    else:
        if use_unity and scene_exists:
            unity_data = extract_unity_scene_blendshapes(
                effective_scene,
                avatar_name=effective_avatar or None,
                character_hints=character_hints,
                unity_assets_root=unity_assets_root,
                fbx_paths=combined_fbx_paths,
            )
            if unity_data["loaded"]:
                resolved_meshes = unity_data["mesh_weights"]
                root_name = unity_data["root_name"] or effective_avatar
                source_used = "unity"
                resolved_metadata = {
                    "avatar": root_name,
                    "source": "unity_scene",
                    "unity_scene": Path(effective_scene).name,
                }

        if source_used == "unity":
            _merge_face_anim_into_mesh()
        elif requested_source == "unity":
            if anim_exists and do_import_face:
                _merge_face_anim_into_mesh()
                source_used = "unity"
        elif cfg_exists:
            resolved_meshes, resolved_metadata = load_blendshapes_cfg(effective_cfg)
            source_used = "cfg"
            if (
                do_import_face
                and anim_exists
                and (override_face_anim is not None or default_face_mesh not in resolved_meshes)
            ):
                _merge_face_anim_into_mesh()
        elif anim_exists and do_import_face:
            _merge_face_anim_into_mesh()
            source_used = "anim"

        if fill_missing_from_fbx and combined_fbx_paths:
            resolved_meshes = merge_missing_fbx_blendshapes(
                resolved_meshes,
                combined_fbx_paths,
                default_weight=0.0,
                allowed_meshes=fbx_allowed_meshes,
                excluded_meshes=fbx_excluded_meshes,
            )
            if source_used == "none" and resolved_meshes:
                source_used = "fbx"
                if not resolved_metadata:
                    resolved_metadata = {
                        "avatar": root_name or "avatar",
                        "source": "fbx",
                    }

        if not do_import_face or not do_import_body:
            for mesh_key, shape_dict in resolved_meshes.items():
                for shape_key in list(shape_dict.keys()):
                    is_face = is_face_blendshape_key(
                        mesh_key, shape_key, extra_face_keys=anim_face_keys
                    )
                    if (is_face and not do_import_face) or (not is_face and not do_import_body):
                        shape_dict[shape_key] = 0.0

        if source_used != "cfg":
            for shape_dict in resolved_meshes.values():
                for shape_key in list(shape_dict.keys()):
                    if is_nipple_blendshape_key(shape_key):
                        shape_dict[shape_key] = 0.0

        resolved_metadata["import_face"] = "1" if do_import_face else "0"
        resolved_metadata["import_body"] = "1" if do_import_body else "0"

    if exclude_meshes_when_no_custom_hair and custom_hair_mesh_names:
        hair_name_set = set(custom_hair_mesh_names)
        resolved_meshes = {
            mesh_key: shape_dict
            for mesh_key, shape_dict in resolved_meshes.items()
            if mesh_key not in hair_name_set
        }

    saved_path_str = ""
    if save_cfg_path and resolved_meshes:
        written_path = save_blendshapes_cfg(
            save_cfg_path,
            resolved_meshes,
            metadata=resolved_metadata or {"avatar": root_name or "avatar", "source": source_used},
            header_comments=header_comments,
        )
        saved_path_str = str(written_path)

    return {
        "source_used": source_used,
        "mode_requested": requested_source,
        "import_face": do_import_face,
        "import_body": do_import_body,
        "mesh_weights": resolved_meshes,
        "metadata": resolved_metadata,
        "cfg_path": effective_cfg,
        "unity_scene": effective_scene,
        "root_name": root_name,
        "face_anim": effective_face_anim,
        "saved_cfg_path": saved_path_str,
    }


def apply_blendshapes_to_blender_object(
    mesh_obj: Any,
    shape_weights: Dict[str, float],
    reset_unlisted: bool = True,
    allow_lr_symmetry: bool = False,
) -> Tuple[int, int]:
    """
    Apply a `{shape_name_or_index: weight}` dictionary to a Blender mesh object.

    Supports exact shape key names, optional `_R`/`_L` symmetry expansion when a
    facial key lacks its unsuffixed block, and `index:<N>` 0-based fallback slots
    (`key_blocks[N + 1]`). Returns `(applied_slot_count, active_nonzero_count)`.
    """
    if not mesh_obj or not getattr(mesh_obj.data, "shape_keys", None):
        return 0, 0

    key_blocks = mesh_obj.data.shape_keys.key_blocks
    if reset_unlisted:
        for key_block in key_blocks[1:]:
            key_block.value = 0.0

    applied_count = 0
    active_count = 0

    for shape_key, raw_weight in shape_weights.items():
        weight_val = float(raw_weight)
        if shape_key.startswith("index:"):
            try:
                zero_based_idx = int(shape_key.split(":", 1)[1])
            except ValueError:
                continue
            target_slot = zero_based_idx + 1
            if 1 <= target_slot < len(key_blocks):
                key_blocks[target_slot].value = weight_val
                applied_count += 1
                if abs(weight_val) > 1e-6:
                    active_count += 1
            continue

        direct_block = key_blocks.get(shape_key)
        if direct_block is not None:
            direct_block.value = weight_val
            applied_count += 1
            if abs(weight_val) > 1e-6:
                active_count += 1
        elif allow_lr_symmetry:
            for side_suffix in ("_R", "_L"):
                side_block = key_blocks.get(f"{shape_key}{side_suffix}")
                if side_block is not None:
                    side_block.value = weight_val
                    applied_count += 1
                    if abs(weight_val) > 1e-6:
                        active_count += 1

    return applied_count, active_count


def apply_blendshapes_to_blender_scene(
    bpy_module: Any,
    mesh_weights: Dict[str, Dict[str, float]],
    exclude_meshes: Sequence[str] = (),
    include_meshes: Optional[Sequence[str]] = None,
    lr_symmetry_meshes: Sequence[str] = ("Body",),
    reset_unlisted: bool = True,
) -> Dict[str, Tuple[int, int]]:
    """Apply resolved blendshapes across matching objects in the active Blender scene."""
    excluded_set = set(exclude_meshes)
    included_set = set(include_meshes) if include_meshes is not None else None
    symmetry_set = set(lr_symmetry_meshes)
    summary_map: Dict[str, Tuple[int, int]] = {}

    for mesh_name, shape_dict in mesh_weights.items():
        if mesh_name in excluded_set:
            continue
        if included_set is not None and mesh_name not in included_set:
            continue
        target_obj = bpy_module.data.objects.get(mesh_name)
        if not target_obj or not getattr(target_obj.data, "shape_keys", None):
            continue
        counts = apply_blendshapes_to_blender_object(
            target_obj,
            shape_dict,
            reset_unlisted=reset_unlisted,
            allow_lr_symmetry=mesh_name in symmetry_set,
        )
        summary_map[mesh_name] = counts

    return summary_map


def export_character_blendshapes_to_cfg(
    character_section: str,
    output_cfg_path: Optional[Union[str, Path]] = None,
    unity_scene_override: Optional[Union[str, Path]] = None,
    avatar_name_override: Optional[str] = None,
    preserve_existing_cfg: bool = True,
    fill_missing_from_fbx: bool = True,
) -> Optional[Path]:
    """
    Export or synchronize blendshape presets for an avatar preset (`shinano_casual`,
    `shinano_er`, `miltina_maid`) or protagonist slot into a `.cfg` preset file.

    By default (`preserve_existing_cfg=True`), any existing `.cfg` values remain
    untouched while missing channels from configured FBX models are appended
    with weight `0.0`.
    """
    if project_paths is None:
        raise RuntimeError("vrc2gtav_paths is required to export character blendshapes.")

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
    for fbx_key in (
        "source_fbx",
        "fbx_shinano",
        "fbx_outfit",
        "fbx_watch",
        "fbx_hair",
    ):
        fbx_val = char_cfg.get(fbx_key)
        if fbx_val and fbx_val not in candidate_fbxs:
            candidate_fbxs.append(fbx_val)

    target_out = output_cfg_path or char_cfg.get("blendshapes_cfg")
    if not target_out:
        rel_default = AVATAR_PRESET_RELATIVE_PATHS.get(
            avatar_id
        ) or DEFAULT_PRESET_RELATIVE_PATHS.get(character_section)
        if rel_default:
            target_out = project_paths.get_project_root() / rel_default
    if not target_out:
        raise ValueError(f"No blendshapes_cfg output path configured for {character_section}")

    target_path_obj = Path(project_paths.to_host_path(str(target_out)))
    existing_comments = _read_leading_cfg_comments(target_path_obj)

    hints_by_avatar = {
        "shinano_casual": ["shinano"],
        "shinano_er": ["shinano", "reunion"],
        "miltina_maid": ["milltina", "miltina"],
        "franklin": ["shinano"],
        "michael": ["shinano", "reunion"],
        "trevor": ["milltina", "miltina"],
    }
    excluded_fbx_meshes = (
        SHINANO_CASUAL_EXTRA_MESHES if avatar_id == "shinano_er" else ()
    )
    should_preserve_cfg = (
        preserve_existing_cfg
        and target_path_obj.is_file()
        and unity_scene_override is None
    )

    resolved = resolve_character_blendshapes(
        char_cfg,
        fbx_paths=candidate_fbxs,
        character_hints=hints_by_avatar.get(
            avatar_id, hints_by_avatar.get(character_section, [character_section])
        ),
        override_source="cfg" if should_preserve_cfg else "auto",
        override_cfg_path=target_path_obj if should_preserve_cfg else None,
        override_unity_scene=unity_scene_override,
        override_avatar_name=avatar_name_override,
        save_cfg_path=target_path_obj,
        fill_missing_from_fbx=fill_missing_from_fbx,
        fbx_excluded_meshes=excluded_fbx_meshes,
        header_comments=existing_comments or None,
    )
    return Path(resolved["saved_cfg_path"]) if resolved["saved_cfg_path"] else None


def main() -> int:
    """CLI entrypoint for exporting Unity project & FBX blendshapes into `.cfg` files."""
    if project_i18n is not None:
        project_i18n.set_active_language()

    parser = argparse.ArgumentParser(
        description=_translate_msg(
            "blendshapes.cli_desc",
            "Export Unity scene/prefab, .anim, and FBX blendshapes into portable .cfg presets.",
        )
    )
    parser.add_argument(
        "--character",
        choices=[
            "franklin",
            "michael",
            "trevor",
            "shinano_casual",
            "shinano_er",
            "miltina_maid",
            "all",
        ],
        default="all",
        help="Target protagonist or avatar preset in vrc2gtav.cfg (default: all)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional explicit .cfg output path (for single-character export)",
    )
    parser.add_argument(
        "--unity-scene",
        default=None,
        help="Optional Unity scene path override",
    )
    parser.add_argument(
        "--overwrite-from-unity",
        action="store_true",
        help="Re-read active weights from Unity scene instead of keeping existing .cfg edits",
    )
    parser.add_argument(
        "--lang",
        choices=["auto", "en", "ja", "pt"],
        default="auto",
        help="Output language (auto, en, ja, pt)",
    )
    parsed_args = parser.parse_args()
    if project_i18n is not None:
        project_i18n.set_active_language(parsed_args.lang)

    targets = (
        ["shinano_casual", "shinano_er", "miltina_maid"]
        if parsed_args.character == "all"
        else [parsed_args.character]
    )
    for char_name in targets:
        out_path = parsed_args.output if len(targets) == 1 else None
        saved = export_character_blendshapes_to_cfg(
            char_name,
            output_cfg_path=out_path,
            unity_scene_override=parsed_args.unity_scene,
            preserve_existing_cfg=not parsed_args.overwrite_from_unity,
        )
        if saved:
            print(
                _translate_msg(
                    "blendshapes.exported_cfg",
                    "[Blendshapes] Exported {char} preset to {path}",
                    char=char_name,
                    path=saved,
                )
            )
        else:
            print(
                _translate_msg(
                    "blendshapes.export_skipped",
                    "[Blendshapes] No Unity blendshapes found for {char}; skipped.",
                    char=char_name,
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
