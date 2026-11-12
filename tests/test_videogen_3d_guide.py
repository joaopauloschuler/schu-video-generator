"""3D guide passes as the guide of a generated shot (DESIGN.md §113.8): ``guide: depth | outline |
mask`` on a ``3d`` scene, validation, the plan, the request hash, the prompt and the converted
``guide.<pass>.mp4``. Nothing is sent or paid; one test renders a tiny scene in Chromium."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import minimal_config, write_clip

from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videogen import request_hash
from vidgen.videogen.inputs import SceneRender, make_inputs
from vidgen.videogen.shots import GUIDE_PROMPTS, NO_HOST_BLOCKED, plan_shots, project_shots
from test_videogen_shots import CATALOG
from test_videogen_host import fake_cloudflared  # noqa: F401 - the fixture

OBJECTS = [
    {"id": "crate", "shape": "box", "color": "#d08040", "size": 1.0, "position": [0, 0.5, 0]},
    {"id": "ana", "shape": "standin", "name": "Ana", "position": [-1.5, 0.8, 0]},
    {"id": "ben", "shape": "standin", "position": [1.5, 0.8, 0]},
]
SHEET = {"prompt": "a tall woman in a yellow raincoat", "views": ["front"]}


def guide_config(guide: Any = "depth", scene_type: str = "3d", **shot: Any) -> dict[str, Any]:
    """A 9:16 project: one scene with a floor, a box and two stand-ins, one action shot."""
    params = {"floor": True, "camera": {"position": [0, 2.5, 6], "look_at": "crate"}, "objects": OBJECTS} if scene_type == "3d" else {"text": "x"}
    return minimal_config(
        format={"width": 1080, "height": 1920, "fps": 30},
        characters=[{"name": "ana", "reference_sheet": SHEET}],
        videogen={"provider": "mock", "budget_usd": 2.0},
        scenes=[{"id": "plaza", "type": scene_type, "params": params, "beats": [{
            "id": "act", "text": "Ana walks to the crate.",
            "generated_shot": {"kind": "action", "model": "bytedance/seedance-2.0-fast", "characters": ["ana"], "guide": guide, **shot},
        }]}],
    )


def lossless_clip(path: Path, seconds: float, size: str, fps: int, color: str = "0x40c040") -> Path:
    """A flat-coloured FFV1 clip (a stand-in for a lossless guide pass)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    source = f"color=c={color}:s={size}:r={fps}:d={seconds}"
    subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", source, "-c:v", "ffv1", "-pix_fmt", "bgr0", str(path)], check=True)
    return path


# ----- config and validation ---------------------------------------------------------------------


@pytest.mark.parametrize(("value", "source"), [(True, "render"), ("render", "render"), (False, None), ("depth", "depth"), ("outline", "outline"), ("mask", "mask"), ("yes", "render")])
def test_guide_values(make_project, value: Any, source: str | None) -> None:
    spec = Project.load(make_project(guide_config(value))).config.scenes[0].beats[0].generated_shot
    assert spec is not None and spec.guide_source == source


def test_unknown_guide_is_refused_with_did_you_mean(make_project) -> None:
    with pytest.raises(VidgenError, match=r"'dpeth' is not true, false, render, depth, outline, mask \(did you mean depth\?\)"):
        Project.load(make_project(guide_config("dpeth")))


def test_a_pass_needs_a_3d_scene(make_project) -> None:
    with pytest.raises(VidgenError, match=r"guide: mask is a guide pass of a 3d scene, but scene 'plaza' is a text_card scene; use guide: true"):
        Project.load(make_project(guide_config("mask", scene_type="text_card")))
    Project.load(make_project(guide_config(True, scene_type="text_card"), folder="ok"))   # the render guide works anywhere


# ----- shots, prompt, hash -------------------------------------------------------------------------


@pytest.mark.slow
def test_the_shot_sends_the_pass_and_says_what_it_is(make_project) -> None:
    project = Project.load(make_project(guide_config("depth")))
    (shot,) = project_shots(project, CATALOG)
    (guide,) = [i for i in shot.inputs if i.role == "guide"]
    assert guide.path == project.root / "build" / "videogen" / "act" / "guide.depth.mp4" and guide.kind == "video"
    assert guide.what.startswith("depth pass of the beat's 3D scene")
    assert GUIDE_PROMPTS["depth"] + "." in shot.prompt and "Mask colours" not in shot.prompt
    render = project_shots(Project.load(make_project(guide_config(True), folder="r")), CATALOG)[0]
    assert render.inputs[-1].path.name == "guide.mp4" and "The guide video is" not in render.prompt


