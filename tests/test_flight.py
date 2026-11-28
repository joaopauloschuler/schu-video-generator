"""Flight paths (Step 385): the frames and their conversions both ways, the worlds'
air against the page's, each manoeuvre against its closed form, smoothness where legs meet, the
ground check and the lift, the landing, the re-entry's ends, determinism, the cache and the keys,
the validation; the numpy port of ``vidgen/space-land``'s heights against the JavaScript (Node, a
lattice of one's own); in Chromium (``slow``): the page receives exactly the Python values,
``craft.fly`` follows a flight, and the page's ``heightAt`` equals the port for every preset."""

from __future__ import annotations

import base64
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from vidgen import extensions, flight as F
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.scenes import flight_data as fd
from vidgen.web import flights as wf

EARTH = F.world("earth")
FRAME = F.LocalFrame(-34.5, 20.0, EARTH.radius)
SEA = F.FlightContext(EARTH, FRAME, F.SeaGround("sea", "the sea"), margin=20.0)


def _run(legs: list[dict[str, Any]], start: dict[str, Any] | None = None, context: F.FlightContext = SEA, **extra: Any) -> F.FlightRun:
    spec = F.Flight.model_validate({"name": "P", "start": start or {"x": 0, "z": 0, "height": 1000, "heading": 0, "speed": 150}, "legs": legs, **extra})
    return F.FlightRun(spec, context)


@dataclass(frozen=True)
class Hill(F.Ground):
    """A 900 m hill 12 km north of the anchor."""

    def height(self, x: Any, z: Any) -> np.ndarray:
        x, z = np.asarray(x, dtype=float), np.asarray(z, dtype=float)
        return 900.0 * np.exp(-(x**2 + (z + 12000.0) ** 2) / 3000.0**2)


HILL = F.FlightContext(EARTH, FRAME, Hill("hill", "a hill"), margin=20.0)


# ----- frames ---------------------------------------------------------------------------------------------


def test_the_local_frame_is_space_lands_and_converts_both_ways() -> None:
    m = FRAME.axes
    a, o = math.radians(-34.5), math.radians(20.0)
    # vidgen/space-land's placeFrame(at) in three.js's body axes (x, y = pole, z) is (x, -z, y) in the planet-fixed frame
    up3, east3, south3 = [math.cos(a) * math.cos(o), math.sin(a), -math.cos(a) * math.sin(o)], [-math.sin(o), 0, -math.cos(o)], [math.sin(a) * math.cos(o), -math.cos(a), -math.sin(a) * math.sin(o)]
    for col, v in ((1, up3), (0, east3), (2, south3)):
        np.testing.assert_allclose(m[:, col], [v[0], -v[2], v[1]], atol=1e-15)
    assert np.allclose(m.T @ m, np.eye(3)) and np.linalg.det(m) == pytest.approx(1.0)     # east, up, south: three.js's right-handed x, y, z
    rng = np.random.default_rng(3)
    local = rng.uniform(-2e5, 2e5, (50, 3))
    np.testing.assert_allclose(FRAME.from_fixed(FRAME.to_fixed(local)), local, atol=1e-8)
    lat, lon, h = FRAME.geodetic(local)
    np.testing.assert_allclose(FRAME.place(lat, lon, h), local, atol=1e-6)
    assert np.allclose(FRAME.to_fixed([0.0, 0.0, 0.0]), EARTH.radius * m[:, 1]) and FRAME.height([0, 0, 0]) == pytest.approx(0.0)
    # the sphere drops away from the plane y = 0: 3.42 m at 6.6 km on a sphere of 6371 km
    p = FRAME.chart(6600.0, 0.0, 0.0)
    assert p[1] == pytest.approx(-(6600.0**2) / (2 * EARTH.radius), rel=1e-4) and FRAME.height(p) == pytest.approx(0.0, abs=1e-7)
    # headings: 0 is -z (north) at the anchor, 90 is +x (east)
    np.testing.assert_allclose(FRAME.heading_vector([0, 0, 0], 0.0), [0, 0, -1], atol=1e-12)
    np.testing.assert_allclose(FRAME.heading_vector([0, 0, 0], 90.0), [1, 0, 0], atol=1e-12)
    assert float(FRAME.heading_of([0, 0, 0], [1, 0, -1])) == pytest.approx(45.0)


def test_the_local_frame_and_the_orbit_bridges_ecliptic_frame() -> None:
    from vidgen.orbits.rotation import ROTATIONS

    rng = np.random.default_rng(5)
    local, velocity = rng.uniform(-5e5, 5e5, (20, 3)), rng.uniform(-300, 300, (20, 3))
    jd = 2461000.5 + rng.uniform(0, 3, 20)
    r, v = FRAME.to_ecliptic(EARTH, local, velocity, jd)
    back, vback = FRAME.from_ecliptic(EARTH, r, v, jd)
    np.testing.assert_allclose(back, local, atol=1e-6)
    np.testing.assert_allclose(vback, velocity, atol=1e-9)
    # a point at rest on the ground moves with the turning Earth: 2πR cos(lat) a sidereal day, eastward
    r0, v0 = FRAME.to_ecliptic(EARTH, np.zeros((1, 3)), np.zeros((1, 3)), np.array([2461000.5]))
    speed = 2 * math.pi * EARTH.radius * math.cos(math.radians(-34.5)) / ROTATIONS["earth"].period
    assert np.linalg.norm(v0) == pytest.approx(speed, rel=1e-9)
    east = FRAME.ecliptic_axes(EARTH, 2461000.5)[:, 0]
    assert float(v0[0] @ east) / speed == pytest.approx(1.0, rel=1e-9)
    # the place's up is the body frame's direction of its latitude and longitude
    up = r0[0] / np.linalg.norm(r0[0])
    body = ROTATIONS["earth"].frame(2461000.5)
    a, o = math.radians(-34.5), math.radians(20)
    np.testing.assert_allclose(up, body @ [math.cos(a) * math.cos(o), math.cos(a) * math.sin(o), math.sin(a)], atol=1e-12)


