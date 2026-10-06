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

## Step 14 — Timing lint
What was built
- Four timing rules in `vidgen lint` (same command, report, JSON, `lint:` config, `lint_ignore`,
  JSON Schema): `narration_speed` (spoken words per second of speech per beat outside
  `[min_rate 1.8, max_rate 3.5]`, beats of ≥ `min_words` 5), `dead_air` (nothing on screen
  changes for > `max_seconds` 6 s; `min_change` 0.0002 of the frame), `animation_overrun` (a
  beat's code takes longer than its narration + pad by > `tolerance` 0.1 s, so the next beat
  starts late; lists the animations still running when the narration ends; silent scenes
  whose animations exceed `duration` too), `rushed_animation` (animations `play_steps` had to
  shorten below `min_run_time` 0.5 s because the beat is too short for its steps). All
  default `warning`; `narration_speed` on beats without audio is `info` and grouped.
- **Activity file** `build/<q>[_<variant>]/activity/<scene>.json`, written by the worker with
  the stills/layout: beats (`start`, `end`, `busy`, `source`, `text`), every `play`/`wait`
  (scene times, beat, animation names, `requested` when `play_steps` shortened it), silent
  `{duration, busy}`, and a per-frame motion signal.
- `NarratedScene` records `play_log` (it overrides `play`; `wait` goes through it),
  `beat_busy`, `silent_busy`; `play_steps` marks shortened plays.
- Docs: docs/CONFIG.md new "Activity file" section, Lint intro/rule table/defaults block/JSON
  finding text, frames index `activity`; README (quick start, command table, paragraph);
  EXTENDING.md (how timing lint sees custom scenes); DESIGN §2, §5.1, §16, new §17;
  `examples/minimal/video.yaml` usage line.

Files
- New: `src/vidgen/activity.py`, `src/vidgen/lint/timing_rules.py`, `tests/test_timing_lint.py`
  (10 tests, 1 render test).
- Changed: `scene.py` (`PlayRecord`, `play`, `play_log`, `beat_busy`, `silent_busy`,
  `narrate`, `play_steps`, `tear_down`), `capture.py` (`FrameCapture(..., motion=)`),
  `render/worker.py` (`scene_activity_path`, MotionTrack, activity written/deleted),
  `render/pipeline.py` (`_has_stills` needs the activity; frames index `activity`),
  `storyboard.py` (`stills_current` needs it), `config.py` (4 rule names + settings models),
  `lint/rules.py` (scope `scene`, `SceneContext`, `Issue.beat/time`), `lint/run.py`
  (`_timing_findings`), `lint/findings.py` (`still` optional), `lint/report.py` (wider rule
  column, no still line without one), `lint/__init__.py`, tests `test_lint.py` (fake renders
  write an activity file; report spacing), `test_introspect.py` (activity in index/reuse),
  docs above, tasklist.md.

Public interfaces added/changed (`vidgen.api` unchanged)
- `NarratedScene.play_log: list[PlayRecord]`, `.beat_busy: dict[str, float]`,
  `.silent_busy: float | None`, `PlayRecord` (in `vidgen.scene`), `play` override.
- `vidgen.activity`: `MotionTrack(samples=180, level=6)` (`observe(frame, index, count)`,
  `to_json()`), `activity_document(scene, motion, fps)`, `ACTIVITY_VERSION`.
- `FrameCapture(per_beat, listeners, motion=None)`; `worker.scene_activity_path`.
- `vidgen.lint`: `SceneContext` exported; `Issue(..., beat=None, time=0.0)`; rule scope
  `"scene"`; `Finding.still: Path | None` (JSON `still` may be null);
  `vidgen.lint.timing_rules`: `spoken_words`, `speech_bounds`, `static_runs`.
- Config: `lint.rules.{narration_speed, dead_air, animation_overrun, rushed_animation}`; the
  same names in `lint_ignore`. Frames index scene entries: `activity`.

Decisions / deviations
- **Change signal from the renderer, not by decoding the MP4**: `FrameCapture` already sees
  every frame written (frozen waits once, with a count), the pixels are exact so a static
  frame is bit-identical (no codec noise to threshold away), and there is no second decode
  pass. Frames are sampled on a grid (every 3rd px at 480p, 6th at 1080p, ≤ 180 points on the
  shorter side) and compared with the previous: measured ~1.3 ms per written frame, i.e. at
  most ~2 s CPU for the 98 s examples/minimal preview (~55 s CPU render), a few percent.
  Only recorded when stills are captured (lint/storyboard/`--frames`), when it is needed.
- `min_change` 0.0002 (≈ 9 sample points): eased animations' first/last frames change only
  1-5 points and do not matter; a counter digit changes more than that.
- `narration_speed` uses the **speech** inside the MP3 (leading/trailing silence below -40 dB
  cut: ElevenLabs adds 0-0.8 s of trailing silence) and **spoken** words. Plain
  `len(text.split()) / mp3 length` gave kphi3 rates 1.60-3.12 with false "too slow" beats
  (`s7_b2` 1.72: "1.60", "1.58", "1.57", "K-Phi-3"; `s2_b4` 1.60: a short question plus 0.5 s
  trailing silence); with both corrections the 27 kphi3 beats are 2.13-3.40 words/s, so the
  defaults 1.8-3.5 flag none of them. Without audio the beat length is the estimate, so the
  rate only shows where numbers/acronyms make the estimate wrong (or the configured
  `words_per_second` is implausible): `info`, one finding per scene.
- `dead_air` treats narrated and silent time alike (one threshold): a silent card held still
  for > 6 s is dead air too; 6 s keeps title holds and short end cards quiet (none in the
  examples is flagged). Static stretches are attributed to the beat where they start, the
  message lists the beats they span.
- `animation_overrun` uses `busy` measured in `narrate` (the body's time before the wait to
  `d + pad`), so user `self.wait()` past the narration counts too. Running into the pad only
  is not reported (`tolerance` is beyond `d + pad`).
- `rushed_animation` only sees `play_steps` compression (it knows what was wanted); plays a
  scene shortens itself (`run_time=d/5`) are invisible. The task's "beat too short for its
  animations" is covered by `animation_overrun` for custom scenes (they overrun) and by
  `rushed_animation` for `play_steps`/`reveal`/built-ins (they compress).
- Timing findings are not merged across beats by object (they have none): one finding per
  issue, or per `group` (estimates). Rule column of the human report widened to 17 chars.

Findings on the examples (all real; not fixed here: Review 1 / Step 22)
- `examples/minimal` 16:9 and `--variant vertical`: no timing findings (layout findings as in
  Step 13). Closest: `note` holds still 5.5 s while narrating (the whole card appears in 0.8 s
  of a 5.8 s beat), `steps` beat 2 5.0 s still. No audio, all estimates within range.
- `examples/kphi3` (real MP3s): 4 `dead_air` warnings, checked on frames extracted from the
  scene MP4s (identical pixels across the interval):
  - `setup` 3.0-10.4 s (7.4 s, beat `s5_b1`: the Phi-3 setup diagram appears in 3 s of a
    9.8 s beat), `setup` 22.3-29.2 s (6.9 s, `s5_b3` into `s5_b4`).
  - `loss` 16.3-23.7 s (7.3 s, `s7_b2`, the 15.7 s beat about validation loss: the "best 1.57"
    highlight appears early, then nothing moves).
  - `method` 38.0-44.5 s (6.5 s, `s4_b5`: the zoomed-out diagram holds while narrating).
  - Near misses: `conclusion` 5.7 s and 5.8 s still stretches.
  - No `narration_speed`, `animation_overrun` or `rushed_animation` findings: every kphi3 beat
    finishes its animations 0.7-7 s before its narration ends.
- The render tests exercise all four rules on a real render (overrun, rushed steps, dead air
  in a narrated beat and in a silent scene).

Known gaps / TODOs
- `rushed_animation` cannot see run times a scene computes itself; per-animation intended
  durations would need an API (e.g. `self.play(..., min_run_time=...)`).
- The speech-rate count is English-centric (digits read as English words, acronym rule).
- Dead air does not distinguish meaningful from trivial motion (a slow Ken Burns pan counts as
  change, which is intended); a tiny blinking element resets the timer.
- Renders from before Step 14 have no activity file and are re-rendered by lint/storyboard.
- Storyboard sheets could mark dead-air stretches / overruns on the timeline.

How to test: `/home/claude/venv/bin/python -m pytest -q` (546 passed, 1 skipped). Manual:
`vidgen lint examples/kphi3 --rule dead_air --rule narration_speed --rule animation_overrun
--rule rushed_animation`, `vidgen lint examples/minimal [--variant vertical]`, then read
`examples/*/build/preview/activity/*.json`.

## Step 15 — Layout regions
What was built
- `vidgen/regions.py`, exported by `vidgen.api`: `Region` (rectangle in Manim units with
  `width/height/center/orientation`, `point(align)`, `contains`, `inset`, `below`/`above`,
  `rows`/`columns`/`split`, `grid`, `to_rectangle`), `frame_region()`, `safe_area()`,
  `region(name)` (`full, header, body, hero, caption, top, bottom, left, right, center`),
  `grid(rows, cols, area)`, `place(mob, area, fit="contain"|"width"|"height"|"none",
  align=..., max_scale=None, buff=0)`, `orientation()`, `readable_size(font)` and
  `readable_text(text, area, size, min_size, **fit_text_args)`.
- `NarratedScene.safe_area` and `NarratedScene.region(name)`; `safe_width`/`safe_height` now
  derive from `safe_area`.
- Aspect-aware: `left`/`right` are side by side in landscape/square and the upper/lower half in
  portrait (`Region.split` likewise; literal halves via `Region.columns(2)`); band and
  `center` shares differ per orientation (table in docs/EXTENDING.md).
- Built-ins refactored onto regions (the two worst 9:16 offenders per Steps 11–13):
  - `code`: title in `header`, listing in the rest; new param `wrap` (default true): when the
    listing is width-bound and would be smaller than `size` (or the readable minimum), long
    lines are wrapped with a hanging indent and the listing rebuilt; wrapped listings keep one
    number per original line and highlights cover the wrapped continuation lines.
  - `bullets`: heading in `header`, list centered below it; in portrait the heading is 1.3x
    (`portrait_growth`), a short list grows up to 1.3x and spreads out.
- `examples/custom_scene/extensions/gears.py` uses `region("center")`, `place` and
  `readable_text` (usage example); docs/EXTENDING.md's `checklist` example now uses regions
  and is executed by a test.

Before / after (examples/minimal, preview, `vidgen lint` + `vidgen storyboard`)
- 16:9: 7 warnings before, 7 after (identical findings; none from `steps`/`listing`). Stills of
  `steps` and `listing` look the same (heading/title a few px lower: centered in `header`).
- 9:16: 8 warnings before, 7 after: the `listing` `min_font` warning (code 9.8 px cap height,
  2.04 %) is gone — code is now 15.6 px font_px (wrapped to ~31 columns, 13 lines for 9 original
  lines, at the requested `caption` size). `steps` items went from 19.4 to 21.3 px `font_px` (the
  width limits growth: they wrap) and the heading from 22.0 to 28.5 px; rows are spread out, so
  the list fills the frame instead of a small block in the middle band.
- The remaining 7 (both orientations) are outside this step: theme `dim` contrast (5, Step 16
  presets), `bar_chart` caption at theme `small` (min_font), `image` caption 12 px into the
  bottom margin. `examples/custom_scene` 16:9 and vertical: 0 findings.

Files
- New: `src/vidgen/regions.py`, `tests/test_regions.py` (36 tests; 10 tiny renders at 160x90 and
  90x160).
- Changed: `api.py` (exports), `scene.py` (`safe_area`, `region`, margins from `regions`),
  `introspect.py` (layout `safe_area` from `regions.safe_area`), `layout.py`
  (`fit_text_sized`; `fit_text` delegates), `render/fingerprint.py` (key `readable`),
  `scenes/bullets.py`, `scenes/code.py`, `examples/custom_scene/extensions/gears.py`,
  DESIGN.md (§2, §5.3, §6.4, new §18), docs/EXTENDING.md ("Layout regions", checklist
  example), docs/CONFIG.md (`bullets`, `code` + `wrap`), README, tasklist.md.

Public interfaces added/changed
- `vidgen.api`: `Region, frame_region, safe_area, region, grid, place, orientation,
  readable_size, readable_text` (DESIGN §18). `NarratedScene.safe_area`, `.region()`,
  `Bullets.portrait_growth`. `vidgen.regions`: also `MARGIN_X/MARGIN_Y`, `GAP`,
  `REGION_NAMES`, `ALIGNMENTS`, `MIN_TEXT_FRACTION`, `min_text_fraction()`.
- `vidgen.layout.fit_text_sized` (internal, not exported). `vidgen.scenes.code.wrap_code`,
  `MIN_COLUMNS`, `HANGING_INDENT`.
- Config: `code` param `wrap: bool = true` (additive; existing configs unchanged). Render
  fingerprint now includes `lint.rules.min_font.min_size`.

Decisions / deviations
- **Single source of truth for the safe area**: the margins stay on the scene (`margin_x`,
  `margin_y`, defaults from `regions`), and the layout dump builds its `safe_area` with
  `regions.safe_area(scene.margin_x, scene.margin_y)`; lint reads the dump, so scene layout,
  dump and lint cannot drift. Values unchanged (0.6 / 0.5 units).
- **`left`/`right` adapt** instead of adding a separate orientation-aware pair: code written
  for a 16:9 two-column layout gets two rows in 9:16 for free; `Region.columns(2)` remains for
  literal halves and `Region.split(n)` is the general orientation-aware split.
- **Readable size from the lint threshold**: `readable_size` uses the project's
  `lint.rules.min_font.min_size` (5 % margin), so "what layout aims for" and "what lint
  accepts" are one setting; that value had to join the render fingerprint (other lint
  settings still do not invalidate renders).
- `readable_text` shrinks below the floor (with a logged warning) rather than overflowing when
  text cannot fit even when wrapped: layouts never break, and lint reports `min_font`.
- `code` wraps to reach the requested `size` (not just the lint minimum): wrapping only to the
  2.5 % floor left the 9:16 listing barely legible on a phone. Wrapping happens only when the
  listing is width-bound, so 16:9 output is unchanged.
- `bullets` grows in portrait only for short lists (≤ 5 items, < 75 % of the space), and the
  heading grows with it (items larger than the heading looked wrong in the first try).

Known gaps / TODOs
- Other built-ins (`quote`, `text_card`, `title`, `end_card`, `equation`, charts, `image`)
  still use `safe_width`/`safe_height` arithmetic; moving them to regions (and fixing the
  `image` caption margin, `bar_chart` caption size) fits Step 22 (Review 1) or the scene steps.
- Wrapped code: the layout dump's `text` of the line-number column is Manim's original string
  (`1..13`), not the shown labels; syntax highlighting of a line wrapped inside a string
  literal may be off (the wrapper avoids it when it can).
- `readable_size` measures the capital H of the font; a font with unusual proportions is
  measured correctly, but lint's cap-height estimate for lowercase-only text differs slightly.
- No `grid_shape(n)` helper (choose rows x cols for n items per orientation) yet; Step 21
  (`icon_grid`) may want one.

How to test: `/home/claude/venv/bin/python -m pytest -q` (582 passed, 1 skipped; regions:
`pytest tests/test_regions.py`). Manual: `vidgen storyboard examples/minimal --variant vertical
--scene steps --scene listing`, `vidgen lint examples/minimal [--variant vertical]`.

## Step 16 — Theme presets (mechanism + 3 presets)
What was built
- `theme: {preset: NAME, ...}` in `video.yaml`: a preset is a named set of theme values
  (`background`, `font`, `code_style`, `colors`, `palette`, `sizes`). Precedence, highest
  first: values written under `theme:` (after merging a variant) > the preset (then its `base`)
  > `register_theme_defaults` > built-in defaults. No preset → that level is empty, so existing
  projects render as before (apart from the `dim` fix below). Variants switch presets with
  `variants: {light: {theme: {preset: light_academic}}}`.
- Built-in presets (`src/vidgen/presets.py`): `dark_tech` (= the defaults), `light_academic`
  (off-white `#F8F7F3`, near-black text, ink accents, white `surface`, Pygments `xcode`),
  `high_contrast` (black, white text, accents ≥ 7:1, `caption` 26 / `small` 24).
- New theme key `code_style` (Pygments style, validated); the `code` scene's `style` param now
  defaults to it (was hard-coded `github-dark`, unreadable on a light window).
- Project presets: `vidgen.api.register_theme_preset(name, *, base, background, font, colors,
  palette, sizes, code_style, description)`, stored on the active Theme (per project).
- Reusable contrast check `vidgen.lint.color.theme_contrast(theme, text_ratio=4.5,
  graphic_ratio=3.0) -> list[ContrastCheck]`: text/dim vs background and surface (4.5:1),
  accent tokens and palette vs background (3:1).
- `vidgen validate` reports an unknown preset (`theme.preset: unknown theme preset ...; known
  presets: ...`); `vidgen schema` has `preset` (built-in + project presets) and `code_style`
  (installed Pygments styles) enums.
- Example: `examples/minimal` base theme `preset: dark_tech`, new variants `light`
  (`light_academic`) and `contrast` (`high_contrast`); the init template uses `preset:
  dark_tech` instead of an explicit background.

Files
- New: `src/vidgen/presets.py`, `tests/test_presets.py` (35 tests, 3 render tests: 7 built-in
  scene types rendered at 640x360 with each preset, lint `contrast` must be clean).
- Changed: `theme.py` (preset resolution, `preset`, `presets`, `preset_chain()`,
  `add_preset()`, `derive()`, `code_style`; `DEFAULT_*` now defined in `presets.py` and
  re-exported), `config.py` (`ThemeConfig.preset`, `code_style`; `background`/`font` default
  `None`), `api.py` (`register_theme_preset`), `cli.py` (preset check in `project_problems`),
  `schema.py` (`theme_presets`, enums, `project_themes` uses `Theme.derive`, `theme_tokens`
  skips themes with an unknown preset), `lint/color.py` (`theme_contrast`, `ContrastCheck`,
  `hex_rgb` accepts `#RGB`/`#RRGGBBAA`), `scenes/code.py` (`style` default), `scenes/bullets.py`
  (`dimmed_opacity = 0.45`), `templates/minimal/video.yaml`, `examples/minimal/video.yaml`,
  tests `test_config.py`, `test_docs.py` (preset table in sync), docs/CONFIG.md (Theme section
  rewritten: precedence, "Theme presets" table, `code_style`; schema enums; `code.style` row),
  docs/EXTENDING.md (§4 project presets), README (feature line), DESIGN.md (§2, §4, §6.2, §6.4,
  new §19), tasklist.md.

Public interfaces added/changed
- `vidgen.api.register_theme_preset` (new export).
- Config: `theme.preset`, `theme.code_style` (additive). `ThemeConfig.background`/`.font` are
  now `None` unless written (read resolved values from `Theme`, never from the config).
- `vidgen.theme.Theme`: `preset`, `presets`, `preset_chain()`, `add_preset()`, `derive()`,
  `code_style`. `vidgen.presets`: `ThemePreset`, `make_preset`, `BUILTIN_PRESETS`,
  `code_styles()`, `check_code_style()`, `DEFAULT_BACKGROUND/FONT/CODE_STYLE/COLORS/PALETTE/SIZES`.
- `vidgen.lint.color`: `theme_contrast`, `ContrastCheck`, `TEXT_RATIO`, `GRAPHIC_RATIO`,
  `TEXT_TOKENS`, `ACCENT_TOKENS`. `vidgen.schema.theme_presets`.
- `code` param `style`: default `None` (= theme `code_style`). `Bullets.dimmed_opacity`.

Decisions / deviations
- **Preset above extension defaults** (task: "define the precedence"): choosing a preset is an
  explicit config decision, so it beats defaults an extension registered in code, but never a
  value written in `video.yaml`. Built-in presets set all 8 built-in colour tokens, so an
  extension that re-defaults e.g. `dim` is overridden once a preset is chosen; extension-only
  tokens (`k2`) are unaffected. Brands should use `register_theme_preset(..., base=...)`.
- **Default `dim` fixed (visible change)**: `#6B7280` → `#838B98` (3.91:1 → 5.5:1 on the
  background, 5.0:1 on `surface`). Removes the five `contrast` warnings Steps 13–15 reported on
  examples/minimal. kphi3 writes its own `dim: "#6B7280"` in its config and is unchanged
  (faithful to the original video).
- Gotcha documented rather than changed: values written in the base `theme:` also override a
  variant's preset (deep merge), e.g. a base `background` keeps a light variant dark; the
  example and init template therefore select `preset: dark_tech` instead of writing
  `background`.
- `bullets` `dim_previous` opacity 0.4 → 0.45: the dimmed `primary` marker on `light_academic`
  was 1.93:1 (< lint's 2:1 for de-emphasised text); 0.45 gives 2.12:1. Dark output changes
  imperceptibly.
- Contrast scope of the check: text/dim on background and surface; accents and palette 3:1
  (WCAG 1.4.11). Accents are also used as text (title highlight, kicker, end-card title, bar
  value labels), so the built-in presets keep them ≥ 4.5:1 anyway (light) / ≥ 7:1 (high
  contrast). Code-style token colours are not part of `theme_contrast`; the render test runs
  lint's `contrast` rule on the code listing instead (xcode on white min 5.07:1, github-dark on
  `#161B24` 5.6:1).
- Presets are resolved lazily (on every read), so extensions can register a preset after the
  runtime context exists; a module reading the theme at import before the preset is registered
  gets the "unknown theme preset" error (documented: register in a module that sorts first).
- `light_academic` uses Inter like the others: no serif is guaranteed on every platform until
  Step 18 bundles fonts.
- Built-ins checked on light backgrounds: no hard-coded white/black anywhere in
  `src/vidgen/scenes`; image caption band uses `theme.background` (light band, dark text: fine);
  chart gridlines are `dim` at 0.4 opacity (light grey on light: fine); code window `surface`
  + `dim` border. Only `code` (style) and `bullets` (dim opacity) needed changes.

