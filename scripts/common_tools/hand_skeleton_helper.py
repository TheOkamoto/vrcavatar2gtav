#!/usr/bin/env python3
"""
hand_skeleton_helper.py
=======================
Utilitario compartilhado para rigagem 1:1 de dedos e realocacao de esqueletos
(.ydd no Blender e .yft via PyMateria) nos tres protagonistas do GTA V.

Garante que:
  1. Os 30 ossos de dedos (SKEL_{L,R}_Finger{0..4}{0..2}) e ossos auxiliares
     de torcao/pulso (RB_{L,R}_ForeArmRoll, RB_{L,R}_ArmRoll, PH/IK_{L,R}_Hand)
     sejam mapeados individualmente em vez de serem colapsados no pulso.
  2. Os ossos da armature do drawable (.ydd) e do fragmento (.yft) sejam
     movidos em paralelo para as posicoes exatas dos membros/dedos do avatar
     VRChat na A-pose, preservando as rotacoes locais nativas das animacoes .ycd.
"""

from pathlib import Path
from typing import Dict, Optional, Tuple


# Ossos auxiliares de braco/pulso preservados alem da lista basica do esqueleto
EXTRA_ARM_HELPER_BONES = (
    "RB_L_ArmRoll",
    "RB_R_ArmRoll",
    "RB_L_ForeArmRoll",
    "RB_R_ForeArmRoll",
    "PH_L_Hand",
    "PH_R_Hand",
    "IK_L_Hand",
    "IK_R_Hand",
)

# Todos os 30 ossos canonicos de dedos no GTA V
GTAV_FINGER_BONE_NAMES = tuple(
    f"SKEL_{side_tag}_Finger{finger_idx}{segment_idx}"
    for side_tag in ("L", "R")
    for finger_idx in range(5)
    for segment_idx in range(3)
)

# Candidatos de nomes de ossos VRChat (Shinano, ER e Milltina) para cada alvo GTA V
VRC_ARM_HAND_BONE_CANDIDATES: Dict[str, Tuple[str, ...]] = {
    "SKEL_L_Clavicle": ("Shoulder.L", "Shoulder_L", "LeftShoulder"),
    "SKEL_L_UpperArm": ("Upper_arm.L", "Upper_arm_L", "UpperArm.L", "LeftUpperArm"),
    "SKEL_L_Forearm": ("Lower_arm.L", "Lower_arm_L", "LowerArm.L", "LeftLowerArm"),
    "SKEL_L_Hand": ("Hand.L", "Hand_L", "LeftHand"),
    "SKEL_R_Clavicle": ("Shoulder.R", "Shoulder_R", "RightShoulder"),
    "SKEL_R_UpperArm": ("Upper_arm.R", "Upper_arm_R", "UpperArm.R", "RightUpperArm"),
    "SKEL_R_Forearm": ("Lower_arm.R", "Lower_arm_R", "LowerArm.R", "RightLowerArm"),
    "SKEL_R_Hand": ("Hand.R", "Hand_R", "RightHand"),
}

_FINGER_NAME_BY_INDEX = ("Thumb", "Index", "Middle", "Ring", "Little")
_SEGMENT_NAME_BY_INDEX = ("Proximal", "Intermediate", "Distal")

for _side_code, _humanoid_side in (("L", "Left"), ("R", "Right")):
    for _finger_idx, _finger_label in enumerate(_FINGER_NAME_BY_INDEX):
        for _seg_idx, _seg_label in enumerate(_SEGMENT_NAME_BY_INDEX):
            _gtav_finger_name = f"SKEL_{_side_code}_Finger{_finger_idx}{_seg_idx}"
            VRC_ARM_HAND_BONE_CANDIDATES[_gtav_finger_name] = (
                f"{_finger_label} {_seg_label}.{_side_code}",
                f"{_finger_label} {_seg_label}_{_side_code}",
                f"{_finger_label}_{_seg_label}.{_side_code}",
                f"{_finger_label}_{_seg_label}_{_side_code}",
                f"{_humanoid_side}{_finger_label}{_seg_label}",
                f"{_humanoid_side} {_finger_label} {_seg_label}",
            )


def detect_bone_side_code(bone_name: str) -> Optional[str]:
    """Detecta o lado anatomico ('L' ou 'R') a partir de convensoes Blender/Unity."""
    lower_name = bone_name.lower()
    if (
        bone_name.endswith(".L")
        or bone_name.endswith("_L")
        or "_l_" in lower_name
        or "left" in lower_name
    ):
        return "L"
    if (
        bone_name.endswith(".R")
        or bone_name.endswith("_R")
        or "_r_" in lower_name
        or "right" in lower_name
    ):
        return "R"
    return None


