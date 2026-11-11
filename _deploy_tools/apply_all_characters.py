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
DUMMY_YDD_PATH = ROOT / "_deploy_tools" / "head_000_r.ydd"

# Configurações de cada personagem
CHARACTERS = {
    "player_zero": {
        "name": "Michael De Santa -> Shinano Eternal Reunion",
        "model_ydd": ROOT / "2_Michael_Shinano_EternalReunion" / "4_exported_models" / "uppr_000_u.ydd",
        "texture_ytd": ROOT / "2_Michael_Shinano_EternalReunion" / "3_textures_gtav" / "test_er.ytd",
    },
    "player_one": {
        "name": "Franklin Clinton -> Shinano Casual",
        "model_ydd": ROOT / "1_Franklin_Shinano_Casual" / "4_exported_models" / "uppr_008_u.ydd",
        "texture_ytd": ROOT / "1_Franklin_Shinano_Casual" / "3_textures_gtav" / "shinano_franklin_2k.ytd",
    },
    "player_two": {
        "name": "Trevor Philips -> Miltina Maid",
        "model_ydd": ROOT / "3_Trevor_Miltina_Maid" / "4_exported_models" / "uppr_000_u.ydd",
        "texture_ytd": ROOT / "3_Trevor_Miltina_Maid" / "3_textures_gtav" / "miltina_maid.ytd",
    }
}

TARGET_DIRS = [
    STAGING / "mppatches_extracted",
    STAGING / "streamedpeds_players_extracted"
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