Verification (examples/minimal, preview 854x480, `vidgen storyboard` sheets viewed + `vidgen lint`)
- Default / `dark_tech` 16:9: 2 warnings (was 7 before this step: the 5 `dim` contrast
  warnings are gone). Remaining: `bar_chart` caption at theme `small` (`min_font`), `image`
  caption 12 px into the bottom margin (`safe_area`) — both pre-existing, Step 22.
- `--variant vertical` (dark): 2 warnings (same two; was 7).
- `--variant light` (`light_academic`): 2 warnings (same two). Before the bullets fix: +3
  `contrast` warnings on dimmed numbered markers.
- `--variant contrast` (`high_contrast`): 1 warning (only `safe_area`; `small` 24 pt clears
  `min_font`).
- `examples/custom_scene`: 0 findings. Sheets: every scene reads well on all three presets
  (light: dark text on off-white, xcode listing in a white window with an amber highlight band,
  pastel dimmed bars, image band light with dark caption).

Known gaps / TODOs (Step 17+)
- No `vidgen list-themes` yet (Step 17): it could print each preset with `theme_contrast`
  results. `vidgen lint`/`validate` do not yet run `theme_contrast` on the project's own theme
  (a `theme_contrast` lint rule of scope "project" would need a third scope).
- Type scales (`compact`/`standard`/`large`) are Step 17; `high_contrast` only raises
  `caption`/`small` for now.
- `register_theme_defaults` cannot set `background`/`font`/`palette` (unchanged); use a preset.
- Variant themes in `vidgen schema` share the base project's registered presets (`derive`),
  but a variant whose extensions differ is not modelled (variants cannot change extensions'
  code anyway).

How to test: `/home/claude/venv/bin/python -m pytest -q` (618 passed, 1 skipped). Presets only:
`pytest tests/test_presets.py`. Manual: `vidgen storyboard examples/minimal --variant light`,
`vidgen lint examples/minimal --variant contrast`, `vidgen schema examples/minimal`.

## Step 17 — Theme presets (4 more + type scales)
What was built
- Four built-in presets (`src/vidgen/presets.py`): `warm_editorial` (cream paper `#F6F0E4`,
  espresso text, petrol/terracotta/oxblood, Pygments `default`), `brand_neutral` (grey
  `#F4F5F7`, white `surface`, graphite text, one blue — a base for a brand colour, `xcode`),
  `soft_pastel` (dusky plum `#252238`, pastel accents, `zenburn`), `bold_neon` (violet-black
  `#0B0614`, cyan/magenta/yellow, `monokai`, `large` scale). Each defines all 8 colour tokens,
  an ordered 5-colour palette, `code_style`, `scale` and a description. Code styles were picked
  by measuring every Python token colour against the preset's `surface` (≥ 4.5:1).
- Type scales (`src/vidgen/scales.py`): `compact` 48/36/32/28/22/20, `standard` 56/42/36/32/24/20
  (= the old defaults), `large` 66/50/44/38/30/26, and `auto` (= `large` when the final `format`
  is portrait, else `standard`). `theme: {scale: NAME}` in the config, `scale` on presets
  (`ThemePreset`, `make_preset`, `register_theme_preset`); `sizes` still override single sizes.
  With no scale anywhere the default is `auto`, so vertical variants get larger text by default.
- `Theme` knows its orientation: `Theme(config, orientation=...)`, `Theme.for_format(config,
  fmt)` (runtime context + `NarratedScene`), `derive(config, fmt)`; `scale_setting`, `scale`.
- Font-role hook: `ThemePreset.fonts` / `register_theme_preset(fonts=...)`, `Theme.fonts`,
  `Theme.font_for(role)` (config `font` > preset role > `font`). Not read by scenes yet.
- Colour-vision check (`src/vidgen/lint/color.py`): `simulate_cvd` (Machado 2009 matrices),
  `lab`, `delta_e` (CIEDE2000), `palette_distinctness(palette)` → min ΔE per vision. All
  built-in palettes except `dark_tech` ≥ 7.5 under normal/protan/deutan/tritan (tested; new
  presets 8.7–10.9 min). `light_academic` and `high_contrast` third palette colour changed (their
  purples matched the blue for deuteranopes: 2.5 → 11.9 and 0.4 → 8.8).
- `vidgen list-themes [PROJECT] [--swatches PNG] [--json]` (`src/vidgen/themelist.py`): every
  preset (built-in + project) with resolved colours/palette/sizes/scale in this project, contrast
  summary, palette distinctness, and the scale table; `--swatches` writes a 1280 px PNG, one row
  per preset (looked at during the step: all seven read clearly and look distinct).
- `vidgen validate` warns (stderr `warning: theme contrast: ...`, JSON `warnings`; never fails)
  when the project's theme or a variant's own theme has a pair below WCAG AA.
- `examples/minimal`: variants `editorial`, `neutral` (`brand_neutral` + `scale: compact`),
  `pastel`, `neon` and a `list-themes --swatches` usage line; init template mentions
  `list-themes` and `scale`.

Verification (examples/minimal, preview, every preset storyboarded and the sheets opened)
| variant (preset, scale) | lint findings | notes |
|---|---|---|
| default (`dark_tech`, auto=standard) | 2 warnings | pre-existing: `bar_chart` caption `min_font`, `image` caption `safe_area` |
| `light` (`light_academic`) | 2 warnings | same two |
| `contrast` (`high_contrast`, large) | 1 warning | `safe_area` only (large caption clears `min_font`) |
| `editorial` (`warm_editorial`) | 2 warnings | same two; first draft had +1 `contrast` (line-chart label in palette `#D24A1E`, 3.9:1) → palettes of light presets made text-grade |
| `neutral` (`brand_neutral`, compact) | 2 warnings | same two (first draft +1 `contrast` like editorial) |
| `pastel` (`soft_pastel`) | 2 warnings | same two |
| `neon` (`bold_neon`, large) | 1 warning | `safe_area` only |
| `vertical` (`dark_tech`, auto=large) | 1 warning | `safe_area` only (was 2; `min_font` gone). Title, bullets, quote, end card visibly larger, nothing overflows |
`examples/custom_scene`: 0 findings in 16:9 and 9:16 (vertical now `large`; checked its sheet).
`examples/kphi3` validate now prints two `theme contrast` warnings (its own `dim: "#6B7280"`,
kept for fidelity to the original video, as in Step 16).

Files
- New: `src/vidgen/scales.py`, `src/vidgen/themelist.py`, `tests/test_scales.py` (15 tests, one
  9:16 render with `bold_neon`/large linted for off-frame/safe-area/overlap).
- Changed: `presets.py` (4 presets, `scale`/`fonts`, built-ins via `make_preset`,
  `DEFAULT_SIZES` from the standard scale, 2 palette fixes), `theme.py` (orientation, scale
  layering, fonts), `config.py` (`ThemeConfig.scale`), `runtime.py`, `scene.py`, `schema.py`
  (themes per format), `regions.py` (`orientation` delegates to `scales.frame_orientation`),
  `lint/color.py` (CVD helpers), `cli.py` (`list-themes`, theme warnings in `validate`),
  `jsonout.py` (`list_themes_document`), `api.py` (`register_theme_preset(scale=, fonts=)`),
  `render/fingerprint.py` (`themelist.py` not a render input), `templates/minimal/video.yaml`,
  `examples/minimal/video.yaml`, `tests/test_presets.py`, DESIGN.md (§2, §4, §6.4, §8, new §20),
  docs/CONFIG.md (Theme: `scale`, "Type scales", presets table + what each is for, colour-blind
  note, `vidgen list-themes`, JSON shape), docs/EXTENDING.md (preset `scale`/`fonts`, checks),
  README, tasklist.md.

Public interfaces added/changed
- Config: `theme.scale` (`compact|standard|large|auto`, additive). CLI: `vidgen list-themes`
  (JSON command `list-themes`, envelope v1). `vidgen validate` may print `warning:` lines.
- `vidgen.api.register_theme_preset(..., scale=None, fonts=None)` (keyword additions).
- `vidgen.theme.Theme`: `orientation`, `for_format`, `derive(config, fmt=None)`, `scale`,
  `scale_setting`, `fonts`, `font_for`. `vidgen.presets.ThemePreset.scale/.fonts`.
  `vidgen.scales`: `TYPE_SCALES`, `SCALE_TOKENS`, `SCALE_CHOICES`, `AUTO_SCALES`,
  `DEFAULT_SCALE`, `frame_orientation`, `resolve_scale`, `scale_sizes`, `Orientation`.
  `vidgen.lint.color`: `simulate_cvd`, `lab`, `delta_e`, `palette_distinctness`, `VISIONS`,
  `CVD_MATRICES`. `vidgen.cli.theme_warnings`, `log_theme_warnings`.

Decisions / deviations
- **`auto` is the default scale (visible change in portrait)**: the task asked for scale-aware
  defaults for vertical variants; vertical stills before this step had 19–22 px text on a 480 px
  wide preview. Landscape/square output is unchanged; `scale: standard` restores the old portrait
  sizes. `auto` follows the final `format`, so preview and final match.
- **Scale = shorthand at its level** (see DESIGN §20): a scale chosen anywhere overrides
  extension size defaults for the six scale tokens (consistent with preset colours overriding
  extension colour defaults); with no scale chosen, extension defaults still win as in Step 16.
- `high_contrast` now uses `large` instead of `caption 26 / small 24` (bigger everywhere).
- Built-in palettes are text-grade (≥ 4.5:1), stricter than the 3:1 `theme_contrast` checks,
  because charts write series labels in palette colours (lint caught it). Tested.
- `dark_tech` palette left as is (deuteranopia min ΔE 4.7) to keep default output stable;
  documented in CONFIG.md.
- Font roles are a hook only: no preset sets them and no scene reads them until Step 18.
- Theme warnings in `validate` are warnings, not problems: a project may choose colours
  deliberately (kphi3).

Known gaps / TODOs
- Step 18: bundle serif/mono, give `warm_editorial`/`light_academic` a serif heading role and
  `code` a mono role via `font_for`.
- `code` listings in portrait wrap more with `large` (`caption` 30 → ~25 columns in the example);
  readable but more broken lines. A code-specific size cap for portrait could be considered in
  Step 22 or Step 32 (`code_walkthrough`).
- Chart axis labels / tick labels use fixed fractions rather than size tokens in places, so they
  grow less than titles with `large`; Step 30 (chart helpers) can route them through the scale.
- `vidgen lint` still does not run `theme_contrast` (validate does).
- `list-themes` shows presets with the project's orientation; a variant with another orientation
  is not listed separately (`--json` `current` is the base config's).

How to test: `/home/claude/venv/bin/python -m pytest -q` (662 passed, 1 skipped). Step only:
`pytest tests/test_scales.py tests/test_presets.py`. Manual: `vidgen list-themes examples/minimal
--swatches build/themes.png`, `vidgen storyboard examples/minimal --variant neon`, `vidgen lint
examples/minimal --variant vertical`, `vidgen validate examples/kphi3` (theme warnings).

## Step 18 — Bundled fonts
What was built
- Three SIL OFL families ship as package data in `src/vidgen/data/fonts/<Family>/` with their
  `OFL.txt`; `THIRD_PARTY_NOTICES.md` (repo root) lists source, version, copyright, files:
  | family (Pango name) | files | size | source (via npm, the only allowed channel; GitHub is blocked) |
  |---|---|---|---|
  | Inter 4.001 (`Inter`) | Regular, Bold, Italic `.ttf` | 985 KB | `inter-ui` 4.1.1 `web/*.woff2` → TTF (fontTools, lossless) |
  | Source Serif 4 4.005 (`Source Serif 4`) | Regular, Bold, It `.ttf` | 721 KB | Adobe's `source-serif` 4.5.1 `TTF/` (as shipped) |
  | JetBrains Mono NL 2.242 (`JetBrains Mono NL`) | Regular, Bold `.ttf` | 290 KB | `jetbrains-mono` 1.0.6 `fonts/webfonts/*.woff2` → TTF; OFL text from `@fontsource/jetbrains-mono` |
  Total 2.0 MB on disk, the wheel grows to ~1.1 MB (checked with a local `pip wheel`: all 11
  files are in it). `pyproject.toml` package-data `data/fonts/**/*`.
- `src/vidgen/fonts.py`: `BUNDLED_FAMILIES`, `FONTS_DIR`, `SANS/SERIF/MONO_FAMILY`,
  `bundled_font_files()`, `bundled_font_file(family, bold, italic)`,
  `register_bundled_fonts()` (manimpango.register_font per file, idempotent, failures are
  warnings, clears Manim's cached font list), `FONT_TOKENS`, `ROLE_DEFAULTS`, `BUILTIN_ROLES`.
  Registration runs at import of `vidgen.helpers` / `vidgen.regions` and first thing in the
  worker's `render_scene` (Pango only sees fonts registered before its first text layout —
  verified: registering after a first `Text` has no effect on Linux).
- Theme tokens `font_serif` (Source Serif 4), `font_mono` (JetBrains Mono NL), `font` stays the
  sans family (Inter); config `theme.font_serif`, `theme.font_mono`, `theme.fonts` (role →
  `sans`/`serif`/`mono` or a family); presets/`make_preset`/`register_theme_preset` gain
  `font_serif`, `font_mono`. `Theme.font_for(role)`: config `fonts` > preset chain > role default
  (`code` → mono, `quote_mark` → serif, else sans), tokens resolved to the families.
- Built-in scenes read roles: `heading` (title/bullets/chart/code titles, end-card title),
  `quote` (quote text), `quote_mark` (`quote.mark_font` default now the role), `code` (`code.font`
  default now the role = JetBrains Mono NL). `fit_text(..., font=None)`.
- Presets: `light_academic` serif headings; `warm_editorial` serif headings and quotes.
- `list-themes`: `font_serif`, `font_mono`, `font_roles` in entries and the text listing; swatch
  heading drawn in the preset's heading family. Contact sheets prefer the bundled Inter files.
- Fingerprint includes the bundled font files.

Verification
- Pango really uses the bundled files: `test_pango_renders_with_the_bundled_faces` compares the
  ink width of three sample strings laid out by Pango (Manim `Text`) with FreeType's
  measurement of the same strings from the bundled file (Pillow), for all 3 families × Regular/Bold:
  the ratio agrees within 2 % per sample across families (a substituted face is off far more).
  Source Serif 4 and JetBrains Mono NL are *not* installed system-wide here (`fc-list`), and
  `test_fonts_need_no_system_install` checks that a fresh process without vidgen does not know
  them while one importing `vidgen.helpers` does. Inter IS installed system-wide here:
  registration still succeeds for its bundled files (tested).
- Storyboards of examples/minimal viewed: `editorial` (serif title/headings/chart titles/code
  window title/end-card title, serif quote with serif mark, JetBrains Mono listing),
  `light` (serif headings, sans quote), default and `vertical` (all Inter, JetBrains Mono
  listing; wrapping in portrait unchanged in character). Looks tasteful; the serif headings in
  bold read well on the paper backgrounds.
- `vidgen lint`: default 2 warnings, `light` 2, `editorial` 2 (the same pre-existing
  `bar_chart` caption `min_font` and `image` caption `safe_area`), `vertical` 1 (`safe_area`),
  `examples/custom_scene` 0. `vidgen validate examples/kphi3` ok (its own `font: Inter`).

Files
- New: `src/vidgen/fonts.py`, `src/vidgen/data/fonts/**` (8 TTF + 3 OFL.txt),
  `THIRD_PARTY_NOTICES.md`, `tests/test_fonts.py` (19 tests, 2 render).
- Changed: `presets.py`, `theme.py`, `config.py`, `api.py`, `helpers.py`, `regions.py`,
  `layout.py`, `sheets.py`, `themelist.py`, `render/worker.py`, `render/fingerprint.py`,
  scenes `title.py`, `bullets.py`, `bar_chart.py`, `line_chart.py`, `end_card.py`, `code.py`,
  `quote.py`; `pyproject.toml`; tests `test_scales.py` (font-role semantics), `test_regions.py`
  (mono measured with JetBrains Mono NL); README (install: fonts bundled, feature line,
  troubleshooting), docs/CONFIG.md (theme keys, new "Fonts" section with the role table,
  presets note, `quote.mark_font`, `code.font`, list-themes JSON), docs/EXTENDING.md
  (`fit_text(font=)`, theme font attributes, preset font args), DESIGN.md (§2, §4, §15 note,
  §20 note, new §21), tasklist.md.

Public interfaces added/changed
- Config: `theme.font_serif`, `theme.font_mono`, `theme.fonts` (additive).
- `vidgen.api.register_theme_preset(..., font_serif=None, font_mono=None)`; `fit_text(...,
  font=None)` (also `fit_text_sized`). `Theme.font_serif`, `Theme.font_mono`; `Theme.fonts` now
  includes config roles; `ThemePreset.font_serif/.font_mono`; `presets.DEFAULT_FONT_SERIF/MONO`.
- Params: `code.font` default `None` (= role `code`), `quote.mark_font` default `None` (= role
  `quote_mark`).
- `vidgen.fonts` module (internal helpers listed above). list-themes JSON entries: `font_serif`,
  `font_mono`, `font_roles`.

Decisions / deviations
- **`font_for` precedence changed from Step 17** (DESIGN §21): a `font` written in `video.yaml`
  is the sans family and no longer overrides every role. With the old rule `examples/minimal`'s
  base `font: Inter` would have cancelled the serif headings of its light/editorial variants and
  turned code listings into Inter. No output changed for anyone before this step (no preset set
  roles). Test in `test_scales.py` updated.
- Roles may name a token (`sans`, `serif`, `mono`) rather than only a family, so `font_serif:
  Georgia` in the config also changes a preset's serif headings.
- **JetBrains Mono NL** (no ligatures) instead of JetBrains Mono: a teaching video should show
  `!=`, `->`, `>=` as typed. Pango family name is `JetBrains Mono NL`.
- npm `jetbrains-mono` 1.0.6 has font version 2.242 (current upstream 2.304; GitHub releases are
  blocked here). Fontsource 5.x only has unicode-range-split WOFF2 subsets, so it was used only
  for the licence text.
- Weights: Regular + Bold for all, Italic for Inter and Source Serif 4 (Markup `<i>` in user
  text); no Medium/SemiBold — built-ins only use NORMAL/BOLD. Pango synthesises other weights
  from the nearest face (or an installed copy).
- Registration at import time of `vidgen.helpers`/`vidgen.regions` (a side effect) because
  Pango freezes its font map at the first layout; in-process users (tests, notebooks) need it
  before any vidgen text.
- `Source Serif 4` has an ~8 % smaller cap height per point than Inter; serif headings are a bit
  smaller at the same size token. Left as is (headings are far above `min_font`).

Known gaps / TODOs
- Windows/macOS registration (`AddFontResourceEx` private / CoreText process scope via
  manimpango) is not exercised here (Linux only). If a Windows Pango build ignores private GDI
  fonts, text falls back to an installed font of that name; worth a check on the user's machine
  (`vidgen storyboard examples/minimal --variant editorial`: titles must be serif).
- Manim's text SVG cache (`build/.../media/texts/<scene>`) is keyed by text+font name: an SVG
  made before a font became available is reused. Not a problem for fresh projects (the bundled
  families are new names); deleting `build/` fixes any stale case.
- `T()`/`MT()`/`self.text` take `font=` but no `role=` shortcut; extension authors call
  `self.theme.font_for(role)`. Could be added in the Step 22 API review.
- kphi3 scenes are unchanged (own scenes, `font: Inter`).

How to test: `/home/claude/venv/bin/python -m pytest -q` (681 passed, 1 skipped). Step only:
`pytest tests/test_fonts.py`. Manual: `vidgen storyboard examples/minimal --variant editorial`,
`vidgen list-themes examples/minimal --swatches build/themes.png`, `fc-list | grep -i "source
serif"` (empty: the bundled copy is what renders).


## Step 19 — Icons: mechanism + seed set
What was built
- **Vendored icons** (package data `src/vidgen/data/icons/`): 40 Lucide SVGs (npm `lucide-static`
  1.52.0, ISC; files unmodified), `lucide/LICENSE` (ISC + Feather MIT notice) and `manifest.json`
  (`sources` + `icons: [{name, category, tags, source}]`; tags from Lucide's `tags.json` plus a
  few `extra_tags`). Seed set, 5 per category:
  | category | icons |
  |---|---|
  | tech | cpu, server, cloud, code, smartphone |
  | data | database, chart-column, chart-line, chart-pie, chart-scatter |
  | science | atom, flask-conical, microscope, dna, zap |
  | business | briefcase, trending-up, target, handshake, dollar-sign |
  | people | user, users, user-check, message-circle, brain |
  | ui (arrows/interface) | arrow-right, refresh-cw, check, x, search |
  | nature | leaf, sun, droplet, mountain, tree-pine |
  | education | book-open, graduation-cap, lightbulb, pencil, presentation |
- **`tools/vendor_icons.py` + `tools/icon_set.json`** (not shipped): re-vendors from the list
  (`npm pack lucide-static@<version>` into a temp dir, or `--package-dir DIR`), validates
  names/categories/version/`extra_tags`, removes unlisted SVGs, writes the manifest. Step 20:
  add names to `icon_set.json` (and `extra_tags` where Lucide's tags miss the obvious word), run
  `python tools/vendor_icons.py`.
- **Registry** `src/vidgen/icons.py` (no manim): built-ins + project `assets/icons/<name>.svg`
  (adds or overrides by name) with optional `assets/icons/icons.json` (category, tags);
  `search_icons` (name > tag > category ranking), `find_icon` with did-you-mean + "matching
  tags" suggestions. `vidgen validate` reports a broken project icon folder (`assets/icons: ...`).
- **`icon()` / `Icon`** (`src/vidgen/icon_mobject.py`, exported by `vidgen.api`): `icon(name,
  size="body", color="text", stroke_width=None, *, height=None, theme=None)`. Box = the SVG
  viewBox (invisible first submobject), size tokens/points → `points * 0.0208` units (1.5 em),
  `height=` in units; recoloured by theme token/hex (`color=None` keeps a project SVG's own
  colours, `currentColor` → `text`); SVG stroke widths converted to Manim units for the size;
  `Icon.scale()` scales strokes by default; round caps/joins kept.
- **`IconName`** param type (`vidgen.api`): checked against the project's icons in validate and at
  scene construction; `list-scenes` type `icon`; `vidgen schema` gives an `enum` of icon names.
- **`vidgen list-icons [PROJECT] [--search TEXT] [--category NAME] [--sheet PNG] [--json]`**
  (`src/vidgen/iconlist.py`): text listing, Step 8 JSON envelope, and a labelled 1280 px contact
  sheet drawn with the same `build_icon` + Manim Cairo camera (paginated like storyboard sheets).
- **Layout dump / lint**: an icon is one object of kind `icon` with `icon: <name>` (not a pile of
  paths); lint describes it as `icon 'x'`, finding objects gain `icon`, `lint_ignore` `object`
  matches icon names.
- Example: `examples/custom_scene` has a project icon `assets/icons/bicycle.svg` (+ `icons.json`)
  shown left of the ratio caption by `gear_pair` (new param `icon: IconName | None = "bicycle"`),
  and a `vidgen list-icons ... --sheet` usage line.

Verification (looked at every image with Read)
- Rendered all 40 icons through Manim's Cairo camera at 854x480 and 1920x1080 (4 sizes from 0.25
  to 1.6 units plus one icon scaled 2.5x after creation): identical proportions at both
  resolutions, strokes 2/24 of the box, round caps, filled dots of `chart-scatter` correct, the
  scaled icon's strokes thicken with it. Test `test_icon_strokes_are_resolution_independent`
  pins the ink share at 480x270 and 1920x1080 (equal within 0.3 %).
- Storyboards of a scratch project (all 40 icons in a grid + a scaled `GrowFromCenter`/`Write`
  beat) at preview 16:9, final 1080p, `--variant vertical` and `--variant light`
  (`light_academic`): crisp, theme-coloured on dark and light backgrounds. `vidgen lint` there:
  no finding involves an icon (only my test labels at theme `small`, and their overlaps in 9:16).
  The invisible box never shows during `Write`/`DrawBorderThenFill`/`Create`/`FadeIn`/
  `GrowFromCenter`/`SpinInFromNothing` (checked at 40 % progress).
- `examples/custom_scene` storyboard (`pair`): bicycle icon in `highlight` next to the caption;
  layout dump has one `icon` object `bicycle`; `vidgen lint examples/custom_scene`: 0 findings.
- `vidgen list-icons --sheet` sheet viewed: 5 rows of 8, names and categories legible.
- Wheel built locally: 40 SVGs + manifest + LICENSE included; `tools/` not shipped.

Files
- New: `src/vidgen/icons.py`, `src/vidgen/icon_mobject.py`, `src/vidgen/iconlist.py`,
  `src/vidgen/data/icons/**` (manifest, 40 SVG, LICENSE), `tools/vendor_icons.py`,
  `tools/icon_set.json`, `tests/test_icons.py` (36 tests, 4 render),
  `examples/custom_scene/assets/icons/bicycle.svg` + `icons.json`.
- Changed: `api.py` (exports), `scene.py` (`IconName`, `ThemeToken` kind `icon`), `schema.py`
  (icon enum), `cli.py` (`list-icons`, icon check in `project_problems`), `jsonout.py`
  (`list_icons_document`), `introspect.py` (kind `icon`), `lint/layout_rules.py` (`describe`),
  `lint/findings.py` (`icon` key), `lint/run.py` (ignore matches icon names),
  `render/fingerprint.py` (vendored icons in the source digest; `iconlist.py` not a render
  input), `pyproject.toml` (package data), `examples/custom_scene/{video.yaml,extensions/gears.py}`,
  `tests/test_lint.py` (finding object has `icon`), README, docs/CONFIG.md ("Icons",
  `vidgen list-icons`, JSON shape, layout dump kind, lint object key), docs/EXTENDING.md
  (`IconName`, "Icons"), DESIGN.md (§2, §6.4, §8, §15 note, new §22), THIRD_PARTY_NOTICES.md,
  tasklist.md.

Public interfaces added/changed
- `vidgen.api`: `icon`, `Icon`, `IconName` (additive). CLI: `vidgen list-icons` (JSON command
  `list-icons`, envelope v1).
- Layout dump: kind `icon` + key `icon` (additive). Lint finding objects: key `icon` (added
  within JSON version 1).
- `vidgen.icons` (`IconInfo`, `CATEGORIES`, `builtin_icons`, `builtin_sources`, `project_icons`,
  `available_icons(root)`, `active_icons`, `search_icons`, `find_icon`, `unknown_icon_message`,
  `categories`), `vidgen.icon_mobject` (`build_icon`, `icon_height`, `ICON_UNITS_PER_POINT`),
  `vidgen.iconlist` — internal.

Decisions / deviations
- **Size semantics**: `size` follows text (theme token or points) so an icon next to text of
  token X uses `size=X`; box = 1.5 em (`0.0208` units/pt), matching the 24 px icon / 16 px text
  pairing of UI kits (body icon drawing ≈ 1.7x body cap height, tested). Manim units via
  `height=`. `stroke_width` is in the SVG's own units (Lucide users know "1.5" / "2").
- **Box includes the viewBox padding** (invisible rect): consistent alignment and sizes across
  icons for grids/bullets (Step 21); the layout dump/lint ignore it (opacity 0) and measure the
  drawing.
- **Prepared SVG copies in a per-process temp dir**: Manim's `SVGMobject` writes `<stem>_.svg`
  beside the source, which would race between `--jobs` workers and fail for a read-only
  site-packages; also fixes two Manim parsing quirks (`currentColor` → black, `stroke="none"` →
  white stroke).
- **`Icon.scale` scales strokes by default**: otherwise `place()` (which scales) would leave
  hairlines on big icons and blobs on small ones.
- `IconName` reuses the `ThemeToken` marker (`x-vidgen-theme: icon`) instead of a new schema
  key: one mechanism for "names resolved in the project" in describe/schema.
- `list-icons` finds the project root without validating the config (an agent fixing a broken
  `video.yaml` still needs the icon list); `--sheet` added (cheap, reuses sheet fonts/helpers).
- Category ids: `ui` for "arrows/UI". Lucide's own categories are not in the npm package; ours
  are curated in `tools/icon_set.json`.

Known gaps / TODOs
- Step 20: expand `tools/icon_set.json` to ~200 (25 per category) and re-run the tool; maybe a
  manifest `aliases` field (Lucide renamed icons, e.g. `bar-chart` → `chart-column`; search by
  old names would help).
- Step 21: `icon:` on bullets/title/end_card and `icon_grid` — use `IconName` params and
  `icon(name, size=<the text's size token>)`; a `grid_shape(n)` helper is still missing (Step 15
  note).
- Project SVGs: only the root's `stroke-linecap`/`-linejoin` are honoured (per-element ones are
  ignored); gradients/patterns/text in SVGs are whatever Manim's SVG parser does (documented:
  use simple stroke/fill icons).
