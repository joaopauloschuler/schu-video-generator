"""Portals (a rift that opens, crackles and seals) and hologram characters (DESIGN.md §100.3,
§100.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from manim import ManimColor
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST, stage_params
from vidgen.cartoon import portal
from vidgen.cartoon.character import build_character
from vidgen.cartoon.hologram import (
    DARK_SHARE,
    HOLOGRAM_COLOR,
    apply_hologram,
    hologram_edge,
    hologram_fill,
    is_hologram,
    lightness,
)
from vidgen.cartoon.living import GLOWS, LIVING_KINDS, SWITCHED_PROPS
from vidgen.cartoon.living_drawing import PORTAL_PARTS, LivingProp, living_parts
from vidgen.cartoon.props import FLOATING_IN_PLACE, PROP_KINDS, SCIFI_PROPS, draw_prop
from vidgen.cartoon.shading import LIT, mark_lit
from vidgen.cli import check_project
from vidgen.config import CharacterEntry, HologramConfig
from vidgen.project import Project
from vidgen.theme import Theme

# ----- the portal's maths (no manim) --------------------------------------------------------------


def test_openness_opens_seals_and_turns_back() -> None:
    o = portal.openness
    assert o(False, [], 5.0) == 0.0 and o(True, [], 0.0) == 1.0
    opening = [(1.0, True)]
    assert o(False, opening, 1.0) == 0.0
    assert o(False, opening, 1.0 + portal.OPEN_SECONDS / 2) == pytest.approx(0.5)
    assert o(False, opening, 1.0 + portal.OPEN_SECONDS) == 1.0 == o(False, opening, 30.0)
    sealing = [(1.0, True), (5.0, False)]
    assert o(False, sealing, 5.0 + portal.CLOSE_SECONDS / 2) == pytest.approx(0.5)
    assert o(False, sealing, 5.0 + portal.CLOSE_SECONDS) == 0.0
    halfway = [(0.0, True), (portal.OPEN_SECONDS / 2, False)]   # sealed half-way through opening
    assert o(False, halfway, portal.OPEN_SECONDS / 2 + portal.CLOSE_SECONDS / 4) == pytest.approx(0.25)
    assert o(True, [(2.0, False)], 1.0) == 1.0


def test_a_crack_first_then_the_oval() -> None:
    assert portal.opening_size(0.0) == (0.0, 0.0) and portal.opening_size(1.0) == (1.0, 1.0)
    width, height = portal.opening_size(portal.CRACK_SHARE)
    assert height == 1.0 and width < 0.3
    early_width, early_height = portal.opening_size(0.1)
    assert early_width == portal.CRACK_WIDTH and 0 < early_height < 0.5


def test_changing_only_while_it_is_not_sealed() -> None:
    assert not portal.changing(False, [], 0.0, 9.0)
    assert portal.changing(False, [(3.0, True)], 2.0, 4.0) and portal.changing(True, [], 0.0, 0.1)
    assert not portal.changing(False, [(1.0, True), (2.0, False)], 2.0 + portal.CLOSE_SECONDS, 9.0)


def test_shape_stays_in_its_box_and_crackles() -> None:
    assert portal.portal_shape(0.0, 1.0) is None
    left, bottom, right, top = portal.EXTENT
    for now in np.linspace(0, 3, 40):
        shape = portal.portal_shape(1.0, float(now), seed=3)
        assert shape is not None and 0.0 < shape.glow <= 1.0
        points = [*shape.rim, *shape.inside, *(p for ring in shape.rings for p in ring), *(p for arm in shape.swirls for p in arm),
                  *(p for spark in shape.sparks for p in spark)]
        assert all(left <= x <= right and bottom <= y <= top for x, y in points)
    assert portal.portal_shape(1.0, 0.5, 3) == portal.portal_shape(1.0, 0.5, 3)          # the same each render
    a, b = portal.portal_shape(1.0, 0.0, 3), portal.portal_shape(1.0, 1.0 / portal.CRACKLE_RATE, 3)
    assert a is not None and b is not None and a.rim != b.rim and a.swirls != b.swirls   # new jags, turned swirls
    crack = portal.portal_shape(0.1, 0.0)
    assert crack is not None and max(x for x, _ in crack.inside) - min(x for x, _ in crack.inside) < 0.02   # a thin crack


# ----- the prop -----------------------------------------------------------------------------------


def test_the_portal_is_a_switched_prop() -> None:
    assert SCIFI_PROPS == ("portal", "hologram_display") and "portal" in PROP_KINDS and "portal" in SWITCHED_PROPS and "portal" in LIVING_KINDS
    assert "portal" in GLOWS and "portal" in FLOATING_IN_PLACE
    params = stage_params(props=[{"prop": "portal", "on": True}], characters=["pip"])
    assert params.props[0].on
    with pytest.raises(ValidationError, match="portal"):
        stage_params(props=[{"prop": "sofa", "on": True}])


def test_living_portal_opens_glows_and_is_not_graded() -> None:
    theme = Theme()
    prop = draw_prop("portal", height=3.0, theme=theme, main="#33CC99", living=True)
    assert prop.height == pytest.approx(3.0) and all(living_parts(prop, part) for part in PORTAL_PARTS if part != "portal_view")
    assert not living_parts(prop, "portal_view")   # no view: its swirling inside (Step 246)
    mark_lit(prop)
    live = LivingProp(prop)
    inside = living_parts(prop, "portal_inside")[0]
    assert len(inside.points) == 0 and live.glow is not None
    assert live.glow.spec.color.upper() == "#33CC99"   # the rim's own colour
    assert all(getattr(m, LIT) is False for part in PORTAL_PARTS for m in living_parts(prop, part))
    assert not live.changing(0.0, 5.0)
    live.switch(True, 1.0)
    assert live.changing(0.0, 0.5) is False and live.changing(0.5, 1.5)
    live.update(1.0 + portal.OPEN_SECONDS)
    assert len(inside.points) > 0
    low, high = prop.get_corner(np.array([-1.0, -1.0, 0.0])), prop.get_corner(np.array([1.0, 1.0, 0.0]))
    assert inside.get_center()[1] == pytest.approx((low[1] + high[1]) / 2, abs=0.15 * 3.0)
    live.switch(False, 4.0)
    live.update(4.0 + portal.CLOSE_SECONDS + 0.1)
    assert len(inside.points) == 0


def stage(make_project, params: dict[str, Any], beats: list[dict[str, Any]], characters: list[dict[str, Any]] | None = None) -> Project:
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=characters or CAST, scenes=scenes)))


ISO = {
    "place": "indoor",
    "map": "######\n#....#\n#.r..#\n#..a.#\n#....#\n##+###",
    "spots": {"r": "rift", "a": "here"},
}


def test_a_portal_stands_at_a_spot_of_an_iso_place(make_project) -> None:
    beats = [{"text": "A tear opens in the air, and a stranger steps out of it.",
              "actions": [{"switch_on": "tear", "at": 0.1}, {"enter": "kit", "door": "rift", "at": 0.5}]},
             {"text": "Then it seals.", "actions": [{"switch_off": "tear"}]}]
    params = {"light": "night", "iso": ISO, "props": [{"prop": "portal", "name": "tear", "at": "rift"}],
              "characters": [{"name": "pip", "at": "here"}, {"name": "kit", "at": "here"}]}
    assert check_project(stage(make_project, params, beats)) == []


@pytest.mark.render
def test_portal_opens_with_its_sounds(make_project, tmp_path: Path, monkeypatch) -> None:
    from vidgen import extensions, registry

    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    params = {"light": "night", "props": [{"prop": "portal", "name": "tear", "at": 0.7}], "characters": [{"name": "pip", "at": 0.3}]}
    beats = [{"text": "Pip waits in the dark for a while."}, {"text": "Then a rift tears open in the air.", "actions": [{"switch_on": "tear", "at": 0.2}]}]
    scene, frames = frames_of(stage(make_project, params, beats), tmp_path / "rift", monkeypatch)
    assert set(scene.living) == {"tear"}
    opened = round((scene.living["tear"].switches[0][0] + portal.OPEN_SECONDS) * 5)
    assert opened < len(frames)
    assert not np.array_equal(frames[opened], frames[2])   # the open portal and its glow show
    sounds = {s.sound for s in scene.sfx_log}
    assert {"whoosh", "thunder"} <= sounds and "click" not in sounds
    assert not scene.shadows or all(c.mobject is not scene.props["tear"] for g in scene.shadows for c in g.casters)   # it floats


# ----- holograms ----------------------------------------------------------------------------------


def test_hologram_colours() -> None:
    assert lightness("#000000") == 0.0 and lightness("#FFFFFF") == pytest.approx(1.0)
    dark = ManimColor(hologram_fill("#000000", "#5FD8FF")).to_rgb()
    assert dark == pytest.approx(np.array(ManimColor("#5FD8FF").to_rgb()) * DARK_SHARE, abs=0.01)
    assert hologram_fill("#FFFFFF", "#5FD8FF") != hologram_fill("#808080", "#5FD8FF")
    assert lightness(hologram_edge("#5FD8FF")) > lightness("#5FD8FF")


def test_hologram_setting() -> None:
    assert CharacterEntry(name="ai").hologram_look() is None
    assert CharacterEntry(name="ai", hologram=True).hologram_look() == HologramConfig()
    assert CharacterEntry(name="ai", hologram={"color": "accent", "opacity": 0.4}).hologram_look().opacity == 0.4
    for bad in ({"opacity": 0.1}, {"glow": 1}):
        with pytest.raises(ValidationError):
            CharacterEntry(name="ai", hologram=bad)


def test_a_hologram_character_is_drawn_in_its_colour() -> None:
    theme = Theme()
    plain = build_character(CharacterEntry(name="ai", look={"hair": "short"}), theme=theme)
    holo = build_character(CharacterEntry(name="ai", look={"hair": "short"}, hologram={"color": "#40C0FF", "opacity": 0.5}), theme=theme)
    assert is_hologram(holo) and not is_hologram(plain)
    tint = np.array(ManimColor("#40C0FF").to_rgb())
    filled = [m for m in holo.get_family() if m.has_points() and m.get_fill_opacity() > 0]
    assert filled
    for member in filled:
        rgb = np.array(member.get_fill_color().to_rgb())
        assert rgb == pytest.approx(tint * (rgb.sum() / tint.sum()), abs=0.02)   # a shade of the tint
        assert member.get_fill_opacity() <= 0.5 + 1e-6
    edges = {m.get_stroke_color().to_hex().upper() for m in holo.get_family() if m.has_points() and m.get_stroke_width() > 0 and m.get_stroke_opacity() > 0}
    assert edges == {hologram_edge("#40C0FF").upper()}
    assert apply_hologram(plain, HOLOGRAM_COLOR) is plain and is_hologram(plain)


@pytest.mark.render
def test_a_hologram_is_not_graded_by_the_light(make_project, tmp_path: Path, monkeypatch) -> None:
    from vidgen import extensions

    extensions.load_builtins()
    cast = [*CAST[:1], {"name": "ai", "look": {"body": "tall"}, "hologram": True}]
    params = {"light": "night", "characters": [{"name": "pip", "at": 0.3}, {"name": "ai", "at": 0.7}]}
    scene, _ = frames_of(stage(make_project, params, [{"text": "A glowing figure stands in the dark."}], characters=cast), tmp_path / "holo", monkeypatch)
    assert all(getattr(m, LIT, False) is False for m in scene.cast["ai"].get_family())
    assert any(getattr(m, LIT, False) for m in scene.cast["pip"].get_family())
