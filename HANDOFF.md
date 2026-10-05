# Handoff log

Each implementation step appends a section here. Read all previous sections before starting.

## Step 0 — Design spec
- Added `DESIGN.md` (architecture and contracts), `CLAUDE.md` (conventions), this file, and
  `.gitattributes`.
- Plan of steps:
  1. Foundation: package, CLI skeleton, config models, project loading, theme, errors, tests.
  2. Extension system + scene base: runtime context, registry, extension discovery, hooks,
     `NarratedScene`/`narrate()`, helpers, `vidgen.api`, `list-scenes`/`validate`.
  3. ElevenLabs TTS with caching (`vidgen tts`).
  4. Render pipeline: worker subprocess, padding, concat, preview, `--scene`, variants, timings, SRT.
  5. Built-in scene library.
  6. Migrate kphi3 to `examples/kphi3` (custom scenes as extensions) + regression comparison.
  7. Independent review, docs, fixes.

## Step 1 — Foundation
What was built
- Installable package (`pyproject.toml`, setuptools, src layout, console script `vidgen`,
  `[dev]` extra with pytest, `render` pytest marker). Installed editable into `/home/claude/venv`.
- `vidgen/errors.py` (`VidgenError`), `config.py`, `project.py`, `theme.py`, `cli.py`,
  `__main__.py`, init template in `src/vidgen/templates/minimal/` (package data).
- `.gitignore`: `**/build/`, `**/media/`, `*.mp4`, `*.srt`, `*.wav` (audio/ is not ignored).
- Tests: `tests/conftest.py` (`minimal_config()`, `make_project` fixture), `test_config.py`,
  `test_project.py`, `test_theme.py`, `test_cli.py` — 61 tests, no manim import, < 1 s.

Public interfaces (use these in later steps)
- `vidgen.config`: `VideoConfig(title, output, format, preview, variants, theme, voice, narration,
  extensions, scenes)`, `FormatConfig(width, height, fps)`, `ThemeConfig(background, font, colors,
  palette, sizes)`, `VoiceConfig(provider, voice_id, model_id, output_format, settings, context)`,
  `VoiceSettings(stability, similarity_boost, style, use_speaker_boost)`,
  `NarrationConfig(pad, words_per_second)`, `SceneConfig(id, type, params, beats, duration)` +
  `.silent`, `BeatConfig(id, text)` + `.estimated_duration(wps)` (id always filled after
  validation). `parse_config(data, source) -> VideoConfig` (raises VidgenError with
  `<file>: invalid config` + one `path: message` line per error). `format_validation_error(err,
  source)` — reuse it for scene `Params` validation in Step 2 for consistent messages.
- `vidgen.project`: `Project.load(path=".", variant=None)`; attributes `root`, `config_file`,
  `config`, `variant`; properties `output_name`, `audio_dir`, `build_dir`, `extension_dirs`;
  methods `render_dir(preview)` (`build/<final|preview>[_<variant>]`, per DESIGN §5.2),
  `render_format(preview) -> FormatConfig`, `output_path(preview=False)`, `srt_path(preview=False)`,
  `asset(rel)`, `scene(id)`, `beats()` -> iterator of (SceneConfig, BeatConfig), `beat(id)`,
  `estimated_duration()`. Helpers `deep_merge`, `find_config_file`, `read_config_file`, `CONFIG_NAMES`.
- `vidgen.theme`: `Theme(theme_config=None)`; `background`, `font`, `colors`, `sizes`, `palette`
  (copies), `color(name_or_hex)`, `size(name_or_number)`, `palette_color(i)` (wraps),
  `add_defaults(colors=None, sizes=None)` (registered defaults beat built-ins, lose to config).
  `DEFAULT_COLORS`, `DEFAULT_SIZES`, `DEFAULT_PALETTE`. No manim import (tested).
- `vidgen.cli`: `main(argv=None) -> int`, `build_parser()`. `init` and `validate` work; `list-scenes`
  (step 2), `tts` (step 3), `render` (step 4) raise "not implemented yet (step N)". All their
  arguments from DESIGN §8 are already declared, so later steps only replace `set_defaults(func=...)`.

