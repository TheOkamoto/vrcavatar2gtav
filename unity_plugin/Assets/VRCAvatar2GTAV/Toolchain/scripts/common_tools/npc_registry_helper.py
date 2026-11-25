#!/usr/bin/env python3
"""
npc_registry_helper.py
======================
Universal GTA V NPC discovery, RPF staging, slot replacement (supporting both
`streamed` NPCs like `ig_lamardavis` / `cs_lamardavis` and packed
`componentpeds` street pedestrians like `a_f_y_beach_01`), and DLC/base RPF
repack deployment for vrc2gtav.
"""

from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

try:
    import error_handler_helper as err_helper
    import ped_damage_helper
    import repack_and_deploy_everything as repack_helper
    import vrc2gtav_i18n as project_i18n
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import error_handler_helper as err_helper
    from common_tools import ped_damage_helper
    from common_tools import repack_and_deploy_everything as repack_helper
    from common_tools import vrc2gtav_i18n as project_i18n
    from common_tools import vrc2gtav_paths as project_paths


NPC_REGISTRY_REL_PATH = Path("configs") / "npc_registry.json"

BASE_PED_OUTER_RPFS: Tuple[str, ...] = (
    "x64e.rpf",
    "x64v.rpf",
    "x64g.rpf",
    "x64b.rpf",
)

PROPS_INNER_ARCHIVE_CANDIDATES: Tuple[Tuple[str, str], ...] = (
    ("x64v.rpf", "models/cdimages/streamedpedprops.rpf"),
    ("x64e.rpf", "models/cdimages/pedprops.rpf"),
    ("x64g.rpf", "levels/gta5/generic/ped_props.rpf"),
)

STREAMED_COMPONENT_PREFIXES: Tuple[str, ...] = (
    "head",
    "berd",
    "hair",
    "uppr",
    "lowr",
    "hand",
    "feet",
    "teef",
    "accs",
    "task",
    "decl",
    "jbib",
)

PRIMARY_COMPONENT_PRIORITY: Tuple[str, ...] = ("uppr", "head", "jbib", "lowr", "accs")


def _rage_keys_dir(staging_dir: Path) -> Optional[Path]:
    """Return pre-extracted RAGE keys folder if available to avoid reading GTA5.exe."""
    keys_candidate = staging_dir / "rage_keys"
    if keys_candidate.is_dir() and any(keys_candidate.iterdir()):
        return keys_candidate
    return None


def ensure_rage_cli_ready(*, download_if_missing: bool = True) -> str:
    """Resolve `rage` / `rage.exe`, auto-downloading into `<workspace_root>/tools` if missing."""
    rage_cmd = project_paths.get_rage_cli().strip()
    if rage_cmd:
        if rage_cmd.startswith("wsl "):
            return rage_cmd
        if shutil.which(rage_cmd) or Path(rage_cmd).is_file():
            return rage_cmd

    proj_root = project_paths.get_project_root()
    exe_name = "rage.exe" if os.name == "nt" else "rage"
    work_tools_exe = err_helper.resolve_workspace_root(proj_root) / "tools" / exe_name
    if work_tools_exe.is_file():
        return str(work_tools_exe)

    if download_if_missing:
        try:
            import avatar_archive_helper

            downloaded_exe = avatar_archive_helper.download_and_install_rage(proj_root)
            if downloaded_exe.is_file():
                try:
                    import setup_first_run

                    cfg_file = project_paths.find_project_config_file()
                    setup_first_run.update_cfg_values_in_place(
                        cfg_file,
                        {"executables": {"rage": str(downloaded_exe).replace("\\", "/")}},
                    )
                    project_paths.load_project_config(force_reload=True)
                except Exception:
                    pass
                return str(downloaded_exe)
        except Exception as download_exc:
            raise FileNotFoundError(
                f"RAGE CLI ({exe_name}) missing and auto-download failed: {download_exc}"
            ) from download_exc

    raise FileNotFoundError(
        f"RAGE CLI ({exe_name}) not found. Click 'Download Required Tools & Setup' in Unity."
    )


def build_safe_rage_cmd(*rage_args: str, gtav_root: Optional[Path] = None, staging_dir: Optional[Path] = None) -> List[str]:
    """
    Build a RAGE CLI invocation preferring pre-extracted `--keys` so running
    GTA V executables are never touched during active sessions.
    """
    rage_executable = ensure_rage_cli_ready(download_if_missing=True)
    resolved_staging = staging_dir or project_paths.get_staging_dir()
    keys_dir = _rage_keys_dir(resolved_staging)
    global_flags: List[str] = []
    if keys_dir is not None:
        global_flags = ["--keys", str(keys_dir)]
    else:
        resolved_gtav = gtav_root or project_paths.get_gtav_root_dir()
        if (resolved_gtav / "GTA5.exe").is_file():
            global_flags = ["--exe", str(resolved_gtav)]
    if rage_executable.startswith("wsl "):
        wsl_binary = rage_executable[4:].strip()
        return ["wsl", wsl_binary, *global_flags, *rage_args]
    return [rage_executable, *global_flags, *rage_args]


def normalize_ped_model_name(raw_ped_name: str) -> str:
    """Normalize a GTA V ped model name (e.g. 'IG_LamarDavis' -> 'ig_lamardavis')."""
    cleaned = str(raw_ped_name or "").strip().lower()
    if cleaned.endswith((".yft", ".ydd", ".ymt", ".ytd")):
        cleaned = cleaned.rsplit(".", 1)[0]
    return cleaned


def _parse_rage_search_hits(stdout_text: str) -> List[str]:
    """Extract normalized archive hit paths printed by `rage search`."""
    hits: List[str] = []
    for raw_line in (stdout_text or "").splitlines():
        line_str = raw_line.strip()
        if not line_str or line_str.startswith(("ERR:", "No files")):
            continue
        hits.append(line_str.replace("\\", "/"))
    return hits


