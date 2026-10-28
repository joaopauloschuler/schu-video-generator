"""Many bodies (Phase X, Step 232; DESIGN §98.6): the restricted three-body problem (Lagrange
points against published values, Routh's criterion, the Jacobi constant conserved, tadpole and
horseshoe motion), the figure-eight's return, the Laplace resonance, barycentres, which way the
Moon's path bends, tides — and the ``orbit`` scene's params, targets, actions and tiny renders."""

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
TROJAN = {"system": "sun_jupiter", "lagrange": True, "bodies": [{"name": "Trojan", "near": "L4", "shift": [0.004, 0.0069], "trail": "60 yr"}], "span": "150 yr"}


def cls() -> Any:
    extensions.load_builtins()
    return registry.get("orbit").cls


# ----- the model ------------------------------------------------------------------------------------


def test_lagrange_points_against_published_values() -> None:
    """Earth–Moon (μ = 0.012 150 585): γ₁ = 0.150 934, γ₂ = 0.167 833, L3 at x = −1.005 06
    (Koon, Lo, Marsden & Ross 2011; Szebehely 1967); L4 / L5 at 60°. Sun–(Earth + Moon): L1 and
    L2 about 1.5 million km from the Earth (1.4976 and 1.5077 million km)."""
    em = orbits.RESTRICTED["earth_moon"]
    assert em.mu == pytest.approx(0.0121506, abs=2e-7)
    assert orbits.collinear_gamma(em.mu, "L1") == pytest.approx(0.150934, abs=2e-6)
    assert orbits.collinear_gamma(em.mu, "L2") == pytest.approx(0.167833, abs=2e-6)
    pts = orbits.lagrange_points(em.mu)
    assert pts["L3"][0] == pytest.approx(-1.005063, abs=2e-6)
    assert pts["L4"] == pytest.approx([0.5 - em.mu, math.sqrt(3) / 2])
    # every point is an equilibrium: the effective potential's gradient vanishes there (an independent check)
    for name, (x, y) in pts.items():
        h = 1e-6
        gx = (orbits.restricted_potential(em.mu, x + h, y) - orbits.restricted_potential(em.mu, x - h, y)) / (2 * h)
        gy = (orbits.restricted_potential(em.mu, x, y + h) - orbits.restricted_potential(em.mu, x, y - h)) / (2 * h)
        assert abs(gx) < 1e-7 and abs(gy) < 1e-7, name
    # Earth–Moon L1 / L2 from the Earth, in km: about 326 400 and 448 900
    assert (1 - orbits.collinear_gamma(em.mu, "L1")) * em.separation / 1e3 == pytest.approx(326_400, abs=100)
    assert (1 + orbits.collinear_gamma(em.mu, "L2")) * em.separation / 1e3 == pytest.approx(448_900, abs=100)
    se = orbits.RESTRICTED["sun_earth"]
    d = se.distances()
    assert d["L1"] / 1e9 == pytest.approx(1.4976, abs=0.0005) and d["L2"] / 1e9 == pytest.approx(1.5077, abs=0.0005)
    assert orbits.collinear_gamma(se.mu, "L1") == pytest.approx(0.0100110, abs=2e-7)
    assert orbits.collinear_gamma(se.mu, "L2") == pytest.approx(0.0100782, abs=2e-7)
    # the ordering of their Jacobi constants; C4 = C5 = 3 − μ(1 − μ)
    c = orbits.lagrange_jacobi(em.mu)
    assert c["L1"] > c["L2"] > c["L3"] > c["L4"] == pytest.approx(c["L5"])
    assert c["L4"] == pytest.approx(3 - em.mu * (1 - em.mu))


def test_routh_criterion() -> None:
    assert orbits.ROUTH_MU == pytest.approx(0.0385209, abs=1e-7)
    assert 27 * orbits.ROUTH_MU * (1 - orbits.ROUTH_MU) == pytest.approx(1.0)   # Gascheau's form
    assert orbits.routh_stable(0.0121) and orbits.routh_stable(0.0385) and not orbits.routh_stable(0.0386)


