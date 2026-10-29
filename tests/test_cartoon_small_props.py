"""Everyday small props (DESIGN.md §69.56): cake, muffin, book, phone, letter, gift, balloons,
vase, watering can; a ringing phone, balloons let go, a watering can pouring."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from test_cartoon_living import room_project
from test_cartoon_stage import render_with_layout, stage_params
from vidgen.cartoon.holding import FULL_SIZE_HELD, HOLD_MAX_HEIGHT, HandlingStep, held_height, holding_problems
from vidgen.cartoon.living import RING_BURST, RING_PERIOD, RING_TILT, on_since, ring_burst, ring_bursts, ring_shake
from vidgen.cartoon.living_drawing import LivingProp, living_parts
from vidgen.cartoon.props import PROP_GRIPS, PROP_HEIGHTS, PROP_KINDS, PROP_SHAPES, SMALL_PROPS, WATERING_SPOUT, draw_prop
from vidgen.cartoon.shading import LIT
from vidgen.cartoon.small_props import (
    DROP_GRAVITY,
    FLOAT_DRIFT,
    FLOAT_MAX_SECONDS,
    FLOAT_MIN_SECONDS,
    POUR_FLOWS,
    float_end,
    float_point,
    float_progress,
    float_seconds,
    pour_drops,
    pour_flow,
    pour_tilt,
)
from vidgen.cli import check_project
from vidgen.sfx import BUILTIN_SOUNDS, RATE, synthesize
from vidgen.theme import Theme

OPENING = ("book", "letter", "gift")


# ----- drawing (no render) ----------------------------------------------------------------------------


def test_each_small_prop_builds() -> None:
    theme = Theme()
    assert set(SMALL_PROPS) <= set(PROP_KINDS) and all(kind in PROP_HEIGHTS for kind in SMALL_PROPS)
    for kind in SMALL_PROPS:
        for facing in ("right", "left"):
            prop = draw_prop(kind, height=1.5, theme=theme, facing=facing)
            assert prop.height == pytest.approx(1.5) and prop.feet()[1] == pytest.approx(0.0, abs=1e-6), (kind, facing)
            assert prop.kind == kind and prop.name == kind


@pytest.mark.parametrize("kind", OPENING)
def test_open_and_closed_shapes(kind: str) -> None:
    theme = Theme()
    assert PROP_SHAPES[kind] == ("closed", "open")
    closed = draw_prop(kind, height=1.0, theme=theme)
    opened = draw_prop(kind, height=1.0, theme=theme, shape="open")
    assert closed.shape == "closed" and opened.shape == "open"
    assert closed.shape_width("open") == pytest.approx(opened.width, rel=0.02)   # one prop unit for both shapes
    feet = closed.feet().copy()
    closed.show_shape("open")
    assert closed.width == pytest.approx(opened.width, rel=0.02) and closed.feet() == pytest.approx(feet)
    hidden = [m for m in closed.get_family() if m.points.size == 0]
    assert hidden   # the closed shape's members stay in the family without points
    closed.show_shape("closed")
    assert closed.height == pytest.approx(1.0, rel=0.02)


def test_grips_and_the_spout() -> None:
    theme = Theme()
    balloons = draw_prop("balloons", height=2.0, theme=theme)
    grip = balloons.grip_point()
    assert grip[1] < balloons.get_bottom()[1] + 0.1 * balloons.height   # held by the strings' end, near the weight
    can = draw_prop("watering_can", height=1.0, theme=theme)
    assert ("watering_can", None) in PROP_GRIPS and can.grip_point()[1] > can.get_center()[1]   # by the handle on top
    spout = can.prop_point(*WATERING_SPOUT)
    assert spout[0] > can.grip_point()[0] and can.get_left()[0] < spout[0] <= can.get_right()[0] + 1e-6
    mirrored = draw_prop("watering_can", height=1.0, theme=theme, facing="left")
    assert mirrored.prop_point(*WATERING_SPOUT)[0] < mirrored.grip_point()[0]


@pytest.mark.parametrize(("params", "message"), [
    ({"props": [{"prop": "cake", "open": True}]}, "open is for props that open (door, umbrella, book, letter, gift), not cake"),
    ({"props": [{"prop": "vase", "on": True}]}, "on is for props that switch on (fireplace, kettle, lamp, phone, tv, portal), not vase"),
])
def test_bad_params(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=re.escape(message)):
        stage_params(**params)


def test_params() -> None:
    p = stage_params(props=[{"prop": "book", "open": True}, {"prop": "phone", "on": True}, "gift"])
    assert p.props[0].open and p.props[1].on and p.props[2].prop == "gift"


# ----- a ringing phone (no render) --------------------------------------------------------------------


def test_ring_timing() -> None:
    assert on_since(True, [], 3.0) == 0.0 and on_since(False, [], 3.0) is None
    switches = [(2.0, True), (5.0, False), (7.0, True)]
    assert on_since(False, switches, 1.0) is None and on_since(False, switches, 4.0) == 2.0
    assert on_since(False, switches, 6.0) is None and on_since(False, switches, 9.0) == 7.0
    assert ring_burst(2.5, 2.0) and not ring_burst(2.0 + RING_BURST + 0.1, 2.0) and ring_burst(2.0 + RING_PERIOD + 0.1, 2.0)
    assert not ring_burst(1.0, 2.0) and not ring_burst(1.0, None)
    shakes = [ring_shake(2.0 + t / 200, 2.0) for t in range(int(RING_BURST * 200))]
    assert max(shakes) > 0.8 * RING_TILT and min(shakes) < -0.8 * RING_TILT and all(abs(a) <= RING_TILT + 1e-9 for a in shakes)
    assert ring_shake(2.0, 2.0) == 0.0 and ring_shake(2.0 + RING_BURST + 0.2, 2.0) == 0.0 and ring_shake(5.0, None) == 0.0
    assert ring_bursts([(2.0, 7.0), (10.0, 11.0)]) == [2.0, 4.0, 6.0, 10.0]


def test_a_phone_rings_and_shakes_while_on() -> None:
    theme = Theme()
    plain, living = draw_prop("phone", height=1.0, theme=theme), draw_prop("phone", height=1.0, theme=theme, living=True)
    assert living.height == pytest.approx(plain.height) and living.feet() == pytest.approx(plain.feet())
    living.shift([3.0, 1.0, 0.0])
    screen, rings = living_parts(living, "screen"), living_parts(living, "ring")
    assert len(screen) == 3 and len(rings) == 4
    live = LivingProp(living, seed=1)
    drawn = [m.points.copy() for m in live.movers()]
    assert not live.changing(0.0, 5.0) and all(m.get_fill_opacity() == 0.0 for m in screen)
    assert all(not getattr(m, LIT) for m in screen) and getattr(living.submobjects[0], LIT, True)   # only the lit screen shines
    live.switch(True, 1.0)
    assert live.changing(0.0, 5.0) and live.glow is None and live.steam is None
    live.update(1.0 + 0.3 / 13)   # in the first burst, near a shake's top
    assert all(m.get_fill_opacity() == 1.0 for m in screen) and all(m.get_stroke_opacity() > 0 for m in rings)
    assert any(not np.allclose(a, m.points) for a, m in zip(drawn, live.movers()))
    box = live.region()
    assert all(box[0] <= m.get_left()[0] and m.get_right()[0] <= box[2] and m.get_top()[1] <= box[3] for m in live.movers() if m.points.size)
    live.update(1.0 + RING_BURST + 0.3)   # between bursts: still and quiet, the screen still lit
    assert all(np.allclose(a, m.points) for a, m in zip(drawn, live.movers()))
    assert all(m.get_stroke_opacity() == 0.0 for m in rings) and screen[0].get_fill_opacity() == 1.0
    live.switch(False, 4.0)
    live.update(4.5)
    assert all(m.get_fill_opacity() == 0.0 for m in screen) and all(np.allclose(a, m.points) for a, m in zip(drawn, live.movers()))


def test_the_phone_sound() -> None:
    sound = BUILTIN_SOUNDS["phone"]
    samples = synthesize("phone")
    assert len(samples) == round(sound.duration * RATE) and np.array_equal(samples, synthesize("phone"))
    middle = samples[int(0.46 * len(samples)) : int(0.48 * len(samples))]
    assert np.abs(middle).max() < 0.1 * np.abs(samples).max()   # the gap between the two rings


# ----- balloons floating away (no render) -------------------------------------------------------------


def test_balloons_float_up_and_drift_with_the_wind() -> None:
    start = (1.0, -0.5)
    calm, windy, left = float_end(start, 5.0, 0.0), float_end(start, 5.0, 0.8), float_end(start, 5.0, -0.8)
    assert calm == (1.0, 5.0) and windy[0] == pytest.approx(1.0 + FLOAT_DRIFT * 0.8 * 5.5) and left[0] < 1.0
    points = [float_point(u, start, windy, seed=3) for u in np.linspace(0.0, 1.0, 41)]
    assert points[0][:2] == pytest.approx(start) and points[-1][:2] == pytest.approx(windy)
    ys = [p[1] for p in points]
    assert np.all(np.diff(ys) > 0)   # always rising
    steps = np.diff(ys)
    assert steps[1] < steps[8]   # speeding up from rest
    assert points[0][2] == pytest.approx(0.0) and points[-1][2] == pytest.approx(0.0, abs=1e-9)
    assert max(abs(p[2]) for p in points) > 1.0   # leaning as they sway
    assert float_point(0.5, start, windy, seed=3) == float_point(0.5, start, windy, seed=3) != float_point(0.5, start, windy, seed=4)
    assert float_progress(0.0) == 0.0 and float_progress(1.0) == pytest.approx(1.0)
    assert float_seconds(0.1) == FLOAT_MIN_SECONDS and float_seconds(500.0) == FLOAT_MAX_SECONDS
    assert FLOAT_MIN_SECONDS < float_seconds(5.0) < FLOAT_MAX_SECONDS


def test_balloons_are_held_at_full_size() -> None:
    assert "balloons" in FULL_SIZE_HELD
    assert held_height(1.1, 2.0) == pytest.approx(HOLD_MAX_HEIGHT * 2.0)
    assert held_height(1.1, 2.0, full_size=True) == pytest.approx(2.2)


# ----- pouring (no render) ------------------------------------------------------------------------------


def test_the_pour_tilt_and_flow() -> None:
    assert pour_tilt(0.0) == 0.0 and pour_tilt(1.0) == pytest.approx(0.0) and pour_tilt(0.5) == 1.0
    assert pour_tilt(0.1) == pytest.approx(pour_tilt(0.9)) and 0.0 < pour_tilt(0.1) < 1.0
    start, end = pour_flow(2.0)
    assert 0.0 < start < end < 2.0 and start + end == pytest.approx(2.0)
    assert pour_tilt(start / 2.0) == pytest.approx(POUR_FLOWS)


def test_the_drops_fall_from_the_spout_to_the_ground() -> None:
    flow, spout, ground, height = (0.4, 1.6), (2.0, 1.0), 0.0, 2.0
    assert pour_drops(0.3, flow, spout, ground, height, 1.0) == []
    drops = pour_drops(1.0, flow, spout, ground, height, 1.0, seed=2)
    assert len(drops) > 5 and drops == pour_drops(1.0, flow, spout, ground, height, 1.0, seed=2)
    assert all(d.x >= spout[0] and ground < d.y <= spout[1] + 1e-9 and d.radius > 0 for d in drops)
    back = pour_drops(1.0, flow, spout, ground, height, -1.0, seed=2)
    assert all(d.x <= spout[0] for d in back)
    fall = math.sqrt(2 * (spout[1] - ground) / (DROP_GRAVITY * height))
    assert pour_drops(flow[1] + fall + 0.05, flow, spout, ground, height, 1.0) == []   # all landed after the flow


# ----- validate (no render) ------------------------------------------------------------------------------


def test_let_go_and_pour_in_the_replay() -> None:
    characters = {"pip": (0.0, 1.0)}
    props = {"balloons": 0.1, "cake": 0.1, "can": 0.1}
    kinds = {"balloons": "balloons", "cake": "cake", "can": "watering_can"}

    def problems(*steps: tuple[str, dict[str, Any]]) -> list[tuple[str, str]]:
        played = [HandlingStep(f"b{k}", action, ("pip",), options) for k, (action, options) in enumerate(steps)]
        return holding_problems(played, characters=characters, props=props, place_x=lambda p: 0.0, to_fraction=lambda x: x, kinds=kinds)

    assert problems(("hold", {"to": "balloons"}), ("let_go", {})) == []
    assert problems(("pick_up", {"to": "can"}), ("pour", {}), ("put_down", {})) == []
    [(where, message)] = problems(("hold", {"to": "cake"}), ("let_go", {}))
    assert where == "b1.target" and "'cake' does not float away" in message and "put_down" in message
    [(_, message)] = problems(("hold", {"to": "cake"}), ("pour", {}))
    assert "'cake' does not pour" in message
    [(_, message)] = problems(("let_go", {}),)
    assert "holds no prop" in message
    [(where, message)] = problems(("hold", {"to": "balloons"}), ("let_go", {}), ("pick_up", {"to": "balloons"}))
    assert where == "b2.to" and "floated away out of the frame (b1)" in message


def test_actions_validate(make_project) -> None:
    params = {
        "props": [{"prop": "table", "at": 0.5}, {"prop": "phone", "at": 0.5, "lift": 0.17}, {"prop": "balloons", "at": 0.3},
                  {"prop": "watering_can", "at": 0.7}, {"prop": "book", "at": 0.6}, "cake"],
        "characters": [{"name": "pip", "at": 0.3}, {"name": "kit", "at": 0.7}],
    }
    good = [
        {"text": "The phone rings and Pip lets the balloons go.", "actions": [
            {"switch_on": "phone"}, {"hold": "pip", "to": "balloons", "at": 0}, {"let_go": "pip", "at": 0.4}, {"open": "book", "at": 0.5}]},
        {"text": "Kit waters the plants and the phone stops.", "actions": [
            {"pick_up": "kit", "to": "watering_can"}, {"pour": "kit", "at": 0.4}, {"switch_off": "phone", "at": 0.8}, {"close": "book"}]},
    ]
    assert check_project(room_project(make_project, params, good)) == []
    bad = [{"text": "Hm.", "actions": [{"hold": "pip", "to": "cake", "at": 0}, {"let_go": "pip", "prop": "cake", "at": 0.3},
                                       {"pour": "kit", "prop": "balloons", "at": 0.5}, {"open": "cake", "at": 0.6}]}]
    problems = check_project(room_project(make_project, params, bad))
    assert any("'cake' (cake) does not float away (props that do: balloons)" in p for p in problems), problems
    assert any("'balloons' (balloons) does not pour (props that do: watering_can)" in p for p in problems), problems
    assert any("'cake' cannot open (props that can: book, door, gift, letter, umbrella)" in p for p in problems), problems


# ----- render ---------------------------------------------------------------------------------------------


YARD: dict[str, Any] = {
    "props": [{"prop": "phone", "at": 0.5, "on": True}, {"prop": "balloons", "at": 0.25}, {"prop": "watering_can", "at": 0.75}],
    "characters": [{"name": "pip", "at": 0.25}, {"name": "kit", "at": 0.75}],
}


@pytest.mark.render
def test_balloons_float_away_a_can_pours_and_the_phone_rings(make_project, tmp_path: Path, monkeypatch) -> None:
    """Pip lets go of the balloons: they end above the frame, out of its hand; kit pours: the
    water is gone when the pour ends and the can is back as it was; the phone rang all along:
    a ``phone`` sound at each burst."""
    from vidgen import extensions, registry

    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    beats = [{"text": "Pip holds the balloons and Kit holds the can.", "actions": [
                {"hold": "pip", "to": "balloons", "at": 0}, {"hold": "kit", "to": "watering_can", "at": 0}]},
             {"text": "Pip lets them go while Kit waters the grass.", "actions": [{"let_go": "pip"}, {"pour": "kit"}]}]
    scene, _ = render_with_layout(room_project(make_project, YARD, beats), "home", tmp_path / "media")
    balloons, can = scene.props["balloons"], scene.props["watering_can"]
    assert balloons.held_by is None and balloons.get_bottom()[1] > scene.frame_height / 2 and scene.holdings.hands("pip") == {}
    assert can.held_by == "kit" and not any(type(m).__name__ == "WaterDrops" for m in scene.mobjects)
    hand = scene.cast["kit"].hand_point(can.hand)
    assert can.grip_point()[:2] == pytest.approx(hand[:2], abs=1e-3)
    rings = [e.time for e in scene.sfx_log if e.sound == "phone"]
    assert rings == pytest.approx([k * RING_PERIOD for k in range(len(rings))]) and len(rings) == math.ceil(float(scene.renderer.time) / RING_PERIOD)
