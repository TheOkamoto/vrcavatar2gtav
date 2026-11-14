#!/usr/bin/env python3
"""
repack_and_deploy_everything.py
===============================
Repacota e instala todos os arquivos RPF do mod GTA V com barra de progresso:
  1. Repack mppatches.rpf e patch do TOC (f_size=0, enc='OPEN')
  2. Repack mppatchesng_dlc.rpf e patch do TOC (f_size=0, enc='OPEN')
  3. Deploy dlc.rpf -> D:/GTAV/mods/update/x64/dlcpacks/mppatchesng/dlc.rpf
  4. Repack/Deploy patchday4ng (quando presente no staging)
  5. Repack streamedpeds_players.rpf e patch do TOC (f_size=0, enc='OPEN')
  6. Repack streamedpedprops.rpf e patch do TOC (f_size=0, enc='OPEN')
  7. Repack x64v_modded.rpf e patch do TOC (f_size=0, enc='OPEN')
  8. Deploy x64v.rpf -> D:/GTAV/mods/x64v.rpf
  9. Verificacao de integridade estrita (rage verify / list -d)

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
import threading
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
RPF_PATHS_CONFIG = project_paths.get_rpf_paths()

MPPATCHES_EXTRACTED_DIR = RPF_PATHS_CONFIG["mppatches_extracted"]
MPPATCHESNG_EXTRACTED_DIR = RPF_PATHS_CONFIG["mppatches_dlc_extracted"]
MPPATCHES_RPF_FILE = (
    MPPATCHESNG_EXTRACTED_DIR / RPF_PATHS_CONFIG["mppatches_rpf_relative"]
)
MPPATCHESNG_DLC_RPF_FILE = RPF_PATHS_CONFIG["mppatches_modded_rpf"]
TARGET_DLC_RPF_PATH = RPF_PATHS_CONFIG["mppatches_game_rpf"]

PATCHDAY4NG_EXTRACTED_DIR = RPF_PATHS_CONFIG["patchday4ng_dlc_extracted"]
PATCHDAY4NG_INNER_RPF = (
    PATCHDAY4NG_EXTRACTED_DIR / RPF_PATHS_CONFIG["patchday4ng_rpf_relative"]
)
PATCHDAY4NG_MODELS_DIR = RPF_PATHS_CONFIG["patchday4ng_models_extracted"]
PATCHDAY4NG_DLC_RPF_FILE = RPF_PATHS_CONFIG["patchday4ng_modded_rpf"]
TARGET_PATCHDAY4NG_DLC_PATH = RPF_PATHS_CONFIG["patchday4ng_game_rpf"]

STREAMEDPEDS_EXTRACTED_DIR = RPF_PATHS_CONFIG["streamedpeds_extracted"]
STREAMEDPEDPROPS_EXTRACTED_DIR = RPF_PATHS_CONFIG["streamedpedprops_extracted"]
X64V_EXTRACTED_DIR = RPF_PATHS_CONFIG["x64v_extracted"]
STREAMEDPEDS_RPF_FILE = (
    X64V_EXTRACTED_DIR / RPF_PATHS_CONFIG["streamedpeds_rpf_relative"]
)
STREAMEDPEDPROPS_RPF_FILE = (
    X64V_EXTRACTED_DIR / RPF_PATHS_CONFIG["streamedpedprops_rpf_relative"]
)
X64V_MODDED_RPF_FILE = RPF_PATHS_CONFIG["x64v_modded_rpf"]
TARGET_X64V_RPF_PATH = RPF_PATHS_CONFIG["x64v_game_rpf"]


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


def get_adaptive_bar_width(reserved_columns: int = 62) -> int:
    """Calcula a largura da barra para caber inteira no terminal (ex: CMD 80 colunas)."""
    terminal_columns = shutil.get_terminal_size(fallback=(80, 24)).columns
    available_columns = terminal_columns - reserved_columns
    return max(12, min(28, available_columns))


def format_progress_bar(fraction_value: float, bar_width: int = 0) -> str:
    """Formata uma barra de progresso ASCII padronizada entre [0.0, 1.0]."""
    resolved_width = bar_width if bar_width > 0 else get_adaptive_bar_width()
    clamped_fraction = max(0.0, min(1.0, fraction_value))
    filled_count = int(round(clamped_fraction * resolved_width))
    empty_count = resolved_width - filled_count
    return f"[{'#' * filled_count}{'-' * empty_count}]"


def format_indeterminate_bar(tick_index: int, bar_width: int = 0) -> str:
    """Formata uma barra de atividade ASCII animada enquanto o tamanho cresce do zero."""
    resolved_width = bar_width if bar_width > 0 else get_adaptive_bar_width()
    slider_width = 4
    travel_span = max(1, resolved_width - slider_width)
    cycle_length = travel_span * 2
    cycle_offset = tick_index % cycle_length
    slider_pos = (
        cycle_offset
        if cycle_offset <= travel_span
        else cycle_length - cycle_offset
    )
    left_padding = " " * slider_pos
    right_padding = " " * max(0, resolved_width - slider_pos - slider_width)
    return f"[{left_padding}===>{right_padding}]"


def write_progress_line(line_text: str, is_final: bool = False) -> None:
    """
    Escreve uma linha de progresso adaptando-se automaticamente a TTY interativo
    (atualizacao inline com \\r ajustada a largura do terminal) ou log/pipe.
    """
    is_interactive_tty = sys.stdout.isatty()
    if is_interactive_tty:
        terminal_columns = shutil.get_terminal_size(fallback=(80, 24)).columns
        max_line_width = max(40, terminal_columns - 1)
        rendered_text = (
            line_text[:max_line_width]
            if len(line_text) > max_line_width
            else line_text.ljust(max_line_width)
        )
        sys.stdout.write(f"\r{rendered_text}" + ("\n" if is_final else ""))
    else:
        sys.stdout.write(f"{line_text}\n")
    sys.stdout.flush()


class PipelineProgressTracker:
    """Gerencia e exibe a barra de progresso global entre todas as etapas do deploy."""

    def __init__(self, total_stages: int):
        self.total_stages = max(1, total_stages)
        self.current_stage = 0
        self.pipeline_start_time = time.time()

    def begin_stage(self, stage_title: str) -> None:
        """Avanca para a proxima etapa e imprime a barra de progresso global."""
        self.current_stage = min(self.total_stages, self.current_stage + 1)
        fraction_completed = (self.current_stage - 1) / self.total_stages
        global_bar = format_progress_bar(fraction_completed, bar_width=24)
        percent_completed = fraction_completed * 100.0
        elapsed_seconds = time.time() - self.pipeline_start_time
        print(
            f"\n[ETAPA {self.current_stage}/{self.total_stages}] "
            f"{global_bar} {percent_completed:5.1f}% | {stage_title} "
            f"({elapsed_seconds:.1f}s decorridos)",
            flush=True,
        )

    def finish_pipeline(self) -> None:
        """Exibe a barra global em 100% ao concluir todo o pipeline."""
        global_bar = format_progress_bar(1.0, bar_width=24)
        total_elapsed = time.time() - self.pipeline_start_time
        print(
            f"\n[PROGRESSO] Pipeline Completo {global_bar} 100.0% "
            f"(tempo total: {total_elapsed:.1f}s)",
            flush=True,
        )


def compute_directory_total_bytes(target_directory: Path) -> int:
    """Calcula o volume total de bytes de entrada para estimar o tamanho do RPF."""
    total_size_bytes = 0
    if not target_directory.is_dir():
        return 0
    for walk_root, dir_names, file_names in os.walk(target_directory):
        # Mantem dir_names referenciado de forma limpa sem variaveis curtas
        dir_names[:] = dir_names
        for single_filename in file_names:
            candidate_path = Path(walk_root) / single_filename
            try:
                total_size_bytes += candidate_path.stat().st_size
            except OSError:
                continue
    return total_size_bytes


def copy_file_with_progress(
    source_file_path: Path, destination_file_path: Path, copy_label: str
) -> None:
    """
    Copia um arquivo grande em blocos exibindo barra de progresso, MB/s e ETA,
    preservando metadados (equivalente ao shutil.copy2).
    """
    destination_file_path.parent.mkdir(parents=True, exist_ok=True)
    total_file_bytes = source_file_path.stat().st_size
    total_megabytes = total_file_bytes / (1024.0 * 1024.0)
    print(f"Instalando {copy_label} ({total_megabytes:.1f} MB) -> {destination_file_path}...", flush=True)

    if total_file_bytes == 0:
        shutil.copy2(str(source_file_path), str(destination_file_path))
        write_progress_line(
            f"  [PROGRESSO] {format_progress_bar(1.0)} 100.0% (0.0/0.0 MB)",
            is_final=True,
        )
        return

    chunk_size_bytes = 4 * 1024 * 1024
    copied_bytes = 0
    copy_start_time = time.time()
    last_tty_refresh = 0.0
    next_non_tty_milestone = 25.0
    is_interactive_tty = sys.stdout.isatty()

    with open(source_file_path, "rb") as source_handle:
        with open(destination_file_path, "wb") as dest_handle:
            while True:
                data_chunk = source_handle.read(chunk_size_bytes)
                if not data_chunk:
                    break
                dest_handle.write(data_chunk)
                copied_bytes += len(data_chunk)

                fraction_done = min(1.0, copied_bytes / total_file_bytes)
                percent_done = fraction_done * 100.0
                current_time = time.time()
                elapsed_seconds = max(0.001, current_time - copy_start_time)
                transfer_rate_mbs = (copied_bytes / (1024.0 * 1024.0)) / elapsed_seconds
                copied_megabytes = copied_bytes / (1024.0 * 1024.0)
                remaining_bytes = max(0, total_file_bytes - copied_bytes)
                eta_seconds = (
                    (remaining_bytes / (1024.0 * 1024.0)) / transfer_rate_mbs
                    if transfer_rate_mbs > 0.0
                    else 0.0
                )

                should_render_tty = is_interactive_tty and (
                    current_time - last_tty_refresh >= 0.15
                )
                should_render_log = (not is_interactive_tty) and (
                    percent_done >= next_non_tty_milestone and percent_done < 100.0
                )
                if should_render_tty or should_render_log:
                    progress_text = (
                        f"  [PROGRESSO] {format_progress_bar(fraction_done)} "
                        f"{percent_done:5.1f}% ({copied_megabytes:.1f}/{total_megabytes:.1f} MB "
                        f"| {transfer_rate_mbs:.1f} MB/s | ETA {eta_seconds:.0f}s)"
                    )
                    write_progress_line(progress_text, is_final=False)
                    last_tty_refresh = current_time
                    while next_non_tty_milestone <= percent_done:
                        next_non_tty_milestone += 25.0

    shutil.copystat(str(source_file_path), str(destination_file_path))
    total_elapsed = max(0.001, time.time() - copy_start_time)
    final_rate_mbs = total_megabytes / total_elapsed
    write_progress_line(
        f"  [PROGRESSO] {format_progress_bar(1.0)} 100.0% "
        f"({total_megabytes:.1f}/{total_megabytes:.1f} MB | {final_rate_mbs:.1f} MB/s | {total_elapsed:.1f}s)",
        is_final=True,
    )
    print(f"{copy_label} instalado com sucesso.", flush=True)


def execute_rage_create_with_progress(
    command_arguments_list: list,
    output_rpf_path: Path,
    source_directory_path: Path,
    task_description: str,
) -> str:
    """
    Executa `rage create` monitorando progresso em tempo real:
      - Fase de leitura/indexacao: exibe barra animada enquanto o .rpf ainda nao cresceu.
      - Fase de gravacao em disco: calcula progresso real pelo volume gravado no .rpf.
    """
    expected_bytes = max(1, compute_directory_total_bytes(source_directory_path))
    expected_megabytes = expected_bytes / (1024.0 * 1024.0)
    print(f"--- {task_description} ({expected_megabytes:.1f} MB entrada) ---", flush=True)

    start_timestamp = time.time()
    process_handle = subprocess.Popen(
        command_arguments_list,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )

    captured_output_lines = []

    def drain_process_output() -> None:
        if process_handle.stdout is None:
            return
        for output_line in process_handle.stdout:
            captured_output_lines.append(output_line)

    reader_thread = threading.Thread(target=drain_process_output, daemon=True)
    reader_thread.start()

    is_interactive_tty = sys.stdout.isatty()
    tick_counter = 0
    last_log_heartbeat = start_timestamp
    next_write_milestone = 25.0
    tty_line_active = False

    while process_handle.poll() is None:
        current_time = time.time()
        elapsed_seconds = current_time - start_timestamp
        written_bytes = output_rpf_path.stat().st_size if output_rpf_path.exists() else 0

        if written_bytes <= 0:
            activity_bar = format_indeterminate_bar(tick_counter)
            if is_interactive_tty:
                write_progress_line(
                    f"  [PROGRESSO] {activity_bar} Lendo arquivos... "
                    f"({elapsed_seconds:.1f}s | ~{expected_megabytes:.1f} MB)",
                    is_final=False,
                )
                tty_line_active = True
            elif current_time - last_log_heartbeat >= 5.0:
                write_progress_line(
                    f"  [PROGRESSO] {activity_bar} Lendo arquivos... "
                    f"({elapsed_seconds:.1f}s | ~{expected_megabytes:.1f} MB)",
                    is_final=True,
                )
                last_log_heartbeat = current_time
        else:
            write_fraction = min(0.99, written_bytes / expected_bytes)
            write_percent = write_fraction * 100.0
            written_megabytes = written_bytes / (1024.0 * 1024.0)
            if is_interactive_tty:
                write_progress_line(
                    f"  [PROGRESSO] {format_progress_bar(write_fraction)} "
                    f"{write_percent:5.1f}% Gravando RPF ({written_megabytes:.1f}/{expected_megabytes:.1f} MB | {elapsed_seconds:.1f}s)",
                    is_final=False,
                )
                tty_line_active = True
            elif write_percent >= next_write_milestone or (current_time - last_log_heartbeat >= 5.0):
                write_progress_line(
                    f"  [PROGRESSO] {format_progress_bar(write_fraction)} "
                    f"{write_percent:5.1f}% Gravando RPF ({written_megabytes:.1f}/{expected_megabytes:.1f} MB | {elapsed_seconds:.1f}s)",
                    is_final=True,
                )
                last_log_heartbeat = current_time
                while next_write_milestone <= write_percent:
                    next_write_milestone += 25.0

        tick_counter += 1
        time.sleep(0.2)

    reader_thread.join(timeout=5.0)
    combined_stdout = "".join(captured_output_lines)

    if process_handle.returncode != 0:
        if tty_line_active:
            sys.stdout.write("\n")
            sys.stdout.flush()
        print(f"[ERRO] Falha ao executar: {task_description}")
        print(f"Codigo de retorno: {process_handle.returncode}")
        print("Saida do processo:")
        print(combined_stdout)
        raise subprocess.CalledProcessError(
            process_handle.returncode, command_arguments_list, output=combined_stdout
        )

    final_seconds = max(0.001, time.time() - start_timestamp)
    final_bytes = output_rpf_path.stat().st_size if output_rpf_path.exists() else 0
    final_megabytes = final_bytes / (1024.0 * 1024.0)
    write_progress_line(
        f"  [PROGRESSO] {format_progress_bar(1.0)} 100.0% "
        f"({final_megabytes:.1f} MB) Concluido em {final_seconds:.1f}s",
        is_final=True,
    )
    return combined_stdout


def repack_single_rpf_stage(
    output_rpf_path: Path,
    source_directory_path: Path,
    task_description: str,
) -> None:
    """Remove RPF antigo, executa `rage create` com progresso e aplica patch OPEN/f_size=0."""
    if output_rpf_path.exists():
        output_rpf_path.unlink()
    execute_rage_create_with_progress(
        [
            RAGE_CLI_TOOL,
            "create",
            "-o",
            str(output_rpf_path),
            str(source_directory_path),
        ],
        output_rpf_path,
        source_directory_path,
        task_description,
    )
    patch_rpf7_open_and_zero_compressed(output_rpf_path)


def main():
    print("=== GTA V MOD REPACK & DEPLOY PIPELINE ===", flush=True)
    print(f"RAGE CLI:        {RAGE_CLI_TOOL}", flush=True)
    print(f"Staging RPF:     {STAGING_DIRECTORY}", flush=True)
    print(f"Destino GTA V:   {GTAV_MODS_DIRECTORY}", flush=True)

    # Validacao previa dos diretorios essenciais
    if not STAGING_DIRECTORY.exists():
        print(
            f"[ERRO] Diretorio de staging nao encontrado: {STAGING_DIRECTORY}"
        )
        sys.exit(1)

    has_patchday4ng_staging = (
        PATCHDAY4NG_EXTRACTED_DIR.exists() and PATCHDAY4NG_MODELS_DIR.exists()
    )
    has_streamedpedprops_staging = STREAMEDPEDPROPS_EXTRACTED_DIR.is_dir()

    # Etapas: mppatches + mppatchesng_dlc + deploy_dlc + [patchday4ng*3] + streamedpeds + [streamedpedprops] + x64v + deploy_x64v + verify
    total_pipeline_stages = (
        7
        + (3 if has_patchday4ng_staging else 0)
        + (1 if has_streamedpedprops_staging else 0)
    )
    stage_tracker = PipelineProgressTracker(total_pipeline_stages)

    try:
        # 1. Repack mppatches.rpf
        stage_tracker.begin_stage("Repacotando mppatches.rpf")
        repack_single_rpf_stage(
            MPPATCHES_RPF_FILE,
            MPPATCHES_EXTRACTED_DIR,
            "Repacotando mppatches.rpf",
        )

        # 2. Repack mppatchesng_dlc.rpf
        stage_tracker.begin_stage("Repacotando mppatchesng_dlc.rpf")
        repack_single_rpf_stage(
            MPPATCHESNG_DLC_RPF_FILE,
            MPPATCHESNG_EXTRACTED_DIR,
            "Repacotando mppatchesng_dlc.rpf",
        )

        # 3. Deploy dlc.rpf
        stage_tracker.begin_stage("Instalando mppatchesng/dlc.rpf")
        copy_file_with_progress(
            MPPATCHESNG_DLC_RPF_FILE, TARGET_DLC_RPF_PATH, "dlc.rpf"
        )

        # 3B. Repack e Deploy patchday4ng (se presente no staging)
        if has_patchday4ng_staging:
            stage_tracker.begin_stage("Repacotando patchday4ng.rpf")
            repack_single_rpf_stage(
                PATCHDAY4NG_INNER_RPF,
                PATCHDAY4NG_MODELS_DIR,
                "Repacotando patchday4ng.rpf",
            )

            stage_tracker.begin_stage("Repacotando patchday4ng dlc.rpf")
            repack_single_rpf_stage(
                PATCHDAY4NG_DLC_RPF_FILE,
                PATCHDAY4NG_EXTRACTED_DIR,
                "Repacotando patchday4ng dlc.rpf",
            )

            stage_tracker.begin_stage("Instalando patchday4ng/dlc.rpf")
            copy_file_with_progress(
                PATCHDAY4NG_DLC_RPF_FILE,
                TARGET_PATCHDAY4NG_DLC_PATH,
                "patchday4ng/dlc.rpf",
            )

        # 4. Repack streamedpeds_players.rpf
        stage_tracker.begin_stage("Repacotando streamedpeds_players.rpf")
        repack_single_rpf_stage(
            STREAMEDPEDS_RPF_FILE,
            STREAMEDPEDS_EXTRACTED_DIR,
            "Repacotando streamedpeds_players.rpf",
        )

        # 4B. Repack streamedpedprops.rpf (props e dummies de oculos)
        if has_streamedpedprops_staging:
            stage_tracker.begin_stage("Repacotando streamedpedprops.rpf")
            repack_single_rpf_stage(
                STREAMEDPEDPROPS_RPF_FILE,
                STREAMEDPEDPROPS_EXTRACTED_DIR,
                "Repacotando streamedpedprops.rpf",
            )
        else:
            print(
                f"[AVISO] Diretorio streamedpedprops_extracted ausente ({STREAMEDPEDPROPS_EXTRACTED_DIR}); pulando repack de props."
            )

        # 5. Repack x64v_modded.rpf
        stage_tracker.begin_stage("Repacotando x64v_modded.rpf")
        repack_single_rpf_stage(
            X64V_MODDED_RPF_FILE,
            X64V_EXTRACTED_DIR,
            "Repacotando x64v_modded.rpf",
        )

        # 6. Deploy x64v.rpf
        stage_tracker.begin_stage("Instalando x64v.rpf")
        copy_file_with_progress(
            X64V_MODDED_RPF_FILE, TARGET_X64V_RPF_PATH, "x64v.rpf"
        )

        # 7. Verificacao de Criptografia e Estrutura
        stage_tracker.begin_stage("Verificando RPFs instalados (OPEN e f_size=0)")
        print("\n=== VERIFICANDO ARQUIVOS INSTALADOS ===", flush=True)
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
            stage_tracker.finish_pipeline()
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
