"""tools/colab/build_noguide_workflow.py: the LTX graph of a first frame + stylesheet, no control video."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "colab" / "build_noguide_workflow.py"


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_noguide_workflow", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _graph(**kw: object) -> dict:
    args = dict(first_frame_file="start.png", sheet_file="sheet.png", sheet_prompt="top left, the woman; top right, the street",
                prompt="The camera tracks backwards in front of her.", prefix="ltx_walk1")
    args.update(kw)
    return _tool().graph(**args)


def test_no_control_video_and_no_union_control() -> None:
    g = _graph()
    classes = [node["class_type"] for node in g.values()]
    assert "LoadVideo" not in classes and "GetVideoComponents" not in classes and "LTXMultiICLoRA" not in classes
    assert classes.count("LTXAddVideoICLoRAGuide") == 1
    assert not any("union-control" in json.dumps(node) for node in g.values())
    assert g["2"] == {"class_type": "LTXICLoRALoaderModelOnly",
                      "inputs": {"model": ["1", 0], "lora_name": "ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors", "strength_model": 1.0}}


def test_keeps_first_frame_and_sheet_conditioning() -> None:
    g = _graph(frames=97)
    assert g["9"]["inputs"]["image"] == "start.png"
    assert g["13"]["inputs"]["image"] == ["9", 0] and g["13"]["inputs"]["bypass"] is False and g["13"]["inputs"]["strength"] == 1.0
    assert g["40"]["inputs"]["image"] == "sheet.png"
    assert g["41"]["inputs"] == {"image": ["40", 0], "amount": 97}
    assert g["42"]["inputs"]["image"] == ["41", 0] and g["42"]["inputs"]["latent"] == ["13", 0]
    assert g["42"]["inputs"]["latent_downscale_factor"] == ["2", 1]
    assert g["16"]["inputs"]["video_latent"] == ["42", 2]
    for nid in ("20", "23"):
        assert g[nid]["inputs"]["positive"] == ["42", 0] and g[nid]["inputs"]["negative"] == ["42", 1]


def test_every_reference_resolves_and_settings_pass_through() -> None:
    g = _graph(width=960, height=512, frames=121, seed=7)
    refs = {v[0] for node in g.values() for v in node["inputs"].values() if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)}
    assert refs <= set(g)
    assert g["12"]["inputs"] == {"width": 960, "height": 512, "length": 121, "batch_size": 1}
    assert g["17"]["inputs"]["noise_seed"] == 7
    assert g["26"]["inputs"]["filename_prefix"] == "ltx_walk1" and "audio" not in g["26"]["inputs"]
    assert g["4"]["inputs"]["text"] == ("Reference sheet: top left, the woman; top right, the street. "
                                       "Generated video: The camera tracks backwards in front of her.")


@pytest.mark.parametrize("bad", [dict(width=770), dict(frames=96)])
def test_bad_size_or_length_is_refused(bad: dict) -> None:
    with pytest.raises(ValueError):
        _graph(**bad)


def test_command_line_writes_the_workflow(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("She walks towards the camera.\n", encoding="utf-8")
    out = _tool().main(["--run", "walk1_s43", "--seed", "43", "--first-frame", "start.png", "--sheet", "sheet.png",
                        "--sheet-prompt", "top left, the woman", "--prompt-file", str(prompt), "--out-dir", str(tmp_path)])
    assert out == tmp_path / "workflow_walk1_s43.json"
    g = json.loads(out.read_text(encoding="utf-8"))
    assert g["17"]["inputs"]["noise_seed"] == 43 and g["26"]["inputs"]["filename_prefix"] == "ltx_walk1_s43"
    assert g["4"]["inputs"]["text"].endswith("Generated video: She walks towards the camera.")
