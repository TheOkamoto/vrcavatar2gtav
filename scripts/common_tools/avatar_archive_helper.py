#!/usr/bin/env python3
"""
avatar_archive_helper.py
========================
Handles automatic portable Blender 4.0.2 + Sollumz installation, safe .zip / .unitypackage
extraction into isolated Unity project workspaces, multi-avatar Unity scene discovery,
and paginated (10 options per page + Next) interactive user selection menus.
"""

from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

COMMON_TOOLS_DIR = Path(__file__).resolve().parent
if str(COMMON_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_TOOLS_DIR))

import error_handler_helper as err_helper

try:
    import unity_scene_helper
except ImportError:
    unity_scene_helper = None

try:
    import unity_hair_helper
except ImportError:
    unity_hair_helper = None


BLENDER_REQUIRED_VERSION = "4.0.2"
BLENDER_REQUIRED_MINOR_PREFIX = "4.0"
BLENDER_WINDOWS_ZIP_URL = (
    "https://download.blender.org/release/Blender4.0/blender-4.0.2-windows-x64.zip"
)
BLENDER_LINUX_TAR_URL = (
    "https://download.blender.org/release/Blender4.0/blender-4.0.2-linux-x64.tar.xz"
)
SOLLUMZ_LATEST_API_URL = "https://api.github.com/repos/Sollumz/Sollumz/releases/latest"
SOLLUMZ_FALLBACK_ZIP_URL = (
    "https://github.com/Sollumz/Sollumz/releases/download/v2.9.0/sollumz.zip"
)
RAGE_CLI_LATEST_API_URL = "https://api.github.com/repos/VIRUXE/rage-cli/releases/latest"
RAGE_CLI_FALLBACK_TAG = "v0.29.0"

VRC_AVATAR_DESCRIPTOR_GUID = "661092b4961be7145bfbe56e1e62337b"
MA_COMPONENT_GUIDS: Set[str] = {
    "2df373bf91cf30b4bbd495e11cb1a2ec",  # MergeArmature
    "42581d8044b64899834d3d515ab3a144",  # BoneProxy
    "560fdafd46c74b2db6422fdf0e7f2363",  # MeshSettings
    "6fd7cab7d93b403280f2f9da978d8a4f",  # BlendshapeSync
    "7e949680c0864ee7b441d9b2c93b890b",  # ReplaceObject
    "a162bb8ec7e24a5abcf457887f1df3fa",  # ObjectToggle
    "2db441f589c3407bb6fb5f02ff8ab541",  # ShapeChanger
    "09a660aa9d4e47d992adcac5a05dd808",  # ScaleAdjuster
    "e41c5d0c41074360bc33887977722a4d",  # Activator
}

NON_AVATAR_UTILITY_NAMES: Set[str] = {
    "main camera",
    "directional light",
    "eventsystem",
    "event system",
    "gesturemanager",
    "nadena.dev.ndmf__activator",
    "vrcworld",
    "floor",
    "stage",
    "mirror",
    "reflection probe",
}

SKIP_PROJECT_SCAN_DIRS: Set[str] = {
    "library",
    "temp",
    "obj",
    "logs",
    "builds",
    "usersettings",
    ".git",
    "__pycache__",
    "node_modules",
    "packages",
}

DEFAULT_AVATAR_PAGE_SIZE = 10


def _decode_yaml_scalar(raw_text: str) -> str:
    """Decode YAML quotes and \\uXXXX unicode escape sequences from Unity fields."""
    if unity_scene_helper is not None and hasattr(unity_scene_helper, "decode_unity_name"):
        return unity_scene_helper.decode_unity_name(raw_text)
    cleaned = str(raw_text or "").strip()
    if len(cleaned) >= 2 and cleaned.startswith('"') and cleaned.endswith('"'):
        try:
            decoded_json = json.loads(cleaned)
            if isinstance(decoded_json, str):
                return decoded_json.strip()
        except Exception:
            cleaned = cleaned[1:-1]
    elif len(cleaned) >= 2 and cleaned.startswith("'") and cleaned.endswith("'"):
        cleaned = cleaned[1:-1].replace("''", "'")
    if "\\u" in cleaned or "\\U" in cleaned:
        cleaned = re.sub(r"\\u([0-9a-fA-F]{4})", lambda hex_match: chr(int(hex_match.group(1), 16)), cleaned)
        cleaned = re.sub(r"\\U([0-9a-fA-F]{8})", lambda hex_match: chr(int(hex_match.group(1), 16)), cleaned)
    return cleaned.strip()


def _detect_host_target_os() -> str:
    """Return 'windows' when running on Windows or WSL targeting Windows GTA V builds."""
    if os.name == "nt":
        return "windows"
    rel_lower = platform.uname().release.lower()
    if "microsoft" in rel_lower or "wsl" in rel_lower or Path("/mnt/c/Windows").is_dir():
        return "windows"
    return "linux"


def _download_file_with_retry(
    download_url: str,
    dest_file: Path,
    *,
    max_retries: int = 3,
    timeout_sec: float = 60.0,
    headers: Optional[Dict[str, str]] = None,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> Path:
    """Stream-download a remote file atomically to `dest_file` with retry and cleanup."""
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="download")
    dest_file = Path(dest_file)
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest_file.with_suffix(dest_file.suffix + ".part")

    req_headers = {"User-Agent": "vrc2gtav-setup/1.0"}
    if headers:
        req_headers.update(headers)

    last_error: Optional[Exception] = None
    for attempt_idx in range(1, max_retries + 1):
        try:
            active_logger.debug(
                f"Downloading {download_url} (attempt {attempt_idx}/{max_retries})..."
            )
            request_obj = urllib.request.Request(download_url, headers=req_headers)
            with urllib.request.urlopen(request_obj, timeout=timeout_sec) as response:
                total_header = response.headers.get("Content-Length")
                expected_bytes = int(total_header) if total_header and total_header.isdigit() else 0
                written_bytes = 0
                next_report_mb = 25
                with open(part_path, "wb") as out_stream:
                    while True:
                        chunk = response.read(262144)
                        if not chunk:
                            break
                        out_stream.write(chunk)
                        written_bytes += len(chunk)
                        written_mb = written_bytes // (1024 * 1024)
                        if written_mb >= next_report_mb:
                            pct_txt = (
                                f" ({(written_bytes * 100) // expected_bytes}%)"
                                if expected_bytes > 0
                                else ""
                            )
                            active_logger.debug(f"  Downloaded {written_mb} MB{pct_txt}...")
                            next_report_mb += 25
            os.replace(part_path, dest_file)
            return dest_file
        except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
            last_error = exc
            if part_path.exists():
                try:
                    part_path.unlink()
                except OSError:
                    pass
            active_logger.warning(
                f"Download attempt {attempt_idx} failed for {download_url}: {exc}"
            )
            if attempt_idx < max_retries:
                time.sleep(min(4.0, float(attempt_idx)))

    raise err_helper.AssetDownloadError(
        f"Failed to download {download_url} after {max_retries} attempts: {last_error}",
        stage="download",
        cause=last_error,
    )


