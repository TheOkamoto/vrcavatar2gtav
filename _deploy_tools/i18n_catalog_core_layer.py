"""
i18n_catalog_core_layer.py
==========================
Layer 1 of 3 for the VRC2GTAV trilingual translation catalog.

Contains core CLI/path/setup/manager/deployment translations (`common.*`,
`paths.*`, `setup.*`, `manager.*`, `apply.*`, etc.).
"""

from typing import Dict


# Ordered subset of the trilingual ("en", "ja", "pt") catalog consumed by
# vrc2gtav_i18n.py to keep catalog files concise and maintainable.
CORE_TRANSLATION_CATALOG: Dict[str, Dict[str, str]] = {
    "common.language_option_help": {
        "en": "Interface language override (auto, en, ja, pt). Default: auto (system locale).",
        "ja": "UI言語を上書き指定します (auto, en, ja, pt)。既定値: auto (システムロケール)。",
        "pt": "Idioma da interface (auto, en, ja, pt). Padrão: auto (idioma do sistema).",
    },
    "common.yes_no_default_yes": {
        "en": "[Y/n]",
        "ja": "[Y/n]",
        "pt": "[S/n]",
    },
    "common.yes_no_default_no": {
        "en": "[y/N]",
        "ja": "[y/N]",
        "pt": "[s/N]",
    },
    "common.press_enter_to_continue": {
        "en": "Press Enter to continue...",
        "ja": "続行するには Enter キーを押してください...",
        "pt": "Pressione Enter para continuar...",
    },
    "paths.empty_path_error": {
        "en": "Empty path encountered while resolving configuration.",
        "ja": "設定の解決中に空のパスが検出されました。",
        "pt": "Caminho vazio encontrado ao resolver a configuração.",
    },
    "paths.config_not_found_explicit": {
        "en": "Specified configuration file not found: {path}",
        "ja": "指定された設定ファイルが見つかりません: {path}",
        "pt": "Arquivo de configuração especificado não encontrado: {path}",
    },
    "paths.config_not_found_env": {
        "en": "Configuration file pointed to by {env_var} was not found: {path}",
        "ja": "{env_var} が指す設定ファイルが見つかりません: {path}",
        "pt": "Arquivo apontado por {env_var} não encontrado: {path}",
    },
    "paths.config_not_found_default": {
        "en": "File '{filename}' not found. Make sure it exists in the project root or set {env_var}.",
        "ja": "ファイル '{filename}' が見つかりません。プロジェクトルートに存在するか、{env_var} を設定してください。",
        "pt": "Arquivo '{filename}' não encontrado. Certifique-se de que existe na raiz do projeto ou defina {env_var}.",
    },
    "paths.template_not_found_explicit": {
        "en": "Specified template file not found: {path}",
        "ja": "指定されたテンプレートファイルが見つかりません: {path}",
        "pt": "Arquivo template especificado não encontrado: {path}",
    },
    "paths.template_not_found_default": {
        "en": "Template file '{filename}' not found.",
        "ja": "テンプレートファイル '{filename}' が見つかりません。",
        "pt": "Arquivo template '{filename}' não encontrado.",
    },
    "paths.config_stat_error": {
        "en": "Could not read metadata for {path}: {error}",
        "ja": "{path} のメタデータを読み取れませんでした: {error}",
        "pt": "Não foi possível ler os metadados de {path}: {error}",
    },
    "paths.config_parse_error": {
        "en": "Syntax error while reading configuration '{path}': {error}",
        "ja": "設定ファイル '{path}' の読み込み中に構文エラーが発生しました: {error}",
        "pt": "Erro de sintaxe ao ler a configuração '{path}': {error}",
    },
    "paths.config_open_error": {
        "en": "Failed to open configuration file: {path}",
        "ja": "設定ファイルを開けませんでした: {path}",
        "pt": "Falha ao abrir o arquivo de configuração: {path}",
    },
    "paths.config_missing_directories": {
        "en": "Required section [directories] is missing in {path}.",
        "ja": "{path} に必須セクション [directories] がありません。",
        "pt": "Seção obrigatória [directories] ausente em {path}.",
    },
    "paths.section_not_found": {
        "en": "Section [{section}] not found in {path}.",
        "ja": "{path} にセクション [{section}] が見つかりません。",
        "pt": "Seção [{section}] não encontrada em {path}.",
    },
    "paths.option_not_found": {
        "en": "Key '{option}' not found in section [{section}] of {path}.",
        "ja": "{path} のセクション [{section}] にキー '{option}' が見つかりません。",
        "pt": "Chave '{option}' não encontrada na seção [{section}] de {path}.",
    },
    "paths.streamedpedprops_not_found": {
        "en": "streamedpedprops.rpf not found for extraction at: {path}",
        "ja": "展開用の streamedpedprops.rpf が見つかりません: {path}",
        "pt": "streamedpedprops.rpf não encontrado para extração em: {path}",
    },
    "paths.extracting_streamedpedprops": {
        "en": "[INFO] Extracting {source_path} -> {target_dir}...",
        "ja": "[情報] {source_path} を {target_dir} に展開しています...",
        "pt": "[INFO] Extraindo {source_path} -> {target_dir}...",
    },
    "paths.restored_skeleton_backup": {
        "en": "[OK] Restored base skeleton from vanilla backup: {filename}",
        "ja": "[OK] バニラバックアップからベーススケルトンを復元しました: {filename}",
        "pt": "[OK] Esqueleto base restaurado do backup vanilla: {filename}",
    },
    "paths.extracting_vanilla_skeleton": {
        "en": "[INFO] Extracting vanilla skeleton '{filename}' from {archive_name}...",
        "ja": "[情報] {archive_name} からバニラスケルトン '{filename}' を抽出しています...",
        "pt": "[INFO] Extraindo esqueleto vanilla '{filename}' de {archive_name}...",
    },
    "paths.extracting_base_skeleton": {
        "en": "[INFO] Extracting base skeleton '{filename}' from {archive_name}...",
        "ja": "[情報] {archive_name} からベーススケルトン '{filename}' を抽出しています...",
        "pt": "[INFO] Extraindo esqueleto base '{filename}' de {archive_name}...",
    },
    "paths.skeleton_missing_run_setup": {
        "en": "Base skeleton '{path}' is missing. Run First-Run Setup (`python run_mod_manager.py --setup`) to extract vanilla files from your GTA V installation.",
        "ja": "ベーススケルトン '{path}' がありません。初回セットアップ (`python run_mod_manager.py --setup`) を実行して GTA V からバニラファイルを抽出してください。",
        "pt": "Esqueleto base '{path}' ausente. Execute a Configuração Inicial (`python run_mod_manager.py --setup`) para extrair os arquivos vanilla do seu GTA V.",
    },
    "paths.prop_dummy_not_found": {
        "en": "Prop dummy YDD not found at: {path}",
        "ja": "プロップ用ダミー YDD が見つかりません: {path}",
        "pt": "Prop dummy YDD não encontrado em: {path}",
    },
    "paths.props_dir_missing": {
        "en": "  [WARNING] Props directory not found: {path}",
        "ja": "  [警告] プロップディレクトリが見つかりません: {path}",
        "pt": "  [AVISO] Diretório de props não encontrado: {path}",
    },
    "paths.props_replaced_line": {
        "en": "      Prop dummies (p_*.ydd, {size_bytes} B):     {count}",
        "ja": "      プロップダミー置換 (p_*.ydd, {size_bytes} B): {count}",
        "pt": "      Dummies de props (p_*.ydd, {size_bytes} B):  {count}",
    },
    "paths.props_untouched_line": {
        "en": "      Other props/textures untouched:         {count}",
        "ja": "      その他のプロップ/テクスチャ未変更:       {count}",
        "pt": "      Outros props/texturas intocados:         {count}",
    },
    "paths.summary_header": {
        "en": "=== VRC2GTAV: Paths Loaded via .cfg ===",
        "ja": "=== VRC2GTAV: .cfg から読み込まれたパス ===",
        "pt": "=== VRC2GTAV: Caminhos Carregados via .cfg ===",
    },
    "paths.summary_cfg_file": {
        "en": "Config file (.cfg): {path}",
        "ja": "設定ファイル (.cfg): {path}",
        "pt": "Arquivo .cfg:       {path}",
    },
    "paths.summary_language": {
        "en": "Active language:    {language}",
        "ja": "使用中の言語:       {language}",
        "pt": "Idioma ativo:       {language}",
    },
    "paths.summary_os": {
        "en": "Operating System:   {system_name} ({release_name})",
        "ja": "オペレーティングシステム: {system_name} ({release_name})",
        "pt": "Sistema Operacional: {system_name} ({release_name})",
    },
    "paths.summary_project_root": {
        "en": "Project Root:       {path}",
        "ja": "プロジェクトルート: {path}",
        "pt": "Raiz do Projeto:    {path}",
    },
    "paths.summary_unity_assets": {
        "en": "Unity Assets:       {path}",
        "ja": "Unity アセット:     {path}",
        "pt": "Assets Unity:       {path}",
    },
    "paths.summary_staging": {
        "en": "Staging:            {path}",
        "ja": "ステージング:       {path}",
        "pt": "Staging:            {path}",
    },
    "paths.summary_gtav_mods": {
        "en": "GTA V Mods:         {path}",
        "ja": "GTA V Mods:         {path}",
        "pt": "GTA V Mods:         {path}",
    },
    "paths.summary_rage_cli": {
        "en": "RAGE CLI:           {path}",
        "ja": "RAGE CLI:           {path}",
        "pt": "RAGE CLI:           {path}",
    },
    "paths.summary_blender_exe": {
        "en": "Blender Exe:        {path}",
        "ja": "Blender 実行ファイル: {path}",
        "pt": "Blender Exe:        {path}",
    },
    "paths.summary_python_exe": {
        "en": "Python Exe:         {path}",
        "ja": "Python 実行ファイル: {path}",
        "pt": "Python Exe:         {path}",
    },
    "paths.summary_ffmpeg_exe": {
        "en": "FFmpeg Exe:         {path}",
        "ja": "FFmpeg 実行ファイル: {path}",
        "pt": "FFmpeg Exe:         {path}",
    },
    "paths.summary_dummy_ydd": {
        "en": "Dummy YDD:          {path}",
        "ja": "ダミー YDD:         {path}",
        "pt": "Dummy YDD:          {path}",
    },
    "paths.summary_prop_dummy_ydd": {
        "en": "Prop Dummy YDD:     {path}",
        "ja": "プロップダミー YDD: {path}",
        "pt": "Prop Dummy YDD:     {path}",
    },
    "paths.summary_x64v_mod_rpf": {
        "en": "x64v Mod RPF:       {path}",
        "ja": "x64v Mod RPF:       {path}",
        "pt": "x64v Mod RPF:       {path}",
    },
    "hand.invalid_vrc_armature": {
        "en": "Invalid VRChat armature when extracting hand bone targets.",
        "ja": "手のボーンターゲット抽出時に無効な VRChat アーマチュアが渡されました。",
        "pt": "Armature VRChat inválida ao extrair os alvos dos ossos das mãos.",
    },
    "hand.missing_required_bones": {
        "en": "Missing required bones while extracting VRChat armature targets: main={main_bones}, fingers={finger_bones}",
        "ja": "VRChat アーマチュアのターゲット抽出に必要なボーンが見つかりません: main={main_bones}, fingers={finger_bones}",
        "pt": "Ossos obrigatórios ausentes ao extrair alvos da armature VRChat: principais={main_bones}, dedos={finger_bones}",
    },
    "hand.invalid_gtav_armature": {
        "en": "Invalid GTA V armature for bone relocation.",
        "ja": "ボーン再配置用の GTA V アーマチュアが無効です。",
        "pt": "Armature GTA V inválida para realocação de ossos.",
    },
    "hand.yft_source_not_found": {
        "en": "Source .yft file not found: {path}",
        "ja": "元の .yft ファイルが見つかりません: {path}",
        "pt": "Arquivo .yft de origem não encontrado: {path}",
    },
    "hand.fragment_missing_drawable": {
        "en": "Fragment has no valid drawable in: {path}",
        "ja": "フラグメントに有効な drawable がありません: {path}",
        "pt": "Fragmento sem drawable válido em: {path}",
    },
    "hand.fragment_missing_skeleton": {
        "en": "Fragment has no valid skeleton in: {path}",
        "ja": "フラグメントに有効なスケルトンがありません: {path}",
        "pt": "Fragmento sem esqueleto válido em: {path}",
    },
    "hand.target_bone_disappeared": {
        "en": "Target bone '{bone_name}' disappeared after exporting {path}.",
        "ja": "エクスポート後にターゲットボーン '{bone_name}' が消失しました: {path}",
        "pt": "Osso alvo '{bone_name}' desapareceu após exportar {path}.",
    },
    "hand.roundtrip_error_excessive": {
        "en": "Excessive round-trip error while validating {filename}: {error_meters:.6f} m",
        "ja": "{filename} のラウンドトリップ検証で許容誤差を超えました: {error_meters:.6f} m",
        "pt": "Erro de round-trip excessivo ao validar {filename}: {error_meters:.6f} m",
    },
    "apply.banner": {
        "en": "=== GTA V UNIVERSAL AVATAR SLOT APPLICATOR ===",
        "ja": "=== GTA V 汎用アバタースロット適用ツール ===",
        "pt": "=== APLICADOR UNIVERSAL DE AVATARES GTA V ===",
    },
    "apply.project_root": {
        "en": "Project Root:    {path}",
        "ja": "プロジェクトルート: {path}",
        "pt": "Raiz do Projeto: {path}",
    },
    "apply.staging_rpf": {
        "en": "Staging RPF:     {path}",
        "ja": "ステージング RPF: {path}",
        "pt": "Staging RPF:     {path}",
    },
    "apply.patch_error": {
        "en": "[ERROR] Failed to replace {path}: {error}",
        "ja": "[エラー] {path} の置換に失敗しました: {error}",
        "pt": "[ERRO] Falha ao substituir {path}: {error}",
    },
    "apply.dir_uppr_models": {
        "en": "      Replaced uppr models:        {count}",
        "ja": "      置換された uppr モデル:      {count}",
        "pt": "      Modelos uppr substituídos:     {count}",
    },
    "apply.dir_textures": {
        "en": "      Texture dictionaries (.ytd):   {count}",
        "ja": "      テクスチャ辞書 (.ytd):         {count}",
        "pt": "      Dicionários de textura (.ytd): {count}",
    },
    "apply.dir_dummies": {
        "en": "      Dummies installed (629 B):     {count}",
        "ja": "      ダミー配置数 (629 B):          {count}",
        "pt": "      Dummies instalados (629 B):    {count}",
    },
    "apply.dir_untouched": {
        "en": "      Untouched files:               {count}",
        "ja": "      未変更ファイル:                {count}",
        "pt": "      Arquivos intocados:            {count}",
    },
    "apply.dummy_not_found": {
        "en": "[ERROR] Dummy YDD not found at: {path}",
        "ja": "[エラー] ダミー YDD が見つかりません: {path}",
        "pt": "[ERRO] Dummy YDD não encontrado em: {path}",
    },
    "apply.prop_dummy_not_found": {
        "en": "[ERROR] Prop dummy YDD not found at: {path}",
        "ja": "[エラー] プロップダミー YDD が見つかりません: {path}",
        "pt": "[ERRO] Prop Dummy YDD não encontrado em: {path}",
    },
    "apply.props_extract_failed": {
        "en": "[ERROR] Failed to prepare streamedpedprops_extracted: {error}",
        "ja": "[エラー] streamedpedprops_extracted の準備に失敗しました: {error}",
        "pt": "[ERRO] Falha ao preparar streamedpedprops_extracted: {error}",
    },
    "apply.unknown_character": {
        "en": "[ERROR] Unknown character key: {character_key}",
        "ja": "[エラー] 不明なキャラクターキーです: {character_key}",
        "pt": "[ERRO] Personagem desconhecido: {character_key}",
    },
    "apply.applying_header": {
        "en": "\n--- Applying {display_name} ({character_key}) ---",
        "ja": "\n--- {display_name} ({character_key}) を適用中 ---",
        "pt": "\n--- Aplicando {display_name} ({character_key}) ---",
    },
    "apply.missing_model_ydd": {
        "en": "[ERROR] Model YDD not found: {path}",
        "ja": "[エラー] モデル YDD が見つかりません: {path}",
        "pt": "[ERRO] Modelo YDD não encontrado: {path}",
    },
    "apply.missing_texture_ytd": {
        "en": "[ERROR] Texture YTD not found: {path}",
        "ja": "[エラー] テクスチャ YTD が見つかりません: {path}",
        "pt": "[ERRO] Textura YTD não encontrada: {path}",
    },
    "apply.missing_skeleton_yft": {
        "en": "[ERROR] Skeleton YFT not found: {path}",
        "ja": "[エラー] スケルトン YFT が見つかりません: {path}",
        "pt": "[ERRO] Esqueleto YFT não encontrado: {path}",
    },
    "apply.skeleton_updated": {
        "en": "  [{character_key}] Updated skeleton: {filename}",
        "ja": "  [{character_key}] スケルトン更新: {filename}",
        "pt": "  [{character_key}] Esqueleto atualizado: {filename}",
    },
    "apply.success": {
        "en": "\n[SUCCESS] Characters applied successfully into staging directories!",
        "ja": "\n[成功] ステージングディレクトリへのキャラクター適用が完了しました！",
        "pt": "\n[SUCESSO] Personagens aplicados com sucesso nos diretórios de staging!",
    },
    "apply.cli_description": {
        "en": "Apply VRChat avatars into GTA V clothing slots",
        "ja": "VRChat アバターを GTA V の衣装スロットに適用します",
        "pt": "Aplica avatares VRChat nos slots de roupas do GTA V",
    },
    "apply.cli_character_help": {
        "en": "Character to apply (player_zero=Michael, player_one=Franklin, player_two=Trevor, all=All)",
        "ja": "適用するキャラクター (player_zero=マイケル, player_one=フランクリン, player_two=トレバー, all=全員)",
        "pt": "Personagem a aplicar (player_zero=Michael, player_one=Franklin, player_two=Trevor, all=Todos)",
    },
    "apply.next_step_repack": {
        "en": "Run 'python repack_and_deploy_everything.py' to rebuild RPF archives and install into the game.",
        "ja": "'python repack_and_deploy_everything.py' を実行して RPF を再構築し、ゲームにインストールしてください。",
        "pt": "Execute 'python repack_and_deploy_everything.py' para gerar os arquivos RPF e instalar no jogo.",
    },
    "setup.prompt_current": {
        "en": "    Current in .cfg: {value}",
        "ja": "    現在の .cfg 設定: {value}",
        "pt": "    Atual no .cfg: {value}",
    },
    "setup.prompt_detected": {
        "en": "    Auto-detected:   {value}",
        "ja": "    自動検出値:      {value}",
        "pt": "    Detectado automaticamente: {value}",
    },
    "setup.prompt_input": {
        "en": "    Path [Enter = use '{suggested}']: ",
        "ja": "    パス [Enter = '{suggested}' を使用]: ",
        "pt": "    Caminho [Enter = usar '{suggested}']: ",
    },
    "setup.created_cfg": {
        "en": "[INFO] Created local configuration file from template: {path}",
        "ja": "[情報] テンプレートからローカル設定ファイルを作成しました: {path}",
        "pt": "[INFO] Arquivo de configuração local criado a partir do template: {path}",
    },
    "setup.step_gtav_title": {
        "en": "1) GTA V Legacy root directory",
        "ja": "1) GTA V レガシー版のルートフォルダ",
        "pt": "1) Pasta raiz do GTA V Legacy",
    },
    "setup.step_gtav_desc": {
        "en": "must contain GTA5.exe and x64v.rpf",
        "ja": "GTA5.exe と x64v.rpf を含む必要があります",
        "pt": "deve conter GTA5.exe e x64v.rpf",
    },
    "setup.step_assets_title": {
        "en": "2) Unity/VRChat Assets directory",
        "ja": "2) Unity/VRChat の Assets フォルダ",
        "pt": "2) Pasta Assets do Unity/VRChat",
    },
    "setup.step_assets_desc": {
        "en": "containing Shinano/, DOLOSart/, Vagrant Brand/, Li-ne/, etc.",
        "ja": "Shinano/、DOLOSart/、Vagrant Brand/、Li-ne/ 等を含む必要があります",
        "pt": "contendo Shinano/, DOLOSart/, Vagrant Brand/, Li-ne/, etc.",
    },
    "setup.step_blender_title": {
        "en": "3) Blender executable (with Sollumz add-on)",
        "ja": "3) Blender 実行ファイル (Sollumz アドオン導入済み)",
        "pt": "3) Executável do Blender (com add-on Sollumz)",
    },
    "setup.step_blender_desc": {
        "en": "e.g. C:/Program Files/Blender Foundation/Blender 4.0/blender.exe",
        "ja": "例: C:/Program Files/Blender Foundation/Blender 4.0/blender.exe",
        "pt": "ex.: C:/Program Files/Blender Foundation/Blender 4.0/blender.exe",
    },
    "setup.step_rage_title": {
        "en": "4) RAGE CLI executable (rage)",
        "ja": "4) RAGE CLI 実行ファイル (rage)",
        "pt": "4) Executável RAGE CLI (rage)",
    },
    "setup.step_rage_desc": {
        "en": "e.g. rage in PATH or full path to the rage binary",
        "ja": "例: PATH 上の rage または rage バイナリへのフルパス",
        "pt": "ex.: rage no PATH ou caminho completo para o binário rage",
    },
    "setup.saved_cfg": {
        "en": "[OK] Configuration saved to: {path}",
        "ja": "[OK] 設定を保存しました: {path}",
        "pt": "[OK] Configuração salva em: {path}",
    },
    "setup.source_rpf_missing": {
        "en": "Source RPF file not found: {path}",
        "ja": "元の RPF ファイルが見つかりません: {path}",
        "pt": "Arquivo RPF de origem não encontrado: {path}",
    },
    "setup.extracting_default": {
        "en": "Extracting {filename}",
        "ja": "{filename} を展開中",
        "pt": "Extraindo {filename}",
    },
    "setup.invalid_gtav_root": {
        "en": "[ERROR] Valid GTA V Legacy installation not found at: {path}\n        Ensure GTA5.exe and x64v.rpf exist in the configured folder.",
        "ja": "[エラー] 有効な GTA V レガシー版インストールが見つかりません: {path}\n        指定フォルダ内に GTA5.exe と x64v.rpf があるか確認してください。",
        "pt": "[ERRO] Instalação válida do GTA V Legacy não encontrada em: {path}\n       Certifique-se de que GTA5.exe e x64v.rpf existam na pasta configurada.",
    },
    "setup.rage_not_found": {
        "en": "[ERROR] RAGE CLI not found at '{rage_bin}'.\n        Install `rage` (https://github.com/VIRUXE/rage) and set it in vrc2gtav.cfg.",
        "ja": "[エラー] RAGE CLI が '{rage_bin}' に見つかりません。\n        `rage` (https://github.com/VIRUXE/rage) をインストールし、vrc2gtav.cfg で指定してください。",
        "pt": "[ERRO] RAGE CLI não encontrado em '{rage_bin}'.\n       Instale o binário `rage` (https://github.com/VIRUXE/rage) e informe o caminho no vrc2gtav.cfg.",
    },
    "setup.extracting_keys": {
        "en": "[INFO] Extracting cryptographic keys from GTA5.exe into {path}...",
        "ja": "[情報] GTA5.exe から暗号鍵を {path} に抽出しています...",
        "pt": "[INFO] Extraindo chaves criptográficas do GTA5.exe em {path}...",
    },
    "setup.keys_ready": {
        "en": "[OK] RAGE keys already available at: {path}",
        "ja": "[OK] RAGE 鍵ファイルは既に準備済みです: {path}",
        "pt": "[OK] Chaves RAGE já disponíveis em: {path}",
    },
    "setup.desc_extract_x64v": {
        "en": "Extracting vanilla x64v.rpf",
        "ja": "バニラ版 x64v.rpf を展開中",
        "pt": "Extraindo x64v.rpf vanilla",
    },
    "setup.x64v_ready": {
        "en": "[OK] x64v_extracted already prepared: {path}",
        "ja": "[OK] x64v_extracted は既に準備済みです: {path}",
        "pt": "[OK] x64v_extracted já preparado: {path}",
    },
    "setup.desc_extract_streamedpeds": {
        "en": "Extracting streamedpeds_players.rpf",
        "ja": "streamedpeds_players.rpf を展開中",
        "pt": "Extraindo streamedpeds_players.rpf",
    },
    "setup.streamedpeds_ready": {
        "en": "[OK] streamedpeds_players_extracted already prepared: {path}",
        "ja": "[OK] streamedpeds_players_extracted は既に準備済みです: {path}",
        "pt": "[OK] streamedpeds_players_extracted já preparado: {path}",
    },
    "setup.desc_extract_skeletons": {
        "en": "Extracting vanilla skeletons (.yft)",
        "ja": "バニラスケルトン (.yft) を抽出中",
        "pt": "Extraindo esqueletos vanilla (.yft)",
    },
    "setup.desc_extract_vanilla_peds_for_skeletons": {
        "en": "Extracting vanilla streamedpeds_players.rpf for skeletons",
        "ja": "スケルトン用にバニラ版 streamedpeds_players.rpf を抽出中",
        "pt": "Extraindo streamedpeds_players.rpf vanilla para esqueletos",
    },
    "setup.skeleton_backups_ready": {
        "en": "[OK] Vanilla skeleton backups already saved in: {path}",
        "ja": "[OK] バニラスケルトンのバックアップは既に保存済みです: {path}",
        "pt": "[OK] Backups de esqueletos vanilla já salvos em: {path}",
    },
    "setup.character_skeleton_ready": {
        "en": "[OK] Base skeleton ready ({character}): {path}",
        "ja": "[OK] ベーススケルトン準備完了 ({character}): {path}",
        "pt": "[OK] Esqueleto base pronto ({character}): {path}",
    },
    "setup.streamedpedprops_ready": {
        "en": "[OK] streamedpedprops_extracted ready: {path}",
        "ja": "[OK] streamedpedprops_extracted 準備完了: {path}",
        "pt": "[OK] streamedpedprops_extracted pronto: {path}",
    },
    "setup.mppatches_missing": {
        "en": "[ERROR] Required DLC mppatchesng not found at: {path}",
        "ja": "[エラー] 必須 DLC mppatchesng が見つかりません: {path}",
        "pt": "[ERRO] DLC obrigatório mppatchesng não encontrado em: {path}",
    },
    "setup.desc_extract_mppatchesng": {
        "en": "Extracting update/x64/dlcpacks/mppatchesng/dlc.rpf",
        "ja": "update/x64/dlcpacks/mppatchesng/dlc.rpf を展開中",
        "pt": "Extraindo update/x64/dlcpacks/mppatchesng/dlc.rpf",
    },
    "setup.mppatchesng_ready": {
        "en": "[OK] mppatchesng_extracted already prepared: {path}",
        "ja": "[OK] mppatchesng_extracted は既に準備済みです: {path}",
        "pt": "[OK] mppatchesng_extracted já preparado: {path}",
    },
    "setup.desc_extract_mppatches": {
        "en": "Extracting mppatches.rpf",
        "ja": "mppatches.rpf を展開中",
        "pt": "Extraindo mppatches.rpf",
    },
    "setup.mppatches_ready": {
        "en": "[OK] mppatches_extracted already prepared: {path}",
        "ja": "[OK] mppatches_extracted は既に準備済みです: {path}",
        "pt": "[OK] mppatches_extracted já preparado: {path}",
    },
    "setup.desc_extract_patchday4_dlc": {
        "en": "Extracting update/x64/dlcpacks/patchday4ng/dlc.rpf",
        "ja": "update/x64/dlcpacks/patchday4ng/dlc.rpf を展開中",
        "pt": "Extraindo update/x64/dlcpacks/patchday4ng/dlc.rpf",
    },
    "setup.patchday4_dlc_ready": {
        "en": "[OK] patchday4ng_dlc_extracted already prepared: {path}",
        "ja": "[OK] patchday4ng_dlc_extracted は既に準備済みです: {path}",
        "pt": "[OK] patchday4ng_dlc_extracted já preparado: {path}",
    },
    "setup.desc_extract_patchday4_rpf": {
        "en": "Extracting patchday4ng.rpf",
        "ja": "patchday4ng.rpf を展開中",
        "pt": "Extraindo patchday4ng.rpf",
    },
    "setup.patchday4_models_ready": {
        "en": "[OK] patchday4ng_models_extracted already prepared: {path}",
        "ja": "[OK] patchday4ng_models_extracted は既に準備済みです: {path}",
        "pt": "[OK] patchday4ng_models_extracted já preparado: {path}",
    },
    "setup.patchday4_optional_skipped": {
        "en": "[INFO] Optional DLC patchday4ng not found in gtav_root; skipping step.",
        "ja": "[情報] オプション DLC patchday4ng が gtav_root に見つからないためスキップします。",
        "pt": "[INFO] DLC opcional patchday4ng não encontrado em gtav_root; etapa ignorada.",
    },
    "setup.desc_extract_patchday_dlc": {
        "en": "Extracting update/x64/dlcpacks/{dlc}/dlc.rpf",
        "ja": "update/x64/dlcpacks/{dlc}/dlc.rpf を展開中",
        "pt": "Extraindo update/x64/dlcpacks/{dlc}/dlc.rpf",
    },
    "setup.patchday_dlc_ready": {
        "en": "[OK] {dlc}_dlc_extracted already prepared: {path}",
        "ja": "[OK] {dlc}_dlc_extracted は既に準備済みです: {path}",
        "pt": "[OK] {dlc}_dlc_extracted já preparado: {path}",
    },
    "setup.desc_extract_patchday_rpf": {
        "en": "Extracting {dlc}.rpf",
        "ja": "{dlc}.rpf を展開中",
        "pt": "Extraindo {dlc}.rpf",
    },
    "setup.patchday_models_ready": {
        "en": "[OK] {dlc}_models_extracted already prepared: {path}",
        "ja": "[OK] {dlc}_models_extracted は既に準備済みです: {path}",
        "pt": "[OK] {dlc}_models_extracted já preparado: {path}",
    },
    "setup.patchday_optional_skipped": {
        "en": "[INFO] Optional DLC {dlc} not found in gtav_root; skipping step.",
        "ja": "[情報] オプション DLC {dlc} が gtav_root に見つからないためスキップします。",
        "pt": "[INFO] DLC opcional {dlc} não encontrado em gtav_root; etapa ignorada.",
    },
    "setup.extraction_success": {
        "en": "\n[SUCCESS] First-Run setup and vanilla extraction completed successfully!",
        "ja": "\n[成功] 初回セットアップとバニラファイルの抽出が正常に完了しました！",
        "pt": "\n[SUCESSO] Configuração inicial e extração vanilla concluídas com sucesso!",
    },
    "setup.diag_header": {
        "en": "  FIRST-RUN DIAGNOSTICS (VRC2GTAV)",
        "ja": "  初回実行診断レポート (VRC2GTAV)",
        "pt": "  DIAGNÓSTICO DE PRIMEIRA EXECUÇÃO (VRC2GTAV)",
    },
    "setup.diag_tag_ok": {
        "en": "[OK]",
        "ja": "[OK]",
        "pt": "[OK]",
    },
    "setup.diag_tag_pending": {
        "en": "[PENDING]",
        "ja": "[未完了]",
        "pt": "[PENDENTE]",
    },
    "setup.banner_title": {
        "en": "  FIRST-RUN SETUP AND VANILLA GTA V ASSET EXTRACTION",
        "ja": "  初回セットアップおよびバニラ GTA V アセット抽出",
        "pt": "  CONFIGURAÇÃO INICIAL (FIRST-RUN) E EXTRAÇÃO DE ASSETS VANILLA DO GTA V",
    },
    "setup.banner_notice": {
        "en": "  No copyrighted GTA V files or paid VRChat assets are distributed in\n  this repository. We will configure your local paths and extract the\n  required vanilla files directly from your GTA V installation.",
        "ja": "  このリポジトリには著作権で保護された GTA V ファイルや有料 VRChat アセットは\n  一切含まれていません。ローカルパスを設定し、お使いの GTA V インストール先から\n  必要なバニラファイルを直接抽出します。",
        "pt": "  Nenhum arquivo protegido do GTA V ou asset pago de VRChat é distribuído\n  neste repositório. Vamos configurar seus caminhos locais e extrair os\n  arquivos vanilla necessários diretamente da sua instalação do GTA V.",
    },
    "setup.unity_assets_warning": {
        "en": "[WARNING] Unity Assets folder does not exist or is unreachable: {path}\n          GTA V extraction will proceed, but point to your assets before compiling textures and 3D models.",
        "ja": "[警告] Unity Assets フォルダが存在しないかアクセスできません: {path}\n       GTA V の抽出は続行しますが、テクスチャや 3D モデルをコンパイルする前にアセットパスを指定してください。",
        "pt": "[AVISO] A pasta Assets Unity ainda não existe ou não está acessível: {path}\n        A extração do GTA V continuará, mas certifique-se de apontar para seus assets antes de compilar texturas e modelos 3D.",
    },
    "setup.cli_description": {
        "en": "First-Run wizard and vanilla GTA V extractor for vrc2gtav",
        "ja": "vrc2gtav 用 初回セットアップウィザード兼 GTA V バニラアセット抽出ツール",
        "pt": "Assistente First-Run e extrator de arquivos vanilla do GTA V para vrc2gtav",
    },
    "setup.cli_check_only": {
        "en": "Display diagnostics only without modifying files",
        "ja": "ファイルを変更せずに診断結果のみ表示します",
        "pt": "Apenas exibe o diagnóstico sem modificar arquivos",
    },
    "setup.cli_non_interactive": {
        "en": "Do not ask interactive questions (use autodetect / vrc2gtav.cfg / CLI flags)",
        "ja": "対話プロンプトを表示せず自動検出 / vrc2gtav.cfg / CLI 引数を使用します",
        "pt": "Não faz perguntas no terminal (usa autodetecção / vrc2gtav.cfg / flags CLI)",
    },
    "setup.cli_force": {
        "en": "Re-extract vanilla RPFs even if folders already exist in staging/",
        "ja": "staging/ にフォルダが存在していてもバニラ RPF を再抽出します",
        "pt": "Reextrai os RPFs vanilla mesmo se as pastas já existirem em staging/",
    },
    "setup.cli_gtav_root": {
        "en": "GTA V Legacy root folder",
        "ja": "GTA V レガシー版のルートフォルダ",
        "pt": "Pasta raiz do GTA V Legacy",
    },
    "setup.cli_unity_assets": {
        "en": "Unity project Assets folder",
        "ja": "Unity プロジェクトの Assets フォルダ",
        "pt": "Pasta Assets do projeto Unity",
    },
    "setup.cli_blender": {
        "en": "Blender executable path",
        "ja": "Blender 実行ファイルのパス",
        "pt": "Executável do Blender",
    },
    "setup.cli_rage": {
        "en": "RAGE CLI (rage) executable",
        "ja": "RAGE CLI (rage) 実行ファイル",
        "pt": "Executável RAGE CLI (rage)",
    },
    "setup.cli_python": {
        "en": "Python 3 executable",
        "ja": "Python 3 実行ファイル",
        "pt": "Executável Python 3",
    },
    "setup.prompt_download_blender": {
        "en": "Blender 4.0.2 not found or wrong version. Download portable Blender 4.0.2 + Sollumz now?",
        "ja": "Blender 4.0.2 が見つからないかバージョンが異なります。ポータブル版 Blender 4.0.2 + Sollumz をダウンロードしますか？",
        "pt": "Blender 4.0.2 não encontrado ou versão incompatível. Baixar Blender 4.0.2 portátil + Sollumz agora?",
    },
    "setup.prompt_download_sollumz": {
        "en": "Sollumz add-on is missing in Blender 4.0.2. Download and install Sollumz now?",
        "ja": "Blender 4.0.2 に Sollumz アドオンが見つかりません。ダウンロードしてインストールしますか？",
        "pt": "O add-on Sollumz não foi encontrado no Blender 4.0.2. Baixar e instalar o Sollumz agora?",
    },
    "manager.subcmd_starting": {
        "en": "[STARTING] {task}...",
        "ja": "[開始] {task}...",
        "pt": "[INICIANDO] {task}...",
    },
    "manager.subcmd_failed": {
        "en": "[FAILED] {task} failed after {elapsed:.1f}s with exit code {returncode}.",
        "ja": "[失敗] {task} が {elapsed:.1f}秒後に終了コード {returncode} で失敗しました。",
        "pt": "[FALHA] {task} falhou após {elapsed:.1f}s com código de retorno {returncode}.",
    },
    "manager.subcmd_tail_header": {
        "en": "--- LAST OUTPUT LINES ---",
        "ja": "--- 出力の最後の数行 ---",
        "pt": "--- ÚLTIMAS LINHAS DA SAÍDA ---",
    },
    "manager.subcmd_completed": {
        "en": "[COMPLETED] {task} in {elapsed:.1f}s.",
        "ja": "[完了] {task} ({elapsed:.1f}秒)。",
        "pt": "[CONCLUÍDO] {task} em {elapsed:.1f}s.",
    },
    "manager.subcmd_unexpected_error": {
        "en": "[UNEXPECTED ERROR] {task}: {error}",
        "ja": "[予期しないエラー] {task}: {error}",
        "pt": "[ERRO INESPERADO] {task}: {error}",
    },
    "manager.prereq_header": {
        "en": "SYSTEM PREREQUISITES CHECK",
        "ja": "システム前提条件チェック",
        "pt": "VERIFICAÇÃO DE PRÉ-REQUISITOS DO SISTEMA",
    },
    "manager.prereq_cfg": {
        "en": "[OK] Loaded .cfg configuration: {path}",
        "ja": "[OK] .cfg 設定を読み込みました: {path}",
        "pt": "[OK] Configuração .cfg carregada: {path}",
    },
    "manager.prereq_python": {
        "en": "[OK] Configured Python: {path}",
        "ja": "[OK] 設定済み Python: {path}",
        "pt": "[OK] Python configurado: {path}",
    },
    "manager.prereq_libs_ok": {
        "en": "[OK] Python libraries (Pillow, NumPy) installed and working.",
        "ja": "[OK] Python ライブラリ (Pillow, NumPy) が利用可能です。",
        "pt": "[OK] Bibliotecas Python (Pillow, NumPy) instaladas e funcionais.",
    },
    "manager.prereq_libs_missing": {
        "en": "[ERROR] Missing Python libraries in {python_exe}: {error}",
        "ja": "[エラー] {python_exe} に必要な Python ライブラリが不足しています: {error}",
        "pt": "[ERRO] Bibliotecas Python ausentes em {python_exe}: {error}",
    },
    "manager.prereq_python_fail": {
        "en": "[ERROR] Failed to validate Python environment ({python_exe}): {error}",
        "ja": "[エラー] Python 環境の検証に失敗しました ({python_exe}): {error}",
        "pt": "[ERRO] Falha ao validar ambiente Python ({python_exe}): {error}",
    },
    "manager.prereq_blender_ok": {
        "en": "[OK] Located Blender executable: {path}",
        "ja": "[OK] Blender 実行ファイルを検出しました: {path}",
        "pt": "[OK] Executável do Blender localizado: {path}",
    },
    "manager.prereq_blender_warn": {
        "en": "[WARNING] Blender not found at '{path}'. Update [executables] -> blender in vrc2gtav.cfg.",
        "ja": "[警告] Blender が '{path}' に見つかりません。vrc2gtav.cfg の [executables] -> blender を更新してください。",
        "pt": "[AVISO] Blender não encontrado em '{path}'. Ajuste [executables] -> blender em vrc2gtav.cfg.",
    },
    "manager.prereq_rage_ok": {
        "en": "[OK] Located RAGE CLI: {path}",
        "ja": "[OK] RAGE CLI を検出しました: {path}",
        "pt": "[OK] RAGE CLI localizado: {path}",
    },
    "manager.prereq_rage_err": {
        "en": "[ERROR] RAGE CLI not found at '{path}'. Update [executables] -> rage in vrc2gtav.cfg.",
        "ja": "[エラー] RAGE CLI が '{path}' に見つかりません。vrc2gtav.cfg の [executables] -> rage を更新してください。",
        "pt": "[ERRO] RAGE CLI não encontrado em '{path}'. Ajuste [executables] -> rage em vrc2gtav.cfg.",
    },
    "manager.prereq_assets_ok": {
        "en": "[OK] Located Unity Assets folder: {path}",
        "ja": "[OK] Unity Assets フォルダを検出しました: {path}",
        "pt": "[OK] Pasta de Assets Unity localizada: {path}",
    },
    "manager.prereq_assets_warn": {
        "en": "[WARNING] Unity Assets folder not found: {path}",
        "ja": "[警告] Unity Assets フォルダが見つかりません: {path}",
        "pt": "[AVISO] Pasta de Assets Unity não encontrada: {path}",
    },
    "manager.prereq_mods_ok": {
        "en": "[OK] Located GTA V mods folder: {path}",
        "ja": "[OK] GTA V mods フォルダを検出しました: {path}",
        "pt": "[OK] Pasta de mods do GTA V localizada: {path}",
    },
    "manager.prereq_mods_warn": {
        "en": "[WARNING] GTA V mods folder not found: {path}",
        "ja": "[警告] GTA V mods フォルダが見つかりません: {path}",
        "pt": "[AVISO] Pasta de mods do GTA V não encontrada: {path}",
    },
    "manager.prereq_dummy_ok": {
        "en": "[OK] Located Dummy YDD: {path}",
        "ja": "[OK] ダミー YDD を検出しました: {path}",
        "pt": "[OK] Dummy YDD localizado: {path}",
    },
    "manager.prereq_dummy_err": {
        "en": "[ERROR] Dummy YDD not found: {path}",
        "ja": "[エラー] ダミー YDD が見つかりません: {path}",
        "pt": "[ERRO] Dummy YDD não encontrado: {path}",
    },
    "manager.prereq_prop_dummy_ok": {
        "en": "[OK] Located Prop Dummy YDD: {path}",
        "ja": "[OK] プロップダミー YDD を検出しました: {path}",
        "pt": "[OK] Prop Dummy YDD localizado: {path}",
    },
    "manager.prereq_prop_dummy_err": {
        "en": "[ERROR] Prop Dummy YDD not found: {path}",
        "ja": "[エラー] プロップダミー YDD が見つかりません: {path}",
        "pt": "[ERRO] Prop Dummy YDD não encontrado: {path}",
    },
    "manager.stage1_header": {
        "en": "STAGE 1: TEXTURE ATLAS GENERATION (2K DXT5)",
        "ja": "ステージ 1: テクスチャアトラス生成 (2K DXT5)",
        "pt": "ETAPA 1: GERAÇÃO DE TEXTURE ATLAS (2K DXT5)",
    },
    "manager.tex_script_missing": {
        "en": "[ERROR] Texture script not found: {path}",
        "ja": "[エラー] テクスチャスクリプトが見つかりません: {path}",
        "pt": "[ERRO] Script de textura não encontrado: {path}",
    },
    "manager.generating_atlas_task": {
        "en": "Generating Texture Atlas for {display_name}",
        "ja": "{display_name} のテクスチャアトラスを生成",
        "pt": "Gerando Atlas de Textura para {display_name}",
    },
    "manager.stage2_header": {
        "en": "STAGE 2: BLENDER 3D MODEL BUILD (SOLLUMZ)",
        "ja": "ステージ 2: BLENDER 3D モデルビルド (SOLLUMZ)",
        "pt": "ETAPA 2: COMPILAÇÃO DE MODELOS NO BLENDER (SOLLUMZ)",
    },
    "manager.blender_script_missing": {
        "en": "[ERROR] Blender script not found: {path}",
        "ja": "[エラー] Blender スクリプトが見つかりません: {path}",
        "pt": "[ERRO] Script Blender não encontrado: {path}",
    },
    "manager.building_blender_task": {
        "en": "Building 3D Model for {display_name}",
        "ja": "{display_name} の 3D モデルをビルド",
        "pt": "Compilando Modelo 3D para {display_name}",
    },
    "manager.stage3_header": {
        "en": "STAGE 3: UNIVERSAL SLOT APPLICATION (ANTI-CLIPPING)",
        "ja": "ステージ 3: 汎用スロット適用 (クリッピング防止)",
        "pt": "ETAPA 3: APLICAÇÃO UNIVERSAL DE SLOTS (ANTI-CLIPPING)",
    },
    "manager.apply_script_missing": {
        "en": "[ERROR] apply_characters.py script not found: {path}",
        "ja": "[エラー] apply_characters.py スクリプトが見つかりません: {path}",
        "pt": "[ERRO] Script apply_characters.py não encontrado: {path}",
    },
    "manager.patching_slots_task": {
        "en": "Patching slots for character {ped_id}",
        "ja": "キャラクター {ped_id} のスロットをパッチ",
        "pt": "Substituindo slots para o personagem {ped_id}",
    },
    "manager.stage4_header": {
        "en": "STAGE 4: RPF REPACKING AND GTA V DEPLOY",
        "ja": "ステージ 4: RPF 再パックと GTA V デプロイ",
        "pt": "ETAPA 4: REPACOTAMENTO RPF E DEPLOY NO GTA V",
    },
    "manager.repack_script_missing": {
        "en": "[ERROR] repack_and_deploy_everything.py script not found: {path}",
        "ja": "[エラー] repack_and_deploy_everything.py スクリプトが見つかりません: {path}",
        "pt": "[ERRO] Script repack_and_deploy_everything.py não encontrado: {path}",
    },
    "manager.repacking_task": {
        "en": "Repacking RPFs and Installing into Game",
        "ja": "RPF を再パックしてゲームにインストール",
        "pt": "Repacotando RPFs e Instalando no Jogo",
    },
    "manager.first_run_detected": {
        "en": "FIRST-RUN SETUP REQUIRED",
        "ja": "初回セットアップが検出されました (FIRST-RUN SETUP)",
        "pt": "PRIMEIRA EXECUÇÃO DETECTADA (FIRST-RUN SETUP)",
    },
    "manager.first_run_missing_msg": {
        "en": "  Local configuration vrc2gtav.cfg or extracted vanilla GTA V files\n  are missing from staging/ and 2_blender/.",
        "ja": "  ローカル設定 vrc2gtav.cfg、または staging/・2_blender/ 内の\n  GTA V バニラ抽出ファイルがまだ揃っていません。",
        "pt": "  Falta configurar o arquivo local vrc2gtav.cfg ou extrair os arquivos\n  base vanilla do seu GTA V para staging/ e 2_blender/.",
    },
    "manager.prompt_run_setup_now": {
        "en": "Run First-Run Setup now? [Y/n] (default: yes): ",
        "ja": "今すぐ初回セットアップを実行しますか？ [Y/n] (既定値: はい): ",
        "pt": "Deseja executar a Configuração Inicial agora? [S/n] (padrão: sim): ",
    },
    "manager.setup_incomplete_abort": {
        "en": "\n[ERROR] First-Run Setup incomplete. Fix the paths and try again.",
        "ja": "\n[エラー] 初回セットアップが完了していません。パスを修正して再試行してください。",
        "pt": "\n[ERRO] Configuração inicial incompleta. Corrija os caminhos e tente novamente.",
    },
    "manager.menu_title": {
        "en": "          VRChat AVATAR MANAGER FOR GTA V",
        "ja": "        GTA V 用 VRChat アバターマネージャー",
        "pt": "         GERENCIADOR DE AVATARES VRChat PARA GTA V",
    },
    "manager.menu_prompt_select": {
        "en": "Select which character you want to swap/update:",
        "ja": "更新・差し替えするキャラクターを選択してください:",
        "pt": "Selecione qual personagem você deseja trocar/atualizar:",
    },
    "manager.menu_opt_1": {
        "en": "  [1] Michael  (player_zero) -> Shinano Eternal Reunion",
        "ja": "  [1] マイケル     (player_zero) -> Shinano Eternal Reunion",
        "pt": "  [1] Michael  (player_zero) -> Shinano Eternal Reunion",
    },
    "manager.menu_opt_2": {
        "en": "  [2] Franklin (player_one)  -> Shinano Casual / Uniform",
        "ja": "  [2] フランクリン (player_one)  -> Shinano Casual / 制服",
        "pt": "  [2] Franklin (player_one)  -> Shinano Casual / Uniforme",
    },
    "manager.menu_opt_3": {
        "en": "  [3] Trevor   (player_two)  -> Miltina Maid",
        "ja": "  [3] トレバー     (player_two)  -> Miltina Maid",
        "pt": "  [3] Trevor   (player_two)  -> Miltina Maid",
    },
    "manager.menu_opt_4": {
        "en": "  [4] All 3 Characters (Full Pipeline)",
        "ja": "  [4] 全 3 キャラクター (フルパイプライン)",
        "pt": "  [4] Todos os 3 Personagens (Processo Completo)",
    },
    "manager.menu_opt_5": {
        "en": "  [5] Repack & Install RPFs Only (Deploy Only)",
        "ja": "  [5] RPF 再パックとインストールのみ (デプロイのみ)",
        "pt": "  [5] Apenas Repacotar e Instalar RPFs no GTA V (Deploy Only)",
    },
    "manager.menu_opt_6": {
        "en": "  [6] Initial Setup & GTA V Extraction (First-Run Setup)",
        "ja": "  [6] 初期設定と GTA V バニラ抽出 (First-Run Setup)",
        "pt": "  [6] Configuração Inicial e Extração GTA V (First-Run Setup)",
    },
    "manager.menu_opt_7": {
        "en": "  [7] Change / Swap VRChat Avatar Assignment",
        "ja": "  [7] VRChat アバター割り当ての変更 / 入れ替え",
        "pt": "  [7] Trocar / Alternar Avatar VRChat por Personagem",
    },
    "manager.menu_opt_0": {
        "en": "  [0] Exit",
        "ja": "  [0] 終了",
        "pt": "  [0] Sair",
    },
    "manager.menu_opt_slot": {
        "en": "  [{opt}] {protagonist} ({ped_name}) -> {avatar}",
        "ja": "  [{opt}] {protagonist} ({ped_name}) -> {avatar}",
        "pt": "  [{opt}] {protagonist} ({ped_name}) -> {avatar}",
    },
    "manager.menu_input_choice": {
        "en": "Enter desired option [0-10]: ",
        "ja": "オプション番号を入力してください [0-10]: ",
        "pt": "Digite a opção desejada [0-10]: ",
    },
    "manager.cancelled": {
        "en": "[INFO] Operation cancelled by user.",
        "ja": "[情報] ユーザーによって操作がキャンセルされました。",
        "pt": "[INFO] Operação cancelada pelo usuário.",
    },
    "manager.missing_cfg_option6": {
        "en": "[ERROR] vrc2gtav.cfg does not exist. Run option [6] first.",
        "ja": "[エラー] vrc2gtav.cfg が存在しません。先にオプション [6] を実行してください。",
        "pt": "[ERRO] O arquivo vrc2gtav.cfg não existe. Execute a opção [6] primeiro.",
    },
    "manager.invalid_option": {
        "en": "[ERROR] Invalid option entered.",
        "ja": "[エラー] 無効なオプションが指定されました。",
        "pt": "[ERRO] Opção inválida informada.",
    },
    "manager.stage_config_header": {
        "en": "\nSelect which pipeline stages to run:",
        "ja": "\n実行するパイプラインステージの設定:",
        "pt": "\nConfiguração das etapas a serem executadas:",
    },
    "manager.prompt_textures": {
        "en": "Generate Texture Atlases (2K)? [Y/n] (default: yes): ",
        "ja": "テクスチャアトラス (2K) を生成しますか？ [Y/n] (既定値: はい): ",
        "pt": "Deseja gerar os Texture Atlases (2K)? [S/n] (padrão: sim): ",
    },
    "manager.prompt_blender": {
        "en": "Compile 3D models in Blender? [Y/n] (default: yes): ",
        "ja": "Blender で 3D モデルをビルドしますか？ [Y/n] (既定値: はい): ",
        "pt": "Deseja compilar os modelos no Blender? [S/n] (padrão: sim): ",
    },
    "manager.prompt_deploy": {
        "en": "Patch slots and install into GTA V? [Y/n] (default: yes): ",
        "ja": "スロットに適用して GTA V にインストールしますか？ [Y/n] (既定値: はい): ",
        "pt": "Deseja aplicar nos slots e instalar no GTA V? [S/n] (padrão: sim): ",
    },
    "manager.abort_textures": {
        "en": "\n[ERROR] Aborting pipeline due to texture generation error.",
        "ja": "\n[エラー] テクスチャ生成エラーのためパイプラインを中止しました。",
        "pt": "\n[ERRO] Abortando pipeline devido a erro na geração de texturas.",
    },
    "manager.abort_blender": {
        "en": "\n[ERROR] Aborting pipeline due to Blender compilation error.",
        "ja": "\n[エラー] Blender ビルドエラーのためパイプラインを中止しました。",
        "pt": "\n[ERRO] Abortando pipeline devido a erro na compilação do Blender.",
    },
    "manager.abort_slots": {
        "en": "\n[ERROR] Aborting pipeline due to slot patching error.",
        "ja": "\n[エラー] スロット適用エラーのためパイプラインを中止しました。",
        "pt": "\n[ERRO] Abortando pipeline devido a erro na aplicação de slots.",
    },
    "manager.abort_repack": {
        "en": "\n[ERROR] Aborting pipeline due to RPF repacking error.",
        "ja": "\n[エラー] RPF 再パックエラーのためパイプラインを中止しました。",
        "pt": "\n[ERRO] Abortando pipeline devido a erro no repacotamento de RPFs.",
    },
    "manager.pipeline_success_header": {
        "en": "PIPELINE COMPLETED SUCCESSFULLY",
        "ja": "パイプラインが正常に完了しました",
        "pt": "PIPELINE CONCLUÍDO COM TOTAL SUCESSO",
    },
    "manager.pipeline_success_body": {
        "en": "The avatars are ready and installed in your GTA V.",
        "ja": "アバターの準備と GTA V へのインストールが完了しました。",
        "pt": "Os avatares estão prontos e instalados no seu GTA V.",
    },
    "manager.cli_description": {
        "en": "Master Orchestrator for VRChat Avatars to GTA V",
        "ja": "GTA V 用 VRChat アバター統合オーケストレーター",
        "pt": "Gerenciador Mestre de Avatares VRChat para GTA V",
    },
    "manager.cli_character": {
        "en": "Character to process (opens interactive menu if omitted)",
        "ja": "処理するキャラクター (省略時は対話メニューを起動)",
        "pt": "Personagem a processar (se omitido, abre o menu interativo)",
    },
    "manager.cli_skip_textures": {
        "en": "Skip texture atlas generation stage",
        "ja": "テクスチャアトラス生成ステージをスキップ",
        "pt": "Pula a etapa de geração de texture atlas",
    },
    "manager.cli_skip_blender": {
        "en": "Skip Blender compilation stage",
        "ja": "Blender コンパイルステージをスキップ",
        "pt": "Pula a etapa de compilação no Blender",
    },
    "manager.cli_skip_deploy": {
        "en": "Skip slot patching and RPF repack stages",
        "ja": "スロット適用および RPF 再パックステージをスキップ",
        "pt": "Pula a etapa de aplicação nos slots e repacotamento de RPFs",
    },
    "manager.cli_deploy_only": {
        "en": "Run only slot deployment and final RPF repacking",
        "ja": "デプロイと最終 RPF 再パックのみ実行",
        "pt": "Executa apenas a aplicação e o repacotamento final",
    },
    "manager.cli_check_env": {
        "en": "Verify system prerequisites and exit",
        "ja": "システム前提条件を確認して終了",
        "pt": "Apenas verifica os pré-requisitos do sistema e encerra",
    },
    "manager.cli_setup": {
        "en": "Run First-Run configurator and extract vanilla GTA V RPFs",
        "ja": "初回設定ウィザードを実行し、GTA V バニラ RPF を抽出",
        "pt": "Executa o configurador First-Run e extrai RPFs vanilla do GTA V",
    },
    "manager.cli_force_setup": {
        "en": "Force re-extraction of vanilla RPFs during setup",
        "ja": "セットアップ時にバニラ RPF を強制再抽出",
        "pt": "Força reextração dos RPFs vanilla durante a configuração",
    },
    "manager.cli_non_interactive": {
        "en": "Run --setup without interactive prompts",
        "ja": "対話プロンプトなしで --setup を実行",
        "pt": "Executa --setup sem perguntas interativas",
    },
    "manager.auto_setup_info": {
        "en": "[INFO] Incomplete initial environment detected; running automatic setup...",
        "ja": "[情報] 初期環境が未完了のため自動セットアップを実行します...",
        "pt": "[INFO] Ambiente inicial incompleto detectado; executando configuração automática...",
    },
    "manager.auto_setup_failed": {
        "en": "[ERROR] Could not complete First-Run setup automatically. Run `python run_mod_manager.py --setup` to configure.",
        "ja": "[エラー] 初回セットアップを自動完了できませんでした。`python run_mod_manager.py --setup` を実行して設定してください。",
        "pt": "[ERRO] Não foi possível concluir a Configuração Inicial automaticamente. Execute `python run_mod_manager.py --setup` para configurar.",
    },
    "manager.cli_automated_done": {
        "en": "AUTOMATED PIPELINE COMPLETED SUCCESSFULLY",
        "ja": "自動パイプラインが正常に完了しました",
        "pt": "PIPELINE AUTOMATIZADO CONCLUÍDO COM SUCESSO",
    },
    "repack.rpf_not_found": {
        "en": "[ERROR] RPF file to patch not found: {path}",
        "ja": "[エラー] パッチ対象の RPF ファイルが見つかりません: {path}",
        "pt": "[ERRO] Arquivo RPF para patching não encontrado: {path}",
    },
    "repack.rpf7_invalid_magic": {
        "en": "[ERROR] Invalid RPF7 magic in {path}: 0x{magic:08X}",
        "ja": "[エラー] {path} の RPF7 マジックが不正です: 0x{magic:08X}",
        "pt": "[ERRO] Magic inválido para RPF7 em {path}: 0x{magic:08X}",
    },
    "repack.rpf_patch_failed": {
        "en": "[ERROR] Failed to patch RPF {path}: {error}",
        "ja": "[エラー] RPF {path} のパッチに失敗しました: {error}",
        "pt": "[ERRO] Falha ao aplicar patch no RPF {path}: {error}",
    },
    "repack.rpf7_patched_summary": {
        "en": "  [RPF7 PATCH] {filename}: enc='OPEN', patched {count} binary entries (f_size=0)",
        "ja": "  [RPF7 PATCH] {filename}: enc='OPEN', {count} 件のバイナリエントリをパッチしました (f_size=0)",
        "pt": "  [RPF7 PATCH] {filename}: enc='OPEN', corrigidas {count} entradas binárias (f_size=0)",
    },
    "repack.stage_line": {
        "en": "\n[STAGE {current}/{total}] {bar} {percent:5.1f}% | {title} ({elapsed:.1f}s elapsed)",
        "ja": "\n[段階 {current}/{total}] {bar} {percent:5.1f}% | {title} ({elapsed:.1f}秒経過)",
        "pt": "\n[ETAPA {current}/{total}] {bar} {percent:5.1f}% | {title} ({elapsed:.1f}s decorridos)",
    },
    "repack.pipeline_complete_line": {
        "en": "\n[PROGRESS] Pipeline Complete {bar} 100.0% (total time: {elapsed:.1f}s)",
        "ja": "\n[進捗] 全パイプライン完了 {bar} 100.0% (合計時間: {elapsed:.1f}秒)",
        "pt": "\n[PROGRESSO] Pipeline Completo {bar} 100.0% (tempo total: {elapsed:.1f}s)",
    },
    "repack.installing_start": {
        "en": "Installing {label} ({megabytes:.1f} MB) -> {dest}...",
        "ja": "{label} ({megabytes:.1f} MB) を {dest} にインストール中...",
        "pt": "Instalando {label} ({megabytes:.1f} MB) -> {dest}...",
    },
}
