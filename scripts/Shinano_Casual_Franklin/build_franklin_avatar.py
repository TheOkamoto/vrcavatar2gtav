import bpy
import bmesh
import json
import math
import os as operating_system
import re as regex_module
import struct
import sys
import zlib
from pathlib import Path
import addon_utils
import mathutils

# Resolucao dinamica via vrc2gtav.cfg (compativel com ambos espelhos)
_CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_CANDIDATE = _CURRENT_SCRIPT_DIR.parent.parent
for _tools_candidate in (
    _REPO_ROOT_CANDIDATE / "scripts" / "common_tools",
    _REPO_ROOT_CANDIDATE / "_deploy_tools",
):
    if _tools_candidate.is_dir() and str(_tools_candidate) not in sys.path:
        sys.path.insert(0, str(_tools_candidate))

import vrc2gtav_paths as project_paths

FRANKLIN_CFG = project_paths.get_character_paths("franklin")


def load_anim_blendshapes(anim_filepath):
    """Extrai blendshapes faciais estaticas de um arquivo Unity .anim (YAML)."""
    shapes_map = {}
    if not operating_system.path.exists(anim_filepath):
        return shapes_map
    with open(anim_filepath, "r", encoding="utf-8") as anim_handle:
        raw_text = anim_handle.read()
    animation_blocks = raw_text.split("  - serializedVersion: 2")
    for curve_block in animation_blocks[1:]:
        val_match = regex_module.search(r"value:\s*([-\d.]+)", curve_block)
        attr_match = regex_module.search(r"attribute:\s*([^\n]+)", curve_block)
        path_match = regex_module.search(r"path:\s*([^\n]+)", curve_block)
        if val_match and attr_match and path_match:
            raw_val = float(val_match.group(1))
            attr_name = attr_match.group(1).strip()
            shape_name = attr_name.replace("blendShape.", "").strip()
            if shape_name.startswith('"'):
                try:
                    shape_name = json.loads(shape_name)
                except Exception:
                    shape_name = shape_name.strip('"')
            if abs(raw_val) > 1e-4:
                shapes_map[shape_name] = raw_val / 100.0
            else:
                shapes_map[shape_name] = 0.0
    return shapes_map


def read_fbx_nodes(fbx_bytes):
    """Leitor binario autonomo de nos FBX (versoes <7500 e >=7500)."""
    fbx_version = struct.unpack_from("<I", fbx_bytes, 23)[0]
    is_64bit = fbx_version >= 7500
    header_fmt = "<QQQB" if is_64bit else "<IIIB"
    header_size = 25 if is_64bit else 13

    def parse_property(cursor_pos):
        type_char = chr(fbx_bytes[cursor_pos])
        cursor_pos += 1
        if type_char == "Y":
            return struct.unpack_from("<h", fbx_bytes, cursor_pos)[0], cursor_pos + 2
        if type_char == "C":
            return bool(fbx_bytes[cursor_pos]), cursor_pos + 1
        if type_char == "I":
            return struct.unpack_from("<i", fbx_bytes, cursor_pos)[0], cursor_pos + 4
        if type_char == "F":
            return struct.unpack_from("<f", fbx_bytes, cursor_pos)[0], cursor_pos + 4
        if type_char == "D":
            return struct.unpack_from("<d", fbx_bytes, cursor_pos)[0], cursor_pos + 8
        if type_char == "L":
            return struct.unpack_from("<q", fbx_bytes, cursor_pos)[0], cursor_pos + 8
        if type_char in ("S", "R"):
            str_len = struct.unpack_from("<I", fbx_bytes, cursor_pos)[0]
            cursor_pos += 4
            raw_slice = fbx_bytes[cursor_pos : cursor_pos + str_len]
            decoded_val = raw_slice.decode("utf-8", errors="replace") if type_char == "S" else raw_slice
            return decoded_val, cursor_pos + str_len
        if type_char in ("f", "d", "l", "i", "b"):
            arr_len, encoding_flag, comp_len = struct.unpack_from("<III", fbx_bytes, cursor_pos)
            cursor_pos += 12
            raw_slice = fbx_bytes[cursor_pos : cursor_pos + comp_len]
            cursor_pos += comp_len
            if encoding_flag == 1:
                raw_slice = zlib.decompress(raw_slice)
            type_map = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "B"}
            return struct.unpack(f"<{arr_len}{type_map[type_char]}", raw_slice), cursor_pos
        raise ValueError(f"Tipo de propriedade FBX desconhecido: {type_char}")

    def parse_node(cursor_pos):
        end_offset, num_props, prop_len, name_len = struct.unpack_from(header_fmt, fbx_bytes, cursor_pos)
        if end_offset == 0:
            return None, cursor_pos + header_size
        cursor_pos += header_size
        node_name = fbx_bytes[cursor_pos : cursor_pos + name_len].decode("utf-8", errors="replace")
        cursor_pos += name_len
        properties_list = []
        prop_end = cursor_pos + prop_len
        for _ in range(num_props):
            prop_val, cursor_pos = parse_property(cursor_pos)
            properties_list.append(prop_val)
        cursor_pos = prop_end
        children_list = []
        while cursor_pos < end_offset:
            child_node, cursor_pos = parse_node(cursor_pos)
            if child_node is None:
                break
            children_list.append(child_node)
        return (node_name, properties_list, children_list), end_offset

    scan_pos = 27
    nodes_list = []
    while scan_pos < len(fbx_bytes) - header_size:
        parsed_node, scan_pos = parse_node(scan_pos)
        if parsed_node is None:
            break
        nodes_list.append(parsed_node)
    return nodes_list

