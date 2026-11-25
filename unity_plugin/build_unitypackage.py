#!/usr/bin/env python3
"""
build_unitypackage.py
=====================
Stage the complete non-copyrighted VRCAvatar2GTAV project toolchain into
`Assets/VRCAvatar2GTAV/Toolchain/` and build `VRCAvatar2GTAV.unitypackage`
containing Editor UI + Python/ASI runtime scripts cleanly (excluding GTA V
game archives, paid VRChat assets, third-party DLLs, and local caches).
"""

from __future__ import annotations

import argparse
import hashlib
import io as io_stream
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tarfile
import time
from typing import Callable, Dict, Iterable, List, Optional, Tuple


DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_TOP_FILES = (
    "EXECUTAR_GERENCIADOR.bat",
    "LICENSE",
    "README.ja.md",
    "README.md",
    "README.pt-BR.md",
    "RUN_MANAGER.bat",
    "requirements.txt",
    "run_mod_manager.py",
    "setup_first_run.py",
    "vrc2gtav.cfg.example",
)

ALLOWED_STATIC_DIRS = (
    "_deploy_tools",
    "configs",
    "docs",
    "scripts",
    "1_Franklin_Shinano_Casual",
    "2_Michael_Shinano_EternalReunion",
    "3_Trevor_Miltina_Maid",
)

ALLOWED_EXTENSIONS = frozenset(
    {
        ".py",
        ".cfg",
        ".md",
        ".txt",
        ".bat",
        ".example",
        ".asi",
        ".ini",
        ".cpp",
        ".hpp",
    }
)

ALLOWED_DUMMY_YDD_NAMES = frozenset({"head_000_r.ydd", "p_eyes_dummy.ydd"})

FORBIDDEN_SUBDIRS = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "env",
        "venv",
        "staging",
        "tools",
        "backups",
        "logs",
        "npcs",
        "imported_unity_projects",
        "vtoon_profiles",
        "3_textures_gtav",
        "4_exported_models",
        "patchday3_work",
        "mppatches_work",
    }
)


def _deterministic_guid(asset_rel_posix: str) -> str:
    """Return a stable 32-char lowercase hex GUID from an Assets-relative path."""
    digest_bytes = hashlib.md5(f"VRCAvatar2GTAV::{asset_rel_posix}".encode("utf-8")).hexdigest()
    return digest_bytes


def _load_existing_meta(
    rel_from_plugin: Path,
    existing_meta_dirs: Iterable[Path],
) -> Optional[str]:
    """Read an existing `.meta` file preserving Unity GUIDs when available."""
    meta_rel = Path(f"{rel_from_plugin.as_posix()}.meta")
    for base_dir in existing_meta_dirs:
        candidate = base_dir / meta_rel
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8", errors="ignore")
    return None


def _build_default_meta_text(asset_rel_posix: str, is_dir: bool) -> str:
    """Create a valid Unity `.meta` YAML document for files or directories."""
    guid_hex = _deterministic_guid(asset_rel_posix)
    if is_dir:
        return (
            "fileFormatVersion: 2\n"
            f"guid: {guid_hex}\n"
            "folderAsset: yes\n"
            "DefaultImporter:\n"
            "  externalObjects: {}\n"
            "  userData: \n"
            "  assetBundleName: \n"
            "  assetBundleVariant: \n"
        )
    low_name = asset_rel_posix.lower()
    if low_name.endswith(".cs"):
        return (
            "fileFormatVersion: 2\n"
            f"guid: {guid_hex}\n"
            "MonoImporter:\n"
            "  externalObjects: {}\n"
            "  serializedVersion: 2\n"
            "  defaultReferences: []\n"
            "  executionOrder: 0\n"
            "  icon: {instanceID: 0}\n"
            "  userData: \n"
            "  assetBundleName: \n"
            "  assetBundleVariant: \n"
        )
    if low_name.endswith(".asmdef"):
        return (
            "fileFormatVersion: 2\n"
            f"guid: {guid_hex}\n"
            "AssemblyDefinitionImporter:\n"
            "  externalObjects: {}\n"
            "  userData: \n"
            "  assetBundleName: \n"
            "  assetBundleVariant: \n"
        )
    return (
        "fileFormatVersion: 2\n"
        f"guid: {guid_hex}\n"
        "DefaultImporter:\n"
        "  externalObjects: {}\n"
        "  userData: \n"
        "  assetBundleName: \n"
        "  assetBundleVariant: \n"
    )


