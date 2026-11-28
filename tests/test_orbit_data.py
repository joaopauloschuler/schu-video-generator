"""Orbit data for ``web`` scenes (Step 367): the numbers the page is given are
the orbit model's (and the flat ``orbit`` scene's), per frame on vidgen's clock, in the ecliptic
frame; rotation, planes, a ship's burns, a flyby, n-body; the cache and the keys; ``ctx.orbits``
on a page."""

from __future__ import annotations

import base64
import json
import math
from typing import Any

import numpy as np
import pytest

from vidgen import extensions, orbits
from vidgen.errors import VidgenError
from vidgen.orbits import rotation as rot
from vidgen.project import Project
from vidgen.scenes import orbit_data as od
from vidgen.web import orbits as wo

PLANETS = [{"preset": p} for p in ("mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune")]
TRANSFER = {"bodies": [{"preset": "earth", "e": 0, "i": 0, "raan": 0, "argp": 0}, {"preset": "mars", "e": 0, "i": 0, "raan": 0, "argp": 0, "nu": 95},
                       {"name": "Ship", "alongside": "Earth"}], "transfer": {"ship": "Ship", "to": "Mars"}}


def _f64(b64: str, n: int = 3) -> np.ndarray:
    a = np.frombuffer(base64.b64decode(b64), "<f8")
    return a.reshape(-1, n) if n > 1 else a


def _body(data: dict[str, Any], name: str) -> dict[str, Any]:
    return next(b for b in data["bodies"] if b["name"] == name)


def _data(settings: dict[str, Any], fps: int = 10, frames: int = 52, scene_frames: int = 50) -> tuple[od.OrbitData, dict[str, Any]]:
    s = od.OrbitData.model_validate(settings)
    return s, od.make_orbit_data(s, fps, frames, scene_frames)


# ----- the numbers are the model's ------------------------------------------------------------------


def test_positions_and_velocities_are_the_orbit_models_on_every_frame() -> None:
    s, data = _data({"bodies": [*PLANETS, {"preset": "moon", "around": "Earth", "nu": 30}], "span": "1 yr", "date": "2026-11-17"})
    model = s.model(None)
    times = _f64(data["time"], 1)
    assert data["frame"] == od.ECLIPTIC_FRAME and data["units"]["length"] == "m" and len(times) == 52
    assert times[0] == 0 and times[50] == model.span and times[51] == model.span   # one speed-up to the scene's end, then held
    assert data["jd0"] == orbits.julian_date("2026-11-17")
    for o in model.system.orbiters:
        b = _body(data, o.name)
        np.testing.assert_array_equal(_f64(b["position"]), model.position(o.name, times))
        np.testing.assert_array_equal(_f64(b["velocity"]), model.velocity(o.name, times))
        assert b["plane"] == "ecliptic"
    assert _body(data, "Moon")["parent"] == "Earth" and _body(data, "Earth")["parent"] == "Sun"
    assert data["bodies"][0]["name"] == "Sun" and not np.any(_f64(data["bodies"][0]["position"]))


def test_the_flat_orbit_scenes_numbers_are_the_same() -> None:
    from vidgen.scenes.orbit import Orbit

    settings = {"bodies": PLANETS[:4], "span": "200 d", "date": "2030-01-01"}
    flat = Orbit.Params.model_validate({"title": "x", **settings}).model()
    _, data = _data(settings)
    times = _f64(data["time"], 1)
    for o in flat.system.orbiters:
        np.testing.assert_array_equal(_f64(_body(data, o.name)["position"]), flat.position(o.name, times))


def test_heliocentric_positions_on_the_date_are_jpl_table_1s() -> None:
    _, data = _data({"bodies": PLANETS, "span": "30 d", "date": "2026-11-17"})
    for p in PLANETS:
        b = next(x for x in data["bodies"] if x["key"] == p["preset"])
        first = _f64(b["position"])[0]
        assert np.linalg.norm(first - orbits.heliocentric(p["preset"], data["jd0"])) < 1e-6 * np.linalg.norm(first)


