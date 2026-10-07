# schu-video-generator

The project and pip package are called schu-video-generator;
the command and the Python package are `vidgen` (`vidgen render`, `from vidgen.api import *`).

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

  See them all in the **[scene gallery](docs/gallery/README.md)**: every type at 16:9 and 9:16,
  with a GIF, its YAML, params and targets (`vidgen gallery` makes it, also for a project's own
  types).
- **Made for AI authors**: [AGENTS.md](AGENTS.md), also built in as `vidgen guide`, tells an
  agent how to make a good video with vidgen (see [For AI agents](#for-ai-agents)); `vidgen mcp`
  gives an agent's client every command as an MCP tool, storyboards returned as images
  ([Use from an AI agent via MCP](#use-from-an-ai-agent-via-mcp)).
- **From an outline to a draft**: `vidgen plan outline.md` turns a Markdown outline or a
  plain-text script into a draft project (no AI involved): headings become scenes and chapters,
  prose becomes beats of 6–15 words, lists / tables / code / maths / images / quotes / `A -> B`
  chains / numbers pick their scene types, and every scene says why (`# plan:`) and what to check
  (`# TODO:`) ([example](examples/plan)).
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
- **Chapters in the outputs**: `vidgen render` writes the chapters into the MP4 (players list
  them and jump to them) with tags (`metadata: {artist, comment, ...}`; title from `title`), and
  `<output>_chapters.txt`, the `0:00 Intro` / `1:05 Results` list for a YouTube description; an
  "Intro" chapter covers the opening before the first chapter (`chapters: {intro: false}` starts
  the first chapter at 0:00 instead), and `validate` / `render` warn when YouTube would ignore the
  list (fewer than 3 chapters, one shorter than 10 s)
  ([reference](docs/CONFIG.md#chapters-in-the-outputs-chapters-metadata)).
- **Thumbnail and shareable parts**: `thumbnail: {title, subtitle, icon}` draws a designed
  1280x720 card (1080x1920 for a vertical variant) in the theme — one big bold title sized to
  stay legible at YouTube's 320x180 — or `thumbnail: {scene, beat, at, overlays: false}` takes a
  frame of a scene; written by every `vidgen render` (or `vidgen thumbnail`) as
  `<output>_thumbnail.png` (+ a JPEG under 2 MB), with the small size to look at and checks of
  text size and contrast ([reference](docs/CONFIG.md#thumbnail-thumbnail-vidgen-thumbnail)).
  `vidgen export gif --scene ID --max-mb 5` turns a scene (or `--from` / `--to`) into a palette
  GIF within a size budget, `vidgen export clip` into an MP4 (stream-copied when it can be)
  ([reference](docs/CONFIG.md#export-gif-and-clip-vidgen-export)).
- **Slides**: `vidgen slides` turns the video into one self-contained HTML deck — a slide per
  beat (its fully built frame; `--mode scene` for one per scene), the narration as speaker notes,
  keyboard / click / swipe navigation, an overview by chapter, fullscreen, and with `--audio` a
  narrated play mode ([reference](docs/CONFIG.md#slides-vidgen-slides)). `--format pdf` writes
  a PDF instead: a slide per page, or with `--notes` notes pages (slide, narration, page
  numbers), an optional title page, bookmarks by chapter and the `metadata:` as document
  properties (optional extra `schu-video-generator[pdf]`; [reference](docs/CONFIG.md#pdf-deck---format-pdf)).
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
- **Readback check**: `vidgen readback` transcribes the narration MP3s with speech to text
  (faster-whisper locally, extra `schu-video-generator[stt]`, or ElevenLabs) and compares them with the beat
  texts: a word error rate per beat, the words expected and heard ("K-Phi-3" said "kay fye three",
  heard "kay five three"), and a suggested fix — a pronunciation entry for a term misheard in
  several beats, regenerating a beat that lost words. Transcripts are cached; `vidgen lint`'s
  `readback` rule reports the beats above the threshold ([reference](docs/CONFIG.md#readback-vidgen-readback)).
- **Generated images**: an `image` scene can take `generate: {prompt, negative, style, aspect,
  seed}` instead of a file. `vidgen imagegen` makes the missing pictures once with the OpenAI
  Images API (`OPENAI_API_KEY`; `--dry-run` shows the prompts and an estimated cost) and stores
  them in `assets/generated/` with a JSON note of how each was made — commit them like audio.
  Until then renders show a placeholder card with the prompt, so the video can be laid out first;
  a project `imagegen.style` keeps the pictures alike, and `vidgen validate` warns when a prompt
  asks for text in the picture ([reference](docs/CONFIG.md#generated-images-imagegen-vidgen-imagegen)).
- **Other languages**: a variant with `language: pt-BR` and `translations: translations/pt.yaml`
  is the same video in Portuguese. `vidgen translate-template --variant pt` lists every beat text
  and on-screen text (titles, bullets, labels, table cells, chapter titles, the thumbnail...)
  with its source and a hash; fill in the translations, and re-running it keeps them, marks the
  ones whose source changed and follows texts that moved. Untranslated texts show the source and
  `vidgen validate` lists them. Captions and the SRT break lines by the language's rules, the
  speed lint uses its rate, ElevenLabs gets its `language_code` where the model takes one, the
  MP4 its audio language tag, and translated beats get their own `audio/<variant>/`
  ([reference](docs/CONFIG.md#languages-and-translations)).
- **Multiple voices**: `voices: {ana: {voice_id: ..., label: "Dr. Ana"}}` plus `voice: ana` on a
  scene or a beat for interviews and dialogue; each named voice inherits the base `voice:`, only
  its own beats are re-voiced when it changes, `vidgen tts --dry-run` counts characters per voice
  (`--voice ana` voices one speaker), and `subtitles: {speakers: name}` / captions `speakers:`
  name or colour the speakers ([reference](docs/CONFIG.md#multiple-voices-voices)).
- **Sound effects**: eleven synthesised sounds (whoosh, swoosh, pop, click, tick, typing, riser,
  chime, success, error, thud; free to use in your videos, including commercially; no
  attribution needed) or your own `assets/sfx/NAME.wav`, placed as a beat
  action (`- sfx: whoosh` with `at`, `gain`, `align: end`, `params: {pitch: 3}`), in a scene's
  `sfx:` list (seconds, silent scenes too) or with `self.sfx("pop")` in scene code; mixed
  sample-exact about 7 dB under the narration; `sfx: {auto: true}` adds soft sounds to built-in
  reveals, highlights, callouts, zooms and chapter cards. `vidgen list-sfx` describes every sound
  in words and `--render-dir` writes them out to listen to ([reference](docs/CONFIG.md#sound-effects-sfx)).
- **Background music**: `music: calm` — one of three generated ambient beds (`calm` pad,
  `pulse` soft arpeggio at 96 BPM, `bright` uplifting at 120 BPM; seamless loops; free to use in your videos, including commercially; no attribution
  needed) or
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
  previews; `render`, `storyboard` and `lint` re-render only the scenes whose inputs changed.
- Windows, macOS and Linux; Python 3.10–3.13.

## For AI agents

vidgen is meant to be driven by AI agents. An agent making a video should read
**[AGENTS.md](AGENTS.md)** first — or run `vidgen guide` (the same guide, shipped with vidgen;
`vidgen guide --list` for its topics, `vidgen guide scenes` for one, `--json` for programs). It
covers the working loop (write → `validate --json` → `storyboard`, and look at the PNGs → `lint
--json` → fix → `tts --dry-run` → `tts` → `render`), pacing and on-screen text rules, a scene-type
chooser with a snippet per type, visual design, beat actions and audio with restraint, good vs bad
examples, outputs and the fixes for common validate / lint messages. (`CLAUDE.md` is for agents
working on schu-video-generator's own code.) Starting from an outline, `vidgen plan outline.md --json` writes a
draft project to refine: its `# TODO:` comments list what to check first.

### Use from an AI agent via MCP

`vidgen mcp` is a [Model Context Protocol](https://modelcontextprotocol.io) server: an agent in
Claude Desktop, Claude Code or any MCP client calls vidgen's commands as tools — `guide`, `plan`,
`init`, `validate`, `schema`, `list_scenes`, `list_icons`, `list_themes`, `list_sfx`,
`list_music`, `storyboard`, `lint`, `render`, `tts`, `imagegen`, `readback`, `slides`,
`thumbnail`, `export`, `gallery`, `translate_template` — and gets each command's JSON document
back. `storyboard`, `thumbnail` and `gallery` also return their pictures, so the agent **sees** its
video. Install the extra: `pip install ".[mcp]"` (the official MCP Python SDK).

Claude Desktop (`claude_desktop_config.json`; on Windows give the full path of `vidgen.exe` in
the venv's `Scripts` folder if `vidgen` is not on the PATH):

```json
{
  "mcpServers": {
    "schu-video-generator": {
      "command": "vidgen",
      "args": ["mcp", "--root", "C:\\Users\\me\\videos"]
    }
  }
}
```

Claude Code: `claude mcp add schu-video-generator -- vidgen mcp --root /home/me/videos` (or the same
`mcpServers` entry in the project's `.mcp.json`).

- **One folder**: the tools read and write only inside `--root` (default: the folder the server
  starts in); a path outside it, also through `..` or a link, is refused — in tool arguments and
  in the files a project's `video.yaml` names (pictures, clips, code files, extensions...).
- **No surprise bills**: `tts` and `imagegen` are dry runs unless called with `dry_run: false`
  **and** `confirm_cost: true` (and `readback` with a paid speech-to-text provider needs
  `confirm_cost: true`); the dry run says what it would cost. API keys come from the server's
  environment (set `ELEVENLABS_API_KEY` / `OPENAI_API_KEY` where the client starts it, e.g. an
  `"env"` entry) and are never returned.
- **Robust**: every call runs the CLI in a fresh process (`vidgen <command> --json`), reports its
  progress lines, and stops it when the call is cancelled; renders run one at a time.
- Resources: the guide (`vidgen://guide`, `vidgen://guide/<topic>`) and the JSON Schema
  (`vidgen://schema`). Reference: [docs/CONFIG.md](docs/CONFIG.md#mcp-server-vidgen-mcp).

## Install

Upgrading an environment that installed this project before it was renamed (as `vidgen`): run
`pip uninstall vidgen` once, then install as below (the `vidgen` command is unchanged).
An unrelated project on PyPI is also named `vidgen` and also installs a top-level `vidgen`
package, so do not install both in the same environment.

### Windows

1. **Python 3.10–3.13** from [python.org](https://www.python.org/downloads/) (tick "Add
   python.exe to PATH").
2. **ffmpeg**: `winget install ffmpeg`, then open a new terminal (`ffmpeg -version` must work).
3. **schu-video-generator** (in PowerShell, from a copy of this repository; it installs the
   `vidgen` command):
   ```
   cd video-generator
   py -m venv .venv
   .venv\Scripts\Activate.ps1          # cmd.exe: .venv\Scripts\activate.bat
   pip install .                       # or `pip install -e ".[dev]"` to work on schu-video-generator itself
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
7. Optional, only for PDF slide decks (`vidgen slides --format pdf`): `pip install ".[pdf]"`
   (fpdf2, pure Python).
8. Optional, only for `vidgen readback` with local speech to text: `pip install ".[stt]"`
   (faster-whisper; its first run downloads the Whisper model from the Hugging Face Hub, ~500 MB
   for `small`).
9. Optional, only for `vidgen imagegen` (generated pictures): an **OpenAI API key**,
   `setx OPENAI_API_KEY your_key` (read only from this variable, never written anywhere).
10. Optional, only for `vidgen mcp` (the MCP server for AI agents): `pip install ".[mcp]"`.

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
                                # (or: vidgen plan outline.md -o my_video  -> a draft from your outline)
cd my_video
vidgen validate                 # check config, scene types, params, assets and audio status
vidgen render --preview         # 854x480 check, timed from word counts -> my_video_preview.mp4
vidgen storyboard               # contact sheets of every beat -> build/preview/storyboard/*.png
vidgen lint                     # layout + timing checks: text cut off, too small, low contrast, dead air...
vidgen tts --dry-run            # what would be sent to ElevenLabs (with the pronunciation applied), how many characters
vidgen tts                      # generate narration MP3s (only new/changed beats)
vidgen readback                 # speech to text of the MP3s vs the texts: misheard terms, missing words (schu-video-generator[stt])
vidgen imagegen --dry-run       # pictures of generate: params still to make, their prompts and estimated cost
vidgen render                   # final render -> my_video.mp4 + my_video.srt (+ my_video_chapters.txt with chapters)
vidgen thumbnail                # my_video_thumbnail.png (also written by render with a thumbnail: section)
vidgen export gif --scene intro # exports/my_video_intro.gif
vidgen slides --final --audio   # exports/my_video_slides.html: the video as a narrated slide deck
vidgen slides --final --format pdf --notes   # exports/my_video_notes.pdf: slides with the narration (schu-video-generator[pdf])
```

Edit `video.yaml` (reference: [docs/CONFIG.md](docs/CONFIG.md)) and repeat. Until audio exists,
beats are timed from their word count, so you can lay out the whole video before paying for
narration.

## Commands

| command | |
|---|---|
| `vidgen init DIR [--example minimal] [--json]` | create a new project (DIR must not exist or be empty) |
| `vidgen mcp [--root DIR]` | the MCP server (stdio) giving an AI agent's client these commands as tools, inside DIR only (needs `schu-video-generator[mcp]`; also `vidgen-mcp`) |
| `vidgen plan INPUT [--output DIR\|FILE] [--title TEXT] [--format 16:9\|9:16] [--preset NAME] [--language TAG] [--force] [--json]` | a draft project from a Markdown outline or a plain-text script (deterministic, no AI): scenes chosen from its headings and cues, narration cut into beats, on-screen texts compressed, a `# plan:` reason and `# TODO:`s per scene; prints scenes, estimated length and TODO count, and validates the draft |
| `vidgen guide [TOPIC] [--list] [--json]` | the author guide for AI agents ([AGENTS.md](AGENTS.md)): all of it, one topic (`workflow`, `pacing`, `social`, `scenes`, `design`, `actions`, `overlays`, `audio`, `examples`, `outputs`, `troubleshooting`, ...) or the list |
| `vidgen validate [PROJECT] [--json]` | load config and extensions, report every problem (also in every variant, including variants that do not load), estimated length, audio status, generated pictures |
| `vidgen list-scenes [PROJECT] [--json]` | scene types (built-in and the project's) with their params |
| `vidgen list-themes [PROJECT] [--swatches PNG] [--json]` | theme presets (built-in and the project's) with colours, type scale, contrast check; `--swatches` draws them all in one PNG |
| `vidgen list-icons [PROJECT] [--search TEXT] [--category NAME] [--sheet PNG [--theme [PRESET]]] [--json]` | icons (built-in and the project's `assets/icons`) with category and tags; `--sheet` draws the listed icons, labelled, into a PNG (`--theme`: in the project's or a preset's colours) |
| `vidgen list-sfx [PROJECT] [--render-dir DIR] [--json]` | sound effects (built-in and the project's `assets/sfx`) with a description of each sound, length, loudness; `--render-dir` writes them as WAV files |
| `vidgen list-music [PROJECT] [--render-dir DIR] [--json]` | background music beds (built-in, described in words: instruments, key, tempo, chords, mood) and the project's `assets/music` files; `--render-dir` writes one loop of each bed as WAV |
| `vidgen schema [PROJECT] [--scene TYPE \| --all] [--json]` | JSON Schema of `video.yaml` (params checked per scene type, the project's extension types included), for editors and AI agents |
| `vidgen tts [PROJECT] [--dry-run] [--force] [--beat ID ...] [--voice NAME ...] [--variant NAME] [--json]` | generate missing/stale narration into `audio/`; `--dry-run` needs no key (shows each beat's voice and characters per voice) |
| `vidgen imagegen [PROJECT] [--dry-run] [--force] [--scene ID ...] [--variant NAME] [--json]` | generate the missing pictures of `generate:` params into `assets/generated/` (OpenAI Images, `OPENAI_API_KEY`); `--dry-run` needs no key and shows prompts and an estimated cost |
| `vidgen readback [PROJECT] [--variant NAME] [--beat ID ...] [--max-wer RATE] [--force] [--json]` | transcribe the narration MP3s (speech to text, `stt:`; cached in `build/readback/`) and compare them with the beat texts: word error rate per beat, words expected vs heard, a suggested fix for each (e.g. a pronunciation entry), terms misheard in several beats |
| `vidgen translate-template [PROJECT] --variant NAME [--language TAG] [--output FILE] [--json]` | write or update the variant's translation file: every text to translate with its source, keeping existing translations (stale / moved / obsolete marked) |
| `vidgen render [PROJECT] [--preview] [--scene ID ...] [--variant NAME] [--no-audio] [--keep-going] [--jobs N] [--frames] [--frames-per-beat N] [--force] [--json]` | render the scenes that changed (reusing current renders, e.g. the storyboard's) and join the video |
| `vidgen storyboard [PROJECT] [--scene ID ...] [--per-beat N] [--variant NAME] [--preview \| --final] [--width PX] [--jobs N] [--force] [--json]` | contact sheets (PNG) of the video's stills with labels and narration, to review a video without watching it |
| `vidgen lint [PROJECT] [--scene ID ...] [--rule NAME ...] [--variant NAME] [--preview \| --final] [--fail-on SEVERITY] [--jobs N] [--force] [--json]` | check the layout at the end of every beat (text off the frame or in the margins, overlapping or covered text, a callout label touching other text, text too small, low contrast, too many words) and the timing (narration too fast/slow, dead air, animations overrunning their narration or squeezed into a short beat), and the narration heard differently from its text (`readback`, after `vidgen readback`); exit code 1 on errors |
| `vidgen thumbnail [PROJECT] [--variant NAME] [--preview] [--scene ID [--beat ID\|N] [--at S] [--no-overlays]] [--jpeg] [--jobs N] [--json]` | write `<output>_thumbnail.png` from the `thumbnail:` config (a designed card, or a scene's frame) or the frame `--scene` names, a 320 px copy to look at, and legibility checks |
| `vidgen export gif\|clip [PROJECT] [--scene ID] [--from S] [--to S] [--variant NAME] [--preview] [--width PX] [--fps F] [--max-mb MB] [--with-audio] [--output FILE] [--json]` | a scene or part of the rendered video as a palette GIF (`--max-mb`: lower frame rate / width until it fits) or an MP4 clip, in `exports/` |
| `vidgen gallery [PROJECT] [--output DIR] [--types T,T] [--formats 16:9,9:16] [--theme PRESET] [--clips \| --no-clips] [--jobs N] [--force] [--json]` | render every scene type's sample (from the author guide; a project's own types from its `video.yaml`) at 16:9 and 9:16 into a Markdown gallery: an index, a page per type (stills, GIF, YAML, params, targets); default `docs/gallery` ([this repository's](docs/gallery/README.md)) |
| `vidgen slides [PROJECT] [--format html\|pdf] [--variant NAME] [--preview \| --final] [--mode beat\|scene] [--per-beat N] [--overlays \| --no-overlays] [--no-dedupe] [--image-format webp\|jpeg\|png] [--quality Q] [--max-width PX] [--audio] [--separate] [--notes] [--title-page] [--paper a4\|letter] [--output FILE] [--jobs N] [--force] [--json]` | one self-contained HTML slide deck in `exports/`: a slide per beat (or scene) from the stills, the narration as speaker notes, keyboard navigation, overview, fullscreen, optional narrated play mode; `--format pdf`: a PDF (slide pages or `--notes` pages, `--title-page`, bookmarks by chapter; needs `schu-video-generator[pdf]`) |

`PROJECT` is a project folder or its config file (default: the current folder).
`render` renders only the scenes whose render is missing or out of date (their config, audio,
assets, extensions or vidgen changed: the same check as `storyboard`), so a render after a
storyboard of the same format just joins. Options: `--force` renders every scene again;
`--preview` uses the `preview` resolution; `--scene ID` re-renders only those
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
  translations/       # optional: translation files of language variants (vidgen translate-template)
  audio/              # generated narration: <beat_id>.mp3 + .hash (keep it; it cost money)
  build/              # intermediate render files, --frames stills + layout, storyboards (safe to delete)
  exports/            # vidgen export: GIFs and clips; vidgen slides: HTML and PDF decks
  my_video.mp4  my_video.srt  my_video_chapters.txt  my_video_thumbnail.png  my_video_preview.mp4 ...
```

## Examples and docs

- [examples/minimal](examples/minimal) — the core built-in scene types (title, bullets, icon
  grid, charts, image, quote, equation, code, cards) and beat actions, no Python:
  `vidgen render examples/minimal --preview [--variant vertical]`; burned-in captions with
  `--variant subtitled`, 9:16 karaoke captions with `--variant social`, a partly translated
  Brazilian Portuguese version with `--variant pt` (`examples/minimal/translations/pt.yaml`).
- [examples/gallery](examples/gallery) — every other built-in scene type once (stat, chapter,
  comparison, table, timeline, diagram, process, network, scatter, histogram, pie, heatmap, map,
  screenshot, video clip, equation derivation, code walkthrough), overlays (a watermark, a
  lower third, a progress bar, a chapter indicator), sound effects, a ducked music bed,
  transitions (crossfades, colour fades, a push, a wipe), two carried objects, four chapters
  (in the MP4 and `gallery_preview_chapters.txt`) and a designed thumbnail:
  `vidgen storyboard examples/gallery [--variant vertical]`, `vidgen render examples/gallery --preview`,
  `vidgen thumbnail examples/gallery`, `vidgen export gif examples/gallery --preview --scene share`,
  `vidgen slides examples/gallery` (an HTML deck with an overview by chapter),
  `vidgen slides examples/gallery --format pdf --notes` (a PDF with notes pages and chapter bookmarks).
- [examples/custom_scene](examples/custom_scene) — "How a bicycle gear works": built-ins plus a
  custom scene type with a helper module, a project icon, a vertical variant and a hook.
- [examples/kphi3](examples/kphi3) — a real 4-minute paper video whose eight bespoke scenes all
  live in its `extensions/` folder (narration MP3s included, so it renders without a key).
- [examples/plan](examples/plan) — `outline.md`, a 2½-minute explainer outline, and the draft
  `video.yaml` that `vidgen plan examples/plan/outline.md -o examples/plan/video.yaml --force`
  writes from it (unedited: 19 scenes with chapters, no `vidgen lint` findings; the `# TODO:`s
  are what an author still has to do).
- [docs/gallery](docs/gallery/README.md) — every built-in scene type rendered (16:9 and 9:16
  stills, a GIF each) with its YAML, params and targets; regenerate with `vidgen gallery`.
- [docs/CONFIG.md](docs/CONFIG.md) — every config key and built-in scene type.
- [docs/EXTENDING.md](docs/EXTENDING.md) — writing scene types, actions, overlays, helpers, theme tokens and hooks;
  layout regions (`region("header")`, `grid`, `place`, `readable_text`) that adapt to 16:9 and 9:16.
- [DESIGN.md](DESIGN.md) — architecture and internal contracts.

## Your content and third-party services

- The MIT licence covers the software, not the videos you make with it or the files you add.
- Use only images, clips, screenshots, music and quotes you own or have permission to use
  (screenshots of other products may also show their trademarks).
- Narration from ElevenLabs and pictures from OpenAI are subject to those providers' terms (for
  example, plan limits on commercial use; cloning a voice requires the speaker's consent).
- The built-in fonts (SIL Open Font License), Lucide icons (ISC), Natural Earth map data (public
  domain), sound effects and music beds may be used in your videos, including commercially. No
  attribution is required in a video (the OFL and ISC notices apply to redistributing the files
  themselves; Natural Earth asks for none, though "Made with Natural Earth" is appreciated).
  Details: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Working on schu-video-generator

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
