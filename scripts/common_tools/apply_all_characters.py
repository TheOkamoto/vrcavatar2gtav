#!/usr/bin/env python3
"""
apply_all_characters.py
=======================
Aplica a Substituição Universal de Slots (Universal Slot Replacement) para os
três protagonistas do Grand Theft Auto V de uma só vez:
  1. Michael (player_zero) -> Shinano Eternal Reunion
  2. Franklin (player_one) -> Shinano Casual / Uniforme
  3. Trevor   (player_two)  -> Miltina Maid

Multiplataforma: roda tanto no Windows nativo quanto no Linux/WSL sem caminhos fixos.
"""

import os
import shutil
import sys
from pathlib import Path

# Adiciona o diretório atual ao sys.path para importar vrc2gtav_paths
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import vrc2gtav_paths as paths
except ImportError:
    from common_tools import vrc2gtav_paths as paths

ROOT = paths.get_project_root()
STAGING = paths.get_staging_dir()
DUMMY_YDD_PATH = paths.get_dummy_ydd_path()

RPF_PATHS_CFG = paths.get_rpf_paths()
MICHAEL_CFG = paths.get_character_paths("michael")
FRANKLIN_CFG = paths.get_character_paths("franklin")
TREVOR_CFG = paths.get_character_paths("trevor")

# Configuracoes de cada personagem via vrc2gtav.cfg
CHARACTERS = {
    str(MICHAEL_CFG["ped_name"]): {
        "name": "Michael De Santa -> Shinano Eternal Reunion",
        "model_ydd": MICHAEL_CFG["target_model_ydd"],
        "texture_ytd": MICHAEL_CFG["ytd_file"],
    },
    str(FRANKLIN_CFG["ped_name"]): {
        "name": "Franklin Clinton -> Shinano Casual",
        "model_ydd": FRANKLIN_CFG["target_model_ydd"],
        "texture_ytd": FRANKLIN_CFG["ytd_file"],
    },
    str(TREVOR_CFG["ped_name"]): {
        "name": "Trevor Philips -> Miltina Maid",
        "model_ydd": TREVOR_CFG["target_model_ydd"],
        "texture_ytd": TREVOR_CFG["ytd_file"],
    },
}

TARGET_DIRS = [
    RPF_PATHS_CFG["mppatches_extracted"],
    RPF_PATHS_CFG["streamedpeds_extracted"],
    RPF_PATHS_CFG["patchday4ng_models_extracted"],
]

def patch_character_in_dir(char_id, config, ped_dir):
    if not ped_dir.is_dir():
        return

    model_src = config["model_ydd"]
    tex_src = config["texture_ytd"]

    uppr_count = 0
    ytd_count = 0
    dummy_count = 0
    skipped_count = 0

    all_files = sorted(os.listdir(ped_dir))
    for filename in all_files:
        filepath = ped_dir / filename
        if not filepath.is_file():
            continue

        prefix = filename.split("_")[0].lower()
        ext = filepath.suffix.lower()

        if prefix == "uppr" and ext == ".ydd":
            shutil.copyfile(model_src, filepath)
            uppr_count += 1
        elif prefix == "uppr" and "diff" in filename and ext == ".ytd":
            shutil.copyfile(tex_src, filepath)
            ytd_count += 1
        elif ext == ".ydd" and prefix in [
            "accs", "berd", "decl", "feet", "hair",
            "hand", "head", "jbib", "lowr", "task", "teef"
        ]:
            shutil.copyfile(DUMMY_YDD_PATH, filepath)
            dummy_count += 1
        else:
            skipped_count += 1

    print(f"  [{char_id}] {ped_dir.parent.name}/{char_id}:")
    print(f"      Modelos uppr substituídos:     {uppr_count}")
    print(f"      Dicionários de textura (.ytd): {ytd_count}")
    print(f"      Dummies instalados (629 B):    {dummy_count}")
    print(f"      Arquivos intocados:            {skipped_count}")

def main():
    print("=== APLICADOR UNIVERSAL DE AVATARES GTA V ===")
    print(f"Raiz do Projeto: {ROOT}")
    print(f"Staging RPF:     {STAGING}")
    
    if not DUMMY_YDD_PATH.exists():
        print(f"[ERRO] Dummy YDD não encontrado em: {DUMMY_YDD_PATH}")
        sys.exit(1)

    for char_id, config in CHARACTERS.items():
        print(f"\n--- Aplicando {config['name']} ({char_id}) ---")
        if not config["model_ydd"].exists():
            print(f"[ERRO] Modelo YDD não encontrado: {config['model_ydd']}")
            sys.exit(1)
        if not config["texture_ytd"].exists():
            print(f"[ERRO] Textura YTD não encontrada: {config['texture_ytd']}")
            sys.exit(1)

        for base_dir in TARGET_DIRS:
            ped_dir = base_dir / char_id
            patch_character_in_dir(char_id, config, ped_dir)

    print("\n[SUCESSO] Todos os 3 personagens foram aplicados com sucesso nos diretórios de staging!")
    print("Execute 'python3 repack_and_deploy_everything.py' para gerar os arquivos RPF e instalar no jogo.")

if __name__ == "__main__":
    main()