def test_the_worlds_air_is_the_pages() -> None:
    from vidgen.web.space_names import constant_entries, object_entries

    airs = constant_entries("vidgen/space-bodies", "AIRS")
    radii = {k: float(v) for k, v in constant_entries("vidgen/space-air", "RADII").items()}
    presets = constant_entries("vidgen/space-air", "PRESETS")
    for name, world_name, radius in (("earth", "earth", radii["earth"]), ("mars", "mars", radii["mars"]), ("thin", "thin", 2.4e6), ("thick", "thick", 7.4e6)):
        w = F.world(world_name)
        share = float(object_entries(airs[name if name != "thick" else "earth"])["height"])
        if name == "thick":
            share = float(object_entries(object_entries(presets["thick"])["air"])["height"])
        assert w.radius == radius and w.air.scale_height == pytest.approx(share * radius, rel=1e-12)
    assert F.WORLDS["thin"].radius == float(object_entries(presets["thin"])["radius"])
    land_radii = {k: float(v) for k, v in constant_entries("vidgen/space-land", "RADII").items()}
    for name, radius in land_radii.items():
        assert F.world(name).radius == radius and F.world(name).air is None
    assert EARTH.sound_speed == pytest.approx(math.sqrt(1.4 * EARTH.g0 * EARTH.air.scale_height)) and 345 < EARTH.sound_speed < 355
    assert EARTH.g0 == pytest.approx(9.82, abs=0.01) and F.world("thin").invented
    with pytest.raises(VidgenError, match="did you mean 'earth'"):
        F.world("erth")


def test_the_smoothstep_joins_with_three_derivatives() -> None:
    from vidgen.flight.profiles import PEAK, step, step_integral

    u = np.array([0.0, 1e-3, 0.5, 1 - 1e-3, 1.0])
    s = step(u)
    assert s[0] == 0 and s[-1] == 1 and s[2] == pytest.approx(0.5) and s[1] < 1e-10 and 1 - s[3] < 1e-10
    d = 1e-4
    assert (step(0.5 + d) - step(0.5 - d)) / (2 * d) == pytest.approx(PEAK, rel=1e-6)
    u = np.linspace(0, 0.3, 30001)
    f = step(u)
    assert step_integral(1.0) == pytest.approx(0.5) and step_integral(0.3) == pytest.approx(float(np.sum((f[1:] + f[:-1]) / 2 * np.diff(u))), abs=1e-9)
    assert step_integral(2.5) == pytest.approx(2.0)


# ----- manoeuvres against closed forms -------------------------------------------------------------------


def test_a_coordinated_turn_has_the_radius_and_bank_of_the_formula() -> None:
    run = _run([{"straight": 10}, {"turn": {"by": 90, "bank": 30}}, {"straight": 5}])
    turn = run.legs[1]
    middle = 0.5 * (turn.start + turn.end)
    s = run.sample(np.array([middle]))
    v, a = np.linalg.norm(s["velocity"][0]), s["acceleration"][0]
    g_eff = EARTH.gravity(1000.0) - v * v / (EARTH.radius + 1000.0)
    up = (s["position"][0] - FRAME.centre) / np.linalg.norm(s["position"][0] - FRAME.centre)
    lateral = np.linalg.norm(a - (a @ up) * up)
    assert v * v / lateral == pytest.approx(v * v / (g_eff * math.tan(math.radians(30))), rel=1e-6)          # r = v² / (g tan φ)
    assert v * v / (EARTH.g0 * math.tan(math.radians(30))) == pytest.approx(v * v / lateral, rel=2e-3)
    assert math.degrees(s["bank"][0]) == pytest.approx(30.0, abs=0.3)            # the turning world's Coriolis part: 0.13°
    assert s["load"][0] == pytest.approx(1 / math.cos(math.radians(30)), rel=3e-3)
    after = run.sample(np.array([turn.end, run.end]))
    assert math.degrees(after["heading"][0]) == pytest.approx(90.0, abs=1e-5)
    left = _run([{"turn": {"to": 300, "radius": 2500}}])
    assert math.degrees(left.sample(np.array([left.end]))["heading"][0]) == pytest.approx(300.0, abs=1e-5)
    tight = left.sample(np.array([0.5 * left.end]))
    assert np.linalg.norm(tight["velocity"][0]) ** 2 / np.linalg.norm(tight["acceleration"][0]) == pytest.approx(2500, rel=2e-3)
    assert math.degrees(tight["bank"][0]) < 0                      # the shorter way to 300 is to the left: a left bank


