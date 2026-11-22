#!/usr/bin/env python3
"""
blender_hair_helper.py
======================
Shared Blender geometry, rigging, skull-fitting, UV sub-tile remapping, and
uint16 chunk-splitting utilities for importing arbitrary Unity / VRChat hairs
into GTA V RAGE ped builds (Michael, Franklin, and Trevor).
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import unity_hair_helper
import unity_scene_helper

SHINANO_DEFAULT_HAIR_MESHES = frozenset(
    {
        "hair_back",
        "hair_bang",
        "hair_base",
        "hair_side",
    }
)

MILTINA_DEFAULT_HAIR_MESHES = frozenset(
    {
        "milltina_hair_base",
        "milltina_hair_side",
        "milltina_hair_front",
        "milltina_hair_front_side",
        "milltina_hair_twintail",
        "milltina_cloth_hair_ribbon",
    }
)

DEFAULT_HAIR_CAP_CANDIDATES = frozenset(
    {
        "hair_base",
        "hair_back",
        "hair_bang",
        "hair_side",
        "milltina_hair_base",
        "milltina_hair_front",
        "milltina_hair_side",
    }
)

_HIP_TAIL_TOKENS = (
    "neko_tail",
    "cow_tail",
    "fox_tail",
    "cat_tail",
    "wolf_tail",
    "dog_tail",
    "animal_tail",
    "other_tail",
    "shippo",
)

_SCALP_MESH_TOKENS = (
    "base",
    "baase",
    "scalp",
    "cap",
    "back",
    "front",
    "bang",
    "top",
    "in hair",
    "in_hair",
)

_ACCENT_EXCLUDE_TOKENS = (
    "pin",
    "halo",
    "ribbon",
    "earring",
    "roller",
    "post",
    "twintail",
    "twin tail",
    "ponytail",
    "pony",
    "tail",
    "ahoge",
    "aho",
)


def strip_blender_numeric_suffix(object_name: str) -> str:
    """Remove Blender duplicate suffix such as '.001' for clean Unity name matching."""
    return re.sub(r"\.\d{3}$", "", object_name.strip())


def is_default_hair_mesh_name(mesh_name: str, avatar_kind: str = "") -> bool:
    """Return True when mesh_name belongs to an avatar's stock built-in hair."""
    lower_name = strip_blender_numeric_suffix(mesh_name).lower()
    lower_avatar = avatar_kind.strip().lower()
    if "miltina" in lower_avatar or "milltina" in lower_avatar:
        return lower_name in MILTINA_DEFAULT_HAIR_MESHES
    if "shinano" in lower_avatar:
        return lower_name in SHINANO_DEFAULT_HAIR_MESHES
    return lower_name in SHINANO_DEFAULT_HAIR_MESHES or lower_name in MILTINA_DEFAULT_HAIR_MESHES


def remove_default_hair_meshes(
    bpy_module: Any,
    avatar_kind: str,
    imported_hair_names: Sequence[str] = (),
    mesh_list_to_prune: Optional[List[Any]] = None,
    name_list_to_prune: Optional[List[str]] = None,
    remove_shinano_ears_if_replaced: bool = False,
) -> List[str]:
    """Remove stock avatar hair objects from Blender scene when custom or 'none' hair is active."""
    removed_names: List[str] = []
    imported_lower_blob = " ".join(name.lower() for name in imported_hair_names)
    targets = set(
        MILTINA_DEFAULT_HAIR_MESHES
        if "miltina" in avatar_kind.lower() or "milltina" in avatar_kind.lower()
        else SHINANO_DEFAULT_HAIR_MESHES
    )
    if (
        remove_shinano_ears_if_replaced
        and "shinano" in avatar_kind.lower()
        and any(tok in imported_lower_blob for tok in ("ear", "neko"))
    ):
        targets.add("other_ear")

    for obj_item in list(bpy_module.data.objects):
        if obj_item.type != "MESH":
            continue
        clean_lower = strip_blender_numeric_suffix(obj_item.name).lower()
        if clean_lower not in targets:
            continue
        removed_names.append(obj_item.name)
        if mesh_list_to_prune is not None and obj_item in mesh_list_to_prune:
            mesh_list_to_prune.remove(obj_item)
        if name_list_to_prune is not None and obj_item.name in name_list_to_prune:
            name_list_to_prune.remove(obj_item.name)
        bpy_module.data.objects.remove(obj_item, do_unlink=True)
    return removed_names