def test_jacobi_conserved_tadpole_horseshoe_and_instability() -> None:
    mu = orbits.RESTRICTED["sun_jupiter"].mu
    l4 = orbits.lagrange_points(mu)["L4"]
    _, ys = orbits.integrate_restricted(mu, [l4[0] + 0.004, l4[1] + 0.0069, 0.0, 0.0], 30 * 2 * math.pi, samples=3000)
    c = orbits.jacobi(mu, ys[:, 0], ys[:, 1], ys[:, 2], ys[:, 3])
    assert np.max(np.abs(c - c[0])) < 1e-9
    ang = orbits.coorbital_angles(np.column_stack([ys[:, 0] + mu, ys[:, 1]]), np.tile([1.0, 0.0], (len(ys), 1)))
    assert orbits.coorbital_kind(ang) == "tadpole L4" and 20 < ang.min() < 60 < ang.max() < 140
    # a horseshoe: from just outside L3, round past L3 and back, never reaching Jupiter
    _, ys = orbits.integrate_restricted(mu, [-1.0 - mu - 0.003, 0.0, 0.0, 0.0], 200 * 2 * math.pi, samples=8000)
    ang = orbits.coorbital_angles(np.column_stack([ys[:, 0] + mu, ys[:, 1]]), np.tile([1.0, 0.0], (len(ys), 1)))
    assert orbits.coorbital_kind(ang) == "horseshoe" and np.abs(ang).min() > 10
    # above Routh's limit the same start leaves L4
    _, ys = orbits.integrate_restricted(0.05, [0.45 + 0.002, math.sqrt(3) / 2, 0.0, 0.0], 30 * 2 * math.pi, samples=3000)
    ang = orbits.coorbital_angles(np.column_stack([ys[:, 0] + 0.05, ys[:, 1]]), np.tile([1.0, 0.0], (len(ys), 1)))
    assert orbits.coorbital_kind(ang) != "tadpole L4"


def test_zero_velocity_curve_lies_where_2_omega_is_c() -> None:
    mu = 0.0121506
    c = 3.1
    segs = orbits.zero_velocity_segments(mu, c, (-1.5, 1.5), (-1.5, 1.5), cells=300)
    assert len(segs) > 100
    pts = segs.reshape(-1, 2)
    assert np.max(np.abs(2 * orbits.restricted_potential(mu, pts[:, 0], pts[:, 1]) - c)) < 2e-3


def test_figure_eight_returns_after_one_period() -> None:
    """The published initial values come back after T = 6.32591398 (integrated here, RK45)."""
    eight = orbits.figure_eight(orbits.GM_SUN, orbits.AU)
    assert eight.period == pytest.approx(6.32591398 * math.sqrt(orbits.AU**3 / orbits.GM_SUN))
    sun = orbits.Body("A", orbits.GM_SUN)
    stand_in = orbits.Elements.from_state(orbits.GM_SUN, [orbits.AU, 0, 0], [0, 30e3, 0])
    system = orbits.System(sun, (orbits.Orbiter("B", orbits.Body("B", orbits.GM_SUN), stand_in), orbits.Orbiter("C", orbits.Body("C", orbits.GM_SUN), stand_in)))
    initial = {n: (eight.positions[k] - eight.positions[0], eight.velocities[k] - eight.velocities[0]) for k, n in ((1, "B"), (2, "C"))}
    run = orbits.simulate(system, eight.period, method="rk45", initial=initial, samples=400)
    for name in ("B", "C"):
        k = run.names.index(name)
        assert np.linalg.norm(run.positions[k, -1] - run.positions[k, 0]) < 1e-6 * orbits.AU
    assert run.drift < 1e-8 and run.angular_drift < 1e-8   # its total angular momentum is zero: measured against Σ|r||v|
    assert abs(float(run.angular[0])) < 1e-6 * run.angular_scale


