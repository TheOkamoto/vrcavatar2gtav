#!/usr/bin/env python3
"""
test_suite_core_layer.py
========================
Layer 1 of 4 for automated project validation (`test_mod_suite`).

Contains shared test helpers and core suites: syntax compilation, paths,
dummy integrity, compiled drawables/textures, RPF headers, i18n catalog,
extended Python/C++ AST & modularity quality gates, and source templates. for verifying all Python scripts, trilingual
translation catalogs, path resolution, compiled assets (.ydd, .ytd), dummy
meshes, deployed RPF headers, code quality rules, and mirror synchronization.
"""

import argparse
import ast
import filecmp
import io as io_stream
import os
import py_compile
import re as regex_module
import string
import struct
import sys
import tarfile
import tempfile
import zipfile
import zlib
from pathlib import Path
from typing import Any, List, Sequence, Tuple

CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT_DIR = (
    CURRENT_SCRIPT_DIR.parent
    if CURRENT_SCRIPT_DIR.name == "_deploy_tools"
    else CURRENT_SCRIPT_DIR.parent.parent
)
sys.path.insert(0, str(PROJECT_ROOT_DIR / "_deploy_tools"))
sys.path.insert(0, str(CURRENT_SCRIPT_DIR))

try:
    import vrc2gtav_i18n as i18n
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import vrc2gtav_i18n as i18n
    from common_tools import vrc2gtav_paths as project_paths


def resolve_startup_language() -> None:
    """Resolve UI language from CLI arguments, environment variables, or config."""
    configured_language = None
    try:
        configured_language = project_paths.get_configured_language()
    except FileNotFoundError:
        configured_language = None
    i18n.set_active_language(configured_language, cli_args=sys.argv[1:])


def print_status_result(
    test_label: str, success_condition: bool, detail_message: str = ""
) -> bool:
    """Print an ASCII-tagged pass/fail line using the active UI language."""
    status_tag = i18n.translate(
        "tests.status_pass" if success_condition else "tests.status_fail"
    )
    detail_suffix = f" - {detail_message}" if detail_message else ""
    print(f"  {status_tag} {test_label}{detail_suffix}")
    return success_condition


_PRUNED_WALK_DIRS = frozenset(
    {
        "staging",
        ".git",
        "__pycache__",
        ".venv",
        "tools",
        "imported_unity_projects",
        "logs",
        "extracted_rpfs",
        "backups",
        "npcs",
    }
)


def _iter_project_python_files(scan_root: Path) -> List[Path]:
    """Walk `scan_root` pruning large binary/cache/tool subtrees up front."""
    found_files: List[Path] = []
    for cur_root, dir_names, file_names in os.walk(scan_root):
        dir_names[:] = sorted(
            sub_dir for sub_dir in dir_names if sub_dir not in _PRUNED_WALK_DIRS
        )
        for file_name in sorted(file_names):
            if file_name.endswith(".py"):
                found_files.append(Path(cur_root) / file_name)
    return found_files


def test_python_syntax_compilation() -> bool:
    """Compile every tracked Python file to verify valid syntax."""
    print(i18n.translate("tests.sec1_title"))
    all_compiled_cleanly = True
    python_files_found = _iter_project_python_files(PROJECT_ROOT_DIR)

    for python_file_path in python_files_found:
        try:
            py_compile.compile(str(python_file_path), doraise=True)
            print_status_result(
                python_file_path.name,
                True,
                str(python_file_path.relative_to(PROJECT_ROOT_DIR)),
            )
        except py_compile.PyCompileError as compile_error:
            print_status_result(python_file_path.name, False, str(compile_error))
            all_compiled_cleanly = False

    return all_compiled_cleanly


def test_path_resolution() -> bool:
    """Verify dynamic path resolution from vrc2gtav.cfg."""
    print(i18n.translate("tests.sec2_title"))
    resolution_success = True

    try:
        config_file_path = project_paths.find_project_config_file()
        resolution_success &= print_status_result(
            i18n.translate("tests.cfg_central"),
            config_file_path.exists(),
            str(config_file_path),
        )
    except Exception as config_error:
        resolution_success &= print_status_result(
            i18n.translate("tests.cfg_central"), False, str(config_error)
        )

    resolved_root = project_paths.get_project_root()
    resolution_success &= print_status_result(
        i18n.translate("tests.project_root"), resolved_root.exists(), str(resolved_root)
    )

    staging_directory = project_paths.get_staging_dir()
    resolution_success &= print_status_result(
        i18n.translate("tests.staging_dir"),
        staging_directory.exists(),
        str(staging_directory),
    )

    blender_executable = project_paths.get_blender_exe()
    resolution_success &= print_status_result(
        i18n.translate("tests.blender_exe"),
        Path(blender_executable).exists() or bool(blender_executable),
        str(blender_executable),
    )

    python_executable = project_paths.get_python_exe()
    resolution_success &= print_status_result(
        i18n.translate("tests.python_exe"),
        Path(python_executable).exists(),
        str(python_executable),
    )

    rage_cli_tool = project_paths.get_rage_cli()
    resolution_success &= print_status_result(
        i18n.translate("tests.rage_cli"),
        Path(rage_cli_tool).exists(),
        str(rage_cli_tool),
    )

    unity_assets_directory = project_paths.get_vrc_assets_dir()
    resolution_success &= print_status_result(
        i18n.translate("tests.unity_assets"),
        unity_assets_directory.exists(),
        str(unity_assets_directory),
    )

    return resolution_success


def test_dummy_mesh_integrity() -> bool:
    """Verify byte sizes of the universal ped and prop dummy meshes."""
    print(i18n.translate("tests.sec3_title"))
    dummy_mesh_file = project_paths.get_dummy_ydd_path()
    prop_dummy_file = project_paths.get_prop_dummy_ydd_path()

    if not dummy_mesh_file.exists():
        head_dummy_ok = print_status_result(
            "head_000_r.ydd", False, i18n.translate("tests.file_not_found")
        )
    else:
        file_size_bytes = dummy_mesh_file.stat().st_size
        head_dummy_ok = print_status_result(
            "head_000_r.ydd",
            file_size_bytes == 629,
            i18n.translate("tests.byte_size", actual=file_size_bytes, expected=629),
        )

    if not prop_dummy_file.exists():
        prop_dummy_ok = print_status_result(
            "p_eyes_dummy.ydd", False, i18n.translate("tests.file_not_found")
        )
    else:
        prop_size_bytes = prop_dummy_file.stat().st_size
        prop_dummy_ok = print_status_result(
            "p_eyes_dummy.ydd",
            prop_size_bytes == 515,
            i18n.translate("tests.byte_size", actual=prop_size_bytes, expected=515),
        )

    return head_dummy_ok and prop_dummy_ok


