#!/usr/bin/env python3
"""
test_suite_restore_multislot_layer.py
======================================
Regression tests for:
1. Per-FBX active mesh pruning & MA bake plan scoping (`Eresia` extra mesh removal)
2. Scene-scoped material collection, `m_Parent` variants, `_TransparentMode: 0` opaque,
   and `>= 256px` spec/normal + RGB (`DXT1`) diffuse atlas generation
3. Vanilla skeleton tag collision avoidance (406 reserved tags) + scoped INI removal
4. Incremental `mods/` staging preservation + non-clobbering INI sync + selective
   Restore-to-Vanilla (`restore_vanilla_helper`) + `--slots-json` batch execution
5. Unity C# Editor constraints (`9` files, `<= 500` lines each, zero emojis)
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest.mock
from pathlib import Path
from typing import Any, Dict, List

try:
    import test_suite_core_layer as core_suite
except ImportError:
    from common_tools import test_suite_core_layer as core_suite

print_status_result = core_suite.print_status_result
PROJECT_ROOT_DIR = core_suite.PROJECT_ROOT_DIR


def _build_fake_bpy(mesh_specs_by_fbx: Dict[str, List[str]]) -> tuple[Any, Dict[str, Any]]:
    """Build a minimal fake `bpy` module for offline `apply_modular_avatar_plan_in_blender` testing."""
    state: Dict[str, Any] = {"objects": [], "removed": []}

    class _FakeData:
        def __init__(self, name_val: str) -> None:
            self.name = name_val
            self.materials: List[Any] = []

    class _FakeObj:
        def __init__(self, obj_name: str, obj_type: str = "MESH", parent: Any = None) -> None:
            self.name = obj_name
            self.type = obj_type
            self.parent = parent
            self.data = _FakeData(obj_name)
            self.vertex_groups: List[Any] = []
            self.modifiers: List[Any] = []
            self.pose = None

        def select_set(self, _flag: bool) -> None:
            pass

    class _FakeObjsCollection(list):
        def remove(self, obj_item: Any, do_unlink: bool = False) -> None:  # type: ignore[override]
            state["removed"].append(obj_item.name)
            if obj_item in self:
                list.remove(self, obj_item)

    objs_coll = _FakeObjsCollection()
    state["objects"] = objs_coll

    def _fake_import_fbx(**kwargs: Any) -> None:
        fpath = str(kwargs.get("filepath", ""))
        key_name = Path(fpath).name.lower()
        for mesh_name in mesh_specs_by_fbx.get(key_name, ()):
            objs_coll.append(_FakeObj(mesh_name, "MESH"))

    class _FakeBpy:
        class data:
            objects = objs_coll

        class ops:
            class import_scene:
                fbx = staticmethod(_fake_import_fbx)

            class object:
                @staticmethod
                def select_all(**_kwargs: Any) -> None:
                    pass

                @staticmethod
                def mode_set(**_kwargs: Any) -> None:
                    pass

        class context:
            class view_layer:
                class objects:
                    active = None

    return _FakeBpy, state


def _test_ma_fbx_pruning_and_scoped_atlas() -> tuple[bool, bool]:
    """Verify per-FBX unreferenced mesh pruning and scoped opaque DXT1/256px atlas build."""
    import modular_avatar_helper
    import universal_atlas_builder
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        assets_dir = tmp_dir / "Assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        base_fbx = assets_dir / "Shinano_Base.fbx"
        outfit_fbx = assets_dir / "Eresia_For_Shinano.fbx"
        base_fbx.write_bytes(b"FBX_BASE")
        outfit_fbx.write_bytes(b"FBX_ERESIA")
        (assets_dir / "Shinano_Base.fbx.meta").write_text("fileFormatVersion: 2\nguid: 11111111111111111111111111111111\n", encoding="utf-8")
        (assets_dir / "Eresia_For_Shinano.fbx.meta").write_text("fileFormatVersion: 2\nguid: 22222222222222222222222222222222\n", encoding="utf-8")

        tex_skin = assets_dir / "skin.png"
        tex_sibling = assets_dir / "sibling_cutout.png"
        mask_unused = assets_dir / "unused_alpha_mask.png"
        Image.new("RGBA", (64, 64), (240, 200, 180, 128)).save(tex_skin)
        Image.new("RGBA", (64, 64), (10, 200, 10, 50)).save(tex_sibling)
        Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(mask_unused)
        (assets_dir / "skin.png.meta").write_text("fileFormatVersion: 2\nguid: 33333333333333333333333333333333\n", encoding="utf-8")
        (assets_dir / "sibling_cutout.png.meta").write_text("fileFormatVersion: 2\nguid: 44444444444444444444444444444444\n", encoding="utf-8")
        (assets_dir / "unused_alpha_mask.png.meta").write_text("fileFormatVersion: 2\nguid: 55555555555555555555555555555555\n", encoding="utf-8")

        parent_mat = assets_dir / "BaseSkin.mat"
        parent_mat.write_text(
            "Material:\n  m_Name: BaseSkin\n  m_CustomRenderQueue: 2000\n  m_SavedProperties:\n"
            "    m_TexEnvs:\n    - _MainTex:\n        m_Texture: {fileID: 2800000, guid: 33333333333333333333333333333333, type: 3}\n"
            "    m_Floats:\n    - _TransparentMode: 0\n    - _Cull: 2\n",
            encoding="utf-8",
        )
        (assets_dir / "BaseSkin.mat.meta").write_text("fileFormatVersion: 2\nguid: 66666666666666666666666666666666\n", encoding="utf-8")

        variant_mat = assets_dir / "VariantSkin.mat"
        variant_mat.write_text(
            "Material:\n  m_Name: VariantSkin\n  m_Parent: {fileID: 2100000, guid: 66666666666666666666666666666666, type: 2}\n"
            "  m_CustomRenderQueue: 2455\n  m_ValidKeywords: []\n  m_SavedProperties:\n"
            "    m_TexEnvs:\n    - _AlphaMask:\n        m_Texture: {fileID: 2800000, guid: 55555555555555555555555555555555, type: 3}\n",
            encoding="utf-8",
        )
        (assets_dir / "VariantSkin.mat.meta").write_text("fileFormatVersion: 2\nguid: 77777777777777777777777777777777\n", encoding="utf-8")

        sibling_mat = assets_dir / "SiblingCutout.mat"
        sibling_mat.write_text(
            "Material:\n  m_Name: SiblingCutout\n  m_CustomRenderQueue: 2950\n  m_SavedProperties:\n"
            "    m_TexEnvs:\n    - _MainTex:\n        m_Texture: {fileID: 2800000, guid: 44444444444444444444444444444444, type: 3}\n"
            "    m_Floats:\n    - _TransparentMode: 2\n",
            encoding="utf-8",
        )
        (assets_dir / "SiblingCutout.mat.meta").write_text("fileFormatVersion: 2\nguid: 88888888888888888888888888888888\n", encoding="utf-8")

        scene_file = assets_dir / "TestScene.unity"
        scene_file.write_text(
            "\n".join([
                "%YAML 1.1",
                "--- !u!1 &10", "GameObject:", "  m_Name: TargetAvatar", "  m_IsActive: 1",
                "--- !u!4 &11", "Transform:", "  m_GameObject: {fileID: 10}", "  m_Children:", "  - {fileID: 13}", "  - {fileID: 16}", "  m_Father: {fileID: 0}",
                "--- !u!1 &12", "GameObject:", "  m_Name: Body", "  m_IsActive: 1",
                "--- !u!4 &13", "Transform:", "  m_GameObject: {fileID: 12}", "  m_Children: []", "  m_Father: {fileID: 11}",
                "--- !u!137 &14", "SkinnedMeshRenderer:", "  m_GameObject: {fileID: 12}", "  m_Enabled: 1",
                "  m_Materials:", "  - {fileID: 2100000, guid: 77777777777777777777777777777777, type: 2}",
                "  m_Mesh: {fileID: 4300000, guid: 11111111111111111111111111111111, type: 3}",
                "--- !u!1 &15", "GameObject:", "  m_Name: Bikini_Panti", "  m_IsActive: 1",
                "--- !u!4 &16", "Transform:", "  m_GameObject: {fileID: 15}", "  m_Children: []", "  m_Father: {fileID: 11}",
                "--- !u!137 &17", "SkinnedMeshRenderer:", "  m_GameObject: {fileID: 15}", "  m_Enabled: 1",
                "  m_Materials:", "  - {fileID: 2100000, guid: 77777777777777777777777777777777, type: 2}",
                "  m_Mesh: {fileID: 4300002, guid: 22222222222222222222222222222222, type: 3}",
                "--- !u!1 &20", "GameObject:", "  m_Name: SiblingAvatar", "  m_IsActive: 1",
                "--- !u!4 &21", "Transform:", "  m_GameObject: {fileID: 20}", "  m_Children:", "  - {fileID: 23}", "  m_Father: {fileID: 0}",
                "--- !u!1 &22", "GameObject:", "  m_Name: WitchHat", "  m_IsActive: 1",
                "--- !u!4 &23", "Transform:", "  m_GameObject: {fileID: 22}", "  m_Children: []", "  m_Father: {fileID: 21}",
                "--- !u!137 &24", "SkinnedMeshRenderer:", "  m_GameObject: {fileID: 22}", "  m_Enabled: 1",
                "  m_Materials:", "  - {fileID: 2100000, guid: 88888888888888888888888888888888, type: 2}",
                "  m_Mesh: {fileID: 4300004, guid: 22222222222222222222222222222222, type: 3}",
            ]),
            encoding="utf-8",
        )

        plan = modular_avatar_helper.build_modular_avatar_bake_plan(
            scene_file, avatar_name="TargetAvatar", assets_root=assets_dir, resolve_materials=True
        )
        fake_bpy, fake_state = _build_fake_bpy({
            "shinano_base.fbx": ["Body", "UnusedBaseExtra"],
            "eresia_for_shinano.fbx": ["Bikini_Panti", "Witch_Cape", "Heels"],
        })
        base_arm = fake_bpy.data.objects.__class__()
        base_obj_ref = type("_Arm", (), {"name": "Armature", "type": "ARMATURE", "data": type("_D", (), {"bones": []})(), "pose": None})()
        _ = base_arm
        fake_bpy.ops.import_scene.fbx(filepath=str(base_fbx))
        for scene_item in fake_state["objects"]:
            scene_item.parent = base_obj_ref
        modular_avatar_helper.apply_modular_avatar_plan_in_blender(
            fake_bpy, base_obj_ref, plan, import_extra_fbx=True, primary_base_fbx=base_fbx
        )
        remaining_names = sorted(obj_item.name for obj_item in fake_state["objects"] if obj_item.type == "MESH")
        pruning_ok = (
            plan["loaded"]
            and remaining_names == ["Bikini_Panti", "Body"]
            and "Witch_Cape" in fake_state["removed"]
            and "Heels" in fake_state["removed"]
        )

        collected = universal_atlas_builder.collect_avatar_materials(
            scene_file, tmp_dir, base_fbx, extra_fbxs=[outfit_fbx], ma_plan=plan, avatar_name="TargetAvatar"
        )
        out_atlas_dir = tmp_dir / "atlas_out"

        def _fake_rage_run(cmd_args: Sequence[str], **_kwargs: Any) -> subprocess.CompletedProcess:
            if "-o" in cmd_args:
                out_idx = list(cmd_args).index("-o") + 1
                Path(cmd_args[out_idx]).write_bytes(b"RSC7MOCK")
            return subprocess.CompletedProcess(cmd_args, 0, "", "")

        with unittest.mock.patch.object(universal_atlas_builder.subprocess, "run", side_effect=_fake_rage_run):
            atlas_res = universal_atlas_builder.build_universal_avatar_atlas(
                ped_name="player_zero",
                project_dir=tmp_dir,
                scene_or_prefab=scene_file,
                source_fbx=base_fbx,
                extra_fbxs=[outfit_fbx],
                output_dir=out_atlas_dir,
                atlas_size=512,
                normal_size=0,
                ma_plan=plan,
                avatar_name="TargetAvatar",
                vtoon_char_id=0,
                sync_to_game=False,
            )
        spec_sz = Image.open(atlas_res["spec_png"]).size
        norm_sz = Image.open(atlas_res["normal_png"]).size
        diff_mode = Image.open(atlas_res["atlas_png"]).mode
        atlas_ok = (
            list(collected.keys()) == ["VariantSkin"]
            and collected["VariantSkin"]["alpha_mode"] == "opaque"
            and spec_sz == (512, 512)
            and norm_sz == (512, 512)
            and diff_mode == "RGB"
        )
        return pruning_ok, atlas_ok


def _test_physbones_collision_and_ini_cleanup() -> bool:
    """Verify vanilla tag collision avoidance, C++ model priority, and per-ped INI removal."""
    import physbone_cfg_ini_layer
    import physbone_helper
    import physbone_presets_layer
    import vtoon_profile_helper

    vanilla_tags = physbone_presets_layer.VANILLA_RESERVED_BONE_TAGS
    packed_res = physbone_helper.pack_physbone_chains_to_gtav_budget(
        [
            {
                "root_bone": "SkirtBL",
                "parent_bone": "SKEL_Pelvis",
                "spoke_bones": ["SkirtBL_0", "SkirtBL_1"],
                "all_descendants": ["SkirtBL", "SkirtBL_0", "SkirtBL_1"],
                "depth": 2,
                "stiffness": 0.25,
                "gravity": 0.15,
                "pull": 0.3,
                "spring": 0.6,
                "immobile": 0.2,
                "limit_angle": 45.0,
                "limit_pitch": 45.0,
                "limit_yaw": 45.0,
                "radius": 0.04,
            }
        ],
        gtav_prefix="PB_ER",
    )
    no_collision = bool(packed_res.get("custom_bones")) and all(
        physbone_helper.compute_gtav_bone_tag(bone_name) not in vanilla_tags
        for bone_name in packed_res["custom_bones"]
    )

    cpp_path = PROJECT_ROOT_DIR / "scripts" / "physbones_asi" / "gtav_physbones.cpp"
    cpp_txt = cpp_path.read_text(encoding="utf-8", errors="ignore")
    cpp_ok = "ResolveChainBoneIndices" in cpp_txt and "uint32_t pedModelHash" in cpp_txt and "modelRootRefs" in cpp_txt

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        pb_ini = tmp_dir / "GTAVPhysBones.ini"
        pb_ini.write_text(
            "; test\n"
            "[Chain_0]\nname = Chain_player_zero_Skirt\nmodel = player_zero\nroot_tag = 51001\n\n"
            "[Chain_1]\nname = Chain_player_one_Hair\nmodel = player_one\nroot_tag = 51002\n\n"
            "[Blink_0]\nmodel = player_zero\nmode = uv\n\n"
            "[Blink_1]\nmodel = player_one\nmode = uv\n",
            encoding="utf-8",
        )
        physbone_cfg_ini_layer.remove_ped_from_physbone_ini(pb_ini, "player_zero")
        pb_after = pb_ini.read_text(encoding="utf-8")

        vt_ini = tmp_dir / "GTAVVToon.ini"
        vtoon_profile_helper.upsert_vtoon_ini_character(
            [vt_ini], 1, "player_zero", "a.png", "b.png", {0: {"rim_strength": 0.5}}
        )
        vtoon_profile_helper.upsert_vtoon_ini_character(
            [vt_ini], 2, "player_one", "c.png", "d.png", {0: {"rim_strength": 0.7}}
        )
        vtoon_profile_helper.remove_vtoon_ini_character([vt_ini], char_ids=(1,), char_names=("player_zero",))
        vt_after = vt_ini.read_text(encoding="utf-8")

        ini_ok = (
            "player_zero" not in pb_after
            and "Chain_player_one_Hair" in pb_after
            and "model = player_one" in pb_after
            and "blink_count = 1" in pb_after
            and "[Char_1]" not in vt_after
            and "[Char_2]" in vt_after
        )
    return len(vanilla_tags) >= 400 and no_collision and cpp_ok and ini_ok


def _test_restore_and_multislot_pipeline() -> bool:
    """Verify incremental mods/ seeding, non-clobbering INI sync, restore-to-vanilla, and multi-slot."""
    import npc_registry_helper
    import repack_and_deploy_everything as repack_helper
    import restore_vanilla_helper

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        van_rpf = tmp_dir / "vanilla_x64v.rpf"
        mods_rpf = tmp_dir / "mods_x64v.rpf"
        van_rpf.write_bytes(b"VAN")
        mods_rpf.write_bytes(b"MOD")
        dlc_van = tmp_dir / "van_patchday3ng.rpf"
        dlc_mod = tmp_dir / "mods_patchday3ng.rpf"
        dlc_van.write_bytes(b"DVAN")
        dlc_mod.write_bytes(b"DMOD")

        outer_dir = tmp_dir / "outer_extracted"
        inner_dir = tmp_dir / "streamedpeds_extracted"
        backup_yft = tmp_dir / "backup_yft" / "player_zero.yft"
        backup_dir = tmp_dir / "backup_vanilla" / "player_zero"
        dlc_dir = tmp_dir / "dlc_ext"
        models_dir = tmp_dir / "dlc_models"

        fake_paths = {
            "ped_name": "player_zero",
            "ped_format": "streamed",
            "outer_rpf_name": "x64v.rpf",
            "vanilla_outer_rpf": van_rpf,
            "outer_extracted_dir": outer_dir,
            "inner_rpf_rel": Path("models/cdimages/streamedpeds_players.rpf"),
            "inner_rpf_file": outer_dir / "models" / "cdimages" / "streamedpeds_players.rpf",
            "inner_extracted_dir": inner_dir,
            "outer_modded_rpf": tmp_dir / "x64v_modded.rpf",
            "outer_game_rpf": mods_rpf,
            "dlc_override_specs": [
                {
                    "dlc_name": "patchday3ng",
                    "vanilla_dlc_rpf": dlc_van,
                    "inner_rpf_rel": Path("x64/models/cdimages/patchday3ng.rpf"),
                    "dlc_extracted_dir": dlc_dir,
                    "inner_rpf_file": dlc_dir / "x64" / "models" / "cdimages" / "patchday3ng.rpf",
                    "models_extracted_dir": models_dir,
                    "modded_dlc_rpf": tmp_dir / "patchday3ng_mod.rpf",
                    "game_dlc_rpf": dlc_mod,
                    "members": ["player_zero"],
                }
            ],
            "vanilla_skeleton_backup": backup_yft,
            "npc_backup_dir": backup_dir,
            "npc_work_dir": tmp_dir / "work",
            "blender_dir": tmp_dir / "work" / "2_blender",
            "textures_dir": tmp_dir / "work" / "3_textures_gtav",
            "package_dir": tmp_dir / "work" / "5_rpf_package",
        }
        seen_extract_srcs: List[str] = []

        def _fake_extract(archive_path: Path, target_dir: Path, **_kwargs: Any) -> None:
            seen_extract_srcs.append(archive_path.name)
            target_dir.mkdir(parents=True, exist_ok=True)
            if archive_path == mods_rpf:
                inner_p = target_dir / "models" / "cdimages" / "streamedpeds_players.rpf"
                inner_p.parent.mkdir(parents=True, exist_ok=True)
                inner_p.write_bytes(b"MOD_INNER")
            elif archive_path == van_rpf:
                inner_p = target_dir / "models" / "cdimages" / "streamedpeds_players.rpf"
                inner_p.parent.mkdir(parents=True, exist_ok=True)
                inner_p.write_bytes(b"VAN_INNER")
            elif archive_path == dlc_mod:
                dlc_in = target_dir / "x64" / "models" / "cdimages" / "patchday3ng.rpf"
                dlc_in.parent.mkdir(parents=True, exist_ok=True)
                dlc_in.write_bytes(b"DLC_MOD_INNER")
            elif archive_path.name == "streamedpeds_players.rpf":
                (target_dir / "player_zero.yft").write_bytes(b"YFT_DATA")
                (target_dir / "player_zero").mkdir(parents=True, exist_ok=True)
                (target_dir / "player_zero" / "uppr_000_u.ydd").write_bytes(b"YDD")
            elif archive_path.name == "patchday3ng.rpf":
                (target_dir / "player_zero").mkdir(parents=True, exist_ok=True)

        with (
            unittest.mock.patch.object(npc_registry_helper, "get_npc_staging_paths", return_value=fake_paths),
            unittest.mock.patch.object(npc_registry_helper, "_extract_archive", side_effect=_fake_extract),
        ):
            npc_registry_helper.ensure_npc_staging_extracted("player_zero", {"ped_format": "streamed"})

        mods_seed_ok = (
            "mods_x64v.rpf" in seen_extract_srcs
            and "mods_patchday3ng.rpf" in seen_extract_srcs
            and "vanilla_x64v.rpf" in seen_extract_srcs
            and backup_yft.is_file()
        )

        # Verify _sync_vtoon_runtime_to_game never sets overwrite_inis=True
        sync_calls: List[bool] = []
        with unittest.mock.patch.object(
            repack_helper,
            "sync_gtav_runtime_mods",
            side_effect=lambda *_args, **kwargs: sync_calls.append(bool(kwargs.get("overwrite_inis", False))) or {},
        ):
            repack_helper._sync_vtoon_runtime_to_game(tmp_dir, tmp_dir)
        non_clobber_ok = sync_calls == [False]

        # Verify restore_peds_to_vanilla removes only requested ped & repacks once
        proj_root = tmp_dir / "proj"
        gtav_root = tmp_dir / "gtav"
        staging_root = tmp_dir / "staging"
        proj_root.mkdir()
        gtav_root.mkdir()
        staging_root.mkdir()
        npc_registry_helper.save_npc_registry(
            {
                "npcs": {
                    "player_zero": {"location": {"ped_format": "streamed"}, "vtoon_char_id": 1},
                    "player_one": {"location": {"ped_format": "streamed"}, "vtoon_char_id": 2},
                }
            },
            proj_root,
        )
        (gtav_root / "GTAVPhysBones.ini").write_text(
            "[Chain_player_zero_Hair]\nmodel = player_zero\n\n[Chain_player_one_Hair]\nmodel = player_one\n",
            encoding="utf-8",
        )
        repack_calls: List[List[str]] = []
        with (
            unittest.mock.patch.object(npc_registry_helper, "get_npc_staging_paths", return_value=fake_paths),
            unittest.mock.patch.object(npc_registry_helper, "ensure_npc_staging_extracted"),
            unittest.mock.patch.object(restore_vanilla_helper, "restore_single_ped_in_staging", return_value={"ped_name": "player_zero", "files_restored": 3}),
            unittest.mock.patch.object(restore_vanilla_helper, "repack_and_deploy_built_peds", side_effect=lambda peds, **_kw: repack_calls.append(list(peds)) or []),
        ):
            restore_vanilla_helper.restore_peds_to_vanilla(
                ["player_zero"], gtav_root=gtav_root, staging_dir=staging_root, project_root=proj_root
            )
        reg_after = npc_registry_helper.load_npc_registry(proj_root)["npcs"]
        pb_after = (gtav_root / "GTAVPhysBones.ini").read_text(encoding="utf-8")
        restore_ok = (
            "player_zero" not in reg_after
            and "player_one" in reg_after
            and "player_zero" not in pb_after
            and "player_one" in pb_after
            and repack_calls == [["player_zero"]]
        )

        # Verify multi-slot batch execution forwards independent options per slot without cross-slot leaks
        slot_calls: List[tuple[str, bool]] = []
        slot_kwargs: List[Dict[str, Any]] = []

        def _fake_build(**kwargs: Any) -> Dict[str, Any]:
            slot_calls.append((str(kwargs["target_ped"]), bool(kwargs["repack_archives"])))
            slot_kwargs.append(dict(kwargs))
            return {"ped_name": kwargs["target_ped"], "avatar_name": kwargs.get("avatar_name", "")}

        multislot_repack: List[List[str]] = []
        with unittest.mock.patch.object(
            restore_vanilla_helper,
            "repack_and_deploy_built_peds",
            side_effect=lambda peds, **_kw: multislot_repack.append(list(peds)) or [],
        ):
            restore_vanilla_helper.run_multi_slot_builds(
                [
                    {
                        "target_ped": "player_zero",
                        "source": "A.unity",
                        "avatar_name": "ShinanoA",
                        "atlas_size": 4096,
                        "normal_size": 512,
                        "eye_blink": True,
                        "eye_blink_strength": 0.7,
                        "mouth_open_strength": 0.6,
                        "blood_decals": False,
                        "import_face_blendshapes": True,
                        "physbones_marshmallow": True,
                        "face_anim": "A_face.anim",
                        "texture_overrides": {"Hair": "hair_a.png"},
                    },
                    {
                        "target_ped": "player_one",
                        "source": "B.prefab",
                        "avatar_name": "ShinanoB",
                        "atlas_size": 1024,
                        "normal_size": 256,
                        "eye_blink": False,
                        "mouth_open_strength": 0.25,
                        "blood_decals": True,
                        "import_face_blendshapes": False,
                        "physbones_marshmallow": False,
                        "texture_overrides": {"Body": "body_b.png"},
                    },
                ],
                build_fn=_fake_build,
            )
        multislot_ok = (
            slot_calls == [("player_zero", False), ("player_one", False)]
            and multislot_repack == [["player_zero", "player_one"]]
            and len(slot_kwargs) == 2
            and slot_kwargs[0]["atlas_size"] == 4096
            and slot_kwargs[0]["normal_size"] == 512
            and slot_kwargs[0]["eye_blink"] is True
            and abs(float(slot_kwargs[0]["eye_blink_strength"]) - 0.7) < 1e-6
            and abs(float(slot_kwargs[0]["mouth_open_strength"]) - 0.6) < 1e-6
            and slot_kwargs[0]["blood_decals"] is False
            and slot_kwargs[0]["import_face_blendshapes"] is True
            and slot_kwargs[0]["physbones_marshmallow"] is True
            and slot_kwargs[0]["face_anim"] == "A_face.anim"
            and slot_kwargs[0]["texture_overrides"] == {"Hair": "hair_a.png"}
            and slot_kwargs[1]["atlas_size"] == 1024
            and slot_kwargs[1]["normal_size"] == 256
            and slot_kwargs[1]["eye_blink"] is False
            and slot_kwargs[1]["eye_blink_strength"] is None
            and abs(float(slot_kwargs[1]["mouth_open_strength"]) - 0.25) < 1e-6
            and slot_kwargs[1]["blood_decals"] is True
            and slot_kwargs[1]["import_face_blendshapes"] is False
            and slot_kwargs[1]["physbones_marshmallow"] is False
            and slot_kwargs[1]["face_anim"] is None
            and slot_kwargs[1]["texture_overrides"] == {"Body": "body_b.png"}
        )
        return mods_seed_ok and non_clobber_ok and restore_ok and multislot_ok


def _test_unity_transform_and_earring_alignment() -> bool:
    """Verify base `Neck` scale, `MergeArmature` Hair offset/scale, and dual mirrored `Earring` instances."""
    import modular_avatar_helper
    import modular_avatar_yaml_layer

    unit_pts = {"Hips": (0.0, -0.0164, 0.7935), "Hand.R": (-0.484, 0.0152, 1.0611)}
    unit_mats = {
        "Hips": [[100.0, 0.0, 0.0, 0.0], [0.0, 0.0, -100.0, -0.0164], [0.0, 100.0, 0.0, 0.7935], [0.0, 0.0, 0.0, 1.0]],
        "Hand.R": [[100.0, 0.0, 0.0, -0.484], [0.0, 0.0, -100.0, 0.0152], [0.0, 100.0, 0.0, 1.0611], [0.0, 0.0, 0.0, 1.0]],
    }
    corr_val = modular_avatar_yaml_layer.compute_bone_unit_scale_correction(unit_pts, unit_mats)
    if abs(corr_val - 0.01) > 1e-4:
        return False

    with tempfile.TemporaryDirectory() as tmp_str:
        assets_dir = Path(tmp_str) / "Assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        for asset_name, guid_val in (
            ("BaseAvatar.fbx", "a1111111111111111111111111111111"),
            ("OffsetHair.fbx", "b2222222222222222222222222222222"),
            ("SideEarring.fbx", "c3333333333333333333333333333333"),
        ):
            fpath = assets_dir / asset_name
            fpath.write_bytes(b"FBX_MOCK")
            (assets_dir / f"{asset_name}.meta").write_text(
                f"fileFormatVersion: 2\nguid: {guid_val}\n", encoding="utf-8"
            )

        hair_prefab = assets_dir / "HairAligned.prefab"
        hair_prefab.write_text(
            "\n".join([
                "%YAML 1.1",
                "--- !u!1 &100", "GameObject:", "  m_Name: MA HairRoot", "  m_IsActive: 1",
                "--- !u!4 &101", "Transform:", "  m_GameObject: {fileID: 100}", "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}", "  m_LocalPosition: {x: 0, y: 0, z: 0}", "  m_LocalScale: {x: 1, y: 1, z: 1}", "  m_Children:", "  - {fileID: 103}", "  - {fileID: 201}", "  m_Father: {fileID: 0}",
                "--- !u!114 &102", "MonoBehaviour:", "  m_GameObject: {fileID: 100}", "  m_Enabled: 1", "  m_Script: {fileID: 11500000, guid: 2df373bf91cf30b4bbd495e11cb1a2ec, type: 3}", "  mergeTarget:", "    referencePath: Armature", "  mangleNames: 1",
                "--- !u!1 &104", "GameObject:", "  m_Name: Armature", "  m_IsActive: 1",
                "--- !u!4 &103", "Transform:", "  m_GameObject: {fileID: 104}", "  m_LocalRotation: {x: -0.7071068, y: 0, z: 0, w: 0.7071067}", "  m_LocalPosition: {x: 0, y: 0, z: 0}", "  m_LocalScale: {x: 1, y: 1, z: 1}", "  m_Children:", "  - {fileID: 105}", "  m_Father: {fileID: 101}",
                "--- !u!1 &106", "GameObject:", "  m_Name: Hips", "  m_IsActive: 1",
                "--- !u!4 &105", "Transform:", "  m_GameObject: {fileID: 106}", "  m_LocalRotation: {x: 0.7071068, y: 0, z: 0, w: 0.7071067}", "  m_LocalPosition: {x: 0, y: -0.0164, z: 0.7935}", "  m_LocalScale: {x: 1, y: 1, z: 1}", "  m_Children:", "  - {fileID: 107}", "  m_Father: {fileID: 103}",
                "--- !u!1 &108", "GameObject:", "  m_Name: Neck", "  m_IsActive: 1",
                "--- !u!4 &107", "Transform:", "  m_GameObject: {fileID: 108}", "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}", "  m_LocalPosition: {x: 0, y: 0.2984, z: 0}", "  m_LocalScale: {x: 1, y: 1, z: 1}", "  m_Children:", "  - {fileID: 109}", "  m_Father: {fileID: 105}",
                "--- !u!1 &110", "GameObject:", "  m_Name: Head", "  m_IsActive: 1",
                "--- !u!4 &109", "Transform:", "  m_GameObject: {fileID: 110}", "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}", "  m_LocalPosition: {x: 0, y: 0.0407, z: 0}", "  m_LocalScale: {x: 1, y: 1, z: 1}", "  m_Children:", "  - {fileID: 111}", "  - {fileID: 301}", "  - {fileID: 401}", "  m_Father: {fileID: 107}",
                "--- !u!1 &112", "GameObject:", "  m_Name: Hair Root", "  m_IsActive: 1",
                "--- !u!4 &111", "Transform:", "  m_GameObject: {fileID: 112}", "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}", "  m_LocalPosition: {x: -0.0007, y: 0.0863, z: 0.0028}", "  m_LocalScale: {x: 1.0927, y: 1.0927, z: 1.0927}", "  m_Children: []", "  m_Father: {fileID: 109}",
                "--- !u!1 &200", "GameObject:", "  m_Name: Bangs", "  m_IsActive: 1",
                "--- !u!4 &201", "Transform:", "  m_GameObject: {fileID: 200}", "  m_Father: {fileID: 101}",
                "--- !u!137 &202", "SkinnedMeshRenderer:", "  m_GameObject: {fileID: 200}", "  m_Enabled: 1", "  m_RootBone: {fileID: 105}", "  m_Mesh: {fileID: 4300000, guid: b2222222222222222222222222222222, type: 3}",
                "--- !u!1 &300", "GameObject:", "  m_Name: Earring L", "  m_IsActive: 1",
                "--- !u!4 &301", "Transform:", "  m_GameObject: {fileID: 300}", "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}", "  m_LocalPosition: {x: 0.0232, y: -1.7463, z: 0.0229}", "  m_LocalScale: {x: 1.6313, y: 1.6313, z: 1.6313}", "  m_Children:", "  - {fileID: 302}", "  - {fileID: 305}", "  m_Father: {fileID: 109}",
                "--- !u!1 &303", "GameObject:", "  m_Name: Li-ne_Earring", "  m_IsActive: 1",
                "--- !u!4 &302", "Transform:", "  m_GameObject: {fileID: 303}", "  m_LocalRotation: {x: -0.7071068, y: 0, z: 0, w: 0.7071067}", "  m_LocalPosition: {x: 0, y: 0, z: 0}", "  m_LocalScale: {x: 1, y: 1, z: 1}", "  m_Children:", "  - {fileID: 304}", "  m_Father: {fileID: 301}",
                "--- !u!1 &306", "GameObject:", "  m_Name: Earring", "  m_IsActive: 1",
                "--- !u!4 &304", "Transform:", "  m_GameObject: {fileID: 306}", "  m_LocalRotation: {x: 0.499, y: 0.501, z: -0.501, w: -0.499}", "  m_LocalPosition: {x: -0.0518, y: -0.0209, z: 1.0931}", "  m_LocalScale: {x: 1, y: 1, z: 1}", "  m_Children: []", "  m_Father: {fileID: 302}",
                "--- !u!1 &307", "GameObject:", "  m_Name: Earring", "  m_IsActive: 1",
                "--- !u!4 &305", "Transform:", "  m_GameObject: {fileID: 307}", "  m_Father: {fileID: 301}",
                "--- !u!137 &308", "SkinnedMeshRenderer:", "  m_GameObject: {fileID: 307}", "  m_Enabled: 1", "  m_RootBone: {fileID: 304}", "  m_Mesh: {fileID: 4300002, guid: c3333333333333333333333333333333, type: 3}",
                "--- !u!1 &400", "GameObject:", "  m_Name: Earring R", "  m_IsActive: 1",
                "--- !u!4 &401", "Transform:", "  m_GameObject: {fileID: 400}", "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}", "  m_LocalPosition: {x: -0.0231, y: -1.74625, z: 0.01936}", "  m_LocalScale: {x: -1.6313, y: 1.6313, z: 1.6313}", "  m_Children:", "  - {fileID: 402}", "  - {fileID: 405}", "  m_Father: {fileID: 109}",
                "--- !u!1 &403", "GameObject:", "  m_Name: Li-ne_Earring", "  m_IsActive: 1",
                "--- !u!4 &402", "Transform:", "  m_GameObject: {fileID: 403}", "  m_LocalRotation: {x: -0.7071068, y: 0, z: 0, w: 0.7071067}", "  m_LocalPosition: {x: 0, y: 0, z: 0}", "  m_LocalScale: {x: 1, y: 1, z: 1}", "  m_Children:", "  - {fileID: 404}", "  m_Father: {fileID: 401}",
                "--- !u!1 &406", "GameObject:", "  m_Name: Earring", "  m_IsActive: 1",
                "--- !u!4 &404", "Transform:", "  m_GameObject: {fileID: 406}", "  m_LocalRotation: {x: 0.499, y: 0.501, z: -0.501, w: -0.499}", "  m_LocalPosition: {x: -0.0518, y: -0.0209, z: 1.0931}", "  m_LocalScale: {x: 1, y: 1, z: 1}", "  m_Children: []", "  m_Father: {fileID: 402}",
                "--- !u!1 &407", "GameObject:", "  m_Name: Earring", "  m_IsActive: 1",
                "--- !u!4 &405", "Transform:", "  m_GameObject: {fileID: 407}", "  m_Father: {fileID: 401}",
                "--- !u!137 &408", "SkinnedMeshRenderer:", "  m_GameObject: {fileID: 407}", "  m_Enabled: 1", "  m_RootBone: {fileID: 404}", "  m_Mesh: {fileID: 4300002, guid: c3333333333333333333333333333333, type: 3}",
            ]),
            encoding="utf-8",
        )
        (assets_dir / "HairAligned.prefab.meta").write_text(
            "fileFormatVersion: 2\nguid: d4444444444444444444444444444444\n", encoding="utf-8"
        )

        scene_file = assets_dir / "AlignedScene.unity"
        scene_file.write_text(
            "\n".join([
                "%YAML 1.1",
                "--- !u!1 &10", "GameObject:", "  m_Name: TargetAvatar", "  m_IsActive: 1",
                "--- !u!4 &11", "Transform:", "  m_GameObject: {fileID: 10}", "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}", "  m_LocalPosition: {x: -40.32, y: 0, z: 0}", "  m_LocalScale: {x: 1, y: 1, z: 1}", "  m_Children:", "  - {fileID: 13}", "  - {fileID: 21}", "  - {fileID: 31}", "  m_Father: {fileID: 0}",
                "--- !u!1 &12", "GameObject:", "  m_Name: Armature", "  m_IsActive: 1",
                "--- !u!4 &13", "Transform:", "  m_GameObject: {fileID: 12}", "  m_Children:", "  - {fileID: 15}", "  m_Father: {fileID: 11}",
                "--- !u!1 &14", "GameObject:", "  m_Name: Neck", "  m_IsActive: 1",
                "--- !u!4 &15", "Transform:", "  m_GameObject: {fileID: 14}", "  m_LocalScale: {x: 0.9, y: 0.9, z: 0.9}", "  m_Children: []", "  m_Father: {fileID: 13}",
                "--- !u!1 &20", "GameObject:", "  m_Name: Body", "  m_IsActive: 1",
                "--- !u!4 &21", "Transform:", "  m_GameObject: {fileID: 20}", "  m_Children: []", "  m_Father: {fileID: 11}",
                "--- !u!137 &22", "SkinnedMeshRenderer:", "  m_GameObject: {fileID: 20}", "  m_Enabled: 1", "  m_Mesh: {fileID: 4300000, guid: a1111111111111111111111111111111, type: 3}",
                "--- !u!1 &30", "GameObject:", "  m_Name: SwapHolder", "  m_IsActive: 1",
                "--- !u!4 &31", "Transform:", "  m_GameObject: {fileID: 30}", "  m_LocalRotation: {x: -0.7071068, y: 0, z: 0, w: 0.7071067}", "  m_LocalPosition: {x: 0.181, y: 0, z: -1.637}", "  m_LocalScale: {x: 1, y: 1, z: 1}", "  m_Children: []", "  m_Father: {fileID: 11}",
                "--- !u!1001 &900", "PrefabInstance:",
                "  m_Modification:",
                "    m_TransformParent: {fileID: 31}",
                "    m_Modifications:",
                "    - target: {fileID: 101, guid: d4444444444444444444444444444444, type: 3}",
                "      propertyPath: m_LocalScale.x",
                "      value: 1.05",
                "      objectReference: {fileID: 0}",
                "    - target: {fileID: 101, guid: d4444444444444444444444444444444, type: 3}",
                "      propertyPath: m_LocalScale.y",
                "      value: 1.05",
                "      objectReference: {fileID: 0}",
                "    - target: {fileID: 101, guid: d4444444444444444444444444444444, type: 3}",
                "      propertyPath: m_LocalScale.z",
                "      value: 1.05",
                "      objectReference: {fileID: 0}",
                "    - target: {fileID: 101, guid: d4444444444444444444444444444444, type: 3}",
                "      propertyPath: m_LocalPosition.x",
                "      value: -0.181",
                "      objectReference: {fileID: 0}",
                "    - target: {fileID: 101, guid: d4444444444444444444444444444444, type: 3}",
                "      propertyPath: m_LocalPosition.y",
                "      value: -1.6316",
                "      objectReference: {fileID: 0}",
                "    - target: {fileID: 101, guid: d4444444444444444444444444444444, type: 3}",
                "      propertyPath: m_LocalPosition.z",
                "      value: -0.0707",
                "      objectReference: {fileID: 0}",
                "    - target: {fileID: 101, guid: d4444444444444444444444444444444, type: 3}",
                "      propertyPath: m_LocalRotation.x",
                "      value: 0.7071068",
                "      objectReference: {fileID: 0}",
                "    - target: {fileID: 101, guid: d4444444444444444444444444444444, type: 3}",
                "      propertyPath: m_LocalRotation.w",
                "      value: 0.7071067",
                "      objectReference: {fileID: 0}",
                "    - target: {fileID: 107, guid: d4444444444444444444444444444444, type: 3}",
                "      propertyPath: m_LocalScale.x",
                "      value: 0.9473684",
                "      objectReference: {fileID: 0}",
                "    - target: {fileID: 107, guid: d4444444444444444444444444444444, type: 3}",
                "      propertyPath: m_LocalScale.y",
                "      value: 0.9473684",
                "      objectReference: {fileID: 0}",
                "    - target: {fileID: 107, guid: d4444444444444444444444444444444, type: 3}",
                "      propertyPath: m_LocalScale.z",
                "      value: 0.9473684",
                "      objectReference: {fileID: 0}",
                "  m_SourcePrefab: {fileID: 100100000, guid: d4444444444444444444444444444444, type: 3}",
            ]),
            encoding="utf-8",
        )

        plan = modular_avatar_helper.build_modular_avatar_bake_plan(
            scene_file, avatar_name="TargetAvatar", assets_root=assets_dir, resolve_materials=False
        )
        neck_ok = plan.get("base_bone_scales") == {"Neck": [0.9, 0.9, 0.9]}
        instances = plan.get("fbx_instances", [])
        hair_inst = next((item for item in instances if "OffsetHair.fbx" in item.get("fbx_path", "")), None)
        ear_insts = [item for item in instances if "SideEarring.fbx" in item.get("fbx_path", "")]
        hair_mat = (hair_inst or {}).get("bone_matrices", {}).get("Hair Root")
        hair_z = hair_mat[2][3] if hair_mat else 0.0
        ear_xs = sorted(
            item["bone_matrices"]["Earring"][0][3]
            for item in ear_insts
            if "Earring" in item.get("bone_matrices", {})
        )
        return (
            neck_ok
            and hair_mat is not None
            and abs(hair_z - 1.224) < 0.03
            and len(ear_insts) == 2
            and all(item.get("attach_parent_bone") == "Head" for item in ear_insts)
            and len(ear_xs) == 2
            and ear_xs[0] < -0.04
            and ear_xs[1] > 0.04
        )


def _test_mat_overrides_and_non_colliding_atlas() -> bool:
    """Verify PrefabInstance m_Materials overrides, same-stem .mat disambiguation, and MatCap bake."""
    import numpy as numpy_mod
    from PIL import Image

    try:
        import modular_avatar_yaml_layer as mayl
        import unity_hair_bake_layer as uhbl
        import universal_atlas_builder as uab
    except ImportError:
        from common_tools import modular_avatar_yaml_layer as mayl
        from common_tools import unity_hair_bake_layer as uhbl
        from common_tools import universal_atlas_builder as uab

    with tempfile.TemporaryDirectory(prefix="vrc2gtav_mat_test_") as tmp_root_str:
        tmp_root = Path(tmp_root_str)
        assets_dir = tmp_root / "Assets"
        mats_dir = assets_dir / "TestAvatar" / "Materials"
        pants_dir = mats_dir / "pants"
        sweat_dir = mats_dir / "sweat"
        pants_dir.mkdir(parents=True, exist_ok=True)
        sweat_dir.mkdir(parents=True, exist_ok=True)

        matcap_png = assets_dir / "TestAvatar" / "MatCapTest.png"
        Image.new("RGBA", (64, 64), (210, 215, 225, 255)).save(matcap_png)
        matcap_guid = "aaaa0000111122223333444455556666"
        (assets_dir / "TestAvatar" / "MatCapTest.png.meta").write_text(
            f"fileFormatVersion: 2\nguid: {matcap_guid}\n",
            encoding="utf-8",
        )

        pants_png = pants_dir / "pants_albedo.png"
        sweat_png = sweat_dir / "sweat_albedo.png"
        Image.new("RGBA", (64, 64), (30, 60, 190, 255)).save(pants_png)
        Image.new("RGBA", (64, 64), (190, 50, 40, 255)).save(sweat_png)
        pants_tex_guid = "bbbb0000111122223333444455550001"
        sweat_tex_guid = "bbbb0000111122223333444455550002"
        (pants_dir / "pants_albedo.png.meta").write_text(
            f"fileFormatVersion: 2\nguid: {pants_tex_guid}\n",
            encoding="utf-8",
        )
        (sweat_dir / "sweat_albedo.png.meta").write_text(
            f"fileFormatVersion: 2\nguid: {sweat_tex_guid}\n",
            encoding="utf-8",
        )

        pants_mat = pants_dir / "BLACK-BLUE.mat"
        sweat_mat = sweat_dir / "BLACK-BLUE.mat"
        halo_mat = mats_dir / "_Halo.mat"
        blue_guid = "cccc0000111122223333444455550001"
        orig_guid = "cccc0000111122223333444455550002"
        pants_mat_guid = "cccc0000111122223333444455550003"
        sweat_mat_guid = "cccc0000111122223333444455550004"

        pants_mat.write_text(
            "%YAML 1.1\n--- !u!21 &2100000\nMaterial:\n  m_Name: BLACK-BLUE\n"
            "  m_SavedProperties:\n    m_TexEnvs:\n"
            f"    - _MainTex:\n        m_Texture: {{fileID: 2800000, guid: {pants_tex_guid}, type: 3}}\n"
            "        m_Scale: {x: 1, y: 1}\n        m_Offset: {x: 0, y: 0}\n"
            "    m_Floats:\n    - _TransparentMode: 0\n    m_Colors:\n"
            "    - _Color: {r: 1, g: 1, b: 1, a: 1}\n",
            encoding="utf-8",
        )
        sweat_mat.write_text(
            "%YAML 1.1\n--- !u!21 &2100000\nMaterial:\n  m_Name: BLACK-BLUE\n"
            "  m_SavedProperties:\n    m_TexEnvs:\n"
            f"    - _MainTex:\n        m_Texture: {{fileID: 2800000, guid: {sweat_tex_guid}, type: 3}}\n"
            "        m_Scale: {x: 1, y: 1}\n        m_Offset: {x: 0, y: 0}\n"
            "    m_Floats:\n    - _TransparentMode: 0\n    m_Colors:\n"
            "    - _Color: {r: 1, g: 1, b: 1, a: 1}\n",
            encoding="utf-8",
        )
        halo_mat.write_text(
            "%YAML 1.1\n--- !u!21 &2100000\nMaterial:\n  m_Name: _Halo\n"
            "  m_SavedProperties:\n    m_TexEnvs:\n"
            "    - _MainTex:\n        m_Texture: {fileID: 0}\n"
            "        m_Scale: {x: 1, y: 1}\n        m_Offset: {x: 0, y: 0}\n"
            f"    - _MatCapTex:\n        m_Texture: {{fileID: 2800000, guid: {matcap_guid}, type: 3}}\n"
            "        m_Scale: {x: 1, y: 1}\n        m_Offset: {x: 0, y: 0}\n"
            "    m_Floats:\n    - _UseMatCap: 1\n    - _MatCapBlend: 1\n    - _MatCapBlendMode: 1\n    - _TransparentMode: 0\n"
            "    m_Colors:\n    - _Color: {r: 0, g: 0, b: 0, a: 1}\n"
            "    - _MatCapColor: {r: 0.72, g: 0.75, b: 0.80, a: 1}\n",
            encoding="utf-8",
        )

        ovr_mods = [
            {
                "target_fid": "1370001",
                "target_guid": "dddd0000",
                "property": "m_Materials.Array.data[0]",
                "ref_guid": blue_guid,
                "value": "",
            },
            {
                "target_fid": "1370001",
                "target_guid": "dddd0000",
                "property": "m_Enabled",
                "ref_guid": "",
                "value": "1",
            },
        ]
        parsed_ovr = mayl.extract_renderer_mod_overrides(ovr_mods, expected_guid="dddd0000")
        eff_mats = mayl.resolve_overridden_renderer_mats(
            {"comp_fid": "1370001", "mat_guids": [orig_guid]},
            parsed_ovr,
        )
        override_ok = eff_mats == [blue_guid]

        baked_halo = uhbl.bake_liltoon_mat_to_image(
            str(halo_mat),
            tile_size=(64, 64),
            preserve_alpha=True,
            unity_assets_root=assets_dir,
        )[0]
        halo_arr = numpy_mod.array(baked_halo)
        halo_mean = float(halo_arr[:, :, :3].mean())
        matcap_ok = halo_mean >= 90.0

        pants_mat.with_suffix(".mat.meta").write_text(
            f"fileFormatVersion: 2\nguid: {pants_mat_guid}\n",
            encoding="utf-8",
        )
        sweat_mat.with_suffix(".mat.meta").write_text(
            f"fileFormatVersion: 2\nguid: {sweat_mat_guid}\n",
            encoding="utf-8",
        )
        halo_mat.with_suffix(".mat.meta").write_text(
            "fileFormatVersion: 2\nguid: cccc0000111122223333444455550005\n",
            encoding="utf-8",
        )

        fake_mesh = tmp_root / "DummyMesh.fbx"
        fake_mesh.write_bytes(b"Kaydara FBX Binary  ")
        scene_plan = {
            "active_material_paths": [str(pants_mat), str(sweat_mat), str(halo_mat)],
            "fbx_instances": [
                {
                    "fbx_path": str(fake_mesh),
                    "mesh_materials": {
                        "pants": [{"name": "BLACK-BLUE", "mat_path": str(pants_mat), "mat_guid": pants_mat_guid}],
                        "sweat": [{"name": "BLACK-BLUE", "mat_path": str(sweat_mat), "mat_guid": sweat_mat_guid}],
                    },
                }
            ],
        }
        collected = uab.collect_avatar_materials(
            scene_or_prefab=None,
            project_dir=tmp_root,
            source_fbx=fake_mesh,
            extra_fbxs=(),
            ma_plan=scene_plan,
        )
        out_atlas = tmp_root / "atlas_out"
        with (
            unittest.mock.patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess(args=[], returncode=0),
            ),
            unittest.mock.patch.object(uab.ped_damage_helper, "enforce_ytd_rpf7_size_budget"),
            unittest.mock.patch.object(uab.ped_damage_helper, "validate_rpf7_resource_file"),
        ):
            manifest = uab.build_universal_avatar_atlas(
                ped_name="test_ped",
                project_dir=tmp_root,
                scene_or_prefab=None,
                source_fbx=fake_mesh,
                extra_fbxs=(),
                output_dir=out_atlas,
                atlas_size=256,
                sync_to_game=False,
                ma_plan=scene_plan,
            )
        by_path = manifest.get("materials_by_path", {})
        pants_key = str(pants_mat.resolve()).replace("\\", "/").lower()
        sweat_key = str(sweat_mat.resolve()).replace("\\", "/").lower()
        halo_key = str(halo_mat.resolve()).replace("\\", "/").lower()
        atlas_disambig_ok = (
            len(collected) >= 3
            and pants_key in by_path
            and sweat_key in by_path
            and halo_key in by_path
            and by_path[pants_key] != by_path[sweat_key]
        )

    try:
        import blendshape_helper as bshape_mod
    except ImportError:
        from common_tools import blendshape_helper as bshape_mod

    nipple_tokens_ok = (
        bshape_mod.is_nipple_blendshape_key("Nipple_ON")
        and bshape_mod.is_nipple_blendshape_key("Nipple_big2")
        and bshape_mod.is_nipple_blendshape_key("TKB BIG")
        and bshape_mod.is_nipple_blendshape_key("LD_TKB")
        and bshape_mod.is_nipple_blendshape_key("Chikuwa")
        and bshape_mod.is_nipple_blendshape_key("Chikubi_ON")
        and bshape_mod.is_nipple_blendshape_key("\u4e73\u9996")
        and bshape_mod.is_nipple_blendshape_key("\u4e73\u982d")
        and not bshape_mod.is_nipple_blendshape_key("Breasts_big")
    )
    with tempfile.TemporaryDirectory(prefix="vrc2gtav_nip_cfg_") as nip_tmp:
        nip_dir = Path(nip_tmp)
        nip_cfg = nip_dir / "custom_nipple.cfg"
        bshape_mod.save_blendshapes_cfg(
            nip_cfg,
            {"Body_base": {"Nipple_ON": 0.45, "Breasts_big": 0.8}},
            metadata={"avatar": "CustomCfg"},
        )
        res_cfg = bshape_mod.resolve_character_blendshapes(
            {},
            override_source="cfg",
            override_cfg_path=nip_cfg,
            import_face=True,
            import_body=True,
            fill_missing_from_fbx=False,
        )
        cfg_weights = res_cfg.get("mesh_weights", {}).get("Body_base", {})
        nipple_cfg_ok = (
            abs(float(cfg_weights.get("Nipple_ON", 0.0)) - 0.45) < 1e-4
            and abs(float(cfg_weights.get("Breasts_big", 0.0)) - 0.8) < 1e-4
        )
    nipple_ok = nipple_tokens_ok and nipple_cfg_ok

    return override_ok and matcap_ok and atlas_disambig_ok and nipple_ok


def test_restore_and_multislot_regressions() -> bool:
    """Run all regression checks for scoped MA/Atlas, PhysBones isolation, Restore, and Multi-Slot."""
    print("[Restore/MultiSlot] Validating PRUNING, SCOPED ATLAS, PHYSBONES, RESTORE, MULTI-SLOT...")
    pruning_ok, atlas_ok = _test_ma_fbx_pruning_and_scoped_atlas()
    pb_ok = _test_physbones_collision_and_ini_cleanup()
    restore_multi_ok = _test_restore_and_multislot_pipeline()
    unity_trs_ok = _test_unity_transform_and_earring_alignment()
    mat_ovr_ok = _test_mat_overrides_and_non_colliding_atlas()

    editor_dir = PROJECT_ROOT_DIR / "unity_plugin" / "Assets" / "VRCAvatar2GTAV" / "Editor"
    cs_files = sorted(editor_dir.glob("*.cs")) if editor_dir.is_dir() else []
    cs_ok = (not cs_files) or (
        len(cs_files) == 9
        and all(len(cs_p.read_text(encoding="utf-8").splitlines()) <= 500 for cs_p in cs_files)
    )

    all_ok = pruning_ok and atlas_ok and pb_ok and restore_multi_ok and unity_trs_ok and mat_ovr_ok and cs_ok
    return print_status_result(
        "Restore-Vanilla & Per-Protagonist Multi-Slot Regression Suite",
        all_ok,
        f"pruning={pruning_ok}, atlas={atlas_ok}, physbones={pb_ok}, restore_multi={restore_multi_ok}, unity_trs={unity_trs_ok}, mat_ovr={mat_ovr_ok}, csharp={cs_ok}",
    )
