#!/usr/bin/env python3
"""
run_mod_manager.py
==================
Master Orchestrator for managing and deploying VRChat avatars into GTA V.

Allows selecting interactively or via CLI flags which protagonist to build
(Michael, Franklin, Trevor, or All), controlling each pipeline stage:
  1. Texture Atlas generation (2K DXT5) and .ytd dictionaries
  2. 3D model assembly and rigging in Blender (Sollumz .ydd)
  3. Universal slot replacement and dummy installation (apply_characters)
  4. RPF repacking and GTA V deployment (repack_and_deploy_everything)
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Add common helper directories to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts" / "common_tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "_deploy_tools"))
try:
    import blendshape_helper
    import physbone_helper
    import setup_first_run
    import unity_hair_helper
    import vrc2gtav_i18n as project_i18n
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import blendshape_helper
    from common_tools import physbone_helper
    from common_tools import setup_first_run
    from common_tools import unity_hair_helper
    from common_tools import vrc2gtav_i18n as project_i18n
    from common_tools import vrc2gtav_paths as project_paths

CONFIG_FILE_PATH = None
PROJECT_ROOT_DIRECTORY = Path(__file__).resolve().parent
SCRIPTS_DIRECTORY = None
BLENDER_EXECUTABLE = ""
RAGE_CLI_TOOL = ""
PYTHON_EXECUTABLE = sys.executable
GTAV_MODS_DIRECTORY = None
UNITY_ASSETS_DIRECTORY = None
APPLY_CHARACTERS_SCRIPT_PATH = None
REPACK_DEPLOY_SCRIPT_PATH = None
MICHAEL_CFG = None
FRANKLIN_CFG = None
TREVOR_CFG = None
CHARACTER_PIPELINE_REGISTRY: Dict[str, Dict[str, object]] = {}

SUBCOMMAND_STATUS_MARKERS = (
    "[OK]",
    "[INFO]",
    "[情報]",
    "[SUCCESS]",
    "[成功]",
    "[SUCESSO]",
    "[WARNING]",
    "[警告]",
    "[AVISO]",
    "[ERROR]",
    "[エラー]",
    "[ERRO]",
    "[STAGE",
    "[段階",
    "[ETAPA",
    "[PROGRESS]",
    "[進捗]",
    "[PROGRESSO]",
    "[RPF7 PATCH]",
    "[VERIFICATION",
    "[検証",
    "[VERIFICAÇÃO",
    "Exported",
    "Saved",
    "vertices",
    "Repacking",
    "再パック",
    "Repacotando",
    "Patching",
    "Copying",
    "Replacing",
    "Compiling",
    "Building",
    "生成",
)


def _build_subprocess_env(base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Propagate active language selection into child processes cleanly."""
    merged_env = dict(os.environ if base_env is None else base_env)
    merged_env[project_i18n.LANG_ENV_VAR] = project_i18n.get_active_language()
    merged_env.setdefault("PYTHONUTF8", "1")
    return merged_env


def _format_assignment_display(protagonist_key: str, avatar_id: str) -> str:
    """Return a localized 'Protagonist -> Avatar' display label."""
    protagonist_label = project_i18n.translate(f"protagonist.{protagonist_key}")
    avatar_label = project_i18n.translate(f"avatar.{avatar_id}")
    return f"{protagonist_label} -> {avatar_label}"


def load_runtime_context(
    force_reload: bool = False,
    avatar_overrides: Optional[Dict[str, str]] = None,
) -> None:
    """Load runtime paths and character registries from vrc2gtav.cfg."""
    global CONFIG_FILE_PATH
    global PROJECT_ROOT_DIRECTORY
    global SCRIPTS_DIRECTORY
    global BLENDER_EXECUTABLE
    global RAGE_CLI_TOOL
    global PYTHON_EXECUTABLE
    global GTAV_MODS_DIRECTORY
    global UNITY_ASSETS_DIRECTORY
    global APPLY_CHARACTERS_SCRIPT_PATH
    global REPACK_DEPLOY_SCRIPT_PATH
    global MICHAEL_CFG
    global FRANKLIN_CFG
    global TREVOR_CFG
    global CHARACTER_PIPELINE_REGISTRY

    if force_reload:
        project_paths.invalidate_config_cache()

    CONFIG_FILE_PATH = project_paths.find_project_config_file()
    PROJECT_ROOT_DIRECTORY = project_paths.get_project_root()
    SCRIPTS_DIRECTORY = project_paths.get_scripts_root_dir()
    BLENDER_EXECUTABLE = project_paths.get_blender_exe()
    RAGE_CLI_TOOL = project_paths.get_rage_cli()
    PYTHON_EXECUTABLE = project_paths.get_python_exe()
    GTAV_MODS_DIRECTORY = project_paths.get_gtav_mods_dir()
    UNITY_ASSETS_DIRECTORY = project_paths.get_vrc_assets_dir()

    APPLY_CHARACTERS_SCRIPT_PATH = project_paths.get_config_path(
        "common_assets", "apply_characters_script"
    )
    REPACK_DEPLOY_SCRIPT_PATH = project_paths.get_config_path(
        "common_assets", "repack_deploy_script"
    )

    normalized_overrides = {
        project_paths.normalize_protagonist_key(raw_prot): project_paths.normalize_avatar_id(
            raw_avatar
        )
        for raw_prot, raw_avatar in (avatar_overrides or {}).items()
        if raw_avatar
    }

    MICHAEL_CFG = project_paths.get_character_paths(
        "michael", avatar_override=normalized_overrides.get("michael")
    )
    FRANKLIN_CFG = project_paths.get_character_paths(
        "franklin", avatar_override=normalized_overrides.get("franklin")
    )
    TREVOR_CFG = project_paths.get_character_paths(
        "trevor", avatar_override=normalized_overrides.get("trevor")
    )

    loaded_cfgs = {
        "michael": MICHAEL_CFG,
        "franklin": FRANKLIN_CFG,
        "trevor": TREVOR_CFG,
    }
    CHARACTER_PIPELINE_REGISTRY = {}
    for protagonist_key in project_paths.list_available_protagonists():
        char_cfg = loaded_cfgs[protagonist_key]
        avatar_id = str(char_cfg["avatar_id"])
        protagonist_label = project_i18n.translate(f"protagonist.{protagonist_key}")
        avatar_label = project_i18n.translate(f"avatar.{avatar_id}")
        CHARACTER_PIPELINE_REGISTRY[protagonist_key] = {
            "character_key": str(char_cfg["ped_name"]),
            "avatar_id": avatar_id,
            "protagonist_label": protagonist_label,
            "avatar_label": avatar_label,
            "display_name": f"{protagonist_label} -> {avatar_label}",
            "folder_name": char_cfg["character_dir"].name,
            "texture_script": char_cfg["atlas_script"],
            "blender_script": char_cfg["blender_script"],
        }


def print_section_header(section_title: str) -> None:
    """Print an ASCII section header without emojis."""
    separator_line = "=" * 70
    print(f"\n{separator_line}")
    print(f"  {section_title}")
    print(f"{separator_line}\n")