addon_utils.enable('sollumz')
from sollumz.sollumz_properties import SollumType, LODLevel
from sollumz.tools.blenderhelper import create_empty_object
from sollumz.tools.drawablehelper import set_recommended_bone_properties, convert_obj_to_model
from sollumz.ydr.shader_materials import create_shader

# 1. Limpeza da cena
for scene_obj in list(bpy.data.objects):
    bpy.data.objects.remove(scene_obj)
for mesh_block in list(bpy.data.meshes):
    bpy.data.meshes.remove(mesh_block)
for armature_block in list(bpy.data.armatures):
    bpy.data.armatures.remove(armature_block)
for mat_block in list(bpy.data.materials):
    bpy.data.materials.remove(mat_block)

# 2. Importa esqueleto do Franklin a partir do .yft configurado
skeleton_yft_path = Path(FRANKLIN_CFG["skeleton_yft"])
print(f"[INFO] Importando esqueleto do Franklin ({skeleton_yft_path.name})...")
bpy.ops.sollumz.import_assets(
    directory=str(skeleton_yft_path.parent) + "/",
    files=[{"name": skeleton_yft_path.name}],
)
skeleton_arm_name = skeleton_yft_path.stem
f_arm = bpy.data.objects.get(skeleton_arm_name) or bpy.data.objects["player_one"]

target_bones = set([
    'SKEL_ROOT', 'SKEL_Pelvis', 'SKEL_Spine_Root', 'SKEL_Spine0', 'SKEL_Spine1', 'SKEL_Spine2', 'SKEL_Spine3',
    'SKEL_Neck_1', 'SKEL_Head',
    'SKEL_L_Clavicle', 'SKEL_L_UpperArm', 'SKEL_L_Forearm', 'SKEL_L_Hand',
    'SKEL_R_Clavicle', 'SKEL_R_UpperArm', 'SKEL_R_Forearm', 'SKEL_R_Hand',
    'SKEL_L_Thigh', 'SKEL_L_Calf', 'SKEL_L_Foot', 'SKEL_L_Toe0',
    'SKEL_R_Thigh', 'SKEL_R_Calf', 'SKEL_R_Foot', 'SKEL_R_Toe0'
])
for side in ['L', 'R']:
    for finger_idx in range(5):
        for sub in range(3):
            target_bones.add(f'SKEL_{side}_Finger{finger_idx}{sub}')

target_bones.add('FACIAL_facialRoot')
target_bones.add('FACIAL_jaw')

bpy.context.view_layer.objects.active = f_arm
bpy.ops.object.mode_set(mode='EDIT')
for b_bone in list(f_arm.data.edit_bones):
    if b_bone.name not in target_bones:
        f_arm.data.edit_bones.remove(b_bone)