def test_climbs_speed_changes_and_their_lengths() -> None:
    run = _run([{"climb": {"to": 3000, "rate": 12}}, {"speed": {"to": 210, "rate": 3}}, {"descend": {"by": 500}}, {"climb": {"rate": 4}, "for": 30}, {"level": True}])
    climb, speed, down, rate, level = run.legs
    s = run.sample(np.array([climb.end, 0.5 * (climb.start + climb.end), speed.end, down.end, rate.end, level.end + 1]))
    assert s["height"][0] == pytest.approx(3000.0, abs=1e-6) and s["climb"][1] == pytest.approx(12.0, abs=1e-6)
    a = 0.25 * EARTH.g0
    ramp = 35 / 16 * 12 / a
    assert climb.end - climb.start == pytest.approx(ramp + (2000 - 12 * ramp) / 12 + ramp, rel=1e-9)       # ramps of the vertical acceleration's limit and a steady climb between
    assert speed.end - speed.start == pytest.approx(60 / 3, rel=1e-12) and s["speed"][2] == pytest.approx(210.0)
    assert s["height"][3] == pytest.approx(2500.0, abs=1e-6) and s["climb"][4] == pytest.approx(4.0, abs=1e-6) and s["climb"][5] == pytest.approx(0.0, abs=1e-6)
    t = np.linspace(climb.start, climb.end, 4001)
    assert np.max(run.climb_rate(t, 2)) == pytest.approx(a, rel=1e-4)        # the vertical acceleration's peak is the limit
    assert np.max(np.abs(np.gradient(run.sample(t)["pitch"], t))) < math.radians(2)


def test_the_path_is_smooth_where_legs_meet() -> None:
    run = _run([{"straight": 5}, {"turn": {"by": -20, "bank": 45}}, {"climb": {"by": 400}, "speed": 180}, {"waypoints": [[-4000, -20000], [0, -30000]]}, {"straight": 3}])
    dt = 1 / 30
    for leg in run.legs[:-1]:
        t = leg.end + dt * np.arange(-6, 7)
        s = run.sample(t)
        for key in ("position", "velocity", "acceleration"):
            x = s[key]
            third = np.diff(x, n=3, axis=0) / dt**3 if key == "position" else np.diff(x, n=2 if key == "velocity" else 1, axis=0)
            jumps = np.linalg.norm(np.diff(third, axis=0), axis=-1)
            assert np.max(jumps) < (0.05 if key == "position" else 0.05 if key == "velocity" else 0.05), (leg.kind, key, jumps)
        q = np.array([_quaternion(m) for m in s["matrix"]])
        assert np.allclose(np.linalg.norm(q, axis=-1), 1.0)
        turns = [2 * math.degrees(math.acos(min(1.0, abs(float(q[i] @ q[i + 1]))))) for i in range(len(q) - 1)]
        assert max(np.abs(np.diff(turns))) < 0.05, (leg.kind, turns)            # the attitude turns at a smooth rate: no kink at 30 fps
    # the velocity is the position's derivative and the nose is along it (the angle of attack aside)
    t = np.linspace(0.2, run.end - 0.2, 300)
    s, e = run.sample(t), 1e-3
    d = (run.sample(t + e)["position"] - run.sample(t - e)["position"]) / (2 * e)
    assert np.max(np.linalg.norm(d - s["velocity"], axis=-1)) < 1e-5 * 200
    nose = s["matrix"][:, :, 2]
    angle = np.degrees(np.arccos(np.clip(np.sum(nose * s["velocity"], axis=-1) / np.linalg.norm(s["velocity"], axis=-1), -1, 1)))
    assert np.allclose(angle, np.degrees(s["aoa"]), atol=1e-6)


def _quaternion(m: np.ndarray) -> np.ndarray:
    from vidgen.orbits.rotation import quaternions

    return quaternions(m)


def test_waypoints_and_a_circle() -> None:
    run = _run([{"waypoints": [[2000, -5000], [-1000, -10000], [3000, -16000]]}, {"straight": 5}], start={"x": 0, "z": 0, "height": 1500, "heading": 0, "speed": 120})
    assert max(run.legs[0].notes["misses"]) < 1.5                 # through the places to a metre or so (the tangent plane against the sphere)
    circle = _run([{"circle": {"around": [0, -12000], "radius": 4000, "turns": 1.25, "side": "right"}}], start={"x": 0, "z": 0, "height": 1500, "heading": 0, "speed": 120})
    low, high = circle.legs[0].notes["radius"]
    assert 3999 < low < high < 4001
    mid = circle.sample(np.array([0.5 * circle.legs[0].end]))
    assert mid["bank"][0] > 0 and math.degrees(mid["bank"][0]) == pytest.approx(math.degrees(math.atan(120**2 / (EARTH.g0 * 4000))), abs=0.3)
    with pytest.raises(VidgenError, match="needs a bank of .* over the limit"):
        _run([{"waypoints": [[300, -800], [-300, -1200]]}], start={"x": 0, "z": 0, "height": 1500, "heading": 0, "speed": 250})
    with pytest.raises(VidgenError, match="inside its radius"):
        _run([{"circle": {"around": [0, -1000], "radius": 4000}}])


def test_a_flat_world() -> None:
    flat = F.FlightContext(EARTH, None, F.FlatGround("flat", "flat", elevation=0.0))
    run = _run([{"turn": {"by": 180, "radius": 2000}}, {"climb": {"by": 300}}], start={"x": 0, "z": 0, "height": 300, "heading": 0, "speed": 120}, context=flat)
    s = run.sample(np.array([run.legs[0].end, run.end]))
    assert math.degrees(s["heading"][0]) == pytest.approx(180.0, abs=1e-6) and s["position"][0][1] == pytest.approx(300.0)
    assert s["position"][1][1] == pytest.approx(600.0, abs=1e-6) and s["above_ground"][1] == pytest.approx(600.0, abs=1e-6)
    straight = _run([{"straight": 100}], start={"x": 0, "z": 0, "height": 300, "heading": 90, "speed": 100}, context=flat).sample(np.array([100.0]))
    np.testing.assert_allclose(straight["position"][0], [10000.0, 300.0, 0.0], atol=1e-6)


