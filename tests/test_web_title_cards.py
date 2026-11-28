"""vidgen's opening title and end card for films (Step 364): the module
``vidgen/title-cards``, served by name through the import map and in a page's loaded-files record;
its options checked with a "did you mean", its timing and layout (16:9 and 9:16) in Node when it is
installed. In Chromium (``slow``): a page with both cards draws the same frames twice, the card
shows only while it should, and the text is HTML over the canvas."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import VIDGEN_MODULES, current_loaded, vidgen_file
from vidgen.web.page import INIT_FILES, engine_id

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "src" / "vidgen" / "data" / "web" / "modules" / "title-cards.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)


def test_the_module_is_served_by_its_import_name_and_imports_nothing() -> None:
    assert VIDGEN_MODULES["vidgen/title-cards"] == "title-cards.js"
    assert IMPORT_MAP["imports"]["vidgen/title-cards"] == "/__vidgen__/modules/title-cards.js"
    assert vidgen_file("modules/title-cards.js") == MODULE
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == [] and "Math.random" not in source and "Date.now" not in source
    assert MODULE not in INIT_FILES and MODULE.stem not in engine_id()
    rel = "__vidgen__/modules/title-cards.js"
    assert len(current_loaded(Path("."), [rel])[rel] or "") == 64


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``C`` and print ``body``'s ``out`` as JSON."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    (tmp_path / "title-cards.mjs").symlink_to(MODULE)
    (tmp_path / "t.mjs").write_text("import * as C from './title-cards.mjs';\nconst out = [];\n"
                                    "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
                                    f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=30, check=True)
    return json.loads(done.stdout)


def test_options_are_checked_with_a_did_you_mean(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
out.push(err(() => C.cardOptions("title", {title: "A", fadein: 2})));
out.push(err(() => C.cardOptions("end", {title: "A", line: ["x"]})));
out.push(err(() => C.cardOptions("title", {subtitle: "no title"})));
out.push(err(() => C.cardOptions("title", {title: "A", side: "centre"})));
out.push(err(() => C.cardOptions("title", {title: "A", shade: 2})));
out.push(err(() => C.cardOptions("title", {title: "A", lines: ["only on an end card"]})));
out.push(err(() => C.cardOptions("end", {title: "A", lines: "one string"})));
const t = C.cardOptions("title", {title: "A"}), e = C.cardOptions("end", {title: "A", shade: true});
out.push([t.side, t.start, t.fadeIn, t.hold, t.fadeOut, t.size, t.tracking, t.rule, t.shade, t.id]);
out.push([e.side, e.hold === Infinity, e.size, e.shade, e.id, e.lines]);
""")
    assert 'unknown option "fadein" (did you mean "fadeIn"?)' in out[0] and out[0].startswith("vidgen/title-cards: titleCard:")
    assert 'endCard: unknown option "line" (did you mean "lines"?)' in out[1]
    assert "title must be a non-empty string" in out[2]
    assert 'side must be one of "left", "right", "top", "bottom"' in out[3]
    assert "shade must be a number from 0 to 1" in out[4]
    assert 'titleCard: unknown option "lines"' in out[5]
    assert "lines must be a list of strings" in out[6]
    assert out[7] == ["left", 2, 2, 8, 2, 3.9, 0.26, True, 0.45, "title-card"]
    assert out[8] == ["right", True, 2.7, 0.45, "end-card", []]


