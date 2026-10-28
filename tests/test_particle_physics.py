"""The particle-physics model (Phase Y, Step 237; DESIGN §99): PDG 2024 data and its sanity
(charges and baryon numbers from the quark content, antiparticles), names in ASCII and Unicode,
reaction parsing, and the conservation checker on textbook allowed and forbidden processes. No
manim."""

from __future__ import annotations

import math
import re
import subprocess
import sys
import unicodedata
from fractions import Fraction

import pytest

from vidgen import particle_physics as pp
from vidgen.errors import VidgenError

F = Fraction


# ----- data ------------------------------------------------------------------------------------------


def test_the_table_is_consistent() -> None:
    assert pp.particle_problems() == []
    assert pp.EDITION == "PDG 2024" and "Phys. Rev. D 110, 030001 (2024)" in pp.SOURCE
    for p in pp.PARTICLES.values():
        assert p.mass_mev >= 0 and p.family in ("quark", "lepton", "gauge boson", "scalar boson", "meson", "baryon")
        anti = pp.PARTICLES[p.antiparticle]
        assert anti.antiparticle == p.key and anti.mass_mev == p.mass_mev and anti.spin == p.spin
        assert anti.charge == -p.charge and anti.baryon == -p.baryon and anti.lepton == tuple(-x for x in p.lepton)
        if p.self_conjugate:
            assert p.charge == 0 and p.baryon == 0 and p.lepton_number == 0
        if p.is_hadron:   # charge and baryon number from the quarks (π⁰, K⁰_S: every component)
            for content in p.components:
                assert pp.content_charge(content) == p.charge and pp.content_baryon(content) == p.baryon, p.key
            assert p.baryon in (0, 1, -1) and p.lepton == (0, 0, 0)
            assert (p.family == "baryon") == (p.baryon != 0)
        if p.lifetime is not None and p.width is not None:   # Γ τ = ħ
            assert p.lifetime * p.width == pytest.approx(pp.HBAR_MEV_S)


def test_the_standard_model_particles() -> None:
    sm = {k for k in pp.ELEMENTARY if not k.startswith("anti-")}
    assert sm == {"u", "d", "s", "c", "b", "t", "e-", "e+", "mu-", "mu+", "tau-", "tau+", "nu_e", "nu_mu", "nu_tau",
                  "gamma", "g", "W+", "W-", "Z", "H"}
    quarks = [pp.PARTICLES[k] for k in "udscbt"]
    assert [q.charge for q in quarks] == [F(2, 3), F(-1, 3), F(-1, 3), F(2, 3), F(-1, 3), F(2, 3)]
    assert all(q.baryon == F(1, 3) and q.spin == F(1, 2) and q.colour == "3" for q in quarks)
    assert pp.PARTICLES["anti-u"].colour == "3̄" and pp.PARTICLES["g"].colour == "8"
    # flavour signs follow the charge: S(s) = −1, C(c) = +1, B′(b) = −1, T(t) = +1
    assert [pp.PARTICLES[k].flavour for k in "scbt"] == [(-1, 0, 0, 0), (0, 1, 0, 0), (0, 0, -1, 0), (0, 0, 0, 1)]
    assert pp.PARTICLES["e-"].lepton == (1, 0, 0) and pp.PARTICLES["anti-nu_mu"].lepton == (0, -1, 0)
    assert pp.PARTICLES["nu_tau"].charge == 0 and pp.PARTICLES["tau+"].lepton_number == -1
    assert [pp.PARTICLES[k].spin for k in ("gamma", "g", "Z", "W+", "H")] == [1, 1, 1, 1, 0]
    # masses (PDG 2024, rounded as the module keeps them) and the stated schemes
    m = {k: pp.PARTICLES[k].mass_mev for k in ("e-", "mu-", "tau-", "W+", "Z", "H", "t", "p", "n", "pi+", "pi0", "K+")}
    assert m["e-"] == pytest.approx(0.51099895) and m["mu-"] == pytest.approx(105.6583755)
    assert m["tau-"] == pytest.approx(1776.9, abs=0.2) and m["W+"] / 1000 == pytest.approx(80.37, abs=0.02)
    assert m["Z"] / 1000 == pytest.approx(91.188, abs=0.001) and m["H"] / 1000 == pytest.approx(125.2, abs=0.1)
    assert m["t"] / 1000 == pytest.approx(172.6, abs=0.2) and m["n"] - m["p"] == pytest.approx(1.29333, abs=1e-4)
    assert m["pi+"] == pytest.approx(139.57039) and m["pi0"] == pytest.approx(134.9768) and m["K+"] == pytest.approx(493.677)
    assert "2 GeV" in pp.PARTICLES["u"].mass_scheme and "direct" in pp.PARTICLES["t"].mass_scheme
    assert pp.PARTICLES["nu_e"].mass_limit_mev == pytest.approx(0.8e-6) and pp.PARTICLES["nu_e"].mass_text() == "< 0.8 eV"


