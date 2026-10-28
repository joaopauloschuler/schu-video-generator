"""The orbital-mechanics model (Phase X, Step 229; DESIGN §98): Kepler's equation for every
conic, elements ↔ state vectors, derived quantities against known values, preset bodies and
orbits, values with units, the playback clock and n-body runs against Kepler. No manim."""

from __future__ import annotations

import math
import subprocess
import sys

import numpy as np
import pytest

from vidgen import orbits as o
from vidgen.errors import VidgenError

MU = o.GM_SUN
DAY = 86_400.0


# ----- Kepler's equation -----------------------------------------------------------------------


@pytest.mark.parametrize("e", [0.0, 0.1, 0.5, 0.9, 0.99, 0.999999])
def test_elliptic_kepler_equation_is_solved_to_machine_precision(e: float) -> None:
    m = np.linspace(-20, 20, 4001)
    big_e = o.eccentric_anomaly(m, e)
    assert np.max(np.abs(big_e - e * np.sin(big_e) - m)) < 1e-13
    assert o.eccentric_anomaly(1.0, e) == pytest.approx(float(big_e[np.argmin(np.abs(m - 1.0))]), abs=0.02)   # scalars too
    assert isinstance(o.eccentric_anomaly(1.0, e), float)


@pytest.mark.parametrize("e", [1.000001, 1.1, 1.5, 3.0, 20.0])
def test_hyperbolic_kepler_equation(e: float) -> None:
    m = np.concatenate([np.linspace(-500, 500, 2001), [1e-9, -1e-7]])
    h = o.hyperbolic_anomaly(m, e)
    assert np.max(np.abs(e * np.sinh(h) - h - m) / np.maximum(1.0, np.abs(m))) < 1e-13


def test_barker_equation_in_closed_form() -> None:
    m = np.concatenate([np.linspace(-1e5, 1e5, 4001), np.linspace(-1, 1, 101)])
    d = o.parabolic_anomaly(m)
    assert np.max(np.abs(d + d**3 / 3 - m) / np.maximum(1.0, np.abs(m))) < 1e-14
    assert o.parabolic_anomaly(4.0 / 3.0) == pytest.approx(1.0)   # D = 1: ν = 90°


@pytest.mark.parametrize("e", [0.0, 0.3, 0.9, 1.0, 1.5])
def test_true_and_mean_anomalies_invert_each_other(e: float) -> None:
    limit = math.acos(-1 / e) if e > 1 else math.pi
    nu = np.linspace(-0.98 * limit, 0.98 * limit, 301)
    assert o.true_from_mean(o.mean_from_true(nu, e), e) == pytest.approx(nu, abs=1e-11)
    assert o.kind_of(e) == ("ellipse" if e < 1 else "parabola" if e == 1 else "hyperbola")


def test_anomaly_errors() -> None:
    with pytest.raises(VidgenError, match="cannot be negative"):
        o.kind_of(-0.1)
    with pytest.raises(VidgenError, match="beyond the asymptotes"):
        o.mean_from_true(2.5, 1.5)


# ----- elements and state vectors ----------------------------------------------------------------


@pytest.mark.parametrize("e", [0.0, 0.5, 0.99, 1.0, 1.5])
@pytest.mark.parametrize("angles", [(0.0, 0.0, 0.0), (0.4, 1.2, 2.1), (math.pi, 0.0, 0.7), (2.0, 5.5, 0.3)], ids=["equatorial", "general", "retrograde", "steep"])
@pytest.mark.parametrize("nu", [0.0, 1.0, -2.0])
def test_elements_and_state_round_trip(e: float, angles: tuple[float, float, float], nu: float) -> None:
    i, raan, argp = angles
    el = o.Elements.from_periapsis(MU, 0.8 * o.AU, e, i=i, raan=raan, argp=argp, nu=nu)
    r, v = el.state()
    back = o.Elements.from_state(MU, r, v)
    r2, v2 = back.state()
    assert np.linalg.norm(r2 - r) < 1e-12 * np.linalg.norm(r) and np.linalg.norm(v2 - v) < 1e-12 * np.linalg.norm(v)
    assert back.e == pytest.approx(e, abs=1e-12) and back.p == pytest.approx(el.p, rel=1e-12) and back.i == pytest.approx(i, abs=1e-12)
    assert back.kind == el.kind
    if e > 0 and 0 < i < math.pi:   # every angle is defined: they come back
        assert (back.raan, back.argp, back.nu) == pytest.approx((raan % (2 * math.pi), argp, nu), abs=1e-10)


