"""Step 98: wind on a stage: levels, seeded gusts, fades, sway angles, trailing pieces and
particles drifting, without manim; the ``wind`` action and param in ``vidgen validate``; two
tiny renders (``wind: 0`` gives the same frames as no wind; a windy stage that calms down).

Step 104: strong wind shows clearly (felt force), leaves and wind streaks, and ``blow_away``: the
seeded gusty path, the holdings replay, validate, the action on a fake stage and a tiny render."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_acting import CAST, VOICES
from test_cartoon_limbs import generated
from test_cartoon_stage import render_with_layout, stage_params
from vidgen import extensions, registry
from vidgen.cartoon.character import TRAIL_ATTRIBUTE
from vidgen.cartoon.generator import TRAIL_WEIGHTS
from vidgen.cartoon.holding import HandlingStep, Holdings, holding_problems
from vidgen.cartoon.wind import (
    BLOW_MAX_SECONDS,
    STEADY_SHARE,
    SWAYS,
    TRAIL_DEGREES,
    TRAIL_LIMIT,
    TRAIL_SPRING,
    WIND_BOOST,
    WIND_LEVELS,
    Wind,
    bent_points,
    blow_seconds,
    blow_turns,
    blown_point,
    felt_force,
    gust,
    gusty_progress,
    sway_degrees,
    trail_degrees,
    trail_memory_seconds,
    wind_level,
    wind_phase,
)
from vidgen.cli import check_project
from vidgen.particles import KINDS, PARTICLE_KINDS, WIND_DRIFT, particle_seeds, particle_states
from vidgen.project import Project

# ----- the wind (no manim) -----------------------------------------------------------------------


def test_levels() -> None:
    assert [wind_level(name) for name in WIND_LEVELS] == [0.0, 0.3, 0.6, 1.0]
    assert wind_level(0.4) == 0.4 and wind_level("-0.5") == -0.5 and wind_level(1) == 1.0
    for bad, message in ((1.5, "out of range"), ("-2", "out of range"), ("storm", "unknown wind 'storm'")):
        with pytest.raises(ValueError, match=message):
            wind_level(bad)


def test_gusts_are_seeded_smooth_noise() -> None:
    times = np.arange(0.0, 60.0, 0.05)
    a = np.array([gust(t, 7) for t in times])
    assert np.array_equal(a, [gust(t, 7) for t in times])   # the same seed, the same gusts
    assert not np.allclose(a, [gust(t, 8) for t in times])   # another seed, other gusts
    assert a.min() >= 0.0 and a.max() <= 1.0 and a.max() - a.min() > 0.4   # lulls and gusts
    assert np.abs(np.diff(a)).max() < 0.05   # smooth: no jumps between frames 0.05 s apart


def test_fades_and_force() -> None:
    wind = Wind(0.0, seed=3)
    assert wind.force(5.0) == 0.0 and wind.calm() and not wind.blowing(0.0, 100.0)
    wind.change(0.8, 10.0, 2.0)
    assert wind.level(9.9) == 0.0 and wind.level(11.0) == pytest.approx(0.4) and wind.level(12.0) == 0.8
    assert not wind.blowing(0.0, 9.0) and wind.blowing(9.0, 10.5) and wind.blowing(20.0, 30.0)
    for t in np.arange(12.0, 40.0, 0.37):   # between the steady share and the whole level
        assert 0.8 * STEADY_SHARE <= wind.force(t) <= 0.8
    assert wind.force(20.0, delay=0.5) == pytest.approx(0.8 * (STEADY_SHARE + (1 - STEADY_SHARE) * gust(19.5, 3)))
    assert wind.delay(0.0, 20.0) == 0.0 and wind.delay(1.0, 20.0) > 0.0   # gusts reach the right side later
    left = Wind(-0.6, seed=3)
    assert left.force(1.0) < 0.0 and left.delay(1.0, 1.0) == 0.0   # blowing to the left: from the right side


def test_blown_is_the_same_whatever_the_order() -> None:
    a, b = Wind(0.5, seed=2), Wind(0.5, seed=2)
    late = a.blown(0.0, 7.3)
    early = a.blown(0.0, 2.1)
    assert b.blown(0.0, 2.1) == pytest.approx(early, abs=1e-12) and b.blown(0.0, 7.3) == pytest.approx(late, abs=1e-12)
    assert 0.5 * STEADY_SHARE * 7.3 < late < 0.5 * 7.3
    assert a.blown(2.1, 7.3) == pytest.approx(late - early)
    assert Wind(0.0).blown(0.0, 9.0) == 0.0


def test_sway_angles_from_the_seed() -> None:
    wind = Wind(0.7, seed=11)
    phase = wind_phase("tree")
    angles = [sway_degrees("tree", wind.force(t, wind.delay(0.8, t)), t, phase) for t in np.arange(0.0, 20.0, 0.1)]
    again = Wind(0.7, seed=11)
    assert angles == [sway_degrees("tree", again.force(t, again.delay(0.8, t)), t, phase) for t in np.arange(0.0, 20.0, 0.1)]
    other = Wind(0.7, seed=12)
    assert angles != [sway_degrees("tree", other.force(t, other.delay(0.8, t)), t, phase) for t in np.arange(0.0, 20.0, 0.1)]
    top = SWAYS["tree"].degrees * felt_force(0.7) * (1 + 0.25)
    assert all(0.0 < a <= top for a in angles) and max(angles) - min(angles) > 0.5   # leaning right, in gusts
    assert sway_degrees("tree", 0.0, 3.0, phase) == 0.0
    assert sway_degrees("tree", -0.5, 3.0) == -sway_degrees("tree", 0.5, 3.0)   # to the left
    assert SWAYS["plant"].degrees > SWAYS["tree"].degrees > SWAYS["lamp"].degrees
    assert wind_phase("tree") != wind_phase("tree_2")


def test_trailing_follows_the_spring() -> None:
    assert trail_degrees(Wind(0.0), 8.0) == 0.0
    wind = Wind(0.0, seed=4)
    wind.change(1.0, 1.0, 0.0)   # a gale at once
    assert trail_degrees(wind, 1.0) == pytest.approx(0.0, abs=1e-9)   # it lags behind
    lagged = [trail_degrees(wind, 1.0 + k * 0.02) for k in range(150)]
    reach = TRAIL_DEGREES * STEADY_SHARE
    assert max(lagged) > TRAIL_DEGREES * (STEADY_SHARE + (1 - STEADY_SHARE) * 0.3)   # swings past the steady share with gusts
    assert lagged[3] < lagged[10] and lagged[10] > reach * 0.5
    calm = Wind(0.8, seed=4)
    calm.change(0.0, 2.0, 0.0)
    memory = trail_memory_seconds()
    assert memory == pytest.approx(TRAIL_SPRING.memory_seconds) and 1.0 < memory < 5.0
    assert trail_degrees(calm, 2.0 + 0.3) != 0.0 and trail_degrees(calm, 2.0 + memory + 0.01) == 0.0   # still swinging, then exactly still


def test_bent_points() -> None:
    points = np.array([[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 2.0, 0.0], [0.5, 2.0, 0.0]])
    assert np.array_equal(bent_points(points, 0.0, 0.0, 2.0), points)
    bent = bent_points(points, 10.0, 0.0, 2.0)
    assert bent[0].tolist() == [0.0, 0.0, 0.0]   # the base stays
    assert bent[2, 0] == pytest.approx(math.tan(math.radians(10.0)) * 2.0) and bent[1, 0] == pytest.approx(bent[2, 0] / 4)   # bends, the top most
    assert np.array_equal(bent[:, 1], points[:, 1])
    pot = bent_points(points, 10.0, 0.0, 2.0, bend_from=0.5)
    assert pot[1, 0] == 0.0 and pot[2, 0] == pytest.approx(math.tan(math.radians(10.0)) * 1.0)   # straight up to half way


def test_particles_drift_with_the_wind() -> None:
    seeds = particle_seeds("snow", 40, 3)
    plain = particle_states(seeds, 2.0, 1.6, 0.9)
    calm = particle_states(seeds, 2.0, 1.6, 0.9, blown=0.0, wind=0.0)
    assert all(np.array_equal(getattr(plain, f), getattr(calm, f)) for f in ("x", "y", "size", "angle", "opacity"))
    blown = particle_states(seeds, 2.0, 1.6, 0.9, blown=1.5, wind=0.7)
    shift = np.mod(blown.x - plain.x, 1.0)
    assert shift == pytest.approx(np.mod(WIND_DRIFT["snow"] * np.abs(seeds.speed) * 1.5 / 1.6, 1.0))
    rain = particle_seeds("rain", 10, 3)
    assert particle_states(rain, 1.0, blown=1.0, wind=0.8).angle[0] > particle_states(rain, 1.0).angle[0]   # slants more


def _mean_and_max(values: list[float]) -> tuple[float, float]:
    a = np.abs(values)
    return float(a.mean()), float(a.max())


def test_strong_wind_shows_clearly() -> None:
    """Step 104 (Backlog "wind barely visible"): measured over 30 s. Before, a tree leaned 2.1° on
    average at windy and 3.6° at a gale, a scarf's end turned 12.5° / 20.9°."""
    assert felt_force(0.0) == 0.0 and felt_force(1.0) == 1.0 + WIND_BOOST and felt_force(-0.5) == -felt_force(0.5)
    times = np.arange(0.0, 30.0, 0.05)
    found = {}
    for name in ("breeze", "windy", "gale"):
        wind = Wind(WIND_LEVELS[name], seed=5)
        tree = [sway_degrees("tree", wind.force(t, wind.delay(0.5, t)), t, wind_phase("tree")) for t in times]
        trail = [trail_degrees(wind, t, phase=wind_phase("dot")) for t in times[40:]]
        found[name] = (_mean_and_max(tree), _mean_and_max(trail))
    assert found["breeze"][0][0] < 3.0   # a breeze stays gentle
    assert found["windy"][0][0] > 5.0 and found["gale"][0][0] > 12.0 and found["gale"][0][1] < 30.0
    assert found["windy"][1][0] * TRAIL_WEIGHTS["scarf"] > 20.0 and found["gale"][1][0] * TRAIL_WEIGHTS["scarf"] > 40.0
    assert found["gale"][1][1] < TRAIL_LIMIT   # softly limited: never over the head


