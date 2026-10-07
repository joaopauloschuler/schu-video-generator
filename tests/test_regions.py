"""Layout regions (``vidgen.regions``): safe area, named regions, grids, ``place``, readable text,
and the built-in scenes laid out with them (``bullets``, ``code``) at 16:9 and 9:16."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from manim import DL, UR, Rectangle, Square, Text, tempconfig

from conftest import minimal_config
from vidgen import extensions, registry, runtime
from vidgen.errors import VidgenError
from vidgen.layout import fit_text_sized
from vidgen.project import Project
from vidgen.regions import (
    GAP,
    MARGIN_X,
    MARGIN_Y,
    REGION_NAMES,
    Region,
    frame_region,
    grid,
    orientation,
    place,
    readable_size,
    readable_text,
    region,
    safe_area,
)
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.render.worker import frame_size
from vidgen.scenes.code import MIN_COLUMNS, wrap_code

SIZES = {"landscape": (160, 90), "portrait": (90, 160), "square": (100, 100)}


@pytest.fixture(params=["landscape", "portrait", "square"])
def frame(request: pytest.FixtureRequest) -> Iterator[str]:
    """Manim's config set to a frame of each orientation (shorter side 8 units, as the worker)."""
    w, h = SIZES[request.param]
    fw, fh = frame_size(w, h)
    with tempconfig({"pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "verbosity": "ERROR"}):
        yield request.param


@pytest.fixture
def landscape() -> Iterator[None]:
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_width": 128 / 9, "frame_height": 8.0, "verbosity": "ERROR"}):
        yield


@pytest.fixture
def portrait() -> Iterator[None]:
    with tempconfig({"pixel_width": 90, "pixel_height": 160, "frame_width": 8.0, "frame_height": 128 / 9, "verbosity": "ERROR"}):
        yield


@pytest.fixture
def active(make_project) -> Project:
    project = Project.load(make_project())
    runtime.set_context(project)
    return project


def inside(inner: Region, outer: Region) -> bool:
    eps = 1e-9
    return inner.x0 >= outer.x0 - eps and inner.x1 <= outer.x1 + eps and inner.y0 >= outer.y0 - eps and inner.y1 <= outer.y1 + eps


# ----- regions -------------------------------------------------------------------------------------


def test_frame_and_safe_area(frame: str) -> None:
    full = frame_region()
    assert orientation() == frame
    assert min(full.width, full.height) == pytest.approx(8.0)
    safe = safe_area()
    assert (safe.x0, safe.y0) == pytest.approx((full.x0 + MARGIN_X, full.y0 + MARGIN_Y))
    assert (safe.x1, safe.y1) == pytest.approx((full.x1 - MARGIN_X, full.y1 - MARGIN_Y))
    assert safe.center == pytest.approx([0, 0, 0])
    assert safe_area(1.0, 2.0).width == pytest.approx(full.width - 2.0)


def test_named_regions_stay_inside_the_safe_area(frame: str) -> None:
    safe = safe_area()
    regions = {name: region(name) for name in REGION_NAMES}
    for name, r in regions.items():
        assert inside(r, safe), name
        assert r.width > 0 and r.height > 0, name
    assert regions["full"] == safe
    assert regions["header"].y1 == pytest.approx(safe.y1)
    assert regions["body"].y1 == pytest.approx(regions["header"].y0 - GAP)
    assert regions["body"].y0 == pytest.approx(safe.y0)
    assert regions["caption"].y0 == pytest.approx(safe.y0)
    assert regions["hero"].y1 == pytest.approx(regions["body"].y1)
    assert regions["hero"].y0 == pytest.approx(regions["caption"].y1 + GAP)
    assert regions["top"].y0 == pytest.approx(regions["bottom"].y1 + GAP)
    assert regions["center"].center == pytest.approx(safe.center)


def test_left_and_right_become_rows_in_portrait(frame: str) -> None:
    left, right = region("left"), region("right")
    assert left.width == pytest.approx(right.width) and left.height == pytest.approx(right.height)
    if frame == "portrait":
        assert (left, right) == (region("top"), region("bottom"))
        assert left.width == pytest.approx(safe_area().width)
    else:
        assert right.x0 == pytest.approx(left.x1 + GAP)
        assert left.height == pytest.approx(safe_area().height)


def test_region_on_another_area_and_unknown_name(landscape: None) -> None:
    area = Region(0, 0, 4, 2)
    assert region("full", area) == area
    assert region("left", area, gap=0) == Region(0, 0, 2, 2)
    with pytest.raises(VidgenError, match="unknown region 'middle'.*header"):
        region("middle")
    assert region("left", "body") == region("left", region("body"))  # area by name (Step 22)


def test_rows_columns_split_and_grid(landscape: None) -> None:
    area = Region(0, 0, 10, 4)
    cols = area.columns([1, 3], gap=2)
    assert cols == [Region(0, 0, 2, 4), Region(4, 0, 10, 4)]
    rows = area.rows(2, gap=0)
    assert rows == [Region(0, 2, 10, 4), Region(0, 0, 10, 2)]  # top to bottom
    assert area.split(2, gap=0) == area.columns(2, gap=0)
    cells = area.grid(2, 3, gap=0.5, gap_y=1.0)
    assert len(cells) == 6
    assert cells[0].x0 == 0 and cells[0].y1 == 4  # row-major, starting top left
    assert cells[1].x0 == pytest.approx(cells[0].x1 + 0.5)
    assert cells[3].y1 == pytest.approx(cells[0].y0 - 1.0)
    assert {round(c.width, 6) for c in cells} == {3.0} and {round(c.height, 6) for c in cells} == {1.5}
    assert grid(1, 2, "left") == region("left").columns(2)
    for bad in (0, [1, 0], []):
        with pytest.raises(VidgenError, match="positive weights"):
            area.columns(bad)
    with pytest.raises(VidgenError, match="at least 1 row"):
        area.grid(0, 2)


def test_split_follows_the_frame(portrait: None) -> None:
    area = Region(0, 0, 10, 4)  # wide region in a portrait frame: still rows
    assert area.split(2, gap=0) == area.rows(2, gap=0)


def test_region_helpers(landscape: None) -> None:
    r = Region(-2, -1, 2, 1)
    assert r.inset(0.5) == Region(-1.5, -0.5, 1.5, 0.5)
    assert r.inset(5, 0) == Region(0, -1, 0, 1)  # never negative
    assert r.point("top_left") == pytest.approx([-2, 1, 0])
    assert r.point(DL) == pytest.approx([-2, -1, 0])
    square = Square(side_length=1)
    assert r.below(square, gap=0.1) == Region(-2, -1, 2, -0.6)
    assert r.above(0.5) == Region(-2, 0.5, 2, 1)
    assert r.below(5) == r and r.below(-5).height == 0
    assert r.contains(square) and not r.contains(Square(side_length=3))
    outline = r.to_rectangle()
    assert isinstance(outline, Rectangle) and outline.width == pytest.approx(4)
    assert r.orientation == "landscape"
    with pytest.raises(VidgenError, match="negative size"):
        Region(1, 0, 0, 1)


# ----- place ---------------------------------------------------------------------------------------


def test_place_fits_and_aligns(landscape: None) -> None:
    box = Region(0, 0, 4, 2)
    m = place(Rectangle(width=1, height=1), box)  # contain: scaled up to the height
    assert (m.width, m.height) == pytest.approx((2, 2)) and m.get_center() == pytest.approx([2, 1, 0])
    m = place(Rectangle(width=8, height=1), box, fit="width", align="top_left")
    assert m.width == pytest.approx(4) and m.get_corner(np.array([-1, 1, 0])) == pytest.approx([0, 2, 0])
    m = place(Rectangle(width=1, height=1), box, fit="height", align=UR)
    assert m.height == pytest.approx(2) and m.get_corner(UR) == pytest.approx([4, 2, 0])
    m = place(Rectangle(width=1, height=1), box, fit="contain", max_scale=1.0, align="bottom")
    assert m.width == pytest.approx(1) and m.get_bottom() == pytest.approx([2, 0, 0])
    m = place(Rectangle(width=10, height=10), box, fit="none", buff=0.5, align="left")
    assert m.width == pytest.approx(10) and m.get_left()[0] == pytest.approx(0.5)


def test_place_by_name_and_errors(landscape: None) -> None:
    m = place(Rectangle(width=1, height=1), "header")
    assert region("header").contains(m) and m.height == pytest.approx(region("header").height)
    with pytest.raises(VidgenError, match="unknown alignment 'middle'"):
        place(Square(), "full", align="middle")
    with pytest.raises(VidgenError, match="unknown fit 'cover'"):
        place(Square(), "full", fit="cover")  # type: ignore[arg-type]


# ----- readable text --------------------------------------------------------------------------------


def cap_height(size: float) -> float:
    return float(Text("H", font="Inter", font_size=size).height)


def test_readable_size_matches_the_lint_threshold(frame: str, active: Project) -> None:
    size = readable_size()
    short = min(frame_region().width, frame_region().height)
    assert cap_height(size) / short == pytest.approx(0.025 * 1.05, rel=0.02)
    assert 18 < size < 24
    assert readable_size(fraction=0.05, margin=1.0) == pytest.approx(2 * readable_size(margin=1.0))


def test_readable_size_follows_the_project_lint_setting(make_project, landscape: None) -> None:
    project = Project.load(make_project(minimal_config(lint={"rules": {"min_font": {"min_size": 0.035}}})))
    runtime.set_context(project)
    assert readable_size(margin=1.0) == pytest.approx(readable_size(fraction=0.035, margin=1.0))
    runtime.clear_context()
    with pytest.raises(VidgenError, match="no active vidgen theme"):
        readable_size()
    assert readable_size("Inter") == pytest.approx(readable_size("Inter", fraction=0.025))


def test_readable_text_wraps_instead_of_shrinking(landscape: None, active: Project) -> None:
    text = "A rather long sentence that cannot fit on one line of a narrow region at a readable size"
    narrow = Region(0, 0, 3, 6)
    _, plain = fit_text_sized(text, narrow.width, 0.6, size=32, min_size=8)
    assert plain < readable_size()  # fit_text would shrink it this far
    block = readable_text(text, narrow, size=12)  # asks for less than readable: raised to the floor
    _, used = fit_text_sized(text, narrow.width, narrow.height, size=readable_size(), min_size=readable_size())
    assert used == pytest.approx(readable_size())
    assert len(block) > 3 and block.width <= narrow.width + 1e-6 and block.height <= narrow.height + 1e-6


def test_font_roles_in_text_helpers(landscape: None, make_project) -> None:
    """``role=`` picks the theme's family for a font role; ``font=`` still wins (Step 22)."""
    from vidgen.helpers import MT, T
    from vidgen.layout import fit_text

    project = Project.load(make_project(dict(minimal_config(), theme={"preset": "light_academic"})))
    with extensions.project_session(project) as theme:
        serif = theme.font_for("heading")
        assert serif == "Source Serif 4" != theme.font
        assert T("Hi", role="heading").font == serif and MT("Hi", role="heading").font == serif
        assert T("Hi").font == theme.font and T("Hi", role="heading", font="Inter").font == "Inter"
        assert fit_text("Hello world", 4, role="heading").lines_text.font == serif
        assert readable_text("Hello world", Region(0, 0, 4, 2), role="code") is not None


def test_readable_text_too_long_is_shrunk_with_a_warning(landscape: None, active: Project, caplog: pytest.LogCaptureFixture) -> None:
    tiny = Region(0, 0, 2, 0.5)
    with caplog.at_level(logging.WARNING, logger="vidgen.regions"):
        block = readable_text("far too many words for this tiny little box " * 3, tiny, min_size="body")
    assert block.height <= tiny.height + 1e-6
    assert "does not fit" in caplog.text and "readable size" in caplog.text


def test_readable_size_is_part_of_the_fingerprint(make_project) -> None:
    root = make_project()
    before = scene_fingerprint(Project.load(root), "intro")
    (root / "video.yaml").write_text(
        yaml.safe_dump(minimal_config(lint={"rules": {"min_font": {"min_size": 0.03}}})), encoding="utf-8"
    )
    assert scene_fingerprint(Project.load(root), "intro") != before


def test_scene_safe_area_is_what_the_layout_dump_records(make_project) -> None:
    from types import SimpleNamespace

    from vidgen.introspect import LayoutRecorder

    for w, h in ((160, 90), (90, 160)):
        fw, fh = frame_size(w, h)
        with tempconfig({"pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh}):
            fake = SimpleNamespace(safe_area=safe_area(0.6, 0.5), spec=SimpleNamespace(id="s", type="t"))
            doc = LayoutRecorder().document(fake, 1)  # type: ignore[arg-type]
            safe = safe_area()
            px = w / fw
            assert doc["safe_area"] == pytest.approx(
                [(safe.x0 + fw / 2) * px, (fh / 2 - safe.y1) * px, (safe.x1 + fw / 2) * px, (fh / 2 - safe.y0) * px], abs=0.06
            )


# ----- code wrapping -------------------------------------------------------------------------------


def test_wrap_code_keeps_short_lines_and_maps_groups() -> None:
    lines = ["def f(a, b):", "    return some_function(alpha, beta, gamma, delta)", "", "x = 1"]
    out, groups = wrap_code(lines, 24)
    assert out[0] == "def f(a, b):" and out[-1] == "x = 1"
    assert groups[0] == [0] and len(groups[1]) > 1 and groups[2] == [groups[1][-1] + 1]
    assert all(len(line) <= 24 for line in out)
    continuation = [out[j] for j in groups[1][1:]]
    assert all(line.startswith(" " * 8) for line in continuation)  # hanging indent: 4 + 4
    assert "".join(out[j].strip() for j in groups[1]).replace(" ", "") == lines[1].replace(" ", "")


def test_wrap_code_prefers_spaces_outside_strings_and_hard_cuts() -> None:
    out, _ = wrap_code(['print("a b c d e f g", value)'], 22)
    assert out[0] == 'print("a b c d e f g",'  # not inside the string literal
    out, _ = wrap_code(["x" * 50], 20)
    assert out == ["x" * 20, "    " + "x" * 16, "    " + "x" * 14]
    assert MIN_COLUMNS == 20


# ----- built-in scenes on regions (tiny renders, both orientations) ----------------------------------

CODE = (
    "def moving_average(values, window=3):\n"
    "    total = sum(values[:window])\n"
    "    for i in range(window, len(values)):\n"
    "        total += values[i] - values[i - window]\n"
    "    return total\n"
)


@pytest.fixture(scope="module")
def layout_project(tmp_path_factory: pytest.TempPathFactory) -> Project:
    root = tmp_path_factory.mktemp("regions")
    beats = [{"text": "one two"}, {"text": "three four"}]
    scenes = [
        {"id": "listing", "type": "code", "params": {"code": CODE, "title": "Moving average", "highlight": [1, "3-4"]}, "beats": beats},
        {"id": "nowrap", "type": "code", "params": {"code": CODE, "wrap": False}, "beats": beats},
        {"id": "list", "type": "bullets", "params": {"heading": "Steps", "items": ["Write the beats", "Pick scene types", "Render"]}, "beats": beats},
        {"id": "check", "type": "checklist", "params": {"items": ["Fewer parameters", "Same loss"]}, "beats": beats},
        {"id": "chart", "type": "bar_chart", "params": {"title": "Sizes", "labels": ["a", "b"], "values": [1, 2],
                                                        "caption": "Illustrative numbers"}, "beats": beats},
        {"id": "saying", "type": "quote", "params": {"text": "Simplicity is prerequisite for reliability.",
                                                     "author": "Edsger W. Dijkstra", "source": "1975"}, "beats": beats},
        {"id": "picture", "type": "image", "params": {"path": "assets/wide.png", "fit": "cover",
                                                      "caption": "Images can slowly zoom and pan"}, "beats": beats},
    ]
    (root / "assets").mkdir()
    from PIL import Image as PILImage

    PILImage.new("RGB", (64, 36), "#3366AA").save(root / "assets" / "wide.png")
    (root / "video.yaml").write_text(yaml.safe_dump(minimal_config(scenes=scenes), sort_keys=False), encoding="utf-8")
    # the example of docs/EXTENDING.md "Layout regions"
    (root / "extensions").mkdir()
    (root / "extensions" / "checklist.py").write_text(
        "from vidgen.api import *\n\n\n"
        "@scene(\"checklist\")\n"
        "class Checklist(NarratedScene):\n"
        "    outro = 0.5\n\n"
        "    class Params(SceneParams):\n"
        "        items: list[str] = Field(min_length=1)\n\n"
        "    def construct(self):\n"
        "        body = self.region(\"body\")\n"
        "        rows = VGroup(*[readable_text(f\"✓ {t}\", body, align=\"left\") for t in self.params.items])\n"
        "        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.3)\n"
        "        place(rows, body, fit=\"contain\", max_scale=1.0, align=\"top_left\")\n"
        "        self.reveal([FadeIn(r, shift=RIGHT * 0.2) for r in rows])\n"
        "        self.finish()\n",
        encoding="utf-8",
    )
    return Project.load(root)


def render_unfaded(project: Project, scene_id: str, media: Path, size: tuple[int, int]) -> Any:
    """Render a scene in-process without its final fade-out; returns the scene."""
    w, h = size
    fw, fh = frame_size(w, h)
    settings = {
        "pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "frame_rate": 5,
        "media_dir": str(media), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR",
        "output_file": f"{scene_id}_{w}x{h}",
    }
    with tempconfig(settings):
        spec = project.scene(scene_id)
        theme = extensions.activate(project)
        scene = registry.get(spec.type).cls(spec, project, theme)
        scene.finish = lambda: None
        scene.render()
        scene.layout_safe = scene.safe_area  # while the frame is still configured
        scene.readable = readable_size()
        scene.readable_mono = readable_size("JetBrains Mono NL")
        return scene


def find(scene: Any, class_name: str) -> Any:
    """The first mobject of that class on screen (searching inside groups)."""
    return next(m for top in scene.mobjects for m in top.get_family() if type(m).__name__ == class_name)


def code_font_size(scene: Any) -> float:
    """Font size the listing ends up at (points): cap height of its 'd' line vs Text."""
    listing = find(scene, "Code")
    first = listing.code_lines[0][0]  # the 'd' of def
    return float(first.height / Text("d", font="JetBrains Mono NL", font_size=48).height * 48)


@pytest.mark.render
@pytest.mark.parametrize("orient", ["landscape", "portrait"])
@pytest.mark.parametrize("scene_id", ["listing", "nowrap", "list", "check", "chart", "saying"])
@pytest.mark.slow
def test_scenes_stay_in_the_safe_area(layout_project: Project, tmp_path: Path, scene_id: str, orient: str) -> None:
    scene = render_unfaded(layout_project, scene_id, tmp_path, SIZES[orient])
    assert scene.mobjects
    for mob in scene.mobjects:
        assert scene.layout_safe.contains(mob, tolerance=0.02), (scene_id, orient, type(mob).__name__)


@pytest.mark.render
@pytest.mark.parametrize("orient", ["landscape", "portrait"])
def test_cover_image_caption_stays_in_the_safe_area(layout_project: Project, tmp_path: Path, orient: str) -> None:
    """The caption band of ``fit: cover`` reaches the frame edge, its text stays inside (Step 22)."""
    scene = render_unfaded(layout_project, "picture", tmp_path, SIZES[orient])
    caption = find(scene, "Paragraph")
    assert scene.layout_safe.contains(caption, tolerance=0.01)
    assert caption.get_bottom()[1] == pytest.approx(scene.layout_safe.y0, abs=0.01)


@pytest.mark.render
def test_quote_grows_in_a_vertical_frame(layout_project: Project, tmp_path: Path) -> None:
    wide = render_unfaded(layout_project, "saying", tmp_path, SIZES["landscape"])
    tall = render_unfaded(layout_project, "saying", tmp_path, SIZES["portrait"])

    def cap_height(scene: Any) -> float:  # of the 'S' of "Simplicity"
        return float(find(scene, "Paragraph")[0][0].height)

    assert cap_height(tall) > cap_height(wide) * 1.2


@pytest.mark.render
@pytest.mark.slow
def test_code_wraps_only_where_it_would_be_too_small(layout_project: Project, tmp_path: Path) -> None:
    n = len(CODE.rstrip("\n").split("\n"))
    wide = render_unfaded(layout_project, "listing", tmp_path, SIZES["landscape"])
    tall = render_unfaded(layout_project, "listing", tmp_path, SIZES["portrait"])
    shrunk = render_unfaded(layout_project, "nowrap", tmp_path, SIZES["portrait"])

    def listing(scene: Any) -> Any:
        return find(scene, "Code")

    assert len(listing(wide).code_lines) == n
    assert len(listing(tall).code_lines) > n and len(listing(shrunk).code_lines) == n
    # Step 32: below `caption` (24) to keep about 32 columns, never below the readable size
    assert tall.readable_mono * 0.97 <= code_font_size(tall) < 24 * 0.97
    assert code_font_size(shrunk) < shrunk.readable_mono  # what wrapping avoids
    # wrapped lines: one number per original line, highlights cover their continuation lines
    numbers = listing(tall).line_numbers
    labels = [line for line in numbers if len(line)]
    assert len(labels) == n
    bands = [m for m in tall.mobjects if type(m).__name__ == "VGroup" and len(m) and type(m[0]).__name__ == "RoundedRectangle"]
    assert bands, "highlight band of '3-4' expected"
    band = bands[-1][0]
    lines = listing(tall).code_lines
    covered = [i for i, line in enumerate(lines) if band.get_bottom()[1] < line.get_center()[1] < band.get_top()[1]]
    assert len(covered) > 2  # lines 3 and 4 plus at least one continuation


@pytest.mark.render
def test_bullets_use_the_taller_frame(layout_project: Project, tmp_path: Path) -> None:
    wide = render_unfaded(layout_project, "list", tmp_path, SIZES["landscape"])
    tall = render_unfaded(layout_project, "list", tmp_path, SIZES["portrait"])

    def heading_and_rows(scene: Any) -> tuple[Any, list[Any]]:
        heading = next(m for m in scene.mobjects if type(m).__name__ == "Paragraph")
        rows = [m for m in scene.mobjects if type(m).__name__ == "VGroup"]  # (marker, item) each
        assert len(rows) == 3
        return heading, rows

    def span(rows: list[Any]) -> float:
        return float(rows[0].get_top()[1] - rows[-1].get_bottom()[1])

    wh, wr = heading_and_rows(wide)
    th, tr = heading_and_rows(tall)
    assert th.height == pytest.approx(wh.height * 1.3, rel=0.05)  # portrait_growth
    assert tr[0][1].height > wr[0][1].height * 1.1  # items grew
    assert span(tr) > span(wr) * 1.3  # and spread out
    assert wide.region("header").contains(wh)
    assert th.get_bottom()[1] > tr[0].get_top()[1]


def test_regions_are_in_the_public_api() -> None:
    ns: dict[str, Any] = {}
    exec("from vidgen.api import *", ns)
    for name in ("Region", "frame_region", "safe_area", "region", "grid", "place", "orientation", "readable_size", "readable_text"):
        assert name in ns, name
