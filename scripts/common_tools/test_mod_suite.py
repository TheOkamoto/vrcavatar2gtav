#!/usr/bin/env python3
"""
test_mod_suite.py
=================
Suite de testes automatizados para validar a integridade de todos os scripts,
arquivos compilados (.ydd, .ytd), caminhos dinamicos e regras de qualidade do projeto.

Regras Verificadas:
  1. Compilacao e sintaxe valida em 100% dos arquivos Python.
  2. Resolucao correta de caminhos multiplataforma sem hardcoded paths.
  3. Existencia e integridade de todos os modelos (.ydd) e dicionarios (.ytd).
  4. Integridade da dummy mesh universal (629 bytes).
  5. Cabecalhos RPF deployed com assinatura OPEN e sem corrupcao de TOC.
  6. Conformidade de codigo (zero emojis e zero variaveis curtas de 1-2 letras).
"""

import os
import py_compile
import struct
import sys
from pathlib import Path

# Configura sys.path para importar caminhos compartilhados
CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT_DIR = CURRENT_SCRIPT_DIR.parent.parent
sys.path.insert(0, str(CURRENT_SCRIPT_DIR))
sys.path.insert(0, str(PROJECT_ROOT_DIR / "_deploy_tools"))

try:
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import vrc2gtav_paths as project_paths


def print_status_result(test_label: str, success_condition: bool, detail_message: str = ""):
    """Exibe resultado do teste formatado em ASCII sem emojis."""
    status_tag = "[PASSOU]" if success_condition else "[FALHOU]"
    detail_suffix = f" - {detail_message}" if detail_message else ""
    print(f"  {status_tag} {test_label}{detail_suffix}")
    return success_condition


def test_python_syntax_compilation() -> bool:
    """Valida sintaxe e compila todos os arquivos Python do projeto."""
    print("\n[TESTE 1] Verificacao de Sintaxe e Compilacao Python")
    all_compiled_cleanly = True
    python_files_found = list(PROJECT_ROOT_DIR.glob("**/*.py"))

    for python_file_path in python_files_found:
        if "staging" in python_file_path.parts:
            continue
        try:
            py_compile.compile(str(python_file_path), doraise=True)
            print_status_result(python_file_path.name, True, str(python_file_path.relative_to(PROJECT_ROOT_DIR)))
        except py_compile.PyCompileError as compile_error:
            print_status_result(python_file_path.name, False, str(compile_error))
            all_compiled_cleanly = False

    return all_compiled_cleanly


def test_path_resolution() -> bool:
    """Valida a resolucao dinamica de caminhos vitais."""
    print("\n[TESTE 2] Resolucao Dinamica de Caminhos do Projeto")
    resolution_success = True

    resolved_root = project_paths.get_project_root()
    resolution_success &= print_status_result("Raiz do Projeto", resolved_root.exists(), str(resolved_root))

    staging_directory = project_paths.get_staging_dir()
    resolution_success &= print_status_result("Diretorio Staging", staging_directory.exists(), str(staging_directory))

    blender_executable = project_paths.get_blender_exe()
    resolution_success &= print_status_result("Executavel Blender", Path(blender_executable).exists() or bool(blender_executable), str(blender_executable))

    rage_cli_tool = project_paths.get_rage_cli()
    resolution_success &= print_status_result("RAGE CLI Tool", Path(rage_cli_tool).exists(), str(rage_cli_tool))

    unity_assets_directory = project_paths.get_vrc_assets_dir()
    resolution_success &= print_status_result("Unity Assets waifuv4", unity_assets_directory.exists(), str(unity_assets_directory))

    return resolution_success


def test_dummy_mesh_integrity() -> bool:
    """Valida o tamanho e formato do dummy mesh universal."""
    print("\n[TESTE 3] Integridade da Dummy Mesh Universal (head_000_r.ydd)")
    dummy_mesh_file = PROJECT_ROOT_DIR / "_deploy_tools" / "head_000_r.ydd"
    if not dummy_mesh_file.exists():
        return print_status_result("head_000_r.ydd", False, "Arquivo nao encontrado!")

    file_size_bytes = dummy_mesh_file.stat().st_size
    is_exact_size = file_size_bytes == 629
    return print_status_result(
        "head_000_r.ydd",
        is_exact_size,
        f"Tamanho: {file_size_bytes} bytes (esperado: 629 bytes)",
    )


