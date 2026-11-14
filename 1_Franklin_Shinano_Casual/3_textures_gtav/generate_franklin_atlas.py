#!/usr/bin/env python3
"""
generate_franklin_atlas.py
==========================
Generate the unified 2048x2048 2x2 Texture Atlas and .ytd texture dictionary
for Franklin's Shinano Casual avatar (player_one), applying lilToon and
MoonButterfly shader color transforms:
  1. Top-Left quadrant     (0, 0): Face with warmed skin tone, blush, and eyes.
  2. Top-Right quadrant    (1, 0): Body skin with matching tone.
  3. Bottom-Left quadrant  (0, 1): Costume (sweater, red skirt, tights, boots).
  4. Bottom-Right quadrant (1, 1): Vibrant saturated indigo-blue hair.
"""

import argparse
import subprocess
import sys
from pathlib import Path
import numpy as numpy_lib
from PIL import Image

# Dynamic cross-platform helper resolution compatible with both repo mirrors
_CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_CANDIDATE = _CURRENT_SCRIPT_DIR.parent.parent
for _tools_candidate in (
    _CURRENT_SCRIPT_DIR.parent / "common_tools",
    _REPO_ROOT_CANDIDATE / "scripts" / "common_tools",
    _REPO_ROOT_CANDIDATE / "_deploy_tools",
):
    if _tools_candidate.is_dir() and str(_tools_candidate) not in sys.path:
        sys.path.insert(0, str(_tools_candidate))

import vrc2gtav_i18n as project_i18n
import vrc2gtav_paths as project_paths


def apply_vibrant_hair_transform(image_rgba_object: Image.Image) -> Image.Image:
    """
    Transform Shinano hair albedo into a saturated indigo-blue palette while
    keeping the cyan gradient on the inner ear fluff, matching VRChat lilToon.
    """
    image_pixel_array = numpy_lib.array(image_rgba_object, dtype=numpy_lib.float32)
    red_channel = image_pixel_array[:, :, 0]
    green_channel = image_pixel_array[:, :, 1]
    blue_channel = image_pixel_array[:, :, 2]
    alpha_channel = image_pixel_array[:, :, 3]

    # Weighted original luminance
    weighted_luminance = (
        0.299 * red_channel + 0.587 * green_channel + 0.114 * blue_channel
    )
    normalized_luminance = numpy_lib.clip(weighted_luminance / 255.0, 0.0, 1.0)

    # lilToon tonal curve for electric indigo-blue highlights
    transformed_red = numpy_lib.clip(normalized_luminance * 90.0, 0, 255)
    transformed_green = numpy_lib.clip(
        normalized_luminance * 175.0 + 15.0, 0, 255
    )
    transformed_blue = numpy_lib.clip(
        numpy_lib.power(normalized_luminance, 0.6) * 255.0 + 20.0, 0, 255
    )

    result_pixel_array = numpy_lib.stack(
        [transformed_red, transformed_green, transformed_blue, alpha_channel],
        axis=-1,
    ).astype(numpy_lib.uint8)
    return Image.fromarray(result_pixel_array, "RGBA")


