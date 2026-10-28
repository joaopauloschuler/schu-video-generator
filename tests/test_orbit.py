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
