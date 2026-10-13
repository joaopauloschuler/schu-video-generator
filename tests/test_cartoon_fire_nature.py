"""Step 121: props that move by themselves, part 2 (DESIGN.md §69.55): a fireplace's flames, glow
and crackle, a kettle's steam, fruit falling from a tree, birds crossing the sky. Pure, seeded
maths without rendering; three tiny renders: a fire lit later and a flock that sets off later
change no pixel before then, and a fruit falls on a head with a thud and stars."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from test_cartoon_living import frames_of, room_project
from test_cartoon_stage import stage_params
from vidgen.ambience import FIRE_LEVEL, fire_loop
from vidgen.cartoon.living import (
    FIRE_GLOW_FLICKER,
    FLAME_BASE,
    FLAME_FEET,
    FLAME_HEIGHTS,
    FLAME_LEAN_MAX,
    STEAM_LEAN_MAX,
    STEAM_PUFFS,
    STEAM_SPOUT,
    fire_flicker,
    flame_lean,
    flame_shapes,
    on_spans,
    steam_box,
    steam_puffs,
)
from vidgen.cartoon.living_drawing import LivingProp, closed_curve, living_parts
from vidgen.cartoon.nature import (
    BOUNCE_TURN,
    FRUIT_SPOTS,
    MAX_BIRDS,
    bird_outline,
    bird_place,
    drop_point,
    drop_timing,
    flock_birds,
    flock_box,
    flock_plan,
    fruit_to_drop,
    wing_lift,
)
from vidgen.cartoon.nature_drawing import wing_curve
from vidgen.cartoon.props import FRUIT_INDEX, draw_prop
from vidgen.cartoon.shading import LIT
from vidgen.cli import check_project
from vidgen.loudness import integrated_loudness
from vidgen.sfx import RATE
from vidgen.theme import Theme

# ----- fire and steam (no render) -----------------------------------------------------------------


def test_flames_are_seeded_flicker_and_lean() -> None:
    times = [k / 15 for k in range(60)]
    shapes = [flame_shapes(t, 4) for t in times]
    assert shapes == [flame_shapes(t, 4) for t in times]   # the same in every render
    assert shapes[0] != flame_shapes(0.0, 5)               # another fire differs
    assert len(shapes[0]) == len(FLAME_FEET) + 3 and [s.inner for s in shapes[0]] == [False] * 5 + [True] * 3
    tops = np.array([[max(y for _, y in s.points) for s in frame[:5]] for frame in shapes])
    heights = tops - FLAME_BASE
    assert np.all(heights > 0.4 * np.array(FLAME_HEIGHTS)) and np.all(heights < 1.6 * np.array(FLAME_HEIGHTS))
    assert np.all(heights.std(axis=0) > 0.01)   # each tongue flickers
    assert all(abs(x - foot) <= 0.2 for frame in shapes for s, foot in zip(frame, FLAME_FEET) for x, _ in s.points)
    leaning = flame_shapes(1.0, 4, flame_lean(3.0))
    tip = lambda s: max(s.points, key=lambda p: p[1])   # noqa: E731
    assert all(tip(a)[0] > tip(b)[0] for a, b in zip(leaning[:5], flame_shapes(1.0, 4)[:5]))   # wind to the right
    assert flame_lean(10.0) == FLAME_LEAN_MAX and flame_lean(-10.0) == -FLAME_LEAN_MAX and flame_lean(0.0) == 0.0
    glows = [fire_flicker(t, 4) for t in times]
    assert all(1.0 - FIRE_GLOW_FLICKER - 1e-9 <= g <= 1.0 + 1e-9 for g in glows) and max(glows) - min(glows) > 0.05


def test_steam_rises_from_the_spout_and_drifts_with_the_wind() -> None:
    sx, sy = STEAM_SPOUT
    for t in (0.0, 0.7, 3.1):
        puffs = steam_puffs(t, 2)
        assert puffs == steam_puffs(t, 2) and 0 < len(puffs) <= STEAM_PUFFS
        assert all(p.y >= sy and 0 < p.opacity <= 1 for p in puffs)
        low = min(puffs, key=lambda p: p.y)
        high = max(puffs, key=lambda p: p.y)
        assert low.radius < high.radius   # they grow as they rise
        left, bottom, right, top = steam_box()
        assert all(left <= p.x - p.radius and p.x + p.radius <= right and p.y + p.radius <= top for p in puffs)
    calm, windy = steam_puffs(1.0, 2), steam_puffs(1.0, 2, 1.0)
    assert sum(p.x for p in windy) > sum(p.x for p in calm)
    assert steam_puffs(1.0, 2, 50.0) == steam_puffs(1.0, 2, STEAM_LEAN_MAX)   # capped
    assert steam_box(1.0)[2] > steam_box(0.0)[2] and steam_box(-1.0)[0] < steam_box(0.0)[0]


def test_on_spans() -> None:
    assert on_spans(True, [], 10.0) == [(0.0, 10.0)]
    assert on_spans(False, [(2.0, True), (5.0, False), (7.0, True)], 10.0) == [(2.0, 5.0), (7.0, 10.0)]
    assert on_spans(False, [(2.0, True), (3.0, True), (12.0, False)], 10.0) == [(2.0, 10.0)]
    assert on_spans(True, [(0.0, False)], 4.0) == [] and on_spans(False, [], 4.0) == []


def test_fire_and_kettle_draw_inside_their_box_and_switch() -> None:
    theme = Theme()
    for kind in ("fireplace", "kettle"):
        plain, living = draw_prop(kind, height=2.0, theme=theme), draw_prop(kind, height=2.0, theme=theme, living=True)
        assert plain.width == pytest.approx(living.width) and plain.height == pytest.approx(living.height), kind
        assert living.feet() == pytest.approx(plain.feet())
    fire = draw_prop("fireplace", height=2.0, theme=theme, living=True)
    flames = living_parts(fire, "flame")
    assert len(flames) == 8 and fire.submobjects.index(flames[-1]) < len(fire.submobjects) - 2   # behind the two front logs
    live = LivingProp(fire, seed=1)
    assert all(m.get_fill_opacity() == 0.0 for m in flames) and not live.changing(0.0, 5.0)   # out: as drawn
    assert not getattr(flames[0], LIT) and live.glow is not None and live.steam is None
    live.switch(True, 1.0)
    live.update(1.5)
    assert all(m.get_fill_opacity() == 1.0 for m in flames) and live.changing(2.0, 3.0)
    before = [m.points.copy() for m in flames]
    live.update(1.7)
    assert any(not np.allclose(a, m.points) for a, m in zip(before, flames))   # they flicker
    assert all(m.get_bottom()[1] >= fire.get_bottom()[1] and m.get_top()[1] <= fire.get_top()[1] for m in flames)
    assert 0 < live.glow.submobjects[-1].get_fill_opacity()
    kettle = draw_prop("kettle", height=1.0, theme=theme, living=True).shift([2.0, 0.0, 0.0])
    steaming = LivingProp(kettle, on=True, seed=2)
    shown = [m for m in steaming.steam.submobjects if m.get_fill_opacity() > 0]
    assert shown and getattr(steaming.steam.submobjects[0], LIT)   # steam is graded like the set
    box = steaming.region()
    assert all(box[0] <= m.get_left()[0] and m.get_right()[0] <= box[2] and m.get_top()[1] <= box[3] for m in shown)
    assert box[3] > kettle.get_top()[1] + kettle.height   # the steam rises well above the kettle
    steaming.switch(False, 1.0)
    steaming.update(1.5)
    assert all(m.get_fill_opacity() == 0.0 for m in steaming.steam.submobjects)


def test_closed_curve_passes_through_its_corners() -> None:
    corners = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    curve = closed_curve(corners)
    assert curve.shape == (16, 3) and np.allclose(curve[0::4, :2], corners) and np.allclose(curve[3::4, :2], np.roll(corners, -1, axis=0))


def test_the_fire_crackle_loop() -> None:
    loop = fire_loop()
    assert loop.shape == (8 * RATE, 2) and loop is fire_loop()
    assert integrated_loudness(loop) == pytest.approx(FIRE_LEVEL, abs=0.3)
    seam = np.abs(loop[0] - loop[-1]).max()
    assert seam < 4 * np.abs(np.diff(loop, axis=0)).mean() + 0.05   # no click where it loops


# ----- fruit (no render) ------------------------------------------------------------------------------


def test_a_tree_carries_its_fruit_inside_its_box() -> None:
    theme = Theme()
    plain, fruity = draw_prop("tree", height=3.0, theme=theme), draw_prop("tree", height=3.0, theme=theme, fruit=True)
    assert fruity.width == pytest.approx(plain.width) and fruity.height == pytest.approx(plain.height)
    indices = [getattr(m, FRUIT_INDEX, None) for m in fruity.submobjects]
    assert sorted({k for k in indices if k is not None}) == list(range(len(FRUIT_SPOTS)))
    assert draw_prop("bush", height=1.0, theme=theme, fruit=True).submobjects.__len__() == draw_prop("bush", height=1.0, theme=theme).submobjects.__len__()


def test_a_dropped_fruit_falls_faster_and_faster_then_bounces() -> None:
    timing = drop_timing(0.4, 0.05)
    assert timing.seconds == pytest.approx(math.sqrt(0.8 / 3.2) + 2 * math.sqrt(0.1 / 3.2))
    start, impact, end = (1.0, 3.0), (1.0, 0.0), (1.3, 0.0)
    shares = np.linspace(0.0, timing.impact, 11)
    ys = [drop_point(u, start, impact, end, hit_share=timing.impact, bounce=0.4)[1] for u in shares]
    steps = -np.diff(ys)
    assert ys[0] == pytest.approx(3.0) and ys[-1] == pytest.approx(0.0) and np.all(np.diff(steps) > 0)   # accelerating
    middle = drop_point(timing.impact + (1 - timing.impact) / 2, start, impact, end, hit_share=timing.impact, bounce=0.4)
    assert middle[1] == pytest.approx(0.4) and middle[0] == pytest.approx(1.15)   # the bounce's top, half-way across
    x, y, turn = drop_point(1.0, start, impact, end, hit_share=timing.impact, bounce=0.4)
    assert (x, y) == pytest.approx(end) and turn == pytest.approx(-BOUNCE_TURN)   # rolling to the right: clockwise
    assert drop_point(0.0, start, impact, end, hit_share=timing.impact, bounce=0.4)[2] == 0.0


def test_which_fruit_falls() -> None:
    assert fruit_to_drop([1, 2, 3]) == 1
    assert fruit_to_drop([0, 2, 3], near_x=0.9, xs=[0.0, 0.5, 1.0, 1.5]) == 2
    with pytest.raises(ValueError, match="no fruit left"):
        fruit_to_drop([])


# ----- birds (no render) ------------------------------------------------------------------------------


def test_a_flock_is_seeded_and_crosses_the_stage() -> None:
    birds = flock_birds(5, 3)
    assert birds == flock_birds(5, 3) and birds != flock_birds(5, 4)
    assert birds[0].dx == 0.0 and all(b.dx > 0 for b in birds[1:])   # the leader first, the rest behind it
    plan = flock_plan(1.0, seconds=None, direction=1.0, left=-8.0, right=8.0, y=2.0, span=0.3, count=5, seed=3, frame_width=16.0)
    assert plan.seconds == pytest.approx((16.0 + 2 * plan.margin()) / (0.2 * 16.0))
    assert bird_place(plan, 0, 0.99) is None and bird_place(plan, 0, plan.end + 0.01) is None
    xs = [bird_place(plan, 0, t)[0] for t in np.linspace(plan.start, plan.end, 30)]
    assert xs[0] < -8.0 and xs[-1] > 8.0 and np.all(np.diff(xs) > 0)
    first, last = (bird_place(plan, k, plan.start) for k in (0, len(birds) - 1))
    assert last[0] < first[0]   # it follows the leader
    back = flock_plan(0.0, seconds=4.0, direction=-1.0, left=-8.0, right=8.0, y=2.0, span=0.3, count=3, seed=3, frame_width=16.0)
    assert bird_place(back, 0, 0.0)[0] > 8.0 and bird_place(back, 0, 4.0)[0] < -8.0
    box = flock_box(plan, plan.start, plan.start + 1.0)
    whole = flock_box(plan, 0.0, math.inf)
    assert box[2] < whole[2] and whole[0] < -8.0 and whole[2] > 8.0 and flock_box(plan, 0.0, 0.5) is None
    assert plan.flying(0.0, 1.0) and not plan.flying(plan.end + 0.1, plan.end + 5.0)


def test_wings_flap_and_glide() -> None:
    bird = flock_birds(1, 7)[0]
    lifts = [wing_lift(t / 60, bird) for t in range(600)]
    assert min(lifts) < -0.8 and max(lifts) > 0.8 and all(-1.0 <= v <= 1.0 for v in lifts)
    up, down = bird_outline(1.0), bird_outline(-1.0)
    assert up[0][1] > up[2][1] and down[0][1] < down[2][1] and up[0][0] == -0.5 and up[-1][0] == 0.5
    a, b, c = np.array([0.0, 0.0, 0.0]), np.array([1.0, 1.0, 0.0]), np.array([2.0, 0.0, 0.0])
    curve = wing_curve(a, b, c)
    middle = (curve[0] + 3 * curve[1] + 3 * curve[2] + curve[3]) / 8   # the cubic at t = 0.5
    assert np.allclose(middle, b)


# ----- params and actions (no render) ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"props": [{"prop": "bush", "fruit": True}]}, "fruit is for a tree, not bush"),
        ({"props": [{"prop": "sofa", "on": True}]}, "on is for props that switch on (fireplace, kettle, lamp, phone, tv), not sofa"),
        ({"room": True, "birds": True}, "birds fly outdoors"),
        ({"birds": False}, "birds: false is the default"),
        ({"birds": MAX_BIRDS + 1}, f"less than or equal to {MAX_BIRDS}"),
    ],
)
def test_bad_params(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=re.escape(message)):
        stage_params(**params)


def test_params() -> None:
    p = stage_params(birds=7, props=[{"prop": "tree", "fruit": True}, {"prop": "fireplace", "on": True}, {"prop": "kettle", "on": True}])
    assert p.birds.count == 7 and p.birds.direction == "right" and p.props[0].fruit and p.props[1].on
    assert stage_params(birds=True).birds.count == 5 and stage_params().birds is None


def test_actions_validate(make_project) -> None:
    params = {"props": [{"prop": "tree", "fruit": True}, {"prop": "tree", "name": "bare"}, "bush"], "characters": ["pip"]}
    good = [{"text": "An apple falls, then another one on Pip.", "actions": [{"drop_fruit": "tree"}, {"drop_fruit": "tree", "to": "pip", "at": 0.5}]},
            {"text": "Birds fly over.", "actions": [{"birds": 4, "direction": "left"}, {"action": "birds", "at": 0.5}]}]
    assert check_project(room_project(make_project, params, good)) == []
    bad = [{"text": "Hm.", "actions": [{"drop_fruit": "bare"}, {"drop_fruit": "bush"}, {"drop_fruit": "tree", "to": "kit"}, {"birds": 0}]}]
    problems = check_project(room_project(make_project, params, bad))
    assert any("tree 'bare' has no fruit: give it fruit: true" in p for p in problems), problems
    assert any("'bush' is not a tree" in p for p in problems), problems
    assert any("'kit' is not a character on the stage" in p for p in problems), problems
    assert any("how many birds?" in p for p in problems), problems
    five = [{"text": "Five fall.", "actions": [{"drop_fruit": "tree", "at": k / 5} for k in range(5)]}]
    assert any("has 4 fruits; they have all fallen by then" in p for p in check_project(room_project(make_project, params, five)))
    indoors = [{"text": "Birds in the room?", "actions": [{"birds": 3}]}]
    assert any("birds fly outdoors, not in a room" in p for p in check_project(room_project(make_project, {"room": True, "characters": ["pip"]}, indoors)))


# ----- renders ---------------------------------------------------------------------------------------


ROOM: dict[str, Any] = {
    "light": "night",
    "room": {"windows": [0.2]},
    "props": [{"prop": "fireplace", "at": 0.5, "against": "wall"}, {"prop": "armchair", "at": 0.8, "depth": 0.15}],
    "characters": [{"name": "pip", "at": 0.25, "depth": 0.1}],
}
BEATS = [{"text": "Pip waits in the cold room for a little while."}, {"text": "Then the fire is lit, and it crackles."}]


@pytest.mark.render
def test_a_fire_lit_later_is_drawn_as_before_until_then(make_project, tmp_path: Path, monkeypatch) -> None:
    """Every frame before the fire is lit is the same, pixel for pixel, as without lighting it;
    then the flames burn; the crackle bed spans from the lighting to the scene's end."""
    from vidgen import extensions, registry

    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    plain, before = frames_of(room_project(make_project, ROOM, BEATS), tmp_path / "plain", monkeypatch)
    assert plain.living == {} and "ambience" not in plain.timings()
    lit = [BEATS[0], {**BEATS[1], "actions": [{"switch_on": "fireplace", "at": 0.3}]}]
    scene, after = frames_of(room_project(make_project, ROOM, lit), tmp_path / "lit", monkeypatch)
    fire = scene.living["fireplace"]
    switch = round(fire.switches[0][0] * 5)
    assert len(after) == len(before) and 5 < switch < len(after) - 3
    assert all(np.array_equal(a, b) for a, b in zip(after[:switch], before[:switch]))
    assert not np.array_equal(after[switch + 1], before[switch + 1])
    [bed] = scene.timings()["ambience"]
    assert bed["bed"] == "fire" and bed["start"] == pytest.approx(fire.switches[0][0]) and bed["end"] == pytest.approx(float(scene.renderer.time))
    assert [s for s in scene.sfx_log if s.sound == "burner"]