def _extract_guid_from_meta(meta_text: str, fallback_rel: str) -> str:
    """Parse `guid:` from Unity `.meta` YAML, falling back deterministically."""
    match_obj = re.search(r"^guid:\s*([0-9a-fA-F]{32})\b", meta_text, re.MULTILINE)
    return match_obj.group(1).lower() if match_obj else _deterministic_guid(fallback_rel)


def _should_bundle_repo_file(rel_path: Path) -> bool:
    """Filter project files so only self-authored, non-copyrighted toolchain assets enter Toolchain/."""
    parts_low = [part.lower() for part in rel_path.parts]
    if any(part in FORBIDDEN_SUBDIRS or part.endswith("_extracted") for part in parts_low[:-1]):
        return False

    name_low = rel_path.name.lower()
    if name_low in ("vrc2gtav.cfg", "npc_registry.json"):
        return False
    if name_low in ALLOWED_DUMMY_YDD_NAMES:
        return True
    if name_low.endswith((".pyc", ".pyo", ".meta", ".rpf", ".ytd", ".yft", ".ydd", ".dds", ".dll", ".exe")):
        return False
    if rel_path.parent.name.lower() == "3_textures_gtav" and name_low.endswith(".py"):
        return True
    return rel_path.suffix.lower() in ALLOWED_EXTENSIONS


def _clear_readonly_and_retry(
    remove_func: Callable[..., None],
    target_path: str,
    *_extra_args: object,
) -> None:
    """Clear read-only attributes and retry filesystem unlink/rmdir once."""
    try:
        os.chmod(target_path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass
    remove_func(target_path)


def _remove_directory_tree(target_dir: Path, max_attempts: int = 8) -> None:
    """Remove a directory tree, tolerating transient Windows/sync locks cleanly."""
    for attempt_index in range(max_attempts):
        if not target_dir.exists():
            return
        try:
            if sys.version_info >= (3, 12):
                shutil.rmtree(target_dir, onexc=_clear_readonly_and_retry)
            else:
                shutil.rmtree(target_dir, onerror=_clear_readonly_and_retry)
            return
        except OSError:
            if attempt_index + 1 >= max_attempts:
                raise
            time.sleep(0.2 * (attempt_index + 1))


def sync_toolchain_bundle(
    repo_root: Path = DEFAULT_REPO_ROOT,
    plugin_root: Optional[Path] = None,
) -> Path:
    """Populate `Assets/VRCAvatar2GTAV/Toolchain/` cleanly from `repo_root`."""
    resolved_repo = repo_root.resolve()
    target_plugin = (
        plugin_root.resolve()
        if plugin_root is not None
        else Path(__file__).resolve().parent / "Assets" / "VRCAvatar2GTAV"
    )
    toolchain_dir = target_plugin / "Toolchain"
    _remove_directory_tree(toolchain_dir)
    toolchain_dir.mkdir(parents=True, exist_ok=True)

    for top_name in ALLOWED_TOP_FILES:
        src_top = resolved_repo / top_name
        if src_top.is_file():
            shutil.copy2(src_top, toolchain_dir / top_name)

    for dir_name in ALLOWED_STATIC_DIRS:
        src_base = resolved_repo / dir_name
        if not src_base.is_dir():
            continue
        for cur_root, dir_names, file_names in os.walk(src_base):
            dir_names[:] = sorted(
                sub for sub in dir_names
                if sub.lower() not in FORBIDDEN_SUBDIRS and not sub.lower().endswith("_extracted")
            )
            cur_path = Path(cur_root)
            for fname in sorted(file_names):
                src_file = cur_path / fname
                rel_path = src_file.relative_to(resolved_repo)
                if not _should_bundle_repo_file(rel_path):
                    continue
                dst_file = toolchain_dir / rel_path
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)

    return toolchain_dir


def _add_tar_bytes(tar_handle: tarfile.TarFile, arcname: str, payload: bytes) -> None:
    """Write an in-memory payload entry into a tar archive cleanly."""
    tar_info = tarfile.TarInfo(name=arcname)
    tar_info.size = len(payload)
    tar_info.mode = 0o644
    tar_handle.addfile(tar_info, io_stream.BytesIO(payload))


