"""
Trilingual internationalization (i18n) helper for the VRC Avatar to GTA V pipeline.

Supports English ("en"), Japanese ("ja"), and Portuguese ("pt") automatically
based on CLI arguments, environment overrides, optional vrc2gtav.cfg settings,
or the operating system locale, falling back to English when unsupported.
"""

import configparser
import ctypes
import locale
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


SUPPORTED_LANGUAGES: Tuple[str, ...] = ("en", "ja", "pt")
DEFAULT_LANGUAGE: str = "en"
LANG_ENV_VAR: str = "VRC2GTAV_LANG"

_UNSET_LOCALE_TOKENS = frozenset({"", "auto", "system", "default", "c", "c.utf-8", "c.utf8", "posix"})
_AFFIRMATIVE_ANSWERS = frozenset({"y", "yes", "s", "sim", "はい", "true", "1", "ok"})
_NEGATIVE_ANSWERS = frozenset({"n", "no", "nao", "não", "いいえ", "false", "0"})

_LANGUAGE_ALIASES: Dict[str, str] = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "ingles": "en",
    "inglês": "en",
    "英語": "en",
    "ja": "ja",
    "jp": "ja",
    "jpn": "ja",
    "japanese": "ja",
    "japones": "ja",
    "japonês": "ja",
    "日本語": "ja",
    "pt": "pt",
    "por": "pt",
    "pt_br": "pt",
    "pt-br": "pt",
    "pt_pt": "pt",
    "pt-pt": "pt",
    "portuguese": "pt",
    "portugues": "pt",
    "português": "pt",
    "ポルトガル語": "pt",
}

_LANGUAGE_DISPLAY_NAMES: Dict[str, str] = {
    "en": "English (en)",
    "ja": "日本語 (ja)",
    "pt": "Português (pt)",
}

_ACTIVE_LANGUAGE: Optional[str] = None
_STDIO_CONFIGURED: bool = False


def configure_utf8_stdio() -> None:
    """Ensure stdout and stderr handle UTF-8 cleanly across Windows and WSL terminals."""
    global _STDIO_CONFIGURED
    if _STDIO_CONFIGURED:
        return
    for stream_name in ("stdout", "stderr"):
        stream_obj = getattr(sys, stream_name, None)
        reconfigure_fn = getattr(stream_obj, "reconfigure", None)
        if callable(reconfigure_fn):
            try:
                reconfigure_fn(encoding="utf-8", errors="replace")
            except Exception:
                pass
    _STDIO_CONFIGURED = True


def normalize_language_code(raw_code: Optional[str]) -> Optional[str]:
    """Normalize a locale or language string to 'en', 'ja', 'pt', or None."""
    if raw_code is None:
        return None
    cleaned = str(raw_code).strip()
    if not cleaned:
        return None

    # Strip encoding and modifier suffixes such as ".UTF-8" or "@latin".
    base_token = cleaned.split(".", 1)[0].split("@", 1)[0].strip().lower()
    if base_token in _UNSET_LOCALE_TOKENS:
        return None

    normalized_hyphen = base_token.replace("-", "_")
    if normalized_hyphen in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[normalized_hyphen]

    primary_subtag = normalized_hyphen.split("_", 1)[0]
    return _LANGUAGE_ALIASES.get(primary_subtag)


def extract_cli_language(cli_args: Optional[Sequence[str]] = None) -> Optional[str]:
    """Extract an explicit '--lang <code|auto>' option from CLI arguments without parsing everything."""
    arg_list = list(sys.argv[1:] if cli_args is None else cli_args)
    for index, token in enumerate(arg_list):
        if token == "--lang" and index + 1 < len(arg_list):
            return arg_list[index + 1]
        if token.startswith("--lang="):
            return token.split("=", 1)[1]
    return None


