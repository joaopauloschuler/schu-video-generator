"""Drawing a ``web`` scene's frames faster (Step 349): the progress lines and
how ``vidgen render`` shows them, the frames clip written in a thread beside the drawing, the
first frame's time limit; one ``slow`` page in Chromium whose screenshots equal Playwright's."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from vidgen.browser.frames_clip import FramesClipWriter, write_frames_clip
from vidgen.errors import VidgenError
from vidgen.render import pipeline
from vidgen.render.worker import PROGRESS_PREFIX
from vidgen.web import clip as web_clip
from vidgen.web import page as web_page
from vidgen.web.clip import FrameProgress, duration_text, seconds_text
from vidgen.web.entry import WebEntry
from vidgen.web.page import WebPage

from test_scene_web import _chromium_or_skip, _fake_page


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_times_in_a_progress_line() -> None:
    assert [duration_text(s) for s in (0, 4.4, 59.6, 73, 3599, 4020)] == ["0 s", "4 s", "1 min 00 s", "1 min 13 s", "59 min 59 s",
                                                                          "1 h 07 min"]
    assert seconds_text(1.214) == "1.21" and seconds_text(0.0344) == "0.034"


def test_progress_lines_leave_out_the_first_frame_and_come_every_ten_seconds(caplog: pytest.LogCaptureFixture) -> None:
    clock = Clock()
    progress = FrameProgress(90, ready_seconds=8.0, clock=clock)
    assert progress.line() == "web frames 0/90"
    with caplog.at_level(logging.INFO, logger="vidgen.progress"):
        clock.now += 5.0                     # the first frame: shaders compiled
        progress.drawn(0.02, 4.98)
        for _ in range(9):
            clock.now += 1.2
            progress.drawn(0.02, 1.18)
    lines = [r.getMessage() for r in caplog.records if r.name == "vidgen.progress"]
    assert lines == ["web frames 6/90, 1.20 s a frame, about 1 min 41 s left"]   # 10 s after the start
    assert progress.seconds_per_frame() == pytest.approx(1.2)
    assert progress.summary() == ("web frames 10/90 drawn in 16 s (the page ready in 8.0 s before), 1.58 s a frame "
                                  "(the page's frame(t, ctx) 0.020 s, drawing and the screenshot 1.56 s)")


def test_render_shows_the_workers_progress_lines() -> None:
    lines, rest = pipeline.progress_lines("", f"Manim says\r\n{PROGRESS_PREFIX}web frames 3/9, 1.00 s a frame\n{PROGRESS_PREFIX}web fr")
    assert lines == ["web frames 3/9, 1.00 s a frame"] and rest == f"{PROGRESS_PREFIX}web fr"
    lines, rest = pipeline.progress_lines(rest, "ames 4/9\nwarning: x\n")
    assert lines == ["web frames 4/9"] and rest == ""
    assert pipeline._tail(f"a\n{PROGRESS_PREFIX}web frames 9/9\nerror: boom\n") == "a\nerror: boom"


def test_drawing_a_clip_logs_its_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(web_clip, "WebPage", _fake_page([], {"p.html": ""}))
    (tmp_path / "p.html").write_text("<p>", encoding="utf-8")
    with caplog.at_level(logging.INFO, logger="vidgen.progress"):
        web_clip.make_web_clip(tmp_path, tmp_path / "build", "p", {"page": "p.html"}, size=(16, 16), fps=5, frames=3)
    assert [r.getMessage().split(" drawn in ")[0] for r in caplog.records if r.name == "vidgen.progress"] == ["web frames 3/3"]


def _frames(n: int) -> list[np.ndarray]:
    rng = np.random.default_rng(349)
    return [rng.integers(0, 256, (18, 32, 4), dtype=np.uint8) for _ in range(n)]


def _read(path: Path) -> list[np.ndarray]:
    import av

    with av.open(str(path)) as container:
        return [f.to_ndarray(format="rgba") for f in container.decode(container.streams.video[0])]


def test_the_writer_in_a_thread_writes_what_write_frames_clip_writes(tmp_path: Path) -> None:
    frames = _frames(7)
    write_frames_clip(tmp_path / "plain.mkv", 5, (32, 18), iter(frames), alpha=True)
    with FramesClipWriter(tmp_path / "thread.mkv", 5, (32, 18), lambda i: frames[i], alpha=True) as writer:
        for i in range(len(frames)):
            writer.put(i)
    plain, threaded = _read(tmp_path / "plain.mkv"), _read(tmp_path / "thread.mkv")
    assert len(threaded) == 7 and all(np.array_equal(a, b) for a, b in zip(plain, threaded))
    assert all(np.array_equal(a, b) for a, b in zip(frames, threaded))


def test_a_failure_leaves_no_clip(tmp_path: Path) -> None:
    frames = _frames(3)
    with pytest.raises(RuntimeError, match="the page failed"):
        with FramesClipWriter(tmp_path / "a.mkv", 5, (32, 18), lambda i: frames[i], alpha=True) as writer:
            writer.put(0)
            raise RuntimeError("the page failed")

    def bad(i: int) -> np.ndarray:
        if i == 1:
            raise VidgenError("the page drew 8x8 px")
        return frames[i]

    with pytest.raises(VidgenError, match="drew 8x8"):
        with FramesClipWriter(tmp_path / "b.mkv", 5, (32, 18), bad, alpha=True) as writer:
            for i in range(40):
                writer.put(i % 3)
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_the_first_frame_may_take_as_long_as_load(monkeypatch: pytest.MonkeyPatch) -> None:
    page = WebPage(Path("."), WebEntry("script", "s.js"), scene_id="w", size=(16, 16), fps=5, frames=3)
    limits: list[float] = []
    monkeypatch.setattr(page, "_evaluate", lambda script, arg, when, hook, seconds: limits.append(seconds) or [])
    for n in range(3):
        page.advance(n)
    assert limits == [web_page.FIRST_FRAME_TIMEOUT_S, web_page.FRAME_TIMEOUT_S, web_page.FRAME_TIMEOUT_S]
    assert web_page.FIRST_FRAME_TIMEOUT_S == web_page.LOAD_TIMEOUT_S > web_page.FRAME_TIMEOUT_S


SHOT_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body { margin: 0; height: 100%; }
#bar { position: absolute; left: 4px; top: 6px; width: 30px; height: 10px; background: linear-gradient(90deg, rgba(255,0,0,.2), #0f0); }
input { position: absolute; left: 2px; top: 20px; width: 50px; font: 12px sans-serif; }
p { position: absolute; left: 40px; top: 0; margin: 0; font: italic 13px serif; color: rgba(255, 255, 255, .7); }
</style></head><body><div id="bar"></div><input id="i" value="ab" autofocus><p>Tx</p>
<script>window.vidgen = { load() { document.getElementById('i').focus(); },
  frame(t) { document.getElementById('bar').style.transform = `translateX(${t * 13.3}px) rotate(${t * 40}deg)`;
             document.querySelector('p').textContent = t.toFixed(2); } };</script></body></html>"""


@pytest.mark.slow
@pytest.mark.render
@pytest.mark.parametrize("design_width", [None, 48])
def test_vidgens_screenshot_equals_playwrights(tmp_path: Path, design_width: int | None) -> None:
    _chromium_or_skip()
    (tmp_path / "p.html").write_text(SHOT_PAGE, encoding="utf-8")
    with WebPage(tmp_path, WebEntry("page", "p.html"), scene_id="w", size=(80, 45), fps=5, frames=4, design_width=design_width) as page:
        for n in range(4):
            page.advance(n)
            ours = page.pixels(page.screenshot(n))
            theirs = page.pixels(page._page.screenshot(type="png"))
            assert ours.shape == (45, 80, 4) and np.array_equal(ours, theirs), n
            shown = page._page.evaluate("() => [window.__vidgenShownCarets === undefined, document.getElementById('i').style.caretColor]")
            assert shown == [True, ""]   # the carets are back as they were
        assert len(np.unique(ours[..., 3])) > 2   # the page keeps its alpha