- The contact sheet always draws dark-on-white; a `--theme` option could preview icons in a
  project's colours.

How to test: `/home/claude/venv/bin/python -m pytest -q` (717 passed, 1 skipped). Step only:
`pytest tests/test_icons.py`. Manual: `vidgen list-icons --search chart --sheet build/icons.png`,
`vidgen list-icons examples/custom_scene --json`, `vidgen storyboard examples/custom_scene --scene
pair`, `vidgen lint examples/custom_scene`.

## Step 20 — Icons: curated expansion
What was built
- **200 vendored icons** (Lucide `lucide-static` 1.52.0, files unmodified), 25 per category:
  | category | icons |
  |---|---|
  | tech | cpu, server, cloud, code, smartphone, laptop, monitor, terminal, wifi, lock, shield-check, key-round, bug, git-branch, hard-drive, memory-stick, router, network, globe, bot, brain-circuit, binary, keyboard, battery-full, plug |
  | data | database, chart-column, chart-line, chart-pie, chart-scatter, chart-area, chart-bar, chart-spline, chart-column-stacked, chart-candlestick, chart-network, chart-gantt, table, file-spreadsheet, funnel, sigma, percent, gauge, activity, layers, folder, calculator, variable, workflow, grid-3x3 |
  | science | atom, flask-conical, flask-round, test-tube, microscope, dna, zap, magnet, telescope, orbit, rocket, satellite, thermometer, radiation, biohazard, flame, pill, syringe, stethoscope, pi, infinity, radical, square-function, axis-3d, virus |
  | business | briefcase, trending-up, trending-down, target, handshake, dollar-sign, coins, wallet, credit-card, piggy-bank, banknote, receipt, shopping-cart, store, building-complex, factory, landmark, award, trophy, megaphone, scale, package, truck, flag, clipboard-list |
  | people | user, users, user-check, user-plus, user-x, message-circle, messages-square, brain, baby, person-standing, accessibility, heart, heart-pulse, hand, hand-heart, thumbs-up, thumbs-down, face-slightly-smiling, face-slightly-frowning, eye, ear, mail, phone, id-card, footprints |
  | ui | arrow-right, arrow-left, arrow-up, arrow-down, arrow-up-right, arrow-left-right, refresh-cw, check, x, plus, search, settings, play, pause, circle-check, triangle-alert, info, circle-question-mark, bell, calendar, clock, house, star, download, link |
  | nature | leaf, sun, droplet, mountain, tree-pine, tree-deciduous, moon, cloud-rain, cloud-lightning, cloud-sun, snowflake, wind, rainbow, sprout, flower, earth, waves-horizontal, sunrise, tornado, bird, fish, paw-print, rabbit, shell, recycle |
  | education | book-open, book, book-bookmark, library, graduation-cap, lightbulb, pencil, notebook-pen, presentation, school, backpack, ruler, eraser, highlighter, file-text, clipboard-check, list-checks, puzzle, languages, palette, music, shapes, scroll, hourglass, quote |
- **Tags**: Lucide's tags + explainer-oriented `extra_tags` for every icon (concept words: money,
  growth, security, speed, AI, team, risk, process, ...). `list-icons --search money` → banknote,
  coins, credit-card, dollar-sign...; `AI` → brain-circuit, brain; `growth` → trending-up first.
- **Aliases** (manifest key `aliases`): 36 in all — 24 Lucide old names of renamed icons derived
  by the tool (`home`→house, `pie-chart`/`line-chart`/`area-chart`/`scatter-chart`,
  `alert-triangle`, `help-circle`/`circle-help`, `filter`→funnel, `smile`, `frown`,
  `building-2`, `book-marked`, `waves`, `grid`, ...) plus curated synonyms in
  `tools/icon_set.json` `aliases` (`bar-chart`→chart-column, `dollar`, `warning`, `idea`,
  `gear`, `question`, `person`, `team`, `growth`, `ai`, `money`, `document`). `icon()`,
  `find_icon`, `IconName` validation and the schema `enum` accept them; `list-icons` shows
  `(alias: ...)` and JSON entries have `aliases`; search ranks an exact alias like a name prefix;
  did-you-mean considers aliases.
- **Catalogue** `docs/ICONS.md` generated by `iconlist.catalogue_markdown(manifest)` (written by
  `tools/vendor_icons.py`, new `--docs`), test keeps it in sync. Linked from README, CONFIG.md.
- **Vendor tool**: derives upstream aliases (package files without a `tags.json` entry that draw
  exactly like one vendored icon, ignoring the licence comment and `class`), validates curated
  aliases, rejects old names listed as icons; writes the catalogue.

Verification (looked at every image with Read)
- `vidgen list-icons --sheet` (3 pages, 200 icons): all icons crisp and recognisable, no stray
  fills, arcs/spirals/dots correct.
- Every icon compared with a reference rasteriser (cairosvg in a scratch folder, not a
  dependency) at 192 px: inked-pixel overlap >= 0.971 for all 200 (median 0.998); the eight
  lowest (eye, message-circle, rainbow, phone, gauge, shell, dna, axis-3d) inspected side by
  side: differences are anti-aliasing only. **No loader change and no icon dropped.** (Lucide
  1.52's `dna` is a diagonal helix with rungs — upstream design, faithful but less iconic than
  the old one.)

Files
- Changed: `tools/icon_set.json`, `tools/vendor_icons.py`, `src/vidgen/data/icons/manifest.json`
  + 160 new SVGs in `src/vidgen/data/icons/lucide/`, `src/vidgen/icons.py`, `src/vidgen/iconlist.py`,
  `src/vidgen/scene.py`, `src/vidgen/schema.py`, `tests/test_icons.py` (47 tests: set/categories,
  concept search, aliases, project alias takeover, all-icons load, 6 renders, docs sync, vendor
  tool aliases), README, docs/CONFIG.md, docs/EXTENDING.md, DESIGN.md (§22 note, tree, new §23),
  THIRD_PARTY_NOTICES.md, tasklist.md. New: `docs/ICONS.md`.

Public interfaces added/changed
- `vidgen.api` unchanged; `icon(name)` and `IconName` now also accept aliases (additive).
- `vidgen.icons` (internal): `IconInfo.aliases`, `builtin_aliases()`, `resolve_icon()`,
  `icon_names()`; `vidgen.iconlist.catalogue_markdown()`.
- Manifest entries gain `aliases`; `list-icons --json` icon entries gain `aliases` (additive,
  version 1).

Decisions / deviations
- `bar-chart`: Lucide's own alias points at `chart-no-axes-column-increasing` (not vendored, a
  near-duplicate of `chart-column`), so a curated alias maps it to `chart-column`.
- Aliases come from identical drawings, not from a Lucide alias list (none in `lucide-static`);
  all 264 alias files of 1.52.0 draw exactly like a current icon; `clock` and `clock-4` draw
  alike, so the tool skips an old name that matches two vendored icons.
- `Icon.icon_name` is the resolved name (layout dump/lint report `house` for `icon("home")`).
- No brand icons; `hexagon` (tagged node.js/logo) replaced by `virus`.

Known gaps / TODOs
- Substring search: short terms match inside words (`ai` also finds `rain`, `email`), ranked
  after the real matches; a word-boundary match could rank better (Step 22 review).
- `list-icons --sheet` still draws dark on white (no `--theme`).
- Step 21: `icon:` on bullets/title/end_card and `icon_grid` (unchanged plan).

How to test: `/home/claude/venv/bin/python -m pytest -q` (728 passed, 1 skipped). Step only:
`pytest tests/test_icons.py`. Manual: `vidgen list-icons --sheet build/icons.png` (3 pages),
`vidgen list-icons --search money`, re-vendor: `python tools/vendor_icons.py` (npm) or
`--package-dir DIR`.

## Step 21 — Icons in built-in scenes
What was built
- **`grid_shape(n, aspect=None, *, cell_aspect=1.0, max_cols=None) -> (rows, cols)`** in
  `vidgen/regions.py`, exported by `vidgen.api` (the helper Step 15 left out): picks the shape
  whose cells (at `cell_aspect`) come out largest in an area of `aspect` (number, region name or
  `Region`; default the safe area); near-ties go to fewer empty cells, then fewer rows.
- **`bullets`**: items are a string or `{text, icon}` (`BulletItem`; plain strings still work
  and mix with icon items). Icons form a column next to the text, sized to the item text,
  centred on the first line's capitals; they replace the bullet, or stand between number and
  text when `numbered`; a plain item in a list with icons shows its bullet centred in the icon
  column. Colour `marker_color`; `dim_previous` fades icons with their row.
- **`title`**: `icon`, `icon_color` (`primary`), `icon_position: above | left` (`left` → `above`
  in portrait). **`end_card`**: `icon`, `icon_color` (icon between logo and title; an icon alone
  is a valid card).
- **`icon_grid`** (new built-in, `src/vidgen/scenes/icon_grid.py`): items `{icon, label,
  sublabel?}` (1–16), optional `heading`, `columns`, `reveal: per_beat | all`, `groups` (reveal
  steps by index or label), `highlight` (last step: others dim, the item grows in
  `highlight_color`), `badge` (soft disc behind each icon), `icon_color: palette | color`,
  label/sublabel/heading colours and sizes. Shape from `grid_shape` tried at five cell
  proportions, best resulting layout wins (labels at the requested size, then largest icons);
  labels share one size, shrink (not below `readable_size()`) for room or a long word; rows
  spread over spare height, short last row centred, labels on common baselines.
- **Icons scaled with their group**: `shrink_to_fit` and `place` now also scale the strokes of
  icons inside the group they scale (`icon_mobject.scale_icon_strokes`).
- `examples/minimal`: new `feedback` icon_grid scene (palette colours, highlight), icons on the
  numbered `steps` bullets.

Verification (looked at every sheet with Read)
- Scratch project (11 scenes: title above/left, bullets with icons/mixed/numbered, icon_grid
  with 2, 3, 4, 6 (sublabels, highlight), 9 (no badge, groups), 12 (sublabels, palette, reveal
  all) items, end_card) storyboarded at preview 16:9, `vertical`, `light` (light_academic) and
  `large` scale. Fixed along the way: labels of different sizes when one long word was scaled
  alone (now all labels shrink together), sublabels at uneven heights (baseline placement),
  2 x 6 grids with tiny text at the `large` scale (now several shapes are planned and
  compared), dimmed `dim` sublabels at 1.96:1 on light presets (dimmed opacity 0.55), and
  cells dissolved by part animations (cells are added whole before their entrance).
- `vidgen lint` of that project: no layout finding except the deliberate stress case (12 items
  with "Thermodynamics" in 9:16: min_font on that label); the rest are timing findings of its
  two-word beats.
- `examples/minimal` lint, before → after: 16:9 2 warnings → 2 (same: `sizes` caption
  min_font, `picture` caption safe_area); vertical 1 → 1; light 2 → 2. `--scene feedback
  --scene steps` with the contrast, editorial, neutral, pastel and neon variants: 0 findings.
  Storyboards of `feedback` and `steps` checked in 16:9, vertical and light.

Files
- New: `src/vidgen/scenes/icon_grid.py`, `tests/test_icon_scenes.py` (50 tests, 19 render).
- Changed: `src/vidgen/regions.py` (`grid_shape`; `place` scales icon strokes), `api.py`,
  `icon_mobject.py` (`scale_icon_strokes`), `layout.py` (`shrink_to_fit` scales icon strokes),
  `scenes/__init__.py`, `scenes/bullets.py`, `scenes/title.py`, `scenes/end_card.py`,
  `examples/minimal/video.yaml`, `tests/test_builtin_scenes.py` (icon_grid in BUILTINS/SAMPLES,
  icons in samples), `tests/test_json_output.py` (bullets items type), docs/CONFIG.md (Icons
  intro, `title`, `bullets`, new `icon_grid`, `end_card`), docs/EXTENDING.md (`grid_shape`,
  icon strokes in `place`/`shrink_to_fit`, animating icons inside groups), README, DESIGN.md
  (§6.4, new §24), tasklist.md.

Public interfaces added/changed
- `vidgen.api.grid_shape` (new). Built-in scene type `icon_grid` (new).
- `bullets.items`: `list[BulletItem]` (strings still accepted; `list-scenes` shows
  `list[BulletItem]` with nested `text`, `icon`; JSON Schema `anyOf` string | object).
  `title`: `icon`, `icon_color`, `icon_position`; `end_card`: `icon`, `icon_color`, and its
  "at least one of" message now names `icon`.
- `shrink_to_fit` / `place` scale strokes of icons inside a scaled group (other mobjects
  unchanged). `vidgen.icon_mobject.scale_icon_strokes` (internal).

Decisions / deviations
- `groups` and `highlight` refer to items by 0-based index (as `bar_chart.highlight`) or label.
- `bullets` icon items use one `BulletItem` model with a "string → {text}" pre-validator and a
  custom JSON Schema instead of `str | BulletItem`: errors read `items.1.icon: unknown icon...`
  instead of two union-branch errors per item.
- `dim_previous` uses `fade()` (multiplies opacities) instead of `set_opacity()`, which would
  have shown an icon's invisible box and filled its open paths; text looks identical.
- `icon_grid` dims to 0.55 (bullets keep 0.45): its sublabels are `dim` already.
- No list-wide `icon` on bullets (per-item only), no icon for `text_card`/`quote` (not asked).

Known gaps / TODOs
- `icon_grid` with 12 items and sublabels in 16:9 draws small icons (~0.6 units): the labels
  keep their readable size first. Long single words in narrow 9:16 columns can still go below
  the lint minimum (the stress case above); shorter labels or `columns` fix it.
- `list-scenes` prints `items: list[BulletItem]` although plain strings are accepted (the
  field doc says so); a describe hook for "also accepts" could make it exact (Step 22).

How to test: `/home/claude/venv/bin/python -m pytest -q` (782 passed, 1 skipped). Step only:
`pytest tests/test_icon_scenes.py`. Manual: `vidgen storyboard examples/minimal --scene
feedback --scene steps [--variant vertical|light]`, `vidgen lint examples/minimal [--variant
vertical]`, `vidgen schema --scene icon_grid`.

## Step 22 — Review 1
Independent review of Steps 8–21: storyboard + lint of every example configuration, the
"left for Step 22" gaps of earlier handoffs, an API/CLI consistency pass, docs vs behaviour, test
runtime, and an install check from a wheel.

Lint status (preview; `vidgen lint` + `vidgen storyboard`, every sheet opened)
| example / variant | before | after |
|---|---|---|
| minimal (default `dark_tech`) | 2 warnings (`sizes` caption `min_font`, `picture` caption `safe_area`) | 0 |
| minimal `vertical` | 1 (`safe_area`) | 0 |
| minimal `light`, `editorial` | 2 each (same two) | 0 |
| minimal `contrast`, `neon` | 1 each (`safe_area`) | 0 |
| minimal `neutral`, `pastel` | 2 each (Step 17/21 numbers) | 0 |
| custom_scene, `vertical` | 0, 0 | 0, 0 |
| kphi3 | 1 error + 32 warnings (+2 theme-contrast warnings) | 0 (5 commented `lint_ignore`s) |

