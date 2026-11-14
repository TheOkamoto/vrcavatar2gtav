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

### 主な機能

- **First-Run セットアップ & 外部設定ファイル**: 対話型ウィザードと [`vrc2gtav.cfg`](vrc2gtav.cfg.example) により、ローカルパス設定を Git 管理外へ分離。
- **3言語対応 (`en` / `ja` / `pt`)**: OS のロケールを自動判定し、`--lang` オプションでマネージャー・セットアップ・テスト出力を切り替え可能。
- **スケール `1.0` 標準 + `.unity` シーン抽出**: GitHub 版の既定値として全身スケール `1.0` を採用しつつ、`.unity` シーンファイルが指定された場合は階層内のカスタムスケールを自動読み取り・反映。
- **デフォルトヘア・表情への自動フォールバック**: 任意の BOOTH ヘア（*Neko Tied Bob Hair* / カスタム `fbx_hair`）や任意のアイテクスチャが存在しない場合、各素体アバターの標準ヘア・標準表情／瞳テクスチャへ自動でフォールバック。
- **自動検証テストスイート**: クリーンなクローン環境で実行できるソース検証 (`5` スイート) と、ビルド・配置後に行うフル検証 (`8` スイート) を搭載。

---

## 対応主人公とアバター構成

| GTA V スロット | 主人公 | VRChat アバター | 設定プリセット / 衣装 | 作業ディレクトリ |
| :--- | :--- | :--- | :--- | :--- |
| `player_zero` | **マイケル (Michael)** | **しなの (Shinano)** | *エターナル・リユニオン*（ゴシックドレス＋懐中時計＋任意の *ねこタイドボブヘア*、未指定時はしなの標準ヘアへフォールバック） | [`2_Michael_Shinano_EternalReunion/`](2_Michael_Shinano_EternalReunion/) |
| `player_one` | **フランクリン (Franklin)** | **しなの (Shinano)** | *カジュアル / 制服*（赤スカート＋色変え標準しなのヘア） | [`1_Franklin_Shinano_Casual/`](1_Franklin_Shinano_Casual/) |
| `player_two` | **トレバー (Trevor)** | **ミルティナ (Miltina)** | *クラシックメイド*（白黒メイドドレス＋エプロン＋ツインテール、任意の `fbx_hair` 指定に対応） | [`3_Trevor_Miltina_Maid/`](3_Trevor_Miltina_Maid/) |

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
- **ヘア・フェイス自動フォールバック**:
  - **しなの**: *ねこタイドボブヘア* がある場合はそちらを使用し、無い場合は自動的に標準ヘア（`Hair_base`、`Hair_bang`、`Hair_side`、`Hair_back`、`Other_ear`、`Other_tail`）および `ShinanoDefAdultNewv5.anim` / 標準アイテクスチャを使用します。
  - **ミルティナ**: 任意の `fbx_hair` 上書きに対応し、未指定時は標準ツインテール（`Milltina_hair_*`）および `Miltina_close eyes_Base_adult.anim` / 標準アイテクスチャを使用します。
- **言語の自動判定**: システムロケールに応じて `en` / `ja` / `pt` を自動選択し、`--lang en|ja|pt` での明示指定も可能です。

---

## CLI コマンドと検証テスト

| コマンド | 用途 |
| :--- | :--- |
| `RUN_MANAGER.bat` / `EXECUTAR_GERENCIADOR.bat` | First-Run・ビルド・配置を行う Windows 対話メニュー |
| `python run_mod_manager.py --setup` | 対話型 First-Run ウィザードと `vrc2gtav.cfg` の設定 |
| `python run_mod_manager.py --check-env` | GTA V・Blender・`rage-cli`・アセットパスの検証 |
| `python scripts/common_tools/setup_first_run.py --check-only` | 環境と元アセットの有無を非破壊チェック |
| `python run_mod_manager.py --character all` | 3人分の Blender 再構築・YDD/YTD 出力・RPF7 配置を一括実行 |
| `python run_mod_manager.py --character {michael,franklin,trevor} --lang {en,ja,pt}` | 指定キャラクターのみを指定言語の UI でビルド／配置 |
| `python run_mod_manager.py --deploy-only` | 既存ビルド済みフォルダから `mods/x64v.rpf` へ再梱包・配置 |
| `python scripts/common_tools/test_mod_suite.py --source-only` | ソース・設定・i18n・フォールバックの `5` スイートを実行（クローン直後対応） |
| `python scripts/common_tools/test_mod_suite.py` | 全 `8` スイートの統合検証を実行（ビルド・配置済み環境が必要） |

---

## リポジトリ構成

```text
vrcavatar2gtav/
├── docs/
│   ├── DEPLOYMENT_GUIDE.md          # 技術・導入ガイド全文 (EN)
│   ├── DEPLOYMENT_GUIDE.pt-BR.md    # 技術・導入ガイド全文 (PT-BR)
│   └── DEPLOYMENT_GUIDE.ja.md       # 内部設計・リギング・Sollumz・RPF7 技術ガイド (JA)
├── scripts/
│   ├── common_tools/                # First-Run、.unity スケール解析、i18n、test_mod_suite.py
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
  - **ヘア**: `Hair_back`, `Hair_bang`, `Hair_base`, `Hair_side`, `Other_ear`, `Other_tail` (*Shinano* 標準ヘア)
  - **アイテクスチャ & 表情 *(任意 / フォールバック)***: `MoonButterfly eye` & `ShinanoDefAdultNewv5.anim`

- **トレバー・フィリップス (`player_two`) — ミルティナ (*Classic Maid*)**
  - **素体**: `Body`, `Milltina_body` (*Milltina*)
  - **衣装 & 小物**: `Milltina_cloth_dress`, `Milltina_cloth_apron`, `Milltina_cloth_skirt`, `Milltina_cloth_panties`, `Milltina_cloth_collar`, `Milltina_cloth_hat`, `Milltina_cloth_neck_ribbon`, `Milltina_cloth_wrist_cuffs`, `Milltina_cloth_garterbelt`, `Milltina_cloth_hair_ribbon`, `Milltina_cloth_tail_ribbon`, `Milltina_cloth_tail_slit`, `Milltina_cloth_shoes` (*Milltina*)
  - **ヘア & 牛パーツ**: `Milltina_hair_base`, `Milltina_hair_side`, `Milltina_hair_front`, `Milltina_hair_front_side`, `Milltina_hair_twintail`, `Milltina_cow_ears`, `Milltina_cow_horns`, `Milltina_cow_tail` (*Milltina*、任意のカスタム `fbx_hair` 上書きにも対応)
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

本プロジェクトの自動化スクリプトおよびドキュメントは **MIT License** のもとで公開されています（詳細は [`LICENSE`](LICENSE) / `Copyright (c) 2026 Daniel M` を参照）。上記クレジットに記載されたサードパーティ製アセット・ツールの権利および利用規約は各配布元の定めに従います。
