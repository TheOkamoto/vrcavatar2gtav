#!/usr/bin/env python3
"""
vrc2gtav_paths.py
=================
Centralized cross-platform configuration and path resolver (native Windows
and Linux/WSL) backed by vrc2gtav.cfg.

All project scripts import this module to obtain executable, directory, model,
texture, skeleton, .fbx, and RPF archive paths without hardcoding paths in code.
"""

import configparser
import os as operating_system
import platform
import re as regex_module
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

from vrc2gtav_i18n import (
    LANG_ENV_VAR,
    configure_utf8_stdio,
    get_active_language,
    get_explicit_language_override,
    get_language_display_name,
    translate,
)

configure_utf8_stdio()


CONFIG_ENV_VAR_NAME = "VRC2GTAV_CFG"
DEFAULT_CONFIG_FILENAME = "vrc2gtav.cfg"
DEFAULT_CONFIG_EXAMPLE_FILENAME = "vrc2gtav.cfg.example"

_CONFIG_CACHE: Dict[str, object] = {
    "config_path": None,
    "parser": None,
    "mtime": None,
}


def invalidate_config_cache() -> None:
    """Clear the cached .cfg parser state to force an immediate reload on next read."""
    _CONFIG_CACHE["config_path"] = None
    _CONFIG_CACHE["parser"] = None
    _CONFIG_CACHE["mtime"] = None


def is_windows_host() -> bool:
    """Return True when the active Python interpreter is running on Windows."""
    return platform.system() == "Windows"


def is_wsl_host() -> bool:
    """Return True when Python is running inside Windows Subsystem for Linux."""
    if is_windows_host():
        return False
    release_text = platform.release().lower()
    return ("microsoft" in release_text) or Path("/mnt/c/Windows").exists()


def to_host_path(raw_path_text: str, project_root_dir: Optional[Path] = None) -> Path:
    """
    Convert a .cfg path string (Windows X:/..., WSL /mnt/x/..., POSIX /home/...,
    or relative path) into a native pathlib.Path for the current host OS.
    """
    if not raw_path_text or not str(raw_path_text).strip():
        raise ValueError(translate("paths.empty_path_error"))

    normalized_text = str(raw_path_text).strip().strip('"').strip("'")
    normalized_slashes = normalized_text.replace("\\", "/")

    windows_drive_match = regex_module.match(r"^([A-Za-z]):/(.*)$", normalized_slashes)
    wsl_mount_match = regex_module.match(r"^/mnt/([a-zA-Z])/(.*)$", normalized_slashes)

    if is_windows_host():
        if wsl_mount_match:
            drive_letter = wsl_mount_match.group(1).upper()
            remaining_path = wsl_mount_match.group(2)
            return Path(f"{drive_letter}:/{remaining_path}")
        if windows_drive_match:
            return Path(normalized_slashes)
        candidate_path = Path(normalized_slashes)
        if not candidate_path.is_absolute() and project_root_dir is not None:
            return (project_root_dir / candidate_path).resolve()
        return candidate_path

    # Linux / WSL environment
    if windows_drive_match:
        drive_letter = windows_drive_match.group(1).lower()
        remaining_path = windows_drive_match.group(2)
        return Path(f"/mnt/{drive_letter}/{remaining_path}")
    if wsl_mount_match or normalized_slashes.startswith("/"):
        return Path(normalized_slashes)

    candidate_path = Path(normalized_slashes)
    if project_root_dir is not None:
        return (project_root_dir / candidate_path).resolve()
    return candidate_path.resolve()


def to_windows_path(raw_path_value: Union[str, Path], use_backslashes: bool = False) -> str:
    """
    Convert any host path (/mnt/e/... or E:/...) to Windows format (E:/... or E:\\...).
    Required when invoking Windows executables (such as blender.exe) from WSL.
    """
    path_text = str(raw_path_value).strip().strip('"').strip("'")
    normalized_slashes = path_text.replace("\\", "/")

    wsl_mount_match = regex_module.match(r"^/mnt/([a-zA-Z])/(.*)$", normalized_slashes)
    if wsl_mount_match:
        drive_letter = wsl_mount_match.group(1).upper()
        remaining_path = wsl_mount_match.group(2)
        converted_path = f"{drive_letter}:/{remaining_path}"
    else:
        converted_path = normalized_slashes

    if use_backslashes:
        return converted_path.replace("/", "\\")
    return converted_path


