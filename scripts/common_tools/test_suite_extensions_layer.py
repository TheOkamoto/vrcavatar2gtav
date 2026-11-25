#!/usr/bin/env python3
"""
test_suite_extensions_layer.py
==============================
Layer 3 of 4 for automated project validation (`test_mod_suite`).

Validates protagonist <-> avatar interchangeability, custom Unity hair porting,
First-Run `.zip`/`.unitypackage`/Modular Avatar bake engine & logging guards,
and the universal NPC / street pedestrian pipeline (`ig_*`, `cs_*`,
`componentpeds`, curved-lash eye blinking, and model-scoped INI merging).
"""

import io as io_stream
import os
import struct
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Sequence, Tuple

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
    from test_suite_core_layer import print_status_result
except ImportError:
    from common_tools import vrc2gtav_i18n as i18n
    from common_tools import vrc2gtav_paths as project_paths
    from common_tools.test_suite_core_layer import print_status_result


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
        (scripts_root / "common_tools" / "run_mod_manager.py", "--mouth-open-strength"),
        (scripts_root / "common_tools" / "build_universal_avatar.py", "--mouth-open-strength"),
        (scripts_root / "common_tools" / "universal_gtav_builder.py", "--mouth-open-strength"),
        (scripts_root / "Shinano_Casual_Franklin" / "build_franklin_avatar.py", "--mouth-open-strength"),
        (scripts_root / "Shinano_Casual_Franklin" / "run_build_franklin.py", "--mouth-open-strength"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "build_michael_er.py", "--mouth-open-strength"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "run_build_er.py", "--mouth-open-strength"),
        (scripts_root / "Miltina_Maid_Trevor" / "build_trevor_miltina.py", "--mouth-open-strength"),
        (scripts_root / "Miltina_Maid_Trevor" / "run_pipeline.py", "--mouth-open-strength"),
        (scripts_root / "common_tools" / "universal_gtav_builder.py", "--face-anim"),
        (scripts_root / "common_tools" / "build_universal_avatar.py", "--face-anim"),
        (scripts_root / "common_tools" / "run_mod_manager.py", "--face-anim"),
        (scripts_root / "Shinano_Casual_Franklin" / "build_franklin_avatar.py", "--face-anim"),
        (scripts_root / "Shinano_Casual_Franklin" / "run_build_franklin.py", "--face-anim"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "build_michael_er.py", "--face-anim"),
        (scripts_root / "Shinano_EternalReunion_Michael" / "run_build_er.py", "--face-anim"),
        (scripts_root / "Miltina_Maid_Trevor" / "build_trevor_miltina.py", "--face-anim"),
        (scripts_root / "Miltina_Maid_Trevor" / "run_pipeline.py", "--face-anim"),
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
            for python_file_idx in range(4, 8):
                alpha_mask_img.putpixel((px_idx, python_file_idx), (0, 0, 0, 255))
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
            franklin_cfg = project_paths.get_character_paths("franklin")
            trevor_cfg = project_paths.get_character_paths("trevor")
            keywords_ok = (
                franklin_cfg.get("custom_hair") == "none"
                and trevor_cfg.get("custom_hair") == "default"
                and str(trevor_cfg.get("hair_scale")) == "1.15"
            )
            suite_passed &= print_status_result(
                i18n.translate("tests.hair_cfg_keywords"),
                keywords_ok,
                f"franklin={franklin_cfg.get('custom_hair')}, trevor={trevor_cfg.get('custom_hair')}",
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
            blendshape_id = 300
            obj_children = [
                _pack_node("Model", [("L", model_id), ("S", f"{model_name}\x00\x01Model"), ("S", "Mesh")]),
                _pack_node("Geometry", [("L", geom_id), ("S", "Geo\x00\x01Geometry"), ("S", "Mesh")]),
                _pack_node("Deformer", [("L", blendshape_id), ("S", "BS\x00\x01Deformer"), ("S", "BlendShape")]),
            ]
            conn_children = [
                _pack_node("C", [("S", "OO"), ("L", geom_id), ("L", model_id)]),
                _pack_node("C", [("S", "OO"), ("L", blendshape_id), ("L", geom_id)]),
            ]
            for shape_idx, shape_name in enumerate(shape_names):
                channel_id = 400 + shape_idx
                obj_children.append(
                    _pack_node("Deformer", [("L", channel_id), ("S", f"{shape_name}\x00\x01Deformer"), ("S", "BlendShapeChannel")])
                )
                conn_children.append(_pack_node("C", [("S", "OO"), ("L", channel_id), ("L", blendshape_id)]))
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
                    for chunk_name, chunk_props, child_subnodes in child_specs:
                        chunk_bytes, cur = _write_node_at(cur, chunk_name, chunk_props, child_subnodes)
                        child_chunks.append(chunk_bytes)
                    cur += 13
                    child_chunks.append(b"\x00" * 13)
                end_off = cur
                hdr = struct.pack("<IIIB", end_off, len(props), len(prop_bytes), len(name.encode("utf-8")))
                return hdr + name.encode("utf-8") + bytes(prop_bytes) + b"".join(child_chunks), end_off

            obj_specs = [
                ("Model", [("L", model_id), ("S", f"{model_name}\x00\x01Model"), ("S", "Mesh")], ()),
                ("Geometry", [("L", geom_id), ("S", "Geo\x00\x01Geometry"), ("S", "Mesh")], ()),
                ("Deformer", [("L", blendshape_id), ("S", "BS\x00\x01Deformer"), ("S", "BlendShape")], ()),
            ]
            child_node_specs = [
                ("C", [("S", "OO"), ("L", geom_id), ("L", model_id)], ()),
                ("C", [("S", "OO"), ("L", blendshape_id), ("L", geom_id)], ()),
            ]
            for shape_idx, shape_name in enumerate(shape_names):
                channel_id = 400 + shape_idx
                obj_specs.append(("Deformer", [("L", channel_id), ("S", f"{shape_name}\x00\x01Deformer"), ("S", "BlendShapeChannel")], ()))
                child_node_specs.append(("C", [("S", "OO"), ("L", channel_id), ("L", blendshape_id)], ()))

            obj_blob, next_off = _write_node_at(27, "Objects", (), obj_specs)
            conn_blob, _ = _write_node_at(next_off, "Connections", (), child_node_specs)
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
        for avatar_idx in range(1, 16):
            game_object_id = 1000 + avatar_idx * 10
            transform_id = 2000 + avatar_idx * 10
            root_ids.append(str(transform_id))
            act_flag = 1 if avatar_idx == 13 else 0
            scene_lines.append(
                f"--- !u!1 &{game_object_id}\nGameObject:\n  m_Name: Avatar_{avatar_idx:02d}\n  m_IsActive: {act_flag}\n"
                f"--- !u!4 &{transform_id}\nTransform:\n  m_GameObject: {{fileID: {game_object_id}}}\n  m_Father: {{fileID: 0}}\n  m_Children:\n"
            )
            if avatar_idx == 13:
                scene_lines[-1] += f"  - {{fileID: {transform_id + 1}}}\n"
                scene_lines.append(
                    f"--- !u!1 &{game_object_id + 1}\nGameObject:\n  m_Name: Body\n  m_IsActive: 1\n"
                    f"--- !u!4 &{transform_id + 1}\nTransform:\n  m_GameObject: {{fileID: {game_object_id + 1}}}\n  m_Father: {{fileID: {transform_id}}}\n  m_Children: []\n"
                    f"--- !u!95 &{game_object_id + 2}\nAnimator:\n  m_GameObject: {{fileID: {game_object_id}}}\n"
                    f"--- !u!137 &{game_object_id + 3}\nSkinnedMeshRenderer:\n  m_GameObject: {{fileID: {game_object_id + 1}}}\n  m_Mesh: {{fileID: 4300000, guid: {avatar_prefab_guid}, type: 3}}\n"
                    f"  m_BlendShapeWeights:\n  - 0\n  - 85\n  - 100\n  - 25\n"
                    f"--- !u!1001 &{game_object_id + 4}\nPrefabInstance:\n  m_TransformParent: {{fileID: {transform_id}}}\n"
                    f"  m_SourcePrefab: {{fileID: 100100000, guid: {dress_prefab_guid}, type: 3}}\n"
                    f"  m_Modification:\n    m_Modifications:\n"
                    f"    - target: {{fileID: 10, guid: {dress_prefab_guid}, type: 3}}\n"
                    f"      propertyPath: m_Name\n      value: CustomDress\n      objectReference: {{fileID: 0}}\n"
                )
            else:
                scene_lines[-1] += "  []\n"
                scene_lines.append(f"--- !u!95 &{game_object_id + 2}\nAnimator:\n  m_GameObject: {{fileID: {game_object_id}}}\n")

        scene_lines.append("--- !u!1660057539 &9223372036854775807\nSceneRoots:\n  m_Roots:\n")
        for rid in root_ids:
            scene_lines.append(f"  - {{fileID: {rid}}}\n")
        test_scene = uassets / "TestMultiAvatar.unity"
        test_scene.write_text("".join(scene_lines), encoding="utf-8")

        # Pack into .unitypackage inside .zip to exercise full archive ingestion
        test_pkg = tmp_dir / "ShinanoTest.unitypackage"
        with tarfile.open(test_pkg, "w:gz") as tar_out:
            for item_idx, rel_path in enumerate(
                [
                    ("Assets/ShinanoTest/ShinanoBase.fbx", avatar_fbx, uassets / "ShinanoBase.fbx.meta", avatar_prefab_guid),
                    ("Assets/ShinanoTest/CustomDress.fbx", dress_fbx, uassets / "CustomDress.fbx.meta", dress_guid),
                    ("Assets/ShinanoTest/CustomDress.prefab", dress_prefab, uassets / "CustomDress.prefab.meta", dress_prefab_guid),
                    ("Assets/ShinanoTest/TestMultiAvatar.unity", test_scene, None, "dddddddddddddddddddddddddddddddd"),
                ]
            ):
                unity_rel, asset_src, meta_src, guid_str = rel_path
                for sub_name, raw_bytes in [
                    (f"{guid_str}/pathname", unity_rel.encode("utf-8")),
                    (f"{guid_str}/asset", asset_src.read_bytes()),
                    (
                        f"{guid_str}/asset.meta",
                        meta_src.read_bytes() if meta_src else f"fileFormatVersion: 2\nguid: {guid_str}\n".encode("utf-8"),
                    ),
                ]:
                    tar_info = tarfile.TarInfo(sub_name)
                    tar_info.size = len(raw_bytes)
                    tar_out.addfile(tar_info, io_stream.BytesIO(raw_bytes))

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
                abs(weight_val) < 1e-6
                for mesh_map in zero_res["mesh_weights"].values()
                for weight_val in mesh_map.values()
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


def test_universal_npc_pipeline() -> bool:
    """Validate universal NPC registry, atlas tiling, PhysBone separation & curved blink fit."""
    print(f"\n--- {i18n.translate('tests.suite_npc')} ---")
    import configparser
    import npc_registry_helper
    import physbone_helper
    import universal_atlas_builder
    import eye_blink_helper

    suite_passed = True

    with tempfile.TemporaryDirectory() as tmp_root_str:
        tmp_root = Path(tmp_root_str)

        # 1. Registry round-trip and archive path splitter (streamed + componentpeds)
        reg_file_check = npc_registry_helper.load_npc_registry(tmp_root)
        suite_passed &= print_status_result(
            "Empty NPC registry default load",
            isinstance(reg_file_check.get("npcs"), dict) and len(reg_file_check["npcs"]) == 0,
            str(tmp_root),
        )
        reg_sample = {
            "npcs": {
                "ig_lamardavis": {"ped_name": "ig_lamardavis", "avatar_name": "Karin"},
                "a_f_y_beach_01": {"ped_name": "a_f_y_beach_01", "avatar_name": "BeachKarin"},
            }
        }
        npc_registry_helper.save_npc_registry(reg_sample, tmp_root)
        reloaded_reg = npc_registry_helper.load_npc_registry(tmp_root)
        split_streamed = npc_registry_helper._split_archive_hit(
            "/gtav/x64e.rpf:x64e.rpf/models/cdimages/streamedpeds_ig.rpf/ig_lamardavis/uppr_000_u.ydd"
        )
        split_comp = npc_registry_helper._split_archive_hit(
            "/gtav/x64v.rpf:x64v.rpf/models/cdimages/componentpeds_a_f_y.rpf/a_f_y_beach_01.ydd"
        )
        suite_passed &= print_status_result(
            "NPC registry save/reload & RPF archive hit parsing",
            (
                reloaded_reg["npcs"]["ig_lamardavis"]["avatar_name"] == "Karin"
                and split_streamed[1] == "models/cdimages/streamedpeds_ig.rpf"
                and split_streamed[2] == "ig_lamardavis/uppr_000_u.ydd"
                and split_comp[1] == "models/cdimages/componentpeds_a_f_y.rpf"
                and split_comp[2] == "a_f_y_beach_01.ydd"
            ),
            i18n.translate("tests.npc_pipeline_detail"),
        )

        # 2. PhysBone un-sided Skirt_0 vs Skirt_8 separation, wrist/ankle parents, & model INI scoping
        chain_first = physbone_helper._normalize_gtav_chain_name("Skirt_0")
        chain_second = physbone_helper._normalize_gtav_chain_name("Skirt_8")
        parent_hand, _tag_hand = physbone_helper.resolve_parent_bone_from_unity_chain(
            ["LeftHand", "LeftLowerArm"]
        )
        parent_shoe, _tag_shoe = physbone_helper.resolve_parent_bone_from_unity_chain(
            ["RightFoot", "RightLowerLeg"]
        )

        ini_path = tmp_root / "GTAVPhysBones.ini"
        lamar_chain = {
            "name": "PB_Auto_Tail",
            "model": "ig_lamardavis",
            "parent_bone_tag": 11816,
            "config": {
                "pull": 0.05,
                "spring": 0.80,
                "stiffness": 0.10,
                "gravity": 0.0,
                "gravity_falloff": 0.0,
                "immobile": 0.40,
                "limit_type": 1,
                "max_angle_x": 55.0,
                "max_angle_z": 45.0,
                "integration_type": 1,
                "is_animated": 0,
            },
            "bones": [
                {"name": "PB_Auto_Tail_0", "tag": 12001, "max_angle": 55.0, "local_pos": (0.0, 0.0, 0.0), "local_rot": (0.0, 0.0, 0.0, 1.0), "limit_axis_local": (0.0, -1.0, 0.0)},
                {"name": "PB_Auto_Tail_1", "tag": 12002, "max_angle": 55.0, "local_pos": (0.0, -0.1, 0.0), "local_rot": (0.0, 0.0, 0.0, 1.0), "limit_axis_local": (0.0, -1.0, 0.0)},
            ],
        }
        franklin_chain = dict(lamar_chain, name="PB_SC_Ear_L", model="player_one")
        physbone_helper.export_physbone_asi_ini(ini_path, [franklin_chain], target_ped_model="all")
        physbone_helper.merge_physbone_asi_ini(
            ini_path,
            [lamar_chain],
            own_prefixes=(),
            target_ped_model="all",
            own_chain_models=("ig_lamardavis",),
        )
        cfg_ini = configparser.ConfigParser()
        cfg_ini.read(ini_path, encoding="utf-8")
        models_found = {cfg_ini[sec].get("model") for sec in cfg_ini.sections() if sec.startswith("Chain_")}
        suite_passed &= print_status_result(
            "PhysBone ring separation, limb parents & model-scoped INI merge",
            (
                chain_first != chain_second
                and parent_hand == "SKEL_L_Hand"
                and parent_shoe == "SKEL_R_Foot"
                and models_found == {"player_one", "ig_lamardavis"}
            ),
            f"rings={chain_first}/{chain_second} models={sorted(models_found)}",
        )

        # 3. Eye blink curved lash fit ignoring below-eye stray brow micro-deltas
        fit_res = eye_blink_helper._fit_one_eye_side_weights(
            side_deltas={
                10: (0.0, 0.004, -0.030),
                11: (-0.004, 0.003, -0.025),
            },
            side_coords={
                10: (0.045, -0.050, 1.114),
                11: (0.060, -0.044, 1.121),
            },
            side_sign=1.0,
            upper_bone_name="PB_Blink_L",
            outer_bone_name="PB_Blink_LO",
            side_brow_coords=[
                (0.062, -0.048, 1.075),
                (0.050, -0.052, 1.135),
            ],
        )
        suite_passed &= print_status_result(
            "Eye blink curved upper-lash weight fit with below-eye brow filter",
            bool(fit_res.get("ok")) and (10 in fit_res["weights"]) and (11 in fit_res["weights"]),
            f"weighted_ids={sorted(fit_res['weights'].keys())}",
        )

        # 4. Universal atlas alpha overlay filter & tile manifest structure
        mat_dir = tmp_root / "Assets" / "Karin"
        mat_dir.mkdir(parents=True, exist_ok=True)
        tex_img_path = mat_dir / "Diff.png"
        from PIL import Image
        Image.new("RGBA", (64, 64), (240, 200, 210, 255)).save(tex_img_path)
        alpha_mat = mat_dir / "Karin_Alpha.mat"
        alpha_mat.write_text("m_Name: Karin_Alpha\n", encoding="utf-8")
        hair_mat = mat_dir / "Karin_Hair_Transparent.mat"
        hair_mat.write_text("m_Name: Karin_Hair_Transparent\n", encoding="utf-8")
        parsed_alpha = universal_atlas_builder.parse_unity_material_file(alpha_mat, {})
        parsed_hair_trans = universal_atlas_builder.parse_unity_material_file(hair_mat, {})
        suite_passed &= print_status_result(
            "Universal atlas material filter keeps hair transparency & strips body alpha",
            bool(parsed_alpha["is_body_alpha_overlay"]) and not bool(parsed_hair_trans["is_body_alpha_overlay"]),
            f"alpha={parsed_alpha['is_body_alpha_overlay']} hair={parsed_hair_trans['is_body_alpha_overlay']}",
        )

        # 5. Protagonist wearable prop patch replaces p_head/p_eyes/p_ears & backs up vanilla
        dummy_prop_path = (
            project_paths.get_prop_dummy_ydd_path()
            if project_paths.has_project_config_file()
            else (PROJECT_ROOT_DIR / "_deploy_tools" / "p_eyes_dummy.ydd")
        )
        sample_props_dir = tmp_root / "player_one_p"
        sample_backup_dir = tmp_root / "backup_props"
        sample_props_dir.mkdir(parents=True, exist_ok=True)
        (sample_props_dir / "p_head_000.ydd").write_bytes(b"VANILLA_HAT")
        (sample_props_dir / "p_eyes_000.ydd").write_bytes(b"VANILLA_GLASSES")
        (sample_props_dir / "p_ears_000.ydd").write_bytes(b"VANILLA_EAR")
        (sample_props_dir / "p_head_diff_000_a.ytd").write_bytes(b"KEEP_YTD")
        prop_patch_res = project_paths.patch_character_glasses_props(
            sample_props_dir,
            dummy_prop_path,
            "player_one_p",
            backup_directory=sample_backup_dir,
        )
        dummy_bytes = dummy_prop_path.read_bytes()
        props_all_patched = (
            prop_patch_res["replaced_props"] == 3
            and prop_patch_res["untouched"] == 1
            and (sample_props_dir / "p_head_000.ydd").read_bytes() == dummy_bytes
            and (sample_props_dir / "p_eyes_000.ydd").read_bytes() == dummy_bytes
            and (sample_props_dir / "p_ears_000.ydd").read_bytes() == dummy_bytes
            and (sample_props_dir / "p_head_diff_000_a.ytd").read_bytes() == b"KEEP_YTD"
            and (sample_backup_dir / "p_head_000.ydd").read_bytes() == b"VANILLA_HAT"
        )
        suite_passed &= print_status_result(
            "Protagonist prop patch dummies head/eyes/ears & preserves vanilla backup",
            props_all_patched,
            f"replaced={prop_patch_res['replaced_props']} untouched={prop_patch_res['untouched']}",
        )

        # 6. VToon watermarks, lilToon .mat parsing, INI upsert, and multi-SPS shader modes
        import vtoon_profile_helper
        import ped_damage_helper
        import unity_hair_bake_layer

        blank_atlas = Image.new("RGBA", (256, 256), (120, 140, 160, 255))
        stamped_atlas = vtoon_profile_helper.stamp_vtoon_watermark_block(blank_atlas, 3)
        decoded_id = vtoon_profile_helper.decode_vtoon_watermark_block(stamped_atlas)

        trans_mat = mat_dir / "Hair_Trans_VToon.mat"
        trans_mat.write_text(
            "m_Name: Hair_Trans_VToon\n"
            "m_Shader: {fileID: 4800000, guid: 3c79b10c7e0b2784aaa4c2f8dd17d55e, type: 3}\n"
            "m_CustomRenderQueue: 2460\n"
            "m_SavedProperties:\n"
            "  m_Floats:\n"
            "  - _Cull: 0\n"
            "  - _ShadowBorder: 0.5\n"
            "  m_Colors:\n"
            "  - _ShadowColor: {r: 1, g: 0.9, b: 0.92, a: 1}\n",
            encoding="utf-8",
        )
        parsed_trans = unity_hair_bake_layer.parse_unity_material(trans_mat)
        parsed_vtoon = vtoon_profile_helper.parse_liltoon_mat_file(trans_mat)
        slot_vtoon = vtoon_profile_helper.build_vtoon_slot_from_mat(
            parsed_vtoon, vtoon_profile_helper.SLOT_HAIR
        )

        ini_target = tmp_root / "vtoon_test" / "GTAVVToon.ini"
        vtoon_profile_helper.upsert_vtoon_ini_character(
            [ini_target], 1, "CharOne", "vtoon_profiles\\lut1.png", "vtoon_profiles\\mc1.png", {0: slot_vtoon}
        )
        vtoon_profile_helper.upsert_vtoon_ini_character(
            [ini_target], 2, "CharTwo", "vtoon_profiles\\lut2.png", "vtoon_profiles\\mc2.png", {4: slot_vtoon}
        )
        ini_txt = ini_target.read_text(encoding="utf-8")

        created_shaders = []
        ped_damage_helper.create_ped_hair_cutout_material(lambda sname: created_shaders.append(sname) or type("MatObj", (), {"name": sname, "node_tree": None})(), "h_cut")
        ped_damage_helper.create_ped_alpha_material(lambda sname: created_shaders.append(sname) or type("MatObj", (), {"name": sname, "node_tree": None})(), "h_alp")

        vtoon_unit_ok = (
            decoded_id == 3
            and parsed_trans.get("is_double_sided") is True
            and parsed_trans.get("alpha_mode") == "transparent"
            and abs(slot_vtoon.get("double_sided", 0.0) - 1.0) < 1e-5
            and "[Char_1]" in ini_txt
            and "[Char_2]" in ini_txt
            and created_shaders == ["ped_hair_cutout_alpha.sps", "ped_alpha.sps"]
        )
        suite_passed &= print_status_result(
            "VToon watermark, lilToon transparent shader detect, INI merge & multi-SPS materials",
            vtoon_unit_ok,
            f"watermark={decoded_id} mode={parsed_trans.get('alpha_mode')} shaders={created_shaders}",
        )

        # 7. Prefab ingest scoping, protagonist VToon char IDs, and Unity plugin non-destructive install
        import avatar_archive_helper
        import universal_gtav_rigging_layer

        mock_unity_root = tmp_root / "MockUnityProj"
        avatar_sub = mock_unity_root / "Assets" / "MyAvatar"
        other_sub = mock_unity_root / "Assets" / "OtherAvatar"
        avatar_sub.mkdir(parents=True, exist_ok=True)
        other_sub.mkdir(parents=True, exist_ok=True)
        target_prefab = avatar_sub / "MyAvatar.prefab"
        unrelated_prefab = other_sub / "OtherAvatar.prefab"
        target_prefab.write_text("%YAML 1.1\n--- !u!1 &1000\nGameObject:\n  m_Name: MyAvatar\n", encoding="utf-8")
        unrelated_prefab.write_text("%YAML 1.1\n--- !u!1 &2000\nGameObject:\n  m_Name: OtherAvatar\n", encoding="utf-8")

        ingested_prefab = avatar_archive_helper.ingest_avatar_source(target_prefab, tmp_root)
        selected_src, selected_name = universal_gtav_rigging_layer._select_scene_or_prefab(
            ingested_prefab, "MyAvatar"
        )
        protag_ids_ok = universal_gtav_rigging_layer.PROTAGONIST_VTOON_CHAR_IDS == {
            "player_zero": 1,
            "player_one": 2,
            "player_two": 3,
        }

        import repack_and_deploy_everything as repack_helper

        plugin_dir = PROJECT_ROOT_DIR / "unity_plugin"
        editor_csharp_files = sorted((plugin_dir / "Assets" / "VRCAvatar2GTAV" / "Editor").glob("*.cs"))
        csharp_lengths_ok = bool(editor_csharp_files) and all(
            len(csharp_path.read_text(encoding="utf-8").splitlines()) <= 500 for csharp_path in editor_csharp_files
        )
        existing_asset = mock_unity_root / "Assets" / "KeepMe.txt"
        existing_asset.write_text("do-not-touch", encoding="utf-8")
        legacy_plugin_dir = mock_unity_root / "Assets" / "VRC2GTAV"
        legacy_plugin_dir.mkdir(parents=True, exist_ok=True)
        (legacy_plugin_dir / "old.txt").write_text("stale", encoding="utf-8")

        sys.path.insert(0, str(plugin_dir))
        try:
            import install_unity_plugin
            installed_dest = install_unity_plugin.install_plugin(mock_unity_root)
        finally:
            if str(plugin_dir) in sys.path:
                sys.path.remove(str(plugin_dir))

        mock_gtav = tmp_root / "MockGTAV"
        mock_gtav.mkdir(parents=True, exist_ok=True)
        (mock_gtav / "dinput8.dll").write_bytes(b"ASI_LOADER")
        (mock_gtav / "ScriptHookV.dll").write_bytes(b"SHV")
        (mock_gtav / "RageOpenV.asi").write_bytes(b"MODS_READER")
        (mock_gtav / "GTAVVToon.ini").write_text("; custom\n", encoding="utf-8")
        repack_helper.sync_gtav_runtime_mods(PROJECT_ROOT_DIR, mock_gtav, overwrite_inis=False)
        runtime_status = repack_helper.inspect_gtav_runtime_prerequisites(mock_gtav)
        runtime_sync_ok = (
            runtime_status["asi_loader_ok"]
            and runtime_status["scripthookv_ok"]
            and runtime_status["mods_loader_ok"]
            and runtime_status["physbones_asi_ok"]
            and runtime_status["vtoon_asi_ok"]
            and (mock_gtav / "GTAVVToon.ini").read_text(encoding="utf-8") == "; custom\n"
        )

        win_txt = (installed_dest / "Editor" / "Vrc2GtavExporterWindow.cs").read_text(encoding="utf-8")
        prefab_list = ingested_prefab.get("prefab_files") or []
        win_split = npc_registry_helper._split_archive_hit(
            r"D:\GTAV\x64v.rpf:x64v.rpf/models/cdimages/streamedpeds_players.rpf/player_zero/player_zero.yft"
        )
        win_split_ok = win_split == (
            "D:/GTAV/x64v.rpf",
            "models/cdimages/streamedpeds_players.rpf",
            "player_zero/player_zero.yft",
        )
        unity_plugin_ok = (
            ingested_prefab.get("source_kind") == "unity_prefab"
            and ingested_prefab.get("preferred_prefab") == target_prefab.resolve()
            and target_prefab.resolve() in prefab_list
            and unrelated_prefab.resolve() not in prefab_list
            and selected_src == target_prefab.resolve()
            and isinstance(selected_name, str)
            and protag_ids_ok
            and win_split_ok
            and csharp_lengths_ok
            and runtime_sync_ok
            and not legacy_plugin_dir.exists()
            and 'Tools/VRCAvatar2GTAV/Export Avatar to GTA V' in win_txt
            and existing_asset.read_text(encoding="utf-8") == "do-not-touch"
        )
        mock_x64v = tmp_root / "mock_x64v_extracted"
        mock_players = tmp_root / "mock_players_extracted"
        mock_ped = mock_players / "player_zero"
        (mock_x64v / "models" / "cdimages").mkdir(parents=True, exist_ok=True)
        (mock_x64v / "models" / "cdimages" / "componentpeds_test.rpf").write_bytes(b"C" * 4000)
        mock_ped.mkdir(parents=True, exist_ok=True)
        (mock_ped / "accs_000_u.ydd").write_bytes(b"D" * 629)
        (mock_ped / "accs_diff_000_a_uni.ytd").write_bytes(b"V" * 100_000)
        (mock_ped / "uppr_diff_000_a_uni.ytd").write_bytes(b"Y" * 800_000)
        (mock_ped / "uppr_diff_000_b_uni.ytd").write_bytes(b"Y" * 800_000)
        (mock_ped / "uppr_diff_001_a_uni.ytd").write_bytes(b"Y" * 800_000)
        (mock_ped / "uppr_diff_002_a_uni.ytd").write_bytes(b"Y" * 800_000)

        def _fake_compact_builder(
            src_path: Path,
            dst_path: Path,
            *,
            max_diffuse_px: int,
            max_normal_px: int,
        ) -> Path:
            dst_path.write_bytes(b"K" * (1200 if max_diffuse_px >= 1024 else 400))
            return dst_path

        def _fake_dummy_builder(dst_path: Path) -> Path:
            dst_path.write_bytes(b"M" * 256)
            return dst_path

        budget_res = repack_helper.ensure_x64v_streamed_budget(
            mock_x64v,
            mock_players,
            safe_max_bytes=820_000,
            compact_builder=_fake_compact_builder,
            dummy_builder=_fake_dummy_builder,
        )
        budget_ok = (
            budget_res["compacted"]
            and budget_res["replaced_files"] == 4
            and (mock_ped / "uppr_diff_000_a_uni.ytd").stat().st_size == 800_000
            and (mock_ped / "uppr_diff_000_b_uni.ytd").stat().st_size == 400
            and (mock_ped / "uppr_diff_001_a_uni.ytd").stat().st_size == 1200
            and (mock_ped / "uppr_diff_002_a_uni.ytd").stat().st_size == 1200
            and (mock_ped / "accs_diff_000_a_uni.ytd").stat().st_size == 256
        )

        import shutil
        import subprocess
        import tarfile
        import unittest.mock
        import error_handler_helper as err_helper

        workspace_bundled = err_helper.resolve_workspace_root(
            tmp_root / "SomeUnityProj" / "Assets" / "VRCAvatar2GTAV" / "Toolchain"
        )
        workspace_standalone = err_helper.resolve_workspace_root(tmp_root / "StandaloneRepo")
        workspace_redirect_ok = (
            workspace_bundled == (tmp_root / "SomeUnityProj" / "VRCAvatar2GTAV_Work").resolve()
            and workspace_standalone == (tmp_root / "StandaloneRepo").resolve()
        )

        # Verify texture_overrides + atlas_size=512 + normal_size=64 cleanly with mocked rage build
        tex_alt = mat_dir / "OverrideTex.png"
        Image.new("RGBA", (32, 32), (25, 220, 45, 255)).save(tex_alt)
        ovr_out = tmp_root / "atlas_ovr_out"
        fake_fbx_ovr = mat_dir / "DummyModel.fbx"
        fake_fbx_ovr.write_bytes(b"Kaydara FBX Binary  \x00\x1a\x00")
        alpha_mat.write_text("m_Name: DressMat\n", encoding="utf-8")

        def _fake_rage_run(cmd_args, **_kwargs):
            if "-o" in cmd_args:
                out_idx = cmd_args.index("-o") + 1
                Path(cmd_args[out_idx]).write_bytes(b"RSC7MOCK")
            return subprocess.CompletedProcess(cmd_args, 0, "", "")

        with (
            unittest.mock.patch.object(universal_atlas_builder.subprocess, "run", side_effect=_fake_rage_run),
            unittest.mock.patch.object(
                universal_atlas_builder.npc_registry_helper,
                "build_safe_rage_cmd",
                side_effect=lambda *cmd_args, **_unused: ["rage", *cmd_args],
            ),
            unittest.mock.patch.object(
                universal_atlas_builder.project_paths,
                "get_rage_cli",
                return_value="rage",
            ),
        ):
            with unittest.mock.patch.object(
                universal_atlas_builder,
                "collect_avatar_materials",
                return_value={
                    "DressMat": {
                        "main_tex": str(tex_img_path),
                        "color_rgba": [0.2, 0.2, 0.9, 1.0],
                        "bump_tex": str(tex_img_path),
                        "bump_scale": 0.5,
                        "emission_tex": None,
                        "emission_rgba": [0.0, 0.0, 0.0, 1.0],
                        "alpha_mask_tex": None,
                        "alpha_mask_scale": 1.0,
                        "alpha_mask_val": 0.0,
                        "alpha_mode": "opaque",
                        "is_double_sided": False,
                        "cull_mode": 2.0,
                        "cutoff": 0.5,
                        "mat_path": str(alpha_mat),
                    }
                },
            ):
                atlas_ovr_res = universal_atlas_builder.build_universal_avatar_atlas(
                    ped_name="player_zero",
                    project_dir=tmp_root,
                    scene_or_prefab=None,
                    source_fbx=fake_fbx_ovr,
                    output_dir=ovr_out,
                    atlas_size=512,
                    normal_size=64,
                    texture_overrides={"DressMat": str(tex_alt)},
                    vtoon_char_id=0,
                    sync_to_game=False,
                )
        normal_check_size = Image.open(atlas_ovr_res["normal_png"]).size
        diff_px = Image.open(atlas_ovr_res["atlas_png"]).getpixel((16, 16))
        atlas_res_ok = (
            atlas_ovr_res["atlas_size"] == 512
            and normal_check_size == (64, 64)
            and diff_px[1] > 180
        )

        # Verify explicit secondary_atlas_size=512 proactively compacts uppr_diff_001+
        mock_sec_ped = tmp_root / "sec_players" / "player_zero"
        mock_sec_x64v = tmp_root / "sec_x64v"
        (mock_sec_x64v / "models" / "cdimages").mkdir(parents=True, exist_ok=True)
        mock_sec_ped.mkdir(parents=True, exist_ok=True)
        (mock_sec_ped / "uppr_diff_000_a_uni.ytd").write_bytes(b"A" * 800_000)
        (mock_sec_ped / "uppr_diff_001_a_uni.ytd").write_bytes(b"B" * 800_000)
        sec_res = repack_helper.ensure_x64v_streamed_budget(
            mock_sec_x64v,
            tmp_root / "sec_players",
            safe_max_bytes=50_000_000,
            secondary_atlas_size=512,
            compact_builder=_fake_compact_builder,
            dummy_builder=_fake_dummy_builder,
        )
        sec_budget_ok = (
            sec_res["compacted"]
            and (mock_sec_ped / "uppr_diff_000_a_uni.ytd").stat().st_size == 800_000
            and (mock_sec_ped / "uppr_diff_001_a_uni.ytd").stat().st_size == 400
        )

        # Verify build_unitypackage bundles complete Toolchain & produces clean .unitypackage
        pkg_build_stage = tmp_root / "pkg_stage"
        pkg_plugin_copy = pkg_build_stage / "VRCAvatar2GTAV"
        shutil.copytree(
            plugin_dir / "Assets" / "VRCAvatar2GTAV",
            pkg_plugin_copy,
            ignore=shutil.ignore_patterns("Toolchain"),
        )
        out_pkg_file = pkg_build_stage / "TestOut.unitypackage"
        sys.path.insert(0, str(plugin_dir))
        try:
            import build_unitypackage

            built_pkg = build_unitypackage.create_unitypackage(
                repo_root=PROJECT_ROOT_DIR,
                plugin_root=pkg_plugin_copy,
                output_path=out_pkg_file,
            )
        finally:
            if str(plugin_dir) in sys.path:
                sys.path.remove(str(plugin_dir))

        packed_asset_paths: List[str] = []
        with tarfile.open(built_pkg, "r:gz") as pkg_tar:
            for member in pkg_tar.getmembers():
                if member.name.endswith("/pathname") and member.isfile():
                    raw_handle = pkg_tar.extractfile(member)
                    if raw_handle is not None:
                        packed_asset_paths.append(raw_handle.read().decode("utf-8").strip())
        pkg_paths_ok = (
            built_pkg.is_file()
            and "Assets/VRCAvatar2GTAV/Editor/Vrc2GtavTexturesPanel.cs" in packed_asset_paths
            and "Assets/VRCAvatar2GTAV/Toolchain/run_mod_manager.py" in packed_asset_paths
            and "Assets/VRCAvatar2GTAV/Toolchain/2_Michael_Shinano_EternalReunion/5_rpf_package/GTAVPhysBones.asi" in packed_asset_paths
            and "Assets/VRCAvatar2GTAV/Toolchain/2_Michael_Shinano_EternalReunion/5_rpf_package/GTAVVToon.asi" in packed_asset_paths
            and "Assets/VRCAvatar2GTAV/Toolchain/_deploy_tools/head_000_r.ydd" in packed_asset_paths
            and not any(
                pth.lower().endswith((".rpf", ".yft", ".ytd", ".dds", ".fbx", ".dll", ".exe"))
                or "/vtoon_profiles/" in pth.lower()
                or pth.lower().endswith("/vrc2gtav.cfg")
                for pth in packed_asset_paths
            )
        )

        # Enforce byte-for-byte mirror parity between Google Drive source and Unity Toolchain bundle
        bundled_toolchain_dir = plugin_dir / "Assets" / "VRCAvatar2GTAV" / "Toolchain"
        toolchain_mismatches: List[str] = []
        if bundled_toolchain_dir.is_dir():
            for toolchain_file in sorted(bundled_toolchain_dir.rglob("*")):
                if not toolchain_file.is_file() or toolchain_file.name.endswith(".meta"):
                    continue
                rel_toolchain = toolchain_file.relative_to(bundled_toolchain_dir)
                if rel_toolchain.as_posix() == "vrc2gtav.cfg" or "__pycache__" in rel_toolchain.parts:
                    continue
                orig_file = PROJECT_ROOT_DIR / rel_toolchain
                if not orig_file.is_file() or toolchain_file.read_bytes() != orig_file.read_bytes():
                    toolchain_mismatches.append(rel_toolchain.as_posix())
        disc_csharp = (plugin_dir / "Assets" / "VRCAvatar2GTAV" / "Editor" / "Vrc2GtavConfigDiscovery.cs").read_text(encoding="utf-8")
        cmd_csharp = (plugin_dir / "Assets" / "VRCAvatar2GTAV" / "Editor" / "Vrc2GtavCommandBuilder.cs").read_text(encoding="utf-8")
        bundled_first_ok = (
            not toolchain_mismatches
            and "if (IsValidRepoRoot(bundled)) return Path.GetFullPath(bundled);" in disc_csharp
            and "PreferBundledToolchain" in cmd_csharp
        )
        suite_passed &= print_status_result(
            "Prefab scoped ingest, protagonist VToon IDs & non-destructive Unity plugin install",
            unity_plugin_ok and budget_ok and workspace_redirect_ok and atlas_res_ok and sec_budget_ok and pkg_paths_ok and bundled_first_ok and len(editor_csharp_files) == 9,
            f"kind={ingested_prefab.get('source_kind')} cs_files={len(editor_csharp_files)} pkg_entries={len(packed_asset_paths)} bundled_first={bundled_first_ok} mismatches={len(toolchain_mismatches)}",
        )

    return suite_passed


