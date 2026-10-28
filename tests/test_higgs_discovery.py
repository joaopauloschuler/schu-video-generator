"""Step 243: the particle-physics example `examples/higgs-discovery` through `vidgen validate` (16:9
and its 9:16 variant), the particle_* and calc_* lint, and the numbers it narrates computed by
`vidgen.particle_physics`."""

from __future__ import annotations

import math
import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from vidgen.cli import main, validate_all
from vidgen.project import Project

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "higgs-discovery"


def _scene(project: Project, sid: str) -> dict:
    data = yaml.safe_load((EXAMPLE / "video.yaml").read_text(encoding="utf-8"))
    return next(s for s in data["scenes"] if s["id"] == sid)


@pytest.mark.parametrize("variant", [None, "short"])
def test_the_example_validates_and_uses_the_particle_scenes(variant: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = shutil.copytree(EXAMPLE, tmp_path / "higgs", ignore=shutil.ignore_patterns("build", "output", "audio"))
    assert main(["validate", str(root)]) == 0
    capsys.readouterr()
    project = Project.load(root, variant=variant)
    assert validate_all(project, keep_going=True)[0] == []
    types = [s.type for s in project.config.scenes]
    for kind in ("standard_model", "branching", "detector", "calculation", "plot"):
        assert kind in types, kind
    assert types.count("feynman") == 2 and types.count("mass_spectrum") == 2
    assert project.config.voice.provider == "kokoro" and project.config.music is not None
    text = (root / "video.yaml").read_text(encoding="utf-8")
    for used in ("preset: gg_to_h", "preset: h_to_gammagamma", '{couplings: "particle:H"', "swap_channel",
                 "{preset: h_to_gammagamma, seed: 10}", "channel: h_to_gammagamma", "channel: h_to_4l",
                 '"annotation:significance"', "4 July 2012", 'at: "@'):
        assert used in text, used


def test_the_lint_is_clean() -> None:
    from vidgen.lint.calc_rule import calc_issues
    from vidgen.lint.particle_rule import particle_issues

    for variant in (None, "short"):
        project = Project.load(EXAMPLE, variant=variant)
        rules = project.config.lint.rules
        for scene in project.config.scenes:
            assert particle_issues(project, scene.id, rules) == [], scene.id
            assert calc_issues(project, scene.id, rules) == [], scene.id


def test_the_numbers_are_the_models() -> None:
    from vidgen.lint.calc_rule import candidates
    from vidgen.particle_physics import branching, data, detector, spectrum

    project = Project.load(EXAMPLE)
    _, results = candidates(project)
    assert {r.name: r.value.value_text() for r in results["mass"]}["m"] == "125 GeV"

    # the calculation's inputs are the display event's photons, as the readout writes them
    event = detector.generate("h_to_gammagamma", 10)
    photons = sorted((p for p in event.particles if p.kind == "photon" and not p.group), key=lambda p: -p.pt)
    assert [f"{p.pt:.1f}" for p in photons] == ["56.3", "54.7"]
    assert [f"{p.eta:+.2f}" for p in photons] == ["-0.07", "+0.93"]
    dphi = abs(math.degrees(photons[0].phi - photons[1].phi))
    assert f"{360 - dphi if dphi > 180 else dphi:.1f}" == "178.2"
    assert round(event.products_mass(), 1) == 125.2
    symbols = {s["name"]: s["value"] for s in _scene(project, "mass")["params"]["symbols"]}
    assert symbols == {"pT1": "56.3 GeV", "pT2": "54.7 GeV", "deta": "1.00", "dphi": "178.2 deg"}

    # the lifetime said (1.6 × 10⁻²² s) and the branching ratios shown
    assert round(data.PARTICLES["H"].lifetime * 1e22, 1) == 1.6
    shares = {m.label: m.percent for m in branching.branching("H").modes}
    assert (round(shares["bb̄"]), round(shares["ZZ*"], 1), round(shares["γγ"], 2)) == (58, 2.6, 0.23)

    # the spectra's fitted significances: about 5σ (diphoton, seed 13) and about 4σ (4ℓ, seed 4)
    for channel, seed, z_said in (("h_to_gammagamma", 13, 5.2), ("h_to_4l", 4, 3.9)):
        ch = spectrum.CHANNELS[channel]
        sim = spectrum.generate(spectrum.channel_spec(channel, seed))
        edges = np.arange(ch.lo, ch.hi + ch.bin_width / 2, ch.bin_width)
        sig = spectrum.likelihood_significance(edges, sim.counts(edges), ch.peak, ch.background_degree,
                                               spectrum.peak_guesses(ch.peak, ch.mass, ch.resolution))
        assert round(sig.z, 1) == z_said and abs(sig.fit.params[1] - 125) < 1, channel

    # the five-sigma plot: one-sided normal tails, 1 in 44, 740 and 3.5 million
    series = _scene(project, "five_sigma")["params"]["series"][0]
    for z, p in zip(series["x"], series["y"]):
        assert p == pytest.approx(0.5 * math.erfc(z / math.sqrt(2)), rel=2e-3), z
    assert [round(1 / spectrum.p_value(z)) for z in (2, 3)] == [44, 741] and round(1 / spectrum.p_value(5) / 1e5) == 35


def test_the_readmes_and_the_cookbook_point_to_it() -> None:
    assert "examples/higgs-discovery/README.md" in (REPO / "README.md").read_text(encoding="utf-8")
    assert "examples/higgs-discovery/README.md" in (REPO / "docs" / "COOKBOOK-PARTICLES.md").read_text(encoding="utf-8")
    assert "COOKBOOK-PARTICLES.md" in (EXAMPLE / "README.md").read_text(encoding="utf-8")
