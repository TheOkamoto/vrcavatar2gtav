#!/usr/bin/env python3
"""
run_pipeline.py
===============
Executa a pipeline completa de Miltina Maid (Trevor - player_two) utilizando
exclusivamente os caminhos definidos em vrc2gtav.cfg:
  1. Gera o texture atlas 2K e compila o .ytd
  2. Executa build_trevor_miltina.py no Blender e gera preview renders
  3. Renderiza preview no RAGE e copia capturas se o diretorio de artefatos existir
  4. Aplica os arquivos nos slots do Trevor e executa o repack/deploy RPF
"""

import shutil
import subprocess
import sys
from pathlib import Path
from PIL import Image

_CURRENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CURRENT_DIR.parent.parent
for _tools_dir in (_REPO_ROOT / "scripts" / "common_tools", _REPO_ROOT / "_deploy_tools"):
    if _tools_dir.is_dir() and str(_tools_dir) not in sys.path:
        sys.path.insert(0, str(_tools_dir))

import vrc2gtav_paths as project_paths


def main() -> int:
    trevor_cfg = project_paths.get_character_paths("trevor")
    python_exe = project_paths.get_python_exe()
    rage_cli = project_paths.get_rage_cli()
    artifacts_dir = project_paths.get_artifacts_dir()
    renders_source = project_paths.get_renders_output_dir()
    staging_dir = project_paths.get_staging_dir()

    # 1. Gerar Atlas 2K e .ytd
    print("[INFO] Gerando texture atlas 2K da Miltina...")
    atlas_script = Path(trevor_cfg["atlas_script"])
    if not atlas_script.exists():
        print(f"[ERRO] Script de atlas nao encontrado: {atlas_script}")
        return 1
    subprocess.run([python_exe, str(atlas_script)], check=True)

    # 2. Compilar modelo no Blender + renderizar previews
    blender_script = Path(trevor_cfg["blender_script"])
    if not blender_script.exists():
        print(f"[ERRO] Script Blender nao encontrado: {blender_script}")
        return 1
    blender_cmd, blender_env = project_paths.build_blender_command(blender_script)
    print("[INFO] Executando build e render no Blender...")
    subprocess.run(
        blender_cmd,
        stdin=subprocess.DEVNULL,
        env=blender_env,
        check=True,
    )

    if artifacts_dir.is_dir():
        for render_name in ("miltina_blender_face.png", "miltina_blender_full.png"):
            source_render = renders_source / render_name
            if source_render.exists():
                shutil.copy2(source_render, artifacts_dir / render_name)
                print(f"[OK] Render copiado para artifacts: {render_name}")

    # 3. Preview no RAGE Engine (opcional se modelos e .ytd existirem)
    ydd_path = Path(trevor_cfg["target_model_ydd"])
    ytd_path = Path(trevor_cfg["ytd_file"])
    if not ydd_path.exists() or not ytd_path.exists():
        print(f"[ERRO] Arquivos compilados ausentes: {ydd_path} / {ytd_path}")
        return 1

    rpf_stage_dir = staging_dir / "miltina_preview_rpf_stage"
    shutil.rmtree(rpf_stage_dir, ignore_errors=True)
    rpf_stage_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ydd_path, rpf_stage_dir / ydd_path.name)
    shutil.copy2(ytd_path, rpf_stage_dir / ytd_path.name)

    rpf_output_path = Path(trevor_cfg["preview_rpf"])
    subprocess.run(
        [rage_cli, "create", "-o", str(rpf_output_path), str(rpf_stage_dir)],
        check=True,
    )

    rage_render_dir = renders_source / "miltina_rage_renders"
    rage_render_dir.mkdir(parents=True, exist_ok=True)
    print("[INFO] Gerando preview de render no RAGE...")
    subprocess.run(
        [
            rage_cli,
            "render",
            str(rpf_output_path),
            "--all-angles",
            "-o",
            str(rage_render_dir),
            ydd_path.name,
        ],
        check=True,
    )

    if artifacts_dir.is_dir():
        for filename in rage_render_dir.iterdir():
            if filename.suffix.lower() == ".png":
                dest_name = f"miltina_rage_{filename.name}"
                shutil.copy2(filename, artifacts_dir / dest_name)
                print(f"[OK] Captura RAGE copiada para artifacts: {dest_name}")

        front_screenshot = rage_render_dir / f"{ydd_path.stem}_front.png"
        if front_screenshot.exists():
            crop_dest = artifacts_dir / "miltina_rage_head_crop.png"
            image_obj = Image.open(front_screenshot)
            width_px, height_px = image_obj.size
            cropped_img = image_obj.crop(
                (int(width_px * 0.25), 0, int(width_px * 0.75), int(height_px * 0.42))
            )
            cropped_img.save(crop_dest)
            print("[OK] Gerado recorte do rosto RAGE: miltina_rage_head_crop.png")

    # 4. Aplicar modelo + texturas nos slots do Trevor e fazer deploy RPF
    print("[INFO] Aplicando Miltina aos slots do Trevor...")
    apply_characters_script = project_paths.get_config_path(
        "common_assets", "apply_characters_script"
    )
    subprocess.run(
        [python_exe, str(apply_characters_script), "--character", str(trevor_cfg["ped_name"])],
        check=True,
    )

    print("[INFO] Repacotando RPFs e instalando no diretorio mods do GTA V...")
    repack_script = project_paths.get_config_path(
        "common_assets", "repack_deploy_script"
    )
    subprocess.run([python_exe, str(repack_script)], check=True)

    print("[SUCESSO] Pipeline completa da Miltina finalizada com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
