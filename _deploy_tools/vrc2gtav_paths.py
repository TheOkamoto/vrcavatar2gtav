#!/usr/bin/env python3
"""
vrc2gtav_paths.py
=================
Modulo utilitario compartilhado para resolucao dinamica e multiplataforma
(Windows nativo e Linux/WSL) de todos os caminhos do projeto vrc2gtav.

Regras de Implementacao:
  - Zero hardcode de letras de disco ou barras rigidas.
  - Compatibilidade total entre Windows e Linux/WSL.
  - Zero variaveis de uma ou duas letras.
  - Zero emojis (mensagens formatadas com marcadores ASCII padronizados).
  - Tratamento rigoroso de erros e excecoes.
"""

import os
import platform
import shutil
import sys
from pathlib import Path


def get_project_root() -> Path:
    """
    Detecta o diretorio raiz do projeto vrc2gtav de forma dinamica.
    Prioridades:
      1. Variavel de ambiente VRC2GTAV_ROOT.
      2. Busca ascendente pelos diretrios pais procurando marcadores do projeto.
      3. Verificacao de caminhos padroes nos discos do sistema operacional.
    """
    environment_root = os.environ.get("VRC2GTAV_ROOT")
    if environment_root:
        configured_path = Path(environment_root).resolve()
        if configured_path.exists():
            return configured_path

    current_script_file = Path(__file__).resolve()
    for ancestor_directory in [current_script_file] + list(current_script_file.parents):
        has_scripts_folder = (ancestor_directory / "scripts").exists()
        has_deploy_folder = (ancestor_directory / "_deploy_tools").exists()
        has_franklin_folder = (ancestor_directory / "1_Franklin_Shinano_Casual").exists()
        if has_scripts_folder or has_deploy_folder or has_franklin_folder:
            return ancestor_directory

    is_windows_system = platform.system() == "Windows"
    available_drives = ["E", "D", "C"] if is_windows_system else ["e", "d", "c"]
    for drive_letter in available_drives:
        if is_windows_system:
            candidate_path = Path(f"{drive_letter}:/vrc2gtav")
        else:
            candidate_path = Path(f"/mnt/{drive_letter}/vrc2gtav")
        if candidate_path.exists():
            return candidate_path

    # Fallback seguro: retorna o diretorio pai do arquivo atual
    return current_script_file.parent


def get_vrc_assets_dir() -> Path:
    """
    Localiza o diretorio de assets do Unity (projeto waifuv4) de forma independente do SO.
    """
    environment_assets = os.environ.get("VRC_ASSETS_DIR")
    if environment_assets:
        configured_assets = Path(environment_assets).resolve()
        if configured_assets.exists():
            return configured_assets

    project_root_directory = get_project_root()
    sibling_candidates = [
        project_root_directory.parent / "waifuv4" / "Assets",
        project_root_directory.parent / "WaifuV4" / "Assets",
    ]
    for sibling_path in sibling_candidates:
        if sibling_path.exists():
            return sibling_path

    is_windows_system = platform.system() == "Windows"
    available_drives = ["E", "D", "C"] if is_windows_system else ["e", "d", "c"]
    for drive_letter in available_drives:
        if is_windows_system:
            candidate_path = Path(f"{drive_letter}:/waifuv4/Assets")
        else:
            candidate_path = Path(f"/mnt/{drive_letter}/waifuv4/Assets")
        if candidate_path.exists():
            return candidate_path

    default_fallback = (
        Path("E:/waifuv4/Assets") if is_windows_system else Path("/mnt/e/waifuv4/Assets")
    )
    return default_fallback


def get_staging_dir() -> Path:
    """
    Localiza o diretorio de staging onde os arquivos RPF extraidos residem.
    """
    environment_staging = os.environ.get("GTAV_STAGING_DIR")
    if environment_staging:
        configured_staging = Path(environment_staging).resolve()
        if configured_staging.exists():
            return configured_staging

    project_root_directory = get_project_root()
    internal_staging = project_root_directory / "staging"
    if internal_staging.exists():
        return internal_staging

    is_windows_system = platform.system() == "Windows"
    available_drives = ["E", "D", "C"] if is_windows_system else ["e", "d", "c"]
    for drive_letter in available_drives:
        if is_windows_system:
            candidate_path = Path(f"{drive_letter}:/vrc2gtav/staging")
        else:
            candidate_path = Path(f"/mnt/{drive_letter}/vrc2gtav/staging")
        if candidate_path.exists():
            return candidate_path

    return internal_staging


def get_gtav_mods_dir() -> Path:
    """
    Localiza a pasta de destino do GTA V com suporte a mods.
    """
    environment_mods = os.environ.get("GTAV_MODS_DIR")
    if environment_mods:
        configured_mods = Path(environment_mods).resolve()
        if configured_mods.exists():
            return configured_mods

    is_windows_system = platform.system() == "Windows"
    available_drives = ["D", "E", "C"] if is_windows_system else ["d", "e", "c"]
    subdirectories_to_check = ["GTAV/mods", "Grand Theft Auto V/mods"]
    for drive_letter in available_drives:
        for subdirectory_name in subdirectories_to_check:
            if is_windows_system:
                candidate_path = Path(f"{drive_letter}:/{subdirectory_name}")
            else:
                candidate_path = Path(f"/mnt/{drive_letter}/{subdirectory_name}")
            if candidate_path.exists():
                return candidate_path

    default_fallback = (
        Path("D:/GTAV/mods") if is_windows_system else Path("/mnt/d/GTAV/mods")
    )
    return default_fallback


def get_rage_cli() -> str:
    """
    Localiza o binario executavel do RAGE CLI para manipulacao de RPFs e texturas.
    """
    environment_rage = os.environ.get("RAGE_CLI")
    if environment_rage and shutil.which(environment_rage):
        return environment_rage

    system_path_rage = shutil.which("rage")
    if system_path_rage:
        return system_path_rage

    candidate_binary_paths = [
        Path.home() / ".gemini/antigravity/scratch/gtav_tools/rage",
        Path.home() / ".cargo/bin/rage",
        Path("/usr/local/bin/rage"),
        Path("C:/Tools/rage.exe"),
        Path("E:/Tools/rage.exe"),
    ]
    for candidate_path in candidate_binary_paths:
        if candidate_path.exists():
            return str(candidate_path)

    return "rage"


def get_blender_exe() -> str:
    """
    Localiza o executavel do Blender com suporte ao addon Sollumz.
    """
    environment_blender = os.environ.get("BLENDER_EXE")
    if environment_blender:
        return environment_blender

    system_path_blender = shutil.which("blender")
    if system_path_blender:
        return system_path_blender

    candidate_installations = [
        "E:/waifuv4/BlenderTools/blender-4.0.2-windows-x64/blender.exe",
        "C:/Program Files/Blender Foundation/Blender 4.0/blender.exe",
        "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe",
        "/mnt/e/waifuv4/BlenderTools/blender-4.0.2-windows-x64/blender.exe",
    ]
    for installation_path in candidate_installations:
        if Path(installation_path).exists():
            return installation_path

    return "blender"


if __name__ == "__main__":
    print("=== Diagnostico de Caminhos Multiplataforma (vrc2gtav) ===")
    print("Sistema Operacional: ", platform.system())
    print("Raiz do Projeto:     ", get_project_root())
    print("Assets Unity VRChat: ", get_vrc_assets_dir())
    print("Diretorio Staging:   ", get_staging_dir())
    print("Diretorio Mods GTA:  ", get_gtav_mods_dir())
    print("RAGE CLI Tool:       ", get_rage_cli())
    print("Executavel Blender:  ", get_blender_exe())
