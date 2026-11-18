<div align="center">

# `vrcavatar2gtav`

**Automated pipeline for converting VRChat Unity/FBX avatars into GTA V Legacy player ped replacements**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Game: GTA V Legacy](https://img.shields.io/badge/Game-GTA%20V%20Legacy-2ea44f.svg)](docs/DEPLOYMENT_GUIDE.md)
[![Blender: 4.0.2 + Sollumz v2.9.0](https://img.shields.io/badge/Blender-4.0.2%20%2B%20Sollumz%20v2.9.0-orange.svg)](https://docs.sollumz.org/)
[![rage--cli: 0.28.1](https://img.shields.io/badge/rage--cli-0.28.1-blue.svg)](https://github.com/VIRUXE/rage-cli)
[![i18n: EN | JA | PT](https://img.shields.io/badge/i18n-EN%20%7C%20JA%20%7C%20PT-lightgrey.svg)](docs/DEPLOYMENT_GUIDE.md)

**English** · [Português (BR)](README.pt-BR.md) · [日本語](README.ja.md)

📖 **[Full Deployment & Technical Guide (`docs/DEPLOYMENT_GUIDE.md`)](docs/DEPLOYMENT_GUIDE.md)**

</div>

---

> [!IMPORTANT]
> **Copyright & Asset Redistribution Notice**
>
> This repository contains **zero** copyrighted BOOTH avatar/outfit models, Unity packages, or Rockstar Games / GTA V binary files. Every character model, texture, `.fbx`, `.unity`, `.ydd`, `.ytd`, `.yft`, `.ymt`, and `.rpf` asset stays excluded via [`.gitignore`](.gitignore).
>
> You must supply your own legally obtained BOOTH assets and legally owned **GTA V Legacy** installation, then run the interactive **First-Run** setup wizard to inspect your paths and extract/configure the environment.

---

## Overview

`vrcavatar2gtav` automates converting rigged **VRChat (Unity / FBX)** anime avatars into playable **GTA V Legacy** ped replacements for **Michael De Santa (`player_zero`)**, **Franklin Clinton (`player_one`)**, and **Trevor Philips (`player_two`)**.

Instead of manual bone tweaking and brittle one-off edits, the pipeline coordinates **Blender 4.0.2**, **Sollumz v2.9.0**, and **`rage-cli` 0.28.1** end-to-end — handling skeleton remapping, hand/finger grip alignment, lip-sync morph weights, texture/material calibration, clean `1.0` default scaling (with optional `.unity` scene transform extraction), universal slot packing, and safe RPF7 deployment (`mods/x64v.rpf`).

### Key Features

- **First-Run Setup & Cross-Platform Config**: Guided setup wizard and external [`vrc2gtav.cfg`](vrc2gtav.cfg.example) override keep local paths out of version control.
- **Trilingual Support (`en` / `ja` / `pt`)**: Automatic OS locale detection with explicit `--lang` CLI override across managers, setup tools, and automated test suites.
- **Unit `1.0` Defaults + `.unity` Scale Extraction**: Defaults body scales cleanly to `1.0` out of the box, while automatically reading and extracting custom hierarchy scales when a `.unity` scene file is provided.
- **Universal Custom Unity Hair Porting (`.prefab` / `PrefabVariant` / `.fbx`)**: Automatically parses any VRChat Unity hair prefab, Modular Avatar attachment, or `.fbx` + `.mat`, bakes lilToon color/HSV tints into the 2K atlas, aligns the hair onto the target avatar's skull, and falls back gracefully to default avatar hair (`default` / `none` / missing custom hair).
- **Full Avatar <-> Protagonist Interchangeability**: Any VRChat preset (`shinano_casual`, `shinano_er`, `miltina_maid`) can be assigned to any GTA V protagonist (`michael`, `franklin`, `trevor`) via `[7]` in the interactive menu, CLI `--avatar` / `--*-avatar` flags, or `vrc2gtav.cfg`.
- **Automated Verification**: Includes both a fast source-only check (`7` suites, works on a fresh GitHub clone) and a full post-build/deploy validation suite (`10` suites).

---

## Protagonists & Avatars

By default each protagonist starts with the preset below, and every VRChat avatar preset can be freely assigned to any protagonist slot (`michael`, `franklin`, or `trevor`):

| Default GTA V Slot | Protagonist | Default VRChat Avatar (`avatar` ID) | Configured Preset / Outfit | Workspace Folder |
| :--- | :--- | :--- | :--- | :--- |
| `player_zero` | **Michael De Santa** | **Shinano** (`shinano_er`) | *Eternal Reunion* (Gothic Dress + Pocket Watch + optional custom Unity hair or *Neko Tied Bob Hair*, falls back to default Shinano hair) | [`2_Michael_Shinano_EternalReunion/`](2_Michael_Shinano_EternalReunion/) |
| `player_one` | **Franklin Clinton** | **Shinano** (`shinano_casual`) | *Casual / Uniform* (Red Skirt + Recolored Default Shinano Hair, or optional custom Unity hair) | [`1_Franklin_Shinano_Casual/`](1_Franklin_Shinano_Casual/) |
| `player_two` | **Trevor Philips** | **Miltina** (`miltina_maid`) | *Classic Maid* (Black & White Dress, Apron, Twintails + optional custom Unity hair) | [`3_Trevor_Miltina_Maid/`](3_Trevor_Miltina_Maid/) |

---

## Prerequisites

- **Grand Theft Auto V (Legacy)** installed locally
- **[Ultimate ASI Loader](https://github.com/ThirteenAG/Ultimate-ASI-Loader)** + **[RageOpenV](https://github.com/Chiheb-Bacha/RageOpenV)** installed in the GTA V game directory (required to load the `mods/` folder)
- **[Blender 4.0.2](https://www.blender.org/)** with **[Sollumz v2.9.0](https://github.com/Sollumz/Sollumz)**
- **`rage-cli` `0.28.1`** ([GitHub](https://github.com/VIRUXE/rage-cli)) for RPF7 repacking
- **Python** environment to run [`run_mod_manager.py`](run_mod_manager.py) and validation scripts
- Your legally obtained **BOOTH avatar/outfit files** (plus optional Unity project / `.unity` scene files)

---

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/TheOkamoto/vrcavatar2gtav.git
   cd vrcavatar2gtav
   ```

2. **Verify your clean clone** *(optional)*
   ```bash
   python scripts/common_tools/test_mod_suite.py --source-only
   ```

3. **Run First-Run Setup**
   Launch [`RUN_MANAGER.bat`](RUN_MANAGER.bat) (Windows) or run the CLI wizard directly:
   ```bash
   python run_mod_manager.py --setup
   ```
   This inspects your GTA V Legacy directory, Blender `4.0.2`, `rage-cli`, and source assets, and helps configure [`vrc2gtav.cfg.example`](vrc2gtav.cfg.example) -> `vrc2gtav.cfg` (gitignored). You can also run a non-destructive pre-flight check at any time:
   ```bash
   python scripts/common_tools/setup_first_run.py --check-only
   ```

4. **Build & Deploy All Protagonists**
   ```bash
   python run_mod_manager.py --character all
   ```

---

## Configuration & Fallback Behavior

- **External Config (`vrc2gtav.cfg`)**: Copy [`vrc2gtav.cfg.example`](vrc2gtav.cfg.example) to `vrc2gtav.cfg` (or create it via `--setup`) to point to your GTA V Legacy folder, Blender executable, `rage-cli`, and local source FBX/Unity assets without editing code.
- **Scale Handling (`1.0` + `.unity` Parser)**: Character proportions default to `[1.0, 1.0, 1.0]`. If a `.unity` scene is supplied for your avatar, the pipeline reads the transform hierarchy from the `.unity` file and applies those scales automatically.
- **Blendshape Presets (`Unity` & `configs/*_blendshapes.cfg`)**: Every facial, body-shrink, outfit, accessory, and hair blendshape is resolved via [`scripts/common_tools/blendshape_helper.py`](scripts/common_tools/blendshape_helper.py) from either your Unity project (`.unity` + nested `.prefab` + `.anim`) or portable tracked `.cfg` presets under [`configs/`](configs/) (`shinano_blendshapes.cfg`, `shinano_er_blendshapes.cfg`, `miltina_blendshapes.cfg`). Controlled per character via `blendshapes_source = auto | unity | cfg` and `blendshapes_cfg`.
- **Automatic VRChat PhysBones Importer (`Unity` & `configs/*_physbones.cfg`)**: [`scripts/common_tools/physbone_helper.py`](scripts/common_tools/physbone_helper.py) imports active standard `VRCPhysBone` components (including nested `PrefabInstance` overrides), packs them safely within RAGE's `<= 63` custom-bone / `<= 128` total `.ydd` limit (`0` ELF hash collisions), and exports or reads portable `.cfg` presets (`michael_neko_mimi_physbones.cfg`: `30` chains / `62` bones; `shinano_casual_physbones.cfg`: `24` chains / `62` bones; `miltina_maid_physbones.cfg`: `25` chains / `58` bones — `79` chains / `182` custom bones total). Optional `marshmallow_PB` breast presets are disabled by default and can be enabled anytime via `physbones_marshmallow = true` or `--physbones-marshmallow` (`81` chains / `186` bones total). Controlled via `physbones_source = auto | unity | cfg`, `physbones_cfg`, `--physbones-marshmallow`, and interactive menu `[10]`.
- **Universal Custom Hair & Face Fallbacks**:
  - **Any Avatar Preset**: Supports `custom_hair = auto | default | none | <path to .prefab or .fbx>` (plus optional `hair_mat`, `hair_tex`, `hair_scale`, `hair_offset`) in `vrc2gtav.cfg`, interactive menu option `[8]`, or `--hair` CLI overrides across `shinano_casual`, `shinano_er`, and `miltina_maid`. [`scripts/common_tools/unity_hair_helper.py`](scripts/common_tools/unity_hair_helper.py) resolves `PrefabVariant` chains, Modular Avatar attachments, `.fbx.meta` material maps, and lilToon textures/tints into `custom_hair_manifest.json`, while [`scripts/common_tools/blender_hair_helper.py`](scripts/common_tools/blender_hair_helper.py) fits the hair onto the skull, remaps UVs, and preserves base animal ears.
  - **Shinano**: Uses configured `custom_hair` / *Neko Tied Bob Hair* when provided; otherwise defaults automatically to Shinano's base hair (`Hair_base`, `Hair_bang`, `Hair_side`, `Hair_back`, `Other_ear`, `Other_tail`) and `ShinanoDefAdultNewv5.anim` / base eye textures.
  - **Miltina**: Supports any `custom_hair` (or legacy `fbx_hair`) override; otherwise defaults automatically to Miltina's base twintails (`Milltina_hair_*`) and `Miltina_close eyes_Base_adult.anim` / base eye textures.
- **Language Detection**: Scripts inspect system locale (`en`, `ja`, `pt`) automatically and can be overridden explicitly with `--lang en|ja|pt`.

---

## CLI Usage & Validation Tests

| Command | Purpose |
| :--- | :--- |
| `RUN_MANAGER.bat` / `EXECUTAR_GERENCIADOR.bat` | Interactive Windows launcher for First-Run, build, and deploy |
| `python run_mod_manager.py --setup` | Interactive First-Run wizard & `vrc2gtav.cfg` configuration |
| `python run_mod_manager.py --check-env` | Validate GTA V, Blender, `rage-cli`, and configured asset paths |
| `python scripts/common_tools/setup_first_run.py --check-only` | Non-destructive environment & source asset audit |
| `python run_mod_manager.py --character all` | Full 3D Blender rebuild, XML/YDD/YTD export, and RPF7 deployment |
| `python run_mod_manager.py --character {michael,franklin,trevor} --lang {en,ja,pt}` | Build/deploy a single protagonist in the selected UI language |
| `python run_mod_manager.py --character franklin --avatar miltina_maid` | Build & deploy any VRChat preset (`shinano_casual`, `shinano_er`, `miltina_maid`) onto any protagonist (`--save-assignment` persists to `vrc2gtav.cfg`) |
| `python run_mod_manager.py --character michael --hair "/path/Hair.prefab" --save-hair` | Port any Unity `.prefab` / `PrefabVariant` / `.fbx` custom hair onto a protagonist (`--hair default` / `none` / `--hair-mat` / `--hair-tex` / `--hair-scale` / `--hair-offset`) |
| `python run_mod_manager.py --export-blendshapes` | Export blendshapes from configured `.unity` scenes to `configs/*_blendshapes.cfg` |
| `python run_mod_manager.py --character all --blendshapes-source cfg` | Build using portable `.cfg` blendshape presets instead of Unity scenes |
| `python run_mod_manager.py --export-physbones` | Auto-import standard VRChat PhysBones presets from `.unity` scenes into `configs/*_physbones.cfg` (`--physbones-marshmallow` includes Marshmallow PB; `--overwrite-physbones-from-unity` overwrites edits) |
| `python run_mod_manager.py --character all --physbones-source cfg` | Build using portable `.cfg` PhysBone presets instead of live `.unity` scenes (add `--physbones-marshmallow` to enable Marshmallow PB breasts) |
| `python run_mod_manager.py --deploy-only` | Repack and deploy already-built character folders to `mods/x64v.rpf` |
| `python scripts/common_tools/test_mod_suite.py --source-only` | Run the `7` source/config/i18n/interchangeability/custom-hair suites (clean clone safe) |
| `python scripts/common_tools/test_mod_suite.py` | Run all `10` end-to-end validation suites (requires built & deployed assets) |

---

## Repository Layout

```text
vrcavatar2gtav/
├── configs/                         # Blendshape presets (*_blendshapes.cfg) & PhysBones (*_physbones.cfg)
├── docs/
│   ├── DEPLOYMENT_GUIDE.md          # Full architecture, rigging, Sollumz, shader & RPF7 guide (EN)
│   ├── DEPLOYMENT_GUIDE.pt-BR.md    # Full technical guide (PT-BR)
│   └── DEPLOYMENT_GUIDE.ja.md       # Full technical guide (JA)
├── scripts/
│   ├── common_tools/                # First-run, .unity/hair/blendshape/PhysBones helpers, i18n, test_mod_suite.py
│   ├── physbones_asi/               # Real-time VRChat PhysBones ASI plugin (GTAVPhysBones.asi / .ini)
│   ├── Shinano_Casual_Franklin/     # Franklin (player_one) build scripts
│   ├── Shinano_EternalReunion_Michael/ # Michael (player_zero) build scripts
│   └── Miltina_Maid_Trevor/         # Trevor (player_two) build scripts
├── _deploy_tools/                   # Universal slot dummies (head_000_r.ydd, p_eyes_dummy.ydd) & runtime helpers
├── 1_Franklin_Shinano_Casual/       # Output staging folder for player_one
├── 2_Michael_Shinano_EternalReunion/# Output staging folder for player_zero
├── 3_Trevor_Miltina_Maid/           # Output staging folder for player_two
├── run_mod_manager.py               # Main CLI & interactive orchestrator
├── RUN_MANAGER.bat                  # Windows interactive menu (EN/JA/PT)
├── EXECUTAR_GERENCIADOR.bat         # Windows interactive menu launcher (PT-BR shortcut)
├── vrc2gtav.cfg.example             # Sample external path configuration
└── LICENSE                          # MIT License
```

For in-depth documentation on skeleton bone alignment, hand curl calibration, lip-sync morph synthesis, JOAAT texture hashing, `Sollumz` shaders, universal dummy slot replacement (`ERR_GEN_ZLIB_2` prevention), and manual step-by-step troubleshooting, read the **[Deployment & Technical Guide](docs/DEPLOYMENT_GUIDE.md)**.

---

## Credits — Assets & Tools

All third-party 3D models, outfits, hair, eye textures, Unity packages, and conversion tools remain the intellectual property of their respective authors.

### 3D Avatar, Outfit, Hair & Eye Assets (BOOTH)

| GTA V Protagonist(s) | Category | Asset Name | Creator / Circle | BOOTH Link |
| :--- | :--- | :--- | :--- | :--- |
| Michael, Franklin | Base Avatar & Casual Outfit *(Required)* | **オリジナル3Dモデル「しなの」 (*Shinano*)** | ポンデロニウム研究所 (`ponderogen`) | [Item #6106863](https://ponderogen.booth.pm/items/6106863) · [Shop](https://ponderogen.booth.pm/) |
| Trevor | Base Avatar & Maid Outfit *(Required)* | **オリジナル3Dモデル『ミルティナ』 (*Milltina*)** | DOLOS art (`dolosart`) | [Item #6538026](https://dolosart.booth.pm/items/6538026) · [Shop](https://dolosart.booth.pm/) |
| Michael | Dress, Shoes & Accessories *(Required for Michael)* | **【15アバター対応】エターナル・リユニオン【MA対応】 (*Eternal Reunion* + *Pocket Watch*)** | VAGRANT (`Vagrant Brand`) | [Item #5634313](https://vagrant.booth.pm/items/5634313) · [Shop](https://vagrant.booth.pm/) |
| Michael | Hair, Cat Ears, Clips & Halo *(Optional — falls back to default Shinano hair)* | **ねこタイドボブヘア (*Neko Tied Bob hair*)** | Li-ne (`Li-ne_Shop`) | [Item #7977491](https://li-ne.booth.pm/items/7977491) · [Shop](https://li-ne.booth.pm/) |
| Michael, Franklin | Eye Texture *(Optional)* | **`[eye17アバター対応]MoonButterfly eye & Rurune Make`** | ha-oa | [Item #8483652](https://ha-oa.booth.pm/items/8483652) · [Shop](https://ha-oa.booth.pm/) |
| Trevor | Eye Texture *(Optional)* | **お魚が泳ぐ あわあわ水光 Eye Texture【10Color】【23Avatar】 (`Milltina_AWEyes`)** | NAGIMA (`nagikawamart`) | [Item #6837271](https://nagikawamart.booth.pm/items/6837271) · [Shop](https://nagikawamart.booth.pm/) |

<details>
<summary>Mesh, accessory & FaceEmo preset breakdown per character</summary>

- **Michael De Santa (`player_zero`) — Shinano (*Eternal Reunion*)**
  - **Base Body**: `Body`, `Body_base` (*Shinano*)
  - **Outfit**: `UN1_Shirt`, `UN1_Skirt`, `UN2_Corset`, `UN2_Stocking`, `UN2_Shoes` (*Eternal Reunion*)
  - **Accessories**: `UN1_ChestRibbon`, `UN1_Choker`, `UN3_Bag`, `UN3_Glasses`, `UN3_WaistChain`, `Pocket Watch` (*Eternal Reunion*; `UN2_Beret` disabled)
  - **Hair *(Optional)***: `Bangs`, `Top Back`, `Under Side`, `Back`, `Side Bangs`, `Side`, `In Hair`, `Ears`, `Ribbon`, `_Pin.Back`, `_Pin.R`, `_Pin.L2`, `_Halo` (*Neko Tied Bob hair*; falls back to default Shinano hair if omitted)
  - **Eye Texture & Expression *(Optional / Fallback)***: `MoonButterfly eye` & `ShinanoDefAdultNewv5.anim`

- **Franklin Clinton (`player_one`) — Shinano (*Casual / Uniform*)**
  - **Base Body**: `Body`, `Body_base` (*Shinano*)
  - **Outfit**: `Cloth_sweater`, `Cloth_skirt`, `Cloth_tights`, `Cloth_boots` (*Shinano*)
  - **Hair**: `Hair_back`, `Hair_bang`, `Hair_base`, `Hair_side`, `Other_ear`, `Other_tail` (*Shinano* default hair; supports optional `custom_hair` override while preserving cat ears)
  - **Eye Texture & Expression *(Optional / Fallback)***: `MoonButterfly eye` & `ShinanoDefAdultNewv5.anim`

- **Trevor Philips (`player_two`) — Miltina (*Classic Maid*)**
  - **Base Body**: `Body`, `Milltina_body` (*Milltina*)
  - **Outfit & Accessories**: `Milltina_cloth_dress`, `Milltina_cloth_apron`, `Milltina_cloth_skirt`, `Milltina_cloth_panties`, `Milltina_cloth_collar`, `Milltina_cloth_hat`, `Milltina_cloth_neck_ribbon`, `Milltina_cloth_wrist_cuffs`, `Milltina_cloth_garterbelt`, `Milltina_cloth_hair_ribbon`, `Milltina_cloth_tail_ribbon`, `Milltina_cloth_tail_slit`, `Milltina_cloth_shoes` (*Milltina*)
  - **Hair & Cow Parts**: `Milltina_hair_base`, `Milltina_hair_side`, `Milltina_hair_front`, `Milltina_hair_front_side`, `Milltina_hair_twintail`, `Milltina_cow_ears`, `Milltina_cow_horns`, `Milltina_cow_tail` (*Milltina*; supports optional `custom_hair` / `fbx_hair` override)
  - **Eye Texture & Expression *(Optional / Fallback)***: `Milltina_AWEyes` & `Miltina_close eyes_Base_adult.anim`

</details>

### Unity Packages & GTA V / Blender Tooling

| Tool / Package | Version | Author(s) | Link |
| :--- | :--- | :--- | :--- |
| **lilToon** | `v2.4.1` | `lilxyzw` | [GitHub](https://github.com/lilxyzw/lilToon) · [Website](https://lilxyzw.github.io/lilToon/) |
| **FaceEmo** | `v1.7.0` | `suzuryg` | [GitHub](https://github.com/suzuryg/face-emo) · [Website](https://suzuryg.github.io/face-emo/) |
| **Modular Avatar** | `v1.18.7` | `bd_` (Nadena) | [GitHub](https://github.com/bdunderscore/modular-avatar) · [Website](https://modular-avatar.nadena.dev/) |
| **Blender** | `4.0.2` | Blender Foundation | [Website](https://www.blender.org/) |
| **Sollumz** | `v2.9.0` | `Skylumz`, `Colton`, `alexguirre` | [GitHub](https://github.com/Sollumz/Sollumz) · [Docs](https://docs.sollumz.org/) |
| **rage-cli** | `0.28.1` | `VIRUXE` | [GitHub](https://github.com/VIRUXE/rage-cli) |
| **RageOpenV** | — | `Chiheb-Bacha` | [GitHub](https://github.com/Chiheb-Bacha/RageOpenV) |
| **Ultimate ASI Loader** | — | `ThirteenAG` | [GitHub](https://github.com/ThirteenAG/Ultimate-ASI-Loader) |

---

## License

This project's automation scripts and documentation are released under the **MIT License** — see [`LICENSE`](LICENSE) (`Copyright (c) 2026 TheOkamoto`). Third-party assets and tools listed above remain governed by their own respective licenses and terms of use.
