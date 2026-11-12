#!/usr/bin/env python3
"""
generate_miltina_atlas.py
=========================
Gera o Texture Atlas 2x2 unificado de 2048x2048 pixels para a Miltina Maid no GTA V (Trevor):
  1. Quadrante Superior Esquerdo (0, 0): Rosto com olhos azuis customizados e iluminacao suave.
  2. Quadrante Superior Direito (1, 0):  Corpo com tonalidade de pele consistente.
  3. Quadrante Inferior Esquerdo (0, 1): Traje de empregada (vestido e avental).
  4. Quadrante Inferior Direito (1, 1):  Cabelo azul safira vibrante.

Regras de Implementacao:
  - Zero hardcode de caminhos de disco.
  - Zero variaveis de uma ou duas letras.
  - Zero emojis (mensagens formatadas com marcadores ASCII padronizados).
  - Tratamento rigoroso de erros e excecoes.
"""

import os
import subprocess
import sys
from pathlib import Path
import numpy as numpy_lib
from PIL import Image

# Resolucao dinamica de caminhos multiplataforma (compativel com ambos espelhos)
_CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_CANDIDATE = _CURRENT_SCRIPT_DIR.parent.parent
for _tools_candidate in (
    _CURRENT_SCRIPT_DIR.parent / "common_tools",
    _REPO_ROOT_CANDIDATE / "scripts" / "common_tools",
    _REPO_ROOT_CANDIDATE / "_deploy_tools",
):
    if _tools_candidate.is_dir() and str(_tools_candidate) not in sys.path:
        sys.path.insert(0, str(_tools_candidate))

import vrc2gtav_paths as project_paths


