# Video cookbook: craft notes for vidgen videos

Practical lessons from making long-form videos and vertical shorts with vidgen: a ~9-minute
paper explainer (narrated with ElevenLabs), a ~3-minute software showcase (Kokoro), and a series
of 9:16 shorts cut from them. The author guide (`AGENTS.md`, also printed by `vidgen guide`) and
the config reference (`docs/CONFIG.md`) say what vidgen *can* do. This cookbook is about what made the
videos *work*: hooks, pacing, sound, credits, labels, voice, and the QA loop. For a YouTube Short
that shows source code, see [COOKBOOK-YOUTUBE-SHORT-FOR-CODING.md](COOKBOOK-YOUTUBE-SHORT-FOR-CODING.md);
for writing your own music as score files (room for the voice, builds and lifts, loops, genre
sketches), see [COOKBOOK-MUSIC.md](COOKBOOK-MUSIC.md).

Reusable files are in [`examples/cookbook/`](../examples/cookbook/README.md):

| file | what it is |
|---|---|
| [`fx.py`](../examples/cookbook/fx.py) | palette constants, `glow`, `glow_dot`, `neuron` / `light`, `plane` / `stack` (depth), `dust` (live background), `pill`, `heading`, `run` |
| [`science_helpers.py`](../examples/cookbook/science_helpers.py) | `load_picture`, `glow_dot`, `star_field` + `twinkle`, `rough_blob`, diatom shapes, `run` |
| [`vertical.py`](../examples/cookbook/vertical.py) | `VScene`: a 9:16 scene base whose content band keeps clear of the phone UI and the captions |
| [`cold_open_photo.py`](../examples/cookbook/cold_open_photo.py) | `cold_open`: photo cold open with push-in, glowing streak, title, second line, boxed tag |
| [`scene_skeleton.py`](../examples/cookbook/scene_skeleton.py) | `my_scene`: a minimal custom scene, plus the patterns that bit us |
| [`software_scenes.py`](../examples/cookbook/software_scenes.py) | `dataflow_hook`, `stack_collapse`, `orbit_arch`, `finale` (software showcase) |
| [`paper_scenes.py`](../examples/cookbook/paper_scenes.py) | `edx_probe`, `nitrogen_clock`, `isotope_range` (paper evidence) |
| [`vertical_scenes.py`](../examples/cookbook/vertical_scenes.py) | `short_hook`, `short_end` (9:16 shorts) |
| [`video.template.yaml`](../examples/cookbook/video.template.yaml) | 16:9 starter config: theme, voice, pronunciation, music, SFX, overlays, sources and credits cards |
| [`short.template.yaml`](../examples/cookbook/short.template.yaml) | 9:16 starter config: karaoke captions, tight pacing, hook and end scenes |
| [`whisper_check.py`](../examples/cookbook/whisper_check.py) | stand-alone Whisper transcription, to check pronunciation |

To use them, copy the helpers and scenes you need into `<project>/extensions/`. The files import
each other relatively (`from .fx import ...`), which works because vidgen imports the
`extensions/` folder as one package. See the [examples README](../examples/cookbook/README.md).

---

## 1. The workflow (run every step, in this order)

```bash
vidgen init my-video               # then merge in examples/cookbook/video.template.yaml
cd my-video
vidgen validate                    # schema, beats, audio status, duration estimate
vidgen tts --dry-run               # what would be voiced, characters, cost
vidgen tts                         # only changed beats are re-voiced
vidgen storyboard --jobs auto      # contact sheets: build/preview/storyboard/*.png
vidgen storyboard --scene X        # iterate on one scene
vidgen lint --json                 # overlaps, contrast, min font, dead air, narration speed
vidgen render --jobs auto          # full quality: output/ gets MP4 + SRT + thumbnail + chapters
vidgen lint --final                # lint on the real frames (slow)
```

- Storyboard before TTS while you iterate on layout. Voice before the final storyboard, because
  beat durations drive the animation timing.
- `vidgen render --preview --scene X` gives a fast, low-resolution MP4 of one scene.
- Long renders: run them in the background and follow the log, e.g.
  `nohup vidgen render --jobs auto > render.log 2>&1 &`. Re-running `vidgen render` after an
  interruption reuses every finished scene and only re-joins.
- An MP4 in `output/` (or your `output_dir:`) newer than `video.yaml` and every file in
  `extensions/` is current.

