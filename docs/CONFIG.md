# vidgen config reference

A project is a folder with one config file: `video.yaml` (or `video.yml` / `video.json`), UTF-8.
Unknown keys are an error everywhere except inside `params`, `theme.colors`, `theme.sizes` and
the bodies of `variants`, so typos are caught by `vidgen validate`. Paths are relative to the
project folder. Contents: [top level](#top-level), [scenes and beats](#scenes-and-beats),
[format](#format-and-preview), [variants](#variants), [theme](#theme), [voice](#voice-voice),
[narration](#narration-narration), [narration audio](#narration-audio-elevenlabs),
[built-in scene types](#built-in-scenes),
[JSON Schema](#json-schema-vidgen-schema), [frame stills](#frame-stills-vidgen-render---frames),
[storyboard](#storyboard-vidgen-storyboard), [lint](#lint-vidgen-lint),
[JSON output of commands](#json-output---json).

## Top level

| key | default | |
|---|---|---|
| `title` | required | the video's title (used in `timings.json`; not drawn by itself) |
| `output` | folder name | base name of the output files: `<output>.mp4`, `<output>.srt`, `<output>_preview.mp4`, `<output>_<variant>.mp4`; no path separators |
| `format` | `{width: 1920, height: 1080, fps: 30}` | final render (`vidgen render`) |
| `preview` | `{width: 854, height: 480, fps: 15}` | `vidgen render --preview` |
| `variants` | `{}` | named overrides, see [variants](#variants) |
| `theme` | see [theme](#theme) | preset, colors, sizes, font, background, code style |
| `voice` | see [voice](#voice-voice) | ElevenLabs voice |
| `narration` | see [narration](#narration-narration) | beat padding, duration estimate |
| `extensions` | `[extensions]` | folders whose `*.py` files and packages are imported (see docs/EXTENDING.md); the default may be missing, a folder you list must exist |
| `lint` | see [lint](#lint-vidgen-lint) | thresholds and severities of `vidgen lint` |
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
| `lint_ignore` | `[]` | `vidgen lint` findings to skip in this scene, see [lint](#lint-vidgen-lint) |

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
  preset: light_academic    # optional: a named set of theme values (see below)
  background: "#0E1116"     # frame background
  font: Inter               # font family for all text (must be installed; see README)
  code_style: github-dark   # Pygments style of `code` listings
  colors:                   # tokens; these are the defaults, add any name you like
    text: "#E8EAED"
    dim: "#838B98"
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

You only write what you change: `colors` and `sizes` are merged over the preset and the
defaults (and over tokens registered by extensions); `palette` replaces the list. Colors are hex
(`#RGB`, `#RRGGBB` or `#RRGGBBAA`, quoted in YAML because of the `#`); token names use letters,
digits and `_`. Sizes are positive numbers. `code_style` is any installed Pygments style
(`vidgen schema` lists them); a `code` scene's own `style` param wins over it.

**Precedence** (highest first): the values written under `theme:` (after merging a variant) >
the preset (and its base preset) > defaults registered by extensions
(`register_theme_defaults`, docs/EXTENDING.md) > the built-in defaults shown above (the
`dark_tech` look). Without `preset` the preset level is simply empty, so an existing project
looks exactly as before.

### Theme presets

`theme: {preset: NAME}` selects a named set of values; anything else under `theme:` still
wins, so `{preset: light_academic, colors: {primary: "#0B5FFF"}}` is the light look with your
blue. A variant can switch presets: `variants: {light: {theme: {preset: light_academic}}}`.
Mind that values written in the base `theme:` also override the variant's preset (a base
`background: "#0E1116"` would keep a light variant dark): write in the base only what every
variant shares, or select the default look with `preset: dark_tech` there instead.

| preset | background | text / dim | accents (`accent`, `highlight`, `primary`, `secondary`, `tertiary`) | `surface` | palette | `code_style` | sizes |
|---|---|---|---|---|---|---|---|
| `dark_tech` (the default look) | `#0E1116` | `#E8EAED` / `#838B98` | `#FF6B6B`, `#FFD166`, `#58C4DD`, `#F2A541`, `#83C167` | `#161B24` | `#58C4DD`, `#F2A541`, `#C792EA`, `#83C167` | `github-dark` | defaults |
| `light_academic` | `#F8F7F3` (off-white) | `#1F2328` / `#59606B` | `#B42318`, `#A64B00`, `#1D4ED8`, `#C2410C`, `#15803D` | `#FFFFFF` | `#1D4ED8`, `#C2410C`, `#7E22CE`, `#15803D` | `xcode` | defaults |
| `high_contrast` | `#000000` | `#FFFFFF` / `#C9CED6` | `#FF7A7A`, `#FFE14D`, `#4DD2FF`, `#FFAA4D`, `#7EE787` | `#141414` | `#4DD2FF`, `#FFAA4D`, `#D7A8FF`, `#7EE787` | `github-dark` | `caption: 26`, `small: 24` |

All presets use the font Inter. Every built-in preset passes WCAG AA (tested): `text` and
`dim` at least 4.5:1 on the background and on `surface`, the accent tokens and the palette at
least 3:1 on the background (`high_contrast`: 7:1 for all of them). Projects can add their own
presets (e.g. a brand look based on `light_academic`) with `register_theme_preset` in an
extension (docs/EXTENDING.md); `vidgen validate` reports an unknown preset name, and
`vidgen schema` lists the built-in and the project's presets.

Changed in Step 16: the default `dim` is `#838B98` (was `#6B7280`, 3.9:1 on the default
background, below WCAG AA); dim captions, axis labels and sources are a little lighter.

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
The heading sits in the `header` region, the list is centered in the space below it. In a
vertical video the heading is 1.3x larger and a short list grows up to 1.3x and spreads out to
use the taller frame.

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
Manim's `Code` (Pygments highlighting); the listing is scaled to fill the space below the
title. When its width would make it smaller than `size` (typical for long lines in a vertical
video), long lines are wrapped with a hanging indent (`wrap`); wrapped lines keep their line
number and highlights still count original lines.

| param | type | default | |
|---|---|---|---|
| `code` | str | — | inline code; give exactly one of `code` / `path` |
| `path` | str | — | file in the project (checked by `vidgen validate`) |
| `language` | str | from the file name, else `python` | a Pygments lexer name |
| `title` | str | `""` | |
| `highlight` | list of line specs | `[]` | entry *i* applies at beat *i*: `3`, `"2-4"`, `"1, 5-6"` or `[1, 4]` (1-based) |
| `line_numbers` | bool | `true` | |
| `style` | str | theme `code_style` | a Pygments style (`monokai`, `dracula`, `xcode`, ...); default: the theme's `code_style` (`github-dark`, `xcode` in `light_academic`) |
| `font` | str | `Monospace` | monospace font family (e.g. `Consolas` on Windows) |
| `size` | size | `caption` | starting font size (scaled to fill the frame, up to 1.5x) |
| `highlight_color` | color | `highlight` | |
| `wrap` | bool | `true` | wrap long lines instead of shrinking the listing below `size` / the readable minimum |

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

## JSON Schema (`vidgen schema`)

`vidgen schema [PROJECT]` prints a [JSON Schema](https://json-schema.org) (draft 2020-12) of
`video.yaml` for the project's scene types: the built-ins plus its extensions (without a
PROJECT and no config file in the current folder: the built-ins only). Editors (e.g. the YAML
language server: `# yaml-language-server: $schema=video.schema.json` on the first line) and AI
agents can check a config with it before running `vidgen validate`:

```
vidgen schema > video.schema.json          # the whole config
vidgen schema --scene bar_chart            # one scene type's params
vidgen schema --all                        # one item of `scenes`, with every type's params
```

What the schema checks: every key and type of this reference (unknown keys are errors);
`scenes[].type` is one of the registered types and `scenes[].params` is checked against that
type's params (`if`/`then` per type: required params, types, `Literal` values, ranges, nested
models); a type's fixed beat count (`minItems`/`maxItems` of `beats`); the silent-scene rule
(`duration` exactly when there are no beats); even `width`/`height`; and the bodies of
`variants` (partial configs: the same keys, none required). Color and size params accept a
`#hex` color / a positive number or a token name of the project's theme (defaults, extension
defaults, `theme.colors`/`theme.sizes` of the base config and of every variant); such
properties carry `"x-vidgen-theme": "color"` or `"size"`. `theme.preset` is an enum of the
built-in presets and those the project registers, `theme.code_style` of the installed Pygments
styles. Descriptions come from the field docs (the same text as `doc` in
`vidgen list-scenes --json`).

What only `vidgen validate` checks: unique scene and beat ids, files referenced by params
(images, code, logos), the checks written in Python (`validate_project`, pydantic validators,
e.g. "values has one entry per label") and loading the extensions. A schema-valid config can
still fail `vidgen validate`. The reverse happens only for values vidgen converts, such as
the string `"30"` for a number: write values with their real type (tests check both
directions on the examples and on common mistakes).

The schema is generated for the project as it is now: regenerate it after adding scene types,
theme tokens or variants. If `video.yaml` is invalid, `vidgen schema` still works (that is
when it is most useful): it uses the file's `extensions` and `theme` as far as they are valid
and prints a warning. `--scene` with an unknown type is an error (exit code 1).

## Frame stills (`vidgen render --frames`)

`vidgen render --frames` also saves PNG stills of the render, so you (or an AI agent, which
cannot watch a video) can check what is on screen without playing it. `--frames` takes one
still per beat: its **last frame**, i.e. what is on screen when the narration of the beat (and
its `narration.pad`) is over. `--frames-per-beat N` takes N evenly spaced stills per beat, the
last one again at the end (N=3: after a third, two thirds and all of the beat). A silent scene
counts as one beat lasting `duration` minus the scene's fade-out, so its last still is taken
before the fade. Stills are off by default; they work with `--preview`, `--variant`, `--scene`
and `--jobs`. They are taken from Manim's renderer while it writes the video (the same pixels
as the video frame, before compression), so they do not change the video or its timings.

Files, in `build/<final|preview>[_<variant>]/frames/`:

```
frames/
  index.json            # every still of the video
  <scene>/
    index.json          # the scene's stills
    <beat>-<k>.png      # still k (1..N) of a beat; <scene>-<k>.png for a silent scene
```

`<scene>/index.json`: `{scene, per_beat, width, height, fps, frames}`; `frames` lists, in time
order, `{beat, k, n, frame, time, path}`: the beat id (`null` for a silent scene), the still's
number within its beat (`k == n` is the end of the beat), `n` = stills per beat, the frame's
0-based index in the scene's video, its time in seconds from the scene start (`frame / fps`)
and the PNG file name.

`frames/index.json`: `{title, variant, preview, format, per_beat, vidgen, scenes}`; each scene
is `{id, start, duration, frames}` (`start` in the video) and each still is as above with
`time` in the **video** (scene start + time in the scene), `scene_time` (time in the scene)
and `path` relative to `frames/` (`<scene>/<file>.png`); each scene also has `layout`, its
layout file relative to `frames/` (`../layout/<scene>.json`, see below) and `activity`, its
activity file (`../activity/<scene>.json`, see below). The beat texts are in
`build/.../timings.json`.

Every scene render deletes the scene's old stills, and every `vidgen render` deletes
`frames/index.json` (it is rewritten when stills are requested), so stills never belong to an
older render. With `--scene ID --frames`, scenes that would be reused but have no stills at
this count are rendered again.

## Layout dump (`build/.../layout/<scene>.json`)

Whenever stills are taken (`--frames`, `--frames-per-beat N`, `vidgen storyboard`), the same
frames are also described as data: for each still, every **visible** object on screen with its
position in pixels, size, colours and opacity: the input of [`vidgen lint`](#lint-vidgen-lint)
(text off the frame or outside the safe area, overlapping text, text too small, low contrast,
too many words); you or an agent can read it directly too. It costs a few milliseconds per still and is deleted
and rewritten with the stills, so it always describes the current render.

File `build/<final|preview>[_<variant>]/layout/<scene>.json`:

```
{version: 1, scene, type, width, height, fps, per_beat,
 px_per_unit,              # output pixels per Manim unit (camera not zoomed)
 background: "#0E1116",    # the theme background
 safe_area: [x0, y0, x1, y1],  # frame minus the scene's margins (margin_x/margin_y), in px
 frames: [{beat, k, n, frame, time,     # the same keys as the stills index
           still: "../frames/<scene>/<file>.png",
           camera: {center: [x, y], width, height},   # the camera frame in Manim units
           objects: [...]}]}
```

Coordinates are output-frame pixels: origin at the top-left corner, y downwards, the frame
spans `[0, width] x [0, height]`; boxes are `[x0, y0, x1, y1]` (1 decimal) and may lie partly or
wholly outside the frame. A moving or zoomed camera (`MovingCamera`) is taken into account.

Each object:

| key | meaning |
|---|---|
| `id` | `m1`, `m2`, ...: the same Python object keeps its id in every frame of the scene |
| `kind` | `text` (`Text`, `MarkupText`, `Paragraph`), `code` (the text of a `Code` listing), `math` (`Tex`, `MathTex`), `number` (`DecimalNumber`, `Integer`), `shape` (one path), `group` (a group of shapes with no text or image inside, e.g. an axis' ticks), `image` |
| `class` | the Manim class |
| `path` | where it sits: parent groups from the top-level mobject down, each `Class[index]` (index among its parent's submobjects; top level: in the scene), or the name the scene gave it |
| `name` | the scene attribute that holds it (`self.title = ...`) or a `Mobject.name` set by the scene, else `null` |
| `bbox` | the box of its visible parts, stroke included |
| `opacity` | the highest opacity of its visible parts (fill, or stroke when it has one); a fade-in in progress shows here |
| `z`, `order` | Manim `z_index`, and the drawing position (higher is drawn later, i.e. on top) of its top-most part |
| `parts` | number of visible parts (glyphs, paths) |
| text kinds only: `text` | the characters (markup tags removed; the LaTeX source for `math`) |
| `font_px` | the 75th percentile of its visible glyphs' heights in output pixels: about the cap height (≈ 0.7 em) for mixed-case text, the x-height for lowercase text without ascenders |
| `color`, `colors` | the most common glyph colour, and all of them (most common first) |
| `backdrop` | the most common colour of the frame inside its box, ignoring its own colours: what the text is read against (`null` when off-frame) |
| other kinds: `fill`, `stroke` | `{color, opacity}` / `{color, opacity, width_px}` of the largest visible part, or `null` |

An object is one text mobject (not one per glyph), one path, one image, or one group of shapes.
Parts with opacity 0 are not visible: they do not count in the box, and an object with no
visible part is not listed. `text` is the string the mobject was created with; Manim's
`become()` and `Transform` change the glyphs but not that string, and while
`TransformMatchingShapes`/`TransformMatchingTex` run, the moving glyphs are shapes.

## Activity file (`build/.../activity/<scene>.json`)

Written with the stills and the layout dump (and deleted with them): what happens in the scene
over time, the input of `vidgen lint`'s timing rules. Recording it costs about 1.3 ms per
frame of the render (a sampled comparison with the previous frame).

```
{version: 1, scene, type, fps,
 frames, duration,         # frames written, seconds
 pad,                      # narration.pad
 silent: {duration, busy} | null,   # silent scene: its duration, and how long its code ran
 beats: [{id, start, end,  # scene seconds; end = start + narration length d
          busy,            # seconds the beat's own code (animations, waits) took; more than
                           # d + pad means the beat ran past its narration
          source,          # "audio" (d from the MP3) or "estimate" (from the word count)
          text}],
 plays: [{start, end, beat, animations: ["Write", ...], wait, requested}],
 motion: {step, grid: [w, h], level, changes: [[frame, fraction], ...]}}
```

`plays` lists every `self.play(...)` and `self.wait(...)` (`wait: true`) with the beat being
narrated (`null` outside `narrate`) and the animations' class names (`animate` for
`mobject.animate`, groups with their parts); `requested` is the run time `play_steps` wanted
when it had to shorten an animation to fit the beat, else `null`. `motion.changes` lists the
frames that differ from the previous frame: `fraction` is the part of the frame's sample points
(every `step`-th pixel, `grid` points, at most 180 on the shorter side) whose colour changed by
more than `level` (0-255); frames not listed are identical to the one before.

## Lint (`vidgen lint`)

`vidgen lint [PROJECT]` checks what is on screen at the **end of every beat**, and how the
scenes play over time, and reports problems an author cannot see without watching: text cut
off by the frame edge or in the margins, overlapping text, shapes drawn over text, text too
small for the frame, low contrast and too many words at once (**layout rules**); narration too
fast or too slow, nothing moving for a long time, animations running past their narration or
squeezed into a too short beat (**timing rules**). It reads the
[layout dump](#layout-dump-buildlayoutscenejson) of the beat-end stills and each scene's
[activity file](#activity-file-buildactivityscenejson); scenes whose stills are current (from
`vidgen render --frames` or `vidgen storyboard`, any `--per-beat`) are reused, the others are
rendered first with one still per beat (preview format unless `--final`; reuse works as for
the [storyboard](#storyboard-vidgen-storyboard)). Only beat-end stills are checked by the
layout rules: mid-beat stills show animations in progress (half-faded or moving objects),
which would only add noise.

```
$ vidgen lint examples/minimal
lint: 10 scenes, 23 beat-end stills (preview 854x480)
picture:
  warning safe_area         picture_b2 @ 7.2s: text 'Images can slowly zoom and pan' is outside the safe area at the bottom (12 px into the bottom margin)
          still: examples/minimal/build/preview/frames/picture/picture_b2-1.png
0 errors, 7 warnings, 0 info
```

Each finding names the scene, the beat at whose end it was seen (`+N more beats` when the same
problem stays on screen), the rule, a message with the measured value and the limit, and the
**still** to open to see it. Timing findings name the beat concerned and the scene time where
the problem starts; their still is the end of that beat. The same problem with several objects of one group (an axis' tick
labels, several texts in the same colour) is reported once (`also N more like it`).

Options:

| option | |
|---|---|
| `--scene ID` | only this scene (repeatable) |
| `--rule NAME` | only this rule (repeatable) |
| `--variant NAME` | lint a variant (e.g. the vertical one) |
| `--preview` / `--final` | preview format (the default) or the final format |
| `--fail-on SEVERITY` | `error`, `warning`, `info` or `never`; overrides `lint.fail_on` |
| `--jobs N` | scenes rendered in parallel |
| `--force` | render the selected scenes again even if their stills are current |
| `--json` | print every finding as JSON (below) |

**Exit code**: 1 when a finding is at least as severe as `fail_on` (default `error`), else 0;
with `--fail-on never` it is 0 whatever is found (and 1 only if the command itself fails).

**Rules.** Sizes are fractions of the frame's **shorter side** (the height of a landscape
video, the width of a vertical one), so the same thresholds hold for the 480p preview and the
1080p video, and for 16:9 and 9:16 (a phone shows either orientation with its shorter side
across the screen's width). Objects fainter than `lint.min_opacity` are ignored by every rule.

| rule | default severity | finds |
|---|---|---|
| `off_frame` | error for text, warning for other objects | an object cut off by the frame edge by more than `tolerance`. Not reported: objects wholly outside (not visible), and non-text objects running from edge to edge on the side they cross (a full-frame image with `fit: cover` or Ken Burns, a background, a band or divider): those bleeds are intentional |
| `safe_area` | warning | text inside the frame but in its margins (the scene's `margin_x`/`margin_y`, `safe_area` in the layout dump) by more than `tolerance` |
| `text_overlap` | error | two texts whose boxes overlap by at least `min_overlap` of the smaller box (the same text drawn twice in the same place is not reported) |
| `covered_text` | warning | a shape or image drawn **after** (on top of) a text whose colour shows in at least `min_covered` of the middle of the text's box, measured on the still's pixels. Not reported: shapes drawn before the text (plates, highlight bands, a code window), the text's own parent group, shapes fainter than 0.3, and shapes in the text's own colour (a strike-through) |
| `min_font` | warning; error below `error_size` | text whose cap height is below `min_size` of the shorter side. The cap height is the layout's `font_px` corrected for the text's letters (`font_px` of all-lowercase text is about its x-height); a lone symbol (`+`, `·`) is not checked |
| `contrast` | warning | text whose WCAG contrast ratio with its `backdrop` is below `min_ratio` (4.5, WCAG AA), `large_ratio` (3) for text with a cap height of at least `large_size`, or `dimmed_ratio` (2) for text faded on purpose (opacity below 1, e.g. previous bullets); the text colour is blended with the backdrop at the text's opacity, every colour of a multi-coloured text is checked. A code listing's line numbers are not checked |
| `max_words` | warning | more than `max_words` words (tokens with a letter) of visible `text` objects in one still; code and math do not count |
| `narration_speed` | warning; info without audio | a beat (of at least `min_words` spoken words) narrated at fewer than `min_rate` or more than `max_rate` words per second. With an MP3 the time is the speech in it (leading and trailing silence below -40 dB of its peak cut off). Words count as spoken: hyphens, dashes and slashes separate words (`K-Phi-3` is 3), a number counts one word per digit up to 3 per digit run, plus one per decimal point and symbol (`2.58` is 4, `15%` 3), an all-capitals acronym of 2-5 letters half a word per letter (`GPU` 1.5). **Without audio** the beat's length is the word-count estimate (`narration.words_per_second`), so the rate is only off when the text is (many numbers or acronyms) or the configured rate itself is implausible: reported as `info`, one finding per scene listing the beats |
| `dead_air` | warning | nothing on screen changes for more than `max_seconds` (a frame counts as changed when at least `min_change` of it changed, from the activity file's `motion`), narrated or not; the finding names the beat where the still picture starts and the beats it lasts through. Silent scenes are checked the same way: a silent card held longer than `max_seconds` without motion is reported |
| `animation_overrun` | warning | a beat whose code (animations and waits inside `narrate`) takes longer than its narration plus `narration.pad` by more than `tolerance` seconds: the next beat (and its audio) starts late, leaving silence. The message lists the animations still running when the narration ends. A silent scene whose animations take longer than its `duration` is reported the same way |
| `rushed_animation` | warning | animations that `play_steps` (and so `reveal` and most built-in scenes) had to shorten below `min_run_time` seconds because the beat is too short for its steps |

**Config** (all optional; the values shown are the defaults):

```yaml
lint:
  fail_on: error              # error | warning | info | never: lowest severity that fails
  min_opacity: 0.1            # objects fainter than this are ignored (end of a fade)
  rules:                      # each rule also takes severity: error | warning | info | off
    off_frame: {tolerance: 0.004}           # fraction of the shorter side (2 px at 480p)
    safe_area: {tolerance: 0.01}            # 5 px at 480p
    text_overlap: {min_overlap: 0.1}        # fraction of the smaller box
    covered_text: {min_covered: 0.02}       # fraction of the middle of the text's box
    min_font: {min_size: 0.025, error_size: 0.018}   # cap height: 12 / 8.6 px at 480p, 27 / 19.4 px at 1080p
    contrast: {min_ratio: 4.5, large_ratio: 3.0, large_size: 0.045, dimmed_ratio: 2.0}
    max_words: {max_words: 40}
    narration_speed: {min_rate: 1.8, max_rate: 3.5, min_words: 5}   # spoken words per second
    dead_air: {max_seconds: 6.0, min_change: 0.0002}   # min_change: fraction of the frame
    animation_overrun: {tolerance: 0.1}     # seconds past narration + pad
    rushed_animation: {min_run_time: 0.5}   # seconds
```

`severity` on a rule sets the severity of all its findings (`off` disables the rule). The
`lint` section and `lint_ignore` do not count in a scene's render fingerprint: changing them
never makes stills stale.

**Ignoring findings in a scene** (`lint_ignore` on the scene): a list of rule names (or `all`),
or `{rule, object, beat}` filters. `object` is a pattern (`*` and `?` wildcards, case-sensitive)
matched against the object's `name`, `path` and `text` (for a pair, either object); `beat`
limits the entry to the end of that beat (it must be a beat of the scene).

```yaml
scenes:
  - id: chart
    type: line_chart
    params: {...}
    lint_ignore:
      - max_words                                   # every max_words finding of this scene
      - {rule: min_font, object: "VGroup[2]/*"}     # the small tick labels, by path
      - {rule: contrast, object: "Illustrative*", beat: chart_b2}
```

## Storyboard (`vidgen storyboard`)

`vidgen storyboard [PROJECT]` writes **contact sheets**: PNG pages showing the stills of the
video in a grid, each labelled `beat @ time` with the beat's narration under it and a header
band per scene (`N/M  id · type · start–end (duration)`). It is the way to *look* at a video
without watching it, and is made for AI agents that open the PNG with an image viewer: pages
are 1280 px wide (`--width PX`, 640–2000) and at most about 1.25 times as high, the font sizes
grow with the width, long narration is wrapped and cut with `…`, and long videos are split into
several pages instead of one huge image. 16:9 videos get 4 stills per row (2 on a scene's
sheet), 9:16 videos 5 (4); with `--per-beat N` a beat's stills stay side by side on one row.

Files, in `build/<preview|final>[_<variant>]/storyboard/`:

```
storyboard/
  video-1.png, video-2.png ...   # the whole video (times in the video, m:ss.s)
  scenes/<scene>-1.png ...        # one scene, larger stills (times from the scene start)
```

Options:

| option | |
|---|---|
| `--scene ID` | only this scene's sheet (repeatable); no `video-*.png` is written (old ones are deleted) |
| `--per-beat N` | N stills per beat, evenly spaced, the last at the beat's end (default 1: the end of each beat) |
| `--variant NAME` | storyboard a variant (e.g. the vertical one) |
| `--preview` / `--final` | preview format (the default) or the final format |
| `--width PX` | page width (default 1280) |
| `--jobs N` | scenes rendered in parallel |
| `--force` | render the selected scenes again even if their stills are current |
| `--json` | print the sheets and the stills on each (below) |

**What gets rendered.** The sheets are built from the stills of `vidgen render --frames` (see
above). A scene is rendered again (with stills, in worker processes like `vidgen render`) only
if its stills are missing, were taken at another `--per-beat` count or format, or are stale:
each render records a fingerprint of what the scene depends on (its config entry, the other
config sections except `scenes`/`variants`/`lint`, its beats' MP3s, the project's extension code,
the files under `assets/`, and vidgen's own rendering code), and a scene whose fingerprint
changed is rendered again. So `vidgen storyboard` right after `vidgen render --preview
--frames` renders nothing, and after an edit it renders only the edited scenes. Files a scene
reads from outside `assets/` are not tracked: use `--force`. The storyboard does not join the
video; `vidgen render` does. It dispatches `post_scene` for the scenes it renders, not
`pre_render`/`post_render`.

## JSON output (`--json`)

`vidgen validate`, `vidgen list-scenes`, `vidgen render`, `vidgen schema`, `vidgen storyboard` and `vidgen lint` accept `--json`: stdout then holds
exactly one JSON document (ASCII-only, non-ASCII characters escaped), and everything else
(progress, `warning:` lines, Manim output) goes to stderr. These shapes are meant for programs
and AI agents driving vidgen. Without `--json` the human output is unchanged.

**Stability.** `version` is the version of these shapes (currently **1**), not of vidgen. Keys
are only added within a version; removing or renaming a key or changing a value's type bumps
it. Times are seconds (floats), paths are absolute strings, absent values are `null`.

**Envelope** (every document, success or failure):

| key | type | |
|---|---|---|
| `version` | int | schema version of the document (1) |
| `vidgen` | str | vidgen package version |
| `command` | str \| null | `validate`, `list-scenes`, `render`, `schema`, `storyboard`, `lint` (`null` if the command line could not be parsed) |
| `ok` | bool | `true` on success; the exit code is 0 exactly when `ok` is true |
| `warnings` | list | `{scene, message}`: vidgen warnings of the run (`scene` is `null`, or the scene whose render printed it) |
| `error` | object | only when `ok` is false: `{kind, message, problems, details}` |

**Errors.** `error.kind` is `usage` (bad command line; exit code 2), `error` (something the user
can fix: config, missing file, unknown scene, failed scene...; exit code 1) or `internal` (an
unexpected exception; exit code 1, `details.traceback` holds the traceback). `message` is the
text the human output prints after `error: `. `problems` lists config problems as
`{location, message, variant}` (`location` is a config path such as `scenes[2].params.title`,
or `null` when the problem is not about one value, e.g. an extension that fails to import;
`variant` is the variant whose merged config has the problem, `null` for the base config).
`details` is an object, empty unless stated below.

```json
{"version": 1, "vidgen": "0.1.0", "command": "render", "ok": false, "warnings": [],
 "error": {"kind": "usage", "message": "unrecognized arguments: --bogus", "problems": [], "details": {}}}
```

### `vidgen validate --json`

Always a validate document (also when the project cannot be loaded); exit code 1 if there is
any problem. Unlike the human output, a variant whose config does not load is reported as
problems (with its `variant`) and the other variants are still checked.

| key | type | |
|---|---|---|
| `project`, `config_file` | str \| null | project folder and config file (`null`: the project could not be loaded) |
| `title` | str \| null | |
| `scenes`, `beats` | int \| null | counts in the base config |
| `estimated_duration` | float \| null | seconds, from word counts + `narration.pad` + silent scenes' `duration` |
| `variants` | list | every variant checked: `{name, loaded, estimated_duration, problems}` (`problems`: how many are this variant's own) |
| `problems` | list | `{location, message, variant}` (as in `error.problems`); empty when the project is valid |
| `audio` | list | one per audio folder (the base config's, plus each variant with its own, see [variant audio](#narration-audio-elevenlabs)): `{variant, dir, ok, stale, missing, orphaned, beats}`; `ok`/`stale`/`missing` are counts, `orphaned` the paths of MP3s no beat uses, `beats` lists `{scene, beat, state}` in video order with `state` `ok`, `stale` or `missing` |

When there are problems, `error` is `{"kind": "error", "message": "video.yaml: invalid
project ...", "problems": [same list], "details": {}}`. Problem `message`s are the text after
the location in the human output (`scenes[1].type: unknown scene type 'titel'; did you mean
'title'? ...` → `location` `scenes[1].type`).

### `vidgen list-scenes --json`

| key | type | |
|---|---|---|
| `project` | str \| null | the project whose extensions were loaded (`null`: built-ins only) |
| `scene_types` | list | sorted by name, as below |

Each scene type: `name`; `origin` (`builtin`, or the extension file relative to the project);
`builtin` (bool); `overrides_builtin` (bool, an extension registered with `override=True`);
`doc` (the class docstring, else its module's, or `null`); `beats` (`null` = any number, else
`{min, max, text}` with `max` `null` for no upper limit, e.g. `{"min": 2, "max": 2, "text":
"exactly 2 beats"}`); `params` (`null` = free-form params, else a list of fields).
Each field: `name`; `type` (readable type as in the human listing: `str`, `list[str]`,
`color`, `size`, `'all' | 'per_beat'`, ...); `required` (bool); `default` (JSON value, `null`
when required); `doc` (the docstring under the field or its `Field(description=...)`, or
`null`); `nested` (fields of `SceneParams` models used in the type, as `{model, fields}`).

### `vidgen schema --json`

| key | type | |
|---|---|---|
| `project` | str \| null | the project whose scene types were used (`null`: built-ins only) |
| `schema` | object | the JSON Schema that `vidgen schema` prints without `--json` |

`warnings` includes the warning about an invalid `video.yaml` (see
[JSON Schema](#json-schema-vidgen-schema)).

### `vidgen render --json`

| key | type | |
|---|---|---|
| `project` | str | |
| `variant` | str \| null | |
| `preview` | bool | |
| `audio` | bool | `false` with `--no-audio` |
| `format` | object | `{width, height, fps}` of this render |
| `outputs` | object | `{video, subtitles, timings, frames}`: the MP4, the SRT, `build/.../timings.json` and `build/.../frames/index.json` (`null` without `--frames`) |
| `duration` | float | length of the video |
| `elapsed` | float | wall time of the command |
| `scenes` | list | config order: `{id, type, status, start, duration, render_seconds, beats}`; `status` is `rendered` or `reused` (an existing render was joined, see `--scene`), `render_seconds` the worker's wall time (`null` when reused), `start`/`duration` in the video, `beats` lists `{id, start, end}` (absolute; `end` excludes `narration.pad`) |

`warnings` includes those printed by scene code during rendering (e.g. beats a scene never
narrated), with their `scene`. On failure, `error.details` is `{failed, rendered}`: `failed`
lists `{scene, exit_code, output_tail}` (the last 60 lines of the worker's output; exit code 1
for a vidgen error, 2 for an exception in scene code), `rendered` the scene ids rendered before
(or, with `--keep-going`, besides) the failures.

### `vidgen storyboard --json`

| key | type | |
|---|---|---|
| `project` | str | |
| `variant` | str \| null | |
| `preview` | bool | `false` with `--final` |
| `per_beat` | int | stills per beat |
| `format` | object | `{width, height, fps}` of the stills |
| `folder` | str | the `storyboard/` folder |
| `rendered` | list | ids of the scenes rendered by this command (config order) |
| `reused` | list | ids of the selected scenes whose current stills were reused |
| `elapsed` | float | wall time of the command |
| `sheets` | list | every page written: `{kind, scene, page, pages, path, width, height, frames}`; `kind` is `video` (the whole video, `scene` is `null`) or `scene`; `page` of `pages` (1-based); `width`/`height` in px; `frames` lists the stills on the page in order: `{scene, beat, k, n, time, scene_time, path}` (`beat` `null` for a silent scene, `k` of `n` stills of the beat, `time` in the video or `null` when not every scene has a render at this format, `scene_time` from the scene start, `path` the still's PNG) |

Video sheets come first, then the scene sheets in config order. `warnings` and `error.details`
on a failed scene are as for `vidgen render --json`.

### `vidgen lint --json`

`ok` is false (exit code 1) when a finding is at least as severe as `fail_on`; `error` is then
`{"kind": "error", "message": "lint found 1 error, 3 warning, 0 info (fails on error or worse)",
"problems": [], "details": {"fail_on", "counts"}}` and the findings are still in the document.

| key | type | |
|---|---|---|
| `project` | str | |
| `variant` | str \| null | |
| `preview` | bool | `false` with `--final` |
| `format` | object | `{width, height, fps}` of the stills |
| `fail_on` | str | `error`, `warning`, `info` or `never` |
| `rules` | list | names of the rules run |
| `scenes` | list | ids of the scenes checked (config order) |
| `stills` | int | beat-end stills checked |
| `rendered`, `reused` | list | scene ids rendered for this command / whose current stills were reused |
| `elapsed` | float | wall time of the command |
| `counts` | object | `{error, warning, info}`: findings per severity |
| `ignored` | int | findings skipped by `lint_ignore` |
| `findings` | list | in scene order, then by time and severity, as below |

Each finding: `scene`; `beat` (the beat at whose end it was seen, `null` for a silent scene);
`time` (in the video, `null` when not every scene has a render at this format) and
`scene_time` (from the scene start); `rule`; `severity` (`error`, `warning`, `info`);
`object` (the object concerned, `null` for `max_words` and the timing rules) and `other` (the second object of a
pair: the other text for `text_overlap`, the shape for `covered_text`; else `null`), each
`{id, kind, class, name, path, text, bbox}` as in the [layout dump](#layout-dump-buildlayoutscenejson)
(`text` `null` for shapes); `similar` (further objects with the same problem, reported with
this one, e.g. the other tick labels); `bbox` (the region to look at in the still, px:
the object, the overlap of a pair, or all counted texts); `message`; `value` and `limit` (the
measured number and the threshold it broke: a fraction of the shorter side for sizes, a ratio
for contrast, px for `off_frame`/`safe_area`, a word count, words per second for
`narration_speed`, seconds for the other timing rules); `beats` (every beat end where the
same problem was seen, the first is `beat`); `still` (the PNG at `beat`'s end; `null` if the
scene has none). Timing findings have `bbox` `null` and `time`/`scene_time` where the problem
starts (the beat's start, the start of the still stretch, the narration's end, the first
rushed animation).
