"""Vehicles moving on an iso place (DESIGN.md §105): the rules (routes for a car, a boat, a train
car, a rocket's lift-off), the drawings (a car driving away, turning wheels, a driven vehicle
left out of the place's pictures), the checks of ``drive_to`` / ``sail_to`` / ``lift_off`` and
one small render."""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST
from test_iso_moves import problems
from vidgen import extensions, registry
from vidgen.cartoon.foley import PlayedAction, foley_cues
from vidgen.cartoon.iso_drawing import Line, Poly
from vidgen.cartoon.iso_driving import IsoVehicle, frame_item, track_shapes, vehicle_shapes
from vidgen.cartoon.iso_objects import ObjectLook, _Frame, object_shapes
from vidgen.cartoon.iso_town import car_shapes
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.world.iso import ObjectPlacing, ObjectState, parse_iso_map, place_objects
from vidgen.world.iso_vehicles import (
    drive_seconds,
    drive_share,
    lift_share,
    moved_item,
    moved_place,
    plan_vehicle,
    start_heading,
    track_cells,
)

#: A block of road round a square, a stream at the front, grass at the back for a train.
TOWN = """
..........
.::::::::.
.:......:.
.:..s...:.
.::::::::.
..........
~~~~~~~~~~
~~~~~~~~~~
"""
LOOK = ObjectLook("#E2574C", "#9FD3F2")


def town(*placings: ObjectPlacing):
    return place_objects(parse_iso_map(TOWN, names={"s": "square"}, place="outdoor"), placings)


def test_vehicle_rules_do_not_import_manim() -> None:
    code = "import sys, vidgen.world.iso_vehicles; print('manim' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_a_car_drives_round_the_block_turning_at_corners() -> None:
    place = town(ObjectPlacing("car", (2, 2)))   # cells (1, 1) and (2, 1), heading east
    route = plan_vehicle(place, "car", "drive_to", {"to": {"column": 9, "row": 5}})
    assert route.points[0] == (2.0, 1.5, 0.0)   # its middle, between its two cells
    assert route.end_cells == ((8, 3), (8, 4)) and route.end_heading == (0, 1)   # its front in the goal, heading south
    assert route.turns[0] == ((1, 0), (1, 0)) and ((1, 0), (0, 1)) in route.turns   # straight on, then a turn at the corner
    assert route.at(route.length)[0] == pytest.approx((8.5, 4.0, 0.0))
    for a, b in zip(route.points, route.points[1:]):   # along the map's rows and columns, or across a corner cell
        assert math.dist(a, b) in (pytest.approx(1.0), pytest.approx(math.sqrt(0.5)))
    corner = next(k for k, (before, after) in enumerate(route.turns) if before != after)
    assert route.at(sum(math.dist(a, b) for a, b in zip(route.points[:corner + 1], route.points[1:corner + 1])) + 0.1)[1] == (1, 0)
    moved = moved_item(place.object("car"), route.end_cells, route.end_heading)
    assert (moved.column, moved.row, moved.width, moved.depth, moved.facing) == (8, 3, 1, 2, "right")
    after = moved_place(place, {"car": moved})
    assert after.object_at(8, 4).name == "car" and after.object_at(1, 1) is None


def test_a_car_turns_round_where_its_way_ends_and_stops_near_a_spot_off_the_road() -> None:
    place = town(ObjectPlacing("car", (2, 2)))
    back = plan_vehicle(place, "car", "drive_to", {"to": {"column": 2, "row": 5}})
    assert back.turns[0] == ((1, 0), (-1, 0)) and back.end_heading == (0, 1)   # round at once: the way back is shorter
    near = plan_vehicle(place, "car", "drive_to", {"to": "square"})   # the square's letter is grass: the nearest road cell
    assert near.end_cells[-1] in {(4, 1), (4, 4), (1, 3)}


