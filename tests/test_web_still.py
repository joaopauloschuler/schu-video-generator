"""Step 342: ``vidgen still`` writes single frames of a ``web`` scene's page
that equal the frames of the render's lossless page clip, without rendering the scene."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from vidgen import extensions
from vidgen.browser import chromium
from vidgen.cli import build_parser, main
from vidgen.errors import VidgenError
from vidgen.mcp_tools import cli_args
from vidgen.project import Project
from vidgen.web.still import (
    Moment,
    contact_sheet,
    frame_numbers,
    over_background,
    parse_size,
    sheet_columns,
    still_label,
    still_paths,
    still_project,
    web_scene_spec,
)

WEBCUT = '''from vidgen.api import scene
from vidgen.scenes.web import Web


@scene("web_cut")
class WebCut(Web):
    outro = 0.0
'''
#: Draws from the time alone (and ``ctx.data.t0``, the scene's place in the song).
BY_TIME = '''export function frame(t, ctx) {
  const c = ctx.canvas.getContext("2d");
  c.clearRect(0, 0, ctx.width, ctx.height);
  c.fillStyle = `rgb(${Math.round((t + ctx.data.t0) * 40)}, 90, 200)`;
  c.fillRect(0, 0, ctx.width / 2, ctx.height);
}
'''
#: Keeps state: the picture depends on how many frames were drawn before.
BY_CALLS = '''let calls = 0;
export function frame(t, ctx) {
  calls += 1;
  const c = ctx.canvas.getContext("2d");
  c.fillStyle = `rgb(${calls * 20}, 60, 60)`;
  c.fillRect(0, 0, ctx.width, ctx.height);
}
'''


def still_project_folder(make_project: Any) -> Path:
    """A ``web_cut`` scene and a ``web`` scene (in the body region under a title) drawing from
    the time, a ``web`` scene keeping state, and a ``title`` scene; 160x90 at 5 fps."""
    def web(sid: str, kind: str, script: str, **params: Any) -> dict[str, Any]:
        return {"id": sid, "type": kind, "duration": 2, "params": {"script": f"extensions/{script}.js", **params}}

    scenes = [web("a_cut", "web_cut", "time", data={"t0": 3}), web("b_body", "web", "time", data={"t0": 0}, title="Hello", region="body"),
              web("c_state", "web", "calls"), {"id": "d_title", "type": "title", "duration": 1, "params": {"title": "Hi"}}]
    root = make_project({"title": "S", "format": {"width": 160, "height": 90, "fps": 5},
                         "preview": {"width": 80, "height": 46, "fps": 5}, "transition": "cut", "scenes": scenes})
    (root / "extensions").mkdir()
    for name, text in (("webcut.py", WEBCUT), ("time.js", BY_TIME), ("calls.js", BY_CALLS)):
        (root / "extensions" / name).write_text(text, encoding="utf-8")
    return root


def test_size_names_a_quality_or_a_frame_size(make_project: Any) -> None:
    assert parse_size("final") == ("final", None) and parse_size("Preview") == ("preview", None)
    assert parse_size("640x360") == ("640x360", (640, 360)) and parse_size("320 X 180")[1] == (320, 180)
    with pytest.raises(VidgenError, match="did you mean 'preview'"):
        parse_size("prevew")
    root = still_project_folder(make_project)
    project, preview, name = still_project(root, None, "320x180")
    assert (project.config.format.width, project.config.format.height, project.config.format.fps) == (320, 180, 5)
    assert not preview and name == "320x180" and not project.draft
    assert still_project(root, None, "draft")[0].draft and still_project(root, None, "preview")[1]
    with pytest.raises(VidgenError, match="even number of pixels"):
        still_project(root, None, "321x180")


def test_frames_follow_the_order_asked_and_stay_inside_the_scene() -> None:
    def numbers(moments: list[Moment], count: int | None = None) -> list[int]:
        return frame_numbers(moments, count, fps=30, frames=92, scene_id="s")

    assert numbers([Moment("at", 1.0), Moment("frame", 7), Moment("at", 0.5)]) == [30, 7, 15]
    assert numbers([Moment("at", 0.016), Moment("at", 0.017)]) == [0, 1]   # the frame the render shows at that time
    assert numbers([], 4) == [11, 34, 57, 80] and numbers([], 1) == [46]
    with pytest.raises(VidgenError, match=r"--at 3.5: outside the scene; scene 's' has frames 0 to 91 at 30 fps \(0 to 3.033 s\)"):
        numbers([Moment("at", 3.5)])
    for moments, message in (([Moment("at", -0.1)], "--at -0.1"), ([Moment("frame", 92)], "--frame 92"), ([], "which frames")):
        with pytest.raises(VidgenError, match=message):
            numbers(moments)
    with pytest.raises(VidgenError, match="--count"):
        numbers([], 0)


def test_stills_go_to_a_file_or_a_folder(tmp_path: Path) -> None:
    def paths(numbers: list[int], out: Path | None) -> list[Path]:
        return still_paths(numbers, fps=30, scene_id="s", out=out, default_dir=tmp_path / "exports" / "stills")

    assert paths([375, 0], None) == [tmp_path / "exports" / "stills" / "s_0012.500s.png", tmp_path / "exports" / "stills" / "s_0000.000s.png"]
    assert paths([3], tmp_path / "one.PNG") == [tmp_path / "one.PNG"] and paths([3], tmp_path / "d")[0].parent == tmp_path / "d"
    with pytest.raises(VidgenError, match="2 stills were asked for: give a folder"):
        paths([3, 4], tmp_path / "one.png")
    with pytest.raises(VidgenError, match="PNG files"):
        paths([3], tmp_path / "one.jpg")


def test_the_page_is_laid_over_the_background_and_a_sheet_labels_each_still() -> None:
    pixels = np.zeros((2, 2, 4), dtype=np.uint8)
    pixels[0, 0] = (255, 0, 0, 255)
    pixels[0, 1] = (255, 0, 0, 128)
    flat = over_background(pixels, "#0000FF")
    assert flat.shape == (2, 2, 3) and tuple(flat[0, 0]) == (255, 0, 0) and tuple(flat[1, 1]) == (0, 0, 255)
    assert tuple(flat[0, 1]) == (128, 0, 127)
    assert [sheet_columns(n, None) for n in (1, 4, 5, 9, 100)] == [1, 2, 3, 3, 6] and sheet_columns(5, 2) == 2
    with pytest.raises(VidgenError, match="--columns"):
        sheet_columns(5, 0)
    assert still_label("s", 375, 30) == "s  12.500 s  f375"
    tile = np.full((90, 160, 3), 200, dtype=np.uint8)
    sheet = contact_sheet([(tile, still_label("s", n, 30)) for n in range(5)], 3)
    assert sheet.width == 480 and sheet.height > 180   # two rows of tiles with a label band each
    assert sheet.getpixel((10, 10)) == (200, 200, 200) and sheet.getpixel((330, 150)) == (0, 0, 0)   # no sixth tile
    wide = contact_sheet([(np.zeros((1080, 1920, 3), dtype=np.uint8), "x")] * 2, 4)
    assert wide.width == 1920 and wide.height < 400   # scaled down to a quarter of the sheet each


def test_the_command_line_keeps_the_order_of_at_and_frame() -> None:
    args = build_parser().parse_args(["still", "p", "--scene", "s", "--at", "1,2.5", "--frame", "7", "--at=0.25", "--size", "preview"])
    assert args.moments == [("at", 1.0), ("at", 2.5), ("frame", 7.0), ("at", 0.25)] and args.size == "preview" and args.project == "p"
    assert not args.exact and not args.transparent and args.count is None and args.out is None
    line = cli_args(["still"], ["p"], {"scene": "s", "at": [1.0, 2.5], "frame": [7], "exact": True, "sheet": None})
    assert line == ["still", "p", "--scene=s", "--at=1.0", "--at=2.5", "--frame=7", "--exact", "--json"]
    assert build_parser().parse_args(line).moments == [("at", 1.0), ("at", 2.5), ("frame", 7.0)]


def test_a_scene_that_is_unknown_or_not_a_web_scene_is_refused(make_project: Any) -> None:
    root = still_project_folder(make_project)
    project = Project.load(root)
    with extensions.project_session(project):
        assert web_scene_spec(project, "a_cut").type == "web_cut" and web_scene_spec(project, "b_body").type == "web"
        with pytest.raises(VidgenError, match=r"unknown scene 'a_cu'; did you mean 'a_cut'\? \(web scenes: a_cut, b_body, c_state\)"):
            web_scene_spec(project, "a_cu")
        with pytest.raises(VidgenError, match="'d_title' is a title scene.*vidgen storyboard --scene d_title --per-beat N"):
            web_scene_spec(project, "d_title")


@pytest.mark.slow
def test_the_command_reports_a_refusal_and_writes_nothing(make_project: Any, capsys: pytest.CaptureFixture[str]) -> None:
    root = still_project_folder(make_project)
    assert main(["still", str(root), "--at", "1"]) == 1
    assert "which scene? give --scene ID" in capsys.readouterr().err
    assert main(["still", str(root), "--scene", "d_title", "--at", "0", "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "still" and not doc["ok"] and "is a title scene" in doc["error"]["message"]
    assert not (root / "exports").exists() and not (root / "build" / "final").exists()


def _chromium_or_skip() -> None:
    pytest.importorskip("playwright.sync_api")
    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")


def _still(root: Path, *options: str) -> dict[str, Any]:
    """``vidgen still ROOT ... --json`` in a process of its own (it sets Manim's settings)."""
    run = subprocess.run([sys.executable, "-m", "vidgen", "still", str(root), *options, "--json"], capture_output=True, text=True, encoding="utf-8")
    doc = json.loads(run.stdout)
    assert doc["ok"], doc.get("error")
    return doc


def _png(path: str | Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as picture:
        return np.asarray(picture.convert("RGBA"))


def _clip_frames(path: Path) -> list[np.ndarray]:
    import av

    with av.open(str(path)) as clip:
        return [frame.to_ndarray(format="rgba") for frame in clip.decode(video=0)]


@pytest.mark.slow
@pytest.mark.render
def test_stills_equal_the_frames_of_the_rendered_page_clip(make_project: Any, tmp_path: Path) -> None:
    """The proof: the project is rendered (final and preview), and every still equals the frame
    of that number in the render's lossless page clip, for a ``Web`` subclass, for a page in the
    body region under a title and, with ``--exact``, for a page that keeps state."""
    _chromium_or_skip()
    from vidgen.render.pipeline import render_project

    root = still_project_folder(make_project)
    out = tmp_path / "stills"
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if "__pycache__" not in p.parts)
    doc = _still(root, "--scene", "a_cut", "--at", "0,0.4,1.8", "--frame", "11", "--at", "1", "--transparent", "--out", str(out),
                 "--sheet", str(out / "sheet.png"))
    wrote = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if "__pycache__" not in p.parts)
    assert [p for p in wrote if p not in before and not p.startswith("build/fonts")] == []   # nothing in the project folder
    assert (doc["width"], doc["height"], doc["fps"], doc["frames"], doc["type"], doc["size"]) == (160, 90, 5, 12, "web_cut", "final")
    assert [s["frame"] for s in doc["stills"]] == [0, 2, 9, 11, 5] and [s["time"] for s in doc["stills"]] == [0.0, 0.4, 1.8, 2.2, 1.0]
    assert doc["pages"] == 2 and Path(doc["sheet"]).is_file()   # the last still is earlier than the one before: a new page
    assert Path(doc["stills"][2]["path"]).name == "a_cut_0001.800s.png"

    project = Project.load(root)
    render_project(project)
    clip = _clip_frames(root / "build" / "final" / "web" / "a_cut.mkv")
    assert len(clip) == 12
    for still in doc["stills"]:
        assert np.array_equal(_png(still["path"]), clip[still["frame"]]), still
    assert tuple(clip[5][45, 10]) == (160, 90, 200, 255) and tuple(clip[5][45, 150]) == (0, 0, 0, 0)   # t0 = 3: (1 + 3) * 40

    # region: body under a title: the page's own box, laid over the video's background
    doc = _still(root, "--scene", "b_body", "--count", "3", "--out", str(out))
    clip = _clip_frames(root / "build" / "final" / "web" / "b_body.mkv")
    assert (doc["region"], doc["width"], doc["height"]) == ("body", clip[0].shape[1], clip[0].shape[0]) and doc["width"] < 160
    with extensions.project_session(project) as theme:
        background = str(theme.background)
    for still in doc["stills"]:
        flat = _png(still["path"])
        assert (flat[..., 3] == 255).all() and np.array_equal(flat[..., :3], over_background(clip[still["frame"]], background))

    # a page that keeps state: --exact is the render's frame; without it, the frame as if the ones before were not drawn
    clip = _clip_frames(root / "build" / "final" / "web" / "c_state.mkv")
    exact = _still(root, "--scene", "c_state", "--frame", "3,6", "--exact", "--transparent", "--out", str(out / "exact"))
    jumped = _still(root, "--scene", "c_state", "--frame", "3,6", "--transparent", "--out", str(out / "jumped"))
    for still in exact["stills"]:
        assert np.array_equal(_png(still["path"]), clip[still["frame"]])
    assert tuple(clip[6][0, 0]) == (140, 60, 60, 255)
    assert [tuple(_png(s["path"])[0, 0]) for s in jumped["stills"]] == [(20, 60, 60, 255), (40, 60, 60, 255)]

    # the preview's size and frame rate
    render_project(project, preview=True)
    clip = _clip_frames(root / "build" / "preview" / "web" / "a_cut.mkv")
    doc = _still(root, "--scene", "a_cut", "--at", "0.6,1.4", "--size", "preview", "--transparent", "--out", str(out / "preview"))
    assert (doc["width"], doc["height"]) == (80, 46)
    for still in doc["stills"]:
        assert np.array_equal(_png(still["path"]), clip[still["frame"]])
    doc = _still(root, "--scene", "a_cut", "--at", "1", "--size", "40x24", "--out", str(out / "small.png"))
    assert _png(out / "small.png").shape == (24, 40, 4) and doc["stills"][0]["path"] == str((out / "small.png").resolve())


@pytest.mark.slow
@pytest.mark.render
def test_the_mcp_tool_returns_the_sheet_and_the_stills(make_project: Any, tmp_path: Path) -> None:
    _chromium_or_skip()
    pytest.importorskip("mcp")
    from tests.test_mcp import doc_of, error_text, run_session

    root = still_project_folder(make_project)

    async def body(client: Any) -> None:
        result = await client.call_tool("still", {"project": root.name, "scene": "a_cut", "at": [0.4, 1.0], "frame": [9], "sheet": True})
        doc = doc_of(result)
        assert [s["frame"] for s in doc["stills"]] == [2, 5, 9] and doc["pages"] == 1
        assert Path(doc["sheet"]) == (root / "exports" / "stills" / "contact_sheet.png").resolve()
        assert len([c for c in result.content if c.type == "image"]) == 3   # the sheet, then two stills (the default page)
        assert doc["mcp_images"]["total"] == 4 and doc["mcp_images"]["returned"][0] == doc["sheet"]
        refused = await client.call_tool("still", {"project": root.name, "scene": "d_title", "at": [0.0]})
        assert "is a title scene" in error_text(refused)

    run_session(tmp_path, body)