def test_lifetimes_widths_and_text() -> None:
    mu, n, z, jpsi = (pp.PARTICLES[k] for k in ("mu-", "n", "Z", "J/psi"))
    assert mu.lifetime_text() == "2.197 µs" and n.lifetime_text() == "878.4 s" and pp.PARTICLES["p"].lifetime_text() == "stable"
    assert mu.c_tau_m == pytest.approx(658.6, rel=1e-3)   # cτ of the muon: 659 m
    assert z.width_text() == "2.496 GeV" and jpsi.width_text() == "92.60 keV"
    assert z.lifetime == pytest.approx(2.64e-25, rel=1e-2)
    assert pp.PARTICLES["pi0"].width == pytest.approx(7.8e-6, rel=0.02)   # Γ(π⁰) ≈ 7.8 eV
    assert pp.PARTICLES["t"].mass_text() == "172.57 GeV" and pp.PARTICLES["c"].mass_text() == "1.273 GeV"
    assert pp.PARTICLES["Delta++"].charge_text(sign=True) == "+2" and pp.PARTICLES["d"].charge_text() == "−1/3"
    assert pp.energy_text(0.7823) == "782.3 keV" and pp.time_text(8.43e-17) == "8.43 × 10⁻¹⁷ s"
    # PDG 2024: τ(Λ) = (2.617 ± 0.010) × 10⁻¹⁰ s (Step 238's review; 2.632 before), the same for Λ̄
    assert pp.PARTICLES["Lambda"].lifetime_text() == "261.7 ps" and pp.PARTICLES["anti-Lambda"].lifetime == 2.617e-10
    assert (pp.PARTICLES["W+"].mass_mev, pp.PARTICLES["Z"].mass_mev, pp.PARTICLES["Z"].width_mev, pp.PARTICLES["H"].mass_mev) == (80369.2, 91188.0, 2495.5, 125200.0)


def test_hadrons_from_their_quarks() -> None:
    expect = {"p": "uud", "n": "udd", "pi+": "ud̄", "K+": "us̄", "K0": "ds̄", "D0": "cū", "B+": "ub̄", "Lambda": "uds", "Omega-": "sss",
              "Delta++": "uuu", "anti-p": "ūūd̄", "J/psi": "cc̄", "Upsilon(1S)": "bb̄"}
    for key, content in expect.items():
        assert unicodedata.normalize("NFC", pp.PARTICLES[key].content) == unicodedata.normalize("NFC", content), key
    assert pp.PARTICLES["K+"].flavour[0] == 1 and pp.PARTICLES["Lambda"].flavour[0] == -1 and pp.PARTICLES["Xi-"].flavour[0] == -2
    assert pp.PARTICLES["D+"].flavour[1] == 1 and pp.PARTICLES["B+"].flavour[2] == 1 and pp.PARTICLES["B0"].flavour[2] == 1
    assert pp.PARTICLES["K0_S"].flavour[0] is None and set(pp.PARTICLES["K0_S"].flavour_options()) == {(1, 0, 0, 0), (-1, 0, 0, 0)}
    assert pp.PARTICLES["anti-Sigma-"].charge == -1 and pp.PARTICLES["anti-Sigma-"].antiparticle == "Sigma+"
    assert pp.PARTICLES["Omega-"].spin == F(3, 2) and pp.PARTICLES["p"].parity == 1 and pp.PARTICLES["anti-p"].parity == -1
    assert pp.PARTICLES["pi0"].c_parity == 1 and pp.PARTICLES["eta"].g_parity == 1 and pp.PARTICLES["J/psi"].c_parity == -1


