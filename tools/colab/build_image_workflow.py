"""Write the ComfyUI API-format graphs that make a photoreal version of frame 0.

The graphs are vidgen's (``src/vidgen/videogen/qwen_graph.py``, loaded by its path: no install
needed). Routes:
  qwen    Qwen-Image-Edit-2511 (GGUF Q4_K_M) + the 4-step Lightning LoRA: an instruction edit
  zimage  Z-Image-Turbo + Fun ControlNet Union 2.1 (canny or depth of frame 0), img2img

  python build_image_workflow.py qwen --run qwen_a --out workflow_qwen_a.json [--seed 42]
      [--denoise 1.0] [--prompt-file p.txt]
  python build_image_workflow.py zimage --run zi_canny --control ff_canny.png --strength 0.8
      --denoise 0.7 --out workflow_zi_canny.json
Inputs (in ComfyUI/input, from prep_image_inputs.py): ff_up.png (frame 0 at 1440x768) and the
control image. Output: ComfyUI/output/<run>_00001_.png, scaled back to 960x512 (--width/--height).
The default qwen prompt is the Step 405 run's prompt C (vidgen's own default is generic).
"""
import argparse
import importlib.util
import json
from pathlib import Path

_GRAPH_FILE = Path(__file__).resolve().parents[2] / "src" / "vidgen" / "videogen" / "qwen_graph.py"
_spec = importlib.util.spec_from_file_location("qwen_graph", _GRAPH_FILE)
_qwen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_qwen)


def main() -> None:
    """Parse the arguments and write one graph."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("route", choices=["qwen", "zimage"])
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--denoise", type=float)
    ap.add_argument("--steps", type=int)
    ap.add_argument("--no-lora", action="store_true", help="qwen: without Lightning (cfg 4)")
    ap.add_argument("--control", default="ff_canny.png", help="zimage: control image in input/")
    ap.add_argument("--strength", type=float, default=0.8, help="zimage: controlnet strength")
    ap.add_argument("--prompt-file", type=Path)
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=512)
    a = ap.parse_args()
    prompt = a.prompt_file.read_text(encoding="utf-8").strip() if a.prompt_file else None
    if a.route == "qwen":
        steps = a.steps or (20 if a.no_lora else 4)
        g = _qwen.qwen_graph(a.run, prompt or _qwen.QWEN_PROMPT, a.seed, a.denoise or 1.0, a.width, a.height,
                             steps, not a.no_lora)
    else:
        g = _qwen.zimage_graph(a.run, prompt or _qwen.ZIMAGE_PROMPT, a.seed, a.denoise or 0.7, a.width,
                               a.height, a.control, a.strength, a.steps or 8)
    a.out.write_text(json.dumps(g, indent=1), encoding="utf-8")
    print("wrote", a.out)


main()
