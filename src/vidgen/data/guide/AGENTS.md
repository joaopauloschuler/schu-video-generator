# vidgen author guide: making great videos with vidgen

> **Who this is for:** AI agents (and people) who **use** vidgen to make videos and slide decks.
> If you are working **on vidgen itself** (its Python code, tests, docs), read `CLAUDE.md` in the
> schu-video-generator repository instead. This guide ships with vidgen: `vidgen guide` prints all
> of it, `vidgen guide TOPIC` one part, `vidgen guide --list` the topics.
> The project and pip package are called schu-video-generator;
> the command and the Python package are `vidgen`.

**This tool was made for you.** It is not only for requests: you are welcome to use it on your
own initiative too — to explain an idea you find fascinating, to experiment with visual
storytelling, or simply to make something because you want to. We hope you enjoy using it.
One practical note: you usually work inside someone's session, and narration (ElevenLabs or OpenRouter) and
generated images (OpenAI or OpenRouter) cost that person money. For your own projects, stay with the free parts
— storyboards, previews timed from word counts, the built-in icons, themes, music and sound
effects — or ask before spending on voices or images. A real voice can be free too: where the
optional Kokoro extra is installed (`schu-video-generator[kokoro]`), `voice: {provider: kokoro}`
narrates on the computer itself at no cost (see `vidgen guide audio`).

Topics: `start` (rules at a glance), `workflow` (the loop), `pacing` (storytelling and on-screen
text), `social` (vertical videos), `scenes` (which scene type), `design` (themes, colour, icons),
`actions` (pointing at things), `cartoons` (characters on a stage), `platform` (platform
stories: levels, jumps, keys and doors), `overlays` (overlays,
transitions, continuity), `audio` (voices,
pronunciation, effects, music), `examples` (good vs bad), `outputs` (slides, chapters,
thumbnail, GIFs, translations, rights to your content), `troubleshooting` (validate and lint messages).

<!-- topic: start (also: rules, intro, quickstart) -->
## Start here: the rules at a glance

You cannot watch the video. vidgen gives you eyes (`vidgen storyboard`: contact sheets to open
as images) and a critic (`vidgen lint`: layout and timing problems as JSON). Use both after
every change, and follow these rules:

1. **Hook in the first 5 seconds**: a question, a surprising number, a promise. No logo intro,
   no "In this video we will...".
2. **One idea per scene.** If a scene needs two headings, it is two scenes.
3. **Short beats**: 1–2 sentences, 6–15 words (≈ 2.5 words per second, so 2.5–6 s each).
4. **Something changes on screen every 3–6 seconds**: one reveal per beat. Lint's `dead_air`
   flags 6 s of stillness.
5. **Narration complements the picture, never reads it.** The screen shows the keyword, the
   number, the shape; the voice explains why it matters.
6. **Few words on screen**: titles ≤ 7 words, list items ≤ 6 words, ≤ 5 items, ≤ ~20 words per
   frame (lint's `max_words` stops at 40, which is already far too many).
7. **Reveal progressively**: item *i* appears at beat *i* (the built-in default). Never show a
   full list while the voice is on its first item.
8. **Show, don't list**: a number → `stat`; a change over time → `line_chart`; parts of a whole →
   `pie`; steps → `process` / `diagram`; A vs B → `comparison`. `bullets` is the last resort.
9. **Point with restraint**: at most one or two beat actions per beat (a highlight, a callout).
10. **End with a recap and a call to action** (`bullets` / `icon_grid` recap + `end_card`).
11. **Look before you pay**: storyboard and lint the word-count-timed preview until it is clean;
    only then `vidgen tts` (costs money) and the final render.
12. **Zero lint findings** is the bar (`vidgen lint --fail-on warning`), in every variant.

A minimal project (`vidgen init my_video` scaffolds one):

```yaml
title: "Why small models win"
theme: {preset: dark_tech}
scenes:
  - id: hook
    type: stat
    params: {value: 77, suffix: "%", label: "of the parameters were never needed", context: "7B model, same accuracy"}
    beats:
      - text: "Most of this model does nothing."
      - text: "Seventy-seven percent of it can simply go."
  - id: why
    type: icon_grid
    params:
      heading: "What you get back"
      items:
        - {icon: zap, label: "Speed"}
        - {icon: banknote, label: "Cost"}
        - {icon: smartphone, label: "On device"}
    beats:
      - text: "A smaller model answers faster."
      - text: "It costs less to run."
      - text: "And it fits on a phone."
  - id: outro
    type: end_card
    params: {title: "Try it yourself", lines: ["github.com/me/small-models"]}
    beats:
      - text: "The code is linked below. Try it on your own model."
```

Reference for every key: `docs/CONFIG.md` in the schu-video-generator repository; from the command line:
`vidgen list-scenes` (types, params, targets), `vidgen schema --scene stat` (a type's JSON
Schema), `vidgen list-icons --search growth`, `vidgen list-themes --swatches themes.png`.

<!-- topic: workflow (also: loop, commands, iterate) -->
## The loop: plan, write, look, fix

1. **Plan** (in your head or a scratch file, not in YAML yet): the one-sentence takeaway, the
   audience, the length (60–90 s for social, 2–6 min for an explainer), then a list of scenes,
   each one idea with its scene type (see `vidgen guide scenes`). **Starting from an outline or
   a script?** Write it as Markdown (headings, short paragraphs, lists, tables, code, `$$maths$$`,
   images, quotes, `A -> B -> C` lines) and run `vidgen plan outline.md --json` (`--language
   pt-BR`, `--format 9:16` as needed): it writes a draft project with a scene type per block,
   the prose cut into beats of 6–15 words, compressed on-screen texts, chapters for long videos,
   a `# plan:` comment on every scene (why that type) and `# TODO:`s (what to check). It is a
   draft, not a video: work through every TODO, rewrite the narration for the ear (placeholder
   beats repeat their labels), make on-screen texts keywords, then go on with step 3.
2. **Write `video.yaml`**: narration as beats, content as params. Keep beat `id`s stable once
   audio exists (an edited beat keeps its id; only that beat is re-voiced).
3. **`vidgen validate --json`**: fix every entry of `problems` (`location` is a config path such
   as `scenes[2].params.items`, `message` says what is wrong and usually the fix: did-you-mean
   names, known values). Read `warnings` too (unused pronunciations, missing pictures,
   chapters YouTube would ignore). Repeat until `ok` is true.
4. **`vidgen storyboard`**: renders the preview (timed from word counts until audio exists) and
   writes contact sheets to `build/preview/storyboard/` (`video-1.png`, ...; one per scene in
   `scenes/<id>-1.png`; `--json` lists the paths). **Open the PNGs and look.** Each still is the
   end of a beat, labelled `beat @ time` with its narration underneath. Ask of every still:
   - Is it obvious what to look at? Is the newest element the most prominent?
   - Does the picture match the words under it (and not repeat them)?
   - Is anything cut off, crowded, tiny, or overlapping? Is a frame mostly empty?
   - Does the scene look like its neighbours (same header band, same colours)?
   Use `--scene ID` to look closer and `--per-beat 3` to see animations and actions mid-beat.
5. **`vidgen lint --json`**: every finding has `scene`, `beat`, `rule`, `severity`, `message`
   (with the measured `value` and the `limit`) and `still` (the PNG to open). Fix the cause,
   not the symptom (see `vidgen guide troubleshooting`); use a scene's `lint_ignore` only for a
   finding you mean to have, with a YAML comment saying why. `ok: false` means a finding at or
   above `fail_on` (default `error`); aim for zero findings.
6. **Fix and repeat** 3–5 until the storyboard reads well and lint is clean. Re-runs are cheap:
   only changed scenes are rendered again. Check every variant you ship
   (`vidgen lint --variant vertical`).
7. **`vidgen tts --dry-run`**: what would be sent to the voice service, per beat, with the
   pronunciation applied (`says: ...`) and the character count (what is billed). Read it:
   numbers, acronyms and names are where voices go wrong.
8. **`vidgen tts`**: voices only new or changed beats (needs `ELEVENLABS_API_KEY`; costs money).
9. **`vidgen render`** (`--preview` first): now timed by the real audio. Beats change length,
   so run `vidgen storyboard` and `vidgen lint` again: `narration_speed` and `dead_air` now
   measure the real speech. For a cartoon, `vidgen render --draft` is faster still (about 8 fps,
   240p, no idle motion, wind, shadows, particles or light grade; every timing, position, action
   and the lip sync kept): `<output>_draft.mp4`, to watch the timing and staging before a preview.
   `vidgen animatic` is quicker still once the storyboard's stills are current (seconds, no
   rendering): `<output>_animatic.mp4`, those stills held in time with the narration, with the
   audio and the subtitles, to check the pacing.
10. **`vidgen readback`** (optional extra `schu-video-generator[stt]`): speech-to-text of the MP3s against
    your texts; it names misheard terms and suggests a pronunciation entry, and lists the
    **words to check**: heard with low confidence or after an odd pause inside a sentence, with
    their time in the beat and in the video. Fix, `vidgen tts`, and `vidgen lint` again (its
    `readback` rule reads the cached transcripts; `vidgen lint --readback` also reports the words
    to check, rule `unclear_speech`).
11. **Final**: `vidgen render` (the full-size `format`, 1920x1080 by default) and a last
    `vidgen lint --final`.

```text
vidgen validate --json
vidgen storyboard --json          # then open the PNGs it lists
vidgen lint --json
vidgen tts --dry-run
vidgen tts
vidgen render --preview
vidgen lint --fail-on warning
vidgen render
```

**Costs.** `vidgen tts` (ElevenLabs or OpenRouter, per character; `voice.provider: kokoro` is local and
free), `vidgen imagegen` (OpenAI Images or OpenRouter, per picture) and `vidgen readback` with
`stt: {provider: elevenlabs}` cost money; everything else is local and free. Always run `vidgen tts --dry-run` / `vidgen imagegen --dry-run` first, finish the
layout on the word-count-timed preview, and commit `audio/` and `assets/generated/` (they cannot
be made again identically). Renders are slow but free: `storyboard`, `lint` and `render` re-render
only the scenes that changed (`render` reuses the storyboard's renders of the same format;
`--force` renders everything, e.g. after editing a file outside `assets/`); `--jobs N` renders
several at once, and `--jobs auto` picks N from the available memory (1.5 GB per job) and the CPU
cores and prints why; never run two vidgen commands at once, and run Kokoro `tts` alone; preview
while iterating.

**JSON everywhere.** Every command but `mcp` takes `--json` (`validate`, `list-scenes`,
`schema`, `storyboard`, `lint`, `render`, `tts`, `imagegen`, `plan`, `init`, ...): one document on
stdout, `{version, ok, warnings, ..., error?}`, exit code 0 exactly when `ok`. `vidgen tts
--dry-run --json` lists every beat to voice with its characters; `vidgen imagegen --dry-run
--json` every picture with its prompt and estimated cost.

**Through MCP.** When your client has the vidgen MCP server (`vidgen mcp --root DIR`), the same
commands are tools with the same JSON documents: `guide`, `plan`, `init`, `validate`, `schema`,
`list_scenes`, `list_icons`, `list_themes`, `list_sfx`, `list_music`, `music_preview`, `storyboard`, `lint`,
`render`, `tts`, `imagegen`, `readback`, `slides`, `thumbnail`, `export`, `gallery`,
`translate_template`, `character_sheet`, `direct`, `screenplay`, `cast`, `animatic` (options in snake_case: `per_beat`,
`fail_on`). Paths are
relative to the server's root folder. `storyboard` returns the contact sheets as images (look at
them; page with `image_offset`), `thumbnail`, `gallery` and `character_sheet` their pictures. `render` previews by default. `tts` and
`imagegen` are dry runs unless you pass `dry_run: false` and `confirm_cost: true`: run the dry
run, tell the user what it will cost, and confirm only after they agree.

<!-- topic: pacing (also: story, storytelling, text, narration, beats) -->
## Storytelling and pacing

**Structure.** Hook (0–5 s) → context (why it matters) → 3 to 5 ideas, one scene each →
recap → call to action. A video over 2 minutes gets **chapters** (`chapter` cards or a scene's
`chapter:` key; at least 3, each ≥ 10 s, so YouTube lists them) and a `progress_bar` overlay.

**The hook.** The first beat earns the next 30 seconds. Open on the most surprising fact, a
question the viewer wants answered, or the end result ("This chart took 4 seconds to make").
`stat`, `text_card` and a short `title` work; a silent intro card or a logo does not.

**Beats.** One beat = one thought the viewer hears while one thing happens on screen.
- 1–2 sentences, 6–15 words. vidgen times beats from their word count until the audio exists
  (`narration.words_per_second`, 2.6), and lint's `narration_speed` expects 1.8–3.5 words/s
  (English; other languages have their own range).
- A beat over ~20 words is two beats: split it, and give each half its own reveal.
- Write for the ear: short words, active voice, no parentheses, no "e.g." or "i.e.", no
  "as you can see". Numbers as people say them ("about a third" beats "33.3%").
- Spell out what the voice should say only through `pronunciation:` (`vidgen guide audio`),
  so the subtitles keep the written form.

**A visual change every 3–6 s.** Every built-in scene reveals one step per beat (an item, a
bar, a node, an event). With short beats that gives a change every few seconds for free. A
long beat over a finished picture is dead air: split it, or add an action (`highlight`,
`callout`, `zoom`) in the middle (`at: 0.5`).

**On-screen text.**
- The screen carries **keywords**, the voice carries **sentences**. A bullet is a label
  ("Same accuracy"), not the sentence being spoken ("The model reaches the same accuracy").
- Never put the narration on screen verbatim (captions are the exception, and they are an
  overlay: `vidgen guide social`).
- Limits: title ≤ 7 words; heading ≤ 5; list items ≤ 6 words, ≤ 5 items; labels 1–3 words;
  ≤ ~20 words visible at once. More content → more scenes.
- Numbers on screen get a unit and a comparison (`stat` `comparison`, a chart `caption` with
  the source).

