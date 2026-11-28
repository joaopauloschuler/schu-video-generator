# schu-video-generator — design spec

A configurable generator for narrated, animated explainer videos (Manim + TTS + ffmpeg).
The project and pip distribution are called `schu-video-generator`; the command (`vidgen`, also
`vidgen-mcp`) and the Python package (`vidgen`, `src/vidgen/`) are `vidgen`, and so is every name
below unless it says otherwise. `vidgen.DIST_NAME` (`"schu-video-generator"`) is used where the
distribution is meant: the reinstall hint (`errors.REINSTALL`), the PDF deck's creator, the HTML
deck's `generator` and the MCP server's advertised name. The JSON envelope key `vidgen`, the
`vidgen://` MCP resources and `--version` (`vidgen 0.3.0`) keep the command's name.
Each video is a **project folder** with a config file; the pipeline is shared, and each project
can **extend** the tool with its own scene types, helpers, theme tokens and pipeline hooks.

Status of this document: it describes the implemented system (version 0.3.0). §1–§9 are the core
contract; each later numbered section covers one feature area. Where a later section refines an
earlier one, the later section is what the code does. §63 lists what changed for users of 0.1 in
0.2.0; `CHANGELOG.md` lists the changes since. Changing a public interface requires updating this
file in the same commit. User documentation: README.md, docs/CONFIG.md (every config key, checked
by `tests/test_docs.py`) and docs/EXTENDING.md.

---

## 1. Goals and non-goals

Goals
- One engine, many videos. A new video = a new project folder, no engine edits.
- Config-only videos for common explainers (built-in scene library).
- **First-class extensibility**: any project can add scene types, helpers, theme tokens and hooks
  in its own `extensions/` folder and use them from config by name. A project extension can be
  promoted into the core library unchanged.
- Narration-driven timing: every beat's animation lasts as long as its audio (+ padding).
- Incremental work: TTS only for changed beats; only changed scenes re-render; fast previews.
- Runs on Windows (primary user platform), Linux and macOS.

Non-goals
- A declarative animation DSL: complex animation lives in Python scene classes.
- A GUI video editor.

## 2. Repository layout

Module map of `src/vidgen/` (one line per module or family; "pure" = no manim import). The section
named is where each is specified.

**Core and CLI**
- `__init__.py` (`__version__`, `DIST_NAME`), `__main__.py` (`python -m vidgen`), `api.py` (THE
  public surface, §6.4), `cli.py` (argparse CLI, §8), `jsonout.py` (`--json` documents, §11),
  `schema.py` (JSON Schema, §12), `describe.py` (scene/action descriptions for `list-scenes`),
  `errors.py` (`VidgenError`, `Problem`, `REINSTALL`), `fileio.py` (atomic writes; replacing files
  Windows programs keep open).
- `config.py` (pydantic v2 models of `video.yaml`, §4), `project.py` (`Project`: locate/load config
  with `include:` files, variants, paths, §3–§4), `includes.py` (`include:` files and named sets,
  §69.35), `registry.py` (scene-type, action and overlay registry), `_origin.py` (builtin vs
  extension origin), `extensions.py` (discovery/import, §6.1), `hooks.py` (§6.2), `runtime.py`
  (active Project/Theme, §6.3), `scene.py` (`NarratedScene`, §5).
- `render/`: `worker.py` (one scene per process, §5.2), `pipeline.py` (selection, padding, join),
  `ffmpeg.py`, `fingerprint.py` (what a scene's render depends on, §14, §63), `jobs.py` (`--jobs
  auto`, §70), `disk.py` (frames-clip disk estimate and cleanup, §120.9).
- `videoplan.py` (planned timeline before rendering, §41; planned chapters, §42), `transitions.py`
  (§49–§50, §69.45; pure), `carry.py` (continuity, §50), `cuts.py` (§101), `shorts_suggest.py`
  (§105.6), `audio_only.py` / `audio_encode.py` / `sections.py` / `transcripts.py` / `staging.py`
  (audio-only renders, §111), `sound_design.py` / `scoring.py` / `delivery.py` (audio dramas, §112).

**Theme, layout and drawing helpers**
- `theme.py` (precedence §19), `presets.py` (§19–§20), `scales.py` (§20), `themelist.py`
  (`list-themes`), `fonts.py` (bundled fonts, roles, §21; project `fonts/`, §119), `terms.py`
  (one colour per concept, §87.3).
- `helpers.py` (theme-aware text, drawing utilities), `layout.py` (§5.3), `regions.py` (§18),
  `graph.py` (layered graph layout, pure, §31), `callouts.py` (§37), `clips.py` (video clips,
  §38), `geo.py` (world map, Equal Earth, pure, §39), `charts.py` (§33–§34), `geometry_marks.py`
  (§87.7), `mathexpr.py` (safe maths expressions, §87.6), `word_anchors.py` (`at: "@word"`,
  §87.2), `references.py` / `citations.py` (§95.14).
- Icons and vectors: `icons.py` (registry, pure, §22), `icon_mobject.py`, `iconlist.py`
  (`list-icons`, §22–§23), `svgclean.py` (SVG sanitiser, pure, §65), `vector_mobject.py` (§65).
- Overlays: `overlays.py` (framework, §41), `overlay_layer.py` (compositing, §41), `hud.py`
  (heads-up display maths, pure, §102.5).
- Particles and camera: `particles.py` (pure, §69.9), `particle_field.py` (§69.9, §69.39),
  `camera.py` (camera views in bounds, pure, §69.7).
- Diagrams: `iso_blocks.py`, `iso_labels.py`, `iso_vector.py` (iso diagrams, §90).

**Review and checking**
- `capture.py` (stills, §13), `introspect.py` (layout dump, §15), `activity.py` (timings and
  motion, §17), `storyboard.py` / `sheets.py` (contact sheets, §14), `animatic.py` (§75),
  `motion_check.py` (`vidgen motion check`, §121.3, §122.5), `lint/` (`vidgen lint`, §16–§17:
  `rules.py` framework, `run.py`, `findings.py`, `report.py`, `color.py`, and one `*_rule(s).py`
  per area: layout, timing, cartoon, readback, narration, music, generated, iso, plot, calc,
  science, genetics, orbit, particle, space, shorts, term, three_d, web).
- `readback.py` (§57), `speech_flags.py` (§78), `textnorm.py` (§57), `stt/` (speech-to-text seam:
  `faster_whisper.py`, `elevenlabs.py`, §57), `audio_check.py` (loudness presets, §111.2).

**Outputs**
- `subtitles.py` (SRT, §43), `cues.py` (caption cues, §43), `chapters.py` (§42),
  `chapter_export.py` (§52), `thumbnail.py` / `export.py` (§53), `deck.py` / `slides.py` /
  `slides_pdf.py` (§55–§56), `gallery.py` (§60), `guide.py` (`vidgen guide`, §59).

**Speech and sound**
- `tts/` (provider seam, §7, §66): `elevenlabs.py`, `openrouter.py` (§66), `kokoro.py` (§68),
  `prosody.py` (§72), `effects.py` (`EffectProvider`, §100.2), `cache.py` (audio status), `run.py`
  (`vidgen tts`); `httpapi.py` (POST with retries and scrubbed errors, plain GET; shared by the
  paid providers).
- `kokoro_voices.py` (§68), `emotions.py` (§72), `voice_effects.py` (§100.2), `voices.py` (§46),
  `pronunciation.py` (§45, §88), `voicesounds.py` (§69.33), `overlap.py` (§69.34), `speech.py`
  (word times, §43), `languages.py` / `translation.py` (§54), `dubbing.py` (§80) — all pure.
- `sfx.py` (§47), `ambience.py` (§69.39, §69.62), `music.py` (beds, files, composed music, §48,
  §82–§83), `music_pieces.py` (§93.10), `composer.py` (§83), `musicfit.py` (§84), `score.py`
  (§82), `soundfont.py` (§81), `synth.py` (§81–§82), `mix.py` (§48), `loudness.py` (BS.1770-4,
  §48), `listen.py` (Listen page, §92), `music_video_plan.py` (§121.2), `music_space_plan.py`
  (§122.12).
- `studio/` (score files, no video code, §93: `theory`, `patterns`, `instruments` and per-family
  instrument modules, `effects`, `patches`, `score_file`, `render`, `templates`, `measure`, `check`,
  `beds/`); `studio_app/` (`vidgen studio`, §94).

**Authoring without AI**
- `outline.py`, `prose.py`, `plan.py`, `plan_yaml.py` (`vidgen plan`, §61), `screenplay.py`
  (§69.25), `random_cast.py` (`vidgen cast --random`, §69.49), `story_text.py` /
  `story_places.py` / `story_draft.py` (`vidgen story draft`, §105.5) — all pure.

**Cartoons and worlds**
- `cartoon/` (§69; about 100 modules, one per topic): characters and looks (`character.py`,
  `generator.py`, `svg_look.py`, `clothes.py`, `animals.py`, `robots.py`, …), motion and acting
  (`poses.py`, `transition.py`, `visemes.py`, `acting.py`, `keyframes.py`, `holding.py`,
  `seating.py`, `riding.py`, `foley.py`, …), directing (`directing.py`, `shots.py`, `reframe.py`,
  `host*.py` §71), the stage, its props, rooms, light, weather and effects (`stage.py`, `props.py`,
  `lighting.py`, `drawing_style.py` §79, `wind.py`, `storm.py`, `effects.py`, …), story effects
  (§100, §102), iso worlds (`iso_*.py`, §89–§107) and platform levels (`level_*.py`, §86). Pure
  maths modules are paired with Manim drawing modules (`*_drawing.py`, `*_shapes.py`, …).
- `world/` (platform and iso world model, §86, §89).

**Science**
- `plotcore/` (chart core, pure, §97), `plot_draw.py` (its drawing layer), `quantities/` (units
  and worked calculations, pure, §97.9), `orbits/` (§98), `flight/` (§123.7), `particle_physics/`
  (§99), `cellworld/` (cell model, pure, §95), `cell_draw/` and `cell_vector.py` (its drawing,
  §95.6), `genetics/` (§96).

**Generated media, browsers, remote runs**
- `imagegen/` (§58, §64–§65: `openai.py`, `openrouter.py`, `placeholder.py`, `run.py`).
- `videogen/` (§113): requests and cache key (`__init__`), `models.py`, providers (`openrouter.py`,
  `comfyui*.py` + `*_graph.py` §113.20, `mock.py`), `ledger.py` (budget), `run.py`, sheets and
  subjects (§113.3, §113.16, §113.24), `shots.py`, `inputs.py`, `canny.py`, `chain.py`, `qa.py`,
  `takes.py`, `compose.py`, `workflow.py`, `host*.py` (quick-tunnel hosting, §115);
  `generated_layer.py` (takes laid into frames, §113.4); `clip_join.py` (§117).
- `browser/` (Chromium for `3d` and `web`, frames clips, still planning, §118.5, §120.9),
  `three_d/` (§114), `web/` (`web` scenes, §118, §120, §122–§123).
- `mcp_server.py` / `mcp_tools.py` (§62); `remote.py`, `colab.py`, `colab_ssh.py`,
  `colab_rsync.py`, `colab_transfer.py`, `colab_vm.py` (`vidgen remote` and the Colab route,
  §113.20).

**Scene library and package data**
- `scenes/`: the built-in scene types, beat actions and overlays, registered like extensions;
  `scenes/__init__.py` imports every module and its docstring lists which module holds which
  action and overlay.
- `templates/minimal/` (`vidgen init`), `data/`: `fonts/` (Inter, Source Serif 4, JetBrains Mono
  NL, OFL), `icons/` (Lucide, ISC, §22), `geo/` (Natural Earth 1:110m, §39), `slides/` (§55),
  `guide/AGENTS.md` (§59), `gallery/` (§60), `openrouter/` and `kokoro/` (dated model/voice
  snapshots, §66, §68), `pronunciation/` (§88), `sets/` (built-in stage sets, §76–§77), `three/`
  (three.js 0.186.1 + add-ons, §114, §118.14), `web/` (page runtime, `libs/`, `modules/`
  (`vidgen/...` ES modules), `parts/`, `starters/`; §118–§124).

**Outside `src/`**: `tools/` (maintainer scripts, not shipped: icon vendoring, world map, example
assets, gallery media, Colab setup), `tests/` (pytest, no network), `examples/` (`minimal`,
`custom_scene`, `kphi3`, `plan` (golden output of `vidgen plan`), `cartoon`, `cartoon_series`,
`cartoon-music-box`, …), `docs/` (`CONFIG.md`, `EXTENDING.md`, `ICONS.md` (generated), cookbooks,
`gallery/` written by `vidgen gallery`), `AGENTS.md` (copy of `data/guide/AGENTS.md`), `DESIGN.md`,
`CLAUDE.md`, `README.md`, `CHANGELOG.md`, `THIRD_PARTY_NOTICES.md`, `pyproject.toml` (console
scripts `vidgen`, `vidgen-mcp`; Python >= 3.10).

## 3. Project folder layout

```
my_video/
  video.yaml              # config (video.json also accepted)
  extensions/             # optional; every *.py and every package here is auto-imported
  assets/                 # files referenced by scenes (paths relative to the project root)
    icons/                #   project icons <name>.svg (+ icons.json), §22
    generated/            #   `vidgen imagegen`: <key>.png + <key>.json (committed), §58
  translations/           # translation files of language variants, §54
  audio/                  # generated, kept: <beat_id>.mp3 + <beat_id>.hash
    <variant>/            #   only for a variant whose voice or beat texts differ (§7)
  build/                  # generated: renders, timings, intermediate files
  output/                 # deliverables (moved by `output_dir:` / `--output-dir`, §4)
    <output>.mp4 / .srt   #   suffixes: _preview, _draft (§74), _<variant>
    <output>_chapters.txt #   YouTube chapter list (§52)
    <output>_thumbnail.png#   (+ .jpg), §53
    <output>_animatic.mp4 #   §75
  exports/                # `vidgen export` GIFs / clips (§53), `vidgen slides` decks (§55–§56)
```

`build/<final|preview|draft>[_<variant>]/` (the render folder) holds:
- `scenes/<id>.mp4` (the scene with Manim's audio), `scenes/<id>.wav` (Manim's PCM sound, only
  if the scene has sound), `scenes/<id>.overlay.mov` (RGBA overlays of frames a push / wipe moves,
  §50), `timings/<id>.json` (beat timings + render settings), `media/` (Manim's files),
  `carry/<id>.json` (objects carried into the next scene, §50).
- `padded/<id>.wav` (each scene's audio padded to its video length), `padded/video_concat.txt` /
  `audio_concat.txt` / `video_concat_<k>.txt` (runs of cut-joined scenes, §49), `padded/voice.wav`
  (scene sound summed over crossfades, §49), `padded/sfx.wav` (§47), `padded/mix.wav` (final mix,
  §48), `padded/metadata.txt` (FFMETADATA tags and chapters, §52), `timings.json` (whole video).
- `thumbnail/<name>_small.png` (§53); with `--frames`, `frames/<id>/*.png` +
  `frames/<id>/index.json` + `frames/index.json` (§13) and `layout/<id>.json` (§15).
- A sibling `build/<...>_bare/` holds overlay-free renders for a frame thumbnail (§53).

Shared across qualities and variants: `build/readback/<key>.json` (STT transcripts keyed by audio
content + STT settings, §57) and `build/imagegen/<key>-<look>.png` (placeholders, §58).

## 4. Config schema (`video.yaml`)

Pydantic v2 models in `config.py`. Every key is documented for users in docs/CONFIG.md; this
example shows the core keys and their defaults.

```yaml
title: "Saving 77% of the Parameters in LLMs"   # required
output: kphi3_video                              # basename of output files; default: folder name
format:  {width: 1920, height: 1080, fps: 30}    # final render
preview: {width: 854, height: 480, fps: 15}      # `--preview` render
variants:                                        # named overrides, deep-merged onto the config
  vertical: {format: {width: 1080, height: 1920}, preview: {width: 480, height: 854}}
theme:
  preset: light_academic                         # §19; values below still win
  background: "#0E1116"
  font: Inter                                    # sans; font_serif: Source Serif 4; font_mono: JetBrains Mono NL (§21)
  fonts: {heading: serif}                        # font roles -> sans/serif/mono or a family
  code_style: github-dark                        # Pygments style of `code` listings
  scale: auto                                    # compact/standard/large/auto (§20)
  colors:                                        # open dict; these are the defaults
    {text: "#E8EAED", dim: "#838B98", accent: "#FF6B6B", highlight: "#FFD166",
     primary: "#58C4DD", secondary: "#F2A541", tertiary: "#83C167", surface: "#161B24"}
  palette: ["#58C4DD", "#F2A541", "#C792EA", "#83C167"]   # ordered series colours
  sizes: {title: 56, subtitle: 42, heading: 36, body: 32, caption: 24, small: 20}
voice:
  provider: elevenlabs                           # or openrouter (§66) or kokoro (§68)
  voice_id: nPczCjzI2devNBz1zQrb
  model_id: eleven_multilingual_v2
  output_format: mp3_44100_128
  settings: {stability: 0.55, similarity_boost: 0.75, style: 0.0, use_speaker_boost: true}
  context: true                                  # send previous_text/next_text for continuity
narration: {pad: 0.35, words_per_second: 2.6}    # silence after each beat; estimate without audio
extensions: [extensions]                         # dirs (relative to the project) to auto-import
scenes:
  - id: intro                                    # required, unique, [A-Za-z0-9_]+
    type: title                                  # registered scene type (built-in or extension)
    params: {title: "Saving 77% of the Parameters"}   # validated by the type's Params model
    beats:
      - id: s1_b1                                # optional; default f"{scene.id}_b{n}" (1-based)
        text: "What if a large language model ..."
```

Other top-level keys and their sections: `pronunciation` (§45), `voices`, `subtitles` (§46),
`sfx` (§47), `music`, `audio` (§48), `transition` (§49–§50), `chapters`, `metadata` (§52),
`thumbnail` (§53), `language`, `translations` (§54), `stt` (§57), `imagegen` (§58, §64),
`output_dir` (below), and the later sections' keys.

Rules:
- Unknown keys are an error in every structural model (typo protection). Open dictionaries:
  `params`, `theme.colors`, `theme.sizes` and variant bodies (validated after merging).
- Scene ids unique; beat ids unique across the whole video; `type` must be registered after
  extensions load (`vidgen validate` lists the known types); `params` are validated against the
  scene class's `Params` model when it defines one.
- `theme.colors` / `sizes` / `palette` hold only what the user wrote; `Theme` merges them over the
  defaults. Colours are hex (`#RGB`, `#RRGGBB`, `#RRGGBBAA`); token names follow the id pattern.
- **Silent scenes**: a scene with no beats must set `duration: <seconds>`; `duration` on a scene
  with beats is an error (narrated scenes are timed by their audio).
- **Variants**: the variant mapping is deep-merged onto the raw config (mappings merge
  recursively; lists such as `scenes` and scalars replace), then validated. A variant may not
  contain `variants`. `vidgen validate` checks the base config and every variant.
- `output` must be a plain file name (no path separators).
- **Output folder**: the deliverables (`Project.output_path`, `srt_path`, `chapters_path`,
  `thumbnail_path`) live in `Project.output_dir`, the one property that decides it: `--output-dir
  DIR` (`Project.load(..., output_dir=)`, relative to the current directory; on `render`,
  `thumbnail`, `export`, `slides`, `animatic`) wins over `output_dir:` (relative to the project
  root or absolute; a variant may set its own), else `<root>/output`. It is not created on
  access; the render creates it before joining. `build/` and `exports/` stay under the root.
  `output_dir` is a confined path key under `vidgen mcp` (§63).
- `extensions` entries and `Project.asset(rel)` resolve relative to the project root.

## 5. Scene runtime

### 5.1 `NarratedScene` (in `scene.py`, subclass of `manim.Scene`)

`NarratedScene` subclasses `MovingCameraScene`. Constructor (injection):
`SceneClass(spec, project=None, theme=None, *, audio=True, **manim_scene_kwargs)`;
`project`/`theme` default to the runtime context (§6.3), else the theme is built from
`project.config.theme`. Constructing needs Manim's config set up; params validation does not.

Attributes inside `construct()`: `self.spec` (`SceneConfig`), `self.params` (instance of the
class's `Params` model, or a plain dict), `self.beats` (`BeatConfig`s in order), `self.theme`,
`self.project` (`self.project.asset(rel)` resolves assets), `self.pad`.

Narration:
- `with self.narrate(beat) as d:` — `beat` is a beat id or 0-based index. Adds the beat's MP3 (if
  present) at the current time, yields its duration `d` (audio length, or the word-count
  estimate), and on exit waits until `d + pad` has elapsed. Narrating a beat twice is an error;
  beats never narrated are logged as a warning at the end of the scene.
- `audio=False` (`--no-audio`) skips `add_sound` but still takes durations from the MP3s, so
  timing is identical.
- `self.beat_log: list[BeatTiming]`, `BeatTiming(beat_id, start, end, text)` (NamedTuple, seconds
  from scene start, `end = start + d`). `self.timings()` returns
  `{"scene": id, "duration": total, "beats": [{"id", "start", "end", "text"}]}`.
- Waits are frame-exact (`self.wait_seconds(t)` rounds to whole frames), so a beat lasts `d + pad`
  within half a frame.
- `self.play_log` (every `play`/`wait`: `PlayRecord(start, end, beat, animations, wait,
  requested)`), `self.beat_busy`, `self.silent_busy`: always recorded, written to the activity
  file (§17) when stills are captured.
- Also: `beat_duration(beat)`, `beat(id|index|BeatConfig)`, `beat_audio(beat) -> Path | None`,
  `narrate_all()` (`for beat, d in self.narrate_all(): ...`), `clear_all(run_time=0.6, keep=())`.
- Silent scenes are held to `spec.duration` in `tear_down()`; `self.hold(until=None)` holds
  earlier. Subclasses overriding `tear_down` must call `super().tear_down()`.

Theme-aware text: `self.text(s, size="body"|number, color="text"|"#hex"|ManimColor, weight=...,
role=...)` and `self.markup(...)`; sizes and colours accept theme token names or literal values.

Params: `Params` must subclass `SceneParams` (pydantic, `extra="forbid"`); inherited `Params`
count. Class methods `params_model()`, `validate_params(raw, theme=None)` (raises
`pydantic.ValidationError`), `parse_params(raw, scene_id, theme=None)` (raises `VidgenError`).

### 5.2 How a scene gets rendered

Each scene renders **in its own subprocess** (Manim's global config is not re-entrant):
`python -m vidgen.render.worker <project> <scene_id> --quality final|preview|draft [--variant
NAME] [--no-audio] [--progress] [--frames N] [--bare] [--source] [--guide-passes LIST]
[--intermediate lossless|compact]`, run with `PYTHONUTF8=1`. The worker:
1. `vidgen.extensions.activate(project)`: loads project + variant, builds the Theme, sets the
   runtime context, imports built-in scenes and extensions;
2. configures Manim: `pixel_width/height`, `frame_rate`, `background_color = theme.background`,
   `disable_caching=True`, `media_dir = <render_dir>/media`, `video_dir`/`partial_movie_dir`
   per scene id (parallel workers never share a folder), `text_dir = media/texts/<scene_id>` and
   `tex_dir = media/Tex/<scene_id>` (shared SVG caches let one worker read another's half-written
   file), `output_file = <scene_id>` — never guess Manim's folder naming;
3. `cls = registry.get(spec.type).cls`, `scene = cls(spec, project, theme, audio=...)`,
   `scene.render()`;
4. moves Manim's movie (and `.wav`, if any) to `scenes/<id>.mp4|.wav` and writes
   `timings/<id>.json` = `scene.timings()` (rounded to µs) plus a `"render"` block (width,
   height, fps, audio, vidgen version, …). Old files of the scene are deleted first, so a failed
   render leaves none.

Exit codes: 0 ok, 1 `VidgenError` (`error: ...` on stderr), 2 other exceptions (full traceback).

Invariants:
- **Manim caching off**: on a cache hit Manim advances its clock by the unquantized duration,
  which desynchronises `beat_log` from the frames.
- **Paths**: Manim cannot handle `'`, `{` or `}` in its paths; for such project paths its media
  folder is a temporary directory.
- **Frame size**: the worker sets `frame_width/height` (Manim does not recompute them from pixel
  sizes set in code): the **shorter side is 8 units**, square pixels (16:9 → 14.22 x 8; 9:16 →
  8 x 14.22). Scenes read `NarratedScene.frame_width`, `.frame_height`, `.is_portrait`.
- **No audio drift**: concatenated AAC segments drift (encoder priming per segment), so the
  parent pads each scene's **PCM WAV** (silence for silent scenes and `--no-audio`) to exactly
  its video length (48 kHz stereo; scene *i* gets `round(end_i*48000) - round(start_i*48000)`
  samples, so rounding never accumulates), concatenates videos (stream copy) and WAVs (PCM) with
  concat-demuxer lists, and encodes audio once (AAC 192k) in the final mux. Scene durations are
  measured from the rendered videos with PyAV (frames / fps). The MP4 is written to
  `<name>.partial.mp4` and renamed; if the target stays locked, the partial file is kept and the
  error says so.
- **Timings**: `timings.json` = `{title, variant, preview, format: {width, height, fps}, audio,
  duration, vidgen, scenes: [{id, type, start, duration, beats: [{id, start, end, text}]}]}`,
  absolute seconds. SRT cues come from it (§43; `subtitles.py`: 1-based, `HH:MM:SS,mmm`, UTF-8,
  at most 2 lines of 42 characters).
- **Scene selection** (`pipeline.scenes_to_render`): without `--scene`, a scene renders when its
  render is not current (missing, other format / audio mode / stills / guide passes, or its
  recorded fingerprint differs, §14, §63); `--force` renders all. With `--scene`, those scenes
  render, the others' existing renders are reused current or not, and any without a usable
  render render too (printing `--scene ID: also rendering N other scene(s) (...)`).
- **Failures**: without `--keep-going` the first failing scene stops the command (scene id, exit
  code, last 60 lines of worker output). With it, the rest render, failures print as they happen,
  the video is **not** joined, and the command fails listing the failed scenes.
- **Parallelism**: `render_project(..., jobs=N)` / `--jobs N` (default 1). Live Manim progress
  only for `jobs == 1` on a terminal; otherwise output is captured and `warning:` lines are
  re-printed. `--jobs auto` is resolved to a number by the CLI (§70); Python functions take an int.
- **Before rendering**: missing/stale narration (`tts.audio_status`) is a warning recommending
  `vidgen tts`; missing ffmpeg is a `VidgenError` with install hints (`winget install ffmpeg` on
  Windows).

### 5.3 Scene-building API (Step 5)

On `NarratedScene`, shared by built-ins and extensions:
- `validate_params` / `parse_params` pass the theme to validators as `info.context["theme"]`.
- `ThemeColor` (`Annotated[str, ...]`) and `ThemeSize` (`Annotated[str | float, ...]`) for
  `Params` fields: hex syntax always checked, token names when a theme is given. Both carry a
  `ThemeToken(kind)` marker; `list-scenes` prints them as `color` / `size`.
- Class method `validate_project(params, project) -> list[str]`: project-aware checks run by
  `vidgen validate` after params validate; each message is reported as
  `scenes[i].params.<message>` (start it with the param name). Default `[]`.
- `beat_count: int | tuple[int, int | None] | None = None`: beats a type narrates (`None` any,
  `2` exactly, `(1, None)` at least one, `(2, 4)` a range). `check_beat_count(n) -> str | None`
  (`"needs exactly 2 beats, got 3"`) and `beat_count_text()`. `validate` reports
  `scenes[i].beats: type 'x' needs ...`; the constructor raises `VidgenError("scene 'id': needs
  ...")`. Built-ins leave it `None`.
- `outro: float = 0.0` and `finish()` (fade out everything over `outro`; holds instead when a
  transition follows, keeps carried targets, §49–§50).
- `timeline()`: yields `(index, d)` per narrated beat; a silent scene yields one
  `(0, duration - outro)` step and then holds.
- `play_steps(d, steps, fraction=0.7, cap=1.2)`: spreads steps (animation | list | callable
  returning either) over `d` seconds, each run for `min(cap, fraction * slot)`, never longer than
  `d` (consecutive steps merge if `d` has fewer frames than steps).
- `reveal(steps, fraction, cap)` = `distribute(len(steps), len(beats))` + `timeline()` +
  `play_steps()` per beat.
- `safe_width` / `safe_height`, from `self.safe_area` (frame minus `margin_x = 0.6`,
  `margin_y = 0.5` units, §18).

`vidgen.layout` (exported): `fit_text`, `measure_text`, `shrink_to_fit`, `wrap_lines`,
`normalize_text`, `distribute`, `nice_ticks`, `auto_format`, `format_value`, `check_format`,
`latex_available`, `require_latex`. `fit_text` measures each word once (cached per font/weight),
searches the font size arithmetically and builds the `Paragraph` once; `line_spacing` defaults
to 0.7. Highlights use `t2c` index ranges (wrapping only turns spaces into line breaks, so indices
into the normalized text stay valid).

## 6. Extension system (the core requirement)

### 6.1 Discovery
For each directory in `extensions` (default `extensions/`): every `*.py` file and every
sub-package (a folder with `__init__.py`) is imported, in sorted order, under one private
package `vidgen_ext_<project folder name, lower-cased, non-word characters → _>`, so extension
modules import each other relatively (`from .common import column`). Names starting with `_` or
`.` are skipped. Several directories share the one synthetic package (its `__path__` lists them
all); the same module name in two directories is an error. The default `extensions/` may be
absent; a directory written explicitly must exist. The project directory is **not** put on
`sys.path`. The package is removed from `sys.modules` before each load. An exception while
importing becomes a `VidgenError` with the file (relative to the project) and the traceback
(importlib frames removed); a `VidgenError` raised during import propagates unchanged.

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
register_theme_preset("acme", base="light_academic", colors={"primary": "#0B5FFF"})
```
- **Scene types**: `@scene(name, *, override=False)`; also `@action` (beat actions, §26),
  `@overlay` (§41), `register_model` (plot models, §97.7). A name colliding with another
  extension is an error. Colliding with a built-in raises unless `override=True`, which replaces
  it and logs a warning on logger `vidgen.registry` (`override=True` with no such built-in also
  warns); `vidgen list-scenes` marks it overridden. The CLI prints vidgen log warnings as
  `warning: <message>` on stderr.
- **Origin**: built-in vs extension is decided by the defining module: inside the `vidgen`
  package is `builtin`, anything else shows as its file relative to the project root.
- **Helpers**: plain Python modules inside `extensions/`, shared via relative imports.
- **Theme tokens**: `register_theme_defaults(colors=None, sizes=None)`; `theme.color("k2")`,
  `theme.size("body")`. `register_theme_preset(name, base=..., colors=..., scale=..., fonts=...)`
  (§19–§20).
- **Hooks**: `@hook(event)`; an unknown or missing event is a `VidgenError`. Built-in hooks run
  before extension hooks, each group in registration order. `hooks.dispatch(event, project,
  **data)` returns the `HookContext` (hooks may modify `ctx.data`). A failing hook aborts the
  command: `hook <module.qualname> (<origin>) failed during <event>: ...` + traceback (a
  `VidgenError` keeps just its message).
- **Hook data** (render hooks run in the parent `vidgen render` process):
  - `pre_tts`: `beats` (ids about to be generated, video order; hooks may remove ids to skip
    them or add known ids), `audio_dir`, `force`, `dry_run`; dispatched on dry runs too.
  - `post_tts`: `generated` (ids written, in order), `audio_dir`; not on dry runs or failure.
  - `pre_render`: `scenes` (ids about to render, config order; removing one reuses its existing
    render), `preview`, `variant`, `no_audio`, `render_dir`.
  - `post_scene`: once per scene rendered in this run (not reused ones): `scene_id`, `video`
    (`scenes/<id>.mp4`, before padding), `timings` (the scene's timings), `preview`, `variant`,
    `frames` (its stills folder or `None`).
  - `post_render`: after MP4, SRT, `timings.json` and the thumbnail are written: `output`, `srt`,
    `timings` (combined), `timings_file`, `preview`, `variant`, `frames_index` (or `None`),
    `chapters`, `thumbnail`. Not dispatched when the command fails.
  - The API key is never part of hook data.
- **Promotion**: an extension module copied into `src/vidgen/scenes/` works unchanged, because
  built-ins use exactly the same API. Built-in scene modules import vidgen only through
  `from vidgen.api import *` (a test pins this) and share code by relative imports.

### 6.3 Runtime context
`vidgen.runtime` holds the active Project and Theme. It is set **before** extensions are
imported, so module-level extension code may read theme values
(`C_BASE = current_theme().color("primary")`). `api.T(...)` / `api.MT(...)` are function forms of
`self.text` / `self.markup` using the current theme.

### 6.4 `vidgen.api` exports (stable surface)
`from vidgen.api import *` gives every name of `from manim import *` plus `vidgen.api.VIDGEN_NAMES`
(the authoritative list, about 1,200 names; `__all__` is their sorted union). The only collision
with manim is `scene` (manim's subpackage, shadowed by the decorator); `SHADOWED_MANIM_NAMES`
records it and a test pins it. Anything not exported is internal and may change. Groups:
- **Core**: `NarratedScene`, `SceneParams`, `scene`, `find_scene_type`, `hook`, `HookContext`,
  `register_theme_defaults`, `register_theme_preset`, `current_theme`, `current_project`, `T`,
  `MT`, `VidgenError`, `resolve_color`, `ThemeColor`, `ThemeSize`, `IconName`, `one_or_many`,
  pydantic's `Field`, `field_validator`, `model_validator`; helpers `column`, `edges`,
  `dense_pairs`, `grouped_pairs`, `sparse_pairs`, `group_bounds`, `counter`, `fade_out`, `Fade`.
- **Layout** (§5.3, §18, §24–§25): the `vidgen.layout` helpers; `Region`, `frame_region`,
  `safe_area`, `region`, `grid`, `grid_shape`, `place`, `orientation`, `readable_size`,
  `readable_text`; `role=` keywords on the text helpers; `SceneParams.also_accepts`,
  `text_shorthand`, `text_defaults`.
- **Actions and targets** (§26–§27, §44): `action`, `Action`, `ActionOptions`, `Target`,
  `ActionConfig`; on `NarratedScene` the target API (`target()`, `targets`, `find_targets()`,
  `on_screen_parts()`, `is_shown()`, `entrance()`, …).
- **Drawing families**: graphs (§31: `layered_layout`, `GraphLayout`, …), charts (§33–§34:
  `ChartAxes`, `chart_axes`, `ColorScale`, `color_bar`, `text_color_on`, …), callouts (§37),
  clips (§38), maps (§39), icons (§22: `icon`, `Icon`), vectors (§65: `load_vector`,
  `VectorPicture`), geometry marks and maths expressions (§87.6–§87.7), terms (§87.3), word
  anchors (§87.2).
- **Overlays, chapters, captions** (§41–§43): `overlay`, `Overlay`, `OverlayOptions`,
  `OverlayContext`, `with_opacity`, `video_chapters`, `Chapter`, `CaptionCue`, `caption_cues`,
  `segment_cues`, word timing (`WordTime`, `beat_word_times`, …); HUD (§102.5).
- **Speech and sound**: `Pronunciation`, `Spoken` (§45), speakers (§46), `SfxEvent`,
  `SoundLibrary`, `sound_library`, `synthesize` (§47), stings (§69.46), voice effects (§100.2),
  translation and languages (§54: `TranslatableStr`, `TextRef`, `LanguageRules`), score files
  from `vidgen.studio` (§93: `MusicScore`, `load_music_score`, `render_music_score`,
  `check_music_score`, …).
- **Continuity and cuts**: `carry_move` (§50), `apply_cut` (§101).
- **Generated media**: `GenerateImage`, `generated_image` (§58); `VideoRequest`, `MediaInput`,
  `generate_clip`, `plan_clip`, `plan_shots`, `project_shots`, `project_sheets`,
  `scene_placements`, `check_clip`, `run_shots` (§113).
- **Cartoons, 3D and web** (§69–§71, §79, §86, §89–§90, §100–§109, §114, §118–§123): the public
  names and constants of the character, motion, acting, stage, prop, light, weather, effect,
  vehicle, iso and level modules (`Character`, `character`, `PART_NAMES`, `PoseChange`, `Walk`,
  `Gesture`, `Jump`, `KeyedMotion`, …), of `three_d` and of the `web` data inputs.
- **Science modules** exported whole: `plotcore`, `plot_draw` (§97), `quantities` (§97.9),
  `orbits` (§98), `flight` (§123.7), `particle_physics` (§99), `genetics` (§96), plus the
  `cellworld` / `cell_draw` names (§95) and `register_model`.

### 6.5 Refinements (Step 2)
- **Isolation** (several projects/variants in one process): built-in registrations are permanent
  (their modules stay imported); extension scene types and hooks form a per-project layer.
  `registry.reset()/snapshot()/restore()/isolated()` and the same four in `hooks`;
  `runtime.set_context()/clear_context()/use_context()`; `extensions.activate(project)`
  (process-wide: context + reset + load, returns the Theme) and
  `extensions.project_session(project)` (context manager: everything restored on exit, the
  synthetic package unloaded). Every `activate` builds a fresh Theme, so theme defaults
  registered by one project never leak into another.
- **Validation** (`vidgen validate`): unknown types → `scenes[i].type: unknown scene type 'x';
  did you mean 'y'? (known types: ...)`; params errors → `scenes[i].params.<field>: <message>`.
  Variant problems are prefixed `[variant NAME]`; problems identical to the base config's are
  not repeated.
- **`vidgen list-scenes [PROJECT]`** prints `name  origin  [(overrides builtin)]`, one indented
  line per `Params` field (`name: type [= default]`) or `params: free-form`, and `beats: ...`
  when `beat_count` is set. Without PROJECT and no config in the current directory it lists the
  built-ins only.
- **Built-in library**: `vidgen/scenes/__init__.py` imports each scene module explicitly; the
  user reference is docs/CONFIG.md "Built-in scenes".

## 7. TTS (ElevenLabs)

This section specifies the provider seam, the audio cache and the ElevenLabs provider; OpenRouter
is §66, Kokoro §68, emotions §72–§73, voice effects §100.2.

- **Provider seam** (`vidgen.tts`): `get_provider(voice, emotion=None) -> TTSProvider` picks by
  `voice.provider` (`elevenlabs`, `openrouter`, `kokoro`) and wraps it in `EffectProvider` when
  the voice has an effect. `TTSProvider`: `name`, `cache_key(text)`, `matches(text, stored)`,
  `check_credentials()`, `synthesize(text, previous_text=None, next_text=None) -> bytes`.
  Constructing a provider never needs a key.
- **API key**: read only from `ELEVENLABS_API_KEY`, from the environment on every request
  (stripped), never kept on the object. vidgen never stores it: it is not a config field and is
  never written to video.yaml, audio/, build/, logs, error messages, hook data or git; it is sent
  only as the `xi-api-key` header to api.elevenlabs.io. Only `vidgen tts` (not `--dry-run`) needs
  it, and only when at least one beat must be synthesised; a missing key is a `VidgenError` with
  setup instructions.
- **Request**: `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=...`,
  standard library only (urllib, via `httpapi.py`). JSON body `{text, model_id, voice_settings}`
  plus `previous_text`/`next_text` (neighbouring beats in video order, across scenes, omitted at
  the ends) only when `voice.context` is true. Timeout 120 s. Transient failures (HTTP
  429/500/502/503/504, timeouts, dropped connections) are retried 3 times with backoff 2, 4, 8 s
  (or `Retry-After`, capped at 30 s). Errors become `VidgenError`: `ElevenLabs returned HTTP
  <code>: <body, max 500 chars>` or `cannot reach ElevenLabs: ...`, with any occurrence of the
  key replaced by `***`. The CLI prefixes `beat '<id>': ` and says how many beats were done.
- **Cache key** (stored as `audio/<beat_id>.hash`): `sha1("|".join([voice_id, model_id,
  output_format, json.dumps(settings, sort_keys=True), text]).encode("utf-8"))`, `settings` =
  `voice.settings.model_dump()` (default separators); when a language code is sent,
  `language_code=<code>` goes before the text (§54). `voice.context` and the neighbouring texts
  are **not** hashed, so editing one beat regenerates only that beat.
- **kphi3 hashes** (`sha1(voice_id + model_id + text)`) also count as up to date when
  `output_format == mp3_44100_128`, settings equal the defaults and no language code is sent.
  They are never rewritten (no git noise for the committed kphi3 audio); a regeneration writes a
  current-format hash.
- **Writes**: MP3 via temp file + `os.replace` in the same folder, then the hash the same way, so a
  hash never vouches for a partial MP3. Beats already generated are kept on failure.
- **`vidgen tts`**: `--beat` restricts the selection (unknown id → error), but up-to-date beats
  are skipped unless `--force`. Output: `[n/N] generated <id>.mp3 (<chars> chars)` per beat and a
  summary; dry run prints `would generate ...` lines and `dry run: N beat(s) to generate, C
  characters; U up to date`. The character count is what is billed (beat text only).
- **Variant audio**: a variant uses `audio/<variant>/` when its effective `voice` differs from the
  base config's or a beat id in both configs has a different text; otherwise it shares `audio/`
  (`Project.audio_dir`, `has_own_audio`, `base_config`). Generating into a variant folder copies
  beats whose `audio/` file is up to date for the variant's voice and text.
- **Orphans**: MP3s whose id no config sharing the folder uses (base + variants) are listed,
  never deleted; subfolders are ignored.
- **Audio status** (no key): `vidgen.tts.audio_status(project) -> list[BeatAudioStatus]`
  (`scene_id, beat_id, text, state, mp3, hash_file`; state `ok` | `stale` | `missing`; stale =
  MP3 exists but its hash is missing or does not match), `format_audio_summary(statuses)` →
  `"18 ok, 2 stale, 1 missing"`, `orphaned_audio(project)`. `vidgen validate` prints
  `audio:     <summary>` (+ `(N orphaned mp3)`) and one `audio [<variant>]: ...` line per variant
  with its own folder; `render` warns, never fails, on stale/missing audio.
- Tests mock `urllib.request.urlopen`; no network.

## 8. CLI

Commands (`vidgen <command> --help` and the README.md "Commands" table give every flag):
- Authoring: `init`, `plan` (§61), `screenplay` (§69.25), `story` (§105.5), `shorts` (§105.6),
  `cast` (§69.49), `guide` (§59), `mcp` (§62), `schema` (§12).
- Checking and listing: `validate`, `list-scenes`, `list-themes` (§20), `list-icons` (§22),
  `list-sfx` (§47), `list-pronunciation` (§88), `list-music` (§48, §83), `lint` (§16), `motion`
  (§121.3), `audio` (§111.2), `readback` (§57), `parts` (§122.5), `direct` (§69.24).
- Media generation: `tts` (§7), `imagegen` (§58), `generate` (§113), `split-sheet` (§113.16),
  `music` / `studio` / `soundfont` (§81–§94), `cache` (§123.2), `translate-template` (§54).
- Rendering and outputs: `render`, `storyboard` (§14), `animatic` (§75), `still` (§120.3),
  `thumbnail`, `export` (§53), `slides` (§55–§56), `gallery` (§60), `character`,
  `character-sheet` (§69.1, §69.16), `space-page` (§122.12), `remote` (§113.20).

Rules:
- PROJECT defaults to the current directory; the exit code is non-zero on error; a
  `VidgenError` prints as `error: ...` without a traceback; `--json` prints the §11 documents.
- `render` renders the scenes whose render is not current (§5.2; `--force`: all) and joins the
  video; it prints one line per scene, then the output paths, the total duration and the
  measured loudness (§48).
- Every command with `--jobs` accepts `auto`, which first prints `jobs: N (auto: <reason>)` (§70).

## 9. Testing

- No network, no API keys: paid APIs are mocked.
- Tests that invoke Manim rendering are marked `@pytest.mark.render` and use tiny resolutions
  (e.g. 160x90 @ 5 fps); `-m "not render"` skips them.
- A test over about 0.4 s is marked `slow`; `tests/conftest.py` leaves slow tests out of the
  default run (about 3–4 minutes on one CPU). `-m slow` runs only those, `-m "slow or not slow"`
  everything, and a test named by node id always runs.
- ffmpeg is required on PATH for render tests; they skip with a clear reason if it is missing.
## 10. Refinements (Step 7, independent review)

- **Audio length** (`scene.audio_duration`) = decoded samples / sample rate, not the container
  duration (PyAV versions differ on MP3 encoder padding).
- **Dependencies**: `manim>=0.19`; vidgen wraps `renderer.add_frame(frame, num_frames)`.
- **Config**: `format`/`preview` `width`/`height` must be even (Manim's H.264 writer crashes on
  odd sizes); a UTF-8 BOM and CRLF are accepted.
- **Windows files** (`vidgen.fileio`): outputs that may be open elsewhere (final MP4, kept as
  `<name>.partial.mp4` until moved; SRT; timings; TTS MP3/hash) are written to a temp file and
  moved with `replace_file` (retries ~1.5 s, then `VidgenError("cannot write X ...; is it open in
  another program...")`); deletes use `remove_file`. The CLI sets `errors="backslashreplace"` on
  stdout/stderr; a closed pipe ends quietly.
- **Workers** get the environment without `ELEVENLABS_API_KEY`.
- **Extensions**: `beat_count` checked at registration and before `render` starts workers; a
  failing `validate_project` is reported as `scenes[i]: validate_project of scene type 'x'
  (<file>) failed: ...` and the other scenes are still checked; bare `@scene`/`@hook` raise a
  message showing the right form.
- **`vidgen init`** creates `assets/`, `extensions/`, `.gitignore` (stored as `gitignore` because
  setuptools does not package dot files).

## 11. Refinements (Step 8, JSON output)

- **`--json`** (`cli.JSON_COMMANDS`): stdout holds exactly one document (`jsonout.dumps`,
  indented, ASCII); other output goes to stderr; log warnings also go into `warnings`. Exit 0 iff
  `ok`, 1 error, 2 usage. Shapes: docs/CONFIG.md "JSON output". `jsonout.SCHEMA_VERSION` (1):
  keys may be added within a version; removing/renaming a key or changing a type bumps it.
  `error.kind`: `usage`, `error` (`VidgenError`), `internal` (`details.traceback`).
- **Problems**: `errors.Problem(location, message, variant=None, file=None)` and
  `VidgenError(message, *, problems=(), details=None)`; `config.validation_problems(err,
  prefix)`; `cli.project_problems(project) -> list[Problem]`. A `validate_project` message
  `"<param>: <text>"` is located at `scenes[i].params.<param>`, others at `scenes[i].params`.
  `cli.validate_all(project, keep_going=False)`: with `--json` every variant is checked.
- **Render**: `RenderResult.timings`, `render_seconds`, `warnings`; failures raise
  `VidgenError(..., details={"failed": [{scene, exit_code, output_tail}], "rendered": [ids]})`.
- **Param docs**: `SceneParams` uses `use_attribute_docstrings=True` (`pydantic>=2.7`); every
  built-in param has a docstring. A type's doc is its class docstring, else its module's. Helpers:
  `vidgen/describe.py`.
- **Usage errors**: the parser raises `cli.UsageError`; `main` returns 2 (no `SystemExit`).

## 12. Refinements (Step 9, JSON Schema export)

- **`vidgen schema`** (`vidgen/schema.py`: `config_schema(entries, themes)`, `params_schema`,
  `scene_schema`; user reference docs/CONFIG.md "JSON Schema"): Draft 2020-12 from the pydantic
  models (validation mode), post-processed. With a config that fails to load,
  `schema.lenient_project` keeps its valid `extensions` and `theme` and warns.
- **Encoded**: per-type `if {type: const NAME} then {params: $ref #/$defs/scene.NAME}` (nested
  models `scene.NAME.Model`, `beats` counts from `beat_count`), the silent-scene rule, `variants`
  bodies, `dict[Identifier, X]` as `propertyNames`. `ThemeToken` adds `"x-vidgen-theme":
  "color"|"size"|"icon"`, exported as an `anyOf` with an `enum` of the token names of the active
  and every variant's theme (`schema.project_themes`). Every config field has a one-line
  docstring.
- **Only `vidgen validate` checks** unique ids, referenced files, `validate_project` and Python
  validators; coerced values (`"30"` for an int) pass validate but not the schema.

## 13. Refinements (Step 10, frame capture)

- **Option**: `render --frames` / `--frames-per-beat N`; `render_project(..., frames=N)` (0 = off);
  worker `--frames N`. Files and index format: docs/CONFIG.md "Frame stills".
- **Mechanism** (`vidgen.capture`): `FrameCapture(per_beat, listeners, motion=None)`, passed as
  `NarratedScene(..., capture=None)`, wraps `scene.renderer.add_frame` and counts frames written,
  so a still's `frame` is its index in the scene video. It only reads the array: frames,
  `renderer.time` and the beat log must stay identical to a render without capture. `narrate()`
  calls `begin_segment(beat_id, round((d + pad) * fps), include_end=False)` / `end_segment`:
  still `k < N` is the last frame before `k/N` of the beat, still `N` its last frame; a silent
  scene is one segment (`beat_id = None`); `tear_down` calls `finish()`. Taken from the renderer,
  not by decoding the MP4: exact pixels on every Manim/PyAV version, and listeners see the live
  scene.
- **Listeners**: `CaptureListener = Callable[[NarratedScene, CapturedFrame], None]`, called when
  the frame is written; `CapturedFrame(scene_id, beat_id, k, n, frame, time, pixels)`.
  `StillWriter(folder)` writes `<beat>-<k>.png` (`<scene>-<k>.png` when silent) and `index.json`.
- **Files and staleness**: `worker.scene_frames_dir` = `<render_dir>/frames/<scene>/`;
  `pipeline.write_frames_index` writes `frames/index.json` after joining; timings record
  `render.frames`. The worker deletes the scene's stills before rendering and `render_project`
  deletes `frames/index.json`; with frames requested `_usable_render` needs equal `render.frames`
  and the index. `RenderResult.frames_index`.

## 14. Refinements (Step 11, storyboard)

- **`vidgen storyboard`** (`vidgen/storyboard.py`, `make_storyboard(project, *, preview=True,
  scenes=None, per_beat=1, width=1280, jobs=1, force=False) -> StoryboardResult`; options, JSON:
  docs/CONFIG.md "Storyboard"): `<render_dir>/storyboard/video-<p>.png` and
  `storyboard/scenes/<scene>-<p>.png`; its folder (or those pages) is cleared first.
- **Reuse**: `storyboard.stills_current(project, preview, scene_id, per_beat)` checks timings
  (format, `render.frames`, `render.fingerprint`), the stills, the layout file (§15) and the
  activity file (§17); `per_beat=None` accepts any count. Other scenes are rendered by
  `pipeline.render_scenes(project, preview, ids, jobs, frames)` (the render workers with audio and
  `post_scene`; no `pre_render`/`post_render`, no join).
- **Fingerprint** (`vidgen/render/fingerprint.py`, `scene_fingerprint(project, scene_id)`):
  SHA-256 over the scene entry (without `lint_ignore`, `chapter`), the config minus
  `scenes`/`variants`/`lint` (variant applied; plus `lint.rules.min_font.min_size` as `readable`,
  §18), beat MP3 size+mtime, contents of extension `.py` files, size+mtime of files under
  `<root>/assets`, the vidgen version and `vidgen_source_digest` (vidgen's source and bundled
  data such as fonts and icons, except `NOT_RENDER_INPUTS`: modules that cannot change pixels or
  timing, e.g. CLI, JSON, schema, sheets, storyboard, pipeline, ffmpeg, subtitles, tts, lint; new
  modules count by default). Stored as `render.fingerprint`; none = stale. `vidgen render` uses it
  (§63).
- **Sheets** (`vidgen/sheets.py`, `compose_pages(...) -> list[SheetPage]`): default 1280 px wide
  (640–2000) because agents' image tools downsize to ~1568 px and the labels must stay readable.

## 15. Refinements (Step 12, layout introspection)

- **What**: whenever stills are captured, `vidgen.introspect.LayoutRecorder` (a second capture
  listener) writes `<render_dir>/layout/<scene>.json` (`worker.scene_layout_path`) for the same
  frames; no flag, so stills and layout always come from one render. Format (`LAYOUT_VERSION =
  1`, additive keys only): docs/CONFIG.md "Layout dump". Deleted before each render;
  `introspect.py` counts in the fingerprint.
- **Measuring**: points via the camera's `points_to_subpixel_coords` (zoom honoured); curves
  sampled at 5 parameters per cubic; strokes widen boxes by half their width; objects without a
  visible leaf are omitted. Text mobjects (`Text`, `MarkupText`, `Paragraph`,
  `SingleStringMathTex`, `DecimalNumber`) are one object; `Code` paragraphs are kind `code`; a
  group without text/image is one `group`. `id` = `m<N>` per Python object (kept alive so `id()`
  is not reused); `path` = `Class[index]` chain or a scene attribute / `Mobject.name`. `font_px`
  = 75th percentile of glyph heights; `backdrop` = most common colour in the text box excluding
  the text's colours; `order` = draw order.
- **Limits**: `text` is the build string (kept by `Transform`; scenes that count set
  `original_text`); Cairo draws moving mobjects over static ones regardless of z-index.

## 16. Refinements (Step 13, `vidgen lint` layout rules)

- **Command**: `vidgen lint` (`vidgen.lint.lint_project(project, *, preview=True, scenes=None,
  rules=None, fail_on=None, jobs=1, force=False) -> LintResult`; options, rules, thresholds, JSON:
  docs/CONFIG.md "Lint"). Exit 1 iff a finding is at least as severe as `fail_on` (default
  `error`).
- **Input**: layout dumps of **beat-end stills** (`k == n`) only; missing ones rendered one per
  beat. Objects below `lint.min_opacity` (0.1) dropped. Sizes are fractions of the frame's
  **shorter side**, so 9:16 is judged like landscape.
- **Framework** (`vidgen/lint/rules.py`): `@rule(name, scope="still", default=severity)`
  registers `check(context, settings) -> Iterable[Issue]` in `RULES`; `name` must be in
  `config.LINT_RULES` (same order) with one `RuleConfig` model in `config.LintRules`; a test
  keeps the three in sync. `Issue(message, bbox, objects=(), severity=None, value=None,
  limit=None, group=None)`; scope `still` gets `StillContext(layout, frame, objects, still)`.
  Severity: configured, else the issue's own, else the rule default; `off` skips. Findings merge
  across beats (same rule/severity/objects) and within a still (same `group` or object `text`).
- **Config**: `VideoConfig.lint: LintConfig` (`fail_on`, `min_opacity`, `rules`);
  `SceneConfig.lint_ignore: list[RuleName | "all" | LintIgnore(rule, object, beat)]` (`object`
  matches name/path/text/icon name with `*`/`?` only). Both are outside the fingerprint.

## 17. Refinements (Step 14, timing lint)

- **Rules** (`vidgen/lint/timing_rules.py`, scope `scene`): `narration_speed`, `dead_air`,
  `animation_overrun`, `rushed_animation`, `talked_over` (§69.34); thresholds: docs/CONFIG.md
  "Lint". They get `SceneContext(scene_id, activity, audio_dir)` and yield issues with `beat`
  and `time`; `run._timing_findings` turns them into findings (`still` may be `None`).
- **Activity file** (`vidgen/activity.py`, `ACTIVITY_VERSION = 1`, `worker.scene_activity_path` =
  `<render_dir>/activity/<scene>.json`; format: docs/CONFIG.md "Activity file"): written with the
  stills, deleted before each render, required for reuse.
- **Play log**: `NarratedScene.play` appends a `PlayRecord` (waits recorded `wait: true`);
  `narrate()` stores `beat_busy[id]`; `play_steps` marks shortened plays with `requested`.
  Recording never changes frames or timing.
- **Motion** (`MotionTrack`, fed by `FrameCapture._observe`): each written frame is sampled every
  `ceil(short side / 180)` px and compared with the previous; only changes are stored. From the
  renderer because its static frames are bit-identical (codec noise would need a fuzzy threshold).
- **Logic**: `narration_speed` counts `timing_rules.spoken_words` per second of speech
  (`speech_bounds` trims silence below -40 dB; without audio, findings are `info`).
  `animation_overrun`: `busy - (d + pad) > tolerance`. `rushed_animation` sees only plays
  `play_steps` shortened.

## 18. Refinements (Step 15, layout regions)

- **Module** `vidgen/regions.py`, exported by `vidgen.api`; user reference docs/EXTENDING.md
  "Layout regions" (region names and shares, `place`, `readable_text`). `Region(x0, y0, x1, y1)`
  (frozen, Manim units, y up; negative size → `VidgenError`) with `rows`, `columns`, `split`
  (rows when the active frame is portrait), `grid`, `inset`, `below`/`above`. `GAP = 0.3`.
- **Safe area**: `safe_area(margin_x=MARGIN_X, margin_y=MARGIN_Y)` (0.6 / 0.5) is the single
  source for `NarratedScene.safe_area` and the layout dump's `safe_area`.
- **Orientation** (`scales.frame_orientation`): `landscape` if w > 1.2 h, `portrait` if h > 1.2 w,
  else `square`. Unknown region names, fits or alignments → `VidgenError`.
- **`readable_size(font=None, *, fraction=None, margin=1.05)`**: font size whose `H` is `fraction`
  of the shorter side; `fraction` defaults to `min_text_fraction()` = the project's
  `lint.rules.min_font.min_size` (`MIN_TEXT_FRACTION = 0.025`), so layout and lint share the
  threshold, which is therefore in the fingerprint (key `readable`).
  `readable_text(text, area, *, size="body", min_size=None, theme=None, **fit_text_kwargs)` wraps
  rather than shrinking below that floor and logs a warning on `vidgen.regions` when it must
  scale; built on internal `layout.fit_text_sized`.
- **`code` wrapping** (`wrap: bool = True`): `lex_code` lexes the whole text with Pygments into
  runs and `wrap_runs(rows, columns)` breaks them (never below `MIN_COLUMNS` 20); Manim's `Code`
  gets the wrapped text as `language="text"` and `paint_code` colours glyphs from the runs,
  because lexing each wrapped piece separately breaks strings and comments. Only original lines
  are numbered.

## 19. Refinements (Step 16, theme presets)

- **Config**: `ThemeConfig.preset`, `code_style` (installed Pygments style); `background`/`font`
  default `None` (= not written) so a preset can supply them. User reference: docs/CONFIG.md
  "Theme presets".
- **Precedence** (`Theme` in `theme.py`): `video.yaml` `theme.*` > preset chain (`preset_chain()`:
  preset, then its `base`, recursively) > `register_theme_defaults` > built-in defaults (the
  `dark_tech` values). `colors`/`sizes` merge per token; `background`, `font`, `code_style`,
  `palette` take the highest layer that sets them. A preset beats code defaults because it is an
  explicit config choice, but never a written config value.
- **Presets** (`vidgen/presets.py`, frozen `ThemePreset`; `None`/empty = unset; `DEFAULT_*`
  constants, re-exported by `vidgen.theme`): `BUILTIN_PRESETS` = `dark_tech`, `light_academic`,
  `high_contrast`, `warm_editorial`, `brand_neutral`, `soft_pastel`, `bold_neon`, built via
  `make_preset` (validated at import); values in docs/CONFIG.md (a test keeps the table in sync).
- **Project presets**: `vidgen.api.register_theme_preset(name, *, base, background, font, colors,
  palette, sizes, code_style, description, scale, fonts, font_serif, font_mono)` → `make_preset` →
  `Theme.add_preset` (error on a built-in name, duplicate, unknown `base`); per project, on the
  active `Theme`. Unknown preset → `VidgenError("unknown theme preset ...; known presets: ...")`;
  `vidgen validate` reports it as `theme.preset: ...` and skips the scene checks.
  `Theme.derive(config, fmt=None)` builds a variant's theme sharing registered defaults and presets.
- **Contrast** (`vidgen/lint/color.py`): `theme_contrast(theme, *, text_ratio=4.5,
  graphic_ratio=3.0) -> list[ContrastCheck]`: `text`/`dim` on background and `surface` 4.5:1;
  accents and palette 3:1. Tests run it on every built-in preset. `vidgen validate` and `vidgen
  lint` log failures as `warning: theme contrast: ...`, never failures. No built-in hard-codes
  white or black; `code` `style` defaults to `theme.code_style`.

## 20. Refinements (Step 17, more presets and type scales)

- **Type scales** (`vidgen/scales.py`, manim-free): `TYPE_SCALES` `compact`, `standard` (=
  `DEFAULT_SIZES`), `large`; `auto` = `AUTO_SCALES[orientation]` (`large` portrait, else
  `standard`); none goes below `small` 20. `ThemeConfig.scale` / preset `scale`.
- **Orientation**: `Theme.for_format(config, fmt)` is used with the project's **final** `format`,
  so preview and final share sizes.
- **Size precedence**: base, registered extension sizes, each preset in the chain (lowest first)
  its scale then its `sizes`, the config's scale, the config's `sizes`. Base = `DEFAULT_SIZES`
  when any level chooses a scale, else the `auto` scale for the orientation.
- **Palettes**: 4–6 colours, each ≥ 4.5:1 on its background (charts draw labels in them).
  `lint.color.palette_distinctness(palette) -> {vision: min CIEDE2000}` for normal and simulated
  protanopia/deuteranopia/tritanopia; built-in presets except `dark_tech` reach ≥ 7.5 (tested);
  `dark_tech` keeps the default palette so default output does not change.
- **`vidgen list-themes`** (`themelist.py`, not a render input; JSON in docs/CONFIG.md
  "`vidgen list-themes`"); `--swatches`/`--sheet` PNG.

## 21. Refinements (Step 18, bundled fonts)

- **Bundled** (`src/vidgen/data/fonts/<Family>/` with `OFL.txt`; `THIRD_PARTY_NOTICES.md`):
  `Inter`, `Source Serif 4`, `JetBrains Mono NL` (no ligatures, so code shows the typed
  characters); unmodified.
- **Registration** (`fonts.register_bundled_fonts()`): `manimpango.register_font` per file, once
  per process, then clears Manim's `Text.font_list`. Pango reads fonts when it lays out the first
  text, so registration must come first: `vidgen.helpers` and `vidgen.regions` call it at import,
  the worker first in `render_scene`. A failure is a warning, never an error.
- **Tokens**: `font` (sans, Inter), `font_serif`, `font_mono`; `theme.fonts: {role:
  token-or-family}`.
- **Roles** (`Theme.font_for(role)`): config `fonts[role]` > preset chain `fonts[role]` >
  `fonts.ROLE_DEFAULTS` (`code` → `mono`, `quote_mark` → `serif`) > `sans`; `sans`/`serif`/`mono`
  (`fonts.FONT_TOKENS`) name the tokens. A config `font` is the sans family only and does not
  override roles (else `font: Inter` would cancel a preset's serif headings and mono code).
  Built-ins use `heading` for titles/headings, `quote`, `quote_mark`, `code`; other text `body`.

## 22. Refinements (Step 19, icons: mechanism + seed set)

- **Vendored set** (`src/vidgen/data/icons/`): `lucide/<name>.svg` (unmodified `lucide-static`),
  `lucide/LICENSE`, `manifest.json` (`{version: 1, sources, icons: [{name, category, tags,
  aliases, source}]}`, sorted). `icons.CATEGORIES`: `tech, data, science, business, people, ui,
  nature, education`. List: `tools/icon_set.json`; `tools/vendor_icons.py` (not shipped)
  re-creates the folder (§23).
- **Registry** (`vidgen/icons.py`, manim-free): `IconInfo`, `builtin_icons()`,
  `project_icons(root)` (`<root>/assets/icons/*.svg`, names `[A-Za-z0-9][A-Za-z0-9_-]*`, optional
  `icons.json`, category default `project`), `available_icons(root=None)` (project icons replace
  built-ins by name), `active_icons()`, `search_icons(icons, text, category)` (ranking §25),
  `find_icon(name)`, `unknown_icon_message`. Project icon problems are `VidgenError`s, reported as
  `assets/icons: ...`.
- **Mobject** (`vidgen/icon_mobject.py`): `icon(name, size="body", color="text",
  stroke_width=None, *, height=None, theme=None) -> Icon`, `build_icon`. The SVG is pre-processed
  into a per-process temp folder (Manim's `SVGMobject` writes `<stem>_.svg` beside its input:
  races between workers, fails read-only): an invisible `<rect>` over the `viewBox` becomes the
  `Icon`'s layout `box` (submobject 0), `currentColor` a marker colour, `stroke="none"` zero
  width; strokes scale with the height (resolution independent). Box height = points x
  `ICON_UNITS_PER_POINT` (0.0208). `Icon.scale(f, scale_stroke=True)`; `scale_icon_strokes` (§24).
- **Params**: `vidgen.scene.IconName` (`ThemeToken("icon")`): with a theme in the validation
  context the name or alias must be in `active_icons()`; schema `enum` of names and aliases.
  Layout dump kind `icon` with `icon` = name.
- **`vidgen list-icons`** (`iconlist.py`, not a render input; finds the project root without
  loading the config; JSON in docs/CONFIG.md "`vidgen list-icons`"). Icon modules and vendored
  files are in `vidgen_source_digest`.

## 23. Refinements (Step 20, icons: curated expansion)

- **Set**: 200 Lucide icons, 25 per category, each with ≥ 3 distinct tags; no brand marks.
- **Aliases**: Lucide's old names whose file draws exactly like one vendored icon, plus curated
  `{alias: icon}` in `tools/icon_set.json`; the tool rejects aliases that are current Lucide names,
  conflict, point at unlisted icons, or old names listed as icons.
- **Resolution**: `resolve_icon(name, icons)` (name first, then alias; an alias never shadows a
  name), `builtin_aliases()`, `icon_names(icons)`; a project icon replacing a built-in keeps its
  aliases.
- **Catalogue**: `docs/ICONS.md` = `iconlist.catalogue_markdown(manifest)` (`vendor_icons.py
  --docs`); a test keeps it equal to the manifest.

## 24. Refinements (Step 21, icons in built-in scenes)

- **`grid_shape(n, aspect=None, *, cell_aspect=1.0, max_cols=None) -> (rows, cols)`**
  (`regions.py`, in `vidgen.api`): best cell size, then fewest empty cells, then fewest rows.
- **`icon_mobject.scale_icon_strokes(mob, factor)`**: `shrink_to_fit` and `place` call it so icons
  in a scaled group keep their proportions.
- **`bullets`** `items: list[BulletItem]` (`BulletItem(text, icon)`, a string accepted via
  `also_accepts`); `title` and `end_card` `icon` (an icon alone satisfies `end_card`'s "at least
  one of title, lines, logo, icon"); **`icon_grid`** (`scenes/icon_grid.py`). Keys:
  docs/CONFIG.md#bullets, #title, #icon_grid. Cells are added whole before their entrance (else an
  introducing animation would add a part alone); `icon_grid` `groups` list every item once.

## 25. Refinements (Step 22, review 1)

- **Font roles in text helpers**: `T`, `MT`, `NarratedScene.text`/`markup`, `fit_text`,
  `fit_text_sized`, `readable_text` take `role=None` (family = `font`, else
  `theme.font_for(role)`, else `theme.font`).
- **`SceneParams.also_accepts: ClassVar[tuple[type, ...]] = ()`**: other input types a nested
  model is built from; `describe.type_name` prints them (`list[str | BulletItem]`).
- **`register_theme_defaults`** rejects non-identifier token names and colours other than `#RGB`,
  `#RRGGBB`, `#RRGGBBAA`.
- **Icon search** (`icons._score`): 0 exact name, 1 name prefix or exact alias, 2 whole word of
  name/alias, 3 exact tag, 4 whole word of a tag, 5 part of name/alias, 6 part of a tag, 7 category.
- **`--json` errors**: every `--json` command answers errors with the envelope, `ok: false`, exit
  1 (usage 2).

## 26. Refinements (Step 23, per-beat actions)

- **Config** (`config.ActionConfig`, `BeatConfig.actions`; user reference docs/CONFIG.md "Beat
  actions"): canonical `{action, target, at, until, run_time, ...options}` (`target` name, pattern
  with `*`/`?` or list; `at` in [0, 1); `until` a later beat of the scene). Other keys are options
  (`ActionConfig.options`; `ACTION_KEYS` reserved). Shorthand `{NAME: TARGET, ...options}`: `NAME`
  = first non-`ACTION_KEYS` key; `ActionConfig.resolved(known)` re-picks when exactly one other key
  is an action (key-sorting tools). Actions count in the render fingerprint, not the TTS hash.
- **Registry** (`vidgen.registry`): action types beside scene types with the same two layers and
  collision rules (`register_action`, decorator `action(name, *, override=False)`, `find_action`,
  `action_names`, `all_actions`); `reset/snapshot/restore/isolated` cover both. Built-ins in
  `src/vidgen/scenes/actions.py` (only `from vidgen.api import *`).
- **`vidgen.actions.Action`** (exported): `Options` (`ActionOptions`, `extra="forbid"`), class
  attributes `run_time` (0.6), `reversible` (allows `until`, needs `revert`), `needs_visible`
  (hidden targets revealed first), `needs_target`, `temporary`, `moves_camera`, `target_options`
  (§27). One instance per use, so `apply(scene, targets) -> list[Animation]` can keep what
  `revert(scene, targets)` needs. `check_action_class` validates at registration.
- **Targets** (`vidgen.actions.Target(names, mobject, entrance)`, exported): a scene type declares
  `target_patterns` and classmethod `target_names(params)` (every name, for validation without
  rendering); `construct()` registers with `self.target(names, mobject, entrance=None)`.
  `on_screen_parts(t)` = the target's largest parts in the scene's family (a group target is never
  added itself, else Manim draws its parts twice); `entrance(t)` = `[]` when shown. Built-ins build
  their steps from `entrance()`, so a target an action revealed early is not revealed again;
  `reveal` of a shown target is a no-op, not an error (timing decides).
- **Validation** (`actions.scene_actions(...) -> (uses, problems)`): unknown action, options,
  `until` on a non-reversible action, missing/unknown targets, at
  `scenes[i].beats[j].actions[k].<key>`. `plan_actions` raises one `VidgenError`; it runs in
  `pipeline._check_scenes` (before workers) and `NarratedScene.__init__`.
- **Timing** (`actions.ActionRunner`): due frame = beat start + `round(at * d * fps)`; `until`
  reverts are due at the beat start, first. Actions run **inside waits only**
  (`ActionRunner.wait(frames)`), so an action never shares a `play` with the scene's own
  animation. Run times shrink so all phases end by `d + pad` (shortened plays carry `requested`);
  phases: entrances of hidden targets, then batches with disjoint target families. `end_beat()`
  applies what found no time and warns. `play_steps` ends slot *k* at the absolute `start +
  (k+1)·slot`.
- **Built-in actions**: `reveal`, `dim` (`opacity` 0.45, §27), `highlight` (`style`
  `color|box|underline|flash|fill` or a list; `flash` and `color` exclusive). Colour/opacity
  changes use `Repaint` (fill/stroke RGBA arrays, points untouched); revert restores only the
  channels the action changed (RGB for highlight, alpha for dim), so the two combine and undo
  independently. Listing/schema: `list-scenes` shows targets and actions; schema
  `BeatConfig.actions.items` = `anyOf` [`ActionConfig`, `ActionShorthand`], options under
  `$defs/action.NAME`; targets and `until` are left to validate.

## 27. Refinements (Step 24, zoom, transform, targets everywhere)

- **Camera**: `NarratedScene` subclasses `MovingCameraScene`; scenes that never move the frame are
  pixel-identical to a plain `Scene`. `play` removes the camera frame from `self.mobjects` after a
  play that added it, unless it has updaters. Layout dump `camera.zoom`; zoomed stills (> 1.001)
  skip `off_frame`/`safe_area`. Screen-fixed overlays are composited in `add_frame` (§41).
- **Framework**: `temporary` (needs `reversible`): revert due `run_time` before the end of the
  return beat (the use's beat, or the beat before `until`). `moves_camera`: never two in a batch.
  `target_options`: option names holding targets, checked like `target`. Same-frame order:
  `until` undoings, beat actions, temporary undoings (`_rank`). An undo of a never-applied use is
  skipped. `resolve_targets(scene, pattern)`: a plain name shared by several targets selects the
  ones on screen, else the first.
- **Full opacity**: `Target.rest` (at registration; `rest_opacity(member)` falls back to 1/0), so
  scenes register targets right after layout. **`dim`** = at most `opacity` x full opacity (ratios
  kept; never compounds); `scenes.actions.dim_to(target, part, factor)` serves built-ins.
  **`highlight` `color`** raises alpha to full; revert restores RGB and alpha min(current, saved).
  Box around `Target.outline`. `Repaint` also animates `ImageMobject.pixel_array` (`paint_image`).
- **`zoom`** (reversible, temporary, `moves_camera`; `scale` (> 1, ≤ 8), `padding` (0.15)):
  magnification ≤ `max_scale` 3 by default, centre clamped inside the frame, ≤ 1.01 → no move and
  a warning; `MoveCamera(scene, width, center)`.
- **`transform`** (`into` required, a target, not a literal, because a literal has no place or
  style in the layout; `style auto|replace|shapes|tex|fade`): the source's on-screen parts are
  swapped for a copy that morphs into `into`. Scene steps skip transformed-away targets.
- **Targets of every built-in**: table in docs/CONFIG.md "Beat actions", kept in sync with
  `target_patterns` by `tests/test_actions_coverage.py`. `equation` `terms` use
  `MathTex(substrings_to_isolate=...)` (each must occur in a step).

## 28. Refinements (Step 25, `stat` and `chapter`)

- **`stat`** (`scenes/stat.py`; keys docs/CONFIG.md#stat): `format_number(value, decimals,
  thousands, decimal_mark)` (typographic minus, no "minus zero"); `StatComparison` accepts a plain
  number. The change chip's pill is filled with `surface` (a colour tint failed contrast on light
  presets). The count-up lays out at the final value, then rebuilds the line each frame (`become`
  + `original_text`, so the layout dump sees the shown string).
- **`chapter`** (`scenes/chapter.py`; keys docs/CONFIG.md#chapter): `params.title` is **the
  chapter's name** (read by §42 and §52), `number_text()` the number.

## 29. Refinements (Step 26, `comparison` and `table`)

- **Dotted target names** (`actions.TARGET_NAME`: `word(.part)*(:label)?`): `col2.item3`, `cell2.4`.
- **`highlight` style `fill`**: a plate at `fill_opacity` 0.22 (below lint's 0.3 cover threshold),
  faded in by a `Transform` (`FadeIn` would move it to the top), inserted in `scene.mobjects`
  just before the target's first part; scenes put backdrops at `z_index` -1 so the plate lies
  between backdrop and text.
- **`comparison`**, **`table`** (`scenes/comparison.py`, `scenes/table.py`; keys
  docs/CONFIG.md#comparison, #table): one text size per scene, down to `readable_size()`, else
  scaled with a warning. `table` rejects bool/null cells; `Params.texts()` = cells as shown (also
  for `row:<first cell>`); every cell text is added on its own and invisible row/column/cell
  rectangles are the targets' outlines.

## 30. Refinements (Step 27, `timeline`)

- **`measure_text(text, max_width, *, size, weight, slant, line_spacing, balance, theme, font,
  role) -> TextMeasure(lines, width, height, fits)`** (`vidgen.layout`, exported): how `fit_text`
  would wrap, from cached word widths without building a `Paragraph` (0.1–0.3 s each). Estimates
  run a few percent short, so planners measure at ~0.97 of the width and check the built result.
- **`fit_text(..., balance=False)`** (also `fit_text_sized`, `measure_text`): re-wraps at the
  narrowest width keeping the line count.
- **`timeline`** (`scenes/timeline.py`; keys docs/CONFIG.md#timeline): a YAML date becomes its ISO
  string; event refs = 0-based index, else date as shown, else title (ambiguous → error);
  `date_position()` parses numbers, years, `YYYY-MM`, `YYYY-MM-DD`; proportional spacing needs
  non-decreasing positions. Layout candidates are compared by fit first, so growth never decides
  the layout (also in `diagram`, `process`). `_reveal` brings hidden predecessors' segments, so an
  early `reveal` never makes the scene repeat an entrance.

## 31. Refinements (Step 28, graph layout and `diagram`)

- **`vidgen.graph`** (manim-free; in `vidgen.api`): `layered_layout(nodes, edges, *,
  direction="LR"|"TB", layer_gap=1.0, node_gap=0.5, routing="straight"|"orthogonal",
  port_spacing=0.2, port_spread=0.6, label_margin=0.15, sweeps=12) -> GraphLayout(nodes: {id:
  NodePlace(x, y, width, height, layer, order)}, edges: [EdgeRoute(source, target, points,
  reversed, label_at)], layers, width, height, direction, crossings, reversed_edges)`. Nodes: ids
  or `GraphNode(id, width, height, shape)` (`box`/`ellipse`/`diamond`/`stadium`); edges
  `(source, target)` or `GraphEdge(source, target, label=(w, h))`. Centred on the origin, y up.
  Unknown/duplicate ids, self-loops, unknown options → `VidgenError`. Deterministic.
- **Phases** (Sugiyama): DFS cycle breaking in input order (back edges reversed), longest-path
  layers with dummies, barycenter sweeps with transposition, least-squares coordinates, ports on
  facing sides (`orthogonal`: one lane per run). The topology phases are cached (`_topology`,
  `lru_cache`) because scenes lay out one graph at many sizes.
- **`diagram`** (`scenes/diagram.py`; keys docs/CONFIG.md#diagram), registered again as
  **`flowchart`** (`scene("flowchart")(Diagram)`: same class, its own type for listing, schema and
  validate). Edge strings (`"a -> b"`, `"a -> b: label"`, `"a --> b"`, chains) expanded by a
  before-validator; `from` is the alias of field `source` (`describe` shows aliases). Validation:
  duplicate ids, unknown nodes, self-loops, duplicate edges, bad `steps`/`highlight` refs. Steps
  reveal in waves (sources, edges, reached nodes); a named edge brings its ends.

## 32. Refinements (Step 29, `process` and `network`)

- **Network helpers** (`helpers.py`, exported): `column(n, x, gap, y0, r, color, *,
  horizontal=False, skip=None)`, `edges(a, b, pairs, color, width, opacity, *, colors=None,
  shorten=0.0)`, `grouped_pairs(n, groups, m=None)` (`group_bounds`), `sparse_pairs(n, m, ratio,
  seed=0)` (seeded, every unit keeps ≥ 1 pair; reproducible).
- **`process`**, **`network`** (`scenes/process.py`, `scenes/network.py`; keys
  docs/CONFIG.md#process, #network): `process` z order cards 2, content 3, token 1, tag 4 (follows
  the token on an offset path, no updaters); an early `reveal` of a stage shows the card only.
  `network` `Connection` accepts a string (`dense`, `sparse:0.3`, `grouped 3`) or object; sparse
  pairs are seeded by the layer index and thinned to `max_edges` reproducibly.

## 33. Refinements (Step 30, chart helpers, `scatter` and `histogram`)

- **`vidgen/charts.py`** (in `vidgen.api`; user reference docs/EXTENDING.md "Charts"):
  `axis_ticks`, `short_number`, `tick_texts`, `linear_fit -> LinearFit` (< 2 distinct x →
  `VidgenError`), `ChartAxis`, `value_axis` (domain = data extended to the outer ticks unless
  `lo`/`hi` fix an end), `chart_axes -> ChartAxes`, `chart_label_size(size)` (≥ `readable_size()`),
  `chart_legend`, `legend_spot`, `auto_legend` (panel at `z_index` 1 so gridlines never cover
  it), `sample_path`, `chart_marker` (`CHART_MARKERS`), `chart_title` (heading role, in
  `region("header")`, `PORTRAIT_TITLE_GROWTH` 1.3), `chart_caption`. `bar_chart`, `line_chart`
  and every later chart use them.
- **`scatter`**, **`histogram`** (`scenes/scatter.py`, `scenes/histogram.py`; keys
  docs/CONFIG.md#scatter, #histogram): `ScatterPoint` accepts `[x, y]`/`[x, y, label]`; validation
  rejects points outside explicit bounds (no silent clipping), non-positive values on log axes,
  trends on log axes or with < 2 distinct x; an index wins over a numeric label. `histogram`
  rules use numpy's bin count with `nice_width` and `aligned_edges`; `MAX_BINS` 60; `compare`
  shares the edges; range labels (`bin:<range>`) = `tick_texts(edges, x_format)` joined with `-`.

## 34. Refinements (Step 31, `pie` / donut and `heatmap`)

- **Colour helpers** (`charts.py`, exported): `mix_colors(a, b, t)`, `text_color_on(fill,
  min_ratio=4.5)`, `ColorScale` (OKLab interpolation), `color_scale(...)` (`center` outside given
  `lo`/`hi` → `VidgenError`), `color_bar(...)`.
- **`pie`**, **`heatmap`** (`scenes/pie.py`, `scenes/heatmap.py`; keys docs/CONFIG.md#pie,
  #heatmap): `pie` `uses_legend()` is static (`legend` or > 6 slices) so `target_names` knows it;
  the last slice's colour never equals the first; layouts that drop labels warn. `heatmap` ≤
  40 x 40, `scale: auto` diverging when values lie on both sides of `center`, cells below
  `MIN_CELL` 0.3 warn "split the matrix"; values hidden when they do not fit (warning with
  `show_values: true`).

## 35. Refinements (Step 32, `code_walkthrough`)

- **`code_walkthrough`** (`scenes/code_walkthrough.py`; keys docs/CONFIG.md#code_walkthrough):
  `steps` aligned with the beats (`WalkStep` or a bare line spec).
- **Line specs** (`parse_lines`, `resolve_lines(spec, source, first)`): `N`, `N-M`, `/regex/`,
  mixed ranges (end = first match at or after the start), commas (inside `/.../` they belong to it)
  or a list; `all` clears, `None` keeps the view. Checked at params validation for inline code, by
  `validate_project` for a `path`.
- **Scrolling**: the `Code` stays one mobject; rows out of view are taken out of its two
  `Paragraph`s (`_include`), so they are not drawn, `is_shown(line<N>)` is false and the layout
  dump still sees one `Code` (`original_text` = shown rows). Sizing is analytic (`_fit`) because a
  listing costs ~0.1 s per line. Focus moves the camera (`MoveCamera`).
- **`code` helpers** shared with it: `mono_metrics`, `size_for_columns`, `text_canvas`,
  `renumber`, `line_centers`, `line_runs`, `style_names`; `code` wraps at `max(readable, min(size,
  size giving TARGET_COLUMNS 32))`.
- **Manim text canvas**: Manim renders `Text` on a canvas of the output's pixel size and fails the
  glyph check ("rendered fewer glyph(s)...") when text runs off it; `code.text_canvas(lines, size)`
  enlarges `config.pixel_width/height` while a listing is built. The SVG cache key ignores the
  canvas, so an SVG clipped by an earlier failure must be deleted with `build/`.

## 36. Refinements (Step 33, `equation_derivation`)

- **`equation_derivation`** (`scenes/equation_derivation.py`; keys
  docs/CONFIG.md#equation_derivation): `steps` aligned with the beats.
- **Part isolation** without Manim's `substrings_to_isolate` (which splits raw substrings, e.g.
  `x` out of `\exp`): the TeX is tokenised, parts are whole-token runs, and each occurrence is
  wrapped in a dvisvgm group (`\special{dvisvgm:raw <g id='vgpartNNN'>}` … `</g>`) read from
  `id_to_vgroup_dict`; `{{ … }}` (split with `MathTex._split_double_braces`) too. A token after
  `\left`/`\right`/`\big…` is never wrapped. `tex_string` is reset to the step as written.
- **Morph** (`morph(source, target, style)`): the source is a copy; `SwapAtEnd` adds the target
  formula whole, so between beats the scene holds whole `MathTex`es. `term:` targets mean the live
  step, `step<N>` the line (live or archived).
- **Errors**: brace problems, empty `{{ }}`, unused parts, `match` not in both steps → params
  errors; LaTeX errors → `VidgenError` "step N does not compile: <TeX message> (at: <context>)"
  (`tex_error_excerpt`).

## 37. Refinements (Step 34, `screenshot` and callouts)

- **Callout helpers** (`vidgen/callouts.py`, in `vidgen.api`; also used by the callout action
  §44): an area is a mobject, `Region`, or `[x, y]`/`[x, y, w, h]` (top-left, y down) in fractions
  of `within` or (`units="px"`) image pixels; `callout_area`. `callout_box`, `callout_circle`,
  `callout_arrow`, `callout_magnifier`, `callout_spotlight` share `(area, label="", *, within,
  units, color, label_size, side, bounds, avoid, scale, theme, ...)`; `callout(kind, ...)`
  dispatches (`CALLOUT_KINDS`). The `callout_` prefix avoids shadowing `box`/`circle`/`arrow` under
  `from vidgen.api import *`. `Callout(Group)` with `extent(pad)` (feeds `avoid`) and
  `draw(start=0)` (one animation per part; no `AnimationGroup`, which would leave its `Group` in
  `scene.mobjects`). Label plates are drawn first so lint reads them as the backdrop.
- **`screenshot`** (`scenes/screenshot.py`; keys docs/CONFIG.md#screenshot): `steps` aligned with
  beats; fractions are checked by the params model, pixels by `validate_project`. Callouts are
  built once before the first beat; callouts built for another camera always leave when it
  changes. A step whose callouts are all shown is skipped.

## 38. Refinements (Step 35, `video_clip`)

- **Frames decoded inside Manim, not composited by ffmpeg**, so stills, layout dump, lint,
  callouts, camera moves and actions see the clip like any image.
- **`ClipMobject(ImageMobject)`** (`vidgen/clips.py`, in `vidgen.api`): `play(scene, at=None)`
  ties a shared `_Playback` to `scene.renderer.time`; `get_pixel_array()` returns the frame at
  `timing.source_time(now - start)`; a time-based no-op updater makes Manim redraw it every frame.
  `_Playback.__deepcopy__` returns itself, so copies show the same moving picture.
- **Modulation**: a clip's `pixel_array` is a 1 x 2 black/white RGBA pair and each frame maps
  affinely through it, so interpolations, `dim` and `highlight` act on the moving picture exactly
  as on a still.
- **Decoding** (`ClipReader`, PyAV, sequential; seeks only backwards or > 2 s ahead): the frame at
  `t` is the last with time ≤ `t` + 2 ms. A second video stream titled `alpha` (§120.9) supplies
  the alpha channel. At magnification 1 the decode size equals the shown size and
  `resampling_algorithm` is `NEAREST`.
- **Timing** (`ClipTiming(start, end, speed, loop)`, `fit_speed`): clamped to `end - END_GAP`
  (5 ms) without `loop`. **The clip never changes the scene's length** (§5): longer clips are cut
  by the fade-out, shorter ones hold their last frame (warning above 2 s) unless they loop.
- **Sound** (`clip_audio`): one ffmpeg call writes exactly the played sound (`atempo` chain,
  loops in sample step, padded to the scene length, faded over the outro) to a temp WAV mixed by
  `add_sound` at time 0; volume `UNDER_NARRATION` 0.25 with beats, 1 when silent; skipped with
  `--no-audio`.
- **`video_clip`** (`scenes/video_clip.py`; keys docs/CONFIG.md#video_clip): a subclass of the
  `screenshot` scene; `magnifier` callouts and `frame` with `bleed` are rejected. Limits: rotation
  metadata ignored; variable frame rate shows the frame preceding the scene time.

## 39. Refinements (Step 36, `map`)

- **Data** (`src/vidgen/data/geo/world-110m.json` + `LICENSE`): Natural Earth 1:110m countries
  via `world-atlas`, names/codes from `i18n-iso-countries`, built by `tools/make_world_map.py`
  (antimeridian cuts, outer rings counter-clockwise and holes clockwise for Cairo's non-zero
  fill, label points, "main" boxes; deterministic). ISO countries missing at this scale are in
  `small` (explicit error).
- **Lookup** (`find_country`): normalised names claimed in priority order (codes, display names,
  aliases); unknown → suggestions; small countries → "use a pin".
- **Projection**: Equal Earth (numpy) centred on the view's middle longitude; `MapView(box, area,
  antarctica, expand)`; polygons cached per centre longitude and shifted ±360° (views over the
  date line work). A `world` view in portrait keeps the items' longitudes and every latitude.
- **`map`** (`scenes/world_map.py`; keys docs/CONFIG.md#map): steps as `screenshot`; only
  countries the params name have targets (static `target_names`). Limits: flat arcs, no city
  list, no graticule.

## 40. Refinements (Step 37, review 2)

- **Examples**: `examples/minimal` (core built-ins, beat actions) and `examples/gallery` (the
  rest); a test checks that together they use every built-in type.
- **Header synonyms** (`SceneParams.header_synonyms`, default on; `HEADER_SYNONYMS`): a `Params`
  model with only one of `heading`/`title` (and their `_size`/`_color`) accepts the other via
  `AliasChoices` set in `__pydantic_init_subclass__`; `title`, `chapter`, `end_card` opt out. Both
  given → error (`'title' is another name for 'heading', which is given too; keep one`).
  `actions.TARGET_SYNONYMS` does the same for target names.
- **Unknown keys**: `config.validation_problems(error, prefix, model=None, noun="parameter")`
  rewrites pydantic's extra-input error with `describe.unknown_key_message` (`unknown parameter
  'dim_prev'; did you mean 'dim_previous'? (known: ...)`) for params, action options
  (`noun="option"`) and the top level (`noun="key"`).
- **`one_or_many(item)`** (`vidgen.api`): `Annotated[list[item] | item, AfterValidator]`, always a
  list.
- **Text on fills** (`NarratedScene.target(..., on_fill=)`, `(text, shape)` pairs): dimming and
  highlighting recolour such text with `text_color_on` (dimmed at `TEXT_ON_FILL_DIM` 0.7) instead
  of fading it; reverts restore it.
- **Scene dimming survives `until`** (`Target.scene_dim`): `dim_to(..., own=True)` records the
  factor; the `dim` action's revert caps at `rest x scene_dim`.
- **Decorations follow** (`scenes/actions._follow`): boxes, underlines and fill plates get a
  non-time-based updater (waits stay frozen) keeping their offset and opacity relative to the
  outline; undo clears it first.
- **Copy-free fades** (`helpers.Fade`, `helpers.fade_out`, in `vidgen.api`): Manim's
  `FadeIn`/`FadeOut` copy the mobject in `begin`, which dominated long renders; `Fade` animates
  fill/stroke arrays without a copy. `clear_all` uses `fade_out` (Manim's `FadeOut` with
  images/clips); `Repaint` skips the copy too.
- **Layout dump `rotation`** (`introspect._glyph_heights`): one-line text (≥ 4 glyphs) rotated
  ≥ 8° is measured along its normal; key `rotation` in degrees.
- **Too-much-content warnings** read `the <thing>'s N <items> do(es) not fit this frame at the
  readable size; <remedy>`.
## 41. Refinements (Step 38, overlays: framework, `lower_third`, `watermark`)

- **Config**: `VideoConfig.overlays: list[OverlayConfig]` (`extra="allow"`): `type`, `id` (default
  the type; `<type><n>` when several id-less entries share it), `scenes` (`all` | ids), `exclude`,
  `from` / `to` (field `from_`; seconds or a scene id = its start / end), `reserve` (`bool | None`);
  other keys = type options. `SceneConfig.overlays: bool | {id: false | overrides}`; a mapping with
  `type` under an unknown id = a scene-only overlay. Keys: docs/CONFIG.md "Overlays"; custom types:
  docs/EXTENDING.md §9.
- **Registry**: a third kind beside scene types and actions (`register_overlay`, decorator
  `overlay(name, *, override=False)`, `find_overlay`, `overlay_names`, `all_overlays`,
  `unknown_overlay_message`; `Snapshot` is a triple). `overlays.check_overlay_class`: `Options` an
  `OverlayOptions` with no common-key names, `build` implemented, `layer` an int. Built-ins in
  `scenes/overlays.py`, `scenes/progress.py`, `scenes/captions.py`.
- **`Overlay`** (one per scene render): `options`, `config`, `context`, `id`, `scenes`, `span`
  (video seconds, `inf` open). API: `build()` (full look, whole frame, once), `window()`,
  `state(t)` (hashable or `None`, **a pure function of video time**, so both sides of a cut agree),
  `pose(mobject, state)` (a copy), `settled(state)` (for lint), `shown_in(start, end)` (§42),
  `default_reserve()` (§43), `yields` (§51), classmethod `validate_project`; class attributes
  `layer`, `lint_skip`; helpers `interval()`, `transition(...)`, property `timed` (set `timed =
  True` when `state` reads video time). `with_opacity(mob, f)` is exported.
- **Timeline contract** (`vidgen/videoplan.py`, `VideoPlan(project, fps)`): each scene renders
  alone, so its place is planned. A beat lasts `round((d + pad) x fps)` frames (`d` = the MP3's
  decoded length, cached by path + size + mtime, else the word estimate); a narrated scene = beats +
  `ceil(outro x fps)` (`outro` = the type's attribute or `outro_seconds(params)`); a silent one
  `max(round(duration x fps), round(max(duration - outro, 1 / fps) x fps) + ceil(outro x fps))`. `SceneSlot(index, id, type, start, duration, beats:
  BeatSlot(id, start, end, text), chapter, overlap_in, overlap_out, cut)`, `chapters`, `resolve`.
  Built-ins match it frame-exactly; `join_scenes` warns when a scene with timed overlays starts
  > 1.5 frames from its plan (`render.overlays` in the timings). Only timed overlays read the plan.
- **Fingerprint**: with any overlay, `_overlay_inputs` = `{scenes, voices}`: per scene id, type,
  duration, `chapter` (+ a card's `number`), `overlays`, `transition`, and per beat id, text, spoken
  text, voice, MP3 and `.align.json` stats; plus the `voices` / `subtitles` sections. Without
  overlays the key is `null`.
- **Drawn in the renderer, not as mobjects**: `OverlayLayer` wraps `renderer.add_frame` outermost
  (after `FrameCapture`), so stills, layout dump and motion signal see composited frames while
  `scene.mobjects`, camera moves, `clear_all`, timing and frame counts are untouched. Frame `k` is
  video time `start + k / fps`; frozen waits split into runs of equal states. Not an updater (would
  unfreeze waits), not ffmpeg afterwards (stills and lint would miss it).
- **Patches**: cached per `(overlay, state)` (LRU 64 each), drawn by two cameras over black and
  white cropped to the posed pixel box (+ strokes + 3 px): Cairo is premultiplied, Manim images are
  straight alpha, so `on_black` = colour and `on_white - on_black` = `255 - alpha` exactly. Shown
  patches blend in layer order (uint16), within 2 levels of direct drawing.
- **Layout dump**: overlays at the still after all scene objects (`order` + 1000), paths
  `overlay:<id>/...`, key `overlay`; frames have `overlays: [{id, type, settled, skip}]`.
- **Reserve**: a reserving overlay's built box (`NarratedScene._reserved`) cuts `scene.safe_area`
  via `overlays.avoid(area, box, gap=0.2)` (largest of the four parts around it), static for the
  whole scene. Built-ins lay out in `self.safe_area` (incl. `chart_title(..., area=)`, `title`,
  `end_card`); `regions.safe_area()` is unchanged.
- **Lint**: `overlay_overlap` (warning, `min_overlap` 0.05): an overlay's box over scene
  text/code/math/number/icon; `safe_area`, `text_overlap`, `covered_text` skip overlay pairs;
  unsettled overlays and rules in `lint_skip` are dropped.
- **Validation** (`overlays.overlay_problems`, in `cli.project_problems` and `pipeline._check_scenes`):
  unknown types (did-you-mean), duplicate ids, unknown scene ids, numeric `to <= from`, misplaced
  override keys, unknown override ids, options as written and with each scene's overrides
  (`scenes[j].overlays.<id>`), theme tokens, `validate_project`. `scene_overlays(project, spec,
  theme, plan)` builds a scene's instances by `layer`, skipping timed ones missing the scene.
- **Listing / schema**: `list-scenes --json` `overlays: [{name, origin, builtin, overrides_builtin,
  doc, layer, lint_skip, options}]`; `vidgen schema`: `type` an enum, per type `if`/`then`
  (`overlay.NAME` defs, `additionalProperties: false`).
- **`lower_third`**: name / title / icon on a `surface` plate with an accent bar, `max_width` 0.6 of
  the safe width (9:16 all), `place(..., align)` (9:16 raised `PORTRAIT_LIFT` 0.12). Window: its
  scene's start + `at` for `duration`, cut at the scene end unless `across_cuts`; state = eased
  progress (3 decimals), sliding `SLIDE` 0.5. **`watermark`**: `image` (height `size` x short side,
  ≤ 0.3 wide) | `icon` | `text`, `inset` 0.025, `fade`; `lint_skip = ("contrast",)`.
- Limits: `reserve` is per scene, not per moment; no video overlays.

## 42. Refinements (Step 39, chapters, `progress_bar`, `chapter_indicator`)

- **Chapters** (`vidgen/chapters.py`): start at a `chapter` scene and at any scene with
  `SceneConfig.chapter` (title or `{title, number?}`; on a card it renames and keeps the card's
  number). `chapter_marks(scenes) -> [ChapterMark(title, number, scene, scene_index, card)]`;
  `chapter_problems` (in `VideoConfig`'s validator): repeated (casefolded title, number), integer
  numbers not increasing, a non-card mark right after a card.
- **Planned** (`VideoPlan.chapters`): `Chapter(title, number, scene, start, end, index, count,
  card)` (+ `label`, `duration`); `chapter_of`, `chapter_at`. **Public**:
  `vidgen.api.video_chapters(project, fps=None, intro=False)` and `Chapter`; `OverlayContext.chapters`
  / `.chapter`. A scene's own `chapter:` is out of its config dump (in overlay inputs).
- **`shown_in(start, end)`** `False` drops a timed overlay from that scene's render (no draw, no
  reserve); one shown in part of a scene reserves for all of it.
- **`progress_bar`** (`timed`): track (`dim` 0.35) and played (`primary`) along an edge,
  `thickness` 0.006 of the short side (≥ 2 px), `inset` 0; `chapters` → gaps of max(2 x thickness,
  3 px). State = played pixel columns `round(t / duration x width_px)`, of the whole video.
- **`chapter_indicator`** (`timed`): a label per chapter (`number` / `total` / title), shortened
  with "…" to `max_width` 0.4 (9:16 min(2x, 0.85)), `opacity` 0.85, `corner`; `build()` returns all
  labels (reserve clears the widest). Runs of a chapter's scenes (minus cards unless
  `on_chapter_cards`) cross-fade over `fade` at touching cuts; `shown_in` false on cards and before
  the first chapter.

## 43. Refinements (Step 40, burned-in captions)

- **Word times** (`vidgen/speech.py`: `WordTime`, `spoken_words`, `speech_bounds`, `SILENCE_DB`
  −40 dB). `beat_word_times(audio_dir, beat_id, text, start, end, spoken=None)`: a stored alignment
  of the current MP3 and text, else `estimate_word_times` within the MP3's speech bounds, else over
  `start..end`. Estimate weight per word = syllables + 0.05 x letters, pauses 2 syllables at a
  sentence end and 1 at `, ; : —`.
- **Alignment**: `voice.timestamps` (default false, not hashed) makes `vidgen tts` call
  `provider.synthesize_timed(text, previous, next) -> (audio, alignment | None)` (ElevenLabs
  `/with-timestamps`). `write_alignment` → `<audio_dir>/<beat>.align.json` `{version: 1, text,
  audio_sha1, characters, starts, ends}` (written after the MP3, before the hash; removed when a
  beat is made without timings; copied with variant audio). `read_alignment` accepts it only for the
  same text and MP3 sha1.
- **Cue cutting** (`vidgen/cues.py`, shared by SRT and captions): `segment_cues(words, widths, space,
  max_width, max_lines, max_words)` by dynamic programming; break costs `phrase_break_cost(before,
  after, language)` (sentence end 0, clause / dash 1, before conjunction 2, before preposition 3,
  plain 4.5, after article / preposition 9) + 1 per cue + under-fill `3(1 - fill)²` + unequal lines
  `4 Δwidth / max_width` + 3 for a sentence end inside a line. `caption_cues`: first cue at the
  beat start, others at their first word, the last until `until`. The SRT (`subtitles.split_text`,
  `beat_cues`, `write_srt(path, timings, audio_dir, ...)`) uses it at 42 characters.
- **`captions`** (`scenes/captions.py`, `timed`, `layer` 10, `lint_skip = ("max_words",)`): an
  invisible band (`max_lines` + padding) at the safe area's bottom (9:16 `lift` 0.12) / top / centre
  holds each cue as `VGroup(plate, *line Texts)` (ligatures off, shared baselines). State: cue index,
  or `(cue, word)` for karaoke (word glyphs scaled by `pop`, ≤ `POP_ROOM` 0.25 of a space per side;
  odd glyph counts → no highlight). Text colour and plate opacity (+0.05 steps) are chosen so
  `plate_contrast` (over black and white) reaches `lint.rules.contrast.min_ratio`; a failing
  highlight falls back to the first accent that passes (warning); `background: null` = outline.
- **Reserve default**: `Overlay.reserves` = `reserve`, else `default_reserve()` (base `False`;
  captions `position != "center"`); the band is reserved, not the cues.

## 44. Refinements (Step 41, the `callout` beat action)

- **A beat action, not an overlay** (`scenes/callout_action.py`, §26 / §37 helpers): it points at
  in-scene targets and moves with a zoom. `- callout: "bar:4K"` or `{action: callout, area: ...}`.
  Options: `kind` (`box` | `circle` | `arrow` | `label` | `spotlight` | `magnifier`), `label`,
  `area` (`[x, y, w, h]` / `[x, y]`, top-left), `within` (`frame` | `safe`), `units` (`fraction` |
  `px`), `color`, `label_size`, `side`, `curved`, `zoom`, `keep`, `name`. `problems()`: a target or
  an area; magnifier needs a target and an area; `within` only without a target; `keep` with `until`.
- **Geometry**: around `Target.outline` (else on-screen parts) of all targets; `area` with a
  target = fractions / px of its largest picture, else its box; without = of the visible view or
  its safe area. Labels stay in `scene.safe_area` (zoomed: the view, built at `scale` = view /
  frame width) and `avoid` on-screen text, callouts, small targets (< 20 % of the view) and overlay
  boxes; z-index +2 (spotlight +1).
- **Lifetime**: `Action.until_next_beat` (reversible, not temporary) and `default_until(later)`: a
  callout fades out when the next beat starts (`keep`: at the fade-out), not at its beat end,
  because beat-end stills must show it.
- **Named callouts**: `Action.provides()` registers target names later actions may use (`TARGET_NAME`,
  unused); a callout's `on_fill = (label, plate)` keeps it readable under `dim` / `highlight`.
  `Action.problems()` returns `(key, message)`s.
- **Magnifier** needs a still picture in the target, else a render-time `VidgenError`.
- **`screenshot` `caption`** (+ size / colour), like `video_clip`'s: a line under the picture, target
  `caption`; captions fade out during a `focus` move.

## 45. Refinements (Step 42, pronunciation dictionary)

- **Config**: `pronunciation: {term: say | PronunciationEntry {say, case_sensitive: true,
  whole_word: true, regex: false, language} | null}` (`null` removes a term; deep-merged in variants)
  and `pronunciation_file: PATH | [PATH, ...]` (same form, YAML / JSON); effective = files in order,
  then the inline map. Files load with the `Project` (`Project.pronunciation`; errors at
  `pronunciation_file (<file>)`). Bad regexes (no compile, empty match, missing group) are config
  errors. Users: docs/CONFIG.md "Pronunciation".
- **Matching** (`vidgen/pronunciation.py`, no manim): `whole_word` adds `(?<!\w)` / `(?!\w)` only
  where the term starts / ends with a word character; all matches in the **written** text are
  chosen greedily by start, length, entry order, never re-matched. `Pronunciation.apply(text) ->
  Spoken(text, spoken, replacements, matched, conflicts)`; `Project.spoken_texts()`. Per beat only.
- **TTS / hash**: everything sent to the provider is spoken text; the key is
  `provider.cache_key(spoken)` (§7), so unmatched beats keep their hashes. `audio_status` and the
  variant audio rule compare spoken text; `tts --dry-run` prints `says: <spoken>`.
- **Written text stays on screen**: alignments are of the spoken text; `map_word_times(spoken,
  times)` maps spoken word times back via `Spoken.word_groups()` (a written word spans its spoken
  words; one said as nothing gets a zero-length time at the next spoken word). `narration_speed`
  counts spoken words; the no-audio estimate counts written words.
- **Fingerprint**: `pronunciation` / `pronunciation_file` are out of the config part.
- **Validate warnings**: an entry matching no beat, one always shadowed by a longer entry, two
  entries on the same / crossing spans (`cli.validate_warnings`).
- No SSML phonemes and no server-side dictionaries. Built-in lists: §88.

## 46. Refinements (Step 43, multiple voices)

- **Config**: `voices: {name: VoiceEntry}` (every `voice:` key optional, `settings` merged key by
  key, plus `label`, `color`), `SceneConfig.voice`, `BeatConfig.voice`, `VoiceConfig.label` /
  `color`, `subtitles: {speakers: off | name}`. `default` is reserved for the base voice.
  `voices.voice_reference_problems` (in `parse_config`): unknown names with did-you-mean; unused
  voices warn. Users: docs/CONFIG.md "Multiple voices".
- **Effective voice** (`vidgen/voices.py`): beat `voice`, else scene's; `resolve_voice(config,
  name)` = base dump without `label` / `color` + the entry's non-`None` keys; `label` / `color`
  never inherited. `Project.voice_names()`, `voice(name)`, `beat_voice(id)`, `speaker_tags(mode)`.
- **Hash**: §7 formula by the beat's own provider (`tts.beat_providers`); base-voice beats hash as
  without `voices:`; `label` / `color` unhashed. Variant audio: own folder when `audio_fields` of
  the base voice differ or a shared beat's spoken text or effective voice differs.
- **Context**: `previous_text` / `next_text` only from neighbouring beats of the same voice
  (`tts.run.context_texts`): providers read context as the same speaker. Not hashed.
- **`vidgen tts --voice NAME`** (repeatable; intersects with `--beat`); `TTSPlan.voices`,
  `characters_by_voice()`.
- **Speaker tags**: `voices.speaker_tags(config)` labels each beat whose voice differs from the
  previous beat's and has a label (named: `label` or the name capitalised with `_` → space); the
  first cue starts `"<label>:"`, glued to the first word in cutting (`caption_cues(prefix=,
  prefix_width=)`, `CaptionCue.prefix`). `captions` `speakers: off | name | color | both`
  (`speaker_color`: the voice's `color`, else `theme.palette_color(index)`); plate opacity rises
  until every speaker colour passes contrast, else text colour (warning).
- **Fingerprint**: `voices` / `subtitles` are out of the config part (in overlay inputs, §41).

## 47. Refinements (Step 44, sound effects)

- **Built-ins** (`vidgen/sfx.py`, numpy): `BUILTIN_SOUNDS` (§69.19 lists the set) of
  `BuiltinSound(name, generate, duration, duration_range, description, use)`, deterministic (noise
  seed `crc32(name)`). `params`: `duration` (in range), `pitch` (±24 semitones), `intensity` (0–1).
  `_finish`: high-pass 25 Hz, ends exactly 0, DC removed, loudest 400 ms at `LOUDNESS_TARGET` −27
  LUFS, peaks ≤ `PEAK_CEILING` −9 dBFS (~7 dB under narration; a test keeps ≥ 5 dB). Synthesised at
  join, `lru_cache` per process (no shipped WAVs: params are continuous).
- **Project sounds**: `assets/sfx/<name>.<wav|flac|ogg|mp3>` (`project_sounds`, `.wav` first)
  extend / replace built-ins (`SoundLibrary`), decoded to 48 kHz, own level, no `params`.
- **Sources**: `NarratedScene.sfx(sound, at=None, *, gain, pan, align, **params)` → `SfxEvent(time,
  sound, gain, pan, align, params, beat)` in `sfx_log`; scene `sfx:` list (`SfxCue`: `sound`, `at`,
  `gain` −60..12 dB, `pan` −1..1, `align` `start|end`, `params`); the `sfx` beat action
  (`scenes/sfx_action.py`). Users: docs/CONFIG.md "Sound effects (`sfx`)".
- **Framework**: `Action.scene_targets = False` (target not resolved among scene targets) and
  `Action.animates = False` (runner calls `cue(scene, time)` at the due frame; never queued; must
  implement `cue`, not `apply`, not reversible). A sound plays exactly at `at`.
- **`sfx.auto`** (default off): built-in actions that animate get `AUTO_ACTION_SFX` (reveal pop −3,
  highlight tick −3, callout click −2, zoom whoosh 0.5 s −6, transform swoosh −6) except in beats
  with their own `sfx`; types with `entrance_sfx` (`chapter`: whoosh −3) at 0.
- **Mixing**: events go to `timings/<id>.json`; `join_scenes` shifts them to video time and writes
  `padded/sfx.wav` (`write_track`: 48 kHz stereo s16, exactly `round(total * 48000)` samples, start
  `round(time * 48000)`, `align: end` subtracts the length, clipped sums, master `sfx.gain`);
  equal-power pan with centre = full level on both channels. Sounds cross cuts (past the scene
  end warns); scene renders have none. Mix: §48.
- **Checks**: `sfx.config_problems` (unknown sounds, params on files, durations) in validate and
  the render pre-check; `NarratedScene.sfx` raises `VidgenError`. `vidgen list-sfx [--render-dir]
  [--json]` (`sound_entries`). `sfx.py` is not a render input; `sfx:` lists are scene config.

## 48. Refinements (Step 45, background music, ducking, loudness)

- **Config**: `music:` (`MusicSetting`: a source, a `MusicCue`, a list, or `false`); `MusicCue`
  `source` (bed or project path), `volume` (−60..12 dB), `start`, `loop` (true), `crossfade` (2),
  `fade_in` (1.5), `fade_out` (3), `duck` (`DuckConfig` | bool), `from` / `to` scene ids
  (`_music_problems`: known, ordered, one cue per scene); scene `music: true | false | {volume}`;
  `audio: {normalize: auto | true | false, target_lufs: −16, true_peak: −1.5}`.
  `music.config_problems` checks sources. None of `music`, `audio`, scene `music`, `music.py`,
  `mix.py`, `loudness.py` is a render input. Users: docs/CONFIG.md "Background music (`music`)".
- **Beds** (`vidgen/music.py`, numpy): `calm`, `pulse`, `bright` (more: §69.63, §91), PADsynth
  pads etc., rendered **circularly** so loops tile seamlessly; seed `crc32("music:<name>")`;
  `bed_loop(name)` cached; level `MUSIC_LEVEL` −28 LUFS integrated. A tiled loop, not a whole-video
  piece (fixed cost, seamless).
- **Files**: PyAV, mono duplicated, cached per (path, size, mtime), scaled to `MUSIC_LEVEL`;
  `music.Source`: looping plays `body[:-X]` once, then a loop whose head is cross-faded with the
  tail (equal power); `loop: false` → silence after the end.
- **Loudness** (`vidgen/loudness.py`): BS.1770-4 integrated (400 ms / 100 ms, gates −70 / −10),
  K-weighting by FFT on 10 s blocks with 0.5 s margins, `LoudnessMeter`, true peak by 4x polyphase
  sinc; matches FFmpeg `ebur128`.
- **Ducking** (`vidgen/mix.py`): a gain curve from narration timing (beat start to the end of its
  speech, `speech.speech_bounds`), not an envelope follower: exact, deterministic, looks ahead,
  unaffected by SFX / clip sound. `duck_curve` (100 Hz): gaps < `hold` filled, `-depth` on speech,
  raised-cosine `attack` / `release`. `DuckConfig` defaults depth 12, attack 0.4, release 1.0, hold
  1.5 (shorter holds pump between beats); `clips` (true) treats a sounding `video_clip` as speech.
- **Gain** (`plan_music` → `Placement`s, 10 ms): `10^(volume/20)` × fades × scene levels
  (`smooth_steps`: running min then 0.75 s average, so the quieter scene keeps its level) × ducking.
  A cue spans its `from` start to its `to` end (the last to the video end); cues do not cross-fade.
- **The mix** (`mix_audio`, in `join_scenes` unless `--no-audio`): `normalize: auto` = on only with
  music (narration-only videos keep their exact audio), never while narrated beats lack MP3s. On:
  pass 1 measures, gain = target − measured; pass 2 writes `padded/mix.wav` (48 kHz stereo 24-bit)
  through `limit()` (per-sample gain keeping the true peak `LIMITER_MARGIN_DB` 0.4 under
  `true_peak`) and measures. Off: `ffmpeg.join(..., sfx=)` sums with
  `amix=inputs=2:duration=first:dropout_transition=0:normalize=0`. One AAC encode. `MixReport` →
  `timings.json` / `render --json` `mix` `{mixed, normalized, target_lufs, true_peak_limit, gain_db,
  integrated_lufs, true_peak_dbtp, limited_db, music: [...]}`.
- `vidgen list-music [--render-dir] [--json]` (`music.music_entries`); music is not in scene renders.

## 49. Refinements (Step 46, transitions: crossfade and fade through a colour)

- **Config**: `TransitionConfig {type: cut | crossfade | fade_color | push | wipe, duration, color,
  direction, soft}` (0 < duration ≤ 5; `TRANSITION_DURATIONS` crossfade 0.5, fade_color 1.0, push /
  wipe 0.6; `color` fade_color only, default the background); a string = the type.
  `SceneConfig.transition` = the way **into** the scene; `VideoConfig.transition` the default for
  all but the first (`transitions.effective`). An overlapping type on the first scene is an error;
  `fade_color` there fades in. Users: docs/CONFIG.md "Transitions".
- **Timing contract**: overlapping types (`OVERLAPPING_TRANSITIONS`) start the next scene `overlap`
  frames early (video shortens); `fade_color` fades the last / first `round(duration x fps / 2)`
  frames (length kept). **Speech never overlaps**: a transition covers only the previous scene's
  silent tail (`transitions.silent_tail`); a short tail **holds** the last picture
  (`NarratedScene.tear_down`; extend, not clamp; `validate` warns). Built-in defaults need no hold.
- **The plan is the one source of starts**: `transition(i) -> TransitionSlot(type, seconds, color,
  overlap, fade_out, fade_in, hold)`, `scene_duration(i)` = own + hold, `start(i) = start(i-1) +
  frames(i-1) - overlap(i)`, `SceneSlot.cut = end - overlap_out`. Overlays, chapters,
  `resolve(id, end=True)` follow it. The join recomputes overlaps from renders
  (`transitions.join_overlaps`, limited to the measured tail; shortening warns) and every later
  time (timings, SRT, SFX, music, frames index, storyboard) derives from them.
- **Scene end**: before a non-cut, `finish()` holds the picture instead of `clear_all` (same frame
  count). `transition_in` / `transition_out` hold the slots.
- **Join video**: cut runs concat, chained `xfade` (`crossfade_graph`, half a frame early: weights
  `(j + 0.5) / n`, exactly `sum - overlaps` frames), then one libx264 encode (`VIDEO_CRF` 18);
  without overlaps a stream copy. Each run passes `ffmpeg.constant_rate` (`tpad`, `setpts`, `fps`,
  `trim`, `settb`) because `xfade` needs a constant rate across FFmpeg 4.4–8.x. ffmpeg ≥ 4.4
  required (`ffmpeg.MIN_VERSION`, `version_hint`).
- **Join audio**: with overlaps, padded WAVs sum into `padded/voice.wav`
  (`transitions.write_voice_track`, cumulative rounding, earlier tail faded under the next start).
- **`fade_color`** (`transitions.ColorFade`) wraps `add_frame` outermost (overlays fade too);
  boundary frames are pure colour.
- **Overlays in a crossfade**: from the next scene's start, the outgoing render draws the incoming
  scene's overlays (`OverlayLayer(following=, cut=)`); the blend is linear, so overlays come out as
  if drawn once. Own overlays still decide `reserve`.
- **Fingerprint**: `next_transition` (its config plus the next scene's duration, beats, MP3 stats;
  `"cut"` for a cut); own `transition` in the config dump. `timings.json` scenes get `transition:
  {type, duration, overlap}`; activity `overlap_out` (ends `dead_air` runs).

## 50. Refinements (Step 47, push, wipe, continuity)

- **push / wipe**: `direction` (`left | right | up | down`; default `transitions.direction`: left
  wide / square, up tall, per format), `soft` (wipe). `xfade_name`: `slide<dir>`, `wipe<dir>`,
  `smooth<dir>`. Timing is §49's.
- **Overlays rendered once, composited at the join** (a slide is not per-pixel linear): the
  outgoing scene draws none after its cut; the incoming worker's `OverlayLayer.split_head(overlap,
  path)` writes its first frames bare and their overlays to `scenes/<id>.overlay.mov` (`RgbaClip`,
  PNG straight alpha, plus a trailing transparent frame). `ffmpeg.join(kinds=, overlays=)` /
  `overlay_graph` lays it over the `xfade` chain (`overlay=eof_action=pass:format=yuv444`).
  `render.overlays.head` records it.
- **Continuity `carry`**: `SceneConfig.carry: [name | "a -> b"]` (`CarryEntry`, names match
  `config.TARGET_NAME_PATTERN`; not on the first scene). `carry.carry_problems` checks names against
  `target_names(params)`; `carry_warnings` for fade_color / push / wipe.
  - A: `carry_out` keeps those parts through `finish()` (`clear_all(keep=)`); `tear_down` stores
    their vector shapes (`carry.parts_state`; images skipped with a warning) → `carry/<A>.json`
    `{version, scene, fingerprint, objects}`. Re-created shapes, not pickled mobjects.
  - B: reads it (missing → `VidgenError`), `render.carry_from` = A's fingerprint, shows the copies
    from frame 0; `entrance(target)` → `carry_move` (`Transform` when shape counts match, else
    `FadeTransform`); unmatched copies fade out; `carry_in(name)` for custom code.
  - Order: `pipeline.with_carried` adds stale partners; `_runs(after=)` makes B wait for A.
  - Fingerprint: A `next_carry`, B `carry` + `carry_from` (only with carries).

## 51. Refinements (Step 48, review 3: overlays, captions, audio, transitions)

- **Narration level**: `scene.add_narration` decodes the MP3 (`sfx.decode_audio`, 48 kHz) and gives
  Manim a stereo WAV with mono at full level on both channels (`sfx.stereo`), so videos play at the
  MP3s' level (Manim's own path upmixes at −3 dB).
- **Scene lengths** (`ffmpeg.probe`): frames / nominal rate (`r_frame_rate`), not the average rate.
- **Overlays making way**: `Overlay.yields` (class attribute), `clear_of`, `clear_area`,
  `overlays.build_overlays`: yielding overlays build after reserving ones; `lower_third` yields
  (moves above bottom captions).
- **`Action.after_camera`** (`callout`): in a frame with a `moves_camera` action due, such actions
  get their own batch after it.
- By design: a beat's first cue starts at the beat start; overlapping transitions re-encode the
  whole video.

## 52. Refinements (Step 49, chapters in the MP4 and a YouTube chapter list)

- **Config**: `chapters: {metadata: true, youtube: true, intro: "Intro" | false}`, `metadata:
  {title, artist, album, comment, description, copyright, date, genre}` (title defaults to the
  video's). Out of scene fingerprints. Users: docs/CONFIG.md "Chapters in the outputs".
- **Published chapters** (`chapter_export.py`): start at 0:00 — `published_chapters` adds an intro
  chapter (`Chapter.intro = True`) or with `intro: false` moves the first to 0 (within 1 ms counts
  as 0). Only in outputs; overlays use `VideoPlan.chapters`. Output times come from the join
  (`joined_chapters`).
- **MP4**: `padded/metadata.txt` (FFMETADATA, `[CHAPTER]` `TIMEBASE=1/1000`, `END > START`, `\ = ; #`
  and newlines escaped) mapped with `-map_metadata N -map_chapters N`; `metadata: false` → no
  chapters (tags still).
- **YouTube list** (`pipeline.write_chapter_list`): `<output>[_<variant>][_preview]_chapters.txt`
  (`Project.chapters_path`), `M:SS Title` (`H:MM:SS` ≥ 1 h), times **rounded down**.
  `youtube_problems` (≥ 3 chapters, each ≥ 10 s) are `chapters:` warnings at render and validate
  (`chapter_warnings`); the file is written anyway, and removed when chapters / `youtube` are off.
- **JSON**: `timings.json` / `render --json` `chapters`, `outputs.chapters`;
  `RenderResult.chapters`; `post_render` hooks get `chapters`. Titles on one line, without numbers.

## 53. Refinements (Step 50, thumbnail and GIF / clip export)

- **Config** `thumbnail:` (`ThumbnailConfig`): a frame (`scene`, `beat` id or 1-based number, `at`,
  `overlays`: true) or a designed card (`title`, `subtitle`, `icon` | `image`, `preset`,
  `background`), plus `jpeg` (false), `auto` (true); mixing kinds is a config error
  (`thumbnail_problems`). Out of fingerprints. Users: docs/CONFIG.md "Thumbnail".
- **Size** (`thumbnail_size`): 1280x720 / 1080x1920 / 1080x1080 by the final format's orientation,
  cover-fitted. **Files**: `Project.thumbnail_path(preview, suffix)` =
  `<output>[_<variant>][_preview]_thumbnail.png` (`.jpg`: quality 92 → 55 until ≤ 2 MB), small copy
  `build/<render dir>/thumbnail/<name>_small.png` (`SMALL_LONG_SIDE` 320). Atomic writes.
- **Frame thumbnails** come from the scene's own render `scenes/<id>.mp4` (rendered first when not
  `render_current`). `frame_number`: a beat's last frame (the §13 still, capped by the next beat), or
  `floor(((beat start | 0) + at) x fps)`, or the last beat's end / a silent scene's frame before its
  fade-out; past the end → error.
- **Bare renders**: `Project.without_overlays()` (`overlays: []`, every scene `overlays: false`,
  `bare = True`, `render_dir` `build/<final|preview>[_<variant>]_bare`; worker `--bare`), a separate
  folder so normal renders are never replaced. Also used by decks (§55).
- **Designed thumbnails** (`design_thumbnail`, Pillow; icon via Cairo): 16:9 text left / visual
  right, else visual on top; title the largest even size 0.2 S → 0.078 S (S = short side) fitting 3
  lines (4 portrait), else cut with `…`; colours chosen for ≥ 4.5:1; `preset` =
  `Theme.derive(ThemeConfig(preset=...))`.
- **Checks** (`ThumbnailCheck(rule, severity, message)`) at the small size: `min_font` (title 14 /
  subtitle 10 px), `contrast` 4.5:1, `fit`, `max_words` > 6 (info), `file_size` > 2 MB, `resolution`
  (info). Frame thumbnails' text is not measured.
- **Render**: with `auto`, made after the join outside the extension session, then `post_render`
  (§63). `RenderResult.thumbnail`, `outputs.thumbnail`. `vidgen thumbnail` (`--scene`, `--beat`: a
  digit string is a number unless the scene has such a beat id, `--at`, `--no-overlays`,
  `--preview`, `--jpeg`, `--json`).
- **`vidgen export gif|clip`** (`export.py`): source = joined video + `timings.json` (missing →
  error naming `vidgen render`; durations agree within 0.1 s). `resolve_range`: `--scene` times
  from its start, default the whole scene incl. its outgoing transition. Default
  `exports/<output>[_<variant>][_preview]_<scene|video>[_<from>-<to|end>s].<gif|mp4>`. Users:
  docs/CONFIG.md "Export: GIF and clip".
  - GIF: one pass `palettegen=stats_mode=full` + `paletteuse=dither=sierra2_4a:diff_mode=rectangle`,
    `-loop 0`; width 480 (9:16 270) and 12 fps, each ≤ the video's; `--max-mb` re-encodes
    (`next_try`, ≥ 5 fps, ≥ 160 px, `MAX_ATTEMPTS` 6; else `within_budget: false`).
  - Clip: stream copy (`-c:v copy -frames:v N`) when the start is within half a frame of a keyframe
    and no `--width` / `--fps`; `--with-audio` encodes AAC 192k from a second seeked input; else
    libx264 CRF 18. Chapters dropped.

## 54. Refinements (Step 51, multi-language variants)

- **`language`** (`config.LanguageTag`, BCP-47, normalised `pt-BR`; per variant). `None` = English
  rules, nothing sent. `vidgen/languages.py`: `LanguageRules(code, name, conjunctions, prepositions,
  clinging, words_per_second, silent_final_e, iso639_2, abbreviations)` for en, pt, es, fr, de, it;
  others neutral. `language_matches(entry, video)`: subtag prefix. Users: docs/CONFIG.md "Languages
  and translations".
- **Language-aware**: `phrase_break_cost(..., language)` (and every cue / SRT function; punctuation
  of all scripts), `speech.syllables(word, language)`, lint `narration_speed` (`unit: auto | words
  | characters`, `min_rate` / `max_rate` `None` = the language's range via
  `NarrationSpeedRule.limits(language)`; characters 8–17/s where no word rate).
- **ElevenLabs `language_code`** (`str | false | None` on voices): `voices.resolve_voice` stores the
  code sent (`languages.elevenlabs_language_code`; auto only for `LANGUAGE_CODE_MODELS`
  `eleven_turbo_v2_5`, `eleven_flash_v2_5`). Only a sent code enters the body and the §7 hash
  (`language_code=<code>` before the text).
- **Outputs**: audio stream tagged with ISO 639-2 (`ffmpeg.join(..., language=)`); `timings.json`
  `language`. `PronunciationEntry.language` filters entries (`pronunciation.applies_to`).
- **Translation files** (`vidgen/translation.py`, no manim):
  - Markers: `TranslatableStr`, `TextRef` (in `vidgen.api`; schema `x-vidgen-text: text|ref`) on
    every built-in text field; `SceneParams.text_shorthand` / `text_defaults` describe shorthands.
  - Keys: `parse_key` / `format_key` (`.name` = mapping key or an item id of `scenes` / `beats`
    (`<scene>_b<n>`) / `overlays`; `[n]`, `["key"]`, `{"key"}` the key itself, `=field`, `$sep`).
  - `extract_texts(data, scene_model, action_model, overlay_model)` / `project_texts(project)`:
    only values present in the raw config, plus references (`TextRef` values, action targets naming
    a text).
  - File `TranslationFile {version: 1, language, source_language, entries: {key: TranslationEntry
    {source, hash, text, stale, old_source, obsolete} | text}, references}`; `source_hash` =
    sha1[:10]; `dump_translation_file` (YAML, header, insertion order).
  - **Applied at load to the raw config** (`apply_translations(data, doc) -> (data,
    TranslationReport)`; `Project.source_data` / `source_config` keep the original), so every
    consumer sees one translated config: texts, then key renames, then references. An entry applies
    only with text, a matching hash and not `stale` (**stale translations are not used**).
  - `merge_template`: keep (same key + hash), move (same hash, other key in the scene), mark
    `stale` with `old_source`, or `obsolete` / drop leftovers. `vidgen translate-template [--variant]
    [--lang | --language] [--output] [--json]` (`write_template`): file = the variant's
    `translations:` or `translations/<variant>.yaml`.
  - Validate: `translation_warnings`, `language_warnings`; `validate --json` `language` /
    `translations`.
- **Fingerprint**: `language` is in the config part, `translations` is not; `languages.py` is a
  render input, `translation.py` is not.
- Limits: number formats and map country names are not localised; arc shorthands, `lint_ignore`
  patterns and targets naming a translated point label do not follow translations.

## 55. Refinements (Step 52, slides export: HTML)

- **Key frames** (`vidgen/deck.py`): `deck_frames(project, *, preview=True, mode="beat"|"scene",
  per_beat=1, overlays=True, dedupe=True, jobs=1, force=False) -> Deck`, from §13 stills made
  current the §14 way (only stale scenes render). `beat` (default: content replaced per beat would
  be lost otherwise) = a slide per beat still; `scene` = the last still, all beats as notes
  (`per_beat` > 1 is an error). Dedupe (`stills_alike`, within a scene: ≤ 0.05 % of pixels at
  320 px differ by > 24 levels) keeps the later still. `DeckSlide(index, scene, scene_type,
  scene_number, scene_title, chapter, still, beats, k, n, time, scene_time, at, until, merged)`,
  `notes` (translated text, not pronunciation), `alt_text()`; `DeckChapter`; `DeckClip(beat, audio,
  at, duration)`. The play timeline puts rendered scene durations back to back (no overlaps).
- **Page** (`vidgen/slides.py`): `make_slides(project, ..., image_format="webp", quality=80,
  max_width=None, audio=False, separate=False, output=None) -> SlidesResult`, `slides_html(deck,
  images, size, audio)`; default `exports/<output>[_<variant>][_preview]_slides.html`. One file:
  pictures as `data:` URIs (each once), package data `data/slides/deck.css` / `deck.js` inlined, deck
  data in `<script type="application/json" id="deck-data">`, MP3s with `--audio`; `separate` puts
  files in `<name>_files/`. > 50 MB warns.
- **`deck.js`**: no libraries, ES5; keyboard / click / swipe navigation, hash `#N`, notes,
  overview, fullscreen, help, accessible slide groups and live region, print CSS. Play mode is
  driven by one clock along the deck timeline (re-seeks clips drifting > 0.3 s), not by chained
  `ended` events.
- **CLI** `vidgen slides` (`jsonout.slides_document`). `deck.py` / `slides.py` are not render
  inputs. Users: docs/CONFIG.md "Slides".

## 56. Refinements (Step 53, slides export: PDF)

- `vidgen slides --format pdf` shares frame and picture options with HTML; HTML-only (`--audio`,
  `--separate`) and PDF-only (`--notes`, `--title-page`, `--paper`) options on the other format are
  errors (`cli._slides_options`); picture defaults depend on the format (parser defaults `None`).
- **fpdf2** (`fpdf2>=2.7.9`, base dependency): pure Python, subset TrueType with ToUnicode,
  outlines, JPEG embedded as is. Not cairo (pycairo cannot load the bundled font file). Missing →
  `VidgenError(incomplete_install("fpdf2"))` before rendering.
- `make_slides_pdf(project, *, preview, mode, per_beat, overlays, dedupe, notes=False,
  title_page=False, paper="a4", image_format="jpeg", quality=85, max_width=None, output=None, jobs,
  force) -> PdfResult(path, bytes, pages, options: PdfOptions, width, height, bookmarks, thumbnail,
  deck)`, `write_pdf(deck, options)`; default `exports/<output>[_<variant>][_preview]_slides.pdf`
  (`_notes.pdf`). Slide pages: the video's aspect, long side 960 pt. Notes pages: A4 / Letter
  portrait with header, picture, meta line, narration, `page / total`. Title page: the existing
  thumbnail (not made here) or a typeset title. Outline: chapters (level 0) → slides (level 1).
  Info: `/Title`, `/Author`, `/Subject`, `/Keywords`, `/Creator vidgen <version>`, `/Lang`.
- Fonts: bundled Inter (§21), no fallback (missing glyphs dropped). JSON
  `jsonout.slides_pdf_document` (`output_format: "pdf"`). `slides_pdf.py` is not a render input.

## 57. Refinements (Step 54, readback check: speech to text)

- **Purpose**: the agent cannot listen; `vidgen readback` transcribes each beat's MP3 and compares
  it with the beat's spoken text.
- **Seam** (`vidgen.stt`): `STTProvider` (`name`, `check_available()`, `transcribe(path) ->
  Transcript(text, words: (TranscriptWord(text, start, end), ...), language)`),
  `get_stt_provider(project)`, `stt_settings(project)`. Constructing loads nothing.
  - `faster_whisper` (base dependency): model loaded on first use, `beam_size=5,
    word_timestamps=True, condition_on_previous_text=False, vad_filter=False`; audio decoded by
    vidgen (`render.ffmpeg.decode_mono(path, 16000)`); words keep `probability` (§78). Missing →
    `VidgenError(incomplete_install("faster-whisper"))`.
  - `elevenlabs`: `POST /v1/speech-to-text` (`scribe_v1`, `timestamps_granularity=word`), shared
    retry loop.
- **Config** `stt: {provider: faster_whisper | elevenlabs, model, language, device}`: model `small.en`
  for English, else `small` (`scribe_v1`); language = the video's subtag, `auto` = detect; `device`
  not in the cache key. Out of the fingerprint. Users: docs/CONFIG.md "Readback".
- **Normaliser** (`vidgen.textnorm`): `normalize_words(words, language) -> [Token(text, source)]`,
  `fold` (casefold, accents removed), number words for en / pt, acronyms joined. Both sides use it.
- **Comparison** (`vidgen.readback`): Levenshtein `align` (ties: more matches), WER over normalised
  spoken words; edits mapped to **written** words (`Spoken.word_groups()`) as `Edit(kind, expected,
  heard, written, said, errors, at, after, term, entry, suggestion)`; writing-only differences are
  dropped. `hard_term`, suggestions (pronunciation entry, `vidgen tts --force --beat ID`),
  `term_reports` (`consistent` = misheard in ≥ 2 beats). Flag: `wer > lint.rules.readback.max_wer`
  (0.1). Exit 0 whenever it ran.
- **Cache**: `build/readback/<sha1(json({audio: sha1(mp3), provider, model, language}))>.json`,
  content-addressed; `--force` redoes. The provider is created only when something needs
  transcribing.
- **CLI** `vidgen readback [--variant] [--beat ID ...] [--max-wer] [--force] [--json]`
  (`jsonout.readback_document`, version 1).
- **Lint rule** `readback` (last in `LINT_RULES`): reads cached transcripts only
  (`readback.cached_readback`), never transcribes.

## 58. Refinements (Step 55, generated images)

- **Param** `GenerateImage` (`vidgen.imagegen`, in `vidgen.api`; a string = the prompt): `prompt`,
  `negative`, `style`, `aspect` (`auto|landscape|portrait|square`), `seed`, `format` (§65). `image`
  takes exactly one of `path` / `generate`; any type with a top-level `GenerateImage` field opts in
  (`find_images`).
- **Config** `imagegen: {provider: openai, model: gpt-image-1, size: auto | WxH, quality, style,
  negative}` (+ §64, §65), a render input (picture vs placeholder). Users: docs/CONFIG.md "Generated
  images".
- **Request** (`image_request(project, generate) -> ImageRequest`): size from the model family and
  aspect (`auto` = the final format's orientation); text `<prompt>. Style: <words>. Avoid:
  <negative>.`; `STYLE_PRESETS`. **Key** = sha1(json{v: 1, provider, model, size, quality, seed,
  prompt: text})[:16]; files `assets/generated/<key>.png` + `<key>.json` sidecar. Content-addressed
  (changed = missing; old files are orphans, reported, never deleted); committed.
- **Seam**: `ImageProvider` (`name`, `check_credentials()`, `generate(request) ->
  GeneratedPicture(data, revised_prompt, cost)`, optional `check_requests`),
  `get_image_provider(project)`. `OpenAIImageProvider` (`POST /v1/images/generations`,
  `OPENAI_API_KEY` read at request time). Retries via `vidgen.httpapi.post_with_retries(url, data,
  headers, service, secret, ..., transient=)` (3, backoff 4 / 8 / 16 s or `Retry-After`, cap 60 s,
  timeout 240 s; never on quota / billing errors; key scrubbed).
- **Placeholder** (`imagegen/placeholder.py`) with the prompt, cached in `build/imagegen/`;
  `generated_image(project, generate, theme)` returns the PNG or the placeholder.
- **Only `vidgen imagegen` calls a provider** (`[--dry-run] [--force] [--scene] [--variant]
  [--json]`); validate warns about missing pictures and text-in-picture prompts
  (`imagegen_warnings`); render logs missing ones. `screenshot` has no `generate:`.

## 59. Refinements (Step 56, the author guide for AI agents)

- `CLAUDE.md` is for developers of vidgen, `AGENTS.md` for authors using it. The guide is package
  data `src/vidgen/data/guide/AGENTS.md`; the root `AGENTS.md` is a byte-identical copy (tested).
- Topics: a marker `<!-- topic: NAME (also: ALIAS, ...) -->` before each `##`. `vidgen.guide`:
  `GUIDE_FILE`, `GuideTopic(name, title, aliases, text)`, `guide_text()`, `guide_topics()`,
  `find_topic(name)` (unknown → `VidgenError`), `topic_lines()`. `vidgen guide [TOPIC] [--list]
  [--json]`. Not a render input.
- `tests/test_guide.py` keeps it true: commands and options exist, every built-in type / preset /
  action / lint rule / sound / bed is listed, every `yaml` block validates.

## 60. Refinements (Step 57, scene gallery)

- **`vidgen gallery [PROJECT] [--output DIR] [--types] [--formats] [--theme] [--clips |
  --no-clips] [--jobs] [--force] [--json]`** (`gallery.make_gallery`): every scene type from one
  sample at 16:9 and 9:16 into Markdown, default `docs/gallery` (committed).
- **Samples**: built-ins from the guide's `scenes` snippets (`guide_samples()`, groups from the
  first comment line, uses from the chooser, `chooser_uses()`); project types from their first scene
  (`project_samples()`); aliases are listed, not rendered (`GalleryType.alias_of`); `assets/` maps to
  `data/gallery/` stand-ins (`sample_asset()`).
- **Work project** `build/gallery/video.yaml` (640x360 @ 12 fps, variant `portrait`), always all
  samples so `--types` keeps fingerprints; `render_scenes(..., frames=1)`.
- **Media**: `media/<type>-16x9.png` / `-9x16.png`, GIFs 320 / 180 px, 6 fps, 32 colours, no
  dither (`export.write_gif`). Deterministic: workers run with `PYTHONHASHSEED=0` (unless set).
- **Pages**: `README.md` index and `<type>.md` (docstring, stills, GIFs, YAML, params table).
  Size limits: `BUDGET` (main gallery), `WEB_BUDGET` (web gallery, §123.1) and `ENTRY_MAX` per
  entry in `tests/test_gallery.py`; each GIF ≤ `gallery.CLIP_MAX_BYTES` 150 KB.
- **Placement rules from this pass**: `map` narrows portrait regional views (`_portrait_region`),
  `_misleading`, `_clear_spot`; `screenshot` / `video_clip` `steps[].focus` default `None` (`true`
  for a landscape picture ≥ 1.2:1 in a vertical frame); `video_clip` `fit: auto` (contain, or a
  near-square middle `cover` for a landscape clip without callouts in a vertical frame);
  `label_spot` `clearance`, `rivals` (< 0.75x distance blocks), `straight`, `side` only while clear;
  `tag_spot` clearance 0.2. Lint **`label_spacing`** (warning, `min_gap` 0.02 of the short side): a
  label on its own outline-less plate too close to another text.

## 60.1 Animated previews and showcases (Step 182)

Types drawn in a web page have their own gallery, `docs/gallery/web` (§123.1).

- The index shows each scene's GIFs (180 px high) in a `<picture>` with the still as
  `prefers-reduced-motion` source (`gallery.preview_html`).
- **GIF timing** (`gallery._write_clip`): start at `clip_start` (first frame reaching
  `CLIP_START_SHARE` 0.75 of the clip's largest change, ≤ `CLIP_START_MAX` 1 s); the final frame
  held `CLIP_HOLD` 2 s **at the start** (`write_gif(..., hold_first=True)`) so a static view shows the
  finished picture; over `CLIP_MAX_BYTES` 150 KB → `CLIP_FALLBACK_FPS` 5, then 4.
- **Showcases**: `gallery.SHOWCASES` of `Showcase(name, section, title, use)`, configs in
  `data/gallery/showcases/<name>.yaml` (one scene, id = name, `Showcase.config`), each its own work
  project `build/gallery/showcases/<name>/`; `section` = a guide group or its own (`SECTION_NOTES`,
  `GROUP_TITLES`). Names may not be scene types; `--types` accepts them; project runs skip them.
- The project README shows four gallery GIFs (tested).

## 61. Refinements (Step 58, `vidgen plan`)

- **`vidgen plan INPUT [--output] [--title] [--format] [--preset] [--language] [--force] [--json]`**:
  a draft project from Markdown or plain text. **No LLM, no network**: deterministic, byte-identical
  output (no times or absolute paths); decisions as `# plan:` comments, doubts as `# TODO:`.
- **Pipeline** (no manim): `outline.parse_outline(text, plain)` → blocks (`Heading`, `Paragraph`,
  `ListBlock`/`ListItem`, `Table`, `Code`, `Math`, `Image`, `Quote`; links incl. bare domains,
  `outline._DOMAIN`) → `plan.make_plan(blocks, PlanOptions) -> Plan(title, scenes:
  [PlannedScene(id, type, params, beats, duration, reason, todos)], language, chapters, assets,
  notes)` → `plan_yaml.plan_yaml` / `write_plan -> PlanResult(root, config, assets, created)` →
  `validate_all` (a draft with problems is still written, exit 1).
- **Rules**: H1 = title, next levels = sections / units; chapters (cards + `progress_bar`) when
  narration > `CHAPTER_SECONDS` 120 and ≥ 3 sections; a closing unit narrates an `end_card` with its
  links. `prose.py`: `split_sentences` (`LanguageRules.abbreviations`), `split_long` / `merge_short`
  (DPs on `phrase_break_cost`), `compress(text, max_words, language)` (heading 5, item 6, label 3,
  title 7, comparison point 4 words). Block → type cues (dated → `timeline`, numbered 2–8 →
  `process`, iconable nouns → `icon_grid`, numeric 2-column table → `bar_chart`, code, math, image,
  quote, arrows → `diagram`, vs / pros-cons → `comparison`, prominent numbers → `stat`, else
  `bullets` / `text_card`) live in `plan.py`.
- **YAML writer**: hand-written (comments above scenes, flow style ≤ 96 characters, literal code
  blocks, quoting rules); must load back to exactly `plan_config(plan)`.
- `examples/plan/video.yaml` is a golden file. `cli.scaffold_project(target, example)` is shared
  with `init`. Plan modules are not render inputs.

## 62. Refinements (Step 59, MCP server)

- **`vidgen mcp [--root DIR]`** / `vidgen-mcp`: stdio MCP server (`mcp>=1.19`, base dependency; SDK
  2.x `MCPServer`, else 1.x `FastMCP`; results via `CallToolResult.model_validate`).
- **Tools** (`mcp_server.build_server`): one per command (`guide`, `init`, `plan`, `validate`,
  `schema`, `list_*`, `storyboard`, `lint`, `render`, `tts`, `imagegen`, `readback`, `slides`,
  `thumbnail`, `export`, `gallery`, `translate_template`, `character_sheet` §69.16, `direct` §69.24,
  `screenplay` §69.25, `cast` §69.49), parameters mirroring options. Result = the command's `--json`
  document (compact) + images; `ok` false → `isError`. Argument errors are `ToolError`s.
- **A fresh subprocess per call** (`run_vidgen`: `sys.executable -m vidgen ... --json`, cwd = root,
  stdin devnull): Manim and the registries are process-global, the server must survive crashes.
  stderr → progress (≤ every 0.5 s) and a 30-line tail. Cancel kills the process group (POSIX) /
  `taskkill /F /T` (Windows). Rendering tools share one `anyio.Lock`.
- **Root policy** (`mcp_tools.RootPolicy`): resolved paths must be inside the root
  (`PathOutsideRoot`); options as `--name=value`; server files in `build/mcp/`;
  `VIDGEN_CONFINE_ROOT` set for every command (§63). Nothing returned holds environment values.
- **Cost guard**: `tts` / `imagegen` default `dry_run=True`; a real run needs `confirm_cost=True`
  (`mcp_tools.cost_refusal`); `readback` too when `stt.provider` is in `PAID_STT`; free TTS:
  §68.
- **Pictures** (`prepare_picture`): ≤ 1568 px, PNG unless > 800 KB (then JPEG q85); `images`
  (default 3, ≤ 8) from `image_offset`, `mcp_images` in the document.
- **Defaults vs CLI**: render / thumbnail / export preview; gallery to `build/mcp/gallery` without
  clips; `plan` takes `markdown_text`; `validate` checks all variants; `schema` needs `full=true` /
  `all_types=true` for the whole schema (use `scene=TYPE`).
- **Resources**: `vidgen://guide[/<topic>]`, `vidgen://schema`, `vidgen://gallery/index|<type>`.
- Every wrapped command has `--json` (`init`, `tts`, `imagegen` included); human `validate` checks
  all variants (`validate_all(keep_going=True)`). `mcp_server.py` / `mcp_tools.py` are not render
  inputs.

## 63. Refinements (Step 60, final review; version 0.2.0)

**Release notes of 0.2.0** (Steps 8–60 over 0.1; details in the sections named).

New:
- `--json` on every command, `vidgen schema`; self-checks `vidgen storyboard`, `vidgen lint`,
  `vidgen readback` (§57).
- Theme presets and type scales, bundled fonts, icons (`vidgen list-icons`), layout regions.
- Scene types `stat`, `chapter`, `comparison`, `table`, `timeline`, `diagram` / `flowchart`,
  `process`, `network`, `scatter`, `histogram`, `pie` / donut, `heatmap`, `code_walkthrough`,
  `equation_derivation`, `screenshot`, `video_clip`, `map`; per-beat actions (`reveal`,
  `highlight`, `dim`, `zoom`, `transform`, `callout`, `sfx`).
- Overlays (`lower_third`, `watermark`, `progress_bar`, `chapter_indicator`, `captions`, §41–§43);
  pronunciation, several voices, sound effects, music with ducking and loudness (§45–§48);
  transitions and `carry` (§49, §50).
- Outputs: MP4 chapters and YouTube list (§52), thumbnail, GIF / clip export (§53), language
  variants and translation files (§54), HTML / PDF decks (§55, §56), generated images (§58), the
  author guide (§59), the gallery (§60), `vidgen plan` (§61), the MCP server (§62).

Behaviour changes for 0.1 projects:
- **Incremental `vidgen render`**: `render_project(..., force=False)` renders only scenes for which
  `pipeline.current_render` is false (no usable render — `_usable_render`: format, audio mode,
  `--frames` stills — or `render.fingerprint` ≠ `scene_fingerprint`, §14) and reuses the rest
  (`RenderResult.reused`, scene `status: reused`). `--force` renders all; `--scene` renders those
  plus scenes without a usable render. Files read outside `assets/` are not tracked: use `--force`.
- **Narration plays 3 dB louder** (at the MP3s' level, §51); mono clip sound is panned to both
  channels at full level (`clips.clip_audio`: `pan=stereo|c0=c0|c1=c0`; `ClipInfo.channels`).
- **SRT cues** are cut at phrase boundaries and timed by word times (§43).
- The first render after upgrading renders every scene (new fingerprint inputs).

Rules set in 0.2.0:
- **Silent scenes render exactly their planned frames**: `NarratedScene.timeline()` waits to
  `round(d * fps)` frames from its start and `hold()` to `round(target * fps)`, the rounding of
  `VideoPlan` (silent part `max(duration - outro, 1 / fps)`).
- **`code` highlight band**: `scenes.code.readable_band` takes the strongest of `BAND_OPACITIES`
  (0.2, 0.16, 0.12, 0.1) keeping every syntax colour at `INK_RATIO` 4.6:1; below that, short colours
  mix towards `text`.
- **`post_render` after the thumbnail**, in a second extension session; hook data `thumbnail`
  (`Path | None`).
- **Confinement**: with `VIDGEN_CONFINE_ROOT` (`project.CONFINE_ENV`) set, `Project.load` requires
  every string under a `PATH_KEYS` key anywhere in the raw config (variants too: `path`, `logo`,
  `image`, `source`, `pronunciation_file`, `translations`, `extensions`, `output_dir`, `svg`, and a
  Kokoro `voice`'s `.pt` parts) to resolve (links followed) inside the folder
  (`confinement_problems`), else `VidgenError` "files outside the allowed folder"; non-path values
  under those keys resolve inside and pass.
- `translate-template --language` (alias of `--lang`); packaging with PEP 639 metadata (`license =
  "MIT"`, `license-files` incl. `THIRD_PARTY_NOTICES.md`; setuptools ≥ 77), `data/geo/LICENSE`.

## 64. Refinements (Step 61, OpenRouter image provider)

- **API** (base `https://openrouter.ai/api/v1`): `POST /images` (`{model, prompt, n, aspect_ratio,
  resolution, size, quality, seed, output_format, ...}` → base64 `data[].b64_json`, `usage.cost`
  in USD; explicit `size` with a mismatched ratio / resolution is a 400; 402 = no credits); public
  `GET /images/models` (`supported_parameters`) and `GET /images/models/{author}/{slug}/endpoints`
  (`pricing: [{billable, unit: image | megapixel | token | request, cost_usd, variant?}]`). Every
  request sends `openrouter.APP_HEADERS` (`HTTP-Referer` of the repository, `X-OpenRouter-Title:
  schu-video-generator`).
- **Config**: `imagegen.provider: openai | openrouter`, `imagegen.resolution`; `openrouter` needs an
  explicit `author/name` model, a quality in `OPENROUTER_QUALITIES`, not both `WxH` and a
  resolution; `resolution` with `openai` is an error. Users: docs/CONFIG.md "OpenRouter provider".
- **Request**: `size: auto` → `aspect_ratio` nearest the final format (`openrouter_aspect`) or
  `16:9` / `9:16` / `1:1` for another `aspect`; `ImageRequest.aspect_ratio`, `resolution`,
  `explicit_size`, `shape`, nominal `size` (`nominal_size`, 1K = 1024). No default quality.
- **Key**: `request_key(..., extra)` adds `{aspect_ratio, resolution}` for OpenRouter only (OpenAI
  keys unchanged, pinned). Sidecar adds `aspect_ratio`, `resolution`, `size`, `cost_usd`.
- **Provider** `imagegen/openrouter.py`: retries 429 / 500 / 502 / 503 / 504 / 524 / 529 (not 402 /
  4xx), key from `OPENROUTER_API_KEY`; `seed` only when listed; `output_format: png` when listed;
  `decode_response` → `RawPicture(data, media_type, cost, revised_prompt)`; JPEG / WebP → PNG
  (`openai.as_png`).
- **Before paying**: `check_requests` refuses unknown models, unsupported quality / resolution,
  models needing input pictures; notes for clamped ratios and unsent seeds; unreachable records
  refuse nothing. **Prices** (`openrouter.quote -> PriceQuote(cost, basis)`): image / request as
  is, megapixel × nominal pixels, token = unknown; matching tier, else untiered, else highest;
  several endpoints → highest. `lookup_models` (`LOOKUP_TIMEOUT` 5 s, stops at the first
  unreachable). Only the dry run looks prices up; `imagegen --json` has `price_basis`, `notes`,
  `problems`, `charged`. Not a render input. Live check: `tools/live_check_openrouter.py`.

## 65. Refinements (Step 61b, vector (SVG) generated images; data-policy errors)

- `GenerateImage.format: png | svg`; `imagegen.svg_model` (default `model`). svg needs `provider:
  openrouter` (`imagegen_problems`); `vector_warnings` (model not in `SVG_MODELS` / without
  "vector", SVG-only model for png, sanitiser warnings). svg requests: no quality / resolution,
  nominal 1K, path `<key>.svg`, key `extra` `format: svg` (PNG keys unchanged), body `output_format:
  svg`; `parse_response(body, format)` rejects a raster / vector mismatch; sidecar `format: svg`.
- **Sanitiser** (`vidgen/svgclean.py`): refuses > 20 MB, `<!ENTITY`, non-SVG roots, bad XML,
  nothing drawable; removes `script`, `foreignObject`, `image`, `filter`, `mask` / `clipPath`,
  `text`, external `use` / `href` (warnings), metadata, animation, `on*`, other `url()`; flattens
  gradient / pattern paints to one colour (else `#888888`); shared Manim fixes (`fix_manim_quirks`,
  `insert_box`, `view_box`); caps `MAX_SHAPES` 1500, `MAX_SEGMENTS` 60 000; `simplify` (% of the
  viewBox; `true` = 0.05). `CleanSvg(data, view_box, shapes, segments, warnings, notes)`.
- **Shapes** (`vidgen/vector_mobject.py`): `load_vector(path, *, height, recolor, theme, simplify,
  where) -> VectorPicture`; `SvgDrawing` is the base of `Icon` and `VectorPicture`; `recolor:
  theme` (`svgclean.theme_color`) maps near-greys to the nearest-lightness neutral, others to the
  nearest-hue theme colour keeping lightness. `vidgen.api` exports `VectorPicture`, `load_vector`.
- **`image`**: `.svg` paths; `draw`, `recolor` (`none | theme`), `simplify` only for vector
  pictures; `draw: true` = `DrawBorderThenFill`. Layout dump kind `vector`; `covered_text` treats it
  as a shape.
- **Data policy**: `openrouter.is_policy_error` (404 mentioning data policy / ZDR / guardrail /
  settings/privacy) → `policy_message(model, svg)` with the settings link and ZDR-capable models
  (`zdr_image_models`, from public `GET /endpoints/zdr`; 5 s). Not retried.

## 66. Refinements (Step 62, OpenRouter TTS provider; one provider per video)

- **API**: `POST /api/v1/audio/speech` `{model, input, voice?, instructions?, response_format: mp3 |
  pcm, speed?}` → raw audio (`audio/mpeg` or `audio/pcm` s16le 24 kHz mono) + `X-Generation-Id`;
  the cost comes from `GET /api/v1/generation?id=` (§67). Public model and endpoint lists give
  `supported_voices` and per-provider `pricing {prompt, completion}`.
- **Config**: `VoiceConfig.provider: elevenlabs | openrouter | kokoro` (`TTS_PROVIDERS`), `model`,
  `voice`, `instructions`, `speed` (0.25–4), also on `VoiceEntry`; `openrouter` requires `model`.
  Other providers' keys are ignored on `voice:` (`PROVIDER_VOICE_KEYS`), so a variant can switch
  provider by deep merge (its audio goes to `audio/<variant>/`).
- **One provider per video** (`voices.voice_provider_problems`, in `parse_config`): a named voice
  with another `provider`, or setting another provider's key, is a problem at `voices.<name>.<key>`.
- **Provider** `tts/openrouter.py`: `httpapi.post_with_retries(..., response_headers=)`; no
  context texts, no `language_code`; `pcm` for `PCM_ONLY_PREFIXES` (`google/`) and after a 400
  naming it; `as_mp3` converts WAV / PCM with ffmpeg (`convert_to_mp3`, 128 kb/s). Key via
  `imagegen.openrouter.read_api_key("tts")`.
- **Hash**: `sha1(json.dumps({provider, model, voice, instructions, speed}, sort_keys=True,
  ensure_ascii=False) + "|" + spoken_text)`; ElevenLabs hashes unchanged.
- **Prices** (`tts.run.price_tts`): `character_rate` = highest `prompt` over endpoints, unknown when
  any `completion` is non-zero or offline; `TTSPlan` carries `rates`, `notes`, `problems`,
  `price_notes`, `charged`, `beat_cost`, `cost`. ElevenLabs is never estimated.
- **Checks**: `tts.tts_warnings` (validate, offline) from `data/openrouter/tts_models.json`; the dry
  run / run use the live list (unknown model refused before paying; `INSTRUCTION_PREFIXES`,
  `SPEED_PREFIXES` notes). Policy 404s → `policy_message` with `zdr_tts_models`. No alignment: word
  times are estimated. `tts --json` adds `provider`, `estimated_cost`, `prices`, per-beat `model`,
  `provider_voice`, `instructions`, `speed`; `voice_id` `null` for non-ElevenLabs videos.

## 67. Refinements (Step 63, review of Phase F)

- **Cost lookup** (`OpenRouterTTSProvider.reported_cost(timeout, waits=COST_WAITS)`): records are
  written late, so 404 / transient / no numeric `total_cost` are retried after `COST_WAITS` 1, 2, 4,
  8 s (deadline `sum(waits) + 2·timeout`); 400 / 401 / 403 are not. `cost_problem` says why;
  `run._reported_cost` prints `cost not reported by openrouter yet (<why>; see
  https://openrouter.ai/activity)`. Never fails the run. `conftest.LIVE_ZDR_404` pins a real
  policy body.
- **Key hygiene**: `httpapi.scrub` also removes the `repr`-escaped key; `httpapi.get(..., secret=)`
  scrubs and wraps `http.client.HTTPException`; `read_api_key` refuses keys with spaces, control or
  non-ASCII characters without quoting them.

## 68. Refinements (Step 65, local Kokoro TTS; optional extra)

- **Library**: `hexgrad/Kokoro-82M` v1.0 (Apache-2.0), weights `kokoro-v1_0.pth`, languages `a b e f
  h i j p z`; `KPipeline` downloads weights and voices through the HF cache on first use; only `a` /
  `b` yield token times. espeak-ng comes from the `espeakng-loader` wheel; `j` / `z` need
  `misaki[ja]` / `[zh]`.
- **Config**: `provider: kokoro`, `KOKORO_VOICE_KEYS = (voice, speed, lang, device)`, `VoiceConfig.lang`
  (`a|b|e|f|h|i|j|p|z|null`), `device: cpu|cuda|auto = cpu`. Users: docs/CONFIG.md "Kokoro on this
  computer".
- **Resolution** (`kokoro_voices.resolve`): `lang` = given, else the voice's first letter, else the
  video language (`en` a, `en-GB/IE/AU/NZ` b, es e, fr f, hi h, it i, ja j, pt p, zh z; none a);
  `voice` = given, else the language's `default_voice`; `speed` 1. A language without a Kokoro voice
  is a config error (`voices._kokoro_language_problems`). `audio_fields` leaves out `device`
  (`RUNTIME_FIELDS`).
- **Provider** `tts/kokoro.py` (`KokoroProvider`, `timings_included = True`): nothing imports
  kokoro / torch before the first beat. `check_installed(lang)` → `VidgenError` telling to reinstall
  (Python > 3.12: use 3.12). One `KokoroEngine` per process (`shared_engine`), pipelines share one
  `KModel`. Audio → `pcm16` → MP3 (`convert_to_mp3`, 24 kHz mono); token times →
  `alignment_from_tokens` (`None` under 80 % timed), stored as `.align.json`. stdout is redirected
  to stderr while it runs (`quiet_stdout`); errors explained by `explain()`.
- **Hash**: `sha1(json.dumps({provider: kokoro, model: hexgrad/Kokoro-82M, weights:
  kokoro-v1_0.pth, voice, lang, speed}, sort_keys=True, ensure_ascii=False) + "|" + spoken_text)`
  with resolved values; not device or package version; `.pt` voices by name.
- **Run**: `run_tts` uses `synthesize_timed` when `timestamps` or `timings_included`; `kokoro.run_notes`
  (free, device, pending download via `hf_cache_dir()`); cost 0 (`KOKORO_PRICE_NOTE`). MCP `tts`
  needs no `confirm_cost` when the loaded project's provider is in `FREE_TTS = ("kokoro",)`
  (`mcp_server.tts_provider`).
- **Validate** (offline): `kokoro.voice_warnings` against `data/kokoro/voices.json`, language
  mismatches, `timestamps` without timings, `kokoro.install_warnings`.
- **Packaging**: base dependencies `kokoro>=0.9.4` and `misaki[zh]>=0.9.4` with `python_version <
  '3.13'`; `misaki[ja]` is not one (no pyopenjtalk wheels). Nothing of Kokoro is bundled.
## 69. Characters (Step 67, character model: vector parts with pivots)

`cartoon/character.py`. The generator (§69.1) and SVGs (§69.2) produce `CharacterPart` lists;
poses (§69.3) are `PartPose` tables applied with `set_state`; lip sync and blinks (§69.4–69.5)
swap shapes; the `stage` (§69.6) places characters by `feet()`.

- **Parts**: `PART_NAMES = body, legs, leg_left, leg_left_lower, leg_right, leg_right_lower,
  arm_left, arm_left_lower, arm_right, arm_right_lower, head, eyes, brows, mouth, accessory, tail,
  antenna, cape, cheeks, bristles` (§69.26, §69.48, §69.58, §69.59). `REQUIRED_PARTS = body,
  arm_left, arm_right, head, eyes, brows, mouth` (`Character(..., required=)` overrides; an SVG
  needs only `body`). Legs are one `legs` part or `SINGLE_LEG_PARTS`. `CharacterPart(name, shapes,
  pivot, parent=None, order=None)`: `shapes` maps names to `VMobject`s, the first is the rest shape.
  Parents default to `DEFAULT_PARENTS` (body is the root; a missing default parent is replaced by
  its own parent; no cycles); draw order to `DEFAULT_DRAW_ORDER` (ties by `PART_NAMES`), so facing
  right the character's right arm is behind the body. `arm_left` / `arm_right` are the
  character's own sides. Bad part sets raise `VidgenError` naming the character and parts.
- **Units**: origin between the feet, `y` up, top = 1. `Character(parts, name=, height=3.0,
  facing="right", voice=None)` scales to `height` Manim units; `feet()` is the origin on screen.
- **Redraw**: one frozen `PartPose(angle, scale, shift, shape)` per part (degrees
  counterclockwise as drawn facing right; scale about the pivot; shift in character units).
  `refresh()` sets each part's points to `screen · mirror · world(part) · rest_points`,
  `world(part) = world(parent) · pose(part) · overlay(part)`, `pose = T(shift) · T(pivot) · R · S
  · T(-pivot)`: a pose moves its children only, and every redraw starts from the rest shape (no
  accumulated rounding). Live styles are not touched. `parts[name]` holds one live child per
  shape for the character's whole life; only the shown one has points (§69.22).
- **Placement**: `submobjects[0]` is an invisible three-point anchor (feet, +0.05 right, +0.05
  up) inside the figure's box; Manim's `shift` / `scale` / `rotate` / `move_to` move it and
  `refresh()` reads the placement back from it. No Manim transform is overridden.
- **Facing**: `face("left")` mirrors about the feet's vertical line; `turn()` toggles; draw
  order and part names are kept. `face("front")`: §69.44.
- **API**: `set_part(part, angle=, scale=, shift=, shape=)`, `swap`, `reset(part=None)`, `face`,
  `turn`, `state()` → `CharacterState(facing, parts)`, `set_state`, `pose_of`, `shape_names`,
  `parent_of`, `has_part`, `draw_order`, `pivot(part)`, `parts`; chainable; `copy()` is deep.
  Animate via updaters or `PoseChange`, not `.animate.set_part` (straight chords, not arcs).
- **Strokes**: drawn at `OUTLINE_WIDTH = 4` for `REFERENCE_HEIGHT = 3`; `Character.__init__`
  scales rest strokes by `height / REFERENCE_HEIGHT`, at least one pixel (`100 * frame_height /
  pixel_height`), so outlines are a fixed fraction of the character at any resolution. A later
  Manim `scale()` does not scale strokes.
- **Config**: top-level `characters: list[CharacterEntry(name, voice, look: CharacterLook,
  colors: CharacterColors)]`; `CharacterColors(skin = secondary, clothes = primary, outline =
  features = CHARACTER_INK #1F2430, hair = accent, accessory = highlight)`. A list, not a mapping,
  so a duplicate name is an error rather than YAML silently keeping the last.
- **Checks**: `voices.voice_reference_problems` covers `characters[k].voice`. `cartoon/cast.py`
  (no manim): `character_names`, `find_character` (did-you-mean), `character_color_problems`
  (`cli.project_problems`), `check_character_name`.
- **`CharacterName`** (`scene.py`, exported): an identifier checked against the active project's
  `characters:` only when the validation context has a theme and a project (like `IconName`); no
  enum in `vidgen schema` (the schema is per video).
- **`character(name, height=3.0, facing="right")`** (exported): the project's character in the
  current theme (`build_character(entry, theme=, height=, facing=)`).
- **Fingerprint**: `characters` is in the config part of every scene's fingerprint (editing one
  re-renders all scenes). Layout dump: one object of kind `character` (§69.6).

### 69.1 The character generator (Step 68)

`cartoon/generator.py`: `generate_parts(look, colors, *, outline_width=OUTLINE_WIDTH)`; `colors`
maps `COLOR_KEYS` (`skin, clothes, outline, features, hair, accessory, trim`). Option sets: §69.47.

- **Proportions**: `resolve_proportions(look)` (no drawing). With `look.seed`, each proportion is
  multiplied by `0.92 + 0.16 × random.Random(seed).random()` in field order; only `random()` is
  used because Python guarantees its sequence across platforms (`uniform` is not). No seed: none.
- **Drawing**: parts are scaled about the feet so the tallest shape tops at 1. Hair, ears and
  nose are inside `head`; `scarf` / `bag` inside `body`; `glasses` / `hat` form `accessory`.
  Shape names are the same for every look (eyes `open` / `closed`, mouth `smile` / `open` and
  visemes `A E O U M F L W`). Every shape is a primitive; no option imitates a known character.
- **`vidgen character NAME [PROJECT] [--variant NAME] [--png [FILE]] [--facing right|left]`**
  (`cli.cmd_character`): prints `cast.character_lines` (voice, look, colours with hex); `--png`:
  `still.write_character_png`, shorter side 720 px, default `exports/character_<name>.png`. No
  `--json` (`character-sheet`, §69.16, is the agent tool).

### 69.2 Characters from SVG files (Step 69)

`look: {svg: FILE}` (relative to the project, no other `look` key); `cartoon/svg_look.py`;
`build_character(entry, root=)`.

- **Splitting** (`split_character_svg`, `read_character_svg`; no manim): after
  `svgclean.sanitize_svg` (§65), each drawn element belongs to the nearest enclosing element
  whose id names a part (`part_key`: `<part>` rest, `<part>_<shape>` another shape; longest part
  name wins). Unowned shapes go to `body` unless hidden in the file (then dropped). Rest names
  `REST_SHAPE_NAMES` (`eyes` → `open`, `mouth` → `smile`, else `rest`). Each (part, shape) becomes
  its own document (others removed, its ancestors un-hidden, viewBox kept).
- **Pivots**: `data-pivot="x y"` in viewBox units (rest element's wins), else `default_pivot`
  from the rest box; `pivot_warnings` for `TURNING_PARTS` without one.
- **Errors** (`VidgenError`): unreadable file, sanitiser refusal, duplicate (part, shape), bad
  `data-pivot`, no body. **Warnings**: near-miss ids, a non-rest shape shown in the file, an empty
  part element.
- **Shapes** (`svg_character_parts`): `vector_mobject.svg_shapes` per document, aligned by viewBox
  top-left (Manim flips y about each drawing's centre); the rest shapes' union box defines
  character units (x = middle of `legs`, else `body`). Strokes via `set_svg_stroke` at the
  `REFERENCE_HEIGHT` factor. Draw order = file order. The SVG's colours are kept (`colors:` unused).
- **`cast.ACTION_NEEDS`** (action → alternatives of parts or `part.shape`; `unavailable_actions`,
  `missing_needs`): `say` mouth, `blink` eyes.closed, `look_at` head, `emote` eyes / brows /
  mouth, `gesture: point` / `wave` an arm, `shrug` both arms, `nod` / `shake_head` head. Actions
  declare `Action.character_needs()` and skip what a character lacks.
- **Validate**: `cast.character_look_problems` / `character_look_warnings` (sanitiser and split
  warnings, guessed pivots, unused `colors`, one-shape mouth, unavailable actions).
- **Fingerprint**: an SVG under `assets/` is in every scene's fingerprint; elsewhere it is not.
  Example: `examples/svg_character`.

### 69.3 Poses and expressions (Step 70)

- **Tables** (`cartoon/poses.py`): `POSES` (`stand, pointing, waving, thinking, shrug,
  arms_crossed, sitting`) and `EXPRESSIONS` (`neutral, happy, sad, angry, surprised, worried,
  thinking` and §69.59's), name → part → `PartPoseEntry(angle, scale, shift, shape)`. A pose sets
  `POSE_PARTS` (`body, legs, arm_left, arm_right, head, accessory`), an expression
  `EXPRESSION_PARTS` (`eyes, brows, mouth, cheeks, bristles`), so one of each combines; unnamed
  parts of the group return to rest. Values are relative to the rest drawing. `shape` is a list:
  the first the character has (`chosen_shape`), else rest; missing parts are skipped.
- **Character**: `Character(..., poses=, expressions=)`; `names(kind)` (built-in, then own; an own
  entry with a built-in name replaces it), `posed_state(pose=None, expression=None)`, `set_pose`,
  `set_expression`; unknown names raise from `poses.find_entry` with did-you-mean.
- **Own entries** (`characters[].poses` / `.expressions`): a part outside the group, zero scale
  or unknown key is a config error; `cast.character_pose_problems` / `_warnings` check shapes and
  parts without drawing (`cast.GENERATED_SHAPES`, kept equal to the generator's by a test).
- **`PoseChange(character, *, pose=None, expression=None, state=None, facing=None,
  lag_ratio=0.15, part_rate_func=smooth, **animation_kwargs)`** (`cartoon/transition.py`,
  exported): target resolved at creation, start at `begin` (which calls `end_blink()`). Each
  changed part eases in its own window (`part_windows`, `PART_NAMES` order, staggered by
  `lag_ratio`, last ends at 1); `blend_poses` is linear and switches shape and facing at halfway;
  redrawn with `set_state` per frame, so parts sweep arcs. `state=` with `pose` / `expression` is
  a `TypeError`.

### 69.4 Lip sync: viseme tracks (Step 71)

`cartoon/visemes.py` (no manim) builds and stores tracks; `Character.lip_sync` plays them.

- **Visemes** (`VISEMES`): `rest, A, E, O, U, M, F, L, W` (Preston Blair groups; also the SVG
  mouth shape names). `VISEME_SHAPES` lists each viseme's shapes by preference; none present
  shows the rest shape.
- **Phonemes → visemes**: `PHONEME_VISEMES` (IPA and misaki's diphthong letters; marks, `h`, the
  glottal stop and unknown symbols take no time); `phoneme_units` weights vowels 2, consonants 1,
  a space `rest` 0.5. Fallback `letter_units` (digraphs, then letters; a silent final `e` per
  `language_rules(...).silent_final_e`).
- **Sources** (`SOURCES`): `kokoro` (`KokoroProvider.last_phonemes` from `synthesize_timed`), else
  per word through `text_g2p(language)`: the first loadable of `G2P_BACKENDS` — `misaki`
  (English only when `en_core_web_sm` is importable, since misaki would pip-install it; other
  languages when `espeakng_loader` is), `espeak` (`espeak-ng` on `PATH`) — else `letters`.
  Nothing is installed; tests mock them.
- **Timing** (`TIMINGS`): Kokoro token times, else `speech.beat_word_times` (`alignment`,
  `speech`, `estimate`); units share their word's time by weight; `rest` fills the gaps, 0 .. the
  MP3's length.
- **Merge rule** (`merge_short_cues`, `MIN_CUE_SECONDS = 0.07`): equal neighbours join; shortest
  first, a cue under the minimum goes to its longer neighbour (earlier on a tie), except a short
  `M` is lengthened from its longer neighbour if that stays ≥ the minimum. Cues stay contiguous.
- **Storage**: `.visemes.json` next to the MP3: `{version: 1, text, audio_sha1, source, timing,
  cues: [[start, end, viseme], ...]}` (4 decimals); valid only while the MP3's sha1 and spoken
  text match. `vidgen tts` writes it for voiced or copied beats when the video declares
  `characters:`, and writes missing tracks of up-to-date beats; the beat's `.hash` is unchanged.
- **Reading**: `beat_visemes(project, beat_id, duration=None) -> VisemeTrack(cues, source,
  timing)` (`at(seconds)`, `duration`): the stored track, else built in memory and not written (a
  render never changes its own fingerprint inputs).
- **Fingerprint**: with `characters:`, each scene's fingerprint has `visemes` (stats of every
  beat's `.visemes.json` and `.align.json`); without characters the shape is unchanged.
- **Character**: `viseme_shape`, `show_viseme`, `lip_sync(track, *, start=0.0, clock=None)` (a
  plain-method updater; time = `clock()` or `start` + frame `dt`s), `stop_lip_sync`,
  `lip_sync_track`, `sync_mouth`. The viseme is a layer over the mouth's pose (`_spoken`): the
  pose's scale and angle stay (a flipped `sad` mouth speaks flipped); `rest` shows the pose's
  shape. No mouth: no-ops. Manim suspends updaters during an animation on the mobject, so
  animations call `sync_mouth()` each frame to keep a clocked mouth in step.
- **API**: `VISEMES`, `VisemeCue`, `VisemeTrack` exported. `audio_duration` is in `speech.py` (no
  manim).

### 69.5 Automatic life: blinking and idle motion (Step 72)

Breathing, head sway and blinks as one updater-driven layer over the poses.

- **Schedule** (`cartoon/idle.py`, no manim): blink gaps uniform in `BLINK_GAP_SECONDS = (2, 6)`
  from `random.Random(seed)` (`random()` only), each `BLINK_SECONDS = 0.15`; seed default
  `idle_seed(name)` (CRC-32), so characters do not blink together. `breath_scale` and
  `sway_angle` are periodic and 0 at the clock's start (a still at time 0 is the plain pose).
- **Idle clock**: advances by `dt` in the updater, so it stops during any animation on the
  character. `PoseChange`, `Walk`, `Gesture`, `Jump` end a running blink at `begin`.
  `blink_times(seed, duration, *, pose_changes=())` gives the schedule in scene seconds without
  drawing; `IdleClock` is the running state (a test checks both agree frame by frame).
- **Character**: `start_idle(seed=None)` (a plain-method updater, so `copy()` gets its own clock),
  `stop_idle`, `end_blink`, `is_idle`, `shown_shape(part)`. The layer is `_overlays` (body scale,
  head angle, eyes `closed`), applied after the pose; `state()` / `set_state()` hold poses only,
  and the mouth is never touched. No `head`: no sway; no `eyes.closed`: no blink.
- **Config**: `characters[].idle: bool = True` (`build_character` starts it); stage `idle: false`
  stops it. A `Character` built from parts does not idle until `start_idle()`.

### 69.6 The `stage` scene type (Step 73)

`scenes/stage.py`; geometry in `cartoon/stage.py` (no manim). Keys: docs/CONFIG.md#stage.

- **Geometry**: x is a fraction of the stage width, the ground line a fraction of the frame
  height, sizes fractions of the frame's shorter side (8 units in every aspect). `MARKS` =
  `far_left 0.1, left 0.25, centre 0.5, right 0.75, far_right 0.9` plus the stage's own (own
  wins); `mark_x` raises `ValueError` with did-you-mean. Depth 0..1: `depth_scale(d) = 1 - (1 -
  FAR_SCALE) d` (`FAR_SCALE = 0.55`), feet `FAR_RISE = 0.12` frame heights higher at depth 1.
  `stage_layout(items, marks=, ground=, size=, frame_width=, frame_height=, stage_width=)`:
  `StageItem(name, kind, at, depth, scale, lift=0)` → `StagePlacement(name, kind, index,
  x_fraction, depth, feet, height)` in draw order (deeper first, ties in list order); `kind`
  `character` or `prop`. `facing_towards_centre(x)`.
- **Params** (`Stage.Params`): `image` or `generate` (a top-level `GenerateImage`, so `vidgen
  imagegen` finds it) or `background` (colour or vertical gradient), mutually exclusive;
  `ground` (0..0.6, 0.2), `ground_color` (band up to `ground_top`, §69.22; default `surface`
  without a picture, none with one), `marks`, `size` (0.45), `idle`, `cartoon_motion`,
  `characters: list[StageCharacter]` (`name`, `at`, `depth`, `scale` (0, 3], `facing` `auto |
  right | left`, `pose`, `expression`). Duplicate names and unknown marks are params errors;
  `validate_project` checks images and `cast.pose_name_problem` (exported).
- **Construct**: each character is `character(name, height=placement.height, facing=)`, posed
  and moved so `feet()` is at the placement. One reveal step fades in backdrop and characters
  (registered back to front, which is Manim's draw order); `finish()` fades out (0.5 s).
- **Targets**: characters by name (`target_patterns = ("<character>",)`), so generic actions work
  on them. `Stage.cast` (name → `Character`, back to front).
- **Layout dump / lint**: a `Character` is one object of kind `character` (box over drawn parts,
  anchor excluded); the picture or colour is `background`, the band `ground`; lint names it
  `character 'pip'` and `lint_ignore` matches that.
- **Guide and gallery**: the guide's `# cartoons` block is a whole config (`characters:` +
  `scenes:`); `gallery.guide_samples` reads one sample per scene with `Sample.characters`.

### 69.7 Parallax layers and the camera on a stage (Step 74)

- **Layer math** (`cartoon/stage.py`): layers are drawn for the home view (stage centre, zoom
  1). `layer_transform(factor, camera_center, zoom) -> (scale, (dx, dy))` puts a home point `b`
  at `k b + c (1 - factor k)`, `k = zoom ** (factor - 1)`: factor 1 moves with the stage, 0 is
  fixed on screen, < 1 far, > 1 near. `layer_half_extent(..., max_zoom=MAX_ZOOM 8)` is the half
  size that never shows an edge for views inside the stage at zoom 1–8. `LAYER_PLACES =
  (background, middle, foreground)`, `DEFAULT_FACTORS` 0.3 / 0.6 / 1.4.
- **Camera bounds** (`camera.py`): `view_center_within(bounds, center, width, height)`;
  `NarratedScene.camera_bounds()` is the frame, `Stage`'s its width × frame height; `zoom` clamps
  with it.
- **Stage params**: `width` (1–4 frame widths; a reframing stage narrower than 16:9 counts in
  16:9 widths, §69.30), `camera_at`, `layers: [StageLayer{name, place, factor, image | shapes,
  bottom}]` (names default `<place>_layer`, `_2`...; `LayerShape` `rect`, `ellipse`, `triangle`,
  `hills`). Draw order: backdrop, background and middle layers, ground band, characters,
  foreground layers. `Stage.layers`; each layer mobject is named after it.
- **Moving layers**: home points are kept (`_Parallax`); `_move_layers`, registered with
  `NarratedScene.add_camera_listener` when a factor is not 1, sets `home × scale + shift` each
  frame (from home points, so a layer's own animation never shifts it).
- **Camera driver**: `follow_with_camera(x_of)` (`None` stops; `camera_following`) and
  `add_camera_listener` share the scene updater `_camera_step` (follow first, then listeners).
  Scene updaters run after all mobject updaters and are never suspended, so layers never lag.
  While following, `get_moving_mobjects` returns every mobject (§69.20).
- **`pan`** (`scenes/actions.py`; 1.5 s, reversible, no target needed, moves the camera): `to` a
  mark / x of `camera_bounds` or a target (exactly one); ends a `follow`; keeps view size and y;
  `cut: true` jumps (§69.30). Marks resolve via classmethod `NarratedScene.camera_place(params,
  place)`, checked at validate by the hook `Action.scene_problems(scene_cls, params)`.
- **`follow`** (1.0 s, reversible; one target): pans to the target (`_MoveThenFollow`, which
  starts following in `clean_up_from_scene`) and follows its x to the scene's end (a `Character`
  by `feet()` x); `until` stops unless a later `follow` took over.
- **`zoom` revert** returns to the view before the zoom (`camera_view` / `move_camera_back`).
- **Lint**: `StillContext.camera_moved`; `off_frame` and `safe_area` skip such stills.
- **Limits**: no vertical pan; layers are not targets; a near image layer zoomed in low can show
  a sliver below its `bottom`.

### 69.8 Props (Step 75)

- **Built-in props** (`cartoon/props.py`): the set is `PROP_KINDS`, heights relative to a
  character in `PROP_HEIGHTS` (SVG `SVG_PROP_HEIGHT` 0.5), colours `PROP_COLORS` (`main`,
  `detail` theme tokens), `PROP_LIFTS` (`cloud`, `sun`, `moon` hang 0.5 frame heights up). Drawn
  in prop units (feet at origin, top 1) from primitives in `CHARACTER_INK` outline; all original.
  Gallery image: `still.write_props_png` → `docs/gallery/media/props.png`.
- **`Prop(VGroup)`** (`name`, `kind`, `facing`, `feet()`): `draw_prop(kind, *, height, theme,
  name=None, main=None, detail=None, facing="right", character_height=None)` scales strokes like
  a character of `character_height` (`scale_strokes` / `one_pixel_stroke`); `svg_prop(path, *,
  height, name, theme=None, recolor="none", facing="right", where=None)` (sanitised; stands on
  its viewBox bottom).
- **Stage `props`** (`StageProp`: `prop` or `svg`, `name`, `at`, `depth`, `scale` (0, 5], `lift`,
  `facing`, `color` / `detail`, `recolor`; a string is a built-in name). Names default to the kind
  (SVG: file stem), numbered from the second (`tree_2`); duplicates and names clashing with
  characters are errors. `Params.items()` lists props before characters, so at equal depth a
  character is in front. `Stage.props`; `target_patterns = ("<character>", "<prop>")`.
- **Layout dump**: kind `prop` (`prop 'tree'`). An SVG prop outside `assets/` is not in the
  fingerprint.

### 69.9 Particles (Step 76)

- **Model** (`particles.py`, no manim): `PARTICLE_KINDS = rain, snow, sparkles, dust, confetti,
  smoke, bubbles, leaves, streaks` (§69.38, rain on a stage §69.39), each a `ParticleKind` in
  `KINDS`. `particle_seeds` draws once from `numpy.random.default_rng([seed, kind index])`;
  `particle_states(seeds, t, width, height)` is a pure function of time (positions wrapped in
  0..1, faded near edges). `particle_count` = count × density × area share, at most
  `MAX_PARTICLES` 300, half (`PREVIEW_SHARE`) at preview, at least 1.
- **Drawing** (`particle_field.py`): `ParticleField(VGroup)`; `draw_at(now)` uses the scene's
  `renderer.time` and the camera's current view, so a frame's look is independent of updater
  calls and particles stay steady through camera moves. `suspend_updating` is a no-op;
  `fade_out_animation()` (used by `helpers.fade_out`) fades while particles keep moving.
  `particle_field(scene, kind, settings)`; `ParticleSettings`: `density` (0, 4], `area`,
  `color`, `seed`.
- **Preview**: `NarratedScene.is_preview`, set by `render_scene`; preview and final builds use
  separate folders, so no fingerprint entry.
- **`particles` action** (`scenes/particles_action.py`; 0.6 s fade out, reversible,
  `until_next_beat`, `scene_targets = False`, so the runner resolves no targets): `kind`, `keep`,
  settings; whole scene: `keep: true` on the first beat. Stage param `particles:
  list[StageParticles]` (drawn in front of everything; `Stage.particles`).
- **Lint**: kind `particles`; `off_frame` skips it. Not an overlay because overlays composite per
  distinct state (§41) and particles change every frame.

### 69.10 Shared style for generated backgrounds (Step 77)

`cartoon_style:` (top level, default none): style words added to every `generate:` prompt of
scene types with `NarratedScene.uses_cartoon_style = True` (`Stage`). `find_images` reads the
attribute from the registered class and `generated_picture` uses it at render, so both resolve
the same request. `image_request(project, generate, *, cartoon=False)` joins the style words and
`cartoon_style_words` with `"; "`: `<prompt>. Style: <style>; <cartoon style>. Avoid:
<negative>.` (`style: none` drops only the style words). Cache key formula unchanged (§58); keys
of scenes without it stay identical (pinned by tests). `cartoon_style` is in the dumped config,
so changing it re-renders every scene. User docs: CONFIG.md "Generated backgrounds".

### 69.11 Acting actions, part 1: speaking and looking (Step 78)

`scenes/acting.py` (against `vidgen.api` only).

- **Who speaks** (`cast.beat_voice`: beat, scene, `default`; `speaking_characters`):
  `Stage.narrate` lip-syncs them for the beat and stops after `d + pad` unless a later lip sync
  took over; in a beat with a `say` action, `say` picks the speakers. `shared_voice_warnings`.
- **Timing**: `NarratedScene.beat_clock()` (time since the current beat started) and
  `speak(character)` = `lip_sync(beat_visemes(current_beat), clock=beat_clock())`, so the mouth
  follows the audio whatever else runs.
- **`_Acting` base**: targets must be declared characters (`scene_problems`; at render skipped);
  `_change` / `_undo` restore only the parts and facing changed.
- **Actions**: `say` (0.4 s; `bubble` false / true (beat text) / text, `color` `#FFFFFF`, `size`
  `caption`; `say_problem` without a voice; `revert` stops only its own lip sync), `look_at` (0.5
  s; `to` a target, mark / x, or `camera`; `cartoon/acting.py` `look_pose` caps head tilt at
  `LOOK_MAX_DEGREES` 20, `camera_look`), `turn` (0.4 s), `emote` (0.5 s), `pose` (0.8 s),
  `react` (0.6 s, `until_next_beat`; `expression` and / or `pose`). All reversible; several on
  one character play in sequence.
- **Speech bubble** (`speech_bubble`): uses the public callout helpers `callout_label`,
  `label_spot`, `label_bounds`, `label_avoid`; plate and tail are one `Union` (both
  counterclockwise, since Manim's `Union` joins only same-direction paths); a `Callout` of kind
  `label`; `follow_speaker` keeps it at its offset from the speaker's feet.
- **Validate**: `cast.acting_warnings(project)` warns per action use on a character lacking its
  `ACTION_NEEDS` parts. A `say` by a character whose voice is not the beat's follows the beat's
  audio.

### 69.12 Acting actions, part 2: moving (Step 79)

`scenes/moving.py`: `walk_to`, `enter`, `exit`, `gesture`, `jump` (none reversible).

- **Motion** (`cartoon/acting.py`, no manim): `walk_seconds(distance, speed=WALK_SPEED 2.5)`
  with even ease-in / out over `WALK_EASE` 0.15 of the time; `walk_cycle` (a step per
  `STEP_LENGTH` 0.35 heights; scaled by the walk's amplitude, so a walk starts and ends in the
  pose); `offstage_x`, `enter_path`, `exit_path`; `GESTURES` (point, wave, shrug, nod,
  shake_head) with `GESTURE_SECONDS`, `gesture_moves`; `jump_lift` (`JUMP_HEIGHT` 0.4 heights,
  `JUMP_SECONDS` 0.6).
- **Animations** (`cartoon/transition.py`, exported): `Walk(character, x, *, start_x=None,
  park_x=None, speed=WALK_SPEED)`, `Gesture`, `Jump`: each redraws from its start state and ends
  in it; `Character.character_height` scales steps and jumps.
- **Actions**: `walk_to` (`to`, `speed` (0, 20]); `enter` (`side`, `to` default `Stage.homes`,
  starts beyond the view edge); `exit` (ends beyond the view edge, then parks beyond the stage
  edge; a `follow` of it stops); `gesture` (`to`; needs `gesture: <kind>`); `jump` (`height` (0,
  2]). Characters an `enter` names (`NarratedScene.action_uses`) start parked off stage.
- **Timing**: hook `Action.run_time_for(scene, targets) -> float | None` gives the natural run
  time when due (unless `run_time` is set or the phase undoes); the runner still shortens to fit
  the beat.
- **Camera**: `Action.alters_targets` (`False` for `pan`, `follow`): such targets do not split
  batches, so a `follow` plays with a walk; `_MoveThenFollow` re-aims each frame.
- **Lint `walk_overlap`** (`lint/cartoon_rules.py`, `min_overlap` 0.25): a character that walked
  in the beat (`Character.walked_in`) ending on another. Depth while walking: §69.44.

### 69.13 Animation principles built in (Step 80)

`cartoon/motion.py` (no manim): anticipation, squash and stretch, overshoot and settle,
follow-through as pure functions of time inside `PoseChange`, `Walk`, `Gesture`, `Jump`.

- **Setting**: `cartoon_motion: lively | calm | none` (`MotionSetting`, exported) on the video, a
  stage and a character (all default none); `resolve_motion(character, scene, video)` takes the
  first given, else `DEFAULT_MOTION` `lively`. `MOTION_LEVELS` 1 / 0.4 / 0; every effect is
  linear in it and at 0 every function returns the plain motion (no offset, no extra time).
- **Character**: `Character(..., motion="lively")` (unknown: `VidgenError`), `motion_strength`,
  `set_squash(x, y)` (about the feet, outside the poses: `state()` never holds it).
- **Functions**: `Phases` (wind-up, move, settle); `motion_ease(u, strength, base=smoothstep)`;
  `walk_motion_seconds`, `walk_accent`; `jump_motion_seconds`, `jump_stretch`, `squash_scale`
  (area kept); `follow_through` / `follow_lag` on `FOLLOW_SPRING = Spring.tuned(2.0, 0.5)`
  (§69.15), `follow_angles` (arms, head, accessory; walks and jumps only), `end_fade` so an
  animation ends exactly in its state. Run times of walks and jumps include the extra phases.

### 69.14 Keyframes and motion paths (Step 81)

`scenes/keyframes_action.py`: `keyframes` and `move_along`, on a stage's characters, props and
parts.

- **Part targets**: `<character>.<part>` (`target_patterns`; `cast.part_target_names`, only with
  an active project). Wildcards select parts too; acting and moving actions skip them
  (`is_part_target`) and reject one named alone.
- **Channels** (`cartoon/keyframes.py`, no manim): `x, y, rotate, scale`. Whole target: `x` a
  mark / x (`camera_place`), `y` feet height above its ground line in frame heights
  (`Stage.grounds`), `rotate` degrees about the feet, `scale` a factor of the built size. Part:
  pose shift, angle and scale (scale signs kept). `rotate` and `scale` are absolute.
- **Keys** (`KeyFrame`, `extra=forbid`): `t` seconds (0..600) or `"40%"` of the narration, all
  one kind, strictly increasing (`key_time_problems`); `x`, `y` (±2), `rotate` (±1080), `scale`
  (0, 10], `ease`. Times count from the action's start. A channel holds `start` before its first
  key and its last value after.
- **Eases** (`EASES`, `EaseName`, default `smooth`): Manim's rate function names written out
  without importing manim (a test checks them against `manim.utils.rate_functions`), plus
  `lively` / `calm`; no `there_and_back`-style eases.
- **Paths**: `path_curve` (Catmull-Rom, `PATH_SAMPLES` 32 per segment), `MotionPath.at(share)`
  at constant speed, clamped.
- **`KeyedMotion(mobject, values_at, *, part=None)`** (exported).
- **Actions**: `keyframes` (`keys`, `ease`; `run_time_for` = last key); `move_along` (`path`,
  `curve` `smooth | straight`, `ease`, `speed` (0, 20]); both reversible (back to the values at
  `apply`). Limits: whole |y| ≤ `WHOLE_Y_LIMIT` 1, part |x|, |y| ≤ `PART_SHIFT_LIMIT` 1.

### 69.15 Spring physics for secondary motion (Step 82)

`cartoon/spring.py` (no manim, exported): `Spring(stiffness, damping)` (unit mass; both > 0,
else `ValueError`), `Spring.tuned(frequency_hz, damping_ratio)`, `angular_frequency`,
`damping_ratio`, `is_critical`, `decay_rate`, closed-form `step_response`, `overshoot`,
`settle_seconds(tolerance=0.02)`. `follow(target, seconds)` weights the target's past by the
impulse response (slice weights are `step_response` differences, so they sum to 1) over the last
6 decay times: stateless, the same at any frame rate and after any seek. Used by follow-through
(§69.13) and custom scenes; no YAML for springs.

### 69.16 Character sheets and mid-action storyboard stills (Step 83)

- **Sheet** (`cartoon/still.py`): `character_sheet_sections(entry, root)` (pose, expression,
  mouth; `own` marked), `sheet_layout(sections, columns=SHEET_COLUMNS 8)`,
  `write_character_sheet(project, entry, theme, path=None) -> CharacterSheet`. Cells are drawn by
  Manim at cell pixel size (so the one-pixel stroke floor holds) at the right height, not scaled,
  pasted on a Pillow page in the storyboard's fonts; close-ups share one scale; saved as a
  64-colour PNG without dithering.
- **`vidgen character-sheet [NAME] [PROJECT] [--all] [--variant NAME] [--output FILE] [--json]`**:
  default `exports/character_sheet_<name>.png`; `--output` only with a NAME; no characters is a
  `VidgenError`. JSON (`jsonout.character_sheet_document`): `project, variant, elapsed, sheets:
  [{character, path, width, height, bytes, sections: [{kind, names, own}]}]`. MCP tool
  `character_sheet(project, name=None, variant=None, images, image_offset)`.
- **Mid-action stills** (`capture.py`): `NarratedScene.mid_still_actions` (`Stage`: `walk_to,
  enter, exit, gesture, jump, keyframes, move_along`). `ActionRunner._run` calls
  `FrameCapture.add_mid_still` before playing a batch; frame `mid_action_frame(start, frames,
  taken, min_gap)` = `start + frames // 2`, none under two frames or within
  `MID_STILL_GAP_SECONDS` 0.4 of another still; at most `MAX_MID_STILLS` 3 per beat. Times come
  from the run as played.
- **Records**: `CapturedFrame` with `k` 0 and `mid` = label; file `<beat>-m<frame>.png`; `mid`
  in `index.json` and the layout dump only on mid stills. `lint` reads only `k == n`, `deck`
  skips them, `gallery` takes the end still; the storyboard labels `½ walk_to pip @ time` and
  JSON frames carry `mid` (null otherwise).

### 69.17 Cartoon lint rules (Step 84)

`lint/cartoon_rules.py` (imported after `layout_rules`, so `RULES` keeps `LINT_RULES`' order),
default `warning`, settings in `config.LintRules`, beat-end stills only. Scene rule
`look_alike`: §69.49.

- **Layout dump keys** (`introspect._character_keys`): `facing`, `speaking`, and when they apply
  `face` (head box, px), `viseme` (`Character.spoken_viseme`), `looked_at`
  (`Character.looked_at`), `passage` (`enter` / `exit` while that walk plays), `walked_in`.
  Bubble objects carry `bubble` = the speaker. A beat-end still's frame has `narrating`
  (`scene.beat_log`, false in the pad).
- **Rules**: `off_stage` (`min_hidden` 0.05; skipped with `passage` or zoomed in; `off_frame`
  skips characters; in a shot only framed characters, §69.29), `character_overlap`
  (`min_overlap` 0.25; walkers and passers excluded), `bubble_overlap` (`min_overlap` 0.1, faces
  and bubbles), `facing_away` (listener = `looked_at` in view, else the nearest; `camera` not
  checked), `hidden_speaker` (`min_hidden` 0.5 of the face covered by later-drawn characters,
  props, foreground layers, overlays; 12 x 12 grid), `mouth_without_voice` (a non-`rest` viseme
  while not narrating).
- Each message ends with its fix (also in CONFIG.md's rule table); `lint_ignore`'s `object`
  matches a bubble's speaker. Limits: no depth in the dump; boxes, not pixels.

### 69.18 Cartoon storytelling in the guide, and `examples/cartoon` (Step 85)

Guide topic `cartoons` (aliases `cartoon`, `characters`, `character`, `stage`, `dialogue`,
`acting`), between `actions` and `overlays`; it requires original characters (never a known
character, mascot, brand figure, logo or "style of" prompt). `examples/cartoon` ("The Box Kite")
is the reference example: no audio committed, it must pass `vidgen validate` and `vidgen lint
--fail-on warning` on the preview.

### 69.19 Foley and music stings (Step 86)

Ordinary sound effects (§47) recorded during the render: `SfxEvent`s on the one SFX track.

- **Built-in sounds** (`sfx.BUILTIN_SOUNDS`): `footstep`, `boing`, `sting_reveal`,
  `sting_comic`, `sting_sad` (generated, nothing downloaded); `whoosh`, `swoosh`, `pop` reused.
- **Schedule** (`cartoon/foley.py`, exported): `foley_cues(PlayedAction(action, start, seconds,
  expression, heights, phases)) -> [FoleyCue(time, sound, gain, params, align)]`: a `footstep` per
  footfall of `walk_to` / `enter` / `exit` (`footfall_shares`, from inverting `walk_progress`) plus
  a softer closing step, `whoosh` at an `enter`'s start, `swoosh` ending with an `exit`, `boing`
  at a jump's take-off, `pop` on a `surprised` emote / react; nothing else.
- **Timing from the real run**: `ActionRunner._run` calls `scene.action_foley(name, options,
  animations, start=now, seconds=frames / fps)` before `scene.play` (not for undoing or for
  actions applied without animation). `NarratedScene.action_foley` does nothing; `Stage`'s builds
  `PlayedAction`s from `Walk.heights` / `Walk.phases` / `Jump.phases` and omits `params` when
  `assets/sfx` replaces the sound.
- **Switch**: top-level `foley` and stage `foley: bool | None`; in the render fingerprint.
- **Stings**: beat `sting:` (`StingSetting`: `reveal | comic | sad` or `StingCue(kind, at,
  gain)`; `placed_at`: `at`, else `start` for reveal, `end` (before the pad) for comic / sad),
  recorded by `NarratedScene.narrate` with `duck` set; any scene type.
- **Ducking**: `SfxEvent.duck` (JSON key only when set). `join_scenes` computes
  `mix.sting_ducking` = `duck_curve(speech_spans, frames, STING_DUCK)` (`depth 6, attack 0.15,
  release 0.3, hold 0`) and passes `ducking_db=` to `sfx.write_track`. Lighter than the music's
  12 dB / 1.5 s hold because a sting lasts 1–2.5 s; stings stay on the SFX track so they sound
  with or without `music:`.

### 69.20 Render speed for cartoons (Step 87)

- **Static image**: `NarratedScene.get_moving_mobjects` returns every mobject only while the
  camera follows; with camera listeners only, Manim keeps its static image of the backdrop.
- **Part drawings**: each shape's points are kept once (`shape_drawing`); live members are found
  again only when the shown shape changes (`_live_members`); `refresh` only applies matrices.
- **Look cache**: `look_parts(look, colors)` / `look_key` share generated parts per process; key =
  look + resolved colours (never poses, name, voice, height or state); at most `LOOK_CACHE_SIZE`
  16; SVG looks are not cached.
- **Not done**: raster caching of parts (changes the drawing); caching Manim's subpath split
  (needs a Manim internal missing in 0.19).

### 69.21 Review of Phase H (Step 88)

- `StageCharacter`, `StageProp`, `StageParticles` accept a plain string; their
  `__get_pydantic_json_schema__` returns `anyOf` (string, object) so `vidgen schema` shows it.
- libx264 through PyAV encodes frames whose width is not a multiple of 16 (the 854-px preview)
  differently between runs; compare renders by raw frames or at widths that are multiples of 16.

### 69.22 Fixes after the Phase H review: the ground under the set, the mouth while moving

- **Ground band**: `ground_top(ground, items)` (`cartoon/stage.py`, exported) = `ground +
  FAR_RISE ×` the largest depth of items on the ground (lifted items excluded), so everything at
  a depth stands inside the drawn band. Depth geometry is unchanged. A picture has no band unless
  `ground_color` is given.
- **One live copy per shape**: a swap only moves points between permanent children, because
  Manim draws the family list captured when an animation begins: a replaced child would stay
  drawn where it was. A style set on the character is kept by every shape.

### 69.23 Automatic directing, part 1: looks and reactions (Step 89)

`auto_direct` adds routine dialogue acting as ordinary beat actions.

- **Setting**: `AutoDirect(looks, reactions, gestures, closeups, effects)` (each default `True`;
  `effects` §69.40), `AutoDirectSetting = bool | AutoDirect` on the video (`False`), the stage and
  the beat; `directing_kinds(beat, scene, video)` takes the first given (none: off).
- **Planner** (`cartoon/directing.py`, no manim, pure): `plan_directions(scene_id, cast, beats,
  stage=None) -> [DirectedBeat]` from `CastMember`s and `BeatInput`s, one `_SceneState`, passes in
  `_PASSES` (`DIRECTING_KINDS` order). `_follow_written` applies written actions first; a
  character targeted by a written action (except `FRAMING_ACTIONS`) is *touched* and gets nothing
  added that beat (written actions win).
  - **Looks**: listeners look at the first speaker, each speaker at its addressee (`_addressee`:
    latest other speaker on stage, previous addressee, next speaker of the scene, the only other
    character, else none); `look_at` at 0 unless touched, headless or already looking.
  - **Reactions**: `line_cue` (`?` question, `NEGATIONS` word, `!` exclaim) → `react` with an
    expression of `REACTIONS[cue]` other than the last, picked by
    `random.Random("<scene>/<beat>/<character>")` (same in every process), at `REACTION_AT` 0.95
    of the narration.
- **Tag / merge**: `ActionConfig.automatic(data)` (`auto`; `describe()` appends `(auto)`;
  `shorthand()`). `NarratedScene.auto_actions` (classmethod, default none) and
  `with_auto_actions` (written first); merged in `NarratedScene.__init__` before `plan_actions`;
  the project config is unchanged. `Stage.auto_actions` = `stage_directions(...)`. Validate checks
  written actions only; the planner emits only built-in actions and expressions.
- **Fingerprint**: `auto_direct` is config; `cartoon/directing.py` is render code.
- **Visible**: `project_directions` (`directing_used` skips the session when unused); storyboard
  `auto:` line (`auto_label`, `AUTO_LINES` 2; JSON `auto`); **`vidgen direct [PROJECT] [--print]
  [--scene ID] [--variant NAME] [--json]`** (`--print`: `directions_yaml` to paste; pasted
  actions are written, so nothing more is added); JSON `project, variant, scenes: [{scene,
  beats: [{beat, actions}]}]`.

### 69.24 Automatic directing, part 2: gestures, close-ups and the lint check (Step 90)

- **Inputs**: `CastMember.gestures`; `BeatInput.seconds` / `.words` (`_beat_words`, read only
  when needed); `StageFrame` / `StagePlace` from `stage_frame(project, params)` (as
  `Stage.construct` places them). `_SceneState` tracks feet x, facing and camera x through written
  moves.
- **Lint check**: `_still` predicts the beat's still as a `StillContext` (figure box
  `FIGURE_HALF_WIDTH` 0.21 heights plus `GESTURE_REACH`); `still_findings` runs `CHECKED_RULES`
  (`off_stage`, `facing_away`); an action is added only if it adds no finding. Without a
  `StageFrame` or while following, looks are unchecked and arm gestures and close-ups are not
  added.
- **Gestures**: `stressed_word` (`*word*`, else an all-capitals word, else the longest word of 6+
  letters if the speaker did not gesture last line); `gesture_choices` (the word's own list, the
  line's cue, then `EMPHASIS_GESTURES` shuffled by `"<scene>/<beat>/<speaker>"`); at most one per
  line, timed to land on the word and end within the narration.
- **Close-ups**: a line of ≤ `SHORT_LINE_WORDS` 5 words after one of ≥ `LONG_LINE_WORDS` 8 gets
  a `zoom` on its speaker (`CLOSEUP_SCALE` 2, `CLOSEUP_SECONDS` 0.5) when both moves fit in 80 %
  of the remaining narration, else a `shot: closeup` (§69.29); not after a close-up, not with a
  written `MOVING_ACTIONS` action, a bubble `say` or a gesture, nor while following.
- **MCP** tool `direct` (read-only).
- **Emphasis marks**: `BeatConfig` strips `*word*` asterisks from `text` on read
  (`config.EMPHASIS`, `strip_emphasis`; not `2*3*4`, `a * b`, `**bold**`) and keeps
  `marked_text`, so TTS hashes, captions and every reader see plain text (unmarked beats
  unchanged); the scene fingerprint adds `emphasis` when a scene has marks.
### 69.25 Screenplays (Step 91)

`vidgen screenplay FILE [--out DIR|FILE.yaml] [--cast FILE] [--species NAME ...] [--seed S] [--force] [--json]`
(`cli.cmd_screenplay`, MCP `screenplay`) builds a stage project from a screenplay without AI.
`screenplay.py` (no manim) parses and builds; writing reuses `plan_yaml.commented_yaml` (checked
to load back) and `write_project`, as `write_plan` does.

- **Parse** (`parse_screenplay(text) -> Screenplay(title, front, scenes)`): optional YAML front
  matter (`scenes` refused). First level-1 heading not starting `Scene` = title; other headings
  start a `ScriptScene`. `[...]` alone is a `Direction`; `NAME [(manner)]: text` a `Line` whose
  inline `[...]` become directions at words-before / words (≤ 0.9). `NARRATOR`, `NARRATION`,
  `VOICE OVER`, `V.O.` and plain paragraphs are the narrator. Errors are `VidgenError`s naming the
  line.
- **Set** (`parse_set(text, names) -> SetDesign`): `;` parts `background`, `props` (`PROP_KINDS`,
  `kind (name) at place`, else next `PROP_SLOTS`), `marks`, `characters`; the rest becomes a scene
  `# TODO:`. Unplaced characters take `PLACES[count]` marks ≥ `SPACING` 0.12 from placed ones.
- **Directions** (`direction_actions(text, state, default)`): `_VERBS` map clauses to `walk_to`
  (to a prop / character: `PROP_GAP` 0.1 / `CHARACTER_GAP` 0.14 before it, the other side if
  taken; `runs`: `RUN_SPEED` 5), `enter` / `exit`, `jump`, `look_at`, `point at`, `wave`, `nod`,
  `shrug`, head shake; subjects by name or pronoun (`StageState`). Groups chain by estimated
  seconds at `at` = start / line seconds (words / 2.6 or `narration.words_per_second`), ≤
  `LATEST_AT` 0.95; after a scene's last line at `TRAILING_AT` 0.6. A manner is a leading `react`;
  unmatched text becomes beat `# TODO:`s.
- **Characters and voices** (`screenplay_project`): front-matter `characters` kept (only
  `voice_kind:` removed); other speakers (`OLD ASH` -> `old_ash`) get a `LOOKS` look (§69.47) and
  a `<id>_voice` entry. Voice kind (`VOICE_KINDS` feminine / masculine / neutral) from a bracket
  pronoun (`FEN (she):`, `PRONOUN_KINDS`) or `voice_kind:`, else the look's; conflicting kinds, a
  pronoun on the narrator, an unknown kind: `VidgenError`. `_generated_looks` (§69.49): first
  unused look of the kind keeping `MIN_CONTRAST`, else a random contrasting one; never twice.
  `assign_voices(voice, language, kinds)`: Kokoro voices of the narrator's language by accent and
  gender, best grade first, minus the narrator's and `santa`; OpenRouter `known_voices` in turn;
  ElevenLabs: `label` only plus a `# TODO:` for `voice_id`s. `DEFAULTS`: 1920x1080, preview
  854x480, `soft_pastel`, Kokoro `bf_emma` at 0.85, `narration.pad` 0.7, `auto_direct: true`;
  front matter wins.
- **Output**: commented YAML, then `validate_all` (exit 1 on problems); JSON
  `jsonout.screenplay_document`. Sample `examples/screenplay/humming_box.md`; tests
  `tests/test_screenplay.py`. One set per scene.

### 69.26 Arms and legs in two segments (Step 92)

`cartoon/limbs.py` (no manim): limb names, two-bone solver, fold of one-piece limbs.

- **Parts**: `arm_left` / `arm_right` = upper arm (pivot shoulder), `arm_*_lower` = forearm
  (pivot elbow). Legs are `legs` (one piece) or `leg_left` / `leg_right` (pivot hip) with optional
  `leg_*_lower` (knee); `legs` plus a single leg is a `VidgenError`. Lower segments draw over
  upper, `leg_right` behind `leg_left`, legs behind the body. `CharacterPart.end` (optional) marks
  hand middle / sole. A missing default parent falls back to its parent; an explicit `parent` must
  exist. Generated characters have two capsule segments per limb (`LIMB_WIDTH` 0.08) and single
  legs (`cast.GENERATED_SHAPES`).
- **Solver / API**: `solve_two_bone(root, target, upper_length, lower_length, bend) ->
  TwoBone(direction, bend, reached)` (`ELBOW_BEND` +1, `KNEE_BEND` −1). `Character.reach(hand,
  point, bend=+1)`, `plant(foot, point, bend=-1)`, `hand_point`, `foot_point`,
  `sole_height(state=None)`, `grounded(state, level=0)`; solved in the parent frame via the
  inverse screen matrix, setting only angles.
- **One-piece limbs**: poses for `arm_left_lower` still apply to a character without it, shown by
  `fold(b)` (turn `b/2`, length `cos(b/2)` ≥ `FOLD_MIN_LENGTH` 0.6); built-in poses keep upper +
  elbow/2 equal to the one-piece angle.
- **Motion**: `part_windows` moves a lower segment with its upper (`TIMING_GROUP`). Gestures:
  `POINT_DEGREES` 82 + `POINT_ELBOW` 12, `WAVE_DEGREES` 115 + `WAVE_ELBOW` 60 (`WAVE_SWING` 40°),
  shrug 15 + 60. Walk: `WALK_THIGH_DEGREES` 20, `WALK_KNEE_DEGREES` 40, `WALK_ELBOW_DEGREES` 10 +
  `WALK_ELBOW_SWING` 20; the lower sole stays at its start height (`grounded`, only within
  `GROUND_TOLERANCE` 0.02 of the ground).
- **SVG** (§69.2): ids `arm_left_lower`, `leg_left`, ...; longest part name wins; default pivot of
  single legs / lower segments: top centre. `examples/svg_character` stays one-piece. A `legs`
  reference does not apply to generated characters (validate reports it). Tests
  `tests/test_cartoon_limbs.py`.

### 69.27 Props in hands (Step 93)

Beat actions `pick_up`, `hold`, `put_down`, `give`, `throw` (`scenes/handling.py`, `_Acting`
§69.11; target = character; `to` = prop, place or receiver; `prop` picks one of two; `hand`
`left` (near, default) / `right`).

- **State** (`cartoon/holding.py`, no manim): `Holdings` (prop -> (character, hand)); refusals are
  `HoldingError`s that state the fix. Kept by `Stage.holdings`, validate's replay and the planner.
  One prop per hand.
- **Attached, not added** (§69.22): a held prop is never a submobject of its character; an
  updater keeps its grip at `hand_point(hand)` and the prop right after its holder in
  `scene.mobjects`. Layout dump: `holding`, `held_by`, `hand`.
- **Geometry** (character heights): hold point `HOLD_FORWARD` 0.12 ahead, `HOLD_DROP` 0.13 below
  the shoulder; held height ≤ `HOLD_MAX_HEIGHT` 0.4; `PUT_DOWN_AHEAD` 0.35. `throw_seconds` = 0.35
  + 0.15 + flight (0.45 s + 0.06 s/unit, ≤ 1.6 s).
- **Animations** (`cartoon/transition.py`, exported): `ArmMove(character, keys)`, `PropMove(prop,
  to=, follow=, leave=, arrive=, height=, rise=, turns=, lands=)`; arm targets from
  `Character.reached_parts`. Run times `pick_up` 1.2 s, `hold` 0.4, `put_down` 1.0, `give` 1.2. The
  arm pose before a take is restored on release.
- **Validate**: hook `NarratedScene.action_sequence_problems(spec, params, uses)` (default none;
  `scene_actions` calls it once all uses are valid, so validate and `plan_actions` both run it).
  The stage replays actions in play order (beat, `at`, written) through `holding_problems`: held
  elsewhere, full hand, nothing to release, ambiguous `prop`, `pick_up` > `PICK_UP_REACH` 0.75
  heights, `put_down` > `PUT_DOWN_REACH` 0.75, `give` > `GIVE_REACH` 1.2 or off stage, animating a
  held prop. `move_along` / `keyframes` make x unknown. Messages suggest a `walk_to`.
- **Foley / directing**: `thud` at `PlayedAction.lands` (`LANDING_GAIN` −4 dB); no gesture with a
  holding hand (`GESTURE_HANDS`); prop actions are `MOVING_ACTIONS`. Tests
  `tests/test_cartoon_holding.py`.

### 69.28 Sitting, leaning and crouching (Step 94)

Beat actions `sit_on`, `lean_on`, `stand_up` (`scenes/sitting.py`; `to` = prop); `pick_up` /
`put_down` crouch for low props.

- **Seats** (`cartoon/seating.py`, prop units): `PROP_SEATS`, `PROP_LEANS`, `SEAT_BACKS` (a chair
  sets the sitter's facing); mirrored with the prop (`seat_point()`, `lean_edges()`). SVG props:
  `data-seat="x y"` / `data-lean="left right"` on `<svg>` (kept by the sanitiser; bad value:
  `VidgenError`).
- **State**: `Postures`: `sit` (one per prop or per sofa / bed place, §69.43), `lean` (many),
  `stand`, `pinned` (refuses `PINNED_ACTIONS` `walk_to`, `enter`, `exit`, `jump`, `turn`,
  `move_along`, `keyframes` while posed); refusals are `PostureError`s naming the fix. Layout dump
  `sitting_on` / `leaning_on`.
- **Bodies**: `Character.seated(state, seat)` (hips — the first leg part's pivot — on the seat;
  one-piece legs to the ground or `SEATED_LEGS_DEGREES` 80), `leaning(state, LEAN_DEGREES 12)`,
  `lowered`, `planted`; `BodyMove(character, keys, x=, facing=, soles=)` re-plants feet every frame.
  `sit_on` 1.0 s, `lean_on` 0.8 s (faces away), `stand_up` 0.8 s; only `POSTURE_PARTS` change.
  While posed, `look_at` turns only the head, `pose` / `react` keep body and legs.
- **Crouch** (`handling.crouch`): if the arm (`CROUCH_REACH` 0.95) cannot reach, lower ≤
  `CROUCH_MAX` 0.6 of hip height and stoop ≤ `CROUCH_STOOP` 15°; none under `CROUCH_MIN` 0.01.
- **Validate**: the prop needs a seat / lean edges; the replay checks a taken seat, a held prop,
  `SIT_REACH` 0.75 / `LEAN_REACH` 1.0 heights, `stand_up` from nothing, pinned actions, handling a
  sat-on prop. Tests `tests/test_cartoon_seating.py`.

### 69.29 Shots within a scene (Step 95)

A beat's `shot:` frames characters of a `stage`: the camera cuts (or eases, `move: true`) to a
framing from where they stand, holds it, and the next shot-less beat returns to the pre-shot view.

- **Framing** (`cartoon/shots.py`, no manim): `ShotFigure(name, x, feet_y, height, facing, top)`
  (box `FIGURE_HALF_WIDTH` 0.21 heights each side); `frame_shot(kind, subjects, ...) ->
  ShotView(center_x, center_y, scale)`, scale 1 .. `MAX_SHOT_SCALE` (= `MAX_ZOOM` 8): `wide`,
  `two_shot` (`TWO_SHOT_PADDING` 0.1), `medium` / `closeup` (`SHOT_SPANS`, `LOOK_ROOM` 0.1),
  `over_shoulder` (subject at `SUBJECT_AT` 0.66). `shot_figures(kind, named, present, speakers=,
  looked_at=) -> Shot(kind, subjects, near)` fills in missing names; nothing to frame gives `wide`.
- **Config**: `ShotConfig(kind, of, move, run_time)` from a mapping or words (`"over_shoulder kit
  pip"`); `SHOT_NAMES` (wide 0, two_shot 0–2, medium 1, over_shoulder 1–2, closeup 1);
  `run_time` needs `move`. `ShotConfig.action()` gives the `shot` action.
- **`shot` action** (`scenes/shot_action.py`): `kind` (none: back home), `move`; run time
  `SHOT_MOVE_SECONDS` 1.0 moving, 0 cutting; only scene types with `shot_framing` (`stage`). Stores
  the pre-shot view in `NarratedScene.shot_home`, sets `camera_shot`. A cut sets the camera frame
  directly, never an animation (the runner plays a batch for its longest run time). `pan` /
  `follow` call `end_shot`.
- **Ordering** (`actions.beat_action_list`): a beat's `shot:` key first (location `beats[j].shot`),
  then its actions; a beat after a shot gets a kind-less `shot` (same `move` / `run_time`) unless it
  has one at `at: 0`.
- **Rendering / lint**: camera listeners run first after a cut (§69.20); `say` bubbles are
  `after_camera`; the shot does not follow walks. Dump frames get `shot: {kind, subjects, near}`;
  `off_stage` in a non-wide shot checks only subjects (face box in `FACE_SHOTS`).
- **Directing** (§69.24): `shot` is in `FRAMING_ACTIONS` and `MOVING_ACTIONS`; a close-up whose
  moves do not fit the line becomes a `closeup` shot held for the line (`_closeup_shot`); a written
  shot makes looks and gestures checked on its view. Tests `tests/test_cartoon_shots.py`.

### 69.30 Vertical cartoons follow the speaker (Step 96)

On a `stage` wider than the frame the camera keeps the speaker in view, so a 16:9 cartoon renders
as 9:16 without camera directions.

- **Setting** (`config.ReframeSetting` = `speaker | none`): `VideoConfig.reframe`, stage param
  `reframe` (wins), default none; `directing.stage_reframes` returns `speaker` when the start
  layout is wider than the frame (`reframe_needed`). A variant may set `reframe: none`.
- **Stage width** (`cartoon/reframe.py`): `stage_base_width(frame_width, frame_height,
  reframing)` = `max(frame width, 16/9 × short side)` while reframing (`LANDSCAPE_ASPECT`), so
  marks and walks match the landscape video; else the frame width (§69.6).
- **Path** (`reframe_path(beats, ...) -> [CameraMove(beat, x, seconds)]`, pure): written `pan`
  sets the centre, `follow` makes it unknown, `zoom` / kinded `shot` change nothing; otherwise the
  first speaker with a line ≥ `REPLY_HOLD_SECONDS` 1.5 not in view (`CUT_TOLERANCE` 0.02) is
  framed (`REFRAME_LOOK_ROOM` 0.1, no edge cutting a figure). Eases `REFRAME_SECONDS` 1.0 (≤ 0.8 of
  the shortest line); cuts in the first beat and in beats whose `say` draws a bubble.
- **Planner**: `plan_reframe(cast, beats, stage)` emits automatic `pan`s (`to` 4 decimals,
  `run_time` or `cut: true`), placed first in their beats and passed to `plan_directions` as
  written.
- **`pan` `cut: true`** (§69.7) moves the frame at once (`run_time_for` 0). **Runner**: in a batch,
  camera moves first, then other actions, then `after_camera` ones. Tests
  `tests/test_cartoon_reframe.py`.

### 69.31 Lighting and mood (Step 97)

A `stage` has a light (`light:` param, `light` action) and ground shadows (`shadows:`, default on).

- **Grade** (`cartoon/lighting.py`): `LightGrade(multiply, glow, stars, shadow)`; `c ->
  clip(c * multiply + glow, 0, 1)`, alpha kept. `tint_grade(tint, strength)`. Presets
  (`PRESET_LIGHTS`): `day`, `morning`, `sunset`, `night` (stars), `indoor`; `{tint, strength}`
  (`CustomLight`, strength 0.5). Fades: `LightChange`, generic `fade_at` / `changing` (shared with
  wind) wrapped by `light_at` / `light_changing` (start order, each from the light at its start,
  smoothstep).
- **Drawing** (`cartoon/shading.py`): graded as drawn, never recoloured: `StageLight` wraps the
  Cairo camera's `get_fill_rgbas`, `get_stroke_rgbas`, `display_image_mobject` for mobjects marked
  `light_graded` (`mark_lit`: backdrop, layers, props, characters); bubbles, callouts, particles and
  captions keep theme colours. A `day` stage without `light` actions installs nothing.
- **`light` action** (`scenes/light_action.py`): `animates = False` (cued, never stretches a
  batch), `run_time` = fade (`LIGHT_FADE_SECONDS` 2). The updater is kept as `_light_updater`
  (Manim removes updaters by identity) and removes itself when changes end;
  `get_moving_mobjects` returns everything only while a change overlaps (§69.20).
- **Stars**: without a picture, `night_stars` (seeded from the `sparkles` stream) and `StarField`
  fill the top `STAR_SKY` 0.75 of the sky, ending `STAR_HEAD_ROOM` 0.04 frame heights above the
  highest head; static (no twinkle), not graded.
- **Shadows**: `shadow_ellipse` (`SHADOW_FLATNESS` 0.16, `SHADOW_OPACITY` 0.3 × light `shadow`,
  shrink `1 / (1 + SHADOW_SHRINK 1.5 × above / size)`), `SHADOW_WIDTH` 0.55 of height,
  `PROP_SHADOW_WIDTH` 0.9 of width. Held and lifted props cast none. Unmovable props' shadows are
  one static `StageShadows` in the backdrop; moving casters share one with a `follow` updater. The
  layout dump omits `StageShadows` and `StarField`. Tests `tests/test_cartoon_lighting.py`.

### 69.32 Wind (Step 98)

A `stage` has a wind (`wind:` param, `wind` action): props sway, trailing pieces follow on a
spring, particles drift.

- **Model** (`cartoon/wind.py`): signed level (`1` = gale to `+x`); `WIND_LEVELS` calm 0, breeze
  0.3, windy 0.6, gale 1. `gust(t, seed)`: value noise from splitmix64 integers (identical on every
  platform). `Wind.force(t, delay) = level × (STEADY_SHARE 0.5 + 0.5 × gust)`, delay
  `GUST_CROSSING_SECONDS` 1.2 across the stage; `blown(start, t)` integrates force (`BLOWN_STEP`
  0.05 s, cached, frame-order independent). Seed `wind_seed(scene id)`.
- **Sway**: `SWAYS` (per felt force, §69.38), `sway_degrees`, `bent_points` (exactly the rest
  points at 0°).
- **Trailing pieces**: generator members marked `TRAIL_ATTRIBUTE` (`wind_trail` = pivot x, y,
  weight; `TRAIL_WEIGHTS`) inside `head` / `body`, so parts, sheets, SVG ids and the look cache are
  unchanged. `Character.set_wind(degrees)` (not in `state()`); `trail_degrees` uses `TRAIL_SPRING =
  Spring.tuned(1.2 Hz, ζ 0.3)` and is exactly 0 once force has been 0 for `memory_seconds`.
- **Particles**: `WIND_DRIFT` per kind; `particle_states(..., blown, wind)`.
- **Stage** (`windblown.py`): calm param and actions install nothing (`wind: 0` renders
  frame-identical to no wind — tested). Else `StageWind`: swaying props are `SWAYS` kinds no action
  moves, holds, sits or leans on. `_wind_updater` removes itself once nothing can move;
  `get_moving_mobjects` redraws from the first swaying prop / trailing character on.
- **`wind` action**: `- wind: 0.8` or a level name; `animates = False`, fade `WIND_FADE_SECONDS`
  2; `number_target = True` (`ActionConfig` keeps a YAML number as text). Tests
  `tests/test_cartoon_wind.py`.

### 69.33 Non-speech voice sounds (Step 99)

`[gasp]`, `[hmm]`, `[laugh]`, `[sigh]`, `[giggle]`, `[groan]` (any case, plural `s`) in a beat's
text are sounds of its speaker. User docs: docs/CONFIG.md "Voice sounds".

- **Markers** (`voicesounds.py`): `BeatConfig` calls `take_out_sounds` before `strip_emphasis`:
  `text` plain, `marked_text` with `*word*`, `voice_sounds` = `VoiceSound(kind, word)`. Nothing
  reading `beat.text` sees markers; markers only is a config error.
- **TTS text**: `Project.spoken(beat)` = `pronunciation.apply(text)` then `voiced_spoken` (voicings
  as zero-length `Replacement`s, so `map_word_times` times only written words); `spoken_texts`
  (audio hash, `vidgen tts`, lint) uses it. Beats without markers are unchanged (pinned keys).
- **Per provider** (`VOICE_SOUNDS`): `eleven_v3*` gets audio tags; others say `Ha ha ha!`, `Hee
  hee!`, `Hmm.`, `Ugh.`; `gasp` / `sigh` at a line's start / end are generated `sfx.py` sounds
  (audio and hash unchanged), inside a line `Hah!` / `Haah.`.
- **Timing / mix**: `sound_spans`; generated sounds `SOUND_GAP` 0.05 s from the words, recorded by
  `NarratedScene.narrate` as beat SFX at `SOUND_GAIN_DB` +6 dB (overridable in `assets/sfx/`).
- **Mouth / face**: `beat_visemes` overlays generated sounds at read time (`.visemes.json`
  unchanged); `directing.sound_reactions` (always run first) adds a `react` for the first sound's
  expression unless a written `FACE_ACTIONS` acts on that speaker.
- **Captions / readback**: `captions`, `write_srt(spoken=)`; `compare_beat(..., skip_heard=)`.
- **Fingerprint**: a scene with sounds adds `voice_sounds` (beat -> `[kind, word]`). Tests
  `tests/test_voice_sounds.py`.

### 69.34 Overlapping speech and interruptions (Step 100)

`overlap: S` starts a beat `S` s before the previous speech ends; `interrupt: true` cuts that line.
User docs: docs/CONFIG.md "Overlapping lines".

- **Rules**: refused on a scene's first beat (§49, §50, §52 unchanged); `interrupt` with `overlap:
  0` refused; `overlap >= 0`; validate warns on overlapping the same voice.
- **Timeline** (`overlap.py`): `beat_lines` -> `SpokenLine`; `beat_windows(lines, pad, fps) ->
  BeatWindow(body, rest, heard, shape)`: not joined `(d, pad, d, plain)` (same float `d + pad`);
  joined `body = max(speech_end - lead, MIN_WINDOW)` in whole frames, `rest = 0`. Lead =
  `overlap`, or for a bare interrupt `INTERRUPT_WORD_SHARE` 0.7 into the last word (stored
  alignment), else `INTERRUPT_LEAD` 0.2 s. `NarratedScene.beat_window` and `VideoPlan` share it.
- **Mix**: `VoiceShape` dip (`DIP_RAMP` 0.1 s, `OVERLAP_DIP_DB` 3) or cut fade (`INTERRUPT_FADE`
  0.05 s) applied in `add_narration`; a plain shape is not applied at all.
- **Mouths / captions**: `end_lip_sync` keeps a still-sounding beat in `_lingering`; an interrupted
  track is `VisemeTrack.until(cut)`. `cues.stack_cues` shows ≤ `MAX_STACK` 2 cues on one plate;
  SRT cues may overlap.
- **Lint**: rule `talked_over` (scene scope, warning) reports words spoken over or cut.
- **Fingerprint**: keys enter the scene dump as `joins` only when set. `timings.json` keys
  unchanged (the scene's speech end is the latest `end`). Tests `tests/test_overlap.py`,
  `tests/test_overlap_pinned.py`.

### 69.35 Shared casts and sets (Step 101)

A series keeps characters, voices and places in included files. User docs: docs/CONFIG.md
"Shared casts and sets".

- **Loading** (`includes.py`, no manim): `read_project_config(config_file, confine)` reads the
  `include:` tree depth first (paths relative to the including file; a file reached twice merged
  once), then the project: `merge_config` merges mappings by key, `characters` by name (later keys
  win), anything else replaces. Included files may hold only `include`, `characters`, `voices`,
  `sets`; their file paths are rewritten relative to the project (`ConfigSource.named_files`).
  Missing, unreadable, circular, non-YAML or (under `vidgen mcp`) out-of-root includes raise a
  `VidgenError` naming the chain. Variants may not contain `include`.
- **Sets**: `expand_sets` applies each scene's `set:` before validation (`Params` never sees it):
  `image` / `generate` / `background` are one choice; mappings merge; `characters` / `props` /
  `layers` / `particles` combine (set first; same explicit name replaces, `numbered_names`; `[]`
  clears) — combine, because a set is furniture a scene adds to. Unknown set: config problem with
  did-you-mean.
- **Problem locations**: `Origin(file, location)` (`Project.origins`); `attributed(problems,
  origins)` rewrites by longest prefix; `Problem.file` (JSON `file`; `None` = project config).
- **Caches**: the merged config is what renders and hashes see; the scene fingerprint leaves out
  `include`, `sets`, `set` and adds `included_files` (stats of `named_files` outside `assets/`).
- **CLI**: `vidgen validate` prints `included:` (`--json` `included`). `vidgen screenplay --cast
  FILE` (MCP `cast`) writes `include: [...]`, treats cast characters as declared, and
  `parse_set(text, names, sets)` reads a leading cast set name as `set:`. Example
  `examples/cartoon_series/`; tests `tests/test_includes.py`.

### 69.36 Review of Phase I (Step 102)

Invariants this review fixed (check: `tests/test_phase_i_review.py`):

- `overlays.scene_overlays` finds a scene by id (an `auto_direct` stage renders a merged copy).
- Seat lines sit below every generated look's hips (0.15–0.24 of height): `PROP_HEIGHTS` `chair`
  0.26, `box` / `rock` 0.155 (seats at 0.14); `Character.seated` puts the hips (`_hips_y`) on the
  seat line.
- `vidgen mcp` confinement: `svg` is in `PATH_KEYS`; a Kokoro `.pt` `voice` is checked against
  the project and current folders; `read_include_file` confines nested includes under
  `VIDGEN_CONFINE_ROOT`. Folder scans (`assets/sfx/`, `assets/icons/`, `audio/`) are not checked.
- `voices.voice_warnings(config, origins)` skips unused voices from included files.

### 69.37 Props: basket, umbrella, napkin (Step 103)

Props `basket`, `umbrella`, `napkin` (`cartoon/props.py`, §69.8), plus multi-shape props and grips.

- **Shapes** (`PROP_SHAPES = {"umbrella": ("closed", "open")}`): a drawer may return a dict;
  every shape stays in the family (hidden = no points). `Prop.show_shape(name)` redraws from
  points recorded in prop units through an invisible anchor (`character.anchor_mobject` /
  `anchor_placement`, shared with `Character`), so the new shape keeps place, size and facing.
  `Prop.shape` (`None` for one shape), `shapes`; `StageProp.open: true` (config error without an
  `open` shape).
- **Grips** (`PROP_GRIPS`): basket handle top, open umbrella shaft; else the middle.
  `Prop.grip_point()` is what follow updaters, `PropMove` and `pick_up` use.
- **Overhead** (`cartoon/holding.py`): an `OVERHEAD_PROPS` prop (§69.56) showing an
  `OVERHEAD_SHAPES` shape is held at `overhead_point` (`OVERHEAD_HAND` 0.6), `OVERHEAD_HEIGHT` 0.85
  of the holder (not capped), drawn right *before* its holder (others after, §69.27).
- **`open` / `close`** (`_Reshape`, targets props, `RESHAPE_SECONDS` 0.6, switch at
  `RESHAPE_SHARE` 0.5 via `PropReshape`, which keeps the grip at `follow()` because Manim pauses
  the prop's updater while animated). Validate: not a prop / no such shape. Targets are movable
  for shadows; `ShadowCaster` takes `widths` per shape; dump key `shape`. Tests
  `tests/test_cartoon_props.py`.

### 69.38 Visible wind and props that blow away (Step 104)

- **Felt force** (`cartoon/wind.py`): `felt_force(f) = f × (1 + WIND_BOOST 2 × |f|)`, used by
  `sway_degrees` and `trail_degrees`; trails soft-limit to `TRAIL_LIMIT 80 × tanh(x / 80)`.
- **Particles**: `leaves` and `streaks` (`fall` 0, along the wind; opacity ramps in above
  `wind_shown` 0.2 over `WIND_SHOWN_RAMP` 0.3). Never automatic (that would change every windy
  stage's dump and lint).
- **Path** (pure): `gusty_progress(share, seed)` (monotone 0 → 1), `blown_point` (never below the
  straight line, whole turns so it ends upright), `blow_seconds(distance, level) = 0.6 + distance
  / (3 × max(felt_force(|level|), 0.5))`, ≤ 6 s.
- **`blow_away`** (`BlowAway`, targets props, `to` optional): `LIGHT_PROPS` (napkin, umbrella,
  ball, cup, basket, box) and SVG props. With `to`: lands standing there; without: beyond the
  downwind edge, `BLOW_AWAY_UP` 0.2 frame heights up. Seed `wind_seed("<scene>:<prop>")`;
  `PropMove(..., path=blown_point)`; a held prop leaves `Holdings` (`drop`) and the arm returns.
- **Validate**: not a prop, too heavy, bad `to`; a prop blown off stage is gone for later
  actions; `blow_away` without `to` at level 0 is a problem. `wind: 0` still renders identically.

### 69.39 Rain on the ground (Step 105)

On a `stage`, rain lands on the ground (depth-aware) with splashes; open umbrellas and trees
shelter; puddles may grow; a rain bed plays. Other scene types are unchanged.

- **Model** (`cartoon/rain.py`, numpy): `rain_ground(...) -> RainGround` (landing band from
  `LANDING_FRONT` 0.05 frame heights in front of the ground line to `ground_top`); landing shares
  from their own stream (`default_rng([seed, 105])`) so drop positions are unchanged;
  `ShelterBox.covers` (`SHELTER_REACH` 0.1); splashes `SPLASH_SECONDS` 0.3; puddles
  (`default_rng([seed, 1105])`, 4 per frame width, full at `PUDDLE_GROW_SECONDS` 10).
  `SHELTER_PROPS`: tree, umbrella (`open`).
- **Drawing**: `ParticleField(ground=, seed=)` (rain only) adds one `splashes` `VMobject`.
  `Puddles` hold plain functions, not the field or scene, because Manim deep-copies a mobject it
  fades in. Layout dump omits puddles.
- **Stage**: hook `NarratedScene.particles_started(field, settings)` (default nothing); the stage
  keeps rain fields for the bed when foley is on and lays lit puddles behind the characters.
  `puddles` on another particle kind: config error / validate problem.
- **Sound bed** (`ambience.py`, `mix.py`): stage `timings()` adds `ambience: [{bed: rain, start,
  end}]`; spans closer than `JOIN_GAP` 0.25 s join. `rain_loop()`: 8 s seamless stereo, seeded
  `crc32("ambience:rain")`, `RAIN_LEVEL` −32 LUFS, fades 1.5 s, `RAIN_DUCK` 5 dB under speech. A bed
  makes `mix_audio` write the mix but does not trigger `normalize: auto`; the `mix` report gains
  `ambience`. Tests `tests/test_cartoon_rain.py`.

### 69.40 Effect symbols over characters (Step 107)

Beat action `effect` pops a symbol over a head (`- effect: pip` + `to: idea`).

- **Symbols** (`cartoon/effects.py`, pure): `EFFECT_KINDS` sweat, anger, idea, question, exclaim,
  sleep, hearts, stars, sparkle, tear; `effect_pieces(kind)` (primitives only, no font glyphs);
  `EFFECT_STYLES` (spot, size in head heights, theme token). `effect_spot(..., avoid=)` picks the
  spot from `head_box` and facing, trying `ALTERNATE_SPOTS` when a speech bubble overlaps; chosen
  once, recomputed from the head each frame. Motion is pure in time (`pop_scale` with
  `POP_SPRING`, `exit_scale`, `piece_pose`); shapes are never mirrored.
- **Drawing** (`cartoon/effect_symbols.py`): `EffectSymbol(kind, color=, character_height=)`,
  `place`, `follow`; never part of the character (§69.22).
- **Action** (`scenes/effect_action.py`): `to` (required), `color`, `sound`; `EFFECT_SECONDS` 0.4;
  reversible, `until_next_beat`; `alters_targets = False` (same batch as the character's other
  actions). Placed at `z_index` top + 1 via `EffectAppear`; later `say` bubbles avoid it; not lit.
  Sounds `EFFECT_SOUNDS` (`cartoon/foley.py`).
- **Dump / lint**: kind `effect`, keys `effect`, `effect_of`; `bubble_overlap` covers symbols;
  `hidden_speaker` ignores them.
- **Directing** (kind `effects`, last in `DIRECTING_KINDS`): ≤ 1 per beat, for the first
  expression change in `EXPRESSION_EFFECTS` (§69.59); none with a written `effect`. Screenplay
  phrases: `_EFFECT_VERBS`. Tests `tests/test_cartoon_effects.py`.

### 69.41 Motion effects and running (Step 108)

- **Cues** (`cartoon/motion_effects.py`, pure): `motion_effect_cues(played, strength)` maps a
  `PlayedAction` (§69.19) to `MotionEffectCue(kind, time, seconds, toward, arm)`; strength 0 gives
  none. Walks at ≥ `FAST_SPEED` 1.15 heights/s: `dust` at set-off and stop, `speed_lines`; `jump`
  landing: dust, plus `impact` stars from `HARD_LANDING` 0.7; flying props: `speed_lines`;
  `gesture` with `big: true`: `whoosh`. `motion_seed` (crc32) makes renders identical.
- **Drawing** (`cartoon/motion_effect_shapes.py`): `MotionEffect(cue, mover, ...)`, a fixed pool
  of `VMobject`s with a `dt` updater; never added to a character.
- **Stage**: hook `NarratedScene.action_motion_effects` called right after `action_foley`;
  `motion_effects` (stage, else top level, default true). Effects go next to their mover in
  `scene.mobjects`; not lit; `_motion_sweep` removes finished ones and itself.
- **Running** (`run_to`, `WalkTo` subclass): `Walk(gait=RUNNING)`; `Gait` (`cartoon/acting.py`)
  stride 1.6, swing 1.5, knee 1.6, elbow 2, bob 2, lean 12°; `RUN_SPEED` 6 units/s. `WALKING`
  uses the same floating-point operations as the plain walk (frames identical). `run_to` counts as
  a walk everywhere.
- **Dump / lint**: kind `motion_effect`, keys `motion_effect`, `effect_of`; `off_frame`,
  `covered_text`, `hidden_speaker` skip it. Tests `tests/test_cartoon_motion_effects.py`.

### 69.42 Rooms: indoor sets (Step 109)

A stage's `room:` draws a room instead of sky and ground band. User docs: docs/CONFIG.md "Rooms".

- **Geometry** (`cartoon/room.py`, pure): `wall_depth(items, depth)` = `room.depth`, else
  max(`WALL_DEPTH` 0.4, deepest floor item); a given depth with something deeper is a config error.
  `room_geometry(...) -> RoomGeometry` (floor to the wall line `ground + FAR_RISE × depth`, also
  the items' `ground_top`; wall; skirting; optional ceiling). Wall unit = a scale-1 character's
  height at the wall depth (windows and doors sized in it). Patterns: stripes, dots, `boards`,
  `tiles`, `plain`.
- **Window sky**: `window_sky(light)` (`WINDOW_SKIES`), `SkyChange` / `sky_at` fade with the
  light.
- **Drawing** (`cartoon/room_drawing.py`): `draw_room(...) -> RoomDrawing` of `room`,
  `window_views`, `room_front`. Default colours are fixed hex (no token is light and warm in every
  preset).
- **Stage**: `StageRoom` (`wall`, `wallpaper`, `floor`, `flooring`, `skirting`, `ceiling`,
  `depth`, `windows`, `doors`; `room: true` = defaults), `RoomWindow`, `RoomDoor`. All lit except
  `WindowViews`; `_show_light` updates the windows.
- **Doors are props**: `door` shapes `closed` / `open`; `Params.stage_props()` appends a
  `StageProp(prop: door, depth: wall depth, scale: DOOR_SCALE 1.3)` per room door (numbered with
  props). A door name is also a mark (`stage_marks()`); clashes with marks, characters or props are
  config errors. Doors cast no shadow.
- **Through a door**: `enter` / `exit` option `door` (not with `side` / `to`) opens it and fades
  the walker (`DOOR_FADE_SECONDS` 0.35, `passage_fade`, `Character.shown`). Without `door` nothing
  changes.
- **No weather inside**: `wind` ≠ 0 or `OUTDOOR_PARTICLES` (rain, snow, leaves, streaks) in a room
  is a config error (actions: validate problems).
- **Sets** (§69.35): a stage `room` drops the set's `image`, `generate`, `background`,
  `ground_color`, and vice versa; rooms merge by key. Tests `tests/test_cartoon_room.py`.

### 69.43 Furniture (Step 110)

Furniture is built-in props (§69.8): `FURNITURE` in `cartoon/props.py` (sofa, armchair, bed,
bookshelf, counter, fridge, picture, rug, houseplant, clock, tv, desk); gallery
`docs/gallery/media/furniture.png` via `still.write_props_png(..., kinds=FURNITURE)`.

- **Seats**: every built-in seat line is at 0.14 of a character's height (§69.36). `SEAT_PLACES`
  (sofa, bed): one sitter per place; `Postures.sit(character, prop, places, prefer)` takes the
  first free preferred place; full: `PostureError` (`'sofa' is full: ...`). `sit_on` prefers the
  place nearest the feet. `SEAT_BACKS` `desk`: the sitter faces the desk.
- **Against the wall**: `StageProp.against: wall | None`. In a room an `on_wall()` prop gets the
  wall depth in `Params.stage_props()` and is excluded from `wall_depth`; a given `depth` wins;
  `against: wall` without a room is a config error.
- **Hanging**: `PROP_HANGS` (picture 0.5, clock 0.85 character heights); `StageItem.hang` (default
  0) is added to the feet y by `stage_layout`, unlike `lift` (frame heights). Hanging and
  `FLAT_PROPS` (`rug`) cast no shadow.
- **Screenplay**: `set:` takes `room` (`ROOM_WORDS`, windows, doors), `against the wall`, and
  `PROP_WORDS` synonyms. Tests `tests/test_cartoon_furniture.py`.

### 69.44 Moving in depth, and a front view (Step 111)

- **Depth walks** (`cartoon/stage.py`, pure): `walk_to` / `run_to` take `depth` or `to: {mark,
  depth}` (`WalkPlace`, `walk_destination`); straight line (`depth_along`,
  `depth_walk_distance`: one unit of depth = `DEPTH_WALK_HEIGHTS` 2 heights), so walks across are
  unchanged. Not behind a room's wall. `Walk(..., depth=, feet_y=, carried=)` rescales the walker,
  its strokes and held props each frame; `Character.stage_depth` / `ground_y` follow (not `depth`:
  Manim's z-size property).
- **Draw order**: `depth_slot` puts a character after deeper ones and props at its depth.
  Manim fixes `moving_mobjects` when an animation begins, so `_draw_order_step` reorders and
  resets it during depth walks (and front-facing scenes); `get_moving_mobjects` redraws from the
  first crossed object. Put-down props take the holder's `stage_depth`; shadows scale with depth.
- **Front view** (`generate_parts(look, colors, front=True)`, cached per view): same parts and
  shape names (`_check_front`); each part holds both views' copies, only the shown one with points,
  so the family never changes (§69.22). Facing `front` (`FACINGS`): no mirror, `FRONT_DRAW_ORDER`;
  `side_facing` remembers the side. SVG characters ignore it (`cast.front_view_warnings`).
  `PoseChange` side <-> front swaps half-way with `TURN_SQUASH` 0.12; `turn` takes `to: front`.
  Walking front shortens the lifting leg; sitting, leaning, crouching are drawn from the side.
  `facing_sign(facing, front=1.0)` (shots and reframing use `front=0`).
- **Validate / lint**: `holding_problems(depths=)` reports `sit_on`, `lean_on`, `pick_up`, `give`
  across more than `DEPTH_REACH` 0.05 with the fixing walk; dump writes `depth` when > 0;
  `character_overlap` / `walk_overlap` skip pairs ≥ `DEPTH_APART` 0.15 apart. Tests
  `tests/test_cartoon_depth.py`.
### 69.45 Iris transitions (Step 112)

- **Config** (`config.py`): `TransitionConfig.type` `iris_out` / `iris_in` (default 1.2 s,
  `TRANSITION_DURATIONS`) with `character` (a name) or `at` (`[x, y]`, frame fractions from the
  top-left, each 0..1; not both) and `color` (default black, `transitions.IRIS_COLOR`; values as
  for `fade_color`). `character` / `at` on another type, or `color` on a type other than
  `fade_color` and the irises, is a config error. `IRIS_TRANSITIONS`, `COLOR_TRANSITIONS =
  (fade_color, iris_out, iris_in)` and `TransitionConfig.through_color` are the tests used by
  plan, requested and head frames. The key is `character`, not `on` (PyYAML reads bare `on:` as
  `True`). `iris_out` on the first scene is an error; `iris_in` there opens the video.
- **Semantics.** A close then an open through the colour, split like `fade_color`
  (`round(duration x fps / 2)` frames each side, no overlap, §49 timing). `iris_out` closes on the
  scene before's target and opens the next from the centre; `iris_in` closes on the centre and
  opens on the next scene's target (`transitions.iris_scene(i, t)`: `i - 1` for iris_out, `i` for
  iris_in).
- **Drawn in the renders, not at the join.** `ColorFade(..., iris_in=, iris_out=)` (outermost
  `add_frame` wrapper, §49) blends `frame x inside + colour x (1 - inside)` with `inside =
  iris_coverage(h, w, x, y, r)` and `r = iris_radius(weight, iris_full_radius(w, h, x, y), hold)`
  (weight 1 = closed on the boundary frames); with `hold` (a head) the circle eases to it, stays
  between `IRIS_HOLD` 0.55 and 0.8, then closes. `NarratedScene._iris_point` returns `(width,
  height) -> IrisPoint(x, y, hold)`: the `at` point, the centre, or the character's `head_box`
  through the camera frame (`hold` = `IRIS_HEAD_SCALE` 1.5 x half its diagonal), asked on every
  masked frame so it follows the character. A name not in the cast at render time is a
  `VidgenError`. The join sees a cut, so nothing depends on the FFmpeg version and stills,
  storyboards and the layout dump show irises. Rejected: an `xfade` expression at the join
  (overlap hides the next scene's start, needs head positions from the worker, differs per build).
- **Validate**: `transitions.iris_problems(config)`: a `character` not among the target scene's
  declared characters. Only circles; targets are characters or points, not props. Tests:
  `tests/test_cartoon_cards.py`.

### 69.46 Title cards: the `card` scene (Step 112)

- **Scene** (`scenes/card.py`): `text` (required), `subtitle`, `style: burst | frame | plain`,
  `color` (default `primary`), `text_color` / `outline_color` (default: the better of white and
  dark ink for the fill, the other for the outline), `spin` (burst), `sting` (`at: end` is an
  error; plays as the text pops in). The colour is a full-frame rectangle from frame 0 (an
  `iris_in` opens on the card). Silent with `duration` or narrated; `outro` 0.5. Targets `text`,
  `subtitle`, `burst` / `frame`.
- **Pure layout** (`cartoon/cards.py`, no manim): `card_layout(width, height, style=, subtitle=)`
  -> `CardLayout`; `burst_rays`, `burst_ray_color`; `card_text_inks(*backgrounds)` (white or
  `CHARACTER_INK`, the higher worst contrast, so lint's `contrast` passes); `card_outline_width`.
- **Drawing**: the outline is a layer of glyph shapes behind the text (a per-glyph background
  stroke covers the previous glyph); a `group` in the layout dump. Text pops with `pop_scale`
  (§69.40); the burst grows by `UpdateFromAlphaFunc`, not `GrowFromCenter` (an introducer is
  re-added over the text).
- **Screenplay** (§69.25): `# Card: TEXT` (any level; `:`, `.` or dash) is a
  `ScriptScene(card=True)`; `_add_card` writes a `card` scene, `duration: CARD_SECONDS` 2.5 without
  lines, else one beat per line (`[directions]` become `# TODO:` notes); `set:` under a card is an
  error. A card after another scene comes in with `iris_out`; the scene after it gets
  `transition: iris_in`. `vidgen screenplay` (also `--json`) counts a silent card's beats and
  characters as 0 and says "N scenes".
- Gallery `docs/gallery/card.md` (`vidgen gallery --types card`). Tests:
  `tests/test_cartoon_cards.py`.

### 69.47 More bodies and clothes (Step 113)

`config.CharacterLook` values drawn from primitives, side and front (§69.44). User keys:
docs/CONFIG.md "Characters". Shape constants live in `cartoon/` (`BODY_SIZES`,
`PROPORTION_FACTORS`, ...).

- **Bodies** `pear`, `triangle`; **`proportions`** `adult | kid | tall_kid` multiply the adult
  `Proportions` by `PROPORTION_FACTORS` before the seed's variation. The figure stays height 1; a
  kid's size is the stage `scale`, so seats, reach and lint keep one character unit.
  `Character.seated` puts the hips on the seat whatever the legs (`seated_sole`).
- **Outfits** (`cartoon/clothes.py`; `outfit` `plain | apron | dress | overalls | coat | shorts`,
  `colors.trim` default `dim`): `limb_colors` colours the §69.26 segments; body clothes are cut
  from its outline (`primitives.outline_polygon`, `clip_to_box`, `span_at`).
- **Skirts on the body**: skirt / coat tails (`SKIRTED_OUTFITS`) are in the `body` part so legs
  walk under them; such a body has a second shape `seated` (`config.SEATED_BODY_SHAPE`), shown by
  `Character.seated` and named by the `sitting` pose (`chosen_shape` falls back to the rest shape
  for others); `cast.character_part_shapes` lists it.
- **Patterns** `stripes` / `dots` in `pattern_tone`; **shoes** `shoes | boots`
  (`colors.accessory`) in the shin group, the figure's bottom stays at 0; **hair** `ponytail`,
  `braids`, `afro`; **`facial_hair`** `moustache`, `beard` (`colors.hair`); **accessories** `bow`,
  `cap` (head `accessory` part, `config.HEAD_ACCESSORIES`), `backpack`, `necklace`. `hat` with
  `cap` is a config error (§69.58's `TOP_OF_HEAD`).
- **Wind** (§69.32): `TRAIL_WEIGHTS` lives in `cartoon/primitives.py` (re-exported by the
  generator). **Effect symbols** (§69.40): afro, ponytail, braids, beard are marked
  `OUTER_HAIR_ATTRIBUTE`; `effect_symbols.head_box` leaves them out, `crown_top` counts them.
- **Invariant**: older looks draw exactly as before (pinned digests in
  `tests/test_cartoon_outfits.py`).
- **Tools**: the screenplay's `LOOKS` each carry a `voice_kind`; `vidgen character-sheet` has a
  `view` (`front`) section; `vidgen character` prints `wears:`; `still.write_looks_png(theme, path,
  entries)`. Tests: `tests/test_cartoon_outfits.py`.

### 69.48 Animal characters and the `tail` part (Step 114)

`look.species` (`config.Species`): `human` (default), `cat`, `dog`, `bird`, `bear`, `rabbit`,
`mouse` (more in §69.57, §69.58): generic animals in the look's colours, no feature from a known
character. `ears`, `nose`, `facial_hair` other than `none` with an animal are config errors
(`config.SPECIES_OWN_KEYS`); `svg` with `species` is the usual "svg draws the character" error.
User keys: docs/CONFIG.md "Animal characters (`species`)".

- **Drawing** (`cartoon/animals.py`, called by the generator): `HEAD_SHAPES`, ears, muzzle
  (`fur_tint`), snout, nose, beak; ears, snouts and beak are `OUTER_HAIR_ATTRIBUTE`. Paws; a bird's
  arms are `wing`s. `BEAK_COLOR`, `PINK` are fixed colours like `EYE_WHITE`, not theme tokens.
- **Mouth**: `mouth_place` moves the human mouth onto the muzzle (`MOUTH_PLACES`,
  `FRONT_MOUTH_PLACES`; a human's place is unchanged). A bird's `mouth` is `beak_mouth` (pivot the
  hinge; visemes open it by `BEAK_OPENINGS`); every shape is symmetric about the hinge line so a
  frown's negative y scale keeps it upright.
- **`tail` part** (`PART_NAMES`, `PosePart`, `DEFAULT_PARENTS` body, `DEFAULT_DRAW_ORDER` 5;
  optional): `tail_part`, pivot at the root. Motion: `motion.follow_angles` (spring, limit ±30°),
  `walking_state` swing, idle `idle.tail_sway_angle` (0 at clock start), wind `TRAIL_WEIGHTS`.
  An SVG `id="tail"` is that part (default pivot the bottom corner nearer the body;
  `TURNING_PARTS` pivot warning; `svg_character_parts` marks it trailing). Characters without a
  tail draw, pose and idle exactly as before (pinned in `tests/test_cartoon_animals.py`).
- `cast.character_part_shapes` adds `tail` for an animal; `vidgen character` prints `species`. An
  animal has no voice kind of its own unless the screenplay states one (§69.25). Tests:
  `tests/test_cartoon_animals.py`.

### 69.49 A random, well-contrasted cast (Step 115)

- **Contrast score** (`cartoon/contrast.py`, no manim): `look_features(look, colors, theme)` ->
  `LookFeatures` (silhouette values, resolved colours, a detail set; a bald head's hair colour is
  its skin, no accessories/shoes -> accessory colour = clothes); `None` for an `svg` look.
  `contrast_score(a, b)` (pure, symmetric, 0..1) = `WEIGHTS` silhouette 0.45 + colour 0.4 +
  accessories 0.15 of `contrast_parts`: silhouette by `SILHOUETTE_WEIGHTS` over differing
  features; colour by `COLOUR_WEIGHTS` of CIEDE2000 (`lint.color.lab` / `delta_e`) / `COLOUR_SPAN`
  30, capped at 1 (unresolved token: 0 if same name, else 1); accessories = Jaccard distance of
  detail sets (both empty: 0). `MIN_CONTRAST` 0.35.
- **Advice**: `compare(first, a, second, b) -> PairContrast(score, parts, shared, advice)`: shared
  non-default features and colours closer than `CLOSE_COLOUR` 10; `advice` names the keys of the
  three heaviest.
- **Lint `look_alike`** (scene scope, `lint/cartoon_rules.py`, `LookAlikeRule.min_contrast` 0.35,
  warning): `contrast.character_pairs(config, theme)` compares every two generated characters on
  the video's stages in first-appearance order, each pair tied to the scene where the later one
  first appears; the runner (`_timing_findings`) fills `SceneContext.character_pairs`
  (`Theme.for_format`). One finding per pair, at that scene's first beat, no objects.
- **Generator** (`random_cast.py`, no manim): `random_look(rng, kind, species)` draws every value
  and hex colours from fixed lists (`SKIN_COLORS`, `FUR_COLORS`, `CLOTHES_COLORS`, ...: same in
  every theme) only through `Random(seed).random()` (`_pick`, `_shuffled`; §69.1); never hat with
  cap; `KIND_EXCLUDES` keeps a look suited to its voice kind; adult proportions only.
  `pick_looks(kinds, rng, species, existing, curated, theme)`: the first unused `curated` look of
  the kind (then neutral) with `min_contrast` ≥ `MIN_CONTRAST` against `existing` and earlier
  picks; else `CANDIDATES` 48 random looks, greedy maximin (ties: first drawn); kind `None` takes
  the least-picked kind.
- **`vidgen cast --random N`** (`cli.cmd_cast`, MCP `cast`, `jsonout.cast_document`):
  `random_cast(count, seed, species, voice, language, taken)`: kinds from `balanced_kinds` (each
  round of three a shuffle of `VOICE_KINDS`); looks, names, voices from separate streams
  (`Random(3 * seed)`, `+ 1`, `+ 2`), so `--random 5` extends `--random 4`; names from
  `NAMES[kind]` (`_k` suffixes when exhausted); voices by `screenplay.assign_voices` (narrator
  `--narrator`, default `bf_emma`). Written with `plan_yaml.commented_yaml`; entries checked with
  `CharacterEntry`. 1-24 characters (`MAX_CAST`); `.yaml` only; an existing file needs `--force`.
  User side: docs/CONFIG.md "A random cast (`vidgen cast`)".
- **Screenplay** (§69.25): `_generated_looks` calls `pick_looks` with stated kinds, declared and
  cast characters as `existing`, `LOOKS` as `curated` (when `human` is in `--species`), the front
  matter's theme and `Random(--seed)`; after the curated looks come unused neutral ones, then
  random looks. `--species cat dog` (MCP `species`) gives only random animals. Tests:
  `tests/test_random_cast.py`.

### 69.50 Review of Phase K (Step 116)

- **Example** `examples/cartoon-muffin-mystery` (screenplay `muffin_mystery.md`, hand-edited
  `video.yaml`); `tests/test_phase_k_review.py` runs its cheap checks.
- **Held before entering**: `Stage._held_before_entering` finds props a `hold` gives to an
  `_entering()` character before its first `enter`; the construct puts each beside its holder off
  stage (§69.64), so the hold plays unseen.
- **Through doors**: `Walk` `fade_in` / `fade_out` (§69.42) scale `carried` props with the
  character; `enter` / `exit` with `door` pass held props (`moving._carried`, also for walks in
  depth).
- **Turning front**: `turn` `to: front` ends with `camera_look("front")`; `look_pose` facing front
  keeps the head upright and moves only the eyes.

### 69.51 Props that vanished, overlapped or showed through (after Step 116)

- **Moving list never drops a thing**: `get_moving_mobjects` (§69.44) marks everything from the
  first thing a walk in depth passes as moving; Manim draws the rest once as a static image.
  `Stage._moving_in_order` keeps everything the list had and adds what moves now, in draw order, so
  a mid-play rebuild by `_draw_order_step` cannot leave a prop drawn by neither.
- **`prop_overlap` lint rule** (warning, `min_overlap` 0.15 of the narrower width): two floor props
  less than `DEPTH_APART` 0.15 apart in depth whose boxes overlap sideways; lifted, hung, flat and
  held props are skipped. Layout dump on a prop: `prop` (kind), `depth` (above 0), `raised` and
  `flat` (only when true); `Prop.raised` set from `lift` + hang height. A still rule like
  `character_overlap`; the runner merges a pair's findings over beats.
- **Set fades as one picture**: the entrance adds set, props, shadows and characters at once, back
  to front, under `Stage._cover` (a camera-background rectangle 1.5 × the view) that fades out; a
  `carry:` copy still moves in. `Stage.finish` fades the same cover in over everything (z index
  above all) over `outro` seconds, then removes every mobject. With no outro, a transition other
  than a cut, or a next scene that carries something (`carry:`), it falls back to
  `NarratedScene.finish` (§49, §50). While the light changes, a character's moving part is never
  listed again after everything (it would draw over the cover).

### 69.52 Vehicles on the ground (Step 118)

A vehicle is a built-in prop (§69.8): placing, `scale`, `facing`, colours, depth, shadows, light,
layout dump and prop checks work as for any prop; riding is a posture like sitting (§69.28). User
keys: docs/CONFIG.md "Vehicles (`get_in`, `ride_to`, `get_out`)".

- **Geometry** (`cartoon/vehicles.py`, no manim): `VEHICLES` kind → `VehicleSpec` (prop units,
  facing right, from character heights): `height` (`PROP_HEIGHTS` reads it), `seats` (front
  first), `seat`, `floor`, `wheels`, `half_length`, `hides_legs`, default `speed`, bicycle `crank`
  / `grip`. Pure: `seat_origin`, `seated_height`, `get_in_gap`, `place_order` (nearest seat
  first), `wheel_degrees` (one turn per circumference), `crank_degrees`, `pedal_points`,
  `ride_facing`. Ride time = `walk_seconds` at the vehicle speed; in depth `depth_walk_distance`.
- **Drawings** (`cartoon/vehicle_drawing.py`): original shapes in the prop's `PROP_COLORS`; glass
  windows (`GLASS_OPACITY`) show riders drawn before the vehicle while its side hides their legs.
  Wheel / crank places come from the spec. `draw_prop` returns a `Prop` with anchor, `wheels`,
  `crank`; `Prop.turn_wheels(degrees)` (mirrored facing left; `wheel_angle` / `crank_angle`),
  `Prop.prop_point(x, y)`, `Prop.unit`. `write_props_png(..., kinds=VEHICLE_KINDS)`; `props.png`
  leaves vehicles out.
- **Riders** (`cartoon/riding.py`): never added to the vehicle (§69.22). `RiderSeat` (rider,
  vehicle, place, `ratio`) and `place_rider` put the feet on the seat's floor point at `ratio` ×
  the vehicle unit, facing its way, with its `stage_depth` / `ground_y`; an updater calls it every
  frame and `Ride` calls it too (Manim pauses an animated character's updaters). `riding_state`
  seats the rider; on a bicycle it leans, plants the feet on the pedals (`Character.planted`,
  §69.26) and reaches to the grip. `Ride(vehicle, x, seats=, speed=, depth=, feet_y=, strength=)`
  turns the vehicle to its direction at once, moves along `walk_progress`, scales about its feet in
  depth, turns wheels, re-plants cyclist feet. `BodyMove(y=)` eases the feet's y.
- **Actions** (`scenes/riding.py`, against `vidgen.api`): `get_in` (`to` a vehicle; 1.0 s): nearest
  free seat (`Postures.ride`), `BodyMove`, follow updater, `Character.riding`; drawn right before a
  car / bus, right after a bicycle. `ride_to` (vehicle or rider; `to` a place or `{mark, depth}`,
  `depth`, `speed`): a `Ride` per vehicle; in depth registers with `Stage.ride_in_depth`.
  `get_out` (0.9 s): updater off, `Postures.get_out`, `BodyMove` back, drawn right after the
  vehicle. Riding counts as posed (`is_posed`): looks turn only the head, poses move only arms and
  head.
- **Stage**: vehicles are movable props when a `ride_to` is used (`ShadowCaster(grows=True)`,
  `Prop.standing_height`); riders cast no shadow. The §69.44 keeper moves a vehicle with riders and
  their held props as one block (`_moving_block`); `_depth_crossers` knows `Ride`.
- **Validate** (`holding_problems(vehicles=)`, `StageFrame.vehicles`): `get_in` beyond
  `GET_IN_REACH` 0.5 heights from the vehicle's end or at another depth (suggests the `walk_to`); a
  full vehicle; `ride_to` of a non-rider; `get_out` without `get_in`; pinned actions (§69.28) and
  `stand_up` / `sit_on` / `lean_on` while riding; `pick_up` / `hold` of a vehicle; `keyframes` /
  `move_along` of a ridden one. The replay moves riders and vehicles. `scene_problems`: `to` /
  targets that are not vehicles.
- **Sound and effects**: `ride_cues` (`RIDE_SOUNDS`, `BRAKES`, `ENGINE_SHARE`; sounds generated in
  `sfx.py`); `motion_effect_cues` treats `ride_to` as a walk (dust, speed lines from `FAST_SPEED`).
- **Planner, shots**: `_follow_written` replays the three actions (`_riding`); they are
  `LOOK_CHANGING` and `MOVING_ACTIONS`. `follow` of a vehicle (its box) or rider (its feet) tracks
  the ride; a beat's `shot` is framed where riders are at the beat's start. Layout key `riding`;
  `character_overlap` / `walk_overlap` skip two riders of one vehicle; `hidden_speaker` ignores a
  rider's own vehicle. Tests: `tests/test_cartoon_vehicles.py`.

### 69.53 Vehicles on the water and in the air (Step 119)

`boat`, `hot_air_balloon`, `toy_rocket`: vehicle props as in §69.52; only the path differs. User
keys: docs/CONFIG.md "Water and air vehicles (`water`, `land`)".

- **Geometry**: `VehicleSpec.medium` (`ground` / `water` / `air`; `GROUND_VEHICLES`,
  `WATER_VEHICLES`, `AIR_VEHICLES`, `medium(kind)`) and `.stands` (riders stand). The balloon is
  2.1 character heights tall (riders are full size); the rocket has no seats (`get_in` refused in
  `scene_problems`). `ROCKET_ASCENT_SHARE` is shared by foley and paths. Only ground vehicles turn
  wheels.
- **Paths** (`cartoon/vehicle_paths.py`, pure, seeded): `Course(kind, start, end, rise, drift,
  land, seed).at(share)` → feet (x, y) and turn. Ground / water straight, walk-eased;
  `balloon_point` rises, cruises with a drift `drift·sin(πs)` (0 at both ends, so it lands at
  `to`) and lands; `rocket_point` arcs up, then parachutes down upright; `land=False` keeps going
  out of the frame. `balloon_seconds`, `rocket_seconds`. Water: `wave_offset`, `front_outline`,
  `boat_bob`, `bob_phase(name)`. Smoke: `smoke_puffs(age, course, seconds, size, seed)` while
  `Course.powered()`.
- **Drawings**: the rocket has shapes `folded` and `chute` (`PROP_SHAPES["toy_rocket"]`,
  `VehicleDrawing.shapes`). Every vehicle has an anchor; `Prop.pose_at(x, y, degrees)` undoes its
  `tilt` about the feet and sets place and turn.
- **Water** (stage param `water: true | {left, right, color}`; `cartoon/water.py` `StageWater`):
  a band in the backdrop after the ground band and a front strip first in the foreground, over the
  keels. Scene updater `_water_step` moves waves and bobs boats about `Prop.afloat`, re-placing
  riders after. Waves drift right (left with negative `wind`). `get_moving_mobjects` redraws from
  the first boat on. Boats cast no shadow. A boat needs water, its `at` on it (its middle), depth
  0; water and water / air vehicles in a `room` are refused.
- **Rides** (`Ride(..., rise=, drift=, away_y=, seed=)`): a boat updates `afloat`; a flying
  vehicle's `Course` is built in `begin` (and `__init__` for run time); `interpolate` calls
  `pose_at`; a rocket shows `chute` from the top of a landing flight, `folded` at touchdown; `Ride`
  sets `Prop.flight = (course, seconds)`. `RideTo._flight` (`scenes/riding.py`): rise
  `BALLOON_ALTITUDE` / `ROCKET_APEX` capped so the top stays `FLIGHT_MARGIN` under the frame top, at
  least `LOWEST_RISE`; balloon drift `BALLOON_DRIFT` × the stage's wind level; `land: false` →
  `away_y` above the frame; seed from scene and vehicle name. No riding in depth on water or air.
- **Validate** (`holding_problems(water=)`, `StageFrame.water`): boat `to` off the water; `depth`
  for a non-ground vehicle; `land: false` for a non-air one; any later use of a vehicle that flew
  away or its riders (the planner `_riding` marks them gone too).
- **Sound and effects**: `RIDE_SOUNDS` boat `engine`, balloon `burner`, rocket `launch`; with
  `PlayedAction.lands` a parachute `pop` and a touchdown `thud`. No dust or speed lines on water or
  in the air; a rocket's `smoke` cue (`MOTION_EFFECT_KINDS`, `MotionEffect._smoke` from
  `Prop.flight`). Tests: `tests/test_cartoon_water_air.py`.

### 69.54 Props that move by themselves, indoors (Step 120)

A `clock` runs, a `tv` flickers, a `lamp` glows. Every other prop, and these while they never run
or come on, draw exactly as before. User keys: docs/CONFIG.md "Clocks, televisions and lamps
(`time`, `on`, `switch_on`)".

- **Maths** (`cartoon/living.py`, no manim): `parse_clock_time` (`H:MM` / `H:MM:SS`,
  0:00–23:59:59), `clock_seconds(start, speed, t)`, `hand_angles` (clockwise from twelve),
  `shows_second_hand(speed)` (up to `SECOND_HAND_MAX_SPEED` 10), `MAX_CLOCK_SPEED` 3600.
  `switched_on(on_at_start, switches, t)` (last `(time, on)` at or before `t` wins),
  `switch_between`, `on_between`. `tv_shot`, `tv_flicker`, `tv_picture` (`TV_PALETTES`); `GLOWS`,
  `glow_rings` (`GLOW_RINGS` 12 discs stacking to the given opacity), `redrawn_members`. Seeds are
  `random.Random` of a text key.
- **Drawing** (`cartoon/living_drawing.py`): `draw_prop(kind, ..., living=True)` (`LIVING_KINDS`)
  adds `living_overlays` and an anchor; overlays lie inside the prop box, so feet, size, shadow
  and layout dump do not change. `LivingProp(prop, start, speed, on, seed, movable)` `update`s
  them per scene time (hands from the screen position of the clock's middle, so a left-facing
  clock still runs clockwise). `PropGlow` is its own mobject right before the prop, never graded
  (§69.31); lit overlays are not graded (`LIT` cleared), hands are. Glows are not in the layout
  dump.
- **Stage**: prop keys `on` (switched props), `time` and `speed` (`clock`; either makes it run:
  `StageProp.runs`, `clock_start`); each is a config error on other props; `StageProp` takes YAML
  1.1's bare `on` → `true` key as `on`. `_living_names`: running clocks and switched props that are
  `on` or named by a `switch_on` (globs too); only those draw `living`. `_start_living` (after
  `mark_lit`; seeds `motion_seed(scene, name)`), scene updater `_living_step`. `switch_props`
  records switches and plays `click` with foley.
- **Actions** (`scenes/switch_action.py`): `switch_on` / `switch_off`, non-animating like `light`,
  instant; `scene_problems`: not a prop, a prop that does not switch, not a stage.
- **Only moving parts leave the static image** (§69.20): `get_moving_mobjects` ends with
  `_living_redrawn`. For each `LivingProp` that `changing(start, end)` (a running clock; a tv while
  on; a lamp when a switch falls in the span, or while on if an action may move it), its movers are
  redrawn every frame, plus every member drawn after the first mover whose box overlaps a mover's
  region (+ `REDRAW_MARGIN`) or an already redrawn member (`redrawn_members`). Everything else stays
  static; Manim's own moving list is kept; the result is in draw order. A lamp does not light
  characters. Tests: `tests/test_cartoon_living.py`.

### 69.55 Props that move by themselves, part 2: fire, steam, nature (Step 121)

Seeded and pure; nothing changes for a scene that uses none of it. User keys: docs/CONFIG.md
"Fireplaces and kettles", "Fruit falling from a tree", "Birds".

- **Fire and steam** (`cartoon/living.py`): `flame_shapes(t, seed, lean)`, `flame_lean(force)`,
  `fire_flicker` (glow strength), `steam_puffs(t, seed, lean)`, `steam_box`, `on_spans(on,
  switches, end)`. `SWITCHED_PROPS` lists every prop that takes `on` / `switch_on`.
- **Drawing** (`cartoon/props.py`, `living_drawing.py`): `fireplace` (furniture), `kettle`. A
  living fireplace has `flame` members before its front logs; `LivingProp._burn` redraws them
  (`closed_curve`, a vectorised Catmull-Rom, then one `Prop.prop_points`); a kettle gets a
  `PropSteam` right after it, graded (flames and glow are not). `LivingProp(wind=)` =
  `Stage._felt_wind` when the stage's wind may blow, else `None`.
- **Fruit** (`cartoon/nature.py`): stage key `fruit` (trees only) → `draw_prop("tree",
  fruit=True)` adds 4 fruit (`FRUIT_SPOTS`, tagged `FRUIT_INDEX`; tree box unchanged).
  `drop_timing`, `drop_point`, `fruit_to_drop`. `Stage.drop_fruit(tree, onto)` (`drop_fruit`
  action): hides the fruit on the tree (tree stays static), adds a `FallenFruit` after the tree,
  plays `FruitDrop` (`PropMove` with `path`, `lands_at` = impact → `thud`). No `to`: to the ground
  and bounces; `to: <character>`: the fruit nearest above the head hits it and `hit_stars` (the
  `stars` symbol, in `Stage.motion_effects`) circles the head; no fruit above: to the ground.
  Validate: not a tree / no fruit, `to` not a character, a fifth drop (`_fruit_count_problems`, in
  `action_sequence_problems` before its early return). A fallen fruit is not a prop.
- **Birds** (`nature.py`, `nature_drawing.py`): `flock_birds`, `wing_lift`, `flock_plan` (default
  `FLOCK_SPEED` 0.2 frame widths/s), `bird_place` (`None` outside its time), `flock_box`. `Flock`
  (graded) is drawn right after the sky (`Stage._sky_end`, `_put_in_sky`). Stage param `birds`
  (`StageBirds`: `true`, a count, or {count, direction, height 0.5–0.97 default 0.8, start 0.5 s,
  seconds, seed}) and non-animating action `birds` (`FlockSettings`; a number target is the
  count); both refused in a room. Default seed `motion_seed(scene, "birds", k)`.
- **Redraw** (§69.54): `_living_things` = living props and flocks (and §69.60–61's layers, fog,
  rainbows), each with `changing(start, end)`, `movers()`, `region(start, end)`; `_living_step`
  removes itself once only finished things are left.
- **Sound** (`ambience.py`, `mix.py`): `fire_loop()` (seeded `crc32("ambience:fire")`) at
  `FIRE_LEVEL` −34 LUFS; `BEDS` holds each bed's loop, duck and fades; `plan_ambience` places every
  bed of `AMBIENCE_BEDS` the same way. `Stage.timings()` adds `{bed: fire}` per burning fireplace's
  `on_spans` with foley. Lighting a fireplace plays `burner` instead of `click`.
- Layout dump leaves out `PropSteam`, `Flock`, `FallenFruit`. Tests:
  `tests/test_cartoon_fire_nature.py`.

### 69.56 Everyday small props (Step 122)

`SMALL_PROPS` (`cartoon/props.py`, in `PROP_KINDS` after `kettle`): `cake`, `muffin`, `book`,
`phone`, `letter`, `gift`, `balloons`, `vase`, `watering_can`. Fixed hex only where no token fits
every theme (`CANDLE_FLAME`, `PAPER`, `BALLOON_STRING`, ...). User keys: docs/CONFIG.md "Everyday
small props (`let_go`, `pour`)".

- `book`, `letter`, `gift` have shapes `closed` / `open` (`PROP_SHAPES`, §69.37; both one prop unit
  tall), so `open` / `close` / `open: true` work. Grips in `PROP_GRIPS` (`BALLOON_KNOT`,
  `WATERING_GRIP`); `WATERING_SPOUT`.
- **Held** (`cartoon/holding.py`, `scenes/handling.py`): `OVERHEAD_PROPS` = {umbrella}
  (`is_overhead` checks the kind too). `FULL_SIZE_HELD` = {balloons}: `held_height(...,
  full_size=True)` (not `HOLD_MAX_HEIGHT`), drawn right before the holder. `_moving_block` also
  takes props held right before a walker.
- **Ringing phone**: on = ringing; living: lit `screen` (never graded) and `ring` lines.
  `on_since`, `ring_burst` (`RING_BURST` 1 s every `RING_PERIOD` 2 s), `ring_shake`. `LivingProp`
  keeps the whole drawing in prop units (`Prop.drawn_points`, inverse of `prop_points`) and redraws
  it turned about `PHONE_CENTRE` each ringing frame (absolute, so holding or a `PropMove` never
  accumulates a turn). `Stage._ring_sounds` (after `finish`, with foley) records `phone` per
  `ring_bursts(on_spans(...))`; switching a phone on plays no `click` (off does, and answers it).
- **Balloons let go** (`cartoon/small_props.py`, no manim): `FLOATING_PROPS` = {balloons};
  `float_end` (drift by the felt wind), `float_progress`, `float_point` (seeded sway),
  `float_seconds` (1–6 s). `let_go` (character, `prop`): releases, arm back,
  `PropMove(path=float_point)`; the prop is detached and gone for the scene.
- **Pouring**: `POURING_PROPS` = {watering_can}; `pour_tilt`, `pour_flow`, `pour_drops` (seeded).
  `pour` (character, `prop`, `POUR_SECONDS` 2 s): `Pouring` (the can turned about its grip,
  clockwise when the spout points right, grip at the hand each frame; a can whose spout points
  behind the holder is flipped first, §69.64) and `WaterFlow` on `WaterDrops` (graded, inserted
  after the can, removed after; not in the layout dump).
- **Validate**: `holding_problems(kinds=)`: `let_go` needs a held floating prop (else "'cake' does
  not float away ...; put_down it instead") and later uses are reported; `pour` needs a held
  pouring prop; `prop` options checked in `scene_problems`. `LIGHT_PROPS` includes `letter`,
  `balloons`.
- `write_props_png` leaves `SMALL_PROPS` out by default. Tests: `tests/test_cartoon_small_props.py`.

### 69.57 More animals: fox, owl, frog, turtle, penguin (Step 123)

`config.Species` includes `fox`, `owl`, `frog`, `turtle`, `penguin` (generic; §69.48 rules hold).

- **Drawing** (`cartoon/animals.py`): `HEAD_SHAPES`; `SPECIES_PROPORTIONS` multiplies
  `Proportions` after `proportions` and before the seed. Owl uses the bird's wings and shins
  (`WINGED`); frog has eye bulges (`species_frame` replaces `head_y` / `eye_y`) and no tail
  (`config.SPECIES_WITHOUT_TAIL`, also in `cast.character_part_shapes`); turtle has a `shell`
  (`colors.hair`) on every `body` shape; penguin `flipper` arms. `tapered_band(profile=...)` for the
  fox's tail.
- **Beaks**: `BEAKS` per `BEAKED` species (bird, owl, penguin); `beak_mouth(species, ...)` scales
  against the bird's (bird unchanged). Fox, frog, turtle in `MOUTH_PLACES` / `FRONT_MOUTH_PLACES`.
- **Moving** (`cartoon/acting.py`): `SpeciesMotion(gait, speed, jump)`, `SPECIES_MOTIONS`
  (turtle slow, penguin waddle, frog high jump); others `PERSON_MOTION`. `build_character` sets
  `Character.species_motion`; `Walk` uses `species_motion.walking(gait)` (a run keeps `RUNNING`
  with the waddle). `Gait.waddle` → `WalkCycle.rock`; `walking_state` rocks the body, legs kept
  upright. The species factor applies only when the YAML gives no `speed` (`model_fields_set`),
  and `jump` only without `height`. The screenplay plans walk times at a person's speed.
- **Contrast** (§69.49): `species_difference` counts two species of one `SPECIES_FAMILIES` family
  0.5 apart; a turtle's hair colour (shell) is compared. `random_cast` draws from `SPECIES_COLORS`
  / `SHELL_COLORS` (other species' picks unchanged).
- Earlier species and human looks draw exactly as before (pinned in
  `tests/test_cartoon_animals.py`). Tests: `tests/test_cartoon_more_animals.py`.

### 69.58 Robots and costumes (Step 124)

`species: robot` with `look.robot` (`config.RobotLook`: `head` box | round, `face` eyes | screen,
`antenna` true | false, `moves_on` legs | wheels; `CharacterLook.robot_look()` gives defaults).
`ROBOT_OWN_KEYS` (`ears`, `nose`, `facial_hair`, `hair`) are not given with a robot; `robot` with
another species and `shoes` on wheels are config errors. `animals.is_animal` is false for a robot;
`SPECIES_WITHOUT_TAIL` holds it. User keys: docs/CONFIG.md "Robots and costumes".

- **Drawing** (`cartoon/robots.py`): eyes, brows, mouth are the person's parts; on a screen drawn
  with `features` = `SCREEN_GLOW` (`face_colors`, `screen_eye`), so visemes, blinks and expressions
  show. On wheels each shin ends at a `wheel` with the sole still at 0 (seats, planting, grounding
  unchanged).
- **`antenna` part** (`PART_NAMES`, `PosePart`, `SVG_PART_NAMES`; parent `head`, draw order 49):
  shapes `default` and `dim` (`idle.ANTENNA_DIM_SHAPE`); trails, follows (`follow_angles`), idle
  overlays `antenna_sway_angle` / `antenna_light_on`. `crown_top` counts it.
- **Moving**: legged `SPECIES_MOTIONS["robot"]`; wheels `ROLLING_MOTION` (`Gait(..., rolls=True)`):
  `species_motion(species, wheels=)`. `Gait.rolls` → `foley.PlayedAction.rolls`: no footsteps.
- **Costumes** (`cartoon/costumes.py`; `Accessory` `crown`, `wizard_hat`, `party_hat`, `cape`):
  hats in the `accessory` part (`HEADWEAR_DRAWINGS`, `HEAD_ACCESSORIES`). `config.TOP_OF_HEAD`
  (hat, cap, crown, wizard_hat, party_hat): at most one per look ("X and Y are both worn on top of
  the head").
- **`cape` part** (parent `body`, draw order 3, pivot at the neck): trails, follows, flutters in
  `walking_state`; `cape_clasp` over every body shape.
- **Voice**: `[beep]` (`VOICE_SOUNDS`, said `Beep boop!`, face `happy`, viseme `E`) with built-in
  sound `beep`, like a gasp (§69.33).
- **Cast and contrast**: `cast.character_part_shapes` adds `antenna` (`default`, `dim`) and `cape`;
  `vidgen character` prints e.g. `species robot (box head, eyes face, antenna, legs)`.
  `contrast.HEADWEAR` includes the three hats; robot details count in contrast. `random_cast` draws
  robot plating / build (`SPECIES_COLORS["robot"]`, `ROBOT_CHOICES`) only for robots; costumes are
  never random. Earlier looks draw as before. Tests: `tests/test_cartoon_robots.py`.

### 69.59 More expressions (Step 125)

`poses.EXPRESSIONS` adds `laughing`, `blushing`, `tongue_out`, `crying`, `dizzy`, `frightened`
after the seven of §69.3, on every generated look, side and front; SVG characters fall back
through their shape lists.

- **Parts and shapes**: optional `ExpressionPart`s, children of `head` (not in `SVG_PART_NAMES`):
  `cheeks` (draw order 55; `none`, `blush`, `tears`, `tears_running`) and `bristles` (48; `none`,
  `up`). Rest shape `none` draws nothing (`expression_shapes.nothing`). Eyes add `laughing`, `wide`,
  `swirl`, `swirl_turned`; mouth `laugh`, `tongue`, `wavy`; all appended after earlier shapes
  (`cast.GENERATED_SHAPES`), so rest shapes and shape order stay. Drawing:
  `cartoon/expression_shapes.py`; beak versions in `animals.beak_mouth`.
- **Sizes stay**: `generator._scaled_to_unit_height` ignores `EXPRESSION_ONLY` shapes;
  `drawing_digest` in tests leaves them out, so earlier pins hold.
- **Moods** (`idle.py`; overlays in `Character._idle_step`, never in `state()`): `shape_mood` picks
  the first `MOOD_SHAPES` match (`eyes swirl` → `sway`, `eyes wide` → `shiver`, `mouth laugh` /
  `cheeks tears` → `bounce`), so own expressions with these shapes move too. `IdleClock.set_mood` /
  `mood_levels`: moods rise and die on `MOOD_SPRING` (never below 0, dropped after
  `MOOD_SETTLE_SECONDS`), so nothing jumps; the clock stops during a `PoseChange`. `mood_motion`
  keeps the feet in place. `idle: false`: no mood motion.
- **Eyes and tears**: no blink over `BLINKLESS_EYES`; `ALTERNATE_SHAPES` swaps `swirl` ↔
  `swirl_turned`, `tears` ↔ `tears_running` every `ALTERNATE_SECONDS` 0.2 s. Visemes show over the
  expression's mouth during words (§69.4).
- **Mappings**: `[laugh]`, `[giggle]` → `laughing`; `[gasp]` → `surprised`; screenplay `MANNERS`
  map the six names and synonyms; `EXPRESSION_EFFECTS`: `dizzy` → `stars`, `frightened` → `sweat`
  (`crying` has none; the `tear` symbol, §69.40, is for `[cries]`). `react`, `emote`, stage
  `expression` and the character sheet read the tables. Tests: `tests/test_cartoon_expressions.py`.

### 69.60 More weather, part 1: snow that settles, fog (Step 126)

Seeded, pure, outdoors only; a scene without them renders as before. User keys: docs/CONFIG.md
"Snow that settles (`settle`)", "Fog (`fog`)".

- **Settling snow** (`cartoon/snow.py`, no manim): `ParticleSettings.settle` (snow only,
  `settle_problem`, like `puddles`) and `settled` (seconds already lying, 0–600, needs `settle`).
  A settling field gets `snow_ground`; a `RainGround` shelter may be a `TopLine(xs, ys, feet)`
  (`top_at(x)`, `covers`) besides a `ShelterBox`. `flake_floors`, `rest_flakes` (a flake lies on
  its floor, fades, hides until it wraps). `ParticleField` splashes only for rain.
- **The layer**: `settled_seconds` counts snowfall in `SETTLE_STEP` 0.5 s steps (frozen at the
  field's end; never melts); `settle_amount(seconds, density)` = seconds × density /
  `SETTLE_SECONDS` 24, ≤ 1. `blanket_outline` (to the ground area's back edge), `blanket_cover`,
  `bare_patches(shelters)` (holes by winding under trees and unmoved open umbrellas, covered by
  thin snow, since bare holes show the dark ground). Caps: `curve_segments`, `top_line(segments,
  columns)` (highest crossing per column, not point samples, which leave spikes), `cap_thickness`
  (full only on slopes ≤ `CAP_SLOPE` 45°), `cap_outlines`, `cap_full_thickness`. `SNOW_COLOR` or
  the field's first `color`.
- **Drawing** (`cartoon/weather_drawing.py`): `SnowBlanket`, `SnowCap`, `SettledSnow` (`update`
  redraws only when the step changes; `changing`, `done`, `movers`, `region`); `prop_top_line`.
- **Stage**: `snow_ground()` = rain's band, open umbrellas (`_shelter_of`) and `_snow_tops()` of
  ground props that no action moves, not lifted / hung / `FLAT_PROPS` / water or air vehicles /
  umbrellas / held. `_settle_snow`: blanket laid like puddles (`_lay_on_ground(under_water=True)`),
  a cap right after each prop (`_put_after_prop`, `_after_props` for the entrance), none on `SWAYS`
  kinds when wind may blow; all lit. `Stage.snow_layers`. No snow on characters or held props.
- **Fog** (`cartoon/fog.py`, no manim): bands at `FOG_DEPTHS` (1, 0.8, 0.6, 0.4, 0.2);
  `band_opacities(density)` so the bands in front of depth d hide `1 − exp(−FOG_THICKNESS ×
  density × d)`; `fog_cover(depth, density, high=False)` (0 at depth ≤ 0.2; the sky = every band).
  Each band has `FOG_LAYERS` 3 layers sharing its optical depth exactly: a haze to the frame top
  (so deep tree crowns fog too) and two wavy banks. `band_outlines`, `band_box`, `fog_shift(t,
  blown, depth, drift)` (nearer bands drift faster).
- **Fog on the stage**: `FogBand` (depth in `stage_depth`, not Manim's `Mobject.depth`, the z
  extent), `StageFog`. Stage param `fog` (`StageFogSetting`: `true`, a density, or {density, color,
  drift, seed}; `false` is an error; refused in a room). `Stage._fog()` (lit; `blown` from
  `particle_wind`; seed `motion_seed(scene, "fog")`); `_sort_fog()` puts each band right before the
  first character or prop (held props excepted) at its depth or nearer, else before the foreground
  or the first particle field; it runs in the entrance and every frame of a walk in depth
  (`_draw_order_step`); `_depth_crossers` adds bands a walker passes. Room windows show no fog;
  particles stay in front of it.
- **Redraw** (§69.54): a layer redraws itself and what stands in front only in animations where a
  step passes; moving fog redraws everything from the back band on. Tests:
  `tests/test_cartoon_snow_fog.py`.

### 69.61 More weather, part 2: lightning, rainbows, the sun and moon moving (Step 127)

User keys: docs/CONFIG.md "Lightning and thunder (`lightning`)", "Rainbows (`rainbow`)", "Light
and shadows" (`move_sun`).

- **Strikes** (`cartoon/storm.py`, no manim): `Strike(time, x, distance, seed, bolt)` with seeded
  `pulses` (`strike_pulses`, `FLASH_PULSES`, `FLASH_TAIL`); `level(now)` = `flash_strength(distance)`
  × brightest pulse. `flash_level`, `flashing(strikes, start, end)`, `flash_grade(grade, level,
  share=FLASH_SHARE 0.5)` (towards `FLASH_COLOR`; stars and shadow dimmed).
- **Thunder**: `thunder_delay(km) = km / 0.343` s; `thunder_cue(km)` (quieter, longer, lower with
  distance), `thunder_pan(x)`. Built-in `thunder` (`sfx._thunder`). `Stage._thunder` cues it with
  foley (a project file `thunder` plays as is).
- **Rain storms**: `ParticleSettings.lightning: bool | float (2..120)` (`storm_problem`: rain
  only; `storm_every`: 8 s for `true`). `storm_strikes(start, until, every, seed, stop)` is a
  prefix of the same seeded sequence whatever `until`. `RainStorm(start, every, seed, ended)`.
  `Stage.particles_started` adds one per rain field with `lightning`; `_storm_thunder` (after the
  scene) cues thunder that starts before the scene's end.
- **Flash** (`shading.StageLight`): `strikes`, `storms`, `flash_share` (× `ROOM_FLASH` 0.5 in a
  room), `strikes_until(t)`; `update` grades `light_at(...)` then `flash_grade`; `changing` and
  `settled` count strikes and storms. The light is installed from the start when the scene may
  flash (`Stage._lightning_used`), so a stage without a background gets the lit background
  rectangle (same pixels). `get_moving_mobjects` redraws everything in an animation where a flash
  falls. `room.flash_sky` lights room window skies.
- **Bolt** (`weather_drawing.LightningBolt`, not graded, named `lightning`): one per outdoor stage
  that may flash, right after the sky; `Stage._show_bolt(now)` (in `_sky_step`) shows the
  brightest strike with a bolt from the frame top to the horizon (`_horizon_y`) at `left + strike.x
  · stage_width` (`bolt_paths`, cached per seed); hidden otherwise.
- **`lightning` action** (`scenes/storm_action.py`, non-animating, `run_time` `FLASH_SECONDS` 0.7,
  `number_target`): target a mark or an x, `distance` (0..10 km), `bolt`, `seed`; `cue` →
  `Stage.strike_lightning` (no place: x from the seed; seed default `motion_seed(scene,
  "lightning", time)`; no bolt in a room). Validate: a stage scene, one place, a known mark or x.
- **Rainbows**: `rainbow_bands`, `RainbowChange`, `rainbow_level`; `Rainbow`, `StageRainbow` (a
  §69.54 living thing, in `Stage.rainbows`). `rainbow` action (non-animating, `run_time` 3): target
  the middle (default `centre`), `width` (frame widths, 0.75), `opacity` (0.55), `hide` (fades all
  out; no place); refused in a room. `Stage.show_rainbow` puts it after the sky, lit, on the
  horizon; `hide_rainbows`.
- **Sun and moon path** (`cartoon/sun_path.py`, no manim): share 0 (left horizon) .. 0.5 (top) .. 1
  (right horizon), hidden `PATH_HIDDEN` beyond, one round `PATH_ROUND` (`wrap_share`);
  `PATH_PLACES` per light preset for sun and moon; `path_blend` moves forward only; `PathMove`,
  `path_share_at`, `path_point`, `elevation`, `shadow_cast(s)` → (stretch ≤ `MAX_SHADOW_STRETCH` 3,
  side), `cast_shadow(ellipse, stretch, side)` (foot stays).
- **Moving them** (`light` option `move_sun`; validate: a preset, outdoors, a `sun` or `moon`
  prop): `Stage._start_sky_path` makes every sun / moon prop a `SkyBody`;
  `change_light(..., move_sun=True)` adds a `PathMove` per body; `_sky_place`; `_sky_step(now)`
  (in `_light_step` and `get_moving_mobjects`, before the light update) places bodies, sets every
  shadow group's `set_cast` from the body that shows most (the sun on a tie) and shows the bolt. A
  sun move comes only with a light change, so the whole stage is redrawn meanwhile.
- Outro: §69.51. Tests: `tests/test_cartoon_storm.py`, `tests/test_cartoon_depth.py`.

### 69.62 More sounds: door creaks, knocks, splashes, the set's ambience (Step 128)

User keys: docs/CONFIG.md "Ambience and door sounds (`ambience`, `knock`)".

- **Built-in sounds** (`sfx.py`, finished as §47): `creak`, `knock`, `splash`; `bell`, `engine`,
  `phone` (§69.52, §69.56) serve bicycle, engine and ringing.
- **Set beds** (`ambience.py`, numpy, seeded `crc32("ambience:<bed>")`, circular, `_leveled` to
  integrated loudness, as rain and fire): `birdsong_loop`, `city_loop`, `room_tone_loop`, with
  ducks (`BIRDSONG_DUCK`, `CITY_DUCK`, `ROOM_TONE_DUCK` 0) and `SET_FADE_IN` / `SET_FADE_OUT`; all in
  `AMBIENCE_BEDS` / `BEDS`, so `plan_ambience`, the mix report and the shift to video times handle
  them.
- **Which bed** (`set_ambience(setting, room=, lights=, rain=, end=)`, pure): `False` none; a list
  of `SET_BEDS` names: each for the whole scene (deduplicated, in order); `True` (automatic): a room
  → `room_tone`; outdoors `birdsong` over spans whose light is in `DAYLIGHT` (`day`, `morning`; a
  tint is not), minus rain spans extended by `BIRDS_AFTER_RAIN` 2 s, spans under
  `MIN_BIRDSONG_SECONDS` 2 s dropped; `city` never automatic. `Stage.set_beds(rain, end)`: none
  without foley; the stage's `ambience` (`auto` / `true`, a bed name or list, `false`), else the
  top-level `ambience` (bool, default `true` = automatic; on by default because nothing tells an
  old project from a new one). `Stage.light_marks`: `(0, params.light)` and per `change_light`
  `(start + seconds / 2, preset or None)`. `Stage.timings()` appends the beds after rain and fire.
- **Door foley**: `_played` maps a `PropReshape` to `PlayedAction(prop=kind)` and a `Walk` to
  `through_door` (§69.42) and `opens_door` (`Walk(opens_door=)`, set by `enter` / `exit` from
  `_door_closed` before `_door_x` opens it). `door_cues`: `open` → `creak` at the start; `close` →
  a shorter `creak` then `thud` at `RESHAPE_SHARE`. A walk through a door plays no whoosh, and a
  creak first when it opened the door; a door already in the asked shape is silent. Door sounds
  are centred.
- **Water**: a boat's `ride_to` adds a `splash` at its start; a `pour`'s `WaterFlow` →
  `PlayedAction(pours=True)` → one soft `splash` as long as the water runs, from `pour_flow`'s start
  + `POUR_FALL_SECONDS`; `wet_steps(cues, wet_from)` adds a `splash` under every footstep from the
  first puddles' start (`Stage.puddles`).
- **`knock`** (`scenes/knock_action.py`, non-animating, `run_time` 0.75): targets door props (room
  doors or a `door` prop; validate names the stage's doors); `cue` → `Stage.knock_on(patterns,
  time)`: one `knock` at `KNOCK_GAIN` −3 dB with foley however many doors match; nothing moves.
  Tests: `tests/test_cartoon_sounds.py`.

### 69.63 More music: the `cartoon` and `lullaby` beds (Step 129)

- Made like the §48 beds in `music.py` (`_pads`, `_partials`, `_pluck`, `_bell`, `_circular_add`,
  `_finish`, `BUILTIN_BEDS`, `bed_loop`): numpy only, no samples, seeded `crc32("music:<name>")`,
  circular, `_finish`ed to `MUSIC_LEVEL` −28 LUFS integrated; original melodies. Voices
  `_pizzicato`, `_music_box`, `_woodblock`, `_tick`; `_add_panned`.
- **`cartoon`**: 45 s, 24 bars of 4/4 at 128 BPM, G major; score data `_CARTOON_BARS`,
  `_CARTOON_PERCUSSION`. **`lullaby`**: 45 s, 16 bars of 3/4 at 64 BPM, F major; `_LULLABY_BARS`,
  `_LULLABY_PATTERNS`. `Bed` has no time-signature field.
- **Seam test** (`tests/test_music.py`): for beds with a tempo the change at the seam must lie
  within the range of that change at the loop's other beats (± 0.5 dB); `calm` keeps the 1.5 dB RMS
  rule. Loops start on the downbeat (`start: 0` begins at the top of the tune).

### 69.64 Review of Phase L (Step 130)

- **Example** `examples/cartoon-rainbow-ride` (screenplay `rainbow_ride.md`, hand-edited
  `video.yaml`); `tests/test_phase_l_review.py` runs its cheap checks.
- **Screenplay exits**: `[X exits right.]` writes `{exit: x, to: right}` (`exit`'s edge option is
  `to`; `enter`'s is `side`).
- **Pouring facing**: `pour` flips the can about its grip (`Prop.flip`, `facing`) when its spout
  points behind its holder (held props otherwise keep their drawn facing, §69.27).
- **Held off stage**: a character waiting beyond the edge for its `enter` while holding a prop
  (§69.50) is put a further half its width plus the prop's width outwards, so the prop stays out
  of view.
## 70. Render jobs: `--jobs auto` (Step 117)

- `vidgen/render/jobs.py`: `jobs_for(available_bytes, cores, per_job_bytes)` =
  `min(available // per_job, cores)`, at least 1; 1 when memory is unknown. `choose_jobs()` →
  `JobsChoice(jobs, cores, per_job_bytes, memory)` with `reason` and `to_json()`.
- `available_memory()` → `MemoryReading(available_bytes, source)`, stdlib only, swap never
  counted: Linux the smaller of `/proc/meminfo` `MemAvailable` and `cgroup_headroom` (v1/v2 limit −
  (usage − inactive file cache), smallest over the group and its parents); Windows
  `GlobalMemoryStatusEx.ullAvailPhys`; macOS free + inactive `vm_stat` pages; else unknown.
  `cpu_cores()`: `os.sched_getaffinity(0)` else `os.cpu_count()` (no cgroup CPU quota).
- `PER_JOB_BYTES` 1.5 GB (about 1.8x a 1080p scene render's peak; 4K needs about 2.5 GB, so docs
  say to give `--jobs N` there).
- Every CLI `--jobs` (`render`, `storyboard`, `lint`, `thumbnail`, `slides`, `gallery`) takes `N`
  or `auto` (`_jobs_value`; else usage error; `0` → `--jobs must be at least 1`).
  `_resolve_auto_jobs` (in `main` / `_run_json`) replaces `auto`, prints `jobs: N (auto:
  <reason>)` (stderr with `--json`) and adds `jobs` to the JSON document (also on error). MCP tools
  take int 1–16 or `"auto"` (default 1). Python functions take an int; `vidgen tts` has no `--jobs`.


## 71. A cartoon host beside any scene (Step 133)

`host:` draws a character of `characters:` beside the content of every scene type that lays out
in the safe area. User keys: docs/CONFIG.md "A host beside any scene".

- **Config**: `VideoConfig.host: Identifier | HostConfig | None` (a name = `{character: name}`);
  `HostConfig(character, side=right, size (0, 0.9] | None, place auto|beside|below, floor=true,
  floor_color=dim, facing auto|left|right|front, speaks narrator|own, pose, expression,
  auto_direct)`. `SceneConfig.host`: `false` none, `true`/unset the video's, a name, or
  `HostOverride` (keys written, `model_fields_set`, replace the video's).
- **Checks** (`cartoon/host.py`, no manim): `video_host`, `scene_host`; `host_problems` in
  `parse_config` (unknown character, pose, expression; `host_action_problems`, §71.1);
  `cli.project_problems`: `floor_color` not a theme colour, a scene `host:` on a type with
  `takes_host = False`; `host_warnings`: `speaks: own` without a voice.
- **Scene types**: `NarratedScene.takes_host` (ClassVar, default true); `stage` and `card` false.
  Others lay out in `self.safe_area`.
- **Geometry** (pure `host_layout(area, frame_width, frame_height, host, width_ratio) ->
  HostLayout`; `area` = safe area after overlay reserves): `below` for `place: below` or `auto` in
  portrait. Height = `size` or `HOST_SIZES` (landscape 0.5, square 0.42, portrait 0.36) × the
  shorter side, capped by `BESIDE_MAX_HEIGHT` 0.95 / `BELOW_MAX_HEIGHT` 0.4 of the area height and
  `BESIDE_MAX_WIDTH` 0.4 of its width. Column = figure width × (1 + 2 × `FLOOR_OVERHANG` 0.25)
  with a floor. The **reserve** is the whole column (beside) or full-width bottom band (below), so
  `overlays.avoid` keeps content on the other side. Feet on the area's bottom; `facing: auto` looks
  at the content.
- **Drawing** (`cartoon/host_drawing.py` `build_host(...) -> HostFigure`): measured at
  `REFERENCE_HEIGHT`, rebuilt at the layout height (§69.1 outline), centred in its column; floor
  `Line` in `floor_color`. `HostFigure(VGroup)`: `floor`, `character`, `layout`, `config`,
  `host_name`.
- **In the scene**: `_build_host()` after overlays appends the reserve to `_reserved` (§41), so
  every region and `place()` lays out beside it. `self.host` (`None` without). Added with
  `add_foreground_mobject` (Manim redraws only it over a static image while it idles).
- **Who speaks** (`host_speaks`): its own voice, plus (with `speaks: narrator`) any voice no other
  character owns; `narrate` calls `_host_speak` / `end_lip_sync` per beat (§69.11, §69.34).
- **Between scenes**: on screen from frame 0; `host_continues` (next scene shows an equal
  `HostConfig`) keeps it out of the outro's `clear_all`. The fingerprint gains `next_host` when the
  video or either scene sets a host.
- **Layout dump**: kind `host` (named after the character, box includes the floor) with
  `_character_keys`, `side`, `below`; cartoon rules read kind `character` only. **Lint**
  `host_overlap` (warning, `min_overlap` 0.02 of the smaller box): host box vs scene and overlay
  objects, except particles, motion effects and backdrops holding the whole host box; `covered_text`
  skips the host.
- The host is a scene mobject (moves with `zoom`/`pan`); its idle motion counts for `dead_air`.

### 71.1 Host actions: pointing, reacting, moving (Step 134)

`scenes/host_actions.py` (only `vidgen.api`): `host_point`, `host_look`, `host_react`,
`host_move`, `host_enter`, `host_exit`; they act on `scene.host`, never a target. User keys:
docs/CONFIG.md "Pointing, reacting and moving (host actions)".

- `_HostAction`: `alters_targets = False`; `Action.alters(scene) -> [scene.host]` joins
  `ActionRunner._changed`, so host actions due together play in sequence. Refused on
  `takes_host = False` types, without a host, with more than one of `HOST_MOVES` per beat, or a
  `host_react` expression the character lacks.
- **Point**: `pointed_spot(shoulder, box)`; `hand_goal(..., reach_out=HAND_REACH_OUT 0.1)` keeps
  the hand inside the host's room grown by 0.1 (< `avoid`'s 0.2 gap, so it never touches content);
  look first, then `Character.reached_parts` (§69.26) with the near arm; reverted at the next beat
  or `until:`. `line: true` adds a pointer `Line` (`POINTER_GAP` 0.12, `POINTER_WIDTH` 3), dumped
  as kind `pointer`, skipped by `host_overlap`; never added automatically.
- **`host_react`**: expression and optional effect symbol (§69.40).
- **`host_move`** (`other_side` | `left` | `right`): **the content swaps side with the host**.
  `host_move_plan(...) -> HostMove(side, feet_x, reserve, content_shift)`; the camera frame moves
  by `-content_shift` (`moves_camera = True`), so all scene mobjects shift together without a
  second layout; overlays stay. Below (9:16) only the host walks. The next scene starts on its own
  `side`; `finish()` carries the host over a cut only when `at_home`.
- **`host_enter` / `host_exit`**: walk to/from `offstage_x(side, view, half_reach)`;
  `starts_present` parks the host off screen when the scene's first passage is an enter; its room
  stays reserved.
- Layout dump: `side` is the current side; `pointing_at` while pointing.

### 71.2 Automatic host directing (Step 134)

`cartoon/host_directing.py` (no manim). User keys: docs/CONFIG.md "Automatic host directing".

- `directing_kinds(beat, host, video auto_direct)`: nearest wins. `NarratedScene.auto_actions`
  returns `host_directions(...)` by default (`stage` overrides).
- `NarratedScene.reveal_steps(params) -> list[RevealStep(focus, result)]`, mapped to beats like
  `reveal()`. Built-ins: `bullets` (`item<N>`), `bar_chart` (per bar, `value_trend`), `line_chart`
  (per series), `code` (per highlight; `error` when `has_error_text`); other types none.
  `value_trend` rise/fall above `TREND_SHARE` 0.05 of the largest magnitude.
- `plan_host_directions(beats, present)`, pure: skips beats with a written move (**never adds a
  move**) or with the host off screen; adds one `host_point` at the first new focus, else a
  `host_look` at a written highlight/callout/zoom target or the first focus, and a `host_react`
  (`HOST_REACTIONS` rise happy, fall worried, error surprised; `HOST_EFFECTS` sparkle, sweat,
  exclaim) at `REACT_AT` 0.4 — each unless the author wrote that kind. All are
  `ActionConfig.automatic`. Lint-safe by construction.
- Example: `examples/host-explainer`.

## 72. Voices with feeling, part 1: Kokoro (Step 135)

User keys: docs/CONFIG.md "Voices with feeling (`emotion`)".

- **Config**: `emotion: NAME | {like, speed, pitch, gain, pauses}` on `BeatConfig`, `VoiceConfig`,
  `VoiceEntry` (`EmotionConfig`: speed 0.5-2, pitch -3..3 semitones, gain -12..6 dB, pauses
  0.25-3; `EmotionName` = `emotions.EMOTION_NAMES`). `emotion` is in `voices.SPEAKER_FIELDS` (not
  inherited by named voices). `Project.beat_emotion(beat_id) -> Prosody | None` (beat's, else its
  voice's; `None` if neutral). `has_own_audio` compares emotions.
- `emotions.py` (no manim): `Prosody(name, speed, pitch, gain, pauses)`; `EMOTIONS` 13 rows
  (neutral, happy, excited, sad, angry, worried, scared, surprised, calm, doubtful, sleepy,
  whisper, shout); `EMOTION_WORDS` / `manner_emotion` (screenplay manners → `emotion`).
- `get_provider(voice, emotion=None)`; `beat_providers` keys providers by (voice, emotion).
- **Kokoro**: `spec()` gains `emotion: {...}` only when non-neutral (old hashes unchanged). Speed
  = voice × emotion (clamped 0.25-4) goes into Kokoro. `tts/prosody.py` then scales inner pauses
  (English only, needs word timings; growing inserts `(pauses − 1) × max(pause, natural)` with
  `CLAUSE_PAUSE` 0.2 / `SENTENCE_PAUSE` 0.4 s), shifts token and phoneme times (visemes follow),
  applies gain (tanh soft limit above 0.7), and pitch-shifts length-preserving in the MP3 encode
  (`asetrate,aresample,atempo`). One emotion per beat.
- **Weighted blends**: `kokoro_voices.blend_weights("af_heart+af_bella:0.6")` (unweighted parts
  share the rest; malformed → config error); `voice_for` mixes the packs; hashed as written.

## 73. Voices with feeling, part 2: ElevenLabs and OpenRouter (Step 136)

Every provider speaks `emotion:`; without one, requests and hashes are unchanged. User keys:
docs/CONFIG.md "`emotion` with ElevenLabs and OpenRouter".

- `NAMED_CUES` (`NamedCues(tag, stability, style, instruction)`, every emotion but neutral):
  looked up by **name** (`like`), so these providers ignore a mapping's numbers.
- **ElevenLabs `eleven_v3`** (`voicesounds.is_tagged_voice`): `Project.spoken` inserts `"<tag> "`
  at position 0 (`Spoken.inserted`, term `emotion`); it belongs to no written word (captions,
  karaoke, visemes skip it, §69.33), is in the hash, and `readback.compare_beat` ignores unclaimed
  audio tags. **Other ElevenLabs models**: the row's `stability` / `style` changes go into
  `voice_settings` (clamped 0-1, 3 decimals); text unchanged.
- **OpenRouter** with instructions (`takes_instructions`: `openai/`, `google/`): the row's sentence
  is appended to the voice's `instructions`; `spec()` gains `emotion: {name, instruction}`.
  Others (also `elevenlabs/eleven-v3` there): `with_prosody` post-processes gain, tempo (0.5-2)
  and pitch (no pauses); `spec()` gains `emotion: {name, speed, pitch, gain}`; neutral in those →
  plain hash.
- `tts.speaks_emotion_by_name`; `tts.emotion_warnings` warns about numbers ignored by name-only
  voices and about emotions reduced to speed/pitch/loudness.

## 74. Fast drafts: `vidgen render --draft` (Step 137)

A draft keeps every timing, position, action and lip sync, small and without decoration. User
keys: docs/CONFIG.md "Drafts".

- `draft: DraftConfig` (`width`+`height`, `fps`). `draft_format`: else `DRAFT_SHORT_SIDE` 240 px
  short side at the format's shape (even), `DRAFT_FPS` 8, never above the format. `draft` is out of
  the scene fingerprint.
- `Project.draft` (`load(..., draft=True)`) wins over `preview` in path methods:
  `build/draft[_<variant>][_bare]`, outputs `<output>[_<variant>]_draft*`; draft and preview/final
  never share files.
- `--draft` excludes `--preview` (MCP `render` `draft`); renders with `preview=True`
  (`is_preview` true), worker `--quality draft`, timings and JSON carry `draft: true`.
- `NarratedScene.is_draft` leaves out: idle motion, wind sway (`Wind` kept), shadows, motion
  effects, drawn particles (their timing and sounds kept), puddles/settling snow, fog, lightning
  bolt/flash (thunder kept), the light's grade (`StageLight(flat=True)`), shading and texture
  (§79). Everything else and every sound stays. Beats fall on whole frames, so they may drift a
  frame or two.

## 75. Animatic: `vidgen animatic` (Step 138)

Storyboard stills held in time with the video's audio and captions. User keys: docs/CONFIG.md
"Animatic".

- `animatic.py` `make_animatic`: stills from `build/preview[_<variant>]/frames/<scene>/index.json`;
  scenes whose stills are not current (`storyboard.stills_current(..., per_beat=None)`) are
  rendered with `render_scenes(..., frames=1)`. `animatic.py` is out of the render fingerprint.
- Pure `hold_plan(scenes, frames, fps)` (whole frames): each beat's stills split its time, the last
  holding to the beat's end; scene firsts from the scene start, lasts until the next scene's first;
  overlaps (§49) cut at the next scene start; zero-frame stills dropped. Starts and length from the
  combined timings. No crossfades.
- Audio: `render/pipeline.prepare_join` (shared with `join_scenes`) into `animatic/audio/`.
- Captions: `with_captions(holds, cues, fps)` from `pipeline.video_cues`; burned in with Pillow
  (`CAPTION_SIZE` 0.055, `CAPTION_PLATE_ALPHA` 170), not ffmpeg `subtitles` (needs libass, missing on
  some Windows builds). Default on unless the video has a `captions` overlay.
- `render/ffmpeg.join_stills`: concat demuxer with durations, exactly `round(duration × fps)`
  frames, x264 `-tune stillimage`. Output `Project.animatic_path()` =
  `<output>[_<variant>]_animatic.mp4`.
- CLI `vidgen animatic [PROJECT] [--variant] [--no-audio] [--captions|--no-captions] [--jobs]
  [--output-dir] [--json]`; MCP `animatic` (`captions: null|true|false`).

## 76. Ready-made sets, part 1: outdoors (Step 139)

User keys and set list: docs/CONFIG.md "Ready-made sets".

- Package data `src/vidgen/data/sets/*.yaml` (`sets:` in project format); `includes.builtin_sets()`
  (cached, returns a copy). `expand_sets`: project sets first, then built-ins; `apply_set` merges
  by §69.35; built-in values get no origin. Expanded params carry the set, so editing one
  re-renders its scenes.
- `outdoors.yaml`: `city_street`, `park`, `beach`, `forest`, `snowy_hills`; each with marks
  `stand_left` / `stand_right` (clear of props within 0.15 depth, laid out for 16:9).
- `OUTDOOR_PROPS` in `cartoon/props.py`; `road`, `path` in `FLAT_PROPS` (no shadow, no snow, out of
  `prop_overlap`). `write_props_png` leaves `OUTDOOR_PROPS` and `INDOOR_PROPS` out of its default;
  galleries by `tools/make_sets_gallery.py` into `docs/gallery/media/`. `vidgen screenplay` does
  not look up built-in sets. Tests: `tests/test_builtin_sets.py`.

## 77. Ready-made sets, part 2: indoors (Step 140)

`indoors.yaml`: rooms (§69.42) `classroom`, `kitchen`, `shop`, `living_room`, `bedroom`, read
sorted by file name (rooms list first). Each: one door `door`, one window, `ambience: room_tone`,
stand marks and a mark per seat; wall furniture at depth 0.4, free furniture at least 0.15 in
front. `INDOOR_PROPS`: `blackboard` (`PROP_HANGS`), `school_desk` (`SEAT_BACKS`),
`shelf_with_goods` (fixed `GOODS_COLORS`), `till`, `wardrobe`. User keys: docs/CONFIG.md
"Ready-made rooms".

## 78. Flag badly spoken words (Step 141)

The recogniser's word confidence and timings flag words a 0 word error rate misses. User keys:
docs/CONFIG.md "Readback" and the `unclear_speech` rule.

- `TranscriptWord(text, start, end, probability=None)`; JSON words `[text, start, end(, p)]`
  (old files load); `run_readback` re-transcribes a cached faster-whisper transcript lacking
  probabilities. `CACHE_VERSION` 1. `stt.faster_whisper.load_audio` decodes with the ffmpeg
  executable (`render.ffmpeg.decode_mono`), not PyAV.
- `compare_beat` keeps `transcript` and `heard_spoken` on `BeatReadback`, `heard_indices` /
  `written_index` on each `Edit`.
- `speech_flags.flag_words(result, spoken, settings, pauses_before) -> [WordFlag]` (no manim): per
  heard word or edit, `low_probability` (`< min_probability` unclear, `< doubtful_probability`
  doubtful), `gap` (unexpected pause `> max_gap`: not after punctuation, before an opening
  quote/dash, before a voice sound, or next to skipped words), `mismatch` (unclear for a term or 2+
  errors). Suggestions end with `vidgen tts`.
- `lint.rules.unclear_speech` (`min_probability` 0.5, `doubtful_probability` 0.75, `max_gap` 0.5
  s); also used by `vidgen readback`. `WordFlag.video_time` from `beat_video_starts` (last render;
  `null` before one).
- `vidgen readback` always reports flags (`words to check` section; JSON `flag_thresholds`,
  `summary.unclear/doubtful`, per-beat `flags`).
- Lint rule `unclear_speech` (`lint/readback_rule.py`, last in `LINT_RULES`, doubtful → `info`)
  runs only with `lint_project(readback=True)` / `--readback` or when named in `rules`; it runs
  `run_readback` (cache reused) before rendering. MCP with a paid `stt.provider` needs
  `confirm_cost`.

## 79. Drawing style switch: `drawing:` (Step 142)

User keys: docs/CONFIG.md "Drawing style (`drawing`)". (`cartoon_style:`, §69.10, is only
prompt words.)

- `DrawingConfig {outline: thin|normal|bold, shading: flat|soft, texture: none|paper|storybook,
  seed}` at top level and as the `stage` param; `resolve_drawing(*settings) -> DrawingStyle`
  (later wins; `NarratedScene.drawing_settings()`), resolved into `self.drawing` after host and
  overlays, before the colour fade. Drafts keep only the outline (`DrawingStyle.for_draft`).
- **Applied when drawn** (like §69.31): nothing is recoloured, so digests, layout dump, lint and
  sheets are unchanged; a plain style installs nothing.
  - Outline (`style_camera`): stroke widths × `OUTLINE_FACTORS` (0.6/1/1.7), never thinned below
    1 px; on a `stage` every stroke, elsewhere only `mark_outlined` (the host).
  - Shading `soft`: `mark_shaded` one-colour fills get a vertical gradient (`soft_stops`) after the
    light's grade.
  - Texture (stage only): `attach_texture` multiplies each written frame by
    `texture_shade(texture, seed, w, h)` (cached; seeded `default_rng([seed, kind])`) between the
    overlay layer (§41) and colour fade (§49): over the scene, under overlays and captions, in
    screen space. Not a mobject (would be redrawn each frame and break depth order).
- Character PNGs, sheets and prop galleries draw plain.


## 80. Dubbing: `dub:` and `--all-languages` (Step 143)

Voices for translated variants (§54). User keys: docs/CONFIG.md "Dubbing (`dub`,
`--all-languages`)".

- `dub: {LANG: VOICE | DubVoice}` on `VoiceConfig` / `VoiceEntry` (on voices, because beats name
  voices); `dub_setting` picks the most specific matching key.
- `dubbing.voice_dubs(config)` (no manim): a given dub wins; a named voice without its own
  voice follows the base's (`how: base`); a Kokoro voice of another language without `lang` gets
  `auto`: same kind (`voice_kind`), least used, never `NOVELTY_VOICES`, one target per source.
  ElevenLabs and OpenRouter voices are kept.
- `voices.resolve_voice` merges the dub (`_merge_voice`) and drops `dub` (`DUB_FIELDS`), so hashes
  see only the effective voice; the variant gets `audio/<variant>/` and all timing comes from its
  MP3s. Kokoro gives word timings only for English (dubbed interrupts without `overlap` start
  `INTERRUPT_LEAD` before the line's end).
- Checks: `_dub_problems` in `voice_provider_problems`; `dubbing.dub_warnings` (kind lost, two
  voices merged); validate prints `dub [lang]: ...` lines.
- `cli.each_language`: `--all-languages` on `tts`, `render`, `lint` runs the base then each
  `dubbing.language_variants`, in sequence; worst exit code; `--json` envelope `languages: [...]`;
  not with `--variant`; MCP `all_languages`.

## 81. Composed music, part 1: the `music` extra and the SoundFont (Step 145)

User keys: docs/CONFIG.md "SoundFont (`soundfont`, `vidgen soundfont`)".

- Base dependency `symusic==0.5.9` exactly (0.6.0's render fails); `synth.require_symusic()`
  raises `VidgenError` otherwise; never imported at load time.
- `vidgen/soundfont.py`: default GeneralUser GS 2.0.3 (`URL`, `SIZE_BYTES` 32,319,396, `SHA256`),
  never in the wheel (tested). `cache_dir()`: `VIDGEN_CACHE_DIR`, else the OS cache folder +
  `vidgen`; file `soundfonts/GeneralUser-GS.sf2`. `fetch` streams to a temp file, checks size and
  SHA-256, then `fileio.replace_file`; a mismatch is never used.
- `resolve(setting, root, download=True)`: `soundfont: PATH` must be `.sf2`/`.sf3` with a RIFF
  `sfbk` header (validate problem); else the cached default (hash checked once per process), else
  downloaded. `soundfont` is in `PATH_KEYS` and out of scene fingerprints.
- CLI `vidgen soundfont fetch [--force]`, `vidgen soundfont info [PROJECT]`. Licences and
  `soundfont.CREDIT` in THIRD_PARTY_NOTICES.

## 82. Composed music, part 2: the score and its renderer (Step 146)

- `vidgen/score.py` (frozen, checked, `VidgenError` "score: ..."): `Score(tempo, parts,
  time_signature=(4, 4), key="C major", sections=(), length=None, balance=False)`, `Part(name,
  notes, program=0, drums=False, volume=0.0, pan=0.0, reverb=0.2)`, `Note(start, length, pitch,
  velocity=90)`, `Section(name, start, tempo=None, key=None, time_signature=None)`. A beat is a
  quarter note; a section's key / time signature reach only the MIDI. `fingerprint()` includes
  `FORMAT_VERSION`. `to_symusic` / `write_midi` (480 ticks per beat).
- `synth.render_score(score, soundfont, cache_dir)`: each part rendered alone (symusic ignores CC
  and ends at the last note), then `mix_parts`: with `balance` each part first at `BALANCE_LEVEL`
  −28 LUFS measured where it sounds (`_sounding`), volume, constant-power pan, one shared seeded
  reverb (`reverb_impulse`); length + `TAIL_SECONDS` 3; `MUSIC_LEVEL` −28 LUFS; limited only above
  `TRUE_PEAK_CEILING` −1 dBTP. Silence is an error.
- Cache `score-<render_key>.wav` (16-bit; the returned array is the 16-bit value, so cached =
  fresh); `render_key` = score fingerprint, symusic version, SoundFont SHA-256, `RENDERER_VERSION`
  (2), rate. `score.py`, `synth.py`, `soundfont.py` are in `NOT_RENDER_INPUTS`.

## 83. Composed music, part 3: the composer and its moods (Step 147)

User keys: docs/CONFIG.md "Composed music (`compose`)", "`vidgen music preview`".

- A music cue takes exactly one of `compose:` / `source:` (`MusicCue._one_source`).
  `ComposeConfig {mood, key, tempo, instruments, seed=1, bars}` (`compose: MOOD` short form;
  `config._mood_name_schema` puts the string form in the JSON Schema); `instruments` per part
  (`melody`, `chords`, `pad`, `bass`, `drums`). `composer.settings_problems`: unknown names
  (did-you-mean), kit/role mismatch, key in the wrong mode, bars not a multiple of 4.
- `vidgen/composer.py` (pure): `compose_piece(mood, key, tempo, instruments, seed, bars, ending)
  -> Piece`, `compose(...) -> Score`. Seeded by `crc32("vidgen-compose:<mood>:<seed>")`, one
  generator per part (changing one instrument leaves other parts' notes). `MOODS` (`Mood`: key,
  tempo, meter, A/B/C progressions in Roman numerals, rhythm cells, patterns, default parts,
  fallback bed); a test checks questions end on V and answers on I. `parse_chord`, `form`, melody
  and accompaniment rules live in the module. Scores are `balance=True`, `length` exactly the bars.
- `music.Source`: `source_kind(cue)` → `composed`/`bed`/`file`; looped renders wrap the tail onto
  the start; `loop: false` plays once; `crossfade` does not apply. Without symusic,
  `fallback_bed(cue)` plays `Mood.bed` with a warning.
- 42 instruments + 5 kits; pizzicato, xylophone and bright piano are not offered (render badly in
  GeneralUser GS).
- `vidgen list-music` lists moods and instruments (JSON `moods`, `instruments`, `symusic`);
  `vidgen music preview` (`cli.cmd_music`; `--mood --seed --bars --key --tempo --out`) writes
  `<mood>-seed<S>.wav` and `.mid` without cache. `composer.py` is in `NOT_RENDER_INPUTS`.

## 84. Composed music, part 4: music that follows the video (Step 148)

User keys: docs/CONFIG.md "Music that follows the video".

- A `compose:` cue without `bars` (`musicfit.is_fitted`) is composed in `mix.plan_music` from the
  combined timings; with `bars` it loops (§83). `start`, `loop` do not apply.
- `musicfit.cue_inputs`: a `Slot` per scene (start + half its transition overlap), reveal times
  (`reveal_steps`, `reveal` actions, `sting_reveal`), `Pause`s (`music_pause: true`; a non-first
  `card` until its first beat ends; a last beat of ≤ `PAUSE_WORDS` 8 words unless `music_pause:
  false`, which adds a `button` slot when ≥ `BUTTON_MIN` 0.3 s remain).
- Per-scene `SceneMusic` `mood/key/tempo/instruments/seed` (only under a fitted cue,
  `_scene_compose_problems`): another mood starts from its defaults with the cue's seed.
- `plan_sections` (pure): short slots join neighbours; bar count with tempo within ±`TEMPO_LIMIT`
  8 %, else a *hold* on the last bar; the last section closes (`CLOSE_STRETCH` 1.3, `RIT_STEP`
  6 %); a button bar at the tempo that fills it. `TempoMap` per beat.
- `fit_music(sections, reveals, pauses)`: one `compose_piece(..., ending)` per run of equal settings
  (`cadence` last, `open` others); swells at reveals (`SWELL_BEATS` 2 apart, `SWELL_GAIN` 1.2);
  notes dropped/cut in pause windows (`PAUSE_LEAD` 0.4 s to the next bar line).
- The fitted score hashes like any score, so changed timings re-render. `Placement.fit` adds
  `fit: {sections, swells, pauses, closing}` to the mix summary; fade-out never starts before
  `FittedMusic.closing_seconds`.
- Stings: `sting_score(kind, settings)`; `composed_stings` (from `join_scenes`) replaces built-in
  stings under a composed cue (unless `assets/sfx/sting_*` exists) by a rendered sting, tail
  `STING_TAIL` 1.5 s, matched to the built-in's loudness; `gain`, `at`, ducking stay.
- `musicfit.py` is in `NOT_RENDER_INPUTS`; `music_pause` is out of scene fingerprints.

## 85. Composed music, part 5: tooling, examples and the review of Phase N (Step 149)

- `music.music_warnings` (validate): no usable symusic → names the fallback beds; default
  SoundFont not cached → first render downloads it. A missing SoundFont is fetched (or errors) at
  render; only missing symusic falls back, so a final render never silently loses music.
  `music.music_summary` prints `music:` lines and is `validate --json`'s `music`.
- Drafts and animatics mix through `prepare_join`, so they carry fitted music; `build/music/` is
  shared by preview, draft and final.
- MCP `music_preview` (`vidgen music preview --json`, `out` confined, default `build/mcp/music`).
- Examples: `examples/host-explainer`, `examples/cartoon-rain-check`.

## 86. Platform worlds (Phase O, Steps 150–155)

Side-view platform scenes for kids' stories from a small ASCII map. User keys: docs/CONFIG.md
"Platform levels (`level`)". World and rules are game-reusable; games are out of scope.

### 86.1 Three layers

1. World model (`vidgen/world/`, frozen dataclasses): `Level` (tiles, `Spot`s), `Body`s (feet and
   height in tile units), items (§86.8), `World`.
2. Rules (`vidgen/world/`, pure, deterministic, `VidgenError` when impossible): input + world →
   next world + planned motion. No physics engine.
3. Renderer: `cartoon/level_stage.py`, `cartoon/level_drawing.py` (Pillow), `scenes/stage.py`.

`vidgen.world`, `level_stage`, `level_drawing`, `vidgen.camera`, `cartoon.foley` never import
Manim (tested).

### 86.2 A `stage` with a `level`, not a new scene type

`level:` is a `stage` param, because the stage already has characters, acting, props, shots,
camera, layers, light and sound. Tiles replace the ground; the stage is as wide as the map. A set
applies, minus `includes.LEVEL_DROPPED_KEYS` (props, water, room, `ground_color`; dropped, not
refused, since set props stand at depths a level refuses).

### 86.3 The map (Step 150)

- One line per row, top first: `.`/space air, `#` ground, `=` platform, `~` cloud, `|` ladder;
  item symbols §86.8; a letter (each once) is a spot (`spots: {a: start}` names it). Tabs → 4,
  short rows padded. Max `MAX_COLUMNS` 400 × `MAX_ROWS` 40.
- Model row 0 is the bottom. `STANDABLE` = ground, platform, cloud. Outside the map is air. A spot
  stands on the first standable tile below (`surface_below`); an x on the column's top
  (`top_surface`).
- `parse_level` errors give row and column from the top left, from 1; reported at
  `scenes[i].params.level`.

### 86.4 Geometry on the stage (Step 150)

- `CHARACTER_TILES` 2: tile = `size × shorter side / 2`; default `size` from `character_size`
  (§86.10; medium = `LEVEL_SIZE` 0.25).
- `level_frame`: stage width = map width (`width` refused), map bottom on frame bottom. Spots are
  marks at `(column + 0.5) / columns`. `level_fit_problems`: map narrower than the frame.
- `level_layout` replaces `stage_layout`; `Stage.grounds` are tile tops. Depth, `room`, `water`
  refused.

### 86.5 Drawing (Step 150)

- `level_shapes(level, colors, outline)` (tile units; ground mass with grass and `crc32`-placed
  pebbles, platform slabs, clouds); outline `OUTLINE` 0.04 tile × the drawing style's factor;
  `LevelColors`.
- `draw_columns` supersamples so separately drawn chunks are byte-identical to one drawing.
  `Stage._level_tiles`: `CHUNK_COLUMNS` 8 per `ImageMobject` (one column overlap), at
  `LEVEL_OVERSAMPLE` 1.25 (1 in a draft; capped by `LEVEL_MAX_PIXELS` 24 M). No disk cache.
- `LevelTiles` (`level`, chunks `level_1`...) keeps only chunks in view as members (Manim
  transforms every `ImageMobject` each frame). Background picture parallax
  `LEVEL_PICTURE_FACTOR` 0.2. Tiles are lit (`mark_lit`).

### 86.6 The rest of the phase (plan)

The phase is built: §86.7–§86.11.

### 86.7 Walking and jumping (Step 151)

User keys: docs/CONFIG.md "Walking and jumping on a level".

- `vidgen/world/moves.py`: body box `BODY_WIDTH` 0.4 of its height; `SOLID` = ground, platform.
  `walk_route`: Dijkstra over (column, height), steps up/down `STEP_TILES` 1, ladders at
  `CLIMB_SLOWNESS` 2 → `Route` of `Leg`s (`walk`, `step`, `climb`); refusal names where it stops
  and suggests a jump.
- **Clouds are one-way** (stand on, pass through sideways and from below; a falling arc lands on
  the first cloud top it crosses).
- `plan_jump`: parabolic arcs from walkable take-offs, clearance `JUMP_CLEARANCE` 0.75, sampled
  every 0.05 tiles; limits `MAX_JUMP_ACROSS` 5, `MAX_JUMP_UP` 3, `MAX_JUMP_DOWN` 8; prefer shortest
  jump, then shortest run-up, then lowest arc. `flight_seconds`: `JUMP_GRAVITY` 8 tiles/s²,
  `JUMP_AIR_SPEED` 4, ≥ 0.7 s. `walk_body` / `jump_body` apply to a `World`.
- `level_goal` (spot, mark/x, tile `{column, row}`); validate replays `walk_to`, `run_to`, `jump`,
  `enter`, `exit` (`level_move_problems`) and reports at `beats[j].actions[k].to`; `enter`/`exit`
  are checked at render.
- `cartoon/level_motion.py`: `RouteWalk` (a `Walk` following the route) and `ArcJump` (crouch
  `LEVEL_JUMP_CROUCH_SECONDS` 0.32, landing `LEVEL_JUMP_LAND_SECONDS` 0.55, wobble 7°); run-up +
  jump is one `Succession`.
- `Stage`: `on_level`, `level_pace` (`size / STAGE_SIZE`), `level_walk/enter/exit/jump/moved`.
  `feet_y_at` raises on a level. `rushed_animation`'s `max_speedup` 1.5 applies to level moves.

### 86.8 Story props and reactions (Step 152)

User keys: docs/CONFIG.md "Story props on a level (keys, doors, coins, stars, blockers)".

- `vidgen/world/items.py`: `Item` (kind `key`/`door`/`coin`/`star`/`blocker`, `holder`, `blocks`,
  ...); `World.items`.
- Coins and stars are map symbols `$` / `*` (named `coin_1`, `star_1`... in map order); keys,
  doors and blockers are named stage props/characters at spots, with `locks: {door: key}` and
  `blockers: [name]` on the level (letters stay spots only). Every closed `door` prop blocks.
- `vidgen/world/story_props.py`: a blocking item is an `Obstacle` up to the first solid tile above
  it; a refused move names the obstacle and what clears it. `route_pickups` / `jump_pickups`
  (`PICKUP_RADIUS` 0.3). `open_door` (only the key's holder within `DOOR_REACH` 1.6 / `DOOR_REACH_UP`
  0.5), `close_door`, `step_aside`, `hold_key`.
- Validation replay follows the key, doors and blockers; `StageLevel` checks `locks` and `blockers`
  names and that no prop takes a coin/star name.
- `cartoon/level_items.py` `Collectible`: bobs, pops on `collect()` (`POP_SECONDS` 0.35), not lit.
- `react: {when, expression, effect}` on level moves: `Reaction` at a progress (first pickup,
  `LANDED` 1, `SETTLED` 2) inside the move (a separate action cannot start mid-move); `when`, not
  `on`, because YAML 1.1 reads `on:` as `true`.
- `open` takes `by`; `step_aside` is a moving action; `walk_to`/`run_to` take a tile (`MapTile`).

### 86.9 Sounds on a level (Step 153)

User keys: docs/CONFIG.md "Story props on a level" (Sounds), "Foley and music stings".

- Level sounds are stage foley (§69.19, `foley_cues`), timed from the rules' plan, so `foley:
  false`, `sfx: {gain}` and `assets/sfx/<name>.wav` apply. Take-off `boing`; landing `thud` +
  `footstep`; pickups `coin` / `twinkle` rising a semitone per further one (≤ 5), on the pop's
  frame; key-opened door `unlock` then creak after `UNLOCK_SECONDS` 0.3; `step_aside` a soft
  swoosh. A move's `react` plays no sound.
- New `sfx.py` sounds `unlock`, `coin`, `twinkle` (−27 LUFS, peaks ≤ −9 dBFS).

### 86.10 The camera and `character_size` (Step 154)

User keys: docs/CONFIG.md "Character size (`character_size`)", "The camera on a level
(`follow`)", lint `small_speaker`.

- `character_size: small|medium|large` (video and stage param) = default `size` ×
  `CHARACTER_SIZE_FACTORS` 0.7/1/1.4 (`STAGE_SIZE` 0.45, `LEVEL_SIZE` 0.25). Scene > video >
  medium; `includes.expand_character_size` copies the video's into stage params as data, because
  `params.size` is read without a scene. Both keys in one scene is refused. On plain stages it
  scales characters and props only; on a level tiles, props and items, with `level_pace` keeping
  move durations. Sky, background, layers, captions and overlays are not scaled.
- `vidgen/camera.py` `SmoothFollow` (no manim; dead zone `FOLLOW_DEAD_ZONE` 0.08, spring
  `FOLLOW_SECONDS` 0.45, `FOLLOW_MAX_OFFSET` 0.3, vertical head/feet room). `follow_with_camera`
  takes it (duck-typed `view_center`, `restart`); `Stage.camera_follower` gives it on a level.
- `level.follow: <character>` follows the hero from frame 0 (`pan` stops, `shot` restores,
  `camera_at` refused); no default hero.
- `LevelFrame.top` rises for tall maps (`LEVEL_HEAD_ROOM` 2 tiles); skies, layers and stars
  (`LEVEL_STAR_SKY` 0.45) follow. A short map in portrait is raised by ground rows
  (`level_raise`, `PORTRAIT_SKY_SHARE` 0.4, `PORTRAIT_MAX_RAISE` 0.3); landscape unaffected.
- Lint `small_speaker` (`min_face` 0.075 of the shorter side); `off_frame` skips `scenery: true`
  objects (tile chunks).

### 86.11 The example, the guide and the review of the phase (Step 155)

- Example `examples/platform-story` (three levels, `level.follow`, a 9:16 variant with
  `character_size: large`). `snail` species on the turtle's machinery ("shelled" contrast family).
- `vidgen screenplay` on levels: set lines may name front-matter sets, spots are marks, "X jumps
  to Y" is a `jump`.
- `SHOT_MIN_WIDTHS` (`cartoon/shots.py`: closeup 0.55, medium / over_shoulder 0.7 of the
  character's height) keeps portrait shots wide enough.
- **`vidgen.api` exports the level layers** (`scenes/stage.py` imports them only from there,
  §6.4): `Level`, `World`, `COIN`, `KEY`, `parse_level`, `walk_route`, `plan_jump`,
  `reversed_route`, `route_pickups`, `jump_pickups`, `obstacles_in`, `step_aside`, `open_door`,
  `close_door`, `hold_key`; `LevelFrame`, `LevelProps`, `LevelStep`, `LEVEL_MOVES`,
  `LEVEL_PROP_ACTIONS`, `LEVEL_SIZE`, `LEVEL_UNTRACKED`, `CHARACTER_SIZE_FACTORS`,
  `character_size_default`, `level_frame`, `level_layout`, `level_world`, `level_goal`,
  `level_fit_problems`, `level_move_problems`; `CHUNK_COLUMNS`, `LevelColors`, `draw_columns`,
  `drawn_rows`, `level_shapes`, `COIN_COLOR`, `STAR_COLOR`, `Collectible`; `ArcJump`, `RouteWalk`,
  `Reaction`, `LANDED`, `SETTLED`; `SmoothFollow`; `CharacterSize`. None shadows a manim name.
- Drawing the tile chunks dominates a level's render time.
## 87. Presentation toolkit (Phase P, Steps 156–164)

User reference: docs/CONFIG.md "Actions on a spoken word", "One colour per concept (`terms`)",
`code_morph`, `terminal`, `function_plot`, `number_line`, the chart sections. Every feature is
checked by `vidgen validate` (a `VidgenError` saying what to write), works in 16:9 and 9:16, and
adds public surface only through `vidgen.api`.

### 87.1 The plan

Done: §87.2–§87.11.

### 87.2 Actions on a spoken word (Step 156)

- **Syntax** (`vidgen/word_anchors.py`, no manim): `at: "@WORDS[#N][±S s]"`. `WORDS` match the
  beat's text split at spaces, ignoring case, accents (`textnorm.fold`) and surrounding
  punctuation; `#N` = N-th occurrence (from 1); the offset needs its `s` (so `@K-Phi-3` is a word).
  `parse_word_anchor` refuses `@`, `#0`, a second `@`, and on an action a beat id before `@`.
- **The field**: `ActionConfig.at` is `float (0 ≤ at < 1) | str (^\s*@)`. The written anchor is
  kept in private `_anchor` (`ActionConfig.anchor`) and `at` is set to the resolved fraction
  (`set_fraction`), so every consumer reads a float. `shorthand()` / `model_dump` write the anchor
  back (a dumped config re-validates to the same anchor); `resolved()` keeps the fraction.
- **Resolution, each refining the last**: `BeatConfig` validator (the beat must say the word, else
  `ValueError` with `difflib` suggestions or "there is no #3"; estimate at the default rate) →
  `VideoConfig` (estimate in the video's `language` and `narration.words_per_second`) →
  `Project.__init__` (`retime_project_anchors`: a beat with an MP3 is re-timed from
  `beat_word_times` over the MP3 with the beat's spoken form — the karaoke timings). Renders,
  storyboards, `lint` and `direct` see audio times after `vidgen tts`.
- **A fraction**: `(word start + offset) / narration length`, clamped to `MAX_FRACTION` 0.999,
  multiplied by the beat's body like any `at` (with `overlap` / `interrupt` it lands slightly
  earlier; accepted).
- **Translations**: `pin_translated_anchors` turns an anchor of a beat whose text changed into the
  source fraction (4 places).
- **`lower_third`** `at` also takes `"@Ada"` (first beat of the anchor scene saying it; `#N` over
  the scene) or `"intro_b2@Ada"`; `locate_word_anchor` gives beat and seconds.
- **Refused anchors**: a scene's `sfx:` list, `keyframes` `t`, the thumbnail's `at`, `sting`.
- **`vidgen.api`**: `WordAnchor`, `is_word_anchor`, `parse_word_anchor`, `locate_word_anchor`.

### 87.3 One colour per concept (Step 157)

- **Config**: `VideoConfig.terms: dict[str, ColorRef | TermConfig]` (`color`, `tex: str |
  list[str]`); keys hold a word and differ beyond case and spaces. `SceneConfig.terms: bool =
  True` (`false`: the scene's text and captions keep usual colours). Colours checked against the
  theme (`terms.term_color_problems`).
- **Matching** (`vidgen/terms.py`, no manim): `term_spans` finds whole words in any case with an
  optional `s` / `es`, phrases across whitespace, longest first, no overlaps, no accent folding
  (spans index the drawn text).
- **Applied in the text helpers**: `helpers.styled` and `layout.fit_text_sized` (so `T`,
  `self.text`, `fit_text`, `readable_text`, chart labels, captions) add `t2c` slices for the
  active terms; explicit `t2c` / `highlights` win; `terms=False` opts out. `MarkupText` and `Code`
  are never coloured.
- **Active terms**: a module global (like `current_theme()`) set in `NarratedScene.__init__`
  before anything is built, cleared by `tear_down` and `runtime.set_context` / `clear_context`;
  `using_terms(...)` narrows them.
- **Beyond words**: a `line_chart` series whose whole name is a term and a `callout` without
  `color` take the term colour; `equation` / `equation_derivation` isolate `tex` parts as whole
  tokens (`equation_derivation.isolated_source`, used only when a step contains one); a
  derivation's own `colors` win.
- **Captions**: a term colour is used only where it meets the `contrast` rule's `min_ratio`; the
  plate opacity rises in 0.05 steps up to 1, else the term keeps the text colour with a warning.
- **Lint `concept_colors`** (`lint/term_rule.py`): more than `max_colors` (5) colours, a colour
  under `min_contrast` (4.5) on the background, and per scene (`terms.term_conflicts`) a setting
  colouring a term otherwise (`title.highlight_color`, a series `color`, a derivation `colors`
  entry, a `callout` `color`, plot / number-line item colours).
- **Not coloured**: thumbnails, `MarkupText`, code, chart fills, pictures; a translated variant
  gives its own `terms:`.
- **`vidgen.api`**: `Term`, `active_terms`, `find_term`, `term_spans`, `using_terms`.

### 87.4 Code that morphs between versions (Step 158)

- **Scene type `code_morph`** (`scenes/code_morph.py`, `CodeMorph(CodeListing)`): `versions`
  (≥ 2; a string or `{code | path, highlight}`) plus `code`'s display params. `validate` refuses a
  version equal to the one before.
- **Diff** (`diff_code`, `difflib`, no manim): lines matched without indentation
  (`SequenceMatcher`, no autojunk); within a replaced block lines are paired by a small DP on
  token similarity (≥ `PAIR_RATIO` 0.5), so an edited line stays one line; a line removed and
  re-added unchanged elsewhere is a move. A glyph is addressed as (line, n-th non-space char),
  since `Code` draws one glyph per such char and wrapping only changes spaces. `highlight:
  changed` = new, edited or moved lines.
- **One size for all versions**: `CodeListing._fit_listings` fits several listings at one size
  with `code`'s phone rules; versions share the tallest one's top.
- **The morph** (`_Morph`): kept glyphs `Transform`, removed ones fade by opacity (not `FadeOut`,
  whose remover would dissolve the group), new lines grow from the left. At its end the new
  version is one `Code` with its bands, so the layout dump reads a listing and `is_shown` tells
  which version shows.
- **Timing**: version *i* at beat *i*; targets `version<N>` / `version<N>.line<K>` (entrance =
  the morph, `entrance_time` `MORPH_SECONDS` 1.5 s); a version a `reveal` action shows is left out
  of the scene's steps. Morphs only go forward; a skipped version is diffed directly.
- **Highlights** dim other rows to 0.35 before the morph (`listing_bands`, shared with `code`).

### 87.5 Terminal scene (Step 159)

- **Scene type `terminal`** (`scenes/terminal.py`, subclasses `CodeListing`): `steps` (step *i*
  at beat *i*; `{command, output, clear, output_color}` or a command string). It never runs a
  command. Params: docs/CONFIG.md#terminal (`prompt` `$`, `typing_speed` 18 chars/s, `code` for
  a listing beside it).
- **Rows** (`session_pages`, no manim): prompt + command lines, output lines (Pygments
  `Generic.Output`), the prompt again after a last command; `clear` starts a page. One window
  sized for the tallest page.
- **Fitting** through `_fit_listings` (phone rules of `code`); with `code`, side by side or
  stacked, whichever gives larger text (portrait: stacked), one shared scale.
- **Segments**: each prompt and wrapped row is its own one-line `Paragraph` placed on the page
  listing's glyphs; targets `command<N>`, `output<N>`, `output<N>.line<K>` exist in the scene only
  once shown, so the dump reads exactly the visible text.
- **Timing** (`play_steps`; each step one `_Show`, printing not fading): prompt, typing
  `max(0.3, chars / typing_speed)`, Enter, output rows; shortened in proportion when too long.
- **Actions**: a `reveal` of `command<N>` / `output<N>` leaves that item to the action; earlier
  unshown items on the page appear at once. **`NarratedScene.entrance_time(target)`** (public,
  default `None`) is the seconds a target's entrance wants; `Reveal.run_time_for` uses the
  longest (an explicit `run_time` wins).
- **After code**: `code` / `code.line<K>` are targets, so `carry: ["listing -> code"]` glides a
  listing in (§50).

### 87.6 Maths, part 1: function plots (Step 160)

- **Scene type `function_plot`** (`scenes/function_plot.py`; keys: docs/CONFIG.md#function_plot).
- **Expressions, never `eval`** (`vidgen/mathexpr.py`, no manim, no sympy): a recursive-descent
  parser compiling to numpy closures. Implicit products (`2x`, `x sin(x)`), unary minus below `^`
  (`-x^2` = `-(x^2)`), `^` / `**` right-associative, `pi` / `e` / `tau`, the whitelist
  `MATH_FUNCTIONS`, earlier definitions (`g(x) = f(x) + 1`; no cycles), Unicode `−×·π²`. Anything
  else is a `ValueError` naming it, its column and close names. Non-finite values become `nan`
  (gaps). `vidgen.api`: `MathExpression`, `parse_expression`, `pretty_expression`,
  `split_definition`, `MATH_FUNCTIONS`, `MATH_CONSTANTS`, `MATH_NAMES`.
- **Axes** (`math_axes` → `MathAxes`, §87.8): cross at the origin when in view, else along the
  edges; `aspect: equal` one unit, `auto` fills the body (≤ `MAX_TALL` 1.5 tall:wide). Draw order
  by `z_index` (grid, areas, curves, labels, dots); the dump sorts by it for `covered_text`.
- **Curves** (`curve_runs`) split where undefined, out of range, or at a jump over 1.5 ranges
  (asymptotes); `auto_y_range` trims asymptote tails.
- **Labels**: placed clear of axes, curves and other labels (`place_label`, `dot_label_spot`,
  `area_label_spot`); templates `{x}`, `{y}`, `{slope}`, `{name}`, `{area}`, `{from}`, `{to}`
  checked by `label_problem`.
- **The `trace` action** (`to`; 2 s; reversible with `until`) moves a dot or an area's end; other
  shown parts get a no-op animation so Manim redraws them (else they freeze in the static
  background).
- **Reveal**: an entrance brings its chain (title, axes, function, dot) once; steps: functions,
  dots, areas, one per beat; an item a `reveal` action shows keeps its slot empty.
- **Lint**: `cap_height` counts U+2212 like `-`.

### 87.7 Maths, part 2: the plan for geometry basics (Step 161)

Done: §87.8.

### 87.8 Maths, part 2: geometry basics (Step 161)

- **Shared parts** (`scenes/math_axes.py`): `MathAxes` / `math_axes` (`visible=False` for `axes:
  false`), tick and label helpers, `ChainedTargets` (entrance chains, one item per beat), and the
  generic **`trace`**: a scene type defines `trace_problem(params, name, options)` and
  `traced_item(target)` returning a `Traced` (`state`, `place(state)`, `driver`, `parts`,
  optional `goal(to, scale)`). Options: exactly one of `to: float | [x, y]` or `scale` (not 0).
- **The plane** (`scenes/plane_geometry.py`, on `function_plot`; at least one of `functions`,
  `points`, `vectors`): `PlotPoint`, `PlotVector` (`from`, `to | components | sum`), `PlotMark`
  (`segment`, `brace`, `angle`, `dimension`). `PlaneFigure` (no manim) resolves positions from
  `[x, y]`, names or `point<N>` / `vector<N>` (only earlier vectors: no cycles); derived items
  follow `move`. Names: no spaces or brackets, not `point3` / `vector2`, unique.
- **Defaults**: without ranges the plot spans the figure (`geometry_range`); `aspect` is `equal`
  with vectors or angle marks or without functions. Every position and `trace` goal must be
  inside the plot (validate; ranges do not grow for actions).
- **Steps**: after functions, dots, areas: points, vectors, marks in list order, one per beat; an
  item brings what it names first (`needs`).
- **Mark builders** (`vidgen/geometry_marks.py`, in `vidgen.api`: `GeometryMark`, `brace_mark`,
  `angle_mark`, `dimension_mark`, `segment_normal`, `angle_between`), in frame coordinates: brace
  = `BraceBetweenPoints` (no LaTeX), angle = the smaller one (a square within 0.5° of 90°). With
  `aspect: auto` an arc shows the drawn angle while `{angle}` is in data units.
- **`number_line`** (`scenes/number_line.py`; keys: docs/CONFIG.md#number_line): `points`,
  `intervals` (notation `"[-1, 3)"`, `inf` as text, so the schema allows a string), `jumps` (label
  `'{by}'` preformatted, so `{by:...}` is refused). Targets `title`, `line`, `point<N>`,
  `point:<name>`, `interval<N>`, `jump<N>`; `trace` moves a point.
- **Lint**: `cap_height` counts `= + < > ≤ ≥ × ÷ ~` as x-height glyphs.

### 87.9 Charts that change between beats (Step 162)

- **`bar_chart` and `line_chart` take `changes`** (later states; the first is `values` /
  `series`). Not `pie`, `histogram`, `scatter`, `heatmap`, `stat`. A chart without `changes`
  builds as without the feature. Keys: docs/CONFIG.md (`sort`, `rescale` default `true`). Change
  keys are `TextRef`s (follow a translated series name).
- **Steps**: each change is one step after the reveal steps; `change<N>` is a target
  (`scenes/chart_changes.py`, `ChangingChart`) whose mobject is the whole chart; `is_shown` means
  "state N reached"; `entrance_time` `CHANGE_TIME` 1.2 s. Changes only go forward; a change before
  the chart is on screen sets its shape at once. `reveal_steps` adds one rising / falling step per
  change.
- **Bars**: one value scale over every state (there is no value axis, so rescaling would hide the
  change); labels sized for every state. Labels rebuilt with `become` keep opacity
  (`keep_opacity`, not `match_style`, which hid digits).
- **Lines**: every state precomputed; the y axis rescales when values leave it or span under
  `RESCALE_SHARE` 0.5 of it (`rescale: false`: one axis for all); `chart_axes` `tick_width`
  (default 0) reserves the widest tick label of all axes. The `axes` target stays one group
  (`_SwapAtEnd` is an `Animation`, not an `AnimationGroup`, which Manim would add to the scene).
- **Cursor**: `trace` takes a `line_chart` series (`to` an x inside the data); a dot with a live
  value that follows changes.

### 87.10 Narration–picture check in lint (Step 163)

- **Rules** (`lint/narration_rule.py`, last in `LINT_RULES`): `said_before_shown` (warning: a
  label named more than `min_lead` 1.5 s before it shows and not again in that beat);
  `unsaid_reveal` (default `off`: a later beat brings labels the scene never names).
- **Inputs** (deterministic): layout dump stills, beat times, word times
  (`word_anchors.beat_words`: alignment or estimate) and actions, read into
  `SceneContext.narration` (`NarrationPicture`) only when a rule runs; rules are pure.
- **A label**: a scene text (not overlays, speech bubbles, name tags, maths, code) of at most
  `max_words` (4) words with a content word; same content words = one label. Arrival is bounded
  by the frame before it first shows, narrowed by a word-timed `reveal` / `callout` /
  `transform` of that beat.
- **Matching**: folded words (NFKC), English stems, English and Portuguese stop words; a
  multi-word label is named where all its content words are said within `len + 1` content words.
- **False positives kept low**: nothing within a beat unless an action pins the arrival; words
  already on screen don't count; numbers are not content words.

### 87.11 Example, docs and the review of the phase (Step 164)

- **Example** `examples/gradient-descent` (with a 9:16 `short` variant; no audio committed).
- **`diagram` node on a word**: a node target's entrance (`Diagram._node_entrance`) shows the
  node, then grows edges to nodes on screen (not edges a `steps` entry names); inside the scene's
  own waves a node only appears, so no edge grows twice.
- **Plane labels**: a dot's live label avoids plane labels (`PlaneGeometry.label_boxes`);
  `math_axes` plates every axis number (`LABEL_PLATE_Z` −0.5); jump labels show the decimals their
  ends need (`ends_places`).
- **Lint `min_font`**: sub- / superscript digits count as 0.4 em glyphs (`_SCRIPT`).
- **Readback**: `textnorm._decimals_joined` joins a word starting with the decimal mark to the
  number before (`1` `.5`); a transcript's `-3` is "minus three" (`_MINUS`).
- **Colour advice, no rule**: a term in `accent` looks like scene defaults (tangent, jump arc,
  prompt); the docs name the tokens scenes use.


## 88. Built-in pronunciation lists (Step 165)

User reference: docs/CONFIG.md "Built-in pronunciation lists". Shipped entries every project uses
for words an engine reads wrong (Kokoro's misaki G2P says "epoch" like "epic").

- **Data**: `src/vidgen/data/pronunciation/<engine>-<language>.yaml` (the `pronunciation_file`
  format). A list name layers by dashes: `kokoro-en-us` = `kokoro-en.yaml` then
  `kokoro-en-us.yaml` (`builtin_files`); no files = no entries (`builtin_entries`, cached; a
  broken shipped file is a `VidgenError`). `builtin_list_names()` = `kokoro-en-gb`,
  `kokoro-en-us`. An entry ships only when the default is clearly wrong and the respelling clearly
  better (checked with misaki as Kokoro runs it); each records misaki's phonemes in a comment.
- **Which list** (`builtin_list_name(voice, language)`): from the beat's **effective voice** (§46,
  after a dub §80) — the engine's reading rules, not the video's language. Kokoro: the G2P language
  (`kokoro_voices.resolve`) mapped by `KOKORO_DIALECTS` (`a` → `en-us`, `b` → `en-gb`, …). Other
  providers: `<provider>-<language, default en>`; none ships on purpose.
- **Order** (`build_pronunciation(entries, language, builtin_list)`): project entries
  (`pronunciation_file`s, then `pronunciation:`) over the list's: same term replaces, `null`
  removes; a project entry of another `language` neither applies nor replaces. Project rules get
  the lower `index`, so they win on the same span. `load_pronunciation(config, root,
  builtin_list=None)`.
- **Opt-out**: top-level `pronunciation_defaults: bool = True`; out of the render fingerprint like
  `pronunciation` (audio only).
- **Project** (`vidgen/project.py`): `builtin_list(voice)`, `pronunciation_for(voice)` (cached per
  list), `beat_pronunciation(beat_id)`, `pronounced(beat)`, `builtin_changes()`;
  `Project.pronunciation` is the base voice's. Every reader of a beat's spoken form (TTS, hash,
  lint, captions, SRT via `pipeline.video_cues`, word anchors, overlay fingerprint, readback) uses
  the beat's own.
- **Hash**: the §7 / §45 formula over the spoken text, so only beats a list entry changes go stale.
- **Visible**: `validate` prints a `pronounce: built-in <list> changes N beat(s): …` line (base
  config) and JSON `pronunciation_defaults`; `pronunciation_warnings` never reports a built-in
  entry; `tts --dry-run` / `--json` mark built-in terms (`TTSPlan.builtin`); `vidgen
  list-pronunciation [PROJECT] [--json]` (`builtin_listing`) shows lists with each entry's state
  (`used`, `replaced`, `removed`) and beats.
- **Readback** (`readback.entry_hint`): a misheard built-in word suggests a project entry or
  `term: null`.

## 89. Isometric story worlds (Phase Q, Steps 166–171)

User reference: docs/CONFIG.md "Isometric places (`iso`)". An iso place is an ASCII map with
heights seen from above at an angle, with ready-made objects, indoor rooms (front walls cut away)
or outdoor places. Characters stay the stage's flat cut-outs. No platforming in iso; the side walk
cycle slides along diagonals (accepted).

### 89.1 Layers, as in Phase O

The three layers of §86.1:

1. **World model** (no manim, pure, `VidgenError`): `vidgen/world/iso.py` (`IsoPlace`, `IsoCell`,
   `IsoSpot`, `IsoObject`, `ObjectKind` / `OBJECT_KINDS`, `ObjectPlacing`, `parse_iso_map`,
   `place_objects`), `vidgen/world/iso_moves.py` (routes, §89.9).
2. **The view** (`vidgen/world/iso_view.py`, no manim, no drawing): `iso_point`, `ISO_RISE`,
   `Box3`, `in_front`, `draw_order`; shared with `iso_diagram` (§90.6).
3. **Renderers** (`cartoon/`, Pillow, no manim): `iso_drawing.py`, `iso_objects.py`,
   `iso_scenery.py`, `iso_stage.py`, `iso_pictures.py`, `iso_motion.py`, `iso_weather.py`;
   `scenes/stage.py` and `scenes/stage_iso.py` (`IsoStaging`) show them.

### 89.2 `iso:` on the `stage`, not a new scene type

An iso place is the stage's `iso` param (like `level:`, §86.2), purely additive: every iso branch
tests `params.iso is not None` / `on_iso` first, so stages without `iso` are unchanged.
`Params._check_iso` refuses, naming the alternative: `level`, `room` (`iso: {place: indoor}`),
`water` (`~`), `fog`, `width`, `layers`, big flat `props` (use `iso.objects`), `size` /
`character_size` (use shots), a character's `depth`, a character `at` anything but a spot. A set
gives an iso place sky, light, ambience, particles, birds; `includes.ISO_DROPPED_KEYS`
(`LEVEL_DROPPED_KEYS` + `layers`, `fog`, `width`) are dropped, and the video's `character_size` is
not copied into iso scenes (`expand_character_size`).

### 89.3 The view: projection and draw order (Step 166)

- **Coordinates**: `x` = map column (to the lower right), `y` = row from the top (lower left), `z`
  up, in tiles. The map's top line is the back.
- **Projection**: `u = (x − y) / 2`, `v = (x + y) / 4 − z·ISO_RISE` in tile widths (2:1 diamonds),
  `ISO_RISE = √1.5 / 2`. Parallel: a character has one size everywhere (no `depth` scaling).
- **Draw order**: everything that can hide something is a `Box3`. `in_front(a, b)` is `None` when
  their pictures are apart (`PICTURE_SLACK` 0.35) or side by side (apart along `x` one way, `y` the
  other); else the first separating axis decides (larger `x` / `y`, higher `z` in front).
  `draw_order` is Kahn's topological sort, ties by `x0 + y0`, `z0`, index (deterministic); a cycle
  breaks at the furthest-back box. Boxes, not a per-cell depth key, because objects span cells and
  characters stand inside cells.

### 89.4 The map (Step 166)

- **Symbols** (one line per row, top = back): space or `-` outside (`-` because a YAML block
  scalar cannot start with a space), `.` floor, `:` path, `~` water, `#` wall, `+` door, `%`
  window, `1`–`9` a `BLOCK` that many steps high (`STEP_HEIGHT` 0.5; `0` floor), `@` tree, `&`
  bush, `*` flowers, `=` fence, a letter = a spot. Tabs expand to 4; at most `MAX_COLUMNS` x
  `MAX_ROWS` 48 x 48.
- **Letters and object symbols take the surrounding ground** (`_inherited`: most common standable
  ground and height of the four neighbours; ties to lower, then floor, path, block).
- **`heights`**: an optional digit map; raising water or outside is refused.
- **Spots**: `stand_cell(name)` is the spot's cell, or when an object stands there the nearest
  free standable cell (Chebyshev, then most in front, then leftmost).
- **Objects from symbols** are named `tree_1`, `fence_1`… in map order; fences link to fences and
  walls beside them.
- **Walls**: outdoors `GARDEN_WALL_HEIGHT` 1 (a door is a gap). Indoors a wall cell is cut
  (`is_cut`, to `CUT_WALL_HEIGHT` 0.45) when a non-wall cell lies right behind it (left, up,
  up-left), else stands `WALL_HEIGHT` 3 — one rule for rooms of any shape.
- **Standing** (`is_standable`): floor, path, block, door, a walkable object (rug, bridge).
- **Errors** (`VidgenError` at `scenes[i].params.iso`) name row and column from 1: unknown symbol,
  a letter twice, a `spots` letter missing, one name for two letters, nowhere to stand, bad
  `heights`, raised water, too large, unknown place kind.

### 89.5 Ready-made objects (Step 166)

- `OBJECT_KINDS` (`world/iso.py`) gives each kind's footprint (facing left), height, deck and
  top; `facing: right` swaps it, `size: [columns, rows]` replaces it. `at` is the back (top-left)
  cell: a spot or `{column, row}`.
- `place_objects` checks each footprint: inside, not on a wall, not on water (but a bridge), not
  on another object, one height; names default to the kind (`house`, `house_2`); duplicates are
  refused.
- Colours: `OBJECT_COLORS` theme tokens (hex where none fits); `color` / `detail` override.
- `iso_objects.BED_KINDS` (flowers, bush): a larger `size` draws a clump per cell.

### 89.6 Drawing (Step 166)

- **Shapes** (`iso_drawing.py`): `Poly`, `Blobs`, `Disc`, `Upright` (cylinder), `Line`;
  `draw_shapes` paints them in order on an `IsoCanvas` at `ISO_SUPERSAMPLE` 3, box-filter reduced.
  A polygon's fill also strokes its own edge (no seams between fills).
- **Joined boxes** (`box_shapes`): top and the two front faces (`LEFT_SHADE`, `RIGHT_SHADE`); a
  `joined` side has no face or outline, so terraces and wall runs are one form.
- **Ground** (`ground_shapes`), raised `_block`s, walls (`_wall`: a core plus an arm to each joined
  wall, one piece); room colours follow `room.py`.

### 89.7 The place on a stage (Step 166)

- `StageIso` (`scenes/stage.py`): `place`, `map`, `heights`, `spots`, `objects`
  (`IsoObjectParam`), `colors` (`IsoColors`), `name_tags`. `parsed()` is cached (`_parsed_iso`).
- **World scale**: the whole place fits the frame with `ISO_MARGIN` 5 % (`place_bounds`); the
  camera starts on the wide view (§89.13). A character is `ISO_CHARACTER_HEIGHT` 2 tiles tall
  (× `scale`).
- **Layout** (`iso_layout`): feet in the middle of the stand cell on its top (`iso_stand`), as
  `StagePlacement`s, so the stage's construct, `stage_frame` and `stage_reframes` work unchanged.
- **Marks**: each spot is a stage mark at `map_fraction` (frame-independent); the iso branch of
  `stage_marks` comes first so `iso` + `level` reports the conflict.
- **Pictures** (`IsoScenery`): a `base` with ground and every piece in draw order, plus per body
  something hides a front picture (`iso_front_<name>`, drawn right after it) holding the pieces in
  front of it, transitively (`pieces_in_front`). Base-with-everything plus fronts, not layers cut
  between characters, because split pieces showed seams. No disk cache.
- `vidgen.api`: `ISO_CHARACTER_HEIGHT`, `OBJECT_KINDS`, `IsoPlace`, `ObjectPlacing`,
  `parse_iso_map`, `place_objects`, `Box3`, `draw_order`, `iso_point`, `draw_shapes`,
  `OBJECT_COLORS`, `ObjectLook`, `IsoColors`, `IsoView`, `body_box`, `canvas_center`,
  `iso_layout`, `iso_stand`, `iso_view`, `map_fraction`, `IsoScenery`.

### 89.8 The rest of the phase (plan)

Done: §89.9–§89.13.

### 89.9 Characters moving on the place (Step 167)

- **Routes** (`world/iso_moves.py`): 8 neighbours (4 made zig-zags); a diagonal needs both side
  cells standable and all four level (`can_step`); height changes at most one step. Cheapest path
  over (cell, heading): 1 per side, √2 per diagonal, `TURN_COST` 0.05, `CROWD_COST` 4 per cell
  where someone stands (never refused). Ties by `NEIGHBOURS` order: deterministic. `IsoRoute`
  points stand at `stand_z` (cell top or an object's deck); feet ease over `STEP_EASE` 0.3 at a
  height edge.
- **Goals** (`goal_cell`): a spot or `{column, row}`; a goal where someone stands becomes a free
  cell beside them on the picture (`BESIDE`, never straight in front or behind), else the nearest
  free cell within `BESIDE_REACH` 2 of them. Errors name unknown spots (listing them), cells
  outside or unstandable, and for **no route** the reached cell nearest the goal and what blocks
  it (edge, object, water, wall, a climb, a corner).
- **Moves**: `walk_to` / `run_to` `to:` a spot or cell; `after: <character>` (`gap` 1) follows
  the leader's route of the same batch (`Stage._iso_planned`), and a follower right behind its
  leader steps aside; `meet` (`with:`) picks the side-by-side pair (`SIDE_BY_SIDE`) the longer walk
  reaches soonest, both end facing each other; `wander` (`around`, `radius` 3, `stops` 3, `seed`
  default `crc32(name/beat)`); `enter` / `exit` cross the edge (`edge_ways`: `left` = the map's
  west and south edges, `right` = north and east; `EDGE_STEP` 1 tile with a fade) or use `door:` a
  spot (`DOOR_FADE_SECONDS`); indoors only a door in an edge wall leads out. Held props go with
  the walker on enter / exit (`carried`).
- **One plan for render and validate** (`plan_move`) from the logical cells (`Stage.iso_cells`,
  `None` = off the place); `validate`'s replay (`iso_move_problems`) reports what the render would
  meet, naming beat and option.
- **Timing**: natural time = route / speed, scaled by `level_pace` (character height over
  `STAGE_SIZE`); `at` and word anchors start it; lint `rushed_animation` covers `IsoWalk`. A tile
  counts as a tile of height for footsteps (`IsoWalk._distance`).
- **The walk** (`cartoon/iso_motion.py`, `IsoWalk(Walk)`): facing by the leg's picture direction
  (`leg_facing`); towards the camera the front view if any; away, the last side (no back view).
  `iso_feet` holds the world position.
- **Draw order while moving** (`Stage._iso_keep_order`, every frame once a walk applies): each body
  stands in `standing_box` (kept inside its feet's cell); `IsoScenery.over` gives the pieces over
  it and its front picture is swapped when they change; bodies re-sort by box. Fronts are made on
  first need, kept for the scene, drawn only over their pieces' boxes (`FRONT_MARGIN`) in whole
  canvas pixels so they lie on the base pixel for pixel.
- **Checks** (`moving.py`): on iso, `to` is a spot or cell, no `depth`; `after` needs iso, not
  with `to`, names another character; `meet` / `wander` need iso; `door` is a spot, not with
  `side` / `to`; jumps, `react`, `step_aside` stay a level's.
- **Public**: `IsoScenery`, `standing_box`, `IsoRoute`, `IsoStep`, `ISO_MOVES`, `WANDER_RADIUS`,
  `WANDER_STOPS`, `cell_of`, `find_route`, `plan_move`, `iso_move_problems`, `IsoWalk`.
- **Decided**: walkers do not avoid each other (routes avoid standing characters only; time
  reservation would change every route); a closed door does not block a route (room doors are
  drawn closed; docs say to `open` a house door first).

### 89.10 Staging on the place (Step 168)

- **Tiles at levels of detail** (`cartoon/iso_stage.py`, `iso_pictures.py`): each `Picture` is
  drawn in `TILE_PIXELS` 512 tiles (`TILE_OVERLAP` 2) at level k = 2^k × level 0's pixels, up to
  `MAX_DETAIL` 3 (`MAX_ZOOM` 8); `detail_for(zoom, density)` picks the least sharp-enough level.
  `tile_image` caches (LRU `TILE_CACHE` 320). Each picture is an `IsoTiles` group of the tiles in
  view (plus half a view), swapped by a camera listener (`Stage._iso_show_view`) and again before
  Manim splits moving and static mobjects. `draw_tile` (`install_tile_drawing`) resizes and blends
  only the part in the frame.
- **Camera**: the stage's. `shot:` as anywhere (`wide` = the wide view); `follow` zooms until the
  character is `ISO_FOLLOW_SIZE` 0.45 of the shorter side (`follow_width`) and tracks y too; `pan`
  to a spot or character (§89.13); `zoom` frames a group. Bounds stay the frame.
- **Small things**: `props` from `ISO_ITEMS` (`scenes/stage.py`) or an svg. `drop` = `put_down`
  without `to` (beside the feet, `ISO_PUT_ASIDE` 0.36), `place` = `put_down` `to:` a spot (on the
  object there, `ObjectKind.top`, `iso_item_point`). A thing is a body (`item_box`) with its own
  front; held, it goes with its holder (§69.27). Refused: big props, `depth`, `lift`, `against`,
  a non-spot `at`, a name an object / door / spot has, `throw`, `blow_away`.
- **Reach**: `iso_move_problems` replays `ISO_ITEM_ACTIONS` with the moves; giver and taker must
  be `ISO_REACH` 1 cell apart, naming the walk that fixes it.
- **Changes to the place**: `ObjectState` (`shown`, `open`, `on`; `OPENING_KINDS`,
  `SWITCHED_KINDS`, `default_state`), drawn by `object_shapes(..., state)`; room back-wall doors are
  `door_1`… (`IsoPlace.doors`). Actions `open` / `close`, `switch_on` / `switch_off`, `reveal`,
  `hide`. A changeable object the scene names is **layered**: left out of the base, its own
  `IsoObject` group after the base (with the pieces over it); a change (`Stage.iso_change`) fades
  the new layer in, and other pictures showing it follow (§90.15). Layers, not redrawing the base,
  because the base is large and in the static image. A hidden or `shown: false` object is left
  out of the place moves plan on (`IsoPlace.without`, `ISO_PLACE_CHANGES`).
- **Public**: `IsoTiles`, `install_tile_drawing`, `ObjectState`, `default_state`,
  `OPENING_KINDS`, `SWITCHED_KINDS`, `ISO_FOLLOW_SIZE`, `follow_width`, `iso_item_point`,
  `item_box`, `object_box`, `ISO_ITEM_ACTIONS`, `ISO_PLACE_CHANGES`, `ISO_REACH`.

### 89.11 Mood, sound and who speaks on the place (Step 169)

- **No mood keys**: time of day is the stage's `light`, weather its `particles`. An iso place with
  `rain` and no `light` gets `ISO_RAIN_LIGHT` `("#6B7890", 0.45)` (`_check_iso`); rain started by
  the `particles` action keeps the light.
- **Lights glow**: `Poly` / `Disc` `glow`; `draw_shapes(..., glow=True)` draws a picture of the
  lights (others clear what they cover). `IsoTiles` adds `GlowTile`s whose `light_graded` is
  always false, so the stage light grades the place but not its lights.
- **Rain**: `IsoRainGround` lands drops on the place's picture at their x (`place_outline`);
  beside the place or on a body they fall through (`NO_FLOOR`). Shelter and puddles: §90.2. Indoors
  no rain, snow, leaves or streaks (`iso_particle_problem`).
- **Ambience**: bed `crickets`, chosen automatically only outdoors on iso at `sunset` / `night`
  (birdsong's rules); indoors the room tone. Any stage may name it.
- **Footsteps by surface**: `surface_at` (`SURFACES`), `route_surfaces` → `IsoWalk.surfaces`;
  `foley._walk_steps` plays `SURFACE_STEPS` (`step_grass`, `step_gravel`, `step_wood`,
  `step_stone`, rug a soft `footstep`); without surfaces plain `footstep`s.
- **Other sounds, iso only**: `handling_cues` (pick up, give, put down), `place_change_cues`
  (doors, blooms, reveals). A flat stage's `pick_up` stays silent.
- **Name tags** (automatic; `iso.name_tags: false`): `IsoStaging.speak` adds a `NameTag` (voice
  `label`, else name, in `speaker_color`) at constant screen size over the head, only during the
  line and while the head is under `NAME_TAG_FACE` 0.075 of the view's shorter side (lint
  `small_speaker`'s `min_face`); a `say` with a `bubble` hides it. Tags, not bubbles, because a
  narrated line's bubble covers the place. Name tags are not labels for `said_before_shown`.
- **Lint**: `hidden_speaker` on iso uses each later tile's `covers` mask over the 12 x 12
  `face_grid(features)` and reports from `min_hidden_features` (0.25), naming the pieces;
  `small_speaker` skips tagged lines of at most `max_tagged_words` (12); `offscreen_action`
  (warning): `iso_watch` counts frames with at least `WATCH_IN_VIEW` ½ in view (or filling
  `WATCH_FILLS` ¼), the dump gets `iso_actions` via the scene hook `layout_keys(beat_id)`, and the
  rule reports `seen < min_seen` (0.5).
- **Public**: `GlowTile`, `place_outline`, `IsoRainGround`, `SURFACES`, `surface_at`,
  `route_surfaces`, `SURFACE_STEPS`, `handling_cues`, `place_change_cues`.

### 89.12 The example story and the docs (Step 170)

Example `examples/iso-story`: iso scenes on a project `set` (`sets: {village: {background, iso}}`)
so the map is written once. Guide topic `iso`; CONFIG "Isometric places (`iso`)".

### 89.13 The review of Phase Q (Step 171)

- **The wide view** (`iso_stage.wide_view`, `ISO_WIDE_MAX` 2): the world scale stays the
  whole-place fit; the camera starts magnified until the place fills the frame, at most
  `ISO_WIDE_MAX`, but keeping (with `ISO_MARGIN`) the characters and small things at their spots
  (also later arrivals), and in a frame at least as wide as tall every spot and every
  `iso.objects` item whole; a room keeps all of itself. In a tall frame it also keeps the spots
  the scene's `walk_to`, `run_to` and `enter` go to (`_iso_arrivals`). `shot: wide` is this view
  (`IsoStaging.iso_wide_shot`); `camera_at` (a spot) moves it.
- **`pan` moves in** (`IsoStaging.pan_width`, `ISO_PAN_ZOOM` 2).
- **Lamplight** (`lighting.lamp_lit`, `shading.LampLit`, `mark_lamp_lit`, `ISO_LAMP_REACH` (1,
  2.2)): bodies near a lit lamp are graded towards `LAMP_LIGHT` by distance × the lamp's level,
  scaled by darkness; computed when drawn (cached per scene time), not by an updater (which would
  make every wait render each frame).
- **Schema**: `schema._yaml_on_key` adds a `"true"` property beside every boolean `on` (YAML 1.1
  reads a bare `on` as `true`).
- **Public**: `wide_view`, `ISO_WIDE_MAX`, `ISO_PAN_ZOOM`, `LampLit`, `mark_lamp_lit`.


## 90. Iso polish and iso diagrams (Phase R, Steps 172–176)

User reference: docs/CONFIG.md "Isometric places (`iso`)" and `iso_diagram`. Weather on an iso
place, and the `iso_diagram` presentation scene on the same projection and block drawing.

### 90.1 The phase (plan)

Done: §90.2–§90.15.

### 90.2 Rain on the place: shelter and puddles (Step 172)

- **Top surface** (`cartoon/iso_weather.py`, no manim: `TopSurface`, `top_surface`): the height of
  the highest upward-facing shape over each point (`SURFACE_SAMPLES` 8 per tile), built from the
  very shapes the place is drawn with (`IsoScenery.top_surface()`, cached per object states) —
  so what keeps rain off is exactly what snow lies on, and new objects need nothing.
- **Shelter** (`lift_floors`, `IsoRainGround.lift`): where the top surface is `SHELTER_CLEARANCE`
  0.3 tiles above the ground, the drop lands on it. A flat `RainGround` has no lift.
- **Puddles** (`puddles: true`): `iso_puddles` picks seeded cells (`"puddles:<seed>"`) among
  `puddle_cells` (outdoor grass or path, free, unsheltered, nothing in front), one per
  `CELLS_PER_PUDDLE` 10, 2–12; `IsoPuddles` draws them over the place under bodies, with `ripples`
  inside each puddle while it rains. Left out of the layout dump.

### 90.3 Settling snow on the place (Step 172)

`draw_shapes(..., snow=True)` draws a picture of the snow lying on the shapes (`Poly` / `Disc`
`holds_snow`, default true; `Poly.snow_cap` for uprights; the defaults draw every picture as
without snow). `IsoSnow` lays each tile's snow over its own pixels in place (not separate
overlapping snow tiles, which doubled into white lines), at `BLANKET_OPACITY ×
blanket_cover(settle_amount(...))` (§69.60). Flakes land on the iso rain ground. `color` colours
flakes only. Not in a draft (§74).

### 90.4 Speed lines along the walk (Step 172)

`MotionEffect._way`: a body with `iso_feet` draws its lines along its projected feet movement
(kept for a still frame, `ISO_STILL_MOVE`); otherwise level along its facing.

### 90.5 Public (Step 172)

`TopSurface`, `top_surface`, `lift_floors`, `IsoPuddle`, `iso_puddles`, `ripples`, `IsoPuddles`,
`IsoSnow`; `Poly.holds_snow` / `snow_cap`, `Disc.holds_snow`; a `snow` keyword on `draw_shapes`
and `IsoScenery.tile_image` / `picture`; `IsoRainGround.lift`; `IsoTiles.set_snow_opacity`,
`picture_tiles`. `puddles` and `settle` are accepted on an outdoor iso place.

### 90.6 The `iso_diagram` scene type (Step 173)

User reference: docs/CONFIG.md `iso_diagram`. `scenes/iso_diagram.py`, not a stage mode.

- **Layers**: `iso_blocks.py` (model, no manim: what `validate` runs), `iso_labels.py` (label
  geometry, §90.8), `iso_vector.py` (iso shapes as Manim mobjects), the scene. Shares
  `world/iso_view.py` and `cartoon/iso_drawing.py` unchanged. **Vector, not Pillow pictures**:
  small, sharp under zoom, and actions change blocks one by one.
- **Model** (`layout_iso_diagram`): `ItemSpec`s — a block (`BlockSpec`: `SHAPES` box / slab /
  cylinder / database / tile; footprint; height) or a stack of layers on one footprint. `at` is
  the back cell; all items have `at` or none (`arrange`: `row`, `column`, `grid`, `zigzag`,
  `auto` = row in 16:9, zigzag in 9:16 — only the `x = y` diagonal runs down an iso picture).
  Group plates lift their members. Refused (located by validate): mixed `at`, overlapping items or
  plates, a non-member on a plate, an item in two groups, a connector between layers of one stack.
- **Floor**: follows the union of items, plates and connectors, tidied to whole cells (`_tidy`),
  or their bounding rectangle when the union covers at least `FLOOR_FILL` 0.6; when blocks arrive
  a part at a time the floor arrives under them (`FloorCells.under`).
- **Connectors** (`route`): straight when footprints face each other (`MIN_SHARED` 0.2), round the
  front of obstacles (`DETOUR`), else one turn; twin connectors `TWIN_OFFSET` apart; ends kept
  visible past hidden back sides (`hidden_run`). Flat arrows lie on the floor before the blocks;
  pipes are low boxes in the blocks' draw order. A connector to raised blocks tilts evenly
  between their lifts (`iso_blocks.ramped`; pipes as sheared boxes); draw order stays the ground
  one.
- **Fit**: label size from `size` down by 0.9 to the readable minimum, never below; per size the
  largest scale (tile ≤ `max_tile` 2.4; 9:16 `portrait_tile` 1.35 ×) at which everything fits,
  found by `IsoDiagram._largest` (fitting is not monotonic in scale: start at the largest scale
  the drawing alone fits, scan down by `SCAN_STEP` 0.9, then `BISECT_STEPS` 8); labels beside
  blocks are tried first when only the height overflows (`sideways`). Then a warning and a
  shrink when nothing fits.
- **Colours**: own `color` (layer, else stack), else the first term its label says (§87.3), else
  the next palette colour in block order (so blocks shared by two scenes want their own `color`).
  Outlines `outline_ink` (not ink: it vanished on dark themes); top-label ink `readable_ink`,
  registered `on_fill`.
- **Params**: one ordered `blocks` list (a block with `layers` is a stack); `diagram` shorthands
  (`"a -> b: label"`, `-->` dashed, chains). Without `build: each` everything comes in one step in
  the first beat. Every block, stack, group and connector is a target.
- **9:16 layouts** (`Params.layouts(portrait)`): the preferred layout, the grid as written, and
  slanted (`slant(..., share)`) all or half the way along x and y; the largest fit wins unless the
  preferred one is within `LAYOUT_GAIN` 5 %. `portrait_grid: auto` enables slanting.

### 90.7 Public (Step 173)

`BlockSpec`, `ItemSpec`, `GroupSpec`, `EdgeSpec`, `IsoDiagramLayout`, `layout_iso_diagram`,
`DiagramShapes`, `diagram_shapes`, `outline_ink`, `readable_ink`, `top_point`, `top_room`,
`side_point` (`iso_blocks`), `picture_to_scene`, `shapes_mobject` (`iso_vector`).

### 90.8 Labels, reworked (Step 174)

- **Outlines, not bounding boxes** (`iso_labels.py`, no manim; placement and lint share it):
  blocks are convex outlines (`block_outline`, `convex_hull`), pipes their segments, connectors
  their samples. Candidates slide out of an outline (`slide_out`) in `AROUND` order; covered area
  is exact (`clip_area`). `Obstacles.cost` weighs labels, blocks, near-blocks and connector
  samples (`LINE_COST`; for a raised block's label also its tilted connectors at the planned
  lift). First free candidate wins, else pushed candidates (`FAR_COST` per unit beyond
  `leader_from` 0.35), else the cheapest; beyond `leader_from` a leader line is drawn.
- **Order**: layer labels, group captions (by the plate's front edges), block labels (on the top
  when it fits), stack captions, connector labels.
- **One label per block** (`all_blocks`): a one-layer stack is labelled once; a caption repeating
  a layer's label is not drawn.
- **Stacks**: a side column with leaders, or `label_side: below` (`auto` in 9:16) with a swatch
  list under the stack.
- **Room for actions** (`_planned_lifts`): fit and labels account for planned `raise` / `explode`
  lifts and every `relabel` text (`_Label.extent`).

### 90.9 Actions (Step 174)

`scenes/iso_actions.py` (against `vidgen.api`; animations in `scenes/iso_motion.py`). Each checks
that the scene is an `iso_diagram` (`iso_diagram_actions = True`) and its targets' kinds
(`IsoDiagram.target_kind`). All take `at` (share or word); `mid_still_actions` covers `build`,
`raise`, `lower`, `explode`, `collapse`, `flow`, `relabel`.

- **Lifts** (`_lifts_of`): own raise + layers below + stack gap; `_settle` moves points only
  (`LiftMove`), so concurrent colour animations are untouched; raised blocks cast a shadow.
- **`raise`** (`by` 0.5, ≤ 4) / **`lower`** (to the ground by default, never below); `until`
  undoes. **`explode`** (`gap` 0.6, ≤ 3) / **`collapse`**.
- **`build`** (`style` grow, drop, fade) / **`reveal`**: the scene's own steps leave named items to
  them (`_left_to_actions`); `_arrivals` brings floor, plates, captions, blocks back to front, then
  connectors whose both ends are in. `GrowBlock` is an introducer (§90.15).
- **`flow`** (`count` 3, `style` dots / packets, `back`, `chain`): dots along the connector's world
  path at the z of the segment under them, removed at the end.
- **`focus`** (`padding` 0.12 of the safe area's shorter side, `scale`): `MoveCamera` to the
  targets within the scene's `safe_area` (`iso_focus_view`, ≤ 3×); `focus: diagram` = the whole
  frame. Not temporary; no rotation. Labels not wholly inside the new view fade out and back
  (`iso_veil`).
- **`relabel`** (`text`): `Transform` to the new text, swapped into the label's group at the end
  (`SwapAtEnd`; nothing removed). A target without a label is refused.
- **`dim` / `highlight` keep shading** via the generic hook `Target.recolor(paint) -> {member id:
  (fill, stroke)}`: `dim_to` mixes colours towards the background (not opacity: see-through
  blocks); highlights repaint with shading kept. Targets without `recolor` are unchanged.
- **Target** `diagram`: the whole drawing.

### 90.10 Lint `iso_labels` (Step 174)

The scene adds an `iso_diagram` key to each dump still (`layout_keys`): labels (box, owner, on a
top, leader), block / plate outlines, stacks, connector paths, `zoom`. `lint/iso_rule.py` (last in
`LINT_RULES`, warning) reports a label covering at least `min_cover` (0.1) of its box over a block
it does not name, two labels sharing `min_overlap` (0.05), a label over 2+ samples of another
connector, and a leaderless label further than `max_gap` (0.06) × short side × `zoom` from its
subject.

### 90.11 Public (Step 174)

`PIPE_HEIGHT`, `PlacedBlock`, `arrow_shapes`, `block_outline`, `block_shapes`, `box_faces`,
`box_outline`, `picture_size`, `plate_shapes`, `slant` (`iso_blocks`); `AROUND`, `FAR_COST`,
`LINE_COST`, `Obstacles`, `clip_area`, `convex_hull`, `hull_box`, `hull_gap`, `hull_of_point`,
`polyline_gap`, `ray_exit`, `rect_exit`, `rect_of`, `rect_union`, `slide_out` (`iso_labels`);
`ISO_RISE`. `Target.recolor`; `NarratedScene.target(..., recolor=None)`. Config: the actions
above, params `build`, `entrance`, `portrait_grid`, `label_side: below`, target `diagram`, rule
`iso_labels` (`min_cover`, `min_overlap`, `max_gap`).

### 90.12 The example and the fixes it found (Step 175)

Example `examples/iso-web-page`. Fit by scanning and `focus` in the safe area: §90.6, §90.9.

### 90.13 Review of Phase R (Step 176)

Folded into §90.6 (sideways labels, 9:16 layouts, floor, tilted connectors), §90.9 (focus veil,
padding) and §90.2 (ripples stay inside their puddle, `RIPPLE_OFFSET`).

### 90.14 Follow-ups (Step 177)

- Tilted connectors and pipes, raised labels, lint at `zoom`: §90.6, §90.8, §90.10.
- **9:16 shots on an iso place** (`shots.portrait_shot`, from `Stage.shot_framing` on iso in a
  tall frame): across, the nearest centre where every other character is wholly in
  (`PORTRAIT_EDGE` 0.04) or wholly out; vertically, figures centred when the view is
  `PORTRAIT_ROOM` 1.6 times their height. `wide` and `over_shoulder` unchanged; `zoom` / `pan` not
  reframed. `vidgen.api`: `portrait_shot`.

### 90.15 Nothing shows its final look before it comes in (Step 178)

- **Rule**: Manim adds a non-introducer sub-animation's mobject when a `Succession` starts but
  interpolates it only at its turn, so an animation that builds its mobject from nothing must be
  an introducer. `GrowBlock` is one (also each layer of a `LaggedStart`).
- **Iso place changes**: other pictures showing a changing object follow the change
  (`_IsoFollow`): the new picture under the old, fading in over the first half while the old fades
  out over the second; never two left drawn at the end.
- **Moving list**: pictures made mid-play join Manim's moving list, removed ones leave it
  (`_iso_undraw`).
- **Known limit**: an object's own two-picture change (lamp, door) draws soft edges twice until it
  ends.
## 91. Documentary music beds (Step 179)

Five built-in beds with more drive than §48's `pulse` / `bright`: `discovery` (D minor, 104 BPM,
24 bars), `breakthrough` (C minor → E-flat major, 112 BPM, 24 bars, lift at 25.714 s: `start:
25.7 − T` puts it T s after the cue starts), `enigma` (B minor, 96 BPM, 20 bars), `momentum` (G
minor, 120 BPM, 24 bars, a 3+3+2 sixteenth ostinato), `lab` (F minor, 108 BPM, 20 bars). All 4/4,
a chord every two bars; `Bed.description` gives instruments, ranges and chords. User docs:
docs/CONFIG.md#background-music-music.

- **Made like the other beds** (`music.py`): numpy only, no samples, seeded `crc32("music:<name>")`
  (or `Bed.seed`, §91.1), rendered circularly, `_finish`ed to `MUSIC_LEVEL` −28 LUFS; `Bed`
  entries after `lullaby` (listing order kept); `bed_loop` makes the loop at the join. Private
  helpers include `_kick`, `_synth_bass`, `_hat`, `_clock`, `_piano`, `_fm_pluck`, `_pump`
  (side-chain gain curve), `_riser`, `_echoed`, `_opening_pads` and `_tone_filter` (32 Hz
  high-pass plus a gentle low-pass as one FFT over the whole loop, so the seam is filtered like
  any other point).
- **Invariant**: every bed's float32 loop is locked by
  `tests/test_music.py::test_bed_sounds_as_approved` (loop length and three projections on seeded
  noise, tolerance 0.01); a helper change must keep it. Parametrised bed tests (determinism,
  −28 ± 0.05 LUFS, headroom, little above 5 kHz / below 35 Hz, width, seam) run on every bed.
  `Bed` has no time-signature or lift field (the lift time is in the description).

### 91.1 Energetic beds (Step 181)

`ascent` (A minor, 136 BPM, 32 bars, lift at 28.235 s), `horizon` (D minor → F major, 132 BPM, 32
bars, lift at 29.088 s), `beacon` (E minor, 120 BPM, 24 bars), `neon` (F-sharp minor, 116 BPM, 24
bars), built on `momentum`'s accent (`_ACCENTS`) and figure (`_FIGURE`).

- **Seeds**: `Bed.seed: str | None = None` is the name to seed with when not the bed's own
  (`bed_loop` uses `bed.seed or name`); these four seed with their prototype names (`trance_a`,
  `trance_b`, `pulsar_a`, `night_drive_a`). Changing a seed changes the sound.
- **Grid**: `_grid(tempo)` returns `(beat, bar, chord segment, sixteenth)` with the beat rounded
  down to whole sixteenths (an exact sixteenth grid); `_grid_seconds(tempo, bars)` the loop length.
  `Bed.tempo` stays nominal.
- New helpers: `_saw_chords`, `_sweep_mix` (equal-power cross-fade of a dark and a bright
  render), `_section_curve`, `_gate`, `_analog_bass`, `_square_pluck`, `_gated_snare`,
  `_add_stereo`, `_pulsar_pulse`, `_static`, `_clap` (shared with `momentum`).
- `ascent`'s loop (2^10 × 2647 samples) has a large prime factor, so its whole-loop FFTs are slow
  (~17 s); not changeable without changing the bed. `vidgen list-music` makes every loop (about a
  minute).

## 92. The Listen page (Step 183)

`docs/music/README.md` and its media, linked from the README, let people hear the built-in music
and sounds. User docs: docs/CONFIG.md#listen-page-vidgen-music-page.

- **Generator**: `vidgen music page` (`vidgen/listen.py`, `make_listen_page`), not part of `vidgen
  gallery` (which renders scenes with Manim in a project; the page only synthesises audio). Never
  edited by hand; `tests/test_listen.py` fails when the committed text differs from what the code
  writes (except the composed clips' table, which needs the SoundFont).
- **Content** (`--out`, default `docs/music`): per bed a 15 s clip (`CLIP_SECONDS`) from
  `bed_clip_start` — the loop's top, or 6 s before the moment in `CLIP_MOMENTS` (a loop fraction),
  wrapping — with 0.2 s / 1.5 s raised-cosine fades; six `SOUND_ROWS` clips covering every
  `BUILTIN_SOUNDS` entry (a test keeps the set complete); one clip of the six ambience beds; when
  symusic and the cached default SoundFont are present (`composed_available`; never downloads),
  15 s of `curious` and `playful` (`--no-composed` leaves them out); the score-format section
  (§93.14) and a studio paragraph (`listen.page_text`).
- **Levels**: music +12 dB (`MUSIC_GAIN_DB`: −28 → −16 LUFS), effects +8 dB, ambience +12 dB, each
  lowered if a sample would pass −1.5 dBFS.
- **Files** (deterministic for fixed vidgen, FFmpeg / LAME, Pillow, symusic): `listen.write_mp3`
  — libmp3lame CBR 128 kbps stereo (music, ambience) or 96 kbps mono (effects), `-map_metadata -1`,
  bitexact, no ID3, no Xing header. Spectrograms: palette PNGs (64 inferno steps plus a grey for
  dotted 100 Hz / 1 kHz lines), 32 px/s × 120 px, 40 Hz–8 kHz log, −95 to −10 dB, 4096-point Hann
  FFT of the mono mix. Size budget (tested): page under 6.5 MB, music clips 200–320 KB, PNGs ≤ 80 KB.

## 93. Music agents can write: score files (Phase S, Steps 184–191; follow-up 192)

Agents (and people) make music without editing vidgen's Python: a piece is a YAML **score file**
played by vidgen's own synthesizer, with an instrument library, templates of the beds, a check
that reports in words, and pieces used in videos like beds. A human chooses by listening.

Term: a **score file** (YAML; class `MusicScore`) is not the composer's `vidgen.score.Score`
(§82, a note list played with a SoundFont).

User documentation of the format, instruments, effects and commands:
docs/CONFIG.md#score-files-vidgen-music-render and its sub-sections (templates, check, project
pieces); craft notes: docs/COOKBOOK-MUSIC.md. This section keeps the developer contract.

### 93.1 The phase (plan)

Built: format and `vidgen music render` (§93.3–§93.6), instruments and effects (§93.4, §93.7),
templates (§93.8), the check (§93.9), project pieces (§93.10), example and craft notes (§93.11),
score beds (§93.12, §93.14), review rules (§93.13). Rule: additive; every bed stays
byte-identical (`tests/test_music.py` fingerprints).

### 93.2 Where it lives

`src/vidgen/studio/`: `theory`, `patterns`, `events`, `instruments` (and the families `additive`,
`brass`, `organ`, `strings`, `percussion`, `choir`, `singing`), `effects`, `patches`,
`score_file`, `render`, `templates`, `measure`, `check`; package data `beds/` (templates and score
beds) and `data/` (the check's narration sample).

- **Self-contained** (decision: it could become its own package): imports only `vidgen.music`'s
  building blocks (`_kick`, `_pad_wave`, `_tone_filter`, `_finish`…, `BUILTIN_BEDS` for template
  names), `vidgen.sfx`, `vidgen.loudness`, `vidgen.errors` and what they import (`vidgen.config`,
  `languages`, `textnorm`, `voicesounds`, `word_anchors`) — never manim, scenes, the project or the
  render pipeline. `tests/test_studio.py::test_studio_imports_no_video_code` imports every module
  and is an allow-list. The MP3 writer (`listen.write_mp3`) is called by the commands, not `studio`.
- **Public through `vidgen.api`**: `MusicScore`, `load_music_score(path)`,
  `parse_music_score(data, origin)`, `render_music_score(score)`, `patch_catalog()`,
  `music_template_text(bed)`, `music_template_catalog()`, `check_music_score(score)`,
  `check_music_audio(samples, name)`, `music_check_text(check)`, `MusicCheck`.

### 93.3 The format

Decision: one small, regular vocabulary an agent can write correctly the first time — named
things are mappings, every bar of a pattern is a string of steps, chords are written as musicians
write them, everything has a default. Syntax: docs/CONFIG.md#score-files-vidgen-music-render;
reference demo `tests/data/studio/tidewater.yaml`.

- **Top-level keys**: `version title description key tempo time seed loop bars sections
  progression chord_bars tracks master`; `key`, `tempo`, `tracks` required; `bars` or `sections`;
  `progression` only when a pitched track plays; `master` default `{lowpass: 4500, highpass: 32}`.
  Section names lower case; a section's chords restart at its first bar.
- **Parsers**: chords `theory.parse_chord` (an item may be `{chord, notes, bass}`); steps
  `patterns.parse_steps`. Degrees count from the track's `octave` (voice-led to the nearest
  inversion); `vN` counts the voicing from its lowest note (written `notes`, else what `*` plays),
  past the top an octave up. A drum given a pitch, `octave` or `transpose` is a problem; `play:
  chords` is for pads only.
- **Timing** (determinism contract): the beat is `int(48000 · 60 / tempo)` rounded down to a
  multiple of 4 (as `_grid`), a bar the beat × `n · 4 / d`, step k of a bar at `round(k · bar /
  steps)`; a loop is exactly `bars × bar` samples. Same text and `seed` → same samples.

### 93.4 Instruments (the library, Steps 184–185)

`instruments.INSTRUMENTS` (with the family modules) is the set; `patch_catalog()` / `vidgen music
patches [--json]` describes every instrument, setting (range, default, words) and effect.

- **Decision**: bed-derived instruments wrap `vidgen.music` functions with the beds' defaults
  instead of moving that code, so `music.py` and the beds are untouched; the rest live in `studio`.
- Each instrument has a `level` (its normal hit's amplitude before the piece is set to −28 LUFS),
  so the default balance is the beds'. Notes play `held + ring` seconds.
- **Pads**: `detune` / `fade` defaults are the beds' fixed values (`fade` 1.6 s, `saw_pad` 0.5,
  `glass` 0.8); `swell` 0 is steady. The pad `sub` plays the written `bass` note when given and is
  one wave on both sides; `sub_width` (0–1, default 0) at 1 reproduces the per-side sub exactly
  (only the `skyline` bed uses it, §93.12).

### 93.5 Checks

`score_file.parse_music_score` raises one `VidgenError` listing every problem as `where: what`
(`tracks.bass.steps: unknown symbol 'a' at 6 ...`), with did-you-mean for keys, instruments,
settings, sections and modes; after a bad key / tempo / time the rest is still checked with
stand-ins. Limits: tempo 40–240, `MAX_BARS` 512, `MAX_SECONDS` 600 s.

### 93.6 Rendering

`render.render_music_score(score, warnings=None)`:

- Tracks' events are synthesised one by one; pads from `_pad_wave` tables of 2^18 samples with
  independent phases per channel seeded `crc32("studio:<seed>:<track>:...")`, so a track's sound
  never depends on other tracks (only the final level does). Pan `(1 − pan, 1 + pan)`; summed.
- **Loop**: summed circularly and filtered by `_tone_filter` over the whole loop (the seam is an
  ordinary point). **One-shot**: summed linearly with 8 s for tails, filtered with a second of
  silence after, cut 50 ms after the last sample above −80 dB of its peak (not before its last
  bar), 5 ms / 50 ms fades. Then `_finish`: −28 LUFS, float32, read-only.
- Notes outside 20 Hz–12 kHz are left out and reported per track and section in `warnings`
  (stderr; `--json` as `{scene: null, message}`).
- `vidgen music render SCORE|NAME [--out FILE.wav|FILE.mp3] [--json]` (`action: render`; MP3 via
  `listen.write_mp3`); names: §93.13.

### 93.7 Effects and movement (Step 185)

Keys `spread width lowpass highpass duck gate echo reverb` (and `volume` curves) go on a track and
in its section changes, where `none` / `off` / `false` / `null` switches one off. Fields and
defaults: docs/CONFIG.md#score-files-vidgen-music-render (and `effects.EFFECTS`); demo
`tests/data/studio/skyline_lift.yaml`. Internals:

- **Curves**: a number, `{from, to}` over the section, or `[[bar, value], ...]` points (straight
  between, in octaves for frequencies, held outside); jumps between sections smoothed over 20 ms.
  A constant `volume` scales each note; a moving one the track's sound.
- **Filters**: the beds' second-order zero-phase filters. A moving cutoff (`effects.swept_filter`,
  `_sweep_mix` generalised): copies filtered (one whole-buffer FFT, circular for a loop) at cutoffs
  half an octave apart, the two neighbours cross-faded along the curve; a section without the
  filter is unfiltered (20 ms cross-fade). Copies run on `SWEEP_THREADS` (≤ 4) threads, channel by
  channel, at most `SWEEP_MEMORY` (400 MB) at once, each adding only where its weight is not 0,
  in a fixed order — bit-identical to a serial run.
- **`duck`**: at each trigger hit (note starts; chord starts for `play: chords`; every beat for
  `beat`) in a ducking section, `_pump`'s dip (8 ms attack, exponential release, ≤ two beats) is
  subtracted from 1, clipped at 0, circular for a loop; `follow: true` scales it by the hit's gain
  (`X` 1.5, `x` 1, `o` / `?` 0.5). A muted trigger still pumps. A missing trigger or the track
  itself is a problem.
- **`gate`**: `_gate`'s window (3 ms attack, open `duty` of the step, 18 ms release) per hit;
  `floor + (1 − floor) · window` in gated sections, 1 elsewhere, smoothed over 3 ms. A gate
  pattern may not start with `-`.
- **`echo`**: repeat k is the sound `k · delay` later × `feedback^k`, sides swapped on odd repeats
  when ping-pong. **`reverb`**: each side convolved (FFT) with its own seeded decaying noise
  (−60 dB at `size`, 5 ms onset, unit energy), low-passed at `tone`, high-passed at 120 Hz;
  circular for a loop, tail kept for a one-shot. **`spread`**: odd steps right of `pan`, even
  left. **`width`**: mid / side.
- **Processing order** (decision): a track with a bus effect is rendered on its own buffer — notes
  summed per (echo, reverb) setting so each section gets its own and tails carry into the next —
  then filters, gate, ducking, volume curve and width along the piece, then added to the mix.
  Other tracks are summed straight into the mix. Quick FFT lengths: studio only (§94.19).

### 93.8 Templates of the built-in beds (Step 186)

`vidgen music template [BED [--out FILE.yaml] [--force] [--json]]` lists or writes one (user
docs: docs/CONFIG.md#templates-of-the-built-in-beds-vidgen-music-template). Package data
`studio/beds/<bed>.yaml`; `studio/templates.py` (`template_path` with did-you-mean,
`music_template_text`, `music_template_catalog`).

- **Decision**: a template is a close re-creation of a Python bed, not the bed (still made by
  `music.py`): same key, tempo, bars, the bed's voicings and bass written as `{chord, notes,
  bass}`, its sections, every part a track at the bed's level (`volume` = `20 log10(bed level /
  instrument level)`), its random choices written out as steps, comments per part. Header `#
  <Name>: a score-file template of schu-video-generator's built-in bed ...`. For score beds
  (§93.12, §93.14) the template is the bed.
- **Known differences**: pad phases and noise seeds, some accent levels (×1.5 / ×0.5), a few note
  lengths, the old beds' beat (not whole sixteenths), small voicing / pan details; beds without a
  final filter get `master: {lowpass: 16000, highpass: 10}`. Filter openings are dark and bright
  copies cross-faded with equal-power `volume` curves (closer and cheaper than a sweep).
- **Measurements** (`studio/measure.py`, also used by the check): `tempo` (onset autocorrelation,
  70–180 BPM; 3+3+2 can read as 2/3), `chroma` (60 Hz–2.5 kHz), `key_fits` / `key`
  (Krumhansl-Kessler), `loudness_curve`, `band_balance` (20–150, 150–300, 300–1000, 1000–3000,
  3000–6000, 6000–20000 Hz).
- **Closeness test** (`tests/test_music_templates.py`, `slow`) against
  `tests/data/studio/bed_measures.json`: same length, −28 LUFS, clean seam, tempo within 1 %, chroma
  cosine ≥ 0.97 (per chord ≥ 0.95 mean), key fit within 0.1, 2-bar loudness within 2 dB (0.75 mean),
  bands < 6 kHz within 1.5 dB, above within 5 dB.

### 93.9 Checking a piece (Step 187)

`vidgen music check SCORE|AUDIO|NAME [--narration FILE] [--compare OTHER] [--out DIR] [--json]`
(`cli._music_check`, `jsonout.music_check_document`, `studio/check.py`): verdict, findings with
advice naming score keys, a spectrogram PNG and a demo MP3 under narration. User docs:
docs/CONFIG.md#checking-a-piece-vidgen-music-check.

- **Track by track** (decision: so each problem is put on the tracks causing it, with the dB to
  change): `render.render_music_stems` renders each track alone and hands it to a callback (one
  buffer at a time), then mixes as §94.14. Stem bands use the master filter's power response and
  the final gain. Audio files are scaled to −28 LUFS, measured in 2 s blocks, no sections, generic
  advice.
- **Measures**: per 50 ms frame (4096-sample Hann) power in 20–150 Hz (bass), 300 Hz–3 kHz (voice
  range), 2–20 kHz (brightness), 5–20 kHz (highs), per bar; K-weighted loudness (integrated, 3 s,
  sections, half-sections, bars); true peak; tempo (×1, ×2, ×½, ×⅔, ×3⁄2, ×4⁄3, ×¾ within 2 % = same
  beat); seam step over the 99.9th-percentile step; pitched tracks' share on the key's scale per
  section and best key; per chord ≥ 0.5 s, each pitched track with ≥ 5 % of the pitched sound
  there, its share on the scale or chord tones — worst under 25 % is a `key` fix (decision: per
  track; a clashing line barely moves the mix's figure).
- **Sections by name**: `lift` / `drop` / `chorus` / `climax` / `peak` / `high` against the section
  before (round the loop for the first) — louder or brighter — plus a `note` when an earlier
  section is ≥ 1 dB louder and as bright; `build` / `buildup` / `rise` / `riser` / `climb`: second
  half against first.
- **Limits** (`check.LIMITS`): calibrated so every bed (as audio) and template (as a score)
  passes with no note.
- **Advice**: the fewest tracks (≤ 3) holding a band lowered together by one whole dB (≤ 20),
  written as a score change, plus alternatives (octave up, `tone` / `lowpass`, `decay`, master
  `lowpass`). A resting part is proposed for a lift only if it plays outside a build and is not in
  `TRANSITION_INSTRUMENTS`. Mechanical lines carry studio edits (§94.15).
- **`CHECK_VERSION`** (2): bump when findings change; it is in every kept check's cache name.
- **Narration demo**: `studio/data/narration_sample.mp3` (`check.NARRATION_SAMPLE`; 20 s, Kokoro
  `af_heart`, Apache-2.0 so it can ship; −21.5 LUFS, §48). `--narration FILE` plays as recorded
  (≤ 60 s, 3 s of music after). Music from its start, 1.5 s fade-in, 2 s fade-out, ducked by
  `check.duck_gain_db` — `mix.duck_curve` re-written (studio may not import `mix`) with
  `DuckConfig()`'s numbers, a test keeps them equal — over `check.speech_spans`; then −16 LUFS,
  true peak ≤ −1.5 dBTP (scaled, no limiter).
- **Picture**: a row per piece (two with `--compare`, one time scale, 20 columns/s, ≤ 1600):
  spectrogram 30 Hz–16 kHz log on a fixed −105 … −30 dB scale, section lines, dotted 300 Hz / 3 kHz,
  and a lane of each bar's voice-range level against its limit.

### 93.10 Project pieces: score files in a video (Step 188)

A score file in `assets/music` is a **project piece**, played by `music:` cues like a bed
(`src/vidgen/music_pieces.py`; `vidgen.music` calls it, never the other way round at import).
User docs: docs/CONFIG.md#project-pieces-score-files-in-a-video.

- **Names** (decision): `source` is a score when it ends `.yaml` / `.yml` (a path under the
  project) or has no suffix and is not a bed — then `assets/music/<source>.yaml` (`.yml`),
  sub-folders with `/`, `..` refused; a suffix-less existing file stays a music file.
  `music.source_kind(cue, root)` → `score`.
- **Clash** (decision: a problem, not a silent precedence): a bed's name with a piece of the same
  name is a `music.config_problems` problem (`bed_conflict` reads `BUILTIN_BEDS`); use the path
  form or rename. Unknown names: did-you-mean across beds and pieces.
- **Join**: `music.Source` renders via `music_pieces.piece_audio` (`render_music_score`), cached as
  `build/music/piece-<key>.npy` (float32, atomic) and per process (4). **Key**: SHA-256 of
  `{score: sha256 of the file's bytes, renderer: PIECE_RENDER_VERSION (1; bump when the studio's
  sound changes), vidgen: __version__, rate}`.
- **Loop**: a `loop: true` piece under a looping cue is seamless (`start` wraps); cue `loop: false`
  plays it once from `start`. A `loop: false` piece always plays once (`start` inside it).
- **`section`** (`MusicCue.section`; `music_pieces.cue_score`, `section_start`, `section_problem`):
  a piece or score bed starts at that section, `start` counted from it. Decision: no re-timing of
  a written piece to scenes. Other sources or a missing section: a `music[k].section` problem.
- **Reporting**: `mix.music[].kind` `score` in `timings.json` / `render --json`; `vidgen validate`
  prints `music: my_theme, a project piece (score file, rendered at the join)`.
- **Validation**: `config_problems` parses every played piece (no render) and reports
  `music.source: assets/music/x.yaml: <where>: <what>`; `piece_warnings` covers unplayed pieces.
  `list-music` entries with origin `score` (`piece_entry`, read not rendered): name, path, title,
  description, key, tempo, time, bars, chords, loop, `loop_seconds` / `duration`, sections,
  loudness, `problems`.
- **Lint** (`lint/music_rule.py`, rule `music_check`, last in `LINT_RULES`, scope `scene`, warning;
  project pieces only): findings of `check_music_score` (no demo, no picture) whose topic is in
  `topics` (default `voice range`, `highs`, `bass`, `steadiness`, `peaks`, `loop seam`), on the
  cue's first scene, with two suggestions. Judged on the part played (`played_bars`, `_heard`):
  an uncrossed seam, unreached sections and unplayed loud bars are dropped ("the video plays bars
  1-2 of its 4"). Cached as `build/music/piece-<key>-check<CHECK_VERSION>.json` (`piece_check`).
- **MCP** (`mcp_server.py`): `music_template`, `music_patches`, `music_render` (default out
  `build/mcp/music/<score>.mp3`), `music_check` (default out `build/mcp/music`; returns the
  spectrogram); render and check run one at a time.
- `music_pieces.py` and `studio/` are in `render.fingerprint.NOT_RENDER_INPUTS`. No `vidgen.api`
  names.

### 93.11 The example, the craft notes and the Listen row (Step 189)

- `examples/gps-time-of-flight`: six narrated scenes with `music: time_of_flight` (the bed,
  §93.14); its README keeps the agent's iteration log. Tests: `tests/test_music_pieces.py`.
- `docs/COOKBOOK-MUSIC.md` (decision: separate from the video cookbook): craft notes and genre
  sketches as complete score files (parsed by `tests/test_docs.py`); original material only.
- Listen page row: §93.14.

### 93.12 Two score pieces as built-in beds (Step 190)

`tidewater` (E minor, 108 BPM, 24 bars, lift at 26.664 s) and `skyline` (D minor, 128 BPM, 32
bars = 60 s, lift at 30 s) are beds written as score files, in `BUILTIN_BEDS` after the 14 Python
beds; they work wherever a bed does.

- **Mechanism** (decision: the score file is the bed): `studio/beds/<bed>.yaml` (so `vidgen music
  template tidewater` writes what the bed plays). `Bed.score: bool`; generator
  `music._score_bed(name)` imports `vidgen.studio` when called (studio imports music) and returns
  `render_music_score(load_music_score(...))`; `rng` unused, `Bed.seed` `None`. Cached per process
  by `bed_loop`, not on disk.
- **Data**: the YAML equals `tests/data/studio/tidewater.yaml` / `skyline_lift.yaml` plus comments,
  except `skyline`'s pad `sub_width: 1` (the approved sound; the test demo keeps the centred sub).
  Tests: `test_score_beds_facts` (data and `Bed` facts), `test_score_bed_is_its_template`, the
  bed fingerprints.

### 93.13 Review of Phase S (Step 191)

- **Holds across sections** (`render._track_events`, `_events_and_last`,
  `patterns.parse_steps(lead_hold=True)`, `score_file._check_lead_holds`): steps starting with `-`
  continue the note sounding when the section starts (round a loop's end for the first section),
  with the sound of the section it started in. The track must play in the section just before;
  else a problem ("starts the piece (loop: false)" / "the track rests in 'X' just before").
- **Names in the commands** (`music_pieces.music_source`): `render` and `check` (and `--compare`)
  take a path or a name: a bed (score beds as their files; a Python bed as its loop — `check`
  measures it as audio; `render --json` gives `bed`, `bars` / `seed` null, no sections or tracks)
  or a piece in the current folder's `assets/music`; a name that is both is refused. MCP
  `music_render` / `music_check` pass a name (`MUSIC_NAME`: words joined by `/`, no suffix, no
  `..`) when no such file is under the root.
- Roman-numeral chord names are spelled by key signature.

### 93.14 Time of Flight as a built-in bed (Step 192)

`time_of_flight` (§93.11's agent-made piece; B minor, 108 BPM, 24 bars; build from 8.9 s, lift at
26.7 s, settle at 44.4 s) is a score bed like §93.12, after `skyline`, in
`studio/beds/time_of_flight.yaml`.

- The example plays the bed and has no project copy (decision: a copy would clash by §93.10 and be
  a second source of truth), so the `music_check` lint rule does not run on it.
- **Listen page** (`listen.SCORE_PIECES`, `ScorePiece`): a "Made with the score format" section
  after the beds links the score-file, template, check and project-piece docs and the craft
  notes, one row per author-made piece that became a bed (how it was made, the example); "hear it"
  links the bed's own clip (no second copy). `piece_score` reads `studio/beds`. Score-bed clips
  start 6 s before the lift (`CLIP_MOMENTS` 0.5).

## 94. vidgen studio: a local music workstation (Phase T, Steps 193–201)

`vidgen studio [PROJECT] [--port N] [--no-browser] [--clean]` serves a web app on 127.0.0.1 and
opens it: load a built-in bed's template (§93.8), edit, listen, check, keep versions, export YAML /
MP3 / WAV, or save into a project's `assets/music/`. **The sound is always vidgen's own renderer**
(`vidgen.studio`); the browser only plays rendered audio. User docs (page, controls, keyboard,
themes, disk): docs/CONFIG.md#music-studio-vidgen-studio.

Terms: **the studio** is the app (package `vidgen.studio_app`, so named because `studio` was
taken); `vidgen.studio` (§93) is the score-file package. A **session** is one piece (a folder); a
**version** one state of its score file (never changed once written); a **render** a version's
audio; a **preset** a built-in bed's template.

### 94.1 The phase (plan)

Built: server, API, sessions, page (§94.2–§94.7); song strip and tracks (§94.12); inspector and
typed YAML (§94.13); fast re-render (§94.14); check, versions, exports (§94.15); notes and agents
(§94.16); variations (§94.17); polish and disk rule (§94.18); review rules (§94.19). Rule:
additive — beds, templates, project mixes, the Listen page and other commands are unaffected; the
studio writes only in its session folders, chosen exports, or `assets/music/` when asked.

### 94.2 Process and server

- **Modules** (`src/vidgen/studio_app/`): `__init__.py` (`run_studio`, `clean_studio_folder`),
  `app.py` (`StudioApp`: every API call without HTTP; tests call it directly), `server.py`
  (`StudioServer`, a thin router), `session.py`, `edits.py`, `song.py`, `inspector.py`, `stems.py`,
  `narration.py`, `checks.py`, `exports.py`, `notes.py`, `agent.py`, `variations.py`,
  `cleanup.py`, `static/`. `vidgen.studio` never imports `studio_app` (§93.2).
- **Server** (decision: standard library): `http.server.ThreadingHTTPServer` on `127.0.0.1` only,
  port 0 (OS picks) or `--port N` (in use: a `VidgenError`; Windows `SO_EXCLUSIVEADDRUSE`);
  `webbrowser.open` 0.3 s after binding. Ctrl+C stops it (`app.close()` stops late facts too) and
  removes `open.json`. One thread per request; one lock for renders (one at a time), one for
  session changes.
- **Guards**: `Host` exactly `127.0.0.1:<port>` or `localhost:<port>` (403: no DNS rebinding); POST
  only `Content-Type: application/json` (415; a cross-site form cannot send it without a preflight,
  which is never answered) and, with an `Origin`, from this server (403); bodies ≤
  `MAX_BODY_BYTES` 2 MB (413, nothing read; negative `Content-Length` 400); every 4xx / 5xx closes
  the connection; JSON numbers finite, whole where whole is expected. Files only from allow-lists:
  `static/` (listed at start), three bundled fonts, and session files whose names match patterns
  (`<20 hex>.wav`, `<20 hex>-<section>.wav`, …). Every name that reaches the disk (render, picture,
  export names, session / batch / note ids, letters, keys, score section and track names via
  `vidgen.studio`'s `_NAME`) matches a pattern ending in `\Z` with ASCII `[0-9]`; URL paths are
  never decoded. Headers: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, CSP
  `'self'` only (no inline script or style, no `eval`). A dropped connection is ignored; an
  unexpected error is logged and answered 500. A `VidgenError` is 400 with its message.

### 94.3 Sessions on disk

```
<studio>/open.json                          the running studio: url, session id, pid, started
<studio>/sessions/<id>/session.json         format 1: id, created, preset, title, current, redo, revision, versions
<studio>/sessions/<id>/versions/v0001.yaml  each version's text, exactly as written
<studio>/sessions/<id>/renders/<key>.wav    a render; <key>.json facts; <key>-<section>.wav;
                                            <key>.m<tag>.wav listening mix; ….n.wav under narration
<studio>/sessions/<id>/checks/ exports/ variations/<batch>/ inbox/ notes.json request.json proposals.json
```

- **Where** (`session.studio_dir`): the project's `build/studio/` (`PROJECT`, or the current
  folder with a `video.yaml`, found by `project.find_config_file` without reading it), else
  `studio/` in `soundfont.cache_dir()`. It is a cache; a person keeps a piece by exporting or saving.
- **Sessions**: loading a preset or text starts one (id `YYYYMMDD-HHMMSS-xxxx`, pattern-checked
  before a path is built). Versions `{number, parent, origin, label, created, starred}`; `origin`
  `preset | text | edit | check | agent | variation`; `revision` bumped by every change. Text stored
  with `\n` (`session.normal_text`). Writes atomic (`fileio.write_text_atomic`).
- **`open.json`**: removed on exit only if its pid is still this one. MCP tools read it (§94.16).

### 94.4 Versions, undo / redo and A/B (plan for Steps 195 and 197)

- **The score text is the source of truth** and keeps its comments; controls never rewrite the
  file — they edit one value in place (§94.12), and typed YAML is the same operation reversed.
- **Every committed edit is a new version** (slider release, grid click, typed YAML valid for
  0.8 s); invalid text is a draft, never a version, and the last good render keeps playing.
- **Undo / redo** move `current` (rules §94.15); a new edit after an undo starts a branch; nothing
  is deleted.
- **A/B**: A the first or a picked version, B the current or a picked one; `Player.setSource` keeps
  the position and every render plays at the same audition gain (level-matched).

### 94.5 The JSON API

Answers are `{"ok": true, "result": ...}` or `{"ok": false, "error": "..."}` (400 `VidgenError`;
403 / 404 / 413 / 415 / 416 guards; 500 bug). Routes (`server.py`; behaviour in `StudioApp`):

| Call | What it does |
|---|---|
| `GET /api/info` | version, project, studio folder, default preset (`momentum`), audition gain, open session, `provider {name, key_env, key_set, model, model_env}` |
| `GET /api/presets` | the beds in order with facts, `one_line` (≤ 110 chars), `score_bed` |
| `GET /api/patches` | `patch_catalog()` plus `unit`, `scale`, `integer` (`inspector.studio_catalog`) |
| `GET /api/session[?since=R]` | open session and current score; with `since`: picks up the inbox, `{revision, unchanged}` or the whole state |
| `GET /api/score?version=N` | text, outline, problems, render key |
| `POST /api/load {preset} \| {text}` | new session, version 1 |
| `POST /api/validate {text}` | `ok`, problems `{where, message, line}`, outline |
| `POST /api/render {version? \| variation?, section?, mute?, narration?}` | render facts (`key`, `url`, `mix_gain`, `meters`, `timing`, `facts_pending`, …) |
| `GET /api/facts?key=K` | late facts (waits); `{pending: true}` if superseded |
| `GET /audio/<key>[.m<tag>][.n][-<section>].wav` | render / mix / section with `Range` (206, 416) |
| `POST /api/edit {version?, ops, label?, dry_run?}` | value and song edits as a new version; `{ok: false, problems}` writes nothing |
| `POST /api/text {version?, text}` | typed text as a new version (`unchanged` when equal) |
| `POST /api/undo`, `/api/redo`, `/api/current {version}`, `/api/version {version, label?, starred?}` | versions |
| `GET /api/sessions`, `POST /api/open {session}` | list / reopen sessions |
| `POST /api/check {version?, wait?}`, `GET /media/<key>-check.png`, `POST /api/check/apply {version, key, edit}` | check, spectrogram, apply advice |
| `POST /api/export {version?, format, length?, count?, level?}`, `GET /download/<name>` | exports (attachment) |
| `POST /api/save {version?, name, overwrite?}` | save to `assets/music/<name>.yaml` |
| `POST /api/notes`, `/api/notes/update` | listening notes |
| `POST /api/ask {version?}`, `GET /api/ask` | write / read the hand-off |
| `POST /api/proposal/paste {reply}`, `/api/proposal/send {model, confirm: true}`, `/api/proposal/decide {id, keep}` | proposals |
| `POST /api/variations`, `GET /api/variations[?batch=B]`, `POST /api/variations/keep {batch, letter}` | variations |
| `GET /api/disk`, `POST /api/cleanup` | sizes; clean by the rule |

### 94.6 Renders and playback

- **A render** (`StudioApp.render`): the score mixed from stems (§94.14) to −28 LUFS, written as
  16-bit WAV (`sfx.wav_bytes`, also used by `write_wav`) at the **audition level** +12 dB
  (`listen.MUSIC_GAIN_DB`, `audition_gain_db()`), clipped at full scale, the same for every
  version. Facts in `<key>.json`.
- **Render key** (`render_key`): first 20 hex of SHA-256 of `{score: parsed YAML data, renderer:
  STUDIO_RENDER_VERSION (3), vidgen: __version__}` (comments and layout do not re-render). Bump
  `STUDIO_RENDER_VERSION` when the 16-bit render or its facts change.
- **Sections** are cut bit-exact from the whole render (`_slice_wav`, under the render lock; the
  last section of a one-pass piece keeps the tail). Renders are content-named and never replaced,
  so a streamed file is never overwritten (Windows).
- **Playback** (`player.js`): `<audio>` with range requests (decision: not Web Audio — it streams
  and seeks for free); `setSource` keeps the position.

### 94.7 The page

`studio_app/static/` (package data): `index.html`, `studio.css`, ES modules (`app.js`, `api.js`,
`player.js`, `yaml_view.js`, `yaml_edit.js`, `strip.js`, `timeline.js`, `tracks.js`,
`inspector.js`, `stepgrid.js`, `versions.js`, `check.js`, `exports.js`, `notes.js`,
`variations.js`), `favicon.svg`. Vanilla JS, no build step, no CDN, fonts from vidgen's bundled
fonts at `/fonts/...`: works offline. Colours from the `dark_tech` theme, the light option from
`light_academic`. With no open session the page loads `momentum`. `data-busy`, `data-draft`,
`data-ab`, `data-checking`, `data-variations`, `data-switching` on `<body>` are the browser tests'
hooks (pytest marker `ui`, skipped without Playwright).

### 94.8 Listening notes and agents (plan for Step 198; what was built: §94.16)

See §94.16. Decision: agents reach sessions through the disk (MCP tools reading sessions and
writing `inbox/` files), not the studio's HTTP — no port or token to find, works while the studio
is closed, and the MCP root policy already confines writes.

### 94.9 Variations (plan for Step 199; what was built: §94.17)

See §94.17.

### 94.10 Not done in Step 193

Nothing here remains open; the later sections describe the features (pruning: §94.18).

### 94.11 Step 193: facts

No `vidgen.api` names (the studio is a command, not an extension surface); `studio_app` is in
`render.fingerprint.NOT_RENDER_INPUTS`; package data `studio_app/static/*`.

### 94.12 Step 194: song strip, timeline, track list

- **Value edits** (`edits.py`): `set` (a quoted string keeps its quotes; missing keys and parents
  added after their siblings — before `}` in a flow mapping, a new line at the indentation in a
  block one), `delete` (with the comment lines just above; with its comma in flow), `insert`,
  `rename`, `unset` (§94.13). Nodes found by `yaml.compose` (`SafeLoader`) marks; new strings plain
  only when a name or key, else double-quoted.
- **Song edits** (`song.py`), turned into value edits on the text as it then is: `add_track`
  (default pattern `song.default_steps`, `volume: -6`), `delete_track` (not the last),
  `add_section` (4 bars, `part`, `part_2`…), `remove_section` (not the last; cleans `only` /
  `rest` / per-section changes; a track playing only there goes too), `rename_section`. A `bars:`
  score allows only its bars (1–64 from the page).
- **`StudioApp.edit`**: a valid result is the next version (`origin: edit`, parent the edited
  version) and current; problems write nothing; `dry_run` only checks.
- **Chords** (decision: in Python, `song.roman_numeral`): root degree in the key (`b` / `#`
  outside), lower case when minor, the name's suffix and slash bass kept (`Gm(add9)` →
  `i(add9)`). Outline: `{text, written, chords: [{symbol, numeral, name}]}` per progression
  (`own_progression` per section).
- **Energy curve**: `measure.loudness_curve` per bar of the −28 LUFS render (silence
  `ENERGY_FLOOR` −70), a late fact.
- **Mute / solo** (decision: a listening aid, never the score): sent as `mute`; a listening mix
  `<key>.m<tag>.wav` (`tag` 10 hex of the sorted names) remixes the other stems at the whole mix's
  gain and length (muting never makes the rest louder; a one-shot keeps its tails).

### 94.13 Step 195: the inspector, the step grid, the score file typed

- Controls write the track (`tracks.<t>.<key>`) or one section (`tracks.<t>.sections.<s>.<key>`,
  `PART_KEYS`).
- **`unset`**: removes a key and the mappings it leaves empty, keeping the first `keep` path parts
  (default 2); a kept empty mapping is written `{}`.
- **Sliders** from `/api/patches`: `unit` from the words, `scale` `log` for frequencies spanning
  ≥ 2 octaves, `integer`; one version per drag (on `change`).
- **`change_instrument`** (`inspector.change_instrument`): shared settings kept (clamped into
  range), others dropped, per track and section; a drum loses pitch keys and pitched steps (gets
  `song.default_steps`); `play: chords` becomes a pattern where chords cannot be held. The dry
  run's `notes` say what changes. **`play_mode`** (chords ↔ steps `* - - -`), **`section_plays`**
  (written as `only` or `rest` as the track does; never nowhere; resting drops that section's
  changes).
- **Effects**: shorthands read as fields; editing a field of a shorthand writes the whole mapping.
  In a section, removing the track's effect writes `none`; changing an inherited effect writes a
  changed copy.
- **Step grid** (`stepgrid.js`): same tokens as `studio.patterns`; an edit replaces only the
  cell's characters (spacing and `|` stay). Changing a bar's step count (1–32) resamples it.
- **Typed YAML** (`yaml_edit.js`): validated 0.3 s after the last key; valid and unchanged for
  0.8 s → a version via `/api/text`; text with problems is a draft that disables the editing
  controls.

### 94.14 Step 196: fast re-render, playing on, under narration, meters

- **Stems** (`vidgen.studio.render`, not in `__all__`): `render_track_stem(score, name,
  fast_fft=False)` → `TrackStem` (the track alone, float64, before master filter and level; its
  left-out notes); `mix_track_stems(score, stems, warnings=None, whole=None, threads=1,
  fast_fft=False)` → `(float32 audio, MixFacts(gain, samples))`: summed in the order given, master
  filter, level measured on the mix (`music._level_gain`; `_finish(x, gain)`); with `whole` (a
  listening mix) the whole piece's gain and length. `render_music_stems` is built on them.
- **Exactness** (decision): `render_music_score` stays unchanged (it adds plain tracks' notes
  straight into the piece; stems sum first, so only addition order differs). Contract: the remix
  equals `render_music_score` within **1e-9** with the same warnings, and the **studio's 16-bit
  WAV is byte-identical** (`tests/test_studio_stems.py`). Exports, videos and beds use
  `render_music_score` itself; making it sum stems would move bed and template samples.
- **Loudness**: stems are never normalised; the mix is measured (−28 LUFS); listening mixes reuse
  its gain (`mix_gain`). The master filter's two channels and the loudness's 10 s blocks run on two
  threads (bit-identical); tracks render one at a time (memory).
- **Stem key** (`stems.track_keys`): SHA-256 of the score's top-level data except `title`,
  `description`, `master`, `tracks`; the track's name and spec; for a ducking track the trigger's
  **hit inputs** only (`steps`, `accent`, `play`, `rest`, `only`, sections' `steps` / `accent`);
  `STEM_RENDER_VERSION` (1); vidgen's version. A **volume-only change** of a plain volume
  (`plain_volume`) scales the kept stem (everything after volume is linear).
- **Cache** (`StemCache`): in memory, least recently used out past `STEM_CACHE_BYTES` (768 MB); a
  mix's own stems stay. Decision: not on disk (float64 stems are hundreds of MB a version). A score
  whose stems do not fit is **streamed** (`score_stems`, `StemSet.streamed`, `get`): mix and check
  take one stem at a time.
- **Late facts** (loudness, true peak, energy) are computed after the answer on one worker that
  gives way to renders (waits until none ran for 0.3 s; only the latest render's).
- **Under narration** (`narration.py`): `<name>.n.wav`: `check.NARRATION_SAMPLE` repeated, music
  ducked by `check.duck_gain_db` over `check.speech_spans`, both raised by one gain putting the
  voice's true peak at −1.5 dBTP (level-matched across versions).
- **Meters**: each stem's RMS per 50 ms as heard (× mix gain × audition gain, before the master
  filter; floor −60).
- **Playing on** (`player.js`): a new source loads in a second `<audio>` (`audio-next`), seeked
  0.15 s ahead, started at that moment, cross-faded over 60 ms; the playing one is always id
  `audio`.
- **Section-only render** (decision: not built): it would not sound as in the piece at its edges
  and would compete with the whole's render.

### 94.15 Step 197: the check panel, versions, A/B, exports

- **Advice as edits** (`vidgen.studio.check`): an advice line may be a `Fix` (a `str` carrying
  `edits`: `(label, ops)` with `{op: set, path, value}`); `Finding.edits` lists `{fix, label,
  ops}`. Only mechanical advice: a volume (not past a volume curve), an octave up (one octave
  everywhere, ≤ 8), a track `lowpass` / `highpass` (when none), `master.lowpass: 6000`, a build's
  ramp or sweep, a riser added (`riser`, `riser_2`…, volume 6) or raised. CLI output unchanged.
- **`check_music_score(score, hop=None, tracks=None, mix=None, between=None)`**: reuse rendered
  stems / mix; `between` is called between steps and may raise to stop. Same report either way.
- **Checker** (`checks.py`): one worker; kept as `checks/<render key>.json` + `-check.png` while
  `CHECK_VERSION` and `STUDIO_CHECK_FORMAT` (1) match; starts once no render ran for 0.4 s, uses
  kept stems under the render lock, yields to renders, stops (`superseded`) when another version's
  check is asked; `wait` ≤ 60 s. Apply → next version, `origin: check`, label `check: <label>`.
- **Versions** (`session.py`): `undo` (to the parent, pushed on `redo`), `redo` (only when the top
  of `redo` is a child of current), `set_current` (keeps the trail only when it is its next step),
  `add_version(current=True)` clears `redo`, `update_version` (label 1–120 chars, `starred`),
  `list_sessions`.
- **Exports** (`exports.py`): `render_music_score` itself under the render lock; `length` `once`,
  `loops` (1–`MAX_LOOPS` 64, loop pieces only, tiled exactly) or `seconds` (looped, or cut /
  padded; 2 s fade-out when the music goes on); at most `MAX_SECONDS` 600 s; `level` `video`
  (−28 LUFS) or `listening` (+12 dB, lowered to keep true peak ≤ −1 dBTP); made block by block into
  one float32 array. Names `<title slug>-v<N>[-<length>-<level>].<ext>` in `exports/`; MP3 via
  `listen.write_mp3` to a `.partial-` name then `replace_file` (retried on Windows; partial removed
  on failure); served as attachments. YAML is the version's text.
- **Save to project** (`save_to_project`): no project → `VidgenError`; name
  `^[a-z0-9][a-z0-9_-]{0,63}\Z`, not a Windows device name (`exports.WINDOWS_RESERVED`), not a bed
  (§93.10; suggests `<bed>_mine`); existing `.yaml` / `.yml` only with `overwrite`; `assets/music`
  must resolve inside the project; atomic; answers with `music: <name>`.
- The check is of the score as written (mute / solo / narration are listening aids).

### 94.16 Step 198: listening notes and "Ask an agent"

- **Notes** (`notes.py`, `NoteBook`, `notes.json`): `{id n1.., text (1–500 chars), seconds, bar,
  beat, section, bar_in_section, frac, version, created, status open|resolved, answers}`;
  `locate(outline, seconds)`. Decision: notes belong to the session; `place` puts them in the
  version shown at the same bar of the same section and point in the bar (shorter section → its
  last bar; removed section → the same bar of the piece), `moved` says so.
- **Hand-off** (`agent.py`, `request.json`, id `r<time>-<hex>`): base version and text, open notes
  placed in it, its kept check (`check_summary` or `null`), the parent → base diff (≤ 80 lines),
  the instruction (one focused change per note, keep the rest and comments, a line per note, full
  score, don't worsen the check), the reply format; `prompt_text` makes one Markdown prompt.
- **Proposals** (`make_proposal`, `proposals.json`): validated with `check_text`; a valid, changed
  score becomes a version (`origin: agent`, parent the base, label `agent: <summary>`) **not**
  made current (`add_version(current=False)`); anything else is an `invalid` proposal. Keep makes
  it current and resolves its notes; Discard relabels it `discarded · …` (versions are never
  deleted).
- **MCP tools** (`vidgen mcp`, via `anyio.to_thread`): `studio_sessions` (`agent_sessions` over
  `studio_folders(root)`: the root's `build/studio`, each direct sub-folder's `build/studio` (no
  links out), the cache folder's `studio/`), `studio_read` (`agent_read`), `studio_check` (writes
  only `<root>/build/mcp/studio/<id>-v<N>.yaml` / `-proposal.yaml`), `studio_propose`
  (`agent_propose`: note ids and score checked — problems are the tool's error, nothing written —
  unchanged refused, then `inbox/<time>-<hex>.json` written atomically), `studio_variations`
  (§94.17). Beyond the root policy (§62) they reach only the cache folder's `studio/`, writing only
  `inbox/` there; ids are checked before paths are built; a session folder linking out of its
  studio folder is refused (`agent._contained`).
- **Polling** (`?since=R`, 1.5 s while visible, 4 s offline): `poll` turns inbox files into
  proposals oldest first (unreadable → invalid proposal) and removes each once recorded; `touch`
  bumps `revision`.
- **Paste reply** (`parse_reply`): the ```yaml block, else the largest code block, else the whole
  text if it reads as a score with `tracks`; `n1: …` lines; `summary:`.
- **Provider** (optional, OpenRouter): `ask_openrouter` → `/chat/completions` via
  `httpapi.post_with_retries` (`secret=` scrubbed); `OPENROUTER_API_KEY` read when sending
  (`read_api_key`), never stored, logged or sent to the page (`provider_info` only says whether it
  is set); model from the page or `VIDGEN_STUDIO_MODEL`. `/api/proposal/send` needs `confirm:
  true`. Never called in tests (the tests clear the key and stub the call).
- Public: the MCP tools; `checks.kept_check`; `StudioSession.add_version(current=)`, `revision`,
  `touch`.

### 94.17 Step 199: variations

- **Operators** (`variations.py`): pure `op(piece, v)` on the parsed score (`Piece`) →
  `Variation(kind, name, label, ops)` or `None`; `ops` are value edits; `v` (0–2) a variant. **No
  random numbers.** Kinds: **harmony** `revoice`, `substitute` (a non-first numeral of a text
  progression to a relative sharing two tones: minor `VI↔iv`, `VII↔v`, `III→v`, `i→VI`; major
  `IV↔ii`, `V↔iii`, `vi→IV`, `I→vi`), `invert`, `reseed`; **pattern** on the figure (busiest
  pitched non-pad, non-bass track with ≥ 4 notes a bar) `rotate`, `reaccent`, `swap_degrees`,
  `hat_touch`; **mix** `tone` (darker ×0.72 master low-pass ≤ 6000, pads ×0.7, hat −2 dB; brighter
  ×1.4 / ×1.4 / +1.5 dB), `balance`; **energy** `sparser_intro`, `stronger_lift`, `build_in`,
  `breathe`. **Tempo and key are never changed** (every track re-renders; slow FFT lengths).
- **Choosing four** (`make_variations(text, shuffle, first)`): valid candidates per kind (applied,
  `check_text`, a new render key, no duplicate text), turned by `shuffle`, one per kind in the
  order harmony, pattern, mix, energy (`first` leads: "more like this"), then the kinds' next.
  Every template gets four valid, different variations of ≥ 3 kinds (tested).
- **Batches** (`VariationBatches`, `variations/b0001/`: `a.yaml`…`d.yaml`, `batch.json` with root
  version, base, shuffle, label chain, state `running | done | stopped`, per candidate `{letter,
  kind, name, label, status waiting|rendering|rendered|checking|done|failed, key, render, check,
  kept}`). One worker; a new batch stops the old. Renders all four first (`_render_whole`, stems
  reused, no late facts), then checks through a **second `Checker`** (never supersedes the
  current version's check; both yield to renders). A batch left `running` by a closed studio reads
  `stopped`.
- **Keep** (`keep_variation`): next version (`origin: variation`, parent the batch's root, label
  `variation: <chain>; <label>`), current. **Decision: candidates not kept never become versions**
  (they stay in `variations/`). A candidate plays via `/api/render {variation: "b0001/c"}`.
- MCP `studio_variations(session?, version?, shuffle?)` (`agent_variations`): the four scores;
  nothing rendered or written.
- Public: `StudioApp.render(variation=)`, `make_variations`, `variation_batch`, `keep_variation`.

### 94.18 Step 200: docs and polish

- **Keyboard** (`app.js` `wireKeys`; list in CONFIG): none act in an input, textarea, select or
  contenteditable. Decision: Space plays unless the focused control was reached by keyboard
  (`focusByPointer`; `:focus-visible` cannot tell).
- **Widths** (`studio.css`): ≥ 1320 px three columns; 980–1320 px tracks beside a tabbed pane
  (`#pane-tabs`, `data-pane`); < 980 px one column; the work row ≥ 300 px tall. Text contrast ≥
  4.5:1 in both themes; every control named.
- **Offline** (`api.js` `onConnection`): a failed `fetch` shows a banner; a restarted studio with
  no open session reopens the page's (`reconnect`). The open batch and last hand-off
  (`last_handoff`) return after a reload.
- **Disk rule** (`cleanup.py`; decision: renders are a cache, nothing else is): a session keeps
  the renders (files starting with the render key) of its current, first and starred versions,
  its last `KEEP_VERSIONS` (8), its newest batch's candidates and the last `KEEP_PLAYED` (6)
  renders asked for, capped at `CAP_BYTES` (1 GB; current, first, starred and just-played never
  dropped); exports older than `EXPORT_AGE` (a day) go. Runs after a render at most once a minute
  (`_auto_clean`, render lock), at start, on **Clean up** (`POST /api/cleanup`: exports older than
  `ASKED_EXPORT_AGE`, an hour) and with `vidgen studio --clean [PROJECT]` (`clean_studio_folder`);
  start-up and `--clean` skip the session a running studio has open (`_running_session`). Never
  removed: versions, notes, hand-offs, proposals, candidates' texts, checks, `session.json`. Files
  in use (Windows) are left for next time.
- Public: `vidgen studio --clean`; `vidgen.studio_app.clean_studio_folder`;
  `StudioApp.last_handoff`, `disk`, `clean_up`, `variation_batches`.

### 94.19 Step 201: the review of Phase T

Security rules are in §94.2, §94.15 and §94.16 (tests: `tests/test_phase_t_review.py`). Also:

- **YAML**: `check_text` uses the safe loader and refuses documents whose anchors / aliases
  expand past `MAX_YAML_NODES` (200 000; `expanded_nodes`) or that nest too deeply; steps written
  as a list of lists are a steps problem. No shell anywhere; writes atomic (`fileio`).
- **Quick FFT lengths** (decision: **studio only**; a different FFT length cannot be
  byte-identical and shipped scores use slow lengths, so videos, beds, exports and CLI checks
  render exactly): `effects.CircularFFT(n, fast)` zero-pads to `fast_fft_length(2n)` (3n for a
  loop's reverb) and folds the result back around `n` — the same circular convolution within 1e-9
  of the loudest sample. Used when `slow_fft_length(n)` (a prime factor above `SLOW_FFT_PRIME`
  500) and `n ≥ FAST_FFT_MIN` (65536), in `swept_filter`, `reverb` and the master filter (`fast` /
  `fast_fft`, default off; the studio passes `stems.FAST_FFT` True). The studio's 16-bit WAV stays
  byte-identical to `render_music_score`'s.
- **Memory** (bit-identical): `_render_bus` releases summed buffers (`_Canvas.release`) and
  applies gains in place; stems stream (§94.14); exports are block by block (§94.15). Heavy
  10-minute pieces still need more than 3 GB.
- Public (`vidgen.studio.effects`): `CircularFFT`, `slow_fft_length`, `fast_fft_length`,
  `SLOW_FFT_PRIME`, `FAST_FFT_MIN`, `SWEEP_MEMORY`. `studio_app`: `stems.FAST_FFT`,
  `StemSet.streamed` / `get`, `app.MAX_YAML_NODES`, `expanded_nodes`, `KEEP_PLAYED`,
  `session.normal_text`, `exports.WINDOWS_RESERVED`.
## 95. Cell biology in physical scale (Phase U, Steps 202–211)

2D cell-biology presentations at university and research level, stylised but never wrong, checked by
`vidgen validate` and `vidgen lint`, in 16:9 and 9:16. Five scene types: `cell`, `molecule`,
`pathway`, `cell_cycle`, `metabolism`. User side (keys, the rules a user meets, examples):
docs/CONFIG.md (`#cell`, `#molecule`, `#pathway`, `#cell_cycle`, `#metabolism`) and
docs/COOKBOOK-CELL-BIOLOGY.md.

### 95.1 The phase (plan)

Built; §95.2–95.16 describe it. Every type follows one pattern: a manim-free model with **rules** in
`vidgen.cellworld` (a pure function from the world and an action's options to the moves it plans, or a
`VidgenError` naming the beat), a renderer, and a scene against `vidgen.api`. State over beats is
replayed by `vidgen validate` in beat and `at` order. Impossibilities are validation errors;
judgements are lint (§95.14).

### 95.2 A new scene type `cell` (decided)

`cell` is its own type, not a mode of `stage` (characters, ground line, tiles do not apply; the camera
spans five orders of magnitude) nor of `iso_diagram`. Shared catalog, geometry and rules live in
`vidgen.cellworld`, so `pathway` uses the same names without being a `cell`.

### 95.3 The world model (`vidgen/cellworld/`, no manim)

Three layers as in §86.1 / §89.1: model and rules (`vidgen.cellworld`; a test checks it imports without
`manim`), renderer (`vidgen/cell_vector.py`, re-exporting `cell_draw/`), scene (`scenes/cell.py`,
`scenes/cell_actions.py`).

- **Units.** Everything inside is µm (floats). YAML writes a number (µm) or a length string
  (`parse_length`: `"25 nm"`, `"1.5 um"`, `"20 µm"`, `"0.1 mm"`; ≤ 0 refused; `parse_coordinate`
  allows signs). `format_length` writes `25 nm`, `1.5 µm`; `nice_length` gives 1-2-5 lengths.
- **Catalog** (`catalog.py`, data only): `COMPARTMENTS` (label, note, **topology**: `cytosolic`,
  `lumenal` — topologically outside —, `extracellular`, `mitochondrial`, `peroxisomal`, `plastid`),
  `MEMBRANES` (outside and inside compartment, lipid mix, `exo` side), kinds (`Kind`: label, plural,
  `structure` or `complex`, shape, default size, textbook `size_range`, own membranes outside-in with
  the compartments they enclose, `places`, `surfaces`, the reason the rules quote `why`, `cells` /
  `cells_why`, hue), the typical animal, plant and bacterial cells, and the textbook constants
  (Alberts, Lodish: bilayer, gaps, lumens, Golgi period, pore densities, walls, filaments, coats),
  each defined and commented in `catalog.py`.
- **Geometry** (`geometry.py`): a world is a **cross-section**. Shapes in µm (`Ellipse`, `Capsule`,
  `ArcBand`, `RoundedBox`, `Polyline`) with `contains(p, pad)`, `outline`, `inset`, `bounds`,
  `surface` / `faces` (points with outward normals). **Membranes are bilayer mid-lines**: an
  envelope's membranes are `gap + bilayer` apart; a bound complex sits `bilayer / 2 +` its radius off.
- **The world** (`model.py`; built by `build.py`): `build_cell_world(CellSpec) -> CellWorld`.
  `CellSpec`: kind, size, aspect, `contents`, `ObjectSpec`s (with a `where` for messages), seed.
  Entries: the typical contents (unless `contents: none`), each replaced by an object of the same id,
  then the objects; ids default to the kind (`kind_2` for a second); reserved ids `cell`, `title`,
  `tissue`, `scale_bar`, `cytosol`, `extracellular`, `world`. An entry places `Placed` things (`key`:
  id or `<id>#<n>`) with `footprint`, `parts` (membranes and the compartment inside each), `host` (a
  compartment *instance*: `cytosol` or `<key>.<compartment>`), `surface`, `normal`, `facing` (a Golgi
  stack's cis side); generated entries have an `owner` (`nucleus.pores`, `rough_er.ribosomes`).
  Queries: `compartment_at(p)`, `region_at(p)` (nucleolus, centrosome). Neighbouring cells are
  `Neighbour`s.
- **Placement** (`builder.py`): kinds in dependency order (nucleus, Golgi, centrosome, nucleolus, rough
  ER, smooth ER, the rest; written `at` first within a kind); the typical layout's place (Golgi on a
  curve round the nucleus, cis face towards it; rough-ER sheets joined to the outer nuclear membrane;
  smooth ER joining a rough sheet), else scattered with `random.Random("<seed>:<id>")` (600 tries;
  structures 0.25 µm off the plasma membrane, 0.2 µm off each other). Complexes: `on:` the host's
  cytosolic faces, `in:` named instances, `at` one point. **Deterministic** per spec.

### 95.4 The location rules

`build_cell_world` raises `VidgenError` naming the object (`objects[3] (ribosome 'ribosome')`, or
`contents: typical`), what is wrong and the fix; the params validator reports it as a
`scenes[i].params` problem. Rules: unknown names (did-you-mean), `places` / `surfaces` / `cells`
violations quoting `why`, an `at` in a forbidden compartment, overlapping structures or one reaching
the plasma membrane, a nucleolus outside its nucleus, a rough ER without a nucleus, conflicting options
(`at` + `count`, `in` + `on`, `in` on a structure, another kind's option), reserved or duplicate ids, no
room for a count. The full list a user meets: docs/CONFIG.md#cell. Sizes, counts and exaggerations are
lint (§95.14).

### 95.5 The camera in µm, levels, level of detail, scale bar (`view.py`, no manim)

- **Scale.** The body (safe area under the title) shows `CellView(center, span, level)`; `span` is µm
  across the body's **shorter side**, so a view means the same in 16:9 and 9:16. `unit` = body's
  shorter side / the start view's span.
- **Levels** (`level_view`, shares in `FILL`): `tissue` (3.2 cell lengths), `cell` (the cell's box with
  7 % margin, `fit_span`), `organelle` (structure at 62 % of the short side; a sheet or tubule network:
  2.6 µm), `complex` (complex at 20 %; on a structure: a bound pore, else ribosome, else its outer
  membrane, 160 nm). A cytosolic vesicle within `FUSION_REACH` = 0.6 µm of the plasma membrane is
  framed with that membrane. `focus_point`; `width` overrides; `default_level` (organelle for
  structures, complex for complexes).
- **LOD** (`lod_weights`): each feature drawn by its on-screen size in pixels of a frame whose
  **shorter side is 1080 px** whatever the resolution (a preview shows what the final shows), faded on
  a log scale between two sizes per feature (table in `view.py`; ribosome dots keep a 0.8 px rim).
- **Scale bar** (`scale_bar`): the largest 1-2-5 length up to `SCALE_BAR_SHARE` = 22 % of the span.
- **Zoom path** (`zoom_path`): van Wijk and Nuij's smooth zoom-and-pan, ρ = 1.4 (`ZOOM_RHO`): an even
  pace on a log scale (Manim's linear `MoveCamera` rushes a deep zoom's end), out and in between far
  places.

### 95.6 Drawing (`cell_vector.py`) and the scene (`scenes/cell.py`, `scenes/cell_actions.py`)

- **Outlines** are cubic Bézier paths (arcs in pieces ≤ 22.5°: within 0.1 nm for a 20 µm membrane);
  shapes of one look are one `VMobject` with subpaths. `CellDrawing` builds `tissue`, `cell` and one
  `VGroup` per structure or free-complex entry. Pieces register a LOD feature expression
  (`"particles&!particle_detail"`); a membrane is a line at low zoom and a true-width band with a
  midplane at high zoom. Fills are the kind's hue mixed into the background; outlines darker (light
  themes) or lighter (dark).
- **Strokes in pixels**: `update` resets stroke widths from pixels on every camera move
  (`stroke_unit`), since Manim's moving camera scales strokes.
- **Camera listener** (`Cell.on_camera`, via `add_camera_listener` and called by `CellZoom` on every
  interpolation, so nothing is left stale): LOD, strokes, pinned overlays (title plate, labels, scale
  bar) at fixed screen size in front (`OVERLAY_Z`). Every scale-bar text (each 1-2-5 length from 4 nm
  to twice the largest planned span) is made at the start and only shown or hidden: Manim draws an
  animation's family as it was at its start, so a text swapped in mid-zoom would not be drawn.
- **Start-view labels**: columns left and right (16:9), else rows above and below (9:16), else beside
  each thing; anchored on the outline point furthest towards the label's side, spread, with leaders.
  Only things with `labels` weight > 0.5 are named; labels fade as the camera zooms 1.2–1.6× away.
  9:16 rows untangle crossing leaders. Zoomed-view labels: §95.8.
- **Targets**: `title`, `cell`, `tissue`, `scale_bar`, each entry id (`target_names` builds the world,
  `lru_cache` per spec). `reveal: all` (everything in beat one; the tissue unseen until zoomed out) or
  `per_beat` (`ChainedTargets`). `layout_keys` adds `cell`: span, pixels per µm, scale-bar text, LOD
  weights.
- **`zoom_to`**: one target, `level`, `width`, `until`, `labels`; `moves_camera`,
  `alters_targets = False`, 2 s; `scene_problems` refuses other scene types, several or wildcard
  targets, `title` / `scale_bar`, a view the level cannot give; the storyboard draws its half-way still
  (`mid_still_actions`). `CellZoom` animates along `zoom_path`.

### 95.7 Public (Step 202)

`vidgen.api`: `CELL_COMPARTMENTS`, `CELL_KINDS`, `CELL_LEVELS`, `CELL_OBJECT_KINDS`, `CellColors`,
`CellDrawing`, `CellObjectSpec` (`cellworld.ObjectSpec`), `CellSpec`, `CellView`, `CellWorld`,
`build_cell_world`, `cell_default_level`, `cell_label_weight`, `cell_level_view`, `cell_lod_weights`,
`cell_scale_bar`, `cell_zoom_path`, `did_you_mean`, `format_length`, `parse_coordinate`,
`parse_length`. The geometry's `Ellipse` is not exported (it would shadow Manim's).
`vidgen.cellworld` imports without manim for tools and lint.

### 95.8 The structure library (Step 203)

- **Modules** (`cellworld`, no manim): `model`, `catalog`, `geometry`, `curves` (Bézier pieces,
  adaptive arc steps), `regions` (`Region`: boolean ops via skia-pathops, a manim dependency, with a
  sequential fallback and a nudge when Skia refuses; **paths in nanometres** — in µm Skia lost small
  overlapping pieces), `morphology` (cristae, envelopes with pores, ER networks, Golgi, grana,
  intraluminal vesicles, centrioles, filaments), `builder` (placing), `filaments` (microtubules,
  cortex, stress fibres, flagella, pili; motors facing their end), `build` (`build_cell_world`, static
  checks), `bilayer` (lipid layouts, rafts, surface mosaic), `anatomy` (`part_anchors`), `view`.
  Drawing: `cell_draw/` (`base`, `drawing`, `organelles`, `plant`, `bacteria`, `cytoskeleton`,
  `closeup`, `molecules`, `traffic`, `expression`, `expression_route`).
- **Morphology**: the outer nuclear membrane and the rough ER are one membrane (the region union draws
  no seam); stroma lamellae leave granal thylakoids at their margins. Part anchors are checked against
  the model (each label point in its compartment ≥ 3 nm from its edge, or in its bilayer).
- **Cell kinds** `animal`, `plant` (exact shared walls), `bacterium` (a colony), with `gram`,
  `capsule`, `wall`, `plasmodesmata`; `style: section | surface` (surface: a schematic of pores and a
  lipid mosaic).
- **Close-ups**: lipids, tubulin and actin beads, mosaic are built only round views spanning ≤ 0.45 µm
  (start and each `zoom_to`: `closeups`), so they cost nothing elsewhere; lipids leave a gap round
  membrane proteins (`lipid_layout(gaps=)`, random stream unchanged).
- **Zoomed-view labels**: each `zoom_to` view gets labels from `part_anchors` on the body's edges,
  shown near that view; `ZoomTo.Options.labels` (`true` / `false` / names).
- **Emphasis through LOD**: `Pieces` records what an action did to a piece relative to what LOD last
  wrote (a factor per owner) and applies it to pieces that appear later; hidden pieces drop their
  points.
- **Public:** `CELL_COATS`, `CELL_MEMBRANES`, `CellAnchor` (`cellworld.Anchor`), `cell_part_anchors`.
  YAML 1.1's `on:` (read as `true`) is accepted in objects and views.
- **Limits:** no `set_state` in `cell`; an endocytosed vesicle is not added to the world; zoomed-view
  labels can go stale after a process (`labels: false`).

### 95.9 Molecules and notation (Step 204)

- **Decided:** a separate type `molecule` for close-ups (fixed camera in nm, a membrane across the
  view, molecules in rows), and molecules as **kinds of the cell world** for `cell`; both draw the same
  glyphs.
- **Modules** (`cellworld`, no manim): `notation` (chemical markup: `Ca2+` → Ca²⁺; a monatomic ion's
  digits are its charge, a polyatomic one's counts), `names` (species nomenclature as data — HGNC, MGI,
  RGD, SGD, PomBase, FlyBase, ZFIN, E. coli, TAIR —; italic checked gene symbols, roman protein names
  refused when written like the gene; modification markers P / Ub / Ac / Me with their residues;
  histone marks against the human H2A, H2B, H3.1, H4 sequences), `sequences` (alphabets, complements,
  `CODONS`, Crick's wobble), `molecules` (`MoleculeKind`: markup, family, nm sizes with ranges,
  places / membranes with reasons, oriented part and side — `n` cytosolic / matrix / stroma, `p`
  exoplasmic —, states, cells; `check_membrane`, `check_faces`, `check_place`; each also a cell-world
  `Kind`), `glyphs` (`MoleculeSpec`, `check_molecule`, `molecule_glyph`: prims in nm, a membrane
  protein's +y exoplasmic, bilayer mid-plane y = 0, named anchors), `placing` (both sides of each
  candidate probed so the exoplasmic side faces the exoplasmic compartment). Renderer
  `cell_draw/molecules.py`. Scenes `scenes/molecule.py` (layout), `scenes/molecule_runtime.py`
  (process runtime mixin), `scenes/cell.py`.
- **Sizes** in the molecule catalog; protein diameter 2 × 0.066 × M^⅓ nm (`protein_size`, Erickson
  2009).
- **Rules** (errors with the reason): wrong membrane or facing, `in:` / `at` for a membrane protein,
  wrong compartment or cell, another kind's option, a missing state, an opposed symport, wrong bases,
  an anticodon not reading its amino acid, a marker on the wrong residue, gene / protein case. Details:
  docs/CONFIG.md#molecules-in-a-cell and #molecule.
- **LOD**: `molecules` (a 10 nm molecule whole from 6 px) and `molecule_detail` (40–70 px). A `zoom_to`
  a molecule frames its glyph at about half the view.
- **`molecule` layout**: membrane proteins in a row along the membrane (three or more on several rows
  when that frames them larger), soluble ones in rows on their side, each slot as wide as its name;
  part labels in columns or rows, whichever leaves the drawing larger.
- **Public:** `MOLECULE_KINDS`, `MoleculeKind`, `MoleculeSpec`, `MoleculeGlyph`, `molecule_glyph`,
  `check_molecule`, `place_glyph`, `glyph_mobjects`, `membrane_sides`, `protein_size`, `BILAYER_NM`,
  `check_molecule_membrane`, `check_molecule_faces`, `check_molecule_place`, `SPECIES`,
  `MODIFICATIONS`, `nomenclature_species`, `check_gene`, `check_protein`, `gene_markup`,
  `protein_markup`, `check_modification`, `histone_mark`, `chem_markup`, `chem_plain`, `charge_of`,
  `check_markup`, `CODONS`, `check_sequence`, `check_trna`, `codons_read`, `reverse_complement`,
  `LIPID_HEAD_HUE`, `LIPID_TAIL_HUE`.

### 95.10 Transport and membrane processes as actions (Step 205)

- **Actions.** `molecule`: `set_state`, `transport`, `diffuse`, `osmosis`, `action_potential`.
  `cell`: `motor_walk`, `endocytosis`, `exocytosis` (`snares: generic | constitutive | neuronal`,
  default `generic`: a cell-type option on the action, not a cell kind). Each validates before
  rendering (wrong scene, unknown molecule, missing state, a passive path against its gradient, an ion
  a channel does not pass, a walk past a track's end, a vesicle fused twice). Keys:
  docs/CONFIG.md#cell-actions and #molecule.
- **Layers.** `cellworld.transport` and `cellworld.traffic` (no manim): a process is a `Plan` of
  `Phase`s (protein states, particle `Move`s in nm with a Brownian-bridge walk, a caption); an event's
  membrane shapes are keyframes. `cell_draw/traffic.py` (`EventDrawing`) draws events;
  `scenes/molecule_process.py` plays plans (`PlanPlayer`, `Hold`; prims matched by look and
  interpolated, unmatched ones fade).
- **Physics** (data `TYPICAL_CONCENTRATIONS`, `MOLECULE_TRANSPORTERS`, `MOLECULE_ION_FLOW`): Nernst with
  RT/F = 26.7 mV at 37 °C; ΔG = RT ln(c₂/c₁) + zFΔψ; a passive path needs ΔG < 0, a coupled carrier a
  total ΔG < 0 over its stoichiometry; resting potential −70 mV; the Na⁺/K⁺-ATPase Post–Albers cycle;
  carriers by alternating access with an occluded state; inactivation only on voltage-gated channels;
  simple diffusion only for bilayer-permeant molecules; the action potential a monotone cubic through
  textbook points; motor step sizes per motor, each walking to its end.
- **Public:** `cell_transport`, `cell_traffic`, `CellEventDrawing`, `cell_motor_curves`,
  `cell_motor_parts`, `MOLECULE_ION_FLOW`, `MoleculePrim`, `carrier_parts`, `molecule_small_prims`,
  `MOLECULE_ION_RADII`, `MOLECULE_ION_HUES`, `MOLECULE_TRANSPORTERS`, `TYPICAL_CONCENTRATIONS`,
  `molecule_pump_type`.

### 95.11 Gene expression as actions (Step 206)

- **Where.** A `gene:` param (in `molecule` and `cell`) makes the gene a target. `molecule` with a gene
  is a close-up of every base and residue (`transcribe`, `cap`, `splice`, `polyadenylate`, `export`,
  `translate`, `target_er`, `glycosylate`, `fold`) and has no `molecules`, `solutes`, `membrane`,
  `potential`. `cell` follows products through the cell (`transcribe`, `export`, `translate`,
  `to_golgi`, `secrete`); close-up steps in a cell are refused with a pointer to `molecule`. Keys:
  docs/CONFIG.md#a-gene-in-a-cell.
- **The gene** (`GeneSpec` → `build_gene` → `Gene`): a coding-strand `sequence` with 1-based introns, a
  `protein` (back-translated with frequent human codons), or generated from `codons` and `seed` (with
  promoter, Kozak, consensus introns ≥ 30 nt, stop, polyadenylation signals; bacterial elements for a
  bacterium). ORF = first AUG of the mature mRNA to the first in-frame stop; NCBI table 1; human
  anticodons (inosine at the wobble place). Signal peptide by a von Heijne rule; sequons N-X-S/T, X not
  Pro. A premature stop more than `NMD_DISTANCE` = 50 nt before the last junction is refused.
- **Rules** (`ExpressionState`, `step_problem` / `advance`, replayed in beat and `at` order): each step
  needs its predecessors (e.g. `target_er` only for a signal peptide before it leaves the tunnel,
  `glycosylate` only in the ER once a sequon reaches the OST). In a cell, `cell_steps` expands each
  step into the molecular steps it implies, so the same rules apply.
- **Modules.** No manim: `cellworld/expression.py` (model, rules), `expression_stage.py` (stage in
  nucleotide slots: `Look`, `Pose`, `Clip`, `Builder`), `expression_cyto.py` (ribosome, tRNAs, tunnel,
  SRP/Sec61, OST, chaperones), `expression_route.py` (`RoutePlanner` in µm; gentle curves). Drawing:
  `cell_draw/expression.py` (`ExpressionDrawing`, one mobject per look, made up front),
  `cell_draw/expression_route.py` (`RouteDrawing`). Scenes: `scenes/molecule_gene.py`
  (`GeneExpression`, `StagePlayer`), `scenes/cell_expression.py` (`CellExpression`, `RoutePlayer`),
  `scenes/gene_actions.py`.
- **Scale.** Nucleic acids are stretched about 6× against proteins; the scene says *schematic: not to
  scale*. Window `WINDOW_WIDE` 36 / `WINDOW_TALL` 15 slots, chosen by the **frame**'s shape.
- **Timing.** An action's length follows its content (`run_time_for` builds and caches the clip);
  elongation captions two cycles then runs fast (≤ 7 s); a short beat squeezes it; `run_time` overrides.
- **Public:** `GENE_CELL_STEPS`, `GENE_CHAPERONES`, `GENE_STEPS`, `ExpressionState`, `Gene`, `GeneSpec`,
  `build_gene`, `parse_protein`, `signal_peptide_length`, `gene_advance`, `gene_cell_advance`,
  `gene_cell_step_problem`, `gene_step_problem`, `ExpressionStage`, `GeneRoutePlanner`,
  `gene_route_problem`, `ExpressionDrawing`, `GeneRouteDrawing`.

### 95.12 Signalling pathways: the `pathway` scene (Step 207)

- **Modules.** No manim: `cellworld/pathway.py` (bands, node kinds, arc types, `build_pathway` with
  every rule, loops, activity and effects, signal waves, drug table), `pathway_layout.py`,
  `pathway_templates.py` (`PATHWAY_TEMPLATES`: `gpcr_camp_pka`, `rtk_ras_mapk`, `pi3k_akt`).
  Runtime: `scenes/pathway.py`, `scenes/pathway_play.py` (`PathwayPlay`), `scenes/pathway_actions.py`
  (`PATHWAY_ACTIONS`: `signal`, `inhibit`, `knockout`, `drug`, `amplify`; order replayed). `focus`
  (`iso_actions.py`) also moves the camera onto pathway targets.
- **Shared names**: band labels from the catalog's compartments and membranes (other compartments are
  aliases of their bands); `names.check_gene` / `check_protein` / `check_modification`,
  `notation.chem_markup`.
- **Notation** (SBGN PD / AF adapted) and **rules** (did-you-mean; biological impossibilities of arcs,
  places and states): docs/CONFIG.md#pathway. An inhibitory phosphorylation is a T-bar with a P,
  played as switching its target off. Loops not broken by a `feedback` arc (Tarjan SCCs) are warnings
  of `validate_project`.
- **Layout** (`pathway_layout`, deterministic): the main axis is the flow (LR: bands as columns; TB:
  rows). A membrane band is one rank; other bands are layered by longest path over arcs that are
  neither feedback nor loop-closing. **Satellites**: a node nothing upstream activates acting on a
  node with other inputs, and (LR) an outcome after its node, stand beside that node in its rank. Long
  arcs get dummies; barycenter sweeps (blocks move whole), fewest crossings kept; cross positions by a
  weighted isotonic fit. **Routes** run straight through each rank's slab and change cross position
  only in the gaps between ranks, so no route passes through a node (`route_hits`).
- **Fitting.** Per direction (the frame's own first) the largest text factor in `GROWTH` (1.9× down to
  `readable_size()` × 1.02) at which the layout fits; the other direction wins only with text 12 %
  larger. Up to 3 % overflow at readable size is scaled quietly, more draws smaller with a warning. A
  width-bound pathway spreads up to 3× (`SPREAD`). `edge_labels: auto` drops arc labels when they
  would cost more than 10 % of text size. Band names, arc labels, pills take the candidate spot
  covering least (earlier labels cost 3×); nodes with badges are made taller so badges never cover
  names.
- **Logic.** `signal_waves`: breadth first, each step carrying a sign (on, off, reached), so a double
  negative turns its target on; feedback fires last; knocked-out, drugged and held nodes stop it.
  `activity` (steady state, stimulus on): no activating input 1; else the geometric mean of activating
  inputs (2 % residue for a lost one among several), divided by 1 + 3 × active inhibitors; off nodes
  0; feedback and loop-closing arcs left out. `effects`: ↑ above +25 %, ↓ below −20 %, off below 0.03.
  Known drugs must name their target.
- **Drawing**: changes remembered for `until`; part-way items are built invisible and drawn by `Draw`
  / `Appear` (Manim adds an animation's mobjects when the whole `Succession` starts); effects appear
  upstream first (topological `LaggedStart`).
- **Public:** `cell_pathway`, `cell_pathway_layout` (modules), `PATHWAY_BANDS`, `PATHWAY_EDGE_TYPES`,
  `PATHWAY_NODE_KINDS`, `PATHWAY_TEMPLATES`, `Pathway`, `PathwaySpec`, `build_pathway`.

### 95.13 Cell cycle, division and energy: the `cell_cycle` and `metabolism` scenes (Step 208)

- **Decided: two scene types, not `cell` actions** — a cycle is a diagram in time, a division a cell
  whose chromosome count matters more than µm scale, energy pathways graphs plus a membrane section.
  `cell_cycle` (`mode: cycle | mitosis | meiosis`), `metabolism` (`process: glycolysis |
  link_reaction | tca | etc | light_reactions`); actions `advance` (both), `checkpoint` (`cycle`).
- **Modules.** No manim: `cellworld/cycle.py` (phases, restriction point at 60 % of G1, checkpoints as
  regulator rows, `cycle_geometry`, stylised cyclin–CDK curves, `CycleState.advance_problem`: G0 only
  from G1 before R, no passing an arrested checkpoint), `cellworld/division.py` (`stage_counts`,
  `check_spec`, `plan_division`: keyframes of items; **every keyframe has every item**, missing ones at
  opacity 0, so drawing is plain interpolation; chromatids coloured per segment so crossovers swap;
  2n ≤ 8, animal cell), `cellworld/energy.py` (steps, chain components, proton and ATP counts,
  `check_setting`, `tallies`, `electron_path`, `chain_effects`). Drawing: `scenes/division_draw.py`,
  `scenes/bio_draw.py`, `scenes/cell_cycle.py`, `scenes/metabolism.py` (columns grow up to `GROW` =
  1.6×), `scenes/cycle_actions.py`. Every text that will show is made at build time and shown by
  opacity. Enzyme names are roman.
- **Validation** replayed in beat and `at` order (`action_sequence_problems`): arrests and their
  `until`, stage order, `expect` counts, the gradient before ATP synthase, the cycle's turns.
  Non-disjunction: §96.11.
- **Public:** modules `cell_cycle_model`, `cell_division`, `cell_energy`.

### 95.14 Scientific accuracy lint and references (Step 209)

- **Knowledge** (`vidgen.cellworld.accuracy`, no manim): narration checks `direction_claims`,
  `location_claims` (`PLACES`), `count_claims`, `placement_claims`, `pathway_claims`, `naming_claims`
  (`protein_form`), transport words (`says_active`, `says_passive`, `transport_mode`). **False
  positives avoided by narrowness**: normalised text split into sentences and `;` clauses; sentences
  with a negation, contrast or question skipped; each claim needs its context words; contexts that make
  a direction right exempt it. English only, one sentence at a time.
- **Rules** (`vidgen.lint.science_rule`, scene scope, default warning, `RuleConfig`s in `LintRules`,
  after `music_check` in `LINT_RULES`): `science_scale` (`factor` 1.5 against `size_range` /
  `WIDTH_RANGES` / `CELL_TYPICAL`, only while `scale_bar` and not `not_to_scale`; `MOST_PER_CELL`
  always), `science_location`, `science_direction`, `science_energy`, `science_naming`,
  `science_pathway`, `science_counts` (what each reports: docs/CONFIG.md#lint-vidgen-lint).
  `science_issues(project, scene_id, rules)` validates the params through the registered type (no
  render; worlds from the lru cache); the runner fills `SceneContext.science` once per scene.
  Decided: config-level, not pixels — no drawn-exaggeration check (LOD minimum sizes are deliberate).
- **`not_to_scale: true`** (`cell`): a pinned "not to scale" plate lower right (part of the `cell`
  target) and no `science_scale` size findings.
- **Narration–picture rules**: `SHOWING_ACTIONS` includes the cell-biology actions; an action without
  its own `label` shows its single target's name from the type's optional classmethod
  `target_text(params, name)`, so `said_before_shown` narrows a label's arrival to that action.
- **References** (`vidgen.references`, no manim): `ReferenceConfig` (`label` ≤ 120 chars, at least one
  of `doi` / `pmid` / `isbn` / `url`, `id`), `FigureCreditConfig` (`text`, `license`, identifiers; a
  string is its text), checked offline (DOI `10.<4–9 digits>/<suffix>` with `doi:` /
  `https://doi.org/` removed, PMID 1–8 digits, ISBN-10/13 check digits, http(s) URL with a dotted
  host). No network check (decided: resolving DOIs is not offline-safe). Scene `references` (≤ 12),
  `figure_credit`; beat `cite`; video `citations: {show: footer | marker | card | none,
  card_seconds: 4, description: true}`. Numbers are video-wide by first appearance
  (`video_references`). Docs and tests use only fake identifiers (`10.0000/example`, PMID
  `12345678`, ISBN `978-0-00-000000-2`). User side:
  docs/CONFIG.md#references-and-figure-credits-references-figure_credit-citations.
- **On screen** (`vidgen/citations.py`, core): a `Citations` overlay (not a registered type) that
  `overlays.scene_overlays` adds for each scene with references or a credit; `Scene._build_overlays`
  builds overlays when any scene has citations. Shows the beat's `cite`s (all when no beat cites;
  hidden in a non-citing beat when others cite), or the card for the last `min(card_seconds,
  duration/2)`. Footer and marker reserve room (`default_reserve`) in every beat; the card lies over
  the end (`lint_skip = ("overlay_overlap",)`).
- **Description**: `write_chapter_list` writes `<output>_chapters.txt` when there are chapters or
  citations; `chapter_export.write_youtube_list(path, chapters, references)` appends
  `description_text` (References, Figure credits). Without references the output is byte-identical.
- **Fingerprint** leaves out `citations`, `references`, `figure_credit`, `cite`; adds a `citations`
  entry only when the scene or the next one (crossfades draw its overlays) has citations.
- **Public:** modules `cell_accuracy`, `video_references`.

### 95.15 Example, guide, cookbook and gallery (Step 210)

- **Example** `examples/gene-to-secreted-protein` (README with scene table; 9:16 variant `short`).
  **Decided: α1-antitrypsin, not insulin** — constitutively secreted and N-glycosylated, so every step
  shown is true of it.
- **Guide topic `biology`** (aliases `cell-biology`, `science`, `lecture`, `research`) and
  docs/COOKBOOK-CELL-BIOLOGY.md (pattern validated by `tests/test_docs.py`).
- **Gallery**: `GROUP_SECTIONS` merges the cell-biology guide groups into one "Cell biology" section;
  `SECTION_NOTES`, `SECTION_FOOTERS` / `DEFAULT_FOOTER` give further reading; stills are 256-colour
  palette PNGs (`STILL_COLORS`). Budget: §96.12.
- **Scenery**: the cell world's pieces, event overlays and a gene close-up's stage are `scenery`;
  `introspect` marks a group scenery when it holds only scenery, so `off_frame` ignores a zoomed view's
  cropped world.

### 95.16 Review of Phase U (Step 211)

- **Captions** never go below the readable size (a gene close-up reserves three lines in 16:9, four in
  9:16). `notes` on process actions: `auto` (default: full in a wide frame, first clause in a tall
  one), `full` / `true`, `short`, `false`; `cellworld.captions.short_note` cuts at the first `: ` /
  `; ` / ` — ` outside parentheses and markup (a first clause under 32 characters takes the next).
  **Decided:** shortening by rule — every caption is written statement-first.
- **Gene symbols in captions**: scene types may define `gene_symbols(params)`; the captions overlay
  (`genes: true`) collects them video-wide and italicises them (Manim `t2s`) where narration writes
  them as whole words, case-sensitive, except before "protein", "kinase", "receptor"…
  (`names.gene_spans`, `PROTEIN_WORDS`). **Decided:** video-wide and opt-out, not `terms:` (a term is a
  colour, not a style). Scenes without genes build unchanged texts.
- **Public:** `CellNoteMode`, `cell_note_text`, `gene_spans`; hook `gene_symbols(params)`;
  docs/CONFIG.md#captions.

## 96. Genetics at university level (Phase V, Steps 213–221)

Genetics videos with standard notation, **computed rather than drawn by hand** (ratios,
probabilities, gametes, map distances, frequencies come from a model), checked by `vidgen validate`
(did-you-mean errors) and `vidgen lint`, in 16:9 and 9:16. Built like §95: a manim-free model with
rules (`vidgen/genetics/`), renderers and scene types apart; additive and opt-in. Nomenclatures: NSGC
(pedigrees), ISCN (karyotypes), HGVS (variants), HGNC (symbols). User side: docs/CONFIG.md (`#cross`
… `#gwas`, the YAML and every user-facing refusal) and docs/COOKBOOK-GENETICS.md.

### 96.1 The phase (plan)

Built; §96.2–96.20 describe it: nine scene types, non-disjunction in `cell_cycle` meiosis, seven
`genetics_*` lint rules.

### 96.2 Scene types (decided)

| Type | Shows | Shares |
| --- | --- | --- |
| `cross` | Punnett square, branch diagram, gametes, ratios, chi-square | chromatid look of `cellworld.division` |
| `pedigree` | NSGC chart, mode analysis, risks | own layout (`vidgen.graph` does not know couples and sibships) |
| `karyotype` | G-band ideograms, karyogram, ISCN changes | chromosome outlines of `cellworld.division` |
| `linkage_map` | loci in cM, crossing over, three-point crosses | chiasmata as in `cell_cycle` meiosis I |
| `cell_cycle` (existing) | meiosis with `nondisjunction` | an option, not a type |
| `mutation` | a coding sequence with a variant, HGVS `c.` / `p.` | `cellworld.sequences.CODONS`, `cellworld.expression` |
| `crispr` | sgRNA, PAM, Cas9 cut, NHEJ / HDR | DNA ladder of `molecule` |
| `dna_lab` | `method: pcr \| gel \| sanger \| ngs` | one type, several techniques (like `metabolism`) |
| `population` | Hardy–Weinberg, seeded Wright–Fisher simulations | `vidgen.charts` axes |
| `gwas` | Manhattan, QQ, regional plots | `vidgen.charts` |

New types rather than modes: each is one picture grammar. Shared code lives in `vidgen.genetics` and
`cellworld` (sequences, names, chromosome look, accuracy helpers), imported, not copied. Gene symbols
go italic through `gene_symbols(params)` (§95.16) and are checked by `cellworld.names`.

### 96.3 The model (`vidgen/genetics/`, no manim; Step 213)

Modules `notation`, `model`, `genotype`, `phenotype`, `cross`, `modes`, `presets`, plus each scene's
model (§96.7–96.18); a test checks they import without `manim`. **Probabilities are
`fractions.Fraction` everywhere** (YAML floats go through their decimal text: `0.1` is exactly 1/10;
`"17%"`, `"1/6"` read too).

- **Alleles**: a base with an optional superscript after `^` (`I^A`, `c^{ch}`, `w^+`, `+`; `+` is wild
  type), written as text with Unicode superscripts (the `^` form stays where Unicode lacks the
  letter), Pango markup (alleles italic, X / Y roman) or YAML, which reads back. Symbols must differ
  between a system's loci. `X` / `Y` are alleles only in a system without sex chromosomes.
- **Locus** keys (`gene`, `trait`, `alleles` most dominant first, `chromosome: autosome | X | Y | mt`,
  `dominance`, `heterozygotes`, `lethal`, `penetrance`, `normal`, `expressivity`): docs/CONFIG.md#cross.
  Dominance hierarchy `"I^A = I^B > i"` (`>` complete, `=` codominant, `~` incomplete; one kind per
  level). Penetrance is an exact share per phenotype; non-penetrant carriers show `normal`.
  `expressivity` is recorded for pedigree and lint only.
- **Linkage**: loci in map order with each interval's RF, 0 ≤ RF ≤ 0.5; `coincidence` or
  `interference` for three loci; `rf_male`. Two or more X-linked loci need a group; Y / mt never.
- **Epistasis** between two loci, one pair per locus: `recessive` 9:3:4, `dominant` 12:3:1,
  `suppression` 13:3, `duplicate` 15:1, `complementary` 9:7, `cumulative` 9:6:1.
- **System** (`GeneticSystem`, `build_system(spec, where)`; or one `preset:` from `PRESETS`): loci,
  autosomal groups (an unlinked locus is a group of one), X group, Y and mt loci, epistasis, **traits**
  (phenotype columns). No ZW / X0 systems; one mt allele per individual.
- **Genotypes** (`parse_genotype(system, text, where, sex)`): `AaBb`, `A/a B/b`, phase `AB/ab` /
  `Ab/aB` (required when heterozygous at two linked loci), `X^H X^h`, `X^H/Y`, `X^{H,b}`, `Y^T`.
  Canonical: dominant haplotype first, X before Y. `genotype_text(system, g, style)` writes text /
  markup / YAML. Errors name the place (`parents[0]: genotype 'RrYx': …`) and the fix.
- **Modes** (`MODES`: `AD`, `AR`, `XD`, `XR`, `YL`, `MT`, hallmarks as data; `parse_mode`;
  `mode_of(system, locus, phenotype)`): one table for pedigree analysis and lint.

### 96.4 The cross engine (Step 213)

- **Gametes** (`gametes(system, genotype, sex)`): the product over autosomal groups of each group's
  haplotypes, with every crossover pattern inside a group (three loci: doubles `C·r₁·r₂`, singles
  `r − C·r₁·r₂`; two loci: parentals `(1 − r)/2`, recombinants `r/2`). Females recombine X-linked
  loci; males pass X or Y; `rf_male` applies to male meiosis; eggs carry the mtDNA.
- **Cross** (`cross(system, mother, father)` → `CrossResult`): every egg × sperm, zygotes summing to 1,
  the `lethal` share, survivors' distributions renormalized. Phenotype classes (with sex when the
  system has sex chromosomes) in textbook order: females first, then dominance order (incomplete
  heterozygotes between their parents) or the epistasis kind's order. `ratio()` smallest whole
  numbers, `ratio_text()` `9 : 3 : 3 : 1`. Without sex chromosomes or mtDNA parents are symmetric.
- **Test cross** (`make_tester`, `test_cross`): the partner homozygous (hemizygous) recessive at every
  locus, of the other sex; refused where the lowest level holds two alleles. **Reciprocal**
  (`reciprocal`): the lines swap sexes (a true-breeding mother needed at X-linked loci; the new father
  keeps the old father's Y; mtDNA goes with its line).

### 96.5 How the later steps plug in (plan; YAML as planned)

Superseded by the built scenes: §96.7–96.18 describe each type and docs/CONFIG.md its YAML.

### 96.6 Public (Step 213)

`vidgen.api`: `genetics` (the package; every genetics module is reached through it), `GeneticSystem`,
`CrossResult`, `build_genetic_system` (`genetics.build_system`), `genetic_cross` (`genetics.cross`),
`parse_genotype`, `GENETICS_PRESETS`, `INHERITANCE_MODES`.

### 96.7 The `cross` scene (Step 214)

- **Plan** (`genetics/punnett.py`): `build_plan(params)` → `CrossPlan`, cached by the params' JSON
  (`plan_cross`): system, parents, `kind: cross | test | reciprocal`, P line, `GameteView`s (frequency,
  each allele's homologue 0 / 1 / `None`, recombinant; ordered by frequency then dominance), `Cell`s
  (`fertilize(egg, sperm)`), `PhenotypeClass`es, `GenotypeClass`es, branch tree, notes. **Everything
  shown comes from `CrossResult`**, so a drawn ratio cannot disagree with the cross. `P`
  (true-breeding) must give one F1 genotype per sex.
- **Branch diagram**: a tree of survivors (sex, then each trait; or `branch: genotypes`), each node with
  its probability **conditional** on its path, so linked loci stay exact. Limits: Punnett up to 8 × 8
  (`show: auto` up to 4 × 4, branch beyond), at most 16 leaves.
- **Chi-square** (`genetics/stats.py`, no scipy): exact expected counts and χ², df = classes − 1,
  p = Q(df/2, χ²/2) by the upper regularized gamma (series below a + 1, Lentz's continued fraction
  above), critical value by bisection, E < 5 flagged; `observed` matched by words in any order or a
  list in class order.
- **Pictures** (`genetics/glyphs.py`, `class_glyphs`; drawn by `scenes/cross_draw.py`) from trait and
  phenotype words; coat heads via param `animal` / `glyphs.animal_of` (preset, title or trait, else
  neutral fur — never a guess).
- **Scene** (`scenes/cross.py`): 16:9 drawing left 58 %, panel right (parent 1 beside rows, parent 2
  over columns); 9:16 stacked. Tables at 1.15 × label size; genotype tables two-column beyond six
  classes, none beyond 12.
- **Actions** (`scenes/cross_actions.py`; `needs_visible = False`, each runs what it needs first):
  `form_gametes`, `fill`, `count`, `ratio`, `chi_square` (targets: docs/CONFIG.md#cross). Any of
  them makes the scene manual; `action_sequence_problems` refuses anything done twice. Crossing over
  shows as ringed recombinant gametes, not chiasmata (that is `linkage_map`).

### 96.8 The `pedigree` scene (Step 215)

- **Chart** (`genetics/pedigree.py`): `parse_pedigree(individuals, couples)` → `Pedigree` (people in
  YAML order, couples with children in birth order, generations, married-in, NSGC labels); person keys
  and the line form: docs/CONFIG.md#pedigree. Couples from shared children, `spouse:`, `couples:`;
  consanguinity also from shared ancestors. Generations solved as offsets per family (conflicts
  refused). NSGC ids (`II-3`) for everyone or no one; the numeral must match the generation and numbers
  read left to right as drawn. One locus per chart.
- **Layout** (`genetics/pedigree_layout.py`, deterministic, pitch units): anchors own rectangular
  blocks; a married-in partner beside its anchor; a sibship is its children's blocks centred under the
  mating line (twins adjacent). **Joins** (relatives as partners): both lines are pulled together up
  to the common ancestors' sibship, so the mating line crosses nothing.
- **Analysis** (`genetics/pedigree_analysis.py`): one locus, two alleles; genotype = (sex, disease
  copies); P(affected | genotype) = `penetrance` for the disease genotype, else 0 (no phenocopies).
  Founders follow Hardy–Weinberg with q → 0 (weights as (power of q, coefficient), an exact semiring
  for the leading term); with `carrier_frequency` c, q = c / (2 − c). `rare: true` (default): a
  married-in founder carries no more copies than its phenotype needs. Inference is variable
  elimination (greedy smallest factor), exact on consanguineous loops. A mode **fits** when the total
  weight is non-zero. An excluded mode's reason is the first textbook rule that applies, else the
  smallest nuclear family no genotypes fit; when penetrance 1/2 would allow it the reason ends with
  the exact condition ("— excluded unless I-1 is non-penetrant (Xᵃ Y; very unusual)"; "unusual" for
  AR, "very unusual" for XR); a fitting mode's note uses the same form. A male is never called a carrier
  of an X-linked allele. `infer`: posteriors, forced genotypes, obligate carriers, the proposed child's
  risk (per sex for X / Y modes; textbook factors shown when their product equals the risk).
- **Plan** (`genetics/pedigree_plan.py`, cached by params JSON): chart, layout, modes tried
  (`analyse`), stated mode (`mode`, or via `mode_of` from a `preset` / one locus), the mode used (stated
  if it fits, else the only fitting one, else none), `warnings`. `declared_mode_problem(plan)` feeds
  the lint. Validation errors: a male carrier under a stated X-linked mode, any carrier under YL / MT,
  `mode` against the locus' mode, `genotypes` / `deduce` / `risk` without a mode.
- **Scene** (`scenes/pedigree.py`, `pedigree_draw.py`, `pedigree_actions.py`): 16:9 chart 60 % with
  the panel right; 9:16 chart on top with what the tallest card leaves (`_panel_need`); a height-bound
  chart spreads up to 1.3 pitches. Actions `deduce`, `analyse`, `risk`; any of them, or a `reveal` of
  `generation:<R>` / `person:<id>`, makes it manual (else a generation per beat).

### 96.9 The `linkage_map` scene (Step 216)

- **Map functions** (`genetics/mapping.py`: `MAP_FUNCTIONS`, `rf_to_cm`, `cm_to_rf`): `none` d = 100 r
  (warned beyond `SHORT_CM` = 15 cM), `haldane` d = −½ ln(1 − 2r) M, `kosambi` d = ¼ ln((1 + 2r)/
  (1 − 2r)) M; RF > ½ refused; at r = ½ distance is ∞.
- **`analyse(loci, counts, function)`** → `MapAnalysis`: all 2ⁿ classes once (`class_key`,
  `parse_counts`); reciprocal pairs summed; largest pair parental (tie refused), giving the phase; for
  three loci the smallest pair is the DCOs (tie refused) and fixes the middle locus; RF exact
  (`Fraction`), DCOs counted in both intervals, outer RF counted directly; coincidence = observed /
  (RF₁ × RF₂ × N), interference = 1 − coincidence (undefined with an empty interval).
- **Plan** (`build_linkage_plan` / `plan_linkage`, cached): `counts` + `loci` or `map`, `phase`,
  `crossover`, `measure_interval`.
- **Scene** (`scenes/linkage_map.py`, `linkage_actions.py`): the homologue pair as four chromatids in
  true map order from the start (the table's columns move into map order at the `order` step); the
  steps are built-in `reveal` targets; actions `cross_over`, `measure`.

### 96.10 The `karyotype` scene (Step 216)

- **Model** (`genetics/karyotype.py`): 24 chromosomes with GRCh38 lengths (`LENGTH_MB`) and centromeres,
  classes, Denver groups, each arm's last ISCN band (`TERMINAL`, the one band fact checked). **Bands
  are schematic**: regions and bands (`REGION_BANDS` = 3 except the last region's), widths by a fixed
  hash; a named band (`band_ref`, `parse_band_label`) lies where this scheme puts it, so labels and
  breakpoints agree with the drawing (near, not at, ISCN positions; the card says so).
- **ISCN** (`parse_karyotype`): count, sex chromosomes, `+N` / `-N`, `del`, `dup`, `inv`, `t`, `rob` /
  `der` between acrocentric autosomes, `mat` / `pat` / `dn`; the count must equal 44 + sex + gains −
  losses − Robertsonian fusions; refusals: docs/CONFIG.md#karyotype. Order is lint
  (`iscn_order_problem`, §96.18). A cell's chromosomes are `Copy`s by slot; a derivative is
  `Segment(chrom, a, b)` pieces (a > b inverted) with its centromere. Conditions are named only where
  certain.
- **Scene** (`scenes/karyotype.py`, `karyotype_draw.py`, action `rearrange`): band polygons cut from
  capsules, fixed neutral greys in every theme, foreign material accent-tinted; `show: auto |
  karyogram | ideogram`. `rearrange`: segments (`segment_piece`) `ReplacementTransform` into the
  derivative's.

### 96.11 Non-disjunction in `cell_cycle` meiosis (Step 216)

`DivisionSpec.nondisjunction = (I | II, pair index)` (param `{division, pair}` from 1), checked in
`check_spec` (meiosis only; an existing pair). I: both homologues go to the first daughter at anaphase
I; II: in the first daughter both sisters go to the upper pole. Daughters' and products' chromosomes
are lists (`members`, `products`); without the option every keyframe is unchanged. `gamete_outcomes`
(I: 2 of 4 n + 1, 2 n − 1; II: 2 of 4 n, 1 n + 1, 1 n − 1); `nondisjunction_cells` gives per-cell
(chromosomes, chromatids) once they differ and refuses per-cell `expect` there.

### 96.12 The gallery budget (Step 216)

Every gallery entry is held to `ENTRY_MAX` = 0.36 MB (page, two palette stills, two GIFs each ≤
`CLIP_MAX_BYTES`), one test per entry, under a total `BUDGET` (both in `tests/test_gallery.py`).
Decided: the budget grows with the entries rather than lowering new GIFs' frame rate; genetics
samples are two or three short beats.

### 96.13 The `mutation` scene and HGVS (Step 217)

- **`CodingSequence`** (`genetics/hgvs.py`): coding-strand DNA from `c.first` (`c.1` = the A of the
  ATG), coding exons as `c.` ranges, intron sequences when known; `coding_sequence()` checks bases (U
  read as T), exons (in order, touching, covering) and length.
- **DNA variants** (`parse_c` → `RawVariant`, `resolve` → `DnaVariant` + `Edit`): substitution, `del`,
  `dup`, `ins`, `delins`, intronic substitutions (reference base from the intron, else the GT…AG
  consensus at ±1, ±2); common slips refused with the fix (docs/CONFIG.md#mutation).
  `normalize(cds, edit)` trims common bases, shifts indels 3′-most **within the exon** and turns a
  copying insertion into a dup; `check_written` refuses a non-canonical form with the canonical one.
- **Protein** (`protein_change`, with `CODONS`): synonymous, missense, nonsense, frameshift (`fs`
  counts the first changed residue as 1; no stop → `fs*?`), in-frame indels, `p.(Met1?)`, `ext`;
  splice site `p.?`. `ProteinChange.text(style, stop)`; `parse_p` and `check_stated` compare an
  author's form, naming legacy numbering when the residue is one less.
- **Consequence** (`consequence`): canonical change, protein change, class, translations, notes (NMD
  when a premature stop lies more than `NMD_DISTANCE` = 50 nt upstream of the last junction, judged
  only with complete exons; a splice site predicts exon skipping for an internal exon, else intron
  retention; `splice: skip | retain | auto`).
- **Reference genes** (`genetics/reference_genes.py`): real coding windows of **HBB** (NM_000518.5),
  **CFTR** (NM_000492.4, exons 11–13) and **GJB2** (NM_004004.6) with their textbook variants and
  legacy names (CFTR legacy = c. + 132; its old exon numbering is in the module text); a test checks
  each variant's published protein change.
- **Plan** (`genetics/mutation.py`, `build_mutation_plan` / `plan_mutation`, cached): a reference
  window, an author's `sequence` or a `cellworld.expression` gene; symbol checked by `cellworld.names`;
  `VariantView`s.
- **Scene** (`scenes/mutation.py`, `scenes/molecular_draw.py`, action `mutate` in
  `scenes/molecular_actions.py`): reference and variant rows of base tiles (Phase U base colours
  lightened for 4.5:1 contrast) in a fixed codon frame, so a frameshift regroups every later codon. The
  card drops notes, then the legacy name, then the big type rather than go below readable size.

### 96.14 The `crispr` scene (Step 217)

- **Model** (`genetics/crispr.py`): `CAS` holds SpCas9 (`NGG`, 20-nt spacer) and SaCas9 (`NNGRRT`,
  21–23 nt), both cutting both strands 3 bp 5′ of the PAM (blunt). `find_guides` lists every
  protospacer with a PAM on either strand; `check_guide` refuses a bad spacer listing the guides that
  would work. `repair`: NHEJ indel (default +1, copying the base 4 bp upstream of the PAM) or HDR with a
  donor carrying `edit`; with `coding_first` the outcome runs through `hgvs.edit_consequence`, and
  notes say whether the repaired allele keeps its protospacer and PAM.
- **Scene** (`scenes/crispr.py`): drawn **from the strand that carries the PAM** (a bottom-strand guide
  shows the reverse complement, so the protospacer reads 5′→3′ on top; HGVS keeps the target's
  numbering). Steps / actions `scan`, `cleave`, `repair` after `dna`. In 9:16 tiles shrink to fit when
  the protospacer and PAM do not fit at readable size.

### 96.15 The `dna_lab` scene (Step 217)

- **Model** (`genetics/dna_lab.py`), one plan per `method`. **PCR**: primers checked against the
  template (each binds once; they point towards each other); Tm by the Wallace rule below 14 nt, else
  the GC formula; annealing refused at or above the lower Tm. `pcr_strands` simulates the first cycles
  exactly (the defined-length product first appears in cycle 3); `PcrPlan.counts(n)`: 2ⁿ molecules,
  2ⁿ − 2n of exactly the product (a primer at the template's edge gives it a cycle earlier). **Gel**:
  `resolving_range` from the standard agarose table; `migration` linear in log₁₀(size) over that range
  (0.1–0.9 of the run), smoothly compressed outside, strictly decreasing; `size_from_distance` reads
  the ladder log-linearly. **Sanger**: seeded peaks, heterozygous calls by IUPAC code. **NGS**
  (`plan_ngs`): seeded reads with per-base errors; `variant` `31C>T` or `a_bdel[BASES]` (1–12 bp);
  the call counts only reads spanning the whole site (`NgsPlan.site_depth`): heterozygous ≥ 15 %,
  homozygous ≥ 85 %, below 10× *low coverage*; reads start from `MIN_OVERLAP` − L to len −
  `MIN_OVERLAP` and are clipped, so coverage is even to the window's edges.
- **Scene** (`scenes/dna_lab.py`, action `run: <target>`): each method's steps beat by beat; gel
  readings one per size ("≈" outside the resolving range); a gapped NGS read as two pieces and a line;
  a short call card drops lines, never the call.

### 96.16 The `population` scene (Step 218)

- **Hardy–Weinberg** (`genetics/population.py`, `hardy_weinberg(spec)` → `HardyWeinberg`): exactly one
  source (`counts`, `frequencies`, `p`, `incidence`; q = √incidence exact as a `Fraction` when both
  parts are squares; `incidence` refused with `inbreeding`); expected p² + Fpq, 2pq(1 − F), q² + Fpq.
  `hwe_test`: exact expected counts and χ², **df = 1** (three classes − 1 − one estimated frequency),
  critical 3.84, E < 5 flagged, F̂ = 1 − H_obs/H_exp. Two alleles only.
- **Wright–Fisher** (`simulate(spec)` → `Simulation`): each generation the expected frequency after
  selection, mutation and migration is sampled as Binomial(2N, p')/2N with
  `numpy.random.default_rng(seed)` (same seed, same lines; replicates draw in turn from one generator);
  `bottleneck`, `founder`; the deterministic recursion; fixation / loss generations (absorbing only
  when nothing reintroduces the allele); expected H_t = H_{t−1}(1 − 1/2N_t); the first line's
  individuals per generation (seeded, matching that generation's allele count). Fitness `{AA, Aa, aa}`
  or `s`, `h`; viability selection only. `model` defaults to `hardy_weinberg`; `model: mutation`
  exists and `mu` / `nu` add to any simulation.
- **Plan** (`build_population_plan` / `plan_population`, cached): a param of another model is refused
  naming its model.
- **Scene** (`scenes/population.py`, actions `simulate`, `resample` in `population_actions.py`): at most
  100 dots (one per N/100 beyond); Hardy–Weinberg steps are `reveal` targets; any `simulate` /
  `resample` / `reveal` of `generation:<t>` makes it manual; a `simulate` that does not go forward is
  refused.

### 96.17 The `gwas` scene (Step 218)

- **Model** (`genetics/gwas.py`): p kept as −log₁₀ p, parsed through `decimal` (`"3e-450"`; 0 < p ≤ 1);
  z ↔ −log₁₀ p two-sided (`erfc`, asymptotic beyond z = 37). Chromosomes 1–22 and X (Y / MT refused);
  positions in bp or `"53.8 Mb"` (a bare number below 1000 refused), within `karyotype.LENGTH_MB`.
  Author data: `read_rows` (CSV / TSV), inline `variants`, `clump` (leads below `label_p` = 5 × 10⁻⁸
  labelled). Synthetic (tagged *simulated data*): seeded null background (default 2400 variants,
  optional λ inflation) plus `peaks` with LD as distance decay (z_i = r_i z_lead + √(1 − r²)·ε).
  λ_GC = median χ²₁ / 0.4549 (over the null background for synthetic data); at most `MAX_DRAWN` = 4000
  points drawn (every p < 0.01 kept). `build_gwas_plan` / `plan_gwas` (cached).
- **Scene** (`scenes/gwas.py`; action `regional` in `scenes/population_actions.py`): `plot: manhattan |
  qq | both`, optional regional plot (five fixed r² colours); a `reveal` of a later target makes it
  manual (the `regional` action does not).

### 96.18 The genetics accuracy lint (Step 219)

Built on §95.14's framework: knowledge in `vidgen.genetics.accuracy` (reusing `cellworld.accuracy`'s
`sentences`, `plain`, `normal_text`, `Claim`), glue in `vidgen.lint.genetics_rule` (`GENETICS_RULES`,
`genetics_issues(project, scene_id, rules)`); findings are appended to `SceneContext.science` after the
`science_*` ones, so they are reported, ignored and configured the same way. `ScienceIssue` has an
optional own `severity`. Configs `GeneticsRatioRule` / `GeneticsLinkageRule` (`tolerance` 0.05),
`GeneticsHweRule` (`tolerance` 0.1), `GeneticsPedigreeRule`, `GeneticsCrisprRule`,
`GeneticsKaryotypeRule`, `GeneticsHgvsRule`; scene scope, default warning, last in `LINT_RULES`. What
each rule reports: docs/CONFIG.md#lint-vidgen-lint.

- **Reading** narrowly: sentences with a negation, contrast, question or hypothetical (`HYPOTHETICAL`)
  are skipped. `shares_in` reads shares in digits and words, each knowing "about" (relative
  `tolerance`), bounds (not compared) and written precision; `ratios_said` reads ratios with only the
  cross's phenotype words between numbers. English only.
- **Model sources**: `genetics_ratio` compares against `cross_ratios(plan)` (reduced, sorted);
  `genetics_pedigree` raises `declared_mode_problem` as an **error** on the first beat and checks
  `pedigree_claims` against `infer`; `genetics_linkage` uses `map_pairs` / `cross_pairs`;
  `genetics_hwe` the scene's Hardy–Weinberg model; `genetics_crispr` `PAMS` / `SPACER_RANGES`;
  `genetics_karyotype` `parse_karyotype` and `iscn_order_problem`; `genetics_hgvs` `genetics.hgvs`,
  `check_stated` and `_legacy_numbering` (info for legacy shorthand; `F508del` not reported).
- **`science_naming` reused**: `science_issues` validates `mutation`, `crispr`, `gwas`, `karyotype`
  too and asks their `gene_symbols(params)`, which also italicise them in captions
  (`video_gene_symbols`).
- **Narration–picture rules**: `SHOWING_ACTIONS` includes the genetics actions; `target_text` on
  `cross`, `pedigree`, `gwas` (`peak:<label>`), `karyotype` (`band:<band>`).

### 96.19 The example, the guide topic and the cookbook (Step 220)

- **`examples/cystic-fibrosis`** (README with scene table): one disease through six of the nine types
  and a `process` recap; diagnosis by sequencing because a 3-bp difference does not show on an agarose
  gel. A test validates both variants, runs the genetics lint and checks narrated numbers against the
  plans.
- **Shared lint details**: a lone character on a plate is a tile (not a label for `label_spacing`, not
  a word for `max_words`); `introspect._backdrop` widens a glyph box narrower than half its height
  before sampling.
- **Docs**: guide topic `genetics` (aliases heredity, inheritance, medical-genetics, punnett, hgvs),
  docs/COOKBOOK-GENETICS.md, gallery Genetics section (`SECTION_NOTES`, `SECTION_FOOTERS`); the CONFIG
  completeness test covers the nine types.

### 96.20 Review of Phase V (Step 221)

- **`fit_text` ligatures** (shared): Manim's `Paragraph` assigns glyphs to lines by counting characters,
  so a ligature (Source Serif 4 "fi"; Inter "->", "=>") moves letters to the next line. `_paragraph`
  rebuilds a multi-line paragraph with `disable_ligatures=True` when its glyph count differs from its
  letter count (keeping the first build if Manim refuses). Other texts are built unchanged.
- The review's data checks, wording and frame-use rules are folded into §96.8–96.15.
## 97. Science foundation: scientific charts and worked calculations (Phase W, Steps 222–228)

One chart core shared by science scenes, and worked calculations with units (the `calculation`
scene and a lint comparing narrated numbers with computed ones). User guide:
`docs/COOKBOOK-SCIENCE-CHARTS.md`; keys: docs/CONFIG.md#plot, docs/CONFIG.md#calculation.

### 97.1 The phase (plan)

Done: §97.3–§97.12, with the review folded in (§97.13).

### 97.2 How charts are drawn today (survey, Step 222)

`vidgen.charts` (§33–34, public, used by extensions) serves `bar_chart`, `line_chart`, `scatter`,
`histogram`, `heatmap`, `map`, `pie`, `population`, `gwas`; `scenes/math_axes.py` (§87.6–87.8,
axes through the origin) serves `function_plot` and `number_line`. Lab pictures draw their own
(action-potential inset in `molecule`, cyclin curves in `cell_cycle`, Sanger / gel / coverage in
`dna_lab`). The core (`plotcore`) serves `plot`, the PCR trace (§97.12) and `orbit` (§98).

### 97.3 The design

**Two layers.** `vidgen/plotcore/` decides everything that needs no drawing (ticks, labels,
domains, data-to-frame mapping, panel layout, clipping); it imports only `vidgen.errors` and
`vidgen.mathexpr` (no manim, no scipy; a test imports it in a fresh interpreter) and is
deterministic, so tests check layouts without rendering. Text sizes come from a callback
(`Measure: text -> (width, height)`): `plot_draw.text_measure` (real `Text`, cached) or
`approx_measure` in tests. `vidgen/plot_draw.py` only turns layouts into manim objects. Both are
`vidgen.api` modules (`plotcore`, `plot_draw`); public names are `plotcore.__all__`.

- **Ticks** (`plotcore.ticks`). Linear: the smallest step of 1, 2, 2.5 or 5 × 10ᵏ giving at most
  `max_ticks` from a multiple at or below the data to one at or above (`layout.nice_ticks`'s
  rule), values cleaned to 12 significant digits, a single value widened (`5..5` → `4.5..5.5`);
  `inside=True` (fixed domain): the densest round step with ≤ `max_ticks` inside. Log 10:
  decades (every k-th beyond `max_ticks`), 1-2-5 within two decades, minor 2–9 × 10ᵏ when every
  decade is labelled. Symlog: linear within ±`linthresh` (→ ±1), then `sign(v)(1 +
  log₁₀(|v|/linthresh))`; default `linthresh` the decade of the smallest non-zero magnitude, at
  most 1/1000 of the largest.
- **Numbers** (`plotcore.numbers`): plain Unicode, no LaTeX (minus U+2212, superscripts).
  `auto`: linear plain while the largest tick is in [10⁻³, 10⁵), else ÷10ⁿ (n multiple of 3) with
  the power in the title (`distance (10⁶ km)`), or full ticks for a narrow window far from 0;
  log / symlog plain from 0.001 to 10 000, else `10⁻⁹`. Also `plain`, `sci`, `si` (linear: one
  prefix in the title; log: per tick; needs a base unit, `km` refused), a `str.format` pattern.
  Axis title `label (unit)`.
- **Axes** (`plotcore.axis`). `AxisSpec` (scale, `lo`/`hi`, `reversed`, `linthresh`, `breaks`,
  `format`, `unit`, `label`, `max_ticks`, `include_zero`, `exact`, `margin`, `tight`, `ticks`);
  `problems(values, name)`: log with a value ≤ 0, data past `min`/`max` (never clipped
  silently), a value in a break, bad breaks, `linthresh` off symlog, `si` with a prefixed unit.
  `build_axis(values, spec, lo=, hi=)` → `Axis`: free ends reach the outer ticks; fixed ends (or
  `exact`) keep ticks inside; `tight` (`plot` uses 0.08) takes the next round tick only when it
  adds ≤ 8 % of the span, else `TIGHT_PAD` 4 % past the data. `Axis.fraction(v)`: transform,
  reversal (`1 − f`), breaks (each `BREAK_GAP` = 4 % of the length).
- **Figures** (`plotcore.figure`). `layout_figure(area, panels, measure, arrange, share, gap, top,
  aspect, weights)` → `PanelLayout`s in the chart scenes' style (§33): y labels right-aligned left
  of the plot, horizontal y title above (no rotated text), x labels and title below. `rows`
  stacked (with `share` one x axis, only the lowest labelled, equal edges); `columns` sharing y.
  Touching labels thinned (`label_stride`, also used by `charts`). `aspect: equal` (one panel,
  linear): the roomier axis widens about its middle (iterated) or, with fixed ends, the plot
  narrows; both axes take the larger step (`_common_step`). `clip_polyline` (Liang–Barsky; `nan`
  breaks a line). `layout_axes(area, x, y, measure, top=)`: one panel from caller-built `Axis`es.
- **Tables** (`plotcore.data`). `read_table(text, source)`: `,` `;` or tab (from the header), `#`
  comments, header units `name (unit)` (space before the bracket, so `f(x)` is a name), `name
  [unit]`, `name / unit`; `.` decimals; blank / `NA` / `NaN` are gaps. Errors name file, line and
  column; `Table.column` has did-you-mean (own `difflib` helper).
- **Drawing** (`plot_draw`): `draw_panel(layout, size, color, axis_color, grid, cache=)` (axes cut
  at breaks with `//`, dashed gridlines opacity 0.4, minor 0.16, labels at `chart_label_size`),
  series lines / markers, `error_bars` (on log a bar to ≤ 0 runs to the edge), `band`, `bars`,
  `plate`, `reference_line`, `span`, `leader`, `flat`, `morph_into`; legends via
  `charts.auto_legend` / `chart_legend` (swatches `dashed`, `band`).

**Compatibility rule**: chart scenes keep `vidgen.charts` and draw as before; a domain plot moves
onto the core only when clearly better and visually equal (§97.12).

### 97.4 The `plot` scene type (Step 222)

**`plot`** (`scenes/plot.py`; mixins `PlotFigure` in `plot_figure.py`, `LivePlot` in
`plot_live.py`; params in `plot_parts.py`, `plot_models.py`): data and models on scientific axes
(`function_plot` stays for functions of x). Params: docs/CONFIG.md#plot.

- **Labels and units from the data**: an axis without `label` / `unit` takes the first series'
  column name / header unit; a column in another unit, or two units on one axis, is an error.
- **Checks** at param validation (inline data) or `vidgen validate` (`validate_project`, CSV or
  model): unique series names, `series` xor `panels`, `x` + `y` or `points`, equal lengths,
  did-you-mean columns, axis problems, no own x on shared stacked panels, `aspect: equal` only
  with one linear panel, gaps only in y. A CSV lives under `assets/` (the fingerprint's folder).
- **Layout**: at most 7 x / 6 y ticks in 16:9 (4 / 7 in 9:16); `aspect: equal` domains are data +
  6 %. Legends per panel (`_legend_panels`, static so `target_names` knows them): `legend`, else
  panels with several series (or one its axis title does not name); in a free corner, else a row
  above. Palette colours by position, lines 4 px, markers 0.1 … 0.035 units by count.
- **Steps**: axes with the first step; `reveal: series` one series per beat (legend entry and
  error bars with it), then fits, then annotations; `reveal: all` one step. Targets an action
  names leave the steps; entrances nest (fit → series → axes; `_batch` builds each once per step).
  Targets: `title`, `axes`, `panel<N>`, `legend`, `series<N>`, `series:<name>`, `errors:<name>`,
  `fit<N>`, `fit:<name>`, `annotation<N>`, `annotation:<id>`.

### 97.5 Data features (Step 223)

**Fits** (`plotcore.fit`, numpy only). `make_model(kind, degree, background, expr, params,
guesses, units)` → `Model` (labels, formula, f(x, p), design matrix when linear in p, a guess from
the data, parameter units from the axes via `unit_ratio`). `MODEL_KINDS`: `linear`, `poly` (n ≤
6), `exponential` A·exp(k·x), `power` A·xᵏ (x > 0), `logistic`, `gaussian` / `breit_wigner`
(`PEAK_KINDS`, `background: n`), `custom` (`mathexpr.parse_model`: parameters may shadow
constants, unused ones refused). `MODEL_ALIASES`: `cauchy`/`lorentzian`, `polynomial`, `exp`,
`gauss`, `sigmoid`. `fit_curve(x, y, model, y_err, x_err, poisson=)`: weighted `lstsq` when
linear in p, else Levenberg–Marquardt (Marquardt scaling, central differences, λ ×4 / ÷3).
Covariance (JᵀWJ)⁻¹: absolute with y errors, × SSR/(n − p) without (`curve_fit`'s
`absolute_sigma`); x errors by effective variance σ_y² + (f′σ_x)², four re-weightings. **Counts**
(`y_err: sqrt`, histogram curve fits) use Poisson maximum likelihood: least squares re-weighted by
the fitted curve until it settles (Fisher errors, Pearson χ², 0 counts allowed) — √N weights from
observed counts bias decays low. `FitResult`: params, errors, cov, χ², χ²/ν, R² (unweighted),
RMSE, residuals, `band(xs, level, kind)` (delta method; Student's t with n − p, normal with known
errors), `parameter_lines`. Errors: n ≤ p, power with x ≤ 0, y errors ≤ 0, rank-deficient JᵀJ, a
model undefined at the start. `plotcore.stats`: normal CDF / quantile, Student's t, χ² survival,
≤ 1e-9 from scipy.

**No scipy**: the core must import without it (schu-video-generator does not list it); tests
compare with scipy when importable (`tests/test_science_review.py`).

**Histograms** (`plotcore.hist`): `rule_width` = numpy's `histogram_bin_edges` (`BIN_RULES`
sturges, fd, scott, sqrt, `auto` = min(sturges, fd)); `bin_edges(values, bins, width, lo, hi,
nice)`: `nice` (default) rounds the width to 1/2/2.5/5 × 10ᵏ with edges on its multiples;
`integers` (k ± ½), a count, explicit edges; ≤ 400 bins; outer edges always cover the data
(`_cover`). `histogram()`: last bin closed, √N errors. `fit_distribution` (`DISTRIBUTIONS`
normal with 1/N, exponential, poisson): maximum likelihood on the raw values, heights
N·width·pdf, dof bins − 1 − p.

**Numbers**: `value_with_error(v, e, unit)` rounds the error by the PDG rule (leading digits
100–354: two digits; 355–949: one; 950–999: up to 1000, two), the value to the same place,
power of ten outside brackets beyond [10⁻³, 10⁵): `(2.510 ± 0.031) × 10⁻⁴ s`.

**Annotations** (`plotcore.annotate`, deterministic): cost 1000 per unit area outside the plot, 10
per covered data point (markers, line samples every 0.1, bars, error-bar ends), 1000 + 5000 ×
area per touched text box; cheapest wins, ties to the first. `place_near` (8 directions × 3
rings, leader off the first), `place_in_plot`, `place_on_hline` / `vline`, `place_in_span`.

### 97.6 The `plot` scene's data features (Step 223)

Series errors (`y_err`, `x_err`, meaning `error`: `sd`, `sem`, `ci95`, `range`, `poisson`,
`other`), histogram series, `fits` (series refs are `TextRef`s), `annotations`. Fits are computed
at validation / `vidgen validate`, so a failing fit names itself (`fits[1] (power fit): …`).
Layout: each data panel followed by its fits' residual panels (weight 0.4, shared x; normalized
ones symmetric about 0, ticked ±2, points without bars, counts with σ = √fit). Error-bar ends and
fit curves count as axis data. Placement loop: legends, fit boxes and notes in free spots, else a
**side group** (right column in 16:9, above in 9:16), layout redone (≤ fits + notes + 3 rounds);
annotations last. `label_size` default `body` landscape, `caption` portrait, never below
`min_font`. Actions `fit`, `annotate` (`scenes/plot_actions.py`, plot scenes only) play the
target's entrance (1.6 s, 1 s).

### 97.7 Models and live plots in the core (Step 224)

**Integrators** (`plotcore.integrate`, deterministic). `rk4(f, t0, y0, t1, step, samples)`: last
step ends on `t1`, outputs thinned to ~`samples`, > 2·10⁶ steps refused. `rk45(f, t0, y0, t1,
times, rtol, atol, first_step, max_step)`: Dormand–Prince 5(4), scipy's tableau and RMS norm
(error < `atol + rtol·|y|`), outputs from the fourth-order dense output, growth ×0.2…×5, safety
0.9; stiffness by Hairer's test (h·|k₇ − k₆|/|y₇ − y₆| > 2.5 on 30 accepted steps, six calm steps
reset) raised only when the rest needs > 20 000 steps; > 10⁵ steps refused. `verlet(accel, t0, x0,
v0, t1, step, samples)`: kick–drift–kick, symplectic, bounded O(h²) energy error. All raise
`IntegrationError` (`VidgenError`, `kind` `blow_up` / `stiff` / `steps`) when the state is not
finite or exceeds 10¹² × max(1, |y₀|).

**Models** (`plotcore.models`) → `Simulation` (first column the progress `t` / `n`, units,
`drift` of `conserved` quantities = max |q − q₀| / max(|q₀|, max |q|)). `simulate_ode`: keys `x`,
`dx/dt`, `x'`; right sides by `mathexpr.parse_system`; default step span/1000, ≤ span/4; rk45
`atol` = rtol × 10⁻³ × largest initial |value|; `leapfrog` needs `x' = v` pairs or accelerations
not reading velocities; errors name the model and what to try. `simulate_recurrence` (`x_next`,
`x[n+1]`). `random_walk`, `poisson_process` (≤ 50 000 events) draw from `SplitMix64` (seed 0 →
`0xE220A8397B1DCDAF`), not numpy streams, so results are stable across numpy versions.
`vidgen.api.register_model(name)` / `run_registered`: `fn(params, seed) -> {column: values}`,
checked (equal-length numeric columns, non-decreasing first; exceptions become a `VidgenError`).

**Live logic** (`plotcore.live`): pure functions of the progress, so a frame never depends on
earlier frames (`grown`, `segment`, `value_at`, `time_like`). `rescale_schedule(times, values,
final, fixed_lo, fixed_hi)` → first domain + `Stop`s in transform space: first domain covers 12 %
of progress with 30 % headroom; growths with that headroom when data would leave it (clipped to
`final`, ends within 15 % snap to it, fixed ends stay), each easing over 7 % of progress and
**ending when the data arrive** (data never leave the plot). `domain_at`, `blend`, `axis_for`,
`figure.relabel` (same plot rectangle while rescaling). `readout_text`: 3 significant digits,
plain from 10⁻³ to 10⁵.

### 97.8 Live and animated `plot` scenes (Step 224)

`models: {name: PlotModel}` (`kind` `ode`, `recurrence`, `random_walk`, `poisson`, `function`;
unknown keys name the kind; `method` aliases `verlet`/`symplectic` → `leapfrog`, `adaptive` →
`rk45`), cached by the model's JSON; a model's columns are a `Table` (`model:<name>`). Series
`model`, `live`, `head`, `readout`, `trail`; `rescale` (default `true`); `Params.conservation()`
for lint. Keys: docs/CONFIG.md#live-plots-models-and-grow.

**Drawing while playing** (`LivePlot`): everything that changes is a **flat** group re-shaped in
place each frame (`plot_draw.morph_into`). Animations and the growth updater act on an empty
**clock** mobject (z −1000), not on a group of parts: adding a group with members of another
top-level group makes manim dissolve the latter, losing its updater.

**Timing**: consecutive free live series of one model form one step: axes and legend (≤ 0.8 s),
then growth over `GROW_SHARE` = 92 % of the slot, linear in model time. Action `grow` (targets
live series, `axes`, `panel<N>`; `to`) lasts until the beat's next action
(`ActionRunner.time_left(next_action=True)`, `NarratedScene.beat_time_left`) or the beat's end.
Fits and annotations on live data wait for the growth; `settle()` finishes it at scene end.
**Rescaling** only for a panel whose series share one progress, `rescale: true`, not `aspect:
equal`, per unshared, unbroken, not doubly fixed, not time-like axis; the static layout is the
final domain (boxes placed once). **Filling histograms**: bins of all values, each frame bins the
first ⌊u⌋. **Readouts**: sized to their widest text over the growth, placed like notes.
**Zoom**: the `zoom` action's `x` / `y` (data units, not with `scale`, plot scenes only) eases the
panels' domains (camera still), annotations fade out until undone; broken axes refused.

### 97.9 Quantities with units (Step 225)

**Own engine, not pint**: calculations need exact fractions through a chain, school
significant-figure rules, TeX of every step and dimension errors in the author's words.
`vidgen/quantities/` is stdlib only (`fractions`, `decimal`), imports only `vidgen.errors` /
`vidgen.mathexpr`, deterministic. Exported as `vidgen.api.quantities`.

- **Units** (`units`): a dimension is seven `Fraction` exponents (m, kg, s, A, K, mol, cd). A
  `UnitDef` has an SI factor (a `Fraction` when exact: km, h, eV, au, ly, atm, bar, mmHg, cal =
  4.184 J, Da; a float with π: deg, pc), a dimension, an offset (°C, °F only), prefixability.
  `parse_unit` (cached): symbols before prefix readings (`Pa`, `min`, `mol`; `ft` refused),
  products, `/`, powers (`^2`, `²`, `⁻¹`, `^(1/2)`), brackets, leading `1`; offset units alone
  (`°C/s` refused, "write K/s"). `si_unit(dim)`: a named derived unit on exact match (N, J, W, Pa,
  C, V, Ω, F, T, Wb, H; J·s; s⁻¹ left alone), else base units, kg first.
- **Constants** (`constants`): SI 2019 exact (c, h, e, k_B, N_A; R = N_A·k_B), CODATA 2022 (G,
  m_e, m_p, m_u, ε₀, μ₀), g_n, au (IAU 2012), IAU 2015 nominal (GM)☉, (GM)⊕, R⊕; M☉, M⊕ = GM /
  CODATA G. Each with TeX, meaning, source, aliases, did-you-mean.
- **Quantity** (`quantity`): `Quantity(value, dim, sig, temperature)`; value a `Fraction` while
  exact, else float; `sig` None = exact. A written fraction or unit-less whole number is exact;
  others get `count_sig` figures (`1500` → 2). °C → K keeps resolution (25.0 °C → 298.2 K). `add`:
  dims must agree, result keeps the coarser resolution (cancellation loses figures); `mul`/`div`:
  fewest figures; `power`: a dimensioned base needs an exact rational exponent, exact roots stay
  exact. **Temperatures**: `"point"` (written in °C/°F) or `"difference"`; adding two readings is
  refused, a difference cannot be shown in °C/°F, T + ΔT is a reading, K values are plain.
  `decimal_text`: half away from zero, plain in [10⁻³, 10⁵) when no digit left of the point is
  uncertain, else scientific.
- **Expressions** (`expr`): `mathexpr`'s grammar as a tree (`Node`) plus `9.81 [m/s^2]`; formula
  numbers are exact. `evaluate`; `to_tex(node, leaf, replace, values, stack)` with `stack` 0 / 1 /
  2 (2: one factor of the outer product per line, a bare number kept with the next factor).
- **Worked calculations** (`calc`): `work(symbols, calcs, wrap, lenient)` over `SymbolInput`s and
  `CalcInput`s in order; each result names a value for later ones (use before computation, unknown
  constants: errors saying the fix). `CalcResult`: value, `Step`s (formula | substitute |
  intermediate | result | convert; substitution variants §97.10; `Step.values` of an
  intermediate line), conversions, warnings (`sig` beyond the inputs). `name_tex` (`M_sun` →
  `M_{\odot}`, `t_half` → `t_{1/2}`). Formats `auto` (a nice fraction then its decimal, exact if it
  terminates within six figures; exact irrational: 4 figures after ≈; measured: its figures),
  `decimal`, `sci`, `fraction` (exact only), `percent`. Intermediates carry one guard figure; later
  calculations use full values. No ± propagation.

### 97.10 The `calculation` scene (Step 225)

**`calculation`** (`scenes/calculation.py`) shows worked numbers (`equation` and
`equation_derivation` stay for formulas and algebra). Params: docs/CONFIG.md#calculation. The
validator runs `work(lenient)`, so every param error surfaces in `validate_params` / `vidgen
validate`; `from_scene` (`scene_id` or `scene_id.result`, also an orbit scene's `calc_values`,
§98.5) is resolved by `validate_project` and at render (`resolve_imports`, recursive, loops
refused).

**Layout.** Table beside the work in 16:9 (0.6 / 0.4), above in 9:16 (≤ half the body); rows
`symbol = value unit` over `meaning · source`. One calculation at a time, lines aligned at the
relation (group `vgrel`). `_fit`: a too-tall block shrinks its largest lines first to a common cap
(bisection), no line more than `SPREAD` = 1.6 × the smallest, then a uniform shrink if too wide.
Substitution variants in order: full units (one line, two lines, one factor per line), **common
unit** (`Step.common` / `common_stacked`: when every value with a unit has the result's dimension,
each is written in the result's unit with the unit once at the end, `(√(2.945² + 10.93²) − 7.726)
km/s`; `common_bare` when the unit cancels ranks with SI), SI numbers (one / two lines). `_choose`
judges final sizes: the most explicit units variant at least `NEARLY` 0.8 × the largest wins when ≥
`KEEP_UNITS` = 1.2 × the readable size, else the first ≥ 0.8 × the largest or ≥ `LARGE` = 2 ×
readable. `units: always` / `never` restrict the variants. Lines still below the readable size
warn. Symbol colours: `color`, else a `terms:` colour with the same TeX, on every occurrence.

**Steps.** Calculations spread over beats (or beats over a calculation's lines); lines an action
names, and those after, wait for the action. A new calculation sends the previous away in
`LEAVE_SHARE` = 0.5 of a step (result row into the table). Targets: `title`, `table`,
`symbol:<name>`, `row:<name>`, `calc<N>` / `calc:<name>`, `formula<N>`, `substitution<N>`,
`result<N>` / `result:<name>`, `conversion<N>`. Actions `substitute`, `compute`, `convert`
(`scenes/calculation_actions.py`, calculation scenes only; `convert` needs `convert:`).

### 97.11 Lint for calculations and plots (Step 226)

Ten scene-scope rules (last in `LINT_RULES`; models `CalcNumbersRule` … `PlotFitClaimsRule`):
`calc_numbers`, `calc_units` (`tolerance` 0.05), `calc_sigfigs` (info), `plot_units`, `plot_log`,
`plot_errors`, `plot_series`, `plot_truncated` (info), `plot_conserved` (`tolerance` 0.01),
`plot_fit_claims` (`sigmas` 2, `tolerance` 0.05). They read the config, not stills:
`lint/calc_rule.py` and `lint/plot_rule.py` append to `SceneContext.science`.

**Number reader** (`vidgen/quantities/accuracy.py`, not re-exported): `said_values(sentence)`
reads digits, number words (strict grammar), spoken decimals and powers of ten, ordinal fractions,
shares, each with a resolution (half the last place; trailing zeros allow up to a tenth: "thirty"
covers 29.8, "two hundred" not 150), figures, "about", bounds, ranges and units (spoken
`UNIT_WORDS` or `parse_unit` symbols). `agrees(said, actual_si, tolerance, sigma)`; `mixup_power`
(a 10^(3k) slip); `fit_quantities` / `fit_claims` (derived fit values such as half-life ln2/|k|,
within `sigmas` errors); `error_meaning_claims`.

**Matching** (`calc_rule`): candidates are calculation scenes' symbols and results
(`Params.worked(project)`) with their `meaning`, plus unnamed intermediate values (never blamed).
A number with a unit agrees with any same-dimension value of its scene, else is checked against the
named / only one (`calc_units` on a power slip, else `calc_numbers`); a pure number only against a
value the sentence names; other scenes' results only from scenes without own numbers, when named.
Texts: beats and on-screen params (`calc_rule.screen_texts`). **Plots** (`plot_rule`, resolved as
at render): physical-quantity titles without units (`QUANTITY_UNITS`), non-positive things on log
axes, errors without meaning, unnamed series with the legend off, truncated bars, conservation
drift (suggesting leapfrog or half the step). `SHOWING_ACTIONS` includes `fit`, `annotate`,
`grow`, `substitute`, `compute`, `convert`. **Narrow by design** (false findings teach authors to
ignore lint): English; negations, questions, comparisons, hypotheticals, bounds are not checked.

### 97.12 Adoption, the substitution layout, the example and the docs (Step 227)

Only the PCR trace (`dna_lab`) is on the core (`layout_axes` with hand-built axes; y ticks the
three stage temperatures, `dna_lab._all_y_labels`); `population` / `gwas` stay on
`charts.chart_axes`, the other lab pictures on their own drawing. Substitution layout: §97.10.
Example `examples/radioactive-decay` (data from `make_data.py`, `random.Random(227)`, stable
across Python versions, labelled "simulated"). Guide topic `science` (aliases plots, plot,
calculations, calculation, units, fits, physics, data), gallery section "Science charts"; the
CONFIG completeness test covers `plot` and `calculation`.

### 97.13 Review of Phase W (Step 228)

Fixes folded into §97.3–§97.10; accuracy tests in `tests/test_science_review.py`. Kept by decision:
rescaling only on one shared progress; no zoom on broken axes; a 9:16 fit box reserves its room from
the start (static layout); crowded 16:9 fit figures need `label_size: caption`; `bar_chart` /
`line_chart` labels are not compared with narration. `quantities.accuracy` imports the sentence
helpers of `cellworld.accuracy` / `genetics.accuracy`.

## 98. Orbital mechanics (Phase X, Steps 229–236)

Real two-body and n-body physics, computed exactly and honest about scale, on Phase W: axes and
equal aspect from `plotcore` (§97.3), integrators `verlet` / `rk45` (§97.7), units and constants
from `quantities` (§97.9), Δv budgets as `calculation` scenes (§97.10), lint on the `calc_*`
machinery (§97.11). User guide: `docs/COOKBOOK-ORBITS.md`; keys: docs/CONFIG.md#orbit.

### 98.1 The phase (plan)

Done: §98.2–§98.9, with the review folded in (§98.10).

### 98.2 The model: `vidgen.orbits` (Step 229)

No manim (a test imports it in a fresh interpreter); exported as `vidgen.api.orbits`, public names
`orbits.__all__`. **SI throughout**: m, s, rad, μ = GM in m³ s⁻².

- `kepler`: Kepler's equation for every conic, element-wise on arrays: elliptic (Newton from
  Danby's E₀ = M + 0.85 e sign(sin M)), hyperbolic (Newton), parabolic Barker `M = D + D³/3` in
  closed form; `E − e sin E` and `e sinh H − H` evaluated as `(E − sin E) + (1 − e) sin E` with a
  small-argument series, so solvers stay at rounding level near e = 1. `kind_of`: parabola within
  `PARABOLIC_TOLERANCE` = 1e-9.
- `elements`: `Elements(mu, p, e, i, raan, argp, nu)` **stored by the semi-latus rectum p**, so one
  representation serves every conic (a parabola has no finite a). `from_a`, `from_periapsis`,
  `from_apsides`, `from_state(mu, r, v)` (radial refused); rotation R₃(−Ω) R₁(−i) R₃(−ω);
  equatorial → Ω = 0, circular → ω = 0; `conic(samples, r_max)`; free functions `vis_viva`,
  `period`, `semi_major_axis`, `circular_speed`, `escape_speed`, `specific_energy`.
- `bodies`: `BODIES` / `ORBITS` presets (planets from `ephemeris.TABLE1`; Moon 384 400 km, e =
  0.0549, i = 5.145°; `iss`, `geo`, `halley`, Galilean moons, Pluto); sources in the module
  docstring (IAU 2015 nominal GM☉, GM⊕, R☉, R⊕; DE440 GM; IAU WGCCRE radii; JPL Galilean GM).
  `body_preset`, `orbit_preset`, `planet_preset`, `preset_on(key, jd)` with did-you-mean.
- `values`: `value_si(value, kind, where)` (`'1.5 AU'`, `'92 min'`; a bare angle is degrees; mass
  `'2 Msun'` = nominal GM / G) via `quantities`, dimension checked; `length_unit` (AU above 0.05
  AU), `time_unit`, `speedup_text`.
- `system`: `Orbiter(name, body, elements, parent, trajectory)`, `System` (positions summed up the
  parent chain), `Playback` (§98.5), `swept_area`.
- `nbody`: `simulate(system, span, method, step, samples, initial=)` → `NBodyRun`: bodies with gm >
  0 attract, gm 0 are test particles; barycentric, in scaled units; `verlet` (default step 1/1000
  of the shortest 2π√(q³/μ)) or `rk45` (rtol = atol = 1e-10); outputs relative to the central
  body, Hermite-interpolated (`velocity` its derivative); energy (× G) and angular-momentum drift
  (`angular_scale` = Σ|r||v| so a zero total has a meaningful error).

**μ for a body's orbit is G(M + m)** (the Moon's month uses GM⊕ + GM☾; planets GM☉ + GM_planet,
as Table 1 assumes).

### 98.3 The `orbit` scene type (Step 229)

`scenes/orbit.py` (drawing, timing), `scenes/orbit_parts.py` (`OrbitCentral`, `OrbitBody`,
`build_system`, `resolve_model` → `OrbitModel`); mixins for §98.4–§98.7. Params:
docs/CONFIG.md#orbit.

- **Bodies**: a preset, elements (size one way only), or a state `r`, `v`; `around` a body listed
  before. Elements next to a preset override it.
- **Timing**: entrance ≤ 1.2 s; then one updater on a clock mobject reads `renderer.time` (not a
  sum of dt: manim gives a play's first frame dt 0) and maps it through `Playback` onto 0 …
  `span` up to the last frame (beat windows in whole frames, as `narrate` waits them). Within a
  stretch equal video times are equal simulated times, so Kepler II shows unforced. `span` or
  `orbits` (refused for open orbits).
- **Picture**: the extent covers every path over the span in the view's frame; open orbits capped
  at 3 × the rest (a lone flyby: 3 × periapsis; `extent` overrides); margin 6 % (13 % with burns).
  `frame: axes` (`layout_figure`, `aspect="equal"`, AU / km), `scale_bar` (1-2-5), `none`. Bodies
  at true size when ≥ 0.12 (central) / 0.075 (orbiter) units, else enlarged and the panel says
  "sizes not to scale". Inclined orbits drawn projected on the reference plane. Trails 8 fading
  pieces. `follow` shows positions relative to a body.
- **n-body** (`dynamics: nbody`): integrated once at validation (cached by params JSON, 32 kept);
  conics are the osculating start orbits; burns refused (burns are Kepler arcs).
- **Validation** (`VidgenError`): wrong unit kinds, unit-less lengths, negative masses, e < 0, two
  sizes, periapsis inside the body ("it would crash"), missing primary, did-you-mean names, radial
  velocities, ν beyond the asymptotes, n-body keys without n-body, duplicate names.
- **Targets**: `title`, `frame`, `central`, `body:<name>`, `orbit:<name>`, `readout`, plus the
  overlays'; `Orbit.target_text` names them for the lint.

### 98.4 Kepler's laws and orbital speed (Step 230)

**Layout.** No axis titles: the length unit is written once (after the x ticks in 16:9, above the
y ticks in 9:16). The round picture takes the full height under the title in 16:9; the caption
sits in the side column under the panel (wrapped to ≥ `COLUMN_CAPTION_WIDTH` 4.4, `CAPTION_GAP`
0.25), else under the picture. The **side panel** (beside in 16:9, above in 9:16) is `Slot` rows
sized once from probed texts (no re-layout while playing); row choice §98.7. **Labels**
(`orbit_overlays.place`): 8 directions × rings 0 / 0.3 / 0.65 / 1.1; cost overlap × 10 (panel,
column caption, dots incl. its own, earlier labels), outside the plot × 20, orbit points × 0.004,
0.12 per unit of ring; the previous candidate kept while within 0.03 of the best (no jumping).

**Model** (`orbits.laws`): `ellipse_geometry` (e < 1), `apsis_names` (perihelion, perigee, perilune,
perijove…), `area_between` (Gauss–Legendre, 48 nodes per ≤ 45°, from the shape), `sector_times` /
`sector_areas` (times from Kepler's equation, areas from the shape: Kepler II checked, not
assumed). `cannon_shots` → `Shot`s, `classify` by ε = v²/2 − μ/r: parabolic within 10⁻⁹ μ/r (e set
to 1), so only `escape` (√2 × circular exactly) is parabolic; suborbital impact at ν = −acos((p/R −
1)/e). `kepler_planets()` is the plot model **`kepler_planets`** (`kind: function`): Kepler III as
a `plot` with a `power` fit.

**Overlays** (`scenes/orbit_overlays.py`, actions in `orbit_actions.py`): `bodies[].geometry`
(foci, axes, apsides; closed orbits), `sectors` (`count` 2–36; closed, not n-body), `velocity`
(one arrow scale per scene: fastest periapsis speed = ⅕ of the plot's shorter side; not n-body),
`cannonball` (needs a radius; not n-body). An overlay named by `reveal`, `sweep` or `launch` starts
hidden; overlays of a moving parent's satellite are `Pinned`. Actions `sweep`, `launch`
(`animates = False`): the runner `cue`s them with their due frame time, mapped through `Playback`
at draw time.

### 98.5 Manoeuvres and gravity assists (Step 231)

**Approximations, stated**: Kepler arcs, impulsive burns, transfers between circular coplanar
orbits (an eccentric or inclined target is refused, suggesting `e: 0`, `i: 0`), patched-conic
flybys shown in the planet's frame with a Sun-frame vector diagram.

- `orbits.manoeuvres`: `local_frame(r, v)` (prograde along v, normal along r × v, radial outwards),
  `BurnPlan(at, components, label)` (`at` seconds or the next `periapsis` / `apoapsis`), `fly` (each
  burn adds Δv; next arc `Elements.from_state`; refuses burns out of order, an apsis of a circle, an
  arc reaching the surface inbound). `hohmann` (time π√(a³/μ), phase π − n₂t wrapped to (−π, π]
  with n₂ from the target's own μ, synodic 2π/|n₁ − n₂|), `window_wait`, `bielliptic`,
  `bielliptic_thresholds()` (11.938765, 15.58172), `plane_change` = 2v sin(Δi/2),
  `combined_plane_change`, `phasing` (T(1 − θ/2πk); refuses orbits into the planet).
- `orbits.flyby`: `turning_angle` = 2 asin(1/(1 + r_p v∞²/μ)); `flyby` (refuses a periapsis inside
  planet or atmosphere); `gravity_assist(..., side)`: energy change v_planet · Δv∞ is positive
  exactly when the periapsis lies behind (r̂_p · v̂_planet < 0); an arrival where both ways are on
  one side is refused.
- **Scene** (`scenes/orbit_manoeuvres.py`): `bodies[].burns` (positive speeds by direction name;
  minus refused), `bodies[].alongside`, `transfer` (`hohmann` | `bielliptic` | `phasing`; `to` a
  sibling circular within 1e-6 and coplanar within 1e-6 rad, or a radius; `depart: window` default;
  becomes the ship's burns; default span arrival + 20 %), `flyby` (probe added as
  `OrbitModel.extra_bodies`, `Params.body_specs()`). Δv arrows on one scale (largest = 0.16 of the
  shorter side, ≥ 0.12 units).
- **Clock**: `Playback(start, seconds, span, knots)` / `Playback.timed(..., events, holds)`: fixed
  points at events (a burn on its word, flyby periapsis), one speed-up between them, holds (`pause`
  … `coast`) keep simulated time still; refused: events outside the motion or out of order, a hold
  over an event, holds leaving no time. Video times from `NarratedScene.action_times(name, start)`.
  Actions `burn` (`burn:<n>`), `flyby`, `pause`, `coast`.
- **Δv budgets**: `Orbit.calc_values(params)` → {name: (SI value, unit)} (`dv1`, `dv2`, `dv3`,
  `dv_total`, `t_transfer`, `r1`, `r2`, `v1`, `v2`, `phase_angle`, `synodic_period`, `wait`, `dv`,
  `t_phasing`, `dv_burn<n>`, `dv_spent`, `v_inf`, `r_p`, `e`, `delta`, `v_planet`, `v_before`,
  `v_after`, `gain`), read by `calculation`'s `from_scene` (4 significant figures).

### 98.6 Many bodies (Step 232)

**Approximations, stated**: circular restricted problem with massless small bodies; Galilean moons
on circles at phases giving the Laplace angle 180°; tides a static equilibrium schematic.

- `orbits.threebody` (rotating frame, separation 1, Ω = 1, primaries at −μ and 1 − μ):
  `collinear_gamma` (Szebehely's quintic, `numpy.roots` then Newton), `lagrange_points`, `ROUTH_MU`
  = (1 − √(23/27))/2, `jacobi` C = 2Ω − v², `zero_velocity_segments` (marching squares),
  `integrate` (RK45, rtol 10⁻¹¹: the Coriolis term makes leapfrog non-symplectic here),
  `coorbital_kind`; `Restricted` presets `RESTRICTED` (`earth_moon`, `sun_earth`, `sun_jupiter`).
  Exported with `integrate` as `integrate_restricted`, `potential` as `restricted_potential`.
- `orbits.manybody`: `figure_eight` (Simó's values, T = 6.32591398 √(L³/GM)), `barycentre`,
  `laplace_angle`, `conjunctions` (bisection on zeros, not ±π jumps), `tidal_acceleration`,
  `equilibrium_tide` ((M_s/M_p) R⁴/d³); `GALILEAN_PERIODS`, `GALILEAN_PHASES`.
- **Scene** (`scenes/orbit_systems.py`, `scenes/orbit_many.py`, `ManySpec`): `system` makes the
  pair the central body and a first body at ν = 0 (+x of the rotating frame), run n-body, RK45 by
  default (96 samples per turn, ≤ 40 000); `figure_eight` uses leapfrog at T/4000. **View**: with
  `origin: barycentre`, positions turned by `turn` × θ(t) (θ the pair's unwrapped angle from the run
  itself, so the secondary sits exactly on +x); `turn` 0 inertial … 1 rotating, eased by actions
  `corotate` / `inertial` (default 2 s). Trails 64 samples per turn (≤ 2 400). Kepler conics not
  drawn about the barycentre, except a binary's two ellipses. `tides` has its own layout (no axes).
- **Performance**: panel rows reuse cached text in place; trails wholly inside skip clipping.

### 98.7 The Solar System on a date, and the compact panel (Step 233)

**Compact panel.** Each `Slot` has a `name` and `rank` (0 always, 1 and 2 while room, `DIAGNOSTIC`
9 only on request). `choose_rows(slots, mode, budget)`: `compact` (default) up to `PANEL_BUDGET` =
6 rows (16:9) / 5 (9:16) besides the scale notes; `full`; `none`; or a list of names (`PANEL_ROWS`).
Drift rows are diagnostics (`energy: true` promotes ΔE/E, ΔL/L); a transfer's Δv₁ / Δv₂ are rank 1
in 9:16 (burn labels carry them). `Orbit.diagnostics(params)` (`energy_drift`, `angular_drift`,
`jacobi_drift:<name>`, `closure`) feeds the lint regardless of the panel.

**Ephemeris** (`orbits.ephemeris`): Standish's JPL **Table 1** (a, e, I, L, ϖ, Ω at J2000 and rates
per Julian century, J2000 ecliptic, valid 1800–2050) for Mercury … Neptune (Earth = Earth–Moon
barycentre) and Pluto. `TABLE1` is the one copy (all 108 numbers pinned in
`tests/test_orbit_sky.py`). `julian_date` (Gregorian, as TT), `check_valid` (1800-01-01 ≤ JD <
2051-01-01, start and end), `heliocentric` (Standish's method; geometric positions, J2000 frame),
`next_event` (root of the wrapped longitude difference, bracketed on 1/24 synodic period, bisected
to 10⁻⁵ d), `events_between` (searches on from a day after each event). Exported renames:
`ecliptic_longitude`, `planet_distance`, `TABLE1_SOURCE`. Periods come from Kepler III on Table 1's
a, consistently.

**Scene** (`scenes/orbit_sky.py`, `OrbitSky`): `date` (Table 1 planets on the day; others need
`nu` / `mean_anomaly`), `event` (default span 1.15 × time to it, ≥ 30 d), `radial: log` (log₁₀(1 +
r/r₀), r₀ = ⅓ smallest perihelion; rings 0.1 … 100 AU; refused with length / speed overlays, n-body,
transfers, flybys, systems, `follow`), `inset` (`true`: 1.08 × the largest aphelion below 2 AU),
`sizes` (radii to one scale by bisection; refused with motion). Targets `event`, `inset`, `rings`.

### 98.8 Orbital accuracy lint (Step 234)

Nine rules (last in `LINT_RULES`, warning; models `OrbitPeriodRule` … `OrbitCrashRule`):
`orbit_period`, `orbit_speed`, `orbit_dv`, `orbit_transfer`, `orbit_distance` (`tolerance` 0.05),
`orbit_date` (`days` 3), `orbit_scale`, `orbit_conserved` (`tolerance` 0.01), `orbit_crash`;
`lint/orbit_rule.py` appends to `SceneContext.science`.

**Knowledge** (`vidgen/orbits/accuracy.py`, not re-exported): numbers via
`quantities.accuracy.said_values` (also "one and a half million", months, weeks, digit groups after
plain / thin / no-break spaces). A `Fact` (value or range, SI) has a kind mapped to a rule by
`KIND_RULES` and the bodies it is about. `orbit_claims`: the **clause** around a number names the
bodies, its words pick the kinds (`topic_groups`; periods need a period word); agreement as
`calc_numbers` (a range accepts any value inside); otherwise reported against the nearest fact only
when bodies and kind are clear; a factor 1000 is "a prefix mixed up?". `ratio_claims`,
`scale_claims` (against `picture_kind`: `sizes`, `schematic`, `log`, `enlarged` when 7 × R / reach
is below the minimum drawn radius, else `true`), `event_claims` (dates vs `events_between`, Earth
observer, 1800–2050). `ATMOSPHERES`: Earth 100 km (Kármán), Mars 125 km (entry interface).

**Facts** (`orbit_rule.facts`, cached per project): radii, surface speeds, per-orbit / per-arc
speeds, distances, periods, transfer and burn values, flyby values, L1–L5 distances, figure-eight
period, event distance; stand-in orbits give none. `orbit_conserved` reads `Orbit.diagnostics`;
`orbit_crash` flags a periapsis below `ATMOSPHERES`, a flyby without `atmosphere` below it, n-body
bodies closer than their radii at a sample. Non-orbit scenes are checked against facts they name.
`SHOWING_ACTIONS` includes `sweep`, `launch`, `burn`, `flyby`; `burn:<n>` text comes from
`orbit_manoeuvres.burn_text` (shared with the drawing). Narrow by design, as §97.11.

### 98.9 Example, docs and gallery (Step 235)

`examples/mars-transfer` ("How to get to Mars", 16:9 and 9:16 `short`; Δv computed via
`from_scene: hohmann.dv1`, never typed in; numbers pinned by `tests/test_mars_transfer.py`). Guide
topic `orbits` (aliases orbit, orbital, orbital-mechanics, kepler, hohmann, planets, space,
spaceflight); the CONFIG completeness test covers every orbit param. Gallery section "Orbital
mechanics" with entry `orbit` and showcases `mars_hohmann`, `jupiter_trojans` (starts rotating, to
stay under `gallery.CLIP_MAX_BYTES` 150 KB); budgets in `tests/test_gallery.py` (`ENTRY_MAX` 0.36
MB). GIFs are not re-optimised: the next `vidgen gallery` would undo it.

### 98.10 Review of Phase X (Step 236)

Fixes folded into §98.4–§98.8 and §97.10; physics checks in `tests/test_orbit_review.py`.
**Render memory**: a manim `Text` per changing readout string exhausted memory, so
`scenes/orbit_text.LiveText` lays out a string once per shape (digits as 0) and draws digits from
glyphs rendered once (plain `VMobject`s, advances and pair kerning); the text cache keeps
`TEMPLATE_CACHE` = 256; still parts (title, caption, axes at `STILL_Z` −2) lie below the clock
mobject (`CLOCK_Z` −1) so manim draws them once per play. Kept by decision: no n-body with burns;
flybys in the planet's frame; a LEO at true scale is a thin ring (close-up via `center` +
`extent`); no Moon positions on a date, no light time or aberration.
## 99. Particle physics (Phase Y, Steps 237–244)

Particle-physics videos: the Standard Model, Feynman diagrams checked at every vertex,
relativistic kinematics, detectors and event displays, resonances in data. It **builds on Phase W /
X** and re-implements none of it: histograms, fits, live plots and the plot core are §97.3–§97.7;
worked numbers are `calculation` and `vidgen.quantities` (§97.9–§97.10); the lint extends `calc_*`
/ `plot_*` (§97.11, §98.8); `from_scene` (§98.5) reads a scene's values. Additive, opt-in, no new
dependency or config key. Author docs: docs/COOKBOOK-PARTICLES.md; params: docs/CONFIG.md (one
section per scene type); guide topic `particle-physics` (aliases particle, particle_physics, hep,
higgs, standard-model, collider, feynman-diagrams; never `particles`, the cartoon effect).

**Physics honesty** (invariant): values from PDG 2024 (Phys. Rev. D 110, 030001), stated in the
module and on screen; schemes and approximations stated; derived numbers (Q, thresholds, Γ = ħ/τ,
p*, decay lengths, significances) computed, never hard-coded; example data simulated and labelled
so; detectors and diagrams schematic and labelled so; no real experiment's logo or geometry.

### 99.1 The phase (plan)

Built as described below. Names: package `vidgen.particle_physics` (`vidgen.particles` is the
cartoon effect); scene types `standard_model`, `feynman`, `kinematics`, `detector`,
`mass_spectrum`, `decay_chain`, `branching`, `branching_pie`; actions `antiparticles`, `couplings`,
`travel`, `vertex_rule`, `swap_channel`, `boost`, `switch_view`.

### 99.2 The model: `vidgen.particle_physics` (Step 237)

No manim anywhere in the package (a fresh-interpreter test); `vidgen.api.particle_physics` is the
module. MeV with c = 1, seconds.

- `data`: `Particle` (frozen; `key` ASCII such as `e-`, `anti-nu_e`, `K0_S`, `J/psi`; `symbol`,
  `markup`, `tex`, `family`, `mass_mev`, `mass_limit_mev` for neutrinos, `charge`, `spin`, `baryon`
  (Fractions), `lepton` (L_e, L_μ, L_τ), `flavour_numbers` (S, C, B′, T, PDG signs), parities,
  `colour`, `lifetime_s` or `width_mev` (the other computed with ħ from exact SI h, e), `stable`,
  `mass_scheme`, `content` / `components` (mixtures π⁰, η, K⁰_S, K⁰_L have `None` for undefined
  numbers), text helpers). `PARTICLES`: 30 Standard Model + 47 hadron keys. Hadrons take B and
  flavour from their quarks; their given charge is checked (`particle_problems`); antiparticles by
  conjugation (`_anti`). Only the H width (SM prediction 4.1 MeV) is marked `# check`.
- `names`: `particle(text)` accepts keys, aliases, printed Unicode and ASCII anti markers;
  **a bar keeps the antiparticle's own charge, as PDG writes it** (`Σ̄⁻` = anti-Σ⁺); unknown →
  `VidgenError` with did-you-mean.
- `process`: `parse_process("n -> p e- anti-nu_e")` → `Process(initial, final)` of `Leg(particle,
  off_shell)`; one arrow (`->`, `→`, `=>`, `⟶`); `Z*` / `W*` off-shell (`K*` refused);
  `Process.text("unicode" | "ascii" | "tex")`.
- `conservation`: `check` (§99.3), `CONSERVATION_TABLE`, `INTERACTIONS`.
- `chart`: `Cell`, `CELLS` (17), `GRID` (wide 5 × 4, tall 3 × 6), `COUPLINGS` (tree level, by
  boson; the source of every "which boson meets which particle" rule), `SHORT_LABELS`.

### 99.3 The conservation checker (Step 237)

`check(process)` → `Verdict(process, allowed, interaction, checks, violations, notes, threshold,
energy, energy_ok)` with `summary()` and `explain()` (every `Check` ✓ / ✗ / Δ, per-particle shares).

1. **Always**: Q, B, L_e / L_μ / L_τ (when that family takes part); fermion number changes by an
   even number; energy (a decay needs the parent heavier than its on-shell products, hint "write
   Z*"); a reaction gets `Threshold` (least √s; fixed-target E = (M² − m_a² − m_b²) / 2m_b);
   Landau–Yang (spin 1 never → γγ); **2 → 1 with nothing off-shell needs M ≥ m_a + m_b**
   (`_merge_problem`: e⁺e⁻ → γ refused, hint `gamma*`).
2. **Flavour** S, C, B′, T per side; a mixture is read as the component changing flavour least.
3. **Interaction**: Higgs → `higgs` (flavour kept); W, Z, neutrino or flavour change → `weak`
   (each flavour by ≤ 1 unit); photons or charged leptons → `electromagnetic`; else `strong`.
   Strong and EM conserve C-parity, strong G-parity (when every particle has one).
4. Quark-level processes: energy check indicative (note); colour is `feynman`'s (§99.5).

Not checked: parity / orbital L, CKM suppression, FCNC loops, isospin beyond G.

### 99.4 The `standard_model` scene type (Step 237)

`scenes/standard_model.py`, `scenes/standard_model_actions.py`; params docs/CONFIG.md#standard_model.
`layout: auto` = `wide` in 16:9, `tall` in 9:16. Cells in group colours (the theme's `highlight`
stays free for actions); row mode when every mass and charge fit on one line, else column mode, else
row mode scaled with a warning; names shorten for all cells alike. Antiparticle bars are drawn
lines and **every symbol carries a bar (invisible when none)** so the flip morphs like to like (a
`Transform` between different structures leaves a stray copy). Reveal `groups` (default) | `all`.
Targets `title`, `chart`, `header`, `labels`, `key`, `source`, `caption`, `particle:<name>`,
`generation:1`–`3`, `group:quarks | leptons | fermions | gauge_bosons | scalar_bosons | bosons`,
`row:up_type | down_type | charged_leptons | neutrinos`; `target_text` gives on-screen names.
Actions: `antiparticles` (reversible); `couplings` (target a boson cell, checked; reversible,
`until_next_beat`; rows from `chart.COUPLINGS`, the rest dimmed via `dim_to`, restored by
`Repaint`). Both check the scene type. Chart labels are English only. Shared:
`lint/layout_rules._GLYPH_EM` knows Greek lowercase heights.

### 99.5 Feynman diagrams: the model (Step 238)

`feynman` and `feynman_layout`; exported `Diagram`, `DiagramCheck`, `build_diagram`,
`check_diagram`, `preset_diagrams`, `vertex_rule`, `diagram_layout`.

`Diagram(name, lines, groups, label)` of `DiagramLine(id, particle, start, end, off_shell,
label)`: the particle runs **forward in time** from `start` to `end` (a vertex id, `in` or `out`;
`in` → `out` is a spectator quark); the arrow follows fermion-number flow. `HadronGroup(particle,
side, lines)`. `build_diagram` refuses non-diagrams (vertex of < 3 or > 4 lines, disconnected,
> 1 loop, tadpoles, a hadron line, a non-quark spectator, groups on the wrong side).

`check_diagram(d)` → `DiagramCheck(vertices, chains, verdict, hadron_verdict)` (`problems`, `ok`,
`explain()`): (1) `vertex_rule(into, out)` → `VertexRule(kind, name, coupling, interaction, note)`
or why not — fermion pair + γ / g / Z / H (same flavour; H needs mass) or W (a weak doublet, CKM in
the text); **no tree-level flavour change at γ / g / Z / H; H γ γ, H g g, H Z γ refused with a
pointer to the loop preset**; the Standard Model's 3- and 4-boson vertices; four-fermion contact
refused; (2) §99.3's `check` at each vertex (all lines off-shell); (3) colour can form a singlet
(`colour_problem`); (4) `fermion_chains`; (5) the external reaction and, with groups, the hadron
reaction. The scene refuses any problem. Couplings shown are computed from constants (α, α_s(m_Z),
G_F → v, g, y_f); sin²θ_W and CKM magnitudes are display-rounded.

**Presets** (`PRESETS`, `preset_diagrams(key, spectators)`): `ee_to_mumu`, `compton`, `bhabha`,
`moller`, `beta_decay`, `muon_decay`, `pion_decay`, `drell_yan`, `gg_to_h`, `h_to_gammagamma`,
`h_to_zz_4l`, `top_decay`; **line ids are stable across a preset's diagrams** (`swap_channel`
morphs by id).

**`feynman_layout.layout(d)`** → `DiagramLayout(...)` in (t, y), t 0 → 1: timelike bridges order
vertices, spacelike ones share a column; vertex y solved exactly as neighbour means; every order of
the ends (≤ 4 per side) scored by crossings, lines through dots, groups apart, inversions of the
written order. Deterministic; every preset 0 crossings. One loop at most.

### 99.6 The `feynman` scene type (Step 238)

`scenes/feynman.py`, `scenes/feynman_draw.py` (notation), `scenes/feynman_actions.py`; params
docs/CONFIG.md#feynman. Validation builds and checks every diagram (a broken rule is a param error
with the reason). Notation: fermions with arrowheads; γ / W / Z sine waves; g a coil whose path runs
backwards in every turn (`COIL_RADIUS`, `COIL_PITCH`); H dashed; lines drawn from their earlier end.
Fit limits `MAX_UNIT`, `MAX_STRETCH`; `vertex_rule` cards at `NOTE_SCALE` in a right column (16:9)
or bottom band (9:16); `_areas = {False: whole frame, True: beside the cards}` and `_dock(docked)`
re-lay the diagram out, so it is full size before the first card and after the last. The card's
reaction uses no-break spaces. Reveal `time` (per column) | `all`. Targets `title`, `caption`,
`process`, `diagram`, `time_axis`, `line:<id>`, `vertex:<id>`, `hadron:<particle>` (containers, so
they follow `swap_channel`). Actions `travel` (dots along lines on one clock), `vertex_rule` (one
vertex, `until_next_beat`), `swap_channel` (`to`, default next diagram; reversible). Shared:
`vidgen.api.find_scene_type` (= `registry.find`; built-ins import through `vidgen.api`).

### 99.7 Relativistic kinematics: the model (Step 239)

`particle_physics.kinematics`. MeV, c = 1 (`value_text`), SI via `vidgen.quantities`
(`to_si`, `from_si`, `si_text`), `natural_value("10 GeV/c")`.

- `FourVector(energy, px, py, pz)` (`from_mass`, `p`, `mass2`, `mass`, `gamma`, `dot`,
  `boost(beta)`, `total`, `invariant_mass`, `rest_frame_beta`, `to_rest_frame`); `gamma_of`,
  `Boost` (`from_beta`, `from_gamma`, `from_momentum`, `from_energy`, `from_kinetic`),
  `motion(m, …)` (exactly one of momentum / energy / kinetic / beta / gamma). **Refused with
  `VidgenError`**: negative m², β ≥ 1, γ < 1, E < m (hint "kinetic energy?"), a massless rest frame.
- `kallen`, `two_body_momentum`, `two_body("pi+ -> mu+ nu_mu")` → `TwoBodyDecay` (must pass
  `check`; below threshold refused) with `p_star`, `energies`, `q_value`, rest / lab vectors,
  `opening_angle`, `min_opening_angle`.
- `MomentumPicture` (`decay_picture`, `system_picture`; planar, two-body only).
- `threshold(reaction)` → `Thresholds` (`sqrt_s`, `fixed_target`, `collider`, `ratio`);
  `fixed_target_energy`.
- `decay_length(name, energy=…)` → `DecayLength` (`c_tau`, `lab_lifetime`, `length`, `survival`);
  stable refused. `length_text`.
- `pdg_value(name, "mass" | "lifetime" | "width", unit)` → `PdgValue(number, unit, meaning,
  source)` (the table's figures as a decimal string); neutrino mass, stable lifetime refused.
- Plot model `two_body_opening` (columns `p`, `gamma`, `theta_min`, `theta_90`).

### 99.8 The `kinematics` scene type and PDG symbols in calculations (Step 239)

A scene type, not a `plot` model (arrows from one origin and moving frames are not data on axes).
`scenes/kinematics.py`, `scenes/kinematics_actions.py`; params docs/CONFIG.md#kinematics; §99.7's
errors become param errors. Panels side by side (16:9) or stacked (9:16); one arrow scale unless
frames differ by more than `SHARED_SCALE_LIMIT` (1.25×), then the header says `arrows ×N`;
`readout: key` (default) | `all`. Targets `title`, `caption`, `process`, `panel:rest`, `panel:lab`,
`arrow:<n>` / `arrow:<particle>`, `sum`, `values`. **`boost`** (`to: lab | rest | β`; reversible)
runs the rapidity linearly and redraws with `orbit_text.LiveText`; containers keep identity and
dropped parts are made invisible (the renderer keeps drawing the family collected at the start).
`calc_values`: decay `M`, `p_star`, `E1`, `E2`, `Q`, `beta`, `gamma`, `beta_gamma`, `p_lab`,
`E_lab`, `opening_angle` (rad), `decay_length`; particles `m_inv`, `E_total`, `p_total`,
`opening_angle`.

**`calculation` PDG symbols**: `{name, mass: pi+}`, `lifetime:`, `width:` — a fourth source beside
`value`, `constant`, `from_scene` (exactly one), written into `quantities` as `pdg_value`'s string
and unit so it behaves as a measured value (`CalcSymbol.pdg()`, `source_input()`). Shared: a thin
space after a root in products; `register_model(name, labels=, units=)` (`Column.label`,
`Simulation.labels`; the plot's `units` / axis `label` override).

### 99.9 Detectors and events: the model (Step 240)

`particle_physics/detector.py`: metres, GeV, B along +z. Generic schematic geometry (`Layer`,
`Detector(field, return_field)`, field ≤ 0 refused, `bz(r, z)`). `signature(p)` / `SIGNATURES`
(track, ecal, hcal, muon, missing); particles that never reach the detector (cτ < 1 m, Z / W / H /
t, π⁰, quarks, gluons) are errors with the reason; `signature_problem(p, parts)` checks claims
(§99.13). `trajectory` steps the helix (p_T = 0.2998 q B R; clockwise for qB > 0), stopping at
absorption, a full turn, or the envelope. `CALO_SHARE`, `towers`, `tower_fraction`.
`generate(preset, seed, soft)` (`SplitMix64`, seed × 1000003 + preset index; presets `z_to_mumu`,
`h_to_gammagamma`, `h_to_4l`, `w_to_enu`, `dijet`): boson mass a Breit–Wigner truncated to M ±
`DISPLAY_WIDTHS` (1) Γ from one seeded uniform; retried until visible; **every preset event balances
exactly and its missing p_T is the neutrinos'**; `make_jet` sums exactly to the jet's p_T.
`custom_event` (|η| ≤ 3, p_T > 0). `Event.missing_pt()`, `products_mass()`, `transverse_mass()`,
`objects()`. No displaced vertices, material effects, pile-up or smearing.

### 99.10 The `detector` scene type (Step 240)

`scenes/detector.py`, `scenes/detector_actions.py`; params docs/CONFIG.md#detector. Views x–y and
r–z; tracks, hits, towers, jet cones, missing p_T (x–y only); side blocks readout, legend, layer
key, label line ("schematic detector · simulated event · …"). Reveal `layers` (detector; tracks;
towers grown by one `UpdateFromAlphaFunc` on the container; muons; missing p_T and readout) |
`all`. Targets are containers per part holding the current view's mobject, so **`switch_view`
`Transform`s each part and targets follow**; empty parts are put on screen empty. Highlight / dim /
reveal use generic actions. Validation: `field > 0`, the event, `products`, `leaves`, `soft` 0–40.

### 99.11 Collisions, decays and data: the model (Step 241)

**`particle_physics.spectrum`** (simulated, `SplitMix64`: same seed, same events with any numpy):
`SpectrumSpec(...)` with `problems()` (1 ≤ events ≤ 200 000, 0 ≤ signal ≤ events) and `window`;
`CHANNELS` `z_to_mumu`, `h_to_gammagamma`, `h_to_4l`; `channel_spec`; `generate(spec)` →
`Spectrum` (cached per spec; Cauchy ⊗ Gaussian signal, `exponential` | `power` | `flat`
background). Significance, all local: `asimov`, `counting_significance`, `p_value`
(`FIVE_SIGMA_P`), `asimov_curve()` / `counting_curve()` (shares from `window_shares`, its signal
share from its own fixed seed), `likelihood_significance(...)` → `Significance` (binned Poisson
fits via Phase W `fit_curve(poisson=1)`, Z = √q₀), `meaning_lines` / `short_meaning` (the p-value
stated correctly). `decay_times`, `mean_lifetime`, `z_cross_section`. Plot models `mass_spectrum`,
`decay_times`, `z_lineshape`. 4ℓ fits fail for about 1 seed in 40; the error suggests another seed,
more events or wider bins.

**`particle_physics.branching`**: `Branching(parent, modes, source, kind)` of `Mode(process,
fraction, name, note, check)`; `branching(name)`, `listed()`, `branching_problems()` (every mode
passes `check`, sum ≤ 1 within `SUM_TOLERANCE` 10⁻³). H: SM prediction (YR4 at m(H) = 125 GeV,
`kind: theory`, said on screen, `check=True` for the owner); Z, W⁺, π⁺, π⁰, K⁺, μ⁻: PDG 2024.
`chain(decays)` → `Chain` (each decay's parent is the first undecayed product with that key; every
decay checked); `ChainNode.lifetime_lines()`; `mode_fraction` skips the Z's `invisible` mode.

### 99.12 Scenes: `mass_spectrum`, `decay_chain`, `branching`, `branching_pie` (Step 241)

Params: docs/CONFIG.md#mass_spectrum, #decay_chain, #branching, #branching_pie.

- **`mass_spectrum` is a `plot` underneath**: `MassSpectrum(Plot)` turns physics keys into plot
  params in a `mode="before"` validator (live histogram, Phase W peak fit, note
  `annotation:significance`); `series`, `fits`, `panels` typed loosely so translation does not
  offer generated text; giving `series`, `models`, `fits`, `data`, `panels`, `arrange`, `share` or
  `aspect` is an error pointing to `plot`. `explain: true | short` (default) | `long`; with a `fit`
  action the note is held for it (`_held`). Text `LABEL_MARGIN`; 16:9 headroom
  `LANDSCAPE_HEADROOM`; 9:16 (`_portrait`) one combined box at `auto`.
- **`plot` additions** (shared): fit keys `residuals: background`, `parameters` (unknown names
  error); targets `residuals<N>` / `residuals:<name>`; `reveal()` plays axes before data-growing
  entrances; `plotcore.fit._covariance` scales J's columns before the rank test;
  `plot_live._readout_label` keeps only `READOUT_CACHE` (64) texts.
- **`decay_chain`** (own scene: a tree is not data on axes): left → right (16:9), top → bottom
  (9:16); one decay per beat. Targets `title`, `caption`, `chain`, `decay<N>`, `particle:<n>`,
  `particle:<particle>`, `lifetime:<particle>`.
- **`branching` / `branching_pie`**: `bar_chart` / `pie` subclasses (two types since a scene type
  is one class; bars default, small modes are slivers in a pie) fed from `branching`; labels are
  product symbols (not translated).
- Gallery budget 16.5 MB (`tests/test_gallery.py`), `ENTRY_MAX` 0.36 MB, GIF cap 150 KB.

### 99.13 Particle-physics accuracy lint (Step 242)

Scene rules last in `LINT_RULES`; the runner adds `particle_issues` (`lint/particle_rule.py`) to
`SceneContext.science`. Rules (default severity): `particle_mass` (warning), `particle_charge`
(error), `particle_spin` (error), `particle_lifetime`, `branching_ratio`, `conservation_claim`,
`feynman_boson`, `kinematics_number`, `detector_signature`, `significance_claim` (`sigmas` 0.5),
`simulated_label` (warnings), `particle_units` (info); what each catches:
docs/COOKBOOK-PARTICLES.md §6.

Knowledge lives in `vidgen.particle_physics.accuracy` (no manim, not re-exported): `mentions`,
one reader per rule returning `Said(rule, quote, message, severity)`, `said_decays`,
`written_processes` (a word is never split into particles); numbers from `quantities.accuracy`. A
value belongs to the particle named just before it in its clause (≤ 70 characters). **Narrow by
design**: negations, contrasts and questions are skipped, except `conservation_claim`, which reads
polarity per clause and flags "allowed" only when no reading is allowed. **Gate**: charge and spin
rules read every project, the rest only projects with a particle-physics scene, particle `plot`
model or PDG calculation symbol; the examples must stay at 0 findings. Scene facts
(`particle_rule.facts`, cached per project) come from each scene type. English only.

### 99.14 Example, docs and gallery (Step 243)

`examples/higgs-discovery` (every Phase Y type, a 9:16 `short` variant, simulated data only; its
mass is two `calculation`s, m² then m, because a root of GeV² falls back to SI). Guide topic and
cookbook as in §99's intro (the cookbook pattern is tested in `test_docs`). Gallery section
"Particle physics" (`gallery.SECTION_NOTES` / `SECTION_FOOTERS`, showcase `higgs_diphoton`).

### 99.15 Review of Phase Y (Step 244)

Hand computations are pinned in `tests/test_phase_y_review.py`; only the Higgs SM predictions stay
marked for the owner. Fixes are folded into §99.3, §99.6, §99.11, §99.12.

## 100. Story-cartoon features (Phase Z, Steps 245–248)

Generic story-cartoon features, additive and opt-in. User docs in docs/CONFIG.md: Voice effects,
Holograms, Portals, Iridescent skins and afterimages, Hologram displays, Alarms and shutters,
Flashbacks, Holding hands, Isometric places. Samples use neutral content.

### 100.1 The phase (plan) and the gap analysis (Step 245)

Built as §100.2–§100.16.

### 100.2 Voice effects (Step 245)

- **Config**: `effect` on `VoiceConfig` / `VoiceEntry`: a preset (`VoiceEffectName` =
  `voice_effects.VOICE_EFFECTS`, kept equal by a test), a list, or `{use, pitch (−12..12), amount
  (0..1)}`. In `voices.SPEAKER_FIELDS`: a named voice does not inherit the base voice's.
- **Model** (`vidgen/voice_effects.py`, no manim, no ffmpeg run): `voice_effect(setting) ->
  VoiceEffect | None` (names in `VOICE_EFFECTS` order; `otherworldly` = deep −3 + chorus + hall;
  `deep` / `high` set pitch ∓4); `spec()` (hashed; includes `level: matched`); `tail` (`TAILS`);
  `effect_filter(effect)`: an ffmpeg chain (48 kHz mono, `apad` for the tail, pitch with length
  kept, robot / radio / chorus / echo / hall, `GAINS`, `alimiter`), only filters in ffmpeg 4.2+.
- **Applied at voicing** (`vidgen/tts/effects.py`): `get_provider` wraps the voice in
  `EffectProvider(inner, effect)`; audio goes through the chain then `level_match` (the dry voice's
  BS.1770 loudness, ±`MATCH_LIMIT` 15 dB). Timings and phonemes are the inner provider's; other
  attributes pass through. `cache_key` = sha1(inner key | "effect" | spec): **a voice without an
  effect keeps every hash**; `audio_fields` includes it. Voicing, not mixing, so the beat's MP3 is
  what is heard (`readback`, visemes, `narration_speed`, tail in the beat length). Per voice, not
  per line. `describe_voice` names the effect.
- **Public**: `VOICE_EFFECTS`, `VoiceEffect`, `effect_filter`, `voice_effect`.

### 100.3 Hologram characters (Step 245)

`CharacterEntry.hologram: bool | HologramConfig {color = "#5FD8FF", opacity 0.2–1 = 0.6, flicker =
true}`. `cartoon/hologram.py`: `build_character` ends with `apply_hologram(figure, color,
opacity)`, recolouring every member (fill by `hologram_fill`, lightness-scaled tint; outlines
whitened; `family=False`) **including hidden shapes** (styles survive without points, §69.22), so
every expression and viseme stays a hologram; the figure's own parts, not an overlay, so it moves
and speaks normally. `figure.hologram`, `is_hologram`. Stage: `unmark_lit` (the grade skips it),
`mark_shaded` skips it. Public: `HOLOGRAM_COLOR`, `apply_hologram`, `is_hologram`, `unmark_lit`.

### 100.4 Portals (Step 245)

Prop `portal` (`SCIFI_PROPS`, a `PROP_KINDS` group; `FLOATING_IN_PLACE`: no shadow, no snow): its
static drawing is an invisible box of the open size (`portal.EXTENT`, so it places the same open or
sealed) and a faint `seam`. Switched like a lamp (`SWITCHED_PROPS`, `LIVING_KINDS`); living overlays
`PORTAL_PARTS` (`living_drawing._portal_overlays`), unlit, with `GLOWS["portal"]`. Maths
(`cartoon/portal.py`, no manim): `openness`, `opening_size`, `changing`, `portal_shape(level, now,
seed)` → `PortalShape`, **seeded by the stage's `motion_seed`** (every render identical); a sealed
portal is not `changing`, so it stays in Manim's static image. `switch_props` plays
`PORTAL_OPEN_SOUNDS` / `PORTAL_SEAL_SOUNDS` (no click; other kinds keep it). In `ISO_ITEMS`; `enter`
/ `exit` with `door:` its spot fade a character in or out there. Public: `SCIFI_PROPS`,
`FLOATING_IN_PLACE`.

### 100.5 Compatibility (Step 245)

Voices without `effect`, characters without `hologram` and other prop kinds are untouched. Layout
for §100.6–§100.13: `scenes/stage_story.py` (`StoryStaging`, a part of `Stage` like `IsoStaging`),
`scenes/story_actions.py`; maths in `cartoon/alarm.py`, `apparition.py`, `holo_display.py`,
`portal.py`, `vignette.py` (no manim except `CameraVignette`); drawing in `cartoon/figure_fx.py`,
`iso_overlays.py`, `living_drawing.py`.

### 100.6 Framing: a fuller wide view, faces together, clear shots (Step 246)

- `iso.wide` (`auto` | `fill` | 1–2.5; `wide_view(..., fit=)`): `auto` is §89.13's; `fill` fills
  the place's bounds (≤ `ISO_WIDE_MAX`) keeping spots, objects and bodies; a number magnifies
  (`_zoomed_view`). Portrait keeps §90.14.
- `closeup` / `medium` take 1–3 names (`ShotConfig._check_names`); `frame_shot` → `_group` frames
  the union of the subjects' `SHOT_SPANS` boxes, top at the highest head. One name is unchanged.
- `shot` `clear`: `Stage.shot_clear(keep)` hides the others via `FigureAlpha` factor `shot`, sets
  `hidden_by_shot` (dump `hidden`, skipped by lint's `_figures`), restored on the way back or the
  next shot.
- An iso character's `scale` is its size.

### 100.7 Alarms and shutters (Step 246)

- `alarm` action (`start` | `stop`, `color` `ALARM_COLOR`, `period` 0.4–6 s default
  `ALARM_PERIOD`; `animates = False`): `alarm_spans(changes)` → `AlarmSpan`s on `StageLight`;
  `alarm_grade(grade, spans, now)` applies after light and lightning (a dim room lit red, pulsing
  from dark). `changing` / `settled` include alarms; unlit things shine over it; a `flat` draft
  keeps the light. The siren is the `alarm` ambience bed (`Stage.alarm_beds`, start to stop or
  scene end).
- `shutters` action (`close` | `open`; `iso.shutters: true` starts closed; indoor iso place with a
  window into the room only): `window_faces(place)`, `IsoShutters` (a story thing, §100.11),
  `shutter_level` (`SHUTTER_CLOSE_SECONDS`); sounds `slam`, `swoosh`.

### 100.8 Story sounds (Step 246)

`BUILTIN_SOUNDS` gain `alarm`, `crackle`, `hum`, `drone`, `slam` (numpy, seeded, loudness-finished).
Beds `hum` (seamless, not ducked, by name only) and `alarm` (seamless via `siren(circular=True)`,
ducked) in `AMBIENCE_BEDS` / `SET_BEDS`. The Listen page has row `sfx-story` (budget 6.8 MB).

### 100.9 Characters: appearing, flickering, shimmering, trailing (Step 246)

- **`FigureAlpha`** (`figure_alpha(figure)`): opacities snapshot on first use, named factors
  (`shot`, `flicker`, `appear`) multiplied by `apply()`; sets `shown`. **The one place for every
  opacity effect.**
- `materialise` / `dematerialise` (`run_time` default `MATERIALISE_SECONDS`): `Materialise` via
  `materialise_levels` (outlines then fills, with a fading flicker). A character whose first such
  action is a materialise starts at `appear` 0 at its spot (`StoryStaging._materialising()`).
- Flicker (`HologramConfig.flicker`, default true): `flicker_level(now, seed)`; skipped during door
  walks.
- `CharacterEntry.iridescent` (true | `{seconds 2–120 = 12, strength 0.1–1 = 0.8, glow 0–1 =
  0.5}`): `Iridescence` recolours each frame by `iridescent_rgb` (ink and eye whites kept).
- `CharacterEntry.afterimages` (true | `{spacing 0.12, life 0.6, opacity 0.35}`): `Afterimages`
  copies the drawn leaves while the feet move and adds each copy to `scene.mobjects` **and** the
  animation's `moving_mobjects` (else Manim does not draw it until the next `play`).
- All run in one updater (`_story_step`, after the animations); drafts skip flicker, iridescence,
  afterimages.

### 100.10 Holding hands and the hologram display (Step 246)

- `hold_hands` (target, `with`; generated characters only): `HandHold(a, b, start)` reaches the
  nearer hands for a point `HAND_DROP` below the shoulders' midpoint every frame (§100.15);
  `let_go_hands` returns `PoseChange`s. `figure.hand_in_hand` (dump key) lets lint's
  `walk_overlap` / `character_overlap` accept the pair.
- `hologram_display` prop (`SCIFI_PROPS`, switched living prop; `pattern` in `DISPLAY_PATTERNS`
  `fractal | data | text`): parts placed by `LivingProp._project` from `display_frame(pattern,
  since, now, seed)`; unlit; on with `hum` + chime. It and a portal cannot be held
  (`_Handling.scene_problems`).

### 100.11 Lab and memory objects on an iso place (Step 246)

`OBJECT_KINDS` include `console`, `server_rack`, `projector_pad` (walkable; `surface_at` stone),
`whiteboard`, `flower_arch`, `chess_table`. `object_lights` / `LIT_OBJECTS`; `IsoBlinkers` blinks
them (seeded, unlit). Story things (`story_things`: shutters, blinkers) join `_living_things`,
built in `_iso_story_overlays` at the end of `_iso_scenery`.

### 100.12 A flashback's look (Step 246)

Stage `flashback: true | {tint, strength, saturation, vignette, color}` (`FlashbackSetting`).
`LightGrade.saturation` (default 1; `blend_grades` keeps it exactly when equal, `flash_grade`
carries it, **so no other light changes a pixel**). `flashback_grade(grade)` (`FLASHBACK_TINT`,
`FLASHBACK_STRENGTH`, `FLASHBACK_SATURATION`) wraps the light at the start and every `light` change
(`Stage.flashback_look`). `CameraVignette` (`VIGNETTE_COLOR`, `VIGNETTE_OPACITY`) is stretched over
the camera frame each frame, above the set and below bubbles, tags and captions.

### 100.13 A view through a portal (Step 246)

Portal `view: coast | stars | meadow` (`PORTAL_VIEWS`): `living_overlays(..., view=)` adds
`VIEW_SHAPES` `portal_view(view, rx, ry, now, seed)` members inside the oval
(`LivingProp._show_view`).

### 100.14 Compatibility (Step 246)

Shared code with neutral defaults: `LightGrade.saturation` 1, empty `alarms`, `wide_view(fit="auto")`,
one-name shots, optional dump keys, lint's `_figures` / `_riding_together`; `character_overlap` does
not report characters wholly out of view. **Public** (`vidgen.api`): `ALARM_COLOR`, `ALARM_PERIOD`,
`SHUTTER_CLOSE_SECONDS`, `AlarmSpan`, `alarm_grade`, `alarm_spans`, `shutter_level`,
`MATERIALISE_SECONDS`, `flicker_level`, `iridescent_rgb`, `materialise_levels`, `Afterimages`,
`FigureAlpha`, `HandHold`, `Iridescence`, `Materialise`, `figure_alpha`, `DISPLAY_PATTERNS`,
`display_frame`, `IsoBlinkers`, `IsoShutters`, `PORTAL_VIEWS`, `portal_view`, `CameraVignette`,
`FLASHBACK_SATURATION`, `FLASHBACK_STRENGTH`, `FLASHBACK_TINT`, `VIGNETTE_COLOR`,
`VIGNETTE_OPACITY`, `flashback_grade`, `LIT_OBJECTS`, `object_lights`, `window_faces`.

### 100.15 Light on the characters, hands that show (Step 247)

- Stage `fill_light` (0–1, default 0 = nothing marked): `lighting.lifted(grade, share)` moves a
  grade towards the drawn colours (0 returns the grade itself); `shading.mark_light_lift` sets
  `LIGHT_LIFT`; `StageLight._grade_of` applies it after a lamp's light (cached in `_lifted`,
  cleared past 256). `StoryStaging._fill_lights` marks non-hologram characters with
  `max(fill_light, iridescent.glow)`; alarm grades are lifted too.
- `HandHold._keep_close`: each partner is drawn at its own place plus an offset that steps them
  together until within reach (`HAND_REACH`), never closer than `HAND_MIN_GAP` (shoulders) /
  `HAND_MIN_APART` (feet); walking together, the second keeps its place beside the first (give
  both walks the same `run_time`). On an iso place offsets apply only while standing (cells and
  draw order stay the walks'). Offsets, not moved spots, because neighbouring cells are farther
  apart than arms reach.
- Public: `lifted`, `mark_light_lift`.

### 100.16 Review of Phase Z (Step 248)

- **A shot inside a zoom's `until`** (`Zoom.revert`): the shot wins for its beat, then the way back
  (§69.29) returns to the zoomed view; if the zoom ends while a later shot holds the camera, the
  camera stays and the shot's way back becomes the pre-zoom view. The zoom records `camera_shot` at
  its start. Test: `test_cartoon_shots`.
- **`render --max-scenes N`** (MCP `render.max_scenes`): render at most N of the scenes still to
  render (config order), then stop without joining with `VidgenError` (`details.rendered` /
  `remaining`); rerunning continues. No resume inside a scene (manim cannot replay state to a beat
  exactly); split a long scene instead (beat ids keep the audio).
- `tests/test_actions.py` `BUILTIN_ACTIONS` is the one list the registry, the unknown-action
  message and the schema enum are checked against.

## 101. Shorts from a longer video (Phase Z2, Steps 249–250)

Cuts 9:16 Shorts (under 60 s, hook, word-synced captions, end card) out of a longer video. User
docs: docs/CONFIG.md "Cuts and Shorts", "`hook`", docs/COOKBOOK-YOUTUBE-SHORT-FOR-CODING.md.

### 101.1 Cuts (`cut:`, `vidgen.cuts`)

- `cut: {scenes, beats, hook, end_card}` (`CutConfig`; `CutScene` allows extra keys).
  `apply_cut(data, origins)` rewrites the **raw** config before set expansion and validation, in
  `Project._load` for the base and each merged variant; everything later sees an ordinary config.
  `config.cut` stays (`voice_warnings` skips unused voices).
- Beat ids (`<scene>_b<n>` of the full video) are written out before beats are chosen, **so a cut
  shares the full video's audio** (`Project.has_own_audio` compares by id). Beats: a list (that
  order) or `{from, to}`.
- Scene `params` merge like a set's (`merge_params`; named entries via `includes.entry_names`; an
  empty list clears; `drop: true` (`cuts.DROP`, `_merge_named`) removes a named entry, unknown
  names ignored); other keys merge or replace. A scene may appear twice under another id. The first
  scene's transition is dropped unless its entry gives one. `cut.beats` merge onto beats (lists such
  as `actions` replace).
- `hook` → overlay `{type: hook, id: hook, ...}`; `end_card` → a silent `end_card` or `card` scene
  `cut_end`.
- Errors (unknown scene / beat, backwards range, duplicates, a change for a beat not in the cut) are
  one `VidgenError` with problems at `cut...`. `origins` move with the scene.
- No fast-forward of left-out beats (manim cannot skip animations exactly); a cut states where
  characters start.

### 101.2 Shorts (`shorts:`) and the `hook` overlay

- `shorts: true | {max_seconds: 60, bottom: 0.2, right: 0.15, top: 0, left: 0}` (`ShortsConfig`,
  `VideoConfig.shorts_zones`). `overlays.shorts_area(project, area)`: captions, `lower_third`,
  `hook`, `NarratedScene.safe_area` and `card` text keep inside it. **Without `shorts:` nothing
  changes.**
- Karaoke in a Short (`SHORTS_KARAOKE`): default `size` `body`, `max_lines` 1, `max_words` 5;
  bottom captions `SHORTS_LIFT` above the area's bottom (`lift` overrides).
- `hook` overlay (`scenes/overlays.py`, layer 11): bold on a `primary` plate (`text_color_on`),
  window `at` .. `at + seconds`; without `size` it shrinks from 1.25 × `title` to `HOOK_MIN_SCALE`
  until it fits `HOOK_LINES` (2), else stays 1.25 ×.
- Layout dump: a Short's header has `shorts: [x0, y0, x1, y1]` (px); captions have `reach`.
- Lint `shorts_safe_area` (the only `mid_beat` rule): text past the box beyond `tolerance`; a face
  with `min_face` (0.25) outside; an overlay (its `reach` if any) over `min_cover` (0.1) of a face.
  `shorts_length` (error): planned length (`VideoPlan`) over `max_seconds`. `vidgen validate`
  (`cuts.shorts_warnings`): not portrait, too long.
- `zoom` `hold` (`Zoom.revert` returns nothing: stays zoomed until the next camera move) and `cut:
  true` (jump). `Action.opens_scene()` (`Zoom`: `cut`, not a plot region): at `at: 0` on a scene's
  first beat it applies before the entrance (`_apply_now`). A first-beat `shot:` still starts after
  the entrance (existing frames unchanged).
- `audio.bitrate` (`128k`–`320k`, default `192k`; `ffmpeg.join(audio_bitrate=)`): 256k keeps a
  −14 LUFS mix's AAC true peak under 0 dBTP.

### 101.3 Public surface and compatibility (Step 249)

`vidgen.api`: `apply_cut`, `shorts_area`, `Action.opens_scene`, `Rule.mid_beat` /
`rule(mid_beat=)`. Config: `cut` (params `drop`), `shorts`, overlay `hook`, zoom `hold` / `cut`,
`audio.bitrate`, lint `shorts_safe_area` (`min_cover`), `shorts_length` (last in `LINT_RULES`).
Without `cut` / `shorts` / `hold` everything behaves as before.

### 101.4 Review fixes (Step 250)

- Caption reach (`_mark_reach`, a Short only): each caption mobject's `overlay_reach` is the box of
  every caption of its beat(s), dumped in px, so one still catches a longer caption over a face.
- Mid-beat stills (`rule(..., mid_beat=True)`): `_scene_findings` also runs them on mid-beat stills
  (`stills` counts beat ends); in a Short `lint_project` renders `SHORTS_STILLS` (3) per beat and
  reuses a dump with ≥ 2 (`_stills_current`).
## 102. A neon city, an implant's view, other timelines (Phase AA, Steps 251–254)

User docs: docs/CONFIG.md "Isometric places" (**A city at night**), "Particles" (`glow`), "Echo
characters (`echo`)", "Overlays" (`hud`). All features below are additive and opt-in. Their
helper names (towers, traffic, HUD model, echo, kiss, haze, pendant) are exported from `vidgen.api`.

### 102.1 The phase (plan) and the gap analysis (Step 251)

Features: towers (§102.2), traffic (§102.3), glowing particles (§102.4), the `hud` overlay
(§102.5, §102.8), echo characters (§102.6), iso splashes (§102.9), display patterns (§102.10),
sliding doors (§102.11), haze (§102.12), small props (§102.13), neck accessories (§102.14), `kiss`
(§102.15), wavy hair (§102.17), wall strip lights (§102.18).

### 102.2 Towers (Step 251)

- **World** (`world/iso.py`): `OBJECT_KINDS["tower"]` (2 x 2); `TALL_KINDS` (kinds a placing may
  give a `height`: tower 2–30); `OBJECT_FEATURES` (tower `screen`, `garden`); checked in
  `place_objects` (height only for a tall kind, in range; features of its kind). Tower is in
  `SWITCHED_KINDS`, lit by default. `IsoObjectParam.on: bool | None` (`None`: the kind's default).
- **Drawing** (`iso_objects._tower`, maths in `cartoon/iso_city.py`, no manim): seeded lit window
  grid (`TOWER_LIT_SHARE` 0.58) while on, algae bands (`garden_bands`), neon trims in `detail`, the
  info screen (`screen_box`, `screen_color`, corners `tower_screen`), an antenna whose red tip
  (`TOWER_ANTENNA_LIGHT`) `IsoBlinkers` blinks.
- **Crawling screens** (`IsoScreens`, a story thing over the place's pictures, unlit): over each
  screen no other object hides (`in_front`), `SCREEN_LINES` bars crawling up
  (`screen_lines(now, seed)`).
- **Wide view**: `wide_view` does not keep `TALL_KINDS` objects whole (the frame cuts a skyline);
  `place_bounds` still counts them.

### 102.3 Traffic (Step 251)

- **Config** (`IsoTrafficLane`, `StageIso.traffic`): `{from, to, height 0.5–30 = 3, count 1–12 =
  3, seconds 1–120 = 6, color = #5FE8FF, size 0.4–3 = 1, at, shape, hull}` (shape §107); ends are
  known spots or in-map cells, not equal; outdoors only. `StageIso.lane_ends` gives world points.
- **Motion** (`lane_pods`): looping, `count` pods evenly spaced, under way at time 0; with `at`,
  each crosses once, smoothstep eased; fades over `POD_FADE` 8 % at the ends.
- **Drawing** (`IsoTraffic`, story thing, unlit, behind characters), `POD_LENGTH` 0.8 tile widths ×
  `size`. `pod_hidden`: a pod is not drawn when an object's box is `in_front` of its `POD_BOX` and
  the pod's middle lies in that box's screen outline (`box_outline`) — a few comparisons per pod
  and frame, instead of drawing pods into the per-character front pictures (§89.9).
- To follow a pod, `pan` to the lane's end spot with the same `run_time`.

### 102.4 Glowing particles (Step 251)

`ParticleSettings.glow` (any kind, rain splashes too): fill `GLOW_CORE` 0.45 towards white, a halo
stroke (`GLOW_HALO_WIDTH` 3, `GLOW_HALO_OPACITY` 0.4), opacity × `GLOW_BOOST` 1.6 (max 1). Cairo
strokes scale with the camera, so the halo width is reset to `GLOW_HALO_WIDTH × zoom` on every zoom
change. Without `glow` nothing changes.

### 102.5 The `hud` overlay (Step 251)

- **Model** (`vidgen/hud.py`, no manim): `alert_on`, `lines_shown` (`HUD_LINE_SECONDS` 0.6),
  `HeartMonitor {bpm, to, at, skips}` → `heart_rate`, `heart_beats` (the first `skips` beats from
  `at` left out), `heart_trace`; `ScanMeter {level, to, at, wave}` → `scan_level` (above 1 is off
  the scale), `scan_wave` (`organic` | `steady`).
- **Overlay** (`scenes/hud.py`, `@overlay("hud")`, layer 9: under captions and the hook; lint skips
  `contrast`): timed like a lower third (`scene`, `at` via the shared `scene_at` in
  `scenes/overlays.py`, `duration`, `across_cuts`; reuses `LowerThird`'s `validate_project`,
  `window`, `_start_in_scene`). Frame brackets and scan lines, alert plate, readout lines, heart
  and scan panels, all in the safe area; `opacity` applies to everything. `pose` reuses built parts
  and makes only moving parts fresh. Drawn in pieces (§102.8).

### 102.6 Echo characters (Step 251)

`CharacterEntry.echo: bool | EchoConfig {color = #B48CFF, opacity 0.2–0.9 = 0.5, flicker}`; hologram
and echo together are refused. `cartoon/echo.py` `apply_echo(figure, color, opacity)` (after
`build_character`'s hologram step) tints every member, hidden shapes too (expressions, visemes),
sets `figure.echo`. The stage treats an echo as a hologram for light (unlit, no fill light) and
flickers it. Lint `look_alike` (`character_pairs`) skips pairs with an echo.

### 102.7 Public surface and compatibility (Step 251)

Config: iso object `tower` (`height`, `screen`, `garden`); `iso.traffic`; particles `glow`; overlay
`hud`; `characters[].echo`.

### 102.8 A HUD that keeps off faces, drawn in pieces (Step 252)

- **Faces**: `Overlay.avoids_faces` (class flag; `Hud` sets it) makes `OverlayLayer` give the
  overlay `faces`, a callable returning on-screen head boxes `(left, bottom, right, top)` at the
  current frame (`OverlayLayer.face_boxes`: figures in `scene.mobjects`, not `hidden_by_shot`,
  `shown` ≥ 0.3, `head` points through the camera). Read live, because the stage's predicted
  stills know no iso place.
- **Places** (`vidgen/hud.py`): `face_cover(box, faces)` (faces grown `FACE_GROW` 0.12),
  `pick_place(places, faces, current, avoid)` (least covering, first of equals; `current` kept while
  it covers ≤ `FACE_COVER` 0.02 or is within `FACE_SWITCH` 0.05 of the best: no hopping). The alert
  is placed first, then the lines (avoiding the alert). `avoid_faces: false` keeps the first places.
  `compact`: texts and panels × `COMPACT` 0.72, the safe margin halved (every edge moves out).
- **Pieces**: `Overlay.pieces` (class int, 0: one piece): `state(t)` returns one state per piece
  (`None`: hidden), `pose_piece(mobject, k, state)` draws each; `OverlayLayer._patches` caches each
  patch by `(k, (piece, state))`, `composite` / `rgba` blend them in order, `posed` groups them
  (`Overlay.posed_whole`). The HUD has four (static frame, texts, heart, meter), so the static
  part is drawn once.
- **Lint `overlay_face`** (`lint/shorts_rule.py`, after `shorts_safe_area`, warning,
  `OverlayFaceRule.min_cover` 0.15): the layout dump's `overlays` entry has `faces: true` for an
  overlay that avoids faces; its texts and plates (`shape`, fill ≥ 0.3) covering ≥ `min_cover` of a
  `face` box are reported; not in a Short (`shorts_safe_area` checks those overlays by the same
  boxes: `_keeps_off_faces`, `_covering`, `_face_cover`). `hidden_speaker` skips such overlays.
- **In a Short** (`shorts_zones`): the HUD area is raised by `SHORTS_CAPTION_BAND` (0.13 of its
  height) to keep meters above captions; `compact` there only shrinks.

### 102.9 Plain splashes on an iso place (Step 252)

On an `IsoRainGround`, `ParticleField._draw_splashes` keeps only the ring (`splash_shapes(...)[:,
:1]`): seen from above the droplets read as a face. Flat stages keep §69.39's splash.

### 102.10 Display patterns `equations` and `timelines` (Step 252)

`DisplayFrame` gains `glyphs`, `wings`, `boxes`, `dots`; the display always has `GLYPHS` 48,
`WINGS` 12, `BOXES` 8, `DOTS` 16 extra members (`holo_*` in `DISPLAY_PARTS`, before the edge; empty
for other patterns). `equations`: formulas written symbol by symbol plus floating formula
butterflies kept in `FLOAT_BOX` (inside the glow, so the redraw region holds them). `timelines`: a
binary tree of `TIMELINE_LEVELS` 3 growing, then two dots meeting at each of its 8 tips.

### 102.11 Sliding doors (Step 252)

`StageIso.doors: swing | slide` (`IsoColors.doors`; `_wall_door(..., style)`, `_slide_door`).
Opening is §89.10's place change (a crossfade over the action's `run_time`; the door is part of its
wall picture). Foley: `place_change_cues(..., sliding=True)` → `DOOR_HISS`, on closing
`DOOR_SLIDE_SHUT`.

### 102.12 A haze over a spot (Step 252)

`StageIso.haze: [IsoHazeParam {at, width 1.2, height 2.6, color #BFE8FF, strength 0.6, from}]`
(checked like traffic ends). `cartoon/haze.py` (no manim): `haze_ribbons`, `haze_sparks`,
`haze_level` (fade in `HAZE_FADE` 0.8 s). `IsoHaze` (`iso_overlays.py`): story thing over the place
pictures, behind characters, unlit.

### 102.13 Small props `scanner`, `takeout`, `crystal` (Step 252)

In `SMALL_PROPS`; `scanner` and `crystal` are `SWITCHED_PROPS` with `GLOWS`. A scanner's bar and wave
(`SCAN_ROLE`) are drawn each frame by `LivingProp(scan=ScanMeter)` (`StageProp.scan:
ScannerReading {level, to, at, wave}`, `at` in scene seconds), warning-coloured above 1. A crystal's
core is a `lantern` overlay (`crystal_pulse`).

### 102.14 Accessories `medal` and `pendant` (Step 252)

`NECK_ACCESSORIES` (necklace, medal, pendant): one at a time. `clothes._medal`, `_pendant` (core and
halo marked `PENDANT_GLOW`). The stage unmarks those lit and (not in a draft) adds a `PendantPulse`
(halo follows `pendant_level` every `PENDANT_SECONDS` 1.6, times `FigureAlpha`).

### 102.15 The `kiss` action (Step 252)

`- {kiss: a, with: b, hearts, color}` (`story_actions.KissAction`, stage only, generated characters,
default `run_time` `KISS_SECONDS` 3). `StoryStaging.kiss` returns a `KissMotion` per character
sharing one `KissPlan` and a `KissBurst`, plus a `chime` at contact. `KissPlan` (figure_fx) on its
first frame turns both to face each other, records poses, computes the lean (`KISS_LEAN` 11°), the
step in (to `KISS_TOUCH` 0.03 head widths) and the rise (at most `KISS_RISE` 0.6 head heights
each: iso neighbours stand on a slant). Per frame `kiss_share` (in `KISS_IN` 0.7 s, out `KISS_OUT`
0.6 s) sets lean, legs (feet down), eyes `closed`, and an offset kept apart from the stage's own
placement (as `HandHold`). It runs on its own clock (`alpha × seconds`). `figure.kissing` names the
partner (layout dump `kissing`; `character_overlap` allows it). Partners holding hands let go first
(arms set before poses are recorded; two offsets would drift the pair off frame).

### 102.16 Lint `look_alike` and echoes; public surface and compatibility (Step 252)

`look_alike`: §102.6. Config: `hud` `avoid_faces`, `compact`; lint `overlay_face`; display
patterns `equations`, `timelines`; props `scanner` (`scan`), `takeout`, `crystal`; accessories
`medal`, `pendant`; `iso.doors`, `iso.haze`; action `kiss`. Overlay API: `Overlay.avoids_faces`,
`.pieces`, `.faces`, `.pose_piece`, `.posed_whole`.

### 102.17 Wavy hair (Step 253)

`look.hair: wavy` (`HairStyle`; not in `random_cast.HAIR`, so random casts are unchanged): long
waving locks ending in curls (`generator._wavy_outline` / `_wavy_side`), chin and neck clear; one
polygon behind the head, trailing like `long`.

### 102.18 Neon strip lights on a room's walls (Step 253)

`iso.wall_lights: <colour> | [left, right]` (indoor only; `wall_light_colors()`): a glowing strip
near the top of each standing wall face (`iso_scenery._strip_light`, `IsoColors.strips`,
`Poly(glow=True)`, so no `light` dims it). Part of the wall pictures (no per-frame cost).

### 102.19 Fixes from building a story: a kiss holding hands, lights behind a body, overlays (Step 253)

- Kiss while holding hands: §102.15. HUD and `hidden_speaker`: §102.8.
- A lab object's blinking lights (`IsoBlinkers(hidden=)`) are not drawn while a character stands
  `in_front` of the object and covers the light (`IsoStaging._iso_light_hidden`; shot-hidden
  characters do not count).
- Actions of one beat at different `at` run one after another while an earlier one runs (the
  runner waits per phase); actions meant to overlap share one `at`.

### 102.20 Shorts of the story; review of Phase AA (Step 254)

- **A cut drops a scene's own overlay**: a scene overlay timed `at` a beat the cut leaves out is an
  error (`scene ... has no beat ...`); a cut entry's `overlays: {<id>: {drop: true}}` leaves it out
  (`cuts._drop_overlays`, after the entry's changes merge; key `cuts.DROP`).
- **Render fingerprints and cuts**: with a `cut:`, `cut` is left out of each scene's fingerprint
  (it is already applied to the scenes); without one the dump keeps `cut: null`, so other projects'
  fingerprints are stable. A new hook re-renders every scene (a video-wide overlay).
- Limits: lint does not check the hook while it shows; a zoom near a wide stage's edge is kept on
  the stage, so a high `scale` pushes targets aside.

## 103. More iso lab and sci-fi objects (Phase AB, Steps 258–260)

24 lab / sci-fi objects in `OBJECT_KINDS`, drawn in `cartoon/iso_objects.py` (§100.11 style), 1 x 1
except `chemistry_bench`, `airlock` (2 x 1); user list: CONFIG "Other objects". Rules:

- **Tables**: `SWITCHED_KINDS` (`on`), `OPENING_KINDS` (`open`), `OPEN_WORKING` / `object_working`
  (works while on *or* open), `WALL_KINDS` (placed at a standing back-wall cell, facing the floor
  below or right of it; `_wall_box` a thin slab; `wall_clock` `time: "HH:MM"` default 10:10,
  `clock_hands`), `IsoObjectParam.kind` → the placing's `features` (`hazard_sign`: `HAZARD_SIGNS`,
  did-you-mean). Objects do not stack; `top` objects hold small things. Screen text facing right
  reads from the left (`_reading`).
- **Moving parts** (`MOVING_KINDS`): `object_motion(item, look, base, now, state)` returns a fixed
  number of `Motion` polygons. The stage draws one `IsoGadgets` per working, shown object (states
  logged from the start and by `iso_change`: `_iso_state_log`); glowing parts skip the light grade;
  not in a draft. `ObjectLook.moving` tells the picture to leave the moving part to the overlay.
- **What hides them**: an object covering a gadget is redrawn over it as a *cover* picture
  (`iso_scenery.front(its box)`) that follows place changes (`_iso_follow_change`).
  `_iso_place_gadgets` (from `_iso_keep_order`) keeps each gadget and cover right after the last
  body front picture showing the object, else after `_iso_gadget_home`; order among gadgets §109.

## 104. More iso objects: home, town, nature, school, fantasy, seasons (Phase AC, Steps 261–267)

63 more objects in §103's conventions; user list: CONFIG "Other objects".

- **Modules**: one per batch under `vidgen.cartoon` (`iso_home`, `iso_shop`, `iso_town`,
  `iso_nature`, `iso_school`, `iso_fantasy`, `iso_seasons`; `iso_retro` §107). `MORE_MODULES` (kind →
  module) tells `object_shapes` / `object_motion` where to look; each module has `DRAWINGS` (frame,
  look, state → shapes) and `motion(frame, look, now)` and is imported lazily (no cycle). Kinds and
  their tables stay in `world/iso.py`.
- **Lamplight**: `LAMPLIGHT_KINDS`: a lit one lights nearby characters like a lamp (§89.13), from its
  footprint's middle (a `lamp`: its first cell's). Lamplight is warm, so cold-glowing kinds are out.
- **Kinds per object**: `OBJECT_STYLES` (object → its kinds, the first the default; e.g.
  `display_case` → `DISPLAY_CASES`) checks `IsoObjectParam.kind`; part of `OBJECT_FEATURES`.
- **Placing rules**: `ObjectKind.floats` (`boat`: every cell water; error "floats: put it on water
  (~)"); `dock` walkable and `over_water` (`deck` 0.22); `archway` not walkable; `torch_sconce` is a
  `WALL_KINDS` object with a draw box `SCONCE_SPAN` out from the wall. A working `boat` moves whole,
  so the stage alone draws it while working. `traffic_light` cycles `SIGNAL_CYCLE`; a still shows red.
- **Pools of light**: `light_pool(centre, radius, strength)` (saturated amber `LIGHT_POOL`, since a
  pale colour over the night-multiplied picture reads olive) draws every lamp's pool. A pool is a
  `Disc` marked `pool`, drawn only in its own picture (`draw_shapes(pool=True)`; plain and glow
  pictures leave pools out). The stage shows pool tiles (`PoolTile`, between a picture's tiles and
  its glow tiles) at `pool_strength(grade)` (`POOL_DAY` 0.1 by day up to 1 at `LAMP_DARK`), set on
  the camera by `StageLight` (`POOL_STRENGTH`; no light or a draft: day). A pool is drawn by the
  base picture or its piece's layer, never by a character's front picture
  (`IsoScenery.pool_shapes`); pool tiles have no overlap and meet on whole pixels (`draw_tile`
  rounds) so no pixel is drawn twice. A layer picture's clip (`IsoScenery.clip`) includes its pool.
- **Moving light** (`Motion.pool`) shows at pool strength (`IsoGadgets(pool_strength=)`). A gadget's
  redraw region covers where its parts reach over `GADGET_SAMPLES`.
## 105. Seven features without AI APIs (Phase AD, Steps 268–275)

No AI API calls (no LLM or hosted model) in this code or its tests: rules, heuristics and local data
only, plus CLI / MCP building blocks an agent can use.

### 105.1 Moving vehicles (Step 268)

- **Actions** (`scenes/driving.py`; user docs CONFIG): `drive_to` (`car`, `train_car`), `sail_to`
  (`boat`), `lift_off` (`rocket`) on the place's objects; `to`, `via`, `speed` (`VEHICLE_SPEEDS`:
  car 2.6, train 2.2, boat 1.1 tiles/s), lift-off `run_time` `LIFT_OFF_SECONDS` 4. `run_time_for`
  = route length / speed + `SET_OFF_SECONDS` 0.6.
- **Rules** (`world/iso_vehicles.py`, no manim): cars (path cells, one level) and boats (water) move
  over four neighbours (side-on drawing: no diagonals), a cheapest path over (cell, heading) with
  `DRIVE_TURN_COST` 0.3 and `UTURN_COST` 4 (a U-turn is drawn as a flip). It stops with its front
  in the goal cell; a *spot* off its way becomes the nearest stoppable cell within `GOAL_REACH` 2
  (an explicit cell is taken as written). A train car rolls along `track_cells` (its line extended
  over level free floor or path), its middle stopping at `to`. Blockers are named in the
  `VidgenError`. A rocket rises `LIFT_HEIGHT`. In the middle half of a corner's leg
  (`VehicleRoute.turning`) a car or boat is drawn at 45° (`turning_shapes`).
- **Validate** replays them in `iso_move_problems` (`ISO_VEHICLE_ACTIONS`, `vehicle_problems`):
  vehicles stay where they stopped (`moved_place`); a second `lift_off` is refused. At render
  `iso_place_now` includes planned vehicle places.
- **Drawn** (`cartoon/iso_driving.py`): `ObjectLook.driven` leaves a driven vehicle out of the place
  pictures (a rocket keeps its pad and tower); the stage draws an `IsoVehicle`, a sprite shifted
  across the screen (iso has no perspective; one sprite per heading / on / wheel or flame frame).
  The sprite is three fixed image mobjects (picture, `PoolTile`, `GlowTile`) whose pixels change,
  because Manim keeps a moving mobject's members from the animation's start (swapped members
  ghost). `car_shapes(..., reverse=True)` is the back view driving up the picture. Train track
  `track_shapes` is in the ground along `track_cells`. Rocket smoke is an `IsoGadgets`
  (`rocket_smoke`) while firing and `SMOKE_AFTER` 2.5 s after.
- **On the stage** (`scenes/stage_vehicles.py`, `IsoDriving`): a body of the place (`_iso_bodies`,
  `IsoVehicle.box`, `VEHICLE_SIZES`) with a front picture (`IsoScenery.front(box, exclude=)`: not its
  own piece), sorted with characters; `IsoDrive` redraws bodies while it plays. A living thing
  (`update_to`, `changing`). Works with `switch_on` / `switch_off` (`iso_switch_vehicles`),
  `follow`, lint `offscreen_action`, foley `drive_cues`, a tall frame's wide view
  (`_iso_vehicle_views`).
- **Limits**: vehicles and walkers do not avoid each other; no riders; one train car; headlights
  switch at once.

### 105.2 Sitting, lying and using furniture (Step 269)

- **Actions** (`scenes/sitting.py`): `sit_on` (§69.28) also takes an iso object; `lie_on` and `use`
  (`run_time` `USE_SECONDS` 3, timed, not held) are iso only; `stand_up` from any. `use`, not a verb
  per object: the object picks the pose. Postures live in the scene's `Postures` (`Postures.lie`:
  one per bed; `PINNED_ACTIONS` + `wander`, `meet`).
- **Rules** (`world/iso_seats.py`, no manim): `ISO_SEATS` (kind → `IsoSeat`: hips at footprint
  shares `a`, `b` in the object's `_Frame`, `z`, `faces` `front` | `back` | `+a` | `-a`, `front`
  regions, `tucked`), `ISO_BEDS` (`IsoBed`), `ISO_USES` (`IsoUse`, `style` `type` | `warm` | `read`
  | `reach`). A facing-`right` object mirrors the frame (`seat_facing`; no back view). `sit_on` takes
  the free seat nearest the feet (`seat_order`); `use_point` = half way between the hand place and
  the nearest footprint point. Validate (`iso_move_problems`, `ISO_SEAT_ACTIONS`,
  `seat_step_problem`): object within `SEAT_REACH` 1 (8 neighbours), seat free, a walk before
  `stand_up`, no `use` while lying; the hint names the cell to `walk_to` (`next_to`).
- **Drawn** (`scenes/stage_seats.py`, `IsoSeating`; `IsoSeatMove` in `cartoon/iso_motion.py`): feet
  to the floor under the seat (`iso_feet`), `Character.seated`; standing up returns to the start.
  Lying: turned `LIE_DEGREES` (atan 2) about the hips, scaled `LIE_SCALE` 0.72, legs folded.
  **Draw order**: the sitter's box is inside the object's, so its front picture excludes the object
  and starts with the object's *part* in front (`IsoScenery.part`: shapes whose `shape_points` lie
  in the seat's `front` regions, one extra piece per seat, in front pictures only). The seat is on
  the figure (`iso_seat`) from sitting down to the end of standing up.
- **Use**: an `ArmMove` (`reached_parts`; both hands for `type` / `warm`). A standing user turns to
  the object (to its side if straight behind or in front); a seated one keeps its facing.

### 105.3 A day passing in one scene (Step 270)

- **Action** (`scenes/light_action.py`, `TimeOfDay`): `- {time_of_day: <preset>, run_time,
  auto_lights, move_sun}` (`LIGHT_PRESETS`; default `TIME_OF_DAY_SECONDS` 6; `auto_lights` true;
  `move_sun` on with a `sun` / `moon` prop outdoors, `true` requires one). Its own action, not a
  `light` option, because its defaults differ; `light` switches nothing.
- **Rules** (`cartoon/lighting.py`, no manim): `darkness(grade)` (one minus the mean `multiply`
  over `LAMP_DARK`: day 0 … night 1); dusk `DUSK_DARK` 0.35; `dusk_crossing` finds where the
  smoothstep fade crosses it; `auto_switch_time` offsets each light up to `AUTO_SPREAD` 0.9 s (at
  most `AUTO_SPREAD_SHARE` 0.2 of the fade) by a CRC of its name (deterministic); a fade from past
  dusk to darker switches at `DARK_SWITCH_SHARE` 0.25. `day_stages`: day → night passes `sunset` at
  `TWILIGHT_SHARE` 0.5, night → day passes `morning`.
- **Stage** (`scenes/stage_daylight.py`, `DayPassing`): `pass_time` adds a `change_light` per stage
  and, with `auto_lights` and not to `indoor`, switches at the crossing each of `StageIso.auto_lit()`
  (`AUTO_LIGHT_KINDS` minus `auto_light: false`) via `iso_change(..., auto=True)` over
  `AUTO_SWITCH_SECONDS` 1.2, driven cars, and flat `lamp` props (`LivingProp.switch(fade=)`).
  Auto-lit objects are layered (`_iso_action_targets`). `offscreen_action` ignores auto changes;
  moving parts fade with them (`Gadget.level`).
- **Sky**: an outdoor stage with `time_of_day` and no `background` draws the time of day's sky
  (`window_sky`, ungraded, `sky_at`), stars at `grade.stars ** 2`. With a ground band a sky body
  sinks behind it (`SkyBody(sink=)`).

### 105.4 Iso weather: reflections, fog, wind (Step 271)

- **Config**: iso stages take the stage's `fog`, `wind` and the `wind` action (one fog and one
  wind on both stages); indoors they are refused. Rain `settled` pre-grows `puddles`. Reflections
  come with rain `puddles`.
- **Rules** (`cartoon/iso_weather.py`, `cartoon/fog.py`, no manim): lights are an object's glowing
  `Poly` / `Disc`, not pools (`glow_outlines`), mirrored to `2z - h` (`mirrored`), clipped to the
  puddle ellipse (`still_reflection`, `clip_convex`), wobbling while it rains (`shimmered`). Wind:
  `ISO_SWAYS` (kind → `Sway`), `iso_sway_degrees` = `ISO_SWAY_SHARE` 1.0 × degrees × felt force ^
  `ISO_SWAY_POWER` 0.65; `sway_rows` shears a sprite; `ISO_SWINGS` (`balloon_bunch`) turn whole
  (`swing_pixels`). Fog: `iso_fog_depths` spreads the five bands from the back edge (`x + y`)
  forward; `iso_band_outlines` in tile widths.
- **Drawing** (`cartoon/iso_atmosphere.py`): `IsoReflections` at `REFLECTION_OPACITY × darkness ×
  lit(owner)`, ungraded, clipped once per puddle size step (`SIZE_STEP` 0.02), only the wobble per
  frame; `IsoFog` (`FogBand` per share); `IsoSwayer` (a padded sprite bent by the local force).
- **Stage** (`scenes/stage_weather.py`, `IsoWeather`): with wind, outdoors, not in a draft, swaying
  kinds no action targets are `IsoScenery.apart` (in no picture, still in the top surface, so they
  keep rain off) and drawn as swayers with cover pictures (`iso_covers`, `_iso_place_swayers`). Fog
  bands go before the first body at their depth (`_iso_sort_fog`). Light states are logged when
  puddles may lie (`_iso_glow_log`) so a switched lamp fades its reflection. Nothing is redrawn
  while nothing moves.
- **Limits**: only glowing shapes are mirrored; objects an action changes do not sway.

### 105.5 A story in prose to a draft project (Step 272)

- **Command**: `vidgen story draft STORY [-o DIR|FILE] [--style iso|flat] [--format 16:9|9:16]
  [--narrator VOICE] [--seed S] [--force] [--json] [--audio]`; MCP `story_draft` (`input_path` or
  `story_text`); user docs CONFIG "A story in prose". Writes `video.yaml`
  (`plan_yaml.commented_yaml` / `write_project`) and `story_draft.md`; `--json`
  (`jsonout.story_document`): paths, report, cast, scenes, every line with `speaker`,
  `confidence`, `method`. Never calls a model.
- **Reading** (`story_text.py`, no manim): scenes at headings, break lines and time cues; quotes
  `"…"`, `“…”`, `«…»`, and single curly quotes when there are no double ones (`quote_pattern`).
  Characters from tags, `TITLES`, name lists, `FAMILY`, repeated subjects, `PERSON_NOUNS`
  (`Character.described`). First person: ≥ 3 first-person words outside quotes and one per 100
  words. Each quote gets a speaker with a confidence and method (tag 0.95–0.75, action beat 0.6,
  address by name 0.55, alternation 0.5, last mentioned 0.3, narrator 0.1). Narration beats ≤
  `MAX_BEAT_WORDS` 25; moves from `MOVE_VERBS`.
- **Places** (`story_places.py`): `PLACES` (eleven ready iso places with stand spots, walk goals, a
  `<place>_night` set, free cells for `OBJECT_WORDS` objects — numbered when the kind exists — and a
  flat set), chosen by keyword counts (tie: previous scene). Light from `LIGHT_WORDS` / clock times
  (later cues → ≤ 2 `time_of_day` actions outdoors), weather words, music by `MUSIC_WORDS`,
  `DRAFT_AMBIENT` outdoors.
- **Draft** (`story_draft.py`): title card (`card_mood` / `CARD_LOOKS`), scenes, end card; ≤ 4
  characters per scene, `enter` / `exit` from verbs, dialogue with emotion, close-ups and
  two-shots; voices via `screenplay.assign_voices` (narrator `bf_emma` or `--narrator`; first person
  shares the protagonist's voice). `auto_direct: true`; speakers under 0.6 get `# TODO:`. `--audio`:
  §111.

### 105.6 Shorts suggestions (Step 273)

- **Command**: `vidgen shorts suggest [PROJECT] [--count 3] [--min 30] [--max 60] [--teaser]
  [--spoilers] [--end-card TEXT] [--write] [--out shorts.yaml] [--json]`; MCP `shorts_suggest`;
  user docs CONFIG "Suggested Shorts". Never calls a model.
- **Timing** (`shorts_suggest.timed_beats`): `VideoPlan` of the base config in a
  `project_session`; beat lengths from MP3s, else words / `narration.words_per_second`; silent
  scenes break runs; a cut's length adds scene `outro`s and the end card (3 s; teaser 2.5 s).
- **Windows**: runs of whole beats in one run of narrated scenes, `min`..`max` long, not opening on
  an `overlap` / `interrupt` beat, no kept beat waiting `until` a left-out one. Scored by
  `score_window` (dialogue, questions, emotion words `EMOTION_WORDS`, moves, variety, start / end
  strength, length over 45 s, spoiler −4 for the last 15 % unless `--spoilers`; parts kept for the
  report); greedy, ≤ 25 % overlap. Hook: `hook_line` / `shorten` (≤ 6 words), else
  `HOOK_TEMPLATES`, else "Wait for the ending.". Teaser (`teaser_beats`): beats ≤ 6 s, ≤ 2 per
  scene, ≤ 15 s, film order.
- **Variants** (`short_variant`): 1080×1920, preview 360×640, `shorts: true`, `audio {target_lufs:
  -14, bitrate: 256k}`, watermark + karaoke captions, a `cut` per scene, `{zoom: speakers, at: 0,
  cut: true, hold: true}` prepended to the first kept beat of each stage scene (no `hold` when a
  framed character moves later); a mid-scene start first restates the light left by skipped beats
  (`RESTATE_SECONDS` 0.1). Names `short1..`, `teaser`, skipping existing ones.
- **Writing** (`write_suggestions`): a separate included file, not `variants:` in the config, so it
  can be regenerated while the config's text stays. `includes.INCLUDABLE_KEYS` has `variants`
  (merged by name; the config's win). `shorts.yaml` is added to `include:` by a one-line text edit
  (verified by reloading; flow-style YAML or JSON is rewritten whole); backups `<config>.bak`,
  `shorts.yaml.bak`; then validated (problems: exit 1). JSON document `shorts`
  (`jsonout.shorts_document`).

### 105.7 Ambient life (Step 274)

- **Config**: stage key `ambient` (iso only; a stage key like `fog`): `{walkers, birds, cat, ducks,
  butterflies, fireflies, flies, muted, seed, auto}`; counts or `true` (`AMBIENT_DEFAULTS` 3, 4, 1,
  2, 3, 10, 1; max `AMBIENT_MAX`); `ambient: true` = `{auto: true}`. `_check_ambient`: not flat,
  indoors only `INDOOR_KINDS` (`cat`, `flies`), `ducks` need water. `muted` defaults to true.
- **Rules** (`world/iso_ambient.py`, no manim): `ambient_cells`; creatures avoid `around()` the main
  characters' spots, move targets, named objects, seats, beds, driven vehicles, a `clear` radius 2
  round characters, `roads` / tracks and a sailing boat's lanes (`_ambient_lanes`). An
  `AmbientPlan` per creature (seed `ambient_seed(seed, name)`) builds `AmbientMove`s lazily; `at(t)`
  in any order gives the same poses (deterministic). Walkers route with `cell_route`.
- **Drawn** (`cartoon/iso_ambient.py`): `IsoCritter`, a place body with three fixed image slots
  (picture, `PoolTile`, `GlowTile`), a sprite per (pose, frame, facing, detail); `critter_look` by
  seed (`muted`: colours `MUTED_SHARE` 0.35 to grey); walkers and the cat take lamplight.
- **Stage** (`scenes/stage_ambient.py`, `IsoAmbience`): made at the end of `_iso_scenery` (none in
  a draft), in `_iso_bodies` and `story_things`, never action targets. Hidden past a zoom of
  1.45–1.9 over the wide view; butterflies fade with darkness, fireflies appear with it. Front
  pictures per (cell, height band) (`IsoScenery.front(over=)`), clipped to the sprite
  (`IsoTiles.clip`) and spliced in without a full re-sort (`_iso_splice_front`).
- **Limits**: creatures do not react to characters or each other; no own sounds.

### 105.8 Review of Phase AD (Step 275)

Folded into §105.1–§105.7. Schema rule: an optional boolean (`bool | None`, e.g. `on`) also accepts
the YAML 1.1 `"true"` key.

## 106. A fixed-scale wide view for iso places (Step 277)

The whole-place wide views (§89.13, §100.6) fit the place's bounding box; `wide: fixed` fixes the
character's share of the frame instead, so a bigger map fills the frame with ground.

- **Setting**: `StageIso.wide` takes `fixed` and `IsoFixedWide` (`{tiles: N}`, 2–80);
  `StageIso.fixed`, `wide_fit()` (`"fixed"` for both), `view_tiles(fw, fh, character_size)`.
  `character_size` on an iso stage is accepted only with `wide: fixed` (`_iso_wide_given`; refused
  otherwise, naming `wide: fixed`); `expand_character_size` passes the video's to such scenes.
- **Scale** (`iso_stage`): `ISO_FIXED_SHARES` small 0.14, medium 0.20, large 0.28 — a character's
  height as a share of the frame's height in both formats; `fixed_tiles(fw, fh, size)` = tile widths
  across. The view is never wider than the whole place's fit (a small place shows whole).
- **On the ground**: a view of half size `hu` × `hv` centred on picture point (u, v) shows only
  ground iff the ground point under its centre (`x = 2v + u`, `y = 2v − u`) is `fixed_reach = hu +
  2hv` cells from every map edge. `on_ground` clamps x and y independently (an axis too short: its
  middle); `fixed_fill_size = ceil(2 · reach)` (the shorter side of a non-square map counts).
- **Centring** (`fixed_view`): the middle of the bodies' padded bounds (else the place's middle),
  `on_ground`, then moved as little as keeps the bodies in view (`ISO_MARGIN`,
  `ISO_WIDE_BODY_ROOM`: bodies win over the ground), then inside the frame. `wide_view(...,
  fit="fixed", tiles=)` dispatches to it; `ground_view_center` is the same move for any view.
- **Moves over it**: `Stage.zoom_base()` = the fixed view's magnification over the whole place (1
  otherwise); `Zoom` multiplies `scale`, its cap (`max_scale`) and its "already fills" test by it;
  `frame_shot` / `shot_view(max_scale=)` (`MAX_SHOT_SCALE` × base on iso), `follow_width(most=)`
  likewise. `MAX_DETAIL` 5. `SmoothFollow(settle=)` keeps the view on the ground
  (`Stage._follow_settle` → `_iso_on_ground`, feet in view), applied by `_MoveThenFollow` within
  `FOLLOW_MAX_OFFSET`; `pan_point` moves onto the ground keeping the target in the middle half.
- **Lint `iso_ground`** (still rule, warning): `IsoStaging.layout_keys` adds `iso_ground` on a
  scene's first beat (`view`, `place`, `map`, `size`, `tiles`, `need`); a fixed view on a map below
  `need` warns with the size that fills the frame; outdoor `auto` / `fill` gives an info hint naming
  `wide: fixed` (`IsoGroundRule.hint`).
- Without `wide: fixed`, framing, shots and moves are unchanged.

## 107. A retro-future kit (Phase AE, Step 278)

A 1950s–60s "world of tomorrow" kit; user list: CONFIG "Other objects".

- **Style** (`StageIso.style: plain | retro`, default plain): merges `STYLE_COLORS[style]` under the
  place's `colors`, `STYLE_TEXTURES[style]` under its `textures`, and takes objects' default
  colours from `object_colors(kind, style)` (`STYLE_OBJECT_COLORS`; a placing's `color` / `detail`
  win). Retro traffic defaults to cream saucers. An iso key, not a theme preset (themes colour text
  and charts).
- **Textures** (`StageIso.textures: {grass | path | floor | tiles: texture}`, `TEXTURES`,
  `TEXTURED_SURFACES`; `IsoColors.textures` / `texture(surface)`): a surface's own texture
  (`DEFAULT_TEXTURES`) takes the plain code path (identical pictures); any other draws in `_texture`
  without the cell parity shading.
- **Objects** (`cartoon/iso_retro.py` via `MORE_MODULES`): `retro_tower` is in `TALL_KINDS` (4–30,
  on by default); `sunburst_clock` in `WALL_KINDS` and `CLOCK_KINDS` (with `wall_clock`: `time`);
  `tv_console` `kind` from `CONSOLE_PICTURES`; `monorail`, `hedge`, `planter` take `size`. `ISO_USES`
  has `retro_desk` (`type`), `tube_computer`, `tv_console` (`reach`).
- **Rocket car** (`CAR_STYLES`: `car` `kind: sedan | rocket`): `car_shapes` hands a rocket to
  `rocket_car_shapes`; driven too (`IsoVehicle(features=)`, `vehicle_shapes(features=)`,
  `frame_item(features=)`).
- **Traffic shapes** (`IsoTrafficLane.shape: capsule | saucer | monorail`, `hull`; `PodLane.shape`
  / `hull`, `POD_SHAPES`, `POD_RETRO_HULL`). A monorail lane at about 3.15 over a `monorail` beam's
  row rides on it, never hidden.
- **Looks**: outfits `suit`, `lab_coat` (`SKIRTED_OUTFITS`), `jumpsuit`; hair `pompadour`, `bob`;
  accessories `fedora`, `pillbox` (`TOP_OF_HEAD`). `random_cast` keeps its own lists.

## 108. Crisp blue hour, friendly faces, rooms with walls (Step 279)

- **Blue hour** (`light: blue_hour` in `LIGHT_PRESETS` / `PRESET_LIGHTS`, `cartoon/lighting.py`):
  tint `#3555B8` at 0.56, no glow, stars 0.7, shadows 0.6; `PRESET_SATURATION` 1.6; `PRESET_TONES`
  (gamma 1.2, contrast 1.3, vivid 1.15). `LightGrade` has `saturation` (> 1 boosts; `grade_rgbas`
  clips), `gamma` (per channel before the multiply), `contrast` (about `CONTRAST_PIVOT` 0.35 after
  multiply and glow), `vivid` (after), `curved`; `grade_rgbas` / `grade_pixels` share
  `_graded_colors` (a grade without them takes the plain path). Lifted blacks or a strong tint read
  as a filter, a pivot at 0.5 as day. Its `darkness` is past `DUSK_DARK` (pools, lamplight, glows
  show). `lifted`, `blend_grades`, `flash_grade`, `flashback_grade` carry the tone fields.
- **Fill colour** (`Stage.fill_color`): `lifted(grade, share, toward)` lifts towards the colour's
  multiply instead of white; `mark_light_lift(..., toward)`, `LIGHT_LIFT_TOWARD`, cached by (grade,
  share, toward).
- **Outlines on a fixed view**: characters are built at the whole place's scale, so the one-pixel
  stroke floor must be one pixel of the fixed view (else close-ups magnify outlines ~18×).
  `pixel_zoom(zoom)` (context in `cartoon/character.py`; `Stage.construct` wraps the scene in it
  with `zoom_base()` on iso, 1 elsewhere) makes `one_pixel_stroke()` use it.
- **Eyes**: `eyes: bright` (`BRIGHT_EYE`).
- **Rooms** (`StageIso.show_walls`, indoor with `wide: fixed`; `wall_room()`): the standing back
  walls cover `2 h ISO_RISE` cells behind their foot (`wall_reach`, less `WALL_VIEW_MARGIN` 0.3; 0
  unless a back edge is standing wall all along); `on_ground` / `ground_view_center` / `fixed_view`
  / `wide_view` take `back=` to reach that far; `fixed_view` then sits as far back as allowed (`v =
  (reach − back + |u|) / 2`), bodies still win. `poster` (`POSTER_PICTURES`) and `wall_shelf` are
  `WALL_KINDS` (`cartoon/iso_retro.py`, `WALL_SPANS`).

## 109. Fast lit iso places, object zooms (Step 280)

- **Graded pictures kept** (`cartoon/shading.py`): `GradedPictures` keeps per picture the grade, a
  fingerprint (`pixels_digest`: shape, dtype, CRC-32 and Adler-32 of the bytes) and the read-only
  graded pixels; same fingerprint and grade → the kept array. A fingerprint, not identity, because
  pictures change in place (pools, sprites, snow). `OwnedCache` holds values per live owner
  (`weakref.finalize`) within `GRADED_CACHE_BYTES` 192 MB. `StageLight._draw_image` skips pictures
  wholly outside the frame (`_in_frame`).
- **Tile parts kept** (`cartoon/iso_pictures.py`): the light hands a tile `(GradedPictures, grade)`
  (`TILE_GRADING`); `draw_tile` asks `TileParts` for its on-screen part keyed by (fingerprint, grade,
  size, box): a hit draws it as is, a miss grades and resizes (`TILE_PARTS_BYTES` 128 MB).
- **Memory**: `TILE_CACHE` 64; `IsoTiles` drops other levels' tiles when its level of detail changes
  (`_forget_levels`) and the oldest unshown tiles beyond `TILES_KEPT` 3 × shown + `TILES_SPARE` 16
  (`_forget_old`). The caches never change pixels (`tests/test_picture_caches.py`).
- **Object zoom** (`scenes/actions.py`, `scenes/stage_iso.py`): the targets' box comes from the
  scene's `target_box(target)` when it has one (`Stage.target_box`: an object's picture bounds,
  `_iso_object_box`; a layered picture spans the whole canvas), else from on-screen parts. Camera
  moves (`moves_camera`: zoom, pan, follow, shot) do not make an object a layered picture.
- **Gadgets back to front**: `_iso_gadget_places` sorts gadgets by their pieces' draw order.
- **Limit**: a `closeup` at a beat's start on a character who sits down in that beat frames where it
  stood (zoom after the sit).

## 110. Arms at the sides, crossfaded stages, batched joins (Step 281)

- **`arms: front | classic`** (`ArmStyle`; `CharacterLook.arms`, video `cartoon_arms`;
  `generator.ARM_STYLES`). `front` (`generator._arms` / `_arm_hang`): each hanging arm (the side
  view's far arm, both front-view arms) gets its shoulder just past the body's edge
  (`ARM_SHOULDER_OUT`) and the least lean (0.5° steps, at most `ARM_MAX_LEAN` 14°) keeping forearm
  and hand `ARM_GAP` clear of the outline; the side view's near arm leans until its hand's middle is
  on the edge. The lean is in the rest shapes, so poses (relative to the leaning rest), walk swings
  and `reach` work. The side view's far arm is drawn over the body and under the near arm
  (`FAR_ARM_ORDER` 34 / 35). `classic` is the older drawing, unchanged (pinned by tests with
  `arms="classic"`). Defaults: §110.1. `look_key` includes the style.
- **Crossfades into a stage** (`Stage` entrance): with an overlapping `transition_in` the set is
  simply there (the transition blends it; no fade from the background colour), and the scene before
  holds its last picture instead of fading out, so shots of one place do not dip.
- **Joining many crossfaded scenes** (`render/ffmpeg.py`): over `BLEND_BATCH` 8 runs,
  `_blend_batches` blends 8 at a time into lossless H.264 intermediates (`LOSSLESS_CODEC`, removed
  after), then blends those: the same frames as one graph without every input open at once.
- **API**: `vidgen.api.character(..., arms=)` takes the caller's default (the video's and the look's
  win).

### 110.1 `front` is the default everywhere (Step 282)

A character's `look.arms`, else the video's `cartoon_arms`, else `generator.DEFAULT_ARMS =
"front"` (default of `generate_parts`, `look_parts` / `look_key`, `build_character`); no
stage-specific rule. `classic` is the opt-out. Every place that draws a generated character passes
the video's `cartoon_arms`: `api.character`, stills, the character sheet, the scene host
(`build_host(..., arms=)`); the look gallery still (`write_looks_png`, §69.47) takes the default
unless a look says. Pre-made SVG characters are untouched.

## 111. Audio-only output (Phase AF, Step 283)

User docs: docs/CONFIG.md "Audio only (`audio_only`, `sections`, `pacing`)", docs/COOKBOOK-AUDIO.md.

- **Switch**: `vidgen render --audio-only` or `audio_only: true` (not `output:` / `format:`, which
  mean other things). `vidgen.audio_only.render_audio` checks scenes as a render does
  (`_check_scenes`, `warn_audio`), plans the timeline (`plan_audio`), writes
  `build/<render>/audio/voice.wav` (each beat's MP3 at its start, shaped by its `BeatWindow` like
  `add_narration`), `sfx.wav` (`sfx.write_track`) and the mix (`mix.mix_audio(...,
  always_write=True)`; default off, so a video's mix is unchanged), delivers `Project.audio_path`
  (`<output>[_<variant>][_preview|_draft].<ext>`, §111.1) and writes `timings.json` (the combined
  timings' shape without `format`, plus `audio_only: {timing, left_out}`). No `pre_render` /
  `post_render` hooks. MCP `render` takes `audio_only`.
- **Timing** (`pacing:`): `speech` (default) times each line by its MP3 (else the word estimate)
  plus gaps (`line` default `narration.pad`, `speaker`, `scene`, `chapter`, or the beat's `pause`),
  stings (`sting_before`, `sting_after`), overlaps via `beat_windows`; silent scenes last
  `pacing.silent` (overriding a pause section's seconds too) or their `duration`; first scene at 0
  after `lead_in`, `tail` after the last. `video` takes every start from `VideoPlan` at the
  format's fps (the MP4's soundtrack). Both deterministic.
- **Sounds**: only what the config fixes (scene `sfx:`, `sfx` actions §87.2, stings, voice sounds
  §69.33, `entrance_sfx` with `sfx.auto`); sounds made by scene code at render time are left out and
  named (`AudioPlan.left_out`, a warning, `--json` `left_out`) unless §112.1 supplies them.
- **Sections** (`vidgen.sections.expand_sections`, on the raw config in `Project._load` and
  `parse_config`, before cuts, sets and translations): `{id, title, voice, music, sfx, room,
  ambience, beats}` → a `text_card` scene showing its title (also its `chapter`); a string is a
  beat; `{pause: S}` a silent scene. No new scene type. `vidgen direct` and the MCP YAML editors do
  not handle `sections:`. Problems are reported as `sections[i]` (`sections.section_location`;
  `.chapter` / `.params.text` → `.title`, `.duration` → `.pause`) for load errors (`section_error`)
  and later ones (`Project.attributed`, `Project.from_sections`, `Project.section_sources` §112.3).
  `vidgen schema`: the top level requires `title` and `oneOf` `scenes` / `sections`; variants cannot
  set `sections`.
- **Pauses**: `BeatConfig.pause` (0–60 s) and `- pause: S` items (`config.merge_pause_items`, merged
  into the beat before, before default ids) replace the gap after a beat (`SpokenLine.pause` in
  `beat_windows`; videos honour it too).
- **Story draft** `--audio` (`DraftOptions.audio`): sections with the voices, lines and emotions,
  the music bed, `audio: {normalize: true}` (`commented_yaml(list_key="sections")`).
- `chapter_warnings` is empty for `audio_only: true`.

### 111.1 Audio files (Step 284)

`audio_output` (`AudioOutputConfig`; keys: docs/CONFIG.md "Audio files"). `AudioOutputConfig.plain`
(48 kHz stereo 24-bit WAV, no preset, no room tone, no split: the default) copies `mix.wav` byte for
byte; anything else is one FFmpeg encode (`vidgen.audio_encode`): `pan=mono|c0=0.5*c0+0.5*c1`,
`aresample`, `pcm_s16le` / `pcm_s24le` (`-rf64 auto`), `libmp3lame` (CBR, ID3v2.3), `aac` in `ipod`
(faststart), `libopus` in Ogg (16 / 24 / 48 kHz only, else a config error); tags from `metadata`
(`chapter_export.video_tags`); written to `.part` then replaced. No embedded chapters. A missing
encoder gives the FFmpeg error plus "needs an ffmpeg with libmp3lame / libopus".

### 111.2 Loudness presets, the check, the voice leveller

- **Presets** (`vidgen.audio_check.PRESETS`, `LoudnessPreset`; numbers in docs/CONFIG.md):
  `podcast`, `audiobook` (ACX), `broadcast` (EBU R128), `custom` (`audio.target_lufs`,
  `audio.true_peak`), `drama` (§112.3). Audiobook RMS is unweighted over all samples and channels
  (`mix.rms_db`); its format and length items are notes, never failures. The audiobook preset fills
  `pacing` `lead_in: 0.6`, `tail: 2.5` where unset (`audio_only.effective_pacing`,
  `model_fields_set`).
- **Mix targets**: `audio_check.mix_targets` → `mix.MixTargets(lufs | rms, true_peak, mono,
  level_voice, room_tone)` → `mix_audio(..., targets=)`: a preset always normalises; with `mono` the
  LUFS target is raised by `DUAL_MONO_LU` (10·log10 2) so the encoded mono file measures the target;
  `room_tone` adds a fixed 10 s pink-noise loop (80 Hz–6 kHz, seed 111) after the gain, before the
  limiter. Report keys `levelled_db`, `target_rms`, `mono` only when set.
- **Leveller** (`audio.level_voice`, default `None`: on with `podcast` / `audiobook` / `drama`, off
  otherwise): voice 10 ms frame peaks (`mix.frame_peaks`) → `leveller_gain` (threshold = median
  peak of frames within 45 dB of the loudest + 8 dB, ratio 3, 6 dB soft knee, `smooth_steps` over 5
  frames) → `LevelledTrack.read`. Music and effects are not levelled.
- **Check** (`measure_file`): one FFmpeg run, `ebur128=peak=true+sample` plus decoded 48 kHz samples
  on stdout → per-10 ms power only. `check(measured, preset)` → `PresetResult` of `CheckItem(name,
  value, target, status: pass | fail | note)`. A render with a preset measures its file, warns on
  misses, records `audio_output: {file, check}` in `timings.json` (`render --json` `check`). CLI
  `vidgen audio check FILE|PROJECT [--preset] [--lufs --true-peak] [--variant --preview --draft
  --output-dir] [--json]` (exit 1 on failure); MCP `audio_check` (read-only).

### 111.3 Transcripts

`audio_output.transcripts` (default all), next to the file (`vidgen.transcripts`): `_transcript.txt`
(`plain_text`: title, `[M:SS] Title` per chapter but the intro, a paragraph per voice turn, `Name:`
when more than one voice, base voice `Narrator`); `.srt` / `.vtt` from `render.pipeline.video_cues`
(names per `subtitles.speakers`; `vtt_text` escapes `&`, `<`, `>` and drops blank lines);
`_chapters.txt` via `write_chapter_list(..., warn=False)`.

### 111.4 Stereo staging and rooms (Step 285)

Opt-in, videos and audio-only (`vidgen.staging`; keys: docs/CONFIG.md "Stereo staging and rooms").
Applied in the mix to each beat's voice after its overlap shape (`audio_only._voice_samples`,
`scene.add_narration`), never to the MP3s: `pan` is a display field (`voices.DISPLAY_FIELDS`: not in
`audio_fields`, not inherited by named voices), so nothing is re-voiced.

- **Pan**: `PanSetting` (−1…1 or `POSITIONS`) on `voice:`, `voices.<n>`, a beat (`PanMove {from,
  to}`, raised cosine over the line's sound). Equal-power law (`sfx.stereo`; centre = both channels
  at full level, so a centred dry voice is bit-identical). `beat_staging(config, scene, beat,
  stage)`: the beat's pan, else `stage`, else its voice's. `audio.follow_stage`: a video asks
  `NarratedScene.speaker_pan(beat)` (default `None`; `StageScene`: mean x of `beat_speakers` as the
  line starts); audio-only reads the stage's `characters:` `at` (`params_stage_pan`, `mark_x`).
- **Rooms**: `RoomName` / `RoomConfig {use, amount 0–2, narrator}` on a scene / section or
  `audio.room`; the base voice stays dry unless `narrator`; a scene's `none` cancels the default.
  `ROOM_PRESETS`: early reflections (panned with the voice) plus a per-channel IR (`reverb_ir`,
  cached; seeded noise, seed 1110 + 7·index + channel; two bands split at 2 kHz decaying by `rt60` /
  `rt60_high`; unit energy × `wet_db`), FFT-convolved, not panned. `phone`: 300–3400 Hz band,
  tanh saturation, RMS-matched. A tail past the scene's end (video: last beat window; audio-only:
  file end) fades over 0.25 s.
- **Width**: `audio.music_width` / `ambience_width` (0–2) scale the side signal in `MusicTrack.read`
  (`staging.widen`; 1 returns the block itself).
- **Mono compatibility**: `measure_file` keeps per 10 ms L², R², L·R; `mono_check` →
  `PresetResult("mono")`: correlation ≥ 0, worst 1 s window ≥ −0.3, fold ≤ 3.5 dB. `audio check`
  appends it for stereo files (`--mono` makes it set the exit code); an audio-only render with
  staging (`uses_staging`) and stereo output records `timings["stereo"]` (`render --json` `stereo`).
- **Unset = unchanged**: `staging.plain` skips processing; the scene fingerprint adds `staging` only
  when a beat is staged or `follow_stage` is on a stage. `NarratedScene.speaker_pan` may be
  overridden by a scene type.

### 111.5 Review (Step 286)

Folded into §111–§111.4.

## 112. Dramatized audiobooks: sound design, music cues, delivery (Phase AG, Steps 288–291)

Radio plays rendered audio-only, Kokoro local only. User docs: docs/COOKBOOK-AUDIODRAMA.md,
docs/CONFIG.md "Sound design", "Music for dramas", "Delivering an audio drama". Everything is
opt-in: unset, video mixes and audio-only renders are byte-identical to renders without it.

### 112.1 Sound design (Step 288)

`vidgen.sound_design` (no manim) times everything in audio seconds from a `SceneSlot` (`spec`,
`start`, `duration`, `beats: [BeatSlot(beat, start, end, body)]`). The audio-only planner
(`audio_only._design_sound`; returns at once when nothing is set) and the video join
(`pipeline._add_designed_ambience`, scene and beat `ambience` only) share it.

- **Beds** (`AmbienceSetting` on a scene / section / pause: a bed, a list, `AmbienceConfig {beds,
  gain, width}`, or `false`; `AmbienceBedName` = `ambience.AMBIENCE_BEDS`, kept equal by a test).
  `ambience_entries`: at a change, beds whose `(gain, width)` differs or that are not wanted fade
  out and new ones fade in over `audio.ambience_crossfade` (2 s, min `MIN_FADE` 0.05) centred on
  the change; unchanged beds play on. Beat changes `AmbienceChange {start, stop, at (fraction |
  "@word" | end), fade, gain}` (word checked at load; times from `word_anchors.beat_words`). Each
  piece is a timings `ambience` entry with `fade_in` (how `ambience.designed_entries` picks them;
  `ambience_spans` skips them), placed as is by `mix.plan_ambience`. The scene fingerprint excludes
  scene / beat `ambience` (mixed at the join).
- **Cues**: `SfxCue` / `sfx` action `repeat` (1–100), `every`, `room` (`True` scene room, a
  `RoomName`, `False` / `none` dry; `None` → `audio.sfx_room`, default false), named `pan` positions,
  a repeated cue's `PanMove` (`staging.repeat_pans`). `sfx.repeated` gives each play (footsteps
  alternate, `cartoon.foley.FEET`). `SfxEvent.room` (timings `room` only when set) makes
  `sfx.placed` run the sound through `staging.stage_voice`; `staging.cue_room` resolves it.
  `NarratedScene.sfx(..., repeat, every, room)` in videos.
- **Scene sounds without pictures** (`audio.scene_sounds`, audio-only, default false):
  `stage_sounds` gives the set beds as `ambience.set_ambience` chooses them and, on a plain stage
  (no `level`, no `iso`), foley for `walk_to` / `run_to` / `enter` / `exit` (`_Walker` follows each
  character's x via `mark_x`; `cartoon.foley.foley_cues`, `walk_seconds`), doors (`door_cues`),
  `knock`, `switch_on/off`, `jump`, surprised `emote` / `react`, `effect` (`EFFECT_SOUNDS`); first-beat
  actions wait `STAGE_ENTRANCE`. Level / iso moves, vehicles, thrown props, pours, lightning,
  alarms, fires, phones stay left out (named). `clip_sound`: a `video_clip`'s sound via
  `clips.clip_audio` (0.25 under narration), mixed into `voice.wav` (`write_voice_track(clips=)`).

### 112.2 Music cues for drama (Step 289)

`vidgen.scoring` (no manim); `mix.plan_score` places its pieces beside the `music:` cues
(`Placement` with `theme` / `motif`) from the timings alone, so audio-only and the video join share
it (no re-render: `score` and beat `motif` are out of the scene fingerprint, like scene `music`).
Returns at once with no scene theme and no motif.

- **Config**: `score: ScoreConfig {themes, crossfade 3, curve equal_power | linear | smooth, duck
  (default `drama`), fade_in 2, fade_out 4, motif_dip 6, sting_dip 4, check (None: on when themes
  play), dense_lu 15}`; `MusicTheme(ThemeVariation) {source, volume}`, `ThemeVariation {section,
  start, transpose ±12, tempo, tracks}`. Scene `music` takes a name (`SceneMusic` before-validator
  → `{theme}`) or `{theme, variation, volume}`. `BeatConfig.motif: MotifCue {theme, at, length 6,
  fade_in 1, fade_out 2.5, gain, dip, variation}`; `StingCue.at` takes a word anchor (`placed_at`);
  words checked at load. The visual `ThemeConfig` keeps its name; the music one is `MusicTheme`.
- **Ducking presets** `DUCK_PRESETS` / `DuckPreset`: `light`, `standard`, `drama`, `deep`; a
  `DuckConfig` before-validator expands a string or `{preset, ...}` (given keys win). `swell` (dB,
  default 0): `mix.duck_gain_db` = `duck_curve` + `swell × (1 + duck_curve at depth 1)`; with 0
  exactly `duck_curve`.
- **Scene themes** (`theme_pieces`): sticky (a scene without a theme, or a pause section, keeps the
  one playing; `music: false` ends it). At a change the old piece fades out and the new fades in over
  `crossfade`, centred on the change (min 0.05 s); the same `ThemePlay` plays on. `fade_shape`
  equal_power = sin(πu/2). A piece starts its source from its top (or `section` / `start`). Gain =
  `10^(volume/20) × envelope × scene curve × ducking (speech + clip spans) × dips`.
- **Motifs** (`motif_pieces`): placed by `at` (word offsets via `sound_design.word_offset`, shared
  with ambience and stings). `dip_curve`: themes dip by the deepest motif `dip × envelope` and each
  sting's `sting_dip`.
- **Sources** (`theme_source`): no note change → `music.Source` of a looping cue; with `transpose` /
  `tempo` / `tracks` (or a section of a Python-made bed) the score is re-rendered from a project
  piece, a score bed's file or its template (`studio/beds/<bed>.yaml`) by `variant_score` (tempo set
  in the YAML, listed tracks kept, pitched tracks transposed), at the music level, cached as
  `build/music/theme-<key>.npy` (key: `piece_key`, variation, `VARIATION_VERSION`).
  `theme_problems` (in `music.config_problems`): unknown theme (did-you-mean), missing source, a
  variation of an audio file, unknown track or section.
- **Check** (`dense_dialogue_check`, `MixReport.music_check`, `timings.mix.music_check` only when
  measured): 100 ms K-weighted frames of voice vs music placements (no ambience, pre-gain); dense =
  a 5 s window ≥ 80 % speech; runs ≥ 2 s `{start, end, lu}`; `under_dialogue_lu`, `in_pauses_lu`;
  `ok` when every dense run ≥ `dense_lu`; a warning names the worst runs.

### 112.3 Delivery (Step 290)

`vidgen.delivery` (no manim); `audio_check` has `drama`; `mix` writes split parts.

- **`drama` preset**: podcast loudness, `level_voice` on, plus `max_lra` 10 LU
  (`LoudnessPreset.max_lra`) and `dialogue` checks; no noise-floor / head / tail gate.
  `MixTargets.music_check` runs `_check_music` for any music (`score.check: false` turns it off).
  `measure_file(path, momentary=True)` parses ebur128 `framelog=info` momentary values
  (`parse_momentary`, off by default); `line_loudness` gates 400 ms blocks inside a line at −70 LUFS
  then 10 LU under their mean. Lines (`DialogueLine`, `delivery.dialogue`, `speech_bounds`) ≥
  `MIN_LINE` 0.8 s: 10–90th percentile spread ≤ `LINE_SPREAD_LU` 6; speakers within
  `VOICE_SPREAD_LU` 4; music `under_dialogue_lu` and worst dense run ≥ `score.dense_lu`. Without a
  project the dialogue item is a note.
- **Split** (`audio_output.split: chapters`): `plan_parts`, one part per chapter mark (the first
  from 0, so a cold open joins it; none: one part). Cut before chapter k = `max(min(scene start,
  first speech − pacing.lead_in), (previous speech end + first speech)/2)`; fades in ≤
  `PART_FADE_IN` 0.3 s, out ≤ `PART_FADE_OUT` 2 s (none at the audio's own ends). `mix_audio(parts=)`
  writes the whole, then each part from the same pre-limiter `read`, normalised on its own to the
  whole's target (`MixReport.parts`). `write_parts` → `<output>_<NN>_<slug>.<ext>` (`title`
  "Title: Chapter", `album`, `track` "k/n") with per-file transcripts (`part_timings`) and
  `<output>.m3u` (extended M3U, UTF-8; removes only files the previous playlist named and the new
  one does not). No single file or `_chapters.txt`. `files_check`: loudness within `FILE_SPREAD_LU`
  1, median line within `FILE_DIALOGUE_SPREAD_LU` 2. `vidgen audio check PROJECT` reads
  `timings.json` (`delivery.rendered_files`). `AudioRenderResult.files`; `output` is the playlist.
- **Credits and cold open** (`credits: CreditsConfig`, `cold_open: ID | [IDs]`, `[]` = none):
  `apply_delivery(data, origins)` on the raw config after `apply_cut` in `Project._load_config`
  (variants too; not in `parse_config`); returns the data object itself when unset. A scene id moves
  that scene first (drops `chapter`, `transition`); beat ids are deep-copied into a `text_card`
  scene `cold_open` (beats `cold_open_<id>`, source voice on the beat, only `sfx` actions, the first
  source scene's `room` / `ambience` / `music`). Credits append a `text_card` scene (`credit_lines`:
  title, "Starring A as X, …", "Narrated by N.", `lines`; actor from `voiced_by`, else a Kokoro id
  `xx_name` → Name; `music` default `main` when `score.themes` has it; English only). Errors:
  unknown id (did-you-mean), an existing `cold_open` / credits id. The scene fingerprint excludes
  `credits`, `cold_open`, `audio_output`.
- **Cold-open audio**: `delivery.cold_open_sources` maps `cold_open_<id>` → `<id>`;
  `tts.run.plan_tts` reuses the source MP3 (`plan.reuse`) when hashes match and the source is
  current or voiced this run (`_sources_first` orders it; `_copy_source` voices it otherwise).
  Alignments and visemes are read under the source id.
- **Section locations**: `delivery.scene_sources(data)` (section index, or `cold_open` / `credits`;
  `None` when nothing moves) feeds `sections.section_location(text, sources)`;
  `Project.section_sources` (set in `Project._load`, variant merged).
- **JSON**: `render --json` `files`; `audio check --json` `files`, `files_check`; `timings.json`
  `audio_output.{split, playlist, files, files_check}`, `mix.parts`.

### 112.4 Cookbook and review (Step 291)

`docs/COOKBOOK-AUDIODRAMA.md` (skeleton checked by `test_docs`). Review fixes are folded into §112.3.
## 113. Generated video shots through OpenRouter (Phase AH, Steps 292–297)

Video models make selected shots; vidgen keeps story, timing, text, captions, music, sound and
assembly. Opt-in through `videogen:` and per-beat `generated_shot:`; nothing changes for other
projects. Providers: `openrouter` (paid), `mock` (fake API), `comfyui` (§113.20). User side:
[docs/CONFIG.md](docs/CONFIG.md#generated-video-videogen-vidgen-generate),
[docs/COOKBOOK-3D-SCENE-TO-SEEDANCE.md](docs/COOKBOOK-3D-SCENE-TO-SEEDANCE.md),
[docs/COOKBOOK-RESTYLE-WITH-LTX-ON-COLAB.md](docs/COOKBOOK-RESTYLE-WITH-LTX-ON-COLAB.md).

### 113.1 API facts (checked 2026-11-07; no key used, nothing paid)

- `POST /api/v1/videos` `{model, prompt, duration, resolution | size, aspect_ratio, frame_images
  [{type: image_url, image_url: {url}, frame_type: first_frame | last_frame}], input_references
  [{type: image_url | audio_url | video_url, <type>: {url}}], generate_audio, seed,
  previous_job_id, provider {options.<slug>.parameters.<key>, ...}, ...}` → 202 `{id,
  polling_url, status}`. With both arrays, `frame_images` wins. `GET /api/v1/videos/{id}` →
  `{status: pending | in_progress | completed | failed | cancelled | expired, error, usage: {cost,
  is_byok}}`; vidgen downloads via `GET .../{id}/content?index=0`.
- `GET /api/v1/videos/models` (public; copy in `tests/data/openrouter_video_models.json`): per model
  supported resolutions / aspect ratios / sizes / durations / frame images, `generate_audio`,
  `seed`, `pricing_skus` (`duration_seconds_*`, `cents_per_*`, `video_tokens_*`, per-image,
  `minimum_*`, ...), `allowed_passthrough_parameters`; `null` = not listed. It is not filtered by
  the account's privacy settings; video is not ZDR-eligible (with "ZDR endpoints only" every video
  model is refused, HTTP 404).
- Pictures may be sent inline as data URLs; **audio / video must be https URLs** (inline: HTTP
  400). Audio / video references work only on providers that support them (Seedance 2+).
- OpenRouter checks its own worst-case cost before accepting a job (HTTP 402 even with credits
  above vidgen's estimate); vidgen cannot predict it.

### 113.2 The provider layer (Step 292)

- **Package** `vidgen.videogen` (in `NOT_RENDER_INPUTS`; `videogen` config outside fingerprints).
  `VideoRequest(model, prompt, duration, resolution | size, aspect_ratio, frame_images,
  references, seed, previous_job_id, provider_options, generate_audio, sheet, fps)` (checked:
  `author/name`, duration > 0, not both size and resolution, frame images need a frame type,
  references none). `MediaInput(kind: image | audio | video, path | url, frame_type)`.
  **Cache key**: `canonical_request` (cache version, every field, files by SHA-256 and size, never
  by name; `pictures_sent` §113.7; `sheet` / `fps` only when set) → `request_hash` (24 hex of
  SHA-256). `JobState(id, status, polling_url, cost, is_byok, error)`.
- **Models** (`models.py`): `load_catalog(refresh, cache_path, fetch, now, max_age=1 day) ->
  Catalog` from `<vidgen cache>/openrouter/video_models.json` when young, else fetched (no key) and
  cached; offline the cache at any age, else an error. `Catalog.find` with did-you-mean.
  `check_request(request, model) -> RequestCheck(problems, notes, drop)`: unlisted duration /
  resolution / size / aspect / frame type / passthrough → problem with a suggestion
  (`snap_duration`: shortest allowed ≥ wanted, else the longest); a setting the model lists
  nothing for → note and dropped; a seed on a model without one → dropped.
- **Estimates** (`estimate(request, model, duration=, minimum=True) -> Estimate(cost, basis)`):
  per-second SKUs × s; token SKUs × `W × H × 24 × s / 1024`, a `with_video_input` SKU counting
  `(1 + video references) ×` the output tokens; + per-picture SKUs; a `minimum_*` floor. SKU choice
  (`_applicable`): continuation only with `previous_job_id`, `reference_*` only with references,
  `with_video_input` only with a video reference, `image_to_video` vs `text_to_video` by frame
  images, the request's tier, audio SKUs following `generate_audio` (§113.11); then the
  **highest** remaining (conservative). No duration: the longest; no resolution: the highest tier.
  Nothing understood (e.g. `megapixel` SKUs) → `cost None`, and paying refuses.
- **Provider** (`openrouter.py`, `OpenRouterVideoProvider(key_via_proxy, uploader, transport,
  sleep, clock, environ, timeout 120, poll_interval 10, max_interval 60, poll_timeout 900, retries
  4)`): `submit` (one attempt, never retried; refuses a body > `MAX_INLINE_BYTES` 20 MiB before
  sending), `status`, `wait` (×1.5 per poll up to 60 s; past `poll_timeout` a VidgenError: the job
  keeps running, the next run polls it), `download` (atomic). Polls / downloads retry 429, 5xx,
  524, 529, unreachable. `media_url`: a url as is; a picture as a data URL; audio / video through
  `uploader(Path) -> url` (the quick tunnel, §115), else a VidgenError. Transport `(method, url,
  headers, body, timeout) -> Response` (urllib).
- **Key**: `OPENROUTER_API_KEY` read per request, sent only as `Authorization: Bearer`, scrubbed
  from errors (`httpapi.scrub`), never logged or stored. Proxy mode (`videogen.key_via_proxy` or
  `VIDGEN_OPENROUTER_KEY_VIA_PROXY=1|true|yes|on`): no header, no key; also for sheets' image
  provider.
- **Errors** (`http_error`, `job_failure`): 402, 429 (paid submits not retried), 413, 401 / 403,
  content-policy words (`is_policy_error`), 404, failed / cancelled / expired jobs.
- **Mock** (`mock.py`): `MockOpenRouter` transport and `MockVideoProvider` (`provider: mock`; job
  ids `mock-<8 hex>-N`, unique across runs); completed jobs return a playable MP4
  (`synthetic_clip`, also QA's test patterns; a tone with `generate_audio: true`).
- **Ledger** (`ledger.py`): `videogen-ledger.jsonl` (mock: `.mock.jsonl`, comfyui:
  `.comfyui.jsonl`), append-only, `fsync`ed: `{event: submit, job_id, provider, model,
  request_hash, estimate_usd, time}`, `{event: completed | failed | cancelled | expired, job_id,
  cost_usd, is_byok, time}`, intents (§113.10); an unreadable line is an error. `spent()` = reported
  cost, else the estimate (open, timed-out, unreported jobs and unresolved intents count).
  `refusal(budget, estimate, model)`: no cap, unknown estimate, estimate > remaining.
- **Run** (`run.py`): `plan_clip(...) -> ClipPlan`, `generate_clip(..., pay=False) -> ClipResult`.
  Order: cache hit `assets/generated_video/<hash>.mp4` → nothing sent; the ledger's last job of the
  hash open or completed → polled / downloaded, never resubmitted (`again=True` only after its
  output expired); model checks; estimate vs the cap (lower of `videogen.budget_usd` and
  `budget_usd=`); with `pay`: submit, wait, download, sidecar `<hash>.json` `{request, key,
  provider, job_id, estimate_usd, cost_usd, bytes, time}`.
- `videogen:` is its own section (not top-level `generate:`, the scenes' image param);
  `VideogenConfig` in `config.py`.
- **CLI** `vidgen generate models | ledger | plan | sheets | inputs | run | status | takes | pick |
  resolve | frames | subjects`. **Public** `vidgen.api`: `VideoRequest`, `MediaInput`,
  `generate_clip`, `plan_clip`.

### 113.3 Sheets, shot specs, inputs and the plan (Step 293)

- **Names**: `characters[].reference_sheet` (not `sheet`: `vidgen character-sheet` is the cartoon
  sheet), top-level `style_sheet:`, beat key `generated_shot:`. All outside scene fingerprints.
  Keys: [docs/CONFIG.md](docs/CONFIG.md#shots-sheets-and-inputs-generated_shot-reference_sheet-style_sheet).
  Views ⊂ `front | three_quarter | side | back`; `kind: talking | action | establishing`; a talking
  shot refuses `audio: none`; sheets need `approved: true` before any job uses them.
- **Sheets** (`videogen/sheets.py`): each picture an `ImageRequest` (`image_request`, style words
  `imagegen.style` + `style_sheet.words()`) at `assets/sheets/<owner>_<label>_<key>.png` + `.json`:
  one per view and per expression; `frames` style stills (frame n seed + n − 1). `Sheet.ready` =
  approved and all made. `run_sheets(pay=False)`: with `pay`, budget checked, then per picture a
  ledger `submit` (`image-<key>`) and `completed` / `failed`. An approved sheet with missing
  pictures is never remade (blocked until `approved: false`).
- **Shots** (`videogen/shots.py`, `project_shots(project, catalog)`): per beat with a spec, its
  window on the planned timeline. A beat longer than the model's longest is split into
  `ceil(window / longest)` equal parts `<beat>_p<n>`; each part's duration snaps up. Resolution:
  the spec's or the lowest; aspect: the spec's or the listed one nearest the format. Speaker: the
  character whose `voice` is the beat's. Inputs (`ShotInput`): first frame (sheet / render
  `build/videogen/<shot>/first_frame.png` / file / `last_of` / `painted` / `restyled`) as a frame
  image if the model lists `first_frame`, else a reference; refs (characters' sheets, `style`,
  files); `audio.mp3`; the guide. **Blocked** = planned and priced, not payable (sheet not ready,
  input not made or stale, no host, ...); **problems** refuse a paid run. `shot_problems` feeds
  `vidgen validate`.
- **Prompt** (`shot_prompt`): framing, setting, characters, the line (`line: false` omits it),
  guide sentence, style, "No on-screen text, captions, subtitles or logos." Prompt changes change
  keys, so wordings of paid shots are kept byte-identical where noted below.
- **Inputs** (`videogen/inputs.py`, `make_inputs(project, shots, guide=, render=)`): the voice cut
  from the beat's narration MP3 (offset, exact length, MP3 mono 44.1 kHz 128 kb/s); with `--guide`
  the scene rendered (draft, or final per `render_kind`) and cut silent H.264 from the beat's start
  + offset; its first frame past a fade in (≥ 0.7 × the brightest of the first 1.5 s).
- **Plan** (`plan_shots(project, ...) -> VideoGenPlan`): per shot the request, checks, estimate
  (via `plan_clip`, so a cached clip or earlier job is 0), budget left (cap − spent − sheets −
  shots before); sheets to make; totals; nothing sent or paid. `--pay` on plan / inputs is an
  error. **Public**: `plan_shots`, `project_shots`, `project_sheets`.

### 113.4 Takes in the film, QA and the workflow (Step 294)

- **Run** (`videogen/workflow.py`, `run_shots(project, pay=, ...) -> RunReport`): without `pay` a
  dry run. With `pay`, refused before any payment when there is no cap, a selected shot has
  problems (or stale inputs, an unresolved intent), or the ready shots exceed the budget left. Per
  shot: blocked → skipped; else `generate_clip` (ledger re-read per job) → `add_take`. The first
  `VidgenError` stops the run; no retry. `ShotRun.status`: `would_generate | cached | paid |
  downloaded | blocked | problems | failed`.
- **Takes** (`videogen/takes.py`): `takes/<shot>/<n>.mp4` + `<n>.json` `{shot, take, key, model,
  provider, job_id, cost_usd, source, length, time, qa, ...}` + `<n>.contact.png`; one take per
  cache key. Picks in `takes/picks.json` `{shot: n | "none"}` (not `video.yaml`: vidgen never
  rewrites the author's YAML). `chosen_take`: the pick; `none` → vidgen's picture; `auto` → the
  newest take without QA errors.
- **QA** (`videogen/qa.py`, `check_clip`): grey at 64 px wide, ≤ 30 fps. Warnings: short by > 1
  frame, aspect off > 2 %, upscaled > 2×, a black run ≥ 0.5 s (mean < 16, p99 < 40), frozen ≥ 1 s
  (mean change < 0.6), flicker > 3, a cut (> max(30, 6 × median)); all black or all frozen is an
  error; sound is info. `contact_sheet` (8 frames, PIL).
- **Placing** (`videogen/compose.py`, `scene_placements`): only when not a draft, `takes/` exists
  and a beat has `generated_shot.place: true`. Window = the beat's planned window relative to the
  scene (split parts share it equally); the scene's last beat holds its take to `Shot.scene_end`.
  Fades (`crossfade`, default `videogen.crossfade` 0.25 s) only against vidgen's picture: none at
  scene edges or between two takes.
- **In the render** (`vidgen/generated_layer.py`, `GeneratedLayer`; a render input): after the
  overlay layer in `NarratedScene.__init__`, so overlays and captions are drawn on the take. In a
  window the frame is `ClipReader(take, size, crop).frame(t − start)` (`cover` / `contain`; a short
  take holds its last frame); `color_gains` = (grey-world × exposure towards 118)^`color_match`
  (default 0.5), each in 0.8–1.25, from 8 frames at 32 px. The take's sound is never read. Timings
  get `generated: [{shot, take, model, start, length}]`.
- **Fingerprint**: a scene gains `generated` (per placement: take path, size, mtime, start, length,
  fit, fades, colour match, `match_join` when true) only when it shows takes; `generated_shot` keys
  stay outside; `assets/generated_video/` is left out of the `assets` digest.
- **Disclosure**: `credit_line(project)` = "Includes AI-generated footage (<models, sorted>)." appended to
  `<output>_chapters.txt`; lint `generated_footage` (scene, info) on each scene with takes.
- `--pay` only on `run` and `sheets`. **MCP**: `generate_plan`, `generate_run` (`dry_run` default
  true; `dry_run: false` needs `confirm_cost: true`), `generate_status`, `generate_takes`,
  `generate_pick`. **Public**: `run_shots`, `check_clip`, `scene_placements`.

### 113.5 Review of Steps 292–294

Invariants: nothing is paid without `--pay` (or the MCP's two flags) and a cap; the cap is checked
against conservative estimates per job and per run up front; the ledger records a job (and before
that its intent) before polling, so a crash never pays twice; cache and open jobs stop repeat
payments; the key is never logged or stored; placing takes is invisible to projects without them.
Known limits: QA thresholds are from synthetic clips; layout lint still reads objects under a take;
`assets/sheets/` counts as assets (scenes may use them), so new sheets re-render every scene once.

### 113.6 Cleaner sheet prompts and real image costs (Step 295)

- **Character pictures** (`sheets.py`: `CHARACTER_SETUP`, `BACKDROP`, `WHO`, `VIEW_WORDS`): one
  full-body person on a plain light-grey studio backdrop, neutral, empty hands, "No props";
  expressions head and shoulders. Exclusions go in the request's `negative` (`CHARACTER_EXCLUDE`,
  `FRAME_EXCLUDE`, merged with `imagegen.negative`), sent as "Avoid: ..." in the prompt
  (`compose_prompt`): OpenRouter's `/images` has no negative field.
- **Look words** (`_look_words`): palette as "colours only, not objects", era. Character pictures
  drop shot-only words (`_SHOT_ONLY`: lens, camera, framing, lighting clauses) and never take
  `style_sheet.lens`; style frames keep the whole look and ask for no writing.
- **Costs**: sidecars and sheet ledger events carry `cost_source: reported` (response
  `usage.cost`) or `estimate`; `usage` fields are kept; printed via `imagegen.run.cost_words`. The
  pre-payment check uses the estimate. Reported cost can exceed what the account is billed.

### 113.7 What the API accepted, and smaller pictures (Step 296)

- **Smaller pictures** (`videogen/pictures.py`): `sendable_picture` keeps a JPEG / WebP whose long
  side ≤ `PICTURE_MAX_SIDE` 1280, else a resized copy (LANCZOS; JPEG `JPEG_QUALITY` 90, PNG with
  transparency) at `build/videogen/pictures/<sha256 of source, 24 hex>_<max side>.jpg|.png`;
  sources never change. `sendable_request` swaps every local picture; `generate_clip` submits it.
  The key uses the sources plus `pictures_sent: {max_side, jpeg_quality}` (a new rule → new key; a
  new Pillow → same key).
- **Size in the plan**: `openrouter.request_bytes` (audio / video counted as URLs) per ready,
  uncached shot; over `MAX_INLINE_BYTES` is a problem.
- **Inline audio / video**: under `inline_media: all` without a host such a shot has
  `shots.INLINE_AUDIO_VIDEO_PROBLEM`; under `images` it is blocked until hosted (`videogen.host:
  quick_tunnel`, §115). The provider never sends audio / video inline.

### 113.8 A 3D scene's guide pass as a shot's guide (Step 307)

- **Config**: `generated_shot.guide: true | false | render | final | canny | depth | outline | mask`
  (`GuideChoice`, `GUIDE_CHOICES`; `true` = `render`, the silent draft render;
  `GeneratedShot.guide_source`). A before-validator gives did-you-mean; boolean words stay
  booleans. Passes (`depth`, `outline`, `mask`) need `type: 3d` (`depth` also `space` / `web`,
  §113.19); `GUIDES_OF_ANY_SCENE` = none, `render`, `final`, `canny`. A wrong scene type is a
  load-time `VidgenError`.
- **Input**: `build/videogen/<shot>/guide.<pass>.mp4` (`guide_name`; render: `guide.mp4`), a
  `video` input like the render (sharing, blocking as usual).
- **Prompt**: one sentence per guide (`GUIDE_PROMPTS`) after the line; mask adds "Mask colours:
  <name> #rrggbb, ..." for 1 to `MASK_NAMES_MAX` 4 stand-ins (from `passes.mask_colors`). No sentence
  for `render`. The choice reaches the key through the file and the sentence; no extra field.
- **Cut** (`inputs.py`): `make_inputs` asks `render(project, scene, passes, kind) -> SceneRender`
  once per scene; `_render_scene` reuses the render while `current_render(..., guide_passes=)`
  holds, else `render_scenes(..., guide_passes=)` (worker `--guide-passes`; 3D clips reused). A 3D
  pass `<draft render_dir>/three_d/<scene>.<pass>.mkv` is cut like the render guide by `cut_pass`:
  H.264, `yuv420p`, BT.709 limited range, `PASS_CRF` 12. Missing pass file → `VidgenError`.
- **First frame**: `first_frame: render` is always the normal render's frame (a flat picture would
  steer the look); a pass guide alone writes no `first_frame.png` / `guide.mp4`.

### 113.9 Cut inputs that no longer match their sources (Step 308)

- **Record** (`videogen/freshness.py`): `make_inputs` writes `build/videogen/<shot>/inputs.json`
  `{version, inputs: {<file>: {sha256, source}}}` (merged; never shared). Voice source:
  `narration_sha256`, `offset`, `length`. Render inputs: the scene fingerprint of the project that
  drew it (draft, or `without_takes()` for `final`), `draft` `[w, h, fps]` (outside the
  fingerprint), `guide` kind, `offset`, `length`; plus per-kind fields (opening picture, canny,
  restyle, last_of, sheet, mix: §113.13–§113.24).
- **Check** (`InputSources.stale`, in `plan_shots`; free, offline): missing entry, other source or
  hash, or a voice whose `.hash` no longer matches (`tts.cache.audio_status`; asks for `vidgen tts`;
  an MP3 without `.hash` is the owner's and current). Anything in the fingerprint marks every
  render input of the scene; picks and `generated_shot` edits do not (the latter change the key).
- **Result**: blocked "inputs changed since they were cut (...): run `vidgen generate inputs[
  --guide][ --variant V]` (free) before paying" (`ShotPlan.changed_inputs`); `run_shots(pay=True)`
  refuses the whole run on such a shot. A shot whose exact request is cached or has an earlier job
  is not blocked (note only). Variants share `build/videogen/<shot>/`. False alarms (new assets, a
  vidgen upgrade) err on the safe side. `generate status` does not show this block.

### 113.10 Submits with no known outcome (Step 309)

- **Intent first**: just before the POST (body built, size checked) `on_sending` →
  `Ledger.record_intent` writes `submit_intent {intent_id, provider, model, request_hash,
  estimate_usd}`. The `submit` line carries `intent_id`; an answer meaning no job (`SubmitRefused`:
  4xx except 408) appends `intent_resolved {outcome: refused}`; anything else leaves it unresolved.
- **Re-run**: `ClipPlan.unresolved_intent` → `ledger.intent_refusal` (not bypassed by
  `again=True`); the shot is blocked with no new cost; `run_shots(pay=True)` refuses the whole run
  on a selected shot with one. Unresolved intents (also orphans) count at their estimate in
  `spent`.
- **Way out**: `vidgen generate resolve [PROJECT] --intent ID --not-charged | --job JOB_ID |
  --charged [--cost USD]` (`Ledger.resolve_intent`): frees the budget / writes a `submit` line so
  the next run downloads that job / keeps it counted. Refused: unknown id, already resolved, a job
  id already in the ledger. Shown by `generate ledger | plan | status` (JSON `intents`,
  `unresolved_intents`). `run_sheets` writes `submit` before each picture, with no intent.

### 113.11 The model's own sound, and video references in token estimates (Step 312)

- **Setting** (`SoundChoice` `mix` | `model`): `generated_shot.sound` > `videogen.models.<id>.sound`
  > `videogen.sound` (default `mix`); `VideogenConfig.sound_for`. An unlisted `videogen.models` id
  is a plan warning.
- **Request**: `generate_audio` (`mix` = false, the form of all earlier keys; `model` → new key).
  A model listing `generate_audio` false blocks a `model` shot; unknown is a note. Prices: `mix`
  keeps `without_audio`; `model` drops it and prefers `with_audio`.
- **In a film**: a placed take always plays vidgen's mix. To hear the model's sound: `place:
  false` and the take in a `video_clip` scene (volume 1, or `UNDER_NARRATION` 0.25 under
  narration). Seedance re-performs a reference voice (drift up to ~0.9 s), so the voice file
  cannot be laid over the clip. A line with `sound: model` and no voice input gets a note.
- **QA** (`check_clip(..., sound=)`): sound is info; `sound: model` with a silent clip warns.

### 113.12 Guided shots leave the framing to the guide (Step 313)

A shot **has a guide** when `guide_source` is not `None` (also `render`).

- **Talking wording** (`shots.GUIDED_TALKING_FRAMING`): `{who}, speaking` (no close-up, no facing
  the camera).
- **Sheet words** (`shots.without_framing`, only in a guided shot's `Characters:` text): in
  sentences of `reference_sheet.prompt` + `.notes` with a `_FRAMING_WORDS` clause, framing clauses
  and adjacent `_SHEET_ONLY_CLAUSE`s go; other sentences stay byte for byte; a clause with
  `_APPEARANCE_WORDS` is never removed. Sheet prompts, notes, `prompt`, `setting` and style are
  never edited (sheet keys stay). The plan notes what was left out (`_left_out_notes`).
- **Unguided shots**: `_prompt_text(guided=False)`, byte-identical to before.
- **Paid under the earlier wording** (`Shot.earlier_prompt`, `_paid_under_earlier_wording`): a clip,
  take or open / completed job under the old key and none under the new → blocked
  (`EARLIER_WORDING_BLOCKED`); a new `seed:` or `prompt:` pays for the new wording.

### 113.13 The starting picture in the guide, and what the provider really downloaded (Step 316)

Seedance with `frame_images` plus `input_references` runs first-frame only and ignores the
references, silently; with the picture spliced into the guide and no frame image it uses them.

- **Setting** (`FirstFrameIn` `frame` | `guide`): `generated_shot.first_frame_in` >
  `videogen.models.<id>.first_frame_in` > `videogen.first_frame_in` (default `frame`);
  `first_frame_in_for`. With `guide` the shot needs a guide and a starting picture (else a
  problem); `Shot.opening_picture` is set, no frame image sent, the picture stays usable as a
  reference; input `guide[.<pass>].opening.mp4` (`guide_name(kind, opening=True)`).
- **Combined guide** (`inputs.make_opening_guide`): `xfade` of the picture (cover crop) into the
  plain guide, `-t` its length (never longer); dissolve `videogen.first_frame_dissolve` (0.4 s).
  Recorded `opening_picture_sha256`, `opening_dissolve` (`freshness._change`).
- **Role sentence** (`shots._guide_opening_sentences`, `models.GUIDE_OPENING_TEMPLATES` by id
  prefix; Seedance): "{video} opens on the exact starting picture ..." and who each `@imageN` /
  `@audioN` is, numbered per kind in send order. Other shots keep prompts and keys.
- **Block** (`models.known_first_frame_with_references`, `shots._first_frame_with_references_problem`):
  a true first frame plus references on `bytedance/seedance-*` is a problem naming `first_frame_in:
  guide` (a note when paid already); `videogen.models.<id>.first_frame_with_references: true`
  overrides; unknown models are never blocked.
- **Downloads** (`run.unfetched_warnings`): hosted files (`host.files`) not fetched by a `GET` < 400
  in the tunnel's `host_fetch` events are a warning (`ClipResult.warnings`, take
  `info["warnings"]`), naming the input, never an address.

### 113.14 One shot after another: last_of, hard cuts, the opening match, the overlay (Step 317)

- **`first_frame: last_of:<shot>`** (`GeneratedShot.last_of_shot`; a beat id = its last part;
  `shots._link_last_of` after all shots exist): unknown, self and cycles are problems; a source
  without a shown take blocks (so one `run --pay` pays the source, never both). Picture
  `build/videogen/<shot>/last_of.<source>.<take>.png` (`inputs.last_frame`: `-sseof -0.5 -update 1
  -vsync 0`), recorded; another shown take makes it stale (`freshness._last_of_moved`);
  `run_shots` skips a shot whose source's take changed mid-run.
- **Hard cut**: `video_clip` `fade: false`; `NarratedScene.outro_seconds(params)` (overridable
  classmethod) is read by the scene and `videoplan.scene_outro`, so plan and render agree.
- **Opening match** (`qa.opening_similarity`): SSIM of the clip's first frame vs
  `Shot.starting_picture` (grey, 320 px, 8 px windows every 4 px, better of crop and stretch) in
  the take's `qa` metrics; warning under `OPENING_WARNING` 0.7.
- **Overlay** (`inputs.make_overlay`, `overlay.png`): the starting picture 50 % over the guide's
  first frame; never sent, not recorded.

### 113.15 Painted starting pictures, file reference labels and the last-frame overlay (Step 319)

- **`vidgen generate frames`** (`videogen.frames.run_frames`): `paint_first_frame: {prompt, refs,
  seed, model (default bytedance-seed/seedream-4.5), resolution (2K)}` (`config.PaintFirstFrame`).
  The layout `build/videogen/<shot>/layout.png` (first frame of the draft render, free) is the first
  input; the prompt starts with `frames.LAYOUT_INSTRUCTION`; references go in OpenRouter's image
  `input_references` (`check_request` refuses a model without it or above its `max`). Fixed
  `ImagegenConfig(provider="openrouter")`, so the project's `imagegen:` does not apply. Key
  `sha1(base request key | SHA-256 of layout and each reference)`; file `assets/frames/<shot>_<key>.png`
  + `.json`. Paid through `sheets.pay_for_pictures` (budget, known price, `image-<key>` ledger
  lines, `retries=0`). `first_frame: painted` → `frames.painted_picture`; missing → blocked.
- **File labels**: `refs` items may be `{file, shows}` (`config.FileRef`); `shows` naming a character
  sets `ShotInput.owner`, else `ShotInput.shows`. Without `shows` prompts are unchanged.
- **Last-frame overlay**: `overlay.last.png` (`make_overlay(at_end=True)`), never sent.

### 113.16 Splitting a sheet into panels and joining takes (Step 319)

- **`vidgen split-sheet`** (`videogen.split_sheet`, no project): ffmpeg `crop` (+ `scale` lanczos
  with `--scale`); `--columns/--rows/--gap` must give whole pixels; `--box X,Y,W,H` repeats.
- **Assembly** (recipe): a `film.yaml` of `video_clip` scenes with `path: takes/<shot>/<n>.mp4`,
  `region: bleed`, `fade: false`, no beats, `duration:` the take's; `place: false` on the shots.

### 113.17 Readable overlays, the film's disclosure, faster music list, the shot-with-a-line note (Step 321)

- Overlays are enlarged to `OVERLAY_LONG_SIDE` 1600 px; `at_end` marks where the guide changed
  between first and last frame (`changed_mask`: ≥ `CHANGE_LEVELS` 6, nothing if more than
  `MAX_CHANGED_SHARE` 0.6 changed) with a magenta ring (`OUTLINE_REACH` 7 px).
- `compose.clip_takes` finds `video_clip` scenes showing `takes/<shot>/<n>.mp4`; `credit_line` and
  `generated_footage` count them.
- `vidgen list-music` text output comes from `Bed` entries without synthesis (`--json`,
  `--render-dir` still synthesise).
- A config without beats reports no orphaned MP3s. A beat lasts its voice plus `pause:`, or plus
  `narration.pad` when there is no `pause:` (never both).

### 113.18 The finished render and the film's sound as references (Step 402)

- **`guide: final`** (any scene type): cut from the scene's **finished** render at the video's size
  and fps (`guide.final.mp4`), never the draft, showing neither overlays nor placed takes:
  `Project.without_takes()` (no overlays, `takes_shown` false) renders into
  `build/<final|preview>[_<variant>]_source` (worker `--source`); `inputs.render_project(project,
  "final", scene)` uses the film's own project when `references.draws_overlays` is false and no take
  is placed in the scene (one shared render). Freshness always records the `without_takes()`
  fingerprint, so placing a take does not stale its guide.
- **`audio: mix`** (`audio_source`: `beat` | `mix` | `none`): `audio.mp3` cut from the rendered
  film at the beat's start in `build/final/timings.json` + offset (the film's own mix); talking
  shots refuse it. Record `freshness.mix_source`: film name, size, mtime, start, length.
- **Prompt**: `GUIDE_PROMPTS["final"]` (keep layout, framing, motion, timing; remake as real
  footage), `MIX_PROMPT`; with `first_frame_in: guide` the Seedance template's `opens_final` /
  `soundtrack` sentences.

### 113.19 A web scene's exact depth (Step 403b)

`guide: depth` on `space` / `web` scenes (`GUIDES_OF_WEB_SCENES`, `scene_draws_guide`) uses the
depth three.js drew.

- **Drawn by the scene's own shaders** (vertex-displaced geometry survives): with `ctx.draw_mode`
  `"depth"` (`WebPage(draw_mode=)`, in the clip's inputs only when set) `vidgen/three-finish`'s
  `Finish.render(t)` draws the frame as for `t` (no motion blur) and replaces the chain by
  `DEPTH_PACK`: view distance z packed as `n = 1 + round(u (2^24 − 2))`, `u = (log2 z + 16) / 48`
  (`DEPTH_LOG`) in RGB, `n = 0` where depth stayed cleared (sky); sampled through the lens
  distortion, no post effects. A page that draws no depth frame
  (`globalThis.__vidgenDepthFrames`) is refused at frame 0 ("guide: depth needs the page to draw
  through vidgen/three-finish"); a page with its own composer draws its depth frames through `new
  Finish(renderer, scene, camera, ctx).render(t)`.
- **Lossless**: `<render_dir>/web/<scene>.depth.mkv` (+ `.json`; FFV1, never `compact`).
  `pipeline.scene_pass_clips` names a scene's pass clips by type.
- **From the finished render** (`inputs.render_kind`): web passes from `final`, `3d` passes from the
  draft.
- **Grey** (`web.depth.cut_depth`): one range per shot (per frame flickers): `near` = distance
  within which the nearest 1 % of drawn pixels lie (log2 histogram, 64 bins / octave); grey =
  `near / z` clipped (1/z fades smoothly to the horizon, like depth estimators), H.264 BT.709 CRF
  12.
- **Gap**: a scene drawn in depth slices (`vidgen/space-scale` `depth: split`, default) holds only
  the nearest slice.

### 113.20 The `comfyui` video provider (Step 409)

`videogen.provider: comfyui` runs vidgen's own workflows on a ComfyUI server; no money is paid.

- **Config**: `videogen.comfyui` (`ComfyuiSettings`): exactly one of `colab: <session>` or `url:`;
  `units_per_hour` 1.94; `text_encoder: cpu | gpu` (default cpu: node 3 `DualCLIPLoader` gets
  `device: cpu`). The `colab:` route is the command's `--via` (ssh default, exec), never in
  `video.yaml`. A `model:` may be a workflow id.
- **Workflows** (`videogen/comfyui.py`, `Workflow`, `WORKFLOWS`): `controls`, optional first frame,
  `short_side` 512, `size_step` 64 (16:9 → 960x512), `8k+1` frames ≤ `max_frames` 121, `fps_choices`
  (12, 24), stored at 24. `record()` makes a `VideoModel`, listed with OpenRouter's;
  `check_workflow_request` (one control, no last frame; references and audio are notes) and
  `workflow_estimate` ($0). Workflow / provider mismatch is a plan problem. The LTX graph is
  `videogen/ltx_graph.py` (stdlib only; `tools/colab/build_workflow.py` loads it by path).
  `sound: mix` drops the audio decode.
- **Fitting** (`prepare_job`): `fit_control` covers the size (centre crop), resamples to the
  generation rate, cuts or holds to the frame count; `fit_picture` for the first frame (else a
  bypassed placeholder). Files `vidgen_<request key>_control.mp4` / `_first.png`. Clips are kept as
  made and trimmed when placed.
- **Transports**: `comfyui_client.py` (stdlib, no vidgen imports: ComfyUI's API, `run_job(job.json)`).
  `HttpTransport` in process. `ColabTransport` uploads one archive (job, fitted inputs, the client)
  over ssh (`vidgen.colab_ssh`; exec: `vidgen.colab_transfer`), unpacks to
  `/content/vidgen-comfyui/<job id>`, runs the client detached via `colab_vm.py`, downloads
  `output.mp4`. On the VM (marker `/content/.vidgen_setup_vidgen_done`) `colab:` means
  `HttpTransport(127.0.0.1:8188)`. `vidgen remote`'s bring-back includes `build/*/web/*.json` (the
  fingerprint reads them); `colab*.py`, `remote.py` are in `NOT_RENDER_INPUTS`.
- **Provider**: `ComfyUIVideoProvider` has the OpenRouter interface: same request key, cache, takes,
  ledger `videogen-ledger.comfyui.jsonl` (cost 0). `--pay` still starts the work; a $0 estimate needs
  no budget. A failure before ComfyUI queued the job is a refused submit. `usage` (`gpu_seconds`,
  `compute_units` = s × `units_per_hour` / 3600, `server`) goes to the sidecar and take.

### 113.21 The canny guide and the restyled first frame (Step 410)

- **`guide: canny`**: `render_kind` `final`; first frame `first_frame.png`. `videogen/canny.py`
  re-implements OpenCV's `Canny` in numpy + scipy (OpenCV is not a dependency; same edges as
  `cv2.Canny`), no blur, then a glint mask (41 px Gaussian of grey ≤ `glint`, feathered 31 px);
  frames through ffmpeg pipes. `GeneratedShot.canny` (`CannyGuide`: `low` 92, `high` 200, `glint`
  150 | false). Size `inputs.guide_size` (the workflow's size, else 512 short side). Freshness: the
  `final` source plus `canny`, `canny_size`.
- **`first_frame: restyled`** (`RESTYLED_FIRST_FRAME`; needs `comfyui` and a workflow model):
  `make_inputs` cuts `first_frame.png`, then `comfyui.restyle_picture` runs `qwen_graph.qwen_graph`
  (frame at 1.5 × `guide_size` as its own reference latent, output at `guide_size`) through the clip
  transport; job fields `PreparedJob.output` (`output.png`) and `free_after` (`POST /free` after).
  Result `first_frame.restyled.png`; record: source, `first_frame_sha256`, `restyle` (prompt, seed,
  size, model), `usage`; kept while it matches (`freshness.recorded_matches`). Made in `generate
  inputs` because the clip key needs it. Prompt `qwen_graph.RESTYLE_PROMPT` or
  `first_frame_prompt:`.

### 113.22 Chained parts and their join (Step 412)

- **Chained parts**: in a split beat with a starting picture, part k > 1 gets `Shot.last_of =
  <beat>_p<k-1>` (as `last_of:`, no restyle), so a run makes one part per pass in order.
- **Frames** (`videogen/chain.py`): LTX returns the picture as frame 0, so a chained take starts
  `CHAIN_DROP_FRAMES` (1) early and those frames are hidden (`Shot.lead`, `Placement.lead`). The
  picture is the previous take's frame shown at `first - lead` (`picture_at`, recorded
  `last_of_at`); the guide is cut from there (`guide_span`, a quarter frame early); take frame `i` =
  film frame `first - lead + i`; duration covers `length + lead / fps`.
- **Join**: `Placement.match_join` (in the fingerprint only when true): `clip_join.GainMatch` of the
  previous take's last shown frame vs this take's first (after `color_match`), eased out over 1 s;
  nothing outside `GAIN_RANGE`.

### 113.23 A stylesheet with the base video; the clip's size and length (Step 425)

- **Config**: `GeneratedShot.sheet` + `sheet_prompt` (required: vidgen cannot know the panels),
  together, only on a `Workflow.takes_sheet` workflow (`ltx-2.3-union-control`) under `comfyui`.
  Workflow-only keys `size` (`WxH`, multiples of `size_step`; not with `resolution`) and `duration`
  (1 to `max_seconds`; replaces the snapped length, a shorter clip is a note).
- **Shot**: `shots._sheet_input` needs the sheet's aspect within `SHEET_ASPECT_TOLERANCE` 1 % (scaled,
  never cropped: a crop cuts panels). Prompt `Reference sheet: <sheet_prompt>. Generated video:
  <prompt>` (`SHEET_HEAD`, `SHEET_TAIL`). `canonical_request` adds `sheet` (SHA-256, size) only
  when set.
- **Graph** (`ltx_graph.graph(sheet_file=)`): node 2 `LTXMultiICLoRA` (Ingredients LoRA on the sheet,
  guide 0; Union Control on the control, guide 1); nodes 40–42 load, repeat (clip frames) and add the
  sheet guide; node 14 chains after 42. Without a sheet the graph is byte-identical
  (`tests/data/ltx_graph/no_sheet.json`). Not with `second_control_file`.
- **Compiler**: a sheet job first needs `Transport.compiler_off()` true, else a `VidgenError` naming
  `Transport.compiler_fix` (`setup_session.py NAME --no-comfy-compiler`); the provider never
  restarts ComfyUI.
- **VRAM**: `setup_session.py --reserve-vram N` adds `--disable-dynamic-vram --reserve-vram N`; a
  running ComfyUI with other flags is restarted by its PIDs (`comfy_pids`), never `pkill -f`. A
  provider's first job has `free_before` (`POST /free`); `run_shots` uses one provider per paid
  comfyui run, so models unload once and stay loaded between shots.

### 113.24 Subjects: sheet panels made by vidgen, approved, a shot's sheet composed (Steps 428-429)

Sheets come only from an image model (never a video model's frames), made before video work.

- **Config**: top-level `subjects: {name: {look, location, seed, views}}`; 1–4 `SubjectView`s with
  `name` and exactly one of `prompt:` (§113.28), `from: {scene, at}`, `image:`; `crop` and (needed)
  `text` with a still. A shot's `subjects: [names]` (only on a `takes_sheet` workflow, not with
  `sheet`, ≤ `MAX_SHEET_PANELS` 4). Outside the fingerprint.
- **Panels** (`videogen/subjects.py`): a still (the `without_takes()` finished render at `at`, or a
  file) cropped onto `PANEL_SIZE` 1440x768 (object fitted on black, location cover), edited by
  `qwen_graph` (Qwen-Image-Edit-2511) with `OBJECT_PROMPT` / `LOCATION_PROMPT`. `make_panels` runs
  stale panels through one transport. Record `sheets/<subject>/<view>.json`: `source = {still:
  {scene, at, scene_fingerprint, render | image, image_sha256, crop} | null, edit: {prompt, seed,
  model, size}, location?}`, still / panel SHA-256, usage. `PanelSources.state` compares offline;
  same still under a new fingerprint re-records without GPU. Files `<view>.still.png` (no view
  named `contact`), `contact.png` (`write_contact`).
- **Approval** (`vidgen generate subjects --approve NAME | --approve-all | --reject NAME [--view
  VIEW]`): `"approved": true` in the record; only a current panel (else `VidgenError`); a remade
  panel loses it, a re-recorded one keeps it. An unapproved panel blocks the shot (the sheet is
  still composed for viewing). `plan_shots` warns for a `takes_sheet` shot with neither `subjects:`
  nor `sheet:`.
- **Background** (`sheet_background`: shot > `videogen`; default `black`, `location`, `#rrggbb`, a
  picture): `sheet_layout.on_background` replaces the near-black region (r+g+b ≤ 14) connected to
  the corner. `location_background`: the first location panel blurred (18 px at 768 wide), ×1.1,
  35 % blend with its mean lifted to luma 100. `sheet_source` adds it only when not black;
  `background_words` adds "the panels sit on a softly blurred <location>". Black is default
  (location washes out bright scenes).
- **Composition** (`videogen/sheet_layout.py`): `choose_grid` (largest panels; ties: fewer empty
  cells, fewer columns), `GAP` 4 px; `place_words` names cells; prompt `<place>, <look>, <text>`,
  later panels `<place>, the same <name>, <text>`. `make_inputs` writes
  `build/videogen/<shot>/sheet.png` at `guide_size`, recorded with the panels' SHA-256;
  `Shot.sheet` is set only when that record matches, else blocked. Then it is a `sheet:` shot.

### 113.25 Generating at 12 fps, doubled to 24 fps (Step 433)

- **Config**: `GeneratedShot.fps` (`None`, 12, 24; workflows only; `Workflow.fps_problem`).
  `Workflow.durations(fps)`: whole seconds with `s × fps` a multiple of 8 and `s × fps + 1` ≤ 121
  (24 fps: 1–5; 12 fps: 2–10 even); `duration_problem` names the frames. `shots.shot_durations`
  splits beats over the longest (5 s / 10 s).
- **Key**: `VideoRequest.fps` only when not the workflow's own (`shots.generation_fps`), so 24 fps
  keys stay. The guide stays at the film's rate; `fit_control(fps=12)` thins it at submit (covered
  by the key).
- **Graph** (`ltx_graph.graph(fps=12, out_fps=24)`): rate 12 on nodes 6 and 15, then node 50
  `FrameInterpolationModelLoader` (`rife_v4.26.safetensors`) and 51 `FrameInterpolate` ×2 into node
  26 at 24 fps; `out_fps == fps` leaves the graph byte-identical. RIFE stores `2n − 1` frames
  (`Workflow.stored_frames`).
- **Setup**: `tools/colab/setup.sh` fetches `rife_v4.26.safetensors` (`Comfy-Org/Frame-Interpolation`);
  `vm_state.py` counts it; a missing file's error gets `comfyui.missing_weights_hint`.

### 113.26 Three guides on the LTX workflow: canny, final, depth (Step 435)

- `Workflow.controls` of `ltx-2.3-union-control` = `("canny", "final", "depth")` (`controls_text`);
  other guides are plan problems. The graph does not depend on what the control shows. Colour
  (`final`) keeps parts and light best but some CG look, depth lets the model invent surfaces,
  canny invents most: all three are offered.
- Prompt sentences in `shots.GUIDE_PROMPTS`. A web scene's depth is §113.19.
- **Staleness**: the guide file and sentence are in the key; a changed `guide:` makes only that
  shot's input "not made yet"; canny, final and web depth share the `final` render.

### 113.27 The WebGL backend in a render's identity (Step 436)

- After rendering a Chromium-drawn scene (`pipeline.scene_webgl`: `3d`, `web`, `space`, web-based
  types) the pipeline records `render.webgl` (`gpu` | `swiftshader`) in its timings
  (`_record_webgl`); `_usable_render` reuses it only for the same backend (`_same_webgl`; missing =
  `swiftshader`). In `render/pipeline.py`, not the worker or `browser/chromium.py` (render inputs:
  changing them stales every render); not in the fingerprint (a VM-made guide would read stale
  locally). One render per scene path.
- `vidgen remote` passes `VIDGEN_WEBGL` as `VIDGEN_RUN_WEBGL` (`VM_KEYS`); `colab_vm.child_env`
  applies it after `/content/vidgen.env`; unset keeps the VM's.

### 113.28 Panels drawn from a prompt alone (Step 437)

The image model is not guided by images: a `prompt:` view is drawn from words alone, the first way
to make a panel.

- `SubjectView.prompt`; `_one_source`: exactly one of `prompt`, `from`, `image`; `text` optional
  here.
- **Graph** (`qwen_graph.zimage_text_graph`): ComfyUI's Z-Image-Turbo template
  (`z_image_turbo_bf16`, `qwen_3_4b` CLIP type `lumina2`, `ae`; loaders shared via
  `_zimage_loaders`), AuraFlow shift 3, `ConditioningZeroOut` negative, `PANEL_SIZE`, 8 steps, cfg
  1, `res_multistep` / `simple`, the subject's seed. Nothing is uploaded.
- **Panel**: `Panel.from_prompt`, model `TEXT_PANEL_MODEL`; source `{still: null, edit: {...}}`, key
  SHA-256 of model, prompt, seed; no `.still.png`. Approval and blocking as §113.24; `generate
  subjects` stays free.
- **One model at a time**: `_run_batch` groups panels by model and sets `free_after` on each
  model's last job (and `free_before` on the first), so nothing stays in VRAM after the batch.

## 114. 3D scenes with three.js (Phase AI, Steps 298–302)

Simple 3D in **three.js** in headless Chromium via **Playwright** (not Blender or Manim 3D): plain
colours, one light, stand-in characters; stable camera, exact timing, named objects, deterministic
frames, guide passes for generated shots (§113.8). Keys: [docs/CONFIG.md](docs/CONFIG.md#3d);
how-to `docs/COOKBOOK-3D.md`.

### 114.1 How a `3d` scene renders (Step 298)

`Scene3D` (`scenes/scene_3d.py`) is a `NarratedScene`. `construct`: length first (beats on the
scene clock via `beat_window`, Σ round(window × fps) + outro + `SPARE_FRAMES` 2); the description
(§114.3) at the config's size and fps; `make_3d_clip(render_dir/three_d, scene id, description)`
(§114.5); the clip as a full-frame `ClipMobject` (§38) from time 0 (the bottom layer, so Manim
objects and overlays draw over it; `dim` / `highlight` / `zoom` on target `view`); title
`text_plate` fades in at beat 1; 0.5 s outro. Output frame *k* shows clip frame *k* (*t = k /
fps*).

### 114.2 Params (Step 298)

`Scene3DParams` (`three_d/spec.py`; `vidgen.api` with `Camera3D`, `Light3D`, `Object3D`):
`title`, `background`, `camera: {position [3, 2.5, 5], look_at [0, 0, 0], fov 40 (10–120)}`,
`light: {ambient 0.5 (0–5), sun 2.5 (0–10), sun_from [-2, 6, 4], color #ffffff}`, `objects: [{id,
shape box, size [1, 1, 1], color accent, position, rotation (degrees, XYZ), spin (degrees/s)}]`.
Y up. Ids unique, `[A-Za-z_][A-Za-z0-9_-]*`, not `camera`; did-you-mean on shapes, refs and keys;
sizes positive; camera not on `look_at`; `sun_from` non-zero. Targets: `view`, `title`. `fov` is
across the frame's **shorter** side (the page converts), like Manim's frame (§5.2).

### 114.3 The scene description (JSON, version 1)

`three_d/description.py`, `scene_description(params, theme, width=, height=, fps=, frames=, beats=,
draw_mode="normal", camera_moves=, object_changes=)`: `{version: 1, width, height, fps, frames,
duration, draw_mode, background, camera: {fov, position, look_at, near 0.1, far 500}, lights
[ambient, sun (position = sun_from scaled to 20)], objects [{id, shape, size, color, position,
rotation, parent, ...}], timeline: {beats [{id, start, end}], tracks [{target, property, easing
linear | smooth, keys [{t, value}]}]}}`. Colours `#rrggbb`, numbers rounded to 6 decimals (stable
hash). The one Python–page contract; extended only by adding fields. Track properties:
`position`, `rotation`, camera `look_at`, `scale`, `opacity`, `emissive`, arrow `length`; keys
eased between neighbours, held outside. `spin` is a linear `rotation` track. `draw_mode`
(`DRAW_MODES`: `normal`, `depth`, `outline`, `mask`) is applied by the page's `applyDrawMode`.

### 114.4 The page and the browser

`vidgen/data/three/`: `three.module.js`, `three.core.js` (npm `three` 0.186.1, unmodified and
unminified; SHA-256 in THIRD_PARTY_NOTICES.md), `LICENSE`, `page.html`, `vidgen3d.js`
(`load(description)`, `frame(t)` → PNG data URL; `MeshLambertMaterial`). No
`requestAnimationFrame`, clock or randomness. `addons/` is for `web` only (§118.14).

`three_d/browser.py`, `PageRenderer(description)` (one per scene render): Chromium headless with
`--use-angle=swiftshader --enable-unsafe-swiftshader --ignore-gpu-blocklist` (same pixels on any
GPU); `VIDGEN_WEBGL=gpu` → `--use-angle=vulkan --enable-features=Vulkan --ignore-gpu-blocklist`.
Viewport = frame size, `device_scale_factor 1`; every request routed: `http://vidgen-3d.invalid/<file>`
from `PAGE_FILES`, everything else aborted (no network). Page errors → `VidgenError("3D page:
...")`; a page that does not load → `VidgenError("3D page did not load: ...")`, Chromium closed.
`write_clip` encodes FFV1 (`bgr0`) Matroska via PyAV to `<path>.partial` first; a clip that cannot
be replaced is a `VidgenError`. Shared code in `browser/chromium.py` (§118.5). Playwright is a base
dependency imported only when rendering: missing → `INSTALL_HINT`; Chromium missing →
`BROWSER_HINT`; other launch failures "cannot start Chromium for a 3D scene: ...".

### 114.5 The cache

`three_d/clip.py`, `make_3d_clip(folder, name, description)`: `folder/<name>.mkv` + `<name>.json`
`{key, description}`; `key = sha256(engine_id + canonical JSON of the description)`, `engine_id` =
page digest (`PAGE_FILES`, incl. the labels' font) + Playwright version (pins Chromium) +
`webgl=gpu` on the GPU. Reused when the key matches; else record removed, clip drawn, record
written last. `folder` = `<render_dir>/three_d`. The scene fingerprint (§63; page files are in
`vidgen_source_digest`) decides whether the scene renders; `--force` re-renders but reuses an
unchanged clip.

### 114.6 Public interface and decisions (Step 298)

- `vidgen.api`: `text_plate(text, fill, opacity=0.88)`, `Scene3DParams`, `Camera3D`, `Light3D`,
  `Object3D`, `BeatSpan`, `scene_description`, `make_3d_clip`; built-ins import only `vidgen.api`.
- One browser per scene render (workers are separate processes). The 3D clip is a separate cached
  file, so a caption or title change does not redraw 3D frames.

### 114.7 Shapes, labels and groups (Step 299)

`SHAPES`: `box`, `sphere`, `cylinder`, `cone`, `torus`, `plane`, `arrow`, `label`, `group`,
`standin` (§114.11). `size` `[w, h, d]` or a number; `DEFAULT_SIZES` (1; plane 4 flat; torus `[1,
0.25, 1]`; arrow `[0.08, 1, 0.08]` = thickness, length; label 0.3 text height). Geometry is scaled
in `geometry.scale`, never `mesh.scale` (children keep their size).

- **Arrow**: along +y, shaft + cone head (`min(3.5 t, 0.45 L)`, radius `1.25 t`), one group;
  every part has `userData.id`. `to` (point or object id, stopping at its sphere): Python computes
  centre, length, rotation (`euler_xyz`); `to` with `rotation` is an error.
- **Label**: canvas text (Inter Bold served as `inter-bold.ttf`, loaded before frame 0) on a
  `surface` plate at 0.88, a `THREE.Sprite` (faces the camera, scene-unit size).
- **Groups**: `parent: <id>` of an **earlier** object (no cycles); child transforms in the parent's
  frame. Flat `parent`, not nested `children:` (params stay non-recursive). `group` draws nothing.
- **Floor**: `floor: true | {size 12, color surface, y 0}` → plane `floor`, first in the
  description.

`three_d/world.py` `World(params)` mirrors the page in numpy: `matrix(id, t)` = parent ·
T(position) · R(rotation + spin · t) (R = Rx · Ry · Rz), `position`, `focus` (bounding sphere).
The page's `load` is async (font).

### 114.8 Camera moves (Step 299)

Beat actions (`scenes/scene_3d_actions.py`): `camera_orbit` (`around`, `degrees` positive =
counter-clockwise from above, `up`), `camera_dolly` (`by`), `camera_fly_to` (keeps its direction,
stops where the sphere fills `FILL` 60 % of the shorter fov, or at `distance`), `camera_look_at`
(object or `point`), `camera_move` (`to`, `look_at`); `easing: smooth | linear`. Keys:
[docs/CONFIG.md](docs/CONFIG.md#3d-camera-actions).

- Non-animating cues (`animates = False`): `Scene3D.camera_moves` reads `action_times(name, 0.0)`
  (whole frames) and builds `CameraMove`s before playing. `scene_targets = False`: targets are
  object ids checked by `scene_problems`.
- **Timing**: `run_time`, default to the end of the beat; may run into later beats; each move
  starts from the pose at its start; a running move **stops** where the next starts (its easing is
  not squeezed); clipped to the last frame.
- **Tracks** (`three_d/camera.py`, `camera_tracks`): `position` and `look_at`, linear, **one key
  per moving frame**, the eased path computed in Python (`move_path`, `ease`).
- **Checks**: `action_sequence_problems` (`camera_problems`: dolly past the target, orbit from
  straight above, ending on the target); `validate_project` (`check_3d_scene`: zero-length arrow,
  camera on its target); an impossible move at render → `VidgenError`.

### 114.9 `vidgen validate` and a missing browser (Step 299)

`browser.missing_dependency()` (no browser started): Playwright importable and its pinned Chromium
folder (`browsers.json` revision) in the browsers folder (`PLAYWRIGHT_BROWSERS_PATH`, `0` = in the
package, else the OS cache) → `INSTALL_HINT` / `BROWSER_HINT` / `None`. `install_warnings`
reports it as a validate **warning**, only for projects with a `3d` scene.

### 114.10 Public interface and decisions (Step 299)

`vidgen.api`: `CameraMove`, `camera_problems`, `check_3d_scene`, `Floor3D`. three.js stays
unminified; the labels' font is in the page digest.

### 114.11 Object actions and character stand-ins (Step 300)

**Stand-in** (`shape: standin`, default `[0.5, 1.6, 0.5]`, centred, so on a floor at `y = h / 2`):
capsule, a cone nose on +z at 0.28 h (`nose_color`), with `name` a label (0.14 h) above; `voice`
(default id) for lint. Fields `visible: false` (until `object_show`), label `screen_size: true`
(`screen_depth`).

**Beat actions** `object_move` (`to` / `by`), `object_path` (`points`, `smooth` Catmull-Rom,
constant speed, `turn`), `object_rotate`, `object_spin` (`turns`, `axis`), `object_scale`,
`object_show` / `object_hide` (`fade | grow`), `object_highlight` (emissive glow, not the 2D
highlight), `object_walk` (stand-ins; to `[x, z]` or an object, `WALK_GAP`; `speed`; linear),
`object_face` (shorter way). Keys: [docs/CONFIG.md](docs/CONFIG.md#3d-object-actions). Cues like
the camera's (`_ThreeDAction`); `Scene3D.object_changes` → `ObjectChange`s. Length: `run_time`,
else `seconds` (show, hide, face 0.6 s), else to the beat's end; a walk: turn (0.4 s per half
turn) + distance / speed.

**Motion** (`three_d/motion.py`): channels `position`, `rotation`, `scale`, `appear` [opacity,
grow], `glow`; changes become per-frame segments; a later segment cuts an earlier one in the same
channel (glow: brightest wins). Planned in start order; a change needing another object's place
reads it at its first frame (exact). A walk = turn (≤ 25 %) then move with a 2.5 % bob,
`round(distance / (0.38 h))` steps. `World.attach` (`plan_world`) adds S(scale × grow) and
`opacity` (product along parents); `World.follow`; arrows with `to` follow their target (loops are
errors).

**Tracks** (`object_tracks`, `held_keys`: only frames that differ from a neighbour): `position`,
`rotation`, `scale`, `opacity`, `emissive`, arrow `length`. Page: `node.scale`, `setLength`,
`applyLooks` (opacity × parents', transparent below 1; emissive brightest of self and parents).

**Camera follows**: position and look-at are `Ref`s (point or object-carried point since a time);
`look_at: <id>` follows from the start; after `camera_fly_to` / orbit-around the position stays
attached, after `look_at` / `move` / orbit the look-at does; a cut move freezes. `camera_poses` per
frame.

### 114.12 Lint: off frame and hidden (Step 300)

`Scene3D.layout_keys` adds `three_d: {objects, spoken}` to each layout still: `framing_3d` projects
each shown object's sphere (opacity ≥ 0.5) with the camera at `t`, 64 disc samples → share **off**
frame (1 behind the camera) and **hidden** by nearer discs (shrunk to 85 %; planes, labels, arrows,
groups and own group never cover). `spoken_objects` = ids named by the beat's actions + stand-ins
with the beat's voice. Rules (`lint/three_d_rule.py`, skipped under a 2D `zoom`):
`three_d_off_frame` (`max_off` 0.5), `three_d_hidden` (`max_hidden` 0.7), warnings; no pixels.

### 114.13 Public interface and decisions (Step 300)

`vidgen.api`: `ObjectChange`, `plan_world`, `framing_3d`, `hex6`. Poses are resolved per frame in
Python and stored in the description; the page only interpolates. Objects stay non-Manim targets.

### 114.14 Guide passes: depth, outline, mask (Step 301)

**depth**: near white, far dark grey, background black. **outline**: white edges on black.
**mask**: each object one flat colour on black, floor dark grey, with a table.

- **Same description, another mode**: `three_d/passes.py` `guide_pass(description, world, mode,
  depth=)` adds `draw_mode` and `depth_range` / `mask_colors`; frame *n* of a pass = frame *n* of
  the clip. Cached by `make_3d_clip(folder, "<scene>.<mode>", ...)` →
  `<render_dir>/three_d/<scene>.<mode>.mkv`; mask table `<scene>.mask-colors.json` (`mask_table`:
  `{scene, background "#000000", colors, objects [{id, shape, color, parent, name}], names}`).
- **Page**: flat `ShaderMaterial`s, no colour management / tone mapping / light / antialiasing,
  sprites hidden, objects drawn at opacity ≥ 0.5.
- **depth**: linear `u = clamp((far − z) / (far − near))` drawn `0.15 + 0.85 u` (`DARKEST`). One
  range per shot (no flicker): `depth_range` fits the **objects** (not planes) over up to
  `DEPTH_SAMPLES` 120 frames (sphere and box extents, the tighter), padded `DEPTH_PAD` 5 %; planes
  clamp; a planes-only scene fits a 17 × 17 grid; param `depth_range: [near, far]` overrides.
  Linear, not 1/z (a long floor left objects black); objects only (a floor took the range).
- **outline**: two float targets (normal + depth; object number), an edge shader: object change
  right or below, normals beyond `NORMAL_COS` 0.8, non-linear 1/depth (`DEPTH_STEP`); ~1 px per
  540 px of the shorter side.
- **mask**: `FLOOR_MASK` `#404040`; others `MASK_PALETTE` (16 hues × 3 tones = 48, no black or grey)
  at `sha256(id) mod 48`; a clash goes to the alphabetically first id, the other probes
  `MASK_PROBE` 7 on; past 48, a hash colour. Colours depend only on the **set** of ids; the frame
  holds exactly the table colour.
- **Asking**: param `guide_passes: true | all | [depth, outline, mask] | "depth,mask"`
  (`parse_passes`, same as `--guide-passes`; in the fingerprint; `Scene3DParams.passes()`);
  `vidgen render --guide-passes [LIST]` (alone = all; MCP `guide_passes`) →
  `render_project(guide_passes=)` → worker → `scene.guide_passes`. `_draw_view` draws them after
  the clip; timings record `render.guide_passes`; a reused render must have made them and their
  files must exist (`_has_guide_passes`). `RenderResult.guide_passes`.

### 114.15 Public interface and decisions (Step 301)

`vidgen.api`: `GUIDE_PASSES`, `guide_pass`, `make_guide_passes`, `mask_table`; `render_project`,
`current_render`, `render_scene` take `guide_passes=`. Passes stay lossless FFV1 (exact mask
colours; H.264 conversion is `cut_pass`, §113.8); one Chromium per pass; labels and name tags are
never in a pass; lint stays sphere-based.

### 114.16 Docs, example and review (Step 302)

Docs `docs/COOKBOOK-3D.md`, guide topic `three-d` (alias `3d`), `examples/3d-short`,
`examples/gallery`'s `crate`. `framing.view_basis` is the one camera basis for lint and depth range.
## 115. Hosted inputs through a Cloudflare Quick Tunnel (Phase AJ, Steps 305–306)

OpenRouter's video API takes audio / video references only as `https://` URLs (§113.7). Local
audio / video inputs (a voice, a `guide:` render) reach the provider through a **Cloudflare Quick
Tunnel** (`cloudflared tunnel --url http://127.0.0.1:<port>` prints a random
`https://<words>.trycloudflare.com`; no account). Rule: share only what is needed, as briefly as
possible. Tests use a fake `cloudflared` and a real local server.

### 115.1 The host (Step 305)

`vidgen.videogen.host` (not in `vidgen.api`):

- **What is shared.** `QuickTunnelHost(sources, root=, settings=, ledger=, executable=, fetch=,
  out=)`; `copy_into_share` copies each file into a fresh `tempfile.mkdtemp(prefix="vidgen-share-")`
  (refused inside the project) as `secrets.token_hex(8)` + lower-case extension, with size and
  SHA-256. A symlink, folder, missing or duplicate file, or a linked folder (junctions via
  `is_junction`) between the project and the file is a `VidgenError`; `O_NOFOLLOW` where
  available. Only the copies are served, never a project or user path.
- **Server** (`ShareServer`, `ThreadingHTTPServer`): `127.0.0.1`, port 0, no address reuse, no
  name lookup; answers only `GET` / `HEAD` of exact `/<secret>/<name>`
  (`secrets.token_urlsafe(24)` per host, empty query) with `Content-Type`
  (`openrouter.MEDIA_TYPES`), `Content-Length`, `Cache-Control: no-store` (else Cloudflare caches
  `.mp3`/`.mp4`), `X-Content-Type-Options: nosniff`; anything else is a 404 with a 10-byte body;
  no listing, no `Server` header. Requests kept in memory only (`RequestRecord`, secret replaced
  by `<secret>`, no client address); nothing logged. Socket timeout 30 s, `Connection: close`.
- **Tunnel** (`TunnelProcess`): `tunnel_command(executable, port, protocol)` = `cloudflared tunnel
  --url http://127.0.0.1:<port> --no-autoupdate [--protocol http2|quic]` (`auto`: no flag), in
  its own process group (Ctrl+C reaches vidgen, which stops it); last 200 output lines kept for
  errors; address = first `https://<name>.trycloudflare.com` (not `api.`) within `url_timeout`
  (60 s). `find_cloudflared(setting)`: `videogen.cloudflared` (path or command), PATH, then the
  winget locations on Windows; else a `VidgenError` with install hints.
- **Checked before use**: wait (≤ 15 s) for "Registered tunnel connection", then `verify_public`
  sends `HEAD` to every public URL every `verify_interval` (2 s) for `verify_timeout` (60 s) until
  200 with the right length (a missing length is accepted, a wrong one is not). Failure closes
  everything; the error says nothing was sent and points to `host-test`.
- **Close** (`close(reason)`, idempotent, resumable §115.5): cloudflared (`stop_process_tree`:
  Windows `taskkill /PID <pid> /T /F`, or a direct kill without `taskkill`; POSIX SIGTERM to the
  group, SIGKILL after 5 s), the server, the folder (`rmtree`, 5 × 0.2 s retries; failure = a
  warning and `folder_deleted: false`). Reasons: `done`, `error: <type>`, `interrupted`, `failed
  to open`, `interrupted while opening`, `max lifetime` (`host_max_minutes` after `open` began;
  watchdog every 0.1 s), `terminated (SIGTERM)` / `(SIGHUP)`, `vidgen exited` (`atexit`).
- **Ledger** (project `videogen-ledger.jsonl`; not jobs, `Ledger.jobs()` ignores them):
  `host_open {host, files: [{name, size, sha256}], max_seconds}` before the checks, so every open
  has a close (host name only, never the secret; `name` relative to the project); `host_fetch
  {file, method, status, bytes}` per request of a shared file (499 = client left mid-file);
  `host_close {host, reason, seconds_open, requests, not_found, folder_deleted}`.
- **Settings** (`HostSettings.from_config(videogen)`): `videogen.host: none | quick_tunnel`
  (`none`), `cloudflared` (null), `tunnel_protocol: http2 | quic | auto` (`http2`: TCP 443 passes
  more networks than QUIC's UDP 7844), `host_max_minutes` (20, 5–120).
- **`vidgen generate host-test [PROJECT] [--keep SECONDS] [--json]`** (`host_self_test`): free, no
  key, no ledger, default settings outside a project; shares one tiny text file and checks the
  public `HEAD`, the `GET` bytes, and 404 without the secret and with a wrong one. Only `--keep`
  (capped by the lifetime) prints the full URL. A failed check is a `VidgenError` (exit 1) after
  closing. Tests: `tests/test_videogen_host.py`.

### 115.2 Wiring: paid runs, the plan, MCP (Step 306)

- With `host: none` a shot with audio / video inputs is blocked with `shots.NO_HOST_BLOCKED`
  (names the setting and `host-test`; a problem with `inline_media: all`). With `quick_tunnel`,
  `Shot.share_minutes` = `host_max_minutes` and `Shot.shared` = those inputs; a failing
  `find_cloudflared` blocks the shot with the install hints.
- **One tunnel per shot** (split parts `<beat>_p<n>` too): only that shot's files, its own secret,
  for its one job.
- **`generate_clip`** (`run.py`): only after the cache, an earlier job, the model checks, the key
  and the budget pass (never a tunnel for a refused run), `hosted_inputs(sendable)`; if any and a
  `ShareOptions` is given (or the setting makes one), the host opens and verifies (failure raises
  before anything is sent or paid); the provider's `uploader` = `host.url_of` for the submit only
  (restored in `finally`); `submit`, its ledger line and `provider.wait(job)` run inside the
  `with`, so the tunnel closes (`done`) at the job's final state, before the download and the
  final ledger line. A `VidgenError` inside closes it and is re-raised redacted (§115.6). A job
  resumed from the ledger is only polled, never re-shared. Without a host, `media_url` stops the
  submit with a clear error.
- `run_shots` builds `ShareOptions.from_config(settings, out=...)` once; `share=` overrides it;
  the dry run never opens a host.
- **Plan**: per shot that would be shared, "would share through a public Cloudflare quick tunnel,
  only while this shot's job runs (at most N min; …):" and each file with its size (`not made
  yet` while missing); JSON `shared: [{path, bytes}]`, `share_max_minutes`. Sharing needs `--pay`.
- **MCP** `generate_host_test` (`keep` 0–300 s; JSON mode, so the URL with its secret never
  appears). User docs: `docs/COOKBOOK-3D-SCENE-TO-SEEDANCE.md` §5, docs/CONFIG.md.

### 115.3 Review of Steps 305–306

Its fixes are folded into §115.1 and §115.6.

### 115.4 Keeping the tunnel for the job, and refusing a submit without one (Step 309)

- No close-on-fetched: a complete `GET` does not mean the provider is done, and cutting off a
  paid job is worse than a longer exposure. `host_grace_seconds` is not a key.
- `HostSettings.lifetime_problem(poll_timeout)`: `max_seconds ≥ poll_timeout + submit_margin
  (180 s: longest POST 120 s + last poll sleep 60 s) + url_timeout`; otherwise `_resolve_inputs`
  blocks the shot (with the numbers) and `generate_clip` refuses before opening. For a short
  tunnel lower `poll_timeout`; a later run polls the job without a tunnel.
- `QuickTunnelHost.ensure_time_for_job(poll_timeout)` just before the submit: `VidgenError`
  (nothing sent) unless open with `poll_timeout + submit_margin` left (`opened_at` is set before
  cloudflared starts, so a slow start counts). `url_of` / `urls` raise on a closed host.

### 115.5 Cleanup when vidgen is signalled, killed or interrupted during close (Step 310)

`videogen/host_guard.py` and the stand-alone `host_watcher.py`:

- **Resumable close**: steps `cloudflared`, `server`, `folder`, `watcher`, `report` (ledger
  `host_close`); a finished step (even one failing with an `Exception`, a warning) is not rerun;
  `KeyboardInterrupt` / `SystemExit` leaves its step unfinished, the rest still run, and it is
  re-raised at the end; `_closed` only when all finished; `report` waits for the others. A later
  `close` (atexit, watchdog, retry) runs what is left, keeping the first reason. A second thread
  waits (30 s, then a warning); a re-entrant close (signal handler) returns at once. The `watcher`
  step disarms only when cloudflared stopped and the folder is gone.
- **Signals** (`track_host` / `_on_termination`): while a host is open SIGTERM, SIGHUP (Windows
  SIGBREAK) close every host and raise `SystemExit(128 + signum)`; handlers are installed only
  from the main thread and only over the default disposition.
- **Watcher** (`HostGuard`): a `python -I -S` process per host, own session (out of reach of
  `mcp_server.py`'s group kill), stdin piped from vidgen, ignoring SIGINT/SIGTERM/SIGHUP,
  output `DEVNULL`. Messages `tunnel <pid>`, `tunnel-stopped`, `disarm`. EOF without `disarm`:
  stop cloudflared's group (SIGTERM, SIGKILL after 5 s) and delete the folder. Never by pid
  alone: cloudflared holds the write end of a pipe (`tunnel_fds`) whose EOF means it is gone. Not
  `PR_SET_PDEATHSIG` (Linux-only, needs `preexec_fn`, per thread). A watcher that fails to start
  is a warning.
- **Windows** (`HostGuard.adopt`): cloudflared goes into a Job Object with
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` whose non-inheritable handle only vidgen holds; the
  watcher there only deletes the folder.
- **Stale sweep** (`sweep_stale_shares`, in `open`): each share folder holds `.vidgen-host.lock`,
  locked (`flock` / `msvcrt.locking`) by its host before any copy; `open` deletes only folders
  owned by the user whose lock it can take. No pid is trusted.

Not covered: vidgen and watcher killed together (the next sweep deletes the copies; a stray
cloudflared serves nothing), a frozen (SIGSTOP) vidgen.

### 115.6 Provider text never carries the shared address; the mock never shares (Step 311)

`vidgen.videogen.redaction.redact_shared_addresses(text)` (needs no host) replaces the path of
any `*.trycloudflare.com` address (plain, JSON-escaped, percent-encoded or truncated) and any bare
host-shaped path (32-char secret + `/` + 16 hex digits) with `<secret>`; the host name stays.
Applied wherever provider text enters: `parse_job`, `http_error`, `_send`'s transport error.
`QuickTunnelHost.redact` adds the exact secret; `generate_clip` applies it to the message and
details of every `VidgenError` from the host block and `_finish`. `Ledger.append` filters every
string field; provider error text is never stored (terminal lines: status, cost, `is_byok`).

`provider: mock` (`MOCK_PROVIDER`) never shares: `share` and `videogen.host` are ignored, the
mock `uploader` gives `https://mock.invalid/<name>`, `_resolve_inputs` marks the shot
`fake_addresses` (no "would share", no cloudflared lookup, no host block). `host-test` still
opens a real tunnel. Real-host tests use a non-`mock` stand-in
(`tests/test_videogen_host.HostedStandIn`).

## 116. Every Python package is a base dependency (Step 322)

A plain `pip install` of the distribution brings every Python package a user needs; never tell a
user to pip install a package. `dependencies` in `pyproject.toml` holds fpdf2, faster-whisper,
mcp, kokoro, misaki[zh], symusic (exact pin), playwright and fonttools (§119). Extras `pdf`,
`stt`, `mcp`, `kokoro`, `music`, `3d` stay defined and empty; `dev` is the only real extra.

- `kokoro` and `misaki[zh]` carry `python_version < '3.13'`; on 3.13 `install_message` says to
  use a Python 3.12 venv. `misaki[ja]` is left out (pyopenjtalk has no wheels): Japanese Kokoro
  voices stop with `kokoro.JAPANESE_NOTE`.
- A missing package is an incomplete install: `errors.REINSTALL`,
  `errors.incomplete_install(package)` say to reinstall the distribution. Imports stay lazy and
  guarded.
- Chromium is a browser download: `browser.BROWSER_HINT` keeps `python -m playwright install
  chromium`.

## 117. A clip that continues the one before: `match_previous` (Steps 325, 326)

A take made with `first_frame: last_of:<shot>` is redrawn slightly darker than the frame it
starts from, which flashes at the cut. `video_clip` param `match_previous: true | {seconds: 1.0,
hold: false, dissolve: 0, level: true}` (default `false`; `clip_join.MatchPrevious`, `seconds`
in (0, 30]) gives the clip's first frame the previous clip's level and colour and eases the
correction away over `seconds`. No frame is added or removed; durations and sound are unchanged.

- **Applies when** (`clip_join.match_previous_problem`; validate reports at
  `scenes[i].params.match_previous`, the render raises the same text): the scene directly before
  is a `video_clip`, joined by a cut, both with `fade: false` and `region: bleed`.
- **Measure** (`channel_gains`): both frames decoded at 64 x 64 through their scenes' crops; gain
  per channel = mean of the previous clip's last shown frame / mean of this clip's first frame
  (8-bit). The previous frame is at `scene length − 1 / fps` of the planned timeline
  (`VideoPlan.scene_duration`, `clips.clip_timing`): no rendered scene is read, so scenes still
  render in any order and in parallel.
- **Apply** (`GainMatch`): channel × `1 + (gain − 1) · left`, `left = 1 − smoothstep(played /
  seconds)` (`correction_left`), rounded, clipped at 255; untouched from `seconds` on. `hold:
  true` keeps the full gain; the next clip then references this clip's *corrected* last frame
  (`ClipJoin.reference`), so held corrections accumulate along a chain (also when a scene is
  shorter than its `seconds`).
- **Limits**: `GAIN_RANGE = (0.8, 1.25)` (frames as decoded), `MAX_DIFFERENCE = 0.04` (mean grey
  difference after the gain), `MIN_LEVEL = 4` (of 255): outside these, a warning with the numbers
  and no treatment. `APPLIED_RANGE = (0.67, 1.5)` caps the applied gain of a held chain.
- **Dissolve** `N` (0–12, `MAX_DISSOLVE`) blends the first N frames of the render being made
  (`VideoPlan.fps`) with the previous clip's last shown frame held still: weight `(N − k) / (N +
  1)` at frame *k* (`dissolve_weight`), applied after the gain (`JoinTreatment.apply`:
  `apply_gains`, then `blend`, alpha kept). `level: false` = dissolve only; an error without a
  dissolve or with `seconds` / `hold`. Gain and dissolve are skipped together (one warning) when
  the frames are not a continuation (`measure_match`) or the pictures' shapes differ by over 1 %
  (`ClipJoin.shape_problem`).
- **Code**: `vidgen/clip_join.py` is the one place that knows a join (`ShownClip`, `ClipJoin`
  with `reference`, `opening`, `treatment`; `opening_treatment`, called by
  `VideoClip._match_previous`). It returns a `clips.FrameTreatment` set as
  `ClipMobject.playback.treatment`, applied per decoded frame before opacity and tint; its
  hashable `state` is in the one-frame cache key. Not in `vidgen.api`.
- **Cache**: besides the params, the fingerprint carries `match_previous: [fingerprint of the
  scene before, size and mtime of its clip file]`, so a change upstream re-renders it.

## 118. `web` scenes: a page written in HTML, CSS and JavaScript (Phase AK, Steps 328–334, 336–337, 339)

A scene written as a web page. Decisions: project JavaScript is trusted like the Python in
`extensions/` (no flag); the page cannot reach the internet while rendering; full screenshots are
accepted even when slow. Author keys, `ctx` and what the clock does not control:
docs/CONFIG.md#web and `vidgen guide web`.

### 118.1 How a `web` scene renders (Step 328)

`Web` (`scenes/web.py`) is a `NarratedScene` built like `3d` (§114.1): `clip_plan(scene,
SPARE_FRAMES)` (`browser/timing.py`) gives the frames (beat windows or silent duration, the 0.5 s
outro, 2 spare); `make_web_clip` returns a lossless clip of screenshots at the page box's pixel
size (§118.11) and `config.frame_rate`, shown as a `ClipMobject` (target `view`: `dim`,
`highlight`, `zoom`). Clip frame *n* is the page at *t = n / fps*, output frame *n*.

### 118.2 Params and checks

Exactly one of `page:` (`.html`, `.htm`) or `script:` (`.js`, `.mjs`), a path inside the project
folder. `web/entry.py`: `entry_of(params)` -> `WebEntry(kind, path)`; `entry_problems(root,
entry)` (`page: file not found: …`, `script: must be a path inside the project folder, got …`,
`script: expected a .js or .mjs file, got …`; validate reports at `scenes[i].params.page` /
`.script`); the render checks again (`entry_path`).

### 118.3 The page, serving and errors

`web/page.py` `WebPage(root, entry, scene_id=, size=, fps=, frames=, …)`, one per clip:
`Chromium("a web scene", WEB_ARGS)` (`--hide-scrollbars --force-color-profile=srgb
--disable-partial-raster`, the last for pixel-identical renders), viewport = box size, device
scale 1 (or §118.17), time zone `UTC`, locale `en-US`, the init script (§118.8), and a route:

- `http://vidgen-web.invalid/<path>` from the project folder (`inside(root, path)`), type from the
  fixed `CONTENT_TYPES` (Windows may map `.js` to `text/plain`), else `mimetypes`; missing: 404
  and a warning (`favicon.ico` silent); `Range` requests get 206 (`byte_range`; needed to seek a
  `<video>`).
- `__vidgen__/canvas.html` (script only, `data/web/canvas.html`): one `<canvas
  id="vidgen-canvas">`, transparent background, a static `import * as hooks from "/<script>"`
  (so a syntax error carries file and line) copied onto `window.vidgen`.
- Anything else is aborted with one warning `scene '<id>': refused <url> (a web scene cannot reach
  the internet; …)`: a warning, so a page with a CDN link still renders. `data:` / `blob:` never
  reach the route.

`runtime.js` collects uncaught errors and rejections into `window.__vidgen.errors` and defines
`start(info)` and `frame(n)`. Opening waits for `load` and readiness at most `READY_TIMEOUT_MS` =
30 s (the message lists the 404s and refused URLs); any error so far stops the render. Each frame
is a viewport screenshot (`Page.captureScreenshot`, §120.10), size-checked by `png_pixels`.
`error_message`: `scene '<id>': JavaScript error in <file> line <n> at load | in frame(t=0.500):
<Name>: <message>`; location from the error event, else the first stack frame that is a project
file; a `VidgenError`.

### 118.4 The page contract (Step 328) and the cache

- A `page:` sets `window.vidgen = {load(ctx), frame(t, ctx), layout(t, ctx)}`; a `script:` module
  exports them. All optional, may be async; without `frame` each frame shows the page at that
  time. `ctx = {scene, width, height, fps, frames, duration, canvas, theme, data, beats, aspect,
  orientation, frame, region}`. Names are only ever added.
- **Clip cache** (`web/clip.py`): `<render_dir>/web/<scene>.mkv` + `<scene>.json` `{key, inputs,
  loaded}`; `inputs` = `{version: CLIP_VERSION (3), engine, scene, kind, path, sha256, width,
  height, fps, frames, theme, data, beats, shape, alpha: true}` plus optional keys only when set
  (`design_width`, …). `engine` = digest of the runtime files (`clock.js`, `media.js`,
  `runtime.js`, `canvas.html`), Chromium flags, time zone, locale and Playwright version. `key` =
  SHA-256 of canonical `inputs` (the random seed comes from `scene`). Drawn through a `.partial`
  file; the record is written last.
- **Render fingerprint** (§63): `web: {kind, path, sha256}` (`entry_digest`) plus loaded files
  (§118.10); `data/web/*` is in `vidgen_source_digest`.

### 118.5 One Chromium for `3d` and `web` (Step 328)

`browser/chromium.py`: `CHROMIUM_ARGS`, `INSTALL_HINT`, `BROWSER_HINT`, `sync_api`,
`playwright_version`, `missing_dependency`, `install_warnings(project)` (one per type in
`BROWSER_SCENE_TYPES` used), `browser_error`, `Chromium(what, extra_args)`, `write_ffv1_clip`,
`png_pixels`. `three_d/browser.py` keeps the 3D page; `3d` keys do not depend on `web` code. One
browser per clip, not per video.

### 118.6 Public interface and decisions (Step 328)

`vidgen.api`: `make_web_clip`, `web_entry_problems(root, params)`, `clip_plan(scene,
spare_frames)`, `web_page_inputs(scene, spans, css_scale=1)` -> `(ctx.theme, ctx.beats)`,
`web_json_problem(value, path="data")`, `web_page_shape(frame, region="bleed")`, plus the names
in §118.12 and §118.17; new `make_web_clip` arguments are keywords with defaults. Screenshots,
not a canvas read-back: a page may be any HTML.

### 118.7 The phase step by step, and what is left

Limits: no hard cut (`fade: false`) on `web`; storyboard and lint render the whole scene; lint
does not read text in pictures, WebGL or undeclared canvases, nor contrast over gradients; only
the shipped three.js add-ons are served.

### 118.8 Time belongs to vidgen (Step 329)

`init_script(scene_id)` joins `data/web/clock.js`, `media.js`, `runtime.js` (in that order) into
one function run before any page script (top frame only). Hand-written replacements, not CDP
virtual time or Playwright's `page.clock` (neither hits exact fractional frame times or covers
CSS, SVG, video and random numbers).

**Clock.** `nowMs` starts at 0, stands still during loading and `load`, moves only per frame.
Replaced: `Date` (no-argument forms = `2026-01-01T00:00:00Z` + `nowMs`), `performance.now`,
`document.timeline.currentTime`, `setTimeout` / `setInterval` / clears (one id space),
`requestAnimationFrame` / `cancelAnimationFrame`, `requestIdleCallback` (a 0 ms timer,
`timeRemaining()` = 50) / `cancelIdleCallback`.

**One frame** (`__vidgen.frame(n)`, target `n * 1000 / fps` ms):
1. Due timers in due-time order (ties by set order), the clock at each due time, one task after
   each (promises run) and animation discovery. Nested > 5 deep: ≥ 4 ms. The 10 001st callback
   before one frame clears all timers and is an error. Then the clock is set to the target.
2. Wait for every `fetch()` and body read, every incomplete `<img>`, `document.fonts.ready`.
3. Media (`placeMedia`): every `document.getAnimations()` entry is paused in Chromium and placed
   at vidgen's time (`t + (now − at) × playbackRate`; finished natively at its end); the page's
   `play`, `pause`, `reverse`, `finish`, `cancel`, `updatePlaybackRate`, `currentTime`,
   `startTime`, `playbackRate` act on vidgen's time. Outermost `<svg>`s are paused and set with
   `setCurrentTime`. `<video>`s are paused and seeked to vidgen's time, waited to
   `HAVE_CURRENT_DATA`. Then the beat (§118.9), followed by one task.
4. One round of the animation-frame callbacks requested before it, each with `nowMs`.
5. `frame(t, ctx)`, awaited. 6. Steps 2–3 again; errors returned; screenshot.

**Start** (clock at 0): the beat of frame 0 (no event), fonts (every declared face loaded),
pictures, fetches, media, `load(ctx)`, then those again.

**Random**: `Math.random` is sfc32 seeded from SHA-256(`vidgen-web-random:<scene id>`)
(`random_seed`); `crypto.getRandomValues` / `randomUUID` are seeded too (`crypto.subtle` not).

**Time limits** (`_TimeLimit`): `start` `LOAD_TIMEOUT_S` = 90 s, a frame `FRAME_TIMEOUT_S` = 10 s,
the first frame `FIRST_FRAME_TIMEOUT_S` = `LOAD_TIMEOUT_S` (§120.10). Past a limit a thread kills
the page's renderer processes (ids from `SystemInfo.getProcessInfo`) and vidgen raises `scene
'<id>': frame(t=…) in <file> did not return within 10 s: …; vidgen stopped the page`. Without
process ids there is no limit.

### 118.9 What the page is given (Step 330)

`web/inputs.py`. `_serve` inserts `page_head(theme)` after `<head>` (else after `<html>`, else
after the doctype, never before it) of the entry and bare pages: theme style, aspect script,
import map.

- **`ctx.theme`** (`page_theme(theme, px_per_point, project_fonts)`): `preset`, `background`,
  `colors`, `palette`, `fonts` (roles, and `sans` / `serif` / `mono`, which win), `sizes` (CSS px,
  `px_per_point = pixel_height / (72 × frame_height)`), `font_files` (§119).
- **CSS** (`theme_css`, `<style id="vidgen-theme">` first, so page rules win): `@font-face` per
  bundled family named (`/__vidgen__/fonts/<folder>/<file>`), then on `:root`
  `--vidgen-<colour>`, `--vidgen-background`, `--vidgen-palette-<i>`,
  `--vidgen-font-<role|sans|serif|mono>`, `--vidgen-size-<name>`. Theme names are identifiers
  kept with `_`, so kinds cannot collide; a colour token named `background` loses. A `page:` gets
  no forced background.
- **`ctx.data`** = the scene's `data:` (mapping, default `{}`), JSON values only (`json_problem`
  in a before-validator; error at `scenes[i].params.data`); theme colour names in it are not
  resolved.
- **`ctx.beats`** (`page_beats`): `{id, index, start, end, text, words: [{text, start, end}]}`
  from `clip_plan` and `beat_word_times`. `showBeat`: frame *n*'s beat is the last with
  `round(start × fps) ≤ n`; `<body>` `data-beat` / `data-beat-index`; `CustomEvent('vidgen-beat',
  {bubbles: true, detail: {beat, index, previous, t}})` when it changes (also at frame 0).
- **three.js**: import map `"three"` → `/__vidgen__/three/three.module.js` (with `three.core.js`,
  from `data/three`).

### 118.10 Every file the page loaded is in the cache keys (Step 330)

`WebPage._serve` records `loaded` (`path -> SHA-256` before the head insertion; a missing project
file = `None`; `favicon.ico` skipped) over all frames. A clip is reused only if the key matches
and `loaded_changed(root, loaded)` is empty. Render fingerprint `web` = `entry_digest` + `loaded`
(paths in the final and preview records, hashed now) + `align` (stat of each beat's
`.align.json`). On a first render `drawn_fingerprint` adds the new record's files, so the next run
does not re-render. `--force` removes the records (`forget_web_clips`). All of this holds for
subclasses of `Web` (`is_web_type`, §120.1).

### 118.11 A `web` scene fits with the rest of a video (Step 331)

- `region: bleed | body` (default `bleed`) and `title`: `bleed` fills the frame, a title is a
  `text_plate` over it; `body` uses `chart_title(title, area=safe_area)` and the box
  `safe_area.below(title, gap=0.45)` (or the safe area, which excludes reserved overlays and a
  Short's covered parts, §101). `pixel_box` snaps to whole pixels and the page is drawn at the
  box's pixel size. Beat 1 fades in the title; the scene fades out over 0.5 s.
- **Transparency**: Chromium's default background is set transparent once per page
  (`Emulation.setDefaultBackgroundColorOverride`, `TRANSPARENT`); frames are straight-alpha RGBA
  stored as FFV1 `bgra` (`3d` stays `bgr0`) and composited over the theme background. Not per-shot
  `omit_background` (slow) and not composited at capture (shows nothing vidgen draws behind, LCD
  text fringes).
- **Shape** (`page_shape(frame, region)`): `{aspect, orientation, frame, region}` in `ctx`;
  `aspect_name` = nearest of `NAMED_ASPECTS` (`16:9`, `9:16`, `1:1`, `4:5`, `5:4`, `4:3`, `3:4`,
  `3:2`, `2:3`, `21:9`, `9:21`) within 1 %, else the reduced `W:H`; `orientation` from
  `scales.frame_orientation`. Both describe the video frame, not the box; `data-aspect` /
  `data-orientation` on `<html>` are set by an inline script before any page code.

### 118.12 Lint reads the page (Step 332)

Page text becomes layout objects (§15) of kind `text`, so every text rule applies.

- **Reader** (`data/web/layout.js`, `WebPage.layout(n)`): an item is the nearest non-inline
  ancestor of a text node, or an SVG `<text>`. Fields: `text`, `box` (client rects), `font_px`
  (with transform / `scale` / `zoom`), `cap_px` (`measureText("H")`, 0.7 fallback), `color`,
  `opacity`, `background` (solid layers from `elementsFromPoint` over the theme background;
  pictures, canvases, gradients → `null` and `background_unknown`), `clipped`, `cut`, `visible`,
  `name` (`data-vidgen-id`, else a short selector, deduplicated ` (2)`), `lint`
  (`data-vidgen-lint`). Invisible items count in `hidden`. The optional `layout(t, ctx)` hook adds
  declared items (`declared_problem` skips a bad one with a warning).
- The reader runs after the frame's screenshot and touches no timer or random number; a `layout`
  hook must not change the page.
- **When**: `make_web_clip(..., layout_frames=planned_still_frames(self))` reads the planned still
  frames while drawing into `<scene>.layout.json` `{key, reader, frames}` (`reader` = digest of
  `layout.js`, not in the clip key). Other frames: `web_page_layouts(..., at=…)` reads them in one
  Chromium by stepping with `WebPage.advance` (no screenshots), since page state can depend on
  every earlier frame.
- **Dump** (`LayoutRecorder._page_texts`, `web/layout.py` `page_text_objects`): items mapped
  through the view's on-screen box, inserted right after its image object, as `{id: "web:<name>",
  kind: "text", class: "WebText", source: "web", path: "web/<name>", …}`; the frame gets `web:
  {box, size, frame, texts, declared, hidden, canvases}`; the header `reserved: [{overlay, type,
  box}]`.
- **Rules**: `web_clipped` (`lint/web_rule.py`, error, tolerance 0.004 of the shorter side; `is
  cut by its box <by> …` / `runs past the page's box …`). `off_frame` / `safe_area` skip `clipped`
  / `cut` objects; `safe_area` names a reserving overlay, and `overlay_overlap` skips text inside
  a reserved part unless the camera moved (every scene type).
- **Opt-out**: `data-vidgen-lint="off"` or `"off:rule,rule"` (`lint_opt_out`) → `lint_off`;
  `lint_ignore` matches `name`, `path` or `text`.
- **API**: `vidgen.api.web_page_layouts(root, folder, scene_id, params, *, size, fps, frames,
  theme=None, beats=(), shape=None, at=())`, `planned_still_frames(scene)`; `make_web_clip(...,
  layout_frames=())`; `web.clip.layout_record_path`.

### 118.13 Teaching it and proving it (Step 333)

Guide topic `web` (aliases `html`, `css`, `javascript`, `js`, `canvas`, `web-scenes`,
`web-scene`, `web-page`, `page`, `script`); its code must run as written (`tests/test_guide.py`
draws it in Chromium). `examples/web` has one `page:` and two `script:` scenes.
`gallery.sample_asset` maps a web snippet's file (`WEB_SUFFIXES`) to `data/gallery/web/<name>`
(§123.1).

### 118.14 three.js add-ons (Step 334)

23 unmodified `examples/jsm/` files of npm `three` 0.186.1 under `data/three/addons/` with its MIT
`LICENSE`; the list is `web/loaded.py` `THREE_ADDONS` (`THREE_VERSION`). Import map prefixes
`"three/addons/"` and `"three/examples/jsm/"` → `/__vidgen__/three/addons/`, so add-ons share one
core module. `vidgen_file` serves only manifest paths; any other add-on gives
`unshipped_addon_message` (copy it into the project, import it by relative path). Loaded add-ons
are in `loaded`; `3d`'s `page_digest()` excludes `addons/`. `EffectComposer` output is opaque.

### 118.15 Animation and chart libraries (Step 336)

Under `data/web/libs/<package>/`, unmodified with `LICENSE`, manifest `web/libs.py` `WEB_LIBS`
(SHA-256, size): `animejs` 4.5.0, `motion` 14.12.0, `d3` 7.9.2, `chart.js` 4.6.1 (also
`chart.js/auto`), `lottie-web` 5.13.0. The UMD builds (d3, Chart.js, Motion) get a vidgen
`index.js` that imports them and re-exports the global's names. `LICENSES-bundled.txt` covers
bundled packages. GSAP is not shipped (its licence is not redistributable): `NOT_SHIPPED`,
`unshipped_lib_message`. `media.js` keeps `Animation.startTime` on vidgen's clock (Motion sets
it). Frames are drawn in order from 0, so a library's own loop is deterministic.

### 118.16 Relative URLs in a `script:` scene; what `render --scene` renders (Step 337)

- `canvas_page` writes `<base href="/<script's folder>/">` (`script_base`, percent-encoded) into
  the bare page, so `fetch`, `src` and `url()` resolve beside the script; `location` stays
  `/__vidgen__/canvas.html` and vidgen's own URLs are absolute. A `<base>`, not serving from the
  script's folder: vidgen's files are told apart by `__vidgen__/`.
- **`render --scene`** (`pipeline.scenes_to_render`): the named scenes plus every scene without a
  usable render in this `render_dir` (per quality and variant), since the video joins them all;
  `pipeline.also_rendered_note` says so. With `--scene`, `--force` adds no scene. `storyboard` /
  `lint --scene` render only that scene.

### 118.17 `design_width`: a page built in fixed pixels (Step 339)

- `design_width: <int>` (200–8192, `DESIGN_WIDTH_MIN` / `_MAX`; `design_width_problem`): the CSS
  width the page was designed for. No `design_height`: the height follows the box.
- `page_viewport(size, design_width)` -> `((design_width, ceil(size[1] / scale)), scale)`, `scale
  = size[0] / design_width`; the context uses `device_scale_factor=scale` (no resampling). The
  height rounds up and `fit_pixels` cuts the surplus bottom rows, so frames are exactly `size`.
- The page sees the design window (`innerWidth`, `ctx.width` / `height`, the script canvas) and
  `devicePixelRatio` = `scale`; `ctx.frame` / `aspect` / `region` stay the video's; theme sizes are
  divided by `scale` (`css_scale`). A canvas is sharp only when sized by `devicePixelRatio`.
- `design_width` is in `clip_inputs` only when set. Lint maps readings by box / reading width;
  `css_height` keeps both axes on one scale.
- API: `web_page_viewport`, `web_design_width_problem`; `WebPage(..., design_width=None)`.

### 118.18 A draft of a video with `web` scenes (Step 340)

`vidgen render --draft` (§74) is the fast draft: 240 px on the shorter side at the format's
shape, 8 fps, `build/draft[_<variant>]` (`draft: {width, height, fps}`); preview is 854x480 at 15
fps. A `web` clip has its own key per size and rate. Lint and storyboard have no `--draft`.

## 119. The project's own fonts: the `fonts/` folder (Step 338)

`.ttf`, `.otf` and `.woff` under `<project>/fonts/` are used by the whole video.

- `vidgen/fonts.py`: `project_fonts(root)` → `ProjectFont(path, rel, family, weight, italic)` via
  fontTools (family = name 16, else 1; `OS/2.usWeightClass` or the `fvar` `wght` range; italic =
  `fsSelection` bit 0 or 9); an unreadable file is a `VidgenError`. `.woff2` is not read (needs
  `brotli`): `font_warnings` names one without a same-stem sibling.
- `register_project_fonts(root, build_dir)` (called by `extensions.activate`) registers each with
  `manimpango.register_font`; a `.woff` is first converted to `build/fonts/<stem>-<sha12>.<ext>`.
- With font files the text cache is `media/texts/<scene>.<digest of the files>` (Manim caches by
  family name) and the fingerprint gets `fonts` (path → size, mtime); without, neither changes.
- Pages: `ctx.theme.font_files: [{family, weight, style, url}]` (always present) and one
  `@font-face` each (`project_font_faces`); the files are in `loaded` and the clip key.
- `fonts.font_file(family, bold=, italic=)` gives the thumbnail (Pillow) the nearest project file.
- A refused Google Fonts request gives `google_font_message` once per family per scene (put the
  file in `fonts/`, remove the link).
## 120. What three music films asked of the generator (Phase AL, Steps 341–351)

Features built for music films made with `web` scenes and score files: `Web` subclasses in the
render cache (§120.1), page readiness (§120.2), `vidgen still` (§120.3), brass, organ, strings,
percussion and choir instruments (§120.4–§120.6), expressive score notation (§120.7),
`music_data:` (§120.8), compact intermediates (§120.9), faster `web` rendering (§120.10),
`vidgen/three-finish` (§120.11). Invariant for all of them: an existing score synthesizes to the
same audio, and stored cache keys are not invalidated without a written reason.

### 120.1 A scene type that subclasses `Web` is a `web` scene for the cache (Step 341)

- `vidgen.web.entry.is_web_type(name)`: true for `web` and for a registered type whose class has
  the built-in `vidgen.scenes.web.Web` among its bases (read from the class's `__mro__` by module
  and name; nothing is imported). `fingerprint_inputs` uses it to add the scene's `web` part
  (§118.10: the script's SHA-256 and every file the page loaded), and `render_project` uses it for
  `--force` (removes the clip records of every web-type scene).
- A type the registry does not know (no project session) counts only when it is `web` itself; the
  subclass scene's fingerprint then lacks the part and differs from the stored one, so it is
  rendered again rather than wrongly reused. Every caller of `scene_fingerprint` runs inside a
  project session.
- Not a web type: an extension scene that does not subclass `Web` and calls
  `vidgen.api.make_web_clip` itself; its script is in no fingerprint (`extensions` digests only the
  `*.py` files of extension folders, `assets` only `assets/`). Such a scene should subclass `Web`
  or keep its page under `assets/`.
- The frames clip `build/<quality>/web/<scene>.mkv` has its own key (`make_web_clip` compares the
  script and loaded files). Tests: `tests/test_web_extension_cache.py`.

### 120.2 Waiting for a page to become ready (Step 341)

`WebPage._wait_until_ready` polls from Python (`page.evaluate`) every `READY_POLL_MS` (20 ms) up to
`READY_TIMEOUT_MS`, sleeping with `page.wait_for_timeout` (keeps Playwright serving the page's
requests; `time.sleep` would not). Not `page.wait_for_function`, because its repeated looks run on
`requestAnimationFrame`/`setTimeout`, which are vidgen's clock (§118.8) and stand still before
frame 0, so a module still awaiting fetches was never seen ready. The failure message ends
`: not ready after 30000 ms`.

### 120.3 `vidgen still`: single frames of a `web` scene's page (Step 342)

- **Command.** `vidgen still [PROJECT] --scene ID (--at SECONDS | --frame N | --count N)...
  [--size final|preview|draft|WxH] [--variant NAME] [--out FILE|DIR] [--sheet FILE [--columns N]]
  [--exact] [--transparent] [--json]` (`cli.cmd_still`, `vidgen.web.still.make_web_stills`;
  JSON fields: `docs/CONFIG.md`, "`vidgen still --json`"). Draws frames of a `web` scene's page
  without rendering the scene.
- **Same page setup as the render.** `still.page_setup` loads the project for the quality
  (`Project.load(draft=)`), activates extensions, configures Manim with
  `render.worker.configure_manim` (inside `manim.tempconfig`, temporary media folder) and
  instantiates the scene class. `Web.page_clip_args(box=None)` returns the `make_web_clip`
  arguments (page size from `_title()` and `_page_box()`, fps, frame count from `clip_plan`, theme
  and beats from `web_page_inputs`, shape); `Web._draw_view` uses the same method, so a still and a
  render cannot differ in these.
- **Time and size.** `--at t` → frame `round(t * fps)` from the scene's start; `--frame N`; allowed
  0 to `frames - 1` (spare frames included). `WxH` replaces the project's `format` size at the
  final fps before extensions activate (even numbers required).
- **Order and state.** Stills are drawn in the order asked on one page while frames move forward,
  else a new page (the clock cannot run back); a repeated frame is drawn once. Default
  `page.frame(n)` jumps straight there (exact for pages that are a function of time, §118.15);
  `--exact` first calls `page.advance(k)` for every frame in between (no screenshots, as
  `web_page_layouts`, §118.12), as the render does.
- **Output.** PNGs to `--out FILE.png` (one still) or a folder, default `<project>/exports/stills/`,
  named `<scene>_<seconds, 8 wide, 3 decimals>s.png`; RGBA over the theme background, or raw RGBA
  with `--transparent`. `--sheet`: grid up to 1920 px wide (`still.contact_sheet`), stills only
  scaled down, label `scene  t s  fN`, columns `ceil(sqrt(n))` up to 6 or `--columns`. Nothing under
  `build/<quality>/` is read or written: no cache key is touched.
- **Errors** (`VidgenError`): unknown scene (closest id, list of web scenes); non-web scene (names
  `vidgen storyboard --scene ID --per-beat N`); time/frame outside the scene (names the range); no
  `--scene`; no time; bad `--size` (did-you-mean); `--out FILE.png` with several stills.
- **MCP** `still`: `at` and `frame` as lists, `sheet: true` writes `contact_sheet.png` in the
  stills' folder; returns the pictures, sheet first, paged like the storyboard (paging redraws).
- Stills equal the frames of the rendered `build/<quality>/web/<scene>.mkv` (`tests/test_web_still.py`).
  Only `web` scenes; no title, overlays or captions in a still.

### 120.4 Brass and organ for score files (Step 343)

- **Instruments** of kind `note`, catalogue families `brass` and `organ` (between `leads` and
  `pads`): `trumpet`, `horn`, `low_brass` (trombone section with an optional `tuba` an octave
  below), `organ`. Numpy only, no samples. Modules `studio/additive.py`, `studio/brass.py`,
  `studio/organ.py`, registered in `studio/instruments.py`. Settings, ranges and uses:
  `docs/COOKBOOK-MUSIC.md` (instrument table); the DSP constants live in the modules.
- **Additive wave tables** (`additive.py`, shared by §120.5, §120.6, §121.4): harmonics up to
  16 kHz (last 2 kHz faded, `HIGHEST_PARTIAL`) are summed by inverse FFT into one period
  (`wavetables`, ≥ 128 samples per period of the highest harmonic) and read along the note's phase
  (`read_tables`); vibrato and slides are a changing phase step, a changing spectrum a cross-fade
  between table rows (`row`). Nothing above Nyquist is generated, so nothing aliases.
  `remembered` caches the last 48 notes of up to 2 s. `levelled` brings a section's summed power
  (over whole periods, ≥ 50 ms) to the sum of its players' powers (gain at most ±8 dB), because
  detuned players drift in and out of phase.
- **Brass**: one model with bodies `TRUMPET`, `HORN`, `TROMBONE`, `TUBA` (bell cutoff, formants,
  scoop). `spectrum(body, Hz, brightness)`; a note cross-fades between 8 spectra along
  `b(t) = brightness * level(t) ** 1.6`, so the tone opens with the level; the held part is
  normalised to RMS 1, so `brightness` changes tone, not level. Lip scoop into the pitch, tongued
  overshoot for attacks ≤ 0.12 s, breath noise, delayed vibrato (default 9 cents trumpet, 0 horn
  and low brass). Sections (`players` > 1): players `detune` apart, entering up to 28 ms late,
  spread left to right (a solo is mono), summed with `levelled`.
- **Organ**: nine drawbar ranks (16' 5 1/3' 8' 4' 2 2/3' 2' 1 3/5' 1 1/3' 1', 0–8 at 3 dB a
  step); ranks above 6 kHz fold an octave down, under 27 Hz up; ranks on one pitch merge.
  `registration`: `cathedral` (default), `principal`, `flute`, `reed`, `drawbar`, `full`;
  `drawbars` (nine digits, quoted, spaces allowed: `"00 8400 000"`) replaces the bars and keeps the
  pipe kind. Steady: no decay, every pipe starts at the same phase and the note is normalised by
  the power of the partials as they add, so level and tone repeat exactly whatever the
  registration. Options `chorus` (celeste pipe), `detune` (default 0), `click` (default 0). Pipe
  speech with a chiff and wind noise; ranks alternate left/right by semitone and rank.
- **Score format.** `Setting` has `choices` (names for whole numbers from 0: `registration: flute`
  or `2`) and `read` (own notation: `drawbars`); `score_file._setting_value` reads them and reports
  an unknown name with the closest one. Inside the score both are numbers (`TrackPart.settings`),
  so sections and marks can change them. An unquoted `drawbars: 008400000` is refused (YAML reads a
  number). `Instrument` has `seeded` (its `make` takes a seed text `studio:<score seed>:<track
  name>`: two tracks in unison are two players; one track plays a note the same way every time)
  and `range` (written range, warned about, §120.7). `music patches --json` shows `range` and
  `choices`.
- **Levels.** A held note at defaults is about −16 to −17 LUFS before the piece is normalised (as
  piano chords); a chord is as loud as one note, a section as loud as one player. This holds for
  §120.5 and §120.6 instruments too.
- **Cache.** `_render_hits` passes the seed only to `seeded` instruments; no existing instrument,
  default or cache key changed.

### 120.5 Bowed strings for score files (Step 344)

- **Instruments** of kind `note`, family `strings` (between `organ` and `pads`): `violins` (G3–C7,
  6 players), `violas` (C3–E6, 5), `cellos` (C2–A5, 4), `double_basses` (C1–G4, 3; not `basses`,
  the synth-bass family). One model (`studio/strings.py`), four bodies; setting `stroke` =
  `sustain`, `spiccato`, `tremolo`, `pizzicato` (per section or per mark). `players: 1` is a mono
  solo. The older `pizzicato` instrument is unchanged for existing scores.
- **Model.** String spectrum `bowed(body, Hz, brightness)` (sawtooth at 0.5, sul tasto towards 0,
  sul ponticello towards 1) or `plucked(...)`, times a body curve `response(body, Hz, player,
  mute)`: fixed in frequency (air and plate resonances, bridge hill, roll-off, 40 narrow ±5 dB
  resonances drawn once per body and per player), so every pitch has its own harmonic balance.
  `mute` removes the bridge hill. A sustained note's tables are 5 rows across the vibrato swing, so
  vibrato moves the tone too.
- **Bow.** Rosin noise shaped by the body, scaled by `accent` (0–2) and `bow` (0–4), kept under the
  tone's own highs (§121.8); a scratch at stroke start when `attack` < 0.15 s (always in spiccato).
  Sustained notes start and end darker; release `ring` (0.25 s).
- **Short strokes** are a table row per moment since the stroke began (spiccato: bite, `length`
  0.07 s on the string, then each harmonic decaying at its own rate, times `decay`; pizzicato: the
  plucked spectrum ringing). Both ring until their steps end, then are damped over `ring`.
  `tremolo`: level follows bow strokes at `speed` (13/s), section players at different speeds and
  phases; as loud as the sustained note.
- **Determinism.** Nothing depends on chance at render time: same pitch, length, settings and
  track give the same samples (`additive.remembered` makes each ostinato note once).
- **Even section** (players `detune` (8) cents apart, staggered entries, spread left to right),
  kept steady by: `additive.levelled` per stereo side; `_in_step`, which picks per harmonic the
  best of 16 random sets of player phases (`wavetables` takes an optional phase per harmonic);
  equal loudness per note, not RMS (`additive.loudness`, harmonics weighted as the loudness
  measure).
- **Cache.** No existing instrument, default or cache key changed.

### 120.6 Orchestral percussion and a choir for score files (Step 345)

- **Instruments** in families `percussion` and `choir` (after `strings`, before `pads`), numpy only
  (`studio/percussion.py`, `studio/choir.py`): kind `note` with a written range: `timpani`
  (D2–A3), `toms` (G1–C5), `choir` (E2–C6); kind `drum` (drum steps, pitch a setting): `taiko`,
  `bass_drum`, `frame_drum`, `snare_drum`, `cymbal`, `tam_tam`. Settings: `docs/COOKBOOK-MUSIC.md`.
- **Struck head** (`struck`, a `Head`): decaying sines at the head's modes (`MEMBRANE`: Bessel
  zeros; `KETTLE`: the tuned kettledrum ratios 1 : 1.504 : 1.99 : …, plus `KETTLE_DULL` as the
  blow's thump). Low drums ring longer; `mallet` (0–1) sets the blow's low-pass, the mode tilt and
  a knock; every mode starts `drop` semitones sharp and settles; shells add two short modes;
  `edge` (frame drum). The blow fades in, so the first sample is exactly 0; loudness is RMS 1 over
  the first 0.15 s, lowered when the peak would exceed 3.6 times that.
- **Made once.** `struck` is remembered per head, pitch and settings (48 blows); a hit is that array
  cut to length and, if cut early, damped over 70 ms (`ring` on timpani and toms). A `note`
  instrument gets the track seed (each track's drum up to 0.5 % off); a `drum` instrument has no
  seed and is the same in every track.
- **Rolls** (`stroke: roll`: timpani, toms, snare drum): the blow convolved with jittered impulses
  `speed` per second; on a pitched drum each blow falls on a whole number of the note's periods
  after the first (else blows against the head's motion cancel). Steady level (0.7 of a blow, snare
  0.42); a crescendo is a hairpin or `volume` curve.
- **Ensembles** (`players`): drums slightly off in pitch, time (up to `apart`) and level, spread
  left to right; the sum's energy set to one drum's.
- **Snare drum**: short head plus wires (`snares`; 0 removes them).
- **Metal** (`clanged`, a `Metal`, cymbal and tam-tam): fixed inharmonic low modes as sines plus 14
  noise bands up to 14 kHz, highs dying first; tam-tam `bloom`; `stroke: swell` = a growing roll
  ending at a single blow's level when the held steps end. Stereo.
- **Choir** (`choir.py`): formant synthesis on the §120.4 tables. Voice slope set by `brightness`;
  five cascaded resonators (Klatt) with sung-vowel formants for basses, tenors, altos, sopranos
  (Csound manual table after IRCAM CHANT): `vowel` `aah`, `eeh`, `ee`, `oh`, `ooh`, `mm` (hum).
  Five rows across vibrato and drift, so formants stay while pitch moves. When the note is above
  F1, F1 follows the note (`formants`). Section (`singers`, 8): each singer's own throat, tuning,
  scoop, vibrato, entry and place; each side `additive.levelled`. `voices`: `mixed`, `men`,
  `women` share a note among the voice kinds that reach it (basses E2–G3, tenors D3–E4, altos
  A3–C5, sopranos E4–E6, fading over 4 semitones), the nearest kind when none does. Breath noise
  through the vowel's formants; `morph`: the second vowel's tables cross-faded over the middle
  70 % of the held time. Equal loudness per note (`additive.loudness`).
- **Cache.** No existing instrument, default or cache key changed.
- **Limits.** A `drum` instrument's pitch changes per section or per mark only; blows at the same
  settings are identical and a roll repeats one blow.

### 120.7 Expressive notes in the score format (Step 346)

Notation reference for users: `docs/COOKBOOK-MUSIC.md` (marks table). Contract:

- **Rule above all**: a score using none of this notation plays the same samples. New settings
  default to the old constants, new paths are entered only by a mark, the old path is untouched.
- **Marks** `[...]` inside `steps` stand before a step (note, hit, hold `-`, rest); items separated
  by spaces; an item holds until another mark changes it; a repeated pattern restarts as written.
  - *Dynamics* `ppp pp p mp mf f ff fff` = −20, −15, −10, −5, 0, +4, +7, +10 dB (unmarked = `mf`),
    or signed dB (`[-6]`). `<` / `>` open a hairpin, linear in dB over time to the next dynamic
    mark (which gives the arrival level; may stand at the very end of the steps). `fp` (`ffp`,
    `fpp`, `mfp`, …) drops to the second level within 0.25 s; `sfz` starts 7 dB above and returns.
  - *Settings* `name=value` from this step on; a named value alone when only one setting has it
    (`[pizzicato]`, `[roll]`); `[default]` restores the part's settings.
  - Errors name the mark, its place and the nearest known word (hairpin/`fp` without a level, a
    setting the instrument lacks).
- **Slurs** `( ... )`: notes after the first are not re-attacked; each pitch is reached by a glide
  of `glide` s (default 0.06) arriving just after its step. Inside: single notes only (chord, `+`
  or rest is an error) and only `score_file.FREE_IN_SLUR` settings may change (`glide`; `syllable`,
  `vowel` for `choir`, §121.4). Instruments that slur: `trumpet`, `horn`, `low_brass`, the four
  strings (sustain, tremolo), `choir`, `soft_lead`; elsewhere an error listing them.
- **A dynamic** always sets the level; with `Instrument.respond` (settings as played `dB` above
  `mf`) also the tone: brass `brightness`, strings `brightness` and `accent`, choir `brightness`,
  struck percussion `mallet` (and `drop`). Organ, older instruments and pads: level only. A level
  moving inside a note ≥ 0.25 s (hairpin, `fp`, `sfz`) is a gain curve plus, with a response, a
  cross-fade between the note at the curve's softest and loudest levels (same players and phases).
  Shorter notes take the level at their start.
- **`touch`** (default 0, so existing scores do not change): how much old-style accents (`X`, `o`,
  `!`, `?`, `accent:` groups) also change the tone; 1 = as a dynamic of that level.
- **Vibrato** `vibrato_speed` (Hz), `vibrato_delay` (s) beside `vibrato` on the instruments that
  slur; defaults are the old constants.
- **Instrument per section**: `sections: {lift: {instrument: horn}}`; must be of the track's sort
  (drum/pitched; `play: chords` stays with pads); settings start from the new instrument's
  defaults; steps, octave, volume, effects stay the track's.
- **Range**: `vidgen music render`, `vidgen music check` and the studio mix warn about notes outside
  an instrument's written range; they still play.
- **Other readers.** A duck with `follow: true` scales each dip by the dynamic at the hit and its
  accent; a slurred phrase is one event (one dip, one `accent:` position); a pad note takes the
  dynamic at its start; `vidgen music render` names a section's instrument in its track line
  (`melody (horn; trumpet in lift)`); the studio step grid skips marks and parentheses and keeps
  them on edit.
- **Code.** `patterns.parse_steps` reads marks and resolves dynamics (each `Step`: start and end
  level, `burst` for `fp`/`sfz`, `slur`, raw setting items); `score_file` resolves settings
  (`Step.changes`); `render._events_and_last` gives events level segments and slurred notes;
  `render._render_hits` plays a plain event exactly as before, others through `_expressive`. A slur
  reaches the instrument as `phrase` (`(start sample, semitones, glide samples)` per further note):
  one phase through, each note's tables cross-faded (`additive.phrase_tone`), the higher note's
  tables during a glide so no harmonic passes 16 kHz. `additive.remembered` keys on the phrase;
  dynamics reach the instrument as settings, already in its key. A note whose level moves is made
  twice.

### 120.8 Built-in music data for `web` scenes (Step 347)

- **Interface.** `web` param `music_data: false | true | {bands, tracks, t0}`
  (`vidgen.web.music.MusicDataSettings`: `bands` 1–64, default 16; `tracks` default all; `t0`
  seconds). The page's `ctx.music` is built by `data/web/music.js`, a second init script added only
  for such pages, wrapping `window.__vidgen.start` (so `runtime.js`, `clock.js`, `media.js`,
  `engine_id()` and other scenes' clip keys are unchanged). Functions take an optional song time
  `T` (default `ctx.music.now()` = `t0 + performance.now() / 1000`): `band(i)`, `bands()`,
  `level()`, `low()`, `onset()`, `hits / notes / events(track?, T0?, T1?)`, `last(track)`,
  `sounding(track)`, `pulse(track, decay)`, `section()`, `time(t)` (scene → song time). Fields
  camelCase in JS (`dynamicEnd`), snake_case in Python (`dynamic_end`). User guide:
  `docs/COOKBOOK-MUSIC.md`.
- **Measured** (`analyse`): the music the video plays (`plan_music` + `plan_score` of `mix.py` on
  the planned timeline `planned_timings`, through `MusicTrack`: cue start, section, loop, volume,
  fades, scene `music:` levels, ducking, themes), without narration, effects or ambience; rounded
  to 16-bit (`pcm16`, so near-silent bins do not make the onset jump) and mono. Per frame (whole
  video + 2 spare) a 4096-sample Hann window at `round(f * 48000 / fps)`: band powers (`bands + 1`
  log-spaced edges 40 Hz–12 kHz), level 25 Hz–14 kHz, low end 25–150 Hz, onset (mean positive
  change of `log10(power + 1e-9)`). Normalised over frames where a cue plays above `SILENT_DB`
  (−100 dB): bands 20th → 99.5th percentile, level 36 dB and low end 30 dB under their 99.5th,
  onset 1 at its 99.7th; then `released` (keep 0.82, 0.9, 0.8, 0.7).
- **Events** (`vidgen.studio.events.score_events`): the score read as `studio/render.py` plays it,
  with its helpers (`_track_events`, `_Voicer`, `_Skipped`, `_slot_at`): holds, ties, loop tails,
  accents (`ACCENT_GAIN`), chords voiced as played, notes outside 20 Hz–12 kHz dropped, section
  instruments. Per event: time, duration, MIDI pitches, instrument, start dynamic (with `burst`) and
  end dynamic, gain, `stroke` by name, `slur` (a slurred note is its own note with `slur: true`).
  `play: chords` tracks give one note per held chord (merged as `_render_held_chords`). Nothing is
  synthesised.
- **Song time.** From the cue playing at the scene's start (`music:` cues before scene themes):
  `t0 = offset + (scene start − cue start)`, `offset` = cue `start` + its `section`'s start, modulo
  one pass for a loop (as `Source`); events repeat per pass, those before 0 dropped. No cue: `t0` =
  scene video time, `source` and `score` `null`. `music_data: {t0}` overrides.
- **Transfer.** `video_music_data` holds every frame; a page gets its scene's frames ±
  `PAGE_MARGIN_SECONDS` (5 s; outside reads the edge frame) and all events. Series: one byte per
  value, base64. Events per track as base64 typed-array columns (start and duration in 48 kHz
  samples `uint32`, first pitch `uint8`, chord pitches as a sparse map, dynamics and gains
  `float32`, instrument, stroke, slur `uint8`); all-default columns omitted. Not compressed.
- **Cache.** `music_inputs` (no audio read): data version, vidgen's version, fps, every `music:`
  cue, `score:`, `soundfont`, each scene's `music:` and beat motifs, files under `assets/music` and
  each cue's file (score files by SHA-256, others size and time), the planned timeline and, when
  any music ducks, every narration MP3's size and time. `music_data_key` adds the band count; data
  in `build/music/music-data-<key>.json`. Music renders through `Source` with cache `build/music`
  (`piece-<key>.npy`, shared with the join). `render_project` makes the data in the parent before
  workers start (`prepare_music_data`); a worker, `vidgen still` or lint that finds none makes it.
  Only scenes with `music_data` get `music` in the fingerprint's `web` part and `music: {data,
  helper}` (SHA-256 of what is sent and of `music.js`) in the clip inputs.
- **Checks.** `Web.validate_project`: `music_data` with no music (`music_data: the video plays no
  music; ...`), unknown `tracks` (did-you-mean), `tracks` when the scene's music is not a score
  file: `VidgenError`. In the page, an unknown track or band throws, naming the valid ones.
- **`vidgen.api`**: `WebMusicData` (= `MusicDataSettings`), `video_has_music(config)`,
  `web_scene_music(project, scene_id, fps, settings)` (pass as `make_web_clip(..., music=)`);
  exported because built-in scenes import only `vidgen.api`.
- **Limits.** No per-track audio analysis; a cue starting inside a scene gives it no song time;
  ducking makes the measurements dip under narration.

### 120.9 Smaller intermediate files (Step 348)

User reference: `docs/CONFIG.md` "Intermediate files and disk (`render:`)".

- **Frames clips** `build/<quality>/web/<id>.mkv`, `three_d/<id>.mkv` (FFV1 in Matroska, `bgra`;
  `3d`: `bgr0`; intra-only; about 1 byte per pixel and frame for a WebGL page) are the only large
  intermediates; they are needed again only when the scene re-renders for a reason other than its
  page. The scene clip `scenes/<id>.mp4` (H.264 `yuv420p` CRF 23, Manim's default, stream-copied
  by the join) is the delivered picture and is not affected by these settings. The lossless
  default (codec, settings, packets, keys) is unchanged: no cheaper lossless option exists in PyAV.
- **`render.intermediate: compact`** (`--intermediate compact`, MCP `render` `intermediate`).
  `vidgen.browser.frames_clip.write_frames_clip` writes libx264 `yuv444p` CRF 12 (`COMPACT_CRF`),
  preset `veryfast` (`COMPACT_PRESET`), plus for frames with alpha a lossless FFV1 `gray` stream in
  the same file titled `alpha` (`ALPHA_TITLE`). `ClipReader` (`vidgen.clips`) reads that stream
  with a second reader into the alpha channel, so `ClipMobject` and above are unchanged. About
  4.6× smaller; CRF 12 keeps it visually lossless (SSIM 0.96+ on grain).
- **Cache.** The intermediate is not in the clip's key. A compact clip's record says
  `"intermediate": "compact"` (no field = lossless). `clip_serves(stored, wanted)`: lossless serves
  either, compact only `compact`; otherwise `make_web_clip` / `make_3d_clip` redraw. The scene
  fingerprint excludes the setting (use `--force` to remake). Workers get it as `--intermediate`.
- **`render.keep_intermediates: false`** (`--clean-intermediates`, MCP `clean_intermediates`).
  After each scene (in the parent, after `post_scene`) `disk.remove_frames_clips` deletes its frames
  clip and Manim partial movies; after the join, every scene's. Kept: records (the fingerprint still
  sees edited scripts and fetched files), layout readings, `3d` guide passes, scene clips, the
  video. A scene that renders again then redraws every frame (also for title/timing/overlay
  changes, `--frames`, a bare frame thumbnail in `_bare`, `--guide-passes`).
- **Disk.** Before workers start, `disk.expected_bytes` estimates the frames clips to write (scenes
  that draw frames and lack a kept clip, full frame size, last rendered length or `duration` or
  narration estimate, `BYTES_PER_PIXEL` 1.0 lossless / 0.22 compact, an upper bound; with
  `keep_intermediates: false` only the `jobs` largest); a warning ("up to") when free disk is
  smaller names compact, `--clean-intermediates` and `--max-scenes`. After the join `build:` reports
  build size, frames-clip part, free disk, removed bytes (`--json`: `disk: {build, frames_clips,
  free, removed}`; `RenderResult.disk`, `.removed`).

### 120.10 Faster `web` rendering, measured first (Step 349)

- **Screenshot.** `WebPage.screenshot(n)` sends `Page.captureScreenshot` on vidgen's own CDP
  session with what Playwright's `page.screenshot(type="png")` sends (visual viewport from
  `Page.getLayoutMetrics` for the clip, size rounded as `enclosingIntSize`;
  `captureBeyondViewport: false`) plus `optimizeForSpeed: true` (faster PNG, same pixels). Carets
  are hidden around each screenshot (`inPagePrepareForScreenshots`). The clip's scale is the
  viewport's times the device scale (a `design_width` page's emulation is on Playwright's session);
  the time limit is vidgen's `_TimeLimit` (30 s). `WebPage.pixels(png)` decodes; `frame(n)` =
  `advance` + `screenshot` + `pixels`. Pixels equal Playwright's (`tests/test_web_speed.py`); cache
  keys and `engine_id` unchanged. Nearly all of a WebGL frame's time is the page's GL work
  (SwiftShader), which is the author's lever.
- **Rejected** (do not redo): WebP (slower), JPEG (no alpha), WebGL canvas readback (buffer cleared
  after compositing; HTML over it missing), `Page.startScreencast` (frames not tied to vidgen's),
  `HeadlessExperimental.beginFrame` (needs BeginFrameControl), GL flags (no gain; flags are in the
  clip key), splitting a scene over pages (stateful pages must step from frame 0).
- **Pipelined writing.** `make_web_clip` draws in the main thread and hands PNGs to
  `FramesClipWriter` (`browser/frames_clip.py`), which runs `write_frames_clip` in a thread with at
  most two frames waiting; an error on either side stops both and leaves no clip or `.partial`.
- **Progress.** `FrameProgress` (`browser/frames_clip.py`, re-exported by `web/clip.py`) logs on
  `vidgen.progress` at most every `PROGRESS_SECONDS` (10 s): `web frames 30/92, 1.24 s a frame,
  about 1 min 17 s left` (rate from frames after the first), then a summary splitting the page's
  `frame(t, ctx)` from drawing and screenshot. Workers print `progress: …` (`PROGRESS_PREFIX`);
  `vidgen render` shows `[1/12] <scene>: web frames …` (`pipeline.progress_lines`,
  `_run_worker(on_progress=)`; in live mode the worker's own lines). To stdout, or stderr with
  `--json` (MCP `render` reports them as progress); left out of a failed worker's output tail.
- **First frame** may take `FIRST_FRAME_TIMEOUT_S` (= `LOAD_TIMEOUT_S`, 30 s), later frames
  `FRAME_TIMEOUT_S` (10 s), so no shader warm-up is needed in `load`; frame 0 is never drawn twice.
- **`performance.now()` stays on vidgen's clock** (§118.8), with no real-time twin: libraries
  animate from it and a real clock would make pictures depend on machine speed.

### 120.11 Ready-made finishing for three.js `web` scenes: `vidgen/three-finish` (Step 350)

- **Module** `src/vidgen/data/web/modules/three-finish.js` (MIT). Served from `/__vidgen__/modules/`
  (`web/loaded.py` `MODULES_FOLDER`; `VIDGEN_MODULES` maps import name → file, only listed files
  served), on the import map (`web/inputs.py`); the `vidgen/` prefix keeps names apart from npm.
  Package data glob `data/web/modules/*`. Imports `three`, `three/addons/postprocessing/Pass.js`
  (`FullScreenQuad`), `UnrealBloomPass.js`; no `Math.random`. Exports `Finish`, `softShadows`,
  `studioEnvironment`, `nebulaSky`, `surfaceFinish` and helpers. User reference:
  `docs/CONFIG.md#web` ("Finishing three.js scenes"), `docs/COOKBOOK-3D.md`,
  `examples/three-finish`.
- **Cache keys.** An importing page records `__vidgen__/modules/three-finish.js` with its SHA-256
  among loaded files (§118.10), so its keys follow the module. The import map is in no key
  (`engine_id` hashes `clock.js`, `media.js`, `runtime.js`, `canvas.html`, flags, versions).
- **Chain** (`Finish.render(t)`): options resolved (functions of `t` called); scene into a
  half-float target with depth at `renderScale` (linear light); motion blur draws `update(t_i)` at
  `t_i = t + ((i + 0.5)/N − 0.5) × shutter/360/fps` with weight 1/N, nearest-to-`t` last (its depth
  used), `update(t)` again if no sample falls on `t`; options re-read; depth of field or a copy;
  `UnrealBloomPass` in place; grade pass (fringe, exposure × filter × luminance-normalised white
  balance, flash, vignette in linear light; three.js ACES/AgX/Neutral tone mapping with exposure
  as a constant, or the short ACES fit; saturation; sRGB; contrast, lift, gamma, gain on encoded
  values; fade) into 8-bit; FXAA and grain to the canvas (grade straight to canvas when both off).
  Quad materials are `toneMapped: false` without colour-space chunks (nothing converted twice).
  Grain seed `round(t × fps) % 4096`. All effects off equals `renderer.render` within half-float
  rounding, except fog (three.js mixes it after encoding on the canvas, in linear light into a
  target).
- **`warmUp`** (optional): `renderer.compile` plus one drawing and a 1-pixel `readPixels`; not
  `compileAsync`, whose `setTimeout` polling never fires in `load` (§118.8).
- **Depth of field.** `coc(z) = min(K |z − z_f| / z, maxBlur)` px with thin-lens
  `K = (f² / (N (z_f − f))) / 2 / filmHeight × height` (`camera.getFocalLength()`,
  `camera.getFilmHeight()`, `z_f` in mm via `unit`), or `blur` = `K` directly (px at 720p, scaled).
  Nearer samples bleed fully, farther ones only up to the pixel's own circle + 1; colours capped at
  24 before gathering. Orthographic cameras: `blur` only.
- **Soft shadows.** three.js 0.186 maps `PCFSoftShadowMap` to `PCFShadowMap` (five taps on a Vogel
  disc of `shadow.radius`, rotated by interleaved gradient noise: deterministic); `VSMShadowMap`
  blurs the map. `softShadows()` sets either; PCF radius 2–4 recommended (VSM much slower).
- **Cost.** Finishing passes are cheap; motion blur multiplies the scene's cost by its samples.
- **Limits.** No per-object motion blur, SMAA, transparent output (§118.14), MSAA of the scene
  target, or resizing after construction.

### 120.12 Review of Steps 341–350, documents, an example (Step 351)

- **Studio inspector** (`studio_app/static/inspector.js`, `choiceHtml`): a setting with `choices` is
  a list of its names; a choice writes the name, a number in the score shows as its name.
  `drawbars` is a number slider.
- **`3d` scenes share the writer and progress line**: `three_d.browser.write_clip` passes PNGs
  (`PageRenderer.png`) to `FramesClipWriter` (decoded by `PageRenderer.pixels`); `FrameProgress(
  what="3d frames")` logs `3d frames …` (no split). `FrameProgress`, `PROGRESS_SECONDS`,
  `duration_text`, `seconds_text` live in `browser/frames_clip.py` (also importable from
  `web.clip`). The `3d` clip key is the description and the engine.
- **Windows**: frames clips and stills are written through `.partial` files and `os.replace`, with a
  message when the target is open elsewhere; a clip that cannot be deleted is kept with a warning.
- **Example** `examples/signal-fire`: an orchestral cue using §120.4–§120.7, three `web_cut` scenes
  (§120.1) with `music_data: {tracks: [...]}` and `vidgen/three-finish`
  (`tests/test_signal_fire_example.py`). The instrument table is in `docs/COOKBOOK-MUSIC.md`.

### 120.13 "Escapement" as an example (Step 352)

`examples/escapement` (source only: `video.yaml`, the score, `extensions/escapement.js`,
`extensions/webcut.py`, README, `.gitignore`; no audio, video, stills, `build/` or `output/`).
Scenes use `music_data: {tracks: [...]}` (one YAML anchor); the page builds its arrays from
`ctx.music.events` (`fromMusic`), takes `t0` from `ctx.music.t0`, rounds event times to a
thousandth of a sixteenth (`grid`) to match the film's pixels, and keeps its own finishing (not
`vidgen/three-finish`). `webcut.py` stays because a `web` scene's fade-out (`outro`) is a class
attribute with no setting. Test: `tests/test_escapement_example.py` (validate only: file list,
validation, scene starts on bar lines, the score's SHA-256 with line ends normalised, no range
warnings, event counts, the page reads only `ctx.music` tracks that exist).

## 121. Music-video tools (Phase AM, Steps 358–366)

Tools for music videos made of `web` scenes (examples `examples/parallel-space`,
`examples/escapement`, `examples/signal-fire`, `examples/three-finish`): page libraries
`vidgen/music-time` and `vidgen/three-kit` (§121.1), `vidgen music plan` (§121.2), `vidgen motion
check` (§121.3), choir syllables, soloist and whisper (§121.4, §121.6), `vidgen/title-cards`
(§121.7), quieter string bow noise (§121.8). Invariants: existing examples look the same and
existing scores synthesize to the same audio, except held string notes, whose bow hiss §121.8 lowered.

### 121.1 Building blocks for music videos: `vidgen/music-time` and `vidgen/three-kit` (Step 358)

- **Modules** on the import map beside `vidgen/three-finish` (`web/loaded.py` `VIDGEN_MODULES`;
  files in `data/web/modules/`). Every exported name: `docs/CONFIG.md#web`.
  - `vidgen/music-time`: plain JavaScript, no imports (so it serves Canvas/SVG pages and runs in
    Node in tests): shaping (`clamp`, `mix`, `smoothstep`, `smootherstep`, `easeOutCubic`,
    `dbToGain`), seeded numbers (`rng` = mulberry32, `hash`), moves (`keyframes`, `glide`,
    `orbit`, `pathPoint`, `flyThrough`: a Catmull-Rom path through every point, ends continued),
    bars (`barClock`, `count`), `colourScript(stops, glide)`, events as arrays
    (`trackArrays(ctx.music, {hits, notes, grid})` → `{t, g}` / `{t, d, p}` `Float32Array`s;
    `lastIndex`), reactions (`hitEnvelope`, `hitCount`, `hitAge`, `noteAt`, `noteEnvelope`,
    `noteLevel`, `melody` on arrays; `eventLevel`, `signalLevel` on `ctx.music` events, as they
    need dynamics), `reactions(ctx.music, react, {drops})`.
  - `vidgen/three-kit` (imports `three` and `vidgen/music-time`): `setStage`, `Glow`, colours,
    polyhedra and crystals, `SkyDome`, portals, tesseract, star fields and shells, flares, shock
    rings, glints, ribbons, spectrum rays, tunnels, lattice, ring structure, crystal fields and
    swarms, dust, `aimCamera`.
- **Code moved from the films, not rewritten**: each function keeps its arithmetic and GLSL, so
  the examples' pictures stay identical.
- **`setStage({renderer, scene, camera, width, height})`** once per page (one module instance per
  page) sets what builders need (shared uniforms `uRes`, `uK = height / 720`); a builder called
  before it throws a named error.
- **`make…` / `update…` pairs** (`makeStarField` / `updateStarField`): build in `load`, update in
  `frame` from song time, no state between frames.
- **Arrays for reactions**: binary search over a `Float32Array` per frame; `grid` rounds times to
  1/1000 of a sixteenth (§120.13).
- **Callbacks** where data varies: spectrum, fields and swarms take `band(b)`, the tunnel
  `look(index, time)` → `[colour, gain, sides]`.
- **Cache keys.** The import map is in no key; a page importing a module has it in its
  loaded-files record (clip key and fingerprint).

### 121.2 A storyboard from the music: `vidgen music plan` (Step 359)

- **Command** `vidgen music plan SCORE [--out DIR] [--force] [--json] [--max-scene S]
  [--min-scene S] ...` (`--style` and other flags: CONFIG) beside `music render`, `check`, `template`;
  without `--out` it only prints. User
  docs: `docs/CONFIG.md` "A music video from a score (`vidgen music plan`)".
- **Reads the score, not the sound** (`score_events`, §120.8). Per bar: sounding tracks, onsets per
  track, chord. Energy = 0.5 per sounding track + up to 0.5 per track for onsets (8+ a bar = 0.5),
  scaled to the busiest bar (a hi-hat cannot outweigh an orchestra).
- **Roles** (`intro`, `verse`, `build`, `drop`, `climax`, `breakdown`, `outro`): from a word of the
  section name (split on `_` and digits) when it names one, else from energy against the piece and
  neighbours (thresholds in CONFIG). Names win: the author named the form.
- **Cuts.** A scene per section; one longer than `--max-scene` (16 s) is split recursively on a
  4-bar phrase line by a change score (Jaccard distance of sounding tracks, +0.25 where the
  progression restarts, +0.5 × energy step, +0.2 after a sparse bar) plus a pull to the middle; a
  fitting section of 16+ bars is split (parts ≥ 8 bars) when the score reaches 0.45; 8-bar sections
  never. Under `--min-scene` (5 s) joins the scene before. Drops are listed as moments, not cut on.
- **Frames on bar lines**: a scene's frames are `round(end · fps) − round(start · fps)` (no drift);
  `VideoPlan` rounds `duration · fps` back to the same count. A one-pass score's last scene holds
  3 s for the last chord; a loop none.
- **Colour script**: per role a hue (intro 205°, verse 185°, build 280°, drop 325°, climax 32°,
  breakdown 250°, outro 220° pale), saturation and lightness scaled by energy, turned 8° towards
  230° in minor/dorian/phrygian keys, else towards 45°; `accent` = hue + 160°, `deep` a near-black.
  `#rrggbb` per scene and the whole script once under a YAML anchor.
- **Reactions** by the instrument a track plays in the scene: kick → pulse, melody → glints, pads →
  glow, accents → rings (hats, ticks, noise, risers left out); at most two pulses, one ring, two
  glints, one glow per scene; `music_data.tracks` lists only those.
- **Draft** (`--out`): `video.yaml` (`transition: cut`, the music cue), `extensions/web_cut.py` (a
  `Web` subclass with `outro = 0`), a page per scene from `data/web/starters/*.js` (copied verbatim,
  one look per role from the kit, everything scene-specific in `ctx.data`); the score copied to
  `assets/music/` unless already there. Validated before return (exit 1 with the problems).
- **Determinism**: seeds from the scene id (sum of character codes, not Python's salted `hash()`).
- Tests: `tests/test_music_video_plan.py`, `tests/test_web_music_video_kit.py` (Node).

### 121.3 A "watch it" motion check: `vidgen motion check` (Step 360)

- **Command** `vidgen motion check FILE|PROJECT [--variant] [--preview|--draft] [--output-dir]
  [--source scenes] [--threshold NAME=VALUE] [--fail-on] [--json] ...` (full flags: CONFIG); never renders (a project without a
  render gets the `vidgen render` command to run). Thresholds and defaults:
  `docs/CONFIG.md#motion-check-vidgen-motion-check`.
- **Input**: a file; a project's video with scenes from `timings.json` (a crossfade belongs to the
  scene starting in it); or, when missing or with `--source scenes`, the clips of
  `build/<quality>/scenes/` in order.
- **One decode**: ffmpeg scales to 160 px wide (area) and pipes raw RGB; stderr goes to a temporary
  file. Per frame: luma mean and spread (Rec. 709), RGB means, 16-bin luma histogram, 10 x 10 px
  block means (float16) and their change from 1, 2, 3 frames before. Strips re-decode only their
  frames (seek, select by frame number: exact).
- **Checks** (one cause, one finding; order blank, flash, flicker, strobe, pop; same-kind findings
  within 0.5 s merge):
  - **blank** (luma spread < 3/255): a one-frame cut into it is the fault; fades/cuts to black are
    info; start or end on black unreported. **flash**: one or two frames away by `flash` and back
    (a decaying kick pulse is not one). **flicker**: luma reversals on 60 % of a 12-frame window.
  - **Beat-locked**: hits and note starts of the project's score cues (`score_events`, with cue
    `start`, `section`, loop; pads and chords left out) make a flash, pop or flicker starting ½
    frame before to 1.5 frames after one info.
  - **pop**: blocks changing by 0.12 and back within 35 % in one or two frames while the ring around
    stays still (motion moves a neighbour too); one block is info (`pop_blocks` 2); none inside a
    flash, flicker, strobe or within two frames of a cut. **strobe**: period-2 aliasing on half a
    second's frames. **frozen**: change < 0.0015 for 1.5 s inside a scene (info). **cut jump**: luma
    step 0.2 or histogram distance 0.8 at a scene start (info). Dark-picture checks: §122.5.
- **Output**: text (errors first), `--json` (`motion` document), a contact strip per finding (two
  frames before, the finding's frames framed red, two after, 240 px each, a yellow box at a pop or
  strobe; old strips replaced). Exit 1 at `--fail-on` (default `error`). MCP `motion_check`
  defaults `fail_on` to `never`, because the server returns pictures only with `ok` true.
- Tests: `tests/test_motion_check.py`.

### 121.4 More choir: syllables, a soloist, a whisper (Step 361)

User reference (settings `syllable`, `turn`, `soloist`, `whisper`, marks, consonant timings):
`docs/CONFIG.md` "Syllables, a soloist, a whisper".

- **Rule above all.** The new settings default to the old behaviour, and a note using none of them
  (`syllable: vowel`, `soloist: false`, `whisper: 0`, no slurred note naming a syllable or vowel)
  is made by `choir.held_vowels` (the §120.6 function, arithmetic unchanged), so existing choir
  scores render to the same bytes. The new path is `studio/singing.py`, entered by
  `singing.choir_note` (the instrument's maker, remembered as before). Synthesis only, no words:
  one soft consonant (`l`, `m`, `n`, `d`) and one or two vowels per syllable.
- **The mouth is a line of keys.** A key is a mouth shape at a sample: five formants (the §120.6
  vowel table or a consonant's), optionally an antiformant (`m`, `n`) and a low-pass, and the
  voice's level. Between keys each sample cross-fades the two keys' wave tables on the singer's one
  phase (as `additive.phrase_tone`); a move is `_STEPS` = 6 shapes. A held vowel's key has five rows
  across the pitch swing; consonant and glide keys one row. Each key at equal loudness.
- **Consonants** begin the note at the step (`attack` then shapes nothing), so the vowel arrives
  80–120 ms after it; section singers enter closer together (at most 28 ms apart instead of 70).
- **Two vowels** (`ah-oh`, `oo-ah`, `oh-ah`, `ah-ee`, `mm-ah`, `mm-oh`, `mm-oo`) glide over 0.15 s
  (at most 40 % of the note) centred at `turn` (0.5). `morph` applies only to `syllable: vowel`; with
  a syllable it is a documented no-op, not an error (a later mark may switch to a syllable).
- **Slurs.** The first note sings the syllable, the others continue its vowel. A slurred note whose
  mark names a syllable or vowel (or `[default]`) carries `(syllable, vowel)` as a fourth item of
  its `Phrase` entry (`render._sung`). `score_file.FREE_IN_SLUR` = `glide`, `syllable`, `vowel`;
  other instruments' phrase entries keep three items.
- **Soloist** (`soloist`, read by `read_yes_no`: true/false, yes/no, on/off, 1/0): one mono singer
  (`singers` ignored), brighter, with a singer's formant, wider and later vibrato, a scoop and more
  breath. A setting, not a `voices` value: `voices` says who sings, `soloist` how many and how; it
  combines with every `voices` value.
- **Breath and whisper**: one noise through a filter following the keys (STFT, Hann 1024, hop
  256). `whisper` w sets the tone to cos(πw/2) and the whisper noise to 0.8 sin(πw/2) of the
  voice's level, so loudness stays within 1 dB from 0 to 1. A whispered `d` keeps its burst.

### 121.5 Review of Steps 358–361 (Step 362)

Behaviours fixed here and now part of the contract:

- **`melody`** (`vidgen/music-time`): a note's attack rises from the level the previous note has
  at the new note's start (held: 1; released: its 0.45 s decay), so legato lines do not dip; a
  first note or one after a long rest rises from about 0. `noteLevel` still starts each note from 0.
- **Range warnings** (`studio/render.py` `range_warnings`) check only instruments with a written
  range; the 20 Hz–12 kHz limit reports the others.
- **`vidgen motion check`** sends ffmpeg's stderr to a temporary file, not a pipe (a full pipe
  would block both programs).
- **MCP `music_plan`** (`score` as in `music_render`, `out`, `force`, `max_scene`, `min_scene`)
  runs `vidgen music plan` and returns its document.
- **Determinism.** The plan's seeds come from the scene id (sum of character codes, not Python's
  salted `hash()`); starters and the kit use only seeded numbers (`rng`, `hash`).
- **Cache keys.** `vidgen/music-time` and `vidgen/three-kit` are recorded in a page's loaded files
  (three-kit imports music-time, so both are); a page importing neither keeps its key.

### 121.6 The `d` without its "sht" (Step 363)

The `d` burst (`singing._singer`) lies inside the voice's band: noise around 2.4 kHz (× 1.06 /
1.14 / 1.2 for tenors, altos, sopranos and the singer's throat), 0.25 octave, low-pass 3.4 kHz
(scaled the same), 1.5 ms rise, 3 ms decay, at 0.1 of the voice. Reason: this voice model has
almost nothing above 3.5–4 kHz, so a broadband burst stood alone and, summed over a section and
the reverb, was heard as "sht". The closure, the voice's return and the formant move from the
alveolar locus (F2 from 1.7 kHz) carry the `d`. The burst draws the same random numbers as
before, so every note without a `d` is sample-identical, and plain choir notes never reach this
code. Test: `tests/test_studio_singing.py` (`la`, `da`, `de` under −50 dB above 5 kHz).

### 121.7 Opening titles and end cards for films: `vidgen/title-cards` (Step 364)

- **Module** `data/web/modules/title-cards.js` (no imports; on the import map as
  `vidgen/title-cards`; HTML and CSS, so it serves any `web` page, three.js or not).
  `titleCard(ctx, options)` and `endCard(ctx, options)` are async (wait for fonts, then measure)
  and return `{element, options, layout, update(t)}`; `update(t)` sets opacity (`cardAlpha`:
  smoothstep in over `fadeIn` from `start`, hold, smoothstep out; `hold: Infinity` holds to the
  end) and letter spacing (`cardSettle`: from fade-in to end of fade-out, or 8 s when held) and
  returns the opacity. Exported pure helpers `cardOptions` (did-you-mean on unknown options),
  `cardAlpha`, `cardSettle`, `cardLayout`, and `TITLE_DEFAULTS`, `END_DEFAULTS`. Options:
  `docs/CONFIG.md#web` ("Opening titles and end cards").
- **Defaults** follow Escapement's cards in a unit `k`: title → rule 0.75 × title size, rule →
  subtitle 1.7k, then 1.65k; end card lines 4.1k below, line height 1.65; title defaults cool,
  end defaults warm. Timing: 2 + 2 + 8 + 2 s (start, fade in, hold, fade out); end card 1 s, 2.5 s
  fade, held.
- **Size unit.** `k` = 1 % of the width of a 16:9 frame, or of height × 16/9 when wider (21:9 does
  not grow the type), and 1.7 % of the width in portrait. A line wider than its block is set
  smaller once, measured after fonts load at the widest spacing; italic lines wrap instead.
- **Placement.** Landscape `left`: x 5.5 %, block 40 % wide, centred at 46 % of the height;
  `right`: x 51 %, 43.5 % wide, at 45 %. Portrait: `left`/`right` go to the lower part (centre
  64 %), aligned by `align`; `top` centres at 24 %. Margins 8 % of the width in portrait, 5.5 % in
  landscape.
- **Shade.** A linear gradient from the block's edge: `shade` (0.45) black at the edge, 55 % of it
  at 32 %, none at 62 % (55 % for top / bottom), fading with the card.
- **Lint.** Cards are page text with `data-vidgen-id` `title-card` / `end-card` and
  `data-vidgen-lint="off:min_font"` (the subtitle is deliberately under `min_font`); hidden cards
  are `display: none`, so lint skips them.
- `endCard` has a neutral `link` line; what link goes there is the project's choice.
- Tests: `tests/test_web_title_cards.py`.

### 121.8 The strings without the "fo" of a slow, soft note (Step 366)

`strings.py` `_rosin_room`, applied in `_bow_noise` to held and tremolo notes (the held player
also returns `bitten`, its share of the full tone per sample; a section's is the players' mean):
in each octave band of the hiss (from half the bridge hill up to 12 kHz) the hiss may stand out of
the tone no more than it does in an ordinary note (`brightness` 0.5, or the note's own if
brighter) at full bow. The limit comes from the note's own and darker spectra mixed as `bitten`
says, on a grid of 21 steps (one small table per note). Reason: a dark or swelling note has little
above 4 kHz, so a hiss that only followed the level stood alone there (heard as breath). An
ordinary or bright note at full bow is unchanged; spiccato, pizzicato and the scratch at a bitten
start are untouched; scores with soft or dark held string notes have less hiss. Tests:
`tests/test_studio_strings.py`.
## 122. Space scenes (Phase AN, Steps 367–378)

three.js `web` scenes for space built from ready-made parts on the orbit model of §98, instead of
motion written in JavaScript. Owner's rules: positions and timing are **true by default**
(enlarged bodies or compressed distances are explicit, labelled choices); the sky is algorithmic
from a seed by default, a real star catalogue as an option. Parts: orbit bridge (§122.1–122.3),
`vidgen/space-scale` (§122.4), dark-picture checks and the parts registry (§122.5),
`vidgen/space-sky` (§122.6), `vidgen/space-bodies` (§122.7), `vidgen/space-light` (§122.8),
`vidgen/space-phenomena` (§122.9), `vidgen/space-craft` (§122.10), `vidgen/space-camera`
(§122.11), the declarative `space` scene (§122.12), `examples/outbound` (§122.13). Author guide:
`docs/COOKBOOK-SPACE.md`.

### 122.1 The third dimension of the orbit model (Step 367)

Which orbit modules are 3D:
- **3D:** `elements.py` (perifocal → reference frame by R₃(−Ω) R₁(−i) R₃(−ω); `from_state` handles
  equatorial (Ω = 0), circular (ω = 0) and retrograde-equatorial (i = 180°) orbits),
  `manoeuvres.py` (local prograde / radial / normal frame), `nbody.py`, `ephemeris.py`
  (heliocentric ecliptic J2000 with z; events by ecliptic longitude).
- **Transfers** (`orbit_parts._transfer`): circular coplanar orbits in any common plane (refused
  otherwise). The lead angle is measured in the ship's plane, atan2((r_s × r_t)·ĥ, r_s·r_t); in
  the reference plane (h_x = h_y = 0) the x–y arithmetic is kept bit for bit.
- **`nbody.py`** angular-momentum check (`angular_drift`, lint `orbit_conserved`) uses the whole
  vector (`NBodyRun.angular_xy` holds L_x, L_y); the panel's signed ΔL/L stays L_z.
- **2D by design:** `flyby.py` / the `flyby` param (`gravity_assist` refuses z; x is the planet's
  direction of motion by definition), `threebody.py` / `system:` (rotating view about z),
  `manybody.py`, `laws.py`, and the flat `orbit` scene's picture (each orbit seen from above its
  reference plane; `normal` burns show only their projection).
- **Dated presets** start on Table 1's elements of the date, then move on two-body orbits
  (μ = GM☉ + GM), not along Table 1's rates (within the table's accuracy over a year).

**Reference planes.** Planets, the Moon and Halley are measured from the J2000 ecliptic; `iss`,
`geo` and the Galilean moons from their planet's equator. `OrbitPreset.plane` (`ecliptic` /
`equator`) says which. The flat `orbit` scene draws each orbit from above its own plane (so `iss`
and `moon` in one Earth-centred scene mix planes, hidden by the top view); the `web` orbit data
turns equatorial orbits into the ecliptic (§122.3).

### 122.2 Body rotation data (Step 367)

`vidgen.orbits.rotation` (`ROTATIONS`, `RotationModel`, `rotation_model(name)`): the IAU WGCCRE
model per body — pole α₀, δ₀ (ICRF, degrees, constant + rate × T Julian centuries), prime meridian
W (degrees, constant + rate × d days from J2000.0 TDB), periodic terms (`Term`, `ARGUMENTS`) — and
radii, for the Sun, the eight planets, the Moon, Io, Europa, Ganymede and Callisto. Sources: WGCCRE
2015 (Archinal et al. 2018), 2009 (Archinal et al. 2011) for Mars, Saturn and Neptune, NASA fact
sheets for published periods and tilts. Values were written without network access and are not
checked against the documents (`RotationModel.check`); Neptune's W is unsure. Simplifications: the
Earth has no ΔT (W about 0.3° off), the Moon keeps E1–E2 only, Mercury no libration, Mars no 2015
periodic terms. An unknown name raises `VidgenError` with did-you-mean (`sol`/`luna` aliases).

Tests compare each formula period with the published one (2 × 10⁻⁴), each planet's tilt (pole vs
Table 1 orbit normal) with the fact sheet (0.05°), the Galilean periods with `GALILEAN_PERIODS`.
ICRF → mean ecliptic and equinox of J2000 by ε = 84,381.448″ (`OBLIQUITY_J2000_DEG`; frame bias
ignored). A body's frame: x towards its prime meridian, z its IAU north pole (Venus and Uranus
turn backwards about it); `frame(jd)` = E · R₃(α₀ + 90°) R₁(90° − δ₀) R₃(W). `equator_frame` (x the
ecliptic's ascending node on the body's equator, z the pole) turns orbits measured from an equator
into the ecliptic. Pluto, Ceres, other moons and bodies of the author's own have no rotation data.

### 122.3 Orbit data for `web` scenes: `orbit_data:` → `ctx.orbits` (Step 367)

Built like `music_data` (§120.8): declared in the scene, computed in Python, cached, in the keys,
given to the page by a helper script.

- **Interface.** `web` param `orbit_data:` (`vidgen.scenes.orbit_data.OrbitData`, pydantic) takes
  the `orbit` scene's models and words — `central`, `bodies` (`OrbitBody`: presets, elements, state
  vectors, `around`, `alongside`, `burns`; drawing keys accepted and unused), `span` / `orbits`,
  `dynamics` / `method` / `step`, `transfer`, `flyby`, `system`, `date` — plus `speedup`
  (simulated seconds per scene second, instead of a span), `planes`, `path_samples`. Resolved by
  the same `resolve_model`, so errors read as in the `orbit` scene
  (`scenes[1].params.orbit_data: ...`, did-you-mean). Labels are translatable and reach the page
  as `label`. With `speedup`, validation builds a stand-in model whose dates are not checked
  (`check_dates`); the data made for the scene's length is.
- **Time base.** Frame n shows simulated time `span × min(n, N) / N`, N the scene's own frames
  (beats or duration plus fade-out; the clip's 2 spare frames hold the end): one constant speed-up
  from frame 0, no entrance. t = 0 is `date` (default J2000.0 TT, the presets' epoch). The page
  gets `time`, `jd`, `index`.
- **Units and frame.** SI (m, m/s, s, rad), mean ecliptic and equinox of J2000 (x the equinox, z
  the ecliptic north pole), origin the central body; a `flyby` stays in the planet's frame
  (`frame: flyby`, x along the planet's motion round the Sun): its pole (rings) and the `space`
  scene's default sun are turned into that frame from the planet's motion on the date
  (`orbits.ephemeris.flyby_axes`, JPL elements; the Sun stands near +y). Orbit plane per body: `planes`, default the preset's `plane`; a body of one's
  own around a body with rotation data uses its equator, around the Sun the ecliptic; `alongside`
  takes the other body's. An `equator` orbit's state relative to its parent is turned by the
  parent's `equator_frame` at the start date (pole held for the scene), then parents are chained as
  `System.position` does. With `dynamics: nbody` or a `flyby` every body stays `as_written`
  (asking for `equator` is refused); a transfer between bodies in different planes is refused.
- **Rotation.** Per frame, for each body with rotation data: a quaternion (x, y, z, w; w ≥ 0) and W
  (rad). A tidally locked moon (the Moon, Galilean moons) orbiting a body of the data faces it: x
  is the direction to its parent projected on its equator (the model places these moons by phase,
  not by date, so the IAU meridian would not face the planet); W is measured from the IAU node.
- **A body carries** `name`, `key`, `parent`, `label`, `color` (theme token), `gm`, `radius`,
  `plane`, `rotation` (period, retrograde, synchronous, faces_parent, unit pole and spin axis, α₀
  δ₀, computed tilt vs its orbit normal at the start (the Sun: vs the ecliptic), published tilt,
  radii, source, note), `orbit` at the start (a, e, i, raan, argp, nu, period, kind), `burns`
  (number, time, first frame at or after it, Δv in the data frame, prograde / radial / normal
  parts, size, direction, label), and base64 little-endian float64 series `position`, `velocity`
  (frames × 3), `quaternion` (frames × 4), `spin`, `path` (`path_samples` points over the span,
  relative to the parent), `conic` (the start orbit, 361 points). The data names its
  `approximations` in words.
- **A spacecraft** is a body: on a `transfer` or with `burns` it follows its Kepler arcs through
  impulsive burns; a `flyby` probe is a body of the planet's frame.
- **Precision.** float64 end to end, read without interpolation at the frame the time falls on;
  values equal `OrbitModel.position` / `velocity` at frame times bit for bit (tests:
  `tests/test_orbit_data.py`). The page subtracts the camera position in float64 before handing
  float32 to three.js (§122.4); `yUp` / `yUpQuaternion` give three.js axes.
- **Cache and keys.** `vidgen.web.orbits.scene_orbit_data` (in `vidgen.api` as
  `web_scene_orbits`; the maker `make_orbit_data` lives in `vidgen/scenes/orbit_data.py`, which
  imports only `vidgen.api`) caches `build/orbits/orbit-data-<key>.json`; the key holds the data
  version (`ORBIT_DATA_VERSION`, 2), vidgen's version, the SHA-256 of the orbit code (`vidgen/orbits/`, `orbit_parts`,
  `orbit_sky`, `orbit_systems`, `orbit_data`), the settings, the frame rate, the frames drawn and
  the scene's own. Nothing is added to the render fingerprint (params, beats' audio and source are
  already in it). Clip inputs get `orbits: {data: SHA-256 of what the page is sent, helper:
  SHA-256 of orbits.js}` only for a scene with `orbit_data`; `orbits.js` is an init script added
  only on those pages (like `music.js`), so `runtime.js`, `engine_id()` and other clip keys are
  unchanged. Same settings → same JSON.

### 122.4 Scale: `vidgen/space-scale` (Step 368)

float32 cannot hold 1.5 × 10¹¹ m + 10 m, one depth range cannot hold a 100 m ship and a planet
4 × 10⁸ m behind it, and world-coordinate shaders lose everything. `data/web/modules/space-scale.js`
(`vidgen/space-scale`, in `VIDGEN_MODULES`, imports only `three`) places `ctx.orbits` bodies each
frame. User docs: docs/CONFIG.md (`web`, "Astronomical scales").

```js
const space = new SpaceView(ctx, {renderer, scene, camera, mode: "true"});   // or "enlarged" + enlarge, or "log"
space.add(earthMesh, {body: "Earth"});    // radius-1 mesh drawn at the body's radius (times its factor)
space.add(shipGroup, {body: "Ship"});     // no radius in the data: built in metres
space.path("Moon", {kind: "conic"});
// frame(t): space.update(t, {from: {body: "Ship", offset: [-200, 0, 50]}, to: "Ship"}); renderer.render(scene, camera);
```

Options (`DEFAULTS`): `orbits`, `renderer`, `scene`, `camera`, `mode: "true"`, `enlarge: 1`, `depth:
"split"`, `ratio: 1e4`, `join: 3`, `maxSlices: 8`, `near: 0.01`, `dofFocus: null`, `r0: null`;
unknown options and values throw with did-you-mean.

- **Floating origin.** Positions stay float64 in the data frame until the camera position is
  subtracted in JS doubles; the three.js camera stands at the origin (y up). At a frame the data's
  values are used; between frames (motion-blur sub-frames) a cubic Hermite of the two frames'
  positions and velocities. Paths (`path(name)`, ≤ 4,096 points) are rebuilt camera-relative every
  frame.
- **Depth** `split` (default), `log` (renderer with `logarithmicDepthBuffer: true`) or `single` (one
  range fitted per frame). `split` because it needs no shader chunks, keeps three-finish's 24-bit
  depth chain and page keys unchanged, and gives right depth of field with `dofFocus` (three-finish
  reads `log` depth as perspective).
- **How `split` works.** It replaces the renderer's `render` for its scene and camera (three-finish
  calls and sub-frames pass through; `dispose()` restores it). Per call: the view-depth interval of
  every visible mesh, line, point cloud and sprite (bounding sphere; inside one, the distance to a
  round body's surface or a path's nearest segment; an object outside its sphere but beside the view
  begins at (distance − radius) × the frame corner's cosines); overlapping intervals form a stretch;
  a stretch over `ratio` is cut into equal ratios (overlap 10⁻⁴; 10⁵ lets a 100 m shell fight);
  separate stretches get own slices unless together within `join`; at most `maxSlices`
  (`depthSlices(intervals, {ratio, join, maxSlices, near})`). Drawn far to near, depth cleared
  between; `scene.background` and the clear only on the first pass; shadow maps in the first pass
  that draws the world (the sky pass hides every caster). A slice draws only things whose interval
  reaches it. The sky (`scene.background`, `userData.sky = true`, or `frustumCulled = false` with
  negative `renderOrder`; `userData.sky = false` opts out) is drawn first with its own near and far.
  `userData.overlay` objects (§122.8's glare) skip the intervals and are drawn once after the last
  slice. Depth of field reads the last slice's depth; `dofFocus` (metres, an object or a function of
  t) redraws depth from focus / 10⁵ to the farthest thing, nearer things at 0.
- **Path lines near the camera.** A line's interval begins at `nearest × 0.999 × cx × cy` (corner
  cosines). Software GL drops a segment far longer than its distance, so `nearCuts(a, b, d, spare)`
  cuts one over 4× its distance at the nearest point and d, 2d, 4d, … each side (≤ 48 a segment,
  `PATH_SPARE` 96 spare points a line, with a draw range); pieces stay on the same straight line.
- **Scale modes.** `true` (`enlarge` ≠ 1 refused), `enlarged` (radii × `enlarge`: a number or
  `{default, <body>: factor}`, a factor ≠ 1 required; distances true), `log` (r → AU · log10(1 + r /
  r0) along the same direction, r0 a third of the smallest periapsis round the central body — the
  flat `orbit` scene's `radial: log`, `LOG_R0_SHARE`, `log_r0`, equal to `OrbitSky._radial`; in 3D r
  is the whole distance). Mode names match `vidgen.orbits.accuracy.PICTURES` (narration claims).
- **Notes.** `scaleNote(mode, {enlarge, words})` / `space.note()` → `{lines, text}` (joined with " ·
  ") in the flat scene's words ("sizes not to scale", "bodies enlarged 50×; distances to scale", per
  body "1000× (Sun 10×)", "distances compressed (log)"; nothing for `true`); not translated, `words`
  replaces them. `problems()` lists an enlarged body covering another's centre; `pixels(name)` gives
  the on-screen radius (a marker for sub-pixel bodies is the page's choice).
- **Limits.** A sphere mesh is no ground (a 512 × 256 sphere's facets lie up to 120 m under the
  surface; a unit sphere scaled to the Earth keeps vertices to ~0.4 m): closer than a few metres
  needs a local patch. Tests: `tests/test_web_space_scale.py`.

### 122.5 Checks for dark pictures; ready-made parts and their contact sheet (Step 369)

**Dark-picture checks in `vidgen motion check`** (`motion_check.py`). Finding kinds, rules and
thresholds with defaults: docs/CONFIG.md#motion-check-vidgen-motion-check. At 160 px a star field
averages to flat luma, so the 160 px checks alone saw it as blank or frozen and missed black frames
in it.
- **One decode, two pictures.** ffmpeg's filter graph splits each frame: one branch scaled to 160 px
  exactly as before (`scale=W:H:flags=area`, rgb24), the other to `detail_width` (640, area); both
  stacked into one raw picture per frame on one pipe. The 160 px bytes are identical to the
  single-picture command (a test compares them). A source no wider than 160 px gets the old
  command; `--threshold detail_width=0` turns the finer picture off.
- **Only dark frames** (`dark_share` of 160 px pixels under `dark_level`) are measured on the finer
  picture: star points (brightest of a 3 × 3, `star_contrast` above its 5 × 5 ring, ring at most
  `star_ring` of it), subject share, clipped share, banded share, change against the first frame of
  its still stretch, star shimmer.
- **Rules.** A star field (`star_field` stars or a `subject_area` subject) is not blank (out of every
  check's blank mask); black frames entered from or left to a star field or a subject are `blank`
  (error inside a scene, info at a cut, nothing at the video's ends), as is a subject gone and back
  within `vanish_seconds`; a dark frame is unchanged only if the finer picture is too (can only
  remove `frozen`); `clipped` only in dark frames; `shimmer` uses the median star's jump (lines
  crossing stars spoil a mean), takes out the pan most bright stars share (`shimmer_reach`) first,
  judges only point stars (`shimmer_point`) and frames where most stars are found again; `banding`
  needs a staircase of three steps the same way (grain makes up-and-down steps); `empty`; `lost`
  only in scenes named with `--subject SCENE` (repeatable, `all`, MCP `subject`; an unknown id is
  an error before decoding), because only stars may be meant.
- Not found: aliasing that crawls at even brightness; shimmer of under half the stars; banding
  outside dark frames; a grainy film's dark frames never count as frozen.

**Ready-made parts registry.** `data/web/modules/parts.js` (`vidgen/parts`, imports only `three`):
`definePart(info, make)`, `parts({kind, name})`, `part(name)` (did-you-mean), `buildPart(name, stage,
options, seed)`, `defaultStage(width, height)` (black background, 40° camera at (0, 0.8, 6) looking
at the origin, warm key, faint fill), `KINDS` (sheet order: `sky`, `body`, `light`, `craft`,
`craft-part`, `phenomenon`, `camera`, `structure`, `effect`, `environment`). `info` = `{name, kind,
module, label, use, options, seed, at}` (`use` the one line a page writes, `options` the defaults
`make` reads with colours as `"#rrggbb"`, `at` the time shown). `make(stage)` gets `{scene, camera,
key, fill, renderer, width, height, ctx, options, seed, part}`, adds the part (may move the camera,
change lights, set `scene.background` / `environment`), may return `{frame(t)}` and `{finish:
false}`.
- **Parts files beside the modules**: `data/web/parts/<module>.js` (served as
  `__vidgen__/parts/<file>`, imported as `vidgen/parts/<file>` via an import-map prefix), not inside
  the module, because a module's bytes are in the clip keys of every page importing it; the sheet
  imports only the parts files, so `definePart` calls belong there.
- **The description is JSON**, so Python reads it without a browser: the first argument of each
  `definePart(` is parsed with braces matched outside strings and `json.loads`; a non-JSON
  description is an error naming file and line. `KINDS` and required fields are equal in Python and
  JS (test).
- **The sheet page** `data/web/parts-sheet.js` (the only file of a `script:` scene in a temporary
  folder) imports the parts files `ctx.data.files` names, makes one `WebGLRenderer` (stencil on), and
  at frame n (fps 1) disposes part n−1 and builds part n on `defaultStage` at `at`, through
  three-finish with `grain: 0` and bloom 0.12 / radius 0 / threshold 1 (stronger bloom washes small
  tiles). Python lays out tiles (`WebPage.frame`, Pillow): name, kind, label, `use` line in JetBrains
  Mono (cut with "…").

**`vidgen parts`** (`web/parts.py`, CLI `cmd_parts`, MCP `parts`): `[NAME ...]` (names or `fnmatch`
patterns, did-you-mean), `--kind`, `--list` (text by kind or `--json`; no browser), `--out` (default
`parts_sheet.png`; PNG or JPEG), `--size WxH` (default 320x180, one part 960x540; even, 48–1920),
`--columns` (default up to 5), `--time-limit` (default 300 s; later tiles are left out and named in
the title; the first is always drawn). **Adding a part:** the module in `VIDGEN_MODULES`, then
`data/web/parts/<name>.js` with one `definePart({...JSON...}, (s) => {...})` per part (a `KINDS`
kind, `label`, `use`, `options`, `seed` when random, `at`, `make` aiming `s.camera` to fill the
tile); nothing else (sheet, `--list` and MCP read the folder); the slow test
`tests/test_web_parts.py::test_the_contact_sheet_draws_every_part` fails on a black tile.

### 122.6 The sky: `vidgen/space-sky` (Step 370)

`const sky = spaceSky(renderer, {seed}); scene.add(sky.object)` (or `{stars: "real"}`).
`data/web/modules/space-sky.js` (`vidgen/space-sky`, in `VIDGEN_MODULES`; imports `three`, `rng` of
`vidgen/music-time`, `yUp` of `vidgen/space-scale`, and `vidgen/space-sky-stars`). Its own module,
not an extension of three-kit's music-video skies (`SkyDome`, `nebulaSky`, `makeStarField`,
`makeStarShell`, unchanged), which have no magnitudes. Options and defaults (`DEFAULTS`: `seed` 1,
`stars` `seed` | `real`, `look` `natural` | `rich` | `sparse` (`LOOKS`, option sets the page's own
options override), `limit` 8.5, `contrast` 0.8, `nebulae` / `galaxies` 0 (at most 12 each), …):
docs/CONFIG.md (`web`, "The sky of a space scene"). Errors throw with did-you-mean.

**Two layers, both made once.**
- **Stars to magnitude `limit` are GL points** (≈ 69,000): a gaussian spot of sigma 0.75 px at 720p
  (scaled with frame height, never under `MIN_SIGMA` 0.62 px) plus a halo. A spot that wide keeps
  its summed light as it slides between pixels: this is what prevents shimmer. Stars whose middle
  exceeds 1.2 (≈ mag 2.3) are instanced quads (halo wider than a GL point may be); points for the
  rest because quads cost ~20× more in SwiftShader.
- **Everything fainter is baked into a cube map** (half float, mipmaps, 1024 px a face for frames ≥
  600 px tall, else 512; `size`): the Milky Way, faint stars, nebulae, painted galaxies. Each face is
  drawn by a full-screen quad computing its direction as OpenGL addresses a cube map, so the sky
  shader and `scene.background` both read it right. Nebulae and galaxies are separate scissored
  passes over the texels they touch (`faceWindow`; a SwiftShader branch costs as much as its body).
  Through a long lens the shader measures a texel in pixels (`fwidth` of the view direction) and
  past `LENS_PIXELS` (2.5) reads level `LENS_SOFT` (1.5) × log2(texels / 2.5) (same mean light).
- Not a cube alone: one sharp enough for stars at 720p needs 2048 px faces (≈ 270 MB) and still
  softens under lenses over 40°.

**Counts and light.** `STAR_COUNTS` (whole-sky stars brighter than a magnitude; log-linear between
rows). A seeded sky takes the ranks evenly spread (every seed has its Sirius and its counts),
gathers fainter stars toward the band, adds open clusters. Colour: B−V from five groups →
`temperature` (Ballesteros) → `blackbody` (linear sRGB), 0.7 of the way from white. `starAmplitude`:
mag 2.5 is 1.0 linear; to mag 4 each magnitude 10^(−0.4 × 0.85), fainter 10^(−0.4 × `contrast`) (a
photograph's stretch), mag 8.5 at 0.011 above the ACES toe; above 1.0 light grows with the square
root. Below 595 px frame height light is thinned by (natural sigma / 0.62)^1.2.

**The band**: a sech² disc round a wandering midline, star clouds, a warmer bulge, a faint halo;
dust is a continuous optical depth, light × exp(−τ × (0.78, 1.0, 1.34)) (a threshold looked like
clouds at night).

**The real sky** (`stars: "real"`): RA/Dec J2000 turned about x by `OBLIQUITY` 23.4392911° into the
J2000 ecliptic of `ctx.orbits`, then to y up as `vidgen/space-scale` does (`skyDirection` =
`yUp(equatorialToEcliptic)`), so the sky agrees with the planets (tested against
`make_orbit_data`). The band uses the real galactic frame (`GALACTIC`) but the algorithm's clouds
and dust. The Magellanic Clouds and Andromeda are painted at their places. Stars fainter than the
file's `complete_to` are seeded.

**The star file** `data/web/modules/space-sky-stars.js`: an ES module whose default export is one
JSON object (JS imports it statically, Python reads it): `{"catalog", "approximate", "epoch",
"complete_to", "columns", "stars"}`, rows `[ra_deg, dec_deg, v_mag, b_minus_v]` or `[..., "Name"]`,
degrees to 0.001, magnitudes to 0.01; `catalog` and `approximate` appear on `sky.info`.
`tools/make_star_catalogue.py` writes it: `--fixture` from its own table of 221 well-known stars
written from memory (`"approximate": true`, `complete_to` 2.5), or from the Yale Bright Star
Catalogue's fixed-width file by path (bytes 76–90 position, 103–107 V, 110–114 B−V; entries without
a position skipped; a line that does not fit stops it; under 8,000 stars refused; `.gz` read). The
shipped file is the fixture: the BSC is not shipped (no formal licence; owner's decision); vidgen
downloads nothing.

**Drawing.** `sky.object` (cube box, points, quads): `frustumCulled = false`, `renderOrder` −1000 to
−998, no depth test or write, positions from the view rotation only (follows any camera;
`vidgen/space-scale`'s sky pass). Linear light: into a render target written as is with ≈ one code
of noise in the dark; straight to the canvas it applies ACES + sRGB and dithers, each star the step
from sky to sky + star after the curve (`display` overrides). `sky.background` (whole sky in one
cube) and `sky.environment` (PMREM of a 256 px copy) are made on first use. `sky.direction(name)`:
`"center"`, `"anticenter"`, `"pole"`, `"nebula N"`, `"galaxy N"`, a named star, or `{l, b}`.
Disposing the material frees the cube maps.

**`spiralGalaxy(options)`** (foreground): a `THREE.Group` (disc in x–z) of additive gas sprites,
dark dust sprites and star points; fixed draw order (glow, stars, dust), not a sorted volume; needs
a tone-mapped chain.

Use three-finish with `antialias: "none"` for star fields (FXAA smears an off-grid star into a
cross). Parts (`data/web/parts/space-sky.js`): `space-sky*`, `spiral-galaxy`,
`space-sky-environment`; skies return `{finish: false}`. Limits: no proper motion; dust does not dim
point stars; no orthographic camera. Tests: `tests/test_web_space_sky.py`.

### 122.7 Planets, moons and rings: `vidgen/space-bodies` (Step 371)

`const earth = planet(renderer, "earth"); scene.add(earth.object); earth.update(t, {sun})`; with
orbit data `planet(renderer, "Saturn", {space})` places, sizes, tilts, turns and lights it.
`data/web/modules/space-bodies.js` (`vidgen/space-bodies`, in `VIDGEN_MODULES`; imports only
`three` and `rng` of `vidgen/music-time`). Every surface is generated; no real map or image is used
or imitated. Types (`TYPES`: `rocky`, `icy`, `desert`, `ocean`, `lava`, `gas`, `ice-giant`), their
options and defaults, palettes, airs, rings, the 21 `PRESETS` worlds (Solar System lookalikes with no
real geography, plus invented ones): docs/CONFIG.md (`web`, "Planets, moons and rings"). A wrong
key, name or value throws with did-you-mean.

**How a body is drawn.** One mesh (a 48 × 24 sphere drawn from its back faces, a little larger than
body and air) whose fragment shader works each pixel out from the view ray in the body's axes:
- *Exact limb*: analytic ray–sphere, anti-aliased by the ray's pixel distance from the limb (no FXAA
  or MSAA needed). `oblateness` scales the mesh along the pole; normals use the inverse transpose.
- *Depth per pixel* (`gl_FragDepth`: the surface point, or the tangent point for air-only pixels):
  the shell hides and is hidden correctly, works in every `vidgen/space-scale` slice (`split`,
  `single`) and with three-finish's depth of field; not for a logarithmic depth buffer.
  Premultiplied alpha, writes depth, drawn after opaque things.
- *Surface* from two cube maps baked once: A = albedo (as its square root) + gloss above ½ / glow
  below ½; B = the relief's push on the normal (zero exactly code 128: a smooth sea has no 8-bit
  facets) + cloud deck or height. Cube maps: no pole pinch, no seam.
- *Light*: one hard sun (`setSun(direction, {color, intensity})`); Lambert mixed with
  Lommel-Seeliger (`regolith`); relief shadows by two looks toward the sun in the height channel;
  water a microfacet lobe with Fresnel; clouds cast a shadow; city lights only on the night side
  under clear sky. `body.fill` (black by default) and the `ECLIPSE` block (compiled only when asked)
  are set by `spaceLight` (§122.8).
- *Air*: gas thinning exponentially (`height` = scale height / radius), zenith optical depths
  (`rayleigh`, `haze` with a Henyey-Greenstein `forward` lobe, `absorb`). Optical depth to space is
  Chapman's function in Schüler's closed form (with its below-horizon branch), so sunlight reddens
  at the terminator and the planet's shadow falls on the air by itself. The view ray is summed in
  `AIR_STEPS` slabs (`quality` `fast` 2, `standard` 4, `fine` 8), each slab's share the exact
  difference of transmittances, so thick air saturates instead of blowing out. A shell thinner than
  a pixel is drawn 0.7 px deep with density × ratio^0.4 (no limb flicker).
- *Small bodies*: maps have mipmaps; under 2.5 px radius the disc fades into one gaussian spot
  (sigma ≥ 0.62 px, as the sky's stars) holding the disc's light (mean albedo × ⅔ × Lambert phase ×
  area); from 1.5 px down only the spot.
- *Two ways out*, as the sky: linear light into a render target (white ground facing the sun =
  `light`), or ACES + sRGB + dither straight to the canvas; light without coverage is tone-mapped as
  is, not divided by alpha.

**Rings**: a flat slab (≥ 3 px on screen) where the view ray meets the ring plane; the radial profile
(`ringProfile(seed, {style, gaps, color, opacity})`, `RING_STYLES` `broad` / `narrow`) is a 1024 × 1
mipmapped texture read at the pixel's radial footprint, so grazing views average ringlets instead of
aliasing. Light: Chandrasekhar single scattering in a thin layer × 3.0 / 1.8 for multiple
scattering, plus a forward lobe for dusty parts. Globe shadow on rings by ray–sphere toward the sun
(in oblate space) with widening penumbra; ring shadow on the globe from the profile where the sun ray
crosses the plane. Far half drawn before the globe, near half after (three meshes, creation order).

**The bake** (`bakeBody`): per cube face three full-screen passes — coarse fields (three 128 px float
cubes); vec4(height, three fields) in a 32-bit float cube (half float without the extension; no
terraces); paint → A and B with mipmaps. Noise: hashed gradient noise with the cube's eight diagonals
as gradients. Placed things from the seed in JS (`bakeInputs`); small craters a cell lattice, one
size class per octave. Map `size` 256–2048, default 512 from 300 px frame height, 1024 from 900 px.
Time bake stages with `gl.finish()`; the mipmap draw needs `autoClear` off or the last face is
cleared. `drift` / `cloudDrift` use flow mapping (two map copies turned by a latitude-varying wind,
half a cycle and back, cross-faded), so the map never winds up.

**With `ctx.orbits`.** `planet(renderer, "Saturn", {space})` finds the body by name or preset key
(`{body}` says which), adds itself to the `SpaceView` (unit radius → data radius × enlargement);
`update(t)` takes pole and turning from the data quaternion and the sun direction from the data's
Sun (else `update(t, {sun})` / `setSun`). `{orbits: ctx.orbits}` without a `SpaceView` gives turning
and sun only. **Spin:** default `spin: "true"` (the data's turning); `problems()` warns in words over
12° a frame (`turnPerFrame()`); stated alternatives keep the pole true: `"locked"` and `spin:
seconds` (one turn per so many film seconds, negative backwards). Without orbit data `spin` is
seconds per turn, or none.

**Interface.** `planet(renderer, what, extra)` → `Body`: `object`, `update(t, {sun})`, `setSun`,
`sun`, `fill`, `problems(t)`, `turnPerFrame(t)`, `options`, `rings`, `uniforms`, `material`,
`dispose()`. Pure helpers: `resolveOptions`, `bakeInputs`, `bandRamp`, `ringProfile`, `levelFor`,
`sizeFor`, `phaseLight`, `spotSigma`, `pointShare`, `onGlobe`, `linearColor`; constants `TYPES`,
`PALETTES`, `PRESETS`, `AIRS`, `QUALITIES`, `AIR_STEPS`, `RING_STYLES`, `VERSION`. Parts
(`data/web/parts/space-bodies.js`, kind `body`): `body-<type>`, `world-<preset>`, `rings-*`,
`body-crescent`, `body-limb`. Use `antialias: "none"` in three-finish (FXAA breaks thin rings).

**Limits.** One texel per 20 km on an Earth at 512 (no landing); relief is shading, the limb always a
smooth circle; one flat cloud deck; single scattering with a correction; rings without thickness or
spokes; ringed bodies overlapping in one depth slice sort by centre; no orthographic camera. Default
exposure keeps the stars beside a day side (a film convention, §122.8). Tests:
`tests/test_web_space_bodies.py`.

### 122.8 Suns and light: `vidgen/space-light` (Step 372)

`const sun = star(renderer, "sun"); scene.add(sun.object); sun.update(t)` and, for a scene's light,
`const light = spaceLight({scene, camera, sun, bodies, sky}); light.update(t)`.
`data/web/modules/space-light.js` (`vidgen/space-light`, in `VIDGEN_MODULES`; imports `three`, `rng`
of `vidgen/music-time`, `blackbody` of `vidgen/space-sky`). It computes the hooks
`vidgen/space-bodies` leaves open (`setSun`, `light`, `body.fill`, `ECLIPSE`). Star kinds, options
and defaults (`STARS`, `STAR_DEFAULTS`, `LIGHT_DEFAULTS`): docs/CONFIG.md (`web`, "Suns and light");
errors throw with did-you-mean.

**A star close up**: two back-face shells round one place, drawn in creation order, each pixel from
the view ray (as §122.7). *Globe*: exact limb, depth per pixel; cells boil in place (nearest /
second-nearest of lattice points each circling its own place; nothing scrolls), cells under ~2 px
left out; a function of t alone; limb law I = μ^(0.3, 0.55, 0.95) per colour for cool stars, (1.0,
0.66, 0.3) for hot; seeded spots (`starSpots`), faculae, limb loops (`starLoops`). *Corona* (shell
of `reach` radii, additive, no depth write): a function of where the ray passes nearest the star;
the angle round the disc reads a JS-made cube map (`coronaFaces`: R streamers, G finer structure, B
rays, A active ground), so streamers stay rays in any lens (reading by the nearest point's 3D
direction turns them into clouds in close-ups). `starTint`: a black body's colour pushed three
times as far from white (a film's sun is yellower than the real white one).

**Three places**: an object (radius 1); the Sun of `ctx.orbits` (`star(renderer, "Sun", {space})`);
or **in the sky** (`{direction, angularRadius}`, default 0.2665°: meshes moved round the camera
before each draw, unculled so `vidgen/space-scale` draws them in the sky pass, writing far depth so
every body covers them).

**The far sun's glare.** Under 30 px radius at 720p (fading out by 140 px) the star is a point drawn
by one more mesh, a `userData.overlay` object (§122.4), in the frame's own axes (spikes neither
rotate nor flicker): a core (≥ 0.62 px), three halos, `spikes` (≥ 0.62 px across with light kept),
six cool lens ghosts on the line through the frame's middle. Gone a third of a frame outside. Adds
into a linear picture; on the canvas it is screened after the star's ACES.

**What hides the sun** (`sunVisibility`, `star.visibility(camera)`; no read-back, no state): 96 fixed
disc points (sunflower); each ray's nearest distance to every occluder between eye and sun gives a
soft step, times the air's transmission exp(−ext × tangent column) with the bodies' Chapman column.
Mean = the glare's light per colour; light-weighted mean position = where it sits (a sun setting
behind a world with air dims, reddens and slides along the limb). Rays are straight. Occluders
(`star.occluders`): `spaceLight` sets the bodies of `vidgen/space-bodies`; a page adds balls, e.g.
`craft.shade(star)` (§122.10) or a named rock (§122.9).

**`spaceLight(options)`** → `SpaceLight`. `update(t)` runs after bodies, star and camera stand at t;
no state between calls:
1. *Each body's sun*: direction from body to star (camera-relative positions work as is), or one
   direction for all; `body.setSun(direction, {color, intensity})` with `sunlightColor` (white for a
   sun-like star, 0.7 of the way to the black body relative to the Sun's for others).
2. *Distance*: `falloff: 0` (a stated artistic default: every world lit as if exposed for it);
   `falloff: 2` is inverse square from `reference` (default the first body).
3. *Fill* (`body.fill`): the stronger of planet-shine (`planetShine`: (2/3) × albedo × (radius /
   distance)² × Lambert phase, ≤ albedo; source colour read once from its smallest baked mip) and
   ring-shine (`ringShine`: 0.125 × opacity × |sin sun height over the rings|); one source a body,
   never added. In `film` the tiny honest values are lifted by the stated convention `filmShine` =
   0.236 × honest^0.158, × `shine` / `ringShine`.
4. *Eclipses* (`eclipses: true`, opt-in because it recompiles the bodies' shaders): up to 4 bodies
   between a body and the sun; with s along and d across the sun direction, w = s × tan(sun angular
   radius), hidden share = min(1, r²/w²) × (1 − smoothstep(|r − w|, r + w, d)). A body with air leaves
   copper light in its shadow (film 0.085, 0.022, 0.007 of sunlight; honest 3 × 10⁻⁴). No shadows on
   rings.
5. *Ordinary meshes*: `light.directional` (π × sunlight, so a white `MeshStandardMaterial` matches a
   body's white ground) at `at` (default the camera), its colour × what `sunVisibility` leaves there;
   `light.fill` for planet-shine; `shadows: {size}` a shadow box round `at`; `environment: true` sets
   `scene.environment = sky.environment`.

**Exposure** (`EXPOSURES`; a sunlit ground is `SKY_STOPS` 20 stops above the sky `vidgen/space-sky`
draws). `"film"` (default, **a convention, not honest**): nothing changed, stars beside a day side.
`"camera"` (honest): one `ev` (number or function of t): sunlit × 2^ev, sky × 2^(ev − 20), city
lights × 2^(ev − `LIGHTS_STOPS` 10), planet-shine honest. `"auto"` (honest): `ev` from the frame at
t, **a pure function of the scene at t** (frames render in any order and in parallel): a 32 × 18
grid of soft view rays measures each body's sunlit and shine-lit share, each an entry {stops,
share}, a star in frame a twentieth × what shows; `autoExposure` starts at `evMax` 20 and lets each
entry pull toward its own, brightest last, by smoothstep(log share) from `dark` (2 × 10⁻⁴) to `day`
(0.02). Light is held at `BURN` (32) × white so half floats stay finite.

**Interface.** `Star`: `object`, `update(t)`, `direction`, `occluders`, `gain`, `seen`,
`visibility(camera)`, `pixels(camera, height)`, `glare`, `corona`, `mesh`, `options`, `tint`,
`lightColor`, `dispose()`. `SpaceLight`: `update(t)`, `directional`, `fill`, `ambient`, `state`
(`{exposure, ev, gains, bodies: [{sun, intensity, shine, honest, source}], light}`), `albedos`,
`dispose()`. Pure helpers: `resolveStar`, `starTint`, `sunlightColor`, `starSpots`, `starLoops`,
`coronaFaces`, `sunVisibility`, `tangentColumn`, `phaseLight`, `planetShine`, `ringShine`,
`filmShine`, `sunlight`, `exposureGains`, `autoExposure`, `pointShare`, `glareShare`; constants also
`QUALITIES`, `AU`, `SUN_ANGULAR_RADIUS`, `VERSION`. Parts (`data/web/parts/space-light.js`, kind
`light`); each `exposure-*` tile's label says whether it is honest.

**Limits.** In an honest exposure a sun in frame is white whatever its temperature; the corona is a
function of angle, not a volume; planet-shine is one unshadowed directional light per body; the
auto exposure does not see the sky, city lights or ordinary meshes; no orthographic camera. Tests:
`tests/test_web_space_light.py`.

### 122.9 Phenomena: `vidgen/space-phenomena` (Step 373)

`data/web/modules/space-phenomena.js` (`vidgen/space-phenomena`, in `VIDGEN_MODULES`; imports
`three`, `rng` of `vidgen/music-time`, `blackbody`, `starColor`, `starAmplitude` of
`vidgen/space-sky`): `blackHole`, `wormhole`, `warp`, `asteroids`, `asteroid`, `comet`, `aurora`,
each one call and one `update(t)`. Each is a pure function of the time given to `update` and of
seeds (nothing kept between frames; at most a map made once); no cheap stand-ins, only `quality`
(`QUALITIES`: `fast`, `normal`, `fine`). Options, defaults, costs: docs/CONFIG.md (`web`,
"Phenomena"); a misspelt option throws with the closest known one.

**Black hole.** `object` is a quad covering the ball of radius `lens` (the whole frame when the
camera is inside); one unit = the Schwarzschild radius rs, y the disc axis. Per pixel the shader
steps the light path back from the camera: u = 1/r, u'' = −u + 1.5 u², start u₀ = 1/r₀, u' = −u₀ cot
ψ √(1 − u₀) (camera at rest), b = r₀ sin ψ / √(1 − u₀); `HOLE_STEPS` 28 / 44 / 88 velocity-Verlet
steps shared over the expected swept angle.
- Shadow: b < 3√3/2 rs (`SHADOW` 2.598), edge smoothed over the pixel's footprint in b. The sky:
  the `SpaceSky` cube read in the exit direction (nothing baked).
- Stars stay points (a lens brightens a star, it does not lengthen it): the hole draws the sky's
  stars itself, primary and secondary image. Before each draw JS steps 128 paths for the camera
  distance (`lensTables`) into two float textures (per star–hole angle: each image's b and gain,
  held at 24; per path the radius at 64 angles, for disc cover); third and later images left out.
- Disc in x–z between `inner` and `outer`: the path's first two plane crossings (cubic between
  steps) give the direct disc and its far side, composed front to back; shift g = √(1 − 1.5/r) / (1
  − Ω L), Ω = √(0.5/r³). Photon ring at 1.012 × shadow radius, ≥ 1.5 px with light thinned.
- Disc look (stated choices): warm = (T(r)/T_max)^1.6 × (0.62 + 0.9 gas) × g^`doppler`, colour from
  `heatRamp` (64-texel `blackbody` ramp), light ∝ warm^2.5, T(r) the thin-disc law. The gas map
  (1024 × 512) turns ∝ r^−3/2: two copies each sheared for one period, the *finished light*
  cross-faded (blending maps before the non-linear steps made the disc breathe).
- Approximations: non-rotating hole, camera at rest, only the sky bent (scene objects drawn
  normally), a finite lens (`lensRadius`: 2.6 Einstein radii, ≥ 20 rs or 1.4 × `outer`, ≤ 64) with
  the bending eased out over 55–100 % of it, thin flat disc. `sky` may be a plain cube texture
  (stars then stretch) or absent.

**Wormhole.** A ball of radius 1 (the mouth) showing `other` with ours bent round the rim. Ellis
wormhole with a straight middle (`wormholeRadius`: 1 for |l| ≤ `length`/2, √(1 + (|l| −
`length`/2)²) beyond); paths keep b = r sin ψ, l'' = b² r'/r³, φ' = b/r², strides ∝ r
(`WORMHOLE_STEPS` 24 / 36 / 72), the straight middle in one exact stride, straight lines outside
the lens. b < 1 exits on the other side. Both skies are read from their `background` cubes.
`passage(camera, progress, {from, look})` moves the camera on the line through the centre and
returns `{progress, l, side, inside}`; the camera frame is carried straight through, so the far sky
is attached mirrored across the mouth's plane (a convention).

**Warp** (invented). `warpAt(progress)` is the whole script, pure (`speed`, `travel`, `flash`,
`tunnel`, `sky`; `WARP_MARKS` `{enter: 0.14, leave: 0.84, out: 0.96}`). Each star is a streak from
now to `shutter` frames ago (`warpStreak`), so consecutive streaks overlap and nothing strobes; the
flash is never a white frame; `intensity` scales light only, never the lens. `motion check` warns
`shimmer` in the tunnel (streaks move over 4 px a frame): expected.

**Asteroids.** `rockShape(seed)` (direction → surface and shade), `rockGeometry(seed, detail,
{smooth})`. JS places every rock each frame; rocks over 1.7 px are instanced meshes (`shapes` × three
LODs, at most `rocks`), all are points holding their lit face's light (`phaseOfSphere`), fading as
the mesh grows in; `follow` repeats the field's box round the camera (a rock shrinks to nothing
where it would jump); a belt is Kepler orbits with `gaps` (`beltDensity`). Meshes are
`MeshStandardMaterial` lit by the scene's lights; no rock-on-rock shadows; `asteroid` (65,000 faces)
casts and takes shadows. `glint` and a belt's sizes are stated choices.

**Comet.** `cometFrame(toSun, velocity)` → `away` (ion tail) and `lag` (dust bends by `curve` ×
s^1.7); tails are camera-facing ribbons with structure in the fragment shader. With `{space, body}`
place, sun and motion come from `ctx.orbits` and `activity` = `cometActivity(distance)` = (1 AU /
r)², nothing under 0.1, held at 1.6 (tail length ∝ √activity, light ∝ activity); one unit = `unit`
metres (2 × 10⁹, stated). `comet.nucleus` is an `asteroid`.

**Aurora.** Four thin shells over a `vidgen/space-bodies` world, narrow strips round each magnetic
pole (an oval `latitude` from a pole `offset` off the spin pole); turns with `body.spinner`, reads
`body.sun`.

**Order and depth.** Hole and wormhole draw after the sky and before everything else (`renderOrder`
−900), test depth at their middle's distance, write none. The warp is in the sky pass
(`frustumCulled = false`; its flash `userData.overlay`). Rock points, tails, head and curtains are
additive and test depth. Every object has a bounding sphere of its true reach (§122.4). A rock or a
comet nucleus hides a star's glare when named: `sun.occluders = [...sun.occluders, rock]` (scale
taken as a ball radius); a field's instanced rocks do not.

**Interface.** Returned objects: `BlackHole` (`object`, `update(t)`, `set(options)`, `options`,
`uniforms`, `lens`, `dispose()`), `Wormhole` (`object`, `passage`, `release()`, `state`,
`dispose()`), `Warp` (`object`, `update(t, {progress, camera, direction, intensity})`, `state`,
`dispose()`), `Asteroids` (`object`, `update(t, {camera, sun})`, `place(i, t, eye)`, `count`,
`shown`, `dispose()`), `Asteroid` (`object`, `update(t)`, `dispose()`), `Comet` (`object`,
`update(t, {sun, velocity, activity})`, `nucleus`, `state`, `dispose()`), `Aurora` (`object`,
`update(t, {sun})`, `dispose()`). Defaults: `HOLE_DEFAULTS`, `WORMHOLE_DEFAULTS`, `WARP_DEFAULTS`,
`ASTEROIDS_DEFAULTS`, `ASTEROID_DEFAULTS`, `COMET_DEFAULTS`, `AURORA_DEFAULTS`. Pure helpers:
`deflection`, `lightPath`, `lensTables`, `lensRadius`, `discShift`, `discTemperature`, `heatRamp`,
`wormholeRadius`, `wormholePath`, `warpSpeed`, `warpAt`, `warpStreak`, `rockShape`, `rockGeometry`,
`rockRadius`, `phaseOfSphere`, `beltDensity`, `cometActivity`, `cometFrame`; also `SHADOW`,
`HOLE_STEPS`, `WORMHOLE_STEPS`, `WARP_MARKS`, `QUALITIES`, `VERSION`. The hole reads `sky.target`,
`sky.stars`, `sky.starUniforms`, `sky.skyMaterial`, `sky.options` of a `SpaceSky`. Parts
(`data/web/parts/space-phenomena.js`, kind `phenomenon`): `black-hole`, `black-hole-from-above`,
`einstein-ring`, `wormhole`, `wormhole-tunnel`, `warp-streaks`, `warp-tunnel`, `asteroid-field`,
`asteroid-belt`, `asteroid`, `comet`, `aurora`; labels carry the frame cost.

**Limits.** One lens at a time (overlapping lenses each draw the unbent sky inside); no rotating
hole, jet or thick disc; no orthographic camera; the world's shadow does not fall on a belt; tails
cast no shadow; additive light straight to the canvas is only roughly right. A backtick in a GLSL
comment inside a JS template string ends the string. Tests: `tests/test_web_space_phenomena.py`.

### 122.10 The spacecraft kit: `vidgen/space-craft` (Step 374)

`data/web/modules/space-craft.js` (`vidgen/space-craft`; imports `three`, three's
`BufferGeometryUtils` add-on and `rng` of `vidgen/music-time`): ready-made craft, the parts they are
made of, and craft motion that follows `ctx.orbits`. Kinds, parts, options and defaults:
docs/CONFIG.md (`web`, "Spacecraft").

```js
const probe = craft("probe", {seed: 7});                    // metres: +z the nose, +y the top, engines fire toward -z
const light = spaceLight({scene, camera, renderer, sun, bodies: [earth], sky, at: probe.object, shadows: probe.shadows});
probe.shade(sun);                                           // the craft hides the sun's glare
scene.environment = craftEnvironment(renderer, scene, {at: probe.object}).texture;
// frame(t): probe.update(t, {sun, camera, height: ctx.height}); sun.update(t); light.update(t);
const ship = craft("ship", {seed: 2}).fly(space, {body: "Ship", attitude: "prograde", burn: {seconds: 2}});
```

**Design.** Everything computed (no image or model file); the six craft (`CRAFT`: `probe`,
`satellite`, `station`, `ship`, `lander`, `tug`) are invented designs of believable size, no real or
film spacecraft, markings, flags or names. Parts (`craftKit({seed, accent, foil, detail, wear, lit})`)
are `THREE.Group`s in metres with named points (`fore`, `aft`, `port`, `starboard`, `zenith`,
`nadir`, `mount`, `tip`, `top`, `dock`, `feed`, `exit`, or `{angle, along, out}` on a hull, truss,
boom or tank cluster); `attach` joins points, `around` repeats round a hull. A finished craft's
meshes are merged to one per surface (and one set per moving part: tracking wing, gimballed dish,
ring habitat, deployable panel): a few tens of draws. The same seed gives the same vertices, at both
`DETAILS` (`"far"`: fewer sides, no rails or rivets, a third to a quarter of the triangles).
`fleet(kind, {count, seed})` uses seeds seed, seed + 1, … at `"far"`.

**Surfaces** (`SKINS`, all `MeshStandardMaterial`): maps computed once for all craft — foil
(`foilMaps`: crumpled at four scales, each the min/max of bowed facets so creases are sharp;
metalness 0.9), plating (`platingMaps`: seeded panels, grooves, rivets; white paint 0.65 of white so
panel lines survive sunlight), solar cells (`cellMaps`), `glass`, `window` (`WINDOW_LIGHT` 1.25).
The sun's mirror image is held at `GLARE.value` (5) × a white surface (a glint, not a burnt face).
The ship's tanks are foil, never plain white paint (it reads flat).

**Light.** `spaceLight` (§122.8) with `at: craft.object`, `shadows: craft.shadows` (a 2048 px box of
the craft's size). `occlusion` (0.55) baked into vertex colours darkens joints. `craftEnvironment
(renderer, scene, {at, size, hide, near, far})` → `{texture, update(), dispose()}`: the scene drawn
once from the craft (craft, stars and glare left out: the sun is a light, not a reflection) into a
128 px PMREM cube; made once, `update()` redraws. It sets the cube faces' angle to 90 without
touching their projection (the cube camera's −90° fov made `vidgen/space-bodies` read a negative
pixel size). `paintedEnvironment(renderer, {sky, worlds, size})`: the same without a scene.

**Engines** (`PLUMES`: `chemical`, `vacuum`, `ion`, `rcs`, `air`): light summed along the view ray
(ten samples crowded near the axis) through an exhaust widening into vacuum — a core and a flare
(per-volume brightness ∝ 1/width²). No shock diamonds in vacuum (`air` has them). `throttle` 0..1;
`flicker(t, i)` a sum of fixed sines (±10 %). Drawn on its bounding cone's far side with the depth
test.

**Motion: a pure function of t** (`craft.update(t, {...})`, nothing kept between frames).
- *Attitude* (`ATTITUDES`): `prograde`, `retrograde` (relative to the orbited body, top away from
  it), `radial`, `nadir`, `sun` (`axis`), `target` (`axis`), `thrust`, `inertial` (`forward`, `up`).
  A list `[{mode}, {at, turn, mode}, ...]` turns from `at` over `turn` s (default 3), slerp with
  smootherstep, each mode computed for t itself (`attitudeAt`, `attitudeQuaternion`).
- *A burn of `ctx.orbits`* is an instant (§122.3). `fly(space, {body, burn: {seconds, turn}})` shows
  it as `seconds` (2) of thrust centred on it (stated convention): nose turned along Δv during
  `turn` s before, engines firing exactly from `at − seconds/2` to `at + seconds/2` (0.25 s up, 0.4 s
  down), then back; thrusters puff at each turn (`burnWindows`, `throttleAt`, `burnWeight`). The
  turn and burn keep Δv's prograde / radial / normal parts in the flight's own axes at their
  instant (`_thrustAt`), so a prograde burn stays prograde under any speed-up; `seconds` and `turn`
  stay scene seconds (visible at any speed-up); the orbit keeps its exact impulsive Δv.
- Wings face the sun (`trackAngle`); dishes aim at `target` (`aimAngles`, within 100° of rest); a
  ring habitat turns at its rate × t; lights blink by the clock (`blink`, `LIGHTS`). `throttle`,
  `rcs`, `lights` take a number or a function of t.

**Hiding the sun.** `craft.occluders`: a few balls in every solid part's box (not trusses, booms,
antennas), children of the parts; `craft.shade(star)` adds them to `star.occluders` once.

**Small in the frame.** Under 4.5 px radius a point fades in; under 1.6 px the meshes are hidden: a
gaussian ≥ 0.7 px keeping the craft's light, plus a flash when a flat face mirrors the sun to the
camera (`GLINT`: cos^500). Needs `camera` and `height`. `marker` (default 0, stated): the least
light the point shows at any distance.

**Interface** (misspelt option, kind, surface or point throws with the closest known one).
`craft(kind, options)` → `Craft`: `object`, `update(t, {sun, target, velocity, radial, thrust,
attitude, throttle, rcs, lights, camera, height, deploy, spin})`, `fly(space, {body, attitude, burn,
target, sun, parent, camera, height, throttle, marker})`, `shade(star)`, `occluders`, `shadows`,
`size`, `info`, `engines`, `thrusters`, `lights`, `wings`, `dishes`, `burns`, `state`, `materials`,
`glint`, `dispose()`. `CraftKit`: the parts, `craft(root, {fore})`, `materials`, `bins()`.
`attach(parent, at, child, mount, {roll, gap})`, `around(parent, make, {count, angle, span, along,
out, mount, roll, gap})`, `mirror`, `pointOf`; `fleet` → `{object, craft, update, dispose}`.
Constants `CRAFT`, `SKINS`, `ACCENTS`, `FOILS`, `HULL_SHAPES`, `DETAILS`, `PLUMES`, `LIGHTS`,
`ATTITUDES`, `WINDOW_LIGHT`, `GLARE`, `GLINT`, `VERSION`. Parts (`data/web/parts/space-craft.js`):
kinds `craft` and `craft-part`.

**Limits.** Rigid apart from wings, dishes, ring and panels; maps shared by all craft; one 2048 px
shadow map over the craft's box; a plume is unlit and lights nothing beyond its bell; no
anti-aliasing of thin struts (space scenes run without FXAA), so a truss shimmers a little in motion
without motion blur. Tests: `tests/test_web_space_craft.py`.

### 122.11 Camera moves for space scenes: `vidgen/space-camera` (Step 375)

`data/web/modules/space-camera.js` (`vidgen/space-camera`; imports only shaping functions of
`vidgen/music-time`, no three.js, so it all runs in Node): the moves a cinematographer names, each a
function of time. Moves, their options and defaults, views, lenses: docs/CONFIG.md (`web`, "Camera
moves for space scenes").

```js
const cam = spaceCamera({space, camera});                   // on a SpaceView; or {camera, up: [0, 1, 0], sun, bodies}
const view = (t) => cam.arc(t, {subject: "Saturn", phase: {limb: 0.1}, distance: {radii: 7}});
const update = (t) => { cam.apply(t, view(t)); saturn.update(t); sun.update(t); light.update(t); };
```

**Shots are plain data; the rig holds no state.** A move returns `{from, right, up, forward, fov,
aspect, focus, subject, ...}`, float64 arrays in its subjects' frame (orbit data's, z north, with a
`SpaceView`; y up without). `cam.apply(t, shot)` sets the fov and calls `space.update(t, {from:
{offset}, quaternion})` (double precision, §122.4), or sets a plain camera's fields. `shot.focus` is
the subject's distance along the view (`dof.focus` / `dofFocus`). The same time gives the same shot
in any order, so scenes render in any order, a cut on one clock shows one move, and motion-blur
sub-frames work. Built on `vidgen/space-scale`, not `vidgen/music-time`'s `orbit` / `flyThrough`
(kept for music videos), because the moves need the sun, radii and double precision.

**Inputs.** Time: `progress` (0..1) or `over: [start, end]` in seconds of `time` (default t);
`eased(u, ease)` blends even speed (0) with the quintic ease (1). Subjects: a body name, `[x, y, z]`,
`{at, radius, name}` (`at` may be a function of t), `{body, offset}`, a world / star / craft of the
space modules (a flown craft is its `flight.body`), a top-level three.js object (read by
`position`), or a function of t. Distances: metres from the middle, `{radii}`, `{altitude}`. The sun:
the rig's `sun` (direction, subject, or a `vidgen/space-light` star turned into the data frame) or
the data's `"Sun"`.

**Composition.** `shotAt(eye, target, {up, fov, aspect, place, roll})` puts the target exactly at
`place` (−1..1) with a level horizon: a = x tan(fov/2) aspect, b = y tan(fov/2), n = √(1 + a² + b²),
pitch = asin(n sin E / √(1 + b²)) − atan b, heading turned by atan(a / (cos θ − b sin θ)). Only the
zoom centres its subject. `level: body` levels a world's horizon; fly-bys and craft views do so for a
world a data subject flies within three radii of.

**Moves.** `flyBy` (a straight line in the subject's frame; a true hyperbola belongs to the orbit
data, `follow` a `flyby` body; `linger` blends even speed along the line (0) and even turning of the
bearing (1)), `pass` (a fly-by against the craft's velocity), `arc` (a phase angle: `PHASES` name,
degrees, or `{limb: k}` = 180° − (1 + k) asin(R/d)), `arrive` (height falls by a constant factor per
unit of eased progress; `sunAhead` measured from the limb, default day side), `reveal`, `follow`
(`VIEWS`; `lock` `"velocity"` / `"craft"` / `"stars"`; `side` `left` / `right` / `sun`; with `lock:
"velocity"` a named view loses the world on a radial flight, so give a view vector with a large up
share, §122.13), `zoom`.
- **Reveal timing.** On a circle of radius r round the world (radius R), in the plane holding the
  subject direction and square to `plane` (default `up`), a far sun's upper edge meets the limb at
  θ* = asin(R/r) − σ (σ its angular radius); the camera is at θ* + `rate` × (time − `at`); for a
  subject at a finite distance θ* is bisected (60 steps). `air` (degrees, given by the author) adds
  the air's hold-back to the limb; `airMargin(radius, distance, height)` gives one scale height's
  angle.
- **Zoom.** `zoomPlan(distances, {rate | seconds, hold, ease})` → legs and rests; `zoomAt(plan,
  time)` → `{distance, power, leg, share, resting, speed}`. log distance is the integral of a speed
  rising as a smoothstep over `ease` s at eased ends, constant between (closed form): mid-leg d(t +
  1)/d(t) = `rate` exactly; a leg lasts ln(d₁/d₀)/ln(rate) + ease/2 per eased end; `over` solves for
  the rate. The middle between landing points is A₀ + (A₁ − A₀) smoothstep((d − d₀)/(d₁ − d₀)),
  linear in distance, not its log, so it moves with the scale without a kink. Closer than
  `GROUND_SHARE` (10⁻³ radius) above ground `problems` warns (§122.4).

**Lenses.** `LENSES` (16–600 mm): vertical fov of a 36 × 24 mm frame, 2 atan(12/mm).
`frameShare(radius, distance, fov)`, `distanceFor(radius, share, fov)`, `loomLens({craft, world,
gap, craftShare, worldShare})` (the lens and distance for a craft and a world behind it at given
frame shares, plus the world's share at 24 mm).

**Checks.** `cam.problems(t, shot, {subject, box, minPixels, height, ground})` returns sentences:
camera inside a world or within `GROUND_SHARE` of its ground; subject behind the camera, outside the
frame or `box` (a subject larger than the frame counts while any of its disc is in), under
`minPixels` (3), hidden behind a world; a craft (not a world: a crescent is meant) in a world's
shadow cylinder or seen from its unlit side (phase over `UNLIT_PHASE` 150°), with what to do.
`cam.check(move, {from, to, steps})` samples a move for the same, a path through a world between
samples, and a jump (a turn over 8× the move's median, over 3° and over 3× both neighbours: a whip
pan is not a jump).

**Cuts** (each one curve read by both scenes from their own time): `discOf(shot, at, radius)` +
`matchDisc(disc, radius, fov)` → `{distance, place}`; `flashCut(time, cut, {amount, rise, fall})`;
`warpCut(time, cut, {seconds, split})` (progress for §122.9's `warpAt`).

Parts (`data/web/parts/space-camera.js`, kind `camera`): five framings in plain three.js scenes
(craft views have no tile: a `SpaceView` tile would leave its wrapper on the sheet's shared
renderer). Limits: a 300 mm lens shows the sky's cube enlarged; orbit-data paths are polylines (more
`path_samples` for close-ups); the zoom's default direction can face a night side when no sun is
known. Tests: `tests/test_web_space_camera.py`.

### 122.12 Space scenes without code: the `space` scene (Step 376)

A built-in scene type `space` written in `video.yaml` alone, the front for §122.3–122.11 (and
§123.14's additions). Every key, the vocabulary and what YAML does not reach: docs/CONFIG.md#space.
Guide topic `space-scenes` (the orbit topic keeps its alias `space`).

**How it is built.** `Space` subclasses `Web` (`scenes/space.py`), so everything that treats a `web`
page treats it the same (`is_web_type`: fingerprint's loaded files, `vidgen still`, `--jobs`,
`--draft`, `vidgen motion check`, the clip cache). `page_clip_args` writes the page
(`scenes/space_page.py`, `page_source(params, scene_id)`) to `build/space/<id>.js` (only when its
text changes; written to a temporary file and moved into place, since a `--jobs` render may be
serving it) and hands `make_web_clip` the params of a `script:` scene: `{script: build/space/<id>.js,
data: {...data, scene_seconds}}`, with `music` / `orbits` as a `web` scene with `music_data` /
`orbit_data`. So the clip key holds the page's SHA-256 (every picture-changing param changes the
page), `ctx.data`, the orbit and music data; other scenes' keys are unchanged. `scene_seconds` = the
scene's frames less the fade and the two spare frames. vidgen draws no heading (`title:` is the
page's card); `fade: false` (`outro_seconds`) cuts without the 0.5 s fade.

**The page is plain code**, generated, not interpreted: each sky, star, world, craft, phenomenon and
move is a line calling the module's function with its options as a JSON literal (floats exact), so
`vidgen space-page` can hand it over. One exported object `S` (`S.bodies.<name>`, `S.craft.<name>`,
`S.phenomena.<name>`, `S.subjects`, `S.cam`, `S.moves`, `S.view`, `S.step`, `S.finish`); `S.step(t)`
sets everything to scene time t (camera, reactions, phenomena, worlds, sun, craft, light; a function
of t alone), `frame(t)` draws through three-finish (FXAA off by default). Every world of the orbit
data, and a camera's data body that nothing draws, is entered in `S.subjects`. It imports only
shipped modules plus `vidgen/space-scene` (`data/web/modules/space-scene.js`, no three.js):
`sceneTime` (seconds or `{bar, beat}` → scene seconds from `ctx.music.score` / `ctx.music.t0`),
`moveTrack` (moves in sequence, join check), `checkMoves` (space-camera's `check` on every frame of
every move, as notes; sparse samples report false fly-throughs under large speed-ups), `reaction`,
`freeSubject`, `pageNote`.

**Two kinds of scene.** With `orbits:` (`OrbitData` as is) every world and craft is a body of the
data placed by `SpaceView`; `scale:` `true` / `enlarged` / `log`, and when not true the page shows
`space.note()` (`note: false` leaves it to the narration). Without orbits, things stand at `at:`
(metres or lengths with units, z up), added to the same `SpaceView` (`space.add(object, {at,
size})`), so slices and floating origin work at any scale. Rig: `spaceCamera({space, sun, bodies})`.
The sun: the data's Sun, else a far `star({direction})` whose default, for orbit data around a planet
(or the Moon), is the Sun's real direction on the date (−heliocentric position of the planet, JPL
approximate elements, held for the scene; for a `flyby` via `flyby_axes`, §122.3), else `[1, 0.25,
0.35]` with a note.

**Words.** Sections pass the driven module's options as they are, in snake_case or camelCase
(`milky_way` → `milkyWay`); names accept `_` for `-`. A reaction's key is `track:` and an aurora's
`world:`, not `on:`, because YAML 1.1 reads `on` as true. **One source of truth:**
`vidgen/web/space_names.py` reads the modules' own constants from their shipped source (a small
reader of JS literals: names or quoted keys, method shorthand, `...SPREAD` of another constant in the
file, nested objects, strings, comments) — worlds, types and options, airs, sky, stars, light,
exposures, `*_DEFAULTS`, craft, attitudes, each move's `known("<move> options", options, [...])`
list (`pass` takes `flyBy`'s plus `side`), phases, lenses, views, three-finish and title-card
options — so a name added to a module is known to `vidgen validate` with nothing copied (a test
compares camera and title-card lists with Node's).

**Checks.** `vidgen validate` (did-you-mean): keys and names; with orbits, worlds and craft are data
bodies (no `at`, `radius`, `tilt`; `fly:` needs orbits); unique names; moves in order, not
overlapping, each with `over` when there are several, subjects known; lengths in move options (`2.6e9`
read as text is metres); bars only with `music_data`; reaction targets (the Sun's glare, the sky, a
black hole's disc, a warp, a craft's lights / throttle / rcs; never a world, which reflects the sun,
nor the camera); the script file. What the page builder refuses later is a `VidgenError`. `vidgen
lint`: `space_scene` (`lint/space_rule.py`, warning, `degrees` 12: a globe turning over 12° a frame,
an enlarged body past another's middle, free worlds inside each other); `orbit_scale` reads `scale:`.
At load the page leaves what only it knows in `globalThis.__vidgenNotes`, which `WebPage` reads after
`load` (`WebPage.notes`) and logs as warnings (any page may use it; no key changes). A move not
starting where the previous left the camera (1 % of the distance, 1°, 0.5° of fov) stops the page
with both names unless it says `cut: true`.

**Music.** `music_data` as on a `web` scene (kept explicit: the fingerprint and music-data
preparation read it from the raw params). Reactions `{track, pulse | glow | glint: THING, as, amount,
decay}`: pulse = `hitEnvelope`, glint = `noteEnvelope`, glow = `signalLevel` (or `ctx.music.level`
for `track: level`); brightness → `base × (1 + amount × v)`, throttle `min(1, amount × v)`, lights `1
+ amount × v`. Bars (`over: ['bar 9', 'bar 13 beat 3']`) count from 1 in song time, so a move stays
on the music however the film is cut.

**Escape hatches.** `script:` (a project module imported by absolute URL): `setup(S)` once after
build, `frame(t, S)` at the end of each `S.step`. `vidgen space-page PROJECT --scene ID [--out]
[--force] [--json]` (MCP `space_page`: `scene`, `project`, `out`, `force`; `--out` stays in the
project folder) writes `extensions/<id>.js` (its first two lines say it is the author's now) and
prints the replacing `web` scene (`script`, `data: {scene_seconds}`, `orbit_data`, `music_data`);
stills of both are identical.

**`vidgen music plan --style space`** (`music_space_plan.py`; the default `--style web` is
unchanged): each cut of the plan becomes a `space` scene by rules, deterministic from the score and
`--seed`: role → move (quiet: arc to a crescent, the first quiet scene a sunrise on its first section
start, else its last phrase line; build: arrive; verse: a chase; drop / climax: fly-by, pass or warp,
never two warps running); base colour → a colour family → a ready-made world; one sky seed, look by
role; the plan's grade; pulse → the sun (or the warp), glow and glint → the craft; `fade: false`;
title and end card; pass and chase get `around:` the world. Tests: `tests/test_space_scene.py`.

### 122.13 The example film: `examples/outbound` (Step 377)

`video.yaml` (five `space` scenes, no `script:`), one score (`assets/music/outbound.yaml`, 17
tracks) and a README; 1280x720, 30 fps, 18 bars at 75 BPM = 57.6 s. A beat is 24 frames and a bar 96
(3.2 s), so scene lengths (16, 9.6, 9.6, 3.2, 19.2 s) are whole frames and every cut is a bar line
(`fade: false`). Times inside a scene are bars of the song counted from 1 (`at: 'bar 4'`); the end
card's `start` is seconds of its scene.

| Bars | Scene | Parts | Timed to the music |
|---|---|---|---|
| 1–5 | `01_dawn` | sky, Earth-like world, default sun, `reveal`, `title` | first light on bar 4 (`air: 0.1`); `pulse: Sun` on the taikos |
| 6–8 | `02_depart` | `orbits:` (orbit 2,000 km up, a burn, a date, 150×), `ship`, `follow` with its own view vector | the burn at bar 7 |
| 9–11 | `03_rings` | `orbits:` with `flyby`, Saturn, craft, `arc` then `follow` after `cut: true` | the cut on bar 10 |
| 12 | `04_jump` | free craft with `throttle`, `warp`, chase view | `glow: Jump` on the timpani roll |
| 13–18 | `05_horizon` | `black-hole`, `fly-by` (`before: 3`, `after: 6`), `end_card` | `pulse: Hole` on the taikos; the card on bar 17 |

**True and chosen.** The burn's size is computed with `orbits.hohmann` (Earth → Saturn: v∞ at
departure; from a 2,000 km circular orbit √(v∞² + 2μ/r) − √(μ/r) = 7.280 km/s); the fly-by is the
model's hyperbola with the arrival speed (the example's test recomputes both). Chosen and said in
the README: where on the orbit the burn happens, the jump and the black hole. Every shot has a lit
subject (departure seen from above and ahead with the day side behind; jump with the sun behind
the chase camera). `follow` uses a view vector (`[0.4, 1.0, 0.7]`) because with `lock: velocity` a
named view loses the world once the flight turns radial; the fly-by uses `reach: 1.6` (the
smallest allowed) and an establishing `arc` before the cut. Tests:
`tests/test_outbound_example.py` (no render).

### 122.14 Review of Phase AN (Step 378)

The review's fixes are folded into the sections above: the long-lens sky (§122.6), unlit-craft
checks and `follow` `side` (§122.11), burns under a speed-up (§122.10), `shimmer` following a pan
(§122.5), the fly-by frame and dated speed-ups (§122.3), the space page's subjects, length checks
and atomic write, MCP `space_page` (§122.12). Others:
- **A transfer's departure alone** (`orbit_parts`): a span ending between the two burns shows the
  departure; refused only when the first burn is late, naming `transfer.depart` as the way out.
  The flat `orbit` scene accepts the same.
- **Page load** (`web/page.py`): `LOAD_TIMEOUT_S` 90 s (a 2048 world map bakes in ~30 s on 2 cores).
  The bake is not cached between pages: a cache would need a page → vidgen channel for ~50 MB per
  1024 world, keyed by GPU and module, while the bake is a few per cent of a render chunk.
- **Gallery** (`gallery.py`): a still heavier than `STILL_MAX_BYTES` (80 kB) is saved with fewer
  colours (64, 32, 16); a GIF that needs fewer colours is held to `CLIP_NOISY_MAX_BYTES` (95 kB) (a
  star field under a moving camera changes every pixel every frame). The `space` gallery sample
  uses `finish: {grain: 0}`.
- three-finish is unchanged by Phase AN (changing it would re-key the earlier films' pages); FXAA
  stays off in space scenes by the `space` scene's default.
## 123. Air, planes and giant ships (Phase AO, Steps 379–394)

Flight inside atmospheres (sky from inside, ocean, cloud decks and gas giants, terrain; no
forests), parametrized space planes and giant ships, a cache for baked maps, and a second gallery
for scenes drawn in a web page.

### 123.1 Two galleries: the main one and the web gallery (Step 379)

- **Rule** (a property of the type, not a list): an entry is a web entry when its scene class is
  drawn in headless Chromium: `NarratedScene.drawn_in_browser` (`ClassVar[bool]`, default
  `False`), set by `web` (`scenes/web.py`) and `3d` (`scenes/scene_3d.py`) and inherited (`space`,
  any `Web` subclass, a project's own type). `gallery.is_web_type` reads it from the registry;
  `GalleryType.web` carries it (an alias has its class's); a showcase is web when one of its
  scenes is (`is_web_showcase`).
- **Layout.** Web entries: `docs/gallery/web/<name>.md`, media `web/media/<name>-16x9|9x16.png|gif`
  (`gallery_folder`), same sizes and caps as main entries; last line "[All web
  scenes](README.md) · [All scene types](../README.md)". `write_index(..., web=True)` writes
  `web/README.md` ("# Web scene gallery", same table per guide group, no YouTube section). The main
  index lists the other entries, one line linking `web/README.md` when it has entries, and keeps
  "Videos on YouTube" at its end. Showcase links go to either gallery (`page_link`; footer
  `relink_for_web`). Writing an entry removes its copy in the other gallery (`_remove_other_copy`).
  The web index names the music films (`WEB_SECTION_NOTES`), which are not entries. A project's
  gallery splits the same way (`<output>/web/` only with a web type).
- **Budgets** (`tests/test_gallery.py`): `BUDGET` 16.5 MB for `docs/gallery` without `web/`,
  `WEB_BUDGET` 20 MB for `web/`, `ENTRY_MAX` per entry.
- **Elsewhere.** `vidgen gallery` prints both indexes; `--json` has `web_index` and `web` per type
  and showcase; MCP serves `vidgen://gallery/<type>` (names unique across both) and
  `vidgen://gallery/web-index`. `.gitignore` lets `docs/gallery/web/media/` in.
  `browser.chromium.BROWSER_SCENE_TYPES` (the `vidgen validate` Chromium warning) is `3d` and `web`
  only.

### 123.2 The cache of baked maps (Step 380)

- **Cached:** `space-bodies` maps A and B (§122.7; RGBA 8-bit cubes with mipmaps), the `space-sky`
  cube (§122.6; RGBA half float with mipmaps), and later bakes through the same helper (§123.3,
  §123.4, §123.6). Not cached: cheap CPU textures (`space-light`, `space-phenomena`, `space-craft`
  panels, ring profile, sky stars), anything scene-dependent (sky `background` / `environment`,
  craft reflection cubes), and `three-kit` / `three-finish` bakes.
- **Helper `vidgen/baked`** (`data/web/modules/baked.js`, on the import map):
  `baked(renderer, name, inputs, {targets, draw})` returns the render targets `targets()` makes (2D
  or cube, RGBA, unsigned byte / half float / float; `null` for one not needed), filled by
  `draw(targets)` or from the cache. Synchronous (so `planet()` and `spaceSky()` stay so).
  `inputs` holds every input that changes the pixels besides what vidgen adds (a project script
  includes a version of its own bake code). Also exported, pure: `inflate`, `halfBits`,
  `joinPlanes`, `layout`.
- **Key** (`web/baked.py` `bake_key`): SHA-256 of canonical JSON (sorted keys) of `name`, `inputs`,
  the parts' layout (target, face, width, height, type, bytes), the GL renderer (`RENDERER`,
  `VERSION`, shading language, sorted extensions), `vidgen/baked`'s `VERSION`, `code_digest()`
  (every file in `data/web/modules/` and the bundled three.js), `engine_id()` (page files, Chromium
  flags, time zone, locale, Playwright version) and `STORE_VERSION`. `-0` and `0` are one key.
- **Transport.** Synchronous XHR to vidgen's origin `POST __vidgen__/baked/lookup`
  (`WebPage._serve_baked`; never a loaded file, so no scene key sees it). *Miss*: the page draws,
  reads level 0 of each face (half float read as float, re-halved exactly by `halfBits`), keeps
  Blobs in `globalThis.__vidgenBaked`, says `POST <key>/ready`; `WebPage._store_baked` reads them
  via CDP `IO.resolveBlob` / `IO.read` and commits. *Hit*: `GET <key>/<n>` per face; the page
  inflates, joins byte planes, uploads with `texSubImage2D`, calls `generateMipmap` if the bake had
  mipmaps. A missing or broken part: `POST <key>/damaged` (entry removed), bake anew. Outside
  vidgen pages (Node, a browser), or off: `draw` runs.
- **Store** (`BakedStore`): `<cache folder>/baked/<key>/` (`VIDGEN_CACHE_DIR`, else
  `~/.cache/vidgen`, `%LOCALAPPDATA%\vidgen`, `~/Library/Caches/vidgen`): `<n>.z` per face (zlib
  level 1 raw deflate; half/float split into byte planes first) and `meta.json` (sizes, stored
  sizes, SHA-256 per file, which targets had mipmaps). Written in `baked/.staging/` and renamed in
  (concurrent bakers: the second rename drops its copy; no reader sees half an entry). Hashes are
  checked before every hit; damaged entries are removed. **Limit** 2000 MB on disk
  (`VIDGEN_BAKED_CACHE_MB`; `0` = off; an environment variable, not config); LRU eviction after each
  store (a hit touches `meta.json`); nothing stored larger than the limit or leaving under 500 MB
  free; staged leftovers removed after an hour. `tests/conftest.py` sets it to 0.
- **Commands.** `vidgen cache` / `vidgen cache info` (folder, baked count, size, limit, other
  folders and their owners); `vidgen cache clear` (baked maps only).
- **Invariants.** Off, cold and warm give byte-identical pixels; no scene cache key depends on the
  cache. Tests: `tests/test_web_baked.py`.

### 123.3 The sky from inside an atmosphere: `vidgen/space-air` (Step 381)

`const sky = air(renderer, "earth", {sun}); scene.add(sky.object); sky.update(t, {camera})`.
`data/web/modules/space-air.js` (`vidgen/space-air`, in `VIDGEN_MODULES`; imports `three`,
`baked`, and `AIRS`, `PRESETS`, `resolveOptions`, `linearColor` of `vidgen/space-bodies`): one
model for every height, ground to space.

- **One source of numbers.** The air is `vidgen/space-bodies`' `AIRS` (§122.7: per-colour zenith
  depths `rayleigh`, `haze`, `absorb`; scale height `height` as a share of the radius; shell top at
  8 scale heights (`TOP`); `forward`; night `glow`) and its closed-form air along a ray (Chapman
  after Schueler). `airOf(what, extra)` takes a `PRESETS` name, a `space-bodies` world (radius from
  `RADII`), an `AIRS` air, a `planet()` body, or `{world | air, radius, forward, ozone,
  ozoneHeight, ground}`. Inside only: an absorbing layer (`ozone` per-colour depth at
  `ozoneHeight` m, at most 41 crossings' worth; Earth-like 0.030 / 0.028 / 0.004 at 25 km) and a
  two-lobe haze phase (`forward`, plus `aureole` / `aureoleForward`).
- **Presets.** `earth`, `mars` (a dusty season: `air: {like: "mars", density: 3, absorb: [0, 0.013,
  0.031]}`; the plain world's air is `air(renderer, {world: "mars"})`), `thin` (radius 2,400 km:
  dark day sky with stars), `thick` (four times Earth-like, radius 7,400 km). Custom:
  `{air: {rayleigh, haze, absorb, height, forward}, radius, forward, ground}` or `{like, density}`.
- **Sums.** Unit of light: a white matt ground square to the sun (§122.7). Single scattering
  (Rayleigh, Henyey-Greenstein) slab by slab, plus multiple scattering as one isotropic term (after
  Hillaire 2020) from a table over height (32 rows) x sun cosine (64, -0.4 to 1), baked via
  `vidgen/baked` (`space-air/psi`; inputs: `VERSION`, table shape, every air number, ground colour).
  Its directions crowd towards the level so twilight is lit.
- **Sky table.** `update` redraws a small table only when height or sun change (`QUALITIES`:
  `standard` 128 x 192, 32 steps; `fast` 96 x 96, 16; `fine` 192 x 320, 48): bearing from the sun
  over half the circle, angle from the horizon by its square root with rows above and below kept
  apart; single scattering without phase (applied per pixel) and multiple scattering side by side.
- **Dome** (`sky.object`): follows any camera (`frustumCulled = false`, `renderOrder` -900: after a
  `space-sky` sky, before the scene), premultiplied over what is behind. Under the horizon a plain
  matt ground (`ground` colour; `false` for none). Sun disc (`disc`; `sunSize` degrees, default the
  Sun's 0.53, `SUN_SIZE`) with per-colour limb darkening; brightness held at `BURN` 32 whites in
  `camera` / `auto`, 1.6 to 32 in `film`; a soft lens bloom. Drawn straight to the canvas it
  applies ACES and sRGB itself and dithers by two display codes (one code bands after encoding).
- **Aerial perspective.** `sky.haze(material)` patches a three.js material (once; a list is fine):
  colour x transmittance + in-scattered light, exact at both ray ends, so far things end in the
  dome's colour and a ground plane meets its horizon seamlessly. A `ShaderMaterial` includes
  `AIR_GLSL`, takes `sky.uniforms`, calls `airThrough(colour, toPoint)` (or `airLight(mu, cosv,
  dist, through, hit)`). Shadows in the haze: §123.17.
- **Lights.** `sky.light.sun` (`DirectionalLight`: sun after the air at camera height, scaled as
  `vidgen/space-light`'s `light.directional`) and `sky.light.sky` (`HemisphereLight`); `scene:
  scene` adds them. `sky.state`: `height`, `elevation`, `ev`, `gain`, `stars`, `sunlight`,
  `ambient`, `inside`, `up`, `center`.
- **Exposure** (`EXPOSURES`, as §122.8). `"film"` (default): unchanged by day; as the zenith
  darkens it opens by `filmExposure` stops (at most `FILM_STOPS` 16, none above the air) with the
  dusk curve (`duskCurve`: a shoulder on air light; `DUSK_CURVE`, `DUSK_KNEE`), capped so the low
  sky under the sun stays under `ARCH_WHITE`, closing by up to `FILM_CLOSE` 3 stops for a bright
  hazy glow; stars appear with the lift (`filmStars`). `"camera"`: `ev` stops over a sunlit
  ground's. `"auto"`: metered on nine rays (a pure function of the frame's inputs).
- **Fidelity.** True: round-world geometry, single scattering, extinction, ozone, sun size and
  colour, sunset colour order. Approximate: later bounces, camera-to-point air; no refraction. The
  dome's limb is brighter than `planet()`'s (fewer slabs, no ozone there): a descent cross-fades
  above the air, or draws the body with `air: false` under this dome (`ground: false, over: true`).
- **For other modules.** `sky.skyAt(height)` → `{texture, map}` (a second sky table from another
  height, same place and sun; one at a time); `AIR_GLSL` `airPlace(map, mu, cosv)`,
  `airRead(table, uv, cosv)` (`airWhere`, `airFromTable` for the camera's own); `DISPLAY_GLSL`
  (`display(linear)`, `dither(pixel)`); `sky.under(covered)`: the scene covers everything below
  the horizon, so the dome draws nothing there.
- **Parts** (`data/web/parts/space-air.js`, kind `air` after `light` in `vidgen/parts` and
  `vidgen.web.parts.KINDS`): `air-earth-noon`, `air-earth-golden-hour`, `air-earth-sunset`,
  `air-earth-twilight`, `air-mars-day`, `air-mars-sunset`, `air-thin`, `air-thick`,
  `air-from-30-km`, `air-haze`.
- **Exports.** `air`, `Air`, `airOf`, `AIR_GLSL`, `DISPLAY_GLSL`, `PRESETS`, `RADII`, `column`,
  `crossings`, `opticalDepth`, `transmittance`, `phaseRayleigh`, `phaseHaze`, `psiTable`,
  `skyLight`, `sunlightAt`, `skyAmbient`, `ambientTable`, `filmExposure`, `duskCurve`, `filmStars`,
  `sunDirection`, constants `TOP`, `SUN_SIZE`, `BURN`, `SKY_STOPS`, `FILM_STOPS`, `FILM_CLOSE`,
  `ARCH_WHITE`, `DUSK_CURVE`, `DUSK_KNEE`, `LIMB`, `EXPOSURES`, `QUALITIES`, `VIEW_TABLES`,
  `PSI_TABLE`, `VERSION`. Renderer-free functions are pure and run in Node. Tests:
  `tests/test_web_space_air.py`.

### 123.4 Water to the horizon: `vidgen/space-sea` (Step 382)

`const water = sea(renderer, sky, {state: "breeze", seed: 3}); scene.add(water.object);
water.update(t, {camera})` after the air's `update`. `data/web/modules/space-sea.js`
(`vidgen/space-sea`, in `VIDGEN_MODULES`; imports `three`, `baked`, `AIR_GLSL`, `DISPLAY_GLSL`,
`PSI_TABLE`, `SUN_SIZE`, `BURN` of `vidgen/space-air`, `latticeNoise` / `NOISE_GLSL` of
`vidgen/space-clouds`). Sea level is the air's radius; sun, light, exposure and sky table are the
air's. Units the air's (metres), +y up at the anchor.

- **The surface is the world's sphere**, no mesh: a grid of picture cells (8 px at `standard`) is
  laid on the sphere along each line of sight every frame and each pixel solves its own place: no
  edge, tile or pop; horizon at `acos(R / (R + h))` below the level, mixed with the sky by coverage
  and seen through the air (`airThrough`), so no seam. The dome stops under the horizon
  (`sky.under(true)`). `water.horizon` = `{distance, dip, height}`. Scene y away from the anchor
  is not height over water (the sphere drops d^2 / 2R): use `water.pointAt(x, z)`.
- **Waves** (`waveList(state, {seed, count, lifted})`, pure): sine waves, longest first: a wind
  sea (twice the dominant length down to its 180th, at least 0.25 m, log-spaced and seed-jittered,
  Pierson-Moskowitz amplitudes with four standard deviations = the significant height, directions
  spread round the wind) and a swell (5 to 8 waves); deep-water speeds (omega^2 = g k) on vidgen's
  clock; second-harmonic crest sharpening (`chop`). Against a sum-of-sines look: **bends** (three
  slow fields; each wave's phase wanders by its own share, at most `WOBBLE` 1.4 rad, less for
  waves longer than `WOBBLE_SPAN`), **gusts** (`GUSTS`: six octaves of endless gradient noise, 0.5
  to 9 km, drifting at half the wind, weight `GUST_WEIGHT` 0.556 each, scaling waves shorter than a
  third of the dominant), **short-wave warp** (`FINE_WARP`: phases of those waves shifted by k .
  D(p) from three endless-noise fields, slopes following). A sum, not a baked spectrum, because a
  tile repeats.
- **Sea states** (`STATES`, `seaState(what, extra)`): `calm`, `breeze` (default), `swell`,
  `rough`, `storm`. Keys: `wind` (m/s), `direction` (degrees, as `sunDirection`'s azimuth: where
  waves run to), `height` and `length` (default fully developed: 0.21 U^2 / g and 8.17 U^2 / g),
  `swell` `{height, length, direction}` or `null`, `foam`, `chop`, `gusts`, `gravity`. A height
  over a tenth of the length is refused.
- **No shimmer.** Each wave fades by wavenumber x the pixel's footprint on the water (`filter`, 0.8
  px); the loop stops at the first wave finer than it. Faded slopes become roughness (a covariance
  widening the glitter); slopes finer than the list: Cox-Munk (0.003 + 0.00512 U) less the list's.
- **Light**: `(1 - F) body + glitter + mirrored sky`, then foam, dusk curve, air. Fresnel at index
  1.34; the mirrored sky is the air's own table from sea level (`sky.skyAt(0)`); a rough far sea
  uses two facet orientations (`fast` one). Glitter: Gaussian slope distribution with the kept
  covariance and Smith shadowing x the sun after the air (redder sun, lower burn: 2 to `BURN`);
  slopes in the water's local level. Looks: `LOW_HAZE` (glitter dimmed by a low haze), `DUSK_MIRROR`
  (0.4: least mirrored share at dusk, film exposure), `RELIEF` (darker troughs and lit crests for
  steep seas). Body: matt water colour, more through faces turned to the eye (`glow`).
- **Waters** (`WATERS`, `waterOf`): `ocean`, `green`, `tropical`, `grey`, `methane` (index 1.27);
  or `{color, shallow, index, foam, glow}`.
- **Foam** only when it blows: cover 3.84e-6 U^3.41 (Monahan and O'Muircheartaigh) x `foam`, at
  most `FOAM_MOST` 0.12, placed where crests meet and fronts are steep; streaks from the crest
  measure `FOAM_LAG` 2.2 s ago; varied by the baked pattern `space-sea/lace` (256 px) read through
  `untiledGrad` (never repeats). Beyond resolved waves: mean cover.
- **Depth** (optional): `depth: {glsl, uniforms}` defining `float seaDepth(vec2 p)` (metres of
  water along the sea's +x/+z): colour goes to `shallow` over `shoal` m; under 0.25 m the sea is not
  drawn. **Shade** (optional): `shade: {glsl, uniforms}` defining `float seaShade(vec2 p)` (share of
  sunlight reaching the water; default 1), used by §123.5.
- **Lookup**: `water.heightAt(x, z, t)`, `normalAt`, `pointAt` (on the sphere); pure
  `heightAt(list, x, z, t)`, `surfaceAt`, `normalAt`, `gustAt`: exactly the sum the picture draws
  (phases at the camera in double precision each frame). The list depends on `quality` and `waves`
  (a `fast` preview is a smoother sea). `LOWEST` 0.5 m: lowest supported camera.
- **Options** of `sea(renderer, sky, options)`: `state` and any state key, `seed`, `water`,
  `quality` (`fast`: 16 waves, 16 px grid, one facet; `standard`: 32, 8 px, two; `fine`: 48, 4 px,
  two), `waves`, `anchor` (unit vector from the world's middle to the tangent point; default +y),
  `filter`, `depth`, `shoal`, `shade`. Unknown names refused with the closest one.
- **Limits.** No breaking shapes, spray, wakes, shore waves, shadows or reflections of objects
  (only sky and glitter, not the sun's disc); waves on a plane tangent at the anchor; no refraction;
  no moon light.
- **Parts** (`data/web/parts/space-sea.js`, kind `sea` after `air`): `sea-calm`, `sea-breeze`,
  `sea-rough`, `sea-storm`, `sea-sunset`, `sea-dusk`, `sea-from-20-km`, `sea-methane`.
- **Exports.** `sea`, `Sea`, `seaState`, `waveList`, `waterOf`, `surfaceAt`, `heightAt`,
  `normalAt`, `gustAt`, `horizonDistance`, `horizonDip`, `fresnel`, `slopeVariance`, `whitecaps`,
  constants `STATES`, `WATERS`, `QUALITIES`, `DETAIL`, `GUSTS`, `GUST_WEIGHT`, `FINE_WARP`, `BEND`,
  `FOAM_MOST`, `FOAM_LAG`, `LOWEST`, `LOW_HAZE`, `RELIEF`, `DUSK_MIRROR`, `VERSION` (2; in the foam's
  bake key). Tests: `tests/test_web_space_sea.py`.

### 123.5 Cloud decks, towers, lightning and a giant's decks: `vidgen/space-clouds` (Step 383)

`const weather = clouds(renderer, sky, {sky: "fair", seed: 4}); scene.add(weather.object);
weather.update(t, {camera})` after the air's `update`. `data/web/modules/space-clouds.js`
(`vidgen/space-clouds`, in `VIDGEN_MODULES`; imports `three`, `AIR_GLSL`, `DISPLAY_GLSL`, `RADII`,
`sunlightAt`, `skyAmbient` of `vidgen/space-air` and `resolveOptions`, `bandRamp`, `linearColor` of
`vidgen/space-bodies`), in the air's and §123.4's frame.

- **Exact spans, not a jittered march** (marches grain or terrace thin clouds). A deck is a shell
  of the world's sphere between `base` and `top` (m); each ray is cut with every shell
  (`shellSpan`, closed form) and tower, stretches walked front to back until 1.5 % of the light is
  left; the camera may be under, in, between or over decks.
- **Height field from one tile.** `noiseTile()` (`TILE` 256, four channels, from integer hashes:
  the same numbers in Node; not baked; `.mean`). `deckField` reads it four times (broad weather
  twice, clouds stretched along the wind by `stretch`, fine caps); cloud where the pattern exceeds
  `level`, the value a share `cover` of places exceeds (so `cover` is the covered share, within
  0.06); top `floor + sqrt(rise (pattern - level) / span)`, flat base but for `ragged`. Readings
  drift with the wind: a pure function of time. Mip level from the larger of footprint and step.
- **Never repeats.** Every reading goes through `untiled(u, v, salt, warp)` (`UNTILE`: endless
  lattice of cells one repeat wide, each with its own offset and one of sixteen turns, edges blended
  over `blend` keeping mean and contrast); the clouds' reading is first shifted by `warpNoise()`.
  Whole repeats at the camera reach the shader as `uDeckI` beside the fraction `uDeckR` (stable far
  from the origin). `aloft(deck, height)` boosts the broad weather when the camera is high above a
  deck (`ALOFT` `{from: 3, to: 15, boost: 2}` cloud widths over the top; closed or empty decks stay
  so); camera height reaches the shader as `uDeckG.x`; `valueAt` / `coverAt` take it as a fourth
  argument (default 0); `Clouds.coverAt` uses `clouds.height`.
- **Steps.** `QUALITIES` `[picture share, COARSE, FINE]`: `fast` [1/3, 6, 3], `standard` [1/2, 8,
  4], `fine` [1, 10, 5]. Coarse steps read the mean and skip empty space; fine steps solve the part
  under the top as a quadratic's roots (`cloudPart`), so no cloud is straddled. Faces are pushed in
  by the fine caps (`fray`; a displacement as seen, faded with distance); four neighbouring pixels
  offset their steps and the overlay reads four times, so edges are soft.
- **Towers.** Lumpy columns leaning downwind, either still growing (round top) or with an anvil,
  by seed; 24 steps; closed forms.
- **Light** (shaped, not simulated): sun after the air at each deck's height (`sunlightAt`) dimmed
  by the cloud over the place and sunward, a forward lobe for silver linings, sky light from above
  (`skyAmbient`), light from below. Decks deeper than one optical depth shade decks below
  (`cloudShade`) and, via `shade`, the sea. Then the dusk curve and the air to the cloud.
- **Lightning.** `stormOf(lightning, {seed, towers, deck})`: seeded flashes (`strikeTimes`: `rate`
  a minute, never two within 0.25 s) and stated `times` (seconds, events with `time` such as
  `ctx.music`'s, or a `vidgen/music-time` `trackArrays` track whose gains scale them), inside a
  tower (else the lowest deck near the camera). A flash lasts `FLASH_SECONDS` 0.55
  (`flashLevel(age, strokes)`: one to four strokes), lifted with the film exposure to the power
  `FLASH_LIFT` 0.8. `MOST`: decks 4, towers 6, flashes 3.
- **A gas giant** has no ground. `giantAir(world, {density = 8})`: the world's `space-bodies` air 8
  times as deep (ice giants 8 / 3). `giantSky(world, {latitude = 22, scale = 27000, radius, towers
  = 0, squeeze = 40})`: decks at `GIANT` heights in units of `scale`: a dark deep deck, the main
  deck with `stripes` (64 colours of the planet's `bandRamp` round the latitude, `squeeze` times
  narrower than true; `squeeze: 1` is true), a haze, towers only when asked, wind east 90 m/s, and
  `floor` (0.03 of the belts' colour) to the sphere's horizon (`sky.under(true)`). A deck may take
  `stripes: {colors, span}`; stripe code is compiled only when a deck has them.
- **Picture.** Drawn in `update` into a half-float target at the quality's share, laid over dome
  and sea by one full-screen pass (`renderOrder` -800, no depth test): every scene object stands in
  front of every cloud.
- **Options.** `sky` (`SKIES`: `fair`, `overcast`, `layers`, `towers`, `storm`) or `decks`
  (`DECKS`: `cumulus`, `stratus`, `cirrus`, or `{type, base, top, cover, size, stretch, density,
  weather, rise, floor, soft, fray, ragged, puff, color, beyond, stripes}`; at most 4), `towers` (a
  number or `{count, seed, spread, radius, base, top, anvil, density, color, at}`; at most 6),
  `lightning`, `seed`, `wind`, `direction`, `quality`, `floor`, `anchor`, `behind` (§123.6).
  Unknown names fail with the closest one.
- **Object.** `object`, `update(t, {camera})`, `decks`, `towers`, `flashes(t)`, `coverAt(deck, x,
  z, t)`, `horizon(deck)`, `shade` (`{glsl, uniforms}` for the sea), `uniforms`, `target`,
  `dispose()`.
- **Limits.** One top over one base (no overhangs); no rain, fog, rainbow; towers cast and take no
  shadow; the sea mirrors no cloud; decks lit by the sun at the camera's place; decks on a plane
  tangent at the anchor; no rings in a giant's sky; matches `space-bodies`' cloud map in colour and
  cover, not placement.
- **Parts** (`data/web/parts/space-clouds.js`, kind `cloud` after `sea`): `clouds-fair`,
  `clouds-sea-of-cloud`, `clouds-sunset`, `clouds-towers`, `clouds-between-decks`,
  `clouds-lightning`, `clouds-over-sea`, `clouds-giant`, `clouds-ice-giant`.
- **Exports** (this section's; later sections add more): `clouds`, `Clouds`, `deckOf`,
  `deckField`, `towerList`, `stormOf`, `strikeTimes`, `flashLevel`, `giantSky`, `giantAir`,
  `noiseTile`, `shellSpan`, `deckHorizon`, `untiled`, `warpNoise`, `aloft`, `latticeNoise`,
  `NOISE_GLSL`, constants `DECKS`, `SKIES`, `QUALITIES`, `MOST`, `TILE`, `GIANT`, `FLASH_SECONDS`,
  `FLASH_LIFT`, `UNTILE`, `ALOFT`, `VERSION` (2). Tests: `tests/test_web_space_clouds.py`.

### 123.6 Ground with relief: `vidgen/space-land` (Step 384)

`data/web/modules/space-land.js` (`vidgen/space-land`, in `VIDGEN_MODULES`): `land(renderer, sky,
options)` → `Land`, ground under a `vidgen/space-air` sky. No forests or plants.

- **The ground** is a height over the world's sphere, a pure function of the place (x east, z south,
  metres): `heightOf(field, x, z) = reliefAt(recipe, macroAt(macro, x, z)[0], x, z)`.
- **Macro: tie to the globe.** `macroOf(renderer, world, at, radius)` runs `vidgen/space-bodies`'
  own bake code (GLSL via its export `surfaceSource(type)`, numbers via `bakeInputs(o)`: same
  continents, craters, volcanoes, canyons) on a 384 x 384 lattice a 400th of the radius apart
  (`MACRO`) round `at` ([latitude, longitude]; +x east, -z north), plus the paint code for colour.
  A cubic B-spline through it (`macroAt`) x `TYPES[type].relief` x radius is the macro height:
  forms wider than about two cells are the globe's, in its places; finer ones are this module's.
  Flat ground, snow line (plus `snowOver` 300 m) and rock, snow and sand colours come from the
  globe (`TYPES[type].colors`). The macro lattice is the one part made by the GPU.
- **Recipe** (`recipeOf(type, changes, seed)`; every number an option; `reliefAt`): `mountains`
  (ridged multifractal after Musgrave, octaves from `length` down to `FINEST` 16 m, `erosion`,
  `ridged`, crest rounded under `CREST`, `warp`, `height`, `sharp`, `mid`, grown between macro
  heights `from` and `to`, `base` elsewhere), `strata` (benches `step` apart, `soft`), `rough`,
  `dunes` (`length`, `direction`, fields), `craters` (five classes, `largest`, `density`;
  `CRATER_CELLS`), `canyons` (`{depth, width, length, floor, steps, branches, wander}`: winding
  loops where a slow noise is zero, benched walls with risers `RISER` 0.12), `volcanoes` (`{height,
  radius, spacing, density, crater, ridges}`: at most one cone per cell; `coneAt`), `materials`.
  `reliefAt` adds cones, then cuts canyons, after everything else. Noise: integer-lattice gradient
  noise, 32-bit hash, sixteen gradients, quintic fades (`hash2`, `noised`, `GRADIENTS`).
- **Presets** (`PRESETS`: world, place, changes, suitable air): `alpine` (Earth-like at [-34.5,
  20]), `mars` ([-8, 40]), `canyon` ("ochre" at [49, -172]), `dunes` ("ochre" at [-52, -150]), `snow`
  ("boreas"), `volcanic` ("ember", thin air), `airless` ("moon"; `vacuum(radius)` gives a black-sky
  air; `RADII`). `survey(renderer, world)`: a world's heights all round, to choose a place.
- **Method: per-pixel ray walk through height maps** (a camera-centred mesh's outline slides; the
  walk's is exact).
  - *Maps.* Up to `MAPS` 11 square maps of doubling width round the camera (`WIDTH` 4,096 m up,
    never over 1.6 radii; `mapWidths`), `cells` across by `QUALITIES` (`fast` 256 / 512, `standard`
    512 / 1024, `fine` 1024; for pictures up to 400 rows / larger). A map's middle moves in
    sixteenths of its width (`mapMiddle`), so cells keep their world place and nothing pops; terms
    finer than two cells fade to their mean; a place reads map k from 0.4 of map k - 1's width on
    (`mapFor`), blending over the last third. Maps finer than needed are not baked.
  - *Walk* at half picture size (`fast` a third): steps of 0.7 of the height over ground, up to 96
    (`fast` 64, `fine` 144), five halvings. Each full pixel then refines on the nearest and farthest
    of four answers (outlines between ridges exact, one-pixel soft edge to the sky), shades with
    shading-only grain, and writes `gl_FragDepth`.
  - *Baked* via `vidgen/baked` (`space-land/map`, float bits exact): all maps of a page's first
    update, later only maps from the fourth on, so a flying camera does not fill the cache. Shadows
    are not cached.
- **Materials** by height and slope: flat ground, scree and rock between `steep[0]` and `steep[1]`
  (two colours in beds `band` m high), `sandy`, snow above the line and off faces steeper than
  `snowSteep`, `gullies`, lava `glow`. Volcanoes (code compiled only with them) have lava lakes and
  channels; `ground.setGlow(level)` sets the glow from then on (call per frame for a music pulse).
- **Light.** Sun after the air; the ground's own shadow (baked per map and sun: a moving sun
  rebakes all); `shade` (clouds); sky light dimmed in hollows; bounce; dusk curve; `airThrough`.
- **With the other parts.** Order: dome, ground (render order -860), sea, clouds.
  `sea(renderer, sky, {depth: ground.depth})`; `clouds(renderer, sky, {behind: ground.behind})`
  (compiled in only when given: clouds behind a mountain are hidden); then
  `ground.shadedBy(weather.shade)`. Scene meshes are hidden by ground in front (its depth).
- **Lookups.** `ground.heightAt(x, z)`, `normalAt`, `pointAt(x, z)`, `above(position)`,
  `cell(map, i, j)`, `horizon` (`{distance, dip, height, over, finest}`), `definition()` (recipe and
  macro heights as plain data; the recipe's 34 slots keep fixed index, length, turn and seed). The
  finest map agrees with `heightAt` to about 1.3 m.
- **For another program** (§123.7): `reliefAt` and `macroAt` sit at the top of the module with no
  three.js (32-bit wrapping integer products in the hash, doubles elsewhere); the lattice comes from
  `ground.definition().macro.heights` (n x n, rows along +z, times `scale`).
- **`LAND_GLSL`** with `ground.fieldUniforms` and `NL = ground.maps.length`:
  `float landHeight(vec2 p, float foot)` for another module's shader.
- **Limits.** Soft under about 400 m (no rocks or cliffs); one ridge character (no rivers); far
  skylines smoother than near; a camera inside the ground gets a plain colour; the frame is flat
  (usable within about half a radius of the place).
- **Parts** (`data/web/parts/space-land.js`, kind `land` after `cloud`): `land-alpine`,
  `land-alpine-from-30-km`, `land-mars`, `land-canyon`, `land-dunes`, `land-snow`,
  `land-volcanic`, `land-airless`, `land-coast`.
- **Exports.** `land`, `Land`, `macroOf`, `survey`, `recipeOf`, `reliefAt`, `macroAt`, `heightOf`,
  `normalOf`, `flatMacro`, `hash2`, `noised`, `bowl`, `coneAt`, `horizonDistance`, `horizonDip`,
  `rayHeight`, `mapWidths`, `mapFor`, `mapMiddle`, `placeFrame`, `vacuum`, constants `PRESETS`,
  `TYPES`, `QUALITIES`, `WIDTH`, `MAPS`, `FINEST`, `MACRO`, `OCTAVES`, `GRADIENTS`, `CREST`,
  `RISER`, `CRATER_CELLS`, `RADII`, `LAND_GLSL`, `VERSION`. Tests: `tests/test_web_space_land.py`.

### 123.7 Flight paths: `vidgen.flight`, `flight_data:` → `ctx.flight` (Step 385)

`src/vidgen/flight/` (no manim) turns a flight told in words into float64 position, velocity and
attitude for every frame of a `web` scene, checked never to come under the ground, and hands it to
the page as `orbit_data` does (§122.3).

- **One bridge.** Flights ride in the orbit payload (`orbits.flights`): the same `WebPage(orbits=)`,
  `make_web_clip`, `web_page_layouts`, `clip_inputs` and `vidgen still` plumbing. Sibling param
  `flight_data:` (maker `scenes/flight_data.py`, cache `web/flights.py`, mirroring `orbit_data`).
  `data/web/flight.js` is added only on pages whose payload carries flights; it runs after
  `orbits.js` and builds `ctx.flight` (no orbit data: no `ctx.orbits`). Clip inputs gain
  `orbits.flight_helper` (its SHA-256) only then.
- **Frames** (`vidgen.flight.frames`). *Planet-fixed* PF: origin the centre, z the IAU north pole,
  x the prime meridian; a place (φ, λ, h) is (R + h)(cos φ cos λ, cos φ sin λ, sin φ). *Local* L
  (the scene's): metres, origin on the sphere under `at = [φ₀, λ₀]`, x east, y up, z south, centre
  (0, −R, 0): the default frame of `space-air`, `space-sea`, `space-clouds`, `space-land`. PF = R·up
  + M·L, M = [east | up | south] (`space-land`'s `placeFrame(at)`). Heights are over the sphere,
  |L − (0, −R, 0)| − R; height over ground is h − `heightAt(L.x, L.z)` (`Land.above`). *Ecliptic*
  E = F(jd)·PF (F from `vidgen.orbits.rotation`), v_E = F·v_PF + ω × r_E. `LocalFrame.to_fixed /
  from_fixed / to_ecliptic / from_ecliptic / ecliptic_axes / place / geodetic / chart /
  heading_vector / heading_of`. Velocity is over the ground (= air speed, no wind). `ground: flat`:
  y is the height, no latitudes, no re-entry.
- **Worlds** (`vidgen.flight.worlds`): radius the page air's (`space-air` `RADII`, airless from
  `space-land`), GM from `vidgen.orbits.BODIES` (invented: Earth's mean density), spin from
  `vidgen.orbits.rotation`, an isothermal exponential air (scale height the page's; sea-level
  density and γ here: Earth-like 1.225 kg/m³, 1.40; Mars-like 0.020, 1.29; `thin` 0.25, `thick`
  4.9; speed of sound √(γ g₀ H), constant). A land preset's world is its air's.
- **Kinematics** (`vidgen.flight.plan`): channels air speed V(t), height h(t), turn rate ψ̇(t)
  (heading from north towards east). The local frame turns with body rates (ψ̇, 0, V_h / (R + h)),
  integrated by fourth-order Magnus at steps ≤ 0.05 s, composed by a parallel prefix product;
  acceleration analytic. Every change of V, ḣ, bank or curvature uses the septic smoothstep S(u) =
  35u⁴ − 84u⁵ + 70u⁶ − 20u⁷, so position is smooth to the third derivative where legs meet.
- **Legs** (`vidgen.flight.spec`): at most one horizontal manoeuvre, one vertical, one speed
  change; lasting `for` seconds, `until` a scene time (seconds or 'bar 9 beat 3'), or as long as
  needed; unnamed things are held. `straight: s`. `turn: {to | by, side, bank | radius,
  roll_rate}` (coordinated, g_eff = g(h) − V_h² / (R + h); roll rate default 20°/s; heading change
  exact). `climb` / `descend: {to | by, rate, accel}` (default 10 m/s, 0.25 g peak; `{rate}` alone
  climbs on); `level: true`. `speed: {to | mach, rate}` (mean 2 m/s²). `waypoints: [[x, z] | {lat,
  lon}, ...]` or `{points, bank_limit}`: septic Hermite pieces in the leg start's tangent plane with
  G3 continuity; bank checked against `bank_limit` (60°; error names the waypoint). `circle:
  {around, radius, turns, side}`. `follow: {clearance, rate, push, smoothing}`: terrain following
  over consecutive legs (push-overs ≤ (1 − push) g, slopes ≤ `rate`, smoothed over `smoothing` 4 s).
  `land: {glide, flare, touchdown, brake}`: descent at V tan(glide), flare to zero sink exactly at
  the ground under the touchdown point, roll-out to a stop. `reentry`: below.
- **Attitude and numbers.** Nose along velocity raised by the angle of attack (`aoa`, a look: 3°
  per g); bank φ = atan(f_side / D), D = ½(f_up + √(f_up² + (0.1 g)²)) from the specific force
  (with Coriolis and centrifugal parts): upright through push-overs, 0 in free fall. Body axes x
  left wing, y up, z nose (as `vidgen/space-craft`). Per frame: position, velocity (local frame),
  quaternion (x, y, z, w; w ≥ 0), speed, Mach, height over sphere and over ground, load factor
  (negative when down), bank, pitch (flight-path angle), heading, angle of attack (rad), vertical
  rate, heating √(ρ / 10⁻⁴ kg/m³)(v / 7 km/s)³ (1 ≈ a returning orbiter's peak), flight time
  (negative before the start: it waits), the path (`path_samples` points) and the planned legs.
- **Never below ground.** Checked at 1/24 s within 500 m of the highest possible ground (else every
  0.5 s) against ground plus `margin` (default 20 m: far ground is drawn smoother than `heightAt`)
  plus the sea's `waves`; a landing may reach touchdown level. Too low: `VidgenError` naming flight,
  time, leg, place (x, z, lat, lon), clearance and remedies (climb, follow, `lift: true`). `lift:
  true` adds a smooth lift and replans, up to four times, with a warning. Load factor over
  `max_load` (3): a warning.
- **Ground heights** (`vidgen.flight.terrain`, `web/land.py`). `LandGround` ports `space-land`'s
  height definition to numpy (unsigned 32-bit wrapping hash, every recipe part, the B-spline, same
  order: must equal the page's `heightAt`; tests assert under 10⁻⁹ m). `land_definition(options,
  air)` opens a 16x16 page once, reads `ground.definition()` and caches it at
  `<cache folder>/ground/land-<key>.json` (heights as float32 bits; key: options, air,
  `vidgen/baked`'s code digest, layout version; cleared by `vidgen cache clear`). `SphereGround`
  (level at `elevation`), `SeaGround` (`waves` added to the margin), `FlatGround` need no page.
- **Re-entry** (`vidgen.flight.reentry`; `start: {orbit: Ship, at: 'bar 5'}` takes the orbit body
  at that frame via `from_ecliptic`, or a start with height, speed, climb). Physical: the start is
  the orbit's two-body motion seen from the turning world; the glide is the equilibrium glide in the
  exponential air (L = m g (1 − v²/v_c²), v_c = √(g₀ R), D = L / E with `lift_to_drag` 1.2, β =
  `loading` 450 kg/m²; closed-form speed). A look: a `blend` (600 s) from orbit to glide by S;
  S-turns between ±`bank` 60° with `reversals` 3 of `reversal` seconds; an `end` that reaches
  `to.height` and `to.speed` level with three continuous derivatives; `aoa` 40° falling to cruise.
- **YAML** (`flight_data:`, `vidgen.scenes.flight_data.FlightData`, pydantic): `flights` (each
  `name`, `start`, `legs`, `roll_rate`, `accel`, `vertical_accel`, `bank_limit`, `max_load`, `aoa`,
  `lift`), `ground` (`{land: alpine}` or `{land: {preset | world + at, seed, mountains, ...,
  air}}`, `sea` / `{sea: {waves}}`, `sphere` / `{sphere: {elevation}}`, `flat`), `world` (default
  the land's air's, else earth), `at` (default the land's place, else [0, 0]), `start` (scene time
  of flight time 0), `speedup` (default 1; from orbit the orbit data's), `margin`, `path_samples`.
  Unknown keys get a did-you-mean (land options checked against `space-land.js`'s names); bars need
  `music_data`, an orbit start `orbit_data` with that body. User keys: docs/CONFIG.md ("Flight data").
- **Python API.** `vidgen.flight` (in `vidgen.api` as `flight`): `Flight`, `Leg`, `Start`, …,
  `FlightContext(world, frame, ground, margin, to_flight)`, `FlightRun(spec, context,
  start_state)` with `sample(t)`, `position`, `state_at`, `path`, `legs`, `warnings`; `LocalFrame`,
  `world`, `WORLDS`, the grounds, `height_of`, `relief_at`, `macro_at`, `hash2`, `noise`,
  `entry_profile`, `heating`. `vidgen.api.web_scene_flights` (= `scene_flight_data`, mirroring
  `web_scene_orbits`), `web_with_flights`, `web_land_definition`, `web_land_settings`.
- **Page** (`ctx.flight`): `names`, `flights`, `world`, `anchor` (lat, lon, local axes in PF),
  `ground`, `frame`, `units`, `approximations`, `warnings`, `index(t)`, `time(name, t)`, `active`,
  `position`, `velocity`, `quaternion`, `speed`, `mach`, `height`, `aboveGround`, `load`, `bank`,
  `pitch`, `heading`, `aoa`, `heating`, `climb`, `path(name)`, `legs(name)`, `series(name)`,
  `place(object, name, t)`. Values are the frame's own (round(t × fps)), never interpolated: exactly
  Python's float64. `craft.fly(ctx.flight, {flight: "Plane"})` (`vidgen/space-craft`) places a
  craft every `update(t)`. Pages drawing land and air must use the flight's `at` and world.
- **Cache key** (`build/flights/flight-data-<key>.json`): data version, vidgen version, SHA-256 of
  the flight code (`vidgen/flight/`, `vidgen/orbits/`, `scenes/flight_data.py`,
  `scenes/space_params.py`, `web/land.py`), settings, frame rate, frames drawn and the scene's own;
  with a land the page code digest; with bars the score's bar and beat lengths and `t0`; from orbit
  the orbit payload's digest. Deterministic. Tests: `tests/test_flight.py`.

### 123.8 Space plane parts: `vidgen/space-plane` (Step 386)

`data/web/modules/space-plane.js` (`vidgen/space-plane`, in `VIDGEN_MODULES`): winged craft from
parametrized parts (lofted body, one wing function with presets, tails, engines, gear, moving
surfaces) and six ready-made planes varying by seed. Invented designs; a look, not aerodynamics.

- **A sibling of `vidgen/space-craft`**, so `space-craft`'s bytes (in every space page's key) do
  not grow. Imports `CraftKit`, `Craft`, `GLARE`, `ACCENTS`, `platingMaps`; `PlaneKit` extends
  `CraftKit` (all its parts), `Plane` extends `Craft` (`update`, `fly`, `shade`, `occluders`,
  `shadows`, `size`, `info`, far point of light).
- **Axes** (craft kit's): +z nose, +y up, +x the LEFT wing; metres, true size; origin the body's
  middle (gear or bay never move it). With `craft.fly` (§123.7) a right turn lowers the right wing
  (−x, green light).
- **Body** (`kit.body(options)`; numbers: `bodyShape`): `length` (3 to 120 m), `width`, `height`
  (or `diameter`), `nose` (`NOSES`: `ogive`, `blunt`, `pointed`, `chined`, `needle`),
  `noseLength` (0.3), `droop`, `belly` (0 round .. 1 flat), `tail`, `tailLength`, `upsweep`,
  `hump` `{from, to, height}`, `bay` `{from, to, width}`, `cap`, `waterline`, `skins` `{top, belly,
  cap}`. Lofted from superellipse sections with whole-sheet normals (no crease between surfaces).
  `userData.shape`: `point(s, angle, out)`, `normal`, `top`, `bottom`, `half`, `under(s, x)`,
  `over(s, x)` (s 0 nose .. 1 tail; angle 0 left, 90 top).
- **Wing** (`kit.wing(options)`; outline: `wingPlanform` → `{semi, le(eta), te(eta), chord(eta),
  sweepAt(eta), area, aspect, taper, mean}`): `preset`, `span`, `rootChord` (or `chord`),
  `tipChord` (or `taper`), `sweep` (−60 to 85°), `crank` + `sweepInner`, `curve`, `dihedral`,
  `thickness`, `airfoil` (`round`, `sharp`, `flat`), `twist`, `fillet` with `inboard`, `edge`,
  `controls` (`[{name: elevon | flap, from, to, chord}]`), `tip` (`{height, cant, sweep, taper}`),
  `allMoving` (canard), `skins` `{upper, lower, edge}`. Mirrored; straight trailing edge. `WINGS`
  presets: `delta`, `double-delta`, `cranked-arrow`, `swept`, `straight`, `ogival`, `stub`,
  `blended`, `long`.
- **Tails** (`kit.fin`, the wing panel stood up): `type` `single`, `twin` (`spacing`, `cant` 12°),
  `vee` (`cant` 42°); `height`, `rootChord`, `tipChord`, `sweep`, `thickness`, `airfoil`,
  `rudder` (bool or `{from, to, chord}`), `sink`.
- **Other parts**: `kit.nozzles({count, exit, kind, layout: row | block | ring})`,
  `kit.nacelle({length, radius, spike, pylon, kind})`, `kit.intake({width, height, length})`,
  `kit.gear({length, wheel, wheels, fold})`, `kit.patch(bins, body, {from, to, a0, a1, skin})`.
- **From one description**: `planeFrom(spec, options)` with `body`, `wing`, `fins`, `canard`,
  `engines`, `nacelles` (`mount: wing | body | tail`), `intakes`, `gear` (`{nose, main, track,
  clearance, wheel}`), `cockpit` (`{style: panes | band, ...}` or false), `windows`, `markings`,
  `brake`, `bodyFlap`, `rcs`, `lights`; surfaces placed by `at` (share from the nose) and `up` (−1
  belly .. 1 back). Or `kit.plane(body)` after `body.add(wing)`. `planeSpec(kind, {seed})` returns
  a ready-made description to change.
- **Moving parts** (`Plane`): `controls({elevon, roll, rudder, flap, brake, bodyFlap, canard})`
  (degrees; elevon + trailing edges down, roll + right, rudder + nose left), `gear(k)`, `bay(k)`
  (doors to 112°), `cabin(k)`, `update(t, {controls, gear, bay, cabin, auto, ...})`. On a flight
  the surfaces follow the rates (`controlsFromRates`, a look); `auto: false` or `controls` stops it.
- **Anchors** (`plane.anchors`; `plane.anchor(name)` in the scene): `nose`, `tail`, `belly`,
  `cockpit`, `leadingEdges`, `finEdges`, `wingTips`, `finTips`, `nozzles`, `intakes`, `gear`,
  `ground`, `low`. Used by §123.9.
- **Surfaces** (`SURFACES`: three 512 px maps from `platingMaps`, once a page, not baked): heat
  tiles, blankets, panels, bare metal, dark edges and nose cap. `SCHEMES`: `tiles`, `grey`,
  `metal`, `dark`, `paint`, `plain` (no heat shield). `color`, `belly`, `accent`, `scorch` (0 .. 1
  wear as vertex tint). Markings: stripes and an invented registration from the seed. No flags,
  names or emblems.
- **Ready-made** (`plane(kind, {seed})`, `PLANES`): `glider`, `freighter`, `needle`, `lifter`,
  `scout`, `skiff`; `planeFleet(kind or kinds, {count, seed, spacing})`: a vee of consecutive seeds
  at "far" detail. No ready-made plane is a double delta with one tall fin and three bells, and no
  real or invented vehicle, agency or company is named.
- **`problems()`** (as `vidgen/space-scale`'s: sentences, empty when fine): surfaces off the body,
  implausible span, misplaced wing area, gear not reaching below the lowest part, the look-alike
  layout above. Ready-made planes have none.
- **In air and space.** `MeshStandardMaterial`s with the glare cap, lit by `sky.light.*`; call
  `sky.haze(m)` on each of `plane.materials`. Land hides a plane by depth; planes draw in front of
  every cloud and cast no shadow on ground or sea. In space: `plane.shade(star)`, environment from
  `craftEnvironment` or `paintedEnvironment`; `plane.shadows` sizes self-shadows.
- **Parts** (`data/web/parts/space-plane.js`): kind `craft`: `plane-glider`, `plane-freighter`,
  `plane-needle`, `plane-lifter`, `plane-scout`, `plane-skiff`, `plane-open`, `plane-landing`,
  `plane-fleet`; kind `craft-part`: `plane-part-bodies`, `plane-part-wings`, `plane-part-tails`,
  `plane-part-engines`, `plane-part-gear`, `plane-surfaces`. Tests: `tests/test_web_space_plane.py`.

### 123.9 Re-entry and flight effects: `vidgen/space-effects` (Step 387)

`data/web/modules/space-effects.js` (`vidgen/space-effects`, in `VIDGEN_MODULES`; imports `three`
and `AIR_GLSL`, `DISPLAY_GLSL`, `sunlightAt`, `skyAmbient` of `vidgen/space-air`): re-entry glow,
vapour trails, exhaust in air, transonic and hard-turn vapour. Imports neither `space-craft` nor
`space-plane` (works on landers and ships; keeps their keys).

- **One call.** `effects(craft, {flight: ctx.flight, name, sky, seed, quality, shape, anchors,
  scaleHeight, path, sun, light, ambient, reentry, contrails, exhaust, vapour})` → `Effects`:
  `object` (add to the scene), `attached` (added to the craft), `update(t, {...})` (after the
  craft's), `state` (`heat`, `air`, `wind`, `cone`, `wingVapour`, `plume`, ...), `parts`, `shape`,
  `dispose()`. A craft is anything with an `object`, a bounding ellipsoid (`shape: {center,
  radii}`; default from plane anchors, else mesh boxes) and `anchors`; kit engines via
  `craft.engines`. Groups (`true` or options): `reentry` {`full` 0.65, `level`, `shock`, `skin`,
  `wake`, `sparks`, `trail`, `head`, `thickness` 0.055, `length` 7, `persist` 5}, `contrails`
  {`from` nozzles | wingTips | tail | places, `band` [8000, 9000], `always`, `life` 70, `size`,
  `level`, `color`}, `exhaust` {`nozzles`, `level`, `air`}, `vapour` {`cone`, `wings`, `tips`,
  `level`}. `update` overrides (number or function of t): `velocity`, `heating`, `mach`, `load`,
  `height`, `aboveGround`, `air`, `throttle`, `boost`, `pulse` (glow and exhaust multiplier), `sun`.
  Unknown names: did-you-mean.
- **No state.** Every picture is a function of `t` and the flight (integer `hash`, fixed sines);
  only the windward map is kept, a function of the wind direction in craft axes alone. A frame
  drawn after others is byte-identical to the same frame drawn first.
- **Inputs.** `tracker(ctx.flight, name)`: `now` (the frame of `t`) and `at` (linear between
  frames; before the scene's first frame, straight back along its velocity). Without a flight,
  numbers come from `update` and trails follow `path(tau)` or a line. Density `exp(-height /
  scaleHeight)` or `air`.
- **Re-entry** (`heat` = `heating` / `full`): `heatColor` (`HEAT_STOPS`) and `heatLevel` =
  `HEAT_WHITES` 3.2 x h^1.6 (none under 0.02), both monotonic. Shock layer: solid meshes drawn
  once from upwind (orthographic) into a small half-float map (192 px; `fast` 64, `fine` 256); view
  rays sum a layer falling off with distance upwind of that surface, in closed form per step, drawn
  on a ball round the craft and on duplicate "hot surface" meshes each summing only to its own
  surface (the craft hides the glow behind it without a depth texture). Plus hot surfaces, bloom, a
  straight two-stream wake, sparks (`sparkAt`; 36, `fast` 14, `fine` 72; from heat 0.25), and from
  afar a head (≥ 3.4 px marker) and a train along the path for `persist` flight seconds (≥ 1.2 px).
  Exposure: x gain in `camera` / `auto`, x min(gain, 1) in `film`; screen-blended to the canvas,
  added linear into a `vidgen/three-finish` target.
- **Vapour trails.** Soft tubes through rings at fixed birth times (`trailTimes`: 24 a 30th of a
  second apart, 24 a 15th, ..., back to `life`), each where its place on the craft was then, so
  trails stay where laid; widen, thin, lump and snake with age. Only above `band` (or `always`);
  engines within 1.5 m join; at most four. Lit by `sunlightAt` and `skyAmbient`, hazed by
  `airThrough`.
- **Exhaust in air.** Per bell a closed-form flame: core, outer flame and shock diamonds (from 45 %
  throttle), shaped by `plumeShape(air, boost)` (tight in dense air, wide in thin; longer with the
  afterburner; a look tied to density). Replaces a kit engine's plume at the kit's current power.
- **Condensation.** `coneLevel(mach, air)` = exp(-((mach - 0.97) / 0.026)^2) in dense air: two
  closed-form mist discs aft of the body's middle. `wingVapour(load, air)`: from 2.4 g, full at
  5 g: sheets over the wings and wing-tip threads. No sonic-boom ring (by decision).
- **Limits.** In front of every cloud; hidden by ground only via the land's depth; the windward
  map sees solid meshes only; the wake does not follow turns; the glow lights nothing else; the
  layer is tested against its own craft only.
- **Parts** (`data/web/parts/space-effects.js`, kind `effect`): `effect-reentry`,
  `effect-reentry-early`, `effect-reentry-lander`, `effect-reentry-far`, `effect-contrails`,
  `effect-exhaust-air`, `effect-exhaust-thin`, `effect-vapour-cone`, `effect-wing-vapour`. Tests:
  `tests/test_web_space_effects.py`.
### 123.10 Giant ship hulls: `vidgen/space-hull` (Step 388)

`data/web/modules/space-hull.js` (import name `vidgen/space-hull`, in `VIDGEN_MODULES`; imports
`three`, `rng` of `vidgen/music-time`, `CraftKit` / `Craft` / `GLARE` / `ACCENTS` /
`platingMaps` / `craft` of `vidgen/space-craft`). Hulls of ships 0.5 to 10 km long: the large
forms only, with what Step 389 needs to hang the fine detail on.

```js
import {hull, hullFleet} from "vidgen/space-hull";
const ship = hull("carrier", {seed: 4, length: 3000});   // a family of HULLS, another member for every seed
ship.fly(space, {body: "Ship"});                         // a body of ctx.orbits: the bow along the path, the deck away from the world
ship.update(t, {sun, throttle: 0.6});                    // the craft kit's update: bells fire, rings turn, lights blink
ship.scaleRef("ship", {at: "hangar-1", gap: 120});       // a 50 m craft of the kit beside a named place
ship.problems();                                         // [] or sentences
```

- **A sibling module (decision).** As `vidgen/space-plane`: `HullKit extends CraftKit`, `Hull
  extends Craft`; `space-craft.js` is byte-identical to Step 387's, so no existing scene's cache
  key changes. `fly`, `update`, `shade(star)`, `occluders`, `shadows`, `size`, `info`, `engines`
  and `dispose` are the craft's. Axes: +z the bow, +y up (away from the world on a prograde
  flight), +x port; the middle of the bounding box at the origin; metres.
- **The design language** (ours; stated so that later hulls stay in it): (1) every function is
  a mass of its own — crew, propellant, cargo, heat, drive — joined by visible structure, the
  drive far from the crew; (2) one long axis, because thrust loads run along it; (3) radiators
  are the largest surfaces: thin rectangular vanes, warm at the root; (4) nothing is streamlined,
  because these ships never meet air: a bow is a blunt face, a frame, a shield or a ring, never a
  point; edges are chamfers, not curves; rings are polygons; (5) a ship is lopsided where its work
  asks for it (hangars on one side and radiators on the other, one hull set back, an array to
  one side); (6) command sits inside the hull (an anchor, a band on a drum or a terrace front),
  never on a tower; (7) two or three hull tones and one accent a ship.
- **Shapes the kit must not make** (described as shapes only; no work is named anywhere in the
  code, the tests or the documents): a hull whose plan narrows to a point at the bow, with or
  without a raised tower at the stern; a ball with a dish sunk into it; a disc with a second
  hull and engine pods on struts; a spine with a crew ball at its front and a ring behind it; a
  cube; an organic body with arms; a wide head on a thin neck; a great flat triangle. The
  families stay away by construction (a carrier's seed gives `taper` 0.84 to 1 and terraces
  between 0.17 and 0.6 of the length from the bow; the ark's rock is always rough and cut; the
  wheel has no ball; a lance's shield is a faceted cone or disc a fifth of its length wide).
  `forbidden(profile, regions)` and `problems()` name the one layout a description can reach:
  a plan that narrows steadily towards the bow to under 0.45 of its greatest width with a
  `tower-N` in the aft 36 % ("too near a well-known fictional ship"), or to under 0.3 without one.
- **Families** (`HULLS`; each an invented design; `hull(family, {seed, length, ...})`; every
  number below can be given, within the range `hullSpec` checks):

  | family | what it is | usual length | its numbers (shares of the length unless said) |
  |---|---|---|---|
  | `spine` | a long open truss: the drive behind a shadow disc, radiator vanes in one plane, clusters of tanks, crew drums far forward, a docking face as the bow, an array on a mast to one side | 1.2–2.8 km | `girth` (the truss), `drum`, `drums`, `tanks`, `tankCount`, `tank` (girths), `vanes` (2, 4), `vaneSpan`, `bells`, `side` |
  | `carrier` | a thick block with a flat deck: a trench down its middle that opens into a gulf between two blunt prongs of unequal length, hangar slots along one side (or both), a gallery line, stepped terraces and low works on the deck, a keel block, a sponson with radiators on the side without hangars | 1.8–4.2 km | `beam`, `depth`, `taper` (the bow's width over the beam), `trench` (of the beam), `segments`, `hangars`, `side` (1 port, -1 starboard, 0 both), `keel` (of the depth), `vaneSpan`, `bells`, `towers` ([{at, side, len, wid, high}]) |
  | `cluster` | an open frame carrying its load in plain sight: pressure balls, pairs of tanks, a tank lying across, container stacks, gaps; a crew block high on the bow; radiators up and down from the stern | 0.7–1.7 km | `girth`, `aspect`, `vaneSpan`, `bells`, `cells` (a list of `ball`, `pair`, `cross`, `cargo`, `gap`) |
  | `lance` | a very long thin hull behind a faceted shield, the crew drum and tanks close behind it, a box girder with a gantry along its back, a hangar shed slung under it and open to port, a second ring of tanks, the drive far aft on a truss among long narrow radiators | 2.5–6 km | `body` (its width), `shield`, `shieldShape` (`cone`, `disc`), `drum` (body widths), `boom`, `vanes` (3, 4), `vaneSpan`, `bells` |
  | `wheel` | a thick hub with two polygonal crew rings of unequal size turning against each other (1 g at the rim by default), a docking drum as the bow, tanks, a cross of radiators | 0.9–2.4 km | `hub`, `ring` (radius), `second` (the next ring's size), `rings`, `gap`, `at`, `sides`, `spokes`, `vaneSpan`, `bells`, `spin` (rad/s) |
  | `ark` | a worked asteroid: cut flat at the bow, on top and at the stern; a hangar portal built out of the bow face, a polygonal collar with radiators, terraces (stepped piles of thin tiers with low annexes) and works on the mesa, the drive block sunk into the stern | 3–8 km | `girth`, `flat`, `rough`, `mouth`, `vaneSpan`, `bells`, `vaneAngles`, `towers` |
  | `twin` | two unequal hulls side by side, one set back and higher: a drive hull with a trench, a raised crew block and radiators standing from it; a cargo hull with container racks and an open bay of ball tanks in its frame; a yoke round both near the stern, slanting bridges, a hangar pod | 1.2–3.2 km | `beam`, `depth`, `gap`, `stagger`, `second`, `rise` (depths), `bridges`, `vaneSpan`, `bells` |

  Common: `seed`, `length` (200 to 20,000 m), `age` (0 new .. 1: soot towards the stern,
  streaks along the hull), `palette` (`PALETTES`: `bone`, `slate`, `iron`, `sand`, `frost`),
  `inset` (the bells sunk by a share of the length: a way to make a mistake); the kit's `accent`,
  `detail` (`near` | `far`), `wear`, `tile` (metres one repeat of the plate map covers, 240),
  `plate` (the big plates' size, 70 m); a craft's `name`, `camera`, `height`, `sun`, `lights`,
  `marker`, `occlusion` (0 here). `hullSpec(family, options)` is the description as plain JSON,
  `hullFrom(spec, options)` builds it, `hullFleet(families, {count, seed, spacing, detail:
  "far", navy: true})` a formation (`navy`: one maker built it: every hull has the palette and
  the accent the fleet's seed chooses; Step 389). Unknown names are refused with the closest word.
- **How a hull is modelled** (`Shell`, from `hullKit(options).shell()`; a hull of one's own:
  `kit.hull(shell.finish(), {anchors})`). Faces are collected by part (`part(name, {sparse,
  spin})`: a mass; sparse ones give no shadow balls and are left out of the profile) and region
  (`region(name, detail)`). Shapes: `loft` (a polygon carried through stations: prisms, tapers,
  bevelled blocks; `sectionOf(W, H, c, {trench, slots})` gives a cross-section with a trench
  and side slots, so recesses are real geometry that casts shadow), `block`, `lathe` / `drum`
  (round or faceted), `capsule`, `rod`, `truss`, `vane` (a radiator with ribs and edge rails),
  `dish`, `mouth` (a framed recess with depth: a hangar mouth as a dark void), `rock` (a ball
  moved by four octaves of noise, dented by craters, cut flat by planes), `scatter` (low boxes
  on a flat face: the 20 to 100 m break-up). Bells are the craft kit's (`bankPlan({w, h, count,
  layout: grid | ring | row})`, `kit.bells`), at the kit's "far" detail from three bells up,
  each with its plume; lamps are the kit's.
- **Secondary break-up, kept cheap**: every face is cut into plates of `plate` metres, each of
  its own tone (a tenth much lighter or darker); a tiling plate map (the craft kit's
  `platingMaps`, 64 plates of 12 to 60 m a repeat of 240 m, grooves, a normal map); chamfers
  and bevels; ribs at the joints of a carrier, a gallery line along its sides, accent lips over
  the hangar slots; `scatter`ed works on decks; `age` darkens towards the stern. Surfaces
  (`HULL_SKINS`): `hull-a`, `hull-b` (the two tones), `hull-c` (dark metal), `hull-accent`,
  `hull-radiator`, `hull-tank`, `hull-truss`, `hull-rock`, `hull-void` (a recess: nearly black,
  no map), `hull-glass`.
- **Triangle budget** (stated and tested): `near` at most 60,000, `far` at most 20,000.
  Measured, seed 1: spine 13,600 / 8,800, carrier 18,400 / 12,400, cluster 9,200 / 7,900,
  lance 12,400 / 6,600, wheel 13,200 / 10,000, ark 31,300 / 12,900, twin 23,100 / 8,600; 26
  to 37 meshes (one per surface, and per bell its glow and plume). `far`: no plates, half the
  sides, no ribs, works or accents, a coarser rock.
- **The contract for the fine detail (Step 389).** Everything is plain numbers in the hull's
  axes, metres:
  - `hull.regions`: `[{name, detail, surface: {material, expects, density}, skin, box: {min,
    max}, centre, normal, area, charts: [ids], mouth?}]`. Names: `bow`, `midship`,
    `engine-block` (`engine-block-1`, `-2` on a twin), `hangar-N`, `radiator-N`, `tower-N`,
    `tank-N`, `habitat-N`, `ring-N`, `cargo-N`, `trench`, `keel`, `sponson`, `collar`, `rock`,
    `port-hull`, `starboard-hull`, `truss`. `detail` is a key of `SURFACES` (`plating`,
    `windows`, `hangar`, `trench`, `radiator`, `engine`, `tank`, `cargo`, `shield`, `rock`,
    `dock`, `truss`), which says what the surface is made of, what detail belongs there and its
    share of texels. `normal` is the area-weighted outward direction (zero for a region that
    faces all round); `hull.region(name)`.
  - `hull.anchors`: `bells` (`[{name: "bell-N", p, n, radius, kind, bank}]`: the exit's
    middle), `nozzles` (the same as `vidgen/space-effects` reads them), `hangars` (`[{name, p,
    n, width, height, depth}]`: the middle of the opening), `docks`, `lights` (`[{kind, p,
    n}]`), `bridge` (the command place: `{p, n}`), `points` (every named place: `bow`, `stern`,
    `top`, `bottom`, `port`, `starboard`, `bridge`, `hangar-N`, `dock-N`, `bell-N`, `ring-N`,
    `collar`); `hull.anchor(name)`.
  - Two sets of texture coordinates on every hull mesh. `uv`: metres along the face (u along
    the face's width, v along the loft or the profile), continuous within a face, with an
    offset per shape: for tiling detail (a window pattern at true size); the hull's own plate
    map uses it. `uv1`: one atlas for the whole hull. `hull.charts`: `[{id, name:
    "region/face", region, kind: "plane" | "round", size: [w, h] metres, rect: [u0, v0, u1,
    v1], turned (its w runs along v), scale (atlas units per metre), origin, du, dv, normal |
    axis, radius}]`: a point of a plane chart is `origin + du * cu + dv * cv` (cu, cv in metres
    from the chart's corner; for a chart that runs over a bevel the frame is its largest
    face's). Charts never overlap (2/1024 between them; the corner under 4/512 is spare: faces
    without a chart — struts, ribs, scattered works, cargo boxes, faces narrower than 14 m —
    read the texel at 2/512, 2/512). Density: `hull.texel(chart, size)` metres a texel;
    charts share one scale times the region's `density` (windows 1.4, hangars 1.6, radiators
    0.35, rock 0.45); a chart longer than the atlas is drawn smaller by itself. At 4096:
    cluster 0.1–0.45 m, spine 0.27–1.1, wheel 0.38–1.5, twin 0.33–1.5, lance 0.5–2.1, carrier
    0.63–2.9, ark 1.8–8.2 (seed 1). Windows by the thousand on a 3 km hull therefore want the
    tiling `uv` (or a map per region); the atlas suits what is unique: grime, hangar light,
    markings, trench runs. A map on the atlas: `texture.channel = 1` on any map of the hull's
    materials (`hull.materials["hull-a"]`, ...: `MeshStandardMaterial`s shared by the hull).
  - Scale: `hull.size`, `hull.shape.radii`, `hull.profile` (`[{z, x: [min, max], y: [min,
    max]}]`, 40 slices of the solid masses from the stern), `hull.spec` (every number of the
    design), `hull.scale` (atlas units per metre at density 1); `hull.scaleRef(craft, {at,
    gap, seed, detail})` stands a craft of `vidgen/space-craft` (by kind: `ship` is 42 to 58 m)
    or any craft or plane object beside a named anchor, as a child of the hull.
  - The bells are the craft kit's engines (`hull.engines`: `{kind, plume, glow, exit}`;
    `update(t, {throttle})`: a number, a list per bell or a function of t).
- **`problems()`**: a length outside 500 to 10,000 m, a hull wider or higher than 0.85 of its
  length, nearly a cube, a thread, a bell whose exit lies ahead of its block's aft face or
  that fires into another region, two bells through each other, and the forbidden layout.
- **Sense of size at this step** (stills in `/home/claude/work/scratch/ao388/stills/`): a
  normal lens near the hull with a 50 m craft in the frame reads as largest; a long lens from
  far with the world behind is second; a wide lens close along the hull needs fine detail and
  is the weakest so far. Plates of 12 to 60 m read as masonry close up until Step 389 adds the
  small scale.
- **Measured** (2 cores, SwiftShader, straight to the canvas with ACES, in a `SpaceView` with a
  sky, the Earth from a 1024 map and a star; seconds a frame at 1280x720 / 320x180). The sky and
  star alone 0.36 / 0.08. A 3.2 km carrier filling the frame 0.69 / 0.20 (`far` 0.60; shadows
  cost nothing measurable: 0.73 without), small in the frame 0.48 / 0.11; the ark filling it
  0.85, the cluster 0.77; a bank of eight bells firing, seen from astern, 1.17. Building (Node,
  the same code): the first hull of a page 1.0 s (the plate and rock maps), later ones 25 to
  110 ms (`far` 10 to 40 ms). The 14 part tiles: 23 s.
- **A trap found** (not changed here: `space-scale.js` is in the keys of existing scenes): a
  world added to a `SpaceView` by `add(object, {at, size: metres})` instead of as a body of
  the orbit data is drawn over nearer things when the camera is inside its bounding sphere's
  depth range (its interval starts at the view's `near`, the nearest slice holds only the
  world, and the world's shell is never clipped by the far plane). With `orbit_data` and
  `planet(renderer, "Earth", {space})` a hull in front of the world is drawn correctly (the
  Chromium test).
- **Limits and honest notes.** Large forms only: no windows, no lit bays, no markings. The
  hangar slots are black voids. Bevels are scale insets (a notched section's notch narrows with
  them). A rock's facets are 40 to 130 m. Ring parts and vanes give the star's glare no shadow
  balls. `profile` skips slices where only sparse parts are (a spine's truss). The plumes are
  the kit's, summed per bell (a large bank filling the frame is slow, above). Nothing here is
  physics: masses, tank sizes and radiator areas are looks.
- **Parts** (`data/web/parts/space-hull.js`; kinds `craft` and `craft-part`, no new kind):
  `hull-spine`, `hull-carrier`, `hull-cluster`, `hull-lance`, `hull-wheel`, `hull-ark`,
  `hull-twin`, `hull-burn`, `hull-scale`, `hull-fleet`; `hull-part-shapes`, `hull-part-drive`,
  `hull-surfaces`, `hull-charts` (the atlas drawn on a hull, each chart its own colour).
- **Tests** (`tests/test_web_space_hull.py`): the module and its parts; in Node: the atlas
  without overlap and with the stated scales, banks of bells inside their field, a
  cross-section's area and edge names, a description the same for a seed, forty carrier seeds
  clear of the forbidden layout, did-you-mean, the forbidden outlines on numbers; (`slow`)
  every family for three seeds (length honoured to 0.2 %, no problems, regions and anchors
  inside the bounds, charts non-overlapping with their texels, budgets, determinism, 9 km),
  the constructed wedge with a stern tower and the dagger named, buried bells, a hull on orbit
  data, the rings' turn, a fleet, a size reference; in Chromium (`slow`): a 3 km carrier in
  orbit with a 50 m craft in a `SpaceView` over the Earth: in front of the world, the deck one
  colour without speckle, the small craft where it was put, shadows that only darken, the same
  picture from a second page.

### 123.11 Giant ship detail and sense of size: `vidgen/space-hull-detail` (Step 389)

`data/web/modules/space-hull-detail.js` (import name `vidgen/space-hull-detail`, in
`VIDGEN_MODULES`; imports `three`, `rng` of `vidgen/music-time`, `baked` of `vidgen/baked`,
`GLARE` / `PLUMES` / `flicker` / `craft` of `vidgen/space-craft`, `PALETTES` of
`vidgen/space-hull`). It dresses a hull of §123.10 and answers one question in pictures: why does
this ship read as three kilometres long?

```js
import {hull} from "vidgen/space-hull";
import {dress} from "vidgen/space-hull-detail";
const ship = hull("carrier", {seed: 4, length: 3000});
const detail = dress(ship, renderer, {lights: 1});     // maps baked once, clutter, bays, lamps, plumes
ship.update(t, {sun, throttle});                       // the hull's own update first
detail.update(t, {lights: 0.5 + 0.5 * ctx.music.level(t), light});   // light: the spaceLight (an honest exposure dims the lamps)
```

- **A sibling module (decision).** `space-hull.js` changes only where the detail needs it (below);
  `space-craft.js`, `space-scale.js` and `space-light.js` are byte-identical. Nothing here is a
  mesh per window; no weapons are modelled and no option adds any.
- **What is drawn where, and what is baked.**

  | what | how | kept by `vidgen/baked` |
  |---|---|---|
  | 5 to 20 m: panel seams inside the big plates, hatches, conduits with brackets, vents with their soot, ribs, hand lines; pipe bundles, gratings and machine boxes on dark metal; panel grid, feed pipes on radiators; straps, blankets, a feed line on tanks | a tiling map per kind of surface (`KINDS`: `plating`, `metal`, `radiator`, `tank`), 192 m a repeat, read with `uv` (metres) | `space-hull-detail/tile`, 8 maps of 1024 (512 at `far`), shared by every hull and page |
  | 1 to 5 m: fine panel lines, rivet rows, stencil bars, pits, worn edges, small hatches; grating and bolts; radiator fins; quilting and frost | a second tiling map per kind, 32 m a repeat | the same entry |
  | windows | in the surface shader, from the attribute `win` (metres along the row, metres across the decks, the region's share) and two 256 by 256 tiles of window light (`windowCells`: the night watch, the rest) | not kept (1 ms to make) |
  | grime and soot, large marks, the light of bays, trenches and floodlights, the plumes' light on the stern | one map on the hull's atlas (`uv1`): R grime, G marks, B fixed light, A plume light (`uniqueMap`) | `space-hull-detail/unique`, 2048 a hull (1024 at `far`), keyed by the hull's charts, regions, anchors and description |
  | deck and trench clutter (boxes in clusters, pipe runs, stacks, masts, small dishes) | instances that the hull's own surfaces draw (`clutterPlan`: one piece every 34 m, at most 5000) | — |
  | parked craft and cargo in the bays | instances of the craft kit's `ship` and `tug` at `far` detail, lit by the bay | — |
  | thrust structure (gimbal rings, actuators, shrouds, a frame round the bank) | instances | — |
  | navigation, guide, flood and work lamps | one `THREE.Points` (`navLights`) | — |
  | one long plume a bank of bells | a shell drawn twice (front and back), brightest where the view passes through its middle | — |

  The maps are painted in JavaScript (`detailMap`, `uniqueMap`: pure, tested in Node) and copied
  byte for byte into the render targets `vidgen/baked` keeps: a cached page never paints them.
- **Fading by footprint.** Every scale fades with the metres one pixel covers (`fade(scale,
  metres)`, the shader's rule; `SCALES`): the small scale between 0.35 and 1.4 m a pixel, the
  middle scale between 2.5 and 9 m; the maps' mipmaps do the same underneath, so with
  `antialias: "none"` nothing shimmers. A map's mean tone is 0.5 (unchanged), so a faded map
  changes nothing. With the detail on, the hull's own big-plate map is drawn at 0.55 of its depth:
  plates of 12 to 60 m with strong joints are what made a hull read as masonry.
- **Windows.** Rows follow the decks: 3.5 m between floors, 3.2 m between windows, a window 1.25
  by 0.95 m. On a flat wall decks are level (`windowCoords`: the hull's y across the decks, the
  wall's horizontal direction along the row); a face that looks up or down has none; on a round
  face (a drum, a ring) rows run round it and its end faces have none, so a ring's decks lie at
  constant radius. Use decides how many (`WINDOWS`, by the region's `detail` of §123.10:
  `windows` 0.82 of the banks, `dock` 0.3, `trench` 0.3, `plating` 0.24, `rock` and `cargo` 0.05;
  `tank`, `radiator`, `engine`, `shield`, `hangar`, `truss` none; never on a radiator, tank,
  truss, glass or void surface). A bank is 9 windows by 3 decks; in a bank some decks are blank.
  The seed decides which windows exist (0.77) and which are lit (`lit` 0.36 of them, clustered by
  rooms; `watch` 0.4 of those never go out); a run of windows shares its colour: warm (0.68),
  cool (0.22), white. A window is filtered over the pixel (a box filter in the shader, the cells
  through mipmaps): larger than a pixel it is a sharp rectangle with dark glass when unlit,
  smaller it is a steady sparkle. `lights` (0..1) brings the other banks on one after another
  (never all at once, never blinking); work lamps follow it.
- **Exposure.** `detail.update(t, {light})` reads the spaceLight's gains. `film` (the default):
  windows and lamps are drawn at a pleasing brightness, dimmed to 0.15 where the sun lights the
  wall (so they come out as a face turns from the sun), and a window under a pixel is lifted 2.6
  times so that the night side sparkles; this is a stated look. `camera` / `auto`: every lamp and
  window is multiplied by the same gain as a world's city lights (2^(ev - 10), at most 1) with no
  dimming and no lift: exposed for sunlight they cannot be seen, which is true.
- **Hangar bays.** The `hull-void` back wall gets ribs, doors and strips of light drawn from its
  place among the decks; every face inside a bay's box (floor, ceiling, walls) is lit through the
  atlas, with pools under the strips, and the light spills on the hull round the mouth; the floor
  carries a threshold line, landing boxes with dashed lead-in lines and the bay's figure; parked
  craft (42 to 58 m and 19 to 32 m) and stacks of 14 m containers stand on it; amber lamps along
  the sill, cool ones under the lintel, white pairs running into the bay on vidgen's clock;
  `curtain` (0.25) is a faint blue glow across the mouth, strongest at its frame and at a grazing
  view: a look, not physics; 0 removes it.
- **Engine banks.** Round every bell a gimbal ring, three actuators, two machine boxes and a
  heat-stained shroud; ties between neighbours and a frame round the bank; soot on the block in
  the atlas. Firing: the craft kit's glow in the throats and its plume per bell, one long plume
  per bank (24 bank radii at full throttle, a third of that idling; a disc of light seen from
  astern), the block and whatever faces the bells lit through the atlas's A channel, all with
  `throttle` (a number, a list, a function of t: `ctx.music` through the hull's `update`).
  `plumes: "bank"` hides the kit's plumes (cheaper), `"bells"` the long one.
- **Marks and lamps.** `markPlan`: the hull's number (two plain numerals, 12 m to 3 % of the
  length high) on the largest wall of each side with a bar under it, pads with a cross and a
  figure and a dashed line on the decks, the bays' floors. Numerals only: no alphabet, no emblem.
  The tiling maps carry bars, never figures (a tile is seen from both sides). `floodPlan`: lamps
  close over the larger walls whose light runs out along the plate. `navLights`: red along the
  port side and green along the starboard (from `hull.profile`), white at bow and stern, two
  strobes, a beacon on every tower and mast. A lamp is a point at least 2.4 pixels wide whose
  light falls with the square of what it lacks, so a lamp too small to see fades instead of
  flickering.
- **A sense of size: which cues work.** Space has no haze, so distance says nothing. What works,
  strongest first: (1) windows in rows — the eye knows a floor is three metres; eighty rows on a
  wall is a city block; (2) a craft of known size against the hull, best flying into a bay
  (`ship.scaleRef`, `detail.fly(craft, "hangar-2", u)`, `bayApproach`); (3) detail at several
  scales at once — the finest thing in the frame sets the scale, so a close view must show 1 m
  detail and a far one must not show 60 m plates as its finest; (4) overlap and depth — a
  trench full of clutter, a bay with a back wall, a wide lens close along a wall so detail
  streams past at several depths; (5) the planet behind with a long lens (it flattens the hull
  on the world and says "in orbit"); (6) lamps: small steady points and pools of light on big
  walls. What does not work: the hull alone on black from far (a model on a table, whatever the
  detail); strong tone steps between big plates (masonry); large lamps and large glows (they
  shrink the ship); a fleet seen from above with nothing small in frame; a wide lens from far.
- **Changes to `vidgen/space-hull`** (its `VERSION` is 2): every hull mesh has the attribute
  `chart` (the chart each corner lies in, -1 for none); `hullFleet` takes `navy` (above); the
  lance, the twin and the ark's terraces have more character (the table in §123.10); the lance
  has a hangar (`hangar-1`). `dress` adds the attributes `win` and `hullAtlas` (the same numbers
  as `uv1`) to the hull's meshes and patches the hull's materials (`customProgramCacheKey`
  `vidgen-hull-detail-<kind>`); it scales the kit's five lamp bodies to 0.3 (metres across on a
  hull, they read as a toy's).
- **Interface.** `dress(hull, renderer, options)` → `HullDetail` (`update(t, {lights, light |
  gains, throttle})`, `fly(craft, hangar, u, options)`, `info` (`{windows, lit, lamps, clutter,
  craft, bake: {ms}}`), `plan`, `maps`, `object`, `dispose()`); `dressFleet(fleet, renderer,
  options)`. Options: `lights` (1), `windows` (false | `{lit, watch, warm, cool, floor, pitch,
  gain, lift}`), `nav`, `hangars` (false | `{craft, cargo, curtain, light}`), `engines` (false |
  `{structure, plume, light}`), `plumes` (`both` | `bank` | `bells`), `clutter` (false | a
  density), `marks`, `atlas` (2048; 1024 at `far`), `maps` (1024; 512 at `far`). A hull at `far`
  detail gets no clutter, parked craft or thrust structure unless asked. Pure, for tests and for
  one's own use: `detailMap`, `windowCells`, `windowCoords`, `windowShare`, `fade`, `uniqueMap`,
  `markPlan`, `floodPlan`, `navLights`, `clutterPlan`, `bayApproach`, `inBay`; constants
  `SCALES`, `KINDS`, `WINDOWS`, `PLUME_MODES`, `VERSION`. Unknown options and names are refused
  with the closest word.
- **Measured** (2 cores, SwiftShader, in a `SpaceView` with a sky, the Earth and a star; a 3.2 km
  carrier, `near`; seconds a frame at 1280x720 / 320x180, bare in brackets). Filling the frame
  from 2.5 km: 1.0 / 0.30 (0.72 / 0.20). Small in the frame: 0.55 / 0.23 (0.48 / 0.11). A close
  view where the hull covers every pixel: 2.0 (1.3); with the maps and windows only 1.6; the
  night side close 1.7. Eight bells firing seen from astern: 1.33 (`plumes: "bank"` 0.86). Five
  dressed hulls at `far`: 0.9. The first frame of a page costs about 3 s more (the surface
  programs). Dressing (page ready, the hull alone): cache off 2.1 s, cold 4.2 s (painting and
  storing), warm 0.9 s; a `far` hull 1.1 s cold, 0.4 s warm; the ark 2.1 s cold, 1.1 s warm.
  Painting in Node: a 1024 tile 55 to 80 ms, a 2048 unique map 0.3 to 1.2 s. On disk: 4 MB for
  the first hull (the eight tiles 1.5 MB, its unique map 2.5 MB), 1 to 3 MB for every further
  hull, 0.2 MB at `far`.
- **Two traps found, not changed** (their modules' bytes are in the keys of existing scenes;
  for the review step): `vidgen/space-scale` draws every object with `frustumCulled = false` as
  sky, behind everything (a lamp or a plume marked so vanishes in front of the hull);
  `vidgen/space-light` does not hide a sun given as a direction behind a world further than 1e6
  scene units (a ship in a `SpaceView` in metres is never in the Earth's shadow; with the sun as
  a body it is). The cookbook's terminator recipe applies `sunVisibility` by hand.
- **Limits and honest notes.** A round face's unique map knows no place in space: grime only, no
  bay light or plume light on drums and rings. The plume's light on the stern ignores what stands
  in between. Clutter does not cast shadows (pieces of 2 to 30 m under a 2048 shadow map over
  3 km). Window rows on a tapered wall follow level decks and are cut by its edge. The rock of
  the ark gets sparse lights and no marks. A round bay does not exist. `lights` moves banks, not
  single rooms. The bank plume is a look (no flow, no shock structure).
- **Parts** (`data/web/parts/space-hull-detail.js`): `hull-dressed`, `hull-windows`, `hull-bay`,
  `hull-torch`, `hull-fleet-dressed` (kind `craft`), `hull-detail-maps` (`craft-part`).
- **Tests** (`tests/test_web_space_hull_detail.py`): the module and its parts; in Node (`slow`):
  rows a floor apart on any wall and none on decks and end faces, shares by use, the lit share
  from the seed, the fades, the maps' mean tone and sameness, did-you-mean; on real hulls: the
  unique map (a bay lit on every face, the stern lit by the plumes and a tower not, the spare
  texel neutral, the same for a seed), marks, lamps and clutter the same for a seed and on the
  hull, red to port, clutter clear of the bays, the way into a bay, no windows on tanks,
  radiators and engines of any family, one livery a fleet, the `chart` attribute; in Chromium
  (`slow`): the night side has the warm light the bare hull lacks, an honest exposure for
  sunlight shows almost none, the lit hull differs from the bare one, a bay is brighter than the
  void, the same picture from a second page and with the cache off, cold and warm (the nine maps
  come from the cache).

### 123.12 Camera moves in the air and beside giant ships: `vidgen/space-camera-air` (Step 390)

`data/web/modules/space-camera-air.js` (import name `vidgen/space-camera-air`, in `VIDGEN_MODULES`;
imports `clamp`, `mix`, `smoothstep`, `smootherstep`, `hash` of `vidgen/music-time`, the rig, the
lenses and the vector helpers of `vidgen/space-camera`, `sceneTime` of `vidgen/space-scene`; no
three.js: everything runs in Node). The first step of the phase whose subject is motion.

```js
import {airCamera} from "vidgen/space-camera-air";
const cam = airCamera({camera, sky, ground, water, clouds: weather, flight: ctx.flight, music: ctx.music, crafts: {Plane: ship}});
cam.apply(t, cam.skim(t, {over: [0, 8], from: [0, 0], heading: 284, speed: 90, clearance: 14, turn: 14}));
const cam2 = airCamera({space, camera, ships: {Ship: hull}});               // beside a hull flown in a SpaceView
cam2.apply(t, cam2.hullPass(t, {ship: "Ship", over: [{bar: 5}, {bar: 13}], side: "port", standoff: 60, speed: 40}));
```

- **A sibling module (decision).** `AirCamera extends SpaceCamera`: every option, move and check
  of §122.11 works on the rig, and the new moves are its methods. `space-camera.js` is
  byte-identical (its bytes are in the keys of Phase AN's `space` scenes and of
  `examples/outbound`); nothing in it had to change: the new module builds its shots from
  `shotAt`, `lens`, `distanceFor` and the vector helpers that module exports, and overrides only
  `_common` (times in bars) and `problems` (its own notes).
- **A move is a function of its time.** As in §122.11: `move(t, options)` returns a shot (`from`,
  `right`, `up`, `forward`, `fov`, `aspect`, `focus`, plus numbers of its own and `notes`),
  `cam.apply(t, shot)` places the camera. Nothing is kept between frames (tested in Node: seven
  times in a shuffled order give the same shots; in Chromium: the same frames from two pages that
  draw them in different orders). A damped follow is an exponentially weighted mean over the
  flight's past (`lagged`), a shake is a sum of sines with phases from a seed (`shake`), a kick is
  a closed-form spring (`pushBack`): no state anywhere.
- **Times.** `over: [start, end]` in seconds of the scene, or `{bar, beat}` of the score
  (`music: ctx.music`; `cam.seconds({bar: 9, beat: 3})`), also for `at` and `light`; or `progress`
  with `seconds`. `ease`: 0 steady, 1 from rest to rest (the speed rises as a smoothstep over
  half the move), or `[in, out]`: `[1, 0]` starts at rest and ends moving, so two moves cut
  together on motion (`easedEnds`, `easedRate`). Passes (`skim`, `hullPass`) are steady by
  default, reveals (`rise`, `intoBay`) eased. `speed` of a pass is its speed between the eased
  ends.
- **The local frame.** In the air the frame is the scene's (§123.7: x east, y up at the anchor,
  z south, metres; the world's middle at `[0, -radius, 0]`). `localFrame({radius, center})` gives
  `upAt(p)` (the local vertical), `heightOf(p)`, `at(x, z, h)` (the point over the scene's (x, z)
  at a height over the sphere) and `compass(p, degrees)` (a level heading at p). Every air move
  takes "up" from `upAt` at the camera, not from +y (tested 2,000 km from the anchor: 18.3 degrees
  between them), and heights from the ground's own lookups: `ground.heightAt` / `ground.above`
  (§123.6), `water.heightAt` (§123.4; for a plan the sum of the waves' amplitudes), or a function
  `(x, z, t) -> metres`. `cam.surface(x, z, t)`, `cam.clearance(p, t)`, `cam.peakNear([x, z],
  reach)`.
- **Never under the ground.** A move plans over the surface (below) and then checks the place it
  got: nearer than its `margin` (a move's own, else the rig's 3 m; a ground stand keeps its eye
  height) the camera is lifted along
  the local vertical and the shot's `notes` say by how much and where; `cam.problems(t, shot)`
  returns the notes with §122.11's findings, `cam.check(move)` walks a whole move.
- **No flips.** `lookFrame(up, heading, pitch, roll)` builds a frame from a level heading and a
  pitch, defined straight down and straight up (the frame's top is then the heading); `skim`,
  `climbThrough` and `rise` use it. Views locked to a plane (`wing`) use the plane's own axes and
  no vertical at all (tested through a tumble). `chase`, `flyPast` and `orbitPeak` aim with
  `shotAt` and stay far from the vertical by their geometry.
- **Air moves.**

  | move | what it does | options (defaults) |
  |---|---|---|
  | `skim` | a low pass on a ground track at a stated clearance, following the ground with look-ahead, banking into its turn | `from` [x, z], `heading`, `speed` (90), `clearance` (25), `lookAhead` (3 s), `turn` (degrees in all), `bank` (0.35 of a coordinated turn's, at most `maxBank` 20), `horizon` (`bank` / `level`), `pitch` (-4), `follow` (0.5 of the path's slope), `margin` (0.4 x clearance) |
  | `climbThrough` / `descendThrough` | from under a deck through its fog out over its top, and back | `deck` (index, name or `{base, top}`), `below` (500), `above` (600), `at`, `heading`, `speed` (70), `pitch` ([10, -5]: up into the deck, then across its top), `adapt` (stops, 0), `settle` (500 m) |
  | `chase` | behind and above a plane, following with a lag, rolling with part of its bank | `flight`, `distance` (60; a pair closes in), `height` (16), `side` (0), `lag` (0.7 s), `bank` (0.5), `place` ([0, -0.2]), `lead`, `climb` (0.5) |
  | `wing` | locked to the plane's own frame | `flight`, `view` (`wingtip`, `tail`, `belly`, `nose`, or `{at, toward}`), `side`, `craft` or `length` / `span` |
  | `flyPast` | a camera standing in the air or on the ground; the plane passes | `flight`, `at` (the pass), `closest` (120), `side`, `rise` (-12), `stand` (`air` / `ground`), `eye` (2), `place` ([0, 0.25]), `lag` (0.06 s) |
  | `orbitPeak` | circling a mountain, a volcano or a tower of cloud | `around` ([x, z], `{near, reach}`, `{tower}`), `radius` (2500), `height` (0.12 x radius over the top), `start` (180), `sweep` (90), `aim`, `place`, `top`, `clearance` (150) |
  | `rise` | a vertical crane from the surface to altitude | `at`, `from` (20), `to` (30000), `heading`, `horizon` (0.3), `lens` (one, or [from, to]), `drift`, `down` |

  Terrain following (`skim`, the circle of `orbitPeak`): the ground under the track is sampled at
  96 stations (72 round a circle); each value becomes the highest within the look-ahead
  (`envelope`), then a smooth mean over the same reach, and the path is a monotone cubic through
  the result (no overshoot), so it rises before a ridge and settles after it. A ridge narrower
  than a station is caught by the last check (the lift and its note). The track itself is on the
  scene's (x, z) plane (`trackPlan`): over hundreds of kilometres its speed over the sphere
  differs by the cosine of the angle from the anchor (0.1 % at 280 km). The bank is a look:
  `bankOf(speed, rate)` is a coordinated turn's bank at 9.81 m/s². `climbThrough`'s `adapt` is a
  look too: the shot's `ev` falls as the camera nears the deck's top and recovers over `settle`
  metres above it; the page hands it to the air (`air(..., {ev: (t) => now.ev})`). The chase's
  camera stands behind the plane along the mean of the flight's direction over the last `lag`
  seconds (ages up to four lags, 13 samples), so it has no start-up transient and swings wide in
  a turn; `ctx.flight` gives a value a frame, so sub-frame times step. `flyPast`'s turn is
  fastest at the pass: speed / closest radians a second (the shot's `pan`; 150 m/s at 100 m is 86
  degrees a second). `rise` multiplies its height by a constant per step of eased progress and
  tilts down by the horizon's dip so the horizon stays where `horizon` puts it.
- **Ship moves.** Places are metres in the hull's own axes (+z the bow, +y up, +x port); the rig
  turns them by the hull's object (`hull.object.quaternion`; with a `SpaceView` into the data's
  frame at the body's place, in a plain scene by the object's place and scale): update the ship
  for t before asking for the move. `ships: {name: hull}` lets a move name its ship.

  | move | what it does | options (defaults) |
  |---|---|---|
  | `hullPass` | a slow pass along the hull, a wide lens, the path made from the hull's regions | `ship`, `side` (`port`, `starboard`, `dorsal`, `ventral`, degrees), `lane` (0), `standoff` (60), `reach` (3 stand-offs), `from` (0.1) / `to` or `speed` (40) and `toward`, `ahead`, `inward` (0.6), `yaw` (8), lens `ultra-wide` |
  | `hullReveal` | `traverse`: the bow slides into the frame from behind the camera and the hull keeps coming; `limb`: from behind a world (`reveal` of §122.11 with the ship as subject) | `ship`, `at`, `side` (`under` / `over`), `lane`, `standoff` (0.03 x length), `speed` (length / 30), `tilt` (22), `escort` (`{after, speed, gap}`); `limb`: `behind`, `rate`, `distance`... |
  | `intoBay` | an approach to a hangar's mouth at an angle, then inside | `ship`, `hangar`, `from` (4 widths), `along` (0.7 x from), `deep` (0.35), `rise` (-0.28), `out`, `clear` (25), lens `wide` |
  | `sternBurn` | behind the bank as it lights; pushed back; a shake on request | `ship`, `light`, `distance` (3 bank radii), `off` ([0.45, 0.22]), `creep` (0.06), `push` (0.5 radius), `settle` (0.45 s), `shake` (`{amount 0.25, seed, rate 7, decay 1.6, hold 0.15}`), `rise` (0.35 s) |
  | `scaleZoom` | powers of ten from a place on the hull to the whole ship to the ship as a speck by its world (`zoom` of §122.11) | `ship`, `window` (an anchor, a region, a place), `close` (60), `fill` (0.7), `world`, `far` ({radii: 4}), `lift` (20), `over` or `rate`, `hold` |

  `passPlan(hull, {side, lane, standoff, reach})`: at 160 stations along the long axis, the
  furthest reach on that side of every region whose box comes within a stand-off of the lane and
  of the station; `envelope` with the look-ahead; the camera flies the stand-off outside it. So a
  pass over the deck swings up over a tower before it meets it and a pass along a wall follows
  its steps. It is as true as the regions' boxes (a box is never smaller than its region, so the
  camera is never nearer than the stand-off: tested on a stand-in hull at 800 places; on all
  seven families of seed 1 the nearest region is 60.0 m away along all four sides). A ring that turns keeps the box it was
  built with. `hullClearance(regions, p)` names the nearest region; a pass faster than a twelfth
  of the hull a second is noted (`TOY_SHARE`: a 3 km ship passed in 12 s is a model). The
  traverse flies a straight line a stand-off clear of the hull's furthest reach in its lane and
  times the moment the first station crosses the frame's edge (`at`); it is steady by design. Its
  `escort` is where a small craft should be (the hull's axes: a craft of `ship.scaleRef` is a
  child of the hull) to enter the frame after the stern. `intoBay` reads the anchor `{p, n, width,
  height, depth}`: inside it keeps within the mouth, outside it notes a place nearer than `clear`
  to another region. `sternBurn` returns `throttle` (0 before `light`, 1 after `rise` seconds):
  hand it to `ship.update(t, {throttle})` so the picture and the push have one clock.
- **A trap of `vidgen/space-scale`, met again and avoided from the page.** With the default
  `near` (0.01 m) a `SpaceView` splits a hull the camera is inside the bounding sphere of into
  several depth slices, and the world behind is drawn over the parts of the hull in the farther
  slice (seen in `intoBay` and `scaleZoom`: the Earth over the bay's floor; a body of the orbit
  data, not only an object added by hand as §123.10 says). `new SpaceView(ctx, {..., near: 4})`
  (the camera is never nearer than that to anything) keeps the hull in one slice: the pictures of
  this step use it. `space-scale.js` is unchanged (its bytes are in existing scenes' keys); the
  fix belongs to the review step.
- **Measured** (2 cores, SwiftShader; seconds a frame at 426x240 in a draft clip / at 1280x720 in
  `vidgen still`, the first frame of a page left out).

  | move | scene | 426x240 | 1280x720 |
  |---|---|---|---|
  | `skim` | air + breeze sea at sunset | 0.18 | 1.2 |
  | `skim` | Mars-like air + desert | 0.25 to 0.39 | 1.5 (a frame that re-centres the maps 3.9) |
  | `climbThrough` | air + sea + two decks | 0.31 | 2.0 |
  | `chase` / `wing` | air + alpine land + a plane with shadows | 0.30 / 0.28 | 1.45 / 1.5 |
  | `wing` (belly) | air + a plane + re-entry glow | 0.23 | 1.3 |
  | `flyPast` | air + sea + a plane | 0.17 | 0.85 |
  | `orbitPeak` | air + volcanic land | 0.32 | 1.6 |
  | `rise` | air + sea + fair clouds | 0.32 | 2.1 |
  | `hullPass` | dressed carrier, sky, Earth, 60 m off the wall | 0.43 | 1.55 |
  | `hullReveal` | the same, under the hull | 0.20 | 0.45 (bow) to 1.1 (hull overhead) |
  | `intoBay` | the same | 0.44 | 1.6 |
  | `sternBurn` | the same, eight bells firing | 0.43 | 2.1 |
  | `scaleZoom` | the same | 0.25 | 0.8 |

  The moves' own arithmetic is 15 to 50 ms a frame of that where a ground is sampled (`skim` over
  land: about 130 heights and the plan, three times a frame in the test page; `orbitPeak` 170 ms with its peak search each frame: give
  `around: [x, z]` once the peak is known), under 1 ms otherwise. A page's first frame: 2 s (sea)
  to 20 s (land at 1280x720). `vidgen motion check` on each of the 14 draft clips (3 to 8 s,
  426x240, 12 fps): no findings, except a `rise` of 60 km in 5 s (one `strobe` warning: cloud and
  wave patterns move half their repeat a frame at 12 fps); the same rise in 8 s is clean. The 12
  part tiles: 21 s.
- **What reads and what does not** (strips in the step's scratch folder; the moves were looked
  at as strips of frames and checked by `vidgen motion check`, not watched as film). Strong:
  `skim` over the sea at sunset, `chase`, `wing` (wingtip), `flyPast`, `rise`, `hullPass`,
  `intoBay`, `sternBurn`. Fair: `orbitPeak` (correct, slow to show change: give it 12 s and 30
  degrees), `climbThrough` (the story reads; the fog is flat grey), the traverse of `hullReveal`
  (the idea works over 30 s; the underside is plain and only stars are under it), `scaleZoom`
  (the ship is under a pixel long before the world is whole), `wing` on a re-entry (the glow
  hides the tiles at full heating). Speeds: a `hullPass` at 40 m/s takes 80 s for the whole
  3.2 km carrier: show a part of it; `rise` to 60 km in 8 s and a climb of 115 m/s are stylised
  (a film's time), stated here.
- **Limits and honest notes.** A ground track is planned on the scene's plane (above). The
  look-ahead is symmetric: the path also stays high behind a ridge. `chase` does not look for
  ground between the camera and the plane. `flyPast` on the ground stands on the surface as
  planned (the waves' highest sum over a sea). `hullReveal` behind a nearer ship is not built
  (mode `limb` takes a round world; a ship is a ball there). `intoBay` knows the mouth, not what
  is parked inside. `sternBurn` does not know where the plume is: `off` keeps it out by default.
  Nothing here knows about clouds between the camera and its subject, and (as §123.5 says)
  everything in a scene is drawn in front of every cloud.
- **Parts** (`data/web/parts/space-camera-air.js`, kind `camera`): `camera-skim`,
  `camera-climb-through`, `camera-chase`, `camera-wing`, `camera-fly-past`, `camera-orbit-peak`,
  `camera-rise`, `camera-hull-pass`, `camera-hull-reveal`, `camera-into-bay`,
  `camera-stern-burn`, `camera-scale-zoom`.
- **For Step 392 (YAML).** Options are plain numbers, words and names: flights and ships by name
  (`flight: "Plane"`, `ship: "Ship"` with the rig's `flight`, `ships`, `crafts`), decks, towers,
  hangars, anchors and regions by name or index, times as seconds or `{bar, beat}`. The lists for
  validation: `AIR_MOVES`, `SHIP_MOVES`, `SIDES`, `WING_VIEWS`. No option needs a function.
- **Tests** (`tests/test_web_space_camera_air.py`): the module and its parts; in Node: eased
  ends, the envelope, the local frame far from the anchor, no flip straight down, bars; every air
  move the same for the same time in any order; a skim over a hill and over a ridge narrower than
  its samples (lifted, noted, never under its margin), its speed, bank and level horizon; up 2,000
  km from the anchor; the deck's heights, fog and `ev`; the chase's lag, roll, frame and lift;
  the plane's views through a tumble; the fly-past's standing camera and its fastest turn at the
  pass; the circle round a peak and over high ground; the crane's heights, lens and horizon; on a
  stand-in hull: the plan, the stand-off at 800 places, the swing round a tower, a turned and
  scaled hull, the bow's entry at its bar, the escort, the bay's mouth, the bank's light, push
  and seeded shake, the zoom's landing points; did-you-mean for options, views, flights, ships,
  hangars. In Chromium (`slow`): a skim and a climb drawn at three times each in two orders give
  the same frames (within 2 of 255), the camera over the swell in each.

### 123.13 Orbit to ground in one shot: `vidgen/space-descent`, `descend` / `ascend` (Step 391)

`data/web/modules/space-descent.js` (import name `vidgen/space-descent`, in `VIDGEN_MODULES`;
imports `three`, `vidgen/space-air`, `-sea`, `-land`, `-clouds`, `-bodies`) and two moves on
`vidgen/space-camera-air`'s rig.

```js
import {world} from "vidgen/space-descent";
import {airCamera} from "vidgen/space-camera-air";
const w = world(renderer, {planet: "earth", at: [8, -150], sun: [38, 250], sea: {state: "breeze"}, clouds: {sky: "fair"}, scene});
scene.add(w.object);
const cam = airCamera({camera, ...w.rig});
function frame(t) {
  const fall = {over: [0, 10], from: 400e3, to: 300, heading: 300, turn: 30};
  const shot = t < 10 ? cam.descend(t, fall) : cam.skim(t, {over: [10, 14], ...cam.descend(10, fall).end, follow: 0});
  cam.apply(t, shot); w.update(t, {camera}); renderer.render(scene, camera);
}
```

**The split taken.** Built whole: a CAMERA's descent from orbit to a low pass, and back up, over
an ocean world with decks and over bare ground (a Mars-like desert), in one frame of reference
with one air. Not built (the list is in the tasklist): the plane version (a camera following a
plane through the end of a `reentry` leg), re-anchoring the local frame along a long flight, the
joined world inside a `SpaceView`, the decks' weather read from the globe's cloud map.

**The audit of the seams** (stills before the work in `/home/claude/work/scratch/ao391/stills/before_*`:
the same view from 400, 200, 100, 60, 30 and 10 km, the globe alone and the local parts alone).

1. *Frames.* The globe's data are J2000 metres in a `SpaceView`; air, sea, decks and ground are
   the scene's local frame (x east, y up, z south; the world's middle at [0, -radius, 0]). Every
   local part already takes "up" and the height from the camera's place on the sphere and draws
   each pixel on the sphere itself, so the local frame holds for a camera anywhere over the place:
   drawn from 400 km before this step, the sea and the ground were right in shape. Decision: ONE
   scene, the local frame; the globe is put into it (radius metres, middle [0, -radius, 0], turned
   by `globeTurn(at)` = `placeFrame`'s east, up, south as rows, so the place `at` is under the
   origin and the ground's map and the globe's agree). No `SpaceView`. A camera is free to come
   down over the anchor, so nothing is re-anchored; a vehicle is not (a re-entry crosses
   thousands of km): `world.problems(camera)` names a camera further than 0.3 radii along the
   ground from the place (`REACH`; the ground's large-scale map ends at 0.48).
2. *Globe and air.* From 400 km the air's limb (`vidgen/space-air`) is a thin bright blue line,
   the body's own (`vidgen/space-bodies`) a softer, dimmer glow with a pink band; the Mars-like
   preset is dusty where the body's own air is clear. Decision: one source. The dome of
   `vidgen/space-air` is drawn at every height and the globe is made with `air: false`; its
   surface is seen through the dome's own air (`airLight` to the distance of the sphere on the
   pixel's ray) and lit as the dome's plain ground is (the sun after the air at that place plus
   the sky's light over the sun's cosine, floor 0.2). No handover of the air exists, so none can
   show. `space-bodies.js` is not changed; no Phase AN picture or key changes. The joined world's
   limb is therefore `space-air`'s, not the Phase AN body's: a cut from a Phase AN shot of the same
   world to a joined one shows the difference (the leftover of Step 381 stands for the review).
3. *Surface.* Bare ground: `vidgen/space-land` draws well from orbit (craters, the limb), with
   more detail than the globe's map, but its large-scale map ends 0.48 radii out and it costs
   more. Sea: empty from high up. The globe: soft from low orbit (a 1024 px map has texels of
   10 km on an Earth; from 100 km a pixel is 100 m). Decision: the globe's picture (drawn into a
   half-float target with the page's camera) is laid over the local picture by a full-screen
   pass at render order -790 (after the decks' -800, before the scene's own things) with the
   weight `globeWeight(height, distance) = S(ln distance; near) x S(ln height; height)`: `distance`
   to the sphere along the pixel's ray, `height` the camera's, S a smoothstep. Resolution does not
   enter (a draft and the film hand over at the same heights). `HANDOVERS.low` (a sea or decks):
   near 60 to 400 km, height 2.5 to 80 km (20 to 80 km and 2.5 to 14 km until Step 393, before the
   decks had a broad weather); `HANDOVERS.high` (bare ground): near 150 to 600 km,
   height 60 to 300 km. Above `near[1]` only the globe and the dome are updated and drawn; under
   `height[0]` the globe is not drawn (`stageOf`, `world.state.stage`: `globe`, `handover`,
   `local`).
4. *Clouds.* The decks seen from 30 km and up show the noise tile as a lattice (before-still
   `before_a_local_earth.png`), from 10 km still in the far half; the globe's cloud layer is soft
   smears. Decision: no deck is shown further than `near[1]` from the camera (the lattice needs
   many tiles in view), the globe's layer is all there is above; between, one dissolves into the
   other (Step 393: the decks' broad weather breaks the lattice, so `near[1]` is 400 km and the
   decks show from about 150 km). Single clouds are NOT in the same places. Decks beyond the globe's horizon stood over the
   limb as a bright line that appeared at once when the local parts came on: where the far globe
   has taken over, rays passing under 1.5 x the highest deck top show the air alone (weighted with
   the height's weight). A world without `clouds` gets a globe without its cloud layer.
5. *Depth and order.* No `SpaceView`, so none of its traps. The globe's picture is a pass without
   depth, drawn before the scene's meshes: a craft is always in front of it, as of the decks. The
   ground writes depth (meshes behind a ridge are hidden); the globe's picture does not.
6. *Light and exposure.* One exposure: the air's (`film` by default: no lift above the air). The
   sun, its colour after the air and the stars' share come from the one air at every height, so
   nothing can jump at a handover. Stars: `stars: spaceSky(...)`, dimmed by the air as before.
7. *Cost* (2 cores, SwiftShader, `standard`, 1280x720, warm): ocean with decks: 0.75 s a frame in
   the globe stage, 3.1 s in the handover (everything is drawn), 1.8 s near the surface;
   Mars-like ground: 1.6 / 1.5 / 1.7 s (the ground is drawn from 600 km down). First frame in
   which the ground appears: 6.5 to 10.8 s more (its maps). Page ready: 10 s cold (the globe's
   1024 px map), 2.5 to 5.6 s warm. A draft (426x240): 0.32 s a frame over the whole descent.

**`world(renderer, options)` → `World`.** Options (plain, YAML-friendly; unknown keys refused with
a did-you-mean): `planet` (a world of `vidgen/space-bodies`, name or options; default the
ground's own, else `"earth"`), `at` ([latitude, longitude]; default the ground preset's), `sun`
([elevation, azimuth] at the place, or a direction), `air` (name or options; default the ground
preset's, else the planet's name), `sea` / `land` / `clouds` (false, true, a name: a sea state, a
ground preset, a sky; or the part's options), `globe` (more planet options: `size`, `clouds`),
`handover` (`"low"`, `"high"` or `{near, height}`; default by what lies under the air), `match`
(the globe's brightness beside the local picture's, 1), `exposure`, `ev`, `quality`, `stars`,
`scene`. Members: `object` (add to the scene), `update(t, {camera, sun})` (after the camera is
placed), `heightOf(what)`, `up(what)` (a camera, an object, a point), `sun`, the parts `sky`,
`water`, `ground`, `weather`, `body`, `rig` (for `airCamera({camera, ...w.rig})`), `light`,
`stage(height)`, `state` (`height`, `stage`, `globe`, `local`, `below`, `far`, `up`),
`problems(camera)`, `honest` (where the picture is not true, as sentences), `overlay`,
`uniforms`, `dispose()`. Pure exports: `globeWeight`, `stageOf`, `handoverOf`,
`surfaceDistance`, `globeTurn`, `sunOf`, `resolveWorld`, `HANDOVERS`, `STAGES`, `REACH`,
`VERSION`. The globe's cube maps are 1024 px for a frame of 300 rows or more, else 512
(`globe: {size}`).

**`cam.descend(t, options)` / `cam.ascend(t, options)`** (`vidgen/space-camera-air`,
`AIR_MOVES`). From `from` metres over the sphere (400 km) to `to` metres over the surface where
the move ends (300): the logarithm of the height runs steadily (equal time for each power of ten),
eased at the top and settled at the bottom (`ease: [0.3, 0.35]`: it ends with no sink). The view
keeps the horizon `horizon` (0.3) of the half frame over the middle: down at the globe with the
limb across the top from orbit, along the level at the end; `look` (degrees under the level)
starts steeper. `turn` degrees in all, ending on `heading`; from `run` (0.45) of the move it
gathers way to `speed` m/s (90); `lens` one or a pair; `at`, `margin`, the rig's timing (`over`
in seconds or bars, `progress` + `seconds`). The shot adds `height`, `aboveGround`, `dip`, `pitch`,
`heading`, `speed`, `sink`, `travelled` and `end` = `{from, heading, speed, clearance, pitch,
lens}`: a `skim` given `...shot.end, follow: 0` starts at the same place, view, lens and speed
(tested to 1e-6 m; a straight skim: one that starts turning rolls at once). `ascend` is the same
path backwards. A function of t only.

**True and not true** (`world.honest`). True: positions, the sphere, the horizon's dip at every
height, the air's depth and colours at true scale heights, the sun's place, stars fading as the
sky brightens, the ground's and the globe's great forms in the same places. Not true: the
camera's speed (400 km in ten seconds: 100 km/s and more at the top; a vehicle's re-entry takes
half an hour over thousands of km); where single clouds are (globe and decks agree in colour and
roughly in cover only); the globe's 10 to 30 km craters and its snow are not the ground's; the
globe is lit as a matt ground (no city lights at night in a joined world); no shadows of decks on
the globe.

**Measured on the draft clip** (ocean with decks, 400 km to 300 m in 10 s, then a 3 s skim;
426x240, 10 fps; `vidgen motion check`: no findings). Mean change between consecutive frames
(display codes): 3.4 to 4.4 from 140 km to 30 km; 5.0 to 5.9 from 27 to 22 km, where the decks
come into view (1.5 x its neighbours: the largest ratio in the handover, 58 km to 2.9 km); rising
evenly to 21 by 4 km (the clouds rushing up); 26 against 13 at 1.4 km and at 1.0 km (into the
cumulus and out of its base: 2.0 and 2.3 x, a true event); 1.2 in the skim, no step at the join.
In the Chromium test the surface's mean colour changes by under 32 codes and the sky's by under 40
between heights a sixth of a power of ten apart from 100 km to 3.2 km.

**Where the seams still show.** (1) From about 150 km to 25 km over an ocean the surface is soft
and nearly featureless: the globe's map has nothing that fine and the decks cannot be shown that
far; the picture does not pop, it goes blank and then clouds grow out of the haze. (2) The cloud
pattern changes character in the handover (broad smears → puffs); it reads as resolving detail,
not as the same clouds. (3) A thin cirrus deck is a white line across the horizon while the
camera is level with it (about 10 km). (4) Passing through a deck at a kilometre a second is one
or two grey frames. (5) Over bare ground the globe's albedo markings fade as the ground comes in
(the ground under the dusty air is plainer). (6) The limb is `space-air`'s (harder and bluer than
the Phase AN body's).

- **Parts** (`data/web/parts/space-descent.js`): `joined-ocean-orbit`, `joined-ocean-handover`,
  `joined-desert` (kind `air`), `camera-descend` (kind `camera`).
- **Tests** (`tests/test_web_space_descent.py`): served by its import name; parts; in Node: the
  weights (in 0..1, monotonic in distance and in height, steps under 0.12 between heights 8 %
  apart, the ends), what is drawn at which height, the distance to the sphere without
  cancellation, the globe's turn, options and did-you-mean, the descent's profile (equal time a
  power of ten, no sink at the end), its end joined to a skim, `ascend` as the reverse; in
  Chromium (`slow`): 16 heights from 400 km to 300 m draw, the stages are as stated, bounded steps
  across the handover, a frame is the same after other frames, with the maps baked cold, from the
  cache and without the cache (within 2 of 255).

### 123.14 Reach from `video.yaml`: surface scenes, giant ships, planes (Step 392)

The parts of Steps 381–391 written in `video.yaml` alone, in the `space` scene type (§122.12), with
no JavaScript and with did-you-mean on every key and name.

**Two kinds of `space` scene, chosen by one key.** Without `world:` a scene is **orbital** (§122.12
as it was: a `SpaceView`, bodies from `orbits:` or standing at `at:`). With `world:` it is a
**surface** scene: the joined world of `vidgen/space-descent` (§123.13), a plain three.js scene in
the place's local frame (metres, x east, y up, z south, the origin on the sphere under `world.at`),
the stars of `vidgen/space-sky` behind the air. A surface scene refuses `orbits`, `scale`, `bodies`,
`phenomena`, `light` and `sun` (each message says where the job is done there: `world.at`,
`world.planet`, `world.exposure`, `world.sun`), and an orbital scene refuses `flights` and the air
moves. One key rather than a second scene type: the page, the clip, the cache, `vidgen still`,
`vidgen space-page`, the lint and the music plan are the `space` scene's already; a key is what an
agent adds to turn a scene into the other kind and the messages carry it between them.

**The surface vocabulary** (`scenes/space_air_params.py`). `world: {planet, at, sun, air, sea, land,
clouds, globe, handover, match, exposure, ev, quality}`: each part a name or the module's options
(`sea: rough`, `land: {preset: alpine, seed: 3, mountains: {...}}`, `clouds: {decks: [...], towers:
4, lightning: {times: [3.5, 'bar 9'], track: kick}}`). `sun`: `[elevation, azimuth]` in degrees at
the place, or `{date, utc}`: the Earth's Sun from `vidgen.orbits.ephemeris` (JPL's approximate
elements), the mean obliquity and Greenwich mean sidereal time, no refraction (Greenwich at midsummer
noon: 62° up, due south; tested). `flights:` is the `flight_data` vocabulary (Step 385: a list, or
`{flights, start, speedup, margin, path_samples}`) with `ground`, `world` and `at` taken from the
world: its land (with the world's planet, place and air when they are stated), else its sea (the
state's wave height added to the margin: `rough` 3.2 m, a wind sea 0.0246 x wind²), else its
sphere. The same parser and cache as a `web` scene's (`web_scene_flights`; the key holds the
settings, the frames, the code), so `vidgen space-page` hands over `flight_data` unchanged. A start
from orbit is refused (a surface scene has no orbit data; a real re-entry ends thousands of km from
its start, §123.13). `craft:` in a surface scene: `plane:`, `kind:` or `parts:`, each flying a
flight (`fly:`), with `effects:` following it (`vidgen/space-effects` with `flight: ctx.flight`).

**What an orbital scene gains.** A craft may be `plane:` (a `Plane` is a `Craft`: `fly(space,
{body})` or standing at `at`), `hull:` (a family, `length`, `age`, `palette`, the family's numbers;
`fleet: N` with a list of families: `hullFleet`), or `parts:` (the kit's own parts as a tree: `{part:
hull, ..., attach: [{at: fore, part: dish}, {around: {count: 2}, part: solar-wing}]}`, written as
`kit.hull(...)`, `attach(...)`, `around(...)`, `kit.craft(root)`). A hull is dressed by default
(`dress: true`; `false` bare, or `vidgen/space-hull-detail`'s options) and may take `scale_ref` (a
small craft of the kit for size, `hull.scaleRef`; `into: {hangar, over}` flies it into a bay along
the detail's approach; `escort: true` puts it where a `hull-reveal` wants it). **The near plane**:
with any hull in the scene the page makes the `SpaceView` with `near: 4` and says so in a comment
(Step 390: the default 0.01 m slices a hull the camera is inside the bounding sphere of and draws the
world over it); scenes without a hull keep their page. The moves beside a ship (`hull-pass`,
`hull-reveal`, `into-bay`, `stern-burn`, `scale-zoom`) switch the rig to `airCamera({space, ...,
ships})`; the ship's attitude at t is set before the camera (`space.update(t, {from: {body},
to})` and the hull's update: a move reads it), and the hull's throttle follows a `stern-burn`
shot's `throttle`. Effects on an orbital craft are `exhaust` only (the rest follow a flight through
air). A warp may run across a cut (`cut: {at, seconds, split}`: `warpCut`), any scene may flash on
cuts (`flash: [{at, amount, rise, fall}]`: `flashCut` through three-finish's `flash`, a function of
t), and a move may be a match cut (`match: THING, cut: true`: `matchDisc` of THING's disc in the
move before, worked out once).

**Moves** are written kebab-case as the parts sheet names them (`climb-through`, `fly-past`,
`hull-pass`); camelCase is accepted. Their options are each move's own `known(...)` list read from
`vidgen/space-camera-air`; names in them (`flight`, `ship`, `deck`, `hangar`, `world`, `behind`,
`craft`) are checked against the scene; lengths may be text with units; `at` of `fly-past` and
`hull-reveal` and `light` of `stern-burn` are times (seconds or bars). A `skim` with `continues:
true` after a `descend` spreads the descent's `end` into its options (the recipe of §123.13).

**Pages** (`scenes/space_air_page.py` for a surface scene; `scenes/space_page.py` gains the hull,
plane, parts, effects, ship moves, flash, warp cut and match). One line per part, options as exact
JSON literals, everything in `S`: `S.world`, `S.craft`, `S.fx`, `S.cam`, `S.moves`. A surface page:
`world(renderer, {..., stars: S.sky, scene})`, each plane `plane(kind, opts).fly(ctx.flight,
{flight})` hazed by the air, effects, `airCamera({camera, ...S.world.rig, flight: ctx.flight,
crafts, music: ctx.music})`, `S.step(t)`: the craft, the camera, `S.world.update(t, {camera})`, the
effects; drawn straight to the canvas unless `finish:` is given (every measurement of Steps 381–391
is straight to the canvas; three-finish over a joined world was never drawn). `checkMoves` samples a
surface scene's moves 6 times a second (an air move may sample the ground: every frame would cost
seconds when the page opens). `world.problems(camera)` becomes page notes. Lightning on a track's
hits uses the new helper module `vidgen/space-scene-air` (`hitTimes`: song time less the scene's
start; also `ramp` for gear and bay over time, `flashes`, `once`): a module of its own so that
`space-scene.js`'s bytes, in the key of every Phase AN `space` scene, did not change.

**Checks** (`scenes/space_checks.py`): beyond every key and name, a move that needs a flight, a deck,
ground or water, land for a peak or cloud towers, a hull; a `fly:` naming no flight; a stand-off or a
scale zoom's `close` under 10 m beside a hull, an orbital move closer to a hull's middle than half
its length (the family's shortest usual length when none is given); `scale_ref.into` without
`dress`; music targets (`lightning` needs clouds and is a `pulse`, `lava` volcanic ground, `boost` and
`pulse` a craft with effects); `flash` needs a finish; times in bars need `music_data`. A flight under
the ground or the sea is Step 385's error, raised when the frames are made, with the scene's name
(`space scene 'x': flight Plane: at 19.92 s ... under the 20 m it must keep`).

**One registry of names** (`web/space_names.py`, `air_names()`, `yaml_names()`): every list is read
from the modules' own source (presets, states, waters, skies with their decks, deck types, land
presets and recipe parts, the world's options, planes and their options, the effects' groups and keys,
hull families with their numbers and usual lengths, palettes, dress options, each move's options,
sides, wing views, the kit's parts from the class's methods); the reader learned one more literal
form (`const A = [...], B = [...]`). Validation reads them; the guide lists them and a test compares
the guide's lists with the registry; the parts sheet names its tiles with the same words
(`plane-glider`, `hull-carrier`, `sea-rough`, `land-alpine`, `clouds-fair`, `camera-hull-pass`), tested.

**Cost** (`scenes/space_costs.py`): one table of seconds a frame at 1280x720 from the measurements
of Steps 381–391 (a sea 1.2, ground 1.4, fair clouds 1.9, a sea under cumulus 3.0, all three 3.5 —
not measured, the sum less the dome —, a descent through the handover 3.1 (3.4 since Step 393), a dressed hull 1.0, the
ship moves 0.8 to 2.1), combined for a scene (the dearest stretch, scaled by quality and motion
blur); `vidgen lint`'s `space_scene` reports a scene from `seconds` (2) with the minutes its frames
take; the space cookbook prints the same rows and a test reads both.

**Music plan.** `--style space-air` (a new style name, so `--style space` keeps its output for every
seed: hashed for the three film scores and seeds 1, 2, 7 before and after): by role, a skim at
sunset, a descent, a plane chased over the alpine range, a pass along a dressed hull and a craft into
a carrier's bay by turns; bar-locked, `fade: false`, deterministic from the score and the seed. MCP:
`music_plan` gained `style` and `seed`; `space_page`'s text names both kinds.

**What changed for existing scenes.** Nothing in their pages: the generated page text of
`examples/outbound`'s five scenes and of Step 376's three demos is byte-identical (a test holds the
hashes). No existing module's bytes changed (`space-scene.js` untouched: the helpers are a new
module); `loaded.py` gains one import name; the new module file changes `code_digest()`, so baked
maps and the ground heights kept for flights are made once more with the same pixels and numbers.

**Not reached from YAML** (the modules have them; `script:` or `vidgen space-page`): the wormhole
passage (`passage()` moves the camera itself in the scene's frame, outside a `SpaceView`'s floating
origin and the moves' join check: it needs a move of its own in vidgen/space-camera), a re-entry
from orbit into a surface scene, a sun that moves through a scene, the camera placed by hand in a
ship's own axes, a fleet of planes (`planeFleet`), a hull in a surface scene, effects other than
`exhaust` on an orbital craft, the terminator by `sunVisibility`, a plane's own shadows, a flight's
re-anchoring along a long path.

**Tests** (`tests/test_space_air_scene.py`): the five examples validate; 24 surface and 16 orbital
mistakes named with the closest word; 28 cross-checks; the sun on a date; bars; the pages stable and
saying what the params say; 17 params each changing the page; Outbound's and the demos' pages
byte-identical; imports and `node --check`; a surface page (a chase, and a descent continued by a
skim) run in Node with the real camera modules and stand-ins for three.js and the drawing modules;
the helper module in Node; the flights' ground and key; a flight under the sea with the scene's name;
`vidgen space-page` for both kinds; the registry against the parts sheet and the guide; the music
plan; MCP; the lint's estimate; the cookbook's cost rows. `slow`: a skim and a hull pass drawn in
Chromium at 160x90.

### 123.15 Review of Steps 379–392 (Step 393)

The coordinator's notes on every step's stills, each step's "still weak" and "not verified" items and
the tasklist's leftovers were read; the default suite and the slow tests of the touched files were
run. Each fix was checked on a before/after pair of stills (HANDOFF Step 393 names them).

**Fixed.**

| fault | cause | fix | module bytes (scene keys) |
|---|---|---|---|
| the sea showed concentric rings and whorls from about 100 m to a few km up | one warp of the whole wave pattern (the bends) and a strong warp folding the gusts' patches (`GUST_SHIFT` 0.13) | each wave's phase wanders by its own share of the three fields (`WOBBLE`, `WOBBLE_SPAN`; drawn last from the seed, so the waves keep their numbers); `GUST_SHIFT` 0.03 (§123.4) | `space-sea.js` |
| the alpine range drew even horizontal stripes over whole slopes | rock bands were one sine of height over every rock-coloured slope | beds of uneven tone from a hash per bed, warped and broken by a 256 m noise, only from the material's steep slope, gone before a bed is four pixels thick; `bands` over 0.5 is layered rock (the canyon: light and dark beds in turn, flatter, on less steep faces) | `space-land.js` |
| cloud decks showed their 256 px tile as a lattice from 30–60 km, so the descent hid them beyond 80 km | the pattern is one repeating tile at four sizes | a broad weather of three octaves of endless gradient noise (40, 15, 5 deck sizes; deck option `fronts`, default 0.8, 0 for giants): varying cover, clear lanes, closed fields; drawn to nothing round the place and the level calibrated without it, so the cover asked for is the one seen there (§123.5) | `space-clouds.js` |
| the ocean descent nearly blank from 150 to 25 km | the decks were hidden beyond `near[1]` = 80 km | `HANDOVERS.low` near 60–400 km, height 2.5–80 km: decks from about 150 km (§123.13); the handover costs 3.4 s a frame | `space-descent.js` |
| a world added with `at` and `size` drawn over nearer things; with the default `near` a world drawn over a hull's farther slices (inside a bay, at a zoom's start); the limb of an orbit-data world's air added two or three times | a world's shell holds its depth off the far plane, and every slice drew every thing; a thing inside its bounding sphere's depth range reached to `near` | a slice draws only what its depth reaches; a thing outside its bounding sphere begins at (distance - radius) x the corner cosines (§122.4) | `space-scale.js` |
| anything with `frustumCulled = false` drawn as sky | the sky rule | sky: `userData.sky = true`, or `frustumCulled = false` with a negative `renderOrder`; `userData.sky = false` keeps one in the world | `space-scale.js` |
| a ship never in a world's shadow with the sun given as a direction | the sun stood 1e6 units away; a SpaceView's worlds are millions of metres off | `SKY_SUN` 1e20 units | `space-light.js` |
| the Milky Way bright beside a sunlit globe in the film look | `filmStars` showed all the stars wherever the zenith is drawn black | over the day side `DAY_STARS` (0.35) of them (a look) | `space-air.js` |
| the glider read close to a familiar vehicle in side view | white over a black belly on a delta, two seeds in three | its seeds choose grey, dark, grey (`scheme: tiles` by name) | `space-plane.js` |
| three slow guide tests failing | a duplicate alias (`planets`), the topic list, unmarked sketches, a chooser row | fixed | guide only |

**What re-draws.** Scenes whose pages import a changed module draw once more (their key holds its
bytes): Phase AN's `space` scenes and `examples/outbound` (space-scale, space-light), surface scenes
(space-air, sea, land, clouds, descent, plane). Every baked map and kept ground-height file is made
once more (their key holds every module's bytes), with the same pixels and numbers. Outbound at
320x180, ten stills compared byte for byte: eight identical; `01_dawn` (3 s, 12 s) and `02_depart`
(2 s) differ at the limb: the air's glow is now drawn once (a thinner, dimmer band, up to 67 codes
there; mean 0.4 to 4 codes over the frame). The gallery's `space` entry, regenerated into another folder, is byte-identical
(not touched); three showcases were added to the web gallery (`sunset_skim`, `orbit_to_sea`,
`carrier_pass`), and a still may fall back to 128 colours before 64 (skies at dusk band less). The automatic `near: 4` beside a hull (§123.14) is no longer needed for
correctness (default `near` draws the bay right, still 08); it is kept for depth precision.

**Drawn for the first time** (320x180 stills, no error): a craft into a bay, `stern-burn`,
`hull-reveal` with an escort, a hull fleet, a kit-built craft and a plane in an orbital scene, a warp
across a cut, a match cut, lightning on a track, lava glowing on the music at dusk, a sun on a date,
`finish:` over a surface scene, the `--style space-air` music-plan draft (three scenes). Four draft
clips through `vidgen motion check` (a storm sea from 20 m, a turn over cumulus at 2,300 m, a needle's
flame and vapour cone on a fly-past, the night side of a dressed carrier): no findings.

**Left** (tasklist "Phase AO leftovers"): the two limbs (space-air's from orbit about twice the
space-bodies body's in a plain scene; not changed: the body's look is Phase AN's pictures); the storm
sea's woven finest waves and sparse foam; the glitter column's parallel sides from altitude; stubby
towers; the canyon as loops; a faint repeat of the decks from about 60 km; the decks do not read the
globe's cloud map (they agree in colour and roughly in cover, not in place); the shadows of a ground
not kept between pages; no ground shadow under a plane; a whole hull on black reads as a model;
`scaleZoom` loses the ship under a pixel; `hullReveal`'s traverse over black; the shock layer's
stepped edge; everything listed as not reachable from YAML in §123.14.

### 123.16 The orchestral Shorts as examples; projects that share a page (`web_root`) (Step 394)

The owner's seven portrait orchestral music videos (published as YouTube Shorts) are
`examples/orchestral-shorts/<film>/`, one project per film. "Polish" was only removing duplicate
code; picture and sound stay as published.

**One scene module.** The films carried `extensions/orch.js` in two versions. The newer one (Choir
of the Void, Eclipse) differs from the older one (the other five) in one line of the `ribbon` mode:
the ribbon's speed and gain read `D.ribbonSpeed ?? 2.6` and `D.ribbonGain ?? 3.6` where the older
had the constants 2.6 and 3.6. No film sets either key, so the newer module draws the older films'
pictures unchanged: 16 stills at 180x320 of the five older films (their ribbon shots included),
own copy against the newer module, identical in every pixel. The newer module is
`examples/orchestral-shorts/shared/orch.js`, the only copy.

**One straight-cut type.** `web_cut` (the `web` scene without its 0.5 s fade-out) was copied into
each film. vidgen has no built-in straight cut for `web` scenes (`space` has `fade: false`;
`vidgen music plan --out` still writes `extensions/web_cut.py` into its draft), so one copy stays,
`shared/web_cut.py`, loaded by each film with `extensions: [../shared]` (allowed before this step:
the list's folders are relative to the project and may leave it, except under `vidgen mcp`'s root).

**`web_root:` (new top-level key).** A `web` scene's page or script had to lie inside the project
folder, because its page is served from that folder: `script: ../shared/orch.js` was refused, and
a page's URL could not reach above the folder. `web_root` names the folder pages are served from:
the project folder (default, unchanged) or a folder (relative to the project) that holds it.
`vidgen.web.entry`: `served_root(project)` (that folder, or a `VidgenError` when it is missing or
does not hold the project), `served_params(project, params)` (the `page:` / `script:`, written from
the project folder as every path in `video.yaml`, made a path from the served folder:
`../shared/orch.js` → `shared/orch.js`; the same object without `web_root`), `served_entry_problems`
(validate: the file must lie inside the served folder) and `served_prefix` (the project's path on
its pages, `first-light/`, put before the project's own font files' URLs). The `web` and `space`
scenes, `vidgen still` and the render fingerprint take the root and the entry from these; the page
server, the clip cache and the `loaded` records are unchanged (they already took a root and a path).
`vidgen.api` exports three of them for scene types built on `Web` (built-ins use only the API):
`web_served_root`, `web_served_params`, `web_served_entry_problems`.

Safety: without the key nothing changes (same root, same entry, same clip keys). With it the page
may load any file under the named folder, which the author chose; it must hold the project, so it
is never a sibling or an unrelated folder; it is a path key (`PATH_KEYS`), so under `vidgen mcp`
it must lie inside the server's root. A page or script outside the served folder is refused at
validate (`script: must be a path inside the web_root folder (…), got …`) and at render.
`web_root` is left out of the config part of the scene fingerprint: what it changes (the entry's
path and the loaded files) is in the scene's `web` part.

**The tools.** `tools/gen.py` (rewrites a film's `video.yaml` from its `shots.yaml` with `vidgen
music plan --json`) is kept, without copying files into the project, and writes each committed
`video.yaml` byte for byte (a test). The committed files differ from the published ones only in
the script path, two header comments and the two keys `extensions:` and `web_root:`. The owner's
`stems.py` and `balance.py` (per-group stems and per-section levels) and `sheet.py` (a contact
sheet) were dropped: `vidgen music check` plays every track on its own and reports its share of the
power, voice range, bass and highs (per track over the piece, not per section and group), and
`vidgen still --sheet` writes a contact sheet.

**Proof.** 20 stills at 180x320 (two or three per film) from the example folders are identical in
every pixel to the published projects' stills; the audio-only render (`vidgen render --audio-only`,
the video's soundtrack with its normalisation) of each of the seven films is byte-identical
(MD5 of the WAV) between the published project and the example. Not rendered: no film, no
draft.


### 123.17 Shadows in the air (Step 403)

Light crossed the air as if nothing cast a shadow: a deck hid the sun but the haze under it shone, and the
decks shaded nothing in a surface scene. Now what casts a shadow darkens the air in its shadow, on by default.

- **The model.** A ray's air light is the sky table's (§123.3); what changes is the share of it made in a
  caster's shadow. A small pass (`sky.drawShadows()`) draws, for every direction of the frame, a picture a
  quarter of its size (`shadows.share` 0.25): along each ray, over the stretch under the casters' top
  (from the camera, or from where the ray comes under it; at most `reach`, 200 km), `steps` (24) steps
  spaced by the square of their number (fine near the camera), with a quarter step's jitter between the
  four pixels of a square, it sums the green light each slab makes once scattered (its phase functions,
  the sun's light at the slab after the air) and more often (the table of §123.3), and of that what lies in
  shadow: `(1 - sun share) x once + (1 - sky share) x more - diffuse x (1 - sun share) x the sun's light
  thrown evenly`. Kept: that over the ray's whole light (the sky table's, green), half way and all the way
  along the stretch (in the square root of the distance). A second pass takes the 1-2-1 mean of each
  pixel's 3 x 3 neighbours (the four jitter phases even), rays into the sky and rays to the ground apart
  (channels xy and zw), so the picture read between pixels never mixes the two at the horizon.
- **Reading it.** `airLight` (so `airThrough`, `haze`, the dome, the sea, the ground, the clouds' picture,
  the contrails) finds its ray's place in that picture (`uAirShadeView`: the camera's projection and turn),
  reads the share up to the point (linear from none at the stretch's start), divides it by the share of the
  ray's light made in front of the point (green), and scales the air's light by one less that, every colour
  alike (the hue kept: a first version took the near air's colour off and left cyan casts). The code is
  compiled in only while the air has shadows and something casts them (`AIR_SHADOWS`, set by
  `sky.shadowsInto(material)` from `onBeforeCompile`, which `haze` and vidgen's modules call): SwiftShader
  runs the body of a branch even when the condition is false for every pixel (0.15 s a frame here), so
  "off" is a define, not a uniform. `airRay` (a global the caller sets) is the ray's direction; `airLight`
  with `airRay` zero (the descent's globe) is unshadowed.
- **Casters** (`sky.addCaster({name, glsl, uniforms, top, diffuse})`: `<name>Sun(w, h)` and `<name>Sky(w,
  h)` give the share of the sun's light and of the sky's that reaches a point `w` metres from the camera at
  `h` metres up; `top`: no shadow over it; `diffuse`: the share of the hidden sunlight it passes on all round).
  - **The decks** (`vidgen/space-clouds`, when the air's `shadows` is on and a deck casts a shadow, as for
    `shade`: density x depth over 1; at most four decks; one clouds an air): a map 256 x 256 (`fast` 128,
    `fine` 384) of what each deck lets through of the sun's light (a channel a deck), 60 km each side of the
    point where the camera's own ray to the sun crosses that deck's middle, a place x along kept at
    sqrt(x / 60 km) (fine near the camera), drawn every update (the wind moves the decks), with mipmaps.
    What a deck lets through (`deckLetThrough`): the sun's slant path through it read at three heights (0.15,
    0.5, 0.85 of the deck, each (y - 0.5) x depth / tan(elevation) along the sun's bearing), how much each
    is under a cloud's rounded top (`cloudTop`), the light passing the deck's density over a third of the
    slant path at each: a low sun's ray crosses kilometres of a deck and meets the tops of more clouds; a
    ray over a dome passes. Under twice 0.02 of the sun's sine the shadows fade out. The air reads a deck's
    channel where the sun's ray from the point crosses the deck's middle; inside the deck the shadow fades
    to none at its top; beyond the map, the map's mean (its last mipmap). Under a deck the sky's light is
    one less 0.7 x what the deck takes (a mean over some kilometres: the map's third mipmap); `diffuse` 0.25
    (`AIR_SHADOW`). The same map gives `clouds.mapShade` ({glsl, uniforms}: `cloudShade(p, height)` and
    `seaShade(p)` read from it), which `vidgen/space-descent`'s world gives the ground and the sea: a
    surface scene's decks now shade them too (`clouds.shade` still reads the pattern itself).
  - **The ground** (`vidgen/space-land`): its shadow maps (§123.6) are now two bytes a cell (`RGFormat`):
    the share of the sun's light on the ground as before (the same values), and how high over the cell the
    ground's shadow reaches (the highest ground on the way to the sun less the sun's ray's rise to it), kept
    as sqrt(over / the ground's whole range) (`shadowKeep`, `shadowReach`; under 2 m steps near the ground,
    16 m at 1 km for a 4 km range). The walk towards the sun no longer stops once the cell is dark (only
    bakes cost more). The air reads the map for a point's distance and is in shadow under that height,
    softened over 30 m and 1.5 cells each side (`AIR_SHADOW`).
- **The planet's own shadow at dusk** is in the model already: the sun's light at each scattering point is
  `exp(-tau)` along the closed form of §123.3, which goes to nothing under the planet's horizon. Opposite a
  sun at -2 degrees the once-scattered light is nothing below 4 degrees, brightest a band higher, red over
  blue 1.17 there against 0.70 in the shadow and 0.59 at 45 degrees; the band rises as the sun sinks (tested
  in Node). No table changed, so the limb from orbit (`vidgen/space-bodies`) is unchanged and still agrees.
  In the film look the band is faint at -2 degrees and barely seen at -4 (stills `ao402/stills/08`, `09`).
- **Options.** `air(renderer, what, {shadows})`: `true` (default), `false` (none: the pixels of before), or
  `{reach, share, steps}` (`SHADOWS`; `steps` a multiple of four; `quality: "fast"` halves them). The world
  of `vidgen/space-descent` takes `shadows` and gives it to its air; a surface scene's `world: {shadows}`.
- **Measured** (1280x720, SwiftShader, two cores, median of 9 frames, same session): a fixed view over the
  sea under a cumulus deck 2.82 → 3.21 s (+0.38 s, 14 %), with `shadows: false` 2.84 s; Step 390's rise
  (frames 115-124) median 2.54 → 2.79 s, mean 4.03 → 4.38 s. The pass about 7 ms a step; the map and the
  reads about 0.2 s together.
- **Where it is true and where not.** True: the shadow volumes of the decks and the ground in the air, along
  the sun's direction, and the shadowed share of light scattered once and more often. Approximate: a deck as
  three readings of a slant path, a cloud's diffuse light one number, the air's light per ray scaled in all
  colours alike (the near air's own colour not separated), the shadow picture soft (a quarter size, a 3 x 3
  mean: broad shafts, no fine edges). Not done: towers cast no shadow into the air (only the decks' map);
  the sea's reflection of the sky knows nothing of the decks; the exposure knows nothing of clouds (a frame
  under a deck is darker). A look: the decks' sky share 0.7, diffuse 0.25. Weak: crepuscular rays hardly
  show in the picture: the model's haze has the gas's scale height (8.9 km), so the lowest kilometres, where
  the shafts are, hold little of a ray's light; in a hazier air (`haze` ten times the Earth preset's) they
  show as darker and lighter air round a low sun, not as sharp beams.
- **Tests** (Node): `test_the_shadows_in_the_air_in_node` (the stretch, the reading, the sum's properties,
  the options' did-you-mean), `test_the_earths_shadow_rises_opposite_the_sun_at_dusk`,
  `test_the_decks_shadow_map_for_the_air`, `test_the_grounds_shadow_in_the_air_is_kept_in_a_byte`; YAML
  `test_shadows_in_the_air_are_on_unless_the_world_says_so`; Chromium (slow):
  `test_the_air_under_a_closed_deck_lies_in_its_shadow_in_chromium` (dimmer under an overcast, the sky alone
  the same to the pixel with or without shadows, a frame a function of its inputs). The descent's test
  allows 40 levels (was 32) between two heights: the decks' shadows on the sea change the ground's mean.

## 124. Footage, not a render (Steps 397–401)

The owner's request (2026-11-23): web scenes that read as real camera footage, by ordinary image
processing (no AI): the camera's own flaws and the person holding it. Every effect is a function
of `t` and the options (no state carried from frame to frame), off by default (no existing
scene's pixels change unless it asks), cheap (measured at 1280x720 on the 09_rise view of Step
390), and has a JavaScript twin of its curves tested without rendering. Steps: 397 the sensor,
398 the lens, 399 the operator, 400 camera looks, 401 a camera by default. Step 401 reverses "off by
default" for `space` scenes only, at the owner's decision (old scenes need not look the same): they get
the `camera` look unless they say `camera_look: none` (§124.5); three-finish's and the operator's own
defaults stay off.

### 124.1 The sensor: `noise`, `range`, `sharpen` in `vidgen/three-finish` (Step 397)

**What.** Three option groups of `Finish` (§120.11), each off unless given; `true` turns one on at
`SENSOR_ON` (`noise` 0.012, `range` 2.5 stops, `sharpen` 0.5), a number sets its main value, an
object turns it on at those unless it says otherwise (`noise: {size: 2}` is on at 0.012), `false`
or `0` keeps it off. `resolveOptions` checks them like the other groups (did-you-mean, ranges).

- **`range` — a limited dynamic range** (in the grade pass, right after tone mapping, per
  channel, before saturation and encoding; define `RANGE`). The white is `rangeWhite(stops)` =
  0.18 × 2^stops (linear, after exposure: 2.5 stops is about where Rec. 709 white sits over mid
  grey); `top` is the tone curve's value of that grey. From `top / 2` up, a value is stretched by
  up to `1 / top` (a smoothstep), so `top` lands at 1 and what is above clips; the clip has a soft
  quadratic shoulder `shoulder` wide either side of 1; shadows crush as v² / (v + `black`) × (1 +
  `black`) (white kept). Below half the white nothing changes (with `black` 0), so mid tones and
  the page's exposure stay put; ACES' long shoulder becomes a camera's short one and sunlit cloud
  tops, glitter and the sun go flat white channel by channel. `rangeCurve(v, top, {shoulder,
  black})` is the same curve in JavaScript.
- **`sharpen` — in-camera sharpening** (in the output pass, after FXAA, before the noise; define
  `SHARPEN`). An unsharp mask on the encoded picture's luma: the centre against 4 samples
  `radius` × height / 720 pixels away, times `amount`, the change clamped to ±`limit` (the halos
  stay faint), added to all three channels. Four samples, not eight: half the cost in software
  GL with the same look at radius 1.
- **`noise` — sensor noise** in place of the grain (in the output pass; define `NOISE`; the grain
  is not drawn while it is on). The encoded value is decoded (sRGB or gamma 2.2, as `encoding`),
  noise is added in linear light and the sum encoded again, as a camera's noise sits under its
  output curve: σ(v) = `scale` × √(v + `read`) × (1 − v²) — shot noise growing as √signal, a
  read-noise floor, none where a channel clips (a saturated photosite has no noise). `noiseSpread`
  gives `scale` so the encoded picture's spread at mid grey is `amount`, and `read` = 0.18 f² /
  (1 − f²) so the noise at black is `floor` (f) of the noise at mid grey; `noiseSigma` is σ. Once
  encoded, the noise is larger in the shadows than in the highlights (sRGB's steep toe) and
  crushed blacks stay noisy (half the noise survives the clamp at 0, lifting black by about a
  level at the default). The luma noise sits on the sensor's pixels (`size` × height / 720 frame
  pixels; at 1 or below one value a frame pixel, two hashes, define `NOISE_PIXEL`; above,
  bilinear from the cells' corners with the spread kept by dividing by the weights' length), the
  colour noise on cells twice as wide (demosaicing smears it), mixed by `color` with the total
  spread kept; channel gains 1.15, 0.85, 1.3 (blue noisiest, green least, as white-balance gains
  make it). Seeded by the frame number (`round(t × fps) % 4096`, as the grain), so two renders
  of a frame agree and every frame has new noise; multiplied by `fade`. Not sharpened (the
  camera sharpens its noise too; drawing that would need the noise at the ring's samples).
- **Off is exact.** With none of them on, the shaders compile from the same text as before (the
  new code sits behind defines; the tone curves moved into `toneCurve`, the same arithmetic) and
  the passes are the same: the 09_rise view under the `space` finish defaults is identical in
  every pixel to Step 396's module at 4 s and 8 s, and the Chromium test draws the same frames
  with the sensor given as off as without it. A page that imports the module has a new module
  hash in its cache key (as with every edit of a module), so its frames are drawn again, the same.
- **`space` scenes.** `finish: {noise, range, sharpen}` (`FinishSpec.noise`, `range_` with the
  alias `range`, `sharpen`: a bool, a number or a mapping; sub-keys checked against the module's
  `DEFAULTS` with did-you-mean, as `bloom`). They reach the page only when given, so a page
  without them is written byte for byte as before.
- **Cost** (2 cores, SwiftShader, 1280x720; `finish.render` drawn 20 times a frame on a cheap
  scene): the `space` finish defaults 0.116 s; `noise` +0.018 s, `range` +0.002 s, `sharpen`
  +0.020 s, `noise` at `size: 2` +0.022 s, all three +0.045 s. The 09_rise frame (sea, clouds,
  air; wall time of a frame, median of 9): 7.42–7.55 s before, 7.61–7.73 s with all three — the
  frame-to-frame spread (±0.6 s) is larger than the chain's cost.
- **Looks** (stills in the step's scratch folder): at the defaults the effect is felt rather
  than noticed (whiter cloud tops, crisper cloud edges, a fine living noise floor in the dark
  sea); a scene exposed so its clouds sit well below the white clips little at 2.5 stops — 2
  stops or more exposure gives the blown cloud tops of orbital footage. Step 400's camera looks
  choose per-look values.

### 124.2 The lens: `distort`, `edges`, `halation` in `vidgen/three-finish` (Step 398)

**What.** Three more option groups of `Finish`, off unless given, with the sensor's rules (§124.1):
`true` turns one on at `LENS_ON` (`distort` amount 1, `edges` `{soft: 1.2, fringe: 0.8}`,
`halation` 0.25), a number sets its main value (`amount`, `soft`, `amount`; `edges: 2` keeps the
fringe of `true`), an object turns it on at those unless it says otherwise, `false` or `0` keeps
it off; `resolveOptions` checks them (did-you-mean, ranges). All three sit in linear light before
tone mapping: the lens's geometry and its fringes act on light, not on the encoded picture.

- **`distort` — barrel distortion from the lens** (in the grade pass, where the fringe was read;
  define `LENS`). The share by which the corner is pulled in is `lensDistortion(mm)` = `amount` ×
  0.022 × (50 / mm − 1), at most 0.3: 4.7 % at 16 mm ("ultra-wide"), 2.4 % at 24, 0.9 % at 35,
  none from 50 mm ("normal" and every longer lens are drawn straight), about what rectilinear
  wide lenses measure. `mm` is the camera's focal length on a 36 x 24 mm frame from its vertical
  field of view, `focalLength(fov)` = 12 / tan(fov / 2), the convention of `vidgen/space-camera`'s
  `LENSES`, read from `camera.fov` (and `zoom`) at every `render(t)` after `update(t)` has set the
  scene: the space cameras' moves set `camera.fov` from their lens at `t`, so a move that widens
  (`rise` with `lens: [normal, ultra-wide]`) bends more as it widens, and nothing is carried from
  frame to frame. `distort.mm` fixes the focal length instead (needed for a camera that is not a
  `PerspectiveCamera`). **The border.** A barrel lens draws the edges' light from farther in; read
  straight, the frame's corners would want light from outside the picture (a black or smeared
  border). The mapping is `distortSource`: radially s = (1 + c r²) / (1 + c), c = d / (1 − d), r the
  distance from the middle over the half diagonal, so the corners read exactly the corners and
  everything else reads inside the picture: the picture is scaled in rather than rendered wider.
  The diagonal field of view is the camera's; the middle is magnified by 1 + c (5 % at 16 mm),
  bilinearly, so the middle is that much softer; rendering wider would keep it sharp but change the
  camera every page sets, and `renderScale` stops at 1.
- **`edges` — softness and colour fringes towards the edges** (same pass). `soft` and `fringe` are
  pixels at 720p at the corner, growing as r^`power` (`edgeShare`): the fringe pushes red out and
  pulls blue in along the radius (lateral colour, as a wide lens has); the softness is a smear
  along the radius (two reads a channel; none under a quarter pixel, so the middle reads once).
  The older `fringe` option (§120.11, a stylised r³ split in frame units) adds to the fringe, read
  at the undistorted point; with `edges` and `distort` off it is drawn exactly as before.
- **`halation` — a warm glow bleeding round bright edges** (two passes at a quarter of the
  frame's size before the grade; define `HALATION`). The luma above `threshold` (linear, after
  exposure and white balance, held to 8 so the sun does not flood the frame), picked over 4 x 4
  pixels a cell, blurred across and down with 9 binomial taps (`radius` pixels at 720p, a
  Gaussian's spread), read in the grade at the distorted point and added as `color` × `amount`
  before the vignette and tone mapping: a red-orange rim round the sun's glitter on the sea and
  lit cloud edges against dark water or sky, as light scattered back through film or a sensor's
  cover glass. The threshold is 0.4, not bloom's 1: the space scenes expose their bright clouds
  around 0.5–1 linear, and a threshold of 1 left the 09_rise view untouched.
- **Off is exact.** With none of them on, the grade compiles from the same text as before (the
  new code sits behind `LENS` / `HALATION`) and no halation pass runs: the 09_rise view under the
  `space` finish defaults is identical in every pixel to Step 397's module at 4 s and 8 s; the
  Chromium test draws the same frames with the lens given as off as without it, and with the
  focal length at 50 mm within one level of no distortion.
- **`space` scenes.** `finish: {distort, edges, halation}` (`FinishSpec`, sub-keys checked against
  the module's `DEFAULTS` with did-you-mean); written to the page only when given, so a page
  without them is byte for byte as before. The page's `camera` is the one the moves set, so
  `distort: true` follows the camera's lens.
- **Cost** (2 cores, SwiftShader, 1280x720; `finish.render` 20 times a frame on a cheap scene):
  the `space` defaults 0.121 s; `distort` +0.013 s, `edges` +0.052 s, `halation` +0.030 s, all three
  +0.063 s. A first `edges` with a 4-tap disc (12 reads a pixel) cost +0.126 s; the radial smear
  and the quarter-pixel cut-off halved it. The 09_rise frame (wall time of a frame, median of 9):
  7.12 and 7.25 s before (two runs), 7.52 s with all three; the frame-to-frame spread (±0.6 s) is
  as large as the chain's cost.
- **Looks** (stills in the step's scratch folder). Measured on the 09_rise view by matching
  column profiles: at 8 s (16 mm) the limb's middle is drawn 5.5 px higher and its ends 1.5–2 px,
  so a line 120 px above the middle bows by about 4 px more than the planet's own curve; at 4 s
  (about 28 mm) about 1.5 px; at `distort: 1.5` 6 px and 2.5 px. The edges' softness hardly shows
  on this view (its clouds are already soft and motion-blurred); halation at the defaults is a
  faint warm cast on the brightest cloud fields at 8 s and nothing on the 4 s glitter (it peaks
  near 0.4 linear here) — a sun in the frame or brighter exposure shows it. Step 400's looks pick
  their own values.

### 124.3 The operator: `operator:` and `operate` in `vidgen/space-camera-air` (Step 399)

**What.** The person holding the camera, as a wrapper over a view (any function of t giving shots,
such as `moveTrack`'s): `operate(view, {hand, exposure, horizon, seed, start, cuts}, meter)` and the
rig's `cam.operator(view, options)` (the same with the rig's own meter) return the view as the
operator frames it. Off unless given: with no group on, `operate` returns `view` itself. Every value
is a function of t and the seed; nothing is carried from frame to frame. Whatever "lags" is a
weighted sum over the past it needs, read again at every frame: `responded(f, t, {delay, rate,
damping, window, n, since})` is a second-order follower (natural frequency `rate` Hz, `damping`
under 1 overshoots) written as the weighted mean of f at n past times, the weights the follower's
impulse response, over a window of 5 / (damping × 2π rate) seconds; `since` holds f there (a
follower settled at that moment). The shot comes back turned (yaw about its up, pitch about its
right, then rolled; the frame re-squared as `sternBurn`'s shake does), its place, field of view and
focus unchanged, with `ev` (the move's own plus the exposure's) and `operator: {yaw, pitch, roll,
horizon, ev}`.

- **`hand: handheld`** (`handheld(t, o)`, degrees): the drift is smooth endless noise
  (`smoothNoise`: 1D gradient noise, knots one apart, gradients from the seed, two octaves at
  `rate` 0.12 Hz and 2.3 times that, `drift` 1.1°); the operator sees it `delay` 0.3 s late and
  corrects it with a second-order response (`correct` 0.5 Hz, `damping` 0.5: a 16 % overshoot); what
  the frame shows is the drift less the correction, so the frame is held on average and every slow
  wander ends in a small late swing back past the mark. A reframe now and then (`reframeAt`): in
  most spans of `reframe` 6 s (seeded: 7 in 10) the frame slips `size` 0.9° (× 0.6–1, a seeded
  direction, pitch half of yaw) over 1.6 s and is put back `delay` late by a quick move (1.1 Hz,
  damping 0.45: a fifth too far, then settled), so it ends where it started. Tremor (two octaves
  about 5 and 9 Hz, 0.03°) and breath (0.05° of pitch at about 0.23 Hz, its phase wandering).
  Roll is 0.4 of the drift and half the tremor. RMS at 50 mm, 120 s: yaw 0.21°, pitch 0.15°, roll
  0.03°. **The lens.** The angles are a hand's, so on the screen they grow with the focal length;
  a heavier long lens is held a little steadier: `handShare(mm)` = (50 / mm)^0.3 within 0.5–1.6, mm
  from the shot's own field of view at that moment (12 / tan(fov / 2), the convention of `LENSES`,
  so a widening `rise` calms as it widens). Yaw RMS 0.30° at 16 mm, 0.21° at 50, 0.12° at 300: 1 %,
  0.8 % and 2.7 % of the frame's height; `mm` fixes it.
- **`hand: mounted`** (`mounted(t, o)`): vibration only, `vibration` 0.12° at about `rate` 9 Hz (two
  octaves) and a slow `sway` 0.06° at 0.6 Hz: RMS about 0.04°, the same angles at every lens (a
  mount's rotation does not know the lens), so about a pixel at 720p on a normal lens.
- **`horizon`** (`horizonRoll(age, o)`): `degrees` 1 of roll to a seeded side at the start of every
  shot (the start, and each of `cuts`: the seed plus 101 × the shot's index, so the side changes from
  shot to shot), held `hold` 2.5 s, then levelled in about `settle` 1.2 s with `damping` 0.6 (a 9 %
  overshoot). The natural frequency is chosen so the first crossing of level comes `settle` after
  the hold.
- **`exposure`** (`autoExposure(t, meter, o, since)`): `meter(x)` is the metered stops at time x.
  The camera takes back `strength` 0.7 of every change of the metered brightness since the shot's
  start (`since`: the start or the last cut: a camera that has been running is settled there; across
  a cut the new camera does not hunt for the old one's light), `delay` 0.2 s late, as a second-order
  response at `speed` 0.45 Hz with damping 1 − 0.8 × `hunt` (`hunt` 0.6: 0.52, a 15 % overshoot;
  0: none; 1: it swings round twice), held within ±`most` 2 stops by a soft limit (most × tanh(x /
  most)); read at `samples` 24 past times. The stops go into the shot's `ev`; the page hands it to
  the air (`air(..., {ev})`, as `adapt` does), so the sky, sea, ground, clouds and every lit thing
  move together. With the exposure off the air's `ev` is the number it was.
- **How the exposure sees the past: an estimate from the camera's path and the scene's state**
  (`meterStops(shot, scene)`, the rig's `meter(shot, t)`), not a metering render. Two ways were
  open: (a) a tiny low-resolution metering render at a few past times, or (b) an estimate from the
  shot and the scene's state at those times. (a) would draw the whole scene again 20–30 times a
  frame (a past time needs the air, sea, clouds and ship updated to it, their uniforms restored
  after, and the sky table redrawn when the height or sun changes: seconds a frame in software GL
  at any size, and state carried in the objects); fewer samples would make the hunt step rather
  than glide. (b) costs a move's arithmetic per sample (under 0.02 ms for `rise` and
  `climbThrough`, about 0.4 ms for `skim`, which samples the sea) and is a pure function. The
  estimate, in shares of a white ground in full sun (`METER`): the frame's share over the horizon
  from the view's pitch, the horizon's dip and the field of view; the sky (0.3) darkening with
  height (× (0.1 + 0.9 e^(−h/H)), H the air's scale height), the sea (0.03) or land (0.12) lit by the
  sun's height (and a quarter of a day's sky); each deck (cover × density / 0.004, at most 1): under
  it its grey base (0.7) over the sky part and the ground shaded, inside fog (1.5 × the light, darker
  by e^(−6 × the share of the deck above the camera) further down: the middle of a thick stratus is
  dark), above it sunlit tops (1.2) in place of the ground, the edges smoothed over 12 % of the
  deck's depth; the sun in or near the frame (0.15, glare fading from half the half-diagonal to 8°
  outside it, dimmed by the decks over the camera), and its glitter on the sea. The values were fitted
  (a grid search) to the mean linear luminance of 18 drawn frames of the 09_rise view and the
  climb through a stratus deck (adapt 0); differences between frames agree within about a stop
  (residuals −0.2 to +1.4 stops: deep in the deck the picture is darker than the meter thinks, the
  meter overstates the break-out over the deck by about a stop and understates the rise above the
  cumulus tops by about 0.7 stop). It is a stated estimate, like the film
  exposure; it knows nothing of a ship or a plane in the frame, and reads the sun's direction once
  (a sun moving through the scene is not followed).
- **The scripted `adapt` (Step 390) stays as it was.** `adapt` on a move through a deck is a look:
  the shot's `ev` falls before the top (as a director would grade it, ahead of the event), a
  function of height. The operator's exposure is a camera's: it answers after the event, so the
  break-out flashes white for a moment and then settles darker with a small overshoot, and it opens
  up in the dark middle of the deck. They add when both are given; give one. `shake` (the
  sum-of-sines tremble of `sternBurn`) is unchanged.
- **`space` scenes.** `operator: {hand, exposure, horizon, seed}` at the scene's top level, over all
  its moves (`OperatorSpec`; sub-keys checked against the module's `OPERATOR` with did-you-mean, read
  by `air_names()["operator"]`), not on each move: one person holds the camera through the scene,
  and a per-move hand would make the frame jump at every join that is not a cut (`moveTrack`
  refuses a turn over a degree there). The page writes `S.view = S.cam.operator(S.view, {...,
  cuts})` (a surface scene: the rig's meter) or `S.view = operate(S.view, {...})` (an orbital
  scene: hand and horizon only; `exposure` there is refused, since the orbital film exposure has
  no stops to move); `cuts` are the moves given `cut: true`. Written only when given: a page without
  it is byte for byte as before (the existing pages' hashes are checked by a test).
- **Off is exact.** The page of the 09_rise view (the scratch page of Step 390 with the space finish
  defaults) draws the same pixels with the Step 398 module and this one at 4 s and 8 s, 1280x720 (0
  pixels differ); pages that import the module get a new module hash in their cache key (frames
  drawn again, the same).
- **Cost** (2 cores, SwiftShader, 1280x720, the 09_rise frame, wall time of `page.frame`, median of
  9): 7.43 s without, 7.26 and 7.45 s with hand, exposure and horizon on (two runs; 7.59 s for the
  baseline at the step's start): nothing measurable against the frame's ±0.6 s spread. In Node the
  operator with all three costs 0.3–0.4 ms a frame on `rise` and `climbThrough`, 12 ms on `skim`.
- **Looks** (stills and plots in the step's scratch folder). The horizon's degree shows at the
  start of a shot as a tilt one notices on a level sea; the hand reads in motion and not in a still;
  the exposure of the rise closes by about 0.75 stop by 6 s as the cumulus tops fill the
  frame (greyer cloud tops than without: true to a camera on auto, not the nicer picture), and in the climb it opens about 1.4 stops in the deck's dark
  middle, lets the break-out flash, then settles a stop down. Step 400's looks pick their own values.

### 124.4 Camera looks: `camera_look:` and `vidgen/camera-looks` (Step 400)

**What.** One word for a matched set of Steps 397–399 and the existing finishing: the sensor, the lens, the
person or mount holding the camera, the bloom, vignette and grade of one kind of camera. Off unless given
(until Step 401: a `space` scene now gets the `camera` look unless it says `none`, §124.5).

- **The table** is `CAMERA_LOOKS` of a new module `vidgen/camera-looks` (plain JavaScript, no imports):
  `window_handheld` (handheld through a spacecraft's window: a calm braced hand, a gentle meter, the
  horizon 0.8° off; noise, 2 stops of range, the glass's veil as a lift of 0.012, a wide bloom, warm
  halation at a low threshold, heavy corners, the lens's own bend), `drone` (gimbal vibration, a smooth
  meter; fine noise, 2.4 stops, crisp, a little saturated, bend and fringes), `broadcast_long_lens` (a
  heavy head's sway, the iris ridden slowly with no hunting; a big sensor's fine noise, 2.8 stops with a
  soft knee, strong detail halos, long-lens fringes, no distortion), `phone` (a light hand, a quick meter
  that hunts, 1.5° of horizon; blotchy colour noise, heavy sharpening, punchy colour, lifted blacks, the
  lens corrected in software to half its bend), `chase_mount` (strong vibration, an automatic exposure, no
  horizon error; the ultra-wide bend with soft fringed corners, contrast). The full values: CONFIG
  (`space`). It is written as JSON inside the module (quoted keys, numbers, strings) so Python reads the
  same table (`camera_looks()` of `vidgen.web.space_names`, exported by `vidgen.api`: `json.loads` of the
  constant's text, comments stripped); `LOOK_MAIN` names the key a number sets per group (the finish's
  are three-finish's own `SCALAR_GROUP`, checked by a test).
- **Why a module of its own** and not inside `vidgen/three-finish`: the looks set the operator's options
  too (not three-finish's), three-finish stays under its size budget, and three-finish's text is unchanged,
  so no page that imports it gets a new module hash (nothing is drawn again).
- **The merge** (`lookMerge` in JavaScript, `look_merge` in Python, the same rules, checked against each
  other in Node): the scene's own options go over the look's key by key, at every depth: a mapping merges
  into the look's mapping; `true` keeps the look's group as it is; a number (not 0) sets the group's main
  value (`noise: 0.006` is the look's noise at amount 0.006; `exposure: 0.5` its strength); a hand style
  named again keeps the look's hand, another style replaces it; anything else (`false`, `0`, text, a list)
  replaces the look's value. **Precedence**: the scene's own `finish:` / `operator:` values, then the
  look's, then the `finish` defaults of a `space` scene (bloom 0.3, grain 0.02, vignette 0.3, antialias
  none) and the modules' own defaults.
- **`space` scenes.** `camera_look:` at the scene's top level, beside `finish:` and `operator:` (it sets
  both, so it belongs to neither). A `mode="before"` validator of `Space.Params` replaces `finish` and
  `operator` with the merged mappings before they are checked, so every sub-key is checked as before
  (did-you-mean) and the page writers need no change; the name is checked against the table with a
  did-you-mean (`-` for `_` accepted). An orbital scene (no `world:`) has no meter: the look's automatic
  exposure is left out there (the scene's own `operator: {exposure}` is still refused, §124.3), so every
  look works on orbital scenes with its hand and horizon. A surface scene with a look is drawn through
  the finish (without `finish:` it is drawn straight to the canvas). `finish: false` with a look is
  refused. The page notes the look in a comment line. Without `camera_look` the page is written byte for
  byte as before.
- **Other scene types.** Only `space` scenes write three-finish's options from YAML; `web` scenes and the
  music-video pages (`vidgen music plan`) call `Finish` in their own code, so they take the look in code:
  `cameraLook(name, {finish, operator}, {metered})` → `{finish, operator}` for `new Finish(...)` and
  `cam.operator(...)` / `operate(...)`. The `3d` scene type does not use three-finish. No YAML key there.
- **Motion blur** is left to the scene in every look: it multiplies a frame's cost by its samples (about
  five times at the default 5), against the step's rule of cheap effects.
- **Tuning** (stills of the 09_rise view at 4 and 8 s, a skim into the sun, a pass beside a hull, a
  sunrise over a limb). The operator's default meter (strength 0.7, ±2 stops) took the rise's cloud tops
  about 0.6 stop greyer by 8 s; the looks' meters take 0.3–0.45 within ±1 stop, and their ranges are 2–2.8
  stops, so at 8 s the rise's sunlit tops clip (0.6–1.5 % of the frame at 250 or more, none without a
  look; the 99.5th percentile of luma 229–244 against 215) while the picture is 0.1–0.3 stop darker on
  average. The sensor noise is 0.006–0.01 (not 397's strong set; the phone's is blotchy at size 2).
  Halation 0.08–0.3 with thresholds 0.35–0.5: visible as a warm glow round the glitter in every look,
  strongest through the window. Into a low sun (the skim) the drone's 2.4 stops blow the glitter path
  flat (14 % of the frame clipped, 3 % without), louder than "felt"; `range: 3` over it keeps a little
  more (10 %).
- **Off is exact.** The 09_rise view with no look drew 0 differing pixels at 4 s and 8 s (1280x720)
  before and after the step; three-finish and space-camera-air are unchanged; the tests check that a page
  without `camera_look` has no look line and none of the look's options.
- **Cost** (2 cores, SwiftShader, 1280x720, the 09_rise frames 121–129, wall time of `page.frame`,
  median): no look 8.56 / 7.74 s, `window_handheld` 7.97 / 7.83 s (two runs each): nothing measurable
  against the ±0.6 s spread (Steps 397–399 measured each part at +0.045, +0.063 and 0 s).

### 124.5 A camera by default: the `camera` look (Step 401)

**What.** The owner's decision (2026-11-23): old scenes need not look the same. Every `space` scene, orbital
and surface, that gives no `camera_look:` gets the look `camera`, a row of `CAMERA_LOOKS` like the others
(so it is documented, listed and tested the same way): the sensor and the lens of a good small camera with
nobody holding it. `camera_look: none` (or `null`) is no look: the page and its pixels are those of before.

- **The values**: `noise: {amount: 0.006}`, `range: {stops: 2.8, shoulder: 0.1}`, `sharpen: 0.3`, `distort: 1`
  (the lens's own bend, from the camera's focal length at each moment, §124.2), `edges: {soft: 1, fringe: 0.6}`,
  `halation: {amount: 0.15, threshold: 0.45}`, `vignette: 0.2`; `operator: {}`. Modelled on `window_handheld`
  without the operator (no hand, no horizon error, no automatic exposure), without the glass (no lift, no wide
  bloom) and gentler. Motion blur stays the scene's (it multiplies a frame's cost).
- **Tuning** on views not tried before (stills in the step's scratch folder): a dark night side from orbit (a
  thin crescent of Earth, stars), a Mars-like desert at noon (sun 70° up, a skim 200 m over the dunes), a ship
  close-up (`into-bay` of a 3.2 km carrier), a calm sea at noon, and the 09_rise view at 4 and 8 s. A first
  draft took `window_handheld`'s 2.3 stops and noise 0.008: on the desert the per-channel stretch of the range
  (§124.1: values over half the white are stretched so the white lands at 1) pushed the bright orange sand
  visibly redder and more saturated, and the noise showed as a mottle in the noon sky at 100 %. 2.8 stops
  (3.2 was tried: hardly less shift) and noise 0.006 keep the shift small and the noise below notice in a
  640x360 still; the rise's sunlit tops still reach near white at 8 s (99.5th percentile of luma 235 against
  215, 0.37 % of pixels at 250+, none without). The space finish's vignette 0.3 darkened the desert's and the
  sea's corners in a way the clean render did not have (a surface scene without a look is not finished at
  all); 0.2 is a lens's falloff without a frame.
- **Rules.** Without `camera_look:` → `camera`, merged with the scene's own `finish:` and `operator:` as any
  look (§124.4: the scene's values win key by key). `finish: false` without `camera_look:` → no look, straight to
  the canvas (the scene asked for no finishing); with a named look it is still refused. The page writes the
  look's comment line and the merged finish options; `camera` writes no operator line (`camera_look()` returns
  no operator when neither the look nor the scene gives one). A surface scene with `camera` is drawn through
  the finish (with the space finish's bloom 0.3 at threshold 1, so the sun and the glitter bloom as on orbital
  pages); with `none` and no `finish:` straight to the canvas as before. `flash:` on a surface scene therefore
  needs `finish:` only with `none`. `cameraLook("none", own)` in JavaScript returns the own options alone.
- **Why only `space` scenes.** three-finish's own defaults (and the operator's) stay off: a `web` scene or a
  music-video page that calls `new Finish(...)` in its own code chose its finishing by hand and is not a space
  scene; changing those defaults would change every such page and every music video's pixels (and the module's
  hash, so every page would be drawn again), outside what the owner decided. A page of one's own takes the look
  in one line (`cameraLook("camera")`).
- **`none` is exact.** The four new views rendered before the step (no `camera_look`) and after it with
  `camera_look: none`: 0 differing pixels at 1280x720. The page text of Outbound's five scenes and the Step 376
  demos with `none` is byte-identical to Step 391's but for the scene's own `"camera_look": null` in `PARAMS`
  (the test strips that entry and compares hashes); without it the only added lines are the look's comment, the
  merged `new Finish(...)` line and `PARAMS`.
- **Cost** (2 cores, SwiftShader, 1280x720, the 09_rise frames 121–129, median of 9, two runs in both orders):
  `none` (the space finish) 7.30 / 7.38 s, `camera` 7.97 / 7.69 s: about +0.3 to +0.7 s, at the edge of the
  ±0.6 s spread (Steps 397–398 measured the sensor and lens at +0.045 and +0.063 s with `finish.render` alone;
  the frame's own spread is larger). A surface scene with no `finish:` also gains the finish's own passes (bloom,
  tone mapping, output) it did not draw before; single stills: desert 5.5 → 6.3 s, sea 2.3 → 2.9–3.2 s (first
  still of a page, not a median). The cost table's air rows (`space_costs.py`) are measured without it.
- **Not verified**: motion (no clip: the noise is new every frame by construction, the distortion follows the
  lens; Steps 397–398's tests cover both); a desert or snow at noon with the sun in frame; long-lens moves.
