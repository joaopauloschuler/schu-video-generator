"""Step 137: fast drafts (``vidgen render --draft``): the draft format, its own build folder and
output names, the decoration a draft leaves out, and timings that stay those of the video."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of, room_project
from vidgen.cartoon.lighting import light_grade
from vidgen.cartoon.shading import StageLight
from vidgen.cartoon.storm import Strike
from vidgen.cli import UsageError, build_parser
from vidgen.config import DraftConfig, FormatConfig, draft_format
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.render.pipeline import _usable_render
from vidgen.render.worker import build_parser as worker_parser
from vidgen.render.worker import scene_timings_path, scene_video_path

# ----- the draft format ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("width", "height", "fps", "expected"),
    [
        (1920, 1080, 30, (426, 240, 8)),    # 16:9
        (1280, 720, 24, (426, 240, 8)),
        (1080, 1920, 30, (240, 426, 8)),    # 9:16
        (1080, 1080, 30, (240, 240, 8)),    # 1:1
        (1440, 1080, 30, (320, 240, 8)),    # 4:3
        (160, 90, 5, (160, 90, 5)),         # never larger or faster than the video
    ],
)
def test_a_draft_is_240_pixels_on_its_shorter_side_at_8_fps(width: int, height: int, fps: int, expected: tuple[int, int, int]) -> None:
    fmt = draft_format(FormatConfig(width=width, height=height, fps=fps))
    assert (fmt.width, fmt.height, fmt.fps) == expected
    assert fmt.width % 2 == 0 and fmt.height % 2 == 0


def test_draft_settings_win_and_must_be_even_and_given_in_pairs() -> None:
    video = FormatConfig()
    assert draft_format(video, DraftConfig(fps=12)) == FormatConfig(width=426, height=240, fps=12)
    assert draft_format(video, DraftConfig(width=320, height=180)) == FormatConfig(width=320, height=180, fps=8)
    with pytest.raises(ValidationError, match="even"):
        DraftConfig(width=321, height=180)
    with pytest.raises(ValidationError, match="both width and height"):
        DraftConfig(width=320)


def test_a_project_draft_follows_its_variant_format(make_project) -> None:
    data = minimal_config(variants={"vertical": {"format": {"width": 1080, "height": 1920}}, "slow": {"draft": {"fps": 4}}})
    root = make_project(data)
    assert Project.load(root, draft=True).render_format(True) == FormatConfig(width=426, height=240, fps=8)
    assert Project.load(root, "vertical", draft=True).render_format(False) == FormatConfig(width=240, height=426, fps=8)
    assert Project.load(root, "slow", draft=True).render_format(True).fps == 4
    plain = Project.load(root)
    assert plain.render_format(True) == plain.config.preview and plain.render_format(False) == plain.config.format


# ----- folders and names: never mixed with previews or final renders ------------------------------------------


def test_a_draft_has_its_own_build_folder_and_output_names(make_project) -> None:
    root = make_project(minimal_config(output="film", variants={"vertical": {"format": {"width": 1080, "height": 1920}}}))
    final, draft = Project.load(root), Project.load(root, draft=True)
    for preview in (False, True):
        assert draft.render_dir(preview) == root / "build" / "draft"
        assert draft.output_path(preview).name == "film_draft.mp4"
        assert draft.srt_path(preview).name == "film_draft.srt"
        assert draft.chapters_path(preview).name == "film_draft_chapters.txt"
        assert draft.thumbnail_path(preview).name == "film_draft_thumbnail.png"
        assert draft.export_stem(preview) == "film_draft"
    assert {final.render_dir(False), final.render_dir(True)} == {root / "build" / "final", root / "build" / "preview"}
    assert (final.output_path().name, final.output_path(True).name) == ("film.mp4", "film_preview.mp4")
    vertical = Project.load(root, "vertical", draft=True)
    assert vertical.render_dir(True) == root / "build" / "draft_vertical"
    assert vertical.output_path(True).name == "film_vertical_draft.mp4"
    bare = draft.without_overlays()
    assert bare.draft and bare.render_dir(True) == root / "build" / "draft_bare"


def _fake_render(project: Project, preview: bool, scene_id: str) -> None:
    fmt = project.render_format(preview)
    video = scene_video_path(project, preview, scene_id)
    video.parent.mkdir(parents=True)
    video.write_bytes(b"")
    timings = scene_timings_path(project, preview, scene_id)
    timings.parent.mkdir(parents=True)
    render = {"width": fmt.width, "height": fmt.height, "fps": fmt.fps, "audio": True, "fingerprint": scene_fingerprint(project, scene_id)}
    timings.write_text(json.dumps({"render": render}), encoding="utf-8")


def test_a_draft_never_reuses_a_preview_render_nor_a_preview_a_draft(make_project) -> None:
    """Even when a preview is made at the draft's size and rate (same width, height, fps), the
    renders sit in different folders, so neither is taken for the other."""
    root = make_project(minimal_config(preview={"width": 426, "height": 240, "fps": 8}))
    preview, draft = Project.load(root), Project.load(root, draft=True)
    assert preview.render_format(True) == draft.render_format(True)
    _fake_render(preview, True, "intro")
    assert _usable_render(preview, True, "intro", no_audio=False)
    assert not _usable_render(draft, True, "intro", no_audio=False)
    _fake_render(draft, True, "main")
    assert _usable_render(draft, True, "main", no_audio=False)
    assert not _usable_render(preview, True, "main", no_audio=False)
    assert not (root / "build" / "final").exists()


def test_the_draft_setting_does_not_make_other_renders_stale(make_project) -> None:
    before = scene_fingerprint(Project.load(make_project(minimal_config())), "intro")
    after = scene_fingerprint(Project.load(make_project(minimal_config(draft={"fps": 6}))), "intro")
    assert before == after


def test_render_takes_draft_or_preview_not_both() -> None:
    args = build_parser().parse_args(["render", ".", "--draft"])
    assert args.draft and not args.preview
    with pytest.raises(UsageError, match="not allowed with argument --draft"):
        build_parser().parse_args(["render", ".", "--draft", "--preview"])
    assert worker_parser().parse_args([".", "intro", "--quality", "draft"]).quality == "draft"


@pytest.mark.render
def test_the_mcp_render_tool_makes_a_draft(tmp_path: Path) -> None:
    """MCP ``render`` with ``draft: true`` (its ``preview`` left at its default, true) renders a
    draft: the draft's format and file names, no preview render."""
    from test_mcp import doc_of, run_session, tiny_project

    root = tmp_path / "root"
    tiny_project(root / "proj")

    async def body(client: Any) -> None:
        doc = doc_of(await client.call_tool("render", {"project": "proj", "draft": True, "no_audio": True}))
        assert doc["draft"] is True and doc["preview"] is True
        assert doc["format"] == {"width": 160, "height": 90, "fps": 8}
        assert Path(doc["outputs"]["video"]).name == "out_draft.mp4"

    run_session(root, body)
    assert (root / "proj" / "build" / "draft").is_dir() and not (root / "proj" / "build" / "preview").exists()


