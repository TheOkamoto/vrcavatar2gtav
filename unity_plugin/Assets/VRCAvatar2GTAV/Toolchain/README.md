<div align="center">

# `vrcavatar2gtav`

**Automated Unity Editor & CLI pipeline for converting VRChat Unity/FBX avatars into GTA V Legacy protagonists, story/cutscene NPCs, and street pedestrians — with real-time `GTAVVToon.asi` cel shading & `GTAVPhysBones.asi` physics**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Game: GTA V Legacy](https://img.shields.io/badge/Game-GTA%20V%20Legacy-2ea44f.svg)](docs/DEPLOYMENT_GUIDE.md)
[![Unity Plugin: VRCAvatar2GTAV](https://img.shields.io/badge/Unity%20Plugin-Tools%20%E2%86%92%20VRCAvatar2GTAV-5865F2.svg)](docs/DEPLOYMENT_GUIDE.md)
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
> This repository contains **zero** copyrighted BOOTH avatar/outfit models, Unity assets, or Rockstar Games / GTA V binary files. Every character model, texture, `.fbx`, `.unity`, `.ydd`, `.ytd`, `.yft`, `.ymt`, `.rpf`, generated NPC workspace (`npcs/`), and machine-local config (`vrc2gtav.cfg`, `configs/npc_registry.json`, `configs/active_multi_slots.json`) stays excluded via [`.gitignore`](.gitignore) (and from [`VRCAvatar2GTAV.unitypackage`](VRCAvatar2GTAV.unitypackage)).
>
> You must supply your own legally obtained BOOTH assets and legally owned **GTA V Legacy** installation, then use the **Unity Editor Plugin** (`Tools > VRCAvatar2GTAV > Export Avatar to GTA V`) or the **First-Run** CLI wizard to inspect paths and configure your environment.

---

## Overview

`vrcavatar2gtav` automates converting rigged **VRChat (Unity / FBX)** anime avatars into playable **GTA V Legacy** ped replacements for **Michael De Santa (`player_zero`)**, **Franklin Clinton (`player_one`)**, and **Trevor Philips (`player_two`)**, as well as any **GTA V story/cutscene NPC or street pedestrian** (`ig_*`, `cs_*`, `a_f_*`, `a_m_*`, etc., directly from Scene GameObjects, `.prefab`, `.unity`, `.zip`, or `.unitypackage`).

Beyond Blender **4.0.2**, **Sollumz v2.9.0**, and **`rage-cli` 0.28.1** automation, the `unity-ui` branch ships a **self-contained Unity Editor Exporter UI** ([`VRCAvatar2GTAV.unitypackage`](VRCAvatar2GTAV.unitypackage)) with tabbed per-protagonist export profiles, a real-time **D3D11 lilToon shader ASI (`GTAVVToon.asi`)**, **multi-ped VRChat PhysBones (`GTAVPhysBones.asi`)**, single-mip `2048px` `.ytd` locking, selective **Restore Vanilla**, and RPF7 `4.00 GiB` budget management.

### Example Videos

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
        <img src="https://img.shields.io/badge/YouTube_Shorts-Watch_Example_1-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Watch Example 1 on YouTube Shorts">
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
        <img src="https://img.shields.io/badge/YouTube_Shorts-Watch_Example_2-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Watch Example 2 on YouTube Shorts">
      </a>
    </td>
  </tr>
</table>

</div>

### Key Features

- **Unity Editor Exporter Plugin (`VRCAvatar2GTAV.unitypackage`)**: Open `Tools > VRCAvatar2GTAV > Export Avatar to GTA V` inside Unity ([`unity_plugin/Assets/VRCAvatar2GTAV/Editor/`](unity_plugin/Assets/VRCAvatar2GTAV/Editor/)). Features **Shared Mode** and the 4th **Per-Protagonist Independent Mode (`PerProtagonistSlots`)** (`configs/active_multi_slots.json` + `--slots-json`) for configuring all slots independently or swapping a single protagonist without altering the other two modded characters, drag-and-drop scene/prefab/`.unitypackage`/`.zip` picking, per-material `_MainTex` overrides, atlas (`512`–`4096`), normal (`Auto`/`Off`/`256`–`1024`), and secondary outfit (`Auto <3.7 GiB` / `512` / `1024` / `2048`) RPF7 estimators, mouth opening (`0.70` default + quick reset button) and eye-blink sliders, `.anim` override (`--face-anim`), live GTA V runtime status pills (`dinput8.dll`, `PhysBones.asi`, `VToon.asi`, `ScriptHookV.dll`, `OpenIV.asi` / RageOpenV), **Auto / Windows Native / WSL** backend switching, proportional multi-slot progress tracking (`0–82%` per slot + `82–100%` repack via `[PROGRESS pct=...]`), resizable console logs, and **Restore Vanilla** buttons.
- **Real-Time D3D11 lilToon Shader ASI (`GTAVVToon.asi`)**: [`scripts/vtoon_asi/`](scripts/vtoon_asi/gtav_vtoon.cpp) and [`scripts/common_tools/vtoon_profile_helper.py`](scripts/common_tools/vtoon_profile_helper.py) extract lilToon `.mat` parameters (including `m_Parent` inheritance), UV-region LUTs, MatCap textures, and `8×4` BC-aligned mip0 watermarks (`char_id` `1..15`, protagonist IDs `1..3`) into `GTAVVToon.ini` + `vtoon_profiles/`. Intercepts `D3D11CreateDevice*`, `ID3D11Device`, Immediate/Deferred `ID3D11DeviceContext`, `ID3D11DeviceContext1`, and overlay-safe `ScriptHookV` frame callbacks to deliver Half-Lambert dual-border cel shading, warm SSS terminator tints, rim light, forward-alpha hair/glass lens rendering (`kVToonForwardAlphaHlsl`), blurry GTA skin-pass bypass, and `F10` hot-reload with SHA-256 ASI sync verification.
- **Single-Mip `2048px` `.ytd`s, Clean Embedded Maps & Secondary Outfit Budgeting**: [`scripts/common_tools/universal_atlas_builder.py`](scripts/common_tools/universal_atlas_builder.py) writes single-texture external `.ytd`s locked at `--mips 1` so multi-character cutscenes never drop texture resolution under GTA V memory pressure, pairs them with valid `A8R8G8B8` neutral embedded bump/spec maps, and lets `--secondary-atlas-size` compact secondary `uppr_diff_001+` slots (`512`/`1024`/`auto`) while preserving full 2K primary `uppr_000` slots below RPF7's `4.00 GiB` ceiling.
- **Selective Restore-Vanilla (`--restore-peds` / `--restore-all`)**: [`scripts/common_tools/restore_vanilla_helper.py`](scripts/common_tools/restore_vanilla_helper.py) extracts only the target ped's original files from Rockstar vanilla RPFs into staging while preserving all other modded protagonists/NPCs intact, and prunes only those ped entries from `GTAVPhysBones.ini`, `GTAVVToon.ini`, and `configs/npc_registry.json`.
- **Native Modular Avatar (NDMF) Bake & Submesh Alignment**: [`scripts/common_tools/modular_avatar_helper.py`](scripts/common_tools/modular_avatar_helper.py), [`scripts/common_tools/blendshape_helper.py`](scripts/common_tools/blendshape_helper.py), and [`scripts/common_tools/build_universal_avatar.py`](scripts/common_tools/build_universal_avatar.py) natively bake outfits/dresses carrying `ModularAvatarMergeArmature`, `BoneProxy`, `ScaleAdjuster`, `MeshSettings`, `ObjectToggle`/`Activator`, `ReplaceObject`, `ShapeChanger` (`Delete` > `m_threshold` face culling separate from `Set` weights), `BlendshapeSync` (with `RemapCurve` re-evaluation after base preset application so nested outfit prefabs are never reset), manual `Shrink_* > 0.5` interior-face culling on `Body_base`/`Body`, `m_Materials` overrides, embedded `VRCPhysBone`s, and lilToon textures onto any protagonist/NPC, preserving translucent glass/lens alpha and matching Unity `Mesh` submesh slot order (`map_blender_slots_to_unity_submeshes`).
- **Separate Face & Body Blendshapes + `.anim` Preservation**: Prompts separately for face (`--import-face-blendshapes`) and body (`--import-body-blendshapes`) weights, supports `--face-anim` overrides, preserves Unity scene/preset facial blendshapes whenever `face_anim` is empty or all-zero, configures `--mouth-open-strength` (`0.70` default `FACIAL_jaw` ceiling), or generates an all-`0.0` `.cfg` including custom dress FBXs.
- **First-Run Wizard, `.zip`/Unity Ingestion & Blender 4.0.2 Auto-Download**: [`scripts/common_tools/avatar_archive_helper.py`](scripts/common_tools/avatar_archive_helper.py) safely extracts `.zip` / `.unitypackage` archives (Zip-Slip guarded), auto-downloads portable Blender `4.0.2` + `Sollumz` (`--download-blender`) and `rage-cli` (`--download-rage`), and shows a **10-per-page paginated avatar picker (`Next` / `Prev`)**.
- **Universal Custom Unity Hair, PhysBones & Protagonist Interchangeability**: Resolves arbitrary `.prefab` / `PrefabVariant` / `.fbx` hairs with Z-band island splitting, `VRCPhysBone` chains (`79` standard protagonist chains + unlimited per-NPC chains, VRChat `Advanced` `integrationType == 1` parent-relative `stiffness`, lower-hair/bow container spoke unwrapping, dual-stage orphan/unweighted chain pruning before and after Blender shape culling, priority packing `<= 63` custom bones keeping **hair/ears (`97–100`), breasts (`94`), and skirts (`90`)** at top priority above tails/coats/frills, optional `--physbones-marshmallow`), and full protagonist swapping (`[7]`, `--avatar`).
- **Universal GTA V NPC & Street Pedestrian Pipeline**: [`scripts/common_tools/npc_registry_helper.py`](scripts/common_tools/npc_registry_helper.py) and [`scripts/common_tools/universal_gtav_builder.py`](scripts/common_tools/universal_gtav_builder.py) port any Scene / `.prefab` / `.unity` / `.zip` / `.unitypackage` avatar directly onto any story/cutscene NPC (`ig_*`, `cs_*`) or street ped (`a_f_*`, `a_m_*`) via `--npc` / `--all-npcs` / `--target-ped`, with native jaw mapping (`FB_Jaw_000` / `FACIAL_C_Jaw` / `FACIAL_jaw`), `.001` vs `" 1"` bone suffix matching (`0` ungrouped vertices), dummy prop cleanup (`*_p` / `p_*.ydd`), and `GTAVPhysBones.asi` tracking up to **32 simultaneous peds (`kMaxTrackedPeds = 32`)**.
- **GTA V Blood & Wound Decals (`ped.sps` + 6-Zone `UVMap 1`)**: [`scripts/common_tools/ped_damage_helper.py`](scripts/common_tools/ped_damage_helper.py) enables gunshot wounds, slashes, and blood overlays (`--blood-decals`, enabled by default; `--no-blood-decals` for `ped_default.sps`) while excluding tails and long back hair.
- **Optional Natural Eye Blinking (`GTAVPhysBones.asi`)**: [`scripts/common_tools/eye_blink_helper.py`](scripts/common_tools/eye_blink_helper.py) drives smooth asymmetrical eyelid blinking (`2.6–6.0s` random intervals, curved-lash downward filter, eyebrow protection) across the four native `FACIAL_*_eyelidUpper*` bones (`0` PhysBone slots used), skipping avatars with custom closed-eye/winking expressions (`eye_blink = auto`, adjustable via `--eye-blink-strength` / `--no-eye-blink`).
- **Dedicated Error Handling, Trilingual i18n (`en`/`ja`/`pt`) & Automated Verification**: [`scripts/common_tools/error_handler_helper.py`](scripts/common_tools/error_handler_helper.py) writes timestamped `--verbose` logs under `logs/`; [`scripts/common_tools/test_mod_suite.py`](scripts/common_tools/test_mod_suite.py) runs **12** clean-clone source suites (`--source-only`) and **15** end-to-end validation suites. See also the [Unity Editor UI Guide (`docs/UNITY_UI_GUIDE.md`)](docs/UNITY_UI_GUIDE.md).

---

## Protagonists & Avatars

By default each protagonist starts with the preset below, and any VRChat avatar preset or custom Unity source can be assigned freely to any protagonist slot (`michael` / `player_zero`, `franklin` / `player_one`, `trevor` / `player_two`):

| Default GTA V Slot | Protagonist | Default VRChat Avatar (`avatar` ID) | Configured Preset / Outfit | Workspace Folder |
| :--- | :--- | :--- | :--- | :--- |
| `player_zero` | **Michael De Santa** | **Shinano** (`player_zero_michael`) | *Eternal Reunion* (Gothic Dress + Pocket Watch + optional custom Unity hair or default fallback) | `player_zero/` |
| `player_one` | **Franklin Clinton** | **Shinano** (`player_one_franklin`) | *Casual / Uniform* (Red Skirt + Recolored Hair, or optional custom Unity hair) | `player_one/` |
| `player_two` | **Trevor Philips** | **Miltina** (`player_two_trevor`) | *Classic Maid* (Black & White Dress, Apron, Twintails + optional custom Unity hair) | `player_two/` |

---

## Prerequisites

- **Grand Theft Auto V (Legacy)** installed locally
- **[Ultimate ASI Loader](https://github.com/ThirteenAG/Ultimate-ASI-Loader)** (`dinput8.dll`) + **[RageOpenV](https://github.com/Chiheb-Bacha/RageOpenV)** (or `OpenIV.asi`) in the GTA V directory to load `mods/`
- **[ScriptHookV](https://www.dev-c.com/gtav/scripthookv/)** (`ScriptHookV.dll`, recommended for overlay-safe frame/hotkey hooks in `GTAVVToon.asi` and ped tracking in `GTAVPhysBones.asi`)
- **[Blender 4.0.2](https://www.blender.org/)** with **[Sollumz v2.9.0](https://github.com/Sollumz/Sollumz)** *(auto-downloaded cleanly via `--download-blender` or the Unity UI setup button)*
- **`rage-cli` `0.28.1`** ([GitHub](https://github.com/VIRUXE/rage-cli)) for RPF7 repacking *(auto-downloaded via `--download-rage` or Unity UI setup)*
- **Python 3.10+** with dependencies from [`requirements.txt`](requirements.txt) (`numpy`, `Pillow`)
- *(Optional, for GUI workflow)* **Unity Editor 2022.3+** (VRChat Creator Companion project with `Assets/`)
- Your legally obtained **BOOTH avatar/outfit files**

---

## Quick Start

### Option A — Unity Editor Plugin (Recommended for Unity / VCC Projects)

1. Double-click [`VRCAvatar2GTAV.unitypackage`](VRCAvatar2GTAV.unitypackage) to import into your Unity project (or run the non-destructive CLI installer):
   ```bash
   python unity_plugin/install_unity_plugin.py --unity-project "/path/to/MyUnityProject"
   ```
2. In Unity, open **`Tools > VRCAvatar2GTAV > Export Avatar to GTA V`**.
3. Pick **Shared** mode or enable **Per-Protagonist Slots** tabs (`Michael`, `Franklin`, `Trevor`), drag/pick your avatar GameObjects, `.prefab`s, or `.zip`/`.unitypackage` files, adjust resolution/mouth opening (`0.70` default) / eye blink, verify tool & GTA V runtime pills (click **Download / Setup** if tools are missing), and click **Export**!

### Option B — CLI & Interactive Terminal Manager

1. **Clone the repository & install Python dependencies (`numpy`, `Pillow`)**
   ```bash
   git clone https://github.com/TheOkamoto/vrcavatar2gtav.git
   cd vrcavatar2gtav
   pip install -r requirements.txt
   ```

2. **Verify your clean clone** *(optional)*
   ```bash
   python scripts/common_tools/test_mod_suite.py --source-only
   ```

3. **Run First-Run Setup** — launch [`RUN_MANAGER.bat`](RUN_MANAGER.bat) (Windows) or:
   ```bash
   python run_mod_manager.py --setup
   ```
   Or audit your environment without changes:
   ```bash
   python scripts/common_tools/setup_first_run.py --check-only
   ```

4. **Build & Deploy All Protagonists**
   ```bash
   python run_mod_manager.py --character all
   ```

---

## Configuration & Fallback Behavior

- **External Config (`vrc2gtav.cfg`) & Bundled Toolchain**: Copy [`vrc2gtav.cfg.example`](vrc2gtav.cfg.example) to `vrc2gtav.cfg` (or let `--setup` / the Unity Exporter generate it) to configure GTA V Legacy, Blender, `rage-cli`, and source assets. When installed via `.unitypackage`, `Vrc2GtavConfigDiscovery` prioritizes `Assets/VRCAvatar2GTAV/Toolchain` by default while redirecting generated builds into a clean `<ProjectRoot>/VRCAvatar2GTAV_Work` workspace.
- **Scale Handling (`1.0` + `.unity` Parser)**: Character proportions default to `[1.0, 1.0, 1.0]`, and `.unity` scene transforms automatically apply custom hierarchy scales.
- **Blendshape Presets, MA Shape/Sync & Scene/Archive `.cfg` Naming (`Unity` & `configs/*_blendshapes.cfg`)**: Facial, body-shrink, outfit, accessory, and hair keys resolve via [`scripts/common_tools/blendshape_helper.py`](scripts/common_tools/blendshape_helper.py) from `.unity` / nested `.prefab` / `.anim` or UTF-8 `.cfg` presets (`blendshapes_source = auto | unity | cfg`). When exporting any Booth avatar automatically, generated `.cfg` files are named after the **Unity `.unity` scene** (or the user-supplied `.zip`/`.unitypackage` filename stem in CLI mode) and begin with `# Generated`, `# Project`, `# Scene`, and `# FBX` metadata comments. Empty or all-zero `.anim` overrides preserve scene/preset facial blendshapes. Modular Avatar `ShapeChanger` (`Delete` vs `Set`) and `BlendshapeSync` (`RemapCurve`) run after base weight resets, while manual `Shrink_* > 0.5` keys on `Body_base` / `Body` automatically cull fully shrunk interior triangles before poly budgeting.
- **Automatic VRChat PhysBones Importer & Priority Packer (`Unity` & `configs/*_physbones.cfg`)**: [`scripts/common_tools/physbone_helper.py`](scripts/common_tools/physbone_helper.py) imports active `VRCPhysBone` components (`PrefabInstance` overrides, lower-hair/bow spoke unwrapping, orphaned/loose chain pruning in Unity extraction plus final post-cull active-vertex pruning in Blender), packs within RAGE's `<= 63` custom / `<= 128` total `.ydd` limit (`--physbones-marshmallow` optional), and prioritizes **hair/ears (`97–100`), breasts (`94`), and skirts (`90`)** at top priority above tails/wings (`82`), outerwear (`68`), and minor ribbons/accessories (`PHYSBONE_PRIORITY_TIERS`).
- **Universal Custom Hair & Face Fallbacks**:
  - **Any Booth / VRChat Avatar**: Supports `custom_hair = auto | default | none | <path to .prefab or .fbx>` (`[8]` / `--hair`, `--hair-mat`, `--hair-tex`, `--hair-scale`, `--hair-offset`) via [`scripts/common_tools/unity_hair_helper.py`](scripts/common_tools/unity_hair_helper.py) & [`scripts/common_tools/blender_hair_helper.py`](scripts/common_tools/blender_hair_helper.py), falling back cleanly to native hair and expression animations when no custom override is specified.
- **Language Detection**: Scripts auto-detect system locale (`en`, `ja`, `pt`) and accept `--lang en|ja|pt`.

---

## CLI Usage & Validation Tests

| Command | Purpose |
| :--- | :--- |
| `RUN_MANAGER.bat` / `EXECUTAR_GERENCIADOR.bat` | Interactive Windows launcher for First-Run, build, and deploy |
| `python unity_plugin/install_unity_plugin.py --unity-project "/path/Project"` | Non-destructively install `Assets/VRCAvatar2GTAV/` UI + Toolchain into a Unity project (cleaning legacy files/metas) |
| `python unity_plugin/build_unitypackage.py` | Stage `Assets/VRCAvatar2GTAV/Toolchain/` and rebuild `VRCAvatar2GTAV.unitypackage` |
| `python run_mod_manager.py --setup` | Interactive First-Run wizard & `vrc2gtav.cfg` setup |
| `python run_mod_manager.py --setup --avatar-zip "/path/Avatar.zip" --download-blender --verbose` | Extract `.zip`/`.unitypackage`, download Blender `4.0.2` + Sollumz, paginate (`10`/page), configure MA/Face/Body `.cfg` & save log in `logs/` |
| `python scripts/common_tools/build_universal_avatar.py --avatar-zip "/path/Avatar.zip" --interactive --verbose` | Standalone universal Modular Avatar builder for any Booth avatar with 10-per-page picker & timestamped logs |
| `python scripts/common_tools/universal_gtav_builder.py --slots-json "configs/active_multi_slots.json"` | Sequential multi-slot protagonist build (`PerProtagonistSlots`) with single shared RPF7 repack (`--secondary-atlas-size`, `--atlas-size`, `--mouth-open-strength`, `--face-anim`) |
| `python scripts/common_tools/universal_gtav_builder.py --target-character michael --atlas-only` | Build only the single-mip 2K `.ytd` atlas via the universal pipeline (add `--skip-atlas --no-deploy` to compile `.ydd` only) |
| `python scripts/common_tools/universal_gtav_builder.py --restore-peds player_zero` | Selectively restore a protagonist/NPC to Rockstar vanilla (`--restore-all` restores all modded peds) preserving all other modded slots |
| `python run_mod_manager.py --check-env` / `setup_first_run.py --check-only` | Validate GTA V, Blender, `rage-cli`, and configured asset paths |
| `python run_mod_manager.py --character {all,michael,franklin,trevor} --lang {en,ja,pt}` | Full 3D Blender rebuild, YDD/YTD export, `GTAVVToon`/`GTAVPhysBones` sync, and RPF7 deployment |
| `python run_mod_manager.py --character franklin --avatar player_two_trevor` | Assign any configured profile (`player_zero_michael`, `player_one_franklin`, `player_two_trevor`) onto any protagonist (`--save-assignment`) |
| `python run_mod_manager.py --character michael --hair "/path/Hair.prefab" --save-hair` | Port any `.prefab` / `PrefabVariant` / `.fbx` custom hair (`--hair default` / `none` / `--hair-mat` / `--hair-tex` / `--hair-scale` / `--hair-offset`) |
| `python run_mod_manager.py --export-blendshapes` / `--blendshapes-source cfg` | Export `.cfg` blendshapes from `.unity` scenes or build from portable `.cfg` presets |
| `python run_mod_manager.py --export-physbones` / `--physbones-source cfg` | Sync VRCPhysBones presets (`--physbones-marshmallow`, `--overwrite-physbones-from-unity`) |
| `python run_mod_manager.py --character all --blood-decals --eye-blink` | Configure blood/wound decals (`--no-blood-decals`), natural eye blink (`--eye-blink-strength`, `--no-eye-blink`), and `--mouth-open-strength` (`0.70` default) |
| `python run_mod_manager.py --npc ig_lamardavis --avatar-zip "/path/Avatar.zip"` | Build & deploy any GTA V NPC (`ig_*`, `cs_*`) or street ped (`a_f_*`, `a_m_*`) directly (`--all-npcs` / `--target-ped ... --deploy-npc`) |
| `python run_mod_manager.py --deploy-only` | Repack and deploy already-built character, registered NPC folders, and ASI plugins to `mods/` |
| `python scripts/common_tools/test_mod_suite.py --source-only` | Run all **12** clean-clone source/config/Unity/VToon/MA-Shape/Cross-Avatar/i18n/AST suites |
| `python scripts/common_tools/test_mod_suite.py` | Run all **15** end-to-end validation suites (requires built & deployed assets) |

---

## Repository Layout

```text
vrcavatar2gtav/
├── VRCAvatar2GTAV.unitypackage      # Ready-to-import Unity Editor plugin + bundled Toolchain (.gitignore'd / built via build_unitypackage.py)
├── unity_plugin/
│   ├── Assets/VRCAvatar2GTAV/
│   │   ├── Editor/                  # 9 C# Unity Editor UI scripts (VRCAvatar2GTAV.Editor.asmdef)
│   │   └── Toolchain/               # Staged mirror of clean automation scripts & docs
│   ├── build_unitypackage.py        # Self-contained .unitypackage builder
│   └── install_unity_plugin.py      # Non-destructive Unity project installer
├── configs/                         # Blendshape presets (*_blendshapes.cfg), PhysBones (*_physbones.cfg), & local npc_registry.json / active_multi_slots.json (.gitignore)
├── npcs/                            # Local custom NPC & street ped workspaces / compiled models (gitignored)
├── docs/
│   ├── DEPLOYMENT_GUIDE.md          # Full architecture, Unity UI, VToon, rigging, Sollumz & RPF7 guide (EN)
│   ├── DEPLOYMENT_GUIDE.pt-BR.md    # Full technical guide (PT-BR)
│   ├── DEPLOYMENT_GUIDE.ja.md       # Full technical guide (JA)
│   ├── UNITY_UI_GUIDE.md / .pt-BR.md / .ja.md # Illustrated Unity Exporter UI guides (EN/PT-BR/JA)
│   └── images/                      # Unity Editor UI screenshots
├── scripts/
│   ├── common_tools/                # Universal builders, First-Run, .unity/hair/blendshape/PhysBones/VToon/Restore/NPC helpers, i18n, test_mod_suite.py
│   ├── physbones_asi/               # Real-time VRChat PhysBones ASI plugin (GTAVPhysBones.asi / .ini)
│   └── vtoon_asi/                   # Real-time D3D11 lilToon shader ASI plugin (GTAVVToon.asi / .ini / vtoon_profiles)
├── _deploy_tools/                   # Universal slot dummies (head_000_r.ydd, p_eyes_dummy.ydd) & runtime helpers
├── player_zero/                     # Output staging folder for Michael (player_zero)
├── player_one/                      # Output staging folder for Franklin (player_one)
├── player_two/                      # Output staging folder for Trevor (player_two)
├── requirements.txt                 # Python 3.10+ dependencies (numpy, Pillow)
├── run_mod_manager.py               # Main CLI & interactive orchestrator
├── setup_first_run.py               # First-Run setup entrypoint
├── RUN_MANAGER.bat                  # Windows interactive menu (EN/JA/PT)
├── EXECUTAR_GERENCIADOR.bat         # Windows interactive menu launcher (PT-BR shortcut)
├── vrc2gtav.cfg.example             # Sample external path configuration
└── LICENSE                          # MIT License
```

For in-depth documentation on the Unity UI, skeleton bone alignment, hand curl calibration, lip-sync morph synthesis (`0.70` default), `GTAVVToon.asi` HLSL cel shading, single-mip `.ytd`s, selective Restore Vanilla, and RPF7 `4.00 GiB` safety, read the **[Unity Editor UI Guide](docs/UNITY_UI_GUIDE.md)** and the **[Deployment & Technical Guide](docs/DEPLOYMENT_GUIDE.md)**.

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
| **ScriptHookV** | — | `Alexander Blade` | [Website](https://www.dev-c.com/gtav/scripthookv/) |
| **Ultimate ASI Loader** | — | `ThirteenAG` | [GitHub](https://github.com/ThirteenAG/Ultimate-ASI-Loader) |

---

## License

This project's automation scripts and documentation are released under the **MIT License** — see [`LICENSE`](LICENSE) (`Copyright (c) 2026 TheOkamoto`). Third-party assets and tools listed above remain governed by their own respective licenses and terms of use.
