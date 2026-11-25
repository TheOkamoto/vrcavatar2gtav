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
from typing import Any, Dict, List, Sequence

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

        captured_build_cmds: List[List[str]] = []

        def _fake_rage_run(cmd_args: Sequence[str], **_kwargs: Any) -> subprocess.CompletedProcess:
            captured_build_cmds.append(list(cmd_args))
            if "-o" in cmd_args:
                out_idx = list(cmd_args).index("-o") + 1
                Path(cmd_args[out_idx]).write_bytes(b"RSC7MOCK")
            return subprocess.CompletedProcess(cmd_args, 0, "", "")

        with (
            unittest.mock.patch.object(universal_atlas_builder.subprocess, "run", side_effect=_fake_rage_run),
            unittest.mock.patch.object(universal_atlas_builder.npc_registry_helper, "build_safe_rage_cmd", side_effect=lambda *cmd_args, **_unused: ["rage", *cmd_args]),
            unittest.mock.patch.object(universal_atlas_builder.project_paths, "get_rage_cli", return_value="rage"),
        ):
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
        spec_size = Image.open(atlas_res["spec_png"]).size
        normal_file_size = Image.open(atlas_res["normal_png"]).size
        diff_mode = Image.open(atlas_res["atlas_png"]).mode
        rage_png_inputs = [
            tok for cmd_list in captured_build_cmds for tok in cmd_list
            if tok.lower().endswith(".png")
        ]
        atlas_ok = (
            list(collected.keys()) == ["VariantSkin"]
            and collected["VariantSkin"]["alpha_mode"] == "opaque"
            and spec_size == (512, 512)
            and normal_file_size == (512, 512)
            and diff_mode == "RGB"
            and rage_png_inputs == [str(atlas_res["atlas_png"])]
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

        vtoon_ini = tmp_dir / "GTAVVToon.ini"
        vtoon_profile_helper.upsert_vtoon_ini_character(
            [vtoon_ini], 1, "player_zero", "a.png", "b.png", {0: {"rim_strength": 0.5}}
        )
        vtoon_profile_helper.upsert_vtoon_ini_character(
            [vtoon_ini], 2, "player_one", "c.png", "d.png", {0: {"rim_strength": 0.7}}
        )
        vtoon_profile_helper.remove_vtoon_ini_character([vtoon_ini], char_ids=(1,), char_names=("player_zero",))
        vtoon_after = vtoon_ini.read_text(encoding="utf-8")

        ini_ok = (
            "player_zero" not in pb_after
            and "Chain_player_one_Hair" in pb_after
            and "model = player_one" in pb_after
            and "blink_count = 1" in pb_after
            and "[Char_1]" not in vtoon_after
            and "[Char_2]" in vtoon_after
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
                inner_path = target_dir / "models" / "cdimages" / "streamedpeds_players.rpf"
                inner_path.parent.mkdir(parents=True, exist_ok=True)
                inner_path.write_bytes(b"MOD_INNER")
            elif archive_path == van_rpf:
                inner_path = target_dir / "models" / "cdimages" / "streamedpeds_players.rpf"
                inner_path.parent.mkdir(parents=True, exist_ok=True)
                inner_path.write_bytes(b"VAN_INNER")
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
            unittest.mock.patch.object(npc_registry_helper.project_paths, "get_gtav_root_dir", return_value=tmp_dir),
            unittest.mock.patch.object(npc_registry_helper.project_paths, "get_staging_dir", return_value=tmp_dir),
            unittest.mock.patch.object(npc_registry_helper.project_paths, "get_project_root", return_value=tmp_dir),
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
                build_func=_fake_build,
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
        ear_x_values = sorted(
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
            and len(ear_x_values) == 2
            and ear_x_values[0] < -0.04
            and ear_x_values[1] > 0.04
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
            unittest.mock.patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=0)),
            unittest.mock.patch.object(uab.npc_registry_helper, "build_safe_rage_cmd", side_effect=lambda *cmd_args, **_unused: ["rage", *cmd_args]),
            unittest.mock.patch.object(uab.project_paths, "get_rage_cli", return_value="rage"),
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

    glass_trans_ok = False
    with tempfile.TemporaryDirectory(prefix="vrc2gtav_glass_alpha_") as glass_tmp:
        glass_dir = Path(glass_tmp)
        lenses_mat = glass_dir / "Glass_Lenses.mat"
        lenses_mat.write_text(
            "m_Name: Glass_Lenses\n"
            "m_Shader: {fileID: 4800000, guid: 165365ab7100a044ca85fc8c33548a62, type: 3}\n"
            "m_CustomRenderQueue: 2461\n"
            "m_SavedProperties:\n"
            "  m_Floats:\n"
            "  - _AlphaMaskMode: 1\n"
            "  - _AlphaMaskScale: 1\n"
            "  - _AlphaMaskValue: -0.878\n"
            "  - _TransparentMode: 0\n"
            "  m_Colors:\n"
            "  - _Color: {r: 1, g: 1, b: 1, a: 1}\n",
            encoding="utf-8",
        )
        watch_mat = glass_dir / "Watch_Refract.mat"
        watch_mat.write_text(
            "m_Name: Watch_Refract\n"
            "m_Shader: {fileID: 4800000, guid: dce3f3e248acc7b4daeda00daf616b4d, type: 3}\n"
            "m_CustomRenderQueue: -1\n"
            "m_SavedProperties:\n"
            "  m_Floats:\n"
            "  - _AlphaMaskMode: 1\n"
            "  - _AlphaMaskScale: 1\n"
            "  - _AlphaMaskValue: -1\n"
            "  - _TransparentMode: 0\n"
            "  m_Colors:\n"
            "  - _Color: {r: 1, g: 1, b: 1, a: 1}\n",
            encoding="utf-8",
        )
        parsed_lenses = uab.parse_unity_material_file(lenses_mat, {})
        parsed_watch = uab.parse_unity_material_file(watch_mat, {})
        import unity_hair_bake_layer

        baked_lenses = unity_hair_bake_layer.bake_liltoon_mat_to_image(
            lenses_mat, tile_size=(64, 64), preserve_alpha=True, unity_assets_root=glass_dir
        )
        baked_watch = unity_hair_bake_layer.bake_liltoon_mat_to_image(
            watch_mat, tile_size=(64, 64), preserve_alpha=True, unity_assets_root=glass_dir
        )
        lens_alpha = int(baked_lenses[0].getpixel((32, 32))[3]) if baked_lenses else -1
        watch_alpha = int(baked_watch[0].getpixel((32, 32))[3]) if baked_watch else -1
        import universal_gtav_builder
        import universal_gtav_rigging_layer

        zero_anim = glass_dir / "Default_face.anim"
        zero_anim.write_text(
            "%YAML 1.1\n--- !u!74 &7400000\nAnimationClip:\n  m_Name: Default_face\n"
            "  m_FloatCurves:\n  - serializedVersion: 2\n    curve:\n      m_Curve:\n"
            "      - time: 0\n        value: 0\n"
            "    attribute: blendShape.eye_pleasure\n    path: Body\n",
            encoding="utf-8",
        )
        picked_zero = universal_gtav_rigging_layer._pick_default_face_anim(
            {"anim_files": [str(zero_anim)]}, ["Shinano"]
        )
        slot_map_test = universal_gtav_builder.map_blender_slots_to_unity_submeshes(
            [1, 1, 2, 0, 0, 3], 4
        )
        glass_trans_ok = (
            parsed_lenses.get("alpha_mode") == "transparent"
            and parsed_watch.get("alpha_mode") == "transparent"
            and 25 <= lens_alpha <= 38
            and 15 <= watch_alpha <= 28
            and slot_map_test == {1: 0, 2: 1, 0: 2, 3: 3}
            and picked_zero is None
        )

    return override_ok and matcap_ok and atlas_disambig_ok and nipple_ok and glass_trans_ok


def _test_single_tex_ytd_and_physbone_unwrap() -> bool:
    """Verify single-tex YTD, embedded bump/spec, watermark resize, and hair/ribbon PB fixes."""
    from PIL import Image
    import ped_damage_helper
    import physbone_scene_extractor_layer as psel
    import repack_and_deploy_everything as repack_helper
    import universal_gtav_rigging_layer as rig_layer
    import vtoon_profile_helper

    class _FakeTexProps:
        def __init__(self) -> None:
            self.embedded = False

    class _FakeTexNode:
        def __init__(self) -> None:
            self.image = None
            self.texture_properties = _FakeTexProps()

    class _FakeNodeTree:
        def __init__(self, node_map: Dict[str, Any]) -> None:
            self.nodes = node_map

    class _FakeShaderMat:
        def __init__(self) -> None:
            self.name = ""
            node_map = {
                "DiffuseSampler": _FakeTexNode(),
                "BumpSampler": _FakeTexNode(),
                "SpecSampler": _FakeTexNode(),
                "AnisoNoiseSpecSampler": _FakeTexNode(),
            }
            self.node_tree = _FakeNodeTree(node_map)

    fake_mat = ped_damage_helper.create_ped_material(
        lambda _shader_func: _FakeShaderMat(),
        "vrc_embed_test",
        diffuse_image="diff_img",
        bump_image="bump_img",
        spec_image="spec_img",
        embed_bump_spec=True,
    )
    embed_nodes = fake_mat.node_tree.nodes
    embed_ok = (
        embed_nodes["DiffuseSampler"].texture_properties.embedded is False
        and embed_nodes["BumpSampler"].texture_properties.embedded is True
        and embed_nodes["SpecSampler"].texture_properties.embedded is True
        and embed_nodes["AnisoNoiseSpecSampler"].texture_properties.embedded is True
    )

    with tempfile.TemporaryDirectory(prefix="vrc2gtav_wm_resize_") as tmp_watermark:
        watermark_dir = Path(tmp_watermark)
        stamped = vtoon_profile_helper.stamp_vtoon_watermark_block(
            Image.new("RGB", (1024, 1024), (80, 120, 200)),
            char_id=2,
        )
        watermark_png = watermark_dir / "player_two_atlas_2k.png"
        stamped.save(watermark_png)
        repack_helper._resize_extracted_png_for_budget(watermark_png, 512, 256)
        with Image.open(watermark_png) as resized_img:
            watermark_resize_ok = (
                resized_img.size == (512, 512)
                and vtoon_profile_helper.decode_vtoon_watermark_block(resized_img) == 2
            )

        import physbone_helper

        pb_script_line = (
            f"  m_Script: {{fileID: {physbone_helper.VRCHAT_PHYSBONE_CLASS_FILE_ID}, "
            f"guid: {physbone_helper.VRCHAT_PHYSBONE_SCRIPT_GUID}, type: 3}}\n"
        )
        scene_file = watermark_dir / "HairBow.unity"
        scene_file.write_text(
            "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
            "--- !u!1 &10\nGameObject:\n  m_Component:\n  - component: {fileID: 11}\n  m_Name: TestAvatar\n  m_IsActive: 1\n"
            "--- !u!4 &11\nTransform:\n  m_GameObject: {fileID: 10}\n  m_Father: {fileID: 0}\n  m_Children:\n  - {fileID: 21}\n  - {fileID: 31}\n  - {fileID: 41}\n"
            "--- !u!1 &20\nGameObject:\n  m_Component:\n  - component: {fileID: 21}\n  - component: {fileID: 22}\n  m_Name: Head\n  m_IsActive: 1\n"
            "--- !u!4 &21\nTransform:\n  m_GameObject: {fileID: 20}\n  m_Father: {fileID: 11}\n  m_Children:\n  - {fileID: 25}\n  - {fileID: 26}\n  - {fileID: 51}\n"
            "--- !u!114 &22\nMonoBehaviour:\n  m_GameObject: {fileID: 20}\n  m_Enabled: 1\n"
            + pb_script_line
            + "  rootTransform: {fileID: 21}\n"
            "--- !u!1 &24\nGameObject:\n  m_Component:\n  - component: {fileID: 25}\n  m_Name: Child\n  m_IsActive: 1\n"
            "--- !u!4 &25\nTransform:\n  m_GameObject: {fileID: 24}\n  m_Father: {fileID: 21}\n  m_Children: []\n"
            "--- !u!1 &27\nGameObject:\n  m_Component:\n  - component: {fileID: 26}\n  - component: {fileID: 28}\n  m_Name: Back.R.001\n  m_IsActive: 1\n"
            "--- !u!4 &26\nTransform:\n  m_GameObject: {fileID: 27}\n  m_Father: {fileID: 21}\n  m_Children:\n  - {fileID: 29}\n"
            "--- !u!114 &28\nMonoBehaviour:\n  m_GameObject: {fileID: 27}\n  m_Enabled: 1\n"
            + pb_script_line
            + "  rootTransform: {fileID: 26}\n"
            "--- !u!1 &30\nGameObject:\n  m_Component:\n  - component: {fileID: 29}\n  m_Name: Back.R.002\n  m_IsActive: 1\n"
            "--- !u!4 &29\nTransform:\n  m_GameObject: {fileID: 30}\n  m_Father: {fileID: 26}\n  m_Children: []\n"
            "--- !u!1 &50\nGameObject:\n  m_Component:\n  - component: {fileID: 51}\n  - component: {fileID: 52}\n  m_Name: UN_Ribbon\n  m_IsActive: 1\n"
            "--- !u!4 &51\nTransform:\n  m_GameObject: {fileID: 50}\n  m_Father: {fileID: 21}\n  m_Children:\n  - {fileID: 61}\n  - {fileID: 71}\n"
            "--- !u!114 &52\nMonoBehaviour:\n  m_GameObject: {fileID: 50}\n  m_Enabled: 1\n"
            + pb_script_line
            + "  rootTransform: {fileID: 51}\n"
            "--- !u!1 &60\nGameObject:\n  m_Component:\n  - component: {fileID: 61}\n  m_Name: UN_Hat_L.001\n  m_IsActive: 1\n"
            "--- !u!4 &61\nTransform:\n  m_GameObject: {fileID: 60}\n  m_Father: {fileID: 51}\n  m_Children:\n  - {fileID: 63}\n"
            "--- !u!1 &62\nGameObject:\n  m_Component:\n  - component: {fileID: 63}\n  m_Name: UN_Hat_L.002\n  m_IsActive: 1\n"
            "--- !u!4 &63\nTransform:\n  m_GameObject: {fileID: 62}\n  m_Father: {fileID: 61}\n  m_Children: []\n"
            "--- !u!1 &70\nGameObject:\n  m_Component:\n  - component: {fileID: 71}\n  m_Name: UN_Hat_R.001\n  m_IsActive: 1\n"
            "--- !u!4 &71\nTransform:\n  m_GameObject: {fileID: 70}\n  m_Father: {fileID: 51}\n  m_Children:\n  - {fileID: 73}\n"
            "--- !u!1 &72\nGameObject:\n  m_Component:\n  - component: {fileID: 73}\n  m_Name: UN_Hat_R.002\n  m_IsActive: 1\n"
            "--- !u!4 &73\nTransform:\n  m_GameObject: {fileID: 72}\n  m_Father: {fileID: 71}\n  m_Children: []\n"
            "--- !u!1 &35\nGameObject:\n  m_Component:\n  - component: {fileID: 31}\n  - component: {fileID: 32}\n  m_Name: UN_Ribbon\n  m_IsActive: 1\n"
            "--- !u!4 &31\nTransform:\n  m_GameObject: {fileID: 35}\n  m_Father: {fileID: 11}\n  m_Children:\n  - {fileID: 33}\n"
            "--- !u!114 &32\nMonoBehaviour:\n  m_GameObject: {fileID: 35}\n  m_Enabled: 1\n"
            + pb_script_line
            + "  rootTransform: {fileID: 31}\n"
            "--- !u!1 &34\nGameObject:\n  m_Component:\n  - component: {fileID: 33}\n  m_Name: RibbonRoot\n  m_IsActive: 1\n"
            "--- !u!4 &33\nTransform:\n  m_GameObject: {fileID: 34}\n  m_Father: {fileID: 31}\n  m_Children: []\n"
            "--- !u!1 &40\nGameObject:\n  m_Component:\n  - component: {fileID: 41}\n  m_Name: UN_Ribbon_L.002\n  m_IsActive: 1\n"
            "--- !u!4 &41\nTransform:\n  m_GameObject: {fileID: 40}\n  m_Father: {fileID: 11}\n  m_Children: []\n",
            encoding="utf-8",
        )
        fake_fbx = watermark_dir / "FakeHair.fbx"
        fake_fbx.write_bytes(b"Kaydara FBX Binary  \x00")
        seen_excluded: List[List[str]] = []

        def _fake_inspect(_fbxs: Any, excluded_meshes: Sequence[str] = ()) -> Any:
            seen_excluded.append(list(excluded_meshes))
            all_bones = {
                "head", "child", "back.r.001", "back.r.002",
                "un_ribbon", "un_hatroot", "un_hat_l.001", "un_hat_l.002",
                "un_hat_r.001", "un_hat_r.002", "un_ribbon_l.002",
            }
            weighted_bones = {
                "head", "back.r.001", "back.r.002",
                "un_ribbon", "un_hat_l.001", "un_hat_l.002",
                "un_hat_r.001", "un_hat_r.002", "un_ribbon_l.002",
            }
            parent_match = {
                "back.r.001": "head",
                "back.r.002": "back.r.001",
                "un_hat_l.001": "un_hatroot",
                "un_hat_l.002": "un_hat_l.001",
                "un_hat_r.001": "un_hatroot",
                "un_hat_r.002": "un_hat_r.001",
                "un_ribbon_l.002": "un_ribbon",
            }
            mesh_match = {
                fake_fbx: {
                    "Back": {"back.r.001", "back.r.002"},
                    "UN2_Beret": {"un_hat_l.001", "un_hat_l.002", "un_hat_r.001", "un_hat_r.002"},
                    "UN1_ChestRibbon": {"un_ribbon", "un_ribbon_l.002"},
                }
            }
            return all_bones, weighted_bones, parent_match, mesh_match, True

        with unittest.mock.patch.object(psel, "_inspect_fbx_weights_detailed", side_effect=_fake_inspect):
            ext_res = psel.extract_unity_scene_physbones(
                scene_file,
                avatar_name="TestAvatar",
                fbx_paths=[fake_fbx],
                excluded_meshes=["Back", "OldDress"],
                active_meshes=["Back", "UN2_Beret"],
                prune_orphaned=True,
                verbose=False,
            )
        roots = [item["root_bone"] for item in ext_res.get("chains", [])]
        pb_extract_ok = (
            "back" not in [name_str.lower() for name_str in (seen_excluded[0] if seen_excluded else [])]
            and "Back.R.001" in roots
            and "UN_Hat_L.001" in roots
            and "UN_Hat_R.001" in roots
            and "Head" not in roots
            and "UN_Ribbon" not in roots
        )

    parent_lut = {"back.r.001": "Hair Root", "hair root": "Head", "ribbon": "Hair Root"}
    rig_ok = (
        rig_layer._resolve_universal_target_bone("Back.R.001", "Back", {}, src_parent_lookup=parent_lut) == "SKEL_Head"
        and rig_layer._resolve_universal_target_bone("Head", "Body", {"head": "PB_Auto_Head_0"}) == "SKEL_Head"
        and rig_layer._resolve_universal_target_bone("Ribbon", "Ribbon", {}, src_parent_lookup=parent_lut) == "SKEL_Head"
    )
    return embed_ok and watermark_resize_ok and pb_extract_ok and rig_ok


def _test_seam_dds_and_torso_decimate() -> bool:
    import struct
    import tempfile
    import types

    try:
        import blender_hair_helper as bhh_mod
    except ImportError:
        import common_tools.blender_hair_helper as bhh_mod

    class _FakeMatList(list):
        def find(self, target_name: str) -> int:
            for mat_pos, mat_entry in enumerate(self):
                if getattr(mat_entry, "name", "") == target_name:
                    return mat_pos
            return -1

    class _FakeMaterial:
        def __init__(self, mat_name: str) -> None:
            self.name = mat_name

        def copy(self) -> "_FakeMaterial":
            return _FakeMaterial(self.name)

    verts_seq: List[Any] = []
    polys_seq: List[Any] = []

    def _add_symmetric_band_island(ring_count: int, z_base: float, z_step: float) -> List[int]:
        island_poly_ids: List[int] = []
        ring_verts: List[Tuple[int, int, int]] = []
        for ring_idx in range(ring_count + 1):
            z_coord = z_base + float(ring_idx) * z_step
            idx_left = len(verts_seq)
            verts_seq.append(types.SimpleNamespace(co=(-0.10, -0.05, z_coord)))
            idx_mid = len(verts_seq)
            verts_seq.append(types.SimpleNamespace(co=(0.0, -0.06, z_coord)))
            idx_right = len(verts_seq)
            verts_seq.append(types.SimpleNamespace(co=(0.10, -0.05, z_coord)))
            ring_verts.append((idx_left, idx_mid, idx_right))
        for ring_idx in range(ring_count):
            row_first = ring_verts[ring_idx]
            row_second = ring_verts[ring_idx + 1]
            for tri_verts in (
                (row_first[0], row_first[1], row_second[1]),
                (row_first[0], row_second[1], row_second[0]),
                (row_first[1], row_first[2], row_second[2]),
                (row_first[1], row_second[2], row_second[1]),
            ):
                poly_id = len(polys_seq)
                polys_seq.append(
                    types.SimpleNamespace(index=poly_id, material_index=0, vertices=tri_verts)
                )
                island_poly_ids.append(poly_id)
        return island_poly_ids

    body_polys = _add_symmetric_band_island(7, 0.20, 0.03)
    sweat_polys = _add_symmetric_band_island(8, 0.25, 0.03)
    hair_polys = _add_symmetric_band_island(60, 0.50, 0.01)

    mats_list = _FakeMatList([_FakeMaterial("ped_atlas")])
    mesh_data = types.SimpleNamespace(
        polygons=polys_seq,
        vertices=verts_seq,
        materials=mats_list,
        update=lambda: None,
    )
    mock_obj = types.SimpleNamespace(name="SKEL_ROOT", data=mesh_data)
    created_chunks = bhh_mod.split_oversized_material_geometries(
        mock_obj, max_vertices_per_chunk=120
    )
    body_mats = {polys_seq[pid].material_index for pid in body_polys}
    sweat_mats = {polys_seq[pid].material_index for pid in sweat_polys}
    hair_sym_ok = True
    for base_pid in range(hair_polys[0], hair_polys[-1] + 1, 4):
        if polys_seq[base_pid].material_index != polys_seq[base_pid + 2].material_index:
            hair_sym_ok = False
            break
    split_ok = (
        created_chunks >= 1
        and len(body_mats) == 1
        and len(sweat_mats) == 1
        and hair_sym_ok
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        norm_dds = tmp_path / "flat_normal.dds"
        spec_dds = tmp_path / "black_spec.dds"
        bhh_mod.ensure_solid_rgba_dds(norm_dds, rgba_color=(128, 128, 255, 255), size=32)
        bhh_mod.ensure_solid_rgba_dds(spec_dds, rgba_color=(0, 0, 0, 255), size=32)
        norm_raw = norm_dds.read_bytes()
        spec_raw = spec_dds.read_bytes()
        norm_hdr_ok = (
            len(norm_raw) == 4224
            and norm_raw[:4] == b"DDS "
            and struct.unpack("<4I", norm_raw[4:20]) == (124, 0x100F, 32, 32)
            and norm_raw[128:] == bytes((255, 128, 128, 255)) * 1024
        )
        spec_hdr_ok = (
            len(spec_raw) == 4224
            and spec_raw[:4] == b"DDS "
            and spec_raw[128:] == bytes((0, 0, 0, 255)) * 1024
        )
        dds_ok = norm_hdr_ok and spec_hdr_ok

    mod_sweat = types.SimpleNamespace(decimate_type="", ratio=1.0, use_symmetry=False, symmetry_axis="")
    mod_hair = types.SimpleNamespace(decimate_type="", ratio=1.0, use_symmetry=False, symmetry_axis="")
    sweat_obj = types.SimpleNamespace(name="ladies-sweat", data=types.SimpleNamespace(polygons=[0] * 18688))
    shirt_obj = types.SimpleNamespace(name="UN1_Shirt", data=types.SimpleNamespace(polygons=[0] * 18150))
    hair_obj = types.SimpleNamespace(name="Hair_Back", data=types.SimpleNamespace(polygons=[0] * 28000))
    prop_obj = types.SimpleNamespace(name="Bag_Prop", data=types.SimpleNamespace(polygons=[0] * 21000))
    eff_sweat = bhh_mod.configure_rpf7_decimate_modifier(mod_sweat, sweat_obj, 0.45)
    eff_hair = bhh_mod.configure_rpf7_decimate_modifier(mod_hair, hair_obj, 0.45)
    sorted_names = [
        item.name
        for item in sorted(
            [sweat_obj, shirt_obj, hair_obj, prop_obj],
            key=bhh_mod.rpf7_budget_priority_key,
            reverse=True,
        )
    ]
    decimate_ok = (
        eff_sweat >= 0.80
        and abs(eff_hair - 0.45) < 1e-6
        and mod_sweat.use_symmetry is True
        and mod_sweat.symmetry_axis == "X"
        and mod_hair.use_symmetry is True
        and bhh_mod.is_protected_small_torso_cloth(sweat_obj, True) is True
        and bhh_mod.is_protected_small_torso_cloth(hair_obj, True) is False
        and sorted_names == ["Hair_Back", "Bag_Prop", "ladies-sweat", "UN1_Shirt"]
    )
    return split_ok and dds_ok and decimate_ok


def _test_vtoon_hash_sync_and_budget_tiers() -> bool:
    import tempfile

    try:
        import repack_and_deploy_everything as rpk_mod
    except ImportError:
        import common_tools.repack_and_deploy_everything as rpk_mod

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        proj_root = tmp_path / "proj"
        pkg_dir = proj_root / "2_Michael_Shinano_EternalReunion" / "5_rpf_package"
        gtav_dir = tmp_path / "gtav"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        gtav_dir.mkdir(parents=True, exist_ok=True)

        # Verify sync_gtav_runtime_mods overwrites same-size binaries when SHA-256 differs
        (pkg_dir / "GTAVVToon.asi").write_bytes(b"NEW_VTOON_BIN_01")
        (gtav_dir / "GTAVVToon.asi").write_bytes(b"OLD_VTOON_BIN_99")
        sync_res = rpk_mod.sync_gtav_runtime_mods(proj_root, gtav_dir, overwrite_inis=False)
        hash_sync_ok = (
            "GTAVVToon.asi" in sync_res.get("copied", [])
            and (gtav_dir / "GTAVVToon.asi").read_bytes() == b"NEW_VTOON_BIN_01"
        )

        # Verify 736KB DXT1 secondary slot compacts to 1024px (not skipped straight to 512px)
        players_auto = tmp_path / "players_auto"
        x64v_auto = tmp_path / "x64v_auto"
        ped_auto = players_auto / "player_one"
        (x64v_auto / "models" / "cdimages").mkdir(parents=True, exist_ok=True)
        ped_auto.mkdir(parents=True, exist_ok=True)
        (ped_auto / "accs_000_u.ydd").write_bytes(b"D" * 629)
        (ped_auto / "accs_diff_000_a_uni.ytd").write_bytes(b"D" * 400_000)
        (ped_auto / "uppr_diff_000_a_uni.ytd").write_bytes(b"A" * 736_310)
        (ped_auto / "uppr_diff_001_a_uni.ytd").write_bytes(b"B" * 736_310)

        seen_px: List[int] = []

        def _fake_compact(src_path: Path, dst_path: Path, *, max_diffuse_px: int, max_normal_px: int) -> Path:
            seen_px.append(max_diffuse_px)
            dst_path.write_bytes(b"C" * (200_000 if max_diffuse_px >= 1024 else 80_000))
            return dst_path

        def _fake_dummy(dst_path: Path) -> Path:
            dst_path.write_bytes(b"M" * 512)
            return dst_path

        res_auto = rpk_mod.ensure_x64v_streamed_budget(
            x64v_auto,
            players_auto,
            safe_max_bytes=1_000_000,
            secondary_atlas_size=0,
            compact_builder=_fake_compact,
            dummy_builder=_fake_dummy,
        )
        auto_tier_ok = (
            res_auto["compacted"]
            and seen_px == [1024]
            and (ped_auto / "uppr_diff_000_a_uni.ytd").stat().st_size == 736_310
            and (ped_auto / "uppr_diff_001_a_uni.ytd").stat().st_size == 200_000
            and (ped_auto / "accs_diff_000_a_uni.ytd").stat().st_size == 512
        )

        # Verify secondary_atlas_size=2048 keeps 2048px secondary slots while pruning unused dummies
        players_full = tmp_path / "players_full"
        x64v_full = tmp_path / "x64v_full"
        ped_full = players_full / "player_two"
        (x64v_full / "models" / "cdimages").mkdir(parents=True, exist_ok=True)
        ped_full.mkdir(parents=True, exist_ok=True)
        (ped_full / "accs_000_u.ydd").write_bytes(b"D" * 629)
        (ped_full / "accs_diff_000_a_uni.ytd").write_bytes(b"D" * 500_000)
        (ped_full / "uppr_diff_000_a_uni.ytd").write_bytes(b"A" * 1_100_000)
        (ped_full / "uppr_diff_001_a_uni.ytd").write_bytes(b"B" * 1_100_000)
        seen_full_px: List[int] = []

        def _track_full_compact(src_path: Path, dst_path: Path, *, max_diffuse_px: int, max_normal_px: int) -> Path:
            seen_full_px.append(max_diffuse_px)
            dst_path.write_bytes(b"C" * 100_000)
            return dst_path

        rpk_mod.ensure_x64v_streamed_budget(
            x64v_full,
            players_full,
            safe_max_bytes=2_300_000,
            secondary_atlas_size=2048,
            compact_builder=_track_full_compact,
            dummy_builder=_fake_dummy,
        )
        full_sec_ok = (
            seen_full_px == []
            and (ped_full / "uppr_diff_001_a_uni.ytd").stat().st_size == 1_100_000
            and (ped_full / "accs_diff_000_a_uni.ytd").stat().st_size == 512
        )

        # Verify run_multi_slot_builds preserves slot secondary_atlas_size=2048 & single-mip lock
        import restore_vanilla_helper as rvh_mod

        slots_file = tmp_path / "slots_2k.json"
        slots_file.write_text(
            json.dumps(
                {
                    "slots": [
                        {
                            "target_ped": "player_zero",
                            "source": str(tmp_path / "dummy.unity"),
                            "avatar_name": "DummyA",
                            "secondary_atlas_size": 2048,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        captured_slot_sec: List[int] = []
        captured_repack_sec: List[int] = []
        orig_repack_func = rvh_mod.repack_and_deploy_built_peds

        def _fake_build_func(**kwargs: Any) -> Dict[str, Any]:
            captured_slot_sec.append(int(kwargs.get("secondary_atlas_size", -1)))
            return {"ped_name": kwargs["target_ped"], "avatar_name": kwargs["avatar_name"]}

        def _fake_repack_func(built_peds: Any, *, secondary_atlas_size: int = 0) -> List[Path]:
            captured_repack_sec.append(int(secondary_atlas_size))
            return []

        rvh_mod.repack_and_deploy_built_peds = _fake_repack_func
        try:
            rvh_mod.run_multi_slot_builds(
                slots_file,
                shared_defaults={"secondary_atlas_size": None, "atlas_size": None},
                build_func=_fake_build_func,
                deploy=True,
                repack_and_deploy=True,
                secondary_atlas_size=0,
            )
        finally:
            rvh_mod.repack_and_deploy_built_peds = orig_repack_func

        atlas_src = (PROJECT_ROOT_DIR / "scripts" / "common_tools" / "universal_atlas_builder.py").read_text(encoding="utf-8")
        detour_src = (PROJECT_ROOT_DIR / "scripts" / "vtoon_asi" / "vtoon_detour.hpp").read_text(encoding="utf-8")
        mips_vtable_ok = (
            captured_slot_sec == [2048]
            and captured_repack_sec == [2048]
            and '"--mips", "1"' in atlas_src
            and "FnCreateDeferredContext1" in detour_src
            and "seenTable" in detour_src
        )
    return hash_sync_ok and auto_tier_ok and full_sec_ok and mips_vtable_ok


def _test_multislot_proportional_progress() -> bool:
    """Verify proportional multi-slot [PROGRESS pct=..] emission and Runner parsing."""
    import contextlib
    import io as io_stream
    import re
    import restore_vanilla_helper as rvh_mod
    import universal_gtav_rigging_layer as repack_mod

    pct_slot0 = repack_mod.compute_overall_progress_pct(0.68, slot_index=0, slot_total=3, build_share=0.82)
    pct_slot1 = repack_mod.compute_overall_progress_pct(0.68, slot_index=1, slot_total=3, build_share=0.82)
    pct_slot2 = repack_mod.compute_overall_progress_pct(0.68, slot_index=2, slot_total=3, build_share=0.82)
    math_ok = (15.0 <= pct_slot0 <= 25.0) and (40.0 <= pct_slot1 <= 50.0) and (68.0 <= pct_slot2 <= 78.0)

    captured = io_stream.StringIO()
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_path = Path(tmp_str)
        slots_file = tmp_path / "three_slots.json"
        slots_file.write_text(
            json.dumps(
                {
                    "slots": [
                        {"target_ped": "player_zero", "source": str(tmp_path / "a.unity"), "avatar_name": "Mini"},
                        {"target_ped": "player_one", "source": str(tmp_path / "b.unity"), "avatar_name": "Lounge"},
                        {"target_ped": "player_two", "source": str(tmp_path / "c.unity"), "avatar_name": "Reunion"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        orig_repack_func = rvh_mod.repack_and_deploy_built_peds

        def _fake_slot_build(**kwargs: Any) -> Dict[str, Any]:
            slot_idx = int(kwargs.get("slot_index", 0))
            slot_tot = int(kwargs.get("slot_total", 1))
            build_share = float(kwargs.get("build_share", 0.82))
            ped_id = str(kwargs["target_ped"])
            repack_mod.emit_slot_progress(
                0.68,
                "blender_export",
                slot_index=slot_idx,
                slot_total=slot_tot,
                build_share=build_share,
                ped_name=ped_id,
            )
            return {"ped_name": ped_id, "avatar_name": kwargs["avatar_name"]}

        def _fake_repack(built_peds: Any, *, secondary_atlas_size: int = 0) -> List[Path]:
            repack_mod.emit_progress_status(82.5, "rpf_deploy")
            repack_mod.emit_progress_status(99.5, "rpf_done")
            return []

        rvh_mod.repack_and_deploy_built_peds = _fake_repack
        try:
            with contextlib.redirect_stdout(captured):
                rvh_mod.run_multi_slot_builds(
                    slots_file,
                    build_func=_fake_slot_build,
                    deploy=True,
                    repack_and_deploy=True,
                )
        finally:
            rvh_mod.repack_and_deploy_built_peds = orig_repack_func

    out_text = captured.getvalue()
    pcts = [float(match_val) for match_val in re.findall(r"\[PROGRESS\s+pct=([0-9.]+)\]", out_text)]
    monotonic_ok = len(pcts) >= 8 and all(pcts[pct_idx] <= pcts[pct_idx + 1] for pct_idx in range(len(pcts) - 1))
    slots_labeled_ok = (
        "[1/3 Michael]" in out_text
        and "[2/3 Franklin]" in out_text
        and "[3/3 Trevor]" in out_text
        and pcts[0] < 5.0
        and max(pcts) >= 99.0
    )

    runner_path = PROJECT_ROOT_DIR / "unity_plugin" / "Assets" / "VRCAvatar2GTAV" / "Editor" / "Vrc2GtavProcessRunner.cs"
    builder_src = (PROJECT_ROOT_DIR / "scripts" / "common_tools" / "universal_gtav_builder.py").read_text(encoding="utf-8")
    runner_src = runner_path.read_text(encoding="utf-8") if runner_path.is_file() else ""
    csharp_runner_ok = (not runner_src) or (
        "ExplicitProgressRegex" in runner_src
        and "StageBannerRegex" in runner_src
        and "!_hasExplicitProgress" in runner_src
        and 'Progress = Math.Max(Progress, 0.40f)' not in runner_src
        and '"blender_export"' in builder_src
    )
    max_prio_ok = (
        score_info := (
            lambda raw_name, parent_name: __import__("physbone_helper").score_physbone_chain_priority(raw_name, parent_name)["priority"]
        )
    ) and (
        score_info("Dog_Ear.L", "SKEL_Head") == 100
        and score_info("Hair_Main", "SKEL_Head") >= 95
        and score_info("Ahoge", "SKEL_Head") >= 95
        and score_info("Breast.L", "SKEL_Spine2") > score_info("Skirt_F", "SKEL_Pelvis")
        and score_info("Skirt_F", "SKEL_Pelvis") > score_info("Coat_Hem", "SKEL_Pelvis")
        and score_info("Coat_Hem", "SKEL_Pelvis") > score_info("Ribbon", "SKEL_Head")
    )
    return math_ok and monotonic_ok and slots_labeled_ok and csharp_runner_ok and max_prio_ok


def test_restore_and_multislot_regressions() -> bool:
    """Run all regression checks for scoped MA/Atlas, PhysBones isolation, Restore, and Multi-Slot."""
    print("[Restore/MultiSlot] Validating PRUNING, SCOPED ATLAS, PHYSBONES, RESTORE, MULTI-SLOT...")
    pruning_ok, atlas_ok = _test_ma_fbx_pruning_and_scoped_atlas()
    pb_ok = _test_physbones_collision_and_ini_cleanup()
    restore_multi_ok = _test_restore_and_multislot_pipeline()
    unity_trs_ok = _test_unity_transform_and_earring_alignment()
    mat_ovr_ok = _test_mat_overrides_and_non_colliding_atlas()
    single_tex_pb_ok = _test_single_tex_ytd_and_physbone_unwrap()
    seam_dds_dec_ok = _test_seam_dds_and_torso_decimate()
    vtoon_budget_ok = _test_vtoon_hash_sync_and_budget_tiers()
    progress_ok = _test_multislot_proportional_progress()
    extractor_src = (PROJECT_ROOT_DIR / "scripts" / "common_tools" / "physbone_scene_extractor_layer.py").read_text(encoding="utf-8")
    builder_src2 = (PROJECT_ROOT_DIR / "scripts" / "common_tools" / "universal_gtav_builder.py").read_text(encoding="utf-8")
    progress_ok = progress_ok and ("active_meshes_by_fbx" in extractor_src) and ("unweighted/loose chain(s)" in builder_src2)

    editor_dir = PROJECT_ROOT_DIR / "unity_plugin" / "Assets" / "VRCAvatar2GTAV" / "Editor"
    csharp_files = sorted(editor_dir.glob("*.cs")) if editor_dir.is_dir() else []
    csharp_ok = (not csharp_files) or (
        len(csharp_files) == 9
        and all(len(csharp_path.read_text(encoding="utf-8").splitlines()) <= 500 for csharp_path in csharp_files)
    )

    all_ok = pruning_ok and atlas_ok and pb_ok and restore_multi_ok and unity_trs_ok and mat_ovr_ok and single_tex_pb_ok and seam_dds_dec_ok and vtoon_budget_ok and progress_ok and csharp_ok
    return print_status_result(
        "Restore-Vanilla & Per-Protagonist Multi-Slot Regression Suite",
        all_ok,
        f"pruning={pruning_ok}, atlas={atlas_ok}, physbones={pb_ok}, restore_multi={restore_multi_ok}, unity_trs={unity_trs_ok}, mat_ovr={mat_ovr_ok}, single_tex_pb={single_tex_pb_ok}, seam_dds_dec={seam_dds_dec_ok}, vtoon_budget={vtoon_budget_ok}, progress={progress_ok}, csharp={csharp_ok}",
    )