def test_laplace_resonance_periods_and_conjunctions() -> None:
    p = orbits.GALILEAN_PERIODS
    assert p["europa"] / p["io"] == pytest.approx(2.0073, abs=1e-4) and p["ganymede"] / p["europa"] == pytest.approx(2.0147, abs=1e-4)
    assert orbits.nearest_ratio(p["europa"] / p["io"]) == 2 and orbits.nearest_ratio(p["ganymede"] / p["europa"]) == 2
    n = [2 * math.pi / p[k] for k in ("io", "europa", "ganymede")]
    assert abs(n[0] - 3 * n[1] + 2 * n[2]) < 1e-8   # the Laplace relation (rad/day)
    # the presets: a from Kepler III within 0.03 % of the published distances, periods as published
    for key, a_km in (("io", 421_700), ("europa", 671_000), ("ganymede", 1_070_400), ("callisto", 1_882_700)):
        assert orbits.ORBITS[key].a / 1e3 == pytest.approx(a_km, rel=3e-4)
    model = cls().validate_params({"central": "jupiter", "bodies": [{"preset": "io"}, {"preset": "europa"}, {"preset": "ganymede"}],
                                   "resonance": ["Io", "Europa", "Ganymede"], "span": "30 d"}).model()
    io, europa, ganymede = model.system.orbiters
    assert io.elements.period / 86400 == pytest.approx(1.769137786, rel=1e-9)
    ts = np.linspace(0, model.span, 50)
    lam = [np.arctan2(o.positions(ts)[:, 1], o.positions(ts)[:, 0]) for o in (io, europa, ganymede)]
    assert np.max(np.abs(orbits.laplace_angle(*lam) - 180.0)) < 1e-3
    res = model.many.resonance
    ie, eg = res.conjunctions
    synodic_ie = 1 / (1 / p["io"] - 1 / p["europa"]) * 86400
    assert np.diff([t for t, _ in ie]) == pytest.approx(synodic_ie, rel=1e-6)   # Io–Europa every 3.53 d
    assert synodic_ie / 86400 == pytest.approx(3.5256, abs=1e-3)
    for t, angle in ie:   # at each Io–Europa conjunction Ganymede is a quarter turn away
        g = ganymede.positions(t)
        off = math.degrees((math.atan2(g[1], g[0]) - angle + math.pi) % (2 * math.pi) - math.pi)
        assert abs(off) == pytest.approx(90.0, abs=0.01)
    for t, angle in eg:   # at each Europa–Ganymede conjunction Io is on the other side
        i = io.positions(t)
        off = math.degrees((math.atan2(i[1], i[0]) - angle) % (2 * math.pi))
        assert off == pytest.approx(180.0, abs=0.01)


def test_barycentres_and_binary_shares() -> None:
    em = orbits.RESTRICTED["earth_moon"]
    assert em.mu * em.separation / 1e3 == pytest.approx(4_671, abs=2)   # the Earth–Moon barycentre, inside the Earth
    sj = orbits.RESTRICTED["sun_jupiter"]
    assert sj.mu * sj.separation > orbits.BODIES["sun"].radius   # the Sun–Jupiter barycentre lies just outside the Sun
    assert orbits.binary_shares(2.0, 1.0) == pytest.approx((1 / 3, 2 / 3))
    b = orbits.barycentre([2.0, 1.0], [[0, 0, 0], [3, 0, 0]])
    assert b == pytest.approx([1.0, 0, 0])
    p = cls().validate_params({"central": {"name": "A", "mass": "2 Msun"}, "bodies": [{"name": "B", "mass": "1 Msun", "a": "10 AU", "e": 0.5}],
                               "origin": "barycentre"})
    m = p.model()
    assert m.system.central.gm == pytest.approx(2 * orbits.GM_SUN)
    for t in (0.0, m.span / 3):
        assert m.view("A", t) * 2 + m.view("B", t) == pytest.approx(np.zeros(3), abs=1e-3)   # 2 m_A r_A + m_B r_B = 0 about the barycentre
    assert "barycentre" in cls().target_names(p) and "orbit:A" in cls().target_names(p)


def test_the_moons_path_is_concave_toward_the_sun() -> None:
    m = cls().validate_params({"central": "sun", "bodies": [{"preset": "earth"}, {"preset": "moon", "curvature": True}], "span": "1 yr"}).model()
    assert m.many.curvature["Moon"][0] == 1.0
    # a satellite close to the Earth does loop: its path turns away from the Sun part of the time
    iss = cls().validate_params({"central": "sun", "bodies": [{"preset": "earth"}, {"name": "Sat", "around": "Earth", "a": "20000 km", "curvature": True}],
                                 "span": "2 d"}).model()
    assert iss.many.curvature["Sat"][0] < 0.9