def test_leaves_tumble_and_streaks_show_only_in_wind() -> None:
    assert PARTICLE_KINDS[:7] == ("rain", "snow", "sparkles", "dust", "confetti", "smoke", "bubbles")   # their streams unchanged
    leaves = particle_seeds("leaves", 20, 3, colors=3)
    assert not np.allclose(particle_states(leaves, 0.0).angle, particle_states(leaves, 0.4).angle)   # tumbling
    blown = particle_states(leaves, 2.0, blown=1.0, wind=0.6)
    assert np.mod(blown.x - particle_states(leaves, 2.0).x, 1.0) == pytest.approx(np.mod(WIND_DRIFT["leaves"] * leaves.speed * 1.0, 1.0))
    streaks = particle_seeds("streaks", 30, 3)
    shown = KINDS["streaks"].wind_shown
    assert particle_states(streaks, 2.0).opacity.max() == 0.0   # calm: none
    assert particle_states(streaks, 2.0, blown=0.2, wind=shown).opacity.max() == 0.0   # a light breeze: none
    gusty = particle_states(streaks, 2.0, blown=1.0, wind=0.7)
    assert gusty.opacity.max() > 0.3 and gusty.angle == pytest.approx(np.full(30, math.pi / 2))   # lying along the wind
    assert particle_states(streaks, 2.0, blown=1.0, wind=-0.7).angle == pytest.approx(np.full(30, -math.pi / 2))


