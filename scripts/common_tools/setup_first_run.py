#!/usr/bin/env python3
"""
setup_first_run.py
==================
Configurador de Primeira Execucao (First-Run Setup) e Extrator de Assets
Vanilla do GTA V para o projeto vrc2gtav.

Este repositorio nao distribui arquivos protegidos por direitos autorais da
Rockstar Games (.rpf, .yft, drawables/texturas originais) nem assets pagos de
terceiros (BOOTH / Unity / VRChat). No primeiro uso, este script:
  1. Garante que `vrc2gtav.cfg` exista a partir de `vrc2gtav.cfg.example`.
  2. Detecta ou solicita ao usuario os caminhos locais de:
       - Instalacao legal do GTA V Legacy (`gtav_root`, contendo `GTA5.exe`)
       - Pasta `Assets` do projeto Unity/VRChat com os avatares licenciados
       - Blender (com Sollumz instalado)
       - RAGE CLI (`rage`) e Python
  3. Extrai os arquivos base vanilla necessarios do seu GTA V para `staging/`
     e popula os esqueletos base (`player_zero.yft`, `player_one.yft`,
     `player_two.yft`) nas pastas `2_blender/` dos tres personagens.

Regras de Implementacao:
  - Zero variaveis de uma ou duas letras.
  - Zero emojis (mensagens formatadas com marcadores ASCII padronizados).
  - Multiplataforma (Windows nativo e Linux/WSL).
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT_HINT = CURRENT_SCRIPT_DIR.parent.parent
for tools_dir_candidate in (
    CURRENT_SCRIPT_DIR,
    PROJECT_ROOT_HINT / "scripts" / "common_tools",
    PROJECT_ROOT_HINT / "_deploy_tools",
):
    if tools_dir_candidate.is_dir() and str(tools_dir_candidate) not in sys.path:
        sys.path.insert(0, str(tools_dir_candidate))

import vrc2gtav_paths as project_paths


PLACEHOLDER_MARKERS = (
    "C:/Games/Grand Theft Auto V",
    "C:/VRChatProjects/waifuv4/Assets",
    "C:/Program Files/Blender Foundation/Blender 4.0/blender.exe",
)


def is_valid_gtav_root(candidate_dir: Path) -> bool:
    """Verifica se a pasta informada contem GTA5.exe e x64v.rpf."""
    return (
        candidate_dir.is_dir()
        and (candidate_dir / "GTA5.exe").is_file()
        and (candidate_dir / "x64v.rpf").is_file()
    )


def format_path_for_cfg(raw_path_text: str) -> str:
    """
    Formata um caminho para armazenamento portatil em vrc2gtav.cfg.
    Converte `/mnt/x/...` em `X:/...` para funcionar em Windows Blender e Linux/WSL.
    """
    cleaned_text = str(raw_path_text).strip().strip('"').strip("'")
    if not cleaned_text:
        return cleaned_text
    slash_normalized = cleaned_text.replace("\\", "/")
    wsl_drive_match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", slash_normalized)
    if wsl_drive_match:
        drive_upper = wsl_drive_match.group(1).upper()
        sub_path = wsl_drive_match.group(2)
        return f"{drive_upper}:/{sub_path}"
    return slash_normalized


def detect_gtav_root(current_value: str) -> Optional[Path]:
    """Tenta localizar automaticamente a instalacao do GTA V no Windows ou WSL."""
    candidate_paths: List[Path] = []
    if current_value and current_value not in PLACEHOLDER_MARKERS:
        try:
            candidate_paths.append(
                project_paths.to_host_path(current_value, project_root_dir=PROJECT_ROOT_HINT)
            )
        except ValueError:
            pass

    env_gtav_path = os.environ.get("GTAV_PATH", "").strip()
    if env_gtav_path:
        try:
            candidate_paths.append(
                project_paths.to_host_path(env_gtav_path, project_root_dir=PROJECT_ROOT_HINT)
            )
        except ValueError:
            pass

    common_suffixes = [
        "GTAV",
        "Games/GTAV",
        "Games/Grand Theft Auto V",
        "Program Files/Rockstar Games/Grand Theft Auto V",
        "Program Files (x86)/Steam/steamapps/common/Grand Theft Auto V",
        "SteamLibrary/steamapps/common/Grand Theft Auto V",
        "Program Files/Epic Games/GTAV",
        "Epic Games/GTAV",
    ]
    for drive_char in ("c", "d", "e", "f", "g"):
        for relative_suffix in common_suffixes:
            if project_paths.is_windows_host():
                candidate_paths.append(Path(f"{drive_char.upper()}:/{relative_suffix}"))
            else:
                candidate_paths.append(Path(f"/mnt/{drive_char}/{relative_suffix}"))

    for candidate_path in candidate_paths:
        if is_valid_gtav_root(candidate_path):
            return candidate_path
    return None


def is_valid_unity_assets_dir(candidate_dir: Path) -> bool:
    """Verifica se a pasta Assets contem subpastas esperadas de avatares VRChat."""
    if not candidate_dir.is_dir():
        return False
    expected_markers = (
        candidate_dir / "Shinano",
        candidate_dir / "DOLOSart",
        candidate_dir / "Vagrant Brand",
    )
    return any(marker_path.exists() for marker_path in expected_markers)


def detect_unity_assets(current_value: str) -> Optional[Path]:
    """Tenta localizar automaticamente a pasta Assets do Unity/VRChat."""
    candidate_paths: List[Path] = []
    if current_value and current_value not in PLACEHOLDER_MARKERS:
        try:
            candidate_paths.append(
                project_paths.to_host_path(current_value, project_root_dir=PROJECT_ROOT_HINT)
            )
        except ValueError:
            pass

    env_assets_dir = os.environ.get("VRC_ASSETS_DIR", "").strip()
    if env_assets_dir:
        try:
            candidate_paths.append(
                project_paths.to_host_path(env_assets_dir, project_root_dir=PROJECT_ROOT_HINT)
            )
        except ValueError:
            pass

    candidate_paths.extend(
        [
            PROJECT_ROOT_HINT / "Assets",
            PROJECT_ROOT_HINT.parent / "waifuv4" / "Assets",
        ]
    )
    for drive_char in ("c", "d", "e", "f"):
        if project_paths.is_windows_host():
            candidate_paths.append(Path(f"{drive_char.upper()}:/waifuv4/Assets"))
        else:
            candidate_paths.append(Path(f"/mnt/{drive_char}/waifuv4/Assets"))

    for candidate_path in candidate_paths:
        if is_valid_unity_assets_dir(candidate_path):
            return candidate_path
    return None


def detect_blender_executable(current_value: str) -> Optional[str]:
    """Tenta localizar o executavel do Blender no sistema."""
    if current_value and current_value not in PLACEHOLDER_MARKERS:
        try:
            resolved_current = project_paths.to_host_path(
                current_value, project_root_dir=PROJECT_ROOT_HINT
            )
            if resolved_current.is_file():
                return format_path_for_cfg(str(resolved_current))
        except ValueError:
            pass

    which_blender = shutil.which("blender")
    if which_blender:
        return format_path_for_cfg(which_blender)

    blender_candidates: List[Path] = []
    blender_versions = ("4.0.2", "4.0", "4.1", "4.2", "3.6")
    for drive_char in ("c", "d", "e", "f"):
        prefix_base = (
            Path(f"{drive_char.upper()}:/")
            if project_paths.is_windows_host()
            else Path(f"/mnt/{drive_char}")
        )
        for version_tag in blender_versions:
            blender_candidates.append(
                prefix_base / "waifuv4" / "BlenderTools" / f"blender-{version_tag}-windows-x64" / "blender.exe"
            )
            major_minor = ".".join(version_tag.split(".")[:2])
            blender_candidates.append(
                prefix_base / "Program Files" / "Blender Foundation" / f"Blender {major_minor}" / "blender.exe"
            )

    for candidate_exe in blender_candidates:
        if candidate_exe.is_file():
            return format_path_for_cfg(str(candidate_exe))
    return None


def detect_rage_executable(current_value: str) -> Optional[str]:
    """Tenta localizar o binario rage CLI (https://github.com/VIRUXE/rage)."""
    if current_value:
        which_configured = shutil.which(current_value)
        if which_configured:
            return format_path_for_cfg(which_configured)
        if "/" in current_value or "\\" in current_value:
            try:
                resolved_current = project_paths.to_host_path(
                    current_value, project_root_dir=PROJECT_ROOT_HINT
                )
                if resolved_current.is_file():
                    return format_path_for_cfg(str(resolved_current))
            except ValueError:
                pass

    which_rage = shutil.which("rage")
    if which_rage:
        return format_path_for_cfg(which_rage)

    rage_candidates = [
        PROJECT_ROOT_HINT / "tools" / "rage",
        PROJECT_ROOT_HINT / "tools" / "rage.exe",
        Path.home() / ".local" / "bin" / "rage",
        Path.home() / ".cargo" / "bin" / "rage",
        Path.home() / ".gemini" / "antigravity" / "scratch" / "gtav_tools" / "rage",
    ]
    for candidate_bin in rage_candidates:
        if candidate_bin.is_file():
            return format_path_for_cfg(str(candidate_bin))
    return None


def update_cfg_values_in_place(
    config_file_path: Path,
    section_updates: Dict[str, Dict[str, str]],
) -> None:
    """
    Atualiza chaves especificas em vrc2gtav.cfg preservando comentarios,
    ordenacao original e referencias ${secao:chave}.
    """
    original_lines = config_file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    updated_lines: List[str] = []
    active_section: Optional[str] = None
    remaining_updates: Dict[str, Dict[str, str]] = {
        sec_key: dict(sec_map) for sec_key, sec_map in section_updates.items()
    }

    for line_text in original_lines:
        stripped_line = line_text.strip()
        if stripped_line.startswith("[") and stripped_line.endswith("]"):
            if active_section and active_section in remaining_updates and remaining_updates[active_section]:
                for missing_key, missing_val in remaining_updates[active_section].items():
                    updated_lines.append(f"{missing_key} = {missing_val}\n")
                remaining_updates[active_section].clear()
            active_section = stripped_line[1:-1].strip()
            updated_lines.append(line_text)
            continue

        if (
            active_section
            and active_section in remaining_updates
            and "=" in stripped_line
            and not stripped_line.startswith("#")
            and not stripped_line.startswith(";")
        ):
            key_part = line_text.split("=", 1)[0].strip()
            if key_part in remaining_updates[active_section]:
                new_value = remaining_updates[active_section].pop(key_part)
                line_ending = "\r\n" if line_text.endswith("\r\n") else "\n"
                if new_value:
                    updated_lines.append(f"{key_part} = {new_value}{line_ending}")
                else:
                    updated_lines.append(f"{key_part} ={line_ending}")
                continue

        updated_lines.append(line_text)

    if active_section and active_section in remaining_updates and remaining_updates[active_section]:
        for missing_key, missing_val in remaining_updates[active_section].items():
            updated_lines.append(f"{missing_key} = {missing_val}\n")
        remaining_updates[active_section].clear()

    config_file_path.write_text("".join(updated_lines), encoding="utf-8")
    project_paths.invalidate_config_cache()


def prompt_path_setting(
    prompt_title: str,
    current_value: str,
    detected_value: Optional[str],
    validator_desc: str,
) -> str:
    """Solicita interativamente um caminho no terminal oferecendo valor padrao detectado."""
    suggested_value = detected_value if detected_value else current_value
    print(f"\n  {prompt_title} ({validator_desc})")
    if current_value:
        print(f"    Atual no .cfg: {current_value}")
    if detected_value and detected_value != current_value:
        print(f"    Detectado automaticamente: {detected_value}")
    entered_text = input(f"    Caminho [Enter = usar '{suggested_value}']: ").strip()
    chosen_raw = entered_text if entered_text else suggested_value
    return format_path_for_cfg(chosen_raw)


def configure_vrc2gtav_cfg(
    interactive: bool = True,
    gtav_root_override: Optional[str] = None,
    unity_assets_override: Optional[str] = None,
    blender_override: Optional[str] = None,
    rage_override: Optional[str] = None,
    python_override: Optional[str] = None,
) -> Path:
    """
    Garante que `vrc2gtav.cfg` exista e atualiza seus caminhos principais de forma
    interativa ou nao-interativa.
    """
    cfg_was_created = not project_paths.has_project_config_file()
    config_file_path = project_paths.ensure_project_config_from_example(PROJECT_ROOT_HINT)
    if cfg_was_created:
        print(f"[INFO] Criado arquivo de configuracao local a partir do template: {config_file_path}")

    project_paths.invalidate_config_cache()
    config_parser = project_paths.load_project_config(force_reload=True)

    current_gtav_root = config_parser.get("directories", "gtav_root", fallback="")
    current_unity_assets = config_parser.get("directories", "unity_assets", fallback="")
    current_blender = config_parser.get("executables", "blender", fallback="")
    current_rage = config_parser.get("executables", "rage", fallback="")
    current_python = config_parser.get("executables", "python", fallback="")

    detected_gtav = detect_gtav_root(current_gtav_root)
    detected_assets = detect_unity_assets(current_unity_assets)
    detected_blender = detect_blender_executable(current_blender)
    detected_rage = detect_rage_executable(current_rage)

    detected_gtav_str = format_path_for_cfg(str(detected_gtav)) if detected_gtav else None
    detected_assets_str = format_path_for_cfg(str(detected_assets)) if detected_assets else None

    if gtav_root_override:
        chosen_gtav_root = format_path_for_cfg(gtav_root_override)
    elif interactive:
        chosen_gtav_root = prompt_path_setting(
            "1) Pasta raiz do GTA V Legacy",
            current_gtav_root,
            detected_gtav_str,
            "deve conter GTA5.exe e x64v.rpf",
        )
    else:
        chosen_gtav_root = detected_gtav_str or current_gtav_root

    if unity_assets_override:
        chosen_unity_assets = format_path_for_cfg(unity_assets_override)
    elif interactive:
        chosen_unity_assets = prompt_path_setting(
            "2) Pasta Assets do Unity/VRChat",
            current_unity_assets,
            detected_assets_str,
            "contendo Shinano/, DOLOSart/, Vagrant Brand/, Li-ne/, etc.",
        )
    else:
        chosen_unity_assets = detected_assets_str or current_unity_assets

    if blender_override:
        chosen_blender = format_path_for_cfg(blender_override)
    elif interactive:
        chosen_blender = prompt_path_setting(
            "3) Executavel do Blender (com add-on Sollumz)",
            current_blender,
            detected_blender,
            "ex: C:/Program Files/Blender Foundation/Blender 4.0/blender.exe",
        )
    else:
        chosen_blender = detected_blender or current_blender

    if rage_override:
        chosen_rage = format_path_for_cfg(rage_override)
    elif interactive:
        chosen_rage = prompt_path_setting(
            "4) Executavel RAGE CLI (rage)",
            current_rage,
            detected_rage,
            "ex: rage no PATH ou caminho completo para o binario rage",
        )
    else:
        chosen_rage = detected_rage or current_rage

    if python_override:
        chosen_python = format_path_for_cfg(python_override)
    elif current_python in ("", "python3", "python") or not Path(
        project_paths.to_host_path(current_python, project_root_dir=PROJECT_ROOT_HINT)
    ).exists():
        chosen_python = format_path_for_cfg(sys.executable)
    else:
        chosen_python = current_python

    update_cfg_values_in_place(
        config_file_path,
        {
            "directories": {
                "gtav_root": chosen_gtav_root,
                "unity_assets": chosen_unity_assets,
            },
            "executables": {
                "blender": chosen_blender,
                "rage": chosen_rage,
                "python": chosen_python,
            },
        },
    )
    print(f"[OK] Configuracao salva em: {config_file_path}")
    return config_file_path


def run_rage_extract(
    archive_path: Path,
    output_dir: Path,
    gtav_root_dir: Path,
    patterns: Optional[List[str]] = None,
    description: str = "",
) -> None:
    """Executa `rage extract` com chaves Ng derivadas de gtav_root_dir."""
    if not archive_path.is_file():
        raise FileNotFoundError(f"Arquivo RPF de origem nao encontrado: {archive_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    command_args: List[str] = ["--exe", str(gtav_root_dir), "extract", str(archive_path)]
    if patterns:
        command_args.extend(patterns)
    command_args.extend(["-o", str(output_dir)])

    full_command = project_paths.build_rage_command(*command_args)
    label_text = description if description else f"Extraindo {archive_path.name}"
    print(f"[INFO] {label_text} -> {output_dir}...")
    subprocess.run(full_command, check=True)


def extract_vanilla_gtav_assets(force_reextract: bool = False) -> bool:
    """
    Extrai os arquivos RPF base vanilla do GTA V para `staging/` e semeia
    os esqueletos base `player_*.yft` nas pastas `2_blender/` dos 3 personagens.
    """
    project_paths.invalidate_config_cache()
    gtav_root_dir = project_paths.get_gtav_root_dir()
    gtav_mods_dir = project_paths.get_gtav_mods_dir()
    staging_dir = project_paths.get_staging_dir()
    rpf_paths_cfg = project_paths.get_rpf_paths()

    if not is_valid_gtav_root(gtav_root_dir):
        print(
            f"[ERRO] Instalacao valida do GTA V Legacy nao encontrada em: {gtav_root_dir}\n"
            f"       Certifique-se de que GTA5.exe e x64v.rpf existam na pasta configurada."
        )
        return False

    rage_cli_binary = project_paths.get_rage_cli()
    if not (Path(rage_cli_binary).is_file() or shutil.which(rage_cli_binary) or rage_cli_binary.startswith("wsl ")):
        print(
            f"[ERRO] RAGE CLI nao encontrado em '{rage_cli_binary}'.\n"
            f"       Instale o binario `rage` (https://github.com/VIRUXE/rage) e informe o caminho no vrc2gtav.cfg."
        )
        return False

    # Garante pastas locais ignoradas no Git
    for runtime_dir in (
        staging_dir,
        project_paths.get_renders_output_dir(),
        Path(project_paths.get_config_path("directories", "backups")),
        Path(project_paths.get_config_path("directories", "project_root")) / "renders",
        gtav_mods_dir,
    ):
        runtime_dir.mkdir(parents=True, exist_ok=True)

    for char_section in ("franklin", "michael", "trevor"):
        char_cfg = project_paths.get_character_paths(char_section)
        Path(char_cfg["textures_dir"]).mkdir(parents=True, exist_ok=True)
        Path(char_cfg["ytd_dir"]).mkdir(parents=True, exist_ok=True)
        Path(char_cfg["exported_models_dir"]).mkdir(parents=True, exist_ok=True)
        Path(char_cfg["skeleton_yft"]).parent.mkdir(parents=True, exist_ok=True)

    # 1. Extrai e valida chaves de decriptografia do GTA5.exe
    keys_output_dir = staging_dir / "rage_keys"
    if force_reextract or not keys_output_dir.is_dir() or not any(keys_output_dir.iterdir()):
        keys_output_dir.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Extraindo chaves criptograficas do GTA5.exe em {keys_output_dir}...")
        extract_keys_cmd = project_paths.build_rage_command(
            "--exe",
            str(gtav_root_dir),
            "extract-keys",
            "-o",
            str(keys_output_dir),
        )
        subprocess.run(extract_keys_cmd, check=True)
    else:
        print(f"[OK] Chaves RAGE ja disponiveis em: {keys_output_dir}")

    # 2. Extrai x64v.rpf vanilla -> staging/x64v_extracted
    x64v_extracted_dir = rpf_paths_cfg["x64v_extracted"]
    nested_streamedpeds_rpf = x64v_extracted_dir / rpf_paths_cfg["streamedpeds_rpf_relative"]
    nested_props_rpf = x64v_extracted_dir / rpf_paths_cfg["streamedpedprops_rpf_relative"]
    vanilla_x64v_rpf = rpf_paths_cfg["x64v_vanilla_rpf"]

    x64v_freshly_extracted = False
    if force_reextract or not nested_streamedpeds_rpf.is_file() or not nested_props_rpf.is_file():
        run_rage_extract(
            vanilla_x64v_rpf,
            x64v_extracted_dir,
            gtav_root_dir,
            description="Extraindo x64v.rpf vanilla",
        )
        x64v_freshly_extracted = True
    else:
        print(f"[OK] x64v_extracted ja preparado: {x64v_extracted_dir}")

    # 3. Extrai streamedpeds_players.rpf -> staging/streamedpeds_players_extracted
    streamedpeds_dir = rpf_paths_cfg["streamedpeds_extracted"]
    has_all_player_dirs = all(
        (streamedpeds_dir / ped_slot).is_dir()
        for ped_slot in ("player_zero", "player_one", "player_two")
    )
    if force_reextract or not has_all_player_dirs:
        run_rage_extract(
            nested_streamedpeds_rpf,
            streamedpeds_dir,
            gtav_root_dir,
            description="Extraindo streamedpeds_players.rpf",
        )
    else:
        print(f"[OK] streamedpeds_players_extracted ja preparado: {streamedpeds_dir}")

    # 4. Salva copias imutaveis dos esqueletos vanilla (.yft) e popula */2_blender/
    # Nota: se x64v_extracted ja existia de um deploy anterior, streamedpeds_players.rpf
    # dentro dele pode estar modificado; por isso extraimos diretamente do x64v.rpf original.
    vanilla_skeletons_backup = rpf_paths_cfg.get(
        "vanilla_skeletons_backup",
        staging_dir / "backup_vanilla_skeletons",
    )
    vanilla_skeletons_backup.mkdir(parents=True, exist_ok=True)
    missing_vanilla_yft_names = [
        f"{ped_slot}.yft"
        for ped_slot in ("player_zero", "player_one", "player_two")
        if force_reextract or not (vanilla_skeletons_backup / f"{ped_slot}.yft").is_file()
    ]
    if missing_vanilla_yft_names:
        if x64v_freshly_extracted:
            run_rage_extract(
                nested_streamedpeds_rpf,
                vanilla_skeletons_backup,
                gtav_root_dir,
                patterns=missing_vanilla_yft_names,
                description="Extraindo esqueletos vanilla (.yft)",
            )
        else:
            temp_vanilla_stage = staging_dir / "_tmp_vanilla_skeletons"
            shutil.rmtree(temp_vanilla_stage, ignore_errors=True)
            try:
                streamed_rel_str = rpf_paths_cfg["streamedpeds_rpf_relative"].as_posix()
                run_rage_extract(
                    vanilla_x64v_rpf,
                    temp_vanilla_stage,
                    gtav_root_dir,
                    patterns=[streamed_rel_str],
                    description="Extraindo streamedpeds_players.rpf vanilla para esqueletos",
                )
                temp_nested_peds = temp_vanilla_stage / rpf_paths_cfg["streamedpeds_rpf_relative"]
                run_rage_extract(
                    temp_nested_peds,
                    vanilla_skeletons_backup,
                    gtav_root_dir,
                    patterns=missing_vanilla_yft_names,
                    description="Extraindo esqueletos vanilla (.yft)",
                )
            finally:
                shutil.rmtree(temp_vanilla_stage, ignore_errors=True)
    else:
        print(f"[OK] Backups de esqueletos vanilla ja salvos em: {vanilla_skeletons_backup}")

    for char_section in ("franklin", "michael", "trevor"):
        skeleton_dest = project_paths.ensure_character_skeleton_yft(char_section)
        print(f"[OK] Esqueleto base pronto ({char_section}): {skeleton_dest}")

    # 5. Extrai streamedpedprops.rpf -> staging/streamedpedprops_extracted
    props_dir = rpf_paths_cfg["streamedpedprops_extracted"]
    if force_reextract and props_dir.is_dir():
        shutil.rmtree(props_dir, ignore_errors=True)
    project_paths.ensure_streamedpedprops_extracted()
    print(f"[OK] streamedpedprops_extracted pronto: {props_dir}")

    # 6. Extrai mppatchesng/dlc.rpf e mppatches.rpf
    vanilla_mppatches_dlc = (
        gtav_root_dir / "update" / "x64" / "dlcpacks" / "mppatchesng" / "dlc.rpf"
    )
    mppatches_dlc_dir = rpf_paths_cfg["mppatches_dlc_extracted"]
    inner_mppatches_rpf = mppatches_dlc_dir / rpf_paths_cfg["mppatches_rpf_relative"]
    mppatches_models_dir = rpf_paths_cfg["mppatches_extracted"]

    if not vanilla_mppatches_dlc.is_file():
        print(f"[ERRO] DLC obrigatorio mppatchesng nao encontrado em: {vanilla_mppatches_dlc}")
        return False

    if force_reextract or not inner_mppatches_rpf.is_file():
        run_rage_extract(
            vanilla_mppatches_dlc,
            mppatches_dlc_dir,
            gtav_root_dir,
            description="Extraindo update/x64/dlcpacks/mppatchesng/dlc.rpf",
        )
    else:
        print(f"[OK] mppatchesng_extracted ja preparado: {mppatches_dlc_dir}")

    has_mppatches_players = all(
        (mppatches_models_dir / ped_slot).is_dir()
        for ped_slot in ("player_zero", "player_one", "player_two")
    )
    if force_reextract or not has_mppatches_players:
        run_rage_extract(
            inner_mppatches_rpf,
            mppatches_models_dir,
            gtav_root_dir,
            description="Extraindo mppatches.rpf",
        )
    else:
        print(f"[OK] mppatches_extracted ja preparado: {mppatches_models_dir}")

    # 7. Extrai patchday4ng/dlc.rpf e patchday4ng.rpf (quando presente na instalacao do usuario)
    vanilla_patchday4_dlc = (
        gtav_root_dir / "update" / "x64" / "dlcpacks" / "patchday4ng" / "dlc.rpf"
    )
    if vanilla_patchday4_dlc.is_file():
        patchday4_dlc_dir = rpf_paths_cfg["patchday4ng_dlc_extracted"]
        inner_patchday4_rpf = patchday4_dlc_dir / rpf_paths_cfg["patchday4ng_rpf_relative"]
        patchday4_models_dir = rpf_paths_cfg["patchday4ng_models_extracted"]

        if force_reextract or not inner_patchday4_rpf.is_file():
            run_rage_extract(
                vanilla_patchday4_dlc,
                patchday4_dlc_dir,
                gtav_root_dir,
                description="Extraindo update/x64/dlcpacks/patchday4ng/dlc.rpf",
            )
        else:
            print(f"[OK] patchday4ng_dlc_extracted ja preparado: {patchday4_dlc_dir}")

        if force_reextract or not patchday4_models_dir.is_dir() or not any(patchday4_models_dir.iterdir()):
            run_rage_extract(
                inner_patchday4_rpf,
                patchday4_models_dir,
                gtav_root_dir,
                description="Extraindo patchday4ng.rpf",
            )
        else:
            print(f"[OK] patchday4ng_models_extracted ja preparado: {patchday4_models_dir}")
    else:
        print("[INFO] DLC opcional patchday4ng nao encontrado no gtav_root; etapa ignorada.")

    print("\n[SUCESSO] Setup inicial e extracao vanilla concluidos com sucesso!")
    return True


def diagnose_setup_state() -> Dict[str, bool]:
    """Diagnostica se vrc2gtav.cfg, caminhos principais, RPFs e esqueletos estao prontos."""
    has_cfg_file = project_paths.has_project_config_file()
    if not has_cfg_file:
        return {
            "has_cfg": False,
            "gtav_root_valid": False,
            "unity_assets_valid": False,
            "staging_ready": False,
            "skeletons_ready": False,
        }

    project_paths.invalidate_config_cache()
    gtav_root_dir = project_paths.get_gtav_root_dir()
    unity_assets_dir = project_paths.get_vrc_assets_dir()
    rpf_paths_cfg = project_paths.get_rpf_paths()

    gtav_ok = is_valid_gtav_root(gtav_root_dir)
    assets_ok = is_valid_unity_assets_dir(unity_assets_dir)

    x64v_ok = (rpf_paths_cfg["x64v_extracted"] / rpf_paths_cfg["streamedpeds_rpf_relative"]).is_file()
    streamedpeds_ok = all(
        (rpf_paths_cfg["streamedpeds_extracted"] / ped_slot).is_dir()
        for ped_slot in ("player_zero", "player_one", "player_two")
    )
    props_ok = (
        rpf_paths_cfg["streamedpedprops_extracted"].is_dir()
        and any(rpf_paths_cfg["streamedpedprops_extracted"].iterdir())
    )
    mppatches_ok = (rpf_paths_cfg["mppatches_extracted"] / "player_zero").is_dir()
    staging_ok = x64v_ok and streamedpeds_ok and props_ok and mppatches_ok

    skeletons_ok = all(
        Path(project_paths.get_character_paths(char_sec)["skeleton_yft"]).is_file()
        for char_sec in ("franklin", "michael", "trevor")
    )

    return {
        "has_cfg": True,
        "gtav_root_valid": gtav_ok,
        "unity_assets_valid": assets_ok,
        "staging_ready": staging_ok,
        "skeletons_ready": skeletons_ok,
    }


def is_first_run_needed() -> bool:
    """Retorna True se ainda faltar configuracao ou extracao vanilla inicial."""
    status_map = diagnose_setup_state()
    return not (
        status_map["has_cfg"]
        and status_map["gtav_root_valid"]
        and status_map["staging_ready"]
        and status_map["skeletons_ready"]
    )


def print_setup_diagnostics() -> bool:
    """Imprime relatorio legivel do estado do setup inicial."""
    status_map = diagnose_setup_state()
    print("\n" + "=" * 70)
    print("  DIAGNOSTICO DE PRIMEIRA EXECUCAO (VRC2GTAV)")
    print("=" * 70)
    for check_name, check_passed in status_map.items():
        tag_str = "[OK]" if check_passed else "[PENDENTE]"
        print(f"  {tag_str:10} {check_name}")
    print("=" * 70)
    return all(status_map.values())


def run_first_run_setup(
    interactive: bool = True,
    force_reextract: bool = False,
    gtav_root_override: Optional[str] = None,
    unity_assets_override: Optional[str] = None,
    blender_override: Optional[str] = None,
    rage_override: Optional[str] = None,
    python_override: Optional[str] = None,
) -> bool:
    """Executa o fluxo completo de configuracao inicial e extracao vanilla do GTA V."""
    print("\n" + "=" * 70)
    print("  SETUP INICIAL (FIRST-RUN) E EXTRACAO DE ASSETS VANILLA DO GTA V")
    print("=" * 70)
    print(
        "  Nenhum arquivo protegido do GTA V ou asset pago de VRChat e distribuido\n"
        "  neste repositorio. Vamos configurar seus caminhos locais e extrair os\n"
        "  arquivos vanilla necessarios diretamente da sua instalacao do GTA V."
    )

    configure_vrc2gtav_cfg(
        interactive=interactive,
        gtav_root_override=gtav_root_override,
        unity_assets_override=unity_assets_override,
        blender_override=blender_override,
        rage_override=rage_override,
        python_override=python_override,
    )

    unity_assets_dir = project_paths.get_vrc_assets_dir()
    if not unity_assets_dir.is_dir():
        print(
            f"[AVISO] Pasta Assets Unity ainda nao existe ou nao acessivel: {unity_assets_dir}\n"
            f"        A extracao do GTA V continuara, mas certifique-se de apontar para seus assets\n"
            f"        antes de compilar as texturas e modelos 3D."
        )

    extraction_ok = extract_vanilla_gtav_assets(force_reextract=force_reextract)
    print_setup_diagnostics()
    return extraction_ok


def main() -> int:
    """Ponto de entrada CLI do assistente de primeira execucao."""
    arg_parser = argparse.ArgumentParser(
        description="Assistente First-Run e extrator de arquivos vanilla do GTA V para vrc2gtav"
    )
    arg_parser.add_argument(
        "--check-only",
        action="store_true",
        help="Apenas exibe o diagnostico sem modificar arquivos",
    )
    arg_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Nao faz perguntas no terminal (usa autodetect / vrc2gtav.cfg / flags CLI)",
    )
    arg_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extrai RPFs vanilla mesmo se as pastas ja existirem em staging/",
    )
    arg_parser.add_argument("--gtav-root", default=None, help="Pasta raiz do GTA V Legacy")
    arg_parser.add_argument("--unity-assets", default=None, help="Pasta Assets do projeto Unity")
    arg_parser.add_argument("--blender", default=None, help="Executavel do Blender")
    arg_parser.add_argument("--rage", default=None, help="Executavel RAGE CLI (rage)")
    arg_parser.add_argument("--python", default=None, help="Executavel Python 3")

    parsed_args = arg_parser.parse_args()
    if parsed_args.check_only:
        is_ready = print_setup_diagnostics()
        return 0 if is_ready else 1

    setup_ok = run_first_run_setup(
        interactive=not parsed_args.non_interactive,
        force_reextract=parsed_args.force,
        gtav_root_override=parsed_args.gtav_root,
        unity_assets_override=parsed_args.unity_assets,
        blender_override=parsed_args.blender,
        rage_override=parsed_args.rage,
        python_override=parsed_args.python,
    )
    return 0 if setup_ok else 1


if __name__ == "__main__":
    sys.exit(main())