# ----- never below ground ------------------------------------------------------------------------------------


def test_a_path_into_the_ground_is_an_error_naming_time_and_place() -> None:
    with pytest.raises(VidgenError) as raised:
        _run([{"straight": 150}], start={"x": 0, "z": 0, "height": 300, "heading": 0, "speed": 120}, context=HILL)
    text = str(raised.value)
    assert "flight P: at " in text and "leg 1 (straight)" in text and "over the ground at x = " in text and "°" in text and "lift: true" in text and "follow" in text
    lifted = _run([{"straight": 150}], start={"x": 0, "z": 0, "height": 300, "heading": 0, "speed": 120}, context=HILL, lift=True)
    t = np.linspace(0, 150, 3001)
    s = lifted.sample(t)
    assert np.min(s["above_ground"]) >= 20.0 - 1e-6 and lifted.warnings and "raised" in lifted.warnings[0]
    assert s["height"][0] == pytest.approx(300.0, abs=1e-6) and s["height"][-1] == pytest.approx(300.0, abs=1e-6)     # raised only near the hill
    assert np.min(s["load"]) > 0.4                                       # a push-over of at most 0.5 g


def test_terrain_following_keeps_its_clearance() -> None:
    run = _run([{"follow": {"clearance": 150}, "for": 150}], start={"x": 0, "z": 0, "height": 300, "heading": 0, "speed": 120}, context=HILL)
    t = np.linspace(10, 140, 2601)
    s = run.sample(t)
    assert np.min(s["above_ground"]) >= 150 + 20 - 1e-6 and np.max(s["height"]) > 900 + 150
    assert np.min(s["load"]) >= 0.5 - 1e-3                               # the push-over limit
    assert np.max(np.abs(s["climb"])) <= 0.3 * 120 + 1e-6


@pytest.mark.slow
def test_terrain_following_spans_legs_with_turns_and_levels_off_after() -> None:
    legs = [{"follow": {"clearance": 200}, "for": 20}, {"turn": {"by": 20, "bank": 30}, "follow": {"clearance": 250}}, {"follow": {"clearance": 200}, "for": 40}, {"straight": 5}]
    run = _run(legs, start={"x": -2000, "z": -5000, "height": 1200, "heading": 10, "speed": 120}, context=HILL)
    span_end = run.legs[2].end
    s = run.sample(np.linspace(15, span_end, 1000))
    assert np.min(s["above_ground"]) >= 200 + 20 - 1e-6 and np.min(s["height"]) < 500 and np.max(s["height"]) > 900      # down from 1,200 m, up over the hill's side
    after = run.sample(np.array([span_end, span_end + 10]))
    assert abs(after["climb"][0]) < 1e-4 and after["height"][1] == pytest.approx(after["height"][0], abs=1e-6)     # level after the span


def test_a_landing_on_the_sea() -> None:
    run = _run([{"land": {"glide": 3, "flare": 15, "touchdown": 64}}], start={"x": 0, "z": 0, "height": 400, "heading": 0, "speed": 80})
    leg = run.legs[0]
    touch = leg.notes["touchdown"]
    s = run.sample(np.array([touch - 60, touch, run.end, run.end + 10]))
    assert s["climb"][0] == pytest.approx(-64 * math.tan(math.radians(3)), abs=1e-6)
    assert s["height"][1] == pytest.approx(0.0, abs=1e-6) and s["climb"][1] == pytest.approx(0.0, abs=1e-6) and s["speed"][1] == pytest.approx(64.0, abs=1e-6)
    assert s["speed"][2] == pytest.approx(0.0, abs=1e-9) and s["height"][3] == pytest.approx(0.0, abs=1e-6)
    flare = run.sample(np.linspace(touch - 2 * 15 / s["climb"][0] * -1, touch, 50))
    assert flare["height"][0] == pytest.approx(15.0, abs=1e-3) and np.all(np.diff(flare["height"]) <= 1e-9)


# ----- re-entry ---------------------------------------------------------------------------------------------


def _orbit_start(height: float = 400e3) -> tuple[np.ndarray, np.ndarray]:
    r = EARTH.radius + height
    p0 = FRAME.chart(-3000e3, 0.0, height)
    e = FRAME.heading_vector(p0, 90.0)
    return p0, e * math.sqrt(EARTH.gm / r) - np.cross(F.spin_local(EARTH, FRAME), p0 - FRAME.centre)


