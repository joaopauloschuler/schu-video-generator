<!-- topic: particle-physics (also: particle, particle_physics, hep, higgs, standard-model, collider, feynman-diagrams) -->
## Particle physics: particles, collisions and discoveries

Eight scene types share one model, `vidgen.api.particle_physics` (PDG 2024 masses, widths and
lifetimes; the conservation checker; the Standard Model's vertices), and **compute** what they
show: `standard_model` (the chart), `feynman` (diagrams, every vertex checked), `kinematics`
(momentum arrows in two frames), `detector` (a schematic event display), `mass_spectrum`
(simulated data with a resonance, a fit and its significance), `decay_chain`, `branching` and
`branching_pie`; worked numbers go in a `calculation` (`mass: pi+`, `lifetime: mu-`, `width: Z`,
`from_scene`), curves in a `plot`. Every param: `docs/CONFIG.md`; the craft in full:
`docs/COOKBOOK-PARTICLES.md` in the schu-video-generator repository; a whole example:
`examples/higgs-discovery` ("How the Higgs boson was found": the chart, gluon fusion through a top
loop, the decay modes, a diphoton event, the invariant mass worked out, a simulated spectrum with
its bump and fit, what five sigma means; 16:9 and 9:16).

**Planning.** A discovery reads as a chain of questions, one picture each: what is it
(`standard_model` with `highlight` or `couplings`), how is it made (`feynman` with `vertex_rule`
and `travel`), what does it become (`branching`, `decay_chain`), what does the detector see
(`detector`), how is it measured (`calculation`, `kinematics`), how do we know it is real
(`mass_spectrum`, then what the significance means). 15–35 s per scene, 3–4 minutes in all.

**Choosing the scene.** Forces and processes → `feynman` (12 presets or your own lines; a
forbidden vertex is refused with the reason); allowed or forbidden decays → `vertex_rule` with
`show: [checks]` or the checker's reason in words; frames, p*, opening angles, βγcτ →
`kinematics`; signatures → `detector` (`switch_view` for r–z); a resonance in data →
`mass_spectrum`; lifetimes → `decay_chain`; how often each decay happens → `branching` bars (a pie
hides H → γγ's 0.23 %).

**Units.** Particle physicists write masses, momenta and energies in GeV with c = 1; the scenes
write the full units (GeV/c², GeV/c) so the dimensions show. Either is right: pick one per
sentence; in a `calculation` in natural units say "c = 1" in a symbol's meaning. Compute m² first
(`unit: GeV^2`) and then `sqrt(m2)`, or the square root's argument is written in SI. τ = ħ/Γ: the
Higgs boson's 4.1 MeV width is τ = 1.6 × 10⁻²² s.

**Honesty.** Simulated data are always called simulated (the scenes label them; say it too);
the detector is schematic (generic sizes, no experiment's geometry or logo); name the sources —
PDG 2024 for masses, lifetimes and measured branching ratios, the LHC Higgs Cross Section Working
Group's Yellow Report 4 for the Higgs boson's predicted branching ratios and width ("a theory
prediction"). A spectrum's significance is **local** (the look-elsewhere effect is not included);
the readout's `expected` is the Asimov median, the note after the fit the observed likelihood
ratio. A p-value is the chance that background alone fluctuates this high, not the chance of
being wrong: 5σ ↔ p ≈ 2.9 × 10⁻⁷, about once in 3.5 million. Quote real history only when
certain, and never real event counts or significances on simulated pictures.

**Pacing.** One idea per beat, 10–25 words, an action every few seconds (`highlight` on the
particle named, `couplings` on "field", `vertex_rule`, `travel`, `swap_channel`, `grow` / `fit` /
`annotate` on the spectrum). Let a spectrum fill over two beats (`grow: axes, to: 12000`, then the
rest) before the fit. A full chart is about 65 words: `max_words` warns, which is expected. In 9:16
the detector's legend falls under the readable size (`legend: false`). Kokoro at speed 0.85.

**Lint.** `particle_mass`, `particle_charge`, `particle_spin`, `particle_lifetime`,
`branching_ratio`, `conservation_claim`, `feynman_boson`, `kinematics_number`,
`detector_signature`, `significance_claim`, `simulated_label`, `particle_units` check the
narration and the screens against the model; `calc_numbers`, `calc_units`, `calc_sigfigs` check
the calculations. Run `vidgen lint` in 16:9 and 9:16.

```yaml
- id: mass
  type: calculation
  params:
    title: "The invariant mass of the two photons"
    symbols:
      - {name: pT1, value: "56.3 GeV", meaning: "photon 1, c = 1", source: "the event"}
      - {name: pT2, value: "54.7 GeV", meaning: "photon 2, c = 1", source: "the event"}
      - {name: deta, value: "1.00", meaning: "pseudorapidity difference", tex: "\\Delta\\eta"}
      - {name: dphi, value: "178.2 deg", meaning: "angle across the beam", tex: "\\Delta\\phi"}
    calculations:
      - {name: m2, expr: "2*pT1*pT2*(cosh(deta) - cos(dphi))", unit: GeV^2, meaning: "its square"}
      - {name: m, expr: "sqrt(m2)", unit: GeV, meaning: "invariant mass of the two photons"}
  beats:
    - text: "For photons it needs only their transverse momenta and the angles between them."
      actions: [{substitute: calc1, at: "@momenta"}]
    - text: "This event gives one hundred and twenty-five GeV."
      actions: [{compute: calc2, at: "@This"}]
```