Decisions / deviations (DESIGN.md §4 updated with a "Refinements (Step 1)" list)
- Silent scenes allowed: no beats + required `duration`; `duration` forbidden on narrated scenes.
- `extra="forbid"` on all structural models incl. `voice.settings` (no `speed` key yet; add a field
  if needed — mind the TTS hash/kphi3 compatibility in Step 3).
- Theme config stores user values only; defaults are merged in `Theme`. Hex validation on colors.
- `asset(rel)` is relative to the project root (not to `assets/`).
- `validate` also validates every variant.

For Step 2
- Seam: `vidgen.cli.check_project(project) -> list[str]` currently returns `[]`. Make it load
  extensions, check every `scene.type` is registered (list known types), validate `params`.
  It is called for the base project and each variant by `cmd_validate`.
- Hook `list-scenes` by replacing `_not_implemented(2)` in `build_parser()`.
- The `init` template uses scene types `title` (params: title, subtitle) and `bullets`
  (params: heading, items); Step 5 must provide these with those param names, or update
  `src/vidgen/templates/minimal/video.yaml` and `test_init_scaffold`. Its commented
  `extensions/example.py.txt` uses `self.text`, `self.narrate`, `SceneParams` per DESIGN §6.

How to test: `/home/claude/venv/bin/python -m pytest -q`; manual: `vidgen init /tmp/x && vidgen validate /tmp/x`.

## Step 2 — Extension system and scene base
What was built
- `runtime.py` (active Project/Theme), `registry.py` (scene types), `hooks.py`, `extensions.py`
  (discovery/import/activation), `scene.py` (`NarratedScene`, `SceneParams`, `BeatTiming`,
  `audio_duration`), `helpers.py` (`T`, `MT`, `column`, `edges`, `dense_pairs`,
  `grouped_pairs`, `counter`, `resolve_color`, `styled`), `api.py`, private `_origin.py`.
- `vidgen/scenes/` package with one built-in, `text_card` (params `text`, `size="title"`,
  `color="text"`), so built-in/override paths are real.
- CLI: `check_project()` (isolated load, unknown types with difflib suggestions, params
  validation with `scenes[i].params.<field>` paths), `list-scenes`; vidgen log warnings are
  printed as `warning: ...` while a command runs. `config.validation_error_lines(err, prefix)`
  (used by `format_validation_error` too).
- `docs/EXTENDING.md` (first version; its examples were run end to end).
- Tests: `test_registry.py`, `test_extensions.py`, `test_api.py`, `test_scene.py` (5 real
  renders at 160x90@5fps); `conftest.py` gained an autouse isolation fixture and `write_files()`.
  The fixture `minimal_config()` now uses `text_card` scenes (validate needs registered types).

Exact API for the Step 4 worker
```python
from manim import tempconfig            # or set manim.config fields directly
from vidgen import extensions, registry
project = Project.load(project_dir, variant=variant)
theme = extensions.activate(project)    # runtime context + reset + built-ins + extensions
spec = project.scene(scene_id)
cls = registry.get(spec.type).cls       # VidgenError with suggestions if unknown
# configure manim: pixel size/fps from project.render_format(preview), background_color =
# theme.background, media_dir under build/, explicit output_file, disable_caching=True (!)
scene = cls(spec, project, theme, audio=not no_audio)   # VidgenError on bad params
scene.render()
timings = scene.timings()   # {"scene", "duration", "beats": [{"id","start","end","text"}]}
```
- `timings["duration"]` equals the frame count / fps of the written movie (verified by tests);
  values carry float noise (e.g. 5.200000000000001) — round when writing JSON if desired.
- Manim's caching must be off: on a cache hit Manim advances time by the unquantized duration.
- Hooks: `hooks.dispatch(event, project, **data) -> HookContext`. Step 3 calls `pre_tts`/`post_tts`,
  Step 4 the render events; document the `data` keys you pass in DESIGN.md §6.2. The TTS command
  must `extensions.activate(project)` (or use `project_session`) before dispatching, otherwise no
  extension hooks are registered.