def test_blown_path_is_seeded_gusty_and_ends_upright() -> None:
    shares = np.linspace(0.0, 1.0, 101)
    progress = [gusty_progress(s, 7) for s in shares]
    assert progress[0] == 0.0 and progress[-1] == pytest.approx(1.0) and np.all(np.diff(progress) >= 0.0)   # never back
    steps = np.diff(progress)
    assert steps.max() > 1.5 * steps.min()   # surges and lulls, not an even speed
    assert progress != [gusty_progress(s, 8) for s in shares]   # another seed, other gusts
    start, end = (-2.0, -1.0), (7.0, -2.5)
    points = [blown_point(s, start, end, rise=1.0, seed=7) for s in shares]
    assert points == [blown_point(s, start, end, rise=1.0, seed=7) for s in shares]   # pure
    assert points[0] == pytest.approx((-2.0, -1.0, 0.0)) and points[-1][:2] == pytest.approx(end)
    assert points[-1][2] == pytest.approx(-360.0 * blow_turns(9.0)) and blow_turns(9.0) == 3   # whole turns, clockwise to the right: upright
    for share, (x, y, _) in zip(progress, points):
        assert y >= -1.0 + (-2.5 + 1.0) * share - 1e-9   # never under the straight line (the ground)
    assert max(y for _, y, _ in points) > -1.0 + 0.5   # lifted
    left = blown_point(1.0, (0.0, 0.0), (-4.0, 0.0), rise=0.5)
    assert left[2] == pytest.approx(360.0 * blow_turns(4.0))   # counterclockwise to the left
    assert blow_seconds(10.0, 1.0) < blow_seconds(10.0, 0.6) < blow_seconds(10.0, 0.3)   # faster in a stronger wind
    assert blow_seconds(1e6, 1.0) == BLOW_MAX_SECONDS and blow_seconds(0.0, 0.0) > 0.0


