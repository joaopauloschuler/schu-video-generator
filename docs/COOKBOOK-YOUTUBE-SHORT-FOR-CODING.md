# Cookbook: a YouTube Short about code

How to make a 30–50 s vertical video that shows a piece of source code and what it does, with
schu-video-generator. The numbers below come from a Short that went through two visual rounds, real narration,
a readback check and a final render. The general craft (hooks, QA, credits, voices) is in
[COOKBOOK.md](COOKBOOK.md) (§15 for vertical shorts); `vidgen guide social` and `vidgen guide
workflow` give the rules at a glance. This page is about what is special to **code on a phone**.

---

## 1. Format and length

| | value |
|---|---|
| frame | 9:16, `format: {width: 1080, height: 1920, fps: 30}` |
| preview | `preview: {width: 540, height: 960, fps: 15}` |
| length | 30–50 s (the example Short: 47 s); hard maximum 60 s. YouTube accepts longer Shorts, but a code Short past ~50 s loses viewers |
| beats | one sentence each, 8–12 words, about 3–4.5 s spoken |
| scenes | 6–8, a new picture every 3–5 s |
| voice rate | 2.8–3.2 written words per second (a calm documentary voice) |

## 2. Structure

| part | time | what is on screen | scene |
|---|---|---|---|
| hook | 0–3 s | one true, surprising number or claim in big type ("10 / lines of Python") | `stat`, or a project scene with the whole file as a dim backdrop |
| code steps | 3–30 s | one key line or block per beat, large, with a 2–4 word note | `code_focus` (project, §4) or `code` / `code_walkthrough` |
| payoff | ~5 s | the output, in a terminal; labelled **example output** when it is illustrative | `terminal` (the command typed, then the output you write) |
| what you skip | ~4 s | 3 big icon rows: what the reader does not need ("No installs") | `icon_grid` (`reveal: all`) or a project scene |
| call to action | ~4 s | one big icon, a short bold line, the URL large (split it over two lines if long) | `end_card` or a project `cta` |

- The hook must be **true and checkable** (a line count, a size, a run time you measured), and
  readable without sound: the number in the accent colour, 2–4 words under it.
- No title card, no "in this video". The first frame is the cover in the feed.
- No chapter cards either: every second of a Short goes to new content. (In regular videos over
  about 4 min, show each chapter card for about 3.5 s, `duration: 3.5`; see `docs/COOKBOOK.md`.)
- End on the call to action, said once ("The full script is linked below").

## 3. Layout of the vertical frame