Isolation / reset API
- Built-ins are permanent per process; extension scene types and hooks are a per-project layer:
  `registry.reset()/snapshot()/restore()/isolated()`, same in `hooks`;
  `runtime.set_context()/clear_context()/use_context()/has_context()`;
  `extensions.activate(project)` (process-wide) and `extensions.project_session(project)`
  (context manager, restores everything, unloads `vidgen_ext_<name>` from `sys.modules`).

Decisions / deviations (DESIGN.md §5.1, §5.2 and new §6.5 updated)
- Injection = constructor `cls(spec, project=None, theme=None, *, audio=True)`; validation is a
  classmethod (`validate_params`/`parse_params`), so `vidgen validate` needs no Manim config.
- Built-in vs extension is decided by the defining module (`vidgen.*` = built-in), which is what
  makes promotion work unchanged.
- Multiple extension dirs share one synthetic package; duplicate module names error.
- Frame-exact waits (`wait_seconds`) so each beat is `d + pad` within half a frame.
- Silent scenes are auto-held in `tear_down()` (subclasses must call `super().tear_down()`).
- `api` also exports `VidgenError` and `resolve_color`; `scene` shadows manim's `scene` module.

Known gaps / for later steps
- Step 5: the init template uses `title`/`bullets`; `tests/test_cli.py::test_init_scaffold_validates`
  is `xfail(strict=True)` and will start failing (XPASS) once those exist — remove the marker.
- Step 5 built-ins go in `src/vidgen/scenes/` and must be added to the import list in
  `scenes/__init__.py`.
- Stale-audio detection (hash mismatch) is not done by `narrate()`; Step 3/4 decide.
- Extension imports write `__pycache__/` into the project's `extensions/` (normal Python
  behaviour); consider adding it to the init template's `.gitignore` if one is added.

How to test: `/home/claude/venv/bin/python -m pytest -q` (126 tests incl. 5 renders, ~2.5 s);
skip renders with `-m "not render"`. Manual: `vidgen list-scenes`, `vidgen validate <project>`.

## Step 3 — ElevenLabs TTS
What was built
- `vidgen/tts/__init__.py` (provider seam: `TTSProvider` protocol, `get_provider`; re-exports the
  cache API), `tts/elevenlabs.py` (`ElevenLabsProvider`, urllib, retries, key handling),
  `tts/cache.py` (hash/mp3 paths, `audio_status`, `orphaned_audio`, `atomic_write`),
  `tts/run.py` (`plan_tts`, `run_tts` — the command).
- CLI: `vidgen tts [PROJECT] [--force] [--dry-run] [--beat ID ...] [--variant NAME]` (runs inside
  `extensions.project_session`, so extension hooks fire); `vidgen validate` prints an audio
  summary line (+ one per variant with its own audio folder) via `cli.audio_summary_lines()`.
- `Project`: new `base_config` attribute (constructor kwarg, defaults to `config`),
  `has_own_audio` property; `audio_dir` now returns `audio/<variant>/` when it is true.
- Docs: DESIGN §3, §6.2 (hook data), §7 "Refinements (Step 3)", §8; new `docs/CONFIG.md`
  (voice, narration, "Narration audio (ElevenLabs)"); EXTENDING.md hook data table.
- Tests: `tests/test_tts.py` (36 tests, urlopen mocked, incl. the real kphi3 hash files —
  skipped if `/home/claude/work/kphi3_paper_video` is missing). Removed the `tts` case from
  `test_cli.py::test_not_implemented_commands`.

For Step 4 (render)
```python
from vidgen import tts
statuses = tts.audio_status(project)        # list[BeatAudioStatus], video order, no key needed
bad = [s for s in statuses if s.state != "ok"]   # state: "ok" | "stale" | "missing"
# warn (do not fail), e.g. "warning: audio stale for s2_b1, missing for s3_b1; run `vidgen tts`"
tts.format_audio_summary(statuses)           # "18 ok, 2 stale, 1 missing"
```
`BeatAudioStatus(scene_id, beat_id, text, state, mp3, hash_file)`. Use the variant-loaded Project
(`Project.load(dir, variant=...)`): its `audio_dir` already points at the right folder and
`NarratedScene.beat_audio` uses it. Render hooks' data keys still need documenting in §6.2.

