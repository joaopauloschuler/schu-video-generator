# vidgen — design spec

A configurable generator for narrated, animated explainer videos (Manim + ElevenLabs + ffmpeg).
It generalises the one-off `kphi3_paper_video` project: the pipeline is shared, each video is a
**project folder** with a config file, and each project can **extend** the tool with its own
scene types, helpers, theme tokens and pipeline hooks.

Status of this document: describes the implemented system (version 0.1, after the Step 7
review, plus the roadmap steps in tasklist.md recorded in §11 onwards). Sections 1–9 give the original contract; the "Refinements (Step N)" lists record how
each step made it precise, and where a refinement differs from the text above it, the
refinement is what the code does. Changing a public interface requires updating this file in
the same commit and noting it in HANDOFF.md. User documentation: README.md, docs/CONFIG.md
(every config key, checked by `tests/test_docs.py`) and docs/EXTENDING.md.

---

## 1. Goals and non-goals

Goals
- One engine, many videos. A new video = a new project folder, no engine edits.
- Config-only videos for common explainers (built-in scene library).
- **First-class extensibility**: any project can add new scene types, helpers, theme tokens and
  hooks in its own `extensions/` folder, and use them from config by name. A project extension can
  later be promoted into the core library unchanged.
- Narration-driven timing: every beat's animation lasts as long as its audio (+ padding).
- Incremental work: TTS only for changed beats; render one scene at a time; fast previews.
- Runs on Windows (primary user platform), Linux and macOS.

Non-goals (for now)
- Voice providers other than ElevenLabs (keep a small seam, but implement ElevenLabs only).
- Declarative animation DSL. Complex animation lives in Python scene classes.
- GUI / web editor.

## 2. Repository layout

```
pyproject.toml            # package "vidgen", console script `vidgen`, Python >= 3.10
src/vidgen/
  __init__.py             # __version__
  __main__.py             # `python -m vidgen` -> cli.main()
  api.py                  # THE public surface for project extensions (see §6)
  cli.py                  # argparse CLI (see §8)
  jsonout.py              # --json documents of the CLI (see §11)
  describe.py             # scene-type/params descriptions for list-scenes
  guide.py                # `vidgen guide`: the author guide for AI agents, its topics (§59)
  gallery.py              # `vidgen gallery`: samples from the guide, work project, stills / GIFs, pages (§60)
  schema.py               # JSON Schema export (see §12)
  errors.py               # VidgenError, Problem
  config.py               # pydantic v2 models for video.yaml (see §4)
  project.py              # Project: locate/load config, resolve paths, variants
  theme.py                # Theme object (colors, fonts, sizes, background, code style; precedence §19)
  fonts.py                # bundled fonts (data/fonts/, OFL), Pango registration, font roles (§21)
  presets.py              # theme presets: seven built-in presets (§19, §20)
  scales.py               # type scales compact / standard / large / auto, frame orientation (§20)
  themelist.py            # `vidgen list-themes`: preset listing, JSON entries, swatch PNG (§20)
  icons.py                # icon registry: vendored set + project assets/icons, search (§22; no manim)
  icon_mobject.py         # icon() / Icon: SVG -> recoloured VGroup with scaling strokes (§22)
  iconlist.py             # `vidgen list-icons`: listing, JSON, contact sheet, docs/ICONS.md (§22, §23)
  registry.py             # scene-type and action-type registry
  actions.py              # per-beat actions: Target, Action, validation, ActionRunner (§26)
  extensions.py           # discovery + import of project extensions
  hooks.py                # hook registry + dispatch
  runtime.py              # "current project/theme" context used by helpers and extensions
  scene.py                # NarratedScene base class + narrate()
  capture.py              # frame capture: stills at beat ends / N per beat (see §13)
  introspect.py           # layout dump of the captured frames: objects, px boxes, sizes (§15)
  activity.py             # activity file: beat timings, play log, per-frame motion signal (§17)
  storyboard.py           # `vidgen storyboard`: reuse/render stills, write contact sheets (§14)
  sheets.py               # contact-sheet layout and drawing with Pillow (§14)
  lint/                   # `vidgen lint` (§16, §17): rules.py (framework), layout_rules.py,
                          # timing_rules.py, readback_rule.py (§57), color.py, run.py (lint_project), findings.py, report.py
  helpers.py              # theme-aware text helpers and generic drawing utilities
  layout.py               # fit/wrap text, beat distribution, chart numbers, LaTeX detection
  regions.py              # layout regions: safe area, named regions, grids, place(), readable text (§18)
  graph.py                # layered layout of directed graphs, pure Python (§31; no manim)
  callouts.py             # callouts: areas, label placement, box, circle, arrow, magnifier, spotlight (§37)
  clips.py                # video clips: probe, timing, ClipMobject (frames decoded per frame), clip sound (§38)
  geo.py                  # world map data, country lookup, Equal Earth projection, MapView (§39; no manim)
  videoplan.py            # the planned timeline: scene / beat positions in the video before rendering (§41),
                          # planned chapters and video_chapters() (§42)
  chapters.py             # chapter marks from `chapter` scenes and scenes' `chapter:` keys; their checks (§42)
  chapter_export.py       # published chapters (intro at 0:00), MP4 FFMETADATA + tags, YouTube list and rules (§52)
  thumbnail.py            # the thumbnail: a scene's frame or a designed card, small copy, legibility checks (§53)
  export.py               # `vidgen export gif|clip`: palette GIF with a size budget, MP4 clip copy / encode (§53)
  deck.py                 # slide decks' key frames: stills per beat / scene, dedupe, notes, timeline (§55)
  slides.py               # `vidgen slides`: one self-contained HTML deck (data/slides/deck.css, deck.js) (§55)
  slides_pdf.py           # `vidgen slides --format pdf`: slide / notes pages, title page, outline (fpdf2, §56)
  overlays.py             # overlays: Overlay base, OverlayContext, config entries, validation, reserve (§41)
  overlay_layer.py        # OverlayLayer: overlays composited into every frame a scene writes (§41)
  charts.py               # chart helpers: ticks, number labels, axes, legend, markers, fit (§33),
                          # colour scales, colour bar, readable text on fills (§34)
  tts/__init__.py         # provider seam: get_provider(cfg)
  tts/elevenlabs.py       # ElevenLabs provider (stdlib urllib), cache by hash
  stt/                    # speech-to-text seam (§57): __init__.py (STTProvider, Transcript, stt_settings,
                          # get_stt_provider), faster_whisper.py (local, extra vidgen[stt]), elevenlabs.py
  readback.py             # `vidgen readback`: transcripts cached, aligned with the spoken text, WER, edits, suggestions (§57)
  textnorm.py             # text normaliser for readback: case, accents, hyphens, numbers to words (en, pt) (§57; no manim)
  imagegen/               # generated images (§58): __init__.py (GenerateImage, ImageRequest, cache keys, prompt
                          # helpers, warnings), openai.py (OpenAI Images provider), placeholder.py, run.py (`vidgen imagegen`)
  httpapi.py              # POST with retries / scrubbed errors, shared by the ElevenLabs and OpenAI providers (§58)
  render/                 # worker.py (one scene per process), pipeline.py, ffmpeg.py,
                          # fingerprint.py (what a scene's render depends on, §14)
  subtitles.py            # SRT from beat timings (cues cut and timed like captions, §43)
  speech.py               # spoken words, speech bounds of an MP3, word times: estimate / TTS alignment (§43)
  pronunciation.py        # pronunciation dictionary: TTS text of a beat, spoken -> written word map (§45; no manim)
  voices.py               # named voices: effective voice per beat, speaker labels / colours / tags (§46; no manim)
  languages.py            # language tags and per-language rules: cue words, speech rate, TTS / MP4 codes (§54; no manim)
  translation.py          # translation files: text markers, keys, extracting, applying, merging, warnings (§54; no manim)
  cues.py                 # caption cues: phrase-boundary cutting and timing, shared by SRT and captions (§43)
  sfx.py                  # sound effects: synthesised set, loudness, project sounds, the SFX track (§47; no manim)
  music.py                # background music: generated beds, music files as looping sources (§48; no manim)
  mix.py                  # the final mix: music placement, ducking, normalisation, limiter (§48; no manim)
  loudness.py             # BS.1770-4 integrated loudness and true peak, block by block (§48; no manim)
  transitions.py          # scene transitions: effective transition, frame math, colour fade, voice track, xfade names (§49-50; no manim)
  carry.py                # continuity: carried objects' record, rebuild and move, carry checks (§50; manim imported lazily)
  fileio.py               # atomic writes; replacing files that Windows programs keep open
  scenes/                 # built-in scene library (registered like extensions; actions.py:
                          # the built-in beat actions reveal/dim/highlight/zoom/transform, §26-27;
                          # callout_action.py: the callout beat action, §44; sfx_action.py: sfx, §47;
                          # overlays.py: the built-in overlays lower_third/watermark, §41;
                          # progress.py: progress_bar/chapter_indicator, §42; captions.py: captions, §43)
  data/fonts/             # Inter, Source Serif 4, JetBrains Mono NL (.ttf + OFL.txt; package data)
  data/icons/             # manifest.json + lucide/*.svg + lucide/LICENSE (ISC; package data, §22)
  data/geo/               # world-110m.json: Natural Earth 1:110m countries (public domain; package data, §39)
  data/slides/            # deck.css + deck.js inlined into `vidgen slides` pages (package data, §55)
  data/guide/             # AGENTS.md: the author guide printed by `vidgen guide` (package data, §59)
  data/gallery/           # stand-in files for the guide snippets' assets/ paths: picture.png, app.png, clip.webm (§60)
tools/                    # maintainer scripts, not shipped: vendor_icons.py + icon_set.json (§22, §23),
                          # make_screenshot.py, make_clip.py (example assets, §37, §38),
                          # make_gallery_clip.py (data/gallery/clip.webm, §60),
                          # make_world_map.py (builds data/geo/world-110m.json from npm packages, §39)
tests/                    # pytest; no network; slow renders marked `render`
examples/
  minimal/                # config-only example using built-ins
  custom_scene/           # built-ins + one extension scene type, helper module, variant, hook
  kphi3/                  # migrated paper video, custom scenes as extensions
docs/
  CONFIG.md               # config reference
  EXTENDING.md            # how to write project extensions
  ICONS.md                # icon catalogue, generated from the manifest by tools/vendor_icons.py (§23)
  gallery/                # scene gallery written by `vidgen gallery`: README.md, <type>.md, media/ (§60)
AGENTS.md                 # the author guide for agents *using* vidgen (copy of data/guide/AGENTS.md, §59)
DESIGN.md  CLAUDE.md  HANDOFF.md  README.md  THIRD_PARTY_NOTICES.md (bundled fonts §21, icons §22, world map §39)
```

## 3. Project folder layout

```
my_video/
  video.yaml              # config (video.json also accepted)
  extensions/             # optional; every *.py and every package here is auto-imported
  assets/                 # images, data files referenced by scenes (paths relative to project)
    icons/                #   optional project icons <name>.svg (+ icons.json: category, tags) (§22)
    generated/            #   `vidgen imagegen`: <key>.png + <key>.json per generated picture (committed, §58)
  translations/           # optional: translation files of language variants (`vidgen translate-template`, §54)
  audio/                  # generated: <beat_id>.mp3 + <beat_id>.hash  (kept, cheap to reuse)
    <variant>/            #   only for a variant whose voice or beat texts differ (§7)
  build/                  # generated: manim media, per-scene mp4, timings json, concat list
  <output>.mp4            # final video   (<output>_preview.mp4 for previews,
  <output>.srt            #               <output>_<variant>.mp4 for variants)
  <output>_chapters.txt   # YouTube chapter list, when the video has chapters (Step 49, §52)
  <output>_thumbnail.png  # thumbnail (+ .jpg), `vidgen thumbnail` / render with `thumbnail:` (Step 50, §53)
  exports/                # `vidgen export`: GIFs and MP4 clips of parts of the video (Step 50, §53); `vidgen slides` decks (§55, §56)
```

`build/<final|preview>[_<variant>]/` (Step 4) holds: `scenes/<id>.mp4` (the scene as rendered,
with Manim's own audio) and `scenes/<id>.wav` (Manim's uncompressed sound mix, only if the scene
has sound), `timings/<id>.json` (beat timings + the render settings), `media/` (Manim's
intermediate files), `padded/<id>.wav` (each scene's audio padded to its exact video length) with
`padded/video_concat.txt` / `audio_concat.txt`, and `timings.json` (the whole video). Step 44 /
45 add `padded/sfx.wav` (the sound effects, §47) and `padded/mix.wav` (the final mix with
music / normalisation, §48); Step 46 `padded/voice.wav` (the scenes' sound summed where
crossfades overlap them) and `padded/video_concat_<k>.txt` (runs of cut-joined scenes, §49);
Step 47 `scenes/<id>.overlay.mov` (the overlays of the frames a push / wipe into the scene
moves, RGBA) and `carry/<id>.json` (the objects the next scene carries out of it, §50);
Step 49 `padded/metadata.txt` (the MP4's tags and chapters, FFMETADATA, §52); Step 50
`thumbnail/<name>_small.png` (the thumbnail at YouTube's small size, §53) and, for a frame
thumbnail without overlays, a sibling folder `build/<final|preview>[_<variant>]_bare/` (scene
renders of the project without overlays, §53). Step 54: `build/readback/<key>.json` (speech-to-text
transcripts of the beats' MP3s, keyed by audio content + STT settings, shared by qualities and
variants, §57). Step 55: `build/imagegen/<key>-<look>.png` (placeholder cards of generated pictures
not made yet, §58). With `--frames` (Step 10, §13) also `frames/<id>/*.png` + `frames/<id>/index.json` and
`frames/index.json`, and `layout/<id>.json` (Step 12, §15).

## 4. Config schema (`video.yaml`)

Pydantic v2 models in `config.py`. Unknown top-level keys are an error (typo protection);
`params` of scenes and `theme.colors` are open dictionaries.

```yaml
title: "Saving 77% of the Parameters in LLMs"   # required
output: kphi3_video                              # basename of output files; default: folder name

format:                                          # final render
  width: 1920
  height: 1080
  fps: 30
preview:                                         # `--preview` render
  width: 854
  height: 480
  fps: 15

variants:                                        # optional named overrides, deep-merged onto the config
  vertical:
    format: {width: 1080, height: 1920}
    preview: {width: 480, height: 854}

theme:
  preset: light_academic                         # optional (Step 16, §19); values below still win
  background: "#0E1116"
  font: Inter                                    # sans family (Step 18: bundled, §21)
  font_serif: Source Serif 4                     # serif family (Step 18)
  font_mono: JetBrains Mono NL                   # mono family, code listings (Step 18)
  fonts: {heading: serif}                        # font roles -> sans/serif/mono or a family (Step 18)
  code_style: github-dark                        # Pygments style of `code` listings (Step 16)
  scale: auto                                    # type scale (Step 17, §20): compact/standard/large/auto
  colors:                                        # open dict; these names are the defaults
    text: "#E8EAED"
    dim: "#838B98"                               # Step 16 (was #6B7280, below WCAG AA)
    accent: "#FF6B6B"
    highlight: "#FFD166"
    primary: "#58C4DD"
    secondary: "#F2A541"
    tertiary: "#83C167"
    surface: "#161B24"                           # panels / code background (Step 5)
    # projects may add any name, e.g. k2: "#F2A541"
  palette: ["#58C4DD", "#F2A541", "#C792EA", "#83C167"]   # ordered series colors (charts, groups)
  sizes: {title: 56, subtitle: 42, heading: 36, body: 32, caption: 24, small: 20}

voice:
  provider: elevenlabs                           # only allowed value for now
  voice_id: nPczCjzI2devNBz1zQrb
  model_id: eleven_multilingual_v2
  output_format: mp3_44100_128
  settings: {stability: 0.55, similarity_boost: 0.75, style: 0.0, use_speaker_boost: true}
  context: true                                  # send previous_text/next_text for continuity

narration:
  pad: 0.35                                      # seconds of silence after each beat
  words_per_second: 2.6                          # duration estimate when a beat has no audio

pronunciation: {K-Phi-3: kay fye three}          # Step 42 (§45): TTS text only; + pronunciation_file
voices: {ana: {voice_id: 21m00Tcm4TlvDq8ikWAM, label: "Dr. Ana"}}   # Step 43 (§46): + scene / beat `voice: ana`
subtitles: {speakers: off}                       # Step 43 (§46): `name` tags speakers in the SRT
sfx: {auto: false, gain: 0}                      # Step 44 (§47): + scene `sfx:` lists, beat action `sfx`
music: calm                                      # Step 45 (§48): bed / file / cue / cues; + scene `music:`
audio: {normalize: auto, target_lufs: -16, true_peak: -1.5}   # Step 45 (§48): the final mix
transition: crossfade                            # Step 46 (§49): default between scenes; + scene `transition:`
                                                 # Step 47 (§50): push / wipe {direction, soft}; scene `carry:`
chapters: {metadata: true, youtube: true, intro: Intro}   # Step 49 (§52): MP4 chapters, <output>_chapters.txt
metadata: {artist: "Jane Doe"}                   # Step 49 (§52): MP4 tags (title defaults to `title`)
thumbnail: {title: "Saving 77%", icon: cpu}      # Step 50 (§53): designed card, or {scene, beat, at, overlays}
language: en                                     # Step 51 (§54): BCP-47; cue rules, speed lint, TTS / MP4 language
translations: translations/pt.yaml               # Step 51 (§54): usually in a variant; texts replaced at load
stt: {provider: faster_whisper}                  # Step 54 (§57): speech to text of `vidgen readback`
imagegen: {model: gpt-image-1, style: flat}      # Step 55 (§58): generated pictures (`generate:` params)

extensions: [extensions]                         # dirs (relative to project) to auto-import; default shown

scenes:
  - id: intro                                    # required, unique, [A-Za-z0-9_]+
    type: title                                  # registered scene type (built-in or extension)
    params:                                      # validated by the scene type's Params model, if any
      title: "Saving 77% of the Parameters"
      subtitle: "in Large Language Models"
    beats:
      - id: s1_b1                                # optional; default f"{scene.id}_b{n}" (1-based)
        text: "What if a large language model ..."
      - text: "This technical report ..."
```

Validation rules: beat ids unique across the whole video; scene ids unique; `type` must be
registered after extensions load (`vidgen validate` reports unknown types with the list of known
ones); `params` validated against the scene class's `Params` model when it defines one.

Refinements (Step 1):
- Unknown keys are rejected in every structural model (not only top level): `format`, `preview`,
  `theme`, `voice`, `voice.settings`, `narration`, scenes and beats. Open: `params`,
  `theme.colors`, `theme.sizes`, and the bodies of `variants` (validated after merging).
- `theme.colors` / `theme.sizes` / `theme.palette` in the config hold only what the user wrote;
  `Theme` merges them over the built-in defaults shown above. Color values must be hex
  (`#RGB`, `#RRGGBB` or `#RRGGBBAA`); token names follow the id pattern.
- **Silent scenes**: a scene may have no beats (`beats: []` or omitted) if it sets
  `duration: <seconds>`; `duration` is an error on a scene that has beats (narrated scenes are
  timed by their audio).
- Variants: the variant mapping is deep-merged onto the raw config (mappings merge recursively,
  lists such as `scenes` and scalars replace), then the result is validated. A variant may not
  contain `variants`. `vidgen validate` checks the base config and every variant.
- `output` defaults to the project folder name and must be a plain file name (no path separators).
- `extensions` entries are directories relative to the project root; `Project.asset(rel)` also
  resolves relative to the project root (e.g. `assets/logo.png`).

## 5. Scene runtime

### 5.1 `NarratedScene` (in `scene.py`, subclass of `manim.Scene`)

Attributes available inside `construct()`:
- `self.spec` — the `SceneConfig` from video.yaml
- `self.params` — validated params (instance of the class's `Params` model, or a plain dict)
- `self.beats` — list of `BeatConfig` in order
- `self.theme` — the active `Theme`
- `self.project` — the active `Project` (paths: `self.project.asset(rel)` resolves assets)

Methods:
- `with self.narrate(beat) as d:` — `beat` is a beat id **or** 0-based index into `self.beats`.
  Adds the beat's MP3 (if present) at the current time, yields its duration `d` (audio length,
  or the word-count estimate), and on exit waits until `d + pad` has elapsed. Records
  `(beat_id, start, end, text)` into `self.beat_log` (used for subtitles).
- `self.beat_duration(beat) -> float`
- (Step 14) `self.play_log` (every `play`/`wait`: `PlayRecord(start, end, beat, animations,
  wait, requested)`), `self.beat_busy` (seconds each `narrate` body took), `self.silent_busy`;
  recorded always, written to the activity file (§17) when stills are captured.
- `self.clear_all(run_time=0.6)` — fade out everything.
- `self.narrate_all()` — convenience generator: `for beat, d in self.narrate_all(): ...`.

Theme-aware text: `self.text(s, size="body"|int, color="text"|"#hex", weight=...)` and
`self.markup(...)`; sizes and colors accept theme token names or literal values.

Refinements (Step 2):
- Injection is the constructor: `SceneClass(spec, project=None, theme=None, *, audio=True,
  **manim_scene_kwargs)`. `project`/`theme` default to the runtime context (§6.3); without a
  context the theme is built from `project.config.theme`. Constructing needs Manim's config set
  up (Manim creates its renderer); params validation does not: `SceneClass.validate_params(raw)`
  (raises `pydantic.ValidationError`), `SceneClass.parse_params(raw, scene_id)` (raises
  `VidgenError`), `SceneClass.params_model()`. `Params` must subclass `SceneParams`
  (pydantic, `extra="forbid"`); inherited `Params` count.
- `audio=False` (`--no-audio`) skips `add_sound` but still takes durations from the MP3s, so
  timing is identical.
- `self.beat_log: list[BeatTiming]`, `BeatTiming(beat_id, start, end, text)` (NamedTuple; seconds
  from scene start; `end = start + d`). `self.timings()` returns
  `{"scene": id, "duration": total_seconds, "beats": [{"id", "start", "end", "text"}]}`.
- Waits are frame-exact (`self.wait_seconds(t)` rounds to whole frames), so a beat lasts
  `d + pad` within half a frame. Narrating a beat twice is an error; beats never narrated are
  logged as a warning at the end of the scene.
- Silent scenes are held to `spec.duration` automatically in `tear_down()`; `self.hold(until=None)`
  holds earlier. Subclasses overriding `tear_down` must call `super().tear_down()`.
- Also available: `self.beat(id|index|BeatConfig)`, `self.beat_audio(beat) -> Path | None`,
  `self.pad`. `text()`/`markup()` colors may also be `ManimColor` objects.

### 5.2 How a scene gets rendered

The renderer renders **each scene in its own subprocess** (Manim's global config is not
re-entrant): `python -m vidgen.render.worker <project_dir> <scene_id> --quality final|preview
[--variant NAME] [--no-audio]`. The worker:
1. loads the project + variant, builds the Theme, sets the runtime context (§6.3),
2. imports built-in scenes and project extensions,
3. configures Manim (resolution, fps, background, explicit `media_dir` under `build/`, explicit
   output file name — never guess Manim's folder naming),
4. instantiates the registered class for `scene.type`, injects spec/params/beats/theme/project,
   renders, and writes `build/<quality>[_<variant>]/timings/<scene_id>.json` from `beat_log`.

The parent then pads each scene's audio with silence to the exact video length, concatenates in
config order, and writes the final MP4 and SRT (SRT times = scene offset + beat start/end).

Refinements (Step 2): the worker does steps 1–2 with `vidgen.extensions.activate(project)`
(returns the Theme), then `cls = vidgen.registry.get(spec.type).cls`,
`scene = cls(spec, project, theme, audio=not no_audio)`, `scene.render()`, and writes
`scene.timings()`. Manim caching must be disabled (`disable_caching=True`): on a cache hit Manim
advances its clock by the unquantized duration, which would desynchronise `beat_log` from the
frames.

Refinements (Step 4):
- **Worker** (`vidgen/render/worker.py`, extra flag `--progress` shows Manim's progress bars):
  sets `pixel_width/height`, `frame_rate`, `background_color = theme.background`,
  `disable_caching`, `media_dir = <render_dir>/media`, `video_dir`/`partial_movie_dir` per scene
  id (so parallel workers never share a folder) and `output_file = <scene_id>`; after rendering
  it moves `renderer.file_writer.movie_file_path` (and Manim's `.wav` beside it, if any) to
  `scenes/<id>.mp4|.wav` and writes `timings/<id>.json` = `scene.timings()` (rounded to µs) plus
  `"render": {width, height, fps, audio, vidgen}`. Old files of the scene are deleted first, so
  a failed render leaves none. Manim cannot handle `'`, `{` or `}` in its paths (it formats them
  with `str.format` and writes unescaped concat lists); for such project paths Manim's media
  folder is a temporary directory instead. Exit codes: 0 ok, 1 `VidgenError` (`error: ...` on
  stderr), 2 other exceptions (full traceback). The worker runs with `PYTHONUTF8=1`.
- **Frame size**: Manim does not recompute `frame_width` when pixel sizes are set from code (a
  portrait render would be squashed), so the worker sets it: the **shorter side is 8 units**
  with square pixels (16:9 → 14.22 x 8, Manim's default; 9:16 → 8 x 14.22; 1:1 → 8 x 8). Scenes
  read `config.frame_width/height`, or `NarratedScene.frame_width`, `.frame_height`,
  `.is_portrait` (new read-only properties).
- **Audio/no drift**: concatenating AAC segments drifts (every segment carries ~21 ms of encoder
  priming that the concat demuxer does not remove — measured: +50 ms after two scene
  boundaries). So the parent pads Manim's **PCM WAV** of each scene (silence for silent scenes
  and `--no-audio`) to exactly the video's length (48 kHz stereo; the sample count of scene *i*
  is `round(end_i*48000) - round(start_i*48000)`, so rounding never accumulates), concatenates
  the videos (stream copy) and the WAVs (PCM) with two concat-demuxer lists, and encodes the
  audio once to AAC 192k in the final mux. Measured beat onsets in the output match
  `timings.json` within 1 ms. Scene durations are measured from the rendered videos with PyAV
  (frames / fps). The final MP4 is written to `<name>.partial.mp4` and renamed (Step 7: if
  the target stays locked, the partial file is kept and the error says so).
- **Timings**: `build/<q>[_<variant>]/timings.json` = `{title, variant, preview, format: {width,
  height, fps}, audio, duration, vidgen, scenes: [{id, type, start, duration, beats: [{id,
  start, end, text}]}]}`, all times absolute seconds. SRT cues come from it (`subtitles.py`):
  1-based, `HH:MM:SS,mmm`, UTF-8; beat text wrapped to 42-character lines, at most 2 lines per
  cue, the beat's time (start → narration end, pad excluded) shared in proportion to characters.
- **Scene selection**: no automatic up-to-date detection. Without `--scene` every scene is
  rendered. With `--scene` those are rendered, and others are reused if their render exists and
  was made at the current format (and with audio, unless `--no-audio`); otherwise they are
  rendered too. Reused renders are not checked against config/extension changes.
- **Failures**: without `--keep-going` the first failing scene stops the command (message: scene
  id, exit code, last 60 lines of worker output — the user's traceback for exceptions in scene
  code). With it, the remaining scenes are rendered, failures are printed as they happen, the
  video is **not** joined, and the command fails listing the failed scenes.
- **Parallelism**: `render_project(..., jobs=N)` / `vidgen render --jobs N` runs N workers at
  once (default 1). Live Manim progress is shown only for `jobs == 1` on a terminal; otherwise
  worker output is captured and its `warning:` lines are re-printed.
- **Audio check**: before rendering, missing/stale narration audio (`tts.audio_status`) is
  logged as a warning recommending `vidgen tts`; ffmpeg missing is a `VidgenError` with install
  hints (`winget install ffmpeg` on Windows).

Refinements (Step 5):
- **Worker caches**: `config.text_dir = media/texts/<scene_id>` and `config.tex_dir =
  media/Tex/<scene_id>`. Manim caches Text/Tex SVGs by content hash in one folder; with
  `--jobs N` two workers writing the same SVG at once made the other parse a half-written file
  (`xml.etree.ElementTree.ParseError`). Per-scene folders cost cache reuse across scenes only.

### 5.3 Scene-building API (Step 5)

Added to `NarratedScene` so built-ins and extensions share it:
- `validate_params(params, theme=None)` / `parse_params(params, scene_id, theme=None)`: the theme
  is passed to validators as `info.context["theme"]`; the constructor passes `self.theme`.
- `ThemeColor` (`Annotated[str, ...]`) and `ThemeSize` (`Annotated[str | float, ...]`) for
  `Params` fields: hex syntax is always checked, token names when a theme is given (validate and
  render). Both carry a `ThemeToken(kind)` marker; `list-scenes` prints them as `color` / `size`.
- classmethod `validate_project(params, project) -> list[str]`: project-aware checks run by
  `vidgen validate` (inside the project session, after params validated); each message is
  reported as `scenes[i].params.<message>` (convention: start with the param name). Default `[]`.
- `outro: float = 0.0` (class attribute) and `finish()` (fade out everything over `outro`).
- `timeline()`: yields `(index, d)` per narrated beat; a silent scene yields one
  `(0, duration - outro)` step and then holds to that time.
- `play_steps(d, steps, fraction=0.7, cap=1.2)`: spreads steps (animation | list | callable
  returning either) over `d` seconds, each run for `min(cap, fraction * slot)`; never longer
  than `d` (if `d` has fewer frames than steps, consecutive steps are merged).
- `reveal(steps, fraction, cap)`: `distribute(len(steps), len(beats))` + `timeline()` +
  `play_steps()` per beat.
- `safe_width` / `safe_height` (frame minus `margin_x = 0.6`, `margin_y = 0.5` units; Step 15:
  derived from `self.safe_area`, §18).

Refinements (Step 6, found while porting kphi3):
- `beat_count: int | tuple[int, int | None] | None = None` (class attribute): how many beats a
  scene type narrates (`None` any, `2` exactly, `(1, None)` at least one, `(2, 4)` a range).
  Types that narrate fixed beat indices set it. `check_beat_count(n) -> str | None` (e.g.
  `"needs exactly 2 beats, got 3"`) and `beat_count_text()` (`"exactly 2 beats"`) are
  classmethods. `vidgen validate` reports `scenes[i].beats: type 'x' needs ...`; the constructor
  raises `VidgenError("scene 'id': needs ...")`; `vidgen list-scenes` prints `beats: ...`.
  Built-ins leave it `None` (they adapt to any number of beats).

`vidgen.layout` (exported by `vidgen.api`): `fit_text`, `measure_text` (Step 27), `shrink_to_fit`, `wrap_lines`,
`normalize_text`, `distribute`, `nice_ticks`, `auto_format`, `format_value`, `check_format`,
`latex_available`, `require_latex` (+ `missing_latex_tools`, not exported). `fit_text` measures
each word once (cached per font/weight) and searches the font size arithmetically, building the
`Paragraph` once; `Paragraph` `line_spacing` defaults to 0.7 (Manim's -1 sets lines nearly
touching). Highlights are applied with `t2c` index ranges (wrapping only turns spaces into line
breaks, so indices into the normalized text stay valid).

## 6. Extension system (the core requirement)

### 6.1 Discovery
For each directory in `extensions` (default `extensions/`, silently skipped if absent):
every `*.py` file (not starting with `_`) and every sub-package is imported, in sorted order,
under a private package name `vidgen_ext_<sanitised project name>` so that extension modules can
import each other with relative imports (`from .common import column`). The project's
directory is **not** put on `sys.path` globally. Import errors are reported with the file name
and the original traceback.

### 6.2 What an extension can register (all via `vidgen.api`)
```python
from vidgen.api import *          # NarratedScene, scene, hook, theme helpers, manim names

@scene("loss_panel")              # name used as `type:` in video.yaml
class LossPanel(NarratedScene):
    class Params(SceneParams):    # optional pydantic model for params validation
        values: dict[str, float]
        best: str | None = None

    def construct(self):
        with self.narrate(0) as d:
            ...

@hook("post_render")              # events: pre_tts, post_tts, pre_render, post_scene, post_render
def add_watermark(ctx): ...       # ctx: HookContext(project, event, data: dict)

register_theme_defaults({"k2": "#F2A541"})   # extra theme tokens; video.yaml values still win
register_theme_preset("acme", base="light_academic", colors={"primary": "#0B5FFF"})   # Step 16
```
- **Scene types**: `@scene(name, *, override=False)`. Name collision with another extension is an
  error. Colliding with a built-in raises unless `override=True`, which replaces it and logs a
  warning (`vidgen list-scenes` marks it as overridden).
- **Helpers**: plain Python functions/modules inside `extensions/`; shared via relative imports.
- **Theme tokens**: `register_theme_defaults()`; `theme.color("k2")`, `theme.size("body")`.
- **Hooks**: `@hook(event)`; called in registration order; exceptions abort the command with the
  hook's name in the message.
- **Hook data** (Step 3, TTS): `pre_tts` — `beats: list[str]` (ids about to be generated, video
  order; a hook may remove ids to skip them or add known ids), `audio_dir: Path`, `force: bool`,
  `dry_run: bool`; dispatched on dry runs too. `post_tts` — `generated: list[str]` (ids written,
  in order), `audio_dir: Path`; not dispatched on dry runs or when the command fails. The API key
  is never part of hook data.
- **Hook data** (Step 10): `post_scene` also gets `frames` (the scene's stills folder, or `None`
  without `--frames`), `post_render` gets `frames_index` (`frames/index.json` or `None`).
- **Hook data** (Step 4, render; hooks run in the parent `vidgen render` process): `pre_render` —
  `scenes: list[str]` (ids about to be rendered, config order; a hook may remove ids to reuse
  their existing render), `preview: bool`, `variant: str | None`, `no_audio: bool`,
  `render_dir: Path`. `post_scene` — once per scene rendered in this run (not for reused ones):
  `scene_id`, `video: Path` (`scenes/<id>.mp4`, before padding), `timings: dict` (the scene's
  timings file content), `preview`, `variant`. `post_render` — after the MP4, SRT and
  `timings.json` are written: `output: Path`, `srt: Path`, `timings: dict` (combined),
  `timings_file: Path`, `preview`, `variant`. Not dispatched when the command fails.
- **Promotion**: an extension module copied into `src/vidgen/scenes/` works unchanged, because
  built-ins use exactly the same `@scene` API.

### 6.3 Runtime context
`vidgen.runtime` holds the active Project and Theme. It is set **before** extensions are imported,
so module-level code in an extension may read theme values
(`C_BASE = current_theme().color("primary")`). `api.T(...)` / `api.MT(...)` are function forms of
`self.text`/`self.markup` that use the current theme — this makes porting old scripts easy.

### 6.4 `vidgen.api` exports (stable surface)
`NarratedScene, SceneParams, scene, hook, HookContext, register_theme_defaults, current_theme,
current_project, T, MT`, generic helpers from `helpers.py`, and `from manim import *`.
Step 5 adds `ThemeColor, ThemeSize`, the `vidgen.layout` helpers (§5.3) and pydantic's
`Field, field_validator, model_validator`.
Step 15 adds the layout regions (§18): `Region, frame_region, safe_area, region, grid, place,
orientation, readable_size, readable_text`. Step 16 adds `register_theme_preset` (§19); Step 17
gives it the keyword arguments `scale` and `fonts` (§20). Step 19 adds `icon`, `Icon` and
`IconName` (§22). Step 21 adds `grid_shape` (§24). Step 22 (§25) adds keyword arguments only:
`role=` on `T`, `MT`, `NarratedScene.text`/`markup`, `fit_text` and `readable_text`; `region(name,
area)` also takes a region name as `area`; `SceneParams.also_accepts`. Step 23 (§26) adds
`action`, `Action`, `ActionOptions`, `Target` and, on `NarratedScene`, `target_patterns`,
`target_names()`, `target()`, `targets`, `find_targets()`, `on_screen_parts()`, `is_shown()`,
`entrance()`. Step 24 (§27) adds, compatibly: `NarratedScene` is a `MovingCameraScene`;
`target(..., outline=)`; `Target.outline`, `Target.rest`, `Target.rest_opacity()`; `Action`
class attributes `temporary`, `moves_camera`, `target_options`. Step 27 adds `measure_text`.
Step 28 (§31) adds `layered_layout`, `GraphLayout`, `GraphNode`, `GraphEdge`, `EdgeRoute`,
`NodePlace`.
Step 29 (§32) adds `sparse_pairs` and `group_bounds`, and compatible keyword arguments:
`column(..., horizontal=False, skip=None)`, `edges(..., colors=None, shorten=0.0)`,
`grouped_pairs(n, groups, m=None)`.
Step 30 (§33) adds the chart helpers: `ChartAxis`, `ChartAxes`, `LinearFit`, `CHART_MARKERS`,
`axis_ticks`, `short_number`, `tick_texts`, `value_axis`, `chart_axes`, `chart_label_size`,
`chart_legend`, `auto_legend`, `legend_spot`, `sample_path`, `chart_marker`, `linear_fit`,
`chart_title`, `chart_caption`.
Step 31 (§34) adds `ColorScale`, `color_scale`, `color_bar`, `mix_colors`, `text_color_on`.
Step 34 (§37) adds the callout helpers: `Callout`, `CalloutArea`, `CALLOUT_KINDS`, `callout`,
`callout_area`, `callout_box`, `callout_circle`, `callout_arrow`, `callout_magnifier`,
`callout_spotlight`, `callout_label`, `label_spot`.
Step 35 (§38) adds the video clip helpers: `CLIP_SUFFIXES`, `ClipInfo`, `ClipMobject`,
`ClipTiming`, `clip_audio`, `fit_speed`, `probe_clip`.
Step 36 (§39) adds the map helpers: `MAP_VIEWS`, `Country`, `MapView`, `equal_earth`,
`find_country`, `fit_view`, `view_box`, `world_countries`.
Step 38 (§41) adds `overlay`, `Overlay`, `OverlayOptions`, `OverlayContext`, `with_opacity`, and
`NarratedScene.overlay_layer` (compatible: `NarratedScene.safe_area` shrinks for reserved overlays).
Step 39 (§42) adds `video_chapters`, `Chapter`. Step 40 (§43) adds `WordTime`, `beat_word_times`,
`estimate_word_times`, `speech_bounds`, `spoken_words`, `syllables`, `CaptionCue`,
`caption_cues`, `segment_cues`, `phrase_break_cost`, `plate_contrast`, and compatibly
`Overlay.default_reserve()` / `Overlay.reserves`.
Step 41 (§44) adds, compatibly, the `Action` class attribute `until_next_beat` and the methods
`problems()`, `provides()`, `default_until(later)`.
Step 42 (§45) adds `Pronunciation`, `Spoken`, `map_word_times`, and compatibly the optional last
argument `spoken` of `beat_word_times`.
Step 43 (§46) adds `speaker_label`, `speaker_color`, `speaker_prefix`, and compatibly the keyword
arguments `prefix` / `prefix_width` of `caption_cues` and the field `CaptionCue.prefix`.
Step 44 (§47) adds `SfxEvent`, `SfxParams`, `SoundLibrary`, `sound_library`, `synthesize`; on
`NarratedScene` `sfx()`, `sfx_log`, `sounds`, `auto_sfx()` and the class attribute
`entrance_sfx`; on `Action` (compatibly) the class attributes `scene_targets`, `animates` and
the method `cue(scene, time)`.
Step 46 (§49) adds, compatibly, `NarratedScene.transition_in` / `transition_out` (planned
`TransitionSlot`s or `None`) and `SceneSlot.overlap_in`, `overlap_out`, `cut` (fields with
defaults / a property); `finish()` holds instead of fading when a transition follows.
Step 47 (§50) adds `carry_move`; on `NarratedScene` `carry_in(name)`, `carry_out`, `carry_state`,
`carried_in`, `overlay_head`, and compatibly `clear_all(run_time, keep=())`; `entrance()` moves
a carried copy into its target; `finish()` keeps carried targets on screen.
Step 49 (§52) adds, compatibly, the keyword argument `intro=False` of `video_chapters` and the
field `Chapter.intro` (default `False`).
Step 51 (§54) adds `TranslatableStr`, `TextRef`, `LanguageRules`, `language_rules`; on
`SceneParams` the class attributes `text_shorthand` and `text_defaults`; and compatibly the
keyword argument `language=None` of `caption_cues`, `segment_cues`, `phrase_break_cost`,
`beat_word_times`, `estimate_word_times` and `syllables`.
Step 55 (§58) adds `GenerateImage`, `generated_image`.
Anything not exported from `vidgen.api` is internal and may change.

### 6.5 Refinements (Step 2)
- **Built-in vs extension** is decided by the module that defines the class/function: modules
  inside the `vidgen` package are built-in, anything else is an extension. The origin shown in
  messages and `list-scenes` is `builtin` or the defining file relative to the project root.
- **Discovery**: names starting with `_` or `.` are skipped; folders without `__init__.py` are
  skipped. Several `extensions` directories share the one synthetic package (its `__path__`
  lists them all), so relative imports work across them; the same module name in two
  directories is an error. The default `extensions/` may be absent; a directory written
  explicitly in `extensions:` must exist. The package name is `vidgen_ext_<folder name,
  lower-cased, non-word characters replaced by _>`; it is removed from `sys.modules` before each
  load. An exception raised while importing becomes a `VidgenError` with the file (relative to
  the project) and the traceback (importlib frames removed); a `VidgenError` raised during
  import (e.g. a name collision) propagates unchanged.
- **Override**: `override=True` replacing a built-in logs a warning on logger `vidgen.registry`;
  `override=True` without a built-in of that name also logs a warning. The CLI prints vidgen log
  warnings as `warning: <message>` on stderr.
- **Isolation** (several projects/variants in one process): built-in registrations are
  permanent (their modules stay imported); extension scene types and hooks form a per-project
  layer. `registry.reset()/snapshot()/restore()/isolated()` and the same four in `hooks`;
  `runtime.set_context()/clear_context()/use_context()`;
  `extensions.activate(project)` (process-wide: context + reset + load) and
  `extensions.project_session(project)` (context manager: everything restored on exit, the
  synthetic package unloaded). Every `activate` builds a fresh Theme, so theme defaults
  registered by one project never leak into another.
- **Hooks**: built-in hooks run before extension hooks, each group in registration order.
  `dispatch(event, project, **data)` returns the `HookContext` (hooks may modify `ctx.data`).
  Errors are wrapped as `hook <module.qualname> (<origin>) failed during <event>: ...` with the
  traceback appended (a `VidgenError` from a hook keeps just its message).
- **`vidgen.api`** additionally exports `VidgenError` (for extensions to raise clear errors) and
  `resolve_color(color, theme=None)`. The only name shared with `from manim import *` is
  `scene` (manim's `manim.scene` subpackage); `vidgen.api.scene` is the decorator.
  `vidgen.api.SHADOWED_MANIM_NAMES` records this and a test pins it.
- **Validation** (`vidgen validate`): unknown types are reported as
  `scenes[i].type: unknown scene type 'x'; did you mean 'y'? (known types: ...)`; params errors as
  `scenes[i].params.<field>: <message>`. Variant problems are prefixed `[variant NAME]`; problems
  identical to the base config's are not repeated.
- **`vidgen list-scenes [PROJECT]`** prints `name  origin  [(overrides builtin)]` and one indented
  line per `Params` field (`name: type [= default]`), or `params: free-form`. Without a PROJECT
  argument and no config file in the current directory it lists the built-ins only.
- **Built-in library**: `vidgen/scenes/__init__.py` imports each scene module explicitly
  (Step 2 ships `text_card`: params `text`, `size="title"`, `color="text"`). Step 5 adds
  `title, bullets, bar_chart, line_chart, image, quote, equation, code, end_card` (reference:
  docs/CONFIG.md "Built-in scenes"). Their only vidgen import is `from vidgen.api import *`
  (a test pins this); shared code between built-ins uses relative imports (`end_card` imports
  `check_image`/`load_image` from `.image`), exactly like extension modules.

## 7. TTS (ElevenLabs)

- Endpoint `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=...`.
  Standard library only (urllib).
- **API key location**: read only from the environment variable `ELEVENLABS_API_KEY`
  (Windows: `setx ELEVENLABS_API_KEY your_key` once, then open a new terminal; Linux/macOS:
  `export ELEVENLABS_API_KEY=...`). vidgen never stores the key: it is not a config field, and it
  is never written to video.yaml, audio/, build/, logs, error messages, hook contexts or git.
  It is sent only as the `xi-api-key` header to api.elevenlabs.io. Only `vidgen tts` (without
  `--dry-run`) needs it; validate/render/dry-run work without it.
- Cache key: sha1 of `voice_id | model_id | output_format | json(settings, sorted keys) | text`,
  stored as `audio/<beat_id>.hash`. Neighbouring beats' text is sent as `previous_text` /
  `next_text` for intonation but is **not** hashed, so editing one beat regenerates only that beat.
- Backward compatibility: the kphi3 hash format (`sha1(voice_id + model_id + text)`) is also
  accepted as "up to date" when settings/output_format equal the old defaults, so existing audio
  is reused without paying for regeneration.
- `vidgen tts [--force] [--dry-run] [--beat ID ...]`; dry run lists what would be generated and the
  character count. Missing API key → clear error, no traceback. HTTP errors show status + body.
- Orphaned mp3s (beat ids no longer in config) are reported, not deleted.
- Tests mock `urllib.request.urlopen`; no network.

Refinements (Step 3):
- **Provider seam** (`vidgen.tts`): `get_provider(voice) -> TTSProvider` (ElevenLabs only; other
  providers raise `VidgenError`). `TTSProvider`: `name`, `cache_key(text)`, `matches(text,
  stored_hash)`, `check_credentials()`, `synthesize(text, previous_text=None, next_text=None) ->
  bytes`. Constructing a provider never needs the key; it is read from the environment on every
  request (stripped) and never kept on the object.
- **Exact cache key**: `sha1("|".join([voice_id, model_id, output_format,
  json.dumps(settings, sort_keys=True), text]).encode("utf-8"))` where `settings` is
  `voice.settings.model_dump()` (default `json.dumps` separators). `voice.context` is not hashed.
- **kphi3 hashes**: accepted when `output_format == mp3_44100_128` and settings equal
  `{stability 0.55, similarity_boost 0.75, style 0.0, use_speaker_boost true}` (the defaults).
  They are **not rewritten** to the new format: the files stay untouched (no git noise for the
  committed kphi3 example audio); any regeneration writes a new-format hash.
- **Requests**: JSON body `{text, model_id, voice_settings}` plus `previous_text`/`next_text` (the
  neighbouring beats in video order, across scene boundaries, omitted at the ends) only when
  `voice.context` is true. Timeout 120 s. Transient failures (HTTP 429/500/502/503/504, timeouts,
  dropped connections) are retried 3 times with backoff 2, 4, 8 s (or `Retry-After`, capped at
  30 s). Errors become `VidgenError`: `ElevenLabs returned HTTP <code>: <body, max 500 chars>` or
  `cannot reach ElevenLabs: ...`; any occurrence of the key is replaced by `***`. The CLI prefixes
  `beat '<id>': ` and says how many beats were done before the error.
- **Writes**: MP3 via temp file + `os.replace` in the same folder, then the hash the same way, so a
  hash never vouches for a partially written MP3. Already generated beats are kept on failure.
- **Command details**: `--variant NAME` added. `--beat` restricts the selection (unknown id →
  error) but up-to-date beats are still skipped unless `--force`. The key is required only when
  at least one beat must be synthesised (an up-to-date project needs no key). Output: one
  `[n/N] generated <id>.mp3 (<chars> chars)` line per beat and a summary; dry run prints
  `would generate ...` lines and `dry run: N beat(s) to generate, C characters; U up to date`.
  The character count is what is billed (beat text only, not context).
- **Variant audio**: a variant uses `audio/<variant>/` when its effective `voice` (after merging)
  differs from the base config's, or a beat id present in both configs has a different text;
  otherwise it shares `audio/`. `Project.audio_dir` implements this (`Project.has_own_audio`,
  `Project.base_config`), so `NarratedScene.beat_audio` picks the right files. When generating
  into a variant folder, beats whose audio in `audio/` is up to date for the variant's voice
  and text are copied instead of synthesised.
- **Orphans**: MP3s in the audio folder whose id is used by no config sharing that folder (base +
  variants) are listed, never deleted; subfolders are ignored.
- **Audio status** (no key): `vidgen.tts.audio_status(project) -> list[BeatAudioStatus]`
  (`scene_id, beat_id, text, state, mp3, hash_file`; state `ok` | `stale` | `missing`; stale =
  MP3 exists but its hash is missing or does not match). `format_audio_summary(statuses)` →
  `"18 ok, 2 stale, 1 missing"`; `orphaned_audio(project) -> list[Path]`. `vidgen validate`
  prints `audio:     <summary>` (plus `(N orphaned mp3)`) and one `audio [<variant>]: ...` line
  per variant with its own audio folder. `render` (Step 4) should warn, not fail, on stale/missing.

## 8. CLI

```
vidgen init <dir> [--example minimal]   # scaffold a project
vidgen guide [TOPIC] [--list] [--json]  # the author guide for AI agents (AGENTS.md, §59)
vidgen validate [PROJECT] [--json]      # load config + extensions, report all errors
vidgen list-scenes [PROJECT] [--json]   # built-ins + extensions (+ which overrides)
vidgen list-themes [PROJECT] [--swatches PNG] [--json]   # theme presets + type scales (§20)
vidgen list-icons [PROJECT] [--search TEXT] [--category NAME] [--sheet PNG] [--json]   # icons (§22)
vidgen list-sfx [PROJECT] [--render-dir DIR] [--json]   # sound effects with descriptions (§47)
vidgen list-music [PROJECT] [--render-dir DIR] [--json]   # music beds with descriptions (§48)
vidgen schema [PROJECT] [--scene TYPE | --all] [--json]   # JSON Schema of video.yaml (§12)
vidgen tts [PROJECT] [--force] [--dry-run] [--beat ID ...] [--voice NAME ...] [--variant NAME]
vidgen render [PROJECT] [--preview] [--scene ID ...] [--variant NAME] [--no-audio] [--keep-going]
              [--jobs N] [--frames] [--frames-per-beat N] [--json]
vidgen storyboard [PROJECT] [--scene ID ...] [--per-beat N] [--variant NAME] [--preview | --final]
              [--width PX] [--jobs N] [--force] [--json]      # contact sheets (§14)
vidgen lint [PROJECT] [--scene ID ...] [--rule NAME ...] [--variant NAME] [--preview | --final]
              [--fail-on SEVERITY] [--jobs N] [--force] [--json]   # layout checks (§16)
vidgen thumbnail [PROJECT] [--variant NAME] [--preview] [--scene ID [--beat ID|N] [--at S] [--no-overlays]]
              [--jpeg] [--jobs N] [--json]                    # <output>_thumbnail.png (§53)
vidgen export gif|clip [PROJECT] [--scene ID] [--from S] [--to S] [--variant NAME] [--preview] [--width PX]
              [--fps F] [--max-mb MB] [--with-audio] [--output FILE] [--json]   # exports/ (§53)
vidgen slides [PROJECT] [--format html|pdf] [--variant NAME] [--preview | --final] [--mode beat|scene] [--per-beat N]
              [--overlays | --no-overlays] [--no-dedupe] [--image-format F] [--quality Q] [--max-width PX]
              [--audio] [--separate] [--notes] [--title-page] [--paper a4|letter]
              [--output FILE] [--jobs N] [--force] [--json]   # HTML deck (§55), PDF deck (§56)
vidgen translate-template [PROJECT] [--variant NAME] [--lang TAG] [--output FILE] [--json]   # translation file (§54)
vidgen readback [PROJECT] [--variant NAME] [--beat ID ...] [--max-wer RATE] [--force] [--json]   # STT check of the audio (§57)
vidgen imagegen [PROJECT] [--dry-run] [--force] [--scene ID ...] [--variant NAME]   # generated pictures (§58)
vidgen gallery [PROJECT] [--output DIR] [--types T,T] [--formats 16:9,9:16] [--theme PRESET]
              [--clips | --no-clips] [--jobs N] [--force] [--json]   # every scene type rendered (§60)
```
PROJECT defaults to the current directory. `--scene` re-renders only those scenes and re-joins
using the existing renders of the others (missing ones are rendered). Exit code non-zero on error.
`render` prints one line per scene, then the output paths and the total duration (Step 45: and
the measured loudness, §48).

## 9. Testing

- `pytest -q` must pass at every step. No network, no API keys.
- Tests that invoke Manim rendering are marked `@pytest.mark.render` and use tiny resolutions
  (e.g. 160x90 @ 5 fps); they run by default but can be skipped with `-m "not render"`. The
  slowest of them are also marked `slow` (Step 22): `-m "not slow"` is a quick full-coverage-ish run.
- ffmpeg is required on PATH for render tests; skip with a clear reason if missing.

## 10. Refinements (Step 7, independent review)

- **Audio length** (`scene.audio_duration`) = decoded samples / sample rate. The container
  duration depends on the PyAV/FFmpeg version: PyAV 13 (what Manim 0.19 pins, i.e. every
  Python 3.10 install) includes MP3 encoder padding, ~25–50 ms more per beat than PyAV 14+.
  Decoding gives identical timings everywhere (kphi3: unchanged with PyAV 19).
- **Dependencies**: `manim>=0.19` (the `code` scene uses the 0.19 `Code` API). Tested with
  Manim 0.19.1 / PyAV 13 on Python 3.10 and Manim 0.21 / PyAV 19 on Python 3.13.
- **Config**: `format`/`preview` `width` and `height` must be even (Manim's H.264 writer
  crashed with a segfault on odd sizes). Config files may start with a UTF-8 BOM (Windows
  Notepad) and use CRLF line endings.
- **Files on Windows** (`vidgen.fileio`): every output that may be open in another program is
  written to a temporary file and moved with `replace_file`, which retries for ~1.5 s
  (virus scanners) and then raises `VidgenError("cannot write X (...); is it open in another
  program...")`. Used for the final MP4 (the joined video is kept as `<name>.partial.mp4`),
  SRT, timings JSON, TTS MP3/hash files; the worker deletes a scene's old render with
  `remove_file` (same error). The CLI reconfigures stdout/stderr with
  `errors="backslashreplace"`, so a console with a legacy code page never crashes on a title
  or path; a closed pipe (`vidgen list-scenes | more`) ends quietly.
- **API key**: render worker processes get the environment without `ELEVENLABS_API_KEY` (scene
  code never needs it).
- **Extensions**: `beat_count` is validated when the class is registered (`VidgenError` naming
  the type); `SystemExit` raised while importing an extension is reported like any import error;
  an exception in (or a non-list returned by) `validate_project` is reported by `vidgen
  validate` as `scenes[i]: validate_project of scene type 'x' (<file>) failed: ...` and the
  other scenes are still checked; `register_theme_defaults(sizes=...)` requires positive
  numbers; bare `@scene` / `@hook` (no parentheses) raise a message showing the right form;
  hook tracebacks start at the hook. `render` also checks beat counts before starting workers.
- **CLI**: `vidgen list-scenes` prints the fields of nested `SceneParams` models indented
  under their field. `vidgen init` creates `assets/`, `extensions/` and a `.gitignore`
  (template files cannot start with a dot, because setuptools does not package dot files: the
  template stores `gitignore` and `init` renames it).

## 11. Refinements (Step 8, JSON output)

- **`--json`** on `validate`, `list-scenes` and `render` (`vidgen.cli.JSON_COMMANDS`): stdout
  holds exactly one JSON document (`vidgen.jsonout.dumps`: indented, `ensure_ascii=True`, so a
  legacy console code page cannot corrupt it); everything the command prints meanwhile is
  redirected to stderr (`contextlib.redirect_stdout`), and vidgen log warnings are both printed
  on stderr and collected into the document. Exit code 0 iff `ok`; 1 for errors; 2 for usage
  errors. Without `--json` the human output is unchanged.
- **Shapes** (`vidgen/jsonout.py`, reference: docs/CONFIG.md "JSON output"): envelope `{version,
  vidgen, command, ok, warnings: [{scene, message}], ..., error?: {kind, message, problems,
  details}}`. `version` is `jsonout.SCHEMA_VERSION` (1): keys may be added within a version;
  removing/renaming a key or changing a value's type bumps it. `error.kind`: `usage` (argparse
  error, `command` may be `null`), `error` (`VidgenError`), `internal` (any other exception;
  `details.traceback`). Paths are absolute, times are seconds.
- **Structured problems**: `vidgen.errors.Problem(location, message, variant=None)`
  (`str()` = the human line, `to_json()`), and `VidgenError(message, *, problems=(),
  details=None)` (both optional; existing calls unchanged). `config.validation_problems(err,
  prefix)` (`validation_error_lines` now derives from it); `parse_config` and
  `Project.load` (variant problems carry the variant) attach problems to their error.
  `cli.project_problems(project) -> list[Problem]`; `cli.check_project` keeps returning the
  same strings. A `validate_project` message `"<param>: <text>"` gets location
  `scenes[i].params.<param>`; other messages get `scenes[i].params`, and their human line is now
  `scenes[i].params: <message>` (was `scenes[i].params.<message>`, which read like a param
  name). `cli.validate_all(project, keep_going=False)`; with `--json`, a variant whose config
  does not load is reported as problems and the other variants are still checked (the human
  command still stops at it).
- **Render**: `RenderResult` gained `timings` (the combined timings), `render_seconds`
  (`{scene_id: wall seconds}` for scenes rendered in this run) and `warnings`
  (`[(scene_id, message)]` printed by workers, also collected when progress is shown live).
  Render failures raise `VidgenError(..., details={"failed": [{scene, exit_code,
  output_tail}], "rendered": [ids]})`.
- **Param docs**: `SceneParams` sets pydantic's `use_attribute_docstrings=True` (requires
  `pydantic>=2.7`), so a docstring under a field becomes its `description`, shown as `doc` by
  `list-scenes --json`; every built-in param has one. The scene type's `doc` is its class
  docstring, else its module's. The listing helpers moved from `cli.py` to
  `vidgen/describe.py` (`type_name`, `nested_models`, `describe_params`, `params_json`,
  `scene_type_json`).
- **Usage errors**: the CLI parser raises `cli.UsageError` instead of exiting; `main` prints
  argparse's usual `usage:` + `prog: error:` lines and returns 2 (so `main()` returns 2 rather
  than raising `SystemExit(2)`); `--help`/`--version` still exit through argparse.

## 12. Refinements (Step 9, JSON Schema export)

- **`vidgen schema [PROJECT] [--scene TYPE | --all] [--json]`** (`vidgen/schema.py`; reference:
  docs/CONFIG.md "JSON Schema"). Default: the schema of the whole `video.yaml`
  (`schema.config_schema(entries, themes)`); `--scene TYPE`: one type's params
  (`params_schema`, unknown type → `VidgenError` with the did-you-mean message); `--all`: one
  `scenes[]` item with every type's params (`scene_schema`). Draft 2020-12, generated from the
  pydantic models (`model_json_schema`, validation mode) and post-processed. Output is
  `jsonout.dumps` (indented, ASCII) on stdout; extension output during loading goes to stderr.
  With `--json` (now in `cli.JSON_COMMANDS`) the envelope holds `project` and `schema`.
- **Scene types** come from `cli.scene_types_session(path, lenient)` (also used by
  `list-scenes`): without a PROJECT and no config file in the current directory, built-ins
  only. `lenient=True` (schema): if the config does not load, `schema.lenient_project` loads
  the project from a placeholder config keeping the file's `extensions` and `theme` (each only
  if valid) and logs a warning; a missing project is still an error.
- **Per-type params**: `$defs/SceneConfig` gets `type: {enum: [registered names]}` and an
  `allOf` of `if {type: const NAME} then {params: $ref #/$defs/scene.NAME}` (plus `required:
  [params]` when the model has required fields, and `beats` `minItems`/`maxItems`/required from
  `beat_count`); a type without `Params` gets `{type: object}`. Nested models of a type are
  `$defs/scene.NAME.Model` (no collisions between types). Also encoded: the silent-scene rule
  (`if beats non-empty then duration null else duration required`), beat `id` optional/null,
  `variants` bodies (the top-level properties without `variants`, none required,
  `additionalProperties: false`), and `dict[Identifier, X]` as `propertyNames` +
  `additionalProperties` (pydantic's `patternProperties` alone let other keys through);
  `minLength`/`maxLength` pydantic puts on an `anyOf` (a union field's `min_length`) move to
  each branch as `minItems`/`minProperties`/`minLength` by the branch's type.
- **Theme tokens**: `ThemeToken` adds `"x-vidgen-theme": "color"|"size"` to the field's JSON
  Schema (`__get_pydantic_json_schema__`); the export replaces such a node's type by `anyOf`
  [hex pattern | positive number, `enum` of token names]. Token names are the union of the
  active theme (defaults + `register_theme_defaults` + `theme.*`) and every loadable variant's
  theme (`schema.project_themes`).
- **Config models**: `_Strict` uses `use_attribute_docstrings=True` and every config field has a
  one-line docstring (the schema's `description`); `FormatConfig.width/height` carry
  `multipleOf: 2` (`json_schema_extra`; the check stays the `_even` validator, same message);
  `config.Size` has an explicit `WithJsonSchema` (pydantic emitted a non-standard `gt` for the
  `int | float` union). Validation behaviour and messages are unchanged.
- **Not in the schema** (only `vidgen validate`): unique ids, referenced files,
  `validate_project`, Python validators. Values pydantic coerces (`"30"` for an int) pass
  `vidgen validate` but not the schema.
- `describe._doc` is now public as `describe.scene_doc(entry)`. `jsonschema` is a dev
  dependency (tests only).

## 13. Refinements (Step 10, frame capture)

- **Option**: `vidgen render --frames` (one still per beat, its last frame) or
  `--frames-per-beat N` (N evenly spaced stills per beat; implies `--frames`; N >= 1);
  `render_project(..., frames=N)` (0 = off, the default); worker flag `--frames N`. Off by
  default. Reference: docs/CONFIG.md "Frame stills".
- **Where stills are taken** (`vidgen.capture`): a `FrameCapture(per_beat, listeners)` is
  passed to the scene (`NarratedScene(..., capture=None)`, keyword-only, available as
  `self.capture`) and wraps `scene.renderer.add_frame`, the single point where Manim's Cairo
  renderer hands every frame (`num_frames` copies for a frozen wait) to the file writer. It
  counts frames written (skipped animations are not written and not counted), so a still's
  `frame` is its 0-based index in the scene's video and `time = frame / fps`. The wrapper calls
  the original unchanged and only reads the array (Manim passes a fresh copy), so frames,
  `renderer.time` and the beat log are identical to a render without capture (tested:
  identical per-scene timings and frame counts). `narrate()` calls `begin_segment(beat_id,
  round((d + pad) * fps), include_end=False)` on entry and `end_segment(beat_id)` after its
  wait: still `k < N` is planned on entry on the last frame before `k/N` of the beat
  (`capture.plan_targets`) and taken when that frame is written; still `N` is the last frame
  written when the beat ends (exact even if the beat's animations overran `d + pad`). A
  silent scene is one segment (`beat_id = None`) of `duration - outro` (at least one frame),
  planned with its end at construction; `tear_down` calls `finish()`, which takes planned
  stills never reached from the last frame. Stills of a short beat that fall on the same frame
  are merged (highest `k` kept).
- **Listeners** (the seam for Step 12 layout introspection): `capture.listeners` is a list of
  `CaptureListener = Callable[[NarratedScene, CapturedFrame], None]`, called at the moment the
  captured frame is written (mid-beat: inside `add_frame`, after Manim updated the mobjects to
  that frame; end of beat: right after the beat's wait), so `scene.mobjects`, the camera and
  `renderer` are in the state of that frame. `CapturedFrame(scene_id, beat_id, k, n, frame,
  time, pixels)` (`pixels`: H x W x 4 RGBA uint8). `StillWriter(folder)` is the listener that
  writes `<beat>-<k>.png` (`<scene>-<k>.png` for silent scenes; RGB PNG via Pillow, atomic)
  and builds the scene index.
- **Why from the renderer, not by decoding the MP4**: exact pixels and exact frame index (no
  H.264 loss, no seeking/rounding of times), no second pass over the video, works the same for
  every Manim/PyAV version, and it gives listeners the live scene state at the same moment
  (decoding the video afterwards could not). Cost: PNG encoding during the render (~ms per
  still at preview size).
- **Files** (`worker.scene_frames_dir`): `<render_dir>/frames/<scene>/` with the PNGs and
  `index.json` = `{scene, per_beat, width, height, fps, frames: [{beat, k, n, frame, time,
  path}]}` (time from scene start, path relative to the folder); the parent writes
  `frames/index.json` after joining (`pipeline.write_frames_index`) = `{title, variant,
  preview, format, per_beat, vidgen, scenes: [{id, start, duration, frames}]}` with `time` in
  the video, `scene_time` and `path` relative to `frames/`. The per-scene timings' `render`
  block records `frames` (stills per beat, 0 = none).
- **Staleness**: the worker deletes the scene's stills folder before every render (so stills
  always match the scene's current render; `worker.remove_tree`, a locked file is a
  `VidgenError`), and `render_project` deletes `frames/index.json` before rendering. With
  frames requested, `_usable_render` also requires the render's `frames` to equal the count
  and its index to exist, so `--scene ID --frames` renders other scenes again when they have no
  such stills. A scene a `pre_render` hook kept from rendering without matching stills gets an
  empty list in the combined index and a warning.
- **Outputs**: `RenderResult.frames_index` (`Path | None`); `vidgen render` prints `frames:
  <index>`; `render --json` `outputs.frames` (path or `null`; key added within version 1).

## 14. Refinements (Step 11, storyboard)

- **`vidgen storyboard [PROJECT] [--scene ID ...] [--per-beat N] [--variant NAME] [--preview |
  --final] [--width PX] [--jobs N] [--force] [--json]`** (`vidgen/storyboard.py`
  `make_storyboard(project, *, preview=True, scenes=None, per_beat=1, width=1280, jobs=1,
  force=False) -> StoryboardResult`; reference: docs/CONFIG.md "Storyboard"). Preview format by
  default. Writes `<render_dir>/storyboard/video-<p>.png` (whole video; not with `--scene`) and
  `storyboard/scenes/<scene>-<p>.png`, `p` = page 1, 2, ... The folder is cleared first (with
  `--scene`: the video pages and those scenes' pages), so no stale sheet survives.
- **Built on Step 10's stills**: for each selected scene, `storyboard.stills_current(project,
  preview, scene_id, per_beat)` checks the scene's timings (format, `render.frames ==
  per_beat`, `render.fingerprint`), its `frames/<scene>/index.json` and PNGs. Scenes that fail
  (or all selected with `force`) are rendered by `pipeline.render_scenes(project, preview, ids,
  jobs, frames)`: the same workers as `render_project` (`_render_scenes`, renamed result type
  `SceneRuns`), with audio, dispatching `post_scene` but not `pre_render`/`post_render`, no join;
  it removes the combined `frames/index.json` when it renders anything. Stills are then read
  from the per-scene indexes and timings (beat texts); a still's video time uses scene starts
  summed from the per-scene timings' durations (`null` if a scene has no render at the format).
- **Fingerprint** (`vidgen/render/fingerprint.py`, `scene_fingerprint(project, scene_id)`): a
  SHA-256 over the scene's config entry, the config minus `scenes`/`variants`/`lint` (Step 13; the entry without `lint_ignore` and, Step 39, `chapter`) (with the variant
  applied), the beats' MP3 size+mtime, the contents of the `.py` files of the extension folders,
  size+mtime of the files under `<root>/assets`, the vidgen version and a digest of vidgen's own
  source except `NOT_RENDER_INPUTS` (CLI, JSON, schema, sheets, storyboard, pipeline, ffmpeg,
  subtitles, tts: modules that cannot change pixels or timing; new modules count by default).
  The worker computes it before rendering and stores it as `render.fingerprint` in the scene's
  timings (key added; older renders have none and count as stale). `vidgen render` does not use
  it (it re-renders what it is asked to, as before).
- **Sheet layout** (`vidgen/sheets.py`, `compose_pages(title, subtitle, scenes, frame_size, *,
  width, detail, video_times, max_height) -> list[SheetPage]`): white page, a title line and a
  line saying what stills/times mean; per scene a grey header band `N/M  id · type ·
  start–end (duration)` (details dropped when narrow); stills of a beat side by side (a
  *block*), each labelled `beat @ time` (`k/n @ time` with several per beat, the beat id then
  prefixes the narration), the narration wrapped under the block (4 lines on video sheets, 6 on
  scene sheets, `…` when cut). Columns: 16:9 → 4 (scene sheets 2), ~square → 5 (3), 9:16 → 5
  (4); with N stills per beat the multiple of N nearest to that (≤ 8). Scenes that fit in the
  rest of a row share it. Pages are `width` px wide (640–2000, default 1280; font sizes scale
  with it) and at most about `1.25 x width` high, balanced so the last page is not nearly
  empty; a scene continued on a new page repeats its header marked `(continued)`. Fonts: Inter,
  else DejaVu Sans / Arial / Liberation Sans / Helvetica, else Pillow's built-in font.
- **Why these sizes**: an AI agent sees the PNG through an image tool that downsizes large
  images (around 1.2 megapixels / 1568 px long edge); at 1280 px wide the 19 px labels and
  narration stay readable after that, which one huge image of the whole video would not.
- **JSON** (`jsonout.storyboard_document`, `storyboard` in `cli.JSON_COMMANDS`): `project,
  variant, preview, per_beat, format, folder, rendered, reused, elapsed, sheets: [{kind
  (video|scene), scene, page, pages, path, width, height, frames: [{scene, beat, k, n, time,
  scene_time, path}]}]`.

## 15. Refinements (Step 12, layout introspection)

- **What**: whenever stills are captured (worker `--frames N`, so `render --frames`,
  `--frames-per-beat` and `storyboard`), `vidgen.introspect.LayoutRecorder` — a second
  `FrameCapture` listener next to `StillWriter` — describes the same frames as data and the
  worker writes `<render_dir>/layout/<scene>.json` (`worker.scene_layout_path`). Not behind a
  separate flag: it costs ~50 ms per 1080p still (measured on kphi3; negligible next to the
  render), and stills and layout then always come from the same render. It is the input of
  Step 13's `vidgen lint` (§16). Reference: docs/CONFIG.md "Layout dump".
- **Format** (`LAYOUT_VERSION = 1`): `{version, scene, type, width, height, fps, per_beat,
  px_per_unit, background, safe_area: [x0, y0, x1, y1], frames: [{beat, k, n, frame, time,
  still, camera: {center, width, height}, objects}]}`; frames carry the stills index keys and
  `still` (`../frames/<scene>/<file>`, relative to the layout file; `capture.still_name`).
  Objects: `{id, kind, class, path, name, bbox, opacity, z, order, parts}` plus, for text kinds
  (`text|code|math|number`), `{text, font_px, color, colors, backdrop}` and otherwise
  (`shape|group|image|icon`) `{fill: {color, opacity}|null, stroke: {color, opacity,
  width_px}|null}`; kind `icon` (Step 19, §22) also has `icon` (the name). Pixels: output frame, origin top-left, y down, frame `[0,W] x [0,H]`,
  1 decimal. Colours `#RRGGBB`.
- **Measuring**: points go through the scene's own `camera.points_to_subpixel_coords`, so a
  `MovingCamera` frame (zoom/pan) is honoured. VMobject curves are sampled at 5 parameters per
  cubic (anchors+handles would overstate round glyphs); visible strokes widen the box by half
  their width (`stroke_width * camera.cairo_line_width_multiple` units). Images: their corner
  points, opacity = max alpha of the pixel array. Visibility per drawn leaf: max of fill alpha
  and (if `stroke_width > 0`) stroke alpha; leaves at 0 are ignored, objects without a visible
  leaf are not listed (fade-ins show as fractional `opacity`).
- **Grouping** (walk of `scene.mobjects`): text mobjects (`Text`, `MarkupText`, `Paragraph`,
  `SingleStringMathTex` = `Tex`/`MathTex`, `DecimalNumber`) are one object; inside a `Code`,
  paragraphs are kind `code` (Manim's invisible alignment suffix ` pA<n>` removed from `text`)
  and the background is a shape; a group whose family has no text or image is one `group`
  object (fill/stroke of its largest part); other groups are walked into; a group drawing
  points itself also yields a `shape`. Each mobject is visited once.
- **Identity**: `id` = `m<N>` per Python object for the whole scene (the recorder keeps the
  objects alive so `id()` is never reused); `path` = parent chain of `Class[index]` segments,
  replaced by the name where the scene named a mobject (a public attribute of the scene, or a
  `Mobject.name` other than the class name).
- **Sizes and colours**: `font_px` = 75th percentile of the visible glyph heights (outline,
  output px): ≈ cap height for mixed case, x-height for all-lowercase-without-ascenders text;
  robust to punctuation and to one large glyph, and works the same for Tex. `backdrop` = the
  most common exact colour inside the text box in the captured frame, after dropping pixels
  within RGB distance 60 of the text's own colours (unless that leaves < 5 %; boxes are
  subsampled to ≤ 40 000 pixels; colours are grouped in 5-bit bins first so anti-aliasing does
  not split the vote). `order` = position of the object's top-most part in Manim's draw order
  (`extract_mobject_family_members` with z-index).
- **Staleness/reuse**: the worker deletes the layout file before every render (like the stills);
  `pipeline._usable_render` with frames requested also requires it; `frames/index.json` scene
  entries gain `layout` (`../layout/<id>.json` or `null`). `introspect.py` counts in the scene
  fingerprint (it changes the layout output).
- **Limits**: `text` is the string the mobject was built with (Manim's `become`/`Transform`
  keep it; the built-in `bar_chart` counter now updates it); during
  `TransformMatchingShapes`/`TransformMatchingTex` loose glyphs are shapes; while Manim's Cairo
  renderer animates, moving mobjects are drawn over static ones regardless of z-index, which
  `order` does not model; 3D cameras are only as right as `transform_points_pre_display`.

## 16. Refinements (Step 13, `vidgen lint` layout rules)

- **Command**: `vidgen lint [PROJECT] [--scene ID ...] [--rule NAME ...] [--variant NAME]
  [--preview | --final] [--fail-on error|warning|info|never] [--jobs N] [--force] [--json]`
  (`vidgen.lint.lint_project(project, *, preview=True, scenes=None, rules=None, fail_on=None,
  jobs=1, force=False) -> LintResult`; reference: docs/CONFIG.md "Lint"). Exit code 1 iff a
  finding is at least as severe as `fail_on` (`--fail-on`, else `lint.fail_on`, default
  `error`); with `--json` that document has `ok: false` and `error.kind` `error` (`details:
  {fail_on, counts}`) and still lists every finding.
- **Input**: the layout dumps (§15) of the **beat-end stills** (`k == n`) only: mid-beat stills
  show fades and motion in progress, which would be noise. Stills are reused when
  `storyboard.stills_current(project, preview, scene, per_beat=None)` holds (now: any stills
  count, and the layout file must exist); other scenes are rendered with one still per beat
  by `pipeline.render_scenes` (as the storyboard does). Objects below `lint.min_opacity`
  (0.1) are dropped first (the end of a fade).
- **Framework** (`vidgen/lint/rules.py`): `@rule(name, scope="still", default=severity)`
  registers `check(context, settings) -> Iterable[Issue]` in `RULES`; `name` must be in
  `config.LINT_RULES`, whose order is `RULES`' order, and `config.LintRules` has one settings
  model per rule (subclass of `RuleConfig`: `severity: error|warning|info|off|None`); a test
  keeps the three in sync. `Issue(message, bbox, objects=(), severity=None, value=None,
  limit=None, group=None)`. Scope `still` gets a `StillContext(layout, frame, objects, still)`
  (`width`, `height`, `short_side`, `region(box)` = the still's RGB pixels, read lazily).
  Step 14's timing rules use scope `scene` (§17); findings, config, ignores and report are
  shared.
- **Severity** of a finding: the rule's configured `severity`, else the issue's own (rules
  escalate: `off_frame` error for text / warning otherwise, `min_font` error below
  `error_size`), else the rule's default. `off` skips the rule.
- **Merging** (one problem, one line): findings of a scene with the same rule, severity and
  object ids are merged across beats (`beats` lists them, the first gives `beat`, `time`,
  `still`); then findings first seen at the same still with the same rule, severity and
  `group` (default: the object's parent path, e.g. an axis' tick labels; `contrast` groups by
  colour, backdrop and opacity) become one finding with the others in `similar` and `also N
  more like it (...)` in the message. Order: scenes in config order, then scene time,
  severity, rule order.
- **Sizes** are fractions of the frame's **shorter side** (`StillContext.short_side`), not the
  height: equal for landscape, and for 9:16 the height would make the same text count 1.78x
  smaller, although a phone shows either orientation with its shorter side across the screen.
- **Rules** (thresholds in `config.LintRules`, defaults documented in docs/CONFIG.md):
  `off_frame` (bbox beyond the frame by > `tolerance` 0.004; wholly outside objects skipped;
  non-text objects spanning an axis edge to edge are intentional bleeds on that axis: cover
  images, Ken Burns, backgrounds, bands), `safe_area` (text only, inside the frame but past
  the layout's `safe_area` by > `tolerance` 0.01), `text_overlap` (intersection ≥
  `min_overlap` 0.1 of the smaller box; identical text with IoU > 0.9 skipped), `covered_text`
  (a non-text object drawn later (`order`) whose fill/stroke colour, blended at its opacity
  over the text's backdrop, shows in ≥ `min_covered` 0.02 of the middle of the text's box,
  counted on the still's pixels, excluding pixels of the text's own colours; skipped: the
  text's ancestors, shapes below opacity 0.3, shapes whose colour is within RGB distance 40
  of the text or backdrop colour (a strike-through); images: their box), `min_font` (cap
  height < `min_size` 0.025 → warning, < `error_size` 0.018 → error; cap height =
  `font_px * 0.73 / p75(per-character em heights)` with x-height letters 0.55, descender
  letters 0.76, punctuation 0.15, others 0.73, so all-lowercase text is not penalised; math
  uses `font_px`; text without a letter or digit skipped), `contrast` (WCAG 2 ratio of each
  text colour blended at the text's opacity over `backdrop`, worst colour counts; needs
  `min_ratio` 4.5, `large_ratio` 3 when the cap height ≥ `large_size` 0.045, `dimmed_ratio`
  2 when opacity < 0.95 (de-emphasised on purpose); a `code` object of only digits (line
  numbers) skipped), `max_words` (> `max_words` 40 tokens with a letter in `text` objects; code,
  math and numbers do not count; `object` null, `bbox` the union).
- **Config**: `VideoConfig.lint: LintConfig` (`fail_on`, `min_opacity`, `rules`) and
  `SceneConfig.lint_ignore: list[RuleName | "all" | LintIgnore]` (`LintIgnore(rule, object,
  beat)`; `beat` must be a beat of the scene; `SceneConfig.lint_ignores()` normalises).
  `object` is matched with `*`/`?` wildcards only (brackets literal, so paths like
  `VGroup[2]/*` work) against the object's name, path and text (either object of a pair).
  Both are excluded from the render fingerprint (`fingerprint.scene_fingerprint`), and the
  `lint` package is in `NOT_RENDER_INPUTS`.
- **Output**: `Finding.to_json()` = `{scene, beat, time, scene_time, rule, severity, object,
  other, similar, bbox, message, value, limit, beats, still}` (objects as `{id, kind, class,
  name, path, text, bbox}`); `jsonout.lint_document` adds `{project, variant, preview,
  format, fail_on, rules, scenes, stills, rendered, reused, elapsed, counts, ignored,
  findings}` to the envelope. Human report (`lint.report_lines`): a header, findings grouped
  by scene (`severity rule beat @ t (+N more beats): message` + `still: <path>` relative to
  the current folder), a count line and `failed: ...` when failing.
- **Limits**: only beat-end stills; boxes are rectangles (rotated text, curves); `opacity` is
  the max over an object's parts, so per-line dimming inside one `Paragraph`/`Code` is not
  seen; `text` may be stale after `Transform` (§15), so messages can quote the old string
  (the still and `bbox` are right); `backdrop` is the most common colour, approximate over
  busy images.

## 17. Refinements (Step 14, timing lint)

- **Rules** (`vidgen/lint/timing_rules.py`, scope `scene`, all default `warning`):
  `narration_speed`, `dead_air`, `animation_overrun`, `rushed_animation`; settings models
  `NarrationSpeedRule`, `DeadAirRule`, `AnimationOverrunRule`, `RushedAnimationRule` in
  `config.LintRules` (names added to `LINT_RULES`/`RuleName`); defaults and the rule table in
  docs/CONFIG.md "Lint". Same command, report, JSON, `lint:` config and `lint_ignore` as §16.
- **Framework**: `Scope = "still" | "scene"`. A `scene` rule gets `SceneContext(scene_id,
  activity, audio_dir)` (`fps`, `beats`, `beat_at(t)`: the beat whose start ≤ t, pad
  included) once per scene and yields `Issue`s with the new fields `beat` (`None` in a silent
  scene) and `time` (scene seconds). The runner (`run._timing_findings`) makes one finding per
  issue (`still` = the beat-end still of `beat`, `bbox` and `object` null); issues sharing a
  `group` become one finding with all their `beats`. `Finding.still` may be `None` (report and
  JSON handle it). Human report: rule column widened to 17 characters.
- **Input: the activity file** (`vidgen/activity.py`, `ACTIVITY_VERSION = 1`,
  `worker.scene_activity_path` = `<render_dir>/activity/<scene>.json`), written by the worker
  whenever stills are captured, deleted before every render like the stills and layout;
  `storyboard.stills_current` and `pipeline._usable_render` (with frames) require it, so
  renders from before Step 14 count as stale; `frames/index.json` scenes gain `activity`.
  Content: `{version, scene, type, fps, frames, duration, pad, silent: {duration, busy} |
  null, beats: [{id, start, end, busy, source: audio|estimate, text}], plays: [{start, end,
  beat, animations, wait, requested}], motion: {step, grid, level, changes: [[frame,
  fraction]]}}` (docs/CONFIG.md "Activity file").
- **Play log** (`NarratedScene.play` overrides Manim's to append a `PlayRecord`; Manim's `wait`
  goes through `play`, so waits are recorded with `wait: true`). `narrate()` sets the current
  beat for the log and stores `beat_busy[id]` = time its body took before the wait up to
  `d + pad`; `tear_down` stores `silent_busy` before holding a silent scene. `play_steps` marks
  the plays it shortened with `requested = cap`. Recording never changes frames or timing.
- **Motion signal — why from the renderer**: `MotionTrack` is fed by `FrameCapture._observe`
  (`FrameCapture(per_beat, listeners, motion=None)`), which already sees every frame Manim
  writes, with `num_frames` for frozen waits. Each written frame is sampled on a grid (every
  `step = ceil(short side / 180)`-th pixel: 3 at 480p, 6 at 1080p) and compared with the
  previous one; `fraction` = share of sample points with a channel moved by > 6 (0-255);
  only changed frames are stored. ~1.3 ms per written frame (a frozen wait is one), a few
  percent of a preview render. Decoding the scene MP4 with ffmpeg/PyAV afterwards would be a
  second pass, add codec noise (every frame "changes" slightly, needing a fuzzy threshold) and
  could not run without the MP4; the renderer's frames are exact (a static frame is
  bit-identical), so a tiny threshold works. Only recorded with stills (`--frames`,
  storyboard, lint), which is when lint needs it.
- **`narration_speed`**: spoken words (`timing_rules.spoken_words`: hyphens/dashes/slashes
  split words; digit runs `min(len, 3)` words, `+1` per decimal separator and symbol, `+1` for
  letters next to digits; 2-5 letter all-caps acronyms half a word per letter) per second of
  speech: with an MP3, its length minus leading/trailing silence (10 ms envelope below -40 dB
  of the peak; `speech_bounds`, cached by path+mtime); without audio, the estimated `d`, so
  the rate only deviates where spoken words differ from `len(text.split())` or the configured
  `words_per_second` is itself outside the range: those findings are `info`, grouped into one
  per scene. Beats under `min_words` (5) spoken words are skipped.
- **`dead_air`**: static runs between changed frames (`fraction >= min_change`, default 0.0002
  ≈ 9 sample points, which ignores the near-zero first/last frames of eased animations), the
  tail to the scene end included, longer than `max_seconds` (6). Applies to narrated and
  silent scenes alike (a silent card held still longer than 6 s is reported); the beat is
  where the run starts.
- **`animation_overrun`**: `busy - (d + pad) > tolerance` (0.1 s); the message lists the
  non-wait plays of the beat ending after the narration end. Silent scenes: `silent.busy >
  duration + tolerance`. `time` = narration end (or `duration`).
- **`rushed_animation`**: plays with `requested` set whose run time is below `min_run_time`
  (0.5 s), one finding per beat. Plays a scene shortens itself (e.g. `run_time=d / 5`) are not
  seen: only `play_steps` says what it wanted.

## 18. Refinements (Step 15, layout regions)

- **Module** `vidgen/regions.py`, exported by `vidgen.api`; reference: docs/EXTENDING.md
  "Layout regions". `Region(x0, y0, x1, y1)` (frozen dataclass, Manim units, y up; negative
  sizes are a `VidgenError`): `width`, `height`, `center`, `orientation`, `point(align)`,
  `contains(mob, tolerance)`, `inset(x, y)`, `below(mob_or_y, gap)` / `above(...)` (clamped,
  may have zero height), `rows(n | weights, gap)` (top to bottom), `columns(...)` (left to
  right), `split(...)` (columns, or rows when the **active frame** is portrait), `grid(rows,
  cols, gap, gap_y)` (row-major cells), `to_rectangle()`. Default gap `GAP = 0.3` units.
- **Frame and safe area**: `frame_region()` from `config.frame_width/height` (shorter side 8,
  §5.2); `safe_area(margin_x=MARGIN_X, margin_y=MARGIN_Y)` (0.6 / 0.5). Single source of truth:
  `NarratedScene.margin_x/margin_y` default to those constants, `NarratedScene.safe_area` is
  `regions.safe_area(self.margin_x, self.margin_y)` (`safe_width`/`safe_height` derive from
  it), and the layout dump's `safe_area` (§15), which lint's `safe_area` rule reads, is built
  from the same function (`introspect.LayoutRecorder.document`), so values are unchanged.
- **Orientation**: `orientation(w, h)` = `landscape` if w > 1.2 h, `portrait` if h > 1.2 w,
  else `square`.
- **Named regions** (`region(name, area=None, gap=GAP)`; `NarratedScene.region(name)` uses the
  scene's safe area): `full`; `header` (top band, height share of the area 0.16 landscape /
  0.15 square / 0.12 portrait); `caption` (bottom band 0.12 / 0.11 / 0.09); `body` (below the
  header, gap apart); `hero` (between header and caption); `top` / `bottom` (halves);
  `left` / `right` (`area.split(2)`: halves side by side, **but the upper/lower half in
  portrait**, so a two-column layout written for 16:9 becomes two rows in 9:16; literal halves:
  `area.columns(2)`); `center` (centered box, shares of width x height 0.72 x 0.72 / 0.86 x
  0.72 / 1.0 x 0.6). Unknown names → `VidgenError` listing `REGION_NAMES`.
  `grid(rows, cols, area="full", gap, gap_y)` takes a name or a Region.
- **`place(mob, area, fit="contain", align="center", *, max_scale=None, buff=0.0)`**: `contain`
  scales up or down to fit both sides, `width`/`height` match one side (the other may
  overflow), `none` keeps the size; zero-size sides are ignored; `max_scale` caps the factor
  (`1.0`: shrink only). `align` is one of `ALIGNMENTS` (`center, top, bottom, left, right,
  top_left, top_right, bottom_left, bottom_right`; spaces/hyphens accepted) or a Manim
  direction (`UL`, only its signs count): the mobject's matching edge/corner goes on the
  region's (`move_to(point, aligned_edge=...)`). Unknown fit/align → `VidgenError`.
- **Readable size**: `readable_size(font=None, *, fraction=None, margin=1.05)` = the font size
  (points) whose capital `H` is `fraction` of the frame's shorter side, times `margin`.
  `fraction` defaults to `min_text_fraction()`: the active project's
  `lint.rules.min_font.min_size` (default `MIN_TEXT_FRACTION = 0.025`), so layout and lint
  share the threshold; that one lint value is therefore part of the render fingerprint (key
  `readable`), while other lint settings still are not. Inter and the default `Monospace`
  (JetBrains Mono NL since Step 18) measure ≈ 0.0101 units of cap height per point → ≈ 20.8 pt at any resolution (theme `small`
  20 is below it, `caption` 24 above, matching what lint reports).
- **`readable_text(text, area, *, size="body", min_size=None, theme=None, **fit_text_kwargs)`**:
  `fit_text` into the region starting at `max(size, floor)` with `min_size = floor =
  max(readable_size(), min_size)`, so long text wraps instead of shrinking; if it still does
  not fit the height it is scaled down (as `fit_text` does) and a warning is logged on
  `vidgen.regions` (shown as `warning:` by the worker). Not positioned. Built on
  `layout.fit_text_sized` (new, internal: `fit_text` returning the final font size after any
  scaling; `fit_text` delegates to it, behaviour unchanged).
- **Built-ins on regions**: `bullets` — heading fitted into and centered in `header`, list
  centered in `safe_area.below(heading)`; in portrait the heading is `portrait_growth` (1.3,
  class attribute) larger, a short list (≤ 5 items, rows < 75 % of the space) grows up to 1.3x
  and rows are spaced 0.8 x the line pitch (0.55 in landscape). `code` — title in `header`,
  listing scaled into the rest (up to 1.5x, as before); new param `wrap: bool = True`: while
  the listing is width-bound and would end below `max(size, readable_size(font))`, long lines
  are wrapped (`scenes/code.py` `wrap_code(lines, columns)`: break after the last space/comma
  outside a string literal if past half the line, else after an opening bracket, else any
  space, else hard; continuation lines indented 4 more; never narrower than `MIN_COLUMNS` 20)
  and the listing rebuilt. Wrapped listings number original lines only (continuation numbers
  replaced by empty groups; the dumped `text` of the number column is still Manim's string)
  and highlights map original lines to all their wrapped lines. Landscape output of both is
  unchanged except the title/heading now centered in `header` (a few px lower).

## 19. Refinements (Step 16, theme presets)

- **Config**: `ThemeConfig` gains `preset: Identifier | None` and `code_style: str | None`
  (a Pygments style, checked against the installed styles); `background` and `font` now default
  to `None` (= "not written"), so a preset can supply them. Variants deep-merge as before, so a
  variant `theme: {preset: NAME}` switches the preset while base `theme:` values still apply
  (and still win). Reference: docs/CONFIG.md "Theme presets".
- **Precedence** (highest first, `Theme` in `theme.py`): `video.yaml` `theme.*` > the preset
  (`preset_chain()`: the preset, below it its `base`, recursively) > `register_theme_defaults`
  > built-in defaults. For `colors`/`sizes` the layers merge per token; `background`, `font`,
  `code_style` and `palette` take the highest layer that sets them. Without `theme.preset` the
  preset layer is empty, so output is unchanged for existing projects (the built-in defaults are
  the `dark_tech` values). Rationale: a preset is an explicit choice in the config, so it beats
  defaults an extension registered in code, but never a value written in the config.
- **Presets** (`vidgen/presets.py`, `ThemePreset` frozen dataclass: `name, description, base,
  background, font, code_style, colors, palette, sizes, origin`; `None`/empty = not set):
  `BUILTIN_PRESETS` = `dark_tech` (= the defaults), `light_academic` (off-white `#F8F7F3`,
  near-black text, ink accents, white `surface`, `code_style: xcode`), `high_contrast` (black,
  white text, saturated accents ≥ 7:1, `caption` 26 / `small` 24). Values: docs/CONFIG.md table
  (a test keeps it in sync). `DEFAULT_*` constants moved here (`vidgen.theme` re-exports them).
- **Default `dim` changed** from `#6B7280` (3.91:1 on `#0E1116`, below WCAG AA; every dim
  caption was a lint `contrast` warning) to `#838B98` (5.5:1 on the background, 5.0:1 on
  `surface`): a visible change, dim text is slightly lighter.
- **Project presets**: `vidgen.api.register_theme_preset(name, *, base, background, font,
  colors, palette, sizes, code_style, description)` → `presets.make_preset` (validates names,
  hex colours, positive sizes, Pygments style) → `Theme.add_preset` (error on a built-in name,
  a duplicate, or an unknown `base`). Stored on the active `Theme`, so they are per project like
  `register_theme_defaults` (every `activate` builds a fresh Theme). Presets are looked up when
  a value is read; an unknown name raises `VidgenError("unknown theme preset ...; known
  presets: ...")`. `Theme.derive(config)` builds a variant's theme sharing the registered
  defaults and presets (used by `schema.project_themes`).
- **Validation/schema**: `vidgen validate` reports an unknown preset as `theme.preset: ...`
  (and skips the scene checks, which all need the theme); `vidgen schema` gives `preset` an
  `enum` of the built-in and project presets (`schema.theme_presets`) and `code_style` an
  `enum` of the installed Pygments styles.
- **Contrast check** (`vidgen/lint/color.py`): `theme_contrast(theme, *, text_ratio=4.5,
  graphic_ratio=3.0) -> list[ContrastCheck(subject, color, against, against_color, ratio,
  minimum)]` (`.ok`): `text`/`dim` on the background and on `surface` need 4.5:1 (WCAG AA
  text), the accent tokens (`accent, highlight, primary, secondary, tertiary`) and the palette
  3:1 on the background (WCAG 1.4.11 graphical objects / large text). Tests run it on every
  built-in preset. `hex_rgb` now accepts `#RGB` and `#RRGGBBAA` (alpha ignored).
- **Built-ins on light backgrounds**: no built-in hard-codes white/black; colours come from
  theme tokens and the image caption band from `theme.background`. Changed: `code` `style`
  defaults to `None` = `theme.code_style` (a dark style on a white window was unreadable);
  `bullets` dims earlier items to `dimmed_opacity = 0.45` (was 0.4: a dimmed `primary` marker
  on `light_academic` was 1.9:1, under lint's 2:1 for de-emphasised text).

## 20. Refinements (Step 17, more presets and type scales)

- **Type scales** (`vidgen/scales.py`, manim-free): `TYPE_SCALES` `compact` (48/36/32/28/22/20
  for title/subtitle/heading/body/caption/small), `standard` (56/42/36/32/24/20 = the built-in
  `DEFAULT_SIZES`), `large` (66/50/44/38/30/26); `auto` = `AUTO_SCALES[orientation]` (`large`
  for portrait, `standard` for landscape/square). `frame_orientation(w, h)` is the classifier
  (`regions.orientation` now delegates to it). No scale goes below `small` 20 (the lint
  `min_font` floor is ≈ 19.8 pt).
- **Config**: `ThemeConfig.scale: Literal["compact", "standard", "large", "auto"] | None`;
  presets gain `scale` and `fonts` (`ThemePreset`, `make_preset`, `register_theme_preset`).
- **Theme orientation**: `Theme(config, *, orientation="landscape")`, `Theme.for_format(config,
  fmt)` (used by `runtime.set_context` and `NarratedScene` with the project's **final**
  `format`, so preview and final render share sizes), `derive(config, fmt=None)` (variants:
  `schema.project_themes` passes the variant's format). `Theme.scale_setting` (as chosen),
  `Theme.scale` (resolved).
- **Size precedence**: a scale is shorthand for the six sizes at the level where it is chosen.
  `Theme.sizes` = base, then registered extension sizes, then per preset in the chain (lowest
  first) its scale's sizes then its `sizes`, then the config's scale's sizes, then the config's
  `sizes`. The base is `DEFAULT_SIZES` when any level chooses a scale, else the `auto` scale for
  the orientation — so with no scale anywhere, extension defaults still override the built-in
  sizes (as in Step 16), while a chosen scale overrides them for the six scale tokens (like a
  preset's colours override extension colour defaults). **Visible change**: portrait projects
  that choose no scale get `large` sizes (was standard); landscape output is unchanged.
  Built-in scenes fit text into regions, so larger sizes wrap/shrink rather than overflow
  (checked: storyboard + lint of examples/minimal `--variant vertical`, render test at 9:16).
- **Font roles hook**: `ThemePreset.fonts` (role → family, roles are identifiers);
  `Theme.fonts` merges the chain, `Theme.font_for(role)` = `video.yaml` `font` if written, else
  the chain's family for the role, else `Theme.font`. No built-in preset sets roles and no
  built-in scene reads them yet (Step 18 bundles serif/mono fonts and wires them; §21 changes
  the precedence: a config `font` no longer overrides roles).
- **Presets**: `BUILTIN_PRESETS` (built through `make_preset`, so validated at import) adds
  `warm_editorial` (cream `#F6F0E4`, espresso text, petrol/terracotta, Pygments `default`),
  `brand_neutral` (grey `#F4F5F7` with white `surface`, graphite text, one blue, `xcode`),
  `soft_pastel` (dusky plum `#252238`, pastel accents, `zenburn`) and `bold_neon`
  (violet-black `#0B0614`, cyan/magenta/yellow, `monokai`, scale `large`). Every built-in preset
  sets a `scale` (`auto`, `high_contrast` and `bold_neon` `large`) and no `sizes`;
  `high_contrast` dropped its `caption: 26, small: 24` for `large`. Values: docs/CONFIG.md table
  (test keeps it in sync). Code styles were chosen so every Python token colour reaches 4.5:1
  on the preset's `surface`.
- **Palettes**: 4–6 ordered colours; every built-in palette colour reaches 4.5:1 on its
  background (charts draw series labels in palette colours; the first draft of the light
  presets got lint `contrast` warnings on line-chart labels at 3.9:1). Colour-blind check
  `vidgen.lint.color.palette_distinctness(palette) -> {vision: min CIEDE2000}` for `normal` and
  simulated `protanopia`/`deuteranopia`/`tritanopia` (Machado et al. 2009 full-severity
  matrices on linear RGB; `simulate_cvd`, `lab`, `delta_e` = CIEDE2000). Built-in presets
  except `dark_tech` reach ≥ 7.5 under all four (tested); `light_academic` and `high_contrast`
  changed their third colour to reach it (deuteranopia 2.5 → 11.9 and 0.4 → 8.8); `dark_tech`
  keeps the historical default palette (deuteranopia 4.7) so default output does not change.
- **`vidgen list-themes [PROJECT] [--swatches PNG] [--json]`** (`themelist.py`, not a render
  input): per preset (built-in then project) `preset_entry`: values resolved in the project
  (`Theme.derive(ThemeConfig(preset=name))`, so registered defaults and the project's
  orientation apply), `theme_contrast` summary and `palette_distinctness`; plus the type scales.
  JSON: Step 8 envelope, command `list-themes`, documented in docs/CONFIG.md. `--swatches`
  draws one 1280x190 row per preset with Pillow (name/description in its text colours, accent
  chips, `surface` panel, palette bars).
- **`vidgen validate`** logs `theme_contrast` failures of the project's theme (and of each
  variant's, prefixed `[variant]`, unless equal to the base's) as warnings: stderr
  `warning: theme contrast: ...`, JSON `warnings`; they never fail validation.

## 21. Refinements (Step 18, bundled fonts)

- **Bundled families** (package data `src/vidgen/data/fonts/<Family>/`, each with its `OFL.txt`;
  `THIRD_PARTY_NOTICES.md` lists sources, versions and sizes; `pyproject` package-data
  `data/fonts/**/*`): Inter 4.001 (`Inter`: Regular, Bold, Italic), Source Serif 4 4.005
  (`Source Serif 4`: Regular, Bold, Italic), JetBrains Mono NL 2.242 (`JetBrains Mono NL`:
  Regular, Bold; the no-ligature variant, so code shows the typed characters). ~2.0 MB of TTF,
  ~1.1 MB in the wheel. All SIL OFL 1.1, unmodified (Inter/JetBrains Mono decompressed from
  WOFF2, lossless).
- **Registration** (`vidgen/fonts.py`): `register_bundled_fonts()` calls
  `manimpango.register_font` for every file (Linux: fontconfig app font; Windows:
  `AddFontResourceEx` private; macOS: CoreText), once per process, and clears Manim's cached
  `Text.font_list` so its missing-font warning knows them. Pango reads registered fonts when it
  builds its font map (the first text laid out), so registration must precede any text:
  `vidgen.helpers` and `vidgen.regions` call it at import (every vidgen text path imports one
  of them; extensions import them through `vidgen.api`), and the worker calls it first in
  `render_scene`. A file that fails to register is a logged warning (text then uses an
  installed font of that name or Pango's fallback), never an error. A family that is also
  installed system-wide is found twice by fontconfig; either copy renders it (same font).
  Pillow contact sheets and `list-themes --swatches` also prefer the bundled Inter files.
- **Theme tokens**: `font` (sans; default Inter), `font_serif` (default Source Serif 4) and
  `font_mono` (default JetBrains Mono NL), each with the usual precedence (config > preset chain
  > default; `ThemeConfig`, `ThemePreset`, `make_preset`, `register_theme_preset` gain
  `font_serif`/`font_mono`). Config `theme.fonts: {role: token-or-family}` (new, merged per role
  over the preset chain's `fonts`).
- **Font roles** (`Theme.font_for(role)`): setting = config `fonts[role]` > preset chain
  `fonts[role]` > `fonts.ROLE_DEFAULTS` (`code` → `mono`, `quote_mark` → `serif`) > `sans`;
  the tokens `sans`/`serif`/`mono` (`fonts.FONT_TOKENS`) resolve to `font`/`font_serif`/
  `font_mono`, any other value is a family name. **Changed from §20**: a `font` written in
  `video.yaml` is the sans family only and no longer overrides every role (otherwise a config
  `font: Inter`, as in examples/minimal, would silently cancel a preset's serif headings, and
  code listings would lose their mono font). `Theme.fonts` = the roles set by presets + config
  (without defaults).
- **Built-in scenes**: role `heading` for the `title` title, `bullets` heading, `bar_chart` /
  `line_chart` / `code` titles and the `end_card` title; `quote` for the quote text;
  `quote_mark` for its mark (param `mark_font` default `None` = the role; was
  `"Georgia,DejaVu Serif,serif"`); `code` for listings and line numbers (param `font` default
  `None` = the role; was `"Monospace"`, which on Windows was not a monospace font). All other
  text: `body` = theme `font`. `fit_text`/`fit_text_sized` gain `font=None` (default the theme
  font); `readable_text` measures its floor with the `font` it is given.
- **Presets**: `light_academic` `fonts: {heading: serif}`, `warm_editorial` `{heading: serif,
  quote: serif}`; every other preset keeps all-sans text. Source Serif 4 has a smaller cap
  height per point (0.0093 vs Inter 0.0101 units), so serif headings look ~8 % smaller at the
  same size token; headings are far above the `min_font` floor, so sizes were left alone.
- **Fingerprint**: the bundled font files are part of `vidgen_source_digest` (a font update
  re-renders storyboards).
- `vidgen list-themes`: entries gain `font_serif`, `font_mono` and `font_roles` (the family of
  every built-in role); the swatch panel draws "Aa Heading" in the preset's heading family when
  it is bundled.

## 22. Refinements (Step 19, icons: mechanism + seed set)

- **Vendored set** (package data `src/vidgen/data/icons/`, `pyproject` `data/icons/**/*`):
  `lucide/<name>.svg` (unmodified files of npm `lucide-static` 1.52.0), `lucide/LICENSE` (ISC +
  the MIT notice of the Feather-derived icons) and `manifest.json` = `{version: 1, sources:
  {lucide: {package, version, license, license_file, homepage}}, icons: [{name, category, tags,
  source}]}` (sorted by name; tags = Lucide's `tags.json` + `extra_tags`). Seed set: 40 icons,
  5 in each of the 8 categories `icons.CATEGORIES` (`tech, data, science, business, people,
  ui, nature, education`; `ui` = arrows and interface), listed in `tools/icon_set.json`.
  `tools/vendor_icons.py` (not shipped) re-creates the folder from that list (`npm pack`, or
  `--package-dir`), checks names/categories/version, removes unlisted SVGs; Step 20 extended the
  list to 200 (§23). `THIRD_PARTY_NOTICES.md` records the source.
- **Registry** (`vidgen/icons.py`, manim-free): `IconInfo(name, path, category, tags, source,
  origin, overrides)`; `builtin_icons()`, `builtin_sources()`, `project_icons(root)` (every
  `<root>/assets/icons/*.svg`, names `[A-Za-z0-9][A-Za-z0-9_-]*`, optional `icons.json` `{icons:
  [{name, category, tags}]}`, category default `project`; cached per folder by file
  names/sizes/mtimes), `available_icons(root=None)` (built-ins, then project icons replacing by
  name; sorted), `active_icons()` (the runtime project's), `search_icons(icons, text,
  category)` (every word of `text` must be in the name, a tag, or equal the category; ranked
  exact name < name prefix < in name < exact tag < in tag < category, then by name; Step 22
  ranks whole words before substrings, §25),
  `find_icon(name)` / `unknown_icon_message` (difflib close names + icons whose tags match,
  pointing at `vidgen list-icons --search`). Project icon problems are `VidgenError`s;
  `vidgen validate` reports them as `assets/icons: ...`.
- **Mobject** (`vidgen/icon_mobject.py`): `icon(name, size="body", color="text",
  stroke_width=None, *, height=None, theme=None) -> Icon`; `build_icon(info, height, color,
  stroke_width, current=)`. The SVG is pre-processed into a per-process temporary folder
  (Manim's `SVGMobject` writes `<stem>_.svg` next to the file it parses, which would race
  between parallel workers and fail in a read-only install): an invisible `<rect>` spanning the
  `viewBox` is inserted first, `currentColor` becomes a marker colour (Manim reads it as black)
  and `stroke="none"` a zero stroke width (Manim draws it as a white stroke). Then: the rect is
  the `Icon`'s `box` (submobject 0, opacity 0: layout, `place()` and alignment use the design
  box; the layout dump ignores it as invisible), every visible fill/stroke gets `color` (or,
  with `color=None`, only the marker-coloured paint gets the theme `text` colour), each SVG
  stroke width `w` (viewBox units) becomes Manim `w * height / viewBox_height / 0.01` (Cairo
  draws `stroke_width * 0.01` frame units, so the result is resolution independent),
  `stroke-linecap`/`-linejoin` of the root map to `cap_style`/`joint_type`. **Sizes**: a
  size token or number is points as for text; box height = `points * ICON_UNITS_PER_POINT`
  (0.0208 = 1.5 em of Inter: a `body` icon draws ~1.7x the cap height of body text, the ratio
  of 24 px icons to 16 px text in UI kits); `height` is Manim units. `Icon.scale(f,
  scale_stroke=True)` scales strokes by default (Manim's default is False), so `place()`,
  `animate.scale` and `GrowFromCenter` keep proportions. `icon_name`, `icon_origin`.
- **Params**: `vidgen.scene.IconName` = `Annotated[str, AfterValidator, ThemeToken("icon")]`:
  syntax always; with a theme in the validation context (validate, scene construction) the name
  must be in `active_icons()`. `ThemeToken.kind` may now be `icon`: `list-scenes` prints type
  `icon`; the schema export turns `x-vidgen-theme: icon` into `enum` of the active project's
  icon names (`schema.theme_tokens()["icon"]`; built-ins if the project's icon folder is broken).
- **Layout dump / lint**: an `Icon` is one object, kind `icon`, `class` `Icon`, `icon` = its name,
  `fill`/`stroke` of its largest part, `bbox` of its drawn parts. Lint treats icons like other
  non-text objects (`covered_text` when drawn over text, `off_frame`); `describe()` prints
  `icon 'cpu'`; findings' objects gain the key `icon` (`null` for other kinds; added within JSON
  version 1); `lint_ignore` `object` patterns also match the icon name.
- **`vidgen list-icons [PROJECT] [--search TEXT] [--category NAME] [--sheet PNG] [--json]`**
  (`iconlist.py`, not a render input): project root from `find_config_file` without loading the
  config (works while `video.yaml` is broken; no PROJECT and no config in the current folder:
  built-ins); unknown category → `VidgenError` listing them. `--sheet`: 1280 px wide pages, 8
  icons per row (150 px cells, 64 px icon box), name + category under each, at most ~1.25 x
  width high (`<stem>-2.png`... for more; stale extra pages removed); icons drawn by
  `build_icon` through Manim's Cairo `Camera` in one capture per page (same pixels as a render).
  JSON (Step 8 envelope, command `list-icons`): `project, search, category, sources,
  categories [{name, description, count}], count, icons [IconInfo.to_json()], sheets`.
- **Fingerprint**: `icons.py`/`icon_mobject.py` count as vidgen source; the vendored SVGs and
  manifest are part of `vidgen_source_digest`; project icons are under `assets/` (already
  tracked by size+mtime).

## 23. Refinements (Step 20, icons: curated expansion)

- **Set**: 200 Lucide icons, 25 per category, chosen for explainer videos (concepts scripts name:
  hardware/networks/security/AI, chart types/tables/statistics, lab/space/medicine/maths,
  money/growth/commerce/industry, persons/communication/emotions/health, arrows and status
  symbols, weather/plants/animals/landscape, books/school/writing/arts); near-duplicates and
  brand marks left out. Lucide 1.52's current names are listed (e.g. `building-complex`,
  `face-slightly-smiling`, `book-bookmark`, `waves-horizontal`); the old ones are aliases.
- **Tags**: Lucide's `tags.json` + `extra_tags` with the words an explainer script uses for the
  concept (`banknote`: cash, bill, finance; `trending-up`: growth, profit; `shield-check`:
  security, trust; `gauge`: performance, speed, kpi). Every icon has >= 3 distinct tags.
- **Aliases** (manifest entry key `aliases: [str]`, sorted; always present): (1) Lucide keeps
  renamed icons' old names as copies of the new file, so the tool makes every package file that
  has no `tags.json` entry and draws exactly like one vendored icon (comment and `class`
  ignored) an alias of it (`home` → `house`, `pie-chart` → `chart-pie`; an old name drawing like
  two vendored icons is skipped); (2) curated `aliases` in `tools/icon_set.json`
  (`{alias: icon}`): synonyms (`idea`, `ai`, `warning`, `money`, ...) and `bar-chart` →
  `chart-column` (Lucide's `bar-chart` is the axis-less `chart-no-axes-column-increasing`,
  which is not vendored). The tool rejects: a curated alias that is a current Lucide name or
  conflicts with an upstream alias of a vendored icon, an alias of an unlisted icon, and an old
  (alias) name listed as an icon.
- **Resolution** (`vidgen/icons.py`): `IconInfo.aliases`; `builtin_aliases()` (`{alias: name}`);
  `resolve_icon(name, icons)` (name first, then an alias of an icon in `icons`; an alias never
  shadows an icon name); `icon_names(icons)` (names + aliases, sorted). `find_icon` (so `icon()`),
  the `IconName` validator and the schema `enum` accept aliases; `Icon.icon_name` (layout dump,
  lint) is the resolved icon's name. A project icon replacing a built-in keeps its aliases; a
  project icon named like an alias takes the name over (`available_icons` drops it from the
  built-in's aliases). Search: an exact alias scores like a name prefix (1), part of an alias
  like part of a name (2). `unknown_icon_message` also matches aliases, suggesting the icon
  they stand for.
- **Listing**: `list-icons` text lines show `(alias: ...)`; JSON icon entries gain `aliases`
  (additive, envelope version 1).
- **Catalogue**: `docs/ICONS.md` = `iconlist.catalogue_markdown(manifest)` (per category: name,
  aliases, first 8 tags), written by `tools/vendor_icons.py` (`--docs`); a test keeps it equal to
  the shipped manifest.
- **Rendering check**: every icon was compared with a reference rasteriser (cairosvg, not a
  dependency) at 192 px: overlap of inked pixels >= 0.97 for all 200 (arcs, spirals, filled
  dots), so the loader needed no change; tests build all 200 (box, colours, extent) and render
  six with arcs/fills at 96 px.

## 24. Refinements (Step 21, icons in built-in scenes)

- **`grid_shape(n, aspect=None, *, cell_aspect=1.0, max_cols=None) -> (rows, cols)`**
  (`vidgen/regions.py`, exported by `vidgen.api`): `aspect` = width / height as a number, a
  region name or a `Region` (default: the safe area). Every column count without an empty row
  is scored by the cell size it allows at `cell_aspect` (`min(aspect / cols / cell_aspect, 1 /
  rows)`); among shapes within 3 % of the best, fewest empty cells, then fewest rows. `n < 1`,
  non-positive `aspect`/`cell_aspect` → `VidgenError`.
- **Icons scaled with their group**: `vidgen.icon_mobject.scale_icon_strokes(mob, factor)`
  multiplies the stroke widths of the `Icon`s inside a scaled group (not of `mob` itself when it
  is an `Icon`, whose `scale` already does it). `shrink_to_fit` and `place` call it, so icons
  in a list or card keep their proportions when the layout shrinks it. Only icons are affected
  (other mobjects keep Manim's behaviour), so existing output is unchanged.
- **`bullets`**: `items: list[BulletItem]`; `BulletItem(text: str (min 1), icon: IconName |
  None = None)` accepts a plain string (`model_validator(mode="before")` → `{text}`), so old
  configs are unchanged; its JSON Schema is `anyOf: [string (minLength 1), object]`
  (`__get_pydantic_json_schema__`), so the exported schema accepts both forms. Layout per row
  `VGroup(marker?, icon?, text)` (text last): without icons exactly as before. With icons, the
  icons (size = item size x `icon_scale` 0.95 points, box 1.5 em) form a column left of the
  text, centred on the cap height of the first line; numbers stand right-aligned left of that
  column; an item without an icon shows its marker centred in the column (unless numbered).
  Icons use `marker_color`. `dim_previous` now uses `fade(1 - dimmed_opacity)` once per row
  (multiplies each part's opacity) instead of `set_opacity`, which would have made an icon's
  invisible box and unfilled paths visible; for text the result is identical.
- **`title`**: `icon: IconName | None`, `icon_color` (`primary`), `icon_position: above | left`
  (`left` falls back to `above` in portrait). The icon is `icon_height` (1.25) units; above, it
  is stacked over kicker/title/subtitle and the title gets 36 % (was 42 %) of the safe height;
  left, the text width shrinks by the icon and `icon_gap` (0.5) and the icon is scaled to at
  most 1.1x the text block's height. Revealed first in beat 1 (`FadeIn(scale=0.6)`).
- **`end_card`**: `icon: IconName | None`, `icon_color` (`primary`), `icon_height` 1.1 units,
  between logo and title; an icon alone satisfies "at least one of title, lines, logo, icon".
- **`icon_grid`** (`scenes/icon_grid.py`): params in docs/CONFIG.md. Layout: heading in
  `header` (portrait x1.3 like `bullets`), grid in the safe area below it. Shape: `columns` if
  given, else `grid_shape` for each of `cell_aspects` (0.7, 0.9, 1.2, 1.6, 2.2) and each
  distinct shape is planned (`_plan`): column width `min((W - gaps) / cols, 4.2)`; labels and
  sublabels built at one size each, reduced by 10 % steps (not below `readable_size()`) until
  the tallest label block takes ≤ 45 % of a row and the widest word fits the column; icon (or
  disc) height `min(0.6 cell width, 0.85 (row - labels - 0.2), 1.9)`, at least 0.5. Score:
  `(fits, icon_h * min(1, label_size / size)^2)`, so a shape that keeps text at its size and
  icons large wins; if nothing fits, the best one is used and the grid is shrunk as a whole.
  Rows are spread over spare height (≤ 1 unit extra per gap), a short last row is centred,
  labels/sublabels are placed by baseline. Cells (`VGroup(visual, label, sublabel?)`, visual
  = `VGroup(disc, icon)` with `badge`, else `VGroup(icon)`) are added to the scene whole before
  their entrance (a part's introducing animation would otherwise add it alone and dissolve the
  cell); entrance `GrowFromCenter(disc)`, `FadeIn(icon, scale=0.6)`, labels `FadeIn(shift=UP)`,
  lagged. Steps: per item, per `groups` entry, or all; `highlight` adds a last step: other
  cells `fade` to `dimmed_opacity` 0.55 (0.45 left a `dim` sublabel at 1.93:1 on the light
  presets, under lint's 2:1 for dimmed text), the chosen visual is transformed into a 1.15x
  copy in `highlight_color`. `groups`/`highlight` items are 0-based indices (as `bar_chart`'s
  `highlight`) or labels; groups must list every item once.

## 25. Refinements (Step 22, review 1)

- **Font roles in the text helpers**: `T`, `MT`, `NarratedScene.text`/`markup`
  (`helpers.styled`), `fit_text`/`fit_text_sized` and `readable_text` take a keyword `role=None`:
  the family is `font` if given, else `theme.font_for(role)`, else `theme.font`. Additive;
  `readable_text` measures its floor with that family.
- **`region(name, area=None, gap)`**: `area` may also be a region name (`region("left",
  "body")`), like `grid` and `place`.
- **`SceneParams.also_accepts: ClassVar[tuple[type, ...]] = ()`**: other input types a nested
  model is built from (`BulletItem.also_accepts = (str,)`); `describe.type_name` prints them
  before the model (`list[str | BulletItem]` in `list-scenes` and its JSON `type`).
- **`register_theme_defaults`** (`Theme.add_defaults`) rejects token names that are not
  identifiers (`video.yaml` could never override them) and colours that are not `#RGB`,
  `#RRGGBB`, `#RRGGBBAA` (was: any string starting with `#`).
- **Icon search** (`icons._score`): 0 exact name, 1 name prefix or exact alias, 2 a whole word of
  the name or an alias (split at spaces, `-`, `/`, `.`, `_`), 3 exact tag, 4 a whole word of a
  tag, 5 part of the name or an alias, 6 part of a tag, 7 the category. Whole words now rank
  above substrings (`ai`: `brain-circuit`, `bot` before `rain`, `mail`).
- **Lint**: `vidgen lint` logs `theme_contrast` failures of the project's theme like `vidgen
  validate` (`warning: theme contrast: ...`; JSON `warnings`), unless `--rule` excludes
  `contrast` or `lint.rules.contrast.severity` is `off`; they are not findings. Findings
  merging (`run._group_similar`) also merges findings of one still with the same rule,
  severity and object `text` (a label repeated in copies of a component, e.g. two decoder
  boxes' "Attention"), besides the parent-path group.
- **Built-ins on regions / 9:16**: `quote` (`portrait_growth` 1.25 for the text, mark and
  author; `place(card, safe_area, max_scale=1)`), `equation` (`portrait_growth` 1.25 for the
  formulas, positions from the safe area; new param `caption_size`), `image` (with `fit: cover`
  the caption is placed at the bottom of the `caption` region, i.e. on the safe area's bottom
  edge, and the band runs from the frame's edge to 0.3 above it: it was 12 px into the margin),
  `bar_chart`/`line_chart` (new params `caption_size` = `caption` (was the fixed `small`, below
  lint's `min_font`) and `caption_color` = `dim`; caption fitted to 15 % of the safe height).
  16:9 output is unchanged except the chart captions (24 instead of 20 pt) and the cover-image
  caption (0.2 units higher). `title`, `end_card`, `text_card` and the chart bodies were left
  as they are: their 9:16 sheets read well since the Step 17 `auto` scale; charts move to shared
  helpers in Step 30.
- **CLI**: `list-themes --sheet PNG` is an alias of `--swatches` (as `list-icons --sheet`).
  Checked: every command with `--json` (validate, list-scenes, list-themes, list-icons, schema,
  render, storyboard, lint) answers errors with the envelope, `ok: false`, exit 1 (usage: 2).
- **Tests**: marker `slow` on the 18 slowest render tests (several seconds each); `pytest -m
  "not slow"` is the quick run, `-m "not render"` the fastest; the default runs everything.

## 26. Refinements (Step 23, per-beat actions)

- **Config** (`config.ActionConfig`, `BeatConfig.actions: list[ActionConfig] = []`; reference:
  docs/CONFIG.md "Beat actions"). Canonical form `{action: NAME, target, at, until, run_time,
  ...options}`: `action` an identifier; `target` a name or pattern (`*`/`?`, brackets literal)
  or a non-empty list of them; `at` in [0, 1) of the beat's narration (default 0); `until` a
  later beat of the same scene (checked by `SceneConfig`); `run_time` > 0 (default the action
  type's). Every other key is an option of the action (`extra="allow"`, `ActionConfig.options`;
  `ACTION_KEYS` are reserved). **One shorthand**: `{NAME: TARGET, ...options}`; `NAME` is the
  first key that is not one of `ACTION_KEYS` (a wrap validator rewrites it to the canonical
  form and keeps the raw mapping); `ActionConfig.resolved(known)` re-picks the key when that
  one is not a registered action but exactly one other key is (keys sorted by a tool such as
  `yaml.safe_dump`). `target` next to a shorthand is an error. Actions are part of the scene's
  config entry, so they count in the render fingerprint, not in the TTS hash.
- **Registry** (`vidgen.registry`): action types live next to scene types, with the same two
  layers and collision rules (`ActionType(name, cls, origin, overrides)`, `register_action`,
  decorator `action(name, *, override=False)`, `find_action`, `action_names`, `all_actions`,
  `unknown_action_message`; both kinds go through `_add`). `reset/snapshot/restore/isolated`
  cover both layers (`Snapshot` is now a pair). Built-in actions: `src/vidgen/scenes/actions.py`
  (only `from vidgen.api import *`, imported by `vidgen.scenes`).
- **Action class** (`vidgen.actions.Action`, exported): `Options` (an `ActionOptions` pydantic
  model, `extra="forbid"`, theme tokens checked with the theme in the context; field names may
  not be `ACTION_KEYS`), class attributes `run_time` (0.6), `reversible` (`until` allowed;
  requires `revert`), `needs_visible` (True: hidden targets are revealed first),
  `needs_target` (True). One instance per use (`__init__(options, config)`), so `apply(scene,
  targets) -> list[Animation]` can keep what `revert(scene, targets)` needs.
  `check_action_class` validates at registration.
- **Targets** (`vidgen.actions.Target(names, mobject, entrance)`, exported). A scene type
  declares `target_patterns` (doc forms, e.g. `("heading", "item<N>", "item:<text>")`) and
  classmethod `target_names(params)` (every concrete name, for validation without rendering);
  `construct()` registers them with `self.target(names, mobject, entrance=None)` (names match
  `TARGET_NAME`: `word`, `word3`, `kind:any label`; a name may repeat, a pattern selects every
  match). `self.on_screen_parts(t)` = the largest parts of the target that are in the scene's
  family (a group target such as a bar + its labels is never added itself; animating the group
  would make Manim add it and draw its parts twice); `is_shown` = any such part; `entrance(t)`
  = the target's entrance animations, or `[]` when shown. Built-ins build their own reveal
  steps from `entrance()`, which is how **a target revealed early by an action is not revealed
  again by the scene's step** (decision: `reveal` of a shown target is a no-op, not an error —
  whether it is shown depends on timing a static check cannot see). `bullets`: `heading`,
  `item<N>`, `item:<text>` (the row); `bar_chart`: `title`, `bar<N>`, `bar:<label>` (bar +
  value label + category label; title and caption are no longer one `head` group, visually
  identical).
- **Validation** (`actions.scene_actions(type, cls, spec, params, theme) -> (uses, problems)`,
  locations relative to the scene): unknown action (did-you-mean + known list), options
  (pydantic problems at `...actions[k].<option>`), `until` on a non-reversible action, missing
  target, unknown target (difflib suggestions, up to 14 names, the forms, wildcard hint; a type
  without targets names the types that have some). `vidgen validate` reports them as
  `scenes[i].beats[j].actions[k].<key>` (action names and options are checked even when the
  params are invalid; targets need valid params). `plan_actions` raises one `VidgenError`
  with all problems; it runs in `pipeline._check_scenes` (before any worker) and in
  `NarratedScene.__init__`.
- **Timing** (`actions.ActionRunner`, created by the scene when it has actions). `narrate()`
  calls `start_beat(id, d, pad)`: due frame = beat start + `round(at * d * fps)`; reverts of
  applied uses with `until == id` are due at the start, before the beat's own actions. Actions
  run **inside waits only**: `wait_seconds` and an overridden `wait` (plain Manim waits in
  extension code) hand the wait to `ActionRunner.wait(frames)`, which waits to the due frame,
  plays the due actions and waits the rest (`_wait_frames` is the old frame-exact wait). So an
  action never shares a `play` with the scene's own animation of the same mobjects; with `at:
  0` it follows the beat's entrance step. Run time = the configured/default run time, scaled
  down so all phases end by the beat's end (`d + pad`), quantised to whole frames; shortened
  plays carry `requested` (lint `rushed_animation`). Phases: entrances of hidden targets
  (`reveal_time` 0.6 s) for `needs_visible` actions, then batches of due actions whose target
  families do not overlap (actions on one target play one after the other). `end_beat()` (after
  the final wait of `narrate`) applies what found no time without frames (`_apply_now`:
  begin + finish) and logs a warning. `play_steps` now ends slot *k* at `start + (k+1)·slot`
  (absolute), so an action that lengthened a slot's wait is absorbed by later waits (no
  change without actions beyond frame rounding; every built-in's timing test still holds).
- **Built-in actions**: `reveal` (run time 0.8, `needs_visible` False: the targets' entrances).
  `dim` (`opacity` 0.45 relative to the current, reversible). `highlight` (`color` =
  `highlight` token, `style` `color` | `box` | `underline` | `flash` or a list; `flash` and
  `color` cannot combine; reversible: colours restored, box/underline faded out).
  Colour/opacity changes use `Repaint`, an animation of the fill/stroke RGBA arrays of every
  `VMobject` in each on-screen part (points untouched); revert restores only the channels the
  action changed (RGB for highlight, alpha for dim) from the arrays saved at `apply`, so the two
  combine and undo independently. Box: `SurroundingRectangle(buff 0.12, corner_radius 0.1,
  stroke 4)`; underline: `Underline(buff 0.08, stroke 4)`. A first `pulse` style (Indicate-like
  scaling about the target) was dropped: a bar scaled about its group's centre crossed the axis.
- **Listing / schema**: `list-scenes` prints `targets:` per type and an `actions` section;
  `--json` adds `targets` to scene types and a top-level `actions` list (`describe.
  action_type_json`; keys added within version 1). `vidgen schema`: `BeatConfig.actions.items`
  = `anyOf` [`ActionConfig` (`action` enum, per-action `if`/`then` with the options and
  `additionalProperties: false`), `ActionShorthand` (`anyOf` one object per action: `required:
  [NAME]`, its options, `additionalProperties: false`)]; options under `$defs/action.NAME`
  (theme tokens as for params). Targets and `until` are left to `vidgen validate`.
- **Limits / for Step 24**: only `bullets` and `bar_chart` have targets; `dim`/`highlight`
  recolour vectorized mobjects only (images keep their pixels); `dim` compounds with a scene's
  own dimming (`bullets` `dim_previous`); `highlight` keeps the target's current opacity (a
  dimmed item is highlighted dimmed). Step 24 adds `zoom`/`transform` and targets for the
  other built-ins on this framework.

## 27. Refinements (Step 24, zoom, transform, targets everywhere)

- **Camera.** `NarratedScene` subclasses Manim's `MovingCameraScene` (was `Scene`). The camera
  frame starts on the whole frame (`config.frame_width` x `frame_height`, aspect kept for 9:16),
  so scenes that never move it render pixel-identically (whole suite and every example
  unchanged). `NarratedScene.play` removes the frame from `self.mobjects` after a play that
  added it (Manim adds the animated mobject; the frame is never drawn), unless it has updaters
  (an extension's follow-cam). The layout dump already measured with the scene's camera
  (`camera.center/width/height`, §15); it gains `camera.zoom` (= `config.frame_width /
  camera.frame_width`, added within layout version 1). `lint.StillContext.zoomed` (zoom >
  1.001): `off_frame` and `safe_area` skip zoomed stills (cutting the scene off is the point).
  **For Step 38 (overlays):** anything drawn as a mobject in the scene moves with the camera; a
  screen-fixed overlay must either follow `camera.frame` (an updater scaling/moving it with
  the frame) or be composited outside Manim (ffmpeg), which also keeps it out of scene renders.
  (Step 38 composites in the renderer's `add_frame` instead, §41.)
- **Framework additions** (`vidgen.actions`): `Action.temporary` (requires `reversible`): the
  runner schedules `revert` itself, due `run_time` before the end of the *return beat* — the
  use's own beat, or with `until: B` the beat before `B` — so the effect is over when the next
  beat (resp. `B`) starts; at `until` beats it is not undone again. `Action.moves_camera`: two
  such uses never share a batch (the camera frame counts as a shared mobject).
  `Action.target_options`: option names whose values are target names (str or list):
  `scene_actions` checks them like `target` (problems at `...actions[k].<option>`);
  `check_action_class` requires them to be `Options` fields. Ordering on one frame: `until`
  undoings, then the beat's actions, then temporary undoings (`_rank`). Budget: when actions
  run, the time of temporary undoings still pending in the beat is reserved, and both are
  shortened by one factor when the beat is short (`factor = remaining / (phases + reserved)`).
  An undo of a use that was never applied is skipped. `resolve_targets(scene, pattern)`: a
  plain name shared by several targets selects the ones on screen, else the first (patterns
  select all) — used for equation terms registered once per step.
- **Full opacity** (`Target.rest`, a dict `id(member) -> (fill, stroke)` filled at
  registration, shared by a scene's targets via `NarratedScene._rest`; `rest_opacity(member)`
  falls back to 1/0 for members created later, e.g. a value label rebuilt by `become`). Scenes
  register targets right after layout, before any opacity changes of their own.
- **`dim`** now means "at most `opacity` x full opacity": each member's alpha array is scaled
  so its maximum is `<= full x opacity` (ratios kept, so gradients and transparent pixels
  survive); nothing that is already dimmer changes, so dimming never compounds. Exposed to
  built-ins as `scenes.actions.dim_to(target, part, factor)`; `bullets` `dim_previous` and
  `icon_grid`'s highlight step use it (same values as their former relative `fade`).
- **`highlight`**: `style: color` also raises alpha to full (a dimmed target is highlighted at
  full opacity); revert restores RGB and sets alpha to min(current, saved) (undoes the raise,
  keeps dimming that happened since). Box around `Target.outline` (default the mobject);
  `bar_chart` gives each bar an outline = bar + final value label, stopping `outline_gap`
  (0.15) short of the axis, so the box (buff 0.12) stands on the axis instead of crossing it.
- **Images**: `Repaint` also animates the `pixel_array` of `ImageMobject` members
  (`paint_image(member, rgba float array)`): `dim` scales the alpha channel, `highlight` tints
  RGB 30% towards the colour (`image_tint`); `_Memory` saves pixel arrays for undo.
- **`zoom`** (`run_time` 1.0, reversible, temporary, moves_camera; options `scale` (> 1, <= 8)
  and `padding` (0.15, share of the view on each side)). The view: the union box of the
  targets' on-screen parts; magnification `min(max_scale=3, (1-2p) x frame/box)` per axis, or
  `scale`; centre clamped so the view stays inside the frame. Magnification <= 1.01 → no move
  and a warning (the targets fill the frame). Revert: back to the whole frame (no-op when home).
  Animation `MoveCamera(scene, width, center)` (a `Transform` of the frame; its name shows in
  the play log / activity file).
- **`transform`** (`run_time` 1.0, not reversible; options `into` (required; `target_options`)
  and `style` `auto|replace|shapes|tex|fade`). The source's on-screen parts are removed and a
  copy added (so the originals stay intact, and a group target never added whole is not drawn
  twice), then morphed into `into` (its hidden matches); `auto` = `TransformMatchingShapes` when
  both sides are text/formulas only, else `ReplacementTransform`; non-vector sides use
  `FadeTransform`; `tex` without two `MathTex` falls back to shapes (warning). `into` already on
  screen: the sources fade out towards it (warning). **Decision: `into` must be a target**, not a
  text literal: a literal has no place, size or style in the scene's layout; scenes that need
  alternatives provide them as targets (equation steps). Scene steps that would animate a
  transformed-away target skip it (`bar_chart`/`icon_grid` highlight steps, `bullets`
  `dim_previous` via `on_screen_parts`).
- **Targets of every built-in** (table in docs/CONFIG.md "Beat actions", kept in sync with
  `target_patterns` by `tests/test_actions_coverage.py`): `title` (`icon`, `kicker`, `title`,
  `subtitle`, `authors`), `text_card` (`text`), `quote` (`mark`, `quote`, `author`, `source`),
  `equation` (`step<N>`, `caption`, `term:<tex>`; new param `terms`: substrings isolated with
  `MathTex(substrings_to_isolate=...)`, each must occur in a step; a term target per step that
  contains it (`get_part_by_tex`, first occurrence; works with Manim 0.19 and 0.21), entrance
  `[]`), `code` (`title`, `listing`, `line<N>` = physical lines + numbers of original line N,
  `lines:<a-b>` for every a < b; `target_names` counts a `path` file's lines through
  `current_project()`, none without a project context), `image` (`image`, `caption` = the text,
  entrance fades the caption group), `line_chart` (`title`, `axes`, `series<N>`,
  `series:<name>`, `point:<name>@<x>` with `x` as its tick label; without dots a point is a
  separate dot that its entrance fades in), `end_card` (`logo`, `icon`, `title`, `line<N>`),
  `icon_grid` (`heading`, `item<N>`, `item:<label>`). Every built-in builds its steps from
  `self.entrance()`; `equation` steps morph from whichever step is on screen, and a step is
  skipped once a later one is shown.
- **Listing**: `list-scenes` shows `, undone by the beat's end` for temporary actions;
  `--json` actions gain `temporary` and `target_options` (within version 1). `vidgen schema`
  adds required options (`into`) to both action forms.

## 28. Refinements (Step 25, `stat` and `chapter`)

- **`stat`** (`scenes/stat.py`; reference docs/CONFIG.md): params `value`, `label`, `context`,
  `prefix`/`suffix` (number size), `unit` (`unit_ratio` 0.42 of it, on the number's baseline:
  median glyph bottom), `decimals` (default `needed_decimals([value, comparison.value])`, up to
  2), `thousands` (`,`), `decimal_mark` (`.`), `count`, `count_from`, `comparison`, `icon`,
  colours (`color` `primary`; `good_color` `tertiary`, `bad_color` `accent`, `neutral_color`
  `dim`: in every built-in preset `tertiary` is the green and `accent` the red), sizes (number
  `value_scale` 3.0 x `title`). `format_number(value, decimals, thousands, decimal_mark)`
  (module function, typographic minus, no "minus zero"). `StatComparison` (nested, `also_accepts
  = (float,)`: a plain number is `{value: N}`; JSON Schema `anyOf` number | object like
  `BulletItem`): `value`, `label`, `kind: versus | before` (`before` = before → after: the count
  starts at the old value), `word` (default `vs`/`from`, translatable), `delta: difference |
  percent | none`, `better: higher | lower | neither`. The change chip (`Stat.change() -> (text,
  colour token, direction)`) is an arrow (a filled `Triangle`, none for no change) + the signed
  delta in a pill filled with the theme's `surface` and stroked in the colour: a tint of the
  colour behind the delta cost it contrast on light presets (lint `contrast` 4.0:1 on
  `light_academic`), the surface keeps every preset's text ≥ 4.5:1.
- **Count**: the layout is built with the final value (the number's font size is chosen so the
  wider of start/end fits 92 % of the safe width and 42 % of its height, then the card is
  `place`d with `max_scale=1` and the size scaled with it, so the count never changes size).
  Targets are registered at that full look; then the number line shows the start value. Its
  entrance is one `UpdateFromAlphaFunc` (linear) that rebuilds the line each frame
  (`ease_out_cubic` value, fade over the first `fade_share` 25 %, rising 0.15 units into place),
  keeping the final line's top edge and centre x (digits have one height, so nothing jumps);
  `become` + `original_text` as in `bar_chart` so the layout dump sees the shown string.
- **`chapter`** (`scenes/chapter.py`): `title` (required; **the chapter's name** — Step 39's
  indicator and Step 49's chapter list read `params.title` of `chapter` scenes, `number_text()`
  for the number), `number: int | str` (`number_format` `{:02d}` for ints, checked by formatting
  7), `subtitle`, `icon`, `rule`, colours, sizes (number 2.4 x `title` for ints, 1.6 x for text).
  Layout: landscape with a number or icon → `VGroup(left column (icon over number), vertical
  rule, left-aligned title block)`; else stacked and centred (icon, number, short rule
  `rule_length` 1.6, title, subtitle). Entrance: rule `Create` (vertical, drawn downwards) /
  `GrowFromCenter`, number/icon slide in from the left (from above when stacked), title from
  the right (from below), subtitle rises; lagged 0.25. Steps: with ≥ 2 beats `[head,
  subtitle]`, else one step (silent or one beat: the subtitle belongs with the title; two
  steps in one short silent card would rush both).
- Both: Step 15 regions (`safe_area`, `place`), theme tokens and font roles only (numbers and
  chapter titles use the `heading` role), targets per Step 23/24 and the table in CONFIG.md,
  `outro` 0.5, `reveal()` with `fraction` 0.75 (caps 2.0 / 1.6).

## 29. Refinements (Step 26, `comparison` and `table`)

- **Target names may be dotted** (`actions.TARGET_NAME`: `word(.part)*(:label)?`), for parts of
  parts: `col2.item3`, `cell2.4`. Patterns (`cell1.*`) work as before.
- **`highlight` style `fill`**: a `SurroundingRectangle` of the target's outline (`box_buff`
  0.12, corner 0.1, no stroke) filled with the colour at `fill_opacity` 0.22 (below lint's
  0.3 cover threshold; text over it keeps its contrast), faded in by a `Transform` of its
  opacity (not `FadeIn`, an introducer that would move it to the top). It is inserted into
  `scene.mobjects` just before the target's first part when the parts were added on their own,
  else just after the group holding them (then it is a faint overlay), with the parts' lowest
  `z_index`; scenes put backdrops (table stripes, comparison cards) at `z_index` -1 so the plate
  lies between backdrop and text. Undone (`until`) like `box`.
- **`comparison`** (`scenes/comparison.py`; reference docs/CONFIG.md): `columns` (2–3
  `ComparisonColumn`: `heading`, `icon`, `tone: positive | negative | neutral`, `points` ≤ 8 of
  `ComparisonPoint`, a string or `{text, icon}` like `BulletItem`), `heading`, `verdict`,
  `reveal: columns | rows | all`, `markers` (check / x icons, or a dot for neutral), `cards`,
  `vs` badge, tone colours `tertiary`/`accent`/`primary` (as `stat`'s good/bad). Layout: heading
  in `header` (1.3x in portrait), verdict at the bottom of the body, `Region.split(n)` for the
  card slots (columns in landscape, rows in portrait), cards of one size (tallest column).
  One text size for every column: from `size` down (x ≤ 0.95 per try) to `readable_size()`;
  still too tall → scaled about the top-left corner and a warning. Rules line up across
  columns side by side; with `reveal: rows` the *m*-th points too. Targets: a column is
  `VGroup(head, rule, points)` (the card is outside, so `color` does not paint it; `outline` =
  the card inset by the box buff); a point's entrance brings its column's card and heading
  first. Steps through `_column_entrance` (frame, then points not on screen), so early
  reveals are never repeated.
- **`table`** (`scenes/table.py`): `rows` (≤ 30, cells `str | int | float`; bool/null rejected
  with a hint), `header` (≤ 8 columns), `title`, `caption`, `align` (`auto` = numbers right),
  `number_format` (str or per column; default `auto_format` of the column, so a column shares
  its decimals), `reveal: per_beat | all`, `zebra`, colours, sizes. `Params.texts()` gives the
  cells as shown (also used for `row:<first cell>`). **Fitting** (`_fit`): sizes `size` x
  (1, .92, .85, .78, .72, .66, .6) and the readable minimum; at each, `_widths` gives natural
  widths (one line, cell padding 0.75 cap each side) or water-fills the area width (columns
  needing less than a fair share keep their natural width, columns whose floor — longest
  header word, body cells > 16 characters by word, shorter cells and numbers whole — exceeds
  the share get the floor); the first size whose widths fit and whose height fits wins.
  Nothing fits → built at the readable size, scaled to the area, warning "split it into
  smaller tables or drop columns" (lint `min_font` reports it too). A narrow landscape table
  spreads its columns up to 1.25x (at most 80 % of the width). Rows: cells positioned by first
  baseline; header rule `header_color`, stripes every other row (`z_index` -1), end rule
  `rule_color` drawn with the last row. Every cell text is added on its own (so a `fill` plate
  sits just under a row's / column's cells); invisible row/column/cell rectangles (inset by the
  box buff) are the targets' outlines.

## 30. Refinements (Step 27, `timeline`)

- **`measure_text(text, max_width, *, size, weight, slant, line_spacing, balance, theme, font,
  role) -> TextMeasure(lines, width, height, fits)`** (`vidgen.layout`, exported): how
  `fit_text` would wrap the text, estimated from the cached word widths (`_Metrics`) without
  building a `Paragraph`; `fits` is false when a word is wider than `max_width` (`fit_text`
  would scale the block down). Estimates run a few percent short of the built text (Pango
  kerning; `fit_text` re-wraps narrower when a built line comes out too wide), so planners
  measure at ~0.97 of the width and check the built result. Reason: building a `Paragraph`
  costs 0.1–0.3 s for a long text; the timeline's size search over two layouts took 90 s for
  10 long events when it built every candidate, 5 s with `measure_text`.
- **`fit_text(..., balance=False)`** (also `fit_text_sized`, `measure_text`): wrapped text is
  re-wrapped at the narrowest width (down to half of `max_width`, binary search on the
  metrics) that keeps its number of lines, so a two-line title has no lone last word.
  Additive; off by default (existing scenes unchanged).
- **`timeline`** (`scenes/timeline.py`; reference docs/CONFIG.md): `events` (2–10
  `TimelineEvent`: `date: str | int | float` — a YAML date object becomes its ISO string, bool
  rejected — `title`, `text`, `icon`, `at`), `heading`, `orientation: auto | horizontal |
  vertical` (`auto`: horizontal unless the frame is portrait), `sides: auto | alternate | one`,
  `spacing: even | proportional`, `reveal: per_beat | all`, `highlight` and `now` (event refs:
  an int in range is a 0-based index, else the date as shown, else the title; ambiguous →
  error), `now_label`, colours, sizes. `date_position()` parses numbers, years, `YYYY-MM` and
  `YYYY-MM-DD` (fraction of the year); proportional spacing needs a position for every event in
  non-decreasing order (validation errors otherwise).
- **Geometry** in axis coordinates (`along`, `across`; `_point`): events at `pad + q·usable` with
  `pad` = half an even gap at both ends; proportional `q` is blended towards even (`w` in steps
  of 0.05) until neighbours keep `min_gap_share` (0.45) of the even gap and the markers do not
  touch. Each event's text (a "card": date row, title, detail) may use the stretch along the
  axis up to halfway to the neighbouring events *on the same side* (less `card_gap`) or the
  body's end; across it, the room from the stem (`stem` 0.3 beyond the marker) to the body's
  edge. Horizontal: card width = that stretch (≤ `max_card_width` 5.2), centred over the
  marker and pushed inwards at the ends; vertical: card width = the side's room (≤ 5.6), card
  height ≤ the stretch, text aligned towards the axis, the date's line level with the marker
  where there is room. Everything is centred across the axis at the end.
- **Fitting** (`_plan` per side mode): one factor for all events; date/title/detail sizes are
  `max(min(size, floor), size·factor)` (floor = `readable_size()`, the heading role's for
  titles). Factor 1, then 1.2 (`growth`) if that adds no wrapped lines, else reduced (×0.75–0.93
  per try) to the factor where every size is at its floor. Measured with `measure_text`
  (balanced, at 0.97 width); the built cards (`fit_text(balance=True)`) are scaled down alike if
  one is still taller than its room. Not fitting at the floor → `fits` false → the warning
  "split it into two timelines (or shorten titles and texts)" (lint `min_font` reports it too).
  `sides: auto` builds both plans and keeps the better by (fits, factor up to 1, fewer lines,
  factor): growth never decides the layout; typically alternating in 16:9, one column right of
  the axis in 9:16 for ≤ 6 events, alternating for more.
- **Drawing**: track (`axis_color`, 0.55 opacity, tip) from half a gap (≤ 0.7) before the first
  event to as far past the last; markers (`icon_radius` 0.3 disc on the background colour,
  outlined, with the icon or a small dot, when any event has an icon; else a filled 0.12 dot);
  stems; one progress segment per event (`progress_color`, from the previous marker's edge or
  the track start to its marker's edge; `DashedLine` after `now`); `now` → a ring in
  `now_color` and a tag (pill on `surface`, outlined in `now_color`, as `stat`'s chip for
  contrast) after the date; events after `now` have hollow markers.
- **Steps / targets**: steps `[event 1 (with heading and axis), event 2, ...]` (`all`: one
  step), then the `highlight` step (others `dim_to` 0.55; the chosen marker ×1.2 and its title
  in `highlight_color`). `_reveal(indices)` builds one `Succession`: the axis if not shown,
  then per event not shown the missing segments up to it and its marker/stem/card — so an
  early `reveal` of event 3 grows the line through event 2's position without showing event 2,
  and the scene's own steps never repeat an entrance. Targets `heading`, `axis` (the track),
  `event<N>` / `event:<date>` (marker + stem + card; segments are not part of a target).


## 31. Refinements (Step 28, graph layout and `diagram`)

- **`vidgen.graph`** (manim-free; exported by `vidgen.api`): `layered_layout(nodes, edges, *,
  direction="LR"|"TB", layer_gap=1.0, node_gap=0.5, routing="straight"|"orthogonal",
  port_spacing=0.2, port_spread=0.6, label_margin=0.15, sweeps=12) -> GraphLayout(nodes:
  {id: NodePlace(x, y, width, height, layer, order)}, edges: [EdgeRoute(source, target, points,
  reversed, label_at)], layers, width, height, direction, crossings, reversed_edges)`. Nodes
  are ids or `GraphNode(id, width, height, shape)` (`box`/`ellipse`/`diamond`/`stadium`: the
  outline ports are clipped to); edges `(source, target)` or `GraphEdge(source, target,
  label=(w, h))`. Result centred on the origin, y up, in the nodes' units. Unknown ids, duplicate
  ids, self-loops, unknown direction/routing/shape → `VidgenError`.
- **Phases.** (1) Cycles: depth-first search in input order; back edges are laid out reversed
  and their routes reversed again (`EdgeRoute.reversed`). (2) Layers: longest path from the
  sources, then each source with successors moves to just before its nearest successor;
  edges spanning *k* layers get *k − 1* dummy items. (3) Order: from two starts (input order and
  its reverse; later layers by first predecessor), barycenter sweeps alternately down and up
  (ties keep the current order) with adjacent-swap transposition, best order kept; phases 1–3
  depend on the topology only and are cached (`_topology`, `lru_cache`), because the scene lays
  out one graph at many sizes. (4) Coordinates: a layer's centre line is spaced by the deepest
  item of the neighbouring layers plus the gap (`layer_gap`, or label extent + 2 `label_margin`
  for a labelled edge leaving its source through that gap); across, items are packed with
  `node_gap` (half next to a dummy), then 10 passes (alternately towards predecessors and
  successors, ending with successors so parents sit centred over their children) set each
  layer to the weighted least-squares fit of the neighbours' mean under the separation
  constraints (pool adjacent violators; dummies weigh 2x so long edges run straight).
  (5) Routes: ports on the facing sides, ordered by the cross position of the edge's next point
  and spaced `port_spacing` apart within `port_spread` of the side, clipped to the shape;
  `straight` = polyline through the dummies; `orthogonal` adds per gap a run in a lane of its
  own (lanes assigned greedily, downward runs before upward ones, so nested runs do not
  cross). Label anchor: the first segment from the real source at the middle of its gap (for
  orthogonal routes the nearest point of the route to it). `crossings` counts crossings of the
  dummy graph between neighbouring layers.
- **`diagram`** (`scenes/diagram.py`; reference docs/CONFIG.md; registered again as
  **`flowchart`**: `scene("flowchart")(Diagram)` — the same class under a second name, so
  `list-scenes`, the schema and `validate` treat it as a type of its own; the docs test points
  a second name's CONFIG.md section to the first). Params: `nodes` (1–30 `DiagramNode`: a string
  is `{id}`; `id` letters/digits/spaces/`_.-`, `label`, `shape` box | round | pill | circle |
  diamond | cylinder, `icon`, `color`), `edges` (≤ 60 `DiagramEdge`: `{from, to, label, style:
  solid | dashed, color}`, `from` is the alias of the field `source`; strings `"a -> b"`, `"a ->
  b: label"`, `"a --> b"` dashed, chains `"a -> b -> c"` expanded by a before-validator of
  `edges`; JSON Schema `anyOf` string (`pattern: "->"`) | object), `heading`, `direction`
  auto | LR | TB, `routing` curved | straight | orthogonal, `reveal` nodes | layers | all,
  `steps` (per step a ref or a list of refs; a ref is a node id or `a->b`, spaces around `->`
  ignored), `highlight` (refs), `shape`, colours, `size`/`edge_label_size`/`heading_size`.
  Validation (model validator): duplicate ids, unknown nodes in edges (`difflib` suggestions +
  the node list), self-loops, duplicate edges, unknown or repeated refs in `steps`, unknown
  refs in `highlight`. `describe` now shows a field's alias (`from`) in `list-scenes` and its
  JSON `name` (no other built-in uses aliases).
- **Fitting.** Per direction option (`auto`: the frame's orientation first; the other one is
  kept only if its text is `direction_bias` 1.1x larger) and per label wrap width (`wraps` 3.2,
  2.3, 1.7, 4.4 units at 32 pt, scaled with the size), the size factor goes from `growth` 1.3,
  1.15, 1, then x0.9 down to where label and edge-label sizes both sit at their floor
  (`readable_size() x floor_margin` 1.05: lint measures short lowercase labels a little small);
  the first factor whose `layered_layout` fits the body wins. The plan key is (fits, factor
  capped at 1 x bias, factor x bias): growth never decides the layout. Then `_spread` widens the
  gaps (layer factor 1.8 → 1, node factor 1.4x that) while it still fits. Node boxes come
  from `measure_text` (content + padding 0.32 / 0.2 x size/32 units; circle = diagonal; diamond:
  half-diagonals `a = x + 1.5 y`, `b = a / 1.5`; pill: + 0.35 h; cylinder: + two rims);
  icons stand above the label in LR layouts, circles and diamonds, else left of it. Nothing
  fits at the floor → scaled down whole and the warning "split it into smaller diagrams (or
  shorten labels)".
- **Drawing.** A node is `VGroup(shape, icon?, label)` (z 1): the shape filled with its colour
  at `fill_opacity` 0.1 (a tint: `highlight` style `color` then paints a highlight tint under a
  highlight-coloured label that keeps 4.5:1 on light presets; 0.14 did not) and stroked at 3.
  Cylinder: a closed body path (top arc, side, bottom arc, side) + the front rim arc without
  fill. An edge is `VGroup(line, tip, label?)`; `curved` lines are cubic Béziers between the
  route points with handles along the main axis (S-curves; the arrowhead points along the
  axis into the node), `straight`/`orthogonal` polylines; the line stops 0.9 tip-lengths before
  the route's end and a filled triangle tip ends on the outline; `dashed` = `DashedVMobject`.
  An edge label sits on a pill of the background colour (z 2, not part of the target, so
  colour highlights do not paint it) at the route's label anchor.
- **Steps.** Groups per step: `steps` (+ one step with the nodes no step names), else per
  `reveal` in layout order (layer, then order). A step plays in waves (`_reveal`): nodes no
  pending edge leads to, then edges whose source is on screen (`Create`, linear; dashes one
  after another; then tip and label), then the nodes they reach, … (a cycle inside a step starts
  at its first node). Edges between nodes on screen come along unless a later step names them;
  a named edge brings its ends. `highlight` adds a last step: listed nodes (outline stroke
  1.5x, tint 1.6x, icon in `highlight_color`; labels unchanged) and edges (listed, or between
  consecutive listed nodes; line 1.6x wider) recoloured, every other node/edge `dim_to`
  `dimmed_opacity` 0.55. `reveal(fraction=0.75, cap=1.6)`, `outro` 0.5.
- **Targets.** `heading`, `node<N>`/`node:<id>` (outline = the shape, so a `box` frames it),
  `edge:<from>-><to>` (line, tip, label; its entrance as a target brings its hidden ends first).


## 32. Refinements (Step 29, `process` and `network`)

- **Network helpers** (`helpers.py`, exported; kphi3 renders unchanged): `column(n, x, gap, y0,
  r, color, *, horizontal=False, skip=None)` — `horizontal` lays the dots out left to right along
  `y0` centred on `x`; `skip=k` spreads `n` dots over `n + 1` slots leaving slot `k` empty (an
  ellipsis). `edges(a, b, pairs, color, width, opacity, *, colors=None, shorten=0.0)` — one
  colour per pair, lines trimmed by `shorten` at both ends (from the rim of dots).
  `grouped_pairs(n, groups, m=None)` — blocks from `group_bounds(n, groups)` (near-equal,
  `round(g * n / groups)`; identical to the old `n // groups` blocks when `groups` divides `n`),
  block `g` of the first layer to block `g` of the second (`m` units). `sparse_pairs(n, m, ratio,
  seed=0)` — each pair kept with probability `ratio` (numpy `default_rng(seed)`), then any unit
  of either layer left without a pair gets one; sorted, reproducible.
- **`process`** (`scenes/process.py`; reference docs/CONFIG.md): `stages` (2–8 `ProcessStage`:
  a string is `{label}`; `label` unique, `icon`, `text`), `heading`, `layout: auto | row | snake |
  column`, `reveal: per_beat | all`, `loop` (+ `loop_label`), `input`, `output`, `token`,
  `token_icon`, `token_label`, colours (`stage_color`, `active_color`, `token_color`, ...) and
  sizes (`size`, `text_size`, `io_size`, `heading_size`). `auto`: `column` in portrait; else
  `row`, or `snake` (two rows, the second right to left, joined by a turn on the right) for ≥ 4
  stages when its text is `layout_bias` (1.1x) larger — growth never decides; when no layout
  fits, the one that needs the least scaling down.
  **Planning** (`_fit`/`_geometry`): one size factor for label/detail/io sizes (up to `growth`
  1.2 without more lines, down to the factor where every size sits at `readable_size()`),
  measured with `measure_text`; card width = the room left after the io labels (which stand
  above their arrows: lead = max(gap, label width + 0.3)) and gaps (`gap` = max(0.7, token
  diameter + 0.45)), capped at 3.4 (6.0 in a column), never narrower than the longest word;
  height = the tallest content + padding, at least half the width in rows when there is room
  (`card_aspect`), +0.5 u of air in a column; room before the first stage for the token's halo
  (1.7 r) and for its tag centred over the start; bands for the token tag (above rows, a lane left of
  a column), the loop (below a row, a lane right of a column, below and left of a snake). Not
  fitting → warning "shorten the labels and texts (or split the process into two scenes)" and
  the drawing (with the token's paths) is scaled into the body.
  **Drawing**: cards = surface-filled rounded boxes (z 2; content z 3, so a box animated on its
  own does not cover its text) with icon above the text (rows) or left of it (column);
  connectors and the loop are rounded polylines (`rounded_path`, corners as quadratic arcs) with
  a filled tip; the token (z 1: under the cards, over the connectors) is a dot with a halo or an
  icon in a disc; it waits in front of a stage on the incoming connector's tip
  (`rests[i]`); its path to the next stage runs from there through the stage's centre (hidden
  behind the card) and along the connector (`paths[i]`). The tag (pill, z 4) follows the token
  on the same path shifted by a fixed offset (no updaters); it fades while the token loops.
  **Steps** (`_arrive(i)`): previous stage back to `stage_color`, then the token moves while the
  connector it rides grows (if not shown), then the stage appears already active (or, if shown,
  turns active: outline `active_color` at 2x width, icon recoloured); `input` and heading come
  with step 1, `output` after the last stage arrives; `loop` adds step n (token along the loop to
  below/beside stage 1, which becomes active again). `reveal: all`: everything in step 1, later
  steps only move the token. `reveal(fraction=0.75, cap=1.6)`.
  **Targets**: `heading`, `input`, `stage<N>`, `stage:<label>` (outline = the box),
  `connector<N>`, `loop`, `output`, `token` (token + tag). An early `reveal` of a stage shows the
  card only; its step still moves the token there.
- **`network`** (`scenes/network.py`): `layers` (2–8 `NetLayer`: an int is `{size}`; `label`,
  `show`, `connect`, `color`), `heading`, `connect` (`Connection`: `{type: dense | sparse |
  grouped | one_to_one | none, ratio, groups}`, or a string `dense`, `sparse:0.3`, `grouped 3`;
  JSON Schema `anyOf` string | object; default `"dense"`), `direction: auto | LR | TB`,
  `max_neurons` 8, `show` 6, `counts: auto | all | none`, `count_format` `{n:,}`, `reveal:
  layers | all`, `passes` 1 (0–4), `highlight` (`"L.i"` refs, 1-based, units as drawn),
  `max_edges` 64, colours, `group_colors`, `edge_opacity`, sizes. Validation: unique labels, no
  `connect` on the first layer, `count_format` formats `n`, highlight refs in range.
  **Layout**: LR — layers `min(3.4, width / n)` apart, captions (bold label, dim count) in a band
  below; TB (portrait) — rows `min(3.0, height / n)` apart, captions right-aligned in a column
  left of the rows. Unit gap = `min(0.85, room / slots)` (slots = the most drawn units + 1 for an
  ellipsis), radius 0.3 x gap within 0.07–0.22; a truncated layer is `column(..., skip=(m+1)//2)`
  with three small dots in the hole. Edges between drawn units via `Connection.pairs` (sparse
  seeded by the layer index), thinned to `max_edges` (`_thin`: a reproducible sample plus one
  pair per unit that lost all), opacity `clip(2.4 / sqrt(count), 0.2, 0.75)`, width from the
  radius, trimmed to the rims; grouped edges coloured per block with `palette_color`.
  **Steps**: layer k = its incoming edges grow (`Create`, lag) then its units grow one by one with
  the ellipsis and caption; a pass = `LaggedStart` (lag 0.62) of: layer 1 `Indicate` in
  `pulse_color`, then per pair `ShowPassingFlash` copies of the edges and the next layer's
  `Indicate`; highlight = listed units filled `highlight_color` and ×1.3, edges between
  consecutive listed units in neighbouring layers recoloured ×2 width (a missing one drawn), the
  other units, ellipses and edges `dim_to` 0.3. `reveal(fraction=0.75, cap=1.8)`.
  **Targets**: `heading`, `layer<N>` / `layer:<label>` (units, ellipsis, caption), `edges<N>`
  (when the pair has edges), `neuron<L>.<i>` (one dot).


## 33. Refinements (Step 30, chart helpers, `scatter` and `histogram`)

- **`vidgen/charts.py`** (exported by `vidgen.api`; reference docs/EXTENDING.md "Charts").
  Numbers: `axis_ticks(lo, hi, max_ticks=6, *, log=False)` (= `nice_ticks`, or powers of ten:
  1-2-5 steps within two decades, every k-th decade beyond `max_ticks`; `log` needs `lo > 0`);
  `short_number(v, decimals=None)` (`k`/`M`/`B`/`T`); `tick_texts(ticks, fmt=None, unit="", *,
  log=False)` (`fmt` if given; log: `short_number`; else one shared decimals count
  (`auto_format`), suffixed from 10 000 on, `0` stays `0`). `LinearFit(slope, intercept, r2)`
  (callable, `equation(digits=3)` with typographic minus) from `linear_fit(xs, ys)` (`np.polyfit`;
  r² 1 for constant y; < 2 distinct x → `VidgenError`).
- **Axes.** `ChartAxis(lo, hi, ticks, labels, log=False, title="")` (frozen; `fraction(v)`,
  `contains(v)`); `value_axis(values, *, lo, hi, max_ticks, log, fmt, unit, title,
  include_zero)`: domain = data extended to the outer ticks, unless `lo`/`hi` fix an end (then
  ticks outside are dropped) — the old `line_chart` rule. `chart_axes(area, x, y, *, size,
  color, axis_color, grid="y"|"x"|"both"|"none", lines="x"|"xy", right, top, theme) ->
  ChartAxes(plot, x, y, label_size)` with `x_pos`/`y_pos`/`point`/`inside`, `group` and parts
  `lines`, `grid`, `x_labels`, `y_labels`, `x_title`, `y_title`. Layout: y tick labels right-
  aligned left of the plot (gap 0.45 cap + 0.05), y title above them left-aligned at the
  area's top (below `top`), x labels below, x title under them centred (clamped to the area);
  the plot's right end moves in by half the last x label when a tick sits at the end. Label
  thinning `_stride`: the smallest k such that every k-th label clears its neighbour (x: 0.35
  cap + 0.15; y: 0.9 cap), plus the last label when it has room. Gridlines: dashed, stroke 1,
  opacity 0.4, at the *labelled* ticks (not on the axis line). Sizes: `chart_label_size(size)`
  = `max(theme.size(size), readable_size())`.
- **Legend.** `chart_legend(entries, max_width, *, size, color, stack, theme)` (entries `(name,
  colour, swatch)`, swatch `line` | `box` | a marker; rows wrapped to `max_width`, `stack` one
  per row; scaled down only if one entry is wider). `legend_spot(size, plot, points, *, pad=0.15,
  corners=(top_right, top_left, bottom_right, bottom_left))`: the first corner whose box (pad
  inside the plot, pad of air) contains no frame point. `auto_legend(...)`: one row, else
  stacked, in a free corner on a framed panel (`RoundedRectangle`, background fill 0.85, `dim`
  stroke 1 at 0.5; `LEGEND_BUFF` 0.15; `z_index` 1, so gridlines drawn later never cover it —
  lint `covered_text` found exactly that in 9:16) → `(legend, centre)`; no free corner →
  `(row legend, None)` and the caller reserves `top` room and puts it above the plot.
  `sample_path(points, step=0.1)` samples polylines for it. `chart_marker(kind, radius,
  colour)`: `CHART_MARKERS` circle / square (side 1.7 r) / triangle (height 1.95 r) / diamond
  (side 1.6 r, rotated), similar visual weight.
- **Title and caption.** `chart_title(text, *, size="heading", color, growth=None, area)`: bold,
  `heading` role, `balance=True`, fitted into and centred in `region("header")`, x
  `PORTRAIT_TITLE_GROWTH` 1.3 in portrait (as `bullets`). `chart_caption(text, area, *, size,
  color)`: `fit_text` to the area width, ≤ 15 % of its height, at its bottom.
- **`bar_chart` / `line_chart` refactored** (Step 22 findings): title via `chart_title` (was the
  top of the safe area, 18 % high: in 16:9 now a few px lower, centred in the header band; in
  9:16 1.3x larger); caption via `chart_caption`. New params (additive): `title_size`,
  `title_color`, `label_size` (both), `value_size` (`bar_chart`). `bar_chart`: category labels at
  `label_size` (`caption`, was `caption`/`small` by count) with the readable floor as `min_size`;
  value labels: `_value_style` tries the wanted size (`value_size`, default `body`/`caption` as
  before) and 0.9x on one line, then with a word unit (leading space) under the number
  (`unit_ratio` 0.8), then 0.8x, then 0.7x/0.6x, then the floor; nothing fits → in portrait with
  `horizontal` unset the bars turn horizontal (as before also for > 5 bars), else the labels are
  scaled to the slot as before. Horizontal slots are 1.1 (landscape) / 1.5 (portrait) units, at
  least the tallest label + 0.3, bars up to 0.9 thick. The count-up rebuilds a one- or two-line
  label (`become` + `original_text` per `Text`). `line_chart` on `value_axis` + `chart_axes`:
  ticks label with the decimals the *ticks* need (`2.4` instead of `2.40`; `value_format` still
  applies to both), x labels thinned by width instead of "at most 7 (4 in portrait)", tick /
  axis / end labels and legend at `label_size` (`caption`, was `small` for ticks), legend via
  `auto_legend` (inside the plot when a corner is free, else above, as before). 16:9 output:
  same structure; ticks and axis titles 24 instead of 20 pt, title ~0.1 unit lower.
- **`scatter`** (`scenes/scatter.py`; reference docs/CONFIG.md): `ScatterPoint` (`also_accepts
  = (list,)`: `[x, y]` / `[x, y, label]`; JSON Schema `anyOf` array (prefixItems) | object;
  `label`, `group`), `ScatterSeries` (`name`, `points`, `color`, `marker` auto → `CHART_MARKERS`
  by position); `series` dict or list; axes `x_/y_ min/max/log/format/unit/label`; `trend: none |
  each | all` + `trend_label: none | equation | r2 | both` + `trend_color`; `reveal: series |
  groups | all`; `show_labels: all | highlight | none`; `highlight` refs (`<series>@<N>`,
  `<series>@<label>`, a unique label; `Params.point_ref`); `legend` (default > 1 series);
  `point_radius` (default 0.11 / 0.085 / 0.065 / 0.05 for ≤ 20 / 60 / 150 / more points).
  Validation: unique series names and labels per series, positive values and bounds on log
  axes, points inside explicit bounds (no silent clipping), trend only on linear axes with ≥ 2
  distinct x per fit, `trend_label` needs a trend, `groups` needs a group.
  **Layout**: x ticks ≤ 7 (4 in portrait), y ≤ 6 (8 in portrait), grid both, both axis lines;
  legend via `auto_legend` avoiding markers and trend samples. Markers (z 2) get a 1.2 stroke in
  the background colour (overlaps stay apart); trend lines (z 1) run over the fitted points' x
  range, cut where they leave the y domain. Point labels (z 3, a background-colour outline as
  a halo) try right, left, above, below, then diagonals, scored 4·outside the plot + 2·overlap
  of labels/legend + markers covered + 2·trend lines crossed; trend labels are placed after
  them: beside the line's end (away from the line), then on the normal at 6 places along it
  (offset by the label's extent along the normal, so no slope makes them cross), scored 5·lines
  crossed + points covered + 3·boxes; both clamped to the plot. **Steps**: per group a
  `LaggedStart` (lag `min(0.25, 2/n)`) of point pops (`GrowFromCenter`, then the label) sorted
  by x; then the trend (`Create`, linear, then its text); then the highlight (rings 1.9 r in
  `highlight_color`, labels with `show_labels: highlight`, the rest `dim_to` 0.35).
  `reveal(fraction=0.8, cap=2.0)`. Targets per the table; a label that is a number another
  point has as its index names nothing (the index wins).
- **`histogram`** (`scenes/histogram.py`): `values` with `bins` (int: equal bins via
  `np.linspace`; rule `auto` | `sturges` | `sqrt` | `fd`: numpy's bin count, width rounded by
  `nice_width` (nearest of 1, 2, 2.5, 5 x 10^k on a log scale), edges `aligned_edges` on its
  multiples), `bin_width` (aligned, or from `bin_range[0]`), `bin_range`; or `counts` +
  `edges`; `MAX_BINS` 60. `compare` (`HistogramCompare`: `name`, `values` | `counts`, `color`
  `secondary`) binned on the same edges. `percent` (each distribution's own total). `mean` /
  `median`: exact from values; from counts the mean of bin middles and the median interpolated
  in its bin. `highlight`: 0-based indices or range labels. Range labels (`bin:<range>`) are
  `tick_texts(edges, x_format)` joined with `-` (`10-20`, `0-10k`).
  **Layout**: x ticks at the edges when the bins are round (equal nice widths, edges on their
  multiples, or `x_format` given), else round ticks inside; y from 0 (`include_zero`), unit `%`
  with `percent`. Bars inset by `min(0.03, 8 %)` per side. `compare` = a `Polygon` fill at 0.1
  under its step outline (stroke 4). Marker labels (bold, in the marker colour) stand above the y
  title, the second one a line higher if they would touch; room for them is reserved with
  `chart_axes(top=)`; the dashed line runs from the axis up to its label. Legend (with
  `compare`: `name` or `data` as a box, the compare name as a line) via `auto_legend` avoiding the
  outlines and verticals through every bar. **Steps**: bars grow (`ReplacementTransform` of a
  flattened copy, `LaggedStart` lag `min(0.15, 2/n)`), compare, mean, median, highlight (chosen
  bars filled `highlight_color`, others `dim_to` 0.35) — each its own step.


## 34. Refinements (Step 31, `pie` / donut and `heatmap`)

- **Colour helpers** (`vidgen/charts.py`, exported). `mix_colors(a, b, t)`: `a` at opacity `t`
  over `b` in sRGB (what alpha blending shows), `#RRGGBB`. `text_color_on(fill, min_ratio=4.5)`:
  the theme's `text` or `background`, whichever contrasts more with `fill`; below `min_ratio`
  white or black (the better one; the worst case over all fills is ≈ 4.58:1). `ColorScale(lo,
  hi, stops, kind, center)` (frozen): `fraction(v)` (clamped; diverging: 0.5 at `center`, each
  side scaled to its own end), `at(f)` (OKLab interpolation between `(fraction, hex)` stops —
  Ottosson's matrices, sRGB gamma via `lint.color`), `__call__(v)`. `color_scale(values, kind,
  color, low_color, high_color, center, lo, hi)`: sequential stops `mix(color, background, 0.14)`
  → `color` (lightness monotone, "more = more contrast with the background" on light and dark
  presets); diverging `low_color` → `mix(text, background, 0.1)` → `high_color`, domain `center ±
  max distance` unless `lo`/`hi` are given (then `center` must lie inside: `VidgenError`).
  `color_bar(scale, length, vertical, thickness=0.26, size, color, title, max_ticks=5, fmt,
  unit)`: 48 opaque segments + a faint frame, ticks from `axis_ticks` inside the domain with
  `tick_texts` labels (right of a vertical bar, below a horizontal one; thinned with `_stride`),
  optional title above; `VGroup(bar, ticks, labels[, title])` centred at the origin.
- **`pie`** (`scenes/pie.py`; reference docs/CONFIG.md). `Params.slices()` → `PieSlice(label,
  value, color, other)` after `sort` and grouping (`other_below` %, `max_slices`; grouping only
  when ≥ 2 slices qualify; the group is last, `other_color`). Colours: own / one colour / the
  palette in order, past its length lighter shades (`mix(base, background, max(0.4, 1 - 0.3k))`),
  the last slice never equal to the first. Angles from `start_angle` (90 = top), clockwise by
  default; wedges are `AnnularSector`s (inner radius 0 for a pie) with a 2 px background-coloured
  edge. **Layout** (`_plan`): for label sizes from `label_size` down to the readable floor
  (x `floor_margin` 1.05), modes `sides` then `keys` (`legend` alone when `uses_legend()`:
  `legend` or > 6 slices — static, so `target_names` knows it). In each mode up to four rounds:
  labels that fit inside their slice (box corners and edge midpoints inside the annular sector,
  6 % margins; spots at 0.6 / 0.5 / 0.68 / 0.4 r for a pie, mid-ring for a donut; wrap widths
  1.2 / 0.8 / 0.5 r) go inside, the rest outside; `sides`: columns at `r(1 + explode) + ELBOW
  (0.2) + LEAD (0.5)` left/right, room reserved per side only for the sides that have labels,
  labels stacked top-down near their elbow height (`_stack`: `gap` 0.12, pushed back up from the
  bottom; the smallest slices' labels dropped if a side cannot hold them), leader = rim → radial
  elbow → label; `keys`: `chart_legend` swatches + "name value", wrapped rows below the pie in
  9:16 (≤ 60 % of the body, else dropped), stacked beside it in 16:9 (wrapped rows if taller
  than the body), pie and key centred together. The first layout with nothing dropped and
  radius ≥ 0.3 x the body's shorter side wins; else the one dropping fewest (warning). Inside
  labels use `text_color_on(slice colour)`. Donut centre: `center_text()` (the total via
  `value_format`/`unit`) bold in the heading role, fitted to 0.78 x the hole's diameter, plus
  `center_label` in `dim`. **Steps**: wedges grow by `UpdateFromAlphaFunc` rebuilding the
  sector (invisible at alpha 0, the original at 1); `all` = one continuous sweep (each wedge's
  rate is its share of `smooth` over the first 70 %), labels / leaders after 65 %; `per_beat`
  sweeps over 0–65 % and the label over 55–100 % (`window(a, b)` rate functions). Highlight step:
  the wedge (and an inside label) shifts by `explode x r` along its middle, an outside leader's
  first corner follows (`Transform` to the moved polyline), other wedges `dim_to` 0.3, their side
  labels / leaders / keys 0.45, inside labels recoloured with `recolor` to
  `text_color_on(mix(colour, background, 0.3))` at 0.7. `reveal(fraction=0.75, cap=2.0)`.
  **Targets**: `slice<N>` / `slice:<label>` = wedge + label (+ leader), outline the wedge;
  `center`; `legend` = the key (entrance: every slice's entrance).
- **`heatmap`** (`scenes/heatmap.py`). Params `values` (rectangular, `null` allowed, ≤ 40 x 40),
  `rows`/`columns` (unique), `scale` (`auto` = diverging when values lie on both sides of
  `center`), colours, `scale_min/max`, `show_values`, `legend`, `legend_label`, `reveal: all |
  rows`, `highlight` refs (the target names `cell<R>.<C>` / `row<N>` / `row:` / `col<N>` /
  `col:`; `Params.cells_of`). **Layout**: the colour bar (vertical right of the grid in 16:9,
  horizontal below it in 9:16; rebuilt as long as 0.9 x the grid height, 2.4–4.5 units / 0.8 x
  the grid width, 3–5 units), row labels right-aligned (≤ 25 % / 30 % of the width), column
  labels wrapped to the cell width at one size from `label_size` down to the floor (else a
  warning, scaled), cells `min(width / cols, MAX_CELL 2.2)`, height ≤ width ≤ 2.5 x height, the
  whole block centred; gap between cells `min(0.05, 0.06 x side)`; cells smaller than `MIN_CELL`
  (0.3) → warning "split the matrix". Cells are opaque (`surface` + faint outline for null);
  values at the largest size from `value_size` down to the floor at which the four longest
  strings fit (`cell - 0.12` wide, `- 0.1` high), else hidden (warning with `show_values:
  true`), each in `text_color_on(cell colour)`. **Steps**: `all` = labels, legend, and cells
  popping in (`FadeIn(scale=0.6)`) in a diagonal wave (window by `(r + c)`); `rows` = row k's
  label and cells left to right (column labels, legend, title with row 1). Highlight step:
  `highlight_color` outlines (stroke 4, z 2) round each ref's cells; other cells `dim_to` 0.3,
  their values recoloured for the dimmed cell at 0.7. `reveal(fraction=0.75, cap=1.6)`.
  **Targets**: `cell<R>.<C>` (rect + value, outline the rect), `row<N>`/`row:<label>` and
  `col<N>`/`col:<label>` (label + cells; outline a band over the cells; entrance: the hidden
  cells one by one), `legend`, `title`.

## 35. Refinements (Step 32, `code_walkthrough`)

- **`code_walkthrough`** (`scenes/code_walkthrough.py`; reference docs/CONFIG.md). Params `code` |
  `path`, `language`, `excerpt` (`"a-b"`, numbers kept), `title`, `steps`, `visible`,
  `line_numbers`, `style`, `font`, `size`, `wrap`, `highlight_color`, `note_position`
  (`auto | side | bottom`), `note_size`, `note_color`, `focus_scale`, `scrollbar`. **Per-beat
  data** is a params list aligned with the beats (as `code.highlight`, `diagram.steps`): `steps[i]`
  = `WalkStep {lines, note, focus}` or a bare line spec (`also_accepts = (str, int, list)`; JSON
  Schema `anyOf` string | integer | array | object). Steps go through `reveal(fraction=0.6,
  cap=1.0)` like every built-in.
- **Line specs** (`parse_lines` syntax, `resolve_lines(spec, source, first)`): items `N`, `N-M`,
  `/regex/`, and ranges mixing both (`/def f/-/return/`: the end is the first match at or after
  the start), comma-separated (commas inside `/.../` belong to the expression), or a list; `all`
  clears the highlight; `None` keeps the view. Checked at params validation for inline code and
  by `validate_project` for a `path` (problems prefixed `steps[k].lines`).
- **Sizing** (`_fit`, analytic, no trial builds: a listing costs ~0.1 s per line): `size` if
  the longest line fits the window width, else smaller down to `max(readable x 1.05, size giving
  TARGET_COLUMNS)`, else wrapped (`code.wrap_code`) at that size. Notes: `side` (16:9 / square,
  when the code fits beside a column of `0.3 x body` (3.4–4.8 units) without wrapping) or
  `bottom` (bar as tall as the tallest note; always in portrait). The window holds `visible` /
  as many rows as fit; window chrome (title bar with three theme-coloured dots, padding, scroll
  indicator) is drawn by the scene, not by `Code`.
- **Scrolling model.** The `Code` (background removed) stays in the scene as one mobject; rows
  out of view are taken out of its two `Paragraph`s' submobjects (`_include`), so they are not
  drawn, `is_shown(line<N>)` is false for them, and the layout dump still sees a `Code` (kind
  `code`, line numbers exempt from contrast); `lines_text.original_text` is set to the shown rows
  so lint sizes the text by its real characters. `_ViewChange` (an `Animation` without a
  starting copy) interpolates offset, per-row emphasis (1 / `DIMMED` 0.35 / 0 around a focus) x
  edge fade (`FADE` 0.75 rows beyond the window), band shapes (cut at the window's edges) and the
  scroll thumb; rows that can show are positioned lazily (`_place_row`), the others never move.
  Offsets: a selection already in view (with a line of context) stays; else it is centred (its
  start when longer than the window). The band's opacity is `BAND` 0.12, lowered (0.1 … 0.05)
  until every syntax colour keeps `min(4.5, its ratio on the window)` on it (light themes); a bar
  in the highlight colour marks the band's left edge.
- **Notes and focus.** Side notes sit level with the step's highlighted rows (pointer line + dot
  from the window edge); bottom notes in the bar. `focus` moves the camera (`MoveCamera` from
  `scenes/actions.py`) onto the selected rows' ink (numbers excluded), magnification `min(limit,
  0.84 fw / w, (0.84 fh - card) / h)`, hides the other rows and shows the note as a card under
  them built at `1 / magnification` (reads at its normal size); a view top inside the title moves
  below it (or above it); magnification < 1.05 → no focus, warning. The next view without focus
  moves the camera home.
- **Targets**: `title`, `listing` (chrome + `Code`), `line<N>` (file numbers; all wrapped
  pieces), `lines:<a-b>` (all ranges up to `ALL_RANGES_UP_TO` 40 lines, else the steps' runs),
  `note<N>` (step N's note or focus card). Entrances: a hidden line scrolls into view (`_bring`;
  leaves a focus), a note plays its step's view, `listing` the first step.
- **`code` changes** (Step 22 routed issue): wrapping targets `max(readable, min(size, size giving
  TARGET_COLUMNS 32 columns))` instead of `max(size, readable)`, so a 9:16 listing at the `large`
  scale wraps at ~32 columns, not ~25 (16:9 unchanged: `caption` already gives > 32 columns).
  New module helpers shared with `code_walkthrough`: `mono_metrics(font)` (advance and line pitch
  per point), `size_for_columns`, `text_canvas` (see below), `renumber`, `line_centers`,
  `line_runs`, `style_names` (were private methods / functions).
- **Manim text canvas** (found here, affects any long text): Manim renders `Text` with Pango on a
  canvas of the *output's pixel size* and fails the glyph check ("rendered fewer glyph(s)...") when
  text runs off it: ~60 lines of 24 pt code at 854x480, 9 at 160x90. `code.text_canvas(lines,
  size)` enlarges `config.pixel_width/height` while a listing is built (restored after; the SVG
  cache key does not include the canvas, so a clipped SVG cached by an earlier failure must be
  deleted with `build/`).


## 36. Refinements (Step 33, `equation_derivation`)

- **`equation_derivation`** (`scenes/equation_derivation.py`; reference docs/CONFIG.md). Params
  `steps` (≥ 1; `DerivationStep {tex, note, match, transition}` or a string, `also_accepts =
  (str,)`, JSON Schema `anyOf` string | object), `title`, `mode` (`history | replace`), `keep`,
  `align_at` (`"="`), `colors` (TeX → colour), `terms`, `result` (`box | highlight | none`),
  `result_color`, `size` (80; 1.25x `portrait_growth`), `color`, `dim_opacity`, `note_position`
  (`auto | side | bottom`), `note_size`, `note_color`, `note_mark_color`. Per-beat data is the
  params list aligned with the beats (as `code_walkthrough.steps`); steps go through
  `reveal(fraction=0.6, cap=1.6)` like `equation`.
- **Part isolation without Manim's substring splitting.** Manim's `substrings_to_isolate` splits
  raw substrings (`x` out of `\exp`, breaking the TeX) and `{{ }}` main parts become top-level
  `MathTexPart`s whose boundaries may cut TeX groups. Instead the scene tokenises the TeX
  (control words, control symbols, characters), finds parts as whole-token runs (spaces ignored;
  the key of a part is its tokens joined by spaces) and wraps each occurrence in its own dvisvgm
  group (`\special{dvisvgm:raw <g id='vgpartNNN'>}` … `</g>`), which Manim's SVG parser exposes in
  `id_to_vgroup_dict`. `{{ … }}` (split with Manim's own `MathTex._split_double_braces`, so the
  notation means the same as in Manim) becomes such a group too, parts inside it nest. Braces are
  added where TeX takes one argument (after `^`, `_`, `\vec`, `\frac`, … : `{\special…x\special…}`);
  a token after `\left`/`\right`/`\big…` is never wrapped. One compile per step (two more at most
  when it is broken into lines). `tex_string` is reset to the step as written (lint, layout dump).
- **Morph** (`morph(source, target, style)`): `auto` pairs parts with the same key (occurrences in
  order, bigger parts first, glyphs used once) → `Transform` per pair; the remaining glyphs go
  through `TransformMatchingShapes` (identical shapes move, others fade). `shapes`: one
  `TransformMatchingShapes`; `fade`: cross-fade. The source is always a *copy* of the step on
  screen; `_Swap` (an `AnimationGroup`) removes `hide` at setup and, at clean-up, every mobject its
  animations used, then adds the target formula whole — so the scene holds whole `MathTex`es
  between beats (targets, lint) and the source step stays intact for later actions.
- **History.** Each step has an archived copy (dimmed at hand-over: `dim_opacity`, raised by
  `readable_opacity` until every formula / note colour keeps 2.3:1 with the background — lint's
  dimmed 2:1 plus margin). When a step arrives, the live previous step hands over to its archived
  copy (moved up a row), so `term:` targets (registered on the live formula's parts) mean the
  current step only, while `step<N>` (registered on `VGroup(live, archived)`) is the line either
  way. The block is re-centred as it grows; the oldest rows fade out upwards beyond `rows`.
- **Layout** (`_layout`). Notes beside (16:9; column 0.3 × body, 3.0–4.6 units) or in a band below
  (portrait, or `note_position: bottom`; the band sits right under the tallest block, both centred).
  All steps share one scale: ≤ 1, fitting the width (aligned steps: left and right reach from the
  alignment point; others centred) and the tallest run of `rows` rows, where a side note taller
  than its formula sets its row's height. A step whose width alone would set it below `COMFORT`
  (1.5) x the readable size is rebuilt with `\\ &` before its top-level relations (`break_lines`:
  all but the first, then all), kept when it gets larger. `rows` (history, `keep` unset) drops
  while the height would push the scale below the readable size. Below it anyway: a warning.
  The readable size for math is lint's: the 75th percentile of glyph heights vs the cap height of
  `readable_size()`.
- **Errors.** `brace_problem` / unclosed or empty `{{ }}` / parts not in any step / `match` not in
  both steps → params errors (`vidgen validate`). LaTeX errors → `VidgenError` "step N does not
  compile: <TeX message> (at: <context>)" read from the `.log` Manim names
  (`tex_error_excerpt`, dvisvgm markers removed).
- **Targets**: `title`, `step<N>`, `note<N>` (entrance plays the step), `result` (last step + box;
  entrance: the step, or just the box), `term:<tex>` (parts of `terms`, `colors`, `match`, `{{ }}`).
  A `transform` jump to the last step leaves the result's box to the last step's own beat.


## 37. Refinements (Step 34, `screenshot` and callouts)

- **Callout helpers** (`vidgen/callouts.py`, exported by `vidgen.api`; reused by Step 41's callout
  overlay). An *area* is a mobject (its bounding box), a `Region`, or `[x, y]` / `[x, y, w, h]`
  (top-left corner + size, y downwards) relative to `within` (mobject or region; default the
  frame) in fractions or, `units="px"`, pixels of an `ImageMobject`'s `pixel_array` (or of
  `pixels=(w, h)`); `callout_area` turns any of them into a `Region` (a point has size 0). The
  helpers `callout_box`, `callout_circle`, `callout_arrow`, `callout_magnifier` (needs `image=`),
  `callout_spotlight` share the signature `(area, label="", *, within, units, color, label_size,
  side, bounds, avoid, scale, theme, ...)`; `callout(kind, area, label, **options)` dispatches by
  name (`CALLOUT_KINDS`). Names carry the `callout_` prefix like the `chart_*` helpers: bare `box`,
  `circle`, `arrow` would shadow common local names in `from vidgen.api import *` code.
- **`Callout(Group)`**: `kind`, `area` (Region), `mark`, `tag` (label or `None`), `steps` (parts in
  drawing order: a magnifier's source frame, connector lines, inset); `extent(pad)` (mark + tag; a
  spotlight only by its hole and tag) feeds the next callout's `avoid`; `draw(start=0)` returns
  one animation per part with staggered rate functions inside a single run time (no
  `AnimationGroup`, which would leave its own `Group` in `scene.mobjects`): mark then tag, an
  arrow's label before its `GrowArrow`; `start` delays them (while earlier callouts leave).
- **Labels** (`callout_label`): `readable_text` (bold, `label_size`, never below the readable
  size; wrapped at 0.3 x frame width, 0.6 in portrait) on a `RoundedRectangle` plate filled with
  the callout colour; the text colour is `text_color_on(plate)` (≥ 4.5:1, lint's contrast); the
  plate is drawn first, so lint reads it as the text's backdrop.
- **Placement** (`label_spot`, `tag_spot`): candidates in eight directions (arrows, insets) at
  several gaps, or on a mark's edge (tags: above at its left / right end, below, beside; inside
  its top-left corner as a last resort); each is moved inside `bounds` and scored by overlap with
  the anchor (x10), with `avoid` (x4), the shift, a preference order, being nearer than 0.7 x the
  first gap (x6: arrows keep a visible length) and overlap with `prefer_off` (x0.8: the
  screenshot's picture, so labels and insets go to free background when there is room).
- **Arrow**: straight `Arrow` (tip 0.22) or `CurvedArrow` (±45°, bulging towards the bounds'
  centre), from the label plate's edge to where the ray from the area's centre leaves it (a
  point: the point). **Circle**: an ellipse through the area's corners (x√2 + padding; flat
  areas get a minimum height). **Spotlight**: `Cutout(rectangle, rounded hole)` filled with the
  theme background at 0.62 over `cover`/`within`. **Magnifier**: the inset size is `zoom` x the
  area, limited by the room above / below (full bounds width) or beside (full height) the area,
  whichever allows more (that axis is then the only one tried); the pixels are cut from the
  image's `pixel_array` (or `source`) by the area's fractions and resampled (Lanczos) to the
  output resolution / `scale`; connectors are the convex-hull edges joining a corner of the
  source frame to a corner of the inset (`connector_lines`).
- **`screenshot`** (`scenes/screenshot.py`; reference docs/CONFIG.md). Params `path`, `title`,
  `steps` (`ScreenshotStep {callouts, focus, previous}`, a list of callouts or one callout;
  `CalloutSpec {kind, area, label, color, side, curved, zoom}` or the shorthand `{KIND: area,
  ...}`; JSON Schema `anyOf` for both), `frame` (`none | browser | window | phone`), `url`, `units`
  (`fraction | px`), `color`, `label_size`, `previous` (`fade | dim | keep`), `focus_scale`.
  Fractions are checked by the params model, pixels by `validate_project` (image size).
- **Layout**: the picture (and its frame: bar 0.065 x width, 0.4–0.6 units, taller for a
  readable `url`; phone bezels 5 % / 12 % / 10 % of the width) is fitted into the body (below the
  title) inset by 0.25 x 0.1 units in landscape, 10 % of the height in portrait. Labels' bounds are
  the body; the title bar is in every step's `avoid`.
- **Steps**: per-beat data is the params list aligned with beats, like Steps 32/33. Beat 1 plays
  the picture's entrance then step 1 (`play_steps` with two slots); `fraction=0.6, cap=1.5`. A
  step = earlier callouts leave (fade, or `dim`: box / circle / arrow / magnifier source frame to
  0.35 opacity, the rest fades) + the camera move + its callouts' `draw(start=0.4)`. Callouts are
  built once, before the first beat, step by step with `avoid` = title bar + kept callouts + the
  step's areas + the callouts placed so far; spotlights first (z-index 1, other callouts 2).
- **Focus**: the camera (`MoveCamera`) frames the union of the step's areas so it takes at most
  half of the view each way (≤ `focus_scale` / the step's number); the step's callouts are built
  with `scale = 1 / magnification` and `bounds` = the zoomed view's safe area (∩ body), so they
  read at normal size. Callouts built for another camera always leave when it changes (kept
  ones would be enlarged or tiny).
- **Targets**: `title`, `image` (picture + frame), `callout<N>` / `callout:<label>` (numbered in
  written order; entrance: `draw()`, or the step for a focus step not yet zoomed), `step<N>`
  (entrance: the step). A step whose callouts are all on screen (an early `reveal`) is skipped.

## 38. Refinements (Step 35, `video_clip`)

- **Approach: frames decoded inside Manim, not composited by ffmpeg afterwards.** Compositing a
  clip into the rendered scene with ffmpeg would be faster, but stills (§13), the layout dump
  (§15), lint (§16, §17), callouts, camera moves and beat actions would never see it. Instead the
  clip is a mobject drawn by the camera on every frame, so everything that works on an image works
  on a clip. Cost: a full-bleed 854x480 preview renders at ~0.6 s per second of video (Manim's
  image drawing and encoding dominate; decoding and scaling a frame takes ~2 ms).
- **`ClipMobject(ImageMobject)`** (`vidgen/clips.py`, exported by `vidgen.api`). Its picture is the
  frame at the scene's clock: `play(scene, at=None)` ties a shared `_Playback` (reader, timing,
  crop, decode size, clock) to `scene.renderer.time`; `get_pixel_array()` (what the camera draws)
  asks the reader for the frame at `timing.source_time(now - start)`. A time-based no-op updater
  makes Manim treat it as moving (redrawn every frame; waits are not frozen), so it plays through
  `play` and `wait` alike. `Mobject.copy` (deepcopy) shares the playback (`_Playback.__deepcopy__`
  returns itself), so the copies `FadeIn` / `Transform` make show the same moving picture.
- **Modulation.** Manim's animations and vidgen's `dim` / `highlight` actions change an image's
  `pixel_array`. For a clip that array is a 1 x 2 *modulation* — a black and a white RGBA pixel —
  and every frame is mapped through it affinely (`out = black + frame * (white - black) / 255`,
  all four channels). Interpolations (`FadeIn`), alpha scaling (`dim`, `set_opacity`) and tints
  (`highlight`: `p (1 - t) + c t`) are affine per pixel, so they act on the moving picture exactly
  as on a still. The composed frame is cached per (reader, frame serial, modulation).
- **Decoding** (`ClipReader`): PyAV, sequential; the frame showing at `t` is the last whose time
  is ≤ `t` + 2 ms (container time stamps are rounded, WebM to 1 ms); going back (a loop) or more
  than 2 s ahead seeks to the key frame before `t`. Only the current frame (and its converted
  picture) is held. Conversion is FFmpeg's scaler (`VideoFrame.to_ndarray(width, height,
  format="rgba")`) to the decode size of the whole picture, then the crop is sliced out.
  `set_resolution(scale)` sets the decode size: the size shown × `scale` (focus / zoom), as far as
  the clip has pixels inside the crop, and never less than the size shown — so at magnification 1
  the decoded frame has exactly the on-screen size and the camera copies it pixel for pixel:
  `resampling_algorithm` is a property returning `NEAREST` then (PIL perspective transform ~3 ms
  vs ~50 ms bicubic at 854x480), else `BILINEAR`.
- **Timing** (`ClipTiming(start, end, speed, loop)`): `source_time(played) = start + played ×
  speed`, modulo the span with `loop` (played time rounded to µs, so frame times summed from
  1/fps wrap exactly), clamped to `end - 5 ms` (`END_GAP`) otherwise — the frame at `end` is never
  shown, the last one before it holds. `fit_speed(span, window, low, high)` clamps
  `span / window`. In the scene the clip starts at scene time 0 (it fades in playing); the window
  is the narration (Σ beat `d + pad`) or a silent scene's `duration - outro`; `fit_duration`
  speeds one pass to the window within `fit_range`. The scene's length is never changed by the
  clip (the §5 contract): a longer clip is cut by the fade-out (log info), a shorter one holds its
  last frame (warning above 2 s; `dead_air` above 6 s) unless it loops.
- **Sound** (`clip_audio`): one ffmpeg call writes the clip's sound as it plays — `atrim` to the
  span, 48 kHz stereo, an `atempo` chain for the speed (each factor 0.5–2; pitch kept), padded /
  cut to exactly one pass in samples (so loops stay in step with the picture), `volume`, `aloop`
  when looping, `apad` + `atrim` to the scene's length, `afade` over the outro — into a temporary
  WAV that `NarratedScene.add_sound` mixes at scene time 0 (Manim's pydub mix: sounds are summed;
  narration MP3s are added at their beats). The pipeline pads that mix to the video length as for
  any scene (§5.2, Step 4). Default volume 0.25 under narration, 1 in a silent scene; no ducking
  (Step 45). `--no-audio` renders skip it.
- **`video_clip`** (`scenes/video_clip.py`, a subclass of `screenshot`'s scene class: steps,
  callouts, focus, `previous`, frames and targets are shared; `screenshot` gained `picture_name`,
  `_spec_area()` (an area and its units), `_layout(body, fill=)` (cover: the picture takes the
  room's aspect) and `_picture_entrance()` for it). Params add `caption`, `caption_size`,
  `caption_color`, `region` (`body | full | hero | left | right | top | bottom | center | bleed`),
  `fit`, `trim`, `speed`, `fit_duration`, `fit_range`, `loop`, `volume`, `mute`; `magnifier`
  callouts are rejected (a still inset of a moving picture), `frame` with `bleed` too. Callout
  areas are written on the clip's whole picture and moved into the `cover` crop (warning when
  outside it). `bleed` puts title and caption on `surface` plates (z-index 3, over callouts).
- **Targets**: `title`, `clip`, `caption`, `callout<N>`, `callout:<label>`, `step<N>`.
- Known limits: rotation metadata is ignored; variable-frame-rate files show the frame whose
  time stamp precedes the scene time (correct, but uneven if the file is); a file without a
  stated length is measured from its packets.

## 39. Refinements (Step 36, `map`)

- **Data** (`src/vidgen/data/geo/world-110m.json`, 132 KB, package data). Natural Earth 1:110m
  Cultural Vectors, Admin 0 – Countries (public domain), via the npm package `world-atlas` 2.0.2
  (`countries-110m.json`, TopoJSON, ISC) whose ids are ISO 3166-1 numeric codes; alpha-2 /
  alpha-3 codes and English names / aliases from `i18n-iso-countries` 7.14.0 (MIT).
  `tools/make_world_map.py` (maintainer script, `npm pack` of both pinned versions, or
  `--world-atlas DIR --iso DIR`) decodes the topology (delta-encoded quantized arcs), cuts rings
  that cross the antimeridian at ±180° (d3's spherical topology has jumps there; a ring round
  the pole — Antarctica — is closed along its edge), orients outer rings counter-clockwise and
  holes clockwise (so Cairo's non-zero fill leaves Lesotho open in South Africa), rounds to
  hundredths of a degree (flattened integer rings), and computes per country a label point (pole
  of inaccessibility of the largest part by a two-pass grid search) and a "main" box (parts within
  15° of the largest: France without French Guiana). Countries without an ISO code get
  `XK`/`XKX` (Kosovo) or Natural Earth's ADM0_A3 (`CYN`, `SOL`). ISO countries missing at this
  scale are listed in `small` for an explicit error. Output is deterministic.
- **Lookup** (`find_country`): one index of normalised names (NFKD without accents, casefolded,
  punctuation and a leading "the" dropped; `&` = and), claimed in priority order — codes, display
  names, then aliases (Natural Earth's short name, a curated list such as `UK`, `Holland`, `DRC`,
  then i18n-iso-countries' names) — so an ambiguous alias (`Congo`) goes to Natural Earth's
  meaning. Unknown names get `difflib` suggestions; small countries a "use a pin" message.
- **Projection**: Equal Earth (Šavrič, Patterson & Jenny 2018; equal-area, pure numpy) centred on
  the view's middle longitude. `MapView(box, area, antarctica, expand)`: projects the box's
  sampled edges, grows the projected rectangle to `area`'s aspect ratio (more map, within the
  world's outline; the world view without Antarctica is cut at 58° S), fits it inside `area`
  (`region`), and maps points with one scale. Polygons are projected once per centre longitude
  (`lru_cache`; each polygon moved by ±360° to be nearest the centre, which makes views over the
  date line work), then clipped to the view rectangle (Sutherland–Hodgman, numpy per edge).
  World view: ~280 polygons in ~25 ms; cached views ~6 ms. `cropped`: the view cuts the world at
  its sides (a regional view).
- **`map`** (`scenes/world_map.py`). Stages: stage 0 = the top-level `countries` / `pins` /
  `arcs` (with the map), stage *i* = `steps[i-1]`; steps follow `screenshot`: step *i* at beat
  *i* via `distribute`, beat 1 = intro (title, map sweep, legend, caption, stage 0) + step 1,
  `play_steps(fraction=0.6, cap=1.6)`. **Layout**: title (`chart_title`), caption
  (`chart_caption`), legend (`color_bar`, horizontal, ≤ 0.6 x body width) centred under the map,
  map and legend centred together in the body; a cropped view gets a panel (`surface` fill = sea,
  thin `dim` frame) under the countries. Countries are one `VMobject` each (rings as closed
  straight-segment subpaths built with numpy), land = `land_color` mixed 0.3 over the background
  (0.18 for countries without a value on a choropleth), borders 0.8 wide in the background colour.
  **Highlights** are copies over the base shape (fill + 1.6x border; on a choropleth an outline
  of 3.5) so a highlight can be revealed, dimmed or zoomed as its own target. **Labels** are text
  on background-coloured plates (opacity 0.88; lint reads the plate as the backdrop): a country's
  goes on its label point when it fits in 90 % of its main box and is free, else beside it via
  `label_spot` with a leader (z 3.5, under every plate); pins' labels go beside the pin (leader
  when pushed away), arcs' at the top of the arc; all avoid earlier labels and every pin of the
  same view. **Arcs**: `ArcBetweenPoints` bending 72° upwards (flipped when its top would leave
  the map), trimmed 0.13 units at pin ends, arrow tip; `Create` grows them. **Focus**: as
  `screenshot` — camera on the step's items (country main boxes clipped to the map, pins, arc
  ends) at most `focus_scale` / 0.6 of the frame, the step's labels, pins and strokes built at
  1 / magnification; labels built for another camera fade when the camera moves. Animations:
  the map sweeps west to east (each country's `FadeIn` windowed by its x), highlights fade in,
  pins drop in, arcs grow, labels follow (`window` rates).
- **Targets**: `title`, `map` (panel + countries), `legend`, `country:<a3>` / `country:<a2>` /
  `country:<name>` (one target: a highlight with its label and leader, or a valued country's
  shape), `pin<N>` / `pin:<label>`, `arc<N>`, `step<N>`. Only countries the params name have
  targets, so `target_names` stays short and static.
- Known limits: arcs are drawn on the flat map, not as great circles, and do not wrap; no
  bundled city list (pins take coordinates or a country); 1:110m drops small states; no
  graticule; a `world` view in 9:16 is a narrow strip (documented).

## 40. Refinements (Step 37, review 2)

- **Examples split**: `examples/minimal` keeps the core built-ins (title, bullets, icon_grid,
  bar/line charts, image, quote, equation, code, text_card, end_card) and the beat-action
  examples; `examples/gallery` uses every type added in Steps 25–36 once (three `chapter`
  dividers group them). Their assets moved with them (`app.png`, `clip.webm`, `train.py`; the
  maintainer scripts `tools/make_screenshot.py` / `make_clip.py` write there). A test checks
  that the two examples together use every built-in type (`flowchart` = `diagram`).
- **Header synonyms** (`SceneParams.header_synonyms`, default on; `HEADER_SYNONYMS` in
  `vidgen.scene`): a `Params` model with only one of `heading` / `title` (and of the `_size`,
  `_color` pairs) also accepts the other name, via a pydantic `AliasChoices` set in
  `__pydantic_init_subclass__` (inherited models keep it). `title`, `chapter`, `end_card` opt out
  (their `title` is the main text). Giving both names is an error (`'title' is another name for
  'heading', which is given too; keep one`). `vidgen schema` adds the other name as a property
  with the field's schema and a `not: {anyOf: [{required: [a, b]}]}`; `list-scenes` prints
  `(also: title)` and its JSON fields gain `aliases` (list; added within version 1). Target
  names: `actions.TARGET_SYNONYMS` — `title` selects a `heading` target when the scene has no
  `title`, and the reverse (`match_names` over a scene's whole name list; `find_targets` uses
  it too).
- **Unknown keys**: `config.validation_problems(error, prefix, model=None, noun="parameter")`
  rewrites pydantic's "Extra inputs are not permitted" with `describe.unknown_key_message`:
  `unknown parameter 'dim_prev'; did you mean 'dim_previous'? (known: ...)` (16 names shown),
  resolving nested models along the error location (list indexes and union tags skipped).
  Used for scene params (`validate`, `parse_params`), action options (`noun="option"`) and the
  top-level config (`noun="key"`).
- **`one_or_many(item)`** (`vidgen.api`): `Annotated[list[item] | item, AfterValidator]`, the
  value always a list. `highlight` of `diagram`, `heatmap`, `histogram`, `network`, `scatter`
  use it (a single item was an error).
- **Text on fills** (`Target.on_fill`, `NarratedScene.target(..., on_fill=)`): `(text, shape)`
  pairs. `dim_to` recolours such text with `text_color_on(shape colour mixed over the background
  at its dimmed opacity)` and keeps it at `TEXT_ON_FILL_DIM` (0.7) instead of fading it with the
  shape; `highlight` `color` / `flash` give it `text_color_on(highlight colour)` while the shape
  is painted; `fill` gives it the colour that reads on the plate-tinted shape. Registered by
  `pie` (labels inside their slice), `heatmap` (values; rows, columns, cells) and
  `screenshot` / `video_clip` (callout labels on their plates). `pie` and `heatmap` highlight
  steps use `dim_to` for their texts too (the module helper `pie.recolor` is gone). Undo:
  `Dim.revert` restores the colours of the recoloured text; `Highlight.revert` after `fill`
  likewise.
- **Scene dimming survives `until`** (`Target.scene_dim`): `dim_to(..., own=True)` (scenes)
  records the factor; `Dim` (the action) passes `own=False`, and its revert caps the restored
  opacity at `rest x scene_dim` (`_Memory.restore(cap=)`).
- **Decorations follow** (`scenes/actions._follow`): highlight boxes, underlines and fill plates
  get an updater that keeps their offset to the outline (not time-based: waits stay frozen
  frames) and scales their opacity with the anchor's (0 while it is off screen); an outline the
  scene never draws (table / comparison guide rectangles) is followed but never faded. Undo
  clears the updaters before fading them out.
- **Copy-free fades** (`helpers.Fade`, `helpers.fade_out`, in `vidgen.api`): Manim's
  `FadeIn`/`FadeOut` and every `Animation.begin` copy the mobject (`create_starting_mobject`);
  for a 57-line `code_walkthrough` that was 33 of 59 s of a preview render. `Fade` animates fill /
  stroke arrays (and a shift) of the family's `VMobject`s and returns no starting copy;
  `clear_all` (every scene's outro) uses `fade_out` (`Fade` for vector-only families, Manim's
  `FadeOut` with images/clips). `Repaint` (dim / highlight) skips the starting copy too. The
  walkthrough: 59 → 27 s (profiled, preview).
- **Portrait growth**: `comparison` points, column headings and verdict x `portrait_growth`
  (1.3, as `bullets`); `icon_grid` labels x 1.3 in portrait (reduced as before when they do not
  fit); `timeline.vertical_growth` 1.5 and `process.column_growth` 1.5 (tried, then the halfway
  factor, then the old 1.2 rule; never more wrapped lines). 16:9 unchanged.
- **9:16 world map** (`WorldMap._portrait_world`): a `world` (or `auto` → world) view in a
  portrait frame keeps the longitudes of the items (+12 % each side, at least 140°; unchanged
  past 300°) and every latitude, so the map is a regional panel instead of a strip.
- **Layout dump `rotation`** (`introspect._glyph_heights`): for a one-line text (≥ 4 glyphs)
  the principal axis of the glyph centres gives its angle; ≥ 8° counts as rotated and glyph
  heights are measured along the normal, so `font_px` (and lint `min_font`) no longer measure a
  rotated label sideways. New key `rotation` (degrees, 0 when level / several lines / math);
  `LAYOUT_VERSION` stays 1 (additive). kphi3's `lint_ignore` for its rotated label is gone.
- **`table` widths**: one-line widths are measured once per text at `measure_size` (40 pt) and
  scaled (linear in the size): a 24-row table's fitting took 85 s, 26 s now.
- **`list-icons --sheet PNG --theme [PRESET]`** (`iconlist.SheetColors`): the sheet in the
  project's theme (no value) or a preset's: background, icons in `primary`, names in `text`,
  categories in `dim`.
- **Warnings for too much content** read alike: `the <thing>'s N <items> do(es) not fit this
  frame at the readable size; <remedy>` (`heatmap` and `comparison` reworded).
- **Header bands alike**: `table`, `code`, `code_walkthrough`, `equation_derivation`,
  `screenshot` and `video_clip` (framed) build their title with `chart_title` (1.3x in portrait,
  balanced lines) like the charts and the `heading` scenes; their 9:16 titles were ~1.3x
  smaller than the others'. A `table` caption follows a short table (`Table._tuck`: at most
  `caption_gap` 0.45 under it, both centred in their space) instead of standing at the frame's
  bottom.
- **Test markers**: `slow` now also marks the parametrized render sweeps (every scene type x
  orientation, every target, every preset) and every test function over ~1.5 s, so `pytest -m
  "not slow"` stays a quick check (~1.7 min on a 2-CPU box, 1257 tests) while the full suite
  (~14 min) runs everything.

## 41. Refinements (Step 38, overlays: framework, `lower_third`, `watermark`)

- **Config.** `VideoConfig.overlays: list[OverlayConfig]` (`config.OverlayConfig`, `extra="allow"`
  like actions): `type`, `id` (default the type; `<type><n>` (1-based) when several id-less entries
  share a type), `scenes` (`all` | ids), `exclude`, `from` / `to` (field `from_`, alias `from`:
  seconds in the video, or a scene id = its start / its end), `reserve`; every other key is an
  option of the type (`OverlayConfig.options`). `SceneConfig.overlays: bool | {id: bool |
  mapping}` (default `true`): `false` = none on the scene; per id `false`, or a mapping of option
  overrides (+ `reserve`; the other common keys are an error); a mapping with `type` under an id
  that is no video-level id = an overlay of that scene only (no `scenes`/`exclude`/`from`/`to`).
  Reference: docs/CONFIG.md "Overlays".
- **Registry.** A third kind next to scene types and actions (`registry.OverlayType`,
  `register_overlay`, decorator `overlay(name, *, override=False)`, `find_overlay`,
  `overlay_names`, `all_overlays`, `unknown_overlay_message`; same two layers and collision rules;
  `Snapshot` is now a triple). `overlays.check_overlay_class`: `Options` an `OverlayOptions`, no
  option named like a common key, `build` implemented, `layer` an int. Built-ins in
  `scenes/overlays.py` (only `from vidgen.api import *` + `.image` helpers).
- **`Overlay`** (one instance per scene render): `options`, `config`, `context`, `id`, `scenes`
  (ids it is drawn on), `span` (`from`/`to` in video seconds, `inf` without an end). Subclass
  API: `build()` (full look, placed on the whole frame, once per render), `window()` (video
  seconds or `None`), `state(t)` (hashable or `None`; **a pure function of video time**, so the
  look is identical on both sides of a cut), `pose(mobject, state)` (a copy), `settled(state)`
  (full look, for lint), classmethod `validate_project(options, project, scenes)`, class
  attributes `layer`, `lint_skip`; helpers `interval()`, `transition(t, start, end, enter, exit)`
  (smooth 0..1), property `timed` (span bounded or a window; a subclass sets `timed = True` when
  `state` reads the video time otherwise, e.g. Step 39's progress bar). `with_opacity(mob, f)`
  (exported) scales fill / stroke / image alpha of a copy.
- **Timeline contract** (`vidgen/videoplan.py`, `VideoPlan(project, fps)`, lazy and cached): each
  scene renders alone, so its position in the video is planned: a beat lasts `round((d + pad) x
  fps)` frames, `d` = the MP3's decoded length (`scene.audio_duration`, cached by path + size +
  mtime) else the word estimate; a narrated scene = its beats + `ceil(outro x fps)` (the type's
  class attribute `outro`); a silent one `max(round(duration x fps), round((duration - outro) x
  fps) + ceil(outro x fps))`. `SceneSlot(index, id, type, start, duration, beats: BeatSlot(id,
  start, end, text), chapter)`, `Chapter(title, number, scene, start)` from `chapter` scenes
  (Steps 39/49), `scene_start`, `duration`, `resolve(value, end)`. Built-in scenes match it exactly
  (tested: every frame count equal, half-frame durations aside). Overrunning scenes / extensions
  with their own timing shift later scenes: the worker records `render.overlays = {ids, timed,
  start, duration}` in the scene's timings, and `join_scenes` warns when a scene with timed
  overlays starts more than 1.5 frames away from its planned start. Only timed overlays make the
  layer read the plan (reading every MP3 before the scene).
- **Fingerprint.** With any overlay, `_overlay_inputs`: per scene id, type, duration, chapter
  title, `overlays`, beats' ids, texts and MP3 stats (what the plan reads), so editing another
  scene's narration re-renders scenes with overlays; projects without overlays are unaffected
  (the key is `null`).
- **Drawing: composited in the renderer, not mobjects of the scene.** `OverlayLayer` wraps
  `renderer.add_frame` *after* `FrameCapture` attached (outermost), so stills, the layout dump and
  the motion signal see the composited frames, and nothing in `scene.mobjects` changes: the
  `MovingCamera` (zoom, focus) and `clear_all`/outro fades never touch overlays; they never change
  timing or frame counts (tested against renders without them). Frame `k` is drawn at video time
  `start + k / fps`. A frozen wait (one frame written N times) is split into runs of equal states
  (a lower third sliding in during a silent card is drawn frame by frame; static overlays cost one
  call). Why not an updater following `camera.frame`: it would make every wait non-frozen (each
  frame redrawn), add the overlay to `scene.mobjects` (clear_all, scene walks, targets) and have to
  undo scaling for a zoom; why not ffmpeg afterwards: stills, layout and lint would not see it.
- **Patches.** Each distinct tuple of states is drawn once (LRU of 64) with two Manim `Camera`s
  showing the whole frame over black and over white: Cairo draws premultiplied while Manim
  composites images with PIL in straight alpha, so a single transparent camera gives wrong
  colours where they mix; the two opaque renders give exact premultiplied colour (`on_black`) and
  `255 - alpha` (`on_white - on_black`) for both. The patch is cropped to its visible box;
  compositing a frame is `colour + under x (255 - alpha) / 255` on that box (uint16) — within 2
  levels of Cairo drawing directly on the frame (tested).
- **Layout dump.** `LayoutRecorder` appends the overlays shown at the still (`layer.posed(frame)`),
  measured with the layer's whole-frame camera (`_Walk.camera`), after every scene object (`order`
  + 1000), paths `overlay:<id>/...`, key `overlay` (the id); frames gain `overlays: [{id, type,
  settled, skip}]`. `safe_area` is now `scene.safe_area` (equal unless reserved).
- **Reserved space.** `reserve: true` → `NarratedScene._reserved` (the built mobject's box) and
  `safe_area` = the margins' safe area cut by `overlays.avoid(area, box, gap=0.2)` (the largest of
  the four parts above / below / left / right of the box). Static for the whole scene (a layout
  is built once), so a lower third with `reserve` shrinks the scene also while it is not shown.
  The global `regions.safe_area()` is unchanged (built-ins lay out in `self.safe_area`).
- **Lint.** `overlay_overlap` (layout rule after `max_words`, default warning, `min_overlap` 0.05
  of the scene object's box): an overlay's union box over a scene text/code/math/number/icon.
  `safe_area` skips overlay objects; `text_overlap` skips overlay-vs-scene pairs; `covered_text`
  skips an overlay shape over scene text (all `overlay_overlap`'s). The runner drops objects of
  overlays not `settled` (sliding / fading at a beat end, like mid-beat stills) and, per rule,
  objects of overlays whose type's `lint_skip` names it (`watermark`: `contrast`).
- **Validation** (`overlays.overlay_problems`, in `cli.project_problems` and
  `pipeline._check_scenes` via `check_overlays`): unknown types (did-you-mean), duplicate ids,
  unknown scene ids in `scenes`/`exclude`/`from`/`to`, numeric `to <= from`, misplaced keys in scene
  overrides / scene-only overlays, unknown override ids; options as written (at `overlays[i]`)
  and with each scene's overrides (new problems at `scenes[j].overlays.<id>`), theme tokens
  checked; the type's `validate_project`. `scene_overlays(project, spec, theme, plan)` builds the
  scene's instances (sorted by `layer`), skipping timed ones whose interval misses the scene.
- **Listing / schema.** `list-scenes` prints an `overlays` section; `--json` adds `overlays:
  [{name, origin, builtin, overrides_builtin, doc, layer, lint_skip, options}]` (within version
  1). `vidgen schema`: `OverlayConfig.type` an `enum`, per type `if`/`then` with its options and
  `additionalProperties: false` (`overlay.NAME` defs); scene overrides only by shape.
- **`lower_third`**: name (bold, heading role) and optional title / icon on a `surface` plate
  (0.92) with an accent bar, wrapped at the readable size within `max_width` (0.6 of the safe
  width; 9:16 the whole width), placed with `place(..., align)` in the safe area (9:16: raised by
  `PORTRAIT_LIFT` 0.12 of the safe height). Window: its scene's planned start + `at` (seconds or a
  beat's start) for `duration`, cut at that scene's end unless `across_cuts`. State: the eased
  progress (3 decimals); pose: opacity x p, shifted `SLIDE` 0.5 x (1 - p) from its side (from
  below / above when centred).
- **`watermark`**: one of `image` (`image.load_image`, height `size` x the shorter side, at most
  0.3 of the frame wide), `icon`, `text`; `opacity` applied at build; placed `inset` (0.025 of the
  shorter side) from the frame's corner; `fade` at a bounded `from` / `to`. `lint_skip =
  ("contrast",)`.
- **For Steps 39–41.** A progress bar: `timed = True`, `state` from `t / context.duration`
  (quantised to a pixel); a chapter indicator: `context.chapters` / `context.scene.chapter`;
  captions: `context.scene.beats` (planned scene times and texts; karaoke word times can be spread
  in a beat's `[start, end]`). Callouts on any scene (Step 41) need scene targets, i.e. scene-level
  actions rather than overlays.
- Known limits: the plan cannot see what a scene's code does beyond the contract (warning at
  join); `reserve` is per scene, not per moment; overlays are drawn at the render's resolution
  from vector / image mobjects (no video overlays).

## 42. Refinements (Step 39, chapters, `progress_bar`, `chapter_indicator`)

- **Chapters** (`vidgen/chapters.py`, config only): a chapter starts at a `chapter` scene
  (`params.title`, `params.number`) and at any scene with **`SceneConfig.chapter`**: a string
  (the title) or `ChapterConfig {title, number?}` (`number` int or non-empty text). On a
  `chapter` scene the field renames the chapter in lists/indicators and keeps the card's number
  unless it gives one. `chapter_marks(scenes) -> [ChapterMark(title, number: str | None, scene,
  scene_index, card)]`. `chapter_problems(scenes)` runs in `VideoConfig`'s validator (so `parse_config`,
  `validate` and every command reject them): the same (title casefolded, number) twice; integer
  numbers not strictly increasing (text numbers and repeated chapters are skipped); a non-card
  mark right after a chapter card (the card would be a chapter of its own). Two cards in a row
  are allowed (two chapters).
- **Planned chapters** (`VideoPlan.chapters`): `Chapter(title, number, scene, start, end, index,
  count, card)` (+ `label` = number or index, `duration`); a chapter ends where the next starts,
  the last at the planned video end. `chapter_of(scene_id)`, `chapter_at(t)`; `SceneSlot.chapter`
  stays the title (now also from `chapter:` fields). **Public**: `vidgen.api.video_chapters(project,
  fps=None)` (default the final format's fps) and `Chapter` — what Step 49 (MP4 chapter metadata,
  YouTube list) reads; Step 49 adds the "Intro" chapter at 0:00 YouTube needs when the first
  chapter starts later (`video_chapters(..., intro=True)`, published lists only, §52).
  `OverlayContext.chapters` (all), `.chapter` (the scene's).
- **Fingerprint**: a scene's own `chapter:` is excluded from its dump (no pixels depend on it
  without overlays); `_overlay_inputs` carries every scene's `chapter` and a card's `number`.
- **`Overlay.shown_in(start, end)`** (default `True`, asked of timed overlays for the scene's
  slot ∩ interval): `False` drops the overlay from that scene's render, so it neither draws nor
  **reserves** there. This is the cheap part of the Step 38 "reserve is per scene" gap; an
  overlay shown during part of a scene still reserves for the whole scene (a layout is built
  once; documented in CONFIG.md `reserve`).
- **Reserved space respected by chart titles**: built-ins called `chart_title(...)` without
  `area`, i.e. in the global safe area, so a `reserve`d overlay at the top did not move their
  header (seen in 9:16 with two-line titles); every built-in now passes `area=self.safe_area`.
- **Drawing per overlay with cropped cameras** (`OverlayLayer`): patches are cached per
  `(overlay, state)` (LRU 64 per overlay) instead of per combination of states, and each is drawn
  by two cameras (black / white) cropped to the posed mobject's pixel box (points' box + strokes
  + 3 px, clamped to the frame; same pixels-per-unit and an integer pixel offset, so Cairo and
  image drawing match the whole-frame result — tested within 2 levels). A progress bar changing
  every few frames costs a strip, not two 1080p captures plus a redraw of every other overlay.
  Compositing blends the shown patches in layer order (the over operator; equal to drawing them
  together up to rounding).
- **`progress_bar`** (`scenes/progress.py`, `timed = True`): track segments (`track_color`
  `dim` at 0.35) and played segments (`color` `primary`) along the top/bottom edge, `thickness`
  0.006 of the shorter side (≥ 2 px), `inset` 0 (flush; outside the safe area, so no reserve
  needed); with `chapters`, gaps of max(2 x thickness, 3 px) at every chapter start inside the
  video. State: the number of played pixel columns, `round(t / duration x width_px)` — a pure
  function of video time, quantised to a pixel (one patch per column, ≤ width states per video).
  The fraction is of the whole planned video even with `from` / `to` / `exclude`.
- **`chapter_indicator`** (`timed = True`): one `MarkupText` label per chapter (number bold in
  `number_color`, separator and title in `color`; `total` → "index/count"; `number: false` →
  title only), at least the readable size, shortened word by word with "…" to `max_width` (0.4
  of the frame width; 9:16 min(2x, 0.85)), optional rounded plate (`background`), `opacity`
  0.85, placed `inset` from the `corner`. `build()` returns all labels (so `reserve` keeps clear
  of the widest); `pose` shows one or two. **Runs**: the scenes it is drawn on that have a
  chapter, minus chapter cards (unless `on_chapter_cards`), consecutive scenes of one chapter
  merged; runs touching another run (a `chapter:` field change, no card) cross-fade over `fade`
  centred on the cut; free ends fade in/out over `fade` inside the run. State: `((chapter
  position, opacity 2 decimals), ...)`; settled = one label at full opacity. `shown_in` is false on
  cards and before the first chapter, so those scenes get no reserve.
- **Example**: `examples/gallery` has a top `progress_bar` (3 chapter segments) and a top-left
  `chapter_indicator` with `reserve: true`; lint 0 findings in all 8 variants.

## 43. Refinements (Step 40, burned-in captions)

- **Word times** (`vidgen/speech.py`, render input; `spoken_words`, `speech_bounds`,
  `SILENCE_DB` moved here from `lint/timing_rules.py`, which re-imports them). `WordTime(text,
  start, end)`. `beat_word_times(audio_dir, beat_id, text, start, end)`: (1) a stored alignment
  that belongs to the beat's current MP3 and text; (2) else `estimate_word_times` within the MP3's
  speech (`speech_bounds`: leading / trailing silence below -40 dB of the peak cut, as lint's
  `narration_speed`); (3) else the estimate over `start..end` (no audio: the word-count `d`). The
  estimate gives each word `syllables(word) + 0.05 x letters` (vowel groups, a silent final `e`
  dropped; acronyms a syllable per letter; numbers 2 per spoken word) and a pause after it of 2
  syllables at a sentence end, 1 at a comma / semicolon / colon / dash, scaled to fill the span.
- **Alignment seam.** `voice.timestamps` (default `false`, not hashed: the audio is the same)
  makes `vidgen tts` call `provider.synthesize_timed(text, previous, next) -> (audio,
  alignment | None)` when the provider has it; ElevenLabs implements it with
  `POST /v1/text-to-speech/{voice}/with-timestamps` (JSON: `audio_base64`, `alignment {characters,
  character_start_times_seconds, character_end_times_seconds}`; the non-normalised alignment, whose
  characters are the text sent). `write_alignment` stores `<audio_dir>/<beat>.align.json`
  `{version: 1, text, audio_sha1, characters, starts, ends}` after the MP3 and before the hash; a
  beat generated without timings removes an old one; a variant copying base audio copies its
  alignment. `read_alignment` accepts it only for the same text and MP3 bytes (sha1), so a stale
  file is ignored, never wrong. Words map to characters by position (`\S+` runs of the text, or of
  its whitespace-normalised form). Tests mock urlopen; the real endpoint was never called.
- **Cue cutting** (`vidgen/cues.py`, shared by SRT and captions). `segment_cues(words, widths,
  space, max_width, max_lines, max_words)`: dynamic programming over cue ends; a cue's best line
  split is found by trying every split into ≤ `max_lines` lines that fit. Costs: each break by
  `phrase_break_cost(before, after)` — sentence end 0, clause mark or dash 1, before a conjunction 2,
  before a preposition 3, plain 4.5, right after an article / preposition / determiner 9; per cue
  1; an under-filled cue `3 x (1 - fill)^2` (fill = width share of `max_lines x max_width`, or of
  `max_words`); unequal lines `4 x (widest - narrowest) / max_width`; a sentence ending inside a
  line 3. A word wider than a line gets a line of its own. `caption_cues` times them: the first
  cue at the beat's start, the others at their first word's start, each until the next, the last
  until `until` (captions: the next beat's start / the scene's end; SRT: the narration end).
- **SRT change**: `subtitles.split_text` / `beat_cues` now use this cutting (was `textwrap` at
  42 characters + pairs of lines) and cue times follow word times (was: proportional to
  characters); `write_srt(path, timings, audio_dir)` (the pipeline passes `project.audio_dir`, so
  MP3 speech bounds and alignments time the SRT too). SRT and burned-in captions therefore cut at
  the same kind of boundaries; their cues are identical only when the caption width in characters
  equals the SRT's 42 (captions measure real text widths).
- **`captions` overlay** (`scenes/captions.py`, `timed`, `layer` 10, `lint_skip = ("max_words",)`:
  the captions are the narration, not extra words on screen). Reads `context.scene.beats`
  (planned scene times) and the project's audio folder; `shown_in` is false on scenes without
  beats (no reserve there). `build()`: an invisible band (`max_lines` lines + padding, `max_width`
  + padding) placed at the safe area's bottom (9:16: raised by `lift` 0.12 of the safe height, like
  the lower third), top or centre, then every cue of the scene as `VGroup(plate, *line Texts)`
  placed in the band (bottom / top / centre aligned). Lines are `Text`s with ligatures off,
  baselines one pitch apart (glyphs standing on the baseline are lined up), shrunk together when
  a word is wider than the line. State: the cue index (subtitles) or `(cue, word)` (karaoke, the
  last word whose start ≤ t; -1 before the first); `pose` returns the cue, karaoke a copy with the
  word's glyphs in the highlight colour scaled by `pop`, capped so it grows by at most 0.25 of a
  space per side (0.45 until Step 48: neighbours nearly touched) (the plate is that much wider). Glyph indices: Manim keeps a submobject per
  character with spaces (0.21) or without (0.19); other counts (ligatures) → no highlight.
- **Colours**: the text colour (default the best of `text`, background, white, black) and the plate
  opacity are chosen so `plate_contrast` (the plate over black and over white: the worst case of
  whatever is behind) reaches `lint.rules.contrast.min_ratio`, raising the opacity in 0.05 steps;
  a highlight that does not reach it is replaced by the first accent token that does (warning).
  `background: null`: no plate; the text gets a background-coloured outline (lint may then report
  contrast over busy scenes — the user's choice).
- **Reserve default** (framework): `OverlayConfig.reserve` is `bool | None` (default `None`);
  `Overlay.reserves` = the entry's / scene override's value, else `default_reserve()` (base
  `False`). Captions return `position != "center"`: a caption band at the top or bottom shrinks
  the scenes' safe area; centred karaoke text does not (it would cut the frame in half), so lint's
  `overlay_overlap` reports scene text under it. The reserved box is the band (stable across
  scenes), not the scene's own cues.
- **Fixes found with it**: `title` and `end_card` centred their card on the frame origin, not on
  `self.safe_area` (with a reserved bottom band their last line ran into it); both now centre on
  the safe area.
- **Fingerprint**: `_overlay_inputs` beats also carry the `.align.json` stat.
- **Example**: `examples/minimal` variants `subtitled` (16:9, `captions`) and `social` (9:16,
  `captions` `style: karaoke`); `vidgen lint` 0 findings for both.
- Known limits: cue times between alignment-less words are estimates (good to a few hundred ms on
  even speech; numbers and pauses vary); karaoke highlights one word at a time (no fill sweep);
  the caption band is reserved per scene (a scene with only one-line cues still keeps room for
  `max_lines`); a lower third and bottom captions are both placed in the global safe area and can
  overlap in 9:16 (move one with `align` / `position` or `lift`).

## 44. Refinements (Step 41, the `callout` beat action)

- **A beat action, not an overlay** (Step 38's note): a callout points at a scene's targets, which
  only exist inside the scene's render, and should move with a zoom like the rest of the scene,
  so it is a per-beat action (`scenes/callout_action.py`, built on the §26 framework and the §37
  helpers), not a screen-fixed overlay. Syntax as every action: `- callout: "bar:4K"` + options,
  or `{action: callout, area: [x, y, w, h], ...}` without a target. It reuses the action
  machinery: target validation and suggestions, `at`, `until`, `run_time`, timing inside waits,
  the JSON Schema, `list-scenes`.
- **Options**: `kind` (`box` default | `circle` | `arrow` | `label` | `spotlight` | `magnifier`),
  `label`, `area` (`[x, y, w, h]` / `[x, y]`, top-left origin as in §37), `within` (`frame` |
  `safe`, areas without a target), `units` (`fraction` | `px`), `color` (`highlight`),
  `label_size` (`caption`), `side`, `curved` (arrow), `zoom` (magnifier), `keep`, `name`.
  Checks in the model (area shape and range, kind-only options, `label` needs text, magnifier
  needs an area) and in `problems()` (a target or an area; a magnifier needs a target; `within`
  only without a target; `keep` with `until`).
- **What it points at**: the targets' outline (`Target.outline`, e.g. a bar with its value),
  else their parts on screen; several targets → one callout around all of them. With `area`
  and a target: fractions (or `px`) of the target's largest picture (an `ImageMobject` or clip
  in its family — so `image` / `screenshot` areas read off the image file), else of its box.
  Without a target: fractions of the **visible view** (`within: frame`, the camera frame when
  zoomed) or of its safe area (`within: safe`); `px` are pixels of the output frame.
- **Where labels go** (`bounds`, `avoid` of the §37 helpers): inside `scene.safe_area` (which
  already excludes `reserve`d overlays); while the camera is zoomed in, inside the view minus
  margins x scale, and the callout is built with `scale` = view width / frame width so it reads
  at its normal size (§37). `avoid`: boxes of every `Text` / `MarkupText` / `Paragraph` / TeX
  mobject on screen, callouts on screen (targets whose mobject is a `Callout`), the scene's other
  targets on screen smaller than 20 % of the view that do not hold the area's centre (a node,
  a bar; not the axes or a map), and the overlays' boxes (mapped into a zoomed view). The arrow
  and `label` kinds prefer spots off the targets. `label` = a `callout_label` placed by
  `label_spot` at gaps 0.15 / 0.35 / 0.7 (a mark-less note). Z-index: above everything on
  screen (+2; a spotlight +1, under other callouts).
- **Lifetime** (framework): new `Action.until_next_beat` (class attribute; requires reversible,
  not temporary) and `default_until(later)`; the runner stores `ActionUse.until` = `until` or
  the default, and undoes at that beat's start as for `until`. The callout goes when the next
  beat starts (`keep: true`: stays to the scene's fade-out; on the last beat it stays anyway).
  Decision: not "by the end of its beat" like `zoom`, because beat-end stills — what storyboard
  and lint look at — would never show it. Undoing fades the parts out (`fade_out`).
- **Named callouts** (framework): `Action.provides()` lists target names a use registers when
  applied; `scene_actions` lets later actions (same beat after it, or later beats) name them,
  checks the name (`TARGET_NAME`, not taken by the scene or an earlier callout). The callout
  registers itself with `on_fill = (label text, plate)`, so `dim` / `highlight` keep its label
  readable (Step 37's routed item). `Action.problems()` reports use-level checks (key, message).
- **Magnifier**: needs a still picture in the target (`image`, `screenshot` `image`); a clip or
  no picture is a render-time `VidgenError` (static checks cannot see the mobjects).
- **`screenshot` `caption`** (+ `caption_size`, `caption_color`), as `video_clip`'s: a line
  under the picture (the picture shrinks to make room), target `caption`, kept clear by callout
  labels (`_keep_off`); `target_names` moved from `video_clip` to `screenshot`. The caption (of
  both types) fades out when a `focus` step moves the camera in and back with the whole frame
  (enlarged under the picture it ran into the watermark in the gallery's `contrast` / `neon`).
- Known limits: placement is the §37 scored search (labels avoid text and small targets, not
  lines: an arrow or a label may cross a chart line or an edge); a callout added before a `zoom`
  scales with the scene (built for the camera of the moment it appears); a callout with `at` in
  the same frame as a `zoom` plays after the zoom-in, built for the zoomed view
  (`Action.after_camera`, Step 48).

## 45. Refinements (Step 42, pronunciation dictionary)

- **Config** (`config.py`): top-level `pronunciation: {term: value}` with value = the spoken form
  (text), `PronunciationEntry {say, case_sensitive: true, whole_word: true, regex: false}` or
  `null` (removes the term: how a variant or the config drops a file's / the base's entry; the map
  deep-merges in variants like any mapping); `pronunciation_file: PATH | [PATH, ...]` (YAML or
  JSON mappings of the same form, relative to the project). Effective entries = the files' in
  order, then `pronunciation:` over them. A value that is neither form is reported once per
  mistake (a `mode="before"` check, not pydantic's per-branch union errors); a regex that does
  not compile, matches the empty string or whose `say` refers to a missing group is a config error.
  The files are read when the `Project` is built (`Project.pronunciation`), so a missing or invalid
  file is a load error with `pronunciation_file (<file>)` problem locations (`validate --json`
  lists them).
- **Matching** (`vidgen/pronunciation.py`, no manim): each entry is a compiled pattern: a plain
  term is escaped; `whole_word` adds `(?<!\w)` / `(?!\w)` on the sides where the term starts /
  ends with a word character (so `C++` and `K-Phi-3's` work); a regex gets both lookarounds;
  `case_sensitive: false` → `re.IGNORECASE`. All matches of all entries in the **written** text
  are collected and chosen greedily by start, then length, then entry order; replacements are
  never matched again (no cascades). `Pronunciation.apply(text) -> Spoken(text, spoken,
  replacements, matched, conflicts)`; `say(text)`; `Project.spoken_texts()` (beat id → spoken).
- **TTS and hash**: everything sent to the provider is the spoken text (the beat and its
  `previous_text` / `next_text` context); the cache key is `provider.cache_key(spoken)` (formula
  of §7 unchanged), so a beat no entry matches keeps the hash of its written text: adding a
  dictionary does not invalidate existing audio (the committed kphi3 MP3s stay valid; kphi3 has
  no entries), and changing an entry re-voices only the beats whose spoken text changes.
  `audio_status` compares with the spoken text. `vidgen tts --dry-run` prints `says: <spoken>`
  under each beat to generate whose spoken text differs; the character count is of the spoken text.
  Variant audio rule (§7): "a beat's text differs" now reads "a beat's spoken text differs" (each
  config with its own pronunciation; `Project.has_own_audio` is cached per project).
- **Alignment / word timings** (Step 40 interaction): the stored alignment (`voice.timestamps`)
  is of the spoken text (`write_alignment(..., spoken, ...)`; `read_alignment` needs the spoken
  text). Subtitles, captions and storyboards keep the written text; their word times come from
  `beat_word_times(audio_dir, beat_id, text, start, end, spoken)`: when `spoken.changed`, the
  spoken words are timed (alignment, else the estimate within the MP3's speech — so the spoken
  syllables are weighed — else over the beat) and `map_word_times(spoken, times)` maps them back.
  Mapping: `Spoken.word_groups()` gives, per written word (`\S+`), the spoken words (`\S+` of the
  spoken text) its characters became: unchanged characters shift by the replacements before them,
  a character inside a replacement maps to the whole replacement; a written word's time runs from
  its first spoken word's start to its last one's end ("K-Phi-3" → "kay fye three": 3 → 1); a
  word said as nothing gets a zero-length time at the next spoken word's start (or the previous
  end); written words joined by one replacement share its words' time. The SRT gets the project's
  pronunciation (`write_srt(path, timings, audio_dir, pronunciation)`), captions read
  `context.project.pronunciation`.
- **Lint**: `SceneContext.spoken` (beat id → spoken text, from `Project.spoken_texts()`);
  `narration_speed` counts `spoken_words` of the spoken text. The no-audio duration estimate
  (`words_per_second`) still counts written words (unchanged, so renders do not move).
- **Render fingerprint**: `pronunciation` / `pronunciation_file` are excluded from the config
  part (they change only audio, which is tracked); with overlays, each beat's spoken text joins
  the overlay inputs (captions' word times depend on it).
- **`vidgen validate` warnings** (not problems; `--json` `warnings`): an entry that matches no
  beat; an entry that matches but never applies because a longer entry always holds it; two
  entries matching the same span or crossing spans in a beat (which one is used there). An entry
  inside a longer one that also applies elsewhere is intended (no warning). `cli.validate_warnings`
  = theme contrast + pronunciation (`log_theme_warnings` became `log_validate_warnings`).
- **Example**: `examples/minimal` (no committed audio): `LaTeX: lah-tek`, `JSON: jay-son`.
- Known limits / not done: no SSML `<phoneme>` (IPA) entries — ElevenLabs reads phoneme tags only
  with some models (not `eleven_multilingual_v2`), the tags would be billed characters and the
  alignment would no longer be of plain words; no ElevenLabs server-side pronunciation
  dictionaries (`pronunciation_dictionary_locators`); no per-beat `say:` override; matching is
  per beat (a term split across two beats never matches); `whole_word` uses Python's `\w`
  (Unicode letters and digits).


## 46. Refinements (Step 43, multiple voices)

- **Config** (`config.py`): top-level `voices: {name: VoiceEntry}` — every key of `voice:`
  optional (`provider`, `voice_id`, `model_id`, `output_format`, `settings` as
  `VoiceSettingsOverride` with every value optional, `context`, `timestamps`) plus `label` and
  `color`; `SceneConfig.voice` and `BeatConfig.voice` (identifiers); `VoiceConfig` gains `label`
  (default `None`: the base voice is not tagged) and `color` (`ColorRef`: hex or a theme token);
  top-level `subtitles: {speakers: off | name}`. `default` is reserved (the base voice; a
  `voices:` key `default` is an error). Names are checked after the model validates, in
  `parse_config` (`voices.voice_reference_problems`): `scenes[i].voice` /
  `scenes[i].beats[j].voice: unknown voice 'x'; did you mean 'y'? voices: default, ...` as
  problems with locations (variant problems are attributed to the variant as usual). Colour
  tokens are checked by `vidgen validate` with the project's theme (`voice.color`,
  `voices.<name>.color`); a voice no beat uses is a warning (`validate_warnings`). Variants
  deep-merge `voices:` like any mapping.
- **Effective voice** (`vidgen/voices.py`, no manim): a beat's voice is its `voice`, else its
  scene's, `default` → `None` (the base). `resolve_voice(config, name)`: the base voice's
  `model_dump` without `label` / `color`, the entry's non-`None` keys over it, `settings` merged
  key by key; `label` / `color` only from the entry (a speaker's name is never inherited).
  `Project.voice_names()` (beat id → name | `None`, video order), `Project.voice(name)` (cached),
  `Project.beat_voice(beat_id)`, `Project.speaker_tags(mode)`.
- **Hash / cache key**: unchanged formula (§7), computed by the provider of the beat's effective
  voice: `tts.beat_providers(project)` (one provider per voice). Beats of the base voice are hashed
  exactly as before, so a project without the new keys keeps every hash (kphi3's committed audio:
  27 ok); editing one named voice re-voices only its beats; moving a beat to another voice
  re-voices it; `label` / `color` are not hashed. `audio_status`, `plan_tts` and `run_tts` use the
  per-beat providers; their optional `provider` argument replaces all of them (tests). Variant
  audio rule (§7): own folder when the base voice's audio fields differ (`audio_fields`: all but
  `label` / `color`) or a shared beat's spoken text **or effective voice** differs; unchanged beats
  are copied from `audio/` (checked with the beat's own provider).
- **Context decision**: `previous_text` / `next_text` are the neighbouring beats in video order
  (across scenes, as before) **only when they have the same voice name**; at a change of speaker
  none is sent (`tts.run.context_texts`). Reason: ElevenLabs' request context (and request
  stitching, which is defined for one voice) treats the text as the same speaker's surrounding
  speech; another speaker's line would be read as this voice's own words (e.g. the rising tone of
  a question carried into the answer). A speaker's lines separated by another speaker's reply
  are not joined either (a turn is a prosodic reset). Not hashed (unchanged). ElevenLabs' newer
  multi-speaker *text-to-dialogue* endpoint (v3) is not used: it returns one file for many lines,
  which does not fit the beat-per-MP3 cache.
- **`vidgen tts`**: `--voice NAME` (repeatable; `default` = the base voice; unknown → error with
  suggestion) restricts the plan like `--beat` (both: intersection). When `voices:` is non-empty,
  `--dry-run` adds `, voice <name>` to every `would generate` line and after the summary one line
  per voice `  voice <name> (<voice_id>): N beat(s), C characters` (beats to synthesise, copies
  excluded); projects without `voices:` print exactly as before. `TTSPlan.voices`,
  `TTSPlan.characters_by_voice()`. `timestamps` is read from each beat's voice.
- **`vidgen validate`** (human) prints `voices:    default (N beats), ana (M beats)` when
  `voices:` is set.
- **Speakers in subtitles** (`subtitles.speakers: name`): `voices.speaker_tags(config)` gives a
  label for every beat whose voice differs from the previous beat's (video order; the first beat
  included) and that has a label (named voices: `label` or the name with `_` as spaces and a
  capital first letter; the base voice only with `voice.label`). `write_srt(..., speakers)` /
  `cues_from_timings(..., speakers)` / `beat_cues(..., speaker=)` start that beat's first cue with
  `"<label>:"` (`speaker_prefix`). The tag is cut with the text as `caption_cues(prefix=,
  prefix_width=)`: glued to the first word (its width added to the first word's), so a cue never
  holds the tag alone; `CaptionCue.prefix` holds it and `words` excludes it.
- **Captions** (`captions` option `speakers`: `off | name | color | both`, default
  `subtitles.speakers`): `name` adds the tag (glyphs in the speaker's colour); `color` draws each
  cue in its speaker's colour (`speaker_color`: the voice's `color`; a named voice without one:
  `theme.palette_color(index in voices)`; the base voice: `voice.color` or the caption's text
  colour); `both` does both. The plate opacity is raised (0.05 steps) until every speaker colour of
  the scene reaches `lint.rules.contrast.min_ratio`; one that cannot even at opacity 1 falls back
  to the text colour with a warning. Karaoke's word glyph map skips the tag's words (never
  highlighted).
- **Fingerprint**: `voices` and `subtitles` are excluded from the config part (they change only
  audio, which is tracked by the MP3 stats, and captions); with overlays, the overlay inputs carry
  each beat's voice name and the `voices` / `subtitles` sections (a scene's tag depends on the
  previous beat's speaker, possibly in another scene). The overlay inputs are now `{scenes,
  voices}` (renders with overlays count as stale once).
- **Pronunciation (§45)**: one dictionary for every voice; the hash covers the spoken text and
  the voice, so both edits re-voice exactly the beats they change. Per-voice entries are not
  implemented (a variant with its own `pronunciation:` covers another-language voice).
- **Example**: `examples/minimal` names a `guest` voice (another `voice_id`, `stability`, label,
  `secondary` colour), the `note` scene is a two-line dialogue (guest asks, narrator answers),
  `subtitles.speakers: name`, and the `subtitled` variant's captions use `speakers: both`.
- Known limits: storyboard labels and `timings.json` do not name speakers; the tag shows only on
  a beat's first cue (karaoke shows it briefly: prefer `color`); no per-voice `narration.pad` or
  `words_per_second`; no ElevenLabs text-to-dialogue.


## 47. Refinements (Step 44, sound effects)

- **Sounds** (`vidgen/sfx.py`, no manim): eleven built-in sounds (`BUILTIN_SOUNDS`: whoosh,
  swoosh, pop, click, tick, typing, riser, chime, success, error, thud), each a deterministic
  numpy generator (`BuiltinSound(name, generate, duration, duration_range, description, use)`;
  noise from `default_rng(crc32(name))`; filters as zero-phase magnitude responses in the
  frequency domain, time-varying band-passes by STFT) taking `Synth(n, ratio, intensity, rng)`:
  `params` `duration` (within the sound's range), `pitch` (semitones, ±24) and `intensity` (0–1:
  timbre, and ±3 dB around 0.5). Finishing (`_finish`): high-pass 25 Hz, raised-cosine fades
  (first and last sample exactly 0), the mean removed by subtracting a scaled Hann window (zero
  at the ends, so DC is 0 and the ends stay 0), then the level: the loudest 400 ms window
  (BS.1770 K-weighting at 48 kHz, applied as a magnitude response; `loudness()`) at
  `LOUDNESS_TARGET` −27 LUFS (one channel), peaks capped at `PEAK_CEILING` −9 dBFS (short clicks
  and ticks are peak-limited, so they measure quieter). Calibration: the committed kphi3
  ElevenLabs MP3s measure −18.5 to −21.4 LUFS the same way (peaks −4 to −8 dBFS), so a sound at
  gain 0 sits ~7 dB under narration (a test keeps it ≥ 5 dB under the quietest beat).
- **Decision: synthesised when the video is joined, cached per process** (`synthesize`,
  `lru_cache`), not shipped as package-data WAVs: the params are continuous (pre-rendered files
  could only give the defaults), every sound takes 5–110 ms, and nothing (~1 MB of WAVs) is
  added to the wheel. `vidgen list-sfx --render-dir DIR` writes previews for a human.
- **Project sounds**: `assets/sfx/<name>.<wav|flac|ogg|mp3>` (`project_sounds`; `.wav` first
  when a name has several; invalid names skipped with a warning) extend or replace built-ins by
  name (`SoundLibrary`; `list-sfx` marks `overrides_builtin`); decoded with PyAV to 48 kHz
  (mono or stereo kept); played at their own level, no `params` (a problem when given).
- **Where sounds come from**: `NarratedScene.sfx(sound, at=None, *, gain, pan, align, **params)`
  (scene seconds; default `renderer.time`) validates with the config model `SfxCue` and the
  library and appends an `SfxEvent(time, sound, gain, pan, align, params, beat)` to `sfx_log`;
  nothing is drawn, no time passes. A scene's `sfx:` list (`SfxCue`: `sound`, `at` seconds,
  `gain` dB −60..12, `pan` −1..1, `align` `start|end`, `params` `SfxParams`; a plain string =
  `{sound}`; on a silent scene `at` < `duration`) is recorded in the constructor. The beat action
  `sfx` (`scenes/sfx_action.py`) — `- sfx: NAME` (or `sound:`), options `gain`, `pan`, `align`,
  `params` — is cued by the runner. `timings()` gains `sfx` (the events) when there are any.
- **Framework** (`vidgen.actions`, compatible): `Action.scene_targets` (False: `target` is not
  checked against / resolved among the scene's targets; the action's `problems()` checks it) and
  `Action.animates` (False: the runner calls `cue(scene, time)` when the beat starts, with the
  due frame's time — `at` rounded to a frame like any action — and marks the use applied; it is
  never queued for a wait; `check_action_class`: such actions implement `cue`, not `apply`, and
  cannot be reversible). **Decision**: a sound plays exactly at `at`, even while the scene's own
  animation runs (animating actions wait for it), so `at: 0` lands with the beat's entrance;
  syncing to a delayed action's start is left to `sfx.auto`.
- **Auto** (`sfx: {auto: true}`; `SfxConfig.auto`, default off): `ActionRunner._build` calls
  `scene.auto_sfx(name)` when a *built-in* action's `apply` returns animations (so a no-op
  `reveal` makes no sound), at the moment it starts playing — `AUTO_ACTION_SFX`: reveal → pop
  −3 dB, highlight → tick −3, callout → click −2, zoom → whoosh 0.5 s −6, transform → swoosh −6
  — except in beats that have their own non-animating (`sfx`) actions; and scene types with
  `entrance_sfx` (`chapter`: whoosh −3 dB) get it at time 0. Scene types' own reveal steps get no
  automatic sounds (a pop per bullet / bar / node was judged too busy).
- **Mixing (no Manim sound)**: the worker stores the events in `timings/<id>.json` (always, also
  with `--no-audio`). `join_scenes` shifts them by each scene's offset (combined `timings.json`
  scenes gain `sfx`, video times) and, unless `no_audio`, writes **one SFX track for the whole
  video**, `padded/sfx.wav` (`write_track`: 48 kHz stereo s16, exactly `round(total * 48000)`
  samples = the sum of the padded scene WAVs; event start sample `round(time * 48000)`, minus
  its length for `align: end`; parts before 0 / after the end cut; written in 10 s blocks;
  sums clipped, never wrapped), with `sfx.gain` (master dB) added. Pan: equal-power, centre =
  full level on both channels (as a mono narration MP3 is duplicated, since Step 48 by
  `scene.add_narration`; see §51), so loudness compares 1:1. `ffmpeg.join(..., sfx=)` adds it to the concatenated narration with
  `amix=inputs=2:duration=first:dropout_transition=0:normalize=0` (a plain sum) before the one
  AAC encode. Sounds therefore run across scene cuts (a sound after its scene's end is a warning),
  are sample-exact in the timeline, and do not resample the narration (Manim's pydub mix would
  place at 1 ms and resample the MP3 to the sound's rate). Scene renders and storyboards have no
  effects. Without events (or with `--no-audio`) the join is byte-for-byte the old command.
- **For Step 45 (music, ducking, loudness)**: the voice track (concatenated `padded/<id>.wav`:
  narration + clip sound) and the SFX track stay separate until the final mux, so music can be
  ducked with the voice track alone as the sidechain (`sidechaincompress`), then voice + SFX +
  ducked music summed and `loudnorm`ed; the SFX levels are relative (−27 LUFS ≈ 7 dB under
  narration) and survive a normalisation of the sum.
- **Checks**: `vidgen validate` (`cli.project_problems` + `sfx.config_problems`): unknown sounds
  with did-you-mean and the list, params on project files, durations outside the range, at
  `scenes[i].sfx[k].<key>` and `scenes[i].beats[j].actions[k].<target|sound|params.duration|
  run_time>`; the render pre-check raises them; `NarratedScene.sfx` raises `VidgenError`.
- **Listing**: `vidgen list-sfx [PROJECT] [--render-dir DIR] [--json]` (`sound_entries`: name,
  origin, description — precise words for an author who cannot listen — use, duration, range,
  channels, loudness, peak, preview); `list-scenes` shows `sfx` as "(at its time, does not
  animate)", JSON actions gain `scene_targets`, `animates` (within version 1). `sfx.py` is not a
  render-fingerprint input (sounds never change pixels); scene `sfx:` lists and `sfx` actions
  are part of the scene's config, so editing them re-renders that scene's stills.
- Known limits: no per-scene switch for `auto` (a variant can turn it off); a sound still
  playing at the video's end is cut without a fade; project sounds are not loudness-normalised;
  built-ins are mono (pan places them).

## 48. Refinements (Step 45, background music, ducking, loudness)

- **Config** (`config.py`): top-level `music:` (`MusicSetting`): a source name, one `MusicCue`,
  a list of cues, or `false` / null. `MusicCue`: `source` (a bed name or a path under the
  project), `volume` dB (−60..12), `start` s, `loop` (true), `crossfade` s (2), `fade_in` (1.5),
  `fade_out` (3), `duck` (`DuckConfig` or a bool: `false` = depth 0), `from` / `to` scene ids.
  `VideoConfig._music_problems`: known scenes, `from` not after `to`, no two cues on one scene.
  `VideoConfig.music_cues` gives the list. Scene `music: true | false | {volume}`
  (`SceneMusic`). Top-level `audio:` (`AudioConfig`): `normalize: auto | true | false`,
  `target_lufs` (−16, −40..−5), `true_peak` (−1.5 dBTP, −9..0). `vidgen validate`
  (`music.config_problems`) reports a source that is neither a bed nor a file; the render
  pre-check raises it. `music` / `audio` and a scene's `music` are not render-fingerprint
  inputs, nor are `music.py`, `mix.py`, `loudness.py` (music never changes pixels or timing).
- **Beds** (`vidgen/music.py`, numpy only): `calm` (60 s, D major, no beat), `pulse` (40 s,
  A minor, 96 BPM), `bright` (48 s, C major, 120 BPM). Pads by PADsynth: each chord's harmonics
  as Gaussian bumps (18–30 cents wide) with random phases in one spectrum, one inverse FFT → a
  periodic wave whose length divides the chord's segment; chords cross-fade with equal-power
  windows of 1.6 s; an airy layer an octave up swells with an LFO whose period divides the loop;
  a sub-bass under each chord; `pulse` / `bright` add plucked eighth-note arpeggios (patterns
  picked per bar), a soft thump per beat (`pulse`) or a sparse bell melody (`bright`). Tone
  shaping per partial (high-pass 40 Hz, low-pass 3.5–4.5 kHz, both second order): nothing harsh,
  no rumble (tests: < −30 dB of the energy above 5 kHz, < −30 dB below 35 Hz). Everything is
  rendered **circularly** (notes past the loop's end continue at its start; the waves are
  periodic in the loop), so the loop tiles without a seam. Seed `crc32("music:<name>")`;
  `bed_loop(name)` is cached per process (~1–1.5 s to make). Level: `MUSIC_LEVEL` −28 LUFS
  integrated (−30 until Step 48, §51). **Decision: a loop tiled to the needed length**, not a piece generated for the
  whole video: generation cost is fixed, loops of 40–60 s with chord changes every 4–7.5 s and
  slow LFOs rarely sound repetitive under narration, and a loop is trivially seamless.
- **Files**: decoded with PyAV (`sfx.decode_audio`), mono duplicated, cached per (path, size,
  mtime); measured (integrated) and scaled to `MUSIC_LEVEL`. `music.Source(cue, root)`: from
  `start` on; looping files play `body[:-X]` once, then a loop whose first `X` samples are the
  head cross-faded (equal power) with the tail, so every repeat continues exactly where the
  previous pass stopped; `loop: false` → silence after the end (the cue's fade-out ends there).
- **Loudness** (`vidgen/loudness.py`): BS.1770-4 integrated loudness (400 ms blocks, 100 ms
  step, absolute gate −70 LUFS, relative gate −10 LU), K-weighting as the filter's magnitude
  response applied by FFT to 10 s blocks read with 0.5 s margins (circular per block; the margins
  absorb the edges), `LoudnessMeter` fed in order, true peak by 4x polyphase windowed-sinc
  interpolation (Kaiser, 12 taps a side). Checked against FFmpeg's `ebur128` on a rendered mix
  (−16.1 / −1.6 dBTP both). ~0.2 s per 10 s of audio per pass.
- **Ducking** (`vidgen/mix.py`): **decision: a gain curve computed from the narration's timing,
  not an audio envelope follower or FFmpeg `sidechaincompress`**. The key is where speech is: each
  beat from its start to the end of its speech (`speech.speech_bounds` of its MP3; the whole beat
  without audio), so it is exactly "the narration track only" (clip sound and SFX are mixed into
  the same WAVs / track and could not be told apart by level), deterministic, and able to look
  ahead (offline). `duck_curve` at 100 Hz: pauses shorter than `hold` filled; in dB, `-depth`
  where speech is, raised-cosine ramps of `attack` s ending at a speech start and `release` s
  after its end (max of both). Defaults 12 dB / 0.4 s / 1.0 s / 1.5 s: ElevenLabs beats are
  ~1 s apart (lead/trail silence + pad), so with a shorter hold the music pumped up between
  every beat. With `duck.clips` (default) a `video_clip` scene whose clip has sound (not
  `mute`, `volume` ≠ 0, the file has an audio stream) is foreground for its whole span.
- **Per scene and per cue gain** (`plan_music` → `Placement`s, 10 ms frames, interpolated per
  sample): `10^(volume/20)` × fades (raised cosine; fade-out ends at the cue's end or the
  source's) × scene levels (`false` → 0, `{volume}` → dB; steps smoothed by `smooth_steps`:
  a running minimum then a moving average, 0.75 s, so a ramp lies on the louder side — the
  quieter scene has its level from its first to its last sample) × ducking. A cue spans its
  `from` scene's start to its `to` scene's end (the last cue to the video's exact end).
- **The mix** (`mix_audio`, called by `join_scenes` unless `--no-audio`): tracks read block by
  block — `WavTrack` (the padded scene WAVs, the SFX track) and `MusicTrack`. **Decision:
  normalisation `auto` by default — on when the video has music, off otherwise** — so every
  existing narration-only video keeps its exact audio (the join command is byte-for-byte the
  old one; the mix is only measured), while a video with music, whose level is new anyway, comes
  out at −16 LUFS. Not while the video has narrated beats but none has its MP3 (a preview timed
  from word counts: the gallery measured +25 dB of gain on music and effects alone; logged at
  info level, `normalized: false`). With music or `normalize: true`: pass 1 measures the sum (no true peak),
  gain = target − measured; pass 2 writes `padded/mix.wav` (48 kHz stereo **24-bit**: the gain
  and fades stay clean) through `limit()` — the gain each sample needs for its true-peak
  envelope to stay `LIMITER_MARGIN_DB` (0.4 dB since Step 48, was 0.1) under `true_peak`, a running minimum (±5 ms) then a 10 ms moving
  average, so the gain never exceeds the need and moves smoothly; block margins make it exact
  across blocks — and measures the output. `ffmpeg.join(..., mix=)` then uses the WAV as the
  audio (one AAC encode). `MixReport` → combined `timings.json` `mix` and `render --json` `mix`:
  `{mixed, normalized, target_lufs, true_peak_limit, gain_db, integrated_lufs, true_peak_dbtp,
  limited_db, music: [{source, kind, from, to, start, end, volume, duck}]}`; the human render
  output adds a `loudness:` line.
- **Levels measured**: committed kphi3 MP3s are −21.4 LUFS integrated (as stereo). Until Step
  48 a rendered narration track was −24.4 (Manim's MP3 conversion upmixed mono −3 dB per
  channel) and `MUSIC_LEVEL` was −30; Step 48 plays narration at the MP3s' level and sets
  `MUSIC_LEVEL` −28, so music is ~6.5 dB under the voice in pauses and ~18.5 dB under it when
  ducked, and the Step 44 SFX level (≈ 7 dB under narration) holds as stated (§51).
- **`vidgen list-music [PROJECT] [--render-dir DIR] [--json]`** (`music.music_entries`,
  `jsonout.list_music_document`): every bed with a precise description, use, tempo, key, chords,
  loop length and measured loudness; the project's `assets/music` files (any path works as a
  source; that folder is only what is listed); previews of one loop per bed.
- Known limits: cues do not cross-fade into each other (the first fades out, the next fades
  in); the beds are fixed (no tempo / key parameters); a file is decoded whole into memory
  (~23 MB per stereo minute); music is not in scene renders or storyboards; the AAC encode may
  raise the true peak by ~0.2 dB (inside the limiter's margin); no LRA / short-term loudness targets.


## 49. Refinements (Step 46, transitions: crossfade and fade through a colour)

- **Config** (`config.py`): `TransitionConfig {type: cut | crossfade | fade_color, duration,
  color}` (`duration` 0 < d ≤ 5, default per type `TRANSITION_DURATIONS`: crossfade 0.5,
  fade_color 1.0; a cut has no duration; `color` only on fade_color: a theme token, `background`
  or hex, default the theme's background); a plain string is the type (`TransitionSetting`).
  `SceneConfig.transition` = the way **into** that scene; `VideoConfig.transition` = the default
  for every scene but the first (`transitions.effective(config, i)`). A crossfade on the first
  scene is a config error; `fade_color` there fades the video in. `vidgen validate` checks colour
  tokens (`transitions.color_problems`) and warns about holds (below).
- **Timing contract (decision): a crossfade overlaps the two scenes, a fade_color does not.** A
  real cross-dissolve needs both pictures at once, so the next scene starts `overlap` frames before
  the previous one ends and the video gets shorter by it; a fade through a colour needs no second
  picture, so the previous scene's last `fade_out` frames fade to the colour and the next scene's
  first `fade_in` frames fade in from it (`round(duration x fps / 2)` each), and the video keeps
  its length. **Speech never overlaps**: a transition may cover only the *silent tail* of the scene
  before it — its frames after the last beat's narration end (`start + d`: the pad and the
  fade-out), the whole scene when it is silent, never the frames its own incoming transition uses
  (`transitions.silent_tail`). When the tail is shorter, that scene is **held** on its last
  picture by the difference (`hold`, added in `NarratedScene.tear_down`) — a decision for
  "extend" over "clamp": the author gets the transition asked for, and pacing changes by the
  hold only, which `vidgen validate` reports. Defaults need no hold for built-ins (tail = pad 0.35
  + outro 0.5 ≥ 0.5). The incoming scene's narration starts with it, so it may speak during a
  crossfade (over the previous scene's silence).
- **The plan is the one source of start times** (`videoplan`): frame-based now — a scene's own
  frames (beats + outro, or its duration), `transition(i) -> TransitionSlot(type, seconds, color,
  overlap, fade_out, fade_in, hold)` (frames; a cut for every scene of a video without
  transitions, which keeps the old plan exactly), `scene_duration(i)` = own + the hold of the
  transition out of it, `start(i) = start(i-1) + frames(i-1) - overlap(i)`. `SceneSlot` gains
  `overlap_in`, `overlap_out` (seconds) and `cut` (= `end - overlap_out`, where the next scene
  starts). Chapters, the progress bar, the chapter indicator (runs now end at `cut`), lower
  thirds (`min(end, slot.cut)`), `resolve(scene id, end=True)` (= `cut`), captions (per scene
  times), all follow it. The join computes the same overlaps from the renders
  (`transitions.join_overlaps`: the requested frames limited to the measured silent tail and the
  scene's length; equal to the plan when renders match it, and a shortened crossfade is warned
  about), and every later time — combined `timings.json` starts and beats, the SRT, SFX events,
  music cues and ducking spans, the frames index, storyboard times (`storyboard.scene_starts`) —
  is derived from the overlapped starts. `Project.estimated_duration` subtracts crossfades.
- **How a scene ends** (`NarratedScene`): with a transition other than a cut after it,
  `finish()` holds the picture for the outro frames instead of `clear_all` (same frame count),
  so a crossfade blends the full picture (no dip through the background) and a colour fade fades
  the picture itself. Extension scenes that fade out themselves still work (the crossfade blends
  their faded picture). `transition_in` / `transition_out` hold the planned slots; the scene
  reads the plan only when the video has transitions.
- **Video at the join** (`ffmpeg.join(..., crossfades, frames, fps)`): consecutive scenes joined by
  cuts form runs (one concat list each); runs are blended with `xfade=transition=fade`, chained,
  each starting half a frame before its first shared frame (`crossfade_graph`): weights
  `(j + 0.5) / n`, symmetric, the middle frame of an odd crossfade 50/50, and exactly
  `sum - overlaps` output frames (tested). The video is then encoded once (libx264, CRF 18
  `VIDEO_CRF`, yuv420p) — decision: re-encoding only the transitions would need cuts at arbitrary
  frames of stream-copied H.264 (keyframes), and CRF 18 over Manim's CRF 23 sources is visually
  lossless; it costs about real time at 1080p. Without crossfades the join is the old stream copy.
  `xfade` also has wipes and slides (Step 47).
- **Audio at the join**: the padded scene WAVs keep their exact lengths; with overlaps they are
  summed into `padded/voice.wav` (`transitions.write_voice_track`, sample offsets from the same
  cumulative rounding as before, so nothing drifts), the earlier scene's tail fading out (raised
  cosine) under the next scene's start at full level — that tail has no narration by the
  contract; only clip sound can be there. `voice.wav` replaces the per-scene list for the final
  mux and `mix.mix_audio`.
- **fade_color inside the render** (`transitions.ColorFade`): wraps `renderer.add_frame`
  outermost (after the overlay layer), so the colour blends the scene's picture and the overlays
  are drawn on top; colour weight `1 - k / fade_in` at the start, `(j + 1) / fade_out` at the end
  (the scenes' boundary frames are the pure colour); frozen waits are split per faded frame. The
  last frames are found from the planned length (the plan contract; a scene that overruns would
  fade early — the join's drift warning covers it). Stills, the layout dump and storyboards see it.
- **Overlays in a crossfade (decision: the incoming scene's on both sides)**: overlays are
  composited inside each scene's render, so a crossfade blends two composited pictures. Overlay
  states are a pure function of video time, but *which* overlays a scene draws is not (captions
  show the scene's own cues, a chapter card has no indicator, a scene may turn overlays off): A's
  tail would show A's last caption while B's head shows B's first — a doubled, half-transparent
  caption. So `OverlayLayer` takes `following` (the next scene's overlays, built with
  `scene_overlays(next)`) and a `cut` time: from the next scene's start on, A's render draws B's
  overlays instead of its own. Both renders then hold identical overlay pixels in every shared
  frame and, the blend being linear, `α (o + (1 - a) A) + (1 - α) (o + (1 - a) B) = o + (1 - a)
  (α A + (1 - α) B)`: the overlays come out exactly as if drawn over the blended pictures (tested:
  caption region and progress bar equal in both renders, the intro shows the talk's caption over
  its last frames). Overlay changes therefore happen at the *start* of a crossfade. Own overlays
  still decide the scene's `reserve`; `scene_overlays` drops overlays that end before `cut`.
- **Lint / storyboard**: beat-end stills are before the transitions (the overlap lies in the
  outro), so layout rules are unaffected. `dead_air`: the activity file gains `overlap_out`
  (frames the crossfade covers) and a still run ends there (the held outro would otherwise add
  0.5 s of "no change"). Storyboard sheet times are video times with overlaps.
- **Fingerprint**: a scene's render depends on the transition out of it (held vs faded, colour
  fade, hold) — `next_transition` (its config and what limits it: the next scene's duration,
  beats and MP3 stats; `"cut"` for a cut, so adding a transition elsewhere does not re-render
  unrelated scenes); its own `transition` is in its config dump; with overlays every scene's
  `transition` joins the overlay inputs (crossfades move later scenes).
- **JSON**: combined `timings.json` scenes with a transition gain `transition: {type, duration,
  overlap}` (within version 1); activity `overlap_out`.
- **For Step 47 (push, wipe, continuity; done, see §50)**: `type` grows (`push`, `wipe`) with a `direction`
  option; `crossfade_graph` maps them to `xfade`'s `slideleft/right/up/down` and
  `wipeleft/...`. Unlike a fade, a slide or wipe is not linear in the two pictures per pixel, so
  overlays baked into both scenes would slide/wipe with them (a watermark moving). Suggested
  approach: the incoming scene's worker also writes its overlay layer for the overlap frames as a
  separate RGBA clip (or both scenes render the overlap *without* overlays), the join slides the
  bare pictures and overlays the RGBA clip on top (`overlay` filter). The timing contract
  (overlap, silent tail, hold) carries over unchanged. A match-cut helper can use the plan to
  know the previous scene and its last state.
- Known limits: the join re-encodes the whole video when any crossfade exists; `fade_color` and
  crossfades happen at planned frames, so an extension scene that times itself differently from
  the contract is faded/overlapped where the plan expected it (warned at join); a crossfade into a
  scene shorter than the crossfade is shortened to that scene; no transition after the last scene
  (an `end_card` fades out by itself); transitions are not previewed in a single scene's render
  (`vidgen render --scene X` shows the scene's held tail, the blend happens at the join).

## 50. Refinements (Step 47, push, wipe, continuity)

- **Config.** `TransitionConfig.type` adds `push` and `wipe` (default 0.6 s), with `direction`
  (`left | right | up | down`: where the pictures / the edge move; push / wipe only) and `soft`
  (wipe only). `config.OVERLAPPING_TRANSITIONS = (crossfade, push, wipe)`,
  `TransitionConfig.overlaps`; every place that tested `type == "crossfade"` (plan, join
  overlaps, head frames, estimated duration, first-scene check, join warnings) now tests
  `overlaps`. Default direction (`transitions.direction(t, portrait)`): `left` in a wide or square
  frame, `up` in a tall one (the next scene comes in from the right / from below), resolved per
  render format, so one video-level `push` suits the 16:9 video and its 9:16 variant.
  `transitions.xfade_name`: `fade`, `slide<dir>`, `wipe<dir>`, soft → `smooth<dir>` (FFmpeg's
  soft-edged wipes). Checked empirically: `slideleft` moves both pictures left with the next one
  entering from the right, `wipeup` uncovers the next one from the bottom; with the half-frame
  early offset the next scene covers `(j + 0.5) / n` of the picture at shared frame `j` (tested
  with solid colours, all four directions).
- **Timing**: exactly the crossfade contract (overlap of the silent tail, hold, the plan as the
  one source of starts, voice track summed over the overlap).
- **Overlays (decision: rendered once, outside both pictures, composited at the join).** A slide
  or wipe is not per-pixel linear, so overlays baked into both renders would move (a sliding
  watermark, two half captions). So: the outgoing scene draws **no** overlays from the planned
  cut on (`OverlayLayer` without `following`: `_build_overlays` gives `following` only for a
  crossfade, the own overlays stop at `cut` as before); the incoming scene's worker calls
  `OverlayLayer.split_head(overlap, path)` (`NarratedScene.overlay_head` = the planned overlap
  of an incoming push / wipe): its first `overlap` frames are written bare and the overlays of
  those frames go, per frame and as a pure function of video time like everything else, into an
  RGBA clip `scenes/<id>.overlay.mov` (`RgbaClip`: QuickTime + PNG, straight alpha;
  `OverlayLayer.rgba(states, h, w)` blends the cached premultiplied patches over transparency, so
  it is the same picture `composite` would draw, within 2 levels — tested). The join (`ffmpeg.join
  (kinds=, overlays=[(clip, first output frame)])`, `overlay_graph`) draws each clip after the
  `xfade` chain with `overlay=eof_action=pass:format=yuv444`, the clip shifted half a frame early
  so frame `j` lands exactly on output frame `start + j`; `RgbaClip.close` appends a transparent
  frame because `overlay` stops showing a clip at its last frame's timestamp (found by test: the
  last frame was dropped). Which overlays: the incoming scene's, from the transition's start, as
  for a crossfade (§49). The clip covers the incoming scene's first frames whatever overlap the
  join ends up using, so a shortened overlap stays correct. Timings `render.overlays.head`
  records the frames; a clip is used only when the transition into the scene is still a push /
  wipe. Alternative rejected: compositing in Python at the join (decode + re-encode the overlaps
  ourselves) — more code, and the join already re-encodes once.
- **Continuity (`carry`).** `SceneConfig.carry: list[CarryEntry(source, dest)]` from `name` /
  `"a -> b"` strings (`CarrySetting`: dumped back as the strings; target-name syntax
  `config.TARGET_NAME_PATTERN`, now shared with `actions.TARGET_NAME`; one destination once; not
  on the first scene). `carry.carry_problems` (validate + before any render) checks sources
  against the scene before's `target_names(params)` and destinations against the scene's (types
  that declare `target_patterns` only; synonyms `title`/`heading` as for actions);
  `carry_warnings`: a carry through `fade_color` / `push` / `wipe` (they fade or move the
  carried objects with the picture).
  - **Recording** (scene A): `NarratedScene.carry_out` = the next scene's sources; `finish()`
    fades everything but their on-screen parts (`clear_all(keep=)`: a group holding a kept part
    fades only its other submobjects); `tear_down` records each source's on-screen parts as
    plain shape data (`carry.parts_state`: per vector family member with points, its points,
    fill / stroke / background-stroke RGBAs, widths, z, joint / cap style; images are skipped
    with a warning) into `carry_state`; the worker writes `carry/<A>.json` `{version, scene,
    fingerprint, objects: {source: [shapes]}}`. Decision: **re-created shapes, not pickled
    mobjects** (no class identity, updaters or file paths to carry; pixel-identical — tested
    within 1 level on text, strokes and fills).
  - **Showing** (scene B): the worker reads A's record (missing → `VidgenError` naming A) into
    `scene.carried_in` and notes `render.carry_from` = A's fingerprint; `setup()` adds the
    rebuilt `VGroup` of each entry from frame 0. `entrance(target)` (what built-ins use to bring
    targets in) returns `carry_move(copy, target.mobject)` for a target a copy waits for:
    `Transform` of the copy into a flat copy of the target's shapes, then the target itself in
    its place (so later actions find it) when both have as many shapes (same text / icon:
    glyphs glide), else Manim's `FadeTransform` (stretched cross-fade between boxes). `play()`
    fades out a copy whose destination is brought in another way (it is in the play's
    animations) or does not exist (warning). `carry_in(name)` hands the copy to custom code.
  - **Order of renders** (decision: B depends on A's artifact, not on recomputing A's end):
    `pipeline.with_carried` adds to any render list the scene before a carrying scene whose
    record is missing or has another fingerprint than A's current one, and a carrying scene
    whose `carry_from` is not A's current fingerprint when A is rendered; `_runs(after=)` makes a
    carrying scene's task wait for the scene before (thread events; the pool starts tasks in
    list order, so the awaited one has started: no deadlock). Works for `render` (with
    `--scene` / `--jobs`), `storyboard` and `lint` (all go through `_render_scenes`).
  - **Fingerprint**: A gains `next_carry` (what it keeps), B `carry` + `carry_from` (A's
    fingerprint, recursively), only when there are carries; a scene's own `carry` is left out of
    its config dump, so projects without carries keep their fingerprints (adding the
    `direction` / `soft` keys changes those of scenes with transitions once).
- **Example**: `examples/gallery`: `structure` (chapter) → `tradeoff` cut with `carry: ["title ->
  heading"]` (different words: a stretched cross-fade into the heading), `part2` → `speedup` cut
  with `carry: [icon]` (glides into the stat's icon), `schedule` `push`, `cost` `{wipe, right,
  soft}`.
- Known limits: carried objects are vector shapes only, in scene coordinates (a camera zoomed at
  the end of A is not undone); a push / wipe still blends pictures whose overlays were *chosen*
  per scene (the incoming scene's from the transition's start, like a crossfade); stills taken in
  a push / wipe's frames show no overlays (beat-end stills never are); `vidgen render --scene X`
  alone shows neither the slide nor the carry's partner (the join and the scene before do).


## 51. Refinements (Step 48, review 3: overlays, captions, audio, transitions)

- **Narration level**: `NarratedScene.narrate` adds a beat's MP3 through `scene.add_narration`,
  which decodes it (`sfx.decode_audio`, 48 kHz) and hands Manim a stereo WAV (`sfx.stereo`: a
  mono file at full level on both channels, as sound effects have always been). Given the MP3,
  Manim's `convert_audio` encoded it with PyAV's default stereo layout, i.e. libswresample's
  mono → stereo matrix at −3.01 dB per channel: every rendered video since Step 4 was 3 dB
  quieter than its MP3s (kphi3: −24.4 → now −21.4 LUFS integrated, true peak −2.2 dBTP). Clip
  sound (`clips.clip_audio`, FFmpeg `aformat` stereo) keeps the standard −3 dB upmix for mono
  clips; it is under the narration at a chosen `volume` anyway. Recalibrated: `MUSIC_LEVEL` −28
  LUFS (Step 45 had planned −28 and set −30 only to make up for the bug): ~6.5 dB under
  narration in pauses, ~18.5 dB when ducked; the SFX level (−27 LUFS loudest 400 ms) needs no
  change — it was calibrated on the MP3s and is now ~7 dB under the voice as stated.
- **Limiter margin** `mix.LIMITER_MARGIN_DB` 0.4 (was 0.1): the AAC encode raised the gallery's
  true peak 0.2 dB over the WAV's, past the −1.5 dBTP ceiling.
- **Scene lengths** (`ffmpeg.probe`): duration = frames / the stream's nominal rate
  (`guessed_rate`, `r_frame_rate`) instead of the average rate, which Manim's joined partial
  movies put off by a few 1/10000 (15.0003 for 15 fps): the join's starts drifted up to ~3 ms
  from the plan over the gallery (chapter start ≠ scene start) and each padded WAV was a few
  samples short of its video.
- **Overlays making way** (`Overlay.yields`, `clear_of`, `clear_area`; `overlays.build_overlays`
  used by `OverlayLayer`): yielding overlays are built after the others and know the boxes of
  those that reserve room; the built-in `lower_third` yields and, where it would come within the
  reserve gap of such a box (bottom captions in 9:16 *and* 16:9 when `align: bottom`), is placed
  again in `avoid(area, box)` — above the captions. Nothing moves when nothing is in its way.
  Decision: a class attribute on the overlay type (which one gives way is a property of the
  kind of overlay), not a priority number in the config.
- **Actions due with a camera move** (`Action.after_camera`; `callout` sets it): in a frame
  where a `moves_camera` action is due, after-camera actions are ordered last and get a batch of
  their own after it, so a callout written next to a `zoom` (same `at`) is built for the zoomed
  view (it was built for the camera before the zoom and then scaled with the scene).
- **Karaoke pop**: `captions.POP_ROOM` 0.25 of a space per side (was 0.45: the popped word
  nearly touched its neighbour in 9:16).
- **Not changed, documented**: `reserve` stays per scene (a layout is built once; a time-ranged
  reserve would mean re-laying out scenes mid-way) — several reserving overlays add up (the
  gallery's voiced clip in 16:9: captions + lower third + indicator + watermark leave the clip
  small). The SRT's / captions' first cue of a beat starts at the beat's start (not at the
  speech onset ~50–90 ms later), by design (`cues.caption_cues`). Joins with a crossfade, push
  or wipe re-encode the whole video: measured on the gallery preview (3:49, 854x480, 2 CPUs)
  ~40 s of a ~60 s join+mix, ~10 s of it decoding / filtering, the rest x264; stream-copying the
  parts between transitions would need re-encoded head / tail pieces whose H.264 parameters
  (SPS/PPS) match Manim's encoder for a concat copy, and Manim's keyframes fall at its
  partial-movie boundaries, not at the transitions — not robust enough for the gain (the
  scenes' own renders take 2–3x longer than the join).

## 52. Refinements (Step 49, chapters in the MP4 and a YouTube chapter list)

- **Config** (`config.py`): top-level `chapters: ChaptersConfig {metadata: true, youtube: true,
  intro: "Intro" | false}` and `metadata: MetadataConfig {title, artist, album, comment,
  description, copyright, date, genre}` (all optional text; `title` defaults to the video's
  `title`). Both are left out of scene fingerprints (they change no pixels and no timing).
- **Published chapters** (`chapter_export.py`): the list written to the outputs starts at 0:00.
  When the first chapter starts later (an opening title scene), `published_chapters` adds a
  chapter titled `chapters.intro` before it (`Chapter.intro = True`, `scene` = the first scene,
  no number, not a card), or with `intro: false` moves the first chapter's start to 0:00;
  `index` / `count` are renumbered in that list. A first chapter starting within 1 ms of 0
  counts as starting at 0. **Decision: the intro exists only in published lists.** Overlays
  (progress bar gaps, chapter indicator) keep the plain `VideoPlan.chapters` — an indicator saying
  "Intro" over a title card would be noise, and Step 39's runs, fades and reserves stay as they
  were. `video_chapters(project, fps, intro=True)` returns the published list from the plan
  (what `vidgen validate` checks).
- **Times in the outputs come from the join**, not from the plan: `joined_chapters(config,
  scenes, duration)` starts each chapter at its scene's start in the combined timings (the
  overlapped starts of §49: a crossfade / push / wipe into a chapter card starts the chapter where
  the transition starts) and ends the last at the joined duration. For scenes that keep to the
  plan (all built-ins; §51) they equal `video_chapters(..., intro=True)` exactly; for a scene
  that does not, the outputs follow the real video. Found while testing: at 5 fps a silent
  `chapter` card of 1.2 s plans 7 frames and renders 6 (`(duration - outro) x fps` = 3.5 frames:
  the plan rounds the tie up, the scene's waits end a frame shorter) — a half-frame tie only;
  routed to Step 60. The test uses 10 fps.
- **MP4** (`ffmpeg.join(..., metadata=)`): the pipeline writes `padded/metadata.txt`
  (FFMETADATA: global tags, then one `[CHAPTER]` per chapter with `TIMEBASE=1/1000`, `START` /
  `END` rounded to the millisecond, `END > START`, titles on one line; `\ = ; #` and newlines
  escaped) and the final mux adds it as the last input with `-map_metadata N -map_chapters N`.
  FFmpeg's MP4 muxer stores the chapters as a QuickTime chapter text track (a `bin_data` data
  stream in ffprobe) plus a Nero `chpl` list, which is what players read; ffprobe
  `-show_chapters` reads them back (tested: starts equal the plan within 1 ms). With
  `chapters.metadata: false` the file has no `[CHAPTER]` entries (tags still). The join now
  always maps metadata from this file (the concat demuxer's input tags are no longer copied;
  they were only FFmpeg's `encoder`, which the muxer writes anyway).
- **YouTube list** (`pipeline.write_chapter_list`): `<output>[_<variant>][_preview]_chapters.txt`
  (`Project.chapters_path`), one `M:SS Title` line per published chapter (`H:MM:SS` from an hour
  on), UTF-8. **Timestamps round down** to the second: a click lands at the chapter's first frame
  or before it, never after (rounding to nearest could skip up to half a second of a card).
  Rules checked (`youtube_problems`, on the rounded times, since that is what YouTube sees): at
  least 3 chapters, each ≥ 10 s (the first at 0:00 holds by construction); each broken rule is
  one warning starting `chapters:` naming the chapter, its span and a remedy (for a short intro:
  begin with a chapter or `intro: false`). The render logs them (so `render --json` lists them
  in `warnings`) and writes the file anyway; `vidgen validate` reports the same from the plan
  (`chapter_warnings`, part of `validate_warnings`). Without chapters, or with `youtube: false`,
  no file is written and an old one is removed (it would describe another video).
- **JSON**: combined `timings.json` gains `chapters` (published, `chapter_json`: the `Chapter`
  fields, times to 1 µs; also when both outputs are off); `render --json` gains top-level
  `chapters` (the same list) and `outputs.chapters` (the file or `null`); `post_render` hooks get
  `chapters` (the file or `None`); `RenderResult.chapters`. All within version 1.
- **Titles**: the chapter's title on one line (whitespace runs → one space), without its number
  (numbers are part of the on-screen design; "2 · Results" would read oddly in a menu next to
  the player's own numbering).
- Known limits: chapter titles are not translated per variant beyond what the variant's config
  says; a chapter's `number` is not shown in the outputs; YouTube also requires the list in the
  description to be the video's own (vidgen only writes the file); the MP4 has no chapter
  thumbnails.

## 53. Refinements (Step 50, thumbnail and GIF / clip export)

- **Config** (`config.py`): top-level `thumbnail: ThumbnailConfig | None` — a frame of a scene
  (`scene`, `beat` id or 1-based number, `at` seconds ≥ 0, `overlays` default true) or a designed
  card (`title` default the video's `title`, `subtitle`, `icon` | `image`, `preset`,
  `background`), plus `jpeg` (false) and `auto` (true). Frame and design keys together, frame keys
  without `scene`, `icon` with `image`: config errors; `VideoConfig.thumbnail_problems(thumb)`
  checks the scene and beat (also a beat on a silent scene); `vidgen validate` checks icon, image
  file, preset and colour token (`thumbnail.thumbnail_problems`, also run by `render`'s scene
  checks). `ThumbnailConfig()` (no section) = a designed card of the title. Out of scene
  fingerprints.
- **Size** (`thumbnail.thumbnail_size`): from the final `format`'s orientation (`scales.frame_orientation`):
  landscape 1280x720 (YouTube's recommendation), portrait 1080x1920 (Shorts / Reels covers),
  square 1080x1080. Every picture is cover-fitted (centre crop) to it with Lanczos.
- **Files**: `Project.thumbnail_path(preview, suffix)` = `<output>[_<variant>][_preview]_thumbnail.png`
  (and `.jpg`), the small copy `build/<render dir>/thumbnail/<name>_small.png` (long side
  `SMALL_LONG_SIDE` 320 px: YouTube's grid size, for the author — an AI agent opens it as an
  image). JPEG (`jpeg` / `--jpeg`): qualities 92 → 55 until ≤ 2 MB (YouTube's limit); without
  it an old JPEG is removed. Atomic writes.
- **Frame thumbnails** (`_frame_thumbnail`): the frame comes from the **scene's own render**
  (`scenes/<id>.mp4`), not from the joined video: a frame of a scene is the same with or without
  transitions, and it can be (re)made alone. `render_current` (format + fingerprint, §14) decides
  whether the scene is rendered first (`pipeline.render_scenes`, no join). Frame number
  (`frame_number`): a beat without `at` → its last frame, `round(start·fps) + round((end − start
  + pad)·fps) − 1`, capped by the next beat's first frame (the beat-end still of §13, computed
  from the timings instead of capturing stills, so a plain render is reused); `at` → `floor((beat
  start | 0) + at)·fps`; nothing → the last beat's end, or for a silent scene the frame before
  its fade-out (`duration − outro`, the scene type's `outro`); past the scene's end → error.
  Decoded with PyAV (exact frame, no seek rounding). From a render smaller than the thumbnail
  (e.g. `--preview`) an `info` check says it was scaled up.
- **Without overlays** (`overlays: false` / `--no-overlays`): overlays are composited inside the
  render (§41), so the picture without them needs another render. `Project.without_overlays()`
  is the project with `overlays: []` and every scene `overlays: false`, `bare = True`, whose
  `render_dir` is `build/<final|preview>[_<variant>]_bare`; the pipeline passes worker `--bare`,
  which does the same in the worker process. Its fingerprints differ (no overlay inputs), so the
  bare renders are reused while current; carries render the scene before into the bare folder
  too (`with_carried`). Decision: a separate folder rather than a flag on the normal render, so
  the normal renders (and the joined video) are never replaced by overlay-less ones. The scene
  lays out without the room reserving overlays take (the frame shows the scene as designed for
  a clean frame).
- **Designed thumbnails** (`design_thumbnail`, Pillow; the icon through Manim's Cairo camera as
  in `list-icons --sheet`, on the disc colour so no alpha is needed): in 16:9 the text on the
  left 58 %, the icon (on a `surface` disc, `primary`, ≥ 3:1 on the disc) or the image (a bleed
  panel) on the right; in 9:16 / square the visual on top (≈ 45 %), text centred below. Text
  sizes in units of the short side S (720 / 1080 px): margins 0.075 S; the title (font role
  `heading`, bold) the largest even size from 0.2 S down to 0.078 S whose balanced wrap
  (narrowest width keeping the line count) fits in 3 lines (4 in portrait) and the box; at the
  smallest size the rest is cut with `…` (`fit`). Then an accent bar (0.22 S x 0.016 S, theme
  `accent`), the subtitle (role `body`, 0.068 S, ≤ 2 lines). Colours: background = `background`
  (token / hex) or the theme's; title `text` unless below 4.5:1 there (then black / white, the
  stronger); subtitle the first of `highlight`, `primary`, `accent` ≥ 4.5:1, else the title's.
  `preset` uses `Theme.derive(ThemeConfig(preset=...))`: the preset alone, not the project's
  overrides (which would otherwise win over the preset). Fonts: the bundled file of the theme's
  family (`fonts.bundled_font_file`), else an installed font of that name, else
  `sheets.load_font`.
- **Checks** (`ThumbnailCheck(rule, severity, message)`, lint names where they mean the same):
  designed cards are measured at the small size (factor `320 / long side`): `min_font` title
  < 14 px / subtitle < 10 px (the title's minimum size 0.078 S is exactly 14 px small in both
  orientations), `contrast` < 4.5:1 (WCAG via `lint.color`), `fit`, `max_words` > 6 (info);
  all kinds: `file_size` > 2 MB, frame thumbnails `resolution` (info). A frame thumbnail's text
  is not measured (a plain render has no layout dump; `vidgen lint` checks scenes) — documented.
- **Render**: with `thumbnail:` and `auto`, `render_project` makes the thumbnail after the join,
  outside its extension session (a frame thumbnail may run `render_scenes`, which opens its own);
  the scene's render is current then, so nothing is rendered again unless `overlays: false`.
  Warnings are logged (`render --json` `warnings`); `RenderResult.thumbnail` (`ThumbnailResult`),
  `render --json` `outputs.thumbnail`, human `thumbnail:` line. Not in `post_render` hook data
  (the hook runs before it).
- **`vidgen thumbnail`** (`cmd_thumbnail`): the config's thumbnail, or `--scene` (+ `--beat`
  id or number — a digit string is a number unless the scene has a beat of that id —, `--at`,
  `--no-overlays`) checked like the config; `--preview`, `--jpeg`, `--jobs`, `--json`
  (`jsonout.thumbnail_document`).
- **`vidgen export gif|clip`** (`export.py`): source = the joined video + `timings.json` of the
  render dir (error naming `vidgen render [--preview]` when missing; durations must agree within
  0.1 s). `resolve_range`: with `--scene` times from its start (default the whole scene, `end`
  kept within it — `start + duration`, so a transition out of it is included), else video times.
  Default path `exports/<output>[_<variant>][_preview]_<scene|video>[_<from>-<to|end>s].<gif|mp4>`;
  `--output` elsewhere. Decision: an `exports/` folder in the project (not next to the output) —
  shareable artefacts, many per video, easy to ignore in git (`**/exports/`, also in the init
  template's `.gitignore`).
  - **GIF**: one FFmpeg pass, `fps, scale=W:-1:flags=lanczos, split, palettegen=stats_mode=full,
    paletteuse=dither=sierra2_4a:diff_mode=rectangle` (`stats_mode=full`: explainer graphics are
    mostly still, one palette for all frames avoids colour pumping; `diff_mode=rectangle`: only
    changed areas are re-dithered, no shimmer, smaller files), `-loop 0`. Defaults: width 480
    (270 for 9:16), ≤ the video's; 12 fps, ≤ the video's. **Budget** `--max-mb`: `next_try` —
    size ≈ width² · fps, needed factor × 0.9 split as fps × factor^(1/3) (≥ 5 fps) and the width
    taking the rest (≥ 160 px); at most `MAX_ATTEMPTS` 6 encodes or until nothing can be lowered;
    still too big → warning (`within_budget: false`). Attempts listed in the JSON.
  - **Clip**: stream copy when the start lies within half a frame of a keyframe (PyAV demux,
    packets only) and neither `--width` nor `--fps` changes the picture: `-ss <keyframe> -i`,
    `-c:v copy -frames:v N` (`-t` alone let a copy run 2 frames long); with `--with-audio` the
    sound comes from a second input seeked to the same time and is encoded AAC 192k (copied AAC
    packets started up to a packet early: the clip opened with 0.15 s of sound before its first
    picture). Otherwise re-encoded (`libx264 -crf 18 -pix_fmt yuv420p`, accurate input seek,
    `scale=W:-2`, `fps=F`). Chapters dropped. A joined video without crossfades / pushes / wipes
    stream-copies the scenes, so scene starts are keyframes and `export clip --scene X` copies.
- Known limits: frame thumbnails are not checked for text size / contrast; a designed card has
  one layout (title + bar + subtitle + one visual) and no background image behind the text; the
  `_bare` render folder is not cleaned up; GIF budgets assume size ∝ width² · fps (static
  explainer frames compress better, so it can take a few encodes); in a re-encoded join
  (transitions) keyframes fall where x264 put them, so most clips of it are re-encoded.

## 54. Refinements (Step 51, multi-language variants)

- **`language`** (`config.LanguageTag`, top level, so per variant by deep merge): a BCP-47 tag
  (`^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$`) normalised (`pt-br` → `pt-BR`, scripts title case,
  regions upper case). `None` = the English rules and nothing sent: every project without the key
  behaves exactly as before. `vidgen/languages.py` (no manim): `LanguageRules(code, name,
  conjunctions, prepositions, clinging, words_per_second, silent_final_e, iso639_2)` for `en`
  (Step 40's lists), `pt`, `es`, `fr`, `de`, `it`; any other language gets a neutral set (no word
  lists, no word rate, ISO 639-2 from a small table). `language_matches(entry, video)`: subtag
  prefix match (`pt` ⊂ `pt-BR`; no language = `en`).
- **Cues** (`vidgen.cues`): `phrase_break_cost(before, after, language=None)` uses the language's
  lists; punctuation counts in every language (sentence ends incl. `。！？`, clause marks incl.
  `،、，；：`, a break before `¿ ¡ «` is a clause break). `segment_cues`, `split_cues`,
  `caption_cues`, `subtitles.split_text / beat_cues / cues_from_timings / write_srt` take
  `language` (the SRT uses the combined timings' `language` by default; the pipeline passes the
  project's); captions read `project.config.language`. `speech.syllables(word, language)`: the
  silent final `e` only in English and French; `estimate_word_times` / `beat_word_times` pass it.
- **Lint** `narration_speed`: `unit: auto | words | characters`, `min_rate` / `max_rate` now
  default `None` = the language's range (`NarrationSpeedRule.limits(language) -> (unit, min,
  max)`); auto uses words for languages with a word rate, else characters per second
  (`speech.spoken_characters`: letters and digits; 8-17/s). `SceneContext.language`.
  Decision: per-language word ranges rather than one character mode for all, so English results
  are unchanged and the familiar unit stays where it is meaningful.
- **ElevenLabs `language_code`**: `VoiceConfig.language_code` / `VoiceEntry.language_code` (`str |
  false | None`). `voices.resolve_voice` stores the code actually sent
  (`languages.elevenlabs_language_code`): the configured code, `false` → none, `None` (auto) → the
  video language's ISO 639-1 subtag for `LANGUAGE_CODE_MODELS` (`eleven_turbo_v2_5`,
  `eleven_flash_v2_5`; other models reject the field). The provider sends it in the body and
  inserts `language_code=<code>` into the §7 hash parts before the text only when it sends one
  (hashes without a code are unchanged; no legacy kphi3 hash then). `Project._audio_differs`
  compares resolved voices, so a variant whose code is sent gets its own audio folder.
- **MP4 / outputs**: `ffmpeg.join(..., language=<ISO 639-2>)` tags the audio stream
  (`-metadata:s:a:0 language=por`); the combined `timings.json` gains `language`. Per-variant
  SRT, chapter list and thumbnail are already separate files (§52, §53); they carry the
  language through their (translated) texts. No `language` tag in FFMETADATA (the MP4 muxer
  stores no global language).
- **Pronunciation**: `PronunciationEntry.language` (tag or list); `load_pronunciation` leaves out
  entries for other languages (`pronunciation.applies_to`). `translation.language_warnings`: a
  variant in another primary language that keeps base inline entries unchanged (and matching a
  beat) gets a validate warning.
- **Translation files** (`vidgen/translation.py`, no manim):
  - *Markers*: `TextMarker(kind)` in `Annotated` metadata (JSON Schema `x-vidgen-text: text|ref`);
    `TranslatableStr = Annotated[str, TRANSLATABLE]`, `TextRef = Annotated[str, TEXT_REF]` (in
    `vidgen.api`). Every built-in `Params` / action / overlay text field is marked (titles,
    headings, captions, labels, items, table cells, legend / axis names, units, notes, callout
    labels, a lower third's name / title, a watermark's text, chapter `number` text, stat
    separators); refs: `bar_chart` / `pie` / `icon_grid` `highlight` (+ `groups`), `heatmap` /
    `scatter` `highlight`, `timeline` `highlight` / `now`, `map` arc ends. Shorthands:
    `SceneParams.text_shorthand` (`{type: "text" | ("field", F) | ("after", SEP) | ("fields",
    names) | ("model", M)}`) and `text_defaults` (`{"label": "id"}`), read with `getattr` so any
    pydantic model may set them.
  - *Keys*: `parse_key` / `format_key` over `Seg(kind, value)`: `.name` (mapping key, or the id of
    an item of `scenes` / `beats` (default `<scene>_b<n>`) / top-level `overlays` (type /
    `<type><n>`)), `[n]`, `["key"]`, `{"key"}` (the key itself, last), `=field`, `$sep` (last).
    Beat texts are `scenes.<id>.beats.<id>.text`. `_Cursor` reads / writes the raw mapping by key;
    `=field` wraps a string as `{field: string}` (written back only when a field is added) and
    makes the next field default to it.
  - *Extraction* (`extract_texts(data, scene_model, action_model, overlay_model)`, needs the
    models; `project_texts(project)` inside a project session): top-level `title`, `metadata`
    title / album / comment / description, `chapters.intro`, `thumbnail` title / subtitle,
    overlay options, then per scene `chapter`, params (walked by the field types: unions pick the
    member that fits the raw value — marked `str` first; lists by their first item; dicts by the
    model whose fields cover most keys; aliases and header synonyms), beat texts, action options
    (canonical or shorthand form, `ActionConfig.resolved`'s rule) and scene overlay overrides.
    Only values present in the raw config are listed (defaults are not). References: `TextRef`
    values and action targets naming a params text of the scene (whole, after `kind:`, or before
    `@`) → that text's key.
  - *File*: `TranslationFile {version: 1, language, source_language, entries: {key:
    TranslationEntry {source, hash, text, stale, old_source, obsolete} | text}, references}`
    (extra keys forbidden, keys parsed); `source_hash` = sha1[:10] of the source. Written with a
    comment header by `dump_translation_file` (YAML, `allow_unicode`, insertion order).
  - *Applying* (`apply_translations(data, doc) -> (data, TranslationReport)`; registry-free):
    `Project.load` merges the variant, validates, and when the merged config has `translations:`
    applies the file to the **raw** mapping and validates again (`Project.source_data` /
    `source_config` keep the untranslated form, `Project.translation` the report). Texts first,
    mapping-key renames last, then references (`_renamed`: whole value, `kind:` suffix, `@`
    prefix). An entry is applied when it has a text and its `hash` (or `source`) matches the
    current text and it is not `stale`; else the source stays (`untranslated` / `stale` /
    `unknown` in the report). Text is used as written (no stripping: `" min"`), a YAML block's
    final line break dropped. A missing file is not an error (`missing`, a validate warning).
    Decision: **apply at load on the raw config**, so every consumer (TTS, audio hash and folder,
    SRT, captions, scenes, chapters, tags, thumbnail, lint, storyboard) sees one translated
    config with no special cases, and applying needs no scene types (keys are plain paths;
    what needed the models — which fields are text, which places are references — was resolved
    when the template was written). Decision: **stale translations are not used** (gettext's
    fuzzy rule): after a source edit the old text may say something else; validate lists them.
  - *Merging* (`merge_template`): (1) same key, same hash → kept (a hand-written entry without
    source / hash is kept and gets them); (2) the same hash under another key of the same scene →
    moved (an item inserted before it); (3) the key remains, source changed → `stale: true`,
    `old_source`, text kept; leftovers: translated → `obsolete: true`, untranslated → dropped.
    References are rewritten from the current config every run.
  - *Command* `vidgen translate-template [--variant] [--lang] [--output] [--json]`
    (`write_template` → `TemplateResult`): the file is the variant's `translations:` or
    `translations/<variant>.yaml`; the language is `--lang`, else the variant's own `language`;
    prints a hint when the config does not name the file yet. JSON: `translate_template_document`.
  - *Validate*: `translation_warnings` (texts showing the source, stale, unknown keys, references
    the file lacks or that broke, file language ≠ video language, missing file) and
    `language_warnings` join `validate_warnings`; human `language [pt]: pt-BR (file: N
    translated, M stale)`; `validate --json` `language` / `translations` at the top level and per
    variant (`jsonout.translation_json`).
- **Fingerprint**: `translations` excluded from the config part (the texts are in the scenes /
    config already); `translation.py` is not a render input; `languages.py` is (captions).
    `language` is in the config part. Renders made before Step 51 are stale once (new config keys
    in the dump).
- **Example**: `examples/minimal` variant `pt` (`pt-BR`, `translations/pt.yaml`: 54 of 73 texts
  translated — title, intro, steps, feedback, sizes, trend, outro; picture, saying, math,
  listing and note left in English on purpose; the variant's own pronunciation of LaTeX / JSON;
  captions). `vidgen lint` of the translated scenes: 0 findings (two Portuguese texts were
  shortened: 44 words on the bullets slide, 6.3 s of dead air in a longer beat).
- Known limits: a translation file only changes texts present in the config (a stat's default
  `decimal_mark` cannot be added); number formats and the map's country names are not
  localised; a map arc shorthand `"A -> B"`, `lint_ignore` object patterns and targets naming a
  translated point label (`point:<series>@<label>`) do not follow translations; languages
  without spaces are cut at punctuation only; the storyboard / lint labels of vidgen itself stay
  English.

## 55. Refinements (Step 52, slides export: HTML)

- **Key frames** (`vidgen/deck.py`, no manim; shared with the PDF deck of Step 53, §56):
  `deck_frames(project, *, preview=True, mode="beat"|"scene", per_beat=1, overlays=True,
  dedupe=True, jobs=1, force=False) -> Deck`. The stills are the §13 frame stills, made current
  the §14 way (`storyboard.stills_current` → `pipeline.render_scenes(..., frames=per_beat)` for
  the stale or missing scenes only), so a deck after `storyboard` / `lint` / `render --frames`
  renders nothing. `overlays=False` uses `Project.without_overlays()` (§53: `build/..._bare`).
  - `beat` (default): every still is a slide — one per beat (its last frame: for reveal-per-beat
    scenes the fully built state, so the deck "builds" like a presentation), N per beat with
    `per_beat`, a silent scene's still(s) before its fade-out. `scene`: the scene's last still,
    all its beats as notes (`per_beat` > 1 is an error there). Decision: **beat by default** —
    scenes whose content is replaced per beat (walkthroughs, derivations, screenshot steps,
    maps) lose everything but the last state in scene mode; dedupe keeps beat decks compact.
  - **Dedupe** (`stills_alike`): consecutive stills of one scene whose pictures (at most 320 px
    wide, box-filtered) differ in at most 0.05 % of their pixels by more than 24 levels on a
    channel are one slide: the later still (the more finished one), both beats' notes, the first
    one's start (`DeckSlide.merged` counts the stills). Never across scenes. Burned-in captions
    or a moving progress bar make beats differ, so with those overlays nothing merges.
  - `DeckSlide(index, scene, scene_type, scene_number, scene_title, chapter, still, beats, k, n,
    time, scene_time, at, until, merged)`; `notes` (the beats' texts, a blank line between: the
    configured text, translated by the variant's translation file at load, §54 — not the
    pronunciation); `alt_text()` (`"<type> scene “<title>”: <narration, ≤ 160 chars>"`, the
    title from `params` `title` / `heading` / `text` / `name` / `quote`). `DeckChapter(title,
    label, index)` from `chapters.chapter_marks` (no planned timeline needed). `time` = §14
    `scene_starts` (transition overlaps included) + the still's scene time.
  - **Deck timeline** (play mode): the scenes' rendered durations back to back (no overlaps,
    so every slide gets its full time); a slide is on from the still before it in its scene (0 for
    the first) to its own still, the scene's last slide to the scene's end. `DeckClip(beat, audio,
    at, duration)` for each beat with an MP3 in `project.audio_dir` (the file the render used; its
    speech `start` / `end` from the scene timings).
- **Page** (`vidgen/slides.py`): `make_slides(project, ..., image_format="webp", quality=80,
  max_width=None, audio=False, separate=False, output=None) -> SlidesResult` and
  `slides_html(deck, images, size, audio)`. Default path `slides_path` =
  `exports/<output>[_<variant>][_preview]_slides.html` (the §53 `exports/` folder). One HTML file:
  pictures as base64 `data:` URIs (Pillow: WebP `method=4`, JPEG optimised progressive, or PNG;
  Lanczos down to `max_width`), CSS / JS read from package data `data/slides/deck.css` /
  `deck.js` and inlined, the deck data as `<script type="application/json" id="deck-data">`
  (`</` escaped), the MP3s as `<audio>` data URIs with `--audio`. `separate`: pictures
  `slide-NNN.<ext>` and `<beat>.mp3` in `<name>_files/` (earlier `slide-*` / `*.mp3` there
  removed first), referenced relatively. Pages over 50 MB log a warning. Each picture appears
  once in the HTML; the overview and the notes' "next" preview copy its `src` at run time.
  Decision: **WebP q80** default (every current browser; ≈ 3x smaller than PNG for these flat
  graphics, text stays clean); JPEG for old viewers, PNG for exact pixels.
- **Behaviour** (`deck.js`, no libraries, ES5-compatible syntax): one `<section class="slide">`
  visible at a time (others `hidden`), the `<img>` `object-fit: contain` in a black stage
  (letterboxed at any window shape); keys → / ↓ / Space / PageDown / Enter next, ← / ↑ /
  Shift+Space / PageUp / Backspace previous, Home / End, digits + Enter jump (a "Go to N" box,
  Esc / timeout clears), S / N notes, O / G overview, F fullscreen (bars hide after 2.5 s idle),
  P / K play, ? / H help, Esc closes / stops; clicks on the stage's left third go back, else
  forward; horizontal swipes (> 50 px). URL hash `#N` (`history.replaceState`, `hashchange`
  followed). Notes panel: beside the stage (30 %), below it on screens ≤ 760 px or portrait,
  with the slide's meta line and the next slide; its state kept in `localStorage` (guarded).
  Overview: a dialog layer, buttons grouped under chapter headings. Accessibility: slides are
  `role="group"` `aria-roledescription="slide"`, alt text, a polite live region announcing
  "Slide N of M, <chapter — title>", visible focus rings, icon buttons with labels / titles;
  `prefers-reduced-motion` drops the 0.22 s fade. Print CSS: one slide per page.
- **Play mode**: a clock (`performance.now`) runs along the deck timeline; the slide shown is the
  last one whose `at` ≤ t; the clip whose span contains t plays, re-seeked when it drifts > 0.3 s;
  navigating while playing seeks to the slide's `at`; it stops at the end. Without `--audio` it is
  a timed slideshow at the video's pace. Decision: clock-driven rather than chained `ended`
  events, so silent scenes, beats without MP3s, pads and seeking all follow one rule.
- **CLI** `vidgen slides` (`cmd_slides`), `--json` (`jsonout.slides_document`: options, page,
  pictures, `duration`, `stills`, `merged`, `rendered` / `reused`, per slide `{index, scene, type,
  chapter, beats, notes, k, n, merged, time, scene_time, at, until, still}`). `deck.py` /
  `slides.py` are not render inputs (fingerprints unchanged).
- **Tests**: fake stills + stubbed rendering for selection, dedupe, timelines, translated notes,
  page structure (parsed; pictures decoded with Pillow), separate files, CLI / JSON; one render
  test; a Playwright (Chromium) smoke test of navigation, notes, overview, hash and play mode
  with sound (skipped without Playwright; Playwright is not a dependency).
- Known limits: no per-slide `--scene` selection; titles and help texts of the page are English
  (the notes and pictures follow the variant's language); the deck shows frames, not motion
  (animations, clips); a merged slide's notes are joined without saying where the picture
  changed; slides of a 9:16 video are tall (letterboxed on landscape screens).

## 56. Refinements (Step 53, slides export: PDF)

- **Command**: `vidgen slides --format pdf` (one command, two deck formats; `--format html` the
  default) rather than a separate `slides-pdf`: the frame options (`--variant`, `--preview` /
  `--final`, `--mode`, `--per-beat`, `--overlays`, `--no-dedupe`, `--jobs`, `--force`) and the
  picture options (`--image-format`, `--quality`, `--max-width`) are shared. HTML-only `--audio`
  / `--separate` with a PDF, and PDF-only `--notes` / `--title-page` / `--paper` with HTML, are
  errors (`cli._slides_options`, before loading). `--image-format` / `--quality` defaults now
  depend on the format (HTML webp q80, PDF jpeg q85), so the parser's defaults are `None`.
- **Library** (`vidgen/slides_pdf.py`): **fpdf2** as the optional extra `vidgen[pdf]`
  (`fpdf2>=2.7.9`; also in `dev`, with `pypdf` for the tests). Decision: fpdf2 is pure Python
  (≈ 340 KB), embeds subsets of TrueType fonts with a ToUnicode map (extractable, searchable
  Unicode text — pt-BR accents), writes outlines, page labels, document info / XMP and alt text,
  and embeds JPEG files as they are (`DCTDecode`, no re-encode). Its dependency fontTools (~5 MB
  wheel with compiled speed-ups, pure-Python fallback) and LGPL-3.0 licence are why it is an
  extra, not a base dependency; vidgen does not bundle it. Without it, `make_slides_pdf` raises
  `VidgenError('... pip install "vidgen[pdf]" ...')` before rendering anything. Alternatives
  rejected: cairo's PDF surface (already installed with Manim) cannot load a font file through
  pycairo (fontconfig / Windows system fonts only) — the bundled Inter would not be guaranteed;
  ReportLab is several times larger for what this needs. fontTools' INFO logging (subsetting steps) is set to
  WARNING when fpdf2 is imported.
- **Pages**: `make_slides_pdf(project, *, preview, mode, per_beat, overlays, dedupe, notes=False,
  title_page=False, paper="a4", image_format="jpeg", quality=85, max_width=None, output=None,
  jobs, force) -> PdfResult(path, bytes, pages, options: PdfOptions, width, height, bookmarks,
  thumbnail, deck)`; `write_pdf(deck, options)` builds it from a `Deck`. Default file `pdf_path`
  = `exports/<output>[_<variant>][_preview]_slides.pdf`, `_notes.pdf` with notes.
  - **Slide pages**: `slide_page_size` — the video's aspect ratio, the long side 960 pt (13.33 in,
    a widescreen presentation's page; 16:9 → 960 x 540, 9:16 → 540 x 960); the picture fills it.
  - **Notes pages** (`notes=True`): A4 595.28 x 841.89 / Letter 612 x 792 pt portrait, margins
    48 pt; header (chapter `label · title` left, bold; the video's title right; a rule), the
    picture full width (at most half the page high, centred: 9:16) with a hairline border, a
    meta line (`Slide N / M · <scene title> · <m:ss.s> in the video`, 9 pt), the narration of
    the slide's beats (`DeckBeat.text`: the configured, i.e. translated, text) as paragraphs at
    11.5 / 17 pt in Inter, left-aligned, footer `page / total` (fpdf2's `{nb}` alias). Long
    notes break onto further pages with the same header (auto page break only on notes pages).
    A silent scene says "No narration (a silent scene)." in italics.
  - **Title page** (`title_page=True`): the thumbnail `vidgen thumbnail` wrote
    (`Project.thumbnail_path`, this quality's, else the other's; not made here — a designed
    thumbnail would need the theme session and a frame thumbnail a render), full page on a
    slide-page deck; otherwise / on notes paper: (the thumbnail above) the title (`metadata.title`
    else `title`) bold, the thumbnail config's `subtitle`, `artist · date`, and on notes paper
    "N slides with speaker notes · m:ss of narration".
- **Outline**: the title page (its title), then chapters (`DeckChapter`: `label · title`) at
  level 0 with their slides (`N. <scene title or id>`) at level 1; slides before the first
  chapter at level 0. Each entry points at the slide's first page (added right after
  `add_page`, so a notes page continued over several pages is found at its start).
  `page_mode = USE_OUTLINES` opens the bookmarks panel.
- **Document info**: `/Title` (metadata title or title), `/Author` (`metadata.artist`),
  `/Subject` (`description`, else `comment`), `/Keywords` (`album`, `genre`), `/Creator`
  `vidgen <version>`, creation date (now, UTC), catalog `/Lang` (the video's `language`).
- **Pictures**: `slides.encode_still` (JPEG optimised progressive at `quality`, or PNG),
  scaled down to `max_width`; alt text = `DeckSlide.alt_text()`. Each picture once per PDF.
- **Fonts**: the bundled Inter Regular / Bold / Italic (§21) via `add_font`, subset-embedded.
  Characters Inter lacks (CJK, Arabic, Hebrew, Devanagari, emoji) are left out (fpdf2 warns);
  no fallback fonts (none bundled for those scripts).
- **JSON**: `jsonout.slides_pdf_document` — the `slides` document with `output_format: "pdf"`,
  `pages`, `notes`, `title_page`, `thumbnail`, `paper`, `bookmarks` (no `files_dir` / `audio`);
  the HTML document gains `output_format: "html"`. Per-slide entries are shared
  (`jsonout._deck_slides`). `slides_pdf.py` is not a render input.
- **Tests** (`tests/test_slides_pdf.py`, fake stills from `test_slides`, read back with pypdf):
  page count and sizes (16:9, 9:16, A4, Letter), JPEG embedded as `DCTDecode`, PNG as
  `FlateDecode`, outline tree and destinations (incl. notes continued over pages), document
  info and `/Lang`, notes / header / footer text extracted, fonts are Inter, pt-BR text with
  accents and typographic quotes extracted exactly, quality / max width shrink the file, option
  errors, missing fpdf2, CLI / JSON. Layout was checked by eye on `pdftoppm` renders of
  `examples/minimal` (title page with thumbnail, notes pages, the 9:16 variant, pt-BR notes) and
  `examples/gallery` (chapter headers, typeset title page).
- Known limits: the page's own words (`Slide`, `in the video`, `No narration`, `slides with
  speaker notes`) are English, like the HTML deck's; no theme colours on a typeset title page
  (white; the thumbnail gives a themed one); no per-slide `--scene` selection; no fallback font
  for scripts Inter lacks.

## 57. Refinements (Step 54, readback check: speech to text)

- **Purpose**: the AI author cannot listen. `vidgen readback` transcribes each beat's MP3 and
  compares the transcript with what the beat should say, so mispronounced terms, misread numbers
  and dropped / added words show up as text an agent can act on (a pronunciation entry, a
  regenerated beat).
- **Provider seam** (`vidgen.stt`, like §7's TTS seam): `STTProvider` protocol (`name`,
  `check_available()`, `transcribe(path) -> Transcript`); `Transcript(text, words:
  tuple[TranscriptWord(text, start, end)], language)` with `to_json` / `from_json`,
  `word_texts()` / `word_times()`; `get_stt_provider(project)`; `stt_settings(project) ->
  {provider, model, language}` (resolved defaults, no provider import: the cache and the lint
  rule use it). Constructing a provider loads nothing and needs no key.
  - `faster_whisper` (`stt/faster_whisper.py`, optional extra `vidgen[stt]` =
    `faster-whisper>=1.0`; not in `dev`: ~70 MB of CTranslate2 / ONNX Runtime and a model
    download): `WhisperModel(model, device)` loaded on the first transcription, `transcribe(path,
    language, beam_size=5, word_timestamps=True, condition_on_previous_text=False,
    vad_filter=False)` (each beat on its own, so one mistake cannot carry over; no VAD so quiet
    words are not cut). Missing package → `VidgenError('... pip install "vidgen[stt]"')`; a model
    that cannot load (download refused, bad folder) → `VidgenError` naming the model.
  - `elevenlabs` (`stt/elevenlabs.py`): `POST /v1/speech-to-text`, multipart (`model_id`
    `scribe_v1`, `language_code` when known, `timestamps_granularity=word`,
    `tag_audio_events=false`, `file`), `ELEVENLABS_API_KEY` as for TTS. The TTS provider's
    retry / error / key-scrubbing loop moved to `tts.elevenlabs.post_with_retries` (shared; TTS
    behaviour unchanged). Only `type: word` entries of the response are words.
  - No OpenAI provider (the task's "openai?" was optional; the seam takes one more module).
- **Config** `stt: {provider: faster_whisper | elevenlabs, model, language, device}`
  (`SttConfig`): `model` default `small.en` for English / `small` otherwise (faster-whisper),
  `scribe_v1` (ElevenLabs); `language` default the video's language subtag (`en` without one),
  `auto` = detected (`None` sent); `device` `auto|cpu|cuda` (faster-whisper; not part of the cache
  key). `stt` is excluded from the render fingerprint; `stt/`, `readback.py`, `textnorm.py` are
  not render inputs.
- **Normaliser** (`vidgen.textnorm`, no manim): `normalize_words(words, language) ->
  [Token(text, source)]` (source = index of the input word, so differences map back),
  `normalize_text`, `fold` (casefold + accents removed: `você` = `voce`; STT accent slips are
  more common than accent-only minimal pairs), `number_words` / `english_number` /
  `portuguese_number`. Hyphens, dashes, slashes, `_` split words; apostrophes dropped inside
  words (`let's` → `lets`); numbers by the language's marks (en `1,000.5`, pt `1.000,5`), English
  decimals digit by digit (`one point zero eight`), Portuguese decimals as a number (`um vírgula
  cinquenta e sete`; digit by digit after a leading 0 or beyond 3 digits), `%` / currency symbols
  / English ordinals (`22nd`); other languages keep digits (canonical, group marks removed);
  `& + = × @` as words; dotted acronyms and runs of ≥ 2 single capitals joined (`G.P.U.`, `G P
  U` → `gpu`). The same function normalises both sides, so a convention only needs to be
  consistent, not linguistically perfect.
- **Comparison** (`vidgen.readback`): reference = the beat's **spoken** text (pronunciation
  applied, §45); `align(ref, hyp)` Levenshtein with ties broken towards more matches, then
  substitutions; `word_error_rate`. Ops are assigned to **written** words (spoken word → written
  word via `Spoken.word_groups()`; an insertion goes with the next word when that one differs
  too, else the previous one), and consecutive differing written words form one `Edit(kind,
  expected, heard, written, said, errors, at, after, term, entry, suggestion)`. An edit is dropped
  when its words are equal once joined (`overparameterized`, `KPhi3`) or when the heard words
  equal the normalised *written* words (the STT wrote `K-Phi-3` for "kay fye three"): these are
  writing differences. `errors` = non-equal ops of the block (S + D + I), so WER = Σ errors /
  normalised spoken words. `at` = start time of the first differing heard word.
- **Terms and suggestions**: `hard_term` (a digit, two capitals, a non-ASCII letter, or a
  capitalised word inside a sentence) marks a written word a pronunciation entry can fix; an edit
  over a replaced term has `entry: true`. Suggestions: entry → respell its spoken form; hard term
  → `add a pronunciation entry TERM: <how to say it>` (`<the number in words>` for digits);
  deletion → listen, `vidgen tts --force --beat ID`; insertion → listen; else a probable
  transcription slip. A stale MP3 (hash mismatch) adds "run `vidgen tts` first". `term_reports`
  aggregates terms over beats; `consistent` = heard differently in ≥ 2 beats (the strongest
  signal: one slip may be the transcriber's).
- **Flagging**: `wer > lint.rules.readback.max_wer` (default 0.1; `--max-wer` overrides). Below
  it, edits are still reported (JSON) and counted in terms. Exit code 0 whenever the command ran;
  the lint rule is the failing check.
- **Cache**: `build/readback/<sha1(json({audio: sha1(mp3), provider, model, language}))>.json`
  `{version 1, audio_sha1, stt, beat, transcript}`: content-addressed, so variants / qualities
  sharing audio share transcripts and a regenerated MP3 is transcribed again; `--force`
  re-transcribes. In `build/` (not `audio/`): derived, cheap to drop, never committed (kphi3's
  committed `audio/` stays untouched). The provider is created only when something must be
  transcribed (an all-cached run works without the extra or key).
- **CLI** `vidgen readback [PROJECT] [--variant] [--beat ID ...] [--max-wer RATE] [--force]
  [--json]`: progress `[n/N] transcribed <beat> (s)`, then `report_lines` (settings + counts,
  skipped beats, flagged beats with each edit `describe()` + `@ time` and `fix:` lines, worst
  beats, terms misheard in several beats). JSON `jsonout.readback_document` (version 1, new
  document): `project, variant, audio_dir, stt, max_wer, transcribed, cached, elapsed, summary
  {beats, flagged, words, errors, wer, worst}, beats[], skipped[], terms[]`.
- **Lint rule** `readback` (scope `scene`, default warning, `ReadbackRule{severity, max_wer}`,
  last in `LINT_RULES`): `SceneContext.readback` (beat id → `BeatReadback`) is filled by the
  runner from `readback.cached_readback` only when the rule runs and is not `off`; it never
  transcribes, so without `vidgen readback` it reports nothing ("off unless transcripts exist").
  The finding: `value` = WER, `limit` = `max_wer`, time = the beat's start, message quoting up to
  3 edits and the first suggestion, pointing to `vidgen readback --beat ID`.
- **Tests** (`tests/test_readback.py`, all mocked): number words (en / pt), digits in other
  languages, case / punctuation / hyphens / acronyms / pt-BR accents, alignment and WER, writing
  differences not counted, misheard pronunciation entry, terms without entry, insertions /
  deletions with times, pt-BR names, `hard_term`, settings defaults and config errors, a fake
  `faster_whisper` module (options, model loaded once, load error, missing package), ElevenLabs
  multipart request / response / errors with a mocked `urlopen`, the transcript cache (hits,
  `--force`, new audio, new settings), skipped / stale / unknown beats, the CLI (human + JSON,
  documented keys), the lint rule end to end on fake renders and as a unit, the fingerprint.
- **Known limits**: no real STT run was possible while building it (Hugging Face model downloads
  were refused by the build environment's proxy; see HANDOFF.md Step 54); number words only for
  English and Portuguese; English "and" inside spoken numbers ("two hundred and five") and years
  read in pairs ("twenty twenty-four") are not normalised; STT errors on ordinary words are
  reported as possible slips, not filtered.

## 58. Refinements (Step 55, generated images)

- **Purpose**: pictures for `image` scenes (and extension scene types) from a prompt, made once
  (they cost money), stored with the project and reused; the video can be previewed, laid out
  and linted before any picture exists.
- **Param** `GenerateImage` (`vidgen.imagegen`, exported by `vidgen.api`; a plain pydantic model,
  extra keys forbidden, a string = the prompt): `prompt` (required), `negative` (`""`), `style`
  (preset / words / `none`; default `imagegen.style`), `aspect` (`auto|landscape|portrait|square`),
  `seed` (≥ 0). The `image` scene's `path` became optional with `generate` beside it; exactly one is
  required (model validator). A scene type opts in by having a top-level field holding a
  `GenerateImage`; `find_images` discovers it through the registry (built-ins and extensions).
- **Config** `imagegen: {provider: openai, model: gpt-image-1, size: auto | WxH, quality, style,
  negative}` (`ImagegenConfig`). Part of the render fingerprint (it decides which picture or
  placeholder a scene shows); the pictures themselves are files under `assets/` (already tracked).
- **Request** (`image_request(project, generate) -> ImageRequest`): size = `imagegen.size`, or the
  model family's size for the aspect (`auto` = the final `format`'s orientation, so a 9:16 variant
  gets portrait pictures): gpt-image `1536x1024 / 1024x1536 / 1024x1024`, dall-e-3 `1792x1024 /
  1024x1792 / 1024x1024`, dall-e-2 `1024x1024`; quality default medium / standard / none. Text sent
  = `<prompt>. Style: <words>. Avoid: <negative; imagegen.negative>.` (OpenAI has no negative
  prompt). Style presets `photo, illustration, flat, isometric, watercolor, line_art, render_3d,
  cinematic` (`STYLE_PRESETS`). **Key** = sha1(json{v: 1, provider, model, size, quality, seed,
  prompt: text})[:16]; files `assets/generated/<key>.png` + `<key>.json` (`prompt, negative, style,
  sent_prompt, revised_prompt, provider, model, size, quality, seed, created (UTC date), scenes`).
  Content-addressed: no "stale" state; a changed request is "missing", the old file an orphan
  (reported, never deleted); equal requests share one file. Meant to be committed (like `audio/`).
- **Provider seam**: `ImageProvider` protocol (`name`, `check_credentials()`, `generate(request)
  -> GeneratedPicture(data: PNG bytes, revised_prompt)`), `get_image_provider(project)`. One
  provider: `OpenAIImageProvider` (`imagegen/openai.py`, stdlib urllib): `POST
  https://api.openai.com/v1/images/generations`, `Authorization: Bearer $OPENAI_API_KEY` (read at
  request time, never stored / logged / in errors), body `{model, prompt, n: 1, size, quality}` +
  `response_format: b64_json` for DALL·E models (gpt-image models always return base64); response
  `data[0].b64_json` (+ `revised_prompt`), non-PNG data converted with Pillow. Retries: 3 (backoff
  4 / 8 / 16 s or `Retry-After`, cap 60 s, timeout 240 s) on 429 / 5xx / timeouts — not on a 429
  for `insufficient_quota` / `billing_hard_limit`. The ElevenLabs loop moved to
  `vidgen.httpapi.post_with_retries(url, data, headers, service, secret, ..., transient=)`
  (`tts.elevenlabs.post_with_retries` keeps its signature and messages).
- **Placeholder** (`imagegen/placeholder.py`, Pillow): the request's aspect at long side 1280 px,
  surface → surface/primary gradient, rounded outline in dim, a picture glyph in primary, "IMAGE
  TO GENERATE", the prompt (wrapped, ≤ 6 lines, shrunk then cut) in text, "placeholder · run vidgen
  imagegen" in dim; the whole block centred so a `cover` fit crops margins, not text. Cached as
  `build/imagegen/<key>-<sha1(version, colours, font, size, prompt)[:10]>.png`.
  `generated_image(project, generate, theme)` returns the stored PNG or this placeholder.
- **Never a provider call outside `vidgen imagegen`**: `validate` warns (`imagegen_warnings`):
  pictures not made yet, and prompts that quote text or mention text words (text, words, letters,
  label, title, logo, slogan, says, written, font...) or charts / diagrams / tables, unless negated
  ("no text", "without lettering"); summary line `images: N generated, M missing` (and per variant
  whose pictures differ). `render` / `storyboard` log `generated image not made yet for <scenes>`.
- **CLI** `vidgen imagegen [PROJECT] [--dry-run] [--force] [--scene ID ...] [--variant NAME]`:
  distinct requests in video order; dry run prints each key, scenes, size, model, quality, cost
  estimate and the full prompt, then the total (`PRICES`: OpenAI list prices of 2025 per model /
  quality / square-or-not; unknown → "of unknown price"); a real run checks the key first, writes
  PNG + JSON atomically per picture, and on an error names the scene and how many were done.
  Orphans are listed (base config + all variants count as users).
- **Responsible use**: no content filter beyond the provider's (its refusals surface as errors);
  CONFIG.md asks not to generate misleading pictures of real people or brands.
- **Tests** (`tests/test_imagegen.py`, urlopen mocked): prompt composition, style / negative
  resolution, sizes per format / aspect / model, the cache key's inputs, text-in-prompt detection,
  `image` params (`path` xor `generate`), validate warnings and summary (+ variant), render
  warning, provider request / response / conversion / bad responses, 429 retry with Retry-After,
  timeouts, quota and 400 errors not retried with the key scrubbed, missing key, dry run without a
  key, generate / skip / force / `--scene`, orphans, an error midway, a stub provider, the
  placeholder card and its cache, the fingerprint, a render of the placeholder and of a stored
  picture (16:9 and 9:16).
- **Not done**: `generate:` on `screenshot` (its `px` callouts and magnifier need the real
  picture's pixels) and as a thumbnail background (designed thumbnails have no picture behind the
  text yet); no `--json` for `vidgen imagegen`; no image editing / variations endpoints; no second
  provider; prices are a snapshot.

## 59. Refinements (Step 56, the author guide for AI agents)

- **Two agent files, two audiences**: `CLAUDE.md` is for agents developing vidgen; `AGENTS.md`
  (repository root) is for agents **using** vidgen to make videos and decks. Each says so at its
  top and points to the other.
- **One source, shipped**: the guide is package data, `src/vidgen/data/guide/AGENTS.md`
  (`pyproject` package-data `data/guide/*`), so it is there after `pip install`; the root
  `AGENTS.md` is a byte-identical copy (a test fails when they differ). Not a render input
  (`guide.py` is in `NOT_RENDER_INPUTS`; the data folder is outside the source digest).
- **Topics**: each `##` section is introduced by a marker line `<!-- topic: NAME (also: ALIAS,
  ...) -->` (invisible when the Markdown is rendered). `vidgen.guide`: `GUIDE_FILE`,
  `GuideTopic(name, title, aliases, text)`, `guide_text()` (markers removed), `guide_topics()`,
  `find_topic(name)` (name or alias, case-insensitive; unknown → `VidgenError` with
  did-you-mean and the topic list), `topic_lines()`. Topics: `start`, `workflow`, `pacing`,
  `social`, `scenes`, `design`, `actions`, `overlays`, `audio`, `examples`, `outputs`,
  `troubleshooting`.
- **CLI** `vidgen guide [TOPIC] [--list] [--json]`: the whole guide, one topic, or the list
  (`TOPIC` with `--list` is an error). No PROJECT argument (the guide does not depend on one).
  `--json` (in `JSON_COMMANDS`): `{topic, title, topics: [{name, title, aliases}], text, path}`.
- **Kept true by tests** (`tests/test_guide.py`): every `vidgen <command>` in a code span or
  block exists, with every `--option` written after it; the scene chooser table covers every
  built-in type, its params column names real params (or their `title` / `heading` synonyms);
  every type has a snippet; the presets, actions and lint-rule tables list exactly the
  built-in ones; every sound and music bed is named; and every fenced `yaml` block, wrapped
  into a config (a scene list, a partial config, or top-level keys plus one scene; files under
  `assets/` copied from the examples), passes `vidgen validate`'s checks (`validate_all`).

## 60. Refinements (Step 57, scene gallery)

- **`vidgen gallery [PROJECT] [--output DIR] [--types T,T] [--formats 16:9,9:16] [--theme PRESET]
  [--clips | --no-clips] [--jobs N] [--force] [--json]`** (`vidgen.gallery.make_gallery`): every
  registered scene type rendered from one canonical sample at 16:9 and 9:16 into a Markdown
  gallery, default `docs/gallery` (committed in this repository). `PROJECT` (or a config file in
  the current folder) adds the project's own types, its theme (unless `--theme`) and extensions.
- **Samples: one source.** A built-in type's sample is its snippet in the guide's `scenes` topic
  (`guide_samples()`: the yaml blocks are split into list items, keeping the text as written; the
  first of a type, a later one replacing a `generate:` snippet that only renders a placeholder);
  the block's first comment line (`# data`) is the index group, the chooser table's first column
  the "use it for" line (`chooser_uses()`). A project's type takes its first scene in
  `video.yaml` (`project_samples()`, YAML dumped). A name whose class is registered under an
  earlier name (`flowchart` → `diagram`) is an alias: listed, not rendered (`GalleryType.alias_of`).
  Files under `assets/` in the guide's snippets map to stand-ins shipped in `data/gallery/`
  (`sample_asset()`: `picture.png` for `image`, `app.png` for other pictures, `clip.webm` for
  videos — made by `tools/make_gallery_clip.py` from `app.png`).
- **Work project** `<project or .>/build/gallery/video.yaml`: every sample (id = type name),
  preview 640x360 @ 12 fps, variant `portrait` 360x640; always all samples and files, so a
  `--types` run does not make the others' fingerprints stale (they see the config and `assets/`).
  Rendered with `render_scenes(..., frames=1)`; current stills are reused (`stills_current`). The
  "audio missing" warning is filtered (samples have no audio by design).
- **Media**: the last still of each scene saved as an optimised PNG (`media/<type>-16x9.png`,
  `-9x16.png`; 640x360 / 360x640); a GIF of the scene up to its last beat's end (no fade-out:
  full-frame changes cost the most bytes), 320 / 180 px wide, 6 fps, 32-colour palette without
  dithering (flat graphics), last frame held 1.5 s (`export.write_gif(..., colors, dither, hold)`,
  shared with `vidgen export gif`). Deterministic: no times or paths in the pages, Pillow and
  FFmpeg outputs are reproducible for the same inputs and versions, and render workers now run
  with `PYTHONHASHSEED=0` (unless set): with a random per-process seed, frames during a camera
  move (zoom actions, focus steps) differed by a few pixel values between two renders, so their
  GIFs changed on every regeneration. Checked: two `--force` regenerations give byte-identical
  files except `screenshot-9x16.gif` (the picture's sub-pixel edges while the camera moves over
  an image differ between renders; not tracked down, the frames look the same); a regeneration
  that reuses the renders is byte-identical.
- **Pages**: `README.md` (by group: type, stills linked to the page, use; aliases "same type as";
  types without a sample "no sample", types without a page in the folder "not rendered here
  yet"; a project type's "use" is the first sentence of its docstring) and `<type>.md` (use, description = first paragraph of
  the class / module docstring, stills, GIF links, the YAML as written, a params table from the
  `Params` model with nested fields as `a.b`, targets, beat count). An index after a `--types`
  run still lists every type, with whatever stills the folder has.
- **What is committed** (decision): the pages, all stills and all GIFs, about 4.4 MB in total (1.3 MB stills, 3.1 MB GIFs), under
  a tested 8 MB budget (`tests/test_gallery.py`): humans browsing GitHub and agents reading the
  docs see every type without rendering; clips are small enough at 320 px / 6 fps / 32 colours (a regenerated GIF adds to the history, so they stay small). A test
  keeps every page's YAML equal to the guide's current snippet and the index listing every type.
- **Routed visual fixes** (Steps 37 and 56):
  - `map`: a regional view in a vertical frame is narrowed to the longitudes that fill the frame
    at the view's latitudes, around its items (`_portrait_region`; before, the frame was filled
    by growing the view north and south: `europe` showed mostly Africa, Europe tiny). Country
    labels that need a leader avoid crossing earlier leaders and labels, and a label must not
    stand nearer another labelled place (any step) than its own (`_misleading`); when the first
    spot fails, `_clear_spot` searches eight directions out to 3 units (the empty bands above and
    below the map in 9:16).
  - `screenshot` / `video_clip`: `steps[].focus` defaults to auto (`None`): `true` in a vertical
    frame for a landscape picture (≥ 1.2:1), else `false`; a focus view taller / wider than the
    picture is centred on it, a smaller one stays on it. `video_clip` `fit: auto` (new default):
    `contain`, but a landscape clip without callouts in a vertical frame (not `bleed`) is shown
    as a nearly square part from its middle (`cover` into a square room, less the layout's 10 %
    vertical inset).
  - Callout labels (`kind: label`): `label_spot` gained `clearance` (soft distance from `avoid`),
    `rivals` (a spot clearly nearer — under 0.75x the own distance — another bar, value or the
    title than its target is penalised and counts as blocked) and `straight` (above / below /
    beside before the corners); `side` is now honoured only while a spot on that side is clear,
    else the best clear spot elsewhere is used (also for arrows and magnifiers with `side`).
  - Lint rule **`label_spacing`** (warning, `min_gap` 0.02 of the shorter side): a label on its
    own plate (filled rounded shape without an outline — an outlined badge such as the
    timeline's "Now" tag sits in its line by design —, not the background colour, behind exactly one text, at most
    2.2x its height and 3 heights wider; the text's backdrop is the plate) closer than `min_gap`
    to another text (not lone symbols, not the text framed by an outline in the plate's colour:
    the callout's own mark). `text_overlap` / `covered_text` missed these (no overlap, no
    cover). A `box` / `circle` tag (`tag_spot`) gets the same soft `clearance` (0.2 units) and
    the same spots one clearance further out.
