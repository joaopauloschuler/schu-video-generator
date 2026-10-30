# How the Higgs boson was found

A particle-physics explainer (eleven scenes, about 3 min 49 s with Kokoro narration) built on the
Phase Y scene types (`standard_model`, `feynman`, `branching`, `detector`, `mass_spectrum`) with a
`calculation` and a `plot` (DESIGN §99). Masses, widths, branching ratios and significances on
screen come from schu-video-generator's particle model, and the narration says the same numbers (`vidgen lint`'s
`particle_*` rules check it). Every event is **simulated** and labelled so. The craft:
[the particle-physics cookbook](../../docs/COOKBOOK-PARTICLES.md).

```
vidgen validate examples/higgs-discovery           # the short (9:16) variant too
vidgen lint examples/higgs-discovery [--variant short]   # incl. the particle_* rules
vidgen storyboard examples/higgs-discovery --per-beat 2
vidgen tts examples/higgs-discovery                # Kokoro (the kokoro extra): local and free
vidgen render examples/higgs-discovery [--variant short]
```

| scene | type | what it shows |
|---|---|---|
| `intro` | `title` | how do you find a particle that falls apart almost at once? |
| `chart` | `standard_model` | quarks, leptons and the force carriers; the Higgs boson (no charge, spin 0, 125.2 GeV/c²); `couplings` on the Higgs: its field gives the W and Z their masses and the quarks and charged leptons theirs through Yukawa couplings; most of a proton's mass is the energy of its quarks and gluons, not the Higgs |
| `production` | `feynman` (`gg_to_h`) | gluon fusion through a top-quark loop (gluons are massless: no H g g vertex); the Yukawa vertex t → t H with y = √2 m/v ≈ 0.99; the dots travelling through |
| `decays` | `branching` | the Standard Model prediction at 125 GeV (LHC Higgs XS WG, YR4): bb̄ 58.2 % (lost in quark jets), γγ 0.227 % (rare but clean), ZZ* 2.62 % (to electrons or muons: the golden channel); τ = ħ/Γ ≈ 1.6 × 10⁻²² s |
| `loop` | `feynman` (`h_to_gammagamma`) | two photons through a loop: top quarks, then the W loop (`swap_channel`), which contributes most |
| `event` | `detector` | a simulated H → γγ event (seed 10) in the schematic detector: soft charged tracks curling, the two photons' ECAL showers with no tracks, the readout (p_T 56.3 and 54.7 GeV/c, η −0.07 and +0.93, m(γγ) = 125.2 GeV/c²) |
| `mass` | `calculation` | m² = 2 p_T1 p_T2 (cosh Δη − cos Δφ) for massless particles, with the event's numbers (Δφ = 178.2°): 1.57 × 10⁴ GeV², m = 125 GeV (natural units, c = 1) |
| `diphoton` | `mass_spectrum` | 30 000 simulated photon pairs (seed 13) filling, a bump near 125 GeV, the fit (μ = 124.9 ± 0.4 GeV), the local significance 5.2σ (likelihood ratio, p = 8.2 × 10⁻⁸) |
| `four_leptons` | `mass_spectrum` | 40 simulated four-lepton events (seed 4) as points with √N bars: the same peak, 3.9σ local from this channel alone |
| `five_sigma` | `plot` | the one-sided p-value against the significance on a log axis: 2σ once in 44, 3σ once in 740, 5σ once in 3.5 million — the chance that background alone fluctuates this high, not the chance of being wrong |
| `recap` | `bullets` | announced on 4 July 2012 by ATLAS and CMS at CERN's LHC; each about 5σ on its own; seen as two photons and as four leptons; a new boson near 125 GeV |

**Numbers.** Particle values are PDG 2024 (`vidgen.particle_physics`); the Higgs boson's width
(4.1 MeV, hence τ = ħ/Γ = 1.61 × 10⁻²² s) and branching ratios are the Standard Model prediction
(LHC Higgs Cross Section Working Group, Yellow Report 4, the m_H = 125 GeV table), shown as "a
theory prediction, not a measurement". The invariant mass is worked out from the event display's
own photons: p_T and η as the readout writes them, Δφ = 178.2° from the event (φ = −159.2° and
22.6°); m = 125.1 GeV from the rounded values (the readout's 125.2 GeV/c² uses the unrounded
ones). The five-sigma plot's p-values are ½ erfc(Z/√2): 2σ 0.0228, 3σ 0.00135, 5σ 2.87 × 10⁻⁷.

**Honesty.** Every event and spectrum is simulated from a seed (the legend, the caption and the
detector's label say so): counts, backgrounds and significances are not ATLAS's or CMS's. The
significances are local (no look-elsewhere effect). The detector is schematic (generic sizes, no
experiment's geometry or logo). The only historical facts are the announcement on 4 July 2012 by
ATLAS and CMS at CERN's Large Hadron Collider and that each experiment reached about five sigma on
its own; no real event counts or significances are quoted.

**Choices.** Natural units in the calculation (p_T in GeV with c = 1, the mass in GeV, the way
particle physicists write it); the chart and the detector readout write GeV/c². Seed 13 of the
diphoton channel gives a fitted significance near the discovery threshold (seed 1 gives 6.7σ);
seed 4 of the four-lepton channel a realistic single-channel 3.9σ. The event's signature legend is
off (`legend: false`): the narration says the signatures, and the 9:16 legend fell under the
readable size. Music: `discovery` at −10 dB, ducked under the voice.

**Checks.** `vidgen validate`; `vidgen lint` with the Kokoro narration: 0 errors and no
particle-physics findings in 16:9 and 9:16; the warnings left are the Standard Model chart's own
(`max_words`: about 65 words in a full chart; `contrast` on a dimmed gluon cell during `couplings`;
in 16:9 the generation numeral "II"). The 16:9 video renders at 1920×1080, 30 fps in about 5½
minutes on the development machine and the 9:16 one at 1080×1920 in about 7½ minutes (the longest
scene, `diphoton`, about 64 s; peak memory of a render process about 1.4 GB): 228.6 s, video and
audio the same length, −16.0 LUFS integrated, true peak −1.9 dBTP. No audio is committed.
