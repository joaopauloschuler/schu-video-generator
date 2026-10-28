"""Step 244, the review of Phase Y: independent hand computations of the physics (PDG 2024 values,
two-body momenta, thresholds, decay lengths, track curvature, significances) and the reactions the
review tried against the checker and the vertex rules. No manim."""

from __future__ import annotations

import math

import numpy as np
import pytest

from vidgen.particle_physics import branching as br
from vidgen.particle_physics import detector as det
from vidgen.particle_physics import kinematics as kin
from vidgen.particle_physics import spectrum as sp
from vidgen.particle_physics.conservation import check
from vidgen.particle_physics.data import HBAR_MEV_S, PARTICLES
from vidgen.particle_physics.feynman import vertex_rule
from vidgen.particle_physics.names import particle
from vidgen.particle_physics.process import parse_process

# ----- PDG 2024 values (the reviewer's independent reading) ------------------------------------------

PDG_2024 = {   # key: (mass MeV, mean life s or width MeV, which)
    "e-": (0.51099895, None, ""), "mu-": (105.6583755, 2.1969811e-6, "tau"), "tau-": (1776.93, 290.3e-15, "tau"),
    "W+": (80369.2, 2085.0, "width"), "Z": (91188.0, 2495.5, "width"), "H": (125200.0, None, ""),
    "t": (172570.0, 1420.0, "width"), "b": (4183.0, None, ""), "c": (1273.0, None, ""), "s": (93.5, None, ""),
    "d": (4.70, None, ""), "u": (2.16, None, ""),
    "pi+": (139.57039, 2.6033e-8, "tau"), "pi0": (134.9768, 8.43e-17, "tau"), "K+": (493.677, 1.2380e-8, "tau"),
    "K0_S": (497.611, 0.8954e-10, "tau"), "K0_L": (497.611, 5.116e-8, "tau"), "eta": (547.862, 1.31e-3, "width"),
    "phi": (1019.461, 4.249, "width"), "J/psi": (3096.900, 0.0926, "width"), "Upsilon(1S)": (9460.40, 0.05402, "width"),
    "D+": (1869.66, 1.033e-12, "tau"), "D0": (1864.84, 410.3e-15, "tau"), "B+": (5279.41, 1.638e-12, "tau"),
    "B0": (5279.72, 1.517e-12, "tau"), "p": (938.27209, None, ""), "n": (939.56542, 878.4, "tau"),
    "Lambda": (1115.683, 2.617e-10, "tau"), "Sigma+": (1189.37, 0.8018e-10, "tau"), "Sigma0": (1192.642, 7.4e-20, "tau"),
    "Sigma-": (1197.449, 1.479e-10, "tau"), "Xi0": (1314.86, 2.90e-10, "tau"), "Xi-": (1321.71, 1.639e-10, "tau"),
    "Omega-": (1672.45, 0.821e-10, "tau"),
}


@pytest.mark.parametrize("key", sorted(PDG_2024))
def test_pdg_2024_values(key: str) -> None:
    mass, value, which = PDG_2024[key]
    p = PARTICLES[key]
    assert p.mass_mev == pytest.approx(mass, rel=1e-9)
    if which == "tau":
        assert p.lifetime == pytest.approx(value, rel=1e-9)
    elif which == "width":
        assert p.width == pytest.approx(value, rel=1e-9)


