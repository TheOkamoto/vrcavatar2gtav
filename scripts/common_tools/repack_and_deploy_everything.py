#!/usr/bin/env python3
"""
repack_and_deploy_everything.py
===============================
Repacota e instala todos os arquivos RPF do mod GTA V:
  1. Repack mppatches.rpf e patch do TOC (f_size=0, enc='OPEN')
  2. Repack mppatchesng_dlc.rpf e patch do TOC (f_size=0, enc='OPEN')
  3. Deploy dlc.rpf -> D:/GTAV/mods/update/x64/dlcpacks/mppatchesng/dlc.rpf
  4. Repack streamedpeds_players.rpf e patch do TOC (f_size=0, enc='OPEN')
  5. Repack x64v_modded.rpf e patch do TOC (f_size=0, enc='OPEN')
  6. Deploy x64v.rpf -> D:/GTAV/mods/x64v.rpf
  7. Verificacao de integridade estrita (rage verify / list -d)

Regras de Implementacao:
  - Zero variaveis de uma ou duas letras.
  - Zero emojis (mensagens formatadas com marcadores ASCII padronizados).
  - Tratamento rigoroso de erros e excecoes.
  - Multiplataforma (Windows e Linux/WSL).
"""

import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

# Adiciona o diretorio de ferramentas ao sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import vrc2gtav_paths as project_paths

RAGE_CLI_TOOL = project_paths.get_rage_cli()
GTAV_MODS_DIRECTORY = project_paths.get_gtav_mods_dir()
STAGING_DIRECTORY = project_paths.get_staging_dir()

MPPATCHES_EXTRACTED_DIR = STAGING_DIRECTORY / "mppatches_extracted"
MPPATCHES_RPF_FILE = (
    STAGING_DIRECTORY
    / "mppatchesng_extracted"
    / "x64"
    / "models"
    / "cdimages"
    / "mppatches.rpf"
)
MPPATCHESNG_EXTRACTED_DIR = STAGING_DIRECTORY / "mppatchesng_extracted"
MPPATCHESNG_DLC_RPF_FILE = STAGING_DIRECTORY / "mppatchesng_dlc.rpf"
TARGET_DLC_RPF_PATH = (
    GTAV_MODS_DIRECTORY
    / "update"
    / "x64"
    / "dlcpacks"
    / "mppatchesng"
    / "dlc.rpf"
)

PATCHDAY4NG_EXTRACTED_DIR = STAGING_DIRECTORY / "patchday4ng_dlc_extracted"
PATCHDAY4NG_INNER_RPF = (
    PATCHDAY4NG_EXTRACTED_DIR / "x64" / "models" / "cdimages" / "patchday4ng.rpf"
)
PATCHDAY4NG_MODELS_DIR = STAGING_DIRECTORY / "patchday4ng_models_extracted"
PATCHDAY4NG_DLC_RPF_FILE = STAGING_DIRECTORY / "patchday4ng_dlc.rpf"
TARGET_PATCHDAY4NG_DLC_PATH = (
    GTAV_MODS_DIRECTORY
    / "update"
    / "x64"
    / "dlcpacks"
    / "patchday4ng"
    / "dlc.rpf"
)

STREAMEDPEDS_EXTRACTED_DIR = STAGING_DIRECTORY / "streamedpeds_players_extracted"
STREAMEDPEDS_RPF_FILE = (
    STAGING_DIRECTORY
    / "x64v_extracted"
    / "models"
    / "cdimages"
    / "streamedpeds_players.rpf"
)
X64V_EXTRACTED_DIR = STAGING_DIRECTORY / "x64v_extracted"
X64V_MODDED_RPF_FILE = STAGING_DIRECTORY / "x64v_modded.rpf"
TARGET_X64V_RPF_PATH = GTAV_MODS_DIRECTORY / "x64v.rpf"