def _find_bone_insensitive(armature_obj: Any, candidate_names: Sequence[str]) -> Optional[Any]:
    """Locate a pose bone by exact or case-insensitive name match."""
    if armature_obj is None or not getattr(armature_obj, "pose", None):
        return None
    pose_bones = armature_obj.pose.bones
    for candidate in candidate_names:
        if candidate in pose_bones:
            return pose_bones[candidate]
    lower_lookup = {bone.name.lower(): bone for bone in pose_bones}
    for candidate in candidate_names:
        matched = lower_lookup.get(candidate.lower())
        if matched is not None:
            return matched
    return None


def _compute_mesh_world_bounds(
    bpy_module: Any,
    mesh_objects: Sequence[Any],
    z_min_filter: Optional[float] = None,
    xy_radius_limit: Optional[float] = None,
) -> Optional[Dict[str, float]]:
    """Compute world-space X/Y/Z extents over evaluated vertices inside optional cranial bounds."""
    depsgraph = bpy_module.context.evaluated_depsgraph_get()
    xs_vals: List[float] = []
    ys_vals: List[float] = []
    zs_vals: List[float] = []

    for mesh_obj in mesh_objects:
        if mesh_obj is None or mesh_obj.type != "MESH":
            continue
        eval_obj = mesh_obj.evaluated_get(depsgraph)
        temp_mesh = bpy_module.data.meshes.new_from_object(eval_obj)
        world_mtx = eval_obj.matrix_world
        try:
            for vert_item in temp_mesh.vertices:
                world_co = world_mtx @ vert_item.co
                if z_min_filter is not None and world_co.z < z_min_filter:
                    continue
                if xy_radius_limit is not None and (
                    abs(world_co.x) > xy_radius_limit or abs(world_co.y) > xy_radius_limit
                ):
                    continue
                xs_vals.append(float(world_co.x))
                ys_vals.append(float(world_co.y))
                zs_vals.append(float(world_co.z))
        finally:
            bpy_module.data.meshes.remove(temp_mesh)

    if not xs_vals:
        return None

    sorted_zs = sorted(zs_vals)
    p99_idx = min(len(sorted_zs) - 1, int(0.992 * (len(sorted_zs) - 1)))
    min_x, max_x = min(xs_vals), max(xs_vals)
    min_y, max_y = min(ys_vals), max(ys_vals)
    return {
        "min_x": min_x,
        "max_x": max_x,
        "width_x": max_x - min_x,
        "center_x": 0.5 * (min_x + max_x),
        "min_y": min_y,
        "max_y": max_y,
        "depth_y": max_y - min_y,
        "center_y": 0.5 * (min_y + max_y),
        "min_z": sorted_zs[0],
        "max_z": sorted_zs[-1],
        "crown_z": sorted_zs[p99_idx],
    }


