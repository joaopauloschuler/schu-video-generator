# vidgen — design spec

A configurable generator for narrated, animated explainer videos (Manim + ElevenLabs + ffmpeg).
It generalises the one-off `kphi3_paper_video` project: the pipeline is shared, each video is a
**project folder** with a config file, and each project can **extend** the tool with its own
scene types, helpers, theme tokens and pipeline hooks.

Status of this document: describes the implemented system (version 0.1, after the Step 7
review). Sections 1–9 give the original contract; the "Refinements (Step N)" lists record how
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
  config.py               # pydantic v2 models for video.yaml (see §4)
  project.py              # Project: locate/load config, resolve paths, variants
  theme.py                # Theme object (colors, font, sizes, background)
  registry.py             # scene-type registry
  extensions.py           # discovery + import of project extensions
  hooks.py                # hook registry + dispatch
  runtime.py              # "current project/theme" context used by helpers and extensions
  scene.py                # NarratedScene base class + narrate()
  helpers.py              # theme-aware text helpers and generic drawing utilities
  layout.py               # fit/wrap text, beat distribution, chart numbers, LaTeX detection
  tts/__init__.py         # provider seam: get_provider(cfg)
  tts/elevenlabs.py       # ElevenLabs provider (stdlib urllib), cache by hash
  render/                 # worker.py (one scene per process), pipeline.py, ffmpeg.py
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
vidgen validate [PROJECT]               # load config + extensions, report all errors
vidgen list-scenes [PROJECT]            # built-ins + extensions (+ which overrides)
vidgen tts [PROJECT] [--force] [--dry-run] [--beat ID ...] [--variant NAME]
vidgen render [PROJECT] [--preview] [--scene ID ...] [--variant NAME] [--no-audio] [--keep-going]
              [--jobs N]
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

