# GUIA MESTRE DEFINITIVO: Implantação de Avatares VRChat no GTA V

## Conversão, Rigging, Lip Sync, Texturas 2K e Deploy dos Três Protagonistas

---

### Resumo Executivo da Configuração

| Protagonista GTA V | Slot Ped | Avatar VRChat | Traje / Estilo | Pasta do Projeto |
| :--- | :--- | :--- | :--- | :--- |
| **Michael De Santa** | `player_zero` | **Shinano** | Eternal Reunion (Vestido Gótico / Maid de Luxo) | `2_Michael_Shinano_EternalReunion/` |
| **Franklin Clinton** | `player_one` | **Shinano** | Casual / Uniforme Escolar (Saia Vermelha, Cabelo Azul) | `1_Franklin_Shinano_Casual/` |
| **Trevor Philips** | `player_two` | **Miltina** | Maid Clássica (Vestido Longo Preto/Branco, Avental) | `3_Trevor_Miltina_Maid/` |

> **Créditos:** Consulte a [Seção 10 — Créditos dos Assets Utilizados](#10-créditos-dos-assets-utilizados) para a lista completa de criadores, links oficiais no BOOTH, avatares base, vestidos, cabelos, acessórios, texturas de olhos e ferramentas.

---

## 1. Estrutura de Diretórios Unificada (`E:\vrc2gtav` / `/mnt/e/vrc2gtav`)

Todo o projeto foi consolidado na pasta raiz **`vrc2gtav`**, estruturado de forma modular e independente de plataforma:

```
vrc2gtav/
├── 1_Franklin_Shinano_Casual/
│   ├── 1_source/              # Referências dos FBX e texturas originais
│   ├── 2_blender/             # Script build_franklin_avatar.py, run_build.py, player_one.yft
│   ├── 3_textures_gtav/       # Script generate_franklin_atlas.py, shinano_franklin_2k.ytd
│   ├── 4_exported_models/     # Modelos compilados (uppr_008_u.ydd, xmls)
│   └── 5_rpf_package/         # Staging e arquivos prontos para o Franklin
│
├── 2_Michael_Shinano_EternalReunion/
│   ├── 1_source/              # Hierarquia do Unity, referências e texturas
│   ├── 2_blender/             # Script build_michael_er.py, run_build.py, player_zero.yft
│   ├── 3_textures_gtav/       # Script generate_er_atlas.py, shinano_michael_er_2k.ytd
│   ├── 4_exported_models/     # Modelos compilados (uppr_000_u.ydd, uppr_000_r.ydd, xmls)
│   └── 5_rpf_package/         # Script deploy_michael_er.py
│
├── 3_Trevor_Miltina_Maid/
│   ├── 1_source/              # Referências de blendshapes FaceEmo e texturas
│   ├── 2_blender/             # Script build_trevor_miltina.py, player_two.yft
│   ├── 3_textures_gtav/       # Script generate_miltina_atlas.py, miltina_maid.ytd
│   ├── 4_exported_models/     # Modelos compilados (uppr_000_u.ydd, uppr_000_r.ydd, xmls)
│   └── 5_rpf_package/         # Script apply_miltina_to_trevor.py
│
├── _deploy_tools/             # Ferramentas globais de deploy
│   ├── head_000_r.ydd         # Dummy Mesh universal para corpo (629 bytes)
│   ├── p_eyes_dummy.ydd       # Prop Dummy Mesh sem esqueleto para oculos (515 bytes)
│   ├── apply_all_characters.py # Aplica os 3 personagens em todos os slots de uma vez
│   ├── repack_and_deploy_everything.py # Repacota RPFs e instala no GTA V
│   └── vrc2gtav_paths.py      # Leitor do vrc2gtav.cfg + conversor Win/WSL
│
├── vrc2gtav.cfg               # Arquivo mestre INI com TODOS os caminhos (executaveis, FBX, RPFs, etc.)
│
└── scripts/                   # Central de scripts organizados por personagem
    ├── Shinano_Casual_Franklin/
    ├── Shinano_EternalReunion_Michael/
    ├── Miltina_Maid_Trevor/
    └── common_tools/
```

---

## 2. Configuração Centralizada (`vrc2gtav.cfg`) \& Multiplataforma

Todos os caminhos configuráveis (executáveis como Blender, RAGE CLI, Python e FFmpeg; diretórios do Unity `waifuv4`, pasta de mods do GTA V, RPFs extraídos/instalados, `.fbx`, `.anim`, `.yft`, texturas e scripts) ficam centralizados no arquivo `vrc2gtav.cfg`.

O módulo `vrc2gtav_paths.py` lê o `vrc2gtav.cfg` (ou um caminho customizado via variável de ambiente `VRC2GTAV_CFG`) e converte automaticamente entre caminhos Windows (`E:/...`, `D:/...`) e Linux/WSL (`/mnt/e/...`, `/mnt/d/...`):

1. **Para mover o projeto, o GTA V ou o Blender para outro disco/pasta:** edite apenas as seções `[directories]`, `[executables]`, `[rpf_paths]`, `[franklin]`, `[michael]` e `[trevor]` em `vrc2gtav.cfg` — nenhum script `.py` precisa ser alterado.
2. **Suporte Windows Nativo + WSL:** Ao invocar o Blender Windows a partir do Linux/WSL, `build_blender_command()` propaga `VRC2GTAV_CFG` e detecta automaticamente um socket `WSL_INTEROP` ativo.
3. **Variáveis de Ambiente Opcionais:** `VRC2GTAV_CFG` (aponta para outro `.cfg`), `VRC2GTAV_ROOT`, `VRC_ASSETS_DIR`, `GTAV_MODS_DIR`, `RAGE_CLI`, `BLENDER_EXE`.

---

## 3. Arquitetura 3D no Blender e Rigging GTA V

### 3.1 Filtragem do Esqueleto (57 Ossos Essenciais)

Os esqueletos originais do GTA V (`player_zero.yft`, `player_one.yft`, `player_two.yft`) contêm dezenas de ossos auxiliares e de física de tecido que desestabilizam avatares estilizados de anime. Cada personagem é filtrado estritamente para **57 ossos**:

- **Coluna e Tronco:** `SKEL_ROOT`, `SKEL_Pelvis`, `SKEL_Spine_Root`, `SKEL_Spine0`, `SKEL_Spine1`, `SKEL_Spine2`, `SKEL_Spine3`, `SKEL_Neck_1`, `SKEL_Head`.
- **Braços e Clavículas:** `SKEL_L_Clavicle`, `SKEL_L_UpperArm`, `SKEL_L_Forearm`, `SKEL_L_Hand` (e equivalentes `_R_`).
- **Pernas e Pés:** `SKEL_L_Thigh`, `SKEL_L_Calf`, `SKEL_L_Foot`, `SKEL_L_Toe0` (e equivalentes `_R_`).
- **Face / Lip Sync:** `FACIAL_facialRoot` (parentesco com `SKEL_Head`, tag 51105) e `FACIAL_jaw` (parentesco com `FACIAL_facialRoot`, tag 2849).

### 3.2 Correções Críticas de Rigging

1. **Dedos das Mãos:** Mapear os 15 ossos de dedos VRChat para dedos complexos de GTA V causa achatamento dos dedos durante animações de armas. Todos os dedos foram consolidados com peso 1.0 no osso da mão (`SKEL_L_Hand` / `SKEL_R_Hand`), mantendo a pose relaxada e natural perfeita.
2. **Marias-Chiquinhas e Cabelos Laterais (Twintails):**
    - *Problema:* Algoritmos ingênuos que buscam `"tail"` no nome dos ossos atribuíam as marias-chiquinhas da Miltina (`twin tail1_R`, `Twin tail ribbon`) ao osso `SKEL_Pelvis` (cauda do vestido), fazendo o cabelo esticar até o quadril ao caminhar.
    - *Regra Estrita:*\
      if "twin" in low\_name or "pony" in low\_name or "twintail" in low\_name:\
         return "SKEL\_Head"
3. **A-Pose (-55°):** Avatares de VRChat vêm em T-Pose rígida (braços a 90°). Para casar perfeitamente com a postura do GTA V, os braços são rotacionados em **-55° no eixo Y** em relação ao pivô dos ombros.

---

## 4. O Sistema de Lip Sync (Sincronia Labial de Anime)

Para que as personagens mexam a boca ao falar durante cutscenes, ligações telefônicas e falas em gameplay:

```
flowchart TD
    FaceMesh["Malha Facial (Body)"] --> Calibrate["1. Calcular Vértices da Boca (|Δy| < 0.05, z < boca_centro)"]
    Calibrate --> Formula["2. Fórmula de Ponderação Jaw: min(0.35, (|Δz| / 0.0075) * 0.35)"]
    Formula --> HeadWeight["3. Ponderação Head: (1.0 - JawWeight)"]
    HeadWeight --> VGroups["4. Criar Vertex Groups FACIAL_jaw e SKEL_Head ANTES do BMesh"]
    VGroups --> CleanAlpha["5. Remover Decalques de Sombra/Blush via BMesh (Pesos Preservados)"]
    CleanAlpha --> ActiveJoin["6. Definir Body como Objeto Ativo no bpy.ops.object.join()"]
    ActiveJoin --> YDD["7. Exportar Drawable Sollumz (.ydd com 3.193 vértices no FACIAL_jaw)"]
```

### Fórmula de Decaimento Vertical:

$$\\text{peso}*{\\text{jaw}} = \\min\\left(0.35, \\frac{\|\\Delta z\|}{0.0075} \\times 0.35\\right)$$ $$\\text{peso}*{\\text{head}} = 1.0 - \\text{peso}\_{\\text{jaw}}$$

- **Por que o valor máximo é 0.35?** Aberturas ósseas no GTA V foram calibradas para humanos realistas com mandíbulas profundas. Um peso 1.0 em rostos estilizados de anime deforma e estica excessivamente a malha. O valor de 0.35 proporciona uma abertura suave, delicada e fidedigna aos animes.

---

## 5. Texturas e Dicionários .YTD (Padrão 2K e Hash JOAAT)

### 5.1 Limite Obrigatório de 2K (2048x2048)

- Texturas em 4K no GTA V provocam estouro de buffer de streaming de memória e crash do jogo após poucos minutos de gameplay.
- Todos os atlas foram formatados rigorosamente em **2048x2048 pixels**, comprimidos no formato **DXT5 (BC3)** com Mipmaps automáticos via `rage textures build`.

### 5.2 Regra Crítica do Hash JOAAT

A RAGE Engine localiza texturas dentro do arquivo `.ytd` usando o hash numérico Jenkins One-at-a-Time (**JOAAT**). Se os nomes das texturas forem ordenados alfabeticamente no XML da Sollumz, o lookup de ponteiros internos quebra e o modelo fica completamente **preto** ou com texturas trocadas.

- **Ordem Obrigatória de Inclusão no .YTD:**
    1. `miltina_atlas_2k` (ou `shinano_atlas_2k`) — Diffuse Map
    2. `miltina_spec` — Specular Map
    3. `miltina_normal` — Normal Map

---

## 6. Estratégia de Deploy: Universal Slot Replacement \& Dummies

No GTA V, as roupas dos personagens são compostas por múltiplos slots:

- `uppr` (Tronco/Torso), `lowr` (Pernas), `feet` (Sapatos), `head` (Rosto), `hair` (Cabelo), `berd` (Barba), `hand` (Mãos), `teef` (Dentes), `accs` (Acessórios), `task` (Coletes/Armaduras), `jbib` (Jaquetas/Camisas internas).

Se apenas o slot `uppr_000` for substituído, qualquer mudança de roupa nas missões ou safehouses faz com que os braços, calças, sapatos e cabeças masculinas dos protagonistas apareçam e atravessem a waifu.

### A Solução Definitiva:

1. **Avatar Completo no Tronco (`uppr`):** O modelo compilado (`uppr_000_u.ydd`) contém o corpo inteiro (cabeça, cabelo, vestido, braços, pernas, sapatos). Esse modelo e seu `.ytd` são replicados em **todos os slots** **`uppr`** do personagem.
2. **Dummy Mesh de 629 Bytes:** Todas as outras partes humanas (`lowr`, `feet`, `head`, `hair`, `berd`, `hand`, `teef`, `accs`, `task`, `jbib`) são substituídas pelo arquivo `head_000_r.ydd`. Trata-se de uma malha vazia e invisível (1 triângulo degenerado). Nenhuma parte vanilla tem como aparecer.
3. **Dummies de Óculos (`p_eyes_*.ydd` em `streamedpedprops.rpf`):** Todos os 35 drawables de óculos dos três protagonistas (`player_zero_p`: 11, `player_one_p`: 12, `player_two_p`: 12) são substituídos por `p_eyes_dummy.ydd` (515 bytes) — um drawable dictionary rígido dedicado (`HasSkin=0`, sem `<Skeleton>` e sem texturas embutidas), enquanto os `.ytd` de difusa permanecem intactos para preservar o lookup de metadados sem exibir óculos em cutscenes ou gameplay.

---

## 7. Repacotamento RPF7 e Prevenção do `ERR_GEN_ZLIB_2`

O GTA V rejeita arquivos RPF modificados se não atenderem a duas condições fundamentais de baixo nível:

1. **Cabeçalho** **`b'OPEN'`** **(Offset 12):** Os primeiros 16 bytes de cada arquivo RPF contêm o Magic `b'7FPR'` e o indicador de criptografia no offset 12. Os RPFs modificados devem ter esse valor setado para `b'OPEN'` (0x4E45504F), instruindo a engine e o OpenIV a não tentarem decriptação RSA.
2. **Correção do TOC** **`f_size = 0`:** Quando uma ferramenta como o `rage` empacota um RPF dentro de outro RPF (ex: `mppatches.rpf` dentro de `dlc.rpf`), entradas binárias não comprimidas gravadas com tamanho comprimido diferente de zero ativam a exceção interna do zlib no executável do jogo, gerando a janela de erro fatal: $$\\text{ERR\_GEN\_ZLIB\_2} \\quad \\text{("zlib call failed")}$$ O script `repack_and_deploy_everything.py` percorre a tabela de conteúdo (TOC) de cada RPF gerado e zera os bytes 2, 3 e 4 das entradas binárias, eliminando qualquer risco de travamento.

---

## 8. Como Executar (O Orquestrador Mestre Unificado)

Para facilitar a manutenção e evitar ter que rodar comandos manuais individuais, foi criado o script mestre `run_mod_manager.py` (e o inicializador rápido `EXECUTAR_GERENCIADOR.bat`).

### 8.1 Modo Interativo (Recomendado)

No Windows, dê um duplo clique em `EXECUTAR_GERENCIADOR.bat`, ou execute no terminal:

```
python run_mod_manager.py
```

O menu interativo será exibido:

```
======================================================================
         GERENCIADOR DE AVATARES VRChat PARA GTA V
======================================================================
Selecione qual personagem voce deseja trocar/atualizar:
  [1] Michael (player_zero) -> Shinano Eternal Reunion
  [2] Franklin (player_one) -> Shinano Casual / Uniforme
  [3] Trevor   (player_two)  -> Miltina Maid
  [4] Todos os 3 Personagens (Processo Completo)
  [5] Apenas Repacotar e Instalar RPFs no GTA V (Deploy Only)
  [0] Sair
----------------------------------------------------------------------
```

Ao selecionar o personagem, o gerenciador pergunta quais etapas deseja executar (Geração de Texturas 2K, Compilação Blender, e Instalação/Deploy no jogo), permitindo atualizar apenas o que for necessário de forma rápida e segura.

### 8.2 Modo Linha de Comando (Automação / CLI)

Você também pode invocar o script diretamente com argumentos:

```
# Processar apenas o Trevor (Miltina Maid) por completo:
python run_mod_manager.py --character trevor

# Processar todos os 3 personagens de uma vez:
python run_mod_manager.py --character all

# Apenas repacotar os RPFs e instalar no GTA V:
python run_mod_manager.py --deploy-only

# Apenas verificar se todos os pre-requisitos (Blender, RAGE CLI, Python) estao OK:
python run_mod_manager.py --check-env
```

---

## 9. Execução Manual Passo a Passo (Referência Técnica)

Caso você queira rodar cada ferramenta de forma isolada sem o orquestrador:

### Passo 1: Gerar as Texturas e Atlas 2K

```
# Franklin (Shinano Casual)
python3 scripts/Shinano_Casual_Franklin/generate_franklin_atlas.py

# Michael (Shinano Eternal Reunion)
python3 scripts/Shinano_EternalReunion_Michael/generate_er_atlas.py

# Trevor (Miltina Maid)
python3 scripts/Miltina_Maid_Trevor/generate_miltina_atlas.py
```

### Passo 2: Compilar os Modelos 3D no Blender

Os wrappers abaixo lêem automaticamente o executável do Blender e os caminhos em `vrc2gtav.cfg`:

```
# Franklin (player_one)
python3 scripts/Shinano_Casual_Franklin/run_build_franklin.py

# Michael (player_zero)
python3 scripts/Shinano_EternalReunion_Michael/run_build_er.py

# Trevor (player_two)
python3 scripts/Miltina_Maid_Trevor/run_pipeline.py
```

### Passo 3: Aplicar Personagens nos Diretórios de Staging

```
# Aplica um personagem especifico (player_zero, player_one ou player_two):
python3 scripts/common_tools/apply_characters.py --character player_two

# Ou aplica todos:
python3 scripts/common_tools/apply_characters.py --character all
```

### Passo 4: Repacotar RPFs e Instalar no Jogo

```
python3 scripts/common_tools/repack_and_deploy_everything.py
```

O script repacotará `mppatches.rpf`, `dlc.rpf`, `streamedpeds_players.rpf` e `x64v.rpf`, aplicará as assinaturas `OPEN` e corrigirá a tabela de conteúdo (TOC) para prevenir qualquer `ERR_GEN_ZLIB_2`.

---

## 10. Créditos dos Assets Utilizados

Todos os avatares, vestidos, cabelos, acessórios, texturas e presets abaixo pertencem aos seus respectivos autores. Caso utilize ou adapte este mod, respeite os termos de licença de cada criador no BOOTH e nos repositórios oficiais.

### Resumo Geral (Avatares, Roupas, Cabelos, Olhos e Acessórios)

| Categoria | Asset / Item | Criador / Loja | Personagens no Mod | Link Oficial |
| :--- | :--- | :--- | :--- | :--- |
| **Avatar Base & Traje Casual** | オリジナル3Dモデル「しなの」 (*Shinano*) | ポンデロニウム研究所 (`ponderogen`) | Michael, Franklin | [BOOTH](https://ponderogen.booth.pm/items/6106863) / [Loja](https://ponderogen.booth.pm/) |
| **Avatar Base & Traje Maid** | オリジナル3Dモデル『ミルティナ』 (*Milltina*) | DOLOS art (`dolosart`) | Trevor | [BOOTH](https://dolosart.booth.pm/items/6538026) / [Loja](https://dolosart.booth.pm/) |
| **Vestido, Sapatos & Acessórios** | 【15アバター対応】エターナル・リユニオン【MA対応】 (*Eternal Reunion* + *Pocket Watch*) | VAGRANT (`Vagrant Brand`) | Michael | [BOOTH](https://vagrant.booth.pm/items/5634313) / [Loja](https://vagrant.booth.pm/) |
| **Cabelo, Orelhas, Presilhas & Auréola** | ねこタイドボブヘア (*Neko Tied Bob hair*) | Li-ne (`Li-ne_Shop`) | Michael | [BOOTH](https://li-ne.booth.pm/items/7977491) / [Loja](https://li-ne.booth.pm/) |
| **Textura de Olhos (Shinano)** | `[eye17アバター対応]MoonButterfly eye & Rurune Make` | ha-oa | Michael, Franklin | [BOOTH](https://ha-oa.booth.pm/items/8483652) / [Loja](https://ha-oa.booth.pm/) |
| **Textura de Olhos (Milltina)** | お魚が泳ぐ あわあわ水光 Eye Texture【10Color】【23Avatar】 (`Milltina_AWEyes`) | NAGIMA (`nagikawamart`) | Trevor | [BOOTH](https://nagikawamart.booth.pm/items/6837271) / [Loja](https://nagikawamart.booth.pm/) |

---

### 10.1 Michael De Santa (`player_zero`) — Shinano Eternal Reunion

- **Avatar Base (Corpo, Rosto, Pele e Maquiagem):** [オリジナル3Dモデル「しなの」 (Shinano)](https://ponderogen.booth.pm/items/6106863) — [ポンデロニウム研究所](https://ponderogen.booth.pm/)
  - *Origem:* `Shinano/FBX/Shinano.fbx` e `Shinano/Texture/` (`Shinano_body.png`, `Shinano_face_blue.png`, `Shinano_face_makeup1.png`, `Shinano_face_emission_mask.png`).
  - *Meshes utilizadas:* `Body` (cabeça/rosto/olhos) e `Body_base` (corpo).
- **Vestido, Sapatos, Meia-Calça e Acessórios (incluindo Relógio de Bolso):** [【15アバター対応】エターナル・リユニオン【MA対応】 (Eternal Reunion)](https://vagrant.booth.pm/items/5634313) — [VAGRANT](https://vagrant.booth.pm/)
  - *Origem:* `Vagrant Brand/Eternal Reunion/Avatars/Shinano/FBX/ER_Shi.fbx`, `Pocket Watch/FBX/ER_PW.fbx` e texturas em `TEX/` (`V3_UN1.png`, `V3_UN2.png`, `V3_UN3.png`, `UN4.png`, `Masks/`, `Normal/`).
  - *Vestido e Calçados:* `UN1_Shirt` (blusa), `UN1_Skirt` (saia), `UN2_Corset` (espartilho), `UN2_Stocking` (meia-calça), `UN2_Shoes` (sapatos).
  - *Acessórios e Relógio:* `UN1_ChestRibbon` (laço do peito), `UN1_Choker` (gargantilha), `UN3_Bag` (bolsa tiracolo), `UN3_Glasses` (óculos), `UN3_WaistChain` (corrente de cintura) e `Pocket Watch` (relógio de bolso integrado ao pacote). *(Nota: a boina `UN2_Beret` não é incluída na versão final).*
- **Cabelo, Orelhas de Gato, Laço, Presilhas e Auréola:** [ねこタイドボブヘア (Neko Tied Bob hair)](https://li-ne.booth.pm/items/7977491) — [Li-ne (`Li-ne_Shop`)](https://li-ne.booth.pm/)
  - *Origem:* `Li-ne/Neko Tied Bob hair/_Fbx/Neko Tied Bob hair.fbx` e texturas em `_Mat/` e `Accessories/` (`Blue.png`, `Light Mask.png`, `Normal map.png`, `Pin Mat.png`, `Accessories Mat.png`).
  - *Cabelo:* `Bangs`, `Top Back`, `Under Side`, `Back`, `Side Bangs`, `Side`, `In Hair`.
  - *Orelhas e Acessórios:* `Ears` (orelhas de gato), `Ribbon` (laço lateral), `_Pin.Back`, `_Pin.R`, `_Pin.L2` (presilhas/grampos) e `_Halo` (auréola metálica flutuante).
- **Textura de Olhos:** [[eye17アバター対応]MoonButterfly eye & Rurune Make](https://ha-oa.booth.pm/items/8483652) — [ha-oa](https://ha-oa.booth.pm/)
  - *Origem:* `MoonButterfly eye/Sinano/Texture/` (`sky.png`, `Cloud.jpg`, `Eye-highlight.png`, `無題157_20260711214118.png`).
- **Expressão Facial (Blendshapes):** Preset `ShinanoDefAdultNewv5.anim` criado com [FaceEmo](https://suzuryg.github.io/face-emo/) sobre as blendshapes do avatar Shinano.

---

### 10.2 Franklin Clinton (`player_one`) — Shinano Casual

- **Avatar Base, Traje Casual, Cabelo Padrão, Orelhas e Cauda:** [オリジナル3Dモデル「しなの」 (Shinano)](https://ponderogen.booth.pm/items/6106863) — [ポンデロニウム研究所](https://ponderogen.booth.pm/)
  - *Origem:* `Shinano/FBX/Shinano.fbx` e `Shinano/Texture/` (`Shinano_body.png`, `Shinano_costume.png`, `Shinano_hair.png` recolorida para azul anil no atlas, `Shinano_face_blue.png`, `Shinano_face_makeup1.png`).
  - *Corpo e Rosto:* `Body`, `Body_base`.
  - *Roupas e Calçados:* `Cloth_sweater` (suéter), `Cloth_skirt` (saia), `Cloth_tights` (meia-calça), `Cloth_boots` (botas).
  - *Cabelo e Orelhas/Cauda:* `Hair_back`, `Hair_bang`, `Hair_base`, `Hair_side`, `Other_ear` (orelhas), `Other_tail` (cauda).
- **Textura de Olhos:** [[eye17アバター対応]MoonButterfly eye & Rurune Make](https://ha-oa.booth.pm/items/8483652) — [ha-oa](https://ha-oa.booth.pm/)
  - *Origem:* `MoonButterfly eye/Sinano/Texture/` (`sky.png`, `Cloud.jpg`, `Eye-highlight.png`, `無題157_20260711214118.png`).
- **Expressão Facial (Blendshapes):** Preset `ShinanoDefAdultNewv5.anim` criado com [FaceEmo](https://suzuryg.github.io/face-emo/) sobre as blendshapes do avatar Shinano.

---

### 10.3 Trevor Philips (`player_two`) — Miltina Maid

- **Avatar Base, Traje de Maid, Cabelo (Twintails) e Traços de Vaquinha:** [オリジナル3Dモデル『ミルティナ』 (Milltina)](https://dolosart.booth.pm/items/6538026) — [DOLOS art](https://dolosart.booth.pm/)
  - *Origem:* `DOLOSart/1.Milltina/FBX/Milltina.fbx` e `Material/` (`Milltina_Face.png`, `Milltina_Body.png`, `Milltina_Costume.png`, `Milltina_Hair.png`, `Milltina_Costume_Normal.png`).
  - *Corpo e Rosto:* `Body`, `Milltina_body`.
  - *Vestido e Roupas de Maid:* `Milltina_cloth_dress`, `Milltina_cloth_apron` (avental), `Milltina_cloth_skirt`, `Milltina_cloth_panties`.
  - *Acessórios e Calçados de Maid:* `Milltina_cloth_collar` (gola), `Milltina_cloth_hat` (touca/headdress), `Milltina_cloth_neck_ribbon` (laço do pescoço), `Milltina_cloth_wrist_cuffs` (punhos), `Milltina_cloth_garterbelt` (cinta-liga), `Milltina_cloth_hair_ribbon` (laços das marias-chiquinhas), `Milltina_cloth_tail_ribbon` (laço da cauda), `Milltina_cloth_tail_slit`, `Milltina_cloth_shoes` (sapatos).
  - *Cabelo e Orelhas/Chifres/Cauda:* `Milltina_hair_base`, `Milltina_hair_side`, `Milltina_hair_front`, `Milltina_hair_front_side`, `Milltina_hair_twintail`, `Milltina_cow_ears`, `Milltina_cow_horns`, `Milltina_cow_tail`.
- **Textura de Olhos:** [お魚が泳ぐ あわあわ水光 Eye Texture【10Color】【23Avatar】](https://nagikawamart.booth.pm/items/6837271) — [NAGIMA (`nagikawamart`)](https://nagikawamart.booth.pm/)
  - *Origem:* `NAGIMA/AWEyes_Texture/Milltina_AWEyes/Material/` (`Texture/Milltina_AWEyes_Blue Sea.png` e `Osakana/Milltina_AWEyes_Osakana.png`).
- **Expressão Facial (Blendshapes):** Preset `Miltina_close eyes_Base_adult.anim` via [FaceEmo](https://suzuryg.github.io/face-emo/) sobre as blendshapes do avatar Milltina.

---

### 10.4 Shaders, Pacotes Unity/VRChat e Ferramentas do Pipeline

| Ferramenta / Pacote | Autor / Mantenedor | Uso no Projeto | Link |
| :--- | :--- | :--- | :--- |
| **lilToon** (v2.4.1) | `lilxyzw` | Referência de camadas/máscaras para o baking dos atlas 2K e materiais dos avatares | [GitHub](https://github.com/lilxyzw/lilToon) / [Docs](https://lilxyzw.github.io/lilToon/) |
| **FaceEmo** (v1.7.0) | `suzuryg` | Configuração e exportação dos presets de expressão facial (`.anim`) | [GitHub](https://github.com/suzuryg/face-emo) / [Docs](https://suzuryg.github.io/face-emo/) |
| **Modular Avatar** (v1.18.7) | `bd_` (Nadena) | Montagem não destrutiva das roupas e cabelos na cena Unity (`waifuv4`) | [GitHub](https://github.com/bdunderscore/modular-avatar) / [Site](https://modular-avatar.nadena.dev/) |
| **Blender** (4.0.2) | Blender Foundation | Rigging, transferência de pesos, blendshapes e renderização de verificação | [Site Oficial](https://www.blender.org/) |
| **Sollumz** (v2.9.0) | `Skylumz`, `Colton`, `alexguirre` | Add-on do Blender para importação/exportação `.ydd` / `.yft` / XML do GTA V | [GitHub](https://github.com/Sollumz/Sollumz) / [Docs](https://docs.sollumz.org/) |
| **rage-cli** (`rage` 0.28.1) | `VIRUXE` | Extração/repacotamento `.rpf`, compilação `.ytd`, verificação e renders RAGE | [GitHub](https://github.com/VIRUXE/rage-cli) |
| **RageOpenV** | `Chiheb-Bacha` | ASI para carregamento de RPFs da pasta `mods/` no GTA V | [GitHub](https://github.com/Chiheb-Bacha/RageOpenV) |
| **Ultimate ASI Loader** | `ThirteenAG` | Proxy DLL (`dinput8.dll`) para carregamento de plugins `.asi` | [GitHub](https://github.com/ThirteenAG/Ultimate-ASI-Loader) |