def build_franklin_atlas() -> bool:
    """Build the 2048x2048 2x2 texture atlas and compile Franklin's .ytd archive."""
    try:
        franklin_cfg = project_paths.get_character_paths("franklin")

        output_directory = Path(franklin_cfg["ytd_dir"])
        textures_subfolder = Path(franklin_cfg["textures_dir"])
        output_directory.mkdir(parents=True, exist_ok=True)
        textures_subfolder.mkdir(parents=True, exist_ok=True)

        shinano_textures_directory = Path(franklin_cfg["tex_shinano_dir"])
        source_textures_directory = Path(franklin_cfg["staging_textures_src_dir"])

        if not shinano_textures_directory.exists():
            print(
                project_i18n.translate(
                    "franklin.tex_dir_missing", path=shinano_textures_directory
                )
            )
            return False

        cell_dimension = 1024
        canvas_dimension = 2 * cell_dimension

        print(
            project_i18n.translate(
                "franklin.generating_atlas",
                path=textures_subfolder,
                size=canvas_dimension,
            )
        )

        diffuse_pixel_array = numpy_lib.full(
            (canvas_dimension, canvas_dimension, 4),
            [128, 128, 128, 255],
            dtype=numpy_lib.uint8,
        )
        specular_pixel_array = numpy_lib.full(
            (canvas_dimension, canvas_dimension, 4),
            [18, 16, 18, 40],
            dtype=numpy_lib.uint8,
        )
        normal_pixel_array = numpy_lib.full(
            (canvas_dimension, canvas_dimension, 4),
            [128, 128, 255, 255],
            dtype=numpy_lib.uint8,
        )

        # 1. Face (Shinano_face) -> Top-Left quadrant
        face_raw_path = Path(franklin_cfg["tex_face"])
        raw_face_image = (
            Image.open(face_raw_path)
            .convert("RGBA")
            .resize((2048, 2048), Image.Resampling.LANCZOS)
        )
        face_array = numpy_lib.array(raw_face_image, dtype=numpy_lib.float32)

        # Warm peach skin adjustment matching lilToon
        face_array[:, :, 0] = numpy_lib.clip(face_array[:, :, 0] * 1.00, 0, 255)
        face_array[:, :, 1] = numpy_lib.clip(face_array[:, :, 1] * 0.94, 0, 255)
        face_array[:, :, 2] = numpy_lib.clip(face_array[:, :, 2] * 0.93, 0, 255)
        composite_face_image = Image.fromarray(
            face_array.astype(numpy_lib.uint8), "RGBA"
        )

        # Subtle makeup overlay
        makeup_texture_path = Path(franklin_cfg["tex_makeup"])
        if makeup_texture_path.exists():
            makeup_layer_image = (
                Image.open(makeup_texture_path)
                .convert("RGBA")
                .resize((2048, 2048), Image.Resampling.LANCZOS)
            )
            composite_face_image.alpha_composite(makeup_layer_image)

        # MoonButterfly eye layers
        sky_layer_path = Path(franklin_cfg["tex_eye_sky"])
        if sky_layer_path.exists():
            sky_layer_image = (
                Image.open(sky_layer_path)
                .convert("RGBA")
                .resize((2048, 2048), Image.Resampling.LANCZOS)
            )
            composite_face_image.alpha_composite(sky_layer_image)

        cloud_texture_path = Path(franklin_cfg["tex_eye_cloud"])
        cloud_mask_texture_path = Path(franklin_cfg["tex_eye_cloud_mask"])
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
            cloud_pixel_array = numpy_lib.array(cloud_layer_image, dtype=numpy_lib.float32)
            normalized_mask_array = (
                numpy_lib.array(cloud_mask_image, dtype=numpy_lib.float32) / 255.0
            ) * 0.434
            cloud_pixel_array[:, :, 3] = numpy_lib.clip(
                normalized_mask_array * 255.0, 0, 255
            ).astype(numpy_lib.uint8)
            cloud_composite_image = Image.fromarray(
                cloud_pixel_array.astype(numpy_lib.uint8), "RGBA"
            )
            composite_face_image.alpha_composite(cloud_composite_image)

        highlight_layer_path = Path(franklin_cfg["tex_eye_highlight"])
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
        diffuse_pixel_array[0:cell_dimension, 0:cell_dimension] = numpy_lib.array(
            final_face_quadrant
        )

        # 2. Body (Shinano_body) -> Top-Right quadrant
        body_raw_path = Path(franklin_cfg["tex_body"])
        if body_raw_path.exists():
            raw_body_image = (
                Image.open(body_raw_path)
                .convert("RGBA")
                .resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                )
            )
            body_array = numpy_lib.array(raw_body_image, dtype=numpy_lib.float32)
            body_array[:, :, 0] = numpy_lib.clip(body_array[:, :, 0] * 1.01, 0, 255)
            body_array[:, :, 1] = numpy_lib.clip(body_array[:, :, 1] * 0.94, 0, 255)
            body_array[:, :, 2] = numpy_lib.clip(body_array[:, :, 2] * 0.93, 0, 255)
            diffuse_pixel_array[
                0:cell_dimension, cell_dimension : 2 * cell_dimension
            ] = body_array.astype(numpy_lib.uint8)

        # 3. Costume (Shinano_costume) -> Bottom-Left quadrant
        costume_source_candidates = [
            source_textures_directory / "shinano_costume.png",
            textures_subfolder / "shinano_costume.png",
            Path(franklin_cfg["tex_costume"]),
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
            ] = numpy_lib.array(costume_layer_image)

        # 4. Hair (Shinano_hair) -> Bottom-Right quadrant
        hair_source_candidates = [
            source_textures_directory / "shinano_hair.png",
            textures_subfolder / "shinano_hair.png",
            Path(franklin_cfg["tex_hair"]),
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
            ] = numpy_lib.array(vibrant_hair_image)

        # Save final PNG channels configured via vrc2gtav.cfg
        diffuse_final_path = Path(franklin_cfg["atlas_png"])
        specular_final_path = Path(franklin_cfg["spec_png"])
        normal_final_path = Path(franklin_cfg["normal_png"])

        Image.fromarray(diffuse_pixel_array, "RGBA").save(
            diffuse_final_path, format="PNG"
        )
        Image.fromarray(specular_pixel_array, "RGBA").save(
            specular_final_path, format="PNG"
        )
        Image.fromarray(normal_pixel_array, "RGBA").save(
            normal_final_path, format="PNG"
        )

        print(project_i18n.translate("franklin.atlas_saved", path=diffuse_final_path))

        # Compile the .ytd texture dictionary
        rage_cli_binary = project_paths.get_rage_cli()
        output_ytd_file = Path(franklin_cfg["ytd_file"])

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
        print(project_i18n.translate("franklin.compiling_ytd"))
        subprocess.run(
            texture_build_command,
            capture_output=True,
            text=True,
            check=True,
        )
        print(project_i18n.translate("franklin.ytd_generated", path=output_ytd_file))
        return True

    except Exception as runtime_error:
        print(
            project_i18n.translate("franklin.atlas_failed", error=runtime_error)
        )
        return False


def main() -> int:
    """CLI entrypoint for Franklin texture atlas generation."""
    project_i18n.set_active_language()
    arg_parser = argparse.ArgumentParser(
        description=project_i18n.translate("franklin.atlas_cli_description")
    )
    arg_parser.add_argument(
        "--lang",
        choices=["auto", "en", "ja", "pt"],
        default="auto",
        help=project_i18n.translate("common.language_option_help"),
    )
    parsed_args = arg_parser.parse_args()
    project_i18n.set_active_language(parsed_args.lang)
    return 0 if build_franklin_atlas() else 1


if __name__ == "__main__":
    sys.exit(main())
