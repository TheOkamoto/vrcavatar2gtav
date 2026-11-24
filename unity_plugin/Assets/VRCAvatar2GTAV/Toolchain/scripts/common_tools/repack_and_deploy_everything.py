#!/usr/bin/env python3
"""
repack_and_deploy_everything.py
===============================
Repack and deploy all GTA V mod RPF archives with live progress bars:
  1. Repack mppatches.rpf and patch TOC (f_size=0, enc='OPEN')
  2. Repack mppatchesng_dlc.rpf and patch TOC (f_size=0, enc='OPEN')
  3. Deploy dlc.rpf -> <gtav_mods>/update/x64/dlcpacks/mppatchesng/dlc.rpf
  4. Repack/Deploy patchday3ng & patchday4ng (when present in staging)
  5. Repack streamedpeds_players.rpf and patch TOC (f_size=0, enc='OPEN')
  6. Repack streamedpedprops.rpf and patch TOC (f_size=0, enc='OPEN')
  7. Repack x64v_modded.rpf and patch TOC (f_size=0, enc='OPEN')
  8. Deploy x64v.rpf -> <gtav_mods>/x64v.rpf
  9. Run strict integrity verification (`rage list -d` + header check)
"""

import argparse
import hashlib
import io as io_stream
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add current directory to sys.path so shared helpers import in both layouts.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    import npc_registry_helper
    import ped_damage_helper
    import vrc2gtav_i18n as project_i18n
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import npc_registry_helper
    from common_tools import ped_damage_helper
    from common_tools import vrc2gtav_i18n as project_i18n
    from common_tools import vrc2gtav_paths as project_paths


def _build_patchday_spec(
    rpf_paths_cfg: Dict[str, Path],
    staging_dir: Path,
    project_root_dir: Path,
    pack_name: str,
) -> Dict[str, object]:
    """Resolve staging/work directories and output RPF paths for a patchday DLC."""
    dlc_extracted_dir = Path(
        rpf_paths_cfg.get(
            f"{pack_name}_dlc_extracted",
            staging_dir / f"{pack_name}_dlc_extracted",
        )
    )
    models_dir = Path(
        rpf_paths_cfg.get(
            f"{pack_name}_models_extracted",
            staging_dir / f"{pack_name}_models_extracted",
        )
    )
    if pack_name == "patchday3ng" and not (
        dlc_extracted_dir.exists() and models_dir.exists()
    ):
        legacy_work_dir = (
            project_root_dir
            / "1_Franklin_Shinano_Casual"
            / "5_rpf_package"
            / "patchday3_work"
        )
        legacy_dlc_dir = legacy_work_dir / "patchday3ng_extracted"
        legacy_models_dir = legacy_work_dir / "patchday3_extracted"
        if legacy_dlc_dir.exists() and legacy_models_dir.exists():
            dlc_extracted_dir = legacy_dlc_dir
            models_dir = legacy_models_dir

    rpf_relative_path = Path(
        rpf_paths_cfg.get(
            f"{pack_name}_rpf_relative",
            Path("x64") / "models" / "cdimages" / f"{pack_name}.rpf",
        )
    )
    dlc_rpf_file = Path(
        rpf_paths_cfg.get(
            f"{pack_name}_modded_rpf",
            staging_dir / f"{pack_name}_dlc.rpf",
        )
    )
    return {
        "name": pack_name,
        "dlc_extracted_dir": dlc_extracted_dir,
        "inner_rpf": dlc_extracted_dir / rpf_relative_path,
        "models_dir": models_dir,
        "dlc_rpf_file": dlc_rpf_file,
        "target_dlc_path": Path(rpf_paths_cfg[f"{pack_name}_game_rpf"]),
    }


