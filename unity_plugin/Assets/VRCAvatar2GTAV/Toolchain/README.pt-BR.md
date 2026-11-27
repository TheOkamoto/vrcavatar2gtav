<div align="center">

# `vrcavatar2gtav`

**Pipeline automatizado via Plugin do Unity Editor e CLI para converter avatares Unity/FBX do VRChat em protagonistas, NPCs de história/cutscene e pedestres do GTA V Legacy — com shader `GTAVVToon.asi` em tempo real e física `GTAVPhysBones.asi`**

[![Licença: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Jogo: GTA V Legacy](https://img.shields.io/badge/Game-GTA%20V%20Legacy-2ea44f.svg)](docs/DEPLOYMENT_GUIDE.pt-BR.md)
[![Unity Plugin: VRCAvatar2GTAV](https://img.shields.io/badge/Unity%20Plugin-Tools%20%E2%86%92%20VRCAvatar2GTAV-5865F2.svg)](docs/DEPLOYMENT_GUIDE.pt-BR.md)
[![Blender: 4.0.2 + Sollumz v2.9.0](https://img.shields.io/badge/Blender-4.0.2%20%2B%20Sollumz%20v2.9.0-orange.svg)](https://docs.sollumz.org/)
[![rage--cli: 0.28.1](https://img.shields.io/badge/rage--cli-0.28.1-blue.svg)](https://github.com/VIRUXE/rage-cli)
[![i18n: EN | JA | PT](https://img.shields.io/badge/i18n-EN%20%7C%20JA%20%7C%20PT-lightgrey.svg)](docs/DEPLOYMENT_GUIDE.pt-BR.md)

[English](README.md) · **Português (BR)** · [日本語](README.ja.md)

📖 **[Guia Técnico e de Implantação Completo (`docs/DEPLOYMENT_GUIDE.pt-BR.md`)](docs/DEPLOYMENT_GUIDE.pt-BR.md)** · 🖼️ **[Guia da Interface no Unity (`docs/UNITY_UI_GUIDE.pt-BR.md`)](docs/UNITY_UI_GUIDE.pt-BR.md)**

</div>

---

> [!IMPORTANT]
> **Aviso de Direitos Autorais e Redistribuição de Assets**
>
> Este repositório **não** contém modelos de avatar/roupa da BOOTH, pacotes do Unity nem binários proprietários da Rockstar Games / GTA V. Todos os arquivos `.fbx`, `.unity`, `.ydd`, `.ytd`, `.yft`, `.ymt`, `.rpf`, diretórios locais de NPC (`npcs/`) e arquivos de configuração local (`vrc2gtav.cfg`, `configs/npc_registry.json`, `configs/active_multi_slots.json`) ficam bloqueados no [`.gitignore`](.gitignore) (e fora do [`VRCAvatar2GTAV.unitypackage`](VRCAvatar2GTAV.unitypackage)).
>
> O usuário deve fornecer seus próprios assets legalmente adquiridos na BOOTH e sua instalação legal do **GTA V Legacy**, utilizando o **Plugin do Unity Editor** (`Tools > VRCAvatar2GTAV > Export Avatar to GTA V`) ou o assistente interativo **First-Run** para validar caminhos e configurar o ambiente.

---

## Visão Geral

O `vrcavatar2gtav` automatiza a conversão de avatares anime **VRChat (Unity / FBX)** em personagens jogáveis para o **GTA V Legacy**, substituindo **Michael De Santa (`player_zero`)**, **Franklin Clinton (`player_one`)** e **Trevor Philips (`player_two`)**, bem como qualquer **NPC de história/cutscene ou pedestre de rua do GTA V** (`ig_*`, `cs_*`, `a_f_*`, `a_m_*`, etc., direto de GameObjects da cena, `.prefab`, `.unity`, `.zip` ou `.unitypackage`).

Além da automação completa via **Blender 4.0.2**, **Sollumz v2.9.0** e **`rage-cli` 0.28.1**, a branch `unity-ui` traz um **Exportador nativo dentro do Unity Editor** ([`VRCAvatar2GTAV.unitypackage`](VRCAvatar2GTAV.unitypackage)) com perfis em abas por protagonista, shader D3D11 lilToon em tempo real (**`GTAVVToon.asi`**), **VRChat PhysBones multi-ped (`GTAVPhysBones.asi`)**, trava de mip único em `2048px` nos `.ytd`s, **Restauração Seletiva ao Original (Restore Vanilla)** e controle de orçamento RPF7 abaixo de `4.00 GiB`.

### Vídeos de Exemplo

<div align="center">

<table>
  <tr>
    <td align="center">
      <a href="https://youtube.com/shorts/xoaqZa0GhC8?is=Y_0Z3Nd31neOgCFI">
        <img src="https://img.youtube.com/vi/xoaqZa0GhC8/maxresdefault.jpg" width="400" alt="しなのちゃん殴られちゃった (YouTube Shorts)">
      </a>
      <br>
      <sub><b>しなのちゃん殴られちゃった</b></sub>
      <br>
      <a href="https://youtube.com/shorts/xoaqZa0GhC8?is=Y_0Z3Nd31neOgCFI">
        <img src="https://img.shields.io/badge/YouTube_Shorts-Assistir_Exemplo_1-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Assistir Exemplo 1 no YouTube Shorts">
      </a>
    </td>
    <td align="center">
      <a href="https://youtube.com/shorts/Clo0A7oHYhA">
        <img src="https://img.youtube.com/vi/Clo0A7oHYhA/maxresdefault.jpg" width="400" alt="無敵しなのちゃんだ！！ (YouTube Shorts)">
      </a>
      <br>
      <sub><b>無敵しなのちゃんだ！！</b></sub>
      <br>
      <a href="https://youtube.com/shorts/Clo0A7oHYhA">
        <img src="https://img.shields.io/badge/YouTube_Shorts-Assistir_Exemplo_2-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Assistir Exemplo 2 no YouTube Shorts">
      </a>
    </td>
  </tr>
</table>

</div>

### Principais Recursos

- **Plugin Exportador no Unity Editor (`VRCAvatar2GTAV.unitypackage`)**: Abra `Tools > VRCAvatar2GTAV > Export Avatar to GTA V` direto no Unity ([`unity_plugin/Assets/VRCAvatar2GTAV/Editor/`](unity_plugin/Assets/VRCAvatar2GTAV/Editor/)). Suporta **Modo Compartilhado** e a 4ª opção **Avatar Independente por Protagonista (`PerProtagonistSlots`)** (`configs/active_multi_slots.json` + `--slots-json`) para configurar cada slot ou trocar apenas um protagonista mantendo os outros dois modificados intactos, arrastar e soltar GameObjects da cena, `.prefab`, `.unitypackage` ou `.zip`, sobrescrita de `_MainTex` por material, seletor de resolução do atlas (`512`–`4096`), normal (`Auto`/`Off`/`256`–`1024`) e roupas secundárias (`Auto <3.7 GiB` / `512` / `1024` / `2048`) com estimativa de RPF7 ao vivo, barra de progresso proporcional multi-slot (`0–82%` por slot + `82–100%` empacotamento via `[PROGRESS pct=...]`), slider de **Abertura da Boca (`0.70` padrão + botão de reset)** e força de piscar, `.anim` facial opcional (`--face-anim`), pílulas de status runtime do GTA V (`dinput8.dll`, `PhysBones.asi`, `VToon.asi`, `ScriptHookV.dll`, `OpenIV.asi` / RageOpenV), seletor **Auto / Windows Native / WSL**, console redimensionável e botões de **Restaurar Original (Restore Vanilla)**.
- **Shader lilToon D3D11 em Tempo Real (`GTAVVToon.asi`)**: [`scripts/vtoon_asi/`](scripts/vtoon_asi/gtav_vtoon.cpp) e [`scripts/common_tools/vtoon_profile_helper.py`](scripts/common_tools/vtoon_profile_helper.py) extraem parâmetros `.mat` do lilToon (inclusive herança `m_Parent`), LUTs por região UV, MatCaps assados e marcas d'água mip0 alinhadas em bloco `8×4` (`char_id` `1..15`, IDs de protagonistas `1..3`) em `GTAVVToon.ini` + `vtoon_profiles/`. Interceptam `D3D11CreateDevice*`, `ID3D11Device`, `ID3D11DeviceContext` imediato/diferido, `ID3D11DeviceContext1` e callbacks seguros para overlays via `ScriptHookV`, aplicando *cel shading* Half-Lambert de dupla borda, terminador SSS quente, luz de contorno (*rim light*), alpha forward para fios finos e lentes transparentes (`kVToonForwardAlphaHlsl`), bypass do pass borrado de pele do GTA V, hot-reload na tecla **`F10`** e checagem SHA-256 na implantação dos ASIs.
- **`.ytd`s de Textura Única Travados em `--mips 1` (`2048px`) & Orçamento RPF7**: O [`scripts/common_tools/universal_atlas_builder.py`](scripts/common_tools/universal_atlas_builder.py) gera dicionários `.ytd` externos com textura única e `--mips 1`, impedindo quedas de qualidade por *texture streaming* quando múltiplos peds customizados estão na mesma cena/cutscene, usa mapas neutros `A8R8G8B8` válidos para bump/spec embutidos e aplica `--secondary-atlas-size` (`auto <3.7 GiB`, `512`, `1024`, `2048`) nos slots `uppr_diff_001+`, mantendo o `uppr_000` em `2048×2048` abaixo de `4.00 GiB`.
- **Restauração Seletiva ao Original (`--restore-peds` / `--restore-all`)**: O módulo [`scripts/common_tools/restore_vanilla_helper.py`](scripts/common_tools/restore_vanilla_helper.py) extrai dos RPFs originais da Rockstar apenas os arquivos do ped escolhido sem remover os demais protagonistas/NPCs modificados, além de limpar automaticamente suas seções no `GTAVPhysBones.ini`, `GTAVVToon.ini` e `configs/npc_registry.json`.
- **Motor Nativo Modular Avatar (NDMF) & Ordem de Submeshes**: [`scripts/common_tools/modular_avatar_helper.py`](scripts/common_tools/modular_avatar_helper.py), [`scripts/common_tools/blendshape_helper.py`](scripts/common_tools/blendshape_helper.py) e [`scripts/common_tools/build_universal_avatar.py`](scripts/common_tools/build_universal_avatar.py) executam o bake de `ModularAvatarMergeArmature`, `BoneProxy`, `ScaleAdjuster`, `MeshSettings`, `ObjectToggle`/`Activator`, `ReplaceObject`, `ShapeChanger` (`Delete` > `m_threshold` separado de `Set`), `BlendshapeSync` (com `RemapCurve` reavaliado após os pesos base para que prefabs aninhados nunca sejam zerados), remoção automática de faces internas encolhidas por `Shrink_* > 0.5` em `Body_base`/`Body`, sobrescritas `m_Materials`, `VRCPhysBone`s e materiais lilToon, preservam o alpha de lentes/óculos e alinham a ordem de slots do Blender à ordem de submeshes do Unity (`map_blender_slots_to_unity_submeshes`).
- **Blendshapes Separados (Rosto/Corpo) & Preservação de `.anim` Facial**: Pergunta separadamente por rosto (`--import-face-blendshapes`) e corpo (`--import-body-blendshapes`), aceita `--face-anim` dedicado, preserva *blendshapes* faciais da cena Unity quando o `face_anim` está vazio ou zerado, aplica `--mouth-open-strength` (`0.70` padrão no `FACIAL_jaw`) ou gera `.cfg` completo zerado incluindo vestidos customizados.
- **Assistente First-Run, Ingestão de `.zip`/Unity e Download do Blender 4.0.2**: [`scripts/common_tools/avatar_archive_helper.py`](scripts/common_tools/avatar_archive_helper.py) extrai pacotes com proteção *Zip-Slip*, baixa o Blender `4.0.2` + `Sollumz` (`--download-blender`) e `rage-cli` (`--download-rage`) quando ausentes e exibe **menu paginado de avatares (`10`/página + `Next`/`Prev`)**.
- **Porte Universal de Cabelo, PhysBones & Troca entre Protagonistas**: Suporta cabelos `.prefab`/`PrefabVariant`/`.fbx` com divisão por bandas Z, `VRCPhysBone`s (`79` cadeias padrão + cadeias por NPC, modo `Advanced` `integrationType == 1` relativo ao pai, desembrulho de fios inferiores/laços, remoção dupla de órfãos/soltos na extração Unity e após o corte de `ShapeChanger`/`Shrink_*` no Blender, priorização `<= 63` ossos mantendo **cabelos/orelhas (`97–100`), seios (`94`) e saias (`90`)** no topo acima de caudas/casacos/fitas, `--physbones-marshmallow` opcional) e troca livre de slots (`[7]`, `--avatar`).
- **Pipeline Universal de NPCs e Pedestres do GTA V**: [`scripts/common_tools/npc_registry_helper.py`](scripts/common_tools/npc_registry_helper.py) e [`scripts/common_tools/universal_gtav_builder.py`](scripts/common_tools/universal_gtav_builder.py) convertem qualquer avatar direto para qualquer NPC de história/cutscene (`ig_*`, `cs_*`) ou pedestre (`a_f_*`, `a_m_*`) via `--npc` / `--all-npcs` / `--target-ped`, com mapeamento de mandíbula (`FB_Jaw_000` / `FACIAL_C_Jaw` / `FACIAL_jaw`), casamento `.001` vs `" 1"`, limpeza de props `*_p`/`p_*.ydd` e rastreio de até **32 peds simultâneos (`kMaxTrackedPeds = 32`)** no `GTAVPhysBones.asi`.
- **Decals de Sangue (`ped.sps` + `UVMap 1` 6 Zonas) & Piscar Natural dos Olhos**: [`scripts/common_tools/ped_damage_helper.py`](scripts/common_tools/ped_damage_helper.py) (`--blood-decals` padrão / `--no-blood-decals`) e [`scripts/common_tools/eye_blink_helper.py`](scripts/common_tools/eye_blink_helper.py) (`--eye-blink` `auto` / `--eye-blink-strength` / `--no-eye-blink`).
- **Logs `--verbose`, Suporte Trilíngue (`en`/`ja`/`pt`) e Testes Automatizados**: [`scripts/common_tools/error_handler_helper.py`](scripts/common_tools/error_handler_helper.py) grava logs detalhados em `logs/`; [`scripts/common_tools/test_mod_suite.py`](scripts/common_tools/test_mod_suite.py) valida **12** suítes de código-fonte (`--source-only`) e **15** suítes completas pós-deploy.

---

## Protagonistas e Avatares

Qualquer avatar humanoide do VRChat / BOOTH (ex.: *Shinano*, *Miltina*, *Airi*, *Manuka*, *Chocolat*) pode ser atribuído livremente aos slots `michael` (`player_zero`), `franklin` (`player_one`) e `trevor` (`player_two`) — ou a qualquer NPC/pedestre — pelo Plugin do Unity Editor ou pela CLI universal:

| Slot | Protagonista | Perfil / Avatar Padrão (`avatar` ID) | Visual de Referência | Pasta de Staging |
| :--- | :--- | :--- | :--- | :--- |
| `player_zero` | **Michael De Santa** | **Shinano** (`player_zero_michael`) | *Eternal Reunion* (Vestido Gótico + Relógio de Bolso + cabelo customizado Unity ou padrão opcional) | `player_zero/` |
| `player_one` | **Franklin Clinton** | **Shinano** (`player_one_franklin`) | *Casual / Uniform* (Saia Vermelha + Cabelo Padrão Recolorido, ou cabelo customizado Unity opcional) | `player_one/` |
| `player_two` | **Trevor Philips** | **Miltina** (`player_two_trevor`) | *Classic Maid* (Vestido Preto e Branco, Avental, Maria-Chiquinha + cabelo customizado Unity opcional) | `player_two/` |

---

## Pré-requisitos

- **Grand Theft Auto V (Legacy)** instalado localmente
- **[Ultimate ASI Loader](https://github.com/ThirteenAG/Ultimate-ASI-Loader)** (`dinput8.dll`) + **[RageOpenV](https://github.com/Chiheb-Bacha/RageOpenV)** (ou `OpenIV.asi`) na pasta do GTA V para carregar a pasta `mods/`
- **[ScriptHookV](https://www.dev-c.com/gtav/scripthookv/)** (`ScriptHookV.dll`, recomendado para hooks de frame/tecla `F10` do `GTAVVToon.asi` e rastreamento de peds no `GTAVPhysBones.asi`)
- **[Blender 4.0.2](https://www.blender.org/)** com **[Sollumz v2.9.0](https://github.com/Sollumz/Sollumz)** *(baixado automaticamente via `--download-blender` ou botão Setup no Unity)*
- **`rage-cli` `0.28.1`** ([GitHub](https://github.com/VIRUXE/rage-cli)) para empacotamento RPF7 *(baixado automaticamente via `--download-rage` ou UI do Unity)*
- Ambiente **Python 3.10+** com [`requirements.txt`](requirements.txt) (`numpy`, `Pillow`)
- *(Opcional, para fluxo visual no Unity)* **Unity Editor 2022.3+** (projeto VRChat Creator Companion com pasta `Assets/`)
- Seus **arquivos de avatar e roupas da BOOTH** legalmente adquiridos

---

## Início Rápido

### Opção A — Plugin do Unity Editor (Recomendado para projetos Unity / VCC)

1. Dê um duplo clique em [`VRCAvatar2GTAV.unitypackage`](VRCAvatar2GTAV.unitypackage) para importar no seu projeto Unity (ou execute o instalador não destrutivo via CLI):
   ```bash
   python unity_plugin/install_unity_plugin.py --unity-project "/caminho/MeuProjetoUnity"
   ```
2. No Unity, acesse **`Tools > VRCAvatar2GTAV > Export Avatar to GTA V`**.
3. Escolha o modo **Compartilhado** ou ative **Abas por Protagonista** (`Michael`, `Franklin`, `Trevor`), arraste seus avatares da cena, `.prefab`, `.zip` ou `.unitypackage`, ajuste resolução / abertura da boca (`0.70` padrão) / piscar, confira as pílulas de runtime do GTA V (use **Baixar e Configurar** se faltar Blender/rage-cli) e clique em **Iniciar Exportação**.

### Opção B — CLI e Menu Interativo no Terminal

1. **Clone o repositório e instale as dependências Python (`numpy`, `Pillow`)**
   ```bash
   git clone https://github.com/TheOkamoto/vrcavatar2gtav.git
   cd vrcavatar2gtav
   pip install -r requirements.txt
   ```

2. **Valide o repositório limpo** *(opcional)*
   ```bash
   python scripts/common_tools/test_mod_suite.py --source-only
   ```

3. **Execute o First-Run** — abra [`EXECUTAR_GERENCIADOR.bat`](EXECUTAR_GERENCIADOR.bat) (ou [`RUN_MANAGER.bat`](RUN_MANAGER.bat)) no Windows, ou via CLI:
   ```bash
   python run_mod_manager.py --setup
   ```
   Para apenas auditar o ambiente sem alterar arquivos:
   ```bash
   python scripts/common_tools/setup_first_run.py --check-only
   ```

4. **Construa e implante todos os protagonistas**
   ```bash
   python run_mod_manager.py --character all
   ```

---

## Configuração e Comportamento de Fallback

- **Configuração Externa (`vrc2gtav.cfg`) & Toolchain Embutido**: Copie [`vrc2gtav.cfg.example`](vrc2gtav.cfg.example) para `vrc2gtav.cfg` (ou gere via `--setup` / UI do Unity). Quando instalado via `.unitypackage`, o `Vrc2GtavConfigDiscovery` usa prioritariamente `Assets/VRCAvatar2GTAV/Toolchain` e redireciona os arquivos de trabalho para `<RaizDoProjeto>/VRCAvatar2GTAV_Work`.
- **Escalas Corporais (`1.0` + Leitor de `.unity`)**: Proporções assumem `[1.0, 1.0, 1.0]` por padrão e leem escalas customizadas da hierarquia `Transform` quando uma cena `.unity` é fornecida.
- **Blendshapes (`Unity` e `configs/*_blendshapes.cfg`), MA Shape/Sync & `.cfg` por Cena/Arquivo**: Resolvidos via [`scripts/common_tools/blendshape_helper.py`](scripts/common_tools/blendshape_helper.py) (`blendshapes_source = auto | unity | cfg`). No fluxo automático para qualquer avatar BOOTH, os `.cfg`s exportados usam o **nome da cena `.unity`** (ou o nome do `.zip`/`.unitypackage` na CLI) com comentários `#` iniciais informando data/hora, projeto, cena (se aplicável) e `.fbx`. Caso `--face-anim` não seja informado ou o `.anim` esteja zerado, os *blendshapes* faciais configurados na cena Unity ou `.cfg` são preservados. `MA ShapeChanger` (`Delete` vs `Set`) e `MA BlendshapeSync` (`RemapCurve`) são reaplicados após os pesos base, enquanto chaves manuais `Shrink_* > 0.5` em `Body_base`/`Body` removem triângulos internos antes do orçamento de polígonos RPF7.
- **PhysBones (`Unity` e `configs/*_physbones.cfg`)**: [`scripts/common_tools/physbone_helper.py`](scripts/common_tools/physbone_helper.py) importa `VRCPhysBone`s ativos (`PrefabInstance`, desembrulho de fios inferiores/laços, exclusão de cadeias órfãs/soltas na cena e poda final pós-corte no Blender) dentro do teto `<= 63` ossos customizados / `<= 128` totais (`--physbones-marshmallow` habilita opcionalmente) e prioriza via `PHYSBONE_PRIORITY_TIERS` mantendo **cabelos/orelhas (`97–100`), seios (`94`) e saias (`90`)** no topo acima de caudas (`82`), casacos (`68`) e fitas/babados.
- **Cabelo Customizado Universal e Fallbacks**:
  - **Qualquer Avatar VRChat / BOOTH**: Suporta `custom_hair = auto | default | none | <caminho .prefab ou .fbx>` (`[8]` / `--hair`, `--hair-mat`, `--hair-tex`, `--hair-scale`, `--hair-offset`) via [`scripts/common_tools/unity_hair_helper.py`](scripts/common_tools/unity_hair_helper.py) e [`scripts/common_tools/blender_hair_helper.py`](scripts/common_tools/blender_hair_helper.py), mantendo compatibilidade genérica com cabelos originais e animações padrão do avatar quando o opcional é omitido.
- **Idioma Automático**: Detecta o idioma do sistema (`en`, `ja`, `pt`) automaticamente ou via `--lang en|ja|pt`.

---

## Comandos da CLI e Testes

| Comando | Finalidade |
| :--- | :--- |
| `EXECUTAR_GERENCIADOR.bat` / `RUN_MANAGER.bat` | Menu interativo no Windows para First-Run, build e deploy |
| `python unity_plugin/install_unity_plugin.py --unity-project "/caminho/Projeto"` | Instala de forma não destrutiva `Assets/VRCAvatar2GTAV/` no projeto Unity (removendo lixo de versões antigas) |
| `python unity_plugin/build_unitypackage.py` | Prepara `Assets/VRCAvatar2GTAV/Toolchain/` e recompila o `VRCAvatar2GTAV.unitypackage` |
| `python run_mod_manager.py --setup` | Assistente interativo de First-Run e geração de `vrc2gtav.cfg` |
| `python run_mod_manager.py --setup --avatar-zip "/caminho/Shinano.zip" --download-blender --verbose` | Extrai `.zip`/`.unitypackage`, baixa Blender `4.0.2` + Sollumz, pagina avatares (`10`/página), gera `.cfg` e salva log em `logs/` |
| `python scripts/common_tools/build_universal_avatar.py --avatar-zip "/caminho/Avatar.zip" --interactive --verbose` | Construtor universal Modular Avatar para qualquer avatar BOOTH (seletor paginado e logs detalhados) |
| `python scripts/common_tools/universal_gtav_builder.py --slots-json "configs/active_multi_slots.json"` | Constrói múltiplos protagonistas em sequência (`PerProtagonistSlots`) com empacotamento RPF7 único (`--secondary-atlas-size`, `--atlas-size`, `--mouth-open-strength`, `--face-anim`) |
| `python scripts/common_tools/universal_gtav_builder.py --target-character michael --atlas-only` | Gera apenas o atlas 2K (`--mips 1`) e `.ytd` de um protagonista via pipeline universal (use `--skip-atlas --no-deploy` para compilar só o `.ydd`) |
| `python scripts/common_tools/universal_gtav_builder.py --restore-peds player_zero` | Restaura seletivamente um protagonista/NPC ao padrão Rockstar (`--restore-all` para todos) sem afetar outros peds modificados |
| `python run_mod_manager.py --check-env` / `setup_first_run.py --check-only` | Valida GTA V, Blender, `rage-cli` e caminhos de assets |
| `python run_mod_manager.py --character {all,michael,franklin,trevor} --lang {en,ja,pt}` | Reconstrói no Blender, exporta YDD/YTD (`--mips 1`), sincroniza ASIs/perfis e implanta em `mods/` |
| `python run_mod_manager.py --character franklin --avatar player_two_trevor` | Atribui qualquer perfil configurado (`player_zero_michael`, `player_one_franklin`, `player_two_trevor`) a qualquer protagonista (`--save-assignment`) |
| `python run_mod_manager.py --character michael --hair "/caminho/Hair.prefab" --save-hair` | Porta cabelo customizado `.prefab` / `PrefabVariant` / `.fbx` (`--hair default` / `none` / `--hair-mat` / `--hair-tex` / `--hair-scale` / `--hair-offset`) |
| `python run_mod_manager.py --export-blendshapes` / `--blendshapes-source cfg` | Exporta blendshapes das cenas `.unity` ou usa `.cfg` portáteis |
| `python run_mod_manager.py --export-physbones` / `--physbones-source cfg` | Importa VRCPhysBones (`--physbones-marshmallow`, `--overwrite-physbones-from-unity`) |
| `python run_mod_manager.py --character all --blood-decals --eye-blink` | Controla decals de sangue (`--no-blood-decals`), piscar natural (`--eye-blink-strength`, `--no-eye-blink`) e `--mouth-open-strength` (`0.70` padrão) |
| `python run_mod_manager.py --npc ig_lamardavis --avatar-zip "/caminho/Avatar.zip"` | Converte e implanta qualquer NPC (`ig_*`, `cs_*`) ou pedestre (`a_f_*`, `a_m_*`) direto (`--all-npcs` / `--target-ped ... --deploy-npc`) |
| `python run_mod_manager.py --deploy-only` | Reempacota e instala personagens, NPCs registrados e plugins ASI em `mods/` |
| `python scripts/common_tools/test_mod_suite.py --source-only` | Executa todas as **12** suítes de código-fonte/Unity/VToon/MA-Shape/Cross-Avatar/i18n/AST (clone limpo) |
| `python scripts/common_tools/test_mod_suite.py` | Executa todas as **15** suítes completas de ponta a ponta (requer build e deploy concluídos) |

---

## Estrutura do Repositório

```text
vrcavatar2gtav/
├── VRCAvatar2GTAV.unitypackage      # Pacote Unity pronto para importar com UI + Toolchain embutido (ignorado no Git / gerado via build_unitypackage.py)
├── unity_plugin/
│   ├── Assets/VRCAvatar2GTAV/
│   │   ├── Editor/                  # 9 scripts C# do Unity Editor (VRCAvatar2GTAV.Editor.asmdef)
│   │   └── Toolchain/               # Espelho empacotado dos scripts e docs limpos
│   ├── build_unitypackage.py        # Gerador autocontido do .unitypackage
│   └── install_unity_plugin.py      # Instalador não destrutivo para projetos Unity
├── configs/                         # Predefinições de blendshapes (*_blendshapes.cfg), PhysBones (*_physbones.cfg), npc_registry.json e active_multi_slots.json (.gitignore)
├── npcs/                            # Workspaces locais e modelos compilados de NPCs e pedestres (.gitignore)
├── docs/
│   ├── DEPLOYMENT_GUIDE.md          # Guia técnico completo (EN)
│   ├── DEPLOYMENT_GUIDE.pt-BR.md    # Arquitetura, Unity UI, VToon, rigging, Sollumz e RPF7 (PT-BR)
│   ├── DEPLOYMENT_GUIDE.ja.md       # Guia técnico completo (JA)
│   ├── UNITY_UI_GUIDE.md / .pt-BR.md / .ja.md # Guias ilustrados da UI no Unity (EN/PT-BR/JA)
│   └── images/                      # Capturas de tela da interface no Unity
├── scripts/
│   ├── common_tools/                # Builders universais, First-Run, .unity/cabelo/blendshapes/PhysBones/VToon/Restore/NPCs, i18n, test_mod_suite.py
│   ├── physbones_asi/               # Plugin ASI de PhysBones VRChat em tempo real (GTAVPhysBones.asi / .ini)
│   └── vtoon_asi/                   # Plugin ASI de shader lilToon D3D11 em tempo real (GTAVVToon.asi / .ini / vtoon_profiles)
├── _deploy_tools/                   # Dummies universais (head_000_r.ydd, p_eyes_dummy.ydd) e helpers de runtime
├── player_zero/                     # Saída intermediária para Michael (player_zero)
├── player_one/                      # Saída intermediária para Franklin (player_one)
├── player_two/                      # Saída intermediária para Trevor (player_two)
├── requirements.txt                 # Dependências Python 3.10+ (numpy, Pillow)
├── run_mod_manager.py               # Orquestrador principal via CLI e menu interativo
├── setup_first_run.py               # Ponto de entrada da configuração inicial (First-Run)
├── RUN_MANAGER.bat                  # Atalho interativo no Windows (EN/JA/PT)
├── EXECUTAR_GERENCIADOR.bat         # Atalho interativo no Windows (PT-BR)
├── vrc2gtav.cfg.example             # Modelo externo de configuração de caminhos
└── LICENSE                          # Licença MIT
```

Para detalhes completos sobre controles da interface no Unity, alinhamento de ossos, síntese de *lip sync* (padrão `0.70`), shader cel D3D11 `GTAVVToon.asi`, `.ytd`s de mip único, Restore Vanilla seletivo e segurança RPF7 de `4.00 GiB`, consulte o **[Guia da Interface no Unity](docs/UNITY_UI_GUIDE.pt-BR.md)** e o **[Guia Técnico e de Implantação](docs/DEPLOYMENT_GUIDE.pt-BR.md)**.

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
| **Blender** | `4.0.2` | Blender Foundation | [Site Oficial](https://www.blender.org/) |
| **Sollumz** | `v2.9.0` | `Skylumz`, `Colton`, `alexguirre` | [GitHub](https://github.com/Sollumz/Sollumz) · [Docs](https://docs.sollumz.org/) |
| **rage-cli** | `0.28.1` | `VIRUXE` | [GitHub](https://github.com/VIRUXE/rage-cli) |
| **RageOpenV** | — | `Chiheb-Bacha` | [GitHub](https://github.com/Chiheb-Bacha/RageOpenV) |
| **ScriptHookV** | — | `Alexander Blade` | [Site](https://www.dev-c.com/gtav/scripthookv/) |
| **Ultimate ASI Loader** | — | `ThirteenAG` | [GitHub](https://github.com/ThirteenAG/Ultimate-ASI-Loader) |

---

## Licença

Os scripts de automação e a documentação deste projeto são distribuídos sob a **Licença MIT** — consulte [`LICENSE`](LICENSE) (`Copyright (c) 2026 TheOkamoto`). Assets e ferramentas de terceiros permanecem regidos por suas respectivas licenças e termos de uso.
