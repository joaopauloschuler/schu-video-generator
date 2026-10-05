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

## Step 7 — Independent review
Reviewed all code, tests, docs and examples; ran the suite on **Python 3.10** too (uv-installed
CPython 3.10.20 + `pip install -e .[dev]`, which resolves to Manim 0.19.1 / PyAV 13.1) besides
the 3.13 venv (Manim 0.21 / PyAV 19). `vermin -t=3.10-` reports no 3.11+ syntax or stdlib.

Findings (severity — status)
1. **High — fixed.** Beat timing depended on the PyAV version: `audio_duration` used the
   container duration, which PyAV 13 (every Python 3.10 install, since Manim 0.19 pins `av<14`)
   reports including MP3 encoder padding: +25–50 ms per beat (kphi3: up to +49 ms per beat,
   ~1.3 s over the video) and the SRT test failed on 3.10. Now decoded samples / rate:
   identical on both stacks, unchanged for kphi3 on PyAV 19. Test in `test_robustness.py`.
2. **High — fixed.** Odd `width`/`height` made the worker segfault (exit -11, no message).
   Config now requires even sizes (`must be an even number of pixels`).
3. **Medium — fixed (Windows).** Re-rendering while the previous MP4 is open in a player:
   `os.replace` raises `PermissionError` → raw traceback and the joined video was deleted. New
   `vidgen/fileio.py` (`replace_file` with ~1.5 s of retries, `write_bytes_atomic`,
   `write_text_atomic`, `remove_file`): clear `VidgenError`, joined video kept as
   `<name>.partial.mp4`. Also used for SRT, timings JSON, TTS MP3/hash, worker cleanup.
4. **Medium — fixed (Windows).** Output to a redirected console with a legacy code page crashed
   on non-cp1252 characters (titles, paths). CLI reconfigures stdout/stderr with
   `errors="backslashreplace"` (subprocess test with `PYTHONIOENCODING=cp1252`).
   `BrokenPipeError` (`| head`, `| more`) now ends quietly.
5. **Medium — fixed.** `video.json` saved with a BOM (Notepad) failed to parse; config files are
   read as `utf-8-sig`.
6. **Medium — fixed.** Packaging: setuptools skips dot files, so the wheel had no
   `templates/minimal/assets/.gitkeep` → `vidgen init` from an installed vidgen created no
   `assets/`. `init` now creates `assets/` and `extensions/` and writes a `.gitignore` (template
   file `gitignore`, renamed). Test that the template has no dot files.
7. **Medium — fixed.** Extension robustness: invalid `beat_count` (e.g. `'two'`) gave a
   traceback in `validate` → validated at registration; an exception in `validate_project`
   gave a traceback → reported per scene, other scenes still checked (also non-list
   returns); `sys.exit()` in an extension ended vidgen silently with its code → import error;
   bare `@scene` silently did nothing (class replaced by the inner function) and bare `@hook`
   gave a cryptic message → both explain the right form; `register_theme_defaults(sizes=...)`
   accepted strings → positive numbers required; hook tracebacks no longer start in
   `hooks.py`. `render` checks beat counts before starting workers.
8. **Low — fixed.** API-key hygiene: render workers (which run user scene code) no longer
   inherit `ELEVENLABS_API_KEY`. No other leaks found (key only in the request header; errors
   scrubbed; not in hook data or files — existing tests cover it).
9. **Low — fixed.** `pyproject` allowed `manim>=0.18`, whose `Code` API differs from what the
   `code` scene uses → `manim>=0.19` (0.19.1 passes the full suite).
10. **Low — fixed.** `list-scenes` printed nested params only as `front: Ring`; nested
    `SceneParams` fields are now listed indented. `init` no longer `\u`-escapes non-ASCII titles.
11. **Docs — fixed.** CONFIG.md lacked every top-level key (title, output, format, preview,
    variants, theme, extensions, scenes/beats/duration) — now complete, with defaults;
    `tests/test_docs.py` checks every pydantic config field and every built-in param is
    documented, scalar/theme defaults match the code, and doc YAML snippets parse.
    EXTENDING.md's hook example printed `ctx.project.output_path()` (wrong for preview/variant
    renders) → `ctx.data["output"]`. README rewritten (Windows install incl. venv, ffmpeg,
    Inter font "install for all users", MiKTeX, `setx`, command reference, layout,
    troubleshooting). DESIGN.md: status line, layout, new §10 "Refinements (Step 7)".

