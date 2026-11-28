<!-- topic: troubleshooting (also: errors, fixes, lint, validate, problems) -->
## Troubleshooting: messages and fixes

**`vidgen validate`** (each problem names a config path; `--json` lists them all):

| message says | fix |
|---|---|
| `unknown scene type 'x'; did you mean ...` | use a listed type (`vidgen list-scenes`) |
| `unknown parameter 'x'; did you mean 'y'?` | rename it; `vidgen schema --scene TYPE` lists the params |
| `a scene without beats (silent scene) needs a 'duration'` | add `duration: 2.5`, or give it beats |
| `'duration' is only allowed on silent scenes` | remove `duration`: beats set the length |
| `duplicate beat id` | beat ids are unique in the whole video; rename one |
| `unknown target 'x' ...; did you mean ... (targets: ...)` | pick a name from the list (labels are case-sensitive: `bar:4K`) |
| `until 'x' is not a later beat of scene 'y'` | `until` names a later beat id of the same scene |
| `unknown action 'x'` / `unknown option` | actions are `reveal`, `dim`, `highlight`, `zoom`, `pan`, `follow`, `transform`, `callout`, `sfx`, `particles`, `say`, `look_at`, `turn`, `emote`, `pose`, `react`, `walk_to`, `run_to`, `enter`, `exit`, `wander`, `meet`, `gesture`, `jump`, `keyframes`, `move_along`, `pick_up`, `hold`, `put_down`, `give`, `throw`, `open`, `close`, `let_go`, `pour`, `switch_on`, `switch_off`, `hide`, `drop_fruit`, `birds`, `sit_on`, `lean_on`, `stand_up`, `get_in`, `ride_to`, `get_out`, `light`, `wind`, `blow_away`, `effect` |
| `labels has 2 entries but values has 3` | one value per label |
| `unknown theme color 'x'` | use a token (`primary`, `highlight`...) or quoted hex `"#0B5FFF"`, or add it to `theme.colors` |
| `invalid hex color` | `#RGB`, `#RRGGBB` or `#RRGGBBAA`, in quotes (YAML reads `#` as a comment) |
| `unknown icon 'x'; did you mean 'y'?` | `vidgen list-icons --search WORD` |
| `file not found: assets/...` | paths are relative to the project folder |
| `starts chapter 'x' right after the chapter card` | put the `chapter:` key on the card instead |

LaTeX in YAML: write formulas in single quotes (`'\frac{1}{2}'`). Equations need a LaTeX
install; `vidgen validate` warns when it is missing.

**`vidgen lint`** (each finding names its rule and the still to open):