Measured on the final 1080x1920 frames (schu-video-generator's frame is 8 units wide, 135 px per unit):

| band | pixels from the top | what goes there |
|---|---|---|
| top margin | 0–68 | nothing (the default safe margin, 0.5 units; 0.6 units = 81 px at the sides) |
| title band | ~90–190 | the scene's heading, ~78 px type (`chart_title(..., size="heading")`) |
| code | ~370–980 | the code window, full safe width (81–999 px) |
| note | under the window, ~0.45 units gap | 2–4 words on a plate, gold tick or gold text |
| captions | ~1300–1640 | karaoke captions; the scene's safe area ends above them (`reserve`) |
| bottom | ~1640–1920 | nothing: YouTube's title, channel and music line sit here |

- **YouTube's overlays**: the bottom ~15–20 % (title, channel, description) and a column of
  buttons on the right of the lower half. Bottom captions in 9:16 are raised by 12 % of the safe
  height (~215 px) by default, so they clear the bottom; keep text out of the right ~120 px
  below the middle of the frame. Check one frame on a real phone before publishing.
- **Captions never cover code.** Captions at `position: bottom` reserve their band, so scenes lay
  out above it; lint's `overlay_overlap` reports anything under them.
- **Fill the frame.** The failure of the first cut: the code sat small in the middle third, with
  empty bands above and below, and a terminal one fifth of the frame high. Make the code window
  span the safe width and centre the window + note between the title band and the captions.
- At the end of every beat, nothing should be half-built: a list that appears one item at a
  time leaves a mostly empty still. Bring all items in by ~60 % of the beat.
- **Cartoon characters in a Short** (a host who explains the code on a `stage`, a mascot in a
  platform `level`): set **`character_size: large`** for the Short (in its 9:16 variant if the
  video also has a 16:9 one). In 9:16 a character's size is measured against the frame's width,
  so at the default `medium` a character is only about a quarter of the frame's height and its
  face is hard to read on a phone; `large` makes it 1.4 times bigger (on a level the tiles and
  props grow with it, about 6 tiles across and 10 up). Captions, code and other text keep their
  size. `vidgen lint`'s `small_speaker` warns when a speaking face is still too small; a beat's
  `shot: closeup <name>` fixes one line. On a level, `level: {follow: <name>}` keeps the hero in
  the narrow frame as it walks and jumps. An isometric place (`iso:`) takes no `character_size`:
  the whole place fits the frame's width, so in 9:16 keep its map narrow and give every spoken
  line a `shot:` (or `follow` a walker); name tags say who speaks in the wide views. See CONFIG.md
  "Character size (`character_size`)" and "Isometric places (`iso`)".

  ```yaml
  variants:
    short:
      format: {width: 1080, height: 1920, fps: 30}
      character_size: large
  ```
- **Architecture in a Short** (`iso_diagram`): the iso view draws a row wider than tall, so a
  tall frame needs the diagram's long direction down the frame. Without `at`, `arrange: auto` is
  a zigzag in 9:16; with `at`, `portrait_grid: auto` slants the grid down the frame when that
  draws it larger. Either way keep it to about five blocks with short labels ("App 1", "Cache")
  for a phone; a stack lists its layers under it with colour swatches. `focus` on the part the
  narration is about (it lands clear of the captions) and `focus: diagram` back. Check the 9:16
  storyboard: `vidgen lint`'s `iso_labels` names a label lying on another block or connector.
  The `short` variant of `examples/iso-web-page` shows the limit: its seven-block diagram fits,
  but its blocks come out small on a phone.

## 4. Showing the source code

**Size.** Phone-readable code at 1080 px wide is about **56 px font, ~41 px cap height, at most
~24 columns per row** across the safe width. That is twice lint's floor (`min_font`: 27 px cap
height at 1080). Choose the lines so they fit 24–28 columns; long lines wrap.

**Overview, then zoom.** Show the whole file once, small (a dim backdrop behind the hook, or a
`code_walkthrough` step with no highlight), so viewers see it is real and short. Then show one
line or block per beat, large.

**Never edit the code you show.** Show subsets of the real file: pick lines, and only remove the
common indentation of the lines shown together. If you must simplify, say "adapted" on screen.
Keep the original line numbers (`excerpt:` does in `code_walkthrough`), and name the place: a
window bar "top_words.py · line 7" lets a viewer find it in the repository.

**Wrapping rules.**
- Colour first, then wrap: lex the whole file, then split the coloured text. Wrapping first makes
  a comment's continuation lex as code (an apostrophe opens a string). schu-video-generator's `code` and
  `code_walkthrough` do this (they colour before wrapping and break at token boundaries).
- Break after a space, else at a token boundary; never start a row with `)`, `;` or `,`; cut a
  word only when it is longer than a row (then after `/`, `-`, `.` or `_`).
- Continuation rows get a hanging indent of 2 spaces.

**Highlight and dim.** One accent band or bar on the lines being talked about; dim the rest
(`code` `highlight:` and `code_walkthrough` `steps:` do both). Point at lines from beat actions
with `line<N>` / `lines:a-b` targets. In 9:16, `focus: true` zooms the camera and can crop the
title: check the storyboard.

**Built-in or project scene?**

| | built-in `code` / `code_walkthrough` | project `code_focus` (below) |
|---|---|---|
| columns per row | at least 32 (they keep the listing wide) | 24 (`columns`) |
| type size | about two thirds of the target in 9:16 | ~41 px cap height |
| setup | none, validates anywhere | one file in `extensions/` |
| use when | 16:9, or a Short whose lines are ≤ 32 columns | most code Shorts |

A project-local scene type, `extensions/code_focus.py`, using only `vidgen.api` (plus Pygments,
which schu-video-generator installs). It shows step *i* at beat *i*: the step's lines on a full-width plate,
large, and the note under it. It validates and lints clean (0 findings) on the example below:

