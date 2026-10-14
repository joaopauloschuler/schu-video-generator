"""Step 75: props on a stage (built-in props from primitives, SVG props, placement like characters).
Step 103: basket, umbrella (closed and open shapes) and napkin; grips. Step 110's furniture is in
``test_cartoon_furniture.py`` (each prop here builds, furniture included)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from test_cartoon_stage import render_with_layout, stage_params, stage_project
from vidgen.cartoon.vehicles import VEHICLE_KINDS
from vidgen.cartoon.props import (
    FURNITURE,
    PROP_COLORS,
    PROP_GRIPS,
    PROP_HEIGHTS,
    PROP_KINDS,
    PROP_LIFTS,
    PROP_SHAPES,
    SVG_PROP_HEIGHT,
    Prop,
    _DRAWERS,
    draw_prop,
    prop_colors,
    svg_prop,
)
from vidgen.cartoon.stage import StageItem, feet_point, stage_layout
from vidgen.cli import check_project
from vidgen.errors import VidgenError
from vidgen.lint.layout_rules import describe
from vidgen.theme import Theme
from vidgen.vector_mobject import VectorPicture

FW, FH = 8 * 16 / 9, 8.0
#: An SVG prop: a well (a stone ring with a roof), with a script the sanitiser removes.
WELL_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 120">
  <script>alert(1)</script>
  <polygon points="10,40 50,5 90,40" fill="#C0504D" stroke="#1F2430" stroke-width="3"/>
  <rect x="20" y="70" width="60" height="50" fill="#8A8F99" stroke="#1F2430" stroke-width="3"/>
</svg>
"""


def fills(prop: Prop) -> set[str]:
    return {m.get_fill_color().to_hex().upper() for m in prop.get_family() if len(m.points) and m.get_fill_opacity() > 0}


# ----- drawing (no render) ------------------------------------------------------------------------


def test_tables_cover_every_prop() -> None:
    assert len(PROP_KINDS) == 67 and len(set(PROP_KINDS)) == 67 and set(FURNITURE) <= set(PROP_KINDS)
    assert set(PROP_HEIGHTS) == set(PROP_COLORS) == set(_DRAWERS) | set(VEHICLE_KINDS) == set(PROP_KINDS)   # vehicles: Steps 118, 119; fireplace, kettle: Step 121; small props: Step 122
    assert set(PROP_LIFTS) <= set(PROP_KINDS) and set(PROP_SHAPES) <= set(PROP_KINDS)
    assert all(kind in PROP_KINDS and (shape is None or shape in PROP_SHAPES[kind]) for kind, shape in PROP_GRIPS)


def test_umbrella_shapes_swap_without_changing_its_family() -> None:
    """Step 103: closed and open shapes; the hidden one has no points (DESIGN.md §69.37)."""
    theme = Theme()
    umbrella = draw_prop("umbrella", height=2.0, theme=theme).shift([1.0, -1.0, 0.0])
    assert umbrella.shapes == ("closed", "open") and umbrella.shape == "closed" and umbrella.grip is None
    family = umbrella.get_family()
    closed_width, feet = umbrella.width, umbrella.feet()
    assert umbrella.grip_point() == pytest.approx(umbrella.get_center())   # held by its middle
    umbrella.show_shape("open")
    assert umbrella.get_family() == family and umbrella.shape == "open"   # only points change (§69.22)
    assert umbrella.height == pytest.approx(2.0, rel=0.02) and umbrella.width > 3 * closed_width
    assert umbrella.feet()[1] == pytest.approx(feet[1], abs=1e-6) and abs(umbrella.feet()[0] - feet[0]) < 0.05
    assert umbrella.grip_point()[:2] == pytest.approx([1.0, -1.0 + 0.16 * umbrella.height], abs=0.03)   # the shaft above the hook
    assert umbrella.shape_width("open") == pytest.approx(umbrella.width) and umbrella.shape_width("closed") == pytest.approx(closed_width)
    opened = draw_prop("umbrella", height=2.0, theme=theme, shape="open")
    assert np.allclose(opened.shift([1.0, -1.0, 0.0]).get_all_points(), umbrella.get_all_points(), atol=2e-3)   # drawn open = opened (both shapes 1 prop unit tall)
    umbrella.show_shape("closed")
    assert umbrella.width == pytest.approx(closed_width)
    assert fills(umbrella) == fills(draw_prop("umbrella", height=2.0, theme=theme))
    with pytest.raises(VidgenError, match="no shape 'folded'"):
        umbrella.show_shape("folded")
    with pytest.raises(VidgenError, match="no shape 'open'"):
        draw_prop("tree", height=1.0, theme=theme, shape="open")