def _normalize_semver_version(raw_version: Optional[str]) -> Optional[str]:
    """Validate and normalize a SemVer 2.0.0 string (stripping optional leading 'v')."""
    if raw_version is None:
        return None
    cleaned = str(raw_version).strip()
    if cleaned.lower().startswith("v"):
        cleaned = cleaned[1:]
    if not cleaned:
        return None
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", cleaned):
        raise ValueError(f"Invalid SemVer version string: {raw_version!r}")
    return cleaned


def create_unitypackage(
    *,
    repo_root: Path = DEFAULT_REPO_ROOT,
    plugin_root: Optional[Path] = None,
    output_path: Optional[Path] = None,
    existing_meta_dirs: Tuple[Path, ...] = (),
    version: Optional[str] = None,
) -> Path:
    """
    Build a complete `.unitypackage` archive for `Assets/VRCAvatar2GTAV/`
    (both Editor UI scripts and self-contained `Toolchain/`).
    """
    resolved_repo = repo_root.resolve()
    resolved_plugin = (
        plugin_root.resolve()
        if plugin_root is not None
        else Path(__file__).resolve().parent / "Assets" / "VRCAvatar2GTAV"
    )
    normalized_version = _normalize_semver_version(version)
    sync_toolchain_bundle(resolved_repo, resolved_plugin)

    if output_path is not None:
        pkg_out = output_path.resolve()
    elif normalized_version is not None:
        pkg_out = resolved_repo / f"VRCAvatar2GTAV-v{normalized_version}.unitypackage"
    else:
        pkg_out = resolved_repo / "VRCAvatar2GTAV.unitypackage"
    pkg_out.parent.mkdir(parents=True, exist_ok=True)

    meta_sources = tuple(plugin_dir for plugin_dir in existing_meta_dirs if plugin_dir.is_dir())
    entries: List[Tuple[str, bool, Optional[Path], str]] = []

    root_rel = "Assets/VRCAvatar2GTAV"
    root_meta = _load_existing_meta(Path("VRCAvatar2GTAV"), [dir_path.parent for dir_path in meta_sources])
    if root_meta is None:
        root_meta = _build_default_meta_text(root_rel, True)
    entries.append((root_rel, True, None, root_meta))

    for cur_root, dir_names, file_names in os.walk(resolved_plugin):
        dir_names[:] = sorted(sub for sub in dir_names if sub.lower() != "__pycache__")
        cur_path = Path(cur_root)
        for sub_dir in dir_names:
            dir_obj = cur_path / sub_dir
            rel_in_plugin = dir_obj.relative_to(resolved_plugin)
            asset_rel = f"{root_rel}/{rel_in_plugin.as_posix()}"
            meta_txt = _load_existing_meta(rel_in_plugin, meta_sources) or _build_default_meta_text(asset_rel, True)
            entries.append((asset_rel, True, None, meta_txt))
        for fname in sorted(file_names):
            if fname.endswith(".meta") or fname.endswith(".pyc"):
                continue
            file_obj = cur_path / fname
            rel_in_plugin = file_obj.relative_to(resolved_plugin)
            asset_rel = f"{root_rel}/{rel_in_plugin.as_posix()}"
            meta_txt = _load_existing_meta(rel_in_plugin, meta_sources) or _build_default_meta_text(asset_rel, False)
            entries.append((asset_rel, False, file_obj, meta_txt))

    with tarfile.open(pkg_out, "w:gz") as tar_out:
        has_version_entry = False
        for asset_rel, is_dir, file_obj, meta_txt in entries:
            if asset_rel == f"{root_rel}/VERSION.txt":
                has_version_entry = True
            guid_hex = _extract_guid_from_meta(meta_txt, asset_rel)
            _add_tar_bytes(tar_out, f"{guid_hex}/pathname", asset_rel.encode("utf-8"))
            _add_tar_bytes(tar_out, f"{guid_hex}/asset.meta", meta_txt.encode("utf-8"))
            if not is_dir and file_obj is not None:
                _add_tar_bytes(tar_out, f"{guid_hex}/asset", file_obj.read_bytes())
        if normalized_version is not None and not has_version_entry:
            ver_rel = f"{root_rel}/VERSION.txt"
            ver_meta = _build_default_meta_text(ver_rel, False)
            ver_guid = _extract_guid_from_meta(ver_meta, ver_rel)
            _add_tar_bytes(tar_out, f"{ver_guid}/pathname", ver_rel.encode("utf-8"))
            _add_tar_bytes(tar_out, f"{ver_guid}/asset.meta", ver_meta.encode("utf-8"))
            _add_tar_bytes(tar_out, f"{ver_guid}/asset", f"{normalized_version}\n".encode("utf-8"))

    return pkg_out


