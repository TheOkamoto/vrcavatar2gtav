<div align="center">

# `vrcavatar2gtav`

**VRChat 向け Unity/FBX アバターを GTA V Legacy のプレイヤーキャラクターへ自動変換・導入するパイプライン**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Game: GTA V Legacy](https://img.shields.io/badge/Game-GTA%20V%20Legacy-2ea44f.svg)](docs/DEPLOYMENT_GUIDE.ja.md)
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
> 本リポジトリには、BOOTH で販売・配布されている 3D アバター／衣装／ヘア／アイテクスチャ、Unity パッケージ、ならびに Rockstar Games / GTA V のバイナリファイルは**一切含まれていません**。`.fbx`、`.unity`、`.ydd`、`.ytd`、`.yft`、`.ymt`、`.rpf` などのアセット類はすべて [`.gitignore`](.gitignore) によって除外されています。
>
> ご利用にあたっては、正当に入手したご自身の BOOTH アセットおよび **GTA V Legacy** 本体の環境を用意したうえで、対話型の **First-Run** セットアップウィザードを実行してください。

---

## 概要

`vrcavatar2gtav` は、リグ付きの **VRChat (Unity / FBX)** アニメ系アバターを、**GTA V Legacy** のプレイアブル主人公（**マイケル・デ・サンタ `player_zero`**、**フランクリン・クリントン `player_one`**、**トレバー・フィリップス `player_two`**）として動作するように自動変換・導入するパイプラインです。

手作業でのボーン微調整に頼らず、**Blender 4.0.2**、**Sollumz v2.9.0**、**`rage-cli` 0.28.1** を一連の工程として連携させ、スケルトンリマップ、手指の握り補正、リップシンク用モーフ調整、テクスチャ・マテリアル補正、標準スケール `1.0` の適用（および `.unity` シーンからのスケール抽出）、ユニバーサルスロット梱包、RPF7 (`mods/x64v.rpf`) への安全配置までを自動化します。

### サンプル動画

<div align="center">

<a href="https://youtube.com/shorts/xoaqZa0GhC8?is=Y_0Z3Nd31neOgCFI">
  <img src="https://img.youtube.com/vi/xoaqZa0GhC8/maxresdefault.jpg" width="640" alt="vrcavatar2gtav サンプル動画 (YouTube Shorts)">
</a>

<br>

[![YouTube Shorts で視聴](https://img.shields.io/badge/YouTube_Shorts-%E3%82%B5%E3%83%B3%E3%83%97%E3%83%AB%E5%8B%95%E7%94%BB%E3%82%92%E8%A6%8B%E3%82%8B-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://youtube.com/shorts/xoaqZa0GhC8?is=Y_0Z3Nd31neOgCFI)

</div>

### 主な機能

- **First-Run・`.zip`/Unity 読込 & Blender 4.0.2 自動取得**: `--avatar-zip` (`.zip` / `.unitypackage`) または `--unity-project` を渡すだけで、VRChat だけの新しい Unity プロジェクトからも開始可能。[`scripts/common_tools/avatar_archive_helper.py`](scripts/common_tools/avatar_archive_helper.py) が安全に展開し、Blender `4.0.2` + `Sollumz` が未導入なら自動ダウンロードし、**1ページ10件＋`Next`/`Prev` ページング選択メニュー**でアバターを選べます。
- **ネイティブ Modular Avatar (NDMF) ベイクエンジン**: [`scripts/common_tools/modular_avatar_helper.py`](scripts/common_tools/modular_avatar_helper.py) と [`scripts/common_tools/build_universal_avatar.py`](scripts/common_tools/build_universal_avatar.py) が、`ModularAvatarMergeArmature`・`BoneProxy`・`ScaleAdjuster`・`MeshSettings`・`ObjectToggle`/`Activator`・`ReplaceObject`・`ShapeChanger`・`BlendshapeSync`・内蔵 `VRCPhysBone`・lilToon マテリアルを含む衣装やドレスを任意の主人公 (`michael`/`franklin`/`trevor`) へそのままベイクします。
- **顔／体ブレンドシェイプ個別確認＋カスタム衣装含む全ゼロ `.cfg` 生成**: 顔 (`--import-face-blendshapes`) と体 (`--import-body-blendshapes`) を個別に確認し、「Yes」なら Unity から抽出、「No」ならアバター FBX およびカスタム衣装 FBX を含むすべてのシェイプキーを `0.0` で初期化した `.cfg` を出力します。
- **専用エラーハンドラ＆ `--verbose` 日時ログ**: [`scripts/common_tools/error_handler_helper.py`](scripts/common_tools/error_handler_helper.py) により、通常時は簡潔に出力し、`--verbose` 指定時は詳細出力と同時に `logs/` へ日時・アバター名付きログを保存します。
- **3言語対応 (`en` / `ja` / `pt`)**: OS のロケール自動判定と `--lang` 指定。
- **スケール `1.0` 標準 + `.unity` シーン抽出**・**汎用カスタムヘア移植**・**標準 VRCPhysBone 自動抽出**・**アバター <-> 主人公の完全な相互切替**。
- **GTA V 出血・傷デカール対応 (`ped.sps` + 6ゾーン `UVMap 1`)**: [`scripts/common_tools/ped_damage_helper.py`](scripts/common_tools/ped_damage_helper.py) により胴体/スカート・頭部・両腕・両脚へ銃痕や出血表現（`--blood-decals`、既定で有効）を正しく投影し、尻尾や首より下のロングヘアへの誤投影を防ぎます。
- **自動検証テストスイート**: ソース検証 (`8` スイート) およびフル検証 (`11` スイート)。

---

## 対応主人公とアバター構成

初期設定では下記の組み合わせが割り当てられていますが、すべての VRChat アバタープリセットを `michael`・`franklin`・`trevor` のどの主人公スロットへも自由に割り当てられます:

| 既定 GTA V スロット | 主人公 | 既定 VRChat アバター (`avatar` ID) | 設定プリセット / 衣装 | 作業ディレクトリ |
| :--- | :--- | :--- | :--- | :--- |
| `player_zero` | **マイケル (Michael)** | **しなの (Shinano)** (`shinano_er`) | *エターナル・リユニオン*（ゴシックドレス＋懐中時計＋任意のカスタム Unity ヘアまたは *ねこタイドボブヘア*、未指定時はしなの標準ヘアへフォールバック） | [`2_Michael_Shinano_EternalReunion/`](2_Michael_Shinano_EternalReunion/) |
| `player_one` | **フランクリン (Franklin)** | **しなの (Shinano)** (`shinano_casual`) | *カジュアル / 制服*（赤スカート＋色変え標準しなのヘア、または任意のカスタム Unity ヘア） | [`1_Franklin_Shinano_Casual/`](1_Franklin_Shinano_Casual/) |
| `player_two` | **トレバー (Trevor)** | **ミルティナ (Miltina)** (`miltina_maid`) | *クラシックメイド*（白黒メイドドレス＋エプロン＋ツインテール＋任意のカスタム Unity ヘア） | [`3_Trevor_Miltina_Maid/`](3_Trevor_Miltina_Maid/) |

---

## 動作要件

- **Grand Theft Auto V (Legacy)** のローカル環境
- GTA V フォルダに **[Ultimate ASI Loader](https://github.com/ThirteenAG/Ultimate-ASI-Loader)** + **[RageOpenV](https://github.com/Chiheb-Bacha/RageOpenV)** を導入済みであること（`mods/` フォルダ読み込みに必要）
- **[Blender 4.0.2](https://www.blender.org/)** + **[Sollumz v2.9.0](https://github.com/Sollumz/Sollumz)**
- RPF7 再梱包用の **`rage-cli` `0.28.1`** ([GitHub](https://github.com/VIRUXE/rage-cli))
- [`run_mod_manager.py`](run_mod_manager.py) およびテストスイートを実行できる **Python** 環境
- 正当に入手したご自身の **BOOTH アバター／衣装ファイル**（カスタム調整を引き継ぐ場合は Unity プロジェクト / `.unity` ファイルも可）

---

## クイックスタート

1. **リポジトリをクローン**
   ```bash
   git clone https://github.com/TheOkamoto/vrcavatar2gtav.git
   cd vrcavatar2gtav
   ```

2. **クリーン環境チェック** *(任意)*
   ```bash
   python scripts/common_tools/test_mod_suite.py --source-only
   ```

3. **First-Run セットアップを実行**
   Windows では [`RUN_MANAGER.bat`](RUN_MANAGER.bat) を起動するか、CLI から直接ウィザードを実行します：
   ```bash
   python run_mod_manager.py --setup
   ```
   GTA V Legacy フォルダ、Blender `4.0.2`、`rage-cli`、元アセットの配置状況を確認し、[`vrc2gtav.cfg.example`](vrc2gtav.cfg.example) をもとに `.gitignore` 対象の `vrc2gtav.cfg` を作成できます。変更を加えずに事前確認だけ行う場合は次を実行します：
   ```bash
   python scripts/common_tools/setup_first_run.py --check-only
   ```

4. **全キャラクターのビルドと配置を実行**
   ```bash
   python run_mod_manager.py --character all
   ```

---

## 設定とフォールバック仕様

- **外部設定 (`vrc2gtav.cfg`)**: [`vrc2gtav.cfg.example`](vrc2gtav.cfg.example) を `vrc2gtav.cfg` としてコピー（または `--setup` で生成）することで、コードを編集せずに GTA V Legacy、Blender、`rage-cli`、およびローカル FBX/Unity アセットへのパスを指定できます。
- **体格スケール (`1.0` 既定 + `.unity` 解析)**: 体格スケールは既定で `[1.0, 1.0, 1.0]` に設定されています。`.unity` シーンファイルを指定すると、`Transform` 階層のスケール値を自動抽出してビルドへ反映します。
- **ブレンドシェイプ設定 (`Unity` & `configs/*_blendshapes.cfg`)**: 顔・素体シュリンク・衣装・小物・ヘアのすべてのブレンドシェイプを [`scripts/common_tools/blendshape_helper.py`](scripts/common_tools/blendshape_helper.py) 経由で解決します。Unity プロジェクト（`.unity` + ネスト `.prefab` + `.anim`）からの自動取得、または [`configs/`](configs/) 配下の `.cfg` プリセット（`shinano_blendshapes.cfg` / `shinano_er_blendshapes.cfg` / `miltina_blendshapes.cfg`）を `blendshapes_source = auto | unity | cfg` と `blendshapes_cfg` で切り替えられます。
- **VRChat PhysBones 自動インポーター & 優先度パッカー (`Unity` & `configs/*_physbones.cfg`)**: [`scripts/common_tools/physbone_helper.py`](scripts/common_tools/physbone_helper.py) が有効な標準 `VRCPhysBone`（`PrefabInstance` 上書きを含む）を自動抽出し、RAGE `.ydd` のカスタム `<= 63`（合計 `<= 128`）ボーン上限内に ELF ハッシュ衝突 `0` で最適化パッキングしてポータブル `.cfg` へ読み書きします（`michael_neko_mimi_physbones.cfg`: `30` チェーン / `62` ボーン、`shinano_casual_physbones.cfg`: `24` チェーン / `62` ボーン、`miltina_maid_physbones.cfg`: `25` チェーン / `58` ボーン、計 `79` チェーン / `182` カスタムボーン — **すべて RAGE 上限内のため破棄 0**）。任意の `marshmallow_PB` プリセットは既定で無効化されており、必要な場合のみ `physbones_marshmallow = true` または `--physbones-marshmallow` で有効化できます（計 `81` チェーン / `186` ボーン）。**カスタムアバター**が `63` カスタムボーンを超過する場合は、`PHYSBONE_PRIORITY_TIERS` が **Tier 1〜3 必須部位**（ケモ耳・前髪/横髪/後ろ髪・ツインテール・尻尾・翼・スカート・コート・スカーフ・袖・主要胸部）→ **Tier 4**（リボン・フリル・ベール）→ **Tier 5〜7 非必須小物**（ベルト・ストラップ・頬・イヤリング・ヘアピン・キーホルダー・バッグ・ポーチ・ぬいぐるみ・懐中時計・バッジ）の順で優先度判定し、上限内のアバターは **100%** 保持、超過分のみ左右対称を保ちつつ非必須チェーンから除外して元の剛体親ボーン (`SKEL_Head`・`SKEL_Pelvis` 等) へ安全に固定バインドします。さらにインポート時には `extract_unity_scene_physbones` と `prune_orphaned_physbone_chains` が**旧衣装の孤立 PhysBone**（無効化・`EditorOnly`・`m_RemovedGameObjects`/`m_RemovedComponents`・Modular Avatar 非表示・FBX ウェイトゼロの削除済み衣装メッシュや参照切れ/非アクティブな `rootTransform`）を自動検出して除外し、RAGE 枠の無駄遣いを防ぎます。`physbones_source = auto | unity | cfg`、`physbones_cfg`、`--physbones-marshmallow`、対話メニュー `[10]` で制御できます。
- **汎用カスタムヘア & フォールバック仕様**:
  - **全アバタープリセット対応**: `shinano_casual`・`shinano_er`・`miltina_maid` すべてで、`vrc2gtav.cfg` (`custom_hair = auto | default | none | <.prefab または .fbx パス>` および `hair_mat`, `hair_tex`, `hair_scale`, `hair_offset`)、対話メニュー `[8]`、または CLI の `--hair` フラグを利用できます。[`scripts/common_tools/unity_hair_helper.py`](scripts/common_tools/unity_hair_helper.py) が `PrefabVariant` 継承、Modular Avatar 構造、`.fbx.meta` のマテリアル対応表、lilToon テクスチャ/色調補正を `custom_hair_manifest.json` へベイクし、[`scripts/common_tools/blender_hair_helper.py`](scripts/common_tools/blender_hair_helper.py) が頭部位置合わせ・UV リマップ・元ケモ耳保持を行います。
  - **しなの**: `custom_hair` / *ねこタイドボブヘア* がある場合はそちらを使用し、無い場合は自動的に標準ヘア（`Hair_base`、`Hair_bang`、`Hair_side`、`Hair_back`、`Other_ear`、`Other_tail`）および `ShinanoDefAdultNewv5.anim` / 標準アイテクスチャを使用します。
  - **ミルティナ**: 任意の `custom_hair`（または従来の `fbx_hair`）上書きに対応し、未指定時は標準ツインテール（`Milltina_hair_*`）および `Miltina_close eyes_Base_adult.anim` / 標準アイテクスチャを使用します。
- **言語の自動判定**: システムロケールに応じて `en` / `ja` / `pt` を自動選択し、`--lang en|ja|pt` での明示指定も可能です。

---

## CLI コマンドと検証テスト

| コマンド | 用途 |
| :--- | :--- |
| `RUN_MANAGER.bat` / `EXECUTAR_GERENCIADOR.bat` | First-Run・ビルド・配置を行う Windows 対話メニュー |
| `python run_mod_manager.py --setup` | 対話型 First-Run ウィザードと `vrc2gtav.cfg` の設定 |
| `python run_mod_manager.py --setup --avatar-zip "/path/Shinano.zip" --download-blender --verbose` | `.zip`/`.unitypackage` 展開・Blender `4.0.2` + Sollumz 自動導入・10件+`Next` 選択・MA/顔体 `.cfg` 生成・`logs/` ログ記録 |
| `python scripts/common_tools/build_universal_avatar.py --avatar-zip "/path/Shinano.zip" --interactive --verbose` | Modular Avatar 対応汎用アバター・衣装ビルダー（10件ページ選択・顔/体個別質問・詳細ログ対応） |
| `python run_mod_manager.py --check-env` | GTA V・Blender・`rage-cli`・アセットパスの検証 |
| `python scripts/common_tools/setup_first_run.py --check-only` | 環境と元アセットの有無を非破壊チェック |
| `python run_mod_manager.py --character all` | 3人分の Blender 再構築・YDD/YTD 出力・RPF7 配置を一括実行 |
| `python run_mod_manager.py --character {michael,franklin,trevor} --lang {en,ja,pt}` | 指定キャラクターのみを指定言語の UI でビルド／配置 |
| `python run_mod_manager.py --character franklin --avatar miltina_maid` | 任意の VRChat プリセット (`shinano_casual`, `shinano_er`, `miltina_maid`) を任意の主人公へビルド／適用 (`--save-assignment` で `vrc2gtav.cfg` に保存) |
| `python run_mod_manager.py --character michael --hair "/path/Hair.prefab" --save-hair` | 任意の Unity `.prefab` / `PrefabVariant` / `.fbx` ヘアを主人公へ自動移植 (`--hair default` / `none` / `--hair-mat` / `--hair-tex` / `--hair-scale` / `--hair-offset` 対応) |
| `python run_mod_manager.py --export-blendshapes` | 設定済みの `.unity` シーンから `configs/*_blendshapes.cfg` へ書き出す |
| `python run_mod_manager.py --character all --blendshapes-source cfg` | Unity シーンではなく `.cfg` プリセットを使ってビルドを実行 |
| `python run_mod_manager.py --export-physbones` | `.unity` シーンから標準 VRCPhysBone を `configs/*_physbones.cfg` へ自動同期（`--physbones-marshmallow` で Marshmallow PB 含める、`--overwrite-physbones-from-unity` で上書き） |
| `python run_mod_manager.py --character all --physbones-source cfg` | Unity シーンではなく `.cfg` プリセットの PhysBone 設定を使ってビルド（`--physbones-marshmallow` で Marshmallow PB 有効化可能） |
| `python run_mod_manager.py --character all --blood-decals` | GTA V の出血・傷デカール有効でビルド（既定；`--no-blood-decals` で従来の `ped_default.sps` に切替可能） |
| `python run_mod_manager.py --deploy-only` | 既存ビルド済みフォルダから `mods/x64v.rpf` へ再梱包・配置 |
| `python scripts/common_tools/test_mod_suite.py --source-only` | ソース・設定・i18n・First-Run・Modular Avatar の `8` スイートを実行（クローン直後対応） |
| `python scripts/common_tools/test_mod_suite.py` | 全 `11` スイートの統合検証を実行（ビルド・配置済み環境が必要） |

---

## リポジトリ構成

```text
vrcavatar2gtav/
├── configs/                         # ブレンドシェイプ設定 (*_blendshapes.cfg) および PhysBones (*_physbones.cfg)
├── docs/
│   ├── DEPLOYMENT_GUIDE.md          # 技術・導入ガイド全文 (EN)
│   ├── DEPLOYMENT_GUIDE.pt-BR.md    # 技術・導入ガイド全文 (PT-BR)
│   └── DEPLOYMENT_GUIDE.ja.md       # 内部設計・リギング・Sollumz・RPF7 技術ガイド (JA)
├── scripts/
│   ├── common_tools/                # First-Run、.unity/ヘア/ブレンドシェイプ/PhysBones 解析、i18n、test_mod_suite.py
│   ├── physbones_asi/               # リアルタイム VRChat PhysBones ASI プラグイン (GTAVPhysBones.asi / .ini)
│   ├── Shinano_Casual_Franklin/     # フランクリン (player_one) ビルドスクリプト
│   ├── Shinano_EternalReunion_Michael/ # マイケル (player_zero) ビルドスクリプト
│   └── Miltina_Maid_Trevor/         # トレバー (player_two) ビルドスクリプト
├── _deploy_tools/                   # 汎用ダミースロット (head_000_r.ydd, p_eyes_dummy.ydd) および実行ヘルパー
├── 1_Franklin_Shinano_Casual/       # player_one 出力ステージングフォルダ
├── 2_Michael_Shinano_EternalReunion/# player_zero 出力ステージングフォルダ
├── 3_Trevor_Miltina_Maid/           # player_two 出力ステージングフォルダ
├── run_mod_manager.py               # メイン CLI / 対話型オーケストレーター
├── RUN_MANAGER.bat                  # Windows 対話メニュー (EN/JA/PT)
├── EXECUTAR_GERENCIADOR.bat         # Windows 対話メニュー（PT-BR 向けショートカット）
├── vrc2gtav.cfg.example             # 外部パス設定のサンプルファイル
└── LICENSE                          # MIT ライセンス
```

スケルトンボーンの軸合わせ、手指の握り補正、リップシンク合成、テクスチャの JOAAT ハッシュ計算、`Sollumz` シェーダー設定、`ERR_GEN_ZLIB_2` を防ぐユニバーサルダミー置換、手動ステップ手順などの詳細は **[導入・技術ガイド (`docs/DEPLOYMENT_GUIDE.ja.md`)](docs/DEPLOYMENT_GUIDE.ja.md)** をご覧ください。

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
| **Ultimate ASI Loader** | — | `ThirteenAG` | [GitHub](https://github.com/ThirteenAG/Ultimate-ASI-Loader) |

---

## ライセンス

本プロジェクトの自動化スクリプトおよびドキュメントは **MIT License** のもとで公開されています（詳細は [`LICENSE`](LICENSE) / `Copyright (c) 2026 TheOkamoto` を参照）。上記クレジットに記載されたサードパーティ製アセット・ツールの権利および利用規約は各配布元の定めに従います。