| rule | what it means | usual fix |
|---|---|---|
| `max_words` | too much text on one frame | split the scene, shorten items, `dim_previous`, fewer columns |
| `min_font` | text too small for the output | less content per scene (it was shrunk to fit), shorter labels, split the table / diagram / timeline |
| `off_frame` | text cut off at the frame edge | shorter text; in a custom scene, place it in a region |
| `safe_area` | text in the margin, or under the captions (the message names the overlay that keeps that part of the frame) | as above; check reserving overlays; a `web` page: `region: body` |
| `text_overlap` | two texts on top of each other | fewer or shorter labels; a custom scene's layout |
| `covered_text` | a shape drawn over text | move the shape or the callout (`side:`) |
| `label_spacing` | a callout label touches other text (a value, the title) | another `side:`, an `arrow` instead of a `label`, a shorter label |
| `contrast` | text hard to read on its background | theme tokens instead of custom colours; another preset |
| `overlay_overlap` | an overlay covers scene text | `reserve: true` on the overlay, or another corner / position |
| `host_overlap` | the host overlaps the content, a caption or an overlay | a smaller host (`size`), another `side` / `place`, or `host: false` on that scene |
| `walk_overlap` | a character's walk ends on another character | walk it to another mark or x, or move the other one first |
| `off_stage` | a character is cut by the edge of the view (in a `shot`: a character it frames is out of it) | another mark or x inside the view, or `pan` to it; in a shot, keep it from walking out or frame another shot |
| `character_overlap` | two characters stand on each other (at about the same depth) | marks further apart, or `walk_to` one away (across, or in depth) |
| `prop_overlap` | two props on the floor at about the same depth are drawn over each other (a room's door over the sofa against the wall) | another `at` for one (a door: its x in the room's `doors`), a smaller `scale`, or a `depth` that puts one in front; a picture or clock above furniture, a lifted prop and a rug are fine |
| `bubble_overlap` | a speech bubble covers a face, another bubble or an effect symbol | a shorter `bubble` text, characters further apart, or the lines (or the line and the effect) in different beats |
| `facing_away` | a speaker faces away from the one it talks to (last looked at, else the nearest) | `turn`, `look_at: <listener>`, or swap their marks |
| `hidden_speaker` | something in front hides the speaker's face (on an iso place: what really covers its eyes and mouth, a lamp post across the face) | move one of them, or a smaller `depth` for the speaker; on an iso place `walk_to` a spot with nothing in front, or a `shot` |
| `small_speaker` | a speaking face too small on screen to read it and its lip sync (on an iso place a speaker with a name tag may say up to 12 words) | `shot: closeup <name>` (or `medium`) for that beat, or `character_size: large` |
| `offscreen_action` | on an iso place: a walk, a thing handed about or a change of the place (a door, a lamp) the camera mostly does not show while it happens | `shot: wide`, a `pan` or `follow` to it, or do it in a beat whose shot shows it |
| `iso_ground` | an iso place with `wide: fixed` on a map too small for the frame (background round it); info: an outdoor place in the whole-place wide view | the map size it names, or a sky `background` if the floating place is meant |
| `mouth_without_voice` | a mouth still shows speech after the narration ended | `vidgen tts` again; in a custom scene, lip sync with `clock=self.beat_clock()` |
| `said_before_shown` | the narration names a label on screen (a node, a callout, a stage) seconds before it appears, and not again when it does | show it on the word: `{reveal: node:database, at: "@database"}` (or the callout's `at`); or name it in the beat that shows it |
| `unsaid_reveal` | (off unless `lint.rules.unsaid_reveal.severity` is set) a beat shows new labels the narration never names | say what the viewer should look at, or leave it off: many labels need no words |
| `iso_labels` | an `iso_diagram` label over a block it does not name (a group's caption among its blocks), over another label or a connector, or far from what it names | more `spacing` or `at` further apart, shorter labels, fewer blocks; a stack's `label_side` |
| `music_check` | a project piece (`assets/music/NAME.yaml`) the video plays is loud in the voice's range, too bright, boomy, unsteady, peaky or clicks at its loop (`vidgen music check`'s fixes; its notes are info) | the fix the message names (a track's `volume`, an octave, `lowpass`), then `vidgen music check` again; or `severity: off` in `lint.rules.music_check` |
| `science_scale` | a `cell` with a scale bar draws something far outside its real size, or too many nuclei / centrosomes | a real `size`, or `not_to_scale: true` (the scene says so); `lint_ignore` a real exception |
| `science_location` | the narration puts a process where it never is (glycolysis in the mitochondria) or a thing where the `cell` does not show it | say where it is, or place it there (`in:`, `on:`) |
| `science_direction` | a wrong direction: RNA made 3′→5′, a protein made C→N, kinesin to minus, protons pumped into the matrix | the textbook direction the message gives |
| `science_energy` | "active transport" through a channel or uniporter, or with no pump, symporter or ATP in the scene | call it facilitated diffusion, or show the pump / coupled carrier |
| `science_naming` | a scene's gene written as its protein (mouse `TRP53 gene`), the wrong case, a gene label without `<i>` | the form the message gives (mouse: gene *Trp53*, protein TRP53) |
| `science_pathway` | the narration says activates where the pathway's arc inhibits (or the reverse) | fix the words, or the arc (`effect:`) |
| `science_counts` | a number against the textbook (net 4 ATP from glycolysis) | the number the message gives |
| `genetics_ratio` | a ratio or share the `cross` does not give ("a 3:1 ratio" for a dihybrid, "half the daughters affected") | the ratio the message gives, or "each trait alone…" for one trait's ratio |
| `genetics_pedigree` | the chart does not fit its `mode` (error); "a dominant trait skips a generation"; an X-linked trait passed father to son; a carrier or risk probability against the chart | fix the chart or the mode; say reduced penetrance (`penetrance:`); the probability the message gives |
| `genetics_linkage` | RF over 50 %, a distance or RF against the `linkage_map` (or `linkage:`), linked loci called unlinked | the cM / RF the message gives |
| `genetics_hwe` | carriers called q², the incidence called 2pq, q or the carriers against the incidence | q = √incidence, carriers 2pq (≈ 2q) |
| `genetics_crispr` | the wrong PAM for the Cas, a cut downstream of the PAM or not 3 bp upstream, sticky ends for Cas9 | SpCas9: NGG, a blunt cut 3 bp upstream (5′) of the PAM |
| `genetics_karyotype` | ISCN that does not parse or is out of order, "45,X is male", a condition the `karyotype` does not show | the notation or the condition the message gives |
| `genetics_hgvs` | HGVS not valid or not the `mutation`'s variant, legacy numbering unannounced (p.Glu6Val); info: `ΔF508`, `R553X` | the HGVS form; call the old name legacy |
| `calc_numbers` | a number said or shown for a `calculation`'s value that is not what it computes ("thirty-five kilometres per second" for 29.8 km/s) | the value the message gives (or "about" and a rounding of it); or fix the calculation |
| `calc_units` | "a speed of 30 kilometres"; a value off by a factor of 1000 (m/s for km/s, mg for µg) | the unit of that kind, the right prefix |
| `calc_sigfigs` | (info) more figures than the inputs give: a `sig` beyond them, "29.7847 km/s" said for 29.8 | round to the figures the message gives, or give the inputs more figures |
| `plot_units` | a `plot` axis titled with a physical quantity (time, energy…) but no unit | `unit:` on the axis, or `name (unit)` in the CSV header |
| `plot_log` | error bars, a fit or its band, or a reference line at or below zero on a log axis | asymmetric errors that stay positive, a positive model, `band: none`, or a linear / symlog axis |
| `plot_errors` | error bars without `error:`, or narration calling them otherwise ("standard deviation" for `sem`) | `error:` sd, sem, ci95, range, poisson or other; say what they are |
| `plot_series` | several series with `legend: false` and no label naming them; a placeholder name (`series 2`) | show the legend or label each series; name it after what it is |
| `plot_truncated` | (info) bars not starting at zero: a histogram on a broken y axis, a `bar_chart` `baseline` other than 0 | drop the break / baseline, or say so on screen |
| `plot_conserved` | a model's `conserved` quantity drifts beyond 1 % | `method: leapfrog`, or a smaller `step` |
| `plot_fit_claims` | a fitted value said otherwise ("a half-life of twelve days" for 8.0 ± 0.1 d, "exponent five halves") | the value the fit gives, or fit what you say |
| `orbit_period` | a period said for an `orbit` scene's body that its orbit does not have ("Mars takes three years" for 1.88 yr) | the period the message gives ("about two years" is fine), or change the orbit |
| `orbit_speed` | a speed against vis-viva at the point named (perihelion, aphelion…), an escape or circular speed | the speed the message gives, or name the right point |
| `orbit_dv` | a burn's or transfer's Δv said otherwise ("the first burn takes 3.2 km/s" for 2.43) | the Δv the panel shows (first, second, total) |
| `orbit_transfer` | a transfer time, phase angle or launch-window interval said otherwise ("180 days" for 259 d, "every 18 months" for 780 d) | the value the message gives |
| `orbit_distance` | a distance, altitude, radius, Lagrange point or size ratio said otherwise ("L2 is 15 million km away" for 1.5 million) | the value the message gives |
| `orbit_date` | an opposition or conjunction date JPL's elements do not give ("Mars was at opposition in 2021") | the date the message gives |
| `orbit_scale` | "to scale" said of a picture that is not: enlarged bodies, `radial: log`, the `sizes` picture's distances, the tides | say what is to scale ("the distances are to scale, the sizes are not") |
| `orbit_conserved` | an n-body run's energy, angular momentum or Jacobi constant drifts beyond 1 % | a smaller `step`, or `method: leapfrog` |
| `orbit_crash` | a periapsis in the atmosphere (Earth below 100 km), a flyby through the air, n-body bodies passing through each other | raise the periapsis or the flyby; change the starting state |
| `particle_mass` | a mass said otherwise than PDG 2024 ("the W weighs 91 GeV"; MeV for GeV) | the value in the message, or the particle it names (did you mean …) |
| `particle_charge` | a charge said wrong ("the down quark has charge +2/3") | the value in the message |
| `particle_spin` | a spin said wrong ("the photon has spin 1/2", "the Higgs boson is a fermion") | the value in the message |
| `particle_lifetime` | a mean life, half-life or width said otherwise ("the muon lives 2.2 ms") | the value in the message; a moving particle's life is γτ (say so) |
| `branching_ratio` | a branching ratio said wrong ("most Higgs bosons decay to two photons") | the share in the message; "most" only for the largest mode |
| `conservation_claim` | a decay called allowed that the checker forbids, or forbidden by a law it keeps | say what the message says is broken (`particle_physics.check("…").explain()`) |
| `feynman_boson` | the wrong boson: a coupling that does not exist, flavour changed without a W, a boson the diagram does not show | name the boson in the message, or change the diagram |
| `kinematics_number` | a momentum, energy, invariant mass, decay length or threshold said otherwise than computed | the scene's value (or `from_scene` it into a calculation) |
| `detector_signature` | "photons leave tracks", "muons stop in the ECAL", "neutrinos are seen in the calorimeter" | the signature in the message |
| `significance_claim` | a p-value said as the chance the result is wrong, a σ the spectrum does not reach | "background alone would fluctuate this high once in N tries"; the scene's σ |
| `simulated_label` | simulated data called real, or a spectrum / event display without "simulated" on screen | say "simulated"; keep it in the label or caption |
| `particle_units` (info) | masses both in GeV and GeV/c² on screen | one convention throughout |
| `shorts_safe_area` | in a Short (`shorts:`), text or a face where the app covers the frame (bottom 20 %, right 15 %), or a caption / the hook over a face | a closer `shot` or `zoom` with the faces higher; move the scene's text inwards |
| `overlay_face` | a `hud`'s text or plate over a character's face (outside Shorts) | frame the face away from the corners, `compact: true`, fewer `lines` |
| `shorts_length` (error) | a Short longer than `shorts.max_seconds` (60) | leave out beats or scenes in `cut:`, a shorter `end_card` |
| `generated_footage` (info) | the scene shows AI-generated video takes | nothing to fix: when publishing, mark the video as altered or synthetic content where the platform asks |
| `three_d_off_frame` | in a `3d` scene, an object the beat is about (its actions name it, or a stand-in says the line) is mostly outside the frame | `camera_fly_to` / `camera_look_at` it, or move it into view |
| `three_d_hidden` | in a `3d` scene, an object the beat is about is mostly hidden behind a nearer one | `camera_orbit` round it, or move one of them |
| `web_clipped` (error) | in a `web` scene, page text cut by its own box or an ancestor's (`overflow: hidden`), or by the page's box (`region: body`) | shorter or smaller text, a box that grows; `data-vidgen-lint="off"` on text cut on purpose |
| `space_scene` (warning) | in a `space` scene, a globe turning too fast under the orbit data's speed-up, an enlarged body covering another, worlds placed inside each other | `spin: locked` or a stated spin in seconds, a smaller speedup; a smaller enlarge factor for that body; move a world (`at`) |
| `concept_colors` | the `terms:` colours: more than 5, too faint on the background, or a term coloured otherwise by a scene setting | fewer colours (related terms may share one), a readable theme token, or leave the scene's colour setting out |
| `look_alike` | two characters too alike to tell apart | change what the message names on the second (body, hair, species, clothes colour); or `vidgen cast --random N` |
| `dead_air` | nothing moved for over 6 s | split the beat, add a reveal or an action, shorten a silent `duration` |
| `narration_speed` | words per second outside 1.8–3.5 (English) | shorten or lengthen the beat's text; without audio it is only `info` (an estimate) |
| `animation_overrun` | animations ran past the narration | a custom scene's animations are too long for the beat |
| `rushed_animation` | animations squeezed into a short beat | merge two short beats, or reveal fewer things per beat |
| `talked_over` | an `overlap` hides whole words of the line before, or an `interrupt` cuts them | a shorter `overlap` (none for an interrupt), or `interrupt: true` to cut the line |
| `readback` | the audio does not say what the text says | add a `pronunciation:` entry, `vidgen tts`, check again |
| `unclear_speech` | (only with `--readback`) a word heard unclearly or after an odd pause | respell it in `pronunciation:`, or another voice, speed or `emotion:` for the beat; `vidgen tts`, check again |

**Other things that go wrong**

- *The storyboard did not change after an edit to a file outside `assets/`*: `--force`.
- *A table / diagram / timeline "does not fit at the readable size"* (render warning): it was
  scaled down; split it into two scenes or shorten the texts.
- *Preview timing is wrong*: until `vidgen tts`, beats are timed from word counts; numbers and
  acronyms take longer to say. Re-check pacing after the real audio.
- *`vidgen render --scene ID` re-joins the other scenes as they are*: render the scene before a
  new transition or carry too.
- *`vidgen render --scene ID` rendered every scene*: the video is joined from every scene, so a
  scene with no render yet at that quality and variant (`--preview`, `--draft` and each
  `--variant` keep their own renders) is rendered too; a line `--scene ID: also rendering ...`
  names them. The next `--scene ID` renders only that scene. To look at one scene without the
  others, use `vidgen storyboard --scene ID`.
- *`ffmpeg not found`*: install it and open a new terminal.
- *`ffmpeg X.Y is too old`*: install ffmpeg 4.4 or newer.