def test_a_reentry_meets_the_orbit_and_the_flight() -> None:
    p0, v0 = _orbit_start(150e3)
    spec = F.Flight.model_validate({"name": "S", "start": {"orbit": "Ship"}, "legs": [{"reentry": {"to": {"height": 30000, "speed": 1200}, "blend": 150, "reversals": 2}}, {"straight": 10}]})
    run = F.FlightRun(spec, SEA, start_state=(p0, v0))
    entry = run.legs[0]
    s = run.sample(np.array([0.0]))
    np.testing.assert_allclose(s["position"][0], p0, atol=1e-6)
    np.testing.assert_allclose(s["velocity"][0], v0, atol=1e-6)
    end = run.sample(np.array([entry.end, entry.end + 10]))
    assert end["height"][0] == pytest.approx(30000.0, abs=1e-6) and end["speed"][0] == pytest.approx(1200.0, abs=1e-6) and abs(end["climb"][0]) < 1e-6
    assert end["height"][1] == pytest.approx(30000.0, abs=1e-6) and abs(end["bank"][0]) < math.radians(0.5)
    glide = run.sample(np.linspace(entry.notes["glide_start"], entry.end - 1, 300))
    assert np.all(np.diff(glide["height"]) < 0)
    banked = run.sample(np.linspace(entry.notes["glide_start"], entry.notes["glide_end"], 300))["bank"]
    assert math.degrees(np.max(banked)) == pytest.approx(60.0, abs=1e-6) and math.degrees(np.min(banked)) == pytest.approx(-60.0, abs=1e-6)
    joins = [0.0, entry.notes["glide_start"], entry.notes["glide_end"], entry.end]
    for at in joins[1:]:
        t = at + np.arange(-4, 5) * 0.5
        x = run.sample(t)
        assert np.max(np.linalg.norm(np.diff(x["acceleration"], n=2, axis=0), axis=-1)) < 0.05           # no kink in the acceleration where the parts meet


@pytest.mark.slow
def test_a_reentry_from_a_400_km_orbit_follows_the_orbit_first() -> None:
    from vidgen.orbits.elements import Elements

    p0, v0 = _orbit_start()
    spec = F.Flight.model_validate({"name": "S", "start": {"orbit": "Ship"}, "legs": [{"reentry": {"to": {"height": 12000, "speed": 250}, "blend": 400}}, {"straight": 30}]})
    run = F.FlightRun(spec, SEA, start_state=(p0, v0))
    entry = run.legs[0]
    s = run.sample(np.array([0.0, 2.0]))
    np.testing.assert_allclose(s["position"][0], p0, atol=1e-6)
    np.testing.assert_allclose(s["velocity"][0], v0, atol=1e-6)
    # in its first seconds the craft is on the orbit's own path (the turning world's view of a Kepler orbit)
    spin = F.spin_local(EARTH, FRAME)
    orbit = Elements.from_state(EARTH.gm, p0 - FRAME.centre, v0 + np.cross(spin, p0 - FRAME.centre))
    r2 = orbit.positions(2.0)
    w = float(np.linalg.norm(spin))
    k = spin / w
    turn = -w * 2.0
    rot = np.cos(turn) * np.eye(3) + np.sin(turn) * np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]]) + (1 - np.cos(turn)) * np.outer(k, k)
    assert np.linalg.norm(s["position"][1] - (FRAME.centre + rot @ r2)) < 0.01
    # the end: the flight state asked for, level, and the next leg goes on from it
    end = run.sample(np.array([entry.end, entry.end + 10]))
    assert end["height"][0] == pytest.approx(12000.0, abs=1e-6) and end["speed"][0] == pytest.approx(250.0, abs=1e-6) and abs(end["climb"][0]) < 1e-6
    assert end["height"][1] == pytest.approx(12000.0, abs=1e-6) and abs(end["bank"][0]) < math.radians(0.5)
    # the glide: height falling monotonically, the S-turns' bank, heating up there and not near the end
    glide = run.sample(np.linspace(entry.notes["glide_start"], entry.end - 1, 600))
    assert np.all(np.diff(glide["height"]) < 0)
    whole = run.sample(np.linspace(0, entry.end, 1200))
    hot = int(np.argmax(whole["heating"]))
    assert 0.3 < whole["heating"][hot] < 2 and whole["speed"][hot] > 5000 and whole["heating"][-1] < 0.01 and np.all(np.abs(whole["pitch"]) < math.radians(15))
    assert whole["mach"][0] > 20 and math.degrees(whole["aoa"][hot]) == pytest.approx(40.0, abs=1e-6)


# ----- the data for the page ----------------------------------------------------------------------------------


SETTINGS = {"ground": "sea", "at": [-34.5, 20], "flights": [{"name": "Plane", "start": {"x": -2000, "z": 0, "height": 800, "heading": 90, "speed": 120},
            "legs": [{"straight": 0.5}, {"turn": {"by": 45, "bank": 40}}]}, {"name": "Two", "start": {"lat": -34.4, "lon": 20.1, "height": 2000, "speed": 200}}]}


def _f64(text: str, width: int = 1) -> np.ndarray:
    a = np.frombuffer(base64.b64decode(text), "<f8")
    return a.reshape(-1, width) if width > 1 else a


