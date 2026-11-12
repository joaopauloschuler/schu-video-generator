"""The ``web`` scene type (Steps 328-330, DESIGN.md §118): params, the page or script file's checks,
the served paths, error messages, the clip cache, the random seed and the time limit without a
browser; a few tiny pages in Playwright's Chromium (``slow``, skipped when it is missing), among
them the virtual clock (§118.8) and what the page is given (§118.9, §118.10)."""

from __future__ import annotations

import hashlib
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
        loaded: dict[str, str | None] = {}
        def __init__(self, *_: Any, **__: Any) -> None: ...
        def __enter__(self) -> Page:
            return self
        def __exit__(self, *_: Any) -> None: ...
        def frame(self, n: int) -> np.ndarray:
            drawn.append(n)
            return np.zeros((16, 16, 4), dtype=np.uint8)

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


# ----- what the page is given (Step 330) ---------------------------------------------------------


def _theme(preset: str | None = None) -> dict[str, Any]:
    from vidgen.config import ThemeConfig
    from vidgen.theme import Theme
    from vidgen.web.inputs import page_theme

    return page_theme(Theme(ThemeConfig(preset=preset)), 1080 / (72 * 8))


def test_the_theme_as_css_custom_properties() -> None:
    from vidgen.web.inputs import theme_css, theme_properties

    dark, light = _theme(), _theme("light_academic")
    props = theme_properties(light)
    assert props["--vidgen-primary"] == "#1D4ED8" and props["--vidgen-background"] == "#F8F7F3"
    assert props["--vidgen-palette-0"] == "#1D4ED8"
    assert props["--vidgen-font-heading"] == '"Source Serif 4", serif' and props["--vidgen-font-body"] == '"Inter", sans-serif'
    assert props["--vidgen-font-quote_mark"] == '"Source Serif 4", serif' and props["--vidgen-font-mono"] == '"JetBrains Mono NL", monospace'
    assert props["--vidgen-size-body"] == "60px"   # font size 32 at 1080 px: 32 / 72 in * 1080 / 8 px per unit
    assert theme_properties(dark)["--vidgen-font-heading"] == '"Inter", sans-serif'
    css = theme_css(light)
    assert 'src: url("/__vidgen__/fonts/SourceSerif4/SourceSerif4-Bold.ttf") format("truetype"); font-weight: 700' in css
    assert css.count("@font-face") == 8 and ":root {" in css


def test_vidgens_head_goes_first_in_the_page() -> None:
    from vidgen.web.inputs import IMPORT_MAP, page_head, with_head

    head = page_head(None)
    assert head == f'<script type="importmap">{json.dumps(IMPORT_MAP)}</script>'
    assert IMPORT_MAP["imports"]["three"] == "/__vidgen__/three/three.module.js"
    assert with_head(b"<!DOCTYPE html><html lang=en><HEAD><script>", "<X>") == b"<!DOCTYPE html><html lang=en><HEAD><X><script>"
    assert with_head(b"<!doctype html><header>", "<X>") == b"<!doctype html><X><header>"
    assert with_head(b"<p>hi", "<X>") == b"<X><p>hi"
    assert page_head(_theme()).startswith('<style id="vidgen-theme">')
    assert "background: transparent;" in canvas_page("g.js", (16, 9))


def test_data_must_be_json_values() -> None:
    import datetime

    from vidgen.scenes.web import Web

    assert Web.Params.model_validate({"page": "a.html", "data": {"teeth": [1, 2.5], "on": True, "c": None}}).data["teeth"] == [1, 2.5]
    assert Web.Params.model_validate({"page": "a.html"}).data == {}
    for data, problem in (({"a": [1, {"when": datetime.date(2026, 1, 1)}]}, "data.a[1].when: 2026-01-01 is a date"),
                          ({1: "x"}, "data: the key 1 is not text"), ({"x": float("inf")}, "data.x: inf is not a finite number")):
        with pytest.raises(ValidationError, match=problem.replace("[", r"\[").replace("]", r"\]")):
            Web.Params.model_validate({"page": "a.html", "data": data})