def test_blow_away_in_the_holdings_replay() -> None:
    holdings = Holdings()
    holdings.take("pip", "napkin")
    assert holdings.drop("napkin") == ("pip", "left") and holdings.hands("pip") == {} and holdings.drop("napkin") is None
    chars = {"pip": (-4.0, 3.6), "kit": (4.0, 3.6)}

    def problems(*steps: tuple[str, str, dict[str, Any]]) -> list[tuple[str, str]]:
        made = [HandlingStep(f"beats[0].actions[{k}]", action, (who,), options) for k, (action, who, options) in enumerate(steps)]
        place = {"centre": 0.0, "left": -4.0, "right": 4.0}
        return holding_problems(made, characters=chars, props={"napkin": -3.5, "box": -3.0}, place_x=lambda p: place.get(p) if isinstance(p, str) else (p - 0.5) * 16,
                                to_fraction=lambda x: x / 16 + 0.5)

    (empty,) = problems(("hold", "pip", {"to": "napkin"}), ("blow_away", "napkin", {}), ("put_down", "pip", {}))
    assert empty == ("beats[0].actions[2].target", "pip holds no prop then; pick_up one first")   # out of its hand
    (gone,) = problems(("blow_away", "napkin", {}), ("walk_to", "pip", {"to": "right"}), ("pick_up", "pip", {"to": "napkin"}))
    assert gone == ("beats[0].actions[2].to", "'napkin' blew away off stage (beats[0].actions[0]); blow it to: a mark instead to use it again")
    (again,) = problems(("blow_away", "napkin", {}), ("blow_away", "napkin", {"to": "left"}))
    assert again[0] == "beats[0].actions[1].target" and "blew away off stage" in again[1]
    assert problems(("hold", "pip", {"to": "napkin"}), ("blow_away", "napkin", {"to": "right"}), ("pick_up", "kit", {"to": "napkin"})) == []   # landed by kit
    (far,) = problems(("blow_away", "napkin", {"to": "right"}), ("pick_up", "pip", {"to": "napkin"}))
    assert "2.2 of its heights from 'napkin'" in far[1]   # it lies where it landed
    (seat,) = problems(("sit_on", "pip", {"to": "box"}), ("blow_away", "box", {}))
    assert seat[1].startswith("pip sits on 'box' then")


# ----- characters (no render) --------------------------------------------------------------------


def test_trailing_pieces_of_generated_looks() -> None:
    plain = generated(body="round", hair="short", ears="round")
    assert not plain.has_trails
    before = [m.points.copy() for m in plain.family_members_with_points()]
    plain.set_wind(15.0)
    assert all(np.array_equal(a, m.points) for a, m in zip(before, plain.family_members_with_points()))

    dot = generated(body="round", hair="long", ears="floppy", accessories=["scarf", "hat"])
    assert dot.has_trails
    trailing = [m for m in dot.family_members_with_points() if getattr(m, TRAIL_ATTRIBUTE, None) is not None]
    assert {round(getattr(m, TRAIL_ATTRIBUTE)[2], 2) for m in trailing} == {TRAIL_WEIGHTS[k] for k in ("scarf", "long", "floppy", "hat")}
    for facing in ("right", "left"):
        dot.face(facing).set_wind(0.0)
        rest = {id(m): m.points.copy() for m in dot.family_members_with_points()}
        dot.set_wind(12.0)
        for m in dot.family_members_with_points():
            moved = not np.allclose(rest[id(m)], m.points)
            assert moved == (getattr(m, TRAIL_ATTRIBUTE, None) is not None), facing
        for m in trailing:   # hanging (scarf, hair, ears) or standing (hat): blown to the right on screen
            assert m.points[:, 0].mean() > rest[id(m)][:, 0].mean(), (facing, getattr(m, TRAIL_ATTRIBUTE))
        dot.set_wind(0.0)
        assert all(np.array_equal(rest[id(m)], m.points) for m in dot.family_members_with_points())   # 0: as drawn
    dot.set_wind(9.0)
    assert dot.state().parts == generated(body="round", hair="long", ears="floppy", accessories=["scarf", "hat"]).state().parts   # not a pose


