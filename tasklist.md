# vidgen task list — features for AI-authored videos

Legend: `- [ ]` not done · `- [~]` partially done · `- [x]` done

Guiding idea: the AI author cannot watch the video. Prioritise features that let it see its own
output, catch its own mistakes, and build from tested parts instead of raw Manim.

Work is split into **steps**. One agent does one step, in order, following `CLAUDE.md`
(tests pass, `HANDOFF.md` section appended, one commit `Step N: ...`). Each step is small and
bounded: if a step turns out larger than expected, the agent finishes a coherent part, marks the
rest `[~]` with a note, and the remainder becomes a follow-up step. Agents tick boxes here as
part of their commit.

Rules that apply to every step:
- New features need tests, docs (`docs/CONFIG.md` / `docs/EXTENDING.md` / README as relevant)
  and, when user-visible, a usage line in an example.
- Everything that downloads or calls a paid/remote service is optional (an extra or a provider
  seam) and is mocked in tests. Bundled third-party files ship with their licence file.
- From Step 11 on, agents check visual work with `vidgen storyboard`; from Step 14 on, also with
  `vidgen lint`.

---

## Phase A — Feedback loop (let the AI see what it made)

### Step 8 — JSON output for commands
- [x] `vidgen validate --json`: problems (with location), variants checked, estimated length, audio status
- [x] `vidgen list-scenes --json`: types, origin (built-in/project), params with types/defaults/docs
- [x] `vidgen render --json`: output paths, per-scene durations, warnings, elapsed time
- [x] Stable, documented JSON shapes (version field); tests for each

### Step 9 — JSON Schema export
- [x] `vidgen schema` prints the JSON Schema of `video.yaml`
- [x] `vidgen schema --scene TYPE` prints one scene type's `Params` schema; `--all` bundles every type
- [x] Test: all example configs validate against the exported schema

### Step 10 — Frame capture in the worker
- [x] Worker option to save PNG stills at chosen times: end of each beat (default) or N evenly spaced per beat
- [x] Files under `build/<quality>[_<variant>]/frames/<scene>/` plus an index JSON (beat, time, path)
- [x] Works with `--preview`, variants and `--scene`

### Step 11 — `vidgen storyboard`
- [x] Contact sheet PNG per scene and one for the whole video: grid of stills labelled `beat @ time`, narration text under each
- [x] Options: `--scene`, `--per-beat N`, `--variant`, `--preview` (default), `--json` (paths)
- [x] Readable at a glance when opened as an image by an AI (fixed max width, legible label size)

### Step 12 — Layout introspection
- [x] Worker dumps, at each captured frame, every visible mobject: kind, text content, pixel bbox, font size in px, fill colour, opacity
- [x] Written to `build/.../layout/<scene>.json`; documented format

### Step 13 — `vidgen lint` (layout rules)
- [x] Rules: off-frame / outside safe area, text–text overlap, font too small for the output height, low contrast (WCAG ratio vs background), too many words on screen (+ `covered_text`: shapes drawn over text)
- [x] JSON report `{scene, beat, time, rule, severity, object, bbox, message}` and a human-readable summary
- [x] Thresholds configurable in an optional `lint:` config section; per-scene `lint_ignore`

### Step 14 — Timing lint
- [x] Narration speed per beat (words/second from audio or estimate) outside a configurable range
- [x] Dead air: no visual change for more than N seconds (frame difference on sampled low-res frames)
- [x] Beat too short for its animations / animations still running after the narration ends
- [x] Added to `vidgen lint` with the same report format

---

## Phase B — Foundations for better visuals

### Step 15 — Layout regions
- [x] `vidgen.api`: safe area, named regions (`full`, `left`, `right`, `top`, `bottom`, `center`, `hero`, `caption`), grids `rows x cols`
- [x] `place(obj, region, fit="contain"|"width"|"height", align=...)` with automatic scaling
- [x] Aspect-aware: regions adapt to vertical (9:16) formats
- [x] Refactor two built-in scenes to use it; tests at 16:9 and 9:16

### Step 16 — Theme presets (mechanism + 3 presets)
- [x] `theme: {preset: NAME, ...overrides}`; preset values merged under user values
- [x] Presets: `dark_tech` (current default), `light_academic`, `high_contrast`
- [x] Test: every preset passes WCAG AA for text/dim/palette vs background