def resolve_finger_or_arm_bone(source_bone_name: str) -> Optional[str]:
    """
    Mapeia nomes de ossos de dedos e suporte/torcao de braco (Shinano/Miltina/VRChat)
    para seus equivalentes exatos no esqueleto do GTA V.

    Retorna None caso o osso nao seja de dedo ou suporte de braco, permitindo
    que a tabela/regra especifica do personagem trate o restante sem regressao.
    """
    if source_bone_name in GTAV_FINGER_BONE_NAMES or source_bone_name in EXTRA_ARM_HELPER_BONES:
        return source_bone_name

    side_code = detect_bone_side_code(source_bone_name)
    if side_code is None:
        return None

    lower_name = source_bone_name.lower()

    # 1. Suportes e torcoes de antebraco/braco/roupa
    if (
        "lower_arm_twist" in lower_name
        or "lower_arm_cloth_twist" in lower_name
        or "lower_arm_support" in lower_name
        or "forearm_twist" in lower_name
        or "forearm_roll" in lower_name
    ):
        return f"RB_{side_code}_ForeArmRoll"

    if (
        "upper_arm_twist" in lower_name
        or "upper_arm_cloth_twist" in lower_name
        or "upper_arm_support" in lower_name
        or "upperarm_twist" in lower_name
        or "upperarm_roll" in lower_name
    ):
        return f"RB_{side_code}_ArmRoll"

    if "costume_support2" in lower_name:
        return f"SKEL_{side_code}_Forearm"
    if "costume_support1" in lower_name or "costume_support3" in lower_name:
        return f"SKEL_{side_code}_UpperArm"

    # 2. Mapeamento 1:1 para os 30 ossos canonicos de dedos (SKEL_{L,R}_Finger{0..4}{0..2})
    finger_keywords = (
        ("thumb", 0),
        ("index", 1),
        ("middle", 2),
        ("ring", 3),
        ("little", 4),
        ("pinky", 4),
    )
    matched_finger_idx = None
    for keyword_token, finger_idx in finger_keywords:
        if keyword_token in lower_name:
            matched_finger_idx = finger_idx
            break

    if matched_finger_idx is None:
        return None

    if "proximal" in lower_name or "1" in lower_name:
        segment_idx = 0
    elif "intermediate" in lower_name or "2" in lower_name:
        segment_idx = 1
    elif "distal" in lower_name or "3" in lower_name:
        segment_idx = 2
    else:
        return None

    return f"SKEL_{side_code}_Finger{matched_finger_idx}{segment_idx}"