def execute_subcommand(
    command_arguments: List[str],
    task_description: str,
    custom_environment: Optional[Dict[str, str]] = None,
    timeout_sec: Optional[float] = 1800.0,
) -> bool:
    """
    Execute a subprocess safely while streaming salient progress lines and
    reporting detailed failure diagnostics if the command returns non-zero.
    Kills child process cleanly on timeout or error so no orphan processes remain.
    """
    print(project_i18n.translate("manager.subcmd_starting", task=task_description))
    start_timestamp = time.time()
    captured_output_lines: List[str] = []
    effective_env = _build_subprocess_env(custom_environment)
    verbose_mode = os.environ.get("VRC2GTAV_VERBOSE", "0") == "1"
    process_execution: Optional[subprocess.Popen] = None

    def _terminate_child(proc_obj: Optional[subprocess.Popen]) -> None:
        if proc_obj is None or proc_obj.poll() is not None:
            return
        try:
            proc_obj.terminate()
            proc_obj.wait(timeout=3.0)
        except Exception:
            try:
                proc_obj.kill()
                proc_obj.wait(timeout=3.0)
            except Exception:
                pass

    import threading
    timed_out_flag = False
    watchdog_timer: Optional[threading.Timer] = None

    try:
        process_execution = subprocess.Popen(
            command_arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=effective_env,
        )

        if timeout_sec is not None and timeout_sec > 0:
            def _on_timeout() -> None:
                nonlocal timed_out_flag
                timed_out_flag = True
                _terminate_child(process_execution)

            watchdog_timer = threading.Timer(float(timeout_sec), _on_timeout)
            watchdog_timer.daemon = True
            watchdog_timer.start()

        if process_execution.stdout is not None:
            for raw_output_line in process_execution.stdout:
                stripped_line = raw_output_line.rstrip()
                if not stripped_line:
                    continue
                captured_output_lines.append(stripped_line)

                if verbose_mode or any(
                    status_marker in stripped_line
                    for status_marker in SUBCOMMAND_STATUS_MARKERS
                ):
                    print(f"    {stripped_line}")

        process_execution.wait(timeout=timeout_sec if (timeout_sec and timeout_sec > 0) else None)
        if watchdog_timer is not None:
            watchdog_timer.cancel()
        elapsed_seconds = time.time() - start_timestamp

        if timed_out_flag:
            raise TimeoutError(
                f"{task_description} exceeded timeout of {timeout_sec:.0f}s"
            )

        if process_execution.returncode != 0:
            print(
                project_i18n.translate(
                    "manager.subcmd_failed",
                    task=task_description,
                    elapsed=elapsed_seconds,
                    returncode=process_execution.returncode,
                )
            )
            print(project_i18n.translate("manager.subcmd_tail_header"))
            for recent_line in captured_output_lines[-20:]:
                print(f"    {recent_line}")
            return False

        print(
            project_i18n.translate(
                "manager.subcmd_completed",
                task=task_description,
                elapsed=elapsed_seconds,
            )
        )
        return True

    except Exception as unexpected_error:
        if watchdog_timer is not None:
            watchdog_timer.cancel()
        _terminate_child(process_execution)
        print(
            project_i18n.translate(
                "manager.subcmd_unexpected_error",
                task=task_description,
                error=unexpected_error,
            )
        )
        return False