def test_grips_follow_size_and_facing() -> None:
    basket = draw_prop("basket", height=1.0, theme=Theme())
    assert basket.shapes == () and basket.grip == PROP_GRIPS[("basket", None)]
    assert basket.grip_point()[:2] == pytest.approx(basket.get_top()[:2], abs=0.02)   # by the top of its handle
    left = draw_prop("umbrella", height=1.0, theme=Theme(), shape="open", facing="left")
    right = draw_prop("umbrella", height=1.0, theme=Theme(), shape="open")
    assert left.grip_point()[0] == pytest.approx(-right.grip_point()[0]) and left.grip_point()[1] == pytest.approx(right.grip_point()[1])
    width = right.width
    copy = right.copy().scale(2.0, about_point=right.feet())
    assert copy.grip_point()[1] == pytest.approx(2 * right.grip_point()[1])   # the anchor scales with it
    copy.show_shape("closed")
    assert right.shape == "open" and right.width == pytest.approx(width)   # a copy's shapes are its own


@pytest.mark.parametrize("kind", PROP_KINDS)
def test_each_prop_builds(kind: str) -> None:
    theme = Theme()
    prop = draw_prop(kind, height=2.0, theme=theme)
    assert isinstance(prop, Prop) and prop.kind == kind and prop.name == kind
    assert prop.height == pytest.approx(2.0) and prop.feet() == pytest.approx([0.0, 0.0, 0.0], abs=1e-9)
    assert theme.color(PROP_COLORS[kind][0]).upper() in fills(prop)   # the main colour is used
    assert all(m.get_stroke_width() >= 1 for m in prop.get_family() if len(m.points) and m.get_stroke_width() > 0)
    again = draw_prop(kind, height=2.0, theme=theme)
    assert np.allclose(prop.get_all_points(), again.get_all_points())   # the same every time


def test_colours_facing_and_strokes() -> None:
    theme = Theme()
    assert prop_colors("tree", theme) == (theme.color("tertiary"), theme.color("secondary"))
    assert prop_colors("tree", theme, "#123456", "accent") == ("#123456", theme.color("accent"))
    red = draw_prop("ball", height=1.0, theme=theme, main="#AA0000", detail="primary")
    assert {"#AA0000", theme.color("primary").upper()} <= fills(red)
    right = draw_prop("chair", height=2.0, theme=theme)
    left = draw_prop("chair", height=2.0, theme=theme, facing="left", name="seat")
    assert left.name == "seat" and left.facing == "left"
    assert np.allclose(left.get_all_points()[:, 0], -right.get_all_points()[:, 0])   # mirrored about the feet
    thin = draw_prop("cup", height=0.3, theme=theme, character_height=3.0)
    thick = draw_prop("cup", height=0.3, theme=theme, character_height=6.0)
    assert max(m.get_stroke_width() for m in thick.get_family()) == pytest.approx(2 * max(m.get_stroke_width() for m in thin.get_family()))
    with pytest.raises(VidgenError, match="unknown prop 'piano'"):
        draw_prop("piano", height=1.0, theme=theme)
    with pytest.raises(VidgenError, match="facing"):
        draw_prop("box", height=1.0, theme=theme, facing="up")


def test_svg_prop_is_sanitised_and_stands_on_its_box(tmp_path: Path) -> None:
    path = tmp_path / "well.svg"
    path.write_text(WELL_SVG, encoding="utf-8")
    prop = svg_prop(path, height=2.4, name="well", facing="left")
    (picture,) = prop.submobjects
    assert isinstance(picture, VectorPicture) and prop.kind == "svg" and prop.name == "well"
    assert b"script" not in picture.report.data and any("scripts" in w for w in picture.report.warnings)
    assert prop.height == pytest.approx(2.4) and prop.feet() == pytest.approx([0.0, 0.0, 0.0], abs=1e-9)


# ----- stage params and layout (no render) --------------------------------------------------------


def test_params_names_lift_and_targets() -> None:
    params = stage_params(
        characters=["pip"],
        props=["tree", {"prop": "tree", "at": "right", "depth": 0.5}, {"prop": "sun", "at": 0.8},
               {"svg": "assets/Old well.svg", "at": "left", "scale": 2}, {"prop": "table", "name": "desk", "lift": 0.1}],
    )
    assert params.prop_names() == ["tree", "tree_2", "sun", "Old_well", "desk"]
    items = params.items()
    assert [i.kind for i in items] == ["prop"] * 5 + ["character"]   # props first: a character at the same depth is in front
    tree, _, sun, well, desk = items[:5]
    assert tree.scale == PROP_HEIGHTS["tree"] and well.scale == 2 * SVG_PROP_HEIGHT
    assert (tree.lift, sun.lift, desk.lift) == (0.0, PROP_LIFTS["sun"], 0.1)
    from vidgen import registry

    assert registry.get("stage").cls.target_names(params) == ["pip", "tree", "tree_2", "sun", "Old_well", "desk"]
    assert registry.get("stage").cls.target_patterns == ("<character>", "<prop>", "<character>.<part>")