def find_project_config_file(explicit_config_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Locate vrc2gtav.cfg using priority order:
      1. Explicit path argument, if provided
      2. VRC2GTAV_CFG environment variable, if set
      3. Upward directory scan from this module and current working directory
    """
    if explicit_config_path is not None:
        explicit_file = Path(explicit_config_path).expanduser().resolve()
        if explicit_file.is_file():
            return explicit_file
        raise FileNotFoundError(
            translate("paths.config_not_found_explicit", path=explicit_file)
        )

    env_override = operating_system.environ.get(CONFIG_ENV_VAR_NAME, "").strip()
    if env_override:
        env_file = Path(env_override).expanduser().resolve()
        if env_file.is_file():
            return env_file
        raise FileNotFoundError(
            translate(
                "paths.config_not_found_env",
                env_var=CONFIG_ENV_VAR_NAME,
                path=env_file,
            )
        )

    search_origins = [Path(__file__).resolve().parent, Path.cwd().resolve()]
    for origin_dir in search_origins:
        for candidate_dir in [origin_dir] + list(origin_dir.parents):
            candidate_cfg = candidate_dir / DEFAULT_CONFIG_FILENAME
            if candidate_cfg.is_file():
                return candidate_cfg.resolve()

    raise FileNotFoundError(
        translate(
            "paths.config_not_found_default",
            filename=DEFAULT_CONFIG_FILENAME,
            env_var=CONFIG_ENV_VAR_NAME,
        )
    )


def has_project_config_file(
    explicit_config_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Return True if vrc2gtav.cfg (or an explicit/VRC2GTAV_CFG path) exists."""
    try:
        find_project_config_file(explicit_config_path)
        return True
    except FileNotFoundError:
        return False


def find_project_config_example(
    explicit_example_path: Optional[Union[str, Path]] = None,
) -> Path:
    """Locate the vrc2gtav.cfg.example template in the project root."""
    if explicit_example_path is not None:
        explicit_file = Path(explicit_example_path).expanduser().resolve()
        if explicit_file.is_file():
            return explicit_file
        raise FileNotFoundError(
            translate("paths.template_not_found_explicit", path=explicit_file)
        )

    search_origins = [Path(__file__).resolve().parent, Path.cwd().resolve()]
    for origin_dir in search_origins:
        for candidate_dir in [origin_dir] + list(origin_dir.parents):
            candidate_example = candidate_dir / DEFAULT_CONFIG_EXAMPLE_FILENAME
            if candidate_example.is_file():
                return candidate_example.resolve()

    raise FileNotFoundError(
        translate(
            "paths.template_not_found_default",
            filename=DEFAULT_CONFIG_EXAMPLE_FILENAME,
        )
    )


def ensure_project_config_from_example(
    project_root_hint: Optional[Path] = None,
) -> Path:
    """
    Ensure vrc2gtav.cfg exists by copying vrc2gtav.cfg.example if missing.
    """
    if has_project_config_file():
        return find_project_config_file()

    example_file = find_project_config_example()
    target_root = (
        Path(project_root_hint).resolve()
        if project_root_hint is not None
        else example_file.parent
    )
    target_cfg_file = target_root / DEFAULT_CONFIG_FILENAME
    shutil.copy2(example_file, target_cfg_file)
    return target_cfg_file.resolve()


def load_project_config(
    config_file_path: Optional[Union[str, Path]] = None,
    force_reload: bool = False,
) -> configparser.ConfigParser:
    """
    Load and parse vrc2gtav.cfg with ExtendedInterpolation (${section:key}),
    dynamically resolving project_root when set to '.' and caching by mtime.
    """
    resolved_cfg_file = find_project_config_file(config_file_path)
    try:
        current_mtime = resolved_cfg_file.stat().st_mtime
    except OSError as os_error:
        raise FileNotFoundError(
            translate("paths.config_stat_error", path=resolved_cfg_file, error=os_error)
        ) from os_error

    if (
        not force_reload
        and _CONFIG_CACHE["parser"] is not None
        and _CONFIG_CACHE["config_path"] == resolved_cfg_file
        and _CONFIG_CACHE["mtime"] == current_mtime
    ):
        return _CONFIG_CACHE["parser"]  # type: ignore[return-value]

    parser = configparser.ConfigParser(
        interpolation=configparser.ExtendedInterpolation()
    )
    # Preserve exact option key casing.
    parser.optionxform = str  # type: ignore[assignment]

    try:
        read_files = parser.read(str(resolved_cfg_file), encoding="utf-8")
    except configparser.Error as parse_error:
        raise RuntimeError(
            translate("paths.config_parse_error", path=resolved_cfg_file, error=parse_error)
        ) from parse_error

    if not read_files:
        raise FileNotFoundError(
            translate("paths.config_open_error", path=resolved_cfg_file)
        )

    if not parser.has_section("directories"):
        raise ValueError(
            translate("paths.config_missing_directories", path=resolved_cfg_file)
        )

    raw_project_root = parser.get(
        "directories", "project_root", fallback=".", raw=True
    ).strip()
    if raw_project_root in ("", "."):
        effective_root = resolved_cfg_file.parent.resolve()
    else:
        effective_root = to_host_path(
            raw_project_root, project_root_dir=resolved_cfg_file.parent.resolve()
        )

    parser.set("directories", "project_root", effective_root.as_posix())

    _CONFIG_CACHE["config_path"] = resolved_cfg_file
    _CONFIG_CACHE["parser"] = parser
    _CONFIG_CACHE["mtime"] = current_mtime
    return parser


def get_configured_language() -> str:
    """Return [general] -> language from vrc2gtav.cfg, or 'auto' if absent."""
    if not has_project_config_file():
        return "auto"
    parser = load_project_config()
    if parser.has_section("general") and parser.has_option("general", "language"):
        value_text = parser.get("general", "language", fallback="auto").strip()
        return value_text if value_text else "auto"
    return "auto"


def get_config_value(section_name: str, option_name: str) -> str:
    """Return an interpolated value from vrc2gtav.cfg with a descriptive error if missing."""
    parser = load_project_config()
    cfg_file = find_project_config_file()
    if not parser.has_section(section_name):
        raise KeyError(
            translate("paths.section_not_found", section=section_name, path=cfg_file)
        )
    if not parser.has_option(section_name, option_name):
        raise KeyError(
            translate(
                "paths.option_not_found",
                option=option_name,
                section=section_name,
                path=cfg_file,
            )
        )
    return parser.get(section_name, option_name).strip()


def get_project_root() -> Path:
    """Return the resolved project root directory from [directories] -> project_root."""
    raw_root_value = get_config_value("directories", "project_root")
    return to_host_path(raw_root_value)


def get_config_path(
    section_name: str,
    option_name: str,
    as_windows_path: bool = False,
) -> Union[Path, str]:
    """
    Resolve a .cfg path entry into a native host Path (or Windows string when
    as_windows_path=True).
    """
    raw_value = get_config_value(section_name, option_name)
    resolved_host_path = to_host_path(raw_value, project_root_dir=get_project_root())
    if as_windows_path:
        return to_windows_path(resolved_host_path)
    return resolved_host_path


def get_config_path_list(
    section_name: str,
    option_name: str,
    as_windows_path: bool = False,
) -> List[Union[Path, str]]:
    """Resolve a comma-separated .cfg list entry into host Paths or Windows strings."""
    raw_list_text = get_config_value(section_name, option_name)
    resolved_items: List[Union[Path, str]] = []
    root_directory = get_project_root()
    for raw_item in raw_list_text.split(","):
        cleaned_item = raw_item.strip()
        if not cleaned_item:
            continue
        item_path = to_host_path(cleaned_item, project_root_dir=root_directory)
        resolved_items.append(
            to_windows_path(item_path) if as_windows_path else item_path
        )
    return resolved_items


def get_vrc_assets_dir() -> Path:
    """Return the Unity project Assets directory configured in vrc2gtav.cfg."""
    return Path(get_config_path("directories", "unity_assets"))


def get_staging_dir() -> Path:
    """Return the staging directory configured in vrc2gtav.cfg."""
    return Path(get_config_path("directories", "staging"))


def get_gtav_root_dir() -> Path:
    """Return the GTA V installation root directory configured in vrc2gtav.cfg."""
    return Path(get_config_path("directories", "gtav_root"))


def get_gtav_mods_dir() -> Path:
    """Return the GTA V mods directory configured in vrc2gtav.cfg."""
    return Path(get_config_path("directories", "gtav_mods"))


def get_deploy_tools_dir() -> Path:
    """Return the _deploy_tools directory configured in vrc2gtav.cfg."""
    return Path(get_config_path("directories", "deploy_tools"))


def get_scripts_root_dir() -> Path:
    """Return the scripts root directory configured in vrc2gtav.cfg."""
    return Path(get_config_path("directories", "scripts_root"))


def get_common_tools_dir() -> Path:
    """Return the scripts/common_tools directory configured in vrc2gtav.cfg."""
    return Path(get_config_path("directories", "common_tools"))


def get_artifacts_dir() -> Path:
    """Return the artifacts directory configured in vrc2gtav.cfg (or an inert fallback if empty)."""
    raw_artifacts_value = get_config_value("directories", "artifacts").strip()
    if not raw_artifacts_value:
        return get_staging_dir() / "_no_artifacts_configured"
    return Path(get_config_path("directories", "artifacts"))


def get_renders_output_dir() -> Path:
    """Return the renders output directory configured in vrc2gtav.cfg."""
    return Path(get_config_path("directories", "renders_output"))


def get_dummy_ydd_path() -> Path:
    """Return the head_000_r.ydd dummy mesh path from [common_assets]."""
    return Path(get_config_path("common_assets", "dummy_ydd"))


def get_prop_dummy_ydd_path() -> Path:
    """Return the p_eyes_dummy.ydd prop dummy mesh path from [common_assets]."""
    return Path(get_config_path("common_assets", "prop_dummy_ydd"))


def get_rage_cli() -> str:
    """Return the RAGE CLI executable or command configured in [executables] -> rage."""
    raw_rage_value = get_config_value("executables", "rage").strip()
    if raw_rage_value:
        if "/" not in raw_rage_value and "\\" not in raw_rage_value:
            located_binary = shutil.which(raw_rage_value)
            if located_binary:
                return located_binary
            return raw_rage_value
        host_rage_path = to_host_path(raw_rage_value, project_root_dir=get_project_root())
        if host_rage_path.is_file():
            return str(host_rage_path)
        if is_windows_host():
            return f"wsl {raw_rage_value}"
        return str(host_rage_path)

    exe_name = "rage.exe" if is_windows_host() else "rage"
    for cand_dir in (get_staging_dir().parent / "tools", get_project_root() / "tools"):
        if (cand_dir / exe_name).is_file():
            return str(cand_dir / exe_name)
    return shutil.which(exe_name) or shutil.which("rage") or ""


def build_rage_command(*rage_args: str) -> List[str]:
    """Build an argument list to invoke the RAGE CLI natively or via WSL."""
    rage_executable = get_rage_cli()
    if rage_executable.startswith("wsl "):
        wsl_binary = rage_executable[4:].strip()
        return ["wsl", wsl_binary, *rage_args]
    return [rage_executable, *rage_args]


def get_blender_exe(as_windows_path: bool = False) -> str:
    """Return the Blender executable path configured in [executables] -> blender."""
    raw_blender_value = get_config_value("executables", "blender")
    if "/" not in raw_blender_value and "\\" not in raw_blender_value:
        located_binary = shutil.which(raw_blender_value)
        return located_binary if located_binary else raw_blender_value
    host_blender_path = to_host_path(
        raw_blender_value, project_root_dir=get_project_root()
    )
    if as_windows_path:
        return to_windows_path(host_blender_path)
    return str(host_blender_path)


def get_python_exe() -> str:
    """Return the Python executable path from [executables] -> python, with sys.executable fallback."""
    raw_python_value = get_config_value("executables", "python")
    if "/" not in raw_python_value and "\\" not in raw_python_value:
        located_binary = shutil.which(raw_python_value)
        return located_binary if located_binary else sys.executable
    host_python_path = to_host_path(
        raw_python_value, project_root_dir=get_project_root()
    )
    if host_python_path.exists():
        return str(host_python_path)
    return sys.executable


def get_ffmpeg_exe() -> str:
    """Return the ffmpeg executable path configured in [executables] -> ffmpeg."""
    raw_ffmpeg_value = get_config_value("executables", "ffmpeg")
    if "/" not in raw_ffmpeg_value and "\\" not in raw_ffmpeg_value:
        located_binary = shutil.which(raw_ffmpeg_value)
        return located_binary if located_binary else raw_ffmpeg_value
    return str(to_host_path(raw_ffmpeg_value, project_root_dir=get_project_root()))


def get_windows_cmd_exe() -> Path:
    """Return the Windows cmd.exe path configured in [executables] -> windows_cmd."""
    return Path(get_config_path("executables", "windows_cmd"))


def find_working_wsl_interop() -> Optional[str]:
    """
    Under WSL, locate a working /run/WSL/*_interop socket in case the current
    session socket expired after a suspend/reconnect.
    """
    if not is_wsl_host():
        return None
    cmd_host_path = get_windows_cmd_exe()
    candidate_sockets: List[str] = []
    current_socket = operating_system.environ.get("WSL_INTEROP", "").strip()
    if current_socket:
        candidate_sockets.append(current_socket)

    wsl_run_dir = Path("/run/WSL")
    if wsl_run_dir.is_dir():
        for socket_file in sorted(wsl_run_dir.glob("*_interop")):
            socket_str = str(socket_file)
            if socket_str not in candidate_sockets:
                candidate_sockets.append(socket_str)

    if not cmd_host_path.exists():
        return current_socket or None

    for socket_candidate in candidate_sockets:
        test_env = operating_system.environ.copy()
        test_env["WSL_INTEROP"] = socket_candidate
        try:
            probe_result = subprocess.run(
                [str(cmd_host_path), "/c", "echo", "OK"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=3,
                env=test_env,
            )
            if probe_result.returncode == 0:
                return socket_candidate
        except (OSError, subprocess.SubprocessError):
            continue
    return current_socket or None


def build_blender_command(
    blender_script_path: Union[str, Path],
    extra_arguments: Optional[List[str]] = None,
) -> Tuple[List[str], Dict[str, str]]:
    """
    Construct the command line and environment variables to execute a Blender
    Python script on either native Windows or Linux/WSL (via Windows interop).
    """
    custom_env = operating_system.environ.copy()
    blender_host_exe = get_blender_exe(as_windows_path=False)
    extra_tokens = list(extra_arguments) if extra_arguments else []

    explicit_lang = get_explicit_language_override(config_language=get_configured_language())
    if explicit_lang and not custom_env.get(LANG_ENV_VAR, "").strip():
        custom_env[LANG_ENV_VAR] = explicit_lang

    if is_windows_host():
        custom_env[CONFIG_ENV_VAR_NAME] = str(find_project_config_file())
        command_list = [
            blender_host_exe,
            "-b",
            "--python-exit-code",
            "1",
            "-P",
            str(blender_script_path),
        ]
        if extra_tokens:
            command_list.append("--")
            command_list.extend(extra_tokens)
        return command_list, custom_env

    # Under WSL targeting a Windows blender.exe, invoke directly via binfmt_misc
    # to avoid cmd.exe quoting issues and forward env variables via WSLENV.
    if blender_host_exe.lower().endswith(".exe"):
        custom_env[CONFIG_ENV_VAR_NAME] = to_windows_path(find_project_config_file())
        working_interop = find_working_wsl_interop()
        if working_interop:
            custom_env["WSL_INTEROP"] = working_interop

        propagated_vars = [
            env_token.strip()
            for env_token in custom_env.get("WSLENV", "").split(":")
            if env_token.strip()
        ]
        if CONFIG_ENV_VAR_NAME not in propagated_vars:
            propagated_vars.append(CONFIG_ENV_VAR_NAME)
        if custom_env.get(LANG_ENV_VAR, "").strip() and not any(
            existing.split("/")[0] == LANG_ENV_VAR for existing in propagated_vars
        ):
            propagated_vars.append(LANG_ENV_VAR)
        for path_env_key in ("VRC2GTAV_ROOT", "VRC_ASSETS_DIR", "GTAV_MODS_DIR", "RAGE_CLI", "BLENDER_EXE"):
            if path_env_key in custom_env and not any(
                existing.split("/")[0] == path_env_key for existing in propagated_vars
            ):
                propagated_vars.append(f"{path_env_key}/p")
        custom_env["WSLENV"] = ":".join(propagated_vars)

        script_win_path = to_windows_path(blender_script_path)
        command_list = [
            blender_host_exe,
            "-b",
            "--python-exit-code",
            "1",
            "-P",
            script_win_path,
        ]
        path_value_flags = {
            "--output-dir",
            "--texture-dir",
            "--skeleton-yft",
            "--target-yft",
            "--hair-fbx",
            "--hair-mat",
            "--hair-tex",
            "--unity-scene",
            "--blendshapes-cfg",
            "--save-blendshapes-cfg",
            "--physbones-cfg",
            "--save-physbones-cfg",
            "--face-anim",
            "--shinano-fbx",
            "--outfit-fbx",
            "--watch-fbx",
            "--miltina-fbx",
            "--outfit-blend",
            "--base-ydd",
        }
        non_path_hair_presets = {
            "auto",
            "default",
            "none",
            "bald",
            "no_hair",
            "default_er",
        }

        def _convert_cli_path_arg(raw_arg_val: str, is_hair_flag: bool = False) -> str:
            trimmed_val = str(raw_arg_val).strip()
            if not trimmed_val:
                return raw_arg_val
            if is_hair_flag and trimmed_val.lower() in non_path_hair_presets:
                return raw_arg_val
            return to_windows_path(trimmed_val)

        if extra_tokens:
            converted_tokens = []
            token_idx = 0
            while token_idx < len(extra_tokens):
                curr_tok = extra_tokens[token_idx]
                if curr_tok in path_value_flags or curr_tok == "--hair":
                    converted_tokens.append(curr_tok)
                    if token_idx + 1 < len(extra_tokens):
                        next_tok = extra_tokens[token_idx + 1]
                        converted_tokens.append(
                            _convert_cli_path_arg(
                                next_tok,
                                is_hair_flag=(curr_tok == "--hair"),
                            )
                        )
                        token_idx += 2
                        continue
                elif "=" in curr_tok and curr_tok.startswith("--"):
                    flag_name, flag_val = curr_tok.split("=", 1)
                    if flag_name in path_value_flags or flag_name == "--hair":
                        converted_val = _convert_cli_path_arg(
                            flag_val,
                            is_hair_flag=(flag_name == "--hair"),
                        )
                        converted_tokens.append(f"{flag_name}={converted_val}")
                        token_idx += 1
                        continue
                converted_tokens.append(curr_tok)
                token_idx += 1
            command_list.append("--")
            command_list.extend(converted_tokens)
        return command_list, custom_env

    # Native Linux Blender
    custom_env[CONFIG_ENV_VAR_NAME] = str(find_project_config_file())
    command_list = [
        blender_host_exe,
        "-b",
        "--python-exit-code",
        "1",
        "-P",
        str(blender_script_path),
    ]
    if extra_tokens:
        command_list.append("--")
        command_list.extend(extra_tokens)
    return command_list, custom_env


def extract_custom_blender_args(argv_tokens: Optional[List[str]] = None) -> List[str]:
    """
    Return custom CLI arguments passed after `--`, avoiding Blender's own flags
    when a script is invoked via `blender -b -P script.py` without `--`.
    """
    raw_arguments = list(sys.argv) if argv_tokens is None else list(argv_tokens)
    if "--" in raw_arguments:
        return raw_arguments[raw_arguments.index("--") + 1 :]
    executable_name = Path(raw_arguments[0]).name.lower() if raw_arguments else ""
    if "blender" in executable_name:
        return []
    return raw_arguments[1:]


def get_rpf_paths() -> Dict[str, Path]:
    """Return all resolved paths from the [rpf_paths] section of vrc2gtav.cfg."""
    parser = load_project_config()
    root_directory = get_project_root()
    if not parser.has_section("rpf_paths"):
        raise KeyError(
            translate(
                "paths.section_not_found",
                section="rpf_paths",
                path=find_project_config_file(),
            )
        )
    resolved_map: Dict[str, Path] = {}
    for option_key, option_value in parser.items("rpf_paths"):
        if option_key.endswith("_relative"):
            resolved_map[option_key] = Path(option_value.strip())
        else:
            resolved_map[option_key] = to_host_path(
                option_value.strip(), project_root_dir=root_directory
            )
    return resolved_map


PROTAGONIST_ORDER: Tuple[str, ...] = ("michael", "franklin", "trevor")
AVATAR_ORDER: Tuple[str, ...] = ("shinano_casual", "shinano_er", "miltina_maid")

PROTAGONIST_PROFILES: Dict[str, Dict[str, Any]] = {
    "michael": {
        "protagonist": "michael",
        "ped_name": "player_zero",
        "prop_ped_name": "player_zero_p",
        "skeleton_filename": "player_zero.yft",
        "default_avatar": "shinano_er",
        "primary_drawable": "uppr_000_u",
        "export_drawables": ["uppr_000_r", "uppr_000_u", "uppr_001_u", "uppr_004_u"],
        "target_z_min": -0.907,
        "target_z_max": 0.645,
        "arm_pose_degrees": -55.0,
    },
    "franklin": {
        "protagonist": "franklin",
        "ped_name": "player_one",
        "prop_ped_name": "player_one_p",
        "skeleton_filename": "player_one.yft",
        "default_avatar": "shinano_casual",
        "primary_drawable": "uppr_008_u",
        "export_drawables": ["uppr_008_u", "uppr_000_u", "uppr_001_u"],
        "target_z_min": -0.907,
        "target_z_max": 0.640,
        "arm_pose_degrees": -55.0,
    },
    "trevor": {
        "protagonist": "trevor",
        "ped_name": "player_two",
        "prop_ped_name": "player_two_p",
        "skeleton_filename": "player_two.yft",
        "default_avatar": "miltina_maid",
        "primary_drawable": "uppr_000_u",
        "export_drawables": [
            "uppr_000_u",
            "uppr_000_r",
            "uppr_001_u",
            "uppr_002_u",
            "uppr_003_r",
            "uppr_010_u",
            "uppr_027_u",
        ],
        "target_z_min": -0.908,
        "target_z_max": 0.642,
        "arm_pose_degrees": -55.0,
    },
}

PROTAGONIST_ALIASES: Dict[str, str] = {
    "michael": "michael",
    "player_zero": "michael",
    "franklin": "franklin",
    "player_one": "franklin",
    "trevor": "trevor",
    "player_two": "trevor",
}

AVATAR_PRESETS: Dict[str, Dict[str, Any]] = {
    "shinano_casual": {
        "avatar_id": "shinano_casual",
        "legacy_section": "franklin",
        "default_character": "franklin",
        "character_folder": "1_Franklin_Shinano_Casual",
        "scripts_folder": "Shinano_Casual_Franklin",
        "unity_hints": ("shinano",),
        "default_anim_files": ("ShinanoDefAdultNewv5.anim",),
        "default_blendshapes_cfg": "configs/shinano_blendshapes.cfg",
        "default_physbones_cfg": "configs/shinano_casual_physbones.cfg",
        "default_face_mesh": "Body",
    },
    "shinano_er": {
        "avatar_id": "shinano_er",
        "legacy_section": "michael",
        "default_character": "michael",
        "character_folder": "2_Michael_Shinano_EternalReunion",
        "scripts_folder": "Shinano_EternalReunion_Michael",
        "unity_hints": ("shinano", "reunion"),
        "default_anim_files": ("ShinanoDefAdultNewv5.anim",),
        "default_blendshapes_cfg": "configs/shinano_er_blendshapes.cfg",
        "default_physbones_cfg": "configs/michael_neko_mimi_physbones.cfg",
        "default_face_mesh": "Body",
    },
    "miltina_maid": {
        "avatar_id": "miltina_maid",
        "legacy_section": "trevor",
        "default_character": "trevor",
        "character_folder": "3_Trevor_Miltina_Maid",
        "scripts_folder": "Miltina_Maid_Trevor",
        "unity_hints": ("milltina", "miltina"),
        "default_anim_files": ("Miltina_close eyes_Base_adult.anim",),
        "default_blendshapes_cfg": "configs/miltina_blendshapes.cfg",
        "default_physbones_cfg": "configs/miltina_maid_physbones.cfg",
        "default_face_mesh": "Body",
    },
}

AVATAR_ALIASES: Dict[str, str] = {
    "shinano_casual": "shinano_casual",
    "shinano": "shinano_casual",
    "casual": "shinano_casual",
    "shinano_uniform": "shinano_casual",
    "shinano_er": "shinano_er",
    "shinano_eternal_reunion": "shinano_er",
    "eternal_reunion": "shinano_er",
    "er": "shinano_er",
    "miltina_maid": "miltina_maid",
    "miltina": "miltina_maid",
    "milltina": "miltina_maid",
    "milltina_maid": "miltina_maid",
}

_PROTAGONIST_ONLY_KEYS = frozenset(
    {
        "avatar",
        "ped_name",
        "prop_ped_name",
        "skeleton_yft",
        "physbones_cfg",
        "target_z_min",
        "target_z_max",
        "arm_pose_degrees",
        "staging_streamed_ped_dir",
        "staging_mppatches_ped_dir",
        "staging_patchday4_ped_dir",
        "staging_streamed_props_dir",
    }
)

_BUILD_OUTPUT_KEYS = frozenset(
    {
        "exported_models_dir",
        "target_model_ydd",
        "target_yft",
        "extra_model_ydds",
    }
)

_NON_PATH_OPTION_KEYS = frozenset(
    {
        "avatar",
        "ped_name",
        "prop_ped_name",
        "ytd_name",
        "unity_avatar_name",
        "blendshapes_source",
        "physbones_source",
        "physbones_marshmallow",
        "eye_blink",
        "eye_blink_strength",
        "mouth_open_strength",
        "hair_scale",
        "hair_offset",
        "target_z_min",
        "target_z_max",
        "arm_pose_degrees",
        "primary_drawable",
        "avatar_id",
        "protagonist",
    }
)

_HAIR_KEYWORD_OPTION_KEYS = frozenset({"custom_hair", "fbx_hair"})
_HAIR_OVERRIDE_OPTION_KEYS = frozenset(
    {"custom_hair", "fbx_hair", "hair_mat", "hair_tex", "hair_scale", "hair_offset"}
)
_PHYSBONE_OVERRIDE_OPTION_KEYS = frozenset(
    {"physbones_source", "physbones_marshmallow", "eye_blink", "eye_blink_strength", "mouth_open_strength"}
)
_HAIR_MODE_KEYWORDS = frozenset({"auto", "default", "none"})

_LIST_PATH_OPTION_KEYS = frozenset({"extra_model_ydds"})


def list_available_protagonists() -> Tuple[str, ...]:
    """Return canonical GTA V protagonist keys in display order."""
    return PROTAGONIST_ORDER


def list_available_avatars() -> Tuple[str, ...]:
    """Return canonical VRChat avatar preset IDs in display order."""
    return AVATAR_ORDER


def normalize_protagonist_key(raw_name: str) -> str:
    """Normalize protagonist or ped identifier to 'michael', 'franklin', or 'trevor'."""
    cleaned_name = str(raw_name).strip().lower()
    if cleaned_name in PROTAGONIST_ALIASES:
        return PROTAGONIST_ALIASES[cleaned_name]
    raise KeyError(translate("paths.unknown_protagonist", name=raw_name))


def normalize_avatar_id(raw_name: str) -> str:
    """Normalize VRChat avatar preset name or alias to canonical preset ID."""
    cleaned_name = str(raw_name).strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned_name in AVATAR_ALIASES:
        return AVATAR_ALIASES[cleaned_name]
    raise KeyError(translate("paths.unknown_avatar", name=raw_name))


def get_protagonist_profile(character_or_ped: str) -> Dict[str, Any]:
    """Return static GTA V protagonist metadata (ped name, default drawables, Z range)."""
    protagonist_key = normalize_protagonist_key(character_or_ped)
    return dict(PROTAGONIST_PROFILES[protagonist_key])


def get_avatar_preset_info(avatar_name: str) -> Dict[str, Any]:
    """Return static metadata for a canonical VRChat avatar preset."""
    avatar_id = normalize_avatar_id(avatar_name)
    return dict(AVATAR_PRESETS[avatar_id])


def _resolve_option_value(
    option_key: str,
    option_value: str,
    root_directory: Path,
    as_windows_path: bool,
) -> Union[Path, str, List[Union[Path, str]]]:
    """Resolve a raw .cfg option string into a path, list of paths, or plain string."""
    cleaned_value = option_value.strip()
    if option_key in _NON_PATH_OPTION_KEYS or not cleaned_value:
        return cleaned_value
    if (
        option_key in _HAIR_KEYWORD_OPTION_KEYS
        and cleaned_value.lower() in _HAIR_MODE_KEYWORDS
    ):
        return cleaned_value.lower()
    if option_key in _LIST_PATH_OPTION_KEYS:
        item_list: List[Union[Path, str]] = []
        for raw_item in cleaned_value.split(","):
            stripped_item = raw_item.strip()
            if not stripped_item:
                continue
            item_path = to_host_path(stripped_item, project_root_dir=root_directory)
            item_list.append(
                to_windows_path(item_path) if as_windows_path else item_path
            )
        return item_list
    host_path = to_host_path(cleaned_value, project_root_dir=root_directory)
    return to_windows_path(host_path) if as_windows_path else host_path


def get_avatar_paths(
    avatar_name: str,
    as_windows_path: bool = False,
) -> Dict[str, Any]:
    """
    Resolve all asset, Unity, blendshape, texture, and script paths for a
    VRChat avatar preset (`shinano_casual`, `shinano_er`, or `miltina_maid`).

    Reads `[avatar:<id>]` when present and falls back cleanly to legacy
    character sections for older `vrc2gtav.cfg` files.
    """
    avatar_id = normalize_avatar_id(avatar_name)
    preset_info = AVATAR_PRESETS[avatar_id]
    parser = load_project_config()
    root_directory = get_project_root()

    avatar_section_underscore = f"avatar_{avatar_id}"
    avatar_section_colon = f"avatar:{avatar_id}"
    legacy_section = str(preset_info["legacy_section"])
    if parser.has_section(avatar_section_underscore):
        source_section = avatar_section_underscore
    elif parser.has_section(avatar_section_colon):
        source_section = avatar_section_colon
    elif parser.has_section(avatar_id):
        source_section = avatar_id
    elif parser.has_section(legacy_section):
        source_section = legacy_section
    else:
        raise KeyError(
            translate(
                "paths.section_not_found",
                section=avatar_section_underscore,
                path=find_project_config_file(),
            )
        )

    resolved_avatar: Dict[str, Any] = {
        "avatar": avatar_id,
        "avatar_id": avatar_id,
        "legacy_section": legacy_section,
    }
    for option_key, option_value in parser.items(source_section):
        if source_section == legacy_section and (
            option_key in _PROTAGONIST_ONLY_KEYS or option_key in _BUILD_OUTPUT_KEYS
        ):
            continue
        resolved_avatar[option_key] = _resolve_option_value(
            option_key,
            option_value,
            root_directory,
            as_windows_path,
        )

    if "character_dir" not in resolved_avatar:
        fallback_char_dir = root_directory / str(preset_info["character_folder"])
        resolved_avatar["character_dir"] = (
            to_windows_path(fallback_char_dir) if as_windows_path else fallback_char_dir
        )
    if "scripts_dir" not in resolved_avatar:
        fallback_scripts_dir = get_scripts_root_dir() / str(preset_info["scripts_folder"])
        resolved_avatar["scripts_dir"] = (
            to_windows_path(fallback_scripts_dir)
            if as_windows_path
            else fallback_scripts_dir
        )
    if "blendshapes_cfg" not in resolved_avatar:
        fallback_cfg_path = root_directory / str(preset_info["default_blendshapes_cfg"])
        resolved_avatar["blendshapes_cfg"] = (
            to_windows_path(fallback_cfg_path) if as_windows_path else fallback_cfg_path
        )
    if "physbones_cfg" not in resolved_avatar and preset_info.get("default_physbones_cfg"):
        fallback_pb_path = root_directory / str(preset_info["default_physbones_cfg"])
        resolved_avatar["physbones_cfg"] = (
            to_windows_path(fallback_pb_path) if as_windows_path else fallback_pb_path
        )
    return resolved_avatar


def _update_cfg_section_options(
    section_name: str,
    updates: Dict[str, str],
    config_file_path: Optional[Union[str, Path]] = None,
) -> Path:
    """Update or insert key=value pairs in a specific INI section preserving comments."""
    cfg_file = find_project_config_file(config_file_path)
    raw_text = cfg_file.read_text(encoding="utf-8")
    lines = raw_text.splitlines(keepends=True)
    header_target = f"[{section_name}]"
    section_start_idx: Optional[int] = None
    section_end_idx = len(lines)

    for line_idx, raw_line in enumerate(lines):
        stripped_line = raw_line.strip()
        if stripped_line.startswith("[") and stripped_line.endswith("]"):
            if stripped_line.lower() == header_target.lower():
                section_start_idx = line_idx
            elif section_start_idx is not None:
                section_end_idx = line_idx
                break

    if section_start_idx is None:
        raise KeyError(
            translate("paths.section_not_found", section=section_name, path=cfg_file)
        )

    newline_ending = "\n"
    if lines[section_start_idx].endswith("\r\n"):
        newline_ending = "\r\n"

    remaining_keys = dict(updates)
    for scan_idx in range(section_start_idx + 1, section_end_idx):
        candidate_line = lines[scan_idx].lstrip()
        if candidate_line.startswith("#") or candidate_line.startswith(";") or "=" not in candidate_line:
            continue
        key_part = candidate_line.split("=", 1)[0].strip()
        if key_part in remaining_keys:
            lines[scan_idx] = f"{key_part} = {remaining_keys.pop(key_part)}{newline_ending}"

    if remaining_keys:
        insert_pos = section_start_idx + 1
        while insert_pos < section_end_idx and lines[insert_pos].lstrip().startswith(("#", ";")):
            insert_pos += 1
        for key_name, val_str in remaining_keys.items():
            lines.insert(insert_pos, f"{key_name} = {val_str}{newline_ending}")
            insert_pos += 1

    cfg_file.write_text("".join(lines), encoding="utf-8")
    invalidate_config_cache()
    return cfg_file


def set_protagonist_avatar(
    character_or_ped: str,
    avatar_name: str,
    config_file_path: Optional[Union[str, Path]] = None,
) -> str:
    """Persist a protagonist's assigned VRChat avatar preset in vrc2gtav.cfg."""
    protagonist_key = normalize_protagonist_key(character_or_ped)
    avatar_id = normalize_avatar_id(avatar_name)
    _update_cfg_section_options(
        protagonist_key,
        {"avatar": avatar_id},
        config_file_path=config_file_path,
    )
    return avatar_id


def set_character_custom_hair(
    target_section_or_character: str,
    hair_value: str,
    hair_mat: Optional[str] = None,
    hair_tex: Optional[str] = None,
    hair_scale: Optional[str] = None,
    hair_offset: Optional[str] = None,
    config_file_path: Optional[Union[str, Path]] = None,
) -> str:
    """Persist custom hair overrides inside a protagonist or avatar section of vrc2gtav.cfg."""
    cleaned_target = str(target_section_or_character).strip()
    parser = load_project_config(config_file_path)
    if parser.has_section(cleaned_target):
        section_name = cleaned_target
    else:
        try:
            section_name = normalize_protagonist_key(cleaned_target)
        except KeyError:
            avatar_id = normalize_avatar_id(cleaned_target)
            section_name = f"avatar_{avatar_id}"
            if not parser.has_section(section_name):
                section_name = f"avatar:{avatar_id}"

    updates: Dict[str, str] = {"custom_hair": str(hair_value).strip()}
    if hair_mat is not None:
        updates["hair_mat"] = str(hair_mat).strip()
    if hair_tex is not None:
        updates["hair_tex"] = str(hair_tex).strip()
    if hair_scale is not None:
        updates["hair_scale"] = str(hair_scale).strip()
    if hair_offset is not None:
        updates["hair_offset"] = str(hair_offset).strip()

    _update_cfg_section_options(
        section_name,
        updates,
        config_file_path=config_file_path,
    )
    return section_name


def get_character_paths(
    character_section: str,
    as_windows_path: bool = False,
    avatar_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return a dictionary combining a GTA V protagonist slot ('michael',
    'franklin', or 'trevor' / 'player_zero', 'player_one', 'player_two') with
    its assigned or overridden VRChat avatar preset.
    """
    protagonist_key = normalize_protagonist_key(character_section)
    profile = PROTAGONIST_PROFILES[protagonist_key]
    parser = load_project_config()
    if not parser.has_section(protagonist_key):
        raise KeyError(
            translate(
                "paths.section_not_found",
                section=protagonist_key,
                path=find_project_config_file(),
            )
        )
    root_directory = get_project_root()
    rpf_paths_cfg = get_rpf_paths()

    configured_avatar = (
        parser.get(protagonist_key, "avatar", fallback="").strip()
        or str(profile["default_avatar"])
    )
    active_avatar = normalize_avatar_id(avatar_override or configured_avatar)
    is_default_pairing = active_avatar == str(profile["default_avatar"])

    avatar_paths_host = get_avatar_paths(active_avatar, as_windows_path=False)
    avatar_paths = (
        get_avatar_paths(active_avatar, as_windows_path=True)
        if as_windows_path
        else avatar_paths_host
    )

    resolved_character: Dict[str, Any] = dict(avatar_paths)
    has_dedicated_avatar_section = (
        parser.has_section(f"avatar_{active_avatar}")
        or parser.has_section(f"avatar:{active_avatar}")
        or parser.has_section(active_avatar)
    )

    for option_key, option_value in parser.items(protagonist_key):
        if option_key in _PROTAGONIST_ONLY_KEYS:
            resolved_character[option_key] = _resolve_option_value(
                option_key,
                option_value,
                root_directory,
                as_windows_path,
            )
        elif (
            option_key in _HAIR_OVERRIDE_OPTION_KEYS
            or option_key in _PHYSBONE_OVERRIDE_OPTION_KEYS
        ) and option_value.strip():
            resolved_character[option_key] = _resolve_option_value(
                option_key,
                option_value,
                root_directory,
                as_windows_path,
            )
        elif (
            is_default_pairing
            and avatar_override is None
            and not has_dedicated_avatar_section
        ):
            resolved_character[option_key] = _resolve_option_value(
                option_key,
                option_value,
                root_directory,
                as_windows_path,
            )

    ped_name = str(resolved_character.get("ped_name") or profile["ped_name"])
    prop_ped_name = str(
        resolved_character.get("prop_ped_name") or profile["prop_ped_name"]
    )
    resolved_character["ped_name"] = ped_name
    resolved_character["prop_ped_name"] = prop_ped_name
    resolved_character["protagonist"] = protagonist_key
    resolved_character["avatar"] = active_avatar
    resolved_character["avatar_id"] = active_avatar

    def _float_option(key_name: str, default_val: float) -> float:
        raw_val = resolved_character.get(key_name, "")
        try:
            return float(str(raw_val).strip()) if str(raw_val).strip() else default_val
        except ValueError:
            return default_val

    resolved_character["target_z_min"] = _float_option(
        "target_z_min", float(profile["target_z_min"])
    )
    resolved_character["target_z_max"] = _float_option(
        "target_z_max", float(profile["target_z_max"])
    )
    resolved_character["arm_pose_degrees"] = _float_option(
        "arm_pose_degrees", float(profile["arm_pose_degrees"])
    )
    resolved_character["primary_drawable"] = str(profile["primary_drawable"])
    resolved_character["export_drawables"] = list(profile["export_drawables"])

    if "skeleton_yft" not in resolved_character or not str(
        resolved_character["skeleton_yft"]
    ).strip():
        default_skel = rpf_paths_cfg["vanilla_skeletons_backup"] / f"{ped_name}.yft"
        resolved_character["skeleton_yft"] = (
            to_windows_path(default_skel) if as_windows_path else default_skel
        )

    default_staging_entries = {
        "staging_streamed_ped_dir": rpf_paths_cfg["streamedpeds_extracted"] / ped_name,
        "staging_mppatches_ped_dir": rpf_paths_cfg["mppatches_extracted"] / ped_name,
        "staging_patchday4_ped_dir": rpf_paths_cfg["patchday4ng_models_extracted"]
        / ped_name,
        "staging_streamed_props_dir": rpf_paths_cfg["streamedpedprops_extracted"]
        / prop_ped_name,
    }
    for stage_key, stage_default in default_staging_entries.items():
        if stage_key not in resolved_character:
            resolved_character[stage_key] = (
                to_windows_path(stage_default) if as_windows_path else stage_default
            )

    explicit_default_outputs = (
        is_default_pairing
        and avatar_override is None
        and "exported_models_dir" in resolved_character
        and "target_model_ydd" in resolved_character
        and "target_yft" in resolved_character
    )
    if not explicit_default_outputs:
        avatar_char_dir = Path(avatar_paths_host["character_dir"])
        exported_dir = (
            avatar_char_dir / "4_exported_models"
            if is_default_pairing
            else avatar_char_dir / "4_exported_models" / ped_name
        )
        primary_drawable = str(profile["primary_drawable"])
        drawables_list = list(profile["export_drawables"])
        target_ydd_path = exported_dir / f"{primary_drawable}.ydd"
        target_yft_path = exported_dir / f"{ped_name}.yft"
        extra_ydd_paths = [
            exported_dir / f"{drawable_name}.ydd"
            for drawable_name in drawables_list
            if drawable_name != primary_drawable
        ]
        if as_windows_path:
            resolved_character["exported_models_dir"] = to_windows_path(exported_dir)
            resolved_character["target_model_ydd"] = to_windows_path(target_ydd_path)
            resolved_character["target_yft"] = to_windows_path(target_yft_path)
            resolved_character["extra_model_ydds"] = [
                to_windows_path(item_path) for item_path in extra_ydd_paths
            ]
        else:
            resolved_character["exported_models_dir"] = exported_dir
            resolved_character["target_model_ydd"] = target_ydd_path
            resolved_character["target_yft"] = target_yft_path
            resolved_character["extra_model_ydds"] = extra_ydd_paths

    return resolved_character


def ensure_streamedpedprops_extracted() -> Path:
    """
    Ensure streamedpedprops.rpf is extracted into staging, extracting it from
    x64v_extracted via the RAGE CLI if missing or empty.
    """
    rpf_paths_cfg = get_rpf_paths()
    props_extracted_dir = rpf_paths_cfg["streamedpedprops_extracted"]
    if props_extracted_dir.is_dir() and any(props_extracted_dir.iterdir()):
        return props_extracted_dir

    nested_props_rpf = (
        rpf_paths_cfg["x64v_extracted"] / rpf_paths_cfg["streamedpedprops_rpf_relative"]
    )
    if not nested_props_rpf.is_file():
        raise FileNotFoundError(
            translate("paths.streamedpedprops_not_found", path=nested_props_rpf)
        )

    props_extracted_dir.mkdir(parents=True, exist_ok=True)
    gtav_root_dir = get_gtav_root_dir()
    rage_global_flags: List[str] = []
    if (gtav_root_dir / "GTA5.exe").is_file():
        rage_global_flags = ["--exe", str(gtav_root_dir)]
    rage_command = build_rage_command(
        *rage_global_flags,
        "extract",
        "-o",
        str(props_extracted_dir),
        str(nested_props_rpf),
    )
    print(
        translate(
            "paths.extracting_streamedpedprops",
            source_path=nested_props_rpf,
            target_dir=props_extracted_dir,
        )
    )
    subprocess.run(rage_command, check=True)
    return props_extracted_dir


def ensure_character_skeleton_yft(character_section: str) -> Path:
    """
    Ensure the base player_*.yft skeleton exists inside the character's 2_blender
    folder, restoring it from vanilla backup or extracting directly from GTA V RPFs.
    """
    character_cfg = get_character_paths(character_section)
    skeleton_yft_path = Path(character_cfg["skeleton_yft"])
    if skeleton_yft_path.is_file():
        return skeleton_yft_path

    ped_filename = f"{character_cfg['ped_name']}.yft"
    rpf_paths_cfg = get_rpf_paths()
    vanilla_backup_dir = rpf_paths_cfg.get(
        "vanilla_skeletons_backup",
        get_staging_dir() / "backup_vanilla_skeletons",
    )
    vanilla_backup_yft = vanilla_backup_dir / ped_filename

    skeleton_yft_path.parent.mkdir(parents=True, exist_ok=True)
    if vanilla_backup_yft.is_file():
        shutil.copy2(vanilla_backup_yft, skeleton_yft_path)
        print(
            translate(
                "paths.restored_skeleton_backup",
                filename=skeleton_yft_path.name,
            )
        )
        return skeleton_yft_path

    vanilla_x64v_rpf = rpf_paths_cfg["x64v_vanilla_rpf"]
    if vanilla_x64v_rpf.is_file():
        temp_extract_dir = get_staging_dir() / "_tmp_vanilla_skeleton_fetch"
        shutil.rmtree(temp_extract_dir, ignore_errors=True)
        try:
            gtav_root_dir = get_gtav_root_dir()
            rage_global_flags: List[str] = []
            if (gtav_root_dir / "GTA5.exe").is_file():
                rage_global_flags = ["--exe", str(gtav_root_dir)]
            streamed_rel_str = rpf_paths_cfg["streamedpeds_rpf_relative"].as_posix()
            print(
                translate(
                    "paths.extracting_vanilla_skeleton",
                    filename=ped_filename,
                    archive_name=vanilla_x64v_rpf.name,
                )
            )
            subprocess.run(
                build_rage_command(
                    *rage_global_flags,
                    "extract",
                    str(vanilla_x64v_rpf),
                    streamed_rel_str,
                    "-o",
                    str(temp_extract_dir),
                ),
                check=True,
            )
            temp_nested_rpf = temp_extract_dir / rpf_paths_cfg["streamedpeds_rpf_relative"]
            vanilla_backup_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                build_rage_command(
                    *rage_global_flags,
                    "extract",
                    str(temp_nested_rpf),
                    ped_filename,
                    "-o",
                    str(vanilla_backup_dir),
                ),
                check=True,
            )
            if vanilla_backup_yft.is_file():
                shutil.copy2(vanilla_backup_yft, skeleton_yft_path)
                return skeleton_yft_path
        finally:
            shutil.rmtree(temp_extract_dir, ignore_errors=True)

    nested_streamedpeds_rpf = (
        rpf_paths_cfg["x64v_extracted"] / rpf_paths_cfg["streamedpeds_rpf_relative"]
    )
    if nested_streamedpeds_rpf.is_file():
        vanilla_backup_dir.mkdir(parents=True, exist_ok=True)
        gtav_root_dir = get_gtav_root_dir()
        rage_global_flags = []
        if (gtav_root_dir / "GTA5.exe").is_file():
            rage_global_flags = ["--exe", str(gtav_root_dir)]
        rage_command = build_rage_command(
            *rage_global_flags,
            "extract",
            str(nested_streamedpeds_rpf),
            ped_filename,
            "-o",
            str(vanilla_backup_dir),
        )
        print(
            translate(
                "paths.extracting_base_skeleton",
                filename=ped_filename,
                archive_name=nested_streamedpeds_rpf.name,
            )
        )
        subprocess.run(rage_command, check=True)
        if vanilla_backup_yft.is_file():
            shutil.copy2(vanilla_backup_yft, skeleton_yft_path)
            return skeleton_yft_path

    raise FileNotFoundError(
        translate("paths.skeleton_missing_run_setup", path=skeleton_yft_path)
    )


def _resolve_props_backup_directory(
    props_dir_path: Path,
    backup_directory: Optional[Union[str, Path]],
) -> Optional[Path]:
    """Resolve optional vanilla backup directory for staged protagonist props."""
    if backup_directory is not None:
        return Path(backup_directory)
    try:
        rpf_paths_cfg = get_rpf_paths()
        extracted_root = rpf_paths_cfg["streamedpedprops_extracted"].resolve()
        backup_root = rpf_paths_cfg.get("streamedpedprops_backup_p_eyes")
        if backup_root is not None and props_dir_path.resolve().parent == extracted_root:
            return backup_root / props_dir_path.name
    except Exception:
        return None
    return None


def patch_character_glasses_props(
    target_props_directory: Union[str, Path],
    prop_dummy_path: Union[str, Path],
    character_label: str = "",
    backup_directory: Optional[Union[str, Path]] = None,
) -> Dict[str, int]:
    """
    Replace all wearable prop drawables (p_head_*, p_eyes_*, p_ears_* `.ydd`)
    inside a protagonist props folder with the rigid prop dummy (`p_eyes_dummy.ydd`),
    backing up non-dummy vanilla `.ydd` files once and leaving `.ytd` untouched.
    """
    props_dir_path = Path(target_props_directory)
    dummy_file_path = Path(prop_dummy_path)
    if not dummy_file_path.is_file():
        raise FileNotFoundError(
            translate("paths.prop_dummy_not_found", path=dummy_file_path)
        )

    if not props_dir_path.is_dir():
        print(translate("paths.props_dir_missing", path=props_dir_path))
        return {"replaced_glasses": 0, "replaced_props": 0, "untouched": 0}

    dummy_bytes = dummy_file_path.read_bytes()
    resolved_backup_dir = _resolve_props_backup_directory(
        props_dir_path, backup_directory
    )
    replaced_props = 0
    untouched_props = 0
    for entry_path in sorted(props_dir_path.iterdir()):
        if not entry_path.is_file():
            continue
        lowercase_name = entry_path.name.lower()
        if lowercase_name.startswith("p_") and lowercase_name.endswith(".ydd"):
            if resolved_backup_dir is not None and entry_path.read_bytes() != dummy_bytes:
                backup_target = resolved_backup_dir / entry_path.name
                if not backup_target.exists():
                    resolved_backup_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(entry_path, backup_target)
            shutil.copyfile(dummy_file_path, entry_path)
            replaced_props += 1
        else:
            untouched_props += 1

    label_text = character_label if character_label else props_dir_path.name
    dummy_size_bytes = dummy_file_path.stat().st_size
    print(f"  [{label_text}] {props_dir_path.parent.name}/{props_dir_path.name}:")
    print(
        translate(
            "paths.props_replaced_line",
            size_bytes=dummy_size_bytes,
            count=replaced_props,
        )
    )
    print(translate("paths.props_untouched_line", count=untouched_props))
    return {
        "replaced_glasses": replaced_props,
        "replaced_props": replaced_props,
        "untouched": untouched_props,
    }


def print_summary() -> None:
    """Print key resolved paths from vrc2gtav.cfg for diagnostics."""
    cfg_file = find_project_config_file()
    rpf_paths = get_rpf_paths()
    print(translate("paths.summary_header"))
    print(translate("paths.summary_cfg_file", path=cfg_file))
    print(
        translate(
            "paths.summary_language",
            language=get_language_display_name(get_active_language()),
        )
    )
    print(
        translate(
            "paths.summary_os",
            system_name=platform.system(),
            release_name=platform.release(),
        )
    )
    print(translate("paths.summary_project_root", path=get_project_root()))
    print(translate("paths.summary_unity_assets", path=get_vrc_assets_dir()))
    print(translate("paths.summary_staging", path=get_staging_dir()))
    print(translate("paths.summary_gtav_mods", path=get_gtav_mods_dir()))
    print(translate("paths.summary_rage_cli", path=get_rage_cli()))
    print(translate("paths.summary_blender_exe", path=get_blender_exe()))
    print(translate("paths.summary_python_exe", path=get_python_exe()))
    print(translate("paths.summary_ffmpeg_exe", path=get_ffmpeg_exe()))
    print(translate("paths.summary_dummy_ydd", path=get_dummy_ydd_path()))
    print(translate("paths.summary_prop_dummy_ydd", path=get_prop_dummy_ydd_path()))
    print(translate("paths.summary_x64v_mod_rpf", path=rpf_paths["x64v_game_rpf"]))
    print("=" * 44)


if __name__ == "__main__":
    print_summary()