def test_state_vectors_by_hand() -> None:
    # a circular orbit of 1 AU: speed √(μ/r) sideways, e = 0, period one Gaussian year
    v = math.sqrt(MU / o.AU)
    el = o.Elements.from_state(MU, [o.AU, 0], [0, v])
    assert el.e == 0 and el.i == 0 and el.argp == 0 and el.nu == pytest.approx(0)
    assert el.period / DAY == pytest.approx(365.2569, abs=1e-4)
    # escape speed gives a parabola, more gives a hyperbola with v∞² = v² − v_esc²
    assert o.Elements.from_state(MU, [o.AU, 0], [0, math.sqrt(2) * v]).kind == "parabola"
    hyp = o.Elements.from_state(MU, [o.AU, 0], [0, 1.5 * v])
    assert hyp.kind == "hyperbola" and hyp.v_infinity == pytest.approx(math.sqrt((1.5 * v) ** 2 - 2 * v * v))
    retro = o.Elements.from_state(MU, [o.AU, 0, 0], [0, -v, 0])
    assert retro.i == pytest.approx(math.pi)
    with pytest.raises(VidgenError, match="radial"):
        o.Elements.from_state(MU, [o.AU, 0], [v, 0])
    with pytest.raises(VidgenError, match="2 or 3 finite components"):
        o.Elements.from_state(MU, [o.AU], [0, v])


def test_known_values() -> None:
    """Earth's year from a = 1 AU and GM☉, the ISS's period at 420 km, the geostationary radius
    from a sidereal day, and vis-viva at the Earth."""
    assert o.period(o.GM_SUN, o.AU) / DAY == pytest.approx(365.25, abs=0.01)
    iss_minutes = o.period(o.GM_EARTH, o.R_EARTH + 420e3) / 60
    assert 92 < iss_minutes < 93
    assert o.semi_major_axis(o.GM_EARTH, o.SIDEREAL_DAY) / 1e3 == pytest.approx(42_164, abs=1)
    assert o.ORBITS["geo"].a == pytest.approx(42_164.17e3, abs=10)
    assert o.circular_speed(o.GM_SUN, o.AU) / 1e3 == pytest.approx(29.78, abs=0.01)
    assert o.escape_speed(o.GM_EARTH, o.R_EARTH) / 1e3 == pytest.approx(11.18, abs=0.01)
    assert o.vis_viva(o.GM_SUN, o.AU, o.AU) == pytest.approx(o.circular_speed(o.GM_SUN, o.AU))
    assert o.vis_viva(o.GM_SUN, o.AU, math.inf) == pytest.approx(o.escape_speed(o.GM_SUN, o.AU))
    assert o.specific_energy(o.GM_SUN, o.AU, o.circular_speed(o.GM_SUN, o.AU)) == pytest.approx(-o.GM_SUN / (2 * o.AU))
    with pytest.raises(VidgenError, match="only an ellipse"):
        o.period(MU, -1.0)


