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

import ped_damage_helper
import texture_calibration_helper as calibration_helper
import unity_hair_helper
import unity_scene_helper
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
    shinano_tex_dir = Path(michael_cfg["tex_shinano_dir"])
    resolved_face = calibration_helper.resolve_existing_file(
        michael_cfg.get("tex_face"),
        [shinano_tex_dir / "Shinano_face.png"],
    )
    resolved_body = calibration_helper.resolve_existing_file(
        michael_cfg.get("tex_body"),
        [shinano_tex_dir / "Shinano_body.png"],
    )

    main_sources = {
        "face": {
            "diffuse_path": str(resolved_face or michael_cfg.get("tex_face", "")),
            "makeup_path": str(michael_cfg.get("tex_makeup", "")),
            "eye_sky_path": str(michael_cfg.get("tex_eye_sky", "")),
            "eye_cloud_path": str(michael_cfg.get("tex_eye_cloud", "")),
            "eye_cloud_mask_path": str(michael_cfg.get("tex_eye_cloud_mask", "")),
            "eye_highlight_path": str(michael_cfg.get("tex_eye_highlight", "")),
            "emission_mask": str(michael_cfg.get("tex_face_emission", "")),
            "grid_column": 0,
            "grid_row": 1,  # Top row in Blender UV space (v: 0.5 .. 1.0)
        },
        "body": {
            "diffuse_path": str(resolved_body or michael_cfg.get("tex_body", "")),
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
            "diffuse_path": str(michael_cfg.get("tex_hair_diffuse", "")),
            "light_mask": str(michael_cfg.get("tex_hair_light_mask", "")),
            "normal_path": str(michael_cfg.get("tex_hair_normal", "")),
            "grid_column": 2,
            "grid_row": 0,
        },
    }

    accessory_sources = {
        "pin_back": {
            "diffuse_path": str(michael_cfg.get("tex_hair_acc_blue", "")),
            "sub_column": 1,
            "sub_row": 1,
        },
        "silver_pins": {
            "diffuse_path": str(michael_cfg.get("tex_hair_acc_pin", "")),
            "sub_column": 0,
            "sub_row": 0,
        },
        "halo": {
            "diffuse_path": str(michael_cfg.get("tex_hair_acc_mat", "")),
            "sub_column": 0,
            "sub_row": 1,
        },
    }
    return main_sources, accessory_sources


