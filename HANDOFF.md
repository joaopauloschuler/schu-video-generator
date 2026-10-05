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
