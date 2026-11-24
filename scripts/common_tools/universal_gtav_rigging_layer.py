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


def _select_main_fbx(
    scan_info: Dict[str, Any],
    ma_plan: Dict[str, Any],
    selected_prefab_or_scene: Optional[Path],
) -> Path:
    """Resolve the primary humanoid character FBX from MA plan or ingested files."""
    anchor_tokens: List[str] = []
    if selected_prefab_or_scene is not None:
        anchor_tokens.append(selected_prefab_or_scene.stem.lower())
    avatar_plan_name = str(ma_plan.get("avatar_name") or "").strip().lower()
    if avatar_plan_name:
        anchor_tokens.extend(tok for tok in avatar_plan_name.split() if len(tok) >= 3)
    anchor_tokens.append(Path(scan_info["unity_project_root"]).name.lower())

    def _score_fbx(fbx_file: Path) -> Tuple[int, int, int, int, int]:
        stem_low = fbx_file.stem.lower()
        in_loose = 1 if "_ziploosefbx" in str(fbx_file).lower() else 0
        is_accessory = 1 if any(
            tok in stem_low for tok in ("_for_", "wear", "dress", "outfit", "hair", "nail", "earring", "cloth")
        ) else 0
        has_kaihen = 1 if any(tok in stem_low for tok in ("kaihen", "alt", "quest")) else 0
        matches_name = 0 if any(tok in stem_low or stem_low in tok for tok in anchor_tokens if tok) else 1
        return (in_loose, is_accessory, has_kaihen, matches_name, -fbx_file.stat().st_size)

    plan_base_fbxs = [
        Path(fbx_item)
        for fbx_item in (ma_plan.get("base_fbx_paths") or ())
        if Path(fbx_item).is_file()
    ]
    if plan_base_fbxs:
        return sorted(plan_base_fbxs, key=_score_fbx)[0]

    fbx_candidates = [Path(item) for item in (scan_info.get("fbx_files") or ()) if Path(item).is_file()]
    if not fbx_candidates:
        raise FileNotFoundError("No FBX models found inside avatar workspace.")
    return sorted(fbx_candidates, key=_score_fbx)[0]


PROTAGONIST_VTOON_CHAR_IDS: Dict[str, int] = {
    "player_zero": 1,
    "player_one": 2,
    "player_two": 3,
}


