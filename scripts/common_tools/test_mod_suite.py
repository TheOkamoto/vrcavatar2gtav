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
import py_compile
import re as regex_module
import string
import struct
import sys
from pathlib import Path

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


def test_python_syntax_compilation() -> bool:
    """Compile every tracked Python file to verify valid syntax."""
    print(i18n.translate("tests.sec1_title"))
    all_compiled_cleanly = True
    python_files_found = sorted(PROJECT_ROOT_DIR.glob("**/*.py"))

    for python_file_path in python_files_found:
        if any(
            ignored in python_file_path.parts
            for ignored in ("staging", ".git", "__pycache__", ".venv")
        ):
            continue
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

    for asset_file_path in expected_assets_list:
        file_exists = asset_file_path.exists()
        file_size_mb = (
            (asset_file_path.stat().st_size / (1024 * 1024)) if file_exists else 0.0
        )
        all_assets_present &= print_status_result(
            asset_file_path.name,
            file_exists,
            i18n.translate(
                "tests.asset_detail",
                size=file_size_mb,
                parent=asset_file_path.parent.name,
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
    for python_file in sorted(PROJECT_ROOT_DIR.rglob("*.py")):
        if any(
            ignored_part in python_file.parts
            for ignored_part in ("__pycache__", "staging", "backups")
        ):
            continue
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
    for python_file in sorted(root_dir.rglob("*.py")):
        if any(
            ignored in python_file.parts
            for ignored in (".git", "__pycache__", "extracted_rpfs", "backups", "staging", ".venv")
        ):
            continue
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
        franklin_dir = project_paths.get_character_paths("franklin")["character_dir"]
        michael_dir = project_paths.get_character_paths("michael")["character_dir"]
        trevor_dir = project_paths.get_character_paths("trevor")["character_dir"]
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
        (common_dir / "setup_first_run.py", deploy_dir / "setup_first_run.py"),
        (common_dir / "hand_skeleton_helper.py", deploy_dir / "hand_skeleton_helper.py"),
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
    return template_ok and gitignore_check and dummies_ok


def run_source_only_validation_suite() -> bool:
    """Run source-only checks (syntax, templates, i18n, quality, and mirrors)."""
    separator_banner = "=" * 70
    print(f"\n{separator_banner}")
    print(f"      {i18n.translate('tests.source_banner')}")
    print(f"{separator_banner}")

    test_results_summary = [
        (i18n.translate("tests.suite_syntax"), test_python_syntax_compilation()),
        (i18n.translate("tests.suite_templates"), test_source_templates_and_dummies()),
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
