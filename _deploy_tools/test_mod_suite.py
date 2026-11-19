#!/usr/bin/env python3
"""
test_mod_suite.py
=================
Automated validation suite for verifying all Python scripts, trilingual
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
from pathlib import Path
from typing import Any, List, Sequence, Tuple

CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT_DIR = CURRENT_SCRIPT_DIR.parent.parent
sys.path.insert(0, str(CURRENT_SCRIPT_DIR))
sys.path.insert(0, str(PROJECT_ROOT_DIR / "_deploy_tools"))

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
        within_rpf7_cap = (
            file_exists and file_size_bytes <= ped_damage_helper.RPF7_MAX_RESOURCE_BYTES
        )
        all_assets_present &= print_status_result(
            asset_file_path.name,
            file_exists and within_rpf7_cap,
            i18n.translate(
                "tests.asset_detail",
                size=file_size_mb,
                parent=asset_file_path.parent.name,
            ),
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
                if blink_enabled == 1 and blink_bones == 4 and blink_model:
                    blink_models_found.add(blink_model)
                    blink_max_by_model[blink_model] = blink_max_val
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
        "1_Franklin_Shinano_Casual/4_exported_models/uppr_000_u.ydd.xml",
        "2_Michael_Shinano_EternalReunion/4_exported_models/uppr_000_u.ydd.xml",
        "3_Trevor_Miltina_Maid/4_exported_models/uppr_000_u.ydd.xml",
    ):
        xml_file = PROJECT_ROOT_DIR / xml_rel_path
        if xml_file.is_file():
            xml_text = xml_file.read_text(encoding="utf-8", errors="ignore")
            if (
                "FACIAL_L_eyelidUpper" not in xml_text
                or "FACIAL_R_eyelidUpper" not in xml_text
            ):
                blink_ydd_bones_ok = False

    blink_peaks_ok = (
        abs(blink_max_by_model.get("player_zero", 1.0) - 0.5) < 0.02
        and abs(blink_max_by_model.get("player_one", 1.0) - 0.5) < 0.02
        and abs(blink_max_by_model.get("player_two", 1.0) - 0.6) < 0.02
    )
    physbones_runtime_ok = (
        asi_exists
        and ini_exists
        and ini_total_chains == 79
        and ear_chains_count == 30
        and shinano_chains_count == 24
        and miltina_chains_count == 25
        and ini_blink_count >= 3
        and {"player_zero", "player_one", "player_two"}.issubset(blink_models_found)
        and blink_peaks_ok
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
    patchday4_inner = (
        rpf_paths_cfg["patchday4ng_dlc_extracted"] / rpf_paths_cfg["patchday4ng_rpf_relative"]
    )
    if patchday4_inner.is_file():
        repacked_archives.append(patchday4_inner)
    if rpf_paths_cfg["patchday4ng_game_rpf"].is_file():
        repacked_archives.append(rpf_paths_cfg["patchday4ng_game_rpf"])

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
        (common_dir / "vrc2gtav_i18n.py", deploy_dir / "vrc2gtav_i18n.py"),
        (common_dir / "vrc2gtav_paths.py", deploy_dir / "vrc2gtav_paths.py"),
        (common_dir / "error_handler_helper.py", deploy_dir / "error_handler_helper.py"),
        (common_dir / "avatar_archive_helper.py", deploy_dir / "avatar_archive_helper.py"),
        (common_dir / "modular_avatar_helper.py", deploy_dir / "modular_avatar_helper.py"),
        (common_dir / "build_universal_avatar.py", deploy_dir / "build_universal_avatar.py"),
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
            and all_wired_tokens,
            "16 MiB resource & 4 GiB offset guards verified",
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
                "name": "FACIAL_L_eyelidUpper",
                "tag": 38849,
                "parent_tag": 65068,
                "local_pos": (0.0348, -0.0931, 0.7032),
                "local_rot": (0.0, 0.0, 0.0, 1.0),
                "delta_pos": (0.0, 0.005, -0.024),
            },
            {
                "name": "FACIAL_L_eyelidUpperOuterSDK",
                "tag": 44821,
                "parent_tag": 38849,
                "local_pos": (0.0063, -0.0137, 0.0036),
                "local_rot": (0.0, 0.0, 0.0, 1.0),
                "delta_pos": (-0.010, -0.006, 0.008),
            },
            {
                "name": "FACIAL_R_eyelidUpper",
                "tag": 32276,
                "parent_tag": 65068,
                "local_pos": (-0.0319, -0.0931, 0.7032),
                "local_rot": (0.0, 0.0, 0.0, 1.0),
                "delta_pos": (0.0, 0.005, -0.024),
            },
            {
                "name": "FACIAL_R_eyelidUpperOuterSDK",
                "tag": 45333,
                "parent_tag": 32276,
                "local_pos": (-0.0063, -0.0137, 0.0036),
                "local_rot": (0.0, 0.0, 0.0, 1.0),
                "delta_pos": (0.010, -0.006, 0.008),
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
        ]
    )
    eyelid_indices = set(range(12))
    blink_key_coords = []
    for v_idx, (bx_val, by_val, bz_val) in enumerate(base_coords):
        if v_idx in eyelid_indices:
            blink_key_coords.append(_MockVec3(bx_val, by_val - 0.003, bz_val - 0.018))
        else:
            blink_key_coords.append(_MockVec3(bx_val, by_val, bz_val))

    key_basis = types.SimpleNamespace(name="Basis", value=0.0, mute=False)
    key_blink = types.SimpleNamespace(
        name="vrc.Blink",
        value=0.0,
        mute=False,
        data=[types.SimpleNamespace(co=vec_co) for vec_co in blink_key_coords],
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
                key_blocks=[key_basis, key_blink, key_pleasure, key_turi, key_smile]
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
        and all(
            idx in extracted_rig.get("weights_by_orig_vert", {})
            for idx in eyelid_indices
        )
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


def test_unity_scene_and_fallbacks() -> bool:
    """Validate Unity scene scale extraction, unit defaults, and hair/texture fallbacks."""
    import tempfile
    from PIL import Image as pil_image
    import texture_calibration_helper as calibration_helper
    import unity_scene_helper

    print(f"\n=== {i18n.translate('tests.suite_unity')} ===")
    suite_passed = True

    empty_cfg = unity_scene_helper.extract_unity_avatar_config("")
    missing_cfg = unity_scene_helper.extract_unity_avatar_config(
        "/tmp/vrc2gtav_nonexistent_scene.unity"
    )
    empty_ok = (
        not empty_cfg["loaded"]
        and not missing_cfg["loaded"]
        and empty_cfg["root_scale"] == (1.0, 1.0, 1.0)
        and empty_cfg["armature_scale"] == (1.0, 1.0, 1.0)
        and empty_cfg["bone_scales"] == {}
    )
    suite_passed &= print_status_result(
        i18n.translate("tests.unity_empty_unit_scales"), empty_ok, "scale=1.0"
    )

    synthetic_unity_yaml = "\n".join(
        [
            "%YAML 1.1",
            "%TAG !u! tag:unity3d.com,2011:",
            "--- !u!1 &100",
            "GameObject:",
            "  m_Name: TestAvatar",
            "  m_IsActive: 1",
            "--- !u!4 &101",
            "Transform:",
            "  m_GameObject: {fileID: 100}",
            "  m_LocalScale: {x: 1, y: 1, z: 1}",
            "  m_Father: {fileID: 0}",
            "--- !u!1 &200",
            "GameObject:",
            "  m_Name: Armature",
            "  m_IsActive: 1",
            "--- !u!4 &201",
            "Transform:",
            "  m_GameObject: {fileID: 200}",
            "  m_LocalScale: {x: 1.125, y: 1.125, z: 1.125}",
            "  m_Father: {fileID: 101}",
            "--- !u!1 &300",
            "GameObject:",
            "  m_Name: Neck",
            "  m_IsActive: 1",
            "--- !u!4 &301",
            "Transform:",
            "  m_GameObject: {fileID: 300}",
            "  m_LocalScale: {x: 0.9, y: 0.9, z: 0.9}",
            "  m_Father: {fileID: 201}",
            "--- !u!1 &400",
            "GameObject:",
            "  m_Name: lower_leg_L",
            "  m_IsActive: 1",
            "--- !u!4 &401",
            "Transform:",
            "  m_GameObject: {fileID: 400}",
            "  m_LocalScale: {x: 1, y: 1.2, z: 1}",
            "  m_Father: {fileID: 201}",
            "--- !u!1 &500",
            "GameObject:",
            "  m_Name: Breast_1.L",
            "  m_IsActive: 1",
            "--- !u!4 &501",
            "Transform:",
            "  m_GameObject: {fileID: 500}",
            "  m_LocalScale: {x: 0.5, y: 0.5, z: 0.5}",
            "  m_Father: {fileID: 201}",
            "--- !u!1 &502",
            "GameObject:",
            "  m_Name: Breast_1.L",
            "  m_IsActive: 1",
            "--- !u!4 &503",
            "Transform:",
            "  m_GameObject: {fileID: 502}",
            "  m_LocalScale: {x: 2.0, y: 2.0, z: 2.0}",
            "  m_Father: {fileID: 501}",
        ]
    )

    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_root = Path(temp_dir_name)
        scene_file = temp_root / "SyntheticAvatar.unity"
        scene_file.write_text(synthetic_unity_yaml, encoding="utf-8")

        parsed_cfg = unity_scene_helper.extract_unity_avatar_config(
            scene_file, avatar_name="TestAvatar"
        )
        neck_scale = parsed_cfg["bone_scales"].get("Neck", (1.0, 1.0, 1.0))
        leg_scale = parsed_cfg["bone_scales"].get("lower_leg_L", (1.0, 1.0, 1.0))
        scene_ok = (
            parsed_cfg["loaded"]
            and abs(parsed_cfg["armature_scale"][0] - 1.125) < 1e-4
            and abs(neck_scale[0] - 0.9) < 1e-4
            and abs(leg_scale[1] - 1.2) < 1e-4
            and "Breast_1.L" not in parsed_cfg["bone_scales"]
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.unity_extracts_scene_scales"),
            scene_ok,
            f"bones={len(parsed_cfg['bone_scales'])}",
        )

        hair_blank_mode, _ = unity_scene_helper.resolve_hair_mode("", parsed_cfg)
        hair_missing_mode, _ = unity_scene_helper.resolve_hair_mode(
            str(temp_root / "missing_hair.fbx"), parsed_cfg
        )
        hair_ok = hair_blank_mode == "default" and hair_missing_mode == "default"
        suite_passed &= print_status_result(
            i18n.translate("tests.unity_hair_fallback_mode"),
            hair_ok,
            f"{hair_blank_mode}/{hair_missing_mode}",
        )

        base_face_file = temp_root / "Shinano_face.png"
        base_hair_file = temp_root / "Shinano_hair.png"
        miltina_face_file = temp_root / "Milltina_Face.png"
        miltina_hair_file = temp_root / "Milltina_Hair.png"
        sample_img = pil_image.new("RGBA", (64, 64), (210, 200, 195, 255))
        for sample_path in (
            base_face_file,
            base_hair_file,
            miltina_face_file,
            miltina_hair_file,
        ):
            sample_img.save(sample_path, "PNG")

        shinano_face_out, missing_layers = (
            calibration_helper.composite_shinano_face_with_fallback(
                face_path=base_face_file,
                target_size=64,
                makeup_path=str(temp_root / "missing_makeup.png"),
                eye_sky_path=str(temp_root / "missing_sky.png"),
            )
        )
        shi_diff, shi_spec, shi_norm = calibration_helper.calibrate_shinano_default_hair(
            base_hair_file, temp_root, 64
        )
        mil_diff, mil_spec, mil_norm = calibration_helper.calibrate_miltina_default_hair(
            miltina_hair_file, temp_root, 64
        )
        with pil_image.open(miltina_face_file) as miltina_face_opened:
            mil_face_rgba = miltina_face_opened.convert("RGBA")
        mil_face_out, mil_eye_spec, used_custom_eyes = (
            calibration_helper.composite_miltina_eyes_with_fallback(
                mil_face_rgba,
                str(temp_root / "missing_aw_eyes.png"),
                str(temp_root / "missing_aw_hl.png"),
            )
        )
        tex_ok = (
            shinano_face_out.size == (64, 64)
            and "makeup" in missing_layers
            and shi_diff.size == (64, 64)
            and shi_spec.size == (64, 64)
            and shi_norm.size == (64, 64)
            and mil_diff.size == (64, 64)
            and mil_spec.size == (64, 64)
            and mil_norm.size == (64, 64)
            and mil_face_out.size == (64, 64)
            and mil_eye_spec is None
            and not used_custom_eyes
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.texture_fallback_ready"), tex_ok, "64x64 RGBA"
        )

        import blendshape_helper

        presets_dir = PROJECT_ROOT_DIR / "configs"
        expected_presets = (
            "shinano_blendshapes.cfg",
            "shinano_er_blendshapes.cfg",
            "miltina_blendshapes.cfg",
        )
        presets_ok = True
        total_preset_meshes = 0
        for preset_name in expected_presets:
            preset_path = presets_dir / preset_name
            if not preset_path.is_file():
                presets_ok = False
                continue
            loaded_meshes, _loaded_meta = blendshape_helper.load_blendshapes_cfg(
                preset_path
            )
            if not loaded_meshes:
                presets_ok = False
            total_preset_meshes += len(loaded_meshes)

        roundtrip_cfg_path = temp_root / "roundtrip_blendshapes.cfg"
        special_weights = {
            "Body": {
                "======Nail======": 0.0,
                "(T1)highlight_main_x": 0.0,
                "mouth_yaeba(tooth)_top_R": 1.0,
                "index:5": 0.725,
            },
            "Milltina_cloth_hat": {
                "Option_Twin tail": 1.0,
            },
        }
        blendshape_helper.save_blendshapes_cfg(
            roundtrip_cfg_path,
            special_weights,
            metadata={"avatar": "RoundTripTest", "source": "unit_test"},
        )
        parsed_roundtrip, parsed_meta = blendshape_helper.load_blendshapes_cfg(
            roundtrip_cfg_path
        )
        presets_ok = (
            presets_ok
            and parsed_meta.get("avatar") == "RoundTripTest"
            and abs(parsed_roundtrip["Body"]["mouth_yaeba(tooth)_top_R"] - 1.0) < 1e-6
            and abs(parsed_roundtrip["Body"]["index:5"] - 0.725) < 1e-6
            and abs(parsed_roundtrip["Body"]["(T1)highlight_main_x"]) < 1e-6
            and "======Nail======" in parsed_roundtrip["Body"]
            and abs(parsed_roundtrip["Milltina_cloth_hat"]["Option_Twin tail"] - 1.0)
            < 1e-6
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.blendshapes_cfg_presets"),
            presets_ok,
            f"presets={len(expected_presets)}, meshes={total_preset_meshes}",
        )

        hair_guid = "11111111222222223333333344444444"
        prefab_file = temp_root / "TestHair.prefab"
        prefab_meta_file = temp_root / "TestHair.prefab.meta"
        prefab_meta_file.write_text(
            f"fileFormatVersion: 2\nguid: {hair_guid}\n",
            encoding="utf-8",
        )
        prefab_file.write_text(
            "\n".join(
                [
                    "%YAML 1.1",
                    "%TAG !u! tag:unity3d.com,2011:",
                    "--- !u!1 &1000",
                    "GameObject:",
                    "  m_Name: Bangs",
                    "  m_IsActive: 1",
                    "--- !u!4 &1001",
                    "Transform:",
                    "  m_GameObject: {fileID: 1000}",
                    "  m_Children: []",
                    "  m_Father: {fileID: 0}",
                    "--- !u!137 &1002",
                    "SkinnedMeshRenderer:",
                    "  m_GameObject: {fileID: 1000}",
                    "  m_Enabled: 1",
                    "  m_BlendShapeWeights:",
                    "  - 0",
                    "  - 50",
                ]
            ),
            encoding="utf-8",
        )
        blend_scene_file = temp_root / "SyntheticBlendAvatar.unity"
        blend_scene_file.write_text(
            "\n".join(
                [
                    "%YAML 1.1",
                    "%TAG !u! tag:unity3d.com,2011:",
                    "--- !u!1 &100",
                    "GameObject:",
                    "  m_Name: BlendAvatar",
                    "  m_IsActive: 1",
                    "--- !u!4 &101",
                    "Transform:",
                    "  m_GameObject: {fileID: 100}",
                    "  m_Children:",
                    "  - {fileID: 301}",
                    "  m_Father: {fileID: 0}",
                    "--- !u!1 &300",
                    "GameObject:",
                    "  m_Name: Body_base",
                    "  m_IsActive: 1",
                    "--- !u!4 &301",
                    "Transform:",
                    "  m_GameObject: {fileID: 300}",
                    "  m_Children: []",
                    "  m_Father: {fileID: 101}",
                    "--- !u!137 &302",
                    "SkinnedMeshRenderer:",
                    "  m_GameObject: {fileID: 300}",
                    "  m_Enabled: 1",
                    "  m_BlendShapeWeights:",
                    "  - 100",
                    "--- !u!1001 &900",
                    "PrefabInstance:",
                    "  m_Modification:",
                    "    m_TransformParent: {fileID: 101}",
                    "    m_Modifications:",
                    "    - target: {fileID: 1002, guid: 11111111222222223333333344444444}",
                    "      propertyPath: m_BlendShapeWeights.Array.data[0]",
                    "      value: 75",
                    f"  m_SourcePrefab: {{fileID: 100100000, guid: {hair_guid}}}",
                ]
            ),
            encoding="utf-8",
        )
        anim_file = temp_root / "SyntheticFace.anim"
        anim_file.write_text(
            "\n".join(
                [
                    "%YAML 1.1",
                    "  - serializedVersion: 2",
                    "    curve:",
                    "      m_Curve:",
                    "      - serializedVersion: 3",
                    "        value: 80",
                    "    attribute: blendShape.eye_big",
                    "    path: Body",
                ]
            ),
            encoding="utf-8",
        )
        extracted_blend = blendshape_helper.extract_unity_scene_blendshapes(
            blend_scene_file,
            avatar_name="BlendAvatar",
            unity_assets_root=temp_root,
        )
        unity_extract_ok = (
            extracted_blend["loaded"]
            and abs(extracted_blend["mesh_weights"]["Body_base"]["index:0"] - 1.0)
            < 1e-4
            and abs(extracted_blend["mesh_weights"]["Bangs"]["index:0"] - 0.75) < 1e-4
            and abs(extracted_blend["mesh_weights"]["Bangs"]["index:1"] - 0.5) < 1e-4
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.blendshapes_unity_extract"),
            unity_extract_ok,
            f"meshes={len(extracted_blend['mesh_weights'])}",
        )

        test_char_cfg = {
            "blendshapes_source": "auto",
            "blendshapes_cfg": str(roundtrip_cfg_path),
            "unity_scene": str(blend_scene_file),
            "unity_avatar_name": "BlendAvatar",
            "face_anim": str(anim_file),
        }
        res_auto_unity = blendshape_helper.resolve_character_blendshapes(
            test_char_cfg,
            unity_assets_root=temp_root,
        )
        res_forced_cfg = blendshape_helper.resolve_character_blendshapes(
            test_char_cfg,
            unity_assets_root=temp_root,
            override_source="cfg",
        )
        test_char_cfg["unity_scene"] = ""
        res_auto_cfg = blendshape_helper.resolve_character_blendshapes(
            test_char_cfg,
            unity_assets_root=temp_root,
        )
        resolution_ok = (
            res_auto_unity["source_used"] == "unity"
            and abs(res_auto_unity["mesh_weights"]["Body"]["eye_big"] - 0.8) < 1e-4
            and res_forced_cfg["source_used"] == "cfg"
            and "index:5" in res_forced_cfg["mesh_weights"]["Body"]
            and res_auto_cfg["source_used"] == "cfg"
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.blendshapes_resolution_order"),
            resolution_ok,
            f"{res_auto_unity['source_used']}/{res_forced_cfg['source_used']}/{res_auto_cfg['source_used']}",
        )

        # Verify binary FBX channel discovery & zero-fill preservation without resetting .cfg edits
        def pack_fbx_prop(prop_val):
            if isinstance(prop_val, int):
                return b"L" + struct.pack("<q", prop_val)
            raw_bytes = prop_val.encode("utf-8")
            return b"S" + struct.pack("<I", len(raw_bytes)) + raw_bytes

        def pack_fbx_node(node_name, prop_list, children_bytes=b"", cursor_offset=0):
            props_blob = b"".join(pack_fbx_prop(item) for item in prop_list)
            name_bytes = node_name.encode("utf-8")
            body_len = len(props_blob) + len(children_bytes)
            sentinel = b"\x00" * 25 if children_bytes else b""
            end_offset = cursor_offset + 25 + len(name_bytes) + body_len + len(sentinel)
            header = struct.pack("<QQQB", end_offset, len(prop_list), len(props_blob), len(name_bytes))
            return header + name_bytes + props_blob + children_bytes + sentinel

        obj_children = bytearray()
        cursor_pos = 27 + 25 + len(b"Objects")
        for node_tag, node_props in [
            ("Model", [10, "Body\x00\x01Model", "Mesh"]),
            ("Geometry", [20, "Body\x00\x01Geometry", "Mesh"]),
            ("Deformer", [30, "BlendShape\x00\x01Deformer", "BlendShape"]),
            ("Deformer", [40, "eye_joy\x00\x01Deformer", "BlendShapeChannel"]),
            ("Deformer", [41, "======Eye======\x00\x01Deformer", "BlendShapeChannel"]),
            ("Deformer", [42, "body_slim\x00\x01Deformer", "BlendShapeChannel"]),
        ]:
            chunk = pack_fbx_node(node_tag, node_props, cursor_offset=cursor_pos)
            obj_children.extend(chunk)
            cursor_pos += len(chunk)
        objects_node = pack_fbx_node("Objects", [], bytes(obj_children), cursor_offset=27)

        conn_children = bytearray()
        conn_cursor = 27 + len(objects_node) + 25 + len(b"Connections")
        for child_id, parent_id in [(20, 10), (30, 20), (40, 30), (41, 30), (42, 30)]:
            chunk = pack_fbx_node("C", ["OO", child_id, parent_id], cursor_offset=conn_cursor)
            conn_children.extend(chunk)
            conn_cursor += len(chunk)
        connections_node = pack_fbx_node(
            "Connections", [], bytes(conn_children), cursor_offset=27 + len(objects_node)
        )
        synthetic_fbx = temp_root / "SyntheticShinano.fbx"
        synthetic_fbx.write_bytes(
            b"Kaydara FBX Binary  \x00\x1a\x00"
            + struct.pack("<I", 7500)
            + objects_node
            + connections_node
            + (b"\x00" * 25)
        )

        partial_cfg_path = temp_root / "partial_shinano.cfg"
        blendshape_helper.save_blendshapes_cfg(
            partial_cfg_path,
            {"Body": {"eye_joy": 0.35}},
            metadata={"avatar": "SynthShinano", "source": "preset_cfg"},
        )
        merged_cfg_path = temp_root / "merged_shinano.cfg"
        merged_res = blendshape_helper.resolve_character_blendshapes(
            {"blendshapes_source": "cfg", "blendshapes_cfg": str(partial_cfg_path)},
            fbx_paths=[synthetic_fbx],
            save_cfg_path=merged_cfg_path,
        )
        reloaded_merged, _ = blendshape_helper.load_blendshapes_cfg(merged_cfg_path)
        shinano_tracked, _ = blendshape_helper.load_blendshapes_cfg(
            presets_dir / "shinano_blendshapes.cfg"
        )
        fbx_merge_ok = (
            abs(merged_res["mesh_weights"]["Body"]["eye_joy"] - 0.35) < 1e-6
            and abs(reloaded_merged["Body"]["eye_joy"] - 0.35) < 1e-6
            and "======Eye======" in reloaded_merged["Body"]
            and abs(reloaded_merged["Body"]["======Eye======"]) < 1e-6
            and abs(reloaded_merged["Body"]["body_slim"]) < 1e-6
            and len(shinano_tracked) >= 13
            and len(shinano_tracked.get("Body", {})) >= 500
            and abs(shinano_tracked["Body"].get("eye_joy", 0.0) - 0.08) < 1e-6
            and abs(shinano_tracked["Body_base"].get("Shrink_Foot", 0.0) - 1.0) < 1e-6
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.blendshapes_fbx_merge"),
            fbx_merge_ok,
            f"shinano_meshes={len(shinano_tracked)}, body_keys={len(shinano_tracked.get('Body', {}))}",
        )

        import physbone_helper

        pb_assets_root = temp_root / "SynthPBAssets"
        pb_root = pb_assets_root / "marshmallow_PB"
        pb_root.mkdir(parents=True, exist_ok=True)
        marsh_asset = pb_root / "CustomMarshPreset.asset"
        marsh_asset.write_text(
            "\n".join(
                [
                    "%YAML 1.1",
                    "_PhysBone_Pull: 0.08",
                    "_PhysBone_Momentum: 0.55",
                    "_PhysBone_Stiffness: 0.35",
                    "_PhysBone_Gravity: 0.30",
                    "_PhysBone_GravityFalloff: 0.25",
                    "_PhysBone_Immobile: 0.45",
                    "_PhysBone_Immobile_type: 1",
                    "_PhysBone_Limit_Angle: 22",
                    "_PhysBone_Collision_Radius: 5.0",
                ]
            ),
            encoding="utf-8",
        )
        marsh_asset_guid = "99999999000000001111111122222222"
        (pb_root / "CustomMarshPreset.asset.meta").write_text(
            f"fileFormatVersion: 2\nguid: {marsh_asset_guid}\n",
            encoding="utf-8",
        )
        marsh_prefab = pb_root / "Marshmallow_PB.prefab"
        marsh_prefab.write_text(
            "\n".join(
                [
                    "%YAML 1.1",
                    "--- !u!1 &50",
                    "GameObject:",
                    "  m_Name: Marshmallow_PB",
                    "  m_IsActive: 1",
                    "--- !u!4 &51",
                    "Transform:",
                    "  m_GameObject: {fileID: 50}",
                    "  m_Father: {fileID: 0}",
                    "--- !u!114 &52",
                    "MonoBehaviour:",
                    "  m_GameObject: {fileID: 50}",
                    "  m_Enabled: 1",
                    "  _marshmallowPBEnabled: 1",
                    "  _index: 0",
                    "  _PhysBone_index: 0",
                    "  _PhysBone_Pull: 0.20",
                    "  _PhysBone_Momentum: 0.40",
                    "  _presets:",
                    "  - {fileID: 11400000, guid: 00000000000000000000000000000000, type: 2}",
                    "  _pbpresets:",
                    "  - {fileID: 11400000, guid: 00000000000000000000000000000000, type: 2}",
                ]
            ),
            encoding="utf-8",
        )
        marsh_prefab_guid = "aaaaaaaaaaaaaaaa22222222bbbbbbbb"
        (pb_root / "Marshmallow_PB.prefab.meta").write_text(
            f"fileFormatVersion: 2\nguid: {marsh_prefab_guid}\n",
            encoding="utf-8",
        )

        pb_scene = pb_assets_root / "SynthPhysBones.unity"
        pb_scene.write_text(
            "\n".join(
                [
                    "%YAML 1.1",
                    "%TAG !u! tag:unity3d.com,2011:",
                    "--- !u!1 &1000",
                    "GameObject:",
                    "  m_Name: SynthPBAvatar",
                    "  m_IsActive: 1",
                    "--- !u!4 &1001",
                    "Transform:",
                    "  m_GameObject: {fileID: 1000}",
                    "  m_Father: {fileID: 0}",
                    "--- !u!1 &1010",
                    "GameObject:",
                    "  m_Name: Head",
                    "  m_IsActive: 1",
                    "--- !u!4 &1011",
                    "Transform:",
                    "  m_GameObject: {fileID: 1010}",
                    "  m_Father: {fileID: 1001}",
                    "--- !u!1 &1020",
                    "GameObject:",
                    "  m_Name: Ear_L",
                    "  m_IsActive: 1",
                    "--- !u!4 &1021",
                    "Transform:",
                    "  m_GameObject: {fileID: 1020}",
                    "  m_Father: {fileID: 1011}",
                    "--- !u!1 &1022",
                    "GameObject:",
                    "  m_Name: Ear_L_Tip",
                    "  m_IsActive: 1",
                    "--- !u!4 &1023",
                    "Transform:",
                    "  m_GameObject: {fileID: 1022}",
                    "  m_Father: {fileID: 1021}",
                    "--- !u!1 &1030",
                    "GameObject:",
                    "  m_Name: InactiveGimmick",
                    "  m_IsActive: 0",
                    "--- !u!4 &1031",
                    "Transform:",
                    "  m_GameObject: {fileID: 1030}",
                    "  m_Father: {fileID: 1011}",
                    "--- !u!114 &1100",
                    "MonoBehaviour:",
                    "  m_GameObject: {fileID: 1020}",
                    "  m_Enabled: 1",
                    f"  m_Script: {{fileID: {physbone_helper.VRCHAT_PHYSBONE_CLASS_FILE_ID}, guid: {physbone_helper.VRCHAT_PHYSBONE_SCRIPT_GUID}, type: 3}}",
                    "  rootTransform: {fileID: 1021}",
                    "  pull: 0.12",
                    "  spring: 0.65",
                    "  stiffness: 0.25",
                    "  gravity: 0.05",
                    "  gravityFalloff: 0.15",
                    "  immobile: 0.35",
                    "  maxAngleX: 48",
                    "  radius: 0.03",
                    "--- !u!114 &1101",
                    "MonoBehaviour:",
                    "  m_GameObject: {fileID: 1030}",
                    "  m_Enabled: 1",
                    f"  m_Script: {{fileID: {physbone_helper.VRCHAT_PHYSBONE_CLASS_FILE_ID}, guid: {physbone_helper.VRCHAT_PHYSBONE_SCRIPT_GUID}, type: 3}}",
                    "  rootTransform: {fileID: 1031}",
                    "  pull: 0.99",
                    "--- !u!1001 &2000",
                    "PrefabInstance:",
                    "  m_Modification:",
                    "    m_TransformParent: {fileID: 1001}",
                    "    m_Modifications:",
                    f"    - target: {{fileID: 52, guid: {marsh_prefab_guid}, type: 3}}",
                    "      propertyPath: _PhysBone_index",
                    "      value: 0",
                    f"    - target: {{fileID: 52, guid: {marsh_prefab_guid}, type: 3}}",
                    "      propertyPath: _PhysBone_Collision_Radius",
                    "      value: 5.0",
                    f"    - target: {{fileID: 52, guid: {marsh_prefab_guid}, type: 3}}",
                    "      propertyPath: _pbpresets.Array.data[0]",
                    f"      objectReference: {{fileID: 11400000, guid: {marsh_asset_guid}, type: 2}}",
                    f"  m_SourcePrefab: {{fileID: 100100000, guid: {marsh_prefab_guid}, type: 3}}",
                ]
            ),
            encoding="utf-8",
        )

        extracted_default_pb = physbone_helper.extract_unity_scene_physbones(
            pb_scene,
            avatar_name="SynthPBAvatar",
            unity_assets_root=pb_assets_root,
        )
        extracted_pb = physbone_helper.extract_unity_scene_physbones(
            pb_scene,
            avatar_name="SynthPBAvatar",
            unity_assets_root=pb_assets_root,
            include_marshmallow_pb=True,
        )
        extracted_chain_roots = {
            chain_rec.get("root_bone") for chain_rec in extracted_pb.get("chains", [])
        }
        default_chain_roots = {
            chain_rec.get("root_bone") for chain_rec in extracted_default_pb.get("chains", [])
        }
        marsh_breasts = extracted_pb.get("marshmallow_breasts", [])
        ear_chain = next(
            (item for item in extracted_pb.get("chains", []) if item.get("root_bone") == "Ear_L"),
            {},
        )
        pb_extract_ok = (
            extracted_default_pb.get("loaded", False)
            and "Ear_L" in default_chain_roots
            and len(extracted_default_pb.get("marshmallow_breasts", [])) == 0
            and extracted_pb.get("loaded", False)
            and "Ear_L" in extracted_chain_roots
            and "InactiveGimmick" not in extracted_chain_roots
            and abs(float(ear_chain.get("pull", 0.0)) - 0.12) < 1e-4
            and abs(float(ear_chain.get("spring", 0.0)) - 0.65) < 1e-4
            and len(marsh_breasts) >= 2
            and abs(float(marsh_breasts[0].get("pull", 0.0)) - 0.08) < 1e-4
            and abs(float(marsh_breasts[0].get("radius", 0.0)) - 0.05) < 1e-4
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.physbones_unity_extract"),
            pb_extract_ok,
            f"default_marsh=0, chains={len(extracted_pb.get('chains', []))}, marsh={len(marsh_breasts)}",
        )

        excessive_spokes = []
        for idx_num in range(45):
            excessive_spokes.append(
                {
                    "chain_key": f"skirt_strip_{idx_num:02d}",
                    "root_bone": f"SkirtRoot_{idx_num:02d}",
                    "spoke_bones": [
                        f"Skirt_{idx_num:02d}_0",
                        f"Skirt_{idx_num:02d}_1",
                        f"Skirt_{idx_num:02d}_2",
                    ],
                    "all_descendants": [
                        f"Skirt_{idx_num:02d}_0",
                        f"Skirt_{idx_num:02d}_1",
                        f"Skirt_{idx_num:02d}_2",
                    ],
                    "parent_bone": "SKEL_Pelvis",
                    "parent_bone_tag": physbone_helper.SKEL_PELVIS_TAG,
                    "pull": 0.25,
                    "spring": 0.55,
                    "stiffness": 0.30,
                    "gravity": 0.20,
                }
            )
        packed_budget = physbone_helper.pack_physbone_chains_to_gtav_budget(
            excessive_spokes,
            gtav_prefix="PB_Tst",
            max_custom_bones=physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED,
        )
        packed_bones = list(packed_budget.get("custom_bones", []))
        packed_tags = [
            physbone_helper.compute_gtav_bone_tag(bone_item) for bone_item in packed_bones
        ]
        budget_pack_ok = (
            0 < len(packed_bones) <= physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED
            and len(packed_tags) == len(set(packed_tags))
            and not (set(packed_tags) & set(physbone_helper.PARENT_BONE_TAGS.values()))
            and len(packed_budget.get("chains", {})) >= 4
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.physbones_budget_pack"),
            budget_pack_ok,
            f"bones={len(packed_bones)}/{physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED}, chains={len(packed_budget.get('chains', {}))}",
        )

        pb_roundtrip_cfg = pb_root / "synth_physbones.cfg"
        saved_pb_cfg = physbone_helper.save_physbone_config(
            pb_roundtrip_cfg,
            packed_budget["chains"],
            metadata={"avatar": "SynthAvatar", "character": "franklin", "slot": "player_one"},
            bone_mapping=packed_budget["bone_mapping"],
        )
        reloaded_pb_cfg = physbone_helper.load_physbone_config(saved_pb_cfg)
        built_specs, built_parents, built_bones, _built_map_ci = (
            physbone_helper.build_chain_specs_from_config(reloaded_pb_cfg)
        )
        resolved_pb_cfg = physbone_helper.resolve_character_physbones(
            {
                "avatar_id": "shinano_casual",
                "physbones_source": "auto",
                "physbones_cfg": str(saved_pb_cfg),
                "unity_scene": "",
                "protagonist": "franklin",
                "ped_name": "player_one",
            },
        )
        # Regression check: skewed limit_axis (> node max_angle) causes idle radial flare,
        # whereas clamping limit_axis within compute_safe_local_limit_axis bounds keeps
        # standing idle displacement near zero.
        import math as std_math

        rel_child_vec = (0.06, 0.14, -0.04)
        child_len = std_math.sqrt(sum(val * val for val in rel_child_vec))
        child_dir = tuple(val / child_len for val in rel_child_vec)
        # Rotate child_dir in XZ/XY plane by 65 deg (exceeds 42 deg cone) vs 32 deg (safe)
        perp_raw = (child_dir[2], 0.0, -child_dir[0])
        perp_len = std_math.sqrt(sum(val * val for val in perp_raw))
        perp_dir = tuple(val / perp_len for val in perp_raw)

        flare_rad = std_math.radians(65.0)
        flared_axis = tuple(
            std_math.cos(flare_rad) * base_v + std_math.sin(flare_rad) * ort_v
            for base_v, ort_v in zip(child_dir, perp_dir)
        )
        safe_rad = std_math.radians(min(42.0 * 0.78, max(0.0, 42.0 - 5.0)))
        safe_axis = tuple(
            std_math.cos(safe_rad) * base_v + std_math.sin(safe_rad) * ort_v
            for base_v, ort_v in zip(child_dir, perp_dir)
        )
        skirt_cfg = {
            "pull": 0.25,
            "spring": 0.55,
            "stiffness": 0.30,
            "gravity": 0.10,
            "gravity_falloff": 1.0,
            "immobile": 0.0,
            "limit_type": 3,
            "max_angle_x": 60.0,
            "max_angle_x_curve": [(0.0, 0.7), (1.0, 1.0)],
        }
        rest_pos_pair = [(0.0, 0.0, 0.0), rel_child_vec]
        rest_rot_pair = [(0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 1.0)]

        flared_sim = physbone_helper.PhysBoneChainSimulator(
            rest_local_positions=rest_pos_pair,
            rest_local_rotations=rest_rot_pair,
            config=skirt_cfg,
            limit_axes_local=[flared_axis, flared_axis],
        )
        flared_sim.reset((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
        flared_pos = []
        for _ in range(60):
            flared_pos, _ = flared_sim.step((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), 1.0 / 60.0)
        flared_drift_mm = (
            std_math.sqrt(
                sum((sim_v - rest_v) ** 2 for sim_v, rest_v in zip(flared_pos[1], rel_child_vec))
            )
            * 1000.0
        )

        safe_sim = physbone_helper.PhysBoneChainSimulator(
            rest_local_positions=rest_pos_pair,
            rest_local_rotations=rest_rot_pair,
            config=skirt_cfg,
            limit_axes_local=[safe_axis, safe_axis],
        )
        safe_sim.reset((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
        safe_pos = []
        for _ in range(60):
            safe_pos, _ = safe_sim.step((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), 1.0 / 60.0)
        idle_drift_mm = (
            std_math.sqrt(
                sum((sim_v - rest_v) ** 2 for sim_v, rest_v in zip(safe_pos[1], rel_child_vec))
            )
            * 1000.0
        )
        safe_cone_ok = (
            callable(getattr(physbone_helper, "compute_safe_local_limit_axis", None))
            and flared_drift_mm > 30.0
            and idle_drift_mm < 0.5
        )

        miltina_cfg_file = PROJECT_ROOT_DIR / "configs" / "miltina_maid_physbones.cfg"
        casual_cfg_file = PROJECT_ROOT_DIR / "configs" / "shinano_casual_physbones.cfg"
        miltina_std_resolved = physbone_helper.resolve_character_physbones(
            {
                "avatar_id": "miltina_maid",
                "physbones_source": "cfg",
                "physbones_cfg": str(miltina_cfg_file),
                "unity_scene": "",
                "protagonist": "trevor",
                "ped_name": "player_two",
            },
        )
        miltina_marsh_resolved = physbone_helper.resolve_character_physbones(
            {
                "avatar_id": "miltina_maid",
                "physbones_source": "cfg",
                "physbones_cfg": str(miltina_cfg_file),
                "physbones_marshmallow": "true",
                "unity_scene": "",
                "protagonist": "trevor",
                "ped_name": "player_two",
            },
        )
        casual_std_resolved = physbone_helper.resolve_character_physbones(
            {
                "avatar_id": "shinano_casual",
                "physbones_source": "cfg",
                "physbones_cfg": str(casual_cfg_file),
                "unity_scene": "",
                "protagonist": "franklin",
                "ped_name": "player_one",
            },
        )
        casual_marsh_resolved = physbone_helper.resolve_character_physbones(
            {
                "avatar_id": "shinano_casual",
                "physbones_source": "cfg",
                "physbones_cfg": str(casual_cfg_file),
                "unity_scene": "",
                "protagonist": "franklin",
                "ped_name": "player_one",
            },
            override_marshmallow=True,
        )
        marshmallow_param_ok = (
            not miltina_std_resolved.get("marshmallow_pb")
            and len(miltina_std_resolved.get("chain_specs", [])) == 25
            and len(miltina_std_resolved.get("custom_bones", [])) == 58
            and miltina_marsh_resolved.get("marshmallow_pb") is True
            and len(miltina_marsh_resolved.get("chain_specs", [])) == 27
            and len(miltina_marsh_resolved.get("custom_bones", [])) == 62
            and not casual_std_resolved.get("marshmallow_pb")
            and abs(float(casual_std_resolved["chains"]["breast.L"]["max_angle_x"]) - 10.0) < 1e-4
            and casual_marsh_resolved.get("marshmallow_pb") is True
            and abs(float(casual_marsh_resolved["chains"]["breast.L"]["max_angle_x"]) - 35.0) < 1e-4
        )

        pb_roundtrip_ok = (
            len(built_specs) == len(packed_budget["chains"])
            and len(built_bones) == len(packed_bones)
            and bool(built_parents)
            and resolved_pb_cfg.get("source_used") == "cfg"
            and len(resolved_pb_cfg.get("custom_bones", [])) == len(packed_bones)
            and safe_cone_ok
            and marshmallow_param_ok
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.physbones_cfg_roundtrip"),
            pb_roundtrip_ok,
            (
                f"specs={len(built_specs)}, bones={len(built_bones)}, "
                f"source={resolved_pb_cfg.get('source_used')}, "
                f"flared_mm={flared_drift_mm:.1f}, idle_mm={idle_drift_mm:.3f}"
            ),
        )

        # Verify PhysBone prioritization tiers:
        # 1) All 3 built-in avatar configs fit within RAGE <= 63 custom bones with 0 chains dropped.
        # 2) Any custom avatar fitting within <= 63 custom bones keeps 100% of chains.
        # 3) Overloaded custom avatar (> 63 custom bones) preserves Tier 1-2 essential bones
        #    symmetrically, discards lower-tier non-essential props (including Earring/HairPin),
        #    and re-binds discarded vertices statically onto their rigid parent_bone.
        michael_cfg_file = PROJECT_ROOT_DIR / "configs" / "michael_neko_mimi_physbones.cfg"
        michael_std_resolved = physbone_helper.resolve_character_physbones(
            {
                "avatar_id": "shinano_er",
                "physbones_source": "cfg",
                "physbones_cfg": str(michael_cfg_file),
                "unity_scene": "",
                "protagonist": "michael",
                "ped_name": "player_zero",
            },
        )
        builtin_zero_drops_ok = (
            len(michael_std_resolved.get("chain_specs", [])) == 30
            and len(michael_std_resolved.get("custom_bones", [])) == 62
            and len(michael_std_resolved.get("discarded_chains", [])) == 0
            and len(casual_std_resolved.get("chain_specs", [])) == 24
            and len(casual_std_resolved.get("custom_bones", [])) == 62
            and len(casual_std_resolved.get("discarded_chains", [])) == 0
            and len(miltina_std_resolved.get("discarded_chains", [])) == 0
            and michael_std_resolved.get("priority_report", {}).get("within_budget") is True
        )

        def _make_spoke(stem_label: str, parent_nm: str, seg_cnt: int = 3) -> Dict[str, Any]:
            bone_seq = [f"{stem_label}_{seg_i}" for seg_i in range(seg_cnt)]
            return {
                "chain_key": stem_label.lower(),
                "root_bone": bone_seq[0],
                "spoke_bones": bone_seq,
                "all_descendants": list(bone_seq),
                "parent_bone": parent_nm,
                "parent_bone_tag": physbone_helper.PARENT_BONE_TAGS[parent_nm],
                "pull": 0.20,
                "spring": 0.50,
                "stiffness": 0.25,
                "gravity": 0.15,
            }

        light_custom_spokes = [
            _make_spoke("CatEar.L", "SKEL_Head", 3),
            _make_spoke("CatEar.R", "SKEL_Head", 3),
            _make_spoke("FoxTail", "SKEL_Pelvis", 3),
            _make_spoke("Front_Hair", "SKEL_Head", 3),
            _make_spoke("Skirt_F", "SKEL_Pelvis", 3),
            _make_spoke("Hair_Ribbon", "SKEL_Head", 2),
            _make_spoke("Earring_L", "SKEL_Head", 2),
            _make_spoke("Keychain_01", "SKEL_Pelvis", 2),
            _make_spoke("Backpack_Bag", "SKEL_Spine2", 2),
        ]
        packed_light_custom = physbone_helper.pack_physbone_chains_to_gtav_budget(
            light_custom_spokes,
            gtav_prefix="PB_Lit",
            max_custom_bones=physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED,
        )
        light_keeps_all_ok = (
            len(packed_light_custom.get("chains", {})) == len(light_custom_spokes)
            and len(packed_light_custom.get("discarded_chains", [])) == 0
            and len(packed_light_custom.get("custom_bones", [])) <= physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED
            and len(packed_light_custom["chains"]["catear_l"]["chain_bones"]) == 3
            and len(packed_light_custom["chains"]["catear_r"]["chain_bones"]) == 3
        )

        heavy_custom_spokes = [
            _make_spoke("CatEar.L", "SKEL_Head", 3),
            _make_spoke("CatEar.R", "SKEL_Head", 3),
            _make_spoke("TwinTail.L", "SKEL_Head", 3),
            _make_spoke("TwinTail.R", "SKEL_Head", 3),
            _make_spoke("Bang_Center", "SKEL_Head", 3),
            _make_spoke("Side_Hair.L", "SKEL_Head", 3),
            _make_spoke("Side_Hair.R", "SKEL_Head", 3),
            _make_spoke("Back_Hair.L", "SKEL_Head", 3),
            _make_spoke("Back_Hair.R", "SKEL_Head", 3),
            _make_spoke("FoxTail", "SKEL_Pelvis", 3),
            _make_spoke("Skirt_Front_01", "SKEL_Pelvis", 3),
            _make_spoke("Skirt_Front_02", "SKEL_Pelvis", 3),
            _make_spoke("Skirt_Side_01", "SKEL_Pelvis", 3),
            _make_spoke("Skirt_Side_02", "SKEL_Pelvis", 3),
            _make_spoke("Skirt_Back_01", "SKEL_Pelvis", 3),
            _make_spoke("Skirt_Back_02", "SKEL_Pelvis", 3),
            _make_spoke("Cape_Back", "SKEL_Spine3", 3),
            _make_spoke("Scarf_Front", "SKEL_Spine3", 3),
            _make_spoke("Sleeve.L", "SKEL_L_UpperArm", 3),
            _make_spoke("Sleeve.R", "SKEL_R_UpperArm", 3),
            _make_spoke("Hair_Ribbon.L", "SKEL_Head", 3),
            _make_spoke("Hair_Ribbon.R", "SKEL_Head", 3),
            _make_spoke("Chest_Bow", "SKEL_Spine2", 3),
            _make_spoke("Veil_Left.L", "SKEL_Head", 3),
            _make_spoke("Veil_Left.R", "SKEL_Head", 3),
            _make_spoke("Hood_Flap_Back", "SKEL_Spine3", 3),
            _make_spoke("Skirt_Frill_01", "SKEL_Pelvis", 2),
            _make_spoke("Skirt_Frill_02", "SKEL_Pelvis", 2),
            _make_spoke("Waist_Sash_01", "SKEL_Pelvis", 2),
            _make_spoke("Waist_Belt_01", "SKEL_Pelvis", 2),
            _make_spoke("Waist_Belt_02", "SKEL_Pelvis", 2),
            _make_spoke("Thigh_Garter.L", "SKEL_L_Thigh", 2),
            _make_spoke("Thigh_Garter.R", "SKEL_R_Thigh", 2),
            _make_spoke("Cheek_Soft.L", "SKEL_Head", 2),
            _make_spoke("Cheek_Soft.R", "SKEL_Head", 2),
            _make_spoke("Earring_Gem.L", "SKEL_Head", 2),
            _make_spoke("Earring_Gem.R", "SKEL_Head", 2),
            _make_spoke("Necklace_Bell", "SKEL_Spine3", 2),
            _make_spoke("Belly_Soft", "SKEL_Spine0", 2),
            _make_spoke("HairPin_Star", "SKEL_Head", 2),
            _make_spoke("Backpack_Bag", "SKEL_Spine2", 2),
            _make_spoke("Keychain_Cat", "SKEL_Pelvis", 2),
            _make_spoke("Keychain_Coin", "SKEL_Pelvis", 2),
            _make_spoke("Plushie_Mascot", "SKEL_Spine1", 2),
            _make_spoke("PocketWatch_Side", "SKEL_Pelvis", 2),
            _make_spoke("NameBadge_Pin", "SKEL_Spine3", 2),
            _make_spoke("Bracelet_Gem.L", "SKEL_L_UpperArm", 2),
            _make_spoke("Bracelet_Gem.R", "SKEL_R_UpperArm", 2),
        ]
        packed_heavy_custom = physbone_helper.pack_physbone_chains_to_gtav_budget(
            heavy_custom_spokes,
            gtav_prefix="PB_Hvy",
            max_custom_bones=physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED,
        )
        heavy_chains = packed_heavy_custom.get("chains", {})
        heavy_bones = list(packed_heavy_custom.get("custom_bones", []))
        heavy_tags = [physbone_helper.compute_gtav_bone_tag(bone_item) for bone_item in heavy_bones]
        heavy_bmap = packed_heavy_custom.get("bone_mapping", {})
        heavy_discarded_keys = {
            item["chain_key"] for item in packed_heavy_custom.get("discarded_chains", [])
        }
        priority_heavy_ok = (
            0 < len(heavy_bones) <= physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED
            and len(heavy_tags) == len(set(heavy_tags))
            and not (set(heavy_tags) & set(physbone_helper.PARENT_BONE_TAGS.values()))
            and "catear_l" in heavy_chains
            and "catear_r" in heavy_chains
            and "twintail_l" in heavy_chains
            and "twintail_r" in heavy_chains
            and "foxtail" in heavy_chains
            and "bang_center" in heavy_chains
            and "skirt_front_01" in heavy_chains
            and len(heavy_chains["catear_l"]["chain_bones"])
            == len(heavy_chains["catear_r"]["chain_bones"])
            and "keychain_cat" in heavy_discarded_keys
            and "backpack_bag" in heavy_discarded_keys
            and "hairpin_star" in heavy_discarded_keys
            and "earring_gem_l" in heavy_discarded_keys
            and "earring_gem_r" in heavy_discarded_keys
            and heavy_bmap.get("earring_gem.l_0") == "SKEL_Head"
            and heavy_bmap.get("hairpin_star_0") == "SKEL_Head"
            and heavy_bmap.get("backpack_bag_0") == "SKEL_Spine2"
            and heavy_bmap.get("keychain_cat_0") == "SKEL_Pelvis"
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.physbones_priority_pack"),
            bool(builtin_zero_drops_ok and light_keeps_all_ok and priority_heavy_ok),
            (
                f"builtin_drops=0, light_kept={len(packed_light_custom.get('chains', {}))}/{len(light_custom_spokes)}, "
                f"heavy_kept={len(heavy_chains)}/{len(heavy_custom_spokes)} ({len(heavy_bones)}/63 bones, "
                f"discarded={len(heavy_discarded_keys)})"
            ),
        )

        # Verify automatic orphaned/unused old-dress PhysBone removal during Unity/FBX import
        import struct as fbx_struct

        def _pack_fbx_prop(prop_val: Any) -> bytes:
            if isinstance(prop_val, int):
                return b"L" + fbx_struct.pack("<q", prop_val)
            if isinstance(prop_val, str):
                enc_txt = prop_val.encode("utf-8")
                return b"S" + fbx_struct.pack("<I", len(enc_txt)) + enc_txt
            if isinstance(prop_val, list):
                arr_bytes = b"".join(fbx_struct.pack("<d", float(num_val)) for num_val in prop_val)
                return b"d" + fbx_struct.pack("<III", len(prop_val), 0, len(arr_bytes)) + arr_bytes
            raise TypeError(f"Unsupported FBX prop: {type(prop_val)}")

        def _build_fbx_node(
            node_name: str,
            node_props: Sequence[Any],
            child_nodes: Sequence[bytes],
            start_offset: int,
        ) -> bytes:
            prop_blob = b"".join(_pack_fbx_prop(item_val) for item_val in node_props)
            name_bytes = node_name.encode("utf-8")
            body_start = start_offset + 13 + len(name_bytes) + len(prop_blob)
            children_blob = b"".join(child_nodes)
            if child_nodes:
                children_blob += b"\x00" * 13
            end_offset = body_start + len(children_blob)
            hdr_bytes = fbx_struct.pack("<IIIB", end_offset, len(node_props), len(prop_blob), len(name_bytes))
            return hdr_bytes + name_bytes + prop_blob + children_blob

        def _write_minimal_test_fbx(
            fbx_out_path: Path,
            mesh_to_bones: Dict[str, List[str]],
            all_bone_names: List[str],
        ) -> None:
            uid_seq = [1000]

            def _next_id() -> int:
                uid_seq[0] += 1
                return uid_seq[0]

            cursor_pos = 27
            obj_nodes_meta: List[Tuple[str, List[Any], List[Tuple[str, List[Any]]]]] = []
            conn_pairs: List[Tuple[int, int]] = []
            bone_id_map: Dict[str, int] = {}

            for bone_nm in all_bone_names:
                bone_uid = _next_id()
                bone_id_map[bone_nm] = bone_uid
                obj_nodes_meta.append(("Model", [bone_uid, f"{bone_nm}\x00\x01Model", "LimbNode"], []))

            for mesh_nm, weighted_names in mesh_to_bones.items():
                mesh_uid = _next_id()
                geom_uid = _next_id()
                skin_uid = _next_id()
                obj_nodes_meta.append(("Model", [mesh_uid, f"{mesh_nm}\x00\x01Model", "Mesh"], []))
                obj_nodes_meta.append(("Geometry", [geom_uid, f"{mesh_nm}\x00\x01Geometry", "Mesh"], []))
                obj_nodes_meta.append(("Deformer", [skin_uid, f"{mesh_nm}_Skin\x00\x01Deformer", "Skin"], []))
                conn_pairs.append((geom_uid, mesh_uid))
                conn_pairs.append((skin_uid, geom_uid))
                for w_bone_nm in weighted_names:
                    cl_uid = _next_id()
                    obj_nodes_meta.append(
                        (
                            "Deformer",
                            [cl_uid, f"Cluster_{w_bone_nm}\x00\x01Deformer", "Cluster"],
                            [("Weights", [[1.0]])],
                        )
                    )
                    conn_pairs.append((cl_uid, skin_uid))
                    conn_pairs.append((bone_id_map[w_bone_nm], cl_uid))

            obj_prop_cursor = cursor_pos + 13 + len(b"Objects")
            compiled_obj_children: List[bytes] = []
            for o_name, o_props, o_kids in obj_nodes_meta:
                prop_sz = sum(len(_pack_fbx_prop(prop_val)) for prop_val in o_props)
                kid_cursor = obj_prop_cursor + 13 + len(o_name.encode("utf-8")) + prop_sz
                compiled_kids: List[bytes] = []
                for k_name, k_props in o_kids:
                    k_bytes = _build_fbx_node(k_name, k_props, [], kid_cursor)
                    compiled_kids.append(k_bytes)
                    kid_cursor += len(k_bytes)
                node_bytes = _build_fbx_node(o_name, o_props, compiled_kids, obj_prop_cursor)
                compiled_obj_children.append(node_bytes)
                obj_prop_cursor += len(node_bytes)
            objects_block = _build_fbx_node("Objects", [], compiled_obj_children, cursor_pos)
            cursor_pos += len(objects_block)

            conn_cursor = cursor_pos + 13 + len(b"Connections")
            compiled_conns: List[bytes] = []
            for src_uid, dst_uid in conn_pairs:
                c_bytes = _build_fbx_node("C", ["OO", src_uid, dst_uid], [], conn_cursor)
                compiled_conns.append(c_bytes)
                conn_cursor += len(c_bytes)
            conns_block = _build_fbx_node("Connections", [], compiled_conns, cursor_pos)
            file_bytes = (
                b"Kaydara FBX Binary  \x00\x1a\x00"
                + fbx_struct.pack("<I", 7400)
                + objects_block
                + conns_block
                + (b"\x00" * 13)
            )
            fbx_out_path.write_bytes(file_bytes)

        orphan_root = pb_root / "orphan_test"
        orphan_root.mkdir(parents=True, exist_ok=True)
        base_fbx_p = orphan_root / "AvatarWithOldDress.fbx"
        new_dress_fbx_p = orphan_root / "CustomNewDress.fbx"
        _write_minimal_test_fbx(
            base_fbx_p,
            {
                "Body": ["Hips", "Ear_L", "Ear_L_Tip"],
                "OldDress_Mesh": ["OldSkirt_0", "OldSkirt_1"],
            },
            ["Hips", "Ear_L", "Ear_L_Tip", "OldSkirt_0", "OldSkirt_1"],
        )
        _write_minimal_test_fbx(
            new_dress_fbx_p,
            {"NewDress_Mesh": ["NewSkirt_0", "NewSkirt_1"]},
            ["NewSkirt_0", "NewSkirt_1"],
        )
        base_fbx_guid = "11112222333344445555666677778888"
        new_fbx_guid = "99990000aaaabbbbccccddddeeeeffff"
        (orphan_root / "AvatarWithOldDress.fbx.meta").write_text(
            f"fileFormatVersion: 2\nguid: {base_fbx_guid}\n",
            encoding="utf-8",
        )
        (orphan_root / "CustomNewDress.fbx.meta").write_text(
            f"fileFormatVersion: 2\nguid: {new_fbx_guid}\n",
            encoding="utf-8",
        )

        orphan_scene_p = orphan_root / "OrphanDressTest.unity"
        orphan_scene_p.write_text(
            "\n".join(
                [
                    "%YAML 1.1",
                    "%TAG !u! tag:unity3d.com,2011:",
                    "--- !u!1 &100",
                    "GameObject:",
                    "  m_Name: OrphanTestAvatar",
                    "  m_IsActive: 1",
                    "--- !u!4 &101",
                    "Transform:",
                    "  m_GameObject: {fileID: 100}",
                    "  m_Father: {fileID: 0}",
                    "--- !u!1 &110",
                    "GameObject:",
                    "  m_Name: Body",
                    "  m_IsActive: 1",
                    "--- !u!4 &111",
                    "Transform:",
                    "  m_GameObject: {fileID: 110}",
                    "  m_Father: {fileID: 101}",
                    "--- !u!137 &112",
                    "SkinnedMeshRenderer:",
                    "  m_GameObject: {fileID: 110}",
                    "  m_Enabled: 1",
                    f"  m_Mesh: {{fileID: 4300000, guid: {base_fbx_guid}, type: 3}}",
                    "--- !u!1 &120",
                    "GameObject:",
                    "  m_Name: OldDress_Mesh",
                    "  m_IsActive: 0",
                    "--- !u!4 &121",
                    "Transform:",
                    "  m_GameObject: {fileID: 120}",
                    "  m_Father: {fileID: 101}",
                    "--- !u!137 &122",
                    "SkinnedMeshRenderer:",
                    "  m_GameObject: {fileID: 120}",
                    "  m_Enabled: 0",
                    f"  m_Mesh: {{fileID: 4300002, guid: {base_fbx_guid}, type: 3}}",
                    "--- !u!1 &130",
                    "GameObject:",
                    "  m_Name: NewDress_Mesh",
                    "  m_IsActive: 1",
                    "--- !u!4 &131",
                    "Transform:",
                    "  m_GameObject: {fileID: 130}",
                    "  m_Father: {fileID: 101}",
                    "--- !u!137 &132",
                    "SkinnedMeshRenderer:",
                    "  m_GameObject: {fileID: 130}",
                    "  m_Enabled: 1",
                    f"  m_Mesh: {{fileID: 4300000, guid: {new_fbx_guid}, type: 3}}",
                    "--- !u!1 &200",
                    "GameObject:",
                    "  m_Name: Ear_L",
                    "  m_IsActive: 1",
                    "--- !u!4 &201",
                    "Transform:",
                    "  m_GameObject: {fileID: 200}",
                    "  m_Father: {fileID: 101}",
                    "--- !u!1 &202",
                    "GameObject:",
                    "  m_Name: Ear_L_Tip",
                    "  m_IsActive: 1",
                    "--- !u!4 &203",
                    "Transform:",
                    "  m_GameObject: {fileID: 202}",
                    "  m_Father: {fileID: 201}",
                    "--- !u!1 &210",
                    "GameObject:",
                    "  m_Name: OldSkirt_0",
                    "  m_IsActive: 1",
                    "--- !u!4 &211",
                    "Transform:",
                    "  m_GameObject: {fileID: 210}",
                    "  m_Father: {fileID: 101}",
                    "--- !u!1 &212",
                    "GameObject:",
                    "  m_Name: OldSkirt_1",
                    "  m_IsActive: 1",
                    "--- !u!4 &213",
                    "Transform:",
                    "  m_GameObject: {fileID: 212}",
                    "  m_Father: {fileID: 211}",
                    "--- !u!1 &220",
                    "GameObject:",
                    "  m_Name: NewSkirt_0",
                    "  m_IsActive: 1",
                    "--- !u!4 &221",
                    "Transform:",
                    "  m_GameObject: {fileID: 220}",
                    "  m_Father: {fileID: 101}",
                    "--- !u!1 &222",
                    "GameObject:",
                    "  m_Name: NewSkirt_1",
                    "  m_IsActive: 1",
                    "--- !u!4 &223",
                    "Transform:",
                    "  m_GameObject: {fileID: 222}",
                    "  m_Father: {fileID: 221}",
                    "--- !u!1 &230",
                    "GameObject:",
                    "  m_Name: OldDress_DisabledRoot",
                    "  m_IsActive: 0",
                    "--- !u!4 &231",
                    "Transform:",
                    "  m_GameObject: {fileID: 230}",
                    "  m_Father: {fileID: 101}",
                    "--- !u!1 &240",
                    "GameObject:",
                    "  m_Name: PhysBoneContainer_OldDress",
                    "  m_IsActive: 1",
                    "--- !u!4 &241",
                    "Transform:",
                    "  m_GameObject: {fileID: 240}",
                    "  m_Father: {fileID: 101}",
                    "--- !u!114 &300",
                    "MonoBehaviour:",
                    "  m_GameObject: {fileID: 200}",
                    "  m_Enabled: 1",
                    f"  m_Script: {{fileID: {physbone_helper.VRCHAT_PHYSBONE_CLASS_FILE_ID}, guid: {physbone_helper.VRCHAT_PHYSBONE_SCRIPT_GUID}, type: 3}}",
                    "  rootTransform: {fileID: 201}",
                    "--- !u!114 &301",
                    "MonoBehaviour:",
                    "  m_GameObject: {fileID: 220}",
                    "  m_Enabled: 1",
                    f"  m_Script: {{fileID: {physbone_helper.VRCHAT_PHYSBONE_CLASS_FILE_ID}, guid: {physbone_helper.VRCHAT_PHYSBONE_SCRIPT_GUID}, type: 3}}",
                    "  rootTransform: {fileID: 221}",
                    "--- !u!114 &302",
                    "MonoBehaviour:",
                    "  m_GameObject: {fileID: 240}",
                    "  m_Enabled: 1",
                    f"  m_Script: {{fileID: {physbone_helper.VRCHAT_PHYSBONE_CLASS_FILE_ID}, guid: {physbone_helper.VRCHAT_PHYSBONE_SCRIPT_GUID}, type: 3}}",
                    "  rootTransform: {fileID: 211}",
                    "--- !u!114 &303",
                    "MonoBehaviour:",
                    "  m_GameObject: {fileID: 240}",
                    "  m_Enabled: 1",
                    f"  m_Script: {{fileID: {physbone_helper.VRCHAT_PHYSBONE_CLASS_FILE_ID}, guid: {physbone_helper.VRCHAT_PHYSBONE_SCRIPT_GUID}, type: 3}}",
                    "  rootTransform: {fileID: 999999}",
                    "--- !u!114 &304",
                    "MonoBehaviour:",
                    "  m_GameObject: {fileID: 240}",
                    "  m_Enabled: 1",
                    f"  m_Script: {{fileID: {physbone_helper.VRCHAT_PHYSBONE_CLASS_FILE_ID}, guid: {physbone_helper.VRCHAT_PHYSBONE_SCRIPT_GUID}, type: 3}}",
                    "  rootTransform: {fileID: 231}",
                ]
            ),
            encoding="utf-8",
        )
        orphan_extract = physbone_helper.extract_unity_scene_physbones(
            orphan_scene_p,
            avatar_name="OrphanTestAvatar",
            unity_assets_root=orphan_root,
            fbx_paths=[base_fbx_p, new_dress_fbx_p],
        )
        orphan_kept_roots = {rec["root_bone"] for rec in orphan_extract.get("chains", [])}
        orphan_reasons = {
            item["root_bone"]: item["reason"]
            for item in orphan_extract.get("orphaned_physbones", [])
        }
        pruned_cfg_res = physbone_helper.prune_orphaned_physbone_chains(
            {
                "ear_l": {
                    "source_key": "ear_l",
                    "chain_bones": ["PB_Ear_L_0", "PB_Ear_L_1"],
                    "source_bones": ["Ear_L", "Ear_L_Tip"],
                    "parent_bone": "SKEL_Head",
                },
                "oldskirt_0": {
                    "source_key": "oldskirt_0",
                    "chain_bones": ["PB_OldSkirt_0", "PB_OldSkirt_1"],
                    "source_bones": ["OldSkirt_0", "OldSkirt_1"],
                    "parent_bone": "SKEL_Pelvis",
                },
            },
            active_weighted_bones_ci={"ear_l", "ear_l_tip", "newskirt_0", "newskirt_1"},
            bone_mapping={"oldskirt_0": "PB_OldSkirt_0", "ear_l": "PB_Ear_L_0"},
            disabled_mesh_bones_ci={"oldskirt_0", "oldskirt_1"},
        )
        orphan_cleanup_ok = (
            orphan_kept_roots == {"Ear_L", "NewSkirt_0"}
            and orphan_reasons.get("OldSkirt_0") == "disabled_old_outfit_mesh"
            and orphan_reasons.get("PhysBoneContainer_OldDress") == "dangling_root_transform"
            and orphan_reasons.get("OldDress_DisabledRoot") == "inactive_root_transform"
            and "oldskirt_0" not in pruned_cfg_res["chains"]
            and "ear_l" in pruned_cfg_res["chains"]
            and "oldskirt_0" not in pruned_cfg_res["bone_mapping"]
            and len(pruned_cfg_res["orphaned_physbones"]) == 1
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.physbones_orphan_cleanup"),
            orphan_cleanup_ok,
            (
                f"kept={sorted(orphan_kept_roots)}, "
                f"orphans_removed={len(orphan_reasons)}, cfg_pruned={len(pruned_cfg_res['orphaned_physbones'])}"
            ),
        )

    return suite_passed


def test_avatar_interchangeability() -> bool:
    """Validate 3x3 protagonist <-> VRChat avatar interchangeability matrix offline."""
    import shutil
    import tempfile

    print(f"\n=== {i18n.translate('tests.suite_interchangeability')} ===")
    suite_passed = True

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        example_cfg_path = project_paths.find_project_config_example()
        temp_cfg_path = temp_dir / "vrc2gtav.cfg"
        shutil.copy2(example_cfg_path, temp_cfg_path)
        for subdir_name in (
            "1_Franklin_Shinano_Casual",
            "2_Michael_Shinano_EternalReunion",
            "3_Trevor_Miltina_Maid",
            "configs",
            "scripts",
            "_deploy_tools",
        ):
            (temp_dir / subdir_name).mkdir(parents=True, exist_ok=True)

        previous_env_cfg = os.environ.get(project_paths.CONFIG_ENV_VAR_NAME)
        os.environ[project_paths.CONFIG_ENV_VAR_NAME] = str(temp_cfg_path)
        project_paths.invalidate_config_cache()
        try:
            protagonists = list(project_paths.list_available_protagonists())
            avatars = list(project_paths.list_available_avatars())
            expected_ped_map = {
                "michael": ("player_zero", "uppr_000_u.ydd"),
                "franklin": ("player_one", "uppr_008_u.ydd"),
                "trevor": ("player_two", "uppr_000_u.ydd"),
            }

            matrix_ok = len(protagonists) == 3 and len(avatars) == 3
            isolated_targets = set()
            for prot_key in protagonists:
                expected_ped, expected_ydd = expected_ped_map[prot_key]
                for avatar_id in avatars:
                    resolved_cfg = project_paths.get_character_paths(
                        prot_key, avatar_override=avatar_id
                    )
                    preset_info = project_paths.get_avatar_preset_info(avatar_id)
                    if resolved_cfg["ped_name"] != expected_ped:
                        matrix_ok = False
                    if Path(resolved_cfg["skeleton_yft"]).name != f"{expected_ped}.yft":
                        matrix_ok = False
                    if Path(resolved_cfg["target_model_ydd"]).name != expected_ydd:
                        matrix_ok = False
                    if Path(resolved_cfg["target_yft"]).name != f"{expected_ped}.yft":
                        matrix_ok = False
                    if prot_key != preset_info["default_character"]:
                        if Path(resolved_cfg["exported_models_dir"]).name != expected_ped:
                            matrix_ok = False
                    isolated_targets.add(str(resolved_cfg["target_model_ydd"]))

            if len(isolated_targets) != 9:
                matrix_ok = False

            suite_passed &= print_status_result(
                i18n.translate("tests.interchangeability_config"),
                matrix_ok,
                f"3x3={len(isolated_targets)} targets",
            )

            project_paths.set_protagonist_avatar("michael", "miltina_maid", temp_cfg_path)
            project_paths.set_protagonist_avatar("franklin", "shinano_er", temp_cfg_path)
            project_paths.set_protagonist_avatar("trevor", "shinano_casual", temp_cfg_path)

            import blendshape_helper

            swapped_michael = project_paths.get_character_paths("michael")
            swapped_franklin = project_paths.get_character_paths("franklin")
            swapped_trevor = project_paths.get_character_paths("trevor")
            miltina_preset_cfg = Path(project_paths.get_avatar_paths("miltina_maid")["blendshapes_cfg"])
            presets_ok = (
                swapped_michael["avatar_id"] == "miltina_maid"
                and swapped_michael["ped_name"] == "player_zero"
                and swapped_franklin["avatar_id"] == "shinano_er"
                and swapped_franklin["ped_name"] == "player_one"
                and swapped_trevor["avatar_id"] == "shinano_casual"
                and swapped_trevor["ped_name"] == "player_two"
                and Path(swapped_michael["blendshapes_cfg"]).name == "miltina_blendshapes.cfg"
                and Path(swapped_franklin["blendshapes_cfg"]).name == "shinano_er_blendshapes.cfg"
                and Path(swapped_trevor["blendshapes_cfg"]).name == "shinano_blendshapes.cfg"
                and miltina_preset_cfg.name == "miltina_blendshapes.cfg"
                and blendshape_helper.AVATAR_PRESET_RELATIVE_PATHS["miltina_maid"].endswith(
                    "miltina_blendshapes.cfg"
                )
            )
            suite_passed &= print_status_result(
                i18n.translate("tests.interchangeability_presets"),
                presets_ok,
                "michael->miltina, franklin->er, trevor->casual",
            )
        finally:
            if previous_env_cfg is None:
                os.environ.pop(project_paths.CONFIG_ENV_VAR_NAME, None)
            else:
                os.environ[project_paths.CONFIG_ENV_VAR_NAME] = previous_env_cfg
            project_paths.invalidate_config_cache()

    scripts_root = (
        project_paths.get_scripts_root_dir()
        if project_paths.has_project_config_file()
        else PROJECT_ROOT_DIR / "scripts"
    )
    required_cli_tokens = [
        (scripts_root / "Shinano_Casual_Franklin" / "build_franklin_avatar.py", "--target-character"),
        (scripts_root / "Shinano_Casual_Franklin" / "run_build_franklin.py", "--target-character"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "build_michael_er.py", "--target-character"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "run_build_er.py", "--target-character"),
        (scripts_root / "Miltina_Maid_Trevor" / "build_trevor_miltina.py", "--target-character"),
        (scripts_root / "Miltina_Maid_Trevor" / "run_pipeline.py", "--target-character"),
        (scripts_root / "common_tools" / "apply_characters.py", "--avatar"),
        (scripts_root / "common_tools" / "run_mod_manager.py", "--save-assignment"),
        (scripts_root / "common_tools" / "run_mod_manager.py", "--export-physbones"),
        (scripts_root / "common_tools" / "run_mod_manager.py", "--physbones-source"),
        (scripts_root / "Shinano_Casual_Franklin" / "build_franklin_avatar.py", "--physbones-source"),
        (scripts_root / "Shinano_Casual_Franklin" / "run_build_franklin.py", "--physbones-source"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "build_michael_er.py", "--physbones-source"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "run_build_er.py", "--physbones-source"),
        (scripts_root / "Miltina_Maid_Trevor" / "build_trevor_miltina.py", "--physbones-source"),
        (scripts_root / "Miltina_Maid_Trevor" / "run_pipeline.py", "--physbones-source"),
        (scripts_root / "common_tools" / "run_mod_manager.py", "--physbones-marshmallow"),
        (scripts_root / "Shinano_Casual_Franklin" / "build_franklin_avatar.py", "--physbones-marshmallow"),
        (scripts_root / "Shinano_Casual_Franklin" / "run_build_franklin.py", "--physbones-marshmallow"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "build_michael_er.py", "--physbones-marshmallow"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "run_build_er.py", "--physbones-marshmallow"),
        (scripts_root / "Miltina_Maid_Trevor" / "build_trevor_miltina.py", "--physbones-marshmallow"),
        (scripts_root / "Miltina_Maid_Trevor" / "run_pipeline.py", "--physbones-marshmallow"),
        (scripts_root / "common_tools" / "run_mod_manager.py", "--blood-decals"),
        (scripts_root / "common_tools" / "build_universal_avatar.py", "--blood-decals"),
        (scripts_root / "Shinano_Casual_Franklin" / "build_franklin_avatar.py", "--blood-decals"),
        (scripts_root / "Shinano_Casual_Franklin" / "run_build_franklin.py", "--blood-decals"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "build_michael_er.py", "--blood-decals"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "run_build_er.py", "--blood-decals"),
        (scripts_root / "Miltina_Maid_Trevor" / "build_trevor_miltina.py", "--blood-decals"),
        (scripts_root / "Miltina_Maid_Trevor" / "run_pipeline.py", "--blood-decals"),
        (scripts_root / "common_tools" / "run_mod_manager.py", "--eye-blink"),
        (scripts_root / "common_tools" / "build_universal_avatar.py", "--eye-blink"),
        (scripts_root / "Shinano_Casual_Franklin" / "build_franklin_avatar.py", "--eye-blink"),
        (scripts_root / "Shinano_Casual_Franklin" / "run_build_franklin.py", "--eye-blink"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "build_michael_er.py", "--eye-blink"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "run_build_er.py", "--eye-blink"),
        (scripts_root / "Miltina_Maid_Trevor" / "build_trevor_miltina.py", "--eye-blink"),
        (scripts_root / "Miltina_Maid_Trevor" / "run_pipeline.py", "--eye-blink"),
        (scripts_root / "common_tools" / "run_mod_manager.py", "--eye-blink-strength"),
        (scripts_root / "common_tools" / "build_universal_avatar.py", "--eye-blink-strength"),
        (scripts_root / "Shinano_Casual_Franklin" / "build_franklin_avatar.py", "--eye-blink-strength"),
        (scripts_root / "Shinano_Casual_Franklin" / "run_build_franklin.py", "--eye-blink-strength"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "build_michael_er.py", "--eye-blink-strength"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "run_build_er.py", "--eye-blink-strength"),
        (scripts_root / "Miltina_Maid_Trevor" / "build_trevor_miltina.py", "--eye-blink-strength"),
        (scripts_root / "Miltina_Maid_Trevor" / "run_pipeline.py", "--eye-blink-strength"),
    ]
    builders_ok = all(
        file_path.is_file() and expected_token in file_path.read_text(encoding="utf-8")
        for file_path, expected_token in required_cli_tokens
    )
    suite_passed &= print_status_result(
        i18n.translate("tests.interchangeability_builders"),
        builders_ok,
        f"{len(required_cli_tokens)}/{len(required_cli_tokens)} CLI handlers",
    )
    return suite_passed


def test_custom_unity_hair_support() -> bool:
    """Validate CLI flags, Prefab/PrefabVariant resolution, UDIM remap & tail filtering."""
    print(i18n.translate("tests.sec_custom_hair_title"))
    import tempfile
    import types
    import blender_hair_helper
    import unity_hair_helper
    from PIL import Image

    suite_passed = True
    scripts_root = (
        project_paths.get_scripts_root_dir()
        if project_paths.has_project_config_file()
        else PROJECT_ROOT_DIR / "scripts"
    )
    required_hair_cli_files = [
        scripts_root / "Shinano_Casual_Franklin" / "generate_franklin_atlas.py",
        scripts_root / "Shinano_Casual_Franklin" / "build_franklin_avatar.py",
        scripts_root / "Shinano_Casual_Franklin" / "run_build_franklin.py",
        scripts_root / "Shinano_EternalReunion_Michael" / "generate_er_atlas.py",
        scripts_root / "Shinano_EternalReunion_Michael" / "build_michael_er.py",
        scripts_root / "Shinano_EternalReunion_Michael" / "run_build_er.py",
        scripts_root / "Miltina_Maid_Trevor" / "generate_miltina_atlas.py",
        scripts_root / "Miltina_Maid_Trevor" / "build_trevor_miltina.py",
        scripts_root / "Miltina_Maid_Trevor" / "run_pipeline.py",
        scripts_root / "common_tools" / "run_mod_manager.py",
    ]
    cli_ok = all(
        file_item.is_file() and '"--hair"' in file_item.read_text(encoding="utf-8")
        for file_item in required_hair_cli_files
    )
    suite_passed &= print_status_result(
        i18n.translate("tests.hair_cli_flags"),
        cli_ok,
        f"{len(required_hair_cli_files)}/{len(required_hair_cli_files)} files",
    )

    with tempfile.TemporaryDirectory(prefix="vrc2gtav_hair_test_") as temp_root_str:
        temp_root = Path(temp_root_str)
        assets_dir = temp_root / "Assets"
        hair_dir = assets_dir / "TestHairPkg"
        hair_dir.mkdir(parents=True, exist_ok=True)

        fbx_path = hair_dir / "TestHair.fbx"
        fbx_path.write_bytes(b"Kaydara FBX Binary  \x00")
        (hair_dir / "TestHair.fbx.meta").write_text(
            "fileFormatVersion: 2\nguid: 11111111111111111111111111111111\n",
            encoding="utf-8",
        )

        main_tex_path = hair_dir / "hair_main.png"
        Image.new("RGBA", (8, 8), (220, 80, 120, 255)).save(main_tex_path)
        (hair_dir / "hair_main.png.meta").write_text(
            "fileFormatVersion: 2\nguid: 22222222222222222222222222222222\n",
            encoding="utf-8",
        )

        alpha_mask_img = Image.new("RGBA", (8, 8), (255, 255, 255, 255))
        for px_idx in range(4, 8):
            for py_idx in range(4, 8):
                alpha_mask_img.putpixel((px_idx, py_idx), (0, 0, 0, 255))
        alpha_mask_path = hair_dir / "hair_alpha.png"
        alpha_mask_img.save(alpha_mask_path)
        (hair_dir / "hair_alpha.png.meta").write_text(
            "fileFormatVersion: 2\nguid: 33333333333333333333333333333333\n",
            encoding="utf-8",
        )

        mat_main_path = hair_dir / "HairMain.mat"
        mat_main_path.write_text(
            "%YAML 1.1\n"
            "--- !u!21 &2100000\n"
            "Material:\n"
            "  m_Name: HairMain\n"
            "  m_SavedProperties:\n"
            "    m_TexEnvs:\n"
            "    - _MainTex:\n"
            "        m_Texture: {fileID: 2800000, guid: 22222222222222222222222222222222, type: 3}\n"
            "    - _AlphaMask:\n"
            "        m_Texture: {fileID: 2800000, guid: 33333333333333333333333333333333, type: 3}\n"
            "    m_Floats:\n"
            "    - _Metallic: 0.0\n"
            "    m_Colors:\n"
            "    - _Color: {r: 1, g: 1, b: 1, a: 1}\n",
            encoding="utf-8",
        )
        (hair_dir / "HairMain.mat.meta").write_text(
            "fileFormatVersion: 2\nguid: 44444444444444444444444444444444\n",
            encoding="utf-8",
        )

        mat_pin_path = hair_dir / "GoldPin.mat"
        mat_pin_path.write_text(
            "%YAML 1.1\n"
            "--- !u!21 &2100000\n"
            "Material:\n"
            "  m_Name: GoldPin\n"
            "  m_SavedProperties:\n"
            "    m_TexEnvs:\n"
            "    - _MainTex:\n"
            "        m_Texture: {fileID: 0}\n"
            "    m_Floats:\n"
            "    - _Metallic: 0.95\n"
            "    m_Colors:\n"
            "    - _Color: {r: 0.8, g: 0.6, b: 0.1, a: 1}\n",
            encoding="utf-8",
        )
        (hair_dir / "GoldPin.mat.meta").write_text(
            "fileFormatVersion: 2\nguid: 55555555555555555555555555555555\n",
            encoding="utf-8",
        )

        base_prefab = hair_dir / "BaseHair.prefab"
        base_prefab.write_text(
            "%YAML 1.1\n"
            "--- !u!1 &10\n"
            "GameObject:\n"
            "  m_Name: BaseHair\n"
            "  m_IsActive: 1\n"
            "--- !u!4 &11\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 10}\n"
            "  m_LocalScale: {x: 1.05, y: 1.05, z: 1.05}\n"
            "  m_Children:\n"
            "  - {fileID: 21}\n"
            "  - {fileID: 31}\n"
            "  - {fileID: 41}\n"
            "--- !u!1 &20\n"
            "GameObject:\n"
            "  m_Name: Bangs\n"
            "  m_IsActive: 1\n"
            "--- !u!4 &21\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 20}\n"
            "  m_Father: {fileID: 11}\n"
            "--- !u!137 &22\n"
            "SkinnedMeshRenderer:\n"
            "  m_GameObject: {fileID: 20}\n"
            "  m_Materials:\n"
            "  - {fileID: 2100000, guid: 44444444444444444444444444444444, type: 2}\n"
            "  m_Mesh: {fileID: 4300000, guid: 11111111111111111111111111111111, type: 3}\n"
            "--- !u!1 &30\n"
            "GameObject:\n"
            "  m_Name: Side.R braided\n"
            "  m_IsActive: 0\n"
            "--- !u!4 &31\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 30}\n"
            "  m_Father: {fileID: 11}\n"
            "--- !u!137 &32\n"
            "SkinnedMeshRenderer:\n"
            "  m_GameObject: {fileID: 30}\n"
            "  m_Materials:\n"
            "  - {fileID: 2100000, guid: 44444444444444444444444444444444, type: 2}\n"
            "  m_Mesh: {fileID: 4300002, guid: 11111111111111111111111111111111, type: 3}\n"
            "--- !u!1 &40\n"
            "GameObject:\n"
            "  m_Name: HairPin\n"
            "  m_IsActive: 1\n"
            "--- !u!4 &41\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 40}\n"
            "  m_Father: {fileID: 11}\n"
            "--- !u!23 &42\n"
            "MeshRenderer:\n"
            "  m_GameObject: {fileID: 40}\n"
            "  m_Materials:\n"
            "  - {fileID: 2100000, guid: 55555555555555555555555555555555, type: 2}\n"
            "--- !u!33 &43\n"
            "MeshFilter:\n"
            "  m_GameObject: {fileID: 40}\n"
            "  m_Mesh: {fileID: 4300004, guid: 11111111111111111111111111111111, type: 3}\n",
            encoding="utf-8",
        )
        (hair_dir / "BaseHair.prefab.meta").write_text(
            "fileFormatVersion: 2\nguid: 66666666666666666666666666666666\n",
            encoding="utf-8",
        )

        variant_prefab = hair_dir / "VariantHair.prefab"
        variant_prefab.write_text(
            "%YAML 1.1\n"
            "--- !u!1001 &100100000\n"
            "PrefabInstance:\n"
            "  m_Modification:\n"
            "    m_Modifications:\n"
            "    - target: {fileID: 10, guid: 66666666666666666666666666666666, type: 3}\n"
            "      propertyPath: m_Name\n"
            "      value: VariantHair\n"
            "  m_SourcePrefab: {fileID: 100100000, guid: 66666666666666666666666666666666, type: 3}\n",
            encoding="utf-8",
        )

        spec_base = unity_hair_helper.resolve_custom_hair_spec(
            hair_spec_input=str(base_prefab),
            unity_assets_root=str(assets_dir),
        )
        spec_variant = unity_hair_helper.resolve_custom_hair_spec(
            hair_spec_input=str(variant_prefab),
            unity_assets_root=str(assets_dir),
        )
        suppressed_names = sorted(
            {
                name_item.lower()
                for name_item in (
                    list(spec_variant.get("inactive_meshes", []))
                    + list(spec_variant.get("editor_only_meshes", []))
                )
            }
        )
        prefab_ok = (
            spec_base.get("mode") == "custom"
            and spec_variant.get("mode") == "custom"
            and spec_variant.get("primary_fbx") == str(fbx_path)
            and "side.r braided" in set(suppressed_names)
            and "bangs" not in set(suppressed_names)
            and len(spec_variant.get("materials", [])) >= 2
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.hair_prefab_variant"),
            prefab_ok,
            f"materials={len(spec_variant.get('materials', []))}, suppressed={suppressed_names}",
        )

        quad_diff, quad_norm, quad_spec, tile_entries = (
            unity_hair_helper.pack_hair_materials_into_quadrant(
                spec_variant["materials"],
                quad_size=(1024, 1024),
                quad_uv_rect=(0.5, 0.0, 0.5, 0.5),
                gutter_px=4,
            )
        )
        unity_hair_helper.save_custom_hair_manifest(temp_root, spec_variant, tile_entries)
        loaded_manifest = unity_hair_helper.load_custom_hair_manifest(temp_root)
        bangs_rect = unity_hair_helper.resolve_tile_uv_for_mesh_slot(
            mesh_name="Bangs",
            slot_index=0,
            slot_count=1,
            blender_mat_name="HairMain",
            manifest=loaded_manifest,
            fallback_rect=(0.5, 0.0, 0.5, 0.5),
        )
        pin_rect = unity_hair_helper.resolve_tile_uv_for_mesh_slot(
            mesh_name="HairPin",
            slot_index=0,
            slot_count=1,
            blender_mat_name="GoldPin",
            manifest=loaded_manifest,
            fallback_rect=(0.5, 0.0, 0.5, 0.5),
        )

        class _FakeUV:
            def __init__(self, u_coord: float, v_coord: float):
                self.x = u_coord
                self.y = v_coord

        fake_uv_data = [
            types.SimpleNamespace(uv=_FakeUV(1.25, -0.20)),
            types.SimpleNamespace(uv=_FakeUV(1.35, -0.10)),
            types.SimpleNamespace(uv=_FakeUV(1.45, -0.15)),
        ]
        fake_mesh = types.SimpleNamespace(
            name="Bangs",
            data=types.SimpleNamespace(
                uv_layers=types.SimpleNamespace(
                    active=types.SimpleNamespace(name="map1", data=fake_uv_data),
                ),
                materials=[types.SimpleNamespace(name="HairMain")],
                polygons=[types.SimpleNamespace(material_index=0, loop_indices=[0, 1, 2])],
                remove=lambda *_args: None,
            ),
        )
        # Keep __iter__ / __bool__ valid on fake_uv_layers for remap_custom_hair_uvs
        class _FakeUVLayersList(list):
            def __init__(self, layer_obj):
                super().__init__([layer_obj])
                self.active = layer_obj

            def remove(self, layer_obj):
                super().remove(layer_obj)

        fake_mesh.data.uv_layers = _FakeUVLayersList(fake_mesh.data.uv_layers.active)
        blender_hair_helper.remap_custom_hair_uvs(
            [fake_mesh],
            loaded_manifest,
            fallback_rect=(0.5, 0.0, 0.5, 0.5),
            target_uv_name="UVMap",
        )
        u_after = fake_uv_data[0].uv.x
        v_after = fake_uv_data[0].uv.y
        uv_in_bangs_rect = (
            bangs_rect[0] <= u_after <= bangs_rect[0] + bangs_rect[2]
            and bangs_rect[1] <= v_after <= bangs_rect[1] + bangs_rect[3]
            and bangs_rect != pin_rect
            and fake_mesh.data.uv_layers[0].name == "UVMap"
        )

        ponytail_obj = types.SimpleNamespace(
            name="tail",
            vertex_groups=[types.SimpleNamespace(name="Hair_01")],
        )
        animal_tail_obj = types.SimpleNamespace(
            name="Neko_Tail",
            vertex_groups=[types.SimpleNamespace(name="Hips")],
        )
        tail_filter_ok = (
            blender_hair_helper._is_hip_tail_not_hair_ponytail(
                None, ponytail_obj, {"mesh_root_bones": {"tail": "Hair"}}
            )
            is False
            and blender_hair_helper._is_hip_tail_not_hair_ponytail(
                None, animal_tail_obj, {}
            )
            is True
        )
        pack_ok = (
            quad_diff.size == (1024, 1024)
            and quad_norm.size == (1024, 1024)
            and quad_spec.size == (1024, 1024)
            and uv_in_bangs_rect
            and tail_filter_ok
        )
        suite_passed &= print_status_result(
            i18n.translate("tests.hair_uv_packing"),
            pack_ok,
            f"u={u_after:.4f}, v={v_after:.4f}, uv_layer={fake_mesh.data.uv_layers[0].name}",
        )

        # Verify vrc2gtav_paths preserves keyword overrides without wrapping via to_host_path
        temp_cfg = temp_root / "test_hair.cfg"
        cfg_source = (
            Path(project_paths.find_project_config_file())
            if project_paths.has_project_config_file()
            else PROJECT_ROOT_DIR / "vrc2gtav.cfg.example"
        )
        temp_cfg.write_text(cfg_source.read_text(encoding="utf-8"), encoding="utf-8")
        previous_env_cfg = os.environ.get(project_paths.CONFIG_ENV_VAR_NAME)
        os.environ[project_paths.CONFIG_ENV_VAR_NAME] = str(temp_cfg)
        project_paths.invalidate_config_cache()
        try:
            project_paths.set_character_custom_hair("franklin", "none")
            project_paths.set_character_custom_hair("trevor", "default", hair_scale="1.15")
            fr_cfg = project_paths.get_character_paths("franklin")
            tr_cfg = project_paths.get_character_paths("trevor")
            kw_ok = (
                fr_cfg.get("custom_hair") == "none"
                and tr_cfg.get("custom_hair") == "default"
                and str(tr_cfg.get("hair_scale")) == "1.15"
            )
            suite_passed &= print_status_result(
                i18n.translate("tests.hair_cfg_keywords"),
                kw_ok,
                f"franklin={fr_cfg.get('custom_hair')}, trevor={tr_cfg.get('custom_hair')}",
            )
        finally:
            if previous_env_cfg is None:
                os.environ.pop(project_paths.CONFIG_ENV_VAR_NAME, None)
            else:
                os.environ[project_paths.CONFIG_ENV_VAR_NAME] = previous_env_cfg
            project_paths.invalidate_config_cache()

    return suite_passed


def test_first_run_modular_avatar_and_error_handling() -> bool:
    """
    Validate First-Run archive/Unity ingestion, paginated 10+Next avatar selection,
    Modular Avatar native bake planning, Face/Body/Zeroed custom-dress blendshape
    export, PhysBone curve/prefix guards, INI append updates, and `--verbose` logging.
    """
    print(i18n.translate("tests.sec_first_run_ma_title"))
    import error_handler_helper as err_helper
    import avatar_archive_helper
    import modular_avatar_helper
    import blendshape_helper
    import physbone_helper
    import setup_first_run
    import build_universal_avatar

    suite_passed = True

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)

        # 1. Error handler & --verbose timestamped logging + timeout zombie prevention
        log_obj = err_helper.PipelineLogger(
            verbose=True,
            avatar_name="Shinano Test",
            stage_name="unit",
            project_root=tmp_dir,
        )
        log_obj.info("Pipeline concise summary", always=True)
        log_obj.debug("Detailed verbose line")
        log_exists = bool(
            log_obj.log_path
            and log_obj.log_path.is_file()
            and "Detailed verbose line" in log_obj.log_path.read_text(encoding="utf-8")
        )
        suite_passed &= print_status_result(
            "Verbose timestamped log file created in logs/",
            log_exists,
            str(log_obj.log_path),
        )

        timed_out_cleanly = False
        try:
            err_helper.run_subprocess_safe(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                logger=log_obj,
                stage_name="timeout_test",
                timeout_sec=0.4,
            )
        except err_helper.SubprocessExecutionError:
            timed_out_cleanly = True
        suite_passed &= print_status_result(
            "Subprocess timeout cleanly killed without zombie",
            timed_out_cleanly,
        )

        # 2. Zip-Slip rejection + synthetic .unitypackage + .zip ingestion
        evil_zip = tmp_dir / "evil.zip"
        with zipfile.ZipFile(evil_zip, "w") as zip_handle:
            zip_handle.writestr("../escape.txt", "blocked")
        zip_slip_blocked = False
        try:
            avatar_archive_helper.safe_extract_zip(evil_zip, tmp_dir / "unzip_out")
        except err_helper.ArchiveExtractionError:
            zip_slip_blocked = True
        suite_passed &= print_status_result("Zip-Slip traversal blocked", zip_slip_blocked)

        # Build synthetic 15-avatar Unity scene + custom dress MA prefab inside .unitypackage inside .zip
        pkg_staging = tmp_dir / "pkg_staging"
        pkg_staging.mkdir()
        dress_guid = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        dress_prefab_guid = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        avatar_prefab_guid = "cccccccccccccccccccccccccccccccc"

        # Minimal valid binary FBX with ShapeKeys for Avatar (Body) and Custom Dress (CustomDressMesh)
        def _write_min_shape_fbx(fbx_out: Path, model_name: str, shape_names: Sequence[str]) -> None:
            def _pack_node(name: str, props: Sequence[Tuple[str, Any]], children: Sequence[bytes] = ()) -> bytes:
                prop_bytes = bytearray()
                for ptype, pval in props:
                    prop_bytes.append(ord(ptype))
                    if ptype == "L":
                        prop_bytes.extend(struct.pack("<q", int(pval)))
                    elif ptype == "S":
                        raw_str = str(pval).encode("utf-8")
                        prop_bytes.extend(struct.pack("<I", len(raw_str)) + raw_str)
                child_blob = b"".join(children) + (b"\x00" * 13 if children else b"")
                total_rec = 13 + len(name.encode("utf-8")) + len(prop_bytes) + len(child_blob)
                return b"".join([
                    struct.pack("<IIIB", total_rec, len(props), len(prop_bytes), len(name.encode("utf-8"))),
                    name.encode("utf-8"),
                    bytes(prop_bytes),
                    child_blob,
                ])

            model_id = 100
            geom_id = 200
            bs_id = 300
            obj_children = [
                _pack_node("Model", [("L", model_id), ("S", f"{model_name}\x00\x01Model"), ("S", "Mesh")]),
                _pack_node("Geometry", [("L", geom_id), ("S", "Geo\x00\x01Geometry"), ("S", "Mesh")]),
                _pack_node("Deformer", [("L", bs_id), ("S", "BS\x00\x01Deformer"), ("S", "BlendShape")]),
            ]
            conn_children = [
                _pack_node("C", [("S", "OO"), ("L", geom_id), ("L", model_id)]),
                _pack_node("C", [("S", "OO"), ("L", bs_id), ("L", geom_id)]),
            ]
            for s_idx, s_name in enumerate(shape_names):
                ch_id = 400 + s_idx
                obj_children.append(
                    _pack_node("Deformer", [("L", ch_id), ("S", f"{s_name}\x00\x01Deformer"), ("S", "BlendShapeChannel")])
                )
                conn_children.append(_pack_node("C", [("S", "OO"), ("L", ch_id), ("L", bs_id)]))
            header = b"Kaydara FBX Binary  \x00\x1a\x00" + struct.pack("<I", 7400)
            body = (
                _pack_node("Objects", [], obj_children)
                + _pack_node("Connections", [], conn_children)
                + (b"\x00" * 13)
            )
            # Recompute absolute end offsets from 27-byte header cleanly using second pass:
            # Instead build section offsets sequentially so end_offset is exact file offset!
            def _write_node_at(offset: int, name: str, props: Sequence[Tuple[str, Any]], child_specs: Sequence[Any]) -> Tuple[bytes, int]:
                prop_bytes = bytearray()
                for ptype, pval in props:
                    prop_bytes.append(ord(ptype))
                    if ptype == "L":
                        prop_bytes.extend(struct.pack("<q", int(pval)))
                    elif ptype == "S":
                        raw_str = str(pval).encode("utf-8")
                        prop_bytes.extend(struct.pack("<I", len(raw_str)) + raw_str)
                cur = offset + 13 + len(name.encode("utf-8")) + len(prop_bytes)
                child_chunks: List[bytes] = []
                if child_specs:
                    for c_name, c_props, c_sub in child_specs:
                        c_bytes, cur = _write_node_at(cur, c_name, c_props, c_sub)
                        child_chunks.append(c_bytes)
                    cur += 13
                    child_chunks.append(b"\x00" * 13)
                end_off = cur
                hdr = struct.pack("<IIIB", end_off, len(props), len(prop_bytes), len(name.encode("utf-8")))
                return hdr + name.encode("utf-8") + bytes(prop_bytes) + b"".join(child_chunks), end_off

            o_specs = [
                ("Model", [("L", model_id), ("S", f"{model_name}\x00\x01Model"), ("S", "Mesh")], ()),
                ("Geometry", [("L", geom_id), ("S", "Geo\x00\x01Geometry"), ("S", "Mesh")], ()),
                ("Deformer", [("L", bs_id), ("S", "BS\x00\x01Deformer"), ("S", "BlendShape")], ()),
            ]
            c_specs = [
                ("C", [("S", "OO"), ("L", geom_id), ("L", model_id)], ()),
                ("C", [("S", "OO"), ("L", bs_id), ("L", geom_id)], ()),
            ]
            for s_idx, s_name in enumerate(shape_names):
                ch_id = 400 + s_idx
                o_specs.append(("Deformer", [("L", ch_id), ("S", f"{s_name}\x00\x01Deformer"), ("S", "BlendShapeChannel")], ()))
                c_specs.append(("C", [("S", "OO"), ("L", ch_id), ("L", bs_id)], ()))

            obj_blob, next_off = _write_node_at(27, "Objects", (), o_specs)
            conn_blob, _ = _write_node_at(next_off, "Connections", (), c_specs)
            fbx_out.parent.mkdir(parents=True, exist_ok=True)
            fbx_out.write_bytes(header + obj_blob + conn_blob + (b"\x00" * 13))

        # Write Unity project with scene containing 15 avatars + MA custom dress
        uproj = tmp_dir / "FakeUnityProj"
        uassets = uproj / "Assets" / "ShinanoTest"
        uassets.mkdir(parents=True)
        avatar_fbx = uassets / "ShinanoBase.fbx"
        dress_fbx = uassets / "CustomDress.fbx"
        _write_min_shape_fbx(avatar_fbx, "Body", ["vrc.v_aa", "Smile_1", "shrink_breast", "shrink_hip"])
        _write_min_shape_fbx(dress_fbx, "CustomDressMesh", ["Corset", "Skirt_Wide"])
        (uassets / "ShinanoBase.fbx.meta").write_text(f"fileFormatVersion: 2\nguid: {avatar_prefab_guid}\n", encoding="utf-8")
        (uassets / "CustomDress.fbx.meta").write_text(f"fileFormatVersion: 2\nguid: {dress_guid}\n", encoding="utf-8")

        dress_prefab = uassets / "CustomDress.prefab"
        dress_prefab.write_text(
            f"""%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &10