def test_tides_numbers() -> None:
    moon, earth = orbits.BODIES["moon"], orbits.BODIES["earth"]
    d = orbits.ORBITS["moon"].a
    a = orbits.tidal_acceleration(moon.gm, [d, 0, 0], [[earth.radius, 0, 0], [0, earth.radius, 0], [-earth.radius, 0, 0]])
    assert a[0, 0] == pytest.approx(2 * moon.gm * earth.radius / d**3, rel=0.03)   # ≈ 1.1 × 10⁻⁶ m/s², towards the Moon
    assert a[0, 0] > 0 and a[2, 0] < 0 and a[1, 1] < 0   # stretched along the line, squeezed across it
    assert a[1, 1] == pytest.approx(-moon.gm * earth.radius / d**3, rel=0.01)
    assert orbits.equilibrium_tide(moon.gm, earth.gm, earth.radius, d) == pytest.approx(0.36, abs=0.01)


def test_solar_masses_and_angular_momentum() -> None:
    assert orbits.value_si("2 Msun", "mass", "m") * orbits.G == pytest.approx(2 * orbits.GM_SUN)
    assert orbits.value_si("3 Mearth", "mass", "m") * orbits.G == pytest.approx(3 * orbits.GM_EARTH)
    run = cls().validate_params(TROJAN).model().run
    assert run.angular_drift < 1e-6 and run.method == "rk45"   # a three-body pair defaults to RK45
    v = run.velocity("Jupiter", run.times[10:13])
    assert v == pytest.approx(run.velocities[run.names.index("Jupiter"), 10:13], rel=1e-9)


# ----- the scene ------------------------------------------------------------------------------------


def test_restricted_scene_model_and_targets() -> None:
    p = cls().validate_params(TROJAN)
    m = p.model()
    assert m.run is not None and m.many.restricted.secondary == "Jupiter" and m.many.origin == "barycentre"
    assert m.many.coorbital["Trojan"][0] == "tadpole L4"
    c = m.many.jacobi["Trojan"]
    assert np.max(np.abs(c - c[0])) / c[0] < 1e-8   # the scene's own Jacobi constant from the inertial n-body run
    assert cls().target_names(p) == ["frame", "central", "body:Jupiter", "orbit:Jupiter", "body:Trojan", "lagrange", "lagrange:L1", "lagrange:L2",
                                     "lagrange:L3", "lagrange:L4", "lagrange:L5", "rotation", "readout"]
    assert cls().target_text(p, "central") == "Sun"
    # the rotating view: Jupiter stands still on +x, the Sun at −μD
    pair = m.many.restricted.pair
    m.turn = 1.0
    for t in (0.0, m.span / 7, m.span / 2):
        assert m.view("Jupiter", t)[:2] == pytest.approx([(1 - pair.mu) * pair.separation, 0.0], abs=1e-6 * pair.separation)
        assert m.view("Sun", t)[:2] == pytest.approx([-pair.mu * pair.separation, 0.0], abs=1e-6 * pair.separation)
    m.turn = 0.0
    assert np.linalg.norm(m.view("Jupiter", m.span / 7)[:2] - m.view("Jupiter", 0.0)[:2]) > 0.1 * pair.separation
    eight = cls().validate_params({"system": "figure_eight"}).model()
    assert eight.span == pytest.approx(eight.many.eight.period) and eight.many.closure < 1e-4
    tides = cls().validate_params({"tides": True})
    assert cls().target_names(tides) == ["frame", "central", "body:Moon", "pull", "mean", "tidal", "bulges", "face", "readout"]
    assert cls().target_text(tides, "central") == "Earth"


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"system": "sun_mars"}, "unknown three-body system 'sun_mars'"),
        ({"system": "sun_jupiter", "central": "sun"}, "it sets the central body"),
        ({"system": "sun_jupiter", "dynamics": "kepler"}, "leave out dynamics"),
        ({"system": "sun_jupiter", "bodies": [{"name": "J", "near": "L4", "a": "5 AU"}]}, "leave out a"),
        ({"bodies": [{"name": "J", "near": "L4"}]}, "needs a three-body system"),
        ({"bodies": [{"name": "P", "a": "1 AU"}], "view": "rotating"}, "view: rotating turns with a three-body pair"),
        ({"bodies": [{"name": "P", "a": "1 AU"}], "lagrange": True}, "belong to a three-body pair"),
        ({"system": "sun_jupiter", "zero_velocity": True}, "add a body near a Lagrange point"),
        ({"system": {"primary": "jupiter", "secondary": "sun"}}, "the primary is the larger body"),
        ({"system": {"primary": "sun", "secondary": "jupiter", "mu": 0.7}}, "less than or equal to 0.5"),
        ({"system": "figure_eight", "bodies": [{"name": "P", "a": "1 AU"}]}, "leave bodies out"),
        ({"system": "sun_jupiter", "follow": "Jupiter"}, "leave out follow"),
        ({"bodies": [{"name": "P", "a": "1 AU"}], "center": "P"}, "give extent too"),
        ({"bodies": [{"name": "P", "a": "1 AU"}], "center": "Q", "extent": "1 AU"}, "center: no body 'Q'"),
        ({"bodies": [{"name": "P", "a": "1 AU"}, {"name": "Q", "a": "2 AU"}], "resonance": ["Q", "P"]}, "from the inside out"),
        ({"tides": True, "bodies": [{"name": "P", "a": "1 AU"}]}, "leave out bodies"),
        ({"bodies": [{"name": "P", "a": "1 AU", "shift": [0.1, 0]}]}, "give near: L4"),
    ],
)
def test_many_body_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cls().validate_params(params)