def test_served_vidgen_files() -> None:
    from vidgen.web.loaded import served_file, vidgen_file

    assert vidgen_file("three/three.module.js").name == "three.module.js"
    assert vidgen_file("fonts/Inter/Inter-Bold.ttf").is_file()
    for rel in ("three/vidgen3d.js", "fonts/../three/three.core.js", "fonts/Inter/OFL.txt", "web/clock.js"):
        assert vidgen_file(rel) is None
    assert served_file(Path("/p"), "__vidgen__/three/three.core.js").name == "three.core.js"
    assert served_file(Path("/p"), "../x.css") is None


def _fake_page(drawn: list[str], loads: dict[str, str]) -> type:
    """A WebPage stand-in that 'loads' the files of ``loads`` (path -> file under the root)."""

    class Page:
        def __init__(self, root: Path, *_: Any, **kw: Any) -> None:
            from vidgen.web.loaded import current_loaded

            self.loaded = current_loaded(root, loads)
            drawn.append(json.dumps(kw.get("data")))
        def __enter__(self) -> Any:
            return self
        def __exit__(self, *_: Any) -> None: ...
        def frame(self, n: int) -> np.ndarray:
            return np.zeros((16, 16, 4), dtype=np.uint8)

    return Page


def test_the_clip_follows_every_file_the_page_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drawn: list[str] = []
    monkeypatch.setattr(web_clip, "WebPage", _fake_page(drawn, {"p.html": "", "s.css": "", "late.json": ""}))
    (tmp_path / "p.html").write_text("<p>", encoding="utf-8")
    (tmp_path / "s.css").write_text("p {}", encoding="utf-8")
    out = tmp_path / "build"
    make = lambda data=None: web_clip.make_web_clip(tmp_path, out, "p", {"page": "p.html", "data": data or {}},  # noqa: E731
                                                    size=(16, 16), fps=5, frames=2, theme={"background": "#000"})
    make()
    record = json.loads((out / "p.json").read_text(encoding="utf-8"))
    assert record["loaded"]["late.json"] is None and record["inputs"]["data"] == {} and record["inputs"]["theme"] == {"background": "#000"}
    make()
    assert len(drawn) == 1
    (tmp_path / "s.css").write_text("p { color: red }", encoding="utf-8")
    make()
    (tmp_path / "late.json").write_text("{}", encoding="utf-8")   # was missing: now there
    make()
    make({"n": 2})
    assert len(drawn) == 4 and drawn[-1] == '{"n": 2}'
    web_clip.forget_web_clips(out, ["p"])
    make({"n": 2})
    assert len(drawn) == 5


def test_the_fingerprint_follows_the_files_the_page_loaded(make_project: Any) -> None:
    from vidgen.render.fingerprint import drawn_fingerprint, fingerprint_inputs, scene_fingerprint

    project = web_project(make_project, {"page": "p.html"}, {"p.html": "<p>", "s.css": "p {}"})
    root = project.root
    before = fingerprint_inputs(project, "w")
    assert before["web"]["loaded"] == {}
    record = root / "build" / "final" / "web" / "w.json"
    record.parent.mkdir(parents=True)
    loaded = {"p.html": hashlib.sha256(b"<p>").hexdigest(), "s.css": hashlib.sha256(b"p {}").hexdigest()}
    record.write_text(json.dumps({"key": "k", "loaded": loaded}), encoding="utf-8")
    stored = drawn_fingerprint(before, project, False, "w")   # what the worker records after the first render
    assert stored == scene_fingerprint(project, "w")   # the next run: unchanged
    (root / "s.css").write_text("p { color: red }", encoding="utf-8")
    assert scene_fingerprint(project, "w") != stored


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


START_TIME_PAGE = """<!doctype html><meta charset="utf-8">
<style>html, body { margin: 0; background: #000; } #box { position: absolute; left: 0; top: 0; width: 10px; height: 10px; background: #f00; }</style>
<div id="box"></div>
<script>
requestAnimationFrame((now) => {
  const moved = document.getElementById("box").animate([{transform: "translateX(0)"}, {transform: "translateX(50px)"}], {duration: 1000, fill: "both"});
  moved.startTime = now;   // what Motion does to line its animations up
  window.moved = moved;
  setTimeout(() => { moved.startTime = 100; }, 400);
  setTimeout(() => { moved.startTime = null; }, 600);
});
window.seen = [];
window.vidgen = { frame() { window.seen.push([window.moved.startTime, window.moved.currentTime, window.moved.playState]); } };
</script>"""


