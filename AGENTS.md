# vidgen author guide: making great videos with vidgen

> **Who this is for:** AI agents (and people) who **use** vidgen to make videos and slide decks.
> If you are working **on vidgen itself** (its Python code, tests, docs), read `CLAUDE.md` in the
> vidgen repository instead. This guide ships with vidgen: `vidgen guide` prints all of it,
> `vidgen guide TOPIC` one part, `vidgen guide --list` the topics.

Topics: `start` (rules at a glance), `workflow` (the loop), `pacing` (storytelling and on-screen
text), `social` (vertical videos), `scenes` (which scene type), `design` (themes, colour, icons),
`actions` (pointing at things), `overlays` (overlays, transitions, continuity), `audio` (voices,
pronunciation, effects, music), `examples` (good vs bad), `outputs` (slides, chapters,
thumbnail, GIFs, translations), `troubleshooting` (validate and lint messages).

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

Reference for every key: `docs/CONFIG.md` in the vidgen repository; from the command line:
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
   measure the real speech.
10. **`vidgen readback`** (optional extra `vidgen[stt]`): speech-to-text of the MP3s against
    your texts; it names misheard terms and suggests a pronunciation entry. Fix, `vidgen tts`,
    and `vidgen lint` again (its `readback` rule reads the cached transcripts).
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

**Costs.** `vidgen tts` (ElevenLabs, per character), `vidgen imagegen` (OpenAI Images, per
picture) and `vidgen readback` with `stt: {provider: elevenlabs}` cost money; everything else is
local and free. Always run `vidgen tts --dry-run` / `vidgen imagegen --dry-run` first, finish the
layout on the word-count-timed preview, and commit `audio/` and `assets/generated/` (they cannot
be made again identically). Renders are slow but free: `storyboard` and `lint` re-render only
the scenes that changed; `vidgen render` renders every scene unless you give `--scene ID`;
`--jobs N` renders several at once; preview while iterating.

**JSON everywhere.** `validate`, `list-scenes`, `list-themes`, `list-icons`, `list-sfx`,
`list-music`, `schema`, `render`, `storyboard`, `lint`, `thumbnail`, `export`, `slides`,
`translate-template`, `readback`, `gallery`, `plan` and `guide` take `--json`: one document on stdout,
`{version, ok, warnings, ..., error?}`, exit code 0 exactly when `ok`.

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

<!-- topic: scenes (also: chooser, types, scene-types) -->
## Choosing the scene type

Pick by **what the viewer should understand**, not by what the data looks like. To see what
each type looks like at 16:9 and 9:16, open the scene gallery (`docs/gallery/README.md` in the
vidgen repository: a still, a GIF, the YAML, params and targets per type) or make it yourself:
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
| categories compared by size | `bar_chart` | `title`, `labels`, `values`, `unit`, `highlight`, `caption` |
| change over time, trends | `line_chart` | `title`, `x`, `series`, `x_label`, `y_label` |
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
| a short listing (≤ 15 lines) | `code` | `title`, `code`, `path`, `highlight` |
| a long file, explained part by part | `code_walkthrough` | `title`, `path`, `code`, `steps`, `excerpt` |
| thanks, links, call to action | `end_card` | `title`, `lines`, `icon`, `logo` |

How beats drive scenes: each type splits its content into **reveal steps** and plays step *i*
at beat *i* (more steps than beats: spread evenly; more beats: the last ones hold). Types with
per-beat data (`code_walkthrough`, `equation_derivation`, `screenshot`, `video_clip`, `map`)
take a `steps` list, entry *i* for beat *i*: write as many steps as beats. A `highlight` param
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
- id: snippet
  type: code
  params: {title: "Load and train", code: "data = load()\nmodel = fit(data)\nsave(model)", highlight: ["1", "2-3"]}
  beats:
    - text: "We load the data."
    - text: "Then fit and save the model."
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
| `reveal` | bring a later element in early | rarely: the default order is usually right |
| `transform` | morph one target into another (`into`) | for equations and before / after |
| `sfx` | a sound at that moment (`vidgen guide audio`) | the important moments only |

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
          at: 0.3