def test_the_pipeline_asks_the_worker_for_a_draft(make_project, monkeypatch) -> None:
    from vidgen.render import pipeline

    seen: list[list[str]] = []

    class Stopped(Exception):
        pass

    def popen(cmd: list[str], **kwargs: Any) -> Any:
        seen.append(cmd)
        raise Stopped

    monkeypatch.setattr(pipeline.subprocess, "Popen", popen)
    with pytest.raises(Stopped):
        pipeline._run_worker(Project.load(make_project(minimal_config()), draft=True), True, "intro", no_audio=True, live=False)
    quality = seen[0][seen[0].index("--quality") + 1]
    assert quality == "draft"


# ----- what a draft leaves out ------------------------------------------------------------------------------


class _Camera:
    def get_fill_rgbas(self, vmobject: Any) -> Any:
        return "fill"

    def get_stroke_rgbas(self, vmobject: Any, *args: Any, **kwargs: Any) -> Any:
        return "stroke"

    def display_image_mobject(self, image: Any, pixels: Any) -> Any:
        return "image"


def test_a_flat_light_grades_nothing_and_never_flashes_but_keeps_its_changes() -> None:
    camera = _Camera()
    light = StageLight(camera, light_grade("night"), flat=True)
    assert camera.get_fill_rgbas.__func__ is _Camera.get_fill_rgbas   # the camera is not wrapped
    light.change(light_grade("day"), 1.0, 2.0)
    light.strikes.append(Strike(0.5, 0.5, 1.0, 3, True))
    light.update(0.6)
    assert light.flash == 0.0 and not light.changing(0.0, 0.9)
    assert light.changing(1.5, 1.6) and not light.settled(2.5) and light.settled(3.1)
    graded = StageLight(_Camera(), light_grade("night"))
    graded.strikes.append(Strike(0.5, 0.5, 1.0, 3, True))
    assert graded.changing(0.0, 0.9)


