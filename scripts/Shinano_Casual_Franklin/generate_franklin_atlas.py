#!/usr/bin/env python3
"""
generate_franklin_atlas.py
==========================
Gera o Texture Atlas 2x2 unificado de 2048x2048 pixels para a Shinano do Franklin (player_one),
aplicando com total precisao as correcoes do shader lilToon e MoonButterfly:
  1. Quadrante Superior Esquerdo (0, 0): Rosto com pele aquecida, blush e olhos MoonButterfly.
  2. Quadrante Superior Direito (1, 0):  Corpo com tonalidade de pele uniforme.
  3. Quadrante Inferior Esquerdo (0, 1): Traje (sueter, saia vermelha, meias e botas).
  4. Quadrante Inferior Direito (1, 1):  Cabelo azul anil vibrante saturado.

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


def apply_vibrant_hair_transform(image_rgba_object: Image.Image) -> Image.Image:
    """
    Transforma a textura do cabelo da Shinano em um azul anil vibrante e saturado,
    e ajusta a pelugem interna das orelhas com degrade ciano, identico ao visual do VRChat.
    """
    image_pixel_array = np.array(image_rgba_object, dtype=np.float32)
    red_channel = image_pixel_array[:, :, 0]
    green_channel = image_pixel_array[:, :, 1]
    blue_channel = image_pixel_array[:, :, 2]
    alpha_channel = image_pixel_array[:, :, 3]

    # Luminancia ponderada original
    weighted_luminance = (
        0.299 * red_channel + 0.587 * green_channel + 0.114 * blue_channel
    )
    normalized_luminance = np.clip(weighted_luminance / 255.0, 0.0, 1.0)

    # Curva de mapeamento tonal lilToon para azul eletrico vibrante
    transformed_red = np.clip(normalized_luminance * 90.0, 0, 255)
    transformed_green = np.clip(
        normalized_luminance * 175.0 + 15.0, 0, 255
    )
    transformed_blue = np.clip(
        np.power(normalized_luminance, 0.6) * 255.0 + 20.0, 0, 255
    )

    result_pixel_array = np.stack(
        [transformed_red, transformed_green, transformed_blue, alpha_channel],
        axis=-1,
    ).astype(np.uint8)
    return Image.fromarray(result_pixel_array, "RGBA")


def build_franklin_atlas() -> bool:
    """
    Constroi o Texture Atlas 2x2 (2048x2048) e gera o dicionario de textura .ytd para o Franklin.
    """
    try:
        unity_assets_directory = project_paths.get_vrc_assets_dir()
        project_root_directory = project_paths.get_project_root()
        staging_directory = project_paths.get_staging_dir()

        output_directory = (
            project_root_directory
            / "1_Franklin_Shinano_Casual"
            / "3_textures_gtav"
        )
        textures_subfolder = output_directory / "textures"
        textures_subfolder.mkdir(parents=True, exist_ok=True)

        shinano_textures_directory = (
            unity_assets_directory / "Shinano" / "Texture"
        )
        moon_butterfly_directory = (
            unity_assets_directory
            / "MoonButterfly eye"
            / "Sinano"
            / "Texture"
        )
        source_textures_directory = staging_directory / "textures_src"

        if not shinano_textures_directory.exists():
            print(
                f"[ERRO] Diretorio de texturas da Shinano nao encontrado: {shinano_textures_directory}"
            )
            return False

        cell_dimension = 1024
        canvas_dimension = 2 * cell_dimension

        print(
            f"[INFO] Gerando Atlas 2x2 do Franklin em: {textures_subfolder} ({canvas_dimension}x{canvas_dimension})"
        )

        diffuse_pixel_array = np.full(
            (canvas_dimension, canvas_dimension, 4),
            [128, 128, 128, 255],
            dtype=np.uint8,
        )
        specular_pixel_array = np.full(
            (canvas_dimension, canvas_dimension, 4),
            [18, 16, 18, 40],
            dtype=np.uint8,
        )
        normal_pixel_array = np.full(
            (canvas_dimension, canvas_dimension, 4),
            [128, 128, 255, 255],
            dtype=np.uint8,
        )

        # 1. Rosto (Shinano_face) -> Top-Left (0..cell, 0..cell)
        face_raw_path = (
            shinano_textures_directory
            / "Color"
            / "Eye"
            / "Shinano_face_blue.png"
        )
        raw_face_image = (
            Image.open(face_raw_path)
            .convert("RGBA")
            .resize((2048, 2048), Image.Resampling.LANCZOS)
        )
        face_array = np.array(raw_face_image, dtype=np.float32)

        # Ajuste de pele quente pessego lilToon
        face_array[:, :, 0] = np.clip(face_array[:, :, 0] * 1.00, 0, 255)
        face_array[:, :, 1] = np.clip(face_array[:, :, 1] * 0.94, 0, 255)
        face_array[:, :, 2] = np.clip(face_array[:, :, 2] * 0.93, 0, 255)
        composite_face_image = Image.fromarray(
            face_array.astype(np.uint8), "RGBA"
        )

        # Maquiagem suave
        makeup_texture_path = (
            shinano_textures_directory
            / "Make up"
            / "Shinano_face_makeup1.png"
        )
        if makeup_texture_path.exists():
            makeup_layer_image = (
                Image.open(makeup_texture_path)
                .convert("RGBA")
                .resize((2048, 2048), Image.Resampling.LANCZOS)
            )
            composite_face_image.alpha_composite(makeup_layer_image)

        # Camadas MoonButterfly
        sky_layer_path = moon_butterfly_directory / "sky.png"
        if sky_layer_path.exists():
            sky_layer_image = (
                Image.open(sky_layer_path)
                .convert("RGBA")
                .resize((2048, 2048), Image.Resampling.LANCZOS)
            )
            composite_face_image.alpha_composite(sky_layer_image)

        cloud_texture_path = moon_butterfly_directory / "Cloud.jpg"
        cloud_mask_texture_path = (
            moon_butterfly_directory / "無題157_20260711214118.png"
        )
        if cloud_texture_path.exists() and cloud_mask_texture_path.exists():
            cloud_layer_image = (
                Image.open(cloud_texture_path)
                .convert("RGBA")
                .resize((2048, 2048), Image.Resampling.LANCZOS)
            )
            cloud_mask_image = (
                Image.open(cloud_mask_texture_path)
                .convert("L")
                .resize((2048, 2048), Image.Resampling.LANCZOS)
            )
            cloud_pixel_array = np.array(cloud_layer_image, dtype=np.float32)
            normalized_mask_array = (
                np.array(cloud_mask_image, dtype=np.float32) / 255.0
            ) * 0.434
            cloud_pixel_array[:, :, 3] = np.clip(
                normalized_mask_array * 255.0, 0, 255
            ).astype(np.uint8)
            cloud_composite_image = Image.fromarray(
                cloud_pixel_array.astype(np.uint8), "RGBA"
            )
            composite_face_image.alpha_composite(cloud_composite_image)

        highlight_layer_path = (
            moon_butterfly_directory / "Eye-highlight.png"
        )
        if highlight_layer_path.exists():
            highlight_layer_image = (
                Image.open(highlight_layer_path)
                .convert("RGBA")
                .resize((2048, 2048), Image.Resampling.LANCZOS)
            )
            composite_face_image.alpha_composite(highlight_layer_image)

        final_face_quadrant = composite_face_image.resize(
            (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
        )
        diffuse_pixel_array[0:cell_dimension, 0:cell_dimension] = np.array(
            final_face_quadrant
        )

        # 2. Corpo (Shinano_body) -> Top-Right
        body_raw_path = shinano_textures_directory / "Shinano_body.png"
        if body_raw_path.exists():
            raw_body_image = (
                Image.open(body_raw_path)
                .convert("RGBA")
                .resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                )
            )
            body_array = np.array(raw_body_image, dtype=np.float32)
            body_array[:, :, 0] = np.clip(body_array[:, :, 0] * 1.01, 0, 255)
            body_array[:, :, 1] = np.clip(body_array[:, :, 1] * 0.94, 0, 255)
            body_array[:, :, 2] = np.clip(body_array[:, :, 2] * 0.93, 0, 255)
            diffuse_pixel_array[
                0:cell_dimension, cell_dimension : 2 * cell_dimension
            ] = body_array.astype(np.uint8)

        # 3. Traje (Shinano_costume) -> Bottom-Left
        costume_source_candidates = [
            source_textures_directory / "shinano_costume.png",
            textures_subfolder / "shinano_costume.png",
            shinano_textures_directory / "Shinano_costume.png",
        ]
        found_costume_path = next(
            (item for item in costume_source_candidates if item.exists()), None
        )
        if found_costume_path:
            costume_layer_image = (
                Image.open(found_costume_path)
                .convert("RGBA")
                .resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                )
            )
            diffuse_pixel_array[
                cell_dimension : 2 * cell_dimension, 0:cell_dimension
            ] = np.array(costume_layer_image)

        # 4. Cabelo (Shinano_hair) -> Bottom-Right
        hair_source_candidates = [
            source_textures_directory / "shinano_hair.png",
            textures_subfolder / "shinano_hair.png",
            shinano_textures_directory / "Shinano_hair.png",
        ]
        found_hair_path = next(
            (item for item in hair_source_candidates if item.exists()), None
        )
        if found_hair_path:
            raw_hair_image = Image.open(found_hair_path).convert("RGBA")
            vibrant_hair_image = apply_vibrant_hair_transform(
                raw_hair_image
            ).resize(
                (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
            )
            diffuse_pixel_array[
                cell_dimension : 2 * cell_dimension,
                cell_dimension : 2 * cell_dimension,
            ] = np.array(vibrant_hair_image)

        # Gravacao dos arquivos PNG finais
        diffuse_final_path = textures_subfolder / "shinano_atlas_2k.png"
        specular_final_path = textures_subfolder / "shinano_black_spec.png"
        normal_final_path = textures_subfolder / "shinano_flat_normal.png"

        Image.fromarray(diffuse_pixel_array, "RGBA").save(
            diffuse_final_path, format="PNG"
        )
        Image.fromarray(specular_pixel_array, "RGBA").save(
            specular_final_path, format="PNG"
        )
        Image.fromarray(normal_pixel_array, "RGBA").save(
            normal_final_path, format="PNG"
        )

        print(f"[OK] Atlas 2x2 do Franklin salvo em: {diffuse_final_path}")

        # Compilacao do dicionario de textura .ytd
        rage_cli_binary = project_paths.get_rage_cli()
        output_ytd_file = output_directory / "shinano_franklin_2k.ytd"

        texture_build_command = [
            rage_cli_binary,
            "textures",
            "build",
            "-o",
            str(output_ytd_file),
            str(diffuse_final_path),
            str(specular_final_path),
            str(normal_final_path),
        ]
        print("\n[INFO] Compilando dicionario de textura .ytd do Franklin...")
        subprocess.run(
            texture_build_command,
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"[SUCESSO] Dicionario .ytd gerado com sucesso: {output_ytd_file}")
        return True

    except Exception as runtime_error:
        print(
            f"[ERRO] Falha na geracao do atlas de textura do Franklin: {runtime_error}"
        )
        return False


if __name__ == "__main__":
    operation_success = build_franklin_atlas()
    if not operation_success:
        sys.exit(1)