# ----- names and parsing -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "key"),
    [("e-", "e-"), ("electron", "e-"), ("positron", "e+"), ("e⁺", "e+"), ("μ⁻", "mu-"), ("muon", "mu-"), ("antimuon", "mu+"),
     ("ν̄ₑ", "anti-nu_e"), ("anti-nu_e", "anti-nu_e"), ("nubar_e", "anti-nu_e"), ("ν_μ", "nu_mu"), ("ν̄_τ", "anti-nu_tau"),
     ("π⁰", "pi0"), ("pi+", "pi+"), ("K⁰_S", "K0_S"), ("KS", "K0_S"), ("K_L", "K0_L"), ("K̄⁰", "anti-K0"), ("p̄", "anti-p"),
     ("pbar", "anti-p"), ("antiproton", "anti-p"), ("Σ̄⁻", "anti-Sigma-"), ("Σ⁺", "Sigma+"), ("Δ⁺⁺", "Delta++"), ("Ω⁻", "Omega-"),
     ("Λ", "Lambda"), ("J/ψ", "J/psi"), ("Υ(1S)", "Upsilon(1S)"), ("γ", "gamma"), ("photon", "gamma"), ("Z⁰", "Z"), ("W⁻", "W-"),
     ("higgs", "H"), ("ū", "anti-u"), ("ubar", "anti-u"), ("b", "b"), ("B+", "B+"), ("anti-B0", "anti-B0"), ("D0bar", "anti-D0")],
)
def test_particle_names(text: str, key: str) -> None:
    assert pp.particle(text).key == key


def test_unknown_names_say_what_was_meant() -> None:
    with pytest.raises(VidgenError, match="unknown particle 'muon-'; did you mean 'mu-'"):
        pp.particle("muon-")
    with pytest.raises(VidgenError, match="did you mean 'nu_mu'"):
        pp.parse_process("pi+ -> mu+ nu_m")


def test_process_parsing() -> None:
    proc = pp.parse_process("n -> p e- anti-nu_e")
    assert proc.is_decay and [leg.particle.key for leg in proc.final] == ["p", "e-", "anti-nu_e"]
    assert proc.text() == "n → p e⁻ ν̄ₑ" and proc.text("ascii") == "n -> p e- anti-nu_e" and r"\to" in proc.text("tex")
    assert pp.parse_process("μ⁻ → e⁻ ν̄ₑ ν_μ").text("ascii") == "mu- -> e- anti-nu_e nu_mu"
    assert pp.parse_process("e+e- => mu+ + mu-").text("ascii") == "e+ e- -> mu+ mu-"   # a run, '=>', '+' between
    off = pp.parse_process("H -> Z Z*")
    assert [leg.off_shell for leg in off.final] == [False, True] and off.text() == "H → Z Z*"
    with pytest.raises(VidgenError, match="found no arrow"):
        pp.parse_process("n p e-")
    with pytest.raises(VidgenError, match="2 arrows"):
        pp.parse_process("a -> b -> c")
    with pytest.raises(VidgenError, match="excited hadrons"):
        pp.parse_process("K* -> K+ pi-")
    with pytest.raises(VidgenError, match="nothing after"):
        pp.parse_process("n ->")


