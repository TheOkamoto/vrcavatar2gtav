#!/usr/bin/env python3
"""
restore_vanilla_helper.py
=========================
Incremental restore-to-vanilla and multi-slot batch build helpers for
`universal_gtav_builder.py` and the Unity `VRCAvatar2GTAV` Exporter.

Ensures:
1. Restoring a protagonist or NPC extracts ONLY that ped's vanilla files
   from Rockstar vanilla RPFs into the existing `mods/`-seeded staging dirs,
   preserving all other modded peds and NPCs intact.
2. Cleaning `GTAVPhysBones.ini`, `GTAVVToon.ini`, and `configs/npc_registry.json`
   removes ONLY the restored ped(s).
3. Multi-slot builds run sequentially (`--no-repack` per slot) and repack/deploy
   shared archives (`x64v.rpf`, `mppatchesng`, `patchday3ng`, `patchday4ng`) once.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

_COMMON_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _COMMON_DIR.parent
for _cand_dir in (str(_COMMON_DIR), str(_SCRIPTS_DIR)):
    if _cand_dir not in sys.path:
        sys.path.insert(0, _cand_dir)

PROTAGONIST_PEDS: tuple[str, ...] = ("player_zero", "player_one", "player_two")
PROTAGONIST_VTOON_IDS: Dict[str, int] = {
    "player_zero": 1,
    "player_one": 2,
    "player_two": 3,
}


def _collect_ini_sync_targets(gtav_root: Optional[Path], project_root: Path, ped_pkg_dir: Optional[Path] = None) -> tuple[List[Path], List[Path]]:
    """Collect `GTAVPhysBones.ini` and `GTAVVToon.ini` paths under GTA V root and staging packages."""
    pb_inis: List[Path] = []
    vtoon_inis: List[Path] = []
    candidate_dirs: List[Path] = []
    if gtav_root is not None:
        candidate_dirs.append(Path(gtav_root))
    if ped_pkg_dir is not None:
        candidate_dirs.append(Path(ped_pkg_dir))
    for folder_name in (
        "2_Michael_Shinano_EternalReunion",
        "1_Franklin_Shinano_Casual",
        "3_Trevor_Miltina_Maid",
    ):
        candidate_dirs.append(project_root / folder_name / "5_rpf_package")

    seen_dirs: set[str] = set()
    for base_dir in candidate_dirs:
        key_str = str(base_dir).lower()
        if key_str in seen_dirs:
            continue
        seen_dirs.add(key_str)
        pb_file = base_dir / "GTAVPhysBones.ini"
        vt_file = base_dir / "GTAVVToon.ini"
        if pb_file.is_file():
            pb_inis.append(pb_file)
        if vt_file.is_file():
            vtoon_inis.append(vt_file)
    return pb_inis, vtoon_inis


def _extract_optional_patterns(
    archive_path: Path,
    target_dir: Path,
    patterns: Sequence[str],
    *,
    gtav_root: Optional[Path],
    staging_dir: Path,
) -> bool:
    """Run `rage extract` for optional patterns; return True if any files materialized."""
    import npc_registry_helper

    target_dir.mkdir(parents=True, exist_ok=True)
    cmd = npc_registry_helper.build_safe_rage_cmd(
        "extract",
        str(archive_path),
        *list(patterns),
        "-o",
        str(target_dir),
        gtav_root=gtav_root,
        staging_dir=staging_dir,
    )
    subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False)
    return any(target_dir.rglob("*"))


def _copy_restored_ped_tree(
    src_root: Path,
    dst_root: Path,
    ped_token: str,
    *,
    is_streamed: bool,
) -> int:
    """Replace only `ped_token` files/subdirectory in `dst_root` from vanilla `src_root`."""
    copied_count = 0
    if is_streamed:
        dst_subdir = dst_root / ped_token
        if dst_subdir.is_dir():
            shutil.rmtree(dst_subdir, ignore_errors=True)
        src_subdir = src_root / ped_token
        if src_subdir.is_dir():
            shutil.copytree(src_subdir, dst_subdir, dirs_exist_ok=True)
            copied_count += sum(1 for item in src_subdir.rglob("*") if item.is_file())
        for ext_name in (".yft", ".ymt", ".yld"):
            dst_file = dst_root / f"{ped_token}{ext_name}"
            src_file = src_root / f"{ped_token}{ext_name}"
            if src_file.is_file():
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied_count += 1
            elif dst_file.is_file():
                dst_file.unlink()
    else:
        for ext_name in (".yft", ".ymt", ".ydd", ".ytd", ".yld"):
            dst_file = dst_root / f"{ped_token}{ext_name}"
            src_file = src_root / f"{ped_token}{ext_name}"
            if src_file.is_file():
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied_count += 1
            elif ext_name == ".yld" and dst_file.is_file():
                dst_file.unlink()
    return copied_count


def restore_single_ped_in_staging(
    ped_name: str,
    location: Dict[str, Any],
    info: Dict[str, Any],
    *,
    gtav_root: Optional[Path],
    staging_dir: Path,
) -> Dict[str, Any]:
    """Extract only `ped_name` from vanilla RPFs into the active staging directories."""
    import npc_registry_helper

    norm_ped = npc_registry_helper.normalize_ped_model_name(ped_name)
    is_streamed = str(location.get("ped_format", "")) == "streamed"
    vanilla_outer = Path(info["vanilla_outer_rpf"])
    inner_rpf_rel = Path(str(info["inner_rpf_rel"]))
    inner_dir = Path(info["inner_extracted_dir"])
    tmp_root = staging_dir / f"_tmp_restore_{norm_ped}"
    shutil.rmtree(tmp_root, ignore_errors=True)
    files_restored = 0

    try:
        outer_tmp = tmp_root / "outer"
        npc_registry_helper._extract_archive(
            vanilla_outer,
            outer_tmp,
            gtav_root=gtav_root,
            staging_dir=staging_dir,
            patterns=[inner_rpf_rel.as_posix()],
        )
        van_inner_rpf = outer_tmp / inner_rpf_rel
        if van_inner_rpf.is_file():
            ped_tmp = tmp_root / "inner"
            _extract_optional_patterns(
                van_inner_rpf,
                ped_tmp,
                [f"{norm_ped}.*", f"{norm_ped}/*"],
                gtav_root=gtav_root,
                staging_dir=staging_dir,
            )
            files_restored += _copy_restored_ped_tree(
                ped_tmp, inner_dir, norm_ped, is_streamed=is_streamed
            )

        prop_targets = location.get("prop_targets") or ()
        if prop_targets:
            import vrc2gtav_paths as project_paths

            rpf_paths_cfg = project_paths.get_rpf_paths()
            props_rel = Path(rpf_paths_cfg["streamedpedprops_rpf_relative"])
            props_dest_dir = Path(rpf_paths_cfg["streamedpedprops_extracted"])
            if not props_dest_dir.is_dir() or not any(props_dest_dir.iterdir()):
                try:
                    props_dest_dir = project_paths.ensure_streamedpedprops_extracted()
                except Exception:
                    pass
            props_outer_tmp = tmp_root / "props_outer"
            _extract_optional_patterns(
                vanilla_outer,
                props_outer_tmp,
                [props_rel.as_posix()],
                gtav_root=gtav_root,
                staging_dir=staging_dir,
            )
            van_props_rpf = props_outer_tmp / props_rel
            if van_props_rpf.is_file() and props_dest_dir.is_dir():
                props_ped_tmp = tmp_root / "props_inner"
                _extract_optional_patterns(
                    van_props_rpf,
                    props_ped_tmp,
                    [f"{norm_ped}_p.*", f"{norm_ped}_p/*"],
                    gtav_root=gtav_root,
                    staging_dir=staging_dir,
                )
                files_restored += _copy_restored_ped_tree(
                    props_ped_tmp, props_dest_dir, f"{norm_ped}_p", is_streamed=True
                )

        for ovr_spec in info.get("dlc_override_specs") or ():
            dlc_name = str(ovr_spec["dlc_name"])
            van_dlc = Path(ovr_spec["vanilla_dlc_rpf"])
            ovr_rel = Path(str(ovr_spec["inner_rpf_rel"]))
            models_dir = Path(ovr_spec["models_extracted_dir"])
            if not van_dlc.is_file():
                continue
            dlc_outer_tmp = tmp_root / f"dlc_{dlc_name}"
            _extract_optional_patterns(
                van_dlc,
                dlc_outer_tmp,
                [ovr_rel.as_posix()],
                gtav_root=gtav_root,
                staging_dir=staging_dir,
            )
            van_dlc_inner = dlc_outer_tmp / ovr_rel
            if van_dlc_inner.is_file() and models_dir.is_dir():
                dlc_ped_tmp = tmp_root / f"dlc_inner_{dlc_name}"
                _extract_optional_patterns(
                    van_dlc_inner,
                    dlc_ped_tmp,
                    [f"{norm_ped}.*", f"{norm_ped}/*"],
                    gtav_root=gtav_root,
                    staging_dir=staging_dir,
                )
                files_restored += _copy_restored_ped_tree(
                    dlc_ped_tmp, models_dir, norm_ped, is_streamed=is_streamed
                )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return {"ped_name": norm_ped, "files_restored": files_restored}


def repack_and_deploy_built_peds(
    ped_names: Sequence[str],
    *,
    secondary_atlas_size: int = 0,
    registry_entries: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Path]:
    """Repack and deploy all RPF archives modified by `ped_names` in one shared pass."""
    import npc_registry_helper
    import repack_and_deploy_everything as repack_helper
    import vrc2gtav_paths as project_paths

    unique_peds: List[str] = []
    for raw_ped in ped_names:
        norm_ped = npc_registry_helper.normalize_ped_model_name(raw_ped)
        if norm_ped and norm_ped not in unique_peds:
            unique_peds.append(norm_ped)
    if not unique_peds:
        return []

    reg_data = npc_registry_helper.load_npc_registry(project_paths.get_project_root())
    reg_npcs = dict(reg_data.get("npcs", {}))
    if registry_entries:
        for key_ped, val_entry in registry_entries.items():
            reg_npcs.setdefault(key_ped, val_entry)

    last_ped = unique_peds[-1]
    deployed_list = npc_registry_helper.repack_and_deploy_npc_entry(
        last_ped,
        reg_npcs[last_ped],
        skip_shared_archives=False,
        secondary_atlas_size=secondary_atlas_size,
    )
    deployed_set = {str(pth.resolve()) for pth in deployed_list}
    rage_cli = project_paths.get_rage_cli()

    for earlier_ped in unique_peds[:-1]:
        entry_earlier = reg_npcs[earlier_ped]
        info_earlier = npc_registry_helper.get_npc_staging_paths(
            earlier_ped, entry_earlier["location"]
        )
        outer_game = Path(info_earlier["outer_game_rpf"])
        if str(outer_game.resolve()) not in deployed_set:
            repack_helper.repack_single_rpf_stage(
                Path(info_earlier["inner_rpf_file"]),
                Path(info_earlier["inner_extracted_dir"]),
                f"NPC inner {Path(info_earlier['inner_rpf_file']).name}",
                rage_cli,
            )
            repack_helper.repack_single_rpf_stage(
                Path(info_earlier["outer_modded_rpf"]),
                Path(info_earlier["outer_extracted_dir"]),
                f"NPC outer {Path(info_earlier['outer_modded_rpf']).name}",
                rage_cli,
            )
            repack_helper.copy_file_with_progress(
                Path(info_earlier["outer_modded_rpf"]),
                outer_game,
                f"Deploy {outer_game.name}",
            )
            deployed_list.append(outer_game)
            deployed_set.add(str(outer_game.resolve()))

        for ovr_spec in info_earlier.get("dlc_override_specs") or ():
            dlc_game = Path(ovr_spec["game_dlc_rpf"])
            if str(dlc_game.resolve()) in deployed_set:
                continue
            dlc_name = str(ovr_spec["dlc_name"])
            repack_helper.repack_single_rpf_stage(
                Path(ovr_spec["inner_rpf_file"]),
                Path(ovr_spec["models_extracted_dir"]),
                f"DLC inner {dlc_name}/{Path(ovr_spec['inner_rpf_file']).name}",
                rage_cli,
            )
            repack_helper.repack_single_rpf_stage(
                Path(ovr_spec["modded_dlc_rpf"]),
                Path(ovr_spec["dlc_extracted_dir"]),
                f"DLC outer {dlc_name}/dlc.rpf",
                rage_cli,
            )
            repack_helper.copy_file_with_progress(
                Path(ovr_spec["modded_dlc_rpf"]), dlc_game, f"Deploy {dlc_name}/dlc.rpf"
            )
            deployed_list.append(dlc_game)
            deployed_set.add(str(dlc_game.resolve()))

    return deployed_list


def restore_peds_to_vanilla(
    ped_targets: Sequence[str] = (),
    *,
    restore_all: bool = False,
    deploy: bool = True,
    gtav_root: Optional[Path] = None,
    staging_dir: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Restore ONLY the selected ped(s) (or all modded peds) to Rockstar vanilla cleanly."""
    import npc_registry_helper
    import physbone_cfg_ini_layer
    import vrc2gtav_paths as project_paths
    import vtoon_profile_helper

    resolved_project = Path(project_root) if project_root else project_paths.get_project_root()
    resolved_staging = Path(staging_dir) if staging_dir else project_paths.get_staging_dir()
    resolved_gtav = Path(gtav_root) if gtav_root else project_paths.get_gtav_root_dir()

    reg_data = npc_registry_helper.load_npc_registry(resolved_project)
    reg_npcs = dict(reg_data.get("npcs", {}))

    requested: List[str] = []
    if restore_all:
        for base_ped in (*PROTAGONIST_PEDS, *sorted(reg_npcs.keys())):
            norm_ped = npc_registry_helper.normalize_ped_model_name(base_ped)
            if norm_ped and norm_ped not in requested:
                requested.append(norm_ped)
    else:
        for raw_ped in ped_targets:
            norm_ped = npc_registry_helper.normalize_ped_model_name(raw_ped)
            if norm_ped and norm_ped not in requested:
                requested.append(norm_ped)

    if not requested:
        raise ValueError("No ped model specified for vanilla restore")

    restored_details: List[Dict[str, Any]] = []
    temp_deploy_entries: Dict[str, Dict[str, Any]] = {}
    for norm_ped in requested:
        existing_entry = reg_npcs.get(norm_ped) or {}
        location = existing_entry.get("location") or npc_registry_helper.discover_npc_location(norm_ped)
        info = npc_registry_helper.get_npc_staging_paths(
            norm_ped, location, staging_dir=resolved_staging, project_root=resolved_project
        )
        npc_registry_helper.ensure_npc_staging_extracted(norm_ped, location)

        print(f"[Restore Vanilla] Restoring '{norm_ped}' from Rockstar vanilla RPFs...", flush=True)
        res_info = restore_single_ped_in_staging(
            norm_ped,
            location,
            info,
            gtav_root=resolved_gtav,
            staging_dir=resolved_staging,
        )
        temp_deploy_entries[norm_ped] = {"location": location}

        pb_inis, vtoon_inis = _collect_ini_sync_targets(
            resolved_gtav, resolved_project, Path(info["package_dir"])
        )
        if pb_inis:
            physbone_cfg_ini_layer.remove_ped_from_physbone_ini(
                pb_inis[0], norm_ped, extra_sync_paths=pb_inis[1:]
            )
        cand_vtoon_ids: List[int] = []
        if norm_ped in PROTAGONIST_VTOON_IDS:
            cand_vtoon_ids.append(PROTAGONIST_VTOON_IDS[norm_ped])
        if existing_entry.get("vtoon_char_id") is not None:
            cand_vtoon_ids.append(int(existing_entry["vtoon_char_id"]))
        vtoon_profile_helper.remove_vtoon_ini_character(
            vtoon_inis,
            char_ids=tuple(cand_vtoon_ids),
            char_names=(norm_ped,),
        )

        reg_npcs.pop(norm_ped, None)
        res_info["registry_removed"] = True
        restored_details.append(res_info)

    reg_data["npcs"] = reg_npcs
    npc_registry_helper.save_npc_registry(reg_data, resolved_project)

    deployed_rpfs: List[Path] = []
    if deploy and requested:
        deployed_rpfs = repack_and_deploy_built_peds(
            requested, registry_entries=temp_deploy_entries
        )

    print(
        f"[Restore Vanilla] Completed cleanly for: {', '.join(requested)}",
        flush=True,
    )
    return {
        "restored_peds": requested,
        "details": restored_details,
        "deployed_rpfs": [str(pth) for pth in deployed_rpfs],
    }


