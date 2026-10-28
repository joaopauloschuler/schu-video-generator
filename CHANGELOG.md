# Changelog

The project and its pip distribution are `schu-video-generator`; the command and the Python
package are `vidgen`. The release notes of 0.2.0 (what changed from 0.1) are in `HANDOFF.md`
("Release notes: vidgen 0.2.0") and `DESIGN.md` §63. Step numbers refer to `tasklist.md`;
each step has a section in `HANDOFF.md` and its details in `DESIGN.md`.

## Unreleased (Steps 193–233)

### Orbital mechanics (Phase X, from Step 229)

- **The Solar System on a date** (Step 233). `date: 2020-06-01` places the planet presets (and
  the new `pluto`) where JPL's approximate elements (Standish, Table 1, valid 1800–2050; dates
  outside refused) put them that day, the panel showing the date as the clock runs; `event: {kind:
  opposition, of: Mars}` finds the next opposition / conjunction after it by root finding and
  draws the line the planets will stand on (Mars 2020-10-13); `radial: log` fits Mercury to Pluto
  in one picture with labelled rings and "distances compressed (log)"; `inset: true` adds the inner
  planets to scale beside a true-scale picture; `sizes: true` compares radii to scale side by side
  with the Sun's edge. The model: `vidgen.api.orbits` gains `julian_date`, `heliocentric`,
  `mean_elements`, `next_event`, `sidereal_period`, `planet_synodic_period`, `elongation`, `TABLE1`
  and more.
- **Compact orbit panels** (Step 233). The `orbit` scene's side panel now shows the time, the
  speed-up and the few values the scene is about (at most six rows in 16:9, five in 9:16, at a
  readable size); diagnostics such as ΔE/E, ΔL/L and a Jacobi constant's drift are left out unless
  asked for (`energy: true`, `panel: full`, or by name: `panel: [time, total_dv, phase]`;
  `panel: none`). `panel: full` restores the earlier panel.

- **Many bodies** (Step 232). `system: earth_moon | sun_earth | sun_jupiter` (or your own pair
  with a mass ratio `mu`): the circular restricted three-body problem integrated about the
  barycentre, seen in the inertial or the rotating frame (`view: rotating`; the actions
  `corotate` / `inertial` turn the view on a word), the Lagrange points L1–L5 computed for μ
  (`lagrange`), Routh's stability test, bodies placed `near: L4` with a `shift` (tadpoles,
  horseshoes, or a body leaving L4 above μ = 0.0385), the Jacobi constant and its drift, the
  zero-velocity curve; Sun–Earth L1 / L2 shown 1.50 / 1.51 million km from the Earth in a close-up
  (`center` with `extent`, an arrow to the off-plot Sun). `system: figure_eight` (three equal
  masses, Chenciner–Montgomery); `origin: barycentre` (binary stars on their two ellipses);
  `resonance: [Io, Europa, Ganymede]` with the Galilean moons as presets (period ratios, the
  Laplace angle 180°, conjunction lines as they happen); a body's `curvature` (the Moon's path
  always bends towards the Sun); `tides` (a schematic: the Moon's pull, the tidal arrows, two
  bulges, tidal locking). n-body panels show ΔL/L with ΔE/E; masses may be written `'2 Msun'`.
  The model: `vidgen.api.orbits` gains `lagrange_points`, `collinear_gamma`, `routh_stable`,
  `jacobi`, `zero_velocity_segments`, `integrate_restricted`, `figure_eight`, `conjunctions`,
  `laplace_angle`, `tidal_acceleration`, `equilibrium_tide` and more.

- **Manoeuvres and gravity assists** (Step 231). A body's `burns` (Δv prograde, retrograde,
  radial, normal… at a time or the next periapsis / apoapsis: the Δv arrow at the burn point, the
  orbit before faint and after drawn, a mission line in the panel); `transfer` — Hohmann (Δv₁, Δv₂,
  total, transfer time, the phase angle drawn live until the launch window, the synodic period),
  bi-elliptic, phasing — between circular coplanar orbits, with clear errors for eccentric or
  inclined orbits; `alongside: Earth` starts a spacecraft with its planet; `flyby` — a gravity
  assist in the planet's frame (asymptotes, v∞ in and out, the turning angle δ, the periapsis,
  the atmosphere) with the Sun-frame vector diagram (speed gained behind the planet, lost in
  front); the clock actions `burn` (a burn on its word), `flyby`, `pause`, `coast`, each stretch
  of the clock showing its own speed-up; a `calculation` takes the computed Δv, times and angles
  with `from_scene`. The model: `vidgen.api.orbits` gains burns and trajectories, `hohmann`,
  `bielliptic` (and its thresholds 11.94 / 15.58, computed), `plane_change`, `phasing`,
  `synodic_period`, `flyby`, `gravity_assist`. In 9:16 a long panel is set in two columns; a
  scale bar takes the corner the paths keep away from.

- **Kepler's laws and orbital speed** (Step 230). A body's `geometry` (the empty focus and the
  centre, a and b with their lengths, perihelion / aphelion — perigee / apogee around the Earth —
  with their distances), `sectors` (equal areas in equal times: each sector shaded as it is swept,
  its area computed and listed), `velocity` (arrows ∝ speed with a key, the vis-viva speed and
  its range); `cannonball` (Newton's cannon: shots from one point at increasing speeds, each
  classified by its energy as suborbital, circular, elliptical, parabolic or hyperbolic); the
  actions `sweep` and `launch` on a word, `reveal` / `highlight` of every overlay; the plot model
  `kepler_planets` for Kepler's third law on log axes. **Changed look of `orbit`:** the picture
  fills the frame's height (the axes' unit written once instead of two axis titles), labels never
  overlap (further out with a leader line when crowded), and a side panel beside the picture
  holds the readout and a legend of the bodies' periods.

- **The `orbit` scene type and the orbital model** (Step 229). Planets, moons, satellites and
  comets on Kepler orbits, moving in correct timing at one speed-up from the first beat to the
  scene's end (so equal areas in equal times show as they are), with conic orbits, fading trails,
  an equal-aspect frame in AU or km (or a scale bar), a readout of the simulated time and the
  speed-up, "sizes not to scale" when bodies are enlarged, a view that follows a body, and
  `dynamics: nbody` (mutual gravity on leapfrog or RK45, with the energy error). Bodies from
  presets (the planets on JPL's approximate J2000 elements, the Moon, an ISS-like orbit,
  geostationary, Halley), from elements with units (`a: "1.5 AU"`, `periapsis`, `altitude`, `i`,
  `raan`, `argp`, `nu`) or from a position and velocity; clear errors such as a periapsis inside
  the planet. The model is `vidgen.api.orbits` (no manim): Kepler's equation for every conic,
  elements ↔ state vectors, vis-viva, periods, energies, n-body runs.

### Science foundation: scientific charts and worked calculations (Phase W, from Step 222)

- **Review of Phase W: accuracy fixes** (Step 228). Checked against numpy / scipy
  (`tests/test_science_review.py`). **Changed results:** counts — a series with `y_err: sqrt`, or
  a curve fitted to a histogram — are fitted by Poisson maximum likelihood (weights from the fitted
  curve; √N weights from the data pulled a decay low: the example's λ 0.276 → 0.274 min⁻¹, its
  narration updated), and a count of 0 is no longer an error; a histogram with a number of bins
  no longer drops its smallest or largest value to round-off; RK45 samples come from its dense
  output (as scipy: far fewer steps, the same accuracy) with an absolute tolerance scaled to the
  model. **Units:** two readings in °C / °F cannot be added, and a difference of readings cannot
  be shown in °C (write changes in K). **Look:** normalized residual panels are symmetric and
  ticked at ±2 (points without bars); `aspect: equal` plots tick both axes with one step (square
  gridlines); a calculation leaving for the next one fades out faster. The lint also accepts a
  number said for an intermediate step of a calculation.

- **A science example, guide topic and cookbook; the PCR trace on the chart core** (Step 227).
  `examples/radioactive-decay` ("Half-life: how radioactive decay keeps time", about 2:52 with
  Kokoro): a live Monte Carlo of 1000 and 20 nuclei beside the exponential law, counts with √N
  error bars on a log axis with an exponential fit, its confidence band and residuals, the
  half-life worked out with its uncertainty, and carbon-14 dating; seeded data from
  `make_data.py`, a 9:16 variant. `vidgen guide science` (plot or chart, honest axes, error bars,
  fits, live models, units and significant figures, pacing, lint; the `biology` topic no longer
  answers to "science") and `docs/COOKBOOK-SCIENCE-CHARTS.md`; the gallery has a "Science charts"
  section. **Changed look:** a `calculation` keeps the units in a long substitution whenever they
  stay comfortably readable (on two lines, or one factor per line) instead of falling back to SI
  numbers, a block too tall for the frame shrinks its largest lines first, and a calculation's
  lines stay within 1.6 times each other's size (a big formula above a long substitution comes
  down towards it); the `dna_lab` PCR
  trace is drawn by the chart core: a horizontal "temperature (°C)" title, the three temperatures
  named by their stage on the axis ("denature 95") with gridlines, "cycle 1…3" under the cycles.
  New: `plotcore.layout_axes` (a panel from axes you built). The population, GWAS, cyclin and
  action-potential plots keep their drawing (DESIGN §97.12 says why).