bpy.ops.object.mode_set(mode='OBJECT')
print(f"[OK] Esqueleto do Franklin filtrado para {len(f_arm.data.bones)} ossos.")

for cleanup_obj in [
    bpy.data.objects.get(f"{skeleton_arm_name}.mesh"),
    bpy.data.objects.get("player_one.mesh"),
    bpy.data.objects.get("SKEL_ROOT"),
]:
    if cleanup_obj:
        bpy.data.objects.remove(cleanup_obj)

# 3. Importa Shinano FBX
source_fbx_path = str(FRANKLIN_CFG["source_fbx"])
print(f"[INFO] Importando {Path(source_fbx_path).name}...")
bpy.ops.import_scene.fbx(filepath=source_fbx_path)
s_arm = bpy.data.objects['Armature']

# Rotaciona bracos para a postura A-pose do Franklin (-55 graus)
bpy.context.view_layer.objects.active = s_arm
bpy.ops.object.mode_set(mode='POSE')
s_arm.pose.bones['Upper_arm.L'].rotation_mode = 'XYZ'
s_arm.pose.bones['Upper_arm.L'].rotation_euler = (-math.radians(55), 0, 0)
s_arm.pose.bones['Upper_arm.R'].rotation_mode = 'XYZ'
s_arm.pose.bones['Upper_arm.R'].rotation_euler = (-math.radians(55), 0, 0)
bpy.ops.object.mode_set(mode='OBJECT')

# 4. Le normais faciais IndexToDirect do binario FBX
def load_fbx_face_loop_normals(fbx_path):
    with open(fbx_path, 'rb') as fbx_file:
        fbx_bytes = fbx_file.read()
    nodes = read_fbx_nodes(fbx_bytes)
    objs = next(node_item for node_item in nodes if node_item[0] == 'Objects')[2]
    for child_item in objs:
        if child_item[0] == 'Geometry' and len(child_item[1]) >= 3 and child_item[1][2] == 'Mesh':
            if child_item[1][1].split('\x00')[0] != 'Shinano_face':
                continue
            norm_layer = next((sub_child for sub_child in child_item[2] if sub_child[0] == 'LayerElementNormal'), None)
            norms = next((layer_prop[1][0] for layer_prop in norm_layer[2] if layer_prop[0] == 'Normals'), [])
            norm_idx = next((layer_prop[1][0] for layer_prop in norm_layer[2] if layer_prop[0] == 'NormalsIndex'), [])
            out = []
            for idx in norm_idx:
                out.append((float(norms[idx * 3]), float(norms[idx * 3 + 1]), float(norms[idx * 3 + 2])))
            return out
    return None

body_rest_loop_normals = load_fbx_face_loop_normals(source_fbx_path)
print(f"[OK] {len(body_rest_loop_normals) if body_rest_loop_normals else 0} normais de loop faciais recuperadas do FBX.")

# Carrega e aplica blendshapes faciais v5 no Body
anim_path = str(FRANKLIN_CFG["face_anim"])
face_shapes = load_anim_blendshapes(anim_path)
print(f"[INFO] Carregando {len(face_shapes)} blendshapes de {anim_path}")

body_obj = bpy.data.objects.get('Body')
if body_obj and body_obj.data.shape_keys:
    for key_block in body_obj.data.shape_keys.key_blocks:
        key_block.value = 0.0
    act_count = 0
    for name, val in face_shapes.items():
        key_block = body_obj.data.shape_keys.key_blocks.get(name)
        if key_block:
            key_block.value = val
            if val > 0:
                act_count += 1
    print(f"[OK] {act_count} blendshapes aplicadas no Body.")