def test_derived_quantities_of_an_ellipse() -> None:
    el = o.Elements.from_a(MU, 2 * o.AU, 0.6, nu=0.0)
    assert el.periapsis == pytest.approx(0.8 * o.AU) and el.apoapsis == pytest.approx(3.2 * o.AU)
    assert el.b == pytest.approx(2 * o.AU * 0.8)
    assert el.energy == pytest.approx(-MU / (4 * o.AU))
    assert el.angular_momentum == pytest.approx(math.sqrt(MU * el.p))
    r, v = el.state()
    assert np.linalg.norm(np.cross(r, v)) == pytest.approx(el.angular_momentum)
    assert np.dot(v, v) / 2 - MU / np.linalg.norm(r) == pytest.approx(el.energy)
    assert el.speed_at(0.0) == pytest.approx(np.linalg.norm(v))
    # half an orbit from periapsis to apoapsis takes half the period; a quarter of the mean anomaly does not take a quarter of ν
    assert el.time_of_flight(0.0, math.pi) == pytest.approx(el.period / 2)
    assert el.time_of_flight(math.pi, 0.0) == pytest.approx(el.period / 2)
    assert el.time_of_flight(-1.0, 1.0) < el.period / 4   # fast near periapsis
    assert el.at(el.period).nu == pytest.approx(0.0, abs=1e-9)
    assert el.at(el.period / 2).nu == pytest.approx(math.pi, abs=1e-9) or el.at(el.period / 2).nu == pytest.approx(-math.pi, abs=1e-9)
    assert el.at(el.time_of_flight(0, 2.0)).nu == pytest.approx(2.0)
    pts = el.conic(360)
    assert np.allclose(pts[0], pts[-1], atol=1.0) and np.max(np.linalg.norm(pts, axis=1)) == pytest.approx(3.2 * o.AU, rel=1e-4)


def test_open_orbits_move_and_draw() -> None:
    hyp = o.Elements.from_periapsis(o.GM_EARTH, 10_000e3, 1.6, nu=-1.5)
    assert hyp.period is None and hyp.apoapsis == math.inf and hyp.a < 0 and hyp.energy > 0
    t = hyp.time_of_flight(-1.5, 1.5)
    assert hyp.at(t).nu == pytest.approx(1.5) and hyp.at(t / 2).nu == pytest.approx(0.0, abs=1e-9)
    par = o.Elements.from_periapsis(o.GM_EARTH, 10_000e3, 1.0, nu=-1.5)
    assert par.a == math.inf and par.energy == 0 and par.v_infinity == 0
    assert par.at(par.time_of_flight(-1.5, 1.0)).nu == pytest.approx(1.0)
    for el in (hyp, par):
        pts = el.conic(200, r_max=60_000e3)
        assert np.max(np.linalg.norm(pts, axis=1)) == pytest.approx(60_000e3, rel=1e-6)
        assert np.min(np.linalg.norm(pts, axis=1)) == pytest.approx(10_000e3, rel=1e-6)
    with pytest.raises(VidgenError, match="passes each point once"):
        hyp.time_of_flight(1.0, -1.0)
    with pytest.raises(VidgenError, match="beyond the asymptotes"):
        o.Elements.from_periapsis(o.GM_EARTH, 10_000e3, 1.6, nu=2.5)


def test_element_errors() -> None:
    with pytest.raises(VidgenError, match="positive gravitational parameter"):
        o.Elements(-1.0, 1.0, 0.1)
    with pytest.raises(VidgenError, match="no finite semi-major axis"):
        o.Elements.from_a(MU, o.AU, 1.0)
    with pytest.raises(VidgenError, match="positive semi-major axis"):
        o.Elements.from_a(MU, -o.AU, 0.5)
    with pytest.raises(VidgenError, match="swap them"):
        o.Elements.from_apsides(MU, 2 * o.AU, o.AU)
    with pytest.raises(VidgenError, match="between 0° and 180°"):
        o.Elements(MU, o.AU, 0.1, i=4.0)
    assert o.Elements.from_a(MU, -2 * o.AU, 1.5).a == pytest.approx(-2 * o.AU)   # |a| of either sign


# ----- bodies, presets and values -----------------------------------------------------------------


