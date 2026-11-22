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
import json
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

import modular_avatar_helper
import ped_damage_helper
import texture_calibration_helper as calibration_helper
import unity_hair_bake_layer
import unity_hair_helper
import unity_scene_helper
import vrc2gtav_i18n as i18n
import vrc2gtav_paths as project_paths
import vtoon_profile_helper


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

    assets_root = shinano_tex_dir.parent.parent
    shinano_mat_dir = shinano_tex_dir.parent / "Material"
    face_mat_cands = [
        shinano_mat_dir / "Color" / "Eye" / "Shinano_face_eye_blue_newtest.mat",
        shinano_mat_dir / "Shinano_face.mat",
    ]
    resolved_face_mat = next((cand for cand in face_mat_cands if cand.is_file()), None)
    body_mat_cands = [
        assets_root / "_REFLECTO_" / "Lueur Series" / "Lueur Body" / "Shinano" / "Lueur Body Pinkpresetreal.mat",
        shinano_mat_dir / "Shinano_body.mat",
    ]
    resolved_body_mat = next((cand for cand in body_mat_cands if cand.is_file()), None)
    resolved_hair_mat = Path(str(michael_cfg.get("tex_hair_dir", ""))) / "_Mat" / "Blue.mat"
    resolved_ribbon_mat = Path(str(michael_cfg.get("tex_hair_dir", ""))) / "_Mat" / "Bright black.mat"

    main_sources = {
        "face": {
            "diffuse_path": str(resolved_face or michael_cfg.get("tex_face", "")),
            "mat_path": str(resolved_face_mat) if resolved_face_mat else "",
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
            "mat_path": str(resolved_body_mat) if resolved_body_mat else "",
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
            "mat_path": str(resolved_hair_mat) if resolved_hair_mat.is_file() else "",
            "ribbon_mat_path": str(resolved_ribbon_mat) if resolved_ribbon_mat.is_file() else "",
            "light_mask": str(michael_cfg.get("tex_hair_light_mask", "")),
            "normal_path": str(michael_cfg.get("tex_hair_normal", "")),
            "alpha_mask": str(Path(str(michael_cfg.get("tex_hair_dir", ""))) / "_Mat" / "C" / "Mask 3.png"),
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

        # 1A. Special lilToon + Tanzanite / Emission eye compositing for Face and Eyes
        if source_key == "face":
            assets_anchor = shinano_tex_dir.parent.parent
            face_mat_file = source_info.get("mat_path", "")
            baked_face_res = (
                unity_hair_bake_layer.bake_liltoon_mat_to_image(
                    face_mat_file,
                    tile_size=(cell_dimension, cell_dimension),
                    preserve_alpha=False,
                    unity_assets_root=assets_anchor,
                    force_iris_normal_2nd=True,
                )
                if face_mat_file and os.path.isfile(face_mat_file)
                else None
            )
            if baked_face_res is not None:
                composite_face, _face_norm, _face_spec, parsed_face_mat = baked_face_res
                face_em_mask_dynamic = unity_hair_bake_layer.extract_liltoon_emission_mask(
                    parsed_face_mat, tile_size=(cell_dimension, cell_dimension), threshold=0.05
                )
                if face_em_mask_dynamic is not None:
                    source_info["_extracted_em_mask"] = face_em_mask_dynamic
            else:
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
            if source_info.get("_extracted_em_mask") is not None:
                eye_spec_mask = (
                    source_info["_extracted_em_mask"]
                    if eye_spec_mask is None
                    else (eye_spec_mask | source_info["_extracted_em_mask"])
                )
            if eye_spec_mask is not None:
                specular_array[start_y:end_y, start_x:end_x][eye_spec_mask] = [
                    95,
                    110,
                    130,
                    200,
                ]

        # 1B. Body skin warmth calibration (Lueur Body Pinkpresetreal or fallback)
        elif source_key == "body":
            assets_anchor = shinano_tex_dir.parent.parent
            body_mat_file = source_info.get("mat_path", "")
            baked_body_res = (
                unity_hair_bake_layer.bake_liltoon_mat_to_image(
                    body_mat_file,
                    tile_size=(cell_dimension, cell_dimension),
                    preserve_alpha=False,
                    unity_assets_root=assets_anchor,
                    apply_matcap2nd_mul=True,
                )
                if body_mat_file and os.path.isfile(body_mat_file)
                else None
            )
            if baked_body_res is not None:
                cell_diffuse_resized = baked_body_res[0]
            else:
                cell_diffuse_resized = calibration_helper.apply_shinano_skin_warmth(
                    cell_diffuse_image.resize(
                        (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                    ),
                )
            cell_diffuse_numpy = numpy.array(cell_diffuse_resized, dtype=numpy.float32)

        # 1C. Custom anime hair and cat ears (Neko Tied Bob Blue.mat exact linear lilToon)
        elif source_key == "hair_main":
            assets_anchor = shinano_tex_dir.parent.parent
            hair_mat_file = source_info.get("mat_path", "")
            baked_hair_res = (
                unity_hair_bake_layer.bake_liltoon_mat_to_image(
                    hair_mat_file,
                    tile_size=(cell_dimension, cell_dimension),
                    preserve_alpha=True,
                    unity_assets_root=assets_anchor,
                )
                if hair_mat_file and os.path.isfile(hair_mat_file)
                else None
            )
            if baked_hair_res is not None:
                cell_diffuse_resized = baked_hair_res[0]
                cell_diffuse_numpy = numpy.array(cell_diffuse_resized, dtype=numpy.float32)
            else:
                vibrant_hair_image = calibration_helper.apply_shinano_vibrant_hair_tint(
                    cell_diffuse_image
                )
                cell_diffuse_resized = vibrant_hair_image.resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                )
                cell_diffuse_numpy = numpy.array(cell_diffuse_resized, dtype=numpy.float32)

                alpha_mask_path = source_info.get("alpha_mask", "")
                if alpha_mask_path and os.path.exists(alpha_mask_path):
                    mask_img = Image.open(alpha_mask_path).convert("RGBA").resize(
                        (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                    )
                    mask_r = numpy.array(mask_img, dtype=numpy.float32)[:, :, 0] / 255.0
                    cell_diffuse_numpy[:, :, 3] = numpy.clip(cell_diffuse_numpy[:, :, 3] * mask_r, 0.0, 255.0)

            light_mask_path = source_info.get("light_mask")
            if light_mask_path and os.path.exists(light_mask_path):
                light_mask_image = Image.open(light_mask_path).convert("RGBA")
                light_mask_resized = light_mask_image.resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                )
                light_mask_numpy = numpy.array(light_mask_resized, dtype=numpy.float32)

                light_intensity = (light_mask_numpy[:, :, 0] / 255.0) * 0.16
                cell_diffuse_numpy[:, :, 0] += light_intensity * 30.0
                cell_diffuse_numpy[:, :, 1] += light_intensity * 48.0
                cell_diffuse_numpy[:, :, 2] += light_intensity * 85.0

                specular_array[start_y:end_y, start_x:end_x] = [30, 45, 60, 90]
                hair_highlight_bool = light_intensity > 0.07
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

    # 2B. Pack NakoNail (Sky Blue), Ribbon charcoal (#292a2a), and Earrings palette
    # inside empty sub-cell (col=1, row=0) -> u=[0.875..1.0], v=[0.0..0.25]
    nails_spec = _resolve_er_nails_spec(michael_cfg, unity_scene_path, unity_avatar_name)
    nails_manifest_path = output_path_obj / "nails_manifest.json"
    nails_manifest_path.write_text(json.dumps(nails_spec, indent=2), encoding="utf-8")
    nails_sub_x = cell_base_x + sub_dimension
    nails_sub_y = cell_base_y + sub_dimension
    half_sub = sub_dimension // 2
    quarter_sub = half_sub // 2
    if nails_spec.get("fbx_path"):
        nail_tex_path = nails_spec.get("nail_tex", "")
        ribbon_tex_path = nails_spec.get("ribbon_tex", "")
        if nail_tex_path and os.path.exists(nail_tex_path):
            nail_sheet = Image.open(nail_tex_path).convert("RGBA").resize(
                (half_sub, sub_dimension), Image.Resampling.LANCZOS
            )
            diffuse_array[nails_sub_y : nails_sub_y + sub_dimension, nails_sub_x : nails_sub_x + half_sub] = numpy.array(nail_sheet)
        ribbon_bg = Image.new("RGBA", (half_sub, half_sub), (255, 200, 222, 255))
        if ribbon_tex_path and os.path.exists(ribbon_tex_path):
            rib_fg = Image.open(ribbon_tex_path).convert("RGBA").resize(
                (half_sub, half_sub), Image.Resampling.LANCZOS
            )
            ribbon_bg = Image.alpha_composite(ribbon_bg, rib_fg)
        diffuse_array[nails_sub_y : nails_sub_y + half_sub, nails_sub_x + half_sub : nails_sub_x + sub_dimension] = numpy.array(ribbon_bg)
        specular_array[nails_sub_y : nails_sub_y + sub_dimension, nails_sub_x : nails_sub_x + sub_dimension] = [195, 205, 230, 210]

    # Bottom-right 128x128 quadrant (nails_sub_x + 128 .. +256, nails_sub_y + 128 .. +256):
    # Top-left 64x64  -> Neko Ribbon (Bright black.png charcoal #353638 -> #292a2a under VToon)
    # Bot-left 64x64  -> Earrings palette (warm bronze filigree + pearl stud + sapphire beads)
    # Right 64x128    -> Nail_neko tint & VToon bottom-right watermark safe buffer
    blk_x = nails_sub_x + half_sub
    blk_y = nails_sub_y + half_sub
    diffuse_array[blk_y : blk_y + quarter_sub, blk_x : blk_x + quarter_sub] = [53, 54, 56, 255]
    specular_array[blk_y : blk_y + quarter_sub, blk_x : blk_x + quarter_sub] = [38, 38, 42, 90]

    ear_y0 = blk_y + quarter_sub
    half_q = quarter_sub // 2
    # Left 32x64 of Earrings 64x64: filigree dark bronze
    diffuse_array[ear_y0 : ear_y0 + quarter_sub, blk_x : blk_x + half_q] = [104, 78, 72, 255]
    # Top-right 32x32 of Earrings 64x64: top silver-pearl ear stud
    diffuse_array[ear_y0 : ear_y0 + half_q, blk_x + half_q : blk_x + quarter_sub] = [204, 208, 224, 255]
    # Bottom-right 32x32 of Earrings 64x64: deep sapphire chain beads
    diffuse_array[ear_y0 + half_q : ear_y0 + quarter_sub, blk_x + half_q : blk_x + quarter_sub] = [48, 70, 148, 255]
    specular_array[ear_y0 : ear_y0 + quarter_sub, blk_x : blk_x + quarter_sub] = [215, 200, 185, 245]

    diffuse_array[
        blk_y : blk_y + half_sub,
        blk_x + quarter_sub : blk_x + half_sub,
    ] = [248, 245, 252, 255]

    # 3. Write atlas textures to disk (stamp VToon char_id=1 watermark cleanly on bottom-right 8x4)
    diffuse_output_path = os.path.join(output_directory, Path(michael_cfg["atlas_png"]).name)
    specular_output_path = os.path.join(output_directory, Path(michael_cfg["er_spec_png"]).name)
    normal_output_path = os.path.join(output_directory, Path(michael_cfg["er_normal_png"]).name)

    final_diffuse_img = vtoon_profile_helper.stamp_vtoon_watermark_block(
        Image.fromarray(diffuse_array, "RGBA"), char_id=1
    )
    final_diffuse_img.save(diffuse_output_path, "PNG")
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

    _generate_michael_vtoon_profile(
        michael_cfg=michael_cfg,
        source_info_map=main_sources,
        output_path_obj=output_path_obj,
        nails_spec=nails_spec,
        custom_output_dir_mode=custom_output_dir_mode,
    )
    return True


def _resolve_er_nails_spec(michael_cfg: dict, unity_scene_path: str, unity_avatar_name: str) -> dict:
    """Resolve active NakoNail FBX and textures from Shinano.unity Modular Avatar plan."""
    assets_root = Path(michael_cfg.get("tex_shinano_dir", "")).parent.parent
    fallback_fbx = assets_root / "Panda Shop" / "NakoNail" / "Fbx" / "Nail_Nako_Sinano.fbx"
    fallback_tex = assets_root / "Panda Shop" / "NakoNail" / "Materials" / "TEX" / "Nail_skyblue.png"
    fallback_rib = assets_root / "Panda Shop" / "NakoNail" / "Materials" / "TEX" / "pink.png"
    fallback_mat_nail = assets_root / "Panda Shop" / "NakoNail" / "Materials" / "Nail_sky blue_A.mat"
    fallback_mat_rib = assets_root / "Panda Shop" / "NakoNail" / "Materials" / "R_pink.mat"

    fbx_path = str(fallback_fbx) if fallback_fbx.is_file() else ""
    nail_tex = str(fallback_tex) if fallback_tex.is_file() else ""
    ribbon_tex = str(fallback_rib) if fallback_rib.is_file() else ""
    mat_nail_path = str(fallback_mat_nail) if fallback_mat_nail.is_file() else ""
    mat_rib_path = str(fallback_mat_rib) if fallback_mat_rib.is_file() else ""

    if unity_scene_path and os.path.exists(unity_scene_path):
        try:
            ma_plan = modular_avatar_helper.build_modular_avatar_bake_plan(
                unity_scene_path, unity_avatar_name, resolve_materials=True
            )
            for merge_item in ma_plan.get("armature_merges", []):
                mesh_list = [str(name).lower() for name in merge_item.get("mesh_names", [])]
                if "nail_l" in mesh_list or "nail_r" in mesh_list:
                    fbx_cands = merge_item.get("fbx_paths") or []
                    if fbx_cands and os.path.isfile(fbx_cands[0]):
                        fbx_path = str(fbx_cands[0])
                    mesh_mats = ma_plan.get("mesh_materials", {})
                    for nail_key in ("Nail_L", "Nail_R"):
                        if mesh_mats.get(nail_key):
                            mat_info = mesh_mats[nail_key][0]
                            mat_nail_path = mat_info.get("mat_path") or mat_nail_path
                            tex_cand = mat_info.get("tex_envs", {}).get("_MainTex", {}).get("path", "")
                            if tex_cand and os.path.isfile(tex_cand):
                                nail_tex = tex_cand
                            break
                    if mesh_mats.get("Ribbon"):
                        rib_info = mesh_mats["Ribbon"][0]
                        mat_rib_path = rib_info.get("mat_path") or mat_rib_path
                        rib_cand = rib_info.get("tex_envs", {}).get("_MainTex", {}).get("path", "")
                        if rib_cand and os.path.isfile(rib_cand):
                            ribbon_tex = rib_cand
                    break
        except Exception as err_exc:
            print(f"[MA Nails] Warning reading scene MA plan, using fallback: {err_exc}")

    return {
        "fbx_path": fbx_path,
        "nail_tex": nail_tex,
        "ribbon_tex": ribbon_tex,
        "nail_mat": mat_nail_path,
        "ribbon_mat": mat_rib_path,
    }


def _generate_michael_vtoon_profile(
    *,
    michael_cfg: dict,
    source_info_map: dict,
    output_path_obj: Path,
    nails_spec: dict,
    custom_output_dir_mode: bool,
) -> None:
    """Create UV LUT, MatCap, and synced INI entry for char_id=1 (Shinano ER)."""
    assets_root = Path(michael_cfg.get("tex_shinano_dir", "")).parent.parent
    shinano_mat_dir = Path(michael_cfg.get("tex_shinano_dir", "")).parent / "Material"
    face_mat = next(
        (
            cand
            for cand in (
                Path(str(source_info_map.get("face", {}).get("mat_path", ""))),
                shinano_mat_dir / "Color" / "Eye" / "Shinano_face_eye_blue_newtest.mat",
                shinano_mat_dir / "Shinano_face.mat",
            )
            if str(cand) and cand.is_file()
        ),
        None,
    )
    body_mat = next(
        (
            cand
            for cand in (
                Path(str(source_info_map.get("body", {}).get("mat_path", ""))),
                assets_root / "_REFLECTO_" / "Lueur Series" / "Lueur Body" / "Shinano" / "Lueur Body Pinkpresetreal.mat",
                shinano_mat_dir / "Shinano_body.mat",
            )
            if str(cand) and cand.is_file()
        ),
        None,
    )
    hair_mat = Path(str(michael_cfg.get("tex_hair_dir", ""))) / "_Mat" / "Blue.mat"
    halo_mat = Path(str(michael_cfg.get("tex_hair_dir", ""))) / "Accessories" / "_Halo.mat"
    nail_mat = Path(nails_spec["nail_mat"]) if nails_spec.get("nail_mat") else None

    slot_materials = {
        vtoon_profile_helper.SLOT_CLOTH: vtoon_profile_helper.build_vtoon_slot_from_mat(
            None, vtoon_profile_helper.SLOT_CLOTH, albedo_color_already_baked=True
        ),
        vtoon_profile_helper.SLOT_SKIN: vtoon_profile_helper.build_vtoon_slot_from_mat(
            vtoon_profile_helper.parse_liltoon_mat_file(body_mat, assets_root=assets_root),
            vtoon_profile_helper.SLOT_SKIN,
            albedo_color_already_baked=True,
        ),
        vtoon_profile_helper.SLOT_FACE: vtoon_profile_helper.build_vtoon_slot_from_mat(
            vtoon_profile_helper.parse_liltoon_mat_file(face_mat, assets_root=assets_root),
            vtoon_profile_helper.SLOT_FACE,
            albedo_color_already_baked=True,
        ),
        vtoon_profile_helper.SLOT_EYES: vtoon_profile_helper.build_vtoon_slot_from_mat(
            vtoon_profile_helper.parse_liltoon_mat_file(face_mat, assets_root=assets_root),
            vtoon_profile_helper.SLOT_EYES,
            albedo_color_already_baked=True,
        ),
        vtoon_profile_helper.SLOT_HAIR: vtoon_profile_helper.build_vtoon_slot_from_mat(
            vtoon_profile_helper.parse_liltoon_mat_file(hair_mat, assets_root=assets_root),
            vtoon_profile_helper.SLOT_HAIR,
            albedo_color_already_baked=True,
        ),
        vtoon_profile_helper.SLOT_NAILS: vtoon_profile_helper.build_vtoon_slot_from_mat(
            vtoon_profile_helper.parse_liltoon_mat_file(nail_mat, assets_root=assets_root),
            vtoon_profile_helper.SLOT_NAILS,
            albedo_color_already_baked=True,
        ),
        vtoon_profile_helper.SLOT_METAL: vtoon_profile_helper.build_vtoon_slot_from_mat(
            vtoon_profile_helper.parse_liltoon_mat_file(halo_mat, assets_root=assets_root) if halo_mat.is_file() else None,
            vtoon_profile_helper.SLOT_METAL,
            albedo_color_already_baked=True,
        ),
    }
    lut_regions = [
        {"u0": 0.00, "v0": 0.00, "u1": 0.25, "v1": 0.50, "slot_id": vtoon_profile_helper.SLOT_FACE, "shadow_mask": 0.88, "rim_mask": 0.15},
        {"u0": 0.25, "v0": 0.00, "u1": 0.50, "v1": 0.50, "slot_id": vtoon_profile_helper.SLOT_SKIN, "shadow_mask": 0.90, "rim_mask": 0.28},
        {"u0": 0.50, "v0": 0.00, "u1": 1.00, "v1": 0.50, "slot_id": vtoon_profile_helper.SLOT_CLOTH, "shadow_mask": 0.95, "rim_mask": 0.45},
        {"u0": 0.00, "v0": 0.50, "u1": 0.25, "v1": 1.00, "slot_id": vtoon_profile_helper.SLOT_CLOTH, "shadow_mask": 0.95, "rim_mask": 0.50},
        {"u0": 0.25, "v0": 0.50, "u1": 0.50, "v1": 1.00, "slot_id": vtoon_profile_helper.SLOT_METAL, "shadow_mask": 0.95, "rim_mask": 0.85},
        {"u0": 0.50, "v0": 0.50, "u1": 0.75, "v1": 1.00, "slot_id": vtoon_profile_helper.SLOT_HAIR, "shadow_mask": 0.92, "rim_mask": 0.88},
        # Quadrant (3,0): Halo / Pins / _Pin.Back / Nails / Ribbon / Earrings (converted from Blender UV)
        vtoon_profile_helper.blender_uv_rect_to_lut_rect(0.75, 0.25, 0.125, 0.25, vtoon_profile_helper.SLOT_METAL, shadow_mask=0.92, rim_mask=0.85),
        vtoon_profile_helper.blender_uv_rect_to_lut_rect(0.875, 0.25, 0.125, 0.25, vtoon_profile_helper.SLOT_CLOTH, shadow_mask=0.90, rim_mask=0.35),
        vtoon_profile_helper.blender_uv_rect_to_lut_rect(0.75, 0.00, 0.125, 0.25, vtoon_profile_helper.SLOT_METAL, shadow_mask=0.92, rim_mask=0.85),
        vtoon_profile_helper.blender_uv_rect_to_lut_rect(0.875, 0.00, 0.125, 0.25, vtoon_profile_helper.SLOT_NAILS, shadow_mask=0.85, rim_mask=0.95),
        vtoon_profile_helper.blender_uv_rect_to_lut_rect(0.9375, 0.0625, 0.03125, 0.0625, vtoon_profile_helper.SLOT_CLOTH, shadow_mask=0.92, rim_mask=0.35),
        vtoon_profile_helper.blender_uv_rect_to_lut_rect(0.9375, 0.00, 0.03125, 0.0625, vtoon_profile_helper.SLOT_METAL, shadow_mask=0.90, rim_mask=0.92),
    ]

    repo_root = project_paths.get_project_root()
    pkg_dir = (
        Path(michael_cfg["character_dir"]) / "5_rpf_package"
        if not custom_output_dir_mode
        else output_path_obj
    )
    sync_dirs = []
    if not custom_output_dir_mode:
        for candidate_dir in (
            project_paths.get_gtav_root_dir(),
            repo_root / "1_Franklin_Shinano_Casual" / "5_rpf_package",
            repo_root / "3_Trevor_Miltina_Maid" / "5_rpf_package",
        ):
            if candidate_dir and Path(candidate_dir).is_dir():
                sync_dirs.append(Path(candidate_dir))

    lut_path, _matcap_path = vtoon_profile_helper.generate_character_vtoon_assets(
        char_id=1,
        char_name="Shinano_EternalReunion",
        slug="shinano_er",
        package_dir=pkg_dir,
        lut_regions=lut_regions,
        slot_materials=slot_materials,
        mat_paths_for_matcap=[hair_mat],
        assets_root=assets_root if assets_root.is_dir() else None,
        sync_dirs=sync_dirs,
    )

    # Stamp exact iris eye emission/highlight mask inside Face quadrant
    face_em_path = source_info_map.get("face", {}).get("emission_mask", "")
    extracted_em_mask = source_info_map.get("face", {}).get("_extracted_em_mask")
    if lut_path.is_file() and (
        (face_em_path and os.path.exists(face_em_path)) or extracted_em_mask is not None
    ):
        lut_img = Image.open(lut_path).convert("RGBA")
        lut_w, lut_h = lut_img.size
        face_w = lut_w // 4
        face_h = lut_h // 2
        em_mask = numpy.zeros((face_h, face_w), dtype=bool)
        if face_em_path and os.path.exists(face_em_path):
            em_mask |= numpy.array(
                Image.open(face_em_path).convert("L").resize((face_w, face_h), Image.Resampling.BILINEAR)
            ) > 96
        if extracted_em_mask is not None:
            em_mask |= (
                numpy.array(
                    Image.fromarray((extracted_em_mask.astype(numpy.uint8) * 255)).resize(
                        (face_w, face_h), Image.Resampling.BILINEAR
                    )
                )
                > 64
            )
        lut_arr = numpy.array(lut_img)
        eye_region = lut_arr[0:face_h, 0:face_w]
        eye_region[em_mask] = [
            int(round((vtoon_profile_helper.SLOT_EYES / 15.0) * 255.0)),
            85,
            185,
            92,
        ]
        lut_arr[0:face_h, 0:face_w] = eye_region
        updated_lut = Image.fromarray(lut_arr, mode="RGBA")
        updated_lut.save(lut_path)
        for extra_dir in sync_dirs:
            dst_lut = extra_dir / "vtoon_profiles" / lut_path.name
            if dst_lut.parent.is_dir():
                shutil.copy2(lut_path, dst_lut)


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
