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
        _has_invalid_short_identifier_parts,
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
    from test_suite_restore_multislot_layer import (
        test_restore_and_multislot_regressions,
    )
except ImportError:
    from common_tools import vrc2gtav_i18n as i18n
    from common_tools import vrc2gtav_paths as project_paths
    from common_tools.test_suite_core_layer import (
        _PRUNED_WALK_DIRS,
        _has_invalid_short_identifier_parts,
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
    from common_tools.test_suite_restore_multislot_layer import (
        test_restore_and_multislot_regressions,
    )


def test_ma_shape_changer_and_manual_shrink() -> bool:
    """Verify MA ShapeChanger Delete/Set, BlendshapeSync RemapCurve, and manual Shrink_* culling."""
    import tempfile
    from types import SimpleNamespace
    import blendshape_helper
    import modular_avatar_helper
    import modular_avatar_yaml_layer

    suite_ok = True
    prefab_yaml = (
        "%YAML 1.1\n"
        "%TAG !u! tag:unity3d.com,2011:\n"
        "--- !u!1 &1001\n"
        "GameObject:\n"
        "  m_Name: DressTop\n"
        "  m_IsActive: 1\n"
        "--- !u!4 &2001\n"
        "Transform:\n"
        "  m_GameObject: {fileID: 1001}\n"
        "  m_Father: {fileID: 0}\n"
        "--- !u!114 &3001\n"
        "MonoBehaviour:\n"
        "  m_GameObject: {fileID: 1001}\n"
        "  m_Enabled: 1\n"
        f"  m_Script: {{fileID: 11500000, guid: {modular_avatar_yaml_layer.MA_SHAPE_CHANGER_GUID}, type: 3}}\n"
        "  m_inverted: 0\n"
        "  m_shapes:\n"
        "  - Object:\n"
        "      referencePath: Body_base\n"
        "      targetObject: {fileID: 0}\n"
        "    ShapeName: Shrink_Chest1\n"
        "    ChangeType: 0\n"
        "    Value: 100\n"
        "  - Object:\n"
        "      referencePath: Body_base\n"
        "      targetObject: {fileID: 0}\n"
        "    ShapeName: Toe_highheels\n"
        "    ChangeType: 1\n"
        "    Value: 100\n"
        "  - Object:\n"
        "      referencePath: Body_base\n"
        "      targetObject: {fileID: 0}\n"
        "    ShapeName: Shrink_Foot\n"
        "    ChangeType: 1\n"
        "    Value: 3\n"
        "  m_threshold: 0.015\n"
        "--- !u!114 &3002\n"
        "MonoBehaviour:\n"
        "  m_GameObject: {fileID: 1001}\n"
        "  m_Enabled: 1\n"
        f"  m_Script: {{fileID: 11500000, guid: {modular_avatar_yaml_layer.MA_BLENDSHAPE_SYNC_GUID}, type: 3}}\n"
        "  Bindings:\n"
        "  - ReferenceMesh:\n"
        "      referencePath: Body_base\n"
        "      targetObject: {fileID: 0}\n"
        "    Blendshape: Breasts_big\n"
        "    LocalBlendshape: Chest_Fit\n"
        "    RemapCurve:\n"
        "      serializedVersion: 2\n"
        "      m_Curve:\n"
        "      - time: 0\n"
        "        value: 10\n"
        "      - time: 100\n"
        "        value: 80\n"
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        prefab_file = Path(tmp_dir) / "MockMA.prefab"
        prefab_file.write_text(prefab_yaml, encoding="utf-8")
        plan_res = modular_avatar_helper.build_modular_avatar_bake_plan(
            prefab_file,
            assets_root=tmp_dir,
            resolve_materials=False,
        )

    del_items = plan_res.get("shape_changer_deletes") or []
    set_weights = (plan_res.get("shape_changer_weights") or {}).get("Body_base", {})
    sync_items = plan_res.get("blendshape_syncs") or []
    yaml_parse_ok = (
        len(del_items) == 1
        and del_items[0]["mesh"] == "Body_base"
        and del_items[0]["shape_name"] == "Shrink_Chest1"
        and abs(float(del_items[0]["threshold"]) - 0.015) < 1e-6
        and abs(float(set_weights.get("Toe_highheels", 0.0)) - 1.0) < 1e-6
        and abs(float(set_weights.get("Shrink_Foot", 0.0)) - 0.03) < 1e-6
        and "Shrink_Chest1" not in set_weights
        and len(sync_items) == 1
        and len(sync_items[0].get("remap_curve", ())) == 2
        and abs(blendshape_helper.evaluate_ma_remap_curve(0.5, sync_items[0]["remap_curve"]) - 0.45) < 1e-6
    )

    class _MockVec:
        def __init__(self, vec_len: float) -> None:
            self.value = vec_len

        def __sub__(self, other_vec: "_MockVec") -> object:
            return SimpleNamespace(length=abs(self.value - other_vec.value))

    def _make_vec(vec_len: float) -> object:
        return _MockVec(vec_len)

    def _make_kblocks(entries: dict) -> object:
        blocks = [SimpleNamespace(name="Basis", value=0.0, data=entries["Basis"])]
        for key_name, key_spec in entries.items():
            if key_name == "Basis":
                continue
            weight_val, pts_list = key_spec
            blocks.append(SimpleNamespace(name=key_name, value=weight_val, data=pts_list))
        lookup_map = {blk.name: blk for blk in blocks}

        class _BlockCollection(list):
            def get(self, name_str: str, default_val: object = None) -> object:
                return lookup_map.get(name_str, default_val)

            def __contains__(self, name_str: object) -> bool:
                return name_str in lookup_map

            def __getitem__(self, item_key: object) -> object:
                if isinstance(item_key, (int, slice)):
                    return super().__getitem__(item_key)
                return lookup_map[item_key]

        return _BlockCollection(blocks)

    zero_pts = [SimpleNamespace(co=_make_vec(0.0)) for _ in range(4)]
    del_pts = [SimpleNamespace(co=_make_vec(0.05 if idx == 1 else 0.0)) for idx in range(4)]
    shrink_pts = [SimpleNamespace(co=_make_vec(0.001 if idx >= 2 else 0.0)) for idx in range(4)]

    body_obj = SimpleNamespace(
        name="Body_base",
        type="MESH",
        data=SimpleNamespace(
            vertices=[None, None, None, None],
            shape_keys=SimpleNamespace(
                key_blocks=_make_kblocks(
                    {
                        "Basis": zero_pts,
                        "Breasts_big": (0.5, zero_pts),
                        "Toe_highheels": (0.7, zero_pts),
                        "Shrink_Foot": (0.0, zero_pts),
                        "Shrink_Chest1": (0.0, del_pts),
                        "Shrink_Upper_arm": (1.0, shrink_pts),
                    }
                )
            ),
        ),
    )
    dress_first = SimpleNamespace(
        name="DressTop",
        type="MESH",
        data=SimpleNamespace(
            vertices=[None],
            shape_keys=SimpleNamespace(key_blocks=_make_kblocks({"Basis": zero_pts[:1], "Chest_Fit": (0.0, zero_pts[:1])})),
        ),
    )
    dress_second = SimpleNamespace(
        name="DressTop.001",
        type="MESH",
        data=SimpleNamespace(
            vertices=[None],
            shape_keys=SimpleNamespace(key_blocks=_make_kblocks({"Basis": zero_pts[:1], "Chest_Fit": (0.0, zero_pts[:1])})),
        ),
    )
    mock_bpy = SimpleNamespace(data=SimpleNamespace(objects=[body_obj, dress_first, dress_second]))
    sync_summary = blendshape_helper.apply_ma_shape_changers_and_syncs(mock_bpy, plan_res)
    del_rules = blendshape_helper.collect_shape_deleted_vertex_rules(body_obj, plan_res)
    blender_rules_ok = (
        abs(body_obj.data.shape_keys.key_blocks["Toe_highheels"].value - 1.0) < 1e-6
        and abs(body_obj.data.shape_keys.key_blocks["Shrink_Foot"].value - 0.03) < 1e-6
        and abs(dress_first.data.shape_keys.key_blocks["Chest_Fit"].value - 0.45) < 1e-6
        and abs(dress_second.data.shape_keys.key_blocks["Chest_Fit"].value - 0.45) < 1e-6
        and sync_summary["synced_blendshapes"] == 2
        and del_rules["any_verts"] == {1}
        and del_rules["all_verts"] == {2, 3}
    )

    shinano_scene = (
        Path("E:/waifuv4/Assets/Shinano.unity")
        if sys.platform.startswith("win")
        else Path("/mnt/e/waifuv4/Assets/Shinano.unity")
    )
    noctis_ok = True
    if shinano_scene.is_file():
        assets_dir = str(shinano_scene.parent)
        noctis_plan = modular_avatar_helper.build_modular_avatar_bake_plan(
            shinano_scene,
            avatar_name="Shinano Noctis Marine",
            assets_root=assets_dir,
            resolve_materials=False,
        )
        noctis_del_shapes = {entry["shape_name"] for entry in noctis_plan.get("shape_changer_deletes") or ()}
        noctis_set_body = (noctis_plan.get("shape_changer_weights") or {}).get("Body_base", {})
        noctis_set_tights = (noctis_plan.get("shape_changer_weights") or {}).get("Tights", {})
        noctis_ok = (
            len(noctis_del_shapes) >= 15
            and {"Shrink_Chest1", "Shrink_Chest2", "Shrink_Foot"}.issubset(noctis_del_shapes)
            and abs(float(noctis_set_body.get("Toe_highheels", 0.0)) - 1.0) < 1e-6
            and abs(float(noctis_set_body.get("Shrink_Foot", 0.0)) - 0.03) < 1e-6
            and abs(float(noctis_set_tights.get("Toe_highheels", 0.0)) - 1.0) < 1e-6
        )

    suite_ok = yaml_parse_ok and blender_rules_ok and noctis_ok
    segment_guard_ok = (
        not _has_invalid_short_identifier_parts("axis_x")
        and not _has_invalid_short_identifier_parts("eixo_x")
        and not _has_invalid_short_identifier_parts("world_z_offset")
        and not _has_invalid_short_identifier_parts("u_coord")
        and not _has_invalid_short_identifier_parts("ma_plan_id")
        and _has_invalid_short_identifier_parts("ch_k")
        and _has_invalid_short_identifier_parts("vg_nm")
        and _has_invalid_short_identifier_parts("w_val")
        and _has_invalid_short_identifier_parts("act_m")
    )
    return print_status_result(
        "MA ShapeChanger Delete/Set, BlendshapeSync RemapCurve & manual Shrink_* culling",
        suite_ok and segment_guard_ok,
        f"yaml={yaml_parse_ok} rules={blender_rules_ok} noctis={noctis_ok} seg_guard={segment_guard_ok}",
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
        ("MA ShapeChanger & Manual Shrink Suite", test_ma_shape_changer_and_manual_shrink()),
        (i18n.translate("tests.suite_npc"), test_universal_npc_pipeline()),
        ("Restore-Vanilla & Multi-Slot Suite", test_restore_and_multislot_regressions()),
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
        ("MA ShapeChanger & Manual Shrink Suite", test_ma_shape_changer_and_manual_shrink()),
        (i18n.translate("tests.suite_npc"), test_universal_npc_pipeline()),
        ("Restore-Vanilla & Multi-Slot Suite", test_restore_and_multislot_regressions()),
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
