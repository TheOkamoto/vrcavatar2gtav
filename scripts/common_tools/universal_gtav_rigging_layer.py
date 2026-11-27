#!/usr/bin/env python3
"""
universal_gtav_rigging_layer.py
===============================
Layer 1 of 2 for the universal protagonist/NPC/pedestrian builder.

Handles source archive/Unity resolution, humanoid bone discovery, A-Pose arm
rotations, avatar height & root alignment scaling, soft skirt/jaw weight
mapping, and packed `componentpeds` `.ydd`/`.ymt` dictionary inspection.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))


def _resolve_repo_root() -> Path:
    """Locate repository root cleanly in both scripts/common_tools and _deploy_tools."""
    parent_dir = _MODULE_DIR.parent
    if (parent_dir / "vrc2gtav.cfg").is_file() or (parent_dir / "vrc2gtav.cfg.example").is_file():
        return parent_dir
    return parent_dir.parent


def _resolve_source_path(
    raw_value: str,
    project_root: Path,
    base_dir: Optional[Path] = None,
) -> Path:
    """Resolve user-supplied source paths across WSL, Windows, and repo-relative forms."""
    text_val = str(raw_value or "").strip().strip('"').strip("'")
    direct = Path(text_val)
    if direct.exists():
        return direct.resolve()
    try:
        import vrc2gtav_paths as project_paths
        host_cand = project_paths.to_host_path(text_val, project_root_dir=project_root)
        if host_cand.exists():
            return host_cand.resolve()
    except Exception:
        pass
    if base_dir is not None:
        rel_cand = base_dir / text_val
        if rel_cand.exists():
            return rel_cand.resolve()
    return direct


def _select_scene_or_prefab(
    scan_info: Dict[str, Any],
    preferred_name: str = "",
) -> Tuple[Optional[Path], str]:
    """
    Pick the primary `.unity` scene or root `.prefab` inside an ingested Unity
    project (`Karin_v1.11` ships `.prefab` files with zero `.unity` scenes).
    """
    import avatar_archive_helper

    preferred_prefab = scan_info.get("preferred_prefab")
    if preferred_prefab and Path(str(preferred_prefab)).is_file():
        pref_path = Path(str(preferred_prefab))
        return pref_path, (preferred_name or pref_path.stem)

    preferred_scene = scan_info.get("preferred_scene")
    scene_paths = [Path(pth) for pth in (scan_info.get("scenes") or ())]
    if preferred_scene and Path(str(preferred_scene)).is_file():
        chosen_scene = Path(str(preferred_scene))
        discovered_avatars = avatar_archive_helper.discover_scene_avatars(chosen_scene)
        selected_entry = avatar_archive_helper.prompt_select_scene_avatar(
            discovered_avatars,
            default_name=preferred_name or None,
        )
        chosen_name = (
            str(selected_entry.get("name", "")).strip()
            if selected_entry is not None
            else (preferred_name or chosen_scene.stem)
        )
        return chosen_scene, chosen_name

    proj_root = Path(scan_info["unity_project_root"])
    if scene_paths:
        chosen_scene = scene_paths[0]
        discovered_avatars = avatar_archive_helper.discover_scene_avatars(chosen_scene)
        selected_entry = avatar_archive_helper.prompt_select_scene_avatar(
            discovered_avatars,
            default_name=preferred_name or None,
        )
        chosen_name = (
            str(selected_entry.get("name", "")).strip()
            if selected_entry is not None
            else (preferred_name or chosen_scene.stem)
        )
        return chosen_scene, chosen_name

    prefab_paths = [Path(pth) for pth in (scan_info.get("prefab_files") or ())]
    if not prefab_paths:
        return None, preferred_name

    project_tok = re.sub(r"[^a-z0-9]+", "", proj_root.name.lower())
    pref_tok = re.sub(r"[^a-z0-9]+", "", preferred_name.lower())

    def _score_prefab(pref_path: Path) -> Tuple[int, int, str]:
        stem_low = pref_path.stem.lower()
        clean_stem = re.sub(r"[^a-z0-9]+", "", stem_low)
        exact_match = 0
        if pref_tok and clean_stem == pref_tok:
            exact_match = 3
        elif project_tok and (project_tok.startswith(clean_stem) or clean_stem in project_tok):
            exact_match = 2 if len(clean_stem) >= 3 else 1
        # Penalize alternate variant prefabs (`_kisekae`, `_quest`, `_opt`, `_low`) slightly
        variant_pen = 1 if any(tok in stem_low for tok in ("kisekae", "quest", "android", "collider", "prop")) else 0
        depth_val = len(pref_path.parts)
        return (-exact_match, variant_pen, f"{depth_val:03d}:{stem_low}")

    best_prefab = sorted(prefab_paths, key=_score_prefab)[0]
    return best_prefab, best_prefab.stem


def select_primary_avatar_fbx(
    fbx_files: Sequence[Path],
    avatar_name: str = "",
    ma_plan: Optional[Dict[str, Any]] = None,
    fallback_root: Optional[Path] = None,
) -> Optional[Path]:
    """Select the primary humanoid avatar FBX across arbitrary Booth scenes/archives."""
    import blendshape_helper

    candidates = [Path(item) for item in (fbx_files or ()) if Path(item).is_file()]
    if not candidates:
        return None
    plan = ma_plan or {}
    active_by_fbx = {
        str(Path(fbx_key).resolve()): list(mesh_names or ())
        for fbx_key, mesh_names in (plan.get("active_meshes_by_fbx") or {}).items()
        if fbx_key
    }
    anchor_tokens = [tok.lower() for tok in re.split(r"[^A-Za-z0-9]+", str(avatar_name or "")) if len(tok) >= 3]
    scene_str = str(plan.get("scene_path") or "").strip()
    if scene_str:
        anchor_tokens.append(Path(scene_str).stem.lower())
    if fallback_root is not None:
        anchor_tokens.append(Path(fallback_root).name.lower())
    accessory_substrings = (
        "_for_", "wear", "dress", "outfit", "hair", "nail", "earring", "cloth",
        "casquette", "megane", "glass", "ribbon", "watch", "shoe", "sock",
        "collar", "choker", "wing", "horn", "bunny", "monocle", "silk",
        "sleeve", "tight", "gimmick", "zurashi",
    )
    accessory_exact_tokens = frozenset(
        {
            "ear", "ears", "hat", "cap", "card", "item", "prop", "ring", "pin",
            "circle", "radio", "eeg", "bag", "tail", "halo", "love", "bra",
            "bikini", "cuff", "cuffs", "fur", "strap", "chain", "charm", "pack",
        }
    )

    def _score_primary(fbx_file: Path) -> Tuple[int, int, int, int, int, int, int, int]:
        resolved_str = str(fbx_file.resolve())
        stem_low = fbx_file.stem.lower()
        parent_low = str(fbx_file.parent).lower().replace("\\", "/")
        stem_tokens = {tok for tok in re.split(r"[^a-z0-9]+", stem_low) if tok}
        owned_meshes = active_by_fbx.get(resolved_str, ())
        skin_count = sum(
            1 for mesh_name in owned_meshes if blendshape_helper.is_body_or_face_skin_mesh(mesh_name)
        )
        owns_skin = 0 if skin_count > 0 else 1
        in_loose = 1 if "_ziploosefbx" in str(fbx_file).lower() else 0
        is_accessory = (
            1
            if (
                any(tok in stem_low for tok in accessory_substrings)
                or bool(stem_tokens & accessory_exact_tokens)
            )
            else 0
        )
        parent_is_accessory = (
            1
            if any(
                tok in parent_low
                for tok in ("hair", "costume", "outfit", "dress", "wear", "cloth", "acc")
            )
            else 0
        )
        has_kaihen = 1 if any(tok in stem_low for tok in ("kaihen", "alt", "quest")) else 0
        matches_name = 0 if any(tok in stem_low or stem_low in tok for tok in anchor_tokens if tok) else 1
        return (
            owns_skin,
            -skin_count,
            in_loose,
            is_accessory,
            parent_is_accessory,
            has_kaihen,
            matches_name,
            -fbx_file.stat().st_size,
        )

    return sorted(candidates, key=_score_primary)[0]


def _select_main_fbx(
    scan_info: Dict[str, Any],
    ma_plan: Dict[str, Any],
    selected_prefab_or_scene: Optional[Path],
) -> Path:
    """Resolve the primary humanoid character FBX from MA plan or ingested files."""
    plan_base_fbxs = [
        Path(fbx_item)
        for fbx_item in (ma_plan.get("base_fbx_paths") or ())
        if Path(fbx_item).is_file()
    ]
    avatar_plan_name = str(ma_plan.get("avatar_name") or "").strip()
    if not avatar_plan_name and selected_prefab_or_scene is not None:
        avatar_plan_name = selected_prefab_or_scene.stem
    fallback_root = Path(scan_info["unity_project_root"]) if scan_info.get("unity_project_root") else None
    if plan_base_fbxs:
        picked = select_primary_avatar_fbx(plan_base_fbxs, avatar_plan_name, ma_plan, fallback_root=fallback_root)
        if picked is not None:
            return picked

    fbx_candidates = [Path(item) for item in (scan_info.get("fbx_files") or ()) if Path(item).is_file()]
    picked = select_primary_avatar_fbx(fbx_candidates, avatar_plan_name, ma_plan, fallback_root=fallback_root)
    if picked is None:
        raise FileNotFoundError("No FBX models found inside avatar workspace.")
    return picked


PROTAGONIST_VTOON_CHAR_IDS: Dict[str, int] = {
    "player_zero": 1,
    "player_one": 2,
    "player_two": 3,
}

PROTAGONIST_DISPLAY_NAMES: Dict[str, str] = {
    "player_zero": "Michael",
    "player_one": "Franklin",
    "player_two": "Trevor",
}

_PROGRESS_STAGE_CATALOG: Dict[str, Dict[str, str]] = {
    "ingest": {
        "en": "Ingesting avatar source...",
        "pt": "Carregando avatar de origem...",
        "ja": "アバターソースを読み込み中...",
    },
    "discover": {
        "en": "Discovering GTA V archive target...",
        "pt": "Localizando destino no GTA V...",
        "ja": "GTA V アーカイブを検索中...",
    },
    "atlas": {
        "en": "Compiling texture atlas & .ytd...",
        "pt": "Compilando atlas de texturas e .ytd...",
        "ja": "テクスチャアトラスと .ytd を生成中...",
    },
    "rig_resolve": {
        "en": "Resolving blendshapes & PhysBones...",
        "pt": "Processando expressões e PhysBones...",
        "ja": "ブレンドシェイプと PhysBones を解析中...",
    },
    "blender_start": {
        "en": "Starting Blender 4.0.2 + Sollumz...",
        "pt": "Iniciando Blender 4.0.2 + Sollumz...",
        "ja": "Blender 4.0.2 + Sollumz を起動中...",
    },
    "blender_import": {
        "en": "Importing FBX & aligning pose...",
        "pt": "Importando FBX e ajustando pose...",
        "ja": "FBX 読み込み・ポーズ調整中...",
    },
    "blender_weights": {
        "en": "Rigging clothing, facial jaw & blinking...",
        "pt": "Configurando pesos, boca e piscar...",
        "ja": "ウェイト・顎・まばたきを設定中...",
    },
    "blender_damage": {
        "en": "Applying PedDamage & saving .blend...",
        "pt": "Aplicando PedDamage e salvando .blend...",
        "ja": "PedDamage 適用・.blend 保存中...",
    },
    "blender_export": {
        "en": "Exporting .ydd mesh via Sollumz...",
        "pt": "Exportando malha .ydd via Sollumz...",
        "ja": "Sollumz で .ydd メッシュを出力中...",
    },
    "blender_retry": {
        "en": "Optimizing poly budget & retrying .ydd export...",
        "pt": "Otimizando malha e reexportando .ydd...",
        "ja": "ポリゴン最適化後に .ydd を再出力中...",
    },
    "yft_patch": {
        "en": "Patching .yft skeleton & PhysBones...",
        "pt": "Atualizando esqueleto .yft e PhysBones...",
        "ja": ".yft スケルトンと PhysBones を反映中...",
    },
    "slot_done": {
        "en": "Slot build finished",
        "pt": "Slot concluído",
        "ja": "スロット出力完了",
    },
    "rpf_deploy": {
        "en": "Repacking & deploying GTA V archives...",
        "pt": "Reempacotando e instalando RPFs no GTA V...",
        "ja": "GTA V RPF アーカイブを再構築・配置中...",
    },
    "rpf_done": {
        "en": "Deployment verified & complete",
        "pt": "Instalação verificada e concluída",
        "ja": "配置と検証が完了しました",
    },
}


def resolve_progress_text(stage_key_or_text: str, *, lang: str = "") -> str:
    """Resolve a localized stage string for EN/PT/JA progress banners."""
    import vrc2gtav_i18n as project_i18n

    active_lang = str(lang or "").strip().lower() or project_i18n.get_active_language()
    entry = _PROGRESS_STAGE_CATALOG.get(str(stage_key_or_text or "").strip())
    if entry:
        return entry.get(active_lang) or entry["en"]
    return str(stage_key_or_text or "").strip()


def compute_overall_progress_pct(
    slot_fraction: float,
    *,
    slot_index: int = 0,
    slot_total: int = 1,
    build_share: float = 0.82,
) -> float:
    """Map per-slot `[0..1]` completion proportionally into overall `0..99%` progress."""
    total = max(1, int(slot_total))
    idx = max(0, min(total - 1, int(slot_index)))
    clamped = max(0.0, min(1.0, float(slot_fraction)))
    share = max(0.10, min(0.99, float(build_share)))
    return min(99.0, ((idx + clamped) / total) * share * 100.0)


def emit_progress_status(
    pct: float,
    stage_key_or_text: str,
    *,
    slot_index: int = 0,
    slot_total: int = 1,
    ped_name: str = "",
    lang: str = "",
    extra: str = "",
) -> None:
    """Emit structured `[PROGRESS pct=..]` status line for Unity & CLI progress bars."""
    clamped_pct = max(0.0, min(99.9, float(pct)))
    ped_label = PROTAGONIST_DISPLAY_NAMES.get(str(ped_name or "").lower(), ped_name)
    prefix = ""
    if int(slot_total) > 1:
        tag = f"{int(slot_index) + 1}/{int(slot_total)}"
        prefix = f"[{tag} {ped_label}] " if ped_label else f"[{tag}] "
    elif ped_label:
        prefix = f"[{ped_label}] "
    base_text = resolve_progress_text(stage_key_or_text, lang=lang)
    full_text = f"{base_text} {extra}".strip() if extra else base_text
    clean_text = full_text.replace("\r", " ").replace("\n", " ").strip()
    print(f"[PROGRESS pct={clamped_pct:.1f}] {prefix}{clean_text}", flush=True)


def emit_slot_progress(
    slot_fraction: float,
    stage_key_or_text: str,
    *,
    slot_index: int = 0,
    slot_total: int = 1,
    build_share: float = 0.82,
    ped_name: str = "",
    lang: str = "",
    extra: str = "",
) -> None:
    """Emit proportional overall `[PROGRESS pct=..]` update for a slot sub-stage."""
    pct_val = compute_overall_progress_pct(
        slot_fraction,
        slot_index=slot_index,
        slot_total=slot_total,
        build_share=build_share,
    )
    emit_progress_status(
        pct_val,
        stage_key_or_text,
        slot_index=slot_index,
        slot_total=slot_total,
        ped_name=ped_name,
        lang=lang,
        extra=extra,
    )


def _pick_default_face_anim(
    scan_info: Dict[str, Any],
    avatar_hints: Sequence[str],
    fallback_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Locate a non-zero default facial `.anim` fallback when no Unity scene is available."""
    import blendshape_helper

    anim_candidates = sorted(Path(pth) for pth in (scan_info.get("anim_files") or ()))
    if not anim_candidates and fallback_dir is not None and fallback_dir.is_dir():
        anim_candidates = sorted(fallback_dir.rglob("*.anim"))
    for anim_file in anim_candidates:
        low_name = anim_file.stem.lower()
        if "default" not in low_name and "idle" not in low_name:
            continue
        non_zero_keys = blendshape_helper.load_unity_anim_blendshapes(anim_file, include_zero=False)
        if non_zero_keys:
            return anim_file
    return None