def verify_system_prerequisites() -> bool:
    """Verify required tools, libraries, directories, and dummy meshes before starting."""
    print_section_header(project_i18n.translate("manager.prereq_header"))
    verification_passed = True

    print(project_i18n.translate("manager.prereq_cfg", path=CONFIG_FILE_PATH))

    # 1. Python and required image libraries
    print(project_i18n.translate("manager.prereq_python", path=PYTHON_EXECUTABLE))
    try:
        dep_check = subprocess.run(
            [PYTHON_EXECUTABLE, "-c", "import PIL, numpy"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if dep_check.returncode == 0:
            print(project_i18n.translate("manager.prereq_libs_ok"))
        else:
            print(
                project_i18n.translate(
                    "manager.prereq_libs_missing",
                    python_exe=PYTHON_EXECUTABLE,
                    error=dep_check.stderr.strip(),
                )
            )
            verification_passed = False
    except Exception as python_check_error:
        print(
            project_i18n.translate(
                "manager.prereq_python_fail",
                python_exe=PYTHON_EXECUTABLE,
                error=python_check_error,
            )
        )
        verification_passed = False

    # 2. Blender executable
    if Path(BLENDER_EXECUTABLE).exists() or shutil.which(BLENDER_EXECUTABLE):
        print(
            project_i18n.translate(
                "manager.prereq_blender_ok", path=BLENDER_EXECUTABLE
            )
        )
    else:
        print(
            project_i18n.translate(
                "manager.prereq_blender_warn", path=BLENDER_EXECUTABLE
            )
        )

    # 3. RAGE CLI binary
    if Path(RAGE_CLI_TOOL).exists() or shutil.which(RAGE_CLI_TOOL):
        print(project_i18n.translate("manager.prereq_rage_ok", path=RAGE_CLI_TOOL))
    else:
        print(project_i18n.translate("manager.prereq_rage_err", path=RAGE_CLI_TOOL))
        verification_passed = False

    # 4. Unity Assets folder
    if UNITY_ASSETS_DIRECTORY is not None and UNITY_ASSETS_DIRECTORY.exists():
        print(
            project_i18n.translate(
                "manager.prereq_assets_ok", path=UNITY_ASSETS_DIRECTORY
            )
        )
    else:
        print(
            project_i18n.translate(
                "manager.prereq_assets_warn", path=UNITY_ASSETS_DIRECTORY
            )
        )

    # 5. GTA V mods destination folder
    if GTAV_MODS_DIRECTORY is not None and GTAV_MODS_DIRECTORY.exists():
        print(
            project_i18n.translate(
                "manager.prereq_mods_ok", path=GTAV_MODS_DIRECTORY
            )
        )
    else:
        print(
            project_i18n.translate(
                "manager.prereq_mods_warn", path=GTAV_MODS_DIRECTORY
            )
        )

    # 6. Dummy meshes (body slots and eyewear props)
    dummy_ydd_path = project_paths.get_dummy_ydd_path()
    prop_dummy_ydd_path = project_paths.get_prop_dummy_ydd_path()
    if dummy_ydd_path.is_file():
        print(project_i18n.translate("manager.prereq_dummy_ok", path=dummy_ydd_path))
    else:
        print(project_i18n.translate("manager.prereq_dummy_err", path=dummy_ydd_path))
        verification_passed = False

    if prop_dummy_ydd_path.is_file():
        print(
            project_i18n.translate(
                "manager.prereq_prop_dummy_ok", path=prop_dummy_ydd_path
            )
        )
    else:
        print(
            project_i18n.translate(
                "manager.prereq_prop_dummy_err", path=prop_dummy_ydd_path
            )
        )
        verification_passed = False

    return verification_passed


def execute_texture_generation(
    selected_character_keys: List[str],
    extra_atlas_args: Optional[List[str]] = None,
) -> bool:
    """Generate 2K texture atlases and .ytd dictionaries for selected characters."""
    print_section_header(project_i18n.translate("manager.stage1_header"))
    for character_key in selected_character_keys:
        character_data = CHARACTER_PIPELINE_REGISTRY[character_key]
        script_path = Path(character_data["texture_script"])

        if not script_path.exists():
            print(
                project_i18n.translate("manager.tex_script_missing", path=script_path)
            )
            return False

        command_list = (
            [PYTHON_EXECUTABLE, str(script_path), "--target-character", character_key]
            + list(extra_atlas_args or [])
        )
        task_label = project_i18n.translate(
            "manager.generating_atlas_task",
            display_name=character_data["display_name"],
        )
        success_status = execute_subcommand(command_list, task_label)
        if not success_status:
            return False

    return True


def execute_blender_build(
    selected_character_keys: List[str],
    extra_blender_args: Optional[List[str]] = None,
) -> bool:
    """Compile rigged 3D models inside Blender for selected characters."""
    print_section_header(project_i18n.translate("manager.stage2_header"))

    for character_key in selected_character_keys:
        project_paths.ensure_character_skeleton_yft(character_key)
        character_data = CHARACTER_PIPELINE_REGISTRY[character_key]
        script_path = Path(character_data["blender_script"])

        if not script_path.exists():
            print(
                project_i18n.translate(
                    "manager.blender_script_missing", path=script_path
                )
            )
            return False

        per_character_args = ["--target-character", character_key] + list(
            extra_blender_args or []
        )
        blender_command_list, blender_env = project_paths.build_blender_command(
            script_path,
            extra_arguments=per_character_args,
        )
        task_label = project_i18n.translate(
            "manager.building_blender_task",
            display_name=character_data["display_name"],
        )
        success_status = execute_subcommand(
            blender_command_list,
            task_label,
            custom_environment=blender_env,
        )
        if not success_status:
            return False

    return True


def execute_character_slot_patching(selected_character_keys: List[str]) -> bool:
    """Apply compiled drawables and invisible dummies across GTA V clothing slots."""
    print_section_header(project_i18n.translate("manager.stage3_header"))
    apply_script_path = Path(APPLY_CHARACTERS_SCRIPT_PATH)

    if not apply_script_path.exists():
        apply_script_path = (
            PROJECT_ROOT_DIRECTORY / "_deploy_tools" / "apply_characters.py"
        )

    if not apply_script_path.exists():
        print(
            project_i18n.translate(
                "manager.apply_script_missing", path=apply_script_path
            )
        )
        return False

    for character_key in selected_character_keys:
        character_data = CHARACTER_PIPELINE_REGISTRY[character_key]
        ped_identifier = str(character_data["character_key"])
        avatar_id = str(character_data["avatar_id"])
        command_list = [
            PYTHON_EXECUTABLE,
            str(apply_script_path),
            "--character",
            ped_identifier,
            "--avatar",
            avatar_id,
        ]
        task_label = project_i18n.translate(
            "manager.patching_slots_task", ped_id=ped_identifier
        )
        success_status = execute_subcommand(command_list, task_label)
        if not success_status:
            return False

    return True


def execute_rpf_repack_and_deploy() -> bool:
    """Repack RPF archives with OPEN headers and deploy into GTA V mods/."""
    print_section_header(project_i18n.translate("manager.stage4_header"))
    repack_script_path = Path(REPACK_DEPLOY_SCRIPT_PATH)
    if not repack_script_path.exists():
        repack_script_path = (
            PROJECT_ROOT_DIRECTORY / "_deploy_tools" / "repack_and_deploy_everything.py"
        )

    if not repack_script_path.exists():
        print(
            project_i18n.translate(
                "manager.repack_script_missing", path=repack_script_path
            )
        )
        return False

    command_list = [PYTHON_EXECUTABLE, str(repack_script_path)]
    task_label = project_i18n.translate("manager.repacking_task")
    return execute_subcommand(command_list, task_label)


def _prompt_protagonist_selection(
    header_key: str,
    select_prompt_key: str,
) -> Optional[str]:
    """Prompt the user to choose a GTA V protagonist key ('michael'/'franklin'/'trevor')."""
    print_section_header(project_i18n.translate(header_key))
    protagonists = list(project_paths.list_available_protagonists())

    print(project_i18n.translate(select_prompt_key))
    for opt_index, protagonist_key in enumerate(protagonists, start=1):
        char_cfg = project_paths.get_character_paths(protagonist_key)
        current_avatar_label = project_i18n.translate(f"avatar.{char_cfg['avatar_id']}")
        protagonist_label = project_i18n.translate(f"protagonist.{protagonist_key}")
        print(
            project_i18n.translate(
                "manager.menu_opt_slot",
                opt=opt_index,
                protagonist=protagonist_label,
                ped_name=char_cfg["ped_name"],
                avatar=current_avatar_label,
            )
        )
    print(project_i18n.translate("manager.menu_opt_0"))
    prot_choice = input(project_i18n.translate("manager.swap_prompt_choice")).strip()
    if prot_choice == "0":
        return None
    if prot_choice not in {str(idx) for idx in range(1, len(protagonists) + 1)}:
        print(project_i18n.translate("manager.invalid_option"))
        return None
    return protagonists[int(prot_choice) - 1]


def run_interactive_avatar_swap() -> bool:
    """Interactively assign any VRChat avatar preset to any GTA V protagonist."""
    chosen_protagonist = _prompt_protagonist_selection(
        "manager.swap_header",
        "manager.swap_select_protagonist",
    )
    if chosen_protagonist is None:
        return False

    avatars = list(project_paths.list_available_avatars())
    chosen_prot_label = project_i18n.translate(f"protagonist.{chosen_protagonist}")

    print()
    print(
        project_i18n.translate(
            "manager.swap_select_avatar", protagonist=chosen_prot_label
        )
    )
    for opt_index, avatar_id in enumerate(avatars, start=1):
        print(f"  [{opt_index}] {project_i18n.translate(f'avatar.{avatar_id}')} ({avatar_id})")
    print(project_i18n.translate("manager.menu_opt_0"))
    avatar_choice = input(project_i18n.translate("manager.swap_prompt_choice")).strip()
    if avatar_choice == "0":
        return False
    if avatar_choice not in {str(idx) for idx in range(1, len(avatars) + 1)}:
        print(project_i18n.translate("manager.invalid_option"))
        return False
    chosen_avatar = avatars[int(avatar_choice) - 1]

    project_paths.set_protagonist_avatar(chosen_protagonist, chosen_avatar)
    print(
        project_i18n.translate(
            "manager.swap_saved",
            protagonist=chosen_prot_label,
            avatar=project_i18n.translate(f"avatar.{chosen_avatar}"),
        )
    )
    return True


def run_interactive_hair_config() -> bool:
    """Scan Unity Assets and configure custom hair overrides for any protagonist."""
    chosen_protagonist = _prompt_protagonist_selection(
        "manager.hair_header",
        "manager.hair_select_protagonist",
    )
    if chosen_protagonist is None:
        return False

    char_cfg = project_paths.get_character_paths(chosen_protagonist)
    chosen_prot_label = project_i18n.translate(f"protagonist.{chosen_protagonist}")
    current_hair_display = (
        str(char_cfg.get("custom_hair", "")).strip()
        or str(char_cfg.get("fbx_hair", "")).strip()
        or "auto"
    )
    print()
    print(
        project_i18n.translate(
            "manager.hair_current",
            protagonist=chosen_prot_label,
            current=current_hair_display,
        )
    )
    print(project_i18n.translate("manager.hair_scanning"))

    candidates = unity_hair_helper.scan_custom_hair_candidates(
        UNITY_ASSETS_DIRECTORY or project_paths.get_vrc_assets_dir(),
        max_results=30,
    )

    print()
    print(
        project_i18n.translate(
            "manager.hair_select_source", protagonist=chosen_prot_label
        )
    )
    print(project_i18n.translate("manager.hair_opt_auto"))
    print(project_i18n.translate("manager.hair_opt_default"))
    print(project_i18n.translate("manager.hair_opt_none"))
    if candidates:
        for idx_offset, item_entry in enumerate(candidates, start=4):
            kind_tag = item_entry.get("kind", "prefab")
            rel_label = (
                item_entry.get("relative_path")
                or item_entry.get("relative")
                or item_entry.get("path", "")
            )
            print(f"  [{idx_offset}] [{kind_tag}] {rel_label}")
    else:
        print(project_i18n.translate("manager.hair_no_candidates"))
    print(project_i18n.translate("manager.hair_opt_manual"))
    print(project_i18n.translate("manager.menu_opt_0"))

    user_choice = input(project_i18n.translate("manager.hair_prompt_choice")).strip()
    if user_choice == "0":
        return False

    chosen_hair_value = ""
    if user_choice == "1":
        chosen_hair_value = "auto"
    elif user_choice == "2":
        chosen_hair_value = "default"
    elif user_choice == "3":
        chosen_hair_value = "none"
    elif user_choice.lower() == "m":
        manual_raw = (
            input(project_i18n.translate("manager.hair_prompt_manual_path"))
            .strip()
            .strip('"')
            .strip("'")
        )
        if not manual_raw:
            return False
        manual_host = project_paths.to_host_path(manual_raw)
        if not manual_host.exists():
            print(project_i18n.translate("manager.hair_path_missing", path=manual_raw))
            return False
        chosen_hair_value = str(manual_host)
    else:
        try:
            numeric_choice = int(user_choice)
        except ValueError:
            print(project_i18n.translate("manager.invalid_option"))
            return False
        cand_index = numeric_choice - 4
        if cand_index < 0 or cand_index >= len(candidates):
            print(project_i18n.translate("manager.invalid_option"))
            return False
        chosen_hair_value = str(candidates[cand_index]["path"])

    scale_input = input(project_i18n.translate("manager.hair_prompt_scale")).strip()
    offset_input = input(project_i18n.translate("manager.hair_prompt_offset")).strip()

    saved_section = project_paths.set_character_custom_hair(
        chosen_protagonist,
        chosen_hair_value,
        hair_scale=scale_input if scale_input else None,
        hair_offset=offset_input if offset_input else None,
    )
    print(
        project_i18n.translate(
            "manager.hair_saved",
            hair=chosen_hair_value,
            section=saved_section,
        )
    )
    return True


def run_blendshape_cfg_export(
    target_avatars: List[str],
    output_override: Optional[str] = None,
    preserve_existing_cfg: bool = True,
) -> bool:
    """Export/sync FBX & Unity blendshapes into configs/*_blendshapes.cfg."""
    all_exported = True
    for char_section in target_avatars:
        single_override = (
            output_override if len(target_avatars) == 1 and output_override else None
        )
        exported_path = blendshape_helper.export_character_blendshapes_to_cfg(
            char_section,
            output_cfg_path=single_override,
            preserve_existing_cfg=preserve_existing_cfg,
        )
        if exported_path is not None:
            print(
                project_i18n.translate(
                    "manager.export_blendshapes_ok",
                    char=char_section,
                    path=exported_path,
                )
            )
        else:
            print(
                project_i18n.translate(
                    "manager.export_blendshapes_skipped",
                    char=char_section,
                )
            )
            all_exported = False
    return all_exported


def run_interactive_blendshape_sync() -> bool:
    """Interactively populate configs/*_blendshapes.cfg with all FBX blendshape channels."""
    print_section_header(project_i18n.translate("manager.blendshapes_header"))
    print(project_i18n.translate("manager.blendshapes_select_avatar"))
    avatars = list(project_paths.list_available_avatars())
    for opt_index, avatar_id in enumerate(avatars, start=1):
        print(f"  [{opt_index}] {project_i18n.translate(f'avatar.{avatar_id}')} ({avatar_id})")
    all_opt_index = len(avatars) + 1
    print(project_i18n.translate("manager.blendshapes_opt_all", opt=all_opt_index))
    print(project_i18n.translate("manager.menu_opt_0"))

    user_choice = input(project_i18n.translate("manager.blendshapes_prompt_choice")).strip()
    if user_choice == "0":
        return False
    if user_choice == str(all_opt_index):
        selected_avatars = avatars
    elif user_choice in {str(idx) for idx in range(1, len(avatars) + 1)}:
        selected_avatars = [avatars[int(user_choice) - 1]]
    else:
        print(project_i18n.translate("manager.invalid_option"))
        return False

    return run_blendshape_cfg_export(selected_avatars, preserve_existing_cfg=True)


def run_physbone_cfg_export(
    target_avatars: List[str],
    output_override: Optional[str] = None,
    preserve_existing_cfg: bool = True,
    override_marshmallow: Optional[bool] = None,
) -> bool:
    """Export/sync Unity VRCPhysBones (and optional Marshmallow PB) into configs/*_physbones.cfg."""
    all_exported = True
    for char_section in target_avatars:
        single_override = (
            output_override if len(target_avatars) == 1 and output_override else None
        )
        exported_path = physbone_helper.export_character_physbones_to_cfg(
            char_section,
            output_cfg_path=single_override,
            override_marshmallow=override_marshmallow,
            preserve_existing_cfg=preserve_existing_cfg,
        )
        if exported_path is not None:
            print(
                project_i18n.translate(
                    "manager.export_physbones_ok",
                    char=char_section,
                    path=exported_path,
                ),
                flush=True,
            )
        else:
            print(
                project_i18n.translate(
                    "manager.export_physbones_skipped",
                    char=char_section,
                ),
                flush=True,
            )
            all_exported = False
    return all_exported


def run_interactive_physbone_sync() -> bool:
    """Interactively populate configs/*_physbones.cfg from Unity scenes + Marshmallow PB."""
    print_section_header(project_i18n.translate("manager.physbones_header"))
    print(project_i18n.translate("manager.physbones_select_avatar"))
    avatars = list(project_paths.list_available_avatars())
    for opt_index, avatar_id in enumerate(avatars, start=1):
        print(f"  [{opt_index}] {project_i18n.translate(f'avatar.{avatar_id}')} ({avatar_id})")
    all_opt_index = len(avatars) + 1
    print(project_i18n.translate("manager.blendshapes_opt_all", opt=all_opt_index))
    print(project_i18n.translate("manager.menu_opt_0"))

    user_choice = input(project_i18n.translate("manager.physbones_prompt_choice")).strip()
    if user_choice == "0":
        return False
    if user_choice == str(all_opt_index):
        selected_avatars = avatars
    elif user_choice in {str(opt_index) for opt_index in range(1, len(avatars) + 1)}:
        selected_avatars = [avatars[int(user_choice) - 1]]
    else:
        print(project_i18n.translate("manager.invalid_option"))
        return False

    marsh_answer = input(
        project_i18n.translate("manager.physbones_prompt_marshmallow")
    ).strip()
    use_marshmallow = project_i18n.is_affirmative_answer(marsh_answer, default_yes=False)
    return run_physbone_cfg_export(
        selected_avatars,
        preserve_existing_cfg=False,
        override_marshmallow=use_marshmallow,
    )


def run_interactive_menu() -> None:
    """Display the interactive menu and orchestrate selected pipeline stages."""
    if setup_first_run.is_first_run_needed():
        print_section_header(project_i18n.translate("manager.first_run_detected"))
        print(project_i18n.translate("manager.first_run_missing_msg"))
        start_setup_answer = input(
            project_i18n.translate("manager.prompt_run_setup_now")
        ).strip()
        if project_i18n.is_affirmative_answer(start_setup_answer, default_yes=True):
            setup_ok = setup_first_run.run_first_run_setup(interactive=True)
            if not setup_ok:
                print(project_i18n.translate("manager.setup_incomplete_abort"))
                sys.exit(1)
            load_runtime_context(force_reload=True)

    context_dirty = True
    while True:
        separator_banner = "=" * 70
        print(f"\n{separator_banner}")
        print(project_i18n.translate("manager.menu_title"))
        print(f"{separator_banner}")
        print(project_i18n.translate("manager.menu_prompt_select"))
        if project_paths.has_project_config_file():
            if context_dirty:
                load_runtime_context(force_reload=True)
                context_dirty = False
            for opt_index, protagonist_key in enumerate(
                project_paths.list_available_protagonists(), start=1
            ):
                char_entry = CHARACTER_PIPELINE_REGISTRY[protagonist_key]
                print(
                    project_i18n.translate(
                        "manager.menu_opt_slot",
                        opt=opt_index,
                        protagonist=char_entry["protagonist_label"],
                        ped_name=char_entry["character_key"],
                        avatar=char_entry["avatar_label"],
                    )
                )
        else:
            print(project_i18n.translate("manager.menu_opt_1"))
            print(project_i18n.translate("manager.menu_opt_2"))
            print(project_i18n.translate("manager.menu_opt_3"))
        print(project_i18n.translate("manager.menu_opt_4"))
        print(project_i18n.translate("manager.menu_opt_5"))
        print(project_i18n.translate("manager.menu_opt_6"))
        print(project_i18n.translate("manager.menu_opt_7"))
        print(project_i18n.translate("manager.menu_opt_8"))
        print(project_i18n.translate("manager.menu_opt_9"))
        print(project_i18n.translate("manager.menu_opt_10"))
        print(project_i18n.translate("manager.menu_opt_0"))
        print(f"{'-' * 70}")

        user_menu_choice = input(
            project_i18n.translate("manager.menu_input_choice")
        ).strip()

        if user_menu_choice == "0":
            print(project_i18n.translate("manager.cancelled"))
            sys.exit(0)

        if user_menu_choice == "10":
            if not project_paths.has_project_config_file():
                print(project_i18n.translate("manager.missing_cfg_option6"))
                sys.exit(1)
            load_runtime_context(force_reload=True)
            context_dirty = False
            run_interactive_physbone_sync()
            continue

        if user_menu_choice == "9":
            if not project_paths.has_project_config_file():
                print(project_i18n.translate("manager.missing_cfg_option6"))
                sys.exit(1)
            load_runtime_context(force_reload=True)
            context_dirty = False
            run_interactive_blendshape_sync()
            continue

        if user_menu_choice == "8":
            if not project_paths.has_project_config_file():
                print(project_i18n.translate("manager.missing_cfg_option6"))
                sys.exit(1)
            run_interactive_hair_config()
            context_dirty = True
            continue

        if user_menu_choice == "7":
            if not project_paths.has_project_config_file():
                print(project_i18n.translate("manager.missing_cfg_option6"))
                sys.exit(1)
            run_interactive_avatar_swap()
            context_dirty = True
            continue

        if user_menu_choice == "6":
            setup_ok = setup_first_run.run_first_run_setup(interactive=True)
            sys.exit(0 if setup_ok else 1)

        if user_menu_choice == "5":
            load_runtime_context(force_reload=True)
            deploy_ok = execute_rpf_repack_and_deploy()
            sys.exit(0 if deploy_ok else 1)

        break

    if not project_paths.has_project_config_file():
        print(project_i18n.translate("manager.missing_cfg_option6"))
        sys.exit(1)
    load_runtime_context(force_reload=True)

    choice_to_characters_mapping = {
        "1": ["michael"],
        "2": ["franklin"],
        "3": ["trevor"],
        "4": ["michael", "franklin", "trevor"],
    }

    if user_menu_choice not in choice_to_characters_mapping:
        print(project_i18n.translate("manager.invalid_option"))
        sys.exit(1)

    selected_characters_list = choice_to_characters_mapping[user_menu_choice]

    print(project_i18n.translate("manager.stage_config_header"))
    prompt_build_textures = input(
        project_i18n.translate("manager.prompt_textures")
    ).strip()
    should_build_textures = project_i18n.is_affirmative_answer(
        prompt_build_textures, default_yes=True
    )

    prompt_build_blender = input(
        project_i18n.translate("manager.prompt_blender")
    ).strip()
    should_build_blender = project_i18n.is_affirmative_answer(
        prompt_build_blender, default_yes=True
    )

    prompt_apply_and_deploy = input(
        project_i18n.translate("manager.prompt_deploy")
    ).strip()
    should_apply_and_deploy = project_i18n.is_affirmative_answer(
        prompt_apply_and_deploy, default_yes=True
    )

    extra_interactive_blender_args: List[str] = []
    if should_build_blender:
        prompt_eye_blink = input(
            project_i18n.translate("manager.prompt_eye_blink")
        ).strip()
        if project_i18n.is_affirmative_answer(prompt_eye_blink, default_yes=True):
            extra_interactive_blender_args.append("--eye-blink")
        else:
            extra_interactive_blender_args.append("--no-eye-blink")

    # Execute the selected pipeline stages
    if should_build_textures:
        textures_success = execute_texture_generation(selected_characters_list)
        if not textures_success:
            print(project_i18n.translate("manager.abort_textures"))
            sys.exit(1)

    if should_build_blender:
        blender_success = execute_blender_build(
            selected_characters_list,
            extra_blender_args=extra_interactive_blender_args or None,
        )
        if not blender_success:
            print(project_i18n.translate("manager.abort_blender"))
            sys.exit(1)

    if should_apply_and_deploy:
        patch_success = execute_character_slot_patching(selected_characters_list)
        if not patch_success:
            print(project_i18n.translate("manager.abort_slots"))
            sys.exit(1)

        deploy_success = execute_rpf_repack_and_deploy()
        if not deploy_success:
            print(project_i18n.translate("manager.abort_repack"))
            sys.exit(1)

    print_section_header(project_i18n.translate("manager.pipeline_success_header"))
    print(project_i18n.translate("manager.pipeline_success_body"))


def main() -> None:
    """CLI entrypoint for automated or interactive mod orchestration."""
    project_i18n.set_active_language()
    argument_parser = argparse.ArgumentParser(
        description=project_i18n.translate("manager.cli_description")
    )
    argument_parser.add_argument(
        "--character",
        choices=["michael", "franklin", "trevor", "all"],
        default=None,
        help=project_i18n.translate("manager.cli_character"),
    )
    argument_parser.add_argument(
        "--avatar",
        default=None,
        help=project_i18n.translate("manager.cli_avatar"),
    )
    argument_parser.add_argument(
        "--michael-avatar",
        default=None,
        help=project_i18n.translate(
            "manager.cli_protagonist_avatar",
            protagonist=project_i18n.translate("protagonist.michael"),
        ),
    )
    argument_parser.add_argument(
        "--franklin-avatar",
        default=None,
        help=project_i18n.translate(
            "manager.cli_protagonist_avatar",
            protagonist=project_i18n.translate("protagonist.franklin"),
        ),
    )
    argument_parser.add_argument(
        "--trevor-avatar",
        default=None,
        help=project_i18n.translate(
            "manager.cli_protagonist_avatar",
            protagonist=project_i18n.translate("protagonist.trevor"),
        ),
    )
    argument_parser.add_argument(
        "--save-assignment",
        action="store_true",
        help=project_i18n.translate("manager.cli_save_assignment"),
    )
    argument_parser.add_argument(
        "--hair",
        default=None,
        help=project_i18n.translate("manager.cli_hair"),
    )
    argument_parser.add_argument(
        "--hair-mat",
        default=None,
        help=project_i18n.translate("manager.cli_hair_mat"),
    )
    argument_parser.add_argument(
        "--hair-tex",
        default=None,
        help=project_i18n.translate("manager.cli_hair_tex"),
    )
    argument_parser.add_argument(
        "--hair-scale",
        type=float,
        default=None,
        help=project_i18n.translate("manager.cli_hair_scale"),
    )
    argument_parser.add_argument(
        "--hair-offset",
        default=None,
        help=project_i18n.translate("manager.cli_hair_offset"),
    )
    argument_parser.add_argument(
        "--unity-scene",
        default=None,
        help=project_i18n.translate("common.unity_scene_cli_opt"),
    )
    argument_parser.add_argument(
        "--unity-avatar-name",
        default=None,
        help=project_i18n.translate("common.unity_avatar_cli_opt"),
    )
    argument_parser.add_argument(
        "--save-hair",
        action="store_true",
        help=project_i18n.translate("manager.cli_save_hair"),
    )
    argument_parser.add_argument(
        "--skip-textures",
        action="store_true",
        help=project_i18n.translate("manager.cli_skip_textures"),
    )
    argument_parser.add_argument(
        "--skip-blender",
        action="store_true",
        help=project_i18n.translate("manager.cli_skip_blender"),
    )
    argument_parser.add_argument(
        "--skip-deploy",
        action="store_true",
        help=project_i18n.translate("manager.cli_skip_deploy"),
    )
    argument_parser.add_argument(
        "--deploy-only",
        action="store_true",
        help=project_i18n.translate("manager.cli_deploy_only"),
    )
    argument_parser.add_argument(
        "--check-env",
        action="store_true",
        help=project_i18n.translate("manager.cli_check_env"),
    )
    argument_parser.add_argument(
        "--setup",
        action="store_true",
        help=project_i18n.translate("manager.cli_setup"),
    )
    argument_parser.add_argument(
        "--force-setup",
        action="store_true",
        help=project_i18n.translate("manager.cli_force_setup"),
    )
    argument_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help=project_i18n.translate("manager.cli_non_interactive"),
    )
    argument_parser.add_argument(
        "--lang",
        choices=["auto", "en", "ja", "pt"],
        default="auto",
        help=project_i18n.translate("common.language_option_help"),
    )
    argument_parser.add_argument(
        "--gtav-root",
        default=None,
        help=project_i18n.translate("setup.cli_gtav_root"),
    )
    argument_parser.add_argument(
        "--unity-assets",
        default=None,
        help=project_i18n.translate("setup.cli_unity_assets"),
    )
    argument_parser.add_argument(
        "--blender",
        default=None,
        help=project_i18n.translate("setup.cli_blender"),
    )
    argument_parser.add_argument(
        "--rage",
        default=None,
        help=project_i18n.translate("setup.cli_rage"),
    )
    argument_parser.add_argument(
        "--export-blendshapes",
        action="store_true",
        help=project_i18n.translate("manager.cli_export_blendshapes"),
    )
    argument_parser.add_argument(
        "--overwrite-from-unity",
        action="store_true",
        help=project_i18n.translate("manager.cli_overwrite_from_unity"),
    )
    argument_parser.add_argument(
        "--blendshapes-source",
        choices=["auto", "unity", "cfg"],
        default=None,
        help=project_i18n.translate("blendshapes.cli_source"),
    )
    argument_parser.add_argument(
        "--blendshapes-cfg",
        default=None,
        help=project_i18n.translate("blendshapes.cli_cfg"),
    )
    argument_parser.add_argument(
        "--export-physbones",
        action="store_true",
        help=project_i18n.translate("manager.cli_export_physbones"),
    )
    argument_parser.add_argument(
        "--overwrite-physbones-from-unity",
        action="store_true",
        help=project_i18n.translate("manager.cli_overwrite_physbones_from_unity"),
    )
    argument_parser.add_argument(
        "--physbones-source",
        choices=["auto", "unity", "cfg"],
        default=None,
        help=project_i18n.translate("physbones.cli_source"),
    )
    argument_parser.add_argument(
        "--physbones-cfg",
        default=None,
        help=project_i18n.translate("physbones.cli_cfg"),
    )
    argument_parser.add_argument(
        "--physbones-marshmallow",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=project_i18n.translate("physbones.cli_marshmallow"),
    )
    argument_parser.add_argument(
        "--blood-decals",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=project_i18n.translate("ped_damage.cli_blood_decals"),
    )
    argument_parser.add_argument(
        "--eye-blink",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=project_i18n.translate("eye_blink.cli_opt"),
    )
    argument_parser.add_argument(
        "--eye-blink-strength",
        type=float,
        default=None,
        help=project_i18n.translate("eye_blink.strength_cli_opt"),
    )
    argument_parser.add_argument(
        "--avatar-zip",
        default=None,
        help="Path to avatar .zip or .unitypackage archive",
    )
    argument_parser.add_argument(
        "--unity-project",
        default=None,
        help="Path to Unity project directory (containing Assets/) or .unity scene",
    )
    argument_parser.add_argument(
        "--download-blender",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Auto-download portable Blender 4.0.2 + Sollumz if missing",
    )
    argument_parser.add_argument(
        "--import-face-blendshapes",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Import facial blendshapes from Unity into .cfg (No zeroes face keys)",
    )
    argument_parser.add_argument(
        "--import-body-blendshapes",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Import body/outfit blendshapes from Unity into .cfg (No zeroes body keys)",
    )
    argument_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Detailed console output + timestamped log file in logs/",
    )

    parsed_arguments = argument_parser.parse_args()
    active_language = project_i18n.set_active_language(parsed_arguments.lang)
    os.environ[project_i18n.LANG_ENV_VAR] = active_language
    if parsed_arguments.verbose:
        os.environ["VRC2GTAV_VERBOSE"] = "1"
    import error_handler_helper as err_helper
    manager_logger = err_helper.PipelineLogger(
        verbose=bool(parsed_arguments.verbose),
        avatar_name=parsed_arguments.unity_avatar_name or parsed_arguments.character or "manager",
        stage_name="run_mod_manager",
        project_root=project_paths.get_project_root(),
    )

    # Export FBX & Unity blendshape presets to configs/*_blendshapes.cfg
    if parsed_arguments.export_blendshapes:
        if parsed_arguments.avatar:
            target_chars = [project_paths.normalize_avatar_id(parsed_arguments.avatar)]
        elif parsed_arguments.character in (None, "all"):
            target_chars = list(project_paths.list_available_avatars())
        else:
            target_chars = [parsed_arguments.character]
        all_exported = run_blendshape_cfg_export(
            target_chars,
            output_override=parsed_arguments.blendshapes_cfg,
            preserve_existing_cfg=not parsed_arguments.overwrite_from_unity,
        )
        sys.exit(0 if all_exported else 1)

    # Export Unity PhysBone (+ Marshmallow PB) presets to configs/*_physbones.cfg
    if parsed_arguments.export_physbones:
        if parsed_arguments.avatar:
            target_chars = [project_paths.normalize_avatar_id(parsed_arguments.avatar)]
        elif parsed_arguments.character in (None, "all"):
            target_chars = list(project_paths.list_available_avatars())
        else:
            target_chars = [parsed_arguments.character]
        all_exported = run_physbone_cfg_export(
            target_chars,
            output_override=parsed_arguments.physbones_cfg,
            preserve_existing_cfg=not parsed_arguments.overwrite_physbones_from_unity,
            override_marshmallow=parsed_arguments.physbones_marshmallow,
        )
        sys.exit(0 if all_exported else 1)

    avatar_overrides: Dict[str, str] = {}
    if parsed_arguments.avatar:
        normalized_avatar = project_paths.normalize_avatar_id(parsed_arguments.avatar)
        target_protagonists_for_avatar = (
            [parsed_arguments.character]
            if parsed_arguments.character in ("michael", "franklin", "trevor")
            else list(project_paths.list_available_protagonists())
        )
        for prot_key in target_protagonists_for_avatar:
            avatar_overrides[prot_key] = normalized_avatar
    for prot_key, arg_attr in (
        ("michael", "michael_avatar"),
        ("franklin", "franklin_avatar"),
        ("trevor", "trevor_avatar"),
    ):
        raw_override = getattr(parsed_arguments, arg_attr, None)
        if raw_override:
            avatar_overrides[prot_key] = project_paths.normalize_avatar_id(raw_override)

    # Explicit First-Run setup flow
    if parsed_arguments.setup:
        setup_target_char = (
            parsed_arguments.character
            if parsed_arguments.character in ("michael", "franklin", "trevor")
            else None
        )
        setup_ok = setup_first_run.run_first_run_setup(
            interactive=not parsed_arguments.non_interactive,
            force_reextract=parsed_arguments.force_setup,
            gtav_root_override=parsed_arguments.gtav_root,
            unity_assets_override=parsed_arguments.unity_assets,
            blender_override=parsed_arguments.blender,
            rage_override=parsed_arguments.rage,
            avatar_zip_override=parsed_arguments.avatar_zip,
            unity_project_override=parsed_arguments.unity_project,
            download_blender=parsed_arguments.download_blender,
            avatar_name_override=parsed_arguments.unity_avatar_name,
            target_character_override=setup_target_char,
            import_face_blendshapes=parsed_arguments.import_face_blendshapes,
            import_body_blendshapes=parsed_arguments.import_body_blendshapes,
            verbose=parsed_arguments.verbose,
        )
        if not setup_ok:
            sys.exit(1)
        if (
            parsed_arguments.character is None
            and not parsed_arguments.deploy_only
            and not parsed_arguments.check_env
            and not parsed_arguments.save_assignment
        ):
            sys.exit(0)

    if parsed_arguments.save_assignment and avatar_overrides and project_paths.has_project_config_file():
        for prot_key, chosen_avatar_id in avatar_overrides.items():
            project_paths.set_protagonist_avatar(prot_key, chosen_avatar_id)
            print(
                project_i18n.translate(
                    "manager.swap_saved",
                    protagonist=project_i18n.translate(f"protagonist.{prot_key}"),
                    avatar=project_i18n.translate(f"avatar.{chosen_avatar_id}"),
                )
            )
        if (
            parsed_arguments.character is None
            and not parsed_arguments.deploy_only
            and not parsed_arguments.check_env
        ):
            sys.exit(0)

    hair_save_target = (
        parsed_arguments.character
        if parsed_arguments.character in ("michael", "franklin", "trevor")
        else (parsed_arguments.avatar or "")
    )
    has_hair_save_request = bool(
        parsed_arguments.save_hair
        and parsed_arguments.hair is not None
        and hair_save_target
        and project_paths.has_project_config_file()
    )
    if has_hair_save_request:
        saved_section = project_paths.set_character_custom_hair(
            hair_save_target,
            parsed_arguments.hair,
            hair_mat=parsed_arguments.hair_mat,
            hair_tex=parsed_arguments.hair_tex,
            hair_scale=(
                str(parsed_arguments.hair_scale)
                if parsed_arguments.hair_scale is not None
                else None
            ),
            hair_offset=parsed_arguments.hair_offset,
        )
        print(
            project_i18n.translate(
                "manager.hair_saved",
                hair=parsed_arguments.hair,
                section=saved_section,
            )
        )
        if (
            parsed_arguments.character is None
            and not parsed_arguments.deploy_only
            and not parsed_arguments.check_env
        ):
            sys.exit(0)

    if parsed_arguments.avatar_zip or parsed_arguments.unity_project:
        import build_universal_avatar
        target_slot = (
            parsed_arguments.character
            if parsed_arguments.character in ("michael", "franklin", "trevor")
            else None
        )
        universal_argv: List[str] = []
        if parsed_arguments.avatar_zip:
            universal_argv.extend(["--avatar-zip", parsed_arguments.avatar_zip])
        if parsed_arguments.unity_project:
            universal_argv.extend(["--unity-project", parsed_arguments.unity_project])
        if parsed_arguments.unity_scene:
            universal_argv.extend(["--unity-scene", parsed_arguments.unity_scene])
        if parsed_arguments.unity_avatar_name:
            universal_argv.extend(["--avatar-name", parsed_arguments.unity_avatar_name])
        if target_slot:
            universal_argv.extend(["--target-character", target_slot])
        if parsed_arguments.import_face_blendshapes is True:
            universal_argv.append("--import-face-blendshapes")
        elif parsed_arguments.import_face_blendshapes is False:
            universal_argv.append("--no-import-face-blendshapes")
        if parsed_arguments.import_body_blendshapes is True:
            universal_argv.append("--import-body-blendshapes")
        elif parsed_arguments.import_body_blendshapes is False:
            universal_argv.append("--no-import-body-blendshapes")
        if parsed_arguments.download_blender:
            universal_argv.append("--auto-download-blender")
        if parsed_arguments.physbones_marshmallow:
            universal_argv.append("--physbones-marshmallow")
        if parsed_arguments.blood_decals is True:
            universal_argv.append("--blood-decals")
        elif parsed_arguments.blood_decals is False:
            universal_argv.append("--no-blood-decals")
        if parsed_arguments.eye_blink is True:
            universal_argv.append("--eye-blink")
        elif parsed_arguments.eye_blink is False:
            universal_argv.append("--no-eye-blink")
        if parsed_arguments.eye_blink_strength is not None:
            universal_argv.extend(
                ["--eye-blink-strength", str(parsed_arguments.eye_blink_strength)]
            )
        if not parsed_arguments.non_interactive:
            universal_argv.append("--interactive")
        if parsed_arguments.skip_blender:
            universal_argv.append("--prepare-only")
        if parsed_arguments.verbose:
            universal_argv.append("--verbose")
        univ_exit = build_universal_avatar.main(universal_argv)
        if univ_exit != 0:
            manager_logger.error("Universal Modular Avatar build failed.")
            sys.exit(univ_exit)
        if parsed_arguments.skip_deploy or parsed_arguments.skip_blender:
            sys.exit(0)

    # Interactive mode when no character/action flags were specified
    if (
        parsed_arguments.character is None
        and not parsed_arguments.deploy_only
        and not parsed_arguments.check_env
    ):
        if parsed_arguments.non_interactive:
            sys.exit(0)
        run_interactive_menu()
        sys.exit(0)

    if not project_paths.has_project_config_file() or setup_first_run.is_first_run_needed():
        print(project_i18n.translate("manager.auto_setup_info"))
        auto_target_char = (
            parsed_arguments.character
            if parsed_arguments.character in ("michael", "franklin", "trevor")
            else None
        )
        setup_ok = setup_first_run.run_first_run_setup(
            interactive=False,
            force_reextract=False,
            gtav_root_override=parsed_arguments.gtav_root,
            unity_assets_override=parsed_arguments.unity_assets,
            blender_override=parsed_arguments.blender,
            rage_override=parsed_arguments.rage,
            avatar_zip_override=parsed_arguments.avatar_zip,
            unity_project_override=parsed_arguments.unity_project,
            download_blender=parsed_arguments.download_blender,
            avatar_name_override=parsed_arguments.unity_avatar_name,
            target_character_override=auto_target_char,
            import_face_blendshapes=parsed_arguments.import_face_blendshapes,
            import_body_blendshapes=parsed_arguments.import_body_blendshapes,
            verbose=parsed_arguments.verbose,
        )
        if not setup_ok:
            print(project_i18n.translate("manager.auto_setup_failed"))
            sys.exit(1)

    if parsed_arguments.save_assignment and avatar_overrides:
        for prot_key, chosen_avatar_id in avatar_overrides.items():
            project_paths.set_protagonist_avatar(prot_key, chosen_avatar_id)
            print(
                project_i18n.translate(
                    "manager.swap_saved",
                    protagonist=project_i18n.translate(f"protagonist.{prot_key}"),
                    avatar=project_i18n.translate(f"avatar.{chosen_avatar_id}"),
                )
            )

    load_runtime_context(force_reload=True, avatar_overrides=avatar_overrides)

    if parsed_arguments.check_env:
        prerequisites_valid = verify_system_prerequisites()
        setup_first_run.print_setup_diagnostics()
        sys.exit(0 if prerequisites_valid else 1)

    if parsed_arguments.deploy_only:
        deploy_ok = execute_rpf_repack_and_deploy()
        sys.exit(0 if deploy_ok else 1)

    if parsed_arguments.character == "all":
        selected_characters_list = ["michael", "franklin", "trevor"]
    else:
        selected_characters_list = [parsed_arguments.character]

    verify_system_prerequisites()

    extra_hair_shared_args: List[str] = []
    for flag_name, flag_val in (
        ("--hair", parsed_arguments.hair),
        ("--hair-mat", parsed_arguments.hair_mat),
        ("--hair-tex", parsed_arguments.hair_tex),
        ("--unity-scene", parsed_arguments.unity_scene),
        ("--unity-avatar-name", parsed_arguments.unity_avatar_name),
    ):
        if flag_val is not None and str(flag_val) != "":
            extra_hair_shared_args.extend([flag_name, str(flag_val)])

    if not parsed_arguments.skip_textures:
        textures_status = execute_texture_generation(
            selected_characters_list,
            extra_atlas_args=extra_hair_shared_args,
        )
        if not textures_status:
            sys.exit(1)

    if not parsed_arguments.skip_blender:
        extra_blender_args: List[str] = list(extra_hair_shared_args)
        if parsed_arguments.hair_scale is not None:
            extra_blender_args.extend(["--hair-scale", str(parsed_arguments.hair_scale)])
        if parsed_arguments.hair_offset:
            extra_blender_args.extend(["--hair-offset", parsed_arguments.hair_offset])
        if parsed_arguments.blendshapes_source:
            extra_blender_args.extend(
                ["--blendshapes-source", parsed_arguments.blendshapes_source]
            )
        if parsed_arguments.blendshapes_cfg and len(selected_characters_list) == 1:
            extra_blender_args.extend(
                ["--blendshapes-cfg", parsed_arguments.blendshapes_cfg]
            )
        if parsed_arguments.physbones_source:
            extra_blender_args.extend(
                ["--physbones-source", parsed_arguments.physbones_source]
            )
        if parsed_arguments.physbones_cfg and len(selected_characters_list) == 1:
            extra_blender_args.extend(
                ["--physbones-cfg", parsed_arguments.physbones_cfg]
            )
        if parsed_arguments.physbones_marshmallow is True:
            extra_blender_args.append("--physbones-marshmallow")
        elif parsed_arguments.physbones_marshmallow is False:
            extra_blender_args.append("--no-physbones-marshmallow")
        if parsed_arguments.blood_decals is True:
            extra_blender_args.append("--blood-decals")
        elif parsed_arguments.blood_decals is False:
            extra_blender_args.append("--no-blood-decals")
        if parsed_arguments.eye_blink is True:
            extra_blender_args.append("--eye-blink")
        elif parsed_arguments.eye_blink is False:
            extra_blender_args.append("--no-eye-blink")
        if parsed_arguments.eye_blink_strength is not None:
            extra_blender_args.extend(
                ["--eye-blink-strength", str(parsed_arguments.eye_blink_strength)]
            )
        blender_status = execute_blender_build(
            selected_characters_list,
            extra_blender_args=extra_blender_args,
        )
        if not blender_status:
            sys.exit(1)

    if not parsed_arguments.skip_deploy:
        patch_status = execute_character_slot_patching(selected_characters_list)
        if not patch_status:
            sys.exit(1)

        repack_status = execute_rpf_repack_and_deploy()
        if not repack_status:
            sys.exit(1)

    print_section_header(project_i18n.translate("manager.cli_automated_done"))


if __name__ == "__main__":
    main()