def verify_unitypackage(
    package_path: Path,
    *,
    expected_version: Optional[str] = None,
) -> Dict[str, object]:
    """Verify Editor C# scripts, Toolchain scripts, and optional VERSION.txt inside a `.unitypackage`."""
    normalized_expected = _normalize_semver_version(expected_version)
    entries_by_guid: Dict[str, str] = {}
    version_text: Optional[str] = None
    with tarfile.open(package_path, "r:gz") as tar_obj:
        for member in tar_obj.getmembers():
            if member.isfile() and member.name.endswith("/pathname"):
                guid_key = member.name.split("/", 1)[0]
                handle = tar_obj.extractfile(member)
                if handle is not None:
                    entries_by_guid[guid_key] = handle.read().decode("utf-8").strip()
        for guid_key, asset_rel in entries_by_guid.items():
            if asset_rel == "Assets/VRCAvatar2GTAV/VERSION.txt":
                asset_handle = tar_obj.extractfile(f"{guid_key}/asset")
                if asset_handle is not None:
                    version_text = asset_handle.read().decode("utf-8").strip()
                break

    packed_paths = set(entries_by_guid.values())
    has_editor = "Assets/VRCAvatar2GTAV/Editor/Vrc2GtavExporterWindow.cs" in packed_paths
    has_toolchain = "Assets/VRCAvatar2GTAV/Toolchain/run_mod_manager.py" in packed_paths
    if not (has_editor and has_toolchain):
        raise RuntimeError(
            f"Incomplete .unitypackage payload in {package_path}: editor={has_editor}, toolchain={has_toolchain}"
        )
    if normalized_expected is not None and version_text != normalized_expected:
        raise RuntimeError(
            f"VERSION.txt mismatch in {package_path}: got {version_text!r}, expected {normalized_expected!r}"
        )
    return {
        "entry_count": len(packed_paths),
        "version": version_text or "",
        "has_editor": has_editor,
        "has_toolchain": has_toolchain,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for building Assets/VRCAvatar2GTAV and VRCAvatar2GTAV.unitypackage."""
    parser = argparse.ArgumentParser(
        description="Bundle project into Assets/VRCAvatar2GTAV/Toolchain and generate VRCAvatar2GTAV.unitypackage."
    )
    parser.add_argument("--output", default=None, help="Output .unitypackage file path")
    parser.add_argument("--version", default=None, help="Optional SemVer string (e.g. 1.0.0) to embed and name artifact")
    parser.add_argument("--verify", action="store_true", help="Verify generated archive payload and VERSION.txt")
    parser.add_argument("--unity-project", default=None, help="Optional Unity project root to also install into")
    args = parser.parse_args(argv)

    meta_dirs: List[Path] = []
    if args.unity_project:
        waifu_plugin = Path(args.unity_project).expanduser().resolve() / "Assets" / "VRCAvatar2GTAV"
        if waifu_plugin.is_dir():
            meta_dirs.append(waifu_plugin)

    out_pkg = create_unitypackage(
        repo_root=DEFAULT_REPO_ROOT,
        output_path=Path(args.output) if args.output else None,
        existing_meta_dirs=tuple(meta_dirs),
        version=args.version,
    )
    print(f"[OK] Built self-contained Unity package: {out_pkg} ({out_pkg.stat().st_size:,} bytes)")
    if args.verify:
        summary = verify_unitypackage(out_pkg, expected_version=args.version)
        print(
            f"[OK] Verified package payload: entries={summary['entry_count']}, version={summary['version'] or 'unversioned'}"
        )

    if args.unity_project:
        import install_unity_plugin

        installed = install_unity_plugin.install_plugin(Path(args.unity_project))
        print(f"[OK] Installed full Assets/VRCAvatar2GTAV into: {installed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