Decisions
- Cache key exactly as DESIGN §7 refinements; `context` not hashed (toggling it does not regenerate).
- kphi3-format hashes are accepted (only with the default output_format/settings) and **not
  rewritten** — avoids churn in the committed kphi3 example audio; a regeneration writes the new format.
- Variant audio rule: own folder iff effective voice differs or a shared beat id has different
  text; unchanged beats are copied from `audio/` when generating into a variant folder. Variants
  that only add new beat ids share `audio/`; orphan detection considers all configs sharing a folder.
- `--beat` restricts but does not force; the key is only required when something must be synthesised.
- `pre_tts` runs on dry runs (so a filtering hook is reflected in the listing); `post_tts` only after
  a successful real run.
- Retries: 3 (backoff 2/4/8 s, honours `Retry-After`, cap 30 s); sleep injectable (`sleep=` kwarg).
- Any unexpected exception during the request (e.g. http.client rejecting a malformed header) is
  converted to a scrubbed `VidgenError` so the key cannot leak through a traceback.

Known gaps
- No ElevenLabs request-id / character-quota reporting; no concurrency (beats generated serially).
- The provider protocol is minimal; a second provider would also need its own legacy-hash story.
- `vidgen validate` loads every variant again for the audio summary (cheap, but repeated parsing).

How to test: `/home/claude/venv/bin/python -m pytest -q` (161 passed + 1 xfail). Manual without a key:
`vidgen init /tmp/x && vidgen tts /tmp/x --dry-run`.

## Step 4 — Render pipeline
What was built
- `vidgen/render/worker.py` — `python -m vidgen.render.worker <project> <scene_id> --quality
  final|preview [--variant NAME] [--no-audio] [--progress]` (the Step 2 sequence + explicit Manim
  config; exit 0 / 1 `VidgenError` / 2 traceback). Helpers: `scene_video_path`,
  `scene_audio_path`, `scene_timings_path`, `frame_size(w, h)`, `write_json`, `render_scene`.
- `vidgen/render/pipeline.py` — `render_project(project, preview=False, scenes=None,
  no_audio=False, keep_going=False, jobs=1) -> RenderResult(output, srt, timings_file, duration,
  rendered, reused)`; `join_scenes`, `warn_audio`. Activates the project's extensions itself
  (`project_session`), so hooks fire when called directly.
- `vidgen/render/ffmpeg.py` — `find_ffmpeg`, `run_ffmpeg`, `probe -> VideoInfo(width, height, fps,
  duration)`, `pad_audio`, `concat_quote`, `write_concat_list`, `join`.
- `vidgen/subtitles.py` — `Cue`, `split_text`, `beat_cues`, `cues_from_timings`, `format_time`,
  `format_srt`, `write_srt(path, timings)`.
- `NarratedScene.frame_width / frame_height / is_portrait` (read-only); `text_card` uses
  `self.frame_width`.
- CLI `vidgen render ... [--jobs N]` (prints one line per scene, then video/subtitles paths and
  duration); removed the `_not_implemented` helper and its test.
- Docs: DESIGN §2/§3 (build layout), §5.2 "Refinements (Step 4)", §6.2 render hook data, §8;
  EXTENDING.md (frame size / vertical, render hook table); new short README.md quick start.
- Tests: `tests/test_render.py` (17 tests, 9 render: one 3-scene project in
  `my vídeo's dir/proj ç` rendered once per module + small projects), `tests/test_subtitles.py`.

