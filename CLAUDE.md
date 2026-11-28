# Conventions for working on schu-video-generator

> **Who this is for:** agents **developing schu-video-generator itself** (its code, tests and
> docs). To **make videos with schu-video-generator**, read `AGENTS.md` instead (the author guide; also
> `vidgen guide`). The project and pip distribution are `schu-video-generator`; the command and the
> Python package stay `vidgen` (use `vidgen.DIST_NAME` in install hints). The guide is
> `src/vidgen/data/guide/`: a short entry page `AGENTS.md` (copied to the root `AGENTS.md`) and one
> file per topic (`scenes.md`, `web.md`, ...; `vidgen guide TOPIC`). When you change a command,
> scene type or param the guide names, update the topic file (and the entry page if it names it;
> then copy it to the root). `tests/test_guide.py` checks both copies and every topic.

Follow `docs/CODING-AND-COMMUNICATION-GUIDE.md`: when to write code, naming, reuse, how to run
tests on a small machine (memory cap, timeout, one at a time), progress reports, and how to write
to the user.

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
- Public extension surface is `vidgen.api` only. Keep it stable.
- Small modules, docstrings on public functions, no dead code, no print-debugging left behind.
- Errors the user can cause (bad config, missing key, unknown scene type) raise `VidgenError`
  (defined in `vidgen/errors.py`) with a clear message; the CLI prints it without a traceback.

## Tests
- Add tests for everything you build, and keep them cheap (guide rule 9): test logic without
  rendering when you can; rendering tests use `@pytest.mark.render`, tiny resolution (e.g. 160x90,
  5 fps) and `tmp_path`.
- The default run (`python -m pytest -q`) leaves out every test marked `@pytest.mark.slow`
  (`tests/conftest.py` deselects them) and takes about 3–5 minutes on the owner's 1-CPU machine
  (Step 327: 194 s, 6235 passed). `-m slow` runs only the slow ones (about 3 hours there);
  `-m "slow or not slow"` runs everything; a test named by node id (`file.py::test`) always
  runs. Mark a new test `slow` when it takes over about 0.4 s, and keep the default run under
  5 minutes (guide rule 9).
- Before you commit, run the tests that cover your change, not the whole suite (guide rule 8),
  each command under a memory cap and a timeout (guide rule 7). Never run tests in parallel
  (`-n`) or two suites at once. The full suite is run only when the user asks.

## Git
- Work on the user's current branch (check with `git branch --show-current`; do not switch). **Never push. Never add remotes.** One commit per step (you may make
  more, but the step must end with everything committed and the tree clean).
- Commit message: `Step N: <summary>` followed by a short body, then exactly these trailer lines:

      Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
      Claude-Session: https://claude.ai/code/session_013r6GmPmW4RZKBzpmNDgw6t

- Do not commit generated media (`build/`, `media/`, `*.mp4`, `*.wav`, `*.srt` outputs, `__pycache__`).
  Exception: the kphi3 example's narration MP3s/hashes under `examples/kphi3/audio/` ARE committed.

## Task list
`tasklist.md` lists open work only. Each step is done by one agent, in order. In the same commit,
remove your step's items when they are done (completed work lives in the git history), leave a
partly done item as `[~]` with a note on what is left, and raise the file's "Next step number".