## 2. QA loop: frames, not just lint

- [ ] `vidgen validate` is ok, and no beat audio is stale or missing.
- [ ] The storyboard sheets read at a glance: no text on text, nothing touching the header or the
      bottom note.
- [ ] `vidgen lint --json`: **0 errors**. Read every warning, and fix it or justify it.
- [ ] Full render, then extract **20+ frames** spread over the video (include mid-transition
      moments) and look at them as contact sheets:

```bash
mkdir -p qa && for t in 0.5 2 4 7 10 14 18 24 30; do
  ffmpeg -v error -ss $t -i output/my_video.mp4 -frames:v 1 -vf scale=640:-1 qa/f$(printf %06.1f $t).png; done
python3 - <<'P'
from PIL import Image; import glob
fs = sorted(glob.glob('qa/f*.png'))
for k in range(0, len(fs), 10):
    o = Image.new('RGB', (1280, 1800), 'white')
    for i, f in enumerate(fs[k:k + 10]):
        o.paste(Image.open(f), ((i % 2) * 640, (i // 2) * 360))
    o.save(f'qa/sheet{k // 10}.png')
P
```

- [ ] Check the thumbnail PNG and the SRT: the subtitles show the *display* text, not the
      pronunciation spellings.
- [ ] Check the voice (§14): `vidgen readback`, or [`whisper_check.py`](../examples/cookbook/whisper_check.py).

**When it's fine to relax a lint rule or leave a warning**
- `narration_speed: {max_rate: 4.0}` when a voice naturally reads 3.5–3.9 words/s and sounds
  fine (some ElevenLabs narrators do).
- Warnings you can leave, with a note in your report:
  - `contrast` on `glow()` copies of text: the glow layers are low-opacity text copies;
  - `off_frame` of a few px on drifting background particles or rotating rings;
  - `covered_text` for an intentional strike-through line;
  - `dead_air` on built-in code or recap scenes.
- Never ignore `text_overlap`, `min_font` or `safe_area`. Fix the layout instead.

## 3. Cold open: hook in the first 3–5 seconds

Rule: **frame 1 already moves, and the provocative line lands by second 3–5.** No title card
first, and no fade from black longer than 0.5 s. Exclude the hook from the `progress_bar`.

Patterns that worked:
1. **Data flow from the first frame** (`dataflow_hook` in `software_scenes.py`):
   - the input image and glowing feature-map stacks appear in 0.7 s;
   - looping particles run along paths (`_looping_particles`);
   - the stacks pulse layer by layer and the dense neurons light up;
   - the winning output glows, with a `chime`.
