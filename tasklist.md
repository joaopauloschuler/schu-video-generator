# schu-video-generator task list — features for AI-authored videos

This file lists **open work only**: `- [ ]` not done, `- [~]` partly done (the note says what is
left). Completed steps are not kept here; they are in the git history (`git log`, commits
`Step N: ...`). Headings name the phase or step an open item came from.

How a step is done: one agent does one step, following `CLAUDE.md` (tests for what it builds,
one commit `Step N: <summary>`). When a step is finished, its items are removed from this file;
if only part is done, the item stays as `[~]` with a note on what is left. Work that downloads
or calls a paid or remote service stays optional and is mocked in tests.

**Next step number: 445** (the last completed step is 444). Each step raises this number in its commit.

## Phase E — Outputs, extras, guidance

### Step 60 — Final review
- [~] (from Step 59) MCP server — left: trimming large documents, a real client session — see Backlog
- [~] (from Step 58) `vidgen plan` — left: truncated prose bullets, English-only icon search, more cues — see Backlog
- [ ] (from Step 57) Gallery 9:16 stills (`code_walkthrough`, `image` `contain`, wide `world`), mid-beat stills, project-type render test — see Backlog
- [ ] (from Step 55) `generate:` for `screenshot` / thumbnail backgrounds; a real image-generation run — see Backlog
- [ ] (from Step 51) Locale details translations cannot reach — see Backlog
- [~] (from Step 50) Thumbnails — left: measuring a frame thumbnail's text, MP4 cover art — see Backlog
- [~] (from Step 48) Clips and transitions — left: join re-encode, `reserve` per scene, a transitions view — see Backlog
- [ ] (from Step 37) `equation_derivation` highlight in the dimmed copy, `code` steps vs `dim`, Ken Burns / walkthrough render cost — see Backlog

## Phase H — Cartoons (characters, acting, stages)

### Step 72 — Automatic life: blinking and idle motion
- [~] Blinks and idle motion: `idle: false` works per character; per scene it was left to Step 73's `stage` scene

## Phase Q — Isometric story worlds

### Step 169 — Mood, small characters, sounds and lint
- [ ] (optional, not done) closed doors blocking routes

## Phase T — vidgen studio: a local music workstation for humans

### Step 196 — Fast re-render
- [~] Section-only render: measured and not built (a section is cut from the remix; DESIGN §94.14 says why)

## Phase U — Cell biology at university and research level

### Step 205 — Transport and membrane processes as actions
- [~] `set_state` in a `cell` scene not done (molecule scene only); a vesicle taken in by endocytosis is not a new object of the world

### Step 206 — Gene expression as actions
- [~] Step 205 gaps not taken up (`set_state` in a cell, the endocytosed vesicle as an object, stale labels); 9:16 close-ups leave vertical space unused

### Step 207 — Signalling pathways
- [~] 16:9 holds about nine ranks at the readable size (the pi3k_akt template fills it; bigger pathways are drawn smaller with a warning); arc labels are left out in long left-to-right pathways (`edge_labels: auto`); no `carry:` of a molecule between a `cell` and a `pathway` scene yet