Findings and fixes
1. **Built-in captions** (long-standing): `bar_chart`/`line_chart` captions used the fixed
   `small` size (below lint's `min_font`) → new params `caption_size` (`caption`) and
   `caption_color` (`dim`). `image` with `fit: cover` drew its caption 12 px into the bottom
   margin → the caption sits on the bottom of the `caption` region (safe area), the band runs
   from the frame edge to just above it.
2. **9:16 built-ins** (Step 15 regions): `quote` (text, mark and author 1.25x in portrait,
   placed with `place`) and `equation` (formulas 1.25x in portrait, positioned from the safe
   area; new `caption_size`) were small blocks in an empty tall frame. 16:9 sheets are
   unchanged apart from the larger chart captions. Left as they are, because their 9:16 sheets
   read well since the `auto` scale: `title`, `end_card`, `text_card`, chart bodies (Step 30).
3. **kphi3** (fixed in its extensions, documented in its README/REGRESSION.md): `dim`
   `#6B7280` → `#838B98` (decided: 3.9:1 failed WCAG AA on every dim label; 18 contrast warnings
   and 2 theme warnings; a slightly lighter grey is not a material change); `method` beat 5
   column labels keep 22 pt when the diagram zooms out (was the only lint **error**, 7.6 px);
   `loss` ticks/model names 16 → 20 pt, footnote 22 pt inside the safe area, panels 0.2 up;
   `setup` decoder labels and dataset subtitle 20 → 22 pt; `equivalence` token column 0.1 right
   and its label clamped to the safe area. `lint_ignore` (with comments in `video.yaml`): four
   `dead_air` holds (the original pacing) and the rotated `H = length` (lint measures rotated
   glyphs sideways: a lint limitation, routed to Step 37).
4. **Lint**: `vidgen lint` now also prints the theme-contrast warnings `vidgen validate` gives
   (Step 16/17 gap; warnings, not findings; skipped with `--rule` other than `contrast` or
   `contrast: {severity: off}`). The same text repeated in copies of a component (two decoder
   boxes' "Attention") was two identical findings → merged like grouped findings.
5. **API gaps** (Steps 15/18/21): `role=` on `T`, `MT`, `self.text`/`self.markup`, `fit_text`,
   `readable_text` (`font=` still wins); `region(name, area)` accepts a region name as `area`;
   `SceneParams.also_accepts` so `list-scenes` shows `items: list[str | BulletItem]`;
   `register_theme_defaults` rejects non-identifier token names (YAML could never override
   them; Step 7 gap) and malformed hex colours.
6. **Icon search** (Step 20 gap): whole words of names/aliases/tags rank above substrings
   (`ai`: brain-circuit, bot before cloud-rain, mail; `art`: palette before chart-*).
7. **CLI consistency**: checked every `--json` command (validate, list-scenes, list-themes,
   list-icons, schema, render, storyboard, lint) for the error envelope / exit codes 1 and 2 —
   consistent. Added `list-themes --sheet` as an alias of `--swatches` (as in `list-icons`).
   `tts` still has no `--json` (routed to Step 59).
8. **API review, no change needed**: every `VIDGEN_NAMES` entry is in `__all__` and has a
   docstring; size/colour arguments take tokens or literals everywhere (`icon(name, size,
   color)` mirrors `T(s, size, color)`; Manim units only via `height=`); `place`/`grid`/
   `grid_shape` take a region name or `Region`. No renames, so no aliases were needed.
9. **Docs**: CONFIG.md lint example output was stale (10 scenes, 7 warnings) → generic; new
   lint "Theme contrast" paragraph; search ranking, chart/equation caption params, quote/equation
   portrait growth, `--sheet` alias; EXTENDING.md `role=`, `region(name, "body")`,
   `also_accepts`; README "Working on vidgen" (test commands). DESIGN §6.4, §9, §22 note, new
   §25.
10. **Tests**: +12 (794 passed, 1 skipped). New marker `slow` on the 18 slowest render tests:
    full suite 228 s on this 2-CPU box, `-m "not slow"` 65 s, `-m "not render"` 23 s.
11. **Install check**: `pip wheel . --no-deps` (1.25 MB: 11 font files, 200 SVGs + LICENSE,
    templates; no `tools/`) → fresh venv, `pip install` from PyPI → `vidgen --version`, `init`
    (non-ASCII folder), `validate`, `render --preview`, and with a `light_academic` variant
    `storyboard` + `lint` (0 findings): serif heading (Source Serif 4, not installed
    system-wide) and the `pencil` icon rendered from `site-packages/vidgen/data`.

Files
- Code: `helpers.py`, `scene.py`, `layout.py`, `regions.py`, `describe.py`, `theme.py`,
  `icons.py`, `cli.py`, `lint/run.py`, scenes `quote.py`, `equation.py`, `image.py`,
  `bar_chart.py`, `line_chart.py`, `bullets.py`.
- Examples: `examples/kphi3/{video.yaml, extensions/common.py, s3_equivalence.py, s4_method.py,
  s5_setup.py, s7_loss.py, README.md, REGRESSION.md}`, `examples/custom_scene/extensions/gears.py`
  (`role="heading"` usage).
- Tests: `test_regions.py` (roles, region by name, chart/quote in the safe area, cover caption,
  quote growth), `test_lint.py` (theme warnings, same-text merge), `test_icons.py` (ranking),
  `test_theme.py`, `test_extensions.py`, `test_scales.py` (`--sheet`), `test_json_output.py`;
  `slow` markers in 12 test files; `pyproject.toml` (marker).
- Docs: README, docs/CONFIG.md, docs/EXTENDING.md, DESIGN.md, tasklist.md.

Public interfaces added/changed (all additive)
- `vidgen.api`: keyword `role=` on `T`, `MT`, `fit_text`, `readable_text`,
  `NarratedScene.text`/`markup`; `region(name, area: str | Region | None)`;
  `SceneParams.also_accepts` (ClassVar).
- Params: `bar_chart`/`line_chart` `caption_size`, `caption_color`; `equation` `caption_size`.
  `Quote.portrait_growth`, `Equation.portrait_growth` (class attributes, 1.25).
- `register_theme_defaults` raises for non-identifier names / malformed hex (was accepted).
- CLI: `list-themes --sheet` (alias). `vidgen lint` may print `warning: theme contrast: ...`.
- `list-scenes` / `--json` `type` of `bullets.items`: `list[str | BulletItem]` (was
  `list[BulletItem]`; a value change within JSON version 1, it is a display string).

Remaining issues (routed in tasklist.md)
- Step 30: chart titles into `header`, chart labels from size tokens (9:16 `bar_chart` value
  labels are scaled small to fit narrow slots).
- Step 32: a code size cap for portrait listings.
- Step 37: `icon_grid` in 9:16 leaves the lower third empty with few items; `list-icons
  --sheet` in project colours; lint text rotation.
- Step 59: `vidgen tts --json`; human `validate` stops at the first variant that does not load.
- Not routed (cosmetic): `minimal`'s `picture` 9:16 starts with the sun half cropped (the
  example's Ken Burns focus on a landscape image in a cover crop).

How to test: `/home/claude/venv/bin/python -m pytest -q` (794 passed, 1 skipped, ~4 min);
quick: `-m "not slow"` (~1 min) or `-m "not render"` (~20 s). Manual: `vidgen lint
examples/minimal [--variant vertical|light|contrast|editorial|neutral|pastel|neon]`, `vidgen
lint examples/custom_scene [--variant vertical]`, `vidgen lint examples/kphi3` (all 0
findings), `vidgen storyboard ...` likewise.

## Step 23 — Per-beat actions (framework + 3 actions)
What was built
- **YAML**: a beat may have `actions:`. Canonical form `{action: NAME, target: T, at: 0..1,
  until: BEAT, run_time: S, ...options}`; one shorthand `{NAME: TARGET, ...options}` (action name
  as the first key; `- dim: item2`, `- highlight: "bar:4K"` + `color: accent` on the next line).
  `target` is a name, a list, or a `*`/`?` pattern. `until` (a later beat of the scene) undoes
  `dim`/`highlight` when that beat starts. `config.ActionConfig`, `BeatConfig.actions`.
- **Framework** (`src/vidgen/actions.py`): `Target(names, mobject, entrance)`, `Action` /
  `ActionOptions` base classes, validation (`scene_actions`, `plan_actions`), and the
  `ActionRunner` that plays actions inside the beat. Action types are registered like scene
  types (`@action("name")` in `vidgen.registry`, built-in + extension layers, `override=True`).
- **Scene runtime** (`NarratedScene`): `target_patterns`, classmethod `target_names(params)`,
  `self.target(names, mobject, entrance=)`, `targets`, `find_targets`, `on_screen_parts`,
  `is_shown`, `entrance`; `narrate()` schedules the beat's actions; `wait_seconds` and an
  overridden `wait` play due actions inside waits; `play_steps` slots end at absolute times.
- **Built-in actions** (`src/vidgen/scenes/actions.py`, only `vidgen.api`): `reveal`, `dim`
  (`opacity` 0.45), `highlight` (`color` = `highlight` token; `style` `color` (default) | `box`
  | `underline` | `flash`, or a list).
- **Targets**: `bullets` — `heading`, `item<N>`, `item:<text>`; `bar_chart` — `title`,
  `bar<N>`, `bar:<label>` (bar + value + category label). Their reveal steps go through
  `self.entrance()`, so a target an action revealed early is not revealed again.
- **Checks**: `vidgen validate` (and the render pre-check, and the scene constructor) report
  unknown actions (did-you-mean), bad options (pydantic, theme tokens), `until` on `reveal`,
  missing/unknown targets with suggestions and the scene's target list, types without targets;
  `SceneConfig` checks `until` is a later beat. `vidgen schema` describes both forms (action
  enum, per-action options). `vidgen list-scenes` prints `targets:` per type and an actions
  section; `--json` gains `scene_types[].targets` and `actions`.
- `examples/minimal` `sizes` (bar_chart): beat 2 boxes `bar:4K` until beat 3, beat 3 dims the
  other bars and highlights `bar:Preview 480p` (shorthand); its `highlight` param was dropped
  for the actions (same story, shown through actions).

Verification
- Scratch project (bullets with early reveal, dim/highlight with `until`, `at: 0.5`, a pattern
  target, highlight of a not-yet-shown item; bar_chart per_beat with highlight, dim of a list,
  `[flash, box]`, underline) — `vidgen storyboard --per-beat 3` sheets read one by one: every
  action lands after the beat's own entrance, undo at the `until` beat, nothing overruns.
  `vidgen lint`: 0 findings. The EXTENDING example (custom `tick` action + `checklist` targets)
  storyboarded and linted (one `rushed_animation` from its short example beats, not actions).
- `examples/minimal`: `vidgen lint` 0 findings in every variant (default, vertical, light,
  contrast, editorial, neutral, pastel, neon); `examples/custom_scene` 0. `sizes` sheets checked
  in 16:9 (`--per-beat 3`), vertical and light.

Files
- New: `src/vidgen/actions.py`, `src/vidgen/scenes/actions.py`, `tests/test_actions.py` (27
  tests, 6 tiny renders).
- Changed: `config.py` (`ActionConfig`, `ACTION_KEYS`, `BeatConfig.actions`, `until` check),
  `registry.py` (action layer, shared `_add`, pair snapshot), `scene.py`, `api.py`, `cli.py`
  (validate, list-scenes), `describe.py`, `jsonout.py`, `schema.py`, `render/pipeline.py`,
  `scenes/__init__.py`, `scenes/bullets.py`, `scenes/bar_chart.py`; `examples/minimal/video.yaml`;
  docs/CONFIG.md (new "Beat actions", beats, bullets/bar_chart targets, schema, list-scenes
  JSON), docs/EXTENDING.md (§8 targets and custom actions, tested), README, DESIGN.md (§2, §6.4,
  new §26), tasklist.md.

Public interfaces added/changed
- `vidgen.api`: `action`, `Action`, `ActionOptions`, `Target`; `NarratedScene.target_patterns`,
  `target_names`, `target`, `targets`, `find_targets`, `on_screen_parts`, `is_shown`,
  `entrance`; `NarratedScene.wait` now also plays due actions (unchanged without actions).
- Config: `beats[].actions` (additive). `vidgen.registry`: `ActionType`, `register_action`,
  `action`, `find_action`, `action_names`, `all_actions`, `unknown_action_message`;
  `snapshot()` returns a pair (opaque before too).
- JSON: `list-scenes` `scene_types[].targets`, top-level `actions` (added within version 1).
- `schema.config_schema` / `scene_schema` take `actions=None` (default: registered ones).

Decisions / deviations
- **Actions run in waits, never in the scene's own `play`**: no two animations fight over one
  mobject, and "at the start of the beat" means right after the beat's entrance step. Run time
  is cut to end within `d + pad` (whole frames; `requested` recorded for `rushed_animation`);
  no time at all → applied without animation + warning.
- **`reveal` of a shown target is a no-op** (not an error: being shown depends on timing a
  static check cannot see); the scene's own step then skips it. `dim`/`highlight` on a hidden
  target reveal it first.
- **Shorthand with options**: the first-key rule makes `- highlight: x` + options natural; a
  sorted-keys dump (yaml.safe_dump) would break it, so `ActionConfig.resolved()` re-picks the
  one key that names a registered action.
- `dim`/`highlight` animate RGBA arrays (`Repaint`) of the parts on screen, not the target
  group (animating a group Manim never added would add it and draw its parts twice), and undo
  only their own channel, so they combine. A first `pulse` style (Indicate-like scaling) pushed
  bars through the axis; replaced by `flash` (colour there and back).
- `play_steps` uses absolute slot ends (absorbs an action that lengthened a wait); all existing
  timing tests unchanged.

Known gaps / TODOs (Step 24)
- Targets only on `bullets` and `bar_chart`; `zoom`/`transform` not yet. Images are not
  recoloured/dimmed by `Repaint` (vectorized mobjects only). `dim` compounds with `bullets`'
  `dim_previous`; `highlight` keeps a dimmed target dimmed. Box/underline sit around the whole
  target group (for a bar: bar + both labels, crossing the axis line).
- Validation cannot know whether the scene gives an action time (a custom scene that animates
  through the whole beat): that shows as the runtime warning.

How to test: `/home/claude/venv/bin/python -m pytest -q` (821 passed, 1 skipped, ~4 min). Step only: `pytest
tests/test_actions.py`. Manual: `vidgen validate examples/minimal`, `vidgen storyboard
examples/minimal --scene sizes --per-beat 3 [--variant vertical]`, `vidgen lint examples/minimal`,
`vidgen list-scenes`, `vidgen schema | jq '.["$defs"].ActionShorthand'`.

## Step 24 — Per-beat actions (zoom, transform, coverage)
What was built
- **`zoom`** action: the camera moves in on the targets (`scale`, or fitted with `padding`, at
  most 3x, never leaving the frame) and back. It is *temporary*: the zoom-out ends with the beat
  (with `until: B`, when `B` starts). A target that already fills the frame is not zoomed
  (warning). `NarratedScene` is now a `MovingCameraScene` (renders unchanged when the camera
  does not move; the frame is kept out of `scene.mobjects`).
- **`transform`** action: `transform: A` + `into: B` (`B` a target not on screen yet; `style`
  `auto|replace|shapes|tex|fade`). B stays on screen in its place, A is gone; scene steps that
  would reveal B or animate A skip them. Decision: `into` is a target, not a text literal.
- **Targets on every built-in** (`title`, `text_card`, `quote`, `equation` incl. new param
  `terms` → `term:<tex>`, `code` `line<N>`/`lines:<a-b>`, `image`, `line_chart` incl.
  `point:<name>@<x>`, `end_card`, `icon_grid`); every built-in builds its steps from
  `self.entrance()` (early reveals are not repeated; equation steps morph from the one on
  screen and are skipped once a later one is shown). Table scene type x targets x useful
  actions in docs/CONFIG.md "Beat actions", checked against `target_patterns` by a test.
- **Step 23 gaps fixed**: `dim`/`highlight` on images (pixel alpha / 30% tint); dimming never
  compounds (`dim` = at most `opacity` x the target's *full* opacity, captured at
  registration; `bullets` `dim_previous` and `icon_grid`'s highlight step use the same
  `dim_to`); a colour highlight brings a dimmed target to full opacity and its undo restores
  the dimming; a bar's highlight box stands on the axis (`Target.outline`).
- Framework: `Action.temporary`, `moves_camera`, `target_options`; runner schedules temporary
  undoings at the end of the return beat, reserves their time and shortens both alike in short
  beats; repeated plain names select the targets on screen. Layout dump `camera.zoom`; lint's
  `off_frame`/`safe_area` skip zoomed stills. `list-scenes` (+ JSON `temporary`,
  `target_options`), schema requires `into`.
- `examples/minimal` `math`: `terms: ["2ab"]`, beat 2 `transform: step2 → step3` (at 0.6; beat
  3's own morph is skipped), beat 3 `zoom: "term:2ab"`.

Verification
- Scratch project with every built-in type and actions (zoom with/without `until`, nested dim
  + dim_previous + highlight, transform in bullets and equation, image dim/tint, line_chart
  points without dots, code `lines:3-5` box, title/quote/end_card/text_card targets):
  `vidgen storyboard --per-beat 3` (16:9 and 9:16) read sheet by sheet; `vidgen lint` 0 errors
  (only dead-air/rushed warnings of its deliberately short beats).
- `examples/minimal`: `vidgen lint` 0 findings in all 8 variants; `math` and `sizes` sheets
  checked (`--per-beat 3`). `examples/custom_scene` 0, `examples/kphi3` 0 (5 ignored, as before).

Files
- New: `tests/test_actions_coverage.py` (41 tests incl. 30 tiny renders).
- Changed: `src/vidgen/actions.py`, `scene.py`, `scenes/actions.py` (Repaint images, dim_to,
  Zoom, MoveCamera, TransformAction), all built-in scene modules in `scenes/`, `introspect.py`,
  `lint/rules.py`, `lint/layout_rules.py`, `schema.py`, `describe.py`, `cli.py`;
  `tests/test_actions.py`, `tests/test_introspect.py`; `examples/minimal/video.yaml`;
  docs/CONFIG.md, docs/EXTENDING.md, README.md, DESIGN.md (§2, §6.4, new §27), tasklist.md.

Public interfaces added/changed
- Actions `zoom`, `transform`; `equation` param `terms`; targets on all built-ins.
- `vidgen.api` (compatible): `NarratedScene` base is `MovingCameraScene`;
  `NarratedScene.target(..., outline=)`; `Target.outline`, `Target.rest`,
  `Target.rest_opacity()`; `Action.temporary`, `Action.moves_camera`, `Action.target_options`.
- Behaviour: `dim`'s `opacity` is now relative to the target's full opacity (no compounding);
  `highlight` `style: color` undims while highlighted. Layout dump `camera.zoom`; JSON
  `actions[].temporary`, `actions[].target_options`.

Decisions / deviations
- `zoom` always comes back (no "stay zoomed" option): `until` extends it, and it is over when
  that beat starts — the same reading of `until` as Step 23 ("lasts until"), but undone *before*
  the beat rather than in its first wait, so the next beat's entrance is seen in full.
- `transform` into text literals not supported (no layout/style for a literal); scenes offer
  alternatives as targets.
- Lint skips `off_frame`/`safe_area` while zoomed instead of measuring against the zoomed view.

Known gaps / TODOs
- **Step 38 overlays**: mobjects in the scene move with the camera; a screen-fixed overlay must
  follow `camera.frame` or be composited outside Manim (DESIGN §27).
- A `dim` reverted after a scene's own later dimming (`dim_previous`) restores full opacity.
- `code`'s own highlight steps set absolute opacities (they override a `dim` action on lines);
  `lines:<a-b>` enumerates every range (fine for listings that fit on screen).
- Equation `term:` uses the first occurrence per step; terms must be complete TeX groups.
- Zoom on wide targets (a code line, a full-width title) barely zooms (warning); `scale:`
  forces it but may crop the target.

How to test: `/home/claude/venv/bin/python -m pytest -q` (862 passed, 1 skipped). Step only:
`pytest tests/test_actions_coverage.py tests/test_actions.py`. Manual: `vidgen storyboard
examples/minimal --scene math --per-beat 3 [--variant vertical]`, `vidgen lint examples/minimal`,
`vidgen list-scenes`.

## Step 25 — Scenes: `stat` and `chapter`
What was built
- **`stat`** (`src/vidgen/scenes/stat.py`): one big number that counts up (eases out, fades and
  rises into place), with `label`, `context` line, optional `icon` and `comparison`. Number
  format: `prefix`/`suffix` (number size), `unit` (smaller, on the baseline), `decimals` (auto:
  what value and comparison need, up to 2), `thousands`, `decimal_mark`, typographic minus;
  `count: false` fades in instead, `count_from` sets the start. `comparison` is a number or
  `{value, label, kind: versus|before, word, delta: difference|percent|none, better:
  higher|lower|neither}`: a chip with an arrow and the signed delta coloured `good_color`
  (`tertiary`) / `bad_color` (`accent`) / `neutral_color` (`dim`), then "vs 44% in 2023" (or
  "from ..." with `kind: before`, where the count starts at the old value — a before → after).
  Steps: (1) icon, number, label; (2) comparison and context. Targets `icon`, `value`, `label`,
  `comparison`, `context`.
- **`chapter`** (`src/vidgen/scenes/chapter.py`): section divider with optional `number` (int via
  `number_format` `{:02d}`, or text "Part II"), `title` (required; the chapter's name), optional
  `subtitle`, `icon`, accent `rule`. 16:9 with a number/icon: icon over number | vertical rule |
  left-aligned title block; otherwise (9:16, or title only) stacked and centred with a short rule.
  Entrance: the rule draws, number and title slide towards it from either side, subtitle rises.
  Two or more beats: subtitle in beat 2; one beat or silent (`duration`): all together. Targets
  `icon`, `number`, `title`, `subtitle`.
- `examples/minimal`: `part2` (silent numbered chapter with icon, before the charts) and
  `speedup` (stat 0.4 min counting down from 9.8 min in 4K, `delta: percent`, `better: lower`).

Verification (sheets opened with Read)
- Scratch project (3 chapters: numbered+icon+subtitle narrated, title-only silent, "Part II" with
  a long title; 3 stats: % with comparison and context, $ with icon and before/percent/lower,
  `ms` unit with `,` decimal mark and a bare-number comparison) storyboarded in 16:9
  (`--per-beat 3`), vertical, `light_academic`; lint 0 findings in 16:9, vertical, light, neon
  after one fix: the chip's tinted fill dropped the green delta to 4.0:1 on `light_academic` →
  the pill is filled with `surface`, stroked in the colour.
- `examples/minimal`: `vidgen lint` 0 findings in all 8 variants (default, vertical, light,
  contrast, editorial, neutral, pastel, neon); `part2`/`speedup` sheets checked in 16:9
  (`--per-beat 3`), vertical, editorial and contrast (large scale).

Files
- New: `src/vidgen/scenes/stat.py`, `src/vidgen/scenes/chapter.py`, `tests/test_stat_chapter.py`
  (58 tests, 36 tiny renders at 160x90 / 90x160).
- Changed: `src/vidgen/scenes/__init__.py`; `examples/minimal/video.yaml`; tests
  `test_builtin_scenes.py` (BUILTINS/SAMPLES), `test_actions_coverage.py` (SAMPLES, target
  names, early reveal), `test_extensions.py`, `test_registry.py` (type lists); docs/CONFIG.md
  (`stat`, `chapter` sections, targets table, Icons intro), README, DESIGN.md (new §28),
  tasklist.md.

Public interfaces added/changed
- Built-in scene types `stat` and `chapter` (params in docs/CONFIG.md). No `vidgen.api` change.
- Module helpers (internal, built-in module): `vidgen.scenes.stat.format_number`,
  `needed_decimals`; `Stat.change()`, `Stat.written()`, `Stat.start_value()`;
  `Chapter.Params.number_text()`.

Decisions / deviations
- Good/bad colours default to `tertiary`/`accent`: in every built-in preset those are the green
  and the red (no new semantic tokens; a project can point `good_color` at its own token).
- The change chip sits on `surface` (not a tint) to keep WCAG AA for the delta text on light
  presets. A comparison with `delta: none` shows only the words.
- `kind: before` is the before → after form: the number itself animates from the old value; the
  row says "from 9.8 min in 4K". `word` makes "vs"/"from" translatable for language variants.
- Numbers and chapter titles use the `heading` font role (serif in light_academic/editorial).
- `chapter` puts the subtitle in beat 2 only when there are ≥ 2 beats (a silent card or a single
  beat shows everything together instead of splitting a short beat into two rushed halves).
- **For Steps 39/49**: the chapter's name is `params.title` of a `chapter` scene (required,
  plain text); `params.number_text()` gives the number as shown (or `None`).

Known gaps / TODOs
- The count rebuilds the number `Text` every frame (fine for one number; same approach as
  `bar_chart` labels). Digits are proportional (Inter has no tabular figures through Manim's
  `Text`), so the centred number shifts a little while counting.
- `stat` has no layout with the icon beside the number, and no sparkline; `chapter` has no
  "progress" (e.g. 2 / 5) — Step 39's indicator could add it.
- A silent `chapter` of 3 s lasts 3.07 s at 15 fps (the 0.5 s outro rounds up to whole frames),
  as for the other built-ins.

How to test: `/home/claude/venv/bin/python -m pytest -q` (932 passed, 1 skipped). Step only: `pytest
tests/test_stat_chapter.py`. Manual: `vidgen storyboard examples/minimal --scene part2 --scene
speedup --per-beat 3 [--variant vertical|light]`, `vidgen lint examples/minimal [--variant ...]`,
`vidgen list-scenes`, `vidgen schema --scene stat`.

## Step 26 — Scenes: `comparison` and `table`
What was built
- **`comparison`** (`src/vidgen/scenes/comparison.py`): 2–3 columns, each `{heading, icon?,
  tone?, points}` (points: a string or `{text, icon}`, up to 8) on a `surface` card outlined in
  its tone; `tone: positive | negative | neutral` colours heading/icon/markers
  (`positive_color` `tertiary`, `negative_color` `accent`, `neutral_color` `primary`) and marks
  points with check / x icons / dots (`markers: false` hides them; a point's own icon wins).
  Optional scene `heading` (header region), `verdict` (bottom, `highlight` colour, last step),
  `vs` badge between the cards, `cards: false`. `reveal: columns` (one column per beat) | `rows`
  (headings, then the m-th point of every column per beat, rows on shared baselines) | `all`.
  Columns side by side in 16:9 and square, stacked in 9:16 (`Region.split`). One text size for
  all columns, reduced to the readable minimum before scaling (warning).
  Targets `heading`, `col<N>`, `col:<heading>`, `col<N>.item<M>`, `verdict`.
- **`table`** (`src/vidgen/scenes/table.py`): `header` + `rows` (str/number cells; bool/null
  rejected), `title`, `caption`, `align` (`auto`: numbers right), `number_format` (one or per
  column; default per-column decimals with thousands separators), `reveal: per_beat | all`,
  `zebra` stripes in `surface`, header rule in `header_color`, end rule with the last row.
  **Auto-fit**: natural widths, else water-filled widths with wrapping (headings at any space,
  body cells > 16 chars at spaces, numbers/short cells never), sizes from `size` down to the
  readable minimum (lint `min_font`); beyond that the table is scaled and a warning suggests
  splitting it. 9:16 rows get 1.4x vertical padding. Targets `title`, `header`, `row<N>`,
  `row:<first cell>`, `col<N>`, `col:<header>`, `cell<R>.<C>`, `caption`, with outlines spanning
  the full row / column / cell so `box` and `fill` highlights frame them edge to edge.
- **Framework**: target names may be dotted (`col2.item3`, `cell2.4`; `actions.TARGET_NAME`).
  New `highlight` style **`fill`**: a translucent (0.22) plate of the colour under the target
  (above backdrops at `z_index` -1 such as stripes and cards), undone by `until`.
- `examples/minimal`: `tradeoff` (comparison, vs badge, verdict, `highlight col1 box`) after
  `feedback`, `formats` (table with a number column and `highlight row:Preview fill`) before
  `trend`.

Verification (sheets opened with Read)
- Scratch project (2-column comparison with heading/verdict/vs/icons, 3-column `reveal: rows`
  with a `fill` on a point, a 4x4 table with row fill / column box / cell colour, a 6x4 table with
  wrapping notes, per-column formats and `reveal: all` with dim + highlight): storyboards in 16:9
  (also `--per-beat 3`), vertical and `light_academic`. Fixed along the way: points of
  different columns at different heights in `rows` mode (shared baselines), uneven point gaps
  in `columns` mode (row sharing only for `rows`), a bottom rule under an empty table (now drawn
  with the last row), 9:16 tables scaled below the readable size although a wrapped layout
  fit (proper water-filling, header words of number columns wrap, the readable size itself
  tried), "1920 x / 1080" wrapping (short cells stay whole). Lint of the scratch project: only
  the deliberate 6x4 stress table (max_words; in 9:16 also min_font, with the split warning).
- `examples/minimal`: `vidgen lint` 0 findings in all 8 variants (default, vertical, light,
  contrast, editorial, neutral, pastel, neon); `tradeoff`/`formats` sheets checked in 16:9,
  vertical and contrast (large scale).

Files
- New: `src/vidgen/scenes/comparison.py`, `src/vidgen/scenes/table.py`,
  `tests/test_comparison_table.py` (49 tests, 22 tiny renders at 160x90 / 90x160).
- Changed: `src/vidgen/actions.py` (`TARGET_NAME`), `src/vidgen/scene.py` (message),
  `src/vidgen/scenes/actions.py` (`fill` style, `Highlight._plate`), `src/vidgen/scenes/__init__.py`;
  `examples/minimal/video.yaml`; tests `test_builtin_scenes.py` (BUILTINS/SAMPLES),
  `test_actions_coverage.py` (SAMPLES, target names, early reveal), `test_extensions.py` (type
  list); docs/CONFIG.md (`comparison`, `table` sections, targets table, `fill`, Icons intro),
  docs/EXTENDING.md (dotted names, backdrops and `fill`), README, DESIGN.md (new §29), tasklist.md.

Public interfaces added/changed
- Built-in scene types `comparison` and `table` (params in docs/CONFIG.md). Highlight option
  `style` accepts `fill`. Target names may contain dotted parts. No `vidgen.api` change.
- Module helpers (internal): `vidgen.scenes.table.is_number`, `Table.Params.texts()`,
  `column_count()`, `numeric()`, `alignment()`; `Comparison.tone_color()`;
  `Highlight.fill_opacity`.

Decisions / deviations
- Highlights on table rows/columns/cells: `color` recolours the cell text only (stripes and
  cards are not part of a target, otherwise they would be painted solid); `fill` is the
  "band" look. The plate's draw position is found from the target's parts (before them if they
  were added on their own, else over their group as a faint overlay), so it also works in
  other scenes (e.g. a bullets item).
- `table` uses `per_beat | all` like `bullets` (not `rows`); the header, title and caption come
  with row 1. `title` (not `heading`) as in the charts and `code`.
- Comparison headings use the tone colour for positive/negative columns (colour-coded A vs B),
  `heading_color` for neutral ones.
- The "too big" check happens at render time (a log warning plus lint `min_font`), not in
  `vidgen validate`: whether a table fits depends on the variant's frame and type scale.

Known gaps / TODOs
- A 9:16 frame holds about 3–4 columns: wider tables reach the readable minimum quickly (the
  warning says to split). No automatic split into several tables or transposition.
- Table rows with very different heights (one long wrapped cell) look uneven; no per-column
  `width` param yet. Numbers use proportional digits (Inter via `Text` has no tabular figures),
  so right-aligned decimals line up by their right edge only.
- `comparison` cards are as tall as the tallest column (by design); with very different
  column lengths a short column shows empty card space. The `vs` badge has no target.
- `reveal` of a whole column whose point was revealed early is a no-op (it is "shown"); the
  column's own step still brings the rest.
- Found (framework, Step 23, not changed here): an action due in a beat that holds *several*
  reveal steps (more steps than beats) runs in the wait after the first step for its full
  `run_time`, and the following step then pushes the beat past `d + pad` (e.g. 2 comparison
  columns + verdict in 2 beats with a `reveal` in beat 1: 0.4 s over). `ActionRunner` should
  reserve the remaining steps' time; one step per beat (the common case) is unaffected.
  **Fixed after Step 26** (follow-up commit): `play_steps` sets `ActionRunner.held` to the run
  time of the beat's later steps, and actions are shortened to leave it; test
  `test_actions_leave_time_for_the_beats_remaining_steps`.

How to test: `/home/claude/venv/bin/python -m pytest -q` (993 passed, 1 skipped). Step only: `pytest
tests/test_comparison_table.py`. Manual: `vidgen storyboard examples/minimal --scene tradeoff
--scene formats --per-beat 3 [--variant vertical|light]`, `vidgen lint examples/minimal
[--variant ...]`, `vidgen list-scenes`, `vidgen schema --scene table`.

## Step 27 — Scene: `timeline`
What was built
- **`timeline`** (`src/vidgen/scenes/timeline.py`): 2–10 events `{date, title, text?, icon?,
  at?}` along an axis — horizontal in 16:9/square, vertical in 9:16 (`orientation: auto |
  horizontal | vertical`). Each event is a marker on the axis (a disc with its icon when the
  timeline has icons, else a dot), a short stem and a "card" (date in `date_color`, title in the
  heading font role, optional dim detail text). Cards alternate sides of the axis or stand in one
  column (`sides: auto | alternate | one`; `auto` plans both and keeps the one with the larger
  text, then fewer wrapped lines: alternating in 16:9, one column right of the axis in 9:16 for
  up to ~6 events). `spacing: even | proportional` (dates that are numbers, years, `YYYY-MM`,
  `YYYY-MM-DD` — unquoted YAML dates work — or each event's `at`; too-close neighbours are pulled
  apart). A progress line grows to each event as it is revealed (one segment per event).
  `highlight` (last step: others dim, marker and title in `highlight_color`), `now` (a "Now"
  tag + ring on that event, later events hollow with a dashed progress line; `now_label`),
  optional `heading`, `reveal: per_beat | all`. Event refs (`highlight`, `now`): 0-based index,
  date as shown, or title.
- **Fitting**: one text size for all events, up to 1.2x the requested sizes when that adds no
  wrapped lines, reduced together down to the readable minimum; wrapped lines are evened out.
  Too many/long events → scaled down + warning "split it into two timelines (or shorten titles
  and texts)" (and lint `min_font`).
- **Targets**: `heading`, `axis`, `event<N>`, `event:<date>` (marker + stem + text); an early
  `reveal` grows the progress line through skipped events without showing them. Row in the
  CONFIG.md targets table.
- **`vidgen.api` additions**: `measure_text(text, max_width, *, size, weight, ..., balance,
  role) -> TextMeasure(lines, width, height, fits)` (how `fit_text` would wrap, without building
  the text) and `fit_text(..., balance=False)` (even line lengths). Needed for speed: the
  timeline's size search took 90 s for 10 long events when it built every candidate, 5 s now.
- `examples/minimal`: new `schedule` scene (4 days with icons, `now: "Day 3"`, a `box`
  highlight on `event:Day 4`), before `part2`.

Verification (sheets opened with Read)
- Scratch project (space race with icons + highlight; proportional `YYYY-MM` dates + `now`; 10
  events in one beat; 2 events silent) storyboarded in 16:9 (also `--per-beat 3`), vertical and
  `light_academic`. Fixed along the way: a lone last word ("Manual reports every / week") →
  balanced wrapping; growth that made texts wrap more → growth only without extra lines, and
  growth never chooses the layout (a one-sided 16:9 layout had won by growing); the now tag
  went below `min_font` with the `compact` scale → floored at the readable size; a false "word
  too wide" detection on blocks a hair too wide → measured with `measure_text` instead.
  Lint of the scratch project: only the deliberate 10-events-in-one-beat stress case
  (`rushed_animation`, `max_words`).
- `examples/minimal`: `vidgen lint` 0 findings in all 8 variants (default, vertical, light,
  contrast, editorial, neutral, pastel, neon); `examples/custom_scene` 0 (16:9 and vertical).
  `schedule` sheets checked in 16:9, vertical, light and contrast.

Files
- New: `src/vidgen/scenes/timeline.py`, `tests/test_timeline.py` (46 tests, 17 tiny renders).
- Changed: `src/vidgen/layout.py` (`measure_text`, `TextMeasure`, `balance`,
  `_Metrics.width/balanced`), `src/vidgen/api.py`, `src/vidgen/scenes/__init__.py`;
  `examples/minimal/video.yaml`; tests `test_layout.py` (balance, measure), `test_builtin_scenes.py`
  (BUILTINS/SAMPLES), `test_actions_coverage.py` (SAMPLES, names, early reveal),
  `test_extensions.py`, `test_registry.py` (type lists); docs/CONFIG.md (`timeline` section,
  targets table, Icons intro), docs/EXTENDING.md (`measure_text`, `balance`), README, DESIGN.md
  (§5 layout list, new §30), tasklist.md.

Public interfaces added/changed
- Built-in scene type `timeline` (params in docs/CONFIG.md).
- `vidgen.api`: `measure_text` (new), `fit_text(..., balance=False)` (additive keyword; also
  `layout.fit_text_sized`). `vidgen.layout.TextMeasure` (returned, not exported by name).
- Module helpers (internal): `vidgen.scenes.timeline.date_position`, `TimelineEvent.shown()`,
  `.position()`, `Timeline.Params.event_index()`, `.positions()`.

Decisions / deviations
- The target for an event by label is `event:<date>` (the date as shown): the date is the
  event's label on the axis; titles are longer and change more. `highlight`/`now` accept the
  title too.
- `now` marks an event (not an arbitrary point between events): a free-floating "today" marker
  collided with cards and stems in tests of alternating layouts; marking the present event
  and drawing later ones as planned says the same without collisions.
- The "too many events" check is a render-time warning (as `table`): whether it fits depends on
  the variant's frame and type scale; `vidgen validate` caps the list at 10.
- `stem`, radii and gaps are fixed Manim units; text sizes come from theme tokens and font
  roles only; colours are theme tokens.

Known gaps / TODOs
- Proportional spacing is linear (no axis breaks, no tick marks/years along the axis); a
  `ticks:` option could label the axis itself (Step 30 chart helpers could share code).
- In 9:16 with one column the axis sits left of the text block, which is centred as a whole;
  short texts leave the right part of the frame empty (by design, like `bullets`).
- The vertical layout aligns a card's date with its marker only when there is room; tightly
  packed events (10 in 9:16) shift cards up/down within their stretch.
- `measure_text` is an estimate (a few percent short of Pango's layout); scenes using it should
  check the built text, as `timeline` does.

How to test: `/home/claude/venv/bin/python -m pytest -q` (1048 passed, 1 skipped, ~9 min). Step only: `pytest
tests/test_timeline.py`. Manual: `vidgen storyboard examples/minimal --scene schedule --per-beat 2
[--variant vertical|light]`, `vidgen lint examples/minimal [--variant ...]`, `vidgen list-scenes`,
`vidgen schema --scene timeline`.

## Step 28 — Graph layout + `diagram`/`flowchart`
What was built
- **`vidgen.graph`** (new, pure Python, no new dependency; exported by `vidgen.api`):
  `layered_layout(nodes, edges, *, direction="LR"|"TB", layer_gap, node_gap, routing=
  "straight"|"orthogonal", port_spacing, port_spread, label_margin, sweeps) -> GraphLayout`
  with `GraphNode(id, width, height, shape)`, `GraphEdge(source, target, label=(w, h))`,
  `NodePlace`, `EdgeRoute(source, target, points, reversed, label_at)`. Sugiyama phases: DFS
  back edges reversed (routes reversed again), longest-path layers with sources pulled
  forward, dummy nodes on long edges, barycenter sweeps + transposition from two starts (best
  kept), coordinates by weighted isotonic fits towards neighbours (parents end centred over
  children; long edges straight), ports spread along the facing side and clipped to the shape
  (box/ellipse/diamond/stadium), straight or orthogonal routes (a lane per run), room and an
  anchor for edge labels. Deterministic; topology phases cached per graph.
- **`diagram` scene** (`src/vidgen/scenes/diagram.py`), also registered as **`flowchart`**
  (same class). Nodes `{id, label, shape: box|round|pill|circle|diamond|cylinder, icon,
  color}` or a plain id; edges `{from, to, label, style: solid|dashed, color}` or the shorthand
  `"a -> b"`, `"a -> b: label"`, `"a --> b"` (dashed), chains `"a -> b -> c"`. `direction`
  auto (LR in 16:9/square, TB in 9:16; the other only if it keeps text ≥ 1.1x larger) | LR |
  TB; `routing` curved (S-curves, default) | straight | orthogonal. Reveal: `nodes` (one node
  per step in layout order, the edges into it growing from their source first), `layers`,
  `all`, or explicit `steps` (node ids / `a->b` per step; unnamed edges come with their ends,
  unnamed nodes in one more step). `highlight` (a path of node ids + edges) adds a last step:
  outline/tint/icon/line in `highlight_color`, the rest dims to 0.55. Sizing: label size from
  1.3x down to the readable floor (x1.05) per direction and wrap width, the largest that fits
  the body wins, then gaps widen to use spare room; nothing fits → scaled + warning "split it
  into smaller diagrams (or shorten labels)". Heading in the `header` region (1.3x in 9:16).
- **Targets**: `heading`, `node<N>`, `node:<id>` (outline = shape), `edge:<from>-><to>` (line,
  arrowhead, label; its entrance brings hidden ends); row in the CONFIG.md targets table.
- **Validation**: duplicate node ids, bad ids, unknown nodes in edges with suggestions
  (`edges[2] (start -> shp): unknown node 'shp'; did you mean 'ship'? (nodes: ...)`), self-loops,
  duplicate edges, chains with a label, unknown/repeated refs in `steps`, unknown refs in
  `highlight`.
- `describe` shows a field's alias (`from`) in `list-scenes` and its JSON.
- `examples/minimal`: new `loop` scene (the editing loop: pill / box / diamond / pill with
  icons, a dashed back edge "no", a `flash` on it, the happy path as `highlight`), after
  `feedback`.

Verification (sheets opened with Read)
- Scratch project (pipeline with labels, icons, cylinder and dashed edge + a highlight action;
  decision loop with diamond/circle and highlight path; an org tree with `orthogonal` and
  `reveal: layers`; a 10-node web architecture with explicit `steps`, `highlight edge:lb->*`,
  `zoom node:db`, box + dim) storyboarded in 16:9 (also `--per-beat 2`/`4`), vertical and
  `light_academic`. Fixed along the way: cylinder arcs stretched about their own centre (body
  misdrawn), a node appearing before the edges leading to it when several edges entered a step
  (waves), unnamed edges deferred to the last explicit step, lint `min_font` on short lowercase
  edge labels at exactly the readable size (floor x1.05), a highlighted label at 4.43:1 on
  `light_academic` (tint 0.14 → 0.1), a dimmed `dim` edge label at 1.96:1 (dim 0.45 → 0.55),
  narrow LR layouts (icons now above labels in LR; wrap width 1.7 tried), diagrams huddled in
  the middle (gap spreading). Lint of the scratch project: only the deliberate 10-node
  architecture in 16:9 (warning + `min_font`).
- `examples/minimal`: `vidgen lint` 0 findings in all 8 variants (default, vertical, light,
  contrast, editorial, neutral, pastel, neon); `loop` sheets checked in 16:9 (`--per-beat 2`),
  vertical and light.

Files
- New: `src/vidgen/graph.py`, `src/vidgen/scenes/diagram.py`, `tests/test_graph.py` (25
  tests), `tests/test_diagram.py` (45 tests, 21 tiny renders).
- Changed: `src/vidgen/api.py`, `src/vidgen/describe.py`, `src/vidgen/scenes/__init__.py`;
  `examples/minimal/video.yaml`; tests `test_builtin_scenes.py` (BUILTINS/SAMPLES, example uses
  every type but the alias), `test_actions_coverage.py` (SAMPLES, `ALIASES`, names, early
  reveal), `test_docs.py` (a second name's section points to the first); docs/CONFIG.md
  (`diagram`, `flowchart` sections, targets table, Icons intro, list-scenes JSON `name`),
  docs/EXTENDING.md ("Graphs"), README, DESIGN.md (§2, §6.4, new §31), tasklist.md.

Public interfaces added/changed
- Built-in scene types `diagram` and `flowchart` (params in docs/CONFIG.md).
- `vidgen.api`: `layered_layout`, `GraphLayout`, `GraphNode`, `GraphEdge`, `EdgeRoute`,
  `NodePlace` (new).
- `vidgen list-scenes` (and `--json` field `name`) shows a params field by its alias when it has
  one (only `DiagramEdge.from`).
- Module helpers (internal): `vidgen.scenes.diagram.parse_edges`, `edge_ref`,
  `Diagram.Params.resolve()`, `.step_refs()`, `Diagram.graph_layout` (after construct).

Decisions / deviations
- **Alias = the same class registered twice** (`scene("flowchart")(Diagram)`), not a registry
  alias feature: every tool already handles it as a type; tests treat `flowchart` as an alias
  (targets table, example coverage, docs section pointing to `diagram`).
- Node fill is a translucent tint of the node colour (0.1), not `surface`, so the `highlight`
  action's `color` style (which recolours every member) still leaves the label readable; edge
  label backdrops (background-colour pills) are outside the edge target for the same reason.
- The scene's own `highlight` step keeps labels in their colour (outline, tint, icon and
  lines change); the `highlight` action recolours labels too, as everywhere else.
- `steps` refs are node ids and `a->b` (not target names): they are the ids written in
  `nodes`/`edges`. Node ids may contain spaces (a plain string node is its own label).
- The "too dense" check is a render-time warning (as `table`/`timeline`): it depends on the
  variant's frame and type scale.

Known gaps / TODOs
- **Groups / clusters** (boxes around sets of nodes) are not implemented: they need layer
  ordering that keeps a cluster contiguous; a later step could add `groups: [{label, nodes}]`.
- Edge labels sit in the gap next to the source, centred on the route; with several labelled
  edges leaving one node towards close targets they can touch, and lines of other edges may
  pass under a label's pill. Long edges through many layers in 16:9 make wide layouts (the
  10-node architecture example needed the warning); there is no edge bundling or
  node-size-aware dummy compaction (Brandes–Köpf).
- Self-loops are rejected; 2-cycles (`a -> b`, `b -> a`) are drawn as two parallel curves.
- Orthogonal routes have sharp corners and their label anchor is the nearest point of the
  route to the straight anchor.
- `auto` direction prefers the frame's orientation unless the other is 1.1x better; a tree
  with many leaves in 16:9 stays LR (set `direction: TB` for an org chart).

How to test: `/home/claude/venv/bin/python -m pytest -q` (1128 passed, 1 skipped, ~10 min). Step
only: `pytest tests/test_graph.py tests/test_diagram.py`. Manual: `vidgen storyboard
examples/minimal --scene loop --per-beat 2 [--variant vertical|light]`, `vidgen lint
examples/minimal [--variant ...]`, `vidgen list-scenes`, `vidgen schema --scene diagram`.

## Step 29 — Scenes: `process` and `network`
What was built
- **`process`** (`src/vidgen/scenes/process.py`): a pipeline of 2–8 stages `{label, icon?, text?}`
  (a string is a label; labels unique) with a **token** that travels from stage to stage. Layout
  `auto`: a row in 16:9/square, two snaking rows (second row right to left, a turn on the right)
  when that keeps the text ≥ 1.1x larger (≥ 4 stages; in practice 6–8 with details), a column in
  9:16; `layout: row | snake | column` overrides. Cards on `surface`, icon above the text (row)
  or left of it (column). Each step: the previous stage returns to `stage_color`, the token
  leaves (passing *behind* that card) along the connector, which grows under it if not shown,
  and the new stage appears already **active** (outline `active_color` at 2x width, icon too).
  The token waits in front of the stage, on the incoming arrowhead. `token_icon` draws an icon
  in a disc instead of the dot; `token_label` adds a tag that travels with it (above rows, in a
  lane left of a column). `input`/`output` labels stand above their arrows (above/below a
  column); the input comes with step 1 (the token starts at its arrow), the output after the
  last stage. `loop: true` (+ `loop_label`) draws an arrow from the last stage back to the first
  (below a row, right of a column, below and round the left of a snake) and adds a last step
  in which the token follows it. `reveal: all` shows everything in step 1, then only the token
  moves. Fitting like `timeline`/`diagram` (one factor, up to 1.2x, down to the readable size);
  not fitting → warning + the drawing and the token's paths are scaled into the body.
  Targets `heading`, `input`, `stage<N>`, `stage:<label>`, `connector<N>`, `loop`, `output`,
  `token`.
- **`network`** (`src/vidgen/scenes/network.py`): layers (an int or `{size, label, show,
  connect, color}`, 2–8), LR in 16:9, TB in 9:16 (`direction`). Layers larger than `max_neurons`
  (8) are drawn as `show` (6) units with a three-dot ellipsis in the middle slot and their count
  under the label (`counts`, `count_format` `{n:,}`). Connections per layer (scene default
  `connect`): `dense`, `sparse` (`"sparse:0.3"`), `grouped` (`"grouped:3"`, edges in palette
  colours per block, as kphi3's figures), `one_to_one`, `none`, or `{type, ratio, groups}`.
  Edges only between drawn units, capped at `max_edges` (64) per pair (thinned reproducibly,
  every unit kept connected), opacity `clip(2.4/sqrt(count), 0.2, 0.75)`. Steps: layer by layer
  (incoming edges grow, then the units), then `passes` (default 1) forward passes — a pulse
  (`ShowPassingFlash` in `pulse_color`) runs along each set of edges and each layer's units flash
  — then `highlight` (`["1.2", "2.3", "3.1"]`, units as drawn): path units grow in
  `highlight_color`, edges between consecutive ones recoloured (drawn if the connection lacks
  them), the rest dims to 0.3. Targets `heading`, `layer<N>`, `layer:<label>`, `edges<N>`,
  `neuron<L>.<i>`.
- **Helpers** (`helpers.py`, exported by `vidgen.api`, all compatible — kphi3 renders unchanged,
  its tests pass): `column(..., *, horizontal=False, skip=None)`, `edges(..., *, colors=None,
  shorten=0.0)`, `grouped_pairs(n, groups, m=None)` (near-equal blocks, same pairs as before
  when `groups` divides `n`), new `sparse_pairs(n, m, ratio, seed=0)` and `group_bounds(n,
  groups)`. The `network` scene draws its layers with `column` and its edges with `edges`.
- `examples/minimal`: `render` (process: video.yaml → Validate/Voice/Render/Join → MP4, tag
  "scene", a `flash` on `token`) after `loop`, and `net` (network 4 → 256 → 3 with a highlight
  path) after `math`; two storyboard usage lines.

Verification (sheets opened with Read)
- Scratch project (process with io + tag + icons + details; a 4-stage cycle with a loop label and
  an icon token; 8 stages `reveal: all` + loop + input (snake in 16:9); network 4 → 512(show 4)
  → sparse → 3 with a highlight path; a grouped / one-to-one 9-9-9 net with 2 passes; an
  8-layer 784/128.../10 net; stress cases) storyboarded in 16:9 (also `--per-beat 3`: token
  travel, connector growth, pulses), vertical and `light_academic`. Fixed along the way: labels
  of inactive cards hidden by their own box (an animated submobject is re-added on top → box z 2,
  content z 3), io labels beside the arrows ate the row's width (now above the arrows), cards
  of short labels flat as strips (`card_aspect` 0.5), the shrink loop stopping when the caption
  sizes hit the floor while the labels could still shrink, words squashed one per line in
  over-full rows (cards never narrower than the longest word; the whole drawing scaled instead),
  the output appearing before the token reached the last stage, column io labels wrapped at
  the row width, dimmed ellipses missing in the highlight step, network centring in 9:16, the
  token's halo and tag at the start sticking out of the left margin (the row was scaled to 0.98:
  `min_font` warnings with `high_contrast` and `compact`).
- Lint of the scratch project: 0 findings in 16:9, vertical, light, high_contrast (large scale),
  brand_neutral + compact, and bold_neon vertical, apart from the deliberate stress cases (an
  8-stage process with long details and io in a 16:9 row: warning + `min_font`; short beats:
  `rushed_animation`).
- `examples/minimal`: `vidgen lint` 0 findings in all 8 variants (default, vertical, light,
  contrast, editorial, neutral, pastel, neon) for `render`/`net`, and the whole example in 16:9
  and vertical; `render`/`net` sheets checked in 16:9 (`--per-beat 3`), vertical and light.

Files
- New: `src/vidgen/scenes/process.py`, `src/vidgen/scenes/network.py`,
  `tests/test_process_network.py` (51 tests, 25 tiny renders).
- Changed: `src/vidgen/helpers.py`, `src/vidgen/api.py`, `src/vidgen/scenes/__init__.py`;
  `examples/minimal/video.yaml`; tests `test_api.py` (helper extensions),
  `test_builtin_scenes.py` (BUILTINS/SAMPLES), `test_actions_coverage.py` (SAMPLES, names, early
  reveal), `test_extensions.py` (type list); docs/CONFIG.md (`process`, `network` sections,
  targets table, Icons intro), docs/EXTENDING.md (helper arguments), README, DESIGN.md (§6.4,
  new §32), tasklist.md.

Public interfaces added/changed
- Built-in scene types `process` and `network` (params in docs/CONFIG.md).
- `vidgen.api`: `sparse_pairs`, `group_bounds` (new); keyword-only additions `column(horizontal=,
  skip=)`, `edges(colors=, shorten=)`, `grouped_pairs(..., m=None)`. `grouped_pairs` with a
  `groups` that does not divide `n` now makes near-equal blocks instead of dropping the remainder.
- Module helpers (internal): `vidgen.scenes.process.rounded_path`, `ProcessStage`,
  `Process.plan` (after construct); `vidgen.scenes.network.Connection` (`.pairs()`),
  `NetLayer`, `Network.Params.drawn()/truncated()/connection()/neuron()`.

Decisions / deviations
- **Token semantics**: the token waits in front of the active stage (on the arrowhead) and passes
  behind the card it leaves (z order token < cards), which reads as "processed inside"; its tag
  follows on the same path shifted by a fixed offset (no updaters, so waits stay frozen frames)
  and fades during the loop step (it would otherwise cross the cards).
- **Snake = two rows only**, used in landscape; 9:16 always uses a column (8 stages fit; a
  2-column snake in a 6.8-unit-wide frame was too narrow to be useful). The task's "vertical or
  snaking in 9:16" is met by the column.
- The process `output` is not a token destination (it appears after the last stage): with
  `loop` the token's last move is back to stage 1.
- `stage:<label>` needs unique labels (validation error otherwise), like diagram ids.
- Network units are filled dots (kphi3's `column` look); the pass uses `Indicate` (returns to
  the look) and `ShowPassingFlash` copies, so a pass leaves no trace and can repeat.
- `edges<N>` exists only for pairs with edges (`connect: none` has no target).
- `test_early_reveal_is_not_repeated_by_the_scene` covers `network` with `[layer2, edges1]`;
  `process` is covered by its own test (its step still moves the token, by design).

Known gaps / TODOs
- `process` has no per-stage highlight/branching (a pipeline is linear by definition; use
  `diagram` for forks). The token's tag is hidden after a loop.
- With few stages and no details the row leaves vertical space unused (cards are at most half as
  tall as wide); a stage text size larger than `growth` 1.2 is not attempted.
- `network` passes run inside a 1.8 s cap per step; a slow, beat-long pulse would need its own
  timing. Units are not labelled individually (no `x1..xn` inputs), no bias units, no
  per-edge weights/colours by value, no recurrent/skip connections (kphi3-style extras stay
  project scenes, now easier with `column(skip=)`/`edges(colors=)`).
- `play_steps` at very low fps rounds each of many steps in a short beat up to whole frames
  (seen at 5 fps with 9 steps in a 1.75 s beat: 0.05 s over); not specific to these scenes.

How to test: `/home/claude/venv/bin/python -m pytest -q` (1191 passed, 1 skipped, ~11 min). Step
only: `pytest tests/test_process_network.py tests/test_api.py`. Manual: `vidgen storyboard
examples/minimal --scene render --scene net --per-beat 3 [--variant vertical|light]`, `vidgen lint
examples/minimal [--variant ...]`, `vidgen list-scenes`, `vidgen schema --scene network`.

## Step 30 — Chart helpers + `scatter` and `histogram`
What was built
- **`vidgen.charts`** (new module, every name exported by `vidgen.api`): the parts the chart
  scenes share, public so project charts look and scale the same.
  - Numbers: `axis_ticks(lo, hi, max_ticks, log=)` (round linear ticks, or powers of ten; 1-2-5
    within two decades), `short_number` (`1.5k`, `2M`), `tick_texts` (shared decimals, `20k`
    from 10 000 on, or a format), `linear_fit` → `LinearFit(slope, intercept, r2)` with
    `.equation()`.
  - Axes: `ChartAxis` / `value_axis(values, lo, hi, max_ticks, log, fmt, unit, title,
    include_zero)`, and `chart_axes(area, x, y, size, grid, lines, right, top)` → `ChartAxes`
    (`plot` region, `point(x, y)`, `group` and its parts): tick labels at a theme size token
    never below `readable_size()` (`chart_label_size`), axis titles, dashed gridlines, colliding
    labels thinned to every k-th.
  - Legend: `chart_legend` (line / box / marker swatches, wrapped or stacked), `auto_legend`
    (a free corner of the plot on a faint framed panel, else above the plot), `legend_spot`,
    `sample_path`; markers `chart_marker` (`CHART_MARKERS` circle, square, triangle, diamond).
  - Frame: `chart_title` (bold, heading role, in the `header` band, 1.3x in portrait) and
    `chart_caption`.
- **`bar_chart` and `line_chart` on the helpers** (Step 22 findings fixed): titles in the header
  band; tick / category / axis / end labels at `label_size` (`caption`, was `small` 20 pt,
  below lint's floor) with the readable floor; new params `title_size`, `title_color`,
  `label_size`, and `value_size` (bar). 9:16 bar value labels keep their size: 0.9x, then a word
  unit (`" min"`) under the number, then smaller; when even the readable size does not fit a
  vertical slot, portrait charts switch to horizontal bars. `line_chart` ticks show the decimals
  they need, x labels thin by width, and the legend goes into a free plot corner (above the plot
  only when every corner has a line). 16:9 sheets look the same (ticks 24 instead of 20 pt,
  title a little lower); existing configs unchanged.
- **`scatter`** (`src/vidgen/scenes/scatter.py`): series as `{name: [points]}` or `[{name,
  points, color, marker}]`, a point `[x, y]`, `[x, y, label]` or `{x, y, label, group}`; markers
  differ by shape per series; linear or log axes, bounds, formats, units; `reveal: series |
  groups | all` (points pop in left to right); point labels placed beside their point clear of
  other points, labels, the legend and trend lines (halo, drawn above lines); `trend: each |
  all` least-squares lines (own step) with `trend_label: equation | r2 | both`; `highlight`
  rings chosen points (`"ours@2"`, `"ours@small"`, `"small"`), dims the rest; `show_labels:
  highlight` writes labels only for those. Targets `title`, `axes`, `legend`, `series<N>`,
  `series:<name>`, `point:<series>@<N>`, `point:<series>@<label>`, `trend`, `trend:<series>`.
- **`histogram`** (`src/vidgen/scenes/histogram.py`): `values` binned by `bins` (count, or a rule
  `auto | sturges | sqrt | fd` whose width is rounded to 1/2/2.5/5 x 10^k with edges on its
  multiples), `bin_width`, `bin_range`; or `counts` + `edges`. Bars grow left to right; then,
  each its own step, `compare` (a second distribution as an outline on the same bins, with a
  legend), `mean`, `median` (dashed line + value above the plot; exact from values, estimated
  from counts), `highlight` bins. `percent` shows shares. Targets `title`, `axes`, `legend`,
  `bin<N>`, `bin:<range>` (`bin:10-20`), `compare`, `mean`, `median`.
- `examples/minimal`: `cost` (scatter: two series, trend with R², a highlighted point) and
  `beats` (histogram with a median and a `box` highlight on `bin:4-5`) after `trend`; one
  storyboard usage line.

Verification (sheets opened with Read)
- Scratch project (scatter with two series, labels, `trend: all` + both labels, highlight;
  log-x scatter with `reveal: groups`; histogram with mean + median + highlight; counts/edges
  histogram in percent with a compare overlay) in 16:9, vertical, light and vertical light.
  Fixed along the way: legend swatches read as data points (now a framed panel), trend text
  crossing its own line or a point label (placed after point labels, offset along the line's
  normal), a point label crossed by the trend line (lint `covered_text`; labels now avoid lines
  and sit above them with a background halo), the line chart legend under its gridlines in 9:16
  (lint `covered_text`; legend `z_index` 1), histogram marker labels on the y axis title, a
  late-binding closure that revealed a marker instead of the compare overlay.
- `vidgen lint`: `examples/minimal` 0 findings in all 8 variants (default, vertical, light,
  contrast, editorial, neutral, pastel, neon); `examples/custom_scene` 0 (16:9 and vertical); the
  scratch project 0 in 16:9, vertical, light, vertical light. `sizes`, `trend`, `cost`, `beats`
  sheets checked in 16:9 (`--per-beat 3`), vertical and light.

Files
- New: `src/vidgen/charts.py`, `src/vidgen/scenes/scatter.py`, `src/vidgen/scenes/histogram.py`,
  `tests/test_charts.py`.
- Changed: `src/vidgen/api.py`, `src/vidgen/scenes/__init__.py`, `scenes/bar_chart.py`,
  `scenes/line_chart.py`; `examples/minimal/video.yaml`; tests `test_builtin_scenes.py`
  (BUILTINS/SAMPLES), `test_actions_coverage.py` (SAMPLES, early reveal), `test_extensions.py`
  (type list); docs/CONFIG.md ("Charts: common to all chart types", `scatter`, `histogram`,
  bar/line params, targets table), docs/EXTENDING.md ("Charts", tested example), README,
  DESIGN.md (§2, §6.4, new §33), tasklist.md.

Public interfaces added/changed
- `vidgen.api`: `ChartAxis`, `ChartAxes`, `LinearFit`, `CHART_MARKERS`, `axis_ticks`,
  `short_number`, `tick_texts`, `value_axis`, `chart_axes`, `chart_label_size`, `chart_legend`,
  `auto_legend`, `legend_spot`, `sample_path`, `chart_marker`, `linear_fit`, `chart_title`,
  `chart_caption`.
- Built-in scene types `scatter` and `histogram`. Params (additive): `bar_chart` / `line_chart`
  `title_size`, `title_color`, `label_size`; `bar_chart` `value_size`.
- Visible changes: chart titles in the header band (1.3x in 9:16); chart labels at `caption`
  (were `small`); `line_chart` ticks with the decimals the ticks need (`2.4`, was `2.40`) and
  x labels thinned by width (more labels where they fit); portrait bar charts may turn
  horizontal when value labels would otherwise be tiny.

Decisions / deviations
- Charts get no shared base class: the helpers are functions, so a project scene picks what it
  needs; `Params` were not given a common base (field order shows in `list-scenes`).
- Scatter points outside explicit `x_min`/... are a validation error, not silently clipped.
  Trend lines need linear axes (a log-axis "trend" would need a model choice: power or
  exponential); they cover the fitted points' x range only.
- Histogram rules round the bin width so edges are readable numbers (the bin count may differ
  from numpy's by one or two); an int `bins` gives exactly that many equal bins (edges may be
  unround, then the axis gets round ticks inside). `percent` normalises each distribution by
  its own total. `bin:<range>` uses an ASCII hyphen (`bin:-10--5` for negatives).
- Labels that are numbers equal to another point's index do not name a target (the index
  wins); documented.
- Legends inside the plot stand on a framed panel; above the plot (no free corner) unframed,
  as before.

Known gaps / TODOs
- No per-point value labels on histogram bars; no overlapping-bars style for `compare` (outline
  only); no density (`count / width`) scale; no box/violin plots.
- Scatter has no error bars, bubble sizes or point colours by value; label placement is greedy
  (8 positions) and can leave a label crossing a line when nothing better exists (it then sits
  on top with a halo).
- `line_chart` still has no log axis param (the helpers support it); `bar_chart` has no axis /
  gridlines (values are written on the bars).

How to test: `/home/claude/venv/bin/python -m pytest -q` (1279 passed, 1 skipped, ~13 min). Step only: `pytest
tests/test_charts.py`. Manual: `vidgen storyboard examples/minimal --scene cost --scene beats
--scene sizes --scene trend --per-beat 3 [--variant vertical|light]`, `vidgen lint
examples/minimal [--variant ...]`, `vidgen list-scenes`, `vidgen schema --scene scatter`.

## Step 31 — Scenes: `pie`/`donut` and `heatmap`
What was built
- **Colour helpers** (`vidgen/charts.py`, exported by `vidgen.api`): `color_scale(values, kind=
  "sequential"|"diverging", color, low_color, high_color, center, lo, hi)` → `ColorScale`
  (`scale(v)` → hex, `at(fraction)`, `fraction(v)`), interpolated in OKLab between theme
  colours: sequential from a 14 % tint of `color` on the background to `color`; diverging
  `low_color` → a near-background neutral at `center` → `high_color`, symmetric around
  `center`. `color_bar(scale, length, vertical=True, title=...)` (gradient bar, round ticks,
  readable labels), `text_color_on(fill)` (theme text or background, whichever reaches 4.5:1,
  else white/black) and `mix_colors(a, b, t)` (what `a` at opacity `t` over `b` looks like).
- **`pie`** (`src/vidgen/scenes/pie.py`): `labels` + `values` (shares computed), `donut` (`hole`,
  `center` = the total by default, `center_label`), `show_values: percent | value | both | none`,
  palette colours (lighter shades past the palette's length; the last slice never repeats the
  first's colour), `sort`, `other_below` / `max_slices` → one `Other` slice (`other_color` dim),
  `start_angle`, `clockwise`, `reveal: all | per_beat`, `highlight` (+ `explode`), `legend`
  (auto: > 6 slices). **Labels**: inside a slice when the label box fits the annular sector
  (text colour by `text_color_on`), else outside in a column per side with a leader line
  (rim → radial elbow → label), stacked without overlaps (`_stack`); when side columns leave
  the pie under 0.3 x the body's short side or cannot hold the labels (9:16), they go into a
  swatch key below the pie (beside it in 16:9); with `legend` everything is in the key (then
  the `legend` target). Sizes from `label_size` down to the readable floor x 1.05; what still
  does not fit is dropped with a warning naming it. **Animation**: wedges sweep round
  (`UpdateFromAlphaFunc` rebuilding the sector; one continuous sweep for `all`), labels and
  leaders follow; the highlight step moves the slice out along its middle (its leader's first
  corner follows), dims the others to 0.3 and recolours their inside labels for the dimmed
  slice. Targets `title`, `slice<N>`, `slice:<label>`, `center`, `legend`.
- **`heatmap`** (`src/vidgen/scenes/heatmap.py`): `values` (rows; `null` = empty `surface` cell;
  ≤ 40 x 40), `rows` / `columns` labels, `scale: auto | sequential | diverging` (+ `color`,
  `low_color`, `high_color`, `center`, `scale_min`, `scale_max`), `show_values` (auto: when
  the values fit at a readable size), `value_format`, `unit`, `value_size`, `legend` +
  `legend_label` (colour bar right of the grid in 16:9, below it in 9:16, as long as the grid),
  `reveal: all` (diagonal wave) | `rows`, `highlight` (target-style refs `cell2.3`, `row:Tue`,
  `col4`...; outlines in `highlight_color`, the rest dims with recoloured values). Cells at most
  2.2 units, never taller than wide or wider than 2.5x their height; column labels wrap to the
  cell width at one shared size; cells under 0.3 units → warning "split the matrix". Targets
  `title`, `legend`, `row<N>`, `row:<label>`, `col<N>`, `col:<label>`, `cell<R>.<C>`.
- `examples/minimal`: `share` (a donut: render time per scene, total "4.2 s per scene", two
  small slices grouped by `other_below`, `highlight: Text layout`) and `busy` (a 5 x 5 heatmap
  of renders per hour with a `box` highlight action on `col:17h`) after `beats`; a storyboard
  usage line.

Verification (sheets opened with Read)
- Scratch project (pie with highlight; donut per_beat with grouping and a highlight; 12-slice
  donut → legend; one big + five tiny slices → stacked side labels; sequential heatmap with a
  column highlight; diverging correlation matrix with nulls, `reveal: rows` and cell + row
  highlights; an 8 x 24 matrix; pie / heatmap with reveal, dim, zoom, box and fill actions)
  storyboarded in 16:9 (also `--per-beat 3`), vertical, `light_academic` and vertical light.
  Fixed along the way: a 9:16 pie shrunk to a third of the width by side labels (→ the swatch key
  below the pie), big slices whose label did not fit at 0.62 r (→ several spots and wrap
  widths), a 12-row legend scaled below `min_font` in 16:9 (→ wrapped rows), the pie off centre
  with labels on one side only (room reserved per side), lowercase column labels at exactly the
  floor (`min_font`, → floor x 1.05 as in `diagram`), a legend bar longer than a short grid.
  Lint of the scratch project: 0 findings in all four looks except the deliberately short beat
  (`rushed_animation`) and the action cases below.
- `examples/minimal`: `vidgen lint --scene share --scene busy` 0 findings in all 8 variants
  (default, vertical, light, contrast, editorial, neutral, pastel, neon); sheets checked in 16:9
  (`--per-beat 3`), vertical, light and contrast.

Files
- New: `src/vidgen/scenes/pie.py`, `src/vidgen/scenes/heatmap.py`, `tests/test_pie_heatmap.py`
  (49 tests, 16 tiny renders).
- Changed: `src/vidgen/charts.py`, `src/vidgen/api.py`, `src/vidgen/scenes/__init__.py`;
  `examples/minimal/video.yaml`; tests `test_builtin_scenes.py` (BUILTINS/SAMPLES),
  `test_actions_coverage.py` (SAMPLES, target names, early reveal), `test_extensions.py` (type
  list); docs/CONFIG.md (`pie`, `heatmap` sections, "Charts: common" colours, targets table),
  docs/EXTENDING.md ("Charts": colour helpers), README, DESIGN.md (§2, §6.4, new §34),
  tasklist.md.

Public interfaces added/changed
- `vidgen.api`: `ColorScale`, `color_scale`, `color_bar`, `mix_colors`, `text_color_on` (new).
- Built-in scene types `pie` and `heatmap` (params in docs/CONFIG.md).
- Module helpers (internal, built-in modules): `vidgen.scenes.pie.window` (a rate function
  running between two fractions), `recolor` (recolour + fade a text part), `PieSlice`,
  `Pie.Params.slices()/uses_legend()/highlight_index()/percents()/center_text()`;
  `Heatmap.Params.shape()/known()/kind()/cells_of()`.

Decisions / deviations
- **One label place per slice**: inside, beside (leader) or in the key — decided by fitting, not
  by a param (only `label_position: outside` forces leaders). The key in 9:16 is what keeps the
  pie large in a narrow frame; it is part of the slices' targets, not a `legend` target (that
  name must be known from params alone, so `legend` exists only with `legend: true` / > 6
  slices).
- "Percent computed, or given": shares are always value / total (values that are percentages
  give the same numbers); `show_values: value | both` writes the values themselves.
- Heatmap `highlight` refs use the target names (`row:Tue`, `cell2.3`), so one vocabulary for
  params and actions. Highlights outline (a `box` look) rather than recolour, because colour is
  the data.
- Diverging scales are symmetric around `center` by default (equal distances look equally
  strong); `scale_min`/`scale_max` override.
- Text on fills is opaque and chosen per fill (`text_color_on`); faded states are recoloured for
  the faded fill by the scenes' own highlight steps.

Known gaps / TODOs
- The generic `dim` action fades a slice / cell together with its text; dark text on a bright
  fill then drops below lint's 2:1 for dimmed text (seen: 1.5–1.7:1), and a `fill` highlight
  tints cells under light text (3.5:1). The scenes' own `highlight` params stay readable; the
  docs point to `style: box`. A per-target "restyle on dim" hook in the action framework would
  fix it generally.
- Pie leaders can cross a neighbouring label when a side's stack is pushed far from the slices
  (many small slices in a row); grouping (`other_below`) is the remedy. No rotated or curved
  labels, no per-slice `explode` other than the highlight, no pie-to-bar transition.
- Heatmap: no clustering / reordering, no row or column totals, no rotated column labels (long
  ones wrap and shrink; a warning asks to shorten them); 9:16 wide matrices are not transposed
  (warning). A highlight `box` action surrounds the band of cells and may touch the column label.

How to test: `/home/claude/venv/bin/python -m pytest -q` (1340 passed, 1 skipped, ~13 min). Step only:
`pytest tests/test_pie_heatmap.py`. Manual: `vidgen storyboard examples/minimal --scene share
--scene busy --per-beat 3 [--variant vertical|light]`, `vidgen lint examples/minimal --scene
share --scene busy [--variant ...]`, `vidgen list-scenes`, `vidgen schema --scene pie`.

## Step 32 — Scene: `code_walkthrough`
What was built
- **`code_walkthrough`** (`src/vidgen/scenes/code_walkthrough.py`): a long listing (`code` or
  `path`, `language`, optional `excerpt: "a-b"` keeping the file's numbers) in a window of fixed
  height (`visible` rows, else as many as fit at `size`). **Per-beat data** is `steps` (aligned with
  the beats like `code.highlight` / `diagram.steps`): `{lines, note, focus}` or a bare line spec.
  Each step scrolls smoothly so its lines are in view (left alone when they already show with a
  line of context, else centred; a range longer than the window shows its start), dims the other
  lines, lays a band (with an edge bar) behind the selection and shows its note; a step without
  `lines` keeps the view, `lines: all` clears the highlight. Lines: `12`, `"3-7"`, `"1, 5-6"`,
  `[3, 4]`, `"/regex/"` (first match), `"/def f/-/return/"` (range by content), mixed
  (`"40-/return/"`), checked by `vidgen validate`. Scroll indicator (track + thumb) when the code
  is longer than the window; rows fade at the window's edges while scrolling.
- **Notes**: `note_position: auto | side | bottom` — a callout beside the window level with the
  lines, with a pointer (16:9 / square, `auto` when the code fits beside without wrapping), or a
  bar below the window as tall as the tallest note (always in 9:16). **Focus**: `focus: true` (or
  a magnification 1–4; `focus_scale` 2.0 caps `true`) moves the camera onto the selected code
  (numbers excluded), fades the other rows out and shows the note as a card under the lines,
  built at 1/magnification so it reads at its normal size; never stops halfway through the
  title; the next step without focus moves the camera back.
- **Targets**: `title`, `listing`, `line<N>`, `lines:<a-b>` (all ranges up to 40 lines, else the
  ranges the steps select), `note<N>`. Revealing an out-of-view line scrolls to it; revealing a
  note plays its step. Scene × targets row in CONFIG.md "Beat actions".
- **Readability**: syntax colours below 4.6:1 on the window or the faintest band (a Pygments
  style that does not suit the theme, e.g. `default` purple on `warm_editorial`) are mixed
  towards the theme's `text`; the band's opacity drops from 0.12 to 0.07 while a colour would
  fall below 4.5:1 on it. Code is read by lint as `code` (the `Code` mobject stays in the scene).
- **`code` (Step 22 routed issue)**: wrapping now targets `max(readable, min(size, size that keeps
  TARGET_COLUMNS = 32 columns))`, so a vertical listing at the `large` scale wraps at ~32 columns
  instead of ~25 (font a little smaller, never below lint's minimum); 16:9 output unchanged.
- **Manim text canvas fix** (`code.text_canvas`, used by both scenes): Manim renders `Text` on a
  canvas of the output's pixel size and fails with "rendered fewer glyph(s) than its non-space
  characters" when text runs off it — ~60 lines of 24 pt code at 854x480 preview, 9 at 160x90.
  The canvas is enlarged while a listing is built. (This was also the "ligature" error seen with
  long files in `code`.)
- `examples/minimal`: `walkthrough` scene on `assets/train.py` (57 lines: number range, regex
  range, a focus step with a note, a bare `/a/-/b/` step) + a storyboard usage line.

Verification
- Scratch project (60-line file with wrapped lines, a 9-line function, a short-lined file with
  `visible: 8` and forced side notes; focus with and without notes; `lines: all`; silent) via
  `vidgen storyboard` (also `--per-beat 2`) in 16:9, vertical, `light_academic` and vertical light;
  sheets opened with Read. Fixed along the way: scroll thumb in the middle of the window, focus
  with a note out of view or the title cut in half (→ note card under the enlarged lines, title
  rule), focus too weak in 9:16 (→ frame the code ink, not the numbers), side notes squeezing the
  code in 9:16 (→ always bottom), line numbers / code invisible to lint (rows were loose
  VGroups → the `Code` stays in the scene and rows are taken out of its paragraphs), lint
  sizing text by the whole file's characters (→ `lines_text.original_text` = shown rows), band
  contrast on light / pastel presets (→ adaptive band, readable syntax colours), the Pango canvas
  clipping above.
- `vidgen lint examples/minimal --scene walkthrough --scene listing` in all 8 variants (default,
  vertical, light, contrast, editorial, neutral, pastel, neon): 0 findings. Other scenes of the
  example are untouched by this step.

Files
- New: `src/vidgen/scenes/code_walkthrough.py`, `tests/test_code_walkthrough.py` (44 tests, 8
  tiny renders), `examples/minimal/assets/train.py`.
- Changed: `src/vidgen/scenes/code.py` (module helpers `mono_metrics`, `size_for_columns`,
  `text_canvas`, `renumber`, `line_centers`, `line_runs`, `style_names`; constants
  `TARGET_COLUMNS`, `NUMBER_GAP`, `CODE_PADDING`; the column cap), `src/vidgen/scenes/__init__.py`;
  `examples/minimal/video.yaml`; tests `test_builtin_scenes.py` (BUILTINS/SAMPLES),
  `test_actions_coverage.py` (SAMPLES, early reveal of `note2`), `test_extensions.py` and
  `test_custom_scene_example.py` (list-scenes column width), `test_regions.py` (code font size in 9:16 now below `caption`, above readable);
  docs/CONFIG.md (`code_walkthrough` section, `code` column note, targets table), README,
  DESIGN.md (§35), tasklist.md.

Public interfaces added/changed
- Built-in scene type `code_walkthrough` (params in docs/CONFIG.md). No change to `vidgen.api`.
- Module helpers (internal, built-in modules): `vidgen.scenes.code_walkthrough.parse_lines`,
  `resolve_lines`, `WalkStep`, `ALL_RANGES_UP_TO`; `vidgen.scenes.code` helpers above (the former
  `CodeListing._renumber` / `_line_centers` methods and `_runs` / `_style_names` functions moved
  or were renamed).
- `code` output in 9:16 changes (smaller font, wider wrap); in 16:9 unchanged.

Decisions / deviations
- **Per-beat data as a params list** (`steps`), not beat-level fields: every built-in expresses
  per-beat content in params aligned with beats (beats only carry narration and actions), it is
  schema-describable per scene type, and `vidgen validate` can check lines without the beats.
- **Focus = camera + spotlight**, not a bigger font: re-laying the listing at another size means
  building it again (slow) and wide lines would overflow; a camera move keeps the layout. The
  other rows fade out so the note card can sit under the lines without covering text (lint's
  `covered_text`).
- **Rows leave the `Code` paragraphs instead of the scene**: `Scene.remove` would split the
  `Code` into loose parts (lint then no longer sees code, line numbers lose their contrast
  exemption); a target's `is_shown` still follows what is drawn.
- `lines:<a-b>` for long files only covers the steps' ranges: all pairs of a 300-line file
  would be 45 000 targets.
- The walkthrough's window is drawn by the scene (`Code`'s background is dropped) because its
  height is the view's, not the listing's.

Known gaps / TODOs
- A `dim` / `highlight` action on lines lasts until the next step (steps set line opacities, as
  in `code`); a highlight `box` does not follow a scroll. Side notes point at the rows of their
  step's planned view; an action that scrolls elsewhere in that beat leaves the pointer behind.
- Focus with a long selection or very wide lines enlarges little (warning when < 1.05x); in 16:9
  with bottom notes the card is the only note shown during the focus.
- Long files cost ~0.1 s per line to build (Manim glyphs); `excerpt` limits it. No horizontal
  scrolling (long lines wrap). Syntax highlighting of a line wrapped inside a string literal may
  be off (as in `code`).
- The readable-colour adjustment is only in `code_walkthrough`; `code` listings with an
  unsuitable Pygments style may still get a lint `contrast` warning.
- A clipped text SVG cached by Manim before the canvas fix stays in `build/.../media/texts`
  (the cache key ignores the canvas): delete `build/` if the glyph error persists.

How to test: `/home/claude/venv/bin/python -m pytest -q` (full suite); step only: `pytest
tests/test_code_walkthrough.py`. Manual: `vidgen storyboard examples/minimal --scene walkthrough
--per-beat 2 [--variant vertical|light]`, `vidgen lint examples/minimal --scene walkthrough
--scene listing [--variant ...]`, `vidgen list-scenes`, `vidgen schema --scene code_walkthrough`.

## Step 33 — Scene: `equation_derivation`
What was built
- **`equation_derivation`** (`src/vidgen/scenes/equation_derivation.py`): a sequence of equations.
  **Per-beat data** is `steps` (aligned with the beats like `code_walkthrough.steps`): `{tex, note,
  match, transition}` or the LaTeX string. Each step morphs out of the previous one: **marked
  parts** with the same TeX move into each other, the remaining glyphs move when their shapes match
  (`TransformMatchingShapes`) and fade otherwise. Parts are marked `{{ ... }}` (Manim's notation,
  space or start before `{{`), with a step's `match: [...]` (isolated in it and the step before),
  or by `terms` / `colors` keys (every step). `transition: shapes | fade` per step.
- **History / replace**: `mode: history` (default) keeps earlier steps stacked above the current
  one, dimmed (`dim_opacity`, raised to keep 2.3:1 contrast — light presets needed it for the `dim`
  notes) and aligned at the first `align_at` (`=`); the block re-centres as it grows; when the steps
  do not fit at a readable size the oldest scroll away (`keep` fixes the count). `mode: replace`
  shows one step at a time (still aligned at `=`, so the sign stays put).
- **Notes**: a column beside the equations, level with each step, with an accent bar (16:9; earlier
  notes stay, dimmed); a band right under the block, one note at a time (9:16, or
  `note_position: bottom`). A side note taller than its formula sets its row's height (no overlaps
  with the `large` type scale).
- **Colours** `colors: {x: accent}` in every step (and the dimmed history). **Result**: `box`
  (default, drawn after the last morph), `highlight` (a band behind it) or `none`.
- **Sizes**: one scale for all steps (`size` 80 at most, 1.25x in portrait), fitted to the width
  and the stacked rows; a step that would fall below 1.5x the readable size is rebuilt with
  breaks before its top-level relations (`a &= b \\ &= c`, then `a \\ &= b ...`) when that makes
  it larger; still too small → a warning naming the remedy.
- **Errors**: unbalanced braces, unclosed / empty `{{ }}`, `terms`/`colors` not in any step,
  `match` not in both steps → params errors in `vidgen validate`; a LaTeX error → `VidgenError`
  `scene 'd': step 2 does not compile: Undefined control sequence (at: \badcommand {2}); the
  step is 'x = \badcommand{2}' ...` (message and context read from the TeX log, dvisvgm markers
  removed).
- **Targets**: `title`, `step<N>` (also its dimmed line), `note<N>` (revealing it plays the step),
  `result` (last step + box), `term:<tex>` (parts from `terms`, `colors`, `match`, `{{ }}`) — the
  **current** step's only. A `transform` jump to the last step still gets the box at its beat.
- `examples/minimal`: `derive` scene (linear equation, five steps with notes, `x` coloured) + a
  storyboard usage line.

Verification
- Scratch project (5-step solve with notes and colours, replace mode with `match`, a long variance
  derivation, `keep: 2` with highlight/dim/zoom actions and `result: highlight`, a transform jump,
  bad LaTeX) via `vidgen storyboard` (`--per-beat 3`) in 16:9, vertical and `light_academic`;
  sheets opened with Read. Fixed along the way: block + notes centred together (notes were far from
  short formulas), note band moved right under the block in 9:16, formulas too small (default 80
  + portrait growth; break at relations below 1.5x readable, not just below readable), dimmed `dim`
  notes at 1.96:1 on light presets, overlapping side notes with the `large` scale, TeX error
  context full of `\special` markers.
- `vidgen lint examples/minimal --scene derive` in all 8 variants (default, vertical, light,
  contrast, editorial, neutral, pastel, neon): 0 findings. Other scenes untouched.

Files
- New: `src/vidgen/scenes/equation_derivation.py`, `tests/test_equation_derivation.py` (43 tests,
  10 tiny renders).
- Changed: `src/vidgen/scenes/__init__.py`; `examples/minimal/video.yaml`; tests
  `test_builtin_scenes.py` (BUILTINS/SAMPLES, LaTeX skip), `test_actions_coverage.py` (SAMPLES,
  target names, set comparison: a `term:` name is registered once per step that has the term,
  early `note2` reveal), `test_extensions.py` and `test_custom_scene_example.py` (list-scenes
  column now set by `equation_derivation`); docs/CONFIG.md (section, targets row, LaTeX note,
  link from `equation`), README, DESIGN.md (§36), tasklist.md.

Public interfaces added/changed
- Built-in scene type `equation_derivation` (params in docs/CONFIG.md). No change to `vidgen.api`.
- Module helpers (built-in module): `tokens`, `term_key`, `brace_problem`, `split_marked`,
  `plain`, `marked_terms`, `contains`, `break_lines`, `isolated_source`, `tex_error_excerpt`,
  `readable_opacity`, `morph`, `DerivationStep`.
- `vidgen list-scenes` name column is two characters wider (longest built-in name).

Decisions / deviations
- **Own part isolation instead of `substrings_to_isolate` / `TransformMatchingTex`**: Manim
  isolates raw substrings (`x` out of `\exp` breaks the TeX) and `TransformMatchingTex` matches
  only top-level parts, fading everything else. Parts here are whole-token runs wrapped in their
  own dvisvgm groups (braces added after `^`, `_`, one-argument commands; nothing wrapped right
  after `\left`/`\big`…), and the morph pairs marked parts first, then hands the rest to
  `TransformMatchingShapes` — so unmarked digits and signs still move.
- **The live step hands over to a dimmed copy** in history mode (instead of dimming it in place)
  so `term:` targets mean the current step, as the roadmap asked, while `step<N>` still finds the
  line.
- Notes default to `note_color: dim` with an `accent` bar: the formula is the hero.
- Line breaking only at top-level relations (the roadmap's "at `=`"); a long right-hand side with
  no relation to break before is scaled (warning) rather than broken at `+`.

Known gaps / TODOs
- A step with only one relation breaks as `lhs \\ &= rhs` (the left side right-aligned above);
  breaking long sums at `+`/`-` is not done.
- After a `transform` jump in history mode the earlier lines keep their rows (a gap may stay until
  the next step re-centres the block).
- A `highlight` colour action on a step is not carried into its dimmed copy (the copy keeps the
  step's own colours).
- Each step is one LaTeX compile (+ up to two for line breaks); cached by Manim across renders.

How to test: `/home/claude/venv/bin/python -m pytest -q` (full suite); step only: `pytest
tests/test_equation_derivation.py`. Manual: `vidgen storyboard examples/minimal --scene derive
--per-beat 3 [--variant vertical|light]`, `vidgen lint examples/minimal --scene derive
[--variant ...]`, `vidgen list-scenes`, `vidgen schema --scene equation_derivation`.

## Step 34 — Scene: `screenshot` with callouts
What was built
- **Callout helpers** (`src/vidgen/callouts.py`, public in `vidgen.api`, written for reuse by Step
  41's callout overlay): `callout_box`, `callout_circle`, `callout_arrow` (straight or `curved`; the
  label is placed away from the area, inside `bounds`, clear of `avoid`, preferably off
  `prefer_off`), `callout_magnifier` (an inset cut from the image's own pixels with Pillow at the
  output resolution, framed, joined to a frame around the area by two hull lines), `callout_spotlight`
  (shade with a rounded hole), `callout_label` (bold text on a plate in the callout colour, text in
  the theme colour that reaches 4.5:1, never below the readable size), `callout(kind, ...)`,
  `callout_area` (an area as a mobject, a `Region`, or `[x, y]` / `[x, y, w, h]` fractions of
  `within` or pixels of an image) and `label_spot` (the placement search). Each returns a
  `Callout` (`Group`: `kind`, `area`, `mark`, `tag`, `extent()`, `draw(start)`); `scale` builds
  one for a zoomed camera.
- **`screenshot`** scene (`src/vidgen/scenes/screenshot.py`): an image fitted below an optional
  title, optionally in a `browser` (dots + address field with `url`), `window` or `phone` frame
  drawn in `surface` / `dim`; **per-beat `steps`** (one callout, a list, or `{callouts, focus,
  previous}`; callouts `{KIND: area, label, color, side, curved, zoom}` or `{kind, area, ...}`);
  `units: fraction | px`; earlier callouts `fade` / `dim` / `keep` (scene `previous`, per-step
  override); `focus` moves the camera onto the step's areas and builds its callouts at
  1/magnification so labels read normally; targets `title`, `image`, `callout<N>`,
  `callout:<label>`, `step<N>`.
- `examples/minimal`: `app` scene (browser frame; box, curved arrow + circle, magnifier, focus +
  spotlight + arrow) on `assets/app.png` (18 KB, a made-up "Planner" dashboard drawn by the new
  maintainer script `tools/make_screenshot.py` with the bundled Inter; reproducible byte for byte).

Verification
- Scratch project (browser / window / phone frames, all five kinds, `px` units, `previous` fade /
  dim / keep, focus in and back, a silent scene without steps) via `vidgen storyboard` (`--per-beat
  1` and `2`) in 16:9, vertical and `light_academic`, plus `high_contrast` (large type scale) for
  the example; sheets read with Read. Fixed along the way: labels over the browser's address text
  (title bar now in `avoid`; lint `covered_text` from the frame outline drawn over the URL → outline
  drawn before the bar's parts), arrows with almost no length when the label was pushed back into
  the frame (distance penalty), labels on the picture when free background was next to it
  (`prefer_off`), a magnifier in 9:16 that barely enlarged (room measured above / below at full
  width vs beside at full height), tiny focus-built labels kept after the camera left (callouts
  built for another camera always leave), `background` is not a colour token (shade uses
  `theme.background`).
- `vidgen lint examples/minimal --scene app` in all 8 variants (default, vertical, light,
  contrast, editorial, neutral, pastel, neon): 0 findings. Other scenes untouched.

Files
- New: `src/vidgen/callouts.py`, `src/vidgen/scenes/screenshot.py`, `tests/test_screenshot.py` (42
  tests, 16 tiny renders), `tools/make_screenshot.py`, `examples/minimal/assets/app.png`.
- Changed: `src/vidgen/api.py` (exports), `src/vidgen/scenes/__init__.py`;
  `examples/minimal/video.yaml`; tests `test_builtin_scenes.py` (BUILTINS/SAMPLES),
  `test_actions_coverage.py` (SAMPLES, target names, early `step2` reveal), `test_extensions.py`
  (known types list); docs/CONFIG.md
  (`screenshot` section, targets row), docs/EXTENDING.md ("Callouts" building block with an example
  rendered by a test), README, DESIGN.md (§2, §6.4, new §37), tasklist.md.

Public interfaces added/changed
- `vidgen.api`: `Callout`, `CalloutArea`, `CALLOUT_KINDS`, `callout`, `callout_area`, `callout_box`,
  `callout_circle`, `callout_arrow`, `callout_magnifier`, `callout_spotlight`, `callout_label`,
  `label_spot` (DESIGN §37). Built-in scene type `screenshot`. Internal (module) helpers:
  `vidgen.callouts.tag_spot`, `connector_lines`, `mobject_region`, `pixel_size`.

Decisions / deviations
- **Helper names carry a `callout_` prefix** (the roadmap said `arrow`, `box`, `circle`,
  `magnifier`, `spotlight`): bare names would shadow common local names in `from vidgen.api import
  *` code and read ambiguously next to Manim's `Arrow` / `Circle`; the prefix matches the Step 30
  `chart_*` helpers. `callout(kind, ...)` gives the by-name form Step 41 will want.
- **Areas from the top-left corner, y down** (`[x, y, w, h]`), like image editors and `ken_burns`
  focus points, so coordinates can be read off a screenshot; `units: px` for pixel values.
- **Animations without `AnimationGroup`**: `Callout.draw()` returns one animation per part with
  windowed rate functions (an `AnimationGroup` leaves its own `Group` in `scene.mobjects`).
- **Spotlight dims the picture only** (`cover` = the image), not the title or frame; it lies under
  other callouts (z-index 1 vs 2).
- **Focus = camera + callouts built for the zoom** (as `code_walkthrough`'s focus card), not a
  bigger crop; callouts built for another view leave when the camera changes, even with `keep`.
- `dim` keeps marks (box, circle, arrow, a magnifier's source frame) at 0.35 and fades labels,
  insets and shades: dimmed labels on dimmed plates over a picture would fail lint's contrast.

Known gaps / TODOs
- Label placement is a scored search over fixed candidates, not a global layout: with many
  labelled callouts in one step on a small picture, labels may sit over each other's arrows (they
  avoid each other's labels and areas, not lines). One magnifier inset can cover other parts of
  the picture when there is no free background (it avoids the step's areas).
- No rounded corners on the image itself (the frame's corners are rounded; `ImageMobject` cannot
  be clipped); a phone frame suits portrait screenshots.
- A `highlight` colour action on a callout repaints its label text in the same colour as its plate
  (unreadable); use `style: box` / `flash` or `dim` / `zoom` (CONFIG.md lists reveal, dim, zoom).
- Ken Burns / pan on the screenshot itself is not offered (focus covers "zoom to the callout").
- Step 41: place callouts by target name with `callout_*(target.mobject, ...)` or frame
  fractions (`within=None`); for overlays that stay put while a scene's camera moves, build them
  with `scale` and `bounds` from `camera.frame` (as `screenshot._bounds` does).

How to test: `/home/claude/venv/bin/python -m pytest -q` (1487 passed, 1 skipped, ~14 min); step only:
`pytest tests/test_screenshot.py`. Manual: `vidgen storyboard examples/minimal --scene app --per-beat 2
[--variant vertical|light]`, `vidgen lint examples/minimal --scene app [--variant ...]`,
`vidgen list-scenes`, `vidgen schema --scene screenshot`, `python tools/make_screenshot.py`.

## Step 35 — Scene: `video_clip`
What was built
- **Clip helpers** (`src/vidgen/clips.py`, public in `vidgen.api`): `probe_clip(path) -> ClipInfo`
  (width, height, fps, duration, audio; PyAV metadata), `ClipTiming(start, end, speed, loop)`
  (`source_time(played)`, `span`, `length`), `fit_speed(span, window, low, high)`,
  `ClipMobject(path, timing)` (an `ImageMobject` showing the frame at the scene's clock:
  `fit_box(w, h, "contain"|"cover")`, `set_resolution(scale)`, `play(scene, at=None)`,
  `playback_time()`, `crop`, `info`, `timing`, `close()`), `clip_audio(path, wav, timing, length,
  volume, fade)` (the clip's sound as it plays, for `add_sound`), `CLIP_SUFFIXES`. Internal:
  `ClipReader` (sequential PyAV decode, seek on loops / far jumps, one frame held), `atempo_chain`,
  `END_GAP`.
- **`video_clip`** scene (`src/vidgen/scenes/video_clip.py`, subclass of `screenshot`'s class):
  `path`, `trim`, `speed`, `fit_duration` + `fit_range`, `loop` (else the last frame holds),
  `fit: contain | cover`, `region` (body / full / hero / left / right / top / bottom / center, or
  `bleed` = the whole frame), `title`, `caption` (+ size / colour; on `surface` plates over a bleed
  clip), the Step 34 `frame` chrome (`browser` / `window` / `phone`, not with bleed), `volume`
  (default 0.25 narrated, 1 silent) / `mute`, and `screenshot`'s `steps` of callouts (box, circle,
  arrow, spotlight; `focus`, `previous`, `units`), areas on the clip's whole picture (moved into the
  `cover` crop). Targets `title`, `clip`, `caption`, `callout<N>`, `callout:<label>`, `step<N>`.
- `screenshot` refactored for the subclass (no behaviour change): `picture_name`, `_spec_area()`,
  `_layout(body, fill=)`, `_picture_entrance()`, `Params.picture_word` (message wording).
- `examples/minimal`: `clip` scene (window frame, caption, `loop`, two callout steps) on
  `assets/clip.webm` (150 KB, ffmpeg's `testsrc2` + a quiet chord, VP9/Opus), made reproducibly
  (byte-identical twice) by the new maintainer script `tools/make_clip.py`.

Verification
- Scratch project (framed window + title + caption + callouts; bleed cover + loop; trim +
  `fit_duration` + focus/spotlight; `region: left` at speed 2 holding) via `vidgen storyboard
  --per-beat 3` in 16:9 and `--variant vertical`, sheets read with Read; frames checked against the
  clip's own frame counter (fade-in while playing, dimming via `set_opacity`, loop wrap). `vidgen
  lint` reports `dead_air` only for the held clip (6.9 s still); clip motion counts as activity.
- Fixed along the way: a loop showed the frame at the trim end for one frame (float sums of 1/fps
  vs WebM's millisecond time stamps: played time rounded to µs, end clamped 5 ms early, reader
  tolerance 2 ms); a hold re-seeked every frame; rendering was ~3x slower than needed (bicubic
  perspective transform of every frame: now decoded at the on-screen size, so the camera uses
  nearest-pixel copying — 17.3 s → 8.5 s for a 9 s bleed scene, incl. start-up); clip sound of a
  held clip ended after one pass (now padded to the scene's length).
- `vidgen lint examples/minimal --scene clip` in all 8 variants (default, vertical, light,
  contrast, editorial, neutral, pastel, neon): 0 findings; `--scene app` (screenshot, refactored)
  default and vertical: 0 findings.

Files
- New: `src/vidgen/clips.py`, `src/vidgen/scenes/video_clip.py`, `tests/test_video_clip.py` (53
  tests, 16 render; one `slow` lint test), `tools/make_clip.py`, `examples/minimal/assets/clip.webm`.
- Changed: `src/vidgen/api.py` (exports), `src/vidgen/scenes/__init__.py`,
  `src/vidgen/scenes/screenshot.py` (hooks above); `examples/minimal/video.yaml`; tests
  `conftest.py` (`write_clip`: a lossless grey-per-frame clip, `clip_frame_index`),
  `test_builtin_scenes.py` (BUILTINS/SAMPLES, clip asset), `test_actions_coverage.py` (SAMPLES,
  target names, early `step2` reveal, clip asset), `test_extensions.py`, `test_registry.py` (known types); docs/CONFIG.md
  (`video_clip` section, targets row), docs/EXTENDING.md ("Video clips" building block with an
  example rendered by a test), README, DESIGN.md (§2, §6.4, new §38), tasklist.md.

Public interfaces added/changed
- `vidgen.api`: `CLIP_SUFFIXES`, `ClipInfo`, `ClipMobject`, `ClipTiming`, `clip_audio`,
  `fit_speed`, `probe_clip` (DESIGN §38). Built-in scene type `video_clip`. `vidgen.clips` is
  otherwise internal.

Decisions / deviations
- **Frames decoded inside Manim (option a), not composited by ffmpeg afterwards (b)**: (b) would
  hide the clip from stills, the layout dump, lint, callouts, camera moves and actions. Speed is
  acceptable (~0.6 s per second of 854x480 preview for a full-bleed clip).
- **Modulation pixels**: the `pixel_array` Manim/vidgen animate is a 1 x 2 black/white pair applied
  affinely to each frame, so `FadeIn`, `dim`, `highlight` (tint), `set_opacity` act on the moving
  picture without any special casing in the actions. Copies share the playback.
- **The narration owns the length** (Step 14 contract unchanged): the clip starts at scene time 0
  and never lengthens or shortens a scene; longer → cut by the fade-out, shorter → hold (warning >
  2 s, lint `dead_air` > 6 s) unless `loop`; `fit_duration` stretches within `fit_range`.
- **Clip sound** = one temporary WAV built by ffmpeg (trim, `atempo` chain keeping pitch, exact
  one-pass length, `aloop`, pad, fade) mixed by Manim's `add_sound` at time 0 under the narration;
  default volume 0.25 narrated (no ducking; Step 45), skipped by `--no-audio`.
- Callout areas refer to the whole picture (also with `cover`), so they stay on the same content
  whichever part shows; `magnifier` is rejected (its inset would be a still of a moving picture).
- The example clip is WebM, not mp4: `*.mp4` is git-ignored as render output (CLAUDE.md), and
  VP9/Opus keeps it small; the scene accepts mp4/mov/m4v/webm/mkv alike (tests use H.264 mp4).

Known gaps / TODOs
- Callouts are static over a moving picture (no tracking); point at things that stay put.
- Rotation metadata (phone recordings) is not applied; variable frame rate is shown as stamped.
- No ducking of the clip sound under speech, no fade-in of it (Step 45 music/ducking could reuse
  `clip_audio`'s graph).
- In 9:16 a 16:9 clip with `contain` leaves large empty bands (documented: use `bleed` + `cover`).
- `render/ffmpeg.py` is not a render-fingerprint input, so a change there (clip sound) does not
  mark storyboard stills stale (they have no sound anyway).

How to test: `/home/claude/venv/bin/python -m pytest -q` (1546 passed, 1 skipped, ~14 min); step
only: `pytest tests/test_video_clip.py`. Manual: `vidgen storyboard examples/minimal --scene clip --per-beat 2
[--variant vertical|light]`, `vidgen lint examples/minimal --scene clip [--variant ...]`,
`vidgen list-scenes`, `vidgen schema --scene video_clip`, `python tools/make_clip.py`.

## Step 36 — Scene: `map`
What was built
- **Bundled world map** `src/vidgen/data/geo/world-110m.json` (132 KB, package data `data/geo/*`):
  Natural Earth 1:110m admin-0 countries (public domain), 177 countries with ISO 3166-1 alpha-2 /
  alpha-3 codes (Kosovo `XK`/`XKX`; N. Cyprus `CYN` and Somaliland `SOL` from Natural Earth's
  ADM0_A3, no alpha-2), short English names, aliases, a label point and a "main" box per country,
  and a `small` list of the 75 ISO countries too small for this scale. Built reproducibly
  (byte-identical twice) by the maintainer script `tools/make_world_map.py` from npm `world-atlas`
  2.0.2 (TopoJSON; its ids are ISO numeric codes) and `i18n-iso-countries` 7.14.0 (codes, English
  names and aliases); details in DESIGN §39, licences in THIRD_PARTY_NOTICES.md.
- **`vidgen.geo`** (no manim; public in `vidgen.api`): `find_country(name)` → `Country` (codes,
  names, aliases such as `USA`, `UK`, `Holland`, `Ivory Coast`, `DRC`; accents / case /
  punctuation ignored; did-you-mean; "too small for the 1:110m map, use a pin"),
  `world_countries(antarctica=True)`, `equal_earth(lon, lat, lon0)`, `MAP_VIEWS` (world, europe,
  africa, asia, middle_east, north_america, south_america, oceania), `view_box(view)` (boxes over
  the date line), `fit_view(points)` (padded box, over the date line when narrower, world when
  > 200°), `MapView(box, area)` (projected around the middle longitude, grown to the area's
  aspect within the world, fitted; `region`, `point`, `contains`, `polygons` clipped to the view,
  `box_region`, `cropped`). Projected polygons are cached per centre longitude: a world view
  builds ~280 polygons in ~25 ms, again in ~6 ms.
- **`map` scene** (`src/vidgen/scenes/world_map.py`): `view` (`auto` default: fits highlighted /
  valued countries, pins and arcs), top-level `countries` / `pins` / `arcs` (shown with the map in
  beat 1) and per-beat `steps` (`{countries, pins, arcs, focus}`, a list of countries or one
  country; step *i* at beat *i*, as in `screenshot`). Highlights fill (`highlight_color`, own
  `color`, or `palette`) with the country's name on it or beside it with a leader (`labels`,
  per-country `label`); choropleth `values` with `heatmap`'s colour-scale params and a legend bar
  under the map (highlights become outlines there; countries without a value are fainter);
  pins `{lon, lat, label}` / `{country, label}`; arcs `{from, to, label}` / `"A -> B"` (ends: pin
  label, country, `[lon, lat]`) bending upwards, trimmed at pins, growing to an arrowhead; labels on
  background plates, placed clear of each other and of pins; `focus` moves the camera onto a step
  (its labels built for the zoom; labels of other views fade). A regional view is a framed panel
  with the sea in `surface`. The map sweeps in west to east. Targets `title`, `map`, `legend`,
  `country:<code>` (alpha-3, alpha-2 or name; highlighted and valued countries), `pin<N>`,
  `pin:<label>`, `arc<N>`, `step<N>`; row in the CONFIG.md targets table.
- `examples/minimal`: `reach` scene (Europe; Portugal, Germany, Poland; then Lisbon and Warsaw pins
  with an arc) after `busy`, plus a storyboard usage line.

Verification
- Scratch project (world view with steps, pins and a London → Tokyo arc; Europe choropleth with a
  legend, an outline highlight and a focus step on Belgium + Netherlands; an `auto` view of
  Iberia with pins and a labelled arc) storyboarded in 16:9, `--variant vertical` and
  `light_academic`; sheets read with Read. Fixed along the way: a world view drawn as a panel
  (sampled edges missed the equator: `cropped` with a 1 % tolerance), the hard clip edge of
  regional views (→ framed panel with the sea), pin labels overlapping other labels (the pin's own
  box was dropped together with labels touching it), a leader line drawn over another label
  (lint `covered_text` in 9:16: leaders now under all plates), arcs ending under the pin dot
  (trimmed), no-data land darker than low choropleth values on light presets (fainter mix),
  merged blobs of neighbouring highlights (thicker borders on highlights).
- `vidgen lint examples/minimal --scene reach` in all 8 variants (default, vertical, light,
  contrast, editorial, neutral, pastel, neon): 0 findings; scratch project 0 findings in 16:9 and
  light, the 9:16 leader finding fixed. Sheets of `reach` read in 16:9 (`--per-beat 3`), vertical,
  light and contrast. A `slow` test lints a world + choropleth/focus project at 320x180 and 180x320.

Files
- New: `src/vidgen/geo.py`, `src/vidgen/data/geo/world-110m.json`, `src/vidgen/scenes/world_map.py`,
  `tools/make_world_map.py`, `tests/test_world_map.py` (69 tests, 8 render incl. one `slow` lint).
- Changed: `src/vidgen/api.py` (exports), `src/vidgen/scenes/__init__.py`, `pyproject.toml`
  (package data); `examples/minimal/video.yaml`; tests `test_builtin_scenes.py` (BUILTINS /
  SAMPLES), `test_actions_coverage.py` (SAMPLES, target names, early `step2` reveal),
  `test_extensions.py` (known types); docs/CONFIG.md (`map` section, targets row),
  docs/EXTENDING.md ("Maps" building block with an example rendered by a test), README,
  THIRD_PARTY_NOTICES.md ("World map"), DESIGN.md (§2, §6.4, new §39), tasklist.md.

Public interfaces added/changed
- `vidgen.api`: `MAP_VIEWS`, `Country`, `MapView`, `equal_earth`, `find_country`, `fit_view`,
  `view_box`, `world_countries` (DESIGN §39). Built-in scene type `map` (module `world_map`, not
  `map`, to keep the builtin name unshadowed). No other change.

Decisions / deviations
- **Data source**: `world-atlas` lacks alpha codes, so its ISO numeric ids are mapped with
  `i18n-iso-countries` (also the English aliases) — both on npm; GitHub / naturalearthdata.com were
  not needed. Our own compact JSON instead of TopoJSON: no decoder at run time, and the antimeridian
  cuts, orientation and label points are done once.
- **Equal Earth**, re-centred per view (a Pacific view works); not Robinson (Equal Earth is
  equal-area and has a closed form). The view grows to the frame's shape (more map, not empty bands);
  in 9:16 a region therefore shows a lot more land north and south, and a `world` view is a strip.
- **No city list**: pins take `{lon, lat}` or `{country}` (the roadmap made a city list optional).
- **Arcs on the flat map**, not great circles: a great circle London → Tokyo leaves a world map at
  the top and wraps; the flight-path look is the stylised curve.
- **`country:` targets only for countries the params name** (highlighted or valued): 177 x 3 names
  would drown the validation message's target list; `map` covers the rest (e.g. `dim: map`).
- **Highlights are overlays** (copies over the base shape), so `reveal` / `dim` / `zoom` act on them
  and the base map stays one target.
- Per-beat data as `steps` aligned with beats (as Steps 32–35); the top-level `countries` / `pins` /
  `arcs` are the static content of a one-beat map.

Known gaps / TODOs
- Microstates (Singapore, Malta, Bahrain...) are not in the 1:110m data (error suggests a pin); a
  1:50m file would be ~750 KB.
- No graticule, no ocean outline of the Equal Earth "sphere" in the world view, no inset maps
  (Alaska / Hawaii), no curved country labels; label placement is greedy (label_spot candidates).
- Arcs do not wrap round the date line (Los Angeles → Tokyo crosses the whole world map; use a
  Pacific box view).
- Strokes widen with a `focus` / `zoom` (Manim scales stroke widths with the camera); the focus
  step's own strokes are built thinner, earlier ones are not.
- Step 37 (Review 2): storyboard `map` in all presets (done here for the example scene) and decide
  whether the 9:16 world view should crop the empty Pacific edges to grow.

How to test: `/home/claude/venv/bin/python -m pytest -q` (1621 passed, 1 skipped, ~15 min); step
only: `pytest tests/test_world_map.py`. Manual: `vidgen storyboard examples/minimal --scene reach --per-beat 3
[--variant vertical|light]`, `vidgen lint examples/minimal --scene reach [--variant ...]`, `vidgen
list-scenes`, `vidgen schema --scene map`, `python tools/make_world_map.py` (needs npm).
