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
  schema.py               # JSON Schema export (see §12)
  errors.py               # VidgenError, Problem
  config.py               # pydantic v2 models for video.yaml (see §4)
  project.py              # Project: locate/load config, resolve paths, variants
  theme.py                # Theme object (colors, font, sizes, background)
  registry.py             # scene-type registry
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
                          # timing_rules.py, color.py, run.py (lint_project), findings.py, report.py
  helpers.py              # theme-aware text helpers and generic drawing utilities
  layout.py               # fit/wrap text, beat distribution, chart numbers, LaTeX detection
  tts/__init__.py         # provider seam: get_provider(cfg)
  tts/elevenlabs.py       # ElevenLabs provider (stdlib urllib), cache by hash
  render/                 # worker.py (one scene per process), pipeline.py, ffmpeg.py,
                          # fingerprint.py (what a scene's render depends on, §14)
  subtitles.py            # SRT from beat timings
  fileio.py               # atomic writes; replacing files that Windows programs keep open
  scenes/                 # built-in scene library (registered like extensions)
tests/                    # pytest; no network; slow renders marked `render`
examples/
  minimal/                # config-only example using built-ins
  custom_scene/           # built-ins + one extension scene type, helper module, variant, hook
  kphi3/                  # migrated paper video, custom scenes as extensions
docs/
  CONFIG.md               # config reference
  EXTENDING.md            # how to write project extensions
DESIGN.md  CLAUDE.md  HANDOFF.md  README.md
```

## 3. Project folder layout

```
my_video/
  video.yaml              # config (video.json also accepted)
  extensions/             # optional; every *.py and every package here is auto-imported
  assets/                 # images, data files referenced by scenes (paths relative to project)
  audio/                  # generated: <beat_id>.mp3 + <beat_id>.hash  (kept, cheap to reuse)
    <variant>/            #   only for a variant whose voice or beat texts differ (§7)
  build/                  # generated: manim media, per-scene mp4, timings json, concat list
  <output>.mp4            # final video   (<output>_preview.mp4 for previews,
  <output>.srt            #               <output>_<variant>.mp4 for variants)
```

`build/<final|preview>[_<variant>]/` (Step 4) holds: `scenes/<id>.mp4` (the scene as rendered,
with Manim's own audio) and `scenes/<id>.wav` (Manim's uncompressed sound mix, only if the scene
has sound), `timings/<id>.json` (beat timings + the render settings), `media/` (Manim's
intermediate files), `padded/<id>.wav` (each scene's audio padded to its exact video length) with
`padded/video_concat.txt` / `audio_concat.txt`, and `timings.json` (the whole video).
With `--frames` (Step 10, §13) also `frames/<id>/*.png` + `frames/<id>/index.json` and
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
  background: "#0E1116"
  font: Inter
  colors:                                        # open dict; these names are the defaults
    text: "#E8EAED"
    dim: "#6B7280"
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
- `safe_width` / `safe_height` (frame minus `margin_x = 0.6`, `margin_y = 0.5` units).

Refinements (Step 6, found while porting kphi3):
- `beat_count: int | tuple[int, int | None] | None = None` (class attribute): how many beats a
  scene type narrates (`None` any, `2` exactly, `(1, None)` at least one, `(2, 4)` a range).
  Types that narrate fixed beat indices set it. `check_beat_count(n) -> str | None` (e.g.
  `"needs exactly 2 beats, got 3"`) and `beat_count_text()` (`"exactly 2 beats"`) are
  classmethods. `vidgen validate` reports `scenes[i].beats: type 'x' needs ...`; the constructor
  raises `VidgenError("scene 'id': needs ...")`; `vidgen list-scenes` prints `beats: ...`.
  Built-ins leave it `None` (they adapt to any number of beats).

`vidgen.layout` (exported by `vidgen.api`): `fit_text`, `shrink_to_fit`, `wrap_lines`,
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
vidgen validate [PROJECT] [--json]      # load config + extensions, report all errors
vidgen list-scenes [PROJECT] [--json]   # built-ins + extensions (+ which overrides)
vidgen schema [PROJECT] [--scene TYPE | --all] [--json]   # JSON Schema of video.yaml (§12)
vidgen tts [PROJECT] [--force] [--dry-run] [--beat ID ...] [--variant NAME]
vidgen render [PROJECT] [--preview] [--scene ID ...] [--variant NAME] [--no-audio] [--keep-going]
              [--jobs N] [--frames] [--frames-per-beat N] [--json]
vidgen storyboard [PROJECT] [--scene ID ...] [--per-beat N] [--variant NAME] [--preview | --final]
              [--width PX] [--jobs N] [--force] [--json]      # contact sheets (§14)
vidgen lint [PROJECT] [--scene ID ...] [--rule NAME ...] [--variant NAME] [--preview | --final]
              [--fail-on SEVERITY] [--jobs N] [--force] [--json]   # layout checks (§16)
```
PROJECT defaults to the current directory. `--scene` re-renders only those scenes and re-joins
using the existing renders of the others (missing ones are rendered). Exit code non-zero on error.
`render` prints one line per scene, then the output paths and the total duration.

## 9. Testing

- `pytest -q` must pass at every step. No network, no API keys.
- Tests that invoke Manim rendering are marked `@pytest.mark.render` and use tiny resolutions
  (e.g. 160x90 @ 5 fps); they run by default but can be skipped with `-m "not render"`.
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
  SHA-256 over the scene's config entry, the config minus `scenes`/`variants`/`lint` (Step 13; the entry without `lint_ignore`) (with the variant
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
  (`shape|group|image`) `{fill: {color, opacity}|null, stroke: {color, opacity,
  width_px}|null}`. Pixels: output frame, origin top-left, y down, frame `[0,W] x [0,H]`,
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