def extract_skull_reference(
    bpy_module: Any,
    avatar_armature: Any,
    body_meshes: Sequence[Any],
    existing_hair_meshes: Sequence[Any] = (),
    head_bone_names: Sequence[str] = ("Head", "head"),
) -> Dict[str, Any]:
    """
    Measure the live target avatar's Head bone and cranial skull geometry BEFORE
    deleting default hair meshes so any custom hair fits regardless of avatar scale.
    """
    head_pose_bone = _find_bone_insensitive(avatar_armature, head_bone_names)
    if head_pose_bone is not None and avatar_armature is not None:
        head_world_mtx = avatar_armature.matrix_world @ head_pose_bone.matrix
        head_world_pos = avatar_armature.matrix_world @ head_pose_bone.head
        head_scale_vec = head_world_mtx.to_scale()
        head_world_scale_x = abs(float(head_scale_vec.x))
    else:
        head_world_pos = None
        head_world_scale_x = 1.0

    z_floor = (float(head_world_pos.z) - 0.015) if head_world_pos is not None else 0.90
    body_bounds = _compute_mesh_world_bounds(
        bpy_module,
        body_meshes,
        z_min_filter=z_floor,
        xy_radius_limit=0.18,
    )

    cap_candidates = [
        mesh_obj
        for mesh_obj in existing_hair_meshes
        if mesh_obj is not None
        and strip_blender_numeric_suffix(mesh_obj.name).lower() in DEFAULT_HAIR_CAP_CANDIDATES
    ]
    if not cap_candidates:
        cap_candidates = [
            mesh_obj
            for mesh_obj in existing_hair_meshes
            if mesh_obj is not None and "base" in mesh_obj.name.lower()
        ]
    default_cap_bounds = _compute_mesh_world_bounds(
        bpy_module,
        cap_candidates,
        z_min_filter=z_floor,
        xy_radius_limit=0.20,
    )

    skull_width_x = body_bounds["width_x"] if body_bounds else 0.165
    skull_center_x = body_bounds["center_x"] if body_bounds else (
        float(head_world_pos.x) if head_world_pos is not None else 0.0
    )
    skull_center_y = body_bounds["center_y"] if body_bounds else (
        float(head_world_pos.y) if head_world_pos is not None else 0.0
    )
    skull_zmax = body_bounds["max_z"] if body_bounds else (
        (float(head_world_pos.z) + 0.17) if head_world_pos is not None else 1.28
    )

    return {
        "head_world_pos": (
            (float(head_world_pos.x), float(head_world_pos.y), float(head_world_pos.z))
            if head_world_pos is not None
            else (0.0, 0.0, max(0.95, skull_zmax - 0.17))
        ),
        "head_world_scale_x": head_world_scale_x,
        "skull_width_x": skull_width_x,
        "skull_center_x": skull_center_x,
        "skull_center_y": skull_center_y,
        "skull_zmax": skull_zmax,
        "default_cap_width_x": (
            default_cap_bounds["width_x"] if default_cap_bounds else skull_width_x * 1.03
        ),
        "default_cap_center_y": (
            default_cap_bounds["center_y"] if default_cap_bounds else skull_center_y + 0.012
        ),
        "default_cap_crown_z": (
            default_cap_bounds["crown_z"] if default_cap_bounds else skull_zmax + 0.014
        ),
    }


def _is_suppressed_by_prefab(mesh_name: str, suppressed_lower_set: Set[str]) -> bool:
    """Return True when mesh_name matches an inactive or EditorOnly prefab entry."""
    raw_lower = mesh_name.strip().lower()
    clean_lower = strip_blender_numeric_suffix(mesh_name).lower()
    return raw_lower in suppressed_lower_set or clean_lower in suppressed_lower_set


def _is_hip_tail_not_hair_ponytail(
    bpy_module: Any,
    mesh_obj: Any,
    hair_spec: Dict[str, Any],
) -> bool:
    """
    Distinguish hip-attached animal tails (e.g. Neko_Tail / Other_tail) from valid hair
    ponytails or twintails (e.g. Kikyo_YureiHair 'tail', Chiffon_MG 'b03_twin tail').
    """
    lower_name = strip_blender_numeric_suffix(mesh_obj.name).lower()
    if "tail" not in lower_name:
        return False
    if any(hair_tok in lower_name for hair_tok in ("twintail", "twin tail", "ponytail", "pony tail", "pony_tail")):
        return False
    if any(animal_tok in lower_name for animal_tok in _HIP_TAIL_TOKENS):
        return True

    vgroup_names_lower = [vgrp.name.lower() for vgrp in mesh_obj.vertex_groups]
    if any(
        any(hair_tok in vg_name for hair_tok in ("hair", "twintail", "ponytail", "braid"))
        for vg_name in vgroup_names_lower
    ):
        return False

    mesh_root_bones = hair_spec.get("mesh_root_bones") or {}
    root_bone_name = str(mesh_root_bones.get(lower_name, "")).strip().lower()
    if root_bone_name in ("hair", "hair_root", "hair root", "head", "twintail", "ponytail"):
        return False

    # Inspect world Z height against Hip bone vs Head if armature vertices exist
    has_hip_group = any(
        vg_item in ("hips", "pelvis", "other_tail", "neko_tail", "cow_tail")
        for vg_item in vgroup_names_lower
    )
    if has_hip_group or root_bone_name in ("hips", "pelvis"):
        bounds = _compute_mesh_world_bounds(bpy_module, [mesh_obj])
        if bounds is not None and bounds["max_z"] < 1.05:
            return True
    return False