YARD: dict[str, Any] = {
    "props": [{"prop": "tree", "at": 0.35, "fruit": True}],
    "characters": [{"name": "pip", "at": 0.36}],
}


@pytest.mark.render
def test_birds_and_a_fruit_on_a_head(make_project, tmp_path: Path, monkeypatch) -> None:
    """A flock that sets off at 2 s changes no pixel before then; a fruit aimed at pip falls on its
    head (thud, stars) and ends on the ground beside it, its spot on the tree empty."""
    from vidgen import extensions, registry
    from vidgen.scenes import stage as stage_module

    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    made: list[Any] = []
    real = stage_module.hit_stars
    monkeypatch.setattr(stage_module, "hit_stars", lambda figure, **kw: (made.append(real(figure, **kw)), made[-1])[1])
    beats = [{"text": "Pip rests under the tree on a warm afternoon."}, {"text": "Then something falls on Pip's head."}]
    plain, before = frames_of(room_project(make_project, YARD, beats), tmp_path / "plain", monkeypatch)
    flying = {**YARD, "birds": {"start": 2.0, "count": 4}}
    dropped = [beats[0], {**beats[1], "actions": [{"drop_fruit": "tree", "to": "pip", "at": 0.2}]}]
    scene, after = frames_of(room_project(make_project, flying, dropped), tmp_path / "birds", monkeypatch)
    assert len(after) == len(before) > 15
    assert all(np.array_equal(a, b) for a, b in zip(after[:10], before[:10]))   # 2 s at 5 fps
    assert not np.array_equal(after[12], before[12])
    [flock] = scene.flocks
    assert flock.plan.start == 2.0 and len(flock.submobjects) == 4
    fallen = [m for m in scene.mobjects if type(m).__name__ == "FallenFruit"]
    assert len(fallen) == 1 and fallen[0].skin.get_bottom()[1] == pytest.approx(scene.grounds["pip"], abs=0.01)
    assert abs(fallen[0].grip_point()[0] - scene.cast["pip"].feet()[0]) > 0.2 * scene.cast["pip"].character_height   # bounced aside
    index = fallen[0].index
    assert all(m.get_fill_opacity() == 0.0 for m in scene.props["tree"].get_family() if getattr(m, FRUIT_INDEX, None) == index)
    assert [s for s in scene.sfx_log if s.sound == "thud"]
    assert len(made) == 1 and made[0].kind == "stars" and made[0].age > 0   # it fell on the head: stars from the impact on