### Step 208 — Cell cycle, division and energy
- [~] The cyclin curves are stylised; meiosis in an animal cell only; chains move two electrons per run (Q cycle counted, not animated); the gallery budget is nearly spent (the chain's GIF left out)

### Step 209 — Scientific accuracy lint and references
- [~] English narration only; claims across sentences or behind a comma are not read; no `vidgen refs check` (no network by design); molecule scenes have no `target_text`

### Step 210 — Example, docs and gallery
- [~] The exocytosis captions name neuronal SNAREs (turned off in the example; left for Step 211); a hepatocyte is drawn as the typical animal cell

### Step 211 — Review of Phase U
- [~] No `set_state` in a `cell`; an endocytosed vesicle is not an object; stale zoomed-view labels after a process; glyph letters below the readable size (pre-existing lint findings)

## After Phase U

### Step 212 — Regenerate the cell-biology gallery previews
- [~] Lint: the same kinds of findings as Step 211 (glyph letters in ATP synthase, the Na⁺/K⁺ pump and the respiratory chain; dense showcases over 40 words), none new

### Small open items after Phase U
- [ ] Planner chapter cards: `vidgen plan` still writes chapter cards of 2.5 s; the docs now recommend 3.5 s (`duration: 3.5`) — decide whether the planner should follow the cookbook
- [ ] Gallery polish (cosmetic, pre-existing): letters inside the ATP synthase, Na⁺/K⁺ pump and respiratory-chain drawings (α, β, Na⁺, H⁺) below the readable size; long label leaders (mitochondrion labels in the `cell` overview, Granum/Stroma in the 9:16 plant cell); "cAMP → AMP" under the dimmed PDE4 box in the 9:16 glucagon pathway
- [ ] Phase U gaps: no `set_state` in a `cell` scene; an endocytosed vesicle is not a targetable object; zoomed-view labels go stale after a process; 9:16 close-ups of long horizontal strips (a gene, a membrane) leave height unused; the eIF4G·4A blob overlaps "40S" during scanning in 16:9

## Phase V — Genetics at university level

### Step 213 — Genetics model and plan
- [~] No scene type or renderer yet (the Punnett square is Step 214); ZW / X0 sex systems, heteroplasmy and age-dependent penetrance not modelled

### Step 214 — Crosses and Punnett squares
- [~] Phenotype names written in `loci` are not translatable (`vidgen translate-template`); percentages are left out of the phenotype table when the panel is too narrow; genotype tables stop at 12 classes (a trihybrid counts phenotypes)

### Step 215 — Pedigrees
- [~] One locus, two alleles; no new mutations, phenocopies, manifesting heterozygotes or heteroplasmy; quadrants for several conditions not drawn; a partner from another generation (uncle–niece) not laid out; a person who married into the family twice not supported; the stated-mode warning is for Step 219's lint (`pedigree_plan.declared_mode_problem`)

### Step 216 — Chromosomes: linkage, maps and karyotypes
- [~] Band positions are schematic (ISCN names placed by an even split of each arm, not measured ideogram positions); the inversion loop at pairing, mosaics, rings, isochromosomes and markers are not drawn; a karyogram does not animate structural edits (an ideogram does)

### Step 217 — Molecular genetics
- [~] One window of a transcript per `mutation` scene; splice prediction schematic (no cryptic sites); SpCas9 / SaCas9 only, no off-target search or base / prime editing; one PCR product, stylised Sanger peaks, a seeded NGS read model (not an aligner)

### Step 218 — Population genetics
- [~] Two alleles only (no multi-allelic HWE or exact HWE test); no age structure, selfing or assortative mating; the synthetic GWAS is a display model (a few thousand variants, LD as a decay with distance), not a genotype simulation; no conditional analysis, fine-mapping or gene track in the regional plot

### Step 219 — Accuracy lint for genetics
- [~] English only; claims across two sentences are read only for Hardy–Weinberg numbers within one beat; shares are matched to phenotypes by their names (and "affected" / "carriers"), not to genotype classes or gametes; pedigree probabilities only for people named by NSGC id or "unaffected sibling" and the proposed child; no check of GWAS thresholds or PCR / gel numbers in narration

### Step 220 — Example, docs and gallery
- [~] NGS insertions are not modelled (the two 9:16 lint warnings were fixed in Step 221)

## Phase W — Science foundation: scientific charts and worked calculations

### Step 222 — Plan and chart core
- [~] Not yet (planned): error bars, bands, fits, histograms, annotations (223); live series (224); units engine and `calculation` (225); lint (226); adoption by domain scenes, example, `science` guide topic, cookbook (227)

### Step 224 — Live and animated plots
- [~] Not yet: a rescaling panel needs all its series on one progress; a filling histogram's bins are fixed by all its values

### Step 225 — Units and `calculation`
- [~] Not yet: no ± uncertainty propagation (significant figures only); Phase U / V worked-number cards unchanged

### Step 226 — Lint
- [~] Not yet: numbers of intermediate steps; a pure number whose value the sentence does not name; `bar_chart` / `line_chart` labels against their data

### Step 227 — Adoption, example, docs, gallery
- [~] Not yet: the population / GWAS / cyclin / action-potential plots keep their own drawing (reasons in §97.12); a single factor wider than the frame (G's unit in 9:16) still falls back to SI numbers

### Step 228 — Review of Phase W
- [~] Kept as documented gaps (§97.13): SI fallback for a single factor wider than the frame, `label_size: caption` for crowded 16:9 fit figures, one progress per rescaling panel, no zoom on broken axes, the 9:16 fit box room, chart-scene value labels unchecked, the domain plots of §97.12

## Phase X — Orbital mechanics

### Step 229 — Plan and orbital model
- [~] Not yet (planned): burns and transfers (231); rotating frame, Lagrange points (232); example, cookbook, guide topic (235)

### Step 230 — Kepler's laws and orbital speed
- [~] Not done: pausing / slowing the clock on an action; sectors and vectors with n-body; the orbit gallery media still show 229's layout (Step 235)

### Step 231 — Manoeuvres
- [~] Not done: the gallery media (Step 235); n-body with burns; the flyby's probe drawn only in the planet's frame (no heliocentric before / after orbits); a plane change is seen from above only as its projection

### Step 232 — Many bodies
- [~] Not done: n-body with burns; zero-velocity regions only as their boundary; the tidal schematic's bulges do not lead (no spin, no friction); the gallery media (Step 235)

### Step 233 — The Solar System on a date
- [~] Not done: the Moon's position on a date; Table 2a (3000 BC – 3000 AD); light-time / aberration / equinox of date; greatest elongations; the gallery media (Step 235)

### Step 234 — Accuracy lint
- [~] Not done: claims about bodies the scene does not show (no textbook table of the Solar System); eccentricities, inclinations and mass ratios said as pure numbers are not read; `orbit_scale` only flags enlarged bodies it is sure of (from the extent, before the layout)

### Step 235 — Example, docs, gallery
- [~] Not done: a gravity-assist aside in the example (the gallery's `orbit` page and the guide have the flyby); the capture at Mars; a 1080p check render (made at 720p: one 47 s orbit scene at 1080p exceeds a 10-minute command here)

### Step 236 — Review of Phase X
- [~] Kept as gaps: n-body runs with burns; a heliocentric flyby trajectory; an exaggerated-altitude view for LEO at true scale; open-orbit framing beyond 3 × the periapsis without `extent`; small 9:16 pictures with an inset or a long panel

## Phase AA — A second story cartoon: a neon city, an implant's view, other timelines

### Step 252 — Remaining features and a test cut
- [~] A closer look at a pod's rider: not needed for now (a `zoom` on the lane's end spot with `size: 1.4` reads); revisit in 253 if the city shots need it

### Step 253 — The story video
- [~] A closer look at a pod's rider: still not needed (the city shots are wides and tower zooms)

### Step 254 — Shorts and review
- [~] Lint does not check a `hook` while it shows (noted in CONFIG / the guide: look at the still at 1 s)

## Phase AD — Seven features without AI APIs

### Step 271 — Iso weather
- [~] Iso weather (puddles, fog and wind on iso places, outdoors) — partial: no flag object to sway; characters are not mirrored in puddles

## Phase AH — Generated video shots through OpenRouter

### Step 297 — The paid experiment (LATER, gated on the owner's go-ahead)
- [ ] With the owner's key, ≤ US$2.00 total, vertical 9:16 Shorts, lowest sensible resolution, 4–5 s clips

## Phase AK — A fast test suite, then `web` scenes: HTML, CSS and JavaScript written by the author (owner's request, 2026-11-11)

### Step 328 — `web` scene, the core
- [~] Left for later: the YAML `params` mapping (`ctx.params`, Step 330); files the page loads are not in the cache keys (Step 330)

### Step 332 — Lint reads the page
- [~] Not done: lint or a storyboard still renders the whole scene in Manim (no still-only path); text inside pictures, WebGL or an unannounced canvas is not read; contrast over a picture or gradient is not checked; the guide topic is Step 333

### Step 336 — Animation and chart libraries for web scenes
- [~] lottie-web ships as the package's ES build (589 kB, not minified, `lottie.version` reads `[[BM_VERSION]]`); the UMD `lottie.min.js` (306 kB) behind a wrapper would save 283 kB: the owner's choice

### Step 337 — Relative URLs in a `script:` scene; what `render --scene` renders
- [~] Bug B: `vidgen render --scene X --variant Y` renders every scene when that variant or quality was never rendered (no renders to join); behaviour kept, `render` prints which scenes it adds and why, and `--help` says it

### Step 338 — Another font with no internet: the project's `fonts/` folder; the Google Fonts warning
- [~] `.woff2`: not read (fontTools needs `brotli`, which a plain install does not bring; no dependency added); `vidgen validate` warns; a page's own `@font-face` still uses such a file
- [ ] Not tried: Windows and macOS; `.ttc`; the `imagegen` placeholders, PDF slides and contact sheets keep their bundled fonts; no check that a theme family exists anywhere

### Step 339 — `design_width`: a `web` page built in fixed pixels needs no rewrite
- [ ] Not verified: `web_clipped` / `text_overlap` on a real `design_width` page; scales outside 0.125–2.77; Windows and macOS. Found, not fixed: `examples/web`'s `cycle.html` at 160x90 gives one of two pictures for some frames from run to run (also before this step)

### Step 340 — A fast draft of a video with `web` scenes; the README names the six kinds of scene
- [ ] Not done: a draft is about 2.5 times faster than a preview, not more (a draft frame costs half a preview frame, and there are half as many); no progress line while a `web` scene's frames are drawn; no whole-length final render measured in this step

### Step 326 — A dissolve of a few frames where a clip continues the one before, on request
- [~] Tests added to `tests/test_clip_join.py`, **not run with pytest** (owner's rule); each new test body was run once by a plain script
- [ ] Not tried: a final-size (1080x1920, 30 fps) render, `{dissolve: N, level: false}` and `hold` with a dissolve in a real render; nobody watched the previews

### Step 325 — A clip that continues the one before matches its brightness and colour
- [~] Tests `tests/test_clip_join.py` written, **not run with pytest** (owner's rule); each test body was run once by a plain script
- [ ] Not tried: a final-size (1080x1920) render; nobody watched the previews

### Step 324 — Three snags found by following the short prompts
- [ ] For the owner: a dry run of `vidgen generate frames` re-cuts `layout.png` and can block a shot using `first_frame: painted` (reported in HANDOFF; code unchanged)
- [ ] For the owner: `/home/bpsa/app/video-projects/how-to-direct-your-ai/script.md` was off limits; its Cards 6 and 12 now differ from the cookbook

### Step 323 — An AI given only short prompts finds and follows the long cards
- [ ] For the owner: `/home/bpsa/app/video-projects/how-to-direct-your-ai/script.md` was off limits in this step; the intro of the cookbook now says the video uses short prompts

### Step 322 — A plain install brings every Python package
- [~] `misaki[zh]` added; `misaki[ja]` left out (pyopenjtalk has no wheels): owner to decide about Japanese Kokoro voices
- [ ] For the owner: Card 1 in `/home/bpsa/app/video-projects/how-to-direct-your-ai/script.md` not updated (that folder was off limits in this step)

### Step 321 — The tutorial's cards fixed after a fresh agent followed them (voice, refs, shots, readable overlays, disclosure)
- [~] S5 empty `.srt`: left, pinned by `tests/test_render.py` (`result.srt.read_text(...) == ""`)

### Step 320 — The tutorial script and the cookbook of instructions for directing an AI
- [ ] For the owner before publishing: the docs and commands are not on `origin/main` yet (see HANDOFF Step 320)

## Phase AL — What three music films asked of the generator (owner's request, 2026-11-14)

### Step 341 — Fix: an edited script of a `web` scene of an extension type was not rendered again
- [ ] Not covered: an extension scene type that does not subclass `Web` and calls `vidgen.api.make_web_clip` itself (its script is in no render fingerprint); the real Escapement project was not rendered (read-only; its layout was rebuilt small); Windows and macOS

### Step 342 — `vidgen still`: single frames of a `web` scene's page without rendering it
- [ ] Not done: a time on the video's clock (without `--scene`); stills of other scene types; `data:` values overridden on the command line; a still with vidgen's title, overlays and captions; `--exact` on a WebGL canvas that is never cleared was not tried; Windows and macOS

### Step 343 — Synth instruments I: brass and organ
- [ ] Not done: nobody has listened (the owner's judgment of the demo files is open); (slurs and glides: done in Step 346); in `vidgen studio` the `drawbars` setting is a plain slider (0 to 888888888), not nine bars; (`registration` as a list of its names and the cookbook's table of all instruments: done in Step 351)

### Step 344 — Synth instruments II: bowed strings
- [ ] Not done: nobody has listened; (slurs, glides, per-note strokes and the bite of dynamics and accents: done in Step 346); no round-robin variation between strokes (even by design), no measured tremolo, harmonics or col legno; (`stroke` in `vidgen studio` as a list of its names: done in Step 351)

### Step 345 — Synth instruments III: timpani, toms, taiko, choir
- [ ] Not done: nobody has listened; every blow at the same settings is identical and a roll repeats one blow (no round-robin); (per-note dynamics that change the blow, a roll into a hit on one track and a drum's `pitch` per hit: done in Step 346); no rim shot, brushes, choked cymbal or flams; the choir has no words or consonants (slurs: Step 346) and nothing but breath above 5 kHz; (the named settings in `vidgen studio` as lists of names, and `vidgen music check` on a piece using these instruments, `examples/signal-fire`: done in Step 351); the choir's range warning uses the whole choir's E2–C6 whatever `voices` says

### Step 346 — Expressive notes in the score format
- [ ] Not done: nobody has listened; no glide between attacked notes and no slur through a chord; a pad note takes its dynamic at its start; the studio's step grid does not show marks or slurs (it keeps them); a long hairpin over many short drum hits is slow to render (one new blow per dB)

### Step 347 — Built-in music data for `web` scenes
- [ ] Not done: per-track audio analysis; a cue starting inside a scene gives that scene no song time; Windows and macOS not tried

### Step 348 — Smaller intermediate clips
- [ ] Not done: the estimate assumes a detailed WebGL page (a flat page is overestimated up to 40×); the scene clips' own CRF 23 is untouched (it is the delivered picture); Windows not tried

### Step 350 — Ready-made finishing for three.js `web` scenes
- [ ] Not done: a cheaper per-object motion blur (stays a page technique), SMAA, a transparent output, MSAA of the scene target; `nebulaSky` and the `geneva` / `perlage` / `sunray` finishes only drawn in one quick check (`/home/claude/work/scratch/al350/helpers/`), not in a film; Windows and macOS not tried

### Step 351 — Critical review of Steps 341–350
- [ ] Left from the review: `vidgen still` keeps every drawn frame (and the sheet's tiles) in memory at full size (`--count 100` at 1080p holds about 1.4 GB); `load_music_score` refuses a `str` path with an `AttributeError` (public in `vidgen.studio`; not changed because it is in the score loader, which this step left untouched); `ctx.music.sounding` looks at every earlier event of its track on each call, and the event functions without a track sort every track's events on each call (fine for the films' 5,000 events; slow for far more); the choir's range warning ignores `voices`; `drawbars` in the studio is a number slider; `3d` guide passes still draw without the writer thread; Windows and macOS not tried for any Phase AL step

### Step 352 — Escapement as an example (owner's request, 2026-11-16)
- [ ] Not done: the whole film was not rendered from the example (render time estimated from 8 s rendered at final quality); `--draft` checked with one still only; Windows and macOS not tried

### Step 355 — Parallel Space as an example (owner's request, 2026-11-16)
- [ ] Not done: nothing rendered from the example (no still, draft or final; the render time is the earlier measurement of the film); Windows and macOS not tried

## Phase AM — Music-video tools (owner's request, 2026-11-16)

### Step 358 — A library of three.js building blocks for music videos
- [ ] Not done: no film rendered (stills only); Windows and macOS not tried

### Step 359 — A storyboard from the music
- [ ] Not done: no draft rendered (stills of the seven looks at 480x270 from a 22 s synthetic score only); ~~no MCP tool for the plan~~ (Step 362: `music_plan`); Windows / macOS not tried

### Step 360 — A "watch it" motion check
- [ ] Not done: aliasing that looks like a slow or backwards turn (needs the scene's intended speed); scene themes (`score:`) not read for music events; no `--render` (render first); Windows / macOS not tried

### Step 361 — More choir
- [ ] Not done: nobody has listened; consonants start on the step (not before it); only the consonants l, n, m and d; the studio has no control for syllables (marks are kept in the text); Windows / macOS not tried

### Step 362 — Review of Steps 358–361
- [ ] Left: `morph` with a syllable is a documented no-op, not an error; the PS `afterglow` scene's `melody` fix is the same code as `heart`'s but no still was taken there; Windows / macOS not tried

### Step 363 — The choir's `d` without its "sht" (owner's bug report)
- [ ] Not done: nobody has listened to the new demos yet

## Phase AN — Space scenes (owner's request, 2026-11-17)

### Step 371.1 — YouTube Shorts in the gallery (owner's request)
- [ ] Open: the titles of Shorts 2–6 (alt text is "YouTube Short 2" … "YouTube Short 6" until the owner gives them)

### Step 377.1 — Three more YouTube Shorts in the gallery (owner's request)
- [ ] Open: the titles of Shorts 7–9 (alt text is "YouTube Short 7" … "YouTube Short 9" until the owner gives them)

### Phase AN leftovers (after Step 378)
- [ ] Rotation data and the light's constants were written from memory (Neptune's rotation: 16.11 h used, the 2015 report about 15.97 h): a person checks them against the IAU reports — no network in the steps
- [~] Not reached from YAML yet (Step 392 reached the kit's parts, flash cuts, a warp across a cut and match cuts inside a scene): the wormhole passage (it moves the camera itself, outside the `SpaceView`'s floating origin and the moves' join check: a move of its own in vidgen/space-camera first), match cuts across two scenes (no state between scenes), the spiral galaxy (a turn of its own and an exposure first)
- [ ] `follow` on a radial flight (after an escape burn) rolls and loses the world; no view keeps the world behind the craft — Outbound's departure shows it
- [ ] `spiralGalaxy` arms thin and sparse; the seed-4 sky's straight dark edge in one place; the Moon's hard-edged maria under planet-shine — seen in stills, not looked into
- [ ] No ground below a world map's texel (a close limb is soft at 512; 1024 costs 8 s more to open) and no local surface patch for a zoom to the ground (Steps 368, 371)
- [ ] `vidgen motion check`: crawl of stars that keep their light while stepping whole pixels, and shimmer of under half the stars, are not found; a fly-through of point stars is not judged for shimmer (Step 378 chose no false warnings)
- [ ] Ordinary meshes partly hide the glare (craft by balls; an asteroid field's instanced rocks do not); rocks cast no shadows on each other, a world's shadow does not fall on a belt or on rings; planet-shine is one unshadowed light — each a measured cost not yet paid
- [ ] A plume's depth is its cone's; shadow maps are one 2048 map over a craft's box; a craft's reflections are baked once a shot — for craft filling the frame for long
- [ ] Space-scale: a `dots` option for `log` mode; reversed float depth (needs three-finish's depth texture changed, re-keying its pages)
- [ ] FXAA in `vidgen/three-finish` breaks stars and thin rings: the `space` scene turns it off; a star-safe anti-aliasing would re-key the earlier films' pages
- [ ] `reveal`'s `air` is given by the author, not read from the world's atmosphere; a close-up of a craft on its path line wants more `path_samples`
- [ ] The flat `orbit` scene with a transfer that ends before its second burn (now accepted) was not drawn
- [ ] The orbit model: a fly-by is planar and its planet moves at a constant speed (patched conics); dated planets move on two-body orbits after the date; no rotation data for Pluto, other moons or bodies of one's own — each a stated approximation, enough for pictures
- [ ] Looks seen as approximations: the real Milky Way is the algorithm's band on the real plane; dust does not dim point stars; the desert's canyon is one trough and a giant's bands painterly close up; no rotating black hole, jets or thick disc; hole and wormhole bend only the sky; the wormhole's skies are cube pictures (soft stars); the automatic exposure meters bodies and the sun only — each a design step's worth
- [ ] Thin struts shimmer a little at middle distances (no FXAA); no ground for a lander; a moon beside a fly-by at its true distance is a point at best — choices of a shot more than faults
- [ ] The contact sheet has no tiles of space-scale's modes or the craft views (no orbit data or `SpaceView` on the sheet's shared renderer)
- [ ] `music:` track names are checked against `music_data.tracks`, not the score file; page warnings print only when a clip is drawn (not when a stored clip is reused)
- [ ] Outbound was never rendered at full size and nobody has listened to its score; no space film has run on Windows or macOS or a real GPU

## Phase AO — Air, planes and giant ships (owner's request, 2026-11-17)

- [ ] Two gallery Shorts still have placeholder titles ("YouTube Short 7" TSMGYvusLXA, "YouTube Short 8" CrLAV33RlIU): set them in `gallery.YOUTUBE_SHORTS` and the alt text at the end of `docs/gallery/README.md` when known

### Phase AO leftovers (after Step 393)

What the review did not fix (each with what it would take):
- [ ] The two limbs from orbit: `vidgen/space-air`'s is about twice as bright and harder than `vidgen/space-bodies`' (the body sums 4 slabs, no ozone); changing the body changes Phase AN's pictures, so a cross-fade above the air or the body drawn with `air: false` under the dome is the way.
- [ ] Sea: ~~close up a steep sea's finest waves read as a woven texture~~ (gone: Step 396), the storm's foam is sparse and soft (no breaking shapes, spray, wakes, shore waves); the glitter's sides are parallel from high up; no mirror image or shadow of things on the water; a calm sea at noon is dull.
- [ ] Clouds: towers stubby from afar, anvils thin, cumulus undersides smooth; a giant's decks soft, an ice giant's bands hardly differ; ~~a faint repeat of the decks' pattern from about 60 km~~ (gone: Step 395); the decks do not read the globe's cloud map (they agree in colour and roughly in cover, not in place); things of the scene are never hidden by a cloud; no cloud in the sea's mirror; a giant's rings not in its sky; `giantAir` is not the air the body shows from orbit.
- [ ] Ground: the canyon is loops, not a drainage tree, and reads as terraces from 3 km under the dusty air; a range has no cliffs or scree and is soft under about 400 m; volcano channels evenly spaced, flows as tints; the globe's 10–30 km craters and its snow cover are not the ground's; shadows are not kept between pages (a warm start is 8 s at 720p) and a moving sun re-bakes them (2.4 s a frame).
- [ ] Planes and effects: no shadow of a plane on ground, sea or clouds; canopy night lighting not tied to the sun; the shock layer's edge steps and teeth; the diamonds flat lozenges; the vapour cone an upright puff; a flight far from its anchor lit by the anchor's sun (re-anchoring along a long flight, below).
- [ ] Giant ships: a whole hull on black from far and a fleet read as models (tone steps between big plates); the twin weakest, the lance plain, spine and lance alike broadside; the bank plume a soft beam; a close view covering every pixel costs 2.0 s a frame.
- [ ] Camera: `scaleZoom` loses the ship under a pixel before the world is whole; `hullReveal`'s traverse is over black; `climbThrough`'s fog flat grey; no reveal from behind a nearer ship; `chase` does not look for ground between the camera and the plane; a skim after a descend over rough ground may start higher than the descent ends.
- [ ] The descent: the plane version (following a plane out of a `reentry` leg) and re-anchoring the local frame along a long flight; the joined world inside a `SpaceView`; no city lights on a joined world's night side, no deck shadows on the globe.
- [ ] Flight paths: no wind; isothermal speed of sound; a re-entry glide higher than real with a steep end at low lift over drag; curves in the leg start's tangent plane.

Not reachable from `video.yaml` (`script:` or `vidgen space-page`):
- [ ] the wormhole passage; a re-entry from orbit in a surface scene; a sun that moves through a scene; the camera placed by hand in a ship's own axes; a fleet of planes; a hull in a surface scene; effects other than `exhaust` on an orbital craft; a plane's own shadows; match cuts across two scenes.

Never verified (drawn or run nowhere so far):
- [ ] any film or clip at 1280x720 and 30 fps of the Phase AO parts (stills, strips and draft clips at 320x180 to 426x240 only); lightning on a track and the lava's glow on music were drawn but their response to the music was not looked at frame by frame; a coast (ground and sea) in a joined world, a joined world at dusk or at night, with a craft in it, `globe: {size: 2048}`; three-finish over a surface scene beyond one still; `exposure: camera` / `auto` with the sea, clouds, ground or effects; worlds other than the presets' in the air; inside a `SpaceView`: the sea, the clouds, the ground; any real GPU, Windows and macOS for the cache's folder renames and the half-float targets.

### Footage, not a render (owner's request, 2026-11-23)

- [~] **Step 402 — the finished render to a video model.** Built and tested (`guide: final`, `audio: mix`, prompt wording, freshness records); left: the one paid clip — 5 s of a web scene (a plane chase over the sea) with the film's sound, the prompt and a reference picture sent to Seedance 2.0 for real footage, then judged; OpenRouter refused it with HTTP 402 at $3.57 of credits
- [~] **Step 413 — fewer and steadier colab calls** (`vidgen remote`: one tar up, one `begin` exec, a cached VM file list, retries, a per-session lock for every `colab` call). Left: a real run (session `ltx` had ended before the step began)
- [ ] LTX-2.3 on a Colab G4 (RTX PRO 6000, 96 GB): `setup_session.py NAME --gpu G4` with the unquantized model (`Lightricks/LTX-2.3` `ltx-2.3-22b-distilled-1.1.safetensors`, 46.15 GB, or the dev checkpoint + `ltx-2.3-22b-distilled-lora-384-1.1.safetensors` at 0.5 as the official graph), the full Gemma (`Comfy-Org/ltx-2` `gemma_3_12B_it.safetensors`, 24.38 GB), `LTXAVTextEncoderLoader` / `CheckpointLoaderSimple`, and a second stage with `ltx-2.3-spatial-upscaler-x2-1.1.safetensors`; ~75 GB of downloads (from the Step 404 HOWTO).
- [ ] The Colab LTX VM as a service for vidgen: a small HTTP wrapper (not ComfyUI itself) behind a Cloudflare quick tunnel, `POST /jobs` returning a job id at once and `GET /jobs/<id>` for state and result URL (a quick tunnel cuts requests at ~100 s and does not carry SSE reliably), a per-session bearer token, control videos uploaded as files, the tunnel stopped with the session; retry the new address's DNS before use (from the Step 404 HOWTO).
- [ ] LTX restyle ideas (Step 405): keep the subject's details in the photoreal first frame (edit only the background with a mask, or paste the CG subject back and blend); a photoreal last frame for long shots; a sparse canny of only the subject and horizon with the depth; a depth convention that keeps the horizon visible (a floor or gamma in `vidgen.web.depth`).
- Later, not planned yet: flare ghosts and veiling glare with the sun near the frame; lens dirt and window reflections / double panes; rolling shutter; focus breathing and hunting; compression character (blocks in flat sky, crawl in detail); frame rate and shutter angle per look.

### Shadows in the air (owner's request, 2026-11-23)

- Later, not planned yet: sharp light shafts (a haze layer with its own, lower scale height; a finer shadow picture); towers' shadows in the air; the sea's reflection and the exposure knowing about the decks; a cloud's diffuse light coloured by the cloud.

---

## Ideas for future phases (discussed with the owner, not planned yet)

Each content area below would be a phase of its own, built like the cell-biology phase: a model
with real rules (no manim), a renderer, actions timed to beats and words, validation with clear
errors, an accuracy lint, docs, a gallery section, an example and a review.

### Top picks
- [ ] **Video studio (notes on whole videos).** Like the music studio's listening notes: open the
  rendered video in a local page, pause anywhere and pin a note ("too fast here", "this label is
  hard to read", "I want a close-up of the ribosome"); "Ask an agent" sends the notes with the
  scene, beat and frame each points to; the agent edits the YAML, re-renders only the affected
  scenes, and the new version plays side by side with the old one (A/B, keep/discard). Reuse the
  studio's session/version design and MCP hand-off.
- [ ] **Paper to video.** From a PDF of a paper: an outline, chapters and plain-language narration,
  the key figures (with credit) and equations as equation scenes, references collected
  automatically; run validate, lint (incl. the science rules) and a storyboard for review.
- [ ] **A real Windows end-to-end test run** (not a feature, but the most important next step):
  studio, Kokoro, renders and exports were tested on Linux only; a guided run on the owner's
  Windows machine.

### Protein folding (suggested last, or in two parts)
- [ ] Levels of structure (primary → quaternary); amino-acid properties (hydrophobic core,
  charges); α-helix (3.6 residues per turn) and β-sheets with hydrogen bonds; disulfide bridges
- [ ] Folding: the energy-landscape funnel; chaperones (Hsp70, chaperonin, calnexin already
  exist); misfolding and amyloid aggregation
- [ ] Real structures: load a protein from a PDB file (Protein Data Bank data is free to use) and
  draw it as a rotating cartoon ribbon, with AlphaFold confidence colours
- Effort: medium for the schematic version; large for real 3D ribbons (schu-video-generator draws in 2D today;
  Manim can do 3D)

### Other content areas
- [ ] Chemistry: molecules with correct bonding and geometry, reaction mechanisms with curly
  arrows, energy diagrams
- [ ] Physics: circuits, forces and fields, waves, simple simulations driven by real equations
  (plots of simulations driven by equations and worked calculations with units moved into Phase
  W, Steps 224–225; the physics pictures stay here)
- [ ] Neuroscience: neurons and synapses, building on the action potential and SNAREs
- [ ] Computer science: data structures and algorithms stepping through (sorting, graphs, trees),
  a natural fit for coding Shorts

### Cartoons and games
- [ ] Playable levels: export the platform levels as small playable HTML5 games (the world model
  and rules were designed for this in Phase O)
- [ ] Isometric interactions: characters sitting, opening chests, small puzzles, as story tools

### Music and sound
- [ ] Score pieces that follow the video's timings (like composed music), with builds and lifts
  landing on chosen scenes automatically
- [ ] A sound-effects designer in the studio (the same editing loop, for effects)
- [ ] Split music and sound into their own package, with schu-video-generator depending on it

### Reach and polish
- [ ] Brand kits: a theme, fonts, intro/outro and music saved once and reused across videos
- [ ] Faster renders: smarter caching and parallel scenes for long videos

---

## Backlog (after Step 60)

Not done in the roadmap; each is one line, with where it came from. Bugs first, then quality,
then nice-to-have.

Bugs / correctness
- [ ] `scenes/video_clip.py` imports `vidgen.clip_join` (`MatchPrevious`, `match_previous_problem`, `opening_treatment`), `vidgen.clips` (`FrameTreatment`, `clip_timing`) and `vidgen.videoplan` (`VideoPlan`) directly (Steps 325–326), so a built-in uses what an extension cannot import from `vidgen.api`. Fix: export those names from `vidgen.api` (as Step 157 did for the level layers), or move the join into a helper `vidgen.api` already exports; then remove `PRIVATE_IMPORTS` in `tests/test_builtin_scenes.py` (`test_builtins_use_only_the_public_api[video_clip.py]` is `xfail(strict=True)` until then; found in Step 327, left to the owner in Step 335 because it changes the public interface)
- [ ] Word anchors (Step 156): with `overlap` / `interrupt` the runner scales `at` by the beat's shorter body, so a word-timed action lands a little early; an offset like `@mid-20s` reads as the word `mid` minus 20 s (write `"@mid-20s+0s"`)
- [ ] MCP: large documents (a long video's `lint` / `storyboard` JSON, `schema full=true`) are not trimmed and can exceed a client's tool-output limit (Step 59) — page or summarise them
- [ ] MCP on Windows: process-tree kill on cancel is untested; no session with a real client (Claude Desktop / Code) was possible here (Step 59)
- [ ] `equation_derivation`: a `highlight` colour on a step is not carried into its dimmed copy; `code`'s own highlight steps reset opacities a `dim` action set (Step 37)
- [ ] Not run on real Windows / macOS: font registration, MiKTeX's install prompts, long paths (Step 7 onwards)
- [ ] Renders are not byte-reproducible at a width that is not a multiple of 16 (the 854x480 preview): Manim's libx264 encode (via PyAV) of identical frames varies between runs in fast-moving shots; compare frames before encoding or use mod-16 sizes (Step 88, found in Step 87)
- [ ] Kokoro `vidgen tts` needs more than the 1500 MB cap (killed after three beats twice; finished under 2500 MB, peak ~2.2 GB): find out whether memory grows per beat or per voice (Step 88)
- [ ] A shape swap resets that part's style: a dimmed or faded character's speaking mouth or blinking eyes show at full opacity (Steps 67, 78)
- [ ] A walk's run time is planned when its batch starts: two walks of one character due on the same frame both start from its position then; `enter` on a character already on screen first jumps it to the edge (Step 79)
- [ ] An SVG character or SVG prop outside `assets/` is not in the scene fingerprint; `use` elements pointing into a part are not followed when splitting an SVG character (Steps 69, 75)
- [ ] `vidgen mcp`: files found by scanning a folder (`assets/sfx/`, `assets/icons/`, `audio/`) are not confined to the root; a link there can point outside (Step 102)
- [ ] Lint `facing_away` takes the nearest character as the listener, so a speaker turned to the one it addresses farther away is reported (seen on a seated speaker in the Step 102 showcase draft) (Step 102)

Quality (what an agent's video looks like)
- [ ] Charts that change (Step 162): no caption or title per change; bars cannot enter or leave a race (labels fixed), `x` cannot change; no guide line from a line chart's cursor to the axes; `pie` / `heatmap` / `scatter` do not change; no example re-sorts bars (`examples/gradient-descent` shows a line chart's changes and cursor); a rescaled axis' ticks keep the decimals of the unlabelled ticks (`5.0`, `10.0`)
- [ ] `function_plot` (Step 160): a function of a parameter animated over beats (`a` in `a x^2`); parametric / polar curves; LaTeX labels; a dot's label plate does not avoid other curves; `trace` moves in x only
- [ ] `terminal` (Step 159): no general split with another scene type (only the `code` pane); a long session does not scroll (`clear` starts a new page); one colour per output (`code_morph`'s `reveal` uses `entrance_time` since Step 164)
- [ ] `code_morph` (Step 158): `code_walkthrough` does not morph between versions; a token moving to another line (a line split in two) fades out and in instead of gliding (a `reveal` action's morph takes 1.5 s since Step 164)
- [ ] Built-in pronunciation (Step 165): lists for ElevenLabs, OpenRouter and other Kokoro languages; no MCP tool for `list-pronunciation`; the respellings were checked as misaki phonemes, not by listening to Kokoro's audio
- [ ] Phase P review (Step 164): a term in `accent` colours like the default tangents, jump arcs, angle marks and terminal prompt (documented, not linted); a number line or function plot in 9:16 under karaoke captions leaves a tall empty band (the plot keeps its aspect); the karaoke band reserves two lines in 16:9 (`max_lines: 1` frees one); readback's single letters ("w") and short words come out "doubtful" with Kokoro
- [ ] `vidgen plan`: prose-derived bullet items are truncated sentences ("Every request that reaches database costs"); a closing sentence can be split between two scenes; icon search is English-only; no cues for `network` / `line_chart` / `pie` / `map` / `screenshot` / `video_clip`; nested list items dropped; an intro of 2+ sentences becomes its own `bullets` scene; TODO texts in English (Step 58)
- [ ] 9:16 stills: `code_walkthrough` listing small (a 5-line file wraps a line), `image` `fit: contain` leaves bands, a `world` map view spanning most longitudes is a strip (Step 57)
- [ ] `reserve` is per whole scene: several reserving overlays + captions shrink content until `min_font` fires (Step 48)
- [ ] A frame thumbnail's text is not measured (`min_font` / `contrast` at 320x180 from a `--frames` render or lint stills) (Step 50)
- [ ] Locale: number formats, `map` English country names, `"A -> B"` arcs naming translated pins, `lint_ignore` / `point:` targets do not follow translations; no-space languages cut cues only at punctuation (Step 51)
- [ ] A storyboard / lint view of the frames around each transition and carry (Steps 47–48)
- [ ] Cartoon lint: a speaker wholly out of view (the camera still on a flying prop, a pan not yet back) is not reported; no `depth` in the layout dump (characters at different depths overlap like same-depth ones); boxes, not pixels, decide what hides a face; keyed moves and jumps count as standing (Steps 84, 88)
- [ ] `examples/cartoon` with real Kokoro audio: three beats still read at 3.54–3.68 words/s (`narration_speed`) at `speed: 0.8` / `0.85` (Step 88)
- [ ] Characters: a portrait stage leaves a tall empty sky (Step 73; elbows and knees came with Step 92)
- [ ] Automatic directing: English word lists only (negations, gestures, manners); a speaker with several listeners and no answer looks at nobody; a look aims where the speaker stood when it starts; a close-up waits for its speaker's changes at the beat start; a written `zoom` with `until` is not followed; depth and props are not in the predicted stills (Steps 89–90)
- [ ] Screenplay grammar: no verbs for props, sitting, shots or overlaps; a walk to a character aims where it stood at the beat's start; one set per scene; ElevenLabs voices not chosen; generated voices may repeat a cast's voice (Steps 91, 93–95, 100, 101)
- [ ] Limbs: no knees in `jump`, no follow-through on forearms, no YAML `reach` / `plant`, no SVG `data-end` hand point (Step 92)
- [ ] Props in hands: a held prop is not mirrored when its holder turns; `dim` / `highlight` on a held prop pauses its following; no `on: <prop>`; `give` turns both characters at once (Step 93)
- [ ] Sitting: not on the ground or a table; a seat or lean edge at another depth than the character is not refused; no arms on the prop while leaning; no foley for sitting (Step 94)
- [ ] Shots: a shot does not follow a walk; `pan` / `follow` in a shot end it; the planner takes a seated character's head top from its standing height; the near character of `over_shoulder` is not drawn larger (Step 95)
- [ ] Reframe: x only (no zoom on the speaker in a tall frame); props and non-speaking walkers not framed; an `enter`'s side predicted from the written camera; a `follow` with `until` suspends reframing for the rest of the scene; `examples/cartoon`'s 9:16 variant needs the hill's `follow` changed to lint clean (Step 96)
- [ ] Light: particles not graded; no stars over a picture background, no twinkling; a jump or a close-up can still bring a head among the stars; shadows do not stretch with a low sun; a lamp lights nothing; no top-level `light` (Steps 97, 102)
- [ ] Rain across a scene cut: rain started by a scene's first-beat `particles` action begins after the set's 1 s fade-in, so the bed fades out and in at the cut (only a stage `particles` param carries it as one bed); a seated character on a low rock hides the rock and reads almost as standing at 16:9 (Step 106)
- [ ] Wind: not relative to a walking character; held and SVG props (except `blow_away`, Step 104), layers, pictures and SVG characters do not move; no top-level `wind`; long hair turns as one piece instead of bending; an open umbrella does not tug its holder or flip (Steps 98, 104)
- [ ] Effect symbols: always drawn in front (no depth sort), not scaled up with a close-up beyond the head's size, a cycling symbol (tear, Zs) can be between cycles in a still, none for props; an `effect` and a `surprised` face each pop a sound (Step 107)
- [ ] Motion effects: no dust where a thrown prop lands, none for `keyframes` / `move_along`, `big` does not enlarge the gesture; the screenplay's `runs to` still writes a fast `walk_to`, not `run_to`; not checked in 9:16 or at night (Step 108)
- [ ] Rooms: no rain or snow through the windows, no door sound (an entrance through a door plays the `enter` whoosh), windows not checked against the ceiling or the frame's top, one vanishing point for tiles; an open door's leaf reaches past its `at` towards the edge (a door at 0.06–0.11 was cut, Step 116) (Steps 109, 116)
- [ ] Furniture: no lying on a bed, no prop on another (a basket on a counter: `lift` by hand), no sit / lean verbs or door marks in the screenplay's directions; a round character in an armchair hides it and reads almost as standing (Steps 110, 116)
- [ ] Depth and front view: no back view; `enter` / `exit` keep the walker's depth (a door at the wall's depth needs a `walk_to` there first); a speech bubble keeps its size and offset during a walk in depth; directing and reframing plan from start depths and sizes (Step 111)
- [ ] Cards and irises: `wipe_star` (optional) not done, only a circle, no iris on a prop; the screenplay's `iris_out` closes on the centre, not on the last speaker; an `iris_in` opening on a stage shows the set's own 1 s fade-in inside the circle; a wide card wraps "Later that day…" before shrinking (Steps 112, 116)
- [ ] Clothes and animals: patterns only on the body and skirt (not sleeves or trouser legs); one seated skirt wedge for every seat height; a kid's stage size is set by hand (`scale`); a bird's wings ignore sleeves and its toes are not drawn under shoes; mouse and rabbit tails do not swing with front-facing steps; the cat's tail is cut in `animals.png`'s first cell (`write_looks_png` keeps figures in their cells since Step 123, the still was not redrawn); the screenplay plans a turtle's or penguin's walk at a person's speed; a backpack's pack is drawn over a turtle's shell, and the shell hides most of a small chair it sits on; an owl's beak is short, so its lip-sync openings are small (Steps 113, 114, 123)
- [ ] Random casts: the contrast score compares look parameters, not drawn pixels; `vidgen cast` has no `--theme`; a screenplay's random looks ignore `--seed` until the 11 built-in looks are used; `look_alike` skips SVG characters (Step 115)
- [ ] Stage fades and props: a stage whose next scene carries a target out still fades each thing on its own in its outro (`clear_all(keep=)`; otherwise the fade in and out are one picture since Step 127); `prop_overlap` sees only beat-end stills (a prop put down on another mid-beat is not checked) and compares boxes, not drawn pixels (a tall thin prop beside a wide low one may be reported) (after Step 116)
- [ ] Voice sounds: one face per beat (the first sound's); a `[gasp]`'s surprised face also plays the foley `pop`; a beat of sounds only is impossible; the face of a sound at a line's start waits for the speaker's earlier actions (a `[laugh]` while entering shows after the walk) (Steps 99, 102)
- [ ] Overlaps: no per-beat dip / fade settings; an interrupted line's caption shows its whole text until the cut; no overlap across scenes; never tried with ElevenLabs audio (Step 100); Kokoro's stored times stretch a line's last word over its quiet tail ("normal?" 3.01–4.78 s, heard 3.0–3.62 s), so an interrupt without `overlap` starts ~0.6 s after the word is heard (Step 102 follow-up)
- [ ] Voice kinds: only Kokoro voices are chosen by kind (OpenRouter models list no gender; ElevenLabs has no list here, the `# TODO:` names the kinds); declared characters' looks are not read for a kind (Step 102 follow-up)
- [ ] Includes: unused sets are not validated on their own; no set based on another set (Step 101)
- [ ] Phase I narration was not transcribed (Whisper check skipped in Step 102); Kokoro still reaches the 2500 MB cap during `vidgen tts` (page cache counted) and reads above 3.5 words/s at `speed: 0.85` (Step 102)
- [ ] Acting: a long beat makes a large speech bubble; a bubble following its speaker is not clamped to the view; `look_at` is reset by a later `pose` / `emote` (Steps 78–79)
- [ ] Motion: no follow-through on pose changes, gestures or keyed moves; no squash on footfalls; an `enter`'s wind-up happens off stage; a facing change flips at half; no facing or rotation along a `move_along` path, no `depth` / opacity keys; a lifted character walks in the air (Steps 80–81)
- [ ] Mid-action stills only for walks, gestures, jumps and keyed moves (not `pose`, `emote`, `turn`, `look_at` or camera moves); the character sheet shows no left-facing view, blink or gesture (Step 83)
- [ ] Foley: no panning by where the character stands, no depth / speed / ground variation, no landing sound, gestures and keyed moves silent; not listened to by a person (Step 86)
- [ ] Vehicles: no doors open; a beat's `shot` does not follow a ride within the beat; a rider's feet show under a car's side for a moment while it climbs in; a prop a rider holds keeps its size during a ride in depth; no vehicle words in the screenplay grammar; ride sounds not listened to by a person (Step 118)
- [ ] Water and air: a boat's ends are not checked against the water's edges (only its middle); `get_out` of a balloon stands the riders in front of the basket; no water in depth, no splash, no ride in depth on water or in the air; the balloon does not lean with the wind and the rocket's smoke does not drift; a balloon is 2.1 characters tall (a small stage `size` needed); `burner` / `launch` not listened to by a person (Step 119)
- [ ] Living props: a lamp does not light the room or the characters in front of it (its glow lies behind it); switching is instant (no fade); a carried lamp's glow keeps its place in the draw order; a tv has no sound, a clock does not strike; screenplay has no words for them (Step 120)
- [ ] Fire, steam, nature: a fire lights no character; its crackle plays while it burns in the scene, also with the camera elsewhere; a carried kettle's steam keeps its draw-order place; a fallen fruit is not a prop (cannot be picked up) and nothing checks that a `drop_fruit` `to:` character stands under the tree; birds do not land or perch; screenplay has no words for them (Step 121)
- [ ] Small props: no pouring / splash sound and the water wets nothing; a phone is answered with `switch_off` (no `answer` action); balloons let go are gone for the scene; held props are not mirrored with their holder (a watering can is turned round as it pours since Step 130); screenplay has no words for them (Step 122)
- [ ] Lightning, rainbows, the sun's path: a bolt only strikes the horizon (never a prop or a character), clouds are not lit from inside; a rain storm's thunder that would start after the scene's end is left out; the sun and moon move only with a `light` change and keep their size; long shadows only stretch along the ground (no skew); an animation in which a flash falls is redrawn whole (Step 127)
- [ ] Snow and fog: no footprints; no snow caps on swaying props in wind, on characters or held props; the layer never melts; no `fog` action (fog lasts the whole scene) and none seen through a room's windows; still fog with a walk in depth still costs ~13 % render time; screenplay has no words for them (Step 126)
- [ ] Robots and costumes: a robot's wheels do not turn while it rolls and make no sound; no idle hum; an SVG character's `antenna` / `cape` do not trail in the wind; a hat (`party_hat`...) on a robot covers its antenna, so its frightened spring is not seen (Steps 124, 130)
- [ ] Expressions: SVG characters have no `cheeks` / `bristles` or the Step 125 eye and mouth shapes; hats stay on frightened heads and floppy ears do not lift; a mood's spring restarts after a `PoseChange`; small muzzles show `laugh` / `tongue` small at preview sizes (Step 125)
- [ ] Set sounds and music: no door shake on a `knock`; knocks and creaks are centred (not panned by the door's x); no splash getting into or out of a boat or for a fruit falling into water; birdsong ignores snow and fog; a light change counts as one instant; the fire bed's crackles peak at −8 dBFS in single samples (50 ms RMS −30); no time signature on a music bed, one loop each; nobody has listened to the Phase L sounds, beds or music (Steps 128, 129, 130)
- [ ] Riding off: `ride_to` takes an x from 0 to 1 and a vehicle has no `exit`, so riders cannot leave the view (the rainbow-ride example's bicycle stops at 0.88 while the robot rolls out) (Step 130)
- [ ] Host timing: the previous beat's `host_point` and `host_react` are undone one after the other (0.6 s each) after the new beat's reveal and before its own point, so with a short line the new point lands at the beat's end (host-explainer `grow_b3` with Kokoro audio); undoing and the new point could be one move (Steps 134, 144)
- [ ] Host: no `reveal_steps` for `diagram`, `process`, `timeline` and the other types (the host only looks at their written highlights); a pointer line is not routed around content; a `host_move` walks in front of the content for about two seconds (seen over the text card's words); a `host_enter` on a title waits for the title's entrance; a `zoom` / `pan` moves the host with the scene; its idle counts as change for `dead_air` (Steps 133, 134, 144)
- [ ] Emotions: no breathy whisper (quieter, slower, lower: about −9 dB beside the other lines, Step 144); pauses edited in English only; one emotion per beat; `tts --json` does not list the emotion; ElevenLabs v3 tags never checked against the real API, OpenRouter's ElevenLabs models get no tags, no ElevenLabs `speed`, no `tag:` override (Steps 135, 136)
- [ ] Ready-made sets: laid out and checked for 16:9 only (the kettle's and till's `lift` are frame fractions); no sea or wind bed (beach and snowy hills are silent), no shop or classroom sounds; road / path span about 1.5 frames; `vidgen screenplay` does not look up built-in sets or know the new props' other words (chalkboard, cash register) (Steps 139, 140)
- [ ] Drawing style: no texture on non-stage scenes or under a host; the host's effect symbols and pointer line keep their width; the grain does not pan with the camera; character sheets and prop galleries draw plain (Step 142)
- [ ] Composed music, the composer: no chromatic passing tones or syncopated anchors in the melody, a generic 3/4 drum bar, no bridge between two moods (a run ends on its own cadence, the next starts on its tonic), stings at the settings' nominal tempo rather than the fitted section's, no pitch bends (symusic 0.5.9 ignores them) (Steps 146-148)
- [ ] Composed music, fitting: swells only from the type's `reveal_steps`, `reveal` actions and `sting: reveal` (not from stage actions such as a prop appearing, nor `video_clip`), and under narration the ducking hides most of them; a draft's piece is composed for the draft's timings, so it differs slightly from the preview's (Steps 148, 149)
- [ ] Composed music, tooling: rendering a fitted piece costs ~19 s for rain-check's 94 s, three moods, 13 parts, most of it the per-part loudness measurement (`loudness.kweighted_power`; symusic itself 1.2 s); offline with no cached SoundFont a composed render stops with an error instead of playing the moods' beds; no progress bar for the 32 MB SoundFont download, no `--json` for `vidgen soundfont` (Steps 145, 149)
- [ ] Composed music, listening: nobody has listened to the moods, the fitted pieces or the composed stings (MP3s `composed_*.mp3`, `composed_fit_*.mp3`, `phaseN_*.mp3` in the session outputs); rain-check's music sits low (−29 LUFS in pauses, −38 under speech, under the rain bed): the owner may want the storm and night `volume: -3` back to 0 (Steps 147-149)
- [ ] Dubbing: no per-language `overlap` / `interrupt`; OpenRouter voices named after a language (Voxtral `fr_marie_*`) are not swapped; voice labels (`Fen:`) are not translatable; a dubbed Kokoro interrupt has no word timings outside English; no `tts --all-languages` over MCP (Step 143)
- [ ] Readback flags: a beat's first word often comes out doubtful; two words heard as one ("Ever wondered" → "everwandered", probability 0.68) count as an unclear 2-word difference; no per-word audio clip to listen to; the `readback` lint rule reads only the cache (Steps 141, 144)
- [ ] A narration-only video stays at its narration's level (`audio.normalize: auto`): the host-explainer with Kokoro measured −22.3 LUFS integrated; an explainer for publishing wants `audio: {normalize: true}` or music, which the guide does not say (Step 144)
- [ ] Platform levels: a gap shows the parallax hills behind it, so it can read as a valley rather than a hole; draw a gap's sides or a darker depth (Step 155)
- [ ] Platform levels: rain, snow and fog stop at the plain stage's ground line, not on the tiles (Step 150)
- [ ] Platform levels: a move's `react` effect symbol and a `react` expression `surprised` during a move play no sound (an `effect` / `react` action's do) (Step 153)
- [ ] Platform levels: `enter` / `exit` pick up no coins or stars; a blocker that stepped back off the path is not followed by the replay any more (a later walk of it fails only at render); `close` on a door with someone standing in it is not refused (Step 152)
- [ ] Platform levels: climbing uses the front walk cycle (no hands on the rungs); walking through a low cloud shows the character inside it (Step 151)
- [ ] Platform camera: a `level.follow` hero waiting off stage for its `enter` puts the camera at the level's edge until it enters; the follow does not look ahead; `vidgen direct` and the reframe replay plan the camera's x only (Step 154)
- [ ] `small_speaker` measures a `head` part: an SVG character without one is not checked (Step 154)
- [ ] `vidgen screenplay` on a level: the directions' `at` times are estimated as on a plain stage (a wide level's walks take longer), no `climbs` verb, a level only through a front-matter or `--cast` set (Step 155)
- [ ] `web` scenes (Phase AK, Steps 328–333): no hard cut (`fade: false`) on `web`; `vidgen storyboard` and `vidgen lint` render the whole scene at preview size (no still-only path, Steps 331–332; `vidgen still` draws single frames of the page since Step 342, but lint and the storyboard do not use it); text inside pictures, WebGL or a canvas is not read unless declared with `layout()`, nor `text-shadow` / strokes, text covered by a later page element, or contrast over a gradient or picture (Step 332); only a chosen set of three.js add-ons is served (Step 334: no 3D text, Draco / KTX2 / Meshopt, HDR loaders, other controls; a page copies others into the project), and a page with its own import map (two maps) was not tried (Step 330); a file a page stopped loading stays in the fingerprint while the other quality's record lists it (Step 330); `<audio>`, GIF / WebP animation, workers, iframes, XHR / dynamic `import()` and observers are not on vidgen's clock (Step 329); of the shipped libraries (anime.js, Motion, D3, Chart.js, lottie-web) and GSAP only the calls in a measured table were run under the clock; Motion's `controls.time = t` in `frame` shows one frame late; a Motion, lottie-web or GSAP (without `lagSmoothing(0)`) animation playing by itself depends on the frames drawn before it (Step 336); build clips with alpha are about 1.5x larger at 1080p (Step 331; since Step 348 `render.intermediate: compact` keeps them about 4.6x smaller and `keep_intermediates: false` deletes them once used); a `region: bleed` page is not told where a Short's covered parts are (Step 331); nothing tried on Windows (renderer kill by `TerminateProcess`, content types, paths)
- [ ] `web` render speed (Step 349 measured it; the quick PNG, the frames clip written in a thread and a progress line are done): what is left of a WebGL page's frame is its own GL work in SwiftShader (about 1.1 of 1.24 s for the film page at 720p); a worker imports every scene type (`vidgen.scenes`, about 2.6 s a scene: lazy imports not done); `3d` scenes have no progress line and still use Playwright's screenshot path; canvas read-back, WebP / JPEG, screencast, `beginFrame`, two pages and split scenes were measured and rejected; on a machine with more cores `--jobs N` is the way to draw in parallel (10 % on 2 cores)
- [ ] `web` pages that are not repeatable (found in Step 349): a page with CSS transitions or animations that run on the compositor (`examples/web`'s `cycle`) gives 4 to 9 of 92 frames that differ between two screenshots of the same page state (by up to 25 alpha levels: the compositor moves them in real time between screenshots; `tests/test_scene_web.py::test_the_page_is_given_theme_data_beats_and_three` is flaky for this reason, 8 of 15 runs failed on Step 348's code and 4 of 15 after Step 349); a page drawn at a device scale other than 1 (`design_width`) differed in a few pixels (at most 6 levels) in 1 to 3 of 92–302 frames between two renders of the same code

Nice-to-have / performance
- [ ] Tests left out of the default run (`@pytest.mark.slow`, Step 327): make each faster and remove its mark, keeping the default run (`python -m pytest -q`) under 5 minutes (owner's request, 2026-11-08). 1926 of 8184 tests are left out, about 10719 s of test time measured file by file on the owner's 1-CPU machine (per-file table in HANDOFF Step 327; `python -m pytest -q -m slow --collect-only` lists them). Seconds saved (tests left out) by file: `test_schema.py` 634 s (74), `test_music.py` 615 s (65), `test_builtin_scenes.py` 531 s (132), `test_studio_stems.py` 477 s (26), `test_molecular.py` 359 s (3), `test_cycle_energy.py` 355 s (6), `test_music_templates.py` 336 s (23), `test_presets.py` 291 s (9), `test_phase_l_review.py` 231 s (4), `test_chapter_export.py` 175 s (5), `test_pedigree.py` 168 s (3), `test_actions_coverage.py` 165 s (99), `test_mcp.py` 159 s (13), `test_expression.py` 137 s (6), `test_icon_scenes.py` 136 s (20), `test_cartoon_outfits.py` 134 s (55), `test_frames.py` 133 s (4), `test_music_check.py` 124 s (12), `test_population.py` 113 s (3), `test_cell_scene.py` 107 s (9), `test_cartoon_robots.py` 107 s (36), `test_cartoon_wind.py` 105 s (9), `test_comparison_table.py` 104 s (24), `test_overlays.py` 100 s (13), `test_cross.py` 96 s (4), `test_chromosomes.py` 91 s (3), `test_transport.py` 89 s (6), `test_studio_ui.py` 86 s (18), `test_phase_i_review.py` 86 s (15), `test_cell_world.py` 86 s (29), `test_phase_t_review.py` 85 s (14), `test_orbit.py` 83 s (9), `test_render.py` 81 s (10), `test_push_wipe_carry.py` 74 s (17), `test_charts.py` 71 s (25), `test_storyboard.py` 69 s (5), `test_orbit_many.py` 67 s (6), `test_custom_scene_example.py` 67 s (3), `test_phase_h_review.py` 66 s (3), `test_spectrum.py` 65 s (10), `test_cartoon_directing.py` 60 s (5), `test_callout_action.py` 59 s (9), `test_tts_kokoro.py` 53 s (4), `test_studio.py` 50 s (12), `test_cartoon_moving.py` 50 s (3), `test_json_output.py` 49 s (4), `test_sfx.py` 48 s (11), `test_stat_chapter.py` 46 s (36), `test_review4.py` 45 s (3), `test_music_pieces.py` 45 s (5), `test_cuts_shorts.py` 45 s (5), `test_cartoon_more_animals.py` 45 s (13), `test_molecules.py` 44 s (17), `test_cartoon_snail.py` 44 s (10), `test_arms_front.py` 41 s (19), `test_emotions.py` 40 s (3), `test_standard_model.py` 39 s (3), `test_plot_live.py` 39 s (3), `test_timeline.py` 38 s (16), `test_thumbnail_export.py` 38 s (7), `test_process_network.py` 38 s (23), `test_phase_f_review.py` 38 s (4), `test_world_map.py` 35 s (7), `test_staging.py` 35 s (8), `test_kphi3_example.py` 33 s (3), `test_draft.py` 33 s (4), `test_cartoon_lighting.py` 33 s (2), `test_scales.py` 32 s (2), `test_phase_s_review.py` 32 s (9), `test_orbit_sky.py` 32 s (4), `test_cartoon_animals.py` 32 s (20), `test_regions.py` 31 s (19), `test_pie_heatmap.py` 30 s (16), `test_cartoon_holding.py` 30 s (6), `test_calculation.py` 30 s (3), `test_transitions.py` 29 s (5), `test_host.py` 29 s (5), `test_studio_check.py` 28 s (9), `test_phase_k_review.py` 28 s (2), `test_introspect.py` 28 s (4), `test_host_acting.py` 27 s (2), `test_chapters_progress.py` 27 s (6), `test_equation_derivation.py` 26 s (11), `test_cartoon_shots.py` 26 s (3), `test_sound_design.py` 25 s (7), `test_cartoon_lint.py` 25 s (3), `test_cartoon_foley.py` 25 s (2), `test_cartoon_acting.py` 25 s (4), `test_slides.py` 24 s (2), `test_scene_3d.py` 24 s (4), `test_gallery.py` 24 s (11), `test_delivery.py` 24 s (3), `test_videogen_input_freshness.py` 23 s (12), `test_scene_3d_passes.py` 23 s (3), `test_cartoon_sounds.py` 23 s (10), `test_cartoon_expressions.py` 23 s (8), `test_join_batches.py` 22 s (2), `test_detector.py` 22 s (6), `test_cartoon_cards.py` 22 s (3), `test_videogen_first_frame_in.py` 21 s (13), `test_video_clip.py` 21 s (12), `test_scene_3d_actions.py` 21 s (9), `test_plot.py` 21 s (5), `test_overlap.py` 21 s (3), `test_composer.py` 21 s (3), `test_icons.py` 20 s (9); and 174 more files under 20 s each (1501 s, 597 tests). Seen while timing (not profiled): most `test_schema.py` tests run `vidgen schema` and validate against the result, 15–25 s each; `test_music.py` timed out at 900 s as one file (timed in four parts).
- [ ] Platform levels that the camera rises over render at about 2.4x real time at 854x480 (sky of the platform example: 47.9 s in 113 s): most of it is Manim's PIL transform of each tile chunk in view on every frame; draw the chunks in view into one picture per frame, or cut chunks by rows (Step 155)
- [ ] Drafts: beat starts are rounded to whole frames per beat (a draft drifts up to ~0.2 s from the final over a scene); a light change still redraws the whole draft frame; animatics have no crossfade and no `--final` (Steps 137, 138)
- [ ] `--jobs auto`: a cgroup CPU quota (`cpu.max`) is not read; one per-job figure (1.5 GB) whatever the format (a 4K render needs about 2.5 GB); the Windows and macOS memory readings are tested with mocks only (Step 117)
- [ ] Stage: `follow` tracks x only, no vertical pan, layers are not action targets, a near image layer zoomed at the bottom can show a sliver; no `on: <prop>` (a prop's `lift` worked out by hand); particles have no `place: behind`, wind or ground stop; no per-scene opt-out of `cartoon_style` (Steps 74–77)
- [ ] No YAML for springs (no tail or antenna part; generated hair and ears are drawn in the head) (Step 82)
- [ ] Cartoon render speed: cache each part's subpath split (~1.1 s of `yard` on Manim 0.21); narrow the fingerprint so editing `characters:` / `cartoon_style` re-renders only scenes that use them (Steps 67, 77, 87)
- [ ] `vidgen character` does not print `idle` / `cartoon_motion`; `vidgen schema` has no enum of character names; `vidgen gallery` does not add a project's own `characters:` to its work project (Steps 67, 72, 73, 80)
- [ ] Lip sync: the misaki and espeak-ng G2P paths were only run with mocks (Kokoro's own phonemes ran for real in Step 88); one espeak-ng process per word (Step 71)
- [ ] `vidgen clean` (or a size report): `build/` and its `_bare` caches only grow (Steps 7, 50)
- [ ] Joins with a crossfade / push / wipe re-encode the whole video (Step 48); `image` Ken Burns ~1.6x real time in preview, `code_walkthrough` ~0.1 s per line (Step 37)
- [ ] MP4 cover art from the thumbnail (Steps 49–50); `generate:` for `screenshot` and behind a designed thumbnail (Step 55)
- [ ] `vidgen gallery`: mid-beat stills, a project-type render test (Step 57)
- [ ] A real image-generation (OpenAI) and speech-to-text (faster-whisper) run (Steps 54–55: no network for them here)
- [ ] OpenRouter TTS cost: confirm live that `GET /generation` reports `total_cost` for `/audio/speech` requests and how late (`tools/live_check_openrouter.py --tts --zdr --yes`, or `--generation ID`); if it never does, read the cost another way (e.g. the key's usage before / after) (Step 63)
- [ ] OpenRouter SVG generation never run live (no SVG model has a ZDR endpoint; the owner's account requires ZDR): `--svg --yes` with an account allowing non-ZDR providers (Step 61b / 63)
- [ ] OpenRouter estimates use the highest provider's price (Kokoro live: ~6x the charge); optional `provider: {sort: price}` routing or a "from $X to $Y" range (Step 63)
- [ ] Refresh `src/vidgen/data/openrouter/tts_models.json` (dated 2026-10-08) from the public lists when validate warns wrongly; a small `tools/` script could do it (Step 62)
- [ ] Kokoro: refresh `src/vidgen/data/kokoro/voices.json` (dated 2026-10-09) when the model repo adds voices; drop the Python < 3.13 marker of the `kokoro` extra once kokoro / misaki declare 3.13; Kokoro v1.1-zh not supported; a custom `.pt` voice file is hashed by path, not content (Step 65)
- [ ] `vidgen plan` could write an `output:` name from the title (a draft from `outline.md` renders `outline.mp4`); `storyboard --json` lists every still twice (video and scene sheets) — verbose for agents
- [~] **Step 421 — `setup_session.py` works over SSH.** Left: the fixed SSH route has not finished a real run (the first run stopped at the `&&`-subshell hang, since fixed; the rerun was not allowed)
