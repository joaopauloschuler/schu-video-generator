# vidgen

Generate narrated, animated explainer videos from a project folder. You write the narration as
short *beats* and pick a *scene type* for each scene in `video.yaml`; vidgen voices the beats with
ElevenLabs, animates every scene with [Manim](https://www.manim.community/) (each beat lasts
exactly as long as its narration), and joins everything with ffmpeg into one MP4 plus SRT
subtitles.

- **Config-only videos** with twenty-eight built-in scene types, in landscape and vertical
  formats (one config renders both):
  - text and structure: `title`, `chapter` (section divider), `bullets`, `icon_grid`,
    `comparison` (A vs B), `table`, `timeline`, `quote`, `text_card`, `end_card`;
  - flows: `diagram` (alias `flowchart`; laid out automatically from `edges: ["a -> b: label"]`,
    and `layered_layout` is there for project scenes), `process` (a token travelling through a
    pipeline), `network` (a neural network with forward-pass pulses);
  - data: `bar_chart`, `line_chart`, `scatter`, `histogram`, `pie` (and donut), `heatmap` (colour
    scales from the theme), `stat` (a counting number with a comparison), `map` (countries step by
    step, choropleths, pins and flight-path arcs; Natural Earth data bundled);
  - pictures and media: `image` (Ken Burns), `screenshot` (callouts: boxes, arrows, magnified
    insets, a spotlight; in a browser, window or phone frame; a caption), `video_clip` (B-roll, screen
    recordings: trimmed, sped up, looped, full-bleed or framed, their sound under the narration);
  - maths and code: `equation`, `equation_derivation` (steps morphing into each other, with
    notes), `code`, `code_walkthrough` (a long file scrolling to the lines each beat explains).
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
  `comparison`, `timeline`, `diagram`, `process`, `end_card` and the `icon_grid` scene; `vidgen list-icons --search chart --sheet icons.png` finds and shows them;
  a project adds or replaces icons with SVGs in `assets/icons/`.
