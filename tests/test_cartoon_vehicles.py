"""Step 118: vehicles on the ground (DESIGN.md §69.52): the bicycle, the car and the bus, their
seats, wheels and pedals, riding paths, riders attached and detached, the checks of ``vidgen
validate``, foley and motion effects of a ride, the planner, lint, and one tiny render."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_acting import VOICES, figure
from test_cartoon_lint import check, fig, thing
from test_cartoon_stage import CAST, render_with_layout
from vidgen import sfx
from vidgen.cartoon.directing import StageFrame, _riding, _SceneState
from vidgen.cartoon.foley import BRAKES, ENGINE_MIN_SECONDS, ENGINE_SHARE, PlayedAction, foley_cues
from vidgen.cartoon.holding import HandlingStep, holding_problems
from vidgen.cartoon.motion_effects import motion_effect_cues
from vidgen.cartoon.props import PROP_HEIGHTS, PROP_KINDS, draw_prop
from vidgen.cartoon.riding import RiderSeat, character_unit, pedal_soles, place_rider, riding_state, seat_point
from vidgen.cartoon.seating import PostureError, Postures
from vidgen.cartoon.vehicles import (
    GEAR,
    GROUND_VEHICLES,
    GET_IN_REACH,
    VEHICLE_KINDS,
    VEHICLES,
    crank_degrees,
    get_in_gap,
    is_vehicle,
    pedal_points,
    place_order,
    ride_facing,
    seat_count,
    seat_origin,
    seated_height,
    wheel_degrees,
)
from vidgen.cli import check_project
from vidgen.config import ActionConfig
from vidgen.project import Project
from vidgen.theme import Theme

#: Every generated look's hips are this high at most (character heights, DESIGN.md §69.36), and a
#: seated head reaches about 0.8 above them.
HIPS = 0.24
HEAD_ABOVE_HIPS = 0.8


# ----- the vehicles (no render) -----------------------------------------------------------------


def test_vehicles_are_props() -> None:
    assert GROUND_VEHICLES == ("bicycle", "car", "bus") and set(VEHICLE_KINDS) <= set(PROP_KINDS)
    assert VEHICLE_KINDS == (*GROUND_VEHICLES, "boat", "hot_air_balloon", "toy_rocket")   # Step 119
    assert all(is_vehicle(kind) and PROP_HEIGHTS[kind] == VEHICLES[kind].height for kind in VEHICLE_KINDS)
    assert not is_vehicle("chair") and not is_vehicle(None)
    assert [seat_count(kind) for kind in VEHICLE_KINDS] == [1, 2, 4, 2, 2, 0]


@pytest.mark.parametrize("kind", GROUND_VEHICLES)
def test_seats_lie_in_the_vehicle_and_heads_fit_under_the_roof(kind: str) -> None:
    spec = VEHICLES[kind]
    prop = draw_prop(kind, height=2.0, theme=Theme())
    left, right = prop.get_left()[0], prop.get_right()[0]
    for place in range(seat_count(kind)):
        x, floor = seat_origin(kind, place)
        point = seat_point(prop, place)
        assert left < point[0] < right and point[1] == pytest.approx(floor * prop.height) and x == spec.seats[place]
    assert spec.floor < spec.seat < 1.0
    for x, y, r in spec.wheels:   # every wheel stands on the ground
        assert y - r == pytest.approx(0.0, abs=1e-9)
    if spec.hides_legs:   # a seated rider's head is under the roof; its feet are on the floor behind the side
        assert spec.seat * spec.height + HEAD_ABOVE_HIPS < spec.height + 0.02
        assert spec.floor > 0
    else:
        assert spec.crank is not None and spec.grip is not None
    assert get_in_gap(0.0, 0.0, 2.0, kind) == 0.0
    assert get_in_gap(spec.half_length * 2.0 + 0.5, 0.0, 2.0, kind) == pytest.approx(0.5)


def test_seated_height_is_the_seat_above_the_floor() -> None:
    car = VEHICLES["car"]
    assert seated_height("car", 2.0, 2.0 / car.height) == pytest.approx((car.seat - car.floor) * car.height)
    assert seated_height("bicycle", 1.0, 1.0 / VEHICLES["bicycle"].height) == pytest.approx(0.255)   # the saddle, in character heights


def test_the_nearest_seat_comes_first() -> None:
    assert place_order(-5.0, 0.0, 1.0, "car", "right") == [1, 0]   # from behind: the back seat
    assert place_order(5.0, 0.0, 1.0, "car", "right") == [0, 1]
    assert place_order(5.0, 0.0, 1.0, "car", "left") == [1, 0]   # mirrored
    assert place_order(0.0, 0.0, 1.0, "bus", "right")[0] in (1, 2)


# ----- wheels, cranks and pedals (no render) ---------------------------------------------------------


def test_wheels_turn_by_the_way_gone() -> None:
    assert wheel_degrees(2 * math.pi * 0.5, 0.5) == pytest.approx(-360.0)   # one turn per circumference, clockwise
    assert wheel_degrees(-1.0, 0.5) > 0 and wheel_degrees(1.0, 0.0) == 0.0
    assert crank_degrees(-360.0) == pytest.approx(-360.0 / GEAR)


def test_pedals_go_round_the_crank_opposite_each_other() -> None:
    x, y, r = VEHICLES["bicycle"].crank
    for angle in (0.0, 45.0, 200.0):
        pedals = pedal_points("bicycle", angle)
        near, far = np.array(pedals["left"]), np.array(pedals["right"])
        assert np.linalg.norm(near - (x, y)) == pytest.approx(r) and (near + far) / 2 == pytest.approx((x, y))
    assert pedal_points("bicycle", 0.0)["left"] == pytest.approx((x + r, y))   # straight ahead
    assert pedal_points("car", 0.0) == {}


def test_a_vehicle_turns_round_to_go_the_other_way() -> None:
    assert ride_facing("right", -1.0) == "left" and ride_facing("left", 2.0) == "right"
    assert ride_facing("left", 0.0) == "left"   # only in depth: it keeps its facing


def test_drawn_wheels_turn_about_their_axles() -> None:
    bike = draw_prop("bicycle", height=1.5, theme=Theme()).shift([2.0, -1.0, 0.0])
    (spokes, (wx, wy)), _ = bike.wheels
    axle = bike.prop_point(wx, wy)
    start = spokes.get_all_points().copy()
    bike.turn_wheels(-90.0)
    assert bike.wheel_angle == -90.0 and bike.crank_angle == pytest.approx(-90.0 / GEAR)
    moved = spokes.get_all_points()
    assert not np.allclose(moved, start) and np.allclose(np.linalg.norm(moved - axle, axis=1), np.linalg.norm(start - axle, axis=1))
    assert bike.unit == pytest.approx(1.5) and bike.standing_height == pytest.approx(1.5)
    left = draw_prop("car", height=1.0, theme=Theme(), facing="left")
    assert left.prop_point(0.5, 0.0)[0] == pytest.approx(-0.5)   # mirrored: the front on the left


# ----- riders on their seats (manim objects, no render) -----------------------------------------------


def _vehicle(kind: str, unit: float, x: float = 0.0) -> Any:
    prop = draw_prop(kind, height=PROP_HEIGHTS[kind] * unit, theme=Theme(), character_height=unit).shift([x, -2.0, 0.0])
    prop.height_factor = PROP_HEIGHTS[kind]
    return prop


def test_a_rider_follows_its_seat_and_grows_with_the_vehicle() -> None:
    pip = figure()
    car = _vehicle("car", pip.character_height, x=1.0)
    assert character_unit(car) == pytest.approx(pip.character_height)
    seat = RiderSeat(pip, car, 1, pip.character_height / car.unit)
    place_rider(seat)
    assert pip.feet() == pytest.approx(seat_point(car, 1)) and pip.facing == "right"
    car.shift([3.0, 0.5, 0.0])
    car.scale(0.5, about_point=car.feet())
    car.stage_depth, car.ground_y = 0.4, -1.5
    place_rider(seat)
    assert pip.feet() == pytest.approx(seat_point(car, 1)) and pip.character_height == pytest.approx(seat.ratio * car.unit)
    assert pip.stage_depth == 0.4 and pip.ground_y == -1.5
    car.flip(np.array([0.0, 1.0, 0.0]), about_point=car.feet())
    car.facing = "left"
    place_rider(seat)
    assert pip.facing == "left" and pip.feet() == pytest.approx(seat_point(car, 1))


def test_a_cyclist_sits_on_the_saddle_and_pedals() -> None:
    kit = figure("kit")
    bike = _vehicle("bicycle", kit.character_height)
    seat = RiderSeat(kit, bike, 0, kit.character_height / bike.unit)
    kit.face(bike.facing)
    state = riding_state(kit, bike, 0, kit.state())
    place_rider(seat)
    kit.set_state(state)
    soles = kit.sole_points()
    pedals = pedal_soles(seat)
    for foot in ("left", "right"):   # on the pedals, or reaching for them as far as the legs go
        assert np.linalg.norm(np.array(soles[foot]) - pedals[foot]) < 0.06, foot
    grip = bike.prop_point(*VEHICLES["bicycle"].grip)
    assert np.linalg.norm(kit.hand_point("left") - grip) < 0.08 * kit.character_height   # the hands on the handlebar
    bike.turn_wheels(-200.0)   # the cranks turn: the pedals move, the soles follow
    assert pedal_soles(seat)["left"] != pytest.approx(pedals["left"])


# ----- who rides what (no manim) --------------------------------------------------------------------------


def test_postures_seat_riders_and_refuse_the_rest() -> None:
    postures = Postures()
    assert postures.ride("pip", "car", 2, prefer=[1, 0]) == 1
    assert postures.ride("kit", "car", 2) == 0 and postures.riders("car") == ["pip", "kit"]
    with pytest.raises(PostureError, match="'car' is full: it has 2 seats and pip, kit ride it then; get_out one first"):
        postures.ride("moss", "car", 2)
    with pytest.raises(PostureError, match=r"pip rides 'car' then; get_out first \(- get_out: pip\)"):
        postures.pinned("pip", "walk_to")
    with pytest.raises(PostureError, match="pip rides 'car' then; get_out first"):
        postures.sit("pip", "chair")
    with pytest.raises(PostureError, match="it gets out with get_out, not stand_up"):
        postures.stand("pip")
    assert postures.get_out("pip") == "car" and postures.riders("car") == ["kit"]
    with pytest.raises(PostureError, match=r"pip rides nothing then; get_out follows a get_in"):
        postures.get_out("pip")


def _replay(steps: list[HandlingStep], **keys: Any) -> list[tuple[str, str]]:
    characters = {"pip": (-6.0, 2.0), "kit": (0.0, 2.0), "moss": (0.5, 2.0)}
    vehicles = {"car": ("car", 2.0 * PROP_HEIGHTS["car"]), "bike": ("bicycle", 2.0 * PROP_HEIGHTS["bicycle"])}
    return holding_problems(steps, characters=characters, props={"car": 0.0, "bike": 1.0, "box": 0.5}, place_x=lambda p: float(p) if p is not None else None,
                            to_fraction=lambda x: x, vehicles=vehicles, **keys)


def test_validate_riding() -> None:
    def step(k: int, action: str, target: str, **options: Any) -> HandlingStep:
        return HandlingStep(f"a[{k}]", action, (target,), options)

    ok = [step(0, "get_in", "kit", to="car"), step(1, "get_in", "moss", to="car"), step(2, "ride_to", "car", to=5.0),
          step(3, "get_out", "kit"), step(4, "pick_up", "kit", to="box")]
    (far,) = _replay(ok)   # the box stayed behind: after the ride kit is at x 5
    assert far[0] == "a[4].to" and far[1].startswith("kit is 2.2 of its heights from 'box'")
    problems = _replay([
        step(0, "get_in", "pip", to="car"),                      # beyond the car's end
        step(1, "get_in", "kit", to="bike"), step(2, "get_in", "moss", to="bike"),   # the bicycle seats one
        step(3, "walk_to", "kit", to=1.0),
        step(4, "ride_to", "moss", to=2.0),
        step(5, "pick_up", "moss", to="car"),
        step(6, "keyframes", "bike"),
        step(7, "stand_up", "kit"),
    ])
    messages = dict(problems)
    car_end = 2.0 * PROP_HEIGHTS["car"] * VEHICLES["car"].half_length
    assert messages["a[0].to"] == (f"pip is {(6.0 - car_end) / 2.0:.1f} of its heights beyond the end of 'car' (it gets in from at most {GET_IN_REACH}); "
                                   "walk_to first (- walk_to: pip, to: -0.80)")
    assert "a[1].to" not in messages   # kit stands beside the bicycle
    assert messages["a[2].target"] == "'bike' is full: it has 1 seat and kit rides it then; get_out one first"
    assert messages["a[3].target"] == "kit rides 'bike' then; get_out first (- get_out: kit)"
    assert messages["a[4].target"].startswith("moss rides nothing then; get_in first")
    assert messages["a[5].to"] == "'car' is a vehicle, too big to pick up; get_in it instead (- get_in: moss, to: car)"
    assert messages["a[6].target"] == "kit rides 'bike' then; get_out first (- get_out: kit)"
    assert messages["a[7].target"].startswith("kit rides 'bike' then; it gets out with get_out")
    assert len(problems) == 7


def test_validate_riding_across_depths() -> None:
    steps = [HandlingStep("a[0]", "get_in", ("kit",), {"to": "car"})]
    (problem,) = _replay(steps, depths={"kit": 0.0, "car": 0.4})
    assert problem[1].startswith("kit stands at depth 0 and 'car' at depth 0.4; walk_to first")
    steps = [HandlingStep("a[0]", "get_in", ("kit",), {"to": "car"}), HandlingStep("a[1]", "ride_to", ("kit",), {"to": {"mark": 3.0, "depth": 0.5}}),
             HandlingStep("a[2]", "get_out", ("kit",), {}), HandlingStep("a[3]", "sit_on", ("kit",), {"to": "box"})]
    (problem,) = _replay(steps, depths={"kit": 0.0, "car": 0.0, "box": 0.0})
    assert problem[1].startswith("kit stands at depth 0.5 and 'box' at depth 0")   # it rode to the back with the car


# ----- on a project (validate) -------------------------------------------------------------------------


def street(make_project, beats: list[dict[str, Any]], **params: Any) -> Project:
    """A street: a car in the middle, a bicycle on the right, a tree; pip beside the car, kit by the bicycle."""
    stage = {"idle": False, "props": [{"prop": "car", "at": 0.4}, {"prop": "bicycle", "at": 0.8}, {"prop": "tree", "at": 0.1}],
             "characters": [{"name": "pip", "at": 0.35}, {"name": "kit", "at": 0.85}], **params}
    scenes = [{"id": "street", "type": "stage", "params": stage, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))


RIDE = [
    {"text": "They get in.", "actions": [{"get_in": "pip", "to": "car"}, {"get_in": "kit", "to": "bicycle"}]},
    {"text": "Off they go.", "actions": [{"ride_to": "car", "to": {"mark": 0.6, "depth": 0.3}}, {"ride_to": "kit", "to": 0.2}]},
    {"text": "They get out.", "actions": [{"get_out": ["pip", "kit"]}]},
]


def test_validate_a_ride(make_project) -> None:
    assert check_project(street(make_project, RIDE)) == []
    bad = [{"text": "Wrong.", "actions": [{"get_in": "pip", "to": "tree"}, {"get_in": "kit", "to": "van"}, {"ride_to": "tree", "to": 0.5}]}]
    problems = check_project(street(make_project, bad))
    assert any("'tree' is not a vehicle (vehicles: car, bicycle)" in p for p in problems)
    assert any("'van' is not a vehicle of the scene (vehicles: car, bicycle)" in p for p in problems)
    assert sum("'tree' is not a vehicle" in p for p in problems) == 2
    far = [{"text": "Pip tries the bicycle.", "actions": [{"get_in": "pip", "to": "bicycle"}]}]
    (problem,) = check_project(street(make_project, far))
    assert "pip is" in problem and "beyond the end of 'bicycle'" in problem and "walk_to first (- walk_to: pip" in problem


# ----- foley and motion effects of a ride (no manim) ------------------------------------------------------


def test_a_ride_rings_or_starts_its_engine_and_brakes() -> None:
    bell, brakes = foley_cues(PlayedAction("ride_to", 2.0, 3.0, heights=2.0, vehicle="bicycle"))
    assert (bell.sound, bell.time, bell.align) == ("bell", 2.0, "start")
    assert (brakes.sound, brakes.time, brakes.align, brakes.params["pitch"]) == ("brakes", 5.0, "end", BRAKES["bicycle"][0])
    engine, stop = foley_cues(PlayedAction("ride_to", 1.0, 4.0, heights=3.0, vehicle="car"))
    assert engine.sound == "engine" and engine.params["duration"] == pytest.approx(ENGINE_SHARE * 4.0) and stop.sound == "brakes"
    (short, _) = foley_cues(PlayedAction("ride_to", 0.0, 0.5, vehicle="bus"))
    assert short.params == {"duration": ENGINE_MIN_SECONDS, "pitch": -5.0}
    assert foley_cues(PlayedAction("ride_to", 0.0, 1.0)) == []   # no vehicle known: silent


def test_ride_sounds_are_built_in() -> None:
    for name in ("bell", "engine", "brakes"):
        x = sfx.synthesize(name)
        assert len(x) == round(sfx.BUILTIN_SOUNDS[name].duration * sfx.RATE) and np.all(np.isfinite(x)) and x[0] == x[-1] == 0.0
    assert len(sfx.synthesize("engine", duration=3.2)) == round(3.2 * sfx.RATE)


def test_a_fast_ride_raises_dust_and_leaves_speed_lines() -> None:
    kinds = [cue.kind for cue in motion_effect_cues(PlayedAction("ride_to", 0.0, 2.0, heights=5.0, vehicle="car"), 1.0)]
    assert kinds == ["dust", "speed_lines", "dust"]
    assert motion_effect_cues(PlayedAction("ride_to", 0.0, 4.0, heights=1.0, vehicle="bus"), 1.0) == []   # slow
    assert motion_effect_cues(PlayedAction("ride_to", 0.0, 2.0, heights=5.0, vehicle="car"), 0.0) == []   # cartoon_motion: none


# ----- the planner and lint (no manim) ---------------------------------------------------------------------


def test_the_planner_moves_riders_with_their_vehicle() -> None:
    frame = StageFrame(16.0, 9.0, 16.0, 0.0, {}, props={"car": -2.0}, marks={}, vehicles={"car": ("car", 3.0, "right")})
    state = _SceneState(cast={}, present={"pip", "kit"}, frame=frame, x={"pip": -3.0, "kit": 5.0}, facing={"pip": "right", "kit": "left"})
    names = ["pip", "kit"]
    _riding(state, ActionConfig.model_validate({"get_in": "pip", "to": "car"}), names)
    assert state.postures.riders("car") == ["pip"] and state.x["pip"] == -2.0 and state.facing["pip"] == "right"
    _riding(state, ActionConfig.model_validate({"ride_to": "pip", "to": 0.25}), names)
    assert state.prop_x["car"] == pytest.approx(-4.0) and state.x["pip"] == pytest.approx(-4.0)
    assert state.facing["pip"] == "left" and state.facing["car"] == "left"
    _riding(state, ActionConfig.model_validate({"get_out": "pip"}), names)
    _riding(state, ActionConfig.model_validate({"ride_to": "car", "to": 0.75}), names)
    assert state.x["pip"] == pytest.approx(-4.0) and state.prop_x["car"] == pytest.approx(4.0)   # it got out: it stays


def test_lint_knows_riders() -> None:
    car = thing("car", [100, 200, 500, 400], order=9)
    pip = fig("pip", [150, 150, 250, 380], order=5, riding="car", speaking=True, face=[170, 220, 230, 280])
    kit = fig("kit", [190, 150, 290, 380], order=4, riding="car")
    assert check("character_overlap", [kit, pip, car]) == [] and check("walk_overlap", [kit, {**pip, "walked_in": "b2"}, car]) == []
    assert check("hidden_speaker", [kit, pip, car]) == []   # its head shows in the car's window
    assert check("character_overlap", [{**kit, "riding": None}, pip, car]) != []   # one standing on the other
    assert check("hidden_speaker", [{**pip, "riding": None}, car]) != []   # standing behind a car


# ----- render ----------------------------------------------------------------------------------------------


@pytest.mark.render
def test_a_ride_with_riders(make_project, tmp_path: Path) -> None:
    """Pip gets in the car (drawn behind its side), kit on the bicycle (in front of it); the car
    rides to the back and the bicycle to the left with their riders, wheels turning; they get out
    in front of their vehicles; the ride's sounds are recorded."""
    from vidgen.introspect import LayoutRecorder

    recorder = LayoutRecorder()
    scene, _ = render_with_layout(street(make_project, RIDE), "street", tmp_path / "media", recorder)
    car, bike, pip, kit = scene.props["car"], scene.props["bicycle"], scene.cast["pip"], scene.cast["kit"]
    assert car.stage_depth == pytest.approx(0.3) and pip.stage_depth == pytest.approx(0.3) and car.wheel_angle != 0.0
    assert car.facing == "right" and bike.facing == "left" and bike.crank_angle != 0.0
    assert pip.riding is None and kit.riding is None and abs(float(pip.feet()[0] - seat_point(car, 0)[0])) < 0.5 * car.width
    stills = [{o["name"]: o for o in f["objects"] if o["name"]} for f in recorder.frames if "mid" not in f]
    riding, out = stills[0], stills[-1]
    assert riding["pip"]["riding"] == "car" and riding["kit"]["riding"] == "bicycle" and "riding" not in out["pip"]
    assert riding["pip"]["order"] < riding["car"]["order"] and riding["kit"]["order"] > riding["bicycle"]["order"]   # behind its side / on it
    assert out["pip"]["order"] > out["car"]["order"] and out["kit"]["order"] > out["bicycle"]["order"]   # out: in front of them
    sounds = {event.sound for event in scene.sfx_log}
    assert {"engine", "bell", "brakes"} <= sounds


@pytest.mark.render
def test_vehicles_gallery_still(tmp_path: Path) -> None:
    from PIL import Image

    from vidgen.cartoon.still import write_props_png

    path = write_props_png(Theme(), tmp_path / "vehicles.png", width=192, height=64, kinds=VEHICLE_KINDS, columns=3)
    with Image.open(path) as image:
        assert image.size == (192, 64) and image.mode == "P"