def test_what_is_in_a_cars_way_is_named() -> None:
    place = town(ObjectPlacing("car", (2, 2)), ObjectPlacing("bench", (5, 2)), ObjectPlacing("bench", (2, 5), name="bench_2"))
    with pytest.raises(VidgenError, match=r"'car' cannot drive from row 2, column 3 to row 2, column 7: the way stops at row 2, column 4: the bench at"):
        plan_vehicle(place, "car", "drive_to", {"to": {"column": 9, "row": 2}, "via": [{"column": 7, "row": 2}]})
    with pytest.raises(VidgenError, match=r"'car' cannot drive to row 4, column 5: row 4, column 5 is grass \(a car drives along path cells, :\)"):
        plan_vehicle(place, "car", "drive_to", {"to": {"column": 5, "row": 4}})
    with pytest.raises(VidgenError, match=r"'pip' standing there \(walk it away first\)"):
        plan_vehicle(town(ObjectPlacing("car", (2, 2)), ObjectPlacing("bench", (2, 5))), "car", "drive_to", {"to": {"column": 6, "row": 2}},
                     crowd={(3, 1): "pip"})
    with pytest.raises(VidgenError, match="the place has no spot 'shop'"):
        plan_vehicle(place, "car", "drive_to", {"to": "shop"})
    with pytest.raises(VidgenError, match="'car' is car: sail_to moves a boat"):
        plan_vehicle(place, "car", "sail_to", {"to": "square"})


def test_a_boat_sails_on_water_only() -> None:
    place = town(ObjectPlacing("boat", (1, 7)))
    route = plan_vehicle(place, "boat", "sail_to", {"to": {"column": 9, "row": 8}})
    assert route.end_cells[-1] == (8, 7)
    assert all(place.ground(math.floor(x), math.floor(y)) == "water" for x, y, _ in route.points[1:])
    with pytest.raises(VidgenError, match=r"a boat sails on water"):
        plan_vehicle(place, "boat", "sail_to", {"to": {"column": 5, "row": 4}})


def test_a_train_car_rolls_along_its_track() -> None:
    place = town(ObjectPlacing("train_car", (2, 1)))
    assert track_cells(place, place.object("train_car")) == [(c, 0) for c in range(10)]
    route = plan_vehicle(place, "train_car", "drive_to", {"to": {"column": 8, "row": 1}})
    assert route.points == ((2.5, 0.5, 0.0), (7.5, 0.5, 0.0)) and route.end_cells == ((6, 0), (7, 0), (8, 0)) and route.end_heading == (1, 0)
    with pytest.raises(VidgenError, match=r"rolls along its track \(row 1\)"):
        plan_vehicle(place, "train_car", "drive_to", {"to": {"column": 8, "row": 3}})
    with pytest.raises(VidgenError, match="its track runs from row 1, column 1 to row 1, column 10"):
        plan_vehicle(place, "train_car", "drive_to", {"to": {"column": 10, "row": 1}})
    with pytest.raises(VidgenError, match="'kit' stands on the track"):
        plan_vehicle(place, "train_car", "drive_to", {"to": {"column": 8, "row": 1}}, crowd={(6, 0): "kit"})


def test_a_rocket_lifts_off_and_moves_ease() -> None:
    place = town(ObjectPlacing("rocket", (4, 3)))
    route = plan_vehicle(place, "rocket", "lift_off", {}, height=20.0)
    assert route.points == ((4.0, 3.0, 0.0), (4.0, 3.0, 20.0)) and start_heading(place.object("rocket")) == (0, 0)
    shares = [drive_share(k / 20, 3.0) for k in range(21)]
    assert shares[0] == 0.0 and shares[-1] == pytest.approx(1.0) and all(b > a for a, b in zip(shares, shares[1:]))
    assert shares[1] < 0.05 / 2 and drive_share(0.5, 3.0) == pytest.approx(0.5)   # slow off, steady in the middle
    assert lift_share(0.25) < 0.25 / 3 and lift_share(1.0) == 1.0
    assert drive_seconds(route, 5.0) == pytest.approx(4.6)


def test_vehicles_are_drawn_driving_away_and_left_out_of_the_place_when_driven() -> None:
    place = town(ObjectPlacing("car", (2, 2)), ObjectPlacing("train_car", (2, 1)), ObjectPlacing("rocket", (4, 3)), ObjectPlacing("boat", (1, 7)))
    car = place.object("car")
    f = _Frame(car, 0.0)
    assert object_shapes(car, LOOK, 0.0, ObjectState(on=True)) == car_shapes(f, LOOK, ObjectState(on=True))   # parked: as before
    for name in ("car", "boat", "train_car"):
        assert object_shapes(place.object(name), ObjectLook("#E2574C", "#9FD3F2", driven=True), 0.0) == []
    rocket = place.object("rocket")
    pad = object_shapes(rocket, ObjectLook("#E2574C", "#9FD3F2", driven=True), 0.0, ObjectState(on=True))
    assert 0 < len(pad) < len(object_shapes(rocket, LOOK, 0.0))   # the pad and tower stay
    away = car_shapes(f, LOOK, ObjectState(on=True), reverse=True)
    assert away != car_shapes(f, LOOK, ObjectState(on=True))
    tail = [s for s in away if isinstance(s, Poly) and s.fill == "#FF4A3D"]
    assert len(tail) == 2 and all(s.glow for s in tail)   # its tail lights on its end to the viewer
    spokes = [s for s in car_shapes(f, LOOK, ObjectState(), spin=0.3) if isinstance(s, Line)]
    assert len(spokes) == len([s for s in car_shapes(f, LOOK, ObjectState()) if isinstance(s, Line)]) + 4
    for kind in ("car", "boat", "train_car", "rocket"):
        for heading in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            item = frame_item(kind, heading)
            assert abs(item.column + item.width / 2) < 1e-9 and abs(item.row + item.depth / 2) < 1e-9
            assert vehicle_shapes(kind, LOOK, heading=heading, on=True, now=0.5)
    assert track_shapes([(c, 0) for c in range(5)], 0.0)
    still, sailing = (vehicle_shapes("boat", LOOK, heading=(0, -1), on=False, wake=wake) for wake in (False, True))
    assert len(sailing) == len(still) + 3   # its wake: two arms and a trail, under the hull


