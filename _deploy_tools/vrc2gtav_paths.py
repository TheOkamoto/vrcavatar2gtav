#!/usr/bin/env python3
"""
vrc2gtav_paths.py
==================
Resolvedor centralizado de configuracoes e caminhos multiplataforma
(Windows nativo e Linux/WSL) a partir do arquivo vrc2gtav.cfg.

Todos os scripts do projeto importam este modulo para obter caminhos de
executaveis, diretorios, modelos, texturas, skeletons, arquivos .fbx e RPFs
sem depender de caminhos fixos espalhados pelo codigo.
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


CONFIG_ENV_VAR_NAME = "VRC2GTAV_CFG"
DEFAULT_CONFIG_FILENAME = "vrc2gtav.cfg"

_CONFIG_CACHE: Dict[str, object] = {
    "config_path": None,
    "parser": None,
    "mtime": None,
}


def is_windows_host() -> bool:
    """Retorna True se o interpretador Python atual estiver rodando em Windows."""
    return platform.system() == "Windows"


def is_wsl_host() -> bool:
    """Retorna True se o Python estiver rodando dentro do Windows Subsystem for Linux."""
    if is_windows_host():
        return False
    release_text = platform.release().lower()
    return ("microsoft" in release_text) or Path("/mnt/c/Windows").exists()


def to_host_path(raw_path_text: str, project_root_dir: Optional[Path] = None) -> Path:
    """
    Converte uma string de caminho do .cfg (Windows X:/..., WSL /mnt/x/...,
    POSIX /home/... ou relativo) para um pathlib.Path nativo do SO atual.
    """
    if not raw_path_text or not str(raw_path_text).strip():
        raise ValueError("Caminho vazio encontrado ao resolver configuracao.")

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

    # Ambiente Linux / WSL
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
    Converte qualquer caminho (/mnt/e/... ou E:/...) para formato Windows (E:/... ou E:\\...).
    Indispensavel para invocar executaveis Windows (como blender.exe) a partir do WSL.
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
    Localiza o arquivo vrc2gtav.cfg usando:
      1. Caminho explicito (parametro), se fornecido
      2. Variavel de ambiente VRC2GTAV_CFG, se definida
      3. Busca ascendente a partir deste arquivo e do diretorio de trabalho atual
    """
    if explicit_config_path is not None:
        explicit_file = Path(explicit_config_path).expanduser().resolve()
        if explicit_file.is_file():
            return explicit_file
        raise FileNotFoundError(
            f"Arquivo de configuracao especificado nao encontrado: {explicit_file}"
        )

    env_override = operating_system.environ.get(CONFIG_ENV_VAR_NAME, "").strip()
    if env_override:
        env_file = Path(env_override).expanduser().resolve()
        if env_file.is_file():
            return env_file
        raise FileNotFoundError(
            f"Arquivo apontado por {CONFIG_ENV_VAR_NAME} nao encontrado: {env_file}"
        )

    search_origins = [Path(__file__).resolve().parent, Path.cwd().resolve()]
    for origin_dir in search_origins:
        for candidate_dir in [origin_dir] + list(origin_dir.parents):
            candidate_cfg = candidate_dir / DEFAULT_CONFIG_FILENAME
            if candidate_cfg.is_file():
                return candidate_cfg.resolve()

    raise FileNotFoundError(
        f"Arquivo '{DEFAULT_CONFIG_FILENAME}' nao encontrado. "
        f"Certifique-se de que existe na raiz do projeto ou defina {CONFIG_ENV_VAR_NAME}."
    )


