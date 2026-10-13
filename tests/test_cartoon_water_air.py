"""Step 119: vehicles on the water and in the air (DESIGN.md §69.53): the boat on the stage's
water, the hot-air balloon and the toy rocket; their pure paths, waves, bobbing and smoke, the
wind's drift, riders following, the checks of ``vidgen validate``, foley and motion effects, and
one tiny render."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_acting import VOICES, figure, target, use
from test_cartoon_moving import StageFake
from test_cartoon_stage import CAST, render_with_layout
from vidgen import extensions, registry, sfx
from vidgen.cartoon.foley import PlayedAction, foley_cues
from vidgen.cartoon.holding import HandlingStep, holding_problems
from vidgen.cartoon.motion_effects import SMOKE_SECONDS, motion_effect_cues
from vidgen.cartoon.props import PROP_HEIGHTS, PROP_SHAPES, draw_prop
from vidgen.cartoon.riding import Ride, RiderSeat, place_rider, riding_state, seat_point
from vidgen.cartoon.vehicle_paths import (
    BALLOON_RISE_SHARE,
    BOB_DEGREES,
    BOB_HEIGHT,
    SMOKE_BURST,
    WAVE_HEIGHT,
    Course,
    balloon_point,
    balloon_seconds,
    boat_bob,
    chute_open,
    front_outline,
    rocket_point,
    rocket_seconds,
    smoke_puffs,
    wave_offset,
)
from vidgen.cartoon.vehicles import AIR_VEHICLES, ROCKET_ASCENT_SHARE, VEHICLES, WATER_VEHICLES, medium, seat_count
from vidgen.cli import check_project
from vidgen.project import Project
from vidgen.theme import Theme

START, END = (-3.0, -2.0), (3.0, -2.0)


# ----- the vehicles (no render) ------------------------------------------------------------------


def test_water_and_air_vehicles() -> None:
    assert WATER_VEHICLES == ("boat",) and AIR_VEHICLES == ("hot_air_balloon", "toy_rocket")
    assert [medium(k) for k in ("car", "boat", "hot_air_balloon", "toy_rocket")] == ["ground", "water", "air", "air"]
    assert [seat_count(k) for k in ("boat", "hot_air_balloon", "toy_rocket")] == [2, 2, 0]
    assert VEHICLES["hot_air_balloon"].stands and not VEHICLES["boat"].stands
    assert VEHICLES["boat"].hides_legs and VEHICLES["hot_air_balloon"].hides_legs and VEHICLES["boat"].wheels == ()


@pytest.mark.parametrize("kind", ("boat", "hot_air_balloon", "toy_rocket"))
def test_each_draws_with_its_feet_at_its_origin(kind: str) -> None:
    prop = draw_prop(kind, height=2.0, theme=Theme(), facing="left").shift([1.0, -1.0, 0.0])
    assert prop.height == pytest.approx(2.0) and prop.feet() == pytest.approx(prop.prop_point(0.0, 0.0))
    assert prop.unit == pytest.approx(2.0)
    for place in range(seat_count(kind)):   # the seats are inside the vehicle
        assert prop.get_left()[0] < seat_point(prop, place)[0] < prop.get_right()[0]


def test_a_toy_rocket_opens_its_parachute() -> None:
    rocket = draw_prop("toy_rocket", height=1.0, theme=Theme())
    assert rocket.shapes == PROP_SHAPES["toy_rocket"] == ("folded", "chute") and rocket.shape == "folded"
    rocket.show_shape("chute")
    assert rocket.height > 2.0 and rocket.feet()[1] == pytest.approx(0.0)


def test_pose_at_sets_place_and_turn_afresh() -> None:
    boat = draw_prop("boat", height=1.0, theme=Theme())
    boat.pose_at(2.0, 1.0, 10.0)
    boat.pose_at(2.0, 1.5, -5.0)
    assert boat.tilt == -5.0 and boat.prop_point(0.0, 0.0) == pytest.approx([2.0, 1.5, 0.0])
    tip = boat.prop_point(0.0, 1.0) - boat.prop_point(0.0, 0.0)
    assert math.degrees(math.atan2(-tip[0], tip[1])) == pytest.approx(-5.0)   # turned 5° clockwise, no more
    boat.pose_at(0.0, 0.0)
    assert boat.tilt == 0.0 and boat.prop_point(0.0, 1.0) == pytest.approx([0.0, 1.0, 0.0])


# ----- the water (no render) ---------------------------------------------------------------------


def test_waves_and_bobbing_are_small_and_seeded() -> None:
    values = [wave_offset(x / 7.0, t / 3.0) for x in range(-20, 20) for t in range(12)]
    assert max(abs(v) for v in values) <= WAVE_HEIGHT + 1e-9 and max(values) > 0.5 * WAVE_HEIGHT
    assert wave_offset(0.3, 1.0) == wave_offset(0.3, 1.0) and wave_offset(0.3, 1.0, sign=-1.0) != wave_offset(0.3, 1.0)
    bobs = [boat_bob(t / 10.0, 0.4) for t in range(60)]
    assert max(abs(r) for r, _ in bobs) <= BOB_HEIGHT and max(abs(d) for _, d in bobs) <= BOB_DEGREES
    assert boat_bob(1.0, 0.0) != boat_bob(1.0, 1.0)   # two boats do not bob in step


def test_the_front_strip_has_a_wavy_top_under_the_surface() -> None:
    outline = front_outline(-4.0, 2.0, 0.0, -5.0, 0.5, 1.0, steps=24)
    assert outline[0] == (-4.0, -5.0) and outline[1] == (2.0, -5.0) and len(outline) == 2 + 25
    tops = [y for _, y in outline[2:]]
    assert max(tops) < 0.0 and max(tops) - min(tops) > 0.01


# ----- the paths (no render) ---------------------------------------------------------------------------


def test_a_balloon_rises_cruises_and_lands() -> None:
    altitude = 2.0
    assert balloon_point(0.0, START, END, altitude=altitude)[:2] == pytest.approx(START)
    assert balloon_point(1.0, START, END, altitude=altitude)[:2] == pytest.approx(END)
    top = balloon_point(BALLOON_RISE_SHARE, START, END, altitude=altitude)
    assert top[1] == pytest.approx(START[1] + altitude, abs=0.15) and top[2] == 0.0
    early = balloon_point(0.1, START, END, altitude=altitude)
    assert early[1] - START[1] > 3.0 * (early[0] - START[0])   # it goes up more than across at first
    assert balloon_point(0.4, START, END, altitude=altitude, seed=2) == balloon_point(0.4, START, END, altitude=altitude, seed=2)


def test_the_wind_blows_a_balloon_aside_on_the_way() -> None:
    calm = balloon_point(0.5, START, END, altitude=2.0)
    blown = balloon_point(0.5, START, END, altitude=2.0, drift=1.0)
    assert blown[0] - calm[0] == pytest.approx(1.0) and blown[1] == pytest.approx(calm[1])
    assert balloon_point(1.0, START, END, altitude=2.0, drift=1.0)[:2] == pytest.approx(END)   # it still lands there
    left = balloon_point(0.5, START, END, altitude=2.0, drift=-1.0)
    assert left[0] < calm[0]


def test_a_balloon_that_flies_away_keeps_rising() -> None:
    away = (2.0, 9.0)
    ys = [balloon_point(s / 10.0, START, away, altitude=2.0, land=False)[1] for s in range(11)]
    assert ys[-1] == pytest.approx(9.0) and all(b >= a - 0.1 for a, b in zip(ys, ys[1:]))


def test_a_toy_rocket_arcs_up_then_floats_down_under_its_parachute() -> None:
    apex = 3.0
    x0, y0, turn0 = rocket_point(0.0, START, END, apex=apex)
    assert (x0, y0, turn0) == pytest.approx((*START, 0.0))   # it leaves the ground upright
    top = rocket_point(ROCKET_ASCENT_SHARE, START, END, apex=apex)
    assert top[1] == pytest.approx(START[1] + apex) and top[2] == pytest.approx(-90.0)   # its nose along the way, level at the top
    climbing = rocket_point(0.5 * ROCKET_ASCENT_SHARE, START, END, apex=apex)
    assert -90.0 < climbing[2] < 0.0   # leaning to the right, where it goes
    land = rocket_point(1.0, START, END, apex=apex)
    assert land == pytest.approx((*END, 0.0))   # upright on the ground
    near = rocket_point(0.97, START, END, apex=apex)
    assert abs(near[1] - END[1]) < 0.05 * apex   # it slows down to touch down softly
    assert not chute_open(0.2, True) and chute_open(0.5, True) and not chute_open(0.5, False)


def test_a_toy_rocket_flying_away_points_where_it_goes() -> None:
    away = (2.0, 9.0)
    assert rocket_point(0.0, START, away, apex=3.0, land=False)[2] == pytest.approx(0.0)
    x, y, turn = rocket_point(1.0, START, away, apex=3.0, land=False)
    assert (x, y) == pytest.approx(away) and turn < -10.0


def test_a_course_on_the_ground_or_water_eases_like_a_walk() -> None:
    course = Course("boat", START, END)
    assert course.at(0.0)[:2] == pytest.approx(START) and course.at(1.0) == pytest.approx((*END, 0.0))
    assert course.at(0.05)[0] - START[0] < 0.05 * (END[0] - START[0])   # speeding up
    assert not course.flies and Course("hot_air_balloon", START, END).flies
    assert Course("toy_rocket", START, END, 3.0).powered() == ROCKET_ASCENT_SHARE and course.powered() == 0.0


def test_flight_seconds() -> None:
    assert balloon_seconds(6.0, 2.0, 1.0) == pytest.approx(10.0)
    assert rocket_seconds(4.0, 2.0, 4.0) > rocket_seconds(4.0, 2.0, 4.0, land=False)


def test_smoke_bursts_then_trails_the_rocket_and_fades() -> None:
    course = Course("toy_rocket", START, END, 3.0)
    burst = [p for p in smoke_puffs(0.2, course, 3.0, 1.0, seed=4) if abs(p.y - START[1]) < 0.5]   # on the ground where it set off
    assert min(p.x for p in burst) < START[0] < max(p.x for p in burst)   # rolling out both ways
    later = smoke_puffs(0.9, course, 3.0, 1.0, seed=4)
    assert any(p.y > START[1] + 1.0 for p in later)   # the trail up its arc
    assert smoke_puffs(0.9, course, 3.0, 1.0, seed=4) == later
    assert smoke_puffs(ROCKET_ASCENT_SHARE * 3.0 + SMOKE_SECONDS + 0.2, course, 3.0, 1.0) == []
    assert len(smoke_puffs(0.05, Course("toy_rocket", START, END, 3.0), 3.0, 1.0)) <= SMOKE_BURST


# ----- riders and rides (manim objects, no render) ----------------------------------------------------------


def _vehicle(kind: str, unit: float, x: float = 0.0) -> Any:
    prop = draw_prop(kind, height=PROP_HEIGHTS[kind] * unit, theme=Theme(), character_height=unit).shift([x, -2.0, 0.0])
    prop.height_factor = PROP_HEIGHTS[kind]
    return prop


def test_riders_stand_in_a_balloon_and_fly_with_it() -> None:
    pip = figure()
    balloon = _vehicle("hot_air_balloon", pip.character_height, x=-2.0)
    before = pip.state()
    assert riding_state(pip, balloon, 0, before) is before   # standing: the basket hides its legs
    seat = RiderSeat(pip, balloon, 0, pip.character_height / balloon.unit)
    place_rider(seat)
    ride = Ride(balloon, 3.0, seats=[seat], rise=2.0, drift=0.5, seed=5)
    ride.begin()
    ride.interpolate(0.5)
    assert balloon.prop_point(0.0, 0.0)[1] > -2.0 + 1.5 and pip.feet() == pytest.approx(seat_point(balloon, 0))
    ride.interpolate(1.0)
    assert balloon.prop_point(0.0, 0.0) == pytest.approx([3.0, -2.0, 0.0]) and pip.feet() == pytest.approx(seat_point(balloon, 0))
    assert balloon.flight[0] is ride.course and ride.flies


def test_a_rocket_ride_opens_and_folds_its_parachute() -> None:
    rocket = _vehicle("toy_rocket", 1.0, x=-2.0)
    ride = Ride(rocket, 2.0, rise=2.0)
    ride.begin()
    ride.interpolate(0.6)
    assert rocket.shape == "chute"
    ride.interpolate(1.0)
    assert rocket.shape == "folded" and rocket.tilt == pytest.approx(0.0)


def test_a_boat_rides_from_where_it_rests() -> None:
    boat = _vehicle("boat", 1.0, x=-1.0)
    boat.afloat = (-1.0, -2.0)
    boat.pose_at(-1.0, -1.98, 2.0)   # bobbing
    ride = Ride(boat, 1.5)
    assert ride.course.start == (-1.0, -2.0)
    ride.begin()
    ride.interpolate(1.0)
    assert boat.afloat == pytest.approx((1.5, -2.0)) and boat.tilt == 0.0


def test_the_wind_takes_a_balloon_downwind_and_a_flight_stays_in_the_frame() -> None:
    from types import SimpleNamespace

    from vidgen.cartoon.wind import Wind

    balloon = _vehicle("hot_air_balloon", 1.0, x=-4.0)
    balloon.name = "balloon"
    scene = StageFake(balloon=balloon)
    scene.renderer = SimpleNamespace(time=0.0)
    scene.blowing = SimpleNamespace(wind=Wind(0.6))
    scene._riders = {}
    (ride,) = use("ride_to", target="balloon", to=0.75).apply(scene, [target("balloon", balloon)])
    assert ride.drift > 0.0 and ride.course.land
    frame_top = float(scene.camera.frame.get_top()[1])
    assert -2.0 + ride.rise + balloon.unit < frame_top   # its top stays in the frame
    scene.blowing = SimpleNamespace(wind=Wind(-0.6))
    (ride,) = use("ride_to", target="balloon", to=0.75, land=False).apply(scene, [target("balloon", balloon)])
    assert ride.drift < 0.0 and ride.away_y > frame_top


# ----- who goes where (no manim) ------------------------------------------------------------------------


def _replay(steps: list[HandlingStep]) -> dict[str, str]:
    vehicles = {"boat": ("boat", 1.2), "balloon": ("hot_air_balloon", 4.2), "car": ("car", 2.2)}
    problems = holding_problems(steps, characters={"pip": (0.0, 2.0), "kit": (0.5, 2.0)}, props={"boat": 0.0, "balloon": 0.5, "car": -3.0},
                                place_x=lambda p: float(p) if p is not None else None, to_fraction=lambda x: x, vehicles=vehicles, water=(-1.0, 4.0))
    return dict(problems)


def test_validate_water_and_air_rides() -> None:
    def step(k: int, action: str, target: str, **options: Any) -> HandlingStep:
        return HandlingStep(f"a[{k}]", action, (target,), options)

    messages = _replay([
        step(0, "ride_to", "boat", to=6.0),                       # off the water
        step(1, "ride_to", "boat", to={"mark": 1.0, "depth": 0.4}),
        step(2, "ride_to", "car", to=-2.0, land=False),
        step(3, "get_in", "kit", to="balloon"),
        step(4, "ride_to", "balloon", to=2.0, land=False),
        step(5, "walk_to", "kit", to=1.0),                        # it flew away with the balloon
        step(6, "ride_to", "balloon", to=1.0),
    ])
    assert messages["a[0].to"] == "'boat' floats on the water, from -1.00 to 4.00; ride it to an x there"
    assert messages["a[1].depth"] == "'boat' (boat) keeps its depth; only vehicles on the ground ride in depth"
    assert messages["a[2].land"].startswith("'car' (car) cannot fly away")
    assert "a[3].to" not in messages and "a[4].target" not in messages
    assert messages["a[5].target"] == "'kit' flew away out of the frame (a[4]); it is gone for the scene"
    assert messages["a[6].target"].startswith("'balloon' flew away out of the frame")
    assert len(messages) == 5


def street(make_project, params: dict[str, Any], beats: list[dict[str, Any]]) -> Project:
    scenes = [{"id": "lake", "type": "stage", "params": {"idle": False, **params}, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))


def test_the_stage_checks_water_and_rooms() -> None:
    extensions.load_builtins()
    stage = registry.get("stage").cls
    ok = stage.validate_params({"water": True, "props": [{"prop": "boat", "at": 0.5}]})
    assert ok.water_span() == (0.0, 1.0)
    cases = [
        ({"props": ["boat"]}, "'boat' floats on water: give the stage water: true"),
        ({"water": {"left": 0.6}, "props": [{"prop": "boat", "at": 0.3}]}, "'boat' at 0.30 is not on the water (from 0.60 to 1.00)"),
        ({"water": True, "props": [{"prop": "boat", "depth": 0.3}]}, "floats at the front (depth 0)"),
        ({"water": {"left": 0.7, "right": 0.2}}, "water: left (0.7) must be left of right (0.2)"),
        ({"room": True, "props": ["hot_air_balloon"]}, "a hot air balloon stays outdoors"),
        ({"room": True, "props": ["toy_rocket"]}, "a toy rocket stays outdoors"),
        ({"room": True, "water": True}, "a room has no water"),
    ]
    for params, message in cases:
        with pytest.raises(ValidationError, match=message.replace("(", r"\(").replace(")", r"\)")):
            stage.validate_params(params)


def test_validate_a_toy_rocket_nobody_rides(make_project) -> None:
    beats = [{"text": "Pip tries to get in.", "actions": [{"get_in": "pip", "to": "toy_rocket"}]}]
    problems = check_project(street(make_project, {"props": [{"prop": "toy_rocket", "at": 0.45}], "characters": [{"name": "pip", "at": 0.4}]}, beats))
    assert len(problems) == 1 and "'toy_rocket' is a toy: nobody rides it (- ride_to: toy_rocket launches it on its own)" in problems[0]


# ----- foley and motion effects (no manim) ------------------------------------------------------------------


def test_water_and_air_sounds() -> None:
    boat = foley_cues(PlayedAction("ride_to", 1.0, 4.0, vehicle="boat"))
    assert [c.sound for c in boat] == ["engine", "splash"] and boat[0].params["pitch"] > 0   # a small motor, no brakes (a splash since Step 128)
    balloon = foley_cues(PlayedAction("ride_to", 0.0, 8.0, vehicle="hot_air_balloon", lands=1.0))
    assert [(c.sound, c.time) for c in balloon] == [("burner", 0.0), ("thud", 8.0)]
    rocket = foley_cues(PlayedAction("ride_to", 2.0, 3.0, vehicle="toy_rocket", lands=1.0))
    assert [(c.sound, round(c.time, 6)) for c in rocket] == [("launch", 2.0), ("pop", round(2.0 + ROCKET_ASCENT_SHARE * 3.0, 6)), ("thud", 5.0)]
    assert [c.sound for c in foley_cues(PlayedAction("ride_to", 0.0, 2.0, vehicle="toy_rocket"))] == ["launch"]   # flown away
    for name in ("burner", "launch"):
        x = sfx.synthesize(name)
        assert len(x) == round(sfx.BUILTIN_SOUNDS[name].duration * sfx.RATE) and np.all(np.isfinite(x)) and x[0] == x[-1] == 0.0
    assert np.array_equal(sfx.synthesize("launch"), sfx.synthesize("launch"))


def test_only_a_rocket_smokes() -> None:
    (smoke,) = motion_effect_cues(PlayedAction("ride_to", 1.0, 3.0, heights=9.0, vehicle="toy_rocket"), 1.0)
    assert smoke.kind == "smoke" and smoke.time == 1.0 and smoke.seconds > SMOKE_SECONDS
    assert motion_effect_cues(PlayedAction("ride_to", 0.0, 2.0, heights=9.0, vehicle="boat"), 1.0) == []   # no dust on the water
    assert motion_effect_cues(PlayedAction("ride_to", 0.0, 2.0, heights=9.0, vehicle="hot_air_balloon"), 1.0) == []
    assert motion_effect_cues(PlayedAction("ride_to", 0.0, 2.0, heights=9.0, vehicle="toy_rocket"), 0.0) == []   # cartoon_motion: none


# ----- render ----------------------------------------------------------------------------------------------


LAKE = {
    "water": {"left": 0.3}, "size": 0.3,
    "props": [{"prop": "boat", "at": 0.55}, {"prop": "hot_air_balloon", "at": 0.15, "name": "balloon"}, {"prop": "toy_rocket", "at": 0.05, "name": "rocket"}],
    "characters": [{"name": "pip", "at": 0.4}, {"name": "kit", "at": 0.25}],
}
TRIP = [
    {"text": "In they get.", "actions": [{"get_in": "pip", "to": "boat"}, {"get_in": "kit", "to": "balloon"}]},
    {"text": "Off they go.", "actions": [{"ride_to": "boat", "to": 0.8}, {"ride_to": "kit", "to": 0.2, "land": False}, {"ride_to": "rocket", "to": 0.2}]},
]


@pytest.mark.render
def test_a_trip_on_the_water_and_in_the_air(make_project, tmp_path: Path) -> None:
    """Pip rides the boat across the water, bobbing; kit's balloon flies away out of the frame; the
    toy rocket launches with smoke and lands under its parachute; the sounds are recorded."""
    project = street(make_project, LAKE, TRIP)
    assert check_project(project) == []
    scene, _ = render_with_layout(project, "lake", tmp_path / "media")
    boat, balloon, rocket, pip, kit = (scene.props["boat"], scene.props["balloon"], scene.props["rocket"], scene.cast["pip"], scene.cast["kit"])
    assert scene.water is not None and scene.water.contains(boat.afloat[0]) and boat.afloat[0] > 0.0
    assert pip.feet() == pytest.approx(seat_point(boat, 0), abs=1e-6) or pip.feet() == pytest.approx(seat_point(boat, 1), abs=1e-6)
    assert balloon.prop_point(0.0, 0.0)[1] > scene.frame_height / 2 and kit.feet()[1] > scene.frame_height / 2   # flown away with kit
    assert rocket.shape == "folded" and abs(float(rocket.feet()[1]) - scene.feet_y_at(0.0)) < 1e-6
    sounds = {event.sound for event in scene.sfx_log}
    assert {"engine", "burner", "launch", "pop", "thud"} <= sounds
