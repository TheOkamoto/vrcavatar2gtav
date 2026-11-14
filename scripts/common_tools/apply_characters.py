#!/usr/bin/env python3
"""
apply_characters.py
===================
Aplica a Substituicao Universal de Slots (Universal Slot Replacement) para os
protagonistas do Grand Theft Auto V:
  - Michael De Santa (player_zero) -> Shinano Eternal Reunion
  - Franklin Clinton (player_one)  -> Shinano Casual / Uniforme
  - Trevor Philips   (player_two)  -> Miltina Maid

Suporta selecao de personagem individual ou todos simultaneamente.
Substitui todas as malhas de tronco (uppr) pelo modelo completo da waifu,
todas as texturas (uppr_diff) pelo atlas 2K correspondente, e todas as outras
partes do corpo humano (cabeca, cabelo, barba, pernas, pes, maos, acessorios)
por drawables dummy invisiveis (head_000_r.ydd de 629 bytes), eliminando
completamente clipping e sobreposicao de partes dos personagens vanilla.
Tambem substitui todos os oculos dos protagonistas (p_eyes_*.ydd em
streamedpedprops.rpf) pelo prop dummy rigido (p_eyes_dummy.ydd de 515 bytes).

Regras de Implementacao:
  - Zero variaveis de uma ou duas letras.
  - Zero emojis (mensagens formatadas com marcadores ASCII padronizados).
  - Tratamento rigoroso de erros e excecoes.
  - Multiplataforma (Windows e Linux/WSL).
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

# Adiciona o diretorio atual ao sys.path para importar vrc2gtav_paths
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import vrc2gtav_paths as project_paths
except ImportError:
    from common_tools import vrc2gtav_paths as project_paths

PROJECT_ROOT_DIRECTORY = project_paths.get_project_root()
STAGING_DIRECTORY = project_paths.get_staging_dir()
DUMMY_YDD_FILE_PATH = project_paths.get_dummy_ydd_path()
PROP_DUMMY_YDD_FILE_PATH = project_paths.get_prop_dummy_ydd_path()

RPF_PATHS_CONFIG = project_paths.get_rpf_paths()
MICHAEL_CONFIG = project_paths.get_character_paths("michael")
FRANKLIN_CONFIG = project_paths.get_character_paths("franklin")
TREVOR_CONFIG = project_paths.get_character_paths("trevor")

# Registro central de configuracao dos personagens disponiveis via vrc2gtav.cfg
CHARACTER_REGISTRY = {
    str(MICHAEL_CONFIG["ped_name"]): {
        "display_name": "Michael De Santa -> Shinano Eternal Reunion",
        "model_ydd_path": MICHAEL_CONFIG["target_model_ydd"],
        "texture_ytd_path": MICHAEL_CONFIG["ytd_file"],
    },
    str(FRANKLIN_CONFIG["ped_name"]): {
        "display_name": "Franklin Clinton -> Shinano Casual",
        "model_ydd_path": FRANKLIN_CONFIG["target_model_ydd"],
        "texture_ytd_path": FRANKLIN_CONFIG["ytd_file"],
    },
    str(TREVOR_CONFIG["ped_name"]): {
        "display_name": "Trevor Philips -> Miltina Maid",
        "model_ydd_path": TREVOR_CONFIG["target_model_ydd"],
        "texture_ytd_path": TREVOR_CONFIG["ytd_file"],
    },
}

STAGING_TARGET_DIRECTORIES = [
    RPF_PATHS_CONFIG["mppatches_extracted"],
    RPF_PATHS_CONFIG["streamedpeds_extracted"],
    RPF_PATHS_CONFIG["patchday4ng_models_extracted"],
]

CHARACTER_PROPS_DIRECTORY_MAP = {
    str(MICHAEL_CONFIG["ped_name"]): MICHAEL_CONFIG["staging_streamed_props_dir"],
    str(FRANKLIN_CONFIG["ped_name"]): FRANKLIN_CONFIG["staging_streamed_props_dir"],
    str(TREVOR_CONFIG["ped_name"]): TREVOR_CONFIG["staging_streamed_props_dir"],
}

VANILLA_BODY_SLOT_PREFIXES = [
    "accs",
    "berd",
    "decl",
    "feet",
    "hair",
    "hand",
    "head",
    "jbib",
    "lowr",
    "task",
    "teef",
]


def patch_single_character_directory(
    character_identifier: str,
    character_configuration: dict,
    target_ped_directory: Path,
) -> dict:
    """
    Substitui os arquivos dentro da pasta extraida do personagem (player_zero, player_one ou player_two).
    """
    if not target_ped_directory.is_dir():
        return {
            "uppr_models": 0,
            "textures": 0,
            "dummies": 0,
            "untouched": 0,
        }

    source_model_path = character_configuration["model_ydd_path"]
    source_texture_path = character_configuration["texture_ytd_path"]

    statistics_counter = {
        "uppr_models": 0,
        "textures": 0,
        "dummies": 0,
        "untouched": 0,
    }

    all_directory_filenames = sorted(os.listdir(target_ped_directory))
    for current_filename in all_directory_filenames:
        target_file_path = target_ped_directory / current_filename
        if not target_file_path.is_file():
            continue

        filename_prefix = current_filename.split("_")[0].lower()
        filename_extension = target_file_path.suffix.lower()

        try:
            if filename_prefix == "uppr" and filename_extension == ".ydd":
                shutil.copyfile(source_model_path, target_file_path)
                statistics_counter["uppr_models"] += 1
            elif (
                filename_prefix == "uppr"
                and "diff" in current_filename
                and filename_extension == ".ytd"
            ):
                shutil.copyfile(source_texture_path, target_file_path)
                statistics_counter["textures"] += 1
            elif (
                filename_extension == ".ydd"
                and filename_prefix in VANILLA_BODY_SLOT_PREFIXES
            ):
                shutil.copyfile(DUMMY_YDD_FILE_PATH, target_file_path)
                statistics_counter["dummies"] += 1
            else:
                statistics_counter["untouched"] += 1
        except Exception as file_copy_exception:
            print(
                f"[ERRO] Falha ao substituir {target_file_path}: {file_copy_exception}"
            )
            raise

    archive_context_name = target_ped_directory.parent.name
    print(f"  [{character_identifier}] {archive_context_name}/{character_identifier}:")
    print(f"      Modelos uppr substituidos:     {statistics_counter['uppr_models']}")
    print(f"      Dicionarios de textura (.ytd): {statistics_counter['textures']}")
    print(f"      Dummies instalados (629 B):    {statistics_counter['dummies']}")
    print(f"      Arquivos intocados:            {statistics_counter['untouched']}")

    return statistics_counter


def apply_selected_characters(characters_to_apply: list) -> bool:
    """
    Executa a aplicacao para a lista de personagens informada.
    """
    print("=== APLICADOR UNIVERSAL DE AVATARES GTA V ===")
    print(f"Raiz do Projeto: {PROJECT_ROOT_DIRECTORY}")
    print(f"Staging RPF:     {STAGING_DIRECTORY}")

    if not DUMMY_YDD_FILE_PATH.exists():
        print(f"[ERRO] Dummy YDD nao encontrado em: {DUMMY_YDD_FILE_PATH}")
        return False

    if not PROP_DUMMY_YDD_FILE_PATH.exists():
        print(f"[ERRO] Prop Dummy YDD nao encontrado em: {PROP_DUMMY_YDD_FILE_PATH}")
        return False

    try:
        project_paths.ensure_streamedpedprops_extracted()
    except Exception as props_extract_error:
        print(f"[ERRO] Falha ao preparar streamedpedprops_extracted: {props_extract_error}")
        return False

    for character_key in characters_to_apply:
        if character_key not in CHARACTER_REGISTRY:
            print(f"[ERRO] Personagem desconhecido: {character_key}")
            return False

        character_data = CHARACTER_REGISTRY[character_key]
        print(f"\n--- Aplicando {character_data['display_name']} ({character_key}) ---")

        if not character_data["model_ydd_path"].exists():
            print(
                f"[ERRO] Modelo YDD nao encontrado: {character_data['model_ydd_path']}"
            )
            return False

        if not character_data["texture_ytd_path"].exists():
            print(
                f"[ERRO] Textura YTD nao encontrada: {character_data['texture_ytd_path']}"
            )
            return False

        for staging_base_path in STAGING_TARGET_DIRECTORIES:
            ped_subfolder_path = staging_base_path / character_key
            patch_single_character_directory(
                character_key, character_data, ped_subfolder_path
            )

        props_subfolder_path = CHARACTER_PROPS_DIRECTORY_MAP.get(character_key)
        if props_subfolder_path is not None:
            project_paths.patch_character_glasses_props(
                props_subfolder_path,
                PROP_DUMMY_YDD_FILE_PATH,
                f"{character_key}_p",
            )

    print("\n[SUCESSO] Personagens aplicados com sucesso nos diretorios de staging!")
    return True


def main():
    argument_parser = argparse.ArgumentParser(
        description="Aplica avatares VRChat nos slots de roupas do GTA V"
    )
    argument_parser.add_argument(
        "--character",
        choices=["player_zero", "player_one", "player_two", "all"],
        default="all",
        help="Personagem a aplicar (player_zero=Michael, player_one=Franklin, player_two=Trevor, all=Todos)",
    )
    parsed_arguments = argument_parser.parse_args()

    if parsed_arguments.character == "all":
        selected_characters_list = ["player_zero", "player_one", "player_two"]
    else:
        selected_characters_list = [parsed_arguments.character]

    operation_success = apply_selected_characters(selected_characters_list)
    if not operation_success:
        sys.exit(1)


if __name__ == "__main__":
    main()
