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
    import setup_first_run
    import vrc2gtav_i18n as project_i18n
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import setup_first_run
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


def load_runtime_context(force_reload: bool = False) -> None:
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

    MICHAEL_CFG = project_paths.get_character_paths("michael")
    FRANKLIN_CFG = project_paths.get_character_paths("franklin")
    TREVOR_CFG = project_paths.get_character_paths("trevor")

    CHARACTER_PIPELINE_REGISTRY = {
        "michael": {
            "character_key": str(MICHAEL_CFG["ped_name"]),
            "display_name": "Michael De Santa -> Shinano Eternal Reunion",
            "folder_name": MICHAEL_CFG["character_dir"].name,
            "texture_script": MICHAEL_CFG["atlas_script"],
            "blender_script": MICHAEL_CFG["blender_script"],
        },
        "franklin": {
            "character_key": str(FRANKLIN_CFG["ped_name"]),
            "display_name": "Franklin Clinton -> Shinano Casual",
            "folder_name": FRANKLIN_CFG["character_dir"].name,
            "texture_script": FRANKLIN_CFG["atlas_script"],
            "blender_script": FRANKLIN_CFG["blender_script"],
        },
        "trevor": {
            "character_key": str(TREVOR_CFG["ped_name"]),
            "display_name": "Trevor Philips -> Miltina Maid",
            "folder_name": TREVOR_CFG["character_dir"].name,
            "texture_script": TREVOR_CFG["atlas_script"],
            "blender_script": TREVOR_CFG["blender_script"],
        },
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
) -> bool:
    """
    Execute a subprocess safely while streaming salient progress lines and
    reporting detailed failure diagnostics if the command returns non-zero.
    """
    print(project_i18n.translate("manager.subcmd_starting", task=task_description))
    start_timestamp = time.time()
    captured_output_lines: List[str] = []
    effective_env = _build_subprocess_env(custom_environment)

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

        if process_execution.stdout is not None:
            for raw_output_line in process_execution.stdout:
                stripped_line = raw_output_line.rstrip()
                if not stripped_line:
                    continue
                captured_output_lines.append(stripped_line)

                if any(
                    status_marker in stripped_line
                    for status_marker in SUBCOMMAND_STATUS_MARKERS
                ):
                    print(f"    {stripped_line}")

        process_execution.wait()
        elapsed_seconds = time.time() - start_timestamp

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


def execute_texture_generation(selected_character_keys: List[str]) -> bool:
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

        command_list = [PYTHON_EXECUTABLE, str(script_path)]
        task_label = project_i18n.translate(
            "manager.generating_atlas_task",
            display_name=character_data["display_name"],
        )
        success_status = execute_subcommand(command_list, task_label)
        if not success_status:
            return False

    return True


def execute_blender_build(selected_character_keys: List[str]) -> bool:
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

        blender_command_list, blender_env = project_paths.build_blender_command(
            script_path
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

    ped_identifiers_list = [
        str(CHARACTER_PIPELINE_REGISTRY[character_key]["character_key"])
        for character_key in selected_character_keys
    ]

    for ped_identifier in ped_identifiers_list:
        command_list = [
            PYTHON_EXECUTABLE,
            str(apply_script_path),
            "--character",
            ped_identifier,
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

    separator_banner = "=" * 70
    print(f"\n{separator_banner}")
    print(project_i18n.translate("manager.menu_title"))
    print(f"{separator_banner}")
    print(project_i18n.translate("manager.menu_prompt_select"))
    print(project_i18n.translate("manager.menu_opt_1"))
    print(project_i18n.translate("manager.menu_opt_2"))
    print(project_i18n.translate("manager.menu_opt_3"))
    print(project_i18n.translate("manager.menu_opt_4"))
    print(project_i18n.translate("manager.menu_opt_5"))
    print(project_i18n.translate("manager.menu_opt_6"))
    print(project_i18n.translate("manager.menu_opt_0"))
    print(f"{'-' * 70}")

    user_menu_choice = input(
        project_i18n.translate("manager.menu_input_choice")
    ).strip()

    if user_menu_choice == "0":
        print(project_i18n.translate("manager.cancelled"))
        sys.exit(0)

    if user_menu_choice == "6":
        setup_ok = setup_first_run.run_first_run_setup(interactive=True)
        sys.exit(0 if setup_ok else 1)

    if user_menu_choice == "5":
        load_runtime_context(force_reload=True)
        execute_rpf_repack_and_deploy()
        sys.exit(0)

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

    # Execute the selected pipeline stages
    if should_build_textures:
        textures_success = execute_texture_generation(selected_characters_list)
        if not textures_success:
            print(project_i18n.translate("manager.abort_textures"))
            sys.exit(1)

    if should_build_blender:
        blender_success = execute_blender_build(selected_characters_list)
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

    parsed_arguments = argument_parser.parse_args()
    active_language = project_i18n.set_active_language(parsed_arguments.lang)
    os.environ[project_i18n.LANG_ENV_VAR] = active_language

    # Explicit First-Run setup flow
    if parsed_arguments.setup:
        setup_ok = setup_first_run.run_first_run_setup(
            interactive=not parsed_arguments.non_interactive,
            force_reextract=parsed_arguments.force_setup,
            gtav_root_override=parsed_arguments.gtav_root,
            unity_assets_override=parsed_arguments.unity_assets,
            blender_override=parsed_arguments.blender,
            rage_override=parsed_arguments.rage,
        )
        if not setup_ok:
            sys.exit(1)
        if (
            parsed_arguments.character is None
            and not parsed_arguments.deploy_only
            and not parsed_arguments.check_env
        ):
            sys.exit(0)

    # Interactive mode when no character/action flags were specified
    if (
        parsed_arguments.character is None
        and not parsed_arguments.deploy_only
        and not parsed_arguments.check_env
    ):
        run_interactive_menu()
        sys.exit(0)

    if not project_paths.has_project_config_file() or setup_first_run.is_first_run_needed():
        print(project_i18n.translate("manager.auto_setup_info"))
        setup_ok = setup_first_run.run_first_run_setup(
            interactive=False,
            force_reextract=False,
            gtav_root_override=parsed_arguments.gtav_root,
            unity_assets_override=parsed_arguments.unity_assets,
            blender_override=parsed_arguments.blender,
            rage_override=parsed_arguments.rage,
        )
        if not setup_ok:
            print(project_i18n.translate("manager.auto_setup_failed"))
            sys.exit(1)

    load_runtime_context(force_reload=True)

    if parsed_arguments.check_env:
        prerequisites_valid = verify_system_prerequisites()
        setup_first_run.print_setup_diagnostics()
        sys.exit(0 if prerequisites_valid else 1)

    if parsed_arguments.deploy_only:
        execute_rpf_repack_and_deploy()
        sys.exit(0)

    if parsed_arguments.character == "all":
        selected_characters_list = ["michael", "franklin", "trevor"]
    else:
        selected_characters_list = [parsed_arguments.character]

    verify_system_prerequisites()

    if not parsed_arguments.skip_textures:
        textures_status = execute_texture_generation(selected_characters_list)
        if not textures_status:
            sys.exit(1)

    if not parsed_arguments.skip_blender:
        blender_status = execute_blender_build(selected_characters_list)
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