def test_speedup_and_span() -> None:
    _, data = _data({"bodies": PLANETS[2:3], "speedup": 86400.0}, fps=10, frames=22, scene_frames=20)
    times = _f64(data["time"], 1)
    assert data["span"] == 2 * 86400.0 and data["speedup"] == 86400.0
    assert times[10] == pytest.approx(86400.0, rel=1e-15) and times[21] == data["span"]
    _, data = _data({"bodies": PLANETS[2:3]}, fps=10, frames=22, scene_frames=20)   # default: one orbit of the first body
    assert data["span"] == pytest.approx(orbits.ORBITS["earth"].a ** 1.5 * 2 * math.pi / math.sqrt(orbits.GM_SUN + orbits.GM_EARTH), rel=1e-12)


def test_settings_errors() -> None:
    with pytest.raises(ValueError, match="give one of span, orbits or speedup"):
        od.OrbitData.model_validate({"bodies": PLANETS[:1], "span": "1 yr", "speedup": 10})
    with pytest.raises(ValueError, match="no body 'Erth'.*did you mean 'Earth'"):
        od.OrbitData.model_validate({"bodies": PLANETS[2:3], "planes": {"Erth": "ecliptic"}})
    with pytest.raises(ValueError, match="n-body run keeps every body"):
        od.OrbitData.model_validate({"central": "earth", "bodies": [{"preset": "moon"}], "dynamics": "nbody", "planes": {"Moon": "equator"}})
    with pytest.raises(ValueError, match="unknown preset 'marz'"):
        od.OrbitData.model_validate({"bodies": [{"preset": "marz"}]})
    with pytest.raises(ValueError, match="Ship is measured from the ecliptic and Moon from the equator"):
        od.OrbitData.model_validate({"central": "earth", "bodies": [{"preset": "moon", "e": 0, "i": 0}, {"name": "Ship", "altitude": "400 km"}],
                                     "planes": {"Moon": "equator", "Ship": "ecliptic"}, "transfer": {"ship": "Ship", "to": "Moon"}})


# ----- planes and rotation --------------------------------------------------------------------------