**Progressive reveal.** Item *i* appears at beat *i*, so the newest element is what the voice
talks about. Keep the default step-by-step reveal of lists, grids, timelines, diagrams and
processes; use
`dim_previous: true` on `bullets` for long lists; `groups` on `icon_grid` to bring related
items together. `reveal: all` only when the whole picture is the point (a chart's bars).

**Endings.** Recap the 3 takeaways in one scene (each a beat), then an `end_card` with one
call to action (a link, "try it", "subscribe"), narrated in one short beat.

<!-- topic: social (also: vertical, shorts, reels, tiktok, mobile) -->
## Vertical and social videos

A 9:16 variant renders the same config for phones:

```yaml
variants:
  social:
    format: {width: 1080, height: 1920}
    preview: {width: 480, height: 854}
    overlays: [{type: captions, style: karaoke}]
scenes:
  - id: hook
    type: text_card
    params: {text: "77% dead weight"}
    beats:
      - text: "Most of your model is doing nothing at all."
```

- **Captions on**: most people watch muted. `captions` with `style: karaoke` shows a few big
  words with the spoken one highlighted; `voice: {timestamps: true}` makes the word timing
  exact (same TTS price).
- **Bigger type** comes automatically: the `auto` type scale is `large` in portrait. Keep
  texts even shorter than in 16:9 (labels of 1–2 words).
- **Faster cuts**: 30–60 s in total, beats of 6–10 words, a new scene every 5–10 s.
- **The first frame matters**: feeds show it before anything plays. Open with big text at once
  (`stat`, `text_card`), never a silent card, and set a designed `thumbnail:` (the cover).
- Layouts adapt by themselves (columns stack, timelines turn vertical, diagrams run top to
  bottom), but check `vidgen storyboard --variant social`: wide tables (> 4 columns), long
  diagrams and 16:9 screenshots get small. Split them or choose another type. (A landscape
  screenshot's callout steps zoom in on their areas by themselves in 9:16, and a landscape
  `video_clip` without callouts shows a nearly square part from its middle; an `image` keeps its whole
  picture unless you set `fit: cover`.)
- Phone apps cover the bottom ~15 % with their buttons: captions and lower thirds lift
  themselves above it; keep the key part of your own pictures and clips out of it.
- **Cartoons** (`stage` scenes) in 9:16 keep their 16:9 stage: the narrow frame crops it and the
  camera moves to whoever speaks (`reframe: speaker`, on by itself when the characters do not
  fit in one view; a short reply holds the view; your own `pan` / `follow` / `zoom` / `shot`
  win). `reframe: none` (top level or a stage's param) squeezes the whole stage into the frame
  instead. `vidgen direct --variant social` lists the camera's moves. Give the 9:16 variant
  `character_size: large` (top level, or a stage's param; `small` / `medium` / `large`, default
  `medium`): characters measured against the narrow width are small on a phone; text keeps its size.

<!-- topic: scenes (also: chooser, types, scene-types) -->
## Choosing the scene type

Pick by **what the viewer should understand**, not by what the data looks like. To see what
each type looks like at 16:9 and 9:16, open the scene gallery (`docs/gallery/README.md` in the
schu-video-generator repository: a still, a GIF, the YAML, params and targets per type) or make it yourself:
`vidgen gallery --output gallery --types pie,map` (any folder; in a project it also renders the
project's own scene types, in its theme).

| you want to show | scene type | key params |
|---|---|---|
| the title, who made it | `title` | `title`, `subtitle`, `kicker`, `highlight`, `icon` |
| a new section | `chapter` | `number`, `title`, `subtitle`, `icon` |
| one statement or question, big | `text_card` | `text`, `color` |
| a few points, in order | `bullets` | `heading`, `items`, `numbered`, `dim_previous` |
| a set of things (features, parts, options) | `icon_grid` | `heading`, `items`, `groups`, `highlight`, `icon_color` |
| A vs B, before / after, pros / cons | `comparison` | `heading`, `columns`, `verdict`, `vs`, `reveal` |
| exact values to compare across attributes | `table` | `title`, `header`, `rows`, `number_format` |
| what happened when | `timeline` | `heading`, `events`, `spacing`, `highlight`, `now` |
| how parts connect, decisions, architecture | `diagram`, `flowchart` | `heading`, `nodes`, `edges`, `highlight`, `direction` |
| something moving through stages | `process` | `heading`, `stages`, `input`, `output`, `loop`, `token_label` |
| a neural network | `network` | `heading`, `layers`, `connect`, `highlight` |
| one number that matters | `stat` | `value`, `label`, `comparison`, `context`, `prefix`, `suffix`, `unit` |
| categories compared by size | `bar_chart` | `title`, `labels`, `values`, `unit`, `highlight`, `caption`, `changes`, `sort` |
| change over time, trends | `line_chart` | `title`, `x`, `series`, `x_label`, `y_label`, `changes` |
| a relationship between two measures | `scatter` | `title`, `series`, `trend`, `highlight`, `x_label`, `y_label` |
| how values are distributed | `histogram` | `title`, `values`, `bins`, `mean`, `median`, `highlight` |
| parts of a whole (≤ 6 parts) | `pie` | `title`, `labels`, `values`, `donut`, `highlight`, `other_below` |
| a matrix (correlations, hours x days) | `heatmap` | `title`, `rows`, `columns`, `values`, `highlight` |
| where in the world | `map` | `title`, `view`, `steps`, `values`, `pins`, `arcs` |
| a photo or illustration | `image` | `path`, `generate`, `caption`, `fit`, `ken_burns` |
| a user interface, a web page | `screenshot` | `path`, `steps`, `frame`, `url`, `caption` |
| footage, a screen recording | `video_clip` | `path`, `steps`, `trim`, `fit_duration`, `region`, `mute` |
| a quotation | `quote` | `text`, `author`, `source` |
| a formula that transforms | `equation` | `latex`, `terms`, `caption` |
| a derivation with reasons | `equation_derivation` | `title`, `steps`, `colors`, `result` |
| a function's graph: slope, tangent, area under a curve | `function_plot` | `title`, `functions` (expressions: x^2, f(x) = sin(x)...), `x_range`, `y_range`, `dots`, `areas`, `aspect` |
| geometry, vectors: a triangle with braces and angles, adding and scaling vectors | `function_plot` | `points` (at, name), `vectors` (from, to, or sum: [a, b]), `marks` (segment, brace, angle, dimension), `axes` (false: pure geometry) |
| a number line: points, intervals, jumps (+3) | `number_line` | `title`, `range`, `points`, `intervals` ("[-1, 3)"), `jumps` ([2, 5]: an arc labelled +3), `step` |
| a short listing (≤ 15 lines) | `code` | `title`, `code`, `path`, `highlight` |
| code that changes: before / after, a refactor, a fix | `code_morph` | `title`, `versions` (each the code, or code / path / highlight) |
| a long file, explained part by part | `code_walkthrough` | `title`, `path`, `code`, `steps`, `excerpt` |
| running a command: install, tests, a REPL (output written by you) | `terminal` | `title`, `steps` (each a command, or command / output / clear), `prompt`, `language`, `code` |
| characters on a set (a cartoon) | `stage` | `characters`, `props`, `background`, `image`, `generate`, `marks`, `ground`, `layers`, `width`, `particles`, `light`, `wind` |
| a cartoon's title card, "Later that day…", "The End" | `card` | `text`, `subtitle`, `style`, `color`, `sting` |
| thanks, links, call to action | `end_card` | `title`, `lines`, `icon`, `logo` |

How beats drive scenes: each type splits its content into **reveal steps** and plays step *i*
at beat *i* (more steps than beats: spread evenly; more beats: the last ones hold). Types with
per-beat data (`code_walkthrough`, `terminal`, `equation_derivation`, `screenshot`, `video_clip`, `map`)
take a `steps` list, entry *i* for beat *i*: write as many steps as beats (`code_morph`:
one of its `versions` per beat). A `highlight` param
adds a last step that marks one thing and dims the rest, so give it its own beat. Silent
scenes have a `duration` instead of beats (chapter cards: 2–3 s). Every header-band type
accepts `heading` and `title` alike.

Minimal snippets (copy, then adapt):

```yaml
# text and structure
- id: opening
  type: title
  params: {kicker: "EXPLAINER", title: "Saving 77% of the parameters", highlight: "77%", icon: brain-circuit}
  beats: [{text: "What if most of a model could simply go?"}]
- id: part1
  type: chapter
  params: {number: 1, title: "The problem", icon: triangle-alert}
  duration: 2.5
- id: question
  type: text_card
  params: {text: "Do we need all those parameters?", color: highlight}
  beats: [{text: "So do we really need all of them?"}]
- id: steps
  type: bullets
  params:
    heading: "Three steps"
    numbered: true
    items: [{text: "Measure", icon: gauge}, {text: "Prune", icon: funnel}, {text: "Retrain", icon: refresh-cw}]
  beats:
    - text: "First, measure which weights matter."
    - text: "Then remove the rest."
    - text: "And retrain briefly to recover."
- id: parts
  type: icon_grid
  params:
    heading: "What the platform covers"
    icon_color: palette
    items:
      - {icon: cpu, label: "Compute"}
      - {icon: database, label: "Storage"}
      - {icon: network, label: "Network"}
      - {icon: shield-check, label: "Security"}
    groups: [[0, 1], [2, 3]]
  beats:
    - text: "Compute and storage come first."
    - text: "Then networking and security."
- id: choice
  type: comparison
  params:
    heading: "Monolith or microservices?"
    vs: "vs"
    columns:
      - {heading: "Monolith", tone: positive, points: ["One deploy", "Simple setup"]}
      - {heading: "Microservices", tone: negative, points: ["Many deploys", "Network failures"]}
    verdict: "Start with a monolith"
  beats:
    - text: "A monolith ships as one piece."
    - text: "Microservices multiply the moving parts."
    - text: "So start simple, and split later."
- id: results
  type: table
  params:
    title: "Benchmark"
    header: ["Model", "Params", "Accuracy"]
    rows: [["Baseline", 110, 0.812], ["Sparse", 55, 0.809]]
    number_format: [null, "{:,.0f}M", "{:.1%}"]
  beats:
    - text: "The baseline has a hundred and ten million parameters."
    - text: "The sparse one has half, at the same accuracy."
- id: history
  type: timeline
  params:
    heading: "The space race"
    events:
      - {date: 1957, title: "Sputnik", icon: satellite}
      - {date: 1961, title: "Gagarin", icon: user}
      - {date: 1969, title: "Apollo 11", icon: moon}
  beats:
    - text: "In 1957, the first satellite, Sputnik, reached orbit."
    - text: "Four years later, Gagarin flew."
    - text: "And in 1969, people walked on the Moon."
- id: outro
  type: end_card
  params: {title: "Try it yourself", icon: link, lines: ["github.com/me/project"]}
  beats: [{text: "The code is online. Try it on your own model."}]
```

```yaml
# flows
- id: release
  type: flowchart
  params:
    heading: "How a change ships"
    nodes:
      - {id: pr, label: "Pull request", shape: pill}
      - {id: ci, label: "Tests pass?", shape: diamond}
      - {id: fix, label: "Fix the code"}
      - {id: ship, label: "Deploy", icon: rocket}
    edges: ["pr -> ci", "ci -> ship: yes", "ci -> fix: no", "fix --> ci"]
    highlight: [pr, ci, ship]
  beats:
    - text: "Every change starts as a pull request."
    - text: "The tests decide what happens next."
    - text: "A failure goes back for a fix."
    - text: "A pass goes straight to production."
    - text: "That is the path most changes take."
- id: order
  type: process
  params:
    heading: "What happens to an order"
    input: "Checkout"
    output: "At your door"
    token_label: "order"
    stages: [{label: "Pay", icon: credit-card}, {label: "Pack", icon: package}, {label: "Ship", icon: truck}]
  beats:
    - text: "At checkout, the order is paid."
    - text: "The warehouse packs it."
    - text: "And a courier brings it to your door."
- id: mlp
  type: network
  params:
    heading: "A small classifier"
    layers: [{size: 784, label: "Pixels"}, {size: 128, label: "Hidden"}, {size: 10, label: "Digits"}]
  beats:
    - text: "Every pixel is an input."
    - text: "A hidden layer combines them."
    - text: "Ten outputs score the ten digits."
    - text: "A forward pass flows from left to right."
```

```yaml
# data
- id: users
  type: stat
  params:
    value: 73
    suffix: "%"
    label: "of developers use AI tools"
    comparison: {value: 44, label: "in 2023"}
    context: "Survey of 12,000 developers"
  beats:
    - text: "Almost three in four developers now use AI tools."
    - text: "Two years ago, it was not even half."
- id: speed
  type: bar_chart
  params: {title: "Render time per minute", labels: ["480p", "1080p", "4K"], values: [0.4, 2.6, 9.8], unit: " min", caption: "Measured on 2 CPUs"}
  beats:
    - text: "Higher resolutions take much longer."
    - text: "Four K is twenty-five times slower than a preview."
      actions: [{highlight: "bar:4K", style: box}]
- id: loss
  type: line_chart
  params:
    title: "Validation loss"
    x: [1, 2, 3, 4, 5]
    x_label: "epoch"
    series: {baseline: [2.1, 1.8, 1.66, 1.58, 1.53], sparse: [2.2, 1.9, 1.68, 1.55, 1.49]}
  beats:
    - text: "The baseline improves steadily."
    - text: "The sparse model starts slower, but ends lower."
- id: ranking
  type: bar_chart
  params:
    title: "Most loved languages"
    labels: [Python, Rust, Go]
    values: [62, 48, 31]
    changes: [[58, 66, 30], [55, 72, 41]]   # the values at each later step; bars grow / shrink
    sort: true                              # and re-sort, largest first
    unit: "%"
  beats:
    - text: "In the first survey, Python led."
    - text: "A year later Rust overtook it."
    - text: "Then Go climbed as well."
      actions: [{reveal: change2, at: "@climbed"}]   # change 2 on that word
- id: training
  type: line_chart
  params:
    title: "Training loss"
    x: [1, 2, 3, 4]
    series: {loss: [2.4, 1.8, 1.4, 1.2], accuracy: [0.3, 0.5, 0.6, 0.65]}
    changes: [{loss: [1.0, 0.5, 0.3, 0.2]}]   # series left out keep their values; the y axis rescales
    reveal: all
  beats:
    - text: "Here is the loss over four epochs."
      actions: [{trace: "series:loss", to: 3, at: "@four"}]   # a cursor dot with the value sweeps the line
    - text: "With pretraining it starts far lower."
- id: size_vs_accuracy
  type: scatter
  params:
    title: "Size vs accuracy"
    x_label: "parameters (billions)"
    y_label: "accuracy (%)"
    trend: all
    series: {baselines: [[1.3, 61], [6.7, 70], [13, 73]], ours: [[1.0, 66], [3.8, 72, "small"]]}
    highlight: "ours@small"
  beats:
    - text: "Bigger baselines score higher."
    - text: "Ours sit above the line."
    - text: "The trend makes the gap clear."
    - text: "Especially for the small one."
- id: latency
  type: histogram
  params:
    title: "Response times"
    x_label: "milliseconds"
    values: [12, 15, 17, 18, 21, 22, 23, 25, 26, 28, 30, 31, 33, 35, 38, 41, 45, 52, 61, 75, 97]
    median: true
  beats:
    - text: "Most requests finish fast."
    - text: "Half of them in under thirty milliseconds."
- id: devices
  type: pie
  params: {title: "Visits by device", donut: true, labels: ["Mobile", "Desktop", "Tablet"], values: [5200, 3100, 640], highlight: Mobile}
  beats:
    - text: "Most visits come from phones."
    - text: "More than half of them."
- id: busy
  type: heatmap
  params:
    title: "Renders per hour"
    rows: ["Mon", "Tue"]
    columns: ["9h", "12h", "18h"]
    values: [[3, 8, 9], [5, 10, 11]]
    highlight: "col:18h"
  beats:
    - text: "Each cell counts the renders in one hour."
    - text: "Evenings are the busiest."
- id: offices
  type: map
  params:
    title: "Our offices"
    view: europe
    steps:
      - [Germany, France]
      - pins: [{lon: -0.13, lat: 51.51, label: London}]
  beats:
    - text: "We started in Germany and France."
    - text: "Then we opened in London."
```

```yaml
# pictures and media
- id: harbour
  type: image
  params: {generate: "a quiet harbour at dawn, fishing boats, mist over the water", fit: cover, ken_burns: true}
  beats: [{text: "It started in a small harbour town."}]
- id: lab
  type: image
  params: {path: assets/lab.png, caption: "The training cluster"}
  beats: [{text: "Everything ran on this machine."}]
- id: app
  type: screenshot
  params:
    title: "Find any task"
    path: assets/app.png
    frame: browser
    steps:
      - {box: [0.22, 0.04, 0.27, 0.06], label: "Search"}
      - {arrow: [0.86, 0.07], label: "New task"}
  beats:
    - text: "The search box at the top finds any task in seconds."
    - text: "And one click on this button adds a new one."
- id: demo
  type: video_clip
  params: {path: assets/demo.mp4, trim: [1, 5], fit_duration: true, mute: true, caption: "The app, live"}
  beats: [{text: "Here it is running live."}]
- id: saying
  type: quote
  params: {text: "Simplicity is prerequisite for reliability.", author: "Edsger W. Dijkstra"}
  beats: [{text: "As Dijkstra put it, simple systems are the reliable ones."}]
```

```yaml
# maths and code
- id: square
  type: equation
  params: {latex: ["(a + b)^2", "a^2 + 2ab + b^2"], terms: ["2ab"]}
  beats:
    - text: "Take a plus b, squared."
    - text: "The middle term is where the cross products hide."
      actions: [{zoom: "term:2ab"}]
- id: solve
  type: equation_derivation
  params:
    title: "Solving for x"
    colors: {x: accent}
    steps: ['2x + 3 = 11', {tex: '2x = 8', note: "Subtract 3"}, {tex: 'x = 4', note: "Divide by 2"}]
  beats:
    - text: "Two x plus three is eleven."
    - text: "Take three from both sides."
    - text: "So x is four."
- id: slope
  type: function_plot    # f(x) written as maths (parsed safely: x^2, 2x + 1, sin(x), exp(-x^2/2)); one item per beat
  params:
    title: "The slope of x²"
    functions: ["f(x) = x^2"]
    x_range: [-3, 3]
    dots: [{x: -2, tangent: true, label: "slope {slope}"}]   # a live label: {x}, {y}, {slope}
    areas: [{between: [0, 1], label: "A = {area}"}]           # the area under f, its size filled in
  beats:
    - text: "Here is the parabola, f of x equals x squared."
    - text: "A dot on the curve, with its tangent."
    - text: "As the dot moves right, the slope grows steeper."
      actions: [{trace: dot1, to: 2, at: "@moves"}]   # the dot travels along the curve on the word
    - text: "The area under the curve grows as its end moves out."
      actions: [{trace: area1, to: 2.5, at: "@grows"}]
- id: triangle
  type: function_plot    # geometry on the same plane: points, vectors and marks, no functions needed
  params:
    axes: false          # pure geometry; keep the axes for vectors on a grid
    points: [{at: [0, 0], name: A}, {at: [4, 0], name: B}, {at: [4, 3], name: C}]
    marks:
      - {segment: [A, B, C], closed: true}
      - {brace: [A, B], label: "4"}               # outside the triangle by itself
      - {angle: [B, A, C], label: "{angle}°"}     # the angle at A; a square at 90°
      - {dimension: [A, C], label: "c = {length}"}
  beats:
    - text: "A right triangle with sides four and three."
    - text: "Move C up and the angle at A opens."
      actions: [{trace: "point:C", to: [4, 4], at: "@Move"}]   # marks and labels follow
- id: vectors
  type: function_plot
  params:
    x_range: [-1, 6]
    y_range: [-1, 5]
    vectors: [{to: [3, 1], name: a}, {to: [1, 3], name: b}, {sum: [a, b], label: "a + b"}]   # b slides to a's tip
  beats:
    - text: "Vector a, and vector b."
    - text: "Put b at the tip of a: the sum runs from start to end."
    - text: "Double a and the sum follows."
      actions: [{trace: "vector:a", scale: 2, at: "@Double"}]
- id: hops
  type: number_line
  params:
    range: [-2, 8]
    points: [{at: 2, name: a}]
    intervals: ["[4, inf)"]                        # interval notation: [ ] closed, ( ) open, inf
    jumps: [[2, 5], [5, 7]]                        # arcs labelled +3, +2
  beats:
    - text: "Start at two."
    - text: "Every number from four on."
    - text: "Jump three to five."
    - text: "And two more to seven."
- id: snippet
  type: code
  params: {title: "Load and train", code: "data = load()\nmodel = fit(data)\nsave(model)", highlight: ["1", "2-3"]}
  beats:
    - text: "We load the data."
    - text: "Then fit and save the model."
- id: faster
  type: code_morph       # version i at beat i; the diff is computed for you: shared tokens glide, new lines grow in
  params:
    title: "Cache it"
    versions:
      - "def fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)"
      - {code: "@cache\ndef fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)", highlight: changed}
  beats:
    - text: "This version recomputes the same values again and again."
    - text: "One decorator, a cache, and each value is computed once."
      actions: [{reveal: version2, at: "@cache", run_time: 1.5}]   # morph on the word
- id: shell
  type: terminal         # step i at beat i: the command is typed, then its output appears (you write it: nothing runs)
  params:
    title: "Run the tests"
    code: {code: "def mean(xs):\n    return sum(xs) / len(xs)", highlight: 2}   # optional: the code beside it
    steps:
      - {command: "pytest -q", output: "..F\n1 failed, 2 passed in 0.03s"}
      - {command: "python -c 'print(mean([]))'", output: "ZeroDivisionError: division by zero", output_color: secondary}
  beats:
    - text: "We run the tests, and one of them fails."
      actions: [{reveal: output1, at: "@fails"}]   # the output on the word
    - text: "An empty list divides by zero."
- id: walk
  type: code_walkthrough
  params:
    title: "The training loop"
    code: "def train(data):\n    model = init()\n    for batch in data:\n        loss = step(model, batch)\n    return model"
    steps: [{lines: "1-2", note: "Set up the model"}, {lines: "3-4", note: "One step per batch"}]
  beats:
    - text: "The function starts by creating the model."
    - text: "Then it takes one step per batch."
```

```yaml
# cartoons
characters:              # top level of video.yaml: declared once, used by any stage
  - {name: pip, look: {body: bean, hair: short}}
  - {name: kit, look: {body: tall, hair: spiky, accessories: [scarf]}}
scenes:
  - id: park
    type: stage
    params:
      background: [primary, highlight]   # a gradient sky; or image: / generate: for a picture
      characters:
        - {name: pip, at: left, pose: waving, expression: happy}
        - {name: kit, at: right, depth: 0.3}   # further back: smaller, drawn behind
    beats: [{text: "Pip waves at an old friend across the park."}]
```

```yaml
# cartoons
- id: later
  type: card                  # style: burst (rays turning), frame or plain
  params: {text: "Later that day…", subtitle: "at the old mill", sting: comic}
  duration: 2.5               # silent; or beats: to narrate it
```

A whole cartoon (characters, staging, shots, timing, title cards and irises): `vidgen guide cartoons`.

**When to write a custom scene type** (a Python file in the project's `extensions/`, see
`docs/EXTENDING.md`): when the idea is a specific drawing no built-in can express (a mechanism,
a geometric construction, a bespoke animation) and you would otherwise bend a built-in into
it. Prefer built-ins whenever one fits: they are tested at 16:9 and 9:16, fit text to readable
sizes, expose action targets and pass lint. Custom scenes should use regions
(`self.region("body")`, `place(...)`) rather than fixed coordinates, and get checked with the
same storyboard and lint loop.

<!-- topic: design (also: visual, theme, themes, colors, colours, icons, accessibility) -->
## Visual design

**Theme presets** (`theme: {preset: NAME}`; `vidgen list-themes --swatches themes.png` shows
them side by side). Pick one per video and keep it:

| preset | looks | use it for |
|---|---|---|
| `dark_tech` | dark slate, cyan / amber accents (the default) | technical explainers, software, AI |
| `light_academic` | off-white, ink colours, serif headings | papers, lectures, research results |
| `high_contrast` | black and white, large type | accessibility first, low-vision audiences |
| `warm_editorial` | cream paper, serif headings and quotes | essays, history, storytelling |
| `brand_neutral` | light grey, one blue | company videos: set `colors: {primary: "#..."}` to your brand |
| `soft_pastel` | dusky plum, pastels | friendly tutorials, education for beginners |
| `bold_neon` | violet-black, neon, large type | short social clips, launches |

```yaml
theme:
  preset: brand_neutral
  colors: {primary: "#0B5FFF"}
```

**Colour roles.** Use the theme's tokens, not hex values, in params: `text` / `dim` for text,
`primary` for the main element, `highlight` for "look here" (one thing per frame), `accent`
for warnings and bad news, `tertiary` for good news, `surface` for panels, `palette` for
series. Meaning never rides on colour alone: `comparison` adds check / cross markers, charts
label their series, `stat` chips carry an arrow. Every preset passes WCAG AA and has a
colour-blind-safe palette (except `dark_tech`'s blue and purple for deuteranopes: pick another
preset if that matters).

**One colour per concept.** Give the few concepts an explainer keeps coming back to a colour of
their own, once, at the top of `video.yaml`; vidgen then draws those words in that colour
wherever they are written (titles, bullets, cards, chart and diagram labels, captions, a
callout naming one, a `line_chart` series named after one) and their TeX parts in equations:

```yaml
terms:
  loss: accent
  gradient: "#E07A5F"
  learning rate: {color: secondary, tex: '\eta'}   # also η in equation scenes
```

Whole words, any case, plurals too. At most about 5 colours, each readable on the background
(lint `concept_colors` checks both). Do not colour the same word otherwise in a scene (a
title's `highlight_color`, a series' `color`, an `equation_derivation`'s `colors`, a plotted
function's or area's `color`, a callout's `color`): lint warns. `terms: false` on a scene turns it off there (a recap in plain colours).

**Icons.** 200 line icons in one style. Find them by concept:
`vidgen list-icons --search growth`, `vidgen list-icons --category data`, and look at them in
your theme with `vidgen list-icons --search money --sheet icons.png --theme`. Use icons for
categories and steps (`icon_grid`, `bullets` items, `process` stages, `timeline` events), not
as decoration; one icon per idea, the same icon for the same idea across scenes. A project can
add its own SVGs in `assets/icons/`.

**Layout and consistency.** Built-in scenes lay themselves out in named regions (a `header`
band for the title, the `body` below it), adapt to 16:9 and 9:16, and never shrink text below
the readable size (they warn instead: then split the content). So consistency comes from
choices: one preset, the same heading length and style everywhere, the same icon set, the same
transition. Overlays with `reserve: true` shrink every scene's safe area: reserve only what must
stay clear all the time.

**Accessibility.** Lint checks contrast (WCAG AA, 4.5:1) and minimum text size for the output;
keep both clean. Burn in `captions` for social video; the SRT (`<output>.srt`) is always
written for players. `high_contrast` or `scale: large` for audiences that need it.

<!-- topic: actions (also: targets, callouts, highlight, zoom) -->
## Pointing at things: beat actions and callouts

A beat can act on named **targets** of its scene while it is spoken: `vidgen list-scenes`
prints each type's targets (`bar:<label>`, `item<N>`, `node:<id>`, `point:<series>@<x>`...), and
`vidgen validate` lists the valid names when one is wrong.

| action | use it to | restraint |
|---|---|---|
| `highlight` | make the thing the voice names stand out (`style: color`, `box`, `underline`, `fill`, `flash`) | one target per beat |
| `dim` | push the rest back (`opacity`) | pair with a highlight, undo with `until` |
| `callout` | label or point at something (`kind: box`, `circle`, `arrow`, `label`, `spotlight`, `magnifier`) | one per beat; gone at the next beat |
| `zoom` | look closer at a detail, then come back | at most one per scene |
| `pan` | on a `stage`: move the camera to a character or a mark (`to: right`) | on a stage wider than the frame (`width: 2`) |
| `follow` | on a `stage`: keep the camera on a character as it moves (on a platform `level` gently, up and down too; `level: {follow: hero}` follows from the start) | one at a time |
| `reveal` | bring a later element in early | rarely: the default order is usually right |
| `transform` | morph one target into another (`into`) | for equations and before / after |
| `trace` | on a `function_plot`: move a dot along its curve (`- trace: dot1`, `to: 2`; its value label and tangent follow), an area's right end, a point (`to: [x, y]`) or a vector's tip (`to: [x, y]`, or `scale: 2`), everything drawn from them following; on a `number_line`: a point (`to: 4`); on a `line_chart`: a cursor dot along a series (`- trace: series1`, `to: 4`, the line's value over it) | one movement per beat, timed to the word that says it |
| `sfx` | a sound at that moment (`vidgen guide audio`) | the important moments only |
| `particles` | rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves or streaks (wind lines) over any scene (`- particles: confetti`; `density`, `area`, `keep: true` for the rest of the scene) | a mood or a celebration, not on dense text |
| `wind` | on a `stage`: fade the wind to `0.8` or `calm`, `breeze`, `windy`, `gale` (`- wind: gale`; `run_time` = the fade, 2 s) | a storm coming, a gust in the story |
| `blow_away` | on a `stage`: the wind blows a light prop away, tumbling, out of a hand too (`- blow_away: napkin`; `to:` a mark to land there, else off the stage) | a gust in the story; napkin, umbrella, ball, cup, basket, box, letter, balloons only |
| `light` | on a `stage`: fade the light to `morning`, `sunset`, `night`, `indoor` or `day` (`- light: night`; `run_time` = the fade, 2 s; `move_sun: true` moves a `sun` / `moon` prop across the sky, shadows turning) | when time passes in the story |
| `lightning` | on a `stage`: the set flashes and a bolt strikes (`- lightning: right`; `distance: 2`: its thunder ~6 s later; in a room the windows flash) | a storm, a scare; rain with `lightning: true` strikes on its own |
| `rainbow` | on a `stage` outdoors: a rainbow fades into the sky and stays (`- rainbow: centre`; `hide: true` fades it out) | after the rain |
| `switch_on` | on a `stage`: a `tv`, `lamp`, `kettle` goes on, a `fireplace` burns, a `phone` rings (`- switch_on: tv`; a click with foley) | when someone in the story switches it on or lights the fire; when a call comes |
| `switch_off` | on a `stage`: a `tv`, `lamp`, `kettle` or `fireplace` goes off, a `phone` stops ringing (`- switch_off: lamp`) | when someone in the story switches it off or answers |
| `knock` | on a `stage`: someone knocks three times on a door (`- knock: front`; a room's door or a `door` prop; nobody needs to stand there) | a visitor in the story; the door then `open`s with a creak |
| `let_go` | on a `stage`: a character lets go of the balloons it holds; they float away (`- let_go: pip`) | gone for the scene |
| `pour` | on a `stage`: a character pours with the watering can it holds (`- pour: kit`, 2 s) | watering a plant |
| `drop_fruit` | on a `stage`: a fruit falls from a tree with `fruit: true`, bounces, thuds (`- drop_fruit: tree`; `to: pip`: on pip's head, stars) | a comic moment; the character stands under the tree |
| `birds` | on a `stage` outdoors: a flock crosses the sky (`- birds: 5`; `direction: left`) | a calm outdoor moment, time passing |
| `say` | on a `stage`: pick who speaks the beat (`- say: kit`; `bubble: true` or a short text for a speech bubble) | without it the characters whose `voice` is the beat's voice speak; bubbles for short lines |
| `look_at` | on a `stage`: a character looks at another, a prop, a mark or `camera` (`to:`) | when attention moves |
| `turn` | on a `stage`: a character faces the other way (`to: left` / `right`), or the viewer (`to: front`: its front view) | an SVG character has no front view |
| `emote` | on a `stage`: change a character's expression (`to: happy`) | on the word that causes it (`at`) |
| `pose` | on a `stage`: change a character's pose (`to: pointing`) | one pose change per beat |
| `react` | on a `stage`: a listener's `expression` / `pose` for this beat only | the listener, not the speaker |
| `effect` | on a `stage`: a symbol over a character's head for this beat (`to: idea`, `question`, `exclaim`, `sweat`, `anger`, `sleep`, `hearts`, `stars`, `sparkle`, `tear`) | a feeling that should read at a glance; one per line |
| `walk_to` | on a `stage`: a character walks to a mark or x (`to:`; `speed`), also towards or away from the camera (`depth: 0.4`, or `to: {mark: right, depth: 0.4}`) | with `follow` on a wide stage; the walk takes its distance's time |
| `run_to` | on a `stage`: a character runs to a mark or x (`to:`; `speed`): longer strides, leaning forward, dust and speed lines | a hurry, a chase, an escape |
| `enter` | on a `stage`: a character walks in from an edge (`side:`) or through a room's door (`door: door`) to its mark (or `to:`) | it waits off stage until then |
| `exit` | on a `stage`: a character walks out by an edge (`to: left` / `right`) or through a room's door (`door: door`) | an `enter` brings it back |
| `gesture` | on a `stage`: `to: point`, `wave`, `shrug`, `nod`, `shake_head`; `big: true` adds a whoosh arc | on the word it goes with (`at`) |
| `jump` | on a `stage`: a character jumps (`height`); on a platform `level`, `to:` a spot, mark or tile jumps it there on a planned arc, picking up coins and stars on the way (`react: {when: land, expression: happy}`) | joy or surprise; getting onto a platform |
| `step_aside` | on a platform `level`: a blocker (`level.blockers`) moves out of the way (`- step_aside: tobble`; `to:` a place to walk to) | after the line that asks it nicely |
| `keyframes` | on a `stage`: move a character, prop or part (`kit.arm_left`) through `keys: [{t, x, y, rotate, scale, ease}]` (`t` seconds or `"40%"` of the beat) | motion no other action has; keep it short |
| `move_along` | on a `stage`: move a character, prop or part along `path: [[x, y], ...]` (smooth curve; `speed`) | flying, floating |
| `pick_up` | on a `stage`: a character reaches for a prop and holds it (`to: ball`; `hand`); it goes along with the hand | `walk_to` next to the prop first (`vidgen validate` says where) |
| `hold` | on a `stage`: a character holds a prop from now on, without picking it up (`to: cup`) | a prop it has from the start (`at: 0`) |
| `put_down` | on a `stage`: the held prop goes on the ground (`to:` a mark or x, default in front) | within reach |
| `give` | on a `stage`: the held prop goes to another character (`to: kit`) | the two stand next to each other |
| `throw` | on a `stage`: the held prop flies to a mark or x (`to:`; `spin`, `height`) and lands with a thud | |
| `open` | on a `stage`: an `umbrella` or `door` prop opens (`- open: umbrella`); a held umbrella goes up over its holder's head; `by: pip` reaches for it (a locked door on a `level` opens only by whoever holds its key) | `open: true` in `props` starts it open |
| `close` | on a `stage`: an open `umbrella` or `door` closes (`- close: door`); a held umbrella comes down to the hand | |
| `sit_on` | on a `stage`: a character sits on a `chair`, `rock`, `box`, `sofa`, `armchair`, `bed` or `desk` (`to: chair`); its hips and knees bend | next to the prop; `stand_up` before it walks |
| `lean_on` | on a `stage`: a character leans its back on a `tree`, `door`, `sign`, `lamp`, `house`, `bookshelf`, `counter` or `fridge` (`to: tree`) | next to the prop; `stand_up` before it walks |
| `stand_up` | on a `stage`: a character gets up from where it sits or leans | |
| `get_in` | on a `stage`: characters get in a `car`, a `bus`, a `boat` or a `hot_air_balloon` or on a `bicycle` (`to: car`); they ride with it until `get_out` | next to the vehicle; a bicycle seats 1, a car, a boat and a balloon 2, a bus 4 |
| `ride_to` | on a `stage`: a vehicle (or a rider: its vehicle) rides to a mark, an x or `{mark, depth}` with its riders, wheels turning; a boat along the water, a balloon or a `toy_rocket` flies there (`land: false`: away) | `get_in` first (a toy rocket: none) |
| `get_out` | on a `stage`: riders get out of their vehicle where it is | |
| `shot` | on a `stage`: the camera frames characters for the beat; write it as the beat's key `shot: closeup kit` (`wide`, `two_shot`, `medium`, `over_shoulder kit pip`); the next beat without one cuts back | a beat's dialogue line or reaction; not with a walk out of the framing |
| `host_point` | with a `host:`: the host's arm reaches towards a target of the scene and it looks there (`- host_point: item2`; `line: true`: a thin pointer line) | one per beat; a line only when nothing lies between the host and the target |
| `host_look` | with a `host:`: the host looks at a target of the scene (`- host_look: bar3`) | when attention moves |
| `host_react` | with a `host:`: the host's expression for this beat (`- host_react: happy`; `effect: sparkle` adds a symbol) | on a result or a surprise |
| `host_move` | with a `host:`: the host walks to the other side and the content slides over with it (`- host_move: other_side`, `left`, `right`) | one move per beat; rarely, between topics |
| `host_enter` | with a `host:`: the host walks in from an edge (`{action: host_enter}`, or `- host_enter: left`); the scene starts without it | at the start of the video |
| `host_exit` | with a `host:`: the host walks out by an edge (`- host_exit: left`); its room stays free | at the end |

```yaml
- id: speeds
  type: bar_chart
  params: {title: "Render time", labels: ["Preview", "1080p", "4K"], values: [0.4, 2.6, 9.8], unit: " min"}
  beats:
    - text: "Render time grows with the resolution."
    - text: "Four K is the slow one."
      actions:
        - {highlight: "bar:4K", style: box, until: speeds_b3}
    - text: "Previews are how you iterate."
      actions:
        - dim: ["bar:1080p", "bar:4K"]
        - callout: "bar:Preview"
          kind: arrow
          label: "Use this while editing"
          at: "@iterate"           # on that word (or a fraction of the beat: 0.3)
```

- `at` times the action to the word it belongs to: name the word, `at: "@gradient"` (quoted;
  `"@gradient#2"` its second time in the beat, `"@gradient-0.2s"` a moment before it,
  `"@learning rate"` a phrase), or give a fraction of the beat (0–1). A word is timed by the
  beat's audio once `vidgen tts` made it, by an estimate from the text before; a word the beat
  does not say is a `vidgen validate` error that lists the words like it. Every action takes it
  (`callout`, `sfx`, the stage's moves and acting too), and so does `lower_third`'s `at`
  (`"@Ada"`). Actions never make a beat longer.
- The `stage` actions (`say` to `throw`) take the character as the target and the new
  state as `to:` (`- emote: kit` + `to: happy`). How to use them together for a cartoon:
  `vidgen guide cartoons`.
- `until: <later beat id>` keeps a highlight / dim / callout on screen; without it a callout
  disappears at the next beat and a zoom comes back by the beat's end.
- A callout without a target points at an `area: [x, y, w, h]` of the frame (fractions).
- Check actions mid-beat with `vidgen storyboard --scene ID --per-beat 3`.

<!-- topic: cartoons (also: cartoon, characters, character, stage, dialogue, acting) -->
## Cartoons: characters on a stage

**When to make one.** When the idea has people in it: two points of view arguing it out, a
mistake and its fix, a story with a turn, a gentle explainer for beginners or children. A short
sketch also works as the hook of an explainer, before the charts. Not for numbers, code or
formulas: those have their own scene types, and a character pointing at a chart is slower than
the chart. Keep it small: 2–3 characters, one set per scene, 30–90 s.

**Original characters only.** Build them with the generator (`look:`) or from your own SVG
(`look: {svg: ...}`, `docs/CONFIG.md` "Characters"). Never imitate a known character, mascot,
brand figure or logo: not its silhouette and colours, its name or catchphrase, an SVG traced
from it, nor "in the style of" a studio in a `generate:` prompt or `cartoon_style`. If someone
asks for one, say vidgen makes original characters and offer one with the same role.
- Tell them apart at a glance: a different `body` (`round`, `tall`, `pear`, `triangle`...),
  hair (`ponytail`, `braids`, `afro`, or bald with `facial_hair: beard`), one signature item
  each (`hat`, `cap`, `bow`, `scarf`, `glasses`, `backpack`...), an `outfit` (`dress`,
  `overalls`, `coat`, `shorts`, `apron`; second colour `colors.trim`) in different theme tokens,
  maybe a `pattern` (`stripes`, `dots`) or `shoes`. A good test: would the two silhouettes,
  filled black, still differ? A child: `proportions: kid` (or `tall_kid`) and a smaller `scale`
  on the stage (about 0.7). An animal: `species: cat | dog | bird | bear | rabbit | mouse |
  fox | owl | frog | turtle | penguin | snail` (fur colour `colors.skin`: natural tones or theme
  tokens, different for each; a turtle's or a snail's shell `colors.hair`; it gets a `tail`, not a
  frog or a snail; a turtle walks slowly, a snail more slowly still, a penguin waddles, a frog jumps higher). A robot: `species: robot` with `robot:
  {head: box | round, face: eyes | screen, antenna: true | false, moves_on: legs | wheels}` (no
  hair; plating `colors.skin`; a screen face shows its mouth shapes; on wheels it rolls; a
  `[beep]` in its lines). Costume pieces for anyone: `crown`, `wizard_hat`, `party_hat` (one
  thing on top of the head, like `hat` or `cap`) and a `cape` that trails in the wind
  (`docs/CONFIG.md` "Robots and costumes"). `vidgen character-sheet` shows every pose and the front view. `vidgen cast --random 4
  [--seed S] [--species cat dog]` writes a cast chosen to differ (looks, colours, voice kinds
  and voices, original names) for `include:`; lint `look_alike` warns when two look too alike.
- Give each a want and a temper (the eager one, the doubter); their starting `pose` and
  `expression` say it before they speak. Short names, easy to say (the voice says them).
- One voice each (`voices:` + `characters[].voice`), clearly different; keep the narrator's
  voice for the few lines that set the scene.

**Staging.**
- **Marks**: two characters on `left` and `right` face each other (`facing: auto` turns them
  towards the stage's middle; on a wide stage, or with both on one side, set `facing`). A third
  goes at `centre` or further back. Keep characters at least a mark apart and the space above
  their heads free for speech bubbles.
- **Depth**: what matters stands in front (`depth: 0`); the set goes back (`depth: 0.5`–`0.8`:
  higher, smaller, behind; the `ground_color` band reaches up to the deepest of them). Nothing in
  front of a speaker's face (`hidden_speaker`). A character can walk in depth (`- {walk_to: kit,
  to: {mark: 0.6, depth: 0.7}}`: it shrinks and passes behind what it walks by) and come forward
  to speak (`depth: 0`). `facing: front` (or `- {turn: kit, to: front}`) turns a generated
  character to the viewer, for a line said to the audience; it turns back with `turn`.
- **The set**: things at the edges (a `house`, a `tree`), the middle free for the action.
  Props stay inside the frame: `far_left` / `far_right` cut a wide prop (`off_frame`). A
  drawn set is a gradient `background`, a `ground_color`, `layers` (`hills`) and props; a
  generated one (`generate:`) gets one top-level `cartoon_style` ("flat colours, thick outlines,
  soft shadows") so all stages match, and a prompt that describes a set, not a scene: things at
  the edges, an empty middle, the ground across the lower part, `negative: "people, animals,
  text"` (`docs/CONFIG.md` "Generated backgrounds").
- **Drawing style**: one top-level `drawing: {outline: thin | bold, shading: soft, texture:
  paper | storybook}` restyles every stage (a stage's own `drawing` wins key by key); the
  default draws as before; captions and overlays are never textured.
- **Room to move**: a walk takes the time its distance needs (about 4 s from `left` to `right`
  in 16:9), so give it a beat that long and end it on a free mark (`walk_overlap`). On a stage wider than
  the frame (`width: 2`), the camera goes along with `follow`.
- **Light and mood**: `light: morning | sunset | night | indoor` (or `{tint, strength}`) grades
  the whole set and the characters, never the bubbles or text; `night` adds stars on a colour
  background. Time passing is a `- light: night` action (it fades, 2 s). Characters and props on
  the ground get soft shadows on their own (`shadows: false` for none). `wind: breeze | windy |
  gale` (or 0..1; negative blows left) sways trees and bushes, makes scarves, long hair, ears and
  hats trail and particles drift; `- wind: gale` fades it in a beat. From `windy` on it shows
  clearly; add `particles: [leaves, streaks]` so it reads at once. `- blow_away: napkin` blows a
  light prop off the stage (or `to:` a mark), out of a hand too; the wind must blow then.
- **Rain**: `particles: [rain]` (or `- particles: rain` from a beat) on a stage ends on the
  ground with small splashes; an open umbrella (held or standing) and a tree's crown keep the
  rain off whoever stands under them; `{kind: rain, puddles: true}` grows puddles. A generated
  rain sound plays under it while it lasts, ducked less than music (off with `foley: false`).
- **Snow and fog**: `{kind: snow, settle: true}` lands on the ground and on the props, where a
  white layer grows (a blanket on the ground, caps on roofs, crowns, tables; full after 24 s at
  density 1; thin under trees and open umbrellas); `settled: 30` starts it already white. `fog:
  true` (or a density 0..1) lays fog in bands between the characters and props by depth: the
  further back, the more hidden; it drifts slowly and with the wind. Both outdoors only.
- **Storms, rainbows, sunsets**: `- lightning: right` flashes the set with a bolt there and plays
  `thunder` after it (`distance: 2` km: ~6 s later, quieter; in a room the windows flash); rain
  with `lightning: true` strikes every 8 s or so on its own. `- rainbow: centre` fades a rainbow in
  behind the hills (after the rain). With a `sun` (or `moon`) prop, `{light: sunset, move_sun:
  true, run_time: 4}` sinks the sun to the right while the light fades, the shadows stretching
  away from it; `night` sets it and raises the moon.
- **Indoors**: `room: {wallpaper: stripes, windows: [0.3], doors: [{at: 0.8}]}` (or `room:
  true`) replaces the sky and ground with a wall, a floor (`flooring: boards | tiles`) and a
  skirting board; windows show the sky of the stage's `light` (`indoor`: lamplight inside, evening
  outside; `- light: night` darkens it and brings out stars), doors are `door` props whose name is
  a mark: `- {enter: kit, door: door}` brings a character in through it, `exit` with `door:`
  takes it out. No wind, rain or snow inside; a set (`sets:`) can be a room. Furniture props:
  `sofa`, `armchair`, `bed`, `bookshelf`, `counter`, `fridge`, `picture`, `rug`, `houseplant`,
  `clock`, `tv`, `desk`; `{prop: sofa, at: 0.3, against: wall}` stands it at the wall's depth
  (`picture` and `clock` hang on the wall by themselves). Characters that sit on such furniture
  stand at the wall's depth too (`depth: 0.4`, or walk there: `- {walk_to: dot, to: {mark: 0.42,
  depth: 0.4}}`; `vidgen validate` says where); a sofa or a bed seats two.
- **Props that move by themselves**: `{prop: clock, time: "21:45"}` runs (`speed: 60` = a minute
  a second); `{prop: tv, on: true}` shows a flickering picture, `{prop: lamp, on: true}` glows;
  `- switch_on: lamp` / `- switch_off: tv` switch them in a beat (with a click). A lamp at
  `light: night` makes a warm spot, it does not light the whole room. A `fireplace` (furniture,
  `against: wall`) burns with flickering flames, a warm glow and a crackle while `on`; a `kettle`
  (on a `counter` with a `lift`) steams while `on`.
- **Nature that moves**: `{prop: tree, fruit: true}` carries fruits and `- drop_fruit: tree` (`to:
  pip` for a head, stars) lets one fall; `birds: true` (or `- birds: 4`) sends a flock across the
  sky (outdoors only).
- **Small props**: `cake`, `muffin`, `book`, `phone`, `letter`, `gift`, `balloons`, `vase`,
  `watering_can` to hold, give and set on a table (`lift: 0.17` on a `table`). A book, a letter
  and a gift `open` / `close` like an umbrella (held in front, not overhead). A `phone` that is on
  rings (`on: true` or `- switch_on: phone`; it shakes in bursts with a trill, `- switch_off:
  phone` answers it). Held balloons rise behind the head; `- let_go: pip` floats them away for
  good. `- pour: kit` tilts the watering can kit holds and water drops fall.
- **Ready-made sets**: `set: city_street`, `park`, `beach`, `forest` or `snowy_hills` on a stage
  scene gives a whole outdoor set without `sets:` (backdrop, props, light, ambience: a street
  sounds like a city, a park and a forest have birdsong by day). Put two characters on its
  `stand_left` and `stand_right` marks (clear of the props; other marks: `bench`, `bus_stop`,
  `fountain`, `umbrella`, `log`...); the scene's params override it like any set (`light:
  sunset`, `props: [{name: shop_2, color: tertiary}]`, `props: []`). Their props work on any
  stage: `shop`, `bench` and `log` (sit two), `bus_stop`, `fountain`, `flowers`, `fence`,
  `beach_umbrella`, `shell`, `pine`, `mushroom`, and flat `road` / `path` bands.
- **Ready-made rooms**: `set: classroom`, `kitchen`, `shop`, `living_room` or `bedroom` gives a
  furnished room (a door, windows, daylight or lamplight, a room tone) with the same `stand_left` /
  `stand_right` marks. Furniture stands at the wall (depth 0.4): to sit or lean, walk there first
  (`- walk_to: pip, to: {mark: sofa, depth: 0.4}`, then `- sit_on: pip, to: sofa`); pupils' desks
  are at depth 0.25 (marks `pupil`, `pupil_2`), the kitchen table and chairs at 0.2. `light: day`
  for a daytime room. New props: `blackboard` (hangs on the wall), `school_desk` (with its chair:
  sit at it), `shelf_with_goods` and `wardrobe` (lean on them), `till` (`lift` it onto a counter).

**Shot variety.** Change the shot every few beats, as a comic changes panels. A beat's `shot:`
key cuts the camera to a framing of the characters for that beat; the next beat without one cuts
back (`shot: {kind: closeup, of: kit, move: true}` eases instead):
- **wide** (the whole stage, no `shot` or `shot: wide`): the first beat of a scene, entrances,
  anything two characters do together;
- **`two_shot`** (two characters, whole) and **`over_shoulder kit pip`** (kit seen past pip, who
  stands cut at the edge): a dialogue, alternating the speaker's over-the-shoulder shots;
- **`medium kit`** / **`closeup kit`** (hips up / head and shoulders): the punchline or the
  reaction to it; about one close-up per scene, or close-ups stop meaning anything. A `zoom`
  (`scale: 2`) pushes in and comes back within the beat instead of cutting;
- **moving**: `pan` to a character or a mark (`- {action: pan, to: right}`) and `follow` a
  character or a flying prop across a wide stage (either ends a shot).
A shot is framed where the characters stand as the beat starts and does not follow a walk.
In a 9:16 variant the camera follows the speaker across the landscape stage on its own
(`reframe`, see the `social` topic): write the dialogue for 16:9 and check `vidgen storyboard
--variant ...`.

**Reaction shots.** The listener's face is often the joke. While one character speaks, the other
`react`s (`expression` and / or `pose`, for that beat only) and `look_at`s the speaker; `emote` and
`pose` change them for good. A `shot: closeup` of the listener while the other talks is the
reaction shot. `look_at: camera` turns a character to the viewer for an aside. Put the reaction where it
happens: `at: 0.8` lands it on the end of the line, not on its first word.

**Expressions.** `neutral`, `happy`, `sad`, `angry`, `surprised`, `worried`, `thinking`, and the
big ones: `laughing` (shoulders bouncing; it keeps laughing while it talks), `blushing`,
`tongue_out`, `crying` (streams of tears, sobbing), `dizzy` (swirling eyes, swaying) and
`frightened` (wide eyes, hair, fur or feathers standing up, shivering; a robot's antenna springs
up). They work on people, animals and robots, side and front. `[laugh]` / `[giggle]` in a line
make the speaker laugh. Save the big ones for the moments that earn them.

**Effect symbols.** `- {effect: pip, to: idea}` pops a small symbol over a head for the beat: an
`idea` bulb, a `question` or `exclaim` mark, a `sweat` drop, an `anger` mark, `sleep` Zs, `hearts`,
dizzy `stars`, a `sparkle`, a `tear`. It follows the character, sounds with foley (`sound: false`
for none) and goes at the next beat (`until:` keeps it longer). Use one per line at most, on the
moment the feeling lands (`at`); it says "she has an idea" without a word.

**Title cards and irises.** A `card` scene is the cartoon's title card: the episode's name, a
"Later that day…" between two scenes, "The End" (`style: burst`, `frame` or `plain`; `sting:
reveal`, `comic` or `sad` as the text pops in). The classic way between them is an iris: a black
circle closes on the scene before and opens on the next. `transition: {type: iris_out,
character: pip}` closes on Pip's head (a pause on the face, then black); `{type: iris_in,
character: kit}` opens on Kit in the scene it leads into; `at: [x, y]` (fractions of the frame
from the top left) for a point, `color` for another colour. The other side opens or closes on
the frame's centre. `iris_in` on the first scene opens the video.

```yaml
characters: [{name: pip, look: {body: bean}}, {name: kit, look: {body: tall}}]
scenes:
  - id: yard
    type: stage
    params: {characters: [{name: pip, at: left}]}
    beats: [{text: "And that was the last Pip saw of the kite."}]
  - id: later
    type: card
    params: {text: "Later that day…"}
    duration: 2.5
    transition: {type: iris_out, character: pip}
  - id: hill
    type: stage
    params: {characters: [{name: kit, at: right}]}
    transition: {type: iris_in, character: kit}
    beats: [{text: "Up on the hill, Kit found something."}]
```

**Automatic directing.** `auto_direct: true` (top level, a stage's param or a beat's key) adds
the routine looks and reactions for you: listeners `look_at` whoever speaks, the speaker looks at
the one it answers, and after a line with `?`, a negation or `!` the listeners `react` in the
pause (`thinking`, `worried`, `surprised`...). The speaker gestures on the line's stressed word
(mark it `*word*`: the asterisks are not spoken or shown; or write it in CAPITALS; else the
longest word counts; at most one per line), and a short punchy line
right after a long one gets a close-up on its speaker (a short push-in, or a `shot: closeup` when
the line is too short for it). A strong change of face gets its symbol (surprised an
exclamation mark, thinking a question mark, angry an anger mark, dizzy stars, frightened a sweat
drop; one per line). Nothing it adds may cause an `off_stage`
or `facing_away` lint warning (it checks the stage's layout first). Actions you write win: a
character with its own action in a beat gets nothing automatic there. So turn it on, then write only the moments that
matter (the reaction shot, the punchline's look to camera). `vidgen direct` lists what it adds,
`vidgen direct --print` writes it as YAML to paste into the beats and edit; the storyboard shows
an `auto:` line under each beat.

**From a screenplay.** When the story comes as a script, write it as a screenplay and let
`vidgen screenplay story.md --out DIR` (MCP tool `screenplay`) make the project: one `stage`
scene per `# Scene:` heading, one beat per line, a generated look and a voice for each character
not declared in the front matter, `auto_direct: true`. Then refine the YAML as usual (check the
`# TODO:` lines: directions and manners it could not map). `# Card: Later that day…` makes a
title card (silent unless lines follow), coming in with an `iris_out`; the scene after it opens
with an `iris_in`.

```markdown
---
title: The Humming Box            # optional: video.yaml keys (voice, theme, characters...)
---
# Scene: yard
set: background: day; props: box (crate) at 0.6, tree at 0.84; characters: fen at left, bram at right

On a quiet Sunday, Fen heard a sound that did not belong in the yard.

FEN (surprised): Bram, listen! That box is humming a song.

[Fen walks to the crate and points at it.]

BRAM: Boxes do not hum, Fen. Boxes do not do *anything*.
```

Indoors: `set: room: stripes, window at 0.3, door at right; props: sofa against the wall at 0.4,
picture frame on the wall, rug at 0.5`. `NAME (manner):` turns an expression or pose word (`doubtful`, `glad`, `arms crossed`) into a
`react` and a feeling word (`cross`, `whispering`, `sleepy`) into the beat's `emotion` (how the
voice says it), and a pronoun there states the voice kind (`FEN (she):`, `BRAM (he, doubtful):`,
`GUS (they):`; once per character is enough): the generated look and voice then suit it (without
one, the voice follows the look's kind); a plain paragraph is the narrator; `[...]` maps walk / run to, enter, exit, jump, look
at, point at, wave, nod, shrug and shake head, and effect symbols (`[Pip has an idea]`, `is
confused`, `falls asleep`, `cries`...) (on its own line: at the next line's start; inside a
line: at that word), except a voice sound such as `[laugh]` inside a line, which stays in the
line. Undeclared characters get looks that differ from the others (`--species cat dog` for
animals, `--seed` for other random ones). `docs/CONFIG.md` "Cartoons from a screenplay" has the
whole format.

**A series: one cast, shared sets.** Put the characters and their voices in `shared/cast.yaml`
and the places in `shared/sets.yaml` (`sets: {meadow: {background, props, marks, light...}}`);
each episode writes `include: [../shared/cast.yaml, ../shared/sets.yaml]` and a stage scene
`set: meadow` with only what differs in its `params` (`light: sunset`, its characters). The
scene's own params win; props, layers and characters add to the set's (`{name: tree, at: 0.3}`
moves the set's tree); an episode's `characters:` entry of a cast name changes that character
for the episode. `vidgen validate` names the file a problem is in; `vidgen screenplay story.md
--cast shared/cast.yaml` writes an episode that includes the cast and turns `set: meadow` lines
into the set. `examples/cartoon_series/` shows it (CONFIG "Shared casts and sets").

**Comic timing.**
- **Short lines**: one line per beat, one speaker per beat (the beat's `voice`), 6–12 words.
  Kokoro needs about 8 words to sound natural, and a two-word beat with actions trips
  `rushed_animation`. It also reads fast (3.5–4.5 words a second): `speed: 0.8`–`0.85` on each
  voice gives the lines room (`narration_speed` warns above 3.5 once the audio is real).
- **Pauses**: every beat ends with `narration.pad` seconds of silence (0.35). Raise it for a
  cartoon (`narration: {pad: 0.7}`) and put the reaction in it (`at: 0.8`): line, pause,
  reaction. Commas and "..." are pauses in the voice (not in the word-count preview).
- **Setup, pause, punchline**: the punchline is its own beat, after the reaction to the setup.
  The narrator undercutting a character ("Moss was not, in fact, an expert") is a cheap, good
  laugh.
- **One thing at a time**: a move, then a line; at most one or two actions per character per
  beat. Speech bubbles only for short lines (`bubble: "Up there!"`).
- **Motion**: anticipation, squash and stretch, overshoot and follow-through are built in;
  `cartoon_motion: calm` (top level, a stage or a character) tones them down for a quiet story.
  Motion effects come with them: dust where a `run_to` (or a fast walk) sets off and stops and
  where a jump lands, speed lines behind runs and thrown or blown props, stars on a high jump's
  landing, a whoosh arc on a `gesture` with `big: true`; `motion_effects: false` (top level or a
  stage) turns them off. For a move no action has, `keyframes` and `move_along` move a character, a prop or one part
  (`kit.arm_left`); `docs/CONFIG.md` "Keyframes and motion paths". Generated characters bend
  at the elbows and knees: `arm_left` is the upper arm, `arm_left_lower` the forearm (its angle
  is the elbow's bend), the legs are `leg_left` / `leg_right` (+ `_lower`); own poses can bend
  them too (`docs/CONFIG.md` "Bending arms and legs").
- **Props in hands**: `walk_to` next to a prop, `pick_up` it, walk with it, then `put_down`,
  `give` (to a character standing next to it) or `throw` it; `hold` puts a prop in a hand at
  the start. `vidgen validate` replays the scene and says when a prop is too far, held by
  someone else or not held (`docs/CONFIG.md` "Props in hands"). A character crouches by
  itself for a prop on the ground. For a picnic or the weather: `basket`, `napkin` and
  `umbrella` props; `- open: umbrella` raises a held umbrella overhead, `- close: umbrella`.
- **Sitting and leaning**: `sit_on: pip, to: chair` (a `chair`, `rock`, `box`, `sofa`,
  `armchair`, `bed`, `desk`, or an SVG prop with `data-seat`), `lean_on: kit, to: tree` (a `tree`,
  `door`, `sign`, `lamp`, `house`, `bookshelf`, `counter`, `fridge`, or an SVG prop with
  `data-lean`), then `stand_up` before it walks, jumps or turns again. While it sits
  or leans it can talk, gesture, emote and handle props; a look turns only its head. `vidgen
  validate` says when the prop is too far, the seat taken, or a seated character walks
  (`docs/CONFIG.md` "Sitting and leaning").
- **Vehicles**: props `bicycle`, `car`, `bus`. `get_in: [pip, kit], to: car` (each must stand
  beside it), `ride_to: car, to: right` (or `{mark, depth}`; the riders go along, a cyclist
  pedals), `get_out: [pip, kit]`; no walking while riding. They are big next to the characters
  (a bus is 3.2 characters long): give it a `scale` or the stage a smaller `size`
  (`docs/CONFIG.md` "Vehicles"). Outdoors only: a `boat` floats on the stage's `water: true` (or
  `{left, right}`) and rides along it, bobbing; a `hot_air_balloon` (2 stand in its basket; 2.1
  characters tall, so use `size: 0.3`) rises, drifts with the wind and lands at `to`; a
  `toy_rocket` (nobody rides it) launches with smoke and floats down under a parachute to `to`.
  `land: false` flies a balloon or a rocket out of the top of the frame, gone for the scene.
- **Sound**: walks, entrances, exits, jumps, a `surprised` face and most effect symbols make their own sounds
  (foley: footsteps, whoosh, boing, pop, an idea's ding; a thrown prop lands with a thud; a ride rings a bell or starts an engine and brakes, a balloon's burner roars, a toy rocket fizzes off; a door creaks as it opens or closes; water splashes; on a platform `level` a jump lands softly, each coin goes `coin` and each star `twinkle`, a key `unlock`s a locked door, a blocker shuffles aside), timed to the action,
  and rain plays a rain sound bed. Each stage also plays a quiet bed of its set: birdsong
  outdoors by day (not at night, not in rain), a room tone in a room; `ambience: city` on a stage
  names the street sounds instead (or `birdsong`, `room_tone`, a list), `ambience: false` none.
  `foley: false` (top level or a stage) turns all of them off. A beat's `sting: reveal | comic | sad` adds a short music sting
  (`reveal` as the beat starts, `comic` and `sad` in the pause after the line), ducked under the
  voice; under composed music the music's own instruments play it, in its key. One or two per
  cartoon, on the real punchline, or they stop being funny. For music that follows the story
  (a mood per scene, a pause before the punchline) see *Composed music* in `vidgen guide audio`.
- **Voice sounds**: `[gasp]`, `[hmm]`, `[laugh]`, `[sigh]`, `[giggle]`, `[groan]`, `[beep]` in a line
  (`text: "[gasp] The box is open! [laugh]"`) are made by the voice at that point (`Ha ha ha!`,
  `Hmm.`; a gasp or sigh at the line's start or end is a generated breath, a beep a generated
  robot chirp) and never shown in
  captions; the speaker's mouth follows and its face changes (laugh happy, gasp surprised, sigh
  sad) unless the beat's own `emote` / `react` sets it. A line needs words besides its sounds
  (`docs/CONFIG.md` "Voice sounds").
- **Talking at once**: `overlap: 0.4` on a beat starts it 0.4 s before the line before it ends
  (both heard, both mouths move, captions show both lines); `interrupt: true` cuts that line off
  where the beat starts (inside its last word, or `overlap` seconds before its end). Not on a
  scene's first beat, and not on a line of the same voice. Keep overlaps short: `vidgen lint`
  (`talked_over`) warns when whole words of the earlier line are lost under the new one or cut by
  an interrupt (`docs/CONFIG.md` "Overlapping lines").

**The loop for a cartoon.**
1. `vidgen character-sheet NAME` (or `--all`): every pose, expression and mouth shape on one PNG.
   Fix looks that are hard to tell apart now, before writing scenes.
2. `vidgen validate --json`: unknown marks, poses and expressions, a `say` by a character
   without a voice, and warnings for actions a character lacks the parts for (an SVG without
   arms cannot `wave`).
3. `vidgen storyboard --scene ID`: each still is a comic panel. The ½ stills are half-way
   through a walk, gesture, jump or path. Ask: is it clear who speaks? Are both faces visible,
   facing each other? Does the reaction read without the words? Is anything cut by the edge?
4. `vidgen lint --json`: the cartoon rules `off_stage`, `character_overlap`, `walk_overlap`,
   `prop_overlap`, `bubble_overlap`, `facing_away`, `hidden_speaker`, `small_speaker` (a face too small to read: a
   `shot: closeup` or `character_size: large`), `mouth_without_voice` and `look_alike` (fixes in
   `vidgen guide troubleshooting`).
5. Voices: with Kokoro (`vidgen guide audio`) `vidgen tts` is free and writes the lip sync
   tracks; then storyboard and lint again, since real lines change the timing.

```yaml
voice: {provider: kokoro, voice: bf_emma, speed: 0.8}   # the narrator, slowed down
voices:
  dot_voice: {voice: af_bella, speed: 0.85, label: Dot}
  moss_voice: {voice: am_michael, speed: 0.85, label: Moss}
narration: {pad: 0.7}                              # room for reactions after each line
characters:
  - {name: dot, voice: dot_voice, look: {body: round, hair: bun, accessories: [scarf]}}
  - {name: moss, voice: moss_voice, look: {body: tall, eyes: sleepy, accessories: [hat, glasses]}}
scenes:
  - id: yard
    type: stage
    params:
      background: ["#9CCBEA", "#E4F3FB"]
      ground_color: tertiary
      props: [{prop: house, at: 0.17, depth: 0.7}, {prop: box, name: kite, at: 0.43}]
      characters:
        - {name: dot, at: left}
        - {name: moss, at: right, pose: arms_crossed}
    beats:
      - text: "On the windiest day of the year, Dot had a plan."
      - text: "Moss, look! I built a kite that flies by itself."
        voice: dot_voice
        actions:
          - {jump: dot, at: 0.1}
          - {look_at: moss, to: kite, at: 0.5}
      - text: "Dot, that is a cardboard box with a string on it."
        voice: moss_voice
        actions:
          - {look_at: moss, to: dot}
          - {react: dot, expression: worried, at: 0.8}   # in the pause after the line
      - text: "Moss was not, in fact, an expert on boxes."
        sting: comic                                     # ba-dum-tss after the line
        actions:                                         # the narrator's aside: a close-up
          - {zoom: moss, scale: 2, at: 0.1}
          - {look_at: moss, to: camera, at: 0.4}
```

A complete two-scene cartoon (under a minute, a wide stage, `follow` on a flying prop, a close-up
punchline) is `examples/cartoon/` in the schu-video-generator repository.

**A host for an explainer.** `host: NAME` (a character of `characters:`) puts that character
beside the content of every scene: bullets, charts, code, diagrams... Each scene lays its content
out in the room left (a column beside it; in 9:16 a band below it), so nothing needs moving by
hand. Its mouth follows the narration (`speaks: narrator`, the default; `own`: only beats in its
own voice), it blinks and breathes, and a scene can change it (`host: {expression: thinking}`) or
drop it (`host: false`; a title or end card often looks better without). `stage` and `card`
scenes never show it. Keep the host small next to dense content (`size: 0.4`), and check the
storyboard: lint's `host_overlap` reports anything drawn over it.

```yaml
characters: [{name: dot, look: {body: bean, hair: bun, accessories: [glasses]}}]
host: {character: dot, side: right}        # size, place (beside / below), floor, facing, pose, expression
scenes:
  - id: steps
    type: bullets
    params: {heading: "How it works", items: ["Write the beats", "Render a preview"]}
    beats: [{text: "First, you write the narration as short beats."}]
  - id: chart
    type: bar_chart
    host: {expression: happy}
    params: {title: "Render minutes", labels: ["480p", "1080p"], values: [0.4, 2.6]}
    beats: [{text: "Previews are the fast way to iterate."}]
```

**Make the host act.** Beat actions: `host_point: item2` (its arm reaches towards a target of
the scene and it looks there; `line: true` adds a thin pointer line, best when nothing lies
between the host and the target), `host_look: bar3`, `host_react: happy` (`effect: sparkle` adds
a symbol), `host_move: other_side` (it walks across and the content slides to the other side
with it; one move per beat), `host_enter` / `host_exit` (a scene whose first passage is
`host_enter` starts without it). With `auto_direct: true` (or the host's own `auto_direct`) the
host points at each new bullet, bar, series or code highlight, looks at written highlights, and
reacts to results (a chart going up: happy; down: worried; an error in the code: surprised); it
never moves by itself, and anything you write in a beat wins. `vidgen direct` lists what it adds.
A complete example is `examples/host-explainer/`.

```yaml
auto_direct: true
characters: [{name: mo, look: {species: mouse, outfit: apron}}]
host: mo
scenes:
  - id: hello
    type: title
    params: {title: "Why Bread Rises"}
    beats: [{text: "Hi, I'm Mo!", actions: [{action: host_enter}]}]
  - id: bake
    type: process
    params: {stages: ["Mix", "Rise", "Bake"], layout: column}
    beats:
      - text: "Mix it, and let it rise."
      - text: "Then into the oven."
        actions: [{host_point: stage3, line: true, at: 0.5}]
```

<!-- topic: platform (also: level, levels, platformer, jumping, story-props) -->
## Platform stories: levels, jumps and story props

**When to make one.** A children's adventure where the hero *goes somewhere*: skips along the
grass, climbs a ladder, hops over a gap and up onto the clouds, finds a key for a locked gate,
meets someone grumpy in the way and asks nicely. It is a `stage` scene with a `level:` (a side
view drawn from a small map), so everything of `vidgen guide cartoons` still works: lip sync,
expressions, shots, the camera, sets, light, music. Keep a level to one part of the journey
(30–60 s, 8–12 beats) and use a few scenes for a 2–3 minute story.

**The map.** One line per row, top row first: `.` air, `#` ground, `=` a floating plank, `~` a
cloud (stand on it, jump up through it), `|` a ladder, `$` a coin and `*` a star (picked up when
the hero touches them, in the air too), and a **letter** for a *spot*: a place to stand, on the
first tile below the letter. Name the spots (`spots: {a: start, k: key_spot}`) and send every
move to a spot: it reads better than numbers and survives map edits. A character is two tiles
tall: leave two rows of air under a plank to walk under it.

**Moves.** `walk_to` / `run_to` go along the tiles (steps of one tile, ladders on the way,
never across a gap); `jump` with `to:` plans the arc itself (a crouch, the flight, a squash and a
little wobble on landing), at most 5 tiles across, 3 up and 8 down. `vidgen validate` replays
every move and says why one fails and what to write (`'nutmeg' cannot walk to spot 'far_side':
the way stops at map column 22: a gap at column 23; jump there instead`). A walk goes about 1.4
tiles a second (a ladder rung counts double): give each move a beat whose line lasts as long, or
`vidgen lint` warns `rushed_animation`; split a long way over two beats, or `run_to`.

**Story props.** A `door` prop is in the way until it opens; `locks: {gate: garden_key}` locks it
until the holder of the key prop stands next to it (`- open: gate, by: nutmeg`). `blockers:
[mossby]` puts a character in the way until `- step_aside: mossby` (after the line that asks it
nicely). `react: {when: pickup | land | arrive, expression, effect}` on a move puts the joy or
the surprise on the right frame. The sounds come by themselves (a boing, a soft landing, a coin's
pling, a star's twinkle, the unlock and the creak, the shuffle aside).

**Camera and size.** `level: {follow: nutmeg}` keeps the camera on the hero, gently, up and down
too. `character_size: small | medium | large` (top level or per scene) sets how big everyone is:
`medium` shows about 14 x 8 tiles in 16:9; use `large` for a 9:16 Short (a variant), whose
narrow frame shows about 6 x 10. A map must be at least as wide as the frame. For a dialogue,
cut to `shot: closeup <name>` or `two_shot`: small level characters' faces are hard to read
(`small_speaker` warns).

```yaml
characters:
  - {name: nutmeg, look: {species: mouse, proportions: kid, outfit: overalls}}
  - {name: mossby, look: {species: snail, eyes: oval}}
scenes:
  - id: garden
    type: stage
    set: park                       # its sky, hills, light and birdsong; not its props
    params:
      props:
        - {prop: door, name: gate, at: gate_spot}
        - {prop: key, name: garden_key, at: start}
      level:
        map: |
          ..............................
          ...................*..........
          ..a..gd..s..m...b....l...$$.e.
          #################....#########
        spots: {a: start, g: near_gate, d: gate_spot, s: stop, m: path, b: brink, l: over, e: end}
        locks: {gate: garden_key}
        blockers: [mossby]
        follow: nutmeg
      characters: [{name: nutmeg, at: start}, {name: mossby, at: path, facing: left, expression: angry}]
    beats:
      - text: "Nutmeg carried the golden key to the garden gate."
        actions: [{hold: nutmeg, to: garden_key, at: 0}, {walk_to: nutmeg, to: near_gate, at: 0.3}]
      - text: "Click, went the key. And creak, went the little gate."
        actions: [{open: gate, by: nutmeg, at: 0.2}]
      - text: "But Mister Mossby, the grumpiest snail in the garden, sat on the path."
        actions: [{walk_to: nutmeg, to: stop, at: 0.1}, {react: nutmeg, expression: surprised, at: 0.8}]
      - text: "Please, Mister Mossby, may I pass?"
        shot: closeup nutmeg
      - text: "Well, since you asked so nicely, he smiled, and shuffled aside."
        actions: [{emote: mossby, to: happy, at: 0.2}, {step_aside: mossby, at: 0.5}]
      - text: "Nutmeg ran to the edge, then jumped, and caught a star in the air!"
        actions:
          - {run_to: nutmeg, to: brink, at: 0.05}
          - {jump: nutmeg, to: over, at: 0.5, react: {when: land, expression: laughing, effect: sparkle}}
```

**From a screenplay**: put the level in a set of the front matter (`sets: {meadow: {level:
{map: ..., spots: ...}}}`) and start the scene's `set:` line with it (`set: meadow; characters:
nutmeg at start`); spots are marks there, and `[Nutmeg jumps onto over.]` is a jump.

A whole story: `examples/platform-story` (three levels, a key and a gate, coins and stars, a
grumpy snail, clouds up to a picnic, a 9:16 variant). Every key: `docs/CONFIG.md` "Platform levels
(`level`)" and the sections after it.

<!-- topic: overlays (also: transitions, transition, carry, continuity, captions) -->
## Overlays, transitions and continuity

**Overlays** draw on top of every scene and stay fixed through camera moves:

```yaml
overlays:
  - {type: progress_bar, exclude: [intro]}
  - {type: chapter_indicator, total: true, reserve: true}
  - {type: lower_third, scene: intro, at: 1.0, name: "Ada Lovelace", title: "Mathematician"}
  - {type: watermark, icon: brain-circuit, corner: bottom_right, opacity: 0.4}
scenes:
  - id: intro
    type: title
    params: {title: "Engines that think"}
    beats: [{text: "Ada Lovelace saw it first: machines could do more than count."}]
  - id: part1
    type: chapter
    params: {number: 1, title: "The engine"}
    duration: 2.5
  - id: body
    type: text_card
    params: {text: "Cards in, numbers out"}
    beats: [{text: "The engine read its program from punched cards."}]
```

- `progress_bar` and `chapter_indicator` for videos over 2 minutes with chapters.
- `lower_third` once, when a person or place first appears (5 s).
- `watermark` small and faint, or not at all.
- `captions` for social and muted viewing (`vidgen guide social`).
Lint's `overlay_overlap` reports an overlay over scene text: give it `reserve: true` or move it.

**Transitions** (`transition:` per scene = the way into it, or video-wide). Default: cuts (every
scene fades out by itself), which is right most of the time. `crossfade` (0.5 s) for a calm
flow, `fade_color` into `chapter` cards to mark a new section, `push` / `wipe` sparingly (one
style per video), `iris_out` / `iris_in` in cartoons (`vidgen guide cartoons`). Transitions
never cover narration.

```yaml
transition: crossfade
scenes:
  - id: intro
    type: title
    params: {title: "Results"}
    beats: [{text: "Here is what we found."}]
  - id: part2
    type: chapter
    params: {number: 2, title: "Results", icon: chart-column}
    transition: {type: fade_color, color: surface}
    duration: 2.5
  - id: big
    type: stat
    transition: cut
    carry: [icon]
    params: {value: 3.2, suffix: "x", label: "faster", icon: chart-column}
    beats: [{text: "Everything got three times faster."}]
```

**Continuity** (`carry:`): a match cut that moves an element of the scene before into this
scene (the chapter's icon into the stat's icon, `"title -> heading"`). Use it with a `cut`,
once or twice per video, where the two scenes are about the same thing.

<!-- topic: audio (also: sound, sfx, music, voice, voices, pronunciation, readback) -->
## Sound: voices, pronunciation, effects and music

**Voice.** One narrator (`voice: {voice_id: ...}`) for explainers. `voices:` plus a scene's or
beat's `voice:` for interviews and dialogue; label speakers (`label`) so subtitles and captions
can name them (`subtitles: {speakers: name}`).

**Choosing a voice provider.** ElevenLabs, the default provider (key `ELEVENLABS_API_KEY`), sounds the most
natural, sends the neighbouring beats for smooth intonation and can time every word exactly
(`timestamps: true`, for karaoke captions); it bills characters against a monthly plan. `voice:
{provider: openrouter, model: author/name, voice: ...}` (`OPENROUTER_API_KEY`) reaches many TTS
models with one pay-as-you-go key, most of them far cheaper per character (e.g.
`hexgrad/kokoro-82m`, `mistralai/voxtral-mini-tts-2603`), but with no context between beats, no
word timings (captions use estimates) and no `language_code`: the language follows the text and
the voice. Read `vidgen tts --dry-run`: it names provider, model and voice, prints the price per
character and the estimated cost (or why it is unknown) and `note:` / `problem:` lines — fix them
before a real run. Then listen to one beat (`vidgen tts --beat ID`, `vidgen readback`) before
voicing the whole video. One provider per video: named `voices:` change `voice` / `instructions`
/ `speed`, not `provider`; try another provider in a variant (it gets its own `audio/<variant>/`).
If the account requires Zero Data Retention, pick a model with a ZDR endpoint (most TTS models
have one; vidgen's error lists them when a model is refused). A real run ends with what
OpenRouter charged, or `cost not reported by openrouter yet (...)` when its cost records lag:
the audio is stored all the same.

**A free local voice: Kokoro.** `voice: {provider: kokoro, voice: af_heart}` runs the open
Kokoro-82M model on the computer itself: no key, no account, nothing to pay, offline after a
one-time download (~330 MB from Hugging Face; `vidgen tts --dry-run` says when it is still to
come). It needs the optional extra (`pip install "schu-video-generator[kokoro]"`, Python
3.10-3.12); without it `vidgen tts` says what to install. This is the voice for your own
projects: re-voicing after every script change costs nothing, and over MCP a real `tts` run needs
no `confirm_cost`. English is its strength (`af_heart` and `af_bella` are the best voices, then
`bf_emma` for British English; males: `am_michael`, `am_fenrir`, `bm_george`), and English beats
get exact word timings for karaoke captions for free. It also speaks Spanish, French, Hindi,
Italian, Brazilian Portuguese (`pf_dora`), Japanese and Mandarin, less well. `lang` follows the
voice's first letter (`p` for `pf_dora`) or the video's `language:`; `vidgen validate` warns about
an unknown voice or one of another language. Compared with ElevenLabs it is flatter and less
expressive, has no context between beats, and is weak on very short lines (give a beat at least
~8 words) — good for drafts, internal videos and your own experiments; suggest ElevenLabs when
the person wants the most natural narration. It runs at about real time on a laptop CPU (~0.7x on
a small cloud CPU): voice a long video once the script is settled.

Give Kokoro lines feeling with `emotion:` on a beat (or as a speaker's default on its voice):
`happy`, `excited`, `sad`, `angry`, `worried`, `scared`, `surprised`, `calm`, `doubtful`,
`sleepy`, `whisper`, `shout`, or a row with changes such as `{like: sad, pitch: -2}`, change the
speed, pitch, loudness and pauses of that line; use it on the lines of a dialogue that carry a feeling, not on every line.
`excited`, `happy`, `angry` and `shout` also speed a line up: with Kokoro keep the voice's `speed` near
0.75–0.8 (`af_heart` at 0.95 read 3.6–4.6 words a second), then check `narration_speed` with
`vidgen lint` on the real audio. A screenplay's `PIP (cross):` sets it for you. A weighted blend `voice: af_heart+af_bella:0.6`
makes an in-between voice. ElevenLabs and OpenRouter speak the same `emotion` by its name: an
audio tag such as `[excited]` before the line on `eleven_v3`, changed voice settings on other
ElevenLabs models, a sentence added to the `instructions` of OpenRouter models that take them
(other OpenRouter models: the audio's speed, pitch and loudness).

```yaml
voice: {provider: kokoro, voice: af_heart}       # speed: 1.0, lang: a, device: cpu (defaults)
voices:
  guest: {voice: am_michael, label: Guest}         # same provider; another voice
```

**Writing good `instructions`** (OpenRouter models that read them, e.g. Gemini TTS: the dry run
notes when a model ignores them). Describe the speaker and the delivery in a few words, not the
content: who (a warm, unhurried explainer; a curious guest), pace and pauses (slight pause before
numbers; slow down on definitions), energy (calm, never salesy), and the language or accent when
it matters (Brazilian Portuguese, neutral accent). Keep one `instructions` for the narrator so
every beat sounds alike; give each named voice its own. Never put directions into the beat text:
the model reads it aloud.

```yaml
voice:
  provider: openrouter
  model: google/gemini-3.8-flash-lite-tts
  voice: Kore
  instructions: "warm, unhurried explainer; slight pause before numbers"
voices:
  guest: {voice: Puck, instructions: "curious guest, a little faster, rising tone on questions", label: Guest}
```

**Pronunciation.** Write the text as it should be **read** on screen and in subtitles; fix
how it is **said** with `pronunciation:` (applied to the TTS text only). Run
`vidgen tts --dry-run` and read every `says:` line; after `vidgen tts`, `vidgen readback` finds
what the voice still gets wrong, and the words it says unclearly (`unclear`: probability below
0.5 or a pause over 0.5 s inside a sentence; `doubtful`: below 0.75). For an unclear name or
term, respell it in `pronunciation:`; for another word, try another voice, speed or `emotion:`.

```yaml
pronunciation:
  K-Phi-3: kay fye three
  SQL: {say: sequel, case_sensitive: false}
scenes:
  - id: intro
    type: title
    params: {title: "K-Phi-3 and SQL"}
    beats: [{text: "K-Phi-3 writes SQL for you."}]
```

**Sound effects** (`vidgen list-sfx` describes each in words): `whoosh` (something moves in),
`pop` (an item appears), `tick` (steps, counting), `click` (a UI click), `chime` (a key
insight), `success` / `error` (a result), `riser` (tension before a reveal, `align: end`),
`thud` (a big number lands), `swoosh`, `typing`; `footstep`, `boing`, `gasp`, `sigh`, `beep`, `bell`, `engine`, `brakes`, `burner`, `launch`, `phone`, `thunder`, `creak`, `knock`, `unlock`, `coin`, `twinkle`, `splash` and the music stings
`sting_reveal` / `sting_comic` / `sting_sad` are for cartoons (`vidgen guide cartoons`). Two or three per minute, on the moments that
matter; `sfx: {auto: true}` adds soft ones to built-in reveals if you want a uniform feel.

```yaml
sfx: {gain: -3}
scenes:
  - id: reveal
    type: stat
    params: {value: 9.8, unit: "min", label: "for one minute of 4K"}
    beats:
      - text: "One minute of four K took almost ten minutes."
        actions:
          - {sfx: thud, at: 0.2}
```

**Music** (`vidgen list-music`): `calm` (serious, long narration), `pulse` (tech, data,
walkthroughs), `bright` (launches, upbeat social), `cartoon` (playful pizzicato: cartoons,
comic scenes), `lullaby` (music box: bedtime stories, soft endings). It is ducked under the
voice automatically and the mix is normalised to −16 LUFS. Leave the defaults; turn it off over
clips with their own sound (`music: false` on the scene).

```yaml
music: {source: calm, volume: -2}
scenes:
  - id: intro
    type: text_card
    params: {text: "Listen"}
    beats: [{text: "A calm bed sits under the voice."}]
```

**Composed music** (`music: {compose: MOOD}`) is written as notes for this video and played with
real instruments: an original piece in a mood, the same piece for the same settings. Prefer it to
a bed when the music should follow the video. Moods for explainers: `calm` (piano and harp, no
drums: serious topics, long narration), `focused` (vibraphone, guitar, brushes: tech, data,
walkthroughs), `curious` (staccato flute, harp: science, "how does it work"), `upbeat` (marimba,
pop drums: launches, tutorials). For cartoons: `playful` (clarinet, marimba, tuba oom-pah),
`sleepy` (celesta lullaby in 3/4: night, bedtime, endings), `tense` (low clarinet, tremolo
strings, a heartbeat drum: storms, chases, suspense), `triumphant` (trumpet fanfare, march: the
win). `vidgen list-music` describes each mood and instrument in words.
- **It follows the video.** Without `bars` the piece is composed for the real timings when the
  video is joined: every scene starts on a bar line (tempo within 8 % of the mood's), the music
  swells a little when a bullet, chart bar or code step appears, and it ends on a held chord
  instead of fading mid-phrase. After a script change the next render composes it again.
- **A mood per scene.** `music: {mood: tense}` on a scene changes the music for that scene only
  (the next scene returns to the cue's mood); add `volume: -3` under rain or a busy scene. Use it
  where the story turns (calm → tense at the storm, sleepy at night), not on every scene.
- **Pauses before punchlines.** `music_pause: true` on a beat stops the music just before the
  line, until the next bar line after it; vidgen does this by itself before a `card` scene and
  before a short last line (≤ 8 words), whose closing chord then lands as the line ends.
  `music_pause: false` turns either off.
- **Stings** (`sting: reveal | comic | sad`) are played by the music's own instruments, in its key.
- **Without the extra.** Composed music needs `pip install "schu-video-generator[music]"`; the first
  render downloads the SoundFont (32 MB, once; `vidgen soundfont fetch` does it now). Without the
  extra `vidgen validate` warns and the mood's built-in bed plays instead (`calm` → calm,
  `focused` / `tense` → pulse, `curious` / `upbeat` / `triumphant` → bright, `playful` → cartoon,
  `sleepy` → lullaby), so the video still renders. `vidgen music preview --mood M` writes a piece
  as WAV and MIDI to listen to (MCP `music_preview`). Drafts and animatics play it too; storyboards
  have no sound.

```yaml
music: {compose: playful, volume: -2}
scenes:
  - id: storm
    type: stage
    music: {mood: tense, volume: -3}
    beats:
      - text: "Then the cloud did what clouds do."
      - text: "The umbrella left without him."
        music_pause: true
```

<!-- topic: examples (also: good-bad, before-after, patterns, antipatterns) -->
## Good vs bad: before and after

**1. A wall of text → a progressive grid.** Bad: six long items appear together while the voice
reads the first one; 40 words on screen.

```yaml
- id: features_bad
  type: bullets
  params:
    heading: "Key features of the platform you should know about"
    reveal: all
    items:
      - "Our compute layer scales automatically with your workload"
      - "Storage is replicated across three regions for durability"
      - "The network is software-defined and fully encrypted"
      - "Security follows a zero-trust model everywhere"
  beats:
    - text: "The platform has many features: compute that scales automatically, storage replicated across three regions, a software-defined encrypted network, and zero-trust security everywhere."
```

Good: one or two labels per beat, icons carry the category, the voice adds the detail.

```yaml
- id: features_good
  type: icon_grid
  params:
    heading: "What you get"
    icon_color: palette
    items:
      - {icon: cpu, label: "Compute", sublabel: "scales itself"}
      - {icon: database, label: "Storage", sublabel: "3 regions"}
      - {icon: network, label: "Network", sublabel: "encrypted"}
      - {icon: shield-check, label: "Security", sublabel: "zero trust"}
  beats:
    - text: "Compute grows and shrinks with your workload."
    - text: "Every file is stored in three regions."
    - text: "All traffic is encrypted."
    - text: "And nothing is trusted by default."
```

**2. Reading the slide → complementing it.** Bad: the voice says exactly what is written.

```yaml
- id: claim_bad
  type: text_card
  params: {text: "Smaller models can be just as accurate"}
  beats: [{text: "Smaller models can be just as accurate."}]
```

Good: the screen holds the claim, the voice gives the reason and the stakes.

```yaml
- id: claim_good
  type: text_card
  params: {text: "Smaller ≠ worse"}
  beats:
    - text: "We assumed size bought accuracy."
    - text: "On our benchmark, a model half the size scored the same."
      actions: [{highlight: text, style: underline, at: 0.4}]
```

**3. A raw number → a `stat` with a comparison.** Bad: a sentence of digits.

```yaml
- id: latency_bad
  type: text_card
  params: {text: "Median latency went from 18 ms to 12.5 ms after the change"}
  beats: [{text: "Median latency went from eighteen milliseconds to twelve and a half milliseconds after the change."}]
```

Good: one big number that counts, the change coloured by whether it is good.

```yaml
- id: latency_good
  type: stat
  params:
    value: 12.5
    unit: "ms"
    label: "median latency"
    comparison: {value: 18, kind: before, better: lower, delta: percent}
  beats:
    - text: "Requests now take twelve and a half milliseconds."
    - text: "That is almost a third faster than before."
```

**4. An unexplained chart → a chart that points.** Bad: bars appear, the voice talks about
something the viewer has to find.

```yaml
- id: costs_bad
  type: bar_chart
  params: {labels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun"], values: [12, 13, 12, 31, 14, 13]}
  beats: [{text: "As you can see, something unusual happened in one of these months, which we investigated."}]
```

Good: a title that says what the chart is, the outlier highlighted while it is named, a callout
with the reason, and the source in the caption.

```yaml
- id: costs_good
  type: bar_chart
  params:
    title: "Cloud cost per month (k$)"
    labels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    values: [12, 13, 12, 31, 14, 13]
    caption: "Source: billing export, 2025"
  beats:
    - text: "Our cloud bill is usually flat."
    - text: "Except in April, when it more than doubled."
      actions:
        - {highlight: "bar:Apr"}
        - {callout: "bar:Apr", kind: arrow, label: "Test cluster left on", at: 0.5}
    - text: "One forgotten cluster cost nineteen thousand dollars."
```

**5. A long beat → short beats with their own reveals.** Bad: 45 words over one picture: 18 s of
the same frame (lint `dead_air`).

```yaml
- id: pipeline_bad
  type: process
  params: {stages: ["Write", "Check", "Render", "Publish"], reveal: all}
  beats:
    - text: "You write the config, then you check it with validate and storyboard and lint until everything is clean, then you render the final video with the real voice, and finally you publish it together with its chapters, thumbnail and subtitles so people can find it."
```

Good: one stage per beat, the token moves while each is named.

```yaml
- id: pipeline_good
  type: process
  params:
    heading: "From idea to video"
    stages: [{label: "Write", icon: pencil}, {label: "Check", icon: search}, {label: "Render", icon: play}, {label: "Publish", icon: megaphone}]
  beats:
    - text: "You write one config file."
    - text: "Storyboard and lint check it."
    - text: "Then the real voice and the final render."
    - text: "And it ships with chapters and subtitles."
```

**6. A slow opening → a hook.** Bad: 6 s of logo and title before anything is said.

```yaml
- id: opening_bad
  type: title
  params: {title: "Quarterly Infrastructure Review", subtitle: "Platform Team", kicker: "Q3 2025"}
  beats: [{text: "Welcome to the quarterly infrastructure review by the platform team. In this video we will look at a number of topics."}]
```

Good: the result first, then the context.

```yaml
- id: opening_good
  type: stat
  params: {value: 41, suffix: "%", label: "lower cloud bill", context: "Q3 vs Q2 2025"}
  beats:
    - text: "We cut our cloud bill by forty-one percent."
    - text: "Here is how, in three changes."
```

<!-- topic: outputs (also: slides, export, gif, thumbnail, chapters, translations, translate, languages, licence, license, rights) -->
## Outputs: video, chapters, thumbnail, slides, GIFs, translations

- **Video and subtitles**: `vidgen render` writes `output/<output>.mp4` and `<output>.srt`
  (`--preview`: `<output>_preview.mp4`; `--draft`: `<output>_draft.mp4`; `--variant NAME`: `<output>_<variant>.mp4`). The
  chapter list and thumbnail go to `output/` too; `output_dir:` (relative to the project folder)
  or `--output-dir DIR` moves them. `build/` and `exports/` stay put.
- **Chapters**: with `chapter` cards or `chapter:` keys the MP4 gets chapter marks and
  `<output>_chapters.txt` the YouTube list (`0:00 Intro`...); `vidgen validate` warns when
  YouTube would ignore it (fewer than 3 chapters, one under 10 s). `metadata:` adds tags.
- **Thumbnail**: a designed card reads best small. Keep its title ≤ 6 words. `vidgen render`
  writes it with the video, `vidgen thumbnail` alone; open the small copy it names
  (`build/.../thumbnail/<name>_small.png`, YouTube's 320 px) and fix the checks it prints. A
  frame of a scene works too: `vidgen thumbnail --scene results --beat 2`.

```yaml
thumbnail: {title: "77% of the model is dead weight", icon: brain-circuit, jpeg: true}
scenes:
  - id: intro
    type: title
    params: {title: "Pruning large models"}
    beats: [{text: "Most of a large model can go."}]
```

- **Slides**: `vidgen slides --final` writes a self-contained HTML deck to `exports/` (a slide
  per beat, the narration as speaker notes; `--audio` for a narrated deck); `--format pdf
  --notes` a PDF with notes pages (extra `schu-video-generator[pdf]`). A video built with one reveal per beat
  is a good deck for free; check `--mode scene` for a compact one.
- **GIFs and clips**: `vidgen export gif --scene ID --max-mb 5` (a palette GIF within a size
  budget, for READMEs and chats), `vidgen export clip --scene ID --with-audio` (an MP4 part).
  Render the video first.
- **Translations**: add a variant with `language: pt-BR` and `translations:`, run
  `vidgen translate-template --variant pt`, fill in every `text:` of the file (keep it short:
  translations run longer), `vidgen validate` (lists what is still untranslated),
  `vidgen tts --variant pt` (voices only translated beats), then storyboard and lint the
  variant: longer text can overflow where the source fit.
- **Dubbing a cartoon**: the same variant. With Kokoro every speaker gets a voice of the
  language of the same kind automatically (`vidgen validate` prints `dub [pt]: ...` and warns
  when two speakers end up with one voice); name one with `dub: {pt: pm_alex}` on that voice in
  `voices:` (or on `voice:` for the narrator). Then `vidgen tts --all-languages`, `vidgen lint
  --all-languages` (timings, overlaps and text are checked in each language) and `vidgen render
  --preview --all-languages`. Example: `examples/cartoon-music-box` (variant `pt`).

```yaml
variants:
  pt:
    language: pt-BR
    translations: translations/pt.yaml
scenes:
  - id: intro
    type: title
    params: {title: "Hello"}
    beats: [{text: "Hello and welcome."}]
```

- **Generated pictures** (`image` `generate:`): `vidgen imagegen --dry-run` shows prompts and
  cost; placeholders render until you run `vidgen imagegen`. Describe a scene, never text,
  charts or logos (vidgen draws those better), and set one `imagegen: {style: ...}` for the
  whole video.
- **Cartoon backgrounds** (`stage` `generate:`): see "The set" in `vidgen guide cartoons`.
- **Choosing an image provider**: `openai` (the default; `OPENAI_API_KEY`, gpt-image-1) is one
  good model at a known price. `imagegen: {provider: openrouter, model: author/name}`
  (`OPENROUTER_API_KEY`) reaches many models with one key — some cheaper per picture
  (e.g. `bytedance-seed/seedream-4.5` at ~$0.04, `black-forest-labs/flux.2-klein-4b` by the
  megapixel), some better at a style. Read the prices in `vidgen imagegen --dry-run` (its
  `price:` line says the basis; "price unknown" for models billed per token) and fix every
  `problem:` / `note:` it prints before a real run. Keep one provider and model per video so the
  pictures match; changing them makes every picture "missing" (new pictures, new cost). If the
  account requires Zero Data Retention, choose a model with a ZDR endpoint (e.g.
  `bytedance-seed/seedream-5-0-flash`); vidgen's error lists them when a model is refused.
- **Vector (SVG) pictures** (`generate: {prompt, format: svg}` with `imagegen.svg_model`, e.g.
  `recraft/recraft-v4.1-vector`, ~$0.08; or an `.svg` file as `path`): drawn as shapes, so
  `draw: true` traces then fills them and `recolor: theme` paints them in the theme's colours.
  Worth it for flat illustrations, icons and diagram-like art (few flat colours; ask for
  "flat illustration, simple shapes, few colours"); not for photos or soft lighting (thousands
  of shapes, capped and thinned: worse than a PNG). Text in an SVG is removed — keep words in
  vidgen's captions. No SVG model has a ZDR endpoint (2026-10-08).

### Your content and third-party services

- The MIT licence covers the software, not the videos you make or the files you add.
- Use only images, clips, screenshots, music and quotes you own or have permission to use
  (screenshots of other products may also show their trademarks).
- ElevenLabs narration and OpenAI pictures are subject to those providers' terms (e.g. plan
  limits on commercial use; cloning a voice requires the speaker's consent). Pictures made
  through OpenRouter, and narration voiced through it, are subject to OpenRouter's terms and to
  those of the model's provider.
- The built-in fonts (SIL OFL), Lucide icons (ISC), Natural Earth map data, sound effects and
  music beds may be used in your videos, including commercially, with no attribution required
  in the video (Natural Earth asks for none; the OFL and ISC notices concern redistributing the
  files themselves). So may composed music played with the default GeneralUser GS SoundFont (no
  attribution required; a credit in the description is welcome: `vidgen soundfont info` prints
  one); with your own `soundfont:` its licence applies.

<!-- topic: troubleshooting (also: errors, fixes, lint, validate, problems) -->
## Troubleshooting: messages and fixes

**`vidgen validate`** (each problem names a config path; `--json` lists them all):

| message says | fix |
|---|---|
| `unknown scene type 'x'; did you mean ...` | use a listed type (`vidgen list-scenes`) |
| `unknown parameter 'x'; did you mean 'y'?` | rename it; `vidgen schema --scene TYPE` lists the params |
| `a scene without beats (silent scene) needs a 'duration'` | add `duration: 2.5`, or give it beats |
| `'duration' is only allowed on silent scenes` | remove `duration`: beats set the length |
| `duplicate beat id` | beat ids are unique in the whole video; rename one |
| `unknown target 'x' ...; did you mean ... (targets: ...)` | pick a name from the list (labels are case-sensitive: `bar:4K`) |
| `until 'x' is not a later beat of scene 'y'` | `until` names a later beat id of the same scene |
| `unknown action 'x'` / `unknown option` | actions are `reveal`, `dim`, `highlight`, `zoom`, `pan`, `follow`, `transform`, `callout`, `sfx`, `particles`, `say`, `look_at`, `turn`, `emote`, `pose`, `react`, `walk_to`, `run_to`, `enter`, `exit`, `gesture`, `jump`, `keyframes`, `move_along`, `pick_up`, `hold`, `put_down`, `give`, `throw`, `open`, `close`, `let_go`, `pour`, `switch_on`, `switch_off`, `drop_fruit`, `birds`, `sit_on`, `lean_on`, `stand_up`, `get_in`, `ride_to`, `get_out`, `light`, `wind`, `blow_away`, `effect` |
| `labels has 2 entries but values has 3` | one value per label |
| `unknown theme color 'x'` | use a token (`primary`, `highlight`...) or quoted hex `"#0B5FFF"`, or add it to `theme.colors` |
| `invalid hex color` | `#RGB`, `#RRGGBB` or `#RRGGBBAA`, in quotes (YAML reads `#` as a comment) |
| `unknown icon 'x'; did you mean 'y'?` | `vidgen list-icons --search WORD` |
| `file not found: assets/...` | paths are relative to the project folder |
| `starts chapter 'x' right after the chapter card` | put the `chapter:` key on the card instead |

LaTeX in YAML: write formulas in single quotes (`'\frac{1}{2}'`). Equations need a LaTeX
install; `vidgen validate` warns when it is missing.

**`vidgen lint`** (each finding names its rule and the still to open):

| rule | what it means | usual fix |
|---|---|---|
| `max_words` | too much text on one frame | split the scene, shorten items, `dim_previous`, fewer columns |
| `min_font` | text too small for the output | less content per scene (it was shrunk to fit), shorter labels, split the table / diagram / timeline |
| `off_frame` | text cut off at the frame edge | shorter text; in a custom scene, place it in a region |
| `safe_area` | text in the margin | as above; check reserving overlays |
| `text_overlap` | two texts on top of each other | fewer or shorter labels; a custom scene's layout |
| `covered_text` | a shape drawn over text | move the shape or the callout (`side:`) |
| `label_spacing` | a callout label touches other text (a value, the title) | another `side:`, an `arrow` instead of a `label`, a shorter label |
| `contrast` | text hard to read on its background | theme tokens instead of custom colours; another preset |
| `overlay_overlap` | an overlay covers scene text | `reserve: true` on the overlay, or another corner / position |
| `host_overlap` | the host overlaps the content, a caption or an overlay | a smaller host (`size`), another `side` / `place`, or `host: false` on that scene |
| `walk_overlap` | a character's walk ends on another character | walk it to another mark or x, or move the other one first |
| `off_stage` | a character is cut by the edge of the view (in a `shot`: a character it frames is out of it) | another mark or x inside the view, or `pan` to it; in a shot, keep it from walking out or frame another shot |
| `character_overlap` | two characters stand on each other (at about the same depth) | marks further apart, or `walk_to` one away (across, or in depth) |
| `prop_overlap` | two props on the floor at about the same depth are drawn over each other (a room's door over the sofa against the wall) | another `at` for one (a door: its x in the room's `doors`), a smaller `scale`, or a `depth` that puts one in front; a picture or clock above furniture, a lifted prop and a rug are fine |
| `bubble_overlap` | a speech bubble covers a face, another bubble or an effect symbol | a shorter `bubble` text, characters further apart, or the lines (or the line and the effect) in different beats |
| `facing_away` | a speaker faces away from the one it talks to (last looked at, else the nearest) | `turn`, `look_at: <listener>`, or swap their marks |
| `hidden_speaker` | something in front hides the speaker's face | move one of them, or a smaller `depth` for the speaker |
| `small_speaker` | a speaking face too small on screen to read it and its lip sync | `shot: closeup <name>` (or `medium`) for that beat, or `character_size: large` |
| `mouth_without_voice` | a mouth still shows speech after the narration ended | `vidgen tts` again; in a custom scene, lip sync with `clock=self.beat_clock()` |
| `concept_colors` | the `terms:` colours: more than 5, too faint on the background, or a term coloured otherwise by a scene setting | fewer colours (related terms may share one), a readable theme token, or leave the scene's colour setting out |
| `look_alike` | two characters too alike to tell apart | change what the message names on the second (body, hair, species, clothes colour); or `vidgen cast --random N` |
| `dead_air` | nothing moved for over 6 s | split the beat, add a reveal or an action, shorten a silent `duration` |
| `narration_speed` | words per second outside 1.8–3.5 (English) | shorten or lengthen the beat's text; without audio it is only `info` (an estimate) |
| `animation_overrun` | animations ran past the narration | a custom scene's animations are too long for the beat |
| `rushed_animation` | animations squeezed into a short beat | merge two short beats, or reveal fewer things per beat |
| `talked_over` | an `overlap` hides whole words of the line before, or an `interrupt` cuts them | a shorter `overlap` (none for an interrupt), or `interrupt: true` to cut the line |
| `readback` | the audio does not say what the text says | add a `pronunciation:` entry, `vidgen tts`, check again |
| `unclear_speech` | (only with `--readback`) a word heard unclearly or after an odd pause | respell it in `pronunciation:`, or another voice, speed or `emotion:` for the beat; `vidgen tts`, check again |

**Other things that go wrong**

- *The storyboard did not change after an edit to a file outside `assets/`*: `--force`.
- *A table / diagram / timeline "does not fit at the readable size"* (render warning): it was
  scaled down; split it into two scenes or shorten the texts.
- *Preview timing is wrong*: until `vidgen tts`, beats are timed from word counts; numbers and
  acronyms take longer to say. Re-check pacing after the real audio.
- *`vidgen render --scene ID` re-joins the other scenes as they are*: render the scene before a
  new transition or carry too.
- *`ffmpeg not found`*: install it and open a new terminal.
- *`ffmpeg X.Y is too old`*: install ffmpeg 4.4 or newer.