def test_quantum_numbers() -> None:
    spins = {"e-": 0.5, "gamma": 1, "g": 1, "W+": 1, "Z": 1, "H": 0, "pi+": 0, "K+": 0, "phi": 1, "J/psi": 1,
             "p": 0.5, "Lambda": 0.5, "Omega-": 1.5, "Delta++": 1.5}
    for key, spin in spins.items():
        assert float(PARTICLES[key].spin) == spin, key
    assert (PARTICLES["pi0"].c_parity, PARTICLES["pi0"].g_parity) == (1, -1)
    assert (PARTICLES["eta"].c_parity, PARTICLES["eta"].g_parity) == (1, 1)
    assert PARTICLES["J/psi"].c_parity == -1 and PARTICLES["gamma"].c_parity == -1 and PARTICLES["H"].parity == 1
    assert PARTICLES["B+"].flavour == (0, 0, 1, 0)        # u b̄: B′ = +1 (b has −1)
    assert PARTICLES["K+"].flavour == (1, 0, 0, 0)        # u s̄: S = +1
    assert PARTICLES["Omega-"].flavour == (-3, 0, 0, 0)
    assert PARTICLES["Delta++"].charge == 2 and PARTICLES["Xi-"].charge == -1


def test_branching_tables_against_pdg() -> None:
    z = br.branching("Z")
    assert z.mode("hadrons").fraction == pytest.approx(0.69911) and z.mode("invisible").fraction == pytest.approx(0.2000)
    assert z.total == pytest.approx(1.0, abs=2e-4)
    w = br.branching("W+")
    assert w.mode("hadrons").fraction == pytest.approx(0.6741) and w.total == pytest.approx(1.0, abs=2e-4)
    k = br.branching("K+")
    assert k.total == pytest.approx(1.0, abs=5e-4) and k.mode("μ⁺ν_μ").fraction == pytest.approx(0.6356)
    h = br.branching("H")
    assert h.kind == "theory" and all(m.check for m in h.modes)    # YR4 values stay marked for the owner
    assert not any(m.check for m in z.modes + w.modes + k.modes)    # confirmed in review
    # the invisible mode is all three νν̄ pairs: one pair is not 20 %
    assert br.mode_fraction(parse_process("Z -> nu_e anti-nu_e")) is None
    assert br.mode_fraction(parse_process("Z -> mu- mu+")) == pytest.approx(0.033662)


def test_width_and_lifetime_are_hbar_apart() -> None:
    assert HBAR_MEV_S == pytest.approx(6.582119569e-22, rel=1e-9)
    assert PARTICLES["Z"].lifetime == pytest.approx(6.582119569e-22 / 2495.5, rel=1e-9)
    assert PARTICLES["mu-"].c_tau_m == pytest.approx(658.638, rel=1e-5)


# ----- conservation: the reactions the review tried --------------------------------------------------

ALLOWED = {
    "n -> p e- anti-nu_e": "weak", "pi0 -> gamma gamma": "electromagnetic", "K0_S -> pi+ pi-": "weak",
    "Lambda -> p pi-": "weak", "nu_e n -> p e-": "weak", "e+ e- -> gamma gamma": "electromagnetic", "e+ e- -> Z": "weak",
    "e+ e- -> gamma*": "electromagnetic", "g g -> H": "higgs", "K- p -> Omega- K+ K0": "strong", "pi- p -> K+ Sigma-": "strong",
    "Omega- -> Lambda K-": "weak", "Sigma0 -> Lambda gamma": "electromagnetic",
}
FORBIDDEN = {
    "p -> e+ pi0": "baryon number", "mu- -> e- gamma": "electron number", "mu- -> e- e+ e-": "muon number",
    "e+ e- -> gamma": "real massless γ", "p anti-p -> gamma": "real massless γ", "Z -> gamma gamma": "Landau–Yang",
    "pi0 -> gamma gamma gamma": "C-parity", "gamma -> e+ e-": "energy", "n -> p e-": "angular momentum",
    "e+ e- -> pi+": "charge", "p anti-p -> pi0": "merge into one only",
}


@pytest.mark.parametrize("process", sorted(ALLOWED))
def test_allowed(process: str) -> None:
    v = check(process)
    assert v.allowed and v.interaction == ALLOWED[process], v.explain()


@pytest.mark.parametrize("process", sorted(FORBIDDEN))
def test_forbidden(process: str) -> None:
    v = check(process)
    assert not v.allowed and FORBIDDEN[process] in v.summary(), v.explain()


