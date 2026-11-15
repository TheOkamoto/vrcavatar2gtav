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

import texture_calibration_helper as calibration_helper
import unity_hair_helper
import vrc2gtav_i18n as project_i18n
import vrc2gtav_paths as project_paths


def build_franklin_atlas(
    target_character: str = None,
    hair_override: str = None,
    hair_mat_override: str = None,
    hair_tex_override: str = None,
    unity_scene_override: str = None,
    unity_avatar_override: str = None,
    output_dir_override: str = None,
) -> bool:
    """Build the 2048x2048 2x2 texture atlas and compile Franklin's .ytd archive."""
    try:
        franklin_cfg = (
            project_paths.get_character_paths(
                target_character,
                avatar_override="shinano_casual",
            )
            if target_character
            else project_paths.get_avatar_paths("shinano_casual")
        )

        output_directory = (
            Path(output_dir_override)
            if output_dir_override
            else Path(franklin_cfg["ytd_dir"])
        )
        textures_subfolder = (
            Path(output_dir_override)
            if output_dir_override
            else Path(franklin_cfg["textures_dir"])
        )
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
        face_raw_path = calibration_helper.resolve_existing_file(
            franklin_cfg.get("tex_face"),
            [shinano_textures_directory / "Shinano_face.png"],
        )
        if face_raw_path is None:
            raise FileNotFoundError(
                f"Shinano face texture not found: {franklin_cfg.get('tex_face')}"
            )

        composite_face_image, missing_face_layers = (
            calibration_helper.composite_shinano_face_with_fallback(
                face_path=face_raw_path,
                target_size=2048,
                makeup_path=franklin_cfg.get("tex_makeup"),
                eye_sky_path=franklin_cfg.get("tex_eye_sky"),
                eye_cloud_path=franklin_cfg.get("tex_eye_cloud"),
                eye_cloud_mask_path=franklin_cfg.get("tex_eye_cloud_mask"),
                eye_highlight_path=franklin_cfg.get("tex_eye_highlight"),
            )
        )
        if missing_face_layers:
            print(
                project_i18n.translate(
                    "franklin.atlas.eye_fallback",
                    layers=", ".join(missing_face_layers),
                )
            )

        final_face_quadrant = composite_face_image.resize(
            (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
        )
        diffuse_pixel_array[0:cell_dimension, 0:cell_dimension] = numpy_lib.array(
            final_face_quadrant
        )

        face_spec_mask = calibration_helper.build_shinano_face_specular(
            cell_dimension,
            shinano_textures_directory,
            franklin_cfg.get("tex_face_emission", ""),
        )
        if face_spec_mask is not None:
            specular_pixel_array[0:cell_dimension, 0:cell_dimension][face_spec_mask] = [
                95,
                110,
                130,
                200,
            ]

        # 2. Body (Shinano_body) -> Top-Right quadrant
        body_raw_path = calibration_helper.resolve_existing_file(
            franklin_cfg.get("tex_body"),
            [shinano_textures_directory / "Shinano_body.png"],
        )
        if body_raw_path is not None:
            raw_body_image = (
                Image.open(body_raw_path)
                .convert("RGBA")
                .resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                )
            )
            warm_body_image = calibration_helper.apply_shinano_skin_warmth(
                raw_body_image, red_gain=1.01, green_gain=0.94, blue_gain=0.93
            )
            diffuse_pixel_array[
                0:cell_dimension, cell_dimension : 2 * cell_dimension
            ] = numpy_lib.array(warm_body_image)

        # 3. Costume (Shinano_costume) -> Bottom-Left quadrant
        costume_source_candidates = [
            source_textures_directory / "shinano_costume.png",
            textures_subfolder / "shinano_costume.png",
            franklin_cfg.get("tex_costume"),
            shinano_textures_directory / "Shinano_costume.png",
        ]
        found_costume_path = calibration_helper.resolve_existing_file(
            None, costume_source_candidates
        )
        if found_costume_path is not None:
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

        # 4. Hair (custom Unity hair or Shinano_hair default) -> Bottom-Right quadrant
        hair_spec_input = (
            hair_override
            if hair_override is not None
            else (
                str(franklin_cfg.get("custom_hair", "")).strip()
                or str(franklin_cfg.get("fbx_hair", "")).strip()
                or "auto"
            )
        )
        hair_spec = unity_hair_helper.resolve_custom_hair_spec(
            hair_spec_input=hair_spec_input,
            unity_scene=unity_scene_override or franklin_cfg.get("unity_scene"),
            unity_avatar_name=unity_avatar_override
            or str(franklin_cfg.get("unity_avatar_name", "Shinano")),
            hair_mat_override=hair_mat_override or franklin_cfg.get("hair_mat"),
            hair_tex_override=hair_tex_override or franklin_cfg.get("hair_tex"),
            is_calibrated_er_default=False,
        )

        if hair_spec.get("mode") == "custom":
            print(
                project_i18n.translate(
                    "common.hair_custom_packed",
                    source=hair_spec.get("source_input", ""),
                    tiles=len(hair_spec.get("materials", [])),
                )
            )
            quad_diff, quad_norm, quad_spec, tile_entries = (
                unity_hair_helper.pack_hair_materials_into_quadrant(
                    hair_spec.get("materials", []),
                    quad_size=(cell_dimension, cell_dimension),
                    quad_uv_rect=(0.5, 0.0, 0.5, 0.5),
                    gutter_px=4,
                )
            )
            diffuse_pixel_array[
                cell_dimension : 2 * cell_dimension,
                cell_dimension : 2 * cell_dimension,
            ] = numpy_lib.array(quad_diff.convert("RGBA"))
            specular_pixel_array[
                cell_dimension : 2 * cell_dimension,
                cell_dimension : 2 * cell_dimension,
            ] = numpy_lib.array(quad_spec.convert("RGBA"))
            normal_pixel_array[
                cell_dimension : 2 * cell_dimension,
                cell_dimension : 2 * cell_dimension,
            ] = numpy_lib.array(quad_norm.convert("RGBA"))
            unity_hair_helper.save_custom_hair_manifest(
                textures_subfolder, hair_spec, tile_entries
            )
        else:
            configured_hair_path = str(franklin_cfg.get("tex_hair", "")).strip()
            hair_source_candidates = [
                source_textures_directory / "shinano_hair.png",
                textures_subfolder / "shinano_hair.png",
                configured_hair_path,
                shinano_textures_directory / "Shinano_hair.png",
            ]
            found_hair_path = calibration_helper.resolve_existing_file(
                None, hair_source_candidates
            )
            base_shinano_hair = shinano_textures_directory / "Shinano_hair.png"
            if configured_hair_path and not Path(configured_hair_path).is_file():
                print(project_i18n.translate("franklin.atlas.hair_fallback"))

            if found_hair_path is not None:
                hair_diffuse_quad, hair_spec_quad, hair_norm_quad = (
                    calibration_helper.calibrate_shinano_default_hair(
                        base_hair_path=base_shinano_hair
                        if base_shinano_hair.is_file()
                        else found_hair_path,
                        shinano_tex_root=shinano_textures_directory,
                        output_size=cell_dimension,
                        target_tint_path=found_hair_path,
                    )
                )
                diffuse_pixel_array[
                    cell_dimension : 2 * cell_dimension,
                    cell_dimension : 2 * cell_dimension,
                ] = numpy_lib.array(hair_diffuse_quad)
                specular_pixel_array[
                    cell_dimension : 2 * cell_dimension,
                    cell_dimension : 2 * cell_dimension,
                ] = numpy_lib.array(hair_spec_quad)
                normal_pixel_array[
                    cell_dimension : 2 * cell_dimension,
                    cell_dimension : 2 * cell_dimension,
                ] = numpy_lib.array(hair_norm_quad)
            unity_hair_helper.save_custom_hair_manifest(
                textures_subfolder, hair_spec, []
            )

        # Save final PNG channels configured via vrc2gtav.cfg
        diffuse_final_path = (
            textures_subfolder / Path(franklin_cfg["atlas_png"]).name
            if output_dir_override
            else Path(franklin_cfg["atlas_png"])
        )
        specular_final_path = (
            textures_subfolder / Path(franklin_cfg["spec_png"]).name
            if output_dir_override
            else Path(franklin_cfg["spec_png"])
        )
        normal_final_path = (
            textures_subfolder / Path(franklin_cfg["normal_png"]).name
            if output_dir_override
            else Path(franklin_cfg["normal_png"])
        )

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
        output_ytd_file = (
            output_directory / Path(franklin_cfg["ytd_file"]).name
            if output_dir_override
            else Path(franklin_cfg["ytd_file"])
        )

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
    arg_parser.add_argument(
        "--target-character",
        choices=["michael", "franklin", "trevor"],
        default=None,
        help=project_i18n.translate("franklin.build.arg_target_char"),
    )
    arg_parser.add_argument("--output-dir", default=None)
    arg_parser.add_argument("--hair", default=None)
    arg_parser.add_argument("--hair-mat", default=None)
    arg_parser.add_argument("--hair-tex", default=None)
    arg_parser.add_argument("--unity-scene", default=None)
    arg_parser.add_argument("--unity-avatar-name", default=None)
    parsed_args = arg_parser.parse_args()
    project_i18n.set_active_language(parsed_args.lang)
    return (
        0
        if build_franklin_atlas(
            target_character=parsed_args.target_character,
            hair_override=parsed_args.hair,
            hair_mat_override=parsed_args.hair_mat,
            hair_tex_override=parsed_args.hair_tex,
            unity_scene_override=parsed_args.unity_scene,
            unity_avatar_override=parsed_args.unity_avatar_name,
            output_dir_override=parsed_args.output_dir,
        )
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
