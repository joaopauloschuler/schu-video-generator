"""The Solar System on a date (Phase X, Step 233; DESIGN §98.7): JPL's approximate elements
(Table 1) on dates, Julian dates, positions against values derived independently (the Earth at the
equinoxes, the distances within perihelion and aphelion), periods and synodic periods, oppositions
and conjunctions against their published dates, validity — and the ``orbit`` scene's ``date``,
``event``, ``radial: log``, ``inset``, ``sizes`` and the compact side panel, with tiny renders."""

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
from vidgen.errors import VidgenError
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}
DAY = orbits.DAY
EIGHT = ("mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune")


def cls() -> Any:
    extensions.load_builtins()
    return registry.get("orbit").cls


# ----- dates ------------------------------------------------------------------------------------------


def test_julian_dates() -> None:
    assert orbits.julian_date("2000-01-01 12:00") == 2451545.0
    assert orbits.julian_date("1999-12-31") == 2451543.5   # 0h: half a day before noon on the next day
    assert orbits.julian_date("1858-11-17") == 2400000.5   # the modified Julian date's zero
    assert orbits.julian_date("2020-10-13T23:30") == pytest.approx(2459136.479166667, abs=1e-9)
    jd = orbits.julian_date("2022-12-08 05:36")
    assert orbits.date_text(jd, time=True) == "2022-12-08 05:36" and orbits.date_text(jd) == "2022-12-08"
    assert orbits.date_text(orbits.julian_date("2020-10-13 23:59")) == "2020-10-13"   # the day it falls on
    with pytest.raises(VidgenError, match="is not a date"):
        orbits.julian_date("13/10/2020")


def test_validity_range() -> None:
    lo, hi = orbits.valid_range()
    assert orbits.date_text(lo) == "1800-01-01" and orbits.date_text(hi - 1e-6) == "2050-12-31"
    orbits.check_valid(orbits.julian_date("1800-01-01"))
    orbits.check_valid(orbits.julian_date("2050-12-31 23:00"))
    for bad in ("1799-12-31", "2051-01-01"):
        with pytest.raises(VidgenError, match="outside 1800-2050"):
            orbits.check_valid(orbits.julian_date(bad))
    with pytest.raises(VidgenError, match="ends on"):
        orbits.check_valid(orbits.julian_date("2050-06-01"), orbits.julian_date("2051-06-01"))


# ----- elements and positions ---------------------------------------------------------------------------


#: JPL Table 1 transcribed independently (value at J2000, then rate per century), to catch typos.
JPL_TABLE1 = {
    "mercury": ((0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593),
                (0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081)),
    "venus": ((0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255),
              (0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418)),
    "earth": ((1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0),
              (0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0)),
    "mars": ((1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891),
             (0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343)),
    "jupiter": ((5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909),
                (-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106)),
    "saturn": ((9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448),
               (-0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794)),
    "uranus": ((19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.95427630, 74.01692503),
               (-0.00196176, -0.00004397, -0.00242939, 428.48202785, 0.40805281, 0.04240589)),
    "neptune": ((30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574),
                (0.00026291, 0.00005105, 0.00035372, 218.45945325, -0.32241464, -0.00508664)),
    "pluto": ((39.48211675, 0.24882730, 17.14001206, 238.92903833, 224.06891629, 110.30393684),
              (-0.00031596, 0.00005170, 0.00004818, 145.20780515, -0.04062942, -0.01183482)),
}


def test_table1_all_values_pinned() -> None:
    assert list(orbits.TABLE1) == list(JPL_TABLE1)
    n = 0
    for planet, (base, rate) in JPL_TABLE1.items():
        got_base, got_rate = orbits.TABLE1[planet]
        for k, (want, got) in enumerate(zip(base + rate, got_base + got_rate)):
            assert got == want, f"{planet} column {k}: {got} != {want}"
            n += 1
    assert n == 108   # 9 bodies x 12 numbers (54 values at J2000 + 54 rates)


def test_table1_values_and_presets() -> None:
    (a, e, i, L, peri, node), rates = orbits.TABLE1["mars"]
    assert (a, e, i, L, peri, node) == (1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891)
    assert rates[3] == 19140.30268499
    p = orbits.ORBITS["mars"]   # the presets read the same table (J2000)
    assert p.a == pytest.approx(a * orbits.AU) and p.e == e and math.degrees(p.raan) == pytest.approx(node)
    m = orbits.mean_elements("mars", orbits.J2000 + 36525)   # one century later: value + rate
    assert m.a == pytest.approx(a + rates[0]) and m.mean_longitude == pytest.approx(L + rates[3])
    on = orbits.preset_on("mars", orbits.J2000)
    assert on.a == p.a and on.mean_anomaly == pytest.approx(p.mean_anomaly)
    assert "pluto" in orbits.ORBITS and orbits.BODIES["pluto"].radius == pytest.approx(1188.3e3)
    assert "pluto" not in [n.lower() for n in orbits.kepler_planet_names()]   # Kepler III stays the eight planets
    with pytest.raises(VidgenError, match="did you mean 'mars'"):
        orbits.planet_key("marz")
    with pytest.raises(VidgenError, match="not in JPL's Table 1"):
        orbits.planet_key("ceres")