- **Beat actions**: a beat can point at parts of its scene while it is spoken —
  `- highlight: "bar:4K"`, `- dim: item1`, `- reveal: item4` (with `until:` a later beat to undo),
  `- zoom: "term:2ab"` (camera in and back out), `- transform: step1` + `into: step3`,
  `- callout: "point:sparse@8"` + `kind: arrow`, `label: Lowest loss` (a box, circle, arrow,
  label, spotlight or magnifier on a target or at coordinates of the frame, for the beat) — on
  every built-in scene type, timed inside the beat ([reference](docs/CONFIG.md#beat-actions)).
- **Overlays**: a video-level `overlays:` list draws lower thirds (`- {type: lower_third, scene:
  intro, at: 1.5, name: Ada Lovelace}`), a watermark (logo, icon or text in a corner), a progress
  bar and a chapter indicator ("2 · Results") over the scenes, fixed to the screen through camera
  moves and fades and seamless across cuts; per scene on/off or overridden
  ([reference](docs/CONFIG.md#overlays)). Chapters come from `chapter` cards or a scene's
  `chapter:` key ([chapters](docs/CONFIG.md#chapters)).
- **Burned-in captions**: `- {type: captions}` puts the narration into the picture, cut at
  phrase boundaries like the SRT, with the scenes laid out clear of it; `style: karaoke` shows a
  few big words at a time with the spoken one highlighted, for vertical / social videos. Word
  times are estimated from the audio, or exact with `voice: {timestamps: true}` (ElevenLabs
  character timings) ([reference](docs/CONFIG.md#captions)).
- **Pronunciation dictionary**: `pronunciation: {K-Phi-3: kay fye three}` (plain, case-insensitive
  or regex entries, or a separate file) changes only what the voice is sent; subtitles and
  captions keep the written words, timed by the spoken ones. Only beats whose spoken text changes
  are re-voiced, and `vidgen tts --dry-run` shows what they will say
  ([reference](docs/CONFIG.md#pronunciation-pronunciation)).
- **Multiple voices**: `voices: {ana: {voice_id: ..., label: "Dr. Ana"}}` plus `voice: ana` on a
  scene or a beat for interviews and dialogue; each named voice inherits the base `voice:`, only
  its own beats are re-voiced when it changes, `vidgen tts --dry-run` counts characters per voice
  (`--voice ana` voices one speaker), and `subtitles: {speakers: name}` / captions `speakers:`
  name or colour the speakers ([reference](docs/CONFIG.md#multiple-voices-voices)).
- **Sound effects**: eleven synthesised sounds (whoosh, swoosh, pop, click, tick, typing, riser,
  chime, success, error, thud; no licences) or your own `assets/sfx/NAME.wav`, placed as a beat
  action (`- sfx: whoosh` with `at`, `gain`, `align: end`, `params: {pitch: 3}`), in a scene's
  `sfx:` list (seconds, silent scenes too) or with `self.sfx("pop")` in scene code; mixed
  sample-exact about 7 dB under the narration; `sfx: {auto: true}` adds soft sounds to built-in
  reveals, highlights, callouts, zooms and chapter cards. `vidgen list-sfx` describes every sound
  in words and `--render-dir` writes them out to listen to ([reference](docs/CONFIG.md#sound-effects-sfx)).
- **Background music**: `music: calm` — one of three generated ambient beds (`calm` pad,
  `pulse` soft arpeggio at 96 BPM, `bright` uplifting at 120 BPM; seamless loops, no licences) or
  your own file, looped with a cross-faded seam, faded in and out, changed per scene range (a
  list of cues with `from` / `to`) or muted per scene (`music: false`); ducked 12 dB under the
  narration only (not under the sound effects). A video with music is normalised to −16 LUFS
  (EBU R128) with a −1.5 dBTP true-peak limiter (`audio: {normalize, target_lufs, true_peak}`;
  narration-only videos keep their level unless `normalize: true`); `vidgen render` reports the
  measured loudness and `vidgen list-music` describes the beds in words ([reference](docs/CONFIG.md#background-music-music)).
- **Transitions**: `transition: crossfade` between all scenes, or per scene (the way into it):
  `crossfade` (the scenes overlap, the video gets shorter by it), `fade_color` through a theme
  colour (`{type: fade_color, color: surface, duration: 1.2}`), `push` (the next scene slides in
  and pushes the previous one out) or `wipe` (`{type: wipe, direction: up, soft: true}`). A
  transition never covers narration (the scene before is held a little longer if needed);
  subtitles, captions, chapters, overlays, effects and music all follow the overlapped timeline,
  and overlays are neither doubled in a crossfade nor moved by a push or wipe
  ([reference](docs/CONFIG.md#transitions-transition)).
- **Continuity (match cuts)**: `carry: ["title -> heading"]` on a scene starts it with the scene
  before's title exactly where it ended, then glides it into its own heading (also icons and any
  other target), so the cut between them does not show
  ([reference](docs/CONFIG.md#continuity-carrying-objects-into-the-next-scene-carry)).
- **Extensible per video**: a project can add its own scene types, beat actions, overlays,
  helpers, theme tokens and pipeline hooks in its `extensions/` folder, without touching vidgen.
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
6. Optional, only for the `equation` and `equation_derivation` scene types: **LaTeX** — install
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
vidgen tts --dry-run            # what would be sent to ElevenLabs (with the pronunciation applied), how many characters
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
| `vidgen list-icons [PROJECT] [--search TEXT] [--category NAME] [--sheet PNG [--theme [PRESET]]] [--json]` | icons (built-in and the project's `assets/icons`) with category and tags; `--sheet` draws the listed icons, labelled, into a PNG (`--theme`: in the project's or a preset's colours) |
| `vidgen list-sfx [PROJECT] [--render-dir DIR] [--json]` | sound effects (built-in and the project's `assets/sfx`) with a description of each sound, length, loudness; `--render-dir` writes them as WAV files |
| `vidgen list-music [PROJECT] [--render-dir DIR] [--json]` | background music beds (built-in, described in words: instruments, key, tempo, chords, mood) and the project's `assets/music` files; `--render-dir` writes one loop of each bed as WAV |
| `vidgen schema [PROJECT] [--scene TYPE \| --all] [--json]` | JSON Schema of `video.yaml` (params checked per scene type, the project's extension types included), for editors and AI agents |
| `vidgen tts [PROJECT] [--dry-run] [--force] [--beat ID ...] [--voice NAME ...] [--variant NAME]` | generate missing/stale narration into `audio/`; `--dry-run` needs no key (shows each beat's voice and characters per voice) |
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

- [examples/minimal](examples/minimal) — the core built-in scene types (title, bullets, icon
  grid, charts, image, quote, equation, code, cards) and beat actions, no Python:
  `vidgen render examples/minimal --preview [--variant vertical]`; burned-in captions with
  `--variant subtitled`, 9:16 karaoke captions with `--variant social`.
- [examples/gallery](examples/gallery) — every other built-in scene type once (stat, chapter,
  comparison, table, timeline, diagram, process, network, scatter, histogram, pie, heatmap, map,
  screenshot, video clip, equation derivation, code walkthrough), overlays (a watermark, a
  lower third, a progress bar, a chapter indicator), sound effects, a ducked music bed,
  transitions (crossfades, colour fades, a push, a wipe) and two carried objects:
  `vidgen storyboard examples/gallery [--variant vertical]`, `vidgen render examples/gallery --preview`.
- [examples/custom_scene](examples/custom_scene) — "How a bicycle gear works": built-ins plus a
  custom scene type with a helper module, a project icon, a vertical variant and a hook.
- [examples/kphi3](examples/kphi3) — a real 4-minute paper video whose eight bespoke scenes all
  live in its `extensions/` folder (narration MP3s included, so it renders without a key).
- [docs/CONFIG.md](docs/CONFIG.md) — every config key and built-in scene type.
- [docs/EXTENDING.md](docs/EXTENDING.md) — writing scene types, actions, overlays, helpers, theme tokens and hooks;
  layout regions (`region("header")`, `grid`, `place`, `readable_text`) that adapt to 16:9 and 9:16.
- [DESIGN.md](DESIGN.md) — architecture and internal contracts.

## Working on vidgen

`pip install -e ".[dev]"`, then `python -m pytest -q` runs every test (about 17 minutes on two
CPUs: many tests render tiny videos); `python -m pytest -q -n auto` runs them in parallel on
every CPU (pytest-xdist, in the `dev` extra). Quicker: `python -m pytest -q -m "not slow"`
(about two minutes) skips the render sweeps over every scene type, the end-to-end renders of
sound, music and transitions, and every test that takes over ~1.5 s; `-m "not render"` skips
all rendering. Run the full suite before committing. No test needs network or keys.

## Troubleshooting

- `ffmpeg not found on PATH` — install it and open a new terminal.
- Text in a fallback font — a font named in the theme (other than the bundled Inter, Source
  Serif 4 and JetBrains Mono NL) is not installed (for all users, on Windows).
- `cannot write ...mp4 ... is it open in another program` — close the video player showing the
  previous render; the new video was kept as `<name>.partial.mp4`.
- Windows paths longer than 260 characters can fail inside Manim: keep projects in a short
  folder (e.g. `C:\videos\my_video`) or enable long paths in Windows.
