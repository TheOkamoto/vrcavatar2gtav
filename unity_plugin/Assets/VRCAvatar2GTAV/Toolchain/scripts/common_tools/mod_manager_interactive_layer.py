#!/usr/bin/env python3
"""
mod_manager_interactive_layer.py
================================
Interactive menu prompt handlers for the VRC Avatar -> GTA V orchestrator
(`run_mod_manager` layered architecture).

Provides guided CLI flows for:
  - Assigning VRChat avatars across protagonists (`michael`/`franklin`/`trevor`)
  - Scanning and saving Unity custom hair overrides (`--hair`)
  - Synchronizing `.cfg` blendshape & VRCPhysBone presets
  - Launching the interactive Universal NPC & Street Pedestrian builder (`[11]`)
"""

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import blendshape_helper
    import physbone_helper
    import unity_hair_helper
    import vrc2gtav_i18n as project_i18n
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import blendshape_helper
    from common_tools import physbone_helper
    from common_tools import unity_hair_helper
    from common_tools import vrc2gtav_i18n as project_i18n
    from common_tools import vrc2gtav_paths as project_paths


def print_section_header(section_title: str) -> None:
    """Print an ASCII section header without emojis."""
    separator_line = "=" * 70
    print(f"\n{separator_line}")
    print(f"  {section_title}")
    print(f"{separator_line}\n")


def _prompt_protagonist_selection(
    header_key: str,
    select_prompt_key: str,
) -> Optional[str]:
    """Prompt the user to choose a GTA V protagonist key ('michael'/'franklin'/'trevor')."""
    print_section_header(project_i18n.translate(header_key))
    protagonists = list(project_paths.list_available_protagonists())

    print(project_i18n.translate(select_prompt_key))
    for opt_index, protagonist_key in enumerate(protagonists, start=1):
        char_cfg = project_paths.get_character_paths(protagonist_key)
        current_avatar_label = project_i18n.translate(f"avatar.{char_cfg['avatar_id']}")
        protagonist_label = project_i18n.translate(f"protagonist.{protagonist_key}")
        print(
            project_i18n.translate(
                "manager.menu_opt_slot",
                opt=opt_index,
                protagonist=protagonist_label,
                ped_name=char_cfg["ped_name"],
                avatar=current_avatar_label,
            )
        )
    print(project_i18n.translate("manager.menu_opt_0"))
    prot_choice = input(project_i18n.translate("manager.swap_prompt_choice")).strip()
    if prot_choice == "0":
        return None
    if prot_choice not in {str(idx) for idx in range(1, len(protagonists) + 1)}:
        print(project_i18n.translate("manager.invalid_option"))
        return None
    return protagonists[int(prot_choice) - 1]


def run_interactive_avatar_swap() -> bool:
    """Interactively assign any VRChat avatar preset to any GTA V protagonist."""
    chosen_protagonist = _prompt_protagonist_selection(
        "manager.swap_header",
        "manager.swap_select_protagonist",
    )
    if chosen_protagonist is None:
        return False

    avatars = list(project_paths.list_available_avatars())
    chosen_prot_label = project_i18n.translate(f"protagonist.{chosen_protagonist}")

    print()
    print(
        project_i18n.translate(
            "manager.swap_select_avatar", protagonist=chosen_prot_label
        )
    )
    for opt_index, avatar_id in enumerate(avatars, start=1):
        print(f"  [{opt_index}] {project_i18n.translate(f'avatar.{avatar_id}')} ({avatar_id})")
    print(project_i18n.translate("manager.menu_opt_0"))
    avatar_choice = input(project_i18n.translate("manager.swap_prompt_choice")).strip()
    if avatar_choice == "0":
        return False
    if avatar_choice not in {str(idx) for idx in range(1, len(avatars) + 1)}:
        print(project_i18n.translate("manager.invalid_option"))
        return False
    chosen_avatar = avatars[int(avatar_choice) - 1]

    project_paths.set_protagonist_avatar(chosen_protagonist, chosen_avatar)
    print(
        project_i18n.translate(
            "manager.swap_saved",
            protagonist=chosen_prot_label,
            avatar=project_i18n.translate(f"avatar.{chosen_avatar}"),
        )
    )
    return True