def test_a_mask_guide_lists_the_stand_ins_colours(make_project) -> None:
    from test_scene_3d_passes import describe

    from vidgen.three_d.passes import mask_colors
    from vidgen.three_d.spec import Scene3DParams

    project = Project.load(make_project(guide_config("mask")))
    (shot,) = project_shots(project, CATALOG)
    colors = mask_colors(describe(Scene3DParams.model_validate(project.config.scenes[0].params))[0])   # the real description's table
    assert f"Mask colours: Ana {colors['ana']}, Ben {colors['ben']}." in shot.prompt
    assert GUIDE_PROMPTS["mask"] in shot.prompt and shot.prompt.index(GUIDE_PROMPTS["mask"]) < shot.prompt.index("Mask colours")


def test_the_request_hash_changes_with_the_pass(make_project) -> None:
    hashes = []
    for value in (True, "depth", "outline", "mask"):
        root = make_project(guide_config(value), folder=f"p_{value}")
        (shot,) = project_shots(Project.load(root), CATALOG)
        for item in shot.inputs:   # the same bytes in every input: only the guide choice differs
            item.path.parent.mkdir(parents=True, exist_ok=True)
            item.path.write_bytes(item.role.encode())
        hashes.append(request_hash(shot.request()))
    assert len(set(hashes)) == 4


# ----- the plan ------------------------------------------------------------------------------------


def test_plan_names_the_pass_and_shares_it(make_project, fake_cloudflared: list[str]) -> None:
    unhosted = guide_config("depth")
    unhosted["videogen"] = {"provider": "openrouter", "budget_usd": 2.0}
    root = make_project(unhosted)
    (item,) = plan_shots(Project.load(root), catalog=CATALOG).shots
    text = "\n".join(item.lines(root))
    assert "  guide: build/videogen/act/guide.depth.mp4 (depth pass of the beat's 3D scene" in text and "not made yet" in text
    assert NO_HOST_BLOCKED in item.shot.blocked and "inputs not made yet: `vidgen generate inputs --guide`" in item.shot.blocked
    hosted = guide_config("depth")
    hosted["videogen"] = {"provider": "openrouter", "budget_usd": 2.0, "host": "quick_tunnel", "cloudflared": fake_cloudflared[1]}
    root = make_project(hosted, folder="hosted")
    (item,) = plan_shots(Project.load(root), catalog=CATALOG).shots
    text = "\n".join(item.lines(root))
    assert [i.path.name for i in item.shot.shared] == ["guide.depth.mp4"] and NO_HOST_BLOCKED not in item.shot.blocked
    assert "would share through a public Cloudflare quick tunnel" in text and "    build/videogen/act/guide.depth.mp4 (not made yet)" in text


# ----- inputs ----------------------------------------------------------------------------------


@pytest.mark.slow
def test_inputs_convert_the_pass_cut_like_the_render(make_project) -> None:
    from vidgen.render.ffmpeg import probe

    root = make_project(guide_config("depth", first_frame="render"))
    project = Project.load(root)
    (shot,) = project_shots(project, CATALOG)
    video = write_clip(root / "fake" / "plaza.mp4", seconds=6.0, size="54x96", fps=5, audio=False)
    depth = lossless_clip(root / "fake" / "plaza.depth.mkv", 6.0, "54x96", 5)
    asked: list[tuple[str, tuple[str, ...]]] = []

    def render(_project: Project, scene_id: str, passes: tuple[str, ...]) -> SceneRender:
        asked.append((scene_id, passes))
        return SceneRender(video, {"act": 1.0}, {"depth": depth})

    lines: list[str] = []
    written = make_inputs(project, [shot], guide=True, out=lines.append, render=render)
    assert asked == [("plaza", ("depth",))]
    assert [p.name for p in written] == ["guide.depth.mp4", "first_frame.png", "overlay.png", "overlay.last.png"]
    folder = root / "build" / "videogen" / "act"
    info = probe(folder / "guide.depth.mp4")
    assert info.duration == pytest.approx(shot.length, abs=0.25) and (info.width, info.height) == (54, 96)
    stream = json.loads(subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,pix_fmt,nb_frames", "-of", "json", str(folder / "guide.depth.mp4")],
        check=True, capture_output=True, text=True,
    ).stdout)["streams"][0]
    assert stream["codec_name"] == "h264" and stream["pix_fmt"] == "yuv420p" and int(stream["nb_frames"]) == math.ceil(shot.length * 5 - 1e-9)   # as -t cuts guide.mp4
    assert not (folder / "guide.mp4").exists() and any("the depth pass" in line for line in lines)
    from PIL import Image

    frame = np.asarray(Image.open(folder / "first_frame.png").convert("RGB"))
    assert abs(int(frame[..., 1].mean()) - int(frame[..., 0].mean())) < 3   # the grey render, not the green pass
    with pytest.raises(VidgenError, match="drew no depth pass"):
        make_inputs(project, [shot], guide=True, out=lambda line: None, render=lambda p, s, m: SceneRender(video, {"act": 1.0}))