def test_earth_at_the_equinoxes() -> None:
    """At a March equinox the Sun is at geocentric longitude 0° of date, so the Earth is at
    heliocentric longitude 180° of date; Table 1's frame is the J2000 equinox, which precession
    (50.29″ per year) moves: 180° − 0.01397° per year since 2000. The Earth–Moon barycentre is
    within 6″ of the Earth seen from the Sun."""
    for when, of_date in (("2020-03-20 03:50", 180.0), ("2021-03-20 09:37", 180.0), ("2022-09-23 01:04", 360.0), ("1900-03-21 01:39", 180.0)):
        jd = orbits.julian_date(when)
        years = (jd - orbits.J2000) / 365.25
        expected = (of_date - 50.29 / 3600 * years) % 360
        got = float(orbits.ecliptic_longitude("earth", jd))
        assert abs((got - expected + 180) % 360 - 180) < 0.03, when


def test_distances_stay_between_perihelion_and_aphelion() -> None:
    jds = orbits.julian_date("1800-01-01") + np.linspace(0.0, 250 * 365.25, 2500)
    for k in orbits.PLANETS:
        r = np.linalg.norm(orbits.heliocentric(k, jds), axis=1)
        q, Q = [], []
        for jd in jds[::250]:
            m = orbits.mean_elements(k, jd)
            q.append(m.a * (1 - m.e))
            Q.append(m.a * (1 + m.e))
        assert r.min() >= min(q) * orbits.AU * (1 - 1e-4) and r.max() <= max(Q) * orbits.AU * (1 + 1e-4), k
        assert r.max() / r.min() > 1.001   # they move in and out (the eccentric orbits)
    # the J2000 position from the elements by hand (Mars: M = L − ϖ, Kepler's equation, rotations)
    m = orbits.mean_elements("mars", orbits.J2000)
    M = math.radians(m.mean_longitude - m.peri_longitude)
    E = float(orbits.eccentric_anomaly(M, m.e))
    r = m.a * (1 - m.e * math.cos(E)) * orbits.AU
    assert np.linalg.norm(orbits.heliocentric("mars", orbits.J2000)) == pytest.approx(r, rel=1e-12)


def test_periods_and_synodic_periods() -> None:
    assert orbits.sidereal_period("earth") / DAY == pytest.approx(365.2564, abs=1e-3)   # the sidereal year
    assert orbits.sidereal_period("mars") / DAY == pytest.approx(686.98, abs=0.01)
    assert orbits.sidereal_period("jupiter") / orbits.YEAR == pytest.approx(11.862, abs=1e-3)
    syn = {k: orbits.planet_synodic_period("earth", k) / DAY for k in ("mars", "venus", "jupiter", "mercury", "saturn")}
    assert syn["mars"] == pytest.approx(780, abs=1) and syn["venus"] == pytest.approx(584, abs=0.5)
    assert syn["jupiter"] == pytest.approx(399, abs=0.5) and syn["mercury"] == pytest.approx(115.88, abs=0.05)
    assert syn["saturn"] == pytest.approx(378.1, abs=0.2)
    # the same as 231's synodic period from the two periods
    assert orbits.synodic_period(orbits.sidereal_period("earth"), orbits.sidereal_period("mars")) / DAY == pytest.approx(syn["mars"])


@pytest.mark.parametrize("kind,target,after,published", [
    ("opposition", "mars", "2020-01-01", "2020-10-13"),
    ("opposition", "mars", "2022-01-01", "2022-12-08"),
    ("opposition", "mars", "2018-01-01", "2018-07-27"),
    ("opposition", "mars", "2024-01-01", "2025-01-16"),
    ("inferior_conjunction", "venus", "2020-01-01", "2020-06-03"),
    ("inferior_conjunction", "venus", "2023-01-01", "2023-08-13"),
    ("opposition", "jupiter", "2023-01-01", "2023-11-03"),
    ("opposition", "saturn", "2023-01-01", "2023-08-27"),
])
def test_events_against_published_dates(kind: str, target: str, after: str, published: str) -> None:
    """Published dates (UT) of oppositions and conjunctions; the approximate elements give them
    within hours — the test allows ±2 days."""
    ev = orbits.next_event(kind, "earth", target, orbits.julian_date(after))
    assert abs(ev.jd - orbits.julian_date(published + " 12:00")) < 2.0
    assert ev.elongation > 170 if kind == "opposition" else ev.elongation < 10


