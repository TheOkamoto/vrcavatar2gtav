#!/usr/bin/env python3
"""
run_build_franklin.py
=====================
Run the Blender build for Shinano Casual (Franklin - player_one) using paths
configured in vrc2gtav.cfg.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
for tools_dir in (REPO_ROOT / "scripts" / "common_tools", REPO_ROOT / "_deploy_tools"):
    if tools_dir.is_dir() and str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))

import vrc2gtav_i18n as project_i18n
import vrc2gtav_paths as project_paths


def main() -> int:
    """Resolve Franklin paths and invoke Blender for avatar compilation."""
    project_i18n.set_active_language()
    arg_parser = argparse.ArgumentParser(
        description=project_i18n.translate("franklin.runner_description")
    )
    arg_parser.add_argument(
        "--lang",
        choices=["auto", "en", "ja", "pt"],
        default="auto",
        help=project_i18n.translate("common.language_option_help"),
    )
    arg_parser.add_argument(
        "--target-character",
        default="franklin",
        help=project_i18n.translate("franklin.build.arg_target_char"),
    )
    arg_parser.add_argument(
        "--output-dir",
        default=None,
    )
    arg_parser.add_argument(
        "--texture-dir",
        default=None,
    )
    arg_parser.add_argument(
        "--hair",
        default=None,
        help=project_i18n.translate("common.hair_cli_opt"),
    )
    arg_parser.add_argument(
        "--hair-mat",
        default=None,
        help=project_i18n.translate("common.hair_mat_cli_opt"),
    )
    arg_parser.add_argument(
        "--hair-tex",
        default=None,
        help=project_i18n.translate("common.hair_tex_cli_opt"),
    )
    arg_parser.add_argument(
        "--hair-scale",
        type=float,
        default=None,
        help=project_i18n.translate("common.hair_scale_cli_opt"),
    )
    arg_parser.add_argument(
        "--hair-offset",
        default=None,
        help=project_i18n.translate("common.hair_offset_cli_opt"),
    )
    arg_parser.add_argument(
        "--unity-scene",
        default=None,
        help=project_i18n.translate("common.unity_scene_cli_opt"),
    )
    arg_parser.add_argument(
        "--unity-avatar-name",
        default=None,
        help=project_i18n.translate("common.unity_avatar_cli_opt"),
    )
    arg_parser.add_argument(
        "--blendshapes-cfg",
        default=None,
        help=project_i18n.translate("blendshapes.cli_cfg"),
    )
    arg_parser.add_argument(
        "--blendshapes-source",
        choices=["auto", "unity", "cfg"],
        default=None,
        help=project_i18n.translate("blendshapes.cli_source"),
    )
    arg_parser.add_argument(
        "--save-blendshapes-cfg",
        default=None,
        help=project_i18n.translate("blendshapes.cli_save_cfg"),
    )
    arg_parser.add_argument(
        "--physbones-cfg",
        default=None,
        help=project_i18n.translate("physbones.cli_cfg"),
    )
    arg_parser.add_argument(
        "--physbones-source",
        choices=["auto", "unity", "cfg"],
        default=None,
        help=project_i18n.translate("physbones.cli_source"),
    )
    arg_parser.add_argument(
        "--save-physbones-cfg",
        default=None,
        help=project_i18n.translate("physbones.cli_save_cfg"),
    )
    arg_parser.add_argument(
        "--physbones-marshmallow",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=project_i18n.translate("physbones.cli_marshmallow"),
    )
    parsed_args = arg_parser.parse_args()
    active_lang = project_i18n.set_active_language(parsed_args.lang)
    os.environ[project_i18n.LANG_ENV_VAR] = active_lang

    target_protagonist = project_paths.normalize_protagonist_key(
        parsed_args.target_character
    )
    project_paths.ensure_character_skeleton_yft(target_protagonist)
    franklin_cfg = project_paths.get_character_paths(
        target_protagonist,
        avatar_override="shinano_casual",
    )
    blender_script = Path(franklin_cfg["blender_script"])
    if not blender_script.exists():
        print(
            project_i18n.translate(
                "franklin.blender_script_missing", path=blender_script
            )
        )
        return 1

    extra_blender_args = ["--target-character", target_protagonist]
    for flag_name, flag_val in (
        ("--output-dir", parsed_args.output_dir),
        ("--texture-dir", parsed_args.texture_dir),
        ("--hair", parsed_args.hair),
        ("--hair-mat", parsed_args.hair_mat),
        ("--hair-tex", parsed_args.hair_tex),
        ("--hair-offset", parsed_args.hair_offset),
        ("--unity-scene", parsed_args.unity_scene),
        ("--unity-avatar-name", parsed_args.unity_avatar_name),
        ("--blendshapes-cfg", parsed_args.blendshapes_cfg),
        ("--blendshapes-source", parsed_args.blendshapes_source),
        ("--save-blendshapes-cfg", parsed_args.save_blendshapes_cfg),
        ("--physbones-cfg", parsed_args.physbones_cfg),
        ("--physbones-source", parsed_args.physbones_source),
        ("--save-physbones-cfg", parsed_args.save_physbones_cfg),
    ):
        if flag_val:
            extra_blender_args.extend([flag_name, str(flag_val)])
    if parsed_args.hair_scale is not None:
        extra_blender_args.extend(["--hair-scale", str(parsed_args.hair_scale)])
    if parsed_args.physbones_marshmallow is True:
        extra_blender_args.append("--physbones-marshmallow")
    elif parsed_args.physbones_marshmallow is False:
        extra_blender_args.append("--no-physbones-marshmallow")

    blender_command, blender_env = project_paths.build_blender_command(
        blender_script,
        extra_arguments=extra_blender_args,
    )
    print(
        project_i18n.translate(
            "franklin.running_blender", command=" ".join(blender_command)
        )
    )
    result = subprocess.run(
        blender_command,
        stdin=subprocess.DEVNULL,
        env=blender_env,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
