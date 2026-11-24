"""Submit one API-format workflow to ComfyUI (127.0.0.1:8188), wait, and record timing.

Started detached by start_job.py:  python /content/run_job.py /content/workflow_<run>.json <run>
Writes /content/job_<run>.json with wall time, outputs, status messages and peak VRAM
(max of the 1 s nvidia-smi samples in /content/vram.csv during the run).
"""
import json
import sys
import time
import urllib.request

wf_path, run = sys.argv[1], sys.argv[2]
URL = "http://127.0.0.1:8188"
graph = json.load(open(wf_path))
t0 = time.time()
start_iso = time.strftime("%Y/%m/%d %H:%M:%S", time.gmtime(t0))
req = urllib.request.Request(URL + "/prompt", data=json.dumps({"prompt": graph}).encode(),
                             headers={"Content-Type": "application/json"})
try:
    resp = json.load(urllib.request.urlopen(req))
except urllib.error.HTTPError as e:
    json.dump({"run": run, "error": e.read().decode()}, open(f"/content/job_{run}.json", "w"),
              indent=1)
    raise SystemExit(1)
pid = resp["prompt_id"]
hist = None
while True:
    time.sleep(3)
    h = json.load(urllib.request.urlopen(f"{URL}/history/{pid}"))
    if pid in h and h[pid].get("status", {}).get("completed") is not None:
        hist = h[pid]
        if hist["status"].get("status_str") in ("success", "error"):
            break
t1 = time.time()
peak = 0
for line in open("/content/vram.csv"):
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 2:
        continue
    ts = parts[0][:19]
    if start_iso <= ts:
        try:
            peak = max(peak, int(parts[1].split()[0]))
        except ValueError:
            pass
out = {"run": run, "prompt_id": pid, "wall_s": round(t1 - t0, 1),
       "peak_vram_mib_nvidia_smi": peak, "status": hist["status"],
       "outputs": hist.get("outputs")}
json.dump(out, open(f"/content/job_{run}.json", "w"), indent=1)
