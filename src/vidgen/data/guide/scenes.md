<!-- topic: scenes (also: chooser, types, scene-types) -->
## Choosing the scene type

Pick by **what the viewer should understand**, not by what the data looks like. To see what
each type looks like at 16:9 and 9:16, open the scene gallery (`docs/gallery/README.md` in the
schu-video-generator repository: a still, a GIF, the YAML, params and targets per type; the types drawn
in a web page, `3d`, `web` and `space`, in `docs/gallery/web/README.md`) or make it yourself:
`vidgen gallery --output gallery --types pie,map` (any folder; in a project it also renders the
project's own scene types, in its theme).

| you want to show | scene type | key params |
|---|---|---|
| the title, who made it | `title` | `title`, `subtitle`, `kicker`, `highlight`, `icon` |
| a new section | `chapter` | `number`, `title`, `subtitle`, `icon` |
| one statement or question, big | `text_card` | `text`, `color` |
| a few points, in order | `bullets` | `heading`, `items`, `numbered`, `dim_previous` |
| a set of things (features, parts, options) | `icon_grid` | `heading`, `items`, `groups`, `highlight`, `icon_color` |
| A vs B, before / after, pros / cons | `comparison` | `heading`, `columns`, `verdict`, `vs`, `reveal` |
| exact values to compare across attributes | `table` | `title`, `header`, `rows`, `number_format` |
| what happened when | `timeline` | `heading`, `events`, `spacing`, `highlight`, `now` |
| how parts connect, decisions, architecture | `diagram`, `flowchart` | `heading`, `nodes`, `edges`, `highlight`, `direction` |
| something moving through stages | `process` | `heading`, `stages`, `input`, `output`, `loop`, `token_label` |
| a neural network | `network` | `heading`, `layers`, `connect`, `highlight` |
| architecture in 3D: servers, databases, layered stacks, data flow (isometric blocks) | `iso_diagram` | `heading`, `blocks` (in order; one with layers, bottom up, is a stack), `edges`, `groups`, `arrange` |
| a cell in true scale: organelles, membranes, ribosomes; zooming from tissue to one molecule (cell biology) | `cell` | `title`, `cell`, `contents` (typical: the textbook cell), `objects` (kind, at in µm, in, on, count, coat, style; molecules: state, faces, membrane), `view`, `labels`; animal, plant or bacterium; the actions zoom_to, motor_walk, endocytosis, exocytosis; with a `gene`: transcribe, export, translate, to_golgi, secrete (its products' route, the camera following) |
| the cell cycle with its checkpoints and cyclin–CDK levels; mitosis and meiosis with counted chromosomes, crossing over and four haploid cells | `cell_cycle` | `title`, `mode` (cycle, mitosis, meiosis), `start`, `hours`, `chromosomes` (2n), `cell` (animal, plant), `crossovers`, `assortment`, `nondisjunction` ({division: I or II, pair}: aneuploid gametes), `captions`, `counts`; the actions advance (to, into, expect) and checkpoint (outcome, cause) |
| energy metabolism: glycolysis, pyruvate oxidation, the citric acid cycle, the electron transport chain and ATP synthase, the light reactions; flows animated, products counted | `metabolism` | `title`, `process` (glycolysis, link_reaction, tca, etc, light_reactions), `cell`, `in`, `membrane`, `protons_to`, `components`, `link`, `tallies`, `names`; the action advance (to, from) |
| a genetic cross: Punnett square or branch diagram, gametes, genotype and phenotype ratios (mono-, di-, trihybrid, test, reciprocal, P → F1 → F2, dominance, epistasis, lethal 2:1, X-linked, linked genes), a chi-square test | `cross` | `title`, `preset` (pea_dihybrid, abo, labrador, drosophila_white, hemophilia_a…) or `loci` / `linkage` / `epistasis` / `sex`, `parents` (or `mother` / `father`, or `P`), `kind` (cross, test, reciprocal), `show` (auto, punnett, branch), `branch`, `observed`, `alpha`, `notes`, `pictures`, `animal` (a coat's animal: dog, mouse…; auto); the actions form_gametes, fill, count, ratio, chi_square |
| a family pedigree in standard (NSGC) symbols: affected, carriers, deceased, proband, twins, consanguinity; which modes of inheritance fit and why the others are excluded, deduced genotypes, carrier probabilities, the risk for a child | `pedigree` | `title`, `individuals` (lines like "II-3: female affected of I-1 + I-2" or mappings), `couples`, `condition`, `mode`, `analyse`, `genotypes`, `penetrance`, `rare`, `carrier_frequency`, `alleles` or `preset`; the actions deduce, analyse, risk |
| linked genes and genetic maps: crossing over between homologues (coupling / repulsion), a two- or three-point test cross worked out from offspring counts (parental and double-crossover classes, gene order, distances in cM, coincidence and interference), map functions | `linkage_map` | `title`, `loci` + `counts` (the test-cross classes) or `map` (loci at cM positions), `map_function` (none, haldane, kosambi), `phase`, `crossover`, `chromosomes`; the actions cross_over, measure; reveal the steps (table, classes, order, distances, interference, map) |
| a human karyotype from its ISCN notation (47,XX,+21; 45,X; 46,XY,del(5)(p15.2); t(9;22); rob(14;21)): a karyogram by groups A–G with G-banded ideograms and the change highlighted, or the chromosomes involved with structural changes played as edits | `karyotype` | `title`, `karyotype`, `show` (auto, karyogram, ideogram), `chromosomes`, `bands` ({7q31.2: CFTR}), `notation`; the action rearrange |
| a mutation on a real coding sequence: the reading frame and codons, the variant made from them (substitution, deletion, insertion, frameshift with its premature stop, splice site), the protein change from the genetic code, HGVS c. and p. notation checked | `mutation` | `gene` (HBB, CFTR, GJB2, or a gene mapping) or `sequence` (+ `first`, `exons`, `length`), `variant` (c.20A>T, or {c, p, legacy, note}, or a list), `splice`, `codes`, `stop`, `codons`, `strip`, `symbol`; the action mutate |
| CRISPR–Cas9 editing: the sgRNA's spacer, the PAM, the R-loop, the blunt cut 3 bp from the PAM, and the repair (NHEJ indel or HDR from a donor), written in HGVS on a coding target | `crispr` | `target`, `cas` (SpCas9, SaCas9), `spacer` or `guide`, `repair` (nhej, hdr, none), `indel`, `edit`, `coding_first`; the actions scan, cleave, repair |
| the laboratory: PCR (primers, cycles, 2ⁿ copies), an agarose gel (ladder, migration by size), Sanger sequencing (a chromatogram with called bases) or NGS reads with coverage and a variant call | `dna_lab` | `method` (pcr, gel, sanger, ngs) and its params: `template` + `primers` + `temperatures` + `cycles`; `agarose` + `ladder` + `lanes`; `sequence` + `heterozygous`; `reference` + `variant` + `zygosity` + `depth`; the action run |
| population genetics: Hardy–Weinberg worked with exact numbers (p and q, p² + 2pq + q², carriers from an incidence, a chi-square test of HWE), seeded simulations of drift, selection, mutation, migration, a bottleneck or a founder effect with allele frequencies over generations | `population` | `model` (hardy_weinberg, drift, selection, mutation, migration, bottleneck, founder), `counts` / `frequencies` / `p` / `incidence`, `inbreeding`, `alleles`; `N`, `p0`, `generations`, `replicates`, `seed`, `fitness` or `s` + `h`, `mu`, `nu`, `populations` + `m`, `bottleneck`, `founders`; the actions simulate, resample |
| a genome-wide association study: a Manhattan plot with the 5 × 10⁻⁸ line and labelled peaks, a QQ plot with λ_GC, a regional plot of a locus coloured by LD | `gwas` | `plot` (manhattan, qq, both), `peaks` (a synthetic study, labelled "simulated data") or `data` (a CSV) or `variants`, `labels`, `trait`, `regional`, `x_chromosome`, `y_max`; the action regional |
| a signalling pathway: ligands, receptors, kinase cascades, second messengers, genes, in compartment bands, SBGN-style (arrows, T-bars, P marks); a signal spreading, inhibitors, knockouts, drugs | `pathway` | `title`, `template` (gpcr_camp_pka, rtk_ras_mapk, pi3k_akt), `nodes` (id, kind, label, in, gene, state, marks, role), `edges` (a -> b activates, a -o b catalyses, a => b translocates, an arrow with a bar inhibits, or {from, to, type, effect, site, feedback, label}), `remove`, `species`, `direction`; the actions signal, inhibit, knockout, drug, amplify, focus |
| molecules up close: DNA, RNAs, nucleosomes, receptors, channels, pumps, ATP synthase, ions (nm, notation checked); transport, diffusion, osmosis, action potentials | `molecule` | `title`, `membrane` (none, plasma, inner_mitochondrial, thylakoid…), `molecules` (kind, at in nm, in, state, faces, gene, protein, parts, transporter, modifications…), `solutes`, `potential`, `species`, `compartment`; the actions set_state, transport, diffuse, osmosis, action_potential; or a `gene` (codons, introns, signal_peptide, sequence…) whose expression the actions transcribe, cap, splice, polyadenylate, export, translate, target_er, glycosylate, fold show up close |
| one number that matters | `stat` | `value`, `label`, `comparison`, `context`, `prefix`, `suffix`, `unit` |
| categories compared by size | `bar_chart` | `title`, `labels`, `values`, `unit`, `highlight`, `caption`, `changes`, `sort` |
| change over time, trends | `line_chart` | `title`, `x`, `series`, `x_label`, `y_label`, `changes` |
| a relationship between two measures | `scatter` | `title`, `series`, `trend`, `highlight`, `x_label`, `y_label` |
| how values are distributed | `histogram` | `title`, `values`, `bins`, `mean`, `median`, `highlight` |
| measurements and models on scientific axes: log, symlog, reversed or broken axes with units, 10ⁿ and SI prefixes, panels sharing an axis, orbits at an equal aspect; data inline or from a CSV | `plot` | `title`, `series` (name, x and y or points, style, dashed), `data` (a CSV, units in its headers: "time (s)"), `x` / `y` (label, unit, scale, min, max, reversed, format, breaks), `panels`, `aspect` |
| error bars, fitted curves with parameters ± errors and R², confidence bands, residuals, histograms with a fitted distribution or a peak over a background, labels and reference lines on data | `plot` | `series` (y_err / x_err with error: sd, sem, ci95, range; or values with bins: a histogram), `fits` (series, model, band, residuals), `annotations` (label, arrow, hline, vline, xrange, yrange, note); the actions fit, annotate |
| a simulation drawn as it runs: an oscillator, an orbit's energy, predator and prey, the logistic map, a random walk, events arriving | `plot` | `models` (ode with equations, initial, params, t, method rk4 / rk45 / leapfrog; recurrence; random_walk; poisson; function), series naming their columns (x: t, y: x) with readout, trail; `rescale`; the actions grow, zoom (x, y) |
| parts of a whole (≤ 6 parts) | `pie` | `title`, `labels`, `values`, `donut`, `highlight`, `other_below` |
| a matrix (correlations, hours x days) | `heatmap` | `title`, `rows`, `columns`, `values`, `highlight` |
| where in the world | `map` | `title`, `view`, `steps`, `values`, `pins`, `arcs` |
| a photo or illustration | `image` | `path`, `generate`, `caption`, `fit`, `ken_burns` |
| a user interface, a web page | `screenshot` | `path`, `steps`, `frame`, `url`, `caption` |
| footage, a screen recording | `video_clip` | `path`, `steps`, `trim`, `fit_duration`, `region`, `mute`, `fade: false` (hard cut), `match_previous` (no flash where a take continues the one before) |
| simple 3D: shapes, labels and character stand-ins seen by a camera that stands still or moves on words (orbit, push in, fly to an object), objects that move, turn, appear, glow and walk on words, groups that move together | `3d` | `title`, `objects` (id, shape: box, sphere, cylinder, cone, torus, plane, arrow, label, group, standin; size, color, position, rotation in degrees, spin in degrees per second, parent, text, to, visible, name, voice, screen_size), `floor`, `camera` (position, look_at: a point or an object id, fov), `light` (ambient, sun, sun_from, color), `background`, `guide_passes` (depth / outline / mask videos of the 3D picture beside its clip, off by default; true or all for all three, or one name, a comma list such as depth,mask or a list, read like the render option --guide-passes), `depth_range`; the actions camera_orbit, camera_dolly, camera_fly_to, camera_look_at, camera_move, object_move, object_path, object_rotate, object_spin, object_scale, object_show, object_hide, object_highlight, object_walk, object_face |
| a picture or animation no built-in draws, written yourself in HTML, CSS and JavaScript: a bespoke layout, CSS or SVG animation, a canvas drawing, your own three.js scene (`vidgen guide web`) | `web` | `page` (an HTML file of the project: any HTML, CSS, JavaScript) or `script` (a JavaScript module drawn on one canvas), `region` (bleed, body), `title`, `data` (values for the page); CSS animations, requestAnimationFrame, timers and the page's frame hook all follow the video's time; no internet while rendering |
| space with no code: a sky, a sun, planets with rings and air, craft on a real transfer, a black hole, a jump to warp, giant ships, planes over sea, ground and clouds, a descent from orbit, camera moves on bar lines; true positions and timing from orbit data (`vidgen guide space-scenes`) | `space` | `sky`, `sun`, `bodies` (name, world or type, at, radius), `orbits` (the orbit scene's words), `scale`, `light`, `craft` (kind, fly), `phenomena` (kind), `camera` (move, subject, over in seconds or bars, cut), `finish`, `music` (track, pulse / glow / glint), `title`, `end_card`, `script` (your code); a surface scene: `world` (planet, at, sun, air, sea, land, clouds), `flights`; `craft` (with plane, hull, parts, effects); `flash` |
| a quotation | `quote` | `text`, `author`, `source` |
| a formula that transforms | `equation` | `latex`, `terms`, `caption` |
| a derivation with reasons | `equation_derivation` | `title`, `steps`, `colors`, `result` |
| a worked calculation with units and significant figures: a formula, the values put in with their units, the result (orbital speed, half-life, a photon's energy in eV) or an exact probability (2/3 × 1/25 × 1/4 = 1/150); chains of results | `calculation` | `symbols` (name, value with its unit, or constant: G, meaning, source; from_scene: an earlier scene's result; mass / lifetime / width: a particle's PDG value, mass: pi+), `calculations` (name, expr, unit, convert, sig, format); the actions substitute, compute, convert |
| planets, moons, satellites or a comet on their orbits, moving in correct timing (Kepler's laws, the inner planets for a year, the ISS and a geostationary orbit, a flyby); mutual gravity; manoeuvres: burns, Hohmann / bi-elliptic / phasing transfers with their Δv, phase angle and launch windows, a gravity assist; many bodies: Lagrange points and Trojans in the rotating frame, the figure-eight, binary stars, the Io–Europa–Ganymede resonance, tides (a schematic); the Solar System on a date (1800–2050), the next opposition or conjunction, all planets on a log scale, an inset of the inner planets, planet sizes to scale | `orbit` | `central` (sun, earth... or {name, gm or mass, radius}), `bodies` (preset: mars, moon, iss, geo, halley, io; or a and e, periapsis, altitude, i, raan, argp, nu; or r and v with units; geometry, sectors, velocity; near: L4), `span` or `orbits`, `follow`, `frame` (axes, scale_bar), `dynamics` (nbody: mutual gravity), `cannonball` (Newton's cannon: speeds, altitude), bodies[].burns, `transfer` (ship, to), `flyby` (v_inf, altitude, side), `system` (sun_jupiter, earth_moon, figure_eight), `view` (rotating), `lagrange`, `resonance`, `origin` (barycentre), `tides`, `date`, `event` (opposition, of), `radial` (log), `inset`, `sizes`, `panel` (compact, full, none, rows); the actions sweep, launch, burn, flyby, pause, coast, corotate, inertial |
| the Standard Model's particles: quarks and leptons in three generations, the gauge bosons and the Higgs boson with their masses (PDG 2024), charges and spins; antiparticles; which bosons couple to which particles | `standard_model` | `title`, `reveal` (groups, all), `show` (mass, charge, spin, name), `antiparticles`, `layout` (wide, tall), `key`, `source`; targets particle:<name>, generation:<N>, group:<quarks...>, row:<...>; the actions antiparticles, couplings |
| a Feynman diagram in proper notation (e⁺e⁻ → μ⁺μ⁻, Compton, Bhabha, β⁻ and μ⁻ decay, π⁺ → μ⁺ ν_μ, Drell–Yan, gg → H, H → γγ, H → ZZ* → 4ℓ, t → W⁺b) or your own, every vertex checked against the Standard Model; s- and t-channel, decays, loops | `feynman` | `preset` or `diagrams` (lines "id: particle from -> to", groups), `diagram`, `time` (right, up), `spectators`, `reveal` (time, all); targets line:<id>, vertex:<id>, hadron:<particle>; the actions travel, vertex_rule, swap_channel |
| relativistic kinematics: a two-body decay (π⁺ → μ⁺ ν_μ, K⁺ → π⁺ π⁰, H → γγ) as momentum arrows in the rest frame and the lab, particles with their invariant mass, boosts, opening angles, decay lengths βγcτ | `kinematics` | `decay` or `particles` ({particle, momentum, angle}), `momentum` / `energy` / `kinetic` / `beta` / `gamma` of the parent in the lab, `angle`, `frames` (both, rest, lab), `si`, `readout` (key, all); targets panel:rest, panel:lab, arrow:<n>, sum, values; the action boost; a calculation takes p_star with from_scene |
| an event display in a schematic particle detector (tracker, solenoid, calorimeters, muon chambers): tracks bending in the magnetic field, electron / photon / muon / hadron / neutrino signatures, jets, missing transverse momentum; Z → μμ, H → γγ, H → 4ℓ, W → eν, dijet events | `detector` | `event` (a preset, {preset, seed} or {particles: [{particle, pt, eta, phi, leaves}], products}), `view` (xy, rz), `field`, `energy_scale` (log, linear), `tower_max`, `reveal` (layers, all), `readout`, `legend`, `layers`, `labels`, `label`; targets particle:<n>, particle:<particle>, jet:<n>, tracks, ecal, hcal, muon_hits, missing_pt, readout, legend; the action switch_view |
| a resonance emerging from (simulated) data: an invariant-mass histogram filling event by event with a ticker, Z → μμ, H → γγ or H → 4ℓ over a falling background, a peak fit (mass ± error, width), the local significance growing (Asimov) and what 5σ means, data − background | `mass_spectrum` | `channel` (z_to_mumu, h_to_gammagamma, h_to_4l, custom), `seed`, `events`, `signal`, `resolution`, `window`, `bin_width`, `background`, `peak`, `significance` (asimov, counting, none), `explain`, `subtract`, `style` (bars, points); a plot underneath: the actions grow (to: events), fit, annotate, reveal (residuals:fit), zoom (x) |
| a decay chain with lifetimes: π⁺ → μ⁺ ν_μ, μ⁺ → e⁺ ν_e ν̄_μ; H → ZZ* → 4ℓ; τ and cτ (PDG 2024), branching fractions, every decay checked | `decay_chain` | `decays` (in order), `lifetimes`, `branching`, `stable`, `reveal` (decays, all); targets decay<N>, particle:<n>, lifetime:<particle> |
| branching ratios of a particle from the model (H: SM prediction; Z, W, π, K, μ: PDG 2024), the source in the caption | `branching` (bars), `branching_pie` | `particle`, `modes` (the largest N); the bar chart's / pie's params and targets (bar:γγ, slice:hadrons) |
| a function's graph: slope, tangent, area under a curve | `function_plot` | `title`, `functions` (expressions: x^2, f(x) = sin(x)...), `x_range`, `y_range`, `dots`, `areas`, `aspect` |
| geometry, vectors: a triangle with braces and angles, adding and scaling vectors | `function_plot` | `points` (at, name), `vectors` (from, to, or sum: [a, b]), `marks` (segment, brace, angle, dimension), `axes` (false: pure geometry) |
| a number line: points, intervals, jumps (+3) | `number_line` | `title`, `range`, `points`, `intervals` ("[-1, 3)"), `jumps` ([2, 5]: an arc labelled +3), `step` |
| a short listing (≤ 15 lines) | `code` | `title`, `code`, `path`, `highlight` |
| code that changes: before / after, a refactor, a fix | `code_morph` | `title`, `versions` (each the code, or code / path / highlight) |
| a long file, explained part by part | `code_walkthrough` | `title`, `path`, `code`, `steps`, `excerpt` |
| running a command: install, tests, a REPL (output written by you) | `terminal` | `title`, `steps` (each a command, or command / output / clear), `prompt`, `language`, `code` |
| characters on a set (a cartoon) | `stage` | `characters`, `props`, `background`, `image`, `generate`, `marks`, `ground`, `layers`, `width`, `particles`, `light`, `wind` |
| a cartoon's title card, "Later that day…", "The End" | `card` | `text`, `subtitle`, `style`, `color`, `sting` |
| thanks, links, call to action | `end_card` | `title`, `lines`, `icon`, `logo` |

How beats drive scenes: each type splits its content into **reveal steps** and plays step *i*
at beat *i* (more steps than beats: spread evenly; more beats: the last ones hold). Types with
per-beat data (`code_walkthrough`, `terminal`, `equation_derivation`, `screenshot`, `video_clip`, `map`)
take a `steps` list, entry *i* for beat *i*: write as many steps as beats (`code_morph`:
one of its `versions` per beat). A `highlight` param
adds a last step that marks one thing and dims the rest, so give it its own beat. Silent
scenes have a `duration` instead of beats (show each chapter card for about 3.5 s, `duration: 3.5`, so viewers can read the number
and title). Every header-band type
accepts `heading` and `title` alike.

Minimal snippets (copy, then adapt):

```yaml
# text and structure
- id: opening
  type: title
  params: {kicker: "EXPLAINER", title: "Saving 77% of the parameters", highlight: "77%", icon: brain-circuit}
  beats: [{text: "What if most of a model could simply go?"}]
- id: part1
  type: chapter
  params: {number: 1, title: "The problem", icon: triangle-alert}
  duration: 3.5
- id: question
  type: text_card
  params: {text: "Do we need all those parameters?", color: highlight}
  beats: [{text: "So do we really need all of them?"}]
- id: steps
  type: bullets
  params:
    heading: "Three steps"
    numbered: true
    items: [{text: "Measure", icon: gauge}, {text: "Prune", icon: funnel}, {text: "Retrain", icon: refresh-cw}]
  beats:
    - text: "First, measure which weights matter."
    - text: "Then remove the rest."
    - text: "And retrain briefly to recover."
- id: parts
  type: icon_grid
  params:
    heading: "What the platform covers"
    icon_color: palette
    items:
      - {icon: cpu, label: "Compute"}
      - {icon: database, label: "Storage"}
      - {icon: network, label: "Network"}
      - {icon: shield-check, label: "Security"}
    groups: [[0, 1], [2, 3]]
  beats:
    - text: "Compute and storage come first."
    - text: "Then networking and security."
- id: choice
  type: comparison
  params:
    heading: "Monolith or microservices?"
    vs: "vs"
    columns:
      - {heading: "Monolith", tone: positive, points: ["One deploy", "Simple setup"]}
      - {heading: "Microservices", tone: negative, points: ["Many deploys", "Network failures"]}
    verdict: "Start with a monolith"
  beats:
    - text: "A monolith ships as one piece."
    - text: "Microservices multiply the moving parts."
    - text: "So start simple, and split later."
- id: results
  type: table
  params:
    title: "Benchmark"
    header: ["Model", "Params", "Accuracy"]
    rows: [["Baseline", 110, 0.812], ["Sparse", 55, 0.809]]
    number_format: [null, "{:,.0f}M", "{:.1%}"]
  beats:
    - text: "The baseline has a hundred and ten million parameters."
    - text: "The sparse one has half, at the same accuracy."
- id: history
  type: timeline
  params:
    heading: "The space race"
    events:
      - {date: 1957, title: "Sputnik", icon: satellite}
      - {date: 1961, title: "Gagarin", icon: user}
      - {date: 1969, title: "Apollo 11", icon: moon}
  beats:
    - text: "In 1957, the first satellite, Sputnik, reached orbit."
    - text: "Four years later, Gagarin flew."
    - text: "And in 1969, people walked on the Moon."
- id: outro
  type: end_card
  params: {title: "Try it yourself", icon: link, lines: ["github.com/me/project"]}
  beats: [{text: "The code is online. Try it on your own model."}]
```

```yaml
# flows
- id: release
  type: flowchart
  params:
    heading: "How a change ships"
    nodes:
      - {id: pr, label: "Pull request", shape: pill}
      - {id: ci, label: "Tests pass?", shape: diamond}
      - {id: fix, label: "Fix the code"}
      - {id: ship, label: "Deploy", icon: rocket}
    edges: ["pr -> ci", "ci -> ship: yes", "ci -> fix: no", "fix --> ci"]
    highlight: [pr, ci, ship]
  beats:
    - text: "Every change starts as a pull request."
    - text: "The tests decide what happens next."
    - text: "A failure goes back for a fix."
    - text: "A pass goes straight to production."
    - text: "That is the path most changes take."
- id: order
  type: process
  params:
    heading: "What happens to an order"
    input: "Checkout"
    output: "At your door"
    token_label: "order"
    stages: [{label: "Pay", icon: credit-card}, {label: "Pack", icon: package}, {label: "Ship", icon: truck}]
  beats:
    - text: "At checkout, the order is paid."
    - text: "The warehouse packs it."
    - text: "And a courier brings it to your door."
- id: mlp
  type: network
  params:
    heading: "A small classifier"
    layers: [{size: 784, label: "Pixels"}, {size: 128, label: "Hidden"}, {size: 10, label: "Digits"}]
  beats:
    - text: "Every pixel is an input."
    - text: "A hidden layer combines them."
    - text: "Ten outputs score the ten digits."
    - text: "A forward pass flows from left to right."
- id: arch
  type: iso_diagram
  params:
    heading: "A web app, layer by layer"
    blocks:
      - {id: browser, label: "Browser"}
      - {id: app, label: "App server", layers: [Storage, Logic, API]}   # a stack: layers bottom up
      - {id: db, label: "Database", shape: database}
    edges: ["browser -> app: HTTPS", "app -> db"]
  beats:
    - text: "Requests come in from the browser."
    - text: "The app server handles them layer by layer, and keeps its data in a database."
      actions:                                      # iso_diagram actions: build, raise, lower, explode,
        - {flow: "edge:*", chain: true}             # collapse, flow, focus, relabel (`vidgen guide actions`)
        - {explode: "stack:app", at: "@layer"}
```

A whole iso explainer: `examples/iso-web-page` (a request from the browser to the database, each
block built on the word that names it, `flow` along the connectors, `focus` and `relabel` for a
cache miss and hit, a rendering stack exploded layer by layer). When one diagram returns in
several scenes, give its blocks `at` and their own `color` so it looks the same each time; keep
labels short ("App 1" over "Application server 1") so they sit right by their blocks, and leave
out a group caption the blocks' labels already say: every label costs room, and the diagram is
drawn as large as its labels let it.

```yaml
# cell biology
- id: tour
  type: cell
  params:
    title: "Inside an animal cell"
    cell: animal                                   # or plant, bacterium; contents: typical is the textbook cell
    objects:
      - {kind: ribosome, id: mitoribosomes, in: mitochondria, count: 6, label: false}
  beats:
    - text: "A typical animal cell is about twenty micrometres across."
    - text: "Inside one mitochondrion, the inner membrane folds into cristae."
      actions:
        - {zoom_to: mitochondria, at: "@mitochondrion"}   # {zoom_to: rough_er, level: complex}: one ribosome
- id: synthase
  type: molecule
  params:
    title: "ATP synthase"
    membrane: inner_mitochondrial                  # the bilayer between the intermembrane space and the matrix
    molecules:
      - {kind: atp_synthase, parts: true}          # F1 faces the matrix (faces: intermembrane_space is refused)
      - {kind: atp, in: matrix}
  beats:
    - text: "Protons flow back into the matrix through ATP synthase, turning its rotor, and F1 makes ATP."
```

A `cell` is drawn at real sizes in µm and every place is checked: a ribosome in the nucleoplasm,
a mitochondrion inside the nucleus or a ribosome on the Golgi is refused with the textbook reason
(`vidgen validate`). Leave `at` out and things go where they belong; `at: [x, y]` is in µm from
the cell's centre. `cell: plant` adds the wall, plasmodesmata, the central vacuole and
chloroplasts; `cell: bacterium` (`{kind: bacterium, gram: negative, capsule: true}`) a nucleoid,
70S ribosomes, plasmids, a flagellum and pili. Kinds beyond the typical cell: `early_endosome`,
`late_endosome`, `vesicle` with `coat: clathrin|copi|copii`, `microtubule`, `actin_cortex`,
`stress_fiber`, `intermediate_filament` and the motors `kinesin`, `dynein`, `myosin` (`on:` a
filament; `vidgen schema --scene cell` lists them all). `zoom_to` moves between levels (tissue, cell,
organelle, complex) and names what the new view shows (`labels: false` or a list of part names);
the scale bar and the details follow the zoom; `style: surface` (the scene's or an object's) draws
things whole, seen from outside (a nucleus with its pores, a membrane's surface), instead of cut open.

Molecules are kinds too: in a `cell` (`{kind: gpcr, on: cell, count: 3, state: active}`,
`{kind: atp_synthase, on: mitochondria}` on the cristae, `{kind: dna, in: nucleus}`; drawn whole once
a zoom makes them a few pixels wide) and up close in a `molecule` scene (nm; a `membrane` across the
view, the molecules in a row unless `at` places them). Kinds: `dna` (`sequence` 5′→3′, its partner
drawn antiparallel; 5′/3′ ends, grooves), `mrna`, `trna` (`anticodon` 5′→3′ and `amino_acid`,
checked against the genetic code; `style: l_shape`), `rrna`, `nucleosome` (`marks: [H3K4me3,
H3K27ac]`, checked against the histone sequence), `chromatin` (`state: compact`), `protein`
(`domains`, `mass` in kDa), `kinase`, `phosphatase`, `g_protein`, `gpcr`, `rtk` (`state: dimer`),
`ion_channel` (`state: open`, `gating`, `ion`), `carrier` (`mode: symport`, `substrates`, `moves`),
`na_k_atpase`, `atp_synthase`, `atp`, `adp`, `pi`, `gtp`, `gdp`, `camp`, `glucose`, `ligand`, `ion`
(`ion: Ca2+`). Membrane proteins keep their textbook orientation (a GPCR's N-terminus outside, F1 in
the matrix or stroma); `faces:` states it and is checked. Names: `gene: TP53` is set in italics and
checked for the `species` (mouse `Trp53`, yeast `CDC28`), `protein: p53` in roman;
`modifications: [{mark: P, at: Ser15}]` (P, Ub, Ac, Me; phosphate never on Lys). Labels take Pango
markup: `β<sub>2</sub>`, `Ca<sup>2+</sup>`, `<i>lacZ</i>`.

Processes are actions. In a `molecule` scene give `solutes` (`[K+, Na+]`: particles at typical
concentrations, or `{solute: o2, mM: {extracellular: 0.2, cytosol: 0.02}}`) and `potential: -70`
for a live readout; then `set_state` (`{set_state: kv, state: open}`: ion channels closed / open /
inactivated, carriers outward / occluded / inward, the Na⁺/K⁺ pump e1 / e1p / e2p / e2, GPCRs
active), `transport` (an open channel's ions down their gradient; a carrier's cycles —
`transporter: sglt1`, `ncx`, `glut1`…; the pump's Post–Albers cycle with ATP → ADP + Pᵢ;
`h_atpase`, `abc_transporter`, `aquaporin`), `diffuse` (a solute, simple diffusion: O₂, CO₂ across
a bilayer, anything in a solution), `osmosis: membrane` and `action_potential: membrane` (needs
voltage-gated Na⁺ and K⁺ channels; an inset trace). In a `cell`: `motor_walk` (kinesin to the +
end, dynein to the − end; `distance`), `endocytosis: cell` (a coated pit at a 300–500 nm view of
the plasma membrane) and `exocytosis: <vesicle id>`. The rules are checked with the reason: Na⁺
through a K⁺ channel, ions through a closed channel, an antiporter moving both solutes one way,
transport against the gradient without ATP or an ion gradient, kinesin to the − end.

```yaml
# processes
- id: firing
  type: molecule
  params:
    membrane: plasma
    potential: -70
    solutes: [K+, Na+]
    molecules: [{kind: ion_channel, id: nav, ion: Na+}, {kind: ion_channel, id: kv, ion: K+}, {kind: na_k_atpase, id: pump}]
  beats:
    - text: "At threshold the neuron fires an action potential."
      actions: [{action_potential: membrane, at: "@threshold"}]
    - text: "The pump spends one ATP to move three sodium ions out and two potassium ions in."
      actions: [{transport: pump, at: "@pump"}]
```

Gene expression is a set of actions on a `gene`. In a `molecule` scene (`gene:` instead of
molecules) it is a close-up with the bases written out: `transcribe` (promoter, TATA box, RNA
polymerase II, the bubble; the template strand read 3′→5′, RNA made 5′→3′), `cap`, `splice`
(lariat), `polyadenylate`, `export` (through a nuclear pore), `translate` (scanning, E/P/A sites,
codon–anticodon pairing with the genetic code, the chain growing N→C, the stop codon and release
factor; the protein written out under the view), `target_er` (SRP, Sec61, signal peptidase; during
translation: `translate` with `codons: 3` first), `glycosylate` (OST, an N-glycan in SNFG symbols),
`fold` (chaperones). In a `cell` scene with the same `gene`: `transcribe`, `export`, `translate`,
`to_golgi`, `secrete` (`to: outside | lysosome | membrane`) follow the products through the cell,
the camera following. Write the gene as `codons: 12` (generated; `introns: 1`, `signal_peptide:
true`, `glycosylation: true`, `seed`), `protein: MALW…` or a `sequence` (the coding strand from +1,
with `introns: [[31, 70]]`). `vidgen validate` checks the gene (introns GU…AG with a branch A, a
start codon, a stop codon in frame, no premature stop) and the order (no translation before export,
no glycosylation outside the ER, only folded proteins leave the ER). Give each step its own beat
with enough words: a step lasts as long as what it shows (3–15 s) and a short beat squeezes it.

```yaml
# gene expression
- id: expression
  type: molecule
  params:
    title: "From gene to protein"
    gene: {id: ins, name: INS, codons: 10, introns: 1}
  beats:
    - text: "RNA polymerase two copies the gene."
      actions: [{transcribe: ins}]
    - text: "The spliceosome cuts the intron out as a lariat."
      actions: [{splice: ins}]
    - text: "The three prime end is cut and the poly A tail added."
      actions: [{polyadenylate: ins}]
    - text: "The messenger RNA leaves the nucleus through a pore."
      actions: [{export: ins}]
    - text: "In the cytosol a ribosome reads it codon by codon, and the chain grows from its N terminus."
      actions: [{translate: ins}]
```

A `pathway` draws a signalling pathway as a graph in SBGN-inspired notation, laid out by itself in
compartment bands (extracellular space, plasma membrane, cytosol, ER, mitochondrion, nucleus:
columns left to right in 16:9, rows top to bottom in 9:16; membrane proteins stand in a row on the
bilayer, the nuclear envelope has pores where arcs cross it). Start from a template —
`gpcr_camp_pka` (glucagon → GCGR → Gαs → adenylyl cyclase → cAMP → PKA → CREB → *PCK1*, PDE4),
`rtk_ras_mapk` (EGF → EGFR → Grb2/SOS → Ras → Raf → MEK → ERK → Elk-1 → *FOS*, RasGAP, ERK ⊣ SOS),
`pi3k_akt` (RTK → PI3K → PIP3, PTEN, PDK1/mTORC2 → Akt ⊣ TSC2 ⊣ Rheb → mTORC1, ⊣ GSK3β, ⊣ FOXO) —
and change it (`nodes` with a template id change that node, `edges` between the same nodes replace
its arc, `remove: [gluconeogenesis]`), or write your own. Nodes: `{id, kind, label, in, gene, state,
marks}`; kinds `ligand`, `receptor`, `protein`, `kinase`, `phosphatase`, `g_protein`, `gtpase`, `gef`,
`gap`, `adaptor`, `enzyme`, `transcription_factor`, `complex`, `small_molecule`, `gene` (italic
symbol), `phenotype` (an outcome), `drug`; `in:` the compartment (default by kind). Arcs: `"a -> b"`
activates, `"a -| b"` inhibits, `"a -o b"` catalyses, `"a => b"` translocates (the same label in
another compartment), or `{from, to, type: phosphorylates, site: Ser133, effect: inhibits, feedback:
true, label}` with types `phosphorylates`, `dephosphorylates`, `binds`, `transcribes`, `expresses`,
`converts`. `vidgen validate` refuses what cannot be, with the reason: an unknown node, a GAP that
activates its GTPase, a phosphatase that phosphorylates, a gene outside the nucleus, a transcription
factor in the cytosol transcribing a gene, cAMP in the membrane, a gene or protein name in the wrong
case for the `species`; it warns about a loop no arc declares `feedback: true`. Then the actions:
`signal` (wave by wave: GDP → GTP, pS133 appear), `inhibit`, `knockout` and `drug` (the nodes
downstream that change get ↑ / ↓, computed from the graph), `amplify`, `focus`, `highlight`.

```yaml
# signalling pathways
- id: camp
  type: pathway
  params:
    title: "Glucagon signalling"
    template: gpcr_camp_pka                        # or rtk_ras_mapk, pi3k_akt; or nodes + edges
  beats:
    - text: "Glucagon binds its receptor, and the signal runs through cyclic AMP and PKA to the nucleus."
      actions: [{signal: glucagon, at: "@signal"}]
    - text: "A phosphodiesterase inhibitor keeps cyclic AMP high."
      actions: [{drug: pde, name: IBMX}]
```

A `cell_cycle` draws the eukaryotic cell cycle (`mode: cycle`: a ring G1 → S → G2 → M with G0, the
restriction point and the G1/S, G2/M and spindle assembly checkpoints, beside the levels of cyclin
D–CDK4/6, E–CDK2, A–CDK2 and B–CDK1 in their textbook order of rise and fall, a "now" marker on both)
or a dividing cell (`mode: mitosis | meiosis`, `chromosomes: 4` = 2n: homologues in maternal and
paternal colours, sister chromatids joined at the centromere; prophase … cytokinesis with
condensation, envelope breakdown, kinetochore capture, bi-orientation, separase and cohesin, the
contractile ring — `cell: plant` a cell plate; meiosis with synapsis, crossing over (`crossovers:
[[0.75], [0.6]]`, exchanged segments shown), independent assortment (`assortment: [m, p]`) and four
haploid cells). Captions name each stage; a counts line gives chromosomes, chromatids, n / 2n and C
per cell. `advance` moves it on (`to:` a point of the cycle or a stage); `checkpoint` shows a
checkpoint passing or arresting the cell with its regulators (p53 → p21 ⊣ CDK2…). `vidgen validate`
refuses what cannot be, with the reason: G0 after the restriction point, advancing past an arrested
checkpoint, an odd 2n, a bivalent without a crossover, wrong counts in `expect`, a stage of the
other division.

```yaml
# cell cycle and division
- id: meiosis
  type: cell_cycle
  params:
    title: "Meiosis (2n = 4)"
    mode: meiosis                     # or mitosis, or cycle (the cycle with its cyclins and checkpoints)
    assortment: [m, p]                # which homologue faces the first pole at metaphase I, per pair
  beats:
    - text: "Homologues pair, cross over and part; then sisters: four haploid cells."
      actions: [{advance: cell, to: cytokinesis_ii, at: "@pair"}]
```

A `metabolism` scene draws energy metabolism: `process: glycolysis` (ten steps, investment and
payoff phases, net 2 ATP and 2 NADH per glucose; `link: true` adds pyruvate dehydrogenase in the
matrix), `link_reaction`, `tca` (the citric acid cycle as a ring: 3 NADH, FADH₂, GTP, 2 CO₂ per
turn), `etc` (complexes I–IV, Q and cytochrome c in the inner mitochondrial membrane, protons
pumped into the intermembrane space, O₂ → H₂O, ATP synthase) or `light_reactions` (PSII splitting
water, PQ, b₆f, PC, PSI, Fd, FNR making NADPH, ATP synthase with CF₁ in the stroma). Tallies count
the products. `advance` animates it: a token through the steps (`to: pyruvate`), electrons along the
chain with protons crossing (`to: complex_iv`, `from: fadh2`), the gradient through ATP synthase
(`to: atp_synthase`). Checked with the reason: the membrane (`membrane: plasma` for the respiratory
chain is refused), `protons_to` the wrong side, `components` out of order or missing a carrier,
glycolysis outside the cytosol, the light reactions in an animal cell, ATP synthase before any
protons were pumped.

```yaml
# energy metabolism
- id: krebs
  type: metabolism
  params:
    title: "The citric acid cycle"
    process: tca                      # glycolysis, link_reaction, tca, etc, light_reactions
  beats:
    - text: "Acetyl-CoA joins oxaloacetate; two carbons leave as CO2."
      actions: [{advance: tca, to: succinyl_coa, at: "@joins"}]
    - text: "The cycle closes with GTP, FADH2 and NADH."
      actions: [{advance: tca, to: oxaloacetate}]
```

A `cross` scene works a genetic cross out exactly (the cross engine, fractions, no hand-written ratios) and draws it: the parents with their homologous chromosomes and phenotype pictures (peas, flowers, flies, coats, blood groups…), their gametes (each allele in the colour of the homologue it came from; recombinants of linked loci ringed, with their frequencies), a Punnett square up to 4 × 4 (8 × 8 with `show: punnett`) or a branch (forked-line) diagram beyond, and the offspring counted into genotype and phenotype classes — exact fractions in lowest terms, percentages, the whole-number ratio (9 : 3 : 3 : 1, 9 : 3 : 4, 2 : 1 with the lethal class crossed out; X-linked crosses split by sex, X and Y in the headers). Use a `preset` (pea_seed_shape, pea_dihybrid, snapdragon, abo, rabbit_coat, labrador, squash_colour, chicken_feathers, shepherds_purse, sweet_pea, squash_shape, yellow_mouse, drosophila_white, hemophilia_a, drosophila_b_vg) or write the `loci`. Genotypes are textbook notation: `RrYy`, `I^A i`, `X^H X^h`, `X^h Y`, linked loci with their phase `AB/ab`. `P: [RRYY, rryy]` crosses the P generation to its F1 and shows the F2; `kind: test` makes the tester; `kind: reciprocal` swaps the sexes of the lines. `observed` counts add a chi-square table (χ², df, p, the critical value, the verdict). Without cross actions the scene plays itself beat by beat; `form_gametes`, `fill` (`square`, `row2`, `cell1.3`, `"cells:wrinkled, green"`; `by: row`), `count` (`phenotypes` / `genotypes`), `ratio` and `chi_square` (`test`) put each step on a word, and `highlight` marks a class's cells (`style: box`). Checked with the reason: alleles that do not exist (did you mean…), X-linked alleles off their X, a female with a Y, linked loci without their phase, RF over 0.5, a P generation that is not true-breeding, counts for classes the cross does not have, a cell filled twice.

```yaml
# genetics
- id: dihybrid
  type: cross
  params:
    title: "A dihybrid cross"
    preset: pea_dihybrid               # or loci: [{gene: R, trait: seed shape, alleles: {R: round, r: wrinkled}}, ...]
    parents: [RrYy, RrYy]              # P: [RRYY, rryy] for P → F1 → F2; kind: test with one parent
  beats:
    - text: "Each parent makes four kinds of gametes, in equal numbers."
      actions: [{form_gametes: both, at: "@four"}]
    - text: "Sixteen equally likely combinations fill the square."
      actions: [{fill: square, by: row}]
    - text: "Counted, they give nine to three to three to one."
      actions: [{count: phenotypes}, {ratio: phenotypes, at: "@nine"}]
```

A `pedigree` scene draws a family chart in standard human pedigree nomenclature (NSGC: square male, circle female, diamond sex unknown; affected filled, a carrier a dot — `carrier_style: half` for the half-shaded heterozygote —, deceased struck, the proband's arrow with P, double line for consanguinity, MZ / DZ twins, adoption brackets, a miscarriage triangle, a proposed child dashed with ?) laid out by generation (Roman numerals, individuals numbered left to right, sibships in birth order, partners from outside beside the relative), and works its genetics out exactly: which modes of inheritance fit (AD, AR, XD, XR, Y-linked, mitochondrial; an excluded one with its reason, e.g. *father-to-son: a son's X comes from his mother*), the genotypes the chart forces (obligate carriers), carrier probabilities by Bayes' rule on the whole chart (2/3 for an unaffected sibling under AR), and the risk for a proposed child with its factors (2/3 × 1/25 × 1/4 = 1/150). Write each person as a line — `"II-3: female affected deceased of I-1 + I-2"`, flags `carrier`, `proband`, `consultand`, `proposed`, `miscarriage`, `adopted in`, `twin II-4 MZ`, `spouse II-5`, `age 45 y` last — or as a mapping (`{id, sex, affected, parents: [I-1, I-2], twin: {with, kind}}`). Use NSGC ids (`II-3`, numbered left to right as drawn: a partner from outside stands beside the relative) or any names (schu-video-generator numbers the chart). The analysis assumes a rare allele (people marrying in do not carry it: `rare: false` or `carrier_frequency: 1/25` for a common one) and full penetrance (`penetrance: 0.8` lets a dominant trait skip a generation). `mode` sets the mode for genotypes and risk (default: the only one that fits; `preset: hemophilia_a` gives X-linked recessive with H / h). The actions: `analyse: modes` (one by one, the people a reason names ringed; `mode:XR` for one), `deduce: genotypes` (`carriers`, `generation:II`, `person:II-3`), `risk: risk`; `reveal: "generation:II"` or `"person:II-3"` brings people in on a word, `highlight` marks them. Checked with the reason: a child with two fathers, a cycle, twins who are not siblings, numbers that do not read left to right, a male carrier under X-linked inheritance, genotypes or risk when several modes fit and none is stated.

```yaml
# genetics
- id: family
  type: pedigree
  params:
    title: "Who carries the allele?"
    condition: cystic fibrosis
    carrier_frequency: 1/25            # for people marrying in; mode: AR is the only mode that fits
    individuals:
      - "I-1: male"
      - "I-2: female"
      - "II-1: male of I-1 + I-2"
      - "II-2: female affected proband of I-1 + I-2"
      - "II-3: male of I-1 + I-2"
      - "II-4: female"                 # married in, beside II-3
      - "III-1: unknown proposed of II-3 + II-4"
  beats:
    - text: "Unaffected parents, an affected daughter: only a recessive mode fits."
      actions: [{analyse: modes}]
    - text: "Her brother is a carrier with probability two thirds; the risk is one in 150."
      actions: [{deduce: genotypes}, {risk: risk, at: "@risk"}]
```

A `linkage_map` scene shows linked genes: the heterozygous parent's homologue pair (sister chromatids joined at the centromere, maternal and paternal colours) with its alleles, and crossing over in an interval — the non-sister chromatids meet at a chiasma and swap the segments beyond it, giving recombinant chromatids (labelled with their alleles). With `loci` and `counts` it works a two- or three-point test cross out step by step: the table of offspring classes, the parental classes (the largest reciprocal pair; they give the phase, coupling or repulsion) and the double crossovers (the smallest), the gene order (the locus at which a double crossover differs from a parental class is in the middle), each interval's recombinants, RF and distance, the expected and observed double crossovers with the coefficient of coincidence and the interference, and the map. Write each class with every locus once: the mutant allele by its symbol, the wild type as `v+` or `+` (`"v cv+ ct+": 580`). Distances are RF × 100 cM (`map_function: none`, what three-point analyses report; right below ~15 cM) or Haldane's / Kosambi's map function. With `map: {y: 0, w: 1.5, v: 33}` the loci stand at their positions; `measure: "interval:w-v"` shows a distance and the RF it gives. `cross_over: "interval:v-ct"` (or `double`) plays the crossing over on a word; `reveal: order` (or `table`, `classes`, `distances`, `interference`, `map`) plays a step. Checked with the reason: missing or doubled classes, an unknown locus, parental or double-crossover pairs that cannot be told, a crossover between loci that are not neighbours.

```yaml
# genetics
- id: map
  type: linkage_map
  params:
    title: "Mapping three genes"
    loci: [v, cv, ct]                  # mutant alleles, any order: the order is worked out
    counts: {"v cv+ ct+": 580, "v+ cv ct": 592, "v cv ct+": 45, "v+ cv+ ct": 40, "v cv ct": 89, "v+ cv+ ct+": 94, "v cv+ ct": 3, "v+ cv ct+": 5}
  beats:
    - text: "Crossing over gives recombinant gametes; the rarest classes are double crossovers."
    - text: "So ct lies in the middle, 13.2 and 6.4 centimorgans from its neighbours."
```

A `karyotype` scene draws a human karyotype from its ISCN notation, checked: the count against the chromosomes listed (`47,XX` lists 46: write 46,XX), the sex chromosomes, each change and its bands (`5p16` does not exist: 5p ends at 5p15). Supported: `+21`, `-21`, `del(5)(p15.2)`, `del(1)(q21q32)`, `dup(1)(q21q32)`, `inv(9)(p12q13)`, `t(9;22)(q34;q11.2)`, `rob(14;21)(q10;q10)`; sex chromosome aneuploidy in the sex chromosomes (`45,X`, `47,XXY`). `show: karyogram` (default for numerical changes) arranges the pairs 1–22, X, Y in the Denver groups A–G with schematic G-banded ideograms (true relative lengths and centromere positions; satellites on 13, 14, 15, 21, 22) and highlights the change; `show: ideogram` (default when every change is structural, or with `chromosomes: [7]`) draws the chromosomes involved large, with p and q and `bands: {7q31.2: CFTR}` labelled, and plays each structural change as an edit — a deletion falls away, an inversion turns round, a translocation's segments swap, a Robertsonian translocation joins two long arms. A card reads the notation (and names the classic condition: Down, Turner, Klinefelter, cri-du-chat, the Philadelphia chromosome…). The band pattern is schematic: say "band q31" but do not read exact positions off it. `rearrange: change:1` plays a change on a word.

```yaml
# genetics
- id: karyotype
  type: karyotype
  params:
    title: "Trisomy 21"
    karyotype: "47,XY,+21"             # or 46,XX,t(9;22)(q34;q11.2): its edit plays in an ideogram
  beats:
    - text: "A male karyotype, its chromosomes in pairs by size, three copies of chromosome twenty-one."
    - text: "Forty-seven, X Y, plus twenty-one: Down syndrome."
```

A `mutation` scene works a sequence variant out on a real coding sequence with the genetic code: the reference codons with their amino acids (the initiator Met is residue 1) and the variant row made from them — a base swaps, or bases leave or come in and the rest slide through the fixed codon frame, so a frameshift regroups every codon after it and reaches its premature stop. Give a reference window (`gene: HBB`, `CFTR`, `GJB2`: real coding sequence with its exons and transcript), your own `sequence:` (with `first:`, `exons:`, `length:` when you want splice sites and nonsense-mediated decay), or a gene like a `molecule` scene's (`gene: {protein: MVHL…, introns: 1}`). The `variant:` is HGVS on the coding DNA (`c.20A>T`, `c.1521_1523delCTT`, `c.35delG`, `c.35dup`, `c.76_77insT`, `c.76_77delinsTT`, `c.92+1G>A`); schu-video-generator computes the protein change (`p.(Glu7Val)`, `p.(Phe508del)`, `p.(Arg553*)`, `p.(Gly12Valfs*2)`, `p.?` for a splice site with the exon skipped or the intron retained), the class and the notes (side chains, the frame, nonsense-mediated decay), and checks a `p:` you write against the sequence. Use `legacy:` for the old name (ΔF508, Glu6Val: HGVS counts the initiator Met, so HbS is `c.20A>T p.(Glu7Val)`). A list of variants plays one after another; `mutate: variant` puts one on a word. Checked with the reason: a change that is not HGVS, a reference base that is not there, a description that is not the canonical one (the 3′ rule), a stated `p.` that does not follow, `p.R553X` and `ΔF508`.

```yaml
# genetics
- id: sickle
  type: mutation
  params:
    title: "Sickle-cell haemoglobin"
    gene: HBB                                  # or sequence: ATGGTG…, or gene: {protein: …, introns: 1}
    variant: {c: "c.20A>T", p: "p.(Glu7Val)"}  # p. is checked; legacy name Glu6Val
  beats:
    - text: "The start of the beta-globin coding sequence, read in codons."
    - text: "One base changes: A to T in codon seven."
      actions: [{mutate: variant, at: "@changes"}]
    - text: "Glutamic acid becomes valine: sickle-cell haemoglobin."
```

A `crispr` scene shows Cas9 editing a target: the DNA with every base, the sgRNA's 20-nt spacer (21–23 for SaCas9) pairing with the target strand, the PAM (`NGG`; `NNGRRT` for SaCas9) right after the protospacer's 3′ end on the other strand, the R-loop, the blunt double-strand break 3 bp upstream of the PAM, and the repair: `nhej` (a small indel — `indel: +1` is the commonest, and an indel that is not a multiple of 3 is a frameshift knockout) or `hdr` (a donor carrying `edit:`). Leave `spacer` out and schu-video-generator picks a guide from the PAMs it finds (`guide: 2` for the n-th); with `coding_first:` (the `c.` number of the target's first base) the outcome is written in HGVS with its protein change. `scan`, `cleave` and `repair` put the steps on words. Checked with the reason: a spacer that is not in the target or has no PAM after it (with the guides that would work), the wrong length for the enzyme, a spacer written with its PAM, a target without any PAM.

```yaml
# genetics
- id: edit
  type: crispr
  params:
    title: "Cutting with Cas9"
    target: "GACTGCATCAGCTGAAGGTCACCATGGTGCATCTGACTCCTGAGGAGAAGTCTGCC"
    repair: nhej                       # or hdr with edit: 25A>T (c.20A>T with coding_first)
  beats:
    - text: "The guide binds beside its PAM, and three base pairs away both strands break."
      actions: [{scan: dna}, {cleave: dna, at: "@break"}]
```

A `dna_lab` scene shows one laboratory method. `method: pcr`: the primers checked against the template (the forward primer repeats the top strand, the reverse primer is the reverse complement downstream), the product's length, melting temperatures and an annealing temperature ~5 °C below them, the temperature trace (denature ~95 °C, anneal, extend 72 °C with Taq) and the copies — 2ⁿ molecules after n cycles, 2ⁿ − 2n of exactly the product's length, the first in cycle 3. `method: gel`: an agarose gel, DNA running from the wells at the cathode to the anode, the distance log-linear in size within the gel's range, a `ladder` and each band's size read off it. `method: sanger`: chain termination with ddNTPs, the fragments sorted by length and a chromatogram with the called bases (`heterozygous: "8T>C"` gives two half-height peaks and a Y). `method: ngs`: seeded reads aligned to a reference with their coverage and a variant call (≈50 % alt reads: heterozygous). `run: <step>` plays a step on a word (the steps before it play first).

```yaml
# genetics
- id: pcr
  type: dna_lab
  params:
    title: "PCR"
    method: pcr
    template: "GCTTACCAGTCGATGCCATGACTGCATCAGCTGAAGGTCACCATGGTGCATCTGACTCCTGAGG"
    primers: {forward: "GACTGCATCAGCTGAAGGTC", reverse: "CCTCAGGAGTCAGATGCACC"}
  beats:
    - text: "A template, two primers, and a product of a defined length."
    - text: "The strands separate, the primers anneal, Taq extends them."
      actions: [{run: trace}]
    - text: "The molecules double every cycle."
      actions: [{run: counts}]
```

A `population` scene shows population genetics. `model: hardy_weinberg` (the default) draws the population as dots by genotype and works the numbers out exactly, one step a beat: p and q from genotype `counts` (or `frequencies`, `p`, or the `incidence` of a recessive condition: q = √incidence, so 1/2500 gives q = 1/50 and carriers 2pq = 49/1250 ≈ 1 in 25.5, about 2q), the expected p², 2pq, q² (with `inbreeding` F: p² + Fpq, 2pq(1 − F), q² + Fpq) and, from counts, the chi-square test of Hardy–Weinberg proportions with df = 1 (three genotypes − 1 − one estimated allele frequency). Simulations are seeded Wright–Fisher runs of N diploids (2N gene copies drawn each generation): `drift` (replicate lines from `p0`; fixation and loss; heterozygosity falling as H₀(1 − 1/2N)ᵗ), `selection` (`fitness` of AA, Aa, aa, or `s` and `h`; the deterministic course as a thick line, drifting lines around it with `N`), `mutation` (`mu`, `nu`), `migration` (two `populations` and `m`), `bottleneck` (`{at, N, generations}`) and `founder` (`founders` from a source at `p0`). `simulate: "generation:40"` grows the lines on a word, `resample: population` draws the next generation, `reveal: chi_square` plays a Hardy–Weinberg step, `highlight: fixed` marks the lines that fixed. Checked with the reason: frequencies outside [0, 1], genotype frequencies that do not add up to 1, counts that do not add up to the `total`, negative fitness, a param of another model.

```yaml
# genetics
- id: drift
  type: population
  params:
    title: "Genetic drift"
    model: drift                       # or hardy_weinberg with counts / incidence, selection, migration, bottleneck, founder
    N: 20
    p0: 0.5
    generations: 50
    replicates: 3
    seed: 36
  beats:
    - text: "Three populations of twenty individuals start at one half."
    - text: "Each generation samples only forty gene copies: some lines fix the allele, others lose it."
      actions: [{simulate: lines}]
```

```yaml
# genetics
- id: carriers
  type: population
  params:
    title: "Carriers of cystic fibrosis"
    incidence: 1/2500                  # q² = incidence for a recessive condition
    condition: cystic fibrosis
  beats:
    - text: "One baby in two thousand five hundred has cystic fibrosis, so q is one in fifty."
    - text: "Two p q: about one person in twenty-five carries the allele."
      actions: [{reveal: carriers}]
```

A `gwas` scene draws a genome-wide association study: a Manhattan plot of −log₁₀ p along chromosomes 1–22 (alternating colours; X with `x_chromosome: true`), the genome-wide significance line at 5 × 10⁻⁸ and the suggestive line at 1 × 10⁻⁵, peaks labelled with their gene or lead variant; `plot: qq` or `both` adds a QQ plot with λ_GC; `regional: "peak:FTO"` (an action or a param) zooms into a locus with its variants coloured by r² with the lead. Give real data as `data: assoc.csv` (columns CHR, BP, P, SNP…; lead variants are clumped and labelled from `labels: {rs9939609: FTO}`) or `variants:` inline — or `peaks:` for a seeded synthetic study (a null background and your peaks with LD around them), which the plot labels "simulated data": never present synthetic peaks as a real study's results. Checked: p-values outside (0, 1], unknown chromosomes, positions written in Mb as bp or past the chromosome's end.

```yaml
# genetics
- id: gwas
  type: gwas
  params:
    title: "A genome-wide association study"
    trait: body mass index
    peaks:                             # synthetic (shown as simulated data); or data: assoc.csv
      - {chromosome: 16, position: 53.8 Mb, p: 1e-40, gene: FTO}
      - {chromosome: 18, position: 60.2 Mb, p: 2e-14, gene: MC4R}
  beats:
    - text: "Every dot is a variant tested for association with body mass index."
    - text: "Two loci pass genome-wide significance, five times ten to the minus eight."
      actions: [{reveal: thresholds}, {reveal: peaks, at: "@loci"}]
```

In `cell_cycle` meiosis, `nondisjunction: {division: I, pair: 1}` makes that pair's homologues go to one pole at anaphase I (every gamete n + 1 or n − 1), `division: II` its sister chromatids stay together at anaphase II in one cell (half the gametes normal); the gametes are labelled and the last caption gives the zygotes after fertilisation (trisomic, monosomic, euploid).

Accuracy and sources. `vidgen lint` checks the science of these scenes (and of any narration)
with the `science_*` rules: sizes far off scale on a `cell` with a scale bar (set `not_to_scale:
true` when you exaggerate on purpose: the scene then says so), places ("glycolysis in the
mitochondria", "ribosomes in the nucleus" while the picture has them in the cytosol), directions
(RNA made 3′ to 5′, a protein made C to N, kinesin to the minus end, protons pumped into the
matrix), active transport through a channel or with no energy source shown, gene / protein names
(mouse *Trp53* gene, TRP53 protein; `<i>…</i>` for a gene in a label), narration against a
pathway arc ("Akt activates TSC2" where Akt's arc inhibits it) and numbers (net 2 ATP from
glycolysis, 3 NADH per turn, 3 Na⁺ out and 2 K⁺ in per pump cycle). Fix the words, or the
picture. Give a scene `references:` — `{label, doi | pmid | isbn | url, id}` copied from your real
sources, **never invented** (no identifier you have not seen; leave a reference out rather than
guess) — and they appear as small citations (`citations: {show: footer | marker | card | none}`,
numbered across the video; a beat's `cite: [id]` shows only what it cites) and as a numbered list
in the description file `<output>_chapters.txt`. A real micrograph shown with an `image` scene
gets `figure_credit: {text, license, url}`. How to choose, keep it correct and pace a dense
script: `vidgen guide biology` and `docs/COOKBOOK-CELL-BIOLOGY.md` (example:
`examples/gene-to-secreted-protein`).

The genetics scenes are checked the same way by the `genetics_*` rules, against what each scene
computes: a ratio or share the `cross` does not give ("a 3:1 ratio" for a dihybrid — say "each
trait alone segregates 3:1" if you mean one trait —, "half the daughters affected" for a carrier
mother), a `pedigree` that does not fit its `mode` (an error), "a dominant trait skips a
generation" without reduced penetrance, father-to-son transmission of an X-linked trait, a carrier
or risk probability the chart does not give ("II-3 is a carrier with probability 1/2" where it is
2/3), RF over 50 % or a distance against the `linkage_map`, Hardy–Weinberg slips (carriers are
2pq, not q²; q = √incidence), a wrong PAM or cut for the Cas (SpCas9: NGG, a blunt cut 3 bp
upstream of the PAM), karyotype notation and the condition or sex it names ("45,X is female",
`47,XY,+18` is not trisomy 21; changes in ISCN order), and HGVS that is not the `mutation`'s
variant or uses the legacy numbering unannounced (HbS is p.(Glu7Val); say "legacy Glu6Val");
`ΔF508` and `R553X` are reported as info — write the HGVS form and call the old one legacy.
Say numbers exactly as the scene computes them (or with "about"); conditional and comparative
sentences ("if both parents are carriers…", "unlike Down syndrome…") are not read. Choosing among
the genetics types, notation, exactness and pacing: `vidgen guide genetics` and
`docs/COOKBOOK-GENETICS.md` (example: `examples/cystic-fibrosis`).

Numbers in calculations and plots are checked too. The `calc_*` rules read the numbers the
narration and the screen say — in digits or words: "thirty kilometres per second", "eleven point
two", "three point seven times ten to the minus nineteen joules", "one in a hundred and fifty" —
against what each `calculation` scene computes (`calc_numbers`: a value that is not the result,
"about" allows rounding to one or two figures; `calc_units`: "a speed of 30 kilometres", or 30 m/s
for 29.8 km/s; `calc_sigfigs`, info: "29.7847 km/s" for a result known to 3 figures, or a `sig`
beyond the inputs). Give each symbol and result a `meaning`: a pure number ("one in a hundred and
fifty") is only compared when the sentence names it. The `plot_*` rules check a `plot`: an axis of
a physical quantity without its unit (`plot_units`), error bars, fits or lines at or below zero on
a log axis (`plot_log`), error bars without `error:` (sd, sem, ci95…) or called something else in
the narration (`plot_errors`), series without a legend or label (`plot_series`), bars not starting
at zero (`plot_truncated`, info; also a `bar_chart` `baseline`), a model's `conserved` quantity
drifting (`plot_conserved`: use `method: leapfrog` or a smaller `step`), and a fitted value said
otherwise ("a half-life of twelve days" for a fit giving 8.0 ± 0.1 d; `plot_fit_claims`).
Choosing between a plot and a chart, fits, live models, units and pacing for calculations: `vidgen
guide science` and `docs/COOKBOOK-SCIENCE-CHARTS.md` (example: `examples/radioactive-decay`).

```yaml
# accuracy and references
- id: er
  type: cell
  params:
    objects: [{kind: vesicle, id: big_vesicle, size: "400 nm"}]   # larger than real: say so
    not_to_scale: true
  references:                          # placeholders here: copy the real identifiers from your sources
    - {id: book, label: "Example textbook (placeholder)", isbn: "978-0-00-000000-2"}
  beats:
    - text: "Transport vesicles carry cargo from the ER to the Golgi."
      cite: [book]
```

```yaml
# data
- id: users
  type: stat
  params:
    value: 73
    suffix: "%"
    label: "of developers use AI tools"
    comparison: {value: 44, label: "in 2023"}
    context: "Survey of 12,000 developers"
  beats:
    - text: "Almost three in four developers now use AI tools."
    - text: "Two years ago, it was not even half."
- id: speed
  type: bar_chart
  params: {title: "Render time per minute", labels: ["480p", "1080p", "4K"], values: [0.4, 2.6, 9.8], unit: " min", caption: "Measured on 2 CPUs"}
  beats:
    - text: "Higher resolutions take much longer."
    - text: "Four K is twenty-five times slower than a preview."
      actions: [{highlight: "bar:4K", style: box}]
- id: loss
  type: line_chart
  params:
    title: "Validation loss"
    x: [1, 2, 3, 4, 5]
    x_label: "epoch"
    series: {baseline: [2.1, 1.8, 1.66, 1.58, 1.53], sparse: [2.2, 1.9, 1.68, 1.55, 1.49]}
  beats:
    - text: "The baseline improves steadily."
    - text: "The sparse model starts slower, but ends lower."
- id: ranking
  type: bar_chart
  params:
    title: "Most loved languages"
    labels: [Python, Rust, Go]
    values: [62, 48, 31]
    changes: [[58, 66, 30], [55, 72, 41]]   # the values at each later step; bars grow / shrink
    sort: true                              # and re-sort, largest first
    unit: "%"
  beats:
    - text: "In the first survey, Python led."
    - text: "A year later Rust overtook it."
    - text: "Then Go climbed as well."
      actions: [{reveal: change2, at: "@climbed"}]   # change 2 on that word
- id: training
  type: line_chart
  params:
    title: "Training loss"
    x: [1, 2, 3, 4]
    series: {loss: [2.4, 1.8, 1.4, 1.2], accuracy: [0.3, 0.5, 0.6, 0.65]}
    changes: [{loss: [1.0, 0.5, 0.3, 0.2]}]   # series left out keep their values; the y axis rescales
    reveal: all
  beats:
    - text: "Here is the loss over four epochs."
      actions: [{trace: "series:loss", to: 3, at: "@four"}]   # a cursor dot with the value sweeps the line
    - text: "With pretraining it starts far lower."
- id: size_vs_accuracy
  type: scatter
  params:
    title: "Size vs accuracy"
    x_label: "parameters (billions)"
    y_label: "accuracy (%)"
    trend: all
    series: {baselines: [[1.3, 61], [6.7, 70], [13, 73]], ours: [[1.0, 66], [3.8, 72, "small"]]}
    highlight: "ours@small"
  beats:
    - text: "Bigger baselines score higher."
    - text: "Ours sit above the line."
    - text: "The trend makes the gap clear."
    - text: "Especially for the small one."
- id: latency
  type: histogram
  params:
    title: "Response times"
    x_label: "milliseconds"
    values: [12, 15, 17, 18, 21, 22, 23, 25, 26, 28, 30, 31, 33, 35, 38, 41, 45, 52, 61, 75, 97]
    median: true
  beats:
    - text: "Most requests finish fast."
    - text: "Half of them in under thirty milliseconds."
```

Scientific plots and worked calculations (the craft: `vidgen guide science`):

```yaml
# science charts
- id: decay_fit
  type: plot
  params:
    title: "Fitting the decay"
    x: {label: time, unit: d}
    y: {label: activity, unit: Bq}
    series:   # error bars: y_err (number, list, column, {minus, plus} or sqrt) and what they mean (sd, sem, ci95, range)
      - {name: measured, style: points, x: [0, 4, 8, 14, 20, 30, 40], y: [1000, 712, 494, 302, 180, 73, 32], y_err: 20, error: sem}
    fits:     # linear, poly, exponential, power, logistic, gaussian, breit_wigner (background: n), custom (expr + params)
      - {series: measured, model: exponential, name: decay, band: confidence, residuals: true}
    annotations:   # label, arrow, hline, vline, xrange, yrange, note
      - {type: label, series: measured, x: 8, text: "half after 8 days", id: half}
  beats:
    - text: "The measured activity, with its error bars."
    - text: "An exponential fits the points, with its parameters and their errors."
      actions: [{fit: "fit:decay", at: "@exponential"}]
    - text: "After eight days, half is left."
      actions: [{annotate: "annotation:half", at: "@half"}]
- id: decay
  type: plot
  params:
    title: "Activity of an iodine-131 sample"
    x: {label: time, unit: d}
    y: {label: activity, unit: Bq, scale: log}
    # from a file: data: assets/decay.csv, then x: time, y: activity name its columns
    series:
      - {name: measured, style: points, x: [0, 4, 8, 14, 20, 30, 40], y: [1000, 712, 494, 302, 180, 73, 32]}
      - {name: "model, half-life 8.0 d", dashed: true, x: [0, 40], y: [1000, 31.25]}
  beats:
    - text: "The activity halves every eight days."
    - text: "On a log axis that decay is a straight line."
- id: oscillator
  type: plot
  params:
    title: "A damped oscillator"
    models:   # ode (equations, initial, params, t, method: rk4 | rk45 | leapfrog), recurrence, random_walk, poisson, function
      osc:
        kind: ode
        equations: {x: v, v: "-k*x - c*v"}   # x' = v, v' = -k x - c v
        params: {k: 4, c: 0.3}
        initial: {x: 1, v: 0}
        t: [0, 20]
        units: {t: s, x: m, v: m/s}
    arrange: columns
    share: false
    legend: false
    panels:   # a model's series grow live over their beat; readout: the current value; trail: a fading path
      - series: [{name: position, x: t, y: x, readout: true}]
      - series: [{name: phase, x: x, y: v, trail: 3}]
  beats:
    - text: "Friction takes the energy away, so each swing is smaller."
    - text: "In phase space the state spirals in towards rest."
      actions: [{zoom: panel1, x: [0, 5], at: "@phase"}]
- id: orbit_speed
  type: calculation   # formula -> values with units -> result with significant figures -> conversion
  params:
    title: "How fast does the Earth orbit the Sun?"
    symbols:   # value: a number with its unit ("29.8 km/s", "1/25", "6.674e-11 m^3 kg^-1 s^-2"), or a constant (CODATA / IAU)
      - {name: G, constant: G}
      - {name: M_sun, constant: M_sun}
      - {name: r, constant: AU, meaning: "Earth–Sun distance"}
    calculations:   # expr uses the symbols' names; a later calculation may use an earlier result's name
      - {name: v, expr: "sqrt(G*M_sun/r)", sig: 3, convert: km/s, meaning: orbital speed}
  beats:
    - text: "Gravity holds the Earth on its orbit, so its speed is the square root of G M over r."
    - text: "Put in the numbers, and the Earth moves at about thirty kilometres per second."
      actions: [{substitute: calc1, at: "@numbers"}, {compute: calc1, at: "@moves"}]
```

Planets, moons and spacecraft on their orbits, in correct timing (the craft: `vidgen guide orbits`):

```yaml
# orbital mechanics
- id: inner_planets
  type: orbit   # bodies move by Kepler's equation at one speed-up from the first beat to the scene's end
  params:
    title: "The inner planets for one Earth year"
    central: sun   # a preset (sun, earth, mars, jupiter...) or {name, gm or mass, radius}
    bodies:        # presets: mercury ... neptune (JPL J2000 elements), moon, iss, geo, halley
      - {preset: mercury}
      - {preset: earth}
      - {name: Comet, a: "1.5 AU", e: 0.7, argp: 180, nu: 180, trail: 0.15}   # values carry units; angles in degrees
    span: "1 yr"   # or orbits: 2 (periods of the first body)
    caption: "J2000 elements (JPL approximate positions)"
  beats:
    - text: "Mercury races around the Sun in eighty-eight days."
    - text: "The comet crawls far out and sweeps past the Sun."
- id: kepler_laws
  type: orbit
  params:
    title: "Equal areas in equal times"
    bodies:
      - name: Comet
        a: "3 AU"
        e: 0.75
        nu: 150
        geometry: true        # foci, a and b, perihelion / aphelion with their distances
        sectors: 8            # Kepler II: 8 equal times, each area computed and listed
        velocity: {along: 12} # arrows ∝ speed with a key, the vis-viva speed in the panel
    orbits: 1.2
  beats:
    - text: "The Sun sits at one focus; the other is empty."
      actions: [{reveal: "foci:Comet", at: "@focus"}]
    - text: "From now on we sweep eight equal times."
      actions: [{sweep: "sectors:Comet", at: "@sweep"}]
- id: newtons_cannon
  type: orbit
  params:
    title: "Newton's cannonball"
    central: earth
    cannonball: {altitude: "1500 km", speeds: [0.6, circular, 1.2, escape, 1.6]}   # × circular speed; classified by energy
    span: "6 h"
  beats:
    - text: "Too slow, it falls back; at the circular speed it falls around the Earth."
      actions: [{launch: "shot:1", at: "@slow"}, {launch: "shot:2", at: "@circular"}]
    - text: "Faster, an ellipse; at the escape speed it never returns."
      actions: [{launch: "shot:3", at: "@ellipse"}, {launch: "shot:4", at: "@escape"}, {launch: "shot:5"}]
- id: to_mars
  type: orbit
  params:
    title: "Earth to Mars"
    bodies:
      - {preset: earth, e: 0, i: 0, raan: 0, argp: 0}   # a transfer is between circular, coplanar orbits
      - {preset: mars, e: 0, i: 0, raan: 0, argp: 0, nu: 75}
      - {name: Ship, alongside: Earth}
    transfer: {ship: Ship, to: Mars}   # Hohmann: Δv₁, Δv₂, 259 d, phase angle 44.3°, windows every 780 d
    caption: "Circular, coplanar orbits (an approximation)"
  beats:
    - text: "We wait for Mars to lead by forty-four degrees, then burn."
      actions: [{burn: "burn:1", at: "@burn"}]   # the clock runs so the burn falls on this word
    - text: "Two hundred and fifty-nine days later Mars is there."
      actions: [{burn: "burn:2", at: "@there"}]
- id: gravity_assist
  type: orbit
  params:
    title: "A gravity assist at Jupiter"
    central: jupiter
    flyby: {v_inf: "5.6 km/s", altitude: "400000 km", angle: 100, side: behind}   # δ, asymptotes, Sun-frame vectors
  beats:
    - text: "Passing behind Jupiter, the probe leaves faster around the Sun."
      actions: [{action: flyby, at: "@behind"}]   # the closest approach on this word
- id: trojans
  type: orbit
  params:
    title: "Trojans of Jupiter"
    system: sun_jupiter   # earth_moon, sun_earth, sun_jupiter, {primary, secondary, mu}, figure_eight
    lagrange: true        # L1–L5 for the mass ratio; Routh's test and the Jacobi constant in the panel
    bodies:
      - {name: Trojan, near: L4, shift: [0.004, 0.0069], trail: "150 yr"}
    span: "300 yr"
  beats:
    - text: "Seen from the stars, Jupiter and its Trojan go round together."
    - text: "Now let the frame turn with Jupiter: the Trojan traces a tadpole."
      actions: [{action: corotate, at: "@turn"}]   # inertial -> rotating frame on this word
- id: tides
  type: orbit
  params: {central: earth, tides: true}   # a schematic: pull, tidal arrows, bulges, the Moon's near side
  beats:
    - text: "Take away the pull at the centre, and what is left stretches the Earth."
      actions: [{reveal: tidal, at: "@left"}]
- id: mars_opposition
  type: orbit
  params:
    title: "Mars at opposition"
    date: 2020-06-01   # the planets where JPL's approximate elements put them that day (1800–2050); the panel shows the date
    bodies: [{preset: earth}, {preset: mars}]
    event: {kind: opposition, of: Mars}   # the next one after the date (root finding), drawn as the line they will stand on
    caption: "Positions from JPL's approximate planetary elements"
  beats:
    - text: "In mid October the Earth overtakes Mars: Mars is at opposition."
- id: planet_sizes
  type: orbit
  params: {title: "The planets' sizes to scale", sizes: true}   # radii to one scale side by side, the Sun's edge first
  beats:
    - text: "Jupiter is eleven times as wide as the Earth."
```

The Solar System on a date: `date` (1800–2050, refused outside), `event` (opposition,
conjunction, inferior_conjunction, superior_conjunction, aligned; `of`, `observer`), `radial:
log` (every planet in one picture, distances compressed and labelled so, rings instead of axes),
`inset: true` (the inner planets to scale in a box beside a true-scale picture), `sizes` (radii
to scale; `{bodies: [earth, moon, mars]}`); presets add `pluto`.

The side panel is compact by default: the time, the speed-up and the few values the scene is
about, at a readable size. `panel: full` shows every row (diagnostics too: ΔE/E, ΔL/L, the
Jacobi drift), `panel: none` only the "not to scale" note, or name the rows: `panel: [date,
event, distance]` (time, speedup, energy, legend, total_dv, dv, phase, mu, frame, coorbital…; see
CONFIG). `energy: true` puts ΔE/E in a compact panel.

Many bodies: `system` (a restricted three-body pair or the figure-eight), `view: rotating`,
`lagrange`, `zero_velocity`, bodies `near: L4` with `shift`; `resonance: [Io, Europa, Ganymede]`
(period ratios, the Laplace angle, conjunctions); `origin: barycentre` (a binary star);
`curvature: true` on a body; `center` with `extent` for a close-up; the actions `corotate` and
`inertial` switch the frame on a word.

Burns on a body: `burns: [{at: "20 min", prograde: "0.6 km/s"}, {at: apoapsis, prograde: "0.55
km/s"}]` (also retrograde, radial, anti_radial, normal, anti_normal); `transfer: {kind: hohmann |
bielliptic | phasing, ship, to: <body or radius>}`; `- action: pause` / `- action: coast` hold
and run the clock; a `calculation` takes the computed Δv with `from_scene: <orbit scene>.dv1`.

Kepler's third law is a `plot` fed by the built-in model `kepler_planets` (the planets' `a` in
AU, `T` in years): `models: {planets: {kind: function, function: kepler_planets, units: {a: AU,
T: yr}}}`, log axes and a `power` fit, whose exponent comes out 1.500.

`vidgen lint` checks orbit scenes against their own model (the config, not the stills): a period
said for a body (`orbit_period`: "Mars takes about two years" fits 1.88 yr, "three years" does
not), a speed at the point named (`orbit_speed`: vis-viva at perihelion / aphelion, escape and
circular speeds), Δv (`orbit_dv`: "the first burn", "in all"), transfer times, phase angles and
launch windows (`orbit_transfer`), distances, altitudes, Lagrange points and size ratios
(`orbit_distance`: "the Moon is 384,000 km away" fits; "L2 is 15 million km away" does not),
opposition and conjunction dates in any scene (`orbit_date`), "to scale" said of enlarged bodies
or a log view (`orbit_scale`: say "the distances are to scale, the sizes are not"), an n-body run
drifting (`orbit_conserved`) and a periapsis in the atmosphere (`orbit_crash`). A card or caption
naming a body is checked against the orbit scenes too. Write numbers as a viewer hears them, with
"about" when rounded.

The particles of the Standard Model (values from PDG 2024; the model `vidgen.api.particle_physics`
also checks reactions and decays: `particle_physics.check("n -> p e- anti-nu_e").explain()`; the
craft: `vidgen guide particle-physics`):

```yaml
# particle physics
- id: standard_model
  type: standard_model   # quarks and leptons in three generations, gauge bosons, Higgs; mass, charge, spin per cell
  params:
    title: "The Standard Model of particle physics"
    reveal: groups       # quarks, leptons, gauge bosons, Higgs over the beats (all: the whole chart in beat 1)
  beats:
    - text: "Six quarks, in three generations."
    - text: "Six leptons: the electron, the muon, the tau and three neutrinos."
      actions: [{highlight: "row:neutrinos", style: box, at: "@neutrinos"}]
    - text: "The gauge bosons carry the forces."
    - text: "And the Higgs boson, found in twenty twelve."
- id: antimatter
  type: standard_model
  params: {reveal: all}
  beats:
    - text: "Every quark and lepton has an antiparticle, with the opposite charge."
      actions: [{action: antiparticles, at: "@antiparticle"}]   # or a target: "group:leptons", "particle:e"
    - text: "The photon couples to electric charge, so never to a neutrino."
      actions: [{couplings: "particle:photon"}]                 # also particle:g, Z, W, H; undone at the next beat
```

Targets of the chart: `particle:<name>` (`particle:u` or `particle:up`, `particle:e` /
`electron`, `particle:nu_mu`, `particle:photon`, `particle:W`, `particle:H`), `generation:1`…`3`,
`group:quarks` / `leptons` / `fermions` / `gauge_bosons` / `scalar_bosons` / `bosons`,
`row:up_type` / `down_type` / `charged_leptons` / `neutrinos`; `highlight` and `dim` work on all.
`layout: tall` (default in 9:16) puts the bosons in two rows under the fermions.

Feynman diagrams in proper notation, checked vertex by vertex against the Standard Model (a
forbidden vertex is refused with the reason: no H γ γ vertex — draw the loop; no photon on a
neutrino; a W only within a doublet):

```yaml
# particle physics
- id: annihilation
  type: feynman            # fermion arrows (antifermions against time), wavy γ/W/Z, curly g, dashed H
  params:
    title: "Bhabha scattering"
    preset: bhabha         # ee_to_mumu, compton, bhabha, moller, beta_decay, muon_decay, pion_decay, drell_yan,
                           # gg_to_h, h_to_gammagamma, h_to_zz_4l, top_decay
  beats:
    - text: "An electron and a positron annihilate into a photon."
      actions: [{vertex_rule: "vertex:v1", show: [rule, coupling, checks], at: "@photon"}]
    - text: "Or they exchange one: the t channel."
      actions: [{action: swap_channel, to: t, at: "@exchange"}]
    - text: "Follow them through."
      actions: [{travel: diagram}]
- id: muon_decay
  type: feynman
  params:
    diagrams:              # your own: "id: particle from -> to"; ends are vertex ids, in, out
      - lines: ["mu: mu- in -> v1", "nu_mu: nu_mu v1 -> out", "W: W- v1 -> v2", "e: e- v2 -> out", "nu_e: anti-nu_e v2 -> out"]
  beats:
    - text: "The muon becomes its neutrino and a W minus, which decays."
      actions: [{highlight: "line:W", at: "@W"}]
```

Write each line's particle as it travels forward in time (an incoming positron: `e+ in -> v1`;
its arrow is drawn back against time). Targets: `line:<id>`, `vertex:<id>`, `hadron:<particle>`
(with `groups` or `spectators: true` on `beta_decay`), `process`, `diagram`, `time_axis`. `time:
up` draws time bottom → top; the layout (s-, t-, u-channel, decays, loops) is automatic.

Relativistic kinematics as momentum arrows: a two-body decay in the parent's rest frame (p* from
the masses, PDG 2024) and in the lab, or particles with their invariant mass √((ΣE)² − |Σp|²):

```yaml
# particle physics
- id: pion_decay
  type: kinematics         # arrows to scale in the rest frame and the lab; p*, β, γ, opening angle, invariant mass, βγcτ
  params:
    title: "Pion decay in two frames"
    decay: "pi+ -> mu+ nu_mu"
    momentum: "200 MeV/c"  # the pion in the lab (or energy, kinetic, beta, gamma); frames: both | rest | lab
  beats:
    - text: "At rest, the muon and the neutrino fly apart back to back."
    - text: "In the lab the pion moves, and both are thrown forward."
    - text: "The invariant mass is the same in both frames: the pion's mass."
      actions: [{highlight: values, at: "@invariant"}]
- id: speed_up
  type: kinematics
  params: {decay: "pi0 -> gamma gamma", frames: rest, momentum: "1 GeV/c", angle: 90}
  beats:
    - text: "Speed the pion up, and its two photons close up."
      actions: [{action: boost, to: lab, at: "@Speed"}]   # or to: 0.99, to: rest
- id: muon_range
  type: calculation        # PDG values by name: mass, lifetime, width
  params:
    symbols:
      - {name: m_mu, mass: mu-}
      - {name: tau, lifetime: mu-}
      - {name: E, value: "4.00 GeV", meaning: "muon energy"}
      - {name: c, constant: c}
    calculations:
      - {name: gamma, expr: "E/(m_mu*c^2)", meaning: "Lorentz factor"}
      - {name: L, expr: "sqrt(gamma^2 - 1)*c*tau", unit: km, meaning: "mean decay length"}
  beats:
    - text: "A four GeV muon has a gamma of about thirty-eight."
    - text: "On average it flies about twenty-five kilometres: time dilation brings it to the ground."
```

Particles given in the lab: `particles: [{particle: gamma, momentum: "80 GeV/c", angle: 25}, …]`
(their rest frame is found; Σp = 0 there). Targets: `panel:rest`, `panel:lab`, `arrow:<n>` /
`arrow:<particle>`, `sum`, `values`, `process`. A `calculation` takes the numbers with `from_scene:
pion_decay.p_star` (`M`, `E1`, `E2`, `beta`, `gamma`, `opening_angle`, `decay_length`; particles:
`m_inv`). The model `particle_physics.kinematics` also gives thresholds (`threshold("p p -> p p p
anti-p")`: 5.63 GeV kinetic on a fixed target, 0.94 GeV per beam at a collider) and the plot model
`two_body_opening` (the opening angle against momentum; its axes are named and in GeV/c and
degrees by themselves). A decay below threshold, a forbidden decay, β ≥ 1 or an energy below the
mass is refused with the numbers. `readout: key` (default) writes each frame's main numbers large;
`readout: all` every number.

Event displays in a schematic cylindrical detector (tracker, solenoid, ECAL, HCAL, iron yoke, muon
chambers; generic sizes, labelled "schematic detector · simulated event"), seen across the beam
(x–y) or along it (r–z), with a simulated event built layer by layer over the beats:

```yaml
# particle physics
- id: z_event
  type: detector           # tracks bend with R = pT / (0.3 B); e, γ shower in the ECAL, hadrons in the HCAL, μ reach the muon chambers
  params:
    title: "A Z boson decays to two muons"
    event: {preset: z_to_mumu, seed: 3, soft: 0}   # z_to_mumu, h_to_gammagamma, h_to_4l, w_to_enu, dijet; same seed, same event; soft: low-pT pions (default 4)
  beats:
    - text: "Tracks curve; calorimeters take the energy; two muons reach the muon chambers."
      actions: [{highlight: "particle:mu+", at: "@muons"}]
    - text: "Seen from the side."
      actions: [{action: switch_view, to: rz}]
- id: signatures
  type: detector
  params:
    event:
      particles:           # pt in GeV/c, eta, phi in degrees; particle: jet for a jet
        - {particle: e-, pt: 30, eta: 0.3, phi: 20}
        - {particle: gamma, pt: 40, phi: 100, leaves: [ecal]}   # leaves is checked: a photon leaves no track
        - {particle: nu_e, pt: 35, phi: 150}                      # invisible: missing transverse momentum
    reveal: all
  beats:
    - text: "The neutrino escapes: the momentum is out of balance."
      actions: [{highlight: missing_pt, at: "@neutrino"}]
```

`field` (tesla, default 2) sets the bending: positive particles turn clockwise in the x–y view (the
field out of the screen); low-p_T tracks curl up in the tracker. Missing p_T is minus the visible
particles' sum. Towers grow ∝ log(1 + E) (`energy_scale: linear` for ∝ E; `tower_max` fills the
depth). Targets: `particle:<n>` / `particle:mu+` (track, towers, name, readout row), `jet:<n>`,
`tracks`, `ecal`, `hcal`, `muon_hits`, `missing_pt`, `readout`, `legend`, `layers`,
`layer:<tracker|solenoid|ecal|hcal|iron|muon>`, `soft`. A τ, π⁰, Z or quark listed as a particle is
refused with the reason (it decays first; make a jet).

Resonances emerging from data: a simulated invariant-mass spectrum fills event by event (bars, a
ticker "events: 12 400" and the local significance growing with the data), then a peak fit with
the mass ± its uncertainty and the width, the likelihood-ratio significance and what 5σ means;
decay chains with lifetimes; branching ratios from the model:

```yaml
# particle physics
- id: diphoton
  type: mass_spectrum      # simulated, labelled so; a plot underneath: grow, fit, annotate, reveal and zoom work
  params:
    channel: h_to_gammagamma   # z_to_mumu, h_to_gammagamma, h_to_4l, custom (mass, window…)
    seed: 1
  beats:
    - text: "Events arrive, and a small bump grows near one hundred and twenty-five GeV."
      actions: [{grow: axes}]
    - text: "A fit on a smooth background finds the mass, and how unlikely chance is."
      actions: [{fit: "fit:fit", at: "@fit"}]   # the significance note follows (or annotate: "annotation:significance" on a word)
- id: four_leptons
  type: mass_spectrum
  params: {channel: h_to_4l, style: points, subtract: true}   # points with √N bars; a data − background panel
  beats:
    - text: "Four leptons: only a handful of events, then a few more."
      actions: [{grow: axes, to: 20}, {grow: axes, at: "@few"}]   # to: a number of events
    - text: "A fit, then subtract the background, and look closer."
      actions: [{fit: "fit:fit"}, {reveal: "residuals:fit", at: "@subtract"}, {zoom: axes, x: [115, 135], at: "@closer"}]
- id: pion_chain
  type: decay_chain        # each decay checked; τ and cτ (resonances: Γ) from PDG 2024; branching fractions when listed
  params:
    title: "From a pion to an electron"
    decays: ["pi+ -> mu+ nu_mu", "mu+ -> e+ nu_e anti-nu_mu"]
  beats:
    - text: "A positive pion."
    - text: "It lives twenty-six nanoseconds, then becomes a muon and a neutrino."
    - text: "The muon lives two point two microseconds."
- id: higgs_decays
  type: branching          # bars from the model (H: LHC Higgs XS WG prediction; Z, W, π, K, μ: PDG 2024)
  params: {particle: H}
  beats:
    - text: "Most Higgs bosons decay to a bottom quark pair; two photons, a quarter of a percent."
      actions: [{highlight: "bar:γγ", at: "@photons"}]
- id: z_decays
  type: branching_pie      # a pie (small modes grouped below other_below %, 1.5 by default)
  params: {particle: Z}
  beats:
    - text: "Seventy percent of Z bosons decay to hadrons, twenty percent to neutrinos."
```

What the numbers mean, and what is simulated: every event of a `mass_spectrum` is simulated from
its `seed` (the same seed, the same events), labelled "simulated data" in the legend and caption:
the resonance is a Breit–Wigner of the PDG 2024 mass and width smeared by a Gaussian `resolution`,
over a smoothly falling background (`background: exponential | power | flat`, `slope`, `index`);
`events` and `signal` (expected signal events) set the counts; `window` and `bin_width` the axis.
The fit (`peak: gaussian | breit_wigner`, `background_degree`) is Phase W's binned Poisson
likelihood; for the Z the fitted Γ includes the resolution (the caption gives both). The readout's
**local significance** is the expected (Asimov) Z = √(2((s+b) ln(1+s/b) − s)) of the signal and
background expected in the peak window after that many events (`significance: counting` for the
observed excess, `none`); the note after the fit gives the likelihood ratio (background only
against signal + background) and its one-sided p-value: **5σ ↔ p ≈ 2.9 × 10⁻⁷, the chance that
background alone fluctuates up this much — not the chance that the result is wrong**. The note
is short by default (`6.7σ local`, `p = 7.6 × 10⁻¹²`, `(background only)`: let the narration say
what it means); `explain: long` writes the meaning out on screen. Both are
local: the look-elsewhere effect is not included. Targets are the plot's: `axes`, `series:simulated
data`, `fit:fit`, `residuals:fit` (with `subtract`), `annotation:significance`, `legend`, `title`.
A `plot` also takes the models `mass_spectrum` (numbers: mass, width, resolution, lo, hi, events,
signal, slope), `decay_times` (`tau`, `events`: exponential decay times to fit with `model: custom,
expr: "N*exp(-x/tau)"`) and `z_lineshape` (σ(e⁺e⁻ → hadrons) for 2, 3 and 4 neutrino families;
schematic, no radiative corrections — say so in the caption). `decay_chain` targets: `decay<N>`,
`particle:<n>` / `particle:mu+`, `lifetime:mu+`, `chain`; `branching` and `branching_pie` take
`modes` (the largest N) and the targets of `bar_chart` / `pie` (`bar:γγ`, `slice:hadrons`).

`vidgen lint` checks what the narration and the screens say about particles against the same
model: masses (`particle_mass`: "the W weighs 91 GeV" — that is the Z's), charges and spins
(`particle_charge`, `particle_spin`, errors: "the down quark has charge +2/3"), lifetimes, half-lives
and widths (`particle_lifetime`), branching ratios (`branching_ratio`: "most Higgs bosons decay to
two photons"), "allowed" / "forbidden by …" / "conserves …" against the checker
(`conservation_claim`), the boson named for an interaction (`feynman_boson`: "a photon changes the
quark's flavour", "gluons couple to electrons", a boson the diagram does not have), a `kinematics`
scene's numbers, decay lengths βγcτ and thresholds (`kinematics_number`), detector signatures
(`detector_signature`: "photons leave tracks"), the meaning of a p-value and the σ a spectrum
reaches (`significance_claim`: "five sigma means 99.99994 % sure the Higgs exists" is wrong — say
"background alone would fluctuate this high once in 3.5 million tries"), simulated data called
real (`simulated_label`), masses written both as GeV and GeV/c² (`particle_units`, info). Negations
and contrasts are left alone ("photons do not leave tracks" is fine).

```yaml
# data
- id: devices
  type: pie
  params: {title: "Visits by device", donut: true, labels: ["Mobile", "Desktop", "Tablet"], values: [5200, 3100, 640], highlight: Mobile}
  beats:
    - text: "Most visits come from phones."
    - text: "More than half of them."
- id: busy
  type: heatmap
  params:
    title: "Renders per hour"
    rows: ["Mon", "Tue"]
    columns: ["9h", "12h", "18h"]
    values: [[3, 8, 9], [5, 10, 11]]
    highlight: "col:18h"
  beats:
    - text: "Each cell counts the renders in one hour."
    - text: "Evenings are the busiest."
- id: offices
  type: map
  params:
    title: "Our offices"
    view: europe
    steps:
      - [Germany, France]
      - pins: [{lon: -0.13, lat: 51.51, label: London}]
  beats:
    - text: "We started in Germany and France."
    - text: "Then we opened in London."
```

Pictures, screenshots, clips and simple 3D (the 3D craft: `vidgen guide 3d`):

```yaml
# pictures and media
- id: harbour
  type: image
  params: {generate: "a quiet harbour at dawn, fishing boats, mist over the water", fit: cover, ken_burns: true}
  beats: [{text: "It started in a small harbour town."}]
- id: lab
  type: image
  params: {path: assets/lab.png, caption: "The training cluster"}
  beats: [{text: "Everything ran on this machine."}]
- id: app
  type: screenshot
  params:
    title: "Find any task"
    path: assets/app.png
    frame: browser
    steps:
      - {box: [0.22, 0.04, 0.27, 0.06], label: "Search"}
      - {arrow: [0.86, 0.07], label: "New task"}
  beats:
    - text: "The search box at the top finds any task in seconds."
    - text: "And one click on this button adds a new one."
- id: demo
  type: video_clip
  params: {path: assets/demo.mp4, trim: [1, 5], fit_duration: true, mute: true, caption: "The app, live"}
  beats: [{text: "Here it is running live."}]
- id: crate
  type: 3d
  params:
    title: "A crate in 3D"
    floor: true
    objects:
      - {id: crate, shape: box, size: 1.6, position: [0, 0.8, 0], rotation: [0, 20, 0], spin: [0, 30, 0]}
      - {id: tag, parent: crate, shape: label, text: "Crate", position: [0, 1.2, 0]}   # turns with it
      - {id: ball, shape: sphere, size: 0.6, position: [2, 0.3, 1], color: highlight, visible: false}
  beats:
    - text: "A crate turns slowly in front of the camera."
      actions:
        - {object_highlight: crate, at: "@crate"}
    - text: "A ball appears and rolls round it, and the camera circles in."
      actions:
        - {object_show: ball, at: "@appears", style: grow}
        - {object_path: ball, at: "@rolls", points: [[1, 0.3, 2], [-1.6, 0.3, 1.4]], run_time: 1.5}
        - {camera_orbit: crate, at: "@circles", degrees: 60, run_time: 1.5}
- id: meeting
  type: 3d
  params:
    floor: true
    camera: {position: [0, 3, 8], look_at: [0, 0.8, 0]}
    objects:
      - {id: ana, shape: standin, name: "Ana", color: primary, position: [-2.5, 0.8, 0], rotation: [0, 90, 0]}
      - {id: ben, shape: standin, name: "Ben", color: secondary, position: [2.5, 0.8, 0], rotation: [0, -90, 0]}
      - {id: gift, shape: box, size: 0.4, position: [0, 0.2, 1], visible: false}
  beats:
    - text: "Ana walks over to Ben."
      actions:
        - {object_walk: ana, at: "@walks", to: ben}
    - text: "A gift appears between them and glows."
      actions:
        - {object_show: gift, at: "@appears", style: grow}
        - {object_highlight: gift, at: "@glows"}
        - {object_face: ben, at: "@gift", to: gift}
- id: gears
  type: web
  params: {page: extensions/gears.html, region: body, title: "Two gears"}   # or script: extensions/gears.js (one canvas)
  beats: [{text: "Two gears turn together."}]
- id: rings
  type: space          # no code: the page is written for you (see the space-scenes topic of the guide)
  params:
    sky: {seed: 4, look: rich}
    sun: {direction: [1, -0.3, 0.25]}
    bodies: [{name: Saturn}]
    camera: {move: arc, subject: Saturn, phase: [three-quarter, crescent], distance: {radii: 6}}
    finish: {grain: 0}   # no film grain (default 0.02): a lighter picture
  beats: [{text: "Round the planet, the Sun goes behind it: a thin crescent."}]
- id: saying
  type: quote
  params: {text: "Simplicity is prerequisite for reliability.", author: "Edsger W. Dijkstra"}
  beats: [{text: "As Dijkstra put it, simple systems are the reliable ones."}]
```

A `web` scene is a page you write in HTML, CSS and JavaScript (`page:` an HTML file, or `script:` a
module drawing on one canvas), screenshotted frame by frame: CSS animations, timers and
`requestAnimationFrame` follow the video's time, the theme comes as CSS variables
(`var(--vidgen-primary)`), `<body data-beat="b2">` reveals a part on its beat, `import * as THREE
from "three"` loads three.js, and lint reads its text. Prefer a built-in type when one fits; how to
write a good one, with working examples and the usual mistakes: `vidgen guide web`.

```yaml
# maths and code
- id: square
  type: equation
  params: {latex: ["(a + b)^2", "a^2 + 2ab + b^2"], terms: ["2ab"]}
  beats:
    - text: "Take a plus b, squared."
    - text: "The middle term is where the cross products hide."
      actions: [{zoom: "term:2ab"}]
- id: solve
  type: equation_derivation
  params:
    title: "Solving for x"
    colors: {x: accent}
    steps: ['2x + 3 = 11', {tex: '2x = 8', note: "Subtract 3"}, {tex: 'x = 4', note: "Divide by 2"}]
  beats:
    - text: "Two x plus three is eleven."
    - text: "Take three from both sides."
    - text: "So x is four."
- id: slope
  type: function_plot    # f(x) written as maths (parsed safely: x^2, 2x + 1, sin(x), exp(-x^2/2)); one item per beat
  params:
    title: "The slope of x²"
    functions: ["f(x) = x^2"]
    x_range: [-3, 3]
    dots: [{x: -2, tangent: true, label: "slope {slope}"}]   # a live label: {x}, {y}, {slope}
    areas: [{between: [0, 1], label: "A = {area}"}]           # the area under f, its size filled in
  beats:
    - text: "Here is the parabola, f of x equals x squared."
    - text: "A dot on the curve, with its tangent."
    - text: "As the dot moves right, the slope grows steeper."
      actions: [{trace: dot1, to: 2, at: "@moves"}]   # the dot travels along the curve on the word
    - text: "The area under the curve grows as its end moves out."
      actions: [{trace: area1, to: 2.5, at: "@grows"}]
- id: triangle
  type: function_plot    # geometry on the same plane: points, vectors and marks, no functions needed
  params:
    axes: false          # pure geometry; keep the axes for vectors on a grid
    points: [{at: [0, 0], name: A}, {at: [4, 0], name: B}, {at: [4, 3], name: C}]
    marks:
      - {segment: [A, B, C], closed: true}
      - {brace: [A, B], label: "4"}               # outside the triangle by itself
      - {angle: [B, A, C], label: "{angle}°"}     # the angle at A; a square at 90°
      - {dimension: [A, C], label: "c = {length}"}
  beats:
    - text: "A right triangle with sides four and three."
    - text: "Move C up and the angle at A opens."
      actions: [{trace: "point:C", to: [4, 4], at: "@Move"}]   # marks and labels follow
- id: vectors
  type: function_plot
  params:
    x_range: [-1, 6]
    y_range: [-1, 5]
    vectors: [{to: [3, 1], name: a}, {to: [1, 3], name: b}, {sum: [a, b], label: "a + b"}]   # b slides to a's tip
  beats:
    - text: "Vector a, and vector b."
    - text: "Put b at the tip of a: the sum runs from start to end."
    - text: "Double a and the sum follows."
      actions: [{trace: "vector:a", scale: 2, at: "@Double"}]
- id: hops
  type: number_line
  params:
    range: [-2, 8]
    points: [{at: 2, name: a}]
    intervals: ["[4, inf)"]                        # interval notation: [ ] closed, ( ) open, inf
    jumps: [[2, 5], [5, 7]]                        # arcs labelled +3, +2
  beats:
    - text: "Start at two."
    - text: "Every number from four on."
    - text: "Jump three to five."
    - text: "And two more to seven."
- id: snippet
  type: code
  params: {title: "Load and train", code: "data = load()\nmodel = fit(data)\nsave(model)", highlight: ["1", "2-3"]}
  beats:
    - text: "We load the data."
    - text: "Then fit and save the model."
- id: faster
  type: code_morph       # version i at beat i; the diff is computed for you: shared tokens glide, new lines grow in
  params:
    title: "Cache it"
    versions:
      - "def fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)"
      - {code: "@cache\ndef fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)", highlight: changed}
  beats:
    - text: "This version recomputes the same values again and again."
    - text: "One decorator, a cache, and each value is computed once."
      actions: [{reveal: version2, at: "@cache"}]   # morph on the word (1.5 s)
- id: shell
  type: terminal         # step i at beat i: the command is typed, then its output appears (you write it: nothing runs)
  params:
    title: "Run the tests"
    code: {code: "def mean(xs):\n    return sum(xs) / len(xs)", highlight: 2}   # optional: the code beside it
    steps:
      - {command: "pytest -q", output: "..F\n1 failed, 2 passed in 0.03s"}
      - {command: "python -c 'print(mean([]))'", output: "ZeroDivisionError: division by zero", output_color: secondary}
  beats:
    - text: "We run the tests, and one of them fails."
      actions: [{reveal: output1, at: "@fails"}]   # the output on the word
    - text: "An empty list divides by zero."
- id: walk
  type: code_walkthrough
  params:
    title: "The training loop"
    code: "def train(data):\n    model = init()\n    for batch in data:\n        loss = step(model, batch)\n    return model"
    steps: [{lines: "1-2", note: "Set up the model"}, {lines: "3-4", note: "One step per batch"}]
  beats:
    - text: "The function starts by creating the model."
    - text: "Then it takes one step per batch."
```

```yaml
# cartoons
characters:              # top level of video.yaml: declared once, used by any stage
  - {name: pip, look: {body: bean, hair: short}}
  - {name: kit, look: {body: tall, hair: spiky, accessories: [scarf]}}
scenes:
  - id: park
    type: stage
    params:
      background: [primary, highlight]   # a gradient sky; or image: / generate: for a picture
      characters:
        - {name: pip, at: left, pose: waving, expression: happy}
        - {name: kit, at: right, depth: 0.3}   # further back: smaller, drawn behind
    beats: [{text: "Pip waves at an old friend across the park."}]
```

```yaml
# cartoons
- id: later
  type: card                  # style: burst (rays turning), frame or plain
  params: {text: "Later that day…", subtitle: "at the old mill", sting: comic}
  duration: 2.5               # silent; or beats: to narrate it
```

A whole cartoon (characters, staging, shots, timing, title cards and irises): `vidgen guide cartoons`.

**When to write a custom scene type** (a Python file in the project's `extensions/`, see
`docs/EXTENDING.md`): when the idea is a specific drawing no built-in can express (a mechanism,
a geometric construction, a bespoke animation) and you would otherwise bend a built-in into
it. Prefer built-ins whenever one fits: they are tested at 16:9 and 9:16, fit text to readable
sizes, expose action targets and pass lint. Custom scenes should use regions
(`self.region("body")`, `place(...)`) rather than fixed coordinates, and get checked with the
same storyboard and lint loop. If you would rather write the picture as a web page (HTML and CSS,
a canvas, your own three.js), a `web` scene needs no Python: `vidgen guide web`. A Python scene
type is the better choice for one you will reuse with new params, or one whose text and parts must
be vidgen's own (action targets, fitted text); a `web` scene renders much more slowly.

