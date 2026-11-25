#!/usr/bin/env python3
"""
test_suite_unity_physbones_layer.py
===================================
Layer 2 of 4 for automated project validation (`test_mod_suite`).

Validates Unity `.unity` scene scale/transform parsing, custom hair fallback
order, 2K calibration curves, VRChat PhysBones extraction, ELF tag collision-free
<=63-bone packing, priority truncation, and orphaned old-dress chain pruning.
"""

import os
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

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
        packed_skirt_breast = physbone_helper.pack_physbone_chains_to_gtav_budget(
            heavy_custom_spokes[:9] + [_make_spoke("Breast_1.L", "SKEL_Spine2", 2), _make_spoke("Breast_1.R", "SKEL_Spine2", 2)] + [_make_spoke(f"Skirt_{sk_i}", "SKEL_Pelvis", 5) for sk_i in range(18)] + [_make_spoke("Aho", "SKEL_Head", 3)],
            gtav_prefix="PB_SkB",
            max_custom_bones=physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED,
        )
        breast_skirt_ok = {"breast_1_l", "breast_1_r", "aho"} <= set(packed_skirt_breast.get("chains", {})) and len(packed_skirt_breast.get("custom_bones", [])) <= physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED
        suite_passed &= print_status_result(
            i18n.translate("tests.physbones_priority_pack"),
            bool(builtin_zero_drops_ok and light_keeps_all_ok and priority_heavy_ok and breast_skirt_ok),
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

        import types as types_mod
        import eye_blink_helper as blink_mod

        def _make_pt(pos_x: float, pos_y: float, pos_z: float):
            return types_mod.SimpleNamespace(
                co=types_mod.SimpleNamespace(x=pos_x, y=pos_y, z=pos_z)
            )

        mock_face = types_mod.SimpleNamespace(
            matrix_world=None,
            data=types_mod.SimpleNamespace(
                vertices=[
                    types_mod.SimpleNamespace(index=0),
                    types_mod.SimpleNamespace(index=1),
                    types_mod.SimpleNamespace(index=2),
                ],
                shape_keys=types_mod.SimpleNamespace(
                    key_blocks=[
                        types_mod.SimpleNamespace(
                            name="Basis",
                            data=[
                                _make_pt(0.0, 0.0, 1.50),
                                _make_pt(0.0, 0.0, 1.48),
                                _make_pt(0.0, 0.0, 1.60),
                            ],
                        ),
                        types_mod.SimpleNamespace(
                            name="vrc.v_aa",
                            data=[
                                _make_pt(0.0, 0.0, 1.495),   # -5mm drop
                                _make_pt(0.0, 0.0, 1.470),   # -10mm full jaw drop
                                _make_pt(0.0, 0.0, 1.601),   # non-mouth upper vertex
                            ],
                        ),
                    ]
                ),
            ),
        )
        jaw_shut = blink_mod.extract_facial_jaw_weights(mock_face, mouth_open_strength=0.0)
        jaw_def = blink_mod.extract_facial_jaw_weights(mock_face, mouth_open_strength=None)
        jaw_wide = blink_mod.extract_facial_jaw_weights(mock_face, mouth_open_strength=0.85)
        cs_editor_dir = PROJECT_ROOT_DIR / "unity_plugin" / "Assets" / "VRCAvatar2GTAV" / "Editor"
        cs_win_file = cs_editor_dir / "Vrc2GtavExporterWindow.cs"
        cs_cmd_file = cs_editor_dir / "Vrc2GtavCommandBuilder.cs"
        cs_ini_file = cs_editor_dir / "Vrc2GtavIniAndWsl.cs"
        mouth_ok = (
            abs(blink_mod.resolve_mouth_open_strength(None) - 0.70) < 1e-6
            and abs(blink_mod.resolve_mouth_open_strength(0.0, {"mouth_open_strength": "0.60"}) - 0.0) < 1e-6
            and abs(blink_mod.resolve_mouth_open_strength(None, {"mouth_open_strength": "0.75"}) - 0.75) < 1e-6
            and abs(blink_mod.parse_mouth_open_strength(1.8) - 1.0) < 1e-6
            and jaw_shut == {}
            and abs(jaw_def.get(1, 0.0) - 0.70) < 1e-6
            and 2 not in jaw_def
            and abs(jaw_wide.get(1, 0.0) - 0.85) < 1e-6
            and jaw_def.get(0, 0.0) < jaw_wide.get(0, 0.0)
            and cs_win_file.is_file()
            and 'GUILayout.Button("0.70"' in cs_win_file.read_text(encoding="utf-8")
            and cs_cmd_file.is_file()
            and '"MouthOpenStrength", 0.70f' in cs_cmd_file.read_text(encoding="utf-8")
            and cs_ini_file.is_file()
            and "MouthOpenStrength = 0.70f;" in cs_ini_file.read_text(encoding="utf-8")
        )
        suite_passed &= print_status_result(
            "Mouth opening slider & FACIAL_jaw weight scale (0.00..1.00, default=0.70)",
            mouth_ok,
            f"def={jaw_def.get(1, 0.0):.2f} wide={jaw_wide.get(1, 0.0):.2f} shut={len(jaw_shut)}",
        )

        with tempfile.TemporaryDirectory() as anim_tmp:
            anim_ovr = Path(anim_tmp) / "FaceOverride_v3.anim"
            anim_ovr.write_text(
                "\n".join(
                    [
                        "%YAML 1.1",
                        "  - serializedVersion: 3",
                        "    curve:",
                        "      - serializedVersion: 3",
                        "        value: 65",
                        "    attribute: blendShape.mouth_smile",
                        "    path: ",
                        "  - serializedVersion: 2",
                        "    curve:",
                        "      - serializedVersion: 3",
                        "        value: 1",
                        "    attribute: m_IsActive",
                        "    path: Body",
                    ]
                ),
                encoding="utf-8",
            )
            parsed_ovr = blendshape_helper.load_unity_anim_blendshapes(anim_ovr, include_zero=True)
            cfg_base = Path(anim_tmp) / "base.cfg"
            cfg_base.write_text("[Face]\nmouth_smile = 0.10\n", encoding="utf-8")
            resolved_ovr = blendshape_helper.resolve_character_blendshapes(
                {"blendshapes_source": "cfg", "blendshapes_cfg": str(cfg_base)},
                default_face_mesh="Face",
                override_face_anim=str(anim_ovr),
            )
            cs_log_file = PROJECT_ROOT_DIR / "unity_plugin" / "Assets" / "VRCAvatar2GTAV" / "Editor" / "Vrc2GtavLogConsoleWidget.cs"
            win_txt = cs_win_file.read_text(encoding="utf-8")
            cmd_txt = cs_cmd_file.read_text(encoding="utf-8")
            log_txt = cs_log_file.read_text(encoding="utf-8")
            face_ovr_ok = (
                "m_IsActive" not in parsed_ovr
                and abs(parsed_ovr.get("mouth_smile", 0.0) - 0.65) < 1e-6
                and abs(resolved_ovr["mesh_weights"]["Face"]["mouth_smile"] - 0.65) < 1e-6
                and "FaceBlendshapesAnim" in cmd_txt
                and "--face-anim" in cmd_txt
                and "DrawAnimClipOverrideRow" in log_txt
                and "_wrapMiniLabelStyle" in win_txt
            )
            suite_passed &= print_status_result(
                "Face blendshape .anim override & responsive UI layout",
                face_ovr_ok,
                f"anim_keys={list(parsed_ovr.keys())} face_smile={resolved_ovr['mesh_weights']['Face'].get('mouth_smile', 0.0):.2f}",
            )

        with tempfile.TemporaryDirectory() as rpf_tmp:
            import struct as struct_mod
            import npc_registry_helper as npc_mod
            import ped_damage_helper as dmg_mod
            import repack_and_deploy_everything as rpk_mod

            rpf_src = Path(rpf_tmp) / "src_tree"
            sub_dir = rpf_src / "ped_slot"
            sub_dir.mkdir(parents=True, exist_ok=True)
            (sub_dir / "head_000_r.ydd").write_bytes(
                struct_mod.pack("<IIII", 0x37435352, 165, 0xA0000020, 0x50020080) + (b"\x01" * 240)
            )
            (rpf_src / "peds.ymt").write_bytes(b"<CPedModelInfo/>")
            out_rpf = Path(rpf_tmp) / "streamed_out.rpf"
            npc_mod.build_rpf7_open_streaming(out_rpf, rpf_src, "UnitRPF7Test")
            lim_rep = dmg_mod.inspect_rpf7_archive_limits(out_rpf)
            stream_ok = (
                lim_rep["ok"]
                and lim_rep["encryption"] == b"OPEN"
                and lim_rep["entry_count"] == 4
                and not lim_rep["resource_overflows"]
                and not lim_rep["compressed_binaries"]
                and rpk_mod.RPF7_STREAMING_THRESHOLD_BYTES == 850_000_000
                and rpk_mod.SAFE_X64V_ARCHIVE_BYTES == 2_800_000_000
            )
            suite_passed &= print_status_result(
                "Streaming RPF7 OPEN builder & OOM-safe threshold",
                stream_ok,
                f"entries={lim_rep['entry_count']} enc={lim_rep['encryption']} size={lim_rep['total_bytes']}",
            )

        with tempfile.TemporaryDirectory() as rage_tmp:
            import avatar_archive_helper as arch_mod
            import npc_registry_helper as npc_mod2
            import vrc2gtav_paths as paths_mod2

            rage_ws = Path(rage_tmp) / "VRCAvatar2GTAV_Work" / "tools"
            rage_ws.mkdir(parents=True, exist_ok=True)
            exe_nm = "rage.exe" if os.name == "nt" else "rage"
            fake_rage = rage_ws / exe_nm
            fake_rage.write_bytes(b"FAKE_RAGE_BIN")
            orig_get = paths_mod2.get_rage_cli
            orig_root = paths_mod2.get_project_root
            orig_stg = paths_mod2.get_staging_dir
            orig_dl = arch_mod.download_and_install_rage
            try:
                fake_proj = Path(rage_tmp) / "Assets" / "VRCAvatar2GTAV" / "Toolchain"
                fake_proj.mkdir(parents=True, exist_ok=True)
                paths_mod2.get_rage_cli = lambda: ""
                paths_mod2.get_project_root = lambda: fake_proj
                paths_mod2.get_staging_dir = lambda: Path(rage_tmp) / "VRCAvatar2GTAV_Work" / "staging"
                resolved_ws_cmd = npc_mod2.build_safe_rage_cmd("search", "x64v.rpf", "*player*")
                fake_rage.unlink()

                def _mock_dl(_proj):
                    fake_rage.write_bytes(b"DL_RAGE")
                    return fake_rage

                arch_mod.download_and_install_rage = _mock_dl
                resolved_dl_cmd = npc_mod2.build_safe_rage_cmd("search", "x64v.rpf", "*player*")
                rage_guard_ok = (
                    resolved_ws_cmd[0] == str(fake_rage)
                    and resolved_dl_cmd[0] == str(fake_rage)
                    and fake_rage.read_bytes() == b"DL_RAGE"
                )
            finally:
                paths_mod2.get_rage_cli = orig_get
                paths_mod2.get_project_root = orig_root
                paths_mod2.get_staging_dir = orig_stg
                arch_mod.download_and_install_rage = orig_dl
            suite_passed &= print_status_result(
                "Empty rage= fallback & auto-download guard (prevents WinError 87)",
                rage_guard_ok,
                f"resolved={exe_nm}",
            )

    return suite_passed