### Step 17 — Theme presets (4 more + type scales)
- [x] Presets: `warm_editorial`, `brand_neutral`, `soft_pastel`, `bold_neon`
- [x] Named type scales (`compact`, `standard`, `large`) selectable per theme
- [x] `vidgen list-themes [--json]`; storyboard of `examples/minimal` per preset checked in the step

### Step 18 — Bundled fonts
- [x] Ship three open-licensed families as package data with licences: Inter (sans), a serif (e.g. Source Serif 4), a mono (e.g. JetBrains Mono)
- [x] Registered at worker start (no system install needed); system fonts still work
- [x] Theme tokens `font_serif`, `font_mono`; code scene uses `font_mono`

### Step 19 — Icons: mechanism + seed set
- [x] `icon(name, size, color)` helper in `vidgen.api` (SVG → Mobject, recoloured by theme token)
- [x] Vendored icon folder with licence and a manifest (name, tags, category); project `assets/icons/` overrides/extends it
- [x] Seed set: 40 icons from one open-licensed set (Lucide preferred)
- [x] `vidgen list-icons [--search TEXT] [--json]` (also `--category`, `--sheet PNG`; `IconName` param type; `tools/vendor_icons.py` for Step 20)

### Step 20 — Icons: curated expansion
- [x] Expand to ~200 icons, ~25 per category: tech, data, science, business, people, arrows/UI, nature, education (200, 25 each; aliases for Lucide's old names + synonyms)
- [x] Tags in the manifest for search; test that every manifest entry loads and renders (catalogue `docs/ICONS.md` generated + kept in sync)

### Step 21 — Icons in built-in scenes
- [x] `icon:` accepted by bullets items, title, end_card (and documented)
- [x] `icon_grid` scene: a grid of icons with labels revealed per beat (groups, highlight, palette; `grid_shape` helper in `vidgen.api`)

### Step 22 — Review 1
- [x] Run storyboard + lint on every example (16:9 and vertical); fix what they reveal (all 11 example configs lint clean; kphi3 with 5 commented `lint_ignore`s)
- [x] Review Steps 8–21 for API consistency, docs accuracy and test gaps; harden `vidgen.api` (`role=` on text helpers, `region(name, "body")`, `also_accepts`, theme-default name checks, whole-word icon search, lint theme contrast; `slow` test marker; wheel install checked)

---

## Phase C — Animation vocabulary and new scene types

### Step 23 — Per-beat actions (framework + 3 actions)
- [x] Beat-level `actions:` list in YAML; scenes expose named targets (e.g. `item3`, `bar:Preview 480p`) (canonical `{action, target, at, until, run_time, ...options}` + shorthand `{NAME: TARGET, ...options}`; `@action` registry in `vidgen.api`; JSON Schema; `list-scenes` targets/actions)
- [x] Actions `reveal`, `dim`, `highlight`; implemented for `bullets` and `bar_chart` (`highlight` styles color/box/underline/flash; `until:` undoes dim/highlight; actions run inside the beat's waits, never overrun)
- [x] Unknown target/action → clear validation error (with suggestions and the scene's targets)

### Step 24 — Per-beat actions (zoom, transform, coverage)
- [x] `zoom` (camera to target and back) and `transform` (target A → B) (`NarratedScene` is a `MovingCameraScene`; zoom returns by the beat's end or before its `until` beat; `transform` `into:` another target, styles auto/replace/shapes/tex/fade; Step 23 gaps fixed: images dim/tint, dimming never compounds, a colour highlight undims, bar box stands on the axis)
- [x] Actions supported by every built-in scene where they make sense; documented table (targets on all 11 built-ins, equation `terms`; table in CONFIG.md "Beat actions" kept in sync by a test)

### Step 25 — Scenes: `stat` and `chapter`
- [x] `stat`: big number counting up, label, context line, optional comparison value (prefix/suffix/unit, decimals, separators; comparison `versus` or `before` (counts from the old value), change chip with arrow, `difference`/`percent`, `better: higher|lower|neither` → good/bad colours; optional icon)
- [x] `chapter`: section divider with number, title, optional icon (subtitle; side-by-side in 16:9, stacked in 9:16; silent or narrated; the chapter's name is `params.title` for Steps 39/49)

### Step 26 — Scenes: `comparison` and `table`
- [x] `comparison`: two (or three) columns, before/after or A vs B, per-beat reveal
- [x] `table`: header + rows, row/cell highlight actions, auto-fit to region

### Step 27 — Scene: `timeline`
- [x] Horizontal (16:9) / vertical (9:16) timeline, events revealed per beat, optional icons (sides alternate or one column, chosen to keep text largest; even or proportional spacing by date; progress line; `highlight`, `now`; targets `axis`, `event<N>`, `event:<date>`; `measure_text` and `fit_text(balance=)` in `vidgen.api`)

### Step 28 — Graph layout + `diagram`/`flowchart`
- [x] Pure-Python layered layout for directed graphs (no new heavy dependency) (`vidgen.graph.layered_layout` in `vidgen.api`: DFS cycle breaking, longest-path layers, barycenter + transpose from two starts, isotonic coordinates, ports clipped to box/ellipse/diamond/stadium, straight or orthogonal routes, label room; LR/TB; deterministic)
- [x] `diagram` scene: nodes (shape, label, icon) and edges (label, style), step-by-step reveal (alias `flowchart`; shapes box/round/pill/circle/diamond/cylinder; edge shorthand `"a -> b: label"`, `-->` dashed, chains; `reveal: nodes|layers|all` or explicit `steps`; edges grow from their source; `highlight` path; routing curved/straight/orthogonal; auto direction; fitted to the readable size with a "too dense" warning; targets `node<N>`, `node:<id>`, `edge:<from>-><to>`; groups/clusters not done, see HANDOFF)

### Step 29 — Scenes: `process` and `network`
- [x] `process`: linear pipeline of stages with a moving token (row / two snaking rows / column per frame; token dot or icon with an optional travelling tag, passes behind the stage it leaves; active stage outlined in `active_color`; `loop` arrow + step; `input`/`output`; `reveal: all` moves only the token; targets `stage<N>`, `stage:<label>`, `connector<N>`, `loop`, `token`, ...)
- [x] `network`: layered neural-net diagram built on `helpers.column`/`helpers.edges` (helpers extended compatibly: `column(horizontal=, skip=)`, `edges(colors=, shorten=)`, `grouped_pairs(n, groups, m)`, new `sparse_pairs`, `group_bounds`; layers with ellipsis + count, `dense`/`sparse:r`/`grouped:g`/`one_to_one`/`none` per layer, edge cap and opacity, forward-pass pulse steps, highlight path; LR / TB; targets `layer<N>`, `layer:<label>`, `edges<N>`, `neuron<L>.<i>`)

### Step 30 — Chart helpers + `scatter` and `histogram`
- [ ] Shared axis/ticks/legend helpers extracted from `bar_chart`/`line_chart`
- [ ] (from Step 22) Chart titles in the `header` region like `bullets`/`code`/`icon_grid`; tick, axis and value labels sized by theme tokens (in 9:16 `bar_chart` value labels are scaled down to fit narrow slots and look small)
- [ ] `scatter` (series, optional trend line), `histogram` (bins from raw values or given counts)

### Step 31 — Scenes: `pie`/`donut` and `heatmap`
- [ ] `pie` with `donut: true` option, labels, highlight slice
- [ ] `heatmap` with colour scale legend and cell highlight

### Step 32 — Scene: `code_walkthrough`
- [ ] Long code scrolls; lines highlighted per beat (`lines: "3-7"`); optional annotation per beat
- [ ] (from Steps 17/22) A code size cap for portrait: with the `large` scale 9:16 listings wrap to ~25 columns

### Step 33 — Scene: `equation_derivation`
- [ ] Sequence of equations, matching parts transformed step to step, optional per-step note

### Step 34 — Scene: `screenshot` with callouts
- [ ] Image with callouts: arrow, box, circle, magnifier; per-beat reveal
- [ ] Callout helpers in `vidgen.api` (reused by Step 41)

### Step 35 — Scene: `video_clip`
- [ ] Embed an mp4 clip (B-roll / screen recording) with optional trim, speed, caption; timing contract documented

### Step 36 — Scene: `map`
- [ ] Bundled low-res world map (Natural Earth-derived, public domain, e.g. via `world-atlas`)
- [ ] Highlight countries, pins with labels, per-beat reveal

### Step 37 — Review 2
- [ ] Storyboard + lint every new scene at 16:9 and 9:16, every theme preset; fix issues
- [ ] (from Step 22) `icon_grid` in 9:16 leaves the lower third empty with few items (rows spread ≤ 1 unit); `list-icons --sheet` could preview icons in a project's theme colours
- [ ] (from Step 22) Lint measures rotated text sideways (`min_font`); give the layout dump a text rotation
- [ ] Update `examples/minimal` (or add `examples/gallery_src`) to use each new scene type once

---

## Phase D — Overlays, audio, transitions

### Step 38 — Overlay framework + lower thirds + watermark
- [ ] Video-level `overlays:` config drawn on top of scenes (per scene on/off)
- [ ] `lower_third` (name/title, timed) and `watermark` (logo image, corner, opacity)

### Step 39 — Progress / chapter indicator
- [ ] Progress bar overlay; chapter indicator from `chapter` scenes or a scene-level `chapter:` field

### Step 40 — Burned-in captions
- [ ] Theme-styled captions burned into the video (optional), safe-area aware
- [ ] Word-by-word karaoke style for vertical formats (word timings estimated from text; exact timings if the TTS provides them)

### Step 41 — Callout overlay
- [ ] Callouts (Step 34 helpers) placed on any scene by target name or coordinates, per beat

### Step 42 — Pronunciation dictionary
- [ ] Project `pronunciation:` map applied to TTS text only (subtitles keep the original); part of the audio hash

### Step 43 — Multiple voices
- [ ] Named `voices:` and per-scene / per-beat `voice:` overrides (dialogue); cache keys include the voice

### Step 44 — Sound effects
- [ ] Procedurally synthesised SFX set (no licensing): whoosh, pop, click, tick, riser, chime
- [ ] `sfx` API in scenes and `sfx:` per-beat action in YAML

### Step 45 — Background music
- [ ] `music:` config: user-supplied file or one of 3 procedurally generated ambient beds; loop/fade
- [ ] Ducking under narration (ffmpeg sidechain) and loudness normalisation of the final mix

### Step 46 — Transitions: crossfade and fade-through-colour
- [ ] Scene-level `transition:` applied at the join stage; SRT/timing contract stays correct

### Step 47 — Transitions: push, wipe, continuity
- [ ] `push` and `wipe`
- [ ] Continuity helper: a scene can start with named objects of the previous scene in the same place (match-cut)

### Step 48 — Review 3
- [ ] Review Steps 38–47 end to end on all examples; fix, document, harden

---

## Phase E — Outputs, extras, guidance

### Step 49 — Chapters
- [ ] Chapter metadata in the MP4 and a YouTube chapter list (`<output>_chapters.txt`)

### Step 50 — Thumbnail and GIF/clip export
- [ ] Thumbnail from a chosen frame or a `thumbnail:` spec
- [ ] `vidgen export gif|clip --scene ID [--from --to]`

### Step 51 — Multi-language variants
- [~] Variants can already change voice and beat texts, with separate `audio/<variant>/`
- [ ] `vidgen translate-template --variant NAME` writes a beat-text skeleton to fill in; per-variant subtitles and docs

### Step 52 — Slides export (HTML)
- [ ] One slide per scene from key frames, narration as speaker notes, keyboard navigation, self-contained file

### Step 53 — Slides export (PDF)
- [ ] PDF deck from the same frames, optional notes pages

### Step 54 — Readback check (speech-to-text)
- [ ] STT provider seam; optional `faster-whisper` extra; mocked in tests
- [ ] Report per beat: word error rate and differing words (catches mispronunciations)

### Step 55 — Generated images
- [ ] Image-generation provider seam, cached by prompt hash like TTS; one provider; mocked in tests
- [ ] `generate:` params on the `image` scene

### Step 56 — AI author guide
- [ ] `AGENTS.md` + `vidgen guide`: workflow (write → storyboard → lint → fix), pacing rules, on-screen text limits, scene-type chooser, good vs bad examples

### Step 57 — Scene gallery
- [~] `examples/minimal` covers every Step-5 built-in, without rendered clips
- [ ] `vidgen gallery` renders one still + short clip per scene type (16:9 and 9:16) with its YAML into `docs/gallery/`

### Step 58 — `vidgen plan`
- [ ] Outline/script in, draft `video.yaml` out: sentences → beats, simple cues → scene types (no LLM call)

### Step 59 — MCP server
- [ ] Optional `mcp` extra: stdio server exposing validate, schema, list-scenes, render, storyboard, lint, gallery
- [ ] (from Step 22) `vidgen tts --json` (the only command without it); human `vidgen validate` still stops at the first variant that does not load (`--json` lists them all)

### Step 60 — Final review
- [ ] Full review of Steps 8–59; docs and examples consistent; release notes in HANDOFF.md
