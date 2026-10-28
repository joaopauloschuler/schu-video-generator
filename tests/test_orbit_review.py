"""Step 236, review of Phase X (DESIGN §98.10): the orbit model against independent
calculations (written here from the textbook formulas, with scipy's root finding and
integration), the orbit scene's fast live text, the 16:9 column caption and the 9:16 transfer
panel, substitutions in one common unit, and the still parts drawn once per play."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_actions import render
from vidgen import orbits, plot_draw
from vidgen.orbits import ephemeris as eph
from vidgen.project import Project
from vidgen.quantities.calc import CalcInput, SymbolInput, work
from vidgen.scenes.orbit_text import LiveText
from vidgen.theme import Theme

NARRATION = {"pad": 0.2, "words_per_second": 4.0}
GM_E = orbits.GM_EARTH


# ----- the model against independent calculations ----------------------------------------------


def _coe2rv(mu: float, p: float, e: float, i: float, raan: float, argp: float, nu: float) -> tuple[np.ndarray, np.ndarray]:
    """Vallado's COE2RV: the perifocal state rotated by R3(−Ω) R1(−i) R3(−ω)."""
    r_pqw = p / (1 + e * math.cos(nu)) * np.array([math.cos(nu), math.sin(nu), 0.0])
    v_pqw = math.sqrt(mu / p) * np.array([-math.sin(nu), e + math.cos(nu), 0.0])
    co, so, ci, si, cw, sw = math.cos(raan), math.sin(raan), math.cos(i), math.sin(i), math.cos(argp), math.sin(argp)
    rot = np.array([[co * cw - so * sw * ci, -co * sw - so * cw * ci, so * si],
                    [so * cw + co * sw * ci, -so * sw + co * cw * ci, -co * si],
                    [sw * si, cw * si, ci]])
    return rot @ r_pqw, rot @ v_pqw


def test_kepler_and_conversions_against_independent_solutions() -> None:
    brentq = pytest.importorskip("scipy.optimize").brentq
    for e in (0.0, 0.5, 0.99, 0.999999):
        for m in np.linspace(-3.1, 3.1, 25):
            big_e = brentq(lambda x: x - e * math.sin(x) - m, -4.2, 4.2, xtol=1e-15)
            nu = 2 * math.atan2(math.sqrt(1 + e) * math.sin(big_e / 2), math.sqrt(1 - e) * math.cos(big_e / 2))
            assert orbits.true_from_mean(float(m), e) == pytest.approx(nu, abs=1e-9)
    for e in (1.000001, 1.5, 10.0):
        for m in np.linspace(-20, 20, 21):
            h = brentq(lambda x: e * math.sinh(x) - x - m, -50, 50, xtol=1e-15)
            assert orbits.true_from_mean(float(m), e) == pytest.approx(2 * math.atan(math.sqrt((e + 1) / (e - 1)) * math.tanh(h / 2)), abs=1e-9)
    rng = np.random.default_rng(236)
    for _ in range(100):
        e = float(rng.choice([rng.uniform(0.01, 0.95), rng.uniform(1.05, 4.0)]))
        lim = math.acos(-1 / e) - 0.05 if e > 1 else math.pi
        args = (float(rng.uniform(7e6, 5e7)), e, float(rng.uniform(0.05, 3.0)), float(rng.uniform(0, 6.2)), float(rng.uniform(0, 6.2)),
                float(rng.uniform(-lim, lim)))
        r, v = _coe2rv(GM_E, *args)
        el = orbits.Elements(GM_E, *args)
        assert np.allclose(el.state()[0], r, rtol=1e-12, atol=1e-6) and np.allclose(el.state()[1], v, rtol=1e-12, atol=1e-9)
        back = orbits.Elements.from_state(GM_E, r, v)
        assert back.p == pytest.approx(args[0], rel=1e-12) and back.e == pytest.approx(e, abs=1e-12)


def test_propagation_against_numerical_integration() -> None:
    solve_ivp = pytest.importorskip("scipy.integrate").solve_ivp

    def twobody(t: float, y: np.ndarray) -> np.ndarray:
        return np.concatenate([y[3:], -GM_E * y[:3] / np.linalg.norm(y[:3]) ** 3])

    for e in (0.7, 1.0, 1.8):
        el = orbits.Elements(GM_E, 1.2e7, e, 0.4, 1.0, 2.0, -1.0)
        ts = np.linspace(0, 40_000, 9)
        sol = solve_ivp(twobody, (0, ts[-1]), np.concatenate(el.state()), t_eval=ts, rtol=1e-12, atol=1e-6, method="DOP853")
        rs = el.states(ts)[0]
        assert np.max(np.linalg.norm(rs - sol.y[:3].T, axis=1) / np.linalg.norm(rs, axis=1)) < 1e-8


