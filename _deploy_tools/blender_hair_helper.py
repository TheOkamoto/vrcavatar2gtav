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
import struct
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import error_handler_helper as err_helper
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


_GENERIC_HAIR_MESH_TOKENS = frozenset(
    {"hair", "kami", "ahoge", "baasehair", "hairfront", "hairback", "hairside", "twintail", "ponytail", "bang", "bangs"}
)
_GENERIC_HAIR_BLOCK_TOKENS = frozenset(
    {"body", "face", "skin", "cloth", "dress", "shirt", "skirt", "pant", "panty", "bra", "shoe", "boot", "sock", "earring", "pin", "ribbon", "hat", "cap", "collar", "choker", "tail"}
)


def is_default_hair_mesh_name(mesh_name: str, avatar_kind: str = "") -> bool:
    """Return True when mesh_name belongs to an avatar's stock built-in hair."""
    lower_name = strip_blender_numeric_suffix(mesh_name).lower()
    lower_avatar = avatar_kind.strip().lower()
    if "miltina" in lower_avatar or "milltina" in lower_avatar:
        return lower_name in MILTINA_DEFAULT_HAIR_MESHES
    if "shinano" in lower_avatar:
        return lower_name in SHINANO_DEFAULT_HAIR_MESHES
    if lower_name in SHINANO_DEFAULT_HAIR_MESHES or lower_name in MILTINA_DEFAULT_HAIR_MESHES:
        return True
    name_tokens = set(tok for tok in re.split(r"[^a-z0-9]+", lower_name) if tok)
    if name_tokens & _GENERIC_HAIR_BLOCK_TOKENS:
        return False
    return bool(name_tokens & _GENERIC_HAIR_MESH_TOKENS) or lower_name in ("front", "back", "side", "baasehair")


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
    lower_avatar = avatar_kind.strip().lower()
    use_named_table = ("miltina" in lower_avatar or "milltina" in lower_avatar or "shinano" in lower_avatar)
    targets = set(
        MILTINA_DEFAULT_HAIR_MESHES
        if ("miltina" in lower_avatar or "milltina" in lower_avatar)
        else SHINANO_DEFAULT_HAIR_MESHES
    )
    if (
        remove_shinano_ears_if_replaced
        and "shinano" in lower_avatar
        and any(tok in imported_lower_blob for tok in ("ear", "neko"))
    ):
        targets.add("other_ear")

    for obj_item in list(bpy_module.data.objects):
        if obj_item.type != "MESH":
            continue
        clean_lower = strip_blender_numeric_suffix(obj_item.name).lower()
        is_match = (clean_lower in targets) if use_named_table else is_default_hair_mesh_name(obj_item.name, avatar_kind)
        if not is_match:
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
    planar_radius_limit: Optional[float] = None,
) -> Optional[Dict[str, float]]:
    """Compute world-space X/Y/Z extents over evaluated vertices inside optional cranial bounds."""
    depsgraph = bpy_module.context.evaluated_depsgraph_get()
    x_coord_vals: List[float] = []
    y_coord_vals: List[float] = []
    z_coord_vals: List[float] = []

    for mesh_obj in mesh_objects:
        if mesh_obj is None or mesh_obj.type != "MESH":
            continue
        eval_obj = mesh_obj.evaluated_get(depsgraph)
        temp_mesh = bpy_module.data.meshes.new_from_object(eval_obj)
        world_mtx = eval_obj.matrix_world
        try:
            for vert_item in temp_mesh.vertices:
                world_coord = world_mtx @ vert_item.co
                if z_min_filter is not None and world_coord.z < z_min_filter:
                    continue
                if planar_radius_limit is not None and (
                    abs(world_coord.x) > planar_radius_limit or abs(world_coord.y) > planar_radius_limit
                ):
                    continue
                x_coord_vals.append(float(world_coord.x))
                y_coord_vals.append(float(world_coord.y))
                z_coord_vals.append(float(world_coord.z))
        finally:
            bpy_module.data.meshes.remove(temp_mesh)

    if not x_coord_vals:
        return None

    sorted_z_values = sorted(z_coord_vals)
    p99_idx = min(len(sorted_z_values) - 1, int(0.992 * (len(sorted_z_values) - 1)))
    min_x, max_x = min(x_coord_vals), max(x_coord_vals)
    min_y, max_y = min(y_coord_vals), max(y_coord_vals)
    return {
        "min_x": min_x,
        "max_x": max_x,
        "width_x": max_x - min_x,
        "center_x": 0.5 * (min_x + max_x),
        "min_y": min_y,
        "max_y": max_y,
        "depth_y": max_y - min_y,
        "center_y": 0.5 * (min_y + max_y),
        "min_z": sorted_z_values[0],
        "max_z": sorted_z_values[-1],
        "crown_z": sorted_z_values[p99_idx],
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
        planar_radius_limit=0.18,
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
        planar_radius_limit=0.20,
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
        any(hair_tok in vgroup_name for hair_tok in ("hair", "twintail", "ponytail", "braid"))
        for vgroup_name in vgroup_names_lower
    ):
        return False

    mesh_root_bones = hair_spec.get("mesh_root_bones") or {}
    root_bone_name = str(mesh_root_bones.get(lower_name, "")).strip().lower()
    if root_bone_name in ("hair", "hair_root", "hair root", "head", "twintail", "ponytail"):
        return False

    # Inspect world Z height against Hip bone vs Head if armature vertices exist
    has_hip_group = any(
        vgroup_item in ("hips", "pelvis", "other_tail", "neko_tail", "cow_tail")
        for vgroup_item in vgroup_names_lower
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
            for blendshape_key, blendshape_val in prefab_weights_map[candidate_key].items():
                if blendshape_key.startswith("index:"):
                    idx_num = int(blendshape_key.split(":", 1)[1]) + 1  # key_blocks[0] is Basis
                    if 0 < idx_num < len(key_blocks):
                        combined_weights[key_blocks[idx_num].name] = float(blendshape_val)
                else:
                    combined_weights[blendshape_key] = float(blendshape_val)

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
        err_helper.import_fbx_safely(bpy_module, filepath=fbx_str, use_anim=False)
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
                head_world = hair_arm.matrix_world @ head_bone.head
                head_matrix = hair_arm.matrix_world @ head_bone.matrix
                armature_head_pos = (float(head_world.x), float(head_world.y), float(head_world.z))
                armature_head_scale_x = abs(float(head_matrix.to_scale().x))

            root_bone = _find_bone_insensitive(
                hair_arm,
                ("Hair Root", "Hair_root", "HairRoot", "Lazy_Hair_Root", "Hair"),
            )
            if root_bone is not None:
                root_world = hair_arm.matrix_world @ root_bone.head
                armature_hair_root_pos = (float(root_world.x), float(root_world.y), float(root_world.z))

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
        planar_radius_limit=0.22,
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
            rect_u0, rect_v0, rect_delta_u, rect_delta_v = resolved_rects.get(
                poly_item.material_index, fallback_rect
            )

            u_sum = 0.0
            v_sum = 0.0
            for loop_idx in loop_indices:
                uv_vec = uv_layer.data[loop_idx].uv
                u_sum += float(uv_vec.x)
                v_sum += float(uv_vec.y)
            count_float = float(len(loop_indices))
            shift_u = float(math.floor(u_sum / count_float))
            shift_v = float(math.floor(v_sum / count_float))

            for loop_idx in loop_indices:
                uv_vec = uv_layer.data[loop_idx].uv
                local_u = max(0.001, min(0.999, float(uv_vec.x) - shift_u))
                local_v = max(0.001, min(0.999, float(uv_vec.y) - shift_v))
                uv_vec.x = rect_u0 + local_u * rect_delta_u
                uv_vec.y = rect_v0 + local_v * rect_delta_v

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


def ensure_solid_rgba_dds(
    dds_path: Any,
    rgba_color: Tuple[int, int, int, int] = (128, 128, 255, 255),
    size: int = 32,
) -> Path:
    """
    Write a valid uncompressed A8R8G8B8 DX9 DDS file filled with a constant RGBA color.
    Matches `rage.exe textures encode -f rgba8 --mips 1` so Sollumz embeds exact
    neutral BumpSampler/SpecSampler data instead of 16x16 missing checkerboards.
    """
    out_path = Path(dds_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dim = max(4, int(size))
    red, green, blue, alpha = (max(0, min(255, int(chan))) for chan in rgba_color)
    pitch = dim * 4
    header = struct.pack(
        "<4s31I",
        b"DDS ",
        124,
        0x100F,
        dim,
        dim,
        pitch,
        1,
        1,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        32,
        0x41,
        0,
        32,
        0x00FF0000,
        0x0000FF00,
        0x000000FF,
        0xFF000000,
        0x1000,
        0, 0, 0, 0,
    )
    pixel_bytes = bytes((blue, green, red, alpha)) * (dim * dim)
    out_path.write_bytes(header + pixel_bytes)
    return out_path


def weld_symmetry_midline_seams(
    mesh_object: Any,
    midline_tol: float = 0.00045,
    match_dist: float = 0.0008,
    normal_cos_threshold: float = 0.7,
    respect_atlas_tiles: bool = False,
) -> int:
    """
    Weld open-boundary symmetry seam pairs along X=0 (caused by UV mirror cuts or
    decimation T-junctions) without merging opposite-normal double-sided shells.
    """
    import bmesh

    mesh_data = getattr(mesh_object, "data", None)
    if mesh_data is None or not getattr(mesh_data, "polygons", None):
        return 0

    bmesh_mod = bmesh.new()
    bmesh_mod.from_mesh(mesh_data)
    bmesh_mod.verts.ensure_lookup_table()
    bmesh_mod.edges.ensure_lookup_table()
    bmesh_mod.faces.ensure_lookup_table()
    bmesh_mod.normal_update()

    uv_layer = bmesh_mod.loops.layers.uv.active if respect_atlas_tiles else None
    candidates: List[Tuple[Any, int, int, int, Any]] = []
    for vert_item in bmesh_mod.verts:
        if abs(float(vert_item.co.x)) > midline_tol:
            continue
        if not any(edge_item.is_boundary for edge_item in vert_item.link_edges):
            continue
        if not vert_item.link_faces:
            continue
        mat_idx = int(vert_item.link_faces[0].material_index)
        uv_col, uv_row = -1, -1
        if uv_layer is not None:
            for loop_item in vert_item.link_loops:
                uv_val = loop_item[uv_layer].uv
                uv_col = max(0, min(3, int(float(uv_val.x) * 4.0)))
                uv_row = max(0, min(3, int(float(uv_val.y) * 4.0)))
                break
        candidates.append((vert_item, mat_idx, uv_col, uv_row, vert_item.normal.copy()))

    merge_verts: Set[Any] = set()
    used_verts: Set[int] = set()
    max_dist_squared = match_dist * match_dist
    cand_count = len(candidates)
    for idx_first in range(cand_count):
        vert_first, mat_first, color_first, row_first, norm_first = candidates[idx_first]
        if vert_first.index in used_verts:
            continue
        neighbors_first = {edge_item.other_vert(vert_first).index for edge_item in vert_first.link_edges}
        best_match = None
        best_dist_squared = max_dist_squared
        for idx_second in range(idx_first + 1, cand_count):
            vert_second, mat_second, color_second, row_second, norm_second = candidates[idx_second]
            if vert_second.index in used_verts or vert_second.index in neighbors_first:
                continue
            if mat_first != mat_second or (color_first >= 0 and (color_first != color_second or row_first != row_second)):
                continue
            if norm_first.dot(norm_second) < normal_cos_threshold:
                continue
            delta_vec = vert_first.co - vert_second.co
            dist_squared = float(delta_vec.length_squared)
            if dist_squared <= best_dist_squared:
                best_dist_squared = dist_squared
                best_match = vert_second
        if best_match is not None:
            mid_y = 0.5 * (float(vert_first.co.y) + float(best_match.co.y))
            mid_z = 0.5 * (float(vert_first.co.z) + float(best_match.co.z))
            vert_first.co.x = 0.0
            vert_first.co.y = mid_y
            vert_first.co.z = mid_z
            best_match.co.x = 0.0
            best_match.co.y = mid_y
            best_match.co.z = mid_z
            used_verts.add(vert_first.index)
            used_verts.add(best_match.index)
            merge_verts.add(vert_first)
            merge_verts.add(best_match)

    welded_pairs = len(used_verts) // 2
    if merge_verts:
        bmesh.ops.remove_doubles(bmesh_mod, verts=list(merge_verts), dist=1e-4)
        bmesh_mod.to_mesh(mesh_data)
        mesh_data.update()
    bmesh_mod.free()
    return welded_pairs


def configure_rpf7_decimate_modifier(
    decimate_mod: Any,
    obj_item: Any,
    ratio_val: float,
) -> float:
    """
    Configure Blender DECIMATE modifier to preserve X=0 symmetry and gently cap
    collapse on fitted upper-torso garments so skin poke-through/T-junctions stay minimal.
    """
    low_name = str(getattr(obj_item, "name", "") or "").lower()
    is_fitted_garment = any(
        tok in low_name
        for tok in ("sweat", "shirt", "corset", "top", "jersey", "dress", "bodysuit", "bra")
    )
    eff_ratio = max(0.80, float(ratio_val)) if is_fitted_garment else float(ratio_val)
    decimate_mod.decimate_type = "COLLAPSE"
    decimate_mod.ratio = eff_ratio
    if hasattr(decimate_mod, "use_symmetry"):
        decimate_mod.use_symmetry = True
    if hasattr(decimate_mod, "symmetry_axis"):
        decimate_mod.symmetry_axis = "X"
    return eff_ratio


_FITTED_TORSO_CLOTH_TOKENS = (
    "sweat",
    "shirt",
    "corset",
    "top",
    "jersey",
    "dress",
    "skirt",
    "bodysuit",
    "bra",
)


def rpf7_budget_priority_key(obj_item: Any) -> Tuple[int, int]:
    """
    Sort key (used with reverse=True) for RPF7 poly-budget decimation passes:
    defer fitted torso clothing (< 22k polys) behind heavy accessories/hair/large props.
    """
    low_name = str(getattr(obj_item, "name", "") or "").lower()
    mesh_data = getattr(obj_item, "data", None)
    poly_count = len(getattr(mesh_data, "polygons", ()) or ())
    is_small_fitted_torso = poly_count < 22000 and any(
        tok in low_name for tok in _FITTED_TORSO_CLOTH_TOKENS
    )
    return (0 if is_small_fitted_torso else 1, poly_count)


def is_protected_small_torso_cloth(obj_item: Any, already_trimmed: bool) -> bool:
    """Prevent iterative Pass-3 multi-round over-decimation on fitted torso garments."""
    if not already_trimmed:
        return False
    low_name = str(getattr(obj_item, "name", "") or "").lower()
    mesh_data = getattr(obj_item, "data", None)
    poly_count = len(getattr(mesh_data, "polygons", ()) or ())
    return poly_count < 22000 and any(
        tok in low_name for tok in _FITTED_TORSO_CLOTH_TOKENS
    )


def _partition_component_by_z_bands(
    comp_polys: List[int],
    poly_verts_map: Dict[int, Tuple[int, ...]],
    vertices_seq: Any,
    max_polys: int,
    max_verts: int,
    max_loops: int,
) -> List[List[int]]:
    """Subdivide an oversized connected island horizontally across Z bands (never down X=0)."""
    sort_items: List[Tuple[Tuple[float, float, float, int], int]] = []
    has_coord = bool(vertices_seq and hasattr(vertices_seq[0], "co"))
    for poly_idx in comp_polys:
        v_ids = poly_verts_map[poly_idx]
        if has_coord and v_ids:
            count_inv = 1.0 / float(len(v_ids))
            ctr_x = sum(float(vertices_seq[v_idx].co[0]) for v_idx in v_ids) * count_inv
            ctr_y = sum(float(vertices_seq[v_idx].co[1]) for v_idx in v_ids) * count_inv
            ctr_z = sum(float(vertices_seq[v_idx].co[2]) for v_idx in v_ids) * count_inv
            # Pair symmetric (-x, +x) polygons together at the exact same quantized Z ring
            sort_key = (round(ctr_z, 4), round(abs(ctr_x), 3), round(ctr_y, 3), poly_idx)
        else:
            sort_key = (0.0, 0.0, 0.0, poly_idx)
        sort_items.append((sort_key, poly_idx))
    sort_items.sort(key=lambda item: item[0])

    chunks: List[List[int]] = []
    cur_polys: List[int] = []
    cur_verts: Set[int] = set()
    cur_loops = 0
    for _, poly_idx in sort_items:
        v_ids = poly_verts_map[poly_idx]
        add_loops = max(3, len(v_ids))
        next_verts = cur_verts | set(v_ids)
        if cur_polys and (
            len(cur_polys) + 1 > max_polys
            or len(next_verts) > max_verts
            or cur_loops + add_loops > max_loops
        ):
            chunks.append(cur_polys)
            cur_polys = [poly_idx]
            cur_verts = set(v_ids)
            cur_loops = add_loops
        else:
            cur_polys.append(poly_idx)
            cur_verts = next_verts
            cur_loops += add_loops
    if cur_polys:
        chunks.append(cur_polys)
    return chunks


def split_oversized_material_geometries(
    mesh_object: Any,
    max_vertices_per_chunk: int = 30000,
    log_callback: Optional[Callable[[str, int, int], None]] = None,
) -> int:
    """
    Split any material group exceeding RAGE uint16 vertex/polygon thresholds into chunked
    duplicate material slots while keeping connected islands (and X=0 symmetry seams) intact.
    Returns count of additional chunk materials created.
    """
    mesh_data_elem = mesh_object.data
    polys_seq = mesh_data_elem.polygons
    verts_seq = getattr(mesh_data_elem, "vertices", ())
    polys_by_material: Dict[int, List[int]] = {}
    poly_verts_map: Dict[int, Tuple[int, ...]] = {}
    for poly_item in polys_seq:
        poly_index = poly_item.index
        polys_by_material.setdefault(poly_item.material_index, []).append(poly_index)
        poly_verts_map[poly_index] = tuple(int(v_idx) for v_idx in poly_item.vertices)

    max_polys_per_chunk = max(10000, min(19500, int(max_vertices_per_chunk * 0.65)))
    max_loops_per_chunk = 58000
    created_chunks = 0

    for mat_index, poly_indices in list(polys_by_material.items()):
        total_loops = sum(max(3, len(poly_verts_map[poly_item])) for poly_item in poly_indices)
        unique_mat_verts = {v_idx for poly_item in poly_indices for v_idx in poly_verts_map[poly_item]}
        if (
            len(poly_indices) <= max_polys_per_chunk
            and len(unique_mat_verts) <= max_vertices_per_chunk
            and total_loops <= max_loops_per_chunk
        ):
            continue

        # Discover connected islands within this material via shared vertex indices
        parent_map = {poly_item: poly_item for poly_item in poly_indices}
        vert_owner: Dict[int, int] = {}

        def _find_root(node_id: int) -> int:
            while parent_map[node_id] != node_id:
                parent_map[node_id] = parent_map[parent_map[node_id]]
                node_id = parent_map[node_id]
            return node_id

        for poly_item in poly_indices:
            for v_idx in poly_verts_map[poly_item]:
                first_poly_idx = vert_owner.get(v_idx)
                if first_poly_idx is None:
                    vert_owner[v_idx] = poly_item
                else:
                    root_first = _find_root(poly_item)
                    root_second = _find_root(first_poly_idx)
                    if root_first != root_second:
                        parent_map[root_second] = root_first

        islands_map: Dict[int, List[int]] = {}
        for poly_item in poly_indices:
            islands_map.setdefault(_find_root(poly_item), []).append(poly_item)

        units: List[Tuple[List[int], Set[int], int]] = []
        for comp_polys in islands_map.values():
            comp_verts = {v_idx for poly_item in comp_polys for v_idx in poly_verts_map[poly_item]}
            comp_loops = sum(max(3, len(poly_verts_map[poly_item])) for poly_item in comp_polys)
            if (
                len(comp_polys) <= max_polys_per_chunk
                and len(comp_verts) <= max_vertices_per_chunk
                and comp_loops <= max_loops_per_chunk
            ):
                units.append((comp_polys, comp_verts, comp_loops))
            else:
                for sub_polys in _partition_component_by_z_bands(
                    comp_polys,
                    poly_verts_map,
                    verts_seq,
                    max_polys_per_chunk,
                    max_vertices_per_chunk,
                    max_loops_per_chunk,
                ):
                    sub_verts = {v_idx for poly_item in sub_polys for v_idx in poly_verts_map[poly_item]}
                    sub_loops = sum(max(3, len(poly_verts_map[poly_item])) for poly_item in sub_polys)
                    units.append((sub_polys, sub_verts, sub_loops))

        # First-Fit-Decreasing bin packing keeps each connected component whole inside one chunk
        units.sort(key=lambda unit_item: (len(unit_item[0]), len(unit_item[1])), reverse=True)
        bins: List[Tuple[List[int], Set[int], int]] = []
        for unit_polys, unit_verts, unit_loops in units:
            placed = False
            for bin_idx, (bin_polys, bin_verts, bin_loops) in enumerate(bins):
                if len(bin_polys) + len(unit_polys) > max_polys_per_chunk:
                    continue
                if bin_loops + unit_loops > max_loops_per_chunk:
                    continue
                merged_verts = bin_verts | unit_verts
                if len(merged_verts) > max_vertices_per_chunk:
                    continue
                bin_polys.extend(unit_polys)
                bins[bin_idx] = (bin_polys, merged_verts, bin_loops + unit_loops)
                placed = True
                break
            if not placed:
                bins.append((list(unit_polys), set(unit_verts), unit_loops))

        chunk_total = len(bins)
        if chunk_total <= 1:
            continue

        base_material = mesh_data_elem.materials[mat_index]
        if log_callback is not None:
            log_callback(base_material.name, len(poly_indices), chunk_total)

        sub_materials = [base_material]
        for chunk_idx in range(1, chunk_total):
            duplicated_mat = base_material.copy()
            duplicated_mat.name = f"{base_material.name}_chunk{chunk_idx}"
            mesh_data_elem.materials.append(duplicated_mat)
            sub_materials.append(duplicated_mat)
            created_chunks += 1

        for chunk_idx, (bin_polys, _, _) in enumerate(bins):
            target_slot_idx = mesh_data_elem.materials.find(sub_materials[chunk_idx].name)
            for poly_idx in bin_polys:
                polys_seq[poly_idx].material_index = target_slot_idx

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


def _is_closed_thin_shell_face(
    bvh_tree: Any,
    face_item: Any,
    max_shell_thickness: float = 0.004,
) -> bool:
    """Return True when `face_item` already has an opposite-facing wall within thin shell thickness."""
    face_norm = face_item.normal
    if face_norm.length_squared <= 1e-12:
        return False
    face_center = face_item.calc_center_median()
    hit_loc, hit_norm, hit_idx, _hit_dist = bvh_tree.ray_cast(
        face_center - face_norm * 2e-5, -face_norm, float(max_shell_thickness)
    )
    if (
        hit_idx is not None
        and hit_idx != face_item.index
        and hit_norm is not None
        and hit_norm.dot(face_norm) < -0.35
    ):
        return True
    near_radius = min(0.0022, float(max_shell_thickness))
    for near_loc, near_norm, near_idx, _near_dist in bvh_tree.find_nearest_range(
        face_center - face_norm * 0.0008, near_radius
    ):
        if near_idx == face_item.index or near_norm is None:
            continue
        if near_norm.dot(face_norm) < -0.35 and (near_loc - face_center).dot(face_norm) < -1e-5:
            return True
    return False


def duplicate_double_sided_backfaces(
    mesh_obj: Any,
    material_indices: Optional[Sequence[int]] = None,
    normal_offset: float = 0.00012,
    skip_closed_shell: bool = True,
    max_shell_thickness: float = 0.004,
    exclude_polys: Optional[set[int]] = None,
) -> int:
    """Duplicate open single-sided backfaces with flipped winding, skipping closed double-walled geometry."""
    import bmesh
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    mesh_data = getattr(mesh_obj, "data", None)
    if mesh_data is None or not getattr(mesh_data, "polygons", None):
        return 0
    target_set = {int(idx) for idx in material_indices} if material_indices is not None else None
    bmesh_mod = bmesh.new()
    bmesh_mod.from_mesh(mesh_data)
    bmesh_mod.faces.ensure_lookup_table()
    bmesh_mod.faces.index_update()
    bmesh_mod.normal_update()
    excluded = exclude_polys or set()
    raw_src_faces = [
        face_item
        for face_item in list(bmesh_mod.faces)
        if int(face_item.index) not in excluded and (target_set is None or int(face_item.material_index) in target_set)
    ]
    if not raw_src_faces:
        bmesh_mod.free()
        return 0
    if skip_closed_shell:
        bvh_tree = BVHTree.FromBMesh(bmesh_mod, epsilon=1e-6)
        src_faces = [
            face_item
            for face_item in raw_src_faces
            if not _is_closed_thin_shell_face(
                bvh_tree, face_item, max_shell_thickness=max_shell_thickness
            )
        ]
    else:
        src_faces = raw_src_faces
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


_NON_SKIN_ROLE_TOKENS = frozenset(
    {
        "hair", "kami", "eyelash", "eyebrow", "lash", "brow", "iris", "cornea",
        "pupil", "teeth", "tooth", "tongue", "mouth", "nail", "cloth", "outfit",
        "dress", "shirt", "pant", "panty", "panties", "short", "shorts", "skirt",
        "bra", "bikini", "underwear", "sock", "socks", "stocking", "stockings",
        "tight", "tights", "shoe", "shoes", "boot", "boots", "heel", "heels",
        "slipper", "slippers", "hoodie", "jacket", "coat", "cape", "apron",
        "choker", "collar", "ribbon", "bow", "tie", "belt", "strap", "bag",
        "watch", "metal", "silver", "gold", "pin", "halo", "glasses", "megane",
        "hat", "beret", "ear", "ears", "tail", "horn", "wing", "pearl",
        "headset", "alpha", "overlay", "boxer", "boxerpants",
    }
)


def is_face_mesh_or_material_candidate(
    mesh_obj: Any,
    strip_suffix_func: Optional[Callable[[str], str]] = None,
) -> bool:
    """Return True only when a mesh represents a face/head asset that may carry custom anime face normals."""
    raw_name = str(getattr(mesh_obj, "name", mesh_obj) or "").strip()
    clean_name = strip_suffix_func(raw_name).lower() if strip_suffix_func else strip_blender_numeric_suffix(raw_name)
    name_tokens = {tok for tok in re.split(r"[^a-z0-9]+", clean_name) if tok}
    if clean_name in ("face", "head", "kao") or bool(name_tokens & {"face", "head", "kao"}):
        return True

    mesh_data = getattr(mesh_obj, "data", None)
    for mat_slot in getattr(mesh_data, "materials", ()) or ():
        if mat_slot is None:
            continue
        mat_name = str(getattr(mat_slot, "name", "") or "").lower()
        mat_u_name = str(mat_slot.get("vrc2gtav_mat_name", "") or "").lower() if hasattr(mat_slot, "get") else ""
        for mat_label in (mat_name, mat_u_name):
            if ("face" in mat_label or "kao" in mat_label) and "alpha" not in mat_label:
                return True

    shape_keys = getattr(mesh_data, "shape_keys", None)
    key_blocks = getattr(shape_keys, "key_blocks", ()) or ()
    for key_item in key_blocks:
        low_key = str(getattr(key_item, "name", "") or "").lower()
        if any(tok in low_key for tok in ("vrc.v_", "wink", "blink", "eye_close", "mabataki")):
            return True
    return False


def classify_skin_material_role(
    mat_name: str,
    source_obj_name: str = "",
    diffuse_src: str = "",
    alpha_mode: str = "opaque",
    is_skin_source_obj: Optional[bool] = None,
) -> str:
    """Classify a material slot generically into `'face'`, `'body_skin'`, or `'other'`."""
    low_mat = str(mat_name or "").strip().lower()
    low_obj = strip_blender_numeric_suffix(str(source_obj_name or "").strip())
    low_tex = Path(str(diffuse_src or "").strip()).stem.lower() if diffuse_src else ""

    is_face_overlay = any(
        tok in low_mat
        for tok in ("eyelash", "eyebrow", "highlight", "cornea", "alpha", "blush", "cheek", "tear", "decal", "overlay", "mask", "glasses", "lens", "chain")
    )
    if ("face" in low_mat or low_mat in ("head", "kao") or "face" in low_tex) and not is_face_overlay:
        return "face"

    if str(alpha_mode or "opaque").lower() != "opaque":
        return "other"

    mat_tokens = {tok for tok in re.split(r"[^a-z0-9]+", low_mat) if tok}
    tex_tokens = {tok for tok in re.split(r"[^a-z0-9]+", low_tex) if tok}
    if mat_tokens & _NON_SKIN_ROLE_TOKENS:
        return "other"
    if any(tok in low_mat for tok in ("hair", "cloth", "hoodie", "pant", "boxer", "headset", "shoe", "slipper", "choker", "collar", "alpha")):
        return "other"

    if (
        "body" in mat_tokens
        or "skin" in mat_tokens
        or "hada" in mat_tokens
        or "karada" in mat_tokens
        or "body" in tex_tokens
        or "skin" in tex_tokens
        or "_body" in low_mat
        or "_body" in low_tex
    ):
        return "body_skin"

    if is_skin_source_obj:
        return "body_skin"
    if low_obj and is_skin_source_obj is None:
        obj_tokens = {tok for tok in re.split(r"[^a-z0-9]+", low_obj) if tok}
        if (low_obj in ("body", "body_base", "skin") or low_obj.startswith("body_baked")) and not (obj_tokens & _NON_SKIN_ROLE_TOKENS):
            return "body_skin"
    return "other"


def compute_smooth_neck_skin_normal(
    vert_pos: Sequence[float],
    smooth_vert_norm: Sequence[float],
    neck_pos: Sequence[float],
    head_pos: Sequence[float],
) -> Tuple[float, float, float]:
    """Blend smooth neck skin normals smoothly into forward anime neck normals without hard seams."""
    neck_span = max(0.06, float(head_pos[2]) - float(neck_pos[2]))
    z_low = float(neck_pos[2]) - 0.05 * neck_span
    z_high = float(head_pos[2]) + 0.25 * neck_span
    side_limit = max(0.065, 0.60 * neck_span)
    depth_limit = float(head_pos[1]) + max(0.025, 0.25 * neck_span)

    if (
        float(vert_pos[2]) < z_low
        or float(vert_pos[2]) > z_high
        or float(vert_pos[1]) >= depth_limit
        or abs(float(vert_pos[0])) >= side_limit
    ):
        return (float(smooth_vert_norm[0]), float(smooth_vert_norm[1]), float(smooth_vert_norm[2]))

    fade_z_span = max(1e-4, 0.35 * neck_span)
    param_z = min(1.0, max(0.0, (float(vert_pos[2]) - z_low) / fade_z_span))
    weight_z = param_z * param_z * (3.0 - 2.0 * param_z)

    side_core = side_limit * 0.65
    weight_x = 1.0 - min(1.0, max(0.0, (abs(float(vert_pos[0])) - side_core) / max(1e-4, side_limit - side_core)))
    depth_core = float(head_pos[1]) + 0.005 * (neck_span / 0.11)
    weight_y = 1.0 - min(1.0, max(0.0, (float(vert_pos[1]) - depth_core) / max(1e-4, depth_limit - depth_core)))
    blend_weight = weight_z * weight_x * weight_y
    if blend_weight <= 1e-4:
        return (float(smooth_vert_norm[0]), float(smooth_vert_norm[1]), float(smooth_vert_norm[2]))

    scale_x = 3.5 * (0.11 / neck_span)
    raw_x = float(vert_pos[0]) * scale_x
    raw_y = -1.0
    raw_z = -0.08
    target_len = math.sqrt(raw_x * raw_x + raw_y * raw_y + raw_z * raw_z) or 1.0
    target_x = raw_x / target_len
    target_y = raw_y / target_len
    target_z = raw_z / target_len

    inv_weight = 1.0 - blend_weight
    blend_x = inv_weight * float(smooth_vert_norm[0]) + blend_weight * target_x
    blend_y = inv_weight * float(smooth_vert_norm[1]) + blend_weight * target_y
    blend_z = inv_weight * float(smooth_vert_norm[2]) + blend_weight * target_z
    blend_len = math.sqrt(blend_x * blend_x + blend_y * blend_y + blend_z * blend_z) or 1.0
    return (blend_x / blend_len, blend_y / blend_len, blend_z / blend_len)


def apply_face_and_neck_split_normals(
    mesh_obj: Any,
    armature_obj: Any,
    poly_roles: Sequence[str],
) -> Dict[str, int]:
    """
    Apply spherical anime face normals and smooth blended neck normals dynamically anchored to
    `SKEL_Head` / `SKEL_Neck_1`, while resetting non-face loops from smooth vertex normals so
    corrupted FBX custom split normals on body meshes never cause creases under RAGE shaders.
    """
    head_bone = armature_obj.data.bones["SKEL_Head"]
    head_world = (armature_obj.matrix_world @ head_bone.head_local).copy()
    neck_bone = armature_obj.data.bones.get("SKEL_Neck_1")
    if neck_bone is not None:
        neck_world = (armature_obj.matrix_world @ neck_bone.head_local).copy()
        neck_pos = (float(neck_world.x), float(neck_world.y), float(neck_world.z))
    else:
        neck_pos = (float(head_world.x), float(head_world.y) + 0.025, float(head_world.z) - 0.11)
    head_pos = (float(head_world.x), float(head_world.y), float(head_world.z))
    neck_span = max(0.06, head_pos[2] - neck_pos[2])

    mesh_data = mesh_obj.data
    mesh_data.calc_normals_split()
    custom_normals = [tuple(loop_item.normal) for loop_item in mesh_data.loops]
    mesh_verts = mesh_data.vertices
    mesh_loops = mesh_data.loops
    face_loops = 0
    neck_loops = 0
    reset_loops = 0

    face_side_lim = max(0.095, 0.86 * neck_span)
    face_depth_lim = head_pos[1] + max(0.025, 0.23 * neck_span)
    face_center_z = head_pos[2] + 0.45 * neck_span

    for poly_seq_idx, poly_item in enumerate(mesh_data.polygons):
        role = poly_roles[poly_seq_idx] if poly_seq_idx < len(poly_roles) else "other"
        if role == "face":
            for loop_idx in poly_item.loop_indices:
                vpos = mesh_verts[mesh_loops[loop_idx].vertex_index].co
                if vpos.y < face_depth_lim and abs(vpos.x) < face_side_lim:
                    norm_x = vpos.x * 2.2
                    norm_y = -1.0
                    norm_z = (vpos.z - face_center_z) * 1.4
                    norm_len = math.sqrt(norm_x * norm_x + norm_y * norm_y + norm_z * norm_z) or 1.0
                    custom_normals[loop_idx] = (norm_x / norm_len, norm_y / norm_len, norm_z / norm_len)
                    face_loops += 1
            continue

        is_body_skin = role == "body_skin"
        is_hair_alpha = role == "hair_alpha"
        for loop_idx in poly_item.loop_indices:
            vert_item = mesh_verts[mesh_loops[loop_idx].vertex_index]
            smooth_norm = (float(vert_item.normal.x), float(vert_item.normal.y), float(vert_item.normal.z))
            reset_loops += 1
            if is_body_skin:
                vpos = vert_item.co
                blended = compute_smooth_neck_skin_normal(
                    (float(vpos.x), float(vpos.y), float(vpos.z)),
                    smooth_norm,
                    neck_pos,
                    head_pos,
                )
                if blended != smooth_norm:
                    neck_loops += 1
                custom_normals[loop_idx] = blended
            elif is_hair_alpha:
                if smooth_norm[2] < -0.35:
                    lift_weight = min(1.0, (-0.35 - smooth_norm[2]) / 0.65)
                    mix_x = smooth_norm[0]
                    mix_y = smooth_norm[1] - 0.35 * lift_weight
                    mix_z = smooth_norm[2] + (-0.25 - smooth_norm[2]) * lift_weight
                    mix_len = math.sqrt(mix_x * mix_x + mix_y * mix_y + mix_z * mix_z) or 1.0
                    custom_normals[loop_idx] = (mix_x / mix_len, mix_y / mix_len, mix_z / mix_len)
                else:
                    custom_normals[loop_idx] = smooth_norm
            else:
                custom_normals[loop_idx] = smooth_norm

    mesh_data.normals_split_custom_set(custom_normals)
    mesh_data.update()
    return {
        "face_loops": face_loops,
        "neck_loops": neck_loops,
        "reset_loops": reset_loops,
    }


def sample_uv_min_alpha(
    uv_pairs: Sequence[Tuple[float, float]],
    alpha_grid: Any,
    grid_width: int,
    grid_height: int,
) -> float:
    """Return the minimum alpha in [0..1] across triangle corners, edge midpoints, and centroid."""
    if not uv_pairs or grid_width <= 0 or grid_height <= 0:
        return 1.0
    sample_points: List[Tuple[float, float]] = list(uv_pairs)
    vert_count = len(uv_pairs)
    if vert_count >= 2:
        for pair_idx in range(vert_count):
            next_idx = (pair_idx + 1) % vert_count
            sample_points.append((
                0.5 * (uv_pairs[pair_idx][0] + uv_pairs[next_idx][0]),
                0.5 * (uv_pairs[pair_idx][1] + uv_pairs[next_idx][1]),
            ))
        avg_u = sum(pair[0] for pair in uv_pairs) / float(vert_count)
        avg_v = sum(pair[1] for pair in uv_pairs) / float(vert_count)
        sample_points.append((avg_u, avg_v))

    min_alpha = 1.0
    for u_val, v_val in sample_points:
        clamped_u = max(0.0, min(1.0, float(u_val)))
        clamped_v = max(0.0, min(1.0, float(v_val)))
        px_x = max(0, min(grid_width - 1, int(round(clamped_u * float(grid_width - 1)))))
        px_y = max(0, min(grid_height - 1, int(round(clamped_v * float(grid_height - 1)))))
        sampled = float(alpha_grid[px_y][px_x])
        if sampled < min_alpha:
            min_alpha = sampled
    return min_alpha


def resolve_translucent_polygons_by_atlas_alpha(
    mesh_obj: Any,
    atlas_image: Any,
    target_slot_indices: Sequence[int],
    alpha_threshold: float = 0.98,
) -> set[int]:
    """Identify polygons in `target_slot_indices` whose baked atlas UVs touch alpha < `alpha_threshold`."""
    import numpy as numpy_mod

    mesh_data = getattr(mesh_obj, "data", None)
    slot_set = {int(slot_idx) for slot_idx in target_slot_indices}
    if (
        mesh_data is None
        or atlas_image is None
        or not slot_set
        or not getattr(mesh_data, "uv_layers", None)
    ):
        return set()
    img_width, img_height = int(atlas_image.size[0]), int(atlas_image.size[1])
    if img_width <= 0 or img_height <= 0:
        return set()
    pixel_arr = numpy_mod.array(atlas_image.pixels[:], dtype=numpy_mod.float32)
    alpha_grid = pixel_arr.reshape((img_height, img_width, 4))[..., 3]
    uv_layer = mesh_data.uv_layers[0]
    uv_data = uv_layer.data

    translucent_indices: set[int] = set()
    for poly_seq_idx, poly_item in enumerate(mesh_data.polygons):
        if int(poly_item.material_index) not in slot_set:
            continue
        poly_uvs = [
            (float(uv_data[loop_idx].uv.x), float(uv_data[loop_idx].uv.y))
            for loop_idx in poly_item.loop_indices
        ]
        if sample_uv_min_alpha(poly_uvs, alpha_grid, img_width, img_height) < float(alpha_threshold):
            translucent_indices.add(poly_seq_idx)
    return translucent_indices


def apply_atlas_uv_and_alpha_routing(
    joined_mesh_obj: Any,
    slot_regions: Dict[int, Dict[str, Any]],
    slot_roles: Dict[int, str],
    double_sided_slots: Sequence[int],
    transparent_orig_slots: set[int],
    alpha_shader_mat: Any,
    atlas_img: Any,
    default_region: Dict[str, Any],
) -> List[str]:
    """Pack slot UVs, duplicate non-translucent-hair double-sided sheets, and route translucent UVs to ped_alpha."""
    unique_mats, mat_ptr_to_idx, slot_remap = [], {}, {}
    for old_idx, mat_ref in enumerate(list(joined_mesh_obj.data.materials)):
        mat_key_name = mat_ref.name if mat_ref is not None else ""
        if mat_key_name not in mat_ptr_to_idx:
            mat_ptr_to_idx[mat_key_name] = len(unique_mats)
            unique_mats.append(mat_ref)
        slot_remap[old_idx] = mat_ptr_to_idx[mat_key_name]
    uv_layer = joined_mesh_obj.data.uv_layers[0]
    uv_layer.name = "UVMap 0"
    for poly_item in joined_mesh_obj.data.polygons:
        reg_spec = slot_regions.get(int(poly_item.material_index), default_region)
        off_u, off_v = float(reg_spec["u_offset"]), float(reg_spec["v_offset"])
        scl_u, scl_v = float(reg_spec["u_scale"]), float(reg_spec["v_scale"])
        for loop_idx in poly_item.loop_indices:
            uv_coord = uv_layer.data[loop_idx].uv
            local_u = max(0.001, min(0.999, uv_coord.x % 1.0 if (uv_coord.x < 0.0 or uv_coord.x > 1.0) else uv_coord.x))
            local_v = max(0.001, min(0.999, uv_coord.y % 1.0 if (uv_coord.y < 0.0 or uv_coord.y > 1.0) else uv_coord.y))
            uv_coord.x = local_u * scl_u + off_u
            uv_coord.y = local_v * scl_v + off_v
    if double_sided_slots:
        exclude_hair_trans: set[int] = set()
        if transparent_orig_slots and alpha_shader_mat is not None:
            pre_trans = resolve_translucent_polygons_by_atlas_alpha(
                joined_mesh_obj, atlas_img, sorted(transparent_orig_slots), alpha_threshold=0.995
            )
            exclude_hair_trans = {
                idx for idx in pre_trans
                if slot_roles.get(int(joined_mesh_obj.data.polygons[idx].material_index), "other") not in ("body_skin", "face")
            }
        dup_faces = duplicate_double_sided_backfaces(
            joined_mesh_obj, material_indices=double_sided_slots, normal_offset=0.00012, exclude_polys=exclude_hair_trans
        )
        print(f"[VToon] Duplicated {dup_faces} open-sheet double-sided faces for slots {double_sided_slots}", flush=True)
    poly_count = len(joined_mesh_obj.data.polygons)
    poly_orig_slots = [int(poly_item.material_index) for poly_item in joined_mesh_obj.data.polygons]
    poly_roles = [slot_roles.get(orig_slot, "other") for orig_slot in poly_orig_slots]
    translucent_poly_set: set[int] = set()
    if transparent_orig_slots and alpha_shader_mat is not None:
        translucent_poly_set = resolve_translucent_polygons_by_atlas_alpha(
            joined_mesh_obj, atlas_img, sorted(transparent_orig_slots), alpha_threshold=0.995
        )
        for poly_seq_idx in translucent_poly_set:
            if poly_seq_idx < len(poly_roles) and poly_roles[poly_seq_idx] not in ("body_skin", "face"):
                poly_roles[poly_seq_idx] = "hair_alpha"
        opaque_kept = sum(
            1 for poly_seq_idx, orig_slot in enumerate(poly_orig_slots)
            if orig_slot in transparent_orig_slots and poly_seq_idx not in translucent_poly_set
        )
        print(f"[VToon] Routed {len(translucent_poly_set)} translucent UV polygons to ped_alpha.sps (kept {opaque_kept} opaque polygons on ped_default).", flush=True)
    alpha_shader_slot_idx = -1
    if translucent_poly_set and alpha_shader_mat is not None:
        alpha_shader_slot_idx = len(unique_mats)
        unique_mats.append(alpha_shader_mat)
    joined_mesh_obj.data.materials.clear()
    for unique_mat in unique_mats:
        joined_mesh_obj.data.materials.append(unique_mat)
    for poly_seq_idx, poly_item in enumerate(joined_mesh_obj.data.polygons):
        poly_item.material_index = (
            alpha_shader_slot_idx if (poly_seq_idx in translucent_poly_set and alpha_shader_slot_idx >= 0)
            else slot_remap.get(poly_orig_slots[poly_seq_idx], 0)
        )
    return poly_roles