def test_timing_and_layout_in_landscape_and_portrait(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const o = {start: 2, fadeIn: 2, hold: 8, fadeOut: 2};
out.push([0, 2, 3, 4, 10, 13, 14, 20].map((t) => +C.cardAlpha(t, o).toFixed(3)));
out.push([0, 2.25, 100].map((t) => +C.cardAlpha(t, {start: 1, fadeIn: 2.5, hold: Infinity, fadeOut: 0}).toFixed(3)));
out.push([2, 8, 14].map((t) => +C.cardSettle(t, o).toFixed(3)));
for (const [w, h, side] of [[1280, 720, "left"], [1280, 720, "right"], [1920, 1080, "left"], [2560, 1080, "left"], [1080, 1920, "left"], [1080, 1920, "top"]]) {
  const L = C.cardLayout(w, h, {side});
  out.push([L.side, L.portrait, +L.k.toFixed(2), +L.x.toFixed(1), +L.width.toFixed(1), +L.y.toFixed(1), L.shade]);
}
""")
    assert out[0] == [0, 0, 0.5, 1, 1, 0.5, 0, 0]
    assert out[1] == [0, 0.5, 1]
    assert out[2] == [0, 0.5, 1]
    assert out[3] == ["left", False, 12.8, 70.4, 512, 331.2, 90]          # Escapement's opening: 5.5vw, 46vh
    assert out[4] == ["right", False, 12.8, 652.8, 556.8, 324, 270]       # its end card: 51vw
    assert out[5][2] == 19.2 and out[6][2] == 19.2                         # 21:9: sized by the height
    assert out[7][:3] == ["bottom", True, 18.36] and out[7][3] == 86.4 and out[7][5] == 1228.8
    assert out[8][0] == "top" and out[8][5] == 460.8 and out[8][6] == 180


PAGE = """import {titleCard, endCard} from "vidgen/title-cards";
let opening, ending;
export async function load(ctx) {
  document.body.style.background = "#000";
  opening = await titleCard(ctx, {title: "TIDEWATER", subtitle: "a film in four tides", start: 0.2, fadeIn: 0.2, hold: 0.4, fadeOut: 0.2});
  ending = await endCard(ctx, {title: "TIDEWATER", subtitle: "made with a generator", lines: ["One line.", "Another."], start: 1.2, fadeIn: 0.2});
}
export function frame(t) { document.title = JSON.stringify([opening.update(t), ending.update(t)]); }
"""


@pytest.mark.slow
@pytest.mark.render
def test_cards_draw_the_same_frames_every_time_in_both_shapes(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "cards.js").write_text(PAGE, encoding="utf-8")

    def draw(size: tuple[int, int]) -> tuple[list[np.ndarray], dict]:
        with WebPage(tmp_path, WebEntry("script", "cards.js"), scene_id="c", size=size, fps=10, frames=16) as page:
            return [page.frame(n) for n in (0, 5, 15)], dict(page.loaded)

    for size, left in (((320, 180), True), ((180, 320), False)):
        (first, loaded), (again, _) = draw(size), draw(size)
        assert all(np.array_equal(a, b) for a, b in zip(first, again))
        blank, opening, ending = (f[..., :3].astype(float) for f in first)
        assert blank.max() < 8                                  # before the title: nothing but the page
        w = size[0]
        lit = opening.max(axis=(0, 2)) > 60                     # the title's columns
        assert lit.any() and (lit[: w // 2].sum() > lit[w // 2:].sum() if left else True)
        assert ending.max() > 60 and not np.array_equal(opening, ending)
        assert "__vidgen__/modules/title-cards.js" in loaded


def test_the_cookbook_guide_and_reference_describe_the_cards() -> None:
    cookbook = (ROOT / "docs" / "COOKBOOK-3D.md").read_text(encoding="utf-8")
    section = cookbook.split("## 12. Opening titles and end cards for films", 1)[1]
    for part in ("**Asymmetry.**", "**Restraint.**", "**Quiet space behind the text.**", "**Slow timing.**",
                 "**A matching end card.**", "**When not to.**", 'from "vidgen/title-cards"', "titleCard(ctx", "endCard(ctx"):
        assert part in section, part
    assert "github" not in section.lower()
    assert "COOKBOOK-3D.md#12-opening-titles-and-end-cards-for-films" in (ROOT / "docs" / "COOKBOOK.md").read_text(encoding="utf-8")
    assert "**Opening titles and end cards: `vidgen/title-cards`**" in (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    from vidgen.guide import find_topic

    assert "**Opening titles and end cards: `vidgen/title-cards`.**" in find_topic("web").text
