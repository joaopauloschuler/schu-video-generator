"""Lint reads a ``web`` page (DESIGN.md §118.12): the page's text as layout objects, the layout
rules on them, ``web_clipped``, naming and opting out. The rules are checked on hand-made
readings (no browser); one ``slow`` + ``render`` test reads real pages in Chromium."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from vidgen.config import LintRules
from vidgen.lint import RULES, StillContext
from vidgen.lint.run import rule_objects
from vidgen.web.layout import declared_problem, lint_opt_out, page_summary, page_text_objects

RULE_SETTINGS = LintRules()


def text_item(name: str, box: list[float], text: str = "Label", **keys: Any) -> dict[str, Any]:
    """One text of a reading of ``data/web/layout.js`` (page px)."""
    return {"name": name, "tag": "div", "source": "html", "text": text, "box": box, "visible": box, "font_px": 24.0,
            "cap_px": 17.3, "color": "#E8EAED", "colors": ["#E8EAED"], "opacity": 1.0, "background": "#0E1116",
            "background_unknown": None, "clipped": None, "cut": None, "lint": None, **keys}


def reading(*texts: dict[str, Any], declared: list[Any] = (), size: tuple[int, int] = (480, 270)) -> dict[str, Any]:  # type: ignore[assignment]
    return {"width": size[0], "height": size[1], "texts": list(texts), "declared": list(declared), "hidden": 1, "canvases": 0}


def run_rule(name: str, objects: list[dict[str, Any]], *, size: tuple[int, int] = (480, 270), **header: Any) -> list[Any]:
    layout = {"width": size[0], "height": size[1], "background": "#0E1116",
              "safe_area": [20.0, 17.0, size[0] - 20.0, size[1] - 17.0], **header}
    ctx = StillContext(layout, {"camera": {}}, rule_objects(objects, name, {}))
    return list(RULES[name].check(ctx, getattr(RULE_SETTINGS, name)))


# ----- reading -> layout objects ------------------------------------------------------------------


def test_page_texts_become_text_objects_in_frame_pixels() -> None:
    page = reading(text_item("gear", [10, 20, 110, 44], "Gears turn", cut={"bottom": 4.0}))
    # region: body, page box 440 x 129 px drawn at (20, 70); page px = frame px here, then a 2x zoom
    (obj,) = page_text_objects({**page, "width": 440, "height": 129}, [20, 70, 460, 199], (480, 270))
    assert obj["kind"] == "text" and obj["class"] == "WebText" and obj["source"] == "web"
    assert obj["id"] == "web:gear" and obj["name"] == "gear" and obj["path"] == "web/gear"
    assert obj["bbox"] == [30.0, 90.0, 130.0, 114.0] and obj["cap_px"] == 17.3 and obj["backdrop"] == "#0E1116"
    assert obj["cut"] == {"bottom": 4.0}   # the page's bottom edge is inside the frame
    (zoomed,) = page_text_objects(page, [0, 0, 960, 540], (480, 270), opacity=0.5)
    assert zoomed["bbox"] == [20.0, 40.0, 220.0, 88.0] and zoomed["cap_px"] == 34.6 and zoomed["opacity"] == 0.5
    assert "cut" not in zoomed   # at the frame's edge a cut is off_frame's


def test_page_summary_and_unknown_backdrop() -> None:
    page = reading(text_item("a", [0, 0, 10, 10], background=None, background_unknown="picture"))
    (obj,) = page_text_objects(page, [0, 0, 480, 270], (480, 270))
    assert obj["backdrop"] is None and obj["backdrop_unknown"] == "picture"
    assert run_rule("contrast", [obj]) == []   # nothing known behind it: not checked
    assert page_summary(page, [0, 0, 480, 270], 12) == {"box": [0, 0, 480, 270], "size": [480, 270], "frame": 12, "texts": 1,
                                                       "declared": 0, "hidden": 1, "canvases": 0}


def test_declared_text_of_a_canvas() -> None:
    item = {"id": "score", "text": "3 : 1", "box": {"x": 40, "y": 20, "width": 60, "height": 30}, "size": 28, "cap": 20.0,
            "color": "#2A3038", "color_alpha": 1, "background": "#101418"}
    bad = [{"text": "x"}, {"text": "", "box": item["box"]}, "text", {**item, "size": -1}, {**item, "box": {**item["box"], "width": 0}}]
    page = reading(declared=[item, {**item}, *bad])
    first, second = page_text_objects(page, [0, 0, 480, 270], (480, 270))
    assert first["name"] == "score" and second["name"] == "score (2)" and first["declared"] is True
    assert first["bbox"] == [40.0, 20.0, 100.0, 50.0] and first["cap_px"] == 20.0 and first["backdrop"] == "#101418"
    assert run_rule("contrast", [first])[0].message.startswith("text '3 : 1' (page: score) has contrast 1.39:1")
    assert [declared_problem(b, 9) is not None for b in bad] == [True] * len(bad)
    no_background = page_text_objects(reading(declared=[{**item, "background": None}]), [0, 0, 480, 270], (480, 270))[0]
    assert no_background["backdrop"] is None and no_background["backdrop_unknown"] == "not declared"


def test_lint_opt_out_values(caplog: pytest.LogCaptureFixture) -> None:
    assert lint_opt_out("off") == ["all"] and lint_opt_out(" off ") == ["all"]
    assert lint_opt_out("off:text_overlap, contrast") == ["text_overlap", "contrast"] and lint_opt_out("off:") == ["all"]
    with caplog.at_level(logging.WARNING, logger="vidgen.web"):
        assert lint_opt_out("off:contrst") == [] and lint_opt_out("on") == []
    assert "contrst" in caplog.text and "'on'" in caplog.text


def test_opted_out_objects_are_left_out_of_their_rules() -> None:
    page = reading(text_item("deco", [0, 0, 50, 6], cap_px=4.0, lint="off"),
                   text_item("ghost", [0, 100, 80, 124], color="#262B33", colors=["#262B33"], lint="off:contrast"),
                   text_item("small", [0, 200, 80, 206], cap_px=4.0))
    deco, ghost, small = page_text_objects(page, [0, 0, 480, 270], (480, 270))
    assert deco["lint_off"] == ["all"] and ghost["lint_off"] == ["contrast"] and "lint_off" not in small
    assert [o["name"] for o in rule_objects([deco, ghost, small], "min_font", {})] == ["ghost", "small"]
    assert [o["name"] for o in rule_objects([deco, ghost, small], "contrast", {})] == ["small"]
    assert [i.objects[0]["name"] for i in run_rule("min_font", [deco, ghost, small])] == ["small"]


# ----- the existing rules on page text --------------------------------------------------------------


def objects_of(*texts: dict[str, Any], box: list[float] = (0, 0, 480, 270), frame: tuple[int, int] = (480, 270)) -> list[dict[str, Any]]:  # type: ignore[assignment]
    objects = page_text_objects(reading(*texts, size=(round(box[2] - box[0]), round(box[3] - box[1]))), list(box), frame)
    for k, obj in enumerate(objects):
        obj["order"] = 0.1 * (k + 1)
    return objects


def test_text_off_the_frame_overlapping_small_and_low_contrast() -> None:
    (off,) = run_rule("off_frame", objects_of(text_item("runaway", [330, 130, 526, 159], "This line runs off")))
    assert off.message == ("text 'This line runs off' (page: runaway) is cut off at the right edge of the frame "
                           "(46 px outside, 23% of its box hidden)")
    (overlap,) = run_rule("text_overlap", objects_of(text_item("a", [80, 90, 195, 119], "First"), text_item("b", [120, 100, 270, 129], "Second")))
    assert overlap.message == "text 'Second' (page: b) overlaps text 'First' (page: a) (43% of the smaller box)"
    (small,) = run_rule("min_font", objects_of(text_item("footnote", [60, 150, 130, 157], "a footnote", cap_px=4.3)))
    assert small.severity == "error" and "4.3 px tall" in small.message
    (grey,) = run_rule("contrast", objects_of(text_item("murky", [70, 100, 219, 129], color="#888888", colors=["#888888"], background="#777777")))
    assert grey.message.endswith("has contrast 1.26:1 (#888888 on #777777); large text needs 3:1")


def test_web_clipped_by_a_container_and_by_the_page_box() -> None:
    card = text_item("card", [70, 120, 357, 146], "A label too long", clipped={"by": "card", "overflow": "hidden", "sides": {"right": 129}})
    (issue,) = run_rule("web_clipped", objects_of(card))
    assert issue.message.startswith("text 'A label too long' (page: card) is cut by its box card (overflow: hidden) at the right "
                                    "(129 px of the text hidden)")
    assert run_rule("off_frame", objects_of({**card, "box": [70, 120, 557, 146]})) == []   # cut by its box first
    tail = text_item("tail", [60, 120, 276, 141], "Cut by the page box", cut={"bottom": 12})
    body = objects_of(tail, box=[20, 70, 460, 199])   # the page's box: 440 x 129 under a title
    (cut,) = run_rule("web_clipped", body)
    assert cut.message.startswith("text 'Cut by the page box' (page: tail) runs past the page's box at the bottom (12 px")
    assert run_rule("safe_area", body) == [] and run_rule("off_frame", body) == []
    assert run_rule("web_clipped", objects_of(text_item("ok", [0, 0, 10, 10], cut={"bottom": 0.6}))) == []   # within tolerance


def test_text_under_the_captions_is_one_finding_naming_them() -> None:
    reserved = [{"overlay": "captions", "type": "captions", "box": [64.0, 211.0, 416.0, 253.0]}]
    low = objects_of(text_item("low", [60, 228, 287, 252], "A note low"))
    caption = {"id": "c", "kind": "text", "class": "Text", "path": "overlay:captions/Text[0]", "name": None, "text": "Words",
               "bbox": [110, 234, 369, 248], "opacity": 1.0, "order": 1040, "overlay": "captions", "font_px": 14, "colors": ["#FFFFFF"]}
    safe = [20.0, 17.0, 460.0, 204.0]   # the safe area leaves out the captions' band
    (issue,) = run_rule("safe_area", low + [caption], reserved=reserved, safe_area=safe)
    assert issue.message.startswith("text 'A note low' (page: low) is in the part of the frame overlay 'captions' (captions) keeps "
                                    "for itself, outside the safe area at the bottom")
    assert "region: body" in issue.message
    assert run_rule("overlay_overlap", low + [caption], reserved=reserved, safe_area=safe) == []   # safe_area's finding
    lower_third = {**caption, "overlay": "lower_third", "path": "overlay:lower_third/Text[0]"}
    assert len(run_rule("overlay_overlap", low + [lower_third], reserved=reserved, safe_area=safe)) == 1   # it keeps nothing: reported


# ----- the scene's side -----------------------------------------------------------------------------


def test_recorder_puts_page_texts_above_the_page_picture() -> None:
    from vidgen.introspect import LayoutRecorder

    recorder = LayoutRecorder()
    view = object()
    scene = SimpleNamespace(page_layout=lambda frame: (reading(text_item("a", [0, 0, 48, 27]), text_item("b", [0, 100, 48, 127])), view),
                            camera=SimpleNamespace(pixel_width=480, pixel_height=270))
    objects = [{"id": recorder._id(view), "bbox": [0.0, 0.0, 240.0, 135.0], "opacity": 0.8, "order": 3},
               {"id": "title", "bbox": [0, 0, 1, 1], "opacity": 1.0, "order": 4}]
    keys = recorder._page_texts(scene, SimpleNamespace(frame=7), objects)  # type: ignore[arg-type]
    assert [o["id"] for o in objects] == [objects[0]["id"], "web:a", "web:b", "title"]
    assert objects[1]["order"] == pytest.approx(3 + 1 / 3) and objects[2]["order"] == pytest.approx(3 + 2 / 3)
    assert objects[1]["bbox"] == [0.0, 0.0, 24.0, 13.5] and objects[1]["opacity"] == 0.8
    assert keys == {"web": {"box": [0.0, 0.0, 240.0, 135.0], "size": [480, 270], "frame": 7, "texts": 2, "declared": 0, "hidden": 1,
                            "canvases": 0}}
    assert recorder._page_texts(SimpleNamespace(), SimpleNamespace(frame=7), objects) == {}   # type: ignore[arg-type]


def test_planned_still_frames_follow_the_capture() -> None:
    from manim import config

    from vidgen.browser.timing import planned_still_frames

    fps = int(config.frame_rate)
    windows = {"b1": 1.0, "b2": 0.5}
    scene = SimpleNamespace(beats=[SimpleNamespace(id="b1"), SimpleNamespace(id="b2")], capture=None,
                            beat_window=lambda beat: SimpleNamespace(window=windows[beat.id]))
    assert planned_still_frames(scene) == [fps - 1, fps + round(0.5 * fps) - 1]
    scene.capture = SimpleNamespace(per_beat=2)
    assert planned_still_frames(scene) == sorted({round(0.5 * fps) - 1, fps - 1, fps + round(0.25 * fps) - 1, fps + round(0.5 * fps) - 1})
    silent = SimpleNamespace(beats=[], capture=None, spec=SimpleNamespace(duration=2.0), outro=0.5)
    assert planned_still_frames(silent) == [round(1.5 * fps) - 1]


# ----- in Chromium ------------------------------------------------------------------------------------


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body { margin: 0; font: 20px sans-serif; color: #fff; }
.abs { position: absolute; white-space: nowrap; }
</style></head><body>
<div class="abs" data-vidgen-id="plain" style="left: 10px; top: 10px">Plain <b>bold</b> words</div>
<div class="abs" style="left: 10px; top: 50px; transform: scale(0.5); transform-origin: 0 0"><span data-vidgen-id="half" style="display: block">Half size</span></div>
<div class="abs" data-vidgen-id="box" style="left: 10px; top: 90px; width: 60px; overflow: hidden; background: rgba(255, 0, 0, 0.5)">Too long for the box</div>
<div style="overflow: hidden; width: 40px; height: 40px; margin-left: 300px"><div class="abs" data-vidgen-id="escape" style="left: 300px; top: 10px">Escapes</div></div>
<div class="abs" data-vidgen-id="gone" style="left: 10px; top: 130px; opacity: 0">Hidden</div>
<div class="abs" data-vidgen-id="none" style="left: 10px; top: 130px; display: none">None</div>
<div class="abs" data-vidgen-id="grad" style="left: 200px; top: 130px; width: 100px; height: 40px; background: linear-gradient(red, blue)"><span>On a gradient</span></div>
<div data-vidgen-lint="off:contrast"><div class="abs" data-vidgen-id="deco" style="left: 10px; top: 170px">Decor</div></div>
<svg class="abs" style="left: 300px; top: 100px" width="100" height="60" viewBox="0 0 50 30"><rect width="50" height="30" fill="#204060"/>
<text data-vidgen-id="svg" x="2" y="20" font-size="10" fill="#ffcc00">SVG <tspan>text</tspan></text></svg>
<script>window.vidgen = {layout: (t, ctx) => [{id: 'drawn', text: `t=${t}`, box: {x: 1, y: 2, width: 30, height: 10}, size: 10, color: 'red'},
  {id: 'canvas_font', text: 'A', box: {x: 1, y: 20, width: 20, height: 24}, size: 20, font: '700 20px sans-serif'},
  {id: 'family', text: 'A', box: {x: 1, y: 50, width: 20, height: 24}, size: 20, font: 'sans-serif'}]};</script>
</body></html>"""


