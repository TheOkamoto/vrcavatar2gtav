#!/usr/bin/env python3
"""
apply_miltina_to_trevor.py
==========================
Applies Miltina Maid models, texture dictionaries, and dummy drawables/props
to Trevor (`player_two`) across extracted staging directories.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

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


def patch_directory(
    target_dir,
    model_ydd_path=None,
    texture_ytd_path=None,
    dummy_ydd_path=None,
    is_mppatches=False,
):
    """Replace Trevor ped slots and dummy parts inside an extracted ped directory."""
    _ = is_mppatches
    if model_ydd_path is None or texture_ytd_path is None or dummy_ydd_path is None:
        trevor_cfg = project_paths.get_character_paths("trevor")
        model_ydd_path = model_ydd_path or str(trevor_cfg["target_model_ydd"])
        texture_ytd_path = texture_ytd_path or str(trevor_cfg["ytd_file"])
        dummy_ydd_path = dummy_ydd_path or str(project_paths.get_dummy_ydd_path())

    print(i18n.translate("trevor.apply.patching_dir", directory=target_dir))
    if not os.path.isdir(target_dir):
        raise FileNotFoundError(
            i18n.translate("trevor.apply.dir_missing", directory=target_dir)
        )

    uppr_count = 0
    ytd_count = 0
    dummy_count = 0
    skipped_count = 0

    all_files = sorted(os.listdir(target_dir))
    for filename in all_files:
        filepath = os.path.join(target_dir, filename)
        if not os.path.isfile(filepath):
            continue

        prefix = filename.split("_")[0].lower()
        ext = os.path.splitext(filename)[1].lower()

        if prefix == "uppr" and ext == ".ydd":
            shutil.copyfile(model_ydd_path, filepath)
            uppr_count += 1
        elif prefix == "uppr" and "diff" in filename and ext == ".ytd":
            shutil.copyfile(texture_ytd_path, filepath)
            ytd_count += 1
        elif ext == ".ydd" and prefix in [
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
        ]:
            shutil.copyfile(dummy_ydd_path, filepath)
            dummy_count += 1
        else:
            skipped_count += 1

    print(
        i18n.translate(
            "trevor.apply.summary",
            directory=target_dir,
            uppr=uppr_count,
            ytd=ytd_count,
            dummy=dummy_count,
            skipped=skipped_count,
        )
    )


def apply_miltina_slots() -> None:
    """Validate artifacts and patch all configured Trevor staging directories."""
    trevor_cfg = project_paths.get_character_paths("trevor")
    dummy_ydd_path = str(project_paths.get_dummy_ydd_path())
    prop_dummy_ydd_path = str(project_paths.get_prop_dummy_ydd_path())
    miltina_model_ydd_path = str(trevor_cfg["target_model_ydd"])
    miltina_texture_ytd_path = str(trevor_cfg["ytd_file"])

    mppatches_p2_dir = str(trevor_cfg["staging_mppatches_ped_dir"])
    streamedpeds_p2_dir = str(trevor_cfg["staging_streamed_ped_dir"])
    patchday4_p2_dir = str(trevor_cfg["staging_patchday4_ped_dir"])
    streamedprops_p2_dir = str(trevor_cfg["staging_streamed_props_dir"])

    if not os.path.exists(dummy_ydd_path):
        raise FileNotFoundError(
            i18n.translate("trevor.apply.dummy_missing", path=dummy_ydd_path)
        )
    if not os.path.exists(prop_dummy_ydd_path):
        raise FileNotFoundError(
            i18n.translate("trevor.apply.prop_dummy_missing", path=prop_dummy_ydd_path)
        )
    if not os.path.exists(miltina_model_ydd_path):
        raise FileNotFoundError(
            i18n.translate("trevor.apply.model_missing", path=miltina_model_ydd_path)
        )
    if not os.path.exists(miltina_texture_ytd_path):
        raise FileNotFoundError(
            i18n.translate("trevor.apply.ytd_missing", path=miltina_texture_ytd_path)
        )

    project_paths.ensure_streamedpedprops_extracted()
    patch_directory(
        mppatches_p2_dir,
        miltina_model_ydd_path,
        miltina_texture_ytd_path,
        dummy_ydd_path,
        is_mppatches=True,
    )
    patch_directory(
        streamedpeds_p2_dir,
        miltina_model_ydd_path,
        miltina_texture_ytd_path,
        dummy_ydd_path,
        is_mppatches=False,
    )
    if os.path.isdir(patchday4_p2_dir):
        patch_directory(
            patchday4_p2_dir,
            miltina_model_ydd_path,
            miltina_texture_ytd_path,
            dummy_ydd_path,
            is_mppatches=False,
        )
    project_paths.patch_character_glasses_props(
        streamedprops_p2_dir, prop_dummy_ydd_path, "player_two_p"
    )
    print(i18n.translate("trevor.apply.done"))


def main() -> int:
    """CLI entry point for patching Trevor slots with Miltina Maid."""
    resolve_startup_language()
    parser = argparse.ArgumentParser(description=i18n.translate("trevor.apply.cli_desc"))
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

    apply_miltina_slots()
    return 0


if __name__ == "__main__":
    sys.exit(main())
