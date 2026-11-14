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

import ast
import filecmp
import os
import py_compile
import re as regex_module
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
    """Valida a resolucao dinamica de caminhos vitais a partir de vrc2gtav.cfg."""
    print("\n[TESTE 2] Resolucao Dinamica de Caminhos via vrc2gtav.cfg")
    resolution_success = True

    try:
        config_file_path = project_paths.find_project_config_file()
        resolution_success &= print_status_result(
            "Arquivo Central .cfg", config_file_path.exists(), str(config_file_path)
        )
    except Exception as config_error:
        resolution_success &= print_status_result(
            "Arquivo Central .cfg", False, str(config_error)
        )

    resolved_root = project_paths.get_project_root()
    resolution_success &= print_status_result("Raiz do Projeto", resolved_root.exists(), str(resolved_root))

    staging_directory = project_paths.get_staging_dir()
    resolution_success &= print_status_result("Diretorio Staging", staging_directory.exists(), str(staging_directory))

    blender_executable = project_paths.get_blender_exe()
    resolution_success &= print_status_result("Executavel Blender", Path(blender_executable).exists() or bool(blender_executable), str(blender_executable))

    python_executable = project_paths.get_python_exe()
    resolution_success &= print_status_result("Executavel Python", Path(python_executable).exists(), str(python_executable))

    rage_cli_tool = project_paths.get_rage_cli()
    resolution_success &= print_status_result("RAGE CLI Tool", Path(rage_cli_tool).exists(), str(rage_cli_tool))

    unity_assets_directory = project_paths.get_vrc_assets_dir()
    resolution_success &= print_status_result("Unity Assets waifuv4", unity_assets_directory.exists(), str(unity_assets_directory))

    return resolution_success


def test_dummy_mesh_integrity() -> bool:
    """Valida o tamanho e formato das dummy meshes universais (ped e props)."""
    print("\n[TESTE 3] Integridade das Dummy Meshes (head_000_r.ydd e p_eyes_dummy.ydd)")
    dummy_mesh_file = project_paths.get_dummy_ydd_path()
    prop_dummy_file = project_paths.get_prop_dummy_ydd_path()

    head_dummy_ok = False
    if not dummy_mesh_file.exists():
        head_dummy_ok = print_status_result("head_000_r.ydd", False, "Arquivo nao encontrado!")
    else:
        file_size_bytes = dummy_mesh_file.stat().st_size
        head_dummy_ok = print_status_result(
            "head_000_r.ydd",
            file_size_bytes == 629,
            f"Tamanho: {file_size_bytes} bytes (esperado: 629 bytes)",
        )

    prop_dummy_ok = False
    if not prop_dummy_file.exists():
        prop_dummy_ok = print_status_result("p_eyes_dummy.ydd", False, "Arquivo nao encontrado!")
    else:
        prop_size_bytes = prop_dummy_file.stat().st_size
        prop_dummy_ok = print_status_result(
            "p_eyes_dummy.ydd",
            prop_size_bytes == 515,
            f"Tamanho: {prop_size_bytes} bytes (esperado: 515 bytes)",
        )

    return head_dummy_ok and prop_dummy_ok