# ----- the conservation checker ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("process", "interaction"),
    [
        ("n -> p e- anti-nu_e", "weak"),
        ("mu- -> e- anti-nu_e nu_mu", "weak"),
        ("pi+ -> mu+ nu_mu", "weak"),
        ("pi0 -> gamma gamma", "electromagnetic"),
        ("Sigma0 -> Lambda gamma", "electromagnetic"),
        ("J/psi -> mu+ mu-", "electromagnetic"),
        ("e+ e- -> mu+ mu-", "electromagnetic"),
        ("Delta++ -> p pi+", "strong"),
        ("p anti-p -> pi+ pi- pi0", "strong"),
        ("pi- p -> K0 Lambda", "strong"),          # associated production: S = 0 → +1 − 1
        ("pi- p -> K0_S Lambda", "strong"),        # K⁰_S read as K⁰
        ("K+ -> pi+ pi0", "weak"),                 # ΔS = 1
        ("Lambda -> p pi-", "weak"),
        ("Omega- -> Xi0 pi-", "weak"),
        ("D0 -> K- pi+", "weak"),                  # c → s
        ("B0 -> J/psi K0_S", "weak"),
        ("K0_S -> pi+ pi-", "weak"),
        ("t -> W+ b", "weak"),
        ("Z -> e+ e-", "weak"),
        ("nu_mu e- -> nu_mu e-", "weak"),
        ("d -> u e- anti-nu_e", "weak"),
        ("eta -> pi+ pi- pi0", "electromagnetic"),  # not strong: G-parity
        ("H -> b anti-b", "higgs"),
        ("H -> Z Z*", "higgs"),
        ("g g -> H", "higgs"),
        ("p p -> p p p anti-p", "strong"),
    ],
)
def test_allowed_processes_and_their_interaction(process: str, interaction: str) -> None:
    v = pp.check(process)
    assert v.allowed, v.explain()
    assert v.interaction == interaction, v.explain()


@pytest.mark.parametrize(
    ("process", "reason"),
    [
        ("p -> e+ pi0", r"baryon number not conserved: B = \+1 → 0"),
        ("mu- -> e- gamma", r"electron number not conserved: L_e = 0 → \+1; muon number not conserved: L_μ = \+1 → 0"),
        ("n -> p e-", "electron number not conserved"),
        ("n -> p e- nu_e", r"L_e = 0 → \+2"),                      # an antineutrino it must be
        ("pi+ -> mu+ nu_e", "muon number not conserved"),
        ("mu- -> e- nu_e anti-nu_mu", "electron number"),
        ("e- -> nu_e gamma", "charge not conserved"),
        ("n -> p pi0", "charge not conserved"),
        ("pi0 -> gamma gamma gamma", "C-parity not conserved"),
        ("Z -> gamma gamma", "Landau–Yang"),
        ("J/psi -> gamma gamma", "Landau–Yang"),
        ("H -> Z Z", "energy: m\\(H\\) = 125.2 GeV is not more than the products' 182.4 GeV"),
        ("gamma -> e+ e-", "is not more than"),
        ("p -> n e+ nu_e", "is not more than"),                  # free proton: no β⁺ decay
        ("pi0 -> mu+ mu- mu+ mu-", "is not more than"),
        ("Xi- -> n pi-", "strangeness changes by 2"),
        ("Lambda -> p", "charge not conserved"),
    ],
)
def test_forbidden_processes_say_why(process: str, reason: str) -> None:
    v = pp.check(process)
    assert not v.allowed and v.interaction is None
    assert re.search(reason, v.summary()), v.summary()


def test_explanations_are_teaching_text() -> None:
    v = pp.check("n -> p e- anti-nu_e")
    assert v.summary() == "allowed: weak interaction"
    text = v.explain()
    assert "✓ Q: n 0 → p +1, e⁻ −1, ν̄ₑ 0 (total 0)" in text and "✓ L_e: n 0 → p 0, e⁻ +1, ν̄ₑ −1 (total 0)" in text
    assert "m(n) = 939.6 MeV > 938.3 MeV + 0.5110 MeV + 0 = 938.8 MeV" in text and "Q = 782.3 keV" in text
    assert v.check_of("L_e").text() == "electron number L_e: 0 → 0"
    k = pp.check("K+ -> pi+ pi0").explain()
    assert "Δ S: K⁺ +1 → π⁺ 0, π⁰ 0 (total 0)" in k and "ΔS = −1" in k   # a flavour the weak interaction changes
    bad = pp.check("p -> e+ pi0").explain()
    assert "✗ B: p +1 → e⁺ 0, π⁰ 0 (total 0)" in bad
    assert "lepton family numbers are conserved" in pp.check("mu- -> e- gamma").explain()
    assert "with one Z off-shell (write Z*)" in pp.check("H -> Z Z").explain()
    assert "K⁰_S has no definite strangeness" in pp.check("K0_S -> pi+ pi-").explain()
    assert "loop of heavy particles" in pp.check("H -> gamma gamma").explain()
    assert "quark-level process" in pp.check("t -> W+ b").explain()
    assert "slow" in pp.check("eta -> pi0 pi0 pi0").explain()
    assert set(pp.INTERACTIONS) == {"strong", "electromagnetic", "weak", "higgs"} and len(pp.CONSERVATION_TABLE) == 8


