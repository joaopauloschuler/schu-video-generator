# Cookbook: particle-physics videos

Craft notes for videos about elementary particles, collisions and discoveries with schu-video-generator's
particle-physics scene types (DESIGN §99): the chart [`standard_model`](CONFIG.md#standard_model),
Feynman diagrams [`feynman`](CONFIG.md#feynman), momentum pictures
[`kinematics`](CONFIG.md#kinematics), event displays [`detector`](CONFIG.md#detector), simulated
spectra [`mass_spectrum`](CONFIG.md#mass_spectrum), [`decay_chain`](CONFIG.md#decay_chain) and
branching ratios [`branching`](CONFIG.md#branching) / [`branching_pie`](CONFIG.md#branching_pie),
with worked numbers in a [`calculation`](CONFIG.md#calculation) and other curves in a
[`plot`](CONFIG.md#plot). The scenes take their values from one model (`vidgen.particle_physics`:
PDG 2024 masses, widths and lifetimes, the conservation checker, the Standard Model's vertices), so
the craft is choosing what to show, being honest about what is simulated or schematic, and saying
the numbers the model gives. The author guide has the short version (`vidgen guide
particle-physics`); every key is in `docs/CONFIG.md`. The worked example is
[`examples/higgs-discovery`](../examples/higgs-discovery/README.md): "How the Higgs boson was
found" — the chart, gluon fusion through a top loop, the decay modes, a diphoton event, the
invariant mass worked out, a simulated spectrum with its bump and fit, and what five sigma means.
The [scene gallery](gallery/README.md#particle-physics) shows every type.

## 1. Planning the video

A discovery or a process reads best as a chain of questions, each answered by one picture:

1. **What is it?** The particle in context: `standard_model` with a `highlight` or `couplings` on
   it (what it couples to, in words, on screen).
2. **How is it made?** The production diagram: `feynman` with a preset or your own lines, a
   `vertex_rule` on the vertex that matters (the coupling and why), `travel` to follow it.
3. **What does it become?** `branching` bars (or `decay_chain` with lifetimes); say which modes
   are common and which are *useful* — they are rarely the same.
4. **What does the detector see?** `detector` built layer by layer: tracks, showers, muons, the
   missing p_T.
5. **How is it measured?** A `calculation` (an invariant mass from the display's numbers) or a
   `kinematics` picture (frames, p*, the opening angle).
6. **How do we know it is real?** `mass_spectrum`: the data filling, the bump, the fit and the
   local significance — then say what the significance means.

About 3–4 minutes for the whole arc at Kokoro's pace; 15–35 s per scene. The example spends about
35 s on the chart, 20 s on each diagram, 30 s on the decays, 20 s on the event and on the
calculation, 25 s on the spectrum and 25 s on five sigma.

## 2. Choosing a scene

| the viewer should understand | scene | notes |
|---|---|---|
| the particles, their masses, charges and spins | `standard_model` | `reveal: groups` over the beats, or `all` with highlights; `antiparticles`, `couplings` on words |
| how a process happens, which force | `feynman` (12 presets or `diagrams`) | every vertex is checked; `swap_channel` between s / t channels or loops |
| why a decay is allowed or forbidden | `feynman` `vertex_rule` with `show: [checks]`, or a sentence; `particle_physics.check(...)` | the checker's reason is the narration's |
| two-body decays, frames, opening angles, decay lengths | `kinematics` | arrows to scale; `boost` on a word; `from_scene` into a `calculation` |
| what a detector records | `detector` (`z_to_mumu`, `h_to_gammagamma`, `h_to_4l`, `w_to_enu`, `dijet`, or listed particles) | `switch_view` between x–y and r–z |
| a resonance in data | `mass_spectrum` (`z_to_mumu`, `h_to_gammagamma`, `h_to_4l`, `custom`) | simulated, seeded; fit and significance |
| lifetimes along a chain | `decay_chain` | τ and cτ, or Γ for a resonance |
| how often each decay happens | `branching` (bars; small modes visible) or `branching_pie` (few large modes) | a pie hides H → γγ (0.23 %) |
| a number worked out | `calculation` with `mass:`, `lifetime:`, `width:` symbols or `from_scene` | formula, substitution, result with units |
| a curve (p-values, a line shape, decay times) | `plot` (models `z_lineshape`, `decay_times`, `two_body_opening`, or inline numbers) | log axes for p-values |

## 3. Units

- **Natural units are the field's language.** Particle physicists set c = 1 and write masses,
  momenta and energies all in GeV ("the Higgs boson's mass is 125 GeV"). schu-video-generator's pictures write
  the full units (masses in GeV/c², momenta in GeV/c: the chart, the readouts, `kinematics`) so a
  student sees the dimensions. Either is right; **pick one per sentence** and, in a `calculation`
  in natural units, say so in a symbol's meaning ("photon 1, c = 1"). `particle_units` (info)
  notes a narration or screen that writes the same mass both ways.
- **Write values with units as text**: `"56.3 GeV"`, `"4.00 GeV"`, `"178.2 deg"`; `mass: pi+`
  takes the PDG value with its figures. A result's `unit: GeV` is checked against its dimension.
- **Avoid an SI intermediate.** A `calculation` whose outer square root has GeV² inside writes
  the argument in SI (kg² m⁴/s⁴) when it cannot keep the unit; compute m² first (`unit: GeV^2`),
  then `sqrt(m2)`, as the example does.
- **Lifetimes and widths** are the same fact (τ = ħ/Γ): the Higgs boson's 4.1 MeV width (the
  Standard Model prediction) is τ = 1.6 × 10⁻²² s. Say the one the screen shows.
- **Say numbers as the screen writes them**, rounded with "about": "one hundred and twenty-five
  GeV", "about a quarter of a percent", "one point six times ten to the minus twenty-two seconds".

## 4. Honesty

| what | the rule | how schu-video-generator helps |
|---|---|---|
| simulated data | always called simulated, on screen and in the narration | `mass_spectrum` labels its legend and caption "simulated data" (with the seed); the detector's label says "simulated event"; `simulated_label` flags "real data" said of them |
| the detector | schematic: generic sizes, no experiment's geometry or logo | the label "schematic detector"; say "a schematic detector" |
| sources and editions | name them: PDG 2024 (S. Navas et al., Review of Particle Physics, Phys. Rev. D 110, 030001 (2024)) for masses, widths, lifetimes, measured branching ratios; the LHC Higgs Cross Section Working Group's Yellow Report 4 (2016) for the Higgs boson's predicted branching ratios and width | the chart's source line, the branching caption ("a theory prediction, not a measurement"), `calculation` sources |
| theory vs measurement | the Higgs boson's width (4.1 MeV) and branching ratios are predictions; say "predicted" when it matters | the captions say so |
| local vs global significance | a `mass_spectrum` gives the **local** significance at the fitted mass; searching a wide mass range lowers it (the look-elsewhere effect, not included); say "local" | the readout and the note write "local" |
| expected vs observed | the readout's `expected: 5.3σ` is the Asimov median for the data so far; the note after the fit is the observed likelihood ratio of *this* sample | narrate the one you mean |
| what a p-value is | the chance that background alone fluctuates up this much — **not** the chance that the discovery is wrong ("99.99994 % sure" is wrong); 5σ ↔ p = 2.9 × 10⁻⁷, about once in 3.5 million | `significance_claim` |
| real history | quote only what is certain; no real event counts or significances on simulated pictures | the example states the 4 July 2012 announcement by ATLAS and CMS and "each about five sigma on its own" — nothing else |
| diagrams | schematic: lengths and angles carry no meaning; time direction stated | the time arrow; say "time runs left to right" once if the audience is new |

## 5. Pacing

- **One idea per beat, 10–25 words**, an action every few seconds: `highlight` on the particle
  named, `couplings` on "field", `vertex_rule` on "loop", `travel` on "in", `swap_channel` on the
  new boson, `highlight` of the event's particles on "showers", `grow` / `fit` / `annotate` on the
  spectrum, `annotate` on each σ of a p-value plot.
- **Let a spectrum fill.** Two beats of `grow` (`to: 12000`, then the rest) before the fit; the
  bump appears while the narration says "near one hundred and twenty-five GeV".
- **A chart is dense** (about 65 words on screen): reveal it in groups or hold it under a short
  narration; `max_words` warns, and that is expected for a full chart.
- **Calculations**: the formula on the word that names it, `substitute` on the values, `compute`
  on the result's first word. Two short calculations (m², then m) read better than one long one.
- **Kokoro at 0.85**: faster speeds put short beats over `narration_speed` (3.5 words/s).
- **9:16**: the chart stacks the bosons under the fermions; the detector's legend falls below the
  readable size (`legend: false` and let the narration say the signatures); spectra keep the
  fit box inside the plot. Lint the vertical variant too.

## 6. Common mistakes and the rule that catches each

| mistake | rule |
|---|---|
| a mass that is another particle's ("the W weighs 91 GeV") or off by a prefix | `particle_mass` |
| a charge or spin that is wrong ("the down quark has charge +2/3") | `particle_charge`, `particle_spin` (errors) |
| a lifetime, half-life or width said otherwise ("ten to the minus twenty-two seconds" for 1.6 × 10⁻²²) | `particle_lifetime` |
| a branching ratio said otherwise ("most Higgs bosons decay to two photons") | `branching_ratio` |
| "allowed" or "conserves …" said of a decay the checker forbids | `conservation_claim` |
| the wrong boson for an interaction ("a photon changes the quark's flavour", "gluons couple to electrons") | `feynman_boson` |
| a `kinematics` number, a decay length or a threshold said otherwise | `kinematics_number` |
| a signature the detector does not give ("photons leave tracks") | `detector_signature` |
| a significance the spectrum does not reach, or a p-value read as certainty | `significance_claim` |
| simulated data called real | `simulated_label` |
| GeV and GeV/c² mixed for one mass | `particle_units` (info) |
| a calculation's result said otherwise, wrong units, too many figures | `calc_numbers`, `calc_units`, `calc_sigfigs` |

Run `vidgen lint` in 16:9 and 9:16 before the final render. The particle rules read the config and
the narration (not the stills), so they are quick; negations and contrasts are left alone
("photons do not leave tracks", "it is not the chance of being wrong").

## 7. The pattern

```yaml
- id: mass
  type: calculation
  params:
    title: "The invariant mass of the two photons"
    symbols:
      - {name: pT1, value: "56.3 GeV", meaning: "photon 1, c = 1", source: "the event", tex: "p_{T1}"}
      - {name: pT2, value: "54.7 GeV", meaning: "photon 2, c = 1", source: "the event", tex: "p_{T2}"}
      - {name: deta, value: "1.00", meaning: "0.93 − (−0.07)", source: "the event", tex: "\\Delta\\eta"}
      - {name: dphi, value: "178.2 deg", meaning: "angle across the beam", source: "the event", tex: "\\Delta\\phi"}
    calculations:
      - {name: m2, expr: "2*pT1*pT2*(cosh(deta) - cos(dphi))", unit: GeV^2, meaning: "its square", symbol: "m_{\\gamma\\gamma}^2"}
      - {name: m, expr: "sqrt(m2)", unit: GeV, meaning: "invariant mass of the two photons", symbol: "m_{\\gamma\\gamma}"}
  beats:
    - text: "For photons, the invariant mass needs only their transverse momenta and the angles between them."
      actions: [{substitute: calc1, at: "@momenta"}]
    - text: "This event gives one hundred and twenty-five GeV."
      actions: [{compute: calc2, at: "@This"}]
- id: diphoton
  type: mass_spectrum
  params:
    title: "Many photon pairs: simulated data"
    channel: h_to_gammagamma
    seed: 13
  beats:
    - text: "We collect many photon pairs, here simulated, and histogram their mass."
      actions: [{grow: axes, to: 12000}]
    - text: "A small bump grows near one hundred and twenty-five GeV."
      actions: [{grow: axes}]
    - text: "A fit finds its mass. The local significance here is about five sigma."
      actions: [{fit: "fit:fit", at: "@fit"}, {annotate: "annotation:significance", at: "@significance"}]
```