@pytest.mark.slow
@pytest.mark.render
def test_layout_reader_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from vidgen.browser.chromium import missing_dependency
    from vidgen.web.clip import layout_record_path, make_web_clip, web_page_layouts

    if missing_dependency() is not None:
        pytest.skip("no Chromium")
    (tmp_path / "p.html").write_text(PAGE, encoding="utf-8")
    theme = {"background": "#000000", "colors": {}, "palette": [], "fonts": {}, "sizes": {}}
    args = {"size": (480, 270), "fps": 10, "frames": 4, "theme": theme}
    folder = tmp_path / "web"
    make_web_clip(tmp_path, folder, "s", {"page": "p.html"}, **args, layout_frames=[2])
    drawn = web_page_layouts(tmp_path, folder, "s", {"page": "p.html"}, **args, at=[2])[2]
    texts = {t["name"]: t for t in drawn["texts"]}
    assert set(texts) == {"plain", "half", "box", "escape", "grad", "deco", "svg"} and drawn["hidden"] == 2
    assert texts["plain"]["text"] == "Plain bold words" and texts["plain"]["font_px"] == 20
    assert texts["half"]["font_px"] == 10 and texts["half"]["box"][3] - texts["half"]["box"][1] < 13
    assert texts["box"]["clipped"]["by"] == "box" and texts["box"]["clipped"]["sides"]["right"] > 50
    assert texts["box"]["background"] == "#800000"   # half-transparent red over the theme's black
    assert texts["escape"]["clipped"] is None   # absolutely placed: its static parent does not clip it
    assert texts["grad"]["background"] is None and texts["grad"]["background_unknown"] == "gradient"
    assert texts["deco"]["lint"] == "off:contrast"
    assert texts["svg"]["text"] == "SVG text" and texts["svg"]["font_px"] == pytest.approx(20, abs=0.1)
    assert texts["svg"]["color"] == "#FFCC00" and texts["svg"]["background"] == "#204060"
    assert drawn["declared"][0]["text"] == "t=0.2" and drawn["declared"][0]["color"] == "#FF0000"
    # Step 333: a declared font may be the canvas font ("700 20px …") or a family; both give the cap height
    canvas_font, family = drawn["declared"][1]["cap"], drawn["declared"][2]["cap"]
    assert 10 < family < 18 and canvas_font == pytest.approx(family, rel=0.08)
    layout_record_path(folder, "s").unlink()
    stepped = web_page_layouts(tmp_path, folder, "s", {"page": "p.html"}, **args, at=[2])[2]
    assert stepped == drawn   # stepping the page without screenshots reads the same