- **Lint for numbers, units and plots** (Step 226). `vidgen lint` reads the numbers the narration
  and the screen say — in digits and in words ("eleven point two kilometres per second", "three
  point seven times ten to the minus nineteen joules", "one in a hundred and fifty", "three
  halves") — and compares them with what the `calculation` scenes compute: `calc_numbers` (a value
  that is not the result, rounding as written and "about" allowed), `calc_units` ("a speed of 30
  kilometres"; 30 m/s for 29.8 km/s, mg for µg) and `calc_sigfigs` (info: more significant
  figures than the inputs give). New plot rules: `plot_units` (an axis of a physical quantity
  without its unit), `plot_log` (error bars, fits or lines at or below zero on a log axis),
  `plot_errors` (error bars without a stated meaning, or called otherwise in the narration),
  `plot_series` (several series without legend or labels, placeholder names), `plot_truncated`
  (info: bars not starting at zero, also a `bar_chart` baseline), `plot_conserved` (a model's
  conserved energy drifting: use leapfrog or a smaller step) and `plot_fit_claims` ("a half-life
  of twelve days" when the fit gives 8.0 ± 0.1 d). `said_before_shown` / `unsaid_reveal` know the
  plot and calculation actions and targets. No new dependency.

- **Worked calculations with units** (Step 225). A new scene type `calculation` shows a symbol
  table (each value with its unit, its meaning and its source; constants such as `G`, `h`, `c`,
  `M_sun` with CODATA 2022 / SI 2019 / IAU values) and works each calculation step by step: the
  formula (TeX written from the expression), the values substituted with their units, the result
  in a box with the right significant figures — or as an exact fraction when every input is exact
  (2/3 × 1/25 × 1/4 = 1/150) — and the result converted into other units (m/s → km/s, J → eV,
  GeV/c² → kg). Later calculations use earlier results by name, and other scenes can too
  (`from_scene`). Units are checked: adding metres to seconds is refused with both dimensions
  explained. The actions `substitute`, `compute` and `convert` time the steps to words;
  `highlight: "symbol:G"` marks a symbol. The engine is `vidgen.api.quantities` (units,
  prefixes, °C / °F offsets, conversions, significant figures, exact fractions); no new
  dependency.

- **Live plots from simulations** (Step 224). A `plot` takes `models` that generate its data:
  differential equations written as safe expressions (`{x: v, v: "-k*x - c*v"}` with parameters,
  initial conditions and a time span) integrated by RK4, adaptive RK45 or the symplectic
  leapfrog (energy stays bounded on orbits and oscillators), recurrences (the logistic map,
  compound growth), seeded random walks and Poisson events (the same seed gives the same numbers
  everywhere), or a Python function registered with `vidgen.api.register_model`; derived
  quantities (an energy) and their drift when declared conserved. Their series grow over the beat
  with a head marker, an optional readout (`t = 3.20 s`, `x = 0.53 m`) and a fading trail for
  phase-space plots; panels on one model grow together; axes widen smoothly as the data reach
  their edge; histograms can fill as events arrive (a peak emerging from the background). The
  action `grow` times a growth to words (`to: 4` stops part-way), and `zoom` with `x` / `y`
  zooms a plot's axes to a region and back. Fits and annotations wait for the data. Errors name
  the problem: an unknown name in an equation (did you mean), a missing initial condition, a step
  too large, a solution that blows up, a stiff system. No new dependency.

- **Error bars, fits, histograms and annotations on `plot`** (Step 223). Series take error bars
  (`y_err` / `x_err`: a number, a column, a list, `{minus, plus}`, or `sqrt` for √N) with their
  meaning in the legend (`± SD`, `± SEM`, `95 % CI`, `min–max`); `fits` draw fitted curves —
  linear, polynomial, exponential, power law, logistic, Gaussian and Breit–Wigner peaks over a
  polynomial background, or your own expression with named parameters — with the parameters ±
  standard errors (`k = −0.0846 ± 0.0017 d⁻¹`), R², χ²/ν for weighted fits, confidence or
  prediction bands and a residual panel; series with `values` are histograms (Sturges,
  Freedman–Diaconis, Scott, one bin per integer, explicit edges; counts or density) with fitted
  normal, exponential or Poisson distributions; `annotations` (point labels, arrows, reference
  lines, shaded ranges, notes) find a place that covers no data and no other text. The actions
  `fit` and `annotate` put a fit or an annotation on a word. Fitting needs no new dependency
  (numpy; checked against scipy in the tests). Plot text is larger (phone-readable), the plot
  fills its area (axes end just past the data, a legend or fit box without room moves beside the
  figure), legend entries appear with their series, dashed series have dashed swatches, and a
  line no longer crosses an axis break.

- **The chart core and the `plot` scene** (Step 222). A new scene type `plot` draws line and
  point series from inline numbers or a CSV in the project (units read from the headers: `time
  (s)`, `E [MeV]`) on linear, log, symlog, reversed or broken axes, with tick labels in plain
  numbers, powers of ten (`distance (10⁶ km)`, `2.5 × 10⁻³`) or SI prefixes (`time (µs)`, `10
  kHz`), units in the axis titles, gridlines (with a log axis' minor ticks), a legend in a free
  corner, several panels sharing an axis, and an equal aspect for orbits and trajectories. Data
  an axis cannot show (a zero on a log axis, a value inside a break or past `max`), unknown
  columns (with did-you-mean) and mixed units are errors from `vidgen validate`. It is built on a
  chart core without manim (`vidgen.plotcore`: ticks, number formats, axes, CSV tables, the
  layout of multi-panel figures) and a thin drawing layer (`vidgen.plot_draw`), both exported by
  `vidgen.api`. Existing chart scenes are unchanged.

### Genetics (Phase V, from Step 213)

- **Review of Phase V** (Step 221). A scientific-accuracy pass over the presets, reference
  sequences, HGVS, CRISPR, the lab methods, population genetics, GWAS and the lint rules found no
  wrong data (CFTR's legacy numbering, c. + 132, is now documented). Pedigrees use the frame better
  (the chart spreads sideways, a legend column beside it in 16:9, numbers beside the symbols, the
  9:16 chart sized to the cards it shows), place the proband's P where it belongs to no other label,
  and state an exclusion exactly ("— excluded unless I-1 is non-penetrant (Xᵃ Y; very unusual)").
  Normal chromosomes in a 16:9 `karyotype` lie across the frame; `mutation` with few codons puts its
  card beside larger rows; gel labels no longer overlap lanes or ladder bands; a coat colour is
  drawn on a dog for Labradors (`cross` param `animal`, a neutral fur patch when no animal is
  named); `crispr` fits a 9:16 frame. Fixed for every scene: a multi-line text in a font with
  ligatures (the light_academic headings' "fi") no longer moves letters onto the next line.

- **Example, guide topic and cookbook** (Step 220). `examples/cystic-fibrosis`: "Cystic fibrosis:
  from a family to a diagnosis" (about 4 min with Kokoro narration, a 9:16 variant) — a pedigree
  with the modes of inheritance tested, a Punnett square of two carriers, the carrier probability
  2/3 and the risk 1/150, *CFTR* at 7q31.2, c.1521_1523del p.(Phe508del) on the real sequence, an
  NGS carrier test and the carrier frequency from the incidence. A guide topic `vidgen guide
  genetics` and `docs/COOKBOOK-GENETICS.md` (choosing, NSGC / ISCN / HGVS / HGNC notation, exact
  numbers, reading a pedigree aloud, a counselling tone, common mistakes and their lint rules); the
  gallery's Genetics section links both. `dna_lab` NGS reads a **deletion** too (`variant:
  "6_8del"`: gapped reads bridged by a line, the call from the reads spanning it), its reads may
  run past the reference's ends (even coverage up to the edges; **the reads of an existing
  `ngs` scene change**), its tiles drop their letters when they would touch and its call card
  names the verdict in its heading. Lint: `label_spacing` and `max_words` treat a lone character
  on a plate (a DNA base) as a tile, not a label or a word; `contrast` finds the backdrop of a
  narrow glyph (`I`, `1`) beside it; `genetics_hwe` reads "q, the frequency of disease alleles, is
  about one in fifty" as q, not as the incidence.

- **Accuracy lint for genetics** (Step 219). Seven `vidgen lint` rules compare the narration and
  on-screen text with what each genetics scene computes: `genetics_ratio` (a ratio or share the
  `cross` does not give: "a 3:1 ratio" for a dihybrid, "half the daughters affected" for a carrier
  mother), `genetics_pedigree` (a chart that does not fit its stated mode, as an error; a dominant
  trait skipping a generation without reduced penetrance; father-to-son transmission of an X-linked
  trait; carrier and risk probabilities against the chart), `genetics_linkage` (RF over 50 %,
  distances and RF against the map, linked loci called unlinked), `genetics_hwe` (carriers called
  q², q against the incidence, carriers against 2pq), `genetics_crispr` (the wrong PAM for the Cas,
  a cut not 3 bp upstream of the PAM, sticky ends for Cas9, the spacer length), `genetics_karyotype`
  (ISCN that does not parse or lists its changes out of order, "45,X is male", a condition the
  karyotype does not show) and `genetics_hgvs` (HGVS invalid or not the scene's variant, legacy
  numbering such as p.Glu6Val unannounced; `ΔF508` / `R553X` shorthand as info). `science_naming`
  and caption italics know the genes of the new scenes; the narration–picture rules know their
  actions and targets. No new findings on any example or the gallery.

- **Population genetics** (Step 218). A `population` scene type: Hardy–Weinberg worked step by step
  with exact numbers — p and q from genotype counts, genotype frequencies, p or the incidence of a
  recessive condition (1/2500 → q = 1/50, carriers 2pq = 49/1250 ≈ 1 in 25.5), p² + 2pq + q² with an
  inbreeding coefficient, and a chi-square test of HWE with df = 1 — beside the population drawn as
  dots by genotype; and seeded Wright–Fisher simulations — drift (replicate lines, fixation and loss),
  selection (fitnesses or s and h; the deterministic course with drifting lines), mutation,
  migration between two populations, a bottleneck and a founder effect with the heterozygosity
  against H₀ Π(1 − 1/2N). A `gwas` scene type: a Manhattan plot (22 autosomes and X, the 5 × 10⁻⁸ and
  1 × 10⁻⁵ lines, peaks labelled), a QQ plot with λ_GC and a regional plot coloured by r², from a CSV,
  inline variants or a seeded synthetic study labelled "simulated data". New actions `simulate`,
  `resample`, `regional`.

- **Molecular genetics** (Step 217). A `mutation` scene type: a variant applied to a real coding
  sequence (HBB, CFTR, GJB2 reference windows with their exons and transcripts, your own sequence,
  or a gene written as in a `molecule` scene) and worked out with the genetic code — the reference
  codons with their amino acids and the variant row made from them (substitution, deletion,
  duplication, insertion, a frameshift regrouping every later codon to its premature stop,
  splice-site changes with the predicted mRNA) —, with HGVS notation generated and checked against
  the sequence (the 3′ rule, intronic positions, nonsense-mediated decay; `c.20A>T p.(Glu7Val)`,
  `c.1521_1523del p.(Phe508del)`, `c.35del p.(Gly12Valfs*2)`, `c.1657C>T p.(Arg553*)`, legacy
  names). A `crispr` scene type: guides found in a target (PAM `NGG` / `NNGRRT` right after the
  protospacer's 3′ end), the sgRNA's spacer checked, the R-loop, the blunt cut 3 bp upstream of the
  PAM, and the repair — NHEJ with a small indel or HDR from a donor — written in HGVS with its
  protein change on a coding target. A `dna_lab` scene type with `method: pcr | gel | sanger | ngs`:
  primers checked against the template with the product measured, a temperature trace and 2ⁿ /
  2ⁿ − 2n copies from the simulated strands; an agarose gel with a ladder and log-linear migration
  with the sizes read off; a Sanger chromatogram with called bases and a heterozygote; NGS reads
  with coverage and a variant call. New actions `mutate`, `scan`, `cleave`, `repair`, `run`.

- **Chromosomes** (Step 216). A `linkage_map` scene type: the heterozygote's homologue pair with
  its alleles (coupling or repulsion), crossing over between non-sister chromatids giving
  recombinant chromatids, and two- or three-point test crosses worked out from offspring counts
  step by step — parental and double-crossover classes, gene order, interval distances in cM
  (RF × 100, Haldane or Kosambi), expected and observed double crossovers, coefficient of
  coincidence and interference, the map; or loci at map positions with `measure`. A `karyotype`
  scene type: ISCN notation parsed and checked (47,XX,+21; 45,X; 47,XXY; del, dup, inv,
  t(9;22)(q34;q11.2), rob(14;21)(q10;q10)) and drawn as a karyogram in the Denver groups with
  schematic G-banded ideograms (true relative lengths and centromeres) and the change highlighted,
  or as ideograms with structural changes played as edits; a card reads the notation. `cell_cycle`
  meiosis takes `nondisjunction: {division: I | II, pair}`: aneuploid gametes labelled with their
  shares and the zygotes they make. New actions `cross_over`, `measure`, `rearrange`. The committed
  gallery's budget is 13 MB (each entry at most 0.36 MB).

- **A `pedigree` scene type** (Step 215): a family chart in standard human pedigree nomenclature
  (NSGC: squares, circles, diamonds; affected filled, carriers dotted or half-shaded, deceased
  struck, proband arrow with P, consanguinity double line, MZ / DZ twins, adoption brackets,
  miscarriage triangle, a proposed child dashed with ?) laid out by generation (Roman numerals,
  individuals numbered left to right, sibships in birth order, partners beside), written as one
  line per person (`"II-3: female affected of I-1 + I-2"`) or mappings. Its genetics are worked
  out exactly: which modes of inheritance fit (AD, AR, XD, XR, Y-linked, mitochondrial; each
  excluded one with its reason, e.g. father-to-son transmission), reduced penetrance, the
  genotypes the chart forces (obligate carriers), carrier probabilities by Bayes' rule (2/3 for an
  unaffected sibling under AR) and the risk for a proposed child with its factors (2/3 × 1/25 ×
  1/4 = 1/150). The actions `deduce`, `analyse` and `risk` put each step on a word; `reveal`
  brings in generations or people. Validated with the reason (two fathers, a cycle, twins who are
  not siblings, a male carrier under X-linked inheritance).
- **A `cross` scene type** (Step 214): a genetic cross worked out exactly and drawn — the parents
  with their homologous chromosomes, genotypes in standard notation and phenotype pictures (peas,
  flowers, flies, coats, blood groups…), their gametes flying out to a Punnett square's headers
  (each allele in its homologue's colour; recombinants of linked genes ringed, with their exact
  frequencies), the square filling cell by cell or row by row (up to 8 × 8; a branch, forked-line,
  diagram for larger crosses), and the offspring counted into genotype and phenotype classes —
  exact fractions, percentages, whole-number ratios (9 : 3 : 3 : 1, 9 : 3 : 4, 2 : 1 with the
  lethal class crossed out; X-linked crosses split by sex). `P: [RRYY, rryy]` shows P → F1 → F2,
  `kind: test` makes the tester, `kind: reciprocal` swaps the sexes; `observed` counts add a
  chi-square test (χ², df, p, critical value, verdict). The actions `form_gametes`, `fill`,
  `count`, `ratio` and `chi_square` put each step on a word; without them the scene plays itself.
  16:9 and 9:16; validated with the reason (alleles, sexes, phase, counts for classes that do not
  exist, a cell filled twice).
- **The genetics model** (Step 213, no scene type yet; `vidgen.genetics`, also in `vidgen.api`):
  loci and alleles in standard notation (`A`/`a`, `I^A` shown as Iᴬ, `c^{ch}`, wild type `w^+` or
  `+`, X-linked alleles written on their chromosome, `X^H X^h`, `X^h Y`); dominance — complete,
  incomplete, codominant, or a hierarchy of multiple alleles such as `"I^A = I^B > i"`; lethal
  alleles; penetrance and expressivity; epistasis (recessive 9:3:4, dominant 12:3:1, suppression
  13:3, duplicate 15:1, complementary 9:7, cumulative 9:6:1); autosomal, X-, Y-linked and
  mitochondrial loci; linkage with recombination frequencies (coupling / repulsion written
  `AB/ab` / `Ab/aB`, interference for three loci, no crossing over in Drosophila males). An exact
  cross engine computes gametes and offspring genotype and phenotype distributions as fractions,
  with test and reciprocal crosses; 15 presets of textbook crosses (`abo`, `labrador`,
  `drosophila_white`, `drosophila_b_vg`…). Mistakes are refused with the reason: an allele not
  defined for its locus (did-you-mean), a female with a Y, an X-linked allele written without its
  X, linked loci without their phase, a recombination frequency above 0.5. The scene types
  (`cross`, `pedigree`, `karyotype`, `linkage_map`, `mutation`, `crispr`, `dna_lab`,
  `population`, `gwas`) follow in Steps 214–218; plan in `DESIGN.md` §96.

### Cell biology in physical scale (Phase U, from Step 202)

- **A `cell` scene type** (Step 202): a cross-section of an animal cell at textbook sizes in µm
  — nucleus with its two membranes 30 nm apart, nuclear pores and a nucleolus, rough ER studded
  with ribosomes, smooth ER, a Golgi stack (cis face towards the nucleus), the centrosome,
  mitochondria with cristae, lysosomes, peroxisomes, vesicles and 25 nm ribosomes
  (`contents: typical`), plus your own `objects` (`kind`, `at` in µm, `in:` a compartment, `on:`
  a membrane, `count`). Every place is checked by `vidgen validate`: a ribosome in the
  nucleoplasm, a mitochondrion inside the nucleus or a ribosome on the Golgi is refused with the
  textbook reason, and typos get a did-you-mean.
- **A camera in µm** with an automatic **scale bar**: the `zoom_to` action moves between levels —
  tissue, cell, organelle, molecular complex (one ribosome on the ER, a nuclear pore) — on a
  spoken word (`at: "@ribosome"`), zooming at an even pace on a log scale and out on the way
  between far places; **level of detail** switches as things grow on screen (double membranes,
  cristae, nuclear pores, ribosome subunits, 5 nm lipid bilayers). Labels and the scale bar keep
  their size on screen, in 16:9 and 9:16. See `docs/CONFIG.md`, `cell`.
- **The structure library** (Step 203): accurate morphology at every zoom — the nuclear envelope
  continuous with the rough ER, pores with spokes and baskets, nucleolus parts and
  heterochromatin; a smooth-ER tubule network; Golgi cis / medial / trans cisternae with rims and
  buds; mitochondria with crista junctions; early and late (multivesicular) endosomes; clathrin,
  COPI and COPII coated vesicles; centrioles with nine triplets. **Plant cells** (`cell: plant`:
  wall with middle lamella, plasmodesmata, central vacuole, chloroplasts with grana and stroma
  lamellae) and **bacteria** (`cell: bacterium`, Gram-negative or positive, capsule, nucleoid, 70S
  ribosomes, plasmids, flagella, pili). The **cytoskeleton** (microtubules with − and + ends from
  the centrosome, actin cortex and stress fibres, intermediate filaments) and **motors**
  (kinesin, dynein, myosin, with cargo). Bilayer close-ups with phospholipids, cholesterol,
  glycolipids, glycocalyx and a lipid raft; `style: surface` draws things whole, seen from
  outside. Each `zoom_to` view names the parts it shows (`labels:`); a dim during a zoom keeps
  its opacity; the scale bar has a text at any depth.
- **Molecules and notation** (Step 204): a **`molecule` scene type** for close-ups in nm — B-DNA
  with antiparallel strands, 5′/3′ ends, A–T / G–C base pairs and major / minor grooves; mRNA
  (cap, codons, poly(A)), tRNA (cloverleaf or L, anticodon checked against the genetic code),
  rRNA; the nucleosome (147 bp, 1.65 turns, histone marks such as H3K27ac checked against the
  histone sequences) and chromatin; proteins with domains, kinases, phosphatases, G proteins,
  GPCRs, RTKs, gated ion channels, carriers (uniport / symport / antiport), the Na⁺/K⁺ pump and
  ATP synthase in a membrane drawn between its two compartments; ATP, GTP, cAMP, Pᵢ, glucose,
  ions — and the same molecules as `cell` objects (`{kind: atp_synthase, on: mitochondria}` lines
  the cristae). Orientations and places are checked (*ATP synthase F₁ must face the mitochondrial
  matrix*); gene symbols are italic and checked per species (*TP53*, *Trp53*, *CDC28*), proteins
  roman; P / Ub / Ac / Me markers on the residues they go on; charges typeset (Ca²⁺, HCO₃⁻).
- Step 203's zoomed views now point every label at its part (the matrix beside a crista, the
  glycocalyx outside the bilayer), stroma lamellae join grana at their margins, and a ring of
  smooth-ER tubules is no longer drawn filled.
- **Transport and membrane processes as actions** (Step 205). In a `molecule` scene: `solutes`
  (particles at their concentrations, typical mammalian values by default), `potential` (a live
  Vₘ readout and the membrane's charges), concentration bars; `set_state` morphs a molecule
  (a channel opens or inactivates, a carrier turns through its occluded state, the Na⁺/K⁺ pump
  goes E1 → E1P → E2P → E2 with its phosphate shown); `transport` runs a channel (ions one by one
  down their electrochemical gradient, only its own ion), a carrier's alternating access
  (`transporter: sglt1`, `ncx`, `glut1`…), the pump's Post–Albers cycle with ATP → ADP + Pᵢ, H⁺
  pumps (P- and V-type), ABC transporters and aquaporins; `diffuse` (random walks with net flux
  down the gradient), `osmosis` and `action_potential` (channels in step with a trace from −70 to
  +35 and −80 mV in an inset plot). In a `cell` scene: `motor_walk` (kinesin's 8 nm steps to the +
  end, dynein's to the − end, carrying cargo), clathrin-mediated `endocytosis` (coated pit, dynamin
  scission, uncoating) and `exocytosis` (SNARE docking, fusion pore, cargo release). The rules
  come with reasons: *Na⁺ cannot pass a K⁺ channel*, *an antiporter moves its solutes opposite
  ways*, *active transport needs an energy source: ATP or an ion gradient*, *kinesin-1 walks
  towards a microtubule's + end*; states are replayed beat by beat by `vidgen validate`. New
  molecules `h_atpase`, `abc_transporter`, `aquaporin`, `water`, `o2`, `co2`, `drug`. Lipids leave
  room for membrane proteins in cell close-ups, and several membrane proteins in a tall frame go on
  membrane rows.
- **Gene expression as actions** (Step 206). A `gene:` param — a coding-strand `sequence` with
  intron spans, a `protein`, or generated from `codons` and a `seed` (TATA box, Kozak AUG, GU…A…AG
  introns, AAUAAA; a bacterium: −35/−10, Shine–Dalgarno, terminator). In a `molecule` scene, a
  close-up with every base and amino acid written: `transcribe` (GTFs and RNA polymerase II at the
  promoter, a ~13 bp bubble, the template read 3′→5′, an 8 bp RNA–DNA hybrid), `cap`, `splice`
  (snRNPs, the branch A, the lariat, EJCs), `polyadenylate`, `export` through a nuclear pore,
  `translate` (scanning to the AUG, A/P/E sites, codon–anticodon pairing with wobble and
  inosine, the chain growing N→C through the tunnel, eRF1 at the stop codon, ribosome
  recycling), `target_er` (SRP, its receptor, Sec61, signal peptidase), `glycosylate` (OST,
  Glc₃Man₉GlcNAc₂ in SNFG symbols) and `fold` (Hsp70, chaperonin, BiP, calnexin). In a `cell`
  scene the camera follows the products: `transcribe`, `export`, `translate` (free polysomes or
  the rough ER), `to_golgi` (COPII, cis → trans) and `secrete` (to the outside, the membrane or a
  lysosome). The order is checked by `vidgen validate` with reasons (*only proteins made into the
  ER enter the secretory pathway*).
- **Signalling pathways** (Step 207): a `pathway` scene type in SBGN-inspired notation — proteins,
  complexes, second messengers, genes (italic) and outcomes, with their states (GDP / GTP, pS133);
  arcs that activate (arrow), inhibit (T-bar), catalyse (circle), (de)phosphorylate (P), bind,
  translocate into the nucleus, regulate transcription — laid out by itself in compartment bands
  (extracellular space, plasma membrane, cytosol, ER, mitochondrion, nucleus: columns in 16:9, rows
  in 9:16), routes never crossing a node, the nuclear envelope with pores where arcs pass. Three
  templates checked against the textbook account: `gpcr_camp_pka`, `rtk_ras_mapk`, `pi3k_akt`
  (changed with `nodes`, `edges`, `remove`). Actions: `signal` (wave by wave: GDP → GTP, marks
  appear; an inhibitor of an inhibitor turns its target on), `inhibit`, `knockout` and `drug` (the
  effects downstream computed from the graph, ↑ / ↓ on each node that changes; known drugs checked
  against their targets), `amplify`, and `focus` on nodes. `vidgen validate` refuses unknown nodes,
  arcs against declared effects (a GAP activating Ras), impossible compartments (a gene outside the
  nucleus, a transcription factor in the cytosol on its gene) and names in the wrong case for the
  species, and warns about loops not marked `feedback`.
- **Cell cycle, division and energy** (Step 208): a `cell_cycle` scene type — the cycle as a ring
  (G1, S, G2, M with its stages, the restriction point, G0) with the G1/S, G2/M and spindle
  checkpoints and the cyclin–CDK levels (D–CDK4/6, E–CDK2, A–CDK2, B–CDK1) under a "now" marker;
  mitosis (2n = 2–8, homologues coloured, sisters joined at the centromere; `cell: plant` with a
  cell plate) and meiosis (synapsis, chiasmata with exchanged segments, independent assortment,
  four haploid recombinant cells) with captions and counts. A `metabolism` scene type —
  glycolysis (investment and payoff phases, net 2 ATP and 2 NADH; `link: true` adds pyruvate
  dehydrogenase), the citric acid cycle as a ring (3 NADH, FADH₂, GTP, 2 CO₂), the respiratory
  chain (I–IV, Q, cytochrome c, protons into the intermembrane space, ATP synthase) and the light
  reactions (PSII, PQ, b₆f, PC, PSI, Fd, FNR → NADPH), with tallies. Actions: `advance` (round the
  cycle, through a division's stages, along a pathway, electrons and protons down a chain, the
  gradient through ATP synthase) and `checkpoint` (pass or arrest with its cause; regulators lit
  in order). `vidgen validate` refuses wrong counts after meiosis (`expect`), G0 after R, passing
  an arrested checkpoint, a chain in the wrong membrane and protons pumped the wrong way.
- **Scientific accuracy lint and references** (Step 209): seven `vidgen lint` rules read the
  config and the narration — `science_scale` (a `cell` with a scale bar drawing something far
  outside its textbook size; new `not_to_scale: true` shows a "not to scale" note instead),
  `science_location` ("glycolysis in the mitochondria", "ribosomes in the nucleus" while the
  scene shows them in the cytosol), `science_direction` (RNA made 3′→5′, proteins C→N, kinesin to
  the minus end, protons pumped into the matrix), `science_energy` (active transport through a
  channel, or with no energy source shown), `science_naming` (mouse *Trp53* gene vs TRP53
  protein, the wrong case, a gene label without italics), `science_pathway` (narration against an
  arc's effect) and `science_counts` (net 2 ATP from glycolysis, 3 NADH per turn, 3 Na⁺ / 2 K⁺ per
  pump cycle…), each with the textbook fix; 0 findings on the examples. `said_before_shown` knows
  the cell-biology actions and targets. Scenes take **`references:`** (`{label, doi | pmid | isbn |
  url}`, formats checked offline) and `figure_credit:`; beats `cite:` them; they show as small
  citations (`citations: {show: footer | marker | card | none}`, numbered across the video) and
  as a numbered list in `<output>_chapters.txt`.
- **Example, guide, cookbook and gallery** (Step 210): `examples/gene-to-secreted-protein`, "From
  gene to secreted protein" (about 3:34 with Kokoro): α1-antitrypsin from its gene in a liver
  cell to the blood — a zoom into the nucleus, transcription, capping, splicing,
  polyadenylation, export, translation, SRP targeting, N-glycosylation and calnexin up close, the
  route through the Golgi to secretion across the cell, exocytosis and the IL-6–STAT3 pathway;
  references, concept colours, the `discovery` bed, a 9:16 variant. A guide topic (`vidgen guide
  biology`: choosing the scene, accuracy, naming, references, pacing) and
  `docs/COOKBOOK-CELL-BIOLOGY.md`. The scene gallery has one **Cell biology** section with the five
  types and five showcases (a plant cell, the sodium pump, a MEK inhibitor, mitosis, the
  respiratory chain); gallery stills are now palette PNGs (about 40 % of their size, the room for
  the showcases). Fixes found on the way: a cell route's transcription caption no longer mentions
  vidgen's molecule scene; a zoomed `cell` view and a gene close-up no longer report their cropped
  world as `off_frame`; the close-up's "schematic: not to scale" is at the readable size, in the
  safe area and clear of the protein's readout in 9:16.
- **Review of Phase U** (Step 211): drawings use the frame better — molecule scenes put three or
  more membrane proteins on rows when that frames them larger (also beside a plot in 16:9), and
  in 9:16 the action-potential plot spans the panel above the concentrations; a gene close-up in
  9:16 shows 15 slots across (was 18) and takes a tall frame's layout even when its view is wider
  than tall (a 36-slot strip before); a vesicle near the plasma membrane is framed with the
  membrane it fuses with; pathways grow up to 1.9× and spread their ranks to use the height;
  glycolysis grows to fill. Step captions are never below the readable size and are their
  first clause in 9:16 (`notes: auto | full | short | false`). `exocytosis` names generic
  v-/t-SNAREs by default, `snares: constitutive` (a VAMP, syntaxin-4, SNAP-23) or `neuronal`
  (synaptobrevin/VAMP2, syntaxin-1, SNAP-25, Ca²⁺ on synaptotagmin); the example uses the
  constitutive set with its captions on. The captions overlay sets the gene symbols the video
  declares in italics (`genes: true`). Enzyme names in `metabolism` are roman (proteins).
  Calnexin is anchored in the ER membrane by a stalk; ribosomal subunits part in the cytosol on
  the ER; Sec61 is named beside the channel; ion channels are named by their ion (Na⁺ channel);
  overlapping labels fixed (band names in 16:9 pathways, side names of membrane rows, the light
  reactions' P side in 9:16, leader lines of label rows in 9:16); cell-scene products travel on
  gentle curves; a motor's cargo vesicle is kept off the organelles. `scenes/molecule.py` is
  split (the process runtime in `scenes/molecule_runtime.py`).

### vidgen studio: a music workstation for people (Phase T)

- **`vidgen studio [PROJECT] [--port N] [--no-browser] [--clean]`** (Steps 193–200) opens a
  small web app on 127.0.0.1 in your browser, offline, with no new dependency: load any of the
  17 built-in beds as an editable score file and change it with controls (key, tempo, seed and
  chords; sections dragged, looped and edited; tracks with mute / solo, volume, pan, steps
  text; an inspector with every instrument's settings as sliders, effects as chips, per-section
  changes and a step grid) or by typing the YAML; problems show inline with the command line's
  did-you-mean messages while the last good render keeps playing. The sound is always vidgen's
  own renderer: an edit renders only the tracks it changes and plays on from the same moment,
  also under the narration sample. See `docs/CONFIG.md`, "Music studio".
- **Check, versions, A/B, export** (Step 197): `vidgen music check` after each render (verdict,
  spectrogram with sections, advice with **Apply** where the fix is mechanical); every change is
  a version (undo / redo, rename, star, branches); A/B against the original or any version at
  the same moment and level; export YAML / WAV / MP3 or save into `assets/music/`.
- **Listening notes and "Ask an agent"** (Step 198): pin notes on the timeline while listening;
  an AI agent answers them through new MCP tools (`studio_sessions`, `studio_read`,
  `studio_check`, `studio_propose`) with a new version and one line per note, which you A/B and
  keep or discard; or copy the prompt into any chat assistant; or (optional, paid) OpenRouter.
- **Variations** (Step 199): four deterministic siblings of a version — harmony, pattern, mix,
  energy — rendered and checked side by side; play, keep, "more like this", shuffle; MCP
  `studio_variations`.
- **Polish** (Step 200): keyboard shortcuts (Space, N, L, M / S, V, Ctrl+Z / Ctrl+Shift+Z, ? for
  the list), tabs for the inspector, score file and notes in medium and narrow windows, a light
  theme checked for WCAG AA contrast, a first-run hint, a clear message (and automatic
  reconnection) when the studio server stops, the open variations and the last hand-off shown
  again after a reload, every variation batch listed to come back to, and a disk rule for old
  renders and exports (versions, notes and checks are never removed) with **Clean up** and
  `vidgen studio --clean`. The Listen page and the README link to the studio; the author guide
  tells agents when to suggest it; `docs/COOKBOOK-MUSIC.md` §7 walks through a session.
- **Review** (Step 201): hardened against hostile requests (request lengths, numbers, names
  with a trailing newline or other scripts' digits, Windows device names when saving, YAML
  aliases that expand to millions of values, a session folder linked elsewhere); OpenRouter is
  called only with the person's confirmation; edits of pieces at most tempos render 2–3 times
  faster with a third less memory (the same 16-bit audio as a video's); 5-minute pieces no
  longer run out of memory; exports are at most 10 minutes (was 30, which ran out of memory);
  `vidgen studio --clean` leaves a running studio's open session alone.
- Compatibility: additive. The beds, their templates, existing projects' mixes and every
  existing command are unchanged.

## 0.3.0 (Steps 61–192)

0.2.0 made narrated explainer videos that an AI agent can check and fix by itself. 0.3.0 adds
**cartoons**: original characters who talk with lip sync, move, act and react on drawn stages,
indoors and outdoors, with weather, props, vehicles, sound and music, written as YAML or as a
screenplay. It also adds two narration providers (OpenRouter, and Kokoro running free on your
own computer), OpenRouter pictures including SVG, an `output/` folder and `--jobs auto`; a
cartoon host beside any explainer scene, lines spoken with feeling, drafts and animatics,
ready-made sets, drawing styles, word-level readback flags and dubbing, music composed for
each video and played with real instruments, side-view platform stories (levels written as
small maps, planned walks and jumps, keys, doors, coins and friendly blockers), and a
presentation toolkit for explainers and coding Shorts (actions on a spoken word, one colour per
concept, code that morphs, a terminal, function plots and geometry, charts that change, and a
lint check of narration against the picture), and isometric story places (a village or a room
written as a small map, seen from above, where the cut-out characters walk round what is in the
way, hand things about, open doors and light lamps).

0.3.0 was prepared in Step 132 but never tagged or published, so the work of Steps 133–170
(Phases M, N, O and P in `tasklist.md`, Step 165 and Phase Q) is part of this release rather than an "Unreleased" section.

### Behaviour changes and possible breaks

Changes that affect projects made with 0.2.0:

- **Videos go to `output/`** (Step 66): the MP4, `.srt`, `_chapters.txt` and thumbnail are
  written to `<project>/output/`, not the project folder. Set `output_dir:` or pass
  `--output-dir` to choose another folder. An MP4 left in the project folder by 0.2.0 is not
  found by `export` or `slides`: render again, or pass `--output-dir <project folder>` (the
  flag is relative to the current folder).
- **ffmpeg 4.4 or newer** (Step 64). Crossfades, pushes and wipes now work on ffmpeg 7.0 / 7.1
  (they failed with "frame rate 1/0 is invalid"). With an older ffmpeg, the error names the
  version.
- **`[laugh]`, `[gasp]`, `[sigh]`, `[hmm]`, `[giggle]`, `[groan]` in a beat's text** are now
  voice sounds (Step 99): they are spoken or played as sounds and left out of captions. Before,
  they were read out as text. Such beats get new audio hashes. Other brackets stay as text.
- **`*word*` in a beat's text** marks emphasis (Steps 90–91): the asterisks are removed before
  TTS, captions and readback. Beats with asterisks get new audio hashes. Other beats keep
  theirs.
- **The first render after upgrading renders every scene again**: the scene cache key includes
  the vidgen version.
- **`--jobs` accepts `auto`** (Step 117). A bad value now gives the error `invalid value: 'x'
  (a whole number, or auto)` instead of argparse's message.
- **A Kokoro voice of another language is dubbed** (Step 143): in a video (or variant) whose
  `language:` is not the Kokoro voice's, vidgen now picks a Kokoro voice of the video's language
  of the same kind (female / male) instead of reading the text with the wrong pronunciation and
  only warning. `vidgen validate` prints the choice (`dub [pt]: ...`). Write `lang:` on the voice
  to keep it on purpose, or `dub: {LANG: VOICE}` to choose. Those beats get new audio.
- **New lint warnings** (Steps 157, 163): `concept_colors` (more than 5 concept colours, a
  concept colour hard to read on the background, a term coloured otherwise by a scene setting;
  only with `terms:`) and `said_before_shown` (the narration names a label on screen more than
  1.5 s before it appears). `vidgen lint --fail-on warning` may now fail on a project that passed:
  show the label on the word (`{reveal: ..., at: "@word"}`), or set
  `lint.rules.said_before_shown: {severity: off}`.
- **Built-in pronunciation entries** (Step 165): vidgen now respells some words for some voices
  in every project (`vidgen list-pronunciation` lists them): Kokoro's English voices say `README`
  as `readme`, `JSON` as `Jason`, `YAML` as `yammel`, `ReLU` as `ray loo` and more, and its
  American voices `epoch` as `E pock`. The audio hash covers the spoken text, so **existing Kokoro
  audio of beats with these words becomes stale**: `vidgen validate` counts them in `audio:` and
  prints `pronounce: built-in kokoro-en-us changes N beat(s): ...`; `vidgen tts` regenerates only
  those beats. To keep the old audio, set `pronunciation_defaults: false` or drop an entry with
  `term: null`. A project entry for the same term wins, so projects that already respell a word
  keep their audio. ElevenLabs and OpenRouter videos are unchanged (no lists for them yet).
- **Readback transcripts** (Step 141): `vidgen readback` keeps faster-whisper's word
  probabilities in its cache; a cached faster-whisper transcript without them is transcribed
  once more (local, free). Audio for faster-whisper is decoded with the ffmpeg executable.

Cartoon behaviour that changed during the 0.3.0 cycle (cartoons are new in 0.3.0, so this
matters only for projects made with development builds between Steps 67 and 131):

- **Default ambience beds** (Step 128): `ambience: true` by default. Outdoor stages in daylight
  get birdsong, rooms get a quiet room tone, doors creak instead of whooshing, and boats, pours
  and wet steps splash. To keep only the rain and fire beds, set `ambience: false` at the top
  level. `foley: false` turns off all of these sounds.
- **Generated characters' legs** (Step 92): `legs` is split into `leg_left` / `leg_right`
  (with `_lower` shins), and arms gained `arm_left_lower` / `arm_right_lower`. On a generated
  character, a pose of your own with `legs:` does nothing (validate warns) and a `NAME.legs`
  keyframe target is an unknown part. SVG characters may still use one `legs` piece. In an SVG,
  `id="arm_left_lower"` now names a part, not a shape of `arm_left`.
- **Interrupt timing** (Step 102 follow-up): `interrupt: true` without `overlap` now starts 70 %
  of the way into the earlier line's last word (0.2 s before its end without word timings),
  not 0.5 s before the end. It no longer cuts a whole word. Lint `talked_over` reports
  interrupts that cut words.
- **`auto_direct` adds effect symbols** (Step 107) such as `!` and `?` on strong expression
  changes. Use `auto_direct: {effects: false}` to turn them off.
- **Motion effects** (Step 108): with `cartoon_motion: lively` (the default) or `calm`, jumps
  land in dust (impact stars on hard landings), and fast walks, throws and blown props get
  speed lines. Turn them off with `motion_effects: false` or `cartoon_motion: none`.
- **Soft shadows on by default** (Step 97) under characters and props. Use `shadows: false` to
  turn them off.
- **Stage fades** (Steps 116a, 127): a stage fades in, and then out, as one picture instead of
  each thing on its own. Nothing behind another thing shows through during the fade. The first
  and last second of every stage scene look different from before.
- **Smaller seats** (Step 102): chair, box and rock are drawn lower (0.26 / 0.155 / 0.155 of a
  character), and a seated character's hips rest on the seat.
- **Reframing** (Step 96): a stage whose characters do not fit in one view pans to the speaker
  on its own (in 9:16 also laid out at 16:9 width). Set `reframe: none` to stop this.
- **Close-ups by `auto_direct`** (Step 95) are now `shot: closeup` cuts, not 0.03 s zooms.
- **Wind is stronger at `windy` and above** (Step 104). Rain on a stage lands on the ground
  with splashes and has a rain sound bed (Step 105).
- **`vidgen screenplay`** (Steps 113, 115, 130): it now picks from 11 looks (the first six as
  before), then random looks that contrast well. An exit's edge is written as `to` (it was
  `side`, which validate refused). Manner words that name a feeling (`(excited)`,
  `(whispering)`) also set the line's `emotion` (Step 135), so those lines get new audio; a
  `set:` line naming `bench`, `fence`, `log` and the other new outdoor props now places them
  instead of writing a `# TODO` (Step 139).
- **A beat ends on its planned frame** (Step 191): when a beat's narration and pad came to half a
  frame, a scene could run one frame longer or shorter than the video plan, and every caption
  and timed overlay after it was off by that much (2–3 frames by the end of a video, with a
  render warning). Such scenes are now a frame shorter or longer than before, as planned.

### Cartoons: characters

- A character model of named vector parts with pivots (67); a parametric generator with body
  shapes, heads, hair, eyes, noses and accessories (68); imported SVG characters split by `id`
  (69).
- Poses and expressions with eased part-by-part changes, plus poses of your own (70). Later
  steps added more expressions: `laughing`, `blushing`, `tongue_out`, `crying`, `dizzy`,
  `frightened` (125).
- Lip sync from visemes timed by the stored word timings (71); blinking and idle motion (72).
- Arms and legs that bend, with a two-bone solver (92), and a front view (111).
- Bodies, outfits, patterns, shoes, hair, beards and accessories (113). Original animal
  species: cat, dog, bird, bear, rabbit, mouse (114); fox, owl, frog, turtle, penguin (123).
  Robots and costume pieces (124).
- `vidgen cast --random N` writes a cast whose characters look clearly different from each
  other; lint `look_alike` warns when two characters look too alike (115).
- `vidgen character` and `vidgen character-sheet` (also over MCP) show every pose, expression
  and mouth shape (68, 83).

### Cartoons: stages, sets and props

- The `stage` scene type: a background, a ground, marks, depth (73); parallax layers and a
  camera that can `pan`, `zoom` and `follow` (74); shots `wide` / `two_shot` / `over_shoulder` /
  `closeup` / `medium` (95); vertical videos that follow the speaker (96).
- Props drawn from primitives (75), and SVG props. More props followed: basket, umbrella and
  napkin (103); furniture (110); everyday small props such as cake, book, phone, gift, balloons
  and watering can (122).
- Rooms with walls, floors, windows and doors (109–110); walking in depth (111).
- Props that move by themselves: clock, tv, lamp (120); fireplace, kettle, falling fruit, birds
  (121).
- Vehicles: bicycle, car, bus (118); boat, hot-air balloon, toy rocket (119).
- Reusable casts and sets with `include:` and `set:` (101); `cartoon_style` for generated
  backgrounds (77).
- Ready-made sets for `set: NAME` without writing `sets:`: outdoors `city_street`, `park`,
  `beach`, `forest`, `snowy_hills` (139) and rooms `classroom`, `kitchen`, `shop`,
  `living_room`, `bedroom` (140), with 18 new props (shop, bench, fountain, pine, blackboard,
  school desk, shelf with goods, till...) and marks for two characters and every seat.
- A drawing style for the whole video: `drawing: {outline: thin | normal | bold, shading: flat |
  soft, texture: none | paper | storybook}` (142); the default draws exactly as before.

### Platform stories (Phase O)

- A `stage` scene with a `level:`: a side view written as a small ASCII map (ground, floating
  planks, one-way clouds, ladders, gaps, spots by letter), drawn once into tiles in the cartoon
  look, with the background and layers moving behind by parallax (150).
- Walks along the tiles (steps, ladders, stopping at edges) and jumps planned from the author's
  intent (`jump: pip, to: cloud`): a crouch, a slow arc checked against the tiles, a squash and
  a wobble on landing; `vidgen validate` replays every move and says why one cannot be made (151).
- Story props: coins and stars picked up on the way and in the air, a `key` prop and locked
  `door`s (`level.locks`), friendly blockers (`level.blockers`, `step_aside`), reactions on the
  move (`react: {when: pickup | land | arrive}`) (152); their sounds (`coin`, `twinkle`,
  `unlock`, a soft landing) through the foley (153).
- A camera that follows the hero gently (`level.follow`), up and down on tall levels; a short
  map in 9:16 sits on more ground; `character_size: small | medium | large` for the video, a
  variant or a scene (also on plain stages); lint `small_speaker` (154).
- A `snail` species; a set's sky, layers and light on a level (not its props); `vidgen
  screenplay` with a level from a front-matter set and `jumps onto` directions; portrait
  close-ups no narrower than a face; the example `examples/platform-story` (155).

### Isometric story places (Phase Q)

- A `stage` scene with an `iso:` place: a village, a garden or a room written as a small ASCII
  map with heights (grass, paths, water, garden walls, doors, raised blocks, spots by letter),
  seen from above at an angle; ready-made objects (house, tree, lamp, well, bench, bridge,
  flowers, table, sofa, bed...); indoor rooms with their front walls cut away; the characters
  stay the flat cut-outs, hidden by what stands in front of them (166).
- Moves on the place: `walk_to` / `run_to` a spot along a route round objects, water and walls
  and up steps, `meet`, `wander`, `after:` a leader, `enter` / `exit` over the edge or by a door;
  `vidgen validate` replays them and says where the way stops (167).
- Staging: shots and `follow` on the place (sharp in close-ups), `pan` to a spot; small things
  picked up, given and put down (checked in cells); `open` a house's door or flowers (they
  bloom), `switch_on` a lamp, `reveal` / `hide` an object (a bridge appears) (168).
- Mood and sound: `light: morning | sunset | night` with lit lamps and windows glowing, rain
  landing on the place, name tags over small speakers in wide views, footsteps by the ground
  (grass, path, boards, bridge, stone), door, pick-up and bloom sounds, crickets at night; lint
  `offscreen_action`, and `hidden_speaker` / `small_speaker` measured on the place (169).
- The example `examples/iso-story` (16:9 and 9:16), the guide topic `iso`; rain from a scene's
  start darkens an iso place to the rainy tint unless the scene sets a `light`; a held thing
  fades with a character leaving the place; a walk to where someone stands across a stream is
  refused instead of ending on the near bank; lint `said_before_shown` no longer takes a name
  tag for a label (170).
- Review (171): each iso scene starts on a wide view that fills the frame (16:9: the place's
  tips cut, never a spot, a character or a placed object; 9:16: the part where the characters
  stand, up to twice as close), and `shot: wide` is that view; `pan` to a spot moves in from it;
  a lit lamp lights the characters next to it at night; a larger `flowers` or `bush` is a flower
  bed or a hedge (a clump per cell); the JSON Schema takes a bare `on: true` as YAML 1.1 reads it.
- Weather polish (Phase R, 172): rain on an iso place lands on roofs, crowns and the bridge
  instead of under them; `puddles: true` grows puddles with ripples on its grass and paths;
  `settle: true` snow turns its ground, roofs, block tops and treetops white (both were refused
  before); a run's speed lines follow its diagonal. Iso rain scenes and runs render a little
  differently than in Step 171 (splashes on the roofs, slanted speed lines).
- A new scene type `iso_diagram` (173): architecture and data-flow diagrams of blocks in the
  isometric view (boxes, slabs, cylinders and databases, flat tiles; a block with `layers` is a
  stack), group plates and connectors along the grid (flat arrows, dashed, pipes), with flat
  labels that stay readable, placed in order (`arrange`, a zigzag in 9:16) or on the grid
  (`at`), fitted to 16:9 and 9:16.
- `iso_diagram` actions (174), timed like any action (`at: "@word"`): `build` (blocks grow up
  from the floor, drop in or fade in on the word; the scene leaves them to it), `raise` /
  `lower` (with a shadow), `explode` / `collapse` (a stack's layers apart and back, labels
  going along), `flow` (dots or packets along connectors, one after another with `chain`),
  `focus` (the camera onto a part, staying) and `relabel` (a label or value changes in place);
  `dim` and `highlight` keep the blocks' shading. New params `build: each` (one block or stack
  per step), `entrance` (`drop`, `grow`, `fade`) and `portrait_grid` (an `at` grid slanted down
  a 9:16 frame); a target `diagram`. Labels are placed right by their blocks (with a leader
  line when pushed away), clear of other blocks and labels; a group's caption by its plate's
  front edge, connector labels along the connector, one label per block; a stack's layers are
  listed under it with colour swatches in 9:16, where it is drawn larger. A lint rule
  `iso_labels` reports labels over other blocks, labels or connectors, or far from what they
  name.
- The example `examples/iso-web-page` (175, 16:9 and 9:16): "What happens when you open a web
  page", a two-minute explainer of a request from the browser to the database and back and of
  the browser's rendering steps, in three iso diagrams with a title and a recap. Fixes found
  while making it: a diagram is fitted at the largest scale that fits even when a smaller one
  does not (a label pushed clear at one scale can lie by its block at a larger one; a diagram
  could come out at a third of its size), `focus` keeps its targets clear of the captions, and
  `focus: diagram` goes back to the whole frame (it zoomed onto the diagram and cut off the
  heading).
- Review of Phase R (176): an iso diagram fills the room between heading and captions (labels
  go beside the blocks when those above and below would take a wide frame's height; in 9:16 an
  `at` grid is drawn as written or slanted, whichever is largest); `focus` fades out the labels
  its view would cut and brings them back, and its `padding` is a share of the view's shorter
  side (it zooms in 9:16 too); a flat connector tilts up to a raised block; the floor comes in
  with the blocks that are built and follows them in whole cells without a ragged edge; puddle
  ripples stay inside their puddle. The example drops its "App servers" caption and is drawn a
  third larger.
- Follow-ups (177): pipes tilt up to raised blocks too (dots and packets ride on them); the label
  of a block a `raise` lifts keeps off its tilted connectors (the example lints clean in 16:9 and
  9:16; `iso_labels` judges a label's distance at the diagram's own scale under a `focus`); in
  9:16 on an iso place a shot never cuts a character in half at the frame's edge (whole in, or
  out), centres the figures when the tightest zoom leaves the view taller than needed, and the
  wide view keeps in view the spots the scene's walks go to. 16:9 is unchanged.
- Fix (178): a block built with `grow` no longer shows at full size for a moment before it grows
  (it starts unseen on its first frame, whatever the timing); on an iso place an object revealed,
  hidden, opened or switched no longer shows its final look early in the pictures of what stands
  behind it or of a character behind it, and a hidden object no longer comes back (or a closed
  door's open leaf stays) until the next animation.

### Presentation toolkit (Phase P)

- Actions on a spoken word: any beat action's `at` (and a `lower_third`'s) may be `"@gradient"`,
  `"@gradient#2"`, `"@gradient+0.3s"` or `"@learning rate"`, timed from the TTS word timings
  once there is audio and estimated from the text before; an unknown word is a `vidgen validate`
  error that lists the beat's words like it (156).
- One colour per concept: `terms: {loss: primary, gradient: "#E07A5F", "learning rate": {color:
  tertiary, tex: '\eta'}}` colours those words in every text vidgen writes (titles, bullets, chart
  and diagram labels, callouts, karaoke captions) and their symbols in equations; `terms: false`
  opts a scene out; lint `concept_colors` (157).
- `code_morph`: version A of a listing morphs into version B (kept tokens glide, new lines grow
  in, removed ones fade out; the diff is vidgen's), at a beat or on a word (158).
- `terminal`: commands typed at a prompt and the output you write appearing, beside a code
  listing or after a code scene (`carry`); vidgen runs nothing (159).
- `function_plot`: functions written as maths and parsed safely (no `eval`), a dot tracing a
  curve with its tangent and a live label, shaded areas with their signed value, the `trace`
  action (160); points, vectors (sums, scaling), braces, angle marks, dimension lines, and the
  `number_line` scene type with points, intervals and jumps (161).
- `bar_chart` and `line_chart` take `changes` (values per beat): bars grow and re-sort, lines
  morph and the y axis rescales, a cursor sweeps a line with `trace` (162).
- Lint `said_before_shown` (and `unsaid_reveal`, off by default): the narration and the picture
  checked against each other from the layout dump and the word timings (163).
- The example `examples/gradient-descent` (16:9 and 9:16); the Shorts cookbook covers word
  timing, concept colours, code morphs and the terminal; the review's fixes (164).

### Explainer hosts

- `host:` puts a cartoon character beside the content of any explainer scene (bullets, charts,
  code, diagrams...): the content's area shrinks to make room, the host speaks the narration
  with lip sync, and lint rule `host_overlap` checks it (133).
- Host actions `host_point`, `host_look`, `host_react`, `host_move`, `host_enter`,
  `host_exit`, and `auto_direct` for hosts: point at each newly revealed item, react to a
  chart going up or down (134). Example `examples/host-explainer`.

### Cartoons: acting and directing

- Beat actions: `say`, `look_at`, `turn`, `emote`, `pose`, `react` (78); `walk_to`, `run_to`,
  `enter`, `exit`, `gesture`, `jump` (79, 108); `keyframes` and `move_along` (81);
  `pick_up` / `hold` / `put_down` / `give` / `throw` (93); `sit_on`, `stand_up`, `lean_on` (94);
  `get_in` / `ride_to` / `get_out` (118); `effect` symbols (107); `knock`, `pour`, `let_go`,
  `switch_on` / `switch_off`, `open` / `close` (103–128).
- Animation principles built in: anticipation, squash and stretch, overshoot, follow-through
  on a damped spring (`cartoon_motion`; 80, 82). Motion effects such as dust, speed lines and
  impact stars (108).
- `auto_direct`: looks, reactions, gestures, close-ups and effect symbols, planned so that
  lint stays clean; `vidgen direct --print` writes them out as YAML (89, 90, 95, 107).
- Overlapping speech and interruptions (100); voice sounds such as `[laugh]` (99).
- Cartoon lint rules: `off_stage`, `character_overlap`, `bubble_overlap`, `facing_away`,
  `hidden_speaker`, `mouth_without_voice`, `walk_overlap`, `talked_over`, `prop_overlap`,
  `look_alike` (84, 100, 115, 116a). Storyboards include mid-action stills (83).

### Screenplays, cards and transitions

- `vidgen screenplay FILE.md` (also an MCP tool) turns a screenplay into a stage project, with
  looks and voices chosen to suit each character (`FEN (she): ...`) (91, 102 follow-up, 115).
- The `card` scene type for title cards, "Later that day…" cards and end cards; `iris_in` and
  `iris_out` transitions (112).
- Guide topic `cartoons` in `AGENTS.md` / `vidgen guide` (85).

### Weather, light and mood

- `light: day | morning | sunset | night | indoor` and fades between them; soft shadows (97).
- Wind that sways trees and makes hair and scarves trail (98, 104); props that blow away (104).
- Particles: rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves, streaks (76, 104).
  Rain lands on the ground, with shelter and puddles (105).
- Snow that settles, and fog (126); lightning with thunder, rainbows, a sun and moon that move
  with the light (127).

### Sound and music

- Foley tied to actions (footsteps, whooshes, pops, boings, thuds, door creaks, splashes) and
  music stings (86, 128). New generated sounds include `bell`, `engine`, `brakes`, `phone`,
  `thunder`, `beep`, `creak`, `knock`, `splash`.
- Ambience beds: rain, fire, birdsong, city, room tone, crickets (105, 121, 128, 169).
- New music beds: `cartoon` and `lullaby` (129).
- Five documentary music beds with a soft kick and a synth bass (179): `discovery` (D minor,
  104 BPM, a steady approach that builds), `breakthrough` (112 BPM, tension in C minor, then a
  lift to E-flat major 25.7 s into the loop: a reveal), `enigma` (B minor, 96 BPM, mysterious),
  `momentum` (G minor, 120 BPM, the most energetic), `lab` (F minor, 108 BPM, modern tech). Used
  like the other beds (`music: discovery`); bass-heavy, so lighter on phone and laptop speakers.
  The five older beds sound exactly as before. `vidgen validate` suggests the nearest bed name
  for a misspelt `music` source.
- Four energetic electronic music beds (181): `ascent` (A minor, 136 BPM, uplifting trance that
  builds and lifts 28.2 s into the loop), `horizon` (132 BPM, anthemic trance with a gated
  supersaw, D minor lifting to F major 29.1 s in), `beacon` (E minor, 120 BPM, a cosmic
  pulsar-like ticking beacon), `neon` (F-sharp minor, 116 BPM, synthwave night drive). Used like
  the other beds (`music: neon`); bass-heavy, so lighter on phone and laptop speakers. The ten
  older beds sound exactly as before.
- Composed music: `music: {compose: MOOD}` writes an original piece as notes and plays it with
  real instruments (the optional `music` extra, symusic 0.5.9, and the GeneralUser GS SoundFont,
  downloaded once and checked: `vidgen soundfont fetch`, or `soundfont: PATH` for your own) (145,
  146). Eight moods: `calm`, `focused`, `curious`, `upbeat` for explainers, `playful`, `sleepy`,
  `tense`, `triumphant` for cartoons, with instruments per part and a seed (147). The piece is
  composed for the video's timings: scene changes on bar lines, a mood per scene, swells on
  reveals, pauses before punchlines, a closing cadence, and stings played by the music's own
  instruments (148). Without the extra the mood's built-in bed plays and `vidgen validate` warns;
  drafts and animatics play it too; `vidgen music preview` (MCP `music_preview`) writes a piece
  as WAV and MIDI (147, 149). `examples/host-explainer` and `examples/cartoon-rain-check` use it.
- A Listen page, [`docs/music/README.md`](docs/music/README.md), made by `vidgen music page`:
  a 15 s MP3 clip and a spectrogram of every bed (from the lift for `breakthrough`, `ascent` and
  `horizon`), clips that play all 36 sound effects and the six ambience beds, and two composed
  moods; all made by vidgen itself and byte-identical when made again. The README leads with
  the music and sound synthesis and links it (183).
- Score files: music written in YAML (key, tempo, time signature, named sections, a progression
  in Roman numerals or chord names, tracks of step patterns such as `"x... x..."`, `"1358 5315"`
  with `accent: "3+3+2"` or `"E5 - - . G5"`), played by vidgen's own instruments as a seamless
  loop or a one-shot at −28 LUFS; every mistake reported at once with did-you-mean. `vidgen music
  render SCORE.yaml --out FILE.wav` (184).
- Score files gain an instrument library of 26 (gated snare, analog bass, square pluck, soft lead,
  pulsar tick, radio static, saw and glass pads, pizzicato, music box...) and effects on any
  track or section: filter sweeps, side-chain ducking to the kick, trance gates, echo, reverb,
  stereo spread and width, volume curves. `vidgen music patches` describes them all; `vidgen
  music render` writes MP3 too and warns about notes it cannot play (185).
- Templates: every built-in bed as a commented score file to start from, a close re-creation
  measured against the bed (tempo, key, loudness over time, spectrum): `vidgen music template
  momentum --out my_theme.yaml`. Score files gain voicing notes `v1`–`v9`, notes played together
  (`v2+v3+v4`), the bass an octave up (`x'`), a pad `swell` and a `snap`; a pad's sub now plays
  the written bass note and sits in the centre (186).
- `vidgen music check my_theme.yaml` (or any audio file): how a piece will sit under narration,
  in words — loudness and steadiness, peaks and clipping, the tempo heard, the loop's seam, how
  much sits in the voice's range, bass weight, harsh highs, the key, whether the lift lifts and
  the build builds — with advice that names the tracks and score keys to change, a spectrogram
  with the sections marked and a 20 s demo under a narration sample with vidgen's ducking;
  `--compare` puts two versions side by side (187).
- Project pieces: a score file in `assets/music/my_theme.yaml` plays like a bed with `music:
  my_theme` (or `source: assets/music/my_theme.yaml`), rendered when the video is joined and
  cached; `vidgen list-music`, `vidgen validate` and `vidgen lint` (rule `music_check`) include
  them; MCP tools `music_template`, `music_patches`, `music_render`, `music_check`; the author
  guide's "Making music" recipe (188).
- An example made with it: `examples/gps-time-of-flight`, a narrated GPS explainer whose music,
  *Time of Flight*, an AI author made from the `momentum` template in nine checked steps (the
  README has the log and the check report); `docs/COOKBOOK-MUSIC.md`, music craft notes (room for
  the voice, builds and lifts, loops, check and compare, five genre sketches, common mistakes);
  the Listen page gains a "Made with the score format" row. The recipe now says how to change a
  template's key and which section names the check judges; `vidgen music template` suggests the
  check as the next step (189).
- Two new built-in beds written in the score format: `tidewater` (E minor, 108 BPM, steady and
  hopeful, a bell melody in its lift) and `skyline` (D minor, 128 BPM, a pumping supersaw build
  and lift). `music: tidewater` plays them like any bed; `vidgen music template tidewater` gives
  the very score the bed plays. 16 beds in all, on the Listen page too (190).
- Review of the score format (191): a note can be held across a section's change (steps that
  start with `-`); `duck: {follow: true}` dips by each hit's level; a cue can start at a section
  of a piece or score bed (`section: lift`, so the lift begins with a chosen scene); `vidgen music
  render` / `check` (and the MCP tools) take a project piece's or a bed's name; the check finds a
  part that clashes with one chord, notes a lift that stays under an earlier section, no longer
  suggests a riser for a lift and says how far a quiet riser is under a build; lint's
  `music_check` reports only on the part of a piece the video plays; filter sweeps render in
  parallel (the same samples). Every existing score, bed and mix sounds exactly as before.
- *Time of Flight* becomes the 17th built-in bed, `time_of_flight` (B minor, 108 BPM, intro /
  build / lift / settle: science and tech explainers, discovery and measurement stories, maps and
  navigation), exactly as it sounded; `vidgen music template time_of_flight` gives its score. The
  GPS example plays the bed and no longer keeps its own copy (a project piece named
  `time_of_flight` would now clash with the bed: rename it, or play it by its path) (192).

### Narration and pictures

- OpenRouter narration: `voice: {provider: openrouter, ...}`. One provider per video, with
  price estimates in the dry run (62, 63).
- Free local narration with Kokoro: `voice: {provider: kokoro}`, installed with the `kokoro`
  extra on Python 3.10–3.12 (65).
- OpenRouter pictures, `imagegen: {provider: openrouter}` (61); vector pictures with
  `generate: {format: svg}` and `.svg` files in `image` scenes, drawn, recoloured and cleaned up
  (61b). A clear message when the account's privacy settings block a model (Zero Data
  Retention).
- Lines with feeling: `emotion:` on a beat or a voice (13 emotions such as `excited`, `sad`,
  `whisper`, `doubtful`, or your own speed / pitch / gain / pauses). Kokoro changes speed,
  pitch, loudness and pauses (135); ElevenLabs v3 gets audio tags, other ElevenLabs models voice
  settings, OpenRouter models instructions or the same audio changes (136). Kokoro voice blends
  with weights: `af_heart+af_bella:0.6` (135).
- Dubbing: `dub: {LANG: VOICE}` on voices, automatic Kokoro voices of the same kind for a
  translated variant, lip sync and timings from each language's audio, and `--all-languages`
  on `tts`, `render` and `lint` (MCP `render` / `lint`) (143). `examples/cartoon-music-box`
  has a Brazilian Portuguese variant.
- Built-in pronunciation lists per TTS engine and language (`kokoro-en-us`, `kokoro-en-gb`), used
  under every project's own entries; `pronunciation_defaults: false` turns them off; `vidgen
  list-pronunciation [PROJECT] [--json]` shows them and what they change; validate, `tts` and
  readback say when a built-in entry is involved (165).
- `vidgen readback` flags single words the recogniser was unsure of or heard after an odd pause,
  with the time in the video and a suggested fix; `vidgen lint --readback` reports them as rule
  `unclear_speech` (141).

### Rendering and tooling

- `--jobs auto` on `render`, `storyboard`, `lint`, `thumbnail`, `slides`, `gallery` and MCP
  uses as many jobs as the available memory allows, at 1.5 GB per job (117).
- Faster cartoon renders: static layers stay in Manim's static image, and part drawings are
  cached (87).
- Works with Manim 0.22 (64).
- The scene gallery (`docs/gallery`, `vidgen gallery`) shows animated previews: each index cell
  plays the 16:9 and 9:16 GIFs (the still for viewers who ask for reduced motion); every GIF
  skips the empty opening, opens on its held last beat and stays under 150 KB. "2D cartoons" and
  "Isometric cartoons" end with eight showcases, small scenes written for the gallery with their
  whole YAML (a dialogue in a room, walks in depth, rain at nightfall, a platform jump; an iso
  village, a cut-away room, a lamp lit at night, settling snow); `--types` takes their names.
  The README shows four gallery GIFs near the top (182).
- `vidgen render --draft`: a quick render at about 8 fps and 240 px without decoration (idle
  motion, wind, shadows, particles, light grade), every timing kept, in its own `build/draft`
  folder and `_draft.mp4` (137).
- `vidgen animatic` (also an MCP tool): the storyboard's stills timed to the narration with the
  video's audio and captions, joined by ffmpeg in seconds (138).
- Examples: `examples/cartoon`, `cartoon_series`, `screenplay`, `svg_character`,
  `cartoon-music-box`, `cartoon-rain-check`, `cartoon-muffin-mystery`, `cartoon-rainbow-ride`,
  `host-explainer`, `platform-story`, `gradient-descent`.
- Reviews 63, 88, 102, 116, 130, 144, 149, 155 and 164, and full test suite runs (131, 144), fixed what
  they found (4042 tests passed in Step 144's full run).

### Known gaps

- No human has listened to the generated sounds and beds; the composed music was chosen by a
  listening test of the renderer, but the moods and fitted pieces await one. Windows and macOS were not run
  here: see `docs/WINDOWS-CHECK.md`. The open items are listed under "Backlog" in
  `tasklist.md`.