def test_compiled_drawables_and_textures() -> bool:
    """Verify all compiled .ydd, .yft, and .ytd assets exist for each character."""
    print(i18n.translate("tests.sec4_title"))
    all_assets_present = True

    franklin_cfg = project_paths.get_character_paths("franklin")
    michael_cfg = project_paths.get_character_paths("michael")
    trevor_cfg = project_paths.get_character_paths("trevor")

    expected_assets_list = [
        franklin_cfg["target_model_ydd"],
        franklin_cfg["target_yft"],
        franklin_cfg["ytd_file"],
        michael_cfg["target_model_ydd"],
        michael_cfg["extra_model_ydds"][0],
        michael_cfg["target_yft"],
        michael_cfg["ytd_file"],
        trevor_cfg["target_model_ydd"],
        trevor_cfg["extra_model_ydds"][0],
        trevor_cfg["target_yft"],
        trevor_cfg["ytd_file"],
    ]

    import ped_damage_helper

    for asset_file_path in expected_assets_list:
        file_exists = asset_file_path.exists()
        file_size_bytes = asset_file_path.stat().st_size if file_exists else 0
        file_size_mb = file_size_bytes / (1024 * 1024)
        within_rpf7_cap = False
        if file_exists:
            try:
                ped_damage_helper.validate_rpf7_resource_file(asset_file_path)
                within_rpf7_cap = True
            except ValueError:
                within_rpf7_cap = False
        all_assets_present &= print_status_result(
            asset_file_path.name,
            file_exists and within_rpf7_cap,
            i18n.translate(
                "tests.asset_detail",
                size=file_size_mb,
                parent=asset_file_path.parent.name,
            ),
        )

    staging_root_dir = project_paths.get_staging_dir()
    npc_yft_paths = [
        PROJECT_ROOT_DIR / "npcs" / "ig_lamardavis" / "5_rpf_package" / "ig_lamardavis.yft",
        PROJECT_ROOT_DIR / "npcs" / "cs_lamardavis" / "5_rpf_package" / "cs_lamardavis.yft",
        staging_root_dir / "npcs_rpf" / "streamedpeds_ig_extracted" / "ig_lamardavis.yft",
        staging_root_dir / "npcs_rpf" / "cutspeds_extracted" / "cs_lamardavis.yft",
    ]
    for npc_yft_candidate in npc_yft_paths:
        if npc_yft_candidate.is_file():
            yft_bounds_ok = True
            try:
                ped_damage_helper.validate_yft_rsc7_page_bounds(npc_yft_candidate)
            except ValueError:
                yft_bounds_ok = False
            all_assets_present &= print_status_result(
                f"{npc_yft_candidate.parent.name}/{npc_yft_candidate.name}",
                yft_bounds_ok,
                "RSC7 virtual pages & m_SharedMatrixSet bounds",
            )

    import configparser

    gtav_root_dir = project_paths.get_gtav_root_dir()
    physbones_asi_path = gtav_root_dir / "GTAVPhysBones.asi"
    physbones_ini_path = gtav_root_dir / "GTAVPhysBones.ini"
    asi_exists = physbones_asi_path.is_file()
    ini_exists = physbones_ini_path.is_file()
    ear_chains_count = 0
    shinano_chains_count = 0
    miltina_chains_count = 0
    ini_total_chains = 0
    ini_blink_count = 0
    blink_models_found = set()
    blink_max_by_model = {}
    blink_rot_valid_by_model = {}
    if ini_exists:
        ini_parser = configparser.ConfigParser()
        ini_parser.read(str(physbones_ini_path), encoding="utf-8")
        ini_total_chains = ini_parser.getint("General", "chain_count", fallback=0)
        ini_blink_count = ini_parser.getint("General", "blink_count", fallback=0)
        for section_name in ini_parser.sections():
            if section_name.startswith("Blink_"):
                blink_model = ini_parser.get(section_name, "model", fallback="").strip().lower()
                blink_enabled = ini_parser.getint(section_name, "enabled", fallback=0)
                blink_bones = ini_parser.getint(section_name, "bone_count", fallback=0)
                blink_max_val = ini_parser.getfloat(section_name, "max_blink", fallback=1.0)
                has_non_identity_rot = False
                for bone_idx in range(blink_bones):
                    raw_drot = ini_parser.get(section_name, f"bone_{bone_idx}_delta_rot", fallback="")
                    parts = [float(item.strip()) for item in raw_drot.split(",") if item.strip()]
                    if len(parts) == 4 and (parts[0] ** 2 + parts[1] ** 2 + parts[2] ** 2) > 1e-4:
                        has_non_identity_rot = True
                if blink_enabled == 1 and blink_bones == 4 and blink_model:
                    blink_models_found.add(blink_model)
                    blink_max_by_model[blink_model] = blink_max_val
                    blink_rot_valid_by_model[blink_model] = has_non_identity_rot
                continue
            if not section_name.startswith("Chain_"):
                continue
            chain_name = ini_parser.get(section_name, "name", fallback="")
            if chain_name.startswith(("PB_Ear_", "PB_ER_")):
                ear_chains_count += 1
            elif chain_name.startswith("PB_SC_"):
                shinano_chains_count += 1
            elif chain_name.startswith("PB_MT_"):
                miltina_chains_count += 1

    blink_ydd_bones_ok = True
    for xml_rel_path in (
        "1_Franklin_Shinano_Casual/4_exported_models/uppr_008_u.ydd.xml",
        "1_Franklin_Shinano_Casual/4_exported_models/uppr_000_u.ydd.xml",
        "2_Michael_Shinano_EternalReunion/4_exported_models/uppr_000_u.ydd.xml",
        "3_Trevor_Miltina_Maid/4_exported_models/uppr_000_u.ydd.xml",
    ):
        xml_file = PROJECT_ROOT_DIR / xml_rel_path
        if xml_file.is_file():
            xml_text = xml_file.read_text(encoding="utf-8", errors="ignore")
            if (
                "PB_Blink_L" not in xml_text
                or "PB_Blink_R" not in xml_text
            ):
                blink_ydd_bones_ok = False

    blink_peaks_ok = (
        abs(blink_max_by_model.get("player_zero", 1.0) - 0.5) < 0.02
        and abs(blink_max_by_model.get("player_one", 1.0) - 0.5) < 0.02
        and abs(blink_max_by_model.get("player_two", 1.0) - 0.6) < 0.02
    )
    blink_rot_modes_ok = (
        blink_rot_valid_by_model.get("player_zero", False)
        and blink_rot_valid_by_model.get("player_one", False)
        and blink_rot_valid_by_model.get("player_two", False)
    )
    physbones_runtime_ok = (
        asi_exists
        and ini_exists
        and ini_total_chains >= 79
        and ear_chains_count == 30
        and shinano_chains_count == 24
        and miltina_chains_count == 25
        and ini_blink_count >= 3
        and {"player_zero", "player_one", "player_two"}.issubset(blink_models_found)
        and blink_peaks_ok
        and blink_rot_modes_ok
        and blink_ydd_bones_ok
    )
    all_assets_present &= print_status_result(
        "GTAVPhysBones.asi / .ini",
        physbones_runtime_ok,
        (
            f"asi={asi_exists}, chains={ini_total_chains} "
            f"(Michael={ear_chains_count}, Franklin={shinano_chains_count}, Trevor={miltina_chains_count}), "
            f"blinks={ini_blink_count} {sorted(blink_models_found)} "
            f"max=({blink_max_by_model.get('player_zero', -1.0):.2f}/"
            f"{blink_max_by_model.get('player_one', -1.0):.2f}/"
            f"{blink_max_by_model.get('player_two', -1.0):.2f})"
        ),
    )

    return all_assets_present


def test_deployed_rpf_encryption_headers() -> bool:
    """Verify OPEN headers in deployed GTA V RPFs and staged dummy/skeleton parity."""
    print(i18n.translate("tests.sec5_title"))
    mods_directory = project_paths.get_gtav_mods_dir()
    if not mods_directory.exists():
        print(i18n.translate("tests.mods_inaccessible"))
        return True

    all_rpfs_valid = True
    rpf_paths_cfg = project_paths.get_rpf_paths()
    rpf_paths_to_check = [
        rpf_paths_cfg["mppatches_game_rpf"],
        rpf_paths_cfg["patchday3ng_game_rpf"],
        rpf_paths_cfg["patchday4ng_game_rpf"],
        rpf_paths_cfg["x64v_game_rpf"],
    ]

    for rpf_file_path in rpf_paths_to_check:
        if not rpf_file_path.exists():
            continue
        try:
            with open(rpf_file_path, "rb") as rpf_handle:
                header_data = rpf_handle.read(16)
                _magic_number, entry_count, _names_size, encryption_flag = struct.unpack(
                    "<IIII", header_data
                )
                encryption_bytes = struct.pack("<I", encryption_flag)
                has_open_encryption = encryption_bytes == b"OPEN"
                all_rpfs_valid &= print_status_result(
                    f"{rpf_file_path.parent.name}/{rpf_file_path.name}",
                    has_open_encryption,
                    f"enc={encryption_bytes} entries={entry_count}",
                )
        except Exception as read_error:
            all_rpfs_valid &= print_status_result(rpf_file_path.name, False, str(read_error))

    import ped_damage_helper

    repacked_archives = [
        rpf_paths_cfg["mppatches_dlc_extracted"] / rpf_paths_cfg["mppatches_rpf_relative"],
        rpf_paths_cfg["mppatches_game_rpf"],
        rpf_paths_cfg["x64v_extracted"] / rpf_paths_cfg["streamedpeds_rpf_relative"],
        rpf_paths_cfg["x64v_extracted"] / rpf_paths_cfg["streamedpedprops_rpf_relative"],
        rpf_paths_cfg["x64v_game_rpf"],
    ]
    for optional_rpf_path in (
        rpf_paths_cfg.get("patchday3ng_game_rpf"),
        (
            rpf_paths_cfg["patchday3ng_dlc_extracted"]
            / rpf_paths_cfg["patchday3ng_rpf_relative"]
            if "patchday3ng_dlc_extracted" in rpf_paths_cfg
            and "patchday3ng_rpf_relative" in rpf_paths_cfg
            else None
        ),
        (
            PROJECT_ROOT_DIR
            / "1_Franklin_Shinano_Casual"
            / "5_rpf_package"
            / "patchday3_work"
            / "patchday3ng_extracted"
            / "x64"
            / "models"
            / "cdimages"
            / "patchday3ng.rpf"
        ),
        (
            rpf_paths_cfg["patchday4ng_dlc_extracted"]
            / rpf_paths_cfg["patchday4ng_rpf_relative"]
        ),
        rpf_paths_cfg.get("patchday4ng_game_rpf"),
    ):
        if optional_rpf_path is not None and optional_rpf_path.is_file():
            repacked_archives.append(optional_rpf_path)

    rpf7_bounds_ok = True
    max_observed_res = 0
    for audit_path in repacked_archives:
        if not audit_path.is_file():
            continue
        report = ped_damage_helper.inspect_rpf7_archive_limits(audit_path)
        max_observed_res = max(max_observed_res, int(report["largest_resource_bytes"]))
        if not report["ok"]:
            rpf7_bounds_ok = False
    all_rpfs_valid &= print_status_result(
        i18n.translate("tests.rpf7_16mb_safeguards"),
        rpf7_bounds_ok,
        f"largest_rsc7={max_observed_res / (1024 * 1024):.2f} MiB <= 16.00 MiB",
    )

    props_extracted_dir = rpf_paths_cfg["streamedpedprops_extracted"]
    prop_dummy_file = project_paths.get_prop_dummy_ydd_path()
    if props_extracted_dir.is_dir() and prop_dummy_file.exists():
        total_glasses_checked = 0
        mismatched_glasses = []
        for character_section in ("michael", "franklin", "trevor"):
            character_cfg = project_paths.get_character_paths(character_section)
            character_props_dir = Path(character_cfg["staging_streamed_props_dir"])
            if not character_props_dir.is_dir():
                mismatched_glasses.append(
                    i18n.translate("tests.missing_folder", character=character_section)
                )
                continue
            glasses_files = sorted(character_props_dir.glob("p_eyes_*.ydd"))
            if not glasses_files:
                mismatched_glasses.append(
                    i18n.translate("tests.no_glasses", character=character_section)
                )
                continue
            for glasses_path in glasses_files:
                total_glasses_checked += 1
                if not filecmp.cmp(glasses_path, prop_dummy_file, shallow=False):
                    mismatched_glasses.append(
                        f"{character_props_dir.name}/{glasses_path.name}"
                    )

        all_rpfs_valid &= print_status_result(
            i18n.translate("tests.glasses_label"),
            len(mismatched_glasses) == 0 and total_glasses_checked == 35,
            i18n.translate("tests.glasses_ok", count=total_glasses_checked)
            if not mismatched_glasses
            else i18n.translate("tests.mismatches", items=mismatched_glasses[:5]),
        )

    streamedpeds_extracted_dir = rpf_paths_cfg["streamedpeds_extracted"]
    if streamedpeds_extracted_dir.is_dir():
        mismatched_yft_files = []
        for character_section in ("michael", "franklin", "trevor"):
            character_cfg = project_paths.get_character_paths(character_section)
            ped_name = str(character_cfg["ped_name"])
            compiled_yft = Path(character_cfg["target_yft"])
            staged_yft = streamedpeds_extracted_dir / f"{ped_name}.yft"
            if not compiled_yft.exists() or not staged_yft.exists():
                mismatched_yft_files.append(
                    i18n.translate("tests.yft_missing", name=f"{ped_name}.yft")
                )
            elif not filecmp.cmp(compiled_yft, staged_yft, shallow=False):
                mismatched_yft_files.append(
                    i18n.translate("tests.yft_stale", name=f"{ped_name}.yft")
                )

        all_rpfs_valid &= print_status_result(
            i18n.translate("tests.yft_label"),
            len(mismatched_yft_files) == 0,
            i18n.translate("tests.yft_ok")
            if not mismatched_yft_files
            else i18n.translate("tests.mismatches", items=mismatched_yft_files),
        )

    return all_rpfs_valid


