#!/usr/bin/env python3
"""
apply_characters.py
===================
Applies Universal Slot Replacement for all three Grand Theft Auto V protagonists:
  - Michael De Santa (player_zero) -> Shinano Eternal Reunion
  - Franklin Clinton (player_one)  -> Shinano Casual / Uniform
  - Trevor Philips   (player_two)  -> Miltina Maid

Supports patching a single protagonist or all protagonists simultaneously.
Replaces every torso drawable (uppr_*.ydd) with the full waifu model, every
diffuse texture dictionary (uppr_diff_*.ytd) with the matching 2K atlas, and
all remaining vanilla body parts (head, hair, beard, legs, feet, hands,
accessories) with invisible dummy meshes (629-byte head_000_r.ydd), eliminating
clipping and vanilla overlap. Also replaces all protagonist eyewear props
(p_eyes_*.ydd inside streamedpedprops.rpf) with the rigid prop dummy
(515-byte p_eyes_dummy.ydd).
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List

# Add current directory to sys.path so common helpers import in both repo layouts.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    import vrc2gtav_i18n as project_i18n
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import vrc2gtav_i18n as project_i18n
    from common_tools import vrc2gtav_paths as project_paths


VANILLA_BODY_SLOT_PREFIXES = (
    "accs",
    "berd",
    "decl",
    "feet",
    "hair",
    "hand",
    "head",
    "jbib",
    "lowr",
    "task",
    "teef",
)


def _load_apply_runtime_config() -> Dict[str, object]:
    """Load configured character, staging, and dummy paths from vrc2gtav.cfg."""
    rpf_paths_cfg = project_paths.get_rpf_paths()
    michael_cfg = project_paths.get_character_paths("michael")
    franklin_cfg = project_paths.get_character_paths("franklin")
    trevor_cfg = project_paths.get_character_paths("trevor")

    character_registry = {
        str(michael_cfg["ped_name"]): {
            "display_name": "Michael De Santa -> Shinano Eternal Reunion",
            "model_ydd_path": michael_cfg["target_model_ydd"],
            "texture_ytd_path": michael_cfg["ytd_file"],
            "skeleton_yft_path": michael_cfg["target_yft"],
        },
        str(franklin_cfg["ped_name"]): {
            "display_name": "Franklin Clinton -> Shinano Casual",
            "model_ydd_path": franklin_cfg["target_model_ydd"],
            "texture_ytd_path": franklin_cfg["ytd_file"],
            "skeleton_yft_path": franklin_cfg["target_yft"],
        },
        str(trevor_cfg["ped_name"]): {
            "display_name": "Trevor Philips -> Miltina Maid",
            "model_ydd_path": trevor_cfg["target_model_ydd"],
            "texture_ytd_path": trevor_cfg["ytd_file"],
            "skeleton_yft_path": trevor_cfg["target_yft"],
        },
    }

    staging_target_dirs = [
        rpf_paths_cfg["mppatches_extracted"],
        rpf_paths_cfg["streamedpeds_extracted"],
        rpf_paths_cfg["patchday4ng_models_extracted"],
    ]

    character_props_map = {
        str(michael_cfg["ped_name"]): michael_cfg["staging_streamed_props_dir"],
        str(franklin_cfg["ped_name"]): franklin_cfg["staging_streamed_props_dir"],
        str(trevor_cfg["ped_name"]): trevor_cfg["staging_streamed_props_dir"],
    }

    return {
        "project_root": project_paths.get_project_root(),
        "staging_dir": project_paths.get_staging_dir(),
        "dummy_ydd": project_paths.get_dummy_ydd_path(),
        "prop_dummy_ydd": project_paths.get_prop_dummy_ydd_path(),
        "streamedpeds_extracted": rpf_paths_cfg["streamedpeds_extracted"],
        "character_registry": character_registry,
        "staging_target_dirs": staging_target_dirs,
        "character_props_map": character_props_map,
    }


def patch_single_character_directory(
    character_identifier: str,
    character_configuration: dict,
    target_ped_directory: Path,
    dummy_ydd_path: Path,
) -> dict:
    """
    Replace drawables, textures, and body-slot dummies inside a protagonist
    staging folder (player_zero, player_one, or player_two).
    """
    if not target_ped_directory.is_dir():
        return {
            "uppr_models": 0,
            "textures": 0,
            "dummies": 0,
            "untouched": 0,
        }

    source_model_path = character_configuration["model_ydd_path"]
    source_texture_path = character_configuration["texture_ytd_path"]

    statistics_counter = {
        "uppr_models": 0,
        "textures": 0,
        "dummies": 0,
        "untouched": 0,
    }

    all_directory_filenames = sorted(os.listdir(target_ped_directory))
    for current_filename in all_directory_filenames:
        target_file_path = target_ped_directory / current_filename
        if not target_file_path.is_file():
            continue

        filename_prefix = current_filename.split("_")[0].lower()
        filename_extension = target_file_path.suffix.lower()

        try:
            if filename_prefix == "uppr" and filename_extension == ".ydd":
                shutil.copyfile(source_model_path, target_file_path)
                statistics_counter["uppr_models"] += 1
            elif (
                filename_prefix == "uppr"
                and "diff" in current_filename
                and filename_extension == ".ytd"
            ):
                shutil.copyfile(source_texture_path, target_file_path)
                statistics_counter["textures"] += 1
            elif (
                filename_extension == ".ydd"
                and filename_prefix in VANILLA_BODY_SLOT_PREFIXES
            ):
                shutil.copyfile(dummy_ydd_path, target_file_path)
                statistics_counter["dummies"] += 1
            else:
                statistics_counter["untouched"] += 1
        except Exception as file_copy_exception:
            print(
                project_i18n.translate(
                    "apply.patch_error",
                    path=target_file_path,
                    error=file_copy_exception,
                )
            )
            raise

    archive_context_name = target_ped_directory.parent.name
    print(f"  [{character_identifier}] {archive_context_name}/{character_identifier}:")
    print(
        project_i18n.translate(
            "apply.dir_uppr_models", count=statistics_counter["uppr_models"]
        )
    )
    print(
        project_i18n.translate(
            "apply.dir_textures", count=statistics_counter["textures"]
        )
    )
    print(
        project_i18n.translate(
            "apply.dir_dummies", count=statistics_counter["dummies"]
        )
    )
    print(
        project_i18n.translate(
            "apply.dir_untouched", count=statistics_counter["untouched"]
        )
    )

    return statistics_counter


def apply_selected_characters(characters_to_apply: List[str]) -> bool:
    """Apply compiled models, textures, skeletons, and dummies for the given characters."""
    runtime_cfg = _load_apply_runtime_config()
    dummy_ydd_path = Path(runtime_cfg["dummy_ydd"])
    prop_dummy_ydd_path = Path(runtime_cfg["prop_dummy_ydd"])
    character_registry = runtime_cfg["character_registry"]
    staging_target_dirs = runtime_cfg["staging_target_dirs"]
    character_props_map = runtime_cfg["character_props_map"]
    streamedpeds_extracted_dir = Path(runtime_cfg["streamedpeds_extracted"])

    print(project_i18n.translate("apply.banner"))
    print(
        project_i18n.translate(
            "apply.project_root", path=runtime_cfg["project_root"]
        )
    )
    print(
        project_i18n.translate(
            "apply.staging_rpf", path=runtime_cfg["staging_dir"]
        )
    )

    if not dummy_ydd_path.exists():
        print(project_i18n.translate("apply.dummy_not_found", path=dummy_ydd_path))
        return False

    if not prop_dummy_ydd_path.exists():
        print(
            project_i18n.translate(
                "apply.prop_dummy_not_found", path=prop_dummy_ydd_path
            )
        )
        return False

    try:
        project_paths.ensure_streamedpedprops_extracted()
    except Exception as props_extract_error:
        print(
            project_i18n.translate(
                "apply.props_extract_failed", error=props_extract_error
            )
        )
        return False

    for character_key in characters_to_apply:
        if character_key not in character_registry:
            print(
                project_i18n.translate(
                    "apply.unknown_character", character_key=character_key
                )
            )
            return False

        character_data = character_registry[character_key]
        print(
            project_i18n.translate(
                "apply.applying_header",
                display_name=character_data["display_name"],
                character_key=character_key,
            )
        )

        if not Path(character_data["model_ydd_path"]).exists():
            print(
                project_i18n.translate(
                    "apply.missing_model_ydd", path=character_data["model_ydd_path"]
                )
            )
            return False

        if not Path(character_data["texture_ytd_path"]).exists():
            print(
                project_i18n.translate(
                    "apply.missing_texture_ytd", path=character_data["texture_ytd_path"]
                )
            )
            return False

        if not Path(character_data["skeleton_yft_path"]).exists():
            print(
                project_i18n.translate(
                    "apply.missing_skeleton_yft", path=character_data["skeleton_yft_path"]
                )
            )
            return False

        for staging_base_path in staging_target_dirs:
            ped_subfolder_path = Path(staging_base_path) / character_key
            patch_single_character_directory(
                character_key,
                character_data,
                ped_subfolder_path,
                dummy_ydd_path,
            )
            target_yft_destination = Path(staging_base_path) / f"{character_key}.yft"
            if (
                Path(staging_base_path) == streamedpeds_extracted_dir
                or target_yft_destination.exists()
            ):
                shutil.copyfile(
                    character_data["skeleton_yft_path"], target_yft_destination
                )
                print(
                    project_i18n.translate(
                        "apply.skeleton_updated",
                        character_key=character_key,
                        filename=target_yft_destination.name,
                    )
                )

        props_subfolder_path = character_props_map.get(character_key)
        if props_subfolder_path is not None:
            project_paths.patch_character_glasses_props(
                props_subfolder_path,
                prop_dummy_ydd_path,
                f"{character_key}_p",
            )

    print(project_i18n.translate("apply.success"))
    return True


def main() -> None:
    """CLI entrypoint for universal character slot patching."""
    project_i18n.set_active_language()
    argument_parser = argparse.ArgumentParser(
        description=project_i18n.translate("apply.cli_description")
    )
    argument_parser.add_argument(
        "--character",
        choices=["player_zero", "player_one", "player_two", "all"],
        default="all",
        help=project_i18n.translate("apply.cli_character_help"),
    )
    argument_parser.add_argument(
        "--lang",
        choices=["auto", "en", "ja", "pt"],
        default="auto",
        help=project_i18n.translate("common.language_option_help"),
    )
    parsed_arguments = argument_parser.parse_args()
    project_i18n.set_active_language(parsed_arguments.lang)

    if parsed_arguments.character == "all":
        selected_characters_list = ["player_zero", "player_one", "player_two"]
    else:
        selected_characters_list = [parsed_arguments.character]

    operation_success = apply_selected_characters(selected_characters_list)
    if not operation_success:
        sys.exit(1)


if __name__ == "__main__":
    main()