# Aplica shrink blendshapes nas roupas para nao vazar o corpo
mesh_shape_presets = {
    'Body_base': {
        'Shrink_tights': 1.0, 'Shrink_boots': 1.0, 'Shrink_dress': 1.0,
        'Shrink_skirt': 1.0, 'Shrink_sweater': 1.0, 'Corset': 1.0, 'Toe_heels': 1.0
    },
    'Cloth_tights': {
        'Shrink_boots': 1.0, 'Corset': 1.0, 'Toe_heels': 1.0
    },
    'Cloth_dress': {
        'Ribbon_OFF': 1.0, 'Corset_OFF': 1.0
    },
    'Cloth_skirt': {
        'Corset_OFF': 1.0
    }
}
for m_name, sh_dict in mesh_shape_presets.items():
    obj = bpy.data.objects.get(m_name)
    if obj and obj.data.shape_keys:
        for s_name, s_val in sh_dict.items():
            key_block = obj.data.shape_keys.key_blocks.get(s_name)
            if key_block:
                key_block.value = s_val

bpy.context.view_layer.update()


# Calculo de pesos da mandibula (FACIAL_jaw) atraves do shape key vrc.v_aa
body_jaw_weights = {}
orig_body_obj = bpy.data.objects.get("Body")
if orig_body_obj and orig_body_obj.data.shape_keys:
    kb_aa = orig_body_obj.data.shape_keys.key_blocks.get("vrc.v_aa")
    basis = orig_body_obj.data.shape_keys.key_blocks.get("Basis")
    if kb_aa and basis:
        for vertex_item in orig_body_obj.data.vertices:
            delta_z = kb_aa.data[vertex_item.index].co.z - basis.data[vertex_item.index].co.z
            if delta_z < -0.0005:
                w_val = min(0.35, max(0.0, (abs(delta_z) / 0.0075) * 0.35))
                body_jaw_weights[vertex_item.index] = w_val
        print(f"[OK] {len(body_jaw_weights)} vertices mapeados para FACIAL_jaw no Body.")

include_mesh_names = [
    'Body', 'Body_base',
    'Cloth_sweater', 'Cloth_skirt', 'Cloth_tights', 'Cloth_boots',
    'Hair_back', 'Hair_bang', 'Hair_base', 'Hair_side',
    'Other_ear', 'Other_tail'
]

mapping = {
    'Hips': 'SKEL_Pelvis', 'Spine': 'SKEL_Spine1', 'Chest': 'SKEL_Spine2', 'Neck': 'SKEL_Neck_1', 'Head': 'SKEL_Head',
    'LeftEye': 'SKEL_Head', 'RightEye': 'SKEL_Head',
    'Shoulder.L': 'SKEL_L_Clavicle', 'Upper_arm.L': 'SKEL_L_UpperArm', 'Lower_arm.L': 'SKEL_L_Forearm', 'Hand.L': 'SKEL_L_Hand',
    'Shoulder.R': 'SKEL_R_Clavicle', 'Upper_arm.R': 'SKEL_R_UpperArm', 'Lower_arm.R': 'SKEL_R_Forearm', 'Hand.R': 'SKEL_R_Hand',
    'Upper_leg.L': 'SKEL_L_Thigh', 'Lower_leg.L': 'SKEL_L_Calf', 'Foot.L': 'SKEL_L_Foot', 'Toe.L': 'SKEL_L_Toe0',
    'Upper_leg.R': 'SKEL_R_Thigh', 'Lower_leg.R': 'SKEL_R_Calf', 'Foot.R': 'SKEL_R_Foot', 'Toe.R': 'SKEL_R_Toe0',
}

def get_target_bone(name):
    if name in mapping:
        return mapping[name]
    # FIX DE MAOS: Consolidacao direta de todos os vertices de dedos e maos em SKEL_L_Hand e SKEL_R_Hand
    # para eliminar achatamento e torcao gerados pelos ossos masculinos do GTA V
    if any(keyword in name for keyword in ['Finger', 'Thumb', 'Index', 'Middle', 'Ring', 'Little', 'Hand']):
        side = 'L' if ('.L' in name or 'Left' in name or '_L' in name) else 'R'
        return f'SKEL_{side}_Hand'
    if name.startswith('Hair_') or name.startswith('Other_ear'):
        return 'SKEL_Head'
    if name.startswith('Breast_') or name.startswith('Ribbon'):
        return 'SKEL_Spine2'
    if name.startswith('Butt.L'):
        return 'SKEL_L_Thigh'
    if name.startswith('Butt.R'):
        return 'SKEL_R_Thigh'
    if 'support' in name:
        side = 'L' if ('.L' in name or 'Left' in name or '_L' in name) else 'R'
        if 'Lower' in name or 'support2' in name or 'support3' in name:
            return f'SKEL_{side}_Forearm'
        return f'SKEL_{side}_UpperArm'
    if name.startswith('Skirt_'):
        if '.L' in name:
            return 'SKEL_L_Thigh'
        if '.R' in name:
            return 'SKEL_R_Thigh'
        return 'SKEL_Pelvis'
    if name.startswith('Tail') or name.startswith('Belt'):
        return 'SKEL_Pelvis'
    return 'SKEL_Pelvis'