def test_the_data_is_the_runs_on_every_frame_and_is_deterministic() -> None:
    s = fd.FlightData.model_validate(SETTINGS)
    data = fd.make_flight_data(s, 10, 42, 40)
    assert data["frame"] == "local" and data["anchor"]["lat"] == -34.5 and data["world"]["name"] == "earth" and data["speedup"] == 1
    plane = next(f for f in data["flights"] if f["name"] == "Plane")
    times = _f64(plane["time"])
    assert len(times) == 42 and times[40] == 4.0 and times[41] == 4.0
    run = F.FlightRun(s.flights[0], F.FlightContext(EARTH, FRAME, F.SeaGround("sea", "x"), 20.0))
    ref = run.sample(times)
    np.testing.assert_array_equal(_f64(plane["position"], 3), ref["position"])
    np.testing.assert_array_equal(_f64(plane["speed"]), ref["speed"])
    q = _f64(plane["quaternion"], 4)
    assert np.allclose(np.linalg.norm(q, axis=-1), 1) and np.all(q[:, 3] >= 0)
    assert [leg["kind"] for leg in plane["legs"]] == ["straight", "turn"] and plane["legs"][1]["scene_start"] == pytest.approx(0.5)
    assert json.dumps(data) == json.dumps(fd.make_flight_data(fd.FlightData.model_validate(SETTINGS), 10, 42, 40))
    later = fd.make_flight_data(fd.FlightData.model_validate({**SETTINGS, "start": 1.0}), 10, 42, 40)
    lt = _f64(next(f for f in later["flights"] if f["name"] == "Plane")["time"])
    assert lt[0] == -1.0 and lt[10] == 0.0 and np.array_equal(_f64(later["flights"][0]["position"], 3)[0], _f64(later["flights"][0]["position"], 3)[10])


def test_times_in_bars_and_a_start_from_orbit_data() -> None:
    from vidgen.scenes import orbit_data as od

    music = {"t0": 2.0, "score": {"bar": 2.0, "beat": 0.5}}
    assert fd.scene_seconds("bar 3 beat 2", music) == pytest.approx(2 * 2.0 + 0.5 - 2.0)
    with pytest.raises(VidgenError, match="needs the score"):
        fd.scene_seconds("bar 3", None)
    s = fd.FlightData.model_validate({**SETTINGS, "flights": [{**SETTINGS["flights"][0], "legs": [{"straight": 0.5}, {"until": "bar 3"}]}]})
    data = fd.make_flight_data(s, 10, 42, 40, music=music)
    assert data["flights"][0]["legs"][1]["scene_end"] == pytest.approx(2.0)
    orbit = od.OrbitData.model_validate({"central": "earth", "bodies": [{"name": "Ship", "altitude": "400 km", "e": 0, "i": 51.6}], "speedup": 1})
    payload = od.make_orbit_data(orbit, 10, 42, 40)
    entry = fd.FlightData.model_validate({"ground": "sea", "flights": [{"name": "Ship", "start": {"orbit": "Ship", "at": 1.0}, "legs": [{"reentry": {"to": {"height": 40000, "speed": 2500}, "blend": 100}}]}]})
    got = fd.make_flight_data(entry, 10, 42, 40, orbits=payload)
    ship = got["flights"][0]
    body = next(b for b in payload["bodies"] if b["name"] == "Ship")
    frame = F.LocalFrame(0.0, 0.0, EARTH.radius)
    jd = payload["jd0"] + _f64(payload["time"])[10] / 86400
    r, v = frame.to_ecliptic(EARTH, _f64(ship["position"], 3)[10:11], _f64(ship["velocity"], 3)[10:11], np.array([jd]))
    np.testing.assert_allclose(r[0], _f64(body["position"], 3)[10], atol=1e-5)           # where the orbit data has the ship at the hand-over
    np.testing.assert_allclose(v[0], _f64(body["velocity"], 3)[10], atol=1e-8)
    assert ship["legs"][0]["kind"] == "reentry" and ship["start"] == 1.0