def extract_placeholder_fields(template_text: str) -> tuple:
    """Return sorted format field names referenced inside a translation string."""
    formatter = string.Formatter()
    fields = []
    for _literal_text, field_name, _format_spec, _conversion in formatter.parse(template_text):
        if field_name is not None:
            fields.append(field_name)
    return tuple(sorted(fields))


def test_i18n_catalog_integrity() -> bool:
    """Validate that every i18n message key provides non-empty matching en/ja/pt text."""
    print(i18n.translate("tests.sec_i18n_title"))
    catalog_issues = []
    required_languages = tuple(i18n.SUPPORTED_LANGUAGES)

    for message_key, translations in i18n.MESSAGES.items():
        missing_langs = [lang for lang in required_languages if lang not in translations]
        if missing_langs:
            catalog_issues.append(f"{message_key}: missing {missing_langs}")
            continue

        placeholder_sets = {}
        for lang_code in required_languages:
            text_value = translations[lang_code]
            if not isinstance(text_value, str) or not text_value.strip():
                catalog_issues.append(f"{message_key}[{lang_code}]: empty translation")
                continue
            placeholder_sets[lang_code] = extract_placeholder_fields(text_value)

        if len(set(placeholder_sets.values())) > 1:
            catalog_issues.append(
                f"{message_key}: placeholder mismatch {placeholder_sets}"
            )

    helper_checks_ok = (
        i18n.normalize_language_code("pt_BR.UTF-8") == "pt"
        and i18n.normalize_language_code("ja-JP") == "ja"
        and i18n.normalize_language_code("en_US.UTF-8") == "en"
        and i18n.is_affirmative_answer("sim")
        and i18n.is_affirmative_answer("yes")
        and i18n.is_affirmative_answer("はい")
        and not i18n.is_affirmative_answer("não")
        and not i18n.is_affirmative_answer("no")
        and not i18n.is_affirmative_answer("いいえ")
    )
    if not helper_checks_ok:
        catalog_issues.append("Language normalization or affirmative parser check failed")

    translation_func_names = {"translate", "translate_message", "get_text"}
    for python_file in _iter_project_python_files(PROJECT_ROOT_DIR):
        parsed_tree = ast.parse(
            python_file.read_text(encoding="utf-8"), filename=str(python_file)
        )
        for ast_node in ast.walk(parsed_tree):
            if isinstance(ast_node, ast.Call) and ast_node.args:
                callee = ast_node.func
                callee_name = (
                    callee.attr
                    if isinstance(callee, ast.Attribute)
                    else (callee.id if isinstance(callee, ast.Name) else None)
                )
                first_arg = ast_node.args[0]
                if (
                    callee_name in translation_func_names
                    and isinstance(first_arg, ast.Constant)
                    and isinstance(first_arg.value, str)
                    and first_arg.value not in i18n.MESSAGES
                ):
                    catalog_issues.append(
                        f"{python_file.name}:{ast_node.lineno} unknown key {first_arg.value}"
                    )

    catalog_ok = len(catalog_issues) == 0
    return print_status_result(
        i18n.translate("tests.i18n_catalog_label"),
        catalog_ok,
        i18n.translate(
            "tests.i18n_catalog_ok",
            count=len(i18n.MESSAGES),
            langs="/".join(required_languages),
        )
        if catalog_ok
        else i18n.translate(
            "tests.i18n_issues", total=len(catalog_issues), sample=catalog_issues[:5]
        ),
    )