scale_factor = (0.640 - (-0.907)) / (1.132 - 0.106)
z_offset = -0.907 - (0.106 * scale_factor)

depsgraph = bpy.context.evaluated_depsgraph_get()
processed_objs = []
kept_body_normals = None

head_pivot = mathutils.Vector((0.0, 0.0124, 1.1323))
head_scale = 1.10

for mesh_name in include_mesh_names:
    src_obj = bpy.data.objects.get(mesh_name)
    if not src_obj:
        continue
    
    # Avalia com deformacoes aplicadas
    eval_obj = src_obj.evaluated_get(depsgraph)
    new_mesh = bpy.data.meshes.new_from_object(eval_obj)
    
    # Triangula malha e remove faces de alpha no Body
    bm_data = bmesh.new()
    bm_data.from_mesh(new_mesh)
    if mesh_name == 'Body':
        alpha_indices = [mat_idx for mat_idx, mat_item in enumerate(src_obj.data.materials) if 'alpha' in mat_item.name.lower()]
        orig_loop_layer = bm_data.loops.layers.int.new("orig_loop_idx")
        l_counter = 0
        for face_elem in bm_data.faces:
            for loop_item in face_elem.loops:
                loop_item[orig_loop_layer] = l_counter
                l_counter += 1
        if alpha_indices:
            del_faces = [face_elem for face_elem in bm_data.faces if face_elem.material_index in alpha_indices]
            bmesh.ops.delete(bm_data, geom=del_faces, context='FACES')
            del_verts = [vert_item for vert_item in bm_data.verts if not vert_item.link_faces]
            bmesh.ops.delete(bm_data, geom=del_verts, context='VERTS')
        bmesh.ops.triangulate(bm_data, faces=bm_data.faces)
        kept_loop_indices = []
        for face_elem in bm_data.faces:
            face_elem.smooth = True
            for loop_item in face_elem.loops:
                kept_loop_indices.append(loop_item[orig_loop_layer])
        bm_data.to_mesh(new_mesh)
        bm_data.free()
        new_mesh.update()
        print(f"[OK] Body triangulado: {len(new_mesh.vertices)} vertices.")
    else:
        bmesh.ops.triangulate(bm_data, faces=bm_data.faces)
        for face_elem in bm_data.faces:
            face_elem.smooth = True
        bm_data.to_mesh(new_mesh)
        bm_data.free()
        new_mesh.update()

    # Aplica escala 1.1x na cabeca, rosto e cabelo para restaurar proporcao correta do anime
    is_head_component = mesh_name in ['Body', 'Hair_back', 'Hair_bang', 'Hair_base', 'Hair_side', 'Other_ear']

    for vert_item in new_mesh.vertices:
        vert_coord = vert_item.co.copy()
        if is_head_component:
            rel = vert_coord - head_pivot
            vert_coord = head_pivot + (rel * head_scale)
        vert_item.co.x = vert_coord.x * scale_factor
        vert_item.co.y = vert_coord.y * scale_factor
        vert_item.co.z = vert_coord.z * scale_factor + z_offset

    if mesh_name == 'Body' and body_rest_loop_normals and len(kept_loop_indices) == len(new_mesh.loops):
        kept_body_normals = [body_rest_loop_normals[idx] for idx in kept_loop_indices]
        print(f"[OK] Preparadas {len(kept_body_normals)} normais customizadas para o Body.")
    new_mesh.update()

    new_obj = bpy.data.objects.new(f"proc_{mesh_name}", new_mesh)
    bpy.context.collection.objects.link(new_obj)

    # Materiais (ignora alpha no Body)
    for mat in src_obj.data.materials:
        if mesh_name == 'Body' and 'alpha' in mat.name.lower():
            continue
        new_obj.data.materials.append(mat)
    
    # Mapeamento de grupos de vertices
    vert_weights = {vert_idx: {} for vert_idx in range(len(new_mesh.vertices))}
    for vgroup in src_obj.vertex_groups:
        tgt_bone = get_target_bone(vgroup.name)
        for src_vert in src_obj.data.vertices:
            if src_vert.index < len(new_mesh.vertices):
                for group_weight in src_vert.groups:
                    if group_weight.group == vgroup.index and group_weight.weight > 0.001:
                        vert_weights[src_vert.index][tgt_bone] = vert_weights[src_vert.index].get(tgt_bone, 0.0) + group_weight.weight
    
    for v_idx, weights in vert_weights.items():
        total_w = sum(weights.values())
        if total_w > 0:
            for tgt_bone, weight_val in weights.items():
                vgroup = new_obj.vertex_groups.get(tgt_bone)
                if not vgroup:
                    vgroup = new_obj.vertex_groups.new(name=tgt_bone)
                vgroup.add([v_idx], weight_val / total_w, 'ADD')
        else:
            def_bone = 'SKEL_Head' if mesh_name in ['Body', 'Hair_bang', 'Hair_side', 'Hair_back', 'Other_ear'] else 'SKEL_Pelvis'
            vgroup = new_obj.vertex_groups.get(def_bone)
            if not vgroup:
                vgroup = new_obj.vertex_groups.new(name=def_bone)
            vgroup.add([v_idx], 1.0, 'REPLACE')
            

    if mesh_name == "Body" and body_jaw_weights:
        jaw_vg = new_obj.vertex_groups.get("FACIAL_jaw")
        if not jaw_vg:
            jaw_vg = new_obj.vertex_groups.new(name="FACIAL_jaw")
        head_vg = new_obj.vertex_groups.get("SKEL_Head")
        if not head_vg:
            head_vg = new_obj.vertex_groups.new(name="SKEL_Head")
        for v_idx, jaw_w in body_jaw_weights.items():
            if v_idx < len(new_mesh.vertices):
                jaw_vg.add([v_idx], jaw_w, "REPLACE")
                head_vg.add([v_idx], max(0.0, 1.0 - jaw_w), "REPLACE")
        print(f"[OK] Pesos de FACIAL_jaw e SKEL_Head aplicados na malha processada do Body.")

    processed_objs.append(new_obj)

