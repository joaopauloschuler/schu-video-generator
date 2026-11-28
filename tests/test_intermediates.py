"""Step 348: how a render keeps the frames ``web`` and ``3d`` scenes draw:
lossless (default) or compact (H.264 4:4:4 + a lossless alpha stream, read back by
``ClipReader``), deleted once no longer needed (``render.keep_intermediates: false``), and the
disk estimate, warning and report of ``vidgen render``."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest

from conftest import minimal_config
from test_scene_web import _fake_page
from vidgen.browser.frames_clip import ALPHA_TITLE, clip_serves, write_frames_clip
from vidgen.clips import ClipReader
from vidgen.project import Project
from vidgen.render import disk, pipeline
from vidgen.web import clip as web_clip


def _frames(n: int = 3, size: tuple[int, int] = (9, 7)) -> list[np.ndarray]:
    """Smooth RGBA frames (odd size) with an alpha ramp: opaque left, clear right."""
    w, h = size
    x = np.linspace(0, 1, w)[None, :, None]
    y = np.linspace(0, 1, h)[:, None, None]
    out = []
    for k in range(n):
        rgb = np.concatenate([80 + 100 * x + 0 * y, 60 + 120 * y + 0 * x, np.full((h, w, 1), 40.0 + 20 * k)], axis=2)
        alpha = np.broadcast_to(np.round(255 * (1 - x[..., 0]))[..., None], (h, w, 1)) + 0 * y
        out.append(np.concatenate([rgb, alpha], axis=2).round().astype(np.uint8))
    return out


def test_a_lossless_clip_serves_both_a_compact_one_only_compact() -> None:
    assert clip_serves(None, "lossless") and clip_serves(None, "compact")   # clips written before compact clips existed
    assert clip_serves("lossless", "compact") and clip_serves("compact", "compact")
    assert not clip_serves("compact", "lossless")


def test_a_compact_clip_keeps_alpha_exactly_beside_a_close_picture(tmp_path: Path) -> None:
    frames = _frames()
    path = tmp_path / "c.mkv"
    write_frames_clip(path, 5, (9, 7), frames, alpha=True, intermediate="compact")
    with av.open(str(path)) as clip:
        picture, mask = clip.streams.video
        assert (picture.codec_context.name, picture.codec_context.pix_fmt) == ("h264", "yuv444p")
        assert (mask.codec_context.name, mask.codec_context.pix_fmt, mask.metadata.get("title")) == ("ffv1", "gray", ALPHA_TITLE)
    reader = ClipReader(path, (9, 7))
    try:
        for k, frame in enumerate(frames):
            got = reader.frame(k / 5)
            assert np.array_equal(got[..., 3], frame[..., 3])
            error = np.abs(got[..., :3].astype(int) - frame[..., :3])
            assert error.mean() < 3 and error.max() <= 12   # a lossy picture, close (measured on films)
    finally:
        reader.close()


def test_a_compact_clip_without_alpha_is_one_stream_and_reads_opaque(tmp_path: Path) -> None:
    frames = [f[..., :3].copy() for f in _frames(2)]
    path = tmp_path / "o.mkv"
    write_frames_clip(path, 5, (9, 7), frames, intermediate="compact")
    with av.open(str(path)) as clip:
        assert len(clip.streams.video) == 1
    reader = ClipReader(path, (9, 7))
    try:
        assert (reader.frame(0.0)[..., 3] == 255).all()
    finally:
        reader.close()


def test_an_unknown_intermediate_is_refused(tmp_path: Path) -> None:
    from vidgen.errors import VidgenError

    with pytest.raises(VidgenError, match="unknown intermediate 'small'"):
        write_frames_clip(tmp_path / "x.mkv", 5, (4, 4), [], intermediate="small")
    assert not list(tmp_path.iterdir())


def test_a_web_clip_is_reused_across_intermediates_as_far_as_it_serves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drawn: list[str] = []
    monkeypatch.setattr(web_clip, "WebPage", _fake_page(drawn, {"p.html": ""}))
    (tmp_path / "p.html").write_text("<p>", encoding="utf-8")
    out = tmp_path / "build"

    def make(intermediate: str) -> dict[str, Any]:
        web_clip.make_web_clip(tmp_path, out, "p", {"page": "p.html"}, size=(16, 16), fps=5, frames=2, intermediate=intermediate)
        return json.loads((out / "p.json").read_text(encoding="utf-8"))

    lossless = make("lossless")
    assert "intermediate" not in lossless   # the record of a lossless clip is as before compact clips existed
    assert make("compact")["key"] == lossless["key"] and len(drawn) == 1   # a lossless clip serves compact
    web_clip.forget_web_clips(out, ["p"])
    assert make("compact")["intermediate"] == "compact" and len(drawn) == 2
    assert make("compact") and len(drawn) == 2
    assert "intermediate" not in make("lossless") and len(drawn) == 3      # lossless asked: drawn again
    (out / "p.mkv").unlink()                                                 # deleted (keep_intermediates: false)
    make("lossless")
    assert len(drawn) == 4


# ----- disk: estimate, warning, deleting, report --------------------------------------------------------


def _web_project(make_project: Any, **render: Any) -> Project:
    scenes = [{"id": "w", "type": "web", "duration": 2, "params": {"script": "x.js"}},
              {"id": "t", "type": "text_card", "duration": 2, "params": {"text": "Hi"}}]
    root = make_project(minimal_config(format={"width": 160, "height": 90, "fps": 5}, scenes=scenes, render=render))
    (root / "x.js").write_text("export function frame(t, ctx) {}\n", encoding="utf-8")
    return Project.load(root)


def test_the_frames_clips_expected_follow_size_length_and_intermediate(make_project: Any) -> None:
    project = _web_project(make_project)
    assert disk.expected_bytes(project, False, ["w", "t"]) == 160 * 90 * 5 * 2   # 1 byte per pixel and frame, the web scene only
    project.config.render.intermediate = "compact"
    assert disk.expected_bytes(project, False, ["w"]) == round(160 * 90 * 5 * 2 * 0.22)
    clip = project.render_dir(False) / "web" / "w.mkv"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"kept")
    assert disk.expected_bytes(project, False, ["w"]) == 0   # a kept clip is reused or replaced in place


def test_the_room_warning_names_what_helps() -> None:
    assert disk.room_warning(10, 10, False, False) is None
    message = disk.room_warning(5 * 10**9, 10**9, False, False)
    assert message is not None and "up to about 5.0 GB" in message and "1.0 GB free" in message
    assert "--intermediate compact" in message and "--clean-intermediates" in message and "--max-scenes" in message
    message = disk.room_warning(5 * 10**9, 10**9, True, True)
    assert message is not None and "--intermediate" not in message and "--clean" not in message


def test_render_warns_before_drawing_when_the_disk_is_too_small(make_project: Any, monkeypatch: pytest.MonkeyPatch,
                                                                caplog: pytest.LogCaptureFixture) -> None:
    project = _web_project(make_project, keep_intermediates=False)
    monkeypatch.setattr(pipeline, "free_bytes", lambda path: 1000)
    with caplog.at_level(logging.WARNING, logger="vidgen.render"):
        pipeline._warn_room(project, False, ["w", "t"], jobs=1)
    assert "up to about 144 KB of frames clips" in caplog.text and "--clean-intermediates" not in caplog.text
    caplog.clear()
    monkeypatch.setattr(pipeline, "free_bytes", lambda path: 10**9)
    with caplog.at_level(logging.WARNING, logger="vidgen.render"):
        pipeline._warn_room(project, False, ["w", "t"], jobs=1)
    assert caplog.text == ""


def test_removing_frames_clips_keeps_records_and_scene_clips(make_project: Any) -> None:
    project = _web_project(make_project)
    build = project.render_dir(False)
    files = {"web/w.mkv": 300, "web/w.json": 7, "web/w.layout.json": 5, "three_d/w.mkv": 0, "scenes/w.mp4": 11,
             "media/videos/w/partial/uncached_00000.mp4": 13, "web/t.mkv": 17}
    for rel, size in files.items():
        (build / rel).parent.mkdir(parents=True, exist_ok=True)
        (build / rel).write_bytes(b"x" * size)
    usage = disk.build_usage(project, False)
    assert (usage.total, usage.frames_clips) == (sum(files.values()), 317) and usage.free > 0
    assert disk.remove_frames_clips(project, False, ["w"]) == 313
    left = sorted(p.relative_to(build).as_posix() for p in build.rglob("*") if p.is_file())
    assert left == ["scenes/w.mp4", "web/t.mkv", "web/w.json", "web/w.layout.json"]


def test_size_text() -> None:
    assert [disk.size_text(n) for n in (999, 160_400_000, 4_700_000_000)] == ["1 KB", "160 MB", "4.7 GB"]


# ----- settings: config, command line, worker ------------------------------------------------------------


def test_render_settings_default_and_are_checked(make_project: Any) -> None:
    from vidgen.errors import VidgenError

    settings = Project.load(make_project()).config.render
    assert (settings.intermediate, settings.keep_intermediates) == ("lossless", True)
    with pytest.raises(VidgenError, match="intermediate"):
        Project.load(make_project(minimal_config(render={"intermediate": "small"})))


def test_the_command_line_overrides_the_config_and_reaches_the_worker(make_project: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen import cli
    from vidgen.render.worker import build_parser

    seen: dict[str, Any] = {}

    def fake_render(project: Project, **options: Any) -> Any:
        seen.update(intermediate=project.config.render.intermediate, keep=project.config.render.keep_intermediates)
        raise SystemExit(0)

    monkeypatch.setattr(pipeline, "render_project", fake_render)
    root = make_project(minimal_config(render={"intermediate": "compact"}))
    with pytest.raises(SystemExit):
        cli.main(["render", str(root), "--intermediate", "lossless", "--clean-intermediates"])
    assert seen == {"intermediate": "lossless", "keep": False}
    assert build_parser().parse_args([".", "w", "--intermediate", "compact"]).intermediate == "compact"

    commands: list[list[str]] = []

    class Stopped(Exception):
        pass

    def popen(cmd: list[str], **kwargs: Any) -> Any:
        commands.append(cmd)
        raise Stopped

    monkeypatch.setattr(pipeline.subprocess, "Popen", popen)
    project = Project.load(root)
    project.config.render.intermediate = "lossless"   # as the command line set it
    with pytest.raises(Stopped):
        pipeline._run_worker(project, False, "intro", no_audio=True, live=False)
    assert commands[0][commands[0].index("--intermediate") + 1] == "lossless"


def test_audio_only_refuses_the_frames_options(make_project: Any) -> None:
    from vidgen import cli

    root = make_project(minimal_config(audio_only=True))
    assert cli.main(["render", str(root), "--clean-intermediates"]) != 0


# ----- a real render --------------------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.render
def test_a_compact_render_that_deletes_its_frames_clip_still_notices_edits(make_project: Any) -> None:
    """A web scene rendered with compact frames that are deleted after the scene: the video is
    joined, the frames clip is gone, the record stays; rendering again reuses the scene, and an
    edit to the script renders it again (its frames drawn again)."""
    from test_web_extension_cache import _chromium_or_skip

    _chromium_or_skip()
    project = _web_project(make_project, intermediate="compact", keep_intermediates=False)
    (project.root / "x.js").write_text(
        "export function frame(t, ctx) { const g = ctx.canvas.getContext('2d'); g.clearRect(0, 0, 999, 999);"
        " g.fillStyle = '#e04'; g.fillRect(10 + 40 * t, 20, 30, 30); }\n", encoding="utf-8")
    web = project.render_dir(False) / "web"
    result = pipeline.render_project(project)
    assert sorted(result.rendered) == ["t", "w"] and result.output.is_file() and result.removed > 0
    assert not (web / "w.mkv").exists() and json.loads((web / "w.json").read_text(encoding="utf-8"))["intermediate"] == "compact"
    assert result.disk is not None and result.disk.frames_clips == 0
    assert pipeline.render_project(project).rendered == []
    with (project.root / "x.js").open("a", encoding="utf-8") as script:
        script.write("// edited\n")
    assert pipeline.render_project(project).rendered == ["w"]


def test_a_clip_that_cannot_be_deleted_is_kept_with_a_warning(make_project: Any, monkeypatch: pytest.MonkeyPatch,
                                                              caplog: pytest.LogCaptureFixture) -> None:
    project = _web_project(make_project)
    clip = project.render_dir(False) / "web" / "w.mkv"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"x" * 10)

    def refuse(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError(13, "in use")

    monkeypatch.setattr(Path, "unlink", refuse)
    with caplog.at_level(logging.WARNING, logger="vidgen.render"):
        assert disk.remove_frames_clips(project, False, ["w"]) == 0
    assert "could not delete" in caplog.text and "in use" in caplog.text