2. **Provocative question** on a dark plate over the dimmed animation ("A deep learning
   library… *written in <surprise>?*"). The key word is in `highlight` amber with `glow()`,
   scaled in from 1.8× with a `thud`.
3. **Struck-through misconception**: "everyone says / *“<the misconception>.”*", then
   `Create(Line(...))` in `accent` across it with a `swoosh`.
4. **Photo cold open** (`cold_open` in `cold_open_photo.py`):
   - a full-bleed photo with a 45% black shade and a slow push-in updater;
   - a glowing streak (`glow_dot` + `TracedPath`) with a `whoosh`, ending in a `Flash`;
   - the title is `Write`n, then the second line;
   - a **boxed tag** (e.g. "THE EVIDENCE, AS REPORTED") lands with a `thud` and an
     `ease_out_back` scale.
5. The first narration line states the stakes ("If they were right, life had reached Earth from
   space."). Then a question promises the payoff ("So what exactly did they measure…?").

Checklist:
- [ ] Something moves at t = 0.
- [ ] The hook question is on screen by 5 s.
- [ ] One sound hit at the reveal.
- [ ] Image credit in a small corner caption.
- [ ] The tag or strike-through gives a reason to keep watching.

## 4. Pacing and retention

- **A new visual every 3–6 s** (every 1–3 s in a short). One idea per beat. Beats of 8–25
  words (Kokoro is weak on lines under about 8 words).
- Inside a long beat, keep something moving: an `Indicate`, a slow `ken_burns` or
  `.animate.scale(1.05)`, a counter, a wave via `UpdateFromFunc`.
- **Open loops:** raise a question early ("…and one element is missing. We'll get to why that
  matters.") and pay it off later. Name the payoff, so people wait for it.
- **Cliffhangers** at chapter ends: the last beat of a chapter asks the question the next chapter
  answers.
- **Chapters** for videos over about 4 min: `type: chapter` cards (`duration: 1.8`, a
  `fade_color` transition) plus a `chapter_indicator` overlay (`total: true`, excluding the hook,
  sources and credits). Short videos (about 3 min) need only the `progress_bar`. YouTube shows
  chapters only when there are at least 3.
- **Animated counters** for every important number: stars, forks, %, GPa, days. Use the
  `ValueTracker` + `always_redraw` pattern (`scene_skeleton.py`) and `ease_out_cubic`.
- **Recap** before the end (`icon_grid`, about 6 items, `groups` reveal). The call to action or
  a neutral closing line comes last.
- Length follows the content: 9 min works when every scene shows new evidence; 3 min suits a
  showcase.

## 5. Visual style

- **Palette** (a `dark_tech` override, as in the template):
  - background `#0B0F1A`, surface `#121829`;
  - cyan `#4CC9F0` (primary), violet `#A78BFA`, amber `#FFD166` ("look here", one per frame);
  - mint `#5EEAD4` (good), pink `#F472B6`, accent `#FF6B8B` (bad or strike).
  - Use theme tokens (`"text"`, `"dim"`, `"highlight"`, `"accent"`) in `self.text(...)`.
- **Glow and depth** (`fx.py`):
  - `glow(mob, color)` puts a stroke halo behind frames, chips and key words;
  - `glow_dot` for particles;
  - `plane()` / `stack()` draw slanted parallelograms with a grid, for feature maps in depth;
  - `dust()` gives drifting, twinkling specks, so no frame is ever static;
  - dashed rings rotating via an updater (title, finale).
- **Typography:**
  - Inter for everything, JetBrains Mono for code (`role="code"`);
  - the theme's sizes (`title`, `subtitle`, `heading`, `body`, `caption`, `small`; see
    `vidgen list-themes`), or numbers for hero text (64–150);
  - one heading per scene in the header region (`heading()` in `fx.py`).
- **Easing:** `ease_out_cubic` for counters; `ease_out_back` for tags popping in; `ease_in_quad`
  for a falling streak; `there_and_back` for glow pulses; `linear` for continuous waves and
  orbits.
- **Code:** the built-in `code_walkthrough` (e.g. `language: pascal`), the theme's code style, and
  `steps:` that highlight line ranges with a note. Say "adapted from the README" if you simplify.
- **Images:** a rounded frame plus glow, a slow zoom, a caption below with ≥ 0.4 units of space,
  and a credit line in `small` `dim`.

## 6. Labels, instruments and technical terms

Viewers only see a frame for a few seconds. Every label must make sense on its own.

- **Say what the thing is, not just its name.** "Inside Orgueil" becomes "Inside the Orgueil
  meteorite". A name viewers may not know gets its category at first mention ("the Ivuna
  meteorite, fell 1938, Tanzania") and on every later label.
- **Keep different kinds of names apart.** Where a sample and an organism appear together, name
  both separately: "Filament resembling *Titanospirillum velox* (bacterium), in the Ivuna
  meteorite". Give genus labels their group ("cyanobacterium *Calothrix*").
- **Every picture scene says three things, up front:** what we're looking at ("Electron-microscope
  image of a freshly broken surface inside the meteorite"), what to notice (arrows, rings,
  highlights, a zoom), and why it matters. Put all three in the narration *and* on screen.
- **Maps and charts need a legend:** which colour is which element or group, and a one-line "what
  to notice". Axis labels in words ("less carbon-13 ← → more carbon-13") beat bare symbols.
- **Explain the instrument before its data.** Before the first spectrum, a short chapter on what
  the instrument does and why it matters works well: a microscope shows *shape*, and shapes can
  mislead; the X-ray detector (EDS/EDX) shows which *elements* sit at each spot. Animate a beam
  hitting a spot, X-rays coming out, the spectrum's peaks rising, then an element map building up
  colour by colour (`edx_probe` in `paper_scenes.py` is a compact version).
- **Explain technical terms in plain words the first time**, then use them: "heavy carbon"
  becomes "enrichment in carbon-13 versus carbon-12, an isotope fingerprint". If a term sounds
  like a contradiction ("20% water, yet it dissolves in water?"), resolve it on screen: the water
  is *bound* in minerals and salts, and the salts are the glue.
- After every storyboard, read only the labels: would a newcomer know what each picture is?

## 7. Scene types: how we used them

| type | used for | notes |
|---|---|---|
| custom `cold_open` / `dataflow_hook` | first 5–15 s | see §3 |
| `chapter` | chapter cards | `number`, `title`, `icon`, `duration: 1.8` |
| `process` | a sample chain, lab steps | `reveal: all` |
| `pie` | a composition | `donut: true`, `center: "95%"`, `center_label` (set the centre; the default can look odd) |
| `stat` | "~20 GPa", "10,000×" | actions: `highlight` the label, or underline the context |
| `comparison` | two samples side by side | `reveal: columns` |
| `icon_grid` | arguments, recap | `groups: [[0,1],[2,3,4],[5]]` reveals per beat |
| `timeline` | a sequence of events | |
| `image` | photos | `ken_burns: true`, `caption` = the credit |
| `code_walkthrough` | a code snippet | `steps: [{lines: "4-8", note: ...}]` |
| `text_card` | a single neutral statement | |
| `end_card` | sources (7 s) and image credits (5 s) | silent, `lines:` list, `icon: book-open` |
| custom scenes | anything that is the *point* of the video | data flow, evidence charts, terminal, orbit |

Rule: built-ins for lists, cards and charts. A custom scene when the animation *is* the
explanation (the measurement, the mechanism, the data flow). `vidgen list-scenes` shows every
type and its params; `vidgen gallery` renders a sample of each.

## 8. Custom scene patterns

Start from [`scene_skeleton.py`](../examples/cookbook/scene_skeleton.py). The essentials:

```python
@scene("name")
class Name(NarratedScene):
    beat_count = 3
    outro = 0.4

    class Params(SceneParams):
        heading: TranslatableStr
        note: TranslatableStr = ""

    def construct(self):
        p = self.params
        with self.narrate(0) as d:          # d = the beat's audio seconds
            self.sfx("pop", gain=-7)
            self.play(FadeIn(x), run_time=run(d, 0.3, 1.0))   # size animations from d
        self.finish()
```

Lessons:
- **Assets:** `self.project.asset("assets/x.png")`; the path is relative to the project root.
- **Placement:**
  - `heading()` → the header region (`self.region("header")`);
  - source notes at `self.safe_area.y0 + h / 2`;
  - right-align with `self.safe_area.x1 - w / 2`;
  - clamp wide groups with `shrink_to_fit(group, self.safe_width)` or `scale_to_fit_width`.
- **`always_redraw` must position inside the lambda.** Otherwise every counter piles up at the
  origin. Call `clear_updaters()` before the end.
- **Don't combine `x.animate.scale(...)` with `FadeIn(x)` in one `play()`.** The two animations
  fight over `x`, and it can end at the wrong size (a title left 1.6× too wide, off frame). Use
  `FadeIn(x, scale=1.6)` for a scale-in.
- **Animating a sub-mobject re-adds it on top.** `Indicate(card[0])` hid the card's text.
  Animate the whole group, or draw a `SurroundingRectangle`.
- **Fading a nested group**: `group.animate.set_opacity(0.5)` also changes children you meant to
  keep (a tick mark brought a hidden number back). Animate exactly the parts you mean.
- **Dark plate over a busy scene:** fade out the texts underneath, or lint flags overlaps.
- **Lint sees motion only from animated mobjects.** Use
  `self.play(tracker.animate..., UpdateFromFunc(group, fn))`, not a bare updater.
- **Leave margins:** chips near a scale bar or caption need ≥ 0.15 units of gap. Recheck after
  every storyboard.
- **Size animations from `d`** (`run(d, frac, cap)`) so beats never overrun (`animation_overrun`
  warning). Leave 0.3–0.5 s of slack.
- **Unknown icon** (e.g. `gem`, `github`): find real names with `vidgen list-icons --search <word>`.

## 9. Sound design

Global, in `video.yaml`:

```yaml
music: {source: momentum, volume: -2}   # recommended for presentations and documentaries
sfx: {gain: -2}                         # master SFX gain
transition: {type: crossfade, duration: 0.35}
```

In a scene: `self.sfx(name, at=None, *, gain=0.0, pan=0.0, align="start", duration=...,
pitch=..., intensity=...)`. It is mixed sample-exact at the next `play()` (or at `at=` seconds;
`align="end"` ends the sound there). `vidgen list-sfx` and `vidgen list-music` describe the
sounds and beds.

`momentum` (G minor, 120 BPM: a driving sixteenth-note synth ostinato, a soft kick, off-beat bass)
is the recommended bed for presentations and documentaries. Alternatives with the same soft kick
and synth bass: `discovery` (a steady approach to a finding), `breakthrough` (tension, then a
reveal 25.7 s into its loop: `start: 25.7 − T` lands it on a reveal T seconds after the music
starts), `enigma` (mysterious, investigations), `lab` (modern tech); energetic electronic ones:
`ascent` and `horizon` (uplifting trance that builds to a lift halfway through the loop:
energetic reveals, tech launches, montages, uplifting endings), `beacon` (a pulsar-like ticking
beacon: space, astronomy, science, data), `neon` (synthwave: tech at night, retro-futurism,
cities); lighter ones: `calm` (serious, long narration), `pulse` (tech), `bright` (upbeat). The
kick-and-bass beds are bass-heavy and sound lighter on phone and laptop speakers
([CONFIG](CONFIG.md#background-music-music)). When no bed fits, write your own piece as a score
file from a bed's template (`music: my_theme` plays `assets/music/my_theme.yaml`): see
[COOKBOOK-MUSIC.md](COOKBOOK-MUSIC.md) for the craft and genre sketches.

| sound | use for | gain we used |
|---|---|---|
| `whoosh` | an element or image sliding in, a scene opening, a streak | -2 … -8 |
| `swoosh` | a collapse, a swap, a strike-through, leaving | -3 … -5 |
| `pop` | each block, chip or badge appearing | -6 … -8 |
| `tick` | a counter starting, repeated steps, timeline marks | -6 … -12 |
| `click` | a probe placed, a selection | -6 |
| `typing` | terminal text (`duration=` the typing time) | -10 |
| `chime` | the answer, the key number, the final line | -6 |
| `success` | a command's correct output | -8 |
| `thud` | the provocative word landing, a tag, a verdict | -3 … -4 |
| `riser` | a build-up before a reveal (`duration=1.2`, or `align="end"` on the reveal) | -10 |
| `error` | a crossed-out option, a rejected idea | -10 … -12 |

Rules: at most one hit per beat, plus quiet pops for lists. Keep SFX 6–12 dB under the narration.
Use -10 and below for repeated sounds (ticks, typing).

## 10. Credits and licences

- **Image credits in two places:**
  1. a corner caption on the frame where the image appears (`small`, `dim` or light text on a
     70% black band over photos), e.g. "Photo: Gemini Observatory/NOIRLab/NSF/AURA, CC BY 4.0";
  2. a silent **credits `end_card`** (5 s) listing every image with its licence. For repository
     material, one line such as "Images & code: <repo> repository (<licence>)".
- **Check the licence before downloading:**
  - **Wikimedia Commons:** read the file page's licence box. CC BY / CC BY-SA need the author and
    licence; avoid NC/ND.
  - **NOAA / NASA / US federal works:** generally public domain, but check the record. NASA
    technical reports (NTRS) state their rights ("Public Use Permitted", "Copyright") and list
    the authors; a report with authors from outside NASA, or a copyright notice, may restrict
    reuse. Still credit, e.g. "R. Author, NASA/MSFC (NTRS 2010xxxxxxx)".
  - **NOIRLab / ESO / ESA:** usually CC BY 4.0. Credit them as they ask.
  - **arXiv:** check the licence on the abstract page. The default
    (`arxiv.org/licenses/nonexclusive-distrib/1.0`) lets arXiv distribute the paper; it does
    **not** let you reuse its figures. **Recreate figures** as animations from the reported
    numbers, and tag them "illustration after Author et al. 2013, fig. 3". Only CC BY / CC0
    papers allow reusing the figure itself (with credit).
  - **Journal figures:** assume all rights reserved unless the article says otherwise.
  - **GitHub repositories:** the repository licence covers its docs and images. Credit the repo.
- To extract figures from a PDF you may reuse: `pdfimages -png paper.pdf fig` (embedded
  images) or `pdftoppm -r 300 -png paper.pdf page` (whole pages to crop).
- **Sounds and music:** vidgen's built-in SFX and music beds are synthesized by vidgen, so they
  need no credit. Any external audio file needs its licence checked and a credits line.
- **Narration voice:** name it in the credits when it's a local model (e.g. "Narration:
  Kokoro-82M (af_heart)").

## 11. Paper references

- **In narration, attribute every claim to its source:** "the team reports…", "the authors
  say…", "in their words, *unequivocally meteorites*", "as its README puts it…". Don't state a
  contested result as fact.
- **On screen:** a small `dim` tag at the bottom of each evidence scene, e.g. "EDX abundances,
  Wallis et al. 2013 (arXiv:1303.1845), Table 3".
  - Exact quotes go in quotation marks, in `highlight`.
  - Schematic recreations say "(schematic)".
- **Sources card:** a silent `end_card` (7 s, `icon: book-open`), one line per paper:
  `Author et al. Year, Journal Vol:Page, arXiv:ID` or a `doi:`. Put dataset sources there too.
- Keep a header comment in `video.yaml` listing every source and where your local copy lives
  (e.g. a `papers/` folder in the project).
- If papers disagree with each other (e.g. iridium 1–7 vs 7–8 ppm), use the safer rounded
  statement ("about 10,000× crust") and note it.

## 12. Fact discipline

- [ ] Every number comes from a file you read (the paper's text, a README, an API response).
      Note the table, figure or line.
- [ ] Repository stats come from the platform's API, with "as of <date>" on screen.
- [ ] Use only real commands and outputs from the docs (e.g. a terminal scene that types a
      documented command and shows its documented output).
- [ ] Illustrations are labelled as illustrations ("8 → 8 channels, 4 groups"); simplified code
      says "adapted".
- [ ] Soften wording to what the source actually says ("the team offers an answer", "had
      explored it as a way").
- [ ] Before rendering, grep the yaml, the extensions and the SRT for anything that shouldn't be
      there (placeholders, TODOs, stray names).

**Exact scientific wording.** In a scientific video, use the term a scientist would use, never a
loose everyday word:

- "the atmosphere of Jupiter", not "the air in Jupiter";
- "Earth's radius" or "Earth's diameter", not "Earth's width";
- likewise mass vs weight, heat vs temperature, speed vs velocity, "a theory" vs "a guess".

Name the measure when the source does ("Earth's mean radius, about 6,371 km"), and give the unit
in the narration and on screen. Check the narration, the on-screen text and the captions.

**Same term, same colour.** Once a concept has a colour, it keeps it everywhere: the word in a
bullet, a chart's series, the symbol in the equation and the caption all wear the same one, and
no other concept wears it. Set it once in `terms:` (`terms: {loss: tertiary, gradient: "#E07A5F"}`,
with `tex:` for the symbol that stands for it, docs/CONFIG.md "One colour per concept") instead
of colouring scene by scene; give a colour to at most about five concepts, and do not colour the
same word otherwise in one scene (`vidgen lint`'s `concept_colors` rule warns about all three).
Like the wording, the colour is part of the term: never vary it for style.

**Established facts vs reported results.** Textbook facts can be stated plainly. A result that
comes from specific papers and is not settled (not independently validated) always carries its
reference:

- in the narration, with the year: "According to Smith and colleagues, in a 2023 study, …";
- on screen, as a small source tag in that scene ("Smith et al. 2023, Nature 615:123");
- on the sources card (§11).

Never present such a result as settled fact.

## 13. Editorial options (example style choices)

These are choices, not rules. Pick a stance per video and apply it consistently.

- **Paper explainers: present the paper's own case.** You may choose to explain the paper's
  evidence in depth (for each line of evidence: what was measured, how, and why the authors
  conclude what they do, including how they rule out alternatives), and to note only briefly
  that the conclusions have been questioned. One neutral sentence near the end ("The team's
  conclusions have been questioned by other scientists, and remain debated.") followed by the
  sources keeps a video about the evidence from becoming a debate. In a short, a small on-screen
  line ("debated claim · sources in description") does the same job.
- **Alternatively, a balanced review:** give critics and rebuttals their own chapter, with the same
  sourcing discipline (§11, §12).
- **Software showcases:** show what the project actually does (real outputs, real commands),
  with a confident hook and a call to action with the URL at the end.
- **Beauty and pace first:** fast visual pacing, and length only as long as it stays engaging.
- **Unusual topics** ("crazy science", fringe claims) can be framed as "the evidence, as
  reported", attributed to the people who reported it.

## 14. Narration, pronunciation and voice

**Style:**
- Short spoken sentences, concrete verbs ("tears across the sky", "drags along four gigabytes").
- A question at the start of a chapter, the answer in the next beat.
- Numbers spoken the way people say them.
- Write beats as they'll be heard: the beat text becomes the SRT and the captions.

**Pronunciation dictionary** (`pronunciation:`; it changes only the spoken text, not subtitles):

```yaml
pronunciation:
  CUDA: "[CUDA](/kˈudə/)"     # Kokoro: say an acronym as ONE word via inline IPA (bare "CUDA" is spelt out)
  OpenCL: "Open C L"         # the opposite case: force letters with spaces
  AVX-512: "A.V.X. 512"      # "A V X" was heard as "a VX"; dotted letters work
  PyTorch: "Pie Torch"
  README: "read me"
  "1.2.0": "one point two point oh"   # dotted versions: otherwise read as a number
  Wickramasinghe: Wickrama-singha      # hyphenate long names (works for both voices)
  Kyiv: "[Kyiv](/kˈiv/)"               # Kokoro only: inline IPA via misaki markup
```

- **Check what was actually said.** `vidgen readback` transcribes the narration and compares it
  with the beat texts. As an optional standalone check,
  [`whisper_check.py`](../examples/cookbook/whisper_check.py) prints a transcript per clip; it pads
  the start with silence, because Whisper tends to drop the first words of a clip that starts
  immediately. The English `small.en` model was more reliable than the multilingual `small` for
  English narration.
- Judge by sound, not spelling: an unusual name transcribed phonetically (*Sellaphora* heard as
  "Cell-Laugh-Aura") is a pass.
- **Kokoro acronyms:** check the phonemes before rendering:
  `KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M', model=False).g2p("no CUDA lock-in.")[0]`
  (`sˌijˌudˌiˈA` = letters, `kˈudə` = a word). Whisper writes "CUDA" for both, so for acronyms
  check the phonemes.

**Voice choice:**

| | ElevenLabs (`provider: elevenlabs`) | Kokoro (`provider: kokoro`, e.g. `af_heart`) |
|---|---|---|
| quality | most natural and expressive | clear, a bit flatter, no context between beats |
| cost | per character: always `vidgen tts --dry-run` first, reuse unchanged beats, set a budget | free and local |
| speed | some voices read ~3.5–3.9 words/s (relax `narration_speed` to 4.0) | ~3.5 words/s |
| names | handles most with hyphenation | needs IPA markup for non-English names |
| word timings (karaoke) | `timestamps: true` | English (`lang` a / b): automatic |
| use for | final narration of flagship videos | drafts, software videos, fast iteration |

- ElevenLabs reads its key from `ELEVENLABS_API_KEY` (OpenRouter TTS: `OPENROUTER_API_KEY`).
  Check keys for presence only; never print them.
- Kokoro is an optional extra: `pip install "schu-video-generator[kokoro]"` (or `pip install
  -e ".[kokoro]"` from a checkout). The first `vidgen tts` downloads the model. On Python 3.13 see
  the install note in `docs/CONFIG.md` ("Kokoro on this computer").
- **TTS cache:** a beat is re-voiced only when its spoken text (pronunciation applied) or the voice
  settings change. Rewording one beat re-voices only that beat; changing a dictionary entry
  re-voices every beat containing that word. To reuse a clip in another project, copy its
  `audio/<beat_id>.mp3` and `.hash` and keep the same beat id, text and voice.
- **Character budget:** a dry run before every paid run; reuse clips across a long video and its
  shorts where the wording fits.

## 15. Vertical shorts (9:16)

Two ways to make one:
- **A variant** of a landscape project:
  `variants: {vertical: {format: {width: 1080, height: 1920}}}`, then
  `vidgen render --variant vertical` (→ `<output>_vertical.mp4`). Built-in scenes re-lay out for
  9:16; custom 16:9 scenes usually don't.
- **A dedicated short project** (best for a 15–45 s short with its own script): start from
  [`short.template.yaml`](../examples/cookbook/short.template.yaml), with
  [`vertical.py`](../examples/cookbook/vertical.py) and
  [`vertical_scenes.py`](../examples/cookbook/vertical_scenes.py) in `extensions/`. Re-lay out
  any landscape scene for portrait; don't letterbox.

Short-form craft:
- **Hook in the first 1–2 s** with motion and the most stunning claim or visual. No title card,
  no intro.
- **One idea per short**, building to a single payoff. Make the logical chain explicit (A, so B,
  so C) with a tick list or a verdict stamp.
- **A new visual every 1–3 s**, an SFX on each hit, music under everything.
- **Word-by-word captions** burned in: `overlays: [{type: captions, style: karaoke, lift: 0.19}]`.
  They need word timings (ElevenLabs `timestamps: true`, or English Kokoro).
- **Safe zones:** keep content out of the top ~12% (platform header) and the bottom ~20% (phone
  controls). The `captions` overlay reserves its band out of the safe area; `VScene.top` /
  `.bottom` give the band that stays clear of both. Two-line karaoke captions take more room than
  you'd think: check the storyboard.
- **End on a loopable line** or a "Full video on my channel" prompt (`short_end`).
- **Credits** go in a fast end frame or in the post's description text.
- **Length:** 15–45 s. If the voice runs long, tighten the text first; `narration.pad` around
  0–0.05 s keeps gaps short.
- QA: check 15+ frames per short, specifically for the safe zones, overlaps with the captions, and
  caption legibility.
- **A short about code**: phone-readable code sizes, the frame layout, wrapping and a
  `code_focus` scene skeleton are in
  [COOKBOOK-YOUTUBE-SHORT-FOR-CODING.md](COOKBOOK-YOUTUBE-SHORT-FOR-CODING.md).

## 16. Known issues and version notes

- **`vidgen readback` and PyAV 19:** older vidgen releases let faster-whisper decode the audio,
  which fails on PyAV 19 (`TypeError: open() got an unexpected keyword argument
  'metadata_errors'`). Fixed in current vidgen (it decodes the audio itself);
  [`whisper_check.py`](../examples/cookbook/whisper_check.py) remains an optional standalone check.
- **Version notes:** older vidgen releases had problems with transitions on ffmpeg 7.0/7.1 and
  with Manim 0.22; both are fixed in current vidgen. Keep vidgen up to date.
- **The render cache:** a scene's render is reused while its inputs are unchanged. Editing *any*
  `.py` file in `extensions/` re-renders every scene, so batch extension edits; a full re-render
  of a 9-minute video takes a while.
- **Interrupted renders:** re-running `vidgen render` reuses every finished scene and only
  re-joins. A `build/final` folder touched after the MP4 is just `lint --final` drawing stills.
- **Kokoro log noise:** HTTP request lines and a Hugging Face "unauthenticated" warning on every
  `vidgen tts`. Harmless.
- **Lint `contrast` false positives** come from `glow()` copies of text (see §2).
- **"Scene starts 0.1 s after planned"** warnings come from small animation overruns. Harmless;
  trim with `run()` caps.
- **Missing asset:** `self.project.asset()` resolves from the project root, so write
  `assets/x.png`.

## 17. Pre-delivery checklist

- [ ] Hook: motion at t = 0, the question by 5 s (by 1–2 s in a short).
- [ ] A new visual every 3–6 s (1–3 s in a short); counters animate.
- [ ] Labels say what each thing is; pictures say what to notice and why it matters; charts have
      legends.
- [ ] Every claim attributed; source tags on evidence scenes; a sources card.
- [ ] Exact scientific terms ("atmosphere", not "air"; "radius" or "diameter", not "width"), with
      the measure and unit named (§12).
- [ ] Results not yet validated say who reported them and when ("according to … in 2023"), in the
      narration and on screen (§12).
- [ ] Image credits in captions and on the credits card; licences checked; restricted figures
      recreated.
- [ ] The editorial stance you chose (§13) applied consistently.
- [ ] Pronunciation checked (readback or `whisper_check.py`).
- [ ] validate ok · lint 0 errors · full render · lint --final · 20+ frames viewed (15+ per short)
      · thumbnail and SRT checked.
- [ ] Report: paths (MP4, SRT, thumbnail, all in `output/` by default), duration, TTS characters spent, the scene/chapter
      outline with sources, and any problems.
