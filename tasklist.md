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
- [x] PDF deck from the same frames, optional notes pages (use `vidgen.deck.deck_frames`: slides, notes, chapters, alt texts) — `vidgen slides --format pdf [--notes] [--title-page] [--paper a4|letter]`, optional extra `vidgen[pdf]` (fpdf2)

### Step 54 — Readback check (speech-to-text)
- [x] STT provider seam; optional `faster-whisper` extra; mocked in tests (`vidgen.stt`: `stt: {provider: faster_whisper | elevenlabs, model, language, device}`, `vidgen[stt]`; ElevenLabs Speech to Text provider too; transcripts cached in `build/readback/` by MP3 content + settings; no real run here: Hugging Face model downloads were refused by the build environment's proxy — see HANDOFF)
- [x] Report per beat: word error rate and differing words (catches mispronunciations) (`vidgen readback [--beat] [--max-wer] [--force] [--json]`: spoken text (pronunciation applied) vs transcript after a normaliser (case, accents, hyphens, en / pt number words, acronyms), aligned, edits in written words with a suggested fix each, flagged beats, worst beats, terms misheard in several beats; lint rule `readback` from the cached transcripts)

### Step 55 — Generated images
- [x] Image-generation provider seam, cached by prompt hash like TTS; one provider; mocked in tests (`vidgen.imagegen`: `ImageProvider` protocol, `imagegen: {provider: openai, model: gpt-image-1, size: auto, quality, style, negative}`; OpenAI Images `POST /v1/images/generations` with stdlib urllib, `OPENAI_API_KEY` from the environment only, retries on 429 / 5xx with `Retry-After` but not on an exhausted quota; the retry loop shared with ElevenLabs in `vidgen.httpapi`; `assets/generated/<key>.png` + `<key>.json` (prompt, sent / revised prompt, provider, model, size, date), key = hash of prompt + style + negative, provider, model, size, quality, seed; `vidgen imagegen [--dry-run] [--force] [--scene ID] [--variant]` with an estimated cost; render / validate never call it)
- [x] `generate:` params on the `image` scene (`{prompt, negative, style, aspect, seed}` or the prompt, exclusive with `path`; size from the format's orientation or `aspect`; project `imagegen.style` presets / words for a consistent look; a theme-coloured placeholder card with the prompt until generated; validate warnings for missing pictures and prompts asking for text / charts; `GenerateImage` + `generated_image` in `vidgen.api` for extension types. Not done: `screenshot` / thumbnail backgrounds — see HANDOFF)

### Step 56 — AI author guide
- [x] `AGENTS.md` + `vidgen guide`: workflow (write → storyboard → lint → fix), pacing rules, on-screen text limits, scene-type chooser, good vs bad examples (packaged guide `data/guide/AGENTS.md`, root copy kept identical; 12 topics: start, workflow, pacing, social, scenes, design, actions, overlays, audio, examples, outputs, troubleshooting; `vidgen guide [TOPIC] [--list] [--json]`; chooser table for all 28 types + a snippet each; 6 before / after pairs; validate / lint message → fix tables; tests check every command / option, scene type, param, preset, action, lint rule and sound named, and validate all 28 YAML snippets; CLAUDE.md / README say who each file is for)

### Step 57 — Scene gallery
- [~] `examples/minimal` covers every Step-5 built-in, without rendered clips; `examples/gallery` (Step 37) every newer type once — a natural source for the gallery's YAML
- [ ] `vidgen gallery` renders one still + short clip per scene type (16:9 and 9:16) with its YAML into `docs/gallery/`
- [ ] (from Step 37) Check the per-type 9:16 stills for label crowding: `map` labels of small countries far apart in a 9:16 world view (a label may stand beside the wrong country with a long leader), `screenshot` / `video_clip` of a 16:9 picture leave wide bands (a portrait default `fit` / `region` could help)

### Step 58 — `vidgen plan`
- [ ] Outline/script in, draft `video.yaml` out: sentences → beats, simple cues → scene types (no LLM call)

### Step 59 — MCP server
- [ ] Optional `mcp` extra: stdio server exposing validate, schema, list-scenes, render, storyboard, lint, gallery
- [ ] (from Step 22) `vidgen tts --json` (and, from Step 55, `vidgen imagegen --json`: the commands without it); human `vidgen validate` still stops at the first variant that does not load (`--json` lists them all)

### Step 60 — Final review
- [ ] Full review of Steps 8–59; docs and examples consistent; release notes in HANDOFF.md
- [ ] (from Step 55) `generate:` for the `screenshot` scene (its `px` callouts / magnifier need the real picture) and a generated picture behind a designed thumbnail; no real image-generation run was made (mocked only)
- [ ] (from Step 51) Locale details translations cannot reach: number formats (`value_format`, decimal / thousands marks defaulted rather than written in the config), the `map` scene's bundled English country names, `map` arc shorthands `"A -> B"` naming a translated pin label, `lint_ignore` object patterns and `point:<series>@<label>` targets naming translated texts; cue cutting for languages without spaces (only at punctuation)
- [ ] (from Step 50) A frame thumbnail's text is not measured (no layout dump for a plain render; a `--frames` render or the lint stills could give `min_font` / `contrast` at 320x180); `post_render` hooks run before the thumbnail is written; `build/..._bare` renders are never cleaned up; the MP4 could carry the thumbnail as cover art (Step 49 gap)
- [ ] (from Step 49) The plan and a silent scene's render can differ by a frame when `(duration - outro) x fps` is a half frame (5 fps, a 1.2 s `chapter` card: planned 7 frames, rendered 6); chapter outputs follow the join, overlays the plan
- [ ] (from Step 48) Revisit: joins with a crossfade / push / wipe re-encode the whole video (~40 s for the gallery's 3:49 preview; stream-copying between transitions needs SPS-compatible re-encoded pieces); `reserve` is per whole scene (several reserving overlays + captions shrink a scene's content until lint's `min_font` fires); mono clip sound is upmixed −3 dB (narration no longer is); a storyboard / lint view of the frames around each transition and carry (Step 47's suggestion; Step 48 used an ad-hoc contact sheet)
- [ ] (from Step 37) Left as known limits, revisit: a `highlight` colour on an `equation_derivation` step is not carried into its dimmed copy; `code`'s own highlight steps reset line opacities set by a `dim` action; `image` Ken Burns renders ~1.6x real time in preview (Manim's per-frame image transform); `code_walkthrough` builds ~0.1 s per line of the file (Manim glyphs; `excerpt` limits it)
