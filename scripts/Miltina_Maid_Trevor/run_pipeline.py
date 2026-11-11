#!/usr/bin/env python3
# Run pipeline: Blender build & render + RAGE engine render for Miltina Maid

import os
import shutil
import subprocess
import sys
import time

def execute_pipeline():
    start_time = time.time()
    work_dir = "/mnt/e/gtav_mod_trevor_miltina"
    artifacts_dir = "/home/okamoto/.gemini/antigravity/brain/30b341d6-822d-4846-8de4-95dd5ff74215"
    rage_tool = "/home/okamoto/.gemini/antigravity/scratch/gtav_tools/rage"
    python_env = "/home/okamoto/.gemini/antigravity/scratch/vrc-avatar-to-gtav/.venv/bin/python3"
    
    # 0. Generate texture atlas and build .ytd
    print("[INFO] Generating Miltina 2K texture atlas (bright face + sapphire blue hair) with correct JOAAT order...")
    subprocess.run([python_env, os.path.join(work_dir, "build_textures_2k.py")], check=True)
    
    # 1. Execute Blender build & render
    print("[INFO] Starting Blender execution...")
    blender_command = [
        "cmd.exe", "/c",
        r"E:\waifuv4\BlenderTools\blender-4.0.2-windows-x64\blender.exe -b -P E:\gtav_mod_trevor_miltina\build_and_render_miltina.py"
    ]
    
    proc = subprocess.run(blender_command, capture_output=True, encoding="cp932", errors="replace")
    print("--- Blender Output ---")
    for line in proc.stdout.splitlines():
        if any(marker in line for marker in ["[INFO]", "[SUCCESS]", "[OK]", "Error", "Saved"]):
            print("  ", line)
            
    if proc.returncode != 0:
        print("[ERROR] Blender build failed!")
        print(proc.stderr[-2000:])
        sys.exit(proc.returncode)
        
    # Copy Blender renders to artifacts
    renders_source = os.path.join(work_dir, "renders")
    face_render_src = os.path.join(renders_source, "miltina_blender_face.png")
    full_render_src = os.path.join(renders_source, "miltina_blender_full.png")
    
    if os.path.exists(face_render_src):
        shutil.copy2(face_render_src, os.path.join(artifacts_dir, "miltina_blender_face.png"))
        print(f"[OK] Copied face render to artifacts: miltina_blender_face.png")
    if os.path.exists(full_render_src):
        shutil.copy2(full_render_src, os.path.join(artifacts_dir, "miltina_blender_full.png"))
        print(f"[OK] Copied full render to artifacts: miltina_blender_full.png")

    # 1.1 Render Lip Sync Demo (closed, dialogue 8 deg, speech max 15 deg)
    print("[INFO] Rendering Lip Sync poses in Blender (FACIAL_jaw rotation)...")
    lipsync_command = [
        "cmd.exe", "/c",
        r"E:\waifuv4\BlenderTools\blender-4.0.2-windows-x64\blender.exe -b -P E:\gtav_mod_trevor_miltina\render_miltina_lipsync_demo.py"
    ]
    subprocess.run(lipsync_command, capture_output=True, encoding="cp932", errors="replace", check=True)
    lipsync_dir = os.path.join(work_dir, "renders_lipsync_demo")
    for filename in os.listdir(lipsync_dir):
        if filename.endswith(".png"):
            src_path = os.path.join(lipsync_dir, filename)
            shutil.copy2(src_path, os.path.join(artifacts_dir, filename))
            print(f"[OK] Copied lip sync render to artifacts: {filename}")
        
    # 2. Package into temporary RPF and execute RAGE screenshot
    ydd_path = os.path.join(work_dir, "output", "uppr_000_u.ydd")
    ytd_path = os.path.join(work_dir, "miltina_maid.ytd")
    
    if not os.path.exists(ydd_path):
        print(f"[ERROR] YDD not found at: {ydd_path}")
        sys.exit(1)
        
    rpf_stage_dir = os.path.join(work_dir, "rpf_stage")
    os.makedirs(rpf_stage_dir, exist_ok=True)
    shutil.copy2(ydd_path, os.path.join(rpf_stage_dir, "uppr_000_u.ydd"))
    
    rpf_output_path = os.path.join(work_dir, "miltina_preview.rpf")
    print(f"[INFO] Creating preview RPF: {rpf_output_path}")
    subprocess.run([rage_tool, "create", "-o", rpf_output_path, rpf_stage_dir], check=True)
    
    rage_render_dir = os.path.join(work_dir, "rage_renders")
    os.makedirs(rage_render_dir, exist_ok=True)
    
    print("[INFO] Executing RAGE screenshot...")
    screenshot_command = [
        rage_tool, "screenshot",
        "--ytd", ytd_path,
        "--views", "front,45:0,iso",
        "--grid",
        "--size", "1024x1024",
        "-o", rage_render_dir,
        rpf_output_path,
        "uppr_000_u.ydd"
    ]
    subprocess.run(screenshot_command, check=True)
    
    # Copy RAGE screenshots to artifacts
    for filename in os.listdir(rage_render_dir):
        if filename.endswith(".png"):
            src_path = os.path.join(rage_render_dir, filename)
            dest_name = f"miltina_rage_{filename}"
            shutil.copy2(src_path, os.path.join(artifacts_dir, dest_name))
            print(f"[OK] Copied RAGE render to artifacts: {dest_name}")

    # Generate RAGE Head & Face close-up crop
    front_screenshot = os.path.join(rage_render_dir, "uppr_000_u_front.png")
    if os.path.exists(front_screenshot):
        crop_dest = os.path.join(artifacts_dir, "miltina_rage_head_crop.png")
        crop_cmd = [
            "ffmpeg", "-y", "-i", front_screenshot,
            "-filter:v", "crop=320:320:352:170",
            crop_dest
        ]
        subprocess.run(crop_cmd, capture_output=True, check=True)
        print(f"[OK] Generated RAGE face close-up: miltina_rage_head_crop.png")

    # 3. Apply Miltina Maid to Trevor extracted mod directories
    print("[INFO] Applying Miltina Maid to Trevor mod folders...")
    subprocess.run([python_env, os.path.join(work_dir, "apply_miltina_to_trevor.py")], check=True)

    # 4. Repack into dlc.rpf and x64v.rpf with OPEN headers and deploy to GTAV/mods
    print("[INFO] Repacking RPFs and deploying to /mnt/d/GTAV/mods/...")
    repack_script = "/mnt/e/waifuv4/gtav_mod/repack_and_deploy_everything.py"
    subprocess.run([python_env, repack_script], check=True)
    print("[SUCCESS] All RPF archives repacked with OPEN header and deployed!")
            
    elapsed = time.time() - start_time
    print(f"\n[COMPLETE] Full pipeline finished successfully in {elapsed:.1f} seconds.")

if __name__ == "__main__":
    execute_pipeline()