def _split_archive_hit(hit_line: str) -> Tuple[str, str, str]:
    """
    Split a `rage search` line such as:
      `/mnt/d/GTAV/x64e.rpf:x64e.rpf/models/cdimages/streamedpeds_ig.rpf/ig_lamardavis.yft`
      `D:\\GTAV\\x64v.rpf:x64v.rpf/models/cdimages/streamedpeds_players.rpf/player_zero/player_zero.yft`
    into `(outer_archive_path, inner_rpf_rel, member_rel)`.
    """
    normalized = str(hit_line or "").replace("\\", "/")
    colon_start = (
        2 if len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha() else 0
    )
    colon_idx = normalized.find(":", colon_start)
    if colon_idx < 0:
        return normalized, "", ""
    outer_path = normalized[:colon_idx]
    internal_tail = normalized[colon_idx + 1 :]
    parts = [seg for seg in internal_tail.split("/") if seg]
    if parts and parts[0].lower().endswith(".rpf"):
        parts = parts[1:]
    rpf_idx = -1
    for seg_idx, seg_val in enumerate(parts):
        if seg_val.lower().endswith(".rpf"):
            rpf_idx = seg_idx
            break
    if rpf_idx >= 0:
        inner_rel = "/".join(parts[: rpf_idx + 1])
        member_rel = "/".join(parts[rpf_idx + 1 :])
        return outer_path, inner_rel, member_rel
    return outer_path, "", "/".join(parts)


def discover_npc_location(
    raw_ped_name: str,
    *,
    gtav_root: Optional[Path] = None,
    staging_dir: Optional[Path] = None,
    scan_dlcs: bool = True,
) -> Dict[str, Any]:
    """
    Discover where a GTA V NPC lives across base archives (`x64e.rpf`,
    `x64v.rpf`, `x64g.rpf`, `x64b.rpf`) and DLC packs (`patchday*`, etc.).

    Returns a descriptor dict containing `ped_format` (`streamed` vs `componentpeds`),
    outer/inner RPF paths, DLC override targets, prop locations, and primary slot.
    """
    ped_name = normalize_ped_model_name(raw_ped_name)
    if not ped_name:
        raise ValueError("Ped model name must not be empty.")

    resolved_gtav = gtav_root or project_paths.get_gtav_root_dir()
    resolved_staging = staging_dir or project_paths.get_staging_dir()

    candidate_archives: List[Tuple[str, Path]] = []
    for base_name in BASE_PED_OUTER_RPFS:
        base_rpf = resolved_gtav / base_name
        if base_rpf.is_file():
            candidate_archives.append(("base", base_rpf))

    if scan_dlcs:
        dlc_root = resolved_gtav / "update" / "x64" / "dlcpacks"
        if dlc_root.is_dir():
            patchday_dirs = sorted(
                dlc_dir for dlc_dir in dlc_root.iterdir()
                if dlc_dir.is_dir() and (dlc_dir / "dlc.rpf").is_file()
            )
            for dlc_dir in patchday_dirs:
                candidate_archives.append((f"dlc:{dlc_dir.name}", dlc_dir / "dlc.rpf"))

    base_hits_by_inner: Dict[Tuple[str, str], List[str]] = {}
    dlc_hits_by_pack: Dict[Tuple[str, str, str], List[str]] = {}
    prop_locations: List[Dict[str, str]] = []

    search_pattern = f"*{ped_name}*"
    for source_tag, archive_path in candidate_archives:
        cmd = build_safe_rage_cmd(
            "search",
            str(archive_path),
            search_pattern,
            gtav_root=resolved_gtav,
            staging_dir=resolved_staging,
        )
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120.0,
            check=False,
        )
        for hit_line in _parse_rage_search_hits(proc.stdout):
            outer_path, inner_rel, member_rel = _split_archive_hit(hit_line)
            low_member = member_rel.lower()
            low_inner = inner_rel.lower()
            if not inner_rel:
                continue
            # Filter out animations, audio, expressions, and prop folders when matching body archives
            if not (
                low_member.endswith((".yft", ".ymt", ".ydd", ".ytd", ".yld"))
            ):
                continue
            if any(
                seg in low_inner
                for seg in ("/anim/", "/audio/", "/sfx/", "expressions", "cuts_")
            ):
                continue
            if f"/{ped_name}_p/" in f"/{low_member}" or low_member.startswith(f"{ped_name}_p/") or f"/{ped_name}_p." in f"/{low_member}" or "pedprops" in low_inner:
                prop_locations.append(
                    {
                        "source": source_tag,
                        "outer_rpf": outer_path,
                        "inner_rpf_rel": inner_rel,
                        "member_rel": member_rel,
                    }
                )
                continue
            if not (
                low_member.startswith(f"{ped_name}/")
                or low_member.startswith(f"{ped_name}.")
            ):
                continue
            if source_tag == "base":
                base_hits_by_inner.setdefault((outer_path, inner_rel), []).append(member_rel)
            else:
                dlc_name = source_tag.split(":", 1)[1]
                dlc_hits_by_pack.setdefault((dlc_name, outer_path, inner_rel), []).append(member_rel)

    if not base_hits_by_inner and not dlc_hits_by_pack:
        raise FileNotFoundError(
            f"NPC ped '{ped_name}' not found in GTA V archives under {resolved_gtav}."
        )

    # Choose primary ped archive: prefer streamedpeds_ig/strm/players, then componentpeds, then cutspeds, then DLC
    def _rank_archive_candidate(item: Tuple[Tuple[str, str], List[str]]) -> Tuple[int, int, str]:
        (_outer_path, inner_rel_str), members_list = item
        low_inner = inner_rel_str.lower()
        has_yft = any(mem.lower() == f"{ped_name}.yft" for mem in members_list)
        if "cutspeds" in low_inner:
            type_rank = 2
        elif "streamedpeds" in low_inner:
            type_rank = 0
        elif "componentpeds" in low_inner:
            type_rank = 1
        else:
            type_rank = 3
        return (0 if has_yft else 1, type_rank, low_inner)

    primary_members: List[str] = []
    if base_hits_by_inner:
        sorted_base = sorted(base_hits_by_inner.items(), key=_rank_archive_candidate)
        (primary_outer_rpf, primary_inner_rel), primary_members = sorted_base[0]
        primary_source = "base"
    else:
        sorted_dlc = sorted(
            dlc_hits_by_pack.items(),
            key=lambda keyval_item: (0 if any(mem.lower() == f"{ped_name}.yft" for mem in keyval_item[1]) else 1, keyval_item[0][0]),
        )
        (dlc_name, primary_outer_rpf, primary_inner_rel), primary_members = sorted_dlc[0]
        primary_source = f"dlc:{dlc_name}"

    is_streamed = any("/" in mem_item for mem_item in primary_members)
    if "componentpeds" in primary_inner_rel.lower():
        is_streamed = False
    elif "streamedpeds" in primary_inner_rel.lower() or "cutspeds" in primary_inner_rel.lower():
        is_streamed = True
    ped_format = "streamed" if is_streamed else "componentpeds"

    drawables_by_prefix: Dict[str, List[str]] = {}
    if ped_format == "streamed":
        for mem_item in primary_members:
            low_mem = mem_item.lower()
            if "/" in low_mem and low_mem.endswith(".ydd"):
                stem_name = Path(mem_item).stem.lower()
                comp_prefix = stem_name.split("_", 1)[0]
                drawables_by_prefix.setdefault(comp_prefix, []).append(Path(mem_item).stem)

    # Also collect DLC override slots (e.g. patchday3ng overriding ig_lamardavis/lowr_003_r.ydd)
    dlc_overrides: List[Dict[str, Any]] = []
    for (dlc_name, dlc_outer_path, dlc_inner_rel), dlc_members in sorted(dlc_hits_by_pack.items()):
        if primary_outer_rpf == dlc_outer_path and primary_inner_rel == dlc_inner_rel:
            continue
        dlc_drawables: List[str] = []
        for mem_item in dlc_members:
            if mem_item.lower().endswith(".ydd") and "/" in mem_item:
                stem_name = Path(mem_item).stem
                comp_prefix = stem_name.lower().split("_", 1)[0]
                dlc_drawables.append(stem_name)
                if ped_format == "streamed":
                    bucket = drawables_by_prefix.setdefault(comp_prefix, [])
                    if stem_name not in bucket:
                        bucket.append(stem_name)
        dlc_overrides.append(
            {
                "dlc_name": dlc_name,
                "outer_rpf": dlc_outer_path,
                "inner_rpf_rel": dlc_inner_rel,
                "members": sorted(set(dlc_members)),
                "drawables": sorted(set(dlc_drawables)),
            }
        )

    primary_component = "uppr"
    export_drawables: List[str] = []
    if ped_format == "streamed":
        for cand_comp in PRIMARY_COMPONENT_PRIORITY:
            if drawables_by_prefix.get(cand_comp):
                primary_component = cand_comp
                export_drawables = sorted(set(drawables_by_prefix[cand_comp]))
                break
        if not export_drawables and drawables_by_prefix:
            first_comp = sorted(drawables_by_prefix.keys())[0]
            primary_component = first_comp
            export_drawables = sorted(set(drawables_by_prefix[first_comp]))
        if not export_drawables:
            export_drawables = ["uppr_000_u"]

    props_by_inner: Dict[Tuple[str, str, str], List[str]] = {}
    for prop_hit in prop_locations:
        key = (prop_hit["source"], prop_hit["outer_rpf"], prop_hit["inner_rpf_rel"])
        props_by_inner.setdefault(key, []).append(prop_hit["member_rel"])

    prop_targets = [
        {
            "source": src_tag,
            "outer_rpf": prop_outer_rpf,
            "inner_rpf_rel": inner_path,
            "prop_folder": f"{ped_name}_p",
            "members": sorted(set(mems)),
        }
        for (src_tag, prop_outer_rpf, inner_path), mems in sorted(props_by_inner.items())
    ]

    return {
        "ped_name": ped_name,
        "ped_format": ped_format,
        "primary_source": primary_source,
        "outer_rpf": primary_outer_rpf,
        "outer_rpf_name": Path(primary_outer_rpf).name,
        "inner_rpf_rel": primary_inner_rel,
        "inner_rpf_name": Path(primary_inner_rel).name,
        "primary_component": primary_component,
        "export_drawables": export_drawables,
        "primary_members": sorted(set(primary_members)),
        "dlc_overrides": dlc_overrides,
        "prop_targets": prop_targets,
    }


