"""Install or update the VRCAvatar2GTAV Unity Editor plugin inside a target Unity project.

Strictly copies ONLY Assets/VRCAvatar2GTAV/ (and cleans up legacy Assets/VRC2GTAV/)
so existing project files, scenes, packages, and unrelated assets are never modified.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def install_plugin(unity_project: Path, plugin_source_root: Path | None = None) -> Path:
    """Copy Assets/VRCAvatar2GTAV into <unity_project>/Assets/VRCAvatar2GTAV cleanly."""
    resolved_project = unity_project.expanduser().resolve()
    assets_dir = resolved_project / "Assets"
    if not assets_dir.is_dir():
        raise FileNotFoundError(
            f"Target Unity project does not contain an Assets/ directory: {resolved_project}"
        )

    source_root = (
        plugin_source_root.expanduser().resolve()
        if plugin_source_root is not None
        else Path(__file__).resolve().parent / "Assets" / "VRCAvatar2GTAV"
    )
    if not source_root.is_dir():
        raise FileNotFoundError(f"Plugin source directory not found: {source_root}")

    legacy_dir = assets_dir / "VRC2GTAV"
    legacy_meta = assets_dir / "VRC2GTAV.meta"
    if legacy_dir.is_dir():
        shutil.rmtree(legacy_dir)
    if legacy_meta.is_file():
        legacy_meta.unlink()

    destination_root = assets_dir / "VRCAvatar2GTAV"
    dest_toolchain = destination_root / "Toolchain"
    if (source_root / "Toolchain").is_dir() and dest_toolchain.is_dir():
        for existing_item in list(dest_toolchain.rglob("*")):
            rel_existing = existing_item.relative_to(dest_toolchain)
            if (
                existing_item.is_file()
                and not existing_item.name.endswith(".meta")
                and existing_item.name != "vrc2gtav.cfg"
                and "configs" not in rel_existing.parts
            ):
                existing_item.unlink()

    for src_item in source_root.rglob("*"):
        rel = src_item.relative_to(source_root)
        if "__pycache__" in rel.parts or src_item.suffix.lower() in (".pyc", ".pyo"):
            continue
        dst_item = destination_root / rel
        if src_item.is_dir():
            dst_item.mkdir(parents=True, exist_ok=True)
            continue
        dst_item.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_item, dst_item)

    return destination_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Safely install VRC2GTAV Unity Editor UI into Assets/VRC2GTAV/."
    )
    parser.add_argument(
        "--unity-project",
        required=True,
        help="Path to the Unity project folder containing Assets/",
    )
    args = parser.parse_args(argv)
    installed_path = install_plugin(Path(args.unity_project))
    print(f"[OK] Installed VRC2GTAV Unity Editor plugin at: {installed_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