def test_frame_actions_are_checked(make_project) -> None:
    good = {"id": "t", "type": "orbit", "params": TROJAN, "beats": [{"text": "now turn with jupiter", "actions": [{"action": "corotate", "at": "@turn"}]}]}
    bad = {"id": "k", "type": "orbit", "params": {"bodies": [{"name": "P", "a": "1 AU"}]},
           "beats": [{"text": "turn now", "actions": [{"action": "corotate", "at": "@turn"}]}]}
    problems = [m.message for m in project_problems(Project.load(make_project(minimal_config(scenes=[good, bad], narration=NARRATION))))]
    assert not any("'t'" in m or "scene t" in m for m in problems)
    assert any("corotate turns the view of a three-body pair" in m for m in problems)


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_many_body_scenes_render(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [
        {"id": "trojan", "type": "orbit", "params": TROJAN,
         "beats": [{"text": "they go round together"}, {"text": "now turn with jupiter", "actions": [{"action": "corotate", "at": "@turn", "run_time": 0.5}]}]},
        {"id": "tides", "type": "orbit", "params": {"tides": True}, "beats": [{"text": "the moon pulls", "actions": [{"reveal": "tidal", "at": "@pulls"}]}]},
        {"id": "res", "type": "orbit", "params": {"central": "jupiter", "bodies": [{"preset": "io"}, {"preset": "europa"}], "resonance": ["Io", "Europa"],
                                                  "span": "8 d"},
         "beats": [{"text": "they meet again", "actions": [{"reveal": "conjunctions", "at": "@meet"}]}]},
    ]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))
    s = render(project, "trojan", media, size)
    model = s._model
    assert model.turn == 1.0   # turned on its word: the last frame is in the rotating frame
    jup = s._bodies["Jupiter"][0].get_center()
    pair = model.many.restricted.pair
    assert jup[:2] == pytest.approx(s._frame_point(np.array([(1 - pair.mu) * pair.separation, 0, 0]))[:2], abs=1e-3)
    l4 = s._many_parts["lagrange"]["L4"]["cross"].get_center()
    assert l4[:2] == pytest.approx(s._frame_point(np.array([*pair.points()["L4"], 0]))[:2], abs=1e-3)
    assert any(line.startswith("rotating frame") for line in s._last_lines) and not any(line.startswith("C = ") for line in s._last_lines)   # the Jacobi drift: a diagnostic (Step 233)
    assert any(line.startswith("tadpole about L4") for line in s._last_lines)
    t = render(project, "tides", media, size)
    assert t.is_shown("tidal") and any("equilibrium tide" in line for line in t._last_lines)
    r = render(project, "res", media, size)
    assert any(line.startswith("Io–Europa conjunctions: 2") for line in r._last_lines)
