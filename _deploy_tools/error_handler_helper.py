#!/usr/bin/env python3
"""
error_handler_helper.py
=======================
Centralized exception hierarchy, structured try/except guards, subprocess safety
wrappers (DEVNULL + timeouts + orphan cleanup), atomic file writes, and
concise vs `--verbose` timestamped log routing for vrc2gtav.
"""

from contextlib import contextmanager
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple, Union


class Vrc2GtavError(RuntimeError):
    """Base structured pipeline error carrying stage, avatar, and remediation hints."""

    def __init__(
        self,
        message: str,
        *,
        stage: str = "pipeline",
        avatar: str = "",
        file_path: str = "",
        hint: str = "",
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = str(message)
        self.stage = str(stage or "pipeline")
        self.avatar = str(avatar or "")
        self.file_path = str(file_path or "")
        self.hint = str(hint or "")
        self.cause = cause


class AssetDownloadError(Vrc2GtavError):
    """Raised when downloading Blender, Sollumz, or external assets fails."""


class ArchiveExtractionError(Vrc2GtavError):
    """Raised when reading or extracting .zip / .unitypackage archives fails."""


class UnityProjectError(Vrc2GtavError):
    """Raised when scanning or parsing Unity scenes/prefabs encounters errors."""


class ModularAvatarBakeError(Vrc2GtavError):
    """Raised during Modular Avatar NDMF-style hierarchy/component baking."""


class BlenderBuildError(Vrc2GtavError):
    """Raised when Blender asset compilation fails or returns non-zero status."""


class SubprocessExecutionError(Vrc2GtavError):
    """Raised when a child process fails or exceeds its configured timeout."""


def sanitize_log_token(raw_token: str, fallback: str = "general") -> str:
    """Sanitize an avatar or stage name for safe log filenames."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(raw_token or "").strip()).strip("._-")
    return cleaned or fallback


def build_timestamped_log_path(
    project_root: Union[str, Path],
    avatar_name: str = "general",
    stage_name: str = "run",
    now_dt: Optional[datetime] = None,
) -> Path:
    """Construct `<project_root>/logs/<YYYYMMDD_HHMMSS>_<avatar>_<stage>.log`."""
    timestamp_obj = now_dt or datetime.now()
    date_slug = timestamp_obj.strftime("%Y%m%d_%H%M%S")
    avatar_slug = sanitize_log_token(avatar_name, fallback="avatar")
    stage_slug = sanitize_log_token(stage_name, fallback="run")
    logs_dir = Path(project_root) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / f"{date_slug}_{avatar_slug}_{stage_slug}.log"


class PipelineLogger:
    """
    Concise screen reporter by default (`verbose=False`) with optional timestamped
    detailed console + file logging (`verbose=True`).
    """

    def __init__(
        self,
        verbose: bool = False,
        log_file_path: Optional[Union[str, Path]] = None,
        avatar_name: str = "general",
        stage_name: str = "pipeline",
        project_root: Optional[Union[str, Path]] = None,
    ) -> None:
        self.verbose = bool(verbose)
        self.avatar_name = str(avatar_name or "general")
        self.stage_name = str(stage_name or "pipeline")
        self.log_path: Optional[Path] = None
        if log_file_path is not None:
            resolved_log = Path(log_file_path)
            resolved_log.parent.mkdir(parents=True, exist_ok=True)
            self.log_path = resolved_log
        elif self.verbose and project_root is not None:
            self.log_path = build_timestamped_log_path(
                project_root,
                avatar_name=self.avatar_name,
                stage_name=self.stage_name,
            )

        if self.log_path is not None:
            header_line = (
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"[START] avatar={self.avatar_name} stage={self.stage_name} "
                f"verbose={self.verbose}\n"
            )
            try:
                with self.log_path.open("a", encoding="utf-8") as log_handle:
                    log_handle.write(header_line)
            except OSError:
                pass

    def _append_log_file(self, level_tag: str, text_msg: str) -> None:
        if self.log_path is None:
            return
        stamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line_out = f"[{stamp_str}] [{level_tag}] [{self.avatar_name}] {text_msg}\n"
        try:
            with self.log_path.open("a", encoding="utf-8") as log_handle:
                log_handle.write(line_out)
        except OSError:
            pass

    def info(self, message: str, *, always: bool = False) -> None:
        """Print concise status on screen (`always=True` or `verbose`) and record in log."""
        self._append_log_file("INFO", message)
        if always or self.verbose:
            print(message, flush=True)

    def debug(self, message: str) -> None:
        """Emit verbose-only diagnostic line to screen and timestamped log file."""
        self._append_log_file("DEBUG", message)
        if self.verbose:
            stamp_str = datetime.now().strftime("%H:%M:%S")
            print(f"[{stamp_str}] {message}", flush=True)

    def warning(self, message: str) -> None:
        """Print warning on screen and write timestamped entry to log."""
        self._append_log_file("WARN", message)
        formatted = message if message.startswith("[WARNING]") else f"[WARNING] {message}"
        print(formatted, flush=True)

    def error(self, message: str) -> None:
        """Print error message on stderr/stdout and record timestamped entry to log."""
        self._append_log_file("ERROR", message)
        formatted = message if message.startswith("[ERROR]") else f"[ERROR] {message}"
        print(formatted, file=sys.stderr, flush=True)


def get_active_logger_from_env(
    verbose_override: Optional[bool] = None,
    avatar_name: str = "general",
    stage_name: str = "pipeline",
    project_root: Optional[Union[str, Path]] = None,
) -> PipelineLogger:
    """Create a PipelineLogger respecting `--verbose` or `VRC2GTAV_VERBOSE` / `VRC2GTAV_LOG_FILE`."""
    env_verbose = os.environ.get("VRC2GTAV_VERBOSE", "").strip().lower() in ("1", "true", "yes")
    verbose_enabled = env_verbose if verbose_override is None else bool(verbose_override)
    env_log = os.environ.get("VRC2GTAV_LOG_FILE", "").strip()
    log_path_val = Path(env_log) if env_log else None
    return PipelineLogger(
        verbose=verbose_enabled,
        log_file_path=log_path_val,
        avatar_name=avatar_name,
        stage_name=stage_name,
        project_root=project_root,
    )


def format_exception_report(
    exc: BaseException,
    stage_name: str = "pipeline",
    avatar_name: str = "",
    file_path: str = "",
) -> str:
    """Format a structured, readable diagnostic error message with optional cause/hint."""
    details = [f"stage={stage_name}"]
    if avatar_name:
        details.append(f"avatar={avatar_name}")
    if isinstance(exc, Vrc2GtavError):
        if exc.file_path and not file_path:
            file_path = exc.file_path
    if file_path:
        details.append(f"path={file_path}")
    header = f"[ERROR] ({', '.join(details)}) {type(exc).__name__}: {exc}"
    if isinstance(exc, Vrc2GtavError) and exc.hint:
        return f"{header}\n  Hint: {exc.hint}"
    return header


@contextmanager
def guarded_stage(
    stage_name: str,
    *,
    avatar_name: str = "",
    file_path: str = "",
    logger: Optional[PipelineLogger] = None,
    reraise: bool = True,
    error_cls: type = Vrc2GtavError,
) -> Iterator[None]:
    """
    Structured try/except stage wrapper logging full traceback to the verbose log file
    while presenting concise, contextual diagnostics on failure.
    """
    try:
        yield
    except Vrc2GtavError as known_err:
        report_text = format_exception_report(
            known_err,
            stage_name=known_err.stage or stage_name,
            avatar_name=known_err.avatar or avatar_name,
            file_path=known_err.file_path or file_path,
        )
        if logger is not None:
            logger.error(report_text)
            if logger.verbose:
                logger.debug(traceback.format_exc().rstrip())
        else:
            print(report_text, file=sys.stderr, flush=True)
        if reraise:
            raise
    except Exception as raw_err:
        report_text = format_exception_report(
            raw_err,
            stage_name=stage_name,
            avatar_name=avatar_name,
            file_path=file_path,
        )
        if logger is not None:
            logger.error(report_text)
            logger._append_log_file("TRACE", traceback.format_exc().rstrip())
            if logger.verbose:
                print(traceback.format_exc(), file=sys.stderr, flush=True)
        else:
            print(report_text, file=sys.stderr, flush=True)
        if reraise:
            raise error_cls(
                str(raw_err),
                stage=stage_name,
                avatar=avatar_name,
                file_path=file_path,
                cause=raw_err,
            ) from raw_err


def safe_call(
    func: Callable[..., Any],
    *args: Any,
    default_value: Any = None,
    stage_name: str = "operation",
    logger: Optional[PipelineLogger] = None,
    **kwargs: Any,
) -> Any:
    """Invoke a callable inside try/except, returning `default_value` if a non-fatal error occurs."""
    try:
        return func(*args, **kwargs)
    except Exception as call_err:
        warn_msg = f"{stage_name} failed: {type(call_err).__name__}: {call_err}"
        if logger is not None:
            logger.warning(warn_msg)
            logger._append_log_file("TRACE", traceback.format_exc().rstrip())
        else:
            print(f"[WARNING] {warn_msg}", flush=True)
        return default_value


def atomic_write_text(
    target_path: Union[str, Path],
    content_text: str,
    encoding: str = "utf-8",
) -> Path:
    """Atomically write text via sibling `.tmp` file + `os.replace`."""
    resolved = Path(target_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = resolved.with_name(f".{resolved.name}.{os.getpid()}.tmp")
    try:
        with tmp_path.open("w", encoding=encoding) as tmp_handle:
            tmp_handle.write(content_text)
            tmp_handle.flush()
            try:
                os.fsync(tmp_handle.fileno())
            except OSError:
                pass
        os.replace(tmp_path, resolved)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise
    return resolved


def atomic_copy_file(
    source_path: Union[str, Path],
    destination_path: Union[str, Path],
) -> Path:
    """Atomically copy a file through a temporary staging filename + `os.replace`."""
    src_obj = Path(source_path)
    dst_obj = Path(destination_path)
    dst_obj.parent.mkdir(parents=True, exist_ok=True)
    tmp_obj = dst_obj.with_name(f".{dst_obj.name}.{os.getpid()}.tmp")
    try:
        shutil.copy2(src_obj, tmp_obj)
        os.replace(tmp_obj, dst_obj)
    except Exception:
        try:
            if tmp_obj.exists():
                tmp_obj.unlink()
        except OSError:
            pass
        raise
    return dst_obj


def _terminate_process_cleanly(proc_handle: subprocess.Popen) -> None:
    """Terminate or kill a lingering child process so no zombie process remains."""
    try:
        if proc_handle.poll() is None:
            proc_handle.terminate()
            try:
                proc_handle.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc_handle.kill()
                proc_handle.wait(timeout=4)
    except OSError:
        pass


def run_subprocess_safe(
    command: Sequence[Union[str, Path]],
    *,
    logger: Optional[PipelineLogger] = None,
    stage_name: str = "subprocess",
    avatar_name: str = "",
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Dict[str, str]] = None,
    timeout_sec: Optional[float] = None,
    check: bool = True,
    stream_to_console: bool = True,
) -> Tuple[int, str]:
    """
    Execute a child process safely with `stdin=DEVNULL`, timeout protection, zombie cleanup,
    concise/verbose logging, and structured error reporting.
    """
    cmd_strs = [str(part) for part in command]
    merged_env = dict(os.environ if env is None else env)
    merged_env["PYTHONUNBUFFERED"] = "1"
    if logger is not None and logger.log_path is not None:
        merged_env["VRC2GTAV_LOG_FILE"] = str(logger.log_path)
        merged_env["VRC2GTAV_VERBOSE"] = "1" if logger.verbose else "0"

    if logger is not None:
        logger.debug(f"Running command: {' '.join(cmd_strs)}")

    collected_lines: List[str] = []
    proc_handle: Optional[subprocess.Popen] = None
    timed_out_flag = False
    watchdog_timer = None
    try:
        import threading
        import time

        proc_handle = subprocess.Popen(
            cmd_strs,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=str(cwd) if cwd is not None else None,
            env=merged_env,
        )
        assert proc_handle.stdout is not None

        if timeout_sec is not None and float(timeout_sec) > 0.0:
            def _on_timeout() -> None:
                nonlocal timed_out_flag
                timed_out_flag = True
                if proc_handle is not None:
                    _terminate_process_cleanly(proc_handle)

            watchdog_timer = threading.Timer(float(timeout_sec), _on_timeout)
            watchdog_timer.daemon = True
            watchdog_timer.start()

        for raw_line in proc_handle.stdout:
            line_clean = raw_line.rstrip("\r\n")
            collected_lines.append(line_clean)
            if logger is not None:
                logger._append_log_file("SUB", line_clean)
                if logger.verbose and stream_to_console:
                    print(f"  {line_clean}", flush=True)
                elif stream_to_console and any(
                    tok in line_clean for tok in ("[ERROR]", "[WARNING]", "[OK]", "[PASS]", "[FAIL]")
                ):
                    print(f"  {line_clean}", flush=True)
            elif stream_to_console:
                print(line_clean, flush=True)

            if timed_out_flag:
                break

        return_code = proc_handle.wait(timeout=5.0 if timed_out_flag else timeout_sec)
        if watchdog_timer is not None:
            watchdog_timer.cancel()

        if timed_out_flag:
            raise SubprocessExecutionError(
                f"Command timed out after {timeout_sec}s: {cmd_strs[0]}",
                stage=stage_name,
                avatar=avatar_name,
                hint="Increase timeout or inspect the verbose log file.",
            )

        combined_output = "\n".join(collected_lines)
        if check and return_code != 0:
            tail_excerpt = "\n".join(collected_lines[-15:])
            raise SubprocessExecutionError(
                f"Command exited with code {return_code}: {' '.join(cmd_strs[:4])}\n{tail_excerpt}",
                stage=stage_name,
                avatar=avatar_name,
            )
        return return_code, combined_output
    except SubprocessExecutionError:
        if watchdog_timer is not None:
            watchdog_timer.cancel()
        raise
    except (subprocess.TimeoutExpired, OSError, KeyboardInterrupt) as sub_err:
        if watchdog_timer is not None:
            watchdog_timer.cancel()
        if proc_handle is not None:
            _terminate_process_cleanly(proc_handle)
        raise SubprocessExecutionError(
            f"Subprocess failed ({type(sub_err).__name__}): {sub_err}",
            stage=stage_name,
            avatar=avatar_name,
            cause=sub_err,
        ) from sub_err