def test_headlights_light_the_road_ahead_and_corners_show_a_turned_car() -> None:
    """Step 275: the pool of a car's headlights lies ahead of it for every heading (further on
    driving away, where the car hides the road just ahead); half-way round a corner the car is
    drawn turned to the diagonal."""
    from vidgen.cartoon.iso_drawing import Disc

    for heading in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        shapes = vehicle_shapes("car", LOOK, heading=heading, on=True, spin=0.0)
        pool = next(s for s in shapes if isinstance(s, Disc) and s.pool)
        ahead = pool.centre[0] * heading[0] + pool.centre[1] * heading[1]
        side = pool.centre[0] * heading[1] - pool.centre[1] * heading[0]
        assert ahead > 1.0 and abs(side) < 0.1
        if heading in ((-1, 0), (0, -1)):
            assert ahead > 1.8 and pool.radius > 0.7   # away up the picture: further and wider
    place = town(ObjectPlacing("car", (2, 2)))
    route = plan_vehicle(place, "car", "drive_to", {"to": {"column": 9, "row": 5}})   # east, then a right turn south
    corner = next(k for k, (a, b) in enumerate(route.turns) if a != b)
    start = sum(math.dist(a, b) for a, b in zip(route.points[:corner], route.points[1:corner + 1]))
    leg = math.dist(route.points[corner], route.points[corner + 1])
    assert route.turning(start + leg / 2) == ((1, 0), (0, 1))
    assert route.turning(start + leg * 0.1) is None and route.turning(0.1) is None
    turned = vehicle_shapes("car", LOOK, heading=(0, 1), on=True, turn=((1, 0), (0, 1)))
    pool = next(s for s in turned if isinstance(s, Disc) and s.pool)
    assert pool.centre[0] > 0.6 and pool.centre[1] > 0.6   # the road ahead along the diagonal
    assert len(turned) == len(vehicle_shapes("car", LOOK, heading=(1, 0), on=True))


def test_drives_sound_like_engines() -> None:
    sounds = {kind: [c.sound for c in foley_cues(PlayedAction("drive_to", 1.0, 3.0, vehicle=kind))] for kind in ("car", "train_car")}
    assert sounds == {"car": ["engine", "brakes"], "train_car": ["engine", "brakes"]}
    assert [c.sound for c in foley_cues(PlayedAction("sail_to", 0.0, 4.0, vehicle="boat"))] == ["engine", "splash"]
    assert [c.sound for c in foley_cues(PlayedAction("lift_off", 0.0, 4.0, vehicle="rocket"))] == ["engine", "launch"]


# ----- the stage ----------------------------------------------------------------------------------------


STREET = {"map": TOWN, "spots": {"s": "square"},
          "objects": [{"object": "car", "at": {"column": 2, "row": 2}}, {"object": "boat", "at": {"column": 1, "row": 7}},
                      {"object": "train_car", "at": {"column": 2, "row": 1}}, {"object": "rocket", "at": {"column": 4, "row": 3}}]}


def street_project(make_project, beats: list[dict[str, Any]], **params: Any) -> Project:
    params = {"idle": False, "background": "#BFE3F5", "iso": STREET, "characters": [{"name": "pip", "at": "square"}], **params}
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