def test_equatorial_orbits_are_turned_into_the_ecliptic() -> None:
    s, data = _data({"central": "earth", "bodies": [{"preset": "geo"}, {"preset": "iss"}, {"preset": "moon"}], "span": "1 d"},
                    fps=10, frames=101, scene_frames=100)
    assert [b["plane"] for b in data["bodies"]] == ["central", "equator", "equator", "ecliptic"]
    assert math.degrees(_body(data, "GEO satellite")["orbit"]["i"]) == pytest.approx(rot.OBLIQUITY_J2000_DEG, abs=1e-9)
    model = s.model(None)
    times = _f64(data["time"], 1)
    np.testing.assert_array_equal(_f64(_body(data, "Moon")["position"]), model.position("Moon", times))   # the ecliptic one untouched
    turn = rot.equator_frame(rot.ROTATIONS["earth"], data["jd0"])
    assert np.allclose(_f64(_body(data, "ISS")["position"]), model.position("ISS", times) @ turn.T, rtol=0, atol=1e-6)
    # a geostationary satellite stays over one longitude of the turning Earth
    q = _f64(data["bodies"][0]["quaternion"], 4)
    geo = _f64(_body(data, "GEO satellite")["position"])
    longitudes = []
    for (x, y, z, w), p in zip(q, geo):
        frame = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                          [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                          [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        fixed = frame.T @ p
        longitudes.append(math.degrees(math.atan2(fixed[1], fixed[0])))
        assert abs(fixed[2]) < 1e-6 * np.linalg.norm(p)   # over the equator
    assert np.ptp(longitudes) < 1e-3


def test_a_locked_moon_faces_its_planet_and_planets_turn_at_their_period() -> None:
    _, data = _data({"bodies": [{"preset": "earth"}, {"preset": "moon", "around": "Earth"}], "span": "27 d"}, fps=10, frames=60, scene_frames=58)
    moon, earth = _body(data, "Moon"), _body(data, "Earth")
    assert moon["rotation"]["faces_parent"] and moon["rotation"]["synchronous"]
    rel = _f64(moon["position"]) - _f64(earth["position"])
    for (x, y, z, w), r in zip(_f64(moon["quaternion"], 4), rel):
        body_x = np.array([1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w)])
        assert body_x @ (-r / np.linalg.norm(r)) > math.cos(math.radians(7))   # the prime meridian points at the Earth (on the equator: up to the 6.7° tilt off)
    spin = _f64(earth["spin"], 1)
    times = _f64(data["time"], 1)
    expected = np.radians(rot.ROTATIONS["earth"].prime_meridian(data["jd0"] + times / 86400))
    np.testing.assert_allclose(spin, expected, rtol=0, atol=1e-12)
    assert earth["rotation"]["obliquity"] == pytest.approx(23.44, abs=0.01) and earth["rotation"]["period"] == pytest.approx(86164.1, abs=0.1)


# ----- spacecraft --------------------------------------------------------------------------------------


def test_a_ship_on_a_transfer_is_a_body_with_a_path_and_burns() -> None:
    s, data = _data(TRANSFER, fps=10, frames=202, scene_frames=200)
    model = s.model(None)
    ship = _body(data, "Ship")
    times = _f64(data["time"], 1)
    np.testing.assert_array_equal(_f64(ship["position"]), model.position("Ship", times))
    np.testing.assert_array_equal(_f64(ship["velocity"]), model.velocity("Ship", times))
    burns = ship["burns"]
    assert [b["number"] for b in burns] == [1, 2]
    assert burns[0]["magnitude"] == pytest.approx(model.transfer.result.dv1) and burns[0]["direction"] == "prograde"
    for b in burns:
        assert times[b["frame"]] >= b["time"] and (b["frame"] == 0 or times[b["frame"] - 1] < b["time"])
    path = _f64(ship["path"])
    assert len(path) == s.path_samples and np.allclose(path[0], model.position("Ship", 0.0))
    assert ship["orbit"]["period"] == pytest.approx(model.system.orbiter("Ship").elements.period)


def test_a_span_that_ends_before_the_second_burn_shows_the_departure_alone() -> None:
    """Step 378 (Outbound wrote its burn by hand): ``transfer`` with a span that ends between the two burns is a
    shot of the departure; a span that ends before the first burn is refused with a way out."""
    leo = {"central": "earth", "bodies": [{"name": "Ship", "altitude": "2000 km"}, {"name": "Far", "altitude": "300000 km"}]}
    s, data = _data({**leo, "transfer": {"ship": "Ship", "to": "Far", "depart": "2 min"}, "span": "30 min"}, fps=10, frames=52, scene_frames=50)
    burns = _body(data, "Ship")["burns"]
    assert burns[0]["magnitude"] == pytest.approx(s.model(None).transfer.result.dv1) and burns[0]["frame"] is not None
    assert all(b["frame"] is None for b in burns[1:]) or len(burns) == 1
    with pytest.raises(ValueError, match=r"first burn at .* comes after the scene's span .* give transfer.depart a time inside it"):
        _data({**leo, "transfer": {"ship": "Ship", "to": "Far"}, "span": "10 min"})


def test_a_dated_speedup_is_checked_with_its_own_span() -> None:
    """Step 378: with a speed-up the validation's default span (one period of Halley's comet: 76 years) is a
    stand-in; its end date is not refused, while the data made for the scene's length is checked."""
    settings = {"central": "sun", "date": "1986-02-09", "speedup": 200000, "bodies": [{"preset": "halley", "name": "Halley", "nu": -60}]}
    s, data = _data(settings, fps=10, frames=82, scene_frames=80)       # 8 s: 18.5 days of 1986
    assert data["date"].startswith("1986-02-09")
    with pytest.raises(VidgenError, match="outside 1800-2050"):
        _data({**settings, "speedup": 2e9}, fps=10, frames=82, scene_frames=80)     # 8 s: 500 years


def test_a_flyby_probe_is_a_body_in_the_planets_frame() -> None:
    s, data = _data({"central": "jupiter", "flyby": {"v_inf": "5.6 km/s", "altitude": "200000 km"}})
    assert data["frame"] == od.FLYBY_FRAME and [b["name"] for b in data["bodies"]] == ["Jupiter", "Probe"]
    probe = _body(data, "Probe")
    model = s.model(None)
    np.testing.assert_array_equal(_f64(probe["position"]), model.position("Probe", _f64(data["time"], 1)))
    assert probe["orbit"]["kind"] == "hyperbola" and probe["plane"] == "as_written"
    assert any("patched conics" in a for a in data["approximations"])
    # Step 378: the planet's pole is turned into the flyby's frame (x along its motion on the date, z its orbit's north),
    # and a space scene's default sun stands where the Sun is in that frame (the y side, the planet's orbit near circular)
    s, data = _data({"central": "saturn", "date": "2033-04-08", "flyby": {"v_inf": "5.44 km/s", "altitude": "110000 km"}})
    jd = orbits.ephemeris.julian_date("2033-04-08")
    axes = orbits.ephemeris.flyby_axes("saturn", jd)
    pole = np.array(_body(data, "Saturn")["rotation"]["pole"])
    np.testing.assert_allclose(pole, axes @ rot.ROTATIONS["saturn"].pole(np.array([jd]))[0], atol=1e-12)
    assert np.allclose(axes @ axes.T, np.eye(3), atol=1e-12) and abs(pole[2]) < 0.95          # tilted 27 degrees from the flyby plane's north
    from vidgen.scenes import space_page
    from vidgen.scenes.space import Space
    params = Space.Params.model_validate({"orbits": {"central": "saturn", "date": "2033-04-08", "flyby": {"v_inf": "5.44 km/s", "altitude": "110000 km"}}, "camera": {"move": "look", "from": [1e9, 0, 0], "to": "Saturn"}})
    sun = space_page.sun_direction(params)
    assert sun is not None and sun[1] > 0.999 and abs(sun[2]) < 1e-9


def test_an_n_body_run_gives_the_runs_positions() -> None:
    s, data = _data({"central": "sun", "bodies": [{"preset": "jupiter"}, {"preset": "saturn"}], "dynamics": "nbody", "span": "20 yr"})
    model = s.model(None)
    times = _f64(data["time"], 1)
    np.testing.assert_array_equal(_f64(_body(data, "Saturn")["position"]), model.run.position("Saturn", times))
    assert data["dynamics"] == "nbody"


# ----- cache, keys, the scene ------------------------------------------------------------------------------


def _project(make_project: Any, orbit_data: Any) -> Project:
    config = {"title": "O", "format": {"width": 160, "height": 90, "fps": 10}, "preview": {"width": 80, "height": 46, "fps": 10},
              "transition": "cut", "scenes": [{"id": "plain", "type": "web", "duration": 2, "params": {"script": "x.js"}},
                                              {"id": "sky", "type": "web", "duration": 2, "params": {"script": "x.js", "orbit_data": orbit_data}}]}
    root = make_project(config)
    (root / "x.js").write_text("export function frame() {}\n", encoding="utf-8")
    return Project.load(root)


def test_the_data_is_cached_and_its_key_follows_the_settings(make_project: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(make_project, {"bodies": PLANETS[:2], "span": "30 d"})
    s = od.OrbitData.model_validate({"bodies": PLANETS[:2], "span": "30 d"})
    first = wo.scene_orbit_data(project, s, 10, 22, 20)
    key = wo.orbit_data_key(s, 10, 22, 20)
    assert (project.build_dir / "orbits" / f"orbit-data-{key}.json").is_file()
    assert json.loads(json.dumps(od.make_orbit_data(s, 10, 22, 20))) == first
    monkeypatch.setattr(od, "make_orbit_data", lambda *a: pytest.fail("made again"))
    assert wo.scene_orbit_data(project, s, 10, 22, 20) == first
    other = od.OrbitData.model_validate({"bodies": PLANETS[:2], "span": "31 d"})
    assert len({key, wo.orbit_data_key(other, 10, 22, 20), wo.orbit_data_key(s, 30, 22, 20), wo.orbit_data_key(s, 10, 23, 20)}) == 4


def test_the_data_is_deterministic() -> None:
    s = od.OrbitData.model_validate(TRANSFER)
    assert json.dumps(od.make_orbit_data(s, 10, 30, 28)) == json.dumps(od.make_orbit_data(s, 10, 30, 28))


def test_only_scenes_with_orbit_data_get_orbits_in_their_clip_key(make_project: Any) -> None:
    from vidgen.web.clip import clip_inputs
    from vidgen.web.entry import entry_of
    from vidgen.web.music import payload_digest
    from vidgen.web.orbits import helper_digest

    project = _project(make_project, {"bodies": PLANETS[:1], "span": "30 d"})
    entry = entry_of({"script": "x.js"})
    plain = clip_inputs(project.root, entry, scene_id="plain", size=(160, 90), fps=10, frames=20)
    assert "orbits" not in plain
    data = od.make_orbit_data(od.OrbitData.model_validate({"bodies": PLANETS[:1], "span": "30 d"}), 10, 22, 20)
    with_orbits = clip_inputs(project.root, entry, scene_id="sky", size=(160, 90), fps=10, frames=20, orbits=data)
    assert with_orbits["orbits"] == {"data": payload_digest(data), "helper": helper_digest()}
    assert {k: v for k, v in with_orbits.items() if k not in ("orbits", "scene")} == {k: v for k, v in plain.items() if k != "scene"}


def test_a_web_scene_validates_its_orbit_data(make_project: Any) -> None:
    from vidgen.cli import check_project

    project = _project(make_project, {"bodies": [{"preset": "marz"}]})
    with extensions.project_session(project):
        problems = check_project(project)
    assert any("orbit_data" in p and "unknown preset 'marz'" in p for p in problems)


# ----- the page -----------------------------------------------------------------------------------------

PAGE = """
export function load(ctx) {
  const o = ctx.orbits;
  window.__out = {names: o.names, frame: o.frame, fps: o.fps, frames: o.frames, units: o.units, plane: o.bodies.Ship.plane,
                  burns: o.burns('Ship').length, path: o.path('Ship').length, conic: o.conic('Earth').length, rows: []};
  try { o.position('Nope'); } catch (e) { window.__out.error = e.message; }
  window.__out.yUp = o.yUp([1, 2, 3]);
}
export function frame(t, ctx) {
  const o = ctx.orbits;
  window.__out.rows.push({t, index: o.index(), time: o.time(), ship: o.position('Ship'), shipV: o.velocity('Ship'), mars: o.position('Mars'),
                          q: o.quaternion('Earth'), spin: o.spin('Earth'), shipQ: o.quaternion('Ship')});
  const g = ctx.canvas.getContext('2d');
  g.fillStyle = '#000'; g.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
}
"""


@pytest.mark.slow
@pytest.mark.render
def test_the_page_receives_the_numbers_python_computed(make_project: Any) -> None:
    from vidgen.browser import chromium
    from vidgen.web.entry import entry_of
    from vidgen.web.page import WebPage

    pytest.importorskip("playwright.sync_api")
    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    project = _project(make_project, TRANSFER)
    (project.root / "x.js").write_text(PAGE, encoding="utf-8")
    data = od.make_orbit_data(od.OrbitData.model_validate(TRANSFER), 10, 22, 20)
    frames = [0, 7, 21]
    with WebPage(project.root, entry_of({"script": "x.js"}), scene_id="sky", size=(32, 18), fps=10, frames=22, orbits=data) as page:
        for n in frames:
            page.frame(n)
        out = page._page.evaluate("window.__out")
    assert out["names"] == ["Sun", "Earth", "Mars", "Ship"] and out["frame"] == "ecliptic_j2000" and out["units"]["length"] == "m"
    assert out["burns"] == 2 and out["path"] == 256 and out["conic"] == 361 and out["plane"] == "ecliptic"
    assert "no body 'Nope'" in out["error"] and out["yUp"] == [1, 3, -2]
    ship, mars, earth = _body(data, "Ship"), _body(data, "Mars"), _body(data, "Earth")
    rows = out["rows"][-len(frames):]
    for n, row in zip(frames, rows):
        assert row["index"] == n
        assert row["time"] == _f64(data["time"], 1)[n]
        assert row["ship"] == _f64(ship["position"])[n].tolist() and row["shipV"] == _f64(ship["velocity"])[n].tolist()   # exactly: float64 throughout
        assert row["mars"] == _f64(mars["position"])[n].tolist()
        assert row["q"] == _f64(earth["quaternion"], 4)[n].tolist() and row["spin"] == _f64(earth["spin"], 1)[n]
        assert row["shipQ"] is None