def _fetch_latest_sollumz_url(
    logger: Optional[err_helper.PipelineLogger] = None,
) -> str:
    """Resolve the newest Sollumz addon .zip URL from GitHub Releases, falling back cleanly."""
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="sollumz_lookup")
    try:
        req = urllib.request.Request(
            SOLLUMZ_LATEST_API_URL,
            headers={
                "User-Agent": "vrc2gtav-setup/1.0",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            release_data = json.loads(resp.read().decode("utf-8", errors="replace"))
        for asset_item in release_data.get("assets", []):
            asset_name = str(asset_item.get("name", "")).lower()
            asset_url = str(asset_item.get("browser_download_url", ""))
            if asset_name.endswith(".zip") and "sollumz" in asset_name and asset_url:
                return asset_url
        zipball_url = str(release_data.get("zipball_url", ""))
        if zipball_url:
            return zipball_url
    except Exception as exc:
        active_logger.debug(f"GitHub API lookup fallback for Sollumz: {exc}")
    return SOLLUMZ_FALLBACK_ZIP_URL


def inspect_blender_installation(
    blender_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Inspect a Blender executable for exact version (4.0.2 / 4.0.x) and Sollumz availability.
    Never leaves hanging child processes.
    """
    result: Dict[str, Any] = {
        "exists": False,
        "executable": None,
        "version": "",
        "is_target_version": False,
        "is_4_0_series": False,
        "sollumz_installed": False,
        "addons_dir": None,
    }
    if not blender_path:
        return result

    exe_path = Path(blender_path)
    if not exe_path.is_file():
        return result

    result["exists"] = True
    result["executable"] = exe_path

    # Check addons directory directly from folder layout first (fast & side-effect free)
    blender_root = exe_path.parent
    addons_dir = blender_root / BLENDER_REQUIRED_MINOR_PREFIX / "scripts" / "addons"
    if not addons_dir.is_dir():
        candidate_40 = blender_root.parent / BLENDER_REQUIRED_MINOR_PREFIX / "scripts" / "addons"
        if candidate_40.is_dir():
            addons_dir = candidate_40
    result["addons_dir"] = addons_dir
    sollumz_init = addons_dir / "sollumz" / "__init__.py"
    if not sollumz_init.is_file():
        # Check user AppData / .config Blender addons too
        alt_user_init = (
            Path.home()
            / ".config"
            / "blender"
            / BLENDER_REQUIRED_MINOR_PREFIX
            / "scripts"
            / "addons"
            / "sollumz"
            / "__init__.py"
        )
        if alt_user_init.is_file():
            sollumz_init = alt_user_init
    result["sollumz_installed"] = sollumz_init.is_file()

    # Probe exact Blender version cleanly with short timeout & DEVNULL
    version_str = ""
    try:
        proc = subprocess.run(
            [str(exe_path), "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15.0,
            check=False,
        )
        ver_match = re.search(r"Blender\s+(\d+\.\d+\.\d+)", proc.stdout or "")
        if ver_match:
            version_str = ver_match.group(1)
    except (OSError, subprocess.TimeoutExpired):
        # Infer from path if Windows .exe invocation is skipped or unavailable
        path_match = re.search(r"blender-(\d+\.\d+\.\d+)", str(exe_path), re.IGNORECASE)
        if path_match:
            version_str = path_match.group(1)

    result["version"] = version_str
    result["is_target_version"] = version_str == BLENDER_REQUIRED_VERSION
    result["is_4_0_series"] = version_str.startswith(BLENDER_REQUIRED_MINOR_PREFIX + ".")
    return result


def install_sollumz_into_blender(
    blender_exe: Union[str, Path],
    *,
    archive_path: Optional[Union[str, Path]] = None,
    download_url: Optional[str] = None,
    tools_dir: Optional[Union[str, Path]] = None,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> Path:
    """Install the Sollumz add-on into Blender's `4.0/scripts/addons/sollumz` directory."""
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="sollumz_install")
    exe_path = Path(blender_exe)
    if not exe_path.is_file():
        raise err_helper.AssetDownloadError(
            f"Blender executable not found for Sollumz install: {exe_path}",
            stage="sollumz_install",
        )

    addons_dir = exe_path.parent / BLENDER_REQUIRED_MINOR_PREFIX / "scripts" / "addons"
    addons_dir.mkdir(parents=True, exist_ok=True)
    target_sollumz_dir = addons_dir / "sollumz"
    if (target_sollumz_dir / "__init__.py").is_file():
        return target_sollumz_dir

    work_cache = Path(tools_dir) if tools_dir else (exe_path.parent.parent / "_downloads")
    work_cache.mkdir(parents=True, exist_ok=True)

    zip_source: Path
    if archive_path is not None and Path(archive_path).is_file():
        zip_source = Path(archive_path)
    else:
        resolved_url = download_url or _fetch_latest_sollumz_url(logger=active_logger)
        zip_source = work_cache / "sollumz_addon.zip"
        active_logger.info(f"Downloading Sollumz addon from {resolved_url}...", always=True)
        _download_file_with_retry(resolved_url, zip_source, logger=active_logger)

    staging_dir = addons_dir / f".sollumz_staging_{os.getpid()}"
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
    try:
        safe_extract_zip(zip_source, staging_dir, logger=active_logger)
        sollumz_root: Optional[Path] = None
        for init_candidate in staging_dir.rglob("__init__.py"):
            try:
                header_text = init_candidate.read_text(encoding="utf-8", errors="ignore")[:2048]
            except OSError:
                continue
            if "Sollumz" in header_text or init_candidate.parent.name.lower() == "sollumz":
                sollumz_root = init_candidate.parent
                break
        if sollumz_root is None:
            raise err_helper.ArchiveExtractionError(
                f"Could not find Sollumz __init__.py inside {zip_source}",
                stage="sollumz_install",
            )
        if target_sollumz_dir.exists():
            shutil.rmtree(target_sollumz_dir)
        shutil.move(str(sollumz_root), str(target_sollumz_dir))
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    if not (target_sollumz_dir / "__init__.py").is_file():
        raise err_helper.AssetDownloadError(
            f"Sollumz installation verification failed under {target_sollumz_dir}",
            stage="sollumz_install",
        )
    active_logger.info(f"Sollumz installed at: {target_sollumz_dir}", always=True)
    return target_sollumz_dir


def download_and_install_blender(
    project_root: Union[str, Path],
    *,
    target_os: Optional[str] = None,
    download_url: Optional[str] = None,
    install_sollumz: bool = True,
    sollumz_url: Optional[str] = None,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> Path:
    """
    Download and extract portable Blender 4.0.2 (plus optional Sollumz) into
    `<project_root>/tools/blender-4.0.2-<platform>/`.
    """
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="blender_setup")
    resolved_os = (target_os or _detect_host_target_os()).strip().lower()
    tools_dir = err_helper.resolve_workspace_root(project_root) / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    if resolved_os == "windows":
        folder_name = f"blender-{BLENDER_REQUIRED_VERSION}-windows-x64"
        exe_name = "blender.exe"
        default_url = BLENDER_WINDOWS_ZIP_URL
        archive_filename = f"{folder_name}.zip"
    else:
        folder_name = f"blender-{BLENDER_REQUIRED_VERSION}-linux-x64"
        exe_name = "blender"
        default_url = BLENDER_LINUX_TAR_URL
        archive_filename = f"{folder_name}.tar.xz"

    install_dir = tools_dir / folder_name
    target_exe = install_dir / exe_name
    if not target_exe.is_file():
        archive_path = tools_dir / "_downloads" / archive_filename
        source_url = download_url or default_url
        active_logger.info(
            f"Blender {BLENDER_REQUIRED_VERSION} not found; downloading portable package from {source_url}...",
            always=True,
        )
        _download_file_with_retry(source_url, archive_path, timeout_sec=180.0, logger=active_logger)

        staging_dir = tools_dir / f".blender_staging_{os.getpid()}"
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        try:
            active_logger.info(f"Extracting Blender {BLENDER_REQUIRED_VERSION}...", always=True)
            if archive_path.suffix.lower() == ".zip":
                safe_extract_zip(archive_path, staging_dir, logger=active_logger)
            else:
                _safe_extract_tar(archive_path, staging_dir, logger=active_logger)

            found_exe: Optional[Path] = None
            for cand_exe in staging_dir.rglob(exe_name):
                if cand_exe.is_file():
                    found_exe = cand_exe
                    break
            if found_exe is None:
                raise err_helper.ArchiveExtractionError(
                    f"Extracted archive did not contain {exe_name}: {archive_path}",
                    stage="blender_setup",
                )
            extracted_root = found_exe.parent
            if install_dir.exists():
                shutil.rmtree(install_dir)
            shutil.move(str(extracted_root), str(install_dir))
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

    if not target_exe.is_file():
        raise err_helper.AssetDownloadError(
            f"Portable Blender binary missing after extraction: {target_exe}",
            stage="blender_setup",
        )

    if install_sollumz:
        install_sollumz_into_blender(
            target_exe,
            download_url=sollumz_url,
            tools_dir=tools_dir / "_downloads",
            logger=active_logger,
        )

    active_logger.info(f"Blender ready: {target_exe}", always=True)
    return target_exe


def download_and_install_rage(
    project_root: Union[str, Path],
    *,
    target_os: Optional[str] = None,
    download_url: Optional[str] = None,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> Path:
    """Download the latest `rage-cli` executable into `<project_root>/tools/`."""
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="rage_setup")
    resolved_os = (target_os or _detect_host_target_os()).strip().lower()
    tools_dir = err_helper.resolve_workspace_root(project_root) / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    is_win = resolved_os == "windows"
    exe_name = "rage.exe" if is_win else "rage"
    asset_hint = "rage-windows-x86_64.exe" if is_win else "rage-linux-x86_64"
    dest_path = tools_dir / exe_name
    if dest_path.is_file() and dest_path.stat().st_size > 100000:
        return dest_path

    resolved_url = download_url
    if not resolved_url:
        try:
            req = urllib.request.Request(
                RAGE_CLI_LATEST_API_URL,
                headers={"User-Agent": "vrc2gtav-setup/1.0", "Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=20.0) as resp:
                release_json = json.loads(resp.read().decode("utf-8"))
            for item in release_json.get("assets", []):
                if str(item.get("name", "")).lower() == asset_hint:
                    resolved_url = str(item.get("browser_download_url", ""))
                    break
        except Exception as exc:
            active_logger.debug(f"GitHub latest lookup for rage-cli fell back: {exc}")
    if not resolved_url:
        resolved_url = f"https://github.com/VIRUXE/rage-cli/releases/download/{RAGE_CLI_FALLBACK_TAG}/{asset_hint}"

    active_logger.info(f"Downloading rage-cli from {resolved_url}...", always=True)
    _download_file_with_retry(resolved_url, dest_path, timeout_sec=120.0, logger=active_logger)
    if not is_win:
        try:
            os.chmod(dest_path, 0o755)
        except OSError:
            pass
    active_logger.info(f"rage-cli ready: {dest_path}", always=True)
    return dest_path


def _safe_join_under(base_dir: Path, member_rel: str) -> Path:
    """Resolve `member_rel` safely beneath `base_dir`, blocking Zip-Slip traversal."""
    normalized_rel = member_rel.replace("\\", "/").lstrip("/")
    if not normalized_rel:
        return base_dir.resolve()
    parts = [part for part in normalized_rel.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise err_helper.ArchiveExtractionError(
            f"Blocked unsafe archive path traversal entry: {member_rel!r}",
            stage="archive_extract",
        )
    resolved_base = base_dir.resolve()
    resolved_target = (resolved_base / Path(*parts)).resolve()
    try:
        resolved_target.relative_to(resolved_base)
    except ValueError as exc:
        raise err_helper.ArchiveExtractionError(
            f"Archive entry escapes target root: {member_rel!r}",
            stage="archive_extract",
            cause=exc,
        )
    return resolved_target


def _safe_extract_tar(
    tar_path: Path,
    dest_dir: Path,
    *,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> List[Path]:
    """Safely extract a tar/tar.gz/tar.xz archive blocking path traversal."""
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="archive_extract")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    extracted_paths: List[Path] = []
    try:
        with tarfile.open(tar_path, "r:*") as tar_handle:
            for member in tar_handle.getmembers():
                if member.issym() or member.islnk():
                    active_logger.debug(f"Skipping tar symlink entry: {member.name}")
                    continue
                target_path = _safe_join_under(dest_dir, member.name)
                if member.isdir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                src_stream = tar_handle.extractfile(member)
                if src_stream is None:
                    continue
                with src_stream, open(target_path, "wb") as out_handle:
                    shutil.copyfileobj(src_stream, out_handle, length=262144)
                if member.mode & 0o111:
                    try:
                        os.chmod(target_path, member.mode & 0o777)
                    except OSError:
                        pass
                extracted_paths.append(target_path)
    except (tarfile.TarError, OSError) as exc:
        raise err_helper.ArchiveExtractionError(
            f"Failed extracting tar archive {tar_path}: {exc}",
            stage="archive_extract",
            cause=exc,
        )
    return extracted_paths


def safe_extract_zip(
    zip_path: Union[str, Path],
    dest_dir: Union[str, Path],
    *,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> List[Path]:
    """
    Safely extract a .zip archive into `dest_dir` with Zip-Slip path traversal checks
    and Shift-JIS/UTF-8 filename decoding fallback for Japanese asset packs.
    """
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="archive_extract")
    src_zip = Path(zip_path)
    dest_root = Path(dest_dir)
    if not src_zip.is_file():
        raise err_helper.ArchiveExtractionError(
            f"Zip archive not found: {src_zip}", stage="archive_extract"
        )
    dest_root.mkdir(parents=True, exist_ok=True)
    extracted: List[Path] = []

    try:
        with zipfile.ZipFile(src_zip, "r") as zip_handle:
            for info in zip_handle.infolist():
                raw_name = info.filename
                if not (info.flag_bits & 0x800):
                    try:
                        raw_bytes = raw_name.encode("cp437")
                        for codec_name in ("utf-8", "cp932"):
                            try:
                                raw_name = raw_bytes.decode(codec_name)
                                break
                            except UnicodeDecodeError:
                                continue
                    except UnicodeEncodeError:
                        pass

                if raw_name.endswith("/") or raw_name.endswith("\\"):
                    dir_path = _safe_join_under(dest_root, raw_name)
                    dir_path.mkdir(parents=True, exist_ok=True)
                    continue

                out_path = _safe_join_under(dest_root, raw_name)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with zip_handle.open(info, "r") as src_stream, open(out_path, "wb") as dst_stream:
                    shutil.copyfileobj(src_stream, dst_stream, length=262144)
                extracted.append(out_path)
    except (zipfile.BadZipFile, OSError) as exc:
        active_logger.debug(f"Zip extraction error on {src_zip}: {exc}")
        raise err_helper.ArchiveExtractionError(
            f"Failed extracting zip archive {src_zip}: {exc}",
            stage="archive_extract",
            cause=exc,
        )
    return extracted


def _synthesize_minimal_meta(guid_str: str, is_folder: bool = False) -> bytes:
    """Create a minimal valid Unity .meta file when a unitypackage entry omits asset.meta."""
    clean_guid = guid_str.strip().lower()
    folder_line = "folderAsset: yes\n" if is_folder else ""
    content = f"fileFormatVersion: 2\nguid: {clean_guid}\n{folder_line}"
    return content.encode("utf-8")


def extract_unitypackage(
    package_path: Union[str, Path],
    dest_project_dir: Union[str, Path],
    *,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> Dict[str, Any]:
    """
    Extract a Unity `.unitypackage` directly into `dest_project_dir/Assets/...` while
    preserving exact `.meta` GUIDs (needed for scene PrefabInstances, materials, and MA!).
    """
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="unitypackage")
    pkg_file = Path(package_path)
    project_dir = Path(dest_project_dir)
    if not pkg_file.is_file():
        raise err_helper.ArchiveExtractionError(
            f"Unitypackage not found: {pkg_file}", stage="unitypackage"
        )
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "Assets").mkdir(parents=True, exist_ok=True)
    proj_settings = project_dir / "ProjectSettings"
    proj_settings.mkdir(parents=True, exist_ok=True)
    ver_file = proj_settings / "ProjectVersion.txt"
    if not ver_file.is_file():
        err_helper.atomic_write_text(ver_file, "m_EditorVersion: 2022.3.22f1\n")

    pathnames_by_guid: Dict[str, str] = {}
    asset_members: Dict[str, tarfile.TarInfo] = {}
    meta_members: Dict[str, tarfile.TarInfo] = {}
    written_files = 0
    written_metas = 0

    try:
        with tarfile.open(pkg_file, "r:*") as tar_handle:
            for member in tar_handle.getmembers():
                if not member.isfile():
                    continue
                clean_name = member.name.strip("./")
                parts = clean_name.split("/")
                if len(parts) < 2:
                    continue
                guid_key = parts[0].strip().lower()
                item_kind = parts[1]
                if item_kind == "pathname":
                    stream = tar_handle.extractfile(member)
                    if stream is not None:
                        with stream:
                            raw_path = stream.read().decode("utf-8", errors="replace")
                        rel_asset_path = raw_path.splitlines()[0].strip() if raw_path else ""
                        if rel_asset_path:
                            pathnames_by_guid[guid_key] = rel_asset_path
                elif item_kind == "asset":
                    asset_members[guid_key] = member
                elif item_kind == "asset.meta":
                    meta_members[guid_key] = member

            for guid_key, rel_asset_path in pathnames_by_guid.items():
                if not rel_asset_path:
                    continue
                target_asset_path = _safe_join_under(project_dir, rel_asset_path)
                asset_member = asset_members.get(guid_key)
                if asset_member is not None:
                    target_asset_path.parent.mkdir(parents=True, exist_ok=True)
                    src_stream = tar_handle.extractfile(asset_member)
                    if src_stream is not None:
                        with src_stream, open(target_asset_path, "wb") as out_handle:
                            shutil.copyfileobj(src_stream, out_handle, length=262144)
                        written_files += 1
                    meta_path = Path(str(target_asset_path) + ".meta")
                    meta_member = meta_members.get(guid_key)
                    if meta_member is not None:
                        meta_stream = tar_handle.extractfile(meta_member)
                        if meta_stream is not None:
                            with meta_stream, open(meta_path, "wb") as meta_out:
                                shutil.copyfileobj(meta_stream, meta_out, length=65536)
                            written_metas += 1
                    elif not meta_path.is_file() and len(guid_key) == 32:
                        meta_path.write_bytes(_synthesize_minimal_meta(guid_key, is_folder=False))
                        written_metas += 1
                else:
                    # Directory entry in unitypackage
                    target_asset_path.mkdir(parents=True, exist_ok=True)
                    dir_meta_path = Path(str(target_asset_path) + ".meta")
                    meta_member = meta_members.get(guid_key)
                    if meta_member is not None:
                        meta_stream = tar_handle.extractfile(meta_member)
                        if meta_stream is not None:
                            with meta_stream, open(dir_meta_path, "wb") as meta_out:
                                shutil.copyfileobj(meta_stream, meta_out, length=65536)
                            written_metas += 1
    except (tarfile.TarError, OSError) as exc:
        raise err_helper.ArchiveExtractionError(
            f"Failed extracting unitypackage {pkg_file}: {exc}",
            stage="unitypackage",
            cause=exc,
        )

    if unity_hair_helper is not None and hasattr(unity_hair_helper, "clear_guid_cache"):
        unity_hair_helper.clear_guid_cache()

    active_logger.debug(
        f"Extracted unitypackage {pkg_file.name}: {written_files} assets, {written_metas} .meta files"
    )
    return {
        "project_dir": project_dir,
        "assets_dir": project_dir / "Assets",
        "files_extracted": written_files,
        "metas_extracted": written_metas,
    }


def _scan_project_files(assets_dir: Path) -> Dict[str, List[Path]]:
    """Collect `.unity`, `.fbx`, `.prefab`, `.anim`, and `.unitypackage` paths under Assets."""
    scenes: List[Path] = []
    fbx_files: List[Path] = []
    prefab_files: List[Path] = []
    anim_files: List[Path] = []
    packages: List[Path] = []

    if not assets_dir.is_dir():
        return {
            "scenes": scenes,
            "fbx_files": fbx_files,
            "prefab_files": prefab_files,
            "anim_files": anim_files,
            "packages": packages,
        }

    for cur_root, dir_names, file_names in os.walk(assets_dir):
        dir_names[:] = sorted(
            sub_dir
            for sub_dir in dir_names
            if sub_dir.lower() not in SKIP_PROJECT_SCAN_DIRS and not sub_dir.startswith(".")
        )
        for file_name in sorted(file_names):
            low_name = file_name.lower()
            full_path = Path(cur_root) / file_name
            if low_name.endswith(".unity"):
                scenes.append(full_path)
            elif low_name.endswith(".fbx"):
                fbx_files.append(full_path)
            elif low_name.endswith(".prefab"):
                prefab_files.append(full_path)
            elif low_name.endswith(".anim"):
                anim_files.append(full_path)
            elif low_name.endswith(".unitypackage"):
                packages.append(full_path)

    return {
        "scenes": scenes,
        "fbx_files": fbx_files,
        "prefab_files": prefab_files,
        "anim_files": anim_files,
        "packages": packages,
    }


def ingest_avatar_source(
    source_path: Union[str, Path],
    project_root: Union[str, Path],
    *,
    workspace_dir: Optional[Union[str, Path]] = None,
    force_reextract: bool = False,
    logger: Optional[err_helper.PipelineLogger] = None,
) -> Dict[str, Any]:
    """
    Resolve an arbitrary avatar source parameter into a normalized Unity project view:
      - `.zip` archive (extracts contents + any inner `.unitypackage` files into workspace)
      - `.unitypackage` archive (extracts into workspace)
      - existing Unity project folder (containing `Assets/`) or direct `Assets/` folder
      - direct `.unity` scene file (infers enclosing `Assets/` and project root)
    """
    active_logger = logger or err_helper.get_active_logger_from_env(stage_name="ingest_source")
    raw_src = Path(source_path)
    if not raw_src.exists():
        raise err_helper.UnityProjectError(
            f"Avatar source path does not exist: {raw_src}", stage="ingest_source"
        )

    resolved_src = raw_src.resolve()
    proj_root = Path(project_root)

    if resolved_src.is_dir():
        if (resolved_src / "Assets").is_dir():
            unity_project_root = resolved_src
            assets_root = resolved_src / "Assets"
        elif resolved_src.name.lower() == "assets":
            unity_project_root = resolved_src.parent
            assets_root = resolved_src
        else:
            unity_project_root = resolved_src
            assets_root = resolved_src
            nested_pkgs = list(resolved_src.glob("*.unitypackage"))
            if nested_pkgs and not (resolved_src / "Assets").is_dir():
                assets_root = resolved_src / "Assets"
                assets_root.mkdir(parents=True, exist_ok=True)
                for pkg_file in sorted(nested_pkgs):
                    extract_unitypackage(pkg_file, unity_project_root, logger=active_logger)
        scanned = _scan_project_files(assets_root)
        return {
            "source_kind": "directory",
            "unity_project_root": unity_project_root,
            "assets_root": assets_root,
            "extracted_root": None,
            "preferred_scene": scanned["scenes"][0] if scanned["scenes"] else None,
            **scanned,
        }

    suffix_low = resolved_src.suffix.lower()
    if suffix_low in (".unity", ".prefab"):
        assets_root = resolved_src.parent
        unity_project_root = resolved_src.parent.parent
        for parent_dir in resolved_src.parents:
            if parent_dir.name.lower() == "assets":
                assets_root = parent_dir
                unity_project_root = parent_dir.parent
                break
        # Scope subtree walk to avoid slow full-project scans on huge VRChat Unity projects
        scan_scope: Optional[Path] = None
        if resolved_src.parent != assets_root:
            rel_parts = resolved_src.relative_to(assets_root).parts
            if len(rel_parts) >= 2:
                scan_scope = assets_root / rel_parts[0]
        scanned = (
            _scan_project_files(scan_scope)
            if scan_scope is not None and scan_scope.is_dir()
            else {"scenes": [], "fbx_files": [], "prefab_files": [], "anim_files": []}
        )
        if suffix_low == ".unity":
            if resolved_src not in scanned["scenes"]:
                scanned["scenes"].insert(0, resolved_src)
            return {
                "source_kind": "unity_scene",
                "unity_project_root": unity_project_root,
                "assets_root": assets_root,
                "extracted_root": None,
                "preferred_scene": resolved_src,
                "preferred_prefab": None,
                **scanned,
            }
        if resolved_src not in scanned["prefab_files"]:
            scanned["prefab_files"].insert(0, resolved_src)
        return {
            "source_kind": "unity_prefab",
            "unity_project_root": unity_project_root,
            "assets_root": assets_root,
            "extracted_root": None,
            "preferred_scene": None,
            "preferred_prefab": resolved_src,
            **scanned,
        }

    if suffix_low not in (".zip", ".unitypackage"):
        raise err_helper.ArchiveExtractionError(
            f"Unsupported avatar archive format {resolved_src.suffix!r}; expected .zip, .unitypackage, .unity, .prefab, or Unity project directory.",
            stage="ingest_source",
        )

    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", resolved_src.stem).strip("_") or "avatar_pkg"
    work_root = err_helper.resolve_workspace_root(proj_root)
    target_workspace = (
        Path(workspace_dir)
        if workspace_dir is not None
        else (work_root / "imported_unity_projects" / safe_stem)
    )
    stamp_file = target_workspace / ".vrc2gtav_source.json"

    try:
        src_stat = resolved_src.stat()
        cur_sig = {
            "source": str(resolved_src),
            "size": int(src_stat.st_size),
            "mtime_ns": int(src_stat.st_mtime_ns),
        }
    except OSError as exc:
        raise err_helper.ArchiveExtractionError(
            f"Cannot stat archive {resolved_src}: {exc}", stage="ingest_source", cause=exc
        )

    cache_hit = False
    if not force_reextract and stamp_file.is_file() and (target_workspace / "Assets").is_dir():
        try:
            old_sig = json.loads(stamp_file.read_text(encoding="utf-8"))
            if (
                old_sig.get("size") == cur_sig["size"]
                and old_sig.get("mtime_ns") == cur_sig["mtime_ns"]
            ):
                cache_hit = True
        except Exception:
            cache_hit = False

    if not cache_hit:
        target_workspace.mkdir(parents=True, exist_ok=True)
        active_logger.info(
            f"Extracting {resolved_src.name} into workspace {target_workspace}...", always=True
        )
        if suffix_low == ".unitypackage":
            extract_unitypackage(resolved_src, target_workspace, logger=active_logger)
        else:
            zip_extract_dir = target_workspace / "_zip_contents"
            safe_extract_zip(resolved_src, zip_extract_dir, logger=active_logger)
            inner_packages = sorted(zip_extract_dir.rglob("*.unitypackage"))
            for pkg_item in inner_packages:
                active_logger.info(
                    f"Extracting bundled unitypackage: {pkg_item.name}...", always=True
                )
                extract_unitypackage(pkg_item, target_workspace, logger=active_logger)

            # Fallback if zip only contained raw FBX/textures/prefabs without .unitypackage
            assets_dir = target_workspace / "Assets"
            if not assets_dir.is_dir() or not any(assets_dir.iterdir()):
                raw_fallback_dir = assets_dir / safe_stem
                raw_fallback_dir.mkdir(parents=True, exist_ok=True)
                for src_item in zip_extract_dir.iterdir():
                    dst_item = raw_fallback_dir / src_item.name
                    if not dst_item.exists():
                        shutil.move(str(src_item), str(dst_item))
            else:
                # Copy loose FBXs/textures not duplicated by unitypackage into _ZipLooseFBX/
                loose_fbxs = list(zip_extract_dir.rglob("*.fbx"))
                existing_fbx_names = {item.name.lower() for item in _scan_project_files(assets_dir)["fbx_files"]}
                for loose_fbx in loose_fbxs:
                    if loose_fbx.name.lower() not in existing_fbx_names:
                        extra_dir = assets_dir / "_ZipLooseFBX"
                        extra_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(loose_fbx, extra_dir / loose_fbx.name)

        err_helper.atomic_write_text(stamp_file, json.dumps(cur_sig, indent=2))
        if unity_hair_helper is not None and hasattr(unity_hair_helper, "clear_guid_cache"):
            unity_hair_helper.clear_guid_cache()
    else:
        active_logger.debug(f"Reusing cached extracted workspace: {target_workspace}")

    assets_root = target_workspace / "Assets"
    scanned = _scan_project_files(assets_root)
    zip_dir = target_workspace / "_zip_contents"
    if zip_dir.is_dir():
        zip_fbxs = [
            item
            for item in sorted(zip_dir.rglob("*.fbx"))
            if item.name.lower() not in {fbx_item.name.lower() for fbx_item in scanned["fbx_files"]}
        ]
        scanned["fbx_files"].extend(zip_fbxs)

    return {
        "source_kind": suffix_low.lstrip("."),
        "unity_project_root": target_workspace,
        "assets_root": assets_root,
        "extracted_root": target_workspace,
        "preferred_scene": scanned["scenes"][0] if scanned["scenes"] else None,
        **scanned,
    }


def _collect_guid_stem_index(
    assets_root: Optional[Path],
    target_guids: Optional[Set[str]] = None,
    time_budget_sec: float = 2.0,
) -> Dict[str, str]:
    """Quickly map requested prefab/FBX asset GUIDs -> filename stem under `assets_root`."""
    guid_stems: Dict[str, str] = {}
    if not assets_root or not assets_root.is_dir():
        return guid_stems
    if target_guids is not None and not target_guids:
        return guid_stems
    remaining = {guid_str.lower() for guid_str in target_guids} if target_guids else None
    deadline = time.monotonic() + time_budget_sec if time_budget_sec > 0 else None

    for cur_root, dir_names, file_names in os.walk(assets_root):
        if deadline is not None and time.monotonic() > deadline:
            dir_names[:] = []
            break
        dir_names[:] = [
            sub_dir
            for sub_dir in dir_names
            if sub_dir.lower() not in SKIP_PROJECT_SCAN_DIRS and not sub_dir.startswith(".")
        ]
        for file_name in file_names:
            low_name = file_name.lower()
            if not low_name.endswith((".prefab.meta", ".fbx.meta")):
                continue
            meta_file = os.path.join(cur_root, file_name)
            try:
                with open(meta_file, "r", encoding="utf-8", errors="ignore") as handle:
                    for line_idx, line_text in enumerate(handle):
                        if line_text.startswith("guid:"):
                            guid_val = line_text.split(":", 1)[1].strip().lower()
                            if guid_val:
                                guid_stems[guid_val] = Path(file_name[:-5]).stem
                                if remaining is not None:
                                    remaining.discard(guid_val)
                            break
                        if line_idx > 6:
                            break
            except OSError:
                continue
            if remaining is not None and not remaining:
                return guid_stems
    return guid_stems


def discover_scene_avatars(
    scene_path: Union[str, Path],
    assets_root: Optional[Union[str, Path]] = None,
    *,
    include_non_avatar_roots: bool = False,
    sort_active_first: bool = True,
) -> List[Dict[str, Any]]:
    """
    Parse a `.unity` scene accurately (including Unity 2022 `SceneRoots`, stripped
    `PrefabInstance`s, unpacked hierarchies, Modular Avatar outfits, and unicode names)
    and return selectable scene avatar entries without `?` unknown placeholders.
    """
    resolved_scene = Path(scene_path)
    if not resolved_scene.is_file():
        return []

    resolved_assets: Optional[Path] = Path(assets_root) if assets_root else None
    if resolved_assets is None:
        for parent_dir in resolved_scene.parents:
            if parent_dir.name.lower() == "assets":
                resolved_assets = parent_dir
                break

    game_objects: Dict[str, Dict[str, Any]] = {}
    transforms: Dict[str, Dict[str, Any]] = {}
    stripped_transform_to_prefab: Dict[str, str] = {}
    prefab_instances: Dict[str, Dict[str, Any]] = {}
    scene_root_ids: List[str] = []
    animator_game_object_ids: Set[str] = set()
    skinned_mesh_game_object_ids: Set[str] = set()
    vrc_descriptor_game_object_ids: Set[str] = set()
    ma_game_object_ids: Set[str] = set()
    armature_game_object_ids: Set[str] = set()
    camera_or_light_game_object_ids: Set[str] = set()

    current_class = ""
    current_fid = ""
    current_stripped = False
    block_lines: List[str] = []

    def _flush_yaml_block() -> None:
        if not current_class or not current_fid:
            return
        body = "\n".join(block_lines)
        if current_class == "1":
            name_match = re.search(r"^\s*m_Name:\s*(.+)$", body, re.MULTILINE)
            active_match = re.search(r"^\s*m_IsActive:\s*(\d+)", body, re.MULTILINE)
            game_object_name = _decode_yaml_scalar(name_match.group(1)) if name_match else ""
            is_act = (int(active_match.group(1)) != 0) if active_match else True
            game_objects[current_fid] = {"name": game_object_name, "active": is_act}
            if game_object_name.strip().lower() == "armature":
                armature_game_object_ids.add(current_fid)
        elif current_class == "4":
            if current_stripped:
                prefab_instance_match = re.search(r"m_PrefabInstance:\s*\{fileID:\s*(-?\d+)", body)
                if prefab_instance_match:
                    stripped_transform_to_prefab[current_fid] = prefab_instance_match.group(1)
                return
            game_object_match = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", body)
            father_match = re.search(r"m_Father:\s*\{fileID:\s*(-?\d+)", body)
            child_fids: List[str] = []
            if "m_Children:" in body:
                child_chunk = body.split("m_Children:", 1)[1].split("m_Father:", 1)[0]
                child_fids = re.findall(r"-\s*\{fileID:\s*(-?\d+)", child_chunk)
            transforms[current_fid] = {
                "go": game_object_match.group(1) if game_object_match else "",
                "father": father_match.group(1) if father_match else "0",
                "children": child_fids,
            }
        elif current_class == "1001":
            parent_match = re.search(r"m_TransformParent:\s*\{fileID:\s*(-?\d+)", body)
            source_match = re.search(
                r"m_SourcePrefab:\s*\{fileID:\s*-?\d+,\s*guid:\s*([0-9a-fA-F]{32})",
                body,
            )
            src_guid = source_match.group(1).lower() if source_match else ""
            found_name = ""
            root_name_tid = ""
            active_by_tid: Dict[str, bool] = {}
            for entry_chunk in body.split("    - target:")[1:]:
                header_slice = entry_chunk[:450]
                if (
                    "propertyPath: m_Name" not in header_slice
                    and "propertyPath: m_IsActive" not in header_slice
                ):
                    continue
                target_match = re.search(
                    r"\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-fA-F]{32}))?", header_slice
                )
                prop_match = re.search(r"propertyPath:[ \t]*([^\r\n]+)", header_slice)
                value_match = re.search(r"value:[ \t]*([^\r\n]*)", header_slice)
                if not (target_match and prop_match and value_match):
                    continue
                prop_path = prop_match.group(1).strip()
                raw_val = _decode_yaml_scalar(value_match.group(1))
                tgt_fid = target_match.group(1)
                tgt_guid = (target_match.group(2) or "").lower()
                if prop_path == "m_Name" and raw_val:
                    is_src_match = bool(src_guid and tgt_guid == src_guid)
                    if not found_name or (is_src_match and not root_name_tid):
                        found_name = raw_val
                        root_name_tid = tgt_fid
                elif prop_path == "m_IsActive" and tgt_fid:
                    if not src_guid or not tgt_guid or tgt_guid == src_guid:
                        active_by_tid[tgt_fid] = raw_val != "0"

            prefab_instance_active: Optional[bool] = None
            if root_name_tid and root_name_tid in active_by_tid:
                prefab_instance_active = active_by_tid[root_name_tid]
            elif not root_name_tid and "100000" in active_by_tid:
                prefab_instance_active = active_by_tid["100000"]

            prefab_instances[current_fid] = {
                "parent": parent_match.group(1) if parent_match else "0",
                "source_guid": src_guid,
                "name": found_name,
                "active": True if prefab_instance_active is None else prefab_instance_active,
            }
        elif current_class == "95":
            game_object_match = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", body)
            if game_object_match:
                animator_game_object_ids.add(game_object_match.group(1))
        elif current_class == "137":
            game_object_match = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", body)
            if game_object_match:
                skinned_mesh_game_object_ids.add(game_object_match.group(1))
        elif current_class in ("20", "108"):
            game_object_match = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", body)
            if game_object_match:
                camera_or_light_game_object_ids.add(game_object_match.group(1))
        elif current_class == "114":
            game_object_match = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", body)
            script_match = re.search(r"m_Script:\s*\{[^}]*guid:\s*([0-9a-fA-F]{32})", body)
            if game_object_match:
                game_object_id = game_object_match.group(1)
                script_guid = script_match.group(1).lower() if script_match else ""
                if script_guid == VRC_AVATAR_DESCRIPTOR_GUID or (
                    "lipSync:" in body and "ViewPosition:" in body
                ):
                    vrc_descriptor_game_object_ids.add(game_object_id)
                elif script_guid in MA_COMPONENT_GUIDS:
                    ma_game_object_ids.add(game_object_id)
        elif current_class == "1660057539":
            scene_root_ids.extend(re.findall(r"fileID:\s*(-?\d+)", body))

    try:
        with open(resolved_scene, "r", encoding="utf-8", errors="ignore") as yaml_handle:
            for raw_line in yaml_handle:
                if raw_line.startswith("--- !u!"):
                    _flush_yaml_block()
                    header = raw_line[7:].strip()
                    current_stripped = header.endswith("stripped")
                    if current_stripped:
                        header = header[:-8].strip()
                    parts = header.split(" &", 1)
                    current_class = parts[0].strip() if parts else ""
                    current_fid = parts[1].strip() if len(parts) > 1 else ""
                    block_lines = []
                elif current_class:
                    block_lines.append(raw_line.rstrip("\r\n"))
            _flush_yaml_block()
    except OSError as exc:
        raise err_helper.UnityProjectError(
            f"Failed reading Unity scene {resolved_scene}: {exc}",
            stage="discover_avatars",
            cause=exc,
        )

    game_object_to_transform = {
        transform_info["go"]: transform_file_id for transform_file_id, transform_info in transforms.items() if transform_info.get("go")
    }
    unnamed_prefab_instance_guids: Set[str] = {
        str(prefab_instance_info.get("source_guid", "")).lower()
        for prefab_instance_info in prefab_instances.values()
        if prefab_instance_info.get("source_guid") and not str(prefab_instance_info.get("name", "")).strip()
    }
    guid_stems: Dict[str, str] = {}
    if unnamed_prefab_instance_guids and resolved_assets is not None:
        if unity_scene_helper is not None and hasattr(unity_scene_helper, "_collect_guid_paths_bounded"):
            search_dirs = unity_scene_helper._priority_search_dirs(
                resolved_scene, resolved_assets, [resolved_scene.stem]
            )
            found_map = unity_scene_helper._collect_guid_paths_bounded(
                unnamed_prefab_instance_guids, search_dirs, fallback_timeout_sec=2.0
            )
            guid_stems = {guid_lookup_key: path_v.stem for guid_lookup_key, path_v in found_map.items()}
        else:
            guid_stems = _collect_guid_stem_index(
                resolved_assets, target_guids=unnamed_prefab_instance_guids, time_budget_sec=2.0
            )

    active_prefab_count_by_transform: Dict[str, int] = {}
    for prefab_instance_info in prefab_instances.values():
        if prefab_instance_info.get("active", True):
            parent_fid = str(prefab_instance_info.get("parent", "0"))
            active_prefab_count_by_transform[parent_fid] = active_prefab_count_by_transform.get(parent_fid, 0) + 1

    def _collect_transform_subtree_stats(start_transform_file_id: str) -> Dict[str, Any]:
        seen: Set[str] = set()
        queue_ids = deque([start_transform_file_id])
        desc_count = 0
        has_anim = False
        has_vrc = False
        has_arm = False
        smr_count = 0
        ma_count = 0
        only_cam_light = False

        root_game_object = transforms.get(start_transform_file_id, {}).get("go", "")
        if root_game_object in camera_or_light_game_object_ids and not transforms.get(start_transform_file_id, {}).get("children"):
            only_cam_light = True

        while queue_ids:
            cur_transform = queue_ids.popleft()
            if cur_transform in seen:
                continue
            seen.add(cur_transform)
            desc_count += 1
            transform_info = transforms.get(cur_transform)
            if not transform_info:
                continue
            game_object_file_id = transform_info.get("go", "")
            if game_object_file_id:
                if game_object_file_id in animator_game_object_ids:
                    has_anim = True
                if game_object_file_id in vrc_descriptor_game_object_ids:
                    has_vrc = True
                if game_object_file_id in armature_game_object_ids:
                    has_arm = True
                if game_object_file_id in skinned_mesh_game_object_ids:
                    smr_count += 1
                if game_object_file_id in ma_game_object_ids:
                    ma_count += 1
            for child_fid in transform_info.get("children", []):
                queue_ids.append(child_fid)

        # Count nested PrefabInstances & MA components parented anywhere inside subtree
        prefab_instance_child_count = sum(
            active_prefab_count_by_transform.get(transform_item, 0) for transform_item in seen
        )

        return {
            "descendants": desc_count,
            "has_animator": has_anim,
            "has_vrc_descriptor": has_vrc,
            "has_armature": has_arm,
            "smr_count": smr_count,
            "ma_count": ma_count,
            "pi_children": prefab_instance_child_count,
            "only_cam_light": only_cam_light,
        }

    # Build ordered top-level root candidates
    ordered_roots: List[Tuple[str, str]] = []
    seen_root_keys: Set[Tuple[str, str]] = set()

    if scene_root_ids:
        for root_fid in scene_root_ids:
            if root_fid in transforms:
                key = ("tr", root_fid)
                if key not in seen_root_keys:
                    seen_root_keys.add(key)
                    ordered_roots.append(key)
            elif root_fid in stripped_transform_to_prefab:
                prefab_instance_file_id = stripped_transform_to_prefab[root_fid]
                key = ("pi", prefab_instance_file_id)
                if key not in seen_root_keys:
                    seen_root_keys.add(key)
                    ordered_roots.append(key)
            elif root_fid in prefab_instances:
                key = ("pi", root_fid)
                if key not in seen_root_keys:
                    seen_root_keys.add(key)
                    ordered_roots.append(key)
    else:
        for transform_file_id, transform_info in transforms.items():
            if transform_info.get("father") == "0":
                key = ("tr", transform_file_id)
                if key not in seen_root_keys:
                    seen_root_keys.add(key)
                    ordered_roots.append(key)
        for prefab_instance_file_id, prefab_instance_info in prefab_instances.items():
            if str(prefab_instance_info.get("parent", "0")) == "0":
                key = ("pi", prefab_instance_file_id)
                if key not in seen_root_keys:
                    seen_root_keys.add(key)
                    ordered_roots.append(key)

    candidates: List[Dict[str, Any]] = []
    for order_idx, (root_kind, root_fid) in enumerate(ordered_roots):
        if root_kind == "tr":
            transform_info = transforms.get(root_fid, {})
            game_object_file_id = transform_info.get("go", "")
            game_object_info = game_objects.get(game_object_file_id, {})
            disp_name = str(game_object_info.get("name", "") or "").strip()
            if not disp_name:
                disp_name = f"Transform_{root_fid}"
            is_active = bool(game_object_info.get("active", True))
            stats = _collect_transform_subtree_stats(root_fid)
            src_prefab_stem = ""
        else:
            prefab_instance_info = prefab_instances.get(root_fid, {})
            src_guid = str(prefab_instance_info.get("source_guid", "") or "")
            src_prefab_stem = guid_stems.get(src_guid, "")
            disp_name = str(prefab_instance_info.get("name", "") or "").strip() or src_prefab_stem
            if not disp_name:
                disp_name = f"PrefabInstance_{root_fid}"
            is_active = bool(prefab_instance_info.get("active", True))
            stats = {
                "descendants": 1,
                "has_animator": False,
                "has_vrc_descriptor": False,
                "has_armature": True,
                "smr_count": 1,
                "ma_count": 0,
                "pi_children": 0,
                "only_cam_light": False,
            }

        lower_name = disp_name.lower()
        is_utility_name = (
            lower_name in NON_AVATAR_UTILITY_NAMES
            or lower_name.startswith(("nadena.dev.", "com.vrchat.", "__vrc"))
            or stats["only_cam_light"]
        )
        is_avatar_like = (
            not is_utility_name
            and (
                stats["has_vrc_descriptor"]
                or stats["has_animator"]
                or stats["has_armature"]
                or stats["smr_count"] > 0
                or stats["descendants"] > 1
                or root_kind == "pi"
            )
        )
        if not include_non_avatar_roots and not is_avatar_like:
            continue

        candidates.append(
            {
                "scene_order": order_idx,
                "name": disp_name,
                "active": is_active,
                "root_kind": root_kind,
                "root_id": root_fid,
                "descendant_count": stats["descendants"],
                "smr_count": stats["smr_count"],
                "ma_count": stats["ma_count"],
                "pi_children": stats["pi_children"],
                "has_vrc_descriptor": stats["has_vrc_descriptor"],
                "has_animator": stats["has_animator"],
                "source_prefab": src_prefab_stem,
                "is_avatar": is_avatar_like,
            }
        )

    if sort_active_first:
        candidates.sort(key=lambda item: (0 if item["active"] else 1, item["scene_order"]))

    for list_idx, entry in enumerate(candidates, start=1):
        entry["index"] = list_idx
    return candidates


def prompt_select_scene_avatar(
    avatars: Sequence[Dict[str, Any]],
    *,
    input_func: Optional[Callable[[str], str]] = None,
    output_func: Optional[Callable[[str], None]] = None,
    page_size: int = DEFAULT_AVATAR_PAGE_SIZE,
    default_name: Optional[str] = None,
    scene_label: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Display a paginated menu (10 options per page + Next button when more avatars exist)
    to let the user choose which avatar from a Unity scene to import.
    """
    if not avatars:
        return None

    read_input = input_func if input_func is not None else input
    emit = output_func if output_func is not None else print
    per_page = max(1, int(page_size))

    if default_name:
        target_low = default_name.strip().lower()
        for entry in avatars:
            if str(entry.get("name", "")).strip().lower() == target_low:
                return entry

    # Safe fallback when running non-interactively with real stdin
    if input_func is None and not sys.stdin.isatty():
        for entry in avatars:
            if entry.get("active"):
                return entry
        return avatars[0]

    total_count = len(avatars)
    total_pages = (total_count + per_page - 1) // per_page
    page_idx = 0

    while True:
        start_idx = page_idx * per_page
        end_idx = min(start_idx + per_page, total_count)
        page_items = avatars[start_idx:end_idx]

        header_suffix = f" ({scene_label})" if scene_label else ""
        emit("")
        emit(
            f"=== Select Avatar to Import{header_suffix} "
            f"[Page {page_idx + 1}/{total_pages}, {total_count} found] ==="
        )
        for local_num, item in enumerate(page_items, start=1):
            active_tag = "Active" if item.get("active") else "Inactive"
            extra_tags: List[str] = [active_tag]
            ma_cnt = int(item.get("ma_count", 0) or 0)
            if ma_cnt > 0:
                extra_tags.append(f"MA:{ma_cnt}")
            prefab_instance_count = int(item.get("pi_children", 0) or 0)
            if prefab_instance_count > 0:
                extra_tags.append(f"Outfits:{prefab_instance_count}")
            badge_text = ", ".join(extra_tags)
            emit(f"  [{local_num:2d}] {item.get('name', 'Avatar')} ({badge_text})")

        nav_options: List[str] = [f"1-{len(page_items)} select"]
        has_next = (page_idx + 1) < total_pages
        has_prev = page_idx > 0
        if has_next:
            nav_options.append("[N] Next >>")
            emit(f"  [ N] Next page >> ({total_count - end_idx} more)")
        if has_prev:
            nav_options.append("[P] << Prev")
            emit("  [ P] << Previous page")
        emit("  [ 0] Cancel")

        try:
            raw_choice = read_input(f"Choose ({', '.join(nav_options)}, [0] Cancel): ")
        except EOFError:
            return avatars[0]

        choice_txt = (raw_choice or "").strip()
        choice_low = choice_txt.lower()
        if not choice_txt:
            continue
        if choice_low in ("0", "q", "quit", "cancel", "sair"):
            return None
        if choice_low in ("n", "next", "p+" , ">"):
            if has_next:
                page_idx += 1
            else:
                emit("Already on the last page.")
            continue
        if choice_low in ("p", "prev", "previous", "back", "<"):
            if has_prev:
                page_idx -= 1
            else:
                emit("Already on the first page.")
            continue
        if choice_txt.isdigit():
            picked_num = int(choice_txt)
            if 1 <= picked_num <= len(page_items):
                return page_items[picked_num - 1]
            # Also allow typing a global index across pages (e.g. 15)
            if 1 <= picked_num <= total_count:
                return avatars[picked_num - 1]
            emit(f"Invalid option: {choice_txt}")
            continue

        # Allow typing exact or substring avatar name directly
        for item in avatars:
            if str(item.get("name", "")).strip().lower() == choice_low:
                return item
        substring_matches = [
            item for item in avatars if choice_low in str(item.get("name", "")).lower()
        ]
        if len(substring_matches) == 1:
            return substring_matches[0]
        emit(f"Unrecognized selection: {choice_txt}")


def prompt_blendshape_import_preferences(
    *,
    preset_face: Optional[bool] = None,
    preset_body: Optional[bool] = None,
    input_func: Optional[Callable[[str], str]] = None,
    output_func: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, bool]:
    """
    Ask the user separately whether to import facial blendshapes and body blendshapes from Unity.
    When No is chosen, weights for that category are zeroed (0.0) in the generated `.cfg` using
    all blendshapes extracted from the avatar + custom dress FBXs.
    """
    read_input = input_func if input_func is not None else input
    emit = output_func if output_func is not None else print

    def _ask_yes_no(prompt_label: str, default_yes: bool = True) -> bool:
        if input_func is None and not sys.stdin.isatty():
            return default_yes
        hint_tag = "[Y/n]" if default_yes else "[y/N]"
        while True:
            try:
                ans = (read_input(f"{prompt_label} {hint_tag}: ") or "").strip().lower()
            except EOFError:
                return default_yes
            if not ans:
                return default_yes
            if ans in ("y", "yes", "s", "sim", "1", "true"):
                return True
            if ans in ("n", "no", "nao", "não", "0", "false"):
                return False
            emit("Please answer y (yes) or n (no).")

    use_face = (
        preset_face
        if preset_face is not None
        else _ask_yes_no("Import FACE blendshapes from Unity into .cfg?", default_yes=True)
    )
    use_body = (
        preset_body
        if preset_body is not None
        else _ask_yes_no("Import BODY blendshapes from Unity into .cfg?", default_yes=True)
    )
    return bool(use_face), bool(use_body)