def test_compiled_drawables_and_textures() -> bool:
    """Verifica se todos os modelos .ydd e dicionarios .ytd configurados estao presentes."""
    print("\n[TESTE 4] Verificacao dos Modelos e Dicionarios de Texturas (.cfg)")
    all_assets_present = True

    franklin_cfg = project_paths.get_character_paths("franklin")
    michael_cfg = project_paths.get_character_paths("michael")
    trevor_cfg = project_paths.get_character_paths("trevor")

    expected_assets_list = [
        franklin_cfg["target_model_ydd"],
        franklin_cfg["ytd_file"],
        michael_cfg["target_model_ydd"],
        michael_cfg["extra_model_ydds"][0],
        michael_cfg["ytd_file"],
        trevor_cfg["target_model_ydd"],
        trevor_cfg["extra_model_ydds"][0],
        trevor_cfg["ytd_file"],
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
    rpf_paths_cfg = project_paths.get_rpf_paths()
    rpf_paths_to_check = [
        rpf_paths_cfg["mppatches_game_rpf"],
        rpf_paths_cfg["patchday3ng_game_rpf"],
        rpf_paths_cfg["patchday4ng_game_rpf"],
        rpf_paths_cfg["x64v_game_rpf"],
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
                    f"{rpf_file_path.parent.name}/{rpf_file_path.name}",
                    has_open_encryption,
                    f"enc={encryption_bytes} entries={entry_count}",
                )
        except Exception as read_error:
            all_rpfs_valid &= print_status_result(rpf_file_path.name, False, str(read_error))

    # Valida tambem se todos os p_eyes_*.ydd dos protagonistas em staging sao prop dummies
    props_extracted_dir = rpf_paths_cfg["streamedpedprops_extracted"]
    prop_dummy_file = project_paths.get_prop_dummy_ydd_path()
    if props_extracted_dir.is_dir() and prop_dummy_file.exists():
        total_glasses_checked = 0
        mismatched_glasses = []
        for character_section in ("michael", "franklin", "trevor"):
            character_cfg = project_paths.get_character_paths(character_section)
            character_props_dir = Path(character_cfg["staging_streamed_props_dir"])
            if not character_props_dir.is_dir():
                mismatched_glasses.append(f"{character_section}: pasta ausente")
                continue
            glasses_files = sorted(character_props_dir.glob("p_eyes_*.ydd"))
            if not glasses_files:
                mismatched_glasses.append(f"{character_section}: nenhum p_eyes_*.ydd")
                continue
            for glasses_path in glasses_files:
                total_glasses_checked += 1
                if not filecmp.cmp(glasses_path, prop_dummy_file, shallow=False):
                    mismatched_glasses.append(
                        f"{character_props_dir.name}/{glasses_path.name}"
                    )

        all_rpfs_valid &= print_status_result(
            "Dummies de oculos em staging (streamedpedprops)",
            len(mismatched_glasses) == 0 and total_glasses_checked == 35,
            f"{total_glasses_checked}/35 p_eyes_*.ydd identicos a p_eyes_dummy.ydd"
            if not mismatched_glasses
            else f"Divergencias: {mismatched_glasses[:5]}",
        )

    return all_rpfs_valid


def test_code_quality_and_mirror_sync() -> bool:
    """Verifica ausencia de emojis, ausencia de variaveis curtas (1-2 letras) e sincronizacao de espelhos."""
    print("\n[TESTE 6] Qualidade de Codigo e Sincronizacao de Espelhos")
    quality_passed = True
    emoji_pattern = regex_module.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")
    allowed_stdlib_short_names = {"_", "os", "re"}

    root_dir = project_paths.get_project_root()
    total_python_files = 0
    for python_file in sorted(root_dir.rglob("*.py")):
        if any(
            ignored in python_file.parts
            for ignored in (".git", "__pycache__", "extracted_rpfs", "backups")
        ):
            continue
        total_python_files += 1
        file_content = python_file.read_text(encoding="utf-8", errors="ignore")
        if emoji_pattern.search(file_content):
            quality_passed &= print_status_result(
                f"Sem emojis: {python_file.name}", False, str(python_file)
            )

        syntax_tree = ast.parse(file_content, filename=str(python_file))
        invalid_short_names = sorted(
            {
                node.id
                for node in ast.walk(syntax_tree)
                if isinstance(node, ast.Name)
                and len(node.id) <= 2
                and node.id not in allowed_stdlib_short_names
            }
            | {
                node.arg
                for node in ast.walk(syntax_tree)
                if isinstance(node, ast.arg) and len(node.arg) <= 2
            }
        )
        if invalid_short_names:
            quality_passed &= print_status_result(
                f"Variaveis >= 3 chars: {python_file.relative_to(root_dir)}",
                False,
                f"Encontradas: {invalid_short_names}",
            )

    quality_passed &= print_status_result(
        "Escaneamento AST/Emoji",
        quality_passed,
        f"{total_python_files} arquivos Python analisados",
    )

    # Verifica se copias espelhadas estao byte-a-byte identicas
    scripts_dir = project_paths.get_scripts_root_dir()
    deploy_dir = project_paths.get_deploy_tools_dir()
    common_dir = project_paths.get_common_tools_dir()
    franklin_dir = project_paths.get_character_paths("franklin")["character_dir"]
    michael_dir = project_paths.get_character_paths("michael")["character_dir"]
    trevor_dir = project_paths.get_character_paths("trevor")["character_dir"]

    mirror_pairs = [
        (common_dir / "vrc2gtav_paths.py", deploy_dir / "vrc2gtav_paths.py"),
        (common_dir / "apply_characters.py", deploy_dir / "apply_characters.py"),
        (common_dir / "apply_all_characters.py", deploy_dir / "apply_all_characters.py"),
        (common_dir / "repack_and_deploy_everything.py", deploy_dir / "repack_and_deploy_everything.py"),
        (common_dir / "run_mod_manager.py", deploy_dir / "run_mod_manager.py"),
        (common_dir / "run_mod_manager.py", root_dir / "run_mod_manager.py"),
        (scripts_dir / "Shinano_Casual_Franklin" / "build_franklin_avatar.py", franklin_dir / "2_blender" / "build_franklin_avatar.py"),
        (scripts_dir / "Shinano_Casual_Franklin" / "run_build_franklin.py", franklin_dir / "2_blender" / "run_build.py"),
        (scripts_dir / "Shinano_Casual_Franklin" / "generate_franklin_atlas.py", franklin_dir / "3_textures_gtav" / "generate_franklin_atlas.py"),
        (scripts_dir / "Shinano_EternalReunion_Michael" / "build_michael_er.py", michael_dir / "2_blender" / "build_michael_er.py"),
        (scripts_dir / "Shinano_EternalReunion_Michael" / "run_build_er.py", michael_dir / "2_blender" / "run_build.py"),
        (scripts_dir / "Shinano_EternalReunion_Michael" / "generate_er_atlas.py", michael_dir / "3_textures_gtav" / "generate_er_atlas.py"),
        (scripts_dir / "Shinano_EternalReunion_Michael" / "deploy_michael_er.py", michael_dir / "5_rpf_package" / "deploy_michael_er.py"),
        (scripts_dir / "Miltina_Maid_Trevor" / "build_trevor_miltina.py", trevor_dir / "2_blender" / "build_trevor_miltina.py"),
        (scripts_dir / "Miltina_Maid_Trevor" / "run_pipeline.py", trevor_dir / "2_blender" / "run_pipeline.py"),
        (scripts_dir / "Miltina_Maid_Trevor" / "generate_miltina_atlas.py", trevor_dir / "3_textures_gtav" / "generate_miltina_atlas.py"),
        (scripts_dir / "Miltina_Maid_Trevor" / "apply_miltina_to_trevor.py", trevor_dir / "5_rpf_package" / "apply_miltina_to_trevor.py"),
    ]

    mirrors_in_sync = True
    for primary_file, mirror_file in mirror_pairs:
        is_synced = (
            primary_file.exists()
            and mirror_file.exists()
            and filecmp.cmp(primary_file, mirror_file, shallow=False)
        )
        if not is_synced:
            mirrors_in_sync &= print_status_result(
                f"Espelho dessincronizado: {mirror_file.relative_to(root_dir)}",
                False,
                f"deve igualar {primary_file.relative_to(root_dir)}",
            )

    quality_passed &= print_status_result(
        "Sincronizacao de Espelhos",
        mirrors_in_sync,
        f"{len(mirror_pairs)} pares verificados",
    )
    return quality_passed


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
        ("Qualidade e Espelhos", test_code_quality_and_mirror_sync()),
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