Layout under `build/<final|preview>[_<variant>]/`
`scenes/<id>.mp4` (+ `<id>.wav` if the scene has sound), `timings/<id>.json` (scene timings +
`render: {width, height, fps, audio, vidgen}`), `media/` (Manim), `padded/<id>.wav`,
`padded/video_concat.txt`, `padded/audio_concat.txt`, `timings.json` (whole video, absolute
times). Final `<output>[_<variant>][_preview].mp4/.srt` in the project root.

Decisions / deviations
- **No AAC-segment concat** (unlike kphi3's render.py): measured +21–25 ms of drift per scene
  boundary from AAC priming. Instead Manim's PCM `.wav` per scene is padded to the exact video
  length (cumulative sample rounding), WAVs and videos are concatenated separately (concat
  demuxer; video stream-copied), audio encoded once (AAC 192k, 48 kHz stereo). Beat onsets in
  the output match `timings.json` within 1 ms (smoke test with two real kphi3 MP3s; test
  `test_no_drift_beats_start_where_timings_say`).
- **Frame size**: Manim keeps 14.22 x 8 units when pixel sizes are set from code (portrait
  would be squashed). The worker sets the shorter side to 8 units: 9:16 → 8 x 14.22.
- `post_scene` is dispatched in the parent (after each successful worker), so hooks see the
  parent's state and run once per rendered scene; data is paths/dicts, not the Manim scene.
- `pre_render` hooks may remove scene ids (their existing renders are then reused; missing ones
  fail at the join with a clear error).
- No up-to-date detection: all scenes render unless `--scene`. With `--scene`, others are
  reused if rendered at the current format (and with audio unless `--no-audio`).
- `--keep-going` failures → the video is not joined; non-zero exit listing failed scenes.
- Manim breaks on `'`, `{`, `}` in paths (str.format templates, unescaped concat lists) → its
  media dir goes to a temp folder for such projects. Our own concat lists use paths relative to
  the list file (scene ids are `[A-Za-z0-9_]+`) and quote with `'\''` otherwise.
- Workers get `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`; output is decoded as UTF-8.
- Added `--jobs N` (thread pool of worker processes; live Manim progress only for jobs=1 on a TTY).

For Step 5 (built-in scenes)
- Lay out with `self.frame_width`, `self.frame_height`, `self.is_portrait` (or
  `config.frame_width/height`); never assume 14.22 x 8. Theme sizes are font points, so
  portrait needs wrapping/stacking/scaling of wide content.
- The init template's `title`/`bullets` scene types are still missing, so the README quick start
  only works end to end once Step 5 adds them.
For Step 6 (kphi3)
- Old kphi3 scene code using hard-coded coordinates works unchanged at 16:9 (frame 14.22 x 8).
- Compare with the old video knowing the old pipeline had ~20 ms/scene audio drift; the new
  output is sample-accurate, so small A/V differences vs `kphi3_video.mp4` are expected.

Known gaps
- Reused renders (`--scene`) are not checked against config/extension/audio changes.
- A Manim progress bar is only shown live with `--jobs 1` in a terminal.
- `build/` grows (media, wavs); no `clean` command.

How to test: `/home/claude/venv/bin/python -m pytest -q` (181 passed + 1 xfail, ~14 s; renders
~11 s). Skip renders with `-m "not render"`. Manual: a project with `text_card` scenes, then
`vidgen render --preview` and `vidgen render --scene ID`.

## Step 5 — Built-in scene library
What was built
- Nine new built-in scene types in `src/vidgen/scenes/` (one module each, registered in
  `scenes/__init__.py`): `title`, `bullets`, `bar_chart`, `line_chart`, `image`, `quote`,
  `equation`, `code`, `end_card`; `text_card` now wraps with `fit_text` (timing unchanged, no
  fade-out). Every module's only vidgen import is `from vidgen.api import *` (pinned by
  `test_builtins_use_only_the_public_api`); `end_card` reuses `check_image`/`load_image` from
  `.image` by relative import, like extension modules do.
- `vidgen/layout.py` (exported via `vidgen.api`): `fit_text`, `shrink_to_fit`, `wrap_lines`,
  `normalize_text`, `distribute`, `nice_ticks`, `auto_format`, `format_value`, `check_format`,
  `latex_available`, `require_latex`.
