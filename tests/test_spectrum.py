"""Collisions, decays and data (Phase Y, Step 241; DESIGN §99.11–§99.12): simulated spectra
(deterministic, signal share, window), the Asimov and counting significances against hand values,
p-values, peak fits recovering the mass across seeds, the likelihood-ratio significance, decay
times and the lifetime fit, the Z line shape, branching ratios (sources, sums, the conservation
checker), decay chains; the scene types ``mass_spectrum``, ``decay_chain``, ``branching`` and
``branching_pie`` (params, targets, errors, tiny renders) and the ``plot`` additions
(``residuals: background``, ``parameters``, ``residuals:<fit>`` targets)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from conftest import minimal_config
from test_actions import render
from vidgen.errors import VidgenError
from vidgen.particle_physics import PARTICLES
from vidgen.particle_physics import branching as br
from vidgen.particle_physics import spectrum as sp
from vidgen.plotcore import run_registered
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}


def _edges(c: sp.Channel) -> np.ndarray:
    return np.arange(c.lo, c.hi + 1e-9, c.bin_width)


# ----- significance ---------------------------------------------------------------------------------


def test_asimov_against_hand_values() -> None:
    # √(2((s+b)ln(1+s/b) − s)): s=10, b=100 → √(2(110 ln 1.1 − 10)) = √0.968240 = 0.98399
    assert sp.asimov(10, 100) == pytest.approx(0.983992, abs=1e-6)
    # s=100, b=100 → √(2(200 ln 2 − 100)) = √77.2589 = 8.78970 (s/√b would say 10)
    assert sp.asimov(100, 100) == pytest.approx(8.789703, abs=1e-6)
    assert sp.asimov(1, 10_000) == pytest.approx(1 / math.sqrt(10_000), rel=1e-3)   # s ≪ b: s/√b
    assert sp.asimov(0, 100) == 0.0
    with pytest.raises(VidgenError):
        sp.asimov(5, 0)


def test_p_values_and_their_text() -> None:
    assert sp.p_value(5) == pytest.approx(2.8665157e-7, rel=1e-6)   # one-sided 5σ
    assert sp.FIVE_SIGMA_P == pytest.approx(2.8665157e-7, rel=1e-6)
    assert sp.p_value(0) == pytest.approx(0.5)
    assert sp.p_value(3) == pytest.approx(1.3498980e-3, rel=1e-6)
    assert sp.p_text(sp.p_value(5)) == "2.9 × 10⁻⁷"
    assert sp.sigma_text(3.42) == "3.4σ" and sp.sigma_text(78) == "> 20σ"
    for narrow in (False, True):
        text = " ".join(sp.meaning_lines(5.0, narrow=narrow))
        assert "background alone" in text and "not that the result is wrong" in text and "2.9 × 10⁻⁷" in text and "one-sided" in text
    # Step 242: the short note on screen (the narration says the rest)
    assert sp.short_meaning(6.7) == ["6.7σ local · p(background only) = 1.0 × 10⁻¹¹"]
    assert sp.short_meaning(6.7, narrow=True) == ["6.7σ local", "p = 1.0 × 10⁻¹¹", "(background only)"]
    assert sp.short_meaning(30.0, narrow=True)[0] == "> 20σ local" and sp.short_meaning(30.0, narrow=True)[1].startswith("p < ")


def test_counting_significance() -> None:
    assert sp.counting_significance(100, 100) == 0.0
    assert sp.counting_significance(50, 100) == 0.0
    n, b = 130.0, 100.0
    assert sp.counting_significance(n, b) == pytest.approx(math.sqrt(2 * (n * math.log(n / b) - (n - b))))


# ----- simulated spectra ----------------------------------------------------------------------------


def test_spectra_are_deterministic_and_seeded() -> None:
    spec = sp.channel_spec("h_to_gammagamma", seed=4)
    a, b = sp.generate(spec), sp.generate(sp.channel_spec("h_to_gammagamma", seed=4))
    np.testing.assert_array_equal(a.masses, b.masses)
    other = sp.generate(sp.channel_spec("h_to_gammagamma", seed=5))
    assert not np.array_equal(a.masses, other.masses)
    assert a.events == spec.events and np.all((a.masses >= spec.lo) & (a.masses <= spec.hi))
    # the signal share fluctuates around signal / events (binomial)
    n_sig = int(a.signal.sum())
    assert abs(n_sig - spec.signal) < 4 * math.sqrt(spec.signal)
    # the signal sits at the Higgs mass, smeared by the resolution; the background falls
    sig = a.masses[a.signal]
    assert np.median(sig) == pytest.approx(125.2, abs=0.5)
    assert np.std(sig) == pytest.approx(spec.resolution, rel=0.2)
    counts = a.counts(_edges(sp.CHANNELS["h_to_gammagamma"]))
    assert counts[:10].mean() > 2 * counts[-10:].mean()


def test_spectrum_spec_problems() -> None:
    assert sp.SpectrumSpec(91, 2.5, 1, 70, 110, 100, 50).problems() == []
    assert "outside the window" in sp.SpectrumSpec(91, 2.5, 1, 100, 110, 100, 50).problems()[0]
    assert "between 0 and events" in sp.SpectrumSpec(91, 2.5, 1, 70, 110, 100, 500).problems()[0]
    assert "slope" in sp.SpectrumSpec(91, 2.5, 1, 70, 110, 100, 50, "exponential", slope=0).problems()[0]
    with pytest.raises(VidgenError, match="channel 'h_to_gg'"):
        sp.channel_spec("h_to_gg")


def test_asimov_readout_grows_with_the_data() -> None:
    s = sp.generate(sp.channel_spec("h_to_gammagamma", seed=1))
    z = s.asimov_curve()
    assert z[0] == 0 and np.all(np.diff(z) >= -1e-12)   # it only grows
    n = s.events
    assert z[n // 4] == pytest.approx(z[n] / 2, rel=0.02)   # ∝ √n when s ≪ b
    assert 4.5 < z[-1] < 6.5   # the preset is tuned to reach about 5σ
    ss, bb = s.expected(n)
    assert z[-1] == pytest.approx(sp.asimov(ss, bb))
    w_s, w_b = sp.window_shares(s.spec)
    assert 0.9 < w_s < 0.99 and 0 < w_b < 0.2
    obs = s.counting_curve()
    assert obs.shape == z.shape and obs[-1] > 2


@pytest.mark.parametrize("channel, strict", [("z_to_mumu", True), ("h_to_4l", True), ("h_to_gammagamma", False)])
def test_fitted_mass_is_the_true_mass_within_its_uncertainty(channel: str, strict: bool) -> None:
    c = sp.CHANNELS[channel]
    edges = _edges(c)
    width = c.resolution if c.peak == "gaussian" else c.width + c.resolution
    pulls = []
    for seed in range(1, 21):
        s = sp.generate(sp.channel_spec(channel, seed=seed))
        fit = sp.likelihood_significance(edges, s.counts(edges), c.peak, c.background_degree, sp.peak_guesses(c.peak, c.mass, width)).fit
        value, error = fit.value("mu" if c.peak == "gaussian" else "M")
        pulls.append((value - c.mass) / error)
    pulls = np.abs(pulls)
    assert np.median(pulls) < 1.0
    assert np.mean(pulls < 2) >= (0.9 if strict else 0.75)
    if strict:
        assert pulls.max() < 3.5


def test_likelihood_ratio_significance() -> None:
    c = sp.CHANNELS["h_to_gammagamma"]
    edges = _edges(c)
    with_signal = sp.generate(sp.channel_spec("h_to_gammagamma", seed=1))
    g = sp.likelihood_significance(edges, with_signal.counts(edges), "gaussian", 3, sp.peak_guesses("gaussian", c.mass, c.resolution))
    assert g.z > 4 and g.q0 == pytest.approx(g.z**2) and g.p == pytest.approx(sp.p_value(g.z))
    assert g.lnl_sb >= g.lnl_b
    background_only = sp.generate(sp.channel_spec("h_to_gammagamma", seed=1, signal=0))
    g0 = sp.likelihood_significance(edges, background_only.counts(edges), "gaussian", 3, sp.peak_guesses("gaussian", c.mass, c.resolution))
    assert g0.z < 3.5   # a local fluctuation at most
    assert sp.peak_background(g.fit, [125.0])[0] > 0


# ----- decay times, line shape ----------------------------------------------------------------------


def test_decay_times_and_the_lifetime_fit() -> None:
    tau = PARTICLES["mu-"].lifetime_s * 1e6   # µs
    t = sp.decay_times(tau, 5000, seed=2)
    np.testing.assert_array_equal(t, sp.decay_times(tau, 5000, seed=2))
    est, err = sp.mean_lifetime(t)
    assert err == pytest.approx(est / math.sqrt(5000))
    assert abs(est - tau) < 3 * err
    assert np.mean(t > tau) == pytest.approx(math.exp(-1), abs=0.02)   # e⁻¹ survive one mean life
    with pytest.raises(VidgenError):
        sp.decay_times(-1, 10)
    cols = run_registered("decay_times", params={"tau": 2.2, "events": 300}, seed=1)
    assert len(cols.table().column("t").values) == 300


def test_z_line_shape() -> None:
    m = PARTICLES["Z"].mass_mev / 1e3
    peak = sp.z_cross_section([m], 3)[0]
    assert peak == pytest.approx(41.5, abs=0.3)   # σ⁰_had = 12π Γee Γhad / (mZ² ΓZ²): 41.5 nb (PDG fit 41.48)
    assert sp.z_cross_section([m], 2)[0] > peak > sp.z_cross_section([m], 4)[0]
    x = np.linspace(m - 5, m + 5, 2001)
    y = sp.z_cross_section(x, 3)
    half = x[y >= peak / 2]
    assert half[-1] - half[0] == pytest.approx(PARTICLES["Z"].width_mev / 1e3, rel=0.02)   # FWHM ≈ Γ_Z
    cols = run_registered("z_lineshape", params={"lo": 88, "hi": 94}, seed=1)
    table = cols.table()
    for name in ("sqrt_s", "sigma", "sigma_2nu", "sigma_4nu"):
        assert len(table.column(name).values) == 241
    assert table.column("sigma").unit == "nb"


def test_mass_spectrum_model() -> None:
    sim = run_registered("mass_spectrum", params={"mass": 91.19, "width": 2.5, "resolution": 1, "lo": 70, "hi": 110, "events": 500,
                                                 "signal": 400}, seed=3)
    m = np.asarray(sim.table().column("m").values)
    assert len(m) == 500 and m.min() >= 70 and m.max() <= 110
    with pytest.raises(VidgenError, match="needs mass"):
        run_registered("mass_spectrum", params={"lo": 70, "hi": 110, "events": 10, "signal": 1}, seed=1)


# ----- branching ratios and chains ------------------------------------------------------------------


def test_branching_tables() -> None:
    assert br.branching_problems() == []
    for key in br.listed():
        assert br.branching(key).total <= 1 + br.SUM_TOLERANCE
    h = br.branching("H")
    assert h.kind == "theory" and "Yellow Report" in h.source
    assert h.mode("bb̄").fraction == pytest.approx(0.5824) and h.mode("γγ").fraction == pytest.approx(0.00227)
    z = br.branching("Z")
    assert z.kind == "measured" and z.mode("invisible").fraction == pytest.approx(0.2)
    assert z.mode("hadrons").fraction == pytest.approx(0.69911) and z.mode("μ⁺μ⁻").fraction == pytest.approx(0.033662)
    w = br.branching("W-")   # by charge conjugation of W+
    assert w.mode("e⁻ν̄ₑ").fraction == pytest.approx(0.1086) and w.mode("hadrons").fraction == pytest.approx(0.6741)
    assert br.branching("pi+").mode("μ⁺ν_μ").fraction == pytest.approx(0.999877)
    with pytest.raises(VidgenError, match="no branching ratios"):
        br.branching("p")


def test_decay_chain_model() -> None:
    ch = br.chain(["pi+ -> mu+ nu_mu", "mu+ -> e+ nu_e anti-nu_mu"])
    assert [n.particle.key for n in ch.nodes] == ["pi+", "mu+", "nu_mu", "e+", "nu_e", "anti-nu_mu"]
    assert ch.nodes[1].decay == 1 and ch.nodes[1].parent == 0 and ch.children(1) == [3, 4, 5]
    assert ch.fractions[0] == pytest.approx(0.999877) and ch.fractions[1] == pytest.approx(1.0)
    assert ch.nodes[0].lifetime_lines() == ["τ = 26.03 ns", "cτ = 7.804 m"]
    four = br.chain(["H -> Z Z*", "Z -> e- e+", "Z* -> mu- mu+"])
    assert four.nodes[2].leg.off_shell and four.nodes[2].decay == 2 and four.nodes[2].lifetime_lines() == ["off shell (virtual)"]
    assert four.nodes[0].lifetime_lines()[0] == "Γ = 4.1 MeV"
    with pytest.raises(VidgenError, match="muon number not conserved"):
        br.chain(["mu- -> e- gamma"])
    with pytest.raises(VidgenError, match="no τ⁺ to decay"):
        br.chain(["pi+ -> mu+ nu_mu", "tau+ -> mu+ nu_mu anti-nu_tau"])


# ----- scenes: params -------------------------------------------------------------------------------


def test_mass_spectrum_params() -> None:
    from vidgen.scenes.mass_spectrum import MassSpectrum

    p = MassSpectrum.parse_params({}, "m")
    assert p.channel == "h_to_gammagamma" and p.series[0].is_live and p.series[0].model == "events"
    assert "simulated" in p.caption and "simulated" in str(p.series[0].name)
    fit = p.resolve(None).fits[0]
    lines = fit.lines()
    assert lines[0].startswith("μ = 125") and lines[1].startswith("σ = ") and len(lines) == 3   # μ, σ, χ²/ν
    assert any(a.id == "significance" for a in p.annotations)
    names = MassSpectrum.target_names(p)
    assert "annotation:significance" in names and "fit:fit" in names and "residuals:fit" not in names
    z = MassSpectrum.parse_params({"channel": "z_to_mumu", "subtract": True, "style": "points"}, "z")
    assert "residuals:fit" in MassSpectrum.target_names(z) and z.fits[0].residuals == "background"
    assert z.resolve(None).fits[0].lines()[0].startswith("M = 91.2")
    custom = MassSpectrum.parse_params({"channel": "custom", "mass": 750, "window": [600, 900], "signal": 300, "events": 3000}, "c")
    assert custom.spectrum_spec().mass == 750
    # Step 242: the note is short by default (three short lines), long on request, or none
    note = next(a for a in p.annotations if a.id == "significance").text.split("\n")
    assert len(note) == 3 and note[0].endswith("σ local") and note[2] == "(background only)"
    long = MassSpectrum.parse_params({"explain": "long"}, "m")
    assert len(next(a for a in long.annotations if a.id == "significance").text.split("\n")) == 4
    assert not any(a.id == "significance" for a in MassSpectrum.parse_params({"explain": False}, "m").annotations)


@pytest.mark.parametrize("params, message", [
    ({"series": []}, "use type: plot"),
    ({"channel": "custom"}, "needs mass and window"),
    ({"window": [130, 160]}, "outside the window"),
    ({"bin_width": 0.01}, "more than 400 bins"),
    ({"fit": False, "subtract": True}, "subtract needs the fit"),
])
def test_mass_spectrum_errors(params: dict, message: str) -> None:
    from vidgen.scenes.mass_spectrum import MassSpectrum

    with pytest.raises(VidgenError, match=message):
        MassSpectrum.parse_params(params, "m")


def test_plot_background_residuals_and_parameters() -> None:
    from vidgen.scenes.plot import Plot

    peak = np.random.default_rng(1).normal(5.0, 1.0, 400)
    base = {"series": [{"name": "d", "values": [float(v) for v in np.concatenate([peak, np.linspace(0, 10, 200)])]}]}
    with pytest.raises(VidgenError, match="residuals: background"):
        Plot.parse_params({**base, "fits": [{"series": "d", "model": "gaussian", "residuals": "background"}]}, "p")
    with pytest.raises(VidgenError, match="no parameter 'mean'"):
        Plot.parse_params({**base, "fits": [{"series": "d", "model": "gaussian", "background": 0, "parameters": ["mean"]}]}, "p")
    p = Plot.parse_params({**base, "fits": [{"series": "d", "model": "linear", "residuals": True}]}, "p")
    assert "residuals1" in Plot.target_names(p) and "residuals:linear fit" in Plot.target_names(p)


def test_branching_scene_params() -> None:
    from vidgen.scenes.branching import Branching, BranchingPie

    p = Branching.parse_params({"particle": "H"}, "b")
    assert p.labels[0] == "bb̄" and p.values[0] == pytest.approx(58.24) and p.unit == " %"
    assert "prediction" in p.caption and p.sort and p.horizontal
    assert "bar:γγ" in Branching.target_names(p)
    top = Branching.parse_params({"particle": "H", "modes": 3}, "b")
    assert len(top.values) == 3 and "3 largest" in top.caption
    z = BranchingPie.parse_params({"particle": "Z"}, "z")
    assert "hadrons" in z.labels and "PDG 2024" in z.caption
    with pytest.raises(VidgenError, match="no branching ratios"):
        Branching.parse_params({"particle": "proton"}, "b")
    with pytest.raises(VidgenError, match="type: bar_chart"):
        Branching.parse_params({"particle": "H", "values": [1]}, "b")


def test_decay_chain_params() -> None:
    from vidgen.scenes.decay_chain import DecayChain

    p = DecayChain.parse_params({"decays": ["pi+ -> mu+ nu_mu", "mu+ -> e+ nu_e anti-nu_mu"]}, "c")
    names = DecayChain.target_names(p)
    assert {"decay1", "decay2", "particle:1", "particle:mu+", "lifetime:pi+", "lifetime:mu+", "chain"} <= set(names)
    assert DecayChain.target_text(p, "particle:mu+") == PARTICLES["mu+"].name
    with pytest.raises(VidgenError, match="muon number not conserved"):
        DecayChain.parse_params({"decays": ["mu- -> e- gamma"]}, "c")


# ----- renders --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(320, 180), (180, 320)], ids=["landscape", "portrait"])
def test_mass_spectrum_renders(size: tuple[int, int], make_project, media: Path) -> None:
    scene = {"id": "m", "type": "mass_spectrum", "params": {"channel": "h_to_4l", "subtract": True, "style": "points"},
             "beats": [{"text": "events arrive", "actions": [{"grow": "axes", "to": 20}]}, {"text": "and more", "actions": [{"grow": "axes"}]},
                       {"text": "a fit", "actions": [{"fit": "fit:fit"}]},
                       {"text": "subtract", "actions": [{"reveal": "residuals:fit"}]},
                       {"text": "what it means", "actions": [{"annotate": "annotation:significance"}]}]}
    project = Project.load(make_project(minimal_config(scenes=[scene], narration=NARRATION)))
    s = render(project, "m", media, size)
    registered = sorted({n for t in s.targets for n in t.names})
    assert set(type(s).target_names(s.params)) <= set(registered)
    assert all(s.is_shown(n) for n in ("axes", "fit:fit", "residuals:fit", "annotation:significance"))
    lines = s._readout_lines(0, None)
    assert lines[0] == "events: 40" and lines[1].startswith("expected: ") and lines[2] == "(local, Asimov)"
    note = next(a for a in s.params.annotations if a.id == "significance")
    assert s.params.y.max is not None   # headroom above the data in both formats (Step 242: 16:9 too)
    if size[1] > size[0]:   # 9:16: one box (the fit's values, then the significance), placed where it hides no data (else above)
        assert s.params.fits[0].show == "none" and note.text.startswith("μ = ") and note.at == "auto"
    else:   # 16:9: the short note (Step 242)
        assert s.params.fits[0].show != "none" and note.text.split("\n")[0].endswith("σ local") and "(background only)" in note.text


@pytest.mark.render
def test_live_histogram_with_a_grow_action_and_a_note(make_project, media: Path) -> None:
    """Step 241 fix in ``plot``: a note (or fit) step on a live histogram held by a ``grow``
    action brings the axes in before the data grow (a fade of the re-shaped axes failed); in a
    ``mass_spectrum`` with a ``fit`` action the note follows the fit."""
    model = {"kind": "function", "function": "mass_spectrum", "params": {"mass": 125, "resolution": 1.6, "lo": 100, "hi": 160, "events": 2000, "signal": 80}}
    scenes = [{"id": "p", "type": "plot", "params": {"models": {"ev": model}, "series": [{"name": "events", "values": "m", "live": True, "bin_width": 2}],
                                                     "annotations": [{"type": "note", "text": "a note"}]},
               "beats": [{"text": "events arrive", "actions": [{"grow": "axes"}]}, {"text": "and the note"}]},
              {"id": "m", "type": "mass_spectrum", "params": {"channel": "h_to_4l"},
               "beats": [{"text": "events arrive", "actions": [{"grow": "axes"}]}, {"text": "a fit", "actions": [{"fit": "fit:fit"}]}]}]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))
    p = render(project, "p", media, (320, 180))
    assert p.is_shown("annotation1")
    m = render(project, "m", media, (320, 180))
    assert m._note_follows_fit() and m.is_shown("annotation:significance") and m.is_shown("fit:fit")


@pytest.mark.render
@pytest.mark.parametrize("size", [(320, 180), (180, 320)], ids=["landscape", "portrait"])
def test_decay_chain_and_branching_render(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [{"id": "c", "type": "decay_chain", "params": {"title": "pion", "decays": ["pi+ -> mu+ nu_mu", "mu+ -> e+ nu_e anti-nu_mu"]},
               "beats": [{"text": "a pion"}, {"text": "decays"}, {"text": "and the muon", "actions": [{"highlight": "lifetime:mu+"}]}]},
              {"id": "b", "type": "branching", "params": {"particle": "Z"}, "beats": [{"text": "the Z"}]}]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))
    s = render(project, "c", media, size)
    assert sorted({n for t in s.targets for n in t.names}) == sorted(type(s).target_names(s.params))
    assert all(s.is_shown(n) for n in ("decay1", "decay2", "particle:e+"))
    fw, fh = s.camera.frame_width, s.camera.frame_height
    for m in s.mobjects:
        if m.family_members_with_points():
            assert abs(m.get_x()) + m.width / 2 <= fw / 2 + 1e-3 and abs(m.get_y()) + m.height / 2 <= fh / 2 + 1e-3
    b = render(project, "b", media, size)
    assert b.is_shown("bar:hadrons")