def run_interactive_hair_config(unity_assets_directory: Optional[Path] = None) -> bool:
    """Scan Unity Assets and configure custom hair overrides for any protagonist."""
    chosen_protagonist = _prompt_protagonist_selection(
        "manager.hair_header",
        "manager.hair_select_protagonist",
    )
    if chosen_protagonist is None:
        return False

    char_cfg = project_paths.get_character_paths(chosen_protagonist)
    chosen_prot_label = project_i18n.translate(f"protagonist.{chosen_protagonist}")
    current_hair_display = (
        str(char_cfg.get("custom_hair", "")).strip()
        or str(char_cfg.get("fbx_hair", "")).strip()
        or "auto"
    )
    print()
    print(
        project_i18n.translate(
            "manager.hair_current",
            protagonist=chosen_prot_label,
            current=current_hair_display,
        )
    )
    print(project_i18n.translate("manager.hair_scanning"))

    candidates = unity_hair_helper.scan_custom_hair_candidates(
        unity_assets_directory or project_paths.get_vrc_assets_dir(),
        max_results=30,
    )

    print()
    print(
        project_i18n.translate(
            "manager.hair_select_source", protagonist=chosen_prot_label
        )
    )
    print(project_i18n.translate("manager.hair_opt_auto"))
    print(project_i18n.translate("manager.hair_opt_default"))
    print(project_i18n.translate("manager.hair_opt_none"))
    if candidates:
        for idx_offset, item_entry in enumerate(candidates, start=4):
            kind_tag = item_entry.get("kind", "prefab")
            rel_label = (
                item_entry.get("relative_path")
                or item_entry.get("relative")
                or item_entry.get("path", "")
            )
            print(f"  [{idx_offset}] [{kind_tag}] {rel_label}")
    else:
        print(project_i18n.translate("manager.hair_no_candidates"))
    print(project_i18n.translate("manager.hair_opt_manual"))
    print(project_i18n.translate("manager.menu_opt_0"))

    user_choice = input(project_i18n.translate("manager.hair_prompt_choice")).strip()
    if user_choice == "0":
        return False

    chosen_hair_value = ""
    if user_choice == "1":
        chosen_hair_value = "auto"
    elif user_choice == "2":
        chosen_hair_value = "default"
    elif user_choice == "3":
        chosen_hair_value = "none"
    elif user_choice.lower() == "m":
        manual_raw = (
            input(project_i18n.translate("manager.hair_prompt_manual_path"))
            .strip()
            .strip('"')
            .strip("'")
        )
        if not manual_raw:
            return False
        manual_host = project_paths.to_host_path(manual_raw)
        if not manual_host.exists():
            print(project_i18n.translate("manager.hair_path_missing", path=manual_raw))
            return False
        chosen_hair_value = str(manual_host)
    else:
        try:
            numeric_choice = int(user_choice)
        except ValueError:
            print(project_i18n.translate("manager.invalid_option"))
            return False
        cand_index = numeric_choice - 4
        if cand_index < 0 or cand_index >= len(candidates):
            print(project_i18n.translate("manager.invalid_option"))
            return False
        chosen_hair_value = str(candidates[cand_index]["path"])

    scale_input = input(project_i18n.translate("manager.hair_prompt_scale")).strip()
    offset_input = input(project_i18n.translate("manager.hair_prompt_offset")).strip()

    saved_section = project_paths.set_character_custom_hair(
        chosen_protagonist,
        chosen_hair_value,
        hair_scale=scale_input if scale_input else None,
        hair_offset=offset_input if offset_input else None,
    )
    print(
        project_i18n.translate(
            "manager.hair_saved",
            hair=chosen_hair_value,
            section=saved_section,
        )
    )
    return True


def run_blendshape_cfg_export(
    target_avatars: List[str],
    output_override: Optional[str] = None,
    preserve_existing_cfg: bool = True,
) -> bool:
    """Export/sync FBX & Unity blendshapes into configs/*_blendshapes.cfg."""
    all_exported = True
    for char_section in target_avatars:
        single_override = (
            output_override if len(target_avatars) == 1 and output_override else None
        )
        exported_path = blendshape_helper.export_character_blendshapes_to_cfg(
            char_section,
            output_cfg_path=single_override,
            preserve_existing_cfg=preserve_existing_cfg,
        )
        if exported_path is not None:
            print(
                project_i18n.translate(
                    "manager.export_blendshapes_ok",
                    char=char_section,
                    path=exported_path,
                )
            )
        else:
            print(
                project_i18n.translate(
                    "manager.export_blendshapes_skipped",
                    char=char_section,
                )
            )
            all_exported = False
    return all_exported


