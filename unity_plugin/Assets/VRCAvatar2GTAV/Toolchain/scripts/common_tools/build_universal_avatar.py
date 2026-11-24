#!/usr/bin/env python3
"""
build_universal_avatar.py
=========================
Universal GTA V protagonist mod builder for arbitrary VRChat / Unity avatars
(`.zip`, `.unitypackage`, Unity project folder, or `.unity` scene), featuring:
  - Automatic portable Blender 4.0.2 + Sollumz installation check/download
  - Interactive paginated scene avatar picker (10 options/page + Next button)
  - Native Modular Avatar (NDMF) bake engine supporting arbitrary outfits/dresses
  - Separate Face & Body blendshape import prompts (or zeroed `.cfg` with custom dress shapes)
  - Target protagonist selection (`michael`, `franklin`, `trevor`)
  - Concise default output + `--verbose` timestamped log capture in `<project_root>/logs/`
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

COMMON_TOOLS_DIR = Path(__file__).resolve().parent
if str(COMMON_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_TOOLS_DIR))

import error_handler_helper as err_helper
import avatar_archive_helper
import modular_avatar_helper
import blendshape_helper
import eye_blink_helper
import ped_damage_helper
import physbone_helper
import vrc2gtav_paths as project_paths

VALID_TARGET_CHARACTERS: Tuple[str, ...] = ("michael", "franklin", "trevor")
DEFAULT_CHARACTER_OUTFIT_DIRS: Dict[str, str] = {
    "michael": "player_zero_outfit",
    "franklin": "player_one_outfit",
    "trevor": "player_two_outfit",
}
PHYSBONE_PREFIX_BY_CHARACTER: Dict[str, str] = {
    "michael": "PB_SH",
    "franklin": "PB_FR",
    "trevor": "PB_MT",
}


def _extract_in_blender_args(argv_list: Sequence[str]) -> List[str]:
    """Slice arguments after `--` when launched via Blender `-b -P script.py -- ...`."""
    if "--" in argv_list:
        dash_idx = list(argv_list).index("--")
        return list(argv_list)[dash_idx + 1 :]
    return list(argv_list)[1:]


def _prompt_target_character(
    preset_char: Optional[str] = None,
    *,
    interactive: bool = False,
    input_func=None,
    output_func=None,
) -> str:
    """Resolve target GTA V protagonist slot (`michael`, `franklin`, `trevor`)."""
    if preset_char:
        low_val = preset_char.strip().lower()
        if low_val in VALID_TARGET_CHARACTERS:
            return low_val
        raise ValueError(
            f"Unsupported target character {preset_char!r}; expected one of {VALID_TARGET_CHARACTERS}"
        )

    if not interactive and input_func is None:
        return "michael"
    read_in = input_func if input_func is not None else input
    emit = output_func if output_func is not None else print
    if input_func is None and not sys.stdin.isatty():
        return "michael"

    emit("")
    emit("=== Select GTA V Target Protagonist ===")
    emit("  [1] Michael  (player_zero)")
    emit("  [2] Franklin (player_one)")
    emit("  [3] Trevor   (player_two)")
    try:
        ans = (read_in("Choose [1-3] (default 1 - Michael): ") or "").strip().lower()
    except EOFError:
        return "michael"
    if not ans or ans in ("1", "michael", "player_zero"):
        return "michael"
    if ans in ("2", "franklin", "player_one"):
        return "franklin"
    if ans in ("3", "trevor", "player_two"):
        return "trevor"
    return "michael"


def _select_best_scene_for_source(
    ingested: Dict[str, Any],
    override_scene: Optional[str] = None,
    *,
    interactive: bool = False,
    input_func=None,
    output_func=None,
) -> Optional[Path]:
    """Select the `.unity` scene from ingested project sources."""
    if override_scene:
        cand = Path(project_paths.to_host_path(override_scene))
        if cand.is_file():
            return cand
        raise err_helper.UnityProjectError(
            f"Specified Unity scene not found: {cand}", stage="scene_select"
        )

    scenes: List[Path] = list(ingested.get("scenes", ()))
    if not scenes:
        return None
    if len(scenes) == 1:
        return scenes[0]

    # Prefer scene whose name does not look like a small sample/FX test scene
    preferred = ingested.get("preferred_scene")
    if isinstance(preferred, Path) and preferred.is_file():
        return preferred

    if not interactive and input_func is None:
        return scenes[0]
    read_in = input_func if input_func is not None else input
    emit = output_func if output_func is not None else print
    if input_func is None and not sys.stdin.isatty():
        return scenes[0]

    emit("")
    emit("=== Multiple Unity Scenes Found ===")
    for idx, scene_path in enumerate(scenes[:10], start=1):
        emit(f"  [{idx}] {scene_path.name} ({scene_path.parent.name})")
    try:
        raw_choice = (read_in("Choose scene number (default 1): ") or "").strip()
    except EOFError:
        return scenes[0]
    if raw_choice.isdigit():
        num_val = int(raw_choice)
        if 1 <= num_val <= min(10, len(scenes)):
            return scenes[num_val - 1]
    return scenes[0]


def prepare_universal_avatar_job(
    *,
    avatar_zip: Optional[str] = None,
    unity_project: Optional[str] = None,
    unity_scene: Optional[str] = None,
    avatar_name: Optional[str] = None,
    target_character: Optional[str] = None,
    import_face: Optional[bool] = None,
    import_body: Optional[bool] = None,
    face_anim: Optional[str] = None,
    physbones_marshmallow: bool = False,
    blood_decals: bool = True,
    eye_blink: Optional[bool] = None,
    eye_blink_strength: Optional[float] = None,
    mouth_open_strength: Optional[float] = None,
    out_dir: Optional[str] = None,
    interactive: bool = False,
    auto_download_blender: bool = False,
    blender_exe: Optional[str] = None,
    verbose: bool = False,
    logger: Optional[err_helper.PipelineLogger] = None,
    input_func=None,
    output_func=None,
) -> Dict[str, Any]:
    """
    Prepare all inputs for building an arbitrary avatar or outfit cleanly:
      1. Resolve/ingest `.zip`, `.unitypackage`, Unity project, or `.unity` scene
      2. Discover avatars in the Unity scene and prompt via paginated 10-per-page menu
      3. Resolve Modular Avatar NDMF bake plan (MergeArmature, BoneProxy, ShapeChanger, Sync...)
      4. Ask Face & Body blendshape import flags and write `.cfg` (including custom dress FBXs!)
      5. Optionally check/download Blender 4.0.2 + Sollumz
    """
    proj_root = project_paths.get_project_root()
    active_logger = logger or err_helper.PipelineLogger(
        verbose=verbose,
        avatar_name=avatar_name or "universal",
        stage_name="universal_build",
        project_root=proj_root,
    )

    source_arg = avatar_zip or unity_project or unity_scene
    ingested: Dict[str, Any] = {
        "source_kind": "cfg_default",
        "unity_project_root": None,
        "assets_root": None,
        "scenes": [],
        "fbx_files": [],
        "prefab_files": [],
        "anim_files": [],
    }
    if source_arg:
        with err_helper.guarded_stage("ingest_avatar_source", logger=active_logger):
            host_src = project_paths.to_host_path(source_arg)
            ingested = avatar_archive_helper.ingest_avatar_source(
                host_src, proj_root, logger=active_logger
            )
    else:
        cfg_vrc = project_paths.get_vrc_assets_dir()
        if cfg_vrc is not None and cfg_vrc.is_dir():
            ingested = avatar_archive_helper.ingest_avatar_source(
                cfg_vrc, proj_root, logger=active_logger
            )

    selected_scene = _select_best_scene_for_source(
        ingested,
        override_scene=unity_scene,
        interactive=interactive,
        input_func=input_func,
        output_func=output_func,
    )
    assets_root = ingested.get("assets_root")

    chosen_avatar_name = (avatar_name or "").strip()
    discovered_avatars: List[Dict[str, Any]] = []
    if selected_scene is not None and selected_scene.is_file():
        with err_helper.guarded_stage("discover_scene_avatars", logger=active_logger):
            discovered_avatars = avatar_archive_helper.discover_scene_avatars(
                selected_scene, assets_root
            )
        if not chosen_avatar_name and discovered_avatars:
            if interactive or (input_func is not None):
                picked = avatar_archive_helper.prompt_select_scene_avatar(
                    discovered_avatars,
                    input_func=input_func,
                    output_func=output_func,
                    page_size=10,
                    scene_label=selected_scene.name,
                )
                if picked is None:
                    raise err_helper.UnityProjectError(
                        "Avatar selection cancelled by user.", stage="avatar_select"
                    )
                chosen_avatar_name = str(picked.get("name", ""))
            else:
                active_entry = next(
                    (entry for entry in discovered_avatars if entry.get("active")),
                    discovered_avatars[0],
                )
                chosen_avatar_name = str(active_entry.get("name", ""))

    if chosen_avatar_name:
        active_logger.avatar_name = re.sub(r"[^A-Za-z0-9._-]+", "_", chosen_avatar_name).strip("_") or "avatar"

    chosen_target_char = _prompt_target_character(
        target_character,
        interactive=interactive,
        input_func=input_func,
        output_func=output_func,
    )

    if (interactive or input_func is not None) and (import_face is None or import_body is None):
        use_face, use_body = avatar_archive_helper.prompt_blendshape_import_preferences(
            preset_face=import_face,
            preset_body=import_body,
            input_func=input_func,
            output_func=output_func,
        )
    else:
        use_face = True if import_face is None else bool(import_face)
        use_body = True if import_body is None else bool(import_body)

    ma_plan: Dict[str, Any] = {"loaded": False}
    if selected_scene is not None and selected_scene.is_file():
        with err_helper.guarded_stage("modular_avatar_plan", logger=active_logger):
            ma_plan = modular_avatar_helper.build_modular_avatar_bake_plan(
                selected_scene,
                avatar_name=chosen_avatar_name or None,
                assets_root=assets_root,
                character_hints=[chosen_avatar_name] if chosen_avatar_name else (),
                resolve_materials=True,
                logger=active_logger,
            )

    # Combine base avatar FBXs + discovered MA outfit FBXs + project FBXs
    all_fbx_paths: List[Path] = []
    seen_fbx_set: Set[str] = set()
    for raw_fbx in (
        list(ma_plan.get("base_fbx_paths", ()))
        + list(ma_plan.get("extra_fbx_paths", ()))
        + [str(item) for item in ingested.get("fbx_files", ())]
    ):
        if not raw_fbx:
            continue
        fbx_obj = Path(raw_fbx)
        if fbx_obj.is_file():
            resolved_key = str(fbx_obj.resolve())
            if resolved_key not in seen_fbx_set:
                seen_fbx_set.add(resolved_key)
                all_fbx_paths.append(fbx_obj)

    primary_fbx = _choose_primary_fbx(all_fbx_paths, chosen_avatar_name, ma_plan)
    extra_outfit_fbxs = [fbx_item for fbx_item in all_fbx_paths if fbx_item != primary_fbx]

    # Only pick fallback default facial .anim when no Unity scene exists and clip has non-zero keys
    face_anim_path: Optional[Path] = (
        Path(project_paths.to_host_path(face_anim)) if face_anim else None
    )
    if (face_anim_path is None or not face_anim_path.is_file()) and use_face:
        face_anim_path = None
        if not selected_scene:
            anim_files: List[Path] = list(ingested.get("anim_files", ()))
            for anim_cand in anim_files:
                if anim_cand.name.lower() in ("default_face.anim", "default.anim"):
                    if blendshape_helper.load_unity_anim_blendshapes(anim_cand, include_zero=False):
                        face_anim_path = anim_cand
                        break

    preset_avatar_id = _infer_preset_or_custom_avatar_id(chosen_avatar_name, chosen_target_char)
    char_cfg: Dict[str, Any] = {
        "avatar_id": preset_avatar_id,
        "ped_name": {"michael": "player_zero", "franklin": "player_one", "trevor": "player_two"}.get(
            chosen_target_char, "player_zero"
        ),
        "character_key": chosen_target_char,
        "blendshapes_source": "unity" if selected_scene else "auto",
        "unity_scene": str(selected_scene) if selected_scene else "",
        "unity_avatar_name": chosen_avatar_name,
        "face_anim": str(face_anim_path) if face_anim_path else "",
        "import_face_blendshapes": "1" if use_face else "0",
        "import_body_blendshapes": "1" if use_body else "0",
    }

    work_out_dir = (
        Path(project_paths.to_host_path(out_dir))
        if out_dir
        else (proj_root / "work" / DEFAULT_CHARACTER_OUTFIT_DIRS[chosen_target_char])
    )
    work_out_dir.mkdir(parents=True, exist_ok=True)
    cfg_base_dir = work_out_dir if out_dir else (proj_root / "configs")
    safe_avatar_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", chosen_avatar_name or "universal").strip("_") or "universal"
    save_cfg_file = cfg_base_dir / f"{safe_avatar_slug}_{chosen_target_char}_blendshapes.cfg"

    with err_helper.guarded_stage("resolve_blendshapes", logger=active_logger):
        bs_result = blendshape_helper.resolve_character_blendshapes(
            char_cfg,
            fbx_paths=[primary_fbx] if primary_fbx else all_fbx_paths,
            extra_fbx_paths=extra_outfit_fbxs,
            character_hints=[chosen_avatar_name] if chosen_avatar_name else (),
            unity_assets_root=assets_root,
            override_source="unity" if selected_scene else "auto",
            override_unity_scene=str(selected_scene) if selected_scene else "",
            override_avatar_name=chosen_avatar_name,
            override_face_anim=str(face_anim_path) if (face_anim_path and use_face) else "",
            save_cfg_path=save_cfg_file,
            fill_missing_from_fbx=True,
            import_face=use_face,
            import_body=use_body,
        )

    # Ensure Blender 4.0.2 + Sollumz when requested
    resolved_blender: Optional[Path] = None
    if blender_exe:
        resolved_blender = Path(project_paths.to_host_path(blender_exe))
    else:
        raw_blender_exe = project_paths.get_blender_exe()
        resolved_blender = (
            Path(project_paths.to_host_path(raw_blender_exe)) if raw_blender_exe else None
        )

    if auto_download_blender:
        with err_helper.guarded_stage("ensure_blender", logger=active_logger):
            probe = avatar_archive_helper.inspect_blender_installation(resolved_blender)
            if not probe["exists"] or not probe["is_4_0_series"]:
                resolved_blender = avatar_archive_helper.download_and_install_blender(
                    proj_root, install_sollumz=True, logger=active_logger
                )
            elif not probe["sollumz_installed"] and resolved_blender is not None:
                avatar_archive_helper.install_sollumz_into_blender(
                    resolved_blender, logger=active_logger
                )

    pb_cfg_path = cfg_base_dir / f"{chosen_target_char}_physbones.cfg"
    pb_cfg: Dict[str, Any] = {}
    with err_helper.guarded_stage("resolve_physbones", logger=active_logger):
        pb_cfg = physbone_helper.resolve_character_physbones(
            char_cfg,
            fbx_paths=all_fbx_paths,
            character_hints=[chosen_avatar_name] if chosen_avatar_name else (),
            unity_assets_root=assets_root,
            override_source="unity" if selected_scene else "auto",
            override_unity_scene=str(selected_scene) if selected_scene else "",
            override_avatar_name=chosen_avatar_name,
            override_marshmallow=physbones_marshmallow,
            save_cfg_path=pb_cfg_path if selected_scene else None,
            override_excluded_meshes=ma_plan.get("disabled_meshes", ()) if ma_plan else (),
            override_active_meshes=ma_plan.get("active_meshes", ()) if ma_plan else (),
            prune_orphaned=True,
            verbose=verbose,
        )

    resolved_blink_mode = eye_blink_helper.resolve_effective_eye_blink_mode(
        eye_blink, char_cfg, default="auto"
    )
    resolved_blink_strength = eye_blink_helper.resolve_eye_blink_strength(
        eye_blink_strength,
        char_cfg,
        avatar_id=chosen_avatar_name or "",
        default=1.0,
    )
    resolved_mouth_strength = eye_blink_helper.resolve_mouth_open_strength(
        mouth_open_strength, char_cfg
    )
    body_bs_weights = (bs_result.get("mesh_weights") or {}).get("Body") or {}
    blink_conflict = (
        eye_blink_helper.detect_custom_eye_expression_conflict(body_bs_weights)
        if resolved_blink_mode == "auto"
        else None
    )
    if blink_conflict:
        active_logger.info(
            f"Natural eye blink auto-disabled due to custom eye expression ({blink_conflict})",
            always=True,
        )

    manifest_data = {
        "avatar_name": chosen_avatar_name,
        "target_character": chosen_target_char,
        "scene_path": str(selected_scene) if selected_scene else "",
        "assets_root": str(assets_root) if assets_root else "",
        "primary_fbx": str(primary_fbx) if primary_fbx else "",
        "extra_fbxs": [str(item) for item in extra_outfit_fbxs],
        "import_face_blendshapes": use_face,
        "import_body_blendshapes": use_body,
        "blendshapes_cfg_path": str(save_cfg_file),
        "blendshapes_source_used": bs_result.get("source_used", "none"),
        "blendshapes_mesh_count": len(bs_result.get("mesh_weights", {})),
        "ma_armature_merges": len(ma_plan.get("armature_merges", ())),
        "ma_bone_proxies": len(ma_plan.get("bone_proxies", ())),
        "ma_blendshape_syncs": len(ma_plan.get("blendshape_syncs", ())),
        "ma_shape_changers": len(ma_plan.get("shape_changer_weights", {})),
        "physbones_chains": len(pb_cfg.get("chains", ())),
        "physbones_custom_bones": len(pb_cfg.get("custom_bones", ())),
        "physbones_discarded_chains": len(pb_cfg.get("discarded_chains", ())),
        "physbones_orphaned_removed": len(pb_cfg.get("orphaned_physbones", ())),
        "physbones_priority_report": pb_cfg.get("priority_report", {}),
        "physbones_marshmallow": bool(physbones_marshmallow),
        "blood_decals": bool(blood_decals),
        "blood_decals_shader": ped_damage_helper.resolve_ped_shader_filename(bool(blood_decals)),
        "eye_blink": resolved_blink_mode,
        "eye_blink_strength": resolved_blink_strength,
        "mouth_open_strength": resolved_mouth_strength,
        "eye_blink_conflict": blink_conflict or "",
        "out_dir": str(work_out_dir),
        "blender_exe": str(resolved_blender) if resolved_blender else "",
    }
    manifest_path = work_out_dir / "universal_build_manifest.json"
    err_helper.atomic_write_text(manifest_path, json.dumps(manifest_data, indent=2, ensure_ascii=False))

    active_logger.info(
        f"Prepared universal build for {chosen_avatar_name or 'avatar'} -> {chosen_target_char} "
        f"(MA merges={manifest_data['ma_armature_merges']}, blendshape meshes={manifest_data['blendshapes_mesh_count']}, "
        f"physbones={manifest_data['physbones_chains']}/orphans_removed={manifest_data['physbones_orphaned_removed']}/"
        f"drop={manifest_data['physbones_discarded_chains']}, cfg={save_cfg_file.name})",
        always=True,
    )
    if manifest_data["physbones_orphaned_removed"] > 0:
        orphan_preview = ", ".join(
            f"{item.get('root_bone')} ({item.get('reason')})"
            for item in (pb_cfg.get("orphaned_physbones") or ())[:8]
        )
        active_logger.info(
            f"Removed {manifest_data['physbones_orphaned_removed']} orphaned/unused PhysBone chain(s): {orphan_preview}",
            always=True,
        )
    if manifest_data["physbones_discarded_chains"] > 0:
        active_logger.warning(
            physbone_helper.format_physbone_priority_summary(pb_cfg.get("priority_report"))
        )
    if active_logger.log_path:
        active_logger.debug(f"Verbose log file: {active_logger.log_path}")

    return {
        "manifest": manifest_data,
        "manifest_path": manifest_path,
        "ma_plan": ma_plan,
        "blendshapes_result": bs_result,
        "physbones_result": pb_cfg,
        "discovered_avatars": discovered_avatars,
        "log_path": active_logger.log_path,
    }


def _infer_preset_or_custom_avatar_id(avatar_name: str, target_char: str) -> str:
    """Resolve explicit built-in preset IDs only when clearly matching; otherwise mark custom."""
    low_name = str(avatar_name or "").strip().lower()
    tokens = set(re.split(r"[^a-z0-9]+", low_name))
    if "shinano" in tokens and ("reunion" in tokens or "er" in tokens or "eternal" in tokens):
        return "shinano_er"
    if "shinano" in tokens and "casual" in tokens:
        return "shinano_casual"
    if "miltina" in tokens or "milltina" in tokens:
        return "miltina_maid"
    safe_slug = re.sub(r"[^a-z0-9_]+", "_", low_name).strip("_") or "avatar"
    return f"custom_{target_char}_{safe_slug}"


def _choose_primary_fbx(
    fbx_files: Sequence[Path],
    avatar_name: str,
    ma_plan: Dict[str, Any],
) -> Optional[Path]:
    """Select the primary avatar body FBX among discovered FBX files."""
    base_list = [Path(item) for item in ma_plan.get("base_fbx_paths", ()) if Path(item).is_file()]
    if base_list:
        return base_list[0]
    if not fbx_files:
        return None
    name_tokens = [tok.lower() for tok in re.split(r"[^A-Za-z0-9]+", avatar_name) if len(tok) >= 3]
    for fbx_item in fbx_files:
        stem_low = fbx_item.stem.lower()
        if any(tok in stem_low for tok in name_tokens) and "kisekae" not in stem_low:
            return fbx_item
    non_kisekae = [fbx_item for fbx_item in fbx_files if "kisekae" not in fbx_item.stem.lower()]
    return non_kisekae[0] if non_kisekae else fbx_files[0]


def _run_in_blender_bake(manifest_path: Union[str, Path], ma_plan_path: Optional[Union[str, Path]] = None) -> int:
    """Execute inside Blender 4.0.2 to import FBXs, run Modular Avatar bake, apply blendshapes & scale."""
    import bpy

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    primary_fbx = Path(manifest.get("primary_fbx", ""))
    if not primary_fbx.is_file():
        raise err_helper.BlenderBuildError(
            f"Primary avatar FBX missing for Blender bake: {primary_fbx}",
            stage="blender_import",
        )

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(
        filepath=str(primary_fbx),
        use_anim=False,
        automatic_bone_orientation=True,
    )
    arm_objs = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if not arm_objs:
        raise err_helper.BlenderBuildError(
            f"No armature found after importing {primary_fbx}", stage="blender_import"
        )
    base_arm = arm_objs[0]

    ma_plan: Dict[str, Any] = {}
    if ma_plan_path and Path(ma_plan_path).is_file():
        ma_plan = json.loads(Path(ma_plan_path).read_text(encoding="utf-8"))
    elif manifest.get("scene_path"):
        ma_plan = modular_avatar_helper.build_modular_avatar_bake_plan(
            manifest["scene_path"],
            avatar_name=manifest.get("avatar_name") or None,
            assets_root=manifest.get("assets_root") or None,
            resolve_materials=True,
        )

    if ma_plan.get("loaded"):
        modular_avatar_helper.apply_modular_avatar_plan_in_blender(
            bpy, base_arm, ma_plan, import_extra_fbx=True
        )

    cfg_path = manifest.get("blendshapes_cfg_path")
    if cfg_path and Path(cfg_path).is_file():
        mesh_weights, _meta = blendshape_helper.load_blendshapes_cfg(cfg_path)
        blendshape_helper.apply_blendshapes_to_blender_scene(bpy, mesh_weights)

    ped_damage_helper.enforce_ped_rpf7_poly_budget(
        bpy,
        [obj_item for obj_item in bpy.data.objects if obj_item.type == "MESH"],
        enable_blood_decals=bool(manifest.get("blood_decals", True)),
    )

    out_dir = Path(manifest.get("out_dir", project_paths.get_project_root() / "work"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_blend = out_dir / "universal_ma_baked.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser for universal avatar builder."""
    parser = argparse.ArgumentParser(description="Universal VRChat + Modular Avatar GTA V builder")
    parser.add_argument("--avatar-zip", help="Path to avatar .zip or .unitypackage archive")
    parser.add_argument("--unity-project", help="Path to Unity project root or Assets directory")
    parser.add_argument("--unity-scene", help="Path to specific .unity scene file")
    parser.add_argument("--avatar-name", help="Exact or partial name of avatar in Unity scene")
    parser.add_argument(
        "--target-character",
        choices=list(VALID_TARGET_CHARACTERS),
        help="GTA V protagonist slot (michael, franklin, trevor)",
    )
    parser.add_argument(
        "--target-ped",
        help="Any GTA V NPC ped model (e.g. ig_lamardavis, cs_lamardavis, a_f_y_beach_01)",
    )
    parser.add_argument(
        "--deploy-npc",
        action="store_true",
        help="Patch RPF slots and deploy into GTAV/mods when --target-ped is used",
    )
    parser.add_argument(
        "--force-reextract",
        action="store_true",
        help="Re-extract NPC RPF staging even when cached files already exist",
    )
    parser.add_argument("--interactive", action="store_true", help="Prompt paginated avatar menu & options")
    parser.add_argument("--non-interactive", action="store_true", help="Disable all stdin prompts and auto-select defaults")
    parser.add_argument(
        "--import-face-blendshapes",
        dest="import_face_blendshapes",
        action="store_true",
        default=None,
        help="Import facial blendshapes from Unity into .cfg",
    )
    parser.add_argument(
        "--no-import-face-blendshapes",
        dest="import_face_blendshapes",
        action="store_false",
        help="Zero all facial blendshapes in .cfg",
    )
    parser.add_argument(
        "--import-body-blendshapes",
        dest="import_body_blendshapes",
        action="store_true",
        default=None,
        help="Import body/outfit blendshapes from Unity into .cfg",
    )
    parser.add_argument(
        "--no-import-body-blendshapes",
        dest="import_body_blendshapes",
        action="store_false",
        help="Zero all body/outfit blendshapes in .cfg",
    )
    parser.add_argument(
        "--physbones-marshmallow",
        action="store_true",
        help="Enable optional chest/breast Marshmallow PhysBones",
    )
    parser.add_argument(
        "--blood-decals",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable GTA V ped blood/wound decals (ped.sps + 6-zone UVMap 1)",
    )
    parser.add_argument(
        "--eye-blink",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable optional natural eye blinking via native eyelid bones (default: auto)",
    )
    parser.add_argument(
        "--eye-blink-strength",
        type=float,
        default=None,
        help="Optional peak blink closing factor (e.g. 0.50 Shinano / 0.60 Miltina)",
    )
    parser.add_argument(
        "--mouth-open-strength",
        type=float,
        default=None,
        help="Optional mouth opening / FACIAL_jaw weight scale in [0.0, 1.0] (default: 0.70)",
    )
    parser.add_argument(
        "--face-anim",
        default=None,
        help="Optional Unity .anim file overriding face blendshapes",
    )
    parser.add_argument(
        "--out-dir", help="Output working directory")
    parser.add_argument("--blender-exe", help="Explicit path to Blender 4.0.2 executable")
    parser.add_argument(
        "--auto-download-blender",
        action="store_true",
        help="Auto-download portable Blender 4.0.2 + Sollumz if missing",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Extract, select avatar, resolve MA plan & write .cfg files without running Blender",
    )
    parser.add_argument("--in-blender", action="store_true", help="Run Blender MA bake phase")
    parser.add_argument("--manifest", help="Manifest JSON path when invoking --in-blender")
    parser.add_argument("--ma-plan-json", help="Optional precomputed MA plan JSON for --in-blender")
    parser.add_argument("--verbose", action="store_true", help="Detailed output + timestamped log file")
    return parser