def test_bodies_and_presets() -> None:
    assert o.BODIES["sun"].gm == o.GM_SUN == 1.3271244e20 and o.BODIES["earth"].radius == 6.3781e6
    assert o.body_preset("Luna").name == "Moon"
    with pytest.raises(VidgenError, match="did you mean 'jupiter'"):
        o.body_preset("jupyter")
    with pytest.raises(VidgenError, match="cannot be a central body"):
        o.body_preset("iss")
    with pytest.raises(VidgenError, match="did you mean 'mars'"):
        o.orbit_preset("marz")
    with pytest.raises(VidgenError, match="central body"):
        o.orbit_preset("sun")
    with pytest.raises(VidgenError, match="cannot be negative"):
        o.Body("x", -1.0)
    # the planets' sidereal periods from their J2000 a (Kepler III with GM☉): Mars 687 d, Jupiter 11.86 yr
    assert o.period(o.GM_SUN, o.ORBITS["mars"].a) / DAY == pytest.approx(687.0, abs=0.5)
    assert o.period(o.GM_SUN, o.ORBITS["jupiter"].a) / o.YEAR == pytest.approx(11.86, abs=0.01)
    assert o.period(o.GM_SUN, o.ORBITS["mercury"].a) / DAY == pytest.approx(87.97, abs=0.05)
    earth = o.ORBITS["earth"]
    assert math.degrees(earth.argp + earth.raan) % 360 == pytest.approx(102.93768193)   # ϖ = Ω + ω
    assert math.degrees(earth.mean_anomaly) == pytest.approx(100.46457166 - 102.93768193 + 360)   # M = L − ϖ


@pytest.mark.parametrize(
    ("value", "kind", "expected"),
    [("1 AU", "length", o.AU), ("7.8 km/s", "speed", 7800.0), ("92 min", "time", 5520.0), ("2 yr", "time", 2 * o.YEAR),
     (90, "angle", math.pi / 2), ("0.5 rad", "angle", 0.5), ("45 deg", "angle", math.pi / 4), ("30", "angle", math.pi / 6),
     ("3.986004e14 m^3/s^2", "gm", 3.986004e14), ("5.97e24 kg", "mass", 5.97e24)],
)
def test_values_with_units(value: object, kind: str, expected: float) -> None:
    assert o.value_si(value, kind, "x") == pytest.approx(expected)