def test_the_cache_and_its_key(make_project: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(make_project, SETTINGS)
    s = fd.FlightData.model_validate(SETTINGS)
    first = wf.scene_flight_data(project, s, 10, 22, 20)
    key = wf.flight_data_key(s, 10, 22, 20)
    assert (project.build_dir / "flights" / f"flight-data-{key}.json").is_file()
    monkeypatch.setattr(fd, "make_flight_data", lambda *a, **k: pytest.fail("made again"))
    assert wf.scene_flight_data(project, s, 10, 22, 20) == first
    other = fd.FlightData.model_validate({**SETTINGS, "margin": 30})
    turned = fd.FlightData.model_validate({**SETTINGS, "flights": [{**SETTINGS["flights"][0], "legs": [{"straight": 0.5}, {"turn": {"by": 46, "bank": 40}}]}]})
    keys = {key, wf.flight_data_key(other, 10, 22, 20), wf.flight_data_key(turned, 10, 22, 20), wf.flight_data_key(s, 30, 22, 20), wf.flight_data_key(s, 10, 23, 20)}
    assert len(keys) == 5


def test_only_scenes_with_flights_get_the_flight_helper_in_their_clip_key(make_project: Any) -> None:
    from vidgen.web.clip import clip_inputs
    from vidgen.web.entry import entry_of
    from vidgen.web.music import payload_digest
    from vidgen.web.orbits import helper_digest

    project = _project(make_project, SETTINGS)
    entry = entry_of({"script": "x.js"})
    flights = fd.make_flight_data(fd.FlightData.model_validate(SETTINGS), 10, 22, 20)
    payload = wf.with_flights(None, flights)
    inputs = clip_inputs(project.root, entry, scene_id="fly", size=(160, 90), fps=10, frames=20, orbits=payload)
    assert inputs["orbits"] == {"data": payload_digest(payload), "helper": helper_digest(), "flight_helper": wf.helper_digest()}
    plain = clip_inputs(project.root, entry, scene_id="fly", size=(160, 90), fps=10, frames=20, orbits={"bodies": []})
    assert "flight_helper" not in plain["orbits"]


def _project(make_project: Any, flight_data: Any, extra: dict[str, Any] | None = None) -> Project:
    config = {"title": "F", "format": {"width": 160, "height": 90, "fps": 10}, "preview": {"width": 80, "height": 46, "fps": 10},
              "transition": "cut", "scenes": [{"id": "fly", "type": "web", "duration": 2, "params": {"script": "x.js", "flight_data": flight_data, **(extra or {})}}]}
    root = make_project(config)
    (root / "x.js").write_text("export function frame() {}\n", encoding="utf-8")
    return Project.load(root)


def test_validation_with_did_you_mean(make_project: Any) -> None:
    from vidgen.cli import check_project

    bad = {**SETTINGS, "flights": [{**SETTINGS["flights"][0], "legs": [{"trun": {"by": 10}}]}]}
    project = _project(make_project, bad)
    with extensions.project_session(project):
        problems = check_project(project)
    assert any("flight_data" in p and "trun" in p and "did you mean" in p and "turn" in p for p in problems), problems
    with pytest.raises(ValueError, match="did you mean 'alpine'"):
        fd.FlightData.model_validate({"ground": {"land": "alpin"}, "flights": SETTINGS["flights"][:1]})
    with pytest.raises(ValueError, match="mountains: unknown key 'hieght'"):
        fd.FlightData.model_validate({"ground": {"land": {"preset": "alpine", "mountains": {"hieght": 1}}}, "flights": SETTINGS["flights"][:1]})
    with pytest.raises(ValueError, match="two flights are called"):
        fd.FlightData.model_validate({**SETTINGS, "flights": [SETTINGS["flights"][0], SETTINGS["flights"][0]]})
    with pytest.raises(ValueError, match="not a time"):
        fd.FlightData.model_validate({**SETTINGS, "start": "bar nine"})
    with pytest.raises(ValueError, match="a leg has one horizontal manoeuvre"):
        F.Leg.model_validate({"turn": {"by": 10}, "circle": {"around": [0, 0], "radius": 10}})
    with pytest.raises(ValueError, match="give to .* or by"):
        F.Leg.model_validate({"turn": {"bank": 10}})
    bars = _project(make_project, {**SETTINGS, "start": "bar 2"})
    with extensions.project_session(bars):
        assert any("need the score on the page" in p for p in check_project(bars))
    orbit = _project(make_project, {"ground": "sea", "flights": [{"name": "S", "start": {"orbit": "Shp"}, "legs": []}]},
                     {"orbit_data": {"central": "earth", "bodies": [{"name": "Ship", "altitude": "400 km"}], "span": "1 h"}})
    with extensions.project_session(orbit):
        assert any("no body 'Shp'" in p and "did you mean 'Ship'" in p for p in check_project(orbit))
    with pytest.raises(ValueError, match="flat world"):
        fd.FlightData.model_validate({"ground": "flat", "at": [1, 2], "flights": SETTINGS["flights"][:1]})


# ----- the ground's heights: the numpy port of vidgen/space-land -------------------------------------------


def test_the_numpy_heights_are_the_javascript_recipes(tmp_path: Path) -> None:
    from test_web_space_land import _run_in_node

    out = _run_in_node(tmp_path, """
const B = await import('vidgen/space-bodies');
const rnd = (i) => { const x = Math.sin(i * 12.9898) * 43758.5453; return x - Math.floor(x); };
for (const [name, p] of Object.entries(L.PRESETS)) {
  const world = B.resolveOptions(p.world), changes = {};
  for (const k of ["mountains", "rough", "strata", "dunes", "craters", "canyons", "volcanoes", "materials"]) if (p[k] !== undefined) changes[k] = {...p[k]};
  const recipe = L.recipeOf(world.type, changes, world.seed), n = 9, fields = new Float32Array(n * n * 4);
  for (let i = 0; i < n * n; i++) fields[4 * i] = 2 * rnd(i + 1) - 1;
  const macro = {n, spacing: 9000, scale: 1500, fields}, field = {macro, recipe};
  const points = Array.from({length: 300}, (_, i) => [(rnd(3 * i + 7) - 0.5) * (i < 150 ? 1.2e5 : 6000), (rnd(3 * i + 8) - 0.5) * (i < 150 ? 1.2e5 : 6000)]);
  out.push({name, recipe, macro: {n, spacing: 9000, scale: 1500, heights: Array.from({length: n * n}, (_, i) => fields[4 * i])}, points, heights: points.map(([x, z]) => L.heightOf(field, x, z)),
            hashes: [L.hash2(-7, 123456, 9), L.hash2(2 ** 31 - 1, -(2 ** 31), 65535)], noise: points.slice(0, 20).map(([x, z]) => L.noised(x / 777, z / 777, 41)[0])});
}
""")
    assert [o["name"] for o in out] == ["alpine", "mars", "canyon", "dunes", "snow", "volcanic", "airless"]
    worst = 0.0
    for o in out:
        pts = np.array(o["points"])
        mine = F.height_of({"recipe": o["recipe"], "macro": o["macro"]}, pts[:, 0], pts[:, 1])
        js = np.array(o["heights"])
        assert np.all(np.isfinite(js)) and np.ptp(js) > 10
        worst = max(worst, float(np.max(np.abs(mine - js))))
        assert [int(F.hash2(-7, 123456, 9)), int(F.hash2(2**31 - 1, -(2**31), 65535))] == o["hashes"]
        np.testing.assert_allclose(F.noise(pts[:20, 0] / 777, pts[:20, 1] / 777, 41), o["noise"], rtol=0, atol=1e-14)
    assert worst < 1e-9, worst


# ----- in Chromium -------------------------------------------------------------------------------------------


PAGE = """
import * as THREE from "three";
import {craft} from "vidgen/space-craft";
let ship;
export function load(ctx) {
  const f = ctx.flight;
  window.__out = {names: f.names, frame: f.frame, units: f.units, orbits: ctx.orbits === undefined, legs: f.legs('Plane').length, path: f.path('Plane').length, rows: []};
  try { f.position('Nope'); } catch (e) { window.__out.error = e.message; }
  ship = craft("probe", {seed: 1});
  ship.fly(f, {flight: "Plane"});
  try { craft("probe", {seed: 1}).fly(f, {flight: "Plain"}); } catch (e) { window.__out.flyError = e.message; }
}
export function frame(t, ctx) {
  const f = ctx.flight;
  ship.update(t);
  window.__out.rows.push({index: f.index(), time: f.time('Plane'), p: f.position('Plane'), v: f.velocity('Plane'), q: f.quaternion('Plane'), mach: f.mach('Plane'),
                          above: f.aboveGround('Plane'), bank: f.bank('Plane'), heating: f.heating('Plane'), craftP: ship.object.position.toArray(), craftQ: ship.object.quaternion.toArray()});
  const g = ctx.canvas.getContext('2d');
}
"""


@pytest.mark.slow
@pytest.mark.render
def test_the_page_receives_the_numbers_python_computed(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "x.js").write_text(PAGE, encoding="utf-8")
    data = fd.make_flight_data(fd.FlightData.model_validate(SETTINGS), 10, 22, 20)
    frames = [0, 7, 21]
    with WebPage(tmp_path, WebEntry("script", "x.js"), scene_id="fly", size=(32, 18), fps=10, frames=22, orbits=wf.with_flights(None, data)) as page:
        for n in frames:
            page.frame(n)
        out = page._page.evaluate("window.__out")
    assert out["names"] == ["Plane", "Two"] and out["frame"] == "local" and out["units"]["length"] == "m" and out["orbits"] is True
    assert out["legs"] == 2 and out["path"] == 256 and "no flight 'Nope'" in out["error"] and 'did you mean "Plane"' in out["flyError"]
    plane = data["flights"][0]
    for n, row in zip(frames, out["rows"][-len(frames):]):
        assert row["index"] == n and row["time"] == _f64(plane["time"])[n]
        assert row["p"] == _f64(plane["position"], 3)[n].tolist() and row["v"] == _f64(plane["velocity"], 3)[n].tolist()        # exactly: float64 throughout
        assert row["q"] == _f64(plane["quaternion"], 4)[n].tolist() and row["mach"] == _f64(plane["mach"])[n]
        assert row["above"] == _f64(plane["above_ground"])[n] and row["bank"] == _f64(plane["bank"])[n] and row["heating"] == _f64(plane["heating"])[n]
        np.testing.assert_allclose(row["craftP"], row["p"], rtol=1e-7)            # craft.fly: three.js keeps float32 positions
        np.testing.assert_allclose(row["craftQ"], row["q"], atol=1e-7)


@pytest.mark.slow
@pytest.mark.render
def test_the_pages_heights_are_the_numpy_ports_for_every_preset() -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.land import page_heights
    from vidgen.web.space_names import constant_keys

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    rng = np.random.default_rng(385)
    worst = 0.0
    for preset in constant_keys("vidgen/space-land", "PRESETS"):
        points = np.concatenate([rng.uniform(-60000, 60000, (150, 2)), rng.uniform(-3000, 3000, (150, 2))])
        got = page_heights({"preset": preset}, None, points.tolist())
        mine = F.height_of(got["definition"], points[:, 0], points[:, 1])
        worst = max(worst, float(np.max(np.abs(mine - np.array(got["heights"])))))
        assert got["definition"]["macro"]["n"] == 384 and np.ptp(got["heights"]) > 100
    assert worst < 1e-9, worst


def test_the_grounds_definition_is_kept_in_vidgens_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from vidgen.cli import main
    from vidgen.web import land

    monkeypatch.setenv("VIDGEN_CACHE_DIR", str(tmp_path))
    asked: list[Any] = []
    fake = {"radius": 6.371e6, "recipe": {"bound": {"over": 1.0}}, "macro": {"n": 2, "spacing": 1.0, "scale": 2.0, "heights": [0.0, 0.5, 1.0, 1.5]}}
    monkeypatch.setattr(land, "page_heights", lambda options, air=None, points=None: asked.append((options, air)) or {"definition": fake, "heights": []})
    first = land.land_definition({"preset": "alpine"}, "earth")
    again = land.land_definition({"preset": "alpine"}, "earth")
    land.land_definition({"preset": "alpine", "seed": 4}, "earth")
    assert len(asked) == 2 and np.array_equal(first["macro"]["heights"], again["macro"]["heights"]) and first["macro"]["heights"].dtype == float
    assert land.definition_key({"preset": "alpine"}, "earth") != land.definition_key({"preset": "alpine"}, "mars")
    assert len(list((tmp_path / "ground").glob("land-*.json"))) == 2
    assert main(["cache", "clear"]) == 0
    assert "removed 2 ground height definitions" in capsys.readouterr().out and not list((tmp_path / "ground").glob("land-*.json"))