# Limpa objetos temporarios
for temp_obj in [s_arm] + [bpy.data.objects.get(mesh_name_item) for mesh_name_item in list(include_mesh_names) if bpy.data.objects.get(mesh_name_item)]:
    bpy.data.objects.remove(temp_obj)

# 5. Une todas as malhas processadas
bpy.ops.object.select_all(action='DESELECT')
for proc_obj in processed_objs:
    proc_obj.select_set(True)
bpy.context.view_layer.objects.active = processed_objs[0]
bpy.ops.object.join()
joined_mesh_obj = processed_objs[0]
joined_mesh_obj.name = "SKEL_ROOT"

for poly_face in joined_mesh_obj.data.polygons:
    poly_face.use_smooth = True
joined_mesh_obj.data.update()

for vgroup in list(joined_mesh_obj.vertex_groups):
    if vgroup.name not in target_bones:
        joined_mesh_obj.vertex_groups.remove(vgroup)

bpy.context.view_layer.objects.active = joined_mesh_obj
bpy.ops.object.vertex_group_limit_total(limit=4)
bpy.ops.object.vertex_group_normalize_all()
print(f"[OK] Malha consolidada com {len(joined_mesh_obj.data.vertices)} vertices.")

# 6. Materiais com Shader ped_default.sps e Atlas 2x2 atualizado
atlas_tex_path = str(FRANKLIN_CFG["atlas_png"])
norm_tex_path = str(FRANKLIN_CFG["normal_png"])
spec_tex_path = str(FRANKLIN_CFG["spec_png"])

atlas_img = bpy.data.images.load(atlas_tex_path)
flat_norm_img = bpy.data.images.load(norm_tex_path)
black_spec_img = bpy.data.images.load(spec_tex_path)