@pytest.mark.slow
@pytest.mark.render
def test_an_animations_start_time_is_on_vidgens_clock(tmp_path: Path) -> None:
    _chromium_or_skip()
    (tmp_path / "s.html").write_text(START_TIME_PAGE, encoding="utf-8")
    with WebPage(tmp_path, WebEntry("page", "s.html"), scene_id="start", size=(64, 36), fps=10, frames=8) as page:
        lefts = [int(np.argmax(page.frame(n)[5, :, 0] > 128)) for n in range(8)]
        seen = page._page.evaluate("window.seen")
    # 50 px in 1 s from t = 0; at 0.4 s the start moves to 0.1 s (one frame back); at 0.6 s it is held
    assert lefts == [0, 5, 10, 15, 15, 20, 25, 25]
    assert seen[:4] == [[0, 0, "running"], [0, 100, "running"], [0, 200, "running"], [0, 300, "running"]]
    assert seen[4:] == [[100, 300, "running"], [100, 400, "running"], [None, 500, "paused"], [None, 500, "paused"]]


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


GIVEN_PAGE = """<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="g.css">
<script type="module">import * as THREE from "three"; window.revision = THREE.REVISION;</script></head>
<body><div id="box"></div><script>
window.events = [];
window.addEventListener('vidgen-beat', (e) => window.events.push([e.detail.beat.id, e.detail.index, e.detail.t, e.detail.previous && e.detail.previous.id]));
window.vidgen = { load(ctx) { window.seen = [document.body.dataset.beat, ctx.data.n, ctx.theme.colors.primary, ctx.beats.length]; },
                  frame(t) { if (t > 0.3) fetch('late.json'); } };
</script></body></html>"""


@pytest.mark.slow
@pytest.mark.render
def test_the_page_is_given_theme_data_beats_and_three(tmp_path: Path) -> None:
    _chromium_or_skip()
    (tmp_path / "g.html").write_text(GIVEN_PAGE, encoding="utf-8")
    (tmp_path / "g.css").write_text("html, body { margin: 0; height: 100%; background: var(--vidgen-background); font-family: var(--vidgen-font-heading); }\n"
                                    "#box { width: 20px; height: 20px; background: var(--vidgen-primary); opacity: 0; transition: opacity 0.4s linear; }\n"
                                    "body[data-beat=\"b2\"] #box { opacity: 1; }", encoding="utf-8")
    (tmp_path / "late.json").write_text("{}", encoding="utf-8")
    (tmp_path / "t.js").write_text("import * as THREE from 'three';\nexport function frame(t, ctx) { const c = ctx.canvas.getContext('2d');"
                                   " c.fillStyle = new THREE.Color(ctx.theme.colors.primary).getStyle(); c.fillRect(0, 0, 8, 8); }", encoding="utf-8")
    theme = _theme("light_academic")
    beats = [{"id": "b1", "index": 0, "start": 0.0, "end": 0.3, "text": "a", "words": []},
             {"id": "b2", "index": 1, "start": 0.4, "end": 0.9, "text": "b", "words": []}]
    with WebPage(tmp_path, WebEntry("page", "g.html"), scene_id="w", size=(64, 36), fps=10, frames=9,
                 theme=theme, data={"n": 3}, beats=beats) as page:
        reds = [int(page.frame(n)[5, 5, 0]) for n in range(9)]
        state = page._page.evaluate("[window.seen, window.events, window.revision, document.body.dataset.beat, document.body.dataset.beatIndex,"
                                    " getComputedStyle(document.body).fontFamily, document.fonts.check('16px \"Source Serif 4\"')]")
        loaded = page.loaded
    assert state[0] == ["b1", 3, "#1D4ED8", 2]
    assert state[1] == [["b1", 0, 0, None], ["b2", 1, 0.4, "b1"]]
    assert isinstance(state[2], str) and state[2].isdigit()
    assert state[3:6] == ["b2", "1", '"Source Serif 4", serif'] and state[6] is True
    # the background is #F8F7F3 (red 248) until b2 starts at 0.4 s; the box fades to #1D4ED8 (red 29) in 0.4 s
    assert reds[:5] == [248] * 5 and reds[8] == 29 and 29 < reds[6] < 248
    assert {"g.html", "g.css", "late.json", "__vidgen__/three/three.module.js", "__vidgen__/three/three.core.js",
            "__vidgen__/fonts/SourceSerif4/SourceSerif4-Regular.ttf"} <= set(loaded)
    with WebPage(tmp_path, WebEntry("script", "t.js"), scene_id="w", size=(64, 36), fps=10, frames=2, theme=theme) as page:
        pixels = page.frame(0)
    # the bare page is transparent: what the script does not draw shows the video's background
    assert tuple(int(v) for v in pixels[2, 2]) == (0x1D, 0x4E, 0xD8, 255) and int(pixels[30, 50, 3]) == 0


