"""Write ComfyUI API-format graphs for the LTX-2.3 IC-LoRA Union Control runs.

The graph itself is vidgen's ``ltx-2.3-union-control`` workflow
(``src/vidgen/videogen/ltx_graph.py``, loaded by its path: no install needed).
Usage (local, plain Python 3.10+, no dependencies):
  python build_workflow.py --experiment [--out-dir DIR]
      writes the seven workflow_<run>.json of the 2026-11-24 test (byte-identical to the ones run)
  python build_workflow.py --run NAME --control canny_121_960x512.mp4 [--second-control FILE]
      [--first-frame first_frame_960x512.png | --no-first-frame] [--first-frame-strength 0.5]
      [--prompt TEXT | --prompt-file FILE] [--width 960 --height 512 --frames 121 --fps 24 --seed 42]
      writes workflow_NAME.json (output prefix ltx_NAME). File names are names inside
      ComfyUI/input/ on the VM, not local paths.
"""
import argparse
import importlib.util
import json
from pathlib import Path

_GRAPH_FILE = Path(__file__).resolve().parents[2] / "src" / "vidgen" / "videogen" / "ltx_graph.py"
_spec = importlib.util.spec_from_file_location("ltx_graph", _GRAPH_FILE)
_ltx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ltx)
PROMPT, NEGATIVE, FIRST_FRAME = _ltx.PROMPT, _ltx.NEGATIVE, _ltx.FIRST_FRAME
W, H, FRAMES, FPS, SEED = _ltx.W, _ltx.H, _ltx.FRAMES, _ltx.FPS, _ltx.SEED


def graph(**kw) -> dict:
    """The graph of one run (:func:`ltx_graph.graph`); a bad size stops the script."""
    try:
        return _ltx.graph(**kw)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None


RUNS = {
    "depth": dict(control_file="depth_121_960x512.mp4", prefix="ltx_depth", use_first_frame=True),
    "canny": dict(control_file="canny_121_960x512.mp4", prefix="ltx_canny", use_first_frame=True),
    "depth_noff": dict(control_file="depth_121_960x512.mp4", prefix="ltx_depth_noff",
                       use_first_frame=False),
    "depth_canny": dict(control_file="depth_121_960x512.mp4", prefix="ltx_depth_canny",
                        use_first_frame=True, second_control_file="canny_121_960x512.mp4"),
    "canny_noff": dict(control_file="canny_121_960x512.mp4", prefix="ltx_canny_noff",
                       use_first_frame=False),
    "depth_canny_noff": dict(control_file="depth_121_960x512.mp4", prefix="ltx_depth_canny_noff",
                             use_first_frame=False,
                             second_control_file="canny_121_960x512.mp4"),
    "depth_canny_ff05": dict(control_file="depth_121_960x512.mp4", prefix="ltx_depth_canny_ff05",
                             use_first_frame=True, first_frame_strength=0.5,
                             second_control_file="canny_121_960x512.mp4"),
}

def main() -> None:
    """Write the experiment's graphs, or one graph from the command line."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--experiment", action="store_true", help="write the seven graphs of the test")
    p.add_argument("--out-dir", type=Path, default=Path.cwd())
    p.add_argument("--run", help="run name: writes workflow_<run>.json, output prefix ltx_<run>")
    p.add_argument("--control", help="control video in ComfyUI/input/ (full output size)")
    p.add_argument("--second-control", help="a second control video, chained as a second guide")
    p.add_argument("--first-frame", default=FIRST_FRAME, help="first-frame picture in ComfyUI/input/")
    p.add_argument("--no-first-frame", action="store_true", help="bypass the first-frame node")
    p.add_argument("--first-frame-strength", type=float, default=1.0)
    p.add_argument("--guide-strength", type=float, default=1.0)
    p.add_argument("--lora-strength", type=float, default=1.0)
    p.add_argument("--prompt", default=PROMPT)
    p.add_argument("--prompt-file", type=Path, help="read the prompt from this UTF-8 text file")
    p.add_argument("--negative", default=NEGATIVE)
    p.add_argument("--width", type=int, default=W)
    p.add_argument("--height", type=int, default=H)
    p.add_argument("--frames", type=int, default=FRAMES)
    p.add_argument("--fps", type=int, default=FPS)
    p.add_argument("--seed", type=int, default=SEED)
    a = p.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    if a.experiment:
        runs = RUNS
    elif a.run and a.control:
        prompt = a.prompt_file.read_text(encoding="utf-8").strip() if a.prompt_file else a.prompt
        runs = {a.run: dict(control_file=a.control, prefix=f"ltx_{a.run}",
                            use_first_frame=not a.no_first_frame,
                            second_control_file=a.second_control,
                            first_frame_strength=a.first_frame_strength,
                            guide_strength=a.guide_strength, lora_strength=a.lora_strength,
                            prompt=prompt, negative=a.negative, width=a.width, height=a.height,
                            frames=a.frames, fps=a.fps, seed=a.seed,
                            first_frame_file=a.first_frame)}
    else:
        p.error("give --experiment, or --run and --control")
    for name, kw in runs.items():
        path = a.out_dir / f"workflow_{name}.json"
        path.write_text(json.dumps(graph(**kw), indent=1), encoding="utf-8")
        print("wrote", path)


if __name__ == "__main__":
    main()