def _bake_object_modifiers_and_world(
    bpy_module: Any,
    mathutils_module: Any,
    mesh_obj: Any,
) -> None:
    """Bake active shape keys, armature modifiers, and world transform cleanly into mesh data."""
    world_matrix = mesh_obj.matrix_world.copy()
    bpy_module.context.view_layer.objects.active = mesh_obj
    if mesh_obj.data.shape_keys:
        bpy_module.ops.object.shape_key_remove(all=True, apply_mix=True)
    for mod_item in list(mesh_obj.modifiers):
        if mod_item.type == "ARMATURE":
            try:
                bpy_module.ops.object.modifier_apply(modifier=mod_item.name)
            except Exception:
                mesh_obj.modifiers.remove(mod_item)
    mesh_obj.parent = None
    mesh_obj.matrix_world = mathutils_module.Matrix.Identity(4)
    mesh_obj.data.transform(world_matrix)
    mesh_obj.data.update()


def _apply_blendshapes_to_custom_mesh(
    mesh_obj: Any,
    hair_spec: Dict[str, Any],
    resolved_mesh_weights: Optional[Dict[str, Dict[str, float]]] = None,
) -> None:
    """Apply Unity prefab or scene blendshape overrides onto an imported hair mesh before baking."""
    import blendshape_helper

    if not getattr(mesh_obj.data, "shape_keys", None):
        return

    clean_name = strip_blender_numeric_suffix(mesh_obj.name)
    combined_weights: Dict[str, float] = {}

    prefab_weights_map = hair_spec.get("blendshape_weights") or {}
    for candidate_key in (mesh_obj.name, clean_name):
        if candidate_key in prefab_weights_map:
            key_blocks = mesh_obj.data.shape_keys.key_blocks
            for bs_key, bs_val in prefab_weights_map[candidate_key].items():
                if bs_key.startswith("index:"):
                    idx_num = int(bs_key.split(":", 1)[1]) + 1  # key_blocks[0] is Basis
                    if 0 < idx_num < len(key_blocks):
                        combined_weights[key_blocks[idx_num].name] = float(bs_val)
                else:
                    combined_weights[bs_key] = float(bs_val)

    if resolved_mesh_weights:
        for candidate_key in (mesh_obj.name, clean_name):
            if candidate_key in resolved_mesh_weights:
                combined_weights.update(resolved_mesh_weights[candidate_key])

    if combined_weights:
        blendshape_helper.apply_blendshapes_to_blender_object(
            mesh_obj,
            combined_weights,
            reset_unlisted=True,
        )