def _registry_file_path(project_root: Optional[Path] = None) -> Path:
    """Return path to configs/npc_registry.json."""
    resolved_root = project_root or project_paths.get_project_root()
    return resolved_root / NPC_REGISTRY_REL_PATH


def load_npc_registry(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load persisted NPC avatar assignments from configs/npc_registry.json."""
    reg_path = _registry_file_path(project_root)
    if not reg_path.is_file():
        return {"npcs": {}}
    try:
        loaded = json.loads(reg_path.read_text(encoding="utf-8"))
    except Exception:
        return {"npcs": {}}
    if not isinstance(loaded, dict):
        return {"npcs": {}}
    npcs_map = loaded.get("npcs")
    if not isinstance(npcs_map, dict):
        return {"npcs": {}}
    return {"npcs": dict(npcs_map)}


def save_npc_registry(
    registry_data: Dict[str, Any],
    project_root: Optional[Path] = None,
) -> Path:
    """Persist NPC avatar assignments cleanly to configs/npc_registry.json."""
    reg_path = _registry_file_path(project_root)
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(
        json.dumps(registry_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return reg_path


def get_npc_staging_paths(
    ped_name: str,
    location: Dict[str, Any],
    *,
    staging_dir: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Resolve all host staging directories for an NPC's outer RPF, inner ped RPF,
    vanilla skeleton backup, and any DLC override archives.
    """
    norm_ped = normalize_ped_model_name(ped_name)
    resolved_staging = staging_dir or project_paths.get_staging_dir()
    resolved_root = project_root or project_paths.get_project_root()
    rpf_paths_cfg = project_paths.get_rpf_paths()

    outer_rpf_name = str(location.get("outer_rpf_name") or Path(str(location["outer_rpf"])).name)
    outer_stem = Path(outer_rpf_name).stem.lower()
    inner_rpf_rel = Path(str(location["inner_rpf_rel"]))
    inner_stem = inner_rpf_rel.stem.lower()

    npc_rpf_root = resolved_staging / "npcs_rpf"
    if outer_stem == "x64v":
        outer_extracted_dir = Path(rpf_paths_cfg["x64v_extracted"])
        outer_modded_rpf = Path(rpf_paths_cfg["x64v_modded_rpf"])
        outer_game_rpf = Path(rpf_paths_cfg["x64v_game_rpf"])
        if inner_stem == "streamedpeds_players":
            inner_extracted_dir = Path(rpf_paths_cfg["streamedpeds_extracted"])
        else:
            inner_extracted_dir = npc_rpf_root / f"{inner_stem}_extracted"
    else:
        outer_extracted_dir = npc_rpf_root / f"{outer_stem}_extracted"
        outer_modded_rpf = npc_rpf_root / f"{outer_stem}_modded.rpf"
        outer_game_rpf = project_paths.get_gtav_mods_dir() / outer_rpf_name
        inner_extracted_dir = npc_rpf_root / f"{inner_stem}_extracted"

    dlc_override_specs: List[Dict[str, Any]] = []
    for ovr_item in location.get("dlc_overrides") or ():
        dlc_name = str(ovr_item["dlc_name"]).strip()
        ovr_inner_rel = Path(str(ovr_item["inner_rpf_rel"]))
        if dlc_name in ("patchday3ng", "patchday4ng", "mppatchesng"):
            if dlc_name == "mppatchesng":
                dlc_extracted_dir = Path(rpf_paths_cfg["mppatches_dlc_extracted"])
                models_extracted_dir = Path(rpf_paths_cfg["mppatches_extracted"])
                modded_dlc_rpf = Path(rpf_paths_cfg["mppatches_modded_rpf"])
                game_dlc_rpf = Path(rpf_paths_cfg["mppatches_game_rpf"])
            else:
                patch_spec = repack_helper._build_patchday_spec(
                    rpf_paths_cfg, resolved_staging, resolved_root, dlc_name
                )
                dlc_extracted_dir = Path(patch_spec["dlc_extracted_dir"])
                models_extracted_dir = Path(patch_spec["models_dir"])
                modded_dlc_rpf = Path(patch_spec["dlc_rpf_file"])
                game_dlc_rpf = Path(patch_spec["target_dlc_path"])
        else:
            dlc_extracted_dir = npc_rpf_root / f"{dlc_name}_dlc_extracted"
            models_extracted_dir = npc_rpf_root / f"{dlc_name}_models_extracted"
            modded_dlc_rpf = npc_rpf_root / f"{dlc_name}_dlc.rpf"
            game_dlc_rpf = (
                project_paths.get_gtav_mods_dir()
                / "update"
                / "x64"
                / "dlcpacks"
                / dlc_name
                / "dlc.rpf"
            )
        dlc_override_specs.append(
            {
                "dlc_name": dlc_name,
                "vanilla_dlc_rpf": Path(str(ovr_item["outer_rpf"])),
                "inner_rpf_rel": ovr_inner_rel,
                "dlc_extracted_dir": dlc_extracted_dir,
                "inner_rpf_file": dlc_extracted_dir / ovr_inner_rel,
                "models_extracted_dir": models_extracted_dir,
                "modded_dlc_rpf": modded_dlc_rpf,
                "game_dlc_rpf": game_dlc_rpf,
                "members": list(ovr_item.get("members") or ()),
            }
        )

    char_work_dir = err_helper.resolve_workspace_root(resolved_root) / "npcs" / norm_ped
    return {
        "ped_name": norm_ped,
        "ped_format": location["ped_format"],
        "outer_rpf_name": outer_rpf_name,
        "vanilla_outer_rpf": Path(str(location["outer_rpf"])),
        "outer_extracted_dir": outer_extracted_dir,
        "inner_rpf_rel": inner_rpf_rel,
        "inner_rpf_file": outer_extracted_dir / inner_rpf_rel,
        "inner_extracted_dir": inner_extracted_dir,
        "outer_modded_rpf": outer_modded_rpf,
        "outer_game_rpf": outer_game_rpf,
        "dlc_override_specs": dlc_override_specs,
        "vanilla_skeleton_backup": Path(
            rpf_paths_cfg.get(
                "vanilla_skeletons_backup",
                resolved_staging / "backup_vanilla_skeletons",
            )
        )
        / f"{norm_ped}.yft",
        "npc_backup_dir": npc_rpf_root / "backup_vanilla" / norm_ped,
        "npc_work_dir": char_work_dir,
        "blender_dir": char_work_dir / "2_blender",
        "textures_dir": char_work_dir / "3_textures_gtav",
        "package_dir": char_work_dir / "5_rpf_package",
    }


def _extract_archive(archive_path: Path, target_dir: Path, *, gtav_root: Optional[Path] = None, staging_dir: Optional[Path] = None, patterns: Sequence[str] = ()) -> None:
    """Extract an RPF archive cleanly via `rage extract` without touching GTA5.exe."""
    target_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_safe_rage_cmd(
        "extract",
        str(archive_path),
        *list(patterns),
        "-o",
        str(target_dir),
        gtav_root=gtav_root,
        staging_dir=staging_dir,
    )
    subprocess.run(cmd, stdin=subprocess.DEVNULL, check=True)


def ensure_npc_staging_extracted(
    ped_name: str,
    location: Dict[str, Any],
    *,
    force_reextract: bool = False,
) -> Dict[str, Any]:
    """
    Ensure vanilla base skeleton `.yft`, target ped RPF staging folder, DLC
    override staging folders, and immutable backups are ready for patching.
    """
    resolved_gtav = project_paths.get_gtav_root_dir()
    resolved_staging = project_paths.get_staging_dir()
    paths_info = get_npc_staging_paths(
        ped_name,
        location,
        staging_dir=resolved_staging,
        project_root=project_paths.get_project_root(),
    )

    outer_dir = Path(paths_info["outer_extracted_dir"])
    inner_rpf = Path(paths_info["inner_rpf_file"])
    vanilla_outer = Path(paths_info["vanilla_outer_rpf"])
    outer_game = Path(paths_info["outer_game_rpf"])
    outer_seed = outer_game if outer_game.is_file() else vanilla_outer

    outer_fresh_vanilla = False
    if force_reextract or not inner_rpf.is_file():
        print(f"[NPC Staging] Extracting {outer_seed.name} ({outer_seed}) -> {outer_dir} ...", flush=True)
        _extract_archive(outer_seed, outer_dir, gtav_root=resolved_gtav, staging_dir=resolved_staging)
        outer_fresh_vanilla = (outer_seed == vanilla_outer)

    inner_dir = Path(paths_info["inner_extracted_dir"])
    has_ped_data = (
        (inner_dir / f"{ped_name}.yft").is_file()
        and (
            (inner_dir / ped_name).is_dir()
            if location["ped_format"] == "streamed"
            else (inner_dir / f"{ped_name}.ydd").is_file()
        )
    )
    if force_reextract or not has_ped_data:
        print(f"[NPC Staging] Extracting {inner_rpf.name} -> {inner_dir} ...", flush=True)
        _extract_archive(inner_rpf, inner_dir, gtav_root=resolved_gtav, staging_dir=resolved_staging)

    # Save immutable vanilla skeleton .yft + vanilla ped files strictly from Rockstar vanilla RPFs
    backup_yft = Path(paths_info["vanilla_skeleton_backup"])
    npc_backup_dir = Path(paths_info["npc_backup_dir"])
    need_yft_backup = force_reextract or not backup_yft.is_file()
    need_dir_backup = (not npc_backup_dir.is_dir()) or (not any(npc_backup_dir.iterdir()))
    if need_yft_backup or need_dir_backup:
        if outer_fresh_vanilla and (inner_dir / f"{ped_name}.yft").is_file():
            if need_yft_backup:
                backup_yft.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(inner_dir / f"{ped_name}.yft", backup_yft)
            if need_dir_backup:
                npc_backup_dir.mkdir(parents=True, exist_ok=True)
                for ext_name in (".yft", ".ymt", ".ydd", ".ytd", ".yld"):
                    cand_file = inner_dir / f"{ped_name}{ext_name}"
                    if cand_file.is_file():
                        shutil.copy2(cand_file, npc_backup_dir / cand_file.name)
                ped_subdir = inner_dir / ped_name
                if ped_subdir.is_dir():
                    shutil.copytree(ped_subdir, npc_backup_dir / ped_name, dirs_exist_ok=True)
        else:
            tmp_dir = resolved_staging / "_tmp_npc_vanilla_skel"
            shutil.rmtree(tmp_dir, ignore_errors=True)
            try:
                _extract_archive(
                    vanilla_outer,
                    tmp_dir,
                    gtav_root=resolved_gtav,
                    staging_dir=resolved_staging,
                    patterns=[str(paths_info["inner_rpf_rel"].as_posix())],
                )
                tmp_inner = tmp_dir / paths_info["inner_rpf_rel"]
                if tmp_inner.is_file():
                    if need_yft_backup:
                        backup_yft.parent.mkdir(parents=True, exist_ok=True)
                        _extract_archive(
                            tmp_inner,
                            backup_yft.parent,
                            gtav_root=resolved_gtav,
                            staging_dir=resolved_staging,
                            patterns=[f"{ped_name}.yft"],
                        )
                    if need_dir_backup:
                        npc_backup_dir.mkdir(parents=True, exist_ok=True)
                        _extract_archive(
                            tmp_inner,
                            npc_backup_dir,
                            gtav_root=resolved_gtav,
                            staging_dir=resolved_staging,
                            patterns=[f"{ped_name}.*", f"{ped_name}/*"],
                        )
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    blender_yft = Path(paths_info["blender_dir"]) / f"{ped_name}.yft"
    blender_yft.parent.mkdir(parents=True, exist_ok=True)
    if not blender_yft.is_file() and backup_yft.is_file():
        shutil.copy2(backup_yft, blender_yft)

    for ovr_spec in paths_info["dlc_override_specs"]:
        dlc_dir = Path(ovr_spec["dlc_extracted_dir"])
        ovr_inner = Path(ovr_spec["inner_rpf_file"])
        models_dir = Path(ovr_spec["models_extracted_dir"])
        game_dlc = Path(ovr_spec["game_dlc_rpf"])
        vanilla_dlc = Path(ovr_spec["vanilla_dlc_rpf"])
        dlc_seed = game_dlc if game_dlc.is_file() else vanilla_dlc
        if force_reextract or not ovr_inner.is_file():
            print(
                f"[NPC Staging] Extracting DLC {ovr_spec['dlc_name']} ({dlc_seed}) -> {dlc_dir} ...",
                flush=True,
            )
            _extract_archive(
                dlc_seed,
                dlc_dir,
                gtav_root=resolved_gtav,
                staging_dir=resolved_staging,
            )
        if force_reextract or not models_dir.is_dir() or not any(models_dir.iterdir()):
            print(
                f"[NPC Staging] Extracting {ovr_inner.name} -> {models_dir} ...",
                flush=True,
            )
            _extract_archive(
                ovr_inner,
                models_dir,
                gtav_root=resolved_gtav,
                staging_dir=resolved_staging,
            )

    if location.get("prop_targets"):
        project_paths.ensure_streamedpedprops_extracted()

    return paths_info


def _patch_streamed_folder(
    ped_folder: Path,
    *,
    primary_component: str,
    models_by_slot: Dict[str, Path],
    fallback_model_ydd: Path,
    texture_ytd_path: Path,
    dummy_ydd_path: Path,
) -> Dict[str, int]:
    """Patch one streamedpeds/<ped_name>/ folder in place."""
    if not ped_folder.is_dir():
        return {"primary_ydd": 0, "primary_ytd": 0, "dummy_ydd": 0, "untouched": 0}

    primary_prefix = f"{primary_component.lower()}_"
    primary_tex_prefix = f"{primary_component.lower()}_diff_"
    counts = {"primary_ydd": 0, "primary_ytd": 0, "dummy_ydd": 0, "untouched": 0}

    for entry_path in sorted(ped_folder.iterdir()):
        if not entry_path.is_file():
            continue
        low_name = entry_path.name.lower()
        stem_name = entry_path.stem.lower()
        if low_name.startswith(primary_prefix) and low_name.endswith(".ydd"):
            src_ydd = models_by_slot.get(stem_name, fallback_model_ydd)
            ped_damage_helper.validate_rpf7_resource_file(src_ydd)
            shutil.copyfile(src_ydd, entry_path)
            counts["primary_ydd"] += 1
        elif low_name.startswith(primary_tex_prefix) and low_name.endswith(".ytd"):
            ped_damage_helper.validate_rpf7_resource_file(texture_ytd_path)
            shutil.copyfile(texture_ytd_path, entry_path)
            counts["primary_ytd"] += 1
        elif low_name.endswith(".ydd") and any(
            low_name.startswith(f"{comp_tok}_") for comp_tok in STREAMED_COMPONENT_PREFIXES
        ):
            shutil.copyfile(dummy_ydd_path, entry_path)
            counts["dummy_ydd"] += 1
        else:
            counts["untouched"] += 1
    return counts


def _patch_ped_props_folder(
    props_folder: Path,
    prop_dummy_ydd: Path,
) -> int:
    """Replace all p_*.ydd wearables in `<ped_name>_p/` with invisible prop dummy."""
    if not props_folder.is_dir() or not prop_dummy_ydd.is_file():
        return 0
    replaced_count = 0
    for entry_path in sorted(props_folder.iterdir()):
        if entry_path.is_file() and entry_path.name.lower().startswith("p_") and entry_path.suffix.lower() == ".ydd":
            shutil.copyfile(prop_dummy_ydd, entry_path)
            replaced_count += 1
    return replaced_count


def apply_npc_slot_replacement(
    ped_name: str,
    npc_entry: Dict[str, Any],
    *,
    staging_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Apply built `.yft`, `.ydd`, and `.ytd` files onto staged RPF folders for
    an NPC (supporting both `streamed` and `componentpeds` layouts + DLC overrides).
    """
    norm_ped = normalize_ped_model_name(ped_name)
    location = dict(npc_entry["location"])
    info = staging_info or get_npc_staging_paths(norm_ped, location)

    dummy_ydd_path = project_paths.get_dummy_ydd_path()
    prop_dummy_path = project_paths.get_prop_dummy_ydd_path()
    if not dummy_ydd_path.is_file():
        raise FileNotFoundError(f"Dummy .ydd not found: {dummy_ydd_path}")

    package_dir = Path(info["package_dir"])
    skeleton_yft = package_dir / f"{norm_ped}.yft"
    texture_ytd = Path(
        npc_entry.get("ytd_file")
        or (Path(info["textures_dir"]) / f"{norm_ped}_atlas.ytd")
    )
    if not skeleton_yft.is_file():
        raise FileNotFoundError(f"Missing built NPC .yft: {skeleton_yft}")
    if not texture_ytd.is_file():
        raise FileNotFoundError(f"Missing built NPC .ytd: {texture_ytd}")

    ped_damage_helper.validate_rpf7_resource_file(skeleton_yft)
    ped_damage_helper.validate_rpf7_resource_file(texture_ytd)

    inner_dir = Path(info["inner_extracted_dir"])
    shutil.copyfile(skeleton_yft, inner_dir / f"{norm_ped}.yft")

    summary: Dict[str, Any] = {
        "ped_name": norm_ped,
        "ped_format": location["ped_format"],
        "patched_dirs": [],
        "props_replaced": 0,
    }

    if location["ped_format"] == "streamed":
        models_by_slot: Dict[str, Path] = {}
        fallback_model: Optional[Path] = None
        for ydd_candidate in sorted(package_dir.glob("*.ydd")):
            models_by_slot[ydd_candidate.stem.lower()] = ydd_candidate
            if fallback_model is None:
                fallback_model = ydd_candidate
        if fallback_model is None:
            raise FileNotFoundError(f"No built .ydd models found inside {package_dir}")

        primary_comp = str(location.get("primary_component") or "uppr")
        base_counts = _patch_streamed_folder(
            inner_dir / norm_ped,
            primary_component=primary_comp,
            models_by_slot=models_by_slot,
            fallback_model_ydd=fallback_model,
            texture_ytd_path=texture_ytd,
            dummy_ydd_path=dummy_ydd_path,
        )
        summary["patched_dirs"].append({"dir": str(inner_dir / norm_ped), "counts": base_counts})

        for ovr_spec in info["dlc_override_specs"]:
            ovr_models_dir = Path(ovr_spec["models_extracted_dir"])
            if (ovr_models_dir / f"{norm_ped}.yft").is_file():
                shutil.copyfile(skeleton_yft, ovr_models_dir / f"{norm_ped}.yft")
            ovr_counts = _patch_streamed_folder(
                ovr_models_dir / norm_ped,
                primary_component=primary_comp,
                models_by_slot=models_by_slot,
                fallback_model_ydd=fallback_model,
                texture_ytd_path=texture_ytd,
                dummy_ydd_path=dummy_ydd_path,
            )
            summary["patched_dirs"].append(
                {"dir": str(ovr_models_dir / norm_ped), "counts": ovr_counts}
            )
    else:
        comp_ydd = package_dir / f"{norm_ped}.ydd"
        if not comp_ydd.is_file():
            raise FileNotFoundError(f"Missing componentpeds .ydd: {comp_ydd}")
        ped_damage_helper.validate_rpf7_resource_file(comp_ydd)
        shutil.copyfile(comp_ydd, inner_dir / f"{norm_ped}.ydd")
        shutil.copyfile(texture_ytd, inner_dir / f"{norm_ped}.ytd")
        # Remove cloth physics (.yld) when present so replaced geometry does not bind vanilla cloth
        yld_file = inner_dir / f"{norm_ped}.yld"
        if yld_file.is_file():
            yld_file.unlink()
        summary["patched_dirs"].append({"dir": str(inner_dir), "componentped": True})

    if location.get("prop_targets") and prop_dummy_path.is_file():
        rpf_paths_cfg = project_paths.get_rpf_paths()
        streamed_props_dir = Path(rpf_paths_cfg["streamedpedprops_extracted"])
        for prop_tgt in location["prop_targets"]:
            prop_inner = str(prop_tgt.get("inner_rpf_rel", "")).lower()
            if "streamedpedprops" in prop_inner:
                summary["props_replaced"] += _patch_ped_props_folder(
                    streamed_props_dir / f"{norm_ped}_p", prop_dummy_path
                )

    return summary


def repack_and_deploy_npc_entry(
    ped_name: str,
    npc_entry: Dict[str, Any],
    *,
    skip_shared_archives: bool = False,
    secondary_atlas_size: int = 0,
) -> List[Path]:
    """
    Repack the RPF hierarchy touched by `ped_name` (`OPEN`, `f_size=0`), verify
    RPF7 size/offset limits and uncompressed entries, and copy into `GTAV/mods`.
    """
    norm_ped = normalize_ped_model_name(ped_name)
    location = dict(npc_entry["location"])
    info = get_npc_staging_paths(norm_ped, location)
    rage_cli = project_paths.get_rage_cli()
    deployed_paths: List[Path] = []

    inner_rpf_dest = Path(info["inner_rpf_file"])
    inner_src_dir = Path(info["inner_extracted_dir"])
    outer_rpf_dest = Path(info["outer_modded_rpf"])
    outer_src_dir = Path(info["outer_extracted_dir"])
    outer_game_rpf = Path(info["outer_game_rpf"])

    outer_name_low = str(info["outer_rpf_name"]).lower()
    prop_targets = location.get("prop_targets") or ()
    has_streamed_props = any(
        "streamedpedprops" in str(prop_tgt.get("inner_rpf_rel", "")).lower()
        for prop_tgt in prop_targets
    )
    if has_streamed_props and not skip_shared_archives:
        repack_paths_map = repack_helper._load_repack_paths()
        streamed_props_rpf = Path(repack_paths_map["streamedpedprops_rpf_file"])
        streamed_props_dir = Path(repack_paths_map["streamedpedprops_extracted_dir"])
        x64v_modded_rpf = Path(repack_paths_map["x64v_modded_rpf_file"])
        x64v_extracted_dir = Path(repack_paths_map["x64v_extracted_dir"])
        x64v_game_rpf = Path(repack_paths_map["target_x64v_rpf_path"])
        if streamed_props_dir.is_dir() and x64v_extracted_dir.is_dir():
            repack_helper.repack_single_rpf_stage(
                streamed_props_rpf,
                streamed_props_dir,
                "NPC props streamedpedprops.rpf",
                rage_cli,
            )
            if outer_name_low != "x64v.rpf":
                repack_helper.repack_single_rpf_stage(
                    x64v_modded_rpf,
                    x64v_extracted_dir,
                    "NPC props outer x64v.rpf",
                    rage_cli,
                )
                repack_helper.copy_file_with_progress(
                    x64v_modded_rpf, x64v_game_rpf, "Deploy x64v.rpf"
                )
                deployed_paths.append(x64v_game_rpf)

    if not skip_shared_archives or outer_name_low != "x64v.rpf":
        if (
            outer_name_low == "x64v.rpf"
            and inner_rpf_dest.name.lower() == "streamedpeds_players.rpf"
        ):
            repack_helper.ensure_x64v_streamed_budget(
                outer_src_dir,
                inner_src_dir,
                rage_cli,
                secondary_atlas_size=secondary_atlas_size,
            )
        repack_helper.repack_single_rpf_stage(
            inner_rpf_dest,
            inner_src_dir,
            f"NPC inner {inner_rpf_dest.name}",
            rage_cli,
        )
        repack_helper.repack_single_rpf_stage(
            outer_rpf_dest,
            outer_src_dir,
            f"NPC outer {outer_rpf_dest.name}",
            rage_cli,
        )
        repack_helper.copy_file_with_progress(
            outer_rpf_dest, outer_game_rpf, f"Deploy {outer_game_rpf.name}"
        )
        deployed_paths.append(outer_game_rpf)

    for ovr_spec in info["dlc_override_specs"]:
        dlc_name = str(ovr_spec["dlc_name"])
        if skip_shared_archives and dlc_name in ("patchday3ng", "patchday4ng", "mppatchesng"):
            continue
        dlc_inner_dest = Path(ovr_spec["inner_rpf_file"])
        dlc_models_dir = Path(ovr_spec["models_extracted_dir"])
        dlc_outer_dest = Path(ovr_spec["modded_dlc_rpf"])
        dlc_dir = Path(ovr_spec["dlc_extracted_dir"])
        dlc_game_rpf = Path(ovr_spec["game_dlc_rpf"])
        repack_helper.repack_single_rpf_stage(
            dlc_inner_dest,
            dlc_models_dir,
            f"DLC inner {dlc_name}/{dlc_inner_dest.name}",
            rage_cli,
        )
        repack_helper.repack_single_rpf_stage(
            dlc_outer_dest,
            dlc_dir,
            f"DLC outer {dlc_name}/dlc.rpf",
            rage_cli,
        )
        repack_helper.copy_file_with_progress(
            dlc_outer_dest, dlc_game_rpf, f"Deploy {dlc_name}/dlc.rpf"
        )
        deployed_paths.append(dlc_game_rpf)

    for verify_rpf in deployed_paths:
        limit_rep = ped_damage_helper.inspect_rpf7_archive_limits(verify_rpf)
        if not limit_rep["ok"]:
            raise RuntimeError(f"RPF7 limit check failed for {verify_rpf}: {limit_rep}")
        proc_list = subprocess.run(
            build_safe_rage_cmd("list", "-d", str(verify_rpf)),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=120.0,
            check=True,
        )
        bad_comp = [
            line_txt
            for line_txt in proc_list.stdout.splitlines()
            if "Compressed:" in line_txt and "Compressed: 0" not in line_txt
        ]
        if bad_comp:
            raise RuntimeError(
                f"Compressed TOC entries remain in {verify_rpf}: {bad_comp[:5]}"
            )

    repack_helper.sync_gtav_runtime_mods(
        project_paths.get_project_root(),
        project_paths.get_gtav_root_dir(),
        overwrite_inis=False,
    )
    gtav_dir = project_paths.get_gtav_root_dir()
    if gtav_dir.is_dir() and not (gtav_dir / "dinput8.dll").is_file():
        try:
            repack_helper.download_and_install_asi_loader(gtav_dir)
        except Exception as download_exc:
            print(f"[WARN] Could not auto-download dinput8.dll ASI loader: {download_exc}", flush=True)
    repack_helper.print_gtav_runtime_status(gtav_dir)
    return deployed_paths


def build_rpf7_open_streaming(
    output_rpf_path: Path,
    source_directory_path: Path,
    task_description: str = "",
) -> Path:
    """
    Build an uncompressed `OPEN` RPF7 archive via 4 MB streaming I/O (`< 16 MB` RAM),
    avoiding `rage.exe create` multi-gigabyte in-memory Vec OOM on large archives.
    """
    start_timestamp = time.time()
    root_dir = Path(source_directory_path)
    out_path = Path(output_rpf_path)
    if not root_dir.is_dir():
        raise FileNotFoundError(f"RPF7 source directory not found: {root_dir}")

    nodes: List[Dict[str, Any]] = [
        {
            "path": root_dir,
            "name": "",
            "is_dir": True,
            "start": 0,
            "count": 0,
            "size": 0,
            "is_rsc7": False,
            "d2_val": 0,
            "d3_val": 0,
            "sector": 0,
            "name_off": 0,
        }
    ]
    dir_queue: deque[int] = deque([0])
    while dir_queue:
        cur_idx = dir_queue.popleft()
        cur_path = nodes[cur_idx]["path"]
        children = sorted(
            cur_path.iterdir(),
            key=lambda item_path: (item_path.name.encode("ascii", "replace").lower(), item_path.name),
        )
        nodes[cur_idx]["start"] = len(nodes)
        nodes[cur_idx]["count"] = len(children)
        for child_path in children:
            child_idx = len(nodes)
            child_is_dir = child_path.is_dir()
            nodes.append(
                {
                    "path": child_path,
                    "name": child_path.name,
                    "is_dir": child_is_dir,
                    "start": 0,
                    "count": 0,
                    "size": 0,
                    "is_rsc7": False,
                    "d2_val": 0,
                    "d3_val": 0,
                    "sector": 0,
                    "name_off": 0,
                }
            )
            if child_is_dir:
                dir_queue.append(child_idx)

    names_buf = bytearray()
    name_offsets: Dict[bytes, int] = {}
    for node_rec in nodes:
        name_bytes = str(node_rec["name"]).encode("ascii", "replace")
        if name_bytes not in name_offsets:
            name_offsets[name_bytes] = len(names_buf)
            names_buf.extend(name_bytes)
            names_buf.append(0)
        node_rec["name_off"] = name_offsets[name_bytes]
    while len(names_buf) % 16 != 0:
        names_buf.append(0)
    if len(names_buf) > 0xFFFF:
        raise ValueError(f"RPF7 names table exceeds 64 KiB limit ({len(names_buf)} bytes)")

    names_len = len(names_buf)
    toc_len = len(nodes) * 16
    data_start = ((16 + toc_len + names_len + 511) // 512) * 512
    cur_sector = data_start // 512
    total_payload_bytes = 0

    for node_rec in nodes:
        if node_rec["is_dir"]:
            continue
        file_size = node_rec["path"].stat().st_size
        node_rec["size"] = file_size
        node_rec["sector"] = cur_sector
        with open(node_rec["path"], "rb") as probe_handle:
            head16 = probe_handle.read(16)
        if len(head16) >= 16 and head16[:4] == b"RSC7":
            if file_size > ped_damage_helper.RPF7_MAX_RESOURCE_BYTES:
                raise ValueError(
                    f"RSC7 resource exceeds 16 MiB limit ({file_size} bytes): {node_rec['path']}"
                )
            _, _, sys_flags, gfx_flags = struct.unpack("<IIII", head16)
            node_rec["is_rsc7"] = True
            node_rec["d2_val"] = sys_flags
            node_rec["d3_val"] = gfx_flags
        else:
            if file_size > 0xFFFFFFFF:
                raise ValueError(f"Binary entry exceeds 4 GiB: {node_rec['path']}")
            node_rec["d2_val"] = file_size & 0xFFFFFFFF
            node_rec["d3_val"] = 0
        sectors_needed = max(1, (file_size + 511) // 512) if file_size > 0 else 0
        if (cur_sector + sectors_needed) >= 0x7FFFFF:
            raise ValueError(
                f"RPF7 sector offset limit (4.00 GiB) exceeded while packing {node_rec['name']}"
            )
        cur_sector += sectors_needed
        total_payload_bytes += file_size

    label = task_description or out_path.name
    total_mb = total_payload_bytes / (1024.0 * 1024.0)
    print(f"--- {label} (streaming RPF7 OPEN, {total_mb:.1f} MB input) ---", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_name(f".{out_path.name}.tmp.{os.getpid()}")
    chunk_bytes = 4 * 1024 * 1024
    written_payload = 0
    next_pct_step = 25.0
    last_tty_print = 0.0
    open_magic_u32 = struct.unpack("<I", b"OPEN")[0]

    try:
        with open(tmp_path, "wb") as out_handle:
            out_handle.write(struct.pack("<IIII", 0x52504637, len(nodes), names_len, open_magic_u32))
            for node_rec in nodes:
                if node_rec["is_dir"]:
                    d0_val = node_rec["name_off"] & 0xFFFF
                    d1_val = 0x7FFFFF00
                    d2_val = node_rec["start"]
                    d3_val = node_rec["count"]
                elif node_rec["is_rsc7"]:
                    entry_file_size = node_rec["size"]
                    d0_val = (node_rec["name_off"] & 0xFFFF) | ((entry_file_size & 0xFFFF) << 16)
                    d1_val = (
                        0x80000000
                        | ((node_rec["sector"] & 0x7FFFFF) << 8)
                        | ((entry_file_size >> 16) & 0xFF)
                    )
                    d2_val = node_rec["d2_val"]
                    d3_val = node_rec["d3_val"]
                else:
                    d0_val = node_rec["name_off"] & 0xFFFF
                    d1_val = (node_rec["sector"] & 0x7FFFFF) << 8
                    d2_val = node_rec["d2_val"]
                    d3_val = 0
                out_handle.write(struct.pack("<IIII", d0_val, d1_val, d2_val, d3_val))
            out_handle.write(names_buf)
            hdr_pad = data_start - out_handle.tell()
            if hdr_pad > 0:
                out_handle.write(b"\x00" * hdr_pad)

            for node_rec in nodes:
                if node_rec["is_dir"] or node_rec["size"] == 0:
                    continue
                with open(node_rec["path"], "rb") as src_handle:
                    while True:
                        block = src_handle.read(chunk_bytes)
                        if not block:
                            break
                        out_handle.write(block)
                        written_payload += len(block)
                        if total_payload_bytes > 0:
                            pct = min(99.9, (written_payload / total_payload_bytes) * 100.0)
                            now_timestamp = time.time()
                            if (sys.stdout.isatty() and now_timestamp - last_tty_print >= 0.25) or (
                                not sys.stdout.isatty() and pct >= next_pct_step
                            ):
                                bar_str = repack_helper.format_progress_bar(pct / 100.0)
                                repack_helper.write_progress_line(
                                    f"  {bar_str} {pct:5.1f}% ({written_payload / (1024.0 * 1024.0):.1f}/{total_mb:.1f} MB | {now_timestamp - start_timestamp:.1f}s)",
                                    is_final=False,
                                )
                                last_tty_print = now_timestamp
                                while next_pct_step <= pct:
                                    next_pct_step += 25.0
                rem_bytes = node_rec["size"] % 512
                if rem_bytes:
                    out_handle.write(b"\x00" * (512 - rem_bytes))

        os.replace(tmp_path, out_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    elapsed_sec = max(0.001, time.time() - start_timestamp)
    final_mb = out_path.stat().st_size / (1024.0 * 1024.0)
    repack_helper.write_progress_line(
        f"  {repack_helper.format_progress_bar(1.0)} 100.0% ({final_mb:.1f} MB) Finished in {elapsed_sec:.1f}s",
        is_final=True,
    )
    repack_helper.patch_rpf7_open_and_zero_compressed(out_path)
    return out_path
