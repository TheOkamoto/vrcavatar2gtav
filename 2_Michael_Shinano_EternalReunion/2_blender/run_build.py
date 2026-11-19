#!/usr/bin/env python3
"""
run_build_er.py
===============
Executes the Shinano Eternal Reunion (Michael) Blender compilation using the
paths configured in vrc2gtav.cfg.
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

import vrc2gtav_i18n as i18n
import vrc2gtav_paths as project_paths


def resolve_startup_language() -> None:
    """Resolve UI language from CLI arguments, environment variables, or config."""
    configured_language = None
    try:
        configured_language = project_paths.get_configured_language()
    except FileNotFoundError:
        configured_language = None
    i18n.set_active_language(configured_language, cli_args=sys.argv[1:])


def main() -> int:
    """Run the Blender build script configured for Michael (Eternal Reunion)."""
    resolve_startup_language()
    parser = argparse.ArgumentParser(description=i18n.translate("michael.run_desc"))
    parser.add_argument(
        "--lang",
        choices=list(i18n.SUPPORTED_LANGUAGES) + ["auto"],
        default=None,
        help=i18n.translate("common.language_option_help"),
    )
    parser.add_argument(
        "--target-character",
        default="michael",
        help=i18n.translate("trevor.build.arg_target_char"),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
    )
    parser.add_argument(
        "--texture-dir",
        default=None,
    )
    parser.add_argument(
        "--hair",
        default=None,
        help=i18n.translate("common.hair_cli_opt"),
    )
    parser.add_argument(
        "--hair-mat",
        default=None,
        help=i18n.translate("common.hair_mat_cli_opt"),
    )
    parser.add_argument(
        "--hair-tex",
        default=None,
        help=i18n.translate("common.hair_tex_cli_opt"),
    )
    parser.add_argument(
        "--hair-scale",
        type=float,
        default=None,
        help=i18n.translate("common.hair_scale_cli_opt"),
    )
    parser.add_argument(
        "--hair-offset",
        default=None,
        help=i18n.translate("common.hair_offset_cli_opt"),
    )
    parser.add_argument(
        "--unity-scene",
        default=None,
        help=i18n.translate("common.unity_scene_cli_opt"),
    )
    parser.add_argument(
        "--unity-avatar-name",
        default=None,
        help=i18n.translate("common.unity_avatar_cli_opt"),
    )
    parser.add_argument(
        "--blendshapes-cfg",
        default=None,
        help=i18n.translate("blendshapes.cli_cfg"),
    )
    parser.add_argument(
        "--blendshapes-source",
        choices=["auto", "unity", "cfg"],
        default=None,
        help=i18n.translate("blendshapes.cli_source"),
    )
    parser.add_argument(
        "--save-blendshapes-cfg",
        default=None,
        help=i18n.translate("blendshapes.cli_save_cfg"),
    )
    parser.add_argument(
        "--physbones-cfg",
        default=None,
        help=i18n.translate("physbones.cli_cfg"),
    )
    parser.add_argument(
        "--physbones-source",
        choices=["auto", "unity", "cfg"],
        default=None,
        help=i18n.translate("physbones.cli_source"),
    )
    parser.add_argument(
        "--save-physbones-cfg",
        default=None,
        help=i18n.translate("physbones.cli_save_cfg"),
    )
    parser.add_argument(
        "--physbones-marshmallow",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=i18n.translate("physbones.cli_marshmallow"),
    )
    parser.add_argument(
        "--blood-decals",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=i18n.translate("ped_damage.cli_blood_decals"),
    )
    parser.add_argument(
        "--eye-blink",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=i18n.translate("eye_blink.cli_opt"),
    )
    parsed_args = parser.parse_args()
    if parsed_args.lang and parsed_args.lang != "auto":
        os.environ[i18n.LANG_ENV_VAR] = parsed_args.lang
        i18n.set_active_language(parsed_args.lang)

    target_protagonist = project_paths.normalize_protagonist_key(
        parsed_args.target_character
    )
    project_paths.ensure_character_skeleton_yft(target_protagonist)
    michael_cfg = project_paths.get_character_paths(
        target_protagonist,
        avatar_override="shinano_er",
    )
    blender_script = michael_cfg["blender_script"]
    if not blender_script.exists():
        print(i18n.translate("michael.blender_missing", path=blender_script))
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
    if parsed_args.blood_decals is True:
        extra_blender_args.append("--blood-decals")
    elif parsed_args.blood_decals is False:
        extra_blender_args.append("--no-blood-decals")
    if parsed_args.eye_blink is True:
        extra_blender_args.append("--eye-blink")
    elif parsed_args.eye_blink is False:
        extra_blender_args.append("--no-eye-blink")

    blender_command, blender_env = project_paths.build_blender_command(
        blender_script,
        extra_arguments=extra_blender_args,
    )
    print(i18n.translate("michael.running_blender", command=" ".join(blender_command)))
    result = subprocess.run(
        blender_command,
        stdin=subprocess.DEVNULL,
        env=blender_env,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
