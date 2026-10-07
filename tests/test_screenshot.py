"""Step 34: callout helpers (``vidgen.api``: areas, label placement, box, circle, arrow, magnifier,
spotlight, labels) and the ``screenshot`` scene type (frames, steps of callouts, previous
fade / dim / keep, focus, targets)."""

from __future__ import annotations

import re
from pathlib import Path
from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest
from manim import Arrow, CurvedArrow, Ellipse, ImageMobject, RoundedRectangle, Square, tempconfig
from PIL import Image
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import beat_total, beats, render
from test_builtin_scenes import cls_of
from test_schema import errors
from vidgen import api, registry, runtime, schema
from vidgen.callouts import _crop, connector_lines, tag_spot
from vidgen.lint.color import contrast_ratio, hex_rgb
from vidgen.cli import check_project
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.regions import Region, frame_region, readable_size, safe_area
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
STEPS = [
    {"box": [0.1, 0.1, 0.3, 0.2], "label": "Search"},
    [{"arrow": [0.8, 0.2], "label": "New"}, {"circle": [0.6, 0.6, 0.2, 0.2]}],
    {"callouts": [{"magnifier": [0.1, 0.6, 0.2, 0.2], "label": "Zoom"}, {"spotlight": [0.1, 0.6, 0.2, 0.2]}], "previous": "keep"},
]