@pytest.mark.parametrize(
    ("value", "kind", "message"),
    [(1.5, "length", "needs a unit"), ("1.5", "length", "needs a unit"), ("7.8 km", "speed", "is length.*not a speed"),
     ("1 AU", "time", "not a time"), ("3 parsnips", "length", "parsnips"), (True, "length", "is not a value")],
)
def test_value_errors(value: object, kind: str, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        o.value_si(value, kind, "bodies[1].a")


def test_display_units_and_speedup_text() -> None:
    assert o.length_unit(2 * o.AU) == ("AU", o.AU) and o.length_unit(42_000e3) == ("km", 1000.0) and o.length_unit(1e3, "AU")[0] == "AU"
    assert [o.time_unit(s)[0] for s in (3600, 86_400, 30 * DAY, 10 * o.YEAR)] == ["min", "h", "d", "yr"]
    assert o.speedup_text(1.578e6) == "× 1.6 million" and o.speedup_text(4823.0) == "× 4 800" and o.speedup_text(2.3e10) == "× 23 billion"
    assert o.speedup_text(37.0) == "× 37"


# ----- systems, the playback clock and n-body runs --------------------------------------------------


def comet(e: float = 0.8) -> o.System:
    return o.System(o.BODIES["sun"], (o.Orbiter("Comet", o.Body("Comet", 0.0), o.Elements.from_a(MU, 3 * o.AU, e, nu=math.pi)),))


def test_equal_areas_in_equal_times_from_the_playback_clock() -> None:
    """Kepler's second law emerges: positions at equal video intervals sweep equal areas, and a
    whole period sweeps the ellipse (π a b)."""
    system = comet(0.8)
    el = system.orbiters[0].elements
    play = o.Playback(start=1.0, seconds=12.0, span=el.period)
    edges = np.linspace(1.0, 13.0, 13)
    areas = []
    for a, b in zip(edges[:-1], edges[1:]):
        ts = [play.sim_time(v) for v in np.linspace(a, b, 400)]
        areas.append(o.swept_area(system.position("Comet", np.array(ts))))
    assert max(areas) / min(areas) - 1 < 1e-4
    assert sum(areas) == pytest.approx(math.pi * el.a * el.b, rel=1e-4)
    assert play.speedup == pytest.approx(el.period / 12) and play.sim_time(0.0) == 0 and play.sim_time(99.0) == el.period


def test_hierarchical_positions_add_up() -> None:
    sun, earth, moon = o.BODIES["sun"], o.BODIES["earth"], o.BODIES["moon"]
    e_el = o.Elements.from_a(MU + earth.gm, o.AU, 0.0)
    m_el = o.Elements.from_a(earth.gm + moon.gm, 384_400e3, 0.0)
    system = o.System(sun, (o.Orbiter("Earth", earth, e_el), o.Orbiter("Moon", moon, m_el, "Earth")))
    t = np.linspace(0, 30 * DAY, 7)
    assert system.position("Moon", t) - system.position("Earth", t) == pytest.approx(m_el.positions(t))
    assert m_el.period / DAY == pytest.approx(27.28, abs=0.01)   # with GM⊕ + GM☾ (the sidereal month is 27.32 d at the true mean distance)
    with pytest.raises(VidgenError, match="not listed before it"):
        o.System(sun, (o.Orbiter("Moon", moon, m_el, "Earth"),))
    with pytest.raises(VidgenError, match="called 'Earth'"):
        o.System(sun, (o.Orbiter("Earth", earth, e_el), o.Orbiter("Earth", earth, e_el)))


@pytest.mark.parametrize("method", ["leapfrog", "rk45"])
def test_nbody_two_bodies_agree_with_kepler(method: str) -> None:
    """A test particle around the Sun for 20 orbits of e = 0.5: the n-body path stays on the
    Kepler one; leapfrog's energy error stays bounded (it does not grow), RK45's is tiny."""
    system = o.System(o.BODIES["sun"], (o.Orbiter("p", o.Body("p", 0.0), o.Elements.from_a(MU, o.AU, 0.5, nu=0.3)),))
    period = system.orbiters[0].elements.period
    run = o.simulate(system, 20 * period, method=method, samples=800)
    kepler = system.position("p", run.times)
    error = np.max(np.linalg.norm(run.positions[1] - kepler, axis=1)) / o.AU
    assert error < (0.02 if method == "leapfrog" else 1e-4)
    if method == "leapfrog":
        half = len(run.energy) // 2
        e0 = abs(run.energy[0])
        first, second = (np.max(np.abs(run.energy[s] - run.energy[0])) / e0 for s in (slice(0, half), slice(half, None)))
        assert run.drift < 1e-4 and second < 2 * first   # bounded: the second half is no worse than the first
    else:
        assert run.drift < 1e-7 and run.step is None
    mid = 0.5 * (run.times[10] + run.times[11])   # between outputs: Hermite interpolation
    assert np.linalg.norm(run.position("p", mid) - system.position("p", mid)) / o.AU < (0.02 if method == "leapfrog" else 1e-4)


def test_nbody_with_two_masses_conserves_energy_and_momentum() -> None:
    star = o.Body("Star", MU)
    heavy = o.Body("Heavy", 0.01 * MU)
    system = o.System(star, (o.Orbiter("Heavy", heavy, o.Elements.from_a(1.01 * MU, o.AU, 0.2)),
                             o.Orbiter("Light", o.Body("Light", 1e-6 * MU), o.Elements.from_a(MU, 2 * o.AU, 0.1, nu=2.0))))
    run = o.simulate(system, 5 * o.YEAR)
    assert run.drift < 1e-4 and run.method == "leapfrog" and run.names == ("Star", "Heavy", "Light")
    assert run.position("Star", run.times[5]) == pytest.approx(np.zeros(3))   # relative to the central body
    with pytest.raises(VidgenError, match="not one of"):
        o.simulate(system, o.YEAR, method="euler")
    assert o.method_name("verlet") == "leapfrog" and o.method_name("adaptive") == "rk45"


def test_the_model_does_not_import_manim() -> None:
    code = "import sys, vidgen.orbits; print('manim' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
