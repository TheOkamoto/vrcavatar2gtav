import subprocess
import sys
import time

cmd = [
    "powershell.exe",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "& 'E:\\waifuv4\\BlenderTools\\blender-4.0.2-windows-x64\\blender.exe' -b -P E:\\gtav_mod_franklin\\build_franklin_avatar.py"
]

print("[INFO] Iniciando build do avatar do Franklin no Blender...")
start = time.time()
res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
elapsed = time.time() - start

print(f"[INFO] Processo concluido em {elapsed:.1f} segundos. Return code: {res.returncode}")
print("--- STDOUT ---")
for line in res.stdout.splitlines():
    if any(k in line for k in ["[INFO]", "[OK]", "[SUCESSO]", "[ERRO]", "Error", "Saved", "Export", "vertices", "blendshape"]):
        print(line)

if res.returncode != 0:
    print("--- STDERR ---")
    print(res.stderr[-2000:])
    sys.exit(res.returncode)
