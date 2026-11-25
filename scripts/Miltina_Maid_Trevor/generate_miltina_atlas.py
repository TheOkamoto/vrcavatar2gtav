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
import shutil
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

import ped_damage_helper
import texture_calibration_helper as calibration_helper
import unity_hair_bake_layer
import unity_hair_helper
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


def generate_miltina_texture_atlas(
    target_character: str = None,
    hair_override: str = None,
    hair_mat_override: str = None,
    hair_tex_override: str = None,
    unity_scene_override: str = None,
    unity_avatar_override: str = None,
    output_dir_override: str = None,
) -> bool:
    """
    Load source textures from vrc2gtav.cfg, calibrate luminance and
    hair tint (default or custom Unity hair), compose the 2K atlas maps, and build the .ytd file.
    """
    try:
        trevor_cfg = (
            project_paths.get_character_paths(
                target_character,
                avatar_override="miltina_maid",
            )
            if target_character
            else project_paths.get_avatar_paths("miltina_maid")
        )
        output_directory = (
            Path(output_dir_override)
            if output_dir_override
            else Path(trevor_cfg["textures_dir"])
        )
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

        dolosart_mat_dir = Path(trevor_cfg["tex_dolosart_dir"]).parent
        assets_root_dir = dolosart_mat_dir.parent.parent
        body_mat_file = dolosart_mat_dir / "Milltina_Body.mat"

        face_quadrant = raw_face_image.resize(
            (half_dimension, half_dimension), Image.Resampling.LANCZOS
        )
        # Apply warm lilToon face tint instead of gamma lift so skin stays natural peach
        face_quadrant = calibration_helper.apply_shinano_skin_warmth(
            face_quadrant, red_gain=0.98, green_gain=0.90, blue_gain=0.89
        )

        baked_body_res = (
            unity_hair_bake_layer.bake_liltoon_mat_to_image(
                body_mat_file,
                tile_size=(half_dimension, half_dimension),
                preserve_alpha=False,
                unity_assets_root=assets_root_dir,
                apply_matcap2nd_mul=True,
            )
            if body_mat_file.is_file()
            else None
        )
        if baked_body_res is not None:
            body_quadrant = calibration_helper.apply_shinano_skin_warmth(
                baked_body_res[0], red_gain=0.97, green_gain=0.91, blue_gain=0.91
            )
        else:
            body_image = Image.open(source_body_path).convert("RGBA")
            body_quadrant = calibration_helper.apply_shinano_skin_warmth(
                body_image.resize((half_dimension, half_dimension), Image.Resampling.LANCZOS),
                red_gain=0.97,
                green_gain=0.88,
                blue_gain=0.87,
            )

        costume_image = Image.open(source_costume_path).convert("RGBA")
        costume_quadrant = costume_image.resize(
            (half_dimension, half_dimension), Image.Resampling.LANCZOS
        )

        # 2. Calibrate hair (custom Unity hair via resolver, or Milltina_Hair default)
        hair_spec_input = (
            hair_override
            if hair_override is not None
            else (
                str(trevor_cfg.get("custom_hair", "")).strip()
                or str(trevor_cfg.get("fbx_hair", "")).strip()
                or "auto"
            )
        )
        hair_spec = unity_hair_helper.resolve_custom_hair_spec(
            hair_spec_input=hair_spec_input,
            unity_scene=unity_scene_override or trevor_cfg.get("unity_scene"),
            unity_avatar_name=unity_avatar_override
            or str(trevor_cfg.get("unity_avatar_name", "Milltina")),
            hair_mat_override=hair_mat_override or trevor_cfg.get("hair_mat"),
            hair_tex_override=hair_tex_override or trevor_cfg.get("hair_tex"),
            is_calibrated_er_default=False,
        )

        if hair_spec.get("mode") == "custom":
            print(
                i18n.translate(
                    "common.hair_custom_packed",
                    source=hair_spec.get("source_input", ""),
                    tiles=len(hair_spec.get("materials", [])),
                )
            )
            quad_diff, quad_norm, quad_spec, tile_entries = (
                unity_hair_helper.pack_hair_materials_into_quadrant(
                    hair_spec.get("materials", []),
                    quad_size=(half_dimension, half_dimension),
                    quad_uv_rect=(0.5, 0.0, 0.5, 0.5),
                    gutter_px=4,
                )
            )
            hair_quadrant = quad_diff.convert("RGBA")
            hair_normal_quadrant = quad_norm.convert("RGBA")
            hair_specular_quadrant = quad_spec.convert("RGBA")
            unity_hair_helper.save_custom_hair_manifest(
                output_directory, hair_spec, tile_entries
            )
        else:
            if default_hair_path is None:
                print(i18n.translate("trevor.atlas.face_missing", path=trevor_cfg.get("tex_hair", "")))
                return False
            print(i18n.translate("trevor.atlas.hair_fallback"))
            hair_mat_default = dolosart_mat_dir / "Milltina_Hair.mat"
            baked_hair_res = (
                unity_hair_bake_layer.bake_liltoon_mat_to_image(
                    hair_mat_default,
                    tile_size=(half_dimension, half_dimension),
                    preserve_alpha=True,
                    unity_assets_root=assets_root_dir,
                )
                if hair_mat_default.is_file()
                else None
            )
            if baked_hair_res is not None:
                hair_quadrant, hair_normal_quadrant, hair_specular_quadrant, _ = baked_hair_res
                hair_quadrant = hair_quadrant.convert("RGBA")
                hair_specular_quadrant = hair_specular_quadrant.convert("RGBA")
                hair_normal_quadrant = hair_normal_quadrant.convert("RGBA")
            else:
                hair_quadrant, hair_specular_quadrant, hair_normal_quadrant = (
                    calibration_helper.calibrate_miltina_default_hair(
                        base_hair_path=default_hair_path,
                        dolosart_mat_dir=dolosart_mat_dir,
                        output_size=half_dimension,
                    )
                )
            unity_hair_helper.save_custom_hair_manifest(
                output_directory, hair_spec, []
            )

        # 3. Compose Diffuse Atlas
        diffuse_atlas_image = Image.new(
            "RGBA", (atlas_dimension, atlas_dimension), (0, 0, 0, 255)
        )
        diffuse_atlas_image.paste(face_quadrant, (0, 0))
        diffuse_atlas_image.paste(body_quadrant, (half_dimension, 0))
        diffuse_atlas_image.paste(costume_quadrant, (0, half_dimension))
        diffuse_atlas_image.paste(hair_quadrant, (half_dimension, half_dimension))

        diffuse_output_path = (
            output_directory / Path(trevor_cfg["atlas_png"]).name
            if output_dir_override
            else Path(trevor_cfg["atlas_png"])
        )
        diffuse_atlas_image = vtoon_profile_helper.stamp_vtoon_watermark_block(
            diffuse_atlas_image, char_id=3
        )
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

        specular_output_path = (
            output_directory / Path(trevor_cfg["spec_png"]).name
            if output_dir_override
            else Path(trevor_cfg["spec_png"])
        )
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

        normal_output_path = (
            output_directory / Path(trevor_cfg["normal_png"]).name
            if output_dir_override
            else Path(trevor_cfg["normal_png"])
        )
        normal_atlas_image.save(normal_output_path, "PNG")
        print(i18n.translate("trevor.atlas.saved_normal", path=normal_output_path))

        # 6. Compile .ytd texture dictionary via RAGE CLI (preserving JOAAT hash order)
        rage_cli_binary = project_paths.get_rage_cli()
        output_ytd_file = (
            output_directory / Path(trevor_cfg["ytd_file"]).name
            if output_dir_override
            else Path(trevor_cfg["ytd_file"])
        )

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
        ped_damage_helper.enforce_ytd_rpf7_size_budget(
            rage_cli_binary,
            output_ytd_file,
            [diffuse_output_path, specular_output_path, normal_output_path],
        )
        print(i18n.translate("trevor.atlas.ytd_done", path=output_ytd_file))
        _generate_miltina_vtoon_profile(
            trevor_cfg=trevor_cfg,
            dolosart_mat_dir=Path(trevor_cfg["tex_dolosart_dir"]).parent,
            eye_spec_mask_raw=eye_spec_mask_raw,
            output_directory=output_directory,
            custom_output_mode=bool(output_dir_override),
        )
        return True

    except Exception as runtime_error:
        print(i18n.translate("trevor.atlas.failed", error=runtime_error))
        return False


