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
