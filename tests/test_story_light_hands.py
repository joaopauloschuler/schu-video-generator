"""Step 247 (DESIGN.md §100.15): a fill light on a stage's characters, an iridescent visitor's
own glow, and two holding hands who step in close and walk side by side."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from manim import Square

from vidgen.cartoon.character import build_character
from vidgen.cartoon.figure_fx import HAND_MIN_APART, HandHold
from vidgen.cartoon.lighting import LightGrade, grade_rgbas, lifted, light_grade
from vidgen.cartoon.shading import LIGHT_LIFT, StageLight, mark_light_lift, mark_lit
from vidgen.config import CharacterEntry, IridescentConfig
from vidgen.theme import Theme


def test_a_lift_moves_a_grade_back_to_the_colours_as_drawn() -> None:
    night = light_grade("night")
    assert lifted(night, 0.0) is night
    full = lifted(night, 1.0)
    assert full.multiply == (1.0, 1.0, 1.0) and full.glow == (0.0, 0.0, 0.0)
    assert (full.stars, full.shadow, full.saturation) == (night.stars, night.shadow, night.saturation)
    half = lifted(LightGrade((0.4, 0.5, 0.6), (0.2, 0.0, 0.0), saturation=0.5), 0.5)
    assert half.multiply == pytest.approx((0.7, 0.75, 0.8)) and half.glow == pytest.approx((0.1, 0.0, 0.0))
    assert half.saturation == 0.5
    skin = np.array([[0.72, 0.52, 0.38, 1.0]])
    dark, lit = grade_rgbas(skin, night), grade_rgbas(skin, lifted(night, 0.45))
    assert lit[0, :3].mean() > dark[0, :3].mean() + 0.1   # a face reads again at night


class _Camera:
    """The three drawing hooks :class:`StageLight` wraps, returning what they are given."""

    def get_fill_rgbas(self, vmobject: Any) -> np.ndarray:
        return np.array(vmobject.fill_rgbas, dtype=float)

    def get_stroke_rgbas(self, vmobject: Any, *args: Any, **kwargs: Any) -> np.ndarray:
        return np.array(vmobject.stroke_rgbas, dtype=float)

    def display_image_mobject(self, image: Any, pixel_array: Any) -> None:
        return None


def test_the_stage_light_lifts_what_a_fill_light_marks() -> None:
    camera = _Camera()
    light = StageLight(camera, light_grade("night"))
    plain, lit = Square().set_fill("#B98560", opacity=1), Square().set_fill("#B98560", opacity=1)
    mark_lit(plain, lit)
    mark_light_lift(lit, 0.5)
    assert getattr(lit.get_family()[-1], LIGHT_LIFT) == 0.5
    dark, bright = camera.get_fill_rgbas(plain)[0, :3], camera.get_fill_rgbas(lit)[0, :3]
    assert bright.mean() > dark.mean() + 0.1
    assert camera.get_fill_rgbas(lit)[0, :3] == pytest.approx(bright)   # made once, the same again


def test_an_iridescent_visitor_glows_by_default() -> None:
    assert IridescentConfig().glow == 0.5
    entry = CharacterEntry(name="vis", iridescent={"glow": 0.9})
    assert entry.iridescent_look() is not None and entry.iridescent_look().glow == 0.9


def _pair() -> tuple[Any, Any]:
    theme = Theme()
    a = build_character(CharacterEntry(name="ana"), theme=theme, height=2.0).stop_idle()
    b = build_character(CharacterEntry(name="ben", look={"body": "tall"}), theme=theme, height=2.0).stop_idle()
    a.shift(np.array([-1.5, 0.0, 0.0]) - a.feet())
    b.shift(np.array([1.5, 0.0, 0.0]) - b.feet())
    return a, b


def test_two_far_apart_step_in_until_their_hands_meet() -> None:
    a, b = _pair()
    hold = HandHold(a, b, 0.0)
    for k in range(12):
        hold.update(k * 0.05)
    apart = float(b.feet()[0] - a.feet()[0])
    assert HAND_MIN_APART * 2.0 - 1e-6 <= apart < 3.0 - 0.5   # closer, never on top of each other
    ha, hb = np.asarray(a.hand_point(hold.hands[0])), np.asarray(b.hand_point(hold.hands[1]))
    assert float(np.linalg.norm(ha[:2] - hb[:2])) < 0.2   # the hands meet
    before = (float(a.feet()[0]), float(b.feet()[0]))
    hold.update(1.0)   # standing still: the step is kept, not taken again
    assert (float(a.feet()[0]), float(b.feet()[0])) == pytest.approx(before)


def test_two_walking_hand_in_hand_keep_side_by_side() -> None:
    a, b = _pair()
    hold = HandHold(a, b, 0.0)
    for k in range(12):
        hold.update(k * 0.05)
    formation = np.asarray(b.feet()[:2]) - np.asarray(a.feet()[:2])
    for k in range(1, 6):   # each frame their walks put them anew, b lagging behind a
        a.shift(np.array([-1.5 + 0.3 * k, -0.2 * k, 0.0]) - a.feet())
        b.shift(np.array([1.5 + 0.1 * k, 0.1 * k, 0.0]) - b.feet())
        hold.update(1.0 + k * 0.05)
        assert np.asarray(b.feet()[:2]) - np.asarray(a.feet()[:2]) == pytest.approx(formation)
