# Windows check for 0.3.0

schu-video-generator 0.3.0 was built and tested on Linux only. This checklist tests it on Windows in about
30 minutes, plus the Kokoro download. Run the steps in PowerShell from a copy of the
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
pip install ".[pdf,mcp,kokoro]"
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

## What to send back

One message with the following:

- Windows version, Python version(s), ffmpeg version, MiKTeX yes or no.
- For each step 1–6: OK, or the exact error text, with the command that failed.
- The `jobs:` lines from steps 2 and 5, and the machine's RAM and CPU core count.
- One or two stills or short notes on anything that looked or sounded wrong in the videos.