# ----- validate ----------------------------------------------------------------------------------


def wind_project(make_project, actions: list[Any], *, scene_type: str = "stage", params: dict[str, Any] | None = None) -> Project:
    params = {"characters": ["pip"], **(params or {})} if scene_type == "stage" else {"text": "Hello"}
    scenes = [{"id": "s", "type": scene_type, "params": params, "beats": [{"text": "The wind picks up.", "actions": actions}]}]
    return Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))


def test_validate_wind_actions_and_param(make_project) -> None:
    good = [{"wind": 0.8, "run_time": 3}, {"wind": "calm", "at": 0.5}, {"action": "wind", "target": "-0.4", "at": 0.7}]
    assert check_project(wind_project(make_project, good, params={"wind": "breeze"})) == []
    where = "scenes[0].beats[0].actions[0]"
    cases = [
        ({"wind": "gail"}, f"{where}.target: unknown wind 'gail'; a number from -1 to 1 or calm, breeze, windy, gale; did you mean 'gale'?"),
        ({"wind": 2}, f"{where}.target: wind 2 is out of range"),
        ({"action": "wind"}, f"{where}.target: how strong?"),
    ]
    for action, start in cases:
        problems = check_project(wind_project(make_project, [action]))
        assert problems and all(p.startswith(start) for p in problems), (action, problems)
    problems = check_project(wind_project(make_project, [{"wind": 0.5}], scene_type="text_card"))
    assert problems == [f"{where}.action: wind is for stage scenes; a TextCard scene has nothing to blow"]
    assert stage_params().wind == 0.0 and stage_params(wind=-0.3).wind == -0.3 and stage_params(wind="gale").wind == "gale"
    for bad in (1.5, "storm"):
        with pytest.raises(Exception, match="wind"):
            stage_params(wind=bad)


def test_schema_takes_a_number_for_wind() -> None:
    from vidgen.schema import config_schema

    extensions.load_builtins()
    schema = config_schema(registry.all(), [])
    shorthands = {s["title"]: s for s in schema["$defs"]["ActionShorthand"]["anyOf"]}
    assert {"type": "number"} in shorthands["wind (shorthand)"]["properties"]["wind"]["anyOf"]
    assert {"type": "number"} not in shorthands["light (shorthand)"]["properties"]["light"]["anyOf"]


def test_validate_blow_away(make_project) -> None:
    from test_cartoon_holding import prop_project

    props = [{"prop": "napkin", "at": 0.3}, "tree", {"prop": "umbrella", "at": 0.6}]
    good = prop_project(make_project, [{"text": "The wind takes the napkin.", "actions": [
        {"wind": "windy"}, {"blow_away": "napkin", "at": 0.3}, {"blow_away": "umbrella", "to": "far_right", "at": 0.5},
    ]}], props)
    assert check_project(good) == []
    where = "scenes[0].beats[0].actions"
    calm = prop_project(make_project, [{"text": "Nothing blows.", "actions": [{"blow_away": "napkin"}, {"blow_away": "umbrella", "to": 0.9}]}], props)
    assert check_project(calm) == [f"{where}[0].target: the wind is calm then, so nothing blows it off stage: add a wind action before it "
                                   "(- wind: windy) or the stage's wind:, or give to: a mark"]
    bad = prop_project(make_project, [{"text": "Hello.", "actions": [{"wind": "gale"}, {"blow_away": "tree"}, {"blow_away": "pip"},
                                                                     {"blow_away": "napkin", "to": "nowhere"}]}], props)
    problems = check_project(bad)
    assert f"{where}[1].target: 'tree' (tree) is too heavy to blow away (props that can: ball, basket, box, cup, napkin, umbrella, or an svg prop)" in problems
    assert f"{where}[2].target: 'pip' is not a prop; blow_away acts on props (- blow_away: <prop>)" in problems
    assert any(p.startswith(f"{where}[3].to: unknown mark 'nowhere'") for p in problems), problems
    held = prop_project(make_project, [
        {"text": "Pip holds the napkin.", "actions": [{"hold": "pip", "to": "napkin"}, {"wind": "gale", "at": 0.5}]},
        {"text": "It blows away, and Pip puts it down.", "actions": [{"blow_away": "napkin"}, {"put_down": "pip", "at": 0.5}]},
    ], props)
    assert check_project(held) == [f"scenes[0].beats[1].actions[1].target: pip holds no prop then; pick_up one first"]