DECORATED: dict[str, Any] = {
    "light": "night",
    "wind": "windy",
    "fog": True,
    "particles": [{"kind": "rain", "lightning": 3, "puddles": True}],
    "props": [{"prop": "tree", "at": 0.85, "depth": 0.3}],
    "characters": [{"name": "pip", "at": 0.2}, {"name": "kit", "at": 0.6}],
}
BEATS = [
    {"text": "Pip runs across the wet grass to the tree.", "actions": [{"run_to": "pip", "to": 0.7}]},
    {"text": "Then the evening grows dark and lightning strikes.", "actions": [{"light": "day", "run_time": 1.0}, {"lightning": "left", "distance": 1.0}]},
]


def _rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_rounded(v) for v in value]
    return value


@pytest.mark.render
def test_a_draft_leaves_out_the_decoration_and_keeps_every_timing(make_project, tmp_path: Path, monkeypatch) -> None:
    """The same stage rendered normally and as a draft (both 160x90 at 5 fps here): the draft has
    no idle motion, nothing swaying or trailing, no shadows, motion effects, rain drops, puddles,
    fog, bolt or graded light; its beats, sounds, ambience, light changes and the characters'
    places are the normal render's."""
    from vidgen import extensions, registry

    extensions.load_builtins()
    added: list[Any] = []
    stage = registry.get("stage").cls
    add_effect = stage._add_motion_effect
    monkeypatch.setattr(stage, "_add_motion_effect", lambda self, effect, mover, behind: (added.append(effect), add_effect(self, effect, mover, behind=behind)))
    project = room_project(make_project, DECORATED, BEATS)
    full, full_frames = frames_of(project, tmp_path / "full", monkeypatch)
    effects = len(added)
    project.draft = True
    draft, draft_frames = frames_of(project, tmp_path / "draft", monkeypatch)
    assert not full.is_draft and draft.is_draft
    assert effects > 0 and len(added) == effects                       # no motion effects in the draft
    assert full.shadows and not draft.shadows
    assert any(c.is_idle for c in full.cast.values()) and not any(c.is_idle for c in draft.cast.values())
    assert full.blowing.props and not draft.blowing.props and not draft.blowing.characters
    assert draft.blowing.wind.level(0.0) == full.blowing.wind.level(0.0)   # balloons, blown props: same drift
    assert len(full.particles[0].drops) > 0 and draft.particles[0].drops == [] and not draft.particles[0].drawn
    assert full.puddles and not draft.puddles
    assert full.fog is not None and draft.fog is None
    assert full.bolt is not None and draft.bolt is None
    assert not full.light.flat and draft.light.flat and draft.light.flash == 0.0
    assert len(draft_frames) == len(full_frames)
    assert _rounded(draft.timings()["beats"]) == _rounded(full.timings()["beats"])   # as the worker stores them
    assert _rounded(draft.timings()["ambience"]) == _rounded(full.timings()["ambience"])
    assert _rounded([(e.sound, e.time) for e in draft.sfx_log]) == _rounded([(e.sound, e.time) for e in full.sfx_log])
    assert draft.light_marks == full.light_marks
    for name in ("pip", "kit"):
        assert draft.cast[name].feet()[0] == pytest.approx(full.cast[name].feet()[0])


@pytest.mark.render
def test_render_draft_writes_its_own_video(make_project, tmp_path: Path) -> None:
    """``vidgen render --draft`` end to end on a tiny project: the video and timings come from
    ``build/draft``, are named ``..._draft``, and no preview or final render is made."""
    from vidgen.cli import main

    root = make_project(minimal_config(output="clip", format={"width": 160, "height": 90, "fps": 5}))
    assert main(["render", str(root), "--draft", "--no-audio", "--jobs", "1"]) == 0
    video = root / "output" / "clip_draft.mp4"
    assert video.is_file() and (root / "output" / "clip_draft.srt").is_file()
    timings = json.loads((root / "build" / "draft" / "timings.json").read_text(encoding="utf-8"))
    assert timings["draft"] is True and timings["format"] == {"width": 160, "height": 90, "fps": 5}
    scene = json.loads((root / "build" / "draft" / "timings" / "intro.json").read_text(encoding="utf-8"))
    assert scene["render"]["draft"] is True
    assert not (root / "build" / "preview").exists() and not (root / "build" / "final").exists()
    assert not (root / "output" / "clip_preview.mp4").exists()


def test_scenes_know_a_draft_from_their_project(make_project) -> None:
    from vidgen import extensions, registry

    extensions.load_builtins()
    project = Project.load(make_project(minimal_config()), draft=True)
    spec = project.scene("intro")
    scene = registry.get(spec.type).cls(spec, project, extensions.activate(project))
    assert scene.is_draft