# ----- a real render (Chromium) ----------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.render
def test_generate_inputs_renders_the_mask_pass(make_project) -> None:
    from test_scene_3d_passes import _chromium_or_skip, _frames

    _chromium_or_skip()
    data = guide_config("mask")
    data.update(format={"width": 320, "height": 180, "fps": 10}, draft={"width": 160, "height": 90, "fps": 5})
    data["characters"] = [{"name": "ana"}]
    data["scenes"][0]["beats"][0]["generated_shot"].pop("characters")
    root = make_project(data)
    project = Project.load(root)
    (shot,) = project_shots(project, CATALOG)
    written = make_inputs(project, [shot], guide=True, out=lambda line: None)
    assert [p.name for p in written] == ["guide.mask.mp4"]
    frames = _frames(written[0])
    assert len(frames) == math.ceil(shot.length * 5 - 1e-9) and frames[0].shape == (90, 160, 3)
    folder = root / "build" / "draft" / "three_d"
    table = json.loads((folder / "plaza.mask-colors.json").read_text(encoding="utf-8"))["colors"]
    lossless = _frames(folder / "plaza.mask.mkv")[0]
    crate = np.array([int(table["crate"][i:i + 2], 16) for i in (1, 3, 5)])
    inside = np.all(lossless == crate, axis=2)
    inside &= np.roll(inside, 2, 0) & np.roll(inside, -2, 0) & np.roll(inside, 2, 1) & np.roll(inside, -2, 1)   # away from edges
    assert inside.sum() > 20
    error = np.abs(frames[0][inside].astype(int) - crate).max()
    assert error <= 6   # yuv420p at CRF 12: flat colours stay within a few levels inside an object
    again = make_inputs(project, [shot], guide=True, out=lambda line: None)   # the draft render is reused
    assert [p.name for p in again] == ["guide.mask.mp4"]
    (item,) = plan_shots(Project.load(root), catalog=CATALOG).shots
    assert not any(b.startswith("inputs changed") for b in item.shot.blocked)   # the worker's fingerprint is the plan's


# ----- docs and example ------------------------------------------------------------------------------


def test_cookbook_example_validates_and_matches_the_example(tmp_path: Path) -> None:
    import re

    from vidgen.cli import validate_all

    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "COOKBOOK-GENERATED-VIDEO.md").read_text(encoding="utf-8")
    section = text.split("## 6. From a 3D scene to a generated clip", 1)[1].split("\n## 7.", 1)[0]
    block = re.findall(r"```yaml\n(.*?)```", section, flags=re.S)[0]
    assert block in (root / "examples" / "3d-to-video" / "video.yaml").read_text(encoding="utf-8")
    (tmp_path / "video.yaml").write_text(block, encoding="utf-8")
    project = Project.load(tmp_path)
    problems, _ = validate_all(project, keep_going=True)
    assert not problems, problems
    (shot,) = project_shots(project, CATALOG)
    assert shot.spec.guide_source == "depth" and shot.first_frame_in == "guide" and shot.inputs[-1].path.name == "guide.depth.opening.mp4"
    assert "COOKBOOK-GENERATED-VIDEO.md#6-from-a-3d-scene-to-a-generated-clip" in (root / "docs" / "COOKBOOK-3D.md").read_text(encoding="utf-8")
