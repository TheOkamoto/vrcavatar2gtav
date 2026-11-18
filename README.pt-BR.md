<div align="center">

# `vrcavatar2gtav`

**Pipeline automatizado para converter avatares Unity/FBX do VRChat em substituições dos protagonistas do GTA V Legacy**

[![Licença: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Jogo: GTA V Legacy](https://img.shields.io/badge/Game-GTA%20V%20Legacy-2ea44f.svg)](docs/DEPLOYMENT_GUIDE.pt-BR.md)
[![Blender: 4.0.2 + Sollumz v2.9.0](https://img.shields.io/badge/Blender-4.0.2%20%2B%20Sollumz%20v2.9.0-orange.svg)](https://docs.sollumz.org/)
[![rage--cli: 0.28.1](https://img.shields.io/badge/rage--cli-0.28.1-blue.svg)](https://github.com/VIRUXE/rage-cli)
[![i18n: EN | JA | PT](https://img.shields.io/badge/i18n-EN%20%7C%20JA%20%7C%20PT-lightgrey.svg)](docs/DEPLOYMENT_GUIDE.pt-BR.md)

[English](README.md) · **Português (BR)** · [日本語](README.ja.md)

📖 **[Guia Técnico e de Implantação Completo (`docs/DEPLOYMENT_GUIDE.pt-BR.md`)](docs/DEPLOYMENT_GUIDE.pt-BR.md)**

</div>

---

> [!IMPORTANT]
> **Aviso de Direitos Autorais e Redistribuição de Assets**
>
> Este repositório **não** contém modelos de avatar/roupa da BOOTH, pacotes do Unity nem binários proprietários da Rockstar Games / GTA V. Todos os arquivos `.fbx`, `.unity`, `.ydd`, `.ytd`, `.yft`, `.ymt` e `.rpf` de personagens ficam bloqueados no [`.gitignore`](.gitignore).
>
> O usuário deve fornecer seus próprios assets legalmente adquiridos na BOOTH e sua instalação legal do **GTA V Legacy**, executando o assistente interativo de **First-Run** para validar caminhos e configurar o ambiente.

---

## Visão Geral

O `vrcavatar2gtav` automatiza a conversão de avatares anime **VRChat (Unity / FBX)** em personagens jogáveis para o **GTA V Legacy**, substituindo **Michael De Santa (`player_zero`)**, **Franklin Clinton (`player_one`)** e **Trevor Philips (`player_two`)**.

Em vez de ajustes manuais demorados, o pipeline coordena **Blender 4.0.2**, **Sollumz v2.9.0** e **`rage-cli` 0.28.1** de ponta a ponta — executando remapeamento de esqueleto, alinhamento de mãos e dedos, pesos de *lip sync*, calibração de texturas e materiais, escala padrão `1.0` (com extração opcional de escalas em cenas `.unity`), empacotamento universal de *slots* e implantação segura em RPF7 (`mods/x64v.rpf`).

### Principais Recursos

- **Assistente First-Run e Configuração Externa**: Configuração guiada e arquivo [`vrc2gtav.cfg`](vrc2gtav.cfg.example) mantêm caminhos locais fora do controle de versão.
- **Suporte Trilíngue (`en` / `ja` / `pt`)**: Detecção automática do idioma do sistema operacional com sobrescrita explícita via `--lang` nos gerenciadores, ferramentas e suítes de teste.
- **Padrão de Escala `1.0` + Leitor de `.unity`**: Mantém as escalas corporais em `1.0` por padrão no GitHub e extrai automaticamente as escalas reais da hierarquia quando uma cena `.unity` do projeto é fornecida.
- **Porte Universal de Cabelo Customizado Unity (`.prefab` / `PrefabVariant` / `.fbx`)**: Analisa automaticamente qualquer *prefab* de cabelo VRChat, anexo *Modular Avatar* ou `.fbx` + `.mat`, assa cores/HSV do lilToon no atlas 2K, ajusta o encaixe no crânio do avatar e faz *fallback* automático para o cabelo padrão (`default` / `none` / ausente).
- **Intercambiabilidade Completa Avatar <-> Protagonista**: Qualquer preset VRChat (`shinano_casual`, `shinano_er`, `miltina_maid`) pode ser atribuído a qualquer protagonista (`michael`, `franklin`, `trevor`) pela opção `[7]` do menu interativo, flags `--avatar` / `--*-avatar` na CLI ou em `vrc2gtav.cfg`.
- **Testes Automatizados**: Inclui verificação rápida de código-fonte (`7` suítes, compatível com clone limpo do GitHub) e validação completa pós-build/deploy (`10` suítes).

---

## Protagonistas e Avatares

Por padrão cada protagonista começa com o visual abaixo, mas todos os avatares VRChat são totalmente intercambiáveis entre os slots de `michael`, `franklin` e `trevor`:

| Slot Padrão | Protagonista | Avatar VRChat Padrão (`avatar` ID) | Visual Configurado | Pasta de Trabalho |
| :--- | :--- | :--- | :--- | :--- |
| `player_zero` | **Michael De Santa** | **Shinano** (`shinano_er`) | *Eternal Reunion* (Vestido Gótico + Relógio de Bolso + cabelo customizado Unity ou *Neko Tied Bob Hair* opcional, com *fallback* para o cabelo padrão da Shinano) | [`2_Michael_Shinano_EternalReunion/`](2_Michael_Shinano_EternalReunion/) |
| `player_one` | **Franklin Clinton** | **Shinano** (`shinano_casual`) | *Casual / Uniform* (Saia Vermelha + Cabelo Padrão Recolorido, ou cabelo customizado Unity opcional) | [`1_Franklin_Shinano_Casual/`](1_Franklin_Shinano_Casual/) |
| `player_two` | **Trevor Philips** | **Miltina** (`miltina_maid`) | *Classic Maid* (Vestido Preto e Branco, Avental, Maria-Chiquinha + cabelo customizado Unity opcional) | [`3_Trevor_Miltina_Maid/`](3_Trevor_Miltina_Maid/) |

---

## Pré-requisitos

- **Grand Theft Auto V (Legacy)** instalado localmente
- **[Ultimate ASI Loader](https://github.com/ThirteenAG/Ultimate-ASI-Loader)** + **[RageOpenV](https://github.com/Chiheb-Bacha/RageOpenV)** instalados na pasta do GTA V (para carregar a pasta `mods/`)
- **[Blender 4.0.2](https://www.blender.org/)** com **[Sollumz v2.9.0](https://github.com/Sollumz/Sollumz)**
- **`rage-cli` `0.28.1`** ([GitHub](https://github.com/VIRUXE/rage-cli)) para reempacotamento RPF7
- Ambiente **Python** para executar [`run_mod_manager.py`](run_mod_manager.py) e os scripts de validação
- Seus **arquivos de avatar e roupas da BOOTH** legalmente adquiridos (além do projeto Unity / cena `.unity`, caso queira herdar customizações)

---

## Início Rápido

1. **Clone o repositório**
   ```bash
   git clone https://github.com/TheOkamoto/vrcavatar2gtav.git
   cd vrcavatar2gtav
   ```

2. **Valide o repositório limpo** *(opcional)*
   ```bash
   python scripts/common_tools/test_mod_suite.py --source-only
   ```

3. **Execute a configuração inicial (First-Run)**
   Abra [`EXECUTAR_GERENCIADOR.bat`](EXECUTAR_GERENCIADOR.bat) (ou [`RUN_MANAGER.bat`](RUN_MANAGER.bat)) no Windows, ou execute diretamente via CLI:
   ```bash
   python run_mod_manager.py --setup
   ```
   O assistente verifica o diretório do GTA V Legacy, Blender `4.0.2`, `rage-cli` e os assets locais, gerando o arquivo `vrc2gtav.cfg` (ignorado pelo Git) a partir de [`vrc2gtav.cfg.example`](vrc2gtav.cfg.example). Para apenas auditar o ambiente sem alterar arquivos:
   ```bash
   python scripts/common_tools/setup_first_run.py --check-only
   ```

4. **Construa e implante todos os protagonistas**
   ```bash
   python run_mod_manager.py --character all
   ```

---

## Configuração e Comportamento de Fallback

- **Configuração Externa (`vrc2gtav.cfg`)**: Copie [`vrc2gtav.cfg.example`](vrc2gtav.cfg.example) para `vrc2gtav.cfg` (ou crie via `--setup`) para definir os caminhos do GTA V Legacy, Blender, `rage-cli` e dos arquivos FBX/Unity sem editar o código-fonte.
- **Escalas Corporais (`1.0` + Leitor de `.unity`)**: As proporções assumem `[1.0, 1.0, 1.0]` por padrão. Quando uma cena `.unity` é informada, os scripts leem a hierarquia de `Transform` do arquivo e aplicam as escalas customizadas automaticamente.
- **Predefinições de Blendshapes (`Unity` e `configs/*_blendshapes.cfg`)**: Cada *blendshape* de rosto, encolhimento de corpo (*shrink*), roupa, acessório e cabelo é carregado via [`scripts/common_tools/blendshape_helper.py`](scripts/common_tools/blendshape_helper.py) diretamente do seu projeto Unity (`.unity` + `.prefab` + `.anim`) ou de predefinições portáteis em [`configs/`](configs/) (`shinano_blendshapes.cfg`, `shinano_er_blendshapes.cfg`, `miltina_blendshapes.cfg`), controlados por `blendshapes_source = auto | unity | cfg` e `blendshapes_cfg`.
- **Importador Automático de VRChat PhysBones e Marshmallow PB (`Unity` e `configs/*_physbones.cfg`)**: O módulo [`scripts/common_tools/physbone_helper.py`](scripts/common_tools/physbone_helper.py) importa componentes `VRCPhysBone` ativos (incluindo sobrescritas de `PrefabInstance` e predefinições `marshmallow_PB`), empacota dentro do limite de `<= 63` ossos customizados / `<= 128` totais do `.ydd` na RAGE (`0` colisões de hash ELF) e lê/grava arquivos portáteis `.cfg` (`michael_neko_mimi_physbones.cfg`: `30` cadeias / `62` ossos; `shinano_casual_physbones.cfg`: `24` cadeias / `62` ossos; `miltina_maid_physbones.cfg`: `27` cadeias / `62` ossos — `81` cadeias / `186` ossos customizados no total) via `physbones_source = auto | unity | cfg`, `physbones_cfg` e opção `[10]` do menu interativo.
- **Cabelo Customizado Universal e Fallbacks**:
  - **Qualquer Avatar Preset**: Suporta `custom_hair = auto | default | none | <caminho .prefab ou .fbx>` (junto de `hair_mat`, `hair_tex`, `hair_scale`, `hair_offset`) no `vrc2gtav.cfg`, opção `[8]` do menu interativo ou flags `--hair` na CLI em `shinano_casual`, `shinano_er` e `miltina_maid`. O módulo [`scripts/common_tools/unity_hair_helper.py`](scripts/common_tools/unity_hair_helper.py) resolve cadeias de `PrefabVariant`, estruturas *Modular Avatar*, mapas de materiais `.fbx.meta` e cores/HSV lilToon em `custom_hair_manifest.json`, enquanto [`scripts/common_tools/blender_hair_helper.py`](scripts/common_tools/blender_hair_helper.py) ajusta o encaixe no crânio, remapeia UVs e preserva orelhas animais base.
  - **Shinano**: Usa `custom_hair` / *Neko Tied Bob Hair* quando disponível; caso contrário, retorna automaticamente ao cabelo padrão (`Hair_base`, `Hair_bang`, `Hair_side`, `Hair_back`, `Other_ear`, `Other_tail`), `ShinanoDefAdultNewv5.anim` e texturas base de olhos.
  - **Miltina**: Suporta qualquer `custom_hair` (ou `fbx_hair` legado); se ausente, usa automaticamente a maria-chiquinha padrão (`Milltina_hair_*`), `Miltina_close eyes_Base_adult.anim` e texturas base de olhos.
- **Idioma Automático**: Os scripts detectam o idioma do sistema (`en`, `ja`, `pt`) automaticamente e aceitam `--lang en|ja|pt`.

---

## Comandos da CLI e Testes

| Comando | Finalidade |
| :--- | :--- |
| `EXECUTAR_GERENCIADOR.bat` / `RUN_MANAGER.bat` | Menu interativo no Windows para First-Run, build e deploy |
| `python run_mod_manager.py --setup` | Assistente interativo de First-Run e geração de `vrc2gtav.cfg` |
| `python run_mod_manager.py --check-env` | Valida GTA V, Blender, `rage-cli` e caminhos de assets |
| `python scripts/common_tools/setup_first_run.py --check-only` | Auditoria não destrutiva de ambiente e arquivos de origem |
| `python run_mod_manager.py --character all` | Reconstrói tudo no Blender, exporta YDD/YTD e implanta no `x64v.rpf` |
| `python run_mod_manager.py --character {michael,franklin,trevor} --lang {en,ja,pt}` | Executa build/deploy de um único protagonista no idioma escolhido |
| `python run_mod_manager.py --character franklin --avatar miltina_maid` | Compila e aplica qualquer avatar VRChat (`shinano_casual`, `shinano_er`, `miltina_maid`) em qualquer protagonista (`--save-assignment` salva no `vrc2gtav.cfg`) |
| `python run_mod_manager.py --character michael --hair "/caminho/Hair.prefab" --save-hair` | Porta qualquer cabelo customizado `.prefab` / `PrefabVariant` / `.fbx` para um protagonista (`--hair default` / `none` / `--hair-mat` / `--hair-tex` / `--hair-scale` / `--hair-offset`) |
| `python run_mod_manager.py --export-blendshapes` | Exporta blendshapes das cenas `.unity` para `configs/*_blendshapes.cfg` |
| `python run_mod_manager.py --character all --blendshapes-source cfg` | Compila usando os presets `.cfg` de blendshapes em vez das cenas Unity |
| `python run_mod_manager.py --export-physbones` | Importa VRCPhysBones + Marshmallow PB das cenas `.unity` para `configs/*_physbones.cfg` (`--overwrite-physbones-from-unity` sobrescreve edições) |
| `python run_mod_manager.py --character all --physbones-source cfg` | Compila usando os presets `.cfg` de PhysBones em vez de extrair das cenas Unity |
| `python run_mod_manager.py --deploy-only` | Reempacota e implanta pastas já compiladas em `mods/x64v.rpf` |
| `python scripts/common_tools/test_mod_suite.py --source-only` | Executa as `7` suítes de código/config/i18n/intercambiabilidade/cabelo customizado (clone limpo) |
| `python scripts/common_tools/test_mod_suite.py` | Executa todas as `10` suítes de ponta a ponta (requer build e deploy concluídos) |

---

## Estrutura do Repositório

```text
vrcavatar2gtav/
├── configs/                         # Predefinições de blendshapes (*_blendshapes.cfg) e PhysBones (*_physbones.cfg)
├── docs/
│   ├── DEPLOYMENT_GUIDE.md          # Guia técnico completo (EN)
│   ├── DEPLOYMENT_GUIDE.pt-BR.md    # Arquitetura, rigging, Sollumz, shaders e RPF7 (PT-BR)
│   └── DEPLOYMENT_GUIDE.ja.md       # Guia técnico completo (JA)
├── scripts/
│   ├── common_tools/                # First-run, leitores de .unity/cabelo/blendshapes/PhysBones, i18n, test_mod_suite.py
│   ├── physbones_asi/               # Plugin ASI de PhysBones VRChat em tempo real (GTAVPhysBones.asi / .ini)
│   ├── Shinano_Casual_Franklin/     # Scripts de build do Franklin (player_one)
│   ├── Shinano_EternalReunion_Michael/ # Scripts de build do Michael (player_zero)
│   └── Miltina_Maid_Trevor/         # Scripts de build do Trevor (player_two)
├── _deploy_tools/                   # Dummies universais (head_000_r.ydd, p_eyes_dummy.ydd) e helpers de runtime
├── 1_Franklin_Shinano_Casual/       # Saída intermediária para player_one
├── 2_Michael_Shinano_EternalReunion/# Saída intermediária para player_zero
├── 3_Trevor_Miltina_Maid/           # Saída intermediária para player_two
├── run_mod_manager.py               # Orquestrador principal via CLI e menu interativo
├── RUN_MANAGER.bat                  # Atalho interativo no Windows (EN/JA/PT)
├── EXECUTAR_GERENCIADOR.bat         # Atalho interativo no Windows (PT-BR)
├── vrc2gtav.cfg.example             # Modelo externo de configuração de caminhos
└── LICENSE                          # Licença MIT
```

Para detalhes completos sobre alinhamento de ossos, calibração das mãos, síntese de *lip sync*, hashes JOAAT de texturas, shaders no `Sollumz`, substituição universal de *slots* (prevenção de `ERR_GEN_ZLIB_2`) e solução de problemas, consulte o **[Guia Técnico e de Implantação](docs/DEPLOYMENT_GUIDE.pt-BR.md)**.

---

## Créditos — Assets e Ferramentas

Todos os modelos 3D, roupas, cabelos, texturas oculares, pacotes Unity e ferramentas externas pertencem exclusivamente aos seus respectivos autores.

### Avatares 3D, Roupas, Cabelos e Texturas de Olhos (BOOTH)

| Protagonista(s) | Categoria | Asset | Autor / Loja | Link BOOTH |
| :--- | :--- | :--- | :--- | :--- |
| Michael, Franklin | Avatar Base e Roupa Casual *(Obrigatório)* | **オリジナル3Dモデル「しなの」 (*Shinano*)** | ポンデロニウム研究所 (`ponderogen`) | [Item #6106863](https://ponderogen.booth.pm/items/6106863) · [Loja](https://ponderogen.booth.pm/) |
| Trevor | Avatar Base e Roupa de Maid *(Obrigatório)* | **オリジナル3Dモデル『ミルティナ』 (*Milltina*)** | DOLOS art (`dolosart`) | [Item #6538026](https://dolosart.booth.pm/items/6538026) · [Loja](https://dolosart.booth.pm/) |
| Michael | Vestido, Sapatos e Acessórios *(Obrigatório para Michael)* | **【15アバター対応】エターナル・リユニオン【MA対応】 (*Eternal Reunion* + *Pocket Watch*)** | VAGRANT (`Vagrant Brand`) | [Item #5634313](https://vagrant.booth.pm/items/5634313) · [Loja](https://vagrant.booth.pm/) |
| Michael | Cabelo, Orelhas, Presilhas e Auréola *(Opcional — fallback para cabelo padrão)* | **ねこタイドボブヘア (*Neko Tied Bob hair*)** | Li-ne (`Li-ne_Shop`) | [Item #7977491](https://li-ne.booth.pm/items/7977491) · [Loja](https://li-ne.booth.pm/) |
| Michael, Franklin | Textura de Olhos *(Opcional)* | **`[eye17アバター対応]MoonButterfly eye & Rurune Make`** | ha-oa | [Item #8483652](https://ha-oa.booth.pm/items/8483652) · [Loja](https://ha-oa.booth.pm/) |
| Trevor | Textura de Olhos *(Opcional)* | **お魚が泳ぐ あわあわ水光 Eye Texture【10Color】【23Avatar】 (`Milltina_AWEyes`)** | NAGIMA (`nagikawamart`) | [Item #6837271](https://nagikawamart.booth.pm/items/6837271) · [Loja](https://nagikawamart.booth.pm/) |

<details>
<summary>Detalhamento de malhas, acessórios e presets FaceEmo por personagem</summary>

- **Michael De Santa (`player_zero`) — Shinano (*Eternal Reunion*)**
  - **Corpo Base**: `Body`, `Body_base` (*Shinano*)
  - **Roupa**: `UN1_Shirt`, `UN1_Skirt`, `UN2_Corset`, `UN2_Stocking`, `UN2_Shoes` (*Eternal Reunion*)
  - **Acessórios**: `UN1_ChestRibbon`, `UN1_Choker`, `UN3_Bag`, `UN3_Glasses`, `UN3_WaistChain`, `Pocket Watch` (*Eternal Reunion*; `UN2_Beret` desativado)
  - **Cabelo *(Opcional)***: `Bangs`, `Top Back`, `Under Side`, `Back`, `Side Bangs`, `Side`, `In Hair`, `Ears`, `Ribbon`, `_Pin.Back`, `_Pin.R`, `_Pin.L2`, `_Halo` (*Neko Tied Bob hair*; retorna ao cabelo padrão da Shinano se omitido)
  - **Olhos e Expressão *(Opcional / Fallback)***: `MoonButterfly eye` e `ShinanoDefAdultNewv5.anim`

- **Franklin Clinton (`player_one`) — Shinano (*Casual / Uniform*)**
  - **Corpo Base**: `Body`, `Body_base` (*Shinano*)
  - **Roupa**: `Cloth_sweater`, `Cloth_skirt`, `Cloth_tights`, `Cloth_boots` (*Shinano*)
  - **Cabelo**: `Hair_back`, `Hair_bang`, `Hair_base`, `Hair_side`, `Other_ear`, `Other_tail` (*Shinano* padrão; aceita `custom_hair` opcional preservando as orelhas)
  - **Olhos e Expressão *(Opcional / Fallback)***: `MoonButterfly eye` e `ShinanoDefAdultNewv5.anim`

- **Trevor Philips (`player_two`) — Miltina (*Classic Maid*)**
  - **Corpo Base**: `Body`, `Milltina_body` (*Milltina*)
  - **Roupa e Acessórios**: `Milltina_cloth_dress`, `Milltina_cloth_apron`, `Milltina_cloth_skirt`, `Milltina_cloth_panties`, `Milltina_cloth_collar`, `Milltina_cloth_hat`, `Milltina_cloth_neck_ribbon`, `Milltina_cloth_wrist_cuffs`, `Milltina_cloth_garterbelt`, `Milltina_cloth_hair_ribbon`, `Milltina_cloth_tail_ribbon`, `Milltina_cloth_tail_slit`, `Milltina_cloth_shoes` (*Milltina*)
  - **Cabelo e Partes de Vaca**: `Milltina_hair_base`, `Milltina_hair_side`, `Milltina_hair_front`, `Milltina_hair_front_side`, `Milltina_hair_twintail`, `Milltina_cow_ears`, `Milltina_cow_horns`, `Milltina_cow_tail` (*Milltina*; aceita substituição opcional por `custom_hair` / `fbx_hair`)
  - **Olhos e Expressão *(Opcional / Fallback)***: `Milltina_AWEyes` e `Miltina_close eyes_Base_adult.anim`

</details>

### Pacotes Unity e Ferramentas GTA V / Blender

| Ferramenta / Pacote | Versão | Autor(es) | Link |
| :--- | :--- | :--- | :--- |
| **lilToon** | `v2.4.1` | `lilxyzw` | [GitHub](https://github.com/lilxyzw/lilToon) · [Site](https://lilxyzw.github.io/lilToon/) |
| **FaceEmo** | `v1.7.0` | `suzuryg` | [GitHub](https://github.com/suzuryg/face-emo) · [Site](https://suzuryg.github.io/face-emo/) |
| **Modular Avatar** | `v1.18.7` | `bd_` (Nadena) | [GitHub](https://github.com/bdunderscore/modular-avatar) · [Site](https://modular-avatar.nadena.dev/) |
| **Blender** | `4.0.2` | Blender Foundation | [Site](https://www.blender.org/) |
| **Sollumz** | `v2.9.0` | `Skylumz`, `Colton`, `alexguirre` | [GitHub](https://github.com/Sollumz/Sollumz) · [Docs](https://docs.sollumz.org/) |
| **rage-cli** | `0.28.1` | `VIRUXE` | [GitHub](https://github.com/VIRUXE/rage-cli) |
| **RageOpenV** | — | `Chiheb-Bacha` | [GitHub](https://github.com/Chiheb-Bacha/RageOpenV) |
| **Ultimate ASI Loader** | — | `ThirteenAG` | [GitHub](https://github.com/ThirteenAG/Ultimate-ASI-Loader) |

---

## Licença

Os scripts de automação e a documentação deste projeto são distribuídos sob a **Licença MIT** — consulte [`LICENSE`](LICENSE) (`Copyright (c) 2026 TheOkamoto`). Assets e ferramentas de terceiros permanecem regidos por suas respectivas licenças e termos de uso.
