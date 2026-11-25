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
    extra_checks_passed = _verify_model_prefab_menu_toggle_and_skin_selection()
    return print_status_result(
        "MA ShapeChanger Delete/Set, BlendshapeSync RemapCurve & manual Shrink_* culling",
        suite_ok and segment_guard_ok and extra_checks_passed,
        f"yaml={yaml_parse_ok} rules={blender_rules_ok} noctis={noctis_ok} seg_guard={segment_guard_ok} extra={extra_checks_passed}",
    )


def _verify_model_prefab_menu_toggle_and_skin_selection() -> bool:
    """Verify skin/primary-FBX selection, MA MenuItem defaults, Model Prefab overrides, and contour sync."""
    import tempfile
    from types import SimpleNamespace
    import blendshape_helper
    import blendshape_unity_yaml_layer
    import modular_avatar_helper
    import modular_avatar_yaml_layer
    import universal_gtav_rigging_layer

    skin_checks_passed = (
        not blendshape_helper.is_body_or_face_skin_mesh("Head Item Base")
        and not blendshape_helper.is_body_or_face_skin_mesh("Attachable sleeves")
        and not blendshape_helper.is_body_or_face_skin_mesh("Tights")
        and not blendshape_helper.is_body_or_face_skin_mesh("Bunny Tail")
        and blendshape_helper.is_body_or_face_skin_mesh("Body_base")
        and blendshape_helper.is_body_or_face_skin_mesh("Head")
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        root_dir = Path(temp_dir)
        avatar_fbx = root_dir / "Avatar_kisekae.fbx"
        accessory_fbx = root_dir / "Accessory_Ear.fbx"
        avatar_fbx.write_bytes(b"Kaydara FBX Binary  \x00\x1a\x00")
        accessory_fbx.write_bytes(b"Kaydara FBX Binary  \x00\x1a\x00")
        orig_blendshape_reader = blendshape_unity_yaml_layer.extract_fbx_blendshape_names
        try:
            blendshape_unity_yaml_layer.extract_fbx_blendshape_names = lambda _path: {}
            mock_plan = {
                "active_meshes_by_fbx": {
                    str(avatar_fbx): ["Body_base", "Body"],
                    str(accessory_fbx): ["Head Item Base", "Accessory Ear"],
                },
            }
            chosen_fbx = universal_gtav_rigging_layer.select_primary_avatar_fbx(
                [accessory_fbx, avatar_fbx], ma_plan=mock_plan
            )
            primary_fbx_passed = chosen_fbx == avatar_fbx
        finally:
            blendshape_unity_yaml_layer.extract_fbx_blendshape_names = orig_blendshape_reader

        menu_scene = root_dir / "MenuToggleScene.prefab"
        menu_yaml = (
            "%YAML 1.1\n"
            "%TAG !u! tag:unity3d.com,2011:\n"
            "--- !u!1 &101\n"
            "GameObject:\n"
            "  m_Name: TestAvatar\n"
            "  m_IsActive: 1\n"
            "--- !u!4 &201\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 101}\n"
            "  m_Father: {fileID: 0}\n"
            "--- !u!1 &102\n"
            "GameObject:\n"
            "  m_Name: Tights\n"
            "  m_IsActive: 1\n"
            "--- !u!4 &202\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 102}\n"
            "  m_Father: {fileID: 201}\n"
            "--- !u!137 &302\n"
            "SkinnedMeshRenderer:\n"
            "  m_GameObject: {fileID: 102}\n"
            "  m_Enabled: 1\n"
            "  m_Mesh: {fileID: 4300000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 3}\n"
            "--- !u!1 &103\n"
            "GameObject:\n"
            "  m_Name: StylingOffBtn\n"
            "  m_IsActive: 1\n"
            "--- !u!4 &203\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 103}\n"
            "  m_Father: {fileID: 201}\n"
            "--- !u!114 &403\n"
            "MonoBehaviour:\n"
            "  m_GameObject: {fileID: 103}\n"
            "  m_Enabled: 1\n"
            f"  m_Script: {{fileID: 11500000, guid: {modular_avatar_yaml_layer.MA_MENU_ITEM_GUID}, type: 3}}\n"
            "  isDefault: 0\n"
            "--- !u!114 &503\n"
            "MonoBehaviour:\n"
            "  m_GameObject: {fileID: 103}\n"
            "  m_Enabled: 1\n"
            f"  m_Script: {{fileID: 11500000, guid: {modular_avatar_yaml_layer.MA_OBJECT_TOGGLE_GUID}, type: 3}}\n"
            "  m_objects:\n"
            "  - Object:\n"
            "      referencePath: Tights\n"
            "    Active: 0\n"
            "--- !u!1 &104\n"
            "GameObject:\n"
            "  m_Name: SiblingDisabledOutfit\n"
            "  m_IsActive: 0\n"
            "--- !u!4 &204\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 104}\n"
            "  m_Father: {fileID: 201}\n"
            "--- !u!1 &105\n"
            "GameObject:\n"
            "  m_Name: Tights\n"
            "  m_IsActive: 1\n"
            "--- !u!4 &205\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 105}\n"
            "  m_Father: {fileID: 204}\n"
            "--- !u!137 &305\n"
            "SkinnedMeshRenderer:\n"
            "  m_GameObject: {fileID: 105}\n"
            "  m_Enabled: 1\n"
            "  m_Mesh: {fileID: 4300000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 3}\n"
            "--- !u!1 &106\n"
            "GameObject:\n"
            "  m_Name: OptionalCuff\n"
            "  m_IsActive: 1\n"
            "--- !u!4 &206\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 106}\n"
            "  m_Father: {fileID: 201}\n"
            "--- !u!137 &306\n"
            "SkinnedMeshRenderer:\n"
            "  m_GameObject: {fileID: 106}\n"
            "  m_Enabled: 1\n"
            "  m_Mesh: {fileID: 4300000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 3}\n"
            "--- !u!114 &506\n"
            "MonoBehaviour:\n"
            "  m_GameObject: {fileID: 103}\n"
            "  m_Enabled: 1\n"
            "  m_Name: DefaultDisabler\n"
            "--- !u!114 &507\n"
            "MonoBehaviour:\n"
            "  m_GameObject: {fileID: 101}\n"
            "  m_Enabled: 1\n"
            f"  m_Script: {{fileID: 11500000, guid: {modular_avatar_yaml_layer.MA_OBJECT_TOGGLE_GUID}, type: 3}}\n"
            "  m_objects:\n"
            "  - Object:\n"
            "      referencePath: OptionalCuff\n"
            "    Active: 0\n"
        )
        menu_scene.write_text(menu_yaml, encoding="utf-8")
        menu_plan = modular_avatar_helper.build_modular_avatar_bake_plan(
            menu_scene, avatar_name="TestAvatar", assets_root=temp_dir, resolve_materials=False
        )
        menu_toggle_passed = (
            "Tights" in menu_plan.get("active_meshes", ())
            and "Tights" not in menu_plan.get("disabled_meshes", ())
            and "OptionalCuff" in menu_plan.get("disabled_meshes", ())
        )

        mat_dir = root_dir / "1_Hoodie"
        mat_dir.mkdir(parents=True, exist_ok=True)
        default_mat_guid = "11111111111111111111111111111111"
        override_mat_guid = "22222222222222222222222222222222"
        default_mat = mat_dir / "DefaultMat.mat"
        override_mat = mat_dir / "NavyMat.mat"
        default_mat.write_text("%YAML 1.1\nMaterial:\n  m_Name: DefaultMat\n", encoding="utf-8")
        override_mat.write_text("%YAML 1.1\nMaterial:\n  m_Name: NavyMat\n", encoding="utf-8")
        (root_dir / "ModelOutfit.fbx.meta").write_text(
            "fileFormatVersion: 2\nModelImporter:\n  externalObjects:\n"
            "  - first:\n      type: UnityEngine:Material\n      assembly: UnityEngine.CoreModule\n"
            "      name: HoodSlot\n"
            f"    second: {{fileID: 2100000, guid: {default_mat_guid}, type: 2}}\n",
            encoding="utf-8",
        )
        model_fbx = root_dir / "ModelOutfit.fbx"
        model_fbx.write_bytes(b"Kaydara FBX Binary  \x00\x1a\x00")
        orig_mesh_slots = blendshape_unity_yaml_layer.extract_fbx_model_meshes_and_materials
        try:
            blendshape_unity_yaml_layer.extract_fbx_model_meshes_and_materials = lambda _path: {
                "HoodMesh": ["HoodSlot"],
                "PantiesMesh": ["HoodSlot"],
            }
            fake_mods = [
                {"target_fid": "7001", "property": "m_objects.Array.data[0].Object.targetObject", "value": "", "ref_fid": "9901", "ref_guid": ""},
                {"target_fid": "7001", "property": "m_objects.Array.data[0].Object.referencePath", "value": "OutfitRoot/PantiesMesh", "ref_fid": "0", "ref_guid": ""},
                {"target_fid": "9901", "property": "m_TagString", "value": "EditorOnly", "ref_fid": "0", "ref_guid": ""},
                {"target_fid": "8001", "property": "m_Materials.Array.data[0]", "value": "", "ref_fid": "2100000", "ref_guid": override_mat_guid},
            ]
            payload_res = blendshape_unity_yaml_layer.collect_model_prefab_instance_payload(
                model_fbx,
                fake_mods,
                model_fbx,
                lambda _guids, _anchor: {default_mat_guid: default_mat, override_mat_guid: override_mat},
                lambda guids, _anchor, _resolved: [{"name": "NavyMat" if gid == override_mat_guid else "DefaultMat"} for gid in guids],
            )
            model_payload_passed = (
                payload_res.get("mesh_names") == ["HoodMesh"]
                and payload_res.get("disabled_meshes") == ["PantiesMesh"]
                and payload_res.get("mesh_materials", {}).get("HoodMesh", [{}])[0].get("name") == "NavyMat"
            )
            blendshape_unity_yaml_layer.extract_fbx_model_meshes_and_materials = lambda _path: {
                "HandleMesh": [],
                "MoveMesh": [],
            }
            disabled_gizmo_mods = [
                {"target_fid": "1001", "property": "m_IsActive", "value": "0", "ref_fid": "0", "ref_guid": ""},
                {"target_fid": "1002", "property": "m_IsActive", "value": "0", "ref_fid": "0", "ref_guid": ""},
                {"target_fid": "1003", "property": "m_LocalScale.x", "value": "0", "ref_fid": "0", "ref_guid": ""},
                {"target_fid": "1004", "property": "m_LocalScale.x", "value": "0", "ref_fid": "0", "ref_guid": ""},
            ]
            gizmo_payload = blendshape_unity_yaml_layer.collect_model_prefab_instance_payload(
                model_fbx,
                disabled_gizmo_mods,
                model_fbx,
                lambda _guids, _anchor: {},
                lambda _guids, _anchor, _resolved: [],
            )
            gizmo_state = {
                "active_meshes": [],
                "active_meshes_by_fbx": {},
                "mesh_materials": {},
                "active_mat_guids_set": set(),
                "explicit_disabled": set(),
                "fbx_instances": [],
                "attach_items": [],
            }
            registered_fbx_list = []
            blendshape_unity_yaml_layer.register_model_prefab_instance_in_plan(
                model_fbx,
                "scene_gizmo",
                gizmo_payload,
                None,
                True,
                lambda fbx_arg, is_outfit=False: registered_fbx_list.append(fbx_arg),
                gizmo_state,
            )
            model_payload_passed = (
                model_payload_passed
                and gizmo_payload.get("mesh_names") == []
                and set(gizmo_payload.get("disabled_meshes", ())) == {"HandleMesh", "MoveMesh"}
                and not registered_fbx_list
                and not gizmo_state["fbx_instances"]
            )
        finally:
            blendshape_unity_yaml_layer.extract_fbx_model_meshes_and_materials = orig_mesh_slots

    class _MockContourBlocks:
        def __init__(self, entries: dict) -> None:
            self.entries = {name: SimpleNamespace(name=name, value=float(val)) for name, val in entries.items()}

        def __contains__(self, key_name: str) -> bool:
            return key_name in self.entries

        def __getitem__(self, key_name: str) -> object:
            return self.entries[key_name]

        def __iter__(self):
            return iter(self.entries.values())

    body_obj = SimpleNamespace(name="Body_base", type="MESH", data=SimpleNamespace(shape_keys=SimpleNamespace(key_blocks=_MockContourBlocks({"Breasts_big": 1.0, "Hip_big": 0.75}))))
    jacket_obj = SimpleNamespace(name="HoodieMesh", type="MESH", data=SimpleNamespace(shape_keys=SimpleNamespace(key_blocks=_MockContourBlocks({"Breasts_big": 0.0, "Hip_big": 0.0}))))
    explicit_obj = SimpleNamespace(name="OverrideCoat", type="MESH", data=SimpleNamespace(shape_keys=SimpleNamespace(key_blocks=_MockContourBlocks({"Breasts_big": 0.0}))))
    contour_plan = {"loaded": True, "shape_changer_weights": {"OverrideCoat": {"Breasts_big": 0.0}}, "blendshape_syncs": []}
    contour_bpy = SimpleNamespace(data=SimpleNamespace(objects=[body_obj, jacket_obj, explicit_obj]))
    blendshape_helper.apply_ma_shape_changers_and_syncs(contour_bpy, contour_plan)
    contour_passed = (
        abs(float(jacket_obj.data.shape_keys.key_blocks["Breasts_big"].value) - 1.0) < 1e-6
        and abs(float(jacket_obj.data.shape_keys.key_blocks["Hip_big"].value) - 0.75) < 1e-6
        and abs(float(explicit_obj.data.shape_keys.key_blocks["Breasts_big"].value)) < 1e-6
    )

    fbx_points_sample = {"Head": (0.0, 0.0, 1.40), "BunnyEarL": (0.03, 0.0, 1.60)}
    matched_arm_scale_corr = modular_avatar_yaml_layer.compute_bone_unit_scale_correction(
        fbx_points_sample,
        {
            "Head": [[0.0615, 0.0, 0.0, 0.0], [0.0, 0.0615, 0.0, 0.0], [0.0, 0.0, 0.0615, 1.26], [0.0, 0.0, 0.0, 1.0]],
            "BunnyEarL": [[0.0615, 0.0, 0.0, 0.027], [0.0, 0.0615, 0.0, 0.0], [0.0, 0.0, 0.0615, 1.44], [0.0, 0.0, 0.0, 1.0]],
        },
        fbx_col_norm=0.0683,
    )
    centimeter_mismatch_corr = modular_avatar_yaml_layer.compute_bone_unit_scale_correction(
        fbx_points_sample,
        {
            "Head": [[100.0, 0.0, 0.0, 0.0], [0.0, 100.0, 0.0, 0.0], [0.0, 0.0, 100.0, 1.40], [0.0, 0.0, 0.0, 1.0]],
            "BunnyEarL": [[100.0, 0.0, 0.0, 0.03], [0.0, 100.0, 0.0, 0.0], [0.0, 0.0, 100.0, 1.60], [0.0, 0.0, 0.0, 1.0]],
        },
        fbx_col_norm=1.0,
    )
    bone_unit_scale_passed = abs(matched_arm_scale_corr - 1.0) < 1e-6 and abs(centimeter_mismatch_corr - 0.01) < 1e-4

    import subprocess
    from PIL import Image as pil_image
    import npc_registry_helper
    import ped_damage_helper
    import universal_atlas_builder

    atlas_grid_passed = False
    with tempfile.TemporaryDirectory() as atlas_temp_dir:
        atlas_project_dir = Path(atlas_temp_dir) / "Proj"
        tex_dir = atlas_project_dir / "Assets" / "Textures"
        mats_dir = atlas_project_dir / "Assets" / "Materials"
        out_atlas_dir = Path(atlas_temp_dir) / "Out"
        tex_dir.mkdir(parents=True, exist_ok=True)
        mats_dir.mkdir(parents=True, exist_ok=True)
        source_dummy_fbx = atlas_project_dir / "Assets" / "Avatar.fbx"
        source_dummy_fbx.write_bytes(b"Kaydara FBX Binary  \x00\x1a\x00")
        for idx in range(20):
            tex_file = tex_dir / f"tex_{idx:02d}.png"
            pil_image.new("RGB", (8, 8), ((idx * 11 + 20) % 255, (idx * 7 + 40) % 255, 180)).save(tex_file)
            tex_guid = f"aaaa000000000000000000000000{idx:04x}"
            (tex_dir / f"tex_{idx:02d}.png.meta").write_text(f"fileFormatVersion: 2\nguid: {tex_guid}\n", encoding="utf-8")
            mat_file = mats_dir / f"mat_{idx:02d}.mat"
            mat_file.write_text(
                "%YAML 1.1\nMaterial:\n"
                f"  m_Name: Mat_{idx:02d}\n"
                "  m_SavedProperties:\n"
                "    m_TexEnvs:\n"
                "    - _MainTex:\n"
                f"        m_Texture: {{fileID: 2800000, guid: {tex_guid}, type: 3}}\n"
                "    m_Colors:\n"
                "    - _Color: {r: 1, g: 1, b: 1, a: 1}\n",
                encoding="utf-8",
            )
        orig_rage_cmd = npc_registry_helper.build_safe_rage_cmd
        orig_get_rage = universal_atlas_builder.project_paths.get_rage_cli
        orig_subproc_run = subprocess.run
        orig_enforce_ytd = ped_damage_helper.enforce_ytd_rpf7_size_budget
        orig_val_rpf7 = ped_damage_helper.validate_rpf7_resource_file
        try:
            npc_registry_helper.build_safe_rage_cmd = lambda *args, **kwargs: ["mock_rage", *args]
            universal_atlas_builder.project_paths.get_rage_cli = lambda: "mock_rage"
            subprocess.run = lambda *args, **kwargs: (out_atlas_dir / "test_npc_atlas.ytd").write_bytes(b"RSC7")
            ped_damage_helper.enforce_ytd_rpf7_size_budget = lambda *_args, **_kwargs: None
            ped_damage_helper.validate_rpf7_resource_file = lambda *_args, **_kwargs: None
            atlas_res = universal_atlas_builder.build_universal_avatar_atlas(
                ped_name="test_npc",
                project_dir=atlas_project_dir,
                scene_or_prefab=None,
                source_fbx=source_dummy_fbx,
                output_dir=out_atlas_dir,
                atlas_size=512,
                vtoon_char_id=0,
                sync_to_game=False,
            )
            atlas_mats = atlas_res.get("materials", {})
            atlas_grid_passed = (
                atlas_res.get("grid_dim") == 5
                and len(atlas_mats) == 20
                and "Mat_19" in atlas_mats
            )
        finally:
            npc_registry_helper.build_safe_rage_cmd = orig_rage_cmd
            universal_atlas_builder.project_paths.get_rage_cli = orig_get_rage
            subprocess.run = orig_subproc_run
            ped_damage_helper.enforce_ytd_rpf7_size_budget = orig_enforce_ytd
            ped_damage_helper.validate_rpf7_resource_file = orig_val_rpf7

    glass_lens_passed = False
    with tempfile.TemporaryDirectory(prefix="vrc2gtav_dark_lens_") as lens_tmp_dir:
        import numpy as numpy_mod
        import unity_hair_bake_layer
        import vtoon_profile_helper

        lens_root = Path(lens_tmp_dir)
        dark_lens_mat = lens_root / "Custom_Lens.mat"
        dark_lens_mat.write_text(
            "m_Name: Custom_Lens\n"
            "m_Shader: {fileID: 4800000, guid: 6a77405f7dfdc1447af58854c7f43f39, type: 3}\n"
            "m_CustomRenderQueue: 3500\n"
            "m_SavedProperties:\n"
            "  m_Floats:\n"
            "  - _AlphaMaskMode: 1\n"
            "  - _AlphaMaskScale: -1\n"
            "  - _AlphaMaskValue: 1.117\n"
            "  - _UseMatCap: 1\n"
            "  - _MatCapBlendMode: 1\n"
            "  m_Colors:\n"
            "  - _Color: {r: 0, g: 0, b: 0, a: 1}\n",
            encoding="utf-8",
        )
        dark_tex_guid = "abcd1234abcd1234abcd1234abcd1234"
        dark_cloth_tex = lens_root / "dark_cloth.png"
        pil_image.new("RGBA", (32, 32), (10, 10, 12, 255)).save(dark_cloth_tex)
        (lens_root / "dark_cloth.png.meta").write_text(f"fileFormatVersion: 2\nguid: {dark_tex_guid}\n", encoding="utf-8")
        dark_cloth_mat = lens_root / "Opaque_Cloth.mat"
        dark_cloth_mat.write_text(
            "m_Name: Opaque_Cloth\n"
            "m_CustomRenderQueue: 2000\n"
            "m_SavedProperties:\n"
            "  m_TexEnvs:\n"
            "  - _MainTex:\n"
            f"      m_Texture: {{fileID: 2800000, guid: {dark_tex_guid}, type: 3}}\n"
            "      m_Scale: {x: 1, y: 1}\n"
            "      m_Offset: {x: 0, y: 0}\n"
            "  m_Colors:\n"
            "  - _Color: {r: 1, g: 1, b: 1, a: 1}\n",
            encoding="utf-8",
        )
        lens_bake_res = unity_hair_bake_layer.bake_liltoon_mat_to_image(
            dark_lens_mat, tile_size=(64, 64), preserve_alpha=True, unity_assets_root=lens_root
        )
        cloth_bake_res = unity_hair_bake_layer.bake_liltoon_mat_to_image(
            dark_cloth_mat, tile_size=(64, 64), preserve_alpha=False, unity_assets_root=lens_root
        )
        glass_slot_cfg = vtoon_profile_helper.build_vtoon_slot_from_mat(
            vtoon_profile_helper.parse_liltoon_mat_file(dark_lens_mat),
            slot_type=vtoon_profile_helper.SLOT_TRANSPARENT,
        )
        if lens_bake_res is not None and cloth_bake_res is not None:
            lens_arr = numpy_mod.array(lens_bake_res[0].convert("RGBA"))
            cloth_arr = numpy_mod.array(cloth_bake_res[0].convert("RGBA"))
            glass_lens_passed = (
                25 <= int(lens_arr[32, 32, 3]) <= 38
                and float(lens_arr[:, :, :3].mean()) >= 150.0
                and int(cloth_arr[32, 32, 3]) == 255
                and float(cloth_arr[:, :, :3].mean()) <= 30.0
                and glass_slot_cfg.get("use_matcap") == 1.0
                and float(glass_slot_cfg.get("specular_intensity", 0.0)) >= 0.75
                and float(glass_slot_cfg.get("shadow_strength", 1.0)) <= 0.16
            )

    shinano_checks_passed = True
    shinano_scene = Path("E:/waifuv4/Assets/Shinano.unity") if sys.platform.startswith("win") else Path("/mnt/e/waifuv4/Assets/Shinano.unity")
    if shinano_scene.is_file():
        hollow_plan = modular_avatar_helper.build_modular_avatar_bake_plan(shinano_scene, avatar_name="Shinano Hollow Boxer", resolve_materials=True)
        bunny_plan = modular_avatar_helper.build_modular_avatar_bake_plan(shinano_scene, avatar_name="Shinano 断罪 Bunny", resolve_materials=False)
        bunny_fbx = universal_gtav_rigging_layer.select_primary_avatar_fbx(
            [Path(item) for item in list(bunny_plan.get("base_fbx_paths", ())) + list(bunny_plan.get("extra_fbx_paths", ()))],
            ma_plan=bunny_plan,
        )
        shinano_checks_passed = (
            {"Hollow1_Hoodie", "Hollow2_Bra", "Hollow2_Slippers", "Hollow3_HeadSet"}.issubset(set(hollow_plan.get("active_meshes", ())))
            and {"Hollow2_Panties", "Hollow3_Headset_strap"}.issubset(set(hollow_plan.get("disabled_meshes", ())))
            and "Hollow2_Panties" not in hollow_plan.get("active_meshes", ())
            and "BodyModel" not in hollow_plan.get("active_meshes", ())
            and "HandleMesh" not in hollow_plan.get("active_meshes", ())
            and not any("APS_" in path_str for path_str in hollow_plan.get("extra_fbx_paths", ()))
            and bool(bunny_fbx and bunny_fbx.name == "Shinano_kisekae.fbx")
            and {"Tights", "Attachable sleeves", "Harness Belt 1"}.issubset(set(bunny_plan.get("active_meshes", ())))
            and "Tights" not in bunny_plan.get("disabled_meshes", ())
            and "BodyModel" not in bunny_plan.get("active_meshes", ())
            and not any("APS_" in path_str for path_str in bunny_plan.get("extra_fbx_paths", ()))
        )
    return (
        skin_checks_passed
        and primary_fbx_passed
        and menu_toggle_passed
        and model_payload_passed
        and contour_passed
        and bone_unit_scale_passed
        and atlas_grid_passed
        and glass_lens_passed
        and shinano_checks_passed
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