```python
"""code_focus: one key line or block of a source file per beat, phone-large (9:16)."""

from __future__ import annotations

from html import escape
from itertools import groupby

from pygments import lex
from pygments.lexers import get_lexer_by_name
from pygments.styles import get_style_by_name

from vidgen.api import *

Chars = list[tuple[str, str]]  # (character, colour) pairs of one line


def coloured_lines(source: str, language: str, style_name: str, default: str) -> list[Chars]:
    """Colour first: lex the whole file, so a comment stays a comment when its line wraps."""
    style = get_style_by_name(style_name)
    lines: list[Chars] = [[]]
    for token, value in lex(source, get_lexer_by_name(language)):
        colour = style.style_for_token(token).get("color")
        for ch in value:
            if ch == "\n":
                lines.append([])
            else:
                lines[-1].append((ch, f"#{colour}" if colour else default))
    return lines


def wrap(chars: Chars, columns: int, hang: int = 2) -> list[Chars]:
    """Then wrap: after a space, else at a token (colour) change; continuations indented."""
    lead = len(chars) - len("".join(c for c, _ in chars).lstrip(" "))
    rows: list[Chars] = []
    floor = lead + 1  # never cut inside the indentation
    while len(chars) > columns:
        span = range(columns, floor, -1)
        cut = next((k for k in span if chars[k][0] == " "), 0)
        cut = cut or next((k for k in span if chars[k - 1][1] != chars[k][1] and chars[k][0] not in ")]};:,."), columns)
        rows.append(chars[:cut])
        rest = chars[cut:]
        while rest and rest[0][0] == " ":
            rest = rest[1:]
        chars = [(" ", "")] * (lead + hang) + rest
        floor = lead + hang + 1
    return rows + [chars]


def to_markup(rows: list[Chars]) -> str:
    out = []
    for row in rows:
        runs = [(colour, escape("".join(c for c, _ in run), quote=False)) for colour, run in groupby(row, key=lambda p: p[1])]
        out.append("".join(f'<span foreground="{c}">{s}</span>' if c else s for c, s in runs) or " ")
    return "\n".join(out)


class FocusStep(SceneParams):
    lines: str | int
    """One line ('7') or a block ('5-6') of the file, numbered as in the file."""
    note: str = ""


@scene("code_focus")
class CodeFocus(NarratedScene):
    """Step i at beat i: only that step's lines, as large as `columns` allows; a note below."""

    outro = 0.4

    class Params(SceneParams):
        path: str
        language: str = "python"
        title: str = ""
        steps: list[FocusStep] = Field(min_length=1)
        columns: int = 24
        """Characters per row across the safe width: sets the font size."""
        style: str = "one-dark"

    def construct(self) -> None:
        p, area = self.params, self.safe_area
        source = self.project.asset(p.path).read_text(encoding="utf-8")
        lines = coloured_lines(source, p.language, p.style, self.theme.color("text"))
        heading = chart_title(p.title, size="heading", area=area) if p.title else None
        top = heading.get_bottom()[1] - 0.4 if heading else area.y1
        ref = self.markup("0" * p.columns, size=30, role="code")
        size = 30 * (area.width - 0.8) / ref.width
        blocks = []
        for step in p.steps:
            a, _, b = str(step.lines).partition("-")
            shown = lines[int(a) - 1 : int(b or a)]
            indent = min(len(l) - len("".join(c for c, _ in l).lstrip(" ")) for l in shown if l)
            rows = [r for l in shown for r in wrap(l[indent:], p.columns)]
            code = self.markup(to_markup(rows), size=size, role="code")
            plate = RoundedRectangle(width=area.width, height=code.height + 0.8, corner_radius=0.2, stroke_width=0)
            plate.set_fill(self.theme.color("surface"), 1)
            code.move_to(plate).align_to(plate, LEFT).shift(RIGHT * 0.4)
            block = VGroup(VGroup(plate, code))
            if step.note:
                note = self.text(step.note, size="subtitle", color="highlight")
                block.add(note.scale_to_fit_width(min(note.width, area.width)))
            block.arrange(DOWN, buff=0.5).move_to([area.center[0], (top + area.y0) / 2, 0])
            blocks.append(block)
        shown_block = None
        for k, (beat, d) in enumerate(self.narrate_all()):
            new = blocks[min(k, len(blocks) - 1)]
            if shown_block is None:
                self.play(*([FadeIn(heading)] if heading else []), FadeIn(new, shift=UP * 0.2), run_time=0.5)
            elif new is not shown_block:
                self.play(FadeOut(shown_block, shift=UP * 0.2), FadeIn(new, shift=UP * 0.2), run_time=0.5)
            shown_block = new
        self.finish()
```

