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
    parsed_args = arg_parser.parse_args()
    active_lang = project_i18n.set_active_language(parsed_args.lang)
    os.environ[project_i18n.LANG_ENV_VAR] = active_lang

    project_paths.ensure_character_skeleton_yft("franklin")
    franklin_cfg = project_paths.get_character_paths("franklin")
    blender_script = Path(franklin_cfg["blender_script"])
    if not blender_script.exists():
        print(
            project_i18n.translate(
                "franklin.blender_script_missing", path=blender_script
            )
        )
        return 1

    blender_command, blender_env = project_paths.build_blender_command(blender_script)
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