def _read_language_from_cfg_file() -> Optional[str]:
    """Read optional [general] language setting from vrc2gtav.cfg if present."""
    candidate_paths: List[Path] = []
    for env_key in ("VRC2GTAV_CFG", "VRC2GTAV_CONFIG"):
        env_cfg = os.environ.get(env_key, "").strip()
        if env_cfg:
            candidate_paths.append(Path(env_cfg))

    here_dir = Path(__file__).resolve().parent
    for probe_dir in (here_dir, *here_dir.parents):
        candidate_paths.append(probe_dir / "vrc2gtav.cfg")
    candidate_paths.append(Path.cwd() / "vrc2gtav.cfg")

    seen_paths = set()
    for cfg_path in candidate_paths:
        try:
            resolved = cfg_path.resolve()
        except Exception:
            resolved = cfg_path
        if resolved in seen_paths or not resolved.is_file():
            continue
        seen_paths.add(resolved)
        parser = configparser.ConfigParser(
            interpolation=configparser.ExtendedInterpolation()
        )
        try:
            parser.read(resolved, encoding="utf-8")
        except Exception:
            continue
        if parser.has_section("general") and parser.has_option("general", "language"):
            raw_value = parser.get("general", "language", fallback="auto").strip()
            if raw_value.lower() not in ("", "auto", "system", "default"):
                return raw_value
        break
    return None


def _detect_windows_ui_language() -> Optional[str]:
    """Query Windows User Default UI Language via kernel32 without spawning external processes."""
    if os.name != "nt":
        return None
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except Exception:
        return None
    primary_lang_id = int(lang_id) & 0x03FF
    windows_primary_map = {
        0x09: "en",
        0x11: "ja",
        0x16: "pt",
    }
    return windows_primary_map.get(primary_lang_id)


def _iter_posix_env_locales() -> Iterable[str]:
    """Yield configured POSIX locale tokens from standard environment variables."""
    for env_key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        env_value = os.environ.get(env_key, "").strip()
        if env_value:
            yield env_value
    language_list = os.environ.get("LANGUAGE", "").strip()
    if language_list:
        for entry in language_list.split(":"):
            cleaned_entry = entry.strip()
            if cleaned_entry:
                yield cleaned_entry


def detect_system_language(
    config_language: Optional[str] = None,
    cli_args: Optional[Sequence[str]] = None,
) -> str:
    """
    Resolve the active language code ('en', 'ja', or 'pt') using priority order:
    1. '--lang' CLI argument (unless 'auto')
    2. 'VRC2GTAV_LANG' environment variable (unless 'auto')
    3. 'config_language' argument or [general] language in vrc2gtav.cfg (unless 'auto')
    4. POSIX locale env vars (LC_ALL, LC_MESSAGES, LANG, LANGUAGE)
    5. Windows UI Language / Python locale.getlocale()
    6. Fallback to 'en'
    """
    explicit_lang = get_explicit_language_override(
        config_language=config_language,
        cli_args=cli_args,
    )
    if explicit_lang in SUPPORTED_LANGUAGES:
        return explicit_lang

    windows_lang = _detect_windows_ui_language()
    if windows_lang in SUPPORTED_LANGUAGES:
        return windows_lang

    try:
        current_locale, _encoding = locale.getlocale()
    except Exception:
        current_locale = None
    normalized_py_locale = normalize_language_code(current_locale)
    if normalized_py_locale in SUPPORTED_LANGUAGES:
        return normalized_py_locale

    return DEFAULT_LANGUAGE