```yaml
- id: read
  type: code_focus
  params:
    title: "top_words.py"
    path: assets/top_words.py
    steps:
      - {lines: "5-6", note: "Read, lower-case, split"}
      - {lines: 7, note: "Count and rank"}
  beats:
    - text: "Read the file, lower-case it, and split it into words."
    - text: "Counter tallies every word, and most_common ranks them."
```

Easy additions in the same file: a window bar with three dots and "file · line N", a gold bar
beside the highlighted rows, a `self.target("listing", ...)` for beat actions, the whole file as
a dim backdrop for the hook. See [EXTENDING.md](EXTENDING.md) for the scene API. Editing any file
in `extensions/` re-renders every scene, so batch your edits.

**Code that changes: `code_morph`.** To show a fix, a refactor or an optimisation, write the
versions and let schu-video-generator find the difference: what both share glides into place, new lines grow
in, removed lines fade out. Mark the new lines with `highlight: changed` and morph on the word
that names the change:

```yaml
- id: faster
  type: code_morph
  params:
    title: "fib.py"
    versions:
      - "def fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)"
      - code: "@cache\ndef fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)"
        highlight: changed
  beats:
    - text: "This version computes the same values again and again."
    - text: "One decorator, a cache, and each value is computed once."
      actions: [{reveal: version2, at: "@cache"}]   # the morph starts on the word (1.5 s)
```