quadrant_map = {
    'Shinano_face':    (0.0, 0.5),
    'Shinano_body':    (0.5, 0.5),
    'Shinano_costume': (0.0, 0.0),
    'Shinano_hair':    (0.5, 0.0),
}

shader_materials = {}
for mat_name in ['Shinano_face', 'Shinano_body', 'Shinano_costume', 'Shinano_hair']:
    s_mat = create_shader('ped_default.sps')
    s_mat.name = mat_name

    diff_node = s_mat.node_tree.nodes.get('DiffuseSampler')
    if diff_node:
        diff_node.image = atlas_img
        diff_node.texture_properties.embedded = False

    bump_node = s_mat.node_tree.nodes.get('BumpSampler')
    if bump_node:
        bump_node.image = flat_norm_img
        bump_node.texture_properties.embedded = False

    spec_node = s_mat.node_tree.nodes.get('SpecSampler')
    if spec_node:
        spec_node.image = black_spec_img
        spec_node.texture_properties.embedded = False

    for shader_node in s_mat.node_tree.nodes:
        if shader_node.name == 'bumpiness' and hasattr(shader_node, 'set_float'):
            shader_node.set_float(0.0)
        elif shader_node.name == 'StubbleControl' and hasattr(shader_node, 'set_vec2'):
            shader_node.set_vec2((0.0, 0.0))
        elif shader_node.name == 'detailSettings' and hasattr(shader_node, 'set_vec4'):
            shader_node.set_vec3((0.0, 0.0, 0.0))
        elif shader_node.name == 'specularIntensityMult' and hasattr(shader_node, 'set_float'):
            shader_node.set_float(0.0)
        elif shader_node.name == 'specularFalloffMult' and hasattr(shader_node, 'set_float'):
            shader_node.set_float(1.0)
        elif shader_node.name == 'specularFresnel' and hasattr(shader_node, 'set_float'):
            shader_node.set_float(0.0)
            
    shader_materials[mat_name] = s_mat

slot_to_key = {}
for slot_idx, mat_item in enumerate(joined_mesh_obj.data.materials):
    if not mat_item:
        continue
    matched = False
    for mat_key, s_mat in shader_materials.items():
        if mat_key.lower() in mat_item.name.lower():
            joined_mesh_obj.data.materials[slot_idx] = s_mat
            slot_to_key[slot_idx] = mat_key
            matched = True
            break
    if not matched:
        joined_mesh_obj.data.materials[slot_idx] = shader_materials['Shinano_costume']
        slot_to_key[slot_idx] = 'Shinano_costume'

# Remapeamento UV para o Atlas 2x2
uv_layer = joined_mesh_obj.data.uv_layers[0]
uv_layer.name = 'UVMap 0'
for poly in joined_mesh_obj.data.polygons:
    m_key = slot_to_key.get(poly.material_index, 'Shinano_costume')
    u_off, v_off = quadrant_map[m_key]
    for loop_idx in poly.loop_indices:
        uv_coord = uv_layer.data[loop_idx].uv
        uv_coord.x = uv_coord.x * 0.5 + u_off
        uv_coord.y = uv_coord.y * 0.5 + v_off

bpy.context.view_layer.objects.active = joined_mesh_obj
bpy.ops.sollumz.color_attrs_add_missing()
bpy.ops.sollumz.uv_maps_add_missing()

ca1 = joined_mesh_obj.data.color_attributes.get('Color 1')
if ca1:
    for c_data in ca1.data:
        c_data.color = (1.0, 1.0, 1.0, 1.0)

ca2 = joined_mesh_obj.data.color_attributes.get('Color 2')
if ca2:
    for c_data in ca2.data:
        c_data.color = (0.0, 0.0, 0.0, 0.0)