@pytest.mark.parametrize(
    "action,message",
    [
        ({"drive_to": "boat", "to": "square"}, "'boat' is a boat: drive_to moves a car or a train_car (the place's: car, train_car)"),
        ({"sail_to": "bote", "to": "square"}, "'bote' is not a vehicle of the place; did you mean boat?"),
        ({"drive_to": "car", "to": "shop"}, "the place has no spot 'shop'"),
        ({"drive_to": "car", "to": {"column": 3, "row": 2}, "via": ["sqare"]}, "did you mean square?"),
        ({"lift_off": "car"}, "lift_off moves a rocket"),
        ({"drive_to": "car", "to": {"column": 5, "row": 4}}, "'car' cannot drive to row 4, column 5: row 4, column 5 is the rocket"),
        ({"drive_to": "car", "to": {"column": 7, "row": 4}}, "'car' cannot drive to row 4, column 7: row 4, column 7 is grass"),
        ({"sail_to": "boat", "to": {"column": 7, "row": 3}}, "a boat sails on water"),
    ],
)
def test_bad_vehicle_moves(make_project, action: dict[str, Any], message: str) -> None:
    beats = [{"text": "Pip waits.", "actions": [{"walk_to": "pip", "to": {"column": 4, "row": 2}}]}, {"text": "Off they go.", "actions": [action]}]
    found = problems(street_project(make_project, beats), "home")
    assert any(message in text for _, text in found), found


def test_vehicle_moves_need_an_iso_place(make_project) -> None:
    scenes = [{"id": "home", "type": "stage", "params": {"characters": [{"name": "pip", "at": "left"}]},
               "beats": [{"text": "Off it goes.", "actions": [{"drive_to": "pip", "to": "left"}]}]}]
    texts = [text for _, text in problems(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), "home")]
    assert any("drive_to moves a vehicle of an iso place" in t for t in texts), texts


def test_good_vehicle_moves_validate_and_walks_see_where_the_car_went(make_project) -> None:
    beats = [{"text": "The car drives round the block, the boat sails off.",
              "actions": [{"drive_to": "car", "to": {"column": 9, "row": 5}, "via": [{"column": 9, "row": 2}]},
                          {"sail_to": "boat", "to": {"column": 10, "row": 8}}, {"drive_to": "train_car", "to": {"column": 8, "row": 1}}]},
             {"text": "The rocket lifts off.", "actions": [{"lift_off": "rocket", "at": "@lifts"}]},
             {"text": "Pip walks where the car was.", "actions": [{"walk_to": "pip", "to": {"column": 3, "row": 2}}]}]
    assert problems(street_project(make_project, beats), "home") == []
    beats[2]["actions"] = [{"walk_to": "pip", "to": {"column": 9, "row": 5}}]   # the car stands there now
    found = problems(street_project(make_project, beats), "home")
    assert any("nobody can stand there" in text or "the car" in text for _, text in found), found
    beats[1]["actions"] += [{"lift_off": "rocket", "at": 0.5}]
    found = problems(street_project(make_project, beats), "home")
    assert any("has lifted off already" in text for _, text in found), found


@pytest.mark.slow
@pytest.mark.render
def test_vehicles_drive_sail_roll_and_lift_off(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    beats = [{"text": "Off they all go.", "actions": [{"drive_to": "car", "to": {"column": 9, "row": 5}}, {"sail_to": "boat", "to": {"column": 6, "row": 8}},
                                                     {"drive_to": "train_car", "to": {"column": 8, "row": 1}}, {"switch_on": "car"}]},
             {"text": "And up it goes.", "actions": [{"lift_off": "rocket"}]}]
    project = street_project(make_project, beats, light="sunset")
    scene, frames = frames_of(project, tmp_path / "vehicles", monkeypatch)
    vehicles = scene.iso_vehicles
    assert set(vehicles) == {"car", "boat", "train_car", "rocket"} and all(isinstance(v, IsoVehicle) for v in vehicles.values())
    assert vehicles["car"].point == pytest.approx((8.5, 4.0, 0.0)) and vehicles["car"].heading == (0, 1) and vehicles["car"].on_at(1.0)
    assert vehicles["train_car"].point == pytest.approx((7.5, 0.5, 0.0)) and vehicles["rocket"].launch is not None
    assert not vehicles["rocket"].shown   # gone out of the view
    assert scene.iso_place_now().object_at(8, 4).name == "car"   # walks plan round where it stopped
    assert len(vehicles["car"].slots) == 3 and len(frames) > 5 and np.any(frames[-1] != frames[2])
    assert [s for s, _ in vehicles["car"].drives] and vehicles["boat"].region()[2] > vehicles["boat"].region()[0]
