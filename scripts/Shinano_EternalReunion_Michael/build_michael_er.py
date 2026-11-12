#!/usr/bin/env python3
"""
build_avatar_gtav_pivate_ER.py
==============================
Script executado via Blender 4.0+ (modo background) com addon Sollumz 2.9.0
para compilar a Shinano Eternal Reunion completa (acessorios, cabelo custom
CooniBob e relogio de bolso) como componente superior (uppr) para o Michael
(player_zero) no GTA V Legacy (RAGE Engine GEN8).

Caracteristicas Tecnicas e Regras RAGE Engine:
  1. Suporte Multi-FBX:
     - Shinano Base: Body (rosto/olhos) e Body_base (corpo humano)
     - Eternal Reunion: UN1 (camisa, saia, laco, choker), UN2 (corset, boina, sapatos, meias),
       UN3 (bolsa, oculos, corrente de cintura)
     - Pocket Watch: Relogio de bolso funcional
     - CooniBob: Cabelo curto customizado com orelhas (CooniBob_Bang, Back, Side, Dog Ears, ACC)
  2. Remocao estrita de itens inativos / EditorOnly da hierarquia do Unity:
     - Roupas intimas (Cloth_under_bra, Cloth_under_shorts) excluidas
     - Cabelo padrao desabilitado excluido
     - Cauda CooniBob_Tail excluida
     - Variante UN1_Shirt_Summer e UN4_ChestRibbon 2 excluidas
  3. Shrink Culling e Blendshapes:
     - Ativa Corset=1.0 em Body_base e deleta faces do corpo ocultas sob a roupa
     - Ativa Breasts_big=1.0 (busto conforme referencia) e Toe_heels=1.0
     - Aplica 64 blendshapes faciais de ShinanoDefAdultNewv5.anim no Body
  4. Mapeamento Universal de Ossos (Modular Avatar Bake):
     - Todos os ossos de saia, bolsa, correntes, relogio e cabelo sao assados
       diretamente nos 55 ossos validos do esqueleto do Michael (player_zero.yft)
  5. Texture Atlas 4x2 Unificado com Shader ped_default.sps:
     - UVs remapeadas para as 7 celulas da imagem 4096x2048
     - Sem sobreposicao de texturas, sem efeito camuflado, sem tela preta
  6. Auto-Chunking de Geometrias (< 30.000 vertices):
     - Divide sub-geometrias densas em slots adicionais para respeitar o limite uint16 (65.535)
"""

import argparse
import json
import math
import os
import re
import struct
import sys
import zlib
from pathlib import Path

import addon_utils
import bmesh
import bpy

# Configura sys.path para localizar vrc2gtav_paths independentemente de espelho
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_CANDIDATE = _SCRIPT_DIR.parent.parent
for _tools_candidate in (
    _REPO_ROOT_CANDIDATE / "scripts" / "common_tools",
    _REPO_ROOT_CANDIDATE / "_deploy_tools",
):
    if _tools_candidate.is_dir() and str(_tools_candidate) not in sys.path:
        sys.path.insert(0, str(_tools_candidate))

import vrc2gtav_paths as project_paths
import mathutils


# ---------------------------------------------------------------------------
# Perfis dos personagens do GTA V Legacy
# ---------------------------------------------------------------------------
CHARACTER_PROFILES = {
    "michael": {
        "ped_name": "player_zero",
        "skeleton_yft": "player_zero.yft",
        "export_drawables": ["uppr_000_r", "uppr_000_u", "uppr_001_u", "uppr_004_u"],
        "target_z_min": -0.907,
        "target_z_max": 0.645,
        "arm_pose_degrees": -55.0,
    },
    "franklin": {
        "ped_name": "player_one",
        "skeleton_yft": "player_one.yft",
        "export_drawables": ["uppr_008_u", "uppr_000_u", "uppr_001_u"],
        "target_z_min": -0.907,
        "target_z_max": 0.640,
        "arm_pose_degrees": -55.0,
    },
    "trevor": {
        "ped_name": "player_two",
        "skeleton_yft": "player_two.yft",
        "export_drawables": ["uppr_000_r", "uppr_000_u", "uppr_001_u"],
        "target_z_min": -0.907,
        "target_z_max": 0.645,
        "arm_pose_degrees": -55.0,
    },
}


# ---------------------------------------------------------------------------
# Leitor autonomo de arquivos Unity .anim (YAML) para blendshapes faciais
# ---------------------------------------------------------------------------
def load_unity_anim_blendshapes(anim_file_path):
    blendshape_weights = {}
    if not anim_file_path or not os.path.exists(anim_file_path):
        return blendshape_weights

    with open(anim_file_path, "r", encoding="utf-8", errors="ignore") as anim_file:
        anim_text = anim_file.read()

    curve_blocks = anim_text.split("  - serializedVersion: 2")
    for block_text in curve_blocks[1:]:
        val_match = re.search(r"value:\s*([-\d.]+)", block_text)
        attr_match = re.search(r"attribute:\s*([^\n]+)", block_text)
        path_match = re.search(r"path:\s*([^\n]+)", block_text)
        if val_match and attr_match and path_match:
            raw_value = float(val_match.group(1))
            attr_text = attr_match.group(1).strip()
            shape_name = attr_text.replace("blendShape.", "").strip()
            if shape_name.startswith('"'):
                try:
                    shape_name = json.loads(shape_name)
                except Exception:
                    shape_name = shape_name.strip('"')
            if abs(raw_value) > 1e-4:
                blendshape_weights[shape_name] = raw_value / 100.0
            else:
                blendshape_weights[shape_name] = 0.0

    return blendshape_weights


# ---------------------------------------------------------------------------
# Leitor binario de nos FBX para extrair normais IndexToDirect
# ---------------------------------------------------------------------------
def parse_fbx_binary_nodes(fbx_raw_bytes):
    fbx_version = struct.unpack_from("<I", fbx_raw_bytes, 23)[0]
    is_64bit_header = fbx_version >= 7500
    header_format = "<QQQB" if is_64bit_header else "<IIIB"
    header_byte_size = 25 if is_64bit_header else 13

    def parse_single_property(byte_pos):
        type_code = chr(fbx_raw_bytes[byte_pos])
        byte_pos += 1
        if type_code == "Y":
            return struct.unpack_from("<h", fbx_raw_bytes, byte_pos)[0], byte_pos + 2
        if type_code == "C":
            return bool(fbx_raw_bytes[byte_pos]), byte_pos + 1
        if type_code == "I":
            return struct.unpack_from("<i", fbx_raw_bytes, byte_pos)[0], byte_pos + 4
        if type_code == "F":
            return struct.unpack_from("<f", fbx_raw_bytes, byte_pos)[0], byte_pos + 4
        if type_code == "D":
            return struct.unpack_from("<d", fbx_raw_bytes, byte_pos)[0], byte_pos + 8
        if type_code == "L":
            return struct.unpack_from("<q", fbx_raw_bytes, byte_pos)[0], byte_pos + 8
        if type_code in ("S", "R"):
            str_len = struct.unpack_from("<I", fbx_raw_bytes, byte_pos)[0]
            byte_pos += 4
            raw_slice = fbx_raw_bytes[byte_pos : byte_pos + str_len]
            decoded_val = (
                raw_slice.decode("utf-8", errors="replace")
                if type_code == "S"
                else raw_slice
            )
            return decoded_val, byte_pos + str_len
        if type_code in ("f", "d", "l", "i", "b"):
            array_length, encoding_flag, compressed_len = struct.unpack_from(
                "<III", fbx_raw_bytes, byte_pos
            )
            byte_pos += 12
            raw_array = fbx_raw_bytes[byte_pos : byte_pos + compressed_len]
            byte_pos += compressed_len
            if encoding_flag == 1:
                raw_array = zlib.decompress(raw_array)
            format_map = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "B"}
            unpacked_array = struct.unpack(
                f"<{array_length}{format_map[type_code]}", raw_array
            )
            return unpacked_array, byte_pos
        raise ValueError(f"Tipo de propriedade FBX desconhecido: {type_code}")

    def parse_single_node(byte_pos):
        end_offset, prop_count, prop_byte_len, name_len = struct.unpack_from(
            header_format, fbx_raw_bytes, byte_pos
        )
        if end_offset == 0:
            return None, byte_pos + header_byte_size
        byte_pos += header_byte_size
        node_name = fbx_raw_bytes[byte_pos : byte_pos + name_len].decode(
            "utf-8", errors="replace"
        )
        byte_pos += name_len
        prop_list = []
        prop_end_pos = byte_pos + prop_byte_len
        for prop_index in range(prop_count):
            prop_val, byte_pos = parse_single_property(byte_pos)
            prop_list.append(prop_val)
        byte_pos = prop_end_pos
        child_nodes = []
        while byte_pos < end_offset:
            child_item, byte_pos = parse_single_node(byte_pos)
            if child_item is None:
                break
            child_nodes.append(child_item)
        return (node_name, prop_list, child_nodes), end_offset

    cursor_pos = 27
    root_nodes = []
    while cursor_pos < len(fbx_raw_bytes) - header_byte_size:
        parsed_node, cursor_pos = parse_single_node(cursor_pos)
        if parsed_node is None:
            break
        root_nodes.append(parsed_node)
    return root_nodes


