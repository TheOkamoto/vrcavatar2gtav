#!/usr/bin/env python3
"""
build_physbones_asi.py
======================
Compile GTAVPhysBones.asi with MSVC x64 (`vcvars64.bat`) and deploy
GTAVPhysBones.asi + GTAVPhysBones.ini into the package and game directories.
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_COMMON_TOOLS = _REPO_ROOT / "scripts" / "common_tools"
if str(_COMMON_TOOLS) not in sys.path:
    sys.path.insert(0, str(_COMMON_TOOLS))

import vrc2gtav_paths


DEFAULT_VCVARS64 = Path(
    "/mnt/c/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvars64.bat"
)


def _find_vcvars64() -> Path:
    """Locate vcvars64.bat across VS 2022/2025 Community/BuildTools installs."""
    candidates = [
        DEFAULT_VCVARS64,
        Path("/mnt/c/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvars64.bat"),
        Path("/mnt/c/Program Files/Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvars64.bat"),
        Path("/mnt/c/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Auxiliary/Build/vcvars64.bat"),
        Path("/mnt/c/Program Files/Microsoft Visual Studio/18/Community/VC/Auxiliary/Build/vcvars64.bat"),
    ]
    for item in candidates:
        if item.is_file():
            return item
    # Fallback search for cl.exe inside Program Files MSVC toolsets
    for program_files_root in (Path("/mnt/c/Program Files/Microsoft Visual Studio"), Path("/mnt/c/Program Files (x86)/Microsoft Visual Studio")):
        if not program_files_root.is_dir():
            continue
        for match_bat in program_files_root.rglob("vcvars64.bat"):
            return match_bat
    raise FileNotFoundError("Could not locate MSVC vcvars64.bat")


def _to_windows_path(posix_path: Path) -> str:
    """Convert /mnt/<drive>/... WSL path to Windows <DRIVE>:\\... path."""
    resolved = str(posix_path.resolve())
    if resolved.startswith("/mnt/") and len(resolved) > 6 and resolved[6] == "/":
        drive_letter = resolved[5].upper()
        win_tail = resolved[7:].replace("/", "\\")
        return f"{drive_letter}:\\{win_tail}"
    return resolved


def compile_physbones_asi(
    cpp_path: Path,
    output_asi: Path,
    game_dir: Path | None = None,
    ini_source: Path | None = None,
) -> Path:
    """Invoke MSVC cl.exe through cmd.exe with stdin=DEVNULL and deploy .asi."""
    vcvars_bat = _find_vcvars64()
    output_asi.parent.mkdir(parents=True, exist_ok=True)

    win_vcvars = _to_windows_path(vcvars_bat)
    win_cpp = _to_windows_path(cpp_path)
    win_asi = _to_windows_path(output_asi)
    win_out_dir = _to_windows_path(output_asi.parent)

    build_bat = _SCRIPT_DIR / "_build_gtav_physbones.bat"
    bat_lines = [
        "@echo off",
        f'call "{win_vcvars}" > NUL < NUL',
        "if errorlevel 1 exit /b 1",
        f'cl.exe /nologo /O2 /EHsc /std:c++17 /LD "{win_cpp}" /Fe:"{win_asi}" /Fo:"{win_out_dir}\\\\" user32.lib < NUL',
    ]
    build_bat.write_text("\r\n".join(bat_lines) + "\r\n", encoding="ascii")

    try:
        win_bat = _to_windows_path(build_bat)
        proc = subprocess.run(
            ["/mnt/c/Windows/System32/cmd.exe", "/c", "call", win_bat],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.stdout:
            print(proc.stdout.strip())
        if proc.stderr:
            print(proc.stderr.strip(), file=sys.stderr)
        if proc.returncode != 0 or not output_asi.is_file():
            raise RuntimeError(f"MSVC build failed with code {proc.returncode}")
    finally:
        build_bat.unlink(missing_ok=True)
        for leftover in (output_asi.parent / "gtav_physbones.obj", output_asi.parent / "GTAVPhysBones.exp", output_asi.parent / "GTAVPhysBones.lib"):
            leftover.unlink(missing_ok=True)

    if game_dir is not None and game_dir.is_dir():
        dest_asi = game_dir / output_asi.name
        shutil.copy2(output_asi, dest_asi)
        print(f"Deployed ASI -> {dest_asi}")
        if ini_source is not None and ini_source.is_file():
            dest_ini = game_dir / ini_source.name
            shutil.copy2(ini_source, dest_ini)
            print(f"Deployed INI -> {dest_ini}")

    for pkg_folder in ("player_one", "player_two"):
        pkg_dir = _REPO_ROOT / pkg_folder / "5_rpf_package"
        if pkg_dir.is_dir():
            pkg_asi = pkg_dir / output_asi.name
            if pkg_asi.resolve() != output_asi.resolve():
                shutil.copy2(output_asi, pkg_asi)
                print(f"Synced ASI -> {pkg_asi}")

    return output_asi


def main() -> int:
    parser = argparse.ArgumentParser(description="Build GTAVPhysBones.asi with MSVC x64")
    parser.add_argument(
        "--output-asi",
        default=str(_REPO_ROOT / "player_zero" / "5_rpf_package" / "GTAVPhysBones.asi"),
    )
    parser.add_argument("--game-dir", default="")
    parser.add_argument(
        "--ini",
        default=str(_REPO_ROOT / "player_zero" / "5_rpf_package" / "GTAVPhysBones.ini"),
    )
    cli_args = parser.parse_args()

    resolved_game = (
        Path(cli_args.game_dir)
        if cli_args.game_dir
        else vrc2gtav_paths.get_gtav_root_dir()
    )
    out_path = compile_physbones_asi(
        cpp_path=_SCRIPT_DIR / "gtav_physbones.cpp",
        output_asi=Path(cli_args.output_asi),
        game_dir=resolved_game,
        ini_source=Path(cli_args.ini) if cli_args.ini else None,
    )
    print(f"Built {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
