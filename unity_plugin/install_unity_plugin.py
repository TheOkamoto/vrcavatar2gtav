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
    src_toolchain = source_root / "Toolchain"
    dest_toolchain = destination_root / "Toolchain"
    retired_cfg_names = {
        "shinano_blendshapes.cfg",
        "shinano_er_blendshapes.cfg",
        "miltina_blendshapes.cfg",
        "shinano_casual_physbones.cfg",
        "michael_neko_mimi_physbones.cfg",
        "miltina_maid_physbones.cfg",
    }
    if src_toolchain.is_dir() and dest_toolchain.is_dir():
        def _is_preserved_rel(rel_path: Path) -> bool:
            posix = rel_path.as_posix()
            if posix == "vrc2gtav.cfg":
                return True
            if "configs" in rel_path.parts and rel_path.name not in retired_cfg_names:
                return rel_path.suffix.lower() in (".json", ".cfg")
            return False

        for existing_item in sorted(dest_toolchain.rglob("*"), reverse=True):
            rel_existing = existing_item.relative_to(dest_toolchain)
            if "__pycache__" in rel_existing.parts:
                if existing_item.is_file():
                    existing_item.unlink()
                elif existing_item.is_dir():
                    shutil.rmtree(existing_item, ignore_errors=True)
                continue
            if existing_item.is_file():
                if existing_item.name.endswith(".meta"):
                    asset_rel = Path(rel_existing.as_posix()[:-5])
                    if _is_preserved_rel(asset_rel) or (src_toolchain / asset_rel).exists():
                        continue
                    existing_item.unlink()
                    continue
                if _is_preserved_rel(rel_existing):
                    continue
                existing_item.unlink()
            elif existing_item.is_dir():
                if rel_existing.parts == ("configs",):
                    continue
                if not (src_toolchain / rel_existing).is_dir() and not any(existing_item.iterdir()):
                    existing_item.rmdir()
                    dir_meta = Path(str(existing_item) + ".meta")
                    if dir_meta.is_file():
                        dir_meta.unlink()

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
