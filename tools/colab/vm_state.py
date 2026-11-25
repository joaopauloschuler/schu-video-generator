# VM side. Two uses:
#   colab exec -s NAME -f vm_state.py      prints one line "VIDGEN_STATE {json}" (setup_session.py reads it)
#   python /content/vm_state.py ltx|image  exits 0 when that setup is complete (setup*.sh call it)
# Standard library only: it runs in the Colab kernel and from the setup scripts.
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path("/content")
STATE_PREFIX = "VIDGEN_STATE "
COMFY_URL = "http://127.0.0.1:8188"
MARKERS = {"ltx": ".vidgen_setup_ltx_done", "image": ".vidgen_setup_image_done"}
LOGS = ("setup.log", "download.log", "setup_image.log", "comfy.log")
SCRIPTS = {"ltx": "/content/setup.sh", "image": "/content/setup_image.sh"}
CUSTOM_NODES = ("ComfyUI-LTXVideo", "ComfyUI-GGUF", "ComfyUI-VideoHelperSuite", "ComfyUI-KJNodes", "comfyui-hrnodes")
# Files under ComfyUI/models that each setup links in (setup.sh / setup_image.sh).
MODEL_FILES = {
    "ltx": (
        "unet/ltx-2.3-22b-distilled-1.1-Q5_K_M.gguf",
        "vae/ltx-2.3-22b-distilled_video_vae.safetensors",
        "vae/ltx-2.3-22b-distilled_audio_vae.safetensors",
        "text_encoders/ltx-2.3-22b-distilled_embeddings_connectors.safetensors",
        "text_encoders/gemma_3_12B_it_fp8_scaled.safetensors",
        "loras/ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors",
        "loras/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors",
    ),
    "image": (
        "unet/qwen-image-edit-2511-Q4_K_M.gguf",
        "loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
        "text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
        "vae/qwen_image_vae.safetensors",
        "diffusion_models/z_image_turbo_bf16.safetensors",
        "text_encoders/qwen_3_4b.safetensors",
        "vae/ae.safetensors",
        "model_patches/Z-Image-Turbo-Fun-Controlnet-Union-2.1-8steps.safetensors",
    ),
}
MODEL_FOLDERS = ("unet_gguf", "loras", "vae", "text_encoders", "diffusion_models", "model_patches")


def missing_files(part, root=ROOT):
    """The files `part` ("ltx" or "image") needs that are absent or empty (links are followed)."""
    comfy = root / "ComfyUI"
    need = [comfy / "models" / rel for rel in MODEL_FILES[part]]
    if part == "ltx":
        need.append(comfy / "main.py")
        need += [comfy / "custom_nodes" / node / "__init__.py" for node in CUSTOM_NODES]
    return [str(p) for p in need if not (p.is_file() and p.stat().st_size > 0)]


def running_commands(proc=Path("/proc")):
    """The command lines of the running processes, each joined with spaces."""
    lines = []
    for entry in proc.iterdir():
        if entry.name.isdigit():
            try:
                raw = (entry / "cmdline").read_bytes()
            except OSError:
                continue
            if raw:
                lines.append(raw.rstrip(b"\0").replace(b"\0", b" ").decode("utf-8", "replace"))
    return lines


def comfy_get(path, timeout=3.0):
    """GET a ComfyUI endpoint and decode its JSON; None when the server does not answer."""
    try:
        with urllib.request.urlopen(COMFY_URL + path, timeout=timeout) as reply:
            return json.load(reply)
    except (OSError, ValueError):
        return None


def log_info(path, tail_lines=15, max_bytes=200_000):
    """The ### milestone lines and the last lines of the log's last `max_bytes` (empty when absent)."""
    try:
        with path.open("rb") as log:
            log.seek(max(0, path.stat().st_size - max_bytes))
            lines = log.read().decode("utf-8", "replace").replace("\r", "\n").splitlines()
    except OSError:
        return {"exists": False, "milestones": [], "tail": []}
    return {"exists": True, "milestones": [ln for ln in lines if ln.startswith("###")],
            "tail": lines[-tail_lines:]}


def state(root=ROOT, proc=Path("/proc")):
    """Everything setup_session.py needs to decide what to skip, start or wait for."""
    commands = running_commands(proc)
    parts = {}
    for part in MARKERS:
        parts[part] = {
            "marker": (root / MARKERS[part]).is_file(),
            "missing": missing_files(part, root),
            "running": any(f"bash {SCRIPTS[part]}" in c for c in commands),
        }
    up = comfy_get("/system_stats") is not None
    models = {}
    if up:
        for folder in MODEL_FOLDERS:
            names = comfy_get(f"/models/{folder}")
            models[folder] = sorted(names) if isinstance(names, list) else None
    return {
        "parts": parts,
        "comfy": {"up": up, "running": any("main.py" in c and "8188" in c for c in commands),
                  "dir": (root / "ComfyUI" / "main.py").is_file(), "models": models},
        "logs": {name: log_info(root / name) for name in LOGS},
    }


def main(args):
    if args and args[0] in MARKERS:
        missing = missing_files(args[0])
        for path in missing:
            print("MISSING", path)
        return 1 if missing else 0
    print(STATE_PREFIX + json.dumps(state()))
    return 0


if __name__ == "__main__":
    code = main(sys.argv[1:])
    if code:
        sys.exit(code)