def generate_miltina_texture_atlas() -> bool:
    """
    Carrega as texturas originais definidas em vrc2gtav.cfg [trevor], ajusta curvas
    de luminosidade, aplica o tom azul safira no cabelo e compoe o atlas 2K.
    """
    try:
        trevor_cfg = project_paths.get_character_paths("trevor")
        output_directory = Path(trevor_cfg["textures_dir"])
        output_directory.mkdir(parents=True, exist_ok=True)

        source_face_path = Path(trevor_cfg["tex_face"])
        blue_eyes_path = Path(trevor_cfg["tex_eye_base"])
        osakana_path = Path(trevor_cfg["tex_eye_highlight"])
        source_body_path = Path(trevor_cfg["tex_body"])
        source_costume_path = Path(trevor_cfg["tex_costume"])
        source_hair_path = Path(trevor_cfg["tex_hair"])
        costume_normal_path = Path(trevor_cfg["tex_costume_normal"])

        if not source_face_path.exists():
            print(
                f"[ERRO] Textura facial da Miltina nao encontrada: {source_face_path}"
            )
            return False

        atlas_dimension = 2048
        half_dimension = atlas_dimension // 2

        print(f"[INFO] Carregando texturas fonte de: {source_face_path.parent}")
        raw_face_image = Image.open(source_face_path).convert("RGBA")

        # Composicao dos olhos azuis de anime
        if blue_eyes_path.exists():
            print("[INFO] Compondo iris azul marinho anime nos olhos...")
            blue_eyes_image = Image.open(blue_eyes_path).convert("RGBA")
            raw_face_image = Image.alpha_composite(
                raw_face_image, blue_eyes_image
            )
        if osakana_path.exists():
            osakana_image = Image.open(osakana_path).convert("RGBA")
            raw_face_image = Image.alpha_composite(
                raw_face_image, osakana_image
            )

        body_image = Image.open(source_body_path).convert("RGBA")
        costume_image = Image.open(source_costume_path).convert("RGBA")
        hair_image = Image.open(source_hair_path).convert("RGBA")

        # Redimensionamento preciso dos quadrantes para 1024x1024
        face_quadrant = raw_face_image.resize(
            (half_dimension, half_dimension), Image.Resampling.LANCZOS
        )
        body_quadrant = body_image.resize(
            (half_dimension, half_dimension), Image.Resampling.LANCZOS
        )
        costume_quadrant = costume_image.resize(
            (half_dimension, half_dimension), Image.Resampling.LANCZOS
        )
        hair_quadrant = hair_image.resize(
            (half_dimension, half_dimension), Image.Resampling.LANCZOS
        )

        # 1. Elevacao de Luminosidade Facial (evita sombreamento escuro da RAGE)
        face_pixel_array = numpy_lib.array(face_quadrant, dtype=numpy_lib.float32)
        normalized_face_pixels = face_pixel_array[:, :, :3] / 255.0
        lifted_face_pixels = (
            numpy_lib.power(normalized_face_pixels, 0.80) * 1.15
        )
        face_pixel_array[:, :, :3] = numpy_lib.clip(
            lifted_face_pixels * 255.0, 0.0, 255.0
        )
        face_quadrant = Image.fromarray(face_pixel_array.astype(numpy_lib.uint8))

        # 2. Tintura do Cabelo em Azul Safira Vibrante
        hair_pixel_array = numpy_lib.array(hair_quadrant, dtype=numpy_lib.float32)
        blue_tint_vector = numpy_lib.array([0.18, 0.44, 0.92], dtype=numpy_lib.float32)
        hair_pixel_array[:, :, :3] = numpy_lib.clip(
            hair_pixel_array[:, :, :3] * blue_tint_vector * 1.25, 0.0, 255.0
        )
        hair_quadrant = Image.fromarray(hair_pixel_array.astype(numpy_lib.uint8))

        # 3. Montagem do Atlas Diffuse
        diffuse_atlas_image = Image.new(
            "RGBA", (atlas_dimension, atlas_dimension), (0, 0, 0, 255)
        )
        diffuse_atlas_image.paste(face_quadrant, (0, 0))
        diffuse_atlas_image.paste(body_quadrant, (half_dimension, 0))
        diffuse_atlas_image.paste(costume_quadrant, (0, half_dimension))
        diffuse_atlas_image.paste(hair_quadrant, (half_dimension, half_dimension))

        diffuse_output_path = Path(trevor_cfg["atlas_png"])
        diffuse_atlas_image.save(diffuse_output_path, "PNG")
        print(f"[OK] Diffuse Atlas salvo em: {diffuse_output_path}")

        # 4. Montagem do Mapa Especular
        specular_atlas_image = Image.new(
            "RGBA", (atlas_dimension, atlas_dimension), (40, 40, 40, 255)
        )
        hair_specular_quadrant = Image.new(
            "RGBA", (half_dimension, half_dimension), (140, 140, 140, 255)
        )
        costume_specular_quadrant = Image.new(
            "RGBA", (half_dimension, half_dimension), (60, 60, 60, 255)
        )
        skin_specular_quadrant = Image.new(
            "RGBA", (half_dimension, half_dimension), (30, 30, 30, 255)
        )

        specular_atlas_image.paste(skin_specular_quadrant, (0, 0))
        specular_atlas_image.paste(skin_specular_quadrant, (half_dimension, 0))
        specular_atlas_image.paste(costume_specular_quadrant, (0, half_dimension))
        specular_atlas_image.paste(
            hair_specular_quadrant, (half_dimension, half_dimension)
        )

        specular_output_path = Path(trevor_cfg["spec_png"])
        specular_atlas_image.save(specular_output_path, "PNG")
        print(f"[OK] Specular Atlas salvo em: {specular_output_path}")

        # 5. Montagem do Normal Map
        normal_atlas_image = Image.new(
            "RGBA", (atlas_dimension, atlas_dimension), (128, 128, 255, 255)
        )
        if costume_normal_path.exists():
            costume_normal_image = Image.open(costume_normal_path).convert("RGBA")
            costume_normal_quadrant = costume_normal_image.resize(
                (half_dimension, half_dimension), Image.Resampling.LANCZOS
            )
            normal_atlas_image.paste(costume_normal_quadrant, (0, half_dimension))

        normal_output_path = Path(trevor_cfg["normal_png"])
        normal_atlas_image.save(normal_output_path, "PNG")
        print(f"[OK] Normal Map Atlas salvo em: {normal_output_path}")

        # 6. Compilacao do dicionario de textura .ytd via RAGE CLI
        rage_cli_binary = project_paths.get_rage_cli()
        output_ytd_file = Path(trevor_cfg["ytd_file"])

        # Respeita estritamente a ordem de Hash JOAAT
        texture_build_command = [
            rage_cli_binary,
            "textures",
            "build",
            "-o",
            str(output_ytd_file),
            str(diffuse_output_path),
            str(specular_output_path),
            str(normal_output_path),
        ]
        print("\n[INFO] Compilando dicionario de textura .ytd...")
        compilation_process = subprocess.run(
            texture_build_command,
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"[SUCESSO] Dicionario .ytd gerado com sucesso: {output_ytd_file}")
        return True

    except Exception as runtime_error:
        print(
            f"[ERRO] Falha na geracao do atlas de textura da Miltina: {runtime_error}"
        )
        return False


if __name__ == "__main__":
    operation_success = generate_miltina_texture_atlas()
    if not operation_success:
        sys.exit(1)
