#!/usr/bin/env python3
"""
test_mod_suite.py
=================
Layer 4 of 4 (Public CLI Entrypoint & Validation Suite Facade).

Aggregates all automated validation suites from:
  - `test_suite_core_layer`: syntax, paths, dummies, RPF headers, i18n, AST/C++ quality
  - `test_suite_unity_physbones_layer`: Unity scenes, PhysBones packer, orphan cleanup
  - `test_suite_extensions_layer`: interchangeability, custom hair, MA, universal NPC
"""

import argparse
import sys
from pathlib import Path

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
    from test_suite_core_layer import (
        _PRUNED_WALK_DIRS,
        _iter_project_python_files,
        extract_placeholder_fields,
        print_status_result,
        resolve_startup_language,
        test_code_quality_and_mirror_sync,
        test_compiled_drawables_and_textures,
        test_deployed_rpf_encryption_headers,
        test_dummy_mesh_integrity,
        test_i18n_catalog_integrity,
        test_path_resolution,
        test_python_syntax_compilation,
        test_source_templates_and_dummies,
    )
    from test_suite_unity_physbones_layer import (
        test_unity_scene_and_fallbacks,
    )
    from test_suite_extensions_layer import (
        test_avatar_interchangeability,
        test_custom_unity_hair_support,
        test_first_run_modular_avatar_and_error_handling,
        test_universal_npc_pipeline,
    )
except ImportError:
    from common_tools import vrc2gtav_i18n as i18n
    from common_tools import vrc2gtav_paths as project_paths
    from common_tools.test_suite_core_layer import (
        _PRUNED_WALK_DIRS,
        _iter_project_python_files,
        extract_placeholder_fields,
        print_status_result,
        resolve_startup_language,
        test_code_quality_and_mirror_sync,
        test_compiled_drawables_and_textures,
        test_deployed_rpf_encryption_headers,
        test_dummy_mesh_integrity,
        test_i18n_catalog_integrity,
        test_path_resolution,
        test_python_syntax_compilation,
        test_source_templates_and_dummies,
    )
    from common_tools.test_suite_unity_physbones_layer import (
        test_unity_scene_and_fallbacks,
    )
    from common_tools.test_suite_extensions_layer import (
        test_avatar_interchangeability,
        test_custom_unity_hair_support,
        test_first_run_modular_avatar_and_error_handling,
        test_universal_npc_pipeline,
    )


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
        (i18n.translate("tests.suite_npc"), test_universal_npc_pipeline()),
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
        (i18n.translate("tests.suite_npc"), test_universal_npc_pipeline()),
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