GameObject:
  m_Name: CustomDress
  m_IsActive: 1
--- !u!4 &11
Transform:
  m_GameObject: {{fileID: 10}}
  m_Father: {{fileID: 0}}
  m_Children:
  - {{fileID: 21}}
  - {{fileID: 31}}
--- !u!1 &20
GameObject:
  m_Name: Dress_Armature
  m_IsActive: 1
--- !u!4 &21
Transform:
  m_GameObject: {{fileID: 20}}
  m_Father: {{fileID: 11}}
  m_Children: []
--- !u!114 &22
MonoBehaviour:
  m_GameObject: {{fileID: 20}}
  m_Enabled: 1
  m_Script: {{fileID: 11500000, guid: {modular_avatar_helper.MA_MERGE_ARMATURE_GUID}, type: 3}}
  mergeTarget:
    referencePath: Armature
  prefix: Dress_
  suffix: _cloth
  mangleNames: 1
--- !u!1 &30
GameObject:
  m_Name: CustomDressMesh
  m_IsActive: 1
--- !u!4 &31
Transform:
  m_GameObject: {{fileID: 30}}
  m_Father: {{fileID: 11}}
  m_Children: []
--- !u!137 &32
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 30}}
  m_Enabled: 1
  m_Mesh: {{fileID: 4300000, guid: {dress_guid}, type: 3}}