def test_event_geometry_and_errors() -> None:
    jd0 = orbits.julian_date("2020-01-01")
    opp = orbits.next_event("opposition", "earth", "mars", jd0)
    conj = orbits.next_event("conjunction", "earth", "mars", opp.jd)   # behind the Sun about a year later
    assert 300 < conj.jd - opp.jd < 450 and conj.elongation < 5 and conj.distance > 2 * orbits.AU
    nxt = orbits.next_event("opposition", "earth", "mars", opp.jd)
    assert nxt.jd - opp.jd == pytest.approx(780, abs=60)   # the synodic period, give or take Mars's eccentricity
    assert [round(e.jd) for e in orbits.events_between("opposition", "earth", "mars", jd0, nxt.jd + 1)] == [round(opp.jd), round(nxt.jd)]
    # Step 235: each event once (the 2029 opposition used to come twice: the bisection stops just before the root)
    later = [e.date for e in orbits.events_between("opposition", "earth", "mars", orbits.julian_date("2024-01-01"), orbits.julian_date("2031-12-31"))]
    assert later == ["2025-01-16", "2027-02-19", "2029-03-25", "2031-05-04"]
    sup = orbits.next_event("superior_conjunction", "earth", "venus", jd0)
    assert sup.distance > 1.5 * orbits.AU
    with pytest.raises(VidgenError, match="never in opposition"):
        orbits.next_event("opposition", "earth", "venus", jd0)
    with pytest.raises(VidgenError, match="farther from the Sun"):
        orbits.next_event("inferior_conjunction", "earth", "mars", jd0)
    with pytest.raises(VidgenError, match="outside 1800-2050"):
        orbits.next_event("opposition", "earth", "neptune", orbits.julian_date("2050-12-01"))


# ----- the scene -----------------------------------------------------------------------------------------

OPPOSITION = {"date": "2020-06-01", "bodies": [{"preset": "earth"}, {"preset": "mars"}], "event": {"of": "Mars"}}
WHOLE = {"date": "2024-01-01", "bodies": [{"preset": k} for k in EIGHT], "inset": True, "span": "2 yr"}
LOG = {"date": "2024-01-01", "bodies": [{"preset": k} for k in (*EIGHT, "pluto")], "radial": "log", "span": "1 yr"}


def test_scene_on_a_date() -> None:
    p = cls().validate_params(OPPOSITION)
    m = p.model()
    ev = m.sky.event
    assert ev.date == "2020-10-13" and m.span == pytest.approx(1.15 * m.sky.event_t)
    # the scene's Kepler motion from the date's elements stays on Table 1's positions
    for t in (0.0, m.sky.event_t, m.span):
        for name in ("Earth", "Mars"):
            table = orbits.heliocentric(name.lower(), m.sky.jd0 + t / DAY)
            assert np.linalg.norm(m.position(name, t) - table) < 2e-4 * orbits.AU, (name, t)
    assert cls().target_names(p) == ["frame", "central", "body:Earth", "orbit:Earth", "body:Mars", "orbit:Mars", "event", "readout"]
    w = cls().validate_params(WHOLE).model()
    assert w.sky.inner == ["Mercury", "Venus", "Earth", "Mars"] and 1.6 * orbits.AU < w.sky.inset < 1.9 * orbits.AU
    assert "inset" in cls().target_names(cls().validate_params(WHOLE))
    lg = cls().validate_params(LOG).model()
    assert lg.sky.log and lg.sky.r0 == pytest.approx(orbits.ORBITS["mercury"].a * 0 + min(o.elements.periapsis for o in lg.system.orbiters) / 3)
    s = cls().validate_params({"sizes": True})
    assert cls().target_names(s) == ["frame", "central", *[f"body:{k.capitalize()}" for k in EIGHT]]
    assert cls().target_text(s, "body:Jupiter") == "Jupiter"