def load_fbx_face_loop_normals(fbx_file_path, target_geometry_names=None):
    if not os.path.exists(fbx_file_path):
        return None
    if target_geometry_names is None:
        target_geometry_names = ["Shinano_face", "Body", "Face"]

    with open(fbx_file_path, "rb") as fbx_file:
        fbx_bytes = fbx_file.read()

    fbx_nodes = parse_fbx_binary_nodes(fbx_bytes)
    objects_node = next(
        (node_item for node_item in fbx_nodes if node_item[0] == "Objects"), None
    )
    if not objects_node:
        return None

    for child_node in objects_node[2]:
        if (
            child_node[0] == "Geometry"
            and len(child_node[1]) >= 3
            and child_node[1][2] == "Mesh"
        ):
            geom_name = child_node[1][1].split("\x00")[0]
            if geom_name not in target_geometry_names:
                continue
            normal_layer = next(
                (
                    sub_node
                    for sub_node in child_node[2]
                    if sub_node[0] == "LayerElementNormal"
                ),
                None,
            )
            if not normal_layer:
                continue
            normals_flat = next(
                (
                    sub_item[1][0]
                    for sub_item in normal_layer[2]
                    if sub_item[0] == "Normals"
                ),
                [],
            )
            normals_index = next(
                (
                    sub_item[1][0]
                    for sub_item in normal_layer[2]
                    if sub_item[0] == "NormalsIndex"
                ),
                [],
            )
            if normals_flat and normals_index:
                loop_normals = []
                for normal_idx in normals_index:
                    base_idx = normal_idx * 3
                    loop_normals.append(
                        (
                            float(normals_flat[base_idx]),
                            float(normals_flat[base_idx + 1]),
                            float(normals_flat[base_idx + 2]),
                        )
                    )
                return loop_normals
    return None


# ---------------------------------------------------------------------------
# Mapeador Universal de Ossos para GTA V (Modular Avatar Bake)
# ---------------------------------------------------------------------------
HUMAN_TO_GTAV_BONE_MAP = {
    "Hips": "SKEL_Pelvis",
    "Pelvis": "SKEL_Pelvis",
    "Spine": "SKEL_Spine1",
    "Chest": "SKEL_Spine2",
    "UpperChest": "SKEL_Spine3",
    "Upper_chest": "SKEL_Spine3",
    "Neck": "SKEL_Neck_1",
    "Head": "SKEL_Head",
    "LeftEye": "SKEL_Head",
    "RightEye": "SKEL_Head",
    "Eye.L": "SKEL_Head",
    "Eye.R": "SKEL_Head",
    "Shoulder.L": "SKEL_L_Clavicle",
    "LeftShoulder": "SKEL_L_Clavicle",
    "Upper_arm.L": "SKEL_L_UpperArm",
    "UpperArm.L": "SKEL_L_UpperArm",
    "LeftUpperArm": "SKEL_L_UpperArm",
    "Lower_arm.L": "SKEL_L_Forearm",
    "LowerArm.L": "SKEL_L_Forearm",
    "LeftLowerArm": "SKEL_L_Forearm",
    "Hand.L": "SKEL_L_Hand",
    "LeftHand": "SKEL_L_Hand",
    "Shoulder.R": "SKEL_R_Clavicle",
    "RightShoulder": "SKEL_R_Clavicle",
    "Upper_arm.R": "SKEL_R_UpperArm",
    "UpperArm.R": "SKEL_R_UpperArm",
    "RightUpperArm": "SKEL_R_UpperArm",
    "Lower_arm.R": "SKEL_R_Forearm",
    "LowerArm.R": "SKEL_R_Forearm",
    "RightLowerArm": "SKEL_R_Forearm",
    "Hand.R": "SKEL_R_Hand",
    "RightHand": "SKEL_R_Hand",
    "Upper_leg.L": "SKEL_L_Thigh",
    "UpperLeg.L": "SKEL_L_Thigh",
    "LeftUpperLeg": "SKEL_L_Thigh",
    "Lower_leg.L": "SKEL_L_Calf",
    "LowerLeg.L": "SKEL_L_Calf",
    "LeftLowerLeg": "SKEL_L_Calf",
    "Foot.L": "SKEL_L_Foot",
    "LeftFoot": "SKEL_L_Foot",
    "Toe.L": "SKEL_L_Toe0",
    "LeftToes": "SKEL_L_Toe0",
    "Upper_leg.R": "SKEL_R_Thigh",
    "UpperLeg.R": "SKEL_R_Thigh",
    "RightUpperLeg": "SKEL_R_Thigh",
    "Lower_leg.R": "SKEL_R_Calf",
    "LowerLeg.R": "SKEL_R_Calf",
    "RightLowerLeg": "SKEL_R_Calf",
    "Foot.R": "SKEL_R_Foot",
    "RightFoot": "SKEL_R_Foot",
    "Toe.R": "SKEL_R_Toe0",
    "RightToes": "SKEL_R_Toe0",
}


