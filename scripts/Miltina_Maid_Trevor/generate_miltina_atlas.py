#!/usr/bin/env python3
"""
generate_miltina_atlas.py
=========================
Generates the unified 2048x2048 (2x2) Texture Atlas for Miltina Maid in GTA V
(Trevor / player_two):
  1. Top-Left Quadrant (0, 0):     Face with composited blue irises and lifted gamma.
  2. Top-Right Quadrant (1, 0):    Body skin texture.
  3. Bottom-Left Quadrant (0, 1):  Maid costume (dress and apron).
  4. Bottom-Right Quadrant (1, 1): Vibrant sapphire-blue tinted hair.

Then compiles the GTA V .ytd texture dictionary via RAGE CLI in JOAAT order.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
import numpy as numpy_lib
from PIL import Image

# Dynamic multi-platform path resolution (compatible with both repository mirrors)
_CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_CANDIDATE = _CURRENT_SCRIPT_DIR.parent.parent
for _tools_candidate in (
    _CURRENT_SCRIPT_DIR.parent / "common_tools",
    _REPO_ROOT_CANDIDATE / "scripts" / "common_tools",
    _REPO_ROOT_CANDIDATE / "_deploy_tools",
):
    if _tools_candidate.is_dir() and str(_tools_candidate) not in sys.path:
        sys.path.insert(0, str(_tools_candidate))

import texture_calibration_helper as calibration_helper
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


def generate_miltina_texture_atlas() -> bool:
    """
    Load source textures from vrc2gtav.cfg [trevor], calibrate luminance and
    sapphire hair tint, compose the 2K atlas maps, and build the .ytd file.
    """
    try:
        trevor_cfg = project_paths.get_character_paths("trevor")
        output_directory = Path(trevor_cfg["textures_dir"])
        output_directory.mkdir(parents=True, exist_ok=True)

        source_face_path = calibration_helper.resolve_existing_file(
            trevor_cfg.get("tex_face"),
            [Path(trevor_cfg["tex_dolosart_dir"]) / "Milltina_Face.png"],
        )
        source_body_path = Path(trevor_cfg["tex_body"])
        source_costume_path = Path(trevor_cfg["tex_costume"])
        default_hair_path = calibration_helper.resolve_existing_file(
            trevor_cfg.get("tex_hair"),
            [Path(trevor_cfg["tex_dolosart_dir"]) / "Milltina_Hair.png"],
        )
        custom_hair_override = calibration_helper.resolve_existing_file(
            trevor_cfg.get("tex_hair_custom", "")
        )
        costume_normal_path = Path(trevor_cfg["tex_costume_normal"])

        if source_face_path is None:
            print(i18n.translate("trevor.atlas.face_missing", path=trevor_cfg.get("tex_face", "")))
            return False

        atlas_dimension = 2048
        half_dimension = atlas_dimension // 2

        print(i18n.translate("trevor.atlas.loading_dir", path=source_face_path.parent))
        raw_face_image = Image.open(source_face_path).convert("RGBA")

        # Composite optional AWEyes irises and highlights with clean fallback to Milltina_Face
        raw_face_image, eye_spec_mask_raw, used_custom_eyes = (
            calibration_helper.composite_miltina_eyes_with_fallback(
                raw_face_image,
                trevor_cfg.get("tex_eye_base"),
                trevor_cfg.get("tex_eye_highlight"),
                trevor_cfg.get("tex_nagima_dir"),
            )
        )
        if used_custom_eyes:
            print(i18n.translate("trevor.atlas.compositing_eyes"))
        else:
            print(i18n.translate("trevor.atlas.eye_fallback"))

        body_image = Image.open(source_body_path).convert("RGBA")
        costume_image = Image.open(source_costume_path).convert("RGBA")

        face_quadrant = raw_face_image.resize(
            (half_dimension, half_dimension), Image.Resampling.LANCZOS
        )
        body_quadrant = body_image.resize(
            (half_dimension, half_dimension), Image.Resampling.LANCZOS
        )
        costume_quadrant = costume_image.resize(
            (half_dimension, half_dimension), Image.Resampling.LANCZOS
        )

        # 1. Lift facial brightness to counter RAGE dark shading
        face_pixel_array = numpy_lib.array(face_quadrant, dtype=numpy_lib.float32)
        normalized_face_pixels = face_pixel_array[:, :, :3] / 255.0
        lifted_face_pixels = numpy_lib.power(normalized_face_pixels, 0.80) * 1.15
        face_pixel_array[:, :, :3] = numpy_lib.clip(lifted_face_pixels * 255.0, 0.0, 255.0)
        face_quadrant = Image.fromarray(face_pixel_array.astype(numpy_lib.uint8))

        # 2. Calibrate hair (custom override if explicitly provided, else Milltina_Hair.mat calibration)
        custom_hair_fbx = str(trevor_cfg.get("fbx_hair", "")).strip()
        if custom_hair_fbx and Path(custom_hair_fbx).is_file() and custom_hair_override is not None:
            print(i18n.translate("trevor.atlas.hair_custom", path=custom_hair_override))
            raw_custom_hair = (
                Image.open(custom_hair_override)
                .convert("RGBA")
                .resize((half_dimension, half_dimension), Image.Resampling.LANCZOS)
            )
            hair_quadrant = calibration_helper.apply_shinano_vibrant_hair_tint(raw_custom_hair)
            hair_specular_quadrant = Image.new(
                "RGBA", (half_dimension, half_dimension), (140, 140, 140, 255)
            )
            hair_luma = numpy_lib.array(raw_custom_hair.convert("L"), dtype=numpy_lib.float32)
            hair_normal_quadrant = calibration_helper.generate_directional_hair_normal(
                hair_luma, strength=2.0
            )
        else:
            if default_hair_path is None:
                print(i18n.translate("trevor.atlas.face_missing", path=trevor_cfg.get("tex_hair", "")))
                return False
            print(i18n.translate("trevor.atlas.hair_fallback"))
            dolosart_mat_dir = Path(trevor_cfg["tex_dolosart_dir"]).parent
            hair_quadrant, hair_specular_quadrant, hair_normal_quadrant = (
                calibration_helper.calibrate_miltina_default_hair(
                    base_hair_path=default_hair_path,
                    dolosart_mat_dir=dolosart_mat_dir,
                    output_size=half_dimension,
                )
            )

        # 3. Compose Diffuse Atlas
        diffuse_atlas_image = Image.new(
            "RGBA", (atlas_dimension, atlas_dimension), (0, 0, 0, 255)
        )
        diffuse_atlas_image.paste(face_quadrant, (0, 0))
        diffuse_atlas_image.paste(body_quadrant, (half_dimension, 0))
        diffuse_atlas_image.paste(costume_quadrant, (0, half_dimension))
        diffuse_atlas_image.paste(hair_quadrant, (half_dimension, half_dimension))

        diffuse_output_path = Path(trevor_cfg["atlas_png"])
        diffuse_atlas_image.save(diffuse_output_path, "PNG")
        print(i18n.translate("trevor.atlas.saved_diffuse", path=diffuse_output_path))

        # 4. Compose Specular Map
        specular_atlas_image = Image.new(
            "RGBA", (atlas_dimension, atlas_dimension), (40, 40, 40, 255)
        )
        costume_specular_quadrant = Image.new(
            "RGBA", (half_dimension, half_dimension), (60, 60, 60, 255)
        )
        skin_specular_quadrant = Image.new(
            "RGBA", (half_dimension, half_dimension), (30, 30, 30, 255)
        )
        if eye_spec_mask_raw is not None:
            resized_eye_mask = numpy_lib.array(
                Image.fromarray((eye_spec_mask_raw.astype(numpy_lib.uint8) * 255)).resize(
                    (half_dimension, half_dimension), Image.Resampling.NEAREST
                )
            ) > 127
            face_spec_arr = numpy_lib.array(skin_specular_quadrant, dtype=numpy_lib.uint8)
            face_spec_arr[resized_eye_mask] = [95, 110, 130, 200]
            face_specular_quadrant = Image.fromarray(face_spec_arr, "RGBA")
        else:
            face_specular_quadrant = skin_specular_quadrant

        specular_atlas_image.paste(face_specular_quadrant, (0, 0))
        specular_atlas_image.paste(skin_specular_quadrant, (half_dimension, 0))
        specular_atlas_image.paste(costume_specular_quadrant, (0, half_dimension))
        specular_atlas_image.paste(hair_specular_quadrant, (half_dimension, half_dimension))

        specular_output_path = Path(trevor_cfg["spec_png"])
        specular_atlas_image.save(specular_output_path, "PNG")
        print(i18n.translate("trevor.atlas.saved_spec", path=specular_output_path))

        # 5. Compose Normal Map
        normal_atlas_image = Image.new(
            "RGBA", (atlas_dimension, atlas_dimension), (128, 128, 255, 255)
        )
        if costume_normal_path.exists():
            costume_normal_image = Image.open(costume_normal_path).convert("RGBA")
            costume_normal_quadrant = costume_normal_image.resize(
                (half_dimension, half_dimension), Image.Resampling.LANCZOS
            )
            normal_atlas_image.paste(costume_normal_quadrant, (0, half_dimension))
        normal_atlas_image.paste(hair_normal_quadrant, (half_dimension, half_dimension))

        normal_output_path = Path(trevor_cfg["normal_png"])
        normal_atlas_image.save(normal_output_path, "PNG")
        print(i18n.translate("trevor.atlas.saved_normal", path=normal_output_path))

        # 6. Compile .ytd texture dictionary via RAGE CLI (preserving JOAAT hash order)
        rage_cli_binary = project_paths.get_rage_cli()
        output_ytd_file = Path(trevor_cfg["ytd_file"])

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
        print(i18n.translate("trevor.atlas.compiling_ytd"))
        subprocess.run(
            texture_build_command,
            capture_output=True,
            text=True,
            check=True,
        )
        print(i18n.translate("trevor.atlas.ytd_done", path=output_ytd_file))
        return True

    except Exception as runtime_error:
        print(i18n.translate("trevor.atlas.failed", error=runtime_error))
        return False


def main() -> int:
    """CLI entry point for generating Miltina Maid textures and .ytd."""
    resolve_startup_language()
    parser = argparse.ArgumentParser(description=i18n.translate("trevor.atlas.cli_desc"))
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

    return 0 if generate_miltina_texture_atlas() else 1


if __name__ == "__main__":
    sys.exit(main())