def run_interactive_blendshape_sync() -> bool:
    """Interactively populate configs/*_blendshapes.cfg with all FBX blendshape channels."""
    print_section_header(project_i18n.translate("manager.blendshapes_header"))
    print(project_i18n.translate("manager.blendshapes_select_avatar"))
    avatars = list(project_paths.list_available_avatars())
    for opt_index, avatar_id in enumerate(avatars, start=1):
        print(f"  [{opt_index}] {project_i18n.translate(f'avatar.{avatar_id}')} ({avatar_id})")
    all_opt_index = len(avatars) + 1
    print(project_i18n.translate("manager.blendshapes_opt_all", opt=all_opt_index))
    print(project_i18n.translate("manager.menu_opt_0"))

    user_choice = input(project_i18n.translate("manager.blendshapes_prompt_choice")).strip()
    if user_choice == "0":
        return False
    if user_choice == str(all_opt_index):
        selected_avatars = avatars
    elif user_choice in {str(idx) for idx in range(1, len(avatars) + 1)}:
        selected_avatars = [avatars[int(user_choice) - 1]]
    else:
        print(project_i18n.translate("manager.invalid_option"))
        return False

    return run_blendshape_cfg_export(selected_avatars, preserve_existing_cfg=True)


def run_physbone_cfg_export(
    target_avatars: List[str],
    output_override: Optional[str] = None,
    preserve_existing_cfg: bool = True,
    override_marshmallow: Optional[bool] = None,
) -> bool:
    """Export/sync Unity VRCPhysBones (and optional Marshmallow PB) into configs/*_physbones.cfg."""
    all_exported = True
    for char_section in target_avatars:
        single_override = (
            output_override if len(target_avatars) == 1 and output_override else None
        )
        exported_path = physbone_helper.export_character_physbones_to_cfg(
            char_section,
            output_cfg_path=single_override,
            override_marshmallow=override_marshmallow,
            preserve_existing_cfg=preserve_existing_cfg,
        )
        if exported_path is not None:
            print(
                project_i18n.translate(
                    "manager.export_physbones_ok",
                    char=char_section,
                    path=exported_path,
                ),
                flush=True,
            )
        else:
            print(
                project_i18n.translate(
                    "manager.export_physbones_skipped",
                    char=char_section,
                ),
                flush=True,
            )
            all_exported = False
    return all_exported


def run_interactive_physbone_sync() -> bool:
    """Interactively populate configs/*_physbones.cfg from Unity scenes + Marshmallow PB."""
    print_section_header(project_i18n.translate("manager.physbones_header"))
    print(project_i18n.translate("manager.physbones_select_avatar"))
    avatars = list(project_paths.list_available_avatars())
    for opt_index, avatar_id in enumerate(avatars, start=1):
        print(f"  [{opt_index}] {project_i18n.translate(f'avatar.{avatar_id}')} ({avatar_id})")
    all_opt_index = len(avatars) + 1
    print(project_i18n.translate("manager.blendshapes_opt_all", opt=all_opt_index))
    print(project_i18n.translate("manager.menu_opt_0"))

    user_choice = input(project_i18n.translate("manager.physbones_prompt_choice")).strip()
    if user_choice == "0":
        return False
    if user_choice == str(all_opt_index):
        selected_avatars = avatars
    elif user_choice in {str(opt_index) for opt_index in range(1, len(avatars) + 1)}:
        selected_avatars = [avatars[int(user_choice) - 1]]
    else:
        print(project_i18n.translate("manager.invalid_option"))
        return False

    marsh_answer = input(
        project_i18n.translate("manager.physbones_prompt_marshmallow")
    ).strip()
    use_marshmallow = project_i18n.is_affirmative_answer(marsh_answer, default_yes=False)
    return run_physbone_cfg_export(
        selected_avatars,
        preserve_existing_cfg=False,
        override_marshmallow=use_marshmallow,
    )


def run_interactive_npc_builder() -> bool:
    """Interactive prompt to convert any Unity/VRChat avatar onto any GTA V NPC."""
    import universal_gtav_builder

    print_section_header(project_i18n.translate("manager.npc_header"))
    ped_raw = input(project_i18n.translate("manager.npc_prompt_ped")).strip()
    if not ped_raw:
        return False
    source_raw = (
        input(project_i18n.translate("manager.npc_prompt_source"))
        .strip()
        .strip('"')
        .strip("'")
    )
    if not source_raw:
        return False
    avatar_raw = input(project_i18n.translate("manager.npc_prompt_avatar")).strip()
    deploy_answer = input(project_i18n.translate("manager.npc_prompt_deploy")).strip()
    should_deploy = project_i18n.is_affirmative_answer(deploy_answer, default_yes=True)
    blink_answer = input(project_i18n.translate("manager.prompt_eye_blink")).strip()
    enable_blink = project_i18n.is_affirmative_answer(blink_answer, default_yes=True)

    universal_gtav_builder.build_and_deploy_npc_from_source(
        source_spec=source_raw,
        target_ped=ped_raw,
        avatar_name=avatar_raw,
        deploy=should_deploy,
        eye_blink=enable_blink,
    )
    return True