The versions share one font size and wrap width (`code`'s phone rules), so keep each version
short: a morph reads best when 1–3 lines change. Write every version as real code (§10).

**The output: `terminal`.** A terminal window types each step's command at a prompt and then
shows the output **you** write (schu-video-generator runs nothing): step *i* at beat *i*, or the output on a
word (`{reveal: output1, at: "@prints"}`). `code: {path: ..., highlight: 7}` shows the listing
above it in 9:16; after a `code` or `code_morph` scene, `carry: ["listing -> code"]` with
`transition: cut` glides the listing into place. Keep a session to a few rows: one command and
its output fill a phone frame best. Label output that is not from a real run (§7).

## 5. Colours and type

- **Dark background, not pure black**: e.g. `#0A0E16`, with a `surface` of `#131A27` for code
  windows and plates. Text off-white (`#ECEEF2`), not pure white.
- **One accent colour** for "look here": a warm gold (`highlight: "#F5C76B"`) for the hook
  number, the highlight bar, the notes and the spoken word in the captions. A second, calm colour
  (soft blue `#7FB8FF` as `primary`) for icons and links. Red only for "no" crosses.
- **Syntax palette**: a dark Pygments style with good contrast on the window colour
  (`code_style: one-dark` worked; `github-dark` is the default). Comments must still pass contrast.
- **Consistent theme**: one preset (`dark_tech`) with your overrides in `theme:`, for every scene
  and the thumbnail. `vidgen list-themes` prints the contrast ratios; `vidgen lint` checks every
  text (`contrast`: 4.5:1, 3:1 for large text).
- **Type**: Inter for words, JetBrains Mono for code (the defaults). Headings ~78 px, labels in
  the benefits list bold.
- **One colour per concept**: give the two or three ideas the Short is about a colour each, once,
  in `terms:` (`terms: {cache: primary, recursion: secondary}`). schu-video-generator paints those words
  in every title, note, chart label and caption (karaoke too), so the viewer links "blue" to
  *cache* across scenes; code listings keep their syntax colours. Use colours other than the
  `highlight` gold (that is the "look here" colour and the spoken word in the captions), and at
  most about five; `vidgen lint`'s `concept_colors` warns otherwise
  ([COOKBOOK.md](COOKBOOK.md) §12, "Same term, same colour").

## 6. Captions

```yaml
overlays:
  - type: captions
    style: karaoke        # 1–3 big bold words at a time, the spoken one in `highlight`
    position: bottom      # raised above the phone UI in 9:16; reserves its band
voice: {timestamps: true} # exact word times (ElevenLabs, same price); Kokoro English: automatic
```

- Most people watch muted: captions are not optional.
- Keep the defaults (`max_words: 3`, `title` size, bold). The emphasis colour is the theme's
  `highlight`, so it matches the code highlight.
- Captions show the **written** words; `pronunciation:` changes only what the voice says.
- A cue can split a multi-word name ("Visual | Studio Code"): reword the beat if that reads badly.
- The words of `terms:` keep their colour in the captions (the spoken word still turns gold
  while it is said); the plate is made more opaque when a colour needs it to read.

## 7. Output, benefits, call to action, thumbnail

- **Output scene**: a large terminal, the command typed with a cursor, then the output in the
  accent colour. If the output is not from a real run of exactly that code, label it **example
  output** on screen (and say "an example" in the description).
- **What you skip**: 3 rows of a big icon in a disc plus a 1–2 word bold label, evenly spaced
  down the frame ("No installs", "No regex", "One file"). Only claims the source supports.
- **Call to action**: a big icon (a star, ~2.3 units) with a soft halo and one gentle pulse, a
  bold title (~78 px), the URL in mono, split over two lines if needed (`["example.com/",
  "my-project"]`). Give the end ~1 s of hold.
- **Thumbnail** (the cover in the Shorts feed; 1080x1920):

```yaml
thumbnail:
  title: "Top words, 10 lines of Python"   # ≤ 6 words, as large as fits
  subtitle: "no installs, one file"
  icon: file-text
  jpeg: true                               # also a JPEG under YouTube's 2 MB limit
```

  Look at `build/.../thumbnail/<name>_small.png` (the size YouTube shows in grids) before
  publishing.

## 8. Narration and pronunciation

- Short spoken sentences, one per beat, concrete verbs. Say what the code does, not the syntax
  ("Counter tallies every word", not "we call the Counter constructor").
- **A documentary-style voice**: calm, warm, authoritative (an ElevenLabs "storyteller" voice,
  `stability: 0.5`, `style: 0.15`) suits code better than an excited one.
- **Respell what the voice gets wrong** (`pronunciation:`, TTS only):

```yaml
pronunciation:
  int8: eight-bit            # "int eight" was heard as "in to eight"; "eight-bit" read cleanly
  KV: K V                    # letter-by-letter acronyms: letters with spaces
  CLI: C L I
  most_common: most common   # identifiers as words
  "v2.5": "version two point five"
```

  A name with a version number reads best with a comma before the number ("Name, two point
  five"). A short point can still be swallowed: if readback hears "two five", that is usually fine
  when the screen shows the digits.
- **Check what was said**: `vidgen readback` (local faster-whisper, free; `stt: {model: base.en}`
  fits in ~1.5 GB, `small.en` is more accurate when memory allows) and `vidgen lint --readback`
  (rule `unclear_speech`). In the example Short readback measured a 4.4 % word error rate overall
  and the same two terms misheard by two models; after respelling them and re-voicing only those
  two beats, their error rates were 0 % and 7 %.
- **Re-voice only the flagged beats**: changing a `pronunciation:` entry re-voices only the beats
  containing that term; `vidgen tts --beat ID` forces one beat. Every re-voice is billed again.
- **Count before paying**: `vidgen tts --dry-run` prints each beat, the spoken text (`says: ...`)
  and the characters (the example Short: 11 beats, 618 characters; the example below: 8 beats,
  434 characters).
- **Time the picture to the words**: a beat action's `at` can name a word of the beat, `at:
  "@cache"` (its first time), `"@cache#2"`, `"@cache+0.2s"`. The highlight, the morph or the output
  then lands as the voice says it, from the TTS word timings after `vidgen tts` and from an
  estimate before, so the storyboard is already close. In a Short, where a beat is 3–4 s, this is
  the difference between a picture that answers the sentence and one that arrives a second late.
  `vidgen lint`'s `said_before_shown` warns when the narration names a label more than 1.5 s
  before it is on screen.
- `narration_speed` counts **spoken** words, so a respelled acronym ("A P I" = 3 words) can push a
  beat over 3.5 words/s while the written text runs at ~3. Check the real rate, then add a
  `lint_ignore: [{rule: narration_speed, beat: ID}]` with a comment saying why.

## 9. Music and loudness

Use one of schu-video-generator's built-in generated beds (synthesised, not MIDI), chosen by the video's tone:

```yaml
music: {source: momentum, volume: -2} # recommended: presentations, documentaries
music: {source: pulse, volume: -2}    # lighter: "look what this code does"
music: {source: bright, volume: -2}   # calm, cinematic scenes
```

- `momentum`: 120 BPM, G minor, a driving sixteenth-note synth ostinato, a soft kick on every beat
  and off-beat bass; the recommended bed for presentation- and documentary-style Shorts.
- `pulse`: 96 BPM, A minor, a soft plucked arpeggio over a muted pad and a gentle thump on every
  beat; forward-moving without being dramatic, and lighter on phone speakers.
- `bright`: 120 BPM, C major, a light pad, a plucked arpeggio and a sparse soft bell melody;
  warm and open, for calmer, more cinematic pieces.
- Alternatives to `momentum` with the same kick and synth bass: `lab` (108 BPM, modern tech:
  a rolling synth bass, electronic plucks, glitchy clicks) and `discovery` (104 BPM, a steady
  approach that builds); `breakthrough` lifts from tension to a reveal 25.7 s into its loop.
  More energy: `neon` (116 BPM, synthwave: a gated snare, an analog octave bass, a square-wave
  arpeggio; tech at night, retro-futurism, coding), `ascent` / `horizon` (136 / 132 BPM,
  uplifting trance that builds and lifts halfway through the loop: launches, montages, endings),
  `beacon` (120 BPM, a pulsar-like ticking beacon: space, science, data).
  All of these are bass-heavy (57–78 % of their power under 150 Hz) and Shorts are mostly heard on
  phone speakers, which drop most of that: listen on a phone, and fall back to `pulse` if the bed
  sounds thin.
- `volume: -2` sits well under the voice, and schu-video-generator ducks the bed by 12 dB while the voice
  speaks. Every bed loops without a seam, so it fits a video of any length.
- Prefer the beds to composed music (`music: {compose: <mood>}`): on narrated Shorts the beds
  sounded clearly better. Beds need no SoundFont and no music credit.
- The final mix is normalised to **−16 LUFS** integrated with a **true peak ≤ −1 dBTP** (schu-video-generator's
  defaults: `audio: {target_lufs: -16, true_peak: -1.5}`). The example Short with `pulse`:
  −16.0 LUFS, true peak −1.9 dBTP. `vidgen render` prints these numbers.
- Changing only the music re-renders no scenes (the mix happens at the join), so trying both beds
  takes seconds.

## 10. Honesty checklist

- [ ] Every claim in the narration and on screen is checked against the source (file and line),
      noted in a comment in `video.yaml` or a notes file.
- [ ] The hook number is exact (count the lines; say "lines of code" only for the code you show).
- [ ] No speed, size or benchmark numbers you did not measure yourself; no "fastest", "CPU only"
      or platform claims the source does not make.
- [ ] Illustrative output is labelled "example output" on screen and "an example" in the
      description.
- [ ] The code shown is verbatim (subsets only); simplified code says "adapted".
- [ ] Words like "no X needed" match the project's own README.

## 11. Workflow

```bash
vidgen validate                    # schema, files, line specs, icons; duration estimate
vidgen lint --fail-on info         # before audio: timed from word counts
vidgen storyboard                  # contact sheets: build/preview/storyboard/*.png -- look at them
vidgen render --preview            # silent preview (music only), or: vidgen render --draft
vidgen tts --dry-run               # spoken text and characters (what is billed)
vidgen tts                         # voices new or changed beats
vidgen readback                    # what the voice said vs the text
vidgen lint --readback             # unclear words; fix, re-voice those beats, repeat
vidgen render --preview            # now timed by the real audio
vidgen lint --fail-on warning      # 0 findings (or each ignore justified), said_before_shown included
vidgen render                      # final 1080x1920, 30 fps, loudness printed
vidgen lint --final                # on the real frames
vidgen thumbnail                   # if you changed only the thumbnail
```

A contact sheet every 4 s of the video, to see the pacing and empty frames at a glance:

```bash
ffmpeg -i output/my_short_preview.mp4 -vf "fps=1/4,scale=270:-1,tile=6x2" -frames:v 1 contact_4s.png
```

**Publishing text** (write it in a `description.txt` beside the project):
- **Title** ≤ 60 characters, ending in `#shorts`: "Top words in 10 lines of Python #shorts".
- **Description**: 2–3 sentences on what the code does and what it uses; "The program output
  shown is an example." when it is; the link; music credits if needed.
- **Hashtags**: 5–7, language and topic first (`#python #programming #opensource ...`).

## 12. Example `video.yaml`

A complete Short of 5 scenes and 8 beats (~33 s), with built-in scene types only. `vidgen
validate` is ok and `vidgen lint --fail-on info` finds nothing (word-count timing, no audio). For
phone-large code, put `code_focus` (§4) in `extensions/` and use it for the `read` scene. The code
file, `assets/top_words.py`:

```python
from collections import Counter
import sys

def top_words(path, n=5):
    with open(path) as f:
        words = f.read().lower().split()
    return Counter(words).most_common(n)

for word, count in top_words(sys.argv[1]):
    print(f"{word:>8} {count}")
```

```yaml
# A YouTube Short about a small piece of code (9:16, ~35 s). Built-in scene types only.
# Every claim is checked against assets/top_words.py; the terminal output is illustrative.
title: "Top words in 10 lines of Python"
output: top_words_short

format: {width: 1080, height: 1920, fps: 30}
preview: {width: 540, height: 960, fps: 15}

theme:
  preset: dark_tech
  background: "#0A0E16"          # near-black, not pure black
  code_style: one-dark
  colors:
    surface: "#131A27"
    highlight: "#F5C76B"         # the one accent: emphasis words, highlights, the hook number
    primary: "#7FB8FF"
    text: "#ECEEF2"              # off-white, not pure white

voice:
  provider: elevenlabs
  voice_id: YOUR_VOICE_ID        # a calm documentary / storyteller voice
  timestamps: true               # exact word times for the karaoke captions (same price)

pronunciation:
  most_common: most common       # say the identifier as words; the captions keep "most_common"

stt: {provider: faster_whisper, model: base.en}   # vidgen readback: local and free

terms: {words: primary}            # one colour per concept: "words" in every text and caption

music: {source: momentum, volume: -2}   # or pulse (lighter), bright (calmer, cinematic)
transition: {type: crossfade, duration: 0.4}

overlays:
  - type: captions
    style: karaoke
    position: bottom

thumbnail:
  title: "Top words, 10 lines of Python"
  subtitle: "no installs, one file"
  icon: file-text
  jpeg: true

scenes:
  - id: hook
    type: stat
    params:
      value: 10
      label: "lines of Python"
      context: "the most common words in any text"
      color: highlight
    beats:
      - id: hook_b1
        text: "Ten lines of Python find the most common words in any text file."

  - id: read
    type: code_walkthrough
    params:
      title: "top_words.py"
      path: assets/top_words.py
      size: body
      steps:
        - {lines: "1-2", note: "Standard library only"}
        - {lines: "5-6", note: "Read, lower-case, split"}
        - {lines: 7, note: "Count and rank"}
        - {lines: "9-10", note: "Print the top five"}
    beats:
      - id: read_b1
        text: "Two imports, and both come with Python itself."
      - id: read_b2
        text: "Read the file, lower-case it, and split it into words."
      - id: read_b3
        text: "Counter tallies every word, and most_common ranks them."
      - id: read_b4
        text: "Then loop over the top five and print each count."

  - id: output
    type: terminal                 # types the command, then shows the output written here
    params:
      title: "example output"
      steps:
        - command: "python top_words.py notes.txt"
          output: |
                 the 41
                 and 27
                  to 19
    beats:
      - id: output_b1
        text: "Run it on any text file, and you get a ranked list."
        actions:
          - {reveal: output1, at: "@ranked"}   # the output appears on the spoken word

  - id: why
    type: icon_grid
    params:
      heading: "What you skip"
      reveal: all
      items:
        - {icon: x, label: "No installs"}
        - {icon: x, label: "No regex"}
        - {icon: file-text, label: "One file"}
    beats:
      - id: why_b1
        text: "No installs. No regular expressions. Just one small file."

  - id: outro
    type: end_card
    params:
      title: "Try it yourself"
      icon: star
      lines: ["example.com/top-words"]
    beats:
      - id: outro_b1
        text: "The full script is linked below. Try it on your own notes."
```

## 13. First cut vs final: what changed

| first cut | final |
|---|---|
| built-in code scenes: ~30 columns, code in the middle third, long lines wrapped into 3–4 rows | `code_focus`: 24 columns, ~41 px cap height, one key line or block per beat |
| the whole file scrolled in a window on every beat | the whole file once, as a dim backdrop behind the hook number |
| a small terminal (one fifth of the frame) | a full-width terminal, the command typed, then the output |
| the benefits list showed one icon at the end of its beat | all rows in by ~60 % of the beat, evenly spaced |
| a small star and a one-line URL | a big star with a halo, bold title, the URL on two lines |
| acronyms said as written ("int eight") | respelled (`eight-bit`), checked with readback |