def _load_repack_paths() -> Dict[str, object]:
    """Resolve all executable, staging, and target archive paths from vrc2gtav.cfg."""
    rpf_paths_cfg = project_paths.get_rpf_paths()
    staging_dir = project_paths.get_staging_dir()
    project_root_dir = project_paths.get_project_root()
    mppatchesng_extracted_dir = rpf_paths_cfg["mppatches_dlc_extracted"]
    x64v_extracted_dir = rpf_paths_cfg["x64v_extracted"]
    patchday_specs = [
        _build_patchday_spec(rpf_paths_cfg, staging_dir, project_root_dir, pack_name)
        for pack_name in ("patchday3ng", "patchday4ng")
    ]
    return {
        "rage_cli": project_paths.get_rage_cli(),
        "gtav_mods_dir": project_paths.get_gtav_mods_dir(),
        "staging_dir": staging_dir,
        "mppatches_extracted_dir": rpf_paths_cfg["mppatches_extracted"],
        "mppatchesng_extracted_dir": mppatchesng_extracted_dir,
        "mppatches_rpf_file": mppatchesng_extracted_dir / rpf_paths_cfg["mppatches_rpf_relative"],
        "mppatchesng_dlc_rpf_file": rpf_paths_cfg["mppatches_modded_rpf"],
        "target_dlc_rpf_path": rpf_paths_cfg["mppatches_game_rpf"],
        "patchday_specs": patchday_specs,
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

    audit_report = ped_damage_helper.inspect_rpf7_archive_limits(rpf_file_path)
    if audit_report["resource_overflows"]:
        raise ValueError(
            f"RPF7 16 MiB resource overflow (f_size=0xFFFFFF) in {rpf_file_path.name}: "
            f"{audit_report['resource_overflows'][:5]}"
        )
    if audit_report["offset_overflows"] or not audit_report["archive_size_ok"]:
        raise ValueError(
            f"RPF7 4.00 GiB sector offset overflow in {rpf_file_path.name}: "
            f"size={audit_report['total_bytes']:,}, overflows={audit_report['offset_overflows'][:5]}"
        )
    if audit_report["compressed_binaries"]:
        raise ValueError(
            f"RPF7 uncompressed-binary TOC check failed in {rpf_file_path.name}: "
            f"{audit_report['compressed_binaries'][:5]}"
        )

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

    temp_dest_path = destination_file_path.with_name(
        f".{destination_file_path.name}.tmp.{os.getpid()}"
    )
    try:
        if total_file_bytes == 0:
            shutil.copy2(str(source_file_path), str(temp_dest_path))
            os.replace(temp_dest_path, destination_file_path)
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
            with open(temp_dest_path, "wb") as dest_handle:
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

        shutil.copystat(str(source_file_path), str(temp_dest_path))
        os.replace(temp_dest_path, destination_file_path)
    except Exception:
        if temp_dest_path.exists():
            try:
                temp_dest_path.unlink()
            except OSError:
                pass
        raise
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
    process_timeout_sec = 600.0
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

    try:
        while process_handle.poll() is None:
            current_time = time.time()
            elapsed_seconds = current_time - start_timestamp
            if elapsed_seconds > process_timeout_sec:
                raise TimeoutError(
                    f"{task_description} exceeded timeout of {process_timeout_sec:.0f}s"
                )
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
    finally:
        if process_handle.poll() is None:
            try:
                process_handle.terminate()
                process_handle.wait(timeout=3.0)
            except Exception:
                try:
                    process_handle.kill()
                    process_handle.wait(timeout=3.0)
                except Exception:
                    pass
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
    """Validate input limits, build `OPEN` RPF7 via `rage` or streaming I/O, and audit TOC."""
    ped_damage_helper.assert_directory_rpf7_resources_valid(source_directory_path)
    if output_rpf_path.exists():
        output_rpf_path.unlink()
    input_total_bytes = compute_directory_total_bytes(source_directory_path)
    if input_total_bytes >= RPF7_STREAMING_THRESHOLD_BYTES:
        npc_registry_helper.build_rpf7_open_streaming(
            output_rpf_path, source_directory_path, task_description
        )
        return
    try:
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
    except subprocess.CalledProcessError:
        print(
            f"[RPF7] rage create failed on {output_rpf_path.name}; retrying via low-memory streaming builder...",
            flush=True,
        )
        if output_rpf_path.exists():
            output_rpf_path.unlink()
        npc_registry_helper.build_rpf7_open_streaming(
            output_rpf_path, source_directory_path, task_description
        )


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

    patchday_specs = list(paths_map["patchday_specs"])

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

    active_patchday_specs = [
        pack_spec
        for pack_spec in patchday_specs
        if Path(pack_spec["dlc_extracted_dir"]).exists()
        and Path(pack_spec["models_dir"]).exists()
    ]
    has_streamedpedprops_staging = streamedpedprops_extracted_dir.is_dir()

    total_pipeline_stages = (
        7
        + (3 * len(active_patchday_specs))
        + (1 if has_streamedpedprops_staging else 0)
    )
    stage_tracker = PipelineProgressTracker(total_pipeline_stages)

    try:
        # 0. Refresh registered NPC staging patches before shared archives (patchday3ng / x64v) repack
        pre_npc_map = npc_registry_helper.load_npc_registry(
            project_paths.get_project_root()
        ).get("npcs", {})
        for npc_ped_name, npc_entry in sorted(pre_npc_map.items()):
            npc_info = npc_registry_helper.get_npc_staging_paths(
                npc_ped_name, npc_entry["location"]
            )
            if (
                Path(npc_info["package_dir"]).is_dir()
                and Path(npc_info["inner_extracted_dir"]).is_dir()
            ):
                npc_registry_helper.apply_npc_slot_replacement(
                    npc_ped_name, npc_entry, staging_info=npc_info
                )

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

        # 3B. Repack and deploy patchday3ng / patchday4ng when present in staging
        for pack_spec in active_patchday_specs:
            pack_name = str(pack_spec["name"])
            pack_dlc_dir = Path(pack_spec["dlc_extracted_dir"])
            pack_inner_rpf = Path(pack_spec["inner_rpf"])
            pack_models_dir = Path(pack_spec["models_dir"])
            pack_dlc_rpf = Path(pack_spec["dlc_rpf_file"])
            pack_target_dlc = Path(pack_spec["target_dlc_path"])

            stage_title = project_i18n.translate(
                "repack.stage_repacking", name=f"{pack_name}.rpf"
            )
            stage_tracker.begin_stage(stage_title)
            repack_single_rpf_stage(
                pack_inner_rpf,
                pack_models_dir,
                stage_title,
                rage_cli_tool,
            )

            stage_title = project_i18n.translate(
                "repack.stage_repacking", name=f"{pack_name} dlc.rpf"
            )
            stage_tracker.begin_stage(stage_title)
            repack_single_rpf_stage(
                pack_dlc_rpf,
                pack_dlc_dir,
                stage_title,
                rage_cli_tool,
            )

            stage_tracker.begin_stage(
                project_i18n.translate(
                    "repack.stage_installing", name=f"{pack_name}/dlc.rpf"
                )
            )
            copy_file_with_progress(
                pack_dlc_rpf,
                pack_target_dlc,
                f"{pack_name}/dlc.rpf",
            )

        # 4. Repack streamedpeds_players.rpf (compact secondary YTD variants if x64v nears 4 GiB)
        ensure_x64v_streamed_budget(
            x64v_extracted_dir,
            streamedpeds_extracted_dir,
            rage_cli_tool,
        )
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
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120.0,
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
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120.0,
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

        are_patchdays_valid = True
        for pack_spec in active_patchday_specs:
            pack_target_dlc = Path(pack_spec["target_dlc_path"])
            if not pack_target_dlc.is_file():
                continue
            with open(pack_target_dlc, "rb") as pack_file_handle:
                pack_file_handle.seek(12)
                pack_flag = pack_file_handle.read(4)
            pack_list_output = subprocess.run(
                [rage_cli_tool, "list", "-d", str(pack_target_dlc)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=120.0,
                check=True,
            ).stdout
            pack_compressed_entries = [
                line_item
                for line_item in pack_list_output.splitlines()
                if "Compressed:" in line_item and "Compressed: 0" not in line_item
            ]
            if len(pack_compressed_entries) != 0 or pack_flag != b"OPEN":
                are_patchdays_valid = False

        is_dlc_valid = (
            len(dlc_compressed_entries) == 0 and dlc_encryption_flag == b"OPEN"
        )
        is_x64v_valid = (
            len(x64v_compressed_entries) == 0 and x64v_encryption_flag == b"OPEN"
        )

        rpf_limit_checks_ok = True
        archives_to_audit = [
            target_dlc_rpf_path,
            mppatches_rpf_file,
            target_x64v_rpf_path,
            streamedpeds_rpf_file,
        ]
        if has_streamedpedprops_staging:
            archives_to_audit.append(streamedpedprops_rpf_file)
        for pack_spec in active_patchday_specs:
            pack_target_dlc = Path(pack_spec["target_dlc_path"])
            pack_inner_rpf = Path(pack_spec["inner_rpf"])
            if pack_target_dlc.is_file():
                archives_to_audit.extend([pack_target_dlc, pack_inner_rpf])

        npc_registry_map = npc_registry_helper.load_npc_registry(
            project_paths.get_project_root()
        ).get("npcs", {})
        for npc_ped_name, npc_entry in sorted(npc_registry_map.items()):
            print(f"[NPC Deploy] Repacking & deploying registered NPC '{npc_ped_name}'...", flush=True)
            deployed_npc_rpfs = npc_registry_helper.repack_and_deploy_npc_entry(
                npc_ped_name,
                npc_entry,
                skip_shared_archives=True,
            )
            archives_to_audit.extend(deployed_npc_rpfs)

        for audit_archive in archives_to_audit:
            if audit_archive.is_file():
                limit_report = ped_damage_helper.inspect_rpf7_archive_limits(audit_archive)
                if not limit_report["ok"]:
                    rpf_limit_checks_ok = False
                    print(
                        f"    [RPF7 LIMIT FAIL] {audit_archive.name}: {limit_report}",
                        flush=True,
                    )

        _sync_vtoon_runtime_to_game(project_paths.get_project_root(), project_paths.get_gtav_root_dir())

        if is_dlc_valid and is_x64v_valid and are_patchdays_valid and rpf_limit_checks_ok:
            stage_tracker.finish_pipeline()
            print(project_i18n.translate("repack.verify_passed"))
        else:
            print(project_i18n.translate("repack.verify_warn"))
            sys.exit(1)

    except Exception as general_error:
        print(project_i18n.translate("repack.fatal_error", error=general_error))
        sys.exit(1)


ASI_LOADER_LATEST_API_URL = (
    "https://api.github.com/repos/ThirteenAG/Ultimate-ASI-Loader/releases/latest"
)
ASI_LOADER_FALLBACK_URL = (
    "https://github.com/ThirteenAG/Ultimate-ASI-Loader/releases/download/"
    "v10.0.4/Ultimate-ASI-Loader-NoPDB_x64.zip"
)
SCRIPTHOOKV_DOWNLOAD_URL = "https://www.dev-c.com/gtav/scripthookv/"
MODS_READER_CANDIDATES = ("OpenIV.asi", "RageOpenV.asi")


def inspect_gtav_runtime_prerequisites(
    gtav_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Inspect GTA V root for required ASI loader, our .asi/.ini plugins, and 3rd-party loaders."""
    resolved_gtav = gtav_root or project_paths.get_gtav_root_dir()
    is_valid_dir = bool(resolved_gtav and resolved_gtav.is_dir())
    mods_loader_found = ""
    if is_valid_dir:
        for candidate_name in MODS_READER_CANDIDATES:
            if (resolved_gtav / candidate_name).is_file():
                mods_loader_found = candidate_name
                break
    return {
        "gtav_root": str(resolved_gtav or ""),
        "gtav_root_exists": is_valid_dir,
        "asi_loader_ok": is_valid_dir and (resolved_gtav / "dinput8.dll").is_file(),
        "scripthookv_ok": is_valid_dir and (resolved_gtav / "ScriptHookV.dll").is_file(),
        "mods_loader_name": mods_loader_found,
        "mods_loader_ok": bool(mods_loader_found),
        "physbones_asi_ok": is_valid_dir and (resolved_gtav / "GTAVPhysBones.asi").is_file(),
        "physbones_ini_ok": is_valid_dir and (resolved_gtav / "GTAVPhysBones.ini").is_file(),
        "vtoon_asi_ok": is_valid_dir and (resolved_gtav / "GTAVVToon.asi").is_file(),
        "vtoon_ini_ok": is_valid_dir and (resolved_gtav / "GTAVVToon.ini").is_file(),
        "vtoon_profiles_ok": is_valid_dir and (resolved_gtav / "vtoon_profiles").is_dir(),
    }


def download_and_install_asi_loader(
    gtav_root: Path, *, download_url: Optional[str] = None
) -> Optional[Path]:
    """Download open-source Ultimate ASI Loader (x64 dinput8.dll) into GTA V root when absent."""
    if not gtav_root or not gtav_root.is_dir():
        return None
    dest_dll = gtav_root / "dinput8.dll"
    if dest_dll.is_file() and dest_dll.stat().st_size > 50000:
        print(project_i18n.translate("repack.asi_loader_ready", path=dest_dll), flush=True)
        return dest_dll

    print(project_i18n.translate("repack.asi_loader_downloading", dest=dest_dll), flush=True)
    resolved_url = download_url
    if not resolved_url:
        try:
            api_req = urllib.request.Request(
                ASI_LOADER_LATEST_API_URL,
                headers={"User-Agent": "VRCAvatar2GTAV/1.0"},
            )
            with urllib.request.urlopen(api_req, timeout=20.0) as api_resp:
                release_data = json.loads(api_resp.read().decode("utf-8"))
            assets = release_data.get("assets") or []
            for preferred_hint in ("nopdb_x64.zip", "_x64.zip"):
                for asset_item in assets:
                    asset_name = str(asset_item.get("name", "")).lower()
                    if asset_name.endswith(preferred_hint):
                        resolved_url = str(asset_item.get("browser_download_url", ""))
                        break
                if resolved_url:
                    break
        except Exception:
            resolved_url = None

    resolved_url = resolved_url or ASI_LOADER_FALLBACK_URL
    dl_req = urllib.request.Request(
        resolved_url, headers={"User-Agent": "VRCAvatar2GTAV/1.0"}
    )
    with urllib.request.urlopen(dl_req, timeout=60.0) as zip_resp:
        archive_bytes = zip_resp.read()

    with zipfile.ZipFile(io_stream.BytesIO(archive_bytes)) as zip_archive:
        dll_members = [
            member_info
            for member_info in zip_archive.infolist()
            if not member_info.is_dir() and member_info.filename.lower().endswith(".dll")
        ]
        if not dll_members:
            raise RuntimeError("Ultimate ASI Loader archive did not contain any .dll binary.")
        chosen_member = next(
            (item for item in dll_members if Path(item.filename).name.lower() == "dinput8.dll"),
            dll_members[0],
        )
        dest_dll.write_bytes(zip_archive.read(chosen_member.filename))

    print(project_i18n.translate("repack.asi_loader_ready", path=dest_dll), flush=True)
    return dest_dll


def sync_gtav_runtime_mods(
    project_root: Path,
    gtav_root: Path,
    *,
    overwrite_inis: bool = False,
) -> Dict[str, Any]:
    """Deploy GTAVPhysBones.asi/.ini, GTAVVToon.asi/.ini, and vtoon_profiles/ into GTA V root."""
    installed_files: List[str] = []
    if not gtav_root or not gtav_root.is_dir():
        return {"copied": installed_files}

    for pkg_name in (
        "2_Michael_Shinano_EternalReunion",
        "1_Franklin_Shinano_Casual",
        "3_Trevor_Miltina_Maid",
    ):
        pkg_dir = project_root / pkg_name / "5_rpf_package"
        if not pkg_dir.is_dir():
            continue

        for bin_name in ("GTAVVToon.asi", "GTAVPhysBones.asi"):
            src_bin = pkg_dir / bin_name
            dst_bin = gtav_root / bin_name
            if src_bin.is_file() and (
                not dst_bin.is_file()
                or _compute_file_sha256(src_bin) != _compute_file_sha256(dst_bin)
            ):
                shutil.copy2(src_bin, dst_bin)
                installed_files.append(bin_name)

        for ini_name in ("GTAVVToon.ini", "GTAVPhysBones.ini"):
            src_ini = pkg_dir / ini_name
            dst_ini = gtav_root / ini_name
            if src_ini.is_file() and (overwrite_inis or not dst_ini.is_file()):
                shutil.copy2(src_ini, dst_ini)
                installed_files.append(ini_name)

        prof_src = pkg_dir / "vtoon_profiles"
        if prof_src.is_dir():
            prof_dst = gtav_root / "vtoon_profiles"
            prof_dst.mkdir(parents=True, exist_ok=True)
            for prof_item in prof_src.iterdir():
                if prof_item.is_file():
                    target_prof = prof_dst / prof_item.name
                    if overwrite_inis or not target_prof.is_file():
                        shutil.copy2(prof_item, target_prof)
            if "vtoon_profiles/" not in installed_files:
                installed_files.append("vtoon_profiles/")

    if installed_files:
        print(
            project_i18n.translate(
                "repack.runtime_synced",
                dest=gtav_root,
                files=", ".join(installed_files),
            ),
            flush=True,
        )
    return {"copied": installed_files}


def print_gtav_runtime_status(gtav_root: Optional[Path] = None) -> Dict[str, Any]:
    """Print ready/missing status for GTA V root runtime DLLs and ASIs."""
    status = inspect_gtav_runtime_prerequisites(gtav_root)
    if not status["gtav_root_exists"]:
        return status

    gtav_path_str = status["gtav_root"]
    ready_items = [
        label
        for flag, label in (
            ("asi_loader_ok", "dinput8.dll"),
            ("physbones_asi_ok", "GTAVPhysBones.asi"),
            ("physbones_ini_ok", "GTAVPhysBones.ini"),
            ("vtoon_asi_ok", "GTAVVToon.asi"),
            ("vtoon_ini_ok", "GTAVVToon.ini"),
            ("scripthookv_ok", "ScriptHookV.dll"),
            ("mods_loader_ok", status["mods_loader_name"] or "OpenIV.asi"),
        )
        if status[flag]
    ]
    if ready_items:
        print(
            project_i18n.translate("manager.prereq_runtime_ok", items=", ".join(ready_items)),
            flush=True,
        )
    if not status["asi_loader_ok"]:
        print(project_i18n.translate("manager.prereq_asi_loader_missing", path=gtav_path_str), flush=True)
    if not status["scripthookv_ok"]:
        print(project_i18n.translate("manager.prereq_scripthookv_missing", path=gtav_path_str), flush=True)
    if not status["mods_loader_ok"]:
        print(project_i18n.translate("manager.prereq_mods_loader_missing", path=gtav_path_str), flush=True)
    return status


def _sync_vtoon_runtime_to_game(project_root: Path, gtav_root: Path) -> None:
    """Copy GTAVVToon/GTAVPhysBones ASIs, INIs, and profiles into GTA V root without clobbering live INIs."""
    sync_gtav_runtime_mods(project_root, gtav_root, overwrite_inis=False)


RPF7_STREAMING_THRESHOLD_BYTES = 850_000_000
SAFE_X64V_ARCHIVE_BYTES = 2_800_000_000
SAFE_X64V_FULL_SECONDARY_BYTES = 3_950_000_000
SECONDARY_YTD_MIN_COMPACT_BYTES = 480_000
TIER2_YTD_MIN_COMPACT_BYTES = 300_000
DUMMY_SLOT_YDD_MAX_BYTES = 2048
DUMMY_SLOT_YTD_MIN_BYTES = 8192
DUMMY_COMPONENT_PREFIXES = (
    "accs_",
    "berd_",
    "decl_",
    "feet_",
    "hair_",
    "hand_",
    "head_",
    "jbib_",
    "lowr_",
    "task_",
    "teef_",
)


def _directory_content_bytes(target_dir: Path) -> int:
    """Return total byte size of all files recursively under `target_dir`."""
    if not target_dir.is_dir():
        return 0
    total_bytes = 0
    for walk_root, dir_names, file_names in os.walk(target_dir):
        dir_names[:] = dir_names
        for file_name in file_names:
            try:
                total_bytes += (Path(walk_root) / file_name).stat().st_size
            except OSError:
                continue
    return total_bytes


def _compute_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest for `file_path`."""
    digest = hashlib.sha256()
    with open(file_path, "rb") as stream:
        while True:
            chunk = stream.read(1048576)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _resize_extracted_png_for_budget(
    img_path: Path,
    max_diffuse_px: int,
    max_normal_px: int,
) -> None:
    """Resize extracted texture PNG according to diffuse/normal/specular role."""
    import numpy as np_lib
    from PIL import Image

    resampling_enum = getattr(Image, "Resampling", Image)
    lanczos_filter = getattr(resampling_enum, "LANCZOS", Image.LANCZOS)
    stem_low = img_path.stem.lower()
    with Image.open(img_path) as raw_img:
        rgba_img = raw_img.convert("RGBA")
        arr_u8 = np_lib.array(rgba_img)

    if "spec" in stem_low:
        max_span = max(
            int(arr_u8[:, :, chan_idx].max()) - int(arr_u8[:, :, chan_idx].min())
            for chan_idx in range(3)
        )
        if max_span <= 2:
            mean_rgb = tuple(int(arr_u8[:, :, chan_idx].mean()) for chan_idx in range(3))
            Image.new("RGB", (64, 64), mean_rgb).save(img_path, format="PNG")
            return
        target_px = min(rgba_img.width, max(64, max_normal_px))
        rgba_img.resize((target_px, target_px), lanczos_filter).save(img_path, format="PNG")
        return

    if "normal" in stem_low or "nrm" in stem_low:
        delta_flat = np_lib.abs(arr_u8[:, :, :3].astype(int) - np_lib.array([128, 128, 255]))
        if int(delta_flat.max()) <= 3:
            Image.new("RGB", (64, 64), (128, 128, 255)).save(img_path, format="PNG")
            return
        target_px = min(rgba_img.width, max_normal_px)
        rgba_img.convert("RGB").resize((target_px, target_px), lanczos_filter).save(
            img_path, format="PNG"
        )
        return

    try:
        import vtoon_profile_helper
    except ImportError:
        from common_tools import vtoon_profile_helper

    detected_vtoon_id = vtoon_profile_helper.decode_vtoon_watermark_block(rgba_img)
    target_w = min(rgba_img.width, max_diffuse_px)
    target_h = min(rgba_img.height, max_diffuse_px)
    if target_w != rgba_img.width or target_h != rgba_img.height:
        rgba_img = rgba_img.resize((target_w, target_h), lanczos_filter)
        if detected_vtoon_id > 0 and target_w >= 16 and target_h >= 16:
            rgba_img = vtoon_profile_helper.stamp_vtoon_watermark_block(
                rgba_img, detected_vtoon_id
            )
        arr_u8 = np_lib.array(rgba_img)
    elif detected_vtoon_id > 0:
        rgba_img = vtoon_profile_helper.stamp_vtoon_watermark_block(rgba_img, detected_vtoon_id)
        arr_u8 = np_lib.array(rgba_img)
    alpha_min = int(arr_u8[:, :, 3].min())
    out_img = rgba_img.convert("RGB") if alpha_min >= 254 else rgba_img
    out_img.save(img_path, format="PNG")


def _build_compacted_ytd_via_rage(
    source_ytd: Path,
    dest_ytd: Path,
    *,
    max_diffuse_px: int,
    max_normal_px: int,
) -> Optional[Path]:
    """Extract textures from `source_ytd`, downscale into `dest_ytd`, and validate."""
    work_parent = dest_ytd.parent if dest_ytd.parent.is_dir() else source_ytd.parent
    with tempfile.TemporaryDirectory(prefix="vrc2gtav_ytd_cmp_", dir=str(work_parent)) as tmp_str:
        tmp_dir = Path(tmp_str)
        tex_dir = tmp_dir / "tex"
        tex_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            npc_registry_helper.build_safe_rage_cmd("textures", str(source_ytd), "-o", str(tex_dir)),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        png_files = sorted(tex_dir.glob("*.png"))
        if not png_files:
            return None
        for png_file in png_files:
            _resize_extracted_png_for_budget(png_file, max_diffuse_px, max_normal_px)
        subprocess.run(
            npc_registry_helper.build_safe_rage_cmd(
                "textures", "build", "-o", str(dest_ytd), *[str(item) for item in png_files]
            ),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
    ped_damage_helper.validate_rpf7_resource_file(dest_ytd)
    return dest_ytd


def _build_tiny_dummy_ytd_via_rage(dest_ytd: Path) -> Path:
    """Build a minimal 16x16 valid RSC7 `.ytd` for unused invisible dummy slots."""
    from PIL import Image

    work_parent = dest_ytd.parent
    with tempfile.TemporaryDirectory(prefix="vrc2gtav_ytd_dmy_", dir=str(work_parent)) as tmp_str:
        dummy_png = Path(tmp_str) / "vrc2gtav_dummy_blank.png"
        Image.new("RGB", (16, 16), (0, 0, 0)).save(dummy_png, format="PNG")
        subprocess.run(
            npc_registry_helper.build_safe_rage_cmd(
                "textures", "build", "-o", str(dest_ytd), str(dummy_png)
            ),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
    ped_damage_helper.validate_rpf7_resource_file(dest_ytd)
    return dest_ytd


def _is_secondary_uppr_ytd_candidate(
    file_name: str,
    *,
    include_000_non_a: bool,
) -> bool:
    """Return True for `uppr_diff_*.ytd` secondary outfit/color slots eligible for downscaling."""
    low_name = file_name.lower()
    if not (low_name.startswith("uppr_diff_") and low_name.endswith(".ytd")):
        return False
    if low_name.startswith("uppr_diff_000_"):
        return include_000_non_a and not low_name.startswith("uppr_diff_000_a_")
    return True


def _compact_protagonist_uppr_ytds(
    streamedpeds_extracted_dir: Path,
    *,
    max_diffuse_px: int,
    max_normal_px: int,
    min_size_bytes: int,
    include_000_non_a: bool,
    compact_builder: Any,
) -> int:
    """Replace oversized duplicate secondary `uppr_diff_*.ytd` files with compact variants."""
    replaced_count = 0
    with tempfile.TemporaryDirectory(
        prefix="vrc2gtav_x64v_cache_", dir=str(streamedpeds_extracted_dir)
    ) as cache_str:
        cache_dir = Path(cache_str)
        compact_by_hash: Dict[str, Optional[Path]] = {}
        for ped_dir in sorted(streamedpeds_extracted_dir.iterdir()):
            if not ped_dir.is_dir():
                continue
            candidates = sorted(
                item_path
                for item_path in ped_dir.iterdir()
                if item_path.is_file()
                and item_path.stat().st_size > min_size_bytes
                and _is_secondary_uppr_ytd_candidate(
                    item_path.name, include_000_non_a=include_000_non_a
                )
            )
            if not candidates:
                continue
            hash_groups: Dict[str, List[Path]] = {}
            for cand_file in candidates:
                file_hash = _compute_file_sha256(cand_file)
                hash_groups.setdefault(file_hash, []).append(cand_file)
            for src_hash, target_files in hash_groups.items():
                if src_hash not in compact_by_hash:
                    out_ytd = cache_dir / f"cmp_{src_hash[:12]}.ytd"
                    try:
                        compact_by_hash[src_hash] = compact_builder(
                            target_files[0],
                            out_ytd,
                            max_diffuse_px=max_diffuse_px,
                            max_normal_px=max_normal_px,
                        )
                    except Exception:
                        compact_by_hash[src_hash] = None
                built_ytd = compact_by_hash[src_hash]
                if built_ytd is None or not built_ytd.is_file():
                    continue
                built_size = built_ytd.stat().st_size
                for dst_file in target_files:
                    if built_size < dst_file.stat().st_size:
                        shutil.copyfile(built_ytd, dst_file)
                        replaced_count += 1
    return replaced_count


def _compact_unused_dummy_component_ytds(
    streamedpeds_extracted_dir: Path,
    dummy_builder: Any,
) -> int:
    """Compact vanilla `.ytd`s paired with 629-byte invisible dummy `.ydd` components."""
    replaced_count = 0
    with tempfile.TemporaryDirectory(
        prefix="vrc2gtav_x64v_dmy_", dir=str(streamedpeds_extracted_dir)
    ) as tmp_str:
        dummy_ytd = Path(tmp_str) / "dummy_slot.ytd"
        try:
            dummy_ytd = dummy_builder(dummy_ytd)
        except Exception:
            return 0
        if not dummy_ytd.is_file():
            return 0
        dummy_size = dummy_ytd.stat().st_size
        for ped_dir in sorted(streamedpeds_extracted_dir.iterdir()):
            if not ped_dir.is_dir():
                continue
            has_dummy_parts = any(
                part_file.is_file()
                and part_file.name.lower().startswith(DUMMY_COMPONENT_PREFIXES)
                and part_file.suffix.lower() == ".ydd"
                and part_file.stat().st_size <= DUMMY_SLOT_YDD_MAX_BYTES
                for part_file in ped_dir.iterdir()
            )
            if not has_dummy_parts:
                continue
            for item_path in sorted(ped_dir.iterdir()):
                low_name = item_path.name.lower()
                if (
                    item_path.is_file()
                    and low_name.endswith(".ytd")
                    and low_name.startswith(DUMMY_COMPONENT_PREFIXES)
                    and item_path.stat().st_size > max(DUMMY_SLOT_YTD_MIN_BYTES, dummy_size)
                ):
                    shutil.copyfile(dummy_ytd, item_path)
                    replaced_count += 1
    return replaced_count


def ensure_x64v_streamed_budget(
    x64v_extracted_dir: Path,
    streamedpeds_extracted_dir: Path,
    rage_cli_binary: str = "",
    *,
    safe_max_bytes: int = SAFE_X64V_ARCHIVE_BYTES,
    secondary_atlas_size: int = 0,
    compact_builder: Any = None,
    dummy_builder: Any = None,
) -> Dict[str, Any]:
    """
    Ensure `x64v_extracted` + `streamedpeds_players_extracted` fits well below
    RPF7's 4.00 GiB 23-bit sector limit before packing, progressively compacting
    secondary `uppr_diff_001+` `.ytd` duplicates while preserving primary slots.
    """
    if not x64v_extracted_dir.is_dir() or not streamedpeds_extracted_dir.is_dir():
        return {"compacted": False, "projected_bytes": 0, "replaced_files": 0}

    inner_rpf_in_x64v = x64v_extracted_dir / "models" / "cdimages" / "streamedpeds_players.rpf"
    existing_inner_bytes = inner_rpf_in_x64v.stat().st_size if inner_rpf_in_x64v.is_file() else 0
    other_x64v_bytes = max(0, _directory_content_bytes(x64v_extracted_dir) - existing_inner_bytes)
    streamed_bytes = _directory_content_bytes(streamedpeds_extracted_dir)
    projected_bytes = other_x64v_bytes + streamed_bytes

    resolved_compact = compact_builder or _build_compacted_ytd_via_rage
    resolved_dummy = dummy_builder or _build_tiny_dummy_ytd_via_rage
    total_replaced = 0

    if secondary_atlas_size in (256, 512, 1024):
        print(
            f"[RPF7 Budget] Applying user secondary outfit resolution "
            f"{secondary_atlas_size}px to uppr_diff_001+ slots...",
            flush=True,
        )
        total_replaced += _compact_protagonist_uppr_ytds(
            streamedpeds_extracted_dir,
            max_diffuse_px=secondary_atlas_size,
            max_normal_px=min(512, max(64, secondary_atlas_size // 2)),
            min_size_bytes=(
                TIER2_YTD_MIN_COMPACT_BYTES
                if secondary_atlas_size <= 512
                else SECONDARY_YTD_MIN_COMPACT_BYTES
            ),
            include_000_non_a=False,
            compact_builder=resolved_compact,
        )
        streamed_bytes = _directory_content_bytes(streamedpeds_extracted_dir)
        projected_bytes = other_x64v_bytes + streamed_bytes

    if secondary_atlas_size == 2048:
        if projected_bytes > safe_max_bytes:
            total_replaced += _compact_unused_dummy_component_ytds(
                streamedpeds_extracted_dir, dummy_builder=resolved_dummy
            )
            streamed_bytes = _directory_content_bytes(streamedpeds_extracted_dir)
            projected_bytes = other_x64v_bytes + streamed_bytes
        safe_max_bytes = max(int(safe_max_bytes), SAFE_X64V_FULL_SECONDARY_BYTES)

    if projected_bytes <= safe_max_bytes:
        return {
            "compacted": total_replaced > 0,
            "projected_bytes": projected_bytes,
            "replaced_files": total_replaced,
            "rage_cli": rage_cli_binary,
        }

    print(
        f"[RPF7 Budget] Projected x64v.rpf is {projected_bytes / (1024.0 ** 3):.3f} GiB "
        f"(> safe {safe_max_bytes / (1024.0 ** 3):.3f} GiB ceiling); "
        "compacting secondary protagonist slots while keeping uppr_000 full quality...",
        flush=True,
    )

    total_replaced += _compact_protagonist_uppr_ytds(
        streamedpeds_extracted_dir,
        max_diffuse_px=1024,
        max_normal_px=512,
        min_size_bytes=SECONDARY_YTD_MIN_COMPACT_BYTES,
        include_000_non_a=False,
        compact_builder=resolved_compact,
    )
    streamed_bytes = _directory_content_bytes(streamedpeds_extracted_dir)
    projected_bytes = other_x64v_bytes + streamed_bytes

    if projected_bytes > safe_max_bytes:
        total_replaced += _compact_unused_dummy_component_ytds(
            streamedpeds_extracted_dir,
            dummy_builder=resolved_dummy,
        )
        streamed_bytes = _directory_content_bytes(streamedpeds_extracted_dir)
        projected_bytes = other_x64v_bytes + streamed_bytes

    if projected_bytes > safe_max_bytes:
        total_replaced += _compact_protagonist_uppr_ytds(
            streamedpeds_extracted_dir,
            max_diffuse_px=512,
            max_normal_px=256,
            min_size_bytes=TIER2_YTD_MIN_COMPACT_BYTES,
            include_000_non_a=True,
            compact_builder=resolved_compact,
        )
        streamed_bytes = _directory_content_bytes(streamedpeds_extracted_dir)
        projected_bytes = other_x64v_bytes + streamed_bytes

    print(
        f"[RPF7 Budget] Compacted {total_replaced} secondary/dummy .ytd file(s): "
        f"streamedpeds_players={streamed_bytes / (1024.0 ** 3):.3f} GiB, "
        f"projected x64v.rpf={projected_bytes / (1024.0 ** 3):.3f} GiB.",
        flush=True,
    )
    return {
        "compacted": total_replaced > 0,
        "projected_bytes": projected_bytes,
        "replaced_files": total_replaced,
        "rage_cli": rage_cli_binary,
    }


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
