#!/usr/bin/env python3
"""
repack_and_deploy_everything.py
===============================
Repack and deploy all GTA V mod RPF archives with live progress bars:
  1. Repack mppatches.rpf and patch TOC (f_size=0, enc='OPEN')
  2. Repack mppatchesng_dlc.rpf and patch TOC (f_size=0, enc='OPEN')
  3. Deploy dlc.rpf -> <gtav_mods>/update/x64/dlcpacks/mppatchesng/dlc.rpf
  4. Repack/Deploy patchday4ng (when present in staging)
  5. Repack streamedpeds_players.rpf and patch TOC (f_size=0, enc='OPEN')
  6. Repack streamedpedprops.rpf and patch TOC (f_size=0, enc='OPEN')
  7. Repack x64v_modded.rpf and patch TOC (f_size=0, enc='OPEN')
  8. Deploy x64v.rpf -> <gtav_mods>/x64v.rpf
  9. Run strict integrity verification (`rage list -d` + header check)
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict

# Add current directory to sys.path so shared helpers import in both layouts.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    import vrc2gtav_i18n as project_i18n
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import vrc2gtav_i18n as project_i18n
    from common_tools import vrc2gtav_paths as project_paths


def _load_repack_paths() -> Dict[str, object]:
    """Resolve all executable, staging, and target archive paths from vrc2gtav.cfg."""
    rpf_paths_cfg = project_paths.get_rpf_paths()
    mppatchesng_extracted_dir = rpf_paths_cfg["mppatches_dlc_extracted"]
    patchday4ng_extracted_dir = rpf_paths_cfg["patchday4ng_dlc_extracted"]
    x64v_extracted_dir = rpf_paths_cfg["x64v_extracted"]
    return {
        "rage_cli": project_paths.get_rage_cli(),
        "gtav_mods_dir": project_paths.get_gtav_mods_dir(),
        "staging_dir": project_paths.get_staging_dir(),
        "mppatches_extracted_dir": rpf_paths_cfg["mppatches_extracted"],
        "mppatchesng_extracted_dir": mppatchesng_extracted_dir,
        "mppatches_rpf_file": mppatchesng_extracted_dir / rpf_paths_cfg["mppatches_rpf_relative"],
        "mppatchesng_dlc_rpf_file": rpf_paths_cfg["mppatches_modded_rpf"],
        "target_dlc_rpf_path": rpf_paths_cfg["mppatches_game_rpf"],
        "patchday4ng_extracted_dir": patchday4ng_extracted_dir,
        "patchday4ng_inner_rpf": patchday4ng_extracted_dir / rpf_paths_cfg["patchday4ng_rpf_relative"],
        "patchday4ng_models_dir": rpf_paths_cfg["patchday4ng_models_extracted"],
        "patchday4ng_dlc_rpf_file": rpf_paths_cfg["patchday4ng_modded_rpf"],
        "target_patchday4ng_dlc_path": rpf_paths_cfg["patchday4ng_game_rpf"],
        "streamedpeds_extracted_dir": rpf_paths_cfg["streamedpeds_extracted"],
        "streamedpedprops_extracted_dir": rpf_paths_cfg["streamedpedprops_extracted"],
        "x64v_extracted_dir": x64v_extracted_dir,
        "streamedpeds_rpf_file": x64v_extracted_dir / rpf_paths_cfg["streamedpeds_rpf_relative"],
        "streamedpedprops_rpf_file": x64v_extracted_dir / rpf_paths_cfg["streamedpedprops_rpf_relative"],
        "x64v_modded_rpf_file": rpf_paths_cfg["x64v_modded_rpf"],
        "target_x64v_rpf_path": rpf_paths_cfg["x64v_game_rpf"],
    }


def patch_rpf7_open_and_zero_compressed(rpf_file_path: Path) -> int:
    """
    Patch an RPF7 archive table of contents:
      1. Set the encryption header flag at offset 12 to 'OPEN'.
      2. Zero out compressed-size bytes for non-resource binary entries.
    Prevents streaming stalls and ERR_GEN_ZLIB_2 crashes in GTA V.
    """
    if not rpf_file_path.exists():
        raise FileNotFoundError(
            project_i18n.translate("repack.rpf_not_found", path=rpf_file_path)
        )

    patched_entries_count = 0
    try:
        with open(rpf_file_path, "r+b") as rpf_file_handle:
            header_bytes = rpf_file_handle.read(16)
            magic_number, total_entries_count, _names_length, _encryption_flag = (
                struct.unpack("<IIII", header_bytes)
            )

            # Verify valid RPF7 magic value (0x52504637 == '7FPR')
            if magic_number != 0x52504637:
                raise ValueError(
                    project_i18n.translate(
                        "repack.rpf7_invalid_magic",
                        path=rpf_file_path,
                        magic=magic_number,
                    )
                )

            # Write 'OPEN' encryption flag
            rpf_file_handle.seek(12)
            rpf_file_handle.write(b"OPEN")

            # Read the 16-byte-per-entry TOC table
            rpf_file_handle.seek(16)
            toc_table_data = rpf_file_handle.read(total_entries_count * 16)

            for entry_index in range(total_entries_count):
                entry_byte_offset = entry_index * 16
                entry_record = bytearray(
                    toc_table_data[entry_byte_offset : entry_byte_offset + 16]
                )
                entry_descriptor = struct.unpack("<I", entry_record[4:8])[0]

                # Skip directories (0x7FFFFF00) and RSC7 game resources (bit 31 set)
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
            project_i18n.translate(
                "repack.rpf_patch_failed",
                path=rpf_file_path,
                error=error_exception,
            )
        )
        raise

    print(
        project_i18n.translate(
            "repack.rpf7_patched_summary",
            filename=rpf_file_path.name,
            count=patched_entries_count,
        )
    )
    return patched_entries_count


def get_adaptive_bar_width(reserved_columns: int = 62) -> int:
    """Compute progress bar width to fit cleanly within the terminal width."""
    terminal_columns = shutil.get_terminal_size(fallback=(80, 24)).columns
    available_columns = terminal_columns - reserved_columns
    return max(12, min(28, available_columns))


def format_progress_bar(fraction_value: float, bar_width: int = 0) -> str:
    """Format a normalized ASCII progress bar within [0.0, 1.0]."""
    resolved_width = bar_width if bar_width > 0 else get_adaptive_bar_width()
    clamped_fraction = max(0.0, min(1.0, fraction_value))
    filled_count = int(round(clamped_fraction * resolved_width))
    empty_count = resolved_width - filled_count
    return f"[{'#' * filled_count}{'-' * empty_count}]"


def format_indeterminate_bar(tick_index: int, bar_width: int = 0) -> str:
    """Format a sliding ASCII activity indicator while output size is still zero."""
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
    """Write a progress update adapting automatically between interactive TTY and pipes."""
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
    """Tracks and prints overall progress across all repack/deploy stages."""

    def __init__(self, total_stages: int):
        """Initialize tracker with total stage count."""
        self.total_stages = max(1, total_stages)
        self.current_stage = 0
        self.pipeline_start_time = time.time()

    def begin_stage(self, stage_title: str) -> None:
        """Advance to the next stage and print the overall progress banner."""
        self.current_stage = min(self.total_stages, self.current_stage + 1)
        fraction_completed = (self.current_stage - 1) / self.total_stages
        global_bar = format_progress_bar(fraction_completed, bar_width=24)
        percent_completed = fraction_completed * 100.0
        elapsed_seconds = time.time() - self.pipeline_start_time
        print(
            project_i18n.translate(
                "repack.stage_line",
                current=self.current_stage,
                total=self.total_stages,
                bar=global_bar,
                percent=percent_completed,
                title=stage_title,
                elapsed=elapsed_seconds,
            ),
            flush=True,
        )

    def finish_pipeline(self) -> None:
        """Print the completed 100% pipeline banner."""
        global_bar = format_progress_bar(1.0, bar_width=24)
        total_elapsed = time.time() - self.pipeline_start_time
        print(
            project_i18n.translate(
                "repack.pipeline_complete_line",
                bar=global_bar,
                elapsed=total_elapsed,
            ),
            flush=True,
        )


def compute_directory_total_bytes(target_directory: Path) -> int:
    """Compute cumulative input file size inside a folder to estimate RPF output volume."""
    total_size_bytes = 0
    if not target_directory.is_dir():
        return 0
    for walk_root, dir_names, file_names in os.walk(target_directory):
        # Preserve directory traversal list without short temporary identifiers
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
    Copy a large archive in 4 MB chunks while displaying progress, throughput
    (MB/s), and ETA, preserving file metadata (equivalent to shutil.copy2).
    """
    destination_file_path.parent.mkdir(parents=True, exist_ok=True)
    total_file_bytes = source_file_path.stat().st_size
    total_megabytes = total_file_bytes / (1024.0 * 1024.0)
    print(
        project_i18n.translate(
            "repack.installing_start",
            label=copy_label,
            megabytes=total_megabytes,
            dest=destination_file_path,
        ),
        flush=True,
    )

    if total_file_bytes == 0:
        shutil.copy2(str(source_file_path), str(destination_file_path))
        write_progress_line(
            project_i18n.translate(
                "repack.copy_zero_done", bar=format_progress_bar(1.0)
            ),
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
                    progress_text = project_i18n.translate(
                        "repack.copy_progress",
                        bar=format_progress_bar(fraction_done),
                        percent=percent_done,
                        copied_mb=copied_megabytes,
                        total_mb=total_megabytes,
                        rate_mbs=transfer_rate_mbs,
                        eta_sec=eta_seconds,
                    )
                    write_progress_line(progress_text, is_final=False)
                    last_tty_refresh = current_time
                    while next_non_tty_milestone <= percent_done:
                        next_non_tty_milestone += 25.0

    shutil.copystat(str(source_file_path), str(destination_file_path))
    total_elapsed = max(0.001, time.time() - copy_start_time)
    final_rate_mbs = total_megabytes / total_elapsed
    write_progress_line(
        project_i18n.translate(
            "repack.copy_done",
            bar=format_progress_bar(1.0),
            total_mb=total_megabytes,
            rate_mbs=final_rate_mbs,
            elapsed=total_elapsed,
        ),
        is_final=True,
    )
    print(project_i18n.translate("repack.installed_ok", label=copy_label), flush=True)


def execute_rage_create_with_progress(
    command_arguments_list: list,
    output_rpf_path: Path,
    source_directory_path: Path,
    task_description: str,
) -> str:
    """
    Run `rage create` while monitoring real-time disk growth and showing
    an animated activity indicator during input scanning.
    """
    expected_bytes = max(1, compute_directory_total_bytes(source_directory_path))
    expected_megabytes = expected_bytes / (1024.0 * 1024.0)
    print(
        project_i18n.translate(
            "repack.create_start",
            description=task_description,
            expected_mb=expected_megabytes,
        ),
        flush=True,
    )

    start_timestamp = time.time()
    process_handle = subprocess.Popen(
        command_arguments_list,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
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
            line_msg = project_i18n.translate(
                "repack.reading_files",
                bar=activity_bar,
                elapsed=elapsed_seconds,
                expected_mb=expected_megabytes,
            )
            if is_interactive_tty:
                write_progress_line(line_msg, is_final=False)
                tty_line_active = True
            elif current_time - last_log_heartbeat >= 5.0:
                write_progress_line(line_msg, is_final=True)
                last_log_heartbeat = current_time
        else:
            write_fraction = min(0.99, written_bytes / expected_bytes)
            write_percent = write_fraction * 100.0
            written_megabytes = written_bytes / (1024.0 * 1024.0)
            line_msg = project_i18n.translate(
                "repack.writing_rpf",
                bar=format_progress_bar(write_fraction),
                percent=write_percent,
                written_mb=written_megabytes,
                expected_mb=expected_megabytes,
                elapsed=elapsed_seconds,
            )
            if is_interactive_tty:
                write_progress_line(line_msg, is_final=False)
                tty_line_active = True
            elif write_percent >= next_write_milestone or (current_time - last_log_heartbeat >= 5.0):
                write_progress_line(line_msg, is_final=True)
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
        print(project_i18n.translate("repack.cmd_failed", description=task_description))
        print(
            project_i18n.translate(
                "repack.return_code", returncode=process_handle.returncode
            )
        )
        print(project_i18n.translate("repack.process_output"))
        print(combined_stdout)
        raise subprocess.CalledProcessError(
            process_handle.returncode, command_arguments_list, output=combined_stdout
        )

    final_seconds = max(0.001, time.time() - start_timestamp)
    final_bytes = output_rpf_path.stat().st_size if output_rpf_path.exists() else 0
    final_megabytes = final_bytes / (1024.0 * 1024.0)
    write_progress_line(
        project_i18n.translate(
            "repack.create_done",
            bar=format_progress_bar(1.0),
            final_mb=final_megabytes,
            elapsed=final_seconds,
        ),
        is_final=True,
    )
    return combined_stdout


def repack_single_rpf_stage(
    output_rpf_path: Path,
    source_directory_path: Path,
    task_description: str,
    rage_cli_binary: str,
) -> None:
    """Remove stale output RPF, rebuild via `rage create`, and patch header/TOC."""
    if output_rpf_path.exists():
        output_rpf_path.unlink()
    execute_rage_create_with_progress(
        [
            rage_cli_binary,
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


def run_repack_and_deploy() -> None:
    """Execute the full RPF repack, OPEN header patch, deploy, and verify flow."""
    paths_map = _load_repack_paths()
    rage_cli_tool = str(paths_map["rage_cli"])
    gtav_mods_dir = Path(paths_map["gtav_mods_dir"])
    staging_dir = Path(paths_map["staging_dir"])

    mppatches_extracted_dir = Path(paths_map["mppatches_extracted_dir"])
    mppatchesng_extracted_dir = Path(paths_map["mppatchesng_extracted_dir"])
    mppatches_rpf_file = Path(paths_map["mppatches_rpf_file"])
    mppatchesng_dlc_rpf_file = Path(paths_map["mppatchesng_dlc_rpf_file"])
    target_dlc_rpf_path = Path(paths_map["target_dlc_rpf_path"])

    patchday4ng_extracted_dir = Path(paths_map["patchday4ng_extracted_dir"])
    patchday4ng_inner_rpf = Path(paths_map["patchday4ng_inner_rpf"])
    patchday4ng_models_dir = Path(paths_map["patchday4ng_models_dir"])
    patchday4ng_dlc_rpf_file = Path(paths_map["patchday4ng_dlc_rpf_file"])
    target_patchday4ng_dlc_path = Path(paths_map["target_patchday4ng_dlc_path"])

    streamedpeds_extracted_dir = Path(paths_map["streamedpeds_extracted_dir"])
    streamedpedprops_extracted_dir = Path(paths_map["streamedpedprops_extracted_dir"])
    x64v_extracted_dir = Path(paths_map["x64v_extracted_dir"])
    streamedpeds_rpf_file = Path(paths_map["streamedpeds_rpf_file"])
    streamedpedprops_rpf_file = Path(paths_map["streamedpedprops_rpf_file"])
    x64v_modded_rpf_file = Path(paths_map["x64v_modded_rpf_file"])
    target_x64v_rpf_path = Path(paths_map["target_x64v_rpf_path"])

    print(project_i18n.translate("repack.banner"), flush=True)
    print(f"RAGE CLI:        {rage_cli_tool}", flush=True)
    print(f"Staging RPF:     {staging_dir}", flush=True)
    print(project_i18n.translate("repack.gtav_dest", path=gtav_mods_dir), flush=True)

    if not staging_dir.exists():
        print(project_i18n.translate("repack.staging_missing", path=staging_dir))
        sys.exit(1)

    has_patchday4ng_staging = (
        patchday4ng_extracted_dir.exists() and patchday4ng_models_dir.exists()
    )
    has_streamedpedprops_staging = streamedpedprops_extracted_dir.is_dir()

    total_pipeline_stages = (
        7
        + (3 if has_patchday4ng_staging else 0)
        + (1 if has_streamedpedprops_staging else 0)
    )
    stage_tracker = PipelineProgressTracker(total_pipeline_stages)

    try:
        # 1. Repack mppatches.rpf
        stage_title = project_i18n.translate("repack.stage_repacking", name="mppatches.rpf")
        stage_tracker.begin_stage(stage_title)
        repack_single_rpf_stage(
            mppatches_rpf_file,
            mppatches_extracted_dir,
            stage_title,
            rage_cli_tool,
        )

        # 2. Repack mppatchesng_dlc.rpf
        stage_title = project_i18n.translate("repack.stage_repacking", name="mppatchesng_dlc.rpf")
        stage_tracker.begin_stage(stage_title)
        repack_single_rpf_stage(
            mppatchesng_dlc_rpf_file,
            mppatchesng_extracted_dir,
            stage_title,
            rage_cli_tool,
        )

        # 3. Deploy dlc.rpf
        stage_tracker.begin_stage(
            project_i18n.translate("repack.stage_installing", name="mppatchesng/dlc.rpf")
        )
        copy_file_with_progress(
            mppatchesng_dlc_rpf_file, target_dlc_rpf_path, "dlc.rpf"
        )

        # 3B. Repack and deploy patchday4ng when present in staging
        if has_patchday4ng_staging:
            stage_title = project_i18n.translate("repack.stage_repacking", name="patchday4ng.rpf")
            stage_tracker.begin_stage(stage_title)
            repack_single_rpf_stage(
                patchday4ng_inner_rpf,
                patchday4ng_models_dir,
                stage_title,
                rage_cli_tool,
            )

            stage_title = project_i18n.translate("repack.stage_repacking", name="patchday4ng dlc.rpf")
            stage_tracker.begin_stage(stage_title)
            repack_single_rpf_stage(
                patchday4ng_dlc_rpf_file,
                patchday4ng_extracted_dir,
                stage_title,
                rage_cli_tool,
            )

            stage_tracker.begin_stage(
                project_i18n.translate("repack.stage_installing", name="patchday4ng/dlc.rpf")
            )
            copy_file_with_progress(
                patchday4ng_dlc_rpf_file,
                target_patchday4ng_dlc_path,
                "patchday4ng/dlc.rpf",
            )

        # 4. Repack streamedpeds_players.rpf
        stage_title = project_i18n.translate(
            "repack.stage_repacking", name="streamedpeds_players.rpf"
        )
        stage_tracker.begin_stage(stage_title)
        repack_single_rpf_stage(
            streamedpeds_rpf_file,
            streamedpeds_extracted_dir,
            stage_title,
            rage_cli_tool,
        )

        # 4B. Repack streamedpedprops.rpf (props and eyewear dummies)
        if has_streamedpedprops_staging:
            stage_title = project_i18n.translate(
                "repack.stage_repacking", name="streamedpedprops.rpf"
            )
            stage_tracker.begin_stage(stage_title)
            repack_single_rpf_stage(
                streamedpedprops_rpf_file,
                streamedpedprops_extracted_dir,
                stage_title,
                rage_cli_tool,
            )
        else:
            print(
                project_i18n.translate(
                    "repack.props_missing_skip", path=streamedpedprops_extracted_dir
                )
            )

        # 5. Repack x64v_modded.rpf
        stage_title = project_i18n.translate("repack.stage_repacking", name="x64v_modded.rpf")
        stage_tracker.begin_stage(stage_title)
        repack_single_rpf_stage(
            x64v_modded_rpf_file,
            x64v_extracted_dir,
            stage_title,
            rage_cli_tool,
        )

        # 6. Deploy x64v.rpf
        stage_tracker.begin_stage(
            project_i18n.translate("repack.stage_installing", name="x64v.rpf")
        )
        copy_file_with_progress(
            x64v_modded_rpf_file, target_x64v_rpf_path, "x64v.rpf"
        )

        # 7. Verify encryption flags and uncompressed TOC entries
        stage_tracker.begin_stage(project_i18n.translate("repack.stage_verifying"))
        print(project_i18n.translate("repack.verifying_header"), flush=True)
        with open(target_dlc_rpf_path, "rb") as dlc_archive_file:
            dlc_archive_file.seek(12)
            dlc_encryption_flag = dlc_archive_file.read(4)

        with open(target_x64v_rpf_path, "rb") as x64v_archive_file:
            x64v_archive_file.seek(12)
            x64v_encryption_flag = x64v_archive_file.read(4)

        print(
            project_i18n.translate(
                "repack.verify_dlc_header", flag=dlc_encryption_flag
            )
        )
        print(
            project_i18n.translate(
                "repack.verify_x64v_header", flag=x64v_encryption_flag
            )
        )

        dlc_verification_output = subprocess.run(
            [rage_cli_tool, "list", "-d", str(target_dlc_rpf_path)],
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
            project_i18n.translate(
                "repack.verify_dlc_compressed", count=len(dlc_compressed_entries)
            )
        )

        x64v_verification_output = subprocess.run(
            [rage_cli_tool, "list", "-d", str(target_x64v_rpf_path)],
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
            project_i18n.translate(
                "repack.verify_x64v_compressed", count=len(x64v_compressed_entries)
            )
        )

        is_dlc_valid = (
            len(dlc_compressed_entries) == 0 and dlc_encryption_flag == b"OPEN"
        )
        is_x64v_valid = (
            len(x64v_compressed_entries) == 0 and x64v_encryption_flag == b"OPEN"
        )

        if is_dlc_valid and is_x64v_valid:
            stage_tracker.finish_pipeline()
            print(project_i18n.translate("repack.verify_passed"))
        else:
            print(project_i18n.translate("repack.verify_warn"))
            sys.exit(1)

    except Exception as general_error:
        print(project_i18n.translate("repack.fatal_error", error=general_error))
        sys.exit(1)


def main() -> None:
    """CLI entrypoint for RPF repacking and GTA V deployment."""
    project_i18n.set_active_language()
    argument_parser = argparse.ArgumentParser(
        description=project_i18n.translate("repack.cli_description")
    )
    argument_parser.add_argument(
        "--lang",
        choices=["auto", "en", "ja", "pt"],
        default="auto",
        help=project_i18n.translate("common.language_option_help"),
    )
    parsed_arguments = argument_parser.parse_args()
    project_i18n.set_active_language(parsed_arguments.lang)
    run_repack_and_deploy()


if __name__ == "__main__":
    main()