def get_explicit_language_override(
    config_language: Optional[str] = None,
    cli_args: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """Return an explicit language selection from CLI, env, cfg, or POSIX locale, or None."""
    cli_lang_raw = extract_cli_language(cli_args)
    if cli_lang_raw is not None:
        normalized_cli = normalize_language_code(cli_lang_raw)
        if normalized_cli in SUPPORTED_LANGUAGES:
            return normalized_cli
        if str(cli_lang_raw).strip().lower() not in ("auto", "system", "default"):
            return DEFAULT_LANGUAGE

    env_lang_raw = os.environ.get(LANG_ENV_VAR, "").strip()
    if env_lang_raw:
        normalized_env = normalize_language_code(env_lang_raw)
        if normalized_env in SUPPORTED_LANGUAGES:
            return normalized_env
        if env_lang_raw.lower() not in ("auto", "system", "default"):
            return DEFAULT_LANGUAGE

    cfg_lang_raw = config_language if config_language is not None else _read_language_from_cfg_file()
    if cfg_lang_raw:
        normalized_cfg = normalize_language_code(cfg_lang_raw)
        if normalized_cfg in SUPPORTED_LANGUAGES:
            return normalized_cfg

    for locale_token in _iter_posix_env_locales():
        normalized_locale = normalize_language_code(locale_token)
        if normalized_locale in SUPPORTED_LANGUAGES:
            return normalized_locale

    return None


def set_active_language(
    language_code: Optional[str] = None,
    cli_args: Optional[Sequence[str]] = None,
) -> str:
    """Set and return the active language code ('en', 'ja', or 'pt')."""
    global _ACTIVE_LANGUAGE
    configure_utf8_stdio()
    if language_code is None or str(language_code).strip().lower() in ("", "auto", "system", "default"):
        resolved = detect_system_language(cli_args=cli_args)
    else:
        resolved = normalize_language_code(language_code) or DEFAULT_LANGUAGE
    _ACTIVE_LANGUAGE = resolved
    return resolved


def get_active_language() -> str:
    """Return the active language code, detecting it lazily on first use."""
    global _ACTIVE_LANGUAGE
    configure_utf8_stdio()
    if _ACTIVE_LANGUAGE is None:
        _ACTIVE_LANGUAGE = detect_system_language()
    return _ACTIVE_LANGUAGE


def get_language_display_name(language_code: Optional[str] = None) -> str:
    """Return a human-readable label for a language code."""
    resolved = normalize_language_code(language_code) if language_code else get_active_language()
    return _LANGUAGE_DISPLAY_NAMES.get(resolved or DEFAULT_LANGUAGE, "English (en)")


def is_affirmative_answer(answer_text: Optional[str], default_yes: bool = True) -> bool:
    """Parse yes/no answers across English, Japanese, and Portuguese."""
    if answer_text is None:
        return default_yes
    cleaned = str(answer_text).strip().lower()
    if not cleaned:
        return default_yes
    if cleaned in _NEGATIVE_ANSWERS:
        return False
    if cleaned in _AFFIRMATIVE_ANSWERS:
        return True
    return default_yes if cleaned not in ("n", "no") else False


def register_messages(extra_messages: Dict[str, Dict[str, str]]) -> None:
    """Merge additional translation entries into the global MESSAGES catalog."""
    for message_key, translations in extra_messages.items():
        MESSAGES[message_key] = dict(translations)


def translate(message_key: str, **format_kwargs: object) -> str:
    """Look up and format a translated message for the active language."""
    active_lang = get_active_language()
    translations = MESSAGES.get(message_key)
    if not translations:
        return message_key
    template = translations.get(active_lang) or translations.get(DEFAULT_LANGUAGE) or message_key
    if not format_kwargs:
        return template
    try:
        return template.format(**format_kwargs)
    except Exception:
        return template


# Trilingual message catalog: every entry must define 'en', 'ja', and 'pt'
# with identical format placeholders so automated tests verify 100% parity.
MESSAGES: Dict[str, Dict[str, str]] = {
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
        "en": "      Glasses dummies (p_eyes_*.ydd, {size_bytes} B): {count}",
        "ja": "      眼鏡ダミー置換 (p_eyes_*.ydd, {size_bytes} B): {count}",
        "pt": "      Dummies de óculos (p_eyes_*.ydd, {size_bytes} B): {count}",
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
    # -----------------------------------------------------------------------
    # Michael (Shinano Eternal Reunion) scripts
    # -----------------------------------------------------------------------
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
    # -----------------------------------------------------------------------
    # Trevor (Miltina Maid) scripts
    # -----------------------------------------------------------------------
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
    # -----------------------------------------------------------------------
    # Automated Test Suite (test_mod_suite.py)
    # -----------------------------------------------------------------------
    "tests.cli_desc": {
        "en": "Automated validation suite for the vrc2gtav project",
        "ja": "vrc2gtav プロジェクトの自動検証テストスイート",
        "pt": "Suíte de testes automatizados do projeto vrc2gtav",
    },
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
        "en": "{character}: no p_eyes_*.ydd found",
        "ja": "{character}: p_eyes_*.ydd なし",
        "pt": "{character}: nenhum p_eyes_*.ydd encontrado",
    },
    "tests.glasses_label": {
        "en": "Glasses dummies in staging (streamedpedprops)",
        "ja": "ステージング内メガネダミー (streamedpedprops)",
        "pt": "Dummies de óculos em staging (streamedpedprops)",
    },
    "tests.glasses_ok": {
        "en": "{count}/35 p_eyes_*.ydd identical to p_eyes_dummy.ydd",
        "ja": "{count}/35 個の p_eyes_*.ydd が p_eyes_dummy.ydd と一致",
        "pt": "{count}/35 p_eyes_*.ydd idênticos a p_eyes_dummy.ydd",
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
        "en": "Identifiers >= 3 chars: {path}",
        "ja": "識別子 >= 3 文字: {path}",
        "pt": "Identificadores >= 3 caracteres: {path}",
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
    "franklin.atlas.hair_fallback": {
        "en": "[INFO] Custom Franklin hair texture missing; calibrating base Shinano_hair.png.",
        "ja": "[INFO] カスタム髪テクスチャが見つからないため基本 Shinano_hair.png を調整して使用します。",
        "pt": "[INFO] Textura de cabelo customizada ausente; calibrando Shinano_hair.png padrão.",
    },
    "franklin.atlas.eye_fallback": {
        "en": "[INFO] Optional face/eye layers absent ({layers}); keeping base Shinano_face.png eyes.",
        "ja": "[INFO] オプションの目・メイク素材不在 ({layers}) のため基本 Shinano_face.png の目を使用します。",
        "pt": "[INFO] Camadas opcionais de rosto/olhos ausentes ({layers}); mantendo olhos de Shinano_face.png.",
    },
    "michael.atlas.hair_fallback": {
        "en": "[INFO] Custom hair asset absent ({reason}); calibrating default Shinano hair in cell (2, 0).",
        "ja": "[INFO] カスタム髪不在 ({reason}) のためセル (2, 0) に標準 Shinano 髪を調整配置します。",
        "pt": "[INFO] Cabelo customizado ausente ({reason}); calibrando cabelo padrão da Shinano na célula (2, 0).",
    },
    "michael.atlas.eye_fallback": {
        "en": "[INFO] Optional face/eye layers absent ({layers}); keeping base Shinano_face.png eyes.",
        "ja": "[INFO] オプションの目・メイク素材不在 ({layers}) のため基本 Shinano_face.png の目を使用します。",
        "pt": "[INFO] Camadas opcionais de rosto/olhos ausentes ({layers}); mantendo olhos de Shinano_face.png.",
    },
    "michael.atlas.accessory_skip": {
        "en": "[INFO] Optional hair accessory texture absent ({key}: {path}); skipping sub-cell.",
        "ja": "[INFO] オプション髪アクセサリ不在 ({key}: {path}) のためサブセルをスキップします。",
        "pt": "[INFO] Textura opcional de acessório capilar ausente ({key}: {path}); ignorando subcélula.",
    },
    "trevor.atlas.hair_fallback": {
        "en": "[INFO] Using Miltina default hair calibrated from Milltina_Hair.png (lilToon material).",
        "ja": "[INFO] Milltina_Hair.png を lilToon マテリアル基準で調整した標準髪を使用します。",
        "pt": "[INFO] Usando cabelo padrão da Miltina calibrado de Milltina_Hair.png (material lilToon).",
    },
    "trevor.atlas.hair_custom": {
        "en": "[INFO] Using custom hair texture override for Miltina: {path}",
        "ja": "[INFO] Miltina 用カスタム髪テクスチャの上書きを使用します: {path}",
        "pt": "[INFO] Usando textura de cabelo customizada para Miltina: {path}",
    },
    "trevor.atlas.eye_fallback": {
        "en": "[INFO] Optional AWEyes textures absent; keeping default Milltina_Face.png eyes.",
        "ja": "[INFO] オプションの AWEyes 目素材が不在のため基本 Milltina_Face.png の目を使用します。",
        "pt": "[INFO] Texturas opcionais AWEyes ausentes; mantendo os olhos padrão de Milltina_Face.png.",
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
    "avatar.shinano_casual": {
        "en": "Shinano Casual",
        "ja": "しなの (カジュアル)",
        "pt": "Shinano Casual",
    },
    "avatar.shinano_er": {
        "en": "Shinano Eternal Reunion",
        "ja": "しなの (Eternal Reunion)",
        "pt": "Shinano Eternal Reunion",
    },
    "avatar.miltina_maid": {
        "en": "Miltina Maid",
        "ja": "ミルティナ (メイド)",
        "pt": "Miltina Maid",
    },
    "paths.unknown_protagonist": {
        "en": "Unknown GTA V protagonist '{name}'. Expected: michael, franklin, or trevor.",
        "ja": "不明な GTA V 主人公 '{name}' です。michael, franklin, trevor を指定してください。",
        "pt": "Protagonista desconhecido do GTA V '{name}'. Esperado: michael, franklin ou trevor.",
    },
    "paths.unknown_avatar": {
        "en": "Unknown VRChat avatar preset '{name}'. Expected: shinano_casual, shinano_er, or miltina_maid.",
        "ja": "不明な VRChat アバタープリセット '{name}' です。shinano_casual, shinano_er, miltina_maid を指定してください。",
        "pt": "Preset de avatar VRChat desconhecido '{name}'. Esperado: shinano_casual, shinano_er ou miltina_maid.",
    },
    "manager.cli_avatar": {
        "en": "VRChat avatar preset to build/apply (shinano_casual, shinano_er, miltina_maid)",
        "ja": "ビルド/適用する VRChat アバタープリセット (shinano_casual, shinano_er, miltina_maid)",
        "pt": "Preset de avatar VRChat para compilar/aplicar (shinano_casual, shinano_er, miltina_maid)",
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
    "franklin.build.cli_desc": {
        "en": "Shinano Casual to GTA V Blender compiler (interchangeable across protagonists)",
        "ja": "Shinano Casual -> GTA V Blender コンパイラ (主人公切替対応)",
        "pt": "Compilador Shinano Casual para GTA V no Blender (intercambiável entre protagonistas)",
    },
    "franklin.build.arg_target_char": {
        "en": "Target GTA V protagonist slot (michael, franklin, trevor)",
        "ja": "ビルド先の GTA V 主人公スロット (michael, franklin, trevor)",
        "pt": "Protagonista alvo do GTA V (michael, franklin, trevor)",
    },
    "trevor.build.arg_target_char": {
        "en": "Target GTA V protagonist slot (michael, franklin, trevor)",
        "ja": "ビルド先の GTA V 主人公スロット (michael, franklin, trevor)",
        "pt": "Protagonista alvo do GTA V (michael, franklin, trevor)",
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
        "en": "All 3 builders & runners expose --target-character across michael/franklin/trevor",
        "ja": "全 3 ビルド/ランナースクリプトが michael/franklin/trevor 向け --target-character に対応",
        "pt": "Todos os 3 builders e runners aceitam --target-character para michael/franklin/trevor",
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
        "en": "  [{opt}] All Avatars (Shinano Casual, Shinano ER, Milltina)",
        "ja": "  [{opt}] 全アバター (Shinano Casual, Shinano ER, Milltina)",
        "pt": "  [{opt}] Todos os Avatares (Shinano Casual, Shinano ER, Milltina)",
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
}