def import_and_filter_custom_hair_meshes(
    bpy_module: Any,
    mathutils_module: Any,
    hair_spec: Dict[str, Any],
    unity_config: Optional[Dict[str, Any]] = None,
    resolved_mesh_weights: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """
    Import all FBXs resolved for a custom Unity hair, suppress inactive/EditorOnly/animal-tail
    objects, capture rest armature metrics, and return clean baked mesh objects.
    """
    fbx_list = list(hair_spec.get("all_fbxs") or [])
    if not fbx_list and hair_spec.get("primary_fbx"):
        fbx_list = [str(hair_spec["primary_fbx"])]

    suppressed_names = {
        strip_blender_numeric_suffix(item).lower()
        for item in (
            list(hair_spec.get("inactive_meshes") or [])
            + list(hair_spec.get("editor_only_meshes") or [])
        )
        if item
    }

    imported_meshes: List[Any] = []
    imported_armatures: List[Any] = []
    armature_head_pos: Optional[Tuple[float, float, float]] = None
    armature_head_scale_x: float = 1.0
    armature_hair_root_pos: Optional[Tuple[float, float, float]] = None
    armature_has_head_bone = False

    for fbx_str in fbx_list:
        if not fbx_str or not Path(fbx_str).is_file():
            continue
        pre_objects = set(bpy_module.data.objects)
        bpy_module.ops.import_scene.fbx(filepath=fbx_str, use_anim=False)
        new_objects = [obj for obj in bpy_module.data.objects if obj not in pre_objects]

        new_armatures = [obj for obj in new_objects if obj.type == "ARMATURE"]
        for hair_arm in new_armatures:
            imported_armatures.append(hair_arm)
            if unity_config and not hair_spec.get("is_neko_bob_calibrated"):
                unity_scene_helper.apply_unity_bone_scales_to_pose(hair_arm, unity_config)
            bpy_module.context.view_layer.update()

            head_bone = _find_bone_insensitive(hair_arm, ("Head", "head"))
            if head_bone is not None:
                armature_has_head_bone = True
                h_world = hair_arm.matrix_world @ head_bone.head
                h_mtx = hair_arm.matrix_world @ head_bone.matrix
                armature_head_pos = (float(h_world.x), float(h_world.y), float(h_world.z))
                armature_head_scale_x = abs(float(h_mtx.to_scale().x))

            root_bone = _find_bone_insensitive(
                hair_arm,
                ("Hair Root", "Hair_root", "HairRoot", "Lazy_Hair_Root", "Hair"),
            )
            if root_bone is not None:
                r_world = hair_arm.matrix_world @ root_bone.head
                armature_hair_root_pos = (float(r_world.x), float(r_world.y), float(r_world.z))

        for new_obj in new_objects:
            if new_obj.type == "ARMATURE":
                continue
            if new_obj.type != "MESH":
                bpy_module.data.objects.remove(new_obj, do_unlink=True)
                continue

            lower_obj_name = strip_blender_numeric_suffix(new_obj.name).lower()
            if (
                _is_suppressed_by_prefab(new_obj.name, suppressed_names)
                or any(tok in lower_obj_name for tok in ("collider", "dummy", "shadow_proxy"))
                or _is_hip_tail_not_hair_ponytail(bpy_module, new_obj, hair_spec)
            ):
                bpy_module.data.objects.remove(new_obj, do_unlink=True)
                continue

            _apply_blendshapes_to_custom_mesh(
                new_obj,
                hair_spec,
                resolved_mesh_weights=resolved_mesh_weights,
            )
            imported_meshes.append(new_obj)

    bpy_module.context.view_layer.update()
    if not hair_spec.get("is_neko_bob_calibrated"):
        for mesh_obj in imported_meshes:
            _bake_object_modifiers_and_world(bpy_module, mathutils_module, mesh_obj)
        for hair_arm in list(imported_armatures):
            if hair_arm.name in bpy_module.data.objects:
                bpy_module.data.objects.remove(hair_arm, do_unlink=True)
        imported_armatures.clear()

    return {
        "meshes": imported_meshes,
        "armatures": imported_armatures,
        "has_head_bone": armature_has_head_bone,
        "head_world_pos": armature_head_pos,
        "head_world_scale_x": armature_head_scale_x,
        "hair_root_world_pos": armature_hair_root_pos,
    }


def _estimate_hair_cap_bounds(
    bpy_module: Any,
    imported_meshes: Sequence[Any],
) -> Optional[Dict[str, float]]:
    """Measure the cranial scalp cap bounds across imported hair meshes, excluding tails/pins."""
    scalp_meshes = [
        mesh_obj
        for mesh_obj in imported_meshes
        if any(tok in mesh_obj.name.lower() for tok in _SCALP_MESH_TOKENS)
        and not any(tok in mesh_obj.name.lower() for tok in _ACCENT_EXCLUDE_TOKENS)
    ]
    target_meshes = scalp_meshes if scalp_meshes else list(imported_meshes)
    overall = _compute_mesh_world_bounds(bpy_module, target_meshes)
    if overall is None:
        return None

    # Measure width strictly in upper cranial band so flared long strands do not skew skull fit
    cranial_floor_z = overall["crown_z"] - 0.145
    upper_bounds = _compute_mesh_world_bounds(
        bpy_module,
        target_meshes,
        z_min_filter=cranial_floor_z,
        xy_radius_limit=0.22,
    )
    return upper_bounds or overall


def align_custom_hair_to_avatar(
    bpy_module: Any,
    mathutils_module: Any,
    imported_meshes: Sequence[Any],
    skull_ref: Dict[str, Any],
    hair_spec: Dict[str, Any],
    import_meta: Dict[str, Any],
    hair_scale_override: float = 1.0,
    hair_offset_override: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Dict[str, Any]:
    """
    Position and scale any baked Unity hair meshes cleanly onto the target avatar's skull
    before world-to-RAGE height scaling. Handles Head-rigged, Hair-only, and static hairs.
    """
    if not imported_meshes:
        return {"strategy": "empty", "applied_scale": 1.0}

    if hair_spec.get("is_neko_bob_calibrated"):
        return {"strategy": "er_calibrated_neko_bob", "applied_scale": 1.0}

    cap_bounds = _estimate_hair_cap_bounds(bpy_module, imported_meshes)
    if cap_bounds is None:
        return {"strategy": "no_vertices", "applied_scale": 1.0}

    transform_hint = hair_spec.get("transform_hint") or {}
    target_head = mathutils_module.Vector(skull_ref["head_world_pos"])
    user_offset = mathutils_module.Vector(hair_offset_override)

    has_head_bone = bool(
        import_meta.get("has_head_bone")
        and import_meta.get("head_world_pos") is not None
    )

    if has_head_bone:
        src_head = mathutils_module.Vector(import_meta["head_world_pos"])
        prefab_hair_root_scale = transform_hint.get("hair_root_local_scale") or [1.0, 1.0, 1.0]
        prefab_scale_val = max(
            0.5,
            min(
                2.0,
                (
                    float(prefab_hair_root_scale[0])
                    + float(prefab_hair_root_scale[1])
                    + float(prefab_hair_root_scale[2])
                )
                / 3.0,
            ),
        )
        src_head_scale = max(1e-4, float(import_meta.get("head_world_scale_x", 1.0)))
        avatar_head_scale = float(skull_ref.get("head_world_scale_x", 1.0)) / src_head_scale

        # Check whether hair was authored for a different avatar height (cross-avatar transfer)
        cross_avatar_scale = 1.0
        if abs(src_head.z - target_head.z) > 0.025:
            eff_cap_width = cap_bounds["width_x"] * prefab_scale_val * avatar_head_scale
            target_cap_width = float(skull_ref["skull_width_x"]) * 1.05
            if eff_cap_width > 1e-4:
                ratio = target_cap_width / eff_cap_width
                if abs(ratio - 1.0) > 0.05:
                    cross_avatar_scale = max(0.84, min(1.22, ratio))

        total_scale = prefab_scale_val * avatar_head_scale * cross_avatar_scale * float(hair_scale_override)
        pivot_src = src_head
        if abs(prefab_scale_val - 1.0) > 1e-4 and import_meta.get("hair_root_world_pos") is not None:
            pivot_src = mathutils_module.Vector(import_meta["hair_root_world_pos"])
        pivot_target = target_head + (pivot_src - src_head) * avatar_head_scale + user_offset
        strategy_name = "head_bone_align"
    else:
        # Standalone armature ('Hair' root only) or unrigged FBX: fit upper cranial cap to target skull
        target_cap_width = max(
            float(skull_ref["skull_width_x"]) * 1.05,
            float(skull_ref.get("default_cap_width_x", 0.0)) * 0.96,
        )
        raw_fit_ratio = target_cap_width / max(1e-4, cap_bounds["width_x"])
        clamped_fit_scale = max(0.78, min(1.28, raw_fit_ratio))
        total_scale = clamped_fit_scale * float(hair_scale_override)

        pivot_src = mathutils_module.Vector(
            (cap_bounds["center_x"], cap_bounds["center_y"], cap_bounds["crown_z"])
        )
        target_crown_z = max(
            float(skull_ref["skull_zmax"]) + 0.012,
            float(skull_ref.get("default_cap_crown_z", 0.0)),
        )
        target_center_y = float(
            skull_ref.get("default_cap_center_y", skull_ref["skull_center_y"] + 0.012)
        )
        pivot_target = (
            mathutils_module.Vector((skull_ref["skull_center_x"], target_center_y, target_crown_z))
            + user_offset
        )
        strategy_name = "cranial_cap_auto_fit"

    for mesh_obj in imported_meshes:
        for vert_item in mesh_obj.data.vertices:
            rel_vec = vert_item.co - pivot_src
            vert_item.co = pivot_target + (rel_vec * total_scale)
        mesh_obj.data.update()

    return {
        "strategy": strategy_name,
        "applied_scale": round(total_scale, 5),
        "pivot_target": [round(float(val), 5) for val in pivot_target],
    }


def remap_custom_hair_uvs(
    imported_meshes: Sequence[Any],
    manifest: Optional[Dict[str, Any]],
    fallback_rect: Tuple[float, float, float, float],
    target_uv_name: Optional[str] = "UVMap",
) -> None:
    """
    Remap UVs per polygon and material slot into the packed sub-tile rects stored in
    custom_hair_manifest.json, shifting each face by integer UDIM offsets safely so
    polygons straddling tile borders do not tear across the atlas. Also normalizes the
    UV layer name so Blender join() never splits UVs into a separate un-exported layer.
    """
    for mesh_obj in imported_meshes:
        mesh_data = getattr(mesh_obj, "data", None)
        if mesh_data is None or not mesh_data.uv_layers:
            continue
        uv_layer = mesh_data.uv_layers.active or mesh_data.uv_layers[0]
        clean_name = strip_blender_numeric_suffix(mesh_obj.name)
        slot_materials = list(mesh_data.materials)
        slot_count = max(1, len(slot_materials))

        resolved_rects: Dict[int, Tuple[float, float, float, float]] = {}
        for slot_idx in range(slot_count):
            mat_name = (
                slot_materials[slot_idx].name
                if slot_idx < len(slot_materials) and slot_materials[slot_idx]
                else ""
            )
            resolved_rects[slot_idx] = unity_hair_helper.resolve_tile_uv_for_mesh_slot(
                mesh_name=clean_name,
                slot_index=slot_idx,
                slot_count=slot_count,
                blender_mat_name=mat_name,
                manifest=manifest,
                fallback_rect=fallback_rect,
            )

        for poly_item in mesh_data.polygons:
            loop_indices = list(poly_item.loop_indices)
            if not loop_indices:
                continue
            rect_u0, rect_v0, rect_du, rect_dv = resolved_rects.get(
                poly_item.material_index, fallback_rect
            )

            u_sum = 0.0
            v_sum = 0.0
            for loop_idx in loop_indices:
                uv_vec = uv_layer.data[loop_idx].uv
                u_sum += float(uv_vec.x)
                v_sum += float(uv_vec.y)
            count_f = float(len(loop_indices))
            shift_u = float(math.floor(u_sum / count_f))
            shift_v = float(math.floor(v_sum / count_f))

            for loop_idx in loop_indices:
                uv_vec = uv_layer.data[loop_idx].uv
                local_u = max(0.001, min(0.999, float(uv_vec.x) - shift_u))
                local_v = max(0.001, min(0.999, float(uv_vec.y) - shift_v))
                uv_vec.x = rect_u0 + local_u * rect_du
                uv_vec.y = rect_v0 + local_v * rect_dv

        # Drop secondary UV channels and align primary name with Body before join()
        for extra_uv in list(mesh_data.uv_layers):
            if extra_uv != uv_layer:
                mesh_data.uv_layers.remove(extra_uv)
        if target_uv_name:
            uv_layer.name = target_uv_name


def retarget_custom_hair_weights_to_head(
    imported_meshes: Sequence[Any],
    target_bone: str = "SKEL_Head",
) -> None:
    """Bind all imported custom hair vertices 100% cleanly to target_bone (SKEL_Head)."""
    for mesh_obj in imported_meshes:
        mesh_data = getattr(mesh_obj, "data", None)
        if mesh_data is None:
            continue
        mesh_obj.vertex_groups.clear()
        head_group = mesh_obj.vertex_groups.new(name=target_bone)
        all_indices = [vert_item.index for vert_item in mesh_data.vertices]
        if all_indices:
            head_group.add(all_indices, 1.0, "REPLACE")


def split_oversized_material_geometries(
    mesh_object: Any,
    max_vertices_per_chunk: int = 30000,
    log_callback: Optional[Callable[[str, int, int], None]] = None,
) -> int:
    """
    Split any material group exceeding RAGE uint16 vertex safety thresholds into chunked
    duplicate material slots so dense Booth hair meshes export without vertex overflow.
    Returns count of additional chunk materials created.
    """
    mesh_data_elem = mesh_object.data
    polys_by_material: Dict[int, List[int]] = {}
    for poly_item in mesh_data_elem.polygons:
        polys_by_material.setdefault(poly_item.material_index, []).append(poly_item.index)

    max_polys_per_chunk = max(10000, int(max_vertices_per_chunk * 0.65))
    created_chunks = 0

    for mat_index, poly_indices in list(polys_by_material.items()):
        if len(poly_indices) <= max_polys_per_chunk:
            continue

        base_material = mesh_data_elem.materials[mat_index]
        chunk_total = math.ceil(len(poly_indices) / max_polys_per_chunk)
        if log_callback is not None:
            log_callback(base_material.name, len(poly_indices), chunk_total)

        sub_materials = [base_material]
        for chunk_idx in range(1, chunk_total):
            duplicated_mat = base_material.copy()
            duplicated_mat.name = f"{base_material.name}_chunk{chunk_idx}"
            mesh_data_elem.materials.append(duplicated_mat)
            sub_materials.append(duplicated_mat)
            created_chunks += 1

        for poly_seq, poly_idx in enumerate(poly_indices):
            chunk_assignment = poly_seq // max_polys_per_chunk
            target_mat = sub_materials[chunk_assignment]
            mesh_data_elem.polygons[poly_idx].material_index = mesh_data_elem.materials.find(
                target_mat.name
            )

    if created_chunks > 0:
        mesh_data_elem.update()
    return created_chunks


def parse_offset_triple(raw_offset: Optional[str]) -> Tuple[float, float, float]:
    """Parse 'x,y,z' hair offset string safely with zero fallback."""
    if not raw_offset or not str(raw_offset).strip():
        return (0.0, 0.0, 0.0)
    parts = [part.strip() for part in str(raw_offset).split(",") if part.strip()]
    if len(parts) != 3:
        return (0.0, 0.0, 0.0)
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError:
        return (0.0, 0.0, 0.0)


def duplicate_double_sided_backfaces(
    mesh_obj: Any,
    material_indices: Optional[Sequence[int]] = None,
    normal_offset: float = 0.00035,
) -> int:
    """Duplicate selected double-sided faces along smooth vertex normals with flipped winding."""
    import bmesh
    from mathutils import Vector

    mesh_data = getattr(mesh_obj, "data", None)
    if mesh_data is None or not getattr(mesh_data, "polygons", None):
        return 0
    target_set = {int(idx) for idx in material_indices} if material_indices is not None else None
    bmesh_mod = bmesh.new()
    bmesh_mod.from_mesh(mesh_data)
    bmesh_mod.faces.ensure_lookup_table()
    bmesh_mod.normal_update()
    src_faces = [
        face_item
        for face_item in list(bmesh_mod.faces)
        if target_set is None or int(face_item.material_index) in target_set
    ]
    if not src_faces:
        bmesh_mod.free()
        return 0
    dup_res = bmesh.ops.duplicate(bmesh_mod, geom=src_faces)
    dup_faces = [elem for elem in dup_res.get("geom", ()) if isinstance(elem, bmesh.types.BMFace)]
    if dup_faces:
        if normal_offset != 0.0:
            vert_norm_accum: Dict[Any, Vector] = {}
            vert_norm_fallback: Dict[Any, Vector] = {}
            for face_item in dup_faces:
                face_norm = face_item.normal
                for vert_item in face_item.verts:
                    if vert_item not in vert_norm_accum:
                        vert_norm_accum[vert_item] = Vector((0.0, 0.0, 0.0))
                        vert_norm_fallback[vert_item] = face_norm.copy()
                    vert_norm_accum[vert_item] += face_norm
            for vert_item, accum_vec in vert_norm_accum.items():
                if accum_vec.length_squared > 1e-12:
                    smooth_dir = accum_vec.normalized()
                else:
                    fallback_vec = vert_norm_fallback[vert_item]
                    smooth_dir = (
                        fallback_vec.normalized()
                        if fallback_vec.length_squared > 1e-12
                        else Vector((0.0, 0.0, 1.0))
                    )
                vert_item.co = vert_item.co - smooth_dir * float(normal_offset)
        bmesh.ops.reverse_faces(bmesh_mod, faces=dup_faces)
    bmesh_mod.to_mesh(mesh_data)
    bmesh_mod.free()
    mesh_data.update()
    return len(dup_faces)
