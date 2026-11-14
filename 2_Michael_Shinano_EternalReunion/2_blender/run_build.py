#!/usr/bin/env python3
"""
run_build_er.py
===============
Executa a compilacao da Shinano Eternal Reunion (Michael) no Blender usando
todos os caminhos configurados em vrc2gtav.cfg.
"""

import subprocess
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
for tools_dir in (REPO_ROOT / "scripts" / "common_tools", REPO_ROOT / "_deploy_tools"):
    if tools_dir.is_dir() and str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))

import vrc2gtav_paths as project_paths


def main() -> int:
    project_paths.ensure_character_skeleton_yft("michael")
    michael_cfg = project_paths.get_character_paths("michael")
    blender_script = michael_cfg["blender_script"]
    if not blender_script.exists():
        print(f"[ERRO] Script Blender nao encontrado: {blender_script}")
        return 1

    blender_command, blender_env = project_paths.build_blender_command(blender_script)
    print(f"[INFO] Executando Blender: {' '.join(blender_command)}")
    result = subprocess.run(
        blender_command,
        stdin=subprocess.DEVNULL,
        env=blender_env,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
