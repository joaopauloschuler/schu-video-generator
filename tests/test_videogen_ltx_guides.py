"""The three guides of the ``ltx-2.3-union-control`` workflow on a ``web`` scene (Step 435):
``guide: canny``, ``final`` and ``depth``, each with and without a sheet, at 12 and 24 fps: the
plan's guide input and prompt sentence, the request and the graph; other guides refused; a guide
change makes only that shot's inputs and clip new. No rendering, no FFmpeg."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from PIL import Image
from test_videogen_comfyui import no_ffmpeg  # noqa: F401  (a fixture)

from vidgen.project import Project
from vidgen.videogen import comfyui, request_hash
from vidgen.videogen.inputs import _passes_by_render, render_kind
from vidgen.videogen.shots import GUIDE_PROMPTS, GUIDE_WHAT, ShotPlan, guide_name, project_shots

LTX = "ltx-2.3-union-control"
PANELS = "top: the escapement; bottom: the plate"
GUIDES = ("canny", "final", "depth")


def _project(make_project: Any, folder: str, *, sheet: bool = False, fps: int = 12, **tick: Any) -> Path:
    """A comfyui project with one ``web`` scene: beat ``tick`` (``tick`` overrides its shot) and beat ``tock`` (canny)."""
    from conftest import minimal_config

    def shot(**kw: Any) -> dict[str, Any]:
        spec = {"kind": "establishing", "model": LTX, "guide": "canny", "first_frame": "none", "size": "768x448", "line": False,
                "audio": "none", "prompt": "an escapement ticks", "duration": 8 if fps == 12 else 4, "fps": fps, **kw}
        if sheet:
            spec |= {"sheet": "sheets/s.png", "sheet_prompt": PANELS}
        return spec

    pause = 7.6 if fps == 12 else 3.6
    data = minimal_config(
        videogen={"provider": "comfyui", "comfyui": {"url": "http://127.0.0.1:8188"}},
        scenes=[{"id": "w", "type": "web", "params": {"script": "page.js"},
                 "beats": [{"id": "tick", "text": "Tick.", "pause": pause, "generated_shot": shot(**tick)},
                           {"id": "tock", "text": "Tock.", "pause": pause, "generated_shot": shot()}]}],
    )
    root = make_project(data, folder=folder)
    (root / "page.js").write_text("export function frame() {}\n", encoding="utf-8")
    (root / "sheets").mkdir()
    Image.new("RGB", (768, 448), (40, 60, 90)).save(root / "sheets" / "s.png")
    return root


def _shots(root: Path) -> dict[str, Any]:
    from vidgen.videogen.models import Catalog

    return {s.id: s for s in project_shots(Project.load(root), Catalog((), 0.0, "cache"))}


def _make_guides(root: Path, shots: dict[str, Any]) -> None:
    for shot in shots.values():
        for item in shot.inputs:
            item.path.parent.mkdir(parents=True, exist_ok=True)
            item.path.write_bytes(item.path.name.encode())


@pytest.mark.parametrize("fps", [12, 24])
@pytest.mark.parametrize("sheet", [False, True])
@pytest.mark.parametrize("guide", GUIDES)
def test_each_guide_builds_its_control_input_prompt_and_graph(make_project: Any, tmp_path: Path, no_ffmpeg: Any,  # noqa: F811
                                                              guide: str, sheet: bool, fps: int) -> None:
    root = _project(make_project, f"{guide}-{sheet}-{fps}", sheet=sheet, fps=fps, guide=guide)
    shots = _shots(root)
    shot = shots["tick"]
    assert not shot.problems, shot.problems
    (control,) = [i for i in shot.inputs if i.role == "guide"]
    assert control.path.name == guide_name(guide) == f"guide.{guide}.mp4"
    assert GUIDE_PROMPTS[guide] in shot.prompt and shot.prompt.startswith("Reference sheet: ") is sheet
    project = Project.load(root)
    assert render_kind(project, "w", guide) == "final"   # all three come from the finished render of a web scene
    assert _passes_by_render(project, [shot]) == ({("w", "final"): ("depth",)} if guide == "depth" else {})
    _make_guides(root, shots)
    plan = ShotPlan(shot, shot.request())
    assert any(line.startswith("  guide: ") and f"({GUIDE_WHAT[guide]}, " in line for line in plan.lines(root))
    request = plan.request
    assert [r.path for r in request.references] == [control.path] and request.fps == (12 if fps == 12 else None)
    assert (request.sheet is not None) is sheet
    folder = tmp_path / f"job-{guide}-{sheet}-{fps}"
    folder.mkdir()
    job = comfyui.prepare_job(request, folder, "k")
    assert job.graph["10"]["inputs"]["file"] == "vidgen_k_control.mp4" and job.graph["4"]["inputs"]["text"] == request.prompt
    assert json.loads(job.uploads["vidgen_k_control.mp4"].read_bytes()[7:])["frames"] == 97
    assert job.graph["6"]["inputs"]["frame_rate"] == float(fps) and ("51" in job.graph) is (fps == 12)
    assert ("40" in job.graph) is sheet


def test_other_guides_are_refused_by_name(make_project: Any) -> None:
    for guide, shown in ((True, "render"), (False, "no guide")):
        root = _project(make_project, f"refused-{shown}", guide=guide)
        problems = _shots(root)["tick"].problems
        assert f"scenes[0].beats[0].generated_shot.guide: {LTX} takes guide: canny, final or depth as its control video, not {shown}" in " ".join(problems)
    assert comfyui.WORKFLOWS[LTX].controls == ("canny", "final", "depth")


def test_a_guide_change_makes_only_that_shot_new(make_project: Any) -> None:
    root = _project(make_project, "stale")
    _make_guides(root, _shots(root))
    before = _shots(root)
    keys = {sid: request_hash(s.request()) for sid, s in before.items()}
    assert not any(s.blocked for s in before.values())
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["scenes"][0]["beats"][0]["generated_shot"]["guide"] = "final"
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    after = _shots(root)
    tick, tock = after["tick"], after["tock"]
    assert any("inputs not made yet" in b for b in tick.blocked) and not tock.blocked
    assert any(line.endswith("; not made yet)") and "guide.final.mp4" in line for line in ShotPlan(tick, tick.request()).lines(root))
    _make_guides(root, after)
    assert request_hash(tick.request()) != keys["tick"] and request_hash(tock.request()) == keys["tock"]