# ----- vertex rules ------------------------------------------------------------------------------------

VERTICES = [
    (["e-"], ["e-", "gamma"], True), (["e-"], ["mu-", "gamma"], False), (["u"], ["c", "Z"], False), (["e-"], ["mu-", "Z"], False),
    (["e-"], ["e-", "g"], False), (["u"], ["u", "g"], True), (["g"], ["g", "g"], True), (["g"], ["gamma", "gamma"], False),
    (["e-"], ["nu_e", "W-"], True), (["e-"], ["nu_mu", "W-"], False), (["s"], ["u", "W-"], True), (["b"], ["c", "W-"], True),
    (["d"], ["s", "W-"], False), (["u"], ["e+", "W-"], False),
    (["nu_e"], ["nu_e", "H"], False), (["e-"], ["e-", "H"], True), (["t"], ["t", "H"], True), (["nu_e"], ["nu_e", "Z"], True),
    (["nu_e"], ["nu_e", "gamma"], False), (["Z"], ["Z", "gamma"], False), (["Z"], ["gamma", "gamma"], False),
    (["Z"], ["Z", "Z"], False), (["H"], ["gamma", "gamma"], False), (["H"], ["g", "g"], False), (["H"], ["Z", "gamma"], False),
    (["H"], ["Z", "Z"], True), (["H"], ["W+", "W-"], True), (["W+"], ["W+", "gamma"], True), (["W+"], ["W+", "Z"], True),
]


@pytest.mark.parametrize("into, out, ok", VERTICES)
def test_vertex_rules(into: list[str], out: list[str], ok: bool) -> None:
    rule, why = vertex_rule([particle(x) for x in into], [particle(x) for x in out])
    assert (rule is not None) == ok, why


# ----- kinematics, by hand -----------------------------------------------------------------------------


def test_two_body_momenta_by_hand() -> None:
    m_pi, m_mu = 139.57039, 105.6583755
    assert kin.two_body("pi+ -> mu+ nu_mu").p_star == pytest.approx((m_pi**2 - m_mu**2) / (2 * m_pi), rel=1e-12)   # 29.79 MeV/c
    assert kin.two_body("pi+ -> mu+ nu_mu").p_star == pytest.approx(29.79, abs=0.01)
    assert kin.two_body("pi0 -> gamma gamma").p_star == pytest.approx(134.9768 / 2)
    m_l, m_p = 1115.683, 938.27209
    hand = math.sqrt((m_l**2 - (m_p + m_pi) ** 2) * (m_l**2 - (m_p - m_pi) ** 2)) / (2 * m_l)
    assert kin.two_body("Lambda -> p pi-").p_star == pytest.approx(hand, rel=1e-12) and hand == pytest.approx(100.6, abs=0.05)
    m_z, m_e = 91188.0, 0.51099895
    assert kin.two_body("Z -> e- e+").p_star == pytest.approx(math.sqrt(m_z**2 / 4 - m_e**2), rel=1e-12)


def test_thresholds_by_hand() -> None:
    m_p = 938.27209
    t = kin.threshold("p p -> p p p anti-p")
    assert t.sqrt_s == pytest.approx(4 * m_p) and t.fixed_target == pytest.approx(7 * m_p)
    assert t.fixed_target_kinetic == pytest.approx(6 * m_p)   # 5.63 GeV: the Bevatron's design energy
    assert t.collider == pytest.approx((2 * m_p, 2 * m_p))
    m_pi, m_k0, m_lam = 139.57039, 497.611, 1115.683
    assert kin.threshold("pi- p -> K0 Lambda").fixed_target == pytest.approx(((m_k0 + m_lam) ** 2 - m_pi**2 - m_p**2) / (2 * m_p))


