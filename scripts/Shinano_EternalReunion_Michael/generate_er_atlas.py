#!/usr/bin/env python3
"""
generate_er_atlas.py
====================
Generates the unified 4x2 Texture Atlas for Shinano Eternal Reunion in GTA V,
reproducing the VRChat/Unity lilToon shader pipeline:
  1. Diffuse Atlas (shinano_er_atlas.png - 2048x1024, max 2K):
     - Face/Skin: warm anime peach tint (_Color: 0.99, 0.92, 0.92), soft
       Shinano_face_makeup1.png blush/lips, and MoonButterfly Eye layers
       (sky.png iris, masked Cloud.jpg at 0.434 opacity, Eye-highlight.png).
     - Body/Skin: matching warm anime tone to eliminate pale shading.
     - Anime Hair: saturated electric blue curve, tinted inner cat ears, and
       synthesized rim/light highlights.
     - Outfits UN1, UN2, UN3, and Pocket Watch UN4.
  2. Specular Atlas (shinano_er_spec.png and legacy alias):
     - Gold metals (Pocket Watch, glasses, buckles, chains), glossy eyes,
       hair highlights, leather, and matte skin.
  3. Normal Map Atlas (shinano_er_normal.png and legacy alias):
     - Preserved normals per cell.
  4. Automatic compilation of the GTA V .ytd archive via RAGE CLI.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
import numpy
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


def build_texture_sources(michael_cfg):
    """Build primary grid cell and accessory sub-cell texture mappings from config."""
    main_sources = {
        "face": {
            "diffuse_path": str(michael_cfg["tex_face"]),
            "makeup_path": str(michael_cfg["tex_makeup"]),
            "eye_sky_path": str(michael_cfg["tex_eye_sky"]),
            "eye_cloud_path": str(michael_cfg["tex_eye_cloud"]),
            "eye_cloud_mask_path": str(michael_cfg["tex_eye_cloud_mask"]),
            "eye_highlight_path": str(michael_cfg["tex_eye_highlight"]),
            "emission_mask": str(michael_cfg["tex_face_emission"]),
            "grid_column": 0,
            "grid_row": 1,  # Top row in Blender UV space (v: 0.5 .. 1.0)
        },
        "body": {
            "diffuse_path": str(michael_cfg["tex_body"]),
            "grid_column": 1,
            "grid_row": 1,
        },
        "un1": {
            "diffuse_path": str(michael_cfg["tex_er_un1_diffuse"]),
            "metallic_mask": str(michael_cfg["tex_er_un1_metallic"]),
            "smoothness_mask": str(michael_cfg["tex_er_un1_smoothness"]),
            "normal_path": str(michael_cfg["tex_er_un1_normal"]),
            "grid_column": 2,
            "grid_row": 1,
        },
        "un2": {
            "diffuse_path": str(michael_cfg["tex_er_un2_diffuse"]),
            "metallic_mask": str(michael_cfg["tex_er_un2_metallic"]),
            "smoothness_mask": str(michael_cfg["tex_er_un2_smoothness"]),
            "normal_path": str(michael_cfg["tex_er_un2_normal"]),
            "grid_column": 3,
            "grid_row": 1,
        },
        "un3": {
            "diffuse_path": str(michael_cfg["tex_er_un3_diffuse"]),
            "metallic_mask": str(michael_cfg["tex_er_un3_metallic"]),
            "smoothness_mask": str(michael_cfg["tex_er_un3_smoothness"]),
            "normal_path": str(michael_cfg["tex_er_un3_normal"]),
            "grid_column": 0,
            "grid_row": 0,  # Bottom row in Blender UV space (v: 0.0 .. 0.5)
        },
        "watch": {
            "diffuse_path": str(michael_cfg["tex_er_un4_diffuse"]),
            "metallic_mask": str(michael_cfg["tex_er_un4_metallic"]),
            "smoothness_mask": str(michael_cfg["tex_er_un4_smoothness"]),
            "normal_path": str(michael_cfg["tex_er_un4_normal"]),
            "grid_column": 1,
            "grid_row": 0,
        },
        "hair_main": {
            "diffuse_path": str(michael_cfg["tex_hair_diffuse"]),
            "light_mask": str(michael_cfg["tex_hair_light_mask"]),
            "normal_path": str(michael_cfg["tex_hair_normal"]),
            "grid_column": 2,
            "grid_row": 0,
        },
    }

    accessory_sources = {
        "pin_back": {
            "diffuse_path": str(michael_cfg["tex_hair_acc_blue"]),
            "sub_column": 1,
            "sub_row": 1,
        },
        "silver_pins": {
            "diffuse_path": str(michael_cfg["tex_hair_acc_pin"]),
            "sub_column": 0,
            "sub_row": 0,
        },
        "halo": {
            "diffuse_path": str(michael_cfg["tex_hair_acc_mat"]),
            "sub_column": 0,
            "sub_row": 1,
        },
    }
    return main_sources, accessory_sources


def apply_vibrant_hair_transform(image_rgba):
    """
    Transform hair and cat-ear textures into the saturated vibrant sky-indigo
    lilToon look seen in VRChat.
    """
    image_array = numpy.array(image_rgba, dtype=numpy.float32)
    red_channel = image_array[:, :, 0]
    green_channel = image_array[:, :, 1]
    blue_channel = image_array[:, :, 2]
    alpha_channel = image_array[:, :, 3]

    luminance_channel = 0.299 * red_channel + 0.587 * green_channel + 0.114 * blue_channel
    normalized_luminance = numpy.clip(luminance_channel / 255.0, 0.0, 1.0)

    new_red_channel = numpy.clip(normalized_luminance * 90.0, 0, 255)
    new_green_channel = numpy.clip(normalized_luminance * 175.0 + 15.0, 0, 255)
    new_blue_channel = numpy.clip(numpy.power(normalized_luminance, 0.6) * 255.0 + 20.0, 0, 255)

    transformed_array = numpy.stack(
        [new_red_channel, new_green_channel, new_blue_channel, alpha_channel],
        axis=-1,
    ).astype(numpy.uint8)
    return Image.fromarray(transformed_array, "RGBA")


def build_liltoon_er_textures(output_directory, cell_dimension=512):
    """
    Build the Diffuse, Specular, and Normal maps for the 4x2 Texture Atlas
    (up to 2048x1024) and compile the GTA V .ytd archive via RAGE CLI.
    """
    michael_cfg = project_paths.get_character_paths("michael")
    main_sources, accessory_sources = build_texture_sources(michael_cfg)

    total_columns = 4
    total_rows = 2
    canvas_width = total_columns * cell_dimension
    canvas_height = total_rows * cell_dimension

    output_path_obj = Path(output_directory)
    output_path_obj.mkdir(parents=True, exist_ok=True)
    print(
        i18n.translate(
            "michael.atlas.generating",
            output_dir=output_directory,
            width=canvas_width,
            height=canvas_height,
        )
    )

    diffuse_array = numpy.full(
        (canvas_height, canvas_width, 4), [128, 128, 128, 255], dtype=numpy.uint8
    )
    specular_array = numpy.full(
        (canvas_height, canvas_width, 4), [18, 16, 18, 40], dtype=numpy.uint8
    )
    normal_array = numpy.full(
        (canvas_height, canvas_width, 4), [128, 128, 255, 255], dtype=numpy.uint8
    )

    # 1. Process each primary cell in the 4x2 grid
    for source_key, source_info in main_sources.items():
        column_index = source_info["grid_column"]
        row_index_blender = source_info["grid_row"]
        pillow_row_index = 1 - row_index_blender

        start_x = column_index * cell_dimension
        end_x = start_x + cell_dimension
        start_y = pillow_row_index * cell_dimension
        end_y = start_y + cell_dimension

        diffuse_path = source_info["diffuse_path"]
        if not os.path.exists(diffuse_path):
            raise FileNotFoundError(
                i18n.translate("michael.atlas.required_missing", path=diffuse_path)
            )

        print(
            i18n.translate(
                "michael.atlas.processing_cell",
                key=source_key,
                col=column_index,
                row=row_index_blender,
            )
        )
        cell_diffuse_image = Image.open(diffuse_path).convert("RGBA")

        # 1A. Special lilToon + MoonButterfly compositing for Face and Eyes
        if source_key == "face":
            face_highres = cell_diffuse_image.resize((1024, 1024), Image.Resampling.LANCZOS)
            face_numpy_array = numpy.array(face_highres, dtype=numpy.float32)

            # Warm lilToon peach tint (_Color: 0.99, 0.92, 0.92)
            face_numpy_array[:, :, 0] = numpy.clip(face_numpy_array[:, :, 0] * 1.00, 0, 255)
            face_numpy_array[:, :, 1] = numpy.clip(face_numpy_array[:, :, 1] * 0.94, 0, 255)
            face_numpy_array[:, :, 2] = numpy.clip(face_numpy_array[:, :, 2] * 0.93, 0, 255)
            composite_face = Image.fromarray(face_numpy_array.astype(numpy.uint8), "RGBA")

            makeup_path = source_info.get("makeup_path")
            if makeup_path and os.path.exists(makeup_path):
                makeup_image = (
                    Image.open(makeup_path)
                    .convert("RGBA")
                    .resize((1024, 1024), Image.Resampling.LANCZOS)
                )
                composite_face.alpha_composite(makeup_image)

            eye_sky_path = source_info.get("eye_sky_path")
            if eye_sky_path and os.path.exists(eye_sky_path):
                eye_sky_image = (
                    Image.open(eye_sky_path)
                    .convert("RGBA")
                    .resize((1024, 1024), Image.Resampling.LANCZOS)
                )
                composite_face.alpha_composite(eye_sky_image)

            eye_cloud_path = source_info.get("eye_cloud_path")
            eye_cloud_mask_path = source_info.get("eye_cloud_mask_path")
            if (
                eye_cloud_path
                and eye_cloud_mask_path
                and os.path.exists(eye_cloud_path)
                and os.path.exists(eye_cloud_mask_path)
            ):
                cloud_image = (
                    Image.open(eye_cloud_path)
                    .convert("RGBA")
                    .resize((1024, 1024), Image.Resampling.LANCZOS)
                )
                cloud_mask_image = (
                    Image.open(eye_cloud_mask_path)
                    .convert("L")
                    .resize((1024, 1024), Image.Resampling.LANCZOS)
                )
                cloud_numpy_array = numpy.array(cloud_image, dtype=numpy.float32)
                mask_numpy_array = (numpy.array(cloud_mask_image, dtype=numpy.float32) / 255.0) * 0.434
                cloud_numpy_array[:, :, 3] = numpy.clip(mask_numpy_array * 255.0, 0, 255).astype(
                    numpy.uint8
                )
                cloud_composite = Image.fromarray(cloud_numpy_array.astype(numpy.uint8), "RGBA")
                composite_face.alpha_composite(cloud_composite)

            eye_highlight_path = source_info.get("eye_highlight_path")
            if eye_highlight_path and os.path.exists(eye_highlight_path):
                highlight_image = (
                    Image.open(eye_highlight_path)
                    .convert("RGBA")
                    .resize((1024, 1024), Image.Resampling.LANCZOS)
                )
                composite_face.alpha_composite(highlight_image)

            cell_diffuse_resized = composite_face.resize(
                (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
            )
            cell_diffuse_numpy = numpy.array(cell_diffuse_resized, dtype=numpy.float32)

            emission_mask_path = source_info.get("emission_mask")
            if emission_mask_path and os.path.exists(emission_mask_path):
                mask_image = Image.open(emission_mask_path).convert("L")
                mask_resized = mask_image.resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                )
                mask_numpy_array = numpy.array(mask_resized, dtype=numpy.float32) / 255.0
                eye_mask_boolean = mask_numpy_array > 0.20
                specular_array[start_y:end_y, start_x:end_x][eye_mask_boolean] = [
                    95,
                    110,
                    130,
                    200,
                ]

        # 1B. Body skin warmth calibration
        elif source_key == "body":
            cell_diffuse_resized = cell_diffuse_image.resize(
                (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
            )
            cell_diffuse_numpy = numpy.array(cell_diffuse_resized, dtype=numpy.float32)
            cell_diffuse_numpy[:, :, 0] = numpy.clip(cell_diffuse_numpy[:, :, 0] * 1.01, 0, 255)
            cell_diffuse_numpy[:, :, 1] = numpy.clip(cell_diffuse_numpy[:, :, 1] * 0.94, 0, 255)
            cell_diffuse_numpy[:, :, 2] = numpy.clip(cell_diffuse_numpy[:, :, 2] * 0.93, 0, 255)

        # 1C. Anime hair and cat ears
        elif source_key == "hair_main":
            vibrant_hair_image = apply_vibrant_hair_transform(cell_diffuse_image)
            cell_diffuse_resized = vibrant_hair_image.resize(
                (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
            )
            cell_diffuse_numpy = numpy.array(cell_diffuse_resized, dtype=numpy.float32)

            light_mask_path = source_info.get("light_mask")
            if light_mask_path and os.path.exists(light_mask_path):
                light_mask_image = Image.open(light_mask_path).convert("RGBA")
                light_mask_resized = light_mask_image.resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                )
                light_mask_numpy = numpy.array(light_mask_resized, dtype=numpy.float32)

                light_intensity = (light_mask_numpy[:, :, 0] / 255.0) * 0.40
                cell_diffuse_numpy[:, :, 0] += light_intensity * 60.0
                cell_diffuse_numpy[:, :, 1] += light_intensity * 75.0
                cell_diffuse_numpy[:, :, 2] += light_intensity * 85.0

                specular_array[start_y:end_y, start_x:end_x] = [30, 45, 60, 90]
                hair_highlight_bool = light_intensity > 0.15
                specular_array[start_y:end_y, start_x:end_x][hair_highlight_bool] = [
                    80,
                    105,
                    135,
                    150,
                ]

            normal_path = source_info.get("normal_path")
            if normal_path and os.path.exists(normal_path):
                hair_norm_image = Image.open(normal_path).convert("RGBA")
                hair_norm_resized = hair_norm_image.resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                )
                normal_array[start_y:end_y, start_x:end_x] = numpy.array(hair_norm_resized)

        # 1D. Gold metals, leather, and outfit fabrics
        elif source_key in ("un1", "un2", "un3", "watch"):
            cell_diffuse_resized = cell_diffuse_image.resize(
                (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
            )
            cell_diffuse_numpy = numpy.array(cell_diffuse_resized, dtype=numpy.float32)

            metallic_path = source_info.get("metallic_mask")
            if metallic_path and os.path.exists(metallic_path):
                metal_image = Image.open(metallic_path).convert("L")
                metal_resized = metal_image.resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                )
                metal_numpy = numpy.array(metal_resized)
                metal_mask_bool = metal_numpy > 50

                if source_key == "watch":
                    specular_array[start_y:end_y, start_x:end_x][metal_mask_bool] = [
                        240,
                        205,
                        90,
                        255,
                    ]
                elif source_key == "un3":
                    specular_array[start_y:end_y, start_x:end_x][metal_mask_bool] = [
                        235,
                        200,
                        85,
                        250,
                    ]
                    leather_mask_bool = ~metal_mask_bool
                    specular_array[start_y:end_y, start_x:end_x][leather_mask_bool] = [
                        65,
                        60,
                        65,
                        130,
                    ]
                elif source_key == "un2":
                    specular_array[start_y:end_y, start_x:end_x][metal_mask_bool] = [
                        225,
                        195,
                        80,
                        240,
                    ]
                    leather_shoes_bool = (~metal_mask_bool) & (cell_diffuse_numpy[:, :, 0] < 50)
                    specular_array[start_y:end_y, start_x:end_x][leather_shoes_bool] = [
                        75,
                        75,
                        80,
                        150,
                    ]
                elif source_key == "un1":
                    specular_array[start_y:end_y, start_x:end_x][metal_mask_bool] = [
                        225,
                        195,
                        80,
                        240,
                    ]

            normal_path = source_info.get("normal_path")
            if normal_path and os.path.exists(normal_path):
                cloth_norm_image = Image.open(normal_path).convert("RGB")
                cloth_norm_resized = cloth_norm_image.resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                )
                norm_rgba = Image.new(
                    "RGBA", (cell_dimension, cell_dimension), (128, 128, 255, 255)
                )
                norm_rgba.paste(cloth_norm_resized, (0, 0))
                normal_array[start_y:end_y, start_x:end_x] = numpy.array(norm_rgba)

        cell_diffuse_clipped = numpy.clip(cell_diffuse_numpy, 0, 255).astype(numpy.uint8)
        diffuse_array[start_y:end_y, start_x:end_x] = cell_diffuse_clipped

    # 2. Process accessories in sub-cell (column 3, row 0 in Blender UV space)
    cell_base_x = 3 * cell_dimension
    cell_base_y = 1 * cell_dimension
    sub_dimension = cell_dimension // 2

    for accessory_key, accessory_info in accessory_sources.items():
        accessory_path = accessory_info["diffuse_path"]
        if not os.path.exists(accessory_path):
            raise FileNotFoundError(
                i18n.translate("michael.atlas.accessory_missing", path=accessory_path)
            )

        print(i18n.translate("michael.atlas.processing_accessory", key=accessory_key))
        accessory_image = Image.open(accessory_path).convert("RGBA")

        if accessory_key == "pin_back":
            accessory_image = apply_vibrant_hair_transform(accessory_image)

        accessory_resized = accessory_image.resize(
            (sub_dimension, sub_dimension), Image.Resampling.LANCZOS
        )
        accessory_numpy = numpy.array(accessory_resized)

        sub_col = accessory_info["sub_column"]
        sub_row_blender = accessory_info["sub_row"]
        pillow_sub_row = 1 - sub_row_blender

        paste_sub_x = cell_base_x + (sub_col * sub_dimension)
        paste_sub_y = cell_base_y + (pillow_sub_row * sub_dimension)

        diffuse_array[
            paste_sub_y : paste_sub_y + sub_dimension,
            paste_sub_x : paste_sub_x + sub_dimension,
        ] = accessory_numpy

        if accessory_key in ("silver_pins", "halo"):
            specular_array[
                paste_sub_y : paste_sub_y + sub_dimension,
                paste_sub_x : paste_sub_x + sub_dimension,
            ] = [210, 215, 225, 240]
        elif accessory_key == "pin_back":
            specular_array[
                paste_sub_y : paste_sub_y + sub_dimension,
                paste_sub_x : paste_sub_x + sub_dimension,
            ] = [45, 60, 80, 110]

    # 3. Write atlas textures to disk
    diffuse_output_path = os.path.join(output_directory, Path(michael_cfg["atlas_png"]).name)
    specular_output_path = os.path.join(output_directory, Path(michael_cfg["er_spec_png"]).name)
    normal_output_path = os.path.join(output_directory, Path(michael_cfg["er_normal_png"]).name)

    Image.fromarray(diffuse_array).save(diffuse_output_path, "PNG")
    Image.fromarray(specular_array).save(specular_output_path, "PNG")
    Image.fromarray(normal_array).save(normal_output_path, "PNG")

    legacy_spec_path = os.path.join(output_directory, Path(michael_cfg["spec_png"]).name)
    legacy_normal_path = os.path.join(output_directory, Path(michael_cfg["normal_png"]).name)
    Image.fromarray(specular_array).save(legacy_spec_path, "PNG")
    Image.fromarray(normal_array).save(legacy_normal_path, "PNG")

    print(
        i18n.translate(
            "michael.atlas.saved",
            diffuse=diffuse_output_path,
            specular=specular_output_path,
            legacy_spec=legacy_spec_path,
            normal=normal_output_path,
            legacy_normal=legacy_normal_path,
        )
    )

    # 4. Compile .ytd texture dictionary via RAGE CLI
    rage_cli_path = project_paths.get_rage_cli()
    output_ytd_file = michael_cfg["ytd_file"]
    backup_ytd_file = michael_cfg["ytd_backup_file"]

    print(i18n.translate("michael.atlas.compiling_ytd"))
    build_arguments = [
        str(rage_cli_path),
        "textures",
        "build",
        "-o",
        str(output_ytd_file),
        diffuse_output_path,
        legacy_spec_path,
        legacy_normal_path,
    ]
    subprocess.run(
        build_arguments,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    shutil.copy2(output_ytd_file, backup_ytd_file)
    print(i18n.translate("michael.atlas.ytd_done", path=output_ytd_file))
    return True


def main() -> int:
    """CLI entry point for generating Michael (Eternal Reunion) textures and .ytd."""
    resolve_startup_language()
    parser = argparse.ArgumentParser(description=i18n.translate("michael.atlas.cli_desc"))
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=None,
        help=i18n.translate("michael.atlas.output_dir_help"),
    )
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

    michael_cfg = project_paths.get_character_paths("michael")
    target_output_directory = parsed_args.output_dir or str(michael_cfg["textures_dir"])
    build_liltoon_er_textures(target_output_directory)
    return 0


if __name__ == "__main__":
    sys.exit(main())
