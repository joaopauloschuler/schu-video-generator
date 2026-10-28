"""The ``orbit`` scene type (Phase X, Step 229; DESIGN §98): params and their errors, the
resolved model, targets, Kepler's second law from the scene's own timing, and tiny renders in
16:9 and 9:16."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import render
from vidgen import extensions, orbits, registry
from vidgen.cli import project_problems
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}
COMET = {"title": "A comet", "central": "sun", "bodies": [{"name": "Comet", "a": "3 AU", "e": 0.8, "nu": 180, "trail": 0.2}], "orbits": 1}


def cls() -> Any:
    extensions.load_builtins()
    return registry.get("orbit").cls


def test_presets_elements_and_states_resolve() -> None:
    p = cls().validate_params({"central": "sun", "bodies": [{"preset": "earth"}, {"preset": "moon"}, {"name": "Probe", "r": ["1.2 AU", 0], "v": [0, "30 km/s"]},
                                                           {"name": "Rock", "periapsis": "0.5 AU", "apoapsis": "4 AU", "i": "10 deg"}], "span": "1 yr"})
    model = p.model()
    earth, moon, probe, rock = model.system.orbiters
    assert earth.name == "Earth" and earth.parent is None and earth.elements.e == pytest.approx(0.01671123)
    assert moon.parent == "Earth" and moon.elements.periapsis == pytest.approx(384_400e3 * (1 - 0.0549))
    assert probe.elements.kind == "ellipse" and np.linalg.norm(probe.elements.state()[1]) == pytest.approx(30e3)
    assert rock.elements.a == pytest.approx(2.25 * orbits.AU) and rock.elements.i == pytest.approx(math.radians(10))
    assert model.span == pytest.approx(orbits.YEAR) and model.trails["Earth"] == pytest.approx(earth.elements.period / 4)
    # the Moon's orbit uses G(M⊕ + M☾)
    assert moon.elements.mu == pytest.approx(orbits.GM_EARTH + orbits.BODIES["moon"].gm)
    iss = cls().validate_params({"central": "earth", "bodies": [{"preset": "iss"}, {"name": "Sat", "altitude": "35786 km"}]}).model()
    assert iss.system.orbiters[0].elements.period / 60 == pytest.approx(92.97, abs=0.01)
    assert iss.span == pytest.approx(iss.system.orbiters[0].elements.period)   # orbits: 1 of the first body by default
    assert iss.system.orbiters[1].elements.period == pytest.approx(orbits.SIDEREAL_DAY, rel=1e-4)
    custom = cls().validate_params({"central": {"name": "Star", "mass": "2e30 kg", "radius": "700000 km"},
                                    "bodies": [{"name": "P", "a": "1 AU"}], "span": "100 d"}).model()
    assert custom.system.central.gm == pytest.approx(2e30 * orbits.G)


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"central": "earth", "bodies": [{"name": "P", "periapsis": "7000 km", "e": 1.5}], "orbits": 2}, "open orbit .*e = 1.5.* no period; give span"),
        ({"central": "earth", "bodies": [{"name": "P", "periapsis": "7000 km", "e": 1.0}]}, "open orbit .*parabola.* no period"),
        ({"central": "earth", "bodies": [{"name": "Sat", "a": "6000 km"}], "span": "1 h"}, r"periapsis \(6,000 km .*\) lies inside Earth \(radius 6,378 km\)"),
        ({"bodies": [{"name": "P", "a": "1 AU", "mass": "-5e24 kg"}]}, "a mass cannot be negative"),
        ({"central": {"name": "X", "gm": "-1 m^3/s^2"}, "bodies": [{"name": "P", "a": "1 AU"}]}, "central: a mass cannot be negative"),
        ({"bodies": [{"preset": "marz"}]}, "unknown preset 'marz'; did you mean 'mars'"),
        ({"central": "jupyter", "bodies": [{"name": "P", "a": "1e6 km"}]}, "did you mean 'jupiter'"),
        ({"bodies": [{"name": "P", "a": 1.5}]}, r"a: 1.5 needs a unit; write '1.5 AU'"),
        ({"bodies": [{"name": "P", "r": ["1 AU", 0], "v": [0, "30 km"]}], "span": "1 yr"}, "is length.*not a speed"),
        ({"bodies": [{"name": "P", "r": ["1 AU", 0]}], "span": "1 yr"}, "give both r"),
        ({"bodies": [{"name": "P", "a": "1 AU", "r": ["1 AU", 0], "v": [0, "30 km/s"]}]}, "elements .* or a state"),
        ({"bodies": [{"preset": "moon"}]}, "preset 'moon' orbits Earth, but the central body is Sun"),
        ({"bodies": [{"name": "P", "a": "1 AU", "around": "Earht"}]}, "around 'Earht'"),
        ({"bodies": [{"name": "P", "a": "1 AU"}], "follow": "Pp"}, "follow: no body 'Pp'.*did you mean 'P'"),
        ({"bodies": [{"name": "P", "a": "1 AU"}], "span": "1 yr", "orbits": 2}, "not both"),
        ({"bodies": [{"name": "P", "a": "1 AU", "e": -0.2}]}, "cannot be negative"),
        ({"bodies": [{"name": "P", "a": "1 AU", "periapsis": "0.5 AU"}]}, "one way"),
        ({"bodies": [{"name": "P", "a": "1 AU"}, {"name": "P", "a": "2 AU"}]}, "used twice"),
        ({"bodies": [{"name": "P", "a": "1 AU"}], "energy": True}, "dynamics: nbody"),
        ({"bodies": [{"name": "P", "a": "1 AU"}], "dynamics": "nbody", "method": "euler"}, "not one of leapfrog, rk45"),
        ({"bodies": [{"name": "P", "a": "1 AU"}], "span": "-3 d"}, "positive time"),
        ({"bodies": [{"name": "P", "a": "1 AU", "trail": "3 AU"}]}, "not a time"),
        ({"bodies": []}, "at least 1 item"),
    ],
)
def test_param_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cls().validate_params(params)


def test_targets_and_on_screen_names() -> None:
    p = cls().validate_params({**COMET, "bodies": [*COMET["bodies"], {"preset": "earth", "orbit": False, "label": "Home"}]})
    assert cls().target_names(p) == ["title", "frame", "central", "body:Comet", "orbit:Comet", "body:Earth", "readout"]
    assert cls().target_text(p, "body:Earth") == "Home" and cls().target_text(p, "central") == "Sun" and cls().target_text(p, "title") == "A comet"


def test_nbody_params() -> None:
    p = cls().validate_params({"bodies": [{"name": "A", "a": "1 AU", "mass": "3e27 kg"}, {"name": "B", "a": "1.6 AU", "nu": 120, "mass": "3e27 kg"}],
                               "dynamics": "nbody", "orbits": 2})
    model = p.model()
    assert model.run is not None and model.run.drift < 1e-4 and p.shows_energy() and model.energy_error(model.span / 2) != 0
    assert p.model() is model   # cached


@pytest.mark.render
def test_kepler_second_law_from_the_scene_timing(make_project, media: Path) -> None:
    """The comet's dots, as the scene's clock places them in equal stretches of video, sweep
    equal areas (the second law emerges; nothing is drawn to make it)."""
    sc = {"id": "c", "type": "orbit", "params": COMET, "beats": [{"text": "far from the sun it crawls"}, {"text": "near the sun it sweeps by"}]}
    project = Project.load(make_project(minimal_config(scenes=[sc], narration=NARRATION)))
    s = render(project, "c", media)
    play, model = s._playback, s._model
    assert play.start + play.seconds == pytest.approx(float(s.renderer.time))   # the motion runs to the scene's last frame
    assert play.speedup == pytest.approx(model.span / play.seconds)
    stretches = np.linspace(play.start, play.start + play.seconds, 9)
    areas = [orbits.swept_area(model.view("Comet", np.array([play.sim_time(v) for v in np.linspace(a, b, 300)]))) for a, b in zip(stretches[:-1], stretches[1:])]
    assert max(areas) / min(areas) - 1 < 1e-4
    el = model.system.orbiters[0].elements
    assert sum(areas) == pytest.approx(math.pi * el.a * el.b, rel=1e-4)
    # the dot ended where the model puts it at the end of the span (one period: back at apoapsis)
    dot = s._bodies["Comet"][0]
    assert dot.get_center()[:2] == pytest.approx(s._frame_point(model.view("Comet", model.span))[:2], abs=1e-6)
    assert s._t == pytest.approx(model.span)


def test_validate_reports_orbit_errors(make_project) -> None:
    sc = {"id": "o", "type": "orbit", "params": {"central": "earth", "bodies": [{"name": "Low", "a": "6000 km"}]}, "beats": [{"text": "one"}]}
    problems = [m.message for m in project_problems(Project.load(make_project(minimal_config(scenes=[sc], narration=NARRATION))))]
    assert any("lies inside Earth" in m for m in problems)


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_orbits_render(size: tuple[int, int], make_project, media: Path) -> None:
    inner = {"title": "Inner planets", "bodies": [{"preset": "mercury"}, {"preset": "earth"}], "span": "1 yr", "caption": "JPL J2000 elements"}
    moon = {"central": "sun", "bodies": [{"preset": "earth"}, {"preset": "moon"}], "span": "30 d", "follow": "Earth", "frame": "scale_bar"}
    nbody = {"bodies": [{"name": "A", "a": "1 AU", "mass": "3e27 kg"}, {"name": "Probe", "periapsis": "2 AU", "e": 1.3, "nu": -60}],
             "dynamics": "nbody", "span": "2 yr", "frame": "none"}
    scenes = [
        {"id": "inner", "type": "orbit", "params": inner, "beats": [{"text": "mercury races round"}, {"text": "the earth takes a year"}]},
        {"id": "moon", "type": "orbit", "params": moon, "beats": [{"text": "following the earth"}]},
        {"id": "nbody", "type": "orbit", "params": nbody, "beats": [{"text": "a probe passes by"}]},
    ]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))
    s = render(project, "inner", media, size)
    lay = s._lay
    assert (lay.plot.width / (lay.x.hi - lay.x.lo)) == pytest.approx(lay.plot.height / (lay.y.hi - lay.y.lo))   # equal aspect
    assert s._readout_box is not None and s._note == "sizes not to scale" and s._lines_static[0].startswith("× ")
    assert s.is_shown("orbit:Mercury") and s.is_shown("body:Earth")
    m = render(project, "moon", media, size)
    centre = m._central[0].get_center()
    assert np.linalg.norm(m._bodies["Earth"][0].get_center() - m._frame_point(np.zeros(3))) < 1e-6   # the followed body stays put
    assert np.linalg.norm(centre - m._frame_point(np.zeros(3))) > 1   # the Sun is far away (outside the view)
    n = render(project, "nbody", media, size)
    assert n._model.run is not None and any("ΔE/E" in line for line in n._last_lines)
    # Step 230: the picture fills the height in 16:9 (no axis titles: the unit once), labels never overlap
    if size[0] > size[1]:
        assert lay.plot.height > 0.6 * s.frame_height and lay.y_title is None and lay.x_title.text == "AU"
    boxes = [(name, _box(label)) for name, (dot, label) in s._bodies.items()] + [("Sun", _box(s._central[1]))]
    dots = {name: _box(dot) for name, (dot, _) in s._bodies.items()} | {"Sun": _box(s._central[0])}
    for i, (a, box) in enumerate(boxes):
        assert all(_overlap(box, other) < 1e-6 for _, other in boxes[i + 1:]), a
        assert all(_overlap(box, d) < 1e-6 for n, d in dots.items() if n != a), a
        assert _overlap(box, s._readout_box) < 1e-6


def _box(m: Any) -> tuple[float, float, float, float]:
    return (m.get_left()[0], m.get_bottom()[1], m.get_right()[0], m.get_top()[1])


def _overlap(a: Any, b: Any) -> float:
    b = (b.x0, b.y0, b.x1, b.y1) if hasattr(b, "x0") else b
    w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


# ----- Step 230: Kepler's laws and orbital speed ------------------------------------------------

LAWS = {"title": "Kepler", "bodies": [{"name": "Comet", "a": "3 AU", "e": 0.7, "nu": 180, "geometry": True, "sectors": 4, "velocity": {"along": 6}}],
        "orbits": 1.2}
CANNON = {"central": "earth", "cannonball": {"altitude": "1000 km", "speeds": [0.6, "circular", 1.2, "escape", "12 km/s"]}}


def test_overlay_targets_and_panel() -> None:
    p = cls().validate_params(LAWS)
    assert cls().target_names(p) == ["title", "frame", "central", "body:Comet", "orbit:Comet", "geometry:Comet", "foci:Comet", "axes:Comet",
                                     "periapsis:Comet", "apoapsis:Comet", "sectors:Comet", "velocity:Comet", "readout"]
    c = cls().validate_params(CANNON)
    assert cls().target_names(c) == ["frame", "central", "cannon", "shot:1", "shot:2", "shot:3", "shot:4", "shot:5", "readout"]
    model = c.model()
    assert [s.kind for s in model.shots] == ["suborbital", "circular", "elliptical", "parabolic", "hyperbolic"]
    r0 = orbits.R_EARTH + 1e6
    assert np.linalg.norm(model.cannon_at) == pytest.approx(r0) and model.cannon_at[1] == pytest.approx(r0)   # at the top
    assert model.span == pytest.approx(model.shots[2].elements.period)   # the closed shots come round
    assert cls().validate_params({**CANNON, "cannonball": {"speeds": [1]}}).model().cannon_at[1] == pytest.approx(1.1 * orbits.R_EARTH)


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"central": "earth", "bodies": [{"name": "P", "periapsis": "7000 km", "e": 1.5, "geometry": True}], "span": "1 h"}, "geometry: its orbit is a hyperbola"),
        ({"central": "earth", "bodies": [{"name": "P", "periapsis": "7000 km", "e": 1.0, "sectors": True}], "span": "1 h"}, "sectors: its orbit is a parabola"),
        ({"bodies": [{"name": "P", "a": "1 AU", "sectors": 1}]}, "2 to 36 equal times"),
        ({"bodies": [{"name": "P", "a": "1 AU", "geometry": []}]}, "name at least one part"),
        ({"bodies": [{"name": "P", "a": "1 AU", "geometry": ["focus"]}]}, "foci"),
        ({"bodies": [{"name": "P", "a": "1 AU", "mass": "1e27 kg", "sectors": 6}], "dynamics": "nbody"}, "sectors are swept on the Kepler orbit"),
        ({"bodies": [{"name": "P", "a": "1 AU", "velocity": True}], "dynamics": "nbody"}, "velocity vectors come from the Kepler orbit"),
        ({"central": {"name": "X", "gm": "4e14 m^3/s^2"}, "cannonball": {"speeds": [1]}}, "needs a radius"),
        ({"central": "earth", "cannonball": {"speeds": [1], "altitude": "-5 km"}}, "on or under the surface"),
        ({"central": "earth", "cannonball": {"speeds": ["8 km"]}}, "not a speed"),
        ({"central": "earth", "cannonball": {"speeds": [-1]}}, "must be positive"),
        ({"central": "earth", "cannonball": {"speeds": [1]}, "orbits": 2}, "only a cannonball give span"),
        ({"central": "earth", "cannonball": {"speeds": [1]}, "dynamics": "nbody"}, "use dynamics: kepler"),
        ({"central": "earth"}, "at least 1 item"),
    ],
)
def test_overlay_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cls().validate_params(params)


def test_orbit_actions_are_checked(make_project) -> None:
    def problems(scene: dict[str, Any]) -> list[str]:
        return [m.message for m in project_problems(Project.load(make_project(minimal_config(scenes=[scene], narration=NARRATION))))]

    plain = {"id": "o", "type": "orbit", "params": COMET, "beats": [{"text": "sweep now", "actions": [{"sweep": "sectors:Comet"}]}]}
    assert any("sweep needs a body with sectors" in m for m in problems(plain))
    shots = {"id": "o", "type": "orbit", "params": CANNON, "beats": [{"text": "fire", "actions": [{"launch": "shot:9"}]}]}
    assert any("unknown target 'shot:9'" in m or "'shot:9' is not one" in m for m in problems(shots))
    other = {"id": "b", "type": "bullets", "params": {"items": ["a"]}, "beats": [{"text": "go", "actions": [{"launch": "shot:1"}]}]}
    assert problems(other)
    good = {"id": "o", "type": "orbit", "params": LAWS, "beats": [{"text": "now we sweep", "actions": [{"sweep": "sectors:Comet", "at": "@sweep"},
                                                                                                    {"reveal": "foci:Comet"}]}]}
    assert problems(good) == []


@pytest.mark.render
def test_sectors_vectors_and_geometry_render(make_project, media: Path) -> None:
    beats = [{"text": "far out it crawls"}, {"text": "now we sweep the equal times", "actions": [{"sweep": "sectors:Comet", "at": "@sweep"}]},
             {"text": "and see the foci", "actions": [{"reveal": "foci:Comet", "at": "@foci"}]}, {"text": "all areas are equal"}]
    project = Project.load(make_project(minimal_config(scenes=[{"id": "k", "type": "orbit", "params": LAWS, "beats": beats}], narration=NARRATION)))
    s = render(project, "k", media)
    el = s._model.system.orbiters[0].elements
    start = s._sweep_start("Comet")
    assert 0 < start < s._model.span and s._sweep_video["Comet"] > s._playback.start   # swept from the word, not the start
    done = s._areas_done("Comet", s._t)
    assert [n for n, _ in done] == [1, 3]   # alternate sectors of 4, both complete
    assert all(a == pytest.approx(math.pi * el.a * el.b / 4, rel=1e-12) for _, a in done)
    for k, poly in s._sectors["Comet"]["polys"]:   # the drawn sectors (polygons in frame units) have equal areas too
        pts = np.asarray(poly.get_anchors())[:, :2]
        area = 0.5 * abs(np.dot(pts[:, 0], np.roll(pts[:, 1], 1)) - np.dot(pts[:, 1], np.roll(pts[:, 0], 1))) / s._scale**2
        assert area == pytest.approx(math.pi * el.a * el.b / 4, rel=0.01), k
    assert any(line.startswith("A₃ = ") for line in s._last_lines) and "e = 0.700" in s._last_lines
    # the velocity arrow: as long as the speed (one scale), along the velocity
    live = s._velocity["Comet"]["live"]
    tip = np.asarray(live[1].get_anchors())[0]
    r, v = el.states(s._t)
    assert np.linalg.norm(tip[:2] - s._bodies["Comet"][0].get_center()[:2]) == pytest.approx(np.linalg.norm(v) * s._speed_scale, rel=1e-6)
    assert len(s._velocity["Comet"]["along"]) == 6 and any(line.startswith("v = ") for line in s._last_lines)
    assert s.is_shown("foci:Comet") and s.is_shown("axes:Comet") and s.is_shown("periapsis:Comet")


@pytest.mark.render
def test_cannonball_launches_on_words(make_project, media: Path) -> None:
    beats = [{"text": "slowly it falls", "actions": [{"launch": "shot:1", "at": "@falls"}]},
             {"text": "faster it goes round", "actions": [{"launch": "shot:2", "at": "@round"}, {"launch": "shot:3"}]},
             {"text": "escape and beyond", "actions": [{"launch": "shot:4"}, {"launch": "shot:5", "at": "@beyond"}]}]
    project = Project.load(make_project(minimal_config(scenes=[{"id": "c", "type": "orbit", "params": {**CANNON, "span": "3 h"}, "beats": beats}],
                                                       narration=NARRATION)))
    s = render(project, "c", media, (90, 160))
    times = [s._launch_time(k) for k in range(5)]
    assert all(t is not None for t in times) and times[0] < times[1] and times[3] < times[4]
    shot = s._model.shots[0]
    parts = s._shot_parts[0]
    centre = s._central[0].get_center()
    assert np.linalg.norm(parts["ball"].get_center() - centre) == pytest.approx(orbits.R_EARTH * s._scale, rel=1e-6)   # landed
    assert shot.impact < s._t - times[0]
    assert any("suborbital" in line for line in s._last_lines) and any("√2" in line for line in s._last_lines)
