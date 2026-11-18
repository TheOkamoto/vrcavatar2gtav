#!/usr/bin/env python3
"""
setup_first_run.py
==================
First-Run Configurator and Vanilla GTA V Asset Extractor for vrc2gtav.

This repository does not redistribute Rockstar Games copyrighted archives
(.rpf, .yft, vanilla drawables/textures) or paid third-party assets (BOOTH /
Unity / VRChat). On first run, this tool:
  1. Ensures `vrc2gtav.cfg` exists by copying `vrc2gtav.cfg.example`.
  2. Auto-detects or prompts the user for local paths:
       - Legitimate GTA V Legacy installation (`gtav_root`, containing `GTA5.exe`)
       - Unity/VRChat `Assets` directory containing the user's licensed avatars
       - Blender executable (with the Sollumz add-on installed)
       - RAGE CLI (`rage`) and Python executables
  3. Extracts required vanilla base archives from GTA V into `staging/` and
     populates base skeletons (`player_zero.yft`, `player_one.yft`,
     `player_two.yft`) inside each character's `2_blender/` directory.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT_HINT = CURRENT_SCRIPT_DIR.parent.parent
for tools_dir_candidate in (
    CURRENT_SCRIPT_DIR,
    PROJECT_ROOT_HINT / "scripts" / "common_tools",
    PROJECT_ROOT_HINT / "_deploy_tools",
):
    if tools_dir_candidate.is_dir() and str(tools_dir_candidate) not in sys.path:
        sys.path.insert(0, str(tools_dir_candidate))

import blendshape_helper
import error_handler_helper as err_helper
import avatar_archive_helper
import modular_avatar_helper
import vrc2gtav_i18n as project_i18n
import vrc2gtav_paths as project_paths

AVATAR_BLENDSHAPE_PRESETS = {
    "shinano_casual": "shinano_blendshapes.cfg",
    "shinano_er": "shinano_er_blendshapes.cfg",
    "miltina_maid": "miltina_blendshapes.cfg",
}

AVATAR_ANIM_FILES = {
    "shinano_casual": ["ShinanoDefAdultNewv5.anim"],
    "shinano_er": ["ShinanoDefAdultNewv5.anim"],
    "miltina_maid": ["Miltina_close eyes_Base_adult.anim"],
}

AVATAR_SCENE_HINTS = {
    "shinano_casual": ["shinano"],
    "shinano_er": ["shinano"],
    "miltina_maid": ["milltina", "miltina"],
}

DEFAULT_BLENDSHAPE_PRESETS = {
    "franklin": AVATAR_BLENDSHAPE_PRESETS["shinano_casual"],
    "michael": AVATAR_BLENDSHAPE_PRESETS["shinano_er"],
    "trevor": AVATAR_BLENDSHAPE_PRESETS["miltina_maid"],
}

DEFAULT_CHARACTER_ANIM_FILES = {
    "franklin": AVATAR_ANIM_FILES["shinano_casual"],
    "michael": AVATAR_ANIM_FILES["shinano_er"],
    "trevor": AVATAR_ANIM_FILES["miltina_maid"],
}


PLACEHOLDER_MARKERS = (
    "C:/Games/Grand Theft Auto V",
    "C:/VRChatProjects/waifuv4/Assets",
    "C:/Program Files/Blender Foundation/Blender 4.0/blender.exe",
)


def is_valid_gtav_root(candidate_dir: Path) -> bool:
    """Return True if the candidate folder contains GTA5.exe and x64v.rpf."""
    return (
        candidate_dir.is_dir()
        and (candidate_dir / "GTA5.exe").is_file()
        and (candidate_dir / "x64v.rpf").is_file()
    )


def format_path_for_cfg(raw_path_text: str) -> str:
    """
    Normalize a path for portable storage inside vrc2gtav.cfg, converting
    `/mnt/x/...` into `X:/...` so both Windows Blender and Linux/WSL work.
    """
    cleaned_text = str(raw_path_text).strip().strip('"').strip("'")
    if not cleaned_text:
        return cleaned_text
    slash_normalized = cleaned_text.replace("\\", "/")
    wsl_drive_match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", slash_normalized)
    if wsl_drive_match:
        drive_upper = wsl_drive_match.group(1).upper()
        sub_path = wsl_drive_match.group(2)
        return f"{drive_upper}:/{sub_path}"
    return slash_normalized


def detect_gtav_root(current_value: str) -> Optional[Path]:
    """Attempt to locate the GTA V Legacy installation automatically on Windows or WSL."""
    candidate_paths: List[Path] = []
    if current_value and current_value not in PLACEHOLDER_MARKERS:
        try:
            candidate_paths.append(
                project_paths.to_host_path(current_value, project_root_dir=PROJECT_ROOT_HINT)
            )
        except ValueError:
            pass

    env_gtav_path = os.environ.get("GTAV_PATH", "").strip()
    if env_gtav_path:
        try:
            candidate_paths.append(
                project_paths.to_host_path(env_gtav_path, project_root_dir=PROJECT_ROOT_HINT)
            )
        except ValueError:
            pass

    common_suffixes = [
        "GTAV",
        "Games/GTAV",
        "Games/Grand Theft Auto V",
        "Program Files/Rockstar Games/Grand Theft Auto V",
        "Program Files (x86)/Steam/steamapps/common/Grand Theft Auto V",
        "SteamLibrary/steamapps/common/Grand Theft Auto V",
        "Program Files/Epic Games/GTAV",
        "Epic Games/GTAV",
    ]
    for drive_char in ("c", "d", "e", "f", "g"):
        for relative_suffix in common_suffixes:
            if project_paths.is_windows_host():
                candidate_paths.append(Path(f"{drive_char.upper()}:/{relative_suffix}"))
            else:
                candidate_paths.append(Path(f"/mnt/{drive_char}/{relative_suffix}"))

    for candidate_path in candidate_paths:
        if is_valid_gtav_root(candidate_path):
            return candidate_path
    return None


def is_valid_unity_assets_dir(candidate_dir: Path) -> bool:
    """Return True if the candidate folder contains expected VRChat avatar asset subfolders."""
    if not candidate_dir.is_dir():
        return False
    expected_markers = (
        candidate_dir / "Shinano",
        candidate_dir / "DOLOSart",
        candidate_dir / "Vagrant Brand",
    )
    return any(marker_path.exists() for marker_path in expected_markers)


def detect_unity_assets(current_value: str) -> Optional[Path]:
    """Attempt to locate the Unity/VRChat Assets folder automatically."""
    candidate_paths: List[Path] = []
    if current_value and current_value not in PLACEHOLDER_MARKERS:
        try:
            candidate_paths.append(
                project_paths.to_host_path(current_value, project_root_dir=PROJECT_ROOT_HINT)
            )
        except ValueError:
            pass

    env_assets_dir = os.environ.get("VRC_ASSETS_DIR", "").strip()
    if env_assets_dir:
        try:
            candidate_paths.append(
                project_paths.to_host_path(env_assets_dir, project_root_dir=PROJECT_ROOT_HINT)
            )
        except ValueError:
            pass

    candidate_paths.extend(
        [
            PROJECT_ROOT_HINT / "Assets",
            PROJECT_ROOT_HINT.parent / "waifuv4" / "Assets",
        ]
    )
    for drive_char in ("c", "d", "e", "f"):
        if project_paths.is_windows_host():
            candidate_paths.append(Path(f"{drive_char.upper()}:/waifuv4/Assets"))
        else:
            candidate_paths.append(Path(f"/mnt/{drive_char}/waifuv4/Assets"))

    for candidate_path in candidate_paths:
        if is_valid_unity_assets_dir(candidate_path):
            return candidate_path
    return None


def detect_blender_executable(current_value: str) -> Optional[str]:
    """Attempt to locate a Blender executable on the system."""
    if current_value and current_value not in PLACEHOLDER_MARKERS:
        try:
            resolved_current = project_paths.to_host_path(
                current_value, project_root_dir=PROJECT_ROOT_HINT
            )
            if resolved_current.is_file():
                return format_path_for_cfg(str(resolved_current))
        except ValueError:
            pass

    which_blender = shutil.which("blender")
    if which_blender:
        return format_path_for_cfg(which_blender)

    blender_candidates: List[Path] = []
    blender_versions = ("4.0.2", "4.0", "4.1", "4.2", "3.6")
    for drive_char in ("c", "d", "e", "f"):
        prefix_base = (
            Path(f"{drive_char.upper()}:/")
            if project_paths.is_windows_host()
            else Path(f"/mnt/{drive_char}")
        )
        for version_tag in blender_versions:
            blender_candidates.append(
                prefix_base / "waifuv4" / "BlenderTools" / f"blender-{version_tag}-windows-x64" / "blender.exe"
            )
            major_minor = ".".join(version_tag.split(".")[:2])
            blender_candidates.append(
                prefix_base / "Program Files" / "Blender Foundation" / f"Blender {major_minor}" / "blender.exe"
            )

    for candidate_exe in blender_candidates:
        if candidate_exe.is_file():
            return format_path_for_cfg(str(candidate_exe))
    return None


def detect_rage_executable(current_value: str) -> Optional[str]:
    """Attempt to locate the RAGE CLI binary (https://github.com/VIRUXE/rage)."""
    if current_value:
        which_configured = shutil.which(current_value)
        if which_configured:
            return format_path_for_cfg(which_configured)
        if "/" in current_value or "\\" in current_value:
            try:
                resolved_current = project_paths.to_host_path(
                    current_value, project_root_dir=PROJECT_ROOT_HINT
                )
                if resolved_current.is_file():
                    return format_path_for_cfg(str(resolved_current))
            except ValueError:
                pass

    which_rage = shutil.which("rage")
    if which_rage:
        return format_path_for_cfg(which_rage)

    rage_candidates = [
        PROJECT_ROOT_HINT / "tools" / "rage",
        PROJECT_ROOT_HINT / "tools" / "rage.exe",
        Path.home() / ".local" / "bin" / "rage",
        Path.home() / ".cargo" / "bin" / "rage",
        Path.home() / ".gemini" / "antigravity" / "scratch" / "gtav_tools" / "rage",
    ]
    for candidate_bin in rage_candidates:
        if candidate_bin.is_file():
            return format_path_for_cfg(str(candidate_bin))
    return None


def update_cfg_values_in_place(
    config_file_path: Path,
    section_updates: Dict[str, Dict[str, str]],
) -> None:
    """
    Update specific keys inside vrc2gtav.cfg while preserving comments,
    section ordering, and ${section:key} variable references.
    """
    original_lines = config_file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    updated_lines: List[str] = []
    active_section: Optional[str] = None
    remaining_updates: Dict[str, Dict[str, str]] = {
        section_key: dict(section_map) for section_key, section_map in section_updates.items()
    }

    for line_text in original_lines:
        stripped_line = line_text.strip()
        if stripped_line.startswith("[") and stripped_line.endswith("]"):
            if active_section and active_section in remaining_updates and remaining_updates[active_section]:
                for missing_key, missing_val in remaining_updates[active_section].items():
                    updated_lines.append(f"{missing_key} = {missing_val}\n")
                remaining_updates[active_section].clear()
            active_section = stripped_line[1:-1].strip()
            updated_lines.append(line_text)
            continue

        if (
            active_section
            and active_section in remaining_updates
            and "=" in stripped_line
            and not stripped_line.startswith("#")
            and not stripped_line.startswith(";")
        ):
            key_part = line_text.split("=", 1)[0].strip()
            if key_part in remaining_updates[active_section]:
                new_value = remaining_updates[active_section].pop(key_part)
                line_ending = "\r\n" if line_text.endswith("\r\n") else "\n"
                if new_value:
                    updated_lines.append(f"{key_part} = {new_value}{line_ending}")
                else:
                    updated_lines.append(f"{key_part} ={line_ending}")
                continue

        updated_lines.append(line_text)

    if active_section and active_section in remaining_updates and remaining_updates[active_section]:
        for missing_key, missing_val in remaining_updates[active_section].items():
            updated_lines.append(f"{missing_key} = {missing_val}\n")
        remaining_updates[active_section].clear()

    for extra_section, extra_kv in remaining_updates.items():
        if extra_kv:
            if updated_lines and not updated_lines[-1].endswith("\n"):
                updated_lines.append("\n")
            updated_lines.append(f"\n[{extra_section}]\n")
            for extra_key, extra_val in extra_kv.items():
                if extra_val:
                    updated_lines.append(f"{extra_key} = {extra_val}\n")
                else:
                    updated_lines.append(f"{extra_key} =\n")

    config_file_path.write_text("".join(updated_lines), encoding="utf-8")
    project_paths.invalidate_config_cache()


def prompt_path_setting(
    prompt_title: str,
    current_value: str,
    detected_value: Optional[str],
    validator_desc: str,
) -> str:
    """Interactively prompt for a path setting, offering the auto-detected default."""
    suggested_value = detected_value if detected_value else current_value
    print(f"\n  {prompt_title} ({validator_desc})")
    if current_value:
        print(project_i18n.translate("setup.prompt_current", value=current_value))
    if detected_value and detected_value != current_value:
        print(project_i18n.translate("setup.prompt_detected", value=detected_value))
    try:
        entered_text = input(
            project_i18n.translate("setup.prompt_input", suggested=suggested_value)
        ).strip()
    except EOFError:
        entered_text = ""
    chosen_raw = entered_text if entered_text else suggested_value
    return format_path_for_cfg(chosen_raw)


def detect_character_unity_scene(
    unity_assets_path_str: str,
    name_hints: List[str],
    current_value: str,
    character_label: str,
) -> Optional[str]:
    """Optionally locate a matching .unity scene under unity_assets (non-fatal if absent)."""
    if current_value.strip():
        resolved_existing = project_paths.to_host_path(
            current_value.strip(), project_root_dir=PROJECT_ROOT_HINT
        )
        if resolved_existing.is_file():
            return current_value.strip()

    assets_host = project_paths.to_host_path(
        unity_assets_path_str.strip(), project_root_dir=PROJECT_ROOT_HINT
    )
    if not assets_host.is_dir():
        print(project_i18n.translate("setup.unity_scene_optional", char=character_label))
        return None

    candidate_files: List[Path] = []
    skip_dirs = {"library", "temp", "obj", "logs", ".git", "vrchat", "vrcsdk", "liltoon", "poiyomi", "textmesh pro"}
    base_depth = len(assets_host.resolve().parts)
    try:
        for cur_root, dir_names, file_names in os.walk(assets_host):
            cur_depth = len(Path(cur_root).resolve().parts) - base_depth
            if cur_depth >= 4:
                dir_names[:] = []
            else:
                dir_names[:] = [
                    sub_dir
                    for sub_dir in dir_names
                    if sub_dir.lower() not in skip_dirs and not sub_dir.startswith(".")
                ]
            for file_name in file_names:
                if file_name.lower().endswith(".unity"):
                    candidate_files.append(Path(cur_root) / file_name)
    except OSError:
        candidate_files = []

    hint_tokens = [token.lower() for token in name_hints]
    matched_scene: Optional[Path] = None
    for candidate_path in sorted(candidate_files, key=lambda item: item.name.lower()):
        lower_stem = candidate_path.stem.lower()
        if any(token in lower_stem for token in hint_tokens):
            matched_scene = candidate_path
            break

    if matched_scene is None:
        print(project_i18n.translate("setup.unity_scene_optional", char=character_label))
        return None

    print(
        project_i18n.translate(
            "setup.unity_scene_detected", char=character_label, path=matched_scene
        )
    )
    try:
        relative_part = matched_scene.relative_to(assets_host).as_posix()
        return f"${{directories:unity_assets}}/{relative_part}"
    except ValueError:
        return format_path_for_cfg(str(matched_scene))


def detect_character_face_anim(
    unity_assets_path_str: str,
    candidate_names: List[str],
    current_value: str,
) -> Optional[str]:
    """Optionally locate a matching facial .anim preset under unity_assets."""
    if current_value.strip():
        resolved_existing = project_paths.to_host_path(
            current_value.strip(), project_root_dir=PROJECT_ROOT_HINT
        )
        if resolved_existing.is_file():
            return current_value.strip()

    assets_host = project_paths.to_host_path(
        unity_assets_path_str.strip(), project_root_dir=PROJECT_ROOT_HINT
    )
    if not assets_host.is_dir():
        return None

    found_path: Optional[Path] = None
    skip_anim_dirs = {"library", "temp", "obj", "logs", ".git", "vrchat", "vrcsdk", "liltoon", "poiyomi"}
    target_anim_lows = {cand.lower() for cand in candidate_names}
    base_depth = len(assets_host.resolve().parts)
    for candidate_name in candidate_names:
        direct_candidate = assets_host / candidate_name
        if direct_candidate.is_file():
            found_path = direct_candidate
            break
    if found_path is None:
        try:
            for cur_root, dir_names, file_names in os.walk(assets_host):
                cur_depth = len(Path(cur_root).resolve().parts) - base_depth
                if cur_depth >= 5:
                    dir_names[:] = []
                else:
                    dir_names[:] = [
                        sub_dir
                        for sub_dir in dir_names
                        if sub_dir.lower() not in skip_anim_dirs and not sub_dir.startswith(".")
                    ]
                for file_name in file_names:
                    if file_name.lower() in target_anim_lows:
                        found_path = Path(cur_root) / file_name
                        break
                if found_path is not None:
                    break
        except OSError:
            pass

    if found_path is None:
        return None

    try:
        relative_part = found_path.relative_to(assets_host).as_posix()
        return f"${{directories:unity_assets}}/{relative_part}"
    except ValueError:
        return format_path_for_cfg(str(found_path))


def ensure_character_blendshape_presets() -> bool:
    """
    Ensure each character has a readable blendshapes .cfg preset (or Unity scene).
    Never overwrites existing tracked presets under configs/*.cfg.
    """
    project_paths.invalidate_config_cache()
    project_root_dir = project_paths.get_project_root_dir()
    all_ready = True

    for avatar_id in project_paths.list_available_avatars():
        preset_filename = AVATAR_BLENDSHAPE_PRESETS.get(
            avatar_id, f"{avatar_id}_blendshapes.cfg"
        )
        avatar_cfg = project_paths.get_avatar_paths(avatar_id)
        cfg_raw = str(avatar_cfg.get("blendshapes_cfg", "") or "").strip()
        cfg_target = (
            Path(cfg_raw)
            if cfg_raw
            else project_root_dir / "configs" / preset_filename
        )
        if cfg_target.is_file():
            print(
                project_i18n.translate(
                    "setup.blendshapes_cfg_ready",
                    char=avatar_id,
                    path=cfg_target,
                )
            )
            continue

        unity_scene_str = str(avatar_cfg.get("unity_scene", "") or "").strip()
        unity_scene_path = Path(unity_scene_str) if unity_scene_str else None
        if unity_scene_path is not None and unity_scene_path.is_file():
            try:
                exported_cfg = blendshape_helper.export_character_blendshapes_to_cfg(
                    avatar_id,
                    output_cfg_path=cfg_target,
                    unity_scene_override=unity_scene_path,
                )
                if exported_cfg is not None and exported_cfg.is_file():
                    print(
                        project_i18n.translate(
                            "setup.blendshapes_cfg_exported",
                            char=avatar_id,
                            path=exported_cfg,
                        )
                    )
                    continue
            except Exception as err:
                print(
                    f"[WARNING] {avatar_id}: could not export blendshapes .cfg from Unity: {err}"
                )

        print(
            project_i18n.translate(
                "setup.blendshapes_cfg_missing",
                char=avatar_id,
                path=cfg_target,
            )
        )
        all_ready = False

    return all_ready


def configure_vrc2gtav_cfg(
    interactive: bool = True,
    gtav_root_override: Optional[str] = None,
    unity_assets_override: Optional[str] = None,
    blender_override: Optional[str] = None,
    rage_override: Optional[str] = None,
    python_override: Optional[str] = None,
    avatar_zip_override: Optional[str] = None,
    unity_project_override: Optional[str] = None,
    download_blender: Optional[bool] = None,
    avatar_name_override: Optional[str] = None,
    target_character_override: Optional[str] = None,
    import_face_blendshapes: Optional[bool] = None,
    import_body_blendshapes: Optional[bool] = None,
    verbose: bool = False,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> Path:
    """
    Ensure `vrc2gtav.cfg` exists and update its primary executable, directory,
    `.zip`/Unity archive, Blender 4.0.2 + Sollumz, avatar selection, MA outfits,
    and face/body blendshape `.cfg` settings interactively or via parameters.
    """
    active_logger = logger or err_helper.PipelineLogger(
        verbose=verbose,
        avatar_name=avatar_name_override or "first_run",
        stage_name="setup",
        project_root=PROJECT_ROOT_HINT,
    )
    cfg_was_created = not project_paths.has_project_config_file()
    config_file_path = project_paths.ensure_project_config_from_example(PROJECT_ROOT_HINT)
    if cfg_was_created:
        print(project_i18n.translate("setup.created_cfg", path=config_file_path))

    project_paths.invalidate_config_cache()
    config_parser = project_paths.load_project_config(force_reload=True)

    ingested_source: Optional[Dict[str, object]] = None
    source_override = avatar_zip_override or unity_project_override
    if source_override:
        with err_helper.guarded_stage("ingest_avatar_source", logger=active_logger):
            host_src = project_paths.to_host_path(
                source_override, project_root_dir=PROJECT_ROOT_HINT
            )
            ingested_source = avatar_archive_helper.ingest_avatar_source(
                host_src, PROJECT_ROOT_HINT, logger=active_logger
            )
            if not unity_assets_override and ingested_source.get("assets_root"):
                unity_assets_override = str(ingested_source["assets_root"])

    current_gtav_root = config_parser.get("directories", "gtav_root", fallback="")
    current_unity_assets = config_parser.get("directories", "unity_assets", fallback="")
    current_blender = config_parser.get("executables", "blender", fallback="")
    current_rage = config_parser.get("executables", "rage", fallback="")
    current_python = config_parser.get("executables", "python", fallback="")

    detected_gtav = detect_gtav_root(current_gtav_root)
    detected_assets = detect_unity_assets(current_unity_assets)
    detected_blender = detect_blender_executable(current_blender)
    detected_rage = detect_rage_executable(current_rage)

    detected_gtav_str = format_path_for_cfg(str(detected_gtav)) if detected_gtav else None
    detected_assets_str = format_path_for_cfg(str(detected_assets)) if detected_assets else None

    if gtav_root_override:
        chosen_gtav_root = format_path_for_cfg(gtav_root_override)
    elif interactive:
        chosen_gtav_root = prompt_path_setting(
            project_i18n.translate("setup.step_gtav_title"),
            current_gtav_root,
            detected_gtav_str,
            project_i18n.translate("setup.step_gtav_desc"),
        )
    else:
        chosen_gtav_root = detected_gtav_str or current_gtav_root

    if unity_assets_override:
        chosen_unity_assets = format_path_for_cfg(unity_assets_override)
    elif interactive:
        chosen_unity_assets = prompt_path_setting(
            project_i18n.translate("setup.step_assets_title"),
            current_unity_assets,
            detected_assets_str,
            project_i18n.translate("setup.step_assets_desc"),
        )
        # Allow user to paste a .zip / .unitypackage directly into Unity Assets prompt
        raw_assets_candidate = Path(
            project_paths.to_host_path(chosen_unity_assets, project_root_dir=PROJECT_ROOT_HINT)
        )
        if raw_assets_candidate.is_file() and raw_assets_candidate.suffix.lower() in (
            ".zip",
            ".unitypackage",
            ".unity",
        ):
            ingested_source = avatar_archive_helper.ingest_avatar_source(
                raw_assets_candidate, PROJECT_ROOT_HINT, logger=active_logger
            )
            if ingested_source.get("assets_root"):
                chosen_unity_assets = format_path_for_cfg(str(ingested_source["assets_root"]))
    else:
        chosen_unity_assets = detected_assets_str or current_unity_assets

    if blender_override:
        chosen_blender = format_path_for_cfg(blender_override)
    elif interactive:
        chosen_blender = prompt_path_setting(
            project_i18n.translate("setup.step_blender_title"),
            current_blender,
            detected_blender,
            project_i18n.translate("setup.step_blender_desc"),
        )
    else:
        chosen_blender = detected_blender or current_blender

    # Verify Blender 4.0.2 + Sollumz and auto-download if missing or requested
    resolved_blender_path = (
        project_paths.to_host_path(chosen_blender, project_root_dir=PROJECT_ROOT_HINT)
        if chosen_blender and chosen_blender not in PLACEHOLDER_MARKERS
        else None
    )
    blender_probe = avatar_archive_helper.inspect_blender_installation(resolved_blender_path)
    needs_blender_dl = (not blender_probe["exists"]) or (not blender_probe["is_4_0_series"])
    needs_sollumz_dl = blender_probe["exists"] and blender_probe["is_4_0_series"] and (
        not blender_probe["sollumz_installed"]
    )
    if needs_blender_dl or needs_sollumz_dl:
        should_download = download_blender
        if should_download is None and interactive:
            prompt_txt = (
                project_i18n.translate("setup.prompt_download_blender")
                if needs_blender_dl
                else project_i18n.translate("setup.prompt_download_sollumz")
            )
            try:
                dl_ans = input(f"  {prompt_txt} [Y/n]: ").strip()
            except EOFError:
                dl_ans = "y"
            should_download = project_i18n.is_affirmative_answer(dl_ans, default_yes=True)
        if should_download:
            with err_helper.guarded_stage("download_blender", logger=active_logger):
                if needs_blender_dl:
                    dl_exe = avatar_archive_helper.download_and_install_blender(
                        PROJECT_ROOT_HINT, install_sollumz=True, logger=active_logger
                    )
                    chosen_blender = format_path_for_cfg(str(dl_exe))
                elif needs_sollumz_dl and resolved_blender_path is not None:
                    avatar_archive_helper.install_sollumz_into_blender(
                        resolved_blender_path, logger=active_logger
                    )

    if rage_override:
        chosen_rage = format_path_for_cfg(rage_override)
    elif interactive:
        chosen_rage = prompt_path_setting(
            project_i18n.translate("setup.step_rage_title"),
            current_rage,
            detected_rage,
            project_i18n.translate("setup.step_rage_desc"),
        )
    else:
        chosen_rage = detected_rage or current_rage

    if python_override:
        chosen_python = format_path_for_cfg(python_override)
    elif current_python in ("", "python3", "python") or not Path(
        project_paths.to_host_path(current_python, project_root_dir=PROJECT_ROOT_HINT)
    ).exists():
        chosen_python = format_path_for_cfg(sys.executable)
    else:
        chosen_python = current_python

    cfg_updates = {
        "directories": {
            "gtav_root": chosen_gtav_root,
            "unity_assets": chosen_unity_assets,
        },
        "executables": {
            "blender": chosen_blender,
            "rage": chosen_rage,
            "python": chosen_python,
        },
    }

    for avatar_id in project_paths.list_available_avatars():
        preset_info = project_paths.get_avatar_preset_info(avatar_id)
        legacy_section = str(preset_info["legacy_section"])
        target_section = legacy_section
        for candidate_section in (
            f"avatar_{avatar_id}",
            f"avatar:{avatar_id}",
            avatar_id,
            legacy_section,
        ):
            if config_parser.has_section(candidate_section):
                target_section = candidate_section
                break

        scene_hints = list(preset_info.get("unity_hints") or AVATAR_SCENE_HINTS.get(avatar_id, [avatar_id]))
        anim_candidates = list(preset_info.get("default_anim_files") or AVATAR_ANIM_FILES.get(avatar_id, []))
        preset_filename = str(
            preset_info.get("default_blendshapes_cfg")
            or AVATAR_BLENDSHAPE_PRESETS.get(avatar_id, f"{avatar_id}_blendshapes.cfg")
        )

        existing_scene_val = (
            config_parser.get(target_section, "unity_scene", fallback="")
            if config_parser.has_section(target_section)
            else ""
        )
        detected_scene = detect_character_unity_scene(
            chosen_unity_assets,
            scene_hints,
            existing_scene_val,
            avatar_id,
        )
        if detected_scene:
            cfg_updates.setdefault(target_section, {})["unity_scene"] = detected_scene

        existing_anim_val = (
            config_parser.get(target_section, "face_anim", fallback="")
            if config_parser.has_section(target_section)
            else ""
        )
        detected_anim = detect_character_face_anim(
            chosen_unity_assets,
            anim_candidates,
            existing_anim_val,
        )
        if detected_anim and not existing_anim_val.strip():
            cfg_updates.setdefault(target_section, {})["face_anim"] = detected_anim

        existing_bs_cfg = (
            config_parser.get(target_section, "blendshapes_cfg", fallback="")
            if config_parser.has_section(target_section)
            else ""
        )
        if not existing_bs_cfg.strip():
            cfg_updates.setdefault(target_section, {})[
                "blendshapes_cfg"
            ] = f"${{directories:project_root}}/configs/{preset_filename}"

    # Paginated avatar picker + MA / Face & Body blendshape resolution when archive or project supplied
    if (
        ingested_source is not None
        or avatar_name_override is not None
        or import_face_blendshapes is not None
        or import_body_blendshapes is not None
    ):
        import build_universal_avatar
        assets_dir_host = project_paths.to_host_path(
            chosen_unity_assets, project_root_dir=PROJECT_ROOT_HINT
        )
        scene_for_picker: Optional[Path] = None
        if ingested_source and ingested_source.get("preferred_scene"):
            scene_for_picker = Path(str(ingested_source["preferred_scene"]))
        elif assets_dir_host.is_dir():
            first_scene = next(
                (p_item for p_item in sorted(assets_dir_host.glob("*.unity"))), None
            )
            if first_scene is None:
                first_scene = next(
                    (p_item for p_item in sorted(assets_dir_host.glob("*/*.unity"))), None
                )
            scene_for_picker = first_scene

        prep_res = build_universal_avatar.prepare_universal_avatar_job(
            avatar_zip=avatar_zip_override,
            unity_project=unity_project_override or (str(assets_dir_host) if assets_dir_host.is_dir() else None),
            unity_scene=str(scene_for_picker) if scene_for_picker else None,
            avatar_name=avatar_name_override,
            target_character=target_character_override,
            import_face=import_face_blendshapes,
            import_body=import_body_blendshapes,
            interactive=interactive,
            verbose=verbose,
            logger=active_logger,
        )
        manifest_info = prep_res["manifest"]
        chosen_slot = str(manifest_info.get("target_character", "michael"))
        slot_avatar_id = {
            "michael": "shinano_er",
            "franklin": "shinano_casual",
            "trevor": "miltina_maid",
        }.get(chosen_slot, "shinano_er")
        slot_section = f"avatar_{slot_avatar_id}"
        for cand_sec in (f"avatar_{slot_avatar_id}", f"avatar:{slot_avatar_id}", slot_avatar_id):
            if config_parser.has_section(cand_sec):
                slot_section = cand_sec
                break
        if manifest_info.get("scene_path"):
            cfg_updates.setdefault(slot_section, {})["unity_scene"] = format_path_for_cfg(
                str(manifest_info["scene_path"])
            )
        if manifest_info.get("avatar_name"):
            cfg_updates.setdefault(slot_section, {})["unity_avatar_name"] = str(
                manifest_info["avatar_name"]
            )
        cfg_updates.setdefault(slot_section, {})["import_face_blendshapes"] = (
            "1" if manifest_info.get("import_face_blendshapes", True) else "0"
        )
        cfg_updates.setdefault(slot_section, {})["import_body_blendshapes"] = (
            "1" if manifest_info.get("import_body_blendshapes", True) else "0"
        )
        if manifest_info.get("blendshapes_cfg_path"):
            cfg_updates.setdefault(slot_section, {})["blendshapes_cfg"] = format_path_for_cfg(
                str(manifest_info["blendshapes_cfg_path"])
            )

    update_cfg_values_in_place(config_file_path, cfg_updates)
    print(project_i18n.translate("setup.saved_cfg", path=config_file_path))
    return config_file_path


def run_rage_extract(
    archive_path: Path,
    output_dir: Path,
    gtav_root_dir: Path,
    patterns: Optional[List[str]] = None,
    description: str = "",
) -> None:
    """Run `rage extract` with Ng keys derived from gtav_root_dir."""
    if not archive_path.is_file():
        raise FileNotFoundError(
            project_i18n.translate("setup.source_rpf_missing", path=archive_path)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    command_args: List[str] = ["--exe", str(gtav_root_dir), "extract", str(archive_path)]
    if patterns:
        command_args.extend(patterns)
    command_args.extend(["-o", str(output_dir)])

    full_command = project_paths.build_rage_command(*command_args)
    label_text = (
        description
        if description
        else project_i18n.translate("setup.extracting_default", filename=archive_path.name)
    )
    print(f"[INFO] {label_text} -> {output_dir}...")
    try:
        subprocess.run(
            full_command,
            stdin=subprocess.DEVNULL,
            timeout=300.0,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise err_helper.SubprocessExecutionError(
            f"RAGE extraction failed ({archive_path.name}): {exc}",
            stage="rage_extract",
            cause=exc,
        )


def extract_vanilla_gtav_assets(force_reextract: bool = False) -> bool:
    """
    Extract vanilla base RPF archives from GTA V into `staging/` and seed
    base `player_*.yft` skeletons into each character's `2_blender/` directory.
    """
    project_paths.invalidate_config_cache()
    gtav_root_dir = project_paths.get_gtav_root_dir()
    gtav_mods_dir = project_paths.get_gtav_mods_dir()
    staging_dir = project_paths.get_staging_dir()
    rpf_paths_cfg = project_paths.get_rpf_paths()

    if not is_valid_gtav_root(gtav_root_dir):
        print(project_i18n.translate("setup.invalid_gtav_root", path=gtav_root_dir))
        return False

    rage_cli_binary = project_paths.get_rage_cli()
    if not (
        Path(rage_cli_binary).is_file()
        or shutil.which(rage_cli_binary)
        or rage_cli_binary.startswith("wsl ")
    ):
        print(project_i18n.translate("setup.rage_not_found", rage_bin=rage_cli_binary))
        return False

    # Ensure runtime-only directories exist locally
    for runtime_dir in (
        staging_dir,
        project_paths.get_renders_output_dir(),
        Path(project_paths.get_config_path("directories", "backups")),
        Path(project_paths.get_config_path("directories", "project_root")) / "renders",
        gtav_mods_dir,
    ):
        runtime_dir.mkdir(parents=True, exist_ok=True)

    for char_section in ("franklin", "michael", "trevor"):
        char_cfg = project_paths.get_character_paths(char_section)
        Path(char_cfg["textures_dir"]).mkdir(parents=True, exist_ok=True)
        Path(char_cfg["ytd_dir"]).mkdir(parents=True, exist_ok=True)
        Path(char_cfg["exported_models_dir"]).mkdir(parents=True, exist_ok=True)
        Path(char_cfg["skeleton_yft"]).parent.mkdir(parents=True, exist_ok=True)

    # 1. Extract and validate decryption keys from GTA5.exe
    keys_output_dir = staging_dir / "rage_keys"
    if force_reextract or not keys_output_dir.is_dir() or not any(keys_output_dir.iterdir()):
        keys_output_dir.mkdir(parents=True, exist_ok=True)
        print(project_i18n.translate("setup.extracting_keys", path=keys_output_dir))
        extract_keys_cmd = project_paths.build_rage_command(
            "--exe",
            str(gtav_root_dir),
            "extract-keys",
            "-o",
            str(keys_output_dir),
        )
        try:
            subprocess.run(
                extract_keys_cmd,
                stdin=subprocess.DEVNULL,
                timeout=180.0,
                check=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise err_helper.SubprocessExecutionError(
                f"Failed extracting RAGE decryption keys: {exc}",
                stage="rage_extract_keys",
                cause=exc,
            )
    else:
        print(project_i18n.translate("setup.keys_ready", path=keys_output_dir))

    # 2. Extract vanilla x64v.rpf -> staging/x64v_extracted
    x64v_extracted_dir = rpf_paths_cfg["x64v_extracted"]
    nested_streamedpeds_rpf = x64v_extracted_dir / rpf_paths_cfg["streamedpeds_rpf_relative"]
    nested_props_rpf = x64v_extracted_dir / rpf_paths_cfg["streamedpedprops_rpf_relative"]
    vanilla_x64v_rpf = rpf_paths_cfg["x64v_vanilla_rpf"]

    x64v_freshly_extracted = False
    if force_reextract or not nested_streamedpeds_rpf.is_file() or not nested_props_rpf.is_file():
        run_rage_extract(
            vanilla_x64v_rpf,
            x64v_extracted_dir,
            gtav_root_dir,
            description=project_i18n.translate("setup.desc_extract_x64v"),
        )
        x64v_freshly_extracted = True
    else:
        print(project_i18n.translate("setup.x64v_ready", path=x64v_extracted_dir))

    # 3. Extract streamedpeds_players.rpf -> staging/streamedpeds_players_extracted
    streamedpeds_dir = rpf_paths_cfg["streamedpeds_extracted"]
    has_all_player_dirs = all(
        (streamedpeds_dir / ped_slot).is_dir()
        for ped_slot in ("player_zero", "player_one", "player_two")
    )
    if force_reextract or not has_all_player_dirs:
        run_rage_extract(
            nested_streamedpeds_rpf,
            streamedpeds_dir,
            gtav_root_dir,
            description=project_i18n.translate("setup.desc_extract_streamedpeds"),
        )
    else:
        print(project_i18n.translate("setup.streamedpeds_ready", path=streamedpeds_dir))

    # 4. Save immutable copies of vanilla skeletons (.yft) and seed */2_blender/.
    # Note: if x64v_extracted already existed from an earlier deploy, the nested
    # streamedpeds_players.rpf inside it may already be modded, so read from original x64v.rpf.
    vanilla_skeletons_backup = rpf_paths_cfg.get(
        "vanilla_skeletons_backup",
        staging_dir / "backup_vanilla_skeletons",
    )
    vanilla_skeletons_backup.mkdir(parents=True, exist_ok=True)
    missing_vanilla_yft_names = [
        f"{ped_slot}.yft"
        for ped_slot in ("player_zero", "player_one", "player_two")
        if force_reextract or not (vanilla_skeletons_backup / f"{ped_slot}.yft").is_file()
    ]
    if missing_vanilla_yft_names:
        if x64v_freshly_extracted:
            run_rage_extract(
                nested_streamedpeds_rpf,
                vanilla_skeletons_backup,
                gtav_root_dir,
                patterns=missing_vanilla_yft_names,
                description=project_i18n.translate("setup.desc_extract_skeletons"),
            )
        else:
            temp_vanilla_stage = staging_dir / "_tmp_vanilla_skeletons"
            shutil.rmtree(temp_vanilla_stage, ignore_errors=True)
            try:
                streamed_rel_str = rpf_paths_cfg["streamedpeds_rpf_relative"].as_posix()
                run_rage_extract(
                    vanilla_x64v_rpf,
                    temp_vanilla_stage,
                    gtav_root_dir,
                    patterns=[streamed_rel_str],
                    description=project_i18n.translate(
                        "setup.desc_extract_vanilla_peds_for_skeletons"
                    ),
                )
                temp_nested_peds = temp_vanilla_stage / rpf_paths_cfg["streamedpeds_rpf_relative"]
                run_rage_extract(
                    temp_nested_peds,
                    vanilla_skeletons_backup,
                    gtav_root_dir,
                    patterns=missing_vanilla_yft_names,
                    description=project_i18n.translate("setup.desc_extract_skeletons"),
                )
            finally:
                shutil.rmtree(temp_vanilla_stage, ignore_errors=True)
    else:
        print(
            project_i18n.translate(
                "setup.skeleton_backups_ready", path=vanilla_skeletons_backup
            )
        )

    for char_section in ("franklin", "michael", "trevor"):
        skeleton_dest = project_paths.ensure_character_skeleton_yft(char_section)
        print(
            project_i18n.translate(
                "setup.character_skeleton_ready",
                character=char_section,
                path=skeleton_dest,
            )
        )

    # 5. Extract streamedpedprops.rpf -> staging/streamedpedprops_extracted
    props_dir = rpf_paths_cfg["streamedpedprops_extracted"]
    if force_reextract and props_dir.is_dir():
        shutil.rmtree(props_dir, ignore_errors=True)
    project_paths.ensure_streamedpedprops_extracted()
    print(project_i18n.translate("setup.streamedpedprops_ready", path=props_dir))

    # 6. Extract mppatchesng/dlc.rpf and mppatches.rpf
    vanilla_mppatches_dlc = (
        gtav_root_dir / "update" / "x64" / "dlcpacks" / "mppatchesng" / "dlc.rpf"
    )
    mppatches_dlc_dir = rpf_paths_cfg["mppatches_dlc_extracted"]
    inner_mppatches_rpf = mppatches_dlc_dir / rpf_paths_cfg["mppatches_rpf_relative"]
    mppatches_models_dir = rpf_paths_cfg["mppatches_extracted"]

    if not vanilla_mppatches_dlc.is_file():
        print(
            project_i18n.translate(
                "setup.mppatches_missing", path=vanilla_mppatches_dlc
            )
        )
        return False

    if force_reextract or not inner_mppatches_rpf.is_file():
        run_rage_extract(
            vanilla_mppatches_dlc,
            mppatches_dlc_dir,
            gtav_root_dir,
            description=project_i18n.translate("setup.desc_extract_mppatchesng"),
        )
    else:
        print(project_i18n.translate("setup.mppatchesng_ready", path=mppatches_dlc_dir))

    has_mppatches_players = all(
        (mppatches_models_dir / ped_slot).is_dir()
        for ped_slot in ("player_zero", "player_one", "player_two")
    )
    if force_reextract or not has_mppatches_players:
        run_rage_extract(
            inner_mppatches_rpf,
            mppatches_models_dir,
            gtav_root_dir,
            description=project_i18n.translate("setup.desc_extract_mppatches"),
        )
    else:
        print(project_i18n.translate("setup.mppatches_ready", path=mppatches_models_dir))

    # 7. Extract patchday4ng/dlc.rpf and patchday4ng.rpf when present in user install
    vanilla_patchday4_dlc = (
        gtav_root_dir / "update" / "x64" / "dlcpacks" / "patchday4ng" / "dlc.rpf"
    )
    if vanilla_patchday4_dlc.is_file():
        patchday4_dlc_dir = rpf_paths_cfg["patchday4ng_dlc_extracted"]
        inner_patchday4_rpf = patchday4_dlc_dir / rpf_paths_cfg["patchday4ng_rpf_relative"]
        patchday4_models_dir = rpf_paths_cfg["patchday4ng_models_extracted"]

        if force_reextract or not inner_patchday4_rpf.is_file():
            run_rage_extract(
                vanilla_patchday4_dlc,
                patchday4_dlc_dir,
                gtav_root_dir,
                description=project_i18n.translate("setup.desc_extract_patchday4_dlc"),
            )
        else:
            print(
                project_i18n.translate(
                    "setup.patchday4_dlc_ready", path=patchday4_dlc_dir
                )
            )

        if (
            force_reextract
            or not patchday4_models_dir.is_dir()
            or not any(patchday4_models_dir.iterdir())
        ):
            run_rage_extract(
                inner_patchday4_rpf,
                patchday4_models_dir,
                gtav_root_dir,
                description=project_i18n.translate("setup.desc_extract_patchday4_rpf"),
            )
        else:
            print(
                project_i18n.translate(
                    "setup.patchday4_models_ready", path=patchday4_models_dir
                )
            )
    else:
        print(project_i18n.translate("setup.patchday4_optional_skipped"))

    print(project_i18n.translate("setup.extraction_success"))
    return True


def diagnose_setup_state() -> Dict[str, bool]:
    """Inspect whether vrc2gtav.cfg, core paths, extracted RPFs, and skeletons are ready."""
    has_cfg_file = project_paths.has_project_config_file()
    if not has_cfg_file:
        return {
            "has_cfg": False,
            "gtav_root_valid": False,
            "unity_assets_valid": False,
            "staging_ready": False,
            "skeletons_ready": False,
        }

    project_paths.invalidate_config_cache()
    gtav_root_dir = project_paths.get_gtav_root_dir()
    unity_assets_dir = project_paths.get_vrc_assets_dir()
    rpf_paths_cfg = project_paths.get_rpf_paths()

    gtav_ok = is_valid_gtav_root(gtav_root_dir)
    assets_ok = is_valid_unity_assets_dir(unity_assets_dir)

    x64v_ok = (rpf_paths_cfg["x64v_extracted"] / rpf_paths_cfg["streamedpeds_rpf_relative"]).is_file()
    streamedpeds_ok = all(
        (rpf_paths_cfg["streamedpeds_extracted"] / ped_slot).is_dir()
        for ped_slot in ("player_zero", "player_one", "player_two")
    )
    props_ok = (
        rpf_paths_cfg["streamedpedprops_extracted"].is_dir()
        and any(rpf_paths_cfg["streamedpedprops_extracted"].iterdir())
    )
    mppatches_ok = (rpf_paths_cfg["mppatches_extracted"] / "player_zero").is_dir()
    staging_ok = x64v_ok and streamedpeds_ok and props_ok and mppatches_ok

    skeletons_ok = all(
        Path(project_paths.get_character_paths(char_sec)["skeleton_yft"]).is_file()
        for char_sec in project_paths.list_available_protagonists()
    )
    blendshapes_ok = all(
        Path(project_paths.get_avatar_paths(avatar_id).get("blendshapes_cfg", "")).is_file()
        or (
            bool(str(project_paths.get_avatar_paths(avatar_id).get("unity_scene", "") or "").strip())
            and Path(project_paths.get_avatar_paths(avatar_id)["unity_scene"]).is_file()
        )
        for avatar_id in project_paths.list_available_avatars()
    )

    return {
        "has_cfg": True,
        "gtav_root_valid": gtav_ok,
        "unity_assets_valid": assets_ok,
        "staging_ready": staging_ok,
        "skeletons_ready": skeletons_ok,
        "blendshapes_ready": blendshapes_ok,
    }


def is_first_run_needed() -> bool:
    """Return True if configuration or initial vanilla extraction is still incomplete."""
    status_map = diagnose_setup_state()
    return not (
        status_map["has_cfg"]
        and status_map["gtav_root_valid"]
        and status_map["staging_ready"]
        and status_map["skeletons_ready"]
    )


def print_setup_diagnostics() -> bool:
    """Print a human-readable First-Run readiness report."""
    status_map = diagnose_setup_state()
    print("\n" + "=" * 70)
    print(project_i18n.translate("setup.diag_header"))
    print("=" * 70)
    for check_name, check_passed in status_map.items():
        tag_str = (
            project_i18n.translate("setup.diag_tag_ok")
            if check_passed
            else project_i18n.translate("setup.diag_tag_pending")
        )
        print(f"  {tag_str:10} {check_name}")
    print("=" * 70)
    return all(status_map.values())


def run_first_run_setup(
    interactive: bool = True,
    force_reextract: bool = False,
    gtav_root_override: Optional[str] = None,
    unity_assets_override: Optional[str] = None,
    blender_override: Optional[str] = None,
    rage_override: Optional[str] = None,
    python_override: Optional[str] = None,
    avatar_zip_override: Optional[str] = None,
    unity_project_override: Optional[str] = None,
    download_blender: Optional[bool] = None,
    avatar_name_override: Optional[str] = None,
    target_character_override: Optional[str] = None,
    import_face_blendshapes: Optional[bool] = None,
    import_body_blendshapes: Optional[bool] = None,
    verbose: bool = False,
) -> bool:
    """Run the full First-Run configuration, archive/Unity ingestion, MA bake, and GTA V extraction flow."""
    active_logger = err_helper.PipelineLogger(
        verbose=verbose,
        avatar_name=avatar_name_override or "first_run",
        stage_name="setup",
        project_root=PROJECT_ROOT_HINT,
    )
    print("\n" + "=" * 70)
    print(project_i18n.translate("setup.banner_title"))
    print("=" * 70)
    print(project_i18n.translate("setup.banner_notice"))

    try:
        configure_vrc2gtav_cfg(
            interactive=interactive,
            gtav_root_override=gtav_root_override,
            unity_assets_override=unity_assets_override,
            blender_override=blender_override,
            rage_override=rage_override,
            python_override=python_override,
            avatar_zip_override=avatar_zip_override,
            unity_project_override=unity_project_override,
            download_blender=download_blender,
            avatar_name_override=avatar_name_override,
            target_character_override=target_character_override,
            import_face_blendshapes=import_face_blendshapes,
            import_body_blendshapes=import_body_blendshapes,
            verbose=verbose,
            logger=active_logger,
        )

        unity_assets_dir = project_paths.get_vrc_assets_dir()
        if not unity_assets_dir.is_dir():
            print(project_i18n.translate("setup.unity_assets_warning", path=unity_assets_dir))

        ensure_character_blendshape_presets()
        extraction_ok = extract_vanilla_gtav_assets(force_reextract=force_reextract)
        print_setup_diagnostics()
        return extraction_ok
    except Exception as exc:
        active_logger.error(f"First-Run setup failed: {exc}")
        return False


def main() -> int:
    """CLI entrypoint for the First-Run setup wizard."""
    project_i18n.set_active_language()
    arg_parser = argparse.ArgumentParser(
        description=project_i18n.translate("setup.cli_description")
    )
    arg_parser.add_argument(
        "--check-only",
        action="store_true",
        help=project_i18n.translate("setup.cli_check_only"),
    )
    arg_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help=project_i18n.translate("setup.cli_non_interactive"),
    )
    arg_parser.add_argument(
        "--force",
        action="store_true",
        help=project_i18n.translate("setup.cli_force"),
    )
    arg_parser.add_argument(
        "--lang",
        choices=["auto", "en", "ja", "pt"],
        default="auto",
        help=project_i18n.translate("common.language_option_help"),
    )
    arg_parser.add_argument(
        "--gtav-root",
        default=None,
        help=project_i18n.translate("setup.cli_gtav_root"),
    )
    arg_parser.add_argument(
        "--unity-assets",
        default=None,
        help=project_i18n.translate("setup.cli_unity_assets"),
    )
    arg_parser.add_argument(
        "--blender",
        default=None,
        help=project_i18n.translate("setup.cli_blender"),
    )
    arg_parser.add_argument(
        "--rage",
        default=None,
        help=project_i18n.translate("setup.cli_rage"),
    )
    arg_parser.add_argument(
        "--python",
        default=None,
        help=project_i18n.translate("setup.cli_python"),
    )
    arg_parser.add_argument(
        "--avatar-zip",
        default=None,
        help="Path to avatar .zip or .unitypackage archive for First-Run extraction",
    )
    arg_parser.add_argument(
        "--unity-project",
        default=None,
        help="Path to an existing Unity project directory (containing Assets/) or .unity scene",
    )
    arg_parser.add_argument(
        "--avatar-name",
        default=None,
        help="Avatar name to select automatically from the Unity scene",
    )
    arg_parser.add_argument(
        "--target-character",
        choices=["michael", "franklin", "trevor"],
        default=None,
        help="GTA V protagonist target slot",
    )
    arg_parser.add_argument(
        "--download-blender",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Automatically download portable Blender 4.0.2 + Sollumz when missing",
    )
    arg_parser.add_argument(
        "--import-face-blendshapes",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Import facial blendshapes from Unity into .cfg (No zeroes face keys)",
    )
    arg_parser.add_argument(
        "--import-body-blendshapes",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Import body/outfit blendshapes from Unity into .cfg (No zeroes body keys)",
    )
    arg_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Detailed console output + timestamped log file in logs/",
    )

    parsed_args = arg_parser.parse_args()
    project_i18n.set_active_language(parsed_args.lang)

    if parsed_args.check_only:
        is_ready = print_setup_diagnostics()
        return 0 if is_ready else 1

    setup_ok = run_first_run_setup(
        interactive=not parsed_args.non_interactive,
        force_reextract=parsed_args.force,
        gtav_root_override=parsed_args.gtav_root,
        unity_assets_override=parsed_args.unity_assets,
        blender_override=parsed_args.blender,
        rage_override=parsed_args.rage,
        python_override=parsed_args.python,
        avatar_zip_override=parsed_args.avatar_zip,
        unity_project_override=parsed_args.unity_project,
        download_blender=parsed_args.download_blender,
        avatar_name_override=parsed_args.avatar_name,
        target_character_override=parsed_args.target_character,
        import_face_blendshapes=parsed_args.import_face_blendshapes,
        import_body_blendshapes=parsed_args.import_body_blendshapes,
        verbose=parsed_args.verbose,
    )
    return 0 if setup_ok else 1


if __name__ == "__main__":
    sys.exit(main())