```

- `at` (0–1, a fraction of the beat) times the action to the word it belongs to; actions never
  make a beat longer.
- `until: <later beat id>` keeps a highlight / dim / callout on screen; without it a callout
  disappears at the next beat and a zoom comes back by the beat's end.
- A callout without a target points at an `area: [x, y, w, h]` of the frame (fractions).
- Check actions mid-beat with `vidgen storyboard --scene ID --per-beat 3`.

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
style per video). Transitions never cover narration.

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

**Pronunciation.** Write the text as it should be **read** on screen and in subtitles; fix
how it is **said** with `pronunciation:` (applied to the TTS text only). Run
`vidgen tts --dry-run` and read every `says:` line; after `vidgen tts`, `vidgen readback` finds
what the voice still gets wrong.

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
`thud` (a big number lands), `swoosh`, `typing`. Two or three per minute, on the moments that
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
walkthroughs), `bright` (launches, upbeat social). It is ducked under the voice automatically
and the mix is normalised to −16 LUFS. Leave the defaults; turn it off over clips with their
own sound (`music: false` on the scene).

```yaml
music: {source: calm, volume: -2}
scenes:
  - id: intro
    type: text_card
    params: {text: "Listen"}
    beats: [{text: "A calm bed sits under the voice."}]
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

<!-- topic: outputs (also: slides, export, gif, thumbnail, chapters, translations, translate, languages) -->
## Outputs: video, chapters, thumbnail, slides, GIFs, translations

- **Video and subtitles**: `vidgen render` writes `<output>.mp4` and `<output>.srt`
  (`--preview`: `<output>_preview.mp4`; `--variant NAME`: `<output>_<variant>.mp4`).
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
  --notes` a PDF with notes pages (extra `vidgen[pdf]`). A video built with one reveal per beat
  is a good deck for free; check `--mode scene` for a compact one.
- **GIFs and clips**: `vidgen export gif --scene ID --max-mb 5` (a palette GIF within a size
  budget, for READMEs and chats), `vidgen export clip --scene ID --with-audio` (an MP4 part).
  Render the video first.
- **Translations**: add a variant with `language: pt-BR` and `translations:`, run
  `vidgen translate-template --variant pt`, fill in every `text:` of the file (keep it short:
  translations run longer), `vidgen validate` (lists what is still untranslated),
  `vidgen tts --variant pt` (voices only translated beats), then storyboard and lint the
  variant: longer text can overflow where the source fit.

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
| `unknown action 'x'` / `unknown option` | actions are `reveal`, `dim`, `highlight`, `zoom`, `transform`, `callout`, `sfx` |
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
| `dead_air` | nothing moved for over 6 s | split the beat, add a reveal or an action, shorten a silent `duration` |
| `narration_speed` | words per second outside 1.8–3.5 (English) | shorten or lengthen the beat's text; without audio it is only `info` (an estimate) |
| `animation_overrun` | animations ran past the narration | a custom scene's animations are too long for the beat |
| `rushed_animation` | animations squeezed into a short beat | merge two short beats, or reveal fewer things per beat |
| `readback` | the audio does not say what the text says | add a `pronunciation:` entry, `vidgen tts`, check again |

**Other things that go wrong**

- *The storyboard did not change after an edit to a file outside `assets/`*: `--force`.
- *A table / diagram / timeline "does not fit at the readable size"* (render warning): it was
  scaled down; split it into two scenes or shorten the texts.
- *Preview timing is wrong*: until `vidgen tts`, beats are timed from word counts; numbers and
  acronyms take longer to say. Re-check pacing after the real audio.
- *`vidgen render --scene ID` re-joins the other scenes as they are*: render the scene before a
  new transition or carry too.
- *`ffmpeg not found`*: install it and open a new terminal.