def load_project_config(
    config_file_path: Optional[Union[str, Path]] = None,
    force_reload: bool = False,
) -> configparser.ConfigParser:
    """
    Carrega e faz o parse de vrc2gtav.cfg com ExtendedInterpolation (${secao:chave}),
    resolvendo project_root dinamicamente quando configurado como '.' e mantendo cache
    invalidado por modificacao do arquivo.
    """
    resolved_cfg_file = find_project_config_file(config_file_path)
    try:
        current_mtime = resolved_cfg_file.stat().st_mtime
    except OSError as os_error:
        raise FileNotFoundError(
            f"Nao foi possivel ler metadados de {resolved_cfg_file}: {os_error}"
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
    # Preserva caixa original das chaves caso necessario
    parser.optionxform = str  # type: ignore[assignment]

    try:
        read_files = parser.read(str(resolved_cfg_file), encoding="utf-8")
    except configparser.Error as parse_error:
        raise RuntimeError(
            f"Erro de sintaxe ao ler configuracao '{resolved_cfg_file}': {parse_error}"
        ) from parse_error

    if not read_files:
        raise FileNotFoundError(
            f"Falha ao abrir arquivo de configuracao: {resolved_cfg_file}"
        )

    if not parser.has_section("directories"):
        raise ValueError(
            f"Secao obrigatoria [directories] ausente em {resolved_cfg_file}."
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


def get_config_value(section_name: str, option_name: str) -> str:
    """Retorna uma string interpolada do vrc2gtav.cfg com erro descritivo caso ausente."""
    parser = load_project_config()
    if not parser.has_section(section_name):
        raise KeyError(
            f"Secao [{section_name}] nao encontrada em {find_project_config_file()}."
        )
    if not parser.has_option(section_name, option_name):
        raise KeyError(
            f"Chave '{option_name}' nao encontrada na secao [{section_name}] "
            f"de {find_project_config_file()}."
        )
    return parser.get(section_name, option_name).strip()


def get_project_root() -> Path:
    """Retorna o diretorio raiz do projeto configurado em [directories] -> project_root."""
    raw_root_value = get_config_value("directories", "project_root")
    return to_host_path(raw_root_value)


def get_config_path(
    section_name: str,
    option_name: str,
    as_windows_path: bool = False,
) -> Union[Path, str]:
    """
    Resolve qualquer caminho do arquivo .cfg para Path nativo do SO atual
    ou string Windows (quando as_windows_path=True).
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
    """Resolve uma lista separada por virgulas do .cfg para uma lista de caminhos."""
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
    """Retorna o diretorio Assets do projeto Unity configurado no .cfg."""
    return Path(get_config_path("directories", "unity_assets"))


def get_staging_dir() -> Path:
    """Retorna o diretorio staging configurado no .cfg."""
    return Path(get_config_path("directories", "staging"))


def get_gtav_mods_dir() -> Path:
    """Retorna o diretorio mods do GTA V configurado no .cfg."""
    return Path(get_config_path("directories", "gtav_mods"))


def get_deploy_tools_dir() -> Path:
    """Retorna o diretorio _deploy_tools configurado no .cfg."""
    return Path(get_config_path("directories", "deploy_tools"))


def get_scripts_root_dir() -> Path:
    """Retorna o diretorio scripts configurado no .cfg."""
    return Path(get_config_path("directories", "scripts_root"))


def get_common_tools_dir() -> Path:
    """Retorna o diretorio scripts/common_tools configurado no .cfg."""
    return Path(get_config_path("directories", "common_tools"))


def get_artifacts_dir() -> Path:
    """Retorna o diretorio de artefatos configurado no .cfg."""
    return Path(get_config_path("directories", "artifacts"))


def get_renders_output_dir() -> Path:
    """Retorna o diretorio de saida de renders configurado no .cfg."""
    return Path(get_config_path("directories", "renders_output"))


def get_dummy_ydd_path() -> Path:
    """Retorna o caminho do arquivo dummy head_000_r.ydd configurado em [common_assets]."""
    return Path(get_config_path("common_assets", "dummy_ydd"))


def get_rage_cli() -> str:
    """Retorna o executavel ou caminho do RAGE CLI configurado em [executables] -> rage."""
    raw_rage_value = get_config_value("executables", "rage")
    if "/" not in raw_rage_value and "\\" not in raw_rage_value:
        located_binary = shutil.which(raw_rage_value)
        if located_binary:
            return located_binary
        return raw_rage_value

    host_rage_path = to_host_path(raw_rage_value, project_root_dir=get_project_root())
    if is_windows_host() and not host_rage_path.exists():
        # Fallback caso o usuario execute no Windows apontando para rage compilado no WSL
        return f"wsl {raw_rage_value}"
    return str(host_rage_path)


def get_blender_exe(as_windows_path: bool = False) -> str:
    """Retorna o caminho do executavel Blender configurado em [executables] -> blender."""
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
    """Retorna o executavel Python configurado em [executables] -> python, com fallback."""
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
    """Retorna o executavel ffmpeg configurado em [executables] -> ffmpeg."""
    raw_ffmpeg_value = get_config_value("executables", "ffmpeg")
    if "/" not in raw_ffmpeg_value and "\\" not in raw_ffmpeg_value:
        located_binary = shutil.which(raw_ffmpeg_value)
        return located_binary if located_binary else raw_ffmpeg_value
    return str(to_host_path(raw_ffmpeg_value, project_root_dir=get_project_root()))


def get_windows_cmd_exe() -> Path:
    """Retorna o caminho do cmd.exe configurado em [executables] -> windows_cmd."""
    return Path(get_config_path("executables", "windows_cmd"))


def find_working_wsl_interop() -> Optional[str]:
    """
    Em ambiente WSL, encontra um socket /run/WSL/*_interop funcional caso o socket
    atual esteja expirado apos reinicio de sessao.
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
    Monta o comando e variaveis de ambiente para executar um script no Blender
    tanto em Windows nativo quanto em Linux/WSL (via interoperabilidade Windows).
    """
    custom_env = operating_system.environ.copy()
    blender_host_exe = get_blender_exe(as_windows_path=False)
    extra_tokens = list(extra_arguments) if extra_arguments else []

    if is_windows_host():
        custom_env[CONFIG_ENV_VAR_NAME] = str(find_project_config_file())
        command_list = [
            blender_host_exe,
            "-b",
            "-P",
            str(blender_script_path),
        ]
        if extra_tokens:
            command_list.append("--")
            command_list.extend(extra_tokens)
        return command_list, custom_env

    # Em WSL, se o executavel do Blender for .exe Windows, invoca diretamente via
    # binfmt_misc para evitar quebra de aspas do cmd.exe e propaga VRC2GTAV_CFG via WSLENV.
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
            "-P",
            script_win_path,
        ]
        if extra_tokens:
            command_list.append("--")
            command_list.extend(extra_tokens)
        return command_list, custom_env

    # Blender Linux nativo
    custom_env[CONFIG_ENV_VAR_NAME] = str(find_project_config_file())
    command_list = [
        blender_host_exe,
        "-b",
        "-P",
        str(blender_script_path),
    ]
    if extra_tokens:
        command_list.append("--")
        command_list.extend(extra_tokens)
    return command_list, custom_env


def get_rpf_paths() -> Dict[str, Path]:
    """Retorna todos os caminhos resolvidos da secao [rpf_paths] de vrc2gtav.cfg."""
    parser = load_project_config()
    root_directory = get_project_root()
    if not parser.has_section("rpf_paths"):
        raise KeyError(
            f"Secao [rpf_paths] ausente em {find_project_config_file()}."
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
    Retorna um dicionario com todas as chaves resolvidas de um personagem
    ('franklin', 'michael' ou 'trevor') do arquivo vrc2gtav.cfg.
    """
    parser = load_project_config()
    if not parser.has_section(character_section):
        raise KeyError(
            f"Secao [{character_section}] nao encontrada em {find_project_config_file()}."
        )
    root_directory = get_project_root()
    non_path_keys = {"ped_name", "ytd_name"}
    list_path_keys = {"extra_model_ydds"}

    resolved_character: Dict[str, Union[Path, str, List[Union[Path, str]]]] = {}
    for option_key, option_value in parser.items(character_section):
        cleaned_value = option_value.strip()
        if option_key in non_path_keys:
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


def print_summary() -> None:
    """Imprime todos os caminhos principais carregados do vrc2gtav.cfg para diagnostico."""
    cfg_file = find_project_config_file()
    rpf_paths = get_rpf_paths()
    print("=== VRC2GTAV: Caminhos Carregados via .cfg ===")
    print(f"Arquivo .cfg: {cfg_file}")
    print(f"Sistema Operacional: {platform.system()} ({platform.release()})")
    print(f"Raiz do Projeto: {get_project_root()}")
    print(f"Assets Unity: {get_vrc_assets_dir()}")
    print(f"Staging: {get_staging_dir()}")
    print(f"GTA V Mods: {get_gtav_mods_dir()}")
    print(f"RAGE CLI: {get_rage_cli()}")
    print(f"Blender Exe: {get_blender_exe()}")
    print(f"Python Exe: {get_python_exe()}")
    print(f"FFmpeg Exe: {get_ffmpeg_exe()}")
    print(f"Dummy YDD: {get_dummy_ydd_path()}")
    print(f"x64v Mod RPF: {rpf_paths['x64v_game_rpf']}")
    print("============================================")


if __name__ == "__main__":
    print_summary()
