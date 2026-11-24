<div align="center">

# `vrcavatar2gtav`

**VRChat 向け Unity/FBX アバターを GTA V Legacy の主人公・ストーリー/カットシーン NPC・街中歩行者へ自動変換・導入する Unity Editor プラグイン＆CLI パイプライン（リアルタイム `GTAVVToon.asi` トゥーン描画＆`GTAVPhysBones.asi` 対応）**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Game: GTA V Legacy](https://img.shields.io/badge/Game-GTA%20V%20Legacy-2ea44f.svg)](docs/DEPLOYMENT_GUIDE.ja.md)
[![Unity Plugin: VRCAvatar2GTAV](https://img.shields.io/badge/Unity%20Plugin-Tools%20%E2%86%92%20VRCAvatar2GTAV-5865F2.svg)](docs/DEPLOYMENT_GUIDE.ja.md)
[![Blender: 4.0.2 + Sollumz v2.9.0](https://img.shields.io/badge/Blender-4.0.2%20%2B%20Sollumz%20v2.9.0-orange.svg)](https://docs.sollumz.org/)
[![rage--cli: 0.28.1](https://img.shields.io/badge/rage--cli-0.28.1-blue.svg)](https://github.com/VIRUXE/rage-cli)
[![i18n: EN | JA | PT](https://img.shields.io/badge/i18n-EN%20%7C%20JA%20%7C%20PT-lightgrey.svg)](docs/DEPLOYMENT_GUIDE.ja.md)

[English](README.md) · [Português (BR)](README.pt-BR.md) · **日本語**

📖 **[導入・技術ガイド全文 (`docs/DEPLOYMENT_GUIDE.ja.md`)](docs/DEPLOYMENT_GUIDE.ja.md)**

</div>

---

> [!IMPORTANT]
> **著作権およびアセット配布に関する注意**
>
> 本リポジトリには、BOOTH で販売・配布されている 3D アバター／衣装／ヘア／アイテクスチャ、Unity アセット、ならびに Rockstar Games / GTA V のバイナリファイルは**一切含まれていません**。`.fbx`、`.unity`、`.ydd`、`.ytd`、`.yft`、`.ymt`、`.rpf` などのアセットやローカル NPC 生成先 (`npcs/`)・端末固有設定 (`vrc2gtav.cfg`, `configs/npc_registry.json`, `configs/active_multi_slots.json`) はすべて [`.gitignore`](.gitignore)（および [`VRCAvatar2GTAV.unitypackage`](VRCAvatar2GTAV.unitypackage)）から除外されています。
>
> ご利用にあたっては、正当に入手したご自身の BOOTH アセットおよび **GTA V Legacy** 本体の環境を用意したうえで、**Unity Editor プラグイン** (`Tools > VRCAvatar2GTAV > Export Avatar to GTA V`) または対話型の **First-Run** ウィザードを実行してください。

---

## 概要

`vrcavatar2gtav` は、リグ付きの **VRChat (Unity / FBX)** アニメ系アバターを、**GTA V Legacy** のプレイアブル主人公（**マイケル・デ・サンタ `player_zero`**、**フランクリン・クリントン `player_one`**、**トレバー・フィリップス `player_two`**）および任意の **GTA V ストーリー/カットシーン NPC・街中歩行者** (`ig_*`、`cs_*`、`a_f_*`、`a_m_*` など — シーン内 GameObject / `.prefab` / `.unity` / `.zip` / `.unitypackage` から直接変換可能) として動作するように自動変換・導入するパイプラインです。

**Blender 4.0.2**・**Sollumz v2.9.0**・**`rage-cli` 0.28.1** の自動連携に加え、`unity-ui` ブランチでは **完結型 Unity Editor エクスポーター UI**（[`VRCAvatar2GTAV.unitypackage`](VRCAvatar2GTAV.unitypackage) / 主人公別タブ切り替え対応）、リアルタイム **D3D11 lilToon シェーダー ASI (`GTAVVToon.asi`)**、**32 Ped 対応 VRChat PhysBones (`GTAVPhysBones.asi`)**、`2048px` 単一ミップ `.ytd` ロック、**選択的 Restore Vanilla**、RPF7 `4.00 GiB` 容量予算制御を備えています。

### サンプル動画

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
        <img src="https://img.shields.io/badge/YouTube_Shorts-%E3%82%B5%E3%83%B3%E3%83%97%E3%83%AB%E5%8B%95%E7%94%BB%201-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="YouTube Shorts でサンプル動画 1 を見る">
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
        <img src="https://img.shields.io/badge/YouTube_Shorts-%E3%82%B5%E3%83%B3%E3%83%97%E3%83%AB%E5%8B%95%E7%94%BB%202-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="YouTube Shorts でサンプル動画 2 を見る">
      </a>
    </td>
  </tr>
</table>

</div>

### 主な機能

- **Unity Editor エクスポータープラグイン (`VRCAvatar2GTAV.unitypackage`)**: Unity メニュー `Tools > VRCAvatar2GTAV > Export Avatar to GTA V` から起動 ([`unity_plugin/Assets/VRCAvatar2GTAV/Editor/`](unity_plugin/Assets/VRCAvatar2GTAV/Editor/))。**共有モード**および**主人公別タブ切り替えマルチスロット (`PerProtagonistSlots`)**（`configs/active_multi_slots.json` + `--slots-json`）、ドラッグ＆ドロップ・シーン/アーカイブ選択、マテリアル単位の `_MainTex` 上書き、アトラス (`512`–`4096`)・法線 (`Auto`/`Off`/`256`–`1024`)・セカンダリ衣装解像度 (`Auto <3.7 GiB` / `512` / `1024` / `2048`) の RPF7 予測表示、**口の開き強度 (`0.70` 既定 + クイックリセットボタン)** とまばたき強度スライダー、顔 `.anim` 上書き (`--face-anim`)、GTA V ランタイム状態バッジ (`dinput8.dll`・`PhysBones.asi`・`VToon.asi`・`ScriptHookV.dll`・`OpenIV.asi` / RageOpenV)、**Auto / Windows Native / WSL** 実行モード切替、リサイズ可能な実行ログ、**バニラ復元ボタン**を提供します。
- **リアルタイム D3D11 lilToon シェーダー ASI (`GTAVVToon.asi`)**: [`scripts/vtoon_asi/`](scripts/vtoon_asi/gtav_vtoon.cpp) と [`scripts/common_tools/vtoon_profile_helper.py`](scripts/common_tools/vtoon_profile_helper.py) が lilToon `.mat`（`m_Parent` 継承含む）から UV 領域 LUT・MatCap 画像・`8×4` BC 境界整合ウォーターマーク（`char_id` `1..15`、主人公 ID `1..3`）を `GTAVVToon.ini` + `vtoon_profiles/` へ生成。`D3D11CreateDevice*`・`ID3D11Device`・即時/遅延 `ID3D11DeviceContext`・`ID3D11DeviceContext1`・オーバーレイ安全な `ScriptHookV` Present コールバックをフックし、Half-Lambert 2 段階トゥーン陰影、暖色 SSS 境界、リムライト、半透明前髪・眼鏡レンズ用フォワードパス (`kVToonForwardAlphaHlsl`)、GTA V のぼやけ肌パス回避、**`F10` ホットリロード**、SHA-256 ASI 同期チェックを実行します。
- **単一ミップ `2048px` `.ytd` 固定・無圧縮補助マップ・セカンダリ容量制御**: [`scripts/common_tools/universal_atlas_builder.py`](scripts/common_tools/universal_atlas_builder.py) が `--mips 1` で単一テクスチャ外部 `.ytd` を生成し、複数アバター登場カットシーン時のストリーミング解像度低下を防止します。法線/スペキュラは内蔵マテリアル向けの有効な `A8R8G8B8` DX9 DDS として安全に生成され、`--secondary-atlas-size`（`auto <3.7 GiB`、`512`、`1024`、`2048`）により `uppr_000` をフル 2K に保ったまま RPF7 `4.00 GiB` 上限内に収めます。
- **選択的バニラ復元 (`--restore-peds` / `--restore-all`)**: [`scripts/common_tools/restore_vanilla_helper.py`](scripts/common_tools/restore_vanilla_helper.py) が他キャラクター・NPC の Mod を壊さず対象 Ped のバニラファイルのみを Rockstar 元 RPF から復元し、`GTAVPhysBones.ini`・`GTAVVToon.ini`・`configs/npc_registry.json` の該当項目のみを削除します。
- **ネイティブ Modular Avatar (NDMF) ベイク & サブメッシュ順整合**: [`scripts/common_tools/modular_avatar_helper.py`](scripts/common_tools/modular_avatar_helper.py) と [`scripts/common_tools/build_universal_avatar.py`](scripts/common_tools/build_universal_avatar.py) が `MergeArmature`・`BoneProxy`・`ScaleAdjuster`・`MeshSettings`・`ObjectToggle`/`Activator`・`ReplaceObject`・`ShapeChanger`・`BlendshapeSync`・`m_Materials` 上書き・内蔵 `VRCPhysBone`・lilToon をそのままベイクし、透明レンズ/ガラスのアルファ維持および Unity `Mesh` サブメッシュ順へのマッピング (`map_blender_slots_to_unity_submeshes`) を保証します。
- **顔／体ブレンドシェイプ個別確認＋顔 `.anim` 保持**: `--import-face-blendshapes` / `--import-body-blendshapes` の個別制御、`--face-anim` 上書き、未指定／全ゼロ `.anim` 時の Unity シーン顔ブレンドシェイプ保持、`--mouth-open-strength` (`0.70` 既定 `FACIAL_jaw` 上限)、カスタム衣装含む全ゼロ `.cfg` 生成に対応。
- **First-Run・`.zip`/Unity 読込・Blender 4.0.2 / `rage-cli` 自動取得**: [`scripts/common_tools/avatar_archive_helper.py`](scripts/common_tools/avatar_archive_helper.py) が Zip-Slip 保護展開、Blender `4.0.2` + `Sollumz` (`--download-blender`) および `rage-cli` (`--download-rage`) 自動取得、**1 ページ 10 件＋`Next`/`Prev` ページ選択**を提供します。
- **汎用カスタムヘア・PhysBones・主人公間自由切替**: Z 帯アイランド分割付き `.prefab`/`PrefabVariant`/`.fbx` ヘア移植、`VRCPhysBone` 自動抽出（標準 `79` チェーン・`Advanced` `integrationType == 1` 親基準 `stiffness`・下髪/リボン展開・孤立ドレスチェーン自動除外・`<= 63` ボーン優先度パッカー・`--physbones-marshmallow` 任意）、および主人公スロット入替 (`[7]`, `--avatar`) に対応。
- **汎用 GTA V NPC・街中歩行者パイプライン**: [`scripts/common_tools/npc_registry_helper.py`](scripts/common_tools/npc_registry_helper.py) と [`scripts/common_tools/universal_gtav_builder.py`](scripts/common_tools/universal_gtav_builder.py) が `--npc` / `--all-npcs` / `--target-ped` 経由でストーリー/カットシーン NPC (`ig_*`, `cs_*`) や街中歩行者 (`a_f_*`, `a_m_*`) を直接変換し、最大 **32 Ped 同時追跡 (`kMaxTrackedPeds = 32`)** をサポートします。
- **GTA V 出血・傷デカール (`ped.sps` + 6 ゾーン `UVMap 1`) & 自然なまばたき**: [`scripts/common_tools/ped_damage_helper.py`](scripts/common_tools/ped_damage_helper.py)（`--blood-decals` 既定有効 / `--no-blood-decals`）および [`scripts/common_tools/eye_blink_helper.py`](scripts/common_tools/eye_blink_helper.py)（`--eye-blink` `auto` / `--eye-blink-strength` / `--no-eye-blink`）。
- **ログ・3 言語ローカライズ (`en`/`ja`/`pt`)・自動検証**: [`scripts/common_tools/error_handler_helper.py`](scripts/common_tools/error_handler_helper.py) による `logs/` 出力、[`scripts/common_tools/test_mod_suite.py`](scripts/common_tools/test_mod_suite.py) による **10** 項目のソース検証 (`--source-only`) と **13** 項目のフル検証スイートを収録。

---

## 対応主人公とアバター構成

初期設定では下記の組み合わせが割り当てられていますが、すべての VRChat アバタープリセットや Unity アバターを `michael` (`player_zero`)・`franklin` (`player_one`)・`trevor` (`player_two`) へ自由に割り当てられます:

| 既定 GTA V スロット | 主人公 | 既定 VRChat アバター (`avatar` ID) | 設定プリセット / 衣装 | 作業ディレクトリ |
| :--- | :--- | :--- | :--- | :--- |
| `player_zero` | **マイケル (Michael)** | **しなの (Shinano)** (`shinano_er`) | *エターナル・リユニオン*（ゴシックドレス＋懐中時計＋任意のカスタム Unity ヘアまたは *ねこタイドボブヘア*、未指定時はしなの標準ヘアへフォールバック） | [`2_Michael_Shinano_EternalReunion/`](2_Michael_Shinano_EternalReunion/) |
| `player_one` | **フランクリン (Franklin)** | **しなの (Shinano)** (`shinano_casual`) | *カジュアル / 制服*（赤スカート＋色変え標準しなのヘア、または任意のカスタム Unity ヘア） | [`1_Franklin_Shinano_Casual/`](1_Franklin_Shinano_Casual/) |
| `player_two` | **トレバー (Trevor)** | **ミルティナ (Miltina)** (`miltina_maid`) | *クラシックメイド*（白黒メイドドレス＋エプロン＋ツインテール＋任意のカスタム Unity ヘア） | [`3_Trevor_Miltina_Maid/`](3_Trevor_Miltina_Maid/) |

---

## 動作要件

- **Grand Theft Auto V (Legacy)** のローカル環境
- GTA V フォルダに **[Ultimate ASI Loader](https://github.com/ThirteenAG/Ultimate-ASI-Loader)** (`dinput8.dll`) + **[RageOpenV](https://github.com/Chiheb-Bacha/RageOpenV)**（または `OpenIV.asi`）を導入済みであること（`mods/` 読み込みに必要）
- **[ScriptHookV](https://www.dev-c.com/gtav/scripthookv/)** (`ScriptHookV.dll` — `GTAVVToon.asi` のフレーム/`F10` フックおよび `GTAVPhysBones.asi` の Ped 追跡に推奨)
- **[Blender 4.0.2](https://www.blender.org/)** + **[Sollumz v2.9.0](https://github.com/Sollumz/Sollumz)** *(未導入時は `--download-blender` または Unity UI のセットアップボタンで自動導入可能)*
- RPF7 再梱包用の **`rage-cli` `0.28.1`** ([GitHub](https://github.com/VIRUXE/rage-cli)) *(`--download-rage` または Unity UI で自動取得可能)*
- [`requirements.txt`](requirements.txt)（`numpy`, `Pillow`）を導入した **Python 3.10+** 環境
- *(GUI フロー利用時)* **Unity Editor 2022.3+**（VRChat Creator Companion プロジェクト）
- 正当に入手したご自身の **BOOTH アバター／衣装ファイル**

---

## クイックスタート

### 方法 A — Unity Editor プラグイン（Unity / VCC プロジェクト推奨）

1. [`VRCAvatar2GTAV.unitypackage`](VRCAvatar2GTAV.unitypackage) をダブルクリックして Unity プロジェクトへインポートするか、非破壊 CLI インストーラーを実行します:
   ```bash
   python unity_plugin/install_unity_plugin.py --unity-project "/path/to/MyUnityProject"
   ```
2. Unity 上部メニューから **`Tools > VRCAvatar2GTAV > Export Avatar to GTA V`** を開きます。
3. **共有モード**または**主人公別タブ (`Michael`, `Franklin`, `Trevor`)** を選び、シーンのアバターや `.prefab`/`.zip`/`.unitypackage` を指定して、解像度・口の開き（既定 `0.70`）・まばたきを調整し、ランタイム状態（不足ツールがあれば「ダウンロードと初期設定」）を確認のうえエクスポートを実行します。

### 方法 B — CLI & 対話型ターミナル

1. **リポジトリのクローンと Python 依存パッケージ導入**
   ```bash
   git clone https://github.com/TheOkamoto/vrcavatar2gtav.git
   cd vrcavatar2gtav
   pip install -r requirements.txt
   ```

2. **クリーン環境チェック** *(任意)*
   ```bash
   python scripts/common_tools/test_mod_suite.py --source-only
   ```

3. **First-Run セットアップを実行** — Windows では [`RUN_MANAGER.bat`](RUN_MANAGER.bat) を起動するか CLI を実行します:
   ```bash
   python run_mod_manager.py --setup
   ```
   変更を加えず確認だけ行う場合:
   ```bash
   python scripts/common_tools/setup_first_run.py --check-only
   ```

4. **全キャラクターのビルドと配置を実行**
   ```bash
   python run_mod_manager.py --character all
   ```

---

## 設定とフォールバック仕様

- **外部設定 (`vrc2gtav.cfg`) & バンドル Toolchain**: [`vrc2gtav.cfg.example`](vrc2gtav.cfg.example) を `vrc2gtav.cfg` へコピー（または `--setup` / Unity UI で生成）してパスを設定します。`.unitypackage` 版では `Vrc2GtavConfigDiscovery` が既定で `Assets/VRCAvatar2GTAV/Toolchain` を優先利用し、作業出力先を `<ProjectRoot>/VRCAvatar2GTAV_Work` へ分離します。
- **体格スケール (`1.0` 既定 + `.unity` 解析)**: 既定は `[1.0, 1.0, 1.0]`、`.unity` シーン指定時は `Transform` 階層からスケールを自動反映します。
- **ブレンドシェイプ (`Unity` & `configs/*_blendshapes.cfg`) & `.anim` 保持**: [`scripts/common_tools/blendshape_helper.py`](scripts/common_tools/blendshape_helper.py) が `.unity` / ネスト `.prefab` / `.anim` または `.cfg` プリセット (`blendshapes_source = auto | unity | cfg`) から解決します。`--face-anim` が空または全ゼロ値の場合は、シーン／プリセット側の顔ブレンドシェイプがそのまま保持されます。
- **PhysBones (`Unity` & `configs/*_physbones.cfg`)**: [`scripts/common_tools/physbone_helper.py`](scripts/common_tools/physbone_helper.py) が有効 `VRCPhysBone`（`PrefabInstance`・下髪/リボン展開・旧衣装の孤立チェーン除外含む）を `<= 63` カスタム / `<= 128` 合計ボーン内へ自動最適化パッキングします（既定 `79` チェーン / `182` ボーン、破棄 `0`；`--physbones-marshmallow` で `81` チェーン / `186` ボーン；超過カスタムアバターは `PHYSBONE_PRIORITY_TIERS` で重要部位を優先維持し残りを親ボーンへ固定バインド）。
- **汎用カスタムヘア & フォールバック**: `shinano_casual`・`shinano_er`・`miltina_maid` すべてで `custom_hair = auto | default | none | <パス>`（`[8]` / `--hair`）をサポートし、未指定時はしなの標準ヘア＋`ShinanoDefAdultNewv5.anim` またはミルティナ標準ツインテール＋`Miltina_close eyes_Base_adult.anim` へ安全にフォールバックします。
- **言語の自動判定**: OS ロケールから `en` / `ja` / `pt` を自動選択（`--lang en|ja|pt` で明示指定可能）。

---

## CLI コマンドと検証テスト

| コマンド | 用途 |
| :--- | :--- |
| `RUN_MANAGER.bat` / `EXECUTAR_GERENCIADOR.bat` | First-Run・ビルド・配置を行う Windows 対話メニュー |
| `python unity_plugin/install_unity_plugin.py --unity-project "/path/Project"` | Unity プロジェクトへ `Assets/VRCAvatar2GTAV/` を非破壊インストール |
| `python unity_plugin/build_unitypackage.py` | `Toolchain/` を同期して `VRCAvatar2GTAV.unitypackage` を再生成 |
| `python run_mod_manager.py --setup` | 対話型 First-Run ウィザードと `vrc2gtav.cfg` の設定 |
| `python run_mod_manager.py --setup --avatar-zip "/path/Shinano.zip" --download-blender --verbose` | `.zip`/`.unitypackage` 展開・Blender `4.0.2` + Sollumz 導入・10 件ページ選択・`.cfg` 生成・`logs/` ログ保存 |
| `python scripts/common_tools/build_universal_avatar.py --avatar-zip "/path/Shinano.zip" --interactive --verbose` | Modular Avatar 対応汎用アバタービルダー（10 件ページ選択・詳細ログ対応） |
| `python scripts/common_tools/universal_gtav_builder.py --slots-json "configs/active_multi_slots.json"` | 主人公別マルチスロットを連続ビルドし 1 回の RPF7 再パックで導入（`--secondary-atlas-size`・`--atlas-size`・`--mouth-open-strength`・`--face-anim`） |
| `python scripts/common_tools/universal_gtav_builder.py --restore-peds player_zero` | 他キャラクターを残したまま指定 Ped のみ Rockstar バニラへ復元（`--restore-all` で全復元） |
| `python run_mod_manager.py --check-env` / `setup_first_run.py --check-only` | GTA V・Blender・`rage-cli`・アセットパスの検証 |
| `python run_mod_manager.py --character {all,michael,franklin,trevor} --lang {en,ja,pt}` | Blender 再構築・YDD/YTD (`--mips 1`) 出力・ASI/VToon 同期・RPF7 配置を実行 |
| `python run_mod_manager.py --character franklin --avatar miltina_maid` | 任意の VRChat プリセット (`shinano_casual`, `shinano_er`, `miltina_maid`) を任意の主人公へ適用 (`--save-assignment`) |
| `python run_mod_manager.py --character michael --hair "/path/Hair.prefab" --save-hair` | `.prefab` / `PrefabVariant` / `.fbx` ヘア移植 (`--hair default` / `none` / `--hair-mat` / `--hair-tex` / `--hair-scale` / `--hair-offset`) |
| `python run_mod_manager.py --export-blendshapes` / `--blendshapes-source cfg` | `.unity` シーンから `.cfg` 出力、または `.cfg` プリセットを使用 |
| `python run_mod_manager.py --export-physbones` / `--physbones-source cfg` | VRCPhysBone の `.cfg` 同期 (`--physbones-marshmallow` / `--overwrite-physbones-from-unity`) |
| `python run_mod_manager.py --character all --blood-decals --eye-blink` | 出血デカール (`--no-blood-decals`)・まばたき (`--eye-blink-strength`, `--no-eye-blink`)・`--mouth-open-strength` (`0.70` 既定) の指定 |
| `python run_mod_manager.py --npc ig_lamardavis --avatar-zip "/path/Karin.zip"` | `.zip`/`.unitypackage`/Unity から任意の NPC (`ig_*`, `cs_*`) や街中歩行者 (`a_f_*`, `a_m_*`) を直接ビルド＆配置 (`--all-npcs` / `--target-ped ... --deploy-npc`) |
| `python run_mod_manager.py --deploy-only` | 既存ビルド・登録済み NPC・ASI プラグインを `mods/` へ再梱包・配置 |
| `python scripts/common_tools/test_mod_suite.py --source-only` | **10** 項目のソース/Unity/VToon/Restore/i18n/AST 検証を実行（クローン直後対応） |
| `python scripts/common_tools/test_mod_suite.py` | 全 **13** 項目の統合検証を実行（ビルド・配置済み環境が必要） |

---

## リポジトリ構成

```text
vrcavatar2gtav/
├── VRCAvatar2GTAV.unitypackage      # Unity Editor プラグイン + バンドル Toolchain (.gitignore 対象 / build_unitypackage.py で生成)
├── unity_plugin/
│   ├── Assets/VRCAvatar2GTAV/
│   │   ├── Editor/                  # Unity Editor UI 用 C# スクリプト 9 本 (VRCAvatar2GTAV.Editor.asmdef)
│   │   └── Toolchain/               # クリーンな自動化スクリプト＆ドキュメントのステージングミラー
│   ├── build_unitypackage.py        # 完結型 .unitypackage ビルダー
│   └── install_unity_plugin.py      # 既存 Unity プロジェクトへの非破壊インストーラー
├── configs/                         # ブレンドシェイプ (*_blendshapes.cfg)・PhysBones (*_physbones.cfg)・npc_registry.json・active_multi_slots.json (.gitignore)
├── npcs/                            # 汎用 NPC / 街中歩行者のローカル作業フォルダ・出力 (.gitignore)
├── docs/
│   ├── DEPLOYMENT_GUIDE.md          # 技術・導入ガイド全文 (EN)
│   ├── DEPLOYMENT_GUIDE.pt-BR.md    # 技術・導入ガイド全文 (PT-BR)
│   └── DEPLOYMENT_GUIDE.ja.md       # 内部設計・Unity UI・VToon・Sollumz・RPF7 技術ガイド (JA)
├── scripts/
│   ├── common_tools/                # First-Run、.unity/ヘア/ブレンドシェイプ/PhysBones/VToon/Restore/NPC 解析、i18n、test_mod_suite.py
│   ├── physbones_asi/               # リアルタイム VRChat PhysBones ASI プラグイン (GTAVPhysBones.asi / .ini)
│   ├── vtoon_asi/                   # リアルタイム D3D11 lilToon シェーダー ASI (GTAVVToon.asi / .ini / vtoon_profiles)
│   ├── Shinano_Casual_Franklin/     # フランクリン (player_one) ビルドスクリプト
│   ├── Shinano_EternalReunion_Michael/ # マイケル (player_zero) ビルドスクリプト
│   └── Miltina_Maid_Trevor/         # トレバー (player_two) ビルドスクリプト
├── _deploy_tools/                   # 汎用ダミースロット (head_000_r.ydd, p_eyes_dummy.ydd) および実行ヘルパー
├── 1_Franklin_Shinano_Casual/       # player_one 出力ステージングフォルダ
├── 2_Michael_Shinano_EternalReunion/# player_zero 出力ステージングフォルダ
├── 3_Trevor_Miltina_Maid/           # player_two 出力ステージングフォルダ
├── requirements.txt                 # Python 3.10+ 依存パッケージ (numpy, Pillow)
├── run_mod_manager.py               # メイン CLI / 対話型オーケストレーター
├── setup_first_run.py               # First-Run セットアップエントリポイント
├── RUN_MANAGER.bat                  # Windows 対話メニュー (EN/JA/PT)
├── EXECUTAR_GERENCIADOR.bat         # Windows 対話メニュー（PT-BR 向けショートカット）
├── vrc2gtav.cfg.example             # 外部パス設定のサンプルファイル
└── LICENSE                          # MIT ライセンス
```

スケルトンボーンの軸合わせ、手指の握り補正、リップシンク合成（既定 `0.70`）、`GTAVVToon.asi` HLSL トゥーン描画、単一ミップ `.ytd`、`VRCAvatar2GTAV.unitypackage` の操作画面、選択的バニラ復元、RPF7 `4.00 GiB` 容量ガードの詳細は **[導入・技術ガイド (`docs/DEPLOYMENT_GUIDE.ja.md`)](docs/DEPLOYMENT_GUIDE.ja.md)** をご覧ください。

---

## クレジット — アセットおよびツール一覧

本プロジェクトで使用するすべての 3D モデル、衣装、ヘア、アイテクスチャ、Unity パッケージおよび外部ツールの著作権・知的財産権は、各制作者に帰属します。

### 3D アバター・衣装・ヘア・アイテクスチャ (BOOTH)

| 対象主人公 | カテゴリ | アセット名 | 制作者 / ショップ | BOOTH リンク |
| :--- | :--- | :--- | :--- | :--- |
| マイケル, フランクリン | 素体アバター & カジュアル衣装 *(必須)* | **オリジナル3Dモデル「しなの」 (*Shinano*)** | ポンデロニウム研究所 (`ponderogen`) | [Item #6106863](https://ponderogen.booth.pm/items/6106863) · [ショップ](https://ponderogen.booth.pm/) |
| トレバー | 素体アバター & メイド衣装 *(必須)* | **オリジナル3Dモデル『ミルティナ』 (*Milltina*)** | DOLOS art (`dolosart`) | [Item #6538026](https://dolosart.booth.pm/items/6538026) · [ショップ](https://dolosart.booth.pm/) |
| マイケル | ドレス・靴・小物 *(マイケル用・必須)* | **【15アバター対応】エターナル・リユニオン【MA対応】 (*Eternal Reunion* + *Pocket Watch*)** | VAGRANT (`Vagrant Brand`) | [Item #5634313](https://vagrant.booth.pm/items/5634313) · [ショップ](https://vagrant.booth.pm/) |
| マイケル | ヘア・猫耳・ヘアピン・ヘイロー *(任意 — 未導入時は標準ヘアへフォールバック)* | **ねこタイドボブヘア (*Neko Tied Bob hair*)** | Li-ne (`Li-ne_Shop`) | [Item #7977491](https://li-ne.booth.pm/items/7977491) · [ショップ](https://li-ne.booth.pm/) |
| マイケル, フランクリン | アイテクスチャ *(任意)* | **`[eye17アバター対応]MoonButterfly eye & Rurune Make`** | ha-oa | [Item #8483652](https://ha-oa.booth.pm/items/8483652) · [ショップ](https://ha-oa.booth.pm/) |
| トレバー | アイテクスチャ *(任意)* | **お魚が泳ぐ あわあわ水光 Eye Texture【10Color】【23Avatar】 (`Milltina_AWEyes`)** | NAGIMA (`nagikawamart`) | [Item #6837271](https://nagikawamart.booth.pm/items/6837271) · [ショップ](https://nagikawamart.booth.pm/) |

<details>
<summary>キャラクター別メッシュ・小物・FaceEmo プリセット内訳</summary>

- **マイケル・デ・サンタ (`player_zero`) — しなの (*Eternal Reunion*)**
  - **素体**: `Body`, `Body_base` (*Shinano*)
  - **衣装**: `UN1_Shirt`, `UN1_Skirt`, `UN2_Corset`, `UN2_Stocking`, `UN2_Shoes` (*Eternal Reunion*)
  - **小物**: `UN1_ChestRibbon`, `UN1_Choker`, `UN3_Bag`, `UN3_Glasses`, `UN3_WaistChain`, `Pocket Watch` (*Eternal Reunion*、`UN2_Beret` は無効化)
  - **ヘア *(任意)***: `Bangs`, `Top Back`, `Under Side`, `Back`, `Side Bangs`, `Side`, `In Hair`, `Ears`, `Ribbon`, `_Pin.Back`, `_Pin.R`, `_Pin.L2`, `_Halo` (*Neko Tied Bob hair*、未指定時はしなの標準ヘアへフォールバック)
  - **アイテクスチャ & 表情 *(任意 / フォールバック)***: `MoonButterfly eye` & `ShinanoDefAdultNewv5.anim`

- **フランクリン・クリントン (`player_one`) — しなの (*Casual / Uniform*)**
  - **素体**: `Body`, `Body_base` (*Shinano*)
  - **衣装**: `Cloth_sweater`, `Cloth_skirt`, `Cloth_tights`, `Cloth_boots` (*Shinano*)
  - **ヘア**: `Hair_back`, `Hair_bang`, `Hair_base`, `Hair_side`, `Other_ear`, `Other_tail` (*Shinano* 標準ヘア、ケモ耳を維持したまま任意の `custom_hair` 上書きにも対応)
  - **アイテクスチャ & 表情 *(任意 / フォールバック)***: `MoonButterfly eye` & `ShinanoDefAdultNewv5.anim`

- **トレバー・フィリップス (`player_two`) — ミルティナ (*Classic Maid*)**
  - **素体**: `Body`, `Milltina_body` (*Milltina*)
  - **衣装 & 小物**: `Milltina_cloth_dress`, `Milltina_cloth_apron`, `Milltina_cloth_skirt`, `Milltina_cloth_panties`, `Milltina_cloth_collar`, `Milltina_cloth_hat`, `Milltina_cloth_neck_ribbon`, `Milltina_cloth_wrist_cuffs`, `Milltina_cloth_garterbelt`, `Milltina_cloth_hair_ribbon`, `Milltina_cloth_tail_ribbon`, `Milltina_cloth_tail_slit`, `Milltina_cloth_shoes` (*Milltina*)
  - **ヘア & 牛パーツ**: `Milltina_hair_base`, `Milltina_hair_side`, `Milltina_hair_front`, `Milltina_hair_front_side`, `Milltina_hair_twintail`, `Milltina_cow_ears`, `Milltina_cow_horns`, `Milltina_cow_tail` (*Milltina*、任意のカスタム `custom_hair` / `fbx_hair` 上書きにも対応)
  - **アイテクスチャ & 表情 *(任意 / フォールバック)***: `Milltina_AWEyes` & `Miltina_close eyes_Base_adult.anim`

</details>

### Unity パッケージ & GTA V / Blender ツール

| ツール / パッケージ | バージョン | 作者 | リンク |
| :--- | :--- | :--- | :--- |
| **lilToon** | `v2.4.1` | `lilxyzw` | [GitHub](https://github.com/lilxyzw/lilToon) · [公式サイト](https://lilxyzw.github.io/lilToon/) |
| **FaceEmo** | `v1.7.0` | `suzuryg` | [GitHub](https://github.com/suzuryg/face-emo) · [公式サイト](https://suzuryg.github.io/face-emo/) |
| **Modular Avatar** | `v1.18.7` | `bd_` (Nadena) | [GitHub](https://github.com/bdunderscore/modular-avatar) · [公式サイト](https://modular-avatar.nadena.dev/) |
| **Blender** | `4.0.2` | Blender Foundation | [公式サイト](https://www.blender.org/) |
| **Sollumz** | `v2.9.0` | `Skylumz`, `Colton`, `alexguirre` | [GitHub](https://github.com/Sollumz/Sollumz) · [ドキュメント](https://docs.sollumz.org/) |
| **rage-cli** | `0.28.1` | `VIRUXE` | [GitHub](https://github.com/VIRUXE/rage-cli) |
| **RageOpenV** | — | `Chiheb-Bacha` | [GitHub](https://github.com/Chiheb-Bacha/RageOpenV) |
| **ScriptHookV** | — | `Alexander Blade` | [公式サイト](https://www.dev-c.com/gtav/scripthookv/) |
| **Ultimate ASI Loader** | — | `ThirteenAG` | [GitHub](https://github.com/ThirteenAG/Ultimate-ASI-Loader) |

---

## ライセンス

本プロジェクトの自動化スクリプトおよびドキュメントは **MIT License** のもとで公開されています（詳細は [`LICENSE`](LICENSE) / `Copyright (c) 2026 TheOkamoto` を参照）。上記クレジットに記載されたサードパーティ製アセット・ツールの権利および利用規約は各配布元の定めに従います。