def test_thresholds_are_computed() -> None:
    mp = pp.PARTICLES["p"].mass_mev
    t = pp.check("p p -> p p p anti-p").threshold   # the antiproton threshold: kinetic 6 m_p on a fixed target
    assert t.sqrt_s_mev == pytest.approx(4 * mp) and t.beam_mev == pytest.approx(7 * mp) and t.beam_kinetic_mev == pytest.approx(6 * mp)
    assert t.q_mev == pytest.approx(-2 * mp)
    n = pp.check("n -> p e- anti-nu_e").threshold
    assert n.q_mev == pytest.approx(0.78233, abs=1e-4)   # the neutron's Q value, 0.782 MeV
    pi = pp.check("pi+ -> mu+ nu_mu").threshold
    assert pi.q_mev == pytest.approx(139.57039 - 105.6583755)
    z = pp.check("e+ e- -> Z").threshold
    assert z.sqrt_s_mev == pytest.approx(91188.0) and z.beam_mev == pytest.approx((91188.0**2 - 2 * 0.51099895**2) / (2 * 0.51099895))
    assert pp.check("pi- p -> K0 Lambda").threshold.beam_mev == pytest.approx(
        ((497.611 + 1115.683) ** 2 - 139.57039**2 - mp**2) / (2 * mp))
    assert math.isclose(pp.check("H -> Z Z*").threshold.final_mev, 91188.0)   # the off-shell Z does not count


def test_the_chart_data() -> None:
    assert len(pp.CELLS) == 17 and [c.target for c in pp.CELLS[:3]] == ["u", "c", "t"]
    assert pp.cell("electron").key == "e-" and pp.cell("photon").key == "gamma" and pp.cell("W").charge_text() == "±1"
    assert pp.cell("u").charge_text(anti=True) == "−2/3" and pp.cell("e").label == ("electron", "positron")
    assert pp.cell("t").mass_text() == "172.6 GeV" and pp.cell("nu_e").mass_text() == "< 0.8 eV" and pp.cell("H").mass_text() == "125.2 GeV"
    # every grid position is used once in each arrangement
    for arrangement, (cols, rows) in pp.GRID.items():
        spots = [getattr(c, arrangement) for c in pp.CELLS]
        assert len(set(spots)) == len(spots) and all(0 <= x < cols and 0 <= y < rows for x, y in spots)
    # couplings: the photon skips the neutrinos, the gluon the leptons, W and Z reach every fermion
    assert "nu_e" not in pp.COUPLINGS["photon"].fermions and "e" in pp.COUPLINGS["photon"].fermions
    assert set(pp.COUPLINGS["g"].fermions) == {"u", "c", "t", "d", "s", "b"} and pp.COUPLINGS["g"].bosons == ("g",)
    assert len(pp.COUPLINGS["W"].fermions) == len(pp.COUPLINGS["Z"].fermions) == 12
    assert "nu_tau" not in pp.COUPLINGS["H"].fermions and "H" in pp.COUPLINGS["H"].bosons
    # the chart's charges agree with the checker's particles
    for c in pp.CELLS:
        if c.key != "W+":
            assert c.charge_text() == pp.fraction_text(pp.PARTICLES[c.key].charge)


def test_the_model_does_not_import_manim() -> None:
    code = "import sys, vidgen.particle_physics; print('manim' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
