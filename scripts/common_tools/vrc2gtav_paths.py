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
from typing import Dict, List, Optional, Tuple, Union


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
    raw_rage_value = get_config_value("executables", "rage")
    if "/" not in raw_rage_value and "\\" not in raw_rage_value:
        located_binary = shutil.which(raw_rage_value)
        if located_binary:
            return located_binary
        return raw_rage_value

    host_rage_path = to_host_path(raw_rage_value, project_root_dir=get_project_root())
    if is_windows_host() and not host_rage_path.exists():
        # Fallback when invoked from Windows targeting a WSL-built rage binary.
        return f"wsl {raw_rage_value}"
    return str(host_rage_path)


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
        if extra_tokens:
            command_list.append("--")
            command_list.extend(extra_tokens)
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


def get_character_paths(
    character_section: str,
    as_windows_path: bool = False,
) -> Dict[str, Union[Path, str, List[Union[Path, str]]]]:
    """
    Return a dictionary with all resolved keys for a protagonist section
    ('franklin', 'michael', or 'trevor') from vrc2gtav.cfg.
    """
    parser = load_project_config()
    if not parser.has_section(character_section):
        raise KeyError(
            translate(
                "paths.section_not_found",
                section=character_section,
                path=find_project_config_file(),
            )
        )
    root_directory = get_project_root()
    non_path_keys = {"ped_name", "prop_ped_name", "ytd_name", "unity_avatar_name"}
    list_path_keys = {"extra_model_ydds"}

    resolved_character: Dict[str, Union[Path, str, List[Union[Path, str]]]] = {}
    for option_key, option_value in parser.items(character_section):
        cleaned_value = option_value.strip()
        if option_key in non_path_keys or not cleaned_value:
            resolved_character[option_key] = cleaned_value
        elif option_key in list_path_keys:
            item_list: List[Union[Path, str]] = []
            for raw_item in cleaned_value.split(","):
                stripped_item = raw_item.strip()
                if not stripped_item:
                    continue
                item_path = to_host_path(stripped_item, project_root_dir=root_directory)
                item_list.append(
                    to_windows_path(item_path) if as_windows_path else item_path
                )
            resolved_character[option_key] = item_list
        else:
            host_path = to_host_path(cleaned_value, project_root_dir=root_directory)
            resolved_character[option_key] = (
                to_windows_path(host_path) if as_windows_path else host_path
            )
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


def patch_character_glasses_props(
    target_props_directory: Union[str, Path],
    prop_dummy_path: Union[str, Path],
    character_label: str = "",
) -> Dict[str, int]:
    """
    Replace all eyewear drawables (p_eyes_*.ydd) inside a protagonist props
    folder with the empty rigid prop dummy (p_eyes_dummy.ydd), leaving .ytd and
    all other accessories untouched.
    """
    props_dir_path = Path(target_props_directory)
    dummy_file_path = Path(prop_dummy_path)
    if not dummy_file_path.is_file():
        raise FileNotFoundError(
            translate("paths.prop_dummy_not_found", path=dummy_file_path)
        )

    if not props_dir_path.is_dir():
        print(translate("paths.props_dir_missing", path=props_dir_path))
        return {"replaced_glasses": 0, "untouched": 0}

    replaced_glasses = 0
    untouched_props = 0
    for entry_path in sorted(props_dir_path.iterdir()):
        if not entry_path.is_file():
            continue
        lowercase_name = entry_path.name.lower()
        if lowercase_name.startswith("p_eyes_") and lowercase_name.endswith(".ydd"):
            shutil.copyfile(dummy_file_path, entry_path)
            replaced_glasses += 1
        else:
            untouched_props += 1

    label_text = character_label if character_label else props_dir_path.name
    dummy_size_bytes = dummy_file_path.stat().st_size
    print(f"  [{label_text}] {props_dir_path.parent.name}/{props_dir_path.name}:")
    print(
        translate(
            "paths.props_replaced_line",
            size_bytes=dummy_size_bytes,
            count=replaced_glasses,
        )
    )
    print(translate("paths.props_untouched_line", count=untouched_props))
    return {"replaced_glasses": replaced_glasses, "untouched": untouched_props}


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
