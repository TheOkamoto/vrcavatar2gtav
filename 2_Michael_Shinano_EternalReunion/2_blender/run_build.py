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
    parsed_args = parser.parse_args()
    if parsed_args.lang and parsed_args.lang != "auto":
        os.environ[i18n.LANG_ENV_VAR] = parsed_args.lang
        i18n.set_active_language(parsed_args.lang)

    project_paths.ensure_character_skeleton_yft("michael")
    michael_cfg = project_paths.get_character_paths("michael")
    blender_script = michael_cfg["blender_script"]
    if not blender_script.exists():
        print(i18n.translate("michael.blender_missing", path=blender_script))
        return 1

    blender_command, blender_env = project_paths.build_blender_command(blender_script)
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
