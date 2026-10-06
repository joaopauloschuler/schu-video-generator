# vidgen

Generate narrated, animated explainer videos from a project folder. You write the narration as
short *beats* and pick a *scene type* for each scene in `video.yaml`; vidgen voices the beats with
ElevenLabs, animates every scene with [Manim](https://www.manim.community/) (each beat lasts
exactly as long as its narration), and joins everything with ffmpeg into one MP4 plus SRT
subtitles.

- **Config-only videos** with seventeen built-in scene types (title, chapter divider, bullets,
  icon grid, comparison, table, timeline, flowchart / diagram, charts, a counting stat, image,
  quote, equation, code, end card...), in landscape and vertical formats. Diagrams are laid out
  automatically from `edges: ["a -> b: label", ...]` (`layered_layout` is also there for
  project scenes).
- **Theme presets** (`theme: {preset: warm_editorial}`; seven built in: `dark_tech`, the default
  look, `light_academic`, `high_contrast`, `warm_editorial`, `brand_neutral`, `soft_pastel`,
  `bold_neon`), all WCAG AA with colour-blind-safe palettes, and **type scales** (`compact`,
  `standard`, `large`; vertical video gets `large` automatically); `vidgen list-themes
  --swatches themes.png` shows them; projects can register their own (e.g. a brand look).
- **Bundled fonts**: Inter, Source Serif 4 and JetBrains Mono NL ship with vidgen (no install);
  presets pick them per role (serif headings in `light_academic` and `warm_editorial`).
- **Icons**: 200 built-in line icons (Lucide, ISC) in eight categories
  ([catalogue](docs/ICONS.md)), searchable by concept, recoloured by the
  theme and crisp at any size; used from config by `bullets` items, `title`, `chapter`, `stat`,
  `comparison`, `timeline`, `diagram`, `end_card` and the `icon_grid` scene; `vidgen list-icons --search chart --sheet icons.png` finds and shows them;
  a project adds or replaces icons with SVGs in `assets/icons/`.
