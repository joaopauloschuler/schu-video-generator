"""Relativistic kinematics (Phase Y, Step 239; DESIGN §99.7–§99.8): four-vectors, invariant
masses, Källén p* for textbook decays, boosts (m² invariant), thresholds, decay lengths, SI
conversions, PDG values in ``calculation`` symbols, the ``two_body_opening`` plot model, the
``kinematics`` scene's params, targets, values for ``from_scene``, the ``boost`` action and tiny
renders in 16:9 and 9:16. Also the gluon coil of Step 238's ``feynman`` notation."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_actions import render
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.particle_physics import PARTICLES, kinematics as kin
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}
M = {k: PARTICLES[k].mass_mev for k in PARTICLES}


# ----- four-vectors and invariant mass ------------------------------------------------------------


def test_invariant_mass_round_trips() -> None:
    a = kin.FourVector.from_mass(M["mu+"], 29.79, 30.0)
    assert a.mass == pytest.approx(M["mu+"], rel=1e-12) and a.p == pytest.approx(29.79)
    assert a.angle == pytest.approx(30.0)
    pair = kin.two_body("Z -> mu+ mu-").rest_vectors(40.0)
    assert kin.invariant_mass(pair) == pytest.approx(M["Z"], rel=1e-12)
    # two photons of 62.6 GeV back to back: the Higgs mass; at 90° the mass is √2 smaller... computed, not assumed
    g1, g2 = kin.FourVector.from_mass(0, 62600, 0), kin.FourVector.from_mass(0, 62600, 180)
    assert kin.invariant_mass([g1, g2]) == pytest.approx(125200)
    g3 = kin.FourVector.from_mass(0, 62600, 90)
    assert kin.invariant_mass([g1, g3]) == pytest.approx(math.sqrt(2 * 62600**2 * (1 - math.cos(math.pi / 2))))
    assert kin.FourVector(5.0, 3.0, 4.0).mass == 0.0   # massless within rounding
    assert kin.total([g1, g2]).p == pytest.approx(0, abs=1e-6)


def test_boost_keeps_m2_and_the_rest_frame() -> None:
    v = kin.FourVector.from_mass(M["p"], 1500.0, 37.0)
    for beta in (0.1, 0.5, 0.99, 0.999999, np.array([0.3, -0.4, 0.2])):
        w = v.boost(beta)
        assert w.mass2 == pytest.approx(v.mass2, rel=1e-9)
    # boosting a particle by minus its own velocity puts it at rest
    rest = v.boost(-v.beta_vector)
    assert rest.p == pytest.approx(0, abs=1e-6) and rest.energy == pytest.approx(M["p"])
    # Minkowski products are frame independent too
    a, b = kin.FourVector.from_mass(M["pi+"], 300, 10), kin.FourVector.from_mass(M["e-"], 50, 200)
    assert a.boost(0.7).dot(b.boost(0.7)) == pytest.approx(a.dot(b), rel=1e-9)
    lab = kin.system_picture([("gamma", 80000, 25), ("gamma", 57390, -110)])
    assert sum(lab.rest, kin.FourVector(0)).p == pytest.approx(0, abs=1e-6)
    assert [v.px for v in lab.lab] == pytest.approx([80000 * math.cos(math.radians(25)), 57390 * math.cos(math.radians(-110))])
    assert lab.mass == pytest.approx(125200, rel=2e-4)


def test_boost_factors_and_their_errors() -> None:
    b = kin.Boost.from_momentum(10000, M["pi+"])
    assert b.beta_gamma == pytest.approx(10000 / M["pi+"]) and b.gamma == pytest.approx(math.hypot(10000, M["pi+"]) / M["pi+"])
    assert kin.Boost.from_energy(4000, M["mu-"]).gamma == pytest.approx(4000 / M["mu-"])
    assert kin.Boost.from_kinetic(M["p"], M["p"]).gamma == pytest.approx(2.0)
    assert kin.Boost.from_gamma(2).beta == pytest.approx(math.sqrt(3) / 2)
    with pytest.raises(VidgenError, match="superluminal"):
        kin.gamma_of(1.2)
    with pytest.raises(VidgenError, match="not below 1"):
        kin.Boost.from_beta(1.0)
    with pytest.raises(VidgenError, match="γ must be at least 1"):
        kin.Boost.from_gamma(0.5)
    with pytest.raises(VidgenError, match="below the mass"):
        kin.Boost.from_energy(50, M["mu-"])
    with pytest.raises(VidgenError, match="negative mass²"):
        _ = kin.FourVector(1.0, 2.0).mass
    with pytest.raises(VidgenError, match="massless"):
        kin.Boost.from_momentum(10, 0)
    with pytest.raises(VidgenError, match="exactly one"):
        kin.motion(M["mu-"], momentum=1, beta=0.5)


# ----- two-body decays ----------------------------------------------------------------------------


@pytest.mark.parametrize(("decay", "p_star"), [("pi+ -> mu+ nu_mu", 29.79), ("K+ -> pi+ pi0", 205.14), ("Lambda -> p pi-", 100.58),
                                               ("Z -> mu+ mu-", 45593.9), ("H -> gamma gamma", 62600.0), ("pi0 -> gamma gamma", 67.488)])
def test_kallen_momentum_of_textbook_decays(decay: str, p_star: float) -> None:
    d = kin.two_body(decay)
    assert d.p_star == pytest.approx(p_star, rel=2e-4)
    e1, e2 = d.energies
    assert e1 + e2 == pytest.approx(d.parent.mass_mev)
    assert e1**2 - d.p_star**2 == pytest.approx(d.first.mass_mev**2, abs=1e-6 * e1**2)


def test_kallen_function() -> None:
    assert kin.kallen(9, 4, 1) == 81 + 16 + 1 - 72 - 8 - 18
    # massless products: p* = M/2
    assert kin.two_body_momentum(100.0, 0.0, 0.0) == pytest.approx(50.0)
    # one massless product: p* = (M² − m²) / 2M
    assert kin.two_body_momentum(M["pi+"], M["mu+"], 0) == pytest.approx((M["pi+"] ** 2 - M["mu+"] ** 2) / (2 * M["pi+"]))
    assert kin.two_body_momentum(10.0, 5.0, 5.0) == 0.0


def test_decays_that_are_refused() -> None:
    with pytest.raises(VidgenError, match="below threshold"):
        kin.two_body("pi0 -> mu+ mu-")
    with pytest.raises(VidgenError, match="below threshold"):
        kin.two_body_momentum(100, 60, 50)
    with pytest.raises(VidgenError, match="electron number not conserved"):
        kin.two_body("pi+ -> mu+ nu_e")
    with pytest.raises(VidgenError, match="one particle into two"):
        kin.two_body("mu- -> e- anti-nu_e nu_mu")
    with pytest.raises(VidgenError, match="off-shell"):
        kin.two_body("H -> Z Z*")


def test_opening_angle_shrinks_with_momentum() -> None:
    d = kin.two_body("pi0 -> gamma gamma")
    angles = [d.min_opening_angle(kin.Boost.from_momentum(p, M["pi0"])) for p in (200, 1000, 10000)]
    assert angles[0] > angles[1] > angles[2]
    for p, a in zip((200, 1000, 10000), angles):   # massless products: sin(θ_min / 2) = 1/γ
        g = kin.Boost.from_momentum(p, M["pi0"]).gamma
        assert a == pytest.approx(2 * math.degrees(math.asin(1 / g)), rel=1e-4)
    cols = kin._opening_model({"M": M["pi0"] / 1000, "p_min": 0.2, "p_max": 10, "samples": 12}, 1)
    assert list(cols) == ["p", "gamma", "theta_min", "theta_90"] and np.all(np.diff(cols["theta_min"]) < 0)
    with pytest.raises(VidgenError, match="needs M"):
        kin._opening_model({}, 1)


# ----- thresholds and decay lengths ----------------------------------------------------------------


def test_antiproton_threshold_fixed_target_and_collider() -> None:
    t = kin.threshold("p p -> p p p anti-p")
    mp = M["p"]
    assert t.sqrt_s == pytest.approx(4 * mp)
    assert t.fixed_target == pytest.approx(7 * mp) and t.fixed_target_kinetic == pytest.approx(6 * mp)
    assert t.fixed_target_kinetic == pytest.approx(5629.6, abs=0.1)   # 5.63 GeV
    assert t.collider == pytest.approx((2 * mp, 2 * mp)) and t.collider_kinetic == pytest.approx((mp, mp))
    assert t.ratio == pytest.approx(7 / 4)
    assert kin.fixed_target_energy(4 * mp, mp, mp) == pytest.approx(7 * mp)
    with pytest.raises(VidgenError, match="two particles"):
        kin.threshold("Z -> mu+ mu-")
    with pytest.raises(VidgenError, match="baryon number"):
        kin.threshold("p p -> p p anti-p")


def test_decay_lengths() -> None:
    mu = kin.decay_length("mu-", energy=4000)   # a 4 GeV cosmic-ray muon
    assert mu.motion.gamma == pytest.approx(37.86, rel=1e-3)
    assert mu.length == pytest.approx(24.93e3, rel=1e-3) and mu.c_tau == pytest.approx(658.6, rel=1e-3)
    assert mu.lab_lifetime == pytest.approx(37.86 * 2.1969811e-6, rel=1e-3)
    assert mu.survival(15e3) == pytest.approx(math.exp(-15e3 / mu.length))
    assert "24.93 km" in mu.text()
    b = kin.decay_length("B+", momentum=30000)   # millimetres
    assert 1e-3 < b.length < 1e-2
    pi_charged, pi_neutral = kin.decay_length("pi+", momentum=10000), kin.decay_length("pi0", momentum=10000)
    assert pi_charged.length == pytest.approx(559, rel=2e-3) and pi_neutral.length < 1e-5
    assert kin.length_text(pi_neutral.length).endswith("µm")
    with pytest.raises(VidgenError, match="stable"):
        kin.decay_length("p", momentum=1000)


def test_si_conversions() -> None:
    assert kin.to_si(1.0, "energy") == pytest.approx(1.602176634e-13)
    assert kin.to_si(1.0, "mass") == pytest.approx(1.602176634e-13 / 299792458**2)
    assert kin.to_si(1.0, "momentum") == pytest.approx(1.602176634e-13 / 299792458)
    assert kin.from_si(kin.to_si(938.27, "mass"), "mass") == pytest.approx(938.27)
    assert kin.si_text(29.79, "momentum") == "29.79 MeV/c = 1.592 × 10⁻²⁰ kg·m/s"
    assert kin.natural_value("10 GeV/c") == pytest.approx(10000) and kin.natural_value("4 GeV", "energy") == pytest.approx(4000)
    with pytest.raises(VidgenError, match="with its unit"):
        kin.natural_value("10", "momentum")
    with pytest.raises(VidgenError, match="not a unit of momentum"):
        kin.natural_value("10 GeV", "momentum")
    assert kin.value_text(999.9999999999, "momentum") == "1.000 GeV/c"


def test_pdg_values_for_calculations() -> None:
    assert (kin.pdg_value("pi+").number, kin.pdg_value("pi+").unit) == ("139.57039", "MeV/c^2")
    assert (kin.pdg_value("H").number, kin.pdg_value("H").unit) == ("125.20", "GeV/c^2")
    assert kin.pdg_value("mu-", "lifetime", "us").number == "2.1969811"
    assert kin.pdg_value("Z", "width").number == "2.4955" and kin.pdg_value("Z", "width").source == "PDG 2024"
    with pytest.raises(VidgenError, match="only bounded"):
        kin.pdg_value("nu_e")
    with pytest.raises(VidgenError, match="does not fit"):
        kin.pdg_value("pi+", "mass", "s")


def test_calculation_symbols_from_the_particle_table() -> None:
    from vidgen.scenes.calculation import Calculation

    params = {"symbols": [{"name": "m_mu", "mass": "mu-"}, {"name": "tau", "lifetime": "mu-"}, {"name": "E", "value": "4.00 GeV"},
                          {"name": "c", "constant": "c"}],
              "calculations": [{"name": "gamma", "expr": "E/(m_mu*c^2)"}, {"name": "L", "expr": "sqrt(gamma^2 - 1)*c*tau", "unit": "km"}]}
    worked = Calculation.parse_params(params, "t").worked(None)
    assert [r.value.value_text() for r in worked.results] == ["37.9", "24.9 km"]
    m = worked.value("m_mu")
    assert m.source == "PDG 2024" and "μ⁻ mass" in str(m.meaning)
    with pytest.raises(VidgenError, match="exactly one of value, constant, from_scene, mass"):
        Calculation.parse_params({"symbols": [{"name": "m", "mass": "pi+", "value": 1}], "calculations": [{"name": "x", "expr": "2*m"}]}, "t")
    with pytest.raises(VidgenError, match="did you mean"):
        Calculation.parse_params({"symbols": [{"name": "m", "mass": "pion"}], "calculations": [{"name": "x", "expr": "2*m"}]}, "t")


# ----- the scene ----------------------------------------------------------------------------------


def _params(**over: Any) -> Any:
    from vidgen.scenes.kinematics import Kinematics

    return Kinematics.parse_params({"decay": "pi+ -> mu+ nu_mu", "momentum": "200 MeV/c", **over}, "k")


def test_scene_params_are_checked() -> None:
    with pytest.raises(VidgenError, match="one of the two"):
        _params(particles=[{"particle": "gamma", "momentum": "1 GeV/c"}])
    with pytest.raises(VidgenError, match="shows the lab"):
        _params(momentum=None)
    with pytest.raises(VidgenError, match="below threshold"):
        _params(decay="pi0 -> mu+ mu-")
    with pytest.raises(VidgenError, match="superluminal"):
        _params(momentum=None, beta=1.5)
    with pytest.raises(VidgenError, match="give one of"):
        _params(gamma=2)
    with pytest.raises(VidgenError, match="no rest frame"):
        _params(decay=None, momentum=None, particles=[{"particle": "gamma", "momentum": "1 GeV/c"}, {"particle": "gamma", "momentum": "2 GeV/c"}])
    assert _params(momentum=None, frames="rest").frames == "rest"


def test_scene_values_for_calculations() -> None:
    from vidgen.scenes.kinematics import Kinematics

    values = Kinematics.calc_values(_params())
    p_star, unit = values["p_star"]
    assert unit == "MeV/c" and kin.from_si(p_star, "momentum") == pytest.approx(29.79, rel=1e-4)
    assert values["gamma"][0] == pytest.approx(math.hypot(200, M["pi+"]) / M["pi+"])
    assert values["decay_length"][0] == pytest.approx(200 / M["pi+"] * PARTICLES["pi+"].c_tau_m)
    system = Kinematics.calc_values(_params(decay=None, momentum=None, particles=[{"particle": "gamma", "momentum": "62.6 GeV/c"},
                                                                                {"particle": "gamma", "momentum": "62.6 GeV/c", "angle": 180}]))
    assert kin.from_si(system["m_inv"][0], "mass") == pytest.approx(125200) and system["m_inv"][1] == "GeV/c^2"
    assert system["opening_angle"] == (pytest.approx(math.pi), "deg")


def test_from_scene_and_boost_problems(make_project) -> None:
    def problems(*scenes: dict[str, Any]) -> list[str]:
        return [m.message for m in project_problems(Project.load(make_project(minimal_config(scenes=list(scenes), narration=NARRATION))))]

    pion = {"id": "pion", "type": "kinematics", "params": {"decay": "pi+ -> mu+ nu_mu", "frames": "rest", "momentum": "200 MeV/c"},
            "beats": [{"text": "boost it", "actions": [{"action": "boost", "to": "lab"}]}, {"text": "and back", "actions": [{"action": "boost", "to": 0}]}]}
    calc = {"id": "c", "type": "calculation", "params": {"symbols": [{"name": "p", "from_scene": "pion.p_star"}],
                                                         "calculations": [{"name": "q", "expr": "p", "unit": "kg m/s"}]}, "beats": [{"text": "p"}]}
    assert problems(pion, calc) == []
    bad = {**pion, "beats": [{"text": "x", "actions": [{"action": "boost", "to": 1.2}]}]}
    assert any("faster than light" in m for m in problems(bad))
    other = {"id": "b", "type": "bullets", "params": {"items": ["a"]}, "beats": [{"text": "go", "actions": [{"action": "boost"}]}]}
    assert any("boost is an action of kinematics scenes" in m for m in problems(other))
    rest_only = {**pion, "params": {"decay": "pi0 -> gamma gamma", "frames": "rest"}, "beats": [{"text": "x", "actions": [{"action": "boost", "to": "lab"}]}]}
    assert any("needs the decaying particle's momentum" in m for m in problems(rest_only))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(320, 180), (180, 320)], ids=["landscape", "portrait"])
def test_two_frames_render(size: tuple[int, int], make_project, media: Path) -> None:
    scene = {"id": "k", "type": "kinematics", "params": {"title": "Pion decay", "decay": "pi+ -> mu+ nu_mu", "momentum": "200 MeV/c", "si": True},
             "beats": [{"text": "at rest"}, {"text": "in the lab"}, {"text": "the same mass", "actions": [{"highlight": "values"}]}]}
    project = Project.load(make_project(minimal_config(scenes=[scene], narration=NARRATION)))
    s = render(project, "k", media, size)
    registered = sorted({n for t in s.targets for n in t.names})
    assert registered == sorted(type(s).target_names(s.params))
    assert all(s.is_shown(n) for n in ("panel:rest", "panel:lab", "arrow:mu+", "sum", "values"))
    rest, lab = s._panels
    # the rest frame's arrows are back to back and as long as each other; the lab's sum is the pion's momentum
    a, b = (np.array(arrow[0].get_end()) - rest.origin for arrow in rest.arrows)
    assert np.linalg.norm(a) == pytest.approx(np.linalg.norm(b), rel=1e-3) and float(a @ b) < 0
    assert np.linalg.norm(lab.sum_arrow[0].get_end() - lab.origin) / lab.scale == pytest.approx(200, rel=1e-2)
    assert lab.region.x0 >= rest.region.x1 if size[0] > size[1] else lab.region.y1 <= rest.region.y0


@pytest.mark.render
def test_boost_moves_the_frame(make_project, media: Path) -> None:
    scene = {"id": "b", "type": "kinematics", "params": {"decay": "pi0 -> gamma gamma", "frames": "rest", "momentum": "1 GeV/c", "angle": 90},
             "beats": [{"text": "at rest"}, {"text": "speed it up", "actions": [{"action": "boost", "to": "lab"}]}]}
    project = Project.load(make_project(minimal_config(scenes=[scene], narration=NARRATION)))
    s = render(project, "b", media, (320, 180))
    panel = s._panels[0]
    assert panel.eta == pytest.approx(s._pic.eta_lab)
    # the two photons now point forward and close up: 15.4° apart at 1 GeV/c
    ends = [np.array(arrow[0].get_end()) - panel.origin for arrow in panel.arrows]
    angle = math.degrees(math.acos(float(ends[0] @ ends[1]) / (np.linalg.norm(ends[0]) * np.linalg.norm(ends[1]))))
    assert angle == pytest.approx(15.4, abs=0.2)
    # nothing left over from the rest frame: every drawn glyph of the readout is visible text of the new one
    assert all(m.get_fill_opacity() > 0 for m in panel.readout.submobjects)


def test_gluons_are_coils() -> None:
    """Step 238's review: a gluon line loops back on itself (a coil), unlike a photon's wave."""
    from vidgen.scenes import feynman_draw as fd

    path = fd.straight_or_arc(np.array([0.0, 0.0, 0.0]), np.array([3.0, 0.0, 0.0]))
    gluon = fd.path_mobject(path, "gluon", "#ffffff")
    photon = fd.path_mobject(path, "photon", "#ffffff")
    gx = gluon.points[:, 0]
    assert np.sum(np.diff(gx) < -1e-3) > 10   # it runs backwards in each loop
    assert np.all(np.diff(photon.points[:, 0]) > -1e-6)
    assert np.ptp(gluon.points[:, 1]) > np.ptp(photon.points[:, 1])