def quadrants(size: tuple[int, int] = (80, 50)) -> np.ndarray:
    """An RGBA picture: red top left, green top right, blue bottom left, white bottom right."""
    w, h = size
    px = np.zeros((h, w, 4), dtype=np.uint8)
    px[..., 3] = 255
    px[: h // 2, : w // 2, 0] = 255
    px[: h // 2, w // 2 :, 1] = 255
    px[h // 2 :, : w // 2, 2] = 255
    px[h // 2 :, w // 2 :, :3] = 255
    return px


def picture(width: float = 8.0) -> ImageMobject:
    img = ImageMobject(quadrants())
    img.stretch_to_fit_width(width).stretch_to_fit_height(width * 5 / 8).move_to([0, 0, 0])
    return img


def load(make_project, scenes: list[dict[str, Any]]) -> Project:
    root = make_project(minimal_config(scenes=scenes, narration=NARRATION))
    (root / "assets").mkdir(exist_ok=True)
    Image.fromarray(quadrants((160, 100))).save(root / "assets" / "app.png")
    return Project.load(root)


def shot(steps: list[Any], n_beats: int | None = None, **params: Any) -> dict[str, Any]:
    return {"id": "s", "type": "screenshot", "params": {"path": "assets/app.png", "steps": steps, **params},
            "beats": beats(*([None] * (n_beats if n_beats is not None else len(steps))))}


def params(**changes: Any) -> Any:
    return cls_of("screenshot").validate_params({"path": "assets/app.png", "steps": STEPS, **changes}, Theme())


@pytest.fixture
def ctx(make_project) -> Iterator[None]:
    """A project context (theme) for building callouts outside a scene."""
    runtime.set_context(Project.load(make_project()))
    yield
    runtime.clear_context()


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- areas and placement ------------------------------------------------------------------------


def test_callout_area_fractions_pixels_points_and_mobjects() -> None:
    img = picture()                                                     # 8 x 5 units, 80 x 50 px, centred
    r = api.callout_area([0.25, 0.2, 0.5, 0.4], img)
    assert (r.x0, r.x1, r.y1, r.y0) == pytest.approx((-2, 2, 1.5, -0.5))   # y from the top
    assert api.callout_area([20, 10, 40, 20], img, units="px") == r
    point = api.callout_area([0.5, 0.5], img)
    assert point.width == point.height == 0 and point.center == pytest.approx([0, 0, 0])
    sq = Square(side_length=2).shift([1, 1, 0])
    assert api.callout_area(sq) == Region(0, 0, 2, 2)
    assert api.callout_area(Region(0, 0, 1, 1)) is not None
    whole = api.callout_area([0, 0, 1, 1])                              # default: the frame
    assert whole == frame_region()
    assert api.callout_area([10, 10], Region(0, 0, 4, 2), units="px", pixels=(40, 20)).center == pytest.approx([1, 1, 0])


@pytest.mark.parametrize(
    ("area", "kwargs", "message"),
    [([1, 2, 3], {}, r"\[x, y\] or \[x, y, w, h\]"),
     ([0, 0, 1, 1], {"units": "px"}, "need an image"),
     ([0, 0, 1, 1], {"units": "cm"}, "unknown units"),
     ([0, 0, -1, 1], {}, "positive width")],
)
def test_callout_area_errors(area: list[float], kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        api.callout_area(area, **kwargs)


def test_label_spot_stays_inside_off_the_anchor_and_clear_of_avoid(ctx: None) -> None:
    bounds = safe_area()
    anchor = Region(5.5, 3.0, 6.0, 3.3)                                 # near the top-right corner
    spot = api.label_spot((2.0, 0.5), anchor, bounds=bounds)
    assert bounds.x0 - 1e-6 <= spot.x0 and spot.x1 <= bounds.x1 + 1e-6 and bounds.y0 - 1e-6 <= spot.y0 and spot.y1 <= bounds.y1 + 1e-6
    assert not (spot.x0 < anchor.x1 and anchor.x0 < spot.x1 and spot.y0 < anchor.y1 and anchor.y0 < spot.y1)
    free = api.label_spot((1.0, 0.4), Region(0, 0, 0.2, 0.2), bounds=bounds)
    blocked = api.label_spot((1.0, 0.4), Region(0, 0, 0.2, 0.2), bounds=bounds, avoid=[free.inset(-0.05)])
    assert blocked != free
    below = api.label_spot((1.0, 0.4), Region(0, 0, 0.2, 0.2), bounds=bounds, side="bottom")
    assert below.y1 < 0
    near = api.label_spot((1.0, 0.4), Region(0, 0, 0.2, 0.2), bounds=bounds)
    gap = max(near.x0 - 0.2, -near.x1, near.y0 - 0.2, -near.y1)
    assert gap >= 0.5                                                   # an arrow has some length


def test_tag_sits_on_the_edge_of_its_mark(ctx: None) -> None:
    mark = Region(-1, -0.5, 1, 0.5)
    spot = tag_spot((0.8, 0.3), mark, bounds=safe_area())
    assert spot.y0 == pytest.approx(0.58) and spot.x0 == pytest.approx(-1)   # above, at its left end
    top = safe_area().y1
    high = tag_spot((0.8, 0.3), Region(-1, top - 1, 1, top), bounds=safe_area())
    assert high.y1 <= top - 1 + 1e-6 or high.y1 <= top                  # no room above: below or inside


def test_connector_lines_run_along_the_outside() -> None:
    lines = connector_lines(Region(0, 0, 1, 1), Region(3, 3, 5, 5))        # diagonal: TL-TL and BR-BR
    ends = sorted((tuple(np.round(a[:2], 3)), tuple(np.round(b[:2], 3))) for a, b in lines)
    assert len(lines) == 2
    assert {tuple(sorted(e)) for e in ends} == {((0.0, 1.0), (3.0, 5.0)), ((1.0, 0.0), (5.0, 3.0))}
    assert len(connector_lines(Region(0, 0, 1, 1), Region(3, 0, 4, 1))) == 2   # side by side: top and bottom
    assert connector_lines(Region(0, 0, 4, 4), Region(1, 1, 2, 2)) == []       # one inside the other


# ----- the helpers ------------------------------------------------------------------------------------


def test_label_is_readable_on_its_plate(ctx: None) -> None:
    theme = Theme()
    for color in ("highlight", "accent", "primary", "#202020"):
        label = api.callout_label("A label", color=color, theme=theme)
        ink = label.text.family_members_with_points()[0].get_fill_color().to_hex()
        plate = label.plate.get_fill_color().to_hex()
        assert contrast_ratio(hex_rgb(ink), hex_rgb(plate)) >= 4.5, color
        assert label.plate.width > label.text.width and label.plate.height > label.text.height
    small = api.callout_label("A label", size=8, theme=theme)
    big = api.callout_label("A label", theme=theme)
    assert small.text.height == pytest.approx(api.callout_label("A label", size=readable_size(), theme=theme).text.height, rel=0.06)
    assert api.callout_label("A label", scale=0.5, theme=theme).height == pytest.approx(big.height / 2)


def test_box_circle_arrow_and_spotlight_shapes(ctx: None) -> None:
    img = picture()
    box = api.callout_box([0.25, 0.2, 0.5, 0.4], "Box", within=img)
    assert box.kind == "box" and isinstance(box.mark, RoundedRectangle) and box.tag is not None
    assert box.mark.width == pytest.approx(4 + 2 * 0.08)
    ring = api.callout_circle([0.5, 0.5], within=img)
    assert isinstance(ring.mark, Ellipse) and ring.tag is None and ring.mark.width == pytest.approx(0.6)
    oval = api.callout_circle([0.25, 0.2, 0.5, 0.4], within=img)
    assert oval.mark.width > 4 * 1.4 and oval.mark.height > 2 * 1.4      # through the area's corners
    arrow = api.callout_arrow([0.5, 0.5], "Here", within=img)
    assert isinstance(arrow.mark, Arrow)
    assert np.linalg.norm(arrow.mark.get_end() - np.array([0, 0, 0])) < 0.1   # the tip at the point
    curved = api.callout_arrow([0.5, 0.5], "Here", within=img, curved=True)
    assert isinstance(curved.mark, CurvedArrow)
    spot = api.callout_spotlight([0.25, 0.2, 0.5, 0.4], within=img)
    assert spot.mark.width == pytest.approx(img.width)                   # covers the picture only
    assert spot.extent().width < img.width
    assert [type(a).__name__ for a in arrow.draw()] == ["FadeIn", "GrowArrow"]   # label first
    assert [type(a).__name__ for a in box.draw()] == ["Create", "FadeIn"]
    assert api.callout("box", [0.1, 0.1, 0.2, 0.2], within=img).kind == "box"
    with pytest.raises(VidgenError, match="unknown callout kind"):
        api.callout("star", [0, 0])


def test_magnifier_crops_the_picture_sharply(ctx: None) -> None:
    img = picture()
    with tempconfig({"pixel_width": 1920, "pixel_height": 1080}):
        mag = api.callout_magnifier([0.0, 0.0, 0.25, 0.25], "Zoom", image=img, zoom=2.0, bounds=frame_region())
    inset = next(m for m in mag.mark.get_family() if isinstance(m, ImageMobject))
    assert inset.width == pytest.approx(4.0) and inset.height == pytest.approx(2.5)   # 2 x (2 x 1.25)
    px = inset.pixel_array
    assert px.shape[1] == pytest.approx(4.0 * 1920 / 14.222, abs=2)     # output resolution, not 20 source px
    assert np.abs(px[px.shape[0] // 2, px.shape[1] // 2, :3].astype(int) - [255, 0, 0]).max() <= 3   # the red quadrant
    lines = mag.mark.submobjects[1]
    assert len(lines.submobjects) == 2
    region = api.callout_area([0.0, 0.0, 0.25, 0.25], img)
    box = mag.extent(0)
    assert box.x0 >= -7.12 and box.x1 <= 7.12
    assert not (inset.get_left()[0] < region.x1 and region.x0 < inset.get_right()[0]
                and inset.get_bottom()[1] < region.y1 and region.y0 < inset.get_top()[1])   # off its area
    sharp = _crop(quadrants(), (0.0, 0.0, 0.5, 0.5), (8, 6))
    assert sharp.shape == (6, 8, 4) and np.abs(sharp[3, 4, :3].astype(int) - [255, 0, 0]).max() <= 3
    with pytest.raises(VidgenError, match="width and a height"):
        api.callout_magnifier([0.5, 0.5], image=img)


def test_scale_builds_for_a_zoomed_camera(ctx: None) -> None:
    img = picture()
    full = api.callout_box([0.25, 0.2, 0.5, 0.4], "Box", within=img)
    half = api.callout_box([0.25, 0.2, 0.5, 0.4], "Box", within=img, scale=0.5)
    assert half.tag.height == pytest.approx(full.tag.height / 2)
    assert half.mark.get_stroke_width() == pytest.approx(full.mark.get_stroke_width() / 2)


def test_api_exports_the_callout_helpers() -> None:
    for name in ("callout", "callout_area", "callout_arrow", "callout_box", "callout_circle", "callout_label",
                 "callout_magnifier", "callout_spotlight", "label_spot", "Callout", "CalloutArea", "CALLOUT_KINDS"):
        assert name in api.__all__ and name in api.VIDGEN_NAMES


# ----- params -------------------------------------------------------------------------------------------


def test_params_forms_of_steps_and_callouts() -> None:
    p = params()
    assert [len(s.callouts) for s in p.steps] == [1, 2, 2]
    assert p.steps[0].callouts[0].kind == "box" and p.steps[0].callouts[0].area == [0.1, 0.1, 0.3, 0.2]
    assert p.steps[1].callouts[0].kind == "arrow" and p.steps[2].previous == "keep"
    canonical = params(steps=[{"kind": "circle", "area": [0.5, 0.5], "label": "x"}])
    assert canonical.steps[0].callouts[0].kind == "circle"


@pytest.mark.parametrize(
    ("steps", "changes", "message"),
    [([{"box": [0.1, 0.1, 0.3]}], {}, r"area is \[x, y, w, h\] or \[x, y\]"),
     ([{"magnifier": [0.1, 0.1]}], {}, "magnifier needs an area with a size"),
     ([{"box": [0.1, 0.1, 0.2, 0.2], "curved": True}], {}, "only arrows can be curved"),
     ([{"box": [0.1, 0.1, 0.2, 0.2], "zoom": 3}], {}, "only for a magnifier"),
     ([{"box": [0.9, 0.1, 0.2, 0.2]}], {}, "not inside the image"),
     ([{"box": [0.1, 0.1, 0, 0.2]}], {}, "more than 0"),
     ([{"callouts": [], "focus": 9}], {}, "focus magnification"),
     ([{"star": [0.1, 0.1]}], {}, "star"),
     ([], {"frame": "tablet"}, "frame")],
)
def test_params_errors(steps: list[Any], changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        params(steps=steps, **changes)


def test_pixel_areas_are_checked_against_the_image(make_project) -> None:
    project = load(make_project, [shot([{"box": [100, 10, 80, 20]}], units="px")])  # the picture is 160 x 100
    problems = check_project(project)
    assert any("is not inside the image (160 x 100 px)" in p for p in problems)
    assert check_project(load(make_project, [shot([{"box": [10, 10, 80, 20]}], units="px")])) == []


def test_target_names() -> None:
    cls = cls_of("screenshot")
    assert cls.target_names(params(title="T")) == ["title", "image", "callout1", "callout:Search", "callout2", "callout:New",
                                                    "callout3", "callout4", "callout:Zoom", "callout5", "step1", "step2", "step3"]
    assert cls.target_names(params(steps=[[], {"box": [0, 0, 0.1, 0.1]}])) == ["image", "callout1", "step2"]


def test_json_schema_accepts_every_form() -> None:
    doc = schema.params_schema(registry.get("screenshot"), [Theme()])
    assert errors(doc, {"path": "a.png", "steps": STEPS + [{"kind": "box", "area": [0, 0, 1, 1]}, []]}) == []
    assert errors(doc, {"path": "a.png", "steps": [{"box": [0, 0, 1, 1], "colour": "red"}]}) != []
    assert errors(doc, {"path": "a.png", "steps": [{"kind": "star", "area": [0, 0]}]}) != []


# ----- rendering ---------------------------------------------------------------------------------------------


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
@pytest.mark.parametrize("frame", ["none", "browser", "window", "phone"])
@pytest.mark.slow
def test_renders_in_every_frame_and_orientation(make_project, media: Path, size: tuple[int, int], frame: str) -> None:
    project = load(make_project, [shot(STEPS, title="A screenshot", frame=frame, url="example.org/page")])
    scene = render(project, "s", media, size)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    registered = sorted({n for t in scene.targets for n in t.names})
    assert registered == sorted(type(scene).target_names(scene.params))
    body = scene._body                                                  # (the frame of the render; Manim's config is restored)
    for k, made in enumerate(scene._callouts):
        for m in made:
            if m.tag is not None:   # labels inside the safe area, below the title
                tag = api.callout_area(m.tag)
                assert body.x0 - 0.01 <= tag.x0 and tag.x1 <= body.x1 + 0.01 and body.y0 - 0.01 <= tag.y0 and tag.y1 <= body.y1 + 0.01
    picture_box = api.callout_area(scene._picture)
    assert body.x0 - 1e-6 <= picture_box.x0 and picture_box.x1 <= body.x1 + 1e-6


@pytest.mark.render
@pytest.mark.parametrize(("previous", "shown", "faint"), [("fade", False, False), ("dim", True, True), ("keep", True, False)])
def test_previous_callouts_fade_dim_or_stay(make_project, media: Path, previous: str, shown: bool, faint: bool) -> None:
    project = load(make_project, [shot([{"box": [0.1, 0.1, 0.3, 0.2], "label": "A"}, {"circle": [0.6, 0.6, 0.2, 0.2]}], previous=previous)])
    scene = render(project, "s", media)
    first = scene.find_targets("callout1")[0].mobject
    assert bool(scene.on_screen_parts(first.mark)) == shown
    if faint:
        assert first.mark.get_stroke_opacity() == pytest.approx(0.35)
        assert not scene.on_screen_parts(first.tag)                     # labels go
    assert scene.is_shown("callout2")


@pytest.mark.render
def test_focus_moves_the_camera_in_and_back(make_project, media: Path) -> None:
    steps = [{"callouts": [{"arrow": [0.3, 0.3], "label": "Here"}], "focus": True}, {"box": [0.6, 0.6, 0.2, 0.2]}]
    project = load(make_project, [shot(steps, previous="keep")])
    scene = render(project, "s", media, (320, 180))
    moves = [p for p in scene.play_log if "MoveCamera" in p.animations]
    assert [p.beat for p in moves] == ["s_b1", "s_b2"]
    assert scene.camera.frame.width == pytest.approx(scene.frame_width)
    focused = scene.find_targets("callout1")[0].mobject
    assert focused.tag.height < api.callout_label("Here").height * 0.75     # built for the zoom
    assert not scene.is_shown("callout1")                               # built for another camera: it left


@pytest.mark.render
def test_landscape_picture_focuses_by_itself_in_a_vertical_frame(make_project, media: Path) -> None:
    """Step 57: a 16:10 screenshot in 9:16 was a thin strip; its callout steps now zoom in (the
    view centred on the picture vertically, kept on it sideways); not in 16:9, not with
    ``focus: false``."""
    steps = [{"box": [0.1, 0.1, 0.3, 0.2], "label": "Search"}, {"arrow": [0.9, 0.2], "label": "New"}]
    portrait = render(load(make_project, [shot(steps)]), "s", media, (90, 160))
    assert all(cam is not None for cam in portrait._cameras)
    pic = api.callout_area(portrait._picture)
    for width, (x, y) in portrait._cameras:
        height = width * 160 / 90                       # the frame's aspect (Manim's config is restored)
        assert height > pic.height and y == pytest.approx(pic.center[1])           # even bands
        assert pic.x0 - 1e-6 <= x - width / 2 and x + width / 2 <= pic.x1 + 1e-6    # on the picture
    landscape = render(load(make_project, [shot(steps)]), "s", media, (160, 90))
    assert landscape._cameras == [None, None]
    kept = render(load(make_project, [shot([{"callouts": steps[:1], "focus": False}])]), "s", media, (90, 160))
    assert kept._cameras == [None]


@pytest.mark.render
def test_early_reveal_and_actions(make_project, media: Path) -> None:
    project = load(make_project, [{**shot(STEPS), "beats": beats([{"reveal": "step2"}], [{"zoom": "callout:Search"}], [{"dim": "image"}])}])
    scene = render(project, "s", media)
    names = [p.animations for p in scene.play_log if p.beat == "s_b2" and not p.wait]
    assert all("Create" not in n and "GrowArrow" not in n for n in names)   # step 2 was on screen already
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)


@pytest.mark.render
def test_silent_scene_and_no_steps(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": "screenshot", "params": {"path": "assets/app.png", "steps": STEPS}, "duration": 2.0},
                                  {"id": "p", "type": "screenshot", "params": {"path": "assets/app.png", "frame": "phone"}, "beats": beats(None, None)}])
    scene = render(project, "s", media)
    assert all(scene.is_shown(f"callout{n}") for n in (4, 5))
    plain = render(project, "p", media, (90, 160))
    assert plain.is_shown("image") and float(plain.renderer.time) == pytest.approx(beat_total(plain), abs=1.5 / FPS)


@pytest.mark.render
def test_missing_image_is_a_clear_error(make_project, media: Path) -> None:
    project = load(make_project, [shot([], 1)])
    (project.root / "assets" / "app.png").unlink()
    with pytest.raises(VidgenError, match="scene 's': path: file not found"):
        render(project, "s", media)


@pytest.mark.render
def test_extending_callouts_example_renders(make_project, media: Path) -> None:
    text = (Path(__file__).resolve().parents[1] / "docs" / "EXTENDING.md").read_text(encoding="utf-8")
    code = re.search(r"\*\*Callouts\.\*\*.*?```python\n(.*?)```", text, re.S).group(1)
    root = make_project(minimal_config(scenes=[{"id": "a", "type": "annotated", "beats": beats(None, None, None)}], narration=NARRATION))
    (root / "extensions").mkdir(exist_ok=True)
    (root / "extensions" / "annotated.py").write_text("from vidgen.api import *\n\n\n" + code, encoding="utf-8")
    scene = render(Project.load(root), "a", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert len([m for m in scene.mobjects if isinstance(m, Arrow)]) == 1
