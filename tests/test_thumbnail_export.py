"""Thumbnails and GIF / clip export, Step 50 (DESIGN.md §53): the ``thumbnail:`` config, frame
numbers, designed cards (sizes, legibility checks, JPEG), frame thumbnails from renders (with and
without overlays), ``vidgen export gif|clip`` (palette GIF, size budget, stream copy vs encode)."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from conftest import minimal_config
from vidgen import export as ex
from vidgen import thumbnail as th
from vidgen.cli import main
from vidgen.config import FormatConfig, ThumbnailConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not found on PATH")


def silent(sid: str, seconds: float, text: str = "Card") -> dict[str, Any]:
    return {"id": sid, "type": "text_card", "params": {"text": text}, "duration": seconds}


# ----- config ------------------------------------------------------------------------------------


def test_config_kinds_and_errors() -> None:
    assert parse_config(minimal_config()).thumbnail is None
    frame = parse_config(minimal_config(thumbnail={"scene": "intro", "beat": 2, "at": 0.5, "overlays": False})).thumbnail
    assert frame is not None and (frame.kind, frame.beat, frame.at, frame.overlays) == ("frame", 2, 0.5, False)
    assert parse_config(minimal_config(thumbnail={"scene": "intro", "beat": "intro_b1"})).thumbnail.beat == "intro_b1"
    design = parse_config(minimal_config(thumbnail={"title": "Hi", "icon": "star", "jpeg": True})).thumbnail
    assert design is not None and design.kind == "design" and design.jpeg and design.auto
    assert ThumbnailConfig().kind == "design"
    bad = [
        ({"scene": "intro", "title": "x"}, "not both"),
        ({"beat": 1}, "need scene"),
        ({"icon": "star", "image": "a.png"}, "icon or an image"),
        ({"scene": "nope"}, "unknown scene 'nope'"),
        ({"scene": "intro", "beat": 3}, "has 2 beat"),
        ({"scene": "intro", "beat": "custom"}, "no beat 'custom'"),
        ({"scene": "intro", "at": -1}, "thumbnail"),
        ({"titel": "x"}, "titel"),
    ]
    for value, message in bad:
        with pytest.raises(VidgenError, match=message):
            parse_config(minimal_config(thumbnail=value))
    scenes = [silent("card", 2.0), *minimal_config()["scenes"]]
    with pytest.raises(VidgenError, match="silent"):
        parse_config(minimal_config(scenes=scenes, thumbnail={"scene": "card", "beat": 1}))


def test_thumbnail_does_not_change_scene_fingerprints(make_project) -> None:
    base = Project.load(make_project(minimal_config(), folder="a"))
    changed = Project.load(make_project(minimal_config(thumbnail={"scene": "main", "overlays": False}), folder="b"))
    assert scene_fingerprint(base, "intro") == scene_fingerprint(changed, "intro")


def test_sizes_paths_and_bare_project(make_project) -> None:
    assert th.thumbnail_size(FormatConfig()) == (1280, 720)
    assert th.thumbnail_size(FormatConfig(width=1080, height=1920)) == (1080, 1920)
    assert th.thumbnail_size(FormatConfig(width=1080, height=1080)) == (1080, 1080)
    assert th.small_size((1280, 720)) == (320, 180) and th.small_size((1080, 1920)) == (180, 320)
    overlays = [{"type": "watermark", "text": "W"}]
    root = make_project(minimal_config(output="out", overlays=overlays, variants={"v": {}}))
    project = Project.load(root, variant="v")
    assert project.thumbnail_path(True) == root / "out_v_preview_thumbnail.png"
    assert project.thumbnail_path(False, ".jpg") == root / "out_v_thumbnail.jpg"
    assert project.exports_dir == root / "exports" and project.export_stem(True) == "out_v_preview"
    bare = project.without_overlays()
    assert bare.bare and not project.bare and bare.render_dir(True) == root / "build" / "preview_v_bare"
    assert bare.config.overlays == [] and all(s.overlays is False for s in bare.config.scenes)
    assert project.config.overlays  # the original is unchanged


# ----- frame numbers -----------------------------------------------------------------------------


def _timings(fps: int = 10) -> dict[str, Any]:
    return {
        "duration": 7.0,
        "beats": [{"id": "intro_b1", "start": 0.0, "end": 2.0}, {"id": "intro_b2", "start": 2.4, "end": 5.45}],
        "render": {"fps": fps},
    }


def test_frame_number(make_project) -> None:
    project = Project.load(make_project(minimal_config(narration={"pad": 0.35})))
    spec = lambda **kw: ThumbnailConfig(scene="intro", **kw)  # noqa: E731
    # the beat's last frame: start + (narration + pad), capped by the next beat's start
    assert th.frame_number(project, spec(beat=1), _timings(), 0.5) == (23, "intro_b1")
    assert th.frame_number(project, spec(beat="intro_b2"), _timings(), 0.5) == (24 + 34 - 1, "intro_b2")
    assert th.frame_number(project, spec(), _timings(), 0.5) == (57, "intro_b2")  # default: the last beat's end
    assert th.frame_number(project, spec(beat=2, at=1.0), _timings(), 0.5) == (34, "intro_b2")
    assert th.frame_number(project, spec(at=1.25), _timings(), 0.5) == (12, None)
    with pytest.raises(VidgenError, match="past the end of scene 'intro'"):
        th.frame_number(project, spec(at=7.0), _timings(), 0.5)
    scenes = [silent("card", 3.0), *minimal_config()["scenes"]]
    card = Project.load(make_project(minimal_config(scenes=scenes), folder="silent"))
    timings = {"duration": 3.0, "beats": [], "render": {"fps": 10}}
    assert th.frame_number(card, ThumbnailConfig(scene="card"), timings, 0.5) == (24, None)  # before the fade-out


# ----- designed thumbnails -----------------------------------------------------------------------


def test_designed_thumbnail_landscape_with_icon_and_jpeg(make_project) -> None:
    thumb = {"title": "Saving 77% of the parameters", "subtitle": "a short tour", "icon": "star", "jpeg": True}
    root = make_project(minimal_config(output="out", thumbnail=thumb))
    result = th.make_thumbnail(Project.load(root))
    assert result.kind == "design" and result.path == root / "out_thumbnail.png" and result.rendered == []
    with Image.open(result.path) as image:
        assert image.size == (1280, 720) and image.mode == "RGB"
    with Image.open(result.small) as small:
        assert small.size == (320, 180)
    assert result.jpeg == root / "out_thumbnail.jpg" and result.jpeg_bytes is not None and result.jpeg_bytes < th.MAX_BYTES
    assert result.source["title_px"] * 320 / 1280 >= th.MIN_TITLE_SMALL_PX
    assert [c.rule for c in result.checks] == []
    # without jpeg the old JPEG goes (it would show another thumbnail)
    th.make_thumbnail(Project.load(root), jpeg=False)
    assert not (root / "out_thumbnail.jpg").exists()


def test_designed_thumbnail_vertical_preset_and_background(make_project) -> None:
    root = make_project(
        minimal_config(
            output="out",
            format={"width": 1080, "height": 1920, "fps": 30},
            thumbnail={"title": "Short", "preset": "light_academic", "background": "#FFFFFF"},
        )
    )
    result = th.make_thumbnail(Project.load(root))
    with Image.open(result.path) as image:
        assert image.size == (1080, 1920)
        assert image.getpixel((5, 5)) == (255, 255, 255)
        dark = min(sum(image.getpixel((x, y))) for x in range(0, 1080, 9) for y in range(700, 1900, 9))
    assert dark < 200  # dark title text on the white card
    assert result.source["background"] == "#FFFFFF" and result.checks == []
    with Image.open(result.small) as small:
        assert small.size == (180, 320)


def test_designed_checks_flag_long_titles_and_low_contrast(make_project) -> None:
    long_title = " ".join(["Extraordinarily"] * 14)
    root = make_project(minimal_config(thumbnail={"title": long_title, "subtitle": "x"}))
    result = th.make_thumbnail(Project.load(root))
    rules = {c.rule: c.severity for c in result.checks}
    assert rules == {"fit": "warning", "max_words": "info"}
    assert result.source["title_lines"][-1].endswith("…")
    # the checks themselves
    block = th._TextBlock(None, 40, ["a"], 44.0)
    checks = th._design_checks("one two", block, block, "#777777", "#808080", "#888888", 0.25)
    assert {(c.rule, c.severity) for c in checks} == {("min_font", "warning"), ("contrast", "warning")}
    assert len([c for c in checks if c.rule == "contrast"]) == 2


def test_thumbnail_problems(make_project) -> None:
    from vidgen import extensions

    thumb = {"title": "x", "icon": "no-such-icon", "background": "nocolor"}
    root = make_project(minimal_config(thumbnail=thumb), folder="a")
    project = Project.load(root)
    with extensions.project_session(project) as theme:
        problems = {p.location: p.message for p in th.thumbnail_problems(project, theme)}
    assert set(problems) == {"thumbnail.icon", "thumbnail.background"} and "unknown icon" in problems["thumbnail.icon"]
    root = make_project(minimal_config(thumbnail={"image": "assets/missing.png", "preset": "nope"}), folder="b")
    project = Project.load(root)
    with extensions.project_session(project) as theme:
        problems = {p.location: p.message for p in th.thumbnail_problems(project, theme)}
    assert "file not found" in problems["thumbnail.image"] and "unknown theme preset 'nope'" in problems["thumbnail.preset"]


def test_validate_reports_thumbnail_problems(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(thumbnail={"icon": "no-such-icon"}))
    assert main(["validate", str(root), "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert [p["location"] for p in doc["problems"]] == ["thumbnail.icon"]


def test_designed_thumbnail_with_image(make_project) -> None:
    root = make_project(minimal_config(thumbnail={"title": "Photo", "image": "assets/pic.png"}))
    (root / "assets").mkdir()
    Image.new("RGB", (400, 300), (200, 30, 30)).save(root / "assets" / "pic.png")
    result = th.make_thumbnail(Project.load(root))
    with Image.open(result.path) as image:
        assert image.getpixel((1270, 360)) == (200, 30, 30)  # the picture fills the right panel
        assert image.getpixel((5, 5)) != (200, 30, 30)


def test_cli_thumbnail_json_and_usage(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(output="out"))
    assert main(["thumbnail", str(root), "--json", "--jpeg"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "thumbnail" and doc["ok"] and doc["kind"] == "design"
    assert (doc["width"], doc["height"]) == (1280, 720) and doc["source"]["title"] == "Test video"
    assert Path(doc["path"]) == root / "out_thumbnail.png" and Path(doc["jpeg"]).is_file() and Path(doc["small"]).is_file()
    assert doc["checks"] == [] and doc["rendered"] == []
    assert main(["thumbnail", str(root), "--beat", "2"]) == 1
    assert "add --scene" in capsys.readouterr().err
    assert main(["thumbnail", str(root), "--scene", "intro", "--beat", "5"]) == 1
    assert "has 2 beat" in capsys.readouterr().err


# ----- export: ranges, names, budget -------------------------------------------------------------


def _video_timings() -> dict[str, Any]:
    return {"duration": 10.0, "scenes": [{"id": "a", "start": 0.0, "duration": 4.0}, {"id": "b", "start": 4.0, "duration": 6.0}]}


def test_resolve_range() -> None:
    t = _video_timings()
    assert ex.resolve_range(t, "b", None, None) == (4.0, 10.0)
    assert ex.resolve_range(t, "b", 1.5, 3.0) == (5.5, 7.0)
    assert ex.resolve_range(t, "a", 1.0, 99.0) == (1.0, 4.0)  # kept within the scene
    assert ex.resolve_range(t, None, 2.0, 5.0) == (2.0, 5.0)
    assert ex.resolve_range(t, None, None, None) == (0.0, 10.0)
    for scene, start, end, message in (("c", None, None, "unknown scene 'c'"), ("a", 4.0, None, "nothing to export"), (None, 3.0, 2.0, "nothing")):
        with pytest.raises(VidgenError, match=message):
            ex.resolve_range(t, scene, start, end)
    with pytest.raises(VidgenError, match="negative"):
        ex.resolve_range(t, "b", -1.0, None)


def test_default_paths(make_project) -> None:
    project = Project.load(make_project(minimal_config(output="out")))
    assert ex.default_path(project, True, "gif", "intro", None, None) == project.root / "exports" / "out_preview_intro.gif"
    assert ex.default_path(project, False, "clip", "intro", 1.5, None).name == "out_intro_1.5-ends.mp4"
    assert ex.default_path(project, False, "clip", None, None, 4.0).name == "out_video_0-4s.mp4"


def test_next_try_lowers_fps_then_width() -> None:
    width, fps = ex.next_try(480, 12.0, 4_000_000, 1_000_000)
    assert fps < 12 and width < 480 and width**2 * fps < 0.3 * 480**2 * 12
    assert ex.next_try(ex.MIN_GIF_WIDTH, ex.MIN_GIF_FPS, 4_000_000, 1_000_000) == (ex.MIN_GIF_WIDTH, ex.MIN_GIF_FPS)
    width, fps = ex.next_try(480, float(ex.MIN_GIF_FPS), 2_000_000, 1_000_000)
    assert fps == ex.MIN_GIF_FPS and width < 480


def test_export_without_a_render(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config())
    assert main(["export", "gif", str(root), "--scene", "intro"]) == 1
    assert "run `vidgen render` first" in capsys.readouterr().err
    assert main(["export", "gif", str(root), "--with-audio"]) == 1
    assert "a GIF has no sound" in capsys.readouterr().err
    assert main(["export", "clip", str(root), "--max-mb", "2"]) == 1
    assert "--max-mb is for GIFs" in capsys.readouterr().err
    assert main(["export", "movie", str(root)]) == 2


# ----- rendered ----------------------------------------------------------------------------------

FPS = 10


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A rendered preview (160x90 @ 10 fps, no audio) with a frame thumbnail of intro's beat 2."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not found on PATH")
    import yaml

    from vidgen import hooks, registry, runtime
    from vidgen.render.pipeline import render_project

    root = tmp_path_factory.mktemp("thumb") / "proj"
    root.mkdir()
    config = minimal_config(
        output="out",
        preview={"width": 160, "height": 90, "fps": FPS},
        thumbnail={"scene": "intro", "beat": 2},
        overlays=[{"type": "progress_bar", "position": "bottom"}],
    )
    (root / "video.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with registry.isolated(), hooks.isolated():
        result = render_project(Project.load(root), preview=True, no_audio=True)
    runtime.clear_context()
    assert result.thumbnail is not None
    (root / "result.json").write_text(
        json.dumps({"rendered": result.thumbnail.rendered, "source": result.thumbnail.source, "path": str(result.thumbnail.path)}),
        encoding="utf-8",
    )
    return root


@pytest.mark.render
def test_render_writes_the_frame_thumbnail(rendered: Path) -> None:
    info = json.loads((rendered / "result.json").read_text(encoding="utf-8"))
    assert Path(info["path"]) == rendered / "out_preview_thumbnail.png"
    assert info["rendered"] == []  # the scene's render was current: reused
    timings = json.loads((rendered / "build" / "preview" / "timings" / "intro.json").read_text(encoding="utf-8"))
    beat = timings["beats"][1]
    pad = 0.35
    assert info["source"]["frame"] == round(beat["start"] * FPS) + round((beat["end"] - beat["start"] + pad) * FPS) - 1
    assert info["source"]["beat"] == "intro_b2" and info["source"]["overlays"] is True
    with Image.open(info["path"]) as image:
        assert image.size == (1280, 720)


@pytest.mark.render
@pytest.mark.slow
def test_frame_thumbnail_without_overlays(rendered: Path) -> None:
    project = Project.load(rendered)
    spec = ThumbnailConfig(scene="main", overlays=False)
    bare = th.make_thumbnail(project, preview=True, spec=spec)
    assert bare.rendered == ["main"] and (rendered / "build" / "preview_bare" / "scenes" / "main.mp4").is_file()
    assert th.make_thumbnail(project, preview=True, spec=spec).rendered == []  # current now
    with Image.open(bare.path) as image:
        without = image.crop((0, 700, 1280, 720)).convert("L").getextrema()
    drawn = th.make_thumbnail(project, preview=True, spec=ThumbnailConfig(scene="main"))
    with Image.open(drawn.path) as image:
        with_bar = image.crop((0, 700, 1280, 720)).convert("L").getextrema()
    assert with_bar[1] > without[1] + 40  # the progress bar along the bottom edge only with overlays


@pytest.mark.render
@needs_ffmpeg
def test_export_gif_palette_and_budget(rendered: Path, caplog: pytest.LogCaptureFixture) -> None:
    project = Project.load(rendered)
    result = ex.export_gif(project, preview=True, scene="intro", width=120, fps=5)
    assert result.path == rendered / "exports" / "out_preview_intro.gif" and result.method == "palette"
    timings = json.loads((rendered / "build" / "preview" / "timings.json").read_text(encoding="utf-8"))
    intro = timings["scenes"][0]
    assert (result.start, result.end) == (0.0, intro["duration"])
    with Image.open(result.path) as gif:
        assert gif.format == "GIF" and gif.mode == "P" and gif.size == (120, 68) and gif.info.get("loop") == 0
        assert abs(gif.n_frames - intro["duration"] * 5) <= 1
    part = ex.export_gif(project, preview=True, scene="main", start=0.5, end=1.5, fps=5)
    with Image.open(part.path) as gif:
        assert gif.n_frames == 5 and gif.size[0] == 160  # never wider than the video
    with caplog.at_level(logging.WARNING, logger="vidgen"):
        tight = ex.export_gif(project, preview=True, scene="intro", width=160, fps=10, max_mb=0.0005)
    assert len(tight.attempts) > 1 and tight.within_budget is False
    sizes = [(a["width"], a["fps"]) for a in tight.attempts]
    assert sizes[0] == (160, 10) and sizes[-1][0] <= sizes[0][0] and sizes[-1][1] < sizes[0][1]
    assert any("over --max-mb" in r.getMessage() for r in caplog.records)
    loose = ex.export_gif(project, preview=True, scene="intro", max_mb=50)
    assert len(loose.attempts) == 1 and loose.within_budget is True


@pytest.mark.render
@needs_ffmpeg
def test_export_clip_copy_or_encode(rendered: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from vidgen.render.ffmpeg import probe

    project = Project.load(rendered)
    timings = json.loads((rendered / "build" / "preview" / "timings.json").read_text(encoding="utf-8"))
    main_scene = timings["scenes"][1]
    copy = ex.export_clip(project, preview=True, scene="main", audio=True)
    assert copy.method == "copy" and copy.start == pytest.approx(main_scene["start"])
    info = probe(copy.path)
    assert (info.width, info.height) == (160, 90)
    assert round(info.duration * FPS) == round(main_scene["duration"] * FPS)
    import av

    with av.open(str(copy.path)) as container:
        assert len(container.streams.audio) == 1
    encoded = ex.export_clip(project, preview=True, scene="main", start=0.35, end=1.35, width=80)
    assert encoded.method == "encode" and (encoded.width, encoded.height) == (80, 46)
    assert abs(probe(encoded.path).duration - 1.0) <= 1 / FPS
    with av.open(str(encoded.path)) as container:
        assert len(container.streams.audio) == 0
    # the CLI, absolute times without a scene
    assert main(["export", "clip", str(rendered), "--preview", "--from", "1", "--to", "2", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] and doc["kind"] == "clip" and doc["scene"] is None and (doc["start"], doc["end"]) == (1.0, 2.0)
    assert Path(doc["path"]).name == "out_preview_video_1-2s.mp4"