def _generate_miltina_vtoon_profile(
    *,
    trevor_cfg: dict,
    dolosart_mat_dir: Path,
    eye_spec_mask_raw: object,
    output_directory: Path,
    custom_output_mode: bool,
) -> None:
    """Create UV LUT, MatCap, and synced INI entry for char_id=3 (Miltina Maid)."""
    assets_root = dolosart_mat_dir.parent.parent
    face_mat = dolosart_mat_dir / "Milltina_Face.mat"
    body_mat = dolosart_mat_dir / "Milltina_Body.mat"
    costume_mat = dolosart_mat_dir / "Milltina_Costume_Black.mat"
    hair_mat = dolosart_mat_dir / "Milltina_Hair.mat"

    slot_materials = {
        vtoon_profile_helper.SLOT_CLOTH: vtoon_profile_helper.build_vtoon_slot_from_mat(
            vtoon_profile_helper.parse_liltoon_mat_file(costume_mat, assets_root=assets_root),
            vtoon_profile_helper.SLOT_CLOTH,
            albedo_color_already_baked=True,
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
    }
    lut_regions = [
        {"u0": 0.00, "v0": 0.00, "u1": 0.50, "v1": 0.50, "slot_id": vtoon_profile_helper.SLOT_FACE, "shadow_mask": 0.88, "rim_mask": 0.15},
        {"u0": 0.50, "v0": 0.00, "u1": 1.00, "v1": 0.50, "slot_id": vtoon_profile_helper.SLOT_SKIN, "shadow_mask": 0.90, "rim_mask": 0.28},
        {"u0": 0.00, "v0": 0.50, "u1": 0.50, "v1": 1.00, "slot_id": vtoon_profile_helper.SLOT_CLOTH, "shadow_mask": 0.95, "rim_mask": 0.45},
        {"u0": 0.50, "v0": 0.50, "u1": 1.00, "v1": 1.00, "slot_id": vtoon_profile_helper.SLOT_HAIR, "shadow_mask": 0.92, "rim_mask": 0.88},
    ]

    repo_root = project_paths.get_project_root()
    pkg_dir = (
        Path(trevor_cfg["character_dir"]) / "5_rpf_package"
        if not custom_output_mode
        else output_directory
    )
    sync_dirs = []
    if not custom_output_mode:
        for cand_dir in (
            project_paths.get_gtav_root_dir(),
            repo_root / "1_Franklin_Shinano_Casual" / "5_rpf_package",
            repo_root / "2_Michael_Shinano_EternalReunion" / "5_rpf_package",
        ):
            if cand_dir and Path(cand_dir).is_dir():
                sync_dirs.append(Path(cand_dir))

    lut_path, _matcap = vtoon_profile_helper.generate_character_vtoon_assets(
        char_id=3,
        char_name="Miltina_Maid",
        slug="miltina_trevor",
        package_dir=pkg_dir,
        lut_regions=lut_regions,
        slot_materials=slot_materials,
        mat_paths_for_matcap=[hair_mat],
        assets_root=assets_root if assets_root.is_dir() else None,
        sync_dirs=sync_dirs,
    )

    if eye_spec_mask_raw is not None and lut_path.is_file():
        lut_img = Image.open(lut_path).convert("RGBA")
        lut_width, lut_height = lut_img.size
        face_width = lut_width // 2
        face_height = lut_height // 2
        mask_arr = (
            numpy_lib.array(
                Image.fromarray((eye_spec_mask_raw.astype(numpy_lib.uint8) * 255)).resize(
                    (face_width, face_height), Image.Resampling.NEAREST
                )
            )
            > 127
        )
        lut_arr = numpy_lib.array(lut_img)
        eye_region = lut_arr[0:face_height, 0:face_width]
        eye_region[mask_arr] = [
            int(round((vtoon_profile_helper.SLOT_EYES / 15.0) * 255.0)),
            85,
            185,
            78,
        ]
        lut_arr[0:face_height, 0:face_width] = eye_region
        updated_lut = Image.fromarray(lut_arr, mode="RGBA")
        updated_lut.save(lut_path)
        for extra_dir in sync_dirs:
            dst_lut = extra_dir / "vtoon_profiles" / lut_path.name
            if dst_lut.parent.is_dir():
                shutil.copy2(lut_path, dst_lut)


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
    parser.add_argument(
        "--target-character",
        choices=["michael", "franklin", "trevor"],
        default=None,
        help=i18n.translate("trevor.build.arg_target_char"),
    )
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--hair", default=None)
    parser.add_argument("--hair-mat", default=None)
    parser.add_argument("--hair-tex", default=None)
    parser.add_argument("--unity-scene", default=None)
    parser.add_argument("--unity-avatar-name", default=None)
    parsed_args = parser.parse_args()
    if parsed_args.lang and parsed_args.lang != "auto":
        os.environ[i18n.LANG_ENV_VAR] = parsed_args.lang
        i18n.set_active_language(parsed_args.lang)

    return (
        0
        if generate_miltina_texture_atlas(
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
