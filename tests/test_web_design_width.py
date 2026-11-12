"""``design_width:`` of a ``web`` scene (Step 339, DESIGN.md §118.17): a page built in fixed
pixels is laid out in a window that many CSS pixels wide and drawn at the output size. The
param's checks, the window and scale, the cut of a screenshot, the cache key and the lint units
without a browser; tiny pages in Playwright's Chromium (``slow``, skipped when it is missing)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from vidgen.errors import VidgenError
from vidgen.web import clip as web_clip
from vidgen.web.entry import WebEntry
from vidgen.web.inputs import DESIGN_WIDTH_MAX, DESIGN_WIDTH_MIN, css_height, design_width_of, design_width_problem, page_viewport
from vidgen.web.layout import page_text_objects
from vidgen.web.page import WebPage, fit_pixels

from test_scene_web import _chromium_or_skip, _fake_page, web_project
from test_web_lint import reading, run_rule, text_item

# ----- the param ----------------------------------------------------------------------------------


def test_design_width_is_a_whole_number_of_css_pixels_in_a_sane_range() -> None:
    from vidgen.scenes.web import Web

    assert Web.Params(page="p.html").design_width is None
    assert Web.Params(page="p.html", design_width=1280).design_width == 1280
    assert Web.Params(script="s.js", design_width=390.0).design_width == 390
    for bad in (0, -1280, 50, DESIGN_WIDTH_MIN - 1, DESIGN_WIDTH_MAX + 1, 100_000):
        assert "is not a window width a page is designed for" in str(design_width_problem(bad))
        with pytest.raises(ValidationError, match="is not a window width a page is designed for"):
            Web.Params(page="p.html", design_width=bad)
    for bad in (1280.5, True, "wide", "1280", [1280]):
        assert "is not a whole number of CSS pixels" in str(design_width_problem(bad))
        with pytest.raises(ValidationError, match="not a whole number of CSS pixels"):
            Web.Params(page="p.html", design_width=bad)
    assert design_width_problem(None) is None and design_width_problem(DESIGN_WIDTH_MIN) is None
    assert design_width_of({"page": "p.html"}) is None and design_width_of(Web.Params(page="p.html", design_width=800)) == 800


def test_validate_reports_a_bad_design_width_at_its_param(make_project: Any) -> None:
    from vidgen.cli import check_project

    problems = check_project(web_project(make_project, {"page": "p.html", "design_width": 3}, {"p.html": "<p>"}))
    assert len(problems) == 1 and problems[0].startswith(
        "scenes[0].params.design_width: 3 is not a window width a page is designed for (give the width in CSS pixels, 200 to 8192")
    assert check_project(web_project(make_project, {"page": "p.html", "design_width": 1280}, {"p.html": "<p>"})) == []


# ----- the window and its scale -------------------------------------------------------------------


def test_without_design_width_the_window_is_the_frame() -> None:
    assert page_viewport((854, 480)) == ((854, 480), 1.0)
    assert css_height((854, 480)) == 480.0


@pytest.mark.parametrize(("size", "design", "window", "scale"), [
    ((1920, 1080), 1280, (1280, 720), 1.5),
    ((854, 480), 1280, (1280, 720), 854 / 1280),       # 719.44 CSS px high: rounded up
    ((160, 90), 1280, (1280, 720), 0.125),
    ((1920, 1080), 1000, (1000, 563), 1.92),            # 562.5 -> 563
    ((1080, 1920), 390, (390, 694), 1080 / 390),        # a phone page in a vertical video
    ((1700, 820), 1280, (1280, 618), 1700 / 1280),      # region: body
])
def test_the_window_is_design_width_wide_and_as_high_as_the_frames_shape(
        size: tuple[int, int], design: int, window: tuple[int, int], scale: float) -> None:
    viewport, factor = page_viewport(size, design)
    assert viewport == window and factor == pytest.approx(scale)
    assert viewport[1] * factor >= size[1] - 1e-6 and (viewport[1] - 1) * factor < size[1]   # never short, under 1 CSS px over
    assert css_height(size, design) == pytest.approx(size[1] / factor) and css_height(size, design) <= viewport[1] + 1e-6


def test_a_screenshot_is_cut_to_the_frame() -> None:
    pixels = np.arange(8 * 10 * 4, dtype=np.uint8).reshape(8, 10, 4)
    assert fit_pixels(pixels, (10, 8), 1.5, "the page") is not None and fit_pixels(pixels, (10, 8), 1.5, "p").shape == (8, 10, 4)
    cut = fit_pixels(pixels, (10, 6), 1.92, "the page")   # ceil(1.92) + 1 = 3 spare rows
    assert cut.shape == (6, 10, 4) and np.array_equal(cut, pixels[:6])
    with pytest.raises(VidgenError, match="the page drew 10x8 px, expected 10x9"):
        fit_pixels(pixels, (10, 9), 1.5, "the page")      # too short: never stretched
    with pytest.raises(VidgenError, match="drew 10x8 px, expected 10x4"):
        fit_pixels(pixels, (10, 4), 1.5, "the page")      # more than a CSS pixel over: not this window


# ----- the cache key ------------------------------------------------------------------------------


def test_the_key_of_a_clip_without_design_width_is_unchanged(tmp_path: Path) -> None:
    (tmp_path / "p.html").write_text("<p>", encoding="utf-8")
    entry = WebEntry("page", "p.html")
    plain = web_clip.clip_inputs(tmp_path, entry, scene_id="p", size=(16, 9), fps=5, frames=2)
    assert sorted(plain) == ["alpha", "beats", "data", "engine", "fps", "frames", "height", "kind", "path", "scene", "sha256",
                             "shape", "theme", "version", "width"]   # as before Step 339: old clips are reused
    assert plain["version"] == 3
    wide = web_clip.clip_inputs(tmp_path, entry, scene_id="p", size=(16, 9), fps=5, frames=2, design_width=1280)
    assert wide == {**plain, "design_width": 1280}


def test_the_clip_is_drawn_again_when_design_width_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drawn: list[str] = []
    widths: list[Any] = []
    fake = _fake_page(drawn, {"p.html": ""})

    class Page(fake):  # type: ignore[misc, valid-type]
        def __init__(self, root: Path, *args: Any, **kw: Any) -> None:
            super().__init__(root, *args, **kw)
            widths.append(kw.get("design_width"))

    monkeypatch.setattr(web_clip, "WebPage", Page)
    (tmp_path / "p.html").write_text("<p>", encoding="utf-8")
    out = tmp_path / "build"
    make = lambda **params: web_clip.make_web_clip(tmp_path, out, "p", {"page": "p.html", **params}, size=(16, 16), fps=5, frames=2)  # noqa: E731
    make()
    make()
    make(design_width=1280)
    make(design_width=1280)
    make(design_width=1000)
    assert widths == [None, 1280, 1000]
    assert json.loads((out / "p.json").read_text(encoding="utf-8"))["inputs"]["design_width"] == 1000


# ----- lint: the page's CSS pixels become output pixels -------------------------------------------


def test_lint_judges_the_output_size_of_a_design_width_page() -> None:
    # a 1280 x 720 CSS px window drawn as the whole 1920 x 1080 frame: 1.5 output px per CSS px
    small = text_item("small", [100, 100, 300, 114], font_px=12.0, cap_px=8.7)
    wide = text_item("wide", [1100, 300, 1300, 330])                       # 20 CSS px past the window's right edge
    low = text_item("low", [100, 694, 300, 719])                           # 1 CSS px above the window's bottom edge
    boxed = text_item("boxed", [500, 300, 700, 330], clipped={"by": "box", "overflow": "hidden", "sides": {"right": 10.0}})
    page = reading(small, wide, low, boxed, declared=[{"text": "On canvas", "box": {"x": 100, "y": 400, "width": 200, "height": 20}, "size": 16}],
                   size=(1280, 720))
    objects = {o["name"]: o for o in page_text_objects(page, [0, 0, 1920, 1080], (1920, 1080))}
    assert objects["small"]["font_size_px"] == 18.0 and objects["small"]["cap_px"] == pytest.approx(13.05, abs=0.06)
    assert objects["small"]["bbox"] == [150.0, 150.0, 450.0, 171.0]
    assert objects["wide"]["bbox"][2] == 1950.0 and objects["boxed"]["clipped"]["sides"] == {"right": 15.0}
    assert objects["On canvas"]["font_size_px"] == 24.0 and objects["On canvas"]["bbox"] == [150.0, 600.0, 450.0, 630.0]
    found = run_rule("off_frame", list(objects.values()), size=(1920, 1080))
    assert [[o["id"] for o in f.objects] for f in found] == [["web:wide"]]
    assert {o["id"] for f in run_rule("safe_area", list(objects.values()), size=(1920, 1080)) for o in f.objects} >= {"web:low"}
    (tiny,) = [f for f in run_rule("min_font", list(objects.values()), size=(1920, 1080)) if f.objects[0]["id"] == "web:small"]
    assert "is 13.0 px tall (cap height, 1.20% of the frame's shorter side" in tiny.message   # 8.7 CSS px x 1.5
    # the same page as a 854 x 480 preview: 0.667 output px per CSS px
    preview = {o["name"]: o for o in page_text_objects(page, [0, 0, 854, 480], (854, 480))}
    assert preview["small"]["font_size_px"] == 8.0 and preview["small"]["bbox"][0] == pytest.approx(66.7, abs=0.06)


def test_a_declared_texts_cut_is_in_output_pixels() -> None:
    page = reading(declared=[{"text": "Past the edge", "box": {"x": 600, "y": 10, "width": 100, "height": 20}}], size=(640, 360))
    (obj,) = page_text_objects(page, [100, 100, 420, 280], (480, 270))   # region: body, 0.5 output px per CSS px
    assert obj["cut"] == {"right": 30.0}


# ----- pages in Chromium --------------------------------------------------------------------------

FIXED_PAGE = """<!doctype html><meta charset="utf-8">
<style>html, body { margin: 0; height: 100%; background: #ffffff; }
#box { position: absolute; left: 0; top: 0; width: 160px; height: 90px; background: #ff0000; }
#wide { position: absolute; left: 0; bottom: 0; width: 50vw; height: 20px; background: #00ff00; }
#t { position: absolute; left: 170px; top: 10px; font: 12px sans-serif; color: #000000; }
canvas { position: absolute; left: 0; width: 100%; height: 20px; }
@media (min-width: 300px) { #box { background: #0000ff; } }</style>
<div id="box"></div><div id="wide"></div><div id="t" data-vidgen-id="t">Fixed</div>
<canvas id="soft" style="top: 100px"></canvas><canvas id="sharp" style="top: 130px"></canvas>
<script>
const soft = document.getElementById('soft'); soft.width = soft.clientWidth; soft.height = soft.clientHeight;
let g = soft.getContext('2d'); g.fillRect(0, 0, 100.5, 20);
const sharp = document.getElementById('sharp'); const d = window.devicePixelRatio;
sharp.width = Math.round(sharp.clientWidth * d); sharp.height = Math.round(sharp.clientHeight * d);
g = sharp.getContext('2d'); g.scale(d, d); g.fillRect(0, 0, 100.5, 20);
window.seen = {inner: [innerWidth, innerHeight], dpr: d, client: document.documentElement.clientWidth,
  rect: document.getElementById('box').getBoundingClientRect().width, wide: document.getElementById('wide').getBoundingClientRect().width,
  query: matchMedia('(min-width: 300px) and (max-width: 400px)').matches, soft: soft.width, sharp: sharp.width};
window.vidgen = {load(ctx) { window.seen.ctx = [ctx.width, ctx.height, ctx.frame.width, ctx.frame.height]; }};
</script>"""


def _fixed_page(root: Path, size: tuple[int, int], design_width: int | None = 320) -> tuple[np.ndarray, dict[str, Any], dict[str, Any]]:
    """Frame 0 of :data:`FIXED_PAGE` at ``size``, what the page saw and its layout reading."""
    (root / "f.html").write_text(FIXED_PAGE, encoding="utf-8")
    with WebPage(root, WebEntry("page", "f.html"), scene_id="w", size=size, fps=5, frames=1, design_width=design_width) as page:
        pixels = page.frame(0)
        return pixels, page._page.evaluate("window.seen"), page.layout(0)


@pytest.mark.slow
@pytest.mark.render
def test_a_fixed_pixel_page_sees_its_design_window_at_two_output_sizes(tmp_path: Path) -> None:
    _chromium_or_skip()
    for size, scale in (((640, 360), 2.0), ((160, 90), 0.5)):
        pixels, seen, layout = _fixed_page(tmp_path, size)
        assert pixels.shape == (size[1], size[0], 4)                       # exactly the output size
        assert seen["inner"] == [320, 180] and seen["client"] == 320 and seen["dpr"] == scale
        assert seen["rect"] == 160 and seen["wide"] == 160 and seen["query"] is True
        assert seen["ctx"] == [320, 180, size[0], size[1]]                 # ctx.width / height: CSS px; ctx.frame: output px
        w, h = size
        blue = (pixels[..., 2] > 200) & (pixels[..., 0] < 60) & (pixels[..., 1] < 60)   # the 160 x 90 px box: half the frame each way
        assert blue[: h // 2 - 1, : w // 2 - 1].all() and not blue[h // 2 + 1:].any() and not blue[:, w // 2 + 1:].any()
        green = (pixels[..., 1] > 200) & (pixels[..., 0] < 60)
        assert green[h - 1, : w // 2 - 1].all() and not green[h - 1, w // 2 + 1:].any()   # bottom: 0 reaches the frame's last row
        (text,) = page_text_objects(layout, [0, 0, w, h], size)
        assert layout["width"] == 320 and layout["height"] == 180 and text["font_size_px"] == 12 * scale
        assert text["bbox"][0] == pytest.approx(170 * scale, abs=0.11)
        assert seen["soft"] == 320 and seen["sharp"] == w


@pytest.mark.slow
@pytest.mark.render
def test_a_canvas_is_sharp_only_when_it_uses_device_pixel_ratio(tmp_path: Path) -> None:
    _chromium_or_skip()
    pixels, _, _ = _fixed_page(tmp_path, (640, 360))
    soft, sharp = pixels[220, 190:212, 0].astype(int), pixels[280, 190:212, 0].astype(int)   # across the edge at x = 100.5 CSS px
    assert set(sharp.tolist()) == {0, 255} and int((sharp == 0).sum()) == 11   # 201 output px: on a pixel edge
    assert ((soft > 20) & (soft < 235)).sum() >= 2                              # drawn at 320 px, enlarged: a blurred edge


@pytest.mark.slow
@pytest.mark.render
def test_a_window_that_is_not_a_whole_number_of_pixels_high_is_cut_to_the_frame(tmp_path: Path) -> None:
    _chromium_or_skip()
    for size, design, window in (((213, 121), 320, 182), ((500, 281), 260, 147)):   # 181.78 and 146.12 CSS px high
        (tmp_path / "f.html").write_text(FIXED_PAGE, encoding="utf-8")
        with WebPage(tmp_path, WebEntry("page", "f.html"), scene_id="w", size=size, fps=5, frames=1, design_width=design) as page:
            pixels, inner, layout = page.frame(0), page._page.evaluate("[innerWidth, innerHeight]"), page.layout(0)
        assert pixels.shape == (size[1], size[0], 4) and inner == [design, window]
        assert layout["height"] == pytest.approx(size[1] * design / size[0], abs=0.001)   # what the frame shows of the window


@pytest.mark.slow
@pytest.mark.render
def test_without_design_width_the_page_is_as_before(tmp_path: Path) -> None:
    _chromium_or_skip()
    pixels, seen, layout = _fixed_page(tmp_path, (64, 36), None)
    assert pixels.shape == (36, 64, 4) and seen["inner"] == [64, 36] and seen["dpr"] == 1 and seen["ctx"] == [64, 36, 64, 36]
    assert layout["width"] == 64 and layout["height"] == 36


SCRIPT = """import * as THREE from "three";
export function load(ctx) {
  const renderer = new THREE.WebGLRenderer({alpha: true});
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(100, 50);
  window.seen = {ctx: [ctx.width, ctx.height], canvas: [ctx.canvas.width, ctx.canvas.height, ctx.canvas.clientWidth],
                 three: [renderer.domElement.width, renderer.domElement.height, renderer.domElement.style.width], dpr: window.devicePixelRatio};
  const g = ctx.canvas.getContext('2d');
  g.fillStyle = '#ff0000';
  g.fillRect(0, 0, ctx.width / 2, ctx.height);
}
"""


@pytest.mark.slow
@pytest.mark.render
def test_a_script_and_three_js_with_design_width(tmp_path: Path) -> None:
    _chromium_or_skip()
    (tmp_path / "s.js").write_text(SCRIPT, encoding="utf-8")
    with WebPage(tmp_path, WebEntry("script", "s.js"), scene_id="w", size=(480, 270), fps=5, frames=1, design_width=320) as page:
        pixels, seen = page.frame(0), page._page.evaluate("window.seen")
    assert seen["ctx"] == [320, 180] and seen["canvas"] == [320, 180, 320] and seen["dpr"] == 1.5
    assert seen["three"] == [150, 75, "100px"]            # setPixelRatio(devicePixelRatio): output pixels
    assert pixels.shape == (270, 480, 4)
    assert tuple(int(v) for v in pixels[135, 100]) == (255, 0, 0, 255) and int(pixels[135, 380, 3]) == 0   # half the frame, the rest transparent


@pytest.mark.slow
@pytest.mark.render
def test_render_a_design_width_page_in_the_body_region(make_project: Any) -> None:
    _chromium_or_skip()
    import av

    from vidgen.render.pipeline import render_project

    page = ("<!doctype html><style>html { height: 100%; box-sizing: border-box; border: 12px solid #ff0000; }</style>"
            "<script>window.vidgen = {load(ctx) { if (innerWidth !== 400 || ctx.width !== 400) throw new Error('window ' + innerWidth); }};</script>")
    project = web_project(make_project, {"page": "p.html", "region": "body", "title": "Gears", "design_width": 400}, {"p.html": page})
    render_project(project, preview=False)
    inputs = json.loads((project.root / "build" / "final" / "web" / "w.json").read_text(encoding="utf-8"))["inputs"]
    assert inputs["design_width"] == 400 and inputs["width"] < 160 and inputs["height"] < 70 and inputs["shape"]["region"] == "body"
    scale = inputs["width"] / 400
    from vidgen.theme import Theme

    assert inputs["theme"]["sizes"]["body"] * scale == pytest.approx(float(Theme().sizes["body"]) * 90 / (72 * 8.0), rel=0.01)   # as tall as vidgen's text
    with av.open(str(project.root / "build" / "final" / "scenes" / "w.mp4")) as video:
        first = next(video.decode(video=0)).to_ndarray(format="rgb24").astype(int)
    assert first.shape[:2] == (90, 160)
    background = first[2, 2]
    assert np.abs(first[60, 80] - background).max() < 12   # the page's transparent middle shows the theme background
    red = (first[..., 0] > 150) & (first[..., 1] < 90)
    rows = np.flatnonzero(red.any(axis=1))
    assert rows.size and rows.min() > 15                   # the page starts below the title
    cols = np.flatnonzero(red.any(axis=0))
    assert 3 <= int(red[:, cols.min():cols.min() + 12].any(axis=0).sum()) and cols.max() - cols.min() > 100


def test_lint_gives_the_same_verdict_at_the_preview_size() -> None:
    page = reading(text_item("small", [100, 100, 300, 114], font_px=12.0, cap_px=8.7), text_item("big", [100, 200, 600, 250], font_px=44.0, cap_px=32.0),
                   size=(1280, 720))
    for size in ((1920, 1080), (854, 480)):
        found = run_rule("min_font", page_text_objects(page, [0, 0, *size], size), size=size)
        assert [f.objects[0]["id"] for f in found] == ["web:small"], size
