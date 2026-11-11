"""
Script to apply Miltina Maid model and textures to Trevor (player_two).
Replaces drawables and texture dictionaries across extracted mod directories.
"""

import glob
import os
import shutil

DUMMY_YDD_PATH = "/mnt/e/waifuv4/gtav_mod/output/head_000_r.ydd"
MILTINA_MODEL_YDD_PATH = "/mnt/e/gtav_mod_trevor_miltina/output/uppr_000_u.ydd"
MILTINA_TEXTURE_YTD_PATH = "/mnt/e/gtav_mod_trevor_miltina/miltina_maid.ytd"

MPPATCHES_P2_DIR = "/mnt/e/waifuv4/gtav_mod/mppatches_extracted/player_two"
STREAMEDPEDS_P2_DIR = "/mnt/e/waifuv4/gtav_mod/streamedpeds_players_extracted/player_two"

def patch_directory(target_dir, is_mppatches=False):
    print(f"=== Patching {target_dir} ===")
    if not os.path.isdir(target_dir):
        raise FileNotFoundError(f"Directory not found: {target_dir}")

    uppr_count = 0
    ytd_count = 0
    dummy_count = 0
    skipped_count = 0

    all_files = sorted(os.listdir(target_dir))
    for filename in all_files:
        filepath = os.path.join(target_dir, filename)
        if not os.path.isfile(filepath):
            continue

        prefix = filename.split("_")[0].lower()
        ext = os.path.splitext(filename)[1].lower()

        if prefix == "uppr" and ext == ".ydd":
            shutil.copyfile(MILTINA_MODEL_YDD_PATH, filepath)
            uppr_count += 1
        elif prefix == "uppr" and "diff" in filename and ext == ".ytd":
            shutil.copyfile(MILTINA_TEXTURE_YTD_PATH, filepath)
            ytd_count += 1
        elif ext == ".ydd" and prefix in [
            "accs", "berd", "decl", "feet", "hair",
            "hand", "head", "jbib", "lowr", "task", "teef"
        ]:
            shutil.copyfile(DUMMY_YDD_PATH, filepath)
            dummy_count += 1
        else:
            skipped_count += 1

    print(f"Result for {target_dir}:")
    print(f"  Uppr models replaced (Miltina Maid): {uppr_count}")
    print(f"  Uppr textures replaced (Atlas YTD):  {ytd_count}")
    print(f"  Dummy models installed (Empty 629B): {dummy_count}")
    print(f"  Untouched files (metadata/props):    {skipped_count}")

def main():
    if not os.path.exists(DUMMY_YDD_PATH):
        raise FileNotFoundError(f"Dummy YDD not found at {DUMMY_YDD_PATH}")
    if not os.path.exists(MILTINA_MODEL_YDD_PATH):
        raise FileNotFoundError(f"Miltina model not found at {MILTINA_MODEL_YDD_PATH}")
    if not os.path.exists(MILTINA_TEXTURE_YTD_PATH):
        raise FileNotFoundError(f"Miltina texture not found at {MILTINA_TEXTURE_YTD_PATH}")

    patch_directory(MPPATCHES_P2_DIR, is_mppatches=True)
    patch_directory(STREAMEDPEDS_P2_DIR, is_mppatches=False)
    print("\nAll target directories successfully patched.")

if __name__ == "__main__":
    main()