def prepare_universal_npc_build(
    *,
    source_spec: str,
    target_ped: str,
    avatar_name: str = "",
    force_reextract: bool = False,
    blood_decals: bool = True,
    eye_blink: Optional[bool] = None,
    eye_blink_strength: Optional[float] = None,
    mouth_open_strength: Optional[float] = None,
    physbones_marshmallow: Optional[bool] = None,
    import_face_blendshapes: Optional[bool] = None,
    import_body_blendshapes: Optional[bool] = None,
    blendshapes_source: Optional[str] = None,
    physbones_source: Optional[str] = None,
    blendshapes_cfg: Optional[str] = None,
    face_anim: Optional[str] = None,
    physbones_cfg: Optional[str] = None,
    vtoon_char_id: Optional[int] = None,
    atlas_size: int = 2048,
    normal_size: int = 0,
    secondary_atlas_size: int = 0,
    texture_overrides: Optional[Dict[str, str]] = None,
    deploy: bool = True,
    skip_atlas: bool = False,
    slot_index: int = 0,
    slot_total: int = 1,
    build_share: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Ingest Unity avatar archive/folder, discover & extract GTA V NPC staging,
    generate 2K texture atlas & .ytd, resolve BlendShapes + PhysBones, and write
    the Blender build manifest JSON.
    """
    import avatar_archive_helper
    import blendshape_helper
    import eye_blink_helper
    import modular_avatar_helper
    import npc_registry_helper
    import physbone_helper
    import universal_atlas_builder
    import vrc2gtav_i18n as project_i18n
    import vrc2gtav_paths as project_paths

    project_root = project_paths.get_project_root()
    norm_ped = npc_registry_helper.normalize_ped_model_name(target_ped)
    resolved_src = _resolve_source_path(source_spec, project_root)
    eff_slot_total = max(1, int(slot_total))
    eff_slot_index = max(0, min(eff_slot_total - 1, int(slot_index)))
    eff_build_share = float(build_share) if build_share is not None else (0.82 if deploy else 0.98)
    active_lang = project_i18n.get_active_language()

    emit_slot_progress(
        0.04,
        "ingest",
        slot_index=eff_slot_index,
        slot_total=eff_slot_total,
        build_share=eff_build_share,
        ped_name=norm_ped,
        lang=active_lang,
    )
    print(f"[1/4] Ingesting avatar source: {resolved_src}", flush=True)
    scan_info = avatar_archive_helper.ingest_avatar_source(
        resolved_src,
        project_root,
        force_reextract=False,
    )
    selected_scene_or_prefab, resolved_avatar_name = _select_scene_or_prefab(
        scan_info, preferred_name=avatar_name
    )
    unity_proj_root = Path(scan_info["unity_project_root"])
    assets_root = Path(scan_info["assets_root"])
    effective_avatar_name = avatar_name or resolved_avatar_name or unity_proj_root.name
    hints = tuple(
        dict.fromkeys(
            tok.lower()
            for tok in (effective_avatar_name, resolved_src.stem, unity_proj_root.name)
            if tok
        )
    )

    ma_plan: Dict[str, Any] = {"loaded": False}
    if selected_scene_or_prefab is not None and selected_scene_or_prefab.is_file():
        ma_plan = modular_avatar_helper.build_modular_avatar_bake_plan(
            selected_scene_or_prefab,
            avatar_name=effective_avatar_name,
            assets_root=assets_root,
            character_hints=hints,
            resolve_materials=True,
        )

    main_fbx = _select_main_fbx(scan_info, ma_plan, selected_scene_or_prefab)
    extra_fbxs: List[Path] = []
    seen_extra_fbx = {str(main_fbx.resolve())}
    for raw_fbx_item in (
        *(ma_plan.get("base_fbx_paths") or ()),
        *(ma_plan.get("extra_fbx_paths") or ()),
    ):
        cand_fbx = Path(raw_fbx_item)
        if not cand_fbx.is_file():
            continue
        resolved_fbx = str(cand_fbx.resolve())
        if resolved_fbx not in seen_extra_fbx:
            seen_extra_fbx.add(resolved_fbx)
            extra_fbxs.append(cand_fbx)
    all_fbxs = [main_fbx, *extra_fbxs]

    emit_slot_progress(
        0.14,
        "discover",
        slot_index=eff_slot_index,
        slot_total=eff_slot_total,
        build_share=eff_build_share,
        ped_name=norm_ped,
        lang=active_lang,
    )
    print(f"[2/4] Discovering target '{norm_ped}' in GTA V archives...", flush=True)
    reg_existing = npc_registry_helper.load_npc_registry(project_root).get("npcs", {}).get(norm_ped)
    cached_location = reg_existing.get("location") if (not force_reextract and isinstance(reg_existing, dict)) else None
    if isinstance(cached_location, dict) and cached_location.get("outer_rpf") and Path(str(cached_location["outer_rpf"])).is_file():
        npc_location = cached_location
    else:
        npc_location = npc_registry_helper.discover_npc_location(norm_ped)
    staging_info = npc_registry_helper.ensure_npc_staging_extracted(
        norm_ped,
        npc_location,
        force_reextract=force_reextract,
    )

    skeleton_yft = Path(staging_info["blender_dir"]) / f"{norm_ped}.yft"
    vanilla_ped_ydd = ""
    if npc_location["ped_format"] == "componentpeds":
        cand_comp_ydd = Path(staging_info["inner_extracted_dir"]) / f"{norm_ped}.ydd"
        if cand_comp_ydd.is_file():
            vanilla_ped_ydd = str(cand_comp_ydd)
        else:
            backup_comp_ydd = Path(staging_info["npc_backup_dir"]) / f"{norm_ped}.ydd"
            if backup_comp_ydd.is_file():
                vanilla_ped_ydd = str(backup_comp_ydd)

    resolved_vtoon_id = (
        int(vtoon_char_id)
        if vtoon_char_id is not None
        else PROTAGONIST_VTOON_CHAR_IDS.get(norm_ped, 4)
    )
    resolved_atlas_size = max(256, min(4096, int(atlas_size or 2048)))
    resolved_normal_size = int(normal_size or 0)
    resolved_secondary_size = int(secondary_atlas_size or 0)
    emit_slot_progress(
        0.22,
        "atlas",
        slot_index=eff_slot_index,
        slot_total=eff_slot_total,
        build_share=eff_build_share,
        ped_name=norm_ped,
        lang=active_lang,
    )
    textures_dir = Path(staging_info["textures_dir"])
    existing_atlas_manifest_path = textures_dir / "atlas_manifest.json"
    atlas_manifest: Optional[Dict[str, Any]] = None
    if skip_atlas and existing_atlas_manifest_path.is_file():
        try:
            loaded_manifest = json.loads(
                existing_atlas_manifest_path.read_text(encoding="utf-8")
            )
            if (
                isinstance(loaded_manifest, dict)
                and loaded_manifest.get("atlas_png")
                and Path(str(loaded_manifest["atlas_png"])).is_file()
                and loaded_manifest.get("ytd_file")
                and Path(str(loaded_manifest["ytd_file"])).is_file()
            ):
                loaded_manifest["manifest_path"] = str(existing_atlas_manifest_path)
                atlas_manifest = loaded_manifest
                print(
                    f"[3/4] Reusing compiled atlas & .ytd: {loaded_manifest['ytd_file']}",
                    flush=True,
                )
        except Exception:
            atlas_manifest = None

    if atlas_manifest is None:
        print(
            f"[3/4] Compiling {resolved_atlas_size}px GTA V Texture Atlas & .ytd "
            f"(VToon char_id={resolved_vtoon_id})...",
            flush=True,
        )
        atlas_manifest = universal_atlas_builder.build_universal_avatar_atlas(
            ped_name=norm_ped,
            project_dir=unity_proj_root,
            scene_or_prefab=selected_scene_or_prefab,
            source_fbx=main_fbx,
            extra_fbxs=extra_fbxs,
            output_dir=textures_dir,
            atlas_size=resolved_atlas_size,
            normal_size=resolved_normal_size,
            ma_plan=ma_plan,
            avatar_name=effective_avatar_name,
            texture_overrides=texture_overrides,
            vtoon_char_id=resolved_vtoon_id,
            sync_to_game=bool(deploy),
        )

    anim_search_dir = (
        main_fbx.parent.parent
        if main_fbx.parent.parent.is_dir() and main_fbx.parent.parent != assets_root
        else main_fbx.parent
    )
    explicit_face_anim = project_paths.to_host_path(face_anim) if face_anim else None
    if explicit_face_anim is not None and explicit_face_anim.is_file():
        face_anim_path: Optional[Path] = explicit_face_anim
        print(f"[Blendshapes] Applying Face .anim override: {face_anim_path}", flush=True)
    else:
        if explicit_face_anim is not None:
            print(f"[Blendshapes] Requested --face-anim not found: {explicit_face_anim}", flush=True)
        # Preserve facial blendshapes already configured on the avatar in the Unity scene/prefab
        # whenever no explicit Facial Anim Override was selected.
        face_anim_path = (
            None
            if selected_scene_or_prefab
            else _pick_default_face_anim(scan_info, hints, fallback_dir=anim_search_dir)
        )
        if face_anim_path is None and selected_scene_or_prefab and import_face_blendshapes:
            print(
                f"[Blendshapes] Using avatar facial blendshapes directly from Unity scene/prefab ({Path(selected_scene_or_prefab).name})",
                flush=True,
            )
    char_pseudo_cfg: Dict[str, Any] = {
        "protagonist": norm_ped,
        "avatar_id": effective_avatar_name.lower(),
        "avatar": effective_avatar_name,
        "ped_name": norm_ped,
        "source_fbx": str(main_fbx),
        "unity_scene": str(selected_scene_or_prefab or ""),
        "unity_avatar_name": effective_avatar_name,
        "face_anim": str(face_anim_path or ""),
        "blendshapes_source": str(blendshapes_source or "auto"),
        "physbones_source": str(physbones_source or "auto"),
        "physbones_marshmallow": "true" if physbones_marshmallow else "false",
        "eye_blink": "on" if eye_blink is True else ("off" if eye_blink is False else "auto"),
        "eye_blink_strength": str(eye_blink_strength) if eye_blink_strength is not None else "0.80",
        "mouth_open_strength": str(
            eye_blink_helper.resolve_mouth_open_strength(mouth_open_strength)
        ),
    }

    disabled_meshes = list(ma_plan.get("disabled_meshes") or ())
    active_meshes = list(ma_plan.get("active_meshes") or ())

    package_dir = Path(staging_info["package_dir"])
    blender_dir = Path(staging_info["blender_dir"])
    package_dir.mkdir(parents=True, exist_ok=True)
    blender_dir.mkdir(parents=True, exist_ok=True)

    cfg_base_name = blendshape_helper.resolve_cfg_base_name(
        source_spec=resolved_src,
        scene_or_prefab=selected_scene_or_prefab,
        fbx_paths=all_fbxs,
        avatar_name=effective_avatar_name,
        fallback=norm_ped,
    )
    saved_blendshape_cfg = blender_dir / f"{cfg_base_name}_blendshapes.cfg"
    saved_pb_cfg = blender_dir / f"{cfg_base_name}_physbones.cfg"
    archive_for_header = (
        resolved_src
        if resolved_src.suffix.lower() in (".zip", ".unitypackage")
        else None
    )
    blendshape_headers = blendshape_helper.build_cfg_header_comments(
        cfg_kind="Blendshape",
        project_path=unity_proj_root,
        scene_path=selected_scene_or_prefab or "",
        fbx_paths=all_fbxs,
        archive_path=archive_for_header,
    )
    physbone_headers = blendshape_helper.build_cfg_header_comments(
        cfg_kind="PhysBone",
        project_path=unity_proj_root,
        scene_path=selected_scene_or_prefab or "",
        fbx_paths=all_fbxs,
        archive_path=archive_for_header,
    )

    active_face_mesh = next(
        (active_mesh_name for active_mesh_name in active_meshes if active_mesh_name.lower() == "body"),
        next(
            (
                active_mesh_name
                for active_mesh_name in active_meshes
                if any(tok in active_mesh_name.lower() for tok in ("face", "head", "body"))
            ),
            "Body",
        ),
    )
    blendshape_source_eff = str(blendshapes_source or ("unity" if selected_scene_or_prefab else "auto"))
    blendshape_cfg_host = str(project_paths.to_host_path(blendshapes_cfg)) if blendshapes_cfg else None
    pb_cfg_host = str(project_paths.to_host_path(physbones_cfg)) if physbones_cfg else None
    emit_slot_progress(
        0.36,
        "rig_resolve",
        slot_index=eff_slot_index,
        slot_total=eff_slot_total,
        build_share=eff_build_share,
        ped_name=norm_ped,
        lang=active_lang,
    )
    blendshape_res = blendshape_helper.resolve_character_blendshapes(
        char_pseudo_cfg,
        fbx_paths=[str(pth) for pth in all_fbxs],
        character_hints=hints,
        default_face_mesh=active_face_mesh,
        unity_assets_root=assets_root,
        override_source=blendshape_source_eff,
        override_cfg_path=blendshape_cfg_host or None,
        override_unity_scene=selected_scene_or_prefab,
        override_avatar_name=effective_avatar_name,
        override_face_anim=face_anim_path,
        save_cfg_path=saved_blendshape_cfg,
        header_comments=blendshape_headers,
        import_face=import_face_blendshapes,
        import_body=import_body_blendshapes,
    )

    pb_source_eff = str(physbones_source or ("unity" if selected_scene_or_prefab else "auto"))
    physbone_res = physbone_helper.resolve_character_physbones(
        char_pseudo_cfg,
        fbx_paths=[str(pth) for pth in all_fbxs],
        character_hints=hints,
        unity_assets_root=assets_root,
        override_source=pb_source_eff,
        override_cfg_path=pb_cfg_host or None,
        override_unity_scene=selected_scene_or_prefab,
        override_avatar_name=effective_avatar_name,
        override_marshmallow=physbones_marshmallow,
        save_cfg_path=saved_pb_cfg,
        header_comments=physbone_headers,
        max_custom_bones=physbone_helper.MAX_CUSTOM_PHYSBONES_PER_PED,
        override_excluded_meshes=disabled_meshes,
        override_active_meshes=active_meshes,
        verbose=True,
    )

    ma_plan_path = blender_dir / "modular_avatar_plan.json"
    ma_plan_path.write_text(
        json.dumps(ma_plan, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    manifest_data: Dict[str, Any] = {
        "ped_name": norm_ped,
        "ped_format": npc_location["ped_format"],
        "primary_component": npc_location["primary_component"],
        "export_drawables": npc_location["export_drawables"],
        "avatar_name": effective_avatar_name,
        "project_dir": str(unity_proj_root),
        "assets_dir": str(assets_root),
        "scene_or_prefab": str(selected_scene_or_prefab or ""),
        "source_fbx": str(main_fbx),
        "extra_fbxs": [str(pth) for pth in extra_fbxs],
        "skeleton_yft": str(skeleton_yft),
        "vanilla_ped_ydd": vanilla_ped_ydd,
        "target_yft": str(package_dir / f"{norm_ped}.yft"),
        "exported_models_dir": str(package_dir),
        "assembled_blend": str(blender_dir / f"{norm_ped}_assembled.blend"),
        "atlas_manifest": str(atlas_manifest["manifest_path"]),
        "atlas_png": str(atlas_manifest["atlas_png"]),
        "normal_png": str(atlas_manifest["normal_png"]),
        "spec_png": str(atlas_manifest["spec_png"]),
        "bump_dds": str(atlas_manifest.get("bump_dds") or ""),
        "spec_dds": str(atlas_manifest.get("spec_dds") or ""),
        "shader_bumpiness": float(atlas_manifest.get("shader_bumpiness", 0.0) or 0.0),
        "shader_specular_intensity": float(atlas_manifest.get("shader_specular_intensity", 0.0) or 0.0),
        "shader_specular_falloff": float(atlas_manifest.get("shader_specular_falloff", 1.0) or 1.0),
        "ytd_file": str(atlas_manifest["ytd_file"]),
        "blendshape_weights": blendshape_res["mesh_weights"],
        "physbones_cfg": str(saved_pb_cfg),
        "disabled_meshes": disabled_meshes,
        "active_meshes": active_meshes,
        "blood_decals": bool(blood_decals),
        "eye_blink": char_pseudo_cfg["eye_blink"],
        "eye_blink_strength": float(char_pseudo_cfg["eye_blink_strength"]),
        "mouth_open_strength": float(char_pseudo_cfg["mouth_open_strength"]),
        "atlas_size": resolved_atlas_size,
        "normal_size": resolved_normal_size,
        "secondary_atlas_size": resolved_secondary_size,
        "deploy": bool(deploy),
        "ma_plan_path": str(ma_plan_path),
        "progress": {
            "slot_index": eff_slot_index,
            "slot_total": eff_slot_total,
            "build_share": eff_build_share,
            "lang": active_lang,
        },
        "location": npc_location,
        "staging_info": {key: str(val) for key, val in staging_info.items() if isinstance(val, (str, Path))},
    }

    build_manifest_path = blender_dir / f"{norm_ped}_build_manifest.json"
    build_manifest_path.write_text(
        json.dumps(manifest_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    manifest_data["build_manifest_path"] = str(build_manifest_path)

    reg_data = npc_registry_helper.load_npc_registry(project_root)
    reg_data["npcs"][norm_ped] = {
        "ped_name": norm_ped,
        "avatar_name": effective_avatar_name,
        "source_spec": str(resolved_src),
        "project_dir": str(unity_proj_root),
        "scene_or_prefab": str(selected_scene_or_prefab or ""),
        "source_fbx": str(main_fbx),
        "ytd_file": str(atlas_manifest["ytd_file"]),
        "physbones_cfg": str(saved_pb_cfg),
        "build_manifest": str(build_manifest_path),
        "deployed": bool(deploy),
        "location": npc_location,
    }
    npc_registry_helper.save_npc_registry(reg_data, project_root)
    return manifest_data


def _find_humanoid_bone(arm_obj: Any, candidate_keys: Sequence[str]) -> Optional[Any]:
    """Locate a pose bone case-insensitively or by normalized Humanoid key."""
    import modular_avatar_helper

    pose_bones = arm_obj.pose.bones
    low_map = {pbone.name.lower(): pbone for pbone in pose_bones}
    norm_map = {
        modular_avatar_helper.normalize_bone_match_key(pbone.name): pbone
        for pbone in pose_bones
    }
    for key_item in candidate_keys:
        found = low_map.get(key_item.lower())
        if found is not None:
            return found
        norm_tok = modular_avatar_helper.normalize_bone_match_key(key_item)
        found_norm = norm_map.get(norm_tok)
        if found_norm is not None:
            return found_norm
    return None


def _compute_target_yft_pose_metrics(ped_armature: Any) -> Dict[str, Any]:
    """Measure target GTA V `.yft` skeleton vertical bounds and natural A-pose angle."""
    data_bones = ped_armature.data.bones
    arm_world = ped_armature.matrix_world

    def _head_z(bone_name: str) -> Optional[float]:
        bone_item = data_bones.get(bone_name)
        return float((arm_world @ bone_item.head_local).z) if bone_item is not None else None

    helper_left_z = _head_z("PH_L_Foot")
    helper_right_z = _head_z("PH_R_Foot")
    foot_left_z = _head_z("SKEL_L_Foot")
    foot_right_z = _head_z("SKEL_R_Foot")
    head_z = _head_z("SKEL_Head")

    ground_vals = [val for val in (helper_left_z, helper_right_z) if val is not None]
    foot_vals = [val for val in (foot_left_z, foot_right_z) if val is not None]
    ground_z = sum(ground_vals) / len(ground_vals) if ground_vals else -1.0
    foot_z = sum(foot_vals) / len(foot_vals) if foot_vals else -0.908
    target_head_z = head_z if head_z is not None else 0.640

    arm_drop_deg = 55.0
    u_arm = data_bones.get("SKEL_L_UpperArm")
    forearm_bone = data_bones.get("SKEL_L_Forearm")
    if u_arm is not None and forearm_bone is not None:
        vec_arm = (arm_world @ forearm_bone.head_local) - (arm_world @ u_arm.head_local)
        horiz_len = max(1e-5, math.hypot(vec_arm.x, vec_arm.y))
        arm_drop_deg = max(35.0, min(68.0, math.degrees(math.atan2(-vec_arm.z, horiz_len))))

    return {
        "ground_z": ground_z,
        "foot_z": foot_z,
        "head_z": target_head_z,
        "arm_drop_deg": arm_drop_deg,
    }


def _pose_avatar_arms_to_gtav_apose(
    bpy_mod: Any,
    mathutils_mod: Any,
    src_armature: Any,
    target_drop_deg: float,
) -> None:
    """
    Rotate Left and Right upper arms in world space to match GTA V's downward
    A-pose angle regardless of source FBX local bone roll conventions.
    """
    bpy_mod.context.view_layer.objects.active = src_armature
    bpy_mod.ops.object.mode_set(mode="POSE")
    bpy_mod.context.view_layer.update()

    armature_mat_world = src_armature.matrix_world
    side_specs = (
        ("L", ("Upper_arm.L", "LeftUpperArm", "UpperArm.L")),
        ("R", ("Upper_arm.R", "RightUpperArm", "UpperArm.R")),
    )
    forearm_specs = {
        "L": ("Lower_arm.L", "LeftLowerArm", "LowerArm.L"),
        "R": ("Lower_arm.R", "RightLowerArm", "LowerArm.R"),
    }

    for side_tag, upper_cands in side_specs:
        upper_pb = _find_humanoid_bone(src_armature, upper_cands)
        lower_pb = _find_humanoid_bone(src_armature, forearm_specs[side_tag])
        if upper_pb is None or lower_pb is None:
            continue

        start_point = armature_mat_world @ upper_pb.head
        end_point = armature_mat_world @ lower_pb.head
        arm_vec = (end_point - start_point)
        if arm_vec.length < 1e-4:
            continue
        cur_deg = math.degrees(math.atan2(-arm_vec.z, max(1e-5, math.hypot(arm_vec.x, arm_vec.y))))
        delta_deg = target_drop_deg - cur_deg
        if abs(delta_deg) < 1.0:
            continue

        horiz_vec = mathutils_mod.Vector((arm_vec.x, arm_vec.y, 0.0))
        if horiz_vec.length < 1e-5:
            horiz_vec = mathutils_mod.Vector((1.0 if side_tag == "L" else -1.0, 0.0, 0.0))
        horiz_vec.normalize()
        # Cross(horiz_dir, -Z) rotates downward toward -Z by positive angle `delta_deg`
        rot_axis = horiz_vec.cross(mathutils_mod.Vector((0.0, 0.0, -1.0))).normalized()
        world_rot = mathutils_mod.Quaternion(rot_axis, math.radians(delta_deg))

        if upper_pb.parent is not None:
            parent_rot = (armature_mat_world.to_3x3() @ upper_pb.parent.matrix.to_3x3()).normalized()
        else:
            parent_rot = armature_mat_world.to_3x3().normalized()
        rest_local_rot = (
            upper_pb.bone.matrix_local.to_3x3()
            if upper_pb.parent is None
            else (upper_pb.parent.bone.matrix_local.to_3x3().inverted() @ upper_pb.bone.matrix_local.to_3x3())
        )
        local_delta_mat = (parent_rot @ rest_local_rot).inverted() @ world_rot.to_matrix() @ (parent_rot @ rest_local_rot)
        upper_pb.rotation_mode = "QUATERNION"
        upper_pb.rotation_quaternion = (
            upper_pb.rotation_quaternion @ local_delta_mat.to_quaternion()
        ).normalized()

    bpy_mod.context.view_layer.update()
    bpy_mod.ops.object.mode_set(mode="OBJECT")


def _compute_universal_scale_and_offset(
    bpy_mod: Any,
    src_armature: Any,
    active_meshes: Sequence[Any],
    yft_metrics: Dict[str, Any],
) -> Tuple[float, float]:
    """
    Compute uniform scale and Z offset fitting the avatar's shoe sole onto GTA V's
    ground (`PH_L_Foot`) and aligning `Head` height cleanly to target ped `.yft`.
    """
    head_pb = _find_humanoid_bone(src_armature, ("Head", "head"))
    foot_pb = _find_humanoid_bone(src_armature, ("LeftFoot", "Foot.L", "RightFoot", "Foot.R"))

    depsgraph_eval = bpy_mod.context.evaluated_depsgraph_get()
    min_vert_z: Optional[float] = None
    max_vert_z: Optional[float] = None
    for mesh_obj in active_meshes:
        eval_obj = mesh_obj.evaluated_get(depsgraph_eval)
        temp_mesh = bpy_mod.data.meshes.new_from_object(eval_obj)
        world_mat = eval_obj.matrix_world
        for vert_item in temp_mesh.vertices:
            vert_z = float((world_mat @ vert_item.co).z)
            if min_vert_z is None or vert_z < min_vert_z:
                min_vert_z = vert_z
            if max_vert_z is None or vert_z > max_vert_z:
                max_vert_z = vert_z
        bpy_mod.data.meshes.remove(temp_mesh)

    src_floor_z = min_vert_z if min_vert_z is not None else 0.0
    src_head_z = (
        float((src_armature.matrix_world @ head_pb.head).z)
        if head_pb is not None
        else ((max_vert_z or 1.2) * 0.85)
    )

    # Blend sole-to-head and ankle-to-head so shoes touch ground while proportions remain crisp
    target_ground_z = float(yft_metrics["ground_z"])
    target_head_z = float(yft_metrics["head_z"])
    src_span = max(0.3, src_head_z - src_floor_z)
    scale_factor = (target_head_z - target_ground_z) / src_span
    z_offset = target_ground_z - (src_floor_z * scale_factor)
    return scale_factor, z_offset


def _strip_object_base_name(raw_name: str) -> str:
    """Remove Blender `.001` numeric duplication suffixes cleanly."""
    return re.sub(r"\.\d{3}$", "", str(raw_name or "").strip())


def _resolve_universal_target_bone(
    raw_bone_name: str,
    mesh_name: str,
    pb_bone_mapping_lower: Dict[str, str],
    src_parent_lookup: Optional[Dict[str, str]] = None,
) -> str:
    """Resolve an arbitrary Unity bone weight name onto the GTA V + PhysBone skeleton."""
    import hand_skeleton_helper
    import modular_avatar_helper
    import physbone_helper

    def _resolve_direct_token(cand_name: str) -> Optional[str]:
        low_tok = str(cand_name or "").strip().lower()
        if not low_tok:
            return None

        humanoid_table = {
            "hips": "SKEL_Pelvis",
            "spine": "SKEL_Spine1",
            "chest": "SKEL_Spine2",
            "upperchest": "SKEL_Spine3",
            "neck": "SKEL_Neck_1",
            "head": "SKEL_Head",
            "eye_l": "SKEL_Head",
            "eye_r": "SKEL_Head",
            "jaw": "SKEL_Head",
            "shoulder_l": "SKEL_L_Clavicle",
            "shoulder_r": "SKEL_R_Clavicle",
            "upperarm_l": "SKEL_L_UpperArm",
            "upperarm_r": "SKEL_R_UpperArm",
            "arm_l": "SKEL_L_UpperArm",
            "arm_r": "SKEL_R_UpperArm",
            "lowerarm_l": "SKEL_L_Forearm",
            "lowerarm_r": "SKEL_R_Forearm",
            "hand_l": "SKEL_L_Hand",
            "hand_r": "SKEL_R_Hand",
            "upperleg_l": "SKEL_L_Thigh",
            "upperleg_r": "SKEL_R_Thigh",
            "leg_l": "SKEL_L_Thigh",
            "leg_r": "SKEL_R_Thigh",
            "lowerleg_l": "SKEL_L_Calf",
            "lowerleg_r": "SKEL_R_Calf",
            "foot_l": "SKEL_L_Foot",
            "foot_r": "SKEL_R_Foot",
            "toe_l": "SKEL_L_Toe0",
            "toe_r": "SKEL_R_Toe0",
            "toebase_l": "SKEL_L_Toe0",
            "toebase_r": "SKEL_R_Toe0",
        }
        # Exact structural humanoid trunk/head names must never be hijacked by stray
        # VRCPhysBone entries like Head -> Child.
        exact_compact = re.sub(r"[\s_\-]+", "", low_tok)
        if exact_compact in ("hips", "pelvis", "spine", "chest", "upperchest", "neck", "head"):
            return humanoid_table["hips" if exact_compact == "pelvis" else exact_compact]

        if low_tok in pb_bone_mapping_lower:
            return pb_bone_mapping_lower[low_tok]
        space_tok = re.sub(r"\.(\d{3})$", lambda match_obj: f" {int(match_obj.group(1))}", low_tok)
        if space_tok in pb_bone_mapping_lower:
            return pb_bone_mapping_lower[space_tok]

        direct_pb = physbone_helper.resolve_bone_from_mapping(
            cand_name, bone_mapping_lower=pb_bone_mapping_lower
        )
        if direct_pb is not None:
            return direct_pb

        resolved_arm_finger = hand_skeleton_helper.resolve_finger_or_arm_bone(cand_name)
        if resolved_arm_finger is not None:
            return resolved_arm_finger

        norm_key = modular_avatar_helper.normalize_bone_match_key(cand_name)
        return humanoid_table.get(norm_key)

    direct_hit = _resolve_direct_token(raw_bone_name)
    if direct_hit is not None:
        return direct_hit

    low_name = str(raw_bone_name or "").strip().lower()
    if src_parent_lookup:
        cur_anc = src_parent_lookup.get(low_name, "")
        for _step in range(16):
            if not cur_anc:
                break
            anc_hit = _resolve_direct_token(cur_anc)
            if anc_hit is not None:
                return anc_hit
            cur_anc = src_parent_lookup.get(cur_anc.lower(), "")

    low_mesh = str(mesh_name or "").strip().lower()
    side_tag = hand_skeleton_helper.detect_bone_side_code(raw_bone_name)
    if any(
        tok in low_name
        for tok in ("hair", "ear", "cheek", "bang", "aho", "halo", "beret", "glasses", "pocky", "horn", "kemomimi", "mimi", "eyebrow", "eyelash")
    ) or any(low_name.startswith(pref) for pref in ("back.", "back_", "side.", "side_", "un_hat")):
        return "SKEL_Head"
    if "ribbon" in low_name:
        if "hair" in low_mesh or low_mesh == "ribbon":
            return "SKEL_Head"
        if side_tag and any(tok in low_name for tok in ("hand", "wrist", "sleeve", "cuff")):
            return f"SKEL_{side_tag}_Hand" if "hand" in low_name or "wrist" in low_name else f"SKEL_{side_tag}_Forearm"
        return "SKEL_Spine2"
    if "breast" in low_name or "oppai" in low_name or "bust" in low_name:
        return "SKEL_Spine2"
    if "wing" in low_name or "collar" in low_name:
        return "SKEL_Neck_1" if "collar" in low_name else "SKEL_Spine2"
    if side_tag and any(tok in low_name for tok in ("foot", "shoe", "heel", "toe")):
        return f"SKEL_{side_tag}_Foot"
    if side_tag and any(tok in low_name for tok in ("calf", "shin", "knee", "sock", "stocking")):
        return f"SKEL_{side_tag}_Calf"
    if side_tag and any(tok in low_name for tok in ("thigh", "leg")):
        return f"SKEL_{side_tag}_Thigh"
    if side_tag and any(tok in low_name for tok in ("hand", "wrist", "finger")):
        return f"SKEL_{side_tag}_Hand"
    if side_tag and any(tok in low_name for tok in ("forearm", "lower_arm", "sleeve", "cuff")):
        return f"SKEL_{side_tag}_Forearm"
    if side_tag and any(tok in low_name for tok in ("shoulder", "upperarm", "upper_arm")):
        return f"SKEL_{side_tag}_UpperArm"
    if "skirt" in low_name or "tail" in low_name or "coat" in low_name:
        return "SKEL_Pelvis"
    if any(
        tok in low_mesh
        for tok in ("hair", "kemomimi", "ear", "head", "bang", "top back", "under side", "beret", "halo", "glasses", "pocky", "horn")
    ) or low_mesh in ("back", "side"):
        return "SKEL_Head"
    return "SKEL_Pelvis"


def _compute_soft_skirt_weights(
    src_obj: Any,
    orig_vert_idx: int,
    ydd_coord: Any,
    vgroup_names_by_idx: Dict[int, str],
    vgroup_target_names: Dict[int, str],
) -> Dict[str, float]:
    """Blend skirt bone weights softly with Pelvis + Thighs to minimize leg clipping."""
    remapped: Dict[str, float] = {}
    skirt_weight = 0.0

    if orig_vert_idx < len(src_obj.data.vertices):
        src_vert = src_obj.data.vertices[orig_vert_idx]
        for grp_elem in src_vert.groups:
            if grp_elem.weight <= 0.001 or grp_elem.group not in vgroup_target_names:
                continue
            raw_name = vgroup_names_by_idx.get(grp_elem.group, "")
            target_bone = vgroup_target_names[grp_elem.group]
            if "skirt" in raw_name.lower():
                if target_bone.startswith("PB_"):
                    physbone_weight = grp_elem.weight * 0.78
                    remapped[target_bone] = remapped.get(target_bone, 0.0) + physbone_weight
                    skirt_weight += grp_elem.weight * 0.22
                else:
                    skirt_weight += grp_elem.weight
            else:
                remapped[target_bone] = remapped.get(target_bone, 0.0) + grp_elem.weight

    if skirt_weight > 0.0:
        vert_z = max(0.0, min(1.0, (0.05 - float(ydd_coord.z)) / 0.14))
        thigh_cap = vert_z * 0.22
        thigh_weight = skirt_weight * thigh_cap
        pelvis_weight = skirt_weight - thigh_weight
        if pelvis_weight > 1e-6:
            remapped["SKEL_Pelvis"] = remapped.get("SKEL_Pelvis", 0.0) + pelvis_weight
        side_mix = max(0.0, min(1.0, (float(ydd_coord.x) + 0.04) / 0.08))
        if thigh_weight * side_mix > 1e-6:
            remapped["SKEL_L_Thigh"] = remapped.get("SKEL_L_Thigh", 0.0) + (thigh_weight * side_mix)
        if thigh_weight * (1.0 - side_mix) > 1e-6:
            remapped["SKEL_R_Thigh"] = remapped.get("SKEL_R_Thigh", 0.0) + (thigh_weight * (1.0 - side_mix))

    if len(remapped) > 4:
        remapped = dict(
            sorted(remapped.items(), key=lambda pair_item: pair_item[1], reverse=True)[:4]
        )
    return remapped


def _extract_case_insensitive_jaw_weights(
    orig_body_obj: Any,
    mouth_open_strength: Optional[float] = None,
) -> Dict[int, float]:
    """Derive FACIAL_jaw weights from `vrc.v_aa` (any casing) or `kuchi_a` / `あ`."""
    import eye_blink_helper

    return eye_blink_helper.extract_facial_jaw_weights(
        orig_body_obj,
        mouth_open_strength=mouth_open_strength,
        delta_z_threshold=-0.0004,
    )


def _inspect_componentped_drawable_keys(
    vanilla_ydd_path: Path,
    primary_component: str,
) -> Tuple[List[str], List[str]]:
    """
    Import a vanilla `componentpeds` `.ydd` transiently in Blender to collect all
    drawable keys (`head_000_r` / `hash_976FBF04`, etc.) and identify which match
    `primary_component` via name prefix or JOAAT hash.
    """
    import bpy

    if not vanilla_ydd_path.is_file():
        return [f"{primary_component}_000_u"], [f"{primary_component}_000_u"]

    def _joaat(text_val: str) -> int:
        hash_acc = 0
        for byte_val in text_val.lower().encode("ascii", errors="ignore"):
            hash_acc = (hash_acc + byte_val) & 0xFFFFFFFF
            hash_acc = (hash_acc + (hash_acc << 10)) & 0xFFFFFFFF
            hash_acc = (hash_acc ^ (hash_acc >> 6)) & 0xFFFFFFFF
        hash_acc = (hash_acc + (hash_acc << 3)) & 0xFFFFFFFF
        hash_acc = (hash_acc ^ (hash_acc >> 11)) & 0xFFFFFFFF
        hash_acc = (hash_acc + (hash_acc << 15)) & 0xFFFFFFFF
        return hash_acc

    primary_hashes: set[str] = set()
    for var_idx in range(16):
        for race_suf in ("u", "r", "whi", "bla"):
            hash_hex = f"hash_{_joaat(f'{primary_component}_{var_idx:03d}_{race_suf}'):08X}"
            primary_hashes.add(hash_hex.lower())

    for obj_item in list(bpy.data.objects):
        bpy.data.objects.remove(obj_item, do_unlink=True)
    for mesh_blk in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh_blk)
    for arm_blk in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm_blk)

    bpy.ops.sollumz.import_assets(
        directory=str(vanilla_ydd_path.parent) + os.sep,
        files=[{"name": vanilla_ydd_path.name}],
    )

    all_keys: List[str] = []
    primary_keys: List[str] = []
    for obj_item in bpy.data.objects:
        if obj_item.type == "ARMATURE":
            clean_key = obj_item.name.strip()
            if clean_key not in all_keys:
                all_keys.append(clean_key)
                low_key = clean_key.lower()
                if low_key.startswith(f"{primary_component.lower()}_") or low_key in primary_hashes:
                    primary_keys.append(clean_key)

    for obj_item in list(bpy.data.objects):
        bpy.data.objects.remove(obj_item, do_unlink=True)
    for mesh_blk in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh_blk)
    for arm_blk in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm_blk)

    if not all_keys:
        return [f"{primary_component}_000_u"], [f"{primary_component}_000_u"]
    if not primary_keys:
        primary_keys = [all_keys[0]]
    return all_keys, primary_keys


_NON_TORSO_CLOTH_TOKENS = (
    "body",
    "skin",
    "face",
    "head",
    "eye",
    "lash",
    "brow",
    "mouth",
    "teeth",
    "tongue",
    "hair",
    "ear",
    "tail",
    "nail",
    "shoe",
    "slipper",
    "boot",
    "heel",
    "sock",
    "stocking",
    "pin",
    "halo",
    "glass",
    "beret",
    "hat",
    "cap",
    "ribbon",
    "choker",
    "collar_acc",
    "bag",
    "pouch",
    "watch",
    "clock",
    "ring",
    "earring",
    "pocky",
    "button",
)

_TORSO_ARM_BONES = (
    "SKEL_L_UpperArm",
    "SKEL_R_UpperArm",
    "RB_L_ArmRoll",
    "RB_R_ArmRoll",
)


def _is_torso_skin_mesh(mesh_obj) -> bool:
    if getattr(mesh_obj, "type", None) != "MESH" or not getattr(mesh_obj, "data", None):
        return False
    low_name = mesh_obj.name.lower()
    mat_names = " ".join(
        getattr(slot.material, "name", "").lower()
        for slot in getattr(mesh_obj, "material_slots", ())
        if getattr(slot, "material", None)
    )
    combined = f"{low_name} {mat_names}"
    has_body = ("body" in combined) or ("skin" in combined)
    if not has_body:
        return False
    blocked = (
        "sweat",
        "shirt",
        "corset",
        "dress",
        "skirt",
        "short",
        "pant",
        "shoe",
        "hair",
        "face",
        "head",
        "eye",
        "lash",
        "nail",
        "ear",
        "tail",
    )
    return not any(tok in low_name for tok in blocked)


def _is_torso_clothing_mesh(mesh_obj) -> bool:
    if getattr(mesh_obj, "type", None) != "MESH" or not getattr(mesh_obj, "data", None):
        return False
    if _is_torso_skin_mesh(mesh_obj):
        return False
    low_name = mesh_obj.name.lower()
    return not any(tok in low_name for tok in _NON_TORSO_CLOTH_TOKENS)


def _extract_vertex_weight_map(mesh_obj, vertex_obj) -> dict:
    group_lookup = {grp.index: grp.name for grp in mesh_obj.vertex_groups}
    weight_map = {}
    for gpe in vertex_obj.groups:
        grp_name = group_lookup.get(gpe.group)
        if grp_name and gpe.weight > 1e-5:
            weight_map[grp_name] = float(gpe.weight)
    return weight_map


def _assign_vertex_weight_map(mesh_obj, vertex_index: int, weight_map: dict) -> None:
    filtered = {weight_bone_name: val for weight_bone_name, val in weight_map.items() if val > 1e-5}
    total = sum(filtered.values())
    if total <= 1e-6:
        return
    inv_total = 1.0 / total
    existing = {grp.name: grp for grp in mesh_obj.vertex_groups}
    for weight_bone_name, raw_val in filtered.items():
        grp = existing.get(weight_bone_name)
        if grp is None:
            grp = mesh_obj.vertex_groups.new(name=weight_bone_name)
            existing[weight_bone_name] = grp
        grp.add([vertex_index], raw_val * inv_total, "REPLACE")
    for weight_bone_name, grp in existing.items():
        if weight_bone_name not in filtered:
            try:
                grp.remove([vertex_index])
            except RuntimeError:
                pass


def _resolve_torso_bounds(armature_obj) -> tuple:
    medial_limit = 0.140
    chest_z_min = 0.250
    chest_z_max = 0.620
    if not armature_obj or getattr(armature_obj, "type", None) != "ARMATURE":
        return medial_limit, chest_z_min, chest_z_max
    bones = armature_obj.data.bones
    mtx = armature_obj.matrix_world
    arm_offsets = []
    for arm_name in ("SKEL_L_UpperArm", "SKEL_R_UpperArm"):
        arm_bone = bones.get(arm_name)
        if arm_bone is not None:
            arm_offsets.append(abs((mtx @ arm_bone.head_local).x))
    if arm_offsets:
        mean_arm_x = sum(arm_offsets) / float(len(arm_offsets))
        medial_limit = max(0.118, min(0.155, mean_arm_x))
    spine_bone = bones.get("SKEL_Spine2") or bones.get("SKEL_Spine1")
    if spine_bone is not None:
        chest_z_min = float((mtx @ spine_bone.head_local).z) - 0.060
    neck_bone = bones.get("SKEL_Neck_1") or bones.get("SKEL_Head")
    if neck_bone is not None:
        chest_z_max = float((mtx @ neck_bone.head_local).z) + 0.025
    return medial_limit, chest_z_min, max(chest_z_min + 0.150, chest_z_max)


def conform_tight_torso_clothing_weights(
    mesh_objects,
    armature_obj=None,
    max_skin_dist: float = 0.018,
    min_clearance: float = 0.006,
) -> int:
    """Conform upper-chest fitted clothing away from arm bones and lift over skin."""
    if not mesh_objects:
        return 0
    from mathutils import kdtree

    medial_limit, chest_z_min, chest_z_max = _resolve_torso_bounds(armature_obj)
    skin_samples = []
    for skin_obj in mesh_objects:
        if not _is_torso_skin_mesh(skin_obj):
            continue
        mtx = skin_obj.matrix_world
        nrm_mtx = mtx.to_3x3()
        for vtx in skin_obj.data.vertices:
            world_pos = mtx @ vtx.co
            if (
                abs(world_pos.x) > medial_limit + 0.035
                or world_pos.y >= -0.015
                or not (chest_z_min - 0.04 <= world_pos.z <= chest_z_max + 0.03)
            ):
                continue
            world_normal = (nrm_mtx @ vtx.normal).normalized()
            if world_normal.y >= 0.25:
                continue
            skin_weight_map = _extract_vertex_weight_map(skin_obj, vtx)
            if not skin_weight_map:
                continue
            skin_samples.append((world_pos, world_normal, skin_weight_map))

    if not skin_samples:
        return 0

    kdtree_index = kdtree.KDTree(len(skin_samples))
    for smp_idx, (world_pos, _world_normal, _skin_weight) in enumerate(skin_samples):
        kdtree_index.insert(world_pos, smp_idx)
    kdtree_index.balance()

    adjusted_count = 0
    fade_span = 0.025
    for cloth_obj in mesh_objects:
        if not _is_torso_clothing_mesh(cloth_obj):
            continue
        cloth_data = cloth_obj.data
        mtx = cloth_obj.matrix_world
        inv_mtx = mtx.inverted()
        nrm_mtx = mtx.to_3x3()
        cloth_changed = False

        for vtx in cloth_data.vertices:
            world_pos = mtx @ vtx.co
            if (
                abs(world_pos.x) >= medial_limit
                or world_pos.y >= -0.010
                or not (chest_z_min <= world_pos.z <= chest_z_max)
            ):
                continue
            world_normal = (nrm_mtx @ vtx.normal).normalized()
            if world_normal.y >= -0.15:
                continue

            best_sample = None
            best_dist = max_skin_dist
            for _cand_pos, cand_idx, cand_dist in kdtree_index.find_n(world_pos, 4):
                if cand_dist > best_dist:
                    continue
                sample_pos, sample_normal, sample_weights = skin_samples[cand_idx]
                if sample_normal.dot(world_normal) <= 0.20:
                    continue
                if abs(world_pos.x) < abs(sample_pos.x) - 0.025:
                    continue
                best_sample = (sample_pos, sample_normal, sample_weights)
                best_dist = cand_dist
                break

            if best_sample is None:
                continue

            sample_pos, sample_normal, sample_weights = best_sample
            edge_fade = min(1.0, max(0.0, (medial_limit - abs(world_pos.x)) / fade_span))
            if edge_fade <= 1e-4:
                continue

            cur_weights = _extract_vertex_weight_map(cloth_obj, vtx)
            arm_weight = sum(cur_weights.get(weight_bone_name, 0.0) for weight_bone_name in _TORSO_ARM_BONES)
            prox_blend = min(1.0, 0.70 + 0.30 * (1.0 - (best_dist / max_skin_dist)))
            blend_amt = edge_fade * prox_blend

            did_modify_vtx = False
            if arm_weight > 0.03:
                new_weights = {}
                for weight_bone_name, weight_val in cur_weights.items():
                    if weight_bone_name in _TORSO_ARM_BONES:
                        rem_val = weight_val * (1.0 - blend_amt)
                        if rem_val > 1e-5:
                            new_weights[weight_bone_name] = rem_val
                    else:
                        new_weights[weight_bone_name] = (weight_val * (1.0 - blend_amt))
                for weight_bone_name, sample_weight in sample_weights.items():
                    if weight_bone_name in _TORSO_ARM_BONES:
                        continue
                    new_weights[weight_bone_name] = new_weights.get(weight_bone_name, 0.0) + (sample_weight * blend_amt)
                _assign_vertex_weight_map(cloth_obj, vtx.index, new_weights)
                did_modify_vtx = True

            signed_clear = (world_pos - sample_pos).dot(sample_normal)
            req_clear = min_clearance * edge_fade
            if -0.004 <= signed_clear < req_clear:
                lift_vec = sample_normal * (req_clear - signed_clear)
                vtx.co = inv_mtx @ (world_pos + lift_vec)
                did_modify_vtx = True
                cloth_changed = True

            if did_modify_vtx:
                adjusted_count += 1

        if cloth_changed:
            cloth_data.update()

    return adjusted_count


