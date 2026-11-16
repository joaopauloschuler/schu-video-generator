# Windows check for 0.3.0

schu-video-generator 0.3.0 was built and tested on Linux only. This checklist tests it on Windows in about
an hour, plus the Kokoro and Chromium downloads (steps 1–6 about 30 minutes, step 7 about
30 more on a fast machine; its optional `--draft` of `examples/escapement` adds 15 to 30). Run the steps in PowerShell from a copy of the
repository. Write down what each step prints, especially anything marked **report**.
There is no `vidgen doctor` command: the steps below do that job.

## 1. Install (Python 3.12)

Use Python 3.12. It works with every extra, including Kokoro, which supports Python 3.10–3.12
only. If you can, repeat steps 1–4 with 3.10 and 3.11 later.

```
cd video-generator
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python --version
pip install .
vidgen --version
ffmpeg -version
```

- **Report**: the Python version; whether `pip install` worked, and if not, the last 20 lines
  of its output; the `vidgen --version` line (it should say `vidgen 0.3.0`); the first line of
  `ffmpeg -version` (it must be 4.4 or newer).
- If `Activate.ps1` is refused, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

## 2. Validate and a cartoon preview

```
vidgen validate examples/cartoon-rainbow-ride
vidgen render examples/cartoon-rainbow-ride --preview --no-audio --jobs auto
```

- There is no narration audio yet, so the beats are timed from their text.
- **Report**: the `jobs: N (auto: ...)` line, which shows the Windows memory reading; the
  total time; any error with its full text. Open
  `examples/cartoon-rainbow-ride/output/rainbow_ride_preview.mp4` and check that the
  characters, the bicycle, the rain, the rainbow and the room look right, with no missing or
  stray shapes. Check that the sound has birdsong, rain, fire and the `cartoon` music.

## 3. Fonts and the storyboard

```
vidgen storyboard examples/minimal --scene intro --scene listing --jobs auto
```

- These two scenes need no LaTeX. Open the PNG contact sheets in
  `examples/minimal/build/preview/storyboard/`. The title should be in Inter (a clean sans
  serif) and the code in JetBrains Mono. If you see Times New Roman
  or another fallback font, the bundled fonts did not load.
- **Report**: whether the fonts look right.

## 4. LaTeX (MiKTeX)

This step is optional: only the `equation` scene types need LaTeX.

```
vidgen render examples/minimal --preview --scene math
```

- The first run may make MiKTeX ask to install missing packages. Allow it, and tick "always"
  if MiKTeX offers it.
- **Report**: whether MiKTeX asked and which packages it installed; whether the render
  finished; whether the equation shows in `examples/minimal/output/minimal_preview.mp4`.

## 5. Kokoro narration

This step needs the Python 3.12 environment from step 1.

```
vidgen tts examples/cartoon --dry-run
vidgen tts examples/cartoon
vidgen render examples/cartoon --preview --jobs auto
```

- The first `vidgen tts` downloads the model (327 MB) into
  `%USERPROFILE%\.cache\huggingface\hub`, and spaCy's English model (13 MB).
- **Report**: the dry run's `cost:` line; how long the real run took; any message about
  espeak-ng, spaCy or the download; whether
  `examples/cartoon/output/box_kite_preview.mp4` has voices that match the mouths. Do not commit the MP3s it writes under
  `examples/cartoon/audio/`.

## 6. Optional extras

- PDF slides: `vidgen slides examples/minimal --format pdf`. It needs LaTeX from step 4,
  because the deck includes the equation scene. **Report** whether the PDF opens.
- MCP: run `vidgen-mcp --help`. If you use an MCP client, cancel a long `render` from it and
  check in Task Manager that no `python` / `ffmpeg` processes are left behind.
- Long paths: copy an example into a deeply nested folder, more than 200 characters in all, and
  run `vidgen render <it> --preview`. **Report** any "path too long" error.

## 7. Web scenes, stills and the orchestra (Phase AL)

These steps need Chromium once: `py -m playwright install chromium` (about 150 MB). Nothing
here needs narration.

```
vidgen still examples/three-finish --scene still_life --at 1 --at 3 --size preview
vidgen render examples/three-finish --preview --intermediate compact --clean-intermediates
```

- `vidgen still` writes PNGs to `examples/three-finish/exports/stills/`. **Report**: whether
  they open and show a lit still life (not black); any message about a file that is open
  elsewhere.
- During the render, `web frames N/M, ... s a frame, about ... left` progress lines should
  appear about every 10 s. **Report**: whether they do, and the summary line after the last
  frame.
- `--clean-intermediates` deletes the frames clip under `examples/three-finish/build/preview/web/`
  once the scene is rendered. On Windows a file that is still open cannot be deleted: vidgen then
  keeps that clip and prints a warning instead of failing. **Report**: whether the render
  finished; any warning about a clip it could not delete (copy its text); whether
  `build\preview\web\` is empty afterwards; whether
  `examples/three-finish/output/` has an MP4 that plays.

```
vidgen music render examples/signal-fire/assets/music/signal_fire.yaml --out signal_fire.wav
vidgen music check examples/signal-fire/assets/music/signal_fire.yaml
vidgen render examples/signal-fire --draft --jobs auto
```

- The score uses the new orchestral instruments (solo violin, cellos, horns, trumpet, choir,
  timpani, taikos, tam-tam); the render takes about a minute. **Report**: how long it took; any
  range warning; whether `signal_fire.wav` plays, with strings, brass, choir and drums, and
  ends on a major chord. Do not commit it.
- `vidgen music check` writes `signal_fire-check.png` and `signal_fire-demo.mp3` in the
  current folder. **Report**: its first lines (loudness, peaks) and whether both files open.
  Its "unsteady" note about the quiet start is expected.
- Every scene of the project has `music_data:` (the page reads the score through `ctx.music`). **Report**:
  whether the draft finished, and whether in
  `examples/signal-fire/output/` the embers, the sky and the flashes move with the music.
- Optional: `vidgen render examples/escapement --draft --jobs auto` (a 3:11 film; it first
  synthesizes the score, about 5 minutes). **Report**: the total time and whether the
  ticking stays in time with the picture.

## What to send back

One message with the following:

- Windows version, Python version(s), ffmpeg version, MiKTeX yes or no.
- For each step 1–7: OK, or the exact error text, with the command that failed.
- The `jobs:` lines from steps 2, 5 and 7, and the machine's RAM and CPU core count.
- One or two stills or short notes on anything that looked or sounded wrong in the videos.
