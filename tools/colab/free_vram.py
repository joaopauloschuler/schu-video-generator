# Run with: colab exec -s ltx -f free_vram.py
# Asks ComfyUI to unload every model and free memory (POST /free) between the image and LTX stages.
import json
import urllib.request

req = urllib.request.Request("http://127.0.0.1:8188/free",
                             data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
                             headers={"Content-Type": "application/json"})
print("free:", urllib.request.urlopen(req).status)
