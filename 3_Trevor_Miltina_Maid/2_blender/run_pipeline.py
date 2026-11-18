#!/usr/bin/env python3
"""
run_pipeline.py
===============
Runs the complete Miltina Maid (Trevor / player_two) pipeline using the
paths configured in vrc2gtav.cfg:
  1. Generates the 2K Texture Atlas and compiles the .ytd archive.
  2. Executes build_trevor_miltina.py in Blender and renders previews.
  3. Renders RAGE Engine previews and copies captures to artifacts if present.
  4. Applies files to Trevor slots and runs RPF repack/deploy.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from PIL import Image

_CURRENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CURRENT_DIR.parent.parent
for _tools_dir in (_REPO_ROOT / "scripts" / "common_tools", _REPO_ROOT / "_deploy_tools"):
    if _tools_dir.is_dir() and str(_tools_dir) not in sys.path:
        sys.path.insert(0, str(_tools_dir))

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


def main() -> int:
    """Execute the end-to-end Miltina Maid build, render, and deploy pipeline."""
    resolve_startup_language()
    parser = argparse.ArgumentParser(description=i18n.translate("trevor.run.cli_desc"))
    parser.add_argument(
        "--lang",
        choices=list(i18n.SUPPORTED_LANGUAGES) + ["auto"],
        default=None,
        help=i18n.translate("common.language_option_help"),
    )
    parser.add_argument(
        "--target-character",
        default="trevor",
        help=i18n.translate("trevor.build.arg_target_char"),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
    )
    parser.add_argument(
        "--hair",
        default=None,
        help=i18n.translate("common.hair_cli_opt"),
    )
    parser.add_argument(
        "--hair-mat",
        default=None,
        help=i18n.translate("common.hair_mat_cli_opt"),
    )
    parser.add_argument(
        "--hair-tex",
        default=None,
        help=i18n.translate("common.hair_tex_cli_opt"),
    )
    parser.add_argument(
        "--hair-scale",
        type=float,
        default=None,
        help=i18n.translate("common.hair_scale_cli_opt"),
    )
    parser.add_argument(
        "--hair-offset",
        default=None,
        help=i18n.translate("common.hair_offset_cli_opt"),
    )
    parser.add_argument(
        "--unity-scene",
        default=None,
        help=i18n.translate("common.unity_scene_cli_opt"),
    )
    parser.add_argument(
        "--unity-avatar-name",
        default=None,
        help=i18n.translate("common.unity_avatar_cli_opt"),
    )
    parser.add_argument(
        "--blendshapes-cfg",
        default=None,
        help=i18n.translate("blendshapes.cli_cfg"),
    )
    parser.add_argument(
        "--blendshapes-source",
        choices=["auto", "unity", "cfg"],
        default=None,
        help=i18n.translate("blendshapes.cli_source"),
    )
    parser.add_argument(
        "--save-blendshapes-cfg",
        default=None,
        help=i18n.translate("blendshapes.cli_save_cfg"),
    )
    parser.add_argument(
        "--physbones-cfg",
        default=None,
        help=i18n.translate("physbones.cli_cfg"),
    )
    parser.add_argument(
        "--physbones-source",
        choices=["auto", "unity", "cfg"],
        default=None,
        help=i18n.translate("physbones.cli_source"),
    )
    parser.add_argument(
        "--save-physbones-cfg",
        default=None,
        help=i18n.translate("physbones.cli_save_cfg"),
    )
    parser.add_argument(
        "--physbones-marshmallow",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=i18n.translate("physbones.cli_marshmallow"),
    )
    parsed_args = parser.parse_args()
    if parsed_args.lang and parsed_args.lang != "auto":
        os.environ[i18n.LANG_ENV_VAR] = parsed_args.lang
        i18n.set_active_language(parsed_args.lang)

    target_protagonist = project_paths.normalize_protagonist_key(
        parsed_args.target_character
    )
    trevor_cfg = project_paths.get_character_paths(
        target_protagonist,
        avatar_override="miltina_maid",
    )
    python_exe = project_paths.get_python_exe()
    rage_cli = project_paths.get_rage_cli()
    artifacts_dir = project_paths.get_artifacts_dir()
    renders_source = project_paths.get_renders_output_dir()
    staging_dir = project_paths.get_staging_dir()

    # 1. Generate 2K Atlas and .ytd
    print(i18n.translate("trevor.run.generating_atlas"))
    atlas_script = Path(trevor_cfg["atlas_script"])
    if not atlas_script.exists():
        print(i18n.translate("trevor.run.atlas_script_missing", path=atlas_script))
        return 1
    atlas_cmd = [python_exe, str(atlas_script), "--target-character", target_protagonist]
    for flag_name, flag_val in (
        ("--hair", parsed_args.hair),
        ("--hair-mat", parsed_args.hair_mat),
        ("--hair-tex", parsed_args.hair_tex),
        ("--unity-scene", parsed_args.unity_scene),
        ("--unity-avatar-name", parsed_args.unity_avatar_name),
    ):
        if flag_val:
            atlas_cmd.extend([flag_name, str(flag_val)])
    subprocess.run(atlas_cmd, check=True)

    # 2. Compile model in Blender + render previews
    project_paths.ensure_character_skeleton_yft(target_protagonist)
    blender_script = Path(trevor_cfg["blender_script"])
    if not blender_script.exists():
        print(i18n.translate("trevor.run.blender_script_missing", path=blender_script))
        return 1
    extra_blender_args = ["--target-character", target_protagonist]
    for flag_name, flag_val in (
        ("--output-dir", parsed_args.output_dir),
        ("--hair", parsed_args.hair),
        ("--hair-mat", parsed_args.hair_mat),
        ("--hair-tex", parsed_args.hair_tex),
        ("--hair-offset", parsed_args.hair_offset),
        ("--unity-scene", parsed_args.unity_scene),
        ("--unity-avatar-name", parsed_args.unity_avatar_name),
        ("--blendshapes-cfg", parsed_args.blendshapes_cfg),
        ("--blendshapes-source", parsed_args.blendshapes_source),
        ("--save-blendshapes-cfg", parsed_args.save_blendshapes_cfg),
        ("--physbones-cfg", parsed_args.physbones_cfg),
        ("--physbones-source", parsed_args.physbones_source),
        ("--save-physbones-cfg", parsed_args.save_physbones_cfg),
    ):
        if flag_val:
            extra_blender_args.extend([flag_name, str(flag_val)])
    if parsed_args.hair_scale is not None:
        extra_blender_args.extend(["--hair-scale", str(parsed_args.hair_scale)])
    if parsed_args.physbones_marshmallow is True:
        extra_blender_args.append("--physbones-marshmallow")
    elif parsed_args.physbones_marshmallow is False:
        extra_blender_args.append("--no-physbones-marshmallow")

    blender_cmd, blender_env = project_paths.build_blender_command(
        blender_script,
        extra_arguments=extra_blender_args,
    )
    print(i18n.translate("trevor.run.running_blender"))
    subprocess.run(
        blender_cmd,
        stdin=subprocess.DEVNULL,
        env=blender_env,
        check=True,
    )

    if artifacts_dir.is_dir():
        for render_name in ("miltina_blender_face.png", "miltina_blender_full.png"):
            source_render = renders_source / render_name
            if source_render.exists():
                shutil.copy2(source_render, artifacts_dir / render_name)
                print(i18n.translate("trevor.run.copied_render", name=render_name))

    # 3. Preview in RAGE Engine
    ydd_path = Path(trevor_cfg["target_model_ydd"])
    ytd_path = Path(trevor_cfg["ytd_file"])
    if not ydd_path.exists() or not ytd_path.exists():
        print(i18n.translate("trevor.run.compiled_missing", ydd=ydd_path, ytd=ytd_path))
        return 1

    rpf_stage_dir = staging_dir / "miltina_preview_rpf_stage"
    shutil.rmtree(rpf_stage_dir, ignore_errors=True)
    rpf_stage_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ydd_path, rpf_stage_dir / ydd_path.name)
    shutil.copy2(ytd_path, rpf_stage_dir / ytd_path.name)

    rpf_output_path = Path(trevor_cfg["preview_rpf"])
    subprocess.run(
        [rage_cli, "create", "-o", str(rpf_output_path), str(rpf_stage_dir)],
        check=True,
    )

    rage_render_dir = renders_source / "miltina_rage_renders"
    rage_render_dir.mkdir(parents=True, exist_ok=True)
    print(i18n.translate("trevor.run.rendering_rage"))
    subprocess.run(
        [
            rage_cli,
            "screenshot",
            str(rpf_output_path),
            ydd_path.name,
            "--views",
            "front,back,left,right,iso",
            "--facing",
            "prop",
            "--grid",
            "-o",
            str(rage_render_dir),
        ],
        check=True,
    )

    if artifacts_dir.is_dir():
        for filename in rage_render_dir.iterdir():
            if filename.suffix.lower() == ".png":
                dest_name = f"miltina_rage_{filename.name}"
                shutil.copy2(filename, artifacts_dir / dest_name)
                print(i18n.translate("trevor.run.copied_rage_capture", name=dest_name))

        front_screenshot = rage_render_dir / f"{ydd_path.stem}_front.png"
        if front_screenshot.exists():
            crop_dest = artifacts_dir / "miltina_rage_head_crop.png"
            image_obj = Image.open(front_screenshot)
            width_px, height_px = image_obj.size
            cropped_img = image_obj.crop(
                (int(width_px * 0.25), 0, int(width_px * 0.75), int(height_px * 0.42))
            )
            cropped_img.save(crop_dest)
            print(
                i18n.translate(
                    "trevor.run.created_head_crop", name="miltina_rage_head_crop.png"
                )
            )

    # 4. Apply model and textures to Trevor slots and run RPF deploy
    print(i18n.translate("trevor.run.applying_slots"))
    apply_characters_script = project_paths.get_config_path(
        "common_assets", "apply_characters_script"
    )
    subprocess.run(
        [
            python_exe,
            str(apply_characters_script),
            "--character",
            str(trevor_cfg["ped_name"]),
            "--avatar",
            "miltina_maid",
        ],
        check=True,
    )

    print(i18n.translate("trevor.run.repacking"))
    repack_script = project_paths.get_config_path(
        "common_assets", "repack_deploy_script"
    )
    subprocess.run([python_exe, str(repack_script)], check=True)

    print(i18n.translate("trevor.run.done"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