def main(argv_list: Optional[Sequence[str]] = None) -> int:
    """Entrypoint for both external orchestration and Blender-internal execution."""
    raw_argv = _extract_in_blender_args(argv_list or sys.argv)
    args = build_arg_parser().parse_args(raw_argv)

    active_logger = err_helper.PipelineLogger(
        verbose=bool(args.verbose),
        avatar_name=args.avatar_name or "universal",
        stage_name="universal_build",
        project_root=project_paths.get_project_root(),
    )

    try:
        if args.in_blender:
            if not args.manifest:
                raise err_helper.BlenderBuildError("--manifest is required with --in-blender")
            return _run_in_blender_bake(args.manifest, args.ma_plan_json)

        if getattr(args, "target_ped", None):
            import universal_gtav_builder

            src_spec = (
                args.unity_scene
                or args.avatar_zip
                or args.unity_project
            )
            if not src_spec:
                raise ValueError(
                    "--avatar-zip, --unity-project, or --unity-scene is required with --target-ped"
                )
            universal_gtav_builder.build_and_deploy_npc_from_source(
                source_spec=str(src_spec),
                target_ped=str(args.target_ped),
                avatar_name=str(args.avatar_name or ""),
                deploy=bool(getattr(args, "deploy_npc", False)) and not bool(args.prepare_only),
                force_reextract=bool(getattr(args, "force_reextract", False)),
                blood_decals=bool(getattr(args, "blood_decals", True)),
                eye_blink=getattr(args, "eye_blink", None),
                eye_blink_strength=getattr(args, "eye_blink_strength", None),
                mouth_open_strength=getattr(args, "mouth_open_strength", None),
                face_anim=getattr(args, "face_anim", None),
            )
            return 0

        prep_res = prepare_universal_avatar_job(
            avatar_zip=args.avatar_zip,
            unity_project=args.unity_project,
            unity_scene=args.unity_scene,
            avatar_name=args.avatar_name,
            target_character=args.target_character,
            import_face=args.import_face_blendshapes,
            import_body=args.import_body_blendshapes,
            face_anim=getattr(args, "face_anim", None),
            physbones_marshmallow=bool(args.physbones_marshmallow),
            blood_decals=bool(getattr(args, "blood_decals", True)),
            eye_blink=getattr(args, "eye_blink", None),
            eye_blink_strength=getattr(args, "eye_blink_strength", None),
            mouth_open_strength=getattr(args, "mouth_open_strength", None),
            out_dir=args.out_dir,
            interactive=bool(args.interactive) and not bool(args.non_interactive),
            auto_download_blender=bool(args.auto_download_blender),
            blender_exe=args.blender_exe,
            verbose=bool(args.verbose),
            logger=active_logger,
        )

        if args.prepare_only:
            return 0

        manifest = prep_res["manifest"]
        ma_plan_file = Path(manifest["out_dir"]) / "universal_ma_plan.json"
        err_helper.atomic_write_text(
            ma_plan_file, json.dumps(prep_res["ma_plan"], indent=2, ensure_ascii=False)
        )

        blender_bin = manifest.get("blender_exe") or str(
            project_paths.to_host_path(project_paths.get_blender_exe()) or ""
        )
        if not blender_bin or not Path(blender_bin).is_file():
            raise err_helper.AssetDownloadError(
                "Blender 4.0.2 executable not found. Pass --auto-download-blender or run setup_first_run.py.",
                stage="blender_launch",
            )

        use_win_paths = blender_bin.lower().endswith(".exe") and os.name != "nt"
        manifest_arg = (
            project_paths.to_windows_path(str(prep_res["manifest_path"]))
            if use_win_paths
            else str(prep_res["manifest_path"])
        )
        ma_plan_arg = (
            project_paths.to_windows_path(str(ma_plan_file))
            if use_win_paths
            else str(ma_plan_file)
        )
        cmd, custom_env = project_paths.build_blender_command(
            Path(__file__),
            [
                "--in-blender",
                "--manifest",
                manifest_arg,
                "--ma-plan-json",
                ma_plan_arg,
            ],
        )
        if args.blender_exe and cmd:
            cmd[0] = blender_bin
        _ret, _out = err_helper.run_subprocess_safe(
            cmd,
            logger=active_logger,
            stage_name="blender_ma_bake",
            avatar_name=manifest.get("avatar_name", "avatar"),
            env=custom_env,
            timeout_sec=1800.0,
            stream_to_console=bool(args.verbose),
        )
        return 0
    except Exception as exc:
        active_logger.error(f"Universal build failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
