#!/usr/bin/env python3
"""
deploy_universal_slots_private_ER.py
====================================
Aplica a Substituicao Universal de Slots (Opcao 3) para o Michael (player_zero)
e o Franklin (player_one) no Grand Theft Auto V Legacy:
  1. Todos os slots de tronco (uppr_000 a uppr_031) recebem as respectivas malhas completas:
     - Michael: Shinano Eternal Reunion (uppr_000_u.ydd / uppr_000_r.ydd)
     - Franklin: Shinano Padrao com fixes de rosto (lilToon warm peach + olhos MoonButterfly)
       e maos (dedos consolidados em SKEL_Hand) (uppr_008_u.ydd)
  2. Todos os dicionarios de textura de tronco (uppr_diff_000 a uppr_diff_031) sao atualizados:
     - Michael: test_er.ytd (Atlas 4x2)
     - Franklin: shinano_franklin_2k.ytd (Atlas 2x2)
  3. Todos os slots humanos restantes (lowr, feet, head, hair, berd, teef, hand, accs, decl, task, jbib)
     sao convertidos em drawables dummy (invisiveis de 1 KB).
  4. Atualiza os DLCs mppatchesng e patchday3ng com as devidas malhas e dummies.
  5. Aplica a correcao binaria de TOC (file_size = 0 para RPFs aninhados) para evitar ERR_GEN_ZLIB_2.
  6. Valida a integridade estrita com rage verify.
"""

import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

_CURRENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CURRENT_DIR.parent.parent
for _tools_dir in (_REPO_ROOT / "scripts" / "common_tools", _REPO_ROOT / "_deploy_tools"):
    if _tools_dir.is_dir() and str(_tools_dir) not in sys.path:
        sys.path.insert(0, str(_tools_dir))

import vrc2gtav_paths as project_paths

MICHAEL_CFG = project_paths.get_character_paths("michael")
FRANKLIN_CFG = project_paths.get_character_paths("franklin")
RPF_PATHS_CFG = project_paths.get_rpf_paths()
STAGING_DIR = project_paths.get_staging_dir()

RAGE_TOOL_PATH = str(project_paths.get_rage_cli())
DUMMY_SOURCE_PATH = str(project_paths.get_dummy_ydd_path())
PROP_DUMMY_SOURCE_PATH = str(project_paths.get_prop_dummy_ydd_path())

# Fontes do Michael (player_zero)
MICHAEL_ER_DIR = str(MICHAEL_CFG["character_dir"])
MICHAEL_UPPR_U = str(MICHAEL_CFG["target_model_ydd"])
MICHAEL_UPPR_R = str(MICHAEL_CFG["extra_model_ydds"][0])
MICHAEL_YTD = str(MICHAEL_CFG["ytd_file"])

# Fontes do Franklin (player_one)
FRANKLIN_DIR = str(FRANKLIN_CFG["character_dir"])
FRANKLIN_UPPR_U = str(FRANKLIN_CFG["target_model_ydd"])
FRANKLIN_YTD = str(FRANKLIN_CFG["ytd_file"])

# Diretorios de trabalho em streamedpeds_players e streamedpedprops
STREAMED_BASE_DIR = str(RPF_PATHS_CFG["streamedpeds_extracted"])
PLAYER_ZERO_DIR = str(MICHAEL_CFG["staging_streamed_ped_dir"])
PLAYER_ONE_DIR = str(FRANKLIN_CFG["staging_streamed_ped_dir"])
STREAMEDPROPS_BASE_DIR = str(RPF_PATHS_CFG["streamedpedprops_extracted"])
PLAYER_ZERO_PROPS_DIR = str(MICHAEL_CFG["staging_streamed_props_dir"])
PLAYER_ONE_PROPS_DIR = str(FRANKLIN_CFG["staging_streamed_props_dir"])

# Arquivos RPF do x64v
STREAMED_TARGET_RPF = str(STAGING_DIR / "streamedpeds_players_shinano.rpf")
STREAMEDPROPS_TARGET_RPF = str(STAGING_DIR / "streamedpedprops_shinano.rpf")
X64V_EXTRACTED_DIR = str(RPF_PATHS_CFG["x64v_extracted"])
X64V_MODDED_RPF = str(RPF_PATHS_CFG["x64v_modded_rpf"])
GTAV_MODS_X64V_RPF = str(RPF_PATHS_CFG["x64v_game_rpf"])