# ----- Step 331: region, title, transparency, the video's shape ----------------------------------


def test_the_aspect_and_orientation_of_a_frame() -> None:
    from vidgen.web.inputs import aspect_name, page_shape

    assert {aspect_name(w, h) for w, h in [(1920, 1080), (854, 480), (426, 240), (480, 270)]} == {"16:9"}
    assert {aspect_name(w, h) for w, h in [(1080, 1920), (480, 854), (270, 480)]} == {"9:16"}
    assert [aspect_name(1080, 1080), aspect_name(1080, 1350), aspect_name(1000, 700)] == ["1:1", "4:5", "10:7"]
    assert page_shape((270, 480), "body") == {"aspect": "9:16", "orientation": "portrait", "frame": {"width": 270, "height": 480},
                                              "region": "body"}
    assert page_shape((1000, 900))["orientation"] == "square" and page_shape((16, 9))["region"] == "bleed"


def test_the_shape_is_on_html_before_the_pages_own_scripts() -> None:
    from vidgen.web.inputs import page_head, page_shape

    head = page_head(None, page_shape((90, 160)))
    script = '<script>((e)=>{e.dataset.aspect="9:16";e.dataset.orientation="portrait";})(document.documentElement)</script>'
    assert head.startswith(script) and head.index(script) < head.index("importmap")
    assert page_head(_theme(), page_shape((16, 9))).index("</style>") < page_head(_theme(), page_shape((16, 9))).index("dataset.aspect")


def test_the_clip_keeps_alpha_and_follows_the_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen.web.inputs import page_shape

    drawn: list[str] = []
    monkeypatch.setattr(web_clip, "WebPage", _fake_page(drawn, {"p.html": ""}))
    (tmp_path / "p.html").write_text("<p>", encoding="utf-8")
    out = tmp_path / "build"
    make = lambda shape=None: web_clip.make_web_clip(tmp_path, out, "p", {"page": "p.html"}, size=(16, 16), fps=5, frames=2,  # noqa: E731
                                                      shape=shape)
    make()
    inputs = json.loads((out / "p.json").read_text(encoding="utf-8"))["inputs"]
    assert inputs["alpha"] is True and inputs["shape"] == page_shape((16, 16)) and inputs["version"] == 3
    make(page_shape((16, 16)))
    assert len(drawn) == 1   # the default is a page filling a frame of its size
    make(page_shape((32, 18), "body"))
    make(page_shape((18, 32), "body"))
    assert len(drawn) == 3


def test_frames_with_alpha_are_stored_with_alpha(tmp_path: Path) -> None:
    import av

    from vidgen.browser.chromium import write_ffv1_clip

    frame = np.zeros((6, 8, 4), dtype=np.uint8)
    frame[:, :4] = (255, 40, 0, 128)   # half transparent, straight alpha
    write_ffv1_clip(tmp_path / "a.mkv", 5, (8, 6), [frame, frame], alpha=True)
    write_ffv1_clip(tmp_path / "o.mkv", 5, (8, 6), [frame[..., :3]])
    with av.open(str(tmp_path / "a.mkv")) as clip:
        assert clip.streams.video[0].codec_context.pix_fmt == "bgra"
        assert np.array_equal(next(clip.decode(video=0)).to_ndarray(format="rgba"), frame)
    with av.open(str(tmp_path / "o.mkv")) as clip:
        assert clip.streams.video[0].codec_context.pix_fmt == "bgr0"   # 3d clips: unchanged


