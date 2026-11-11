import bpy
import bmesh
import math
import os
import sys
import addon_utils
import mathutils

# Importa o carregador de blendshapes e leitura binaria FBX
sys.path.insert(0, 'E:/FH4_Modding_Tools')
import build_shinano_fh4 as b

addon_utils.enable('sollumz')
from sollumz.sollumz_properties import SollumType, LODLevel
from sollumz.tools.blenderhelper import create_empty_object
from sollumz.tools.drawablehelper import set_recommended_bone_properties, convert_obj_to_model
from sollumz.ydr.shader_materials import create_shader

# 1. Limpeza da cena
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
for m in list(bpy.data.meshes): bpy.data.meshes.remove(m)
for a in list(bpy.data.armatures): bpy.data.armatures.remove(a)
for mat in list(bpy.data.materials): bpy.data.materials.remove(mat)

# 2. Importa esqueleto do Franklin a partir de player_one.yft
print("[INFO] Importando esqueleto do Franklin (player_one.yft)...")
bpy.ops.sollumz.import_assets(directory='E:/waifuv4/gtav_mod/', files=[{'name': 'player_one.yft'}])
f_arm = bpy.data.objects['player_one']

target_bones = set([
    'SKEL_ROOT', 'SKEL_Pelvis', 'SKEL_Spine_Root', 'SKEL_Spine0', 'SKEL_Spine1', 'SKEL_Spine2', 'SKEL_Spine3',
    'SKEL_Neck_1', 'SKEL_Head',
    'SKEL_L_Clavicle', 'SKEL_L_UpperArm', 'SKEL_L_Forearm', 'SKEL_L_Hand',
    'SKEL_R_Clavicle', 'SKEL_R_UpperArm', 'SKEL_R_Forearm', 'SKEL_R_Hand',
    'SKEL_L_Thigh', 'SKEL_L_Calf', 'SKEL_L_Foot', 'SKEL_L_Toe0',
    'SKEL_R_Thigh', 'SKEL_R_Calf', 'SKEL_R_Foot', 'SKEL_R_Toe0'
])
for side in ['L', 'R']:
    for f in range(5):
        for sub in range(3):
            target_bones.add(f'SKEL_{side}_Finger{f}{sub}')

target_bones.add('FACIAL_facialRoot')
target_bones.add('FACIAL_jaw')

bpy.context.view_layer.objects.active = f_arm
bpy.ops.object.mode_set(mode='EDIT')
for b_bone in list(f_arm.data.edit_bones):
    if b_bone.name not in target_bones:
        f_arm.data.edit_bones.remove(b_bone)
bpy.ops.object.mode_set(mode='OBJECT')
print(f"[OK] Esqueleto do Franklin filtrado para {len(f_arm.data.bones)} ossos.")

for o in [bpy.data.objects.get('player_one.mesh'), bpy.data.objects.get('SKEL_ROOT')]:
    if o: bpy.data.objects.remove(o)

# 3. Importa Shinano FBX
print("[INFO] Importando Shinano_Full.fbx...")
bpy.ops.import_scene.fbx(filepath='E:/FH4_Modding_Tools/Shinano_Full.fbx')
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
    fbx_bytes = open(fbx_path, 'rb').read()
    nodes = b.read_fbx_nodes(fbx_bytes)
    objs = next(n for n in nodes if n[0] == 'Objects')[2]
    for c in objs:
        if c[0] == 'Geometry' and len(c[1]) >= 3 and c[1][2] == 'Mesh':
            if c[1][1].split('\x00')[0] != 'Shinano_face':
                continue
            norm_layer = next((cc for cc in c[2] if cc[0] == 'LayerElementNormal'), None)
            norms = next((x[1][0] for x in norm_layer[2] if x[0] == 'Normals'), [])
            norm_idx = next((x[1][0] for x in norm_layer[2] if x[0] == 'NormalsIndex'), [])
            out = []
            for idx in norm_idx:
                out.append((float(norms[idx * 3]), float(norms[idx * 3 + 1]), float(norms[idx * 3 + 2])))
            return out
    return None

body_rest_loop_normals = load_fbx_face_loop_normals('E:/FH4_Modding_Tools/Shinano_Full.fbx')
print(f"[OK] {len(body_rest_loop_normals) if body_rest_loop_normals else 0} normais de loop faciais recuperadas do FBX.")

# Carrega e aplica blendshapes faciais v5 no Body
anim_path = 'E:/waifuv4/Assets/ShinanoDefAdultNewv5.anim'
face_shapes = b.load_anim_blendshapes(anim_path)
print(f"[INFO] Carregando {len(face_shapes)} blendshapes de {anim_path}")