--- !u!114 &33
MonoBehaviour:
  m_GameObject: {{fileID: 30}}
  m_Enabled: 1
  m_Script: {{fileID: 11500000, guid: {modular_avatar_helper.MA_BLENDSHAPE_SYNC_GUID}, type: 3}}
  Bindings:
  - ReferenceMesh:
      referencePath: Body
    Blendshape: shrink_breast
    LocalBlendshape: Corset
--- !u!114 &34
MonoBehaviour:
  m_GameObject: {{fileID: 30}}
  m_Enabled: 1
  m_Script: {{fileID: 11500000, guid: {modular_avatar_helper.MA_SHAPE_CHANGER_GUID}, type: 3}}
  m_inverted: 0
  m_shapes:
  - Object:
      referencePath: Body
      targetObject: {{fileID: 999}}
    ShapeName: shrink_breast
    ChangeType: 1
    Value: 100
""",
            encoding="utf-8",
        )
        (uassets / "CustomDress.prefab.meta").write_text(f"fileFormatVersion: 2\nguid: {dress_prefab_guid}\n", encoding="utf-8")

        # Build a 15-avatar Unity scene using SceneRoots
        scene_lines = ["%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"]
        root_ids: List[str] = []
        for idx_av in range(1, 16):
            go_id = 1000 + idx_av * 10
            tr_id = 2000 + idx_av * 10
            root_ids.append(str(tr_id))
            act_flag = 1 if idx_av == 13 else 0
            scene_lines.append(
                f"--- !u!1 &{go_id}\nGameObject:\n  m_Name: Avatar_{idx_av:02d}\n  m_IsActive: {act_flag}\n"
                f"--- !u!4 &{tr_id}\nTransform:\n  m_GameObject: {{fileID: {go_id}}}\n  m_Father: {{fileID: 0}}\n  m_Children:\n"
            )
            if idx_av == 13:
                scene_lines[-1] += f"  - {{fileID: {tr_id + 1}}}\n"
                scene_lines.append(
                    f"--- !u!1 &{go_id + 1}\nGameObject:\n  m_Name: Body\n  m_IsActive: 1\n"
                    f"--- !u!4 &{tr_id + 1}\nTransform:\n  m_GameObject: {{fileID: {go_id + 1}}}\n  m_Father: {{fileID: {tr_id}}}\n  m_Children: []\n"
                    f"--- !u!95 &{go_id + 2}\nAnimator:\n  m_GameObject: {{fileID: {go_id}}}\n"
                    f"--- !u!137 &{go_id + 3}\nSkinnedMeshRenderer:\n  m_GameObject: {{fileID: {go_id + 1}}}\n  m_Mesh: {{fileID: 4300000, guid: {avatar_prefab_guid}, type: 3}}\n"
                    f"  m_BlendShapeWeights:\n  - 0\n  - 85\n  - 100\n  - 25\n"
                    f"--- !u!1001 &{go_id + 4}\nPrefabInstance:\n  m_TransformParent: {{fileID: {tr_id}}}\n"
                    f"  m_SourcePrefab: {{fileID: 100100000, guid: {dress_prefab_guid}, type: 3}}\n"
                    f"  m_Modification:\n    m_Modifications:\n"
                    f"    - target: {{fileID: 10, guid: {dress_prefab_guid}, type: 3}}\n"
                    f"      propertyPath: m_Name\n      value: CustomDress\n      objectReference: {{fileID: 0}}\n"
                )
            else:
                scene_lines[-1] += "  []\n"
                scene_lines.append(f"--- !u!95 &{go_id + 2}\nAnimator:\n  m_GameObject: {{fileID: {go_id}}}\n")

        scene_lines.append("--- !u!1660057539 &9223372036854775807\nSceneRoots:\n  m_Roots:\n")
        for rid in root_ids:
            scene_lines.append(f"  - {{fileID: {rid}}}\n")
        test_scene = uassets / "TestMultiAvatar.unity"
        test_scene.write_text("".join(scene_lines), encoding="utf-8")

        # Pack into .unitypackage inside .zip to exercise full archive ingestion
        test_pkg = tmp_dir / "ShinanoTest.unitypackage"
        with tarfile.open(test_pkg, "w:gz") as tar_out:
            for item_idx, rel_p in enumerate(
                [
                    ("Assets/ShinanoTest/ShinanoBase.fbx", avatar_fbx, uassets / "ShinanoBase.fbx.meta", avatar_prefab_guid),
                    ("Assets/ShinanoTest/CustomDress.fbx", dress_fbx, uassets / "CustomDress.fbx.meta", dress_guid),
                    ("Assets/ShinanoTest/CustomDress.prefab", dress_prefab, uassets / "CustomDress.prefab.meta", dress_prefab_guid),
                    ("Assets/ShinanoTest/TestMultiAvatar.unity", test_scene, None, "dddddddddddddddddddddddddddddddd"),
                ]
            ):
                unity_rel, asset_src, meta_src, g_str = rel_p
                for sub_name, raw_bytes in [
                    (f"{g_str}/pathname", unity_rel.encode("utf-8")),
                    (f"{g_str}/asset", asset_src.read_bytes()),
                    (
                        f"{g_str}/asset.meta",
                        meta_src.read_bytes() if meta_src else f"fileFormatVersion: 2\nguid: {g_str}\n".encode("utf-8"),
                    ),
                ]:
                    t_info = tarfile.TarInfo(sub_name)
                    t_info.size = len(raw_bytes)
                    tar_out.addfile(t_info, io_stream.BytesIO(raw_bytes))

        bundle_zip = tmp_dir / "AvatarPack.zip"
        with zipfile.ZipFile(bundle_zip, "w") as zip_out:
            zip_out.write(test_pkg, arcname="AvatarPack/ShinanoTest.unitypackage")

        ingested = avatar_archive_helper.ingest_avatar_source(bundle_zip, tmp_dir, logger=log_obj)
        discovered = avatar_archive_helper.discover_scene_avatars(
            ingested["preferred_scene"], ingested["assets_root"]
        )
        suite_passed &= print_status_result(
            "Archive .zip -> .unitypackage -> 15 scene avatars discovered cleanly",
            len(discovered) == 15 and all(entry["name"] != "?" for entry in discovered),
            f"count={len(discovered)}, first={discovered[0]['name'] if discovered else ''}",
        )

        # Test paginated menu: 10 per page + Next button ('n' -> page 2 -> select item '3' = Avatar_03 or check)
        prompts_iter = iter(["n", "3"])
        menu_output: List[str] = []
        picked = avatar_archive_helper.prompt_select_scene_avatar(
            discovered,
            input_func=lambda _prompt: next(prompts_iter),
            output_func=menu_output.append,
            page_size=10,
        )
        has_next_btn = any("Next page >>" in line_txt for line_txt in menu_output)
        has_prev_btn = any("Previous page" in line_txt for line_txt in menu_output)
        suite_passed &= print_status_result(
            "Paginated avatar menu (10/page + Next + Prev)",
            bool(picked and picked == discovered[12] and has_next_btn and has_prev_btn),
            f"selected={picked['name'] if picked else None}",
        )

        # 3. Modular Avatar NDMF plan resolution (MergeArmature, Sync, ShapeChanger, Dress FBX)
        ma_plan = modular_avatar_helper.build_modular_avatar_bake_plan(
            ingested["preferred_scene"],
            avatar_name="Avatar_13",
            assets_root=ingested["assets_root"],
            logger=log_obj,
        )
        bone_map = modular_avatar_helper.resolve_ma_bone_mapping(
            ["Dress_Hips_cloth", "Dress_LeftUpperArm_cloth", "Skirt_Back_01"],
            ["Hips", "UpperArm.L", "Head"],
            prefix="Dress_",
            suffix="_cloth",
        )
        suite_passed &= print_status_result(
            "Modular Avatar NDMF bake plan (MergeArmature, Sync, ShapeChanger, CustomDress FBX)",
            bool(
                ma_plan["loaded"]
                and len(ma_plan["armature_merges"]) == 1
                and len(ma_plan["blendshape_syncs"]) == 1
                and abs(ma_plan["shape_changer_weights"].get("Body", {}).get("shrink_breast", 0.0) - 1.0) < 1e-4
                and bone_map.get("Dress_LeftUpperArm_cloth") == "UpperArm.L"
                and "Skirt_Back_01" not in bone_map
            ),
            f"merges={len(ma_plan['armature_merges'])}, bone_map={bone_map}",
        )

        # 4. Separate Face & Body blendshape extraction & custom dress zeroed .cfg generation
        zero_cfg = tmp_dir / "zeroed.cfg"
        zero_res = blendshape_helper.resolve_character_blendshapes(
            {"unity_scene": str(ingested["preferred_scene"]), "unity_avatar_name": "Avatar_13"},
            fbx_paths=[avatar_fbx],
            extra_fbx_paths=[dress_fbx],
            unity_assets_root=ingested["assets_root"],
            save_cfg_path=zero_cfg,
            import_face=False,
            import_body=False,
        )
        all_zero_ok = (
            zero_res["source_used"] == "fbx_zeroed"
            and "Body" in zero_res["mesh_weights"]
            and "CustomDressMesh" in zero_res["mesh_weights"]
            and all(
                abs(w_val) < 1e-6
                for mesh_map in zero_res["mesh_weights"].values()
                for w_val in mesh_map.values()
            )
        )
        suite_passed &= print_status_result(
            "Blendshapes No/No generates zeroed .cfg including custom dress FBX",
            all_zero_ok,
            f"meshes={list(zero_res['mesh_weights'].keys())}",
        )

        face_only_res = blendshape_helper.resolve_character_blendshapes(
            {"unity_scene": str(ingested["preferred_scene"]), "unity_avatar_name": "Avatar_13"},
            fbx_paths=[avatar_fbx],
            extra_fbx_paths=[dress_fbx],
            unity_assets_root=ingested["assets_root"],
            import_face=True,
            import_body=False,
        )
        face_only_ok = (
            abs(face_only_res["mesh_weights"]["Body"].get("Smile_1", 0.0) - 0.85) < 1e-4
            and abs(face_only_res["mesh_weights"]["Body"].get("shrink_breast", 1.0)) < 1e-6
        )
        suite_passed &= print_status_result(
            "Blendshapes Face=Yes/Body=No preserves face weights & zeroes body",
            face_only_ok,
        )

        # 5. PhysBone YAML curve parser & update_cfg_values_in_place new section append
        curve_block = (
            "  curve:\n"
            "    serializedVersion: 2\n"
            "    m_Curve:\n"
            "    - serializedVersion: 3\n"
            "      time: 0\n"
            "      value: 1\n"
            "    - serializedVersion: 3\n"
            "      time: 1\n"
            "      value: 0.25\n"
            "    m_PreInfinity: 2\n"
        )
        parsed_curve = physbone_helper._parse_yaml_curve(curve_block, "curve")
        cfg_sample = tmp_dir / "sample.cfg"
        cfg_sample.write_text("[directories]\ngtav_root = C:/GTA\n", encoding="utf-8")
        setup_first_run.update_cfg_values_in_place(
            cfg_sample,
            {"new_section": {"unity_avatar_name": "Avatar_13"}},
        )
        appended_ok = "unity_avatar_name = Avatar_13" in cfg_sample.read_text(encoding="utf-8")
        suite_passed &= print_status_result(
            "PhysBone curve parser & INI missing-section append fixes",
            len(parsed_curve) == 2 and abs(parsed_curve[1][1] - 0.25) < 1e-4 and appended_ok,
            f"curve={parsed_curve}",
        )

        # 6. Portable Blender detection check on local workstation when available
        local_blender_raw = project_paths.get_blender_exe() if project_paths.has_project_config_file() else ""
        local_blender = Path(project_paths.to_host_path(local_blender_raw)) if local_blender_raw else None
        if local_blender and local_blender.is_file():
            probe_res = avatar_archive_helper.inspect_blender_installation(local_blender)
            suite_passed &= print_status_result(
                "Blender 4.0.x & Sollumz inspection check",
                bool(probe_res["exists"] and probe_res["sollumz_installed"]),
                f"ver={probe_res['version']} sollumz={probe_res['sollumz_installed']}",
            )

    return suite_passed


def run_source_only_validation_suite() -> bool:
    """Run source-only checks (syntax, templates, i18n, quality, mirrors, First-Run/MA)."""
    separator_banner = "=" * 70
    print(f"\n{separator_banner}")
    print(f"      {i18n.translate('tests.source_banner')}")
    print(f"{separator_banner}")

    test_results_summary = [
        (i18n.translate("tests.suite_syntax"), test_python_syntax_compilation()),
        (i18n.translate("tests.suite_templates"), test_source_templates_and_dummies()),
        (i18n.translate("tests.suite_unity"), test_unity_scene_and_fallbacks()),
        (i18n.translate("tests.suite_interchangeability"), test_avatar_interchangeability()),
        (i18n.translate("tests.suite_custom_hair"), test_custom_unity_hair_support()),
        (i18n.translate("tests.suite_first_run_ma"), test_first_run_modular_avatar_and_error_handling()),
        (i18n.translate("tests.suite_i18n"), test_i18n_catalog_integrity()),
        (i18n.translate("tests.suite_quality"), test_code_quality_and_mirror_sync()),
    ]
    total_passed = sum(1 for _title, success_status in test_results_summary if success_status)
    total_tests = len(test_results_summary)
    print(i18n.translate("tests.source_result", passed=total_passed, total=total_tests))
    print(f"{separator_banner}\n")
    return total_passed == total_tests


def run_full_validation_suite() -> bool:
    """Run the full validation suite against the local workspace and mods folder."""
    separator_banner = "=" * 70
    print(f"\n{separator_banner}")
    print(f"      {i18n.translate('tests.full_banner')}")
    print(f"{separator_banner}")

    test_results_summary = [
        (i18n.translate("tests.suite_syntax"), test_python_syntax_compilation()),
        (i18n.translate("tests.suite_paths"), test_path_resolution()),
        (i18n.translate("tests.suite_dummies"), test_dummy_mesh_integrity()),
        (i18n.translate("tests.suite_unity"), test_unity_scene_and_fallbacks()),
        (i18n.translate("tests.suite_interchangeability"), test_avatar_interchangeability()),
        (i18n.translate("tests.suite_custom_hair"), test_custom_unity_hair_support()),
        (i18n.translate("tests.suite_first_run_ma"), test_first_run_modular_avatar_and_error_handling()),
        (i18n.translate("tests.suite_models"), test_compiled_drawables_and_textures()),
        (i18n.translate("tests.suite_rpf"), test_deployed_rpf_encryption_headers()),
        (i18n.translate("tests.suite_i18n"), test_i18n_catalog_integrity()),
        (i18n.translate("tests.suite_quality"), test_code_quality_and_mirror_sync()),
    ]

    print(f"\n{separator_banner}")
    print(i18n.translate("tests.summary_header"))
    print(f"{separator_banner}")

    total_passed = sum(1 for _title, success_status in test_results_summary if success_status)
    total_tests = len(test_results_summary)

    for test_title, success_status in test_results_summary:
        result_label = i18n.translate(
            "tests.suite_passed" if success_status else "tests.suite_failed"
        )
        print(f"  {result_label:12} : {test_title}")

    print(i18n.translate("tests.full_result", passed=total_passed, total=total_tests))
    print(f"{separator_banner}\n")
    return total_passed == total_tests


def main() -> int:
    """CLI entry point for running the automated validation suite."""
    resolve_startup_language()
    arg_parser = argparse.ArgumentParser(description=i18n.translate("tests.cli_desc"))
    arg_parser.add_argument(
        "--source-only",
        action="store_true",
        help=i18n.translate("tests.arg_source_only"),
    )
    arg_parser.add_argument(
        "--lang",
        choices=list(i18n.SUPPORTED_LANGUAGES) + ["auto"],
        default=None,
        help=i18n.translate("common.language_option_help"),
    )
    parsed_args = arg_parser.parse_args()
    if parsed_args.lang and parsed_args.lang != "auto":
        i18n.set_active_language(parsed_args.lang)

    if parsed_args.source_only:
        test_suite_success = run_source_only_validation_suite()
    else:
        test_suite_success = run_full_validation_suite()
    return 0 if test_suite_success else 1


if __name__ == "__main__":
    sys.exit(main())