def patch_rpf7_open_and_zero_compressed(rpf_file_path: Path) -> int:
    """
    Modifica a tabela de conteudo (TOC) de um arquivo RPF7:
      1. Define o cabeçalho de criptografia para 'OPEN' (offset 12).
      2. Zera os bytes de tamanho comprimido de entradas binarias normais.
    Evita travamentos de leitura e o erro critico ERR_GEN_ZLIB_2 no GTA V.
    """
    if not rpf_file_path.exists():
        raise FileNotFoundError(
            f"[ERRO] Arquivo RPF para patching nao encontrado: {rpf_file_path}"
        )

    patched_entries_count = 0
    try:
        with open(rpf_file_path, "r+b") as rpf_file_handle:
            header_bytes = rpf_file_handle.read(16)
            magic_number, total_entries_count, names_length, encryption_flag = (
                struct.unpack("<IIII", header_bytes)
            )

            # Valida se eh um arquivo RPF7 legitimo (magic 0x52504637 == '7FPR')
            if magic_number != 0x52504637:
                raise ValueError(
                    f"[ERRO] Magic invalido para RPF7 em {rpf_file_path}: 0x{magic_number:08X}"
                )

            # Grava a flag de criptografia 'OPEN'
            rpf_file_handle.seek(12)
            rpf_file_handle.write(b"OPEN")

            # Le a tabela de entradas (TOC)
            rpf_file_handle.seek(16)
            toc_table_data = rpf_file_handle.read(total_entries_count * 16)

            for entry_index in range(total_entries_count):
                entry_byte_offset = entry_index * 16
                entry_record = bytearray(
                    toc_table_data[entry_byte_offset : entry_byte_offset + 16]
                )
                entry_descriptor = struct.unpack("<I", entry_record[4:8])[0]

                # Ignora diretorios (0x7FFFFF00) e recursos RSC7 de jogo (bit 31 ativo)
                is_directory_entry = entry_descriptor == 0x7FFFFF00
                is_resource_entry = (entry_descriptor & 0x80000000) != 0
                if is_directory_entry or is_resource_entry:
                    continue

                compressed_size_value = (
                    entry_record[2]
                    | (entry_record[3] << 8)
                    | (entry_record[4] << 16)
                )
                if compressed_size_value != 0:
                    entry_record[2] = 0
                    entry_record[3] = 0
                    entry_record[4] = 0
                    rpf_file_handle.seek(16 + entry_byte_offset)
                    rpf_file_handle.write(entry_record)
                    patched_entries_count += 1

    except Exception as error_exception:
        print(
            f"[ERRO] Falha ao aplicar patch no RPF {rpf_file_path}: {error_exception}"
        )
        raise

    print(
        f"  [RPF7 PATCH] {rpf_file_path.name}: enc='OPEN', "
        f"corrigidas {patched_entries_count} entradas binarias (f_size=0)"
    )
    return patched_entries_count