body_obj = bpy.data.objects.get('Body')
if body_obj and body_obj.data.shape_keys:
    for kb in body_obj.data.shape_keys.key_blocks:
        kb.value = 0.0
    act_count = 0
    for name, val in face_shapes.items():
        kb = body_obj.data.shape_keys.key_blocks.get(name)
        if kb:
            kb.value = val
            if val > 0: act_count += 1
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
            kb = obj.data.shape_keys.key_blocks.get(s_name)
            if kb:
                kb.value = s_val

bpy.context.view_layer.update()


# Calculo de pesos da mandibula (FACIAL_jaw) atraves do shape key vrc.v_aa
body_jaw_weights = {}
orig_body_obj = bpy.data.objects.get("Body")
if orig_body_obj and orig_body_obj.data.shape_keys:
    kb_aa = orig_body_obj.data.shape_keys.key_blocks.get("vrc.v_aa")
    basis = orig_body_obj.data.shape_keys.key_blocks.get("Basis")
    if kb_aa and basis:
        for v in orig_body_obj.data.vertices:
            dz = kb_aa.data[v.index].co.z - basis.data[v.index].co.z
            if dz < -0.0005:
                w_val = min(0.35, max(0.0, (abs(dz) / 0.0075) * 0.35))
                body_jaw_weights[v.index] = w_val
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
    if any(k in name for k in ['Finger', 'Thumb', 'Index', 'Middle', 'Ring', 'Little', 'Hand']):
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

dg = bpy.context.evaluated_depsgraph_get()
processed_objs = []
kept_body_normals = None

head_pivot = mathutils.Vector((0.0, 0.0124, 1.1323))
head_scale = 1.10

for mesh_name in include_mesh_names:
    src_obj = bpy.data.objects.get(mesh_name)
    if not src_obj:
        continue
    
    # Avalia com deformacoes aplicadas
    eval_obj = src_obj.evaluated_get(dg)
    new_mesh = bpy.data.meshes.new_from_object(eval_obj)
    
    # Triangula malha e remove faces de alpha no Body
    bm = bmesh.new()
    bm.from_mesh(new_mesh)
    if mesh_name == 'Body':
        alpha_indices = [i for i, m in enumerate(src_obj.data.materials) if 'alpha' in m.name.lower()]
        orig_loop_layer = bm.loops.layers.int.new("orig_loop_idx")
        l_counter = 0
        for f in bm.faces:
            for l in f.loops:
                l[orig_loop_layer] = l_counter
                l_counter += 1
        if alpha_indices:
            del_faces = [f for f in bm.faces if f.material_index in alpha_indices]
            bmesh.ops.delete(bm, geom=del_faces, context='FACES')
            del_verts = [v for v in bm.verts if not v.link_faces]
            bmesh.ops.delete(bm, geom=del_verts, context='VERTS')
        bmesh.ops.triangulate(bm, faces=bm.faces)
        kept_loop_indices = []
        for f in bm.faces:
            f.smooth = True
            for l in f.loops:
                kept_loop_indices.append(l[orig_loop_layer])
        bm.to_mesh(new_mesh)
        bm.free()
        new_mesh.update()
        print(f"[OK] Body triangulado: {len(new_mesh.vertices)} vertices.")
    else:
        bmesh.ops.triangulate(bm, faces=bm.faces)
        for f in bm.faces:
            f.smooth = True
        bm.to_mesh(new_mesh)
        bm.free()
        new_mesh.update()

    # Aplica escala 1.1x na cabeca, rosto e cabelo para restaurar proporcao correta do anime
    is_head_component = mesh_name in ['Body', 'Hair_back', 'Hair_bang', 'Hair_base', 'Hair_side', 'Other_ear']

    for v in new_mesh.vertices:
        co = v.co.copy()
        if is_head_component:
            rel = co - head_pivot
            co = head_pivot + (rel * head_scale)
        v.co.x = co.x * scale_factor
        v.co.y = co.y * scale_factor
        v.co.z = co.z * scale_factor + z_offset

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
    vert_weights = {i: {} for i in range(len(new_mesh.vertices))}
    for vg in src_obj.vertex_groups:
        tgt_bone = get_target_bone(vg.name)
        for v in src_obj.data.vertices:
            if v.index < len(new_mesh.vertices):
                for g in v.groups:
                    if g.group == vg.index and g.weight > 0.001:
                        vert_weights[v.index][tgt_bone] = vert_weights[v.index].get(tgt_bone, 0.0) + g.weight
    
    for v_idx, weights in vert_weights.items():
        total_w = sum(weights.values())
        if total_w > 0:
            for tgt_bone, w in weights.items():
                vg = new_obj.vertex_groups.get(tgt_bone)
                if not vg:
                    vg = new_obj.vertex_groups.new(name=tgt_bone)
                vg.add([v_idx], w / total_w, 'ADD')
        else:
            def_bone = 'SKEL_Head' if mesh_name in ['Body', 'Hair_bang', 'Hair_side', 'Hair_back', 'Other_ear'] else 'SKEL_Pelvis'
            vg = new_obj.vertex_groups.get(def_bone)
            if not vg:
                vg = new_obj.vertex_groups.new(name=def_bone)
            vg.add([v_idx], 1.0, 'REPLACE')
            

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
for o in [s_arm] + [bpy.data.objects.get(n) for n in list(include_mesh_names) if bpy.data.objects.get(n)]:
    bpy.data.objects.remove(o)