def _load_slots_payload(slots_spec: Any) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Normalize `--slots-json` path or in-memory slots list into `(slots, shared_defaults)`."""
    if isinstance(slots_spec, (str, Path)):
        payload = json.loads(Path(slots_spec).read_text(encoding="utf-8"))
    else:
        payload = slots_spec
    if isinstance(payload, dict):
        raw_slots = payload.get("slots") or []
        defaults = dict(payload.get("defaults") or {})
        return [dict(item) for item in raw_slots if isinstance(item, dict)], defaults
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)], {}
    raise ValueError("Invalid slots specification: expected JSON array or {slots: [...]}")


def run_multi_slot_builds(
    slots_spec: Any,
    *,
    shared_defaults: Optional[Dict[str, Any]] = None,
    build_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    deploy: bool = True,
    repack_and_deploy: bool = True,
    secondary_atlas_size: int = 0,
) -> List[Dict[str, Any]]:
    """Build multiple `(target_ped -> source/avatar_name)` slots sequentially with one shared repack."""
    import universal_gtav_builder

    parsed_slots, file_defaults = _load_slots_payload(slots_spec)
    if not parsed_slots:
        raise ValueError("Multi-slot specification contained zero avatar slots")

    merged_defaults: Dict[str, Any] = dict(file_defaults)
    if shared_defaults:
        for default_key, default_val in shared_defaults.items():
            if default_val is None:
                continue
            if default_key == "source" and not str(default_val).strip():
                continue
            merged_defaults[default_key] = default_val

    executor = build_fn or universal_gtav_builder.build_and_deploy_npc_from_source
    results: List[Dict[str, Any]] = []
    built_peds: List[str] = []

    for slot_idx, slot_item in enumerate(parsed_slots):
        target_ped = str(slot_item.get("target_ped") or "").strip()
        source_val = str(slot_item.get("source") or merged_defaults.get("source") or "").strip()
        if not target_ped or not source_val:
            raise ValueError(f"Slot #{slot_idx + 1} missing required target_ped or source")
        kwargs = {
            "source_spec": source_val,
            "target_ped": target_ped,
            "avatar_name": str(slot_item.get("avatar_name") or ""),
            "deploy": bool(deploy),
            "repack_archives": False,
            "force_reextract": bool(
                slot_item.get("force_reextract", False)
                or (merged_defaults.get("force_reextract", False) and slot_idx == 0)
            ),
            "blood_decals": bool(slot_item.get("blood_decals", merged_defaults.get("blood_decals", True))),
            "eye_blink": slot_item.get("eye_blink", merged_defaults.get("eye_blink")),
            "eye_blink_strength": slot_item.get("eye_blink_strength", merged_defaults.get("eye_blink_strength")),
            "mouth_open_strength": slot_item.get("mouth_open_strength", merged_defaults.get("mouth_open_strength")),
            "physbones_marshmallow": slot_item.get("physbones_marshmallow", merged_defaults.get("physbones_marshmallow")),
            "import_face_blendshapes": slot_item.get("import_face_blendshapes", merged_defaults.get("import_face_blendshapes")),
            "import_body_blendshapes": slot_item.get("import_body_blendshapes", merged_defaults.get("import_body_blendshapes")),
            "blendshapes_source": slot_item.get("blendshapes_source", merged_defaults.get("blendshapes_source")),
            "physbones_source": slot_item.get("physbones_source", merged_defaults.get("physbones_source")),
            "blendshapes_cfg": slot_item.get("blendshapes_cfg", merged_defaults.get("blendshapes_cfg")),
            "face_anim": slot_item.get("face_anim", merged_defaults.get("face_anim")),
            "physbones_cfg": slot_item.get("physbones_cfg", merged_defaults.get("physbones_cfg")),
            "vtoon_char_id": slot_item.get("vtoon_char_id"),
            "atlas_size": int(slot_item.get("atlas_size", merged_defaults.get("atlas_size", 2048))),
            "normal_size": int(slot_item.get("normal_size", merged_defaults.get("normal_size", 0))),
            "secondary_atlas_size": int(
                slot_item.get(
                    "secondary_atlas_size",
                    merged_defaults.get("secondary_atlas_size", secondary_atlas_size),
                )
            ),
            "texture_overrides": slot_item.get("texture_overrides", merged_defaults.get("texture_overrides")),
        }
        res_manifest = executor(**kwargs)
        results.append(res_manifest)
        built_peds.append(str(res_manifest.get("ped_name") or target_ped))
        print(
            f"[DONE] Slot {slot_idx + 1}/{len(parsed_slots)}: "
            f"{res_manifest.get('ped_name', target_ped)} -> {res_manifest.get('avatar_name', '')}",
            flush=True,
        )

    if deploy and repack_and_deploy and built_peds:
        explicit_sec_default = (shared_defaults or {}).get("secondary_atlas_size")
        if explicit_sec_default is not None:
            resolved_repack_sec = int(explicit_sec_default)
        elif int(secondary_atlas_size or 0) > 0:
            resolved_repack_sec = int(secondary_atlas_size)
        elif merged_defaults.get("secondary_atlas_size") is not None:
            resolved_repack_sec = int(merged_defaults["secondary_atlas_size"])
        else:
            slot_sec_sizes = [
                int(slot_item["secondary_atlas_size"])
                for slot_item in parsed_slots
                if slot_item.get("secondary_atlas_size") is not None
            ]
            resolved_repack_sec = max(slot_sec_sizes) if slot_sec_sizes else 0
        repack_and_deploy_built_peds(
            built_peds,
            secondary_atlas_size=resolved_repack_sec,
        )

    return results
