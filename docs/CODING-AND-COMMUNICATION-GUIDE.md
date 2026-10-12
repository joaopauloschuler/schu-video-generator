# Coding and Communication Guide

Rules for how agents work on schu-video-generator and how they report that work. `CLAUDE.md`
lists the Python basics (Python >= 3.10, `pathlib`, `encoding="utf-8"`, `VidgenError`,
subprocess rules, `vidgen.api` as the only extension surface) and the git and handoff steps.
This guide says when to write code at all, what to name it, where to put it, how to run tests
on a small machine, and how to describe the result. It adapts
`neural-api/docs/CODING-AND-COMMUNICATION-GUIDE.md` to this Python project.

Each entry states the problem, the rule, and why it matters. Rules are added as we find them.

## Menu

| # | Rule | Scope |
| --- | --- | --- |
| [1](#1-do-not-write-code-unless-asked-or-authorized) | Do not write code unless asked or authorized | process |
| [2](#2-names-must-be-meaningful-and-precise) | Names must be meaningful and precise | code |
| [3](#3-before-adding-code-look-for-code-that-already-does-it) | Before adding code, look for code that already does it | code |
| [4](#4-put-new-code-in-the-right-module-and-keep-the-public-surface-small) | Put new code in the right module; keep the public surface small | code |
| [5](#5-reuse-instead-of-copypaste) | Reuse instead of copy/paste | code |
| [6](#6-comment-budget) | Comment budget | code |
| [7](#7-every-test-render-and-lint-run-has-a-memory-cap-and-a-timeout) | Every test, render and lint run has a memory cap and a timeout | tests |
| [8](#8-run-the-tests-that-cover-the-change-not-the-whole-suite) | Run the tests that cover the change, not the whole suite | tests |
| [9](#9-tests-must-be-cheap) | Tests must be cheap | tests |
| [10](#10-report-progress-while-long-work-runs) | Report progress while long work runs | process |
| [11](#11-write-to-the-user-in-clear-technical-language) | Write to the user in clear technical language | communication |
| [12](#12-name-the-actor) | Name the actor | communication |
| [13](#13-repeat-the-defined-term-never-vary-it-for-style) | Repeat the defined term; never vary it for style | communication |
| [14](#14-watch-for-colliding-terms) | Watch for colliding terms | communication |
| [15](#15-prefer-the-ordinary-word) | Prefer the ordinary word | communication |

## 1. Do not write code unless asked or authorized

**Problem.** An agent asked to *review*, *explain* or *plan* answers by editing files. The user
now has a diff they did not ask for, mixed in with the answer they did ask for.

**Rule.** Write code only when the request asks for it ("fix", "add", "implement") or the user
has approved the change in this conversation. When a review finds something worth changing, say
what you would change and why, then wait. Two cases that are *not* approval:

- The user approved a change to file A. That does not cover file B. (A fix to `stt/faster_whisper.py`
  that also changes `sfx.decode_audio` must say so before the edit, or at least in the report.)
- The fix looks obvious and small. Small fixes are cheap to describe, so describe them first.

The same holds for a subagent's prompt: name the files it may change, and ask it to report any
other file it had to touch.

**Why.** The user decides what enters the codebase. An unrequested edit costs a review they did
not plan for.

## 2. Names must be meaningful and precise

**Problem.** `d`, `tmp`, `data2`, `do_it` force every reader to work out what the code holds.
Worse is a name that was right before an edit and is wrong after it.

**Rule.** A name states what the thing *is*, in vidgen's vocabulary:

- **Domain words** are fixed: *project*, *scene*, *beat*, *variant*, *overlay*, *theme token*,
  *deliverable* (the MP4, SRT, chapter list and thumbnail in `output/`), *build* (cache in
  `build/`), *export* (files in `exports/`). Use them exactly; do not invent near-synonyms.
- **Variables** name the quantity and its unit when it has one: `beat_seconds`, `sample_rate`,
  `gain_db` — not `t`, `sr`, `g`. Short names are fine for a tight local scope with an obvious
  meaning (`d` for the beat length inside a `with self.narrate(i) as d:` block is the documented
  idiom).
- **Functions** name the effect, and the effect must match the name. `output_path()` returns a
  path and creates nothing; a function that writes files says so (`write_…`, `make_…`).
- **Booleans** read as a predicate: `is_preview`, `has_audio`, `bare`.
- **A name must not claim more than the code checks.** A function called `validate_assets` that
  only checks the files exist, not that they decode, will stop the next reader from looking.

**Why.** The name is how the next agent finds the code, and a wrong name misleads on every read.

## 3. Before adding code, look for code that already does it

**Problem.** A second audio decoder, a third `run()` helper, a private text-fitting routine inside
one scene. Each copy is a place where a later fix lands in only one of them.

**Rule.** Before writing a routine, search for it: `grep -rn` the concept, the likely name and
the likely caller in `src/vidgen/`. Known homes:

- audio decoding and WAV writing: `vidgen/sfx.py` (`decode_audio`, `write_wav`);
- ffmpeg calls and version checks: `vidgen/render/ffmpeg.py`;
- layout: `shrink_to_fit` in `vidgen/layout.py`, `place` and regions in `vidgen/regions.py` (both exported by `vidgen.api`);
- project paths (`output_dir`, `output_path`, `asset`): `vidgen/project.py`.

If something close exists, extend it (a keyword argument with a default that keeps today's
behaviour) instead of cloning it. If nothing exists, say so in the commit message: that sentence
is the record that the search happened.

**Why.** Duplicated logic drifts apart, and every fix then has to be found twice.

## 4. Put new code in the right module; keep the public surface small

**Problem.** A helper lands in the scene that first needed it, and three scenes later it has been
copied twice. Or an internal helper becomes importable from `vidgen.api` by accident, and now it
can never change.

**Rule.**

- A helper used by one function stays a private function (`_name`) next to it.
- A helper used by several scenes goes in the shared module for its kind (rule 3), not in a
  scene file.
- Behaviour shared by scene types goes on the base class (`NarratedScene`) only if every scene
  type can use it correctly.
- Only what extension authors need goes in `vidgen.api`. Adding to it is a change to the public
  interface: document it in `DESIGN.md`.

**Why.** The right home makes the next user of the code a one-line import. The wrong one either
duplicates it or freezes it.

## 5. Reuse instead of copy/paste

**Problem.** Two loops that differ in one constant, two scenes that build the same chip. They
start identical and drift: the cookbook examples ended up with three `run()` functions whose
lower bounds differ (0.3 vs 0.25) and two `rough_blob` functions with different shapes.

**Rule.** When you catch yourself pasting a block and changing two tokens, factor it: a
parameter, a shared helper, a loop over data. Example files that users copy one by one are the
one exception; if a file must stay self-contained, its docstring says so.

**Why.** Near-copies are where "we fixed that already" bugs come from: the fix went to one copy.

## 6. Comment budget

**Problem.** Long docstrings and line-by-line comments rot faster than the code, and nobody reads
them.

**Rule.**

- A docstring states what the function does and any contract the signature cannot show (units,
  what it creates on disk, what the caller must do first). Aim for one or two lines; a public
  function in `vidgen.api` may need a short paragraph.
- Inside a function, comment only what the code cannot say: a numeric subtlety, a workaround for
  a library version, a deliberate deviation from the obvious approach.
- Do not comment what the line already states.
- No history in comments ("was 0.7, now from d"). That belongs in the commit message.

If a function needs a long explanation, that is usually a naming (rule 2) or decomposition
problem.

**Why.** Every comment is read on every visit and must be kept true on every edit.

## 7. Every test, render and lint run has a memory cap and a timeout

**Problem.** The development machine has 3 GB of RAM and 4 cores. On 2026-10-11 an agent ran two
full test suites in parallel; Manim renders filled the memory and the machine rebooted.

**Rule.** Run every `pytest`, `vidgen render`, `vidgen storyboard` and `vidgen lint` command like
this:

```bash
systemd-run --user --scope -p MemoryMax=1500M -p MemorySwapMax=0 --quiet \
  timeout 300 python -m pytest -q -p no:cacheprovider <test files>
```

- One heavy command at a time. Never two in parallel, never in the background while another
  runs, never `pytest -n` (xdist), and `--jobs 1` for vidgen commands.
- A command killed by the cap or the timeout is a **result**: report it ("killed at 1.5 GB",
  "timed out after 300 s"). Do not retry with higher limits without the user's agreement.
- `ulimit -v` is not a substitute: numpy, PyAV and torch reserve far more virtual memory than they
  use, so an address-space cap breaks imports long before real memory runs out.

**Why.** A capped failure tells you how much memory the code needs. An uncapped failure costs the
user their machine and their session.

## 8. Run the tests that cover the change, not the whole suite

**Problem.** The full suite takes about 10 minutes on 2 cores (HANDOFF Step 65), and much longer
on one. Running it for a two-line fix wastes the user's time, and running it in parallel crashes
the machine (rule 7).

**Rule.**

1. Run the test files of the modules you changed, without render tests:
   `-m "not render" tests/test_<module>.py`. Find other affected files with `grep -rln` on the
   function or string you changed, not by running everything.
2. Run render tests only for files whose rendering behaviour you changed, one file at a time.
3. Keep the total under about 3 minutes for a step. If covering the change needs more, stop and
   say how much more and why.
4. Report exactly what you ran (files, counts, seconds) and what you did not run. "Tests pass"
   without a list is not a report.
5. The full suite is the user's call, before a merge. An agent runs it only when asked.

When a test fails, check whether it fails on the unchanged code before blaming your change: run
just that test in a `git worktree` of `HEAD` in the scratchpad (never `git stash` the user's
tree). Several tests need `ffmpeg` on `PATH`; a missing tool is an environment problem to report,
not a code bug to fix.

**Why.** The user's time is the scarce resource. A targeted run answers "did I break what I
touched?" in seconds; the full suite answers a question nobody asked yet.

## 9. Tests must be cheap

**Problem.** A test that renders five scenes at 480p to check one file name costs a minute and
half a gigabyte for a fact a path function could give in a millisecond.

**Rule.**

- Test the logic without rendering when you can: call the path function, the config model, the
  layout function, the CLI parser.
- A test that must render uses the smallest project that shows the behaviour: one scene, one or
  two short beats, 160x90 at 5 fps, `tmp_path`, `@pytest.mark.render`. Mark anything over a few
  seconds `@pytest.mark.slow` as well.
- Share one render between several assertions (a module-scoped fixture) instead of rendering
  again per test.
- The target is a full suite under **5 minutes** end to end on this machine. A new test that
  pushes it past that needs a reason in the commit message.

**Why.** Every test is paid for on every run, by every agent, for as long as the test exists.

## 10. Report progress while long work runs

**Problem.** An agent starts a ten-minute job and says nothing. The user waits without knowing
what for, and learns of a crash only at the end — or from the machine rebooting.

**Rule.**

- Before a command that may take over a minute, say what it is and why ("rendering
  `examples/minimal` as a preview, to check the MP4 lands in `output/`").
- A subagent appends one line `HH:MM:SS <message>` per stage to `<scratchpad>/progress.log`:
  stage start, each test command with its counts and seconds, every failure, timeout or kill, and
  the commit hash. The main session watches that file and relays it to the user.
- Report the first real signal (a failure, a stall, a kill) as soon as it appears, instead of
  waiting for the exit code. Stop early when the answer is already in.

**Why.** The user can only decide what to do about work they can see.

## 11. Write to the user in clear technical language

**Rule.** Be technical *and* plain:

- **Lead with the result**, then the evidence.
- **Name the thing**: `Project.output_dir` in `src/vidgen/project.py`, not "the path code".
- **Quantify with units**: "16 passed in 79 s", "108 s for a preview render".
- **One idea per sentence**, ordinary words, technical terms only where they are the precise term.
- **State what you did not do**: skipped tests, unchecked assumptions, files you touched that
  were not asked for.
- **Do not hedge a verified result, and do not present an unverified one as fact**: "27 passed"
  or "not run", never "should work".

**Why.** The user reads to make a decision. Vague text forces another round trip; dense text
forces them to decode instead of decide.

## 12. Name the actor

**Problem.** "The audio is decoded", "the folder is created", "the cache is reused" — each drops
the one fact the reader needs: what does it, and when.

**Rule.** Every claim about behaviour names who does it:

| Actorless | Named actor |
| --- | --- |
| "The audio is decoded." | "`FasterWhisperProvider.transcribe` decodes the clip with `sfx.decode_audio` before calling faster-whisper." |
| "The output folder is created." | "`join_scenes` in `render/pipeline.py` creates the `output/` folder; `Project.output_dir` only returns the path." |
| "The scene render is reused." | "`render` reuses a scene's render while its config, audio, assets and extensions are unchanged." |

The same applies to your own work: "the test was fixed" hides whether you fixed the test or the
code under it.

**Why.** The actor is the address: it tells the reader where to look and whether a step happens
on its own or only when someone calls it.

## 13. Repeat the defined term; never vary it for style

**Rule.** Once a term is defined, use exactly that term every time. A *beat* stays a beat — not
"a line", "a segment", "a clip". If you use a different word, the reader may assume you mean a
different thing, so a synonym is a bug in the text.

**Why.** A consistent term can be searched and checked. A varied one makes the reader rebuild a
model you already had.

## 14. Watch for colliding terms

**Problem.** The same word means different things nearby, and the text never says so. Live
collisions in vidgen:

- **output** — the `output:` key (a base file name), the `output/` folder (`output_dir`), the
  `--output FILE` option of `export`, `slides` and `translate-template`, and "command output"
  (stdout, `--json`).
- **export** — the `vidgen export` command and its `exports/` folder, versus exporting chapters
  into the MP4 or `_chapters.txt`.
- **preview** — the `--preview` format (`preview:` in the config), `vidgen render --preview`'s
  `_preview.mp4`, and a quick look in general.
- **source** — `music: {source: ...}`, a paper or URL the video cites, and source code.
- **render** — `vidgen render` (the whole video), rendering one scene with Manim, and the
  `@pytest.mark.render` marker.
- **variant** — a config variant (`--variant vertical`), versus a version of a file.

**Rule.** When two meanings are live in the same text, name the distinction once at first use,
then keep each sense in its own fixed form (rule 13): "the `output:` base name" and "the
`output/` folder", never just "the output".

**Why.** An unnamed collision does not read as ambiguous; it reads as clear and means the wrong
thing.

## 15. Prefer the ordinary word

**Rule.** Name the thing and say plainly what the metaphor was carrying:

| Metaphor | Plain statement |
| --- | --- |
| "the API contract" | "`vidgen.api` names that extensions import; renaming one breaks every project's `extensions/`" |
| "source of truth" | "`src/vidgen/data/guide/AGENTS.md`; `AGENTS.md` is a copy that `tests/test_guide.py` compares" |
| "first-class scene" | "a scene type registered with `@scene`, so `vidgen validate` and `list-scenes` know it" |

Established terms of the field stay: render, codec, sample rate, easing, karaoke captions.

**Why.** The metaphor is always shorter than the fact and always less useful.
