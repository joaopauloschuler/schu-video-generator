"""Kepler's laws and orbital speed in the model (Phase X, Step 230; DESIGN §98.4): the ellipse's
geometry for the Earth's and Halley's orbits, equal areas in equal times to rounding, vis-viva
speeds, Newton's cannonball classified by energy, and Kepler's third law for the planets. No
manim, no rendering."""

from __future__ import annotations

import math

import numpy as np
import pytest

from vidgen import orbits, plotcore
from vidgen.errors import VidgenError

AU = orbits.AU


def earth() -> orbits.Elements:
    p = orbits.ORBITS["earth"]
    return orbits.Elements.from_a(orbits.GM_SUN + orbits.BODIES["earth"].gm, p.a, p.e, i=p.i, raan=p.raan, argp=p.argp)


def halley() -> orbits.Elements:
    p = orbits.ORBITS["halley"]
    return orbits.Elements.from_a(orbits.GM_SUN, p.a, p.e, i=p.i, raan=p.raan, argp=p.argp)


def test_geometry_of_the_earths_and_halleys_orbits() -> None:
    g = orbits.ellipse_geometry(earth())
    assert g.a / AU == pytest.approx(1.00000261) and g.e == pytest.approx(0.01671123)
    assert g.q / AU == pytest.approx(0.98329, abs=1e-5) and g.big_q / AU == pytest.approx(1.01671, abs=1e-5)
    assert g.b / AU == pytest.approx(1.00000261 * math.sqrt(1 - 0.01671123**2), rel=1e-12)
    assert np.linalg.norm(g.centre) == pytest.approx(g.c) and np.linalg.norm(g.empty_focus) == pytest.approx(2 * g.c)
    h = orbits.ellipse_geometry(halley())
    assert (h.q / AU, h.big_q / AU, h.b / AU) == pytest.approx((0.58603, 35.0820, 4.5342), abs=1e-4)
    assert halley().period / orbits.YEAR == pytest.approx(75.31, abs=0.01)
    for geo in (g, h):
        # an end of the minor axis is a from both foci; the apsides lie on the ellipse, on the axis
        assert np.linalg.norm(geo.minor_point) == pytest.approx(geo.a, rel=1e-12)
        assert np.linalg.norm(geo.minor_point - geo.empty_focus) == pytest.approx(geo.a, rel=1e-12)
        assert np.linalg.norm(geo.periapsis_point) == pytest.approx(geo.q) and np.linalg.norm(geo.apoapsis_point) == pytest.approx(geo.big_q)
        assert np.dot(geo.p_hat, geo.q_hat) == pytest.approx(0, abs=1e-15)
    with pytest.raises(VidgenError, match="e < 1"):
        orbits.ellipse_geometry(orbits.Elements.from_periapsis(orbits.GM_EARTH, 7e6, 1.5))


def test_apsis_names_follow_the_body() -> None:
    assert orbits.apsis_names("Sun") == ("perihelion", "aphelion")
    assert orbits.apsis_names("Earth") == ("perigee", "apogee")
    assert orbits.apsis_names("Moon") == ("perilune", "apolune")
    assert orbits.apsis_names("Jupiter") == ("perijove", "apojove")
    assert orbits.apsis_names("Kepler-16") == ("periapsis", "apoapsis")


@pytest.mark.parametrize("which", ["comet", "halley", "earth"])
def test_equal_times_sweep_equal_areas_to_rounding(which: str) -> None:
    el = {"comet": orbits.Elements.from_a(orbits.GM_SUN, 3 * AU, 0.8, argp=1.2, nu=2.0), "halley": halley(), "earth": earth()}[which]
    for count, start in ((8, 0.0), (12, 0.37 * el.period), (2, 1e6)):
        areas = orbits.sector_areas(el, count, start)
        assert len(areas) == count
        assert areas.max() / areas.min() - 1 < 1e-11
        assert areas.sum() == pytest.approx(math.pi * el.a * el.b, rel=1e-12)
    assert orbits.sector_areas(el, 1)[0] == pytest.approx(math.pi * el.a * el.b, rel=1e-12)
    # the area integrated from the shape alone agrees with the polygon of many positions
    ts = np.linspace(0.0, el.period / 8, 20001)
    assert orbits.swept_area(el.positions(ts)) == pytest.approx(orbits.sector_areas(el, 8)[0], rel=1e-7)