def test_manoeuvres_flyby_and_lagrange_against_textbook_formulas() -> None:
    brentq = pytest.importorskip("scipy.optimize").brentq
    r1, r2 = orbits.R_EARTH + 300e3, 42_164.17e3
    h = orbits.hohmann(GM_E, r1, r2)
    assert h.dv1 == pytest.approx(math.sqrt(GM_E / r1) * (math.sqrt(2 * r2 / (r1 + r2)) - 1), rel=1e-12)
    assert h.dv2 == pytest.approx(math.sqrt(GM_E / r2) * (1 - math.sqrt(2 * r1 / (r1 + r2))), rel=1e-12)
    assert h.total == pytest.approx(3893, abs=1) and h.time / 3600 == pytest.approx(5.275, abs=1e-3)
    lo, hi = orbits.bielliptic_thresholds()
    assert (lo, hi) == (pytest.approx(11.93876, abs=1e-5), pytest.approx(15.5817, abs=1e-4))
    mu_j, v_inf, rp = orbits.BODIES["jupiter"].gm, 5.6e3, 271_492e3
    ga = orbits.gravity_assist(mu_j, [0.0, 13.06e3], [v_inf * math.cos(-1.2), v_inf * math.sin(-1.2)], rp, side="behind", radius=71_492e3)
    turn = math.acos(float(ga.flyby.v_in @ ga.flyby.v_out) / v_inf**2)
    assert turn == pytest.approx(2 * math.asin(1 / (1 + rp * v_inf**2 / mu_j)), abs=1e-9)
    vp = np.array([0.0, 13.06e3, 0.0])
    assert ga.gain == pytest.approx(np.linalg.norm(vp + ga.flyby.v_out) - np.linalg.norm(vp + ga.flyby.v_in), rel=1e-12) and ga.gain > 0
    for mu in (0.012150585, 3.0035e-6, 0.05):
        def fx(x: float) -> float:
            return x - (1 - mu) * (x + mu) / abs(x + mu) ** 3 - mu * (x - 1 + mu) / abs(x - 1 + mu) ** 3
        pts = orbits.lagrange_points(mu)
        assert pts["L1"][0] == pytest.approx(brentq(fx, 0.5 - mu, 1 - mu - 1e-9), abs=1e-12)
        assert pts["L2"][0] == pytest.approx(brentq(fx, 1 - mu + 1e-9, 2.0), abs=1e-12)
        assert pts["L3"][0] == pytest.approx(brentq(fx, -2.0, -mu - 1e-9), abs=1e-12)
        assert orbits.lagrange_jacobi(mu)["L4"] == pytest.approx(3 - mu + mu * mu, abs=1e-12)


def test_ephemeris_against_published_dates() -> None:
    """Oppositions and inferior conjunctions from JPL's Table 1 against the published dates
    (within a day; the table's own accuracy is minutes of arc)."""
    for kind, target, date in [("opposition", "mars", "2018-07-27"), ("opposition", "mars", "2025-01-16"), ("opposition", "jupiter", "2023-11-03"),
                               ("opposition", "saturn", "2024-09-08"), ("inferior_conjunction", "venus", "2023-08-13"),
                               ("inferior_conjunction", "venus", "2025-03-23"), ("conjunction", "mars", "2023-11-18")]:
        published = eph.julian_date(date) + 0.5
        assert eph.next_event(kind, "earth", target, published - 60).jd == pytest.approx(published, abs=1.0), (kind, target)


# ----- fast live text ------------------------------------------------------------------------------


def test_live_text_matches_text() -> None:
    theme = Theme()
    live = LiveText(theme, 24, "text")
    for s in ["t = 82.2 d", "× 1.3 million", "Δv₁ = 2.94 km/s", "θ at departure = 44.3°", "2026-11-08", "Earth–Mars 0.678 AU",
              "ΔE/E = −1.23×10⁻¹⁰", "t = 11:30 h", "17 17 71 11 14 41", "sizes not to scale"]:
        ref = plot_draw.label_text(s, size=24, theme=theme)
        got = live.text(s)
        assert len(got) == len(ref.submobjects), s
        assert max(float(np.max(np.abs(g.points - r.points))) for g, r in zip(got, ref.submobjects)) < 1e-5, s   # far below a pixel
        assert all(type(g).__name__ == "VMobject" for g in got)   # no SVG path kept (light to copy and hold)
        assert live.size_of(s) == pytest.approx((ref.width, ref.height), abs=1e-5)