@pytest.mark.parametrize(
    "props,message",
    [
        (["piano"], "props.0"),
        ([{"prop": "tree", "svg": "assets/a.svg"}], "one of the two"),
        ([{"at": "left"}], "one of the two"),
        ([{"svg": "assets/a.png"}], "not an .svg file"),
        ([{"svg": "assets/a.svg", "color": "accent"}], "color and detail are for built-in props"),
        ([{"prop": "tree", "recolor": "theme"}], "recolor is for svg props"),
        (["box", "box", {"prop": "ball", "name": "box"}], "prop name 'box' is used twice \\(props\\[2\\]\\)"),
        ([{"prop": "ball", "name": "pip"}], "props\\[0\\]: 'pip' is also a character"),
        ([{"prop": "rock", "at": "middle"}], "props\\[0\\].at: unknown mark 'middle'"),
        ([{"prop": "rock", "lift": 2}], "less than or equal to 1"),
        ([{"prop": "tree", "open": True}], "open is for props that open \\(door, umbrella, book, letter, gift\\), not tree"),
    ],
)
def test_bad_props(props: list[Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        stage_params(characters=["pip"], props=props)


def test_layout_sorts_props_with_characters_and_lifts_them() -> None:
    items = [StageItem("tree", "prop", "left", 0.6, 1.7), StageItem("sun", "prop", 0.8, 0.0, 0.4, 0.5), StageItem("pip", "character", "left")]
    placed = stage_layout(items, ground=0.2, size=0.45, frame_width=FW, frame_height=FH)
    assert [p.name for p in placed] == ["tree", "sun", "pip"] and placed[0].kind == "prop"
    sun = placed[1]
    assert sun.feet == pytest.approx(feet_point(0.8, 0.0, 0.7, FW, FH))   # 0.5 of the frame height above the ground line
    assert sun.height == pytest.approx(0.45 * FH * 0.4)


def test_validate_reports_a_missing_svg_prop(make_project) -> None:
    project = stage_project(make_project, {"characters": ["pip"], "props": [{"svg": "assets/well.svg"}, "tree"]})
    assert check_project(project) == ["scenes[0].params.props[0].svg: file not found: assets/well.svg (looked for " + str(project.root / "assets" / "well.svg") + ")"]
    (project.root / "assets").mkdir()
    (project.root / "assets" / "well.svg").write_text(WELL_SVG, encoding="utf-8")
    assert check_project(project) == []


def test_lint_names_props() -> None:
    assert describe({"kind": "prop", "class": "Prop", "name": "tree", "path": "tree"}) == "prop 'tree'"


# ----- render ------------------------------------------------------------------------------------


@pytest.mark.render
def test_stage_renders_props(make_project, tmp_path: Path) -> None:
    params = {
        "idle": False,
        "characters": [{"name": "pip", "at": "left"}],
        "props": [{"prop": "tree", "at": "right", "depth": 0.6}, {"prop": "table", "at": "left"}, "sun",
                  {"svg": "assets/well.svg", "at": 0.9, "recolor": "theme"}],
    }
    project = stage_project(make_project, params)
    (project.root / "assets").mkdir()
    (project.root / "assets" / "well.svg").write_text(WELL_SVG, encoding="utf-8")
    scene, objects = render_with_layout(project, "park", tmp_path / "media")
    assert list(scene.props) == ["tree", "table", "sun", "well"] and list(scene.cast) == ["pip"]
    table = scene.props["table"]
    assert table.feet()[:2] == pytest.approx(feet_point(0.25, 0.0, 0.2, scene.frame_width, scene.frame_height), abs=1e-6)
    assert table.height == pytest.approx(PROP_HEIGHTS["table"] * scene.cast["pip"].height, rel=0.02)
    assert scene.props["sun"].feet()[1] > scene.cast["pip"].get_top()[1]   # the sun hangs in the sky
    named = {obj["name"]: obj for obj in objects if obj["name"]}
    assert [named[n]["kind"] for n in ("tree", "sun", "table", "well", "pip")] == ["prop"] * 4 + ["character"]
    assert named["tree"]["order"] < named["table"]["order"] < named["pip"]["order"]   # back to front; a character in front of a prop
    assert named["ground"]["bbox"][1] <= named["tree"]["bbox"][3] + 0.5   # the band reaches up to the tree at depth 0.6


@pytest.mark.render
def test_prop_gallery_still(tmp_path: Path) -> None:
    from PIL import Image

    from vidgen.cartoon.still import write_props_png

    path = write_props_png(Theme(), tmp_path / "docs" / "props.png", width=192, height=108)
    with Image.open(path) as image:
        assert image.size == (192, 108) and image.mode == "P"