def extract_avatar_arm_hand_targets(
    fbx_armature_obj,
    scale_factor: float,
    z_offset: float,
    world_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Dict[str, "mathutils.Vector"]:
    """
    Extrai as posicoes mundiais pos-pose (-55 graus) dos ossos de clavicula, braco,
    antebraco, pulso e 30 dedos da armature VRChat convertidas para o espaco GTA V.
    """
    import bpy
    import mathutils

    if fbx_armature_obj is None or fbx_armature_obj.type != "ARMATURE":
        raise ValueError("Armature VRChat invalida ao extrair alvos de ossos das maos.")

    bpy.context.view_layer.update()

    arm_world_matrix = fbx_armature_obj.matrix_world
    offset_vector = mathutils.Vector(world_offset)
    bone_world_targets: Dict[str, mathutils.Vector] = {}

    for gtav_bone_name, candidate_names in VRC_ARM_HAND_BONE_CANDIDATES.items():
        matched_pose_bone = None
        for candidate_name in candidate_names:
            matched_pose_bone = fbx_armature_obj.pose.bones.get(candidate_name)
            if matched_pose_bone is not None:
                break
        if matched_pose_bone is None:
            continue

        raw_world_point = arm_world_matrix @ matched_pose_bone.head
        shifted_point = raw_world_point + offset_vector
        bone_world_targets[gtav_bone_name] = mathutils.Vector(
            (
                shifted_point.x * scale_factor,
                shifted_point.y * scale_factor,
                shifted_point.z * scale_factor + z_offset,
            )
        )

    required_main_bones = (
        "SKEL_L_Clavicle",
        "SKEL_L_UpperArm",
        "SKEL_L_Forearm",
        "SKEL_L_Hand",
        "SKEL_R_Clavicle",
        "SKEL_R_UpperArm",
        "SKEL_R_Forearm",
        "SKEL_R_Hand",
    )
    missing_main_bones = [
        bone_name for bone_name in required_main_bones if bone_name not in bone_world_targets
    ]
    missing_finger_bones = [
        bone_name for bone_name in GTAV_FINGER_BONE_NAMES if bone_name not in bone_world_targets
    ]
    if missing_main_bones or missing_finger_bones:
        raise RuntimeError(
            "Ossos obrigatorios ausentes ao extrair alvos da armature VRChat: "
            f"principais={missing_main_bones}, dedos={missing_finger_bones}"
        )

    # Calcula ossos auxiliares de torcao (50%) e acopladores de mao (PH/IK)
    for side_code in ("L", "R"):
        upper_arm_pos = bone_world_targets[f"SKEL_{side_code}_UpperArm"]
        forearm_pos = bone_world_targets[f"SKEL_{side_code}_Forearm"]
        hand_pos = bone_world_targets[f"SKEL_{side_code}_Hand"]

        bone_world_targets[f"RB_{side_code}_ArmRoll"] = upper_arm_pos.lerp(forearm_pos, 0.5)
        bone_world_targets[f"RB_{side_code}_ForeArmRoll"] = forearm_pos.lerp(hand_pos, 0.5)
        bone_world_targets[f"PH_{side_code}_Hand"] = hand_pos.copy()
        bone_world_targets[f"IK_{side_code}_Hand"] = hand_pos.copy()

    return bone_world_targets


def relocate_blender_armature_bones(
    ped_armature_obj,
    bone_world_targets: Dict[str, "mathutils.Vector"],
) -> int:
    """
    Translada as articulacoes (head/tail em paralelo) dos membros superiores e dedos
    da armature GTA V no Blender mantendo a orientacao/roll nativos intactos.
    """
    import bpy
    import mathutils

    if ped_armature_obj is None or ped_armature_obj.type != "ARMATURE":
        raise ValueError("Armature GTA V invalida para realocacao de ossos.")

    bpy.context.view_layer.objects.active = ped_armature_obj
    if ped_armature_obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.mode_set(mode="EDIT")

    arm_world_matrix = ped_armature_obj.matrix_world
    arm_world_inverse = arm_world_matrix.inverted()
    zero_delta = mathutils.Vector((0.0, 0.0, 0.0))
    relocated_counter = 0

    def walk_edit_bone(
        edit_bone_item,
        parent_delta_world: mathutils.Vector,
        inside_arm_subtree: bool,
    ) -> None:
        nonlocal relocated_counter
        current_subtree_flag = inside_arm_subtree or edit_bone_item.name in (
            "SKEL_L_Clavicle",
            "SKEL_R_Clavicle",
        )
        old_world_head = arm_world_matrix @ edit_bone_item.head
        tail_offset_local = (edit_bone_item.tail - edit_bone_item.head).copy()

        if edit_bone_item.name in bone_world_targets:
            new_world_head = bone_world_targets[edit_bone_item.name]
        elif current_subtree_flag:
            new_world_head = old_world_head + parent_delta_world
        else:
            new_world_head = old_world_head

        bone_delta_world = new_world_head - old_world_head
        if bone_delta_world.length > 1e-6:
            edit_bone_item.head = arm_world_inverse @ new_world_head
            edit_bone_item.tail = edit_bone_item.head + tail_offset_local
            relocated_counter += 1

        # Salva referencia de filhos antes da recursao
        child_edit_bones = list(edit_bone_item.children)
        for child_edit_bone in child_edit_bones:
            walk_edit_bone(child_edit_bone, bone_delta_world, current_subtree_flag)

    root_edit_bones = [
        edit_bone_item
        for edit_bone_item in ped_armature_obj.data.edit_bones
        if edit_bone_item.parent is None
    ]
    for root_edit_bone in root_edit_bones:
        walk_edit_bone(root_edit_bone, zero_delta, False)

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()
    return relocated_counter


def _build_bone_local_matrix(bone_node, translation_vec) -> "mathutils.Matrix":
    """Constroi matriz local 4x4 a partir de default_translation, default_rotation e default_scale."""
    import mathutils

    rot_raw = bone_node.default_rotation
    scale_raw = bone_node.default_scale
    quat_val = mathutils.Quaternion(
        (float(rot_raw.w), float(rot_raw.x), float(rot_raw.y), float(rot_raw.z))
    )
    rot_matrix = quat_val.to_matrix().to_4x4()
    scale_matrix = mathutils.Matrix.Diagonal(
        (float(scale_raw.x), float(scale_raw.y), float(scale_raw.z), 1.0)
    )
    trans_matrix = mathutils.Matrix.Translation(translation_vec)
    return trans_matrix @ rot_matrix @ scale_matrix


def patch_yft_skeleton(
    source_yft_path: Path,
    output_yft_path: Path,
    bone_world_targets: Dict[str, "mathutils.Vector"],
) -> Tuple[int, int, float]:
    """
    Atualiza `default_translation` no esqueleto do arquivo .yft via PyMateria,
    mantendo rotacoes e escalas originais e propagando deltas para filhos nao
    mapeados dentro das cadeias SKEL_L_Clavicle e SKEL_R_Clavicle.

    Tambem reimporta o .yft gerado para validar round-trip exato dos alvos.
    """
    import mathutils
    import pymateria as pymateria_root
    import pymateria.gta5.gen8 as gen8_module

    resolved_source = Path(source_yft_path)
    resolved_output = Path(output_yft_path)
    if not resolved_source.is_file():
        raise FileNotFoundError(
            f"Arquivo .yft de origem nao encontrado: {resolved_source}"
        )

    fragment_asset = gen8_module.Fragment.import_rsc(str(resolved_source)).result
    if fragment_asset is None or fragment_asset.drawable is None:
        raise RuntimeError(f"Fragmento sem drawable valido em: {resolved_source}")
    skeleton_obj = fragment_asset.drawable.skeleton
    if skeleton_obj is None or skeleton_obj.root_bone is None:
        raise RuntimeError(f"Fragmento sem esqueleto valido em: {resolved_source}")

    updated_bones_count = 0
    total_bones_count = 0
    identity_matrix = mathutils.Matrix.Identity(4)
    zero_delta = mathutils.Vector((0.0, 0.0, 0.0))

    def walk_yft_bone(
        bone_node,
        old_parent_world: mathutils.Matrix,
        new_parent_world: mathutils.Matrix,
        parent_delta_world: mathutils.Vector,
        inside_arm_subtree: bool,
    ) -> None:
        nonlocal updated_bones_count, total_bones_count
        total_bones_count += 1
        current_subtree_flag = inside_arm_subtree or bone_node.name in (
            "SKEL_L_Clavicle",
            "SKEL_R_Clavicle",
        )

        old_trans_raw = bone_node.default_translation
        old_local_trans = mathutils.Vector(
            (float(old_trans_raw.x), float(old_trans_raw.y), float(old_trans_raw.z))
        )
        old_local_matrix = _build_bone_local_matrix(bone_node, old_local_trans)
        old_world_matrix = old_parent_world @ old_local_matrix
        old_world_pos = old_world_matrix.translation.copy()

        if bone_node.name in bone_world_targets:
            target_point = bone_world_targets[bone_node.name]
            new_world_pos = mathutils.Vector(
                (float(target_point.x), float(target_point.y), float(target_point.z))
            )
        elif current_subtree_flag:
            new_world_pos = old_world_pos + parent_delta_world
        else:
            new_world_pos = old_world_pos

        delta_world = new_world_pos - old_world_pos
        new_local_trans = new_parent_world.inverted() @ new_world_pos
        if delta_world.length > 1e-6:
            bone_node.default_translation = pymateria_root.Vector4f(
                float(new_local_trans.x),
                float(new_local_trans.y),
                float(new_local_trans.z),
                float(old_trans_raw.w),
            )
            updated_bones_count += 1

        new_local_matrix = _build_bone_local_matrix(bone_node, new_local_trans)
        new_world_matrix = new_parent_world @ new_local_matrix

        for child_bone_node in bone_node.children:
            walk_yft_bone(
                child_bone_node,
                old_world_matrix,
                new_world_matrix,
                delta_world,
                current_subtree_flag,
            )

    walk_yft_bone(
        skeleton_obj.root_bone,
        identity_matrix,
        identity_matrix,
        zero_delta,
        False,
    )

    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    gen8_module.Fragment.export_rsc(fragment_asset, str(resolved_output))

    # Validacao round-trip apos exportacao binaria
    verify_fragment = gen8_module.Fragment.import_rsc(str(resolved_output)).result
    verify_positions: Dict[str, mathutils.Vector] = {}

    def collect_verified_positions(bone_node, parent_world: mathutils.Matrix) -> None:
        trans_raw = bone_node.default_translation
        local_trans = mathutils.Vector(
            (float(trans_raw.x), float(trans_raw.y), float(trans_raw.z))
        )
        world_matrix = parent_world @ _build_bone_local_matrix(bone_node, local_trans)
        verify_positions[bone_node.name] = world_matrix.translation.copy()
        for child_bone_node in bone_node.children:
            collect_verified_positions(child_bone_node, world_matrix)

    collect_verified_positions(
        verify_fragment.drawable.skeleton.root_bone, identity_matrix
    )

    max_roundtrip_error = 0.0
    for bone_name, expected_vec in bone_world_targets.items():
        if bone_name not in verify_positions:
            raise RuntimeError(
                f"Osso alvo '{bone_name}' desapareceu apos exportar {resolved_output}."
            )
        target_vec = mathutils.Vector(
            (float(expected_vec.x), float(expected_vec.y), float(expected_vec.z))
        )
        diff_len = (verify_positions[bone_name] - target_vec).length
        if diff_len > max_roundtrip_error:
            max_roundtrip_error = diff_len

    if max_roundtrip_error > 1e-3:
        raise RuntimeError(
            f"Erro de round-trip excessivo ao validar {resolved_output.name}: "
            f"{max_roundtrip_error:.6f} m"
        )

    return updated_bones_count, total_bones_count, max_roundtrip_error
