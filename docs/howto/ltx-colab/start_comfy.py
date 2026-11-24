# Run with: colab exec -s ltx -f start_comfy.py
# Starts the ComfyUI server detached on 127.0.0.1:8188, log in /content/comfy.log,
# plus an nvidia-smi sampler (every 1 s) in /content/vram.csv for peak-VRAM numbers.
import subprocess

log = open("/content/comfy.log", "a")
p = subprocess.Popen(["python", "main.py", "--listen", "127.0.0.1", "--port", "8188",
                      "--disable-auto-launch"],
                     cwd="/content/ComfyUI", stdout=log, stderr=subprocess.STDOUT,
                     start_new_session=True)
print("comfy pid", p.pid)
vlog = open("/content/vram.csv", "a")
q = subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,memory.used,utilization.gpu",
                      "--format=csv,noheader", "-l", "1"], stdout=vlog,
                     stderr=subprocess.STDOUT, start_new_session=True)
print("vram sampler pid", q.pid)
