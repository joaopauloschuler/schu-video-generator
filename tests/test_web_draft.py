"""A draft of a video with `web` scenes (`vidgen render --draft`, DESIGN.md §74 and §118.18): the
page is drawn at the draft's size and frame rate into the draft's own folder, with `design_width`
too; lint and the storyboard never use a draft."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vidgen.cli import UsageError, build_parser
from vidgen.config import FormatConfig, draft_format
from vidgen.project import Project
from vidgen.web import clip as web_clip
from vidgen.web.entry import WebEntry
from vidgen.web.inputs import page_viewport

from test_scene_web import _chromium_or_skip


@pytest.mark.parametrize(("video", "design", "size", "window"), [
    ((1920, 1080), 1280, (426, 240), (1280, 722)),    # 721.13 CSS px high: rounded up
    ((1080, 1920), 390, (240, 426), (390, 693)),      # a phone page in a vertical video
    ((1080, 1080), 1000, (240, 240), (1000, 1000)),
])
def test_a_draft_draws_a_design_width_page_in_the_same_window(
        video: tuple[int, int], design: int, size: tuple[int, int], window: tuple[int, int]) -> None:
    draft = draft_format(FormatConfig(width=video[0], height=video[1], fps=30))
    assert (draft.width, draft.height, draft.fps) == (*size, 8)
    viewport, scale = page_viewport(size, design)
    assert viewport == window and scale == pytest.approx(size[0] / design)
    assert viewport[0] == page_viewport(video, design)[0][0]            # the same window width as the final render
    assert abs(viewport[1] - page_viewport(video, design)[0][1]) <= 2   # and height, but for the rounding


def test_a_drafts_web_clip_has_its_own_folder_and_key(make_project: Any, tmp_path: Path) -> None:
    root = make_project({"title": "W", "scenes": [{"id": "w", "type": "web", "params": {"page": "p.html"}, "duration": 1, "beats": []}]})
    draft, plain = Project.load(root, draft=True), Project.load(root)
    folders = {draft.render_dir(True) / "web", plain.render_dir(True) / "web", plain.render_dir(False) / "web"}
    assert {f.relative_to(root).as_posix() for f in folders} == {"build/draft/web", "build/preview/web", "build/final/web"}
    (tmp_path / "p.html").write_text("<p>", encoding="utf-8")
    keys = set()
    for fmt in (draft.render_format(True), plain.render_format(True), plain.render_format(False)):
        inputs = web_clip.clip_inputs(tmp_path, WebEntry("page", "p.html"), scene_id="w", size=(fmt.width, fmt.height), fps=fmt.fps, frames=fmt.fps)
        keys.add(json.dumps(inputs, sort_keys=True))
    assert len(keys) == 3


@pytest.mark.parametrize("command", ["lint", "storyboard"])
def test_lint_and_the_storyboard_never_use_a_draft(command: str) -> None:
    """Lint and the storyboard read the preview or the final render only: a draft makes no finding."""
    with pytest.raises(UsageError, match="unrecognized arguments: --draft"):
        build_parser().parse_args([command, ".", "--draft"])


def test_render_help_names_the_draft_for_any_video(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["render", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "--draft" in text and "240p" in text and "8 fps" in text and "web" in text and "build/draft" in text


@pytest.mark.slow
@pytest.mark.render
def test_render_draft_draws_a_design_width_page_at_the_draft_size(make_project: Any) -> None:
    _chromium_or_skip()
    import av

    from vidgen.render.pipeline import render_project

    page = ("<!doctype html><style>html { height: 100%; box-sizing: border-box; border: 40px solid #ff0000; }</style>"
            "<script>window.vidgen = {load(ctx) { if (innerWidth !== 400 || ctx.width !== 400) throw new Error('window ' + innerWidth); }};</script>")
    root = make_project({"title": "W", "format": {"width": 160, "height": 90, "fps": 10}, "draft": {"width": 96, "height": 54, "fps": 4},
                         "scenes": [{"id": "w", "type": "web", "params": {"page": "p.html", "design_width": 400}, "duration": 1, "beats": []}]})
    (root / "p.html").write_text(page, encoding="utf-8")
    project = Project.load(root, draft=True)
    render_project(project, preview=True)
    inputs = json.loads((root / "build" / "draft" / "web" / "w.json").read_text(encoding="utf-8"))["inputs"]
    assert (inputs["width"], inputs["height"], inputs["fps"], inputs["design_width"]) == (96, 54, 4, 400)
    assert not (root / "build" / "preview").exists() and not (root / "build" / "final").exists()
    with av.open(str(project.output_path(True))) as video:
        first = next(video.decode(video=0)).to_ndarray(format="rgb24").astype(int)
    assert first.shape[:2] == (54, 96) and project.output_path(True).name.endswith("_draft.mp4")
    red = (first[..., 0] > 150) & (first[..., 1] < 90)
    assert red[2, 10:-10].all() and red[-3, 10:-10].all() and not red[27, 30:66].any()   # the 40 px border, drawn about 10 px wide