# Normais suaves do rosto
if kept_body_normals:
    joined_mesh_obj.data.calc_normals_split()
    all_normals = [tuple(loop_elem.normal) for loop_elem in joined_mesh_obj.data.loops]
    n_face_loops = len(kept_body_normals)
    all_normals[:n_face_loops] = kept_body_normals

    verts = joined_mesh_obj.data.vertices
    loops = joined_mesh_obj.data.loops
    for poly in joined_mesh_obj.data.polygons:
        m_key = slot_to_key.get(poly.material_index, 'Shinano_costume')
        if m_key == 'Shinano_face':
            for l_idx in poly.loop_indices:
                v_co = verts[loops[l_idx].vertex_index].co
                if v_co.y < -0.045 and 0.61 < v_co.z < 0.77 and abs(v_co.x) < 0.085:
                    norm_x = v_co.x * 2.2
                    norm_y = -1.0
                    norm_z = (v_co.z - 0.69) * 1.4
                    norm_len = math.sqrt(norm_x * norm_x + norm_y * norm_y + norm_z * norm_z)
                    all_normals[l_idx] = (norm_x / norm_len, norm_y / norm_len, norm_z / norm_len)
        elif m_key == 'Shinano_body':
            for l_idx in poly.loop_indices:
                v_co = verts[loops[l_idx].vertex_index].co
                if v_co.y < -0.015 and 0.55 < v_co.z < 0.65 and abs(v_co.x) < 0.065:
                    norm_x = v_co.x * 3.5
                    norm_y = -1.0
                    norm_z = -0.1
                    norm_len = math.sqrt(norm_x * norm_x + norm_y * norm_y + norm_z * norm_z)
                    all_normals[l_idx] = (norm_x / norm_len, norm_y / norm_len, norm_z / norm_len)

    joined_mesh_obj.data.normals_split_custom_set(all_normals)
    joined_mesh_obj.data.update()

import sollumz.ydr.ydrexport as ydrexport
ydrexport.triangulate_mesh = lambda mesh: mesh

# 7. Estrutura Sollumz
ydd_empty = create_empty_object(SollumType.DRAWABLE_DICTIONARY)
ydd_empty.name = 'uppr_008_u'

f_arm.sollum_type = SollumType.DRAWABLE
f_arm.name = 'uppr_008_u'
f_arm.parent = ydd_empty
f_arm.drawable_properties.lod_dist_high = 9998.0
f_arm.drawable_properties.lod_dist_med = 9998.0
f_arm.drawable_properties.lod_dist_low = 9998.0
f_arm.drawable_properties.lod_dist_vlow = 9998.0

for b_bone in f_arm.data.bones:
    set_recommended_bone_properties(b_bone)

convert_obj_to_model(joined_mesh_obj)
joined_mesh_obj.parent = f_arm

mod = joined_mesh_obj.modifiers.new("Armature", 'ARMATURE')
mod.object = f_arm

# 8. Exportacao
out_dir = operating_system.path.join(str(FRANKLIN_CFG["exported_models_dir"]), "")
operating_system.makedirs(out_dir, exist_ok=True)
print("[INFO] Exportando uppr_008_u.ydd, uppr_000_u.ydd e uppr_001_u.ydd para o Franklin...")
bpy.ops.object.select_all(action='DESELECT')
ydd_empty.select_set(True)
bpy.context.view_layer.objects.active = ydd_empty

res = bpy.ops.sollumz.export_assets(
    directory=out_dir,
    direct_export=True,
    use_custom_settings=True,
    target_versions={'GEN8'},
    target_formats={'NATIVE', 'CWXML'},
    limit_to_selected=False
)
print("Export uppr_008_u result:", res)

ydd_empty.name = 'uppr_000_u'
f_arm.name = 'uppr_000_u'
res2 = bpy.ops.sollumz.export_assets(
    directory=out_dir,
    direct_export=True,
    use_custom_settings=True,
    target_versions={'GEN8'},
    target_formats={'NATIVE', 'CWXML'},
    limit_to_selected=False
)
print('Export uppr_000_u result:', res2)

ydd_empty.name = 'uppr_001_u'
f_arm.name = 'uppr_001_u'
res3 = bpy.ops.sollumz.export_assets(
    directory=out_dir,
    direct_export=True,
    use_custom_settings=True,
    target_versions={'GEN8'},
    target_formats={'NATIVE', 'CWXML'},
    limit_to_selected=False
)
print('Export uppr_001_u result:', res3)
print("[OK] Concluido com sucesso!")
