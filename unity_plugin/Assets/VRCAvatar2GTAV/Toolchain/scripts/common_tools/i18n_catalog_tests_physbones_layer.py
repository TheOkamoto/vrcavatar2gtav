"""
i18n_catalog_tests_physbones_layer.py
=====================================
Layer 3 of 3 for the VRC2GTAV trilingual translation catalog.

Contains VRChat PhysBones, natural eye blink, universal NPC/avatar
orchestration, and automated validation suite strings.
"""

from typing import Dict


# Ordered subset of the trilingual ("en", "ja", "pt") catalog consumed by
# vrc2gtav_i18n.py to keep catalog files concise and maintainable.
TESTS_PHYSBONES_TRANSLATION_CATALOG: Dict[str, Dict[str, str]] = {
    "tests.arg_source_only": {
        "en": "Validate Python syntax, templates, dummies, i18n, and mirrors before First-Run setup",
        "ja": "First-Run セットアップ前の Python 構文・テンプレート・ダミー・i18n・ミラー同期を検証",
        "pt": "Valida sintaxe Python, modelos, dummies, i18n e espelhos antes da configuração inicial",
    },
    "tests.status_pass": {
        "en": "[PASS]",
        "ja": "[合格]",
        "pt": "[PASSOU]",
    },
    "tests.status_fail": {
        "en": "[FAIL]",
        "ja": "[失敗]",
        "pt": "[FALHOU]",
    },
    "tests.sec1_title": {
        "en": "\n[TEST 1] Python Syntax and Compilation Check",
        "ja": "\n[テスト 1] Python 構文およびコンパイル検証",
        "pt": "\n[TESTE 1] Verificação de Sintaxe e Compilação Python",
    },
    "tests.sec2_title": {
        "en": "\n[TEST 2] Dynamic Path Resolution via vrc2gtav.cfg",
        "ja": "\n[テスト 2] vrc2gtav.cfg による動的パス解決",
        "pt": "\n[TESTE 2] Resolução Dinâmica de Caminhos via vrc2gtav.cfg",
    },
    "tests.cfg_central": {
        "en": "Central .cfg file",
        "ja": "中央設定ファイル (.cfg)",
        "pt": "Arquivo Central .cfg",
    },
    "tests.project_root": {
        "en": "Project root",
        "ja": "プロジェクトルート",
        "pt": "Raiz do Projeto",
    },
    "tests.staging_dir": {
        "en": "Staging directory",
        "ja": "ステージングディレクトリ",
        "pt": "Diretório Staging",
    },
    "tests.blender_exe": {
        "en": "Blender executable",
        "ja": "Blender 実行ファイル",
        "pt": "Executável Blender",
    },
    "tests.python_exe": {
        "en": "Python executable",
        "ja": "Python 実行ファイル",
        "pt": "Executável Python",
    },
    "tests.rage_cli": {
        "en": "RAGE CLI tool",
        "ja": "RAGE CLI ツール",
        "pt": "Ferramenta RAGE CLI",
    },
    "tests.unity_assets": {
        "en": "Unity Assets directory",
        "ja": "Unity アセットディレクトリ",
        "pt": "Diretório de Assets Unity",
    },
    "tests.sec3_title": {
        "en": "\n[TEST 3] Dummy Mesh Integrity (head_000_r.ydd and p_eyes_dummy.ydd)",
        "ja": "\n[テスト 3] ダミーメッシュ整合性 (head_000_r.ydd および p_eyes_dummy.ydd)",
        "pt": "\n[TESTE 3] Integridade das Dummy Meshes (head_000_r.ydd e p_eyes_dummy.ydd)",
    },
    "tests.file_not_found": {
        "en": "File not found!",
        "ja": "ファイルが見つかりません！",
        "pt": "Arquivo não encontrado!",
    },
    "tests.byte_size": {
        "en": "Size: {actual} bytes (expected: {expected} bytes)",
        "ja": "サイズ: {actual} バイト (期待値: {expected} バイト)",
        "pt": "Tamanho: {actual} bytes (esperado: {expected} bytes)",
    },
    "tests.sec4_title": {
        "en": "\n[TEST 4] Compiled Drawables and Texture Dictionaries Check (.cfg)",
        "ja": "\n[テスト 4] コンパイル済みモデルおよびテクスチャ辞書検証 (.cfg)",
        "pt": "\n[TESTE 4] Verificação dos Modelos e Dicionários de Texturas (.cfg)",
    },
    "tests.asset_detail": {
        "en": "{size:.2f} MB in {parent}",
        "ja": "{parent} 内に {size:.2f} MB",
        "pt": "{size:.2f} MB em {parent}",
    },
    "tests.sec5_title": {
        "en": "\n[TEST 5] OPEN Encryption Signature on Deployed GTA V RPFs",
        "ja": "\n[テスト 5] 展開済み GTA V RPF の OPEN 暗号化署名チェック",
        "pt": "\n[TESTE 5] Assinatura OPEN nos RPFs Implantados no GTA V",
    },
    "tests.mods_inaccessible": {
        "en": "  [WARN] GTA V mods directory is not accessible in this environment. Skipping test.",
        "ja": "  [警告] この環境から GTA V mods ディレクトリにアクセスできません。テストをスキップします。",
        "pt": "  [AVISO] Diretório de mods do GTA V não acessível neste ambiente. Pulando teste.",
    },
    "tests.missing_folder": {
        "en": "{character}: missing directory",
        "ja": "{character}: ディレクトリ不在",
        "pt": "{character}: pasta ausente",
    },
    "tests.no_glasses": {
        "en": "{character}: no p_*.ydd found",
        "ja": "{character}: p_*.ydd なし",
        "pt": "{character}: nenhum p_*.ydd encontrado",
    },
    "tests.glasses_label": {
        "en": "Head/eye/ear prop dummies (streamedpedprops)",
        "ja": "頭・眼鏡・耳プロップダミー (streamedpedprops)",
        "pt": "Dummies de props cabeça/óculos/orelha (streamedpedprops)",
    },
    "tests.glasses_ok": {
        "en": "{count}/119 p_*.ydd identical to p_eyes_dummy.ydd",
        "ja": "{count}/119 個の p_*.ydd が p_eyes_dummy.ydd と一致",
        "pt": "{count}/119 p_*.ydd idênticos a p_eyes_dummy.ydd",
    },
    "tests.mismatches": {
        "en": "Mismatches: {items}",
        "ja": "不一致: {items}",
        "pt": "Divergências: {items}",
    },
    "tests.yft_missing": {
        "en": "{name} (missing)",
        "ja": "{name} (不在)",
        "pt": "{name} (ausente)",
    },
    "tests.yft_stale": {
        "en": "{name} (outdated)",
        "ja": "{name} (古いファイル)",
        "pt": "{name} (desatualizado)",
    },
    "tests.yft_label": {
        "en": "Hand/finger .yft skeletons in staging (streamedpeds)",
        "ja": "ステージング内 手/指 .yft スケルトン (streamedpeds)",
        "pt": "Esqueletos .yft de mãos/dedos em staging (streamedpeds)",
    },
    "tests.yft_ok": {
        "en": "player_zero/one/two.yft synchronized",
        "ja": "player_zero/one/two.yft 同期済み",
        "pt": "player_zero/one/two.yft sincronizados",
    },
    "tests.sec6_title": {
        "en": "\n[TEST 6] Code Quality, AST Identifiers, and Mirror Synchronization",
        "ja": "\n[テスト 6] コード品質・AST 識別子・ミラー同期チェック",
        "pt": "\n[TESTE 6] Qualidade de Código, Identificadores AST e Sincronização de Espelhos",
    },
    "tests.sec_first_run_ma_title": {
        "en": "\n[TEST 8] First-Run Archive/Unity, Modular Avatar Bake, Face/Body Blendshapes & Error Handling",
        "ja": "\n[テスト 8] First-Run 書庫/Unity・Modular Avatar ベイク・顔/体シェイプキー・エラー処理",
        "pt": "\n[TESTE 8] First-Run Arquivo/Unity, Bake Modular Avatar, Blendshapes Rosto/Corpo e Erros",
    },
    "tests.no_emojis": {
        "en": "No emojis: {name}",
        "ja": "絵文字なし: {name}",
        "pt": "Sem emojis: {name}",
    },
    "tests.vars_min_len": {
        "en": "Identifiers & underscore segments >= 3 chars: {path}",
        "ja": "識別子・アンダースコア区切り >= 3 文字: {path}",
        "pt": "Identificadores e segmentos com '_' >= 3 caracteres: {path}",
    },
    "tests.found_short_vars": {
        "en": "Found: {items}",
        "ja": "検出: {items}",
        "pt": "Encontrados: {items}",
    },
    "tests.ast_emoji_scan": {
        "en": "AST/Emoji scan",
        "ja": "AST・絵文字スキャン",
        "pt": "Escaneamento AST/Emoji",
    },
    "tests.ast_emoji_detail": {
        "en": "{count} Python files analyzed",
        "ja": "{count} 個の Python ファイルを解析済み",
        "pt": "{count} arquivos Python analisados",
    },
    "tests.mirror_desync": {
        "en": "Out-of-sync mirror: {mirror}",
        "ja": "ミラー非同期: {mirror}",
        "pt": "Espelho dessincronizado: {mirror}",
    },
    "tests.must_match": {
        "en": "must match {primary}",
        "ja": "{primary} と一致する必要があります",
        "pt": "deve igualar {primary}",
    },
    "tests.mirror_sync_label": {
        "en": "Mirror synchronization",
        "ja": "ミラー同期",
        "pt": "Sincronização de Espelhos",
    },
    "tests.mirror_sync_detail": {
        "en": "{count} pairs verified",
        "ja": "{count} ペア検証済み",
        "pt": "{count} pares verificados",
    },
    "tests.sec_i18n_title": {
        "en": "\n[TEST I18N] Trilingual Translation Catalog Validation",
        "ja": "\n[テスト I18N] 3か国語翻訳カタログ検証",
        "pt": "\n[TESTE I18N] Validação do Catálogo Trilíngue de Traduções",
    },
    "tests.i18n_catalog_label": {
        "en": "Translation catalog completeness (en/ja/pt)",
        "ja": "翻訳カタログ完全性 (en/ja/pt)",
        "pt": "Completude do catálogo de traduções (en/ja/pt)",
    },
    "tests.i18n_catalog_ok": {
        "en": "{count} message keys validated across {langs} languages",
        "ja": "{count} 個のメッセージキーを {langs} 言語で検証済み",
        "pt": "{count} chaves de mensagem validadas em {langs} idiomas",
    },
    "tests.i18n_issues": {
        "en": "Issues ({total}): {sample}",
        "ja": "問題 ({total} 件): {sample}",
        "pt": "Problemas ({total}): {sample}",
    },
    "tests.sec_template_title": {
        "en": "\n[TEST TEMPLATE] Templates and Anti-Copyright Policy",
        "ja": "\n[テンプレート検証] テンプレートと著作権保護ポリシー",
        "pt": "\n[TESTE MODELO] Modelos e Política Anticopyright",
    },
    "tests.gitignore_rules": {
        "en": ".gitignore copyright rules",
        "ja": ".gitignore 著作権ルール",
        "pt": "Regras de copyright do .gitignore",
    },
    "tests.gitignore_detail": {
        "en": "*.yft / *.ydd / vrc2gtav.cfg present",
        "ja": "*.yft / *.ydd / vrc2gtav.cfg 記載済み",
        "pt": "*.yft / *.ydd / vrc2gtav.cfg presentes",
    },
    "tests.dummies_label": {
        "en": "Technical dummies in _deploy_tools/",
        "ja": "_deploy_tools/ 内の技術用ダミー",
        "pt": "Dummies técnicas em _deploy_tools/",
    },
    "tests.dummies_detail": {
        "en": "head_000_r.ydd and p_eyes_dummy.ydd present",
        "ja": "head_000_r.ydd と p_eyes_dummy.ydd が存在",
        "pt": "head_000_r.ydd e p_eyes_dummy.ydd presentes",
    },
    "tests.source_banner": {
        "en": "CLEAN REPOSITORY VALIDATION SUITE (SOURCE-ONLY)",
        "ja": "クリーンリポジトリ検証スイート (SOURCE-ONLY)",
        "pt": "SUÍTE DE VALIDAÇÃO DE REPOSITÓRIO LIMPO (SOURCE-ONLY)",
    },
    "tests.source_result": {
        "en": "\nSource-Only Result: {passed}/{total} suites passed.",
        "ja": "\nSource-Only 結果: {passed}/{total} スイート合格。",
        "pt": "\nResultado Source-Only: {passed}/{total} suítes aprovadas.",
    },
    "tests.full_banner": {
        "en": "STARTING FULL VRC2GTAV PROJECT VALIDATION SUITE",
        "ja": "VRC2GTAV プロジェクト総合検証スイートを開始します",
        "pt": "INICIANDO SUÍTE DE VALIDAÇÃO INTEGRAL DO PROJETO VRC2GTAV",
    },
    "tests.summary_header": {
        "en": "                    FINAL TEST SUMMARY",
        "ja": "                    最終テストサマリー",
        "pt": "                    RESUMO FINAL DOS TESTES",
    },
    "tests.suite_passed": {
        "en": "[PASSED]",
        "ja": "[合格]",
        "pt": "[APROVADO]",
    },
    "tests.suite_failed": {
        "en": "[FAILED]",
        "ja": "[不合格]",
        "pt": "[REPROVADO]",
    },
    "tests.full_result": {
        "en": "\nOverall Result: {passed}/{total} suites passed.",
        "ja": "\n総合結果: {passed}/{total} スイート合格。",
        "pt": "\nResultado Geral: {passed}/{total} suítes aprovadas.",
    },
    "tests.suite_syntax": {
        "en": "Python Syntax",
        "ja": "Python 構文",
        "pt": "Sintaxe Python",
    },
    "tests.suite_templates": {
        "en": "Templates and Dummies",
        "ja": "テンプレートとダミー",
        "pt": "Modelos e Dummies",
    },
    "tests.suite_i18n": {
        "en": "Trilingual Catalog (i18n)",
        "ja": "3か国語カタログ (i18n)",
        "pt": "Catálogo Trilíngue (i18n)",
    },
    "tests.suite_quality": {
        "en": "Code Quality and Mirrors",
        "ja": "コード品質とミラー同期",
        "pt": "Qualidade e Espelhos",
    },
    "tests.suite_first_run_ma": {
        "en": "First-Run, Modular Avatar & Error Handling",
        "ja": "First-Run・Modular Avatar・エラー処理",
        "pt": "First-Run, Modular Avatar e Tratamento de Erros",
    },
    "tests.suite_paths": {
        "en": "Path Resolution",
        "ja": "パス解決",
        "pt": "Resolução de Caminhos",
    },
    "tests.suite_dummies": {
        "en": "Dummy Mesh Integrity",
        "ja": "ダミーメッシュ整合性",
        "pt": "Integridade da Dummy Mesh",
    },
    "tests.suite_models": {
        "en": "Compiled Models and Textures",
        "ja": "モデルとテクスチャ辞書",
        "pt": "Modelos e Dicionários de Texturas",
    },
    "tests.suite_rpf": {
        "en": "Deployed RPF Headers",
        "ja": "展開済み RPF ヘッダー",
        "pt": "Cabeçalhos RPF Implantados",
    },
    "tests.suite_unity": {
        "en": "Unity Scene Scales and Hair Fallback",
        "ja": "Unity シーンのスケール抽出とデフォルト髪フォールバック",
        "pt": "Escalas Unity e Fallback de Cabelo Padrão",
    },
    "tests.unity_empty_unit_scales": {
        "en": "Empty/missing .unity defaults to 1.0 scales",
        "ja": "未指定・欠損 .unity での 1.0 スケール既定値",
        "pt": ".unity vazio/ausente usa escalas padrão 1.0",
    },
    "tests.unity_extracts_scene_scales": {
        "en": "Synthetic .unity extracts !u!4, !u!1001, and PB cancellation",
        "ja": "疑似 .unity からの !u!4 / !u!1001 スケール抽出と PB 相殺",
        "pt": ".unity sintético extrai !u!4, !u!1001 e cancelamento PB",
    },
    "tests.unity_hair_fallback_mode": {
        "en": "Hair resolver defaults cleanly when custom hair is absent",
        "ja": "カスタム髪不在時のデフォルト髪自動フォールバック",
        "pt": "Resolvedor de cabelo volta ao padrão quando o customizado falta",
    },
    "tests.texture_fallback_ready": {
        "en": "Texture calibration degrades cleanly without optional packs",
        "ja": "オプション素材不在時のテクスチャ補正フォールバック",
        "pt": "Calibração de textura faz fallback seguro sem pacotes opcionais",
    },
    "unity_scene.loaded": {
        "en": "[Unity] Loaded scales from {scene} (avatar='{avatar}', root={root}, armature={armature}, bones={count})",
        "ja": "[Unity] {scene} からスケールを読み込み (avatar='{avatar}', root={root}, armature={armature}, bones={count})",
        "pt": "[Unity] Escalas carregadas de {scene} (avatar='{avatar}', root={root}, armadura={armature}, ossos={count})",
    },
    "unity_scene.default_unit_scales": {
        "en": "[Unity] No custom .unity scale overrides active; using unit body scales (1.0)",
        "ja": "[Unity] カスタム .unity スケール上書きなし。全ボディスケール 1.0 を使用します",
        "pt": "[Unity] Nenhuma escala customizada de .unity ativa; usando escalas corporais padrão (1.0)",
    },
    "unity_scene.applied_bones": {
        "en": "[Unity] Applied {count} pose bone scale override(s) from scene",
        "ja": "[Unity] シーンから {count} 個のボーンポーズスケール上書きを適用しました",
        "pt": "[Unity] Aplicado(s) {count} ajuste(s) de escala em ossos a partir da cena",
    },
    "unity_scene.hair_fallback_default": {
        "en": "[Hair] Using base avatar default hair ({reason})",
        "ja": "[Hair] アバター標準のデフォルト髪を使用します ({reason})",
        "pt": "[Cabelo] Usando cabelo padrão do avatar base ({reason})",
    },
    "unity_scene.hair_custom_active": {
        "en": "[Hair] Using custom hair FBX ({reason}): {path}",
        "ja": "[Hair] カスタム髪 FBX を使用します ({reason}): {path}",
        "pt": "[Cabelo] Usando FBX de cabelo customizado ({reason}): {path}",
    },
    "setup.unity_scene_detected": {
        "en": "Detected optional Unity scene for {char}: {path}",
        "ja": "{char} 用のオプション Unity シーンを検出しました: {path}",
        "pt": "Cena Unity opcional detectada para {char}: {path}",
    },
    "setup.unity_scene_optional": {
        "en": "No Unity scene configured for {char}; default 1.0 body scales will be used.",
        "ja": "{char} 用の Unity シーン未設定のため標準 1.0 ボディスケールを使用します。",
        "pt": "Nenhuma cena Unity configurada para {char}; escalas corporais padrão 1.0 serão usadas.",
    },
    "setup.blendshapes_cfg_ready": {
        "en": "[OK] Blendshape preset for {char} ready: {path}",
        "ja": "[OK] {char} 用のブレンドシェイプ設定ファイルを確認しました: {path}",
        "pt": "[OK] Predefinição de blendshapes para {char} pronta: {path}",
    },
    "setup.blendshapes_cfg_exported": {
        "en": "[OK] Exported Unity blendshapes for {char} -> {path}",
        "ja": "[OK] Unity から {char} のブレンドシェイプを書き出しました -> {path}",
        "pt": "[OK] Blendshapes do Unity exportados para {char} -> {path}",
    },
    "setup.blendshapes_cfg_missing": {
        "en": "[WARNING] No blendshape .cfg or Unity scene found for {char}: {path}",
        "ja": "[警告] {char} 用のブレンドシェイプ .cfg も Unity シーンも見つかりません: {path}",
        "pt": "[AVISO] Nenhum arquivo .cfg de blendshapes ou cena Unity encontrado para {char}: {path}",
    },
    "blendshapes.loaded_source": {
        "en": "[INFO] Blendshapes resolved via '{source}': {meshes} mesh(es), {weights} weight(s) ({detail})",
        "ja": "[情報] '{source}' からブレンドシェイプを読み込みました: {meshes} メッシュ / {weights} ウェイト ({detail})",
        "pt": "[INFO] Blendshapes carregados via '{source}': {meshes} malha(s), {weights} peso(s) ({detail})",
    },
    "blendshapes.saved_cfg": {
        "en": "[OK] Saved blendshape preset file: {path}",
        "ja": "[OK] ブレンドシェイプ設定ファイルを保存しました: {path}",
        "pt": "[OK] Arquivo .cfg de blendshapes salvo: {path}",
    },
    "blendshapes.applied_scene": {
        "en": "[INFO] Applied blendshape presets to {meshes} Blender mesh(es) ({slots} key slots updated).",
        "ja": "[情報] {meshes} 個の Blender メッシュにブレンドシェイプを適用しました ({slots} スロット更新)。",
        "pt": "[INFO] Predefinições de blendshapes aplicadas em {meshes} malha(s) no Blender ({slots} chaves atualizadas).",
    },
    "blendshapes.cli_cfg": {
        "en": "Path to a blendshapes .cfg preset file",
        "ja": "ブレンドシェイプ .cfg プリセットファイルへのパス",
        "pt": "Caminho para o arquivo de predefinição .cfg de blendshapes",
    },
    "blendshapes.cli_source": {
        "en": "Blendshape source priority: auto, unity, or cfg",
        "ja": "ブレンドシェイプの取得元優先順: auto, unity, または cfg",
        "pt": "Origem prioritária dos blendshapes: auto, unity ou cfg",
    },
    "blendshapes.cli_save_cfg": {
        "en": "Save resolved blendshape weights to this .cfg preset file",
        "ja": "解決済みブレンドシェイプウェイトをこの .cfg ファイルに保存",
        "pt": "Salvar os blendshapes resolvidos neste arquivo .cfg",
    },
    "blendshapes.cli_face_anim": {
        "en": "Optional Unity facial .anim file override",
        "ja": "オプションの Unity 表情 .anim ファイル上書き",
        "pt": "Sobrescrita opcional do arquivo .anim facial do Unity",
    },
    "manager.cli_export_blendshapes": {
        "en": "Export and sync all FBX/Unity avatar blendshapes into configs/*_blendshapes.cfg",
        "ja": "FBX/Unity の全ブレンドシェイプを configs/*_blendshapes.cfg へ書き出し・同期する",
        "pt": "Exportar e sincronizar todos os blendshapes dos FBX/Unity para configs/*_blendshapes.cfg",
    },
    "manager.cli_overwrite_from_unity": {
        "en": "When exporting blendshapes, reload active weights from Unity instead of preserving existing .cfg edits",
        "ja": "ブレンドシェイプ書き出し時に既存 .cfg 編集を保持せず Unity シーンの値を再読み込みする",
        "pt": "Ao exportar blendshapes, recarregar pesos ativos da cena Unity em vez de manter edições do .cfg",
    },
    "manager.export_blendshapes_ok": {
        "en": "[OK] Exported blendshapes for {char}: {path}",
        "ja": "[OK] {char} のブレンドシェイプを書き出しました: {path}",
        "pt": "[OK] Blendshapes exportados para {char}: {path}",
    },
    "manager.export_blendshapes_skipped": {
        "en": "[WARNING] Skipped {char}: no Unity scene, .cfg, or FBX blendshapes found.",
        "ja": "[警告] {char} をスキップしました: Unity シーン・.cfg・FBX ブレンドシェイプが見つかりません。",
        "pt": "[AVISO] {char} ignorado: nenhuma cena Unity, .cfg ou blendshape FBX encontrado.",
    },
    "tests.blendshapes_cfg_presets": {
        "en": "Tracked configs/*_blendshapes.cfg & UTF-8 round-trip serialization",
        "ja": "configs/*_blendshapes.cfg プリセット群と UTF-8 ラウンドトリップ読込/保存",
        "pt": "Presets configs/*_blendshapes.cfg e leitura/gravação UTF-8",
    },
    "tests.blendshapes_unity_extract": {
        "en": "Unity scene + nested prefab blendshape weight extraction",
        "ja": "Unity シーンおよびネスト Prefab からのブレンドシェイプウェイト抽出",
        "pt": "Extração de pesos de blendshapes de cena Unity e Prefab aninhado",
    },
    "tests.blendshapes_resolution_order": {
        "en": "Blendshape source resolution order (auto / unity / cfg)",
        "ja": "ブレンドシェイプ取得元の優先解決順 (auto / unity / cfg)",
        "pt": "Ordem de resolução da origem dos blendshapes (auto / unity / cfg)",
    },
    "protagonist.michael": {
        "en": "Michael De Santa",
        "ja": "マイケル・デ・サンタ",
        "pt": "Michael De Santa",
    },
    "protagonist.franklin": {
        "en": "Franklin Clinton",
        "ja": "フランクリン・クリントン",
        "pt": "Franklin Clinton",
    },
    "protagonist.trevor": {
        "en": "Trevor Philips",
        "ja": "トレバー・フィリップス",
        "pt": "Trevor Philips",
    },
    "avatar.player_one_franklin": {
        "en": "Player One Preset (Franklin)",
        "ja": "Player One プリセット (Franklin)",
        "pt": "Preset Player One (Franklin)",
    },
    "avatar.player_zero_michael": {
        "en": "Player Zero Preset (Michael)",
        "ja": "Player Zero プリセット (Michael)",
        "pt": "Preset Player Zero (Michael)",
    },
    "avatar.player_two_trevor": {
        "en": "Player Two Preset (Trevor)",
        "ja": "Player Two プリセット (Trevor)",
        "pt": "Preset Player Two (Trevor)",
    },
    "paths.unknown_protagonist": {
        "en": "Unknown GTA V protagonist '{name}'. Expected: michael, franklin, or trevor.",
        "ja": "不明な GTA V 主人公 '{name}' です。michael, franklin, trevor を指定してください。",
        "pt": "Protagonista desconhecido do GTA V '{name}'. Esperado: michael, franklin ou trevor.",
    },
    "paths.unknown_avatar": {
        "en": "Unknown VRChat avatar preset '{name}'. Expected: player_one_franklin, player_zero_michael, or player_two_trevor.",
        "ja": "不明な VRChat アバタープリセット '{name}' です。player_one_franklin, player_zero_michael, player_two_trevor を指定してください。",
        "pt": "Preset de avatar VRChat desconhecido '{name}'. Esperado: player_one_franklin, player_zero_michael ou player_two_trevor.",
    },
    "manager.cli_avatar": {
        "en": "VRChat avatar preset to build/apply (player_one_franklin, player_zero_michael, player_two_trevor)",
        "ja": "ビルド/適用する VRChat アバタープリセット (player_one_franklin, player_zero_michael, player_two_trevor)",
        "pt": "Preset de avatar VRChat para compilar/aplicar (player_one_franklin, player_zero_michael, player_two_trevor)",
    },
    "manager.cli_protagonist_avatar": {
        "en": "Override VRChat avatar preset specifically for {protagonist}",
        "ja": "{protagonist} に使用する VRChat アバタープリセットを上書き指定",
        "pt": "Sobrescrever o preset de avatar VRChat especificamente para {protagonist}",
    },
    "manager.cli_save_assignment": {
        "en": "Persist --avatar overrides into vrc2gtav.cfg",
        "ja": "--avatar の割り当て変更を vrc2gtav.cfg に保存",
        "pt": "Salvar as atribuições de --avatar no arquivo vrc2gtav.cfg",
    },
    "manager.swap_header": {
        "en": "SWAP VRCHAT AVATAR ASSIGNMENT",
        "ja": "VRChat アバター割り当ての変更",
        "pt": "TROCAR ATRIBUIÇÃO DE AVATAR VRCHAT",
    },
    "manager.swap_select_protagonist": {
        "en": "Select which GTA V protagonist you want to customize:",
        "ja": "カスタマイズする GTA V の主人公を選択してください:",
        "pt": "Selecione qual protagonista do GTA V deseja personalizar:",
    },
    "manager.swap_select_avatar": {
        "en": "Select which VRChat avatar to assign to {protagonist}:",
        "ja": "{protagonist} に割り当てる VRChat アバターを選択してください:",
        "pt": "Selecione qual avatar VRChat atribuir a {protagonist}:",
    },
    "manager.swap_prompt_choice": {
        "en": "Enter choice [0-3]: ",
        "ja": "番号を入力してください [0-3]: ",
        "pt": "Digite a opção [0-3]: ",
    },
    "manager.swap_saved": {
        "en": "[OK] Assigned '{avatar}' to {protagonist} and saved vrc2gtav.cfg.",
        "ja": "[OK] {protagonist} に '{avatar}' を割り当てて vrc2gtav.cfg に保存しました。",
        "pt": "[OK] Avatar '{avatar}' atribuído a {protagonist} e salvo em vrc2gtav.cfg.",
    },
    "apply.cli_avatar": {
        "en": "Optional VRChat avatar preset override for single-character deployment",
        "ja": "単一キャラクター適用時の VRChat アバタープリセット上書き",
        "pt": "Sobrescrita opcional do preset de avatar VRChat para um único personagem",
    },
    "apply.cli_protagonist_avatar": {
        "en": "Override VRChat avatar preset for {protagonist}",
        "ja": "{protagonist} に適用する VRChat アバタープリセットを上書き",
        "pt": "Sobrescrever preset de avatar VRChat para {protagonist}",
    },
    "tests.suite_interchangeability": {
        "en": "Avatar <-> Protagonist Interchangeability",
        "ja": "アバター <-> 主人公の相互切替テスト",
        "pt": "Intercambiabilidade Avatar <-> Protagonista",
    },
    "tests.interchangeability_config": {
        "en": "All 9 (protagonist x avatar) combinations resolve isolated outputs & skeletons",
        "ja": "全 9 通りの (主人公 x アバター) 組み合わせで独立出力とスケルトンを解決",
        "pt": "Todas as 9 combinações (protagonista x avatar) resolvem saídas e skeletons isolados",
    },
    "tests.interchangeability_presets": {
        "en": "Blendshape/Unity preset hints follow active avatar across protagonist swaps",
        "ja": "主人公切替時もブレンドシェイプ/Unity プリセットが選択アバターに追従",
        "pt": "Presets de blendshape/Unity seguem o avatar ativo ao trocar protagonistas",
    },
    "tests.interchangeability_builders": {
        "en": "Universal builders & mod manager expose --target-character across michael/franklin/trevor",
        "ja": "ユニバーサルビルダーと Mod マネージャーが michael/franklin/trevor 向け --target-character に対応",
        "pt": "Os builders universais e o gerenciador aceitam --target-character para michael/franklin/trevor",
    },
    "common.hair_custom_packed": {
        "en": "[HAIR] Packing custom Unity hair '{source}' ({tiles} tile(s)) into atlas...",
        "ja": "[HAIR] カスタム Unity ヘア '{source}' ({tiles} タイル) をアトラスにパッキング中...",
        "pt": "[HAIR] Empacotando cabelo customizado Unity '{source}' ({tiles} bloco(s)) no atlas...",
    },
    "common.hair_aligned_summary": {
        "en": "[HAIR] Aligned {count} custom hair mesh(es) onto avatar skull.",
        "ja": "[HAIR] カスタムヘアーメッシュ {count} 個をアバター頭部に整列しました。",
        "pt": "[HAIR] {count} malha(s) de cabelo customizado alinhada(s) ao crânio do avatar.",
    },
    "common.hair_none_active": {
        "en": "[HAIR] Hair removed (--hair none); exporting without hair meshes.",
        "ja": "[HAIR] ヘアなし (--hair none); ヘアーメッシュを除外してエクスポートします。",
        "pt": "[HAIR] Sem cabelo (--hair none); exportando avatar sem malhas de cabelo.",
    },
    "common.hair_cli_opt": {
        "en": "Custom Unity hair (.prefab, PrefabVariant, .fbx, auto, default, or none)",
        "ja": "カスタム Unity ヘア指定 (.prefab, PrefabVariant, .fbx, auto, default, none)",
        "pt": "Seletor de cabelo Unity (.prefab, PrefabVariant, .fbx, auto, default ou none)",
    },
    "common.hair_mat_cli_opt": {
        "en": "Optional Unity .mat override for raw FBX custom hair",
        "ja": "FBX ヘア用のオプション Unity .mat 上書きパス",
        "pt": "Caminho opcional de material Unity .mat para cabelo FBX avulso",
    },
    "common.hair_tex_cli_opt": {
        "en": "Optional diffuse texture override for custom hair",
        "ja": "カスタムヘア用のオプション拡散テクスチャ上書きパス",
        "pt": "Caminho opcional de textura difusa para o cabelo customizado",
    },
    "common.hair_scale_cli_opt": {
        "en": "Optional uniform scale multiplier for custom hair alignment",
        "ja": "カスタムヘア整列時のオプション均一スケール倍率",
        "pt": "Multiplicador opcional de escala uniforme para ajuste do cabelo",
    },
    "common.hair_offset_cli_opt": {
        "en": "Optional X,Y,Z Unity offset tweak for custom hair (e.g. 0,0.01,-0.02)",
        "ja": "カスタムヘア用のオプション X,Y,Z オフセット補正 (例: 0,0.01,-0.02)",
        "pt": "Ajuste opcional X,Y,Z em espaço Unity para o cabelo (ex: 0,0.01,-0.02)",
    },
    "common.unity_scene_cli_opt": {
        "en": "Optional Unity .unity scene path override",
        "ja": "オプションの Unity .unity シーンパス上書き",
        "pt": "Caminho opcional de cena Unity (.unity) para sobrescrita",
    },
    "common.unity_avatar_cli_opt": {
        "en": "Optional Unity root GameObject name override",
        "ja": "オプションの Unity ルート GameObject 名上書き",
        "pt": "Nome opcional do GameObject raiz na cena Unity",
    },
    "manager.menu_opt_8": {
        "en": "8. Configure custom Unity hair (.prefab / .fbx / auto)",
        "ja": "8. カスタム Unity ヘアを設定 (.prefab / .fbx / auto)",
        "pt": "8. Configurar cabelo customizado do Unity (.prefab / .fbx / auto)",
    },
    "manager.cli_hair": {
        "en": "Override hair across texture + Blender build (auto, default, none, .prefab, .fbx)",
        "ja": "テクスチャ+Blender ビルド用ヘア上書き (auto, default, none, .prefab, .fbx)",
        "pt": "Sobrescrever cabelo no atlas e Blender (auto, default, none, .prefab, .fbx)",
    },
    "manager.cli_hair_mat": {
        "en": "Optional Unity .mat path passed to hair material extractor",
        "ja": "ヘアマテリアル抽出に渡すオプション Unity .mat パス",
        "pt": "Caminho opcional de .mat Unity para extração de material do cabelo",
    },
    "manager.cli_hair_tex": {
        "en": "Optional texture image path override for custom hair",
        "ja": "カスタムヘア用オプションテクスチャ画像パス",
        "pt": "Caminho opcional de imagem de textura para cabelo customizado",
    },
    "manager.cli_hair_scale": {
        "en": "Optional uniform scale multiplier passed to custom hair alignment",
        "ja": "カスタムヘア整列に渡すオプション均一スケール倍率",
        "pt": "Multiplicador de escala uniforme para alinhamento de cabelo customizado",
    },
    "manager.cli_hair_offset": {
        "en": "Optional X,Y,Z Unity offset passed to custom hair alignment",
        "ja": "カスタムヘア整列に渡すオプション X,Y,Z オフセット",
        "pt": "Deslocamento opcional X,Y,Z em Unity para alinhamento do cabelo",
    },
    "manager.cli_save_hair": {
        "en": "Persist --hair* overrides into vrc2gtav.cfg",
        "ja": "--hair* の指定内容を vrc2gtav.cfg に保存",
        "pt": "Salvar sobrescritas --hair* no arquivo vrc2gtav.cfg",
    },
    "manager.hair_header": {
        "en": "CONFIGURE CUSTOM UNITY HAIR",
        "ja": "カスタム Unity ヘアの設定",
        "pt": "CONFIGURAR CABELO CUSTOMIZADO DO UNITY",
    },
    "manager.hair_select_protagonist": {
        "en": "Select which GTA V protagonist's hair to configure:",
        "ja": "ヘアを設定する GTA V の主人公を選択してください:",
        "pt": "Selecione qual protagonista do GTA V terá o cabelo configurado:",
    },
    "manager.hair_current": {
        "en": "Current hair configuration for {protagonist}: {current}",
        "ja": "{protagonist} の現在のヘア設定: {current}",
        "pt": "Configuração atual de cabelo para {protagonist}: {current}",
    },
    "manager.hair_scanning": {
        "en": "Scanning Unity Assets folder for hair prefabs and FBXs...",
        "ja": "Unity Assets フォルダ内のヘア Prefab / FBX をスキャン中...",
        "pt": "Escaneando pasta Unity Assets por prefabs e FBXs de cabelo...",
    },
    "manager.hair_select_source": {
        "en": "Choose a hair source for {protagonist}:",
        "ja": "{protagonist} に使用するヘアソースを選択してください:",
        "pt": "Escolha a fonte de cabelo para {protagonist}:",
    },
    "manager.hair_opt_auto": {
        "en": "  [1] Auto (detect Modular Avatar / VRCFury / Head attachment in .unity scene)",
        "ja": "  [1] Auto (.unity シーン内の Modular Avatar / VRCFury / Head 装着ヘアを自動検出)",
        "pt": "  [1] Auto (detectar Modular Avatar / VRCFury / Head na cena .unity)",
    },
    "manager.hair_opt_default": {
        "en": "  [2] Default avatar hair (use base avatar's native hair)",
        "ja": "  [2] デフォルトヘア (ベースアバター標準の髪を使用)",
        "pt": "  [2] Cabelo padrão do avatar (usar o cabelo nativo do avatar base)",
    },
    "manager.hair_opt_none": {
        "en": "  [3] None (export without hair meshes)",
        "ja": "  [3] なし (ヘアーメッシュなしでエクスポート)",
        "pt": "  [3] Nenhum (exportar avatar sem cabelo)",
    },
    "manager.hair_opt_manual": {
        "en": "  [M] Enter custom .prefab or .fbx path manually",
        "ja": "  [M] .prefab または .fbx のパスを手入力する",
        "pt": "  [M] Digitar caminho manual de arquivo .prefab ou .fbx",
    },
    "manager.hair_no_candidates": {
        "en": "  (No extra hair prefabs detected automatically in Unity Assets.)",
        "ja": "  (Unity Assets 内に追加のヘア Prefab は自動検出されませんでした。)",
        "pt": "  (Nenhum prefab extra de cabelo encontrado automaticamente em Unity Assets.)",
    },
    "manager.hair_prompt_choice": {
        "en": "Enter option number, 'M', or '0' to cancel: ",
        "ja": "番号、'M'、またはキャンセル '0' を入力してください: ",
        "pt": "Digite o número, 'M', ou '0' para cancelar: ",
    },
    "manager.hair_prompt_manual_path": {
        "en": "Enter path to hair .prefab or .fbx: ",
        "ja": "ヘア用 .prefab または .fbx のパスを入力してください: ",
        "pt": "Digite o caminho para o arquivo .prefab ou .fbx do cabelo: ",
    },
    "manager.hair_prompt_scale": {
        "en": "Optional hair scale multiplier [default 1.0]: ",
        "ja": "ヘアのスケール倍率 [既定 1.0]: ",
        "pt": "Multiplicador de escala opcional do cabelo [padrão 1.0]: ",
    },
    "manager.hair_prompt_offset": {
        "en": "Optional X,Y,Z Unity offset [default 0,0,0]: ",
        "ja": "オプションの X,Y,Z Unity オフセット [既定 0,0,0]: ",
        "pt": "Deslocamento opcional X,Y,Z em Unity [padrão 0,0,0]: ",
    },
    "manager.hair_path_missing": {
        "en": "[WARNING] Custom hair file not found: {path}",
        "ja": "[警告] 指定されたヘアファイルが見つかりません: {path}",
        "pt": "[AVISO] Arquivo de cabelo não encontrado: {path}",
    },
    "manager.hair_saved": {
        "en": "[OK] Saved custom_hair='{hair}' into [{section}] in vrc2gtav.cfg.",
        "ja": "[OK] custom_hair='{hair}' を vrc2gtav.cfg の [{section}] に保存しました。",
        "pt": "[OK] Salvo custom_hair='{hair}' em [{section}] no vrc2gtav.cfg.",
    },
    "tests.sec_custom_hair_title": {
        "en": "\n[TEST] Validating Universal Unity Custom Hair Support...",
        "ja": "\n[TEST] 汎用 Unity カスタムヘア対応を検証中...",
        "pt": "\n[TEST] Validando Suporte Universal a Cabelos Customizados do Unity...",
    },
    "tests.suite_custom_hair": {
        "en": "Universal Unity Custom Hair Porting",
        "ja": "汎用 Unity カスタムヘア自動移植",
        "pt": "Porte Automático de Cabelo Customizado Unity",
    },
    "tests.hair_cli_flags": {
        "en": "All atlas generators, Blender builders, runners & manager expose --hair CLI options",
        "ja": "全アトラス生成・Blender ビルド・ランナー・マネージャーが --hair オプションに対応",
        "pt": "Todos os geradores de atlas, builders Blender, runners e manager expõem --hair",
    },
    "tests.hair_prefab_variant": {
        "en": "Unity .prefab / PrefabVariant parser, inactive gimmick filter & lilToon compositor",
        "ja": "Unity .prefab / PrefabVariant 解析・非表示メッシュ除外・lilToon 合成",
        "pt": "Parser .prefab / PrefabVariant, filtro m_IsActive e compositor lilToon",
    },
    "tests.hair_uv_packing": {
        "en": "Multi-tile atlas packing, UDIM centroid remap, gutter padding & tail filter",
        "ja": "マルチタイルアトラス配置・UDIM 重心リマップ・余白パディング・尻尾判定",
        "pt": "Empacotamento multi-tile, remap UDIM por centroide, gutter e filtro tail",
    },
    "tests.hair_cfg_keywords": {
        "en": "Per-protagonist custom_hair keywords (auto/default/none) preserved in vrc2gtav_paths",
        "ja": "主人公別 custom_hair キーワード (auto/default/none) が vrc2gtav_paths で保持",
        "pt": "Palavras-chave por protagonista custom_hair (auto/default/none) preservadas",
    },
    "manager.menu_opt_9": {
        "en": "  [9] Sync / Export All FBX Blendshapes -> configs/*_blendshapes.cfg",
        "ja": "  [9] FBX 全ブレンドシェイプを configs/*_blendshapes.cfg に同期/書き出し",
        "pt": "  [9] Sincronizar / Exportar Todos os Blendshapes do FBX -> configs/*_blendshapes.cfg",
    },
    "manager.blendshapes_header": {
        "en": "SYNC FBX BLENDSHAPES TO .CFG PRESETS",
        "ja": "FBX ブレンドシェイプを .cfg プリセットへ同期",
        "pt": "SINCRONIZAR BLENDSHAPES DO FBX PARA PRESETS .CFG",
    },
    "manager.blendshapes_select_avatar": {
        "en": "Select which avatar preset to populate from its FBX model(s):",
        "ja": "FBX から全ブレンドシェイプを同期するアバタープリセットを選択してください:",
        "pt": "Selecione qual preset de avatar atualizar com os blendshapes do FBX:",
    },
    "manager.blendshapes_opt_all": {
        "en": "  [{opt}] All Configured Avatars (player_zero, player_one, player_two)",
        "ja": "  [{opt}] すべての設定済みアバター (player_zero, player_one, player_two)",
        "pt": "  [{opt}] Todos os Avatares Configurados (player_zero, player_one, player_two)",
    },
    "manager.blendshapes_prompt_choice": {
        "en": "Enter choice [0-4]: ",
        "ja": "番号を入力してください [0-4]: ",
        "pt": "Digite a opção [0-4]: ",
    },
    "tests.blendshapes_fbx_merge": {
        "en": "FBX full channel discovery merges missing blendshapes as 0.0 without resetting existing .cfg edits",
        "ja": "FBX 全チャンネル読込が既存 .cfg 値をリセットせず未設定項目のみ 0.0 で補完",
        "pt": "Leitura completa de blendshapes do FBX preenche ausentes em 0.0 sem zerar edições do .cfg",
    },
    "manager.menu_opt_10": {
        "en": "  [10] Sync / Export All Unity PhysBones -> configs/*_physbones.cfg",
        "ja": "  [10] Unity 全 PhysBone を configs/*_physbones.cfg に同期/書き出し",
        "pt": "  [10] Sincronizar / Exportar Todos os PhysBones do Unity -> configs/*_physbones.cfg",
    },
    "manager.physbones_header": {
        "en": "SYNC UNITY PHYSBONES TO .CFG PRESETS",
        "ja": "UNITY PHYSBONE を .CFG プリセットへ同期",
        "pt": "SINCRONIZAR PHYSBONES DO UNITY PARA PRESETS .CFG",
    },
    "manager.physbones_select_avatar": {
        "en": "Select which avatar preset to sync from Unity standard VRCPhysBones:",
        "ja": "Unity 標準 VRCPhysBone を同期するアバターを選択:",
        "pt": "Selecione qual avatar atualizar com os VRCPhysBones padrão do Unity:",
    },
    "manager.physbones_prompt_marshmallow": {
        "en": "Include optional Marshmallow PB breast overrides? [y/N]: ",
        "ja": "任意の Marshmallow PB 胸プリセット上書きを含めますか? [y/N]: ",
        "pt": "Incluir sobrescrita opcional Marshmallow PB nos seios? [s/N]: ",
    },
    "manager.physbones_prompt_choice": {
        "en": "Enter choice [0-4]: ",
        "ja": "番号を入力してください [0-4]: ",
        "pt": "Digite a opção [0-4]: ",
    },
    "manager.cli_export_physbones": {
        "en": "Export and sync Unity standard VRCPhysBones into configs/*_physbones.cfg (add --physbones-marshmallow to include Marshmallow PB)",
        "ja": "Unity 標準 VRCPhysBone を configs/*_physbones.cfg へ同期書き出し（--physbones-marshmallow で Marshmallow PB 有効化）",
        "pt": "Exportar VRCPhysBones padrão do Unity para configs/*_physbones.cfg (use --physbones-marshmallow para incluir Marshmallow PB)",
    },
    "manager.cli_overwrite_physbones_from_unity": {
        "en": "When exporting PhysBones, reload active Unity/Marshmallow parameters instead of preserving existing .cfg edits",
        "ja": "PhysBone 書き出し時に既存 .cfg 編集を保持せず Unity シーンから再読み込みする",
        "pt": "Ao exportar PhysBones, recarregar valores ativos do Unity em vez de manter edições do .cfg",
    },
    "manager.export_physbones_ok": {
        "en": "[OK] Exported PhysBones for {char}: {path}",
        "ja": "[OK] {char} の PhysBone を書き出しました: {path}",
        "pt": "[OK] PhysBones exportados para {char}: {path}",
    },
    "manager.export_physbones_skipped": {
        "en": "[WARNING] Skipped {char}: no Unity scene or .cfg PhysBone preset found.",
        "ja": "[警告] {char} をスキップしました: Unity シーンまたは .cfg PhysBone が見つかりません。",
        "pt": "[AVISO] {char} ignorado: nenhuma cena Unity ou .cfg de PhysBones encontrado.",
    },
    "physbones.cli_cfg": {
        "en": "Path to a PhysBones .cfg preset file",
        "ja": "PhysBone .cfg プリセットファイルへのパス",
        "pt": "Caminho para o arquivo de predefinição .cfg de PhysBones",
    },
    "physbones.cli_source": {
        "en": "PhysBones source priority: auto, unity, or cfg",
        "ja": "PhysBone の取得元優先順: auto, unity, または cfg",
        "pt": "Origem prioritária dos PhysBones: auto, unity ou cfg",
    },
    "physbones.cli_marshmallow": {
        "en": "Enable or disable optional Marshmallow PB breast overrides (default: off / standard VRCPhysBones)",
        "ja": "任意の Marshmallow PB 胸プリセット上書きを有効/無効化（既定: オフ / 標準 VRCPhysBone）",
        "pt": "Ativar ou desativar o opcional Marshmallow PB nos seios (padrão: desativado / VRCPhysBones padrão)",
    },
    "physbones.cli_save_cfg": {
        "en": "Save resolved PhysBone chains and mapping to this .cfg preset file",
        "ja": "解決済み PhysBone チェーン設定をこの .cfg ファイルに保存",
        "pt": "Salvar as cadeias de PhysBones resolvidas neste arquivo .cfg",
    },
    "physbones.loaded_source": {
        "en": "[INFO] PhysBones loaded via '{source}': {chains} chains, {bones} custom bones ({detail})",
        "ja": "[情報] '{source}' から PhysBone を読込: {chains} チェーン / {bones} ボーン ({detail})",
        "pt": "[INFO] PhysBones carregados via '{source}': {chains} cadeias, {bones} ossos customizados ({detail})",
    },
    "physbones.saved_cfg": {
        "en": "[OK] Saved PhysBones preset file: {path}",
        "ja": "[OK] PhysBone プリセットファイルを保存しました: {path}",
        "pt": "[OK] Arquivo .cfg de PhysBones salvo: {path}",
    },
    "setup.physbones_cfg_ready": {
        "en": "[OK] PhysBones preset for {char} ready: {path}",
        "ja": "[OK] {char} 用 PhysBone プリセット準備完了: {path}",
        "pt": "[OK] Predefinição de PhysBones para {char} pronta: {path}",
    },
    "setup.physbones_cfg_exported": {
        "en": "[OK] Exported Unity PhysBones for {char} -> {path}",
        "ja": "[OK] {char} の Unity PhysBone を書き出しました -> {path}",
        "pt": "[OK] PhysBones do Unity exportados para {char} -> {path}",
    },
    "setup.physbones_cfg_missing": {
        "en": "[WARNING] No PhysBones .cfg or Unity scene found for {char}: {path}",
        "ja": "[警告] {char} の PhysBone .cfg または Unity シーンが見つかりません: {path}",
        "pt": "[AVISO] Nenhum arquivo .cfg de PhysBones ou cena Unity encontrado para {char}: {path}",
    },
    "tests.physbones_unity_extract": {
        "en": "Unity scene + nested prefab + Marshmallow PB PhysBone extraction across all 3 avatars",
        "ja": "3アバター全体の Unity シーン + ネスト Prefab + Marshmallow PB 自動抽出",
        "pt": "Extração de VRCPhysBones + Marshmallow PB do Unity nos 3 avatares",
    },
    "tests.physbones_budget_pack": {
        "en": "RAGE <= 128-bone (.ydd) & <= 63 custom-bone packer with zero ELF hash collisions",
        "ja": "RAGE 128ボーン上限 (カスタム <= 63) パッカーと ELF タグ衝突ゼロ検証",
        "pt": "Empacotador <= 128 ossos (.ydd) / <= 63 customizados sem colisões ELF",
    },
    "tests.physbones_cfg_roundtrip": {
        "en": "Tracked configs/*_physbones.cfg & dynamic chain builder round-trip",
        "ja": "configs/*_physbones.cfg と動的 PhysBone チェーン構築の往復テスト",
        "pt": "Presets configs/*_physbones.cfg e leitura/gravação + builder dinâmico",
    },
    "tests.physbones_priority_pack": {
        "en": "PhysBone priority tiers keep essentials/presets & rigidly discard non-essential overflow",
        "ja": "PhysBone 優先度ティア (プリセット維持・非必須超過分の剛体フォールバック除外)",
        "pt": "Lista de priorização de PhysBones (mantém essenciais/presets e descarta não essenciais)",
    },
    "tests.physbones_orphan_cleanup": {
        "en": "Orphaned/unused old-dress PhysBones detected and removed on import",
        "ja": "衣装差し替えで孤立した旧衣装 PhysBone の自動検出・除外",
        "pt": "Detecção e exclusão automática de PhysBones órfãos de vestidos antigos na importação",
    },
    "ped_damage.cli_blood_decals": {
        "en": "Enable GTA V ped blood/wound decals (`ped.sps` + 6-zone `UVMap 1`, default enabled)",
        "ja": "GTA V の出血・傷デカールを有効化 (`ped.sps` + 6ゾーン `UVMap 1`、既定で有効)",
        "pt": "Habilitar decals de sangue/ferimentos do GTA V (`ped.sps` + `UVMap 1` em 6 zonas, ativo por padrão)",
    },
    "ped_damage.applied": {
        "en": "[OK] Ped blood decals configured: shader={shader}, torso={torso}, head={head}, arms={arms}, legs={legs}, unmapped={unmapped}",
        "ja": "[OK] 出血デカール設定完了: shader={shader}, torso={torso}, head={head}, arms={arms}, legs={legs}, unmapped={unmapped}",
        "pt": "[OK] Decals de sangue configurados: shader={shader}, tronco={torso}, cabeça={head}, braços={arms}, pernas={legs}, excluídos={unmapped}",
    },
    "tests.ped_damage_decals": {
        "en": "GTA V ped blood decals (`ped.sps` + 6-zone `UVMap 1` + vanilla `#FF8000FF` colors)",
        "ja": "GTA V Ped 出血デカール (`ped.sps` + 6ゾーン `UVMap 1` + `#FF8000FF` 頂点カラー)",
        "pt": "Decals de sangue GTA V (`ped.sps` + `UVMap 1` em 6 zonas + vértice `#FF8000FF`)",
    },
    "tests.rpf7_16mb_safeguards": {
        "en": "RPF7 16 MiB (`0xFFFFFF`) resource & 4 GiB sector offset crash guards",
        "ja": "RPF7 16 MiB (`0xFFFFFF`) リソース上限 & 4 GiB セクタオフセット保護",
        "pt": "Proteções contra limite RPF7 de 16 MiB (`0xFFFFFF`) e offset de 4 GiB",
    },
    "eye_blink.cli_opt": {
        "en": "Enable optional natural eye blinking via native GTA V eyelid bones & GTAVPhysBones.ini (auto skips conflicting closed-eye expressions)",
        "ja": "オプションの自然なまばたきを有効化 (GTA V ネイティブまぶたボーン + GTAVPhysBones.ini 使用・閉じ目表情とは自動競合回避)",
        "pt": "Habilitar piscar natural opcional via bones nativos de pálpebra do GTA V e GTAVPhysBones.ini (pula expressões de olho fechado)",
    },
    "eye_blink.strength_cli_opt": {
        "en": "Optional peak blink closing factor (`max_blink`, e.g. 0.50 Shinano / 0.60 Miltina) without altering any other facial blendshape",
        "ja": "まばたきの最大閉じ具合 (`max_blink`、例: しなの 0.50 / ミルティナ 0.60・他の顔ブレンドシェイプは一切変更しません)",
        "pt": "Fator máximo opcional do piscar (`max_blink`, ex.: 0.50 Shinano / 0.60 Miltina) sem afetar nenhum outro blendshape facial",
    },
    "eye_blink.mouth_open_cli_opt": {
        "en": "Mouth opening strength scale (`FACIAL_jaw` weight ceiling 0.00-1.00; 0.00 closed, 0.70 default)",
        "ja": "口の開き具合 (`FACIAL_jaw` 最大ウェイト 0.00〜1.00; 0.00=閉じる / 0.70=既定)",
        "pt": "Intensidade de abertura da boca (peso máximo de `FACIAL_jaw` de 0.00 a 1.00; 0.00 fechada, 0.70 padrão)",
    },
    "eye_blink.applied": {
        "en": "[OK] Natural eye blink rigged: shape_key='{key}', eyelid_verts={verts}, travel=(L:{left_mm:.1f}mm, R:{right_mm:.1f}mm)",
        "ja": "[OK] 自然なまばたき設定完了: shape_key='{key}', まぶた頂点={verts}, 可動量=(L:{left_mm:.1f}mm, R:{right_mm:.1f}mm)",
        "pt": "[OK] Piscar natural configurado: shape_key='{key}', vértices={verts}, deslocamento=(E:{left_mm:.1f}mm, D:{right_mm:.1f}mm)",
    },
    "eye_blink.skipped": {
        "en": "[INFO] Natural eye blink disabled/skipped ({reason})",
        "ja": "[INFO] 自然なまばたきを無効化/スキップ ({reason})",
        "pt": "[INFO] Piscar natural dos olhos desativado/ignorado ({reason})",
    },
    "eye_blink.profile_exported": {
        "en": "[PhysBones] Exported eye blink profile for '{model}' into GTAVPhysBones.ini (enabled={enabled}, max_blink={max_blink:.2f})",
        "ja": "[PhysBones] '{model}' のまばたきプロファイルを GTAVPhysBones.ini へ書き出し (enabled={enabled}, max_blink={max_blink:.2f})",
        "pt": "[PhysBones] Perfil de piscar natural de '{model}' salvo no GTAVPhysBones.ini (enabled={enabled}, max_blink={max_blink:.2f})",
    },
    "eye_blink.ydd_bones_trimmed": {
        "en": "[EyeBlink] Added 4 eyelid bones and trimmed {stripped} unskinned YFT-only hand leaf bone(s) from .ydd (total bones <= 128)",
        "ja": "[EyeBlink] まぶたボーン4本を追加し、.ydd のみ未スキニング手補助ボーン {stripped} 本を整理 (.ydd 上限 <= 128)",
        "pt": "[EyeBlink] Adicionados 4 bones de pálpebra e removidos {stripped} bones auxiliares de mão apenas-YFT do .ydd (limite <= 128)",
    },
    "manager.prompt_eye_blink": {
        "en": "  [?] Enable natural eye blinking? (may glitch if custom closed-eye expression is active) [Y/n]: ",
        "ja": "  [?] 自然なまばたきを有効にしますか? (閉じ目系カスタム表情では不具合の原因になる場合があります) [Y/n]: ",
        "pt": "  [?] Ativar piscar natural dos olhos? (pode bugar se houver expressão customizada de olho fechado) [Y/n]: ",
    },
    "tests.eye_blink_rigging": {
        "en": "Optional natural eye blinking, closed-eye expression conflict guard & GTAVPhysBones.ini blink merge",
        "ja": "オプションの自然なまばたき、カスタム表情競合ガード & GTAVPhysBones.ini 統合テスト",
        "pt": "Piscar natural opcional, proteção contra expressões customizadas e GTAVPhysBones.ini",
    },
    "manager.menu_opt_11": {
        "en": "  [11] Convert & Replace Any GTA V NPC (streamed / pedestrian + VRChat PhysBones)",
        "ja": "  [11] 任意の GTA V NPC を変換・置換 (固有NPC / 街中歩行者 + VRChat PhysBones)",
        "pt": "  [11] Converter & Substituir Qualquer NPC do GTA V (pedestre / secundário + PhysBones)",
    },
    "manager.npc_header": {
        "en": "Universal GTA V NPC Converter (VRChat -> Street Ped / Story NPC)",
        "ja": "汎用 GTA V NPC コンバーター (VRChat -> 歩行者 / サブNPC)",
        "pt": "Conversor Universal de NPCs do GTA V (VRChat -> Pedestre / Secundário)",
    },
    "manager.npc_prompt_ped": {
        "en": "  Target GTA V NPC model (e.g. ig_lamardavis, cs_lamardavis, a_f_y_beach_01): ",
        "ja": "  対象の GTA V NPC モデル名 (例: ig_lamardavis, cs_lamardavis, a_f_y_beach_01): ",
        "pt": "  Nome do modelo NPC alvo no GTA V (ex.: ig_lamardavis, cs_lamardavis, a_f_y_beach_01): ",
    },
    "manager.npc_prompt_source": {
        "en": "  Avatar source path (.zip, .unitypackage, .prefab/.unity, or Unity folder): ",
        "ja": "  アバターのソースパス (.zip, .unitypackage, .prefab/.unity, または Unity フォルダ): ",
        "pt": "  Caminho do avatar (.zip, .unitypackage, .prefab/.unity ou pasta Unity): ",
    },
    "manager.npc_prompt_avatar": {
        "en": "  Optional avatar/prefab name (blank = auto-detect): ",
        "ja": "  任意のアバター/Prefab名 (空欄 = 自動検出): ",
        "pt": "  Nome opcional do avatar/prefab (vazio = detecção automática): ",
    },
    "manager.npc_prompt_deploy": {
        "en": "  Deploy patched RPF archives & GTAVPhysBones.ini directly into GTA V/mods? [Y/n]: ",
        "ja": "  パッチ済み RPF と GTAVPhysBones.ini を GTA V/mods へ直接導入しますか? [Y/n]: ",
        "pt": "  Instalar arquivos RPF e GTAVPhysBones.ini diretamente no GTA V/mods? [Y/n]: ",
    },
    "manager.npc_cli_help": {
        "en": "Target GTA V NPC model name (e.g. ig_lamardavis or a_f_y_beach_01)",
        "ja": "置換対象の GTA V NPC モデル名 (例: ig_lamardavis, a_f_y_beach_01)",
        "pt": "Nome do modelo NPC alvo do GTA V (ex.: ig_lamardavis ou a_f_y_beach_01)",
    },
    "manager.cli_all_npcs": {
        "en": "Include all NPCs registered in configs/npc_registry.json during slot patching/repack",
        "ja": "スロット置換・再パック時に configs/npc_registry.json の全登録済み NPC を含める",
        "pt": "Incluir todos os NPCs registrados em configs/npc_registry.json ao aplicar/empacotar",
    },
    "tests.suite_npc": {
        "en": "Universal NPC discovery, atlas packing, VRChat PhysBones & multi-model INI",
        "ja": "汎用 NPC 検出・アトラス生成・VRChat PhysBones & 複数モデル対応 INI テスト",
        "pt": "Pipeline universal de NPCs, atlas, PhysBones VRChat e INI multi-modelo",
    },
    "tests.npc_pipeline_detail": {
        "en": "streamed + componentpeds layout, un-sided rings, curved lash blink & model-scoped INI",
        "ja": "streamed / componentpeds 構造、スカート個別追従、まばたき範囲、モデル別 INI",
        "pt": "layout streamed/componentpeds, saia separada, piscar suave e INI por modelo",
    },
}