- `examples/minimal/` — config-only, every built-in once, variant `vertical`, tiny generated
  assets (`landscape.png` 10 KB, `moving_average.py`), no audio (word-count timing).
- `init` template: 3-scene demo (`title`, `bullets`, `end_card`); the `xfail` on
  `test_init_scaffold_validates` is gone.
- Docs: docs/CONFIG.md "Built-in scenes" (conventions + params table + YAML per type; every YAML
  example validated), docs/EXTENDING.md new §2 "Building blocks" (example run end to end),
  README (built-ins, example, LaTeX note), DESIGN §2, §4 (`surface` color), §5.2/§5.3, §6.4, §6.5.

Public API added (DESIGN §5.3)
- `NarratedScene`: `validate_params(params, theme=None)` / `parse_params(..., theme=None)`
  (theme in validator context), classmethod `validate_project(params, project) -> list[str]`
  (called by `vidgen validate`; reported as `scenes[i].params.<msg>`), `outro` + `finish()`,
  `timeline()`, `play_steps(d, steps, fraction, cap)`, `reveal(steps, fraction, cap)`,
  `safe_width`/`safe_height` (+ `margin_x`/`margin_y`).
- `ThemeColor` / `ThemeSize` param types (`vidgen.scene.ThemeToken` marker → `list-scenes`
  prints `color`/`size`; unions/literals now print as `a | b`).
- `vidgen.api` also re-exports pydantic `Field`, `field_validator`, `model_validator`.
- New default theme color `surface: #161B24` (panels, code window).

Decisions / deviations
- Reveal model shared by all built-ins: content is a list of steps; `distribute()` maps steps to
  beats (step i → beat i; more steps → contiguous runs differing by ≤1; fewer → later beats
  hold). Animations take `min(cap, fraction × slot)`; a beat never lasts longer than `d + pad`
  (tests assert every built-in scene's duration = Σ(d + pad) + outro, including a 12-item list in
  a 0.25 s beat, which led to merging steps when there are fewer frames than steps).
- Built-ins fade out after the last beat (`outro` 0.5 s, `end_card` 1 s) → scene length = beats
  + outro. `text_card` keeps outro 0 so Step 2–4 timing tests and behaviour are unchanged.
- Charts draw axes/ticks with `Text` (no `Axes` number labels, which need LaTeX). `bar_chart`
  `horizontal` defaults to auto (horizontal in portrait with > 5 bars); value labels share one
  scale fitted to the bar slot. `line_chart` moves series names into a legend when end labels
  would exceed a third of the width (typical in portrait).
- `image` loads files through PIL → RGBA (palette PNGs were resampled without smoothing); Ken
  Burns runs over the whole scene from scene time; in `contain` mode the image box is sized
  for the largest scale so the move never overlaps the caption.
- `equation`: missing LaTeX → `vidgen validate` logs a warning (not an error: the config is
  valid), rendering raises a `VidgenError` naming the scene and MiKTeX; compile errors name the
  formula. **Environment note:** `dvisvgm` was missing in the cloud workspace (latex alone is
  not enough for Manim); I installed it with `apt-get install dvisvgm`. The equation render test
  skips when `dvisvgm` is absent.
- `code` uses Manim 0.21 `Code(code_string=..., formatter_style=..., background="window",
  paragraph_config=...)`; highlights dim other lines and add a band between the window
  background and the text (z-index), the first highlight is applied before the fade-in.
- Bug fix in the Step 4 worker: per-scene `text_dir`/`tex_dir` (parallel workers sharing Manim's
  SVG cache read half-written files; reproduced with `--jobs 5` on two variants at once).