def resolve_gtav_target_bone(source_bone_name, mesh_name=None):
    # 1. Regras especificas por malha de acessorios
    if mesh_name == "UN3_Bag":
        lower_b = source_bone_name.lower()
        if "shoulder.l" in lower_b or "shoulder_l" in lower_b:
            return "SKEL_L_Clavicle"
        if "shoulder.r" in lower_b or "shoulder_r" in lower_b:
            return "SKEL_R_Clavicle"
        if "upper_arm.l" in lower_b or "upperarm.l" in lower_b:
            return "SKEL_L_UpperArm"
        if "upper_arm.r" in lower_b or "upperarm.r" in lower_b:
            return "SKEL_R_UpperArm"
        # Toda a estrutura da mochila (UN_Bag, UN_Bagchain, UN_Bag_Ring, alcas e corpo)
        # deve acompanhar estritamente o peito/torso (SKEL_Spine2) para evitar que o anel
        # e as correntes se soltem e flutuem no ar atras do personagem na idle pose.
        return "SKEL_Spine2"

    if source_bone_name in HUMAN_TO_GTAV_BONE_MAP:
        return HUMAN_TO_GTAV_BONE_MAP[source_bone_name]

    # 2. Dedos das maos e palmas
    # Para eliminar distorcoes, achatamento como papel e dedos torcidos (onde as animacoes
    # do Michael tentam rotacionar ossos masculinos 7.5cm distantes dos dedos de anime),
    # consolidamos todos os vertices de dedos diretamente no pulso (SKEL_L_Hand e SKEL_R_Hand).
    # Isso preserva a pose natural e relaxada original da Shinano em todas as animacoes.
    if any(
        finger_key in source_bone_name
        for finger_key in ["Finger", "Thumb", "Index", "Middle", "Ring", "Little", "Hand"]
    ):
        side_code = (
            "L"
            if (".L" in source_bone_name or "Left" in source_bone_name or "_L" in source_bone_name)
            else "R"
        )
        return f"SKEL_{side_code}_Hand"

    lower_name = source_bone_name.lower()

    # Peito, lacos e ribbons de busto -> SKEL_Spine2
    if (
        lower_name.startswith("breast")
        or lower_name.startswith("bust")
        or "chestribbon" in lower_name
        or "un_ribbon" in lower_name
    ):
        return "SKEL_Spine2"

    # Cabelo, orelhas, chapeu, presilhas, aureola e fita de cabelo -> SKEL_Head
    if (
        "hair" in lower_name
        or "cooni" in lower_name
        or "bang" in lower_name
        or "ear" in lower_name
        or "aho" in lower_name
        or "hat" in lower_name
        or "glasses" in lower_name
        or "halo" in lower_name
        or "pin" in lower_name
        or "atama" in lower_name
        or "back" in lower_name
        or "side" in lower_name
        or "ribbon" in lower_name
    ):
        return "SKEL_Head"

    # Gluteos -> Thighs
    if "butt.l" in lower_name or "butt_l" in lower_name:
        return "SKEL_L_Thigh"
    if "butt.r" in lower_name or "butt_r" in lower_name:
        return "SKEL_R_Thigh"

    # Bracos auxiliares de suporte
    if "support" in lower_name:
        side_code = "L" if (".l" in lower_name or "_l" in lower_name) else "R"
        if "lower" in lower_name or "support2" in lower_name or "support3" in lower_name:
            return f"SKEL_{side_code}_Forearm"
        return f"SKEL_{side_code}_UpperArm"

    # Saia (UN_Skirt) -> Thighs para dinamica de pernas ou Pelvis
    if "skirt" in lower_name:
        if ".l" in lower_name or "_l" in lower_name:
            return "SKEL_L_Thigh"
        if ".r" in lower_name or "_r" in lower_name:
            return "SKEL_R_Thigh"
        return "SKEL_Pelvis"

    # Bolsas, correntes de cintura e relogio de bolso -> SKEL_Pelvis
    if (
        "bag" in lower_name
        or "chain" in lower_name
        or "coin" in lower_name
        or "watch" in lower_name
        or "tail" in lower_name
        or "belt" in lower_name
    ):
        return "SKEL_Pelvis"

    return "SKEL_Pelvis"


# ---------------------------------------------------------------------------
# Divisao de Geometrias Grandes para o Limite uint16 da RAGE Engine (<30.000 verts)
# ---------------------------------------------------------------------------
def split_oversized_material_geometries(mesh_object, max_vertices_per_chunk=30000):
    mesh_data = mesh_object.data
    polys_by_material = {}
    for poly_item in mesh_data.polygons:
        polys_by_material.setdefault(poly_item.material_index, []).append(poly_item.index)

    max_polys_per_chunk = max(10000, int(max_vertices_per_chunk * 0.65))

    for mat_index, poly_indices in list(polys_by_material.items()):
        if len(poly_indices) <= max_polys_per_chunk:
            continue

        base_material = mesh_data.materials[mat_index]
        chunk_total = math.ceil(len(poly_indices) / max_polys_per_chunk)
        print(
            f"[INFO] Dividindo material '{base_material.name}' ({len(poly_indices)} triangulos) "
            f"em {chunk_total} sub-geometrias para respeitar o limite uint16 (65.535 vertices)."
        )

        for chunk_idx in range(1, chunk_total):
            cloned_mat = base_material.copy()
            cloned_mat.name = f"{base_material.name}_chunk{chunk_idx}"
            mesh_data.materials.append(cloned_mat)
            new_slot_index = len(mesh_data.materials) - 1

            start_pos = chunk_idx * max_polys_per_chunk
            end_pos = min(len(poly_indices), (chunk_idx + 1) * max_polys_per_chunk)
            for poly_idx in poly_indices[start_pos:end_pos]:
                mesh_data.polygons[poly_idx].material_index = new_slot_index

    mesh_data.update()


def apply_shape_key_weights_by_index(mesh_obj, weights_by_index, label):
    """Aplica pesos de shape keys por indice 0-based (apos Basis) zerando os demais."""
    if not mesh_obj or not mesh_obj.data.shape_keys:
        raise RuntimeError(f"Malha '{label}' nao possui shape keys disponiveis.")

    key_blocks = mesh_obj.data.shape_keys.key_blocks
    for key_block in key_blocks[1:]:
        key_block.value = 0.0

    applied_count = 0
    for zero_based_idx, weight_val in weights_by_index.items():
        target_slot = zero_based_idx + 1
        if target_slot >= len(key_blocks):
            raise IndexError(
                f"Shape key indice {zero_based_idx} fora do intervalo em '{mesh_obj.name}' "
                f"(total disponivel: {len(key_blocks) - 1})."
            )
        key_blocks[target_slot].value = weight_val
        applied_count += 1

    print(f"[INFO] Aplicados {applied_count} shape keys por indice em '{mesh_obj.name}'.")


def validate_build_inputs(cli_args):
    """Valida existencia dos arquivos e parametros de entrada antes da compilacao."""
    required_paths = [
        ("Esqueleto GTA V (.yft)", cli_args.skeleton_yft),
        ("FBX Base Shinano", cli_args.shinano_fbx),
        ("FBX Roupas Eternal Reunion", cli_args.outfit_fbx),
        ("FBX Pocket Watch", cli_args.watch_fbx),
        ("FBX Cabelo Neko Tied Bob", cli_args.hair_fbx),
        ("Animacao Facial (.anim)", cli_args.face_anim),
    ]
    for desc_label, file_path in required_paths:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"{desc_label} nao encontrado em: {file_path}")

    texture_dir = os.path.abspath(cli_args.texture_dir)
    for tex_name in (cli_args.atlas_png, cli_args.normal_png, cli_args.spec_png):
        tex_path = os.path.join(texture_dir, tex_name)
        if not os.path.isfile(tex_path):
            raise FileNotFoundError(f"Textura do atlas nao encontrada em: {tex_path}")

    if not (1 <= cli_args.max_verts_per_chunk <= 65535):
        raise ValueError(
            f"--max-verts-per-chunk fora do limite uint16 (1..65535): {cli_args.max_verts_per_chunk}"
        )


