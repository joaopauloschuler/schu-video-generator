# Conventions for working on vidgen

Read `DESIGN.md` (the contract) and `HANDOFF.md` (what previous steps did) before changing code.

## Environment (cloud workspace)
- Python venv: `/home/claude/venv` (Python 3.13, manim 0.21, pydantic 2, pyyaml, pytest installed).
  Use `/home/claude/venv/bin/python` and `/home/claude/venv/bin/pip install -e .`.
- ffmpeg and LaTeX are installed. The Inter font is installed.
- The original one-off project lives at `/home/claude/work/kphi3_paper_video` (read-only reference,
  includes real narration MP3s in `audio/` and the finished `kphi3_video.mp4`).
- No network access to ElevenLabs. Never call the real API; mock it.

## Code
- Python >= 3.10 syntax only (the user runs 3.10–3.13 on Windows). Type hints everywhere.
- `pathlib.Path` for all paths; never build paths with string concatenation; no `shell=True`.
- Always pass `encoding="utf-8"` when reading/writing text (Windows default is not UTF-8).
- Subprocesses: use `sys.executable`, list arguments, `check=True`, capture stderr for errors.
- Public extension surface is `vidgen.api` only. Keep it stable; document changes in DESIGN.md.
- Small modules, docstrings on public functions, no dead code, no print-debugging left behind.
- Errors the user can cause (bad config, missing key, unknown scene type) raise `VidgenError`
  (defined in `vidgen/errors.py`) with a clear message; the CLI prints it without a traceback.

## Tests
- `cd /home/claude/work/video-generator && /home/claude/venv/bin/python -m pytest -q` must pass
  before you commit. Add tests for everything you build.
- Rendering tests: `@pytest.mark.render`, tiny resolution (e.g. 160x90, 5 fps), use `tmp_path`.

## Git
- Work on branch `a1` (the user's current branch). **Never push. Never add remotes.** One commit per step (you may make
  more, but the step must end with everything committed and the tree clean).
- Commit message: `Step N: <summary>` followed by a short body, then exactly these trailer lines:

      Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
      Claude-Session: https://claude.ai/code/session_019dnUhQr2V3uxDgrcPF2jrF

- Do not commit generated media (`build/`, `media/`, `*.mp4`, `*.wav`, `*.srt` outputs, `__pycache__`).
  Exception: the kphi3 example's narration MP3s/hashes under `examples/kphi3/audio/` ARE committed.

## Handoff
At the end of your step, append a section to `HANDOFF.md`:
`## Step N — <title>` with: what was built, files touched, public interfaces added/changed,
decisions/deviations from DESIGN.md (and why), known gaps / TODOs for later steps, how to test.

## Task list
`tasklist.md` is the roadmap. Each step is done by one agent, in order. Tick the boxes of your
step (`[x]` done, `[~]` partial with a note) in the same commit.
