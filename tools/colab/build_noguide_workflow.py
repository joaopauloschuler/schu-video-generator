"""Write the ComfyUI API graph of an LTX-2.3 clip from a first frame and a stylesheet, with no control video.

vidgen's ``ltx-2.3-union-control`` workflow needs a guide; this is the same graph with a sheet
(``src/vidgen/videogen/ltx_graph.py``, loaded by its path: no install needed) with the control
branch taken out, as in the city-walk test A of 2026-11-28:

- LoadVideo (10), GetVideoComponents (11) and the control's LTXAddVideoICLoRAGuide (14) are removed;
  what read node 14 (16, 20, 23) reads the sheet guide (42);
- LTX Multi IC-LoRA (2) becomes LTXICLoRALoaderModelOnly with the Ingredients IC-LoRA alone (its
  output 1, the latent downscale factor, goes to node 42); the Union-Control IC-LoRA is not loaded;
- the first frame (9 -> 13, strength 1, not bypassed), the sheet (40 -> 41 -> 42), sampler, sigmas,
  negative, decode and output stay as vidgen writes them; no audio is decoded.

Usage (local, plain Python 3.10+, no dependencies):
  python build_noguide_workflow.py --run NAME --first-frame START.png --sheet SHEET.png
      --sheet-prompt TEXT (--prompt TEXT | --prompt-file FILE)
      [--width 768 --height 448 --frames 97 --fps 24 --seed 42] [--negative TEXT]
      [--text-encoder cpu|gpu] [--out-dir DIR]
  writes DIR/workflow_NAME.json (output prefix ltx_NAME). The prompt is
  "Reference sheet: <sheet prompt>. Generated video: <prompt>". File names are names inside
  ComfyUI/input/ on the VM; both pictures must already be at the clip's size.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

_GRAPH_FILE = Path(__file__).resolve().parents[2] / "src" / "vidgen" / "videogen" / "ltx_graph.py"
_spec = importlib.util.spec_from_file_location("ltx_graph", _GRAPH_FILE)
_ltx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ltx)

#: The nodes of the control video, removed from vidgen's sheet graph.
CONTROL_NODES = ("10", "11", "14")


def full_prompt(sheet_prompt: str, prompt: str) -> str:
    """The text vidgen sends for a sheet shot: the sheet prompt, then the shot's own prompt."""
    return f"Reference sheet: {sheet_prompt.strip().rstrip('.')}. Generated video: {prompt.strip()}"


def graph(*, first_frame_file: str, sheet_file: str, sheet_prompt: str, prompt: str, prefix: str,
          width: int = 768, height: int = 448, frames: int = 97, fps: int = 24, seed: int = _ltx.SEED,
          negative: str = _ltx.NEGATIVE, text_encoder: str = "cpu") -> dict:
    """The no-guide graph: vidgen's sheet graph without its control video (see the module docstring).

    Raises ValueError for a size that is not a multiple of 64 or a frame count that is not 8k+1."""
    g = _ltx.graph(control_file="unused.mp4", prefix=prefix, use_first_frame=True,
                   prompt=full_prompt(sheet_prompt, prompt), negative=negative, width=width, height=height,
                   frames=frames, fps=fps, seed=seed, first_frame_file=first_frame_file, with_audio=False,
                   sheet_file=sheet_file, text_encoder=text_encoder)
    for nid in CONTROL_NODES:
        del g[nid]
    g["2"] = {"class_type": "LTXICLoRALoaderModelOnly",
              "inputs": {"model": ["1", 0], "lora_name": _ltx.INGREDIENTS_LORA, "strength_model": 1.0}}
    g["42"]["inputs"]["latent_downscale_factor"] = ["2", 1]
    g["16"]["inputs"]["video_latent"] = ["42", 2]
    for nid in ("20", "23"):
        g[nid]["inputs"]["positive"] = ["42", 0]
        g[nid]["inputs"]["negative"] = ["42", 1]
    missing = {ref[0] for node in g.values() for ref in node["inputs"].values()
               if isinstance(ref, list) and len(ref) == 2 and isinstance(ref[0], str)} - set(g)
    if missing:
        raise AssertionError(f"the graph refers to missing nodes {sorted(missing)}")
    return g


def main(argv: list[str] | None = None) -> Path:
    """Write workflow_<run>.json from the command line and return its path."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", required=True, help="run name: writes workflow_<run>.json, output prefix ltx_<run>")
    p.add_argument("--first-frame", required=True, help="first-frame picture in ComfyUI/input/ (at the clip's size)")
    p.add_argument("--sheet", required=True, help="stylesheet picture in ComfyUI/input/ (at the clip's size)")
    p.add_argument("--sheet-prompt", required=True, help="what each panel shows: 'top left, ...; top right, ...'")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--prompt", help="the shot's prompt (camera and motion in plain words)")
    group.add_argument("--prompt-file", type=Path, help="read the prompt from this UTF-8 text file")
    p.add_argument("--negative", default=_ltx.NEGATIVE)
    p.add_argument("--width", type=int, default=768)
    p.add_argument("--height", type=int, default=448)
    p.add_argument("--frames", type=int, default=97)
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--seed", type=int, default=_ltx.SEED)
    p.add_argument("--text-encoder", choices=("cpu", "gpu"), default="cpu")
    p.add_argument("--out-dir", type=Path, default=Path.cwd())
    a = p.parse_args(argv)
    prompt = a.prompt_file.read_text(encoding="utf-8").strip() if a.prompt_file else a.prompt
    try:
        g = graph(first_frame_file=a.first_frame, sheet_file=a.sheet, sheet_prompt=a.sheet_prompt, prompt=prompt,
                  prefix=f"ltx_{a.run}", width=a.width, height=a.height, frames=a.frames, fps=a.fps, seed=a.seed,
                  negative=a.negative, text_encoder=a.text_encoder)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    a.out_dir.mkdir(parents=True, exist_ok=True)
    out = a.out_dir / f"workflow_{a.run}.json"
    out.write_text(json.dumps(g, indent=1), encoding="utf-8")
    print(f"{out} (output prefix ltx_{a.run}, prompt {len(g['4']['inputs']['text'].split())} words)")
    return out


if __name__ == "__main__":
    main()