# Diretorios e arquivos do DLC mppatchesng
STAGING_MPPATCHES_SEED = str(RPF_PATHS_CFG["mppatches_extracted"])
STAGING_MPPATCHESNG_SEED = str(RPF_PATHS_CFG["mppatches_dlc_extracted"])
MPPATCHES_WORK_DIR = os.path.join(MICHAEL_ER_DIR, "5_rpf_package", "mppatches_work")
MPPATCHES_EXTRACTED_DIR = os.path.join(MPPATCHES_WORK_DIR, "mppatches_extracted")
MPPATCHESNG_EXTRACTED_DIR = os.path.join(MPPATCHES_WORK_DIR, "mppatchesng_extracted")
MPPATCHES_TARGET_RPF = os.path.join(MPPATCHES_WORK_DIR, "mppatches.rpf")
MPPATCHESNG_TARGET_RPF = os.path.join(MPPATCHES_WORK_DIR, "mppatchesng_dlc.rpf")
GTAV_MODS_MPPATCHESNG_DLC_RPF = str(RPF_PATHS_CFG["mppatches_game_rpf"])

# Diretorios e arquivos do DLC patchday3ng
PATCHDAY3_WORK_DIR = os.path.join(FRANKLIN_DIR, "5_rpf_package", "patchday3_work")
PATCHDAY3_EXTRACTED_DIR = os.path.join(PATCHDAY3_WORK_DIR, "patchday3_extracted")
PATCHDAY3NG_EXTRACTED_DIR = os.path.join(PATCHDAY3_WORK_DIR, "patchday3ng_extracted")
PATCHDAY3_TARGET_RPF = os.path.join(PATCHDAY3_WORK_DIR, "patchday3ng.rpf")
PATCHDAY3NG_TARGET_RPF = os.path.join(PATCHDAY3_WORK_DIR, "patchday3ng_dlc.rpf")
GTAV_MODS_PATCHDAY3NG_DLC_RPF = str(RPF_PATHS_CFG["patchday3ng_game_rpf"])