# ----- substitutions in one unit ---------------------------------------------------------------------


def test_substitution_in_one_common_unit() -> None:
    syms = [SymbolInput(name="v_inf", value="2.945 km/s"), SymbolInput(name="v_esc", value="10.93 km/s"), SymbolInput(name="v_c", value="7726 m/s"),
            SymbolInput(name="GM_earth", constant="GM_earth"), SymbolInput(name="r", value="6678 km"), SymbolInput(name="ang", value="30 deg"),
            SymbolInput(name="T", value="259 d"), SymbolInput(name="T_M", value="687.0 d")]
    calcs = [CalcInput(name="dv", expr="sqrt(v_inf^2 + v_esc^2) - v_c", unit="km/s", sig=3),
             CalcInput(name="w", expr="v_inf*sin(ang)", unit="km/s"),
             CalcInput(name="v", expr="sqrt(GM_earth/r)", unit="km/s"),
             CalcInput(name="th", expr="pi*(1 - 2*T/T_M)", unit="deg")]
    steps = {r.name: next(s for s in r.steps if s.kind == "substitute") for r in work(syms, calcs).results}
    dv = steps["dv"]
    # every speed in km/s (7726 m/s too), the unit once after the bracket; it keeps a unit, before the SI numbers
    assert dv.common == r"\left(\sqrt{{{2.945}}^{2} + {{10.93}}^{2}} - {7.726}\right)\,\mathrm{km}/\mathrm{s}"
    assert dv.variants().index(dv.common) < dv.variants().index(dv.alt) and dv.common in dv.unit_variants()
    assert "30^{\\circ}" in steps["w"].common   # an angle keeps its own unit
    assert steps["v"].common == ""             # different dimensions: no common unit (the SI numbers stay the unit-free way)
    th = steps["th"]   # a pure-number result: the days cancel, no unit after — so it does not count as keeping the units
    assert "{259}" in th.common and r"\mathrm{d}" not in th.common and th.common_bare and th.common not in th.unit_variants()


# ----- the scene: layout, panel and the still parts ---------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


HOHMANN = {"title": "The Hohmann transfer", "bodies": [{"preset": "earth", "e": 0, "i": 0, "raan": 0, "argp": 0, "trail": False},
                                                       {"preset": "mars", "e": 0, "i": 0, "raan": 0, "argp": 0, "nu": 95, "trail": False},
                                                       {"name": "Ship", "alongside": "Earth"}],
           "transfer": {"ship": "Ship", "to": "Mars"}, "caption": "Circular, coplanar orbits (an approximation)"}


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_layout_column_caption_and_portrait_panel(size: tuple[int, int], make_project, media: Path) -> None:
    from vidgen.scenes.orbit import CLOCK_Z, STILL_Z, TEMPLATE_CACHE

    sc = {"id": "h", "type": "orbit", "params": HOHMANN, "beats": [{"text": "we leave now"}, {"text": "and coast to mars"}]}
    project = Project.load(make_project(minimal_config(scenes=[sc], narration=NARRATION)))
    s = render(project, "h", media, size)
    plot, box, cap = s._lay.plot, s._readout_box, s._caption
    names = [slot.name for slot in s._slots]
    if size[0] > size[1]:
        # 16:9: the caption stands in the side column under the panel; the picture takes the height under the title
        assert cap.get_left()[0] >= plot.x1 and cap.get_top()[1] <= box.y0 + 1e-6 and cap.get_left()[0] == pytest.approx(box.x0, abs=1e-6)
        assert plot.height > 0.64 * s.frame_height
        assert names.count("dv") == 2
    else:
        # 9:16: the caption under the picture; each burn's Δv at its arrow, not in the panel
        assert cap.get_top()[1] < plot.y0 and "dv" not in names and "total_dv" in names
    assert s._title.z_index == STILL_Z and cap.z_index == STILL_Z and s._clock_mob.z_index == CLOCK_Z
    assert len(s._templates) <= TEMPLATE_CACHE