def test_blow_away_out_of_a_hand_on_a_fake_stage() -> None:
    from test_cartoon_acting import run, target, use
    from test_cartoon_holding import stage
    from vidgen.cartoon.transition import ArmMove, PropMove

    scene, pip, kit, cup = stage()
    scene.frame_height = 9.0
    scene.blowing, scene.renderer = SimpleNamespace(wind=Wind(-1.0)), SimpleNamespace(time=0.0)   # a gale to the left
    rest = pip.state()
    run(use("hold", to="cup").apply(scene, [target("pip", pip)]))
    assert pip.holding == {"left": "cup"} and scene.holdings.holder("cup") == ("pip", "left")
    blow = use("blow_away", "cup")
    hand = float(pip.hand_point("left")[0])
    assert blow_seconds(hand + 8.0, -1.0) < blow.run_time_for(scene, [target("cup", cup)]) < blow_seconds(hand + 9.5, -1.0)
    anims = blow.apply(scene, [target("cup", cup)])
    assert [type(a) for a in anims] == [ArmMove, PropMove]
    assert scene.holdings.holder("cup") is None and pip.holding == {} and cup.held_by is None and not cup.updaters
    run(anims)
    assert pip.pose_of("arm_left") == rest.parts["arm_left"]   # the empty arm back down
    assert cup.get_right()[0] < -8.0 and cup.height == pytest.approx(0.3, rel=1e-3)   # off the stage, downwind

    scene, pip, kit, cup = stage()
    scene.frame_height, scene.grounds = 9.0, {"cup": -2.0}
    run(use("blow_away", "cup", to="right").apply(scene, [target("cup", cup)]))
    assert cup.feet()[0] == pytest.approx(4.0, abs=1e-6) and cup.feet()[1] == pytest.approx(-2.0, abs=1e-6)   # lands on the mark, upright
    assert cup.height == pytest.approx(0.3, rel=1e-3)


# ----- render ------------------------------------------------------------------------------------

WINDY_SET = {
    "background": ["#9CCBEA", "#E4F3FB"], "idle": False,
    "characters": [{"name": "dot", "at": "left"}, {"name": "pip", "at": "right"}],
    "props": [{"prop": "tree", "at": 0.85, "depth": 0.4}, {"prop": "house", "at": 0.15, "depth": 0.6}, "bush"],
    "particles": [{"kind": "snow", "density": 0.5}],
}
DOT = {"name": "dot", "look": {"body": "round", "hair": "long", "accessories": ["scarf", "hat"]}}


def windy_project(make_project, params: dict[str, Any], actions: list[Any] | None = None) -> Project:
    beats = [{"id": "b1", "text": "The wind blows over the hill.", "actions": actions or []}, {"id": "b2", "text": "Then it is calm."}]
    scenes = [{"id": "hill", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=[DOT, *CAST], voices=VOICES, scenes=scenes)))


def frame_hashes(project: Project, media: Path, monkeypatch) -> tuple[Any, list[str]]:
    """Render the scene ``hill`` at 160x90 and hash every frame written to the movie."""
    from manim.scene.scene_file_writer import SceneFileWriter

    hashes: list[str] = []
    write = SceneFileWriter.write_frame

    def recording(self: Any, frame: Any, num_frames: int = 1) -> None:
        hashes.extend([hashlib.sha1(np.asarray(frame).tobytes()).hexdigest()] * num_frames)
        write(self, frame, num_frames)

    monkeypatch.setattr(SceneFileWriter, "write_frame", recording)
    scene, _ = render_with_layout(project, "hill", media)
    monkeypatch.setattr(SceneFileWriter, "write_frame", write)
    return scene, hashes