def test_vis_viva_speeds_of_the_earth() -> None:
    el = earth()
    v_peri, v_apo = el.speed_at(0.0), el.speed_at(math.pi)
    assert v_peri / 1000 == pytest.approx(30.29, abs=0.01) and v_apo / 1000 == pytest.approx(29.29, abs=0.01)
    assert v_peri * el.periapsis == pytest.approx(v_apo * el.apoapsis, rel=1e-12)   # angular momentum
    for t in np.linspace(0, el.period, 7):
        r, v = el.states(t)
        assert np.linalg.norm(v) == pytest.approx(orbits.vis_viva(el.mu, np.linalg.norm(r), el.a), rel=1e-12)


def test_newtons_cannonball_is_classified_by_energy() -> None:
    mu, radius = orbits.GM_EARTH, orbits.R_EARTH
    r0 = 1.1 * radius
    vc = orbits.circular_speed(mu, r0)
    speeds = [0.6 * vc, 0.97 * vc, 0.99 * vc, vc, 1.2 * vc, 1.414 * vc, orbits.named_speed("escape", mu, r0), 1.6 * vc]
    shots = orbits.cannon_shots(mu, radius, r0, speeds)
    assert [s.kind for s in shots] == ["suborbital", "suborbital", "elliptical", "circular", "elliptical", "elliptical", "parabolic", "hyperbolic"]
    assert [math.copysign(1, s.energy) for s in shots[:6]] == [-1] * 6 and shots[-1].energy > 0
    assert shots[6].elements.e == 1.0 and orbits.named_speed("escape", mu, r0) == pytest.approx(math.sqrt(2) * vc)
    assert shots[-1].elements.v_infinity == pytest.approx(math.sqrt((1.6 * vc) ** 2 - 2 * vc**2), rel=1e-12)
    for s in shots:
        r, v = s.elements.state()
        assert np.linalg.norm(r) == pytest.approx(r0) and np.dot(r, v) == pytest.approx(0, abs=1e-3 * r0)   # fired horizontally
    for s in shots[:2]:   # a falling shot meets the ground at its impact time, and not before
        assert np.linalg.norm(s.positions(s.impact)) == pytest.approx(radius, rel=1e-9)
        assert min(np.linalg.norm(s.positions(np.linspace(0, s.impact * 0.999, 200)), axis=1)) > radius
        assert np.linalg.norm(s.positions(s.impact * 2)) == pytest.approx(radius, rel=1e-9)   # it stays where it landed
    assert shots[2].impact is None and shots[2].elements.periapsis > radius
    clockwise = orbits.cannon_shots(mu, radius, r0, [vc])[0].elements
    assert clockwise.i == pytest.approx(math.pi)   # fired to the right of the top: clockwise seen from above
    with pytest.raises(VidgenError, match="above the surface"):
        orbits.cannon_shots(mu, radius, 0.9 * radius, [vc])


def test_kepler_third_law_for_the_planets() -> None:
    cols = orbits.kepler_planets()
    assert orbits.kepler_planet_names() == ["Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]
    assert cols["T"][2] == pytest.approx(1.0, abs=1e-4) and cols["T"][0] * 365.25 == pytest.approx(87.97, abs=0.01)
    slope = np.polyfit(np.log(cols["a"]), np.log(cols["T"]), 1)[0]
    assert slope == pytest.approx(1.5, abs=2e-4)
    assert np.allclose(cols["T_law"] ** 2, cols["a3"] * (2 * math.pi) ** 2 * AU**3 / orbits.GM_SUN / orbits.YEAR**2, rtol=1e-12)
    sim = plotcore.run_registered("kepler_planets", units={"a": "AU", "T": "yr"})
    assert list(sim.columns) == ["a", "T", "T_law", "a3", "T2"] and np.allclose(sim.columns["T"], cols["T"])
    with pytest.raises(VidgenError, match="takes no params"):
        plotcore.run_registered("kepler_planets", params={"x": 1})