def execute_shell_task(command_arguments, task_description):
    """Executa comando com tratamento estrito de erros."""
    print(f"[TAREFA] {task_description}...")
    completed_process = subprocess.run(
        command_arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed_process.returncode != 0:
        print(f"[ERRO] Falha ao executar: {' '.join(command_arguments)}")
        print(f"Stdout:\n{completed_process.stdout}")
        print(f"Stderr:\n{completed_process.stderr}")
        raise RuntimeError(f"Erro na execucao: {task_description}")
    print(f"[OK] {task_description} concluido com sucesso.")
    return completed_process.stdout


def patch_rpf_table_of_contents(rpf_archive_path):
    """
    Corrige o TOC de arquivos RPF aninhados definindo file_size = 0.
    Isto e mandatorio na RAGE Engine para evitar ERR_GEN_ZLIB_2.
    """
    print(f"[INFO] Aplicando correcao binaria no TOC de: {rpf_archive_path}")
    with open(rpf_archive_path, "r+b") as file_stream:
        magic_number, entry_count, names_byte_len, encryption_code = struct.unpack(
            "<IIII", file_stream.read(16)
        )
        table_bytes = file_stream.read(entry_count * 16)
        names_bytes = file_stream.read(names_byte_len)
        patched_entries_counter = 0

        for entry_idx in range(entry_count):
            entry_chunk = bytearray(table_bytes[entry_idx * 16 : (entry_idx + 1) * 16])
            header_flag = struct.unpack("<I", entry_chunk[4:8])[0]
            if header_flag == 0x7FFFFF00 or (header_flag & 0x80000000) != 0:
                continue

            file_size_val = entry_chunk[2] | (entry_chunk[3] << 8) | (entry_chunk[4] << 16)
            if file_size_val != 0:
                entry_chunk[2] = 0
                entry_chunk[3] = 0
                entry_chunk[4] = 0
                file_stream.seek(16 + entry_idx * 16)
                file_stream.write(entry_chunk)
                patched_entries_counter += 1

    print(f"[INFO] {patched_entries_counter} entradas de arquivos RPF aninhados corrigidas no TOC.")


def apply_universal_slots_to_ped(ped_directory, source_uppr_u, source_uppr_r, source_ytd, ped_label):
    """
    Substitui todos os slots de uppr_ pelo avatar completo e todos os outros slots por dummies.
    """
    print(f"\n[INFO] Aplicando substituicao universal em: {ped_label} ({ped_directory})")
    all_filenames = os.listdir(ped_directory)
    uppr_count = 0
    ytd_count = 0
    dummy_count = 0

    for filename in all_filenames:
        target_path = os.path.join(ped_directory, filename)

        # 1. Slots de tronco (uppr_*.ydd)
        if filename.startswith("uppr_") and filename.endswith(".ydd"):
            if "_r.ydd" in filename:
                shutil.copy2(source_uppr_r, target_path)
            else:
                shutil.copy2(source_uppr_u, target_path)
            uppr_count += 1

        # 2. Dicionarios de textura de tronco (uppr_diff_*.ytd)
        elif filename.startswith("uppr_diff_") and filename.endswith(".ytd"):
            shutil.copy2(source_ytd, target_path)
            ytd_count += 1

        # 3. Outros slots corporais humanos -> Dummy invisivel
        elif filename.endswith(".ydd") and not filename.startswith("uppr_"):
            shutil.copy2(DUMMY_SOURCE_PATH, target_path)
            dummy_count += 1

    print(f"[OK] {ped_label}: {uppr_count} drawables uppr substituidos, {ytd_count} dicionarios .ytd atualizados, {dummy_count} slots humanos convertidos em dummy.")


def deploy_universal():
    """Executa o pipeline completo de implantacao universal."""
    print("======================================================================")
    print("INICIANDO IMPLANTACAO UNIVERSAL DE SLOTS (MICHAEL & FRANKLIN)")
    print("======================================================================")

    # 1. Verifica integridade dos arquivos fonte necessarios
    assert os.path.exists(MICHAEL_UPPR_U), f"Arquivo nao encontrado: {MICHAEL_UPPR_U}"
    assert os.path.exists(MICHAEL_UPPR_R), f"Arquivo nao encontrado: {MICHAEL_UPPR_R}"
    assert os.path.exists(MICHAEL_YTD), f"Arquivo nao encontrado: {MICHAEL_YTD}"
    assert os.path.exists(FRANKLIN_UPPR_U), f"Arquivo nao encontrado: {FRANKLIN_UPPR_U}"
    assert os.path.exists(FRANKLIN_YTD), f"Arquivo nao encontrado: {FRANKLIN_YTD}"
    assert os.path.exists(DUMMY_SOURCE_PATH), f"Arquivo nao encontrado: {DUMMY_SOURCE_PATH}"
    assert os.path.exists(PROP_DUMMY_SOURCE_PATH), f"Arquivo nao encontrado: {PROP_DUMMY_SOURCE_PATH}"

    # 2. Aplica substituicao universal em streamedpeds_players_extracted
    apply_universal_slots_to_ped(
        PLAYER_ZERO_DIR, MICHAEL_UPPR_U, MICHAEL_UPPR_R, MICHAEL_YTD, "Michael (player_zero)"
    )
    apply_universal_slots_to_ped(
        PLAYER_ONE_DIR, FRANKLIN_UPPR_U, FRANKLIN_UPPR_U, FRANKLIN_YTD, "Franklin (player_one)"
    )

    # 3. Empacota streamedpeds_players.rpf e insere no x64v_extracted
    print("\n[INFO] Empacotando streamedpeds_players_shinano.rpf...")
    execute_shell_task(
        [
            RAGE_TOOL_PATH,
            "create",
            "-o",
            STREAMED_TARGET_RPF,
            STREAMED_BASE_DIR,
            "-e",
            "open",
        ],
        "Empacotamento de streamedpeds_players_shinano.rpf",
    )

    nested_streamed_dest = os.path.join(
        X64V_EXTRACTED_DIR, "models", "cdimages", "streamedpeds_players.rpf"
    )
    shutil.copy2(STREAMED_TARGET_RPF, nested_streamed_dest)
    print(f"[INFO] Atualizado: {nested_streamed_dest}")

    # 3B. Substitui oculos (p_eyes_*.ydd) em streamedpedprops e empacota streamedpedprops.rpf
    project_paths.ensure_streamedpedprops_extracted()
    project_paths.patch_character_glasses_props(
        PLAYER_ZERO_PROPS_DIR, PROP_DUMMY_SOURCE_PATH, "player_zero_p"
    )
    project_paths.patch_character_glasses_props(
        PLAYER_ONE_PROPS_DIR, PROP_DUMMY_SOURCE_PATH, "player_one_p"
    )
    execute_shell_task(
        [
            RAGE_TOOL_PATH,
            "create",
            "-o",
            STREAMEDPROPS_TARGET_RPF,
            STREAMEDPROPS_BASE_DIR,
            "-e",
            "open",
        ],
        "Empacotamento de streamedpedprops_shinano.rpf",
    )
    patch_rpf_table_of_contents(STREAMEDPROPS_TARGET_RPF)
    nested_props_dest = str(
        RPF_PATHS_CFG["x64v_extracted"] / RPF_PATHS_CFG["streamedpedprops_rpf_relative"]
    )
    shutil.copy2(STREAMEDPROPS_TARGET_RPF, nested_props_dest)
    print(f"[INFO] Atualizado: {nested_props_dest}")

    # 4. Empacota x64v_modded.rpf e aplica correcao de TOC
    print("\n[INFO] Empacotando x64v_modded.rpf...")
    execute_shell_task(
        [
            RAGE_TOOL_PATH,
            "create",
            "-o",
            X64V_MODDED_RPF,
            X64V_EXTRACTED_DIR,
            "-e",
            "open",
        ],
        "Empacotamento de x64v_modded.rpf",
    )

    patch_rpf_table_of_contents(X64V_MODDED_RPF)

    execute_shell_task(
        [RAGE_TOOL_PATH, "verify", X64V_MODDED_RPF],
        "Verificacao de integridade de x64v_modded.rpf",
    )

    print(f"[INFO] Copiando x64v_modded.rpf para {GTAV_MODS_X64V_RPF}...")
    shutil.copy2(X64V_MODDED_RPF, GTAV_MODS_X64V_RPF)

    execute_shell_task(
        [RAGE_TOOL_PATH, "verify", GTAV_MODS_X64V_RPF],
        f"Verificacao final de integridade em {GTAV_MODS_X64V_RPF}",
    )

    # 5. Atualiza DLC mppatchesng
    print("\n[INFO] Atualizando DLC mppatchesng...")
    os.makedirs(MPPATCHES_WORK_DIR, exist_ok=True)
    if not os.path.exists(MPPATCHES_EXTRACTED_DIR):
        shutil.copytree(STAGING_MPPATCHES_SEED, MPPATCHES_EXTRACTED_DIR)
    if not os.path.exists(MPPATCHESNG_EXTRACTED_DIR):
        shutil.copytree(STAGING_MPPATCHESNG_SEED, MPPATCHESNG_EXTRACTED_DIR)

    # Atualiza Michael no mppatches
    pz_mp = os.path.join(MPPATCHES_EXTRACTED_DIR, "player_zero")
    if os.path.exists(pz_mp):
        for entry_filename in os.listdir(pz_mp):
            entry_filepath = os.path.join(pz_mp, entry_filename)
            if entry_filename.startswith("uppr_") and entry_filename.endswith(".ydd"):
                shutil.copy2(MICHAEL_UPPR_U, entry_filepath)
            elif entry_filename.startswith("uppr_diff_") and entry_filename.endswith(".ytd"):
                shutil.copy2(MICHAEL_YTD, entry_filepath)
            elif entry_filename.endswith(".ydd"):
                shutil.copy2(DUMMY_SOURCE_PATH, entry_filepath)

    # Atualiza Franklin no mppatches
    po_mp = os.path.join(MPPATCHES_EXTRACTED_DIR, "player_one")
    if os.path.exists(po_mp):
        for entry_filename in os.listdir(po_mp):
            entry_filepath = os.path.join(po_mp, entry_filename)
            if entry_filename.startswith("uppr_") and entry_filename.endswith(".ydd"):
                shutil.copy2(FRANKLIN_UPPR_U, entry_filepath)
            elif entry_filename.startswith("uppr_diff_") and entry_filename.endswith(".ytd"):
                shutil.copy2(FRANKLIN_YTD, entry_filepath)
            elif entry_filename.endswith(".ydd"):
                shutil.copy2(DUMMY_SOURCE_PATH, entry_filepath)

    execute_shell_task(
        [RAGE_TOOL_PATH, "create", "-o", MPPATCHES_TARGET_RPF, MPPATCHES_EXTRACTED_DIR, "-e", "open"],
        "Empacotamento de mppatches.rpf",
    )

    nested_mppatches_dest = os.path.join(
        MPPATCHESNG_EXTRACTED_DIR, "x64", "models", "cdimages", "mppatches.rpf"
    )
    shutil.copy2(MPPATCHES_TARGET_RPF, nested_mppatches_dest)

    execute_shell_task(
        [RAGE_TOOL_PATH, "create", "-o", MPPATCHESNG_TARGET_RPF, MPPATCHESNG_EXTRACTED_DIR, "-e", "open"],
        "Empacotamento de mppatchesng_dlc.rpf",
    )

    patch_rpf_table_of_contents(MPPATCHESNG_TARGET_RPF)

    execute_shell_task(
        [RAGE_TOOL_PATH, "verify", MPPATCHESNG_TARGET_RPF],
        "Verificacao de integridade de mppatchesng_dlc.rpf",
    )

    print(f"[INFO] Copiando mppatchesng_dlc.rpf para {GTAV_MODS_MPPATCHESNG_DLC_RPF}...")
    shutil.copy2(MPPATCHESNG_TARGET_RPF, GTAV_MODS_MPPATCHESNG_DLC_RPF)

    execute_shell_task(
        [RAGE_TOOL_PATH, "verify", GTAV_MODS_MPPATCHESNG_DLC_RPF],
        "Verificacao final de integridade em mppatchesng/dlc.rpf",
    )

    # 6. Atualiza DLC patchday3ng
    print("\n[INFO] Atualizando DLC patchday3ng...")
    os.makedirs(PATCHDAY3_WORK_DIR, exist_ok=True)
    if not os.path.exists(PATCHDAY3NG_EXTRACTED_DIR):
        execute_shell_task(
            [RAGE_TOOL_PATH, "extract", "-o", PATCHDAY3NG_EXTRACTED_DIR, GTAV_MODS_PATCHDAY3NG_DLC_RPF],
            "Extracao do patchday3ng/dlc.rpf original",
        )

    # Extrai o patchday3ng.rpf aninhado
    nested_p3_rpf_path = os.path.join(
        PATCHDAY3NG_EXTRACTED_DIR, "x64", "models", "cdimages", "patchday3ng.rpf"
    )
    if not os.path.exists(PATCHDAY3_EXTRACTED_DIR):
        execute_shell_task(
            [RAGE_TOOL_PATH, "extract", "-o", PATCHDAY3_EXTRACTED_DIR, nested_p3_rpf_path],
            "Extracao de patchday3ng.rpf",
        )

    # Injeta Franklin uppr_008_u.ydd atualizado
    po_p3 = os.path.join(PATCHDAY3_EXTRACTED_DIR, "player_one")
    if os.path.exists(po_p3):
        f_target = os.path.join(po_p3, "uppr_008_u.ydd")
        shutil.copy2(FRANKLIN_UPPR_U, f_target)
        print(f"[INFO] Atualizado: {f_target}")

    # Injeta Michael uppr_029_u.ydd atualizado e decl dummy
    pz_p3 = os.path.join(PATCHDAY3_EXTRACTED_DIR, "player_zero")
    if os.path.exists(pz_p3):
        m_target = os.path.join(pz_p3, "uppr_029_u.ydd")
        if os.path.exists(m_target):
            shutil.copy2(MICHAEL_UPPR_U, m_target)
            print(f"[INFO] Atualizado: {m_target}")
        m_decl = os.path.join(pz_p3, "decl_003_u.ydd")
        if os.path.exists(m_decl):
            shutil.copy2(DUMMY_SOURCE_PATH, m_decl)
            print(f"[INFO] Dummy aplicado em: {m_decl}")

    execute_shell_task(
        [RAGE_TOOL_PATH, "create", "-o", PATCHDAY3_TARGET_RPF, PATCHDAY3_EXTRACTED_DIR, "-e", "open"],
        "Empacotamento de patchday3ng.rpf",
    )

    shutil.copy2(PATCHDAY3_TARGET_RPF, nested_p3_rpf_path)

    execute_shell_task(
        [RAGE_TOOL_PATH, "create", "-o", PATCHDAY3NG_TARGET_RPF, PATCHDAY3NG_EXTRACTED_DIR, "-e", "open"],
        "Empacotamento de patchday3ng_dlc.rpf",
    )

    patch_rpf_table_of_contents(PATCHDAY3NG_TARGET_RPF)

    execute_shell_task(
        [RAGE_TOOL_PATH, "verify", PATCHDAY3NG_TARGET_RPF],
        "Verificacao de integridade de patchday3ng_dlc.rpf",
    )

    print(f"[INFO] Copiando patchday3ng_dlc.rpf para {GTAV_MODS_PATCHDAY3NG_DLC_RPF}...")
    shutil.copy2(PATCHDAY3NG_TARGET_RPF, GTAV_MODS_PATCHDAY3NG_DLC_RPF)

    execute_shell_task(
        [RAGE_TOOL_PATH, "verify", GTAV_MODS_PATCHDAY3NG_DLC_RPF],
        "Verificacao final de integridade em patchday3ng/dlc.rpf",
    )

    print("\n======================================================================")
    print("[SUCESSO] IMPLANTACAO UNIVERSAL CONCLUIDA COM EXITO!")
    print("======================================================================")


if __name__ == "__main__":
    deploy_universal()
