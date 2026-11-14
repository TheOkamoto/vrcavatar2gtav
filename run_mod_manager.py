#!/usr/bin/env python3
"""
run_mod_manager.py
==================
Script Mestre Orquestrador para Gestao e Implantação de Avatares VRChat no GTA V.

Permite selecionar interativamente ou via linha de comando qual personagem
atualizar (Michael, Franklin, Trevor ou Todos), controlando cada etapa do pipeline:
  1. Geracao do Texture Atlas (2K DXT5) e dicionarios .ytd
  2. Compilacao e rigging dos modelos 3D no Blender (Sollumz .ydd)
  3. Substituicao universal de slots e instalacao de dummies (apply_characters)
  4. Repacotamento e patch de RPFs no GTA V (repack_and_deploy_everything)

Regras de Implementacao:
  - Zero variaveis de uma ou duas letras.
  - Zero emojis (mensagens formatadas com marcadores ASCII padronizados).
  - Tratamento rigoroso de erros e excecoes em todas as etapas.
  - Compatibilidade multiplataforma total (Windows nativo e Linux/WSL).
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Adiciona o diretorio de ferramentas comuns ao sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts" / "common_tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "_deploy_tools"))
try:
    import setup_first_run
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import setup_first_run
    from common_tools import vrc2gtav_paths as project_paths

CONFIG_FILE_PATH = None
PROJECT_ROOT_DIRECTORY = Path(__file__).resolve().parent
SCRIPTS_DIRECTORY = None
BLENDER_EXECUTABLE = ""
RAGE_CLI_TOOL = ""
PYTHON_EXECUTABLE = sys.executable
GTAV_MODS_DIRECTORY = None
UNITY_ASSETS_DIRECTORY = None
APPLY_CHARACTERS_SCRIPT_PATH = None
REPACK_DEPLOY_SCRIPT_PATH = None
MICHAEL_CFG = None
FRANKLIN_CFG = None
TREVOR_CFG = None
CHARACTER_PIPELINE_REGISTRY = {}


def load_runtime_context(force_reload: bool = False) -> None:
    """Carrega configuracoes e caminhos de runtime a partir de vrc2gtav.cfg."""
    global CONFIG_FILE_PATH
    global PROJECT_ROOT_DIRECTORY
    global SCRIPTS_DIRECTORY
    global BLENDER_EXECUTABLE
    global RAGE_CLI_TOOL
    global PYTHON_EXECUTABLE
    global GTAV_MODS_DIRECTORY
    global UNITY_ASSETS_DIRECTORY
    global APPLY_CHARACTERS_SCRIPT_PATH
    global REPACK_DEPLOY_SCRIPT_PATH
    global MICHAEL_CFG
    global FRANKLIN_CFG
    global TREVOR_CFG
    global CHARACTER_PIPELINE_REGISTRY

    if force_reload:
        project_paths.invalidate_config_cache()

    CONFIG_FILE_PATH = project_paths.find_project_config_file()
    PROJECT_ROOT_DIRECTORY = project_paths.get_project_root()
    SCRIPTS_DIRECTORY = project_paths.get_scripts_root_dir()
    BLENDER_EXECUTABLE = project_paths.get_blender_exe()
    RAGE_CLI_TOOL = project_paths.get_rage_cli()
    PYTHON_EXECUTABLE = project_paths.get_python_exe()
    GTAV_MODS_DIRECTORY = project_paths.get_gtav_mods_dir()
    UNITY_ASSETS_DIRECTORY = project_paths.get_vrc_assets_dir()

    APPLY_CHARACTERS_SCRIPT_PATH = project_paths.get_config_path(
        "common_assets", "apply_characters_script"
    )
    REPACK_DEPLOY_SCRIPT_PATH = project_paths.get_config_path(
        "common_assets", "repack_deploy_script"
    )

    MICHAEL_CFG = project_paths.get_character_paths("michael")
    FRANKLIN_CFG = project_paths.get_character_paths("franklin")
    TREVOR_CFG = project_paths.get_character_paths("trevor")

    CHARACTER_PIPELINE_REGISTRY = {
        "michael": {
            "character_key": str(MICHAEL_CFG["ped_name"]),
            "display_name": "Michael De Santa -> Shinano Eternal Reunion",
            "folder_name": MICHAEL_CFG["character_dir"].name,
            "texture_script": MICHAEL_CFG["atlas_script"],
            "blender_script": MICHAEL_CFG["blender_script"],
        },
        "franklin": {
            "character_key": str(FRANKLIN_CFG["ped_name"]),
            "display_name": "Franklin Clinton -> Shinano Casual",
            "folder_name": FRANKLIN_CFG["character_dir"].name,
            "texture_script": FRANKLIN_CFG["atlas_script"],
            "blender_script": FRANKLIN_CFG["blender_script"],
        },
        "trevor": {
            "character_key": str(TREVOR_CFG["ped_name"]),
            "display_name": "Trevor Philips -> Miltina Maid",
            "folder_name": TREVOR_CFG["character_dir"].name,
            "texture_script": TREVOR_CFG["atlas_script"],
            "blender_script": TREVOR_CFG["blender_script"],
        },
    }


def print_section_header(section_title: str):
    """Exibe um cabecalho formatado em ASCII sem emojis."""
    separator_line = "=" * 70
    print(f"\n{separator_line}")
    print(f"  {section_title}")
    print(f"{separator_line}\n")


def execute_subcommand(
    command_arguments: list,
    task_description: str,
    custom_environment: dict = None,
) -> bool:
    """
    Executa comandos do sistema de forma segura, transmitindo saida em tempo real
    e tratando excecoes e codigos de saida com logs detalhados.
    """
    print(f"[INICIANDO] {task_description}...")
    start_timestamp = time.time()
    captured_output_lines = []

    try:
        process_execution = subprocess.Popen(
            command_arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            env=custom_environment,
        )

        for raw_output_line in process_execution.stdout:
            stripped_line = raw_output_line.rstrip()
            if not stripped_line:
                continue
            captured_output_lines.append(stripped_line)

            # Transmite em tempo real linhas relevantes contendo marcadores de status
            if any(
                status_marker in stripped_line
                for status_marker in [
                    "[OK]",
                    "[INFO]",
                    "[SUCESSO]",
                    "[AVISO]",
                    "[ERRO]",
                    "[ETAPA",
                    "[PROGRESSO]",
                    "[RPF7 PATCH]",
                    "[VERIFICACAO",
                    "Exported",
                    "Saved",
                    "vertices",
                    "Repacotando",
                    "Patching",
                    "Copiando",
                    "Substituindo",
                    "Compilando",
                ]
            ):
                print(f"    {stripped_line}")

        process_execution.wait()
        elapsed_seconds = time.time() - start_timestamp

        if process_execution.returncode != 0:
            print(
                f"[FALHA] {task_description} falhou apos {elapsed_seconds:.1f}s "
                f"com codigo de retorno {process_execution.returncode}."
            )
            print("--- ULTIMAS LINHAS DA SAIDA ---")
            for recent_line in captured_output_lines[-20:]:
                print(f"    {recent_line}")
            return False

        print(f"[CONCLUIDO] {task_description} em {elapsed_seconds:.1f}s.")
        return True

    except Exception as unexpected_error:
        print(f"[ERRO INESPERADO] {task_description}: {unexpected_error}")
        return False


def verify_system_prerequisites() -> bool:
    """
    Verifica a existencia de ferramentas e diretorios fundamentais antes de iniciar.
    """
    print_section_header("VERIFICACAO DE PRE-REQUISITOS DO SISTEMA")
    verification_passed = True

    print(f"[OK] Configuracao .cfg carregada: {CONFIG_FILE_PATH}")

    # 1. Python e bibliotecas essenciais (via executavel configurado em vrc2gtav.cfg)
    print(f"[OK] Python configurado: {PYTHON_EXECUTABLE}")
    try:
        dep_check = subprocess.run(
            [PYTHON_EXECUTABLE, "-c", "import PIL, numpy"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if dep_check.returncode == 0:
            print("[OK] Bibliotecas Python (Pillow, NumPy) instaladas e funcionais.")
        else:
            print(
                f"[ERRO] Bibliotecas Python ausentes em {PYTHON_EXECUTABLE}: "
                f"{dep_check.stderr.strip()}"
            )
            verification_passed = False
    except Exception as python_check_error:
        print(f"[ERRO] Falha ao validar ambiente Python ({PYTHON_EXECUTABLE}): {python_check_error}")
        verification_passed = False

    # 2. Executavel do Blender
    if Path(BLENDER_EXECUTABLE).exists() or shutil.which(BLENDER_EXECUTABLE):
        print(f"[OK] Executavel do Blender localizado: {BLENDER_EXECUTABLE}")
    else:
        print(f"[AVISO] Blender nao encontrado em '{BLENDER_EXECUTABLE}'. Ajuste [executables] -> blender em vrc2gtav.cfg.")

    # 3. RAGE CLI Tool
    if Path(RAGE_CLI_TOOL).exists() or shutil.which(RAGE_CLI_TOOL):
        print(f"[OK] RAGE CLI localizado: {RAGE_CLI_TOOL}")
    else:
        print(f"[ERRO] RAGE CLI nao encontrado em '{RAGE_CLI_TOOL}'. Ajuste [executables] -> rage em vrc2gtav.cfg.")
        verification_passed = False

    # 4. Assets do Unity (waifuv4)
    if UNITY_ASSETS_DIRECTORY.exists():
        print(f"[OK] Pasta de Assets Unity localizada: {UNITY_ASSETS_DIRECTORY}")
    else:
        print(f"[AVISO] Pasta de Assets Unity nao encontrada: {UNITY_ASSETS_DIRECTORY}")

    # 5. Destino de Mods do GTA V
    if GTAV_MODS_DIRECTORY.exists():
        print(f"[OK] Pasta de mods do GTA V localizada: {GTAV_MODS_DIRECTORY}")
    else:
        print(f"[AVISO] Pasta de mods do GTA V nao encontrada: {GTAV_MODS_DIRECTORY}")

    # 6. Dummy meshes (ped e props de oculos)
    dummy_ydd_path = project_paths.get_dummy_ydd_path()
    prop_dummy_ydd_path = project_paths.get_prop_dummy_ydd_path()
    if dummy_ydd_path.is_file():
        print(f"[OK] Dummy YDD localizado: {dummy_ydd_path}")
    else:
        print(f"[ERRO] Dummy YDD nao encontrado: {dummy_ydd_path}")
        verification_passed = False

    if prop_dummy_ydd_path.is_file():
        print(f"[OK] Prop Dummy YDD localizado: {prop_dummy_ydd_path}")
    else:
        print(f"[ERRO] Prop Dummy YDD nao encontrado: {prop_dummy_ydd_path}")
        verification_passed = False

    return verification_passed


def execute_texture_generation(selected_character_keys: list) -> bool:
    """Gera os texture atlases para os personagens selecionados."""
    print_section_header("ETAPA 1: GERACAO DE TEXTURE ATLAS (2K DXT5)")
    for character_key in selected_character_keys:
        character_data = CHARACTER_PIPELINE_REGISTRY[character_key]
        script_path = character_data["texture_script"]

        if not script_path.exists():
            print(f"[ERRO] Script de textura nao encontrado: {script_path}")
            return False

        command_list = [PYTHON_EXECUTABLE, str(script_path)]
        task_label = f"Gerando Atlas de Textura para {character_data['display_name']}"
        success_status = execute_subcommand(command_list, task_label)
        if not success_status:
            return False

    return True


def execute_blender_build(selected_character_keys: list) -> bool:
    """Compila os modelos 3D no Blender para os personagens selecionados."""
    print_section_header("ETAPA 2: COMPILACAO DE MODELOS NO BLENDER (SOLLUMZ)")

    for character_key in selected_character_keys:
        project_paths.ensure_character_skeleton_yft(character_key)
        character_data = CHARACTER_PIPELINE_REGISTRY[character_key]
        script_path = character_data["blender_script"]

        if not script_path.exists():
            print(f"[ERRO] Script Blender nao encontrado: {script_path}")
            return False

        blender_command_list, blender_env = project_paths.build_blender_command(
            script_path
        )
        task_label = f"Compilando Modelo 3D para {character_data['display_name']}"
        success_status = execute_subcommand(
            blender_command_list,
            task_label,
            custom_environment=blender_env,
        )
        if not success_status:
            return False

    return True


def execute_character_slot_patching(selected_character_keys: list) -> bool:
    """Aplica as malhas compiladas e os dummies invisiveis nos slots do GTA V."""
    print_section_header("ETAPA 3: APLICACAO UNIVERSAL DE SLOTS (ANTI-CLIPPING)")
    apply_script_path = APPLY_CHARACTERS_SCRIPT_PATH

    if not apply_script_path.exists():
        apply_script_path = (
            PROJECT_ROOT_DIRECTORY / "_deploy_tools" / "apply_characters.py"
        )

    if not apply_script_path.exists():
        print(f"[ERRO] Script apply_characters.py nao encontrado: {apply_script_path}")
        return False

    # Mapeia chaves para os identificadores internos do jogo (player_zero, etc.)
    ped_identifiers_list = [
        CHARACTER_PIPELINE_REGISTRY[character_key]["character_key"]
        for character_key in selected_character_keys
    ]

    for ped_identifier in ped_identifiers_list:
        command_list = [
            PYTHON_EXECUTABLE,
            str(apply_script_path),
            "--character",
            ped_identifier,
        ]
        task_label = f"Substituindo slots para o personagem {ped_identifier}"
        success_status = execute_subcommand(command_list, task_label)
        if not success_status:
            return False

    return True


def execute_rpf_repack_and_deploy() -> bool:
    """Repacota os arquivos RPF com cabecalho OPEN e instala no GTA V."""
    print_section_header("ETAPA 4: REPACOTAMENTO RPF E DEPLOY NO GTA V")
    repack_script_path = REPACK_DEPLOY_SCRIPT_PATH
    if not repack_script_path.exists():
        repack_script_path = (
            PROJECT_ROOT_DIRECTORY / "_deploy_tools" / "repack_and_deploy_everything.py"
        )

    if not repack_script_path.exists():
        print(
            f"[ERRO] Script repack_and_deploy_everything.py nao encontrado: {repack_script_path}"
        )
        return False

    command_list = [PYTHON_EXECUTABLE, str(repack_script_path)]
    task_label = "Repacotando RPFs e Instalando no Jogo"
    return execute_subcommand(command_list, task_label)


def run_interactive_menu():
    """Exibe o menu interativo e solicita a escolha do usuario."""
    if setup_first_run.is_first_run_needed():
        print_section_header("PRIMEIRA EXECUCAO DETECTADA (FIRST-RUN SETUP)")
        print(
            "  Falta configurar o arquivo local vrc2gtav.cfg ou extrair os arquivos\n"
            "  base vanilla do seu GTA V para staging/ e 2_blender/."
        )
        start_setup_answer = (
            input("Deseja executar o Setup Inicial agora? (s/n) [padrao: s]: ")
            .strip()
            .lower()
        )
        if start_setup_answer != "n":
            setup_ok = setup_first_run.run_first_run_setup(interactive=True)
            if not setup_ok:
                print("\n[ERRO] Setup inicial incompleto. Corrija os caminhos e tente novamente.")
                sys.exit(1)
            load_runtime_context(force_reload=True)

    separator_banner = "=" * 70
    print(f"\n{separator_banner}")
    print("         GERENCIADOR DE AVATARES VRChat PARA GTA V")
    print(f"{separator_banner}")
    print("Selecione qual personagem voce deseja trocar/atualizar:")
    print("  [1] Michael (player_zero) -> Shinano Eternal Reunion")
    print("  [2] Franklin (player_one) -> Shinano Casual / Uniforme")
    print("  [3] Trevor   (player_two)  -> Miltina Maid")
    print("  [4] Todos os 3 Personagens (Processo Completo)")
    print("  [5] Apenas Repacotar e Instalar RPFs no GTA V (Deploy Only)")
    print("  [6] Configuracao Inicial e Extracao GTA V (First-Run Setup)")
    print("  [0] Sair")
    print(f"{'-' * 70}")

    user_menu_choice = input("Digite a opcao desejada [0-6]: ").strip()

    if user_menu_choice == "0":
        print("[INFO] Operacao cancelada pelo usuario.")
        sys.exit(0)

    if user_menu_choice == "6":
        setup_ok = setup_first_run.run_first_run_setup(interactive=True)
        sys.exit(0 if setup_ok else 1)

    if user_menu_choice == "5":
        load_runtime_context(force_reload=True)
        execute_rpf_repack_and_deploy()
        sys.exit(0)

    if not project_paths.has_project_config_file():
        print("[ERRO] Arquivo vrc2gtav.cfg nao existe. Execute a opcao [6] primeiro.")
        sys.exit(1)
    load_runtime_context(force_reload=True)

    choice_to_characters_mapping = {
        "1": ["michael"],
        "2": ["franklin"],
        "3": ["trevor"],
        "4": ["michael", "franklin", "trevor"],
    }

    if user_menu_choice not in choice_to_characters_mapping:
        print("[ERRO] Opcao invalida informada.")
        sys.exit(1)

    selected_characters_list = choice_to_characters_mapping[user_menu_choice]

    print("\nConfiguracao das etapas a serem executadas:")
    prompt_build_textures = input("Deseja gerar os Texture Atlases (2K)? (s/n) [padrao: s]: ").strip().lower()
    should_build_textures = prompt_build_textures != "n"

    prompt_build_blender = input("Deseja compilar os modelos no Blender? (s/n) [padrao: s]: ").strip().lower()
    should_build_blender = prompt_build_blender != "n"

    prompt_apply_and_deploy = input("Deseja aplicar nos slots e instalar no GTA V? (s/n) [padrao: s]: ").strip().lower()
    should_apply_and_deploy = prompt_apply_and_deploy != "n"

    # Executa o pipeline configurado
    if should_build_textures:
        textures_success = execute_texture_generation(selected_characters_list)
        if not textures_success:
            print("\n[ERRO] Abortando pipeline devido a erro na geracao de texturas.")
            sys.exit(1)

    if should_build_blender:
        blender_success = execute_blender_build(selected_characters_list)
        if not blender_success:
            print("\n[ERRO] Abortando pipeline devido a erro na compilacao do Blender.")
            sys.exit(1)

    if should_apply_and_deploy:
        patch_success = execute_character_slot_patching(selected_characters_list)
        if not patch_success:
            print("\n[ERRO] Abortando pipeline devido a erro na aplicacao de slots.")
            sys.exit(1)

        deploy_success = execute_rpf_repack_and_deploy()
        if not deploy_success:
            print("\n[ERRO] Abortando pipeline devido a erro no repacotamento de RPFs.")
            sys.exit(1)

    print_section_header("PIPELINE CONCLUIDO COM TOTAL SUCESSO")
    print("Os avatares estao prontos e instalados no seu GTA V.")


def main():
    argument_parser = argparse.ArgumentParser(
        description="Gerenciador Mestre de Avatares VRChat para GTA V"
    )
    argument_parser.add_argument(
        "--character",
        choices=["michael", "franklin", "trevor", "all"],
        default=None,
        help="Personagem a processar (se omitido, abre o menu interativo)",
    )
    argument_parser.add_argument(
        "--skip-textures",
        action="store_true",
        help="Pula a etapa de geracao de texture atlas",
    )
    argument_parser.add_argument(
        "--skip-blender",
        action="store_true",
        help="Pula a etapa de compilacao no Blender",
    )
    argument_parser.add_argument(
        "--skip-deploy",
        action="store_true",
        help="Pula a etapa de aplicacao nos slots e repacotamento de RPFs",
    )
    argument_parser.add_argument(
        "--deploy-only",
        action="store_true",
        help="Executa apenas a aplicacao e o repacotamento final",
    )
    argument_parser.add_argument(
        "--check-env",
        action="store_true",
        help="Apenas verifica os pre-requisitos do sistema e encerra",
    )
    argument_parser.add_argument(
        "--setup",
        action="store_true",
        help="Executa o configurador First-Run e extrai RPFs vanilla do GTA V",
    )
    argument_parser.add_argument(
        "--force-setup",
        action="store_true",
        help="Forca re-extracao dos RPFs vanilla durante o setup",
    )
    argument_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Executa --setup sem perguntas interativas",
    )
    argument_parser.add_argument("--gtav-root", default=None, help="Pasta raiz do GTA V Legacy")
    argument_parser.add_argument("--unity-assets", default=None, help="Pasta Assets do Unity/VRChat")
    argument_parser.add_argument("--blender", default=None, help="Executavel do Blender")
    argument_parser.add_argument("--rage", default=None, help="Executavel RAGE CLI (rage)")

    parsed_arguments = argument_parser.parse_args()

    # Setup inicial explicito (First-Run)
    if parsed_arguments.setup:
        setup_ok = setup_first_run.run_first_run_setup(
            interactive=not parsed_arguments.non_interactive,
            force_reextract=parsed_arguments.force_setup,
            gtav_root_override=parsed_arguments.gtav_root,
            unity_assets_override=parsed_arguments.unity_assets,
            blender_override=parsed_arguments.blender,
            rage_override=parsed_arguments.rage,
        )
        if not setup_ok:
            sys.exit(1)
        if (
            parsed_arguments.character is None
            and not parsed_arguments.deploy_only
            and not parsed_arguments.check_env
        ):
            sys.exit(0)

    # Modo Interativo (quando nenhum personagem eh passado via CLI)
    if (
        parsed_arguments.character is None
        and not parsed_arguments.deploy_only
        and not parsed_arguments.check_env
    ):
        run_interactive_menu()
        sys.exit(0)

    if not project_paths.has_project_config_file() or setup_first_run.is_first_run_needed():
        print("[INFO] Ambiente inicial incompleto detectado; executando setup automatico...")
        setup_ok = setup_first_run.run_first_run_setup(
            interactive=False,
            force_reextract=False,
            gtav_root_override=parsed_arguments.gtav_root,
            unity_assets_override=parsed_arguments.unity_assets,
            blender_override=parsed_arguments.blender,
            rage_override=parsed_arguments.rage,
        )
        if not setup_ok:
            print(
                "[ERRO] Nao foi possivel concluir o First-Run automaticamente. "
                "Execute `python run_mod_manager.py --setup` para configurar."
            )
            sys.exit(1)

    load_runtime_context(force_reload=True)

    # Se solicitada apenas a verificacao do ambiente
    if parsed_arguments.check_env:
        prerequisites_valid = verify_system_prerequisites()
        setup_first_run.print_setup_diagnostics()
        sys.exit(0 if prerequisites_valid else 1)

    # Modo Apenas Deploy
    if parsed_arguments.deploy_only:
        execute_rpf_repack_and_deploy()
        sys.exit(0)

    # Modo Linha de Comando (CLI automatizado)
    if parsed_arguments.character == "all":
        selected_characters_list = ["michael", "franklin", "trevor"]
    else:
        selected_characters_list = [parsed_arguments.character]

    verify_system_prerequisites()

    if not parsed_arguments.skip_textures:
        textures_status = execute_texture_generation(selected_characters_list)
        if not textures_status:
            sys.exit(1)

    if not parsed_arguments.skip_blender:
        blender_status = execute_blender_build(selected_characters_list)
        if not blender_status:
            sys.exit(1)

    if not parsed_arguments.skip_deploy:
        patch_status = execute_character_slot_patching(selected_characters_list)
        if not patch_status:
            sys.exit(1)

        repack_status = execute_rpf_repack_and_deploy()
        if not repack_status:
            sys.exit(1)

    print_section_header("PIPELINE AUTOMATIZADO CONCLUIDO COM SUCESSO")


if __name__ == "__main__":
    main()