- **Beat actions**: a beat can point at parts of its scene while it is spoken —
  `- highlight: "bar:4K"`, `- dim: item1`, `- reveal: item4` (with `until:` a later beat to undo),
  `- zoom: "term:2ab"` (camera in and back out), `- transform: step1` + `into: step3` — on every
  built-in scene type, timed inside the beat ([reference](docs/CONFIG.md#beat-actions)).
- **Extensible per video**: a project can add its own scene types, beat actions, helpers, theme
  tokens and pipeline hooks in its `extensions/` folder, without touching vidgen.
- **Cheap to iterate**: only new or edited beats are sent to ElevenLabs; fast low-resolution
  previews; re-render one scene at a time.
- Windows, macOS and Linux; Python 3.10–3.13.

## Install

### Windows

1. **Python 3.10–3.13** from [python.org](https://www.python.org/downloads/) (tick "Add
   python.exe to PATH").
2. **ffmpeg**: `winget install ffmpeg`, then open a new terminal (`ffmpeg -version` must work).
3. **vidgen** (in PowerShell, from a copy of this repository):
   ```
   cd video-generator
   py -m venv .venv
   .venv\Scripts\Activate.ps1          # cmd.exe: .venv\Scripts\activate.bat
   pip install .                       # or `pip install -e ".[dev]"` to work on vidgen itself
   vidgen --version
   ```
   This installs Manim, pydantic, PyYAML and PyAV (pre-built wheels; no compiler needed).
4. **Fonts**: nothing to install. vidgen bundles Inter (sans), Source Serif 4 (serif) and
   JetBrains Mono NL (code), all SIL Open Font License (see `THIRD_PARTY_NOTICES.md`). Any
   installed font works too, e.g. `theme: {font: Segoe UI}`.
5. **ElevenLabs API key** (only for `vidgen tts`): `setx ELEVENLABS_API_KEY your_key`, then open
   a new terminal. vidgen reads the key only from this variable and never writes it anywhere.
6. Optional, only for the `equation` scene type: **LaTeX** — install
   [MiKTeX](https://miktex.org/download) (it includes `dvisvgm`; allow it to install missing
   packages on the fly) and open a new terminal.

If PowerShell refuses to run `Activate.ps1`, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

### macOS / Linux

`python3 -m venv .venv && . .venv/bin/activate && pip install .`, ffmpeg from
`brew install ffmpeg` / `sudo apt install ffmpeg` (fonts are bundled), and
`export ELEVENLABS_API_KEY=your_key` in your shell profile. Linux may need Manim's system
libraries first (`sudo apt install libcairo2-dev libpango1.0-dev`). Optional LaTeX: MacTeX, or
`sudo apt install texlive texlive-latex-extra dvisvgm`.

## Quick start

```
vidgen init my_video            # scaffold video.yaml, extensions/, assets/, .gitignore
cd my_video
vidgen validate                 # check config, scene types, params, assets and audio status
vidgen render --preview         # 854x480 check, timed from word counts -> my_video_preview.mp4
vidgen storyboard               # contact sheets of every beat -> build/preview/storyboard/*.png
vidgen lint                     # layout + timing checks: text cut off, too small, low contrast, dead air...
vidgen tts --dry-run            # what would be sent to ElevenLabs, and how many characters
vidgen tts                      # generate narration MP3s (only new/changed beats)
vidgen render                   # final render -> my_video.mp4 + my_video.srt
```

Edit `video.yaml` (reference: [docs/CONFIG.md](docs/CONFIG.md)) and repeat. Until audio exists,
beats are timed from their word count, so you can lay out the whole video before paying for
narration.

## Commands

| command | |
|---|---|
| `vidgen init DIR [--example minimal]` | create a new project (DIR must not exist or be empty) |
| `vidgen validate [PROJECT] [--json]` | load config and extensions, report every problem (also in every variant), estimated length, audio status |
| `vidgen list-scenes [PROJECT] [--json]` | scene types (built-in and the project's) with their params |
| `vidgen list-themes [PROJECT] [--swatches PNG] [--json]` | theme presets (built-in and the project's) with colours, type scale, contrast check; `--swatches` draws them all in one PNG |
| `vidgen list-icons [PROJECT] [--search TEXT] [--category NAME] [--sheet PNG] [--json]` | icons (built-in and the project's `assets/icons`) with category and tags; `--sheet` draws the listed icons, labelled, into a PNG |
| `vidgen schema [PROJECT] [--scene TYPE \| --all] [--json]` | JSON Schema of `video.yaml` (params checked per scene type, the project's extension types included), for editors and AI agents |
| `vidgen tts [PROJECT] [--dry-run] [--force] [--beat ID ...] [--variant NAME]` | generate missing/stale narration into `audio/`; `--dry-run` needs no key |
| `vidgen render [PROJECT] [--preview] [--scene ID ...] [--variant NAME] [--no-audio] [--keep-going] [--jobs N] [--frames] [--frames-per-beat N] [--json]` | render and join the video |
| `vidgen storyboard [PROJECT] [--scene ID ...] [--per-beat N] [--variant NAME] [--preview \| --final] [--width PX] [--jobs N] [--force] [--json]` | contact sheets (PNG) of the video's stills with labels and narration, to review a video without watching it |
| `vidgen lint [PROJECT] [--scene ID ...] [--rule NAME ...] [--variant NAME] [--preview \| --final] [--fail-on SEVERITY] [--jobs N] [--force] [--json]` | check the layout at the end of every beat (text off the frame or in the margins, overlapping or covered text, text too small, low contrast, too many words) and the timing (narration too fast/slow, dead air, animations overrunning their narration or squeezed into a short beat); exit code 1 on errors |

`PROJECT` is a project folder or its config file (default: the current folder).
`render` options: `--preview` uses the `preview` resolution; `--scene ID` re-renders only those
scenes and re-joins with the existing renders of the others; `--variant NAME` applies a named
variant (e.g. vertical 1080x1920); `--no-audio` leaves the narration out (timing is unchanged);
`--keep-going` renders the remaining scenes after a failure; `--jobs N` renders N scenes in
parallel; `--frames` also saves a PNG still of the last frame of every beat (`--frames-per-beat
N`: N evenly spaced stills per beat) in `build/<final|preview>[_<variant>]/frames/<scene>/`,
with an `index.json` (beat, time, path) — a way to look at a render without playing it, see
[docs/CONFIG.md](docs/CONFIG.md#frame-stills-vidgen-render---frames) — and, for the same frames,
`build/.../layout/<scene>.json`: every visible text/shape/image with its pixel box, font size in
px, colours and opacity ([layout dump](docs/CONFIG.md#layout-dump-buildlayoutscenejson)). Errors are printed as `error: ...` with exit code 1.
`--json` prints one machine-readable JSON document on stdout instead (problems with their
config location, scene types with params/defaults/docs, output paths and per-scene durations;
errors too, with a non-zero exit code) — for scripts and AI agents. The shapes are documented
in [docs/CONFIG.md](docs/CONFIG.md#json-output---json).
`vidgen storyboard` writes contact sheets to `build/<preview|final>[_<variant>]/storyboard/`:
`video-<page>.png` (the whole video, split into pages of bounded size) and
`scenes/<scene>-<page>.png` (one scene, larger stills); each still is labelled `beat @ time`
with the beat's narration under it. It renders (preview format by default, with stills) only
the scenes whose stills are missing or out of date, so after `vidgen render --preview --frames`
or an earlier storyboard it is quick; see
[docs/CONFIG.md](docs/CONFIG.md#storyboard-vidgen-storyboard).
`vidgen lint` checks the same stills and each scene's activity over time
(`build/.../activity/<scene>.json`: beat timings, every `play`, a per-frame change signal),
rendering only what is missing or stale like the storyboard, and prints one line per problem
with the still to look at; thresholds and
severities are set in an optional `lint:` section, findings a scene means to have are skipped
with its `lint_ignore`; see [docs/CONFIG.md](docs/CONFIG.md#lint-vidgen-lint).
`vidgen schema > video.schema.json` writes a JSON Schema (draft 2020-12) that editors and
agents can check `video.yaml` against before running `vidgen validate`; see
[docs/CONFIG.md](docs/CONFIG.md#json-schema-vidgen-schema).

## Project layout

```
my_video/
  video.yaml          # the config
  extensions/         # optional: your own scene types, helpers, hooks (*.py)
  assets/             # images, code files, ... referenced from params
    icons/            # optional: your own icons <name>.svg (+ icons.json with tags)
  audio/              # generated narration: <beat_id>.mp3 + .hash (keep it; it cost money)
  build/              # intermediate render files, --frames stills + layout, storyboards (safe to delete)
  my_video.mp4  my_video.srt  my_video_preview.mp4 ...
```

## Examples and docs

- [examples/minimal](examples/minimal) — every built-in scene type, no Python:
  `vidgen render examples/minimal --preview [--variant vertical]`.
- [examples/custom_scene](examples/custom_scene) — "How a bicycle gear works": built-ins plus a
  custom scene type with a helper module, a project icon, a vertical variant and a hook.
- [examples/kphi3](examples/kphi3) — a real 4-minute paper video whose eight bespoke scenes all
  live in its `extensions/` folder (narration MP3s included, so it renders without a key).
- [docs/CONFIG.md](docs/CONFIG.md) — every config key and built-in scene type.
- [docs/EXTENDING.md](docs/EXTENDING.md) — writing scene types, helpers, theme tokens and hooks;
  layout regions (`region("header")`, `grid`, `place`, `readable_text`) that adapt to 16:9 and 9:16.
- [DESIGN.md](DESIGN.md) — architecture and internal contracts.

## Working on vidgen

`pip install -e ".[dev]"`, then `python -m pytest -q` runs every test (a few minutes: many
tests render tiny videos). Quicker: `python -m pytest -q -m "not slow"` skips the slowest
render tests, `-m "not render"` skips all rendering (seconds). No test needs network or keys.

## Troubleshooting

- `ffmpeg not found on PATH` — install it and open a new terminal.
- Text in a fallback font — a font named in the theme (other than the bundled Inter, Source
  Serif 4 and JetBrains Mono NL) is not installed (for all users, on Windows).
- `cannot write ...mp4 ... is it open in another program` — close the video player showing the
  previous render; the new video was kept as `<name>.partial.mp4`.
- Windows paths longer than 260 characters can fail inside Manim: keep projects in a short
  folder (e.g. `C:\videos\my_video`) or enable long paths in Windows.