def test_decay_lengths_by_hand() -> None:
    c = 299_792_458.0
    # a muon of 4 GeV/c: βγ = p/m
    mu = kin.decay_length("mu-", momentum=4000.0)
    assert mu.length == pytest.approx(4000.0 / 105.6583755 * 2.1969811e-6 * c, rel=1e-9)
    assert mu.length == pytest.approx(24.93e3, rel=1e-3)
    # a B⁰ with βγ = 1: cτ = 455 µm
    b = kin.decay_length("B0", gamma=math.sqrt(2.0))
    assert b.length == pytest.approx(1.517e-12 * c, rel=1e-9) and b.length == pytest.approx(454.8e-6, rel=1e-3)
    pi = kin.decay_length("pi+", energy=139.57039 * 10)   # γ = 10: βγ = √99
    assert pi.lab_lifetime == pytest.approx(10 * 2.6033e-8) and pi.length == pytest.approx(math.sqrt(99) * 2.6033e-8 * c)


def test_invariant_mass_of_two_photons_by_hand() -> None:
    a = kin.FourVector.from_mass(0.0, 62600.0, 0.0)
    b = kin.FourVector.from_mass(0.0, 62600.0, 180.0)
    assert kin.invariant_mass([a, b]) == pytest.approx(125200.0)
    e1, e2, angle = 70000.0, 60000.0, 120.0   # m² = 2 E₁E₂ (1 − cos θ)
    v1, v2 = kin.FourVector.from_mass(0.0, e1, 0.0), kin.FourVector.from_mass(0.0, e2, angle)
    assert kin.invariant_mass([v1, v2]) == pytest.approx(math.sqrt(2 * e1 * e2 * (1 - math.cos(math.radians(angle)))))


# ----- detector -----------------------------------------------------------------------------------------


def test_bending_radius_and_sign() -> None:
    assert det.bending_radius(1.0, 2.0) == pytest.approx(1.0 / (0.299792458 * 2.0))   # p_T = 0.3 B R: 1.668 m
    assert det.bending_radius(0.6, 4.0) == pytest.approx(0.5, rel=1e-3)
    d = det.Detector(field=2.0)
    for key, sign in (("mu+", -1), ("mu-", +1)):
        path = det.trajectory(det.EventParticle(particle(key), 2.0, 0.0, 0.0), d).points
        # starting along +x in B along +z: F = q v × B = q B (x̂ × ẑ) = −q B ŷ — a μ⁺ bends to −y (clockwise seen from +z)
        inside = path[np.hypot(path[:, 0], path[:, 1]) < 1.0]
        assert np.sign(inside[-1, 1]) == sign, key
        # the sagitta matches the radius from p_T = 0.3 B R: y at x is R − √(R² − x²)
        r = det.bending_radius(2.0, 2.0)
        x, y = inside[-1, 0], abs(inside[-1, 1])
        assert y == pytest.approx(r - math.sqrt(r * r - x * x), rel=0.02)


# ----- significance -------------------------------------------------------------------------------------


def test_significance_formulas_by_hand() -> None:
    s, b = 30.0, 100.0
    assert sp.asimov(s, b) == pytest.approx(math.sqrt(2 * ((s + b) * math.log(1 + s / b) - s)))
    assert sp.asimov(1.0, 1e4) == pytest.approx(1.0 / math.sqrt(1e4), rel=1e-3)     # s ≪ b: s/√b
    assert sp.counting_significance(130.0, 100.0) == pytest.approx(sp.asimov(30.0, 100.0))
    assert sp.p_value(5.0) == pytest.approx(2.8665e-7, rel=1e-4)                    # five sigma, one-sided
    assert sp.p_value(3.0) == pytest.approx(1.3499e-3, rel=1e-4)
    assert sp.p_value(0.0) == pytest.approx(0.5)


def test_z_peak_cross_section() -> None:
    peak = float(sp.z_cross_section([91.188])[0])
    assert peak == pytest.approx(41.5, abs=0.2)       # σ⁰_had ≈ 41.48 nb (PDG), no radiative corrections
    assert float(sp.z_cross_section([91.188], 2)[0]) > peak > float(sp.z_cross_section([91.188], 4)[0])