@pytest.mark.render
def test_wind_zero_changes_nothing(make_project, tmp_path: Path, monkeypatch) -> None:
    plain, plain_frames = frame_hashes(windy_project(make_project, dict(WINDY_SET)), tmp_path / "a", monkeypatch)
    calm, calm_frames = frame_hashes(windy_project(make_project, {**WINDY_SET, "wind": 0}, [{"wind": "calm", "at": 0.5}]), tmp_path / "b", monkeypatch)
    assert plain.blowing is None and calm.blowing is None and calm.particle_wind is None   # nothing installed
    assert len(plain_frames) > 10 and calm_frames == plain_frames   # pixel for pixel


@pytest.mark.render
def test_windy_stage_sways_trails_and_calms_down(make_project, tmp_path: Path, monkeypatch) -> None:
    from vidgen.cartoon.windblown import SwayingProp

    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    params = {**WINDY_SET, "wind": "gale"}
    project = windy_project(make_project, params, [{"wind": 0, "at": 0.3, "run_time": 0.4}])
    scene, frames = frame_hashes(project, tmp_path / "media", monkeypatch)
    blowing = scene.blowing
    assert blowing is not None and scene.particle_wind is not None
    assert [p.prop.name for p in blowing.props] == ["tree", "bush"]   # the house does not sway
    assert set(blowing.characters) == {"dot"}   # pip has nothing to trail
    assert all(isinstance(p, SwayingProp) for p in blowing.props) and scene.particles[0].wind is not None

    # calm by the end and the spring's memory over: every piece back as drawn, no updater, static set
    now = float(scene.renderer.time)
    assert now > blowing.wind.changes[0].end + trail_memory_seconds(), (now, blowing.wind.changes)
    tree = blowing.props[0].prop
    assert tree not in scene.get_moving_mobjects()
    assert scene._wind_updater not in scene.updaters
    for item in blowing.props:
        assert item.degrees == 0.0 and all(np.array_equal(m.points, rest) for m, rest in item.rest)
    assert scene.cast["dot"].wind == 0.0

    # gusts again: the tree and dot leave the static set while it blows
    scene.change_wind(0.8, now + 0.1, 0.5)
    assert scene._wind_updater in scene.updaters
    moving = scene.get_moving_mobjects()
    assert tree in moving and scene.cast["dot"] in moving
    background = next(m for m in scene.mobjects if getattr(m, "name", None) == "background")
    assert background not in moving   # the sky stays in the static image
    blowing.update(now + 1.0)
    assert blowing.props[0].degrees > 0.0 and scene.cast["dot"].wind != 0.0
    assert len(frames) > 10


@pytest.mark.render
def test_a_gust_blows_the_umbrella_out_of_a_hand(make_project, tmp_path: Path) -> None:
    """Step 104: pip holds the open umbrella; a gale blows it out of the hand and off the stage
    (the dump says nobody holds it); the napkin blows to a mark and lands upright."""
    from test_cartoon_holding import prop_project
    from vidgen.introspect import LayoutRecorder

    project = prop_project(make_project, [
        {"text": "Pip holds the umbrella up.", "voice": "pip_voice", "actions": [{"hold": "pip", "to": "umbrella"}, {"wind": "gale", "run_time": 0.2}]},
        {"text": "A gust takes it away.", "voice": "kit_voice", "actions": [{"blow_away": "umbrella"}, {"blow_away": "napkin", "to": 0.8, "at": 0.3}]},
    ], [{"prop": "umbrella", "at": 0.3, "open": True}, {"prop": "napkin", "at": 0.5}])
    recorder = LayoutRecorder()
    scene, _ = render_with_layout(project, "park", tmp_path / "media", recorder)
    ends = [f for f in recorder.frames if "mid" not in f]
    first = {o["name"]: o for o in ends[0]["objects"] if o["name"]}
    assert first["umbrella"]["held_by"] == "pip" and first["pip"]["holding"] == {"left": "umbrella"}
    assert any(f.get("mid", "").startswith("blow_away") for f in recorder.frames)   # a mid-gust still
    last = {o["name"]: o for o in ends[-1]["objects"] if o["name"]}
    assert "held_by" not in last["umbrella"] and "holding" not in last["pip"] and scene.holdings.holder("umbrella") is None
    left, right = scene.camera_bounds()[:2]
    assert scene.props["umbrella"].get_left()[0] > right   # gone downwind
    napkin = scene.props["napkin"]
    assert napkin.feet()[0] == pytest.approx(left + 0.8 * (right - left), abs=1e-6) and napkin.feet()[1] == pytest.approx(scene.grounds["napkin"], abs=1e-6)