Tried and found working (no change needed): name collisions between extension files, builtin
clash without/with `override=True`, import/syntax errors (file + traceback), circular relative
imports (Python's ImportError with both files), relative import beyond the package, `import
common` (clear ModuleNotFoundError; docs say use relative imports), hook raising in `pre_tts`,
unknown hook event, heavy module-level work (works, but repeated per worker → documented),
variant + extension theme tokens, nested params with `ThemeColor`, wrong beat count, missing
asset, unknown theme token, extension modules named `json.py`/`yaml.py`/`manim.py`/`vidgen.py`
(no shadowing: private package), Unicode and non-identifier file names (`café.py`,
`my-scene.py`), sub-packages, folders without `__init__.py` (skipped), CRLF and BOM in
extension files and YAML, project paths with spaces, `'` and non-ASCII (rendered).

Docs-only walkthrough ("How a bicycle gear works", built only from README/CONFIG/EXTENDING):
5 scenes (title, custom `gear_pair` with nested `Ring` params + `geometry.py` helper, bullets,
bar_chart, end_card), vertical variant, `post_render` hook writing a summary. validate, tts
--dry-run, `render --preview` and `--variant vertical` worked first time; frames checked in
both orientations. Friction recorded and fixed in the docs: no config reference for top-level
keys/variants/theme, wrong path in the hook example, nothing said about what `self.project`
offers, that scenes run in separate processes (print hidden, imports repeated, no shared
state), nested params, `@scene` needing parentheses. Added as `examples/custom_scene/`
(+ `tests/test_custom_scene_example.py`: validate, nested-token error, tiny render in both
orientations with the hook).

Packaging: `pip wheel . --no-deps` → fresh 3.13 venv, `pip install` (deps from PyPI) →
`vidgen --version`, `init` (non-ASCII folder), `validate`, `list-scenes`, `tts --dry-run`,
`render --preview` all work outside the repo.

Regression: `vidgen validate` + `tts --dry-run` on all three examples OK (kphi3: 27 up to
date); `render --preview` minimal 97.93 s (28 s wall, `--jobs 4`), kphi3 231.46 s (56 s wall).

Files: new `src/vidgen/fileio.py`, `src/vidgen/templates/minimal/gitignore` (removed
`assets/.gitkeep`), `examples/custom_scene/`, `tests/test_robustness.py`,
`tests/test_docs.py`, `tests/test_custom_scene_example.py`; changed `cli.py`, `config.py`,
`extensions.py`, `hooks.py`, `project.py`, `registry.py`, `scene.py`, `subtitles.py`,
`theme.py`, `render/{ffmpeg,pipeline,worker}.py`, `tts/cache.py`, `tests/test_tts.py`,
`pyproject.toml`, README.md, docs/CONFIG.md, docs/EXTENDING.md, DESIGN.md.

Remaining known limitations / suggested next steps
- Not run on real Windows (no Windows machine here): the Windows fixes are exercised by
  simulation (monkeypatched `PermissionError`, cp1252 stdout). A first run on Windows should
  check font discovery (Inter installed per-user), MiKTeX's on-the-fly package install
  dialog during an `equation` render, and long paths (> 260 chars inside `build/`).
- No up-to-date detection: `vidgen render` re-renders every scene unless `--scene`; reused
  renders are not checked against config/extension/audio changes. A per-scene fingerprint
  (spec + extension sources + audio hashes + format) would make plain `render` incremental.
- Every worker re-imports all extensions and Manim (~1–2 s per scene); fine for ≤ 20 scenes.
- No `vidgen clean`; `build/` grows (Manim media, WAVs).
- TTS is serial; no ElevenLabs quota/request-id reporting.
- Theme token names registered with `register_theme_defaults` are not checked against the
  id pattern (a name with `-` cannot be overridden from YAML).
- `vidgen validate` aborts on the first variant that fails to *load* (structural error)
  instead of listing it with the others.
- kphi3 scenes are 16:9-only (hard-coded coordinates).

How to test: `/home/claude/venv/bin/python -m pytest -q` (382 passed, ~35 s; same on Python
3.10). Manual: see the commands in each example's `video.yaml` header.

## Step 8 — JSON output for commands
What was built
- `--json` on `vidgen validate`, `vidgen list-scenes` and `vidgen render`. stdout then holds
  exactly one JSON document (indented, ASCII-only so a cp1252 console cannot corrupt it);
  everything the command prints meanwhile (progress, Manim output) is redirected to stderr;
  vidgen log warnings still go to stderr and are also collected into the document. Exit code
  0 iff `ok`, 1 for errors, 2 for usage errors. Errors (usage, `VidgenError`, unexpected
  exceptions) are JSON documents too. Human output without `--json` is unchanged.
- Envelope `{version: 1, vidgen, command, ok, warnings: [{scene, message}], ..., error?: {kind
  (usage|error|internal), message, problems, details}}`. Per command:
  - validate: `project, config_file, title, scenes, beats, estimated_duration, variants: [{name,
    loaded, estimated_duration, problems}], problems: [{location, message, variant}], audio:
    [{variant, dir, ok, stale, missing, orphaned, beats: [{scene, beat, state}]}]` (always this
    shape; summary fields `null` when the config does not load).
  - list-scenes: `project, scene_types: [{name, origin, builtin, overrides_builtin, doc, beats:
    null|{min, max, text}, params: null|[{name, type, required, default, doc, nested: [{model,
    fields}]}]}]`.
  - render: `project, variant, preview, audio, format, outputs: {video, subtitles, timings},
    duration, elapsed, scenes: [{id, type, status (rendered|reused), start, duration,
    render_seconds, beats: [{id, start, end}]}]`; worker warnings carry their scene id; failures
    put `{failed: [{scene, exit_code, output_tail}], rendered}` in `error.details`.
- Reference: docs/CONFIG.md "JSON output (`--json`)"; README command table; DESIGN §2, §8 and
  new §11; EXTENDING.md (field docstrings, problem locations); usage line in
  `examples/minimal/video.yaml`.
- Every built-in param now has a one-line docstring (shown as `doc`).

Files
- New: `src/vidgen/jsonout.py` (document builders, `SCHEMA_VERSION`), `src/vidgen/describe.py`
  (type/params description, moved out of `cli.py` + JSON form), `tests/test_json_output.py`
  (23 tests, 2 of them renders).
- Changed: `cli.py`, `errors.py`, `config.py`, `project.py`, `render/pipeline.py`, `scene.py`,
  all `scenes/*.py` (field docstrings only), `pyproject.toml` (`pydantic>=2.7`), docs above.

Public interfaces added/changed (internal modules; `vidgen.api` unchanged)
- `vidgen.errors.Problem(location, message, variant=None)` with `str()`, `in_variant()`,
  `to_json()`; `VidgenError(message, *, problems=(), details=None)` → `.problems`, `.details`.
- `config.validation_problems(err, prefix)`; `parse_config`/`Project.load` errors carry
  `problems` (variant ones tagged with the variant).
- `cli.project_problems(project) -> list[Problem]` (`check_project` unchanged, returns
  strings), `cli.validate_all(project, keep_going=False)`, `cli.JSON_COMMANDS`,
  `cli.UsageError`; command functions return `int`, or the document `dict` with `--json`.
- `RenderResult.timings`, `.render_seconds`, `.warnings`; render failures have `details`.
- `SceneParams` uses pydantic `use_attribute_docstrings=True`.

Decisions / deviations
- `version` in the documents is the schema version (1), `vidgen` the package version. Keys may
  be added within a version; removals/renames/type changes bump it (documented).
- `validate --json` reports a variant whose config does not load as problems and keeps checking
  the others (closes, for JSON, the Step 7 gap "validate aborts on the first variant that fails
  to load"); the human command still stops there, to keep its output unchanged.
- Tiny human-output change: a `validate_project` message not following the `"<param>: ..."`
  convention now prints as `scenes[i].params: <msg>` instead of `scenes[i].params.<msg>`.
- argparse errors no longer `SystemExit(2)` out of `main()`; `main()` prints the same usage text
  and returns 2 (the console script's exit code is the same).
- The scene type `doc` is the class docstring, else the module docstring (built-in classes
  describe their reveal behaviour; the module line has the one-line summary).

Known gaps / TODOs
- `tts` has no `--json` (not in this step; `vidgen tts --json` is a usage error in JSON).
- Problems from YAML/JSON syntax errors have no location (only the message with the line).
- Worker warnings are recognised by the `warning: ` line prefix in worker output (the format
  the worker's logging uses); prints from scene code are not collected.
- Step 9 (JSON Schema) can reuse `describe.py` and the field docstrings (`description`).

How to test: `/home/claude/venv/bin/python -m pytest -q` (404 passed, 1 skipped; also passes on
Python 3.10 / Manim 0.19). Manual: `vidgen validate examples/minimal --json`,
`vidgen list-scenes --json`, `vidgen render examples/minimal --preview --json 2>/dev/null`.

## Step 9 — JSON Schema export
What was built
- `vidgen schema [PROJECT] [--scene TYPE | --all] [--json]` prints a JSON Schema (draft
  2020-12) generated from the pydantic models for the project's scene types (built-ins + its
  extensions; built-ins only without a PROJECT and no config in the current folder):
  - default: the whole `video.yaml`. `scenes[].type` is an `enum` of the registered types and
    `scenes[].params` is checked per type (`allOf` of `if type == NAME then params: $ref
    #/$defs/scene.NAME`, plus `required: [params]` when the type has required params and
    `beats` min/maxItems from `beat_count`). Also encoded: silent-scene rule, optional/null beat
    ids, even width/height (`multipleOf: 2`), `variants` bodies as partial configs,
    `dict[Identifier, X]` keys (`propertyNames`), and `min_length` of union fields moved to
    each branch as `minItems`/`minProperties` (pydantic emits a `minLength` that validators
    ignore for arrays, e.g. `line_chart.x`).
  - `--scene TYPE`: one type's params schema (unknown type: error with did-you-mean).
  - `--all`: the schema of one `scenes[]` item with every type's params in `$defs`.
  - Theme color/size params (`ThemeColor`/`ThemeSize`) accept hex / positive number or a
    token name of the project's theme (defaults + extension defaults + `theme.*` of the base
    config and every variant); marked `"x-vidgen-theme": "color"|"size"`.
  - Descriptions: field docstrings (every config field now has one; built-in params already
    had them) and the scene type's doc + beat count.
  - Works on an invalid `video.yaml` (that is when an agent needs it): falls back to the
    file's `extensions`/`theme` as far as they are valid, with a warning.
  - Output: indented ASCII JSON on stdout (extension prints go to stderr). `--json` wraps it in
    the Step 8 envelope (`project`, `schema`); errors are JSON documents too.
- Docs: docs/CONFIG.md new section "JSON Schema (`vidgen schema`)" and "`vidgen schema
  --json`"; README command table; EXTENDING.md (what the schema takes from `Params`); DESIGN
  §2, §8 and new §12.

Files
- New: `src/vidgen/schema.py`, `tests/test_schema.py` (51 tests).
- Changed: `cli.py` (`cmd_schema`, `scene_types_session`, `JSON_COMMANDS`), `jsonout.py`
  (`schema_document`), `config.py` (field docstrings, `use_attribute_docstrings`, `multipleOf`
  hint, `Size` JSON schema), `scene.py` (`ThemeToken.__get_pydantic_json_schema__`),
  `describe.py` (`_doc` → public `scene_doc`), `pyproject.toml` (dev extra `jsonschema>=4.18`),
  docs above, tasklist.md.

Public interfaces added/changed (internal modules; `vidgen.api` unchanged)
- `vidgen.schema`: `config_schema(entries, themes)`, `scene_schema(entries, themes)`,
  `params_schema(entry, themes)`, `project_themes(project, theme)`, `theme_tokens(themes)`,
  `lenient_project(path)`, `DIALECT`, `THEME_KEY`.
- `cli.scene_types_session(path, lenient=False)` (context manager → `(project | None,
  theme)`; `list-scenes` uses it too), `cli.cmd_schema`; `jsonout.schema_document`.
- `describe.scene_doc(entry)`.
- Config model fields have `description`s; validation behaviour and messages unchanged.

Decisions / deviations
- `--scene` and `--all` are mutually exclusive; `--all` is "one scene item with every type"
  (a valid schema an agent can apply per scene), not a name → schema map.
- Without `--json` the raw schema is printed (so `vidgen schema > video.schema.json` works);
  `--json` adds the envelope, like the other commands.
- Token enums are the union of base and variant themes (a variant may define a color its own
  scenes use); slightly permissive for the base config.
- Per-type nested models are `$defs/scene.<type>.<Model>` to avoid collisions between types.

Known gaps / TODOs
- Not expressible in the schema (only `vidgen validate`): unique scene/beat ids, referenced
  files, `validate_project`, pydantic validators written in Python (e.g. "one value per
  label"). Values pydantic coerces (`"30"` for an int) pass validate but not the schema.
- The schema is a snapshot: regenerate after adding scene types, theme tokens or variants.

How to test: `/home/claude/venv/bin/python -m pytest -q` (455 passed, 1 skipped; needs the dev
extra `jsonschema`: `pip install -e .[dev]`). Manual: `vidgen schema examples/custom_scene`,
`vidgen schema --scene bar_chart`, `vidgen schema --all --json`.

## Step 10 — Frame capture in the worker
What was built
- `vidgen render --frames` saves a PNG still of the **last frame of every beat** (what is on
  screen when the beat's narration + pad is over); `--frames-per-beat N` saves N evenly spaced
  stills per beat, the last at its end (implies `--frames`). Off by default. Works with
  `--preview`, `--variant`, `--scene`, `--jobs`, `--no-audio` and `--json`.
- Files in `build/<final|preview>[_<variant>]/frames/`: `<scene>/<beat>-<k>.png` (silent scenes:
  `<scene>-<k>.png`), `<scene>/index.json` (`{scene, per_beat, width, height, fps, frames:
  [{beat, k, n, frame, time, path}]}`, time from scene start) and `index.json` for the whole
  video (`time` in the video, `scene_time`, `path` relative to `frames/`; scene `start`/
  `duration`). Silent scenes are one segment of `duration - outro` (the still is taken before
  the fade-out).
- Capture hook (`vidgen/capture.py`): `FrameCapture(per_beat, listeners)` wraps
  `renderer.add_frame`; `NarratedScene.narrate()` marks beat start/end
  (`begin_segment`/`end_segment`), silent scenes are planned at construction, `tear_down`
  calls `finish()`. Listeners `(scene, CapturedFrame)` run at the captured frame with the scene
  in that frame's state — **Step 12 attaches its layout dump here** (append a listener in the
  worker next to `StillWriter`, or pass it in `FrameCapture(..., [writer, layout])`).
- Docs: docs/CONFIG.md "Frame stills (`vidgen render --frames`)" + `outputs.frames` in the
  render JSON table; README (command table, options, layout); EXTENDING.md (hook keys, where
  stills are taken, `self.capture`); `examples/minimal/video.yaml` usage line; DESIGN §2, §3,
  §6.2, §8 and new §13.

Files
- New: `src/vidgen/capture.py`, `tests/test_frames.py` (16 tests, 4 render tests).
- Changed: `scene.py` (`capture=` kwarg, `self.capture`, calls in `narrate`/`__init__`/
  `tear_down`), `render/worker.py` (`--frames N`, `scene_frames_dir`, `remove_tree`, stills
  folder cleared before every render, `render.frames` in timings), `render/pipeline.py`
  (`frames=` arg, `write_frames_index`, `_usable_render` checks stills, combined index removed
  before each render, hook keys), `cli.py` (`--frames`, `--frames-per-beat`, `frames:` line),
  `jsonout.py` (`outputs.frames`), `tests/test_json_output.py` (outputs now include `frames`),
  docs above, tasklist.md.

Public interfaces added/changed
- `NarratedScene(spec, project=None, theme=None, *, audio=True, capture=None, ...)`;
  attribute `self.capture` (`FrameCapture | None`). `vidgen.api` exports unchanged.
- `vidgen.capture`: `FrameCapture(per_beat=1, listeners=())` (`.attach(scene)`,
  `.begin_segment(beat_id, frames, *, include_end)`, `.end_segment(beat_id)`, `.finish()`,
  `.listeners`, `.frames_written`), `CapturedFrame`, `CaptureListener`, `StillWriter(folder)`
  (`.entries`, `.index(...)`), `plan_targets(start, frames, n, include_end)`.
- `render_project(..., frames=0)`, `RenderResult.frames_index`, `pipeline.write_frames_index`;
  `worker.render_scene(..., frames=0)`, `worker.scene_frames_dir`, `worker.remove_tree`.
- Hook data: `post_scene.frames`, `post_render.frames_index` (both `None` without frames).
- `render --json`: `outputs.frames` (added within JSON version 1).

Decisions / deviations
- Captured from Manim's renderer, not by decoding the MP4: exact pixels and frame index (no
  H.264 loss or seek rounding), no extra pass, and listeners see the live scene state at that
  moment, which Step 12 needs. The stills are the uncompressed frames (tests compare them with
  the decoded video: same frame, small codec difference).
- "End of beat" = last frame of the beat including `narration.pad` (the frame before the next
  beat starts), taken when the beat actually ends, so it is right even when a beat's animations
  overrun. Mid-beat stills are planned from `round((d + pad) * fps)`.
- CLI: two flags (`--frames`, `--frames-per-beat N`) instead of `--frames [N]`, because an
  optional value would swallow the PROJECT argument (`vidgen render --frames proj`).
- Stills are always deleted when a scene is re-rendered (with or without `--frames`), and
  `frames/index.json` on every render, so nothing stale is ever indexed. Requesting stills makes
  scenes without matching stills non-reusable (`--scene` renders them again).
- The listener API is internal (`vidgen.capture`), not in `vidgen.api`; `self.capture` is
  documented as internal in EXTENDING.md.

Known gaps / TODOs
- Stills are only taken by narrated beats via `narrate()` (incl. `narrate_all`, `timeline`,
  `reveal`) and for silent scenes; a scene that never calls `narrate` for its beats gets no
  stills for them (it already warns about un-narrated beats).
- Only the Cairo renderer is supported (vidgen never selects OpenGL).
- No max for N; large N at final quality writes many 1080p PNGs (Step 11 storyboard will
  normally use preview).
- Step 11: build contact sheets from `frames/index.json` + `timings.json` (beat texts); default
  to `--preview`. Step 12: add a layout listener (scene mobjects → pixel bboxes) to the same
  `FrameCapture` in `worker.render_scene`.

How to test: `/home/claude/venv/bin/python -m pytest -q` (471 passed, 1 skipped). Manual:
`vidgen render examples/minimal --preview --frames-per-beat 2 --jobs 4`, then look at
`examples/minimal/build/preview/frames/`.

## Step 11 — `vidgen storyboard`
What was built
- `vidgen storyboard [PROJECT] [--scene ID ...] [--per-beat N] [--variant NAME] [--preview |
  --final] [--width PX] [--jobs N] [--force] [--json]` writes contact sheets to
  `build/<preview|final>[_<variant>]/storyboard/`: `video-<p>.png` (the whole video, pages of
  bounded size) and `scenes/<scene>-<p>.png` (one scene, larger stills). Each still is
  labelled `beat @ time` (video time `m:ss.s` on video sheets, scene time on scene sheets;
  `k/n @ time` with several stills per beat), the beat's narration is wrapped (and cut with
  `…`) under it, every scene has a header band `N/M  id · type · start–end (duration)`.
  Preview format by default.
- Reuse: a scene is rendered (with stills, in the usual worker processes, `--jobs`) only when
  its stills are missing, at another `--per-beat`/format, or stale. Staleness uses a new **scene
  fingerprint** the worker stores in `timings/<scene>.json` (`render.fingerprint`): scene entry,
  rest of the config (variant applied), beat MP3 stat, extension `.py` contents, `assets/` stat,
  vidgen's own rendering source. So `storyboard` after `render --preview --frames` or after an
  earlier storyboard renders nothing (~2 s for examples/minimal), and after an edit only the
  edited scenes.
- Sheet design (iterated by looking at the PNGs): white page, 1280 px wide (640–2000, fonts
  scale with the width), at most ~1.25 x width high, balanced pages; 16:9 → 4 stills per row
  (scene sheets 2), 9:16 → 5 (4), N stills per beat → the nearest multiple of N; short scenes
  share a row; a scene continued on the next page repeats its header `(continued)`.
- `--json`: Step 8 envelope with `project, variant, preview, per_beat, format, folder, rendered,
  reused, elapsed, sheets: [{kind, scene, page, pages, path, width, height, frames: [{scene,
  beat, k, n, time, scene_time, path}]}]`.
- Docs: docs/CONFIG.md "Storyboard (`vidgen storyboard`)" + "`vidgen storyboard --json`";
  README (quick start, command table, paragraph); EXTENDING.md (check scenes with storyboard,
  hooks); `examples/minimal/video.yaml` usage line; DESIGN §2, §8, new §14.

Files
- New: `src/vidgen/storyboard.py`, `src/vidgen/sheets.py`, `src/vidgen/render/fingerprint.py`,
  `tests/test_storyboard.py` (21 tests, 2 render tests).
- Changed: `cli.py` (`cmd_storyboard`, parser, `JSON_COMMANDS`), `jsonout.py`
  (`storyboard_document`), `render/pipeline.py` (`render_scenes`, `_SceneRuns` → `SceneRuns`),
  `render/worker.py` (`render.fingerprint`), docs above, `examples/minimal/video.yaml`,
  tasklist.md.

Public interfaces added/changed (internal modules; `vidgen.api` unchanged)
- `vidgen.storyboard`: `make_storyboard(project, *, preview=True, scenes=None, per_beat=1,
  width=1280, jobs=1, force=False) -> StoryboardResult` (`folder, format, preview, per_beat,
  sheets: [Sheet], rendered, reused, warnings`), `Sheet(kind, scene, page, pages, path, width,
  height, stills)`, `stills_current(project, preview, scene_id, per_beat)`, `storyboard_dir`.
- `vidgen.sheets`: `compose_pages(...) -> list[SheetPage]`, `SheetScene`, `SheetStill`,
  `SheetPage`, `load_font`, `wrap_text`, `fit_line`, `format_time`, `DEFAULT_WIDTH`,
  `MIN_WIDTH`/`MAX_WIDTH`, `PAGE_RATIO`, `MAX_COLUMNS`.
- `vidgen.render.fingerprint`: `scene_fingerprint(project, scene_id)`, `vidgen_source_digest()`,
  `NOT_RENDER_INPUTS`, `FINGERPRINT_VERSION`.
- `pipeline.render_scenes(project, preview, scene_ids, jobs=1, frames=0) -> SceneRuns`.
- Per-scene timings `render` block: new key `fingerprint`. JSON: new `storyboard` document.

Decisions / deviations
- Options beyond the task list: `--final` (the opposite of the default `--preview`), `--width`,
  `--jobs`, `--force` (files outside `assets/` are not tracked by the fingerprint).
- With `--scene`, no whole-video sheet is written and old `video-*.png` are deleted (they could
  show the scene's old stills). Without it, the storyboard folder is cleared first.
- Storyboard renders scenes but does not join the video (and does not dispatch
  `pre_render`/`post_render`); `vidgen render` behaviour is unchanged (it does not use the
  fingerprint). Video times come from the per-scene timings' durations (the joined video probes
  the MP4s; the difference is below a frame).
- Default page 1280 px x ≤1600 px rather than 2000 px wide: image tools downscale big images
  (to ~1.2 MP), and at this size the 19 px labels/narration remained clearly legible when I
  opened the sheets with the Read tool; a 9:16 video at 5 per row gets 2 rows per page.
- Light sheet background: dark frames stand out and text has maximum contrast.

What I saw in the storyboards (examples/minimal at 16:9 and `--variant vertical`, kphi3 16:9)
- Sheets read well: labels, times and narration legible; long kphi3 narration is cut after 4
  lines with `…`; `--per-beat 3` shows animations in progress (e.g. the title still being
  written at 1/3 of the first beat).
- Built-in scene issues for later steps (Step 15 layout regions / Step 21+ reviews / lint):
  - 9:16 in general: most built-ins keep their 16:9 layout centred in the tall frame, leaving
    the top and bottom thirds empty. Worst: `code` (the listing is scaled to the frame width,
    text becomes illegibly small), `bullets` (small items in the middle band), `quote` and
    `text_card` (small text in a large empty frame), `line_chart` (narrow plot, tiny tick and
    axis labels). `image` with `fit: cover` + Ken Burns `end_focus [0.7, 0.35]` pushes the sun
    half out of frame in 9:16.
  - Small/dim secondary text at 16:9 too: `title` authors line, `quote` source line,
    `equation` and `bar_chart` captions, `line_chart` tick/axis labels, `image` caption,
    `end_card` lines — likely below a sensible minimum size for 480p/mobile (Step 13 lint).
  - `equation`: the formula is small with lots of empty space; `bullets` 16:9 leaves the lower
    half empty with 4 short items.
- Generated PNGs were not committed (`build/` is ignored).

Known gaps / TODOs
- The fingerprint does not see files a scene reads outside `assets/` or the extension folders'
  `.py` files (`--force`), nor changes in installed libraries (Manim, fonts).
- `vidgen render` could reuse unchanged scenes via the fingerprint too (not done: it would
  change its documented behaviour).
- Pages are capped by height but a single scene with very many stills just gets more pages; no
  overall cap on page count.
- Step 12 can add layout boxes to the stills; a later step could overlay lint findings (Step 13)
  on the sheets.

How to test: `/home/claude/venv/bin/python -m pytest -q` (492 passed, 1 skipped). Manual:
`vidgen storyboard examples/minimal -j 4`, `vidgen storyboard examples/minimal --variant
vertical`, `--per-beat 3`, `--json`; open `examples/minimal/build/preview/storyboard/*.png`.

## Step 12 — Layout introspection
What was built
- Whenever stills are captured (`render --frames` / `--frames-per-beat N`, `storyboard`), the
  worker also writes `build/<final|preview>[_<variant>]/layout/<scene>.json`: for each captured
  frame (same `beat, k, n, frame, time` as the stills index, plus `still` = the PNG relative to
  the layout file and the `camera` frame) every **visible** object: `id` (stable per object
  across the scene's frames), `kind` (`text|code|math|number|shape|group|image`), `class`,
  `path` (parent chain `Class[i]`, or the scene's name for it), `name` (scene attribute or
  `Mobject.name`), `bbox` (output px, top-left origin, stroke included, may exceed the frame),
  `opacity` (fade states included; opacity-0 parts/objects are left out), `z`, `order` (draw
  position), `parts`; text kinds add `text`, `font_px`, `color`, `colors`, `backdrop`; others
  `fill`/`stroke` (`width_px`). Header: `version, scene, type, width, height, fps, per_beat,
  px_per_unit, background, safe_area` (px, from `margin_x/margin_y`).
- `font_px` = 75th percentile of the visible glyph heights in output px (≈ cap height for mixed
  case). `backdrop` = most common frame colour inside the text box excluding the text's own
  colours (sampled from the captured pixels, so it sees plates, images and highlight bands).
- Grouping: one object per text mobject (not per glyph), `Code` split into its paragraphs
  (kind `code`, Manim's invisible ` pA<n>` alignment suffix stripped) and background; groups
  with only shapes collapse into one `group`; MovingCamera zoom/pan handled via the scene's
  camera transform.
- Verified by drawing the boxes on stills (scratch script, not committed) for all of
  examples/minimal (16:9, per-beat 2, and vertical `listing`/`sizes`) and all kphi3 scenes:
  boxes hug the glyphs/shapes/images; `font_px` values look right (e.g. 9.9 px code text in
  9:16 preview, 35 px title at 480p).

Files
- New: `src/vidgen/introspect.py`, `tests/test_introspect.py` (14 tests, 1 render test).
- Changed: `capture.py` (`still_name`), `render/worker.py` (`scene_layout_path`, recorder
  listener, layout deleted before every render), `render/pipeline.py` (`_has_stills` requires
  the layout; `frames/index.json` scenes get `layout`), `scenes/bar_chart.py` (the counting
  value label keeps `original_text` in sync after `become`), DESIGN (§2, §3, new §15),
  docs/CONFIG.md (new "Layout dump" section, combined index `layout`), README, EXTENDING.md,
  tasklist.md.

Public interfaces added/changed (internal modules; `vidgen.api` unchanged)
- `vidgen.introspect`: `LayoutRecorder()` (capture listener; `.objects(scene, pixels)`,
  `.document(scene, per_beat)`, `.frames`), `LAYOUT_VERSION = 1`, `FONT_PERCENTILE = 75`.
- `vidgen.capture.still_name(captured)`; `worker.scene_layout_path(project, preview, scene_id)`.
- `frames/index.json` scene entries: new key `layout` (within its version).

Decisions / deviations
- Always on with stills, no flag: ~50 ms per 1080p still (kphi3 `setup`: 224 ms for 4 stills
  in a 50 s render), and stills/layout can never come from different renders.
- `font_px` is glyph-height based (works for Text, Paragraph, Tex alike; Manim's `font_size`
  is not defined for Paragraph and is wrong after transforms); documented as p75 of glyph
  heights, not em size. Lint thresholds (Step 13) should be set in these units.
- Contrast input is `backdrop` sampled from pixels instead of searching shapes under the text:
  exact for images, gradients, translucent plates.
- Bezier curves are sampled (5 points per cubic) rather than using control points, so round
  glyph boxes are tight.

Known gaps / TODOs (Step 13 lint)
- `text` is the construction string: `become()`/`Transform` don't update it (built-ins fixed
  where it matters); during `TransformMatching*` loose glyphs are `shape`/`group` objects.
- `order` follows z-index draw order; Manim's Cairo renderer draws moving mobjects over static
  ones mid-animation regardless of that. Objects covered by an opaque one are still listed.
- `opacity` is the max over parts (e.g. a code listing with dimmed lines reports 1.0).
- Image objects are often intentionally larger than the frame (`fit: cover`): lint should not
  flag images as off-frame. Findings to expect: `image` caption and `bar_chart` caption touch
  or cross the bottom safe margin; kphi3 `setup` text slightly outside the safe area; 9:16
  `code` text ≈ 10 px at 854 px height.
- No CLI to view layouts; Step 13's `vidgen lint` should check `scene_layout_path` exists
  alongside `storyboard.stills_current` (fingerprint covers `introspect.py`).

How to test: `/home/claude/venv/bin/python -m pytest -q` (506 passed, 1 skipped). Manual:
`vidgen render examples/minimal --preview --frames`, then read
`examples/minimal/build/preview/layout/*.json`.


## Step 13 — `vidgen lint` (layout rules)
What was built
- `vidgen lint [PROJECT] [--scene ID ...] [--rule NAME ...] [--variant NAME] [--preview |
  --final] [--fail-on error|warning|info|never] [--jobs N] [--force] [--json]` checks the
  layout dump (Step 12) of every **beat-end still** and prints one finding per problem:
  severity, rule, `beat @ scene time (+N more beats)`, a message with the measured value and
  the limit, and the still to open. Exit code 1 iff a finding is at least as severe as
  `fail_on` (default `error`). Stills are reused when current (any `--per-beat`, e.g. from a
  storyboard; ~0.7 s for examples/minimal); otherwise the scene is rendered with one still per
  beat, like the storyboard does.
- Rules (`vidgen/lint/layout_rules.py`), sizes as fractions of the frame's shorter side:
  `off_frame` (error for text, warning for other objects; full-frame bleeds such as cover
  images/Ken Burns/backgrounds/bands and wholly off-frame objects are not reported),
  `safe_area` (text in the margins), `text_overlap` (error), `covered_text` (a shape drawn
  over text, checked on the still's **pixels**), `min_font` (cap height < 2.5 % warning,
  < 1.8 % error; `font_px` corrected for lowercase letters), `contrast` (WCAG 2 ratio of the
  text colour blended at its opacity over the sampled backdrop: 4.5 / 3 large / 2 dimmed),
  `max_words` (> 40 words of `text` on screen).
- Noise control: only beat-end stills; objects below `lint.min_opacity` (0.1) ignored; the
  same problem on several beats is one finding (`beats`); same-rule findings of one still
  sharing a parent group (tick labels) or a colour pair (contrast) are one finding with
  `similar` objects (`also N more like it (...)`).
- Config: optional `lint:` section (`fail_on`, `min_opacity`, `rules.<name>.{severity,
  thresholds}`; `severity: off` disables a rule) and per-scene `lint_ignore` (rule names /
  `all`, or `{rule, object, beat}` with `*`/`?` wildcards matched against name, path or text).
  Both are in the JSON Schema (generated) and excluded from the render fingerprint.
- JSON (`--json`): envelope + `{project, variant, preview, format, fail_on, rules, scenes,
  stills, rendered, reused, elapsed, counts, ignored, findings}`; each finding `{scene, beat,
  time, scene_time, rule, severity, object, other, similar, bbox, message, value, limit,
  beats, still}`; failing → `ok: false`, `error.details {fail_on, counts}`.
- Docs: docs/CONFIG.md new "Lint (`vidgen lint`)" section + "`vidgen lint --json`", `lint`
  / `lint_ignore` rows; README (quick start, command table, paragraph); EXTENDING.md (lint new
  scene types; what lint treats as intentional); DESIGN §2, §8, §14 (fingerprint), new §16;
  `examples/minimal/video.yaml` usage line and a `lint:` section.

Files
- New: `src/vidgen/lint/{__init__,rules,layout_rules,color,run,findings,report}.py`,
  `tests/test_lint.py` (20 tests, 1 render test).
- Changed: `config.py` (`LINT_RULES`, `RuleName`, `Severity`, `RuleConfig` + one model per
  rule, `LintRules`, `LintConfig`, `LintIgnore`, `VideoConfig.lint`, `SceneConfig.lint_ignore`
  + `lint_ignores()`), `cli.py` (`cmd_lint`, parser, `JSON_COMMANDS`), `jsonout.py`
  (`lint_document`), `storyboard.py` (`stills_current(..., per_beat=None)` accepts any count
  and requires the layout file; `_scene_starts` → public `scene_starts`),
  `render/fingerprint.py` (`lint`/`lint_ignore` excluded; `lint` package not a render input),
  `tests/test_docs.py` (lint models), docs above, tasklist.md.

Public interfaces added/changed (internal modules; `vidgen.api` unchanged)
- `vidgen.lint`: `lint_project`, `LintResult` (`counts()`, `failed`), `Finding` (`to_json()`),
  `RULES`, `Rule`, `rule(name, *, scope="still", default=...)`, `Issue`, `StillContext`
  (`width`, `height`, `short_side`, `region(box)`), `SEVERITIES`, `FAIL_ON`, `report_lines`.
- Config: `lint` and `scenes[].lint_ignore` (new keys). `storyboard.stills_current` signature
  (`per_beat: int | None`), `storyboard.scene_starts`.

Decisions / deviations
- Sizes relative to the **shorter side**, not the height (the task said height): identical for
  16:9, but for 9:16 the height would make every text count 1.78x smaller than the same text
  in 16:9, flagging nearly everything in vertical videos.
- Thresholds were tuned by looking at the flagged stills (Read) of examples/minimal (16:9 and
  vertical) and kphi3: `min_font` 2.5 % / 1.8 % (theme `small` = 2.46 % is flagged, `caption`
  3.0 % and chart tick labels ≈ 2.55 % pass; kphi3's 1.6 % zoomed-out labels are errors). A
  first draft at 2.8 % / 2.0 % flagged many readable kphi3 labels.
- `font_px` (p75 of glyph heights) measured "sparse" at 11.3 px and "baseline" at 14.6 px at
  the same font size; `min_font` estimates the cap height from the characters' typical
  heights so lowercase labels are not penalised.
- `covered_text` (not in the task list; the "text vs shape" overlap the task called lower
  severity) uses the still's pixels: group/curve boxes are far larger than what they draw
  (the kphi3 network's box covered the title text but its lines did not), and a
  strike-through in the text's colour (kphi3 `setup`) is intentional.
- Contrast: text faded on purpose (opacity < 0.95: previous bullets, dimmed bars) needs only
  2:1, and a listing's line numbers are skipped (WCAG "incidental" text); otherwise WCAG AA.
- Exit code with `--json` follows the Step 8 rule (`ok` ⇔ exit 0): a failing lint is `ok:
  false` with `error.kind` `error`, findings still in the document.

Real findings (not fixed here: Review 1 / Step 15 should act on them)
- Theme `dim` (#6B7280) on the default background is 3.91:1, below WCAG AA 4.5:1 for normal
  text: every dim caption/label is flagged (minimal: `title` authors, `bar_chart` caption,
  `line_chart` axis/tick labels, `quote` source, `equation` caption; most kphi3 labels). One
  theme fix (Step 16 presets) removes most warnings.
- `image` caption sits 12 px into the bottom margin at 480p (both 16:9 and 9:16).
- `bar_chart` caption uses theme `small` (11.8 px cap at 480p, 2.46 %): too small.
- 9:16 `code`: the listing is scaled to the frame width, text 9.8 px (2.0 % of the width).
- kphi3: `method` beat 5 zooms the diagram out to 5.6–7.6 px labels (**error**, the only one);
  `loss` axis ticks and bar labels 9.8–9.9 px, its footnote 23 px into the bottom margin;
  `equivalence` left label 23 px into the left margin and the rotated `H = length` 8.9 px;
  `setup` block labels 11.4 px. Seen but not lintable: in `equivalence`/`title` the dumped
  `text` is the pre-`Transform` string (messages quote it; the still is right).
- No off_frame, text_overlap, covered_text or max_words findings in the examples (all three
  are exercised by tests, including a render test with overlapping and cut-off text).

Known gaps / TODOs
- Only beat-end stills are checked; problems that exist only mid-beat are not seen.
- Per-part opacity is not in the layout dump (max over parts), so dimmed lines inside one
  `Code`/`Paragraph` are invisible to `contrast`; `backdrop` is a single most-common colour
  (approximate over busy images); boxes are axis-aligned (rotated text).
- Same-size texts can measure ±5 % apart (`font_px` + letter correction), so a text near a
  threshold can flip between runs of different content.
- Step 14 (timing rules): add a scope (e.g. `beat`) in `lint/rules.py`, its context and a
  branch in `run._scene_findings`; add names to `config.LINT_RULES`/`RuleName` and settings
  models to `LintRules` (a test keeps them in sync); docs table + defaults block (tested).
- Storyboard sheets could draw lint findings (bbox) on the stills.

How to test: `/home/claude/venv/bin/python -m pytest -q` (536 passed, 1 skipped). Manual:
`vidgen lint examples/minimal`, `vidgen lint examples/minimal --variant vertical`,
`vidgen lint examples/kphi3` (exit 1: one error), `--json`, `--rule min_font`.