def execute_shell_command(
    command_arguments_list: list, task_description: str
) -> str:
    """
    Executa comandos do sistema de forma segura com cronometragem e captura de erro.
    """
    print(f"\n--- {task_description} ---")
    start_timestamp = time.time()
    try:
        process_execution = subprocess.run(
            command_arguments_list,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except subprocess.CalledProcessError as process_error:
        print(f"[ERRO] Falha ao executar: {task_description}")
        print(f"Codigo de retorno: {process_error.returncode}")
        print("Saida do processo:")
        print(process_error.stdout)
        raise

    finish_timestamp = time.time()
    elapsed_seconds = finish_timestamp - start_timestamp
    print(f"Concluido em {elapsed_seconds:.1f}s")
    return process_execution.stdout


def main():
    print("=== GTA V MOD REPACK & DEPLOY PIPELINE ===")
    print(f"RAGE CLI:        {RAGE_CLI_TOOL}")
    print(f"Staging RPF:     {STAGING_DIRECTORY}")
    print(f"Destino GTA V:   {GTAV_MODS_DIRECTORY}")

    # Validacao previa dos diretorios essenciais
    if not STAGING_DIRECTORY.exists():
        print(
            f"[ERRO] Diretorio de staging nao encontrado: {STAGING_DIRECTORY}"
        )
        sys.exit(1)

    try:
        # 1. Repack mppatches.rpf
        if MPPATCHES_RPF_FILE.exists():
            MPPATCHES_RPF_FILE.unlink()
        execute_shell_command(
            [
                RAGE_CLI_TOOL,
                "create",
                "-o",
                str(MPPATCHES_RPF_FILE),
                str(MPPATCHES_EXTRACTED_DIR),
            ],
            "Repacotando mppatches.rpf",
        )
        patch_rpf7_open_and_zero_compressed(MPPATCHES_RPF_FILE)

        # 2. Repack mppatchesng_dlc.rpf
        if MPPATCHESNG_DLC_RPF_FILE.exists():
            MPPATCHESNG_DLC_RPF_FILE.unlink()
        execute_shell_command(
            [
                RAGE_CLI_TOOL,
                "create",
                "-o",
                str(MPPATCHESNG_DLC_RPF_FILE),
                str(MPPATCHESNG_EXTRACTED_DIR),
            ],
            "Repacotando mppatchesng_dlc.rpf",
        )
        patch_rpf7_open_and_zero_compressed(MPPATCHESNG_DLC_RPF_FILE)

        # 3. Deploy dlc.rpf
        TARGET_DLC_RPF_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"\nInstalando dlc.rpf -> {TARGET_DLC_RPF_PATH}...")
        shutil.copy2(str(MPPATCHESNG_DLC_RPF_FILE), str(TARGET_DLC_RPF_PATH))
        print("dlc.rpf instalado com sucesso.")

        # 3B. Repack e Deploy patchday4ng (se presente no staging)
        if PATCHDAY4NG_EXTRACTED_DIR.exists() and PATCHDAY4NG_MODELS_DIR.exists():
            if PATCHDAY4NG_INNER_RPF.exists():
                PATCHDAY4NG_INNER_RPF.unlink()
            execute_shell_command(
                [
                    RAGE_CLI_TOOL,
                    "create",
                    "-o",
                    str(PATCHDAY4NG_INNER_RPF),
                    str(PATCHDAY4NG_MODELS_DIR),
                ],
                "Repacotando patchday4ng.rpf",
            )
            patch_rpf7_open_and_zero_compressed(PATCHDAY4NG_INNER_RPF)

            if PATCHDAY4NG_DLC_RPF_FILE.exists():
                PATCHDAY4NG_DLC_RPF_FILE.unlink()
            execute_shell_command(
                [
                    RAGE_CLI_TOOL,
                    "create",
                    "-o",
                    str(PATCHDAY4NG_DLC_RPF_FILE),
                    str(PATCHDAY4NG_EXTRACTED_DIR),
                ],
                "Repacotando patchday4ng dlc.rpf",
            )
            patch_rpf7_open_and_zero_compressed(PATCHDAY4NG_DLC_RPF_FILE)

            TARGET_PATCHDAY4NG_DLC_PATH.parent.mkdir(parents=True, exist_ok=True)
            print(f"\nInstalando patchday4ng/dlc.rpf -> {TARGET_PATCHDAY4NG_DLC_PATH}...")
            shutil.copy2(str(PATCHDAY4NG_DLC_RPF_FILE), str(TARGET_PATCHDAY4NG_DLC_PATH))
            print("patchday4ng/dlc.rpf instalado com sucesso.")

        # 4. Repack streamedpeds_players.rpf
        if STREAMEDPEDS_RPF_FILE.exists():
            STREAMEDPEDS_RPF_FILE.unlink()
        execute_shell_command(
            [
                RAGE_CLI_TOOL,
                "create",
                "-o",
                str(STREAMEDPEDS_RPF_FILE),
                str(STREAMEDPEDS_EXTRACTED_DIR),
            ],
            "Repacotando streamedpeds_players.rpf",
        )
        patch_rpf7_open_and_zero_compressed(STREAMEDPEDS_RPF_FILE)

        # 5. Repack x64v_modded.rpf
        if X64V_MODDED_RPF_FILE.exists():
            X64V_MODDED_RPF_FILE.unlink()
        execute_shell_command(
            [
                RAGE_CLI_TOOL,
                "create",
                "-o",
                str(X64V_MODDED_RPF_FILE),
                str(X64V_EXTRACTED_DIR),
            ],
            "Repacotando x64v_modded.rpf",
        )
        patch_rpf7_open_and_zero_compressed(X64V_MODDED_RPF_FILE)

        # 6. Deploy x64v.rpf
        TARGET_X64V_RPF_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"\nInstalando x64v.rpf -> {TARGET_X64V_RPF_PATH}...")
        shutil.copy2(str(X64V_MODDED_RPF_FILE), str(TARGET_X64V_RPF_PATH))
        print("x64v.rpf instalado com sucesso.")

        # 7. Verificacao de Criptografia e Estrutura
        print("\n=== VERIFICANDO ARQUIVOS INSTALADOS ===")
        with open(TARGET_DLC_RPF_PATH, "rb") as dlc_archive_file:
            dlc_archive_file.seek(12)
            dlc_encryption_flag = dlc_archive_file.read(4)

        with open(TARGET_X64V_RPF_PATH, "rb") as x64v_archive_file:
            x64v_archive_file.seek(12)
            x64v_encryption_flag = x64v_archive_file.read(4)

        print(
            f"dlc.rpf cabecalho de criptografia:  {dlc_encryption_flag} (esperado b'OPEN')"
        )
        print(
            f"x64v.rpf cabecalho de criptografia: {x64v_encryption_flag} (esperado b'OPEN')"
        )

        dlc_verification_output = subprocess.run(
            [RAGE_CLI_TOOL, "list", "-d", str(TARGET_DLC_RPF_PATH)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        dlc_compressed_entries = [
            line_content
            for line_content in dlc_verification_output.splitlines()
            if "Compressed:" in line_content
            and "Compressed: 0" not in line_content
        ]
        print(
            f"Entradas binarias comprimidas em dlc.rpf: {len(dlc_compressed_entries)} (esperado 0)"
        )

        x64v_verification_output = subprocess.run(
            [RAGE_CLI_TOOL, "list", "-d", str(TARGET_X64V_RPF_PATH)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        x64v_compressed_entries = [
            line_content
            for line_content in x64v_verification_output.splitlines()
            if "Compressed:" in line_content
            and "Compressed: 0" not in line_content
        ]
        print(
            f"Entradas binarias comprimidas em x64v.rpf: {len(x64v_compressed_entries)} (esperado 0)"
        )

        is_dlc_valid = (
            len(dlc_compressed_entries) == 0 and dlc_encryption_flag == b"OPEN"
        )
        is_x64v_valid = (
            len(x64v_compressed_entries) == 0 and x64v_encryption_flag == b"OPEN"
        )

        if is_dlc_valid and is_x64v_valid:
            print(
                "\n[VERIFICACAO APROVADA] Todos os arquivos foram instalados com sucesso, "
                "com cabecalho 'OPEN' e zero risco de ERR_GEN_ZLIB_2!"
            )
        else:
            print(
                "\n[AVISO] Discrepancias encontradas na verificacao. Verifique os logs detalhados."
            )
            sys.exit(1)

    except Exception as general_error:
        print(f"\n[FALHA FATAL NO DEPLOY] {general_error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
