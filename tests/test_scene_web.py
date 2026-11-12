"""The ``web`` scene type (Steps 328-329, DESIGN.md §118): params, the page or script file's checks,
the served paths, error messages, the clip cache, the random seed and the time limit without a
browser; a few tiny pages in Playwright's Chromium (``slow``, skipped when it is missing), among
them the virtual clock (§118.8)."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from vidgen.browser import chromium
from vidgen.cli import check_project, validate_warnings
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.web import clip as web_clip
from vidgen.web import page as web_page
from vidgen.web.entry import WebEntry, entry_digest, entry_of, entry_problems
from vidgen.web.page import (WebPage, byte_range, canvas_page, content_type, error_location, error_message, init_script,
                             project_path, random_seed)


def web_project(make_project: Any, params: dict[str, Any], files: dict[str, str]) -> Project:
    root = make_project({"title": "W", "format": {"width": 160, "height": 90, "fps": 5},
                         "scenes": [{"id": "w", "type": "web", "params": params, "duration": 1, "beats": []}]})
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return Project.load(root)


# ----- params and files -------------------------------------------------------------------------


def test_exactly_one_of_page_and_script() -> None:
    from vidgen.scenes.web import Web

    assert Web.Params.model_validate({"page": "a.html"}).page == "a.html"
    for raw in ({}, {"page": "a.html", "script": "b.js"}):
        with pytest.raises(ValidationError, match="exactly one of page"):
            Web.Params.model_validate(raw)
    assert entry_of({"script": "x/b.js"}) == WebEntry("script", "x/b.js")
    with pytest.raises(VidgenError, match="exactly one"):
        entry_of({})


def test_entry_problems_name_the_param(tmp_path: Path) -> None:
    (tmp_path / "extensions").mkdir()
    (tmp_path / "extensions" / "g.html").write_text("<p>", encoding="utf-8")
    assert entry_problems(tmp_path, WebEntry("page", "extensions/g.html")) == []
    assert entry_problems(tmp_path, WebEntry("page", "extensions/none.html"))[0].startswith("page: file not found: extensions/none.html")
    assert "inside the project folder" in entry_problems(tmp_path, WebEntry("script", "../x.js"))[0]
    assert "inside the project folder" in entry_problems(tmp_path, WebEntry("script", str(tmp_path / "extensions" / "g.html")))[0]
    assert entry_problems(tmp_path, WebEntry("script", "extensions/g.html")) == ["script: expected a .js or .mjs file, got extensions/g.html"]


def test_validate_reports_a_missing_file_at_its_param(make_project: Any) -> None:
    problems = check_project(web_project(make_project, {"script": "extensions/gone.js"}, {}))
    assert len(problems) == 1 and problems[0].startswith("scenes[0].params.script: file not found: extensions/gone.js")
    assert check_project(web_project(make_project, {"page": "extensions/p.html"}, {"extensions/p.html": "<p>"})) == []


def test_validate_warns_about_a_missing_chromium_as_for_3d(make_project: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chromium, "missing_dependency", lambda: chromium.BROWSER_HINT)
    project = web_project(make_project, {"page": "extensions/p.html"}, {"extensions/p.html": "<p>"})
    assert [w for w in validate_warnings(project) if "cannot render here" in w] == [f"web scenes (w) cannot render here: {chromium.BROWSER_HINT}"]


def test_the_fingerprint_follows_the_named_file(tmp_path: Path) -> None:
    (tmp_path / "p.html").write_text("<p>1", encoding="utf-8")
    first = entry_digest(tmp_path, {"page": "p.html"})
    (tmp_path / "p.html").write_text("<p>2", encoding="utf-8")
    assert entry_digest(tmp_path, {"page": "p.html"})["sha256"] != first["sha256"]
    assert entry_digest(tmp_path, {"page": "gone.html"})["sha256"] is None


# ----- serving and messages ---------------------------------------------------------------------


def test_served_paths_and_content_types() -> None:
    assert project_path("http://vidgen-web.invalid/extensions/a%20b.css?v=1") == "extensions/a b.css"
    assert project_path("https://example.org/x.js") is None
    assert content_type(Path("m.mjs")).startswith("text/javascript") and content_type(Path("f.woff2")) == "font/woff2"
    page = canvas_page("extensions/g.js", (160, 90))
    assert 'import * as hooks from "/extensions/g.js";' in page and 'width="160" height="90"' in page


def test_error_location_and_message() -> None:
    entry = WebEntry("script", "extensions/g.js")
    stack = "TypeError: x\n    at frame (http://vidgen-web.invalid/extensions/g.js:12:5)\n    at http://vidgen-web.invalid/__vidgen__/canvas.html:3:1"
    assert error_location({"stack": stack}) == "extensions/g.js line 12"
    assert error_location({"file": "http://vidgen-web.invalid/extensions/p.html", "line": 4}) == "extensions/p.html line 4"
    assert error_location({"file": "http://vidgen-web.invalid/__vidgen__/canvas.html", "line": 2}) is None
    text = error_message("gears", entry, {"message": "Uncaught TypeError: x", "stack": stack}, "in frame(t=0.200)")
    assert text == "scene 'gears': JavaScript error in extensions/g.js line 12 in frame(t=0.200): TypeError: x"
    assert "in extensions/g.js at load" in error_message("gears", entry, {"message": "boom"}, "at load")


def test_the_clip_is_reused_until_the_file_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drawn: list[int] = []

    class Page:
        def __init__(self, *_: Any, **__: Any) -> None: ...
        def __enter__(self) -> Page:
            return self
        def __exit__(self, *_: Any) -> None: ...
        def frame(self, n: int) -> np.ndarray:
            drawn.append(n)
            return np.zeros((16, 16, 3), dtype=np.uint8)

    monkeypatch.setattr(web_clip, "WebPage", Page)
    (tmp_path / "g.js").write_text("export function frame() {}", encoding="utf-8")
    out = tmp_path / "build"
    make = lambda: web_clip.make_web_clip(tmp_path, out, "g", {"script": "g.js"}, size=(16, 16), fps=5, frames=3)  # noqa: E731
    assert make() == out / "g.mkv" and drawn == [0, 1, 2]
    make()
    assert drawn == [0, 1, 2]   # reused
    (tmp_path / "g.js").write_text("export function frame(t) {}", encoding="utf-8")
    make()
    assert drawn == [0, 1, 2, 0, 1, 2]
    with pytest.raises(VidgenError, match="scene 'g': script: file not found"):
        web_clip.make_web_clip(tmp_path, out, "g", {"script": "gone.js"}, size=(16, 16), fps=5, frames=3)


def test_byte_ranges_for_seeking_a_video() -> None:
    assert byte_range("bytes=0-", 10) == (0, 9) and byte_range("bytes=2-4", 10) == (2, 4)
    assert byte_range("bytes=-3", 10) == (7, 9) and byte_range("bytes=5-99", 10) == (5, 9)
    for header in (None, "", "items=0-1", "bytes=-", "bytes=9-2", "bytes=0-1,4-5"):
        assert byte_range(header, 10) is None


def sfc32_values(seed: list[int], count: int) -> list[float]:
    """The page's Math.random (sfc32), in Python, for the seed's first four words."""
    a, b, c, d = seed[:4]
    out = []
    for _ in range(count):
        t = (a + b + d) & 0xFFFFFFFF
        d = (d + 1) & 0xFFFFFFFF
        a = b ^ (b >> 9)
        b = (c + (c << 3)) & 0xFFFFFFFF
        c = ((c << 21) | (c >> 11)) & 0xFFFFFFFF
        c = (c + t) & 0xFFFFFFFF
        out.append(t / 4294967296)
    return out


def test_the_random_seed_follows_the_scene_id() -> None:
    assert random_seed("gears") == random_seed("gears") != random_seed("gears2")
    assert len(random_seed("gears")) == 8 and all(0 <= w < 2**32 for w in random_seed("gears"))
    script = init_script("gears")
    assert f"const VIDGEN_SEED = {json.dumps(random_seed('gears'))};" in script
    assert script.index("const native = {") < script.index("const animations = new Map()") < script.index("const run = {")


def test_the_clip_key_changes_with_the_clock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = web_page.engine_id()
    changed = tmp_path / "clock.js"
    changed.write_text(web_page.CLOCK_FILE.read_text(encoding="utf-8") + "\n// changed\n", encoding="utf-8")
    monkeypatch.setattr(web_page, "INIT_FILES", (changed, web_page.MEDIA_FILE, web_page.RUNTIME_FILE))
    web_page.runtime_digest.cache_clear()
    try:
        assert web_page.engine_id() != before and "tz=UTC" in before
    finally:
        web_page.runtime_digest.cache_clear()


def test_the_time_limit_stops_the_process() -> None:
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    limit = web_page._TimeLimit([sleeper.pid])
    try:
        with limit.running(30):
            pass
        assert not limit.expired and sleeper.poll() is None
        with limit.running(0.05):
            sleeper.wait(timeout=10)
        assert limit.expired
    finally:
        sleeper.kill()
        sleeper.wait()


# ----- pages in Chromium ------------------------------------------------------------------------


def _chromium_or_skip() -> None:
    pytest.importorskip("playwright.sync_api")
    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")


def _open(root: Path, entry: WebEntry, frames: int = 3) -> WebPage:
    return WebPage(root, entry, scene_id="w", size=(64, 36), fps=5, frames=frames)


@pytest.mark.slow
@pytest.mark.render
def test_page_and_script_frames_follow_time(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _chromium_or_skip()
    (tmp_path / "ext").mkdir()
    (tmp_path / "ext" / "p.css").write_text("html, body { margin: 0; height: 100%; background: rgb(0, 0, 0); }", encoding="utf-8")
    (tmp_path / "ext" / "p.html").write_text(
        '<!doctype html><link rel="stylesheet" href="p.css"><link rel="stylesheet" href="https://example.org/f.css">'
        "<script>window.vidgen = {frame(t, ctx) { document.body.style.background = `rgb(${Math.round(t * 250)}, 0, ${ctx.width})`; }};</script>",
        encoding="utf-8")
    (tmp_path / "ext" / "c.js").write_text(
        "export function frame(t, ctx) { const c = ctx.canvas.getContext('2d');"
        " c.fillStyle = `rgb(0, ${Math.round(t * 250)}, 0)`; c.fillRect(0, 0, ctx.width, ctx.height); }", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="vidgen.web"), _open(tmp_path, WebEntry("page", "ext/p.html")) as page:
        reds = [int(page.frame(n)[18, 32, 0]) for n in range(3)]
        assert int(page.frame(0)[18, 32, 2]) == 64   # ctx.width
        assert page.refused == ["https://example.org/f.css"]
    assert reds == [0, 50, 100]
    assert "refused https://example.org/f.css" in caplog.text
    with _open(tmp_path, WebEntry("script", "ext/c.js")) as page:
        assert [int(page.frame(n)[18, 32, 1]) for n in (0, 2)] == [0, 100]


@pytest.mark.slow
@pytest.mark.render
def test_javascript_errors_name_the_file_and_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _chromium_or_skip()
    (tmp_path / "late.js").write_text("export function frame(t) {\n  if (t > 0.1) throw new RangeError('late');\n}\n", encoding="utf-8")
    (tmp_path / "bad.js").write_text("export function frame() {\n  let x = ;\n}\n", encoding="utf-8")
    (tmp_path / "throw.html").write_text("<!doctype html>\n<script>\nnull.go();\n</script>\n", encoding="utf-8")
    (tmp_path / "never.js").write_text("await new Promise(() => {});\n", encoding="utf-8")
    with _open(tmp_path, WebEntry("script", "late.js")) as page:
        page.frame(0)
        with pytest.raises(VidgenError, match=r"^scene 'w': JavaScript error in late\.js line 2 in frame\(t=0\.200\): RangeError: late$"):
            page.frame(1)
    with pytest.raises(VidgenError, match=r"in bad\.js line 2 at load: SyntaxError"):
        _open(tmp_path, WebEntry("script", "bad.js")).__enter__()
    with pytest.raises(VidgenError, match=r"in throw\.html line 3 at load: TypeError"):
        _open(tmp_path, WebEntry("page", "throw.html")).__enter__()
    monkeypatch.setattr(web_page, "READY_TIMEOUT_MS", 1500)
    with pytest.raises(VidgenError, match=r"^scene 'w': never\.js did not become ready within 1\.5 s"):
        _open(tmp_path, WebEntry("script", "never.js")).__enter__()


@pytest.mark.slow
@pytest.mark.render
def test_render_shows_the_page(make_project: Any) -> None:
    _chromium_or_skip()
    import av

    from vidgen.render.pipeline import render_project

    project = web_project(make_project, {"page": "extensions/p.html"},
                          {"extensions/p.html": "<!doctype html><style>html, body { margin: 0; height: 100%; background: #e04040; }</style>"})
    render_project(project, preview=False)
    with av.open(str(project.root / "build" / "final" / "scenes" / "w.mp4")) as video:
        first = next(video.decode(video=0)).to_ndarray(format="rgb24")
    assert first[45, 80, 0] > 180 and first[45, 80, 1] < 100
    assert (project.root / "build" / "final" / "web" / "w.json").is_file()


CLOCK_PAGE = """<!doctype html><meta charset="utf-8">
<style>html, body { margin: 0; background: #000; } #bar { height: 10px; background: #f00; animation: grow 1s linear forwards; }
@keyframes grow { from { width: 0; } to { width: 50px; } }</style><div id="bar"></div><i id="fade"></i>
<script>
window.log = [];
const log = (x) => window.log.push(x);
log(['start', performance.now(), Date.now(), new Date().toISOString()]);
window.randoms = [Math.random(), Math.random()];
window.bytes = Array.from(crypto.getRandomValues(new Uint8Array(4)));
setTimeout(() => { log(['t200', performance.now()]); setTimeout(() => log(['t200+0', performance.now()]), 0); }, 200);
setTimeout(() => log(['t100', performance.now()]), 100);
setTimeout(() => log(['t100b', performance.now()]), 100);
let ticks = 0;
const loop = setInterval(() => { ticks++; }, 0);
setTimeout(() => { clearInterval(loop); log(['interval', ticks]); }, 400);
requestAnimationFrame((t) => { log(['raf', t]); requestAnimationFrame((u) => log(['raf2', u])); });
const moved = document.getElementById("fade").animate([{opacity: 1}, {opacity: 0}], {duration: 400});
moved.finished.then(() => log(['finished', performance.now()]));
window.vidgen = {
  async load(ctx) { const data = await (await fetch('d.json')).json(); log(['load', data.n, performance.now()]); },
  frame(t) { log(['frame', t, document.getAnimations().length, moved.currentTime]); },
};
</script>"""


@pytest.mark.slow
@pytest.mark.render
def test_the_page_runs_on_vidgens_clock(tmp_path: Path) -> None:
    _chromium_or_skip()
    (tmp_path / "c.html").write_text(CLOCK_PAGE, encoding="utf-8")
    (tmp_path / "d.json").write_text('{"n": 7}', encoding="utf-8")
    with WebPage(tmp_path, WebEntry("page", "c.html"), scene_id="clock", size=(64, 36), fps=10, frames=6) as page:
        widths = [int((page.frame(n)[5, :, 0] > 128).sum()) for n in range(6)]
        log = page._page.evaluate("window.log")
        randoms, numbers = page._page.evaluate("[window.randoms, window.bytes]")
    assert widths == [0, 5, 10, 15, 20, 25]   # 50 px in 1 s, at 10 fps
    assert log[0] == ["start", 0, 1767225600000, "2026-01-01T00:00:00.000Z"]
    assert randoms == pytest.approx(sfc32_values(random_seed("clock"), 2), abs=0)
    assert len(numbers) == 4
    events = [e for e in log[1:] if e[0] != "frame"]
    # each frame: its due timers in time order (ties: as set; one set by a timer runs too), then requestAnimationFrame
    assert events == [["load", 7, 0], ["raf", 0], ["t100", 100], ["t100b", 100], ["raf2", 100], ["t200", 200],
                      ["t200+0", 200], ["interval", events[7][1]], ["finished", 400]]
    assert 50 < events[7][1] < 120   # 0 ms then, from the 6th nested run, 4 ms: (400 - 5 * 0) / 4 + 5
    frames = [e for e in log if e[0] == "frame"]
    assert [f[1] for f in frames] == [0, 0.1, 0.2, 0.3, 0.4, 0.5] and frames[2][3] == 200


@pytest.mark.slow
@pytest.mark.render
def test_the_same_page_gives_the_same_frames(tmp_path: Path) -> None:
    _chromium_or_skip()
    (tmp_path / "r.js").write_text(
        "let x = 0;\nfunction tick(now) { x = (now / 7 + Math.random() * 20) % 64; requestAnimationFrame(tick); }\n"
        "requestAnimationFrame(tick);\nexport function frame(t, ctx) { const c = ctx.canvas.getContext('2d');"
        " c.fillStyle = `hsl(${Math.random() * 360}, 90%, 50%)`; c.fillRect(x, Date.now() % 30, 9, 9); }", encoding="utf-8")
    runs = []
    for _ in range(2):
        with _open(tmp_path, WebEntry("script", "r.js"), frames=4) as page:
            runs.append([page.frame(n) for n in range(4)])
    assert all(np.array_equal(a, b) for a, b in zip(*runs)) and not np.array_equal(runs[0][1], runs[0][2])


@pytest.mark.slow
@pytest.mark.render
def test_a_hook_that_never_returns_is_stopped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _chromium_or_skip()
    monkeypatch.setattr(web_page, "FRAME_TIMEOUT_S", 1.0)
    monkeypatch.setattr(web_page, "LOAD_TIMEOUT_S", 1.0)
    (tmp_path / "loop.js").write_text("export async function frame(t) {\n  await null;\n  if (t > 0) while (true) {}\n}\n", encoding="utf-8")
    (tmp_path / "wait.js").write_text("export async function load() { await new Promise((r) => setTimeout(r, 100)); }\n", encoding="utf-8")
    started = time.monotonic()
    with _open(tmp_path, WebEntry("script", "loop.js")) as page:
        page.frame(0)
        with pytest.raises(VidgenError, match=r"^scene 'w': frame\(t=0\.200\) in loop\.js did not return within 1 s: a loop"):
            page.frame(1)
    with pytest.raises(VidgenError, match=r"^scene 'w': load\(ctx\) in wait\.js did not return within 1 s \(time stands still"):
        _open(tmp_path, WebEntry("script", "wait.js")).__enter__()
    assert time.monotonic() - started < 20
