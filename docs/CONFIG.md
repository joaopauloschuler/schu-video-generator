# vidgen config reference

A project is a folder with one config file: `video.yaml` (or `video.yml` / `video.json`), UTF-8.
Unknown keys are an error everywhere except inside `params`, `theme.colors`, `theme.sizes` and
the bodies of `variants`, so typos are caught by `vidgen validate`. Paths are relative to the
project folder. Contents: [top level](#top-level), [scenes and beats](#scenes-and-beats),
[format](#format-and-preview), [variants](#variants), [theme](#theme), [voice](#voice-voice),
[narration](#narration-narration), [narration audio](#narration-audio-elevenlabs),
[built-in scene types](#built-in-scenes).

## Top level

| key | default | |
|---|---|---|
| `title` | required | the video's title (used in `timings.json`; not drawn by itself) |
| `output` | folder name | base name of the output files: `<output>.mp4`, `<output>.srt`, `<output>_preview.mp4`, `<output>_<variant>.mp4`; no path separators |
| `format` | `{width: 1920, height: 1080, fps: 30}` | final render (`vidgen render`) |
| `preview` | `{width: 854, height: 480, fps: 15}` | `vidgen render --preview` |
| `variants` | `{}` | named overrides, see [variants](#variants) |
| `theme` | see [theme](#theme) | colors, sizes, font, background |
| `voice` | see [voice](#voice-voice) | ElevenLabs voice |
| `narration` | see [narration](#narration-narration) | beat padding, duration estimate |
| `extensions` | `[extensions]` | folders whose `*.py` files and packages are imported (see docs/EXTENDING.md); the default may be missing, a folder you list must exist |
| `scenes` | required | the scenes in order, at least one |

## Scenes and beats

```yaml
scenes:
  - id: intro                 # required, unique; letters, digits and _ only
    type: title               # a built-in or extension scene type (`vidgen list-scenes`)
    params: {title: "Hello"}  # checked against the type's params (tables below)
    beats:                    # what the narrator says, in order
      - text: "Welcome."      # required, non-empty
        id: intro_b1          # optional; default <scene id>_b<n> (1-based); unique in the video
      - text: "Let's start."
  - id: pause
    type: text_card
    params: {text: "Part 2"}
    duration: 2               # a silent scene: no beats, a duration in seconds
```

| key | default | |
|---|---|---|
| `id` | required | names the scene in `--scene`, build files and errors |
| `type` | required | scene type name |
| `params` | `{}` | free-form for types without a params model |
| `beats` | `[]` | each beat is narrated into `audio/<beat id>.mp3`; its animation lasts as long as its audio plus `narration.pad` |
| `duration` | none | seconds; required on a scene without beats and not allowed on a scene with beats |

Beat `id`s name the audio files: keep them when you edit the text (only that beat is
re-voiced). A beat `text` is spoken as written; it is also the subtitle.

## Format and preview

`format` and `preview` have the same keys: `width` (default 1920 / 854), `height` (1080 / 480)
and `fps` (30 / 15), all positive integers; `width` and `height` must be even (H.264). Any
aspect ratio works: the shorter side of the frame is always 8 Manim units, so 9:16 gives a frame
8 units wide and 14.22 high.

## Variants

A variant is a named set of overrides deep-merged onto the config: mappings merge key by key,
anything else (lists such as `scenes`, strings, numbers) replaces the base value. The result is
validated like a normal config; a variant cannot contain `variants`. `vidgen validate` checks
every variant.

```yaml
variants:
  vertical:                                   # vidgen render --variant vertical
    format: {width: 1080, height: 1920}       #   -> <output>_vertical.mp4
    preview: {width: 480, height: 854}
  spanish:
    voice: {voice_id: "XXXXXXXXXXXXXXXXXXXX"}   # own audio folder: audio/spanish/
    scenes: [...]                             # a list replaces the whole base list
```

Renders of a variant go to `build/<final|preview>_<variant>/`. Audio sharing rules are under
[narration audio](#narration-audio-elevenlabs).

## Theme

```yaml
theme:
  background: "#0E1116"     # frame background
  font: Inter               # font family for all text (must be installed; see README)
  colors:                   # tokens; these are the defaults, add any name you like
    text: "#E8EAED"
    dim: "#6B7280"
    accent: "#FF6B6B"
    highlight: "#FFD166"
    primary: "#58C4DD"
    secondary: "#F2A541"
    tertiary: "#83C167"
    surface: "#161B24"      # panels, code window
    # brand: "#7C3AED"      # your own tokens work in every color param
  palette: ["#58C4DD", "#F2A541", "#C792EA", "#83C167"]   # series colors (charts), in order
  sizes: {title: 56, subtitle: 42, heading: 36, body: 32, caption: 24, small: 20}  # font points
```

You only write what you change: `colors` and `sizes` are merged over the defaults (and over
tokens registered by extensions); `palette` replaces the default list. Colors are hex
(`#RGB`, `#RRGGBB` or `#RRGGBBAA`, quoted in YAML because of the `#`); token names use letters,
digits and `_`. Sizes are positive numbers.

## Voice (`voice:`)

```yaml
voice:
  provider: elevenlabs              # the only provider for now
  voice_id: nPczCjzI2devNBz1zQrb    # ElevenLabs voice id
  model_id: eleven_multilingual_v2
  output_format: mp3_44100_128      # ElevenLabs output_format query parameter
  settings:                         # sent as voice_settings
    stability: 0.55                 # 0..1
    similarity_boost: 0.75          # 0..1
    style: 0.0                      # 0..1
    use_speaker_boost: true
  context: true                     # send the neighbouring beats' text for smoother intonation
```

All keys are optional; the values shown are the defaults. Unknown keys are an error. Changing
`voice_id`, `model_id`, `output_format` or `settings` re-voices every beat on the next `vidgen tts`.

## Narration (`narration:`)

```yaml
narration:
  pad: 0.35               # seconds of silence after each beat
  words_per_second: 2.6   # duration estimate for beats that have no audio yet
```

## Narration audio (ElevenLabs)

Each beat is spoken by ElevenLabs into `audio/<beat_id>.mp3`, with `audio/<beat_id>.hash`
recording what it was generated from.

**API key.** vidgen reads the key only from the environment variable `ELEVENLABS_API_KEY`;
it never stores it in the config, audio, build files, logs or error messages.

- Windows: `setx ELEVENLABS_API_KEY your_key` once, then open a new terminal.
- Linux/macOS: `export ELEVENLABS_API_KEY=your_key` (add it to your shell profile to keep it).

**Commands.**

```
vidgen tts --dry-run          # list beats that need audio + character count (no key needed)
vidgen tts                    # generate missing/stale beats only
vidgen tts --beat s2_b1       # only these beats (still skipped if up to date)
vidgen tts --force            # regenerate (combine with --beat to limit it)
vidgen tts --variant spanish  # audio for a variant
vidgen validate               # prints e.g. "audio: 18 ok, 2 stale, 1 missing"
```

**What triggers regeneration.** A beat is regenerated when its MP3 is missing or its hash does
not match the beat's text plus `voice_id`, `model_id`, `output_format` and `settings`. Editing
one beat regenerates only that beat: the neighbours' text is sent for intonation but is not part
of the hash, and neither is `context`. Hash files written by the original kphi3 script are
accepted while `output_format` and `settings` keep their defaults.

**Variants.** A variant shares `audio/` unless its voice (after merging) or the text of a beat
differs from the base config; then its audio goes to `audio/<variant>/`. Beats that are the same
in both are copied from `audio/` instead of being paid for again.

**Housekeeping.** MP3s of beats that no longer exist are reported as orphaned but never deleted.
Failed requests show the HTTP status and ElevenLabs' message; rate limits and server errors are
retried a few times automatically. Rendering uses whatever audio exists; stale or missing audio
is reported as a warning.

## Built-in scenes

Every scene has a `type`, `params` (checked by `vidgen validate`; unknown keys are errors) and
either `beats` (narrated) or a `duration` (silent). `vidgen list-scenes` prints every type with
its params. Conventions shared by all built-ins:

- **Colors** (`color` in the tables) are theme tokens (`text`, `dim`, `accent`, `highlight`,
  `primary`, `secondary`, `tertiary`, `surface`, or your own `theme.colors`) or hex (`"#FF6B6B"`).
  **Sizes** (`size`) are theme size tokens (`title`, `subtitle`, `heading`, `body`, `caption`,
  `small`) or a number of points. Unknown tokens are reported by `vidgen validate`.
- **Beats drive the reveal.** Each type splits its content into reveal steps (listed per type
  below). Step *i* appears during beat *i*; with more steps than beats they are spread evenly;
  with more beats than steps the extra beats hold the finished picture. Animations take a
  fraction of each beat and never make a beat longer than its narration (+ `narration.pad`).
  A silent scene shows all steps within its `duration`.
- After the last beat the scene fades out (0.5 s; 1 s for `end_card`; `text_card` does not fade).
- **Any aspect ratio.** Layouts use the frame size, so the same config works for 16:9 and a
  vertical 9:16 variant; long text is wrapped and shrunk to fit.
- Text-only types need no LaTeX; only `equation` does.

### `title`

Steps: (1) kicker, title and subtitle, (2) authors.

| param | type | default | |
|---|---|---|---|
| `title` | str | required | wrapped to fit; may contain `\n` |
| `subtitle` | str | `""` | |
| `kicker` | str | `""` | small label above the title |
| `authors` | list[str] | `[]` | one line each |
| `highlight` | str | `""` | part of the title drawn in `highlight_color` |
| `color`, `highlight_color`, `subtitle_color`, `kicker_color`, `authors_color` | color | `text`, `highlight`, `text`, `primary`, `dim` | |

```yaml
- id: intro
  type: title
  params:
    kicker: "TECHNICAL REPORT"
    title: "Saving 77% of the Parameters"
    highlight: "77%"
    subtitle: "in Large Language Models"
    authors: ["Ada Lovelace · Analytical Engine Society"]
  beats:
    - text: "What if a large language model could lose most of its parameters?"
    - text: "This report, by Ada Lovelace, shows how."
```

### `bullets`

Steps: one per item (the heading comes with the first). `reveal: all` shows every item in beat 1.

| param | type | default | |
|---|---|---|---|
| `items` | list[str] | required | at least one |
| `heading` | str | `""` | |
| `reveal` | `per_beat` \| `all` | `per_beat` | |
| `numbered` | bool | `false` | `1.` `2.` ... instead of `marker` |
| `marker` | str | `"•"` | |
| `dim_previous` | bool | `false` | fade earlier items when a new one appears |
| `size`, `heading_size` | size | `body`, `heading` | shrunk automatically for long lists |
| `color`, `heading_color`, `marker_color` | color | `text`, `text`, `primary` | |

```yaml
- id: points
  type: bullets
  params:
    heading: "Takeaways"
    items: ["Fewer parameters", "Same validation loss", "One GPU, three days"]
    dim_previous: true
  beats:
    - text: "First, the model is much smaller."
    - text: "Second, it learns just as well."
    - text: "And it trained on a single GPU."
```

### `bar_chart`

Steps: all bars (`reveal: all`, default) or one per bar (`per_beat`), then — if `highlight` is
set — a focus step that dims the other bars. Bars grow while their value labels count up.

| param | type | default | |
|---|---|---|---|
| `labels` | list[str] | required | |
| `values` | list[float] | required | same length as `labels`; negatives allowed |
| `title` | str | `""` | |
| `caption` | str | `""` | small note under the chart |
| `unit` | str | `""` | appended to every value label (`"%"`, `" ms"`) |
| `value_format` | str | automatic | Python format, e.g. `"{:.1f}"`, `"{:,.0f}"`, `"{:.0%}"`; default shows the decimals the values need |
| `colors` | color \| list[color] \| `palette` | `primary` | one color, one per bar, or `theme.palette` |
| `highlight` | int \| str | none | bar index (0-based) or label |
| `highlight_color` | color | `highlight` | highlighted value label |
| `horizontal` | bool | auto | default: vertical bars; horizontal in a portrait frame with more than 5 bars |
| `reveal` | `all` \| `per_beat` | `all` | |
| `baseline` | float | `0` | value the bars start from (e.g. `1.0` for losses; say so in `caption`) |

```yaml
- id: params
  type: bar_chart
  params:
    title: "Non-embedding parameters"
    labels: ["phi-3", "kphi-3 (2 layers)", "kphi-3 (3 layers)"]
    values: [227, 35, 53]
    unit: "M"
    colors: palette
    highlight: 2
  beats:
    - text: "The baseline has 227 million parameters; our models far fewer."
    - text: "The three-layer version keeps just 23 percent."
```

### `line_chart`

Steps: one per series (`reveal: per_beat`, default; the axes come with the first) or all
series in beat 1 (`all`). Each line ends with a `name value` label; when those labels would be
too wide (e.g. in portrait) the names move to a legend above the plot. Axis labels are plain
text (no LaTeX).

| param | type | default | |
|---|---|---|---|
| `x` | list[float] \| list[str] | required | numbers (increasing) or category names |
| `series` | `{name: [values]}` or list of `{name, values, color}` | required | one value per `x` |
| `title`, `caption` | str | `""` | |
| `x_label`, `y_label` | str | `""` | |
| `y_min`, `y_max` | float | from the data | |
| `value_format` | str | automatic | for y ticks and end labels |
| `x_format` | str | `"{:g}"` | for numeric `x` |
| `unit` | str | `""` | appended to y values |
| `reveal` | `per_beat` \| `all` | `per_beat` | |
| `annotate` | bool | `true` | end-of-line labels |
| `dots` | bool | auto | markers at the data points (default: up to 12 points) |

```yaml
- id: loss
  type: line_chart
  params:
    title: "Validation loss"
    x: [1, 2, 3, 4, 5]
    x_label: "epoch"
    series:
      - {name: baseline, values: [2.1, 1.8, 1.66, 1.58, 1.53]}
      - {name: sparse, values: [2.2, 1.9, 1.68, 1.55, 1.49], color: tertiary}
  beats:
    - text: "Here is the baseline."
    - text: "And the sparse model, which ends lower."
```

### `image`

Steps: (1) the image, (2) the caption. `vidgen validate` reports a missing or unsupported file
(png, jpg, jpeg, gif, bmp, webp, tif).

| param | type | default | |
|---|---|---|---|
| `path` | str | required | relative to the project folder, e.g. `assets/photo.jpg` |
| `caption` | str | `""` | |
| `fit` | `contain` \| `cover` | `contain` | `contain`: whole image, caption below; `cover`: fills the frame (cropped), caption on a band |
| `ken_burns` | bool \| mapping | `false` | slow zoom/pan over the whole scene; `true` = zoom 1.0 → 1.15 on the center |
| `ken_burns.start_scale`, `.end_scale` | float 1–4 | `1.0`, `1.15` | |
| `ken_burns.start_focus`, `.end_focus` | `[x, y]` in 0–1 | `[0.5, 0.5]` | point to center on (0,0 = top left) |
| `caption_color`, `caption_size` | color, size | `text`, `caption` | |

```yaml
- id: lab
  type: image
  params:
    path: assets/lab.jpg
    fit: cover
    caption: "The training cluster"
    ken_burns: {end_scale: 1.25, end_focus: [0.7, 0.35]}
  beats:
    - text: "Everything ran on this machine."
```

### `quote`

Steps: (1) quote mark and text, (2) attribution. Quote characters around `text` are removed;
the scene draws a large typographic mark.

| param | type | default | |
|---|---|---|---|
| `text` | str | required | |
| `author`, `source` | str | `""` | shown as `— author` and, smaller, `source` |
| `size` | size | `subtitle` | of the quote text (shrunk if long) |
| `color`, `mark_color`, `author_color`, `source_color` | color | `text`, `primary`, `text`, `dim` | |
| `mark_font` | str | `"Georgia,DejaVu Serif,serif"` | font list for the quote mark |

```yaml
- id: saying
  type: quote
  params: {text: "Simplicity is prerequisite for reliability.", author: "Edsger W. Dijkstra"}
  beats:
    - text: "As Dijkstra put it: simplicity is prerequisite for reliability."
```

### `equation`

Steps: one per formula; each morphs into the next. The caption comes with the first. **Needs
LaTeX** (`latex` and `dvisvgm` on PATH — on Windows install MiKTeX). `vidgen validate` warns
when it is missing; rendering then fails with installation hints. A formula that does not
compile is reported with the scene id and the formula.

| param | type | default | |
|---|---|---|---|
| `latex` | str \| list[str] | required | math-mode LaTeX (no `$`); a list is a sequence of steps |
| `caption` | str | `""` | |
| `size` | size | `96` | |
| `color`, `caption_color` | color | `text`, `dim` | |

```yaml
- id: square
  type: equation
  params:
    latex: ["(a + b)^2", "(a + b)(a + b)", "a^2 + 2ab + b^2"]
  beats:
    - text: "Take a plus b, squared."
    - text: "Write it as a product."
    - text: "And expand."
```

In YAML, write backslashes in single quotes (`'\frac{1}{3}'`) or double them in double quotes.

### `code`

Steps: (1) the listing (with the first highlight applied), then one per further `highlight`
entry. Highlighting dims the other lines and puts a soft band behind the selected ones. Uses
Manim's `Code` (Pygments highlighting); the listing is scaled to fit, so keep lines short for
vertical videos.

| param | type | default | |
|---|---|---|---|
| `code` | str | — | inline code; give exactly one of `code` / `path` |
| `path` | str | — | file in the project (checked by `vidgen validate`) |
| `language` | str | from the file name, else `python` | a Pygments lexer name |
| `title` | str | `""` | |
| `highlight` | list of line specs | `[]` | entry *i* applies at beat *i*: `3`, `"2-4"`, `"1, 5-6"` or `[1, 4]` (1-based) |
| `line_numbers` | bool | `true` | |
| `style` | str | `github-dark` | a Pygments style (`monokai`, `dracula`, `one-dark`, ...) |
| `font` | str | `Monospace` | monospace font family (e.g. `Consolas` on Windows) |
| `size` | size | `caption` | starting font size (scaled to fill the frame, up to 1.5x) |
| `highlight_color` | color | `highlight` | |

```yaml
- id: listing
  type: code
  params:
    path: assets/train.py
    highlight: ["1-3", "8", "10-12"]
  beats:
    - text: "We load the data."
    - text: "Define the loss."
    - text: "And train."
```

### `end_card`

Steps: (1) logo and title, (2) lines. Fades out over 1 s.

| param | type | default | |
|---|---|---|---|
| `title` | str | `""` | at least one of `title`, `lines`, `logo` |
| `lines` | list[str] | `[]` | links, credits; short lines shrink together instead of wrapping |
| `logo` | str | none | image file in the project (checked by `vidgen validate`) |
| `title_color`, `color` | color | `highlight`, `text` | |
| `title_size`, `size` | size | `title`, `body` | |

```yaml
- id: outro
  type: end_card
  params:
    title: "Are LLMs over-parameterized?"
    lines: ["github.com/me/my-project", "huggingface.co/me"]
  beats:
    - text: "Code and models are online. Thanks for watching."
```

### `text_card`

One block of text, wrapped to fit, faded in at the first beat and held (no fade-out).

| param | type | default | |
|---|---|---|---|
| `text` | str | required | |
| `size` | size | `title` | |
| `color` | color | `text` | |

```yaml
- id: question
  type: text_card
  params: {text: "Over-parameterized?", color: accent}
  duration: 2
```