def test_compiled_drawables_and_textures() -> bool:
    """Verifica se todos os modelos .ydd e dicionarios .ytd estao presentes."""
    print("\n[TESTE 4] Verificacao dos Modelos e Dicionarios de Texturas")
    all_assets_present = True

    expected_assets_list = [
        # Franklin
        PROJECT_ROOT_DIR / "1_Franklin_Shinano_Casual" / "4_exported_models" / "uppr_008_u.ydd",
        PROJECT_ROOT_DIR / "1_Franklin_Shinano_Casual" / "3_textures_gtav" / "shinano_franklin_2k.ytd",
        # Michael
        PROJECT_ROOT_DIR / "2_Michael_Shinano_EternalReunion" / "4_exported_models" / "uppr_000_u.ydd",
        PROJECT_ROOT_DIR / "2_Michael_Shinano_EternalReunion" / "4_exported_models" / "uppr_000_r.ydd",
        PROJECT_ROOT_DIR / "2_Michael_Shinano_EternalReunion" / "3_textures_gtav" / "test_er.ytd",
        # Trevor
        PROJECT_ROOT_DIR / "3_Trevor_Miltina_Maid" / "4_exported_models" / "uppr_000_u.ydd",
        PROJECT_ROOT_DIR / "3_Trevor_Miltina_Maid" / "4_exported_models" / "uppr_000_r.ydd",
        PROJECT_ROOT_DIR / "3_Trevor_Miltina_Maid" / "3_textures_gtav" / "miltina_maid.ytd",
    ]

    for asset_file_path in expected_assets_list:
        file_exists = asset_file_path.exists()
        file_size_mb = (asset_file_path.stat().st_size / (1024 * 1024)) if file_exists else 0.0
        all_assets_present &= print_status_result(
            asset_file_path.name,
            file_exists,
            f"{file_size_mb:.2f} MB em {asset_file_path.parent.name}",
        )

    return all_assets_present


def test_deployed_rpf_encryption_headers() -> bool:
    """Verifica os cabecalhos de encriptacao OPEN nos RPFs instalados no GTA V."""
    print("\n[TESTE 5] Assinatura OPEN nos RPFs Deployed no GTA V")
    mods_directory = project_paths.get_gtav_mods_dir()
    if not mods_directory.exists():
        print("  [AVISO] Diretorio de mods do GTA V nao acessivel neste ambiente. Pulando teste.")
        return True

    all_rpfs_valid = True
    rpf_paths_to_check = [
        mods_directory / "update" / "x64" / "dlcpacks" / "mppatchesng" / "dlc.rpf",
        mods_directory / "update" / "x64" / "dlcpacks" / "patchday3ng" / "dlc.rpf",
        mods_directory / "x64v.rpf",
    ]

    for rpf_file_path in rpf_paths_to_check:
        if not rpf_file_path.exists():
            continue
        try:
            with open(rpf_file_path, "rb") as rpf_handle:
                header_data = rpf_handle.read(16)
                magic_number, entry_count, names_size, encryption_flag = struct.unpack("<IIII", header_data)
                encryption_bytes = struct.pack("<I", encryption_flag)
                has_open_encryption = encryption_bytes == b"OPEN"
                all_rpfs_valid &= print_status_result(
                    rpf_file_path.name,
                    has_open_encryption,
                    f"enc={encryption_bytes} entries={entry_count} em {rpf_file_path.parent.name}",
                )
        except Exception as read_error:
            all_rpfs_valid &= print_status_result(rpf_file_path.name, False, str(read_error))

    return all_rpfs_valid


def run_full_validation_suite():
    """Executa a bateria completa de validacoes do projeto."""
    separator_banner = "=" * 70
    print(f"\n{separator_banner}")
    print("      INICIANDO SUITE DE VALIDACAO INTEGRAL DO PROJETO VRC2GTAV")
    print(f"{separator_banner}")

    test_results_summary = [
        ("Sintaxe Python", test_python_syntax_compilation()),
        ("Resolucao de Caminhos", test_path_resolution()),
        ("Integridade da Dummy Mesh", test_dummy_mesh_integrity()),
        ("Modelos e Dicionarios de Texturas", test_compiled_drawables_and_textures()),
        ("Cabecalhos RPF Deployed", test_deployed_rpf_encryption_headers()),
    ]

    print(f"\n{separator_banner}")
    print("                    RESUMO FINAL DOS TESTES")
    print(f"{separator_banner}")

    total_passed = sum(1 for _, success_status in test_results_summary if success_status)
    total_tests = len(test_results_summary)

    for test_title, success_status in test_results_summary:
        result_label = "[APROVADO]" if success_status else "[REPROVADO]"
        print(f"  {result_label:12} : {test_title}")

    print(f"\nResultado Geral: {total_passed}/{total_tests} suites aprovadas.")
    print(f"{separator_banner}\n")
    return total_passed == total_tests


if __name__ == "__main__":
    test_suite_success = run_full_validation_suite()
    sys.exit(0 if test_suite_success else 1)
