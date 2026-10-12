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
- [x] Shared axis/ticks/legend helpers extracted from `bar_chart`/`line_chart` (`vidgen.charts`, public in `vidgen.api`: `value_axis`/`axis_ticks` (linear or log), `tick_texts`/`short_number`, `chart_axes` (labels thinned, gridlines), `chart_legend`/`auto_legend` (a free plot corner, else above), `chart_marker`, `linear_fit`, `chart_title`, `chart_caption`, `chart_label_size`)
- [x] (from Step 22) Chart titles in the `header` region like `bullets`/`code`/`icon_grid`; tick, axis and value labels sized by theme tokens (in 9:16 `bar_chart` value labels are scaled down to fit narrow slots and look small) (new params `title_size`, `title_color`, `label_size`, `value_size`; 9:16 value labels keep their size with a word unit under the number, else horizontal bars)
- [x] `scatter` (series, optional trend line), `histogram` (bins from raw values or given counts) (scatter: markers per series, groups, point labels placed clear of points and lines, trend each/all with equation / R², highlight rings, log axes; histogram: count / width / rule bins with round edges, counts + edges, compare overlay, percent, mean / median markers, bin highlight)

### Step 31 — Scenes: `pie`/`donut` and `heatmap`
- [x] `pie` with `donut: true` option, labels, highlight slice (labels inside a slice when they fit, else beside it with leader lines stacked without overlaps, or a swatch key below the pie in 9:16; `legend` with > 6 slices; `other_below` / `max_slices` group small slices into "Other"; total + `center_label` in the hole; sweep in all at once or one slice per beat; `highlight` pulls a slice out, the others dim; targets `slice<N>`, `slice:<label>`, `center`, `legend`)
- [x] `heatmap` with colour scale legend and cell highlight (sequential / diverging scales mixed from theme colours in OKLab — `color_scale`, `color_bar`, `text_color_on`, `mix_colors` in `vidgen.api`; per-cell text colour ≥ 4.5:1; values hidden when cells are too small; wave or row-by-row reveal; `highlight` outlines cells / rows / columns; "too big" warning; targets `cell<R>.<C>`, `row<N>`, `row:<label>`, `col<N>`, `col:<label>`, `legend`)