@pytest.mark.parametrize("params,message", [
    ({"date": "1700-01-01", "bodies": [{"preset": "earth"}]}, "outside 1800-2050"),
    ({"date": "2050-06-01", "bodies": [{"preset": "earth"}], "span": "2 yr"}, "ends on 2052"),
    ({"date": "2020-13-01", "bodies": [{"preset": "earth"}]}, "is not a date"),
    ({"date": "2020-01-01", "central": "earth", "bodies": [{"preset": "moon"}]}, "place it yourself with nu"),
    ({"date": "2020-01-01", "bodies": [{"preset": "earth"}, {"preset": "venus"}], "event": {"of": "Venus"}}, "never in opposition"),
    ({"bodies": [{"preset": "earth"}, {"preset": "mars"}], "event": {"of": "Mars"}}, "give the scene a date"),
    ({"date": "2020-01-01", "bodies": [{"preset": "earth"}], "event": {"of": "Mars"}}, "not a body of the scene"),
    ({"bodies": [{"preset": "earth"}], "radial": "log", "frame": "axes"}, "no linear axes"),
    ({"bodies": [{"preset": "earth", "velocity": True}], "radial": "log"}, "drawn wrongly"),
    ({"bodies": [{"preset": "earth"}], "radial": "log", "inset": True}, "not both"),
    ({"bodies": [{"preset": "earth"}, {"preset": "mars"}], "inset": True}, "every body fits"),
    ({"bodies": [{"preset": "jupiter"}], "inset": True}, "no body's orbit lies within 2 AU"),
    ({"bodies": [{"preset": "earth"}], "panel": ["time", "speed_up"]}, "did you mean 'speedup'"),
    ({"sizes": {"bodies": ["earth", "vulcan"]}}, "unknown body 'vulcan'"),
    ({"sizes": True, "date": "2020-01-01"}, "a scene of its own"),
])
def test_scene_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cls().validate_params(params)


def test_compact_panel_rows() -> None:
    """The compact panel keeps rank 0, then fills to the budget; diagnostics only on request."""
    from vidgen.scenes.orbit_overlays import DIAGNOSTIC, Slot, choose_rows

    rows = [Slot(["t"], name="time", rank=0), Slot(["x"], name="speedup", rank=0), Slot(["E"], name="energy", rank=DIAGNOSTIC),
            Slot(["a"], name="legend", rank=2, scale=0.9), Slot(["b"], name="legend", rank=2), Slot(["m"], name="mu", rank=1, scale=0.85),
            Slot(["n"], name="note", rank=0)]
    names = [s.name for s in choose_rows(rows, "compact", 3)]
    assert names == ["time", "speedup", "mu", "note"]   # the legend's two rows do not fit; never the energy
    assert [s.name for s in choose_rows(rows, "compact", 7)] == ["time", "speedup", "legend", "legend", "mu", "note"]
    assert all(s.scale >= 1 for s in choose_rows(rows, "compact", 7))   # readable sizes
    assert len(choose_rows(rows, "full", 3)) == len(rows)
    assert [s.name for s in choose_rows(rows, ["energy", "time"], 3)] == ["time", "energy", "note"]
    assert [s.name for s in choose_rows(rows, "none", 3)] == ["note"]


def test_diagnostics_whatever_the_panel() -> None:
    trojan = {"system": "sun_jupiter", "bodies": [{"name": "Trojan", "near": "L4", "shift": [0.004, 0.0069]}], "span": "30 yr"}
    d = cls().diagnostics(cls().validate_params(trojan))
    assert set(d) == {"energy_drift", "angular_drift", "jacobi_drift:Trojan"} and d["jacobi_drift:Trojan"] < 1e-8
    assert cls().diagnostics(cls().validate_params(OPPOSITION)) == {}


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_sky_renders(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [
        {"id": "opp", "type": "orbit", "params": OPPOSITION, "beats": [{"text": "mars at opposition"}]},
        {"id": "whole", "type": "orbit", "params": WHOLE, "beats": [{"text": "the planets with an inset"}]},
        {"id": "log", "type": "orbit", "params": LOG, "beats": [{"text": "all of them"}]},
        {"id": "sizes", "type": "orbit", "params": {"sizes": True}, "beats": [{"text": "sizes"}]},
    ]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))
    s = render(project, "opp", media, size)
    assert s._last_lines[0] == orbits.date_text(s._model.sky.jd0 + s._t / DAY)   # the date first
    assert "Mars opposition 2020-10-13" in s._last_lines and s.is_shown("event")
    assert not any("ΔE" in line for line in s._last_lines)
    w = render(project, "whole", media, size)
    assert w._vector_box is not None and w.is_shown("inset")
    assert all(not len(w._bodies[n][1]) for n in w._model.sky.inner)   # named in the inset, not at the crowded Sun
    lg = render(project, "log", media, size)
    assert lg._note == "sizes not to scale" and "distances compressed (log)" in lg._last_lines and lg.is_shown("rings")
    plot = lg._lay.plot
    width, height = lg.camera.frame_width, lg.camera.frame_height   # the safe area is read under the render's config
    if size[0] > size[1]:
        assert plot.height > 0.65 * height   # the picture gets the room
    else:
        assert plot.width > 0.8 * width
    centre = lg._frame_point(np.zeros(3))
    radii = {o.name: float(np.linalg.norm(lg._bodies[o.name][0].get_center() - centre)) for o in lg._model.system.orbiters}
    assert radii["Mercury"] < radii["Earth"] < radii["Jupiter"] < radii["Neptune"]   # monotone in distance
    z = render(project, "sizes", media, size)
    assert z.is_shown("body:Jupiter") and z.is_shown("central")
