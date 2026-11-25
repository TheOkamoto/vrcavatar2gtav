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
clipping and vanilla overlap. Also replaces all protagonist head, eyewear, and
ear wearable props (p_*.ydd inside streamedpedprops.rpf) with the rigid prop
dummy (515-byte p_eyes_dummy.ydd).
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add current directory to sys.path so common helpers import in both repo layouts.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    import npc_registry_helper
    import ped_damage_helper
    import vrc2gtav_i18n as project_i18n
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import npc_registry_helper
    from common_tools import ped_damage_helper
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


def _format_assignment_label(protagonist_key: str, avatar_id: str) -> str:
    """Return a localized 'Protagonist -> Avatar' display label."""
    protagonist_label = project_i18n.translate(f"protagonist.{protagonist_key}")
    avatar_label = project_i18n.translate(f"avatar.{avatar_id}")
    return f"{protagonist_label} -> {avatar_label}"


def _load_apply_runtime_config(
    avatar_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, object]:
    """Load configured character, staging, and dummy paths from vrc2gtav.cfg."""
    rpf_paths_cfg = project_paths.get_rpf_paths()
    normalized_overrides = {
        project_paths.normalize_protagonist_key(raw_prot): project_paths.normalize_avatar_id(
            raw_avatar
        )
        for raw_prot, raw_avatar in (avatar_overrides or {}).items()
        if raw_avatar
    }

    project_root_dir = project_paths.get_project_root()
    character_registry: Dict[str, Dict[str, object]] = {}
    character_props_map: Dict[str, Path] = {}
    for protagonist_key in project_paths.list_available_protagonists():
        char_cfg = project_paths.get_character_paths(
            protagonist_key,
            avatar_override=normalized_overrides.get(protagonist_key),
        )
        ped_key = str(char_cfg["ped_name"])
        avatar_id = str(char_cfg["avatar_id"])
        extra_ydd_paths = [
            Path(extra_path) for extra_path in (char_cfg.get("extra_model_ydds") or [])
        ]
        model_racial_ydd_path = next(
            (
                item_path
                for item_path in extra_ydd_paths
                if item_path.name.lower() == "uppr_000_r.ydd"
            ),
            None,
        )
        if model_racial_ydd_path is None:
            model_racial_ydd_path = next(
                (
                    item_path
                    for item_path in extra_ydd_paths
                    if item_path.stem.lower().endswith("_r") and item_path.exists()
                ),
                None,
            )
        character_registry[ped_key] = {
            "display_name": _format_assignment_label(protagonist_key, avatar_id),
            "model_ydd_path": char_cfg["target_model_ydd"],
            "model_r_ydd_path": model_racial_ydd_path or char_cfg["target_model_ydd"],
            "texture_ytd_path": char_cfg["ytd_file"],
            "skeleton_yft_path": char_cfg["target_yft"],
        }
        character_props_map[ped_key] = char_cfg["staging_streamed_props_dir"]

    staging_target_dirs = [
        rpf_paths_cfg["mppatches_extracted"],
        rpf_paths_cfg["streamedpeds_extracted"],
        rpf_paths_cfg["patchday4ng_models_extracted"],
    ]
    patchday3ng_models_dir = rpf_paths_cfg.get("patchday3ng_models_extracted")
    if patchday3ng_models_dir is not None:
        staging_target_dirs.append(patchday3ng_models_dir)
    for optional_work_dir in (
        project_root_dir / "1_Franklin_Shinano_Casual" / "5_rpf_package" / "patchday3_work" / "patchday3_extracted",
        project_root_dir / "2_Michael_Shinano_EternalReunion" / "5_rpf_package" / "mppatches_work" / "mppatches_extracted",
    ):
        if optional_work_dir.is_dir() and optional_work_dir not in staging_target_dirs:
            staging_target_dirs.append(optional_work_dir)

    return {
        "project_root": project_root_dir,
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

    source_model_path = Path(character_configuration["model_ydd_path"])
    raw_model_racial_path = character_configuration.get("model_r_ydd_path")
    source_model_racial_path = (
        Path(raw_model_racial_path)
        if raw_model_racial_path and Path(raw_model_racial_path).exists()
        else source_model_path
    )
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
                lower_stem = target_file_path.stem.lower()
                is_race_slot = lower_stem.endswith("_r") or "_r_" in lower_stem
                chosen_model_path = (
                    source_model_racial_path if is_race_slot else source_model_path
                )
                shutil.copyfile(chosen_model_path, target_file_path)
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


def apply_selected_characters(
    characters_to_apply: List[str],
    avatar_overrides: Optional[Dict[str, str]] = None,
) -> bool:
    """Apply compiled models, textures, skeletons, and dummies for the given characters."""
    runtime_cfg = _load_apply_runtime_config(avatar_overrides=avatar_overrides)
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

    npc_registry = npc_registry_helper.load_npc_registry().get("npcs", {})

    for raw_character_key in characters_to_apply:
        norm_npc_key = npc_registry_helper.normalize_ped_model_name(raw_character_key)
        if raw_character_key not in character_registry and norm_npc_key in npc_registry:
            npc_entry = npc_registry[norm_npc_key]
            print(
                f"[NPC] Patching registered NPC '{norm_npc_key}' ({npc_entry.get('avatar_name', 'avatar')})...",
                flush=True,
            )
            npc_registry_helper.apply_npc_slot_replacement(norm_npc_key, npc_entry)
            continue

        if raw_character_key in character_registry:
            character_key = raw_character_key
        else:
            try:
                character_key = str(
                    project_paths.get_protagonist_profile(raw_character_key)["ped_name"]
                )
            except KeyError:
                character_key = raw_character_key

        if character_key not in character_registry:
            print(
                project_i18n.translate(
                    "apply.unknown_character", character_key=raw_character_key
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

        for resource_check_path in (
            character_data["model_ydd_path"],
            character_data.get("model_r_ydd_path"),
            character_data["texture_ytd_path"],
            character_data["skeleton_yft_path"],
        ):
            if resource_check_path and Path(resource_check_path).is_file():
                ped_damage_helper.validate_rpf7_resource_file(resource_check_path)

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
                skeleton_src_path = Path(character_data["skeleton_yft_path"])
                if not skeleton_src_path.is_file():
                    raise FileNotFoundError(
                        project_i18n.translate(
                            "apply.missing_skeleton_yft", path=skeleton_src_path
                        )
                    )
                target_yft_destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(skeleton_src_path, target_yft_destination)
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
        choices=[
            "player_zero",
            "player_one",
            "player_two",
            "michael",
            "franklin",
            "trevor",
            "all",
        ],
        default="all",
        help=project_i18n.translate("apply.cli_character_help"),
    )
    argument_parser.add_argument(
        "--avatar",
        default=None,
        help=project_i18n.translate("apply.cli_avatar"),
    )
    argument_parser.add_argument(
        "--michael-avatar",
        default=None,
        help=project_i18n.translate(
            "apply.cli_protagonist_avatar",
            protagonist=project_i18n.translate("protagonist.michael"),
        ),
    )
    argument_parser.add_argument(
        "--franklin-avatar",
        default=None,
        help=project_i18n.translate(
            "apply.cli_protagonist_avatar",
            protagonist=project_i18n.translate("protagonist.franklin"),
        ),
    )
    argument_parser.add_argument(
        "--trevor-avatar",
        default=None,
        help=project_i18n.translate(
            "apply.cli_protagonist_avatar",
            protagonist=project_i18n.translate("protagonist.trevor"),
        ),
    )
    argument_parser.add_argument(
        "--npc",
        nargs="+",
        default=None,
        help="One or more registered GTA V NPC ped names (e.g. ig_lamardavis)",
    )
    argument_parser.add_argument(
        "--all-npcs",
        action="store_true",
        help="Also apply all NPCs registered in configs/npc_registry.json",
    )
    argument_parser.add_argument(
        "--lang",
        choices=["auto", "en", "ja", "pt"],
        default="auto",
        help=project_i18n.translate("common.language_option_help"),
    )
    parsed_arguments = argument_parser.parse_args()
    project_i18n.set_active_language(parsed_arguments.lang)

    if parsed_arguments.npc:
        selected_protagonists = []
        selected_characters_list = [
            npc_registry_helper.normalize_ped_model_name(npc_name)
            for npc_name in parsed_arguments.npc
        ]
    elif parsed_arguments.character == "all":
        selected_protagonists = list(project_paths.list_available_protagonists())
        selected_characters_list = [
            str(project_paths.get_protagonist_profile(prot_key)["ped_name"])
            for prot_key in selected_protagonists
        ]
    else:
        selected_protagonists = [
            project_paths.normalize_protagonist_key(parsed_arguments.character)
        ]
        selected_characters_list = [
            str(project_paths.get_protagonist_profile(prot_key)["ped_name"])
            for prot_key in selected_protagonists
        ]

    if parsed_arguments.all_npcs:
        for reg_npc_name in sorted(npc_registry_helper.load_npc_registry().get("npcs", {}).keys()):
            if reg_npc_name not in selected_characters_list:
                selected_characters_list.append(reg_npc_name)

    avatar_overrides: Dict[str, str] = {}
    if parsed_arguments.avatar:
        normalized_avatar = project_paths.normalize_avatar_id(parsed_arguments.avatar)
        for prot_key in selected_protagonists:
            avatar_overrides[prot_key] = normalized_avatar
    for prot_key, arg_attr in (
        ("michael", "michael_avatar"),
        ("franklin", "franklin_avatar"),
        ("trevor", "trevor_avatar"),
    ):
        specific_avatar = getattr(parsed_arguments, arg_attr, None)
        if specific_avatar:
            avatar_overrides[prot_key] = project_paths.normalize_avatar_id(
                specific_avatar
            )

    operation_success = apply_selected_characters(
        selected_characters_list,
        avatar_overrides=avatar_overrides,
    )
    if not operation_success:
        sys.exit(1)


if __name__ == "__main__":
    main()