### Step 32 — Scene: `code_walkthrough`
- [x] Long code scrolls; lines highlighted per beat (`lines: "3-7"`); optional annotation per beat (params `steps: [{lines, note, focus}]` aligned with beats, or a bare line spec; lines by number, range, `/regex/` or `/a/-/b/`, `all`; `excerpt`; fixed-height window with `visible` rows, smooth scroll with edge fades and a scroll indicator; notes beside the lines (16:9) or in a bar below (9:16); `focus` = camera on the lines with the note as a card; targets `line<N>`, `lines:<a-b>`, `note<N>`, `title`, `listing`; revealing a line scrolls to it)
- [x] (from Steps 17/22) A code size cap for portrait: with the `large` scale 9:16 listings wrap to ~25 columns (`code` and `code_walkthrough` wrap at the size keeping 32 columns, down to the readable size: ~30–32 columns in 9:16; 16:9 unchanged; also fixed: Manim clipped listings longer than the output's pixel height, ~60 lines at 854x480)

### Step 33 — Scene: `equation_derivation`
- [x] Sequence of equations, matching parts transformed step to step, optional per-step note (params `steps: [{tex, note, match, transition}]` aligned with beats; parts marked `{{ }}`, by `match`, `terms` or `colors` move into each other (whole TeX tokens, own dvisvgm groups), the rest by shape; `history` (stacked, dimmed, aligned at `=`, oldest scroll away, `keep`) or `replace`; notes beside (16:9) / below (9:16); `colors` per term; result box / band; long steps broken at relations; TeX errors name the step with TeX's message; targets `title`, `step<N>`, `note<N>`, `result`, `term:<tex>` (current step))

### Step 34 — Scene: `screenshot` with callouts
- [x] Image with callouts: arrow, box, circle, magnifier; per-beat reveal (also `spotlight`; `steps` aligned with beats, each one callout, a list or `{callouts, focus, previous}`; shorthand `{box: [x, y, w, h], label}`; areas in fractions or `units: px`; previous callouts `fade` / `dim` / `keep`; `focus` = camera onto the step's areas with labels built for the zoom; optional `browser` / `window` / `phone` frame drawn in theme colours; targets `title`, `image`, `callout<N>`, `callout:<label>`, `step<N>`; example asset drawn by `tools/make_screenshot.py`)
- [x] Callout helpers in `vidgen.api` (reused by Step 41) (`callout_box`, `callout_circle`, `callout_arrow` (curved, label placed away from the area inside the frame), `callout_magnifier` (Pillow crop at output resolution, connector lines), `callout_spotlight`, `callout_label` (plate + readable text colour), `callout_area` (mobject / region / fractions / pixels), `label_spot`, `callout`, `Callout`)

### Step 35 — Scene: `video_clip`
- [x] Embed an mp4 clip (B-roll / screen recording) with optional trim, speed, caption; timing contract documented (mp4/mov/m4v/webm/mkv decoded frame by frame with PyAV into a `ClipMobject` (`vidgen.api`) on the scene's clock, so stills, layout dump, lint, actions and callouts see it; `trim`, `speed`, `loop` or hold the last frame, `fit_duration` within `fit_range`; `fit: contain|cover`; `region` (layout region or `bleed`), title / caption (plates over a bleed clip), `frame` chrome from Step 34; clip sound mixed under the narration (`volume`, `mute`); `screenshot` callouts per beat (no magnifier), areas on the whole picture; `dead_air` counts clip motion; example asset by `tools/make_clip.py`)

### Step 36 — Scene: `map`
- [x] Bundled low-res world map (Natural Earth-derived, public domain, e.g. via `world-atlas`) (Natural Earth 1:110m admin-0, 177 countries, from npm `world-atlas` 2.0.2 + ISO codes / English names and aliases from `i18n-iso-countries` 7.14.0, converted by `tools/make_world_map.py` into `data/geo/world-110m.json` (132 KB: antimeridian cuts, oriented rings, label points, main boxes); `vidgen.geo` (public in `vidgen.api`): `find_country` (codes, names, aliases, did-you-mean, "too small" for microstates), Equal Earth projection, named views + boxes over the date line, `fit_view`, `MapView` (fit, grow to the area, clip, cached projection))
- [x] Highlight countries, pins with labels, per-beat reveal (`map` scene: `view` auto / world / regions / box, highlights (colour, `palette`, labels on the country or beside it with a leader), choropleth `values` with the Step 31 colour scales + legend, pins `{lon, lat}` / `{country}`, flight-path arcs `"A -> B"` growing to an arrowhead, labels on plates avoiding each other and pins; `steps` per beat like Steps 32–35 with `focus` camera moves; targets `title`, `map`, `legend`, `country:<code>`, `pin<N>`, `pin:<label>`, `arc<N>`, `step<N>`; no bundled city list: pins take coordinates or a country)

### Step 37 — Review 2
- [x] Storyboard + lint every new scene at 16:9 and 9:16, every theme preset; fix issues (both examples in all 8 variants, custom_scene, kphi3: 0 findings; 9:16 growth for `comparison`, `icon_grid` labels, vertical `timeline`, `process` column; header-band titles alike (1.3x in 9:16); a table's caption follows a short table; 9:16 `world` map keeps its items' longitudes; action framework: text on fills stays readable (`on_fill`), boxes / underlines / fills follow their target, `until` keeps a scene's own dimming; `title`/`heading` synonyms for params and targets, did-you-mean for unknown keys, `one_or_many` highlights; copy-free `Fade` (walkthrough render 59 → 27 s), table fitting 85 → 26 s; quick test run rebalanced)
- [x] (from Step 22) `icon_grid` in 9:16 leaves the lower third empty with few items (rows spread ≤ 1 unit); `list-icons --sheet` could preview icons in a project's theme colours (labels 1.3x in 9:16; `list-icons --sheet PNG --theme [PRESET]`)
- [x] (from Step 22) Lint measures rotated text sideways (`min_font`); give the layout dump a text rotation (`rotation` key, glyphs measured across the line; kphi3's `lint_ignore` for it removed)
- [x] Update `examples/minimal` (or add `examples/gallery_src`) to use each new scene type once (`examples/gallery`: every Step 25–36 type once, grouped by three chapters; `examples/minimal` keeps the core types)

---

## Phase D — Overlays, audio, transitions

### Step 38 — Overlay framework + lower thirds + watermark
- [x] Video-level `overlays:` config drawn on top of scenes (per scene on/off) (`{type, id, scenes, exclude, from, to, reserve, ...options}`; a scene's `overlays:` turns all or single ones off, overrides options, or adds an overlay of that scene only; `@overlay` registry in `vidgen.api` with validated options, JSON Schema, `list-scenes [--json]`; composited into every frame inside the scene's render, fixed to the screen through zoom and fades, a pure function of video time so cuts join seamlessly; planned timeline `vidgen.videoplan` (render warns when a scene drifts from it); layout dump / lint see overlays (`overlay_overlap`, lint skips per type, unsettled overlays skipped); `reserve: true` shrinks the scenes' safe area)
- [x] `lower_third` (name/title, timed) and `watermark` (logo image, corner, opacity) (lower third: name / title / icon on a plate, `scene` + `at` (seconds or beat) + `duration`, `across_cuts`, `align`, slide in/out, raised in 9:16; watermark: image, icon or text, corner, opacity, size, inset, `fade` at `from`/`to`; `examples/gallery` uses both)

### Step 39 — Progress / chapter indicator
- [x] Progress bar overlay; chapter indicator from `chapter` scenes or a scene-level `chapter:` field (`chapter: TITLE | {title, number}` on any scene, checked for repeats / decreasing numbers / a mark right after a card; public `video_chapters(project)` → `Chapter(title, number, scene, start, end, index, count, card)` for overlays and Step 49; `progress_bar` (top/bottom edge, chapter gaps, pixel-quantised, continuous across cuts) and `chapter_indicator` ("2 · Results" / "2/5", corner, cross-fade at chapter changes, hidden on chapter cards by default); `Overlay.shown_in` so an overlay hidden on a whole scene reserves nothing there; built-in chart titles follow the reserved safe area; overlays drawn per overlay with cropped cameras; `examples/gallery` uses both (and a cardless chapter 4))

### Step 40 — Burned-in captions
- [x] Theme-styled captions burned into the video (optional), safe-area aware (`captions` overlay: bottom / top / center of the safe area, 9:16 lift, `max_lines` / `max_words` / `max_width`, plate whose opacity rises to lint's contrast ratio over anything; cues cut at phrase boundaries by `vidgen.cues` — shared with the SRT, which now cuts and times the same way — and timed by word; reserves its band at the top / bottom by default (`Overlay.default_reserve`), centred → lint `overlay_overlap`; `title` / `end_card` now centre in the reserved safe area; `examples/minimal` variants `subtitled` and `social`)
- [x] Word-by-word karaoke style for vertical formats (word timings estimated from text; exact timings if the TTS provides them) (`style: karaoke` / `words`: a few big bold words, the spoken one in `highlight` with a capped scale pop; word times: stored alignment, else syllable-weighted estimate with pauses inside the MP3's speech bounds, else over the beat (`vidgen.speech`); `voice.timestamps: true` → ElevenLabs with-timestamps, `audio/<beat>.align.json` tied to text + MP3 hash; mocked in tests)

### Step 41 — Callout overlay
- [x] Callouts (Step 34 helpers) placed on any scene by target name or coordinates, per beat (a `callout` beat action, not an overlay: `- callout: "bar:4K"` + `kind: box|circle|arrow|label|spotlight|magnifier`, `label`, `color`, `side`, `curved`, `zoom`; or `{action: callout, area: [x, y, w, h]}` in fractions of the frame / `within: safe` / `units: px`; `area` with a target = part of its picture or box; gone when the next beat starts, `until: <beat>` or `keep: true`; labels inside the (reserved) safe area, clear of on-screen text, callouts, small targets and overlays; built for a zoomed camera; framework: `Action.until_next_beat`, `default_until`, `problems`, `provides`)
- [x] (from Step 37) `screenshot` has no `caption` param (`video_clip` has one); callout labels could reuse `Target.on_fill` for the overlay's dim / highlight (`caption`, `caption_size`, `caption_color` + target `caption`, faded out during `focus` in both types; `name: X` registers a callout as a target with `on_fill`, so `dim: X` / `highlight: X` keep its label readable)

### Step 42 — Pronunciation dictionary
- [x] Project `pronunciation:` map applied to TTS text only (subtitles keep the original); part of the audio hash (term: spoken form or `{say, case_sensitive, whole_word, regex}`, `null` removes; `pronunciation_file` YAML/JSON under it; one pass, first-then-longest wins; hash of the spoken text, so unmatched beats keep their hash and an edit re-voices only the beats it changes; `tts --dry-run` shows `says:`; variants get own audio when a beat's spoken text differs; captions / SRT keep the written words timed by the spoken ones (`map_word_times`, alignments of the spoken text); lint `narration_speed` counts spoken words; `validate` warns on unused / shadowed / colliding entries; `examples/minimal` uses it. Not done: SSML `<phoneme>` / IPA entries, ElevenLabs server-side dictionaries — see HANDOFF)

### Step 43 — Multiple voices
- [x] Named `voices:` and per-scene / per-beat `voice:` overrides (dialogue); cache keys include the voice (each named voice inherits `voice:`, `settings` merged per value, `default` = the base voice; a beat is hashed with its effective voice, so beats of the base voice keep their hashes (kphi3 27 ok) and editing one speaker re-voices only their beats; TTS context only from neighbours of the same voice; `vidgen tts --dry-run` voice per beat + characters per voice, `--voice NAME`; unknown names with suggestions, colour tokens, unused-voice warning; variants get their own audio when a beat's voice differs; speaker `label` / `color`: `subtitles: {speakers: name}` tags the SRT, captions `speakers: name|color|both`; `examples/minimal` guest/narrator dialogue. Not done: per-voice pronunciation, ElevenLabs text-to-dialogue — see HANDOFF)

### Step 44 — Sound effects
- [x] Procedurally synthesised SFX set (no licensing): whoosh, pop, click, tick, riser, chime (+ swoosh, typing, success, error, thud; numpy generators with `duration` / `pitch` / `intensity`, clean envelopes, no DC, loudest 400 ms at −27 LUFS ≈ 7 dB under narration, peaks ≤ −9 dBFS; synthesised at join time and cached; project `assets/sfx/NAME.wav` extends / replaces; `vidgen list-sfx [--render-dir DIR] [--json]` with a precise description of every sound)
- [x] `sfx` API in scenes and `sfx:` per-beat action in YAML (`self.sfx("pop", at=..., gain=..., pan=..., align=..., **params)`; `- sfx: whoosh` with `at`, `gain`, `pan`, `align: end`, `params`, exactly at `at` (non-animating action: `Action.animates` / `cue`, `scene_targets`); scene `sfx:` lists in seconds for silent scenes; one sample-exact SFX track for the whole video added to the narration in the final mux, skipped by `--no-audio`; optional `sfx: {auto: true}` for built-in reveal / highlight / callout / zoom / transform actions and chapter cards; `examples/gallery` uses whoosh, chime, pop)

### Step 45 — Background music
- [x] `music:` config: user-supplied file or one of 3 procedurally generated ambient beds; loop/fade (`music: calm` / `{source, volume, start, loop, crossfade, fade_in, fade_out, duck}` / a list of cues with `from` / `to` scenes; scene `music: false | {volume}`; beds `calm`, `pulse` (96 BPM), `bright` (120 BPM): numpy PADsynth pads + plucks / bells, rendered circularly into seamless 40–60 s loops at −30 LUFS, deterministic, cached per process; files decoded with PyAV, loudness-matched, looped with an equal-power cross-faded seam; `vidgen list-music [--render-dir] [--json]` describes the beds in words)
- [x] Ducking under narration (ffmpeg sidechain) and loudness normalisation of the final mix (not FFmpeg's sidechain: a deterministic gain curve keyed off the narration's speech spans — MP3 speech bounds, never SFX; `duck: {depth 12, attack 0.4, release 1.0, hold 1.5, clips}` with look-ahead; BS.1770-4 integrated loudness + 4x true peak in numpy (`vidgen.loudness`, matches FFmpeg `ebur128`); `audio: {normalize: auto, target_lufs: -16, true_peak: -1.5}` — auto = only with music, so narration-only videos are unchanged; smooth look-ahead true-peak limiter; 24-bit `padded/mix.wav`; `render` / `render --json` / `timings.json` report the measured loudness; `examples/gallery` uses `calm` ducked)

### Step 46 — Transitions: crossfade and fade-through-colour
- [x] Scene-level `transition:` applied at the join stage; SRT/timing contract stays correct (`cut | crossfade | fade_color | {type, duration, color}` per scene (the way in) + a video default; a crossfade overlaps the scenes (video shorter), a fade_color dips through a theme colour without overlap; transitions cover only the scene before's silent tail, else it is held longer (validate warns); the plan is the one source of start times (SRT, captions, chapters, overlays, SFX, music, storyboard follow); `xfade` at the join + overlapped voice track; the incoming scene's overlays on both sides of a crossfade (no doubling); colour fades in-render under the overlays; `examples/gallery` crossfades, fade_color into chapter cards)

### Step 47 — Transitions: push, wipe, continuity
- [x] `push` and `wipe` (`{type: push|wipe, direction: left|right|up|down, soft}`, default left in 16:9 / up in 9:16; same overlap / silent-tail / hold contract as a crossfade; xfade `slide*` / `wipe*` / `smooth*` at the join; overlays kept out of the moving pictures: both scenes render the shared frames bare, the incoming scene's worker writes their overlays as an RGBA clip drawn once over the transition, so watermark / progress bar / captions stay put)
- [x] Continuity helper: a scene can start with named objects of the previous scene in the same place (match-cut) (scene `carry: [icon, "title -> heading"]`: the scene before keeps those targets through its fade-out and records their shapes in `carry/<id>.json`; the next scene shows them from frame 0 and moves them into its own target through `entrance()` (glyph by glyph, or a stretched cross-fade); `carry_in()` / `carry_move` for custom scenes; validated names; render order with `--jobs` / `--scene` handled by the pipeline; `examples/gallery` uses a push, a soft wipe and two carries)

### Step 48 — Review 3
- [x] Review Steps 38–47 end to end on all examples; fix, document, harden (preview renders of gallery (+ a copy voiced with real MP3s and captions, 16:9 / 9:16), minimal (default / social / subtitled), custom_scene, kphi3: A/V lengths equal, narration within 1 ms of its planned start, SFX sample-exact, plan = render, SRT / chapters consistent, loudness = FFmpeg `ebur128`; transitions / carries / overlays checked frame by frame; lint 0 findings on every example and variant. Fixed: narration 3 dB quieter than its MP3s (Manim's mono → stereo upmix; music recalibrated to −28 LUFS), true peak over the ceiling after AAC (limiter margin 0.4 dB), scene lengths from the average frame rate (starts drifting ms), lower third under bottom captions (`Overlay.yields`), callout due with a zoom built for the old view (`Action.after_camera`), karaoke pop crowding neighbours; quick test run rebalanced, optional `pytest-xdist`)

---

## Phase E — Outputs, extras, guidance

### Step 49 — Chapters
- [x] Chapter metadata in the MP4 and a YouTube chapter list (`<output>_chapters.txt`) (FFMETADATA `[CHAPTER]` entries at the joined scenes' starts, ms time base, + MP4 tags from `title` / `metadata: {artist, album, comment, description, copyright, date, genre}`; `M:SS Title` list, timestamps rounded down; an `Intro` chapter at 0:00 before a later first chapter (`chapters: {intro: TITLE | false}`) in published lists only, overlays unchanged; YouTube rules (≥ 3 chapters, each ≥ 10 s) warned by `validate` and `render`; `chapters: {metadata, youtube}` switches; `chapters` in `timings.json` / `render --json`, `outputs.chapters`; per-variant files; `video_chapters(..., intro=True)`; `examples/gallery` tags + 4 chapters)

### Step 50 — Thumbnail and GIF/clip export
- [x] Thumbnail from a chosen frame or a `thumbnail:` spec (`thumbnail: {scene, beat, at, overlays}` = a frame of the scene's render (rendered first when stale; `overlays: false` renders it into `build/..._bare`), or `{title, subtitle, icon | image, preset | background}` = a designed card in the theme (Pillow + the icon via Manim's camera; biggest bold title that fits, balanced lines); 1280x720 / 1080x1920 (9:16) / 1080x1080 by the format; `<output>[_<variant>][_preview]_thumbnail.png` + `jpeg: true` under 2 MB; written by every `render` (`auto`) and by `vidgen thumbnail [--scene --beat --at --no-overlays] [--jpeg] [--json]`; a 320 px copy to look at and checks at that size: `min_font`, `contrast`, `fit`, `max_words`, `file_size`, `resolution`; `examples/gallery` has a designed one)
- [x] `vidgen export gif|clip --scene ID [--from --to]` (from the joined video + `timings.json`, times relative to the scene or absolute without it; `exports/<output>_<scene>[_<from>-<to>s].gif|mp4` or `--output`; GIF: one-pass `palettegen` / Sierra `paletteuse` (changed rectangles only), `--width` / `--fps`, `--max-mb` lowers fps then width (≥ 5 fps, ≥ 160 px, ≤ 6 encodes, attempts in the JSON); clip: stream copy from a keyframe (exact frame count, sound re-cut sample-accurately with `--with-audio`) else H.264 CRF 18; `--json`)

### Step 51 — Multi-language variants
- [x] Variants can already change voice and beat texts, with separate `audio/<variant>/` (+ `language:` top level / per variant (BCP-47): language-aware caption / SRT cue breaks (word lists for en, pt, es, fr, de, it; punctuation-only neutral rules otherwise), syllable estimate, `narration_speed` ranges per language or characters/s, ElevenLabs `language_code` for models that take one (hashed only when sent), pronunciation entries per `language`, the MP4 audio language tag, `timings.json` `language`)
- [x] `vidgen translate-template --variant NAME` writes a beat-text skeleton to fill in; per-variant subtitles and docs (every beat text and on-screen text — params marked `TranslatableStr` across all built-in scenes, actions and overlays, chapter titles, `title` / `metadata`, thumbnail — keyed by stable paths with source + hash; `translations:` file applied at load (untranslated / stale texts keep the source, validate lists them); re-runs merge (kept / moved / stale / obsolete); `TextRef` params and `kind:<label>` targets follow translations; `examples/minimal` variant `pt`, partly translated into pt-BR)

### Step 52 — Slides export (HTML)
- [x] One slide per scene from key frames, narration as speaker notes, keyboard navigation, self-contained file (`vidgen slides`: a slide per beat by default (its built frame; `--per-beat N`), `--mode scene` one per scene; Step 10 stills reused like the storyboard's, `--no-overlays` from the bare renders; near-identical consecutive slides merged; WebP / JPEG / PNG `data:` URIs or `--separate` files; notes = the beats' (translated) narration; keys, click / swipe, number + Enter, `#N` hash, notes panel, overview by chapter, fullscreen, help, reduced motion, alt text; `--audio` narrated play mode on the video's timing; `--json`; key-frame selection in `vidgen.deck` for Step 53)

### Step 53 — Slides export (PDF)
- [x] PDF deck from the same frames, optional notes pages (use `vidgen.deck.deck_frames`: slides, notes, chapters, alt texts) — `vidgen slides --format pdf [--notes] [--title-page] [--paper a4|letter]`, optional extra `schu-video-generator[pdf]` (fpdf2)

### Step 54 — Readback check (speech-to-text)
- [x] STT provider seam; optional `faster-whisper` extra; mocked in tests (`vidgen.stt`: `stt: {provider: faster_whisper | elevenlabs, model, language, device}`, `schu-video-generator[stt]`; ElevenLabs Speech to Text provider too; transcripts cached in `build/readback/` by MP3 content + settings; no real run here: Hugging Face model downloads were refused by the build environment's proxy — see HANDOFF)
- [x] Report per beat: word error rate and differing words (catches mispronunciations) (`vidgen readback [--beat] [--max-wer] [--force] [--json]`: spoken text (pronunciation applied) vs transcript after a normaliser (case, accents, hyphens, en / pt number words, acronyms), aligned, edits in written words with a suggested fix each, flagged beats, worst beats, terms misheard in several beats; lint rule `readback` from the cached transcripts)

### Step 55 — Generated images
- [x] Image-generation provider seam, cached by prompt hash like TTS; one provider; mocked in tests (`vidgen.imagegen`: `ImageProvider` protocol, `imagegen: {provider: openai, model: gpt-image-1, size: auto, quality, style, negative}`; OpenAI Images `POST /v1/images/generations` with stdlib urllib, `OPENAI_API_KEY` from the environment only, retries on 429 / 5xx with `Retry-After` but not on an exhausted quota; the retry loop shared with ElevenLabs in `vidgen.httpapi`; `assets/generated/<key>.png` + `<key>.json` (prompt, sent / revised prompt, provider, model, size, date), key = hash of prompt + style + negative, provider, model, size, quality, seed; `vidgen imagegen [--dry-run] [--force] [--scene ID] [--variant]` with an estimated cost; render / validate never call it)
- [x] `generate:` params on the `image` scene (`{prompt, negative, style, aspect, seed}` or the prompt, exclusive with `path`; size from the format's orientation or `aspect`; project `imagegen.style` presets / words for a consistent look; a theme-coloured placeholder card with the prompt until generated; validate warnings for missing pictures and prompts asking for text / charts; `GenerateImage` + `generated_image` in `vidgen.api` for extension types. Not done: `screenshot` / thumbnail backgrounds — see HANDOFF)

### Step 56 — AI author guide
- [x] `AGENTS.md` + `vidgen guide`: workflow (write → storyboard → lint → fix), pacing rules, on-screen text limits, scene-type chooser, good vs bad examples (packaged guide `data/guide/AGENTS.md`, root copy kept identical; 12 topics: start, workflow, pacing, social, scenes, design, actions, overlays, audio, examples, outputs, troubleshooting; `vidgen guide [TOPIC] [--list] [--json]`; chooser table for all 28 types + a snippet each; 6 before / after pairs; validate / lint message → fix tables; tests check every command / option, scene type, param, preset, action, lint rule and sound named, and validate all 28 YAML snippets; CLAUDE.md / README say who each file is for)

### Step 57 — Scene gallery
- [x] `examples/minimal` covers every Step-5 built-in, without rendered clips; `examples/gallery` (Step 37) every newer type once — a natural source for the gallery's YAML (Step 57 took the samples from the author guide's snippets instead: one per type, already validated by `tests/test_guide.py`, and what agents read)
- [x] `vidgen gallery` renders one still + short clip per scene type (16:9 and 9:16) with its YAML into `docs/gallery/` (committed: pages, stills and GIFs, ~4.4 MB, tested < 8 MB)
- [x] (from Step 37) Check the per-type 9:16 stills for label crowding: `map` labels of small countries far apart in a 9:16 world view (a label may stand beside the wrong country with a long leader), `screenshot` / `video_clip` of a 16:9 picture leave wide bands (a portrait default `fit` / `region` could help) — map labels keep by their own place without crossing leaders, regional views narrowed in 9:16; screenshot / clip steps focus by themselves in 9:16, `video_clip` `fit: auto`
- [x] (from Step 56) Callout `label`s on crowded bar charts (against the title, on a neighbour's value or bar): placement fixed (`side` only while clear, rivals, clearance); new lint rule `label_spacing`

### Step 58 — `vidgen plan`
- [x] Outline/script in, draft `video.yaml` out: sentences → beats, simple cues → scene types (no LLM call) (`vidgen plan INPUT [--output DIR|FILE] [--title] [--format 16:9|9:16] [--preset] [--language] [--force] [--json]`: Markdown outline or plain-text script → a project scaffolded like `init`; title + subtitle + hook (an opening number → `stat` first), sections / units from headings, chapter cards + progress bar over 2 min; lists → `bullets` / `icon_grid` (icons by search) / `process` / `timeline`, tables → `table` / `bar_chart`, code → `code` / `code_walkthrough`, `$$` → `equation` / `equation_derivation`, images (copied, else `generate:`), quotes, `A -> B` → `diagram`, vs / pros-cons → `comparison`, numbers → `stat`, closing section → `end_card` with its links; sentences split by language (abbreviations per language), beats of 6–15 words fitted one per reveal step; compressed on-screen texts; `# plan:` reason + `# TODO:`s per scene; validated, summary and `--json`; `examples/plan` outline + golden draft: 19 scenes, 2:25, 1 lint finding)

### Step 59 — MCP server
- [x] Optional `mcp` extra: stdio server exposing validate, schema, list-scenes, render, storyboard, lint, gallery (`vidgen mcp [--root DIR]` / `vidgen-mcp`, official MCP SDK `mcp>=1.19` (2.x `MCPServer`, 1.x `FastMCP`); 21 tools — also guide, init, plan (file or text), list-icons / themes / sfx / music, tts, imagegen, readback, slides, thumbnail, export, translate-template — each a fresh `vidgen <cmd> --json` subprocess (Manim not re-entrant, crash isolation), stderr lines as progress, killed on cancel, renders serialised; storyboard sheets / thumbnail / gallery stills / icon sheet / swatches as image content ≤ 1568 px, paged with `images` / `image_offset`; paths confined to `--root` (`..` and links resolved); `tts` / `imagegen` dry runs unless `dry_run: false` + `confirm_cost: true`, `readback` with a paid STT asks too; resources: guide + topics, JSON Schema, gallery pages; SDK client tests over stdio)
- [x] (from Step 22) `vidgen tts --json` (and, from Step 55, `vidgen imagegen --json`: the commands without it); human `vidgen validate` still stops at the first variant that does not load (`--json` lists them all) (also `vidgen init --json` and `validate --json` `images`; human validate now lists every broken variant)

### Step 60 — Final review
- [x] Full review of Steps 8–59; docs and examples consistent; release notes in HANDOFF.md (end-to-end as an agent with the CLI and over MCP, consistency pass, wheel + sdist installed in fresh venvs with and without extras; version 0.2.0; "Release notes: vidgen 0.2.0" in HANDOFF.md, DESIGN §63. Also found and fixed: `vidgen render` re-rendered scenes the storyboard had just rendered → incremental render with `--force`; map data notices missing from the wheel; `translate-template --language`; `init`'s next-step line)
- [~] (from Step 59) MCP server: files a project's `video.yaml` names are now confined to `--root` (`VIDGEN_CONFINE_ROOT`) and cancelling on Windows kills the process tree (`taskkill /T`, untested here); left: trimming large documents, a real client session — see Backlog
- [~] (from Step 58) `code` highlight band contrast fixed (adaptive band, examples/plan lints clean); `vidgen plan`: stat labels without the subject, ranges are not stats, bare web addresses are links, placeholder beats say the whole item; left: truncated prose bullets, English-only icon search, more cues — see Backlog
- [ ] (from Step 57) Gallery 9:16 stills (`code_walkthrough`, `image` `contain`, wide `world`), mid-beat stills, project-type render test — see Backlog
- [ ] (from Step 55) `generate:` for `screenshot` / thumbnail backgrounds; a real image-generation run — see Backlog
- [ ] (from Step 51) Locale details translations cannot reach — see Backlog
- [~] (from Step 50) `post_render` hooks now run after the thumbnail (with `thumbnail` in their data); `_bare` folders kept as caches (documented with `build/`); left: measuring a frame thumbnail's text, MP4 cover art — see Backlog
- [x] (from Step 49) Plan vs render on a half frame: silent scenes now render exactly the planned frames (`timeline` / `hold` round like the plan; test at 5 fps)
- [~] (from Step 48) Mono clip sound now at full level on both channels; left: join re-encode, `reserve` per scene, a transitions view — see Backlog
- [ ] (from Step 37) `equation_derivation` highlight in the dimmed copy, `code` steps vs `dim`, Ken Burns / walkthrough render cost — see Backlog

---

## Phase F — OpenRouter providers (optional; existing defaults unchanged)

Agents build with mocked APIs only. Live checks against OpenRouter (small, a few cents) are run
by the coordinator at the end of each step with the owner's key; agents never see the key.

### Step 61 — OpenRouter image provider
- [x] `imagegen: {provider: openrouter, model: ...}` as an option; `openai` stays the default, existing projects and cached images unchanged (OpenAI cache keys pinned by a test; new optional `imagegen.resolution`)
- [x] REST via the standard library (no SDK); key only from `OPENROUTER_API_KEY`, never written; shared retry helper for rate limits / server errors (`POST /api/v1/images`; also 524 / 529 retried; app headers `HTTP-Referer` / `X-OpenRouter-Title`)
- [x] Map `size` / aspect, `seed`, `quality`, `negative` / `style` to OpenRouter's parameters; clear message for unsupported options (`aspect_ratio` nearest the format, `resolution`, explicit `size`; checked against the model's public record before the first paid request)
- [x] Decode the response to PNG in `assets/generated/`; provider and model in the cache key and the sidecar JSON (+ aspect ratio, resolution, reported `cost_usd`; SVG refused until Step 61b)
- [x] `vidgen imagegen --dry-run`: real per-model prices from OpenRouter's model list when online, else "price unknown"; MCP real runs still need `confirm_cost` (per-endpoint records: per image / per megapixel; per-token models are "price unknown"; each estimate states its basis)
- [x] `vidgen validate`: unknown provider, missing `model`; schema lists the provider
- [x] Tests with mocked responses (success, error, retried rate limit, price lookup) (`tests/test_imagegen_openrouter.py`, fixtures from real public records; `tools/live_check_openrouter.py` for the coordinator)
- [x] Docs: CONFIG.md, README (key setup on Windows and Linux), AGENTS.md (choosing an image provider), third-party/terms notes

### Step 61b — Vector (SVG) generated images
- [x] Find out how OpenRouter's SVG/vectorization models are called (text prompt or input picture); if they only convert pictures, generate a PNG then vectorize it (2026-10-08: the SVG models are Recraft's `*-vector` — text prompt in, SVG out, one call, $0.08 / $0.30 per picture; no vectorise-only model listed, so no two-call pipeline; none has a ZDR endpoint)
- [x] `generate: {..., format: svg}` on the `image` scene, only with a model that returns SVG (validate says which) (`imagegen.svg_model`; validate: error without `provider: openrouter`, warning for a model not known to make SVG with the SVG models listed; dry run / run check the live record)
- [x] Stored as `assets/generated/<hash>.svg` + sidecar; format in the cache key (PNG keys unchanged; dry run, `--json` `format`, MCP through the same JSON)
- [x] Sanitise before loading: drop scripts / filters / embedded rasters, flatten unsupported gradients, cap the path count (clear warning, simplify option) (`vidgen/svgclean.py`: also foreignObject, masks / clip paths, text, animation, links, entities; 1500 shapes / 60 000 segments; `simplify` % of the area)
- [x] Loaded as vector shapes; `draw: true` (strokes then fill), `recolor: theme | none`, fit to region (`load_vector` / `VectorPicture`; also `.svg` files as `path`)
- [x] Layout dump / lint treat it as one picture (kind `vector`)
- [x] Tests: mocked SVG response, sanitiser, draw / recolor render test, path cap (`tests/test_vector_images.py`)
- [x] Docs: CONFIG.md, AGENTS.md (when SVG is worth it) (+ EXTENDING.md, DESIGN §65)
- [x] (from Step 61's live run) OpenRouter's data-policy 404 (account requires ZDR) → a clear error with the settings link and the image models that have a ZDR endpoint; CONFIG.md note; `tools/live_check_openrouter.py --zdr` and `--svg`

### Step 62 — OpenRouter TTS provider (one provider per video)
- [x] `voice: {provider: openrouter, model, voice, instructions, speed}`; `elevenlabs` stays the default; existing audio hashes stay valid (two ElevenLabs keys pinned + kphi3's committed hashes "ok"; keys of the provider not in use are ignored so a variant can switch)
- [x] One provider per video: named `voices:` may change `voice` / `instructions`, not `provider`; a variant may switch provider (own `audio/<variant>/`); any mix is a validate error (also other-provider keys in a named voice, e.g. `voices.ana.voice_id`; named voices may also change `speed` / `model`)
- [x] REST via the standard library, MP3 into the existing `audio/` cache; provider, model, voice, instructions, speed in each beat's hash (`POST /api/v1/audio/speech`, `response_format: mp3`; PCM-only models such as Gemini TTS converted with ffmpeg; app headers; ZDR data-policy 404 → the Step 61b message with the TTS models that have a ZDR endpoint)
- [x] No neighbouring-beat context, no word timestamps (captions use estimated timings; `voice.timestamps` with this provider warns), no `language_code`
- [x] `vidgen tts --dry-run` / `--json`: provider, model, voice, characters per beat and total, estimated cost where listed; MCP real runs still need `confirm_cost` (price per character = the highest of the model's providers, live public lookup; "price unknown" when audio is billed too or offline; a real run prints the cost OpenRouter reports via `/generation`)
- [x] Pronunciation, multiple voices, readback, lint speed and captions work with it (tested)
- [x] Not included: voice cloning from reference audio, multi-speaker input
- [x] Tests with mocked responses (MP3 stored, hash changes, provider-mix error, fallback warning) (`tests/test_tts_openrouter.py`, fixtures `tests/data/openrouter_tts.json` from the public endpoints; validate warnings from a bundled dated model/voice list; `tools/live_check_openrouter.py --tts [--zdr] [--yes]`)
- [x] Docs: CONFIG.md "Narration providers", README, AGENTS.md (choosing a voice provider, writing good `instructions`), an example variant (no audio committed) (`examples/minimal` variant `openrouter`; DESIGN §66, THIRD_PARTY_NOTICES)

### Step 63 — Review of Phase F
- [x] End to end with mocks (imagegen → render, tts → render), dry-run JSON over MCP, docs consistency, wheel build, full suite; the coordinator's live checks recorded in HANDOFF.md (`tests/test_phase_f_review.py`; live: ZDR 404 for Recraft / FLUX, Seedream 5.0 flash $0.018 as estimated, Kokoro and Gemini TTS MP3s fine; the TTS cost lookup now waits up to 15 s for OpenRouter's late records and says why when none came — to confirm live with `tools/live_check_openrouter.py --tts --zdr --yes`; key scrubbing hardened; `tts --json` `voice_id` null for OpenRouter)

---

## Phase G — Owner's reports from a real install

### Step 64 — Bug fixes: ffmpeg 7.1 transitions, Manim 0.22 test fake
- [x] Push, wipe and crossfade fail on Debian's ffmpeg 7.1.5 ("frame rate 1/0 is invalid") but work on 8.1: reproduce with a 7.1 build, fix the filter graph in `src/vidgen/render/ffmpeg.py` (`crossfade_graph` and the push/wipe paths) so it works on ffmpeg 6.1, 7.1 and 8.x; a test that runs each transition type; README states the supported ffmpeg versions (and a minimum, if one remains)
- [x] With Manim 0.22, 6 quick tests fail: Manim now passes `repeat=` to a function whose fake in `tests/test_overlays.py` (~line 77) only accepts `num_frames`; make the fake accept both (and any future keyword) so tests pass on Manim 0.21 and 0.22; check real renders on 0.22

### Step 65 — Local Kokoro TTS (optional extra)
- [x] `voice: {provider: kokoro, voice, speed, lang}` running Kokoro-82M (https://huggingface.co/hexgrad/Kokoro-82M) locally, free and offline after the first model download; installed with `pip install ".[kokoro]"`; clear error naming the extra when it is missing (`src/vidgen/tts/kokoro.py`; extra `kokoro>=0.9.4` for Python < 3.13 — kokoro 0.9.4 declares <3.13; on 3.13 the error prints a forced install that worked here; also `device: cpu|cuda|auto`; `lang` from the voice's first letter or the video's `language:`)
- [x] Same rules as the other providers: one provider per video, MP3 into `audio/`, provider/voice/speed/lang in each beat's hash, pronunciation applied, captions with estimated timings (or Kokoro's own word timings if it provides them), dry run shows "free (local)" (English word timings stored as `.align.json` for every beat; model + weights file in the hash, not the device; ElevenLabs / OpenRouter hashes pinned unchanged; MCP real `tts` without `confirm_cost` for Kokoro projects)
- [x] Voices and languages listed and validated from Kokoro's own voice list; model download location and size documented; CPU works (GPU optional) (`src/vidgen/data/kokoro/voices.json`, 54 voices dated 2026-10-09; validate warnings; model loaded once per run, shared across voices and languages; real run here ~0.7x real time on 2 CPU cores)
- [x] Tests mocked where the model is not installed; one real synthesis test, skipped unless the extra is installed (`tests/test_tts_kokoro.py`; the real test passed in a Python 3.12 venv with the extra)
- [x] Docs: README install (Windows and Linux, incl. any system package such as espeak-ng), CONFIG.md "Narration providers", AGENTS.md (a free local voice for agents' own projects), THIRD_PARTY_NOTICES (Kokoro's licence) (+ DESIGN §68, `examples/minimal` variant `kokoro`; espeak-ng comes bundled in `espeakng-loader`, system package only a fallback)

### Step 66 — Output folder
- [x] Deliverables (`<output>[_<variant>][_preview].mp4`, `.srt`, `_chapters.txt`, `_thumbnail.png` / `.jpg`) go to `<project>/output/` (created when missing); top-level `output_dir:` (relative to the project folder, or absolute; a variant may set its own) and `--output-dir DIR` on `render`, `thumbnail`, `export`, `slides` (relative to the current directory) override it, flag first; one property decides it (`Project.output_dir`); `build/` and `exports/` unchanged; no fallback to an MP4 in the project root; init template `.gitignore` gets `output/`; docs, guide and tests updated

---

## Phase H — Cartoons (characters, acting, stages)

Goal: an agent can write a cartoon in `video.yaml` (characters who talk, move and react, on an
image or drawn background) without drawing frames by hand. Order: characters and poses → lip
sync → stages → acting actions → motion primitives → agent tooling → audio and speed. Each step
follows `docs/CODING-AND-COMMUNICATION-GUIDE.md` (memory cap, targeted tests, cheap tests). Only
original characters: no step adds a known character, mascot or brand figure, nor a way to imitate
one.

### Step 67 — Character model (vector parts with pivots)
- [x] A character is a group of named vector parts (`head`, `eyes`, `brows`, `mouth`, `body`, `arm_left`, `arm_right`, optional `legs`, `accessory`), each with a pivot point and a draw order; one module (`vidgen/cartoon/character.py`), exposed through `vidgen.api` (+ `cartoon/cast.py`: the config-side lookups and checks, no manim; a basic figure is the only look until Step 68; DESIGN §69)
- [x] Parts can be rotated / swapped / scaled around their pivots without moving the rest; facing left or right is a mirror of the whole character
- [x] Top-level `characters:` in `video.yaml` (name, look, colours, `voice:` = a named voice from `voices:`), declared once and reused by any scene; validate: unknown character, unknown voice, duplicate names (a list, so duplicates are caught; unknown character via the `CharacterName` param type, since no built-in scene names characters yet)
- [x] Tests without rendering (part tree, pivots, mirroring, schema) and one tiny render test (`tests/test_cartoon_character.py`)

### Step 68 — Parametric character generator
- [x] `look:` parameters: body shape (round, tall, square, bean), head size, colours (skin / fur, clothes, outline), eye style, nose, hair or ears, accessories (glasses, hat, scarf, bag); seeds give variations; results are original shapes built from primitives (`cartoon/generator.py`; `colors` gains `hair`, `accessory`; DESIGN §69.1)
- [x] Colours default to theme tokens; outline width scales with the frame size (skin, clothes, hair, accessory are tokens; `outline` / `features` stay the fixed dark ink of Step 67, since no token is dark in every preset; strokes scale with the character's height, at least 1 px)
- [x] `vidgen character NAME --png` (one still) for a quick look (also prints the look and colours; `--facing`, `--variant`; no `--json`, Step 83's sheet is the agent tool)
- [x] Tests: every parameter value builds, the same parameters give the same shapes (`tests/test_cartoon_generator.py`)

### Step 69 — Imported SVG characters
- [x] `look: {svg: path/to/file.svg}`: an SVG (own art, or made with the SVG image models of Step 61b) split into parts by a naming convention (`id="mouth"`, `id="arm_left"`, `data-pivot="x y"`); sanitised with `svgclean` (`cartoon/svg_look.py`; shapes outside the named parts make the body; DESIGN §69.2)
- [x] Missing parts degrade gracefully (no arm → no `wave` gesture; validate warns which actions are unavailable); mouth shapes as named alternatives (`mouth_A`, `mouth_E`, …) when present (only `body` is required; `cast.ACTION_NEEDS` is the table later action steps consult)
- [x] Docs: the naming convention with a small example SVG in `examples/`; tests with that SVG (`examples/svg_character/assets/sprout.svg`, CONFIG.md "Characters from SVG files", `tests/test_cartoon_svg.py`)

### Step 70 — Poses and expressions
- [x] Named poses (`stand`, `pointing`, `waving`, `thinking`, `shrug`, `arms_crossed`, `sitting`) and expressions (`neutral`, `happy`, `sad`, `angry`, `surprised`, `worried`, `thinking`) as part angles / part shapes, in one table (`cartoon/poses.py`: `POSES` / `EXPRESSIONS`, part -> `PartPoseEntry`; shape choices fall back per character; generated brows gain `angry` / `sad`; DESIGN §69.3)
- [x] A transition between two poses or expressions eases part by part (not a cross-fade) (`PoseChange` animation in `cartoon/transition.py`, exported: each part eases about its pivot in its own window, body first)
- [x] Characters may define their own poses in YAML; validate lists the known names (`characters[].poses` / `.expressions`; validate checks their shapes and parts; unknown names raise with did-you-mean and the known names; `vidgen character` lists them; no scene / action names a pose yet, so validate has no pose reference to check until Steps 73 / 78)
- [x] Tests: every pose and expression builds on the generator and on the example SVG (`tests/test_cartoon_poses.py`)

### Step 71 — Lip sync (visemes)
- [x] Phonemes per beat: from Kokoro's G2P (misaki) when the provider is Kokoro, else from text (misaki / espeak-ng when installed, a letter-based fallback otherwise), timed with the word timings already stored (ElevenLabs timestamps, Kokoro `.align.json`, estimated timings otherwise) (`cartoon/visemes.py`; Kokoro's token phonemes kept as `KokoroProvider.last_phonemes`; misaki English only with spaCy's model installed; neither is installed here, both mocked)
- [x] Map phonemes to 6–9 standard mouth shapes (rest, A/I, E, O, U, M/B/P, F/V, L, W/Q) and store a per-beat viseme track (`.visemes.json` next to the audio, in the beat's hash) (9 visemes; the track stores the MP3's sha1 and the spoken text, like `.align.json`, and is in the scene fingerprint; `vidgen tts` writes it for videos with `characters:`; generated characters gain mouth shapes `A E O U M F L W`; DESIGN §69.4)
- [x] The speaking character's mouth follows the track; short shapes merged to avoid flicker (`Character.lip_sync(track)` updater / `stop_lip_sync` / `show_viseme`, `NarratedScene.beat_visemes(beat)`; no scene speaks until Steps 73 / 78; cues < 0.07 s merged, a short `M` lengthened)
- [x] Tests: the mapping table, the merge rule, a track from a stored alignment (no TTS call) (`tests/test_cartoon_visemes.py`)

### Step 72 — Automatic life: blinking and idle motion
- [~] Blinks at random but seeded intervals (2–6 s), never during a pose change; idle breathing (small body scale) and a slight head sway; `idle: false` per character or scene to turn them off (`cartoon/idle.py`, `Character.start_idle` / `stop_idle` / `end_blink`, a layer on top of the poses; the idle clock stops during a `PoseChange`, which ends a running blink; `characters[].idle`; per scene left to Step 73's `stage` scene, which does not exist yet; DESIGN §69.5)
- [x] Tests: blink times are deterministic for a seed; no blink overlaps a pose change (`blink_times` without manim, and the running character checked against it frame by frame: `tests/test_cartoon_idle.py`)

### Step 73 — `stage` scene type
- [x] A scene with a background (image file, generated image via `generate:`, or a theme colour / gradient), a ground line, named marks (`left`, `centre`, `right`, or x positions) and characters placed on them (`scenes/stage.py`, geometry in `cartoon/stage.py`; also `far_left` / `far_right` and own `marks`; each character starts in a `pose` / `expression` / `facing`; `idle: false` per scene; DESIGN §69.6)
- [x] Depth sorting: characters and props drawn by their `depth` (scaled smaller further back) (characters only: props are Step 75, and `stage_layout` sorts any item kind)
- [x] Layout dump / lint know the stage: characters and props are boxes with names (kind `character` named after it; `background` / `ground` named; lint `describe` says `character 'pip'`)
- [x] Tests: placement, depth order, a tiny render test with an image background (`tests/test_cartoon_stage.py`)

### Step 74 — Parallax layers and camera on a stage
- [x] `layers:` background / middle / foreground, each an image or shapes, with a parallax factor; camera `pan`, `zoom`, `follow: <character>` move the layers by their factors (`layer_transform` / `layer_half_extent` in `cartoon/stage.py`, no manim; shapes `rect ellipse triangle hills`; stage `width` (up to 4 frames) and `camera_at`; `pan` / `follow` are beat actions next to `zoom`, all three reuse `MoveCamera` and stay inside `NarratedScene.camera_bounds` (`camera.py`); `zoom` now comes back to the view before it; DESIGN §69.7)
- [x] Tests: layer offsets for a given camera move (no render), one tiny render (`tests/test_cartoon_parallax.py`)

### Step 75 — Props
- [x] A set of colourful filled props drawn from primitives (table, chair, tree, bush, house, door, lamp, sign, box, ball, cloud, sun, moon, rock, plant, laptop, cup), themed colours, placed by mark or position like characters (`cartoon/props.py`: `Prop`, `draw_prop`, `PROP_KINDS` / `PROP_HEIGHTS` / `PROP_COLORS` / `PROP_LIFTS`; stage `props:` through `stage_layout` with characters, `StageItem.lift` for sky props; action targets; layout kind `prop`; DESIGN §69.8)
- [x] Imported SVG props (sanitised) with the same placement (`props: [{svg: FILE}]` via `svg_prop` -> `load_vector` / `svgclean`; `recolor: theme`; validate checks the file)
- [x] Tests: each prop builds; a prop gallery still for the docs (`tests/test_cartoon_props.py`; `still.write_props_png` -> `docs/gallery/media/props.png`, 20 KB, shown in CONFIG.md "Props")

### Step 76 — Particles
- [x] `particles: rain | snow | sparkles | dust | confetti | smoke | bubbles` for a scene or a beat, with density, area and colour; seeded so renders are repeatable (`particles.py` pure model, `particle_field.py` `ParticleField`; a `particles` beat action on every scene type (`- particles: snow`, gone at the next beat, `until` / `keep: true`) and a `stage` `particles` param for the whole scene; drawn over the camera's view; no particle code existed to reuse; DESIGN §69.9)
- [x] Particle count capped for render speed; preview quality uses fewer (`MAX_PARTICLES` 300 per field, half at preview via `NarratedScene.is_preview`, set by the worker)
- [x] Tests: seeded positions, the cap (`tests/test_particles.py`: 19 without rendering, 2 tiny renders)

### Step 77 — Shared style for generated backgrounds
- [x] `cartoon_style:` (top level) appended to every `generate:` prompt of `stage` scenes (e.g. "flat colours, thick outlines, soft shadows"), part of the image cache key; a variant may change it (added to the style words, `Style: <style>; <cartoon style>`; scene types opt in with `NarratedScene.uses_cartoon_style`, read by `find_images` and `generated_picture`; other pictures keep their keys; stage layers take no `generate:`; DESIGN §69.10; `tests/test_cartoon_style.py`)
- [x] Docs: writing background prompts that leave room for characters (empty middle, ground visible) (CONFIG.md "Generated backgrounds (`cartoon_style`)", a guide bullet; also `docs/gallery/stage.md` regenerated with Step 74–76's params)

### Step 78 — Acting actions, part 1: speaking and looking
- [x] Beat actions `say` (mouth follows the visemes; optional speech bubble with the beat's text or a short version), `look_at: <character | mark | camera>`, `turn` (face left / right), `emote: <expression>`, `pose: <name>` (`scenes/acting.py`; the character is the target, the new state is `to:` (`- emote: kit` + `to: happy`), since the shorthand's value is the target; `look_at` also takes a prop or an x; bubbles from `callout_label` / `label_spot` with a tail; geometry in `cartoon/acting.py`; DESIGN §69.11)
- [x] The beat's `voice:` picks who speaks (via the character's voice); other characters can have `react:` (expression or pose) during that beat (`Stage.narrate`; a `say` in the beat picks the speakers instead; `react` is a beat action undone at the next beat; lip sync now timed by the scene's clock from the beat's start, `NarratedScene.beat_clock` / `speak`, and kept in step through a `PoseChange`, fixing Step 72's known lag; validate warns per action when a character lacks the parts it needs, `Action.character_needs` + `cast.ACTION_NEEDS`)
- [x] Tests: action schedules without rendering; validate (unknown character, `say` by a character with no voice) (`tests/test_cartoon_acting.py`: 12 without rendering, 1 tiny render)

### Step 79 — Acting actions, part 2: moving
- [x] `walk_to: <mark | x>` (walk cycle from leg / body bob, speed in units per second), `enter: left | right`, `exit: left | right`, `gesture: point | shrug | wave | nod | shake_head`, `jump` (`scenes/moving.py`; the `to:` convention: `- walk_to: pip` + `to: door`, `- enter: kit` + `side: left` (+ `to`, default its mark), `- exit: kit` + `to: right`, `- gesture: kit` + `to: wave`, `- jump: pip` + `height`; pure math in `cartoon/acting.py`, `Walk` / `Gesture` / `Jump` in `cartoon/transition.py`; a walk lasts distance / speed via the new `Action.run_time_for`; characters with an `enter` wait off stage; `follow` plays with a walk and catches up (`Action.alters_targets`); a speech bubble now follows its speaker; DESIGN §69.12)
- [x] Characters in a walk do not overlap others' marks at the end (lint warning otherwise) (lint rule `walk_overlap` on beat-end stills: the layout dump's `walked_in`, set by `walk_to` / `enter`)
- [x] Tests: walk duration from distance and speed, enter / exit end positions (`tests/test_cartoon_moving.py`: 15 without rendering, 1 tiny render)

### Step 80 — Animation principles built in
- [x] Anticipation before a move, squash and stretch on jumps and landings, overshoot and settle on stops, follow-through on arms / ears / hair; one `cartoon_motion: lively | calm | none` setting (per video, scene or character) (pure functions in `cartoon/motion.py` applied inside `PoseChange` / `Walk` / `Gesture` / `Jump`, no new animation class; squash is `Character.set_squash` about the feet; follow-through turns arms, head and accessory (a generated character's hair and ears are in its head) on walks and jumps through `follow_lag`, a first-order lag that Step 82's spring replaces; nearest setting wins: character, then stage param, then top level, default `lively`; walks and jumps gain wind-up / settle time; DESIGN §69.13)
- [x] Tests: the easing curves (values at fixed times), the setting turns each effect off (`tests/test_cartoon_motion.py`: 14 without rendering, 1 tiny render)

### Step 81 — Keyframes and motion paths in YAML
- [x] A small keyframe format for any character, prop or part: `keys: [{t: 0.0, x: .., y: .., rotate: .., scale: ..}, ...]` with `ease:`; `path:` along points or a curve (`move_along: [[x,y], ...]`, smooth) (beat actions `keyframes` (`- keyframes: kit.arm_left` + `keys`, `ease`) and `move_along` (`- move_along: pip` + `path`, `curve: smooth | straight`, `ease`, `speed`) in `scenes/keyframes_action.py`, the `to:` convention of Steps 78–79: the shorthand value is the target, so the points are the `path` option; parts are stage targets `<character>.<part>`; `ease` takes Manim's rate function names plus `lively` / `calm`; pure math in `cartoon/keyframes.py`, `KeyedMotion` in `cartoon/transition.py`; both reversible with `until`; DESIGN §69.14)
- [x] Times relative to the beat (seconds or fractions); validate checks order and ranges (`t` seconds from the action's start or `"40%"` of the beat's narration, all one way; order, shares ≤ 100 %, mark / x / y ranges per target kind, unknown parts, non-stage scenes)
- [x] Tests: interpolation values, path lengths (`tests/test_cartoon_keyframes.py`: 10 without rendering, 1 tiny render)

### Step 82 — Spring physics for secondary motion
- [x] A damped spring helper (stiffness, damping) for parts that should lag and wobble (antennae, ears, tails, hair, hanging signs); used by Step 80's follow-through (`Spring(stiffness, damping)` / `Spring.tuned(frequency_hz, damping_ratio)` in `cartoon/spring.py`, exported by `vidgen.api`: closed-form step response, `overshoot`, `settle_seconds`, and `follow(target, seconds)`, a pure function of time (frame-rate independent); `motion.follow_lag` now runs on `FOLLOW_SPRING` (2 Hz, ζ 0.5) instead of the first-order lag; `cartoon_motion: none` still gives no offset; no YAML for springs, since no tail / antenna parts exist; DESIGN §69.15)
- [x] Tests: settles within a time, no overshoot when critically damped (`tests/test_cartoon_spring.py`: 12 without rendering; `tests/test_cartoon_motion.py`'s follow-through test now checks the spring)

### Step 83 — Character sheets and mid-action storyboards
- [x] `vidgen character-sheet [NAME]`: every pose, expression and mouth shape of a character on one PNG (and over MCP) (`cartoon/still.py` `write_character_sheet`: poses whole, expressions and mouth shapes as head close-ups, 64-colour PNG, ~30 KB; `vidgen character-sheet [NAME] [PROJECT] [--all] [--variant] [--output] [--json]`, no NAME = every character; MCP tool `character_sheet` returns the sheets as pictures; DESIGN §69.16)
- [x] Storyboard stills for `stage` scenes include mid-action frames (half-way through a walk or gesture), not only the end of each beat (`NarratedScene.mid_still_actions`, `stage`: walk_to, enter, exit, gesture, jump, keyframes, move_along; the action runner asks `FrameCapture.add_mid_still` as each plays; `k` 0 + `mid` label, `<beat>-m<frame>.png`, labelled `½ walk_to pip` on the sheets; at most 3 per beat, 0.4 s from other stills; lint and slides skip them)
- [x] Tests: sheet grid size per character; storyboard picks mid-action times (`tests/test_cartoon_sheet.py`: 7 without rendering, 2 tiny renders; `mid_action_frame(s)` and the capture in `tests/test_frames.py`; the MCP tool in `tests/test_mcp.py`)

### Step 84 — Cartoon lint rules
- [x] Character partly off-stage (unless entering / exiting); speech bubble covering a face or another bubble; characters overlapping at rest; speaker facing away from the listener (the character it last looked at or the nearest one); mouth moving while no voice speaks; a character speaking with no line of sight to the camera (back turned) (still rules `off_stage`, `character_overlap`, `bubble_overlap`, `facing_away`, `hidden_speaker`, `mouth_without_voice` in `lint/cartoon_rules.py`, with `walk_overlap` moved there; flat characters never turn their back, so `hidden_speaker` is a speaker whose face something drawn in front hides; `mouth_without_voice` is a lip sync still showing speech after the beat's narration (the pad); the layout dump's `character` objects gain `facing`, `speaking`, `face`, `viseme`, `looked_at`, `passage`, bubble objects `bubble`, beat-end frames `narrating`; `off_frame` leaves characters to `off_stage`; mid-action stills stay skipped; DESIGN §69.17)
- [x] Each rule in the lint rule list with a fix hint, `lint_ignore` works for them (CONFIG.md rule table and defaults, guide troubleshooting table, each message ends with the fix; `lint_ignore`'s `object` also matches a bubble's speaker)
- [x] Tests: one passing and one failing case per rule (`tests/test_cartoon_lint.py`: synthetic layout dumps, `lint_ignore` through `lint_project` on a faked render with a skipped mid still, 8 without rendering, 1 tiny render checking the dump keys and no findings on a plain dialogue)

### Step 85 — Guide: cartoon storytelling in AGENTS.md
- [x] A section on cartoons for agents: when to use one, designing original characters, staging (marks, depth, leaving room), shot variety (wide / medium / close-up via camera), reaction shots, comic timing (pauses, beats of silence), short lines; a small example project in `examples/cartoon/` (no audio committed) (guide topic `cartoons`, aliases `cartoon characters character stage dialogue acting`; the dialogue bullet of `actions` and the cartoon-background bullet of `outputs` folded into it, pointers left; pauses are `narration.pad` + `at` near the line's end, since a beat has no pause key; `examples/cartoon` "The Box Kite": 2 stages, 12 beats, Kokoro voices, validate + `lint --fail-on warning` clean on the word-count preview; DESIGN §69.18)
- [x] Copied to root `AGENTS.md` (test_guide checks it)

### Step 86 — Foley and music stings
- [x] Sound effects tied to actions (footsteps on `walk_to`, a whoosh on `enter` / `exit`, a pop on `emote: surprised`, a boing on `jump`) from the existing sfx library, on by default for `stage` scenes, off with `foley: false` (pure schedule `cartoon/foley.py` `foley_cues(PlayedAction)`, timed from the run as played: `ActionRunner._run` calls the new `NarratedScene.action_foley` hook, `Stage` records the cues as sfx events; whoosh / swoosh / pop reused, `footstep` and `boing` added as built-in generators; footsteps also on `enter` / `exit`, a `react` to `surprised` pops too; top-level `foley` and stage param `foley`; DESIGN §69.19)
- [x] Short music stings on a beat (`sting: reveal | comic | sad`), mixed under narration with the existing ducking (`sting_reveal` / `sting_comic` / `sting_sad` built-in generators; `{kind, at: start | end, gain}`; recorded by `NarratedScene.narrate` as `SfxEvent(duck=True)` on the SFX track, scaled in `sfx.write_track` by `mix.sting_ducking` = `duck_curve(speech_spans, STING_DUCK)`: 6 dB, 0.15 / 0.3 s, no hold)
- [x] Tests: the action → sound schedule; mixing uses the existing path (`tests/test_cartoon_foley.py`: 6 without rendering, 1 tiny render)

### Step 87 — Render speed for cartoons
- [x] Static background layers rendered once per scene and reused as an image; character part drawings cached by look and part (only transforms change per frame) (Manim already kept a plain stage's backdrop in its static image per `play`; a stage with parallax layers now does too unless the camera follows; per-part point arrays transformed per frame; generated looks' parts cached by `look_key`; no raster cache: it would change the drawing; DESIGN §69.20)
- [x] Measure before and after on `examples/cartoon` at preview quality; record numbers in HANDOFF.md (`hill` −8 %, `yard` −3 %, `character-sheet` −23 %; end to end and at the final format within noise)
- [x] Tests: the cache key changes when the look changes, not when the pose changes (`tests/test_cartoon_speed.py`; the static image in `tests/test_cartoon_parallax.py`)

### Step 88 — Review of Phase H
- [x] End to end with mocks: the cartoon example through validate, lint, storyboard, character sheet and a preview render; docs consistency (CONFIG.md, DESIGN.md, AGENTS.md); targeted tests for Phase H, then the full suite only if the owner asks (CLI and MCP on the example; `tests/test_phase_h_review.py`; the stage JSON Schema takes bare names again; real Kokoro narration and a 1280x720 render checked by eye; the `yard` difference traced to x264 at non-mod-16 widths; Phase H gaps moved to the Backlog; full suite not run: not asked)
- [x] Fixes after the review (owner): props and characters at a depth stood above the ground band (the band now reaches up to the deepest thing on the ground, `ground_top`); a speaking character that moved left a copy of its mouth behind (a `Character` keeps one live copy per shape, its family never changes); review video re-rendered as `cartoon_review_v2.mp4` (DESIGN §69.22)

---

## Phase I — Livelier cartoons (directing, screenplays, props, shots, mood)

Goal: cartoons that look directed and alive with less writing. Same rules as Phase H (guide,
memory cap, targeted tests, original characters only). Each step updates the guide's
`cartoons` topic where authors see the change.

### Step 89 — Automatic directing, part 1: looks and reactions
- [x] `auto_direct: true | false | {looks, reactions, gestures, closeups}` (video, stage scene, beat; nearest wins; off by default) (`config.AutoDirect`, `directing_kinds`; a kind not given is on; `gestures` / `closeups` accepted, planned in Step 90; DESIGN §69.23)
- [x] Looks: listeners turn and look at whoever speaks (the beat's voice / `say`), the speaker at the one it last addressed; explicit actions in a beat always win (addressee: the last other speaker, else the one it addressed before, else the next speaker, else the only other character; a character any written action of the beat targets gets nothing automatic, except `say` / `zoom` / `pan` / `follow` / `highlight` / `dim` / `callout`; characters off stage before their `enter` / after their `exit` are left out; no look without a head)
- [x] Reactions in the pad after a line: a listener's expression chosen from the line's punctuation and a small word list (`!` surprised / happy, `?` thinking, negations worried), seeded and never the same twice in a row (`react` at `at: 0.95`; `?` thinking / surprised, negation worried / sad, `!` surprised / happy, in that order; seeded by scene, beat and character names; English word list)
- [x] The added actions are visible: `vidgen storyboard` / `--json` mark them as auto, and `vidgen direct --print` writes them out as YAML an author can paste and edit (an `auto:` line under the beat's narration, frames' `auto`; `ActionConfig.auto`, log lines `look_at kit (auto)`; `vidgen direct [--print] [--scene] [--json]`; no MCP tool)
- [x] Tests: the planner is a pure function from beats to actions (no render) (`tests/test_cartoon_directing.py`: 14 without rendering, 2 tiny renders)

### Step 90 — Automatic directing, part 2: gestures and close-ups
- [x] Gestures on stressed words (from word timings: longest / capitalised / emphasised `*word*` words), at most one per line, chosen from the character's available parts (`_plan_gestures`, `stressed_word`, `gesture_choices` in `cartoon/directing.py`; word times by `beat_word_times`; the word picks the gesture (negation shake_head, yes nod, hello wave, this / there / you point), else the line (question shrug), else point / nod / shrug seeded; the longest word (6+ letters) only when the speaker did not gesture in its previous line; a line too short for the gesture gets none; DESIGN §69.24; the asterisks of `*word*` are taken out of the beat's text since Step 91: `BeatConfig` keeps `marked_text` for the planner, TTS / captions / bubbles / readback / lint get the plain text, unmarked beats keep their audio hash)
- [x] Close-ups: an occasional zoom on the speaker for a short punchy line after a long one, never two in a row, never during a walk or pan (`_plan_closeups`: ≤ 5 words after ≥ 8, `zoom` scale 2, 0.5 s moves when both fit in 80 % of the line, else a cut (0.03 s) so the runner never rushes it; not with a written walk / enter / exit / move_along / keyframes / pan / follow / zoom, a bubble, an automatic gesture of the speaker, nor while following)
- [x] Respect lint: no auto action may create a `facing_away`, `bubble_overlap` or `off_stage` warning (checked in the planner) (`StageFrame` from `stage_layout` via `stage_frame`; `_still` predicts the beat's still as a lint `StillContext` and `still_findings` runs the registered `off_stage` / `facing_away` rules with and without each look, arm gesture and close-up; `bubble_overlap`: automatic actions draw no bubble, no close-up in a bubble beat; without geometry no arm gestures or close-ups; MCP tool `direct` added)
- [x] Tests: pure planner tests; examples/cartoon renders with `auto_direct: true` and lints clean (`tests/test_cartoon_directing.py`: 14 new without rendering + 1 tiny render that lints clean; scratch copies of examples/cartoon (with `auto_direct: true`, and one with only its moves kept) rendered at preview and `vidgen lint --fail-on warning` clean; committed example unchanged)

### Step 91 — Screenplay format
- [x] `vidgen screenplay FILE.md [--out DIR]` turns a screenplay into a stage project: `# Scene: yard` headings (with an optional `set:` line for background / props / marks), `DOT: line`, `MOSS (doubtful): line` (the bracket becomes an expression; known pose names become poses), narrator lines as plain paragraphs, `[Dot walks to the box]` stage directions mapped to actions where a small grammar matches (walk to / enter / exit / jump / look at / point at), others kept as TODO comments (`screenplay.py`; also front matter, `set: characters`, wave / nod / shrug / shake head, directions inside a line, `--force`, `--json`; actions timed one after another from estimated lengths; writer shared with `vidgen plan`: `plan_yaml.commented_yaml` / `write_project`; DESIGN §69.25)
- [x] Characters not declared get generator looks that differ clearly (shape, colours, accessories) and voices assigned from the provider's list (different gender / accent where possible) (six `LOOKS`; Kokoro by accent and gender, the narrator's kind last; OpenRouter: the model's listed voices; ElevenLabs: no list, a TODO asks for voice_ids)
- [x] The output validates; `auto_direct: true` on by default in the generated project (the command runs `validate_all`; the sample also lints clean at preview)
- [x] Also as an MCP tool; the guide shows the format (MCP `screenplay`; guide "From a screenplay" in `cartoons`; docs/CONFIG.md "Cartoons from a screenplay")
- [x] Tests: parser (no render), round trip on a sample screenplay in `examples/` (`tests/test_screenplay.py`: 15, no render; `examples/screenplay/humming_box.md`; MCP test)

### Step 92 — Bending arms and legs
- [x] Arms and legs in two segments (upper / lower, elbow / knee pivots) for generated characters, with a simple two-bone solver (`reach(hand, point)`, `plant(foot, point)`) (`cartoon/limbs.py`; `arm_left` = upper arm + `arm_left_lower`; legs `leg_left` / `leg_right` + `_lower` replace a generated character's one-piece `legs`; `Character.reach` / `plant` / `hand_point` / `foot_point` / `sole_height` / `grounded`; DESIGN §69.26)
- [x] Imported SVG: optional `arm_left_lower` / `leg_left_lower` ids; single-piece limbs keep working (also `leg_left` / `leg_right`, not with `legs`; a one-piece limb keeps a pose for its lower segment and shows the bend folded: half the angle, shortened to the chord, so `reach` works on it too)
- [x] Existing poses, gestures and the walk updated to bend (natural elbows, knee bend in the walk cycle); sheets and earlier tests still pass (update expected values with reasons in HANDOFF) (upper + half the elbow = the old one-piece angle; legs swing one by one, the walk keeps a sole on the ground instead of a fixed bob; lower segments share their limb's pose-change window; no knees in `jump`)
- [x] Tests: solver reach / out-of-reach / elbow side, pose tables (`tests/test_cartoon_limbs.py`: 24, no render)

### Step 93 — Interacting with props
- [x] Beat actions `pick_up: <character>, to: <prop>`, `hold`, `put_down` (at a mark), `give` (to another character), `throw` (to a mark, arc with spin, landing sound) (`scenes/handling.py`, pure parts in `cartoon/holding.py`; `hold` = in the hand from now on without picking up; `hand`, `prop`, `spin`, `height` options; landing `thud` via `PlayedAction.lands`; DESIGN §69.27)
- [x] A held prop follows the hand (it becomes attached to the character, scaled to fit) and is drawn at the right depth; walking with it works (attached by an updater at `hand_point`, not added to the `Character` (§69.22); drawn right after its holder; at most 0.4 holder heights while held; arm bent by `reached_parts`; layout dump `holding` / `held_by` / `hand`; the planner adds no arm gesture with a holding hand)
- [x] Validate: unknown prop, prop too far without a walk (suggest `walk_to` first), giving to a character who is not adjacent (new hook `NarratedScene.action_sequence_problems`; the stage replays its actions with `holding_problems`; also a prop held by another, a full hand, nothing held, a keyed move of a held prop)
- [x] Tests: attach / detach state machine, positions (no render), one tiny render (`tests/test_cartoon_holding.py`: 9 without rendering, 1 render)

### Step 94 — Sitting and leaning
- [x] `sit_on: <character>, to: <prop>` (chair, rock, box, any prop with a seat line), `stand_up`, `lean_on` (tree, door, sign); built-in props get seat / lean points; SVG props may give them (`data-seat`) (`scenes/sitting.py`, pure parts in `cartoon/seating.py`; also `lamp` / `house` to lean on; SVG `data-seat="x y"` / `data-lean="left right"` in viewBox coordinates; hips and knees bent with the Step 92 solver: `Character.seated` / `leaning` / `planted`, played by `BodyMove`; validate replays it with the props in hands (seat taken, too far, walk while seated); a seated or leaning character keeps its facing (looks turn the head, the planner adds no look behind it); layout dump `sitting_on` / `leaning_on`; DESIGN §69.28)
- [x] Also Step 93's gap: `pick_up` / `put_down` crouch for a low prop (knees bend, body lowers and bends forward, feet kept: `Character.lowered`, `crouch_drop`; one-piece SVG legs shorten)
- [x] Tests: seat points per prop, character feet / hips position when seated (`tests/test_cartoon_seating.py`: 12 without rendering, 1 render; stills checked by eye on a generated look and sprout)

### Step 95 — Shots within a scene
- [x] Beat key `shot: wide | two_shot | over_shoulder <character> | closeup <character> | medium <character>` cuts (hard cut, no move) the camera to a framing computed from the characters' positions; `shot: {..., move: true}` eases instead (`cartoon/shots.py` `frame_shot` / `shot_figures`, no manim; `config.ShotConfig` `{kind, of, move, run_time}` or words, `two_shot` / `over_shoulder` may name a second character, defaults filled in; the key becomes a `shot` action (`scenes/shot_action.py`) that `actions.beat_action_list` puts first in its beat; it holds for the beat and the next beat without a shot cuts (or eases) back to the view before the shots; `pan` / `follow` end a shot; layers, particles and bubbles follow the shot's view; DESIGN §69.29)
- [x] Over-the-shoulder shows the near character large, partly out of frame, at the side (lint `off_stage` allows it in that shot) (the near character's middle on the frame's edge, the subject at 0.66 of the width; both magnified, flat characters get no depth change; layout dump frames get `shot: {kind, subjects, near}`; `off_stage` in a shot checks only the characters it frames: their face in medium / over_shoulder / closeup, their box in two_shot)
- [x] `auto_direct` may pick shots (part of Step 90's close-ups switches to shots) (the close-up that was a 0.03 s zoom cut is now `shot: closeup` of the speaker, checked on its predicted still; the eased 0.5 s zoom stays; written shots are where the planner's checks look; `vidgen direct --print` writes it as the beat's `shot:` line)
- [x] Tests: framing maths (no render), lint exceptions (`tests/test_cartoon_shots.py`: 13 without rendering, 1 tiny render; scratch copies of examples/cartoon with shots and with `auto_direct` checked by eye, lint clean)

### Step 96 — Vertical cartoons follow the speaker
- [x] In 9:16 (and any format narrower than the stage), the camera keeps the speaker in frame by default (`reframe: speaker | none`), easing between speakers, holding during short replies (`cartoon/reframe.py` `reframe_path`, pure; `reframe` top level and stage param, default `speaker` when the characters do not fit in one view; a reframing stage in a frame narrower than 16:9 is laid out as wide as the 16:9 one and cropped; moves are automatic `pan`s (1.0 s ease, `cut: true` in the first beat and for a speech bubble); a line under 1.5 s holds; written pan / follow / zoom / shot win; DESIGN §69.30)
- [x] Storyboard / lint check the 9:16 variant of examples/cartoon (scratch copy: storyboard right by eye; lint 1 warning, `off_stage` in hill_count from the written `follow`, also without this step, so the variant is not added to the committed example)
- [x] Tests: the reframe path from a beat list (no render) (`tests/test_cartoon_reframe.py`: 11, no render)

### Step 97 — Lighting and mood
- [x] Stage `light: day | morning | sunset | night | indoor` (or `{tint, strength}`): a colour grade over background, layers, props and characters, keeping theme contrast for text and bubbles; night adds a few stars; `light:` as a beat action to change it over time (fade) (pure maths in `cartoon/lighting.py`: multiply + a warm glow for morning / sunset; drawn graded by `cartoon/shading.py` `StageLight`, which wraps the camera's colour and picture calls for mobjects marked lit, so bubbles, callouts, particles and text are never graded; `- light: night` is a non-animating action (`scenes/light_action.py`) whose `run_time` is the fade; everything is redrawn only while a fade runs; stars from the sparkles' seeded stream, static, colour backgrounds only; DESIGN §69.31)
- [x] Soft shadows under characters and props on the ground (ellipse, depth-scaled, off with `shadows: false`) (three soft rings at the caster's ground line, shrinking and fading as it jumps or flies, none under a held or hanging prop; props that cannot move stay in the static image)
- [x] Tests: grade maths, contrast kept for bubble text (lint `contrast` still passes) (`tests/test_cartoon_lighting.py`: 6 without rendering, 2 tiny renders)

### Step 98 — Wind
- [x] Stage `wind: 0..1` (and as a beat action): trees and bushes sway, scarves / hair / ears / hats trail (the Step 82 spring), particles drift with it; gusts as a seeded noise (pure maths in `cartoon/wind.py`: signed level -1..1 or `calm` / `breeze` / `windy` / `gale`, `gust` = two-octave value noise from splitmix64, fades with the light's `fade_at`; trees, bushes, plants, signs and lamps bend about their base (`bent_points`), not when an action moves, holds, sits or leans on them; hair / ears / scarf end / hat are members marked inside the generated head / body / accessory parts and turned by `Character.set_wind` on `TRAIL_SPRING`, so no new parts; SVG characters and props do not move; `- wind: gale` is non-animating like `light`, its run_time the fade; swaying props leave Manim's static image only while the wind may move them: examples/cartoon +7–13 % render time at a gale; DESIGN §69.32)
- [x] Tests: sway angles from the seed, `wind: 0` changes nothing (`tests/test_cartoon_wind.py`: 11 without rendering, 2 tiny renders, one comparing frame hashes of `wind: 0` + `- wind: calm` with no wind; examples/cartoon with `wind: 0` rendered at 160x90 gives HEAD's frame hashes)

### Step 99 — Non-speech voice sounds
- [x] Inline markers in a line: `[gasp]`, `[hmm]`, `[laugh]`, `[sigh]`, `[giggle]`, `[groan]`: voiced through the TTS provider where it can (e.g. spoken "hmm", "ha ha") or a built-in generated sound otherwise, with matching mouth shapes and an expression (laugh → happy, gasp → surprised) unless the beat sets one
- [x] Captions and readback skip or bracket the markers; pronunciation rules unaffected
- [x] Tests: marker parsing, viseme track around a marker, caption text

### Step 100 — Overlapping speech and interruptions
- [x] Beat `overlap: 0.4` (seconds the beat starts before the previous one ends) and `interrupt: true` (cuts the previous line's audio with a short fade at that point, mouth stops); both characters' mouths follow their own tracks while overlapping (`vidgen/overlap.py`, pure: `beat_windows` from the previous line's speech end (MP3 trailing silence cut off), whole frames, no pad between; `interrupt` alone starts 0.5 s before the end, 0.05 s fade; only on beats after a scene's first (config error), `interrupt` with `overlap: 0` refused, same-voice overlap a validate warning; `NarratedScene.beat_window` and `VideoPlan` share it; the earlier speaker's lip sync (and `say`) lingers until its line ends via `NarratedScene.end_lip_sync`; an interrupted track is `VisemeTrack.until(cut)`; DESIGN §69.34)
- [x] Mixing keeps both voices audible (small gain dip), captions show both lines; lint warns when an overlap hides a whole word (earlier voice −3 dB over 0.1 s from where the later one starts, `VoiceShape` / `shape_voice` applied to the decoded WAV before Manim adds it; `captions` overlay stacks both lines on one plate, one line each, earlier on top, karaoke highlights a word in each; SRT: one-line overlapping cues; new lint rule `talked_over`; `animation_overrun` measures the window; no listener reaction after a line the next one overlaps)
- [x] Tests: timeline maths, mix plan, caption layout (no render) (`tests/test_overlap.py`: 14 without rendering, 2 tiny renders; `tests/test_overlap_pinned.py`: plan and rendered timings pinned from HEAD e312f91, every WAV Manim gets equal to the plain decode; also the Step 99 finding: the wind's updater removes itself once nothing can move, tested)

### Step 101 — Reusable casts and sets
- [x] `include: [cast.yaml, sets.yaml]` (paths relative to the project, or a shared folder): `characters:`, `voices:` and named `sets:` (background, layers, props, marks, light) that a stage uses with `set: <name>` and may override (`vidgen/includes.py`; paths relative to the including file, nested includes, a file reached twice merged once; characters merge by name; scene key `set:`; the scene's params win: one backdrop choice, marks merge, characters / props / layers / particles add to the set's, a named entry changes the set's entry, `[]` clears; DESIGN §69.35)
- [x] Validate reports which file a problem came from; fingerprints include the included files; `vidgen screenplay --cast cast.yaml` reuses a cast (`Problem.file`, `(in FILE)` in the line, a set's value at `sets.NAME...`; no YAML line numbers (the loader does not keep them); missing / circular includes name the chain; TTS hashes and imagegen keys follow the merged config; `--cast` also in the MCP `screenplay` tool, `set: NAME` lines use the cast's sets)
- [x] An `examples/cartoon_series/` with a shared cast and two short episodes (no audio committed) (both validate and lint clean at preview)
- [x] Tests: merge rules, overrides, error locations (`tests/test_includes.py`: 24, no render)

### Step 102 — Review of Phase I
- [x] End to end: the screenplay example → project → validate, lint, storyboard, sheets, a preview render; examples/cartoon with `auto_direct`; real Kokoro narration on one example rendered at 720p and checked by eye; docs consistency; Phase I gaps moved to the Backlog; full suite only if the owner asks (CLI and MCP on the screenplay sample, examples/cartoon with `auto_direct: true` and both series episodes, all lint clean; `tests/test_phase_i_review.py`; fixed: captions on an `auto_direct` stage crashed, seats above the characters' hips (hips now on the seat line, lower chair / box / rock), stars beside heads, `vidgen mcp` confinement of `svg`, Kokoro `.pt` voices and a cast's includes, unused shared-cast voices warned; showcase with real Kokoro at 1280x720 checked by eye; Whisper check skipped by the owner; 16 Backlog lines; full suite not run: not asked)
- [x] Owner's follow-up on the showcase: generated voices did not suit the looks (Fen, bun and scarf, had a male voice; Bram a female one) and an `interrupt` without `overlap` cut the whole word "normal" (looks carry a voice kind, `FEN (she):` / front matter `voice_kind:` state one, the voice is chosen from that kind; an interrupt without `overlap` starts 70% into the last word from the stored word times, else 0.2 s before the speech end; `talked_over` reports words an interrupt cuts; showcase v2 re-voiced and rendered)

---

## Phase J — "Rain Check" (a weather cartoon example)

Goal: a ~70 s original cartoon example, `examples/cartoon-rain-check/` (a picnic, a confident
forecast, wind, rain, night), and the few things it needs. Same rules as Phases H and I.

### Step 103 — Props: basket, umbrella, napkin
- [x] Built-in props `basket`, `umbrella` (closed and open shapes; `open: true` or an action to open it; held overhead when open) and `napkin` (small, light), drawn from primitives in theme colours like the other 17; prop gallery still updated (`PROP_SHAPES`, shapes swapped by points through an anchor, family unchanged; beat actions `open` / `close` on the prop; held open: hand at 0.6 heights, 0.85 heights tall, drawn behind its holder; grips `PROP_GRIPS`: a basket by its handle, an open umbrella by its shaft; `props.png` shows the open umbrella too; DESIGN §69.37)
- [x] They work with pick_up / hold / give / put_down; sheets and docs list them (also throw; the gallery still, CONFIG.md, the guide, `docs/gallery/stage.md`; layout dump `shape`; shadow width per shape)
- [x] Tests: each builds, umbrella open / closed, held positions (`tests/test_cartoon_props.py` +3, `tests/test_cartoon_holding.py` +5 without rendering, +1 tiny render)

### Step 104 — Visible wind and props that blow away
- [x] Wind clearly visible at `windy` and above: stronger sway, leaves / dust streaks drifting, scarves and hair trailing further (Backlog: "wind barely visible") (`felt_force` = force × (1 + 2 |force|) for sway and trails, larger `SWAYS`, soft trail limit 80°; mean tree lean 2.1° → 6.4° windy, 3.6° → 14.1° gale, scarf end 12.5° → 23° / 20.9° → 46°; particle kinds `leaves` (tumbling) and `streaks` (wind lines, seen only above a breeze), added by the author, not automatic; stills checked by eye at breeze / windy / gale; DESIGN §69.38)
- [x] A light prop can blow away: `blow_away: <prop>` (tumbles across and off stage along a seeded gusty path, or `to:` a mark); a held prop can be blown out of a hand (pure `blown_point` / `gusty_progress`, played by `PropMove(path=)`; napkin, umbrella, ball, cup, basket, box, SVG props; `Holdings.drop`, the arm back down, layout dump and validate agree; validate: too heavy, calm wind without `to`, a prop blown off stage used later; the open-umbrella tug / flip (optional) not done)
- [x] Tests: seeded paths, wind 0 still changes nothing (`tests/test_cartoon_wind.py`: +6 without rendering, +1 tiny render; the Step 98 frame-hash test passes; `examples/cartoon` with `wind: 0` at 160x90 gives HEAD 837eb8b's frame hashes)

### Step 105 — Rain on the ground
- [ ] Rain stops at the ground line (depth-aware) with small splashes and, optionally, puddles that grow; rain does not fall through an open umbrella or a tree canopy held / stood under (simple shelter boxes)
- [ ] A `rain` sound bed under the scene while it rains (generated, ducked like music), on with `foley`
- [ ] Tests: drop end heights, shelter boxes, splash positions seeded

### Step 106 — The "Rain Check" example
- [ ] An original screenplay `examples/cartoon-rain-check/rain_check.md` and the hand-edited project `video.yaml` beside it (no audio committed), four beats of story: sunny meadow and the forecast; the picnic and the wind; the rain and the run to the tree (overlap, interrupt); night, stars, soggy sandwiches, a comic sting; background music
- [ ] Validates and lints clean at preview; rendered at 1280x720 with real Kokoro narration (not committed) and checked by eye and ear proxies (levels, stills); README example list

---

## Backlog (after Step 60)

Not done in the roadmap; each is one line, with where it came from. Bugs first, then quality,
then nice-to-have.

Bugs / correctness
- [ ] MCP: large documents (a long video's `lint` / `storyboard` JSON, `schema full=true`) are not trimmed and can exceed a client's tool-output limit (Step 59) — page or summarise them
- [ ] MCP on Windows: process-tree kill on cancel is untested; no session with a real client (Claude Desktop / Code) was possible here (Step 59)
- [ ] `equation_derivation`: a `highlight` colour on a step is not carried into its dimmed copy; `code`'s own highlight steps reset opacities a `dim` action set (Step 37)
- [ ] Not run on real Windows / macOS: font registration, MiKTeX's install prompts, long paths (Step 7 onwards)
- [ ] Renders are not byte-reproducible at a width that is not a multiple of 16 (the 854x480 preview): Manim's libx264 encode (via PyAV) of identical frames varies between runs in fast-moving shots; compare frames before encoding or use mod-16 sizes (Step 88, found in Step 87)
- [ ] Kokoro `vidgen tts` needs more than the 1500 MB cap (killed after three beats twice; finished under 2500 MB, peak ~2.2 GB): find out whether memory grows per beat or per voice (Step 88)
- [ ] A shape swap resets that part's style: a dimmed or faded character's speaking mouth or blinking eyes show at full opacity (Steps 67, 78)
- [ ] A walk's run time is planned when its batch starts: two walks of one character due on the same frame both start from its position then; `enter` on a character already on screen first jumps it to the edge (Step 79)
- [ ] An SVG character or SVG prop outside `assets/` is not in the scene fingerprint; `use` elements pointing into a part are not followed when splitting an SVG character (Steps 69, 75)
- [ ] `VideoPlan` and a rendered scene can disagree by a frame on a beat's start when `d + pad` lands on half a frame (the scene rounds the wait left after its animations) (Step 100)
- [ ] `vidgen mcp`: files found by scanning a folder (`assets/sfx/`, `assets/icons/`, `audio/`) are not confined to the root; a link there can point outside (Step 102)
- [ ] Lint `facing_away` takes the nearest character as the listener, so a speaker turned to the one it addresses farther away is reported (seen on a seated speaker in the Step 102 showcase draft) (Step 102)

Quality (what an agent's video looks like)
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
- [ ] Wind: not relative to a walking character; held and SVG props (except `blow_away`, Step 104), layers, pictures and SVG characters do not move; no top-level `wind`; long hair turns as one piece instead of bending; an open umbrella does not tug its holder or flip (Steps 98, 104)
- [ ] Voice sounds: one face per beat (the first sound's); a `[gasp]`'s surprised face also plays the foley `pop`; a beat of sounds only is impossible; the face of a sound at a line's start waits for the speaker's earlier actions (a `[laugh]` while entering shows after the walk) (Steps 99, 102)
- [ ] Overlaps: no per-beat dip / fade settings; an interrupted line's caption shows its whole text until the cut; no overlap across scenes; never tried with ElevenLabs audio (Step 100); Kokoro's stored times stretch a line's last word over its quiet tail ("normal?" 3.01–4.78 s, heard 3.0–3.62 s), so an interrupt without `overlap` starts ~0.6 s after the word is heard (Step 102 follow-up)
- [ ] Voice kinds: only Kokoro voices are chosen by kind (OpenRouter models list no gender; ElevenLabs has no list here, the `# TODO:` names the kinds); declared characters' looks are not read for a kind (Step 102 follow-up)
- [ ] Includes: unused sets are not validated on their own; no set based on another set (Step 101)
- [ ] Phase I narration was not transcribed (Whisper check skipped in Step 102); Kokoro still reaches the 2500 MB cap during `vidgen tts` (page cache counted) and reads above 3.5 words/s at `speed: 0.85` (Step 102)
- [ ] Acting: a long beat makes a large speech bubble; a bubble following its speaker is not clamped to the view; `look_at` is reset by a later `pose` / `emote` (Steps 78–79)
- [ ] Motion: no follow-through on pose changes, gestures or keyed moves; no squash on footfalls; an `enter`'s wind-up happens off stage; a facing change flips at half; no facing or rotation along a `move_along` path, no `depth` / opacity keys; a lifted character walks in the air (Steps 80–81)
- [ ] Mid-action stills only for walks, gestures, jumps and keyed moves (not `pose`, `emote`, `turn`, `look_at` or camera moves); the character sheet shows no left-facing view, blink or gesture (Step 83)
- [ ] Foley: no panning by where the character stands, no depth / speed / ground variation, no landing sound, gestures and keyed moves silent; not listened to by a person (Step 86)

Nice-to-have / performance
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
