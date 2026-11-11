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
import numpy as np
from PIL import Image

# Resolucao dinamica de caminhos
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common_tools"))
try:
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import vrc2gtav_paths as project_paths


def generate_miltina_texture_atlas() -> bool:
    """
    Carrega as texturas originais do Unity (waifuv4), ajusta curvas de luminosidade,
    aplica o tom azul safira no cabelo e compoe o atlas 2K (Diffuse, Specular, Normal).
    """
    try:
        unity_assets_directory = project_paths.get_vrc_assets_dir()
        project_root_directory = project_paths.get_project_root()
        output_directory = (
            project_root_directory
            / "3_Trevor_Miltina_Maid"
            / "3_textures_gtav"
        )
        output_directory.mkdir(parents=True, exist_ok=True)

        source_textures_directory = (
            unity_assets_directory
            / "DOLOSart"
            / "1.Milltina"
            / "Material"
            / "Texture"
        )
        source_normals_directory = (
            unity_assets_directory
            / "DOLOSart"
            / "1.Milltina"
            / "Material"
            / "Normal"
        )

        if not source_textures_directory.exists():
            print(
                f"[ERRO] Diretorio de texturas da Miltina nao encontrado: {source_textures_directory}"
            )
            return False

        atlas_dimension = 2048
        half_dimension = atlas_dimension // 2

        print(
            f"[INFO] Carregando texturas fonte de: {source_textures_directory}"
        )
        raw_face_image = Image.open(
            source_textures_directory / "Milltina_Face.png"
        ).convert("RGBA")

        # Composicao dos olhos azuis de anime
        eyes_directory = (
            unity_assets_directory
            / "NAGIMA"
            / "AWEyes_Texture"
            / "Milltina_AWEyes"
            / "Material"
        )
        blue_eyes_path = (
            eyes_directory / "Texture" / "Milltina_AWEyes_Blue Sea.png"
        )
        osakana_path = eyes_directory / "Osakana" / "Milltina_AWEyes_Osakana.png"

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

        body_image = Image.open(
            source_textures_directory / "Milltina_Body.png"
        ).convert("RGBA")
        costume_image = Image.open(
            source_textures_directory / "Milltina_Costume.png"
        ).convert("RGBA")
        hair_image = Image.open(
            source_textures_directory / "Milltina_Hair.png"
        ).convert("RGBA")

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
        face_pixel_array = np.array(face_quadrant, dtype=np.float32)
        normalized_face_pixels = face_pixel_array[:, :, :3] / 255.0
        lifted_face_pixels = (
            np.power(normalized_face_pixels, 0.80) * 1.15
        )
        face_pixel_array[:, :, :3] = np.clip(
            lifted_face_pixels * 255.0, 0.0, 255.0
        )
        face_quadrant = Image.fromarray(face_pixel_array.astype(np.uint8))

        # 2. Tintura do Cabelo em Azul Safira Vibrante
        hair_pixel_array = np.array(hair_quadrant, dtype=np.float32)
        blue_tint_vector = np.array([0.18, 0.44, 0.92], dtype=np.float32)
        hair_pixel_array[:, :, :3] = np.clip(
            hair_pixel_array[:, :, :3] * blue_tint_vector * 1.25, 0.0, 255.0
        )
        hair_quadrant = Image.fromarray(hair_pixel_array.astype(np.uint8))

        # 3. Montagem do Atlas Diffuse
        diffuse_atlas_image = Image.new(
            "RGBA", (atlas_dimension, atlas_dimension), (0, 0, 0, 255)
        )
        diffuse_atlas_image.paste(face_quadrant, (0, 0))
        diffuse_atlas_image.paste(body_quadrant, (half_dimension, 0))
        diffuse_atlas_image.paste(costume_quadrant, (0, half_dimension))
        diffuse_atlas_image.paste(hair_quadrant, (half_dimension, half_dimension))

        diffuse_output_path = output_directory / "miltina_atlas_2k.png"
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

        specular_output_path = output_directory / "miltina_spec.png"
        specular_atlas_image.save(specular_output_path, "PNG")
        print(f"[OK] Specular Atlas salvo em: {specular_output_path}")

        # 5. Montagem do Normal Map
        normal_atlas_image = Image.new(
            "RGBA", (atlas_dimension, atlas_dimension), (128, 128, 255, 255)
        )
        costume_normal_path = source_normals_directory / "Milltina_Costume_Normal.png"
        if costume_normal_path.exists():
            costume_normal_image = Image.open(costume_normal_path).convert("RGBA")
            costume_normal_quadrant = costume_normal_image.resize(
                (half_dimension, half_dimension), Image.Resampling.LANCZOS
            )
            normal_atlas_image.paste(costume_normal_quadrant, (0, half_dimension))

        normal_output_path = output_directory / "miltina_normal.png"
        normal_atlas_image.save(normal_output_path, "PNG")
        print(f"[OK] Normal Map Atlas salvo em: {normal_output_path}")

        # 6. Compilacao do dicionario de textura .ytd via RAGE CLI
        rage_cli_binary = project_paths.get_rage_cli()
        output_ytd_file = output_directory / "miltina_maid.ytd"

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