Visual QA done (preview renders of `examples/minimal`, 854x480 and `--variant vertical` 480x854,
frames at the end of each scene's last beat and mid-animation, viewed one by one)
- Fixed along the way: tight line spacing of wrapped text (Paragraph default), quote mark
  cramped/ditto-like (now serif fallback list, more space), equation too small (size 96), code
  listing too small (scales up to 1.5x) and invisible highlight band (z-order), bars growing in
  both dimensions (now one-axis stretch), uneven bullet spacing (rows now spaced by baseline),
  overlapping value labels with 12 bars in portrait, line-chart end labels colliding/shrinking,
  last x label colliding, end-card links squeezed to different sizes, stair-stepped image edges.
- Stress project (scratch, not committed): 3-line title + long subtitle + 3 authors, 10-item
  list in 3 beats, horizontal bars with negatives, 12 bars with `baseline`, 14-point categorical
  line chart with 3 series, contain + Ken Burns, long quote, inline code without line numbers,
  integral, end card with logo + long URL; silent scenes; both orientations — all clean.
- Known cosmetic limits: code with long lines gets small in 9:16 (documented: keep lines short);
  a URL without spaces is shrunk rather than wrapped; the `quote` mark font falls back to the
  system serif (Georgia on Windows, DejaVu Serif on Linux).

Known gaps / for later steps
- Manim emits a Pillow `DeprecationWarning` (`mode` parameter, camera.py) for image renders —
  upstream, harmless; 54 such warnings in the test run.
- `fit_text` estimates line breaks from word ink widths (cached); a final width check re-wraps
  if needed, so text never overflows, but breaks can differ slightly from Pango's.
- Steps merged in very short beats play together (e.g. a `dim_previous` fade and a fade-in on
  the same row); only happens when a beat has fewer frames than steps.

How to test: `/home/claude/venv/bin/python -m pytest -q` (323 passed, ~24 s; 28 tiny renders of
all built-ins at 160x90 and 90x160 @ 5 fps ≈ 10 s). Manual: `vidgen list-scenes`,
`vidgen validate examples/minimal`, `vidgen render examples/minimal --preview [--variant vertical] --jobs 4`.

## Step 6 — kphi3 migration
What was built
- `examples/kphi3/`: the paper video as a vidgen project. `video.yaml` (title, `output:
  kphi3_video`, 1920x1080@30, preview 854x480@15, theme with the original colors: standard
  tokens plus `base`/`k2`/`k3` model colors, `highlight` = gold, `palette` = group colors;
  voice = script.json + the original voice settings; pad 0.35, wps 2.6; 8 scenes with the
  same 27 beat ids and texts, verified programmatically against script.json).
- `examples/kphi3/audio/`: the 27 MP3s + hashes copied byte-for-byte (committed, per
  CLAUDE.md). `vidgen tts --dry-run` → 0 to generate; `vidgen validate` → audio 27 ok.
- `examples/kphi3/extensions/`: `common.py` (dark fill constants, `group_color`, `mini_net`,
  `decoder_layer`, `loss_panel`) and one module per scene, `s1_title.py` … `s8_conclusion.py`,
  registering `kphi_title`, `kphi_sparsity`, `kphi_equivalence`, `kphi_method`, `kphi_setup`,
  `kphi_params`, `kphi_loss`, `kphi_conclusion`. Only `from vidgen.api import *` + relative
  imports. Generic helpers (`T`, `MT`, `column`, `edges`, `dense_pairs`, `grouped_pairs`,
  `counter`, `resolve_color`) come from the API; beats are narrated by index. On-screen
  content moved to `params` for the title card, synapse numbers, the method's result line,
  dataset/hardware facts, parameter rows (nested `ParamRow(SceneParams)` with a `ThemeColor`
  field), losses and takeaways; the schematic scenes keep their diagram labels in code.
- `examples/kphi3/README.md` (re-rendering + original-file mapping), `REGRESSION.md`
  (method, tables), README.md pointer, EXTENDING.md pointer to the example.
- `tests/test_kphi3_example.py`: validate (custom types only, beat ids), committed audio up to
  date + `tts --dry-run` says nothing to do, and 2 tiny worker renders (`title`, `params` at
  160x90@5, `--no-audio`) asserting beat length = MP3 duration and beat spacing = d + pad
  (± half a frame). ~6 s.

API gaps found (and fixes)
1. **No way for a scene type to declare how many beats it narrates.** Every kphi scene narrates
   fixed indices; a missing beat failed only at render time ("beat index out of range"), an
   extra one only produced a warning after rendering. Fix (general): `NarratedScene.beat_count`
   (`None` | int | `(min, max|None)`), classmethods `check_beat_count(n)` / `beat_count_text()`;
   checked by `vidgen validate` (`scenes[i].beats: type 'x' needs exactly 2 beats, got 1`), by
   the constructor (`VidgenError`), and printed by `list-scenes` (`beats: exactly 2 beats`).
   Tests in `test_scene.py` (parametrized semantics, constructor) and `test_builtin_scenes.py`
   (validate + list-scenes). DESIGN §5.3 "Refinements (Step 6)", EXTENDING §2 "Fixed beats".
2. Nothing else was missing. Things that worked as designed: module-level theme access,
   relative imports between extension modules, nested `SceneParams` models with `ThemeColor`
   (theme context reaches nested validators: `scenes[5].params.rows[1].color: unknown theme
   color`), `T`/`MT` with numeric sizes and extra kwargs (`line_spacing`), `counter` with a
   callable anchor, `self.wait()`/`clear_all()` inside narrated beats.
   Friction, not gaps: Manim calls (`set_color`, `Line(color=...)`) need hex, so token colors
   go through `resolve_color("k3")` often; Manim's `t2c` is NOT a drop-in for coloring part of a
   `Text` (Pango re-shapes the runs, see REGRESSION.md), so the title keeps a glyph-slice helper.

Regression summary (details in examples/kphi3/REGRESSION.md)
- Original per-scene lengths came from re-rendering the original `scenes.py` at 320x180@30 in
  a temp copy (sum = 6932 frames = the original MP4 exactly). vidgen final render: 6944 frames
  (231.47 s vs 231.07 s); per scene +2, +1, +1, +1, +1, +2, +2, +2 frames. The original
  `narrate()` was instrumented: it truncates the end-of-beat wait (`int(rest*fps)`, skipped if
  ≤ 0.02 s) where vidgen rounds; the predicted per-scene difference matches exactly (12 beats
  with fractional part ≥ 0.5).
- Frames: 81 pairs (early/mid/end of every beat, aligned for the rounding shift, extracted by
  frame index): 72 bit-identical, 9 at SSIM 1.0000 / PSNR 75–98 dB (encoder noise on still
  holds). Time-based seeking is off by one frame in the original, whose video stream starts at
  0.021 s.
- Audio: narration onsets lag the original's frames by 42–61 ms; vidgen's within 1 ms.
- Final 1080p render: `vidgen render examples/kphi3 --jobs 2` 2 min 40 s; `--preview` 54 s.
  A copy is at /home/claude/work/kphi3_vidgen_render.mp4 (outside the repo).

Decisions / deviations
- vidgen's nearest-frame beat rounding was kept (no kphi-specific narrate); the +0.4 s total
  is documented as the only timing difference.
- Scene ids are descriptive (`title`, `sparsity`, …); beat ids keep the original `sN_bM` so the
  committed audio and hashes are reused.
- The `minimal` example and `kphi3` share the `**/build/`, `*.mp4`, `*.srt` ignores; extension
  `__pycache__/` is ignored by the global rule.

Known gaps / for Step 7
- `beat_count` is not validated itself (a wrong type on the class attribute raises a plain
  exception at validate time); fine for now.
- The kphi scenes use hard-coded 16:9 coordinates (faithful to the original); a vertical
  variant of this example would need layout work (not attempted).
- Reused renders (`--scene`) are still not checked against extension changes: editing an
  extension module while a render is running breaks the workers that start afterwards (seen
  once while porting); re-run the render.

How to test: `/home/claude/venv/bin/python -m pytest -q` (334 passed, ~29 s). Manual:
`vidgen validate examples/kphi3`, `vidgen tts examples/kphi3 --dry-run`,
`vidgen render examples/kphi3 --preview --jobs 2`.