def test_code_quality_and_mirror_sync() -> bool:
    """Verify zero emojis, >=3-char AST identifiers, and byte-identical mirrors."""
    print(i18n.translate("tests.sec6_title"))
    quality_passed = True
    emoji_pattern = regex_module.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")
    allowed_stdlib_short_names = {"_", "os", "re"}

    root_dir = (
        project_paths.get_project_root()
        if project_paths.has_project_config_file()
        else PROJECT_ROOT_DIR
    )
    total_python_files = 0
    for python_file in _iter_project_python_files(root_dir):
        total_python_files += 1
        file_content = python_file.read_text(encoding="utf-8", errors="ignore")
        if emoji_pattern.search(file_content):
            quality_passed &= print_status_result(
                i18n.translate("tests.no_emojis", name=python_file.name),
                False,
                str(python_file),
            )

        syntax_tree = ast.parse(file_content, filename=str(python_file))
        if len(file_content.splitlines()) > 1600 or not ast.get_docstring(syntax_tree):
            quality_passed &= print_status_result(
                f"Python modularity/docstring limit ({python_file.relative_to(root_dir)})",
                False,
                f"lines={len(file_content.splitlines())}, has_doc={bool(ast.get_docstring(syntax_tree))}",
            )

        invalid_short_names = sorted(
            {
                node.id
                for node in ast.walk(syntax_tree)
                if isinstance(node, ast.Name)
                and len(node.id) <= 2
                and node.id not in allowed_stdlib_short_names
            }
            | {
                node.arg
                for node in ast.walk(syntax_tree)
                if isinstance(node, ast.arg) and len(node.arg) <= 2
            }
            | {
                node.name
                for node in ast.walk(syntax_tree)
                if isinstance(node, ast.ExceptHandler)
                and node.name
                and len(node.name) <= 2
                and node.name not in allowed_stdlib_short_names
            }
            | {
                node.asname
                for node in ast.walk(syntax_tree)
                if isinstance(node, ast.alias)
                and node.asname
                and len(node.asname) <= 2
                and node.asname not in allowed_stdlib_short_names
            }
            | {
                node.name
                for node in ast.walk(syntax_tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and len(node.name) <= 2
                and node.name not in allowed_stdlib_short_names
            }
        )
        if invalid_short_names:
            quality_passed &= print_status_result(
                i18n.translate(
                    "tests.vars_min_len", path=python_file.relative_to(root_dir)
                ),
                False,
                i18n.translate("tests.found_short_vars", items=invalid_short_names),
            )

    quality_passed &= print_status_result(
        i18n.translate("tests.ast_emoji_scan"),
        quality_passed,
        i18n.translate("tests.ast_emoji_detail", count=total_python_files),
    )

    cpp_dir = root_dir / "scripts" / "physbones_asi"
    cpp_keywords = {"if", "do", "in", "or"}
    cpp_files_checked = 0
    cpp_quality_ok = True
    if cpp_dir.is_dir():
        for cpp_file in sorted(cpp_dir.iterdir()):
            if cpp_file.suffix not in {".cpp", ".hpp", ".h"}:
                continue
            cpp_files_checked += 1
            cpp_text = cpp_file.read_text(encoding="utf-8", errors="replace")
            cpp_lines = cpp_text.splitlines()
            has_header_comment = any(
                line_txt.strip().startswith(("/*", "//")) for line_txt in cpp_lines[:10]
            )
            if len(cpp_lines) > 800 or not has_header_comment:
                cpp_quality_ok &= print_status_result(
                    f"C++ modularity/header ({cpp_file.name})",
                    False,
                    f"lines={len(cpp_lines)}, has_comment={has_header_comment}",
                )
            stripped_cpp = regex_module.sub(r"/\*.*?\*/", " ", cpp_text, flags=regex_module.S)
            stripped_cpp = regex_module.sub(r"//.*?$", " ", stripped_cpp, flags=regex_module.M)
            stripped_cpp = regex_module.sub(r"^\s*#.*$", " ", stripped_cpp, flags=regex_module.M)
            stripped_cpp = regex_module.sub(r"\"(?:\\.|[^\"\\])*\"|\x27(?:\\.|[^\x27\\])*\x27", " ", stripped_cpp)
            stripped_cpp = regex_module.sub(
                r"\b0[xX][0-9A-Fa-f]+[uUlL]*\b|\b\d+(?:\.\d*)?(?:[eE][+-]?\d+)?[fFlLuU]*\b",
                " ",
                stripped_cpp,
            )
            short_cpp_ids = sorted(
                {
                    tok
                    for tok in regex_module.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", stripped_cpp)
                    if len(tok) <= 2 and tok not in cpp_keywords
                }
            )
            if short_cpp_ids:
                cpp_quality_ok &= print_status_result(
                    f"C++ identifiers >= 3 chars ({cpp_file.name})",
                    False,
                    f"short={short_cpp_ids[:10]}",
                )
    quality_passed &= print_status_result(
        "C++ modularity (<=800 lines), comments & >=3-char identifiers",
        cpp_quality_ok and cpp_files_checked > 0,
        f"files={cpp_files_checked}",
    )

    if project_paths.has_project_config_file():
        scripts_dir = project_paths.get_scripts_root_dir()
        deploy_dir = project_paths.get_deploy_tools_dir()
        common_dir = project_paths.get_common_tools_dir()
        franklin_dir = project_paths.get_avatar_paths("shinano_casual")["character_dir"]
        michael_dir = project_paths.get_avatar_paths("shinano_er")["character_dir"]
        trevor_dir = project_paths.get_avatar_paths("miltina_maid")["character_dir"]
    else:
        scripts_dir = root_dir / "scripts"
        deploy_dir = root_dir / "_deploy_tools"
        common_dir = scripts_dir / "common_tools"
        franklin_dir = root_dir / "1_Franklin_Shinano_Casual"
        michael_dir = root_dir / "2_Michael_Shinano_EternalReunion"
        trevor_dir = root_dir / "3_Trevor_Miltina_Maid"

    mirror_pairs = [
        (common_dir / "i18n_catalog_core_layer.py", deploy_dir / "i18n_catalog_core_layer.py"),
        (common_dir / "i18n_catalog_builders_layer.py", deploy_dir / "i18n_catalog_builders_layer.py"),
        (common_dir / "i18n_catalog_tests_physbones_layer.py", deploy_dir / "i18n_catalog_tests_physbones_layer.py"),
        (common_dir / "vrc2gtav_i18n.py", deploy_dir / "vrc2gtav_i18n.py"),
        (common_dir / "physbone_presets_layer.py", deploy_dir / "physbone_presets_layer.py"),
        (common_dir / "physbone_cfg_ini_layer.py", deploy_dir / "physbone_cfg_ini_layer.py"),
        (common_dir / "physbone_unity_fbx_layer.py", deploy_dir / "physbone_unity_fbx_layer.py"),
        (common_dir / "physbone_scene_extractor_layer.py", deploy_dir / "physbone_scene_extractor_layer.py"),
        (common_dir / "unity_hair_bake_layer.py", deploy_dir / "unity_hair_bake_layer.py"),
        (common_dir / "michael_er_geometry_layer.py", deploy_dir / "michael_er_geometry_layer.py"),
        (common_dir / "blendshape_unity_yaml_layer.py", deploy_dir / "blendshape_unity_yaml_layer.py"),
        (common_dir / "mod_manager_interactive_layer.py", deploy_dir / "mod_manager_interactive_layer.py"),
        (common_dir / "modular_avatar_yaml_layer.py", deploy_dir / "modular_avatar_yaml_layer.py"),
        (common_dir / "universal_gtav_rigging_layer.py", deploy_dir / "universal_gtav_rigging_layer.py"),
        (common_dir / "test_suite_core_layer.py", deploy_dir / "test_suite_core_layer.py"),
        (common_dir / "test_suite_unity_physbones_layer.py", deploy_dir / "test_suite_unity_physbones_layer.py"),
        (common_dir / "test_suite_extensions_layer.py", deploy_dir / "test_suite_extensions_layer.py"),
        (common_dir / "test_mod_suite.py", deploy_dir / "test_mod_suite.py"),
        (common_dir / "vrc2gtav_paths.py", deploy_dir / "vrc2gtav_paths.py"),
        (common_dir / "error_handler_helper.py", deploy_dir / "error_handler_helper.py"),
        (common_dir / "avatar_archive_helper.py", deploy_dir / "avatar_archive_helper.py"),
        (common_dir / "modular_avatar_helper.py", deploy_dir / "modular_avatar_helper.py"),
        (common_dir / "build_universal_avatar.py", deploy_dir / "build_universal_avatar.py"),
        (common_dir / "npc_registry_helper.py", deploy_dir / "npc_registry_helper.py"),
        (common_dir / "universal_atlas_builder.py", deploy_dir / "universal_atlas_builder.py"),
        (common_dir / "universal_gtav_builder.py", deploy_dir / "universal_gtav_builder.py"),
        (common_dir / "setup_first_run.py", deploy_dir / "setup_first_run.py"),
        (common_dir / "setup_first_run.py", root_dir / "setup_first_run.py"),
        (common_dir / "hand_skeleton_helper.py", deploy_dir / "hand_skeleton_helper.py"),
        (common_dir / "eye_blink_helper.py", deploy_dir / "eye_blink_helper.py"),
        (common_dir / "physbone_helper.py", deploy_dir / "physbone_helper.py"),
        (common_dir / "ped_damage_helper.py", deploy_dir / "ped_damage_helper.py"),
        (common_dir / "unity_scene_helper.py", deploy_dir / "unity_scene_helper.py"),
        (common_dir / "unity_hair_helper.py", deploy_dir / "unity_hair_helper.py"),
        (common_dir / "blender_hair_helper.py", deploy_dir / "blender_hair_helper.py"),
        (common_dir / "blendshape_helper.py", deploy_dir / "blendshape_helper.py"),
        (
            common_dir / "texture_calibration_helper.py",
            deploy_dir / "texture_calibration_helper.py",
        ),
        (common_dir / "apply_characters.py", deploy_dir / "apply_characters.py"),
        (common_dir / "apply_all_characters.py", deploy_dir / "apply_all_characters.py"),
        (
            common_dir / "repack_and_deploy_everything.py",
            deploy_dir / "repack_and_deploy_everything.py",
        ),
        (common_dir / "run_mod_manager.py", deploy_dir / "run_mod_manager.py"),
        (common_dir / "run_mod_manager.py", root_dir / "run_mod_manager.py"),
        (
            scripts_dir / "Shinano_Casual_Franklin" / "build_franklin_avatar.py",
            franklin_dir / "2_blender" / "build_franklin_avatar.py",
        ),
        (
            scripts_dir / "Shinano_Casual_Franklin" / "run_build_franklin.py",
            franklin_dir / "2_blender" / "run_build.py",
        ),
        (
            scripts_dir / "Shinano_Casual_Franklin" / "generate_franklin_atlas.py",
            franklin_dir / "3_textures_gtav" / "generate_franklin_atlas.py",
        ),
        (
            scripts_dir / "Shinano_EternalReunion_Michael" / "build_michael_er.py",
            michael_dir / "2_blender" / "build_michael_er.py",
        ),
        (
            scripts_dir / "Shinano_EternalReunion_Michael" / "run_build_er.py",
            michael_dir / "2_blender" / "run_build.py",
        ),
        (
            scripts_dir / "Shinano_EternalReunion_Michael" / "generate_er_atlas.py",
            michael_dir / "3_textures_gtav" / "generate_er_atlas.py",
        ),
        (
            scripts_dir / "Shinano_EternalReunion_Michael" / "deploy_michael_er.py",
            michael_dir / "5_rpf_package" / "deploy_michael_er.py",
        ),
        (
            scripts_dir / "Miltina_Maid_Trevor" / "build_trevor_miltina.py",
            trevor_dir / "2_blender" / "build_trevor_miltina.py",
        ),
        (
            scripts_dir / "Miltina_Maid_Trevor" / "run_pipeline.py",
            trevor_dir / "2_blender" / "run_pipeline.py",
        ),
        (
            scripts_dir / "Miltina_Maid_Trevor" / "generate_miltina_atlas.py",
            trevor_dir / "3_textures_gtav" / "generate_miltina_atlas.py",
        ),
        (
            scripts_dir / "Miltina_Maid_Trevor" / "apply_miltina_to_trevor.py",
            trevor_dir / "5_rpf_package" / "apply_miltina_to_trevor.py",
        ),
    ]

    mirrors_in_sync = True
    for primary_file, mirror_file in mirror_pairs:
        is_synced = (
            primary_file.exists()
            and mirror_file.exists()
            and filecmp.cmp(primary_file, mirror_file, shallow=False)
        )
        if not is_synced:
            mirrors_in_sync &= print_status_result(
                i18n.translate(
                    "tests.mirror_desync", mirror=mirror_file.relative_to(root_dir)
                ),
                False,
                i18n.translate(
                    "tests.must_match", primary=primary_file.relative_to(root_dir)
                ),
            )

    quality_passed &= print_status_result(
        i18n.translate("tests.mirror_sync_label"),
        mirrors_in_sync,
        i18n.translate("tests.mirror_sync_detail", count=len(mirror_pairs)),
    )
    return quality_passed


def test_source_templates_and_dummies() -> bool:
    """Validate vrc2gtav.cfg.example, .gitignore, and technical dummies offline."""
    print(i18n.translate("tests.sec_template_title"))
    cfg_example_path = project_paths.find_project_config_example()
    gitignore_path = PROJECT_ROOT_DIR / ".gitignore"
    dummy_head_path = PROJECT_ROOT_DIR / "_deploy_tools" / "head_000_r.ydd"
    dummy_eyes_path = PROJECT_ROOT_DIR / "_deploy_tools" / "p_eyes_dummy.ydd"

    template_ok = print_status_result(
        "vrc2gtav.cfg.example", cfg_example_path.is_file(), str(cfg_example_path.name)
    )
    gitignore_ok = False
    if gitignore_path.is_file():
        gitignore_text = gitignore_path.read_text(encoding="utf-8")
        gitignore_ok = (
            "*.yft" in gitignore_text
            and "*.ydd" in gitignore_text
            and "vrc2gtav.cfg" in gitignore_text
        )
    gitignore_check = print_status_result(
        i18n.translate("tests.gitignore_rules"),
        gitignore_ok,
        i18n.translate("tests.gitignore_detail"),
    )
    dummies_ok = print_status_result(
        i18n.translate("tests.dummies_label"),
        dummy_head_path.is_file() and dummy_eyes_path.is_file(),
        i18n.translate("tests.dummies_detail"),
    )

    import physbone_helper

    physbone_cfg_specs = (
        ("michael_neko_mimi_physbones.cfg", 30),
        ("shinano_casual_physbones.cfg", 24),
        ("miltina_maid_physbones.cfg", 25),
    )
    configs_valid = True
    loaded_configs_map = {}
    for cfg_filename, expected_chains in physbone_cfg_specs:
        cfg_file_path = PROJECT_ROOT_DIR / "configs" / cfg_filename
        if not cfg_file_path.is_file():
            configs_valid = False
            continue
        parsed_cfg = physbone_helper.load_physbone_config(cfg_file_path)
        loaded_configs_map[cfg_filename] = parsed_cfg
        if len(parsed_cfg.get("chains", {})) != expected_chains:
            configs_valid = False
        if parsed_cfg.get("metadata", {}).get("marshmallow_pb", "false").lower() != "false":
            configs_valid = False

    per_ped_bone_groups = (
        tuple(physbone_helper.MICHAEL_ER_CUSTOM_BONES),
        tuple(physbone_helper.SHINANO_CASUAL_CUSTOM_BONES),
        tuple(physbone_helper.MILTINA_MAID_CUSTOM_BONES),
    )
    combined_pb_bones = (
        per_ped_bone_groups[0] + per_ped_bone_groups[1] + per_ped_bone_groups[2]
    )
    computed_bone_tags = [
        physbone_helper.compute_gtav_bone_tag(bone_name) for bone_name in combined_pb_bones
    ]
    parent_tag_values = set(physbone_helper.PARENT_BONE_TAGS.values())
    tags_unique = (
        all(
            len(bone_group) <= physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED
            for bone_group in per_ped_bone_groups
        )
        and len(combined_pb_bones) == 186
        and len(set(computed_bone_tags)) == 186
        and not (set(computed_bone_tags) & parent_tag_values)
    )

    simulator_step_ok = False
    if configs_valid:
        shinano_ear_cfg = loaded_configs_map["shinano_casual_physbones.cfg"]["chains"].get(
            "ear.L", {}
        )
        miltina_twin_cfg = loaded_configs_map["miltina_maid_physbones.cfg"]["chains"].get(
            "twintail1.L", {}
        )
        shinano_sim = physbone_helper.PhysBoneChainSimulator(
            rest_local_positions=[(0.0, 0.0, 0.08), (0.0, 0.0, 0.08), (0.0, 0.0, 0.08)],
            rest_local_rotations=[(0.0, 0.0, 0.0, 1.0)] * 3,
            config=shinano_ear_cfg,
        )
        miltina_sim = physbone_helper.PhysBoneChainSimulator(
            rest_local_positions=[(0.0, 0.0, -0.10), (0.0, 0.0, -0.10), (0.0, 0.0, -0.10)],
            rest_local_rotations=[(0.0, 0.0, 0.0, 1.0)] * 3,
            config=miltina_twin_cfg,
        )
        shinano_sim.reset((0.0, 0.0, 1.5), (0.0, 0.0, 0.0, 1.0))
        miltina_sim.reset((0.0, 0.0, 1.5), (0.0, 0.0, 0.0, 1.0))
        shinano_pos, shinano_rot = shinano_sim.step(
            (0.20, 0.0, 1.5), (0.0, 0.0, 0.0, 1.0), 1.0 / 60.0
        )
        miltina_pos, miltina_rot = miltina_sim.step(
            (0.20, 0.0, 1.5), (0.0, 0.0, 0.0, 1.0), 1.0 / 60.0
        )
        simulator_step_ok = (
            len(shinano_pos) == 3
            and len(miltina_pos) == 3
            and len(shinano_rot[2]) == 4
            and len(miltina_rot[2]) == 4
            and abs(shinano_pos[2][0] - 0.20) > 1e-4
            and abs(miltina_pos[2][0] - 0.20) > 1e-4
        )

    physbones_source_ok = print_status_result(
        "PhysBone configs, bone tags & solver",
        configs_valid and tags_unique and simulator_step_ok,
        f"bones={len(combined_pb_bones)}, unique_tags={len(set(computed_bone_tags))}, solver={simulator_step_ok}",
    )

    import ped_damage_helper

    damage_cylinders = ped_damage_helper.build_damage_cylinders()
    zone_checks_ok = (
        ped_damage_helper.resolve_ped_shader_filename(True) == "ped.sps"
        and ped_damage_helper.resolve_ped_shader_filename(False) == "ped_default.sps"
        and round(ped_damage_helper.DEFAULT_PED_COLOR1_SRGB[1] * 255.0) == 128
        and ped_damage_helper.DEFAULT_PED_COLOR2_SRGB == (0.0, 0.0, 0.0, 0.0)
        and ped_damage_helper.classify_bone_name_to_damage_zone("SKEL_Spine2")
        == ped_damage_helper.DAMAGE_ZONE_TORSO
        and ped_damage_helper.classify_bone_name_to_damage_zone("Skirt_Front_01")
        == ped_damage_helper.DAMAGE_ZONE_TORSO
        and ped_damage_helper.classify_bone_name_to_damage_zone("SKEL_Head")
        == ped_damage_helper.DAMAGE_ZONE_HEAD
        and ped_damage_helper.classify_bone_name_to_damage_zone("Hair_Bang_L", 0.03, 0.62)
        == ped_damage_helper.DAMAGE_ZONE_HEAD
        and ped_damage_helper.classify_bone_name_to_damage_zone("Hair_Back_03", 0.0, 0.20)
        == ped_damage_helper.DAMAGE_ZONE_NONE
        and ped_damage_helper.classify_bone_name_to_damage_zone("Tail_02")
        == ped_damage_helper.DAMAGE_ZONE_NONE
        and ped_damage_helper.classify_bone_name_to_damage_zone("SKEL_L_Forearm")
        == ped_damage_helper.DAMAGE_ZONE_LEFT_ARM
        and ped_damage_helper.classify_bone_name_to_damage_zone("SKEL_R_Forearm")
        == ped_damage_helper.DAMAGE_ZONE_RIGHT_ARM
        and ped_damage_helper.classify_bone_name_to_damage_zone("SKEL_L_Calf")
        == ped_damage_helper.DAMAGE_ZONE_LEFT_LEG
        and ped_damage_helper.classify_bone_name_to_damage_zone("SKEL_R_Calf")
        == ped_damage_helper.DAMAGE_ZONE_RIGHT_LEG
        and ped_damage_helper.classify_bone_name_to_damage_zone("Pocket Watch_Root", -0.10, 0.13)
        == ped_damage_helper.DAMAGE_ZONE_TORSO
    )
    sample_points = [
        (ped_damage_helper.DAMAGE_ZONE_TORSO, (0.0, -0.10, 0.20)),
        (ped_damage_helper.DAMAGE_ZONE_HEAD, (0.0, -0.09, 0.65)),
        (ped_damage_helper.DAMAGE_ZONE_LEFT_ARM, (0.30, -0.04, 0.28)),
        (ped_damage_helper.DAMAGE_ZONE_RIGHT_ARM, (-0.30, -0.04, 0.28)),
        (ped_damage_helper.DAMAGE_ZONE_LEFT_LEG, (0.12, -0.06, -0.50)),
        (ped_damage_helper.DAMAGE_ZONE_RIGHT_LEG, (-0.12, -0.06, -0.50)),
    ]
    projection_ok = (
        ped_damage_helper.project_point_onto_damage_zone(
            (0.0, 0.20, -0.10), ped_damage_helper.DAMAGE_ZONE_NONE, damage_cylinders
        )
        == (0.0, 0.0)
    )
    for expected_zone, sample_pt in sample_points:
        proj_u, proj_v_blender = ped_damage_helper.project_point_onto_damage_zone(
            sample_pt, expected_zone, damage_cylinders
        )
        v_ydd = 1.0 - proj_v_blender
        decoded_zone = int(((-v_ydd) + 0.5) * 0.5)
        projection_ok &= (proj_u >= 1.0 and proj_u <= 2.0 and decoded_zone == expected_zone)

    unwrapped_u = ped_damage_helper.unwrap_polygon_seam_u([1.95, 1.05, 1.98])
    seam_unwrap_ok = (
        all(val > 0.05 for val in unwrapped_u)
        and (max(unwrapped_u) - min(unwrapped_u)) < 0.5
    )

    sample_verts = [
        (0.02, -0.10, 0.20), (-0.02, -0.10, 0.20), (0.0, -0.10, 0.30),
        (0.02, -0.09, 0.62), (-0.02, -0.09, 0.62), (0.0, -0.09, 0.70),
        (0.28, -0.04, 0.30), (0.32, -0.04, 0.25), (0.30, -0.04, 0.20),
        (-0.28, -0.04, 0.30), (-0.32, -0.04, 0.25), (-0.30, -0.04, 0.20),
        (0.11, -0.06, -0.45), (0.14, -0.06, -0.50), (0.12, -0.06, -0.55),
        (-0.11, -0.06, -0.45), (-0.14, -0.06, -0.50), (-0.12, -0.06, -0.55),
        (0.0, 0.25, -0.05), (0.02, 0.30, -0.08), (-0.02, 0.30, -0.08),
    ]
    sample_polys = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8), (9, 10, 11), (12, 13, 14), (15, 16, 17), (18, 19, 20)
    ]
    sample_weights = (
        [{"SKEL_Spine2": 1.0}] * 3
        + [{"SKEL_Head": 1.0}] * 3
        + [{"SKEL_L_Forearm": 1.0}] * 3
        + [{"SKEL_R_Forearm": 1.0}] * 3
        + [{"SKEL_L_Calf": 1.0}] * 3
        + [{"SKEL_R_Calf": 1.0}] * 3
        + [{"Tail_02": 1.0}] * 3
    )
    computed_damage = ped_damage_helper.compute_mesh_damage_uvs(
        sample_verts, sample_polys, vertex_bone_weights=sample_weights
    )
    zone_counts = computed_damage["zone_poly_counts"]
    counts_ok = (
        zone_counts.get("torso") == 1
        and zone_counts.get("head") == 1
        and zone_counts.get("left_arm") == 1
        and zone_counts.get("right_arm") == 1
        and zone_counts.get("left_leg") == 1
        and zone_counts.get("right_leg") == 1
        and zone_counts.get("unmapped") == 1
        and len(computed_damage["loop_uvs"]) == 21
    )
    summary_text = ped_damage_helper.format_ped_damage_summary(
        {"shader": "ped.sps", "zone_poly_counts": zone_counts},
        translate_func=i18n.translate,
    )
    import inspect

    sig_cfg = inspect.signature(ped_damage_helper.configure_ped_shader_material).parameters
    sig_mat = inspect.signature(ped_damage_helper.create_ped_material).parameters
    shader_defaults_ok = (
        abs(ped_damage_helper.DEFAULT_ANIME_SPECULAR_FRESNEL - 0.98) < 1e-6
        and sig_cfg["bumpiness"].default == 0.0
        and sig_cfg["specular_intensity"].default == 0.0
        and sig_cfg["specular_falloff"].default == 1.0
        and abs(sig_cfg["specular_fresnel"].default - 0.98) < 1e-6
        and abs(sig_mat["specular_fresnel"].default - 0.98) < 1e-6
    )
    michael_src = (
        PROJECT_ROOT_DIR / "scripts/Shinano_EternalReunion_Michael/build_michael_er.py"
    ).read_text(encoding="utf-8")
    franklin_src = (
        PROJECT_ROOT_DIR / "scripts/Shinano_Casual_Franklin/build_franklin_avatar.py"
    ).read_text(encoding="utf-8")
    trevor_src = (
        PROJECT_ROOT_DIR / "scripts/Miltina_Maid_Trevor/build_trevor_miltina.py"
    ).read_text(encoding="utf-8")
    builders_non_chrome_ok = (
        ("specular_intensity=0.85" not in michael_src)
        and ("specular_fresnel=0.70" not in michael_src)
        and ("specular_fresnel=0.0" not in franklin_src)
        and ("specular_fresnel=0.0" not in trevor_src)
        and ("specular_fresnel=ped_damage_helper.DEFAULT_ANIME_SPECULAR_FRESNEL" in michael_src)
        and ("specular_fresnel=ped_damage_helper.DEFAULT_ANIME_SPECULAR_FRESNEL" in franklin_src)
        and ("specular_fresnel=ped_damage_helper.DEFAULT_ANIME_SPECULAR_FRESNEL" in trevor_src)
    )
    damage_decals_ok = print_status_result(
        i18n.translate("tests.ped_damage_decals"),
        zone_checks_ok
        and projection_ok
        and seam_unwrap_ok
        and counts_ok
        and ("ped.sps" in summary_text)
        and shader_defaults_ok
        and builders_non_chrome_ok,
        f"zones={zone_counts}",
    )

    import repack_and_deploy_everything as repack_mod

    with tempfile.TemporaryDirectory(prefix="vrc2gtav_rpf7_limit_") as rpf7_tmp:
        tmp_path = Path(rpf7_tmp)
        valid_res = tmp_path / "ok_prop.ydd"
        valid_res.write_bytes(b"\x00" * 1024)
        oversized_res = tmp_path / "too_big.ytd"
        oversized_res.write_bytes(b"\x00" * (ped_damage_helper.RPF7_MAX_RESOURCE_BYTES + 1))

        valid_size_ok = (
            ped_damage_helper.validate_rpf7_resource_file(valid_res) == 1024
            and len(ped_damage_helper.find_oversized_rpf7_resources(tmp_path)) == 1
        )
        rejected_oversized_res = False
        try:
            ped_damage_helper.validate_rpf7_resource_file(oversized_res)
        except ValueError:
            rejected_oversized_res = True

        rejected_dir_pack = False
        try:
            ped_damage_helper.assert_directory_rpf7_resources_valid(tmp_path)
        except ValueError:
            rejected_dir_pack = True

        # Build minimal binary RPF7 archives testing f_size == 0xFFFFFF & sector >= 0x7FFFFF
        def _write_synthetic_rpf7(
            target_rpf: Path,
            d1_descriptor: int,
            f_size_val: int,
            entry_name_str: str,
        ) -> None:
            name_bytes = entry_name_str.encode("ascii") + b"\x00"
            names_padded = name_bytes + (b"\x00" * ((16 - (len(name_bytes) % 16)) % 16))
            d0_val = 0 | ((f_size_val & 0xFFFF) << 16)
            d1_packed = d1_descriptor | ((f_size_val >> 16) & 0xFF)
            with open(target_rpf, "wb") as synth_handle:
                synth_handle.write(struct.pack("<II", 0x52504637, 1))
                synth_handle.write(struct.pack("<I4s", len(names_padded), b"OPEN"))
                synth_handle.write(struct.pack("<IIII", d0_val, d1_packed, 0, 0))
                synth_handle.write(names_padded)

        overflow_rpf = tmp_path / "res_overflow.rpf"
        _write_synthetic_rpf7(
            overflow_rpf,
            0x80000100,
            ped_damage_helper.RPF7_MAX_RESOURCE_BYTES,
            "oversized.ydd",
        )
        overflow_report = ped_damage_helper.inspect_rpf7_archive_limits(overflow_rpf)
        rejected_rpf_patch = False
        try:
            repack_mod.patch_rpf7_open_and_zero_compressed(overflow_rpf)
        except ValueError:
            rejected_rpf_patch = True

        sector_rpf = tmp_path / "sector_overflow.rpf"
        _write_synthetic_rpf7(sector_rpf, 0x7FFFFE00, 0, "late_entry.rpf")
        sector_report = ped_damage_helper.inspect_rpf7_archive_limits(sector_rpf)

        guards_wired = all(
            (PROJECT_ROOT_DIR / rel_path).read_text(encoding="utf-8")
            for rel_path in (
                "scripts/common_tools/apply_characters.py",
                "scripts/common_tools/repack_and_deploy_everything.py",
                "scripts/common_tools/build_universal_avatar.py",
                "scripts/Shinano_Casual_Franklin/generate_franklin_atlas.py",
                "scripts/Shinano_EternalReunion_Michael/generate_er_atlas.py",
                "scripts/Miltina_Maid_Trevor/generate_miltina_atlas.py",
            )
        )
        all_wired_tokens = (
            "validate_rpf7_resource_file"
            in (PROJECT_ROOT_DIR / "scripts/common_tools/apply_characters.py").read_text(
                encoding="utf-8"
            )
            and "inspect_rpf7_archive_limits"
            in (
                PROJECT_ROOT_DIR / "scripts/common_tools/repack_and_deploy_everything.py"
            ).read_text(encoding="utf-8")
            and "enforce_ytd_rpf7_size_budget"
            in (
                PROJECT_ROOT_DIR / "scripts/Shinano_EternalReunion_Michael/generate_er_atlas.py"
            ).read_text(encoding="utf-8")
            and "enforce_ped_rpf7_poly_budget"
            in (PROJECT_ROOT_DIR / "scripts/common_tools/build_universal_avatar.py").read_text(
                encoding="utf-8"
            )
        )
        import hand_skeleton_helper

        synth_raw_yft = bytearray(0xE000)
        struct.pack_into("<Q", synth_raw_yft, 0xA8, 0x5000C000)
        struct.pack_into("<Q", synth_raw_yft, 0x130, 175)
        synth_raw_yft[0xC010] = 108
        synth_raw_yft[0xC011] = 108
        synth_comp_obj = zlib.compressobj(level=6, wbits=-15)
        synth_yft_path = tmp_path / "synth_npc.yft"
        synth_yft_path.write_bytes(
            struct.pack("<4sIII", b"RSC7", 162, 0xA0021800, 0x20000000)
            + synth_comp_obj.compress(bytes(synth_raw_yft))
            + synth_comp_obj.flush()
        )
        yft_rejected = False
        try:
            ped_damage_helper.validate_rpf7_resource_file(synth_yft_path)
        except ValueError:
            yft_rejected = True
        yft_repair_info = hand_skeleton_helper.ensure_yft_shared_matrix_set_capacity(synth_yft_path)
        yft_verify_info = ped_damage_helper.validate_yft_rsc7_page_bounds(synth_yft_path)
        yft_matrix_guard_ok = (
            yft_rejected
            and yft_repair_info["expanded"] == 1
            and yft_repair_info["new_raw_bytes"] == 0x10000
            and yft_verify_info["system_flags"] == 0xA0002000
        )

        rpf7_guards_ok = print_status_result(
            i18n.translate("tests.rpf7_16mb_safeguards"),
            valid_size_ok
            and rejected_oversized_res
            and rejected_dir_pack
            and not overflow_report["ok"]
            and len(overflow_report["resource_overflows"]) == 1
            and rejected_rpf_patch
            and not sector_report["ok"]
            and len(sector_report["offset_overflows"]) == 1
            and guards_wired
            and all_wired_tokens
            and yft_matrix_guard_ok,
            "16 MiB, 4 GiB & YFT m_SharedMatrixSet bounds verified",
        )

    import eye_blink_helper
    import physbone_helper as pb_mod
    import types

    qp_center = eye_blink_helper.solve_nonneg_two_vector_weights(
        (0.0, 0.0, -0.02),
        (0.0, 0.0, -0.025),
        (-0.01, 0.0, -0.01),
    )
    qp_blend = eye_blink_helper.solve_nonneg_two_vector_weights(
        (-0.005, 0.0, -0.0175),
        (0.0, 0.0, -0.025),
        (-0.01, 0.0, -0.01),
    )
    qp_simplex_ok = (
        qp_center[0] >= 0.79
        and qp_center[1] <= 0.01
        and qp_blend[0] >= 0.0
        and qp_blend[1] >= 0.0
        and (qp_blend[0] + qp_blend[1]) <= 1.0001
        and abs(qp_blend[0] - 0.5) < 0.05
        and abs(qp_blend[1] - 0.5) < 0.05
    )

    dummy_keys = [
        types.SimpleNamespace(name="Basis"),
        types.SimpleNamespace(name="vrc.blink "),
        types.SimpleNamespace(name="eye_pleasure"),
    ]
    found_key = eye_blink_helper.find_blink_shape_key(dummy_keys)
    conflict_safe_open = eye_blink_helper.detect_custom_eye_expression_conflict(
        {"eye_pleasure_1": 0.75, "eye_zitome_1": 0.65, "eyelid_turi1": 0.65}
    )
    conflict_closed = eye_blink_helper.detect_custom_eye_expression_conflict(
        {"eye_pleasure": 0.75, "eye_><": 1.0}
    )
    conflict_blink = eye_blink_helper.detect_custom_eye_expression_conflict(
        {"vrc.Blink": 0.8}
    )

    base_bones_sample = [f"BONE_{idx:02d}" for idx in range(61)] + list(
        eye_blink_helper.YFT_ONLY_HAND_BONES
    )
    bones_blink_on, trimmed_cnt = eye_blink_helper.prepare_ydd_blink_bone_set(
        base_bones_sample,
        enable_eye_blink=True,
        custom_bone_count=62,
    )
    bones_blink_off, no_trim_cnt = eye_blink_helper.prepare_ydd_blink_bone_set(
        base_bones_sample,
        enable_eye_blink=False,
        custom_bone_count=62,
    )
    bone_budget_ok = (
        trimmed_cnt == 4
        and (len(bones_blink_on) + 62) == 127
        and all(
            lid_name in bones_blink_on
            for lid_name in eye_blink_helper.EYELID_BLINK_BONES
        )
        and no_trim_cnt == 0
        and len(bones_blink_off) == 65
        and all(
            hand_leaf in bones_blink_off
            for hand_leaf in eye_blink_helper.YFT_ONLY_HAND_BONES
        )
    )

    ini_roundtrip_ok = False
    with tempfile.TemporaryDirectory(prefix="vrc2gtav_blink_ini_") as blink_tmp:
        ini_file = Path(blink_tmp) / "GTAVPhysBones.ini"
        sample_blink_bones = [
            {
                "name": "PB_Blink_L",
                "tag": 44255,
                "parent_tag": 31086,
                "local_pos": (0.0348, -0.0931, 0.0806),
                "local_rot": (0.0, 0.0, 0.0, 1.0),
                "delta_pos": (0.0, 0.0, 0.0),
                "delta_rot": (0.28, 0.0, 0.0, 0.960000),
            },
            {
                "name": "PB_Blink_LO",
                "tag": 28167,
                "parent_tag": 31086,
                "local_pos": (0.0411, -0.0800, 0.0750),
                "local_rot": (0.0, 0.0, 0.0, 1.0),
                "delta_pos": (0.0, 0.0, 0.0),
                "delta_rot": (0.22, 0.0, -0.15, 0.963900),
            },
            {
                "name": "PB_Blink_R",
                "tag": 44357,
                "parent_tag": 31086,
                "local_pos": (-0.0319, -0.0931, 0.0806),
                "local_rot": (0.0, 0.0, 0.0, 1.0),
                "delta_pos": (0.0, 0.0, 0.0),
                "delta_rot": (0.28, 0.0, 0.0, 0.960000),
            },
            {
                "name": "PB_Blink_RO",
                "tag": 29607,
                "parent_tag": 31086,
                "local_pos": (-0.0382, -0.0800, 0.0750),
                "local_rot": (0.0, 0.0, 0.0, 1.0),
                "delta_pos": (0.0, 0.0, 0.0),
                "delta_rot": (0.22, 0.0, 0.15, 0.963900),
            },
        ]
        pb_mod.merge_physbone_asi_ini(
            ini_file,
            [],
            target_ped_model="all",
            blink_profiles=[
                {
                    "model": "player_zero",
                    "enabled": 1,
                    "max_blink": 0.5,
                    "bones": sample_blink_bones,
                }
            ],
            own_blink_models=("player_zero",),
        )
        pb_mod.merge_physbone_asi_ini(
            ini_file,
            [],
            target_ped_model="all",
            blink_profiles=[
                {
                    "model": "player_two",
                    "enabled": 1,
                    "max_blink": 0.6,
                    "bones": sample_blink_bones,
                }
            ],
            own_blink_models=("player_two",),
        )
        both_profiles = pb_mod._load_ini_blink_profiles(ini_file)
        pb_mod.merge_physbone_asi_ini(
            ini_file,
            [],
            target_ped_model="all",
            blink_profiles=[],
            own_blink_models=("player_zero",),
        )
        after_disable = pb_mod._load_ini_blink_profiles(ini_file)
        ini_roundtrip_ok = (
            len(both_profiles) == 2
            and {item["model"] for item in both_profiles} == {"player_zero", "player_two"}
            and any(
                item["model"] == "player_zero" and abs(float(item.get("max_blink", 0.0)) - 0.5) < 1e-4
                for item in both_profiles
            )
            and len(after_disable) == 1
            and after_disable[0]["model"] == "player_two"
            and abs(float(after_disable[0].get("max_blink", 0.0)) - 0.6) < 1e-4
            and len(after_disable[0]["bones"]) == 4
            and abs(float(after_disable[0]["bones"][0]["delta_rot"][0]) - 0.28) < 1e-4
            and abs(float(after_disable[0]["bones"][0]["delta_rot"][3]) - 0.96) < 1e-4
        )

    strength_resolution_ok = (
        abs(eye_blink_helper.resolve_eye_blink_strength(None, None, avatar_id="shinano_casual") - 0.5) < 1e-5
        and abs(eye_blink_helper.resolve_eye_blink_strength(None, None, avatar_id="shinano_er") - 0.5) < 1e-5
        and abs(eye_blink_helper.resolve_eye_blink_strength(None, None, avatar_id="miltina_maid") - 0.6) < 1e-5
        and abs(eye_blink_helper.resolve_eye_blink_strength(None, {"eye_blink_strength": "0.55"}, avatar_id="shinano_casual") - 0.55) < 1e-5
        and abs(eye_blink_helper.resolve_eye_blink_strength(0.45, {"eye_blink_strength": "0.55"}, avatar_id="miltina_maid") - 0.45) < 1e-5
    )

    class _IdentityMat4:
        def copy(self):
            return self

        def __matmul__(self, coord_vec):
            return coord_vec

    class _MockVec3:
        def __init__(self, x_val: float, y_val: float, z_val: float):
            self.x = x_val
            self.y = y_val
            self.z = z_val

    base_coords = (
        [(0.025 + 0.002 * step_idx, -0.09, 1.56) for step_idx in range(6)]
        + [(-0.025 - 0.002 * step_idx, -0.09, 1.56) for step_idx in range(6)]
        + [
            (0.02, -0.09, 1.48),   # idx 12: mouth/smile vertex
            (0.03, -0.09, 1.585),  # idx 13: eyebrow vertex
            (0.03, -0.089, 1.584), # idx 14: forehead skin behind eyebrow
        ]
    )
    eyelid_indices = set(range(12))
    blink_key_coords = []
    brow_key_coords = []
    for v_idx, (bx_val, by_val, bz_val) in enumerate(base_coords):
        if v_idx in eyelid_indices:
            blink_key_coords.append(_MockVec3(bx_val, by_val - 0.003, bz_val - 0.018))
        elif v_idx == 14:
            blink_key_coords.append(_MockVec3(bx_val, by_val + 0.001, bz_val - 0.004))
        else:
            blink_key_coords.append(_MockVec3(bx_val, by_val, bz_val))
        brow_z = bz_val + 0.003 if v_idx == 13 else bz_val
        brow_key_coords.append(_MockVec3(bx_val, by_val, brow_z))

    key_basis = types.SimpleNamespace(
        name="Basis",
        value=0.0,
        mute=False,
        data=[types.SimpleNamespace(co=_MockVec3(*xyz)) for xyz in base_coords],
    )
    key_blink = types.SimpleNamespace(
        name="vrc.Blink",
        value=0.0,
        mute=False,
        data=[types.SimpleNamespace(co=vec_co) for vec_co in blink_key_coords],
    )
    key_brow = types.SimpleNamespace(
        name="eyebrow_straight",
        value=0.0,
        mute=False,
        data=[types.SimpleNamespace(co=vec_co) for vec_co in brow_key_coords],
    )
    key_pleasure = types.SimpleNamespace(name="eye_pleasure", value=0.75, mute=False)
    key_turi = types.SimpleNamespace(name="eyelid_turi1", value=0.65, mute=False)
    key_smile = types.SimpleNamespace(name="mouth_smile", value=0.40, mute=False)

    def _eval_fake_coords():
        coords_out = []
        for v_idx, (bx_val, by_val, bz_val) in enumerate(base_coords):
            x_out, y_out, z_out = bx_val, by_val, bz_val
            if v_idx == 12:
                z_out += 0.006 * key_smile.value
            elif v_idx == 13:
                z_out -= 0.002 * key_turi.value
            elif v_idx == 14:
                if not key_blink.mute and key_blink.value > 0.0:
                    z_out -= 0.004 * key_blink.value
                    y_out += 0.001 * key_blink.value
            else:
                z_out -= 0.002 * key_pleasure.value
                z_out -= 0.001 * key_turi.value
            if not key_blink.mute and key_blink.value > 0.0 and v_idx in eyelid_indices:
                z_out -= 0.018 * key_blink.value
                y_out -= 0.003 * key_blink.value
            coords_out.append(_MockVec3(x_out, y_out, z_out))
        return coords_out

    def _eval_fake_body(_deps):
        eval_mesh = types.SimpleNamespace(
            vertices=[types.SimpleNamespace(co=vec_co) for vec_co in _eval_fake_coords()]
        )
        return types.SimpleNamespace(
            matrix_world=_IdentityMat4(),
            to_mesh=lambda: eval_mesh,
            to_mesh_clear=lambda: None,
        )

    fake_body_obj = types.SimpleNamespace(
        data=types.SimpleNamespace(
            vertices=[types.SimpleNamespace(co=_MockVec3(*xyz)) for xyz in base_coords],
            shape_keys=types.SimpleNamespace(
                key_blocks=[key_basis, key_blink, key_brow, key_pleasure, key_turi, key_smile]
            ),
        ),
        evaluated_get=_eval_fake_body,
    )
    fake_bpy_mod = types.SimpleNamespace(
        context=types.SimpleNamespace(
            evaluated_depsgraph_get=lambda: None,
            view_layer=types.SimpleNamespace(update=lambda: None),
        )
    )
    extracted_rig = eye_blink_helper.extract_body_eyelid_blink_rig_data(
        fake_bpy_mod,
        fake_body_obj,
        eye_blink_mode="auto",
        shape_weights={
            "eye_pleasure": 0.75,
            "eyelid_turi1": 0.65,
            "mouth_smile": 0.40,
        },
    )
    other_blendshapes_untouched_ok = (
        extracted_rig.get("enabled") is True
        and abs(key_blink.value - 0.0) < 1e-6
        and abs(key_pleasure.value - 0.75) < 1e-6
        and abs(key_turi.value - 0.65) < 1e-6
        and abs(key_smile.value - 0.40) < 1e-6
        and (12 not in extracted_rig.get("weights_by_orig_vert", {}))
        and (13 not in extracted_rig.get("weights_by_orig_vert", {}))
        and (14 not in extracted_rig.get("weights_by_orig_vert", {}))
        and all(
            idx in extracted_rig.get("weights_by_orig_vert", {})
            for idx in eyelid_indices
        )
        and "PB_Blink_L" in extracted_rig.get("pivots_world", {})
        and "PB_Blink_R" in extracted_rig.get("rot_quats_world", {})
    )

    eye_blink_ok = print_status_result(
        i18n.translate("tests.eye_blink_rigging"),
        qp_simplex_ok
        and (found_key is not None and found_key.name == "vrc.blink ")
        and (conflict_safe_open is None)
        and (conflict_closed is not None)
        and (conflict_blink is not None)
        and bone_budget_ok
        and ini_roundtrip_ok
        and strength_resolution_ok
        and other_blendshapes_untouched_ok,
        (
            f"key='vrc.blink ', bone_budget=127/128, ini_merge={ini_roundtrip_ok}, "
            f"strength_presets={strength_resolution_ok}, other_shapes_isolated={other_blendshapes_untouched_ok}"
        ),
    )

    return (
        template_ok
        and gitignore_check
        and dummies_ok
        and physbones_source_ok
        and damage_decals_ok
        and rpf7_guards_ok
        and eye_blink_ok
    )

