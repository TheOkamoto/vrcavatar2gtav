#!/usr/bin/env python3
"""
deploy_michael_er.py
====================
Applies Universal Slot Replacement (Michael player_zero & Franklin player_one)
in Grand Theft Auto V Legacy:
  1. Replaces torso slots (uppr_000 through uppr_031) with the compiled avatars.
  2. Updates torso texture dictionaries (uppr_diff_000 through uppr_diff_031).
  3. Replaces remaining human slots (lowr, feet, head, hair, berd, teef, hand,
     accs, decl, task, jbib) with invisible 1 KB dummy drawables.
  4. Replaces glasses props (p_eyes_*.ydd) with prop dummies.
  5. Updates mppatchesng and patchday3ng DLC archives.
  6. Applies nested RPF binary TOC fix (file_size = 0) to prevent ERR_GEN_ZLIB_2.
  7. Verifies final RPF integrity with `rage verify`.
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

_CURRENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CURRENT_DIR.parent.parent
for _tools_dir in (_REPO_ROOT / "scripts" / "common_tools", _REPO_ROOT / "_deploy_tools"):
    if _tools_dir.is_dir() and str(_tools_dir) not in sys.path:
        sys.path.insert(0, str(_tools_dir))

import ped_damage_helper
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


def execute_shell_task(command_arguments, task_description):
    """Run an external command with strict error checking and localized logging."""
    print(i18n.translate("michael.deploy.task_start", description=task_description))
    completed_process = subprocess.run(
        command_arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed_process.returncode != 0:
        print(
            i18n.translate(
                "michael.deploy.task_failed", command=" ".join(command_arguments)
            )
        )
        print(f"Stdout:\n{completed_process.stdout}")
        print(f"Stderr:\n{completed_process.stderr}")
        raise RuntimeError(
            i18n.translate("michael.deploy.task_error", description=task_description)
        )
    print(i18n.translate("michael.deploy.task_done", description=task_description))
    return completed_process.stdout


def patch_rpf_table_of_contents(rpf_archive_path):
    """
    Patch nested RPF TOC entries by setting file_size = 0.
    Required by RAGE Engine to avoid ERR_GEN_ZLIB_2 on nested OPEN archives.
    """
    print(i18n.translate("michael.deploy.toc_patching", path=rpf_archive_path))
    with open(rpf_archive_path, "r+b") as file_stream:
        _magic_number, entry_count, _names_byte_len, _encryption_code = struct.unpack(
            "<IIII", file_stream.read(16)
        )
        table_bytes = file_stream.read(entry_count * 16)
        patched_entries_counter = 0

        for entry_idx in range(entry_count):
            entry_chunk = bytearray(table_bytes[entry_idx * 16 : (entry_idx + 1) * 16])
            header_flag = struct.unpack("<I", entry_chunk[4:8])[0]
            if header_flag == 0x7FFFFF00 or (header_flag & 0x80000000) != 0:
                continue

            file_size_val = entry_chunk[2] | (entry_chunk[3] << 8) | (entry_chunk[4] << 16)
            if file_size_val != 0:
                entry_chunk[2] = 0
                entry_chunk[3] = 0
                entry_chunk[4] = 0
                file_stream.seek(16 + entry_idx * 16)
                file_stream.write(entry_chunk)
                patched_entries_counter += 1

    limit_report = ped_damage_helper.inspect_rpf7_archive_limits(rpf_archive_path)
    if limit_report["resource_overflows"] or limit_report["offset_overflows"]:
        raise ValueError(
            f"RPF7 limit overflow in {rpf_archive_path}: {limit_report}"
        )

    print(i18n.translate("michael.deploy.toc_patched", count=patched_entries_counter))


def apply_universal_slots_to_ped(
    ped_directory,
    source_uppr_u,
    source_uppr_r,
    source_ytd,
    dummy_source_path,
    ped_label,
):
    """Replace all uppr_* slots with the full avatar and convert other slots to dummies."""
    print(
        i18n.translate(
            "michael.deploy.applying_ped", label=ped_label, directory=ped_directory
        )
    )
    all_filenames = os.listdir(ped_directory)
    uppr_count = 0
    ytd_count = 0
    dummy_count = 0

    for filename in all_filenames:
        target_path = os.path.join(ped_directory, filename)

        if filename.startswith("uppr_") and filename.endswith(".ydd"):
            if filename.endswith("_r.ydd") or "_r_" in filename:
                shutil.copy2(source_uppr_r, target_path)
            else:
                shutil.copy2(source_uppr_u, target_path)
            uppr_count += 1
        elif filename.startswith("uppr_diff_") and filename.endswith(".ytd"):
            shutil.copy2(source_ytd, target_path)
            ytd_count += 1
        elif filename.endswith(".ydd") and not filename.startswith("uppr_"):
            shutil.copy2(dummy_source_path, target_path)
            dummy_count += 1

    print(
        i18n.translate(
            "michael.deploy.ped_summary",
            label=ped_label,
            uppr=uppr_count,
            ytd=ytd_count,
            dummy=dummy_count,
        )
    )


def deploy_universal():
    """Execute the full universal slot deployment pipeline for Michael and Franklin."""
    michael_cfg = project_paths.get_character_paths("michael")
    franklin_cfg = project_paths.get_character_paths("franklin")
    rpf_paths_cfg = project_paths.get_rpf_paths()
    staging_dir = project_paths.get_staging_dir()

    rage_tool_path = str(project_paths.get_rage_cli())
    dummy_source_path = str(project_paths.get_dummy_ydd_path())
    prop_dummy_source_path = str(project_paths.get_prop_dummy_ydd_path())

    michael_er_dir = str(michael_cfg["character_dir"])
    michael_uppr_u = str(michael_cfg["target_model_ydd"])
    extra_michael_ydds = list(michael_cfg.get("extra_model_ydds") or [])
    michael_uppr_r = str(extra_michael_ydds[0]) if extra_michael_ydds else michael_uppr_u
    michael_ytd = str(michael_cfg["ytd_file"])

    franklin_dir = str(franklin_cfg["character_dir"])
    franklin_uppr_u = str(franklin_cfg["target_model_ydd"])
    franklin_ytd = str(franklin_cfg["ytd_file"])

    streamed_base_dir = str(rpf_paths_cfg["streamedpeds_extracted"])
    player_zero_dir = str(michael_cfg["staging_streamed_ped_dir"])
    player_one_dir = str(franklin_cfg["staging_streamed_ped_dir"])
    streamedprops_base_dir = str(rpf_paths_cfg["streamedpedprops_extracted"])
    player_zero_props_dir = str(michael_cfg["staging_streamed_props_dir"])
    player_one_props_dir = str(franklin_cfg["staging_streamed_props_dir"])

    streamed_target_rpf = str(staging_dir / "streamedpeds_players_shinano.rpf")
    streamedprops_target_rpf = str(staging_dir / "streamedpedprops_shinano.rpf")
    x64v_extracted_dir = str(rpf_paths_cfg["x64v_extracted"])
    x64v_modded_rpf = str(rpf_paths_cfg["x64v_modded_rpf"])
    gtav_mods_x64v_rpf = str(rpf_paths_cfg["x64v_game_rpf"])

    staging_mppatches_seed = str(rpf_paths_cfg["mppatches_extracted"])
    staging_mppatchesng_seed = str(rpf_paths_cfg["mppatches_dlc_extracted"])
    mppatches_work_dir = os.path.join(michael_er_dir, "5_rpf_package", "mppatches_work")
    mppatches_extracted_dir = os.path.join(mppatches_work_dir, "mppatches_extracted")
    mppatchesng_extracted_dir = os.path.join(mppatches_work_dir, "mppatchesng_extracted")
    mppatches_target_rpf = os.path.join(mppatches_work_dir, "mppatches.rpf")
    mppatchesng_target_rpf = os.path.join(mppatches_work_dir, "mppatchesng_dlc.rpf")
    gtav_mods_mppatchesng_dlc_rpf = str(rpf_paths_cfg["mppatches_game_rpf"])

    patchday3_work_dir = os.path.join(franklin_dir, "5_rpf_package", "patchday3_work")
    patchday3_extracted_dir = os.path.join(patchday3_work_dir, "patchday3_extracted")
    patchday3ng_extracted_dir = os.path.join(patchday3_work_dir, "patchday3ng_extracted")
    patchday3_target_rpf = os.path.join(patchday3_work_dir, "patchday3ng.rpf")
    patchday3ng_target_rpf = os.path.join(patchday3_work_dir, "patchday3ng_dlc.rpf")
    gtav_mods_patchday3ng_dlc_rpf = str(rpf_paths_cfg["patchday3ng_game_rpf"])

    print("======================================================================")
    print(i18n.translate("michael.deploy.banner"))
    print("======================================================================")

    # 1. Verify required source artifacts exist
    for required_path in (
        michael_uppr_u,
        michael_uppr_r,
        michael_ytd,
        franklin_uppr_u,
        franklin_ytd,
        dummy_source_path,
        prop_dummy_source_path,
    ):
        if not os.path.exists(required_path):
            raise FileNotFoundError(
                i18n.translate("michael.deploy.missing_file", path=required_path)
            )

    # 2. Apply universal slot replacement in streamedpeds_players_extracted
    apply_universal_slots_to_ped(
        player_zero_dir,
        michael_uppr_u,
        michael_uppr_r,
        michael_ytd,
        dummy_source_path,
        "Michael (player_zero)",
    )
    apply_universal_slots_to_ped(
        player_one_dir,
        franklin_uppr_u,
        franklin_uppr_u,
        franklin_ytd,
        dummy_source_path,
        "Franklin (player_one)",
    )
    if os.path.exists(str(michael_cfg["target_yft"])):
        shutil.copy2(
            str(michael_cfg["target_yft"]),
            os.path.join(streamed_base_dir, "player_zero.yft"),
        )
    if os.path.exists(str(franklin_cfg["target_yft"])):
        shutil.copy2(
            str(franklin_cfg["target_yft"]),
            os.path.join(streamed_base_dir, "player_one.yft"),
        )

    # 3. Pack streamedpeds_players.rpf and inject into x64v_extracted
    print(i18n.translate("michael.deploy.packing_streamed"))
    execute_shell_task(
        [
            rage_tool_path,
            "create",
            "-o",
            streamed_target_rpf,
            streamed_base_dir,
            "-e",
            "open",
        ],
        i18n.translate("michael.deploy.task_pack_streamed"),
    )

    nested_streamed_dest = os.path.join(
        x64v_extracted_dir, "models", "cdimages", "streamedpeds_players.rpf"
    )
    shutil.copy2(streamed_target_rpf, nested_streamed_dest)
    print(i18n.translate("michael.deploy.updated_path", path=nested_streamed_dest))

    # 3B. Replace glasses props (p_eyes_*.ydd) in streamedpedprops and pack RPF
    project_paths.ensure_streamedpedprops_extracted()
    project_paths.patch_character_glasses_props(
        player_zero_props_dir, prop_dummy_source_path, "player_zero_p"
    )
    project_paths.patch_character_glasses_props(
        player_one_props_dir, prop_dummy_source_path, "player_one_p"
    )
    execute_shell_task(
        [
            rage_tool_path,
            "create",
            "-o",
            streamedprops_target_rpf,
            streamedprops_base_dir,
            "-e",
            "open",
        ],
        i18n.translate("michael.deploy.task_pack_props"),
    )
    patch_rpf_table_of_contents(streamedprops_target_rpf)
    nested_props_dest = str(
        rpf_paths_cfg["x64v_extracted"] / rpf_paths_cfg["streamedpedprops_rpf_relative"]
    )
    shutil.copy2(streamedprops_target_rpf, nested_props_dest)
    print(i18n.translate("michael.deploy.updated_path", path=nested_props_dest))

    # 4. Pack x64v_modded.rpf and patch TOC
    print(i18n.translate("michael.deploy.packing_x64v"))
    execute_shell_task(
        [
            rage_tool_path,
            "create",
            "-o",
            x64v_modded_rpf,
            x64v_extracted_dir,
            "-e",
            "open",
        ],
        i18n.translate("michael.deploy.task_pack_x64v"),
    )
    patch_rpf_table_of_contents(x64v_modded_rpf)
    execute_shell_task(
        [rage_tool_path, "verify", x64v_modded_rpf],
        i18n.translate("michael.deploy.task_verify_x64v"),
    )

    print(
        i18n.translate(
            "michael.deploy.copying_to", src="x64v_modded.rpf", dest=gtav_mods_x64v_rpf
        )
    )
    shutil.copy2(x64v_modded_rpf, gtav_mods_x64v_rpf)
    execute_shell_task(
        [rage_tool_path, "verify", gtav_mods_x64v_rpf],
        i18n.translate("michael.deploy.task_verify_target", path=gtav_mods_x64v_rpf),
    )

    # 5. Update mppatchesng DLC and staging seed
    print(i18n.translate("michael.deploy.updating_mppatches"))
    staging_mppatches_zero_dir = os.path.join(staging_mppatches_seed, "player_zero")
    if os.path.exists(staging_mppatches_zero_dir):
        apply_universal_slots_to_ped(
            staging_mppatches_zero_dir,
            michael_uppr_u,
            michael_uppr_r,
            michael_ytd,
            dummy_source_path,
            "Michael (mppatches staging)",
        )
    staging_mppatches_one_dir = os.path.join(staging_mppatches_seed, "player_one")
    if os.path.exists(staging_mppatches_one_dir):
        apply_universal_slots_to_ped(
            staging_mppatches_one_dir,
            franklin_uppr_u,
            franklin_uppr_u,
            franklin_ytd,
            dummy_source_path,
            "Franklin (mppatches staging)",
        )
    os.makedirs(mppatches_work_dir, exist_ok=True)
    if not os.path.exists(mppatches_extracted_dir):
        shutil.copytree(staging_mppatches_seed, mppatches_extracted_dir)
    if not os.path.exists(mppatchesng_extracted_dir):
        shutil.copytree(staging_mppatchesng_seed, mppatchesng_extracted_dir)

    michael_mppatches_dir = os.path.join(mppatches_extracted_dir, "player_zero")
    if os.path.exists(michael_mppatches_dir):
        for entry_filename in os.listdir(michael_mppatches_dir):
            entry_filepath = os.path.join(michael_mppatches_dir, entry_filename)
            if entry_filename.startswith("uppr_") and entry_filename.endswith(".ydd"):
                shutil.copy2(michael_uppr_u, entry_filepath)
            elif entry_filename.startswith("uppr_diff_") and entry_filename.endswith(".ytd"):
                shutil.copy2(michael_ytd, entry_filepath)
            elif entry_filename.endswith(".ydd"):
                shutil.copy2(dummy_source_path, entry_filepath)

    franklin_mppatches_dir = os.path.join(mppatches_extracted_dir, "player_one")
    if os.path.exists(franklin_mppatches_dir):
        for entry_filename in os.listdir(franklin_mppatches_dir):
            entry_filepath = os.path.join(franklin_mppatches_dir, entry_filename)
            if entry_filename.startswith("uppr_") and entry_filename.endswith(".ydd"):
                shutil.copy2(franklin_uppr_u, entry_filepath)
            elif entry_filename.startswith("uppr_diff_") and entry_filename.endswith(".ytd"):
                shutil.copy2(franklin_ytd, entry_filepath)
            elif entry_filename.endswith(".ydd"):
                shutil.copy2(dummy_source_path, entry_filepath)

    execute_shell_task(
        [
            rage_tool_path,
            "create",
            "-o",
            mppatches_target_rpf,
            mppatches_extracted_dir,
            "-e",
            "open",
        ],
        i18n.translate("michael.deploy.task_pack_mppatches"),
    )

    nested_mppatches_dest = os.path.join(
        mppatchesng_extracted_dir, "x64", "models", "cdimages", "mppatches.rpf"
    )
    shutil.copy2(mppatches_target_rpf, nested_mppatches_dest)

    execute_shell_task(
        [
            rage_tool_path,
            "create",
            "-o",
            mppatchesng_target_rpf,
            mppatchesng_extracted_dir,
            "-e",
            "open",
        ],
        i18n.translate("michael.deploy.task_pack_mppatches_dlc"),
    )
    patch_rpf_table_of_contents(mppatchesng_target_rpf)
    execute_shell_task(
        [rage_tool_path, "verify", mppatchesng_target_rpf],
        i18n.translate("michael.deploy.task_verify_mppatches_dlc"),
    )

    print(
        i18n.translate(
            "michael.deploy.copying_to",
            src="mppatchesng_dlc.rpf",
            dest=gtav_mods_mppatchesng_dlc_rpf,
        )
    )
    shutil.copy2(mppatchesng_target_rpf, gtav_mods_mppatchesng_dlc_rpf)
    execute_shell_task(
        [rage_tool_path, "verify", gtav_mods_mppatchesng_dlc_rpf],
        i18n.translate("michael.deploy.task_verify_target", path="mppatchesng/dlc.rpf"),
    )

    # 6. Update patchday3ng DLC
    print(i18n.translate("michael.deploy.updating_patchday3"))
    os.makedirs(patchday3_work_dir, exist_ok=True)
    if not os.path.exists(patchday3ng_extracted_dir):
        execute_shell_task(
            [
                rage_tool_path,
                "extract",
                "-o",
                patchday3ng_extracted_dir,
                gtav_mods_patchday3ng_dlc_rpf,
            ],
            i18n.translate("michael.deploy.task_extract_patchday3_dlc"),
        )

    nested_patchday3_rpf_path = os.path.join(
        patchday3ng_extracted_dir, "x64", "models", "cdimages", "patchday3ng.rpf"
    )
    if not os.path.exists(patchday3_extracted_dir):
        execute_shell_task(
            [
                rage_tool_path,
                "extract",
                "-o",
                patchday3_extracted_dir,
                nested_patchday3_rpf_path,
            ],
            i18n.translate("michael.deploy.task_extract_patchday3_rpf"),
        )

    franklin_patchday3_dir = os.path.join(patchday3_extracted_dir, "player_one")
    if os.path.exists(franklin_patchday3_dir):
        franklin_target_ydd = os.path.join(franklin_patchday3_dir, "uppr_008_u.ydd")
        shutil.copy2(franklin_uppr_u, franklin_target_ydd)
        print(i18n.translate("michael.deploy.updated_path", path=franklin_target_ydd))

    michael_patchday3_dir = os.path.join(patchday3_extracted_dir, "player_zero")
    if os.path.exists(michael_patchday3_dir):
        apply_universal_slots_to_ped(
            michael_patchday3_dir,
            michael_uppr_u,
            michael_uppr_r,
            michael_ytd,
            dummy_source_path,
            "Michael (patchday3ng)",
        )

    execute_shell_task(
        [
            rage_tool_path,
            "create",
            "-o",
            patchday3_target_rpf,
            patchday3_extracted_dir,
            "-e",
            "open",
        ],
        i18n.translate("michael.deploy.task_pack_patchday3_rpf"),
    )

    shutil.copy2(patchday3_target_rpf, nested_patchday3_rpf_path)

    execute_shell_task(
        [
            rage_tool_path,
            "create",
            "-o",
            patchday3ng_target_rpf,
            patchday3ng_extracted_dir,
            "-e",
            "open",
        ],
        i18n.translate("michael.deploy.task_pack_patchday3_dlc"),
    )
    patch_rpf_table_of_contents(patchday3ng_target_rpf)
    execute_shell_task(
        [rage_tool_path, "verify", patchday3ng_target_rpf],
        i18n.translate("michael.deploy.task_verify_patchday3_dlc"),
    )

    print(
        i18n.translate(
            "michael.deploy.copying_to",
            src="patchday3ng_dlc.rpf",
            dest=gtav_mods_patchday3ng_dlc_rpf,
        )
    )
    shutil.copy2(patchday3ng_target_rpf, gtav_mods_patchday3ng_dlc_rpf)
    execute_shell_task(
        [rage_tool_path, "verify", gtav_mods_patchday3ng_dlc_rpf],
        i18n.translate("michael.deploy.task_verify_target", path="patchday3ng/dlc.rpf"),
    )

    # 7. Update patchday4ng DLC (e.g. player_zero/uppr_008_r.ydd)
    patchday4_dlc_extracted = str(rpf_paths_cfg["patchday4ng_dlc_extracted"])
    patchday4_models_dir = str(rpf_paths_cfg["patchday4ng_models_extracted"])
    nested_patchday4_rpf_path = os.path.join(
        patchday4_dlc_extracted, str(rpf_paths_cfg["patchday4ng_rpf_relative"])
    )
    patchday4_dlc_target_rpf = str(rpf_paths_cfg["patchday4ng_modded_rpf"])
    gtav_mods_patchday4ng_dlc_rpf = str(rpf_paths_cfg["patchday4ng_game_rpf"])

    if os.path.exists(patchday4_dlc_extracted) and os.path.exists(patchday4_models_dir):
        michael_patchday4_dir = os.path.join(patchday4_models_dir, "player_zero")
        if os.path.exists(michael_patchday4_dir):
            apply_universal_slots_to_ped(
                michael_patchday4_dir,
                michael_uppr_u,
                michael_uppr_r,
                michael_ytd,
                dummy_source_path,
                "Michael (patchday4ng)",
            )
        franklin_patchday4_dir = os.path.join(patchday4_models_dir, "player_one")
        if os.path.exists(franklin_patchday4_dir):
            apply_universal_slots_to_ped(
                franklin_patchday4_dir,
                franklin_uppr_u,
                franklin_uppr_u,
                franklin_ytd,
                dummy_source_path,
                "Franklin (patchday4ng)",
            )

        if os.path.exists(nested_patchday4_rpf_path):
            os.remove(nested_patchday4_rpf_path)
        execute_shell_task(
            [
                rage_tool_path,
                "create",
                "-o",
                nested_patchday4_rpf_path,
                patchday4_models_dir,
                "-e",
                "open",
            ],
            "Pack patchday4ng.rpf",
        )
        patch_rpf_table_of_contents(nested_patchday4_rpf_path)

        if os.path.exists(patchday4_dlc_target_rpf):
            os.remove(patchday4_dlc_target_rpf)
        execute_shell_task(
            [
                rage_tool_path,
                "create",
                "-o",
                patchday4_dlc_target_rpf,
                patchday4_dlc_extracted,
                "-e",
                "open",
            ],
            "Pack patchday4ng dlc.rpf",
        )
        patch_rpf_table_of_contents(patchday4_dlc_target_rpf)
        execute_shell_task(
            [rage_tool_path, "verify", patchday4_dlc_target_rpf],
            i18n.translate("michael.deploy.task_verify_target", path="patchday4ng_dlc.rpf"),
        )

        print(
            i18n.translate(
                "michael.deploy.copying_to",
                src="patchday4ng_dlc.rpf",
                dest=gtav_mods_patchday4ng_dlc_rpf,
            )
        )
        shutil.copy2(patchday4_dlc_target_rpf, gtav_mods_patchday4ng_dlc_rpf)
        execute_shell_task(
            [rage_tool_path, "verify", gtav_mods_patchday4ng_dlc_rpf],
            i18n.translate("michael.deploy.task_verify_target", path="patchday4ng/dlc.rpf"),
        )

    print("\n======================================================================")
    print(i18n.translate("michael.deploy.done"))
    print("======================================================================")


def main() -> int:
    """CLI entry point for deploying Michael and Franklin universal slots."""
    resolve_startup_language()
    parser = argparse.ArgumentParser(description=i18n.translate("michael.deploy.cli_desc"))
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

    deploy_universal()
    return 0


if __name__ == "__main__":
    sys.exit(main())
