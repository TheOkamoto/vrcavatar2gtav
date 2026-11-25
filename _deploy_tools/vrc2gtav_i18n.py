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
        reconfigure_func = getattr(stream_obj, "reconfigure", None)
        if callable(reconfigure_func):
            try:
                reconfigure_func(encoding="utf-8", errors="replace")
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
    normalized_python_locale = normalize_language_code(current_locale)
    if normalized_python_locale in SUPPORTED_LANGUAGES:
        return normalized_python_locale

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

try:
    from i18n_catalog_core_layer import CORE_TRANSLATION_CATALOG
    from i18n_catalog_builders_layer import BUILDERS_TRANSLATION_CATALOG
    from i18n_catalog_tests_physbones_layer import TESTS_PHYSBONES_TRANSLATION_CATALOG
except ImportError:
    from common_tools.i18n_catalog_core_layer import CORE_TRANSLATION_CATALOG
    from common_tools.i18n_catalog_builders_layer import BUILDERS_TRANSLATION_CATALOG
    from common_tools.i18n_catalog_tests_physbones_layer import TESTS_PHYSBONES_TRANSLATION_CATALOG

# Assemble complete trilingual message catalog from the three architectural layers
MESSAGES: Dict[str, Dict[str, str]] = {
    **CORE_TRANSLATION_CATALOG,
    **BUILDERS_TRANSLATION_CATALOG,
    **TESTS_PHYSBONES_TRANSLATION_CATALOG,
}