def build_liltoon_er_textures(
    output_directory,
    cell_dimension=512,
    target_character=None,
    hair_override=None,
    hair_mat_override=None,
    hair_tex_override=None,
    unity_scene_override=None,
    unity_avatar_override=None,
    custom_output_dir_mode=False,
):
    """
    Build the Diffuse, Specular, and Normal maps for the 4x2 Texture Atlas
    (up to 2048x1024) and compile the GTA V .ytd archive via RAGE CLI.
    """
    michael_cfg = (
        project_paths.get_character_paths(
            target_character,
            avatar_override="shinano_er",
        )
        if target_character
        else project_paths.get_avatar_paths("shinano_er")
    )
    main_sources, accessory_sources = build_texture_sources(michael_cfg)
    shinano_tex_dir = Path(michael_cfg["tex_shinano_dir"])

    unity_scene_path = str(
        unity_scene_override or michael_cfg.get("unity_scene", "")
    ).strip()
    unity_avatar_name = (
        str(unity_avatar_override or michael_cfg.get("unity_avatar_name", "")).strip()
        or "Shinano"
    )
    unity_config = unity_scene_helper.extract_unity_avatar_config(
        unity_scene_path,
        avatar_name=unity_avatar_name,
        character_hints=("shinano", "reunion"),
    )

    hair_spec_input = (
        hair_override
        if hair_override is not None
        else (
            str(michael_cfg.get("custom_hair", "")).strip()
            or str(michael_cfg.get("fbx_hair", "")).strip()
            or "auto"
        )
    )
    hair_spec = unity_hair_helper.resolve_custom_hair_spec(
        hair_spec_input=hair_spec_input,
        unity_scene=unity_scene_path,
        unity_avatar_name=unity_avatar_name,
        hair_mat_override=hair_mat_override or michael_cfg.get("hair_mat"),
        hair_tex_override=hair_tex_override or michael_cfg.get("hair_tex"),
        is_calibrated_er_default=True,
    )
    is_calibrated_neko = bool(hair_spec.get("is_neko_bob_calibrated", False))
    is_arbitrary_custom_hair = bool(
        hair_spec.get("mode") == "custom" and not is_calibrated_neko
    )
    hair_mode = hair_spec.get("mode", "default")
    hair_reason = hair_spec.get("source_input", "") or hair_mode
    custom_hair_tex_ready = bool(
        is_calibrated_neko
        and os.path.exists(main_sources["hair_main"]["diffuse_path"])
    )

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

        # 1C. Custom arbitrary Unity hair OR Default Shinano hair fallback
        if source_key == "hair_main" and is_arbitrary_custom_hair:
            mats_list = hair_spec.get("materials", [])
            use_double_cell = len(mats_list) >= 2
            quad_w = (2 * cell_dimension) if use_double_cell else cell_dimension
            quad_h = cell_dimension
            quad_uv = (0.5, 0.0, 0.5, 0.5) if use_double_cell else (0.5, 0.0, 0.25, 0.5)
            print(
                i18n.translate(
                    "common.hair_custom_packed",
                    source=hair_spec.get("source_input", ""),
                    tiles=len(mats_list),
                )
            )
            quad_diff, quad_norm, quad_spec, er_tile_entries = (
                unity_hair_helper.pack_hair_materials_into_quadrant(
                    mats_list,
                    quad_size=(quad_w, quad_h),
                    quad_uv_rect=quad_uv,
                    gutter_px=4,
                )
            )
            diffuse_array[start_y:end_y, start_x : start_x + quad_w] = numpy.array(
                quad_diff.convert("RGBA")
            )
            specular_array[start_y:end_y, start_x : start_x + quad_w] = numpy.array(
                quad_spec.convert("RGBA")
            )
            normal_array[start_y:end_y, start_x : start_x + quad_w] = numpy.array(
                quad_norm.convert("RGBA")
            )
            unity_hair_helper.save_custom_hair_manifest(
                output_path_obj, hair_spec, er_tile_entries
            )
            continue

        if source_key == "hair_main" and not custom_hair_tex_ready:
            fallback_reason = (
                hair_reason if hair_mode == "default" else "tex_hair_diffuse_missing"
            )
            print(i18n.translate("michael.atlas.hair_fallback", reason=fallback_reason))
            default_hair_src = calibration_helper.resolve_existing_file(
                shinano_tex_dir / "Shinano_hair.png"
            )
            if default_hair_src is None:
                raise FileNotFoundError(
                    i18n.translate(
                        "michael.atlas.required_missing",
                        path=shinano_tex_dir / "Shinano_hair.png",
                    )
                )
            hair_diff, hair_spec_img, hair_norm = calibration_helper.calibrate_shinano_default_hair(
                base_hair_path=default_hair_src,
                shinano_tex_root=shinano_tex_dir,
                output_size=cell_dimension,
            )
            diffuse_array[start_y:end_y, start_x:end_x] = numpy.array(hair_diff)
            specular_array[start_y:end_y, start_x:end_x] = numpy.array(hair_spec_img)
            normal_array[start_y:end_y, start_x:end_x] = numpy.array(hair_norm)
            unity_hair_helper.save_custom_hair_manifest(output_path_obj, hair_spec, [])
            continue

        diffuse_path = source_info["diffuse_path"]
        if not diffuse_path or not os.path.exists(diffuse_path):
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

        # 1A. Special lilToon + optional MoonButterfly compositing for Face and Eyes
        if source_key == "face":
            composite_face, missing_face_layers = (
                calibration_helper.composite_shinano_face_with_fallback(
                    face_path=diffuse_path,
                    target_size=1024,
                    makeup_path=source_info.get("makeup_path"),
                    eye_sky_path=source_info.get("eye_sky_path"),
                    eye_cloud_path=source_info.get("eye_cloud_path"),
                    eye_cloud_mask_path=source_info.get("eye_cloud_mask_path"),
                    eye_highlight_path=source_info.get("eye_highlight_path"),
                )
            )
            if missing_face_layers:
                print(
                    i18n.translate(
                        "michael.atlas.eye_fallback",
                        layers=", ".join(missing_face_layers),
                    )
                )

            cell_diffuse_resized = composite_face.resize(
                (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
            )
            cell_diffuse_numpy = numpy.array(cell_diffuse_resized, dtype=numpy.float32)

            eye_spec_mask = calibration_helper.build_shinano_face_specular(
                cell_dimension,
                shinano_tex_dir,
                source_info.get("emission_mask"),
            )
            if eye_spec_mask is not None:
                specular_array[start_y:end_y, start_x:end_x][eye_spec_mask] = [
                    95,
                    110,
                    130,
                    200,
                ]

        # 1B. Body skin warmth calibration
        elif source_key == "body":
            cell_diffuse_resized = calibration_helper.apply_shinano_skin_warmth(
                cell_diffuse_image.resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                ),
                red_gain=1.01,
                green_gain=0.94,
                blue_gain=0.93,
            )
            cell_diffuse_numpy = numpy.array(cell_diffuse_resized, dtype=numpy.float32)

        # 1C. Custom anime hair and cat ears (Neko Tied Bob)
        elif source_key == "hair_main":
            vibrant_hair_image = calibration_helper.apply_shinano_vibrant_hair_tint(
                cell_diffuse_image
            )
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

    if custom_hair_tex_ready and not is_arbitrary_custom_hair:
        unity_hair_helper.save_custom_hair_manifest(output_path_obj, hair_spec, [])
        for accessory_key, accessory_info in accessory_sources.items():
            accessory_path = accessory_info["diffuse_path"]
            if not accessory_path or not os.path.exists(accessory_path):
                print(
                    i18n.translate(
                        "michael.atlas.accessory_skip",
                        key=accessory_key,
                        path=accessory_path,
                    )
                )
                continue

            print(i18n.translate("michael.atlas.processing_accessory", key=accessory_key))
            accessory_image = Image.open(accessory_path).convert("RGBA")

            if accessory_key == "pin_back":
                accessory_image = calibration_helper.apply_shinano_vibrant_hair_tint(
                    accessory_image
                )

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
                ] = [210, 215, 180, 240]
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
    output_ytd_file = (
        output_path_obj / Path(michael_cfg["ytd_file"]).name
        if custom_output_dir_mode
        else michael_cfg["ytd_file"]
    )
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
    ped_damage_helper.enforce_ytd_rpf7_size_budget(
        rage_cli_path,
        output_ytd_file,
        [diffuse_output_path, legacy_spec_path, legacy_normal_path],
    )
    if not custom_output_dir_mode:
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
        "--output-dir",
        dest="output_dir_flag",
        default=None,
        help=i18n.translate("michael.atlas.output_dir_help"),
    )
    parser.add_argument(
        "--lang",
        choices=list(i18n.SUPPORTED_LANGUAGES) + ["auto"],
        default=None,
        help=i18n.translate("common.language_option_help"),
    )
    parser.add_argument(
        "--target-character",
        choices=["michael", "franklin", "trevor"],
        default=None,
    )
    parser.add_argument("--hair", default=None)
    parser.add_argument("--hair-mat", default=None)
    parser.add_argument("--hair-tex", default=None)
    parser.add_argument("--unity-scene", default=None)
    parser.add_argument("--unity-avatar-name", default=None)
    parsed_args = parser.parse_args()
    if parsed_args.lang and parsed_args.lang != "auto":
        os.environ[i18n.LANG_ENV_VAR] = parsed_args.lang
        i18n.set_active_language(parsed_args.lang)

    active_cfg = (
        project_paths.get_character_paths(
            parsed_args.target_character,
            avatar_override="shinano_er",
        )
        if parsed_args.target_character
        else project_paths.get_avatar_paths("shinano_er")
    )
    explicit_output = parsed_args.output_dir_flag or parsed_args.output_dir
    target_output_directory = explicit_output or str(active_cfg["textures_dir"])
    build_liltoon_er_textures(
        target_output_directory,
        target_character=parsed_args.target_character,
        hair_override=parsed_args.hair,
        hair_mat_override=parsed_args.hair_mat,
        hair_tex_override=parsed_args.hair_tex,
        unity_scene_override=parsed_args.unity_scene,
        unity_avatar_override=parsed_args.unity_avatar_name,
        custom_output_dir_mode=bool(explicit_output),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