# ---------------------------------------------------------------------------
# Pipeline Principal de Montagem e Exportacao
# ---------------------------------------------------------------------------
def build_shinano_er_for_gtav(cli_args):
    validate_build_inputs(cli_args)
    addon_utils.enable("sollumz")
    from sollumz.sollumz_properties import SollumType
    from sollumz.tools.blenderhelper import create_empty_object
    from sollumz.tools.drawablehelper import (
        convert_obj_to_model,
        set_recommended_bone_properties,
    )
    from sollumz.ydr.shader_materials import create_shader
    import sollumz.ydr.ydrexport as ydrexport

    char_key = cli_args.target_character.lower()
    if char_key not in CHARACTER_PROFILES:
        raise ValueError(f"Personagem invalido: {char_key}. Use michael, franklin ou trevor.")
    char_profile = CHARACTER_PROFILES[char_key]

    # 1. Limpa a cena do Blender
    for obj_item in list(bpy.data.objects):
        bpy.data.objects.remove(obj_item)
    for mesh_item in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh_item)
    for arm_item in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm_item)
    for mat_item in list(bpy.data.materials):
        bpy.data.materials.remove(mat_item)

    # 2. Importa o esqueleto base .yft do personagem do GTA V
    skel_dir = os.path.dirname(os.path.abspath(cli_args.skeleton_yft)) + "/"
    skel_filename = os.path.basename(cli_args.skeleton_yft)
    print(f"[INFO] Importando esqueleto base do GTA V: {cli_args.skeleton_yft}")
    bpy.ops.sollumz.import_assets(directory=skel_dir, files=[{"name": skel_filename}])

    ped_armature = bpy.data.objects.get(char_profile["ped_name"])
    if not ped_armature:
        ped_armature = next(
            (obj_item for obj_item in bpy.data.objects if obj_item.type == "ARMATURE"),
            None,
        )
    if not ped_armature:
        raise RuntimeError(
            f"Esqueleto GTA V nao carregado de '{cli_args.skeleton_yft}'."
        )

    valid_gtav_bones = {
        "SKEL_ROOT",
        "SKEL_Pelvis",
        "SKEL_Spine_Root",
        "SKEL_Spine0",
        "SKEL_Spine1",
        "SKEL_Spine2",
        "SKEL_Spine3",
        "SKEL_Neck_1",
        "SKEL_Head",
        "FACIAL_facialRoot",
        "FACIAL_jaw",
        "SKEL_L_Clavicle",
        "SKEL_L_UpperArm",
        "SKEL_L_Forearm",
        "SKEL_L_Hand",
        "SKEL_R_Clavicle",
        "SKEL_R_UpperArm",
        "SKEL_R_Forearm",
        "SKEL_R_Hand",
        "SKEL_L_Thigh",
        "SKEL_L_Calf",
        "SKEL_L_Foot",
        "SKEL_L_Toe0",
        "SKEL_R_Thigh",
        "SKEL_R_Calf",
        "SKEL_R_Foot",
        "SKEL_R_Toe0",
    }
    for side_code in ["L", "R"]:
        for finger_idx in range(5):
            for sub_idx in range(3):
                valid_gtav_bones.add(f"SKEL_{side_code}_Finger{finger_idx}{sub_idx}")

    bpy.context.view_layer.objects.active = ped_armature
    bpy.ops.object.mode_set(mode="EDIT")
    for edit_bone in list(ped_armature.data.edit_bones):
        if edit_bone.name not in valid_gtav_bones:
            ped_armature.data.edit_bones.remove(edit_bone)
    bpy.ops.object.mode_set(mode="OBJECT")

    for extra_obj in list(bpy.data.objects):
        if extra_obj != ped_armature:
            bpy.data.objects.remove(extra_obj)

    # 3. Importa os 4 pacotes FBX do avatar e acessorios
    imported_armatures = []

    # 3A. Shinano Base (Body e Body_base)
    print(f"[INFO] Importando Base Shinano FBX: {cli_args.shinano_fbx}")
    bpy.ops.import_scene.fbx(filepath=cli_args.shinano_fbx)
    arm_base = next(
        (obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj != ped_armature and obj not in imported_armatures),
        None,
    )
    if arm_base:
        imported_armatures.append(arm_base)

    # 3B. Eternal Reunion Outfit FBX
    print(f"[INFO] Importando Outfit FBX: {cli_args.outfit_fbx}")
    bpy.ops.import_scene.fbx(filepath=cli_args.outfit_fbx)
    arm_outfit = next(
        (obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj != ped_armature and obj not in imported_armatures),
        None,
    )
    if arm_outfit:
        imported_armatures.append(arm_outfit)

    # 3C. Pocket Watch FBX
    print(f"[INFO] Importando Pocket Watch FBX: {cli_args.watch_fbx}")
    bpy.ops.import_scene.fbx(filepath=cli_args.watch_fbx)
    arm_watch = next(
        (obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj != ped_armature and obj not in imported_armatures),
        None,
    )
    if arm_watch:
        imported_armatures.append(arm_watch)

    # 3D. CooniBob Hair FBX
    print(f"[INFO] Importando CooniBob Hair FBX: {cli_args.hair_fbx}")
    bpy.ops.import_scene.fbx(filepath=cli_args.hair_fbx)
    arm_hair = next(
        (obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj != ped_armature and obj not in imported_armatures),
        None,
    )
    if arm_hair:
        imported_armatures.append(arm_hair)

    # Rotaciona bracos para a A-pose do GTA V (-55 graus) e ajusta escala do Neck (0.90) conforme Shinano.unity
    arm_angle_rad = -math.radians(abs(char_profile["arm_pose_degrees"]))
    neck_scaled_armatures = {arm_obj for arm_obj in (arm_base, arm_outfit) if arm_obj}
    for arm_obj in imported_armatures:
        bpy.context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode="POSE")
        for left_arm_name in ["Upper_arm.L", "UpperArm.L", "LeftUpperArm"]:
            if left_arm_name in arm_obj.pose.bones:
                pose_bone = arm_obj.pose.bones[left_arm_name]
                pose_bone.rotation_mode = "XYZ"
                pose_bone.rotation_euler = (arm_angle_rad, 0.0, 0.0)
        for right_arm_name in ["Upper_arm.R", "UpperArm.R", "RightUpperArm"]:
            if right_arm_name in arm_obj.pose.bones:
                pose_bone = arm_obj.pose.bones[right_arm_name]
                pose_bone.rotation_mode = "XYZ"
                pose_bone.rotation_euler = (arm_angle_rad, 0.0, 0.0)
        if arm_obj in neck_scaled_armatures and "Neck" in arm_obj.pose.bones:
            neck_pose_bone = arm_obj.pose.bones["Neck"]
            neck_pose_bone.scale = (0.9, 0.9, 0.9)
        bpy.ops.object.mode_set(mode="OBJECT")

    if not arm_hair or "Hair Root" not in arm_hair.data.bones:
        raise RuntimeError(
            "Osso 'Hair Root' nao encontrado na armature do cabelo Neko Tied Bob."
        )
    hair_root_rest_pos = (
        arm_hair.matrix_world @ arm_hair.data.bones["Hair Root"].head_local
    ).copy()

    # 4. Carrega normais originais do rosto do FBX da Shinano
    fbx_face_normals = load_fbx_face_loop_normals(cli_args.shinano_fbx)
    if fbx_face_normals:
        print(f"[INFO] {len(fbx_face_normals)} normais faciais IndexToDirect carregadas do FBX.")

    # 5. Aplica blendshapes faciais no Body
    face_blendshapes = load_unity_anim_blendshapes(cli_args.face_anim)
    body_mesh_obj = bpy.data.objects.get("Body")
    if body_mesh_obj and body_mesh_obj.data.shape_keys:
        for key_block in body_mesh_obj.data.shape_keys.key_blocks:
            key_block.value = 0.0
        for shape_name, shape_val in face_blendshapes.items():
            key_block = body_mesh_obj.data.shape_keys.key_blocks.get(shape_name)
            if key_block:
                key_block.value = shape_val

    # 6. Aplica blendshapes de modelagem e encolhimento no Body_base (foto Unity + SMR 1762524570)
    # 100%: Corset, Hip_big, Breasts_big, Nail_hand_Oval, Shrink_Upper_arm, Shrink_Elbow,
    # Shrink_Chest1..2, Shrink_Breast1..2, Shrink_Spine_1..2, Shrink_Hip_all,
    # Shrink_Upper_leg1..2, Shrink_Knees, Shrink_Lower_leg, Shrink_Ankle, Shrink_Foot.
    # 0%: Neck1..3, Shoulder, Low_arm, wrist, hand, Hip1..4, Stocking1..3, Toe_heels, Toe_highheels.
    body_base_weights = {
        0: 1.0,
        6: 1.0,
        7: 1.0,
        14: 1.0,
        25: 1.0,
        26: 1.0,
        30: 1.0,
        31: 1.0,
        32: 1.0,
        33: 1.0,
        34: 1.0,
        35: 1.0,
        36: 1.0,
        41: 1.0,
        42: 1.0,
        43: 1.0,
        44: 1.0,
        45: 1.0,
        46: 1.0,
    }
    apply_shape_key_weights_by_index(
        bpy.data.objects.get("Body_base"), body_base_weights, "Body_base"
    )

    # 6A. Aplica blendshapes de ajuste das roupas Eternal Reunion e Pocket Watch
    outfit_shape_keys_by_index = {
        "UN1_Shirt": {0: 1.0, 4: 1.0},
        "UN1_Skirt": {4: 1.0, 5: 1.0},
        "UN1_ChestRibbon": {0: 1.0},
        "UN2_Corset": {1: 1.0, 2: 1.0},
        "UN2_Stocking": {0: 1.0, 1: 1.0},
        "UN3_WaistChain": {0: 1.0, 1: 1.0},
        "Pocket Watch": {5: 1.0},
    }
    for outfit_mesh_name, outfit_weights in outfit_shape_keys_by_index.items():
        apply_shape_key_weights_by_index(
            bpy.data.objects.get(outfit_mesh_name), outfit_weights, outfit_mesh_name
        )

    # 6B. Aplica blendshapes do Neko Tied Bob hair por indice exato (Shinano.unity / MA Shinano.prefab)
    hair_shape_keys_by_index = {
        "Bangs": {9: 0.284, 17: 1.0, 22: 1.0},
        "Side Bangs": {0: 1.0, 4: 1.0},
        "Side": {
            5: 1.0,
            28: 1.0,
            31: 1.0,
            34: 0.136,
            35: 0.642,
            37: 1.0,
            40: 0.603,
            41: 1.0,
            42: 1.0,
            43: 0.328,
            44: 1.0,
            45: 1.0,
        },
        "Back": {8: 1.0, 12: 0.47, 13: 0.072},
        "Under Side": {
            8: 1.0,
            17: 0.778,
            22: 0.203,
            28: 0.788,
            33: 0.425,
            34: 1.0,
            39: 0.317,
            43: 0.510,
        },
        "In Hair": {
            4: 0.725,
            5: 0.075,
            6: 0.40,
            10: 1.0,
            11: 1.0,
            15: 1.0,
            16: 0.485,
            17: 0.796,
            19: 0.945,
            20: 0.117,
            21: 0.10,
            22: 0.315,
            23: 0.166,
            24: 0.427,
            25: 0.475,
            29: 1.0,
            30: 0.639,
            31: 1.0,
            32: 1.0,
            33: 1.0,
            37: 0.399,
            38: 0.221,
            40: 0.393,
            42: 0.126,
            44: 1.0,
            45: 1.0,
            47: 0.488,
        },
    }
    for hair_mesh_name, hair_weights in hair_shape_keys_by_index.items():
        apply_shape_key_weights_by_index(
            bpy.data.objects.get(hair_mesh_name), hair_weights, hair_mesh_name
        )

    bpy.context.view_layer.update()

    # 7. Inventario das 27 malhas ativas aprovadas
    # Lista com mapeamento de categoria para o Atlas 4x2 unificado
    ACTIVE_MESH_CONFIGS = {
        # Shinano Base
        "Body": {"atlas_col": 0, "atlas_row": 1, "shrink_cull": False},
        "Body_base": {"atlas_col": 1, "atlas_row": 1, "shrink_cull": True},
        # Eternal Reunion UN1
        "UN1_Shirt": {"atlas_col": 2, "atlas_row": 1, "shrink_cull": False},
        "UN1_Skirt": {"atlas_col": 2, "atlas_row": 1, "shrink_cull": False},
        "UN1_ChestRibbon": {"atlas_col": 2, "atlas_row": 1, "shrink_cull": False},
        "UN1_Choker": {"atlas_col": 2, "atlas_row": 1, "shrink_cull": False},
        # Eternal Reunion UN2
        "UN2_Corset": {"atlas_col": 3, "atlas_row": 1, "shrink_cull": False},
        # "UN2_Beret": Desabilitada a pedido do usuario (tratada como EditorOnly / desativada)
        "UN2_Shoes": {"atlas_col": 3, "atlas_row": 1, "shrink_cull": False},
        "UN2_Stocking": {"atlas_col": 3, "atlas_row": 1, "shrink_cull": False},
        # Eternal Reunion UN3
        "UN3_Bag": {"atlas_col": 0, "atlas_row": 0, "shrink_cull": False},
        "UN3_Glasses": {"atlas_col": 0, "atlas_row": 0, "shrink_cull": False},
        "UN3_WaistChain": {"atlas_col": 0, "atlas_row": 0, "shrink_cull": False},
        # Pocket Watch
        "Pocket Watch": {"atlas_col": 1, "atlas_row": 0, "shrink_cull": False},
        # Neko Tied Bob hair (Cabelo Principal em azul vibrante)
        "Bangs": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Top Back": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Under Side": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Back": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Side Bangs": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Side": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "In Hair": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        "Ribbon": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        # Orelhas de Gato (Ears) do Neko Tied Bob hair ativas na ausencia da boina
        "Ears": {"atlas_col": 2, "atlas_row": 0, "shrink_cull": False},
        # Neko Tied Bob hair - Acessorios integrados na celula (coluna 3, linha 0)
        "_Pin.Back": {
            "u_offset": 0.875,
            "v_offset": 0.25,
            "u_scale": 0.125,
            "v_scale": 0.25,
            "shrink_cull": False,
        },
        "_Pin.R": {
            "u_offset": 0.75,
            "v_offset": 0.0,
            "u_scale": 0.125,
            "v_scale": 0.25,
            "clamp_v": True,
            "shrink_cull": False,
        },
        "_Pin.L2": {
            "u_offset": 0.75,
            "v_offset": 0.0,
            "u_scale": 0.125,
            "v_scale": 0.25,
            "clamp_v": True,
            "shrink_cull": False,
        },
        # Aureola metalica flutuante (_Halo)
        "_Halo": {
            "u_offset": 0.75,
            "v_offset": 0.25,
            "u_scale": 0.125,
            "v_scale": 0.25,
            "shrink_cull": False,
        },
    }

    scale_factor = (char_profile["target_z_max"] - char_profile["target_z_min"]) / (1.132 - 0.106)
    z_offset = char_profile["target_z_min"] - (0.106 * scale_factor)

    depsgraph_eval = bpy.context.evaluated_depsgraph_get()
    processed_objects = []
    preserved_body_normals = None

    # Pre-calcula pesos de deformacao da mandibula (FACIAL_jaw) atraves do shape key vrc.v_aa
    body_jaw_weights = {}
    orig_body_obj = bpy.data.objects.get("Body")
    if orig_body_obj and orig_body_obj.data.shape_keys:
        kb_aa = orig_body_obj.data.shape_keys.key_blocks.get("vrc.v_aa")
        basis = orig_body_obj.data.shape_keys.key_blocks.get("Basis")
        if kb_aa and basis:
            for vert_item in orig_body_obj.data.vertices:
                delta_z = kb_aa.data[vert_item.index].co.z - basis.data[vert_item.index].co.z
                if delta_z < -0.0005:
                    w_val = min(0.35, max(0.0, (abs(delta_z) / 0.0075) * 0.35))
                    body_jaw_weights[vert_item.index] = w_val
            print(f"[OK] {len(body_jaw_weights)} vertices mapeados para FACIAL_jaw no Body.")

    for mesh_name, mesh_cfg in ACTIVE_MESH_CONFIGS.items():
        source_obj = bpy.data.objects.get(mesh_name)
        if not source_obj or source_obj.type != "MESH":
            print(f"[AVISO] Objeto de malha '{mesh_name}' nao encontrado, ignorando.")
            continue

        print(f"[INFO] Processando malha: {mesh_name} ({len(source_obj.data.vertices)} vertices)")

        # Identifica vertices encolhidos pelas chaves Shrink_* ativas em Body_base
        shrunk_vertex_indices = set()
        if mesh_cfg["shrink_cull"] and source_obj.data.shape_keys:
            basis_block = source_obj.data.shape_keys.key_blocks[0]
            for key_block in source_obj.data.shape_keys.key_blocks[1:]:
                # Culling estrito para chaves Shrink_* (cintura, seios, bracos superiores e pernas sob a roupa)
                is_shrink_key = key_block.name.lower().startswith("shrink_")
                if is_shrink_key and key_block.value > 0.5:
                    for vert_idx in range(len(source_obj.data.vertices)):
                        delta_vec = key_block.data[vert_idx].co - basis_block.data[vert_idx].co
                        if delta_vec.length > 0.00002:
                            shrunk_vertex_indices.add(vert_idx)

        evaluated_obj = source_obj.evaluated_get(depsgraph_eval)
        baked_mesh = bpy.data.meshes.new_from_object(evaluated_obj)

        bm_data = bmesh.new()
        bm_data.from_mesh(baked_mesh)

        orig_vert_layer = bm_data.verts.layers.int.new("orig_vert_idx")
        for vert_idx_counter, bm_vert_item in enumerate(bm_data.verts):
            bm_vert_item[orig_vert_layer] = vert_idx_counter

        if mesh_name == "Body":
            alpha_mat_indices = [
                mat_idx
                for mat_idx, mat_obj in enumerate(source_obj.data.materials)
                if mat_obj and "alpha" in mat_obj.name.lower()
            ]
            orig_loop_layer = bm_data.loops.layers.int.new("orig_loop_idx")
            loop_counter = 0
            for face_item in bm_data.faces:
                for loop_item in face_item.loops:
                    loop_item[orig_loop_layer] = loop_counter
                    loop_counter += 1
            if alpha_mat_indices:
                faces_to_remove = [
                    face_item
                    for face_item in bm_data.faces
                    if face_item.material_index in alpha_mat_indices
                ]
                bmesh.ops.delete(bm_data, geom=faces_to_remove, context="FACES")
                loose_verts = [vert for vert in bm_data.verts if not vert.link_faces]
                bmesh.ops.delete(bm_data, geom=loose_verts, context="VERTS")

            bmesh.ops.triangulate(bm_data, faces=bm_data.faces)
            kept_loop_indices = []
            for face_item in bm_data.faces:
                face_item.smooth = True
                for loop_item in face_item.loops:
                    kept_loop_indices.append(loop_item[orig_loop_layer])
            kept_orig_vert_indices = [
                bm_vert_item[orig_vert_layer] for bm_vert_item in bm_data.verts
            ]
            bm_data.to_mesh(baked_mesh)
            bm_data.free()
            baked_mesh.update()
        else:
            if shrunk_vertex_indices:
                bm_data.verts.ensure_lookup_table()
                hidden_faces = [
                    face_item
                    for face_item in bm_data.faces
                    if all(
                        vert_item[orig_vert_layer] in shrunk_vertex_indices
                        for vert_item in face_item.verts
                    )
                ]
                if hidden_faces:
                    bmesh.ops.delete(bm_data, geom=hidden_faces, context="FACES")
                    loose_verts = [vert for vert in bm_data.verts if not vert.link_faces]
                    bmesh.ops.delete(bm_data, geom=loose_verts, context="VERTS")
                    print(
                        f"[INFO] Shrink Culling removeu {len(hidden_faces)} faces ocultas de {mesh_name}."
                    )

            bmesh.ops.triangulate(bm_data, faces=bm_data.faces)
            for face_item in bm_data.faces:
                face_item.smooth = True
            kept_orig_vert_indices = [
                bm_vert_item[orig_vert_layer] for bm_vert_item in bm_data.verts
            ]
            bm_data.to_mesh(baked_mesh)
            bm_data.free()
            baked_mesh.update()

        # Transformacao exata do Neko Tied Bob hair baseada na cena Shinano.unity (MA Shinano -> Hair Root)
        neko_hair_mesh_names = {
            "Bangs",
            "Top Back",
            "Under Side",
            "Back",
            "Side Bangs",
            "Side",
            "In Hair",
            "Ribbon",
            "Ears",
            "_Halo",
            "_Pin.Back",
            "_Pin.R",
            "_Pin.L2",
        }
        offset_x = mesh_cfg.get("offset_x", 0.0)
        offset_y = mesh_cfg.get("offset_y", 0.0)
        offset_z = mesh_cfg.get("offset_z", 0.0)

        # Ajuste de transformacao da boina (UN2_Beret) conforme cena Shinano.unity
        is_beret_mesh = (mesh_name == "UN2_Beret")
        if is_beret_mesh:
            # Pivo do osso UN_HatRoot no espaco de mundo do Blender
            hat_pivot = mathutils.Vector((0.0, 0.0314, 1.2534))
            # Inclinacao extra extraida do Shinano.unity (Euler X = -30.272 graus vs rest -18.808 graus no FBX)
            # Delta de inclinacao para tras: -11.464 graus
            hat_rot_matrix = mathutils.Matrix.Rotation(math.radians(-11.464), 4, "X")
            # Delta de translacao relativo a Head entre o FBX e a cena Shinano.unity:
            # Unity LocalPosition: {x: 0, y: 0.1347, z: -0.0473} vs rest {x: -0.000011, y: 0.120822, z: -0.020751}
            # Delta Unity: dY = +0.013878 (cima), dZ = -0.026549 (tras)
            # Mapeamento para Blender: dY_blender = +0.026549 (tras), dZ_blender = +0.013878 (cima)
            hat_pos_delta = mathutils.Vector((0.0, 0.02655, 0.01388))

        # Posicao, escala (1.08696) e leve pitch (-0.001953 rad em X) do osso Hair Root no Unity
        is_neko_hair = (mesh_name in neko_hair_mesh_names)
        neko_target_hair_root = mathutils.Vector((0.000653, 0.010790, 1.202636))
        neko_hair_scale = 1.08696
        neko_hair_rot_matrix = mathutils.Euler((-0.001953, 0.0, 0.0), "XYZ").to_matrix()

        # Escala e alinha altura ao esqueleto do Michael aplicando a matriz de mundo da fonte e offset
        for vert_item in baked_mesh.vertices:
            world_co = source_obj.matrix_world @ vert_item.co
            if is_beret_mesh:
                rel_co = world_co - hat_pivot
                world_co = hat_pivot + (hat_rot_matrix @ rel_co) + hat_pos_delta
            elif is_neko_hair:
                # Mapeia o cabelo do Hair Root em repouso do FBX para o MA Hair Root da cena Shinano.unity
                rel_hair = (world_co - hair_root_rest_pos) * neko_hair_scale
                world_co = neko_target_hair_root + (neko_hair_rot_matrix @ rel_hair)

            vert_item.co.x = (world_co.x + offset_x) * scale_factor
            vert_item.co.y = (world_co.y + offset_y) * scale_factor
            vert_item.co.z = (world_co.z + offset_z) * scale_factor + z_offset

        if (
            mesh_name == "Body"
            and fbx_face_normals
            and len(kept_loop_indices) == len(baked_mesh.loops)
        ):
            preserved_body_normals = [
                fbx_face_normals[loop_idx] for loop_idx in kept_loop_indices
            ]
        baked_mesh.update()

        proc_obj = bpy.data.objects.new(f"proc_{mesh_name}", baked_mesh)
        bpy.context.collection.objects.link(proc_obj)

        # Mapeia UVs desta malha para o seu quadrante ou sub-quadrante no Atlas 4x2
        u_scale = mesh_cfg.get("u_scale", 0.25)
        v_scale = mesh_cfg.get("v_scale", 0.5)
        if "u_offset" in mesh_cfg and "v_offset" in mesh_cfg:
            u_offset = mesh_cfg["u_offset"]
            v_offset = mesh_cfg["v_offset"]
        else:
            atlas_col = mesh_cfg["atlas_col"]
            atlas_row = mesh_cfg["atlas_row"]
            u_offset = atlas_col / 4.0
            v_offset = atlas_row / 2.0

        clamp_v_flag = mesh_cfg.get("clamp_v", False)

        if proc_obj.data.uv_layers:
            uv_layer = proc_obj.data.uv_layers[0]
            for loop_entry in uv_layer.data:
                orig_u, orig_v = loop_entry.uv
                if clamp_v_flag and orig_v > 1.0:
                    orig_v = min(1.0, max(0.0, orig_v % 1.0))
                loop_entry.uv = (u_offset + (orig_u * u_scale), v_offset + (orig_v * v_scale))

        # Atribui pesos de vertices aos 55 ossos validos do GTA V
        vgroup_target_names = {
            vgroup.index: resolve_gtav_target_bone(vgroup.name, mesh_name)
            for vgroup in source_obj.vertex_groups
        }
        vertex_weight_map = {vert_idx: {} for vert_idx in range(len(baked_mesh.vertices))}
        for new_vert_idx, orig_vert_idx in enumerate(kept_orig_vert_indices):
            if orig_vert_idx < len(source_obj.data.vertices):
                src_vert = source_obj.data.vertices[orig_vert_idx]
                for grp_elem in src_vert.groups:
                    if grp_elem.weight > 0.001 and grp_elem.group in vgroup_target_names:
                        target_bone_name = vgroup_target_names[grp_elem.group]
                        current_weight = vertex_weight_map[new_vert_idx].get(target_bone_name, 0.0)
                        vertex_weight_map[new_vert_idx][target_bone_name] = current_weight + grp_elem.weight

        for vert_idx, bone_weights in vertex_weight_map.items():
            weight_sum = sum(bone_weights.values())
            if weight_sum > 0.0:
                for target_bone_name, raw_weight in bone_weights.items():
                    dst_group = proc_obj.vertex_groups.get(target_bone_name)
                    if not dst_group:
                        dst_group = proc_obj.vertex_groups.new(name=target_bone_name)
                    dst_group.add([vert_idx], raw_weight / weight_sum, "ADD")
            else:
                fallback_bone = (
                    "SKEL_Head"
                    if (
                        "head" in mesh_name.lower()
                        or "hair" in mesh_name.lower()
                        or "glasses" in mesh_name.lower()
                        or "beret" in mesh_name.lower()
                        or mesh_name in neko_hair_mesh_names
                        or mesh_name == "Body"
                    )
                    else (
                        "SKEL_Spine2"
                        if mesh_name in ("UN3_Bag", "UN1_Shirt", "UN1_ChestRibbon")
                        else "SKEL_Pelvis"
                    )
                )
                dst_group = proc_obj.vertex_groups.get(fallback_bone)
                if not dst_group:
                    dst_group = proc_obj.vertex_groups.new(name=fallback_bone)
                dst_group.add([vert_idx], 1.0, "REPLACE")

        if mesh_name == "Body" and body_jaw_weights:
            jaw_vg = proc_obj.vertex_groups.get("FACIAL_jaw")
            if not jaw_vg:
                jaw_vg = proc_obj.vertex_groups.new(name="FACIAL_jaw")
            head_vg = proc_obj.vertex_groups.get("SKEL_Head")
            if not head_vg:
                head_vg = proc_obj.vertex_groups.new(name="SKEL_Head")
            for new_v_idx, orig_v_idx in enumerate(kept_orig_vert_indices):
                if orig_v_idx in body_jaw_weights:
                    jaw_w = body_jaw_weights[orig_v_idx]
                    jaw_vg.add([new_v_idx], jaw_w, "REPLACE")
                    head_vg.add([new_v_idx], max(0.0, 1.0 - jaw_w), "REPLACE")
            print("[OK] Pesos de FACIAL_jaw e SKEL_Head aplicados no Body do Michael.")

        processed_objects.append(proc_obj)

    # 8. Limpa os objetos de armatures e malhas brutas
    for old_obj in list(bpy.data.objects):
        if old_obj != ped_armature and old_obj not in processed_objects:
            bpy.data.objects.remove(old_obj)

    # 9. Une todas as 17 malhas processadas no objeto SKEL_ROOT
    print(f"[INFO] Unindo {len(processed_objects)} malhas processadas em SKEL_ROOT...")
    bpy.ops.object.select_all(action="DESELECT")
    for proc_obj in processed_objects:
        proc_obj.select_set(True)
    bpy.context.view_layer.objects.active = processed_objects[0]
    bpy.ops.object.join()
    joined_mesh_obj = processed_objects[0]
    joined_mesh_obj.name = "SKEL_ROOT"

    for poly_item in joined_mesh_obj.data.polygons:
        poly_item.use_smooth = True
    joined_mesh_obj.data.update()

    for vgroup in list(joined_mesh_obj.vertex_groups):
        if vgroup.name not in valid_gtav_bones:
            joined_mesh_obj.vertex_groups.remove(vgroup)

    bpy.context.view_layer.objects.active = joined_mesh_obj
    bpy.ops.object.vertex_group_limit_total(limit=4)
    bpy.ops.object.vertex_group_normalize_all()

    total_verts = len(joined_mesh_obj.data.vertices)
    total_polys = len(joined_mesh_obj.data.polygons)
    print(f"[INFO] SKEL_ROOT unificado: {total_verts} vertices, {total_polys} poligonos.")

    # 10. Cria e configura o material unificado ped_default.sps com o Atlas 4x2
    texture_dir = os.path.abspath(cli_args.texture_dir)
    atlas_image_path = os.path.join(texture_dir, cli_args.atlas_png)
    normal_image_path = os.path.join(texture_dir, cli_args.normal_png)
    spec_image_path = os.path.join(texture_dir, cli_args.spec_png)

    atlas_img = bpy.data.images.load(atlas_image_path)
    flat_norm_img = bpy.data.images.load(normal_image_path)
    black_spec_img = bpy.data.images.load(spec_image_path)

    ped_mat = create_shader("ped_default.sps")
    ped_mat.name = "shinano_er_mat"

    diff_node = ped_mat.node_tree.nodes.get("DiffuseSampler")
    if diff_node:
        diff_node.image = atlas_img
        diff_node.texture_properties.embedded = False

    bump_node = ped_mat.node_tree.nodes.get("BumpSampler")
    if bump_node:
        bump_node.image = flat_norm_img
        bump_node.texture_properties.embedded = False

    spec_node = ped_mat.node_tree.nodes.get("SpecSampler")
    if spec_node:
        spec_node.image = black_spec_img
        spec_node.texture_properties.embedded = False

    for shader_node in ped_mat.node_tree.nodes:
        if shader_node.name == "bumpiness" and hasattr(shader_node, "set_float"):
            shader_node.set_float(0.35)
        elif shader_node.name == "StubbleControl" and hasattr(shader_node, "set_vec2"):
            shader_node.set_vec2((0.0, 0.0))
        elif shader_node.name == "detailSettings" and hasattr(shader_node, "set_vec4"):
            shader_node.set_vec3((0.0, 0.0, 0.0))
        elif shader_node.name == "specularIntensityMult" and hasattr(shader_node, "set_float"):
            # lilToon: reflexao especular dinamica para metais dourados, sapatos e presilhas
            shader_node.set_float(0.85)
        elif shader_node.name == "specularFalloffMult" and hasattr(shader_node, "set_float"):
            # lilToon: brilho pontual nitido caracteristico de anime e cel-shading
            shader_node.set_float(24.0)
        elif shader_node.name == "specularFresnel" and hasattr(shader_node, "set_float"):
            # lilToon: efeito Rim Light de contorno de silhueta (_UseRim: 1)
            shader_node.set_float(0.70)

    # Limpa materiais antigos e atribui o ped_mat unificado
    joined_mesh_obj.data.materials.clear()
    joined_mesh_obj.data.materials.append(ped_mat)

    for poly_item in joined_mesh_obj.data.polygons:
        poly_item.material_index = 0

    if joined_mesh_obj.data.uv_layers:
        joined_mesh_obj.data.uv_layers[0].name = "UVMap 0"

    bpy.context.view_layer.objects.active = joined_mesh_obj
    bpy.ops.sollumz.color_attrs_add_missing()
    bpy.ops.sollumz.uv_maps_add_missing()

    # Define Color 1 = Branco Neutro e Color 2 = Preto Alpha 0 (elimina suor/oleo)
    color_attr_1 = joined_mesh_obj.data.color_attributes.get("Color 1")
    if color_attr_1:
        for corner_item in color_attr_1.data:
            corner_item.color = (1.0, 1.0, 1.0, 1.0)

    color_attr_2 = joined_mesh_obj.data.color_attributes.get("Color 2")
    if color_attr_2:
        for corner_item in color_attr_2.data:
            corner_item.color = (0.0, 0.0, 0.0, 0.0)

    # Normais suaves de anime no rosto
    if fbx_face_normals and preserved_body_normals:
        joined_mesh_obj.data.use_auto_smooth = True
        joined_mesh_obj.data.calc_normals_split()
        split_normals = [tuple(loop_item.normal) for loop_item in joined_mesh_obj.data.loops]
        face_loop_count = min(len(preserved_body_normals), len(split_normals))
        split_normals[:face_loop_count] = preserved_body_normals[:face_loop_count]

        mesh_verts = joined_mesh_obj.data.vertices
        mesh_loops = joined_mesh_obj.data.loops
        for poly_item in joined_mesh_obj.data.polygons:
            for loop_idx in poly_item.loop_indices:
                vert_co = mesh_verts[mesh_loops[loop_idx].vertex_index].co
                if vert_co.y < -0.045 and 0.61 < vert_co.z < 0.77 and abs(vert_co.x) < 0.085:
                    norm_x = vert_co.x * 2.2
                    norm_y = -1.0
                    norm_z = (vert_co.z - 0.69) * 1.4
                    vec_len = math.sqrt(norm_x * norm_x + norm_y * norm_y + norm_z * norm_z)
                    split_normals[loop_idx] = (
                        norm_x / vec_len,
                        norm_y / vec_len,
                        norm_z / vec_len,
                    )
        joined_mesh_obj.data.normals_split_custom_set(split_normals)
        ydrexport.triangulate_mesh = lambda eval_mesh: eval_mesh

    # 11. Divide malha em sub-geometrias se vertices > 30.000 para limite uint16
    split_oversized_material_geometries(
        joined_mesh_obj, max_vertices_per_chunk=cli_args.max_verts_per_chunk
    )

    # 12. Monta hierarquia de Drawable Dictionary do Sollumz e anexa ao ped_armature
    ydd_parent_empty = create_empty_object(SollumType.DRAWABLE_DICTIONARY)
    ped_armature.sollum_type = SollumType.DRAWABLE
    ped_armature.parent = ydd_parent_empty
    ped_armature.drawable_properties.lod_dist_high = 9998.0
    ped_armature.drawable_properties.lod_dist_med = 9998.0
    ped_armature.drawable_properties.lod_dist_low = 9998.0
    ped_armature.drawable_properties.lod_dist_vlow = 9998.0

    for bone_obj in ped_armature.data.bones:
        set_recommended_bone_properties(bone_obj)

    convert_obj_to_model(joined_mesh_obj)
    joined_mesh_obj.parent = ped_armature

    arm_mod = joined_mesh_obj.modifiers.new("Armature", "ARMATURE")
    arm_mod.object = ped_armature

    output_dir = os.path.abspath(cli_args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Exporta para os drawables especificados do personagem
    for drawable_item_name in char_profile["export_drawables"]:
        ydd_parent_empty.name = drawable_item_name
        ped_armature.name = drawable_item_name
        bpy.ops.object.select_all(action="DESELECT")
        ydd_parent_empty.select_set(True)
        bpy.context.view_layer.objects.active = ydd_parent_empty

        export_status = bpy.ops.sollumz.export_assets(
            directory=output_dir,
            direct_export=True,
            use_custom_settings=True,
            target_versions={"GEN8"},
            target_formats={"NATIVE", "CWXML"},
            limit_to_selected=False,
        )
        print(f"[INFO] Exportado {drawable_item_name}.ydd -> {export_status}")


def parse_blender_cli_args():
    raw_arguments = sys.argv
    double_dash_index = raw_arguments.index("--") if "--" in raw_arguments else len(raw_arguments)
    custom_arguments = raw_arguments[double_dash_index + 1 :]

    michael_cfg = project_paths.get_character_paths("michael")

    argument_parser = argparse.ArgumentParser(
        description="Compilador Shinano Eternal Reunion para GTA V Legacy"
    )
    argument_parser.add_argument(
        "--target-character",
        default="michael",
        choices=["michael", "franklin", "trevor"],
        help="Personagem alvo do Modo Historia",
    )
    argument_parser.add_argument(
        "--skeleton-yft",
        default=str(michael_cfg["skeleton_yft"]),
        help="Caminho do arquivo de esqueleto .yft",
    )
    argument_parser.add_argument(
        "--shinano-fbx",
        default=str(michael_cfg["fbx_shinano"]),
        help="Caminho do FBX base da Shinano (Body e Body_base)",
    )
    argument_parser.add_argument(
        "--outfit-fbx",
        default=str(michael_cfg["fbx_outfit"]),
        help="Caminho do FBX de roupas Eternal Reunion",
    )
    argument_parser.add_argument(
        "--watch-fbx",
        default=str(michael_cfg["fbx_watch"]),
        help="Caminho do FBX do Relogio de Bolso",
    )
    argument_parser.add_argument(
        "--hair-fbx",
        default=str(michael_cfg["fbx_hair"]),
        help="Caminho do FBX do Cabelo Neko Tied Bob hair",
    )
    argument_parser.add_argument(
        "--face-anim",
        default=str(michael_cfg["face_anim"]),
        help="Caminho do arquivo .anim com expressoes faciais",
    )
    argument_parser.add_argument(
        "--texture-dir",
        default=str(michael_cfg["textures_dir"]),
        help="Diretorio das texturas do Atlas 4x2",
    )
    argument_parser.add_argument(
        "--atlas-png",
        default=Path(michael_cfg["atlas_png"]).name,
        help="Nome do arquivo PNG do Texture Atlas",
    )
    argument_parser.add_argument(
        "--normal-png",
        default=Path(michael_cfg["normal_png"]).name,
        help="Nome do arquivo PNG do flat normal map",
    )
    argument_parser.add_argument(
        "--spec-png",
        default=Path(michael_cfg["spec_png"]).name,
        help="Nome do arquivo PNG do black specular map",
    )
    argument_parser.add_argument(
        "--output-dir",
        default=str(michael_cfg["exported_models_dir"]),
        help="Diretorio de saida dos arquivos .ydd",
    )
    argument_parser.add_argument(
        "--max-verts-per-chunk",
        type=int,
        default=30000,
        help="Maximo de vertices por sub-geometria (uint16)",
    )

    return argument_parser.parse_args(custom_arguments)


if __name__ == "__main__":
    parsed_cli_args = parse_blender_cli_args()
    build_shinano_er_for_gtav(parsed_cli_args)