def test_region_and_title_params() -> None:
    from vidgen.scenes.web import Web

    params = Web.Params(page="p.html")
    assert (params.region, params.title) == ("bleed", "") and Web.target_names(params) == ["view"]
    titled = Web.Params(page="p.html", region="body", title="Gears")
    assert Web.target_names(titled) == ["view", "title"]
    with pytest.raises(ValidationError, match="'bleed' or 'body'"):
        Web.Params(page="p.html", region="left")


def test_the_page_box_is_on_whole_pixels() -> None:
    from manim import tempconfig

    from vidgen.regions import Region
    from vidgen.scenes.web import pixel_box

    with tempconfig({"pixel_width": 480, "pixel_height": 270, "frame_width": 8 * 16 / 9, "frame_height": 8.0}):
        box = pixel_box(Region(-5.123, -2.871, 5.007, 2.333))
        per_unit = 270 / 8
        for edge, half in [(box.x0, 8 * 8 / 9), (box.x1, 8 * 8 / 9), (box.y0, 4.0), (box.y1, 4.0)]:
            assert abs((edge + half) * per_unit - round((edge + half) * per_unit)) < 1e-9
        assert abs(box.x0 + 5.123) <= 0.5 / per_unit and abs(box.y1 - 2.333) <= 0.5 / per_unit


TRANSPARENT_PAGE = """<!doctype html><meta charset="utf-8">
<style>html, body { margin: 0; height: 100%; } #half { width: 50%; height: 100%; background: rgba(255, 0, 0, 0.5); }
[data-aspect="9:16"] #half { width: 25%; }</style><div id="half"></div>
<script>window.vidgen = {load(ctx) { window.seen = [ctx.width, ctx.height, ctx.aspect, ctx.orientation, ctx.region, ctx.frame.width,
  document.documentElement.dataset.aspect, document.documentElement.dataset.orientation]; }};</script>"""


@pytest.mark.slow
@pytest.mark.render
def test_a_transparent_page_keeps_its_alpha_and_knows_the_videos_shape(tmp_path: Path) -> None:
    _chromium_or_skip()
    from vidgen.web.inputs import page_shape

    (tmp_path / "t.html").write_text(TRANSPARENT_PAGE, encoding="utf-8")
    with WebPage(tmp_path, WebEntry("page", "t.html"), scene_id="w", size=(40, 30), fps=5, frames=1,
                 shape=page_shape((90, 160), "body")) as page:
        pixels = page.frame(0)
        seen = page._page.evaluate("window.seen")
    assert seen == [40, 30, "9:16", "portrait", "body", 90, "9:16", "portrait"]
    assert pixels.shape == (30, 40, 4) and int(pixels[15, 30, 3]) == 0   # nothing drawn: transparent
    assert tuple(int(v) for v in pixels[15, 5]) == (255, 0, 0, 128)       # straight alpha, not premultiplied
    assert int(pixels[15, 15, 3]) == 0                                      # 25 % wide in 9:16


@pytest.mark.slow
@pytest.mark.render
def test_a_body_region_page_sits_under_the_title_on_the_theme_background(make_project: Any) -> None:
    _chromium_or_skip()
    import av

    from vidgen.render.pipeline import render_project

    page = "<!doctype html><style>html { height: 100%; box-sizing: border-box; border: 3px solid #ff0000; }</style>"
    project = web_project(make_project, {"page": "p.html", "region": "body", "title": "Gears"}, {"p.html": page})
    render_project(project, preview=False)
    inputs = json.loads((project.root / "build" / "final" / "web" / "w.json").read_text(encoding="utf-8"))["inputs"]
    assert inputs["width"] < 160 and inputs["height"] < 70 and inputs["shape"]["region"] == "body" and inputs["shape"]["aspect"] == "16:9"
    with av.open(str(project.root / "build" / "final" / "scenes" / "w.mp4")) as video:
        first = next(video.decode(video=0)).to_ndarray(format="rgb24").astype(int)
    background = first[2, 2]
    assert np.abs(first[60, 80] - background).max() < 12   # the page's transparent middle shows the theme background
    red = (first[..., 0] > 150) & (first[..., 1] < 90)
    rows = np.flatnonzero(red.any(axis=1))
    assert rows.size and rows.min() > 15                   # the page's border starts below the title band, not at the frame's top
