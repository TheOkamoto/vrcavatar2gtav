#!/usr/bin/env python3
"""
build_vtoon_asi.py
==================
Compile GTAVVToon.asi with MSVC x64 (`vcvars64.bat`) and deploy
GTAVVToon.asi + GTAVVToon.ini + vtoon_profiles/ into character packages
and the GTA V game root directory.
"""

import argparse
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
    """Locate vcvars64.bat across Visual Studio 2022/2025 installs."""
    candidates = [
        DEFAULT_VCVARS64,
        Path("/mnt/c/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvars64.bat"),
        Path("/mnt/c/Program Files/Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvars64.bat"),
        Path("/mnt/c/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Auxiliary/Build/vcvars64.bat"),
        Path("/mnt/c/Program Files/Microsoft Visual Studio/18/Community/VC/Auxiliary/Build/vcvars64.bat"),
    ]
    for candidate_path in candidates:
        if candidate_path.is_file():
            return candidate_path
    for pf_root in (
        Path("/mnt/c/Program Files/Microsoft Visual Studio"),
        Path("/mnt/c/Program Files (x86)/Microsoft Visual Studio"),
    ):
        if not pf_root.is_dir():
            continue
        for match_bat in pf_root.rglob("vcvars64.bat"):
            return match_bat
    raise FileNotFoundError("Could not locate MSVC vcvars64.bat")


def _to_windows_path(posix_path: Path) -> str:
    """Convert /mnt/<drive>/... WSL path to Windows <DRIVE>:\\... path."""
    resolved_str = str(posix_path.resolve())
    if resolved_str.startswith("/mnt/") and len(resolved_str) > 6 and resolved_str[6] == "/":
        drive_letter = resolved_str[5].upper()
        win_tail = resolved_str[7:].replace("/", "\\")
        return f"{drive_letter}:\\{win_tail}"
    return resolved_str


def compile_vtoon_asi(
    cpp_path: Path,
    output_asi: Path,
    game_dir: Path | None = None,
    ini_source: Path | None = None,
    profiles_dir: Path | None = None,
) -> Path:
    """Compile GTAVVToon.asi via MSVC cl.exe and deploy artifacts cleanly."""
    vcvars_bat = _find_vcvars64()
    output_asi.parent.mkdir(parents=True, exist_ok=True)

    win_vcvars = _to_windows_path(vcvars_bat)
    win_cpp = _to_windows_path(cpp_path)
    win_asi = _to_windows_path(output_asi)
    win_out_dir = _to_windows_path(output_asi.parent)

    build_bat = _SCRIPT_DIR / "_build_gtav_vtoon.bat"
    libs_arg = "d3d11.lib dxgi.lib d3dcompiler.lib windowscodecs.lib ole32.lib user32.lib"
    bat_lines = [
        "@echo off",
        f'call "{win_vcvars}" > NUL < NUL',
        "if errorlevel 1 exit /b 1",
        f'cl.exe /nologo /O2 /EHsc /std:c++17 /LD "{win_cpp}" /Fe:"{win_asi}" /Fo:"{win_out_dir}\\\\" {libs_arg} < NUL',
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
            raise RuntimeError(f"MSVC build of GTAVVToon.asi failed with code {proc.returncode}")
    finally:
        build_bat.unlink(missing_ok=True)
        for leftover_name in ("gtav_vtoon.obj", "GTAVVToon.exp", "GTAVVToon.lib"):
            (output_asi.parent / leftover_name).unlink(missing_ok=True)

    def _sync_bundle_into(target_root: Path) -> None:
        if not target_root.is_dir():
            return
        dest_asi = target_root / output_asi.name
        if dest_asi.resolve() != output_asi.resolve():
            shutil.copy2(output_asi, dest_asi)
            print(f"Deployed VToon ASI -> {dest_asi}")
        if ini_source is not None and ini_source.is_file():
            dest_ini = target_root / ini_source.name
            if dest_ini.resolve() != ini_source.resolve():
                shutil.copy2(ini_source, dest_ini)
                print(f"Deployed VToon INI -> {dest_ini}")
        if profiles_dir is not None and profiles_dir.is_dir():
            dest_prof = target_root / profiles_dir.name
            if dest_prof.resolve() != profiles_dir.resolve():
                shutil.copytree(profiles_dir, dest_prof, dirs_exist_ok=True)
                print(f"Deployed VToon profiles -> {dest_prof}")

    if game_dir is not None and game_dir.is_dir():
        _sync_bundle_into(game_dir)

        for pkg_folder in ("1_Franklin_Shinano_Casual", "3_Trevor_Miltina_Maid"):
            _sync_bundle_into(_REPO_ROOT / pkg_folder / "5_rpf_package")

    return output_asi


def main() -> int:
    parser = argparse.ArgumentParser(description="Build GTAVVToon.asi with MSVC x64")
    default_pkg = _REPO_ROOT / "2_Michael_Shinano_EternalReunion" / "5_rpf_package"
    parser.add_argument("--output-asi", default=str(default_pkg / "GTAVVToon.asi"))
    parser.add_argument("--game-dir", default="")
    parser.add_argument("--no-deploy", action="store_true", help="Compile without copying into game or sibling packages")
    parser.add_argument("--ini", default=str(default_pkg / "GTAVVToon.ini"))
    parser.add_argument("--profiles-dir", default=str(default_pkg / "vtoon_profiles"))
    cli_args = parser.parse_args()

    resolved_game = (
        None
        if cli_args.no_deploy
        else (Path(cli_args.game_dir) if cli_args.game_dir else vrc2gtav_paths.get_gtav_root_dir())
    )
    out_path = compile_vtoon_asi(
        cpp_path=_SCRIPT_DIR / "gtav_vtoon.cpp",
        output_asi=Path(cli_args.output_asi),
        game_dir=resolved_game,
        ini_source=None if cli_args.no_deploy else Path(cli_args.ini),
        profiles_dir=None if cli_args.no_deploy else Path(cli_args.profiles_dir),
    )
    print(f"Built OK: {out_path} ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