# 5. Une todas as malhas processadas
bpy.ops.object.select_all(action='DESELECT')
for o in processed_objs:
    o.select_set(True)
bpy.context.view_layer.objects.active = processed_objs[0]
bpy.ops.object.join()
joined_mesh_obj = processed_objs[0]
joined_mesh_obj.name = "SKEL_ROOT"

for p in joined_mesh_obj.data.polygons:
    p.use_smooth = True
joined_mesh_obj.data.update()

for vg in list(joined_mesh_obj.vertex_groups):
    if vg.name not in target_bones:
        joined_mesh_obj.vertex_groups.remove(vg)

bpy.context.view_layer.objects.active = joined_mesh_obj
bpy.ops.object.vertex_group_limit_total(limit=4)
bpy.ops.object.vertex_group_normalize_all()
print(f"[OK] Malha consolidada com {len(joined_mesh_obj.data.vertices)} vertices.")

# 6. Materiais com Shader ped_default.sps e Atlas 2x2 atualizado
atlas_tex_path = 'E:/gtav_mod_franklin/textures/shinano_atlas_2k.png'
norm_tex_path = 'E:/gtav_mod_franklin/textures/shinano_flat_normal.png'
spec_tex_path = 'E:/gtav_mod_franklin/textures/shinano_black_spec.png'

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

    for n in s_mat.node_tree.nodes:
        if n.name == 'bumpiness' and hasattr(n, 'set_float'):
            n.set_float(0.0)
        elif n.name == 'StubbleControl' and hasattr(n, 'set_vec2'):
            n.set_vec2((0.0, 0.0))
        elif n.name == 'detailSettings' and hasattr(n, 'set_vec4'):
            n.set_vec3((0.0, 0.0, 0.0))
        elif n.name == 'specularIntensityMult' and hasattr(n, 'set_float'):
            n.set_float(0.0)
        elif n.name == 'specularFalloffMult' and hasattr(n, 'set_float'):
            n.set_float(1.0)
        elif n.name == 'specularFresnel' and hasattr(n, 'set_float'):
            n.set_float(0.0)
            
    shader_materials[mat_name] = s_mat

slot_to_key = {}
for i, m in enumerate(joined_mesh_obj.data.materials):
    if not m: continue
    matched = False
    for k, s_mat in shader_materials.items():
        if k.lower() in m.name.lower():
            joined_mesh_obj.data.materials[i] = s_mat
            slot_to_key[i] = k
            matched = True
            break
    if not matched:
        joined_mesh_obj.data.materials[i] = shader_materials['Shinano_costume']
        slot_to_key[i] = 'Shinano_costume'

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
    all_normals = [tuple(l.normal) for l in joined_mesh_obj.data.loops]
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
                    nx = v_co.x * 2.2
                    ny = -1.0
                    nz = (v_co.z - 0.69) * 1.4
                    ln = math.sqrt(nx*nx + ny*ny + nz*nz)
                    all_normals[l_idx] = (nx / ln, ny / ln, nz / ln)
        elif m_key == 'Shinano_body':
            for l_idx in poly.loop_indices:
                v_co = verts[loops[l_idx].vertex_index].co
                if v_co.y < -0.015 and 0.55 < v_co.z < 0.65 and abs(v_co.x) < 0.065:
                    nx = v_co.x * 3.5
                    ny = -1.0
                    nz = -0.1
                    ln = math.sqrt(nx*nx + ny*ny + nz*nz)
                    all_normals[l_idx] = (nx / ln, ny / ln, nz / ln)

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
out_dir = 'E:/gtav_mod_franklin/output/'
os.makedirs(out_dir, exist_ok=True)
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
