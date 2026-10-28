"""Step 242 (DESIGN §99.13): the particle-physics accuracy lint.

Each rule finds its planted mistake and leaves the right statement — and tricky phrasings
(negations, "not a photon", contrasts, other quantities in the sentence) — alone; the scene
facts (a kinematics scene's values, a spectrum's significances, a diagram's bosons, simulated
data); the gate (only particle projects, except charge and spin); no false positives on the
gallery's particle samples; no render."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from vidgen.config import LINT_RULES, LintRules
from vidgen.lint import RULES
from vidgen.lint.particle_rule import PARTICLE_RULES, facts, particle_issues
from vidgen.particle_physics import accuracy as pa
from vidgen.project import Project

REPO = Path(__file__).resolve().parent.parent


def _rules(found: list[pa.Said]) -> list[str]:
    return [f.rule for f in found]


def _project(make_project, scenes: list[dict[str, Any]], **extra: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, **extra)))


def _card(sid: str, *texts: str, text: str = "card") -> dict[str, Any]:
    return {"id": sid, "type": "text_card", "params": {"text": text}, "beats": [{"text": t} for t in texts]}


#: A particle scene so the project is read by every rule.
CHART = {"id": "chart", "type": "standard_model", "beats": [{"text": "The Standard Model."}]}


def _found(project: Project, scene_id: str) -> list[tuple[str, str]]:
    import vidgen.scenes  # noqa: F401 - registers the built-in scene types

    return [(f.rule, f.message) for f in particle_issues(project, scene_id, project.config.lint.rules)]


# ----- registration ------------------------------------------------------------------------------------


def test_rules_are_registered_last_with_their_defaults() -> None:
    assert list(LINT_RULES[-len(PARTICLE_RULES):]) == list(PARTICLE_RULES)
    assert all(RULES[n].scope == "scene" for n in PARTICLE_RULES)
    defaults = {n: RULES[n].default for n in PARTICLE_RULES}
    assert defaults["particle_charge"] == defaults["particle_spin"] == "error" and defaults["particle_units"] == "info"
    assert {defaults[n] for n in PARTICLE_RULES if n not in ("particle_charge", "particle_spin", "particle_units")} == {"warning"}
    rules = LintRules()
    assert rules.particle_mass.tolerance == 0.05 and rules.branching_ratio.tolerance == 0.1 and rules.significance_claim.sigmas == 0.5


def test_the_knowledge_does_not_import_manim() -> None:
    import subprocess
    import sys

    code = "import sys, vidgen.particle_physics.accuracy; print('manim' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_mentions_names_and_symbols() -> None:
    found = [(m.text, m.keys) for m in pa.mentions("μ⁺ and π⁰ and ν̄ₑ and W⁻ and e⁺e⁻, the b̄ quark, the anti-up quark, the Z boson")]
    assert found == [("μ⁺", ("mu+",)), ("π⁰", ("pi0",)), ("ν̄ₑ", ("anti-nu_e",)), ("W⁻", ("W-",)), ("e⁺", ("e+",)), ("e⁻", ("e-",)),
                     ("b̄", ("anti-b",)), ("anti-up quark", ("anti-u",)), ("Z boson", ("Z",))]
    assert pa.mentions("Z = 5.3 here; the muon chambers; the electron number") == []
    assert pa.mentions("neutrinos")[0].keys == ("nu_e", "nu_mu", "nu_tau") and pa.mentions("Higgs")[0].plural is False


# ----- the claims ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sentence, flagged", [
    ("The Z weighs about 91 GeV.", False), ("A top quark is 173 GeV.", False), ("The mass of the W is 80.4 GeV/c².", False),
    ("How a 125 GeV Higgs boson decays", False), ("The b quark weighs about 4.7 GeV.", False),   # the pole mass: the scheme
    ("A 45 GeV electron enters the ECAL.", False), ("Each photon carries 62.6 GeV.", False), ("The Z is 11 GeV heavier than the W.", False),
    ("The proton beam has an energy of 6.5 TeV.", False), ("The W weighs 91 GeV.", True), ("The muon's mass is 105.7 GeV.", True),
    ("The photon has a mass of 1 MeV.", True), ("The top quark is not 80 GeV.", False), ("The invariant mass of the two photons is 125 GeV.", False),
])
def test_mass(sentence: str, flagged: bool) -> None:
    found = pa.mass_claims(sentence)
    assert bool(found) == flagged, found
    if sentence.startswith("The W weighs"):
        assert "did you mean the Z boson" in found[0].message and "80.369 GeV" in found[0].message
    if "105.7 GeV" in sentence:
        assert "prefix" in found[0].message


@pytest.mark.parametrize("sentence, flagged", [
    ("The down quark has charge +2/3.", True), ("The up quark has charge +2/3.", False), ("The up quark has an electric charge of plus two thirds.", False),
    ("The electron carries a charge of minus one.", False), ("The positron has charge -1.", True), ("The neutron is positively charged.", True),
    ("The neutron is neutral.", False), ("The W has charge 1.", False), ("The strange quark has charge 2/3.", True),
    ("The proton's charge is the sum: two thirds plus two thirds minus one third.", False), ("The down quark does not have charge +2/3.", False),
])
def test_charge(sentence: str, flagged: bool) -> None:
    found = pa.charge_claims(sentence)
    assert bool(found) == flagged, found
    if sentence.startswith("The down quark has"):
        assert found[0].message.startswith("the down quark's charge is −1/3") and "up quark" in found[0].message


@pytest.mark.parametrize("sentence, flagged", [
    ("The photon has spin 1/2.", True), ("The photon has spin 1.", False), ("The Higgs boson is a spin-zero particle.", False),
    ("The Higgs boson is a fermion.", True), ("The electron is a fermion.", False), ("The electron has spin one half.", False),
    ("The gluon is a boson.", False), ("The electron is a boson.", True), ("The photon is not a fermion.", False),
])
def test_spin(sentence: str, flagged: bool) -> None:
    assert bool(pa.spin_claims(sentence)) == flagged


@pytest.mark.parametrize("sentence, flagged", [
    ("The muon lives 2.2 microseconds.", False), ("The muon lives 2.2 milliseconds.", True), ("The charged pion lives 26 nanoseconds.", False),
    ("A free neutron decays with a half-life of about ten minutes.", False), ("The neutron lives about 15 minutes.", False),
    ("The Z is 2.5 GeV wide.", False), ("The Z has a width of 3.5 GeV.", True), ("The Higgs boson at 125 GeV is only about 4 MeV wide.", False),
    ("Cosmic-ray muons live 22 microseconds in our frame.", False), ("The fitted width of the Z is 3.5 GeV.", False),
    ("The tau lives 290 femtoseconds.", False), ("The tau lives 2.9 picoseconds.", True),
])
def test_lifetime_and_width(sentence: str, flagged: bool) -> None:
    assert bool(pa.lifetime_claims(sentence)) == flagged


@pytest.mark.parametrize("sentence, flagged", [
    ("Most Higgs bosons decay to two photons.", True), ("Most Higgs bosons decay to bottom quarks.", False),
    ("Most Higgs bosons decay to a pair of b quarks.", False), ("Seventy percent of Z bosons decay to hadrons.", False),
    ("The Z decays to hadrons 50 % of the time.", True), ("The W rarely decays to a muon and a neutrino.", True),
    ("The most common decay of the Higgs boson is to W bosons.", False), ("About 20 % of Z bosons decay to neutrinos.", False),
    ("The Higgs boson rarely decays to two photons.", False), ("The charged pion decays almost always to a muon and a neutrino.", False),
    ("About 10 % of Z bosons decay to charged leptons.", False), ("Seventy percent of Z bosons decay to hadrons, twenty percent to neutrinos.", False),
    ("The Higgs boson decays to two photons with a branching ratio of 2 %.", True), ("Most Higgs bosons do not decay to photons.", False),
])
def test_branching(sentence: str, flagged: bool) -> None:
    found = pa.branching_claims(sentence)
    assert bool(found) == flagged, found
    if sentence == "Most Higgs bosons decay to two photons.":
        assert "0.227 %" in found[0].message and "bb̄ (58.2 %)" in found[0].message


@pytest.mark.parametrize("sentence, flagged", [
    ("The decay p → e⁺ π⁰ is forbidden by baryon number.", False), ("The decay p → e⁺ π⁰ is forbidden by charge.", True),
    ("The decay μ⁻ → e⁻ γ is allowed.", True), ("A muon decaying to an electron and a photon is allowed.", True),
    ("The decay n → p e⁻ ν̄ₑ is forbidden.", True), ("n → p e⁻ ν̄ₑ conserves charge but violates lepton number.", True),
    ("n → p e⁻ ν̄ₑ conserves charge and lepton number.", False), ("The decay π⁺ → μ⁺ ν_μ is not allowed.", True),
    ("A neutron decays into a proton, an electron and an antineutrino; this is allowed.", False),
    ("The reaction π⁺ → μ⁺ ν_μ is not forbidden.", False), ("μ⁻ → e⁻ γ would violate muon number.", False),
    ("Is the decay μ⁻ → e⁻ γ allowed?", False), ("The pion decays into a muon and a neutrino, which is allowed.", False),
    ("A neutron decays into a proton, an electron, and an antineutrino; this is allowed.", False),
    ("μ⁻ → e⁻ γ conserves charge, but it violates muon number.", False), ("μ⁻ → e⁻ γ conserves charge, but it violates baryon number.", True),
    ("The decay μ⁻ → e⁻ γ is allowed, and p → e⁺ π⁰ is forbidden by baryon number.", True),
])
def test_conservation(sentence: str, flagged: bool) -> None:
    found = pa.conservation_claims(sentence)
    assert bool(found) == flagged, found
    if "forbidden by charge" in sentence:
        assert "conserves charge" in found[0].message and "baryon number not conserved" in found[0].message
    if sentence.startswith("The decay μ⁻ → e⁻ γ is allowed, and"):   # each clause about its own process
        assert len(found) == 1 and found[0].message.startswith("called allowed, but the checker forbids μ⁻ → e⁻ γ")


def test_conservation_of_the_scenes_own_process() -> None:
    from vidgen.particle_physics import parse_process

    own = [parse_process("mu- -> e- anti-nu_e nu_mu")]
    assert pa.conservation_claims("This decay is allowed.", own) == []
    assert _rules(pa.conservation_claims("This decay is forbidden.", own)) == ["conservation_claim"]
    assert pa.conservation_claims("This decay is forbidden.") == []   # no process: nothing to check


@pytest.mark.parametrize("sentence, flagged", [
    ("Gluons couple to electrons.", True), ("Gluons couple to quarks.", False), ("The Higgs boson couples to photons.", True),
    ("The photon couples to neutrinos.", True), ("Neutrinos feel the strong force.", True), ("Neutrinos feel the weak force.", False),
    ("A photon changes the quark's flavour.", True), ("The W boson changes the quark's flavour.", False),
    ("A Z boson turns a down quark into an up quark.", True), ("The W turns a down quark into an up quark.", False),
    ("Electrons feel the electromagnetic force.", False), ("The W is not a photon.", False), ("Gluons do not couple to electrons.", False),
])
def test_bosons(sentence: str, flagged: bool) -> None:
    found = pa.boson_claims(sentence)
    assert bool(found) == flagged, found
    if "photon changes" in sentence:
        assert "did you mean the W" in found[0].message


def test_bosons_of_a_diagram() -> None:
    assert _rules(pa.boson_claims("The electron and the positron exchange a W boson.", ["gamma"])) == ["feynman_boson"]
    assert pa.boson_claims("The electron and the positron exchange a photon.", ["gamma"]) == []
    assert pa.boson_claims("The electron and the positron exchange a W boson.") == []   # no diagram given


@pytest.mark.parametrize("sentence, flagged", [
    ("Photons leave tracks.", True), ("Photons do not leave tracks.", False), ("Photons leave no track.", False),
    ("Electrons leave a track and a shower in the ECAL.", False), ("Neutrinos are seen in the calorimeter.", True), ("Muons stop in the ECAL.", True),
    ("Muons pass through the calorimeters to the muon chambers.", False), ("Neutrons curve in the magnetic field.", True),
    ("Muons curve in the magnetic field.", False), ("Neutrinos show up as missing transverse momentum.", False),
    ("Photons show up as missing momentum.", True), ("Electrons reach the muon chambers.", True), ("Charged pions shower in the HCAL.", False),
    ("Unlike photons, electrons leave tracks.", False),
])
def test_detector_signatures(sentence: str, flagged: bool) -> None:
    assert bool(pa.signature_claims(sentence)) == flagged


@pytest.mark.parametrize("sentence, flagged", [
    ("Five sigma means 99.99994% sure the Higgs exists.", True), ("Five sigma means the chance that the result is a fluke is one in 3.5 million.", True),
    ("At five sigma, background alone would fluctuate this high once in 3.5 million tries.", False), ("Five sigma is a one in a million chance.", True),
    ("Five sigma is a one in 3.5 million chance.", False), ("This is not the probability that the Higgs exists, at five sigma.", False),
    ("Five sigma corresponds to 99.99994 %.", False), ("Five sigma corresponds to 99.9 %.", True),
])
def test_p_value_meaning(sentence: str, flagged: bool) -> None:
    assert bool(pa.p_meaning_claims(sentence)) == flagged


def test_sigma_against_the_spectrum() -> None:
    computed = [("expected", 5.3), ("likelihood ratio", 6.7)]
    assert pa.sigma_claims("The bump reaches five sigma.", computed, 0.5, 5.3) == []
    assert pa.sigma_claims("The bump reaches about 6 sigma.", computed, 0.5, 5.3) == []
    assert _rules(pa.sigma_claims("The bump reaches 9 sigma.", computed, 0.5, 5.3)) == ["significance_claim"]
    assert pa.sigma_claims("Five sigma means discovery.", computed, 0.5, 5.3) == []   # the convention, not the bump
    assert pa.sigma_claims("After a few thousand events it is already at three sigma.", computed, 0.5, 5.3) == []


@pytest.mark.parametrize("sentence, flagged", [
    ("A 5 GeV muon travels about 30 km before it decays.", False), ("A 5 GeV muon travels about 3 km before it decays.", True),
    ("With a momentum of 1 GeV/c a charged pion flies 56 m on average.", False),
    ("The reaction p p → p p p p̄ needs a beam of at least 6.6 GeV.", False), ("The reaction p p → p p p p̄ needs at least 5.6 GeV of kinetic energy.", False),
    ("The reaction p p → p p p p̄ needs at least 2 GeV.", True),
])
def test_flight_and_thresholds(sentence: str, flagged: bool) -> None:
    assert bool(pa.flight_claims(sentence) + pa.threshold_claims(sentence)) == flagged


def test_kinematics_values() -> None:
    values = {"p_star": (29.79 * 1.602176634e-13 / 299792458.0, "MeV/c"), "M": (139.57 * 1.602176634e-13 / 299792458.0**2, "MeV/c^2")}
    assert pa.kinematics_claims("The muon's momentum is 29.8 MeV/c.", values) == []
    assert _rules(pa.kinematics_claims("The muon's momentum is 40 MeV/c.", values)) == ["kinematics_number"]
    assert pa.kinematics_claims("The muon flies off.", values) == []


# ----- the scenes and the project ------------------------------------------------------------------------


def test_charge_and_spin_read_every_project_the_rest_only_particle_ones(make_project) -> None:
    plain = _project(make_project, [_card("c", "The down quark has charge +2/3.", "The W weighs 91 GeV.", "Photons leave tracks.")])
    assert [r for r, _ in _found(plain, "c")] == ["particle_charge"]
    with_chart = _project(make_project, [CHART, _card("c", "The down quark has charge +2/3.", "The W weighs 91 GeV.", "Photons leave tracks.")])
    assert sorted(r for r, _ in _found(with_chart, "c")) == ["detector_signature", "particle_charge", "particle_mass"]


def test_screen_text_and_rules_off(make_project) -> None:
    p = _project(make_project, [CHART, _card("c", "A card.", text="The muon lives 2.2 ms.")],
                 lint={"rules": {"particle_mass": {"severity": "off"}}})
    found = _found(p, "c")
    assert [r for r, _ in found] == ["particle_lifetime"] and found[0][1].startswith("text 'The muon lives 2.2 ms.'")


def test_scene_facts(make_project) -> None:
    scenes = [
        {"id": "kin", "type": "kinematics", "params": {"decay": "pi+ -> mu+ nu_mu", "frames": "rest"},
         "beats": [{"text": "The muon's momentum is 29.8 MeV/c."}, {"text": "The muon's momentum is 40 MeV/c."}]},
        {"id": "fey", "type": "feynman", "params": {"preset": "bhabha"},
         "beats": [{"text": "The electron and the positron exchange a W boson."}, {"text": "This process is forbidden."}]},
        {"id": "spec", "type": "mass_spectrum", "params": {"channel": "h_to_4l", "seed": 2},
         "beats": [{"text": "The bump reaches nine sigma."}, {"text": "The bump reaches about six sigma."}, {"text": "These are real data from CMS."}]},
        {"id": "det", "type": "detector", "params": {"event": "z_to_mumu", "label": "event display"}, "beats": [{"text": "A Z decays to two muons."}]},
        {"id": "plot", "type": "plot", "params": {"models": {"ev": {"kind": "function", "function": "mass_spectrum",
                                                                    "params": {"mass": 125, "resolution": 1.6, "lo": 100, "hi": 160, "events": 2000, "signal": 80}}},
                                                  "series": [{"name": "events", "values": "m", "bin_width": 2}]},
         "beats": [{"text": "A histogram."}]},
    ]
    p = _project(make_project, scenes)
    known = facts(p)
    assert known.particle and known.scenes["kin"].values["p_star"][1] == "MeV/c" and "gamma" in known.scenes["fey"].bosons
    assert [w for w, _ in known.scenes["spec"].sigmas] == ["expected, Asimov, all events", "likelihood-ratio fit"]
    assert [r for r, _ in _found(p, "kin")] == ["kinematics_number"]
    assert sorted(r for r, _ in _found(p, "fey")) == ["conservation_claim", "feynman_boson"]
    assert sorted(r for r, _ in _found(p, "spec")) == ["significance_claim", "simulated_label"]
    assert [r for r, _ in _found(p, "det")] == ["simulated_label"]
    assert [r for r, _ in _found(p, "plot")] == ["simulated_label"]


def test_units_convention_is_info(make_project) -> None:
    scenes = [CHART, _card("a", "A card.", text="The W mass is 80.4 GeV/c²."), _card("b", "A card.", text="The Z mass is 91.2 GeV.")]
    p = _project(make_project, scenes)
    assert _found(p, "a") == [] and [r for r, _ in _found(p, "b")] == ["particle_units"]


def test_gallery_particle_samples_are_clean() -> None:
    project = Project.load(REPO / "examples" / "gallery")
    for spec in project.config.scenes:
        assert _found(project, spec.id) == [], spec.id