def _pick_default_face_anim(
    scan_info: Dict[str, Any],
    avatar_hints: Sequence[str],
    fallback_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Locate a `default` resting facial `.anim` file without walking huge Unity trees."""
    anim_candidates = sorted(Path(pth) for pth in (scan_info.get("anim_files") or ()))
    if not anim_candidates and fallback_dir is not None and fallback_dir.is_dir():
        anim_candidates = sorted(fallback_dir.rglob("*.anim"))
    for anim_file in anim_candidates:
        low_name = anim_file.stem.lower()
        if "default" in low_name or "idle" in low_name:
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
    import vrc2gtav_paths as project_paths

    project_root = project_paths.get_project_root()
    norm_ped = npc_registry_helper.normalize_ped_model_name(target_ped)
    resolved_src = _resolve_source_path(source_spec, project_root)

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
    print(
        f"[3/4] Compiling {resolved_atlas_size}px GTA V Texture Atlas & .ytd "
        f"(VToon char_id={resolved_vtoon_id})...",
        flush=True,
    )
    textures_dir = Path(staging_info["textures_dir"])
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
    face_anim_path = (
        explicit_face_anim
        if (explicit_face_anim is not None and explicit_face_anim.is_file())
        else _pick_default_face_anim(scan_info, hints, fallback_dir=anim_search_dir)
    )
    if explicit_face_anim is not None and not explicit_face_anim.is_file():
        print(f"[Blendshapes] Requested --face-anim not found: {explicit_face_anim}", flush=True)
    elif explicit_face_anim is not None:
        print(f"[Blendshapes] Applying Face .anim override: {explicit_face_anim}", flush=True)
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

    saved_bs_cfg = blender_dir / f"{norm_ped}_blendshapes.cfg"
    saved_pb_cfg = blender_dir / f"{norm_ped}_physbones.cfg"

    active_face_mesh = next(
        (m_name for m_name in active_meshes if m_name.lower() == "body"),
        next(
            (
                m_name
                for m_name in active_meshes
                if any(tok in m_name.lower() for tok in ("face", "head", "body"))
            ),
            "Body",
        ),
    )
    bs_source_eff = str(blendshapes_source or ("unity" if selected_scene_or_prefab else "auto"))
    bs_cfg_host = str(project_paths.to_host_path(blendshapes_cfg)) if blendshapes_cfg else None
    pb_cfg_host = str(project_paths.to_host_path(physbones_cfg)) if physbones_cfg else None
    blendshape_res = blendshape_helper.resolve_character_blendshapes(
        char_pseudo_cfg,
        fbx_paths=[str(pth) for pth in all_fbxs],
        character_hints=hints,
        default_face_mesh=active_face_mesh,
        unity_assets_root=assets_root,
        override_source=bs_source_eff,
        override_cfg_path=bs_cfg_host or None,
        override_unity_scene=selected_scene_or_prefab,
        override_avatar_name=effective_avatar_name,
        override_face_anim=face_anim_path,
        save_cfg_path=saved_bs_cfg,
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

    ph_l = _head_z("PH_L_Foot")
    ph_r = _head_z("PH_R_Foot")
    foot_l = _head_z("SKEL_L_Foot")
    foot_r = _head_z("SKEL_R_Foot")
    head_z = _head_z("SKEL_Head")

    ground_vals = [val for val in (ph_l, ph_r) if val is not None]
    foot_vals = [val for val in (foot_l, foot_r) if val is not None]
    ground_z = sum(ground_vals) / len(ground_vals) if ground_vals else -1.0
    foot_z = sum(foot_vals) / len(foot_vals) if foot_vals else -0.908
    target_head_z = head_z if head_z is not None else 0.640

    arm_drop_deg = 55.0
    u_arm = data_bones.get("SKEL_L_UpperArm")
    f_arm = data_bones.get("SKEL_L_Forearm")
    if u_arm is not None and f_arm is not None:
        vec_arm = (arm_world @ f_arm.head_local) - (arm_world @ u_arm.head_local)
        horiz_len = max(1e-5, math.hypot(vec_arm.x, vec_arm.y))
        arm_drop_deg = max(35.0, min(68.0, math.degrees(math.atan2(-vec_arm.z, horiz_len))))

    return {
        "ground_z": ground_z,
        "foot_z": foot_z,
        "head_z": target_head_z,
        "arm_drop_deg": arm_drop_deg,
    }


def _pose_avatar_arms_to_gtav_a_pose(
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

    arm_mw = src_armature.matrix_world
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

        start_pt = arm_mw @ upper_pb.head
        end_pt = arm_mw @ lower_pb.head
        arm_vec = (end_pt - start_pt)
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
            parent_rot = (arm_mw.to_3x3() @ upper_pb.parent.matrix.to_3x3()).normalized()
        else:
            parent_rot = arm_mw.to_3x3().normalized()
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
    pb_bone_mapping_ci: Dict[str, str],
) -> str:
    """Resolve an arbitrary Unity bone weight name onto the GTA V + PhysBone skeleton."""
    import hand_skeleton_helper
    import modular_avatar_helper
    import physbone_helper

    low_name = str(raw_bone_name or "").strip().lower()
    if low_name in pb_bone_mapping_ci:
        return pb_bone_mapping_ci[low_name]
    space_alias = re.sub(r"\.(\d{3})$", lambda match_obj: f" {int(match_obj.group(1))}", low_name)
    if space_alias in pb_bone_mapping_ci:
        return pb_bone_mapping_ci[space_alias]

    direct_pb = physbone_helper.resolve_bone_from_mapping(
        raw_bone_name, bone_mapping_ci=pb_bone_mapping_ci
    )
    if direct_pb is not None:
        return direct_pb

    resolved_arm_finger = hand_skeleton_helper.resolve_finger_or_arm_bone(raw_bone_name)
    if resolved_arm_finger is not None:
        return resolved_arm_finger

    norm_key = modular_avatar_helper.normalize_bone_match_key(raw_bone_name)
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
    if norm_key in humanoid_table:
        return humanoid_table[norm_key]

    if "hair" in low_name or "ear" in low_name or "cheek" in low_name:
        return "SKEL_Head"
    if "breast" in low_name or "oppai" in low_name or "bust" in low_name or "ribbon" in low_name:
        return "SKEL_Spine2"
    if "skirt" in low_name or "tail" in low_name or "coat" in low_name:
        return "SKEL_Pelvis"
    if any(tok in mesh_name.lower() for tok in ("hair", "kemomimi", "ear", "head")):
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
                    pb_w = grp_elem.weight * 0.78
                    remapped[target_bone] = remapped.get(target_bone, 0.0) + pb_w
                    skirt_weight += grp_elem.weight * 0.22
                else:
                    skirt_weight += grp_elem.weight
            else:
                remapped[target_bone] = remapped.get(target_bone, 0.0) + grp_elem.weight

    if skirt_weight > 0.0:
        vert_z = max(0.0, min(1.0, (0.05 - float(ydd_coord.z)) / 0.14))
        thigh_cap = vert_z * 0.22
        thigh_w = skirt_weight * thigh_cap
        pelvis_w = skirt_weight - thigh_w
        if pelvis_w > 1e-6:
            remapped["SKEL_Pelvis"] = remapped.get("SKEL_Pelvis", 0.0) + pelvis_w
        side_mix = max(0.0, min(1.0, (float(ydd_coord.x) + 0.04) / 0.08))
        if thigh_w * side_mix > 1e-6:
            remapped["SKEL_L_Thigh"] = remapped.get("SKEL_L_Thigh", 0.0) + (thigh_w * side_mix)
        if thigh_w * (1.0 - side_mix) > 1e-6:
            remapped["SKEL_R_Thigh"] = remapped.get("SKEL_R_Thigh", 0.0) + (thigh_w * (1.0 - side_mix))

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

