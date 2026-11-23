"""
i18n_catalog_builders_layer.py
==============================
Layer 2 of 3 for the VRC2GTAV trilingual translation catalog.

Contains atlas generators, Blender character builders, hair porting,
blendshape presets, and ped damage strings.
"""

from typing import Dict


# Ordered subset of the trilingual ("en", "ja", "pt") catalog consumed by
# vrc2gtav_i18n.py to keep catalog files concise and maintainable.
BUILDERS_TRANSLATION_CATALOG: Dict[str, Dict[str, str]] = {
    "repack.copy_zero_done": {
        "en": "  [PROGRESS] {bar} 100.0% (0.0/0.0 MB)",
        "ja": "  [進捗] {bar} 100.0% (0.0/0.0 MB)",
        "pt": "  [PROGRESSO] {bar} 100.0% (0.0/0.0 MB)",
    },
    "repack.copy_progress": {
        "en": "  [PROGRESS] {bar} {percent:5.1f}% ({copied_mb:.1f}/{total_mb:.1f} MB | {rate_mbs:.1f} MB/s | ETA {eta_sec:.0f}s)",
        "ja": "  [進捗] {bar} {percent:5.1f}% ({copied_mb:.1f}/{total_mb:.1f} MB | {rate_mbs:.1f} MB/s | 残り {eta_sec:.0f}秒)",
        "pt": "  [PROGRESSO] {bar} {percent:5.1f}% ({copied_mb:.1f}/{total_mb:.1f} MB | {rate_mbs:.1f} MB/s | ETA {eta_sec:.0f}s)",
    },
    "repack.copy_done": {
        "en": "  [PROGRESS] {bar} 100.0% ({total_mb:.1f}/{total_mb:.1f} MB | {rate_mbs:.1f} MB/s | {elapsed:.1f}s)",
        "ja": "  [進捗] {bar} 100.0% ({total_mb:.1f}/{total_mb:.1f} MB | {rate_mbs:.1f} MB/s | {elapsed:.1f}秒)",
        "pt": "  [PROGRESSO] {bar} 100.0% ({total_mb:.1f}/{total_mb:.1f} MB | {rate_mbs:.1f} MB/s | {elapsed:.1f}s)",
    },
    "repack.installed_ok": {
        "en": "{label} installed successfully.",
        "ja": "{label} のインストールが完了しました。",
        "pt": "{label} instalado com sucesso.",
    },
    "repack.create_start": {
        "en": "--- {description} ({expected_mb:.1f} MB input) ---",
        "ja": "--- {description} (入力 {expected_mb:.1f} MB) ---",
        "pt": "--- {description} ({expected_mb:.1f} MB de entrada) ---",
    },
    "repack.reading_files": {
        "en": "  [PROGRESS] {bar} Reading files... ({elapsed:.1f}s | ~{expected_mb:.1f} MB)",
        "ja": "  [進捗] {bar} ファイル読込中... ({elapsed:.1f}秒 | ~{expected_mb:.1f} MB)",
        "pt": "  [PROGRESSO] {bar} Lendo arquivos... ({elapsed:.1f}s | ~{expected_mb:.1f} MB)",
    },
    "repack.writing_rpf": {
        "en": "  [PROGRESS] {bar} {percent:5.1f}% Writing RPF ({written_mb:.1f}/{expected_mb:.1f} MB | {elapsed:.1f}s)",
        "ja": "  [進捗] {bar} {percent:5.1f}% RPF 書込中 ({written_mb:.1f}/{expected_mb:.1f} MB | {elapsed:.1f}秒)",
        "pt": "  [PROGRESSO] {bar} {percent:5.1f}% Gravando RPF ({written_mb:.1f}/{expected_mb:.1f} MB | {elapsed:.1f}s)",
    },
    "repack.cmd_failed": {
        "en": "[ERROR] Execution failed: {description}",
        "ja": "[エラー] 実行に失敗しました: {description}",
        "pt": "[ERRO] Falha ao executar: {description}",
    },
    "repack.return_code": {
        "en": "Return code: {returncode}",
        "ja": "終了コード: {returncode}",
        "pt": "Código de retorno: {returncode}",
    },
    "repack.process_output": {
        "en": "Process output:",
        "ja": "プロセス出力:",
        "pt": "Saída do processo:",
    },
    "repack.create_done": {
        "en": "  [PROGRESS] {bar} 100.0% ({final_mb:.1f} MB) Finished in {elapsed:.1f}s",
        "ja": "  [進捗] {bar} 100.0% ({final_mb:.1f} MB) {elapsed:.1f}秒で完了",
        "pt": "  [PROGRESSO] {bar} 100.0% ({final_mb:.1f} MB) Concluído em {elapsed:.1f}s",
    },
    "repack.banner": {
        "en": "=== GTA V MOD REPACK & DEPLOY PIPELINE ===",
        "ja": "=== GTA V MOD RPF 再パック＆デプロイパイプライン ===",
        "pt": "=== GTA V MOD REPACK & DEPLOY PIPELINE ===",
    },
    "repack.gtav_dest": {
        "en": "GTA V Dest:      {path}",
        "ja": "GTA V 出力先:    {path}",
        "pt": "Destino GTA V:   {path}",
    },
    "repack.staging_missing": {
        "en": "[ERROR] Staging directory not found: {path}",
        "ja": "[エラー] ステージングディレクトリが見つかりません: {path}",
        "pt": "[ERRO] Diretório de staging não encontrado: {path}",
    },
    "repack.stage_repacking": {
        "en": "Repacking {name}",
        "ja": "{name} を再パック中",
        "pt": "Repacotando {name}",
    },
    "repack.stage_installing": {
        "en": "Installing {name}",
        "ja": "{name} をインストール中",
        "pt": "Instalando {name}",
    },
    "repack.stage_verifying": {
        "en": "Verifying installed RPFs (OPEN and f_size=0)",
        "ja": "インストール済み RPF を検証中 (OPEN と f_size=0)",
        "pt": "Verificando RPFs instalados (OPEN e f_size=0)",
    },
    "repack.props_missing_skip": {
        "en": "[WARNING] streamedpedprops_extracted folder missing ({path}); skipping props repack.",
        "ja": "[警告] streamedpedprops_extracted フォルダがないため ({path})、プロップの再パックをスキップします。",
        "pt": "[AVISO] Diretório streamedpedprops_extracted ausente ({path}); pulando repack de props.",
    },
    "repack.verifying_header": {
        "en": "\n=== VERIFYING INSTALLED FILES ===",
        "ja": "\n=== インストール済みファイルを検証中 ===",
        "pt": "\n=== VERIFICANDO ARQUIVOS INSTALADOS ===",
    },
    "repack.verify_dlc_header": {
        "en": "dlc.rpf encryption header:   {flag} (expected b'OPEN')",
        "ja": "dlc.rpf 暗号化ヘッダー:      {flag} (期待値 b'OPEN')",
        "pt": "dlc.rpf cabeçalho de criptografia:  {flag} (esperado b'OPEN')",
    },
    "repack.verify_x64v_header": {
        "en": "x64v.rpf encryption header:  {flag} (expected b'OPEN')",
        "ja": "x64v.rpf 暗号化ヘッダー:     {flag} (期待値 b'OPEN')",
        "pt": "x64v.rpf cabeçalho de criptografia: {flag} (esperado b'OPEN')",
    },
    "repack.verify_dlc_compressed": {
        "en": "Compressed binary entries in dlc.rpf:  {count} (expected 0)",
        "ja": "dlc.rpf 内の圧縮バイナリエントリ数:  {count} (期待値 0)",
        "pt": "Entradas binárias comprimidas em dlc.rpf:  {count} (esperado 0)",
    },
    "repack.verify_x64v_compressed": {
        "en": "Compressed binary entries in x64v.rpf: {count} (expected 0)",
        "ja": "x64v.rpf 内の圧縮バイナリエントリ数: {count} (期待値 0)",
        "pt": "Entradas binárias comprimidas em x64v.rpf: {count} (esperado 0)",
    },
    "repack.verify_passed": {
        "en": "\n[VERIFICATION PASSED] All archives installed successfully with 'OPEN' header and zero risk of ERR_GEN_ZLIB_2!",
        "ja": "\n[検証合格] 全アーカイブが 'OPEN' ヘッダー付きで正常にインストールされ、ERR_GEN_ZLIB_2 のリスクはありません！",
        "pt": "\n[VERIFICAÇÃO APROVADA] Todos os arquivos foram instalados com sucesso, com cabeçalho 'OPEN' e zero risco de ERR_GEN_ZLIB_2!",
    },
    "repack.verify_warn": {
        "en": "\n[WARNING] Discrepancies found during verification. Check detailed logs.",
        "ja": "\n[警告] 検証中に不整合が検出されました。詳細ログを確認してください。",
        "pt": "\n[AVISO] Discrepâncias encontradas na verificação. Verifique os logs detalhados.",
    },
    "repack.fatal_error": {
        "en": "\n[FATAL DEPLOY ERROR] {error}",
        "ja": "\n[致命的デプロイエラー] {error}",
        "pt": "\n[FALHA FATAL NO DEPLOY] {error}",
    },
    "repack.cli_description": {
        "en": "Repack modded GTA V RPF archives with live progress bars and install into mods/",
        "ja": "改造済み GTA V RPF アーカイブを進捗バー付きで再パックし、mods/ にインストールします",
        "pt": "Repacota arquivos RPF modificados do GTA V com barra de progresso e instala em mods/",
    },
    "franklin.runner_description": {
        "en": "Build Shinano Casual (Franklin / player_one) in Blender",
        "ja": "Blender で Shinano Casual (フランクリン / player_one) をビルドします",
        "pt": "Compila a Shinano Casual (Franklin / player_one) no Blender",
    },
    "franklin.blender_script_missing": {
        "en": "[ERROR] Blender script not found: {path}",
        "ja": "[エラー] Blender スクリプトが見つかりません: {path}",
        "pt": "[ERRO] Script Blender não encontrado: {path}",
    },
    "franklin.running_blender": {
        "en": "[INFO] Running Blender: {command}",
        "ja": "[情報] Blender を実行中: {command}",
        "pt": "[INFO] Executando Blender: {command}",
    },
    "franklin.atlas_cli_description": {
        "en": "Generate the 2K texture atlas and .ytd dictionary for Franklin (Shinano Casual)",
        "ja": "フランクリン (Shinano Casual) 用の 2K テクスチャアトラスと .ytd 辞書を生成します",
        "pt": "Gera o texture atlas 2K e dicionário .ytd da Shinano Casual (Franklin)",
    },
    "franklin.tex_dir_missing": {
        "en": "[ERROR] Shinano textures directory not found: {path}",
        "ja": "[エラー] Shinano のテクスチャフォルダが見つかりません: {path}",
        "pt": "[ERRO] Diretório de texturas da Shinano não encontrado: {path}",
    },
    "franklin.generating_atlas": {
        "en": "[INFO] Generating Franklin 2x2 Atlas at: {path} ({size}x{size})",
        "ja": "[情報] フランクリン用 2x2 アトラスを生成中: {path} ({size}x{size})",
        "pt": "[INFO] Gerando Atlas 2x2 do Franklin em: {path} ({size}x{size})",
    },
    "franklin.atlas_saved": {
        "en": "[OK] Franklin 2x2 Atlas saved to: {path}",
        "ja": "[OK] フランクリン用 2x2 アトラスを保存しました: {path}",
        "pt": "[OK] Atlas 2x2 do Franklin salvo em: {path}",
    },
    "franklin.compiling_ytd": {
        "en": "\n[INFO] Compiling Franklin .ytd texture dictionary...",
        "ja": "\n[情報] フランクリン用 .ytd テクスチャ辞書をコンパイル中...",
        "pt": "\n[INFO] Compilando dicionário de textura .ytd do Franklin...",
    },
    "franklin.ytd_generated": {
        "en": "[SUCCESS] Generated .ytd dictionary: {path}",
        "ja": "[成功] .ytd 辞書を生成しました: {path}",
        "pt": "[SUCESSO] Dicionário .ytd gerado com sucesso: {path}",
    },
    "franklin.atlas_failed": {
        "en": "[ERROR] Failed to generate Franklin texture atlas: {error}",
        "ja": "[エラー] フランクリン用テクスチャアトラスの生成に失敗しました: {error}",
        "pt": "[ERRO] Falha na geração do atlas de textura do Franklin: {error}",
    },
    "franklin.fbx_prop_unknown": {
        "en": "Unknown FBX property type: {prop_type}",
        "ja": "不明な FBX プロパティ型です: {prop_type}",
        "pt": "Tipo de propriedade FBX desconhecido: {prop_type}",
    },
    "franklin.importing_skeleton": {
        "en": "[INFO] Importing Franklin skeleton ({filename})...",
        "ja": "[情報] フランクリンのスケルトン ({filename}) をインポート中...",
        "pt": "[INFO] Importando esqueleto do Franklin ({filename})...",
    },
    "franklin.skeleton_filtered": {
        "en": "[OK] Franklin skeleton filtered to {count} bones.",
        "ja": "[OK] フランクリンのスケルトンを {count} ボーンにフィルタリングしました。",
        "pt": "[OK] Esqueleto do Franklin filtrado para {count} ossos.",
    },
    "franklin.importing_fbx": {
        "en": "[INFO] Importing {filename}...",
        "ja": "[情報] {filename} をインポート中...",
        "pt": "[INFO] Importando {filename}...",
    },
    "franklin.face_normals_recovered": {
        "en": "[OK] Recovered {count} face loop normals from FBX.",
        "ja": "[OK] FBX から {count} 個の顔ループ法線を復元しました。",
        "pt": "[OK] {count} normais de loop faciais recuperadas do FBX.",
    },
    "franklin.loading_blendshapes": {
        "en": "[INFO] Loading {count} blendshapes from {path}",
        "ja": "[情報] {path} から {count} 個のブレンドシェイプを読み込み中",
        "pt": "[INFO] Carregando {count} blendshapes de {path}",
    },
    "franklin.applied_blendshapes": {
        "en": "[OK] Applied {count} active blendshapes onto Body.",
        "ja": "[OK] Body に {count} 個の有効なブレンドシェイプを適用しました。",
        "pt": "[OK] {count} blendshapes aplicadas no Body.",
    },
    "franklin.jaw_weights_mapped": {
        "en": "[OK] Mapped {count} vertices to FACIAL_jaw on Body.",
        "ja": "[OK] Body 上の {count} 頂点を FACIAL_jaw にマッピングしました。",
        "pt": "[OK] {count} vértices mapeados para FACIAL_jaw no Body.",
    },
    "franklin.body_triangulated": {
        "en": "[OK] Triangulated Body: {count} vertices.",
        "ja": "[OK] Body を三角化しました: {count} 頂点。",
        "pt": "[OK] Body triangulado: {count} vértices.",
    },
    "franklin.body_normals_prepared": {
        "en": "[OK] Prepared {count} custom normals for Body.",
        "ja": "[OK] Body 用に {count} 個のカスタム法線を準備しました。",
        "pt": "[OK] Preparadas {count} normais customizadas para o Body.",
    },
    "franklin.jaw_weights_applied": {
        "en": "[OK] Applied FACIAL_jaw and SKEL_Head weights to processed Body mesh.",
        "ja": "[OK] 処理済み Body メッシュに FACIAL_jaw と SKEL_Head のウェイトを適用しました。",
        "pt": "[OK] Pesos de FACIAL_jaw e SKEL_Head aplicados na malha processada do Body.",
    },
    "franklin.arm_bones_relocated": {
        "en": "[OK] Relocated {count} arm/hand/finger bones on Franklin armature.",
        "ja": "[OK] フランクリンのアーマチュア上で {count} 本の腕・手・指ボーンを再配置しました。",
        "pt": "[OK] {count} ossos de braço/mão/dedos realocados na armature do Franklin.",
    },
    "franklin.mesh_joined": {
        "en": "[OK] Consolidated mesh has {count} vertices.",
        "ja": "[OK] 統合メッシュの頂点数: {count}。",
        "pt": "[OK] Malha consolidada com {count} vértices.",
    },
    "franklin.exporting_models": {
        "en": "[INFO] Exporting uppr_008_u.ydd, uppr_000_u.ydd, and uppr_001_u.ydd for Franklin...",
        "ja": "[情報] フランクリン用に uppr_008_u.ydd、uppr_000_u.ydd、uppr_001_u.ydd をエクスポート中...",
        "pt": "[INFO] Exportando uppr_008_u.ydd, uppr_000_u.ydd e uppr_001_u.ydd para o Franklin...",
    },
    "franklin.export_result": {
        "en": "Export {slot_name} result: {result}",
        "ja": "{slot_name} エクスポート結果: {result}",
        "pt": "Resultado da exportação de {slot_name}: {result}",
    },
    "franklin.yft_exported": {
        "en": "[OK] Exported .yft skeleton to {path} ({updated}/{total} bones, max error={max_delta:.6f} m)",
        "ja": "[OK] .yft スケルトンを {path} にエクスポートしました ({updated}/{total} ボーン, 最大誤差={max_delta:.6f} m)",
        "pt": "[OK] Esqueleto .yft exportado em {path} ({updated}/{total} ossos, erro máx={max_delta:.6f} m)",
    },
    "franklin.build_done": {
        "en": "[OK] Build completed successfully!",
        "ja": "[OK] ビルドが正常に完了しました！",
        "pt": "[OK] Concluído com sucesso!",
    },
    "michael.run_desc": {
        "en": "Run the Shinano Eternal Reunion (Michael) Blender build using paths from vrc2gtav.cfg.",
        "ja": "vrc2gtav.cfg のパスを使って Shinano Eternal Reunion (Michael) の Blender ビルドを実行します。",
        "pt": "Executa a compilação da Shinano Eternal Reunion (Michael) no Blender usando os caminhos do arquivo vrc2gtav.cfg.",
    },
    "michael.blender_missing": {
        "en": "[ERROR] Blender script not found: {path}",
        "ja": "[エラー] Blender スクリプトが見つかりません: {path}",
        "pt": "[ERRO] Script Blender não encontrado: {path}",
    },
    "michael.running_blender": {
        "en": "[INFO] Running Blender: {command}",
        "ja": "[INFO] Blender を実行中: {command}",
        "pt": "[INFO] Executando Blender: {command}",
    },
    "michael.atlas.cli_desc": {
        "en": "Generate the unified 4x2 lilToon Texture Atlas and compile the GTA V .ytd archive for Michael (Eternal Reunion).",
        "ja": "Michael (Eternal Reunion) 用の統合 4x2 lilToon テクスチャアトラスを生成し、GTA V .ytd 辞書をコンパイルします。",
        "pt": "Gera o Texture Atlas 4x2 unificado lilToon e compila o dicionário .ytd do GTA V para o Michael (Eternal Reunion).",
    },
    "michael.atlas.output_dir_help": {
        "en": "Optional output directory override for generated atlas PNG textures.",
        "ja": "生成されるアトラス PNG テクスチャの出力ディレクトリ（省略可）。",
        "pt": "Diretório de saída opcional para substituir o destino das texturas PNG do atlas.",
    },
    "michael.atlas.generating": {
        "en": "[INFO] Generating lilToon Texture Atlas at: {output_dir} ({width}x{height})",
        "ja": "[INFO] lilToon テクスチャアトラスを生成中: {output_dir} ({width}x{height})",
        "pt": "[INFO] Gerando Texture Atlas lilToon em: {output_dir} ({width}x{height})",
    },
    "michael.atlas.required_missing": {
        "en": "Required texture not found: {path}",
        "ja": "必須テクスチャが見つかりません: {path}",
        "pt": "Textura obrigatória não encontrada: {path}",
    },
    "michael.atlas.processing_cell": {
        "en": "[INFO] Processing cell '{key}' ({col}, {row})...",
        "ja": "[INFO] セル '{key}' ({col}, {row}) を処理中...",
        "pt": "[INFO] Processando célula '{key}' ({col}, {row})...",
    },
    "michael.atlas.accessory_missing": {
        "en": "Accessory texture not found: {path}",
        "ja": "アクセサリーテクスチャが見つかりません: {path}",
        "pt": "Textura de acessório não encontrada: {path}",
    },
    "michael.atlas.processing_accessory": {
        "en": "[INFO] Processing accessory '{key}'...",
        "ja": "[INFO] アクセサリー '{key}' を処理中...",
        "pt": "[INFO] Processando acessório '{key}'...",
    },
    "michael.atlas.saved": {
        "en": "[SUCCESS] lilToon Texture Atlas maps generated successfully:\n  - Diffuse:  {diffuse}\n  - Specular: {specular} (and {legacy_spec})\n  - Normal:   {normal} (and {legacy_normal})",
        "ja": "[成功] lilToon テクスチャアトラスマップの生成が完了しました:\n  - Diffuse:  {diffuse}\n  - Specular: {specular} (および {legacy_spec})\n  - Normal:   {normal} (および {legacy_normal})",
        "pt": "[SUCESSO] Mapas do Texture Atlas lilToon gerados com êxito:\n  - Diffuse:  {diffuse}\n  - Specular: {specular} (e {legacy_spec})\n  - Normal:   {normal} (e {legacy_normal})",
    },
    "michael.atlas.compiling_ytd": {
        "en": "\n[INFO] Compiling Michael (Eternal Reunion) .ytd texture dictionary...",
        "ja": "\n[INFO] Michael (Eternal Reunion) 用 .ytd テクスチャ辞書をコンパイル中...",
        "pt": "\n[INFO] Compilando dicionário de texturas .ytd do Michael (Eternal Reunion)...",
    },
    "michael.atlas.ytd_done": {
        "en": "[SUCCESS] .ytd texture dictionary generated successfully: {path}",
        "ja": "[成功] .ytd テクスチャ辞書を正常に生成しました: {path}",
        "pt": "[SUCESSO] Dicionário .ytd gerado com sucesso: {path}",
    },
    "michael.build.cli_desc": {
        "en": "Shinano Eternal Reunion compiler for GTA V Legacy",
        "ja": "GTA V Legacy 用 Shinano Eternal Reunion コンパイラ",
        "pt": "Compilador Shinano Eternal Reunion para GTA V Legacy",
    },
    "michael.build.arg_target_char": {
        "en": "Target Story Mode character",
        "ja": "対象のストーリーモードキャラクター",
        "pt": "Personagem alvo do Modo História",
    },
    "michael.build.arg_skeleton": {
        "en": "Path to skeleton .yft file",
        "ja": "スケルトン .yft ファイルのパス",
        "pt": "Caminho do arquivo de esqueleto .yft",
    },
    "michael.build.arg_shinano_fbx": {
        "en": "Path to Shinano base FBX (Body and Body_base)",
        "ja": "Shinano ベース FBX (Body / Body_base) のパス",
        "pt": "Caminho do FBX base da Shinano (Body e Body_base)",
    },
    "michael.build.arg_outfit_fbx": {
        "en": "Path to Eternal Reunion outfit FBX",
        "ja": "Eternal Reunion 衣装 FBX のパス",
        "pt": "Caminho do FBX de roupas Eternal Reunion",
    },
    "michael.build.arg_watch_fbx": {
        "en": "Path to Pocket Watch FBX",
        "ja": "懐中時計 (Pocket Watch) FBX のパス",
        "pt": "Caminho do FBX do Relógio de Bolso",
    },
    "michael.build.arg_hair_fbx": {
        "en": "Path to Neko Tied Bob hair FBX",
        "ja": "Neko Tied Bob ヘアー FBX のパス",
        "pt": "Caminho do FBX do cabelo Neko Tied Bob",
    },
    "michael.build.arg_face_anim": {
        "en": "Path to facial expression .anim file",
        "ja": "表情用 .anim ファイルのパス",
        "pt": "Caminho do arquivo .anim com expressões faciais",
    },
    "michael.build.arg_texture_dir": {
        "en": "Directory containing 4x2 Atlas textures",
        "ja": "4x2 アトラステクスチャのディレクトリ",
        "pt": "Diretório das texturas do Atlas 4x2",
    },
    "michael.build.arg_atlas_png": {
        "en": "Texture Atlas diffuse PNG filename",
        "ja": "テクスチャアトラス Diffuse PNG ファイル名",
        "pt": "Nome do arquivo PNG difuso do Texture Atlas",
    },
    "michael.build.arg_normal_png": {
        "en": "Normal map PNG filename",
        "ja": "ノーマルマップ PNG ファイル名",
        "pt": "Nome do arquivo PNG do normal map",
    },
    "michael.build.arg_spec_png": {
        "en": "Specular map PNG filename",
        "ja": "スペキュラマップ PNG ファイル名",
        "pt": "Nome do arquivo PNG do specular map",
    },
    "michael.build.arg_output_dir": {
        "en": "Output directory for exported .ydd files",
        "ja": ".ydd ファイルの出力ディレクトリ",
        "pt": "Diretório de saída dos arquivos .ydd",
    },
    "michael.build.arg_max_verts": {
        "en": "Maximum vertices per sub-geometry (uint16)",
        "ja": "サブジオメトリあたりの最大頂点数 (uint16)",
        "pt": "Máximo de vértices por subgeometria (uint16)",
    },
    "michael.build.unknown_fbx_prop": {
        "en": "Unknown FBX property type: {type_code}",
        "ja": "不明な FBX プロパティ型: {type_code}",
        "pt": "Tipo de propriedade FBX desconhecido: {type_code}",
    },
    "michael.build.watch_bone_missing_outfit": {
        "en": "Bone '{bone}' not found in Eternal Reunion outfit armature.",
        "ja": "Eternal Reunion 衣装アーマチュアにボーン '{bone}' が見つかりません。",
        "pt": "Osso '{bone}' não encontrado na armature do traje Eternal Reunion.",
    },
    "michael.build.watch_bone_missing_watch": {
        "en": "Bone '{bone}' not found in Pocket Watch armature.",
        "ja": "Pocket Watch アーマチュアにボーン '{bone}' が見つかりません。",
        "pt": "Osso '{bone}' não encontrado na armature do Pocket Watch.",
    },
    "michael.build.splitting_material": {
        "en": "[INFO] Splitting material '{name}' ({count} triangles) into {chunks} sub-geometries to satisfy uint16 limit (65,535 vertices).",
        "ja": "[INFO] マテリアル '{name}' ({count} 三角形) を uint16 上限 (65,535 頂点) 内で {chunks} 個のサブジオメトリに分割しています。",
        "pt": "[INFO] Dividindo material '{name}' ({count} triângulos) em {chunks} subgeometrias para respeitar o limite uint16 (65.535 vértices).",
    },
    "michael.build.no_shape_keys": {
        "en": "Mesh '{label}' has no shape keys available.",
        "ja": "メッシュ '{label}' に利用可能なシェイプキーがありません。",
        "pt": "A malha '{label}' não possui shape keys disponíveis.",
    },
    "michael.build.shape_key_oob": {
        "en": "Shape key index {index} out of range on '{name}' (available count: {available}).",
        "ja": "シェイプキーインデックス {index} が '{name}' の範囲外です (利用可能数: {available})。",
        "pt": "Índice de shape key {index} fora do intervalo em '{name}' (total disponível: {available}).",
    },
    "michael.build.applied_shape_keys": {
        "en": "[INFO] Applied {count} indexed shape keys on '{name}'.",
        "ja": "[INFO] '{name}' に {count} 個のインデックス指定シェイプキーを適用しました。",
        "pt": "[INFO] Aplicados {count} shape keys por índice em '{name}'.",
    },
    "michael.build.input_skeleton_label": {
        "en": "GTA V Skeleton (.yft)",
        "ja": "GTA V スケルトン (.yft)",
        "pt": "Esqueleto GTA V (.yft)",
    },
    "michael.build.input_shinano_fbx_label": {
        "en": "Shinano Base FBX",
        "ja": "Shinano ベース FBX",
        "pt": "FBX Base Shinano",
    },
    "michael.build.input_outfit_fbx_label": {
        "en": "Eternal Reunion Outfit FBX",
        "ja": "Eternal Reunion 衣装 FBX",
        "pt": "FBX Roupas Eternal Reunion",
    },
    "michael.build.input_watch_fbx_label": {
        "en": "Pocket Watch FBX",
        "ja": "懐中時計 (Pocket Watch) FBX",
        "pt": "FBX Pocket Watch",
    },
    "michael.build.input_hair_fbx_label": {
        "en": "Neko Tied Bob Hair FBX",
        "ja": "Neko Tied Bob ヘアー FBX",
        "pt": "FBX Cabelo Neko Tied Bob",
    },
    "michael.build.input_face_anim_label": {
        "en": "Facial Animation (.anim)",
        "ja": "フェイシャルアニメーション (.anim)",
        "pt": "Animação Facial (.anim)",
    },
    "michael.build.input_missing": {
        "en": "{label} not found at: {path}",
        "ja": "{label} が見つかりません: {path}",
        "pt": "{label} não encontrado em: {path}",
    },
    "michael.build.atlas_tex_missing": {
        "en": "Atlas texture not found at: {path}",
        "ja": "アトラステクスチャが見つかりません: {path}",
        "pt": "Textura do atlas não encontrada em: {path}",
    },
    "michael.build.max_verts_oob": {
        "en": "--max-verts-per-chunk out of uint16 range (1..65535): {value}",
        "ja": "--max-verts-per-chunk が uint16 範囲 (1..65535) 外です: {value}",
        "pt": "--max-verts-per-chunk fora do limite uint16 (1..65535): {value}",
    },
    "michael.build.invalid_character": {
        "en": "Invalid character: {name}. Use michael, franklin, or trevor.",
        "ja": "無効なキャラクター: {name}。michael、franklin、または trevor を指定してください。",
        "pt": "Personagem inválido: {name}. Use michael, franklin ou trevor.",
    },
    "michael.build.importing_skeleton": {
        "en": "[INFO] Importing base GTA V skeleton: {path}",
        "ja": "[INFO] ベース GTA V スケルトンをインポート中: {path}",
        "pt": "[INFO] Importando esqueleto base do GTA V: {path}",
    },
    "michael.build.skeleton_load_failed": {
        "en": "Failed to load GTA V skeleton from '{path}'.",
        "ja": "'{path}' から GTA V スケルトンを読み込めませんでした。",
        "pt": "Não foi possível carregar o esqueleto GTA V de '{path}'.",
    },
    "michael.build.importing_shinano": {
        "en": "[INFO] Importing Shinano Base FBX: {path}",
        "ja": "[INFO] Shinano ベース FBX をインポート中: {path}",
        "pt": "[INFO] Importando Base Shinano FBX: {path}",
    },
    "michael.build.importing_outfit": {
        "en": "[INFO] Importing Outfit FBX: {path}",
        "ja": "[INFO] 衣装 FBX をインポート中: {path}",
        "pt": "[INFO] Importando Outfit FBX: {path}",
    },
    "michael.build.importing_watch": {
        "en": "[INFO] Importing Pocket Watch FBX: {path}",
        "ja": "[INFO] Pocket Watch FBX をインポート中: {path}",
        "pt": "[INFO] Importando Pocket Watch FBX: {path}",
    },
    "michael.build.importing_hair": {
        "en": "[INFO] Importing Neko Tied Bob Hair FBX: {path}",
        "ja": "[INFO] Neko Tied Bob ヘアー FBX をインポート中: {path}",
        "pt": "[INFO] Importando Cabelo Neko Tied Bob FBX: {path}",
    },
    "michael.build.hair_root_missing": {
        "en": "Bone 'Hair Root' not found in Neko Tied Bob hair armature.",
        "ja": "Neko Tied Bob ヘアーアーマチュアにボーン 'Hair Root' が見つかりません。",
        "pt": "Osso 'Hair Root' não encontrado na armature do cabelo Neko Tied Bob.",
    },
    "michael.build.fbx_normals_loaded": {
        "en": "[INFO] Loaded {count} IndexToDirect facial normals from FBX.",
        "ja": "[INFO] FBX から {count} 個の IndexToDirect フェイシャル法線を読み込みました。",
        "pt": "[INFO] {count} normais faciais IndexToDirect carregadas do FBX.",
    },
    "michael.build.jaw_weights_mapped": {
        "en": "[OK] Mapped {count} vertices to FACIAL_jaw on Body.",
        "ja": "[OK] Body 上の {count} 頂点を FACIAL_jaw にマッピングしました。",
        "pt": "[OK] {count} vértices mapeados para FACIAL_jaw no Body.",
    },
    "michael.build.mesh_not_found": {
        "en": "[WARN] Mesh object '{name}' not found; skipping.",
        "ja": "[警告] メッシュオブジェクト '{name}' が見つかりません。スキップします。",
        "pt": "[AVISO] Objeto de malha '{name}' não encontrado; ignorando.",
    },
    "michael.build.processing_mesh": {
        "en": "[INFO] Processing mesh: {name} ({count} vertices)",
        "ja": "[INFO] メッシュ処理中: {name} ({count} 頂点)",
        "pt": "[INFO] Processando malha: {name} ({count} vértices)",
    },
    "michael.build.removed_glass_faces": {
        "en": "[INFO] Removed {count} glass/lens faces from '{name}'.",
        "ja": "[INFO] '{name}' から {count} 個のガラス/レンズ面を削除しました。",
        "pt": "[INFO] Removidas {count} faces de vidro/lente de '{name}'.",
    },
    "michael.build.shrink_culled": {
        "en": "[INFO] Shrink culling removed {count} hidden faces from {name}.",
        "ja": "[INFO] シュリンクカリングにより {name} の隠れた面 {count} 個を削除しました。",
        "pt": "[INFO] Shrink Culling removeu {count} faces ocultas de {name}.",
    },
    "michael.build.jaw_head_applied": {
        "en": "[OK] Applied FACIAL_jaw and SKEL_Head weights on Michael Body.",
        "ja": "[OK] Michael の Body に FACIAL_jaw と SKEL_Head のウェイトを適用しました。",
        "pt": "[OK] Pesos de FACIAL_jaw e SKEL_Head aplicados no Body do Michael.",
    },
    "michael.build.base_armature_missing": {
        "en": "Shinano base armature not found for arm/finger relocation.",
        "ja": "腕・指ボーン再配置用の Shinano ベースアーマチュアが見つかりません。",
        "pt": "Armature base da Shinano não encontrada para realocar braços/dedos.",
    },
    "michael.build.bones_relocated": {
        "en": "[OK] Relocated {count} arm/hand/finger bones in ped_armature.",
        "ja": "[OK] ped_armature 内で {count} 個の腕・手・指ボーンを再配置しました。",
        "pt": "[OK] {count} ossos de braços/mãos/dedos realocados em ped_armature.",
    },
    "michael.build.joining_meshes": {
        "en": "[INFO] Joining {count} processed meshes into SKEL_ROOT...",
        "ja": "[INFO] {count} 個の処理済みメッシュを SKEL_ROOT に結合中...",
        "pt": "[INFO] Unindo {count} malhas processadas em SKEL_ROOT...",
    },
    "michael.build.unified_summary": {
        "en": "[INFO] Unified SKEL_ROOT: {verts} vertices, {polys} polygons.",
        "ja": "[INFO] 統合 SKEL_ROOT: {verts} 頂点、{polys} ポリゴン。",
        "pt": "[INFO] SKEL_ROOT unificado: {verts} vértices, {polys} polígonos.",
    },
    "michael.build.exported_ydd": {
        "en": "[INFO] Exported {name}.ydd -> {status}",
        "ja": "[INFO] {name}.ydd をエクスポート -> {status}",
        "pt": "[INFO] Exportado {name}.ydd -> {status}",
    },
    "michael.build.exported_yft": {
        "en": "[OK] Exported .yft skeleton to {path} ({updated}/{total} bones, max error={delta:.6f} m)",
        "ja": "[OK] .yft スケルトンを {path} にエクスポート ({updated}/{total} ボーン、最大誤差={delta:.6f} m)",
        "pt": "[OK] Esqueleto .yft exportado em {path} ({updated}/{total} ossos, erro máx={delta:.6f} m)",
    },
    "michael.deploy.cli_desc": {
        "en": "Universal Slot Deployment (Michael & Franklin) into GTA V RPFs via RAGE CLI.",
        "ja": "RAGE CLI 経由で GTA V RPF へユニバーサルスロット置換 (Michael & Franklin) を展開します。",
        "pt": "Implantação Universal de Slots (Michael e Franklin) nos arquivos RPF do GTA V via RAGE CLI.",
    },
    "michael.deploy.task_start": {
        "en": "[TASK] {description}...",
        "ja": "[タスク] {description}...",
        "pt": "[TAREFA] {description}...",
    },
    "michael.deploy.task_failed": {
        "en": "[ERROR] Command failed: {command}",
        "ja": "[エラー] コマンド実行に失敗しました: {command}",
        "pt": "[ERRO] Falha ao executar: {command}",
    },
    "michael.deploy.task_error": {
        "en": "Execution failed: {description}",
        "ja": "実行エラー: {description}",
        "pt": "Erro na execução: {description}",
    },
    "michael.deploy.task_done": {
        "en": "[OK] {description} completed successfully.",
        "ja": "[OK] {description} が正常に完了しました。",
        "pt": "[OK] {description} concluído com sucesso.",
    },
    "michael.deploy.toc_patching": {
        "en": "[INFO] Patching binary TOC on: {path}",
        "ja": "[INFO] TOC バイナリパッチを適用中: {path}",
        "pt": "[INFO] Aplicando correção binária no TOC de: {path}",
    },
    "michael.deploy.toc_patched": {
        "en": "[INFO] Patched {count} nested RPF TOC entries.",
        "ja": "[INFO] ネストされた RPF TOC エントリ {count} 件を修正しました。",
        "pt": "[INFO] {count} entradas de arquivos RPF aninhados corrigidas no TOC.",
    },
    "michael.deploy.applying_ped": {
        "en": "\n[INFO] Applying universal slot replacement to: {label} ({directory})",
        "ja": "\n[INFO] ユニバーサルスロット置換を適用中: {label} ({directory})",
        "pt": "\n[INFO] Aplicando substituição universal em: {label} ({directory})",
    },
    "michael.deploy.ped_summary": {
        "en": "[OK] {label}: {uppr} uppr drawables replaced, {ytd} .ytd dictionaries updated, {dummy} human slots converted to dummy.",
        "ja": "[OK] {label}: {uppr} 個の uppr ドローアブルを置換、{ytd} 個の .ytd 辞書を更新、{dummy} 個の人間スロットをダミー化しました。",
        "pt": "[OK] {label}: {uppr} drawables uppr substituídos, {ytd} dicionários .ytd atualizados, {dummy} slots humanos convertidos em dummy.",
    },
    "michael.deploy.banner": {
        "en": "STARTING UNIVERSAL SLOT DEPLOYMENT (MICHAEL & FRANKLIN)",
        "ja": "ユニバーサルスロット展開を開始します (MICHAEL & FRANKLIN)",
        "pt": "INICIANDO IMPLANTAÇÃO UNIVERSAL DE SLOTS (MICHAEL & FRANKLIN)",
    },
    "michael.deploy.missing_file": {
        "en": "Required file not found: {path}",
        "ja": "必須ファイルが見つかりません: {path}",
        "pt": "Arquivo não encontrado: {path}",
    },
    "michael.deploy.packing_streamed": {
        "en": "\n[INFO] Packing streamedpeds_players_shinano.rpf...",
        "ja": "\n[INFO] streamedpeds_players_shinano.rpf をパック中...",
        "pt": "\n[INFO] Empacotando streamedpeds_players_shinano.rpf...",
    },
    "michael.deploy.updated_path": {
        "en": "[INFO] Updated: {path}",
        "ja": "[INFO] 更新完了: {path}",
        "pt": "[INFO] Atualizado: {path}",
    },
    "michael.deploy.packing_x64v": {
        "en": "\n[INFO] Packing x64v_modded.rpf...",
        "ja": "\n[INFO] x64v_modded.rpf をパック中...",
        "pt": "\n[INFO] Empacotando x64v_modded.rpf...",
    },
    "michael.deploy.copying_to": {
        "en": "[INFO] Copying {src} to {dest}...",
        "ja": "[INFO] {src} を {dest} へコピー中...",
        "pt": "[INFO] Copiando {src} para {dest}...",
    },
    "michael.deploy.updating_mppatches": {
        "en": "\n[INFO] Updating DLC mppatchesng...",
        "ja": "\n[INFO] DLC mppatchesng を更新中...",
        "pt": "\n[INFO] Atualizando DLC mppatchesng...",
    },
    "michael.deploy.updating_patchday3": {
        "en": "\n[INFO] Updating DLC patchday3ng...",
        "ja": "\n[INFO] DLC patchday3ng を更新中...",
        "pt": "\n[INFO] Atualizando DLC patchday3ng...",
    },
    "michael.deploy.dummy_applied": {
        "en": "[INFO] Dummy applied at: {path}",
        "ja": "[INFO] ダミーを適用: {path}",
        "pt": "[INFO] Dummy aplicado em: {path}",
    },
    "michael.deploy.task_pack_streamed": {
        "en": "Pack streamedpeds_players_shinano.rpf",
        "ja": "streamedpeds_players_shinano.rpf のパック",
        "pt": "Empacotamento de streamedpeds_players_shinano.rpf",
    },
    "michael.deploy.task_pack_props": {
        "en": "Pack streamedpedprops_shinano.rpf",
        "ja": "streamedpedprops_shinano.rpf のパック",
        "pt": "Empacotamento de streamedpedprops_shinano.rpf",
    },
    "michael.deploy.task_pack_x64v": {
        "en": "Pack x64v_modded.rpf",
        "ja": "x64v_modded.rpf のパック",
        "pt": "Empacotamento de x64v_modded.rpf",
    },
    "michael.deploy.task_verify_x64v": {
        "en": "Verify x64v_modded.rpf integrity",
        "ja": "x64v_modded.rpf 整合性検証",
        "pt": "Verificação de integridade de x64v_modded.rpf",
    },
    "michael.deploy.task_verify_target": {
        "en": "Final integrity check on {path}",
        "ja": "{path} の最終整合性チェック",
        "pt": "Verificação final de integridade em {path}",
    },
    "michael.deploy.task_pack_mppatches": {
        "en": "Pack mppatches.rpf",
        "ja": "mppatches.rpf のパック",
        "pt": "Empacotamento de mppatches.rpf",
    },
    "michael.deploy.task_pack_mppatches_dlc": {
        "en": "Pack mppatchesng_dlc.rpf",
        "ja": "mppatchesng_dlc.rpf のパック",
        "pt": "Empacotamento de mppatchesng_dlc.rpf",
    },
    "michael.deploy.task_verify_mppatches_dlc": {
        "en": "Verify mppatchesng_dlc.rpf integrity",
        "ja": "mppatchesng_dlc.rpf 整合性検証",
        "pt": "Verificação de integridade de mppatchesng_dlc.rpf",
    },
    "michael.deploy.task_extract_patchday3_dlc": {
        "en": "Extract original patchday3ng/dlc.rpf",
        "ja": "元の patchday3ng/dlc.rpf を展開",
        "pt": "Extração do patchday3ng/dlc.rpf original",
    },
    "michael.deploy.task_extract_patchday3_rpf": {
        "en": "Extract nested patchday3ng.rpf",
        "ja": "ネストされた patchday3ng.rpf を展開",
        "pt": "Extração de patchday3ng.rpf",
    },
    "michael.deploy.task_pack_patchday3_rpf": {
        "en": "Pack patchday3ng.rpf",
        "ja": "patchday3ng.rpf のパック",
        "pt": "Empacotamento de patchday3ng.rpf",
    },
    "michael.deploy.task_pack_patchday3_dlc": {
        "en": "Pack patchday3ng_dlc.rpf",
        "ja": "patchday3ng_dlc.rpf のパック",
        "pt": "Empacotamento de patchday3ng_dlc.rpf",
    },
    "michael.deploy.task_verify_patchday3_dlc": {
        "en": "Verify patchday3ng_dlc.rpf integrity",
        "ja": "patchday3ng_dlc.rpf 整合性検証",
        "pt": "Verificação de integridade de patchday3ng_dlc.rpf",
    },
    "michael.deploy.done": {
        "en": "[SUCCESS] UNIVERSAL SLOT DEPLOYMENT COMPLETED SUCCESSFULLY!",
        "ja": "[成功] ユニバーサルスロット展開が正常に完了しました！",
        "pt": "[SUCESSO] IMPLANTAÇÃO UNIVERSAL CONCLUÍDA COM ÊXITO!",
    },
    "trevor.run.cli_desc": {
        "en": "Run the complete Miltina Maid (Trevor / player_two) pipeline using paths from vrc2gtav.cfg.",
        "ja": "vrc2gtav.cfg のパスを使って Miltina Maid (Trevor / player_two) の完全パイプラインを実行します。",
        "pt": "Executa o pipeline completo da Miltina Maid (Trevor / player_two) usando os caminhos do arquivo vrc2gtav.cfg.",
    },
    "trevor.run.generating_atlas": {
        "en": "[INFO] Generating Miltina 2K texture atlas...",
        "ja": "[INFO] Miltina 2K テクスチャアトラスを生成中...",
        "pt": "[INFO] Gerando texture atlas 2K da Miltina...",
    },
    "trevor.run.atlas_script_missing": {
        "en": "[ERROR] Atlas script not found: {path}",
        "ja": "[エラー] アトラススクリプトが見つかりません: {path}",
        "pt": "[ERRO] Script de atlas não encontrado: {path}",
    },
    "trevor.run.blender_script_missing": {
        "en": "[ERROR] Blender script not found: {path}",
        "ja": "[エラー] Blender スクリプトが見つかりません: {path}",
        "pt": "[ERRO] Script Blender não encontrado: {path}",
    },
    "trevor.run.running_blender": {
        "en": "[INFO] Running Blender build and renders...",
        "ja": "[INFO] Blender ビルドとレンダーを実行中...",
        "pt": "[INFO] Executando compilação e renderização no Blender...",
    },
    "trevor.run.copied_render": {
        "en": "[OK] Render copied to artifacts: {name}",
        "ja": "[OK] レンダーを artifacts にコピーしました: {name}",
        "pt": "[OK] Renderização copiada para artifacts: {name}",
    },
    "trevor.run.compiled_missing": {
        "en": "[ERROR] Missing compiled files: {ydd} / {ytd}",
        "ja": "[エラー] コンパイル済みファイルが見つかりません: {ydd} / {ytd}",
        "pt": "[ERRO] Arquivos compilados ausentes: {ydd} / {ytd}",
    },
    "trevor.run.rendering_rage": {
        "en": "[INFO] Generating RAGE Engine preview renders...",
        "ja": "[INFO] RAGE Engine プレビューレンダーを生成中...",
        "pt": "[INFO] Gerando pré-visualização de renderização no RAGE...",
    },
    "trevor.run.copied_rage_capture": {
        "en": "[OK] RAGE capture copied to artifacts: {name}",
        "ja": "[OK] RAGE キャプチャを artifacts にコピーしました: {name}",
        "pt": "[OK] Captura RAGE copiada para artifacts: {name}",
    },
    "trevor.run.created_head_crop": {
        "en": "[OK] Generated RAGE face crop: {name}",
        "ja": "[OK] RAGE 顔クローズアップを生成しました: {name}",
        "pt": "[OK] Gerado recorte do rosto RAGE: {name}",
    },
    "trevor.run.applying_slots": {
        "en": "[INFO] Applying Miltina to Trevor character slots...",
        "ja": "[INFO] Miltina を Trevor のスロットに適用中...",
        "pt": "[INFO] Aplicando Miltina aos slots do Trevor...",
    },
    "trevor.run.repacking": {
        "en": "[INFO] Repacking RPFs and installing into GTA V mods directory...",
        "ja": "[INFO] RPF を再パックして GTA V mods ディレクトリにインストール中...",
        "pt": "[INFO] Reempacotando RPFs e instalando no diretório mods do GTA V...",
    },
    "trevor.run.done": {
        "en": "[SUCCESS] Full Miltina pipeline completed successfully.",
        "ja": "[成功] Miltina の全パイプラインが正常に完了しました。",
        "pt": "[SUCESSO] Pipeline completa da Miltina finalizada com sucesso.",
    },
    "trevor.atlas.cli_desc": {
        "en": "Generate the unified 2K (2x2) Texture Atlas and .ytd dictionary for Miltina Maid (Trevor).",
        "ja": "Miltina Maid (Trevor) 用の統合 2K (2x2) テクスチャアトラスと .ytd 辞書を生成します。",
        "pt": "Gera o Texture Atlas 2K (2x2) unificado e o dicionário .ytd para a Miltina Maid (Trevor).",
    },
    "trevor.atlas.face_missing": {
        "en": "[ERROR] Miltina face texture not found: {path}",
        "ja": "[エラー] Miltina の顔テクスチャが見つかりません: {path}",
        "pt": "[ERRO] Textura facial da Miltina não encontrada: {path}",
    },
    "trevor.atlas.loading_dir": {
        "en": "[INFO] Loading source textures from: {path}",
        "ja": "[INFO] ソーステクスチャを読み込み中: {path}",
        "pt": "[INFO] Carregando texturas-fonte de: {path}",
    },
    "trevor.atlas.compositing_eyes": {
        "en": "[INFO] Compositing anime navy-blue irises onto eyes...",
        "ja": "[INFO] アニメ風の紺青の瞳孔を目に合成中...",
        "pt": "[INFO] Compondo íris azul-marinho de anime nos olhos...",
    },
    "trevor.atlas.saved_diffuse": {
        "en": "[OK] Diffuse Atlas saved to: {path}",
        "ja": "[OK] Diffuse アトラスを保存しました: {path}",
        "pt": "[OK] Atlas Diffuse salvo em: {path}",
    },
    "trevor.atlas.saved_spec": {
        "en": "[OK] Specular Atlas saved to: {path}",
        "ja": "[OK] Specular アトラスを保存しました: {path}",
        "pt": "[OK] Atlas Specular salvo em: {path}",
    },
    "trevor.atlas.saved_normal": {
        "en": "[OK] Normal Map Atlas saved to: {path}",
        "ja": "[OK] Normal Map アトラスを保存しました: {path}",
        "pt": "[OK] Atlas Normal Map salvo em: {path}",
    },
    "trevor.atlas.compiling_ytd": {
        "en": "\n[INFO] Compiling .ytd texture dictionary...",
        "ja": "\n[INFO] .ytd テクスチャ辞書をコンパイル中...",
        "pt": "\n[INFO] Compilando dicionário de texturas .ytd...",
    },
    "trevor.atlas.ytd_done": {
        "en": "[SUCCESS] .ytd dictionary generated successfully: {path}",
        "ja": "[成功] .ytd 辞書を正常に生成しました: {path}",
        "pt": "[SUCESSO] Dicionário .ytd gerado com sucesso: {path}",
    },
    "trevor.atlas.failed": {
        "en": "[ERROR] Miltina texture atlas generation failed: {error}",
        "ja": "[エラー] Miltina テクスチャアトラスの生成に失敗しました: {error}",
        "pt": "[ERRO] Falha na geração do atlas de texturas da Miltina: {error}",
    },
    "trevor.apply.cli_desc": {
        "en": "Apply Miltina Maid models, textures, and dummy props to Trevor (player_two) directories.",
        "ja": "Miltina Maid のモデル・テクスチャ・ダミープロップを Trevor (player_two) ディレクトリに適用します。",
        "pt": "Aplica modelos, texturas e props dummy da Miltina Maid nos diretórios do Trevor (player_two).",
    },
    "trevor.apply.patching_dir": {
        "en": "=== Patching {directory} ===",
        "ja": "=== パッチ適用中: {directory} ===",
        "pt": "=== Aplicando patch em {directory} ===",
    },
    "trevor.apply.dir_missing": {
        "en": "Directory not found: {directory}",
        "ja": "ディレクトリが見つかりません: {directory}",
        "pt": "Diretório não encontrado: {directory}",
    },
    "trevor.apply.summary": {
        "en": (
            "Result for {directory}:\n"
            "  Uppr models replaced (Miltina Maid): {uppr}\n"
            "  Uppr textures replaced (Atlas YTD):  {ytd}\n"
            "  Dummy models installed (Empty 629B): {dummy}\n"
            "  Untouched files (metadata/props):    {skipped}"
        ),
        "ja": (
            "結果 ({directory}):\n"
            "  置換済み uppr モデル (Miltina Maid): {uppr}\n"
            "  置換済み uppr テクスチャ (Atlas YTD): {ytd}\n"
            "  導入済みダミーモデル (空 629B):      {dummy}\n"
            "  未変更ファイル (メタデータ/プロップ): {skipped}"
        ),
        "pt": (
            "Resultado para {directory}:\n"
            "  Modelos uppr substituídos (Miltina Maid): {uppr}\n"
            "  Texturas uppr substituídas (Atlas YTD):   {ytd}\n"
            "  Modelos dummy instalados (vazio 629B):    {dummy}\n"
            "  Arquivos preservados (metadados/props):   {skipped}"
        ),
    },
    "trevor.apply.dummy_missing": {
        "en": "Dummy YDD not found at {path}",
        "ja": "ダミー YDD が見つかりません: {path}",
        "pt": "Arquivo dummy YDD não encontrado em {path}",
    },
    "trevor.apply.prop_dummy_missing": {
        "en": "Prop Dummy YDD not found at {path}",
        "ja": "プロップダミー YDD が見つかりません: {path}",
        "pt": "Arquivo prop dummy YDD não encontrado em {path}",
    },
    "trevor.apply.model_missing": {
        "en": "Miltina model not found at {path}",
        "ja": "Miltina モデルが見つかりません: {path}",
        "pt": "Modelo da Miltina não encontrado em {path}",
    },
    "trevor.apply.ytd_missing": {
        "en": "Miltina texture not found at {path}",
        "ja": "Miltina テクスチャが見つかりません: {path}",
        "pt": "Textura da Miltina não encontrada em {path}",
    },
    "trevor.apply.done": {
        "en": "\nAll target directories successfully patched.",
        "ja": "\nすべての対象ディレクトリへのパッチ適用が完了しました。",
        "pt": "\nTodos os diretórios de destino foram atualizados com sucesso.",
    },
    "trevor.build.cli_desc": {
        "en": "Miltina Maid to GTA V Trevor (player_two) Blender compiler",
        "ja": "GTA V Trevor (player_two) 用 Miltina Maid Blender コンパイラ",
        "pt": "Compilador Blender da Miltina Maid para o Trevor (player_two) no GTA V",
    },
    "trevor.build.importing_skeleton": {
        "en": "[INFO] Importing Trevor base skeleton: {path}",
        "ja": "[INFO] Trevor ベーススケルトンをインポート中: {path}",
        "pt": "[INFO] Importando esqueleto base do Trevor: {path}",
    },
    "trevor.build.found_armature": {
        "en": "[INFO] Found ped armature: {name}",
        "ja": "[INFO] Ped アーマチュアを検出: {name}",
        "pt": "[INFO] Armature do ped encontrada: {name}",
    },
    "trevor.build.filtered_bones": {
        "en": "[INFO] Filtered ped armature bones to: {count}",
        "ja": "[INFO] Ped アーマチュアのボーンを {count} 本にフィルタリングしました",
        "pt": "[INFO] Ossos da armature do ped filtrados para: {count}",
    },
    "trevor.build.importing_fbx": {
        "en": "[INFO] Importing Miltina model: {path}",
        "ja": "[INFO] Miltina モデルをインポート中: {path}",
        "pt": "[INFO] Importando modelo da Miltina: {path}",
    },
    "trevor.build.imported_vrc_armature": {
        "en": "[INFO] Imported VRC armature: {name}",
        "ja": "[INFO] VRC アーマチュアをインポートしました: {name}",
        "pt": "[INFO] Armature VRC importada: {name}",
    },
    "trevor.build.retained_meshes": {
        "en": "[INFO] Retained {count} active maid meshes.",
        "ja": "[INFO] 有効なメイドメッシュ {count} 個を保持しました。",
        "pt": "[INFO] Mantidas {count} malhas ativas da Miltina Maid.",
    },
    "trevor.build.jaw_mapped": {
        "en": "[OK] Mapped {count} vertices to FACIAL_jaw on Body for lip sync.",
        "ja": "[OK] リップシンク用に Body の {count} 頂点を FACIAL_jaw にマッピングしました。",
        "pt": "[OK] Mapeados {count} vértices para FACIAL_jaw no Body para sincronização labial.",
    },
    "trevor.build.baking_face": {
        "en": "[INFO] Baking exact adult facial expression into 'Body'...",
        "ja": "[INFO] 成人表情シェイプキーを 'Body' にベイク中...",
        "pt": "[INFO] Assando expressão facial adulta exata em 'Body'...",
    },
    "trevor.build.face_baked": {
        "en": "[SUCCESS] Face mesh baked cleanly with exact adult expression.",
        "ja": "[成功] 顔メッシュに成人表情をクリーンにベイクしました。",
        "pt": "[SUCESSO] Malha facial assada perfeitamente com a expressão adulta exata.",
    },
    "trevor.build.removed_decal_faces": {
        "en": "[OK] Removed {count} transparent decal faces from Face mesh.",
        "ja": "[OK] 顔メッシュから透明デカール面 {count} 個を削除しました。",
        "pt": "[OK] Removidas {count} faces de decalque transparente da malha facial.",
    },
    "trevor.build.baking_clothing": {
        "en": "[INFO] Baking anti-clipping blendshapes across all costume components...",
        "ja": "[INFO] 全衣装パーツにクリッピング防止シェイプキーをベイク中...",
        "pt": "[INFO] Assando blendshapes anticolisão em todos os componentes do traje...",
    },
    "trevor.build.clothing_baked": {
        "en": "[SUCCESS] All costume and body blendshapes baked cleanly with neck and arms preserved.",
        "ja": "[成功] 首・腕を 100% 保持したまま全衣装とボディのシェイプキーをベイクしました。",
        "pt": "[SUCESSO] Todos os blendshapes do corpo e traje assados preservando pescoço e braços.",
    },
    "trevor.build.rotating_arms": {
        "en": "[INFO] Rotating VRC armature arms from T-pose to GTA V A-pose (-55 degrees)...",
        "ja": "[INFO] VRC アーマチュアの腕を T-pose から GTA V A-pose (-55度) へ回転中...",
        "pt": "[INFO] Rotacionando braços da armature VRC de T-pose para A-pose do GTA V (-55 graus)...",
    },
    "trevor.build.arms_rotated": {
        "en": "[SUCCESS] Applied -55 degree A-pose rotation to all mesh geometries.",
        "ja": "[成功] 全メッシュジオメトリに -55 度 A-pose 回転を適用しました。",
        "pt": "[SUCESSO] Rotação A-pose de -55 graus aplicada em todas as geometrias.",
    },
    "trevor.build.scale_info": {
        "en": "[INFO] Bone-matched scale: {scale:.4f}, z_offset: {offset:.4f}",
        "ja": "[INFO] ボーン一致スケール: {scale:.4f}, Z オフセット: {offset:.4f}",
        "pt": "[INFO] Escala alinhada ao esqueleto: {scale:.4f}, deslocamento Z: {offset:.4f}",
    },
    "trevor.build.remapping_uvs": {
        "en": "[INFO] Remapping UV coordinates into 2x2 quadrant atlas...",
        "ja": "[INFO] UV 座標を 2x2 象限アトラスへ再マッピング中...",
        "pt": "[INFO] Remapeando coordenadas UV para o atlas de quadrantes 2x2...",
    },
    "trevor.build.retargeting_bones": {
        "en": "[INFO] Retargeting vertex groups to GTA V skeleton...",
        "ja": "[INFO] 頂点グループを GTA V スケルトンへリターゲット中...",
        "pt": "[INFO] Redirecionando grupos de vértices para o esqueleto do GTA V...",
    },
    "trevor.build.preserving_body_groups": {
        "en": "[INFO] Preserving Body vertex groups: FACIAL_jaw & SKEL_Head calibrated ({count} verts).",
        "ja": "[INFO] Body 頂点グループを保持: FACIAL_jaw & SKEL_Head 調整済み ({count} 頂点)。",
        "pt": "[INFO] Preservando grupos de vértices de Body: FACIAL_jaw e SKEL_Head calibrados ({count} vértices).",
    },
    "trevor.build.joined_mesh": {
        "en": "[SUCCESS] Joined meshes into: {name} with {count} vertices.",
        "ja": "[成功] メッシュを結合しました: {name} ({count} 頂点)。",
        "pt": "[SUCESSO] Malhas unidas em: {name} com {count} vértices.",
    },
    "trevor.build.verified_jaw": {
        "en": "[VERIFIED] Unified object has {count} vertices on FACIAL_jaw for lip sync.",
        "ja": "[検証済み] 統合オブジェクトの FACIAL_jaw にリップシンク用 {count} 頂点を確認しました。",
        "pt": "[VERIFICADO] Objeto unificado possui {count} vértices em FACIAL_jaw para sincronização labial.",
    },
    "trevor.build.missing_jaw": {
        "en": "[WARNING] FACIAL_jaw vertex group missing on unified object!",
        "ja": "[警告] 統合オブジェクトに FACIAL_jaw 頂点グループがありません！",
        "pt": "[AVISO] Grupo de vértices FACIAL_jaw ausente no objeto unificado!",
    },
    "trevor.build.consolidated_groups": {
        "en": "[INFO] Consolidated vertex groups count: {count}",
        "ja": "[INFO] 統合後の頂点グループ数: {count}",
        "pt": "[INFO] Quantidade consolidada de grupos de vértices: {count}",
    },
    "trevor.build.bones_relocated": {
        "en": "[OK] Relocated {count} arm/hand/finger bones on Trevor armature.",
        "ja": "[OK] Trevor アーマチュア上の {count} 個の腕・手・指ボーンを再配置しました。",
        "pt": "[OK] {count} ossos de braço/mão/dedos realocados na armature do Trevor.",
    },
    "trevor.build.splitting_material": {
        "en": "[INFO] Splitting material '{name}' ({count} polygons) into {chunks} geometry chunks...",
        "ja": "[INFO] マテリアル '{name}' ({count} ポリゴン) を {chunks} 個のチャンクに分割中...",
        "pt": "[INFO] Dividindo material '{name}' ({count} polígonos) em {chunks} blocos de geometria...",
    },
    "trevor.build.rendering_blender": {
        "en": "[INFO] Rendering Blender preview pictures...",
        "ja": "[INFO] Blender プレビュー画像をレンダリング中...",
        "pt": "[INFO] Renderizando imagens de pré-visualização no Blender...",
    },
    "trevor.build.rendered_face": {
        "en": "[OK] Rendered Face: {path}",
        "ja": "[OK] 顔レンダー保存: {path}",
        "pt": "[OK] Rosto renderizado: {path}",
    },
    "trevor.build.rendered_full": {
        "en": "[OK] Rendered Full Body: {path}",
        "ja": "[OK] 全身レンダー保存: {path}",
        "pt": "[OK] Corpo inteiro renderizado: {path}",
    },
    "trevor.build.mounting_hierarchy": {
        "en": "[INFO] Mounting Sollumz Drawable Dictionary hierarchy...",
        "ja": "[INFO] Sollumz Drawable Dictionary 階層を構築中...",
        "pt": "[INFO] Montando hierarquia de Drawable Dictionary do Sollumz...",
    },
    "trevor.build.exported_ydd": {
        "en": "[INFO] Exported {name}.ydd -> {status}",
        "ja": "[INFO] {name}.ydd をエクスポート -> {status}",
        "pt": "[INFO] Exportado {name}.ydd -> {status}",
    },
    "trevor.build.exported_yft": {
        "en": "[OK] Exported .yft skeleton to {path} ({updated}/{total} bones, max error={delta:.6f} m)",
        "ja": "[OK] .yft スケルトンを {path} にエクスポート ({updated}/{total} ボーン、最大誤差={delta:.6f} m)",
        "pt": "[OK] Esqueleto .yft exportado em {path} ({updated}/{total} ossos, erro máx={delta:.6f} m)",
    },
    "trevor.build.done": {
        "en": "[COMPLETE] Miltina Maid export pipeline completed successfully.",
        "ja": "[完了] Miltina Maid エクスポートパイプラインが正常に完了しました。",
        "pt": "[CONCLUÍDO] Pipeline de exportação da Miltina Maid concluído com sucesso.",
    },
    "tests.cli_desc": {
        "en": "Automated validation suite for the vrc2gtav project",
        "ja": "vrc2gtav プロジェクトの自動検証テストスイート",
        "pt": "Suíte de testes automatizados do projeto vrc2gtav",
    },
}
