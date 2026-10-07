# vidgen config reference

A project is a folder with one config file: `video.yaml` (or `video.yml` / `video.json`), UTF-8.
Unknown keys are an error everywhere except inside `params`, `theme.colors`, `theme.sizes` and
the bodies of `variants`, so typos are caught by `vidgen validate`. Paths are relative to the
project folder. Contents: [top level](#top-level), [scenes and beats](#scenes-and-beats),
[format](#format-and-preview), [variants](#variants), [theme](#theme), [voice](#voice-voice),
[narration](#narration-narration), [narration audio](#narration-audio-elevenlabs),
[built-in scene types](#built-in-scenes), [beat actions](#beat-actions), [overlays](#overlays),
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
| `overlays` | `[]` | lower thirds, a watermark, ... drawn over the scenes, see [overlays](#overlays) |
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
        actions: []           # optional per-beat actions on the scene's targets (see "Beat actions")
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
| `overlays` | `true` | the video's [overlays](#overlays) on this scene: `false` for none, or per overlay id `false` / option overrides, or an overlay of this scene only |
| `chapter` | none | a new [chapter](#chapters) starts at this scene: its title, or `{title, number}` |

Beat `id`s name the audio files: keep them when you edit the text (only that beat is
re-voiced). A beat `text` is spoken as written; it is also the subtitle. A beat's `actions`
(default `[]`) point at parts of the scene while it is spoken — reveal, dim, highlight — see
[beat actions](#beat-actions).

## Chapters

A video can be divided into chapters. A chapter starts at every [`chapter`](#chapter) scene (its
`title` and `number` params) and at every scene with a `chapter:` key, which marks a new chapter
without a divider card:

```yaml
scenes:
  - id: intro                 # before the first chapter: no chapter
    type: title
    params: {title: "Engines"}
    beats: [{text: "..."}]
  - id: part1
    type: chapter             # a divider card starts chapter 1 "Setup"
    params: {number: 1, title: "Setup"}
    duration: 3
  - id: data                  # still chapter 1
    type: text_card
    params: {text: "Data"}
    beats: [{text: "..."}]
  - id: results
    type: bullets
    chapter: Results          # chapter 2 starts here, no card (long form: {title: Results, number: 2})
    params: {heading: "Results", items: ["Faster", "Smaller"]}
    beats: [{text: "..."}]
```

| key | default | |
|---|---|---|
| `title` | required | the chapter's name (the short form `chapter: Results` gives only this) |
| `number` | none | its number as shown (an integer, or text like `"Part II"`); without one, indicators show its position (1, 2, ...) |

On a `chapter` scene, `chapter:` renames the chapter in lists and indicators (e.g. a shorter
title than the card's) and keeps the card's number unless it gives one. A chapter lasts until
the next one starts (the last until the video's end). `vidgen validate` rejects the same
chapter twice (same title and number; a card starts its chapter by itself, the scenes after it
need no `chapter:`), integer numbers that do not increase, and a scene with `chapter:` right
after a chapter card (the card would be a chapter of its own; give the card the `chapter:`
instead). The [`progress_bar`](#progress_bar) marks chapters, the
[`chapter_indicator`](#chapter_indicator) names the current one; extensions read the list with
`video_chapters(project)` (docs/EXTENDING.md).

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
  font: Inter               # sans family: body text and every role not set below (bundled)
  font_serif: Source Serif 4  # serif family, the `serif` font token (bundled)
  font_mono: JetBrains Mono NL  # monospace family, the `mono` token: code listings (bundled)
  fonts: {heading: serif}   # optional: font per role (see "Fonts" below)
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
  scale: auto               # type scale: compact, standard, large or auto (see below)
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
looks exactly as before. `vidgen list-themes` shows every preset with its values (below), and
`vidgen validate` warns (without failing) when the project's own theme has a colour pair below
WCAG AA (`warning: theme contrast: colors.dim #6B7280 on background #0E1116: 3.91:1 (needs
4.5:1, too low)`; same check as the presets' tests, see below).

### Fonts

vidgen ships three open-licence font families (SIL OFL 1.1; licences in
`src/vidgen/data/fonts/`, list in `THIRD_PARTY_NOTICES.md`) and registers them for its own
renders, so they need **no installation** on Windows, macOS or Linux: **Inter** (sans; Regular,
Bold, Italic), **Source Serif 4** (serif; Regular, Bold, Italic) and **JetBrains Mono NL**
(monospace without coding ligatures, so code shows the characters as typed; Regular, Bold).
Any installed font works too: write its family name (`font: Segoe UI`). A bundled family that is
also installed system-wide is fine (either copy is used; they are the same font).

The theme has three family tokens: `font` (sans; default Inter), `font_serif` (default Source
Serif 4) and `font_mono` (default JetBrains Mono NL). Built-in scenes ask for a font by
**role**, and `fonts` maps a role to a token — `sans`, `serif`, `mono` — or directly to a family
name:

| role | used for | default |
|---|---|---|
| `body` | all other text (subtitles, bullets, captions, labels...) | `sans` |
| `heading` | `title` title, `bullets` heading, chart and `code` titles, `end_card` title | `sans` (`serif` in `light_academic`, `warm_editorial`) |
| `quote` | `quote` text | `sans` (`serif` in `warm_editorial`) |
| `quote_mark` | the large mark of `quote` | `serif` |
| `code` | `code` listings and their line numbers | `mono` |

```yaml
theme:
  preset: warm_editorial
  font_serif: Georgia            # an installed serif instead of the bundled one
  fonts: {quote: sans, heading: "Playfair Display"}   # roles: token or family name
```

`fonts` merges over the preset's roles per role; extension scenes can use any role name
(`current_theme().font_for("kicker")`, unknown roles are `sans`). A scene's own font param
(`code.font`, `quote.mark_font`) wins over the role.

Changed in Step 18: `font` is the sans family; a `font` written in `video.yaml` no longer
overrides the roles a preset sets (headings of `light_academic` stay serif; write `fonts:
{heading: sans}` for all-sans). `code` listings use JetBrains Mono NL (was the system's
`Monospace`), the quote mark Source Serif 4 (was Georgia / DejaVu Serif).

### Type scales

`scale` sets the six built-in sizes at once (font points):

| scale | `title` | `subtitle` | `heading` | `body` | `caption` | `small` | for |
|---|---|---|---|---|---|---|---|
| `compact` | 48 | 36 | 32 | 28 | 22 | 20 | dense slides, long lists |
| `standard` | 56 | 42 | 36 | 32 | 24 | 20 | 16:9 video (the defaults) |
| `large` | 66 | 50 | 44 | 38 | 30 | 26 | vertical/mobile video, accessibility |
| `auto` | | | | | | | `large` when the video (`format`) is portrait (taller than 1:1.2), else `standard` |

A scale is shorthand for those six `sizes` at the level where it is chosen: `theme.sizes`
still override single sizes (`{scale: large, sizes: {title: 60}}`), a `scale` written under
`theme:` replaces the preset's scale (and its `sizes` for those six tokens), and a preset's own
`sizes` sit above its scale. Without any `scale` (in the config or the preset) the default is
`auto`, so a `vertical` variant (`format: {width: 1080, height: 1920}`) automatically gets the
larger text a phone needs, while 16:9 output is unchanged; write `scale: standard` to keep
the old sizes in portrait. `auto` follows the variant's final `format` (a `--preview` render
uses the same sizes, so previews show the final layout). Text never overflows because of a
scale: built-in scenes fit text into their regions (wrapping, then shrinking).

Changed in Step 17: portrait projects without a scale get `large` sizes (`auto`), and
`high_contrast` uses `large` (was `caption: 26`, `small: 24`).

### Theme presets

`theme: {preset: NAME}` selects a named set of values; anything else under `theme:` still
wins, so `{preset: light_academic, colors: {primary: "#0B5FFF"}}` is the light look with your
blue. A variant can switch presets: `variants: {light: {theme: {preset: light_academic}}}`.
Mind that values written in the base `theme:` also override the variant's preset (a base
`background: "#0E1116"` would keep a light variant dark): write in the base only what every
variant shares, or select the default look with `preset: dark_tech` there instead.

| preset | background | text / dim | accents (`accent`, `highlight`, `primary`, `secondary`, `tertiary`) | `surface` | palette | `code_style` | scale |
|---|---|---|---|---|---|---|---|
| `dark_tech` (the default look) | `#0E1116` | `#E8EAED` / `#838B98` | `#FF6B6B`, `#FFD166`, `#58C4DD`, `#F2A541`, `#83C167` | `#161B24` | `#58C4DD`, `#F2A541`, `#C792EA`, `#83C167` | `github-dark` | `auto` |
| `light_academic` | `#F8F7F3` (off-white) | `#1F2328` / `#59606B` | `#B42318`, `#A64B00`, `#1D4ED8`, `#C2410C`, `#15803D` | `#FFFFFF` | `#1D4ED8`, `#C2410C`, `#9D2F8F`, `#15803D` | `xcode` | `auto` |
| `high_contrast` | `#000000` | `#FFFFFF` / `#C9CED6` | `#FF7A7A`, `#FFE14D`, `#4DD2FF`, `#FFAA4D`, `#7EE787` | `#141414` | `#4DD2FF`, `#FFAA4D`, `#FF8FD8`, `#7EE787` | `github-dark` | `large` |
| `warm_editorial` | `#F6F0E4` (cream paper) | `#2B2118` / `#6A5A4A` | `#9B1D3A`, `#8F5700`, `#1F5E6E`, `#B4441B`, `#37704F` | `#FFFBF4` | `#1F5E6E`, `#B04A16`, `#8D4AAB`, `#1A7C4D`, `#8C2024` | `default` | `auto` |
| `brand_neutral` | `#F4F5F7` (light grey) | `#15181D` / `#596270` | `#C42B3B`, `#A35200`, `#0B57C2`, `#4A5565`, `#0E7C66` | `#FFFFFF` | `#0B57C2`, `#C2410C`, `#08775A`, `#A04A8A`, `#5B6068` | `xcode` | `auto` |
| `soft_pastel` | `#252238` (dusky plum) | `#F3EEFA` / `#B0A8C4` | `#F7879F`, `#FCE38A`, `#86BDFF`, `#FFC27F`, `#9BEBC9` | `#2C2843` | `#86BDFF`, `#FFC27F`, `#9E8BEF`, `#9BEBC9`, `#F7879F` | `zenburn` | `auto` |
| `bold_neon` | `#0B0614` (violet-black) | `#F7F4FF` / `#A59CC2` | `#FF2E8B`, `#F4FF3A`, `#00C8FF`, `#FF8A1F`, `#39FF9C` | `#170F27` | `#00C8FF`, `#FF2E8B`, `#F4FF3A`, `#8C5BFF`, `#39FF9C` | `monokai` | `large` |

What they are for: `dark_tech` technical explainers; `light_academic` papers and lectures;
`high_contrast` accessibility; `warm_editorial` essays and storytelling; `brand_neutral` a quiet
base for a company colour (`{preset: brand_neutral, colors: {primary: "#..."}}` or a project
preset based on it); `soft_pastel` friendly tutorials; `bold_neon` short social clips.

All presets use the bundled families (Inter, Source Serif 4, JetBrains Mono NL);
`light_academic` sets headings and `warm_editorial` headings and quotes in the serif (see
[Fonts](#fonts)). Every built-in preset
passes WCAG AA (tested): `text` and `dim` at least 4.5:1 on the background and on `surface`,
the accent tokens at least 3:1 on the background and the palette at least 4.5:1 (charts label
series in palette colours; `high_contrast`: 7:1 for all of them). The palettes are ordered and
stay distinguishable for colour-blind viewers: every pair of colours differs by at least 7.5
CIEDE2000 under normal vision and simulated protanopia, deuteranopia and tritanopia (except
`dark_tech`, which keeps the historical default palette; its blue and purple are close for
deuteranopes, so put them apart or use another preset when that matters). Projects can add their own
presets (e.g. a brand look based on `light_academic`) with `register_theme_preset` in an
extension (docs/EXTENDING.md); `vidgen validate` reports an unknown preset name, and
`vidgen schema` lists the built-in and the project's presets.

Changed in Step 17: the third palette colour of `light_academic` (`#7E22CE` → `#9D2F8F`) and
`high_contrast` (`#D7A8FF` → `#FF8FD8`): the old purples were nearly identical to the blue for
deuteranopes.

Changed in Step 16: the default `dim` is `#838B98` (was `#6B7280`, 3.9:1 on the default
background, below WCAG AA); dim captions, axis labels and sources are a little lighter.

### `vidgen list-themes`

`vidgen list-themes [PROJECT] [--json] [--swatches PNG]` lists every preset (built-in, then the
project's own) with its resolved values in this project (background, colours, palette, fonts
and the family of each built-in role, `code_style`, scale and the sizes it gives here), the contrast check (minimum ratios, any
failing pair), the palette's smallest colour difference and for which vision, and the type
scales. `--swatches PNG` (alias `--sheet`, as in `list-icons`) also writes a picture of all presets (one row each: name and
description in its text colours, accent chips, a `surface` panel, the palette as bars), so an
AI author can compare them by opening one image. JSON shape: [below](#vidgen-list-themes---json).

## Icons

vidgen ships 200 line icons (from [Lucide](https://lucide.dev), ISC licence), 25 in each
category `tech`, `data`, `science`, `business`, `people`, `ui` (arrows and interface),
`nature`, `education`, chosen for what explainer videos show; the full list with aliases and
tags is the [icon catalogue](ICONS.md). Built-in scenes take them as params: `icon` on
[`title`](#title), [`chapter`](#chapter), [`stat`](#stat) and [`end_card`](#end_card), `{text,
icon}` items of [`bullets`](#bullets), columns and points of [`comparison`](#comparison),
events of [`timeline`](#timeline), nodes of [`diagram`](#diagram), stages and the token of
[`process`](#process), and the [`icon_grid`](#icon_grid) scene. Extension scenes draw them with `icon(name, ...)` (see
docs/EXTENDING.md "Icons"); scene params that take an icon name are typed `icon` in
`vidgen list-scenes` and checked by `vidgen validate` (an unknown name gets suggestions).

**Aliases.** Some icons have other names that work everywhere a name does: Lucide's old names
of renamed icons (`home` → `house`, `pie-chart` → `chart-pie`, `smile` →
`face-slightly-smiling`, `filter` → `funnel`) and a few synonyms (`idea` → `lightbulb`, `ai`
→ `brain-circuit`, `warning` → `triangle-alert`, `bar-chart` → `chart-column`, `money` →
`banknote`). A project icon with an alias's name replaces the alias.

**Project icons.** Put SVG files in `assets/icons/`: `assets/icons/<name>.svg` adds the icon
`<name>` or replaces the built-in icon of that name (letters, digits, `-` and `_`). Draw them on
a square `viewBox` (Lucide's is 24 x 24, with about 2 units of padding) with strokes or fills in
`currentColor`, so they size and recolour like the built-ins. An optional
`assets/icons/icons.json` gives them a category and search tags:

```json
{"icons": [{"name": "bicycle", "category": "transport", "tags": ["bike", "cycling"]}]}
```

Entries need a `name` whose SVG exists; `category` defaults to `project`, `tags` to none.
Problems (bad file names, a broken `icons.json`) are reported by `vidgen validate` under
`assets/icons`.

### `vidgen list-icons`

`vidgen list-icons [PROJECT] [--search TEXT] [--category NAME] [--sheet PNG [--theme [PRESET]]] [--json]` lists
the icons available in the project (built-in and `assets/icons`; without a PROJECT and no
config in the current folder: built-ins only), one line each: name, category, `[project]` for
project icons, `(alias: ...)`, tags. `--search` keeps icons whose name, aliases, tags or
category contain every word of TEXT (case-insensitive; best first: name, alias, whole words of
a name or alias, tags, whole words of a tag, then words merely contained in a name or tag, so
`--search ai` lists `brain-circuit` and `bot` before `rain`): `--search "chart"`,
`--search computer`. Tags include the concepts an icon stands for
in a script, so search by idea: `money`, `growth`, `security`, `speed`, `AI`, `team`.
`--category` keeps one category (unknown → error listing them). `--sheet PNG` also draws the
listed icons, labelled with name and category, on a 1280 px wide contact sheet (8 per row; a
long list continues in `<stem>-2.png`, ... ), drawn by the same code as a render: open it to
choose icons by eye. It is black on white; `--theme` draws it in the project's theme (its
background, icons in `primary`, names in `text`) and `--theme warm_editorial` in a preset's
(built-in or the project's), to see icons as a video shows them. JSON shape:
[below](#vidgen-list-icons---json).

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
  timestamps: false                 # also fetch when each character is spoken (karaoke captions)
```

All keys are optional; the values shown are the defaults. Unknown keys are an error. Changing
`voice_id`, `model_id`, `output_format` or `settings` re-voices every beat on the next `vidgen tts`.

`timestamps: true` makes `vidgen tts` use ElevenLabs' *with-timestamps* endpoint (same voice,
same price): besides `audio/<beat_id>.mp3` it stores `audio/<beat_id>.align.json`, when each
character is spoken, and burned-in [`captions`](#captions) and the SRT then time every word
exactly. Without it word times are estimated (see `captions`). It is not part of the audio hash:
turning it on does not re-voice anything; `vidgen tts --force` fetches the timings for existing
beats (paid again).

## Narration (`narration:`)

```yaml
narration:
  pad: 0.35               # seconds of silence after each beat
  words_per_second: 2.6   # duration estimate for beats that have no audio yet
```

## Narration audio (ElevenLabs)

Each beat is spoken by ElevenLabs into `audio/<beat_id>.mp3`, with `audio/<beat_id>.hash`
recording what it was generated from (and, with `voice.timestamps`, `audio/<beat_id>.align.json`:
its character timings, with the text and a hash of the MP3 they belong to, so a stale file is
ignored).

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
  vertical 9:16 variant; long text is wrapped and shrunk to fit. In a vertical frame short
  content grows into the tall frame: headings and list text 1.3x (`bullets`, `icon_grid`
  labels, `comparison`), a vertical `timeline` or a `process` column up to 1.5x, while it fits;
  a `map` with the `world` view keeps only the longitudes of its countries, pins and arcs.
- **Header band.** The line at the top of the frame is `heading` in `bullets`, `icon_grid`,
  `comparison`, `timeline`, `diagram`, `process`, `network` and `title` in the charts, `table`,
  `map`, `code`, `code_walkthrough`, `equation_derivation`, `screenshot`, `video_clip`. Every
  one of these types accepts **both names** (also `heading_size` / `title_size`,
  `heading_color` / `title_color`; `vidgen list-scenes` shows `(also: title)`), and the target
  `title` selects a `heading` and the reverse. Not in `title`, `chapter` and `end_card`, whose
  `title` is their main text.
- **Per-beat content** is a `steps` list in `code_walkthrough`, `equation_derivation`,
  `screenshot`, `video_clip` and `map`: step *i* plays at beat *i*. Elsewhere the scene splits
  its content into steps itself (`reveal`); `diagram`'s explicit `steps` are such reveal steps.
  A `highlight` param adds a last step that marks something and dims the rest; where it takes a
  list, one item may be written alone (`highlight: Lint`).
- **Too much content.** Types that fit their content (`table`, `timeline`, `diagram`,
  `process`, `comparison`, `heatmap`, `pie`, `equation_derivation`, `code_walkthrough`) shrink
  text down to the readable minimum (`vidgen lint`'s `min_font`), then scale the whole drawing
  and log a warning at render time — `scene 'x': the timeline's 10 events do not fit this frame
  at the readable size; split it into two timelines (or shorten titles and texts)` — not in
  `vidgen validate`, because it depends on the variant's frame and type scale.
- **Unknown keys** are reported with the closest names: `scenes[2].params.dim_prev: unknown
  parameter 'dim_prev'; did you mean 'dim_previous'? (known: heading, items, ...)`.
- Text-only types need no LaTeX; only `equation` and `equation_derivation` do.

### `title`

Steps: (1) icon, kicker, title and subtitle, (2) authors.
[Action targets](#beat-actions): `icon`, `kicker`, `title`, `subtitle`, `authors` (those the card has).

| param | type | default | |
|---|---|---|---|
| `title` | str | required | wrapped to fit; may contain `\n` |
| `subtitle` | str | `""` | |
| `kicker` | str | `""` | small label above the title |
| `authors` | list[str] | `[]` | one line each |
| `highlight` | str | `""` | part of the title drawn in `highlight_color` |
| `color`, `highlight_color`, `subtitle_color`, `kicker_color`, `authors_color` | color | `text`, `highlight`, `text`, `primary`, `dim` | |
| `icon` | icon | none | optional icon (name or alias, see [Icons](#icons)) |
| `icon_color` | color | `primary` | |
| `icon_position` | `above` \| `left` | `above` | above the kicker/title, or left of the title block, level with it (`left` falls back to `above` in a vertical frame) |

```yaml
- id: intro
  type: title
  params:
    kicker: "TECHNICAL REPORT"
    icon: brain-circuit
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
[Action targets](#beat-actions): `heading`, `item<N>` (1-based), `item:<text>`.
The heading sits in the `header` region, the list is centered in the space below it. In a
vertical video the heading is 1.3x larger and a short list grows up to 1.3x and spreads out to
use the taller frame.

| param | type | default | |
|---|---|---|---|
| `items` | list[str \| item] | required | at least one; each a string or `{text, icon}` (below) |
| `heading` | str | `""` | |
| `reveal` | `per_beat` \| `all` | `per_beat` | |
| `numbered` | bool | `false` | `1.` `2.` ... instead of `marker` |
| `marker` | str | `"•"` | |
| `dim_previous` | bool | `false` | fade earlier items when a new one appears |
| `size`, `heading_size` | size | `body`, `heading` | shrunk automatically for long lists |
| `color`, `heading_color`, `marker_color` | color | `text`, `text`, `primary` | `marker_color` also colours icons |

**Icons.** An item can be `{text: "...", icon: NAME}` (`text` required, `icon` optional; plain
strings keep working, and both forms mix in one list). The icon replaces the bullet; with
`numbered: true` it stands between the number and the text. Icons form a column of their own,
sized to the item text and centred on the capitals of its first line; in a list that mixes
icons and plain items, the plain items' bullets sit centred in that column, so all texts start
at one edge. Icons take `marker_color` and fade with their item (`dim_previous`).

```yaml
- id: points
  type: bullets
  params:
    heading: "Takeaways"
    items:
      - {text: "Fewer parameters", icon: layers}
      - {text: "Same validation loss", icon: chart-line}
      - "One GPU, three days"
    dim_previous: true
  beats:
    - text: "First, the model is much smaller."
    - text: "Second, it learns just as well."
    - text: "And it trained on a single GPU."
```

### `icon_grid`

Icons with a label (and an optional smaller sublabel) in a grid. Steps: one per item (the
heading comes with the first), or one per entry of `groups`; `reveal: all` shows every item in
beat 1; with `highlight`, a last step dims the other items and enlarges the highlighted one in
`highlight_color`. Each item fades in with its icon growing from its centre.
[Action targets](#beat-actions): `heading`, `item<N>` (1-based), `item:<label>` (icon, label and sublabel).

Layout: the heading sits in the `header` region and the grid fills the space below it. Without
`columns`, the shape (rows x columns) is chosen for the frame with `grid_shape` (see
docs/EXTENDING.md), trying narrow and wide cells and keeping the layout whose labels and icons
come out largest: 4 items make one row in 16:9 and a 2 x 2 grid in 9:16, 12 items 2 x 6 or (with
longer labels) 3 x 4 in 16:9. Labels share one size (1.3x in a vertical frame), wrap inside
their column and are reduced
(down to the readable minimum that `vidgen lint` accepts) when they need the room; a word wider
than its column reduces all labels. Icons are as large as the rest of the row allows (at most
1.9 units, a quarter of the frame's shorter side). A last row with fewer items is centred;
labels and sublabels of a row share their baselines. 2–12 items read well in 16:9 and 9:16 (at
most 16).

| param | type | default | |
|---|---|---|---|
| `items` | list[item] | required | 1–16 items `{icon, label, sublabel}`: `icon` (name or alias), `label` (str, required), `sublabel` (str, `""`) |
| `heading` | str | `""` | |
| `columns` | int | auto | fixed number of columns |
| `reveal` | `per_beat` \| `all` | `per_beat` | ignored when `groups` is given |
| `groups` | list[list[int \| str]] | none | reveal steps, each a list of items by 0-based index or label; every item exactly once |
| `highlight` | int \| str | none | item (0-based index or label) emphasised in a last step |
| `badge` | bool | `true` | draw each icon on a soft disc in its colour |
| `icon_color` | `palette` \| color | `primary` | one colour for all icons, or `palette`: one `theme.palette` colour per item |
| `color`, `sublabel_color`, `heading_color`, `highlight_color` | color | `text`, `dim`, `text`, `highlight` | |
| `size`, `sublabel_size`, `heading_size` | size | `body`, `caption`, `heading` | |

```yaml
- id: stack
  type: icon_grid
  params:
    heading: "What the platform covers"
    icon_color: palette
    highlight: "Security"
    items:
      - {icon: cpu, label: "Compute", sublabel: "GPUs and CPUs"}
      - {icon: database, label: "Storage"}
      - {icon: network, label: "Networking"}
      - {icon: shield-check, label: "Security", sublabel: "zero trust"}
    groups: [[0, 1], [2, 3]]       # two items per beat
  beats:
    - text: "Compute and storage come first."
    - text: "Then networking and security."
    - text: "And security matters most."
```

### `bar_chart`

Steps: all bars (`reveal: all`, default) or one per bar (`per_beat`), then — if `highlight` is
set — a focus step that dims the other bars. Bars grow while their value labels count up.
[Action targets](#beat-actions): `title`, `bar<N>` (1-based) and `bar:<label>`, each a bar with
its value and category labels (beat actions can do more than the one `highlight` step).

Like every chart, the title stands in the `header` band (1.3x in a vertical frame) and label
sizes are theme size tokens that never go below the readable minimum (see
[charts](#charts-common-to-all-chart-types)). Value labels keep their size where they can: one
too wide for its bar shrinks a little, then a word unit (`" min"`) moves under the number, then
it shrinks further; in a vertical frame the bars turn horizontal when even the readable size
does not fit (or with more than 5 bars), unless `horizontal` is set.

| param | type | default | |
|---|---|---|---|
| `labels` | list[str] | required | |
| `values` | list[float] | required | same length as `labels`; negatives allowed |
| `title` | str | `""` | |
| `caption` | str | `""` | note under the chart (e.g. the data source) |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |
| `label_size` | size | `caption` | category labels |
| `value_size` | size | `body` (`caption` with more than 6 bars) | value labels |
| `unit` | str | `""` | appended to every value label (`"%"`, `" ms"`) |
| `value_format` | str | automatic | Python format, e.g. `"{:.1f}"`, `"{:,.0f}"`, `"{:.0%}"`; default shows the decimals the values need |
| `colors` | color \| list[color] \| `palette` | `primary` | one color, one per bar, or `theme.palette` |
| `highlight` | int \| str | none | bar index (0-based) or label |
| `highlight_color` | color | `highlight` | highlighted value label |
| `horizontal` | bool | auto | default: vertical bars; horizontal in a portrait frame with more than 5 bars or value labels too wide for vertical ones |
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
too wide (e.g. in portrait) the names move to a legend, placed in a corner of the plot that no
line crosses (else above the plot). Axis labels are plain text (no LaTeX); tick labels that
would collide are thinned to every second (third...) one.
[Action targets](#beat-actions): `title`, `axes`, `series<N>` (1-based), `series:<name>` (a line with its markers
and end label), `point:<name>@<x>` (one data point, `x` as its tick label reads:
`point:sparse@8`; without `dots` the point appears as a dot when an action uses it).

| param | type | default | |
|---|---|---|---|
| `x` | list[float] \| list[str] | required | numbers (increasing) or category names |
| `series` | `{name: [values]}` or list of `{name, values, color}` | required | one value per `x` |
| `title`, `caption` | str | `""` | |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |
| `label_size` | size | `caption` | tick and axis labels, end labels, legend |
| `x_label`, `y_label` | str | `""` | |
| `y_min`, `y_max` | float | from the data | |
| `value_format` | str | automatic | for y ticks and end labels (ticks default to the decimals they need) |
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

### Charts: common to all chart types

`bar_chart`, `line_chart`, `scatter`, `histogram`, `pie` and `heatmap` share their frame (and
the axis charts their axes; the helpers are public for project charts, see EXTENDING.md
"Charts"):

- **Title** in the `header` band at the top (bold, the theme's `heading` font role, 1.3x larger
  in a vertical frame), **caption** at the bottom; the plot gets the space between.
- **Label sizes** are theme size tokens (`label_size`, default `caption`), never below the
  readable minimum that `vidgen lint` checks, so they grow with the type scale (`large` in
  9:16) instead of staying small.
- **Ticks** are round numbers (steps of 1, 2, 2.5 or 5 x 10^k; powers of ten on a log axis),
  written with the decimals they need and `k`/`M`/`B` from 10 000 on (`20k`), unless a format
  is given. Labels that would collide are thinned. Gridlines are faint dashes at the labelled
  ticks.
- **Legends** (several series) stand in a corner of the plot that covers no data, on a faint
  framed panel, as one row or stacked; when every corner has data, above the plot.
- **Colours** are theme tokens: series and slices take the palette, colour scales
  (`heatmap`) are mixed from theme colours, and text written on a filled shape (a slice, a
  cell) switches between the theme's text and background colour so it keeps 4.5:1 contrast.

### `scatter`

Points of one or more series on two numeric axes. Steps: one series per beat (`reveal:
series`, default; the axes come with the first), its points popping in from left to right;
`groups`: the points of each `group` (in order of first use; points without one come first);
`all`: everything in beat 1. Then, if set, the `trend` line grows (a step of its own) and the
`highlight` step rings the chosen points and dims the others. Point labels stand beside their
point where they cover no other point, label or trend line.
[Action targets](#beat-actions): `title`, `axes`, `legend`, `series<N>`, `series:<name>`,
`point:<series>@<N>` (1-based, in the order written) and `point:<series>@<label>`, `trend`
(every trend line with its text) and `trend:<series>` (with `trend: each`).

| param | type | default | |
|---|---|---|---|
| `series` | `{name: [points]}` or list of `{name, points, color, marker}` | required | a point is `[x, y]`, `[x, y, label]` or `{x, y, label, group}`; `marker` `auto` (circle, square, triangle, diamond by position), `circle`, `square`, `triangle`, `diamond` |
| `title`, `caption` | str | `""` | |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |
| `label_size` | size | `caption` | ticks, axis labels, point labels, legend, trend text |
| `x_label`, `y_label` | str | `""` | axis titles |
| `x_min`, `x_max`, `y_min`, `y_max` | float | from the data | axis ends (points outside are an error) |
| `x_log`, `y_log` | bool | `false` | logarithmic axis (positive values) |
| `x_format`, `y_format` | str | automatic | Python format of the tick labels |
| `x_unit`, `y_unit` | str | `""` | appended to tick labels |
| `trend` | `none` \| `each` \| `all` | `none` | least-squares line per series or through every point (linear axes) |
| `trend_label` | `none` \| `equation` \| `r2` \| `both` | `none` | `y = 0.52x + 1.3`, `R² = 0.87` beside the line |
| `trend_color` | color | series color / `text` | |
| `reveal` | `series` \| `groups` \| `all` | `series` | |
| `show_labels` | `all` \| `highlight` \| `none` | `all` | which point labels are written (`highlight`: only highlighted points', in the highlight step) |
| `highlight` | list[str] | `[]` | points for a last step: `"<series>@<N>"`, `"<series>@<label>"` or a label |
| `highlight_color` | color | `highlight` | ring color |
| `legend` | bool | auto | default: with more than one series |
| `point_radius` | float | auto | marker radius in units (0.11 for up to 20 points, down to 0.05) |

```yaml
- id: sizes
  type: scatter
  params:
    title: "Model size vs accuracy"
    x_label: "parameters (billions)"
    y_label: "accuracy (%)"
    trend: all
    trend_label: r2
    highlight: ["ours@2"]
    series:
      baselines: [[1.3, 61], [6.7, 70, "7B"], [13, 73], [65, 80, "65B"]]
      ours: [[1.0, 66], [3.8, 72, "small"], [7.0, 75]]
  beats:
    - text: "Baselines improve as they grow."
    - text: "Our models sit above them."
    - text: "The trend makes the gap clear."
    - text: "Especially for the small one."
```

### `histogram`

A distribution as bars over value bins. Step 1 draws the axes and grows the bars from left to
right; then, each a step of its own (so one per beat when there are enough beats): the
`compare` outline, the `mean` marker, the `median` marker, and the `highlight` of chosen bins
(they turn `highlight_color`, the others dim). Bins come from raw `values` — `bins` as a count
of equal bins, or a rule whose width is rounded to 1, 2, 2.5 or 5 x 10^k with edges on its
multiples (so the axis reads 10, 20, 30), or a `bin_width` — or from `counts` with their
`edges`. Mean and median are exact from values, estimated from counts.
[Action targets](#beat-actions): `title`, `axes`, `legend` (with `compare`), `bin<N>`
(1-based), `bin:<range>` (the edges as the axis writes them: `bin:10-20`), `compare`, `mean`,
`median`.

| param | type | default | |
|---|---|---|---|
| `values` | list[float] | — | raw data (or `counts` + `edges`) |
| `bins` | int \| `auto` \| `sturges` \| `sqrt` \| `fd` | `auto` | equal bins over the range, or a rule (numpy's; `fd` = Freedman-Diaconis) with round widths; at most 60 bins |
| `bin_width` | float | none | width; edges on its multiples (or from `bin_range`'s start) |
| `bin_range` | [low, high] | the data's | values outside are left out |
| `counts`, `edges` | list[float] | — | counts per bin and the `len(counts) + 1` increasing edges, instead of `values` |
| `name` | str | `""` | legend name (shown with `compare`; default `data`) |
| `compare` | `{name, values \| counts, color}` | none | a second distribution over the same bins, drawn as an outline (`color` `secondary`) |
| `percent` | bool | `false` | each bin's share of its total (%) instead of counts |
| `mean`, `median` | bool | `false` | dashed marker with its value above the plot |
| `highlight` | list[int \| str] | `[]` | bins (0-based index or range `"10-20"`) for a last step |
| `title`, `caption` | str | `""` | |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |
| `label_size` | size | `caption` | ticks, axis labels, marker labels, legend |
| `x_label`, `y_label` | str | `""` | axis titles |
| `x_format`, `y_format` | str | automatic | Python format of the edges (also in `bin:` names) / y ticks |
| `x_unit` | str | `""` | appended to x ticks and the mean / median values |
| `color` | color | `primary` | bars |
| `mean_color`, `median_color`, `highlight_color` | color | `accent`, `tertiary`, `highlight` | |

```yaml
- id: latency
  type: histogram
  params:
    title: "Response times"
    x_label: "milliseconds"
    values: [12, 15, 17, 18, 21, 22, 23, 25, 26, 28, 30, 31, 33, 35, 38, 41, 45, 52, 61, 75, 97, 120]
    mean: true
    median: true
    highlight: ["40-50"]
  beats:
    - text: "Most requests finish quickly."
    - text: "The slow tail pulls the mean up."
    - text: "The median stays lower."
    - text: "These are the requests to look at."
```

### `pie`

Shares of a whole as slices of a circle, or of a ring with `donut: true` (the total, or
`center`, in the hole). Step 1 sweeps every slice round from the top, clockwise, then writes
the labels (`reveal: all`, default); `per_beat` sweeps slice *i* in at beat *i*. With
`highlight`, a last step pulls that slice out of the pie and dims the others. Each share is
its value / the total.

**Labels** stand inside their slice when they fit there (in the slice's colour-contrasting
text colour), else outside with a leader line, stacked in a column on each side so they never
overlap; when side columns would leave the pie too small (a 9:16 frame) or cannot hold them,
those labels go into a key of colour swatches below the pie (beside it in 16:9). With more than
6 slices (or `legend: true`) every label is in that key, which is then the `legend`. Many small
slices: group them with `other_below: 3` (slices under 3 % become one `Other` slice, drawn
last in `other_color`) or `max_slices`. Label text shrinks towards the readable minimum before
anything is left out (a warning names what did not fit).
[Action targets](#beat-actions): `title`, `slice<N>` (1-based, as drawn, after grouping),
`slice:<label>` (a slice with its label and leader), `center` (a donut's centre text),
`legend` (with the legend).

| param | type | default | |
|---|---|---|---|
| `labels`, `values` | list[str], list[float] | required | one value (≥ 0) per unique label |
| `donut` | bool | `false` | a ring instead of a full pie |
| `hole` | float | `0.58` | donut hole radius / outer radius (0.3–0.85) |
| `center` | str | the total | text in the donut hole (`value_format` + `unit`); `""` for none |
| `center_label` | str | `""` | a smaller line under it (`visits`) |
| `center_size` | size | `title` | fitted into the hole |
| `show_values` | `percent` \| `value` \| `both` \| `none` | `percent` | under each name: `42%`, the value, `42% · 1,200` or nothing |
| `value_format`, `unit` | str | automatic, `""` | format of values and the total |
| `percent_decimals` | int | auto | 0, or 1 when a slice is under 1 % |
| `colors` | `palette` \| color \| list[color] | `palette` | the palette in order (lighter shades past its length) |
| `sort` | bool | `false` | largest slice first |
| `other_below` | float | none | group slices under this share (%) into one |
| `max_slices` | int | none | keep the largest `max_slices - 1`, group the rest |
| `other_label`, `other_color` | str, color | `Other`, `dim` | the grouped slice |
| `label_position` | `auto` \| `outside` | `auto` | `outside`: never inside a slice |
| `legend` | bool | auto | names in a legend (default: with more than 6 slices) |
| `reveal` | `all` \| `per_beat` | `all` | |
| `highlight` | int \| str | none | slice (0-based index or label, as drawn) pulled out in a last step |
| `explode` | float | `0.1` | how far it moves out (share of the radius, 0–0.3) |
| `start_angle`, `clockwise` | float, bool | `90`, `true` | where the first slice starts (degrees; 90 = top) and the direction |
| `label_size` | size | `caption` | labels and legend |
| `title`, `caption` | str | `""` | |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |

```yaml
- id: traffic
  type: pie
  params:
    title: "Visits by device"
    donut: true
    center_label: "visits"
    labels: ["Mobile", "Desktop", "Tablet", "TV", "Watch"]
    values: [5200, 3100, 640, 120, 80]
    other_below: 2           # TV and Watch become "Other"
    highlight: Desktop
  beats:
    - text: "Most visits come from phones."
    - text: "Desktop is still a third of them."
```

### `heatmap`

A matrix of values as coloured cells: row labels on the left, column labels on top, a
colour-scale legend (a gradient bar with round ticks) right of it (below it in 9:16). Step 1
brings the labels and legend and the cells in a wave from the top left (`reveal: all`,
default); `rows` reveals one row per beat. With `highlight`, a last step outlines the chosen
cells, rows or columns in `highlight_color` and dims the rest.

**Colours** come from theme colours, interpolated perceptually (OKLab, so equal steps in
value look like equal steps in colour): `sequential` runs from a faint tint of `color` to
`color` (larger values stand out more on any background); `diverging` runs from `low_color`
through a near-background neutral at `center` to `high_color`, symmetric around `center`;
`auto` picks diverging when values lie on both sides of `center`. Each value is written in the
theme's text or background colour, whichever reads better on its cell (WCAG 4.5:1 or more,
what `vidgen lint` checks), and the values are hidden when the cells are too small for
readable text. Cells are at most square-tall and 2.5x as wide as tall; a matrix whose cells
come out smaller than 0.3 units logs a warning to split it. `null` values are empty cells.
[Action targets](#beat-actions): `title`, `legend`, `row<N>`, `row:<label>`, `col<N>`,
`col:<label>` (a row / column with its label), `cell<R>.<C>` (1-based).

| param | type | default | |
|---|---|---|---|
| `values` | list[list[float \| null]] | required | the matrix, row by row (up to 40 x 40) |
| `rows`, `columns` | list[str] | `[]` | unique row / column labels |
| `scale` | `auto` \| `sequential` \| `diverging` | `auto` | |
| `color` | color | `primary` | sequential: the highest values |
| `low_color`, `high_color` | color | `primary`, `accent` | diverging: below / above `center` |
| `center` | float | `0` | diverging: the neutral value |
| `scale_min`, `scale_max` | float | from the data | ends of the scale (diverging: symmetric around `center`) |
| `show_values` | bool | auto | values in the cells (default: when they fit at a readable size) |
| `value_format`, `unit` | str | automatic, `""` | cell values and legend ticks |
| `value_size` | size | `caption` | largest value size (shrinks to fit) |
| `legend` | bool | `true` | the colour-scale bar |
| `legend_label` | str | `""` | its title (`correlation`) |
| `reveal` | `all` \| `rows` | `all` | |
| `highlight` | list[str] | `[]` | `cell<R>.<C>`, `row<N>`, `row:<label>`, `col<N>`, `col:<label>` for a last step |
| `highlight_color` | color | `highlight` | outline colour |
| `label_size` | size | `caption` | row / column labels and ticks |
| `title`, `caption` | str | `""` | |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |

```yaml
- id: busy
  type: heatmap
  params:
    title: "Renders per hour"
    rows: ["Mon", "Tue", "Wed"]
    columns: ["9h", "12h", "15h", "18h"]
    values: [[3, 8, 4, 9], [5, 10, 6, 11], [4, 9, null, 13]]
    legend_label: "renders"
    highlight: ["col:18h"]
  beats:
    - text: "Each cell counts the renders in one hour."
    - text: "Evenings are the busiest."
```

### `map`

A world map — the 177 countries of Natural Earth's 1:110m admin-0 map (public domain, bundled;
see THIRD_PARTY_NOTICES.md) in the Equal Earth projection — with highlighted countries, a
choropleth, pins and flight-path arcs. Borders are Natural Earth's *de facto* representation
(e.g. Kosovo, N. Cyprus, Somaliland and W. Sahara are shapes of their own); vidgen takes no
position on disputed boundaries. Countries are named by ISO 3166
alpha-2 or alpha-3 code (`DE`, `DEU`), English name or a common alias (`USA`, `UK`, `Holland`,
`Ivory Coast`, `Czech Republic`...); case and accents do not matter, typos get a "did you mean".
Countries too small for this scale (Singapore, Malta, Bahrain...) are reported by `vidgen
validate`: mark them with a pin instead.

Beat 1 draws the map (a sweep from west to east; a choropleth's colours with it), the legend,
the `countries` / `pins` / `arcs` given outside `steps`, and then step 1. **Per-beat data** is
`steps` (aligned with the beats as in `screenshot` / `code_walkthrough`): step *i* highlights its
countries (the fill fades to the colour, the label follows), drops its pins and grows its arcs
at beat *i*. Earlier steps stay. A step with `focus` moves the camera in on its items (labels
are built for the zoom so they read at their normal size; labels made for another view fade);
the next step without `focus` moves back. More steps than beats are spread evenly; extra beats
hold.

- **View**: `auto` (default) fits the highlighted and valued countries, pins and arcs (with a
  margin; the world when there are none or they span more than 200° of longitude); `world`
  (without Antarctica unless `antarctica: true`); a region — `europe`, `africa`, `asia`,
  `middle_east`, `north_america`, `south_america`, `oceania`; or a box `[lon_min, lat_min,
  lon_max, lat_max]` in degrees (`lon_max < lon_min` crosses the date line, e.g. `[150, -50,
  -170, 0]`). The view is projected around its middle longitude and grown to the shape of the
  space (more of the map, not empty bands); a regional view is drawn as a framed panel with the
  sea in `surface`. In 9:16 the whole world is a narrow strip, so a `world` (or `auto` → world) view
  keeps only the longitudes of the map's countries, pins and arcs (12 % added on each side, at
  least 140°) and all latitudes; items spread round the whole world still give the strip.
- **Highlights** fill countries with `highlight_color` (`accent`; `palette`: one theme palette
  colour per country, in order) or their own `color`, and write their name (`labels`; a
  country's `label` gives other text, `false` none) on its largest part when it fits, else
  beside it with a leader line. A country is highlighted once per scene.
- **Choropleth**: `values` colours countries by a colour scale like `heatmap`'s (`scale`,
  `color`, `low_color`, `high_color`, `center`, `scale_min`, `scale_max`) with a legend bar below
  the map (`legend`, `legend_label`, `value_format`, `unit`); countries without a value are
  fainter land. On a choropleth, highlights are outlines in `highlight_color` (colour is the
  data).
- **Pins** `{lon, lat, label}` (degrees, east / north positive) or `{country, label}` (in the
  middle of the country); **arcs** `{from, to, label}` or `"A -> B"`, where an end is a pin's
  label, a country or `[lon, lat]`. Arcs bend upwards (downwards near the top of the map), grow
  from `from` to an arrowhead at `to` and stop short of pins. Arcs are drawn on the flat map,
  not along great circles, and do not wrap round the date line.
- **Labels** sit on plates of the background colour (readable on any fill), at `label_size`
  (never below the readable minimum), placed clear of each other and of pins.

[Action targets](#beat-actions): `title`, `map` (every country), `legend`, `country:<code>` (a
highlighted or valued country: `country:DEU`, `country:DE` or `country:Germany`), `pin<N>`,
`pin:<label>`, `arc<N>`, `step<N>` (a step's items).

| param | type | default | |
|---|---|---|---|
| `view` | str \| [lon_min, lat_min, lon_max, lat_max] | `auto` | `auto`, `world`, `europe`, `africa`, `asia`, `middle_east`, `north_america`, `south_america`, `oceania`, or a box |
| `countries` | list[str \| {country, color, label}] | `[]` | highlighted in beat 1 |
| `pins` | list[{lon, lat, label, color} \| {country, label, color}] | `[]` | shown in beat 1 |
| `arcs` | list[{from, to, label, color} \| "A -> B"] | `[]` | drawn in beat 1 |
| `steps` | list[{countries, pins, arcs, focus} \| list of countries \| country] | `[]` | step *i* at beat *i* |
| `values` | {country: number} | `{}` | choropleth |
| `labels` | bool | `true` | names on highlighted countries |
| `highlight_color` | color \| `palette` | `accent` | highlight fill (outline on a choropleth) |
| `land_color` | color | `dim` | land, shown faint over the background |
| `pin_color`, `arc_color` | color | `highlight` | defaults for pins / arcs |
| `antarctica` | bool | `false` | draw Antarctica (the `world` view reaches the pole) |
| `scale` | `auto` \| `sequential` \| `diverging` | `auto` | choropleth colour scale (as `heatmap`) |
| `color` | color | `primary` | sequential: the highest values |
| `low_color`, `high_color` | color | `primary`, `accent` | diverging: below / above `center` |
| `center` | float | `0` | diverging: the neutral value |
| `scale_min`, `scale_max` | float | from the data | ends of the scale |
| `value_format`, `unit` | str | automatic, `""` | legend ticks |
| `legend` | bool | `true` | the colour bar under a choropleth |
| `legend_label` | str | `""` | its title (`millions`) |
| `label_size` | size | `caption` | country, pin and arc labels |
| `focus_scale` | float | `3` | largest magnification of `focus: true` (up to 4) |
| `title`, `caption` | str | `""` | |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |

A step's `focus` is `true` (as close as fits, up to `focus_scale`) or a magnification (more
than 1, up to 4).

```yaml
- id: offices
  type: map
  params:
    title: "Our offices"
    view: europe
    steps:
      - [Germany, France]                                    # beat 1: two countries
      - pins: [{lon: -0.13, lat: 51.51, label: London}, {lon: 13.4, lat: 52.52, label: Berlin}]
        arcs: ["London -> Berlin"]                           # beat 2: pins and an arc
      - countries: [{country: NL, label: "Amsterdam HQ"}]
        focus: true                                          # beat 3: the camera moves in
  beats:
    - text: "We started in Germany and France."
    - text: "Then London and Berlin, linked by a weekly flight."
    - text: "Our new head office is in the Netherlands."
```

```yaml
- id: people
  type: map
  params:
    title: "Population"
    view: europe
    values: {Germany: 83, France: 68, Italy: 59, Spain: 48, Poland: 37, UK: 67}
    legend_label: "millions"
    steps: [[], [Germany]]                                   # beat 2 outlines Germany
  beats:
    - text: "Europe's largest countries by population."
    - text: "Germany has the most people."
```

### `image`

Steps: (1) the image, (2) the caption. `vidgen validate` reports a missing or unsupported file
(png, jpg, jpeg, gif, bmp, webp, tif).
[Action targets](#beat-actions): `image`, `caption` (`dim` fades the picture, `highlight` tints it).

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

### `screenshot`

A picture of an app or a web page with **callouts** pointing at its parts, one step per beat:
boxes, circles, arrows with labels, magnified insets and a spotlight. Steps: (1) the picture (in
its frame) and then step 1's callouts, (*i*) step *i*'s callouts. Before a step's callouts are
drawn, the earlier ones fade out (`previous: fade`, default), dim (`dim`: their boxes, circles
and arrows stay faint, labels, insets and shades go) or stay (`keep`). With more steps than beats
they are spread evenly; extra beats hold. `vidgen validate` reports a missing or unsupported
image file and areas outside the image.

**Areas** are `[x, y, w, h]`: the top-left corner and the size, as fractions of the image (`0`–`1`,
from its top-left corner, like `ken_burns` focus points) or, with `units: px`, in the image's own
pixels (as an image editor shows them). A point `[x, y]` is enough for a box, circle or arrow.

**Callouts** are written `{KIND: area, label: ..., ...}` (or `{kind: KIND, area: [...], ...}`):

| kind | draws | options |
|---|---|---|
| `box` | a rounded frame around the area, the label as a tag on its edge (above it, else below) | `label`, `color`, `side` |
| `circle` | an ellipse through the area's corners (a ring around a point), the label beside it | `label`, `color`, `side` |
| `arrow` | the label away from the area — outside the picture when there is room, never off the frame — and an arrow from it to the area's edge (to the point) | `label`, `color`, `side`, `curved` |
| `magnifier` | an enlarged inset of the area (`zoom` times, less when there is not that much room beside the area), joined to a frame around the area by two lines; cut from the image's own pixels, so it is sharp | `label`, `color`, `side`, `zoom` (`2`, more than 1, up to 8) |
| `spotlight` | the rest of the picture dimmed (the theme's background at 62 %), the area clear | `label`, `color`, `side` |

Labels are bold text on a plate in the callout's colour (default the scene's `color`,
`highlight`), written in whichever theme colour reads best on it (4.5:1 or more), at `label_size`
and never below the readable size; long labels wrap. Each label is placed clear of the other
callouts of its step (and of those kept from earlier steps), of their areas and of the frame's
title bar. `side: top | bottom | left | right` forces where the label (a magnifier: its inset)
goes. A spotlight lies under the other callouts.

**Per-beat data** lives in `steps`, aligned with the beats: entry *i* is beat *i*. An entry is one
callout, a list of callouts, or `{callouts, focus, previous}`.

**Focus.** `focus: true` moves the camera in on the step's areas (at most `focus_scale`, so that
they take about half of the view; a number is the magnification) and builds the step's labels and
lines for the zoom, so they read at their normal size. Callouts built for another view (the
whole frame, or another focus) leave when the camera moves; the next step without `focus` moves
the camera back.

**Frames.** `frame: browser` draws a title bar with three dots and an address field (`url`),
`window` the title bar alone, `phone` a rounded body with a speaker slot and a home bar (for
portrait screenshots); all in the theme's `surface` and `dim` colours.

[Action targets](#beat-actions): `title`, `image` (the picture with its frame), `caption`, `callout<N>`
(numbered over all steps, in the order written), `callout:<label>`, `step<N>` (a step's callouts;
revealing it plays the step). Revealing a callout early draws it (one of a focus step brings its
step, with the camera); a step whose callouts are all on screen already is skipped at its beat.

| param | type | default | |
|---|---|---|---|
| `path` | str | required | relative to the project folder, e.g. `assets/app.png` |
| `title` | str | `""` | heading above the picture |
| `caption` | str | `""` | a line under the picture (as in `video_clip`; callout labels keep clear of it; it fades out while a `focus` step has the camera in, and back) |
| `caption_size` | size | `caption` | |
| `caption_color` | color | `text` | |
| `steps` | list | `[]` | step *i* at beat *i*: a callout, a list of callouts, or `{callouts, focus, previous}` |
| `steps[].callouts` | list | `[]` | `{KIND: area, label, color, side, curved, zoom}` (see above) |
| `steps[].callouts[].kind`, `.area` | kind, list | required | the canonical form of `{KIND: area}` |
| `steps[].callouts[].label` | str | `""` | |
| `steps[].callouts[].color` | color | the scene's `color` | mark and label plate |
| `steps[].callouts[].side` | `auto` \| `top` \| `bottom` \| `left` \| `right` | `auto` | where the label / inset goes |
| `steps[].callouts[].curved` | bool | `false` | arrows only |
| `steps[].callouts[].zoom` | number | `2` | magnifiers only |
| `steps[].focus` | bool \| number | `false` | `true`: the camera moves in on the step's areas; a number (1–4): that magnification |
| `steps[].previous` | `fade` \| `dim` \| `keep` | the scene's | what happens to earlier callouts at this step |
| `frame` | `none` \| `browser` \| `window` \| `phone` | `none` | drawn around the picture |
| `url` | str | `""` | text of a `browser` frame's address field |
| `units` | `fraction` \| `px` | `fraction` | how areas are written |
| `color` | color | `highlight` | default callout colour |
| `label_size` | size | `caption` | label text size (never below the readable size) |
| `previous` | `fade` \| `dim` \| `keep` | `fade` | what happens to a step's callouts when the next starts |
| `focus_scale` | number (1–4) | `2.0` | largest magnification of `focus: true` |

```yaml
- id: app
  type: screenshot
  params:
    title: "Point at what matters"
    path: assets/app.png
    frame: browser
    url: "planner.example/overview"
    steps:
      - {box: [0.216, 0.038, 0.269, 0.055], label: "Search every task"}
      - - {arrow: [0.857, 0.065], label: "New task", curved: true}
        - {circle: [0.736, 0.15, 0.25, 0.17], label: "Overdue"}
      - {magnifier: [0.675, 0.545, 0.28, 0.085], label: "Done today", zoom: 2.5}
      - callouts:
          - {spotlight: [0.205, 0.37, 0.428, 0.58]}
          - {arrow: [0.425, 0.55], label: "Thursday was the busiest day"}
        focus: true
  beats:
    - text: "A box marks the search field."
    - text: "An arrow points at the new task button, and a circle at the overdue count."
    - text: "A magnifier enlarges a detail."
    - text: "Focus moves the camera in, and a spotlight dims everything else."
```

Project scenes draw the same callouts with the `callout_*` helpers of `vidgen.api`
([EXTENDING.md](EXTENDING.md#2-building-blocks-params-layout-timing-validation), "Callouts").
Callouts on any other scene type (a chart, a diagram) are the [`callout` beat
action](#beat-actions).

### `video_clip`

A **video file** — B-roll, a screen recording — played inside the scene while the narration
runs: framed in a layout region (optionally in a `browser` / `window` / `phone` frame as in
[`screenshot`](#screenshot), with a title above and a caption below) or full-bleed, with
**callouts** drawn over it step by step exactly as in `screenshot` (same `steps`, kinds, `previous`,
`focus`; no `magnifier`, which needs a still picture). Steps: (1) the clip (with its title and
caption) and then step 1's callouts, (*i*) step *i*'s callouts. Files: mp4, mov, m4v, webm, mkv
(anything FFmpeg decodes); `vidgen validate` reports a missing, unsupported or unreadable file, a
`trim` past the clip's end and pixel areas outside its picture.

**Timing contract.** The narration sets the scene's length, never the clip: the scene lasts its
beats (+ `narration.pad` each, as every scene) plus the 0.5 s fade-out, or a silent scene's
`duration`. The clip starts playing when the scene starts (it fades in while playing) and plays
`trim: [start, end]` (default: all of it) at `speed` through every beat. One pass takes
`(end - start) / speed` seconds on screen; when the scene is longer the clip starts again with
`loop: true`, otherwise its **last frame holds** (a warning names the hold when it is longer than
2 s, and `vidgen lint`'s `dead_air` reports a hold over 6 s, as it reports any still picture);
when the scene is shorter the clip is cut by the fade-out. `fit_duration: true` picks the speed
that makes one pass last exactly as long as the narration, kept within `fit_range` (default
`[0.5, 2.0]`, so a clip is never sped up or slowed down beyond recognition; outside it the clip
holds or is cut as above).

**Sound.** The clip's own sound plays as the picture does (trimmed, at its speed with its pitch
kept, looped, silent while the last frame holds) and is mixed **under the narration** into the
scene's sound: `volume` 0.25 by default in a narrated scene, 1 in a silent one; `mute: true` (or
`volume: 0`) leaves it out. It fades out with the picture. There is no ducking: keep `volume` low
under speech.

**Layout.** `region` is a layout region ([`vidgen.api.region`](EXTENDING.md#2-building-blocks-params-layout-timing-validation)) for the clip below the title: `body`
(default) or `full` (all the room below the title), `hero`, `left`, `right` (upper / lower half in
9:16), `top`, `bottom`, `center` — or `bleed`, the whole frame edge to edge, with the title and the
caption on plates in the theme's `surface` colour over the picture (no `frame` then). `fit:
contain` shows the whole picture as large as fits; `cover` fills the region (or the frame),
cutting the picture's excess equally from both sides — a 16:9 clip in a 9:16 frame keeps only its
middle with `region: bleed, fit: cover`, while `contain` leaves bands above and below.

**Callout areas** are `[x, y, w, h]` (or a point `[x, y]`) from the top-left corner of the clip's
**whole picture**, as fractions or, with `units: px`, in its pixels — also with `fit: cover`, so a
callout stays on the same thing whichever part is shown (a warning names callouts outside the part
`cover` shows). Callouts stay put while the picture moves: point at things that stay there, or
give the step its own beat.

Decoding: frames are read with PyAV as the render reaches them, scaled once to the size shown
(sharper when a `focus` step or a `zoom` action will look closer, up to the clip's own pixels) and
not kept in memory; stills, the layout dump and `vidgen lint` see the clip as an image, and the
clip's motion counts as activity for `dead_air`. Rotation metadata (phone videos) is not applied.

[Action targets](#beat-actions): `title`, `clip` (the picture with its frame), `caption`,
`callout<N>`, `callout:<label>`, `step<N>` (as in `screenshot`). `dim: clip` fades the moving
picture, `highlight: clip` tints it, `zoom: clip` looks closer.

| param | type | default | |
|---|---|---|---|
| `path` | str | required | relative to the project folder, e.g. `assets/demo.mp4` |
| `title` | str | `""` | heading above the clip (on a plate with `region: bleed`) |
| `caption` | str | `""` | line under the clip (on a plate at the bottom with `region: bleed`); fades out while a `focus` step has the camera in |
| `caption_size`, `caption_color` | size, color | `caption`, `text` | |
| `region` | `body` \| `full` \| `hero` \| `left` \| `right` \| `top` \| `bottom` \| `center` \| `bleed` | `body` | where the clip goes (see above) |
| `fit` | `contain` \| `cover` | `contain` | whole picture, or fill the region / frame (cropped) |
| `trim` | [start, end] | the whole clip | seconds of the file that play |
| `speed` | number (0.25–4) | `1.0` | playback speed; the sound keeps its pitch |
| `fit_duration` | bool | `false` | choose the speed so one pass lasts as long as the narration (not with `speed`) |
| `fit_range` | [slowest, fastest] | `[0.5, 2.0]` | limits of `fit_duration` (within 0.25–4) |
| `loop` | bool | `false` | start again when the scene outlasts the clip (else the last frame holds) |
| `volume` | number (0–2) | 0.25 narrated, 1 silent | the clip's own sound, under the narration |
| `mute` | bool | `false` | leave the clip's sound out |
| `steps` | list | `[]` | step *i* at beat *i*: a callout, a list of callouts, or `{callouts, focus, previous}` ([`screenshot`](#screenshot); kinds `box`, `circle`, `arrow`, `spotlight`) |
| `frame`, `url` | `none` \| `browser` \| `window` \| `phone`, str | `none`, `""` | a frame drawn around the clip (not with `bleed`); `url` for `browser` |
| `units` | `fraction` \| `px` | `fraction` | how callout areas are written (of the whole picture) |
| `color`, `label_size` | color, size | `highlight`, `caption` | callout colour and label size |
| `previous` | `fade` \| `dim` \| `keep` | `fade` | what happens to a step's callouts when the next starts |
| `focus_scale` | number (1–4) | `2.0` | largest magnification of `focus: true` |

```yaml
- id: clip
  type: video_clip
  params:
    title: "Clips play under the narration"
    path: assets/clip.webm
    frame: window
    caption: "A generated test pattern, looping"
    loop: true
    steps:
      - {box: [0.0, 0.0, 0.21, 0.14], label: "Time code"}
      - {arrow: [0.92, 0.45], label: "Colour bars", curved: true}
  beats:
    - text: "Video clips play inside a scene, and the narration sets how long they run."
    - text: "Callouts work on moving pictures too, one step per beat."
- id: broll
  type: video_clip
  params: {path: assets/city.mp4, region: bleed, fit: cover, trim: [12, 20], fit_duration: true, mute: true}
  beats:
    - text: "Full-bleed B-roll, trimmed and stretched over the sentence."
```

### `quote`

Steps: (1) quote mark and text, (2) attribution. Quote characters around `text` are removed;
the scene draws a large typographic mark.
[Action targets](#beat-actions): `mark`, `quote`, `author`, `source` (those present).

| param | type | default | |
|---|---|---|---|
| `text` | str | required | |
| `author`, `source` | str | `""` | shown as `— author` and, smaller, `source` |
| `size` | size | `subtitle` | of the quote text (shrunk if long; 1.25x in a vertical frame) |
| `color`, `mark_color`, `author_color`, `source_color` | color | `text`, `primary`, `text`, `dim` | |
| `mark_font` | str | role `quote_mark` (Source Serif 4) | font of the quote mark |

The quote text uses the font role `quote`, the mark `quote_mark` ([Fonts](#fonts)).

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
[Action targets](#beat-actions): `step<N>` (1-based), `caption`, `term:<tex>` for each of `terms` (in the step on
screen). A step that a `transform` or `reveal` action brought in early is not shown again, and
earlier steps are skipped once a later one is on screen.

| param | type | default | |
|---|---|---|---|
| `latex` | str \| list[str] | required | math-mode LaTeX (no `$`); a list is a sequence of steps |
| `caption` | str | `""` | |
| `size` | size | `96` | formula size (1.25x in a vertical frame; shrunk to fit the width) |
| `caption_size` | size | `caption` | |
| `color`, `caption_color` | color | `text`, `dim` | |
| `terms` | list[str] | `[]` | TeX substrings beat actions can target as `term:<tex>` (e.g. `2ab`); each must occur in a step and be a complete TeX group there (not half of a `\frac{..}{..}`); its first occurrence in a step counts |

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

For a derivation — notes per step, earlier steps kept above, matching parts that move, a boxed
result — use [`equation_derivation`](#equation_derivation).

### `equation_derivation`

A derivation: a sequence of equations where each step **morphs into the next** — the parts that
stay the same move into their new place, the rest fades — with an optional **note** per step
(the justification: "divide both sides by 2"), earlier steps kept above the current one or
replaced by it, and a **box** around the result. Steps: one per entry of `steps` (step 1 comes
with the title); with more steps than beats they are spread evenly; extra beats hold. **Needs
LaTeX**, like [`equation`](#equation); a step that does not compile stops the render with the
step's number, its LaTeX and TeX's own message (`step 2 does not compile: Undefined control
sequence (at: \badcommand {2})`). Unbalanced braces and unclosed `{{` are reported by `vidgen
validate`.

**Per-beat data** lives in `steps`, aligned with the beats (as in
[`code_walkthrough`](#code_walkthrough)): entry *i* is beat *i*, written `{tex, note, match,
transition}` or just the LaTeX string.

**Marking matching parts.** Between two steps, parts written the same way move into each other
when they are *marked*; everything else moves glyph by glyph when the shapes match (a `+` that
stays a `+`) and fades otherwise. Three ways to mark a part:

- `{{ ... }}` around it in both steps (Manim's notation: put a space, or the start of the
  formula, before `{{`): `'{{ 2x }} + 3 = 11'` → `'{{ 2x }} = 8'` moves `2x` as one piece;
- `match: [...]` on a step: those parts are isolated in that step and the one before
  (`{tex: '(a+b)(a+b)', match: ['(a+b)']}`);
- `terms` and the keys of `colors`: isolated in every step.

Parts are compared as TeX tokens, spaces ignored (`2 ab` = `2ab`), and found only as whole tokens
(`x` is not taken out of `\exp`; a part right after `\left` is left alone). A part must be a
complete TeX group (not half of a `\frac{..}{..}`). The alignment sign (`align_at`) is always
isolated, so `=` stays in place from step to step. `transition: shapes` matches glyphs by shape
only, `fade` cross-fades.

**History or replace.** `mode: history` (default) keeps the earlier steps on screen, stacked
above the current one, dimmed (`dim_opacity`, raised where a colour would fall below 2.3:1
contrast) and aligned at the first `align_at` of each step (`=`; a step without it is centred);
the block stays centred as it grows. When the steps do not fit at a readable size, the oldest
scroll away (`keep` sets how many stay). `mode: replace` shows one step at a time, each taking the
place of the previous one (still aligned at `=`, so the sign does not jump).

**Notes** sit beside the equations, level with their step, in 16:9 (earlier notes stay, dimmed,
with their steps) and in a band just below them in a vertical frame (one at a time);
`note_position: bottom` uses the band in 16:9 too.

**Sizes.** All steps share one size: `size` at most (1.25x in a vertical frame), smaller to fit
the widest step and the stacked steps. A step that would be set below 1.5x the readable size
(lint's `min_font`) is broken into lines before its relations (`a = b \\ = c`, aligned at the
sign), when that makes it larger; if it still does not fit it is scaled down further and a
warning says so (shorten the step, or split it in two).

**Colours.** `colors: {x: accent, '\lambda': highlight}` colours those parts in every step (and
in the dimmed history), so a variable keeps its colour through the derivation.

**Result.** `result: box` (default) draws a frame around the last step as it arrives,
`highlight` lays a band of `result_color` behind it, `none` leaves it plain.

[Action targets](#beat-actions): `title`, `step<N>` (a step, also as a dimmed earlier line),
`note<N>` (revealing a note plays its step), `result` (the last step with its box) and
`term:<tex>` for each part named in `terms`, `colors`, `match` or marked `{{ }}` — in the
**current** step (earlier, dimmed lines are not included). `transform: step1` + `into: step3`
jumps ahead; the steps in between are skipped and the result still gets its box.

| param | type | default | |
|---|---|---|---|
| `steps` | list (≥ 1) | required | step *i* at beat *i*: `{tex, note, match, transition}` or the LaTeX string |
| `steps[].tex` | str | required | math-mode LaTeX (no `$`); `{{ ... }}` marks a part that moves into the same part of the next step |
| `steps[].note` | str | `""` | a short justification shown with the step |
| `steps[].match` | list[str] | `[]` | parts that move from the previous step into this one (must occur in both) |
| `steps[].transition` | `auto` \| `shapes` \| `fade` | `auto` | `auto`: marked parts, then glyphs by shape |
| `title` | str | `""` | heading above the derivation |
| `mode` | `history` \| `replace` | `history` | keep earlier steps (stacked, dimmed) or replace them |
| `keep` | int (≥ 1) | as many as fit | `history`: the most steps on screen; older ones scroll away |
| `align_at` | str | `"="` | steps are aligned at the first occurrence of this TeX (`'\le'`, ...); `""` centres every step |
| `colors` | map TeX → color | `{}` | parts coloured in every step |
| `terms` | list[str] | `[]` | more parts to isolate in every step (they move into each other; targets `term:<tex>`) |
| `result` | `box` \| `highlight` \| `none` | `box` | how the last step is marked |
| `result_color` | color | `highlight` | |
| `size` | size | `80` | largest formula size (1.25x in a vertical frame; smaller to fit) |
| `color` | color | `text` | formula colour |
| `dim_opacity` | number (0.15–1) | `0.45` | `history`: opacity of earlier steps and their notes |
| `note_position` | `auto` \| `side` \| `bottom` | `auto` | `auto`: beside in 16:9, below in a vertical frame (always below there) |
| `note_size` | size | `body` | |
| `note_color` | color | `dim` | |
| `note_mark_color` | color | `accent` | the bar beside each note (16:9) |

```yaml
- id: solve
  type: equation_derivation
  params:
    title: "Solving for x"
    colors: {x: accent}                    # x keeps its colour in every step
    steps:
      - '{{ 2x }} + 3 = 11'                # {{ }} marks a part that moves into the next step
      - {tex: '{{ 2x }} = 11 - 3', note: "Subtract 3 from both sides"}
      - {tex: '{{ 2x }} = 8', note: "Simplify"}
      - {tex: 'x = \frac{8}{2}', note: "Divide both sides by 2"}
      - {tex: 'x = 4', note: "The result"}
  beats:
    - text: "Two x plus three equals eleven."
    - text: "Subtract three from both sides."
    - text: "Eleven minus three is eight."
    - text: "Divide both sides by two."
    - text: "And x is four."
```

### `code`

Steps: (1) the listing (with the first highlight applied), then one per further `highlight`
entry. Highlighting dims the other lines and puts a soft band behind the selected ones. Uses
Manim's `Code` (Pygments highlighting); the listing is scaled to fill the space below the
title. When its width would make it smaller than `size` (typical for long lines in a vertical
video), long lines are wrapped with a hanging indent (`wrap`); wrapped lines keep their line
number and highlights still count original lines. Wrapping aims for at least 32 characters per
line: where `size` would leave fewer (a vertical frame, especially with the `large` type scale),
the listing is set smaller instead, down to the readable minimum (`lint` `min_font`), and wraps
there. For code longer than the frame holds, use [`code_walkthrough`](#code_walkthrough).
[Action targets](#beat-actions): `title`, `listing` (the window), `line<N>` (an original line,
1-based, with its number; all its pieces when wrapped) and `lines:<a-b>` (lines a to b,
`lines:3-5`). The scene's own `highlight` steps set line opacities, overriding a `dim` action on
those lines.

| param | type | default | |
|---|---|---|---|
| `code` | str | — | inline code; give exactly one of `code` / `path` |
| `path` | str | — | file in the project (checked by `vidgen validate`) |
| `language` | str | from the file name, else `python` | a Pygments lexer name |
| `title` | str | `""` | |
| `highlight` | list of line specs | `[]` | entry *i* applies at beat *i*: `3`, `"2-4"`, `"1, 5-6"` or `[1, 4]` (1-based) |
| `line_numbers` | bool | `true` | |
| `style` | str | theme `code_style` | a Pygments style (`monokai`, `dracula`, `xcode`, ...); default: the theme's `code_style` (`github-dark`, `xcode` in `light_academic`) |
| `font` | str | role `code` (`font_mono`: JetBrains Mono NL) | font family of the listing |
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

### `code_walkthrough`

A long listing in a window of fixed height that scrolls, beat by beat, to the lines the narration
talks about. Steps: one per entry of `steps` (step 1 comes with the window): the window scrolls
smoothly so the step's `lines` are in view (centred, or left where they are when they already
show), the other lines dim and a band marks the selected ones; the step's `note` appears beside
the lines or below the window, and `focus` moves the camera in on them. A step without `lines`
keeps the previous lines and view (e.g. a second note on the same lines); `lines: all` removes the
highlight. With more steps than beats they are spread evenly; extra beats hold.

**Lines** are written as in [`code`](#code) — `12`, `"3-7"`, `"1, 5-6"`, `[3, 4]` — or by content:
`"/def train/"` is the first line the regular expression matches (Python syntax, searched within
each line), `"/def train/-/return/"` runs from there to the first match of the second expression
at or after it, and numbers and expressions mix (`"40-/return/"`). Numbers are the file's own:
with `excerpt: "40-120"` only those lines are shown and steps count from 40. `vidgen validate`
reports lines past the end and expressions that match nothing.

**Per-beat data** lives in `steps`, aligned with the beats like `code`'s `highlight` and
`diagram`'s `steps`: entry *i* is beat *i*. An entry is `{lines, note, focus}` or just a line
spec (`- "3-7"`).

**Size and wrapping.** The listing keeps `size` while the window's width allows (it is never
scaled up), else gets smaller down to the readable minimum (or the size that keeps 32 characters
per line, if larger) and wraps long lines there, with their numbers kept (as in `code`). The
window is as tall as the space allows (`visible` caps it); in a 16:9 frame that is about 9 lines at
the `caption` size, with notes below. A scroll indicator on the right shows where the view is.
Syntax colours that would read poorly on the window or on the highlight band (a Pygments `style`
that does not suit the theme) are mixed towards the theme's `text` colour, and the band is made
fainter on themes where it would cost contrast.

**Notes.** `note_position: side` puts each note in a callout beside the window, level with its
lines and pointing at them; `bottom` puts it in a bar under the window (as tall as the tallest
note, so the window does not change size). `auto` uses `side` in 16:9 when the code fits beside
the notes without wrapping (lines up to about 40 characters at `caption`), else `bottom`; a
vertical frame always uses `bottom`. A note belongs to its step and goes with it.

**Focus.** `focus: true` moves the camera in on the step's lines (as close as they fit, at most
`focus_scale`; a number sets the magnification) while the other lines fade out, and shows the
note as a card under them at its normal size. The next step without `focus` moves the camera
back. The camera never stops halfway through the title. Very wide lines leave little to enlarge
(the camera stays, with a warning).

[Action targets](#beat-actions): `title`, `listing` (the window), `line<N>` (a line by its number,
with its number label; all its pieces when wrapped), `lines:<a-b>` (every range in listings of
up to 40 lines; in longer ones the ranges the steps select, as `lines:12-18`) and `note<N>` (the
note of step N). Revealing a line that is out of view scrolls to it; revealing a note plays its
step. The scene's own steps set line opacities, so a `dim` action on lines lasts until the next
step.

| param | type | default | |
|---|---|---|---|
| `code` | str | — | inline code; give exactly one of `code` / `path` |
| `path` | str | — | file in the project (checked by `vidgen validate`) |
| `language` | str | from the file name, else `python` | a Pygments lexer name |
| `excerpt` | str | none | `"a-b"`: show only those lines of the code (they keep their numbers) |
| `title` | str | `""` | above the window |
| `steps` | list | `[]` | step *i* at beat *i*: `{lines, note, focus}` or a line spec; none: the listing from the top, no highlight |
| `steps[].lines` | line spec | none (keep) | `12`, `"3-7"`, `"1, 5-6"`, `[3, 4]`, `"/regex/"`, `"/a/-/b/"`, or `all` (no highlight) |
| `steps[].note` | str | `""` | short annotation of the step |
| `steps[].focus` | bool \| number | `false` | `true`: enlarge the lines (camera); a number (1–4): that magnification |
| `visible` | int (≥ 3) | as many as fit | lines the window shows at once |
| `line_numbers` | bool | `true` | |
| `style` | str | theme `code_style` | a Pygments style |
| `font` | str | role `code` (`font_mono`) | font family of the listing |
| `size` | size | `caption` | font size of the listing (smaller only to fit the width; never below the readable size) |
| `wrap` | bool | `true` | wrap long lines instead of shrinking the listing below `size` / the readable size |
| `highlight_color` | color | `highlight` | band, its edge bar, notes' frame and pointer |
| `note_position` | `auto` \| `side` \| `bottom` | `auto` | see above |
| `note_size` | size | `body` | note text size |
| `note_color` | color | `text` | note text colour |
| `focus_scale` | number (1–4) | `2.0` | largest magnification of `focus: true` |
| `scrollbar` | bool | `true` | scroll indicator when the code is longer than the window |

```yaml
- id: walkthrough
  type: code_walkthrough
  params:
    title: "Walking through a training loop"
    path: assets/train.py
    steps:
      - {lines: "8-12", note: "All settings live in one small dataclass."}
      - {lines: "/def loss_and_grads/-/loss = gw/", note: "The loss: a mean squared error."}
      - {lines: "/err = /", note: "The prediction error drives it all.", focus: true}
      - "/for batch in/-/b -= /"          # just lines: no note
  beats:
    - text: "A code walkthrough scrolls through a long file. First, the settings."
    - text: "Then it scrolls down to the loss function."
    - text: "Focus enlarges a line: here, the prediction error."
    - text: "And the update itself is plain gradient descent."
```

Building a long listing takes about 0.1 s per line (Manim draws every character); `excerpt`
keeps a big file's walkthrough to the part it talks about.

### `stat`

One big number that counts up, with what it means, an optional comparison and a context line.
Steps: (1) icon, number (counting from `count_from` to `value`, easing out so the last digits
settle) and label, (2) comparison and context; with one beat both come in it.
[Action targets](#beat-actions): `icon`, `value`, `label`, `comparison`, `context` (those present).

Layout, centred in the safe area: icon, number, label, comparison, context. The number is
`size` (default 3x the theme's `title` size) unless that is wider than the frame, then smaller;
the count never changes its size. In a vertical frame the parts are spaced 1.3x further apart.
Numbers use the `heading` font role (serif in `light_academic`/`warm_editorial`).

| param | type | default | |
|---|---|---|---|
| `value` | float | required | the number shown |
| `label` | str | `""` | what the number is, under it |
| `context` | str | `""` | smaller line at the bottom (period, population, source) |
| `prefix`, `suffix` | str | `""` | before/after the number at its size (`"$"`, `"%"`, `"x"`) |
| `unit` | str | `""` | after the number, smaller, on its baseline (`"ms"`, `"users"`) |
| `decimals` | int 0–6 | automatic | decimals of every number shown (also while counting); default: what `value` and the comparison value need, up to 2 |
| `thousands` | str | `","` | thousands separator: `","`, `"."`, `" "`, `"'"` or `""` |
| `decimal_mark` | str | `"."` | `"."` or `","` (e.g. `thousands: "."`, `decimal_mark: ","` for German) |
| `count` | bool | `true` | count up in beat 1; `false`: the number fades in |
| `count_from` | float | `0` | where the count starts; with a `kind: before` comparison, its value |
| `comparison` | number \| mapping | none | a value to compare with (below); a plain number is `{value: N}` |
| `icon` | icon | none | above the number |
| `icon_color`, `color`, `label_color`, `context_color`, `comparison_color` | color | `primary`, `primary`, `text`, `dim`, `dim` | `color` is the number's (prefix, suffix and unit too) |
| `good_color`, `bad_color`, `neutral_color` | color | `tertiary`, `accent`, `dim` | the change chip: better, worse, no change / `better: neither` |
| `size` | size | 3x `title` | number size (shrunk to fit) |
| `label_size`, `context_size`, `comparison_size` | size | `subtitle`, `caption`, `body` | |

**Comparison** (`comparison: {value, label, kind, word, delta, better}`): a row under the label
with the change in a chip (an arrow and the delta, coloured by whether the change is good) and
the words `vs 12% last year`.

| key | default | |
|---|---|---|
| `value` | required | the other value, written with the same prefix, suffix, unit and decimals |
| `label` | `""` | words after it (`"last year"`, `"in 4K"`) |
| `kind` | `versus` | `versus`: "vs 12%"; `before`: a before → after change, the number counts from this value ("from 12%") |
| `word` | `vs` / `from` | the word before the other value (`""` for none; translate it in a language variant) |
| `delta` | `difference` | the chip shows the `difference` (`+19%`, with prefix/suffix/unit), the `percent` change (`+158%`; needs a non-zero value) or `none` (no chip) |
| `better` | `higher` | which direction is good: `higher`, `lower` (costs, latency), `neither` (always neutral) |

```yaml
- id: adoption
  type: stat
  params:
    value: 73
    suffix: "%"
    label: "of developers use AI coding tools"
    comparison: {value: 44, label: "in 2023"}     # chip "▲ +29%" in good_color, "vs 44% in 2023"
    context: "Survey of 12,000 developers, 2025"
  beats:
    - text: "Seventy-three percent of developers now use AI coding tools."
    - text: "Up from forty-four percent two years earlier."
- id: latency
  type: stat
  params:
    value: 12.5
    unit: "ms"
    label: "median latency"
    comparison: {value: 18, kind: before, better: lower, delta: percent}   # counts down from 18
  beats:
    - text: "Median latency fell from eighteen to twelve and a half milliseconds."
```

### `chapter`

A section divider: an optional number, the chapter's `title`, an optional subtitle and icon.
An accent rule draws in, the number (with the icon) and the title slide towards it from either
side, the subtitle rises. In a wide frame with a number or icon, they stand left of a vertical
rule and the title (left-aligned) right of it; otherwise (vertical frames, or only a title) the
parts are stacked and centred, the rule a short line between number and title.
Steps: with two or more beats, (1) rule, icon, number and title, (2) subtitle; with one beat,
or silent with a `duration`, everything comes in together. Further beats hold.
[Action targets](#beat-actions): `icon`, `number`, `title`, `subtitle` (those present).

The chapter's name is its `title` param (what a chapter list or indicator shows; a
`chapter:` key on the scene renames it there, see [chapters](#chapters)).

| param | type | default | |
|---|---|---|---|
| `title` | str | required | the chapter's name; wrapped to fit |
| `number` | int \| str | none | an integer is shown with `number_format` (`02`); text as written (`"II"`, `"Part 2"`) |
| `number_format` | str | `"{:02d}"` | Python format for an integer `number`: `"{}"` gives `2`, `"Part {}"` gives `Part 2` |
| `subtitle` | str | `""` | |
| `icon` | icon | none | above the number, or in its place |
| `rule` | bool | `true` | draw the accent rule |
| `number_color`, `rule_color`, `icon_color`, `title_color`, `subtitle_color` | color | `primary`, `primary`, `primary`, `text`, `dim` | |
| `number_size` | size | 2.4x `title` (1.6x for text) | shrunk to fit |
| `title_size`, `subtitle_size` | size | `title`, `subtitle` | |

```yaml
- id: part2
  type: chapter
  params: {number: 2, title: "Results", subtitle: "What the benchmark shows", icon: chart-line}
  duration: 3                      # silent divider; or give it beats
```

### `comparison`

Two or three columns side by side — A vs B, before / after, three options — each on a card
with a heading, an optional icon and a list of points. A column's `tone` colours it and marks
its points: `positive` (check marks, `positive_color`), `negative` (crosses, `negative_color`)
or `neutral` (dots, `neutral_color`; the heading keeps `heading_color`). An optional `verdict`
line closes the scene. In a vertical frame the columns are stacked.
Steps with `reveal: columns` (default): (1) column 1 (with the heading), (2) column 2, ...,
then the verdict; `reveal: rows`: (1) the column headings, then one point of every column per
step (side by side, the *m*-th points of all columns share a line), then the verdict; `reveal:
all`: every column in step 1, the verdict in step 2.
[Action targets](#beat-actions): `heading`, `col<N>`, `col:<heading>`, `col<N>.item<M>`
(1-based) and `verdict`.

Layout: heading in the `header` region, verdict at the bottom, the cards share the rest
(columns in 16:9, rows in 9:16) and are as tall as the tallest column. Point text starts at
`size` (1.3x in a vertical frame, like the column headings and the verdict) and is reduced
together in every column, not below the readable minimum, until the
columns fit; a comparison that still does not fit is scaled down with a warning (shorten or
remove points).

| param | type | default | |
|---|---|---|---|
| `columns` | list (2–3) | required | `{heading, icon, tone, points}` per column (below) |
| `heading` | str | `""` | above the columns |
| `verdict` | str | `""` | the conclusion, shown in a last step |
| `reveal` | `columns` \| `rows` \| `all` | `columns` | |
| `markers` | bool | `true` | check / cross / dot before each point (a point's own icon always shows) |
| `cards` | bool | `true` | each column on a card in the theme's `surface` colour, outlined in its tone |
| `vs` | str | `""` | text in a small badge between the columns (`"vs"`, `"→"`) |
| `positive_color`, `negative_color`, `neutral_color` | color | `tertiary`, `accent`, `primary` | the tone colours (green and red in every built-in preset) |
| `color`, `heading_color`, `verdict_color` | color | `text`, `text`, `highlight` | point text; scene heading and neutral column headings; verdict |
| `size`, `column_size`, `heading_size`, `verdict_size` | size | `body`, `subtitle`, `heading`, `body` | point text, column headings (reduced with the points), scene heading, verdict |

A column is `{heading, icon, tone, points}`: `heading` (required), `icon` (left of the heading,
in the tone colour), `tone` (`positive`, `negative` or `neutral`, the default) and `points`
(up to 8; each a string or `{text, icon}`, the icon replacing the marker).

```yaml
- id: tradeoff
  type: comparison
  params:
    heading: "Monolith or microservices?"
    vs: "vs"
    columns:
      - heading: "Monolith"
        icon: package
        tone: positive
        points: ["One deploy", "Simple local setup", {text: "Easy refactoring", icon: pencil}]
      - heading: "Microservices"
        icon: network
        tone: negative
        points: ["Many deploys to coordinate", "Network failures between services"]
    verdict: "Start with a monolith; split when teams grow."
  beats:
    - text: "A monolith is one deploy with a simple setup."
    - text: "Microservices mean many deploys and network failures."
    - text: "So start with a monolith."
      actions:
        - {highlight: col1, style: box}
```

### `table`

A header and rows of cells (text or numbers), fitted to the frame, revealed row by row.
Number columns are right-aligned and formatted (`number_format`, default: the decimals the
column needs, with thousands separators); text columns are left-aligned. Every other row is
striped in `stripe_color` (the theme's `surface`); a rule in `header_color` runs under the
header and a thin one under the last row.
Steps with `reveal: per_beat` (default): (1) title, header, caption and row 1, (2) row 2, ...;
with more rows than beats they are spread evenly. `reveal: all`: the whole table in beat 1.
[Action targets](#beat-actions): `title`, `header`, `row<N>`, `row:<first cell>`, `col<N>`,
`col:<header>`, `cell<R>.<C>` and `caption` (1-based; rows count below the header; a row's
first cell as shown, e.g. `row:4K`, `cell2.3`). A `highlight` with `style: fill` lays a
translucent band over a row, column or cell; `box` frames it.

**Fitting.** The title is in the `header` region (1.3x in a vertical frame, like every header
band), the caption at the bottom; the table is centred in the space between, and a table
shorter than that space takes its caption along (just under it, the two centred together). Cell text starts at `size`; when the table is too wide, columns
share the width (a column that needs less keeps its natural width) and text wraps — headings
at any space, body cells of more than 16 characters at spaces; numbers and short cells never
wrap. The size is then reduced until the table fits, not below the readable minimum (lint's
`min_font`). A table that does not fit even then is scaled down and a warning says so: split
it into smaller tables (or drop columns), which is mostly a vertical (9:16) problem — a 9:16
frame holds about 3–4 columns and 12 short rows. In 9:16 rows get more vertical padding.

| param | type | default | |
|---|---|---|---|
| `rows` | list of lists | required | 1–30 rows of cells: text or numbers (`""` for an empty cell); every row as long as the header |
| `header` | list[str] | `[]` | column headings; sets the number of columns (at most 8) |
| `title` | str | `""` | above the table |
| `caption` | str | `""` | note under the table (e.g. the source) |
| `align` | str \| list | `auto` | `auto` (numbers right, text left), `left`, `center`, `right`; one for all columns or one per column |
| `number_format` | str \| list | automatic | Python format for numbers: `"{:,.1f}"`, `"{:.0%}"`, `"${:,.0f}"`, `"{:,.0f}M"`; one for all or one per column (`null` = automatic) |
| `reveal` | `per_beat` \| `all` | `per_beat` | |
| `zebra` | bool | `true` | stripe every other row |
| `color`, `header_color`, `stripe_color`, `rule_color` | color | `text`, `primary`, `surface`, `dim` | cells; header text and its rule; stripes; the rule under the last row |
| `title_color`, `caption_color` | color | `text`, `dim` | |
| `size`, `title_size`, `caption_size` | size | `body`, `heading`, `caption` | `size` is the cell text (headings too), reduced to fit |

```yaml
- id: results
  type: table
  params:
    title: "Benchmark"
    header: ["Model", "Params", "Accuracy"]
    rows:
      - ["Baseline", 110, 0.812]
      - ["Sparse", 55, 0.809]
      - ["Tiny", 14, 0.742]
    number_format: [null, "{:,.0f}M", "{:.1%}"]   # 110M, 81.2%
    caption: "Illustrative numbers"
  beats:
    - text: "The baseline has a hundred and ten million parameters."
    - text: "The sparse model halves that and loses almost nothing."
      actions:
        - {highlight: "row:Sparse", style: fill}
    - text: "The tiny model pays for its size."
      actions:
        - {highlight: "cell3.3", color: accent}
```

### `timeline`

Dated events along an axis: a horizontal one in 16:9 and square frames, a vertical one in 9:16
(`orientation` overrides). Each event is a marker on the axis (a disc with its icon when the
timeline has icons) and its date, title and optional detail text; events alternate sides of the
axis so neighbours do not collide (or all stand on one side — `sides: auto` picks whichever
keeps the text largest, typically alternating in 16:9 and one column right of the axis in 9:16).
As each event is revealed, a progress line grows along the axis to it.
Steps with `reveal: per_beat` (default): (1) heading, axis and event 1, (2) event 2, ...; with
more events than beats they are spread evenly. `reveal: all`: every event in step 1. A
`highlight` adds a last step: the other events dim, the chosen marker and title turn
`highlight_color`.
[Action targets](#beat-actions): `heading`, `axis`, `event<N>` and `event:<date>` (1-based; the
date as shown, e.g. `event:1969`; an event is its marker, stem and text).

**Spacing.** `even` (default) puts the events at equal gaps. `proportional` places them by date:
a number (`1969`, `2.5`), a year, `YYYY-MM` or `YYYY-MM-DD` (unquoted `2024-03-15` works too),
or an event's own `at` for anything else (`"500 BC"` with `at: -500`); events must be in time
order, and neighbours that are too close are pulled apart just enough to keep their markers
apart.

**Now.** `now` names the present event (0-based index, date or title): it gets a `now_label`
tag ("Now") and a ring in `now_color`; later events are drawn as planned (hollow markers, a
dashed progress line).

**Fitting.** Every event's text shares one size: up to 1.2x the requested sizes (1.5x along a
vertical axis, which has much more room) when every event has room without more wrapping, else reduced together down to the readable minimum (lint's
`min_font`); lines are wrapped to even lengths. A timeline that still does not fit is scaled
down and a warning says so: split it into two timelines or shorten the texts. 10 events with
detail texts are the limit of a 9:16 frame; 3–6 read best (and stay under lint's `max_words`).

| param | type | default | |
|---|---|---|---|
| `events` | list (2–10) | required | `{date, title, text, icon, at}` per event, in time order (below) |
| `heading` | str | `""` | above the timeline, with step 1 |
| `orientation` | `auto` \| `horizontal` \| `vertical` | `auto` | `auto`: horizontal in landscape and square frames, vertical in portrait |
| `sides` | `auto` \| `alternate` \| `one` | `auto` | alternate sides of the axis, or all below a horizontal / right of a vertical axis; `auto` picks the layout with the largest text (then the fewest lines) |
| `spacing` | `even` \| `proportional` | `even` | proportional: gaps follow the dates (or `at`) |
| `reveal` | `per_beat` \| `all` | `per_beat` | |
| `highlight` | int \| str | none | event emphasised in a last step: 0-based index (an int in range), or its date or title |
| `now` | int \| str | none | the present event (as `highlight`): a tag and ring; later events hollow with a dashed progress line |
| `now_label` | str | `"Now"` | text of the tag |
| `color`, `date_color`, `text_color` | color | `text`, `primary`, `dim` | event title, date, detail text |
| `marker_color`, `axis_color`, `progress_color` | color | `primary`, `dim`, `primary` | markers and their icons; the axis (drawn faint); the progress line |
| `heading_color`, `highlight_color`, `now_color` | color | `text`, `highlight`, `accent` | |
| `size`, `date_size`, `text_size`, `heading_size` | size | `body`, `caption`, `caption`, `heading` | event title, date, detail text (all fitted together), heading |

An event is `{date, title, text, icon, at}`: `date` (required; text or a number, shown above the
title), `title` (required), `text` (a detail line, smaller and dimmer), `icon` (in the event's
marker) and `at` (a number: its position with `spacing: proportional` when the date is not one).

```yaml
- id: history
  type: timeline
  params:
    heading: "The space race"
    spacing: proportional            # gaps follow the years
    events:
      - {date: 1957, title: "Sputnik", text: "First satellite in orbit", icon: satellite}
      - {date: 1961, title: "Gagarin", text: "First human in space", icon: user}
      - {date: 1969, title: "Apollo 11", text: "First crewed Moon landing", icon: moon}
    highlight: "Apollo 11"           # a last step: the other events dim
  beats:
    - text: "In 1957 Sputnik reached orbit."
    - text: "Four years later, Gagarin flew."
    - text: "In 1969, Apollo 11 landed on the Moon."
    - text: "The landing is still the high point."
      actions:
        - {highlight: axis, style: flash}
```

### `diagram`

A flowchart or any directed graph — a pipeline, an architecture, a decision tree, a state
machine — laid out automatically: nodes in layers along the edges' direction (left to right in
16:9 and square frames, top to bottom in 9:16; `direction` overrides), each layer ordered to
avoid crossing edges, edges routed between the nodes with arrowheads that end on the node's
outline. A cycle (an edge back to an earlier node) is drawn as one edge running backwards. Also
available as type **`flowchart`** (the same scene).
Steps with `reveal: nodes` (default): one node per step in layout order (layer by layer; within
a layer top to bottom or left to right), each after the edges leading to it from nodes on
screen have grown in from their source; the heading comes with step 1. `reveal: layers`: one
layer per step; `all`: everything in step 1. With more steps than beats they are spread evenly.
**Explicit `steps`** replace that: per step a node id or an edge `"a->b"`, or a list of them.
An edge appears with its nodes unless a later step names it (then it grows in that step); an
edge named in a step brings its nodes; nodes no step names come in one more step at the end.
A `highlight` adds a last step: the listed nodes and edges turn `highlight_color` (outline,
tint, icon, line; labels keep their colour) and everything else dims — list a path as node ids
(`[start, check, ship]`: the edges between consecutive ones are highlighted too) and add single
edges as `"a->b"`.
[Action targets](#beat-actions): `heading`, `node<N>` (1-based, in the order of `nodes`),
`node:<id>` and `edge:<from>-><to>` (`edge:check->ship`; patterns such as `edge:check->*`
select every edge leaving a node). Revealing an edge early brings its nodes too.

**Nodes** are written as their id (`- Load data`: the id is also the label) or as
`{id, label, shape, icon, color}`: `id` (letters, digits, spaces, `_`, `.`, `-`), `label` (the
text, wrapped; default the id), `shape` (`box`, `round` (rounded corners), `pill` (start/end),
`circle`, `diamond` (a decision), `cylinder` (a database); default the scene's `shape`),
`icon` (above the label in left-to-right layouts, circles and diamonds; else beside it) and `color` (outline, tint and
icon; default `node_color`).

**Edges** use a shorthand: `"a -> b"`, `"a -> b: label"` (text on the edge, near its start),
`"a --> b"` (dashed), or a chain `"a -> b -> c"` (one edge per arrow; a label needs a single
arrow). The long form is `{from, to, label, style: solid | dashed, color}`. Each edge may be
listed once, a node may not point to itself, and every id must be a node: `vidgen validate`
reports e.g. `edges[2] (start -> shp): unknown node 'shp'; did you mean 'ship'? (nodes: ...)`.

**Fitting.** Labels share one size: up to 1.3x the requested `size` when the diagram has room,
else reduced (with the edge labels) down to the readable minimum (lint's `min_font`); per
direction (with `auto`, the other one is tried too and wins only if it keeps the text 10 %
larger) and label wrap width the layout with the largest text is used, and spare room widens the
gaps. A diagram that still does not fit is scaled down and a warning says so: split it or
shorten the labels. Up to ~12 nodes read well in 16:9, fewer in 9:16 (wide layers do not fit a
narrow frame; long chains do).

| param | type | default | |
|---|---|---|---|
| `nodes` | list (1–30) | required | node ids, or `{id, label, shape, icon, color}` (above) |
| `edges` | list (≤ 60) | `[]` | `"a -> b"`, `"a -> b: label"`, `"a --> b"`, `"a -> b -> c"`, or `{from, to, label, style, color}` |
| `heading` | str | `""` | above the diagram, with step 1 |
| `direction` | `auto` \| `LR` \| `TB` | `auto` | layers left to right or top to bottom; `auto`: `LR` in landscape and square frames, `TB` in portrait |
| `routing` | `curved` \| `straight` \| `orthogonal` | `curved` | smooth S-curves, straight lines, or right angles (each edge in its own lane) |
| `reveal` | `nodes` \| `layers` \| `all` | `nodes` | ignored when `steps` is given |
| `steps` | list | none | per step a node id, an edge `"a->b"`, or a list of them |
| `highlight` | list[str] | `[]` | node ids (a path: edges between consecutive ones too) and edges `"a->b"`, emphasised in a last step |
| `shape` | `box` \| `round` \| `pill` \| `circle` \| `diamond` \| `cylinder` | `round` | default node shape |
| `node_color`, `label_color` | color | `primary`, `text` | node outline / tint / icon; label text |
| `edge_color`, `edge_label_color` | color | `dim`, `dim` | |
| `heading_color`, `highlight_color` | color | `text`, `highlight` | |
| `size`, `edge_label_size`, `heading_size` | size | `body`, `caption`, `heading` | node labels and edge labels are fitted together |

```yaml
- id: release
  type: flowchart                    # = diagram
  params:
    heading: "How a change ships"
    nodes:
      - {id: start, label: "Pull request", shape: pill}
      - {id: ci, label: "Tests pass?", shape: diamond}
      - {id: fix, label: "Fix the code"}
      - {id: ship, label: "Deploy", icon: rocket, shape: circle}
    edges:
      - "start -> ci"
      - "ci -> ship: yes"
      - "ci -> fix: no"
      - "fix --> ci"                 # dashed; a cycle is drawn as an edge running back
    highlight: [start, ci, ship]     # the happy path, in a last step
  beats:
    - text: "Every change starts as a pull request."
    - text: "If the tests fail, we fix the code and try again."
      actions:
        - highlight: "edge:fix->ci"
          style: flash
    - text: "Otherwise it is deployed."
    - text: "That is the path most changes take."
```

### `flowchart`

The same scene type as [`diagram`](#diagram) (same params, steps and targets), under the name a
flowchart is usually looked up by.

### `process`

A pipeline of 2–8 stages that something passes through — a request, an order, a batch of data —
with a **token** (a dot, or an icon) that travels from stage to stage. Stages stand in a row in
16:9 and square frames, in two rows when that keeps the text clearly larger (the second row runs
back, "snaking"; typical for 6–8 stages), and in a column in 9:16 (`layout` overrides). Each
stage is a card with its label, an optional icon and an optional detail line; connectors with
arrowheads join them.
Steps with `reveal: per_beat` (default): (1) heading, `input` and stage 1 (the token arrives at
it), (2) the connector to stage 2 grows while the token travels along it and stage 2 appears, ...;
the `output` comes with the last stage. The stage where the token is is the **active** one: its
outline and icon turn `active_color`, and the previous stage returns to normal. `loop: true` adds
an arrow from the last stage back to the first (below a row, beside a column) and a last step in
which the token follows it. `reveal: all` shows the whole pipeline in step 1; the following steps
only move the token, one stage per step. With more steps than beats they are spread evenly.
While travelling, the token passes behind the stage it leaves and waits in front of the next
one, on its connector's arrowhead.
[Action targets](#beat-actions): `heading`, `input`, `stage<N>` (1-based), `stage:<label>`,
`connector<N>` (from stage N to N+1), `loop`, `output` and `token` (those the pipeline has).

**Fitting.** Stage texts share one size: up to 1.2x the requested sizes (1.5x in a column)
when the pipeline has room without more wrapping, else reduced together down to the readable minimum (lint's `min_font`); `input`/`output`
labels stand above their arrows (above and below a column). A pipeline that still does not fit
is scaled down and a warning says so: shorten the texts or split it into two scenes. Short
labels with an optional detail line read best; 3–5 stages with details fit a 16:9 row.

| param | type | default | |
|---|---|---|---|
| `stages` | list (2–8) | required | a label, or `{label, icon, text}` per stage (labels must differ) |
| `heading` | str | `""` | above the pipeline, with step 1 |
| `layout` | `auto` \| `row` \| `snake` \| `column` | `auto` | `auto`: a column in portrait frames, else a row (two snaking rows when that keeps the text 10 % larger) |
| `reveal` | `per_beat` \| `all` | `per_beat` | `all`: the whole pipeline in step 1, then the token moves one stage per step |
| `loop` | bool | `false` | an arrow from the last stage back to the first; the token follows it in a last step |
| `loop_label` | str | `""` | text on the loop arrow (`repeat`, `next batch`); needs `loop` |
| `input`, `output` | str | `""` | what goes in / comes out, with an arrow into the first / from the last stage |
| `token` | bool | `true` | the travelling token |
| `token_icon` | icon | none | draw the token as this icon in a small disc instead of a dot |
| `token_label` | str | `""` | a short tag that travels with the token (`order`, `request`) |
| `stage_color`, `active_color` | color | `primary`, `highlight` | card outlines and icons; those of the active stage |
| `label_color`, `text_color` | color | `text`, `dim` | stage labels, detail lines |
| `connector_color`, `token_color` | color | `dim`, `accent` | connectors and loop arrow; the token and its tag |
| `io_color`, `heading_color` | color | `dim`, `text` | input, output and loop labels; heading |
| `size`, `text_size`, `io_size`, `heading_size` | size | `body`, `caption`, `caption`, `heading` | stage labels, detail lines (fitted together), input/output/loop/token labels, heading |

```yaml
- id: orders
  type: process
  params:
    heading: "What happens to an order"
    input: "Checkout"
    output: "At your door"
    token_label: "order"
    stages:
      - {label: "Pay", icon: credit-card, text: "card or invoice"}
      - {label: "Pack", icon: package}
      - {label: "Ship", icon: truck, text: "1-2 days"}
  beats:
    - text: "At checkout, the order is paid."
    - text: "The warehouse packs it."
    - text: "And a courier ships it to your door."
      actions:
        - {highlight: token, style: flash}
```

### `network`

A layered neural network: layers of units (dots) joined by edges, left to right in 16:9 and
square frames, top to bottom in 9:16 (`direction` overrides). A layer larger than `max_neurons`
shows `show` units with an ellipsis between them (half before it, half after) and its unit count
under the label, e.g. 6 dots for a layer of 512. Each layer connects to the previous one
`dense` (every unit to every unit), `sparse` (a reproducible share `ratio` of the pairs, every
unit keeping a connection), `grouped` (both layers split into `groups` blocks, block to block,
coloured by block from the theme palette as in grouped convolutions), `one_to_one` or `none`;
the scene's `connect` is the default, a layer's `connect` overrides it. Edges are drawn between
the units shown (at most `max_edges` per pair of layers, thinned evenly beyond that), thinner
and fainter the more there are, so wide layers do not turn into a hairball.
Steps with `reveal: layers` (default): (1) heading and layer 1, (2) the edges into layer 2 grow
from layer 1, then its units appear, ...; `reveal: all`: the whole network in step 1. Then
`passes` forward passes (default 1), each a step: a pulse in `pulse_color` runs along the edges
layer by layer and each layer's units flash as it arrives. A `highlight` adds a last step: the
listed units grow and turn `highlight_color`, so do the edges between consecutive ones in
neighbouring layers (drawn if the connection had none), and everything else dims.
[Action targets](#beat-actions): `heading`, `layer<N>` (1-based; units, ellipsis, label and
count), `layer:<label>`, `edges<N>` (between layer N and N+1, if they have edges) and
`neuron<L>.<i>` (unit i of layer L as drawn, 1-based from the top or left, the ellipsis not
counted: `neuron2.3`).

| param | type | default | |
|---|---|---|---|
| `layers` | list (2–8) | required | a size, or `{size, label, show, connect, color}` per layer, input first (below) |
| `heading` | str | `""` | above the network, with step 1 |
| `connect` | connection | `dense` | how each layer connects to the previous one: `dense`, `sparse`, `grouped`, `one_to_one`, `none`, `"sparse:0.3"`, `"grouped:3"` or `{type, ratio, groups}` |
| `direction` | `auto` \| `LR` \| `TB` | `auto` | `auto`: `TB` in portrait frames, else `LR` |
| `max_neurons` | int (2–12) | `8` | layers with more units are drawn with an ellipsis |
| `show` | int (2–12) | `6` | units drawn for such a layer (a layer's `show` overrides it) |
| `counts` | `auto` \| `all` \| `none` | `auto` | unit counts under the labels: `auto` only for layers drawn with an ellipsis |
| `count_format` | str | `"{n:,}"` | Python format of the count with `n` (`"{n:,} units"`) |
| `reveal` | `layers` \| `all` | `layers` | |
| `passes` | int (0–4) | `1` | forward-pass steps after the network is built |
| `highlight` | list[str] | `[]` | units as `"layer.unit"` (1-based, as drawn): `["1.2", "2.3", "3.1"]` marks a path in a last step |
| `max_edges` | int (4–200) | `64` | most edges drawn between two layers |
| `neuron_color`, `edge_color` | color | `primary`, `dim` | units (unless a layer sets `color`); edges |
| `group_colors` | bool | `true` | colour `grouped` edges by block (theme palette) |
| `edge_opacity` | float | auto | edge opacity; default lower the more edges a pair of layers has |
| `label_color`, `count_color` | color | `text`, `dim` | layer labels, counts |
| `pulse_color`, `highlight_color`, `heading_color` | color | `accent`, `highlight`, `text` | |
| `label_size`, `heading_size` | size | `caption`, `heading` | labels and counts (never below the readable minimum), heading |

A layer is `{size, label, show, connect, color}`: `size` (required; the number of units it
has), `label`, `show` (units drawn when it is larger than `max_neurons`), `connect` (to the
previous layer; not on the first layer) and `color` (its units). A connection's long form is
`{type, ratio, groups}` (`ratio` 0.35 for `sparse`, `groups` 2 for `grouped`).

```yaml
- id: mlp
  type: network
  params:
    heading: "A small classifier"
    layers:
      - {size: 784, label: "Pixels", show: 5}
      - {size: 128, label: "Hidden"}
      - {size: 10, label: "Digits", connect: "sparse:0.4"}
    highlight: ["1.2", "2.3", "3.4"]
  beats:
    - text: "Each pixel of the image is an input."
    - text: "A hidden layer of 128 units combines them."
    - text: "Ten outputs score the ten digits."
    - text: "In a forward pass, the signal flows from left to right."
      actions:
        - {highlight: "layer:Digits", style: box, at: 0.5}
    - text: "This path leads to the answer."
```

### `end_card`

Steps: (1) logo, icon and title, (2) lines. Fades out over 1 s.
[Action targets](#beat-actions): `logo`, `icon`, `title`, `line<N>` (1-based; those present).

| param | type | default | |
|---|---|---|---|
| `title` | str | `""` | at least one of `title`, `lines`, `logo`, `icon` |
| `lines` | list[str] | `[]` | links, credits; short lines shrink together instead of wrapping |
| `logo` | str | none | image file in the project (checked by `vidgen validate`) |
| `icon` | icon | none | icon above the title (below the logo, if both) |
| `icon_color` | color | `primary` | |
| `title_color`, `color` | color | `highlight`, `text` | |
| `title_size`, `size` | size | `title`, `body` | |

```yaml
- id: outro
  type: end_card
  params:
    title: "Are LLMs over-parameterized?"
    icon: link
    lines: ["github.com/me/my-project", "huggingface.co/me"]
  beats:
    - text: "Code and models are online. Thanks for watching."
```

### `text_card`

One block of text, wrapped to fit, faded in at the first beat and held (no fade-out).
[Action targets](#beat-actions): `text`.

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

## Beat actions

A beat can act on named parts of its scene — **targets** such as `item3` or `bar:4K` — while it
is spoken: reveal one early, dim it, highlight it, zoom in on it, morph it into another, or
point at it with a callout (also at any spot of the frame). Actions are listed under the beat:

```yaml
- id: sizes
  type: bar_chart
  params: {labels: ["Preview 480p", "720p", "1080p", "4K"], values: [0.4, 1.1, 2.6, 9.8]}
  beats:
    - text: "Bar charts grow their bars while the values count up."
    - text: "Four K takes by far the longest."
      actions:
        - {action: highlight, target: "bar:4K", style: box, until: sizes_b3}   # canonical form
    - text: "Previews are the fast way to iterate."
      actions:
        - dim: [bar2, bar3, bar4]                  # shorthand: {ACTION: TARGET, ...options}
        - highlight: "bar:Preview 480p"
          color: accent                            # an option, in the shorthand too
```

```yaml
- id: square
  type: equation
  params:
    latex: ["(a + b)^2", "(a + b)(a + b)", "a^2 + 2ab + b^2"]
    terms: ["2ab"]                                 # parts of a formula actions can target
  beats:
    - text: "Take a plus b, squared, and jump straight to the result."
      actions:
        - {transform: step1, into: step3, at: 0.5} # step 2's own turn is then skipped
    - text: "The middle term, two a b, comes from the two cross products."
      actions:
        - zoom: "term:2ab"                         # the camera moves in, and is back by the beat's end
    - text: "That is the whole expansion."
```

```yaml
- id: trend
  type: line_chart
  params: {title: "Validation loss", x: [1, 2, 3, 4], series: {baseline: [2.1, 1.8, 1.6, 1.5], sparse: [2.2, 1.7, 1.5, 1.4]}}
  beats:
    - text: "Here is the baseline."
    - text: "And here is the sparse model, which ends lower."
      actions:
        - callout: "point:sparse@4"                # on a target: an arrow from a label to it
          kind: arrow
          label: "Lowest loss"
          at: 0.4                                  # gone when the next beat starts
    - text: "Both start from the same loss."
      actions:
        - {action: callout, kind: box, area: [0.1, 0.15, 0.3, 0.3], label: "Start"}   # coordinates of the frame
```

**Syntax.** The canonical form is a mapping with `action` and the keys below, plus the
action's options. The shorthand `{ACTION: TARGET, ...options}` (as `- dim: item2`) is the
same thing; write the action name as the first key (if a tool sorted the keys, vidgen finds
the one key that names an action).

| key | default | |
|---|---|---|
| `action` | required | `reveal`, `dim`, `highlight`, `zoom`, `transform`, `callout`, or a project action (`vidgen list-scenes` lists them) |
| `target` | required | a target name, a list of names, or a pattern with `*` / `?` (`bar:*`, `item?`) that must match at least one (`callout` with an `area` needs none) |
| `at` | `0` | when, as a fraction of the beat's narration (`0` ≤ at < `1`) |
| `until` | none | a later beat of the same scene: the action lasts until that beat (`dim`, `highlight`, `callout`: undone when it starts; `zoom`: the camera is back when it starts) |
| `run_time` | the action's | seconds the animation takes (`reveal` / `callout` 0.8, `dim` / `highlight` 0.6, `zoom` / `transform` 1.0; a zoom takes as long again to come back) |

**Targets** depend on the scene type (`vidgen list-scenes` prints them as `targets:`). Every
built-in type has some; `<N>` counts from 1 (`item1`, `item2`...), `<text>`/`<label>`/`<name>`
are written out in full (`item:Pick scene types`, or with a pattern: `item:Pick*`). The last
column lists the actions that make sense on them (the others work, but rarely help: a `zoom` on
a title card, a `transform` of a bar).

<!-- targets-table: kept in sync with the scene types by tests/test_actions.py -->
| scene type | targets | useful actions | notes |
|---|---|---|---|
| `title` | `icon`, `kicker`, `title`, `subtitle`, `authors` | reveal, dim, highlight | those the card has |
| `text_card` | `text` | highlight, zoom | |
| `bullets` | `heading`, `item<N>`, `item:<text>` | reveal, dim, highlight, zoom, transform | an item is its row (marker, icon, text) |
| `icon_grid` | `heading`, `item<N>`, `item:<label>` | reveal, dim, highlight, zoom, transform | an item is its icon, label and sublabel |
| `bar_chart` | `title`, `bar<N>`, `bar:<label>` | reveal, dim, highlight, zoom | a bar with its value and category labels; a `box` sits on the axis |
| `line_chart` | `title`, `axes`, `series<N>`, `series:<name>`, `point:<name>@<x>` | reveal, dim, highlight, zoom | a series is its line, markers and end label; `point:sparse@8` |
| `scatter` | `title`, `axes`, `legend`, `series<N>`, `series:<name>`, `point:<series>@<N>`, `point:<series>@<label>`, `trend`, `trend:<series>` | reveal, dim, highlight, zoom | a point is its marker and label; `point:ours@2` is the 2nd point written; `legend` with several series, `trend:` with `trend: each` |
| `histogram` | `title`, `axes`, `legend`, `bin<N>`, `bin:<range>`, `compare`, `mean`, `median` | reveal, dim, highlight, zoom | `bin:10-20` names a bin by its edges; `legend` and `compare` with `compare`; `mean` / `median` when set |
| `pie` | `title`, `slice<N>`, `slice:<label>`, `center`, `legend` | reveal, dim, highlight, zoom | a slice is its wedge, label and leader line (a `box` frames the wedge); `slice:Other` after grouping; `center` with a donut, `legend` with the names in a legend (revealing it reveals every slice); `dim` and `highlight` recolour a label inside its slice so it stays readable on the slice's new look |
| `heatmap` | `title`, `legend`, `row<N>`, `row:<label>`, `col<N>`, `col:<label>`, `cell<R>.<C>` | reveal, dim, highlight, zoom | a row / column is its cells and label (`box` and `fill` cover its cells edge to edge); `cell2.3` is row 2, column 3; `style: box` keeps the data colours (`color` paints the cells, `fill` tints them); values are recoloured to stay readable on dimmed, painted or tinted cells |
| `map` | `title`, `map`, `legend`, `country:<code>`, `pin<N>`, `pin:<label>`, `arc<N>`, `step<N>` | reveal, dim, highlight, zoom | `country:` for highlighted and valued countries, by alpha-3, alpha-2 or name (`country:DEU`, `country:DE`, `country:Germany`): a highlight with its label (revealing it plays its highlight), a valued country its shape; a pin is its dot and label; `step2` is step 2's items (revealing it plays the step); `zoom: country:FRA` looks closer; `dim: map` fades the countries under the highlights |
| `image` | `image`, `caption` | dim, highlight, zoom | `dim` fades the picture, `highlight` tints it |
| `screenshot` | `title`, `image`, `caption`, `callout<N>`, `callout:<label>`, `step<N>` | reveal, dim, highlight, zoom | a callout is its mark and label (`highlight` repaints the mark and the label's plate; its text keeps a readable colour); `callout:New task`; `step2` is step 2's callouts (revealing it plays the step); `zoom: callout3` looks closer; `dim: image` fades the picture under the callouts |
| `video_clip` | `title`, `clip`, `caption`, `callout<N>`, `callout:<label>`, `step<N>` | reveal, dim, highlight, zoom | as in `screenshot`; `clip` is the moving picture with its frame: `dim` fades it, `highlight` tints it, `zoom` looks closer (it is decoded sharper for that) |
| `quote` | `mark`, `quote`, `author`, `source` | reveal, dim, highlight, zoom | |
| `equation` | `step<N>`, `caption`, `term:<tex>` | reveal, dim, highlight, zoom, transform | `term:` for each of the `terms` param, in the step on screen; `transform: step1` + `into: step3` jumps ahead |
| `equation_derivation` | `title`, `step<N>`, `note<N>`, `result`, `term:<tex>` | reveal, dim, highlight, zoom, transform | `term:` for each part in `terms`, `colors`, `match` or marked `{{ }}`, in the current step only; `step2` is also its dimmed line; `note2` (revealing it plays step 2); `result` is the last step with its box |
| `code` | `title`, `listing`, `line<N>`, `lines:<a-b>` | dim, highlight, zoom | a line with its number; `lines:3-5`; a wide line leaves little to zoom |
| `code_walkthrough` | `title`, `listing`, `line<N>`, `lines:<a-b>`, `note<N>` | reveal, dim, highlight | `reveal: line40` scrolls it into view; `lines:<a-b>`: every range up to 40 lines, else the steps' ranges; `note2` is step 2's note (revealing it plays the step); the next step resets line opacities |
| `end_card` | `logo`, `icon`, `title`, `line<N>` | reveal, dim, highlight | those present |
| `chapter` | `icon`, `number`, `title`, `subtitle` | reveal, dim, highlight | those present |
| `stat` | `icon`, `value`, `label`, `comparison`, `context` | reveal, dim, highlight, zoom | `reveal: value` early runs the count; `comparison` is the change chip with its text |
| `comparison` | `heading`, `col<N>`, `col:<heading>`, `col<N>.item<M>`, `verdict` | reveal, dim, highlight, zoom | a column is its heading and points (a `box` frames its card); `col2.item1` is a point with its marker; revealing a point brings its column's card |
| `table` | `title`, `header`, `row<N>`, `row:<first cell>`, `col<N>`, `col:<header>`, `cell<R>.<C>`, `caption` | reveal, dim, highlight, zoom | `box` and `fill` cover the whole row / column / cell; `cell2.3` is row 2 (below the header), column 3 |
| `timeline` | `heading`, `axis`, `event<N>`, `event:<date>` | reveal, dim, highlight, zoom | an event is its marker, stem and text; revealing one grows the progress line to it; `event:1969` |
| `diagram` | `heading`, `node<N>`, `node:<id>`, `edge:<from>-><to>` | reveal, dim, highlight, zoom | also for `flowchart`; a node is its shape, icon and label (a `box` frames the shape), an edge its line, arrowhead and label; `highlight: [node:a, "edge:a->b", node:b]` marks a path; revealing an edge brings its nodes |
| `process` | `heading`, `input`, `stage<N>`, `stage:<label>`, `connector<N>`, `loop`, `output`, `token` | reveal, dim, highlight, zoom | a stage is its card (a `box` frames it); `connector2` runs from stage 2 to 3; revealing a stage early shows it without moving the token; `highlight: token` with `style: flash` points at it |
| `network` | `heading`, `layer<N>`, `layer:<label>`, `edges<N>`, `neuron<L>.<i>` | reveal, dim, highlight, zoom | a layer is its units, ellipsis, label and count; `edges1` joins layers 1 and 2; `neuron2.3` is unit 3 of layer 2 as drawn |

`title` and `heading` stand for each other (the header band, see "Built-in scenes"): `highlight:
title` works on a `bullets` heading. [Project scene types](EXTENDING.md#8-per-beat-actions-targets-and-custom-actions)
can declare their own targets; a type without any rejects actions in `vidgen validate`.

**Actions**

| action | options | |
|---|---|---|
| `reveal` | — | brings the target on screen with the scene's own entrance animation (e.g. item 4 before its turn). A target already on screen is left alone, and the scene does not reveal it again at its own step. |
| `dim` | `opacity` (`0.45`, 0–1, of the target's full opacity) | fades the target; one that is already dimmer (e.g. by `bullets`' `dim_previous`) stays as it is, so dimming never compounds; `until:` restores the opacity |
| `highlight` | `color` (`highlight`, a theme token or hex), `style` (`color` default, `box`, `underline`, `fill`, `flash`, or a list such as `[color, box]`) | `color` recolours the target and brings a dimmed one back to full opacity while highlighted; `box` draws a rounded frame around it, `underline` a line under it, `fill` lays a translucent band of the colour under it (over backdrops such as table stripes and cards); `flash` flashes the colour there and back (leaves no trace; not with `color`). `until:` restores the colours (and the dimming) and removes box / underline / fill. |
| `zoom` | `scale` (magnification > 1, up to 8; default: as close as the targets fit), `padding` (`0.15`: share of the view kept free on each side of the targets) | moves the camera in on the targets and back out: the zoom-out ends with the beat (with `until: <beat>`, when that beat starts). Without `scale` the view is at most 3x; a target that already fills the frame is not zoomed (a warning says so). The view never leaves the frame. |
| `transform` | `into` (required: a target not on screen yet), `style` (`auto` default, `replace`, `shapes`, `tex`, `fade`) | morphs the target into `into`, which then stays on screen in its own place (the target is gone). `shapes` moves matching glyphs (what `auto` uses for text and formulas), `replace` morphs point by point (`auto` for other shapes), `tex` matches the TeX parts of two formulas, `fade` cross-fades. `into` must be a target of the scene; text that is not part of the scene cannot be morphed into (give the scene that content, e.g. as a later equation step). If `into` is already on screen, the target fades out into its place (warning). |
| `callout` | `kind` (`box` default, `circle`, `arrow`, `label`, `spotlight`, `magnifier`), `label`, `area`, `within` (`frame` \| `safe`), `units` (`fraction` \| `px`), `color` (`highlight`), `label_size` (`caption`), `side` (`auto`, `top`, `bottom`, `left`, `right`), `curved` (arrow), `zoom` (magnifier, `2`), `keep` (`false`), `name` | points at the target — or, without a target, at `area` of the frame — with the [Step 34 callouts](#screenshot): a rounded `box` (label as a tag on its edge), a `circle`, an `arrow` from the label, a `label` beside it (no mark), a `spotlight` (the rest of the view darkened) or a `magnifier` (an enlarged inset of a picture: the target must show one, e.g. `image`). Gone when the next beat starts (`until: <beat>`: when that beat starts; `keep: true`: stays to the end of the scene). See "Callouts" below. |

`dim`, `highlight`, `zoom` and `transform` act on targets on screen; a target not shown yet is
first revealed (as by `reveal`). `dim` and `highlight` change only opacity resp. colour, so
both can apply to one target and each is undone separately. Images are dimmed and tinted too
(their pixels). Text written on a filled shape of its target (a pie slice's label, a heatmap
value, a callout's label on its plate) is not faded or painted with the shape: it takes the
colour that reads on the shape's new look (dimmed: kept at 70 % opacity). Undoing a `dim`
(`until`) keeps the scene's own dimming since (`bullets`' `dim_previous`, a `highlight` step).
A highlight `box` (and `fill`) surrounds what the scene marks as the target's
outline (a bar and its value, standing on the axis; a table row, column or cell edge to edge; a
comparison column's card; else the whole target). Boxes, underlines and fills move with their
target when the scene moves it later (a `code_walkthrough` scrolling, a pie slice pulled out)
and fade while it is off screen (a line scrolled out of the window).

**Callouts** (`callout`) work on every scene type, also project types without targets (with an
`area`). What they point at:
- a target (`callout: "bar:4K"`): its outline (a bar with its value; else its parts on screen);
  a list or a pattern gives one callout around all of them;
- a target and an `area`: `[x, y, w, h]` (or a point `[x, y]`) from the top-left corner, as
  fractions of the target's picture when it shows one (`image`, `screenshot`'s `image`,
  `video_clip`'s `clip`; so the numbers read off the image file, and `units: px` are its pixels),
  else of the target's box;
- an `area` alone: fractions of the visible frame (`within: safe`: of its safe area), or with
  `units: px` pixels of the output frame (1920 x 1080...).

Labels are bold text on a plate in `color` with readable text (as in `screenshot`), never below
the readable size. They go away from what they point at, inside the safe area (which leaves out
overlays with `reserve: true`), clear of the text on screen, of other callouts, of the scene's
other small parts (a node, a bar) and of the overlays; `side` forces a direction. A callout is
drawn over everything else of the scene. While the camera is zoomed in (a `zoom` earlier in the
beat, a `screenshot` focus) it is built for the zoomed view, so its label reads at the normal
size; one drawn before a zoom grows with the scene. `name: peak` makes it a target of later
actions (`dim: peak`, `highlight: peak`; its label stays readable). Validation: a callout needs a
target or an `area`, a `magnifier` a target and an area; `kind: label` needs a `label`; `curved`
is for arrows, `zoom` for magnifiers; `keep` and `until` exclude each other; a `name` must be new
in the scene. A magnifier on a target without a still picture is an error when the scene renders.

**Timing.** Actions never make a beat longer. An action is due `at` x the beat's narration
after the beat starts and runs at the first moment from then on when the scene's own animation
is not playing (the scene's reveal of that beat's step comes first, then the action), for its
`run_time`, shortened to end within the beat (narration + `narration.pad`; `vidgen lint`
reports run times shortened below 0.5 s as `rushed_animation`). Actions due together play
together (ones on the same target, and two camera moves, one after the other). Undoing
(`until`) happens at the start of that beat, with its actions (a `callout` without `until`:
at the start of the next beat). A `zoom` is undone so that the
camera is back when the next beat (or its `until` beat) starts: its zoom-out starts `run_time`
before that beat's end, and a zoom-in late in a short beat is shortened together with its
zoom-out. If a scene leaves no time at all, the action is applied without animation and a
warning is logged. Silent scenes have no beats, so no actions. While the camera is zoomed in,
`vidgen lint` does not report text cut off by the frame or in the margins (`off_frame`,
`safe_area`): that is what a zoom does.

**Checks.** `vidgen validate` reports unknown actions (with suggestions), unknown options,
invalid option values, `until` on an action that cannot be undone or on a beat that is not a
later one of the scene, and unknown targets, listing the scene's targets, e.g.
`scenes[3].beats[1].actions[0].target: unknown target 'bar:4k' for scene type 'bar_chart'; did
you mean 'bar:4K'? (targets: title, bar1, bar:Preview 480p, ...; forms: title, bar<N>,
bar:<label>; * and ? match several)`. The JSON Schema checks action names and options; targets
depend on the params, so only `vidgen validate` checks them. Use `vidgen storyboard --scene ID
--per-beat 3` to see actions mid-beat.

## Overlays

Overlays are drawn **on top of the scenes and fixed to the screen**: a lower third introducing a
speaker, a logo in a corner, a progress bar, the current chapter, captions of the narration. They are listed once for the whole video and appear on every scene
they apply to; the scene's camera moves (a [`zoom`](#beat-actions)) and its fades (the fade-out
at a scene's end) do not touch them, and they look the same on both sides of a cut. They are
drawn into each scene's own render, so `vidgen storyboard`, the [layout dump](#layout-dump-buildlayoutscenejson)
and [`vidgen lint`](#lint-vidgen-lint) see them. `vidgen list-scenes` lists the overlay types
and their options (`--json`: `overlays`).

```yaml
overlays:
  - type: watermark                 # the whole video
    image: assets/logo.png
    corner: bottom_right
    opacity: 0.6
  - type: lower_third               # in scene "intro", 1.5 s after it starts, for 5 s
    scene: intro
    at: 1.5
    duration: 5
    name: Ada Lovelace
    title: Mathematician
    icon: user
  - type: watermark
    id: draft
    text: DRAFT
    corner: top_right
    from: results                   # from the start of scene "results"
    to: 95                          # to 95 s into the video
scenes:
  - id: intro
    type: title
    params: {title: "Engines"}
    beats: [{text: "..."}]
  - id: end
    type: end_card
    params: {title: "Thanks"}
    beats: [{text: "..."}]
    overlays: {watermark: false}    # no logo on the end card
```

Keys every overlay entry has (any other key is an option of its type):

| key | default | |
|---|---|---|
| `type` | required | `lower_third`, `watermark`, `progress_bar`, `chapter_indicator`, `captions`, or a [project overlay type](EXTENDING.md#9-overlays-custom-overlay-types) |
| `id` | the type | the name a scene's `overlays:` refers to; when several entries share a type and have no `id`, they are `<type>1`, `<type>2`, ... (ids must be unique) |
| `scenes` | `all` | the scenes it is drawn on: `all` or a list of scene ids |
| `exclude` | `[]` | scenes it is not drawn on |
| `from` | the video's start | where it starts: seconds in the video, or a scene id (that scene's start) |
| `to` | the video's end | where it ends: seconds in the video, or a scene id (that scene's end) |
| `reserve` | the type's: `false`; `captions` at the top or bottom `true` | keep the scenes' layouts clear of it: on every scene it is drawn on, the safe area (docs/EXTENDING.md "Layout regions") shrinks to leave its box free (plus 0.2 units), so built-in scenes lay out around it (the layout dump's `safe_area` too). Off by default for most types: a lower third shows for a few seconds over content laid out for the whole frame, and a watermark sits in the margin. The safe area is cut on every scene the overlay shows on at all, for the whole scene (a layout is built once): a lower third shown 4 s of a scene shrinks it all along (turn it off there with the scene's `overlays: {ID: {reserve: false}}`). An overlay hidden on a whole scene (the `chapter_indicator` on chapter cards, or outside its `from` / `to`) reserves nothing there |

**On a scene** (`overlays:` of the scene): `false` turns every overlay off there; a mapping
turns single ones off (`{draft: false}`) or overrides their options and `reserve` for that scene
(`{watermark: {corner: top_left}}`); an entry with a `type` that is no video-level id adds an
overlay to **this scene only** (no `scenes`, `exclude`, `from`, `to`):

```yaml
  - id: interview
    type: image
    params: {path: assets/guest.jpg, fit: cover}
    beats: [{text: "..."}, {text: "..."}]
    overlays:
      guest: {type: lower_third, name: Grace Hopper, title: Rear admiral, at: interview_b2}
```

**Timing.** An overlay's times are times in the video. Each scene is rendered on its own, so its
position in the video is *planned* before rendering: a narrated beat lasts its MP3's length
(else the word-count estimate) plus `narration.pad`, a scene its beats plus its fade-out, a
silent scene its `duration`. Built-in scenes keep to this exactly. A scene whose animations run
past its narration (lint `animation_overrun`) or an extension scene that times itself
differently shifts the scenes after it; `vidgen render` then warns that overlays timed in the
video (`from` / `to` in seconds or a scene, a lower third running over a cut) are off there.
Render the scenes again after `vidgen tts` so the plan uses the real audio.

**Lint.** Overlays are checked like the scene (text size, contrast, cut off by the frame), and
the rule `overlay_overlap` reports an overlay covering the scene's text or icons. Their own
placement is deliberate, so `safe_area` does not apply to them (a watermark sits in the margin),
and an overlay over the scene's text is `overlay_overlap`'s finding, not `text_overlap`'s or
`covered_text`'s. Like the scene, an overlay is checked only when settled: a lower third sliding
in or out at a beat's end is left alone. A type may exempt its objects from rules: the watermark
is faint on purpose and is not checked for `contrast`. In the layout dump, overlay objects have the key `overlay` (the
id) and paths starting with `overlay:<id>`, so `lint_ignore` can match them (`{rule:
overlay_overlap, object: "overlay:lower_third*"}`).

### `lower_third`

A name and a title on a plate in the lower third of the frame, sliding in at a moment of a scene
and out after `duration` seconds. It belongs to a scene (`scene`, default the first scene the
entry is drawn on) and starts `at` seconds into it or at one of its beats; it goes by the end of
that scene unless `across_cuts`. It is placed in the safe area (in 9:16 raised by 12 % of the
safe height: phone apps put their controls over the bottom), at least at the readable text size,
and slides in from the side it is aligned to (from below / above when centred).

| param | default | |
|---|---|---|
| `name` | required | the main line (a person's or a place's name), bold, font role `heading` |
| `title` | none | the second line (role, affiliation) |
| `icon` | none | an icon left of the text |
| `scene` | first scene drawn on | the scene it belongs to; it must be one the overlay is drawn on |
| `at` | `0.5` | when it starts: seconds after its scene's start, or a beat id of that scene (the beat's start) |
| `duration` | `5.0` | seconds shown, slide in and out included |
| `across_cuts` | `false` | stay on over the following scenes (those the entry is drawn on) until `duration` is over; default: gone by the end of its scene |
| `align` | `bottom_left` | `bottom_left`, `bottom`, `bottom_right`, `top_left`, `top`, `top_right` (in the safe area) |
| `max_width` | `0.6` | widest it may be, share of the safe width (9:16: the whole width); longer text wraps |
| `color` | `primary` | accent bar and icon |
| `background`, `background_opacity` | `surface`, `0.92` | the plate |
| `name_color`, `title_color` | `text`, `dim` | |
| `name_size`, `title_size` | `body`, `caption` | |
| `enter`, `exit` | `0.5`, `0.4` | seconds of the slide in and out |

### `watermark`

A logo (an image from the project), an icon or a short text in a corner of the frame, faint and
fixed, over the whole video or the part `scenes` / `from` / `to` give. It sits `inset` from the
frame's edges (in the margin, outside the safe area, at the default size), so scenes need not
avoid it; it is not checked for contrast.

| param | default | |
|---|---|---|
| `image` | none | image file relative to the project (`assets/logo.png`); exactly one of `image`, `text`, `icon` |
| `text` | none | a short text instead |
| `icon` | none | an icon instead |
| `corner` | `bottom_right` | `top_left`, `top_right`, `bottom_left`, `bottom_right` |
| `opacity` | `0.6` | of the whole watermark |
| `size` | `0.06` | height of an image or icon, share of the frame's shorter side (an image is at most 30 % of the frame wide) |
| `text_size` | `caption` | size of a text watermark |
| `color` | `text` | colour of a text or icon watermark |
| `inset` | `0.025` | distance from the frame's edges, share of the shorter side |
| `fade` | `0` | seconds it fades in and out where a `from` / `to` starts and ends it (`0`: no fade) |

### `progress_bar`

A thin bar along the top or bottom edge of the frame that fills up as the video plays: the
share of the whole video played so far, continuous across cuts. With `chapters` (default),
small gaps split it at the [chapters](#chapters)' starts, as video players mark them. It sits
on the frame's edge, outside the safe area, so scenes need not avoid it. Use `from` / `to`
or `exclude` to leave it off the title or the end card; it still counts the whole video.

| param | default | |
|---|---|---|
| `position` | `top` | `top` or `bottom` edge (in 9:16 phone apps cover the bottom) |
| `thickness` | `0.006` | height, share of the frame's shorter side (at least 2 pixels) |
| `color` | `primary` | the played part |
| `track_color`, `track_opacity` | `dim`, `0.35` | the part still to come (`0`: hidden) |
| `opacity` | `1` | of the played part |
| `chapters` | `true` | gaps at chapter starts |
| `inset` | `0` | distance from the frame's edge, share of the shorter side (`0`: flush) |

### `chapter_indicator`

A small label in a corner naming the current [chapter](#chapters): "2 · Results" (the number in
`number_color`), or "2/5 · Results" with `total`. When the chapter changes it cross-fades to
the next; it fades out before a chapter card and in after it. It is hidden before the first
chapter and on the `chapter` cards themselves (they say it already; `on_chapter_cards: true`
shows it there too). A title longer than `max_width` is shortened with "…". It sits `inset`
from the frame's corner; at the default size it reaches a little into the safe area, so give
it `reserve: true` (scenes keep clear of it) unless the scenes leave that corner free.

| param | default | |
|---|---|---|
| `corner` | `top_left` | `top_left`, `top_right`, `bottom_left`, `bottom_right` |
| `number` | `true` | show the number (as written, else the chapter's position) |
| `total` | `false` | show the position out of the count ("2/5") instead of the number |
| `separator` | `" · "` | between number and title |
| `size` | `caption` | text size (at least the readable size) |
| `color`, `number_color` | `text`, `primary` | title, number |
| `opacity` | `0.85` | of the label |
| `background`, `background_opacity` | none, `0.85` | a plate behind the label (e.g. `surface`) for pictures reaching the corner |
| `max_width` | `0.4` | widest it may be, share of the frame's width (in 9:16 twice that, at most 0.85) |
| `inset` | `0.025` | distance from the frame's edges, share of the shorter side |
| `fade` | `0.4` | seconds of its fades and of the cross-fade at a chapter change (`0`: cut) |
| `on_chapter_cards` | `false` | also show it on `chapter` scenes |

```yaml
overlays:
  - type: progress_bar
    exclude: [intro]                # not over the title
  - type: chapter_indicator
    total: true                     # "2/5 · Results"
    reserve: true
```

### `captions`

The narration **burned into the video** as captions, in the theme's font and colours (the
`<output>.srt` file is written either way; this puts the text into the picture, for videos
watched without sound). Off unless listed. Two styles:

- `subtitles` (default): one or two lines at a time on a plate, like the SRT.
- `karaoke` (alias `words`): a few big bold words at a time, the word being spoken in the
  `highlight` colour with a small scale pop — the look of vertical / social videos.

**Cues.** Each beat's text is cut into cues at natural phrase boundaries, the same way as the SRT
(which now uses the same cutting, with widths in characters): breaks go after a sentence, then
after a comma, semicolon, colon or dash, then before a conjunction ("and", "which"...) or a
preposition, never right after an article or preposition ("the | model"); a new sentence starts
a line; fuller cues and balanced lines are preferred. A cue appears when its first word is spoken
and stays until the next one; a beat's last cue stays through the pause after it (until the next
beat, the scene's last until the scene ends). Silent scenes show none.

**Word times** come from the MP3's character timings when `vidgen tts` stored them
(`voice.timestamps: true`, `audio/<beat_id>.align.json`); otherwise they are estimated: the
beat's speech (its MP3 with the leading and trailing silence cut off, or the word-count estimate
without audio) is shared among the words by syllables (numbers by their spoken words, acronyms
by letters), with pauses after sentence ends and commas. The SRT uses the same word times.

**Placement.** In the safe area at the `bottom` (in 9:16 raised by 12 % of the safe height:
phone apps put their controls over the bottom), `top` or `center`, centred, at least the
readable text size, the text no wider than `max_width`. At the top or bottom it **reserves** its
band (`max_lines` lines high) by default, so the scenes lay out above / below it; centred it
does not (lint's `overlay_overlap` reports scene text under it; or set `reserve: false` and
check with lint). Scenes without narration reserve nothing. The plate's opacity is raised when
needed so the text keeps lint's contrast ratio (`lint.rules.contrast.min_ratio`) over anything
behind it; a highlight that would not read on the plate is replaced by another theme accent (with
a warning).

| param | default | |
|---|---|---|
| `style` | `subtitles` | `subtitles` or `karaoke` (`words`) |
| `position` | `bottom` | `bottom`, `top` or `center` (of the safe area) |
| `size` | `body`; karaoke `title` | text size (at least the readable size) |
| `bold` | `false`; karaoke `true` | |
| `max_lines` | `2` | lines per caption (1-3) |
| `max_words` | none; karaoke `3` | words per caption |
| `max_width` | `0.8`; karaoke `0.9` | widest the text may be, share of the safe width (9:16: `1`) |
| `color` | auto | text colour; default the theme's `text` or background colour, whichever reads better on the plate |
| `highlight` | `highlight` | karaoke: the word being spoken |
| `pop` | `1.12` | karaoke: scale of the word being spoken (`1`: none); limited so it never touches its neighbours |
| `background`, `background_opacity` | `surface`, `0.8` | the plate; `background: null` for none (the text then gets an outline in the background colour) |
| `lift` | `0`; 9:16 `0.12` | bottom captions: raised by this share of the safe height |

```yaml
overlays:
  - type: captions                  # subtitles at the bottom; scenes keep clear of them
variants:
  social:                           # 9:16 with karaoke captions
    format: {width: 1080, height: 1920}
    overlays: [{type: captions, style: karaoke}]
voice:
  timestamps: true                  # exact word times from ElevenLabs (vidgen tts)
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
(`duration` exactly when there are no beats); beat `actions` in both forms (the action name is
one of the registered actions and the options are that action's); even `width`/`height`; and the bodies of
`variants` (partial configs: the same keys, none required). Color and size params accept a
`#hex` color / a positive number or a token name of the project's theme (defaults, extension
defaults, `theme.colors`/`theme.sizes` of the base config and of every variant); such
properties carry `"x-vidgen-theme": "color"` or `"size"`. `theme.preset` is an enum of the
built-in presets and those the project registers, `theme.code_style` of the installed Pygments
styles. Descriptions come from the field docs (the same text as `doc` in
`vidgen list-scenes --json`).

What only `vidgen validate` checks: unique scene and beat ids, action targets and `until`
beats, files referenced by params
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
                               # (and minus overlays with reserve: true)
 frames: [{beat, k, n, frame, time,     # the same keys as the stills index
           still: "../frames/<scene>/<file>.png",
           camera: {center: [x, y], width, height,    # the camera frame in Manim units
                    zoom},                    # frame width / camera width: > 1 while zoomed in
           objects: [...],
           overlays: [{id, type, settled, skip}]}]}   # overlays drawn in this still; settled:
                                     # false while one slides or fades; skip: lint rules not
                                     # applied to its objects
```

Coordinates are output-frame pixels: origin at the top-left corner, y downwards, the frame
spans `[0, width] x [0, height]`; boxes are `[x0, y0, x1, y1]` (1 decimal) and may lie partly or
wholly outside the frame. A moving or zoomed camera (`MovingCamera`) is taken into account.

Each object:

| key | meaning |
|---|---|
| `id` | `m1`, `m2`, ...: the same Python object keeps its id in every frame of the scene |
| `kind` | `text` (`Text`, `MarkupText`, `Paragraph`), `code` (the text of a `Code` listing), `math` (`Tex`, `MathTex`), `number` (`DecimalNumber`, `Integer`), `shape` (one path), `group` (a group of shapes with no text or image inside, e.g. an axis' ticks), `image`, `icon` (an icon from `icon()`: one object, not one per path) |
| `class` | the Manim class |
| `path` | where it sits: parent groups from the top-level mobject down, each `Class[index]` (index among its parent's submobjects; top level: in the scene), or the name the scene gave it |
| `name` | the scene attribute that holds it (`self.title = ...`) or a `Mobject.name` set by the scene, else `null` |
| `bbox` | the box of its visible parts, stroke included |
| `opacity` | the highest opacity of its visible parts (fill, or stroke when it has one); a fade-in in progress shows here |
| `z`, `order` | Manim `z_index`, and the drawing position (higher is drawn later, i.e. on top) of its top-most part |
| `parts` | number of visible parts (glyphs, paths) |
| text kinds only: `text` | the characters (markup tags removed; the LaTeX source for `math`) |
| `font_px` | the 75th percentile of its visible glyphs' heights in output pixels: about the cap height (≈ 0.7 em) for mixed-case text, the x-height for lowercase text without ascenders; a rotated line of text is measured across its direction |
| `rotation` | the angle of a line of text in degrees, counter-clockwise (`90` for an axis title turned upwards); `0` when level, for several lines and for math |
| `color`, `colors` | the most common glyph colour, and all of them (most common first) |
| `backdrop` | the most common colour of the frame inside its box, ignoring its own colours: what the text is read against (`null` when off-frame) |
| other kinds: `fill`, `stroke` | `{color, opacity}` / `{color, opacity, width_px}` of the largest visible part, or `null` |
| `icon` only: `icon` | the icon's name (`cpu`); its `bbox` is what it draws, not its padded design box |
| overlays only: `overlay` | the id of the [overlay](#overlays) it belongs to; overlay objects come after the scene's, their `path` starts with `overlay:<id>` and they are measured as drawn: fixed to the screen whatever the camera does |

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
$ vidgen lint my_video
lint: 11 scenes, 28 beat-end stills (preview 854x480)
picture:
  warning safe_area         picture_b2 @ 7.2s: text 'Images can slowly zoom and pan' is outside the safe area at the bottom (12 px into the bottom margin)
          still: my_video/build/preview/frames/picture/picture_b2-1.png
0 errors, 1 warning, 0 info
```

Each finding names the scene, the beat at whose end it was seen (`+N more beats` when the same
problem stays on screen), the rule, a message with the measured value and the limit, and the
**still** to open to see it. Timing findings name the beat concerned and the scene time where
the problem starts; their still is the end of that beat. The same problem with several objects of one group (an axis' tick
labels, several texts in the same colour) or with the same text in several places (a label of a
repeated component) is reported once (`also N more like it`).

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

**Theme contrast.** Like `vidgen validate`, `vidgen lint` first checks the theme itself (text and
`dim` on the background and `surface`, accents and palette on the background; see
[Theme presets](#theme-presets)) and prints pairs below WCAG AA as `warning: theme contrast:
...` (JSON: `warnings`). They are not findings and never fail the command; they are skipped
with `--rule` other than `contrast` and when `lint.rules.contrast.severity` is `off`.

**Rules.** Sizes are fractions of the frame's **shorter side** (the height of a landscape
video, the width of a vertical one), so the same thresholds hold for the 480p preview and the
1080p video, and for 16:9 and 9:16 (a phone shows either orientation with its shorter side
across the screen's width). Objects fainter than `lint.min_opacity` are ignored by every rule.

| rule | default severity | finds |
|---|---|---|
| `off_frame` | error for text, warning for other objects | an object cut off by the frame edge by more than `tolerance`. Not reported: objects wholly outside (not visible), and non-text objects running from edge to edge on the side they cross (a full-frame image with `fit: cover` or Ken Burns, a background, a band or divider): those bleeds are intentional; nothing while the camera is zoomed in (a `zoom` action) |
| `safe_area` | warning | text inside the frame but in its margins (the scene's `margin_x`/`margin_y`, `safe_area` in the layout dump, smaller where an overlay has `reserve: true`) by more than `tolerance`; not checked while the camera is zoomed in, nor for [overlays](#overlays) (their place is deliberate) |
| `text_overlap` | error | two texts whose boxes overlap by at least `min_overlap` of the smaller box (the same text drawn twice in the same place is not reported) |
| `covered_text` | warning | a shape or image drawn **after** (on top of) a text whose colour shows in at least `min_covered` of the middle of the text's box, measured on the still's pixels. Not reported: shapes drawn before the text (plates, highlight bands, a code window), the text's own parent group, shapes fainter than 0.3, and shapes in the text's own colour (a strike-through) |
| `min_font` | warning; error below `error_size` | text whose cap height is below `min_size` of the shorter side. The cap height is the layout's `font_px` corrected for the text's letters (`font_px` of all-lowercase text is about its x-height); a lone symbol (`+`, `·`) is not checked |
| `contrast` | warning | text whose WCAG contrast ratio with its `backdrop` is below `min_ratio` (4.5, WCAG AA), `large_ratio` (3) for text with a cap height of at least `large_size`, or `dimmed_ratio` (2) for text faded on purpose (opacity below 1, e.g. previous bullets); the text colour is blended with the backdrop at the text's opacity, every colour of a multi-coloured text is checked. A code listing's line numbers are not checked |
| `max_words` | warning | more than `max_words` words (tokens with a letter) of visible `text` objects in one still; code and math do not count |
| `overlay_overlap` | warning | an [overlay](#overlays) whose box (all its objects) covers at least `min_overlap` of the box of a scene text or icon. `text_overlap` and `covered_text` leave an overlay over scene text to this rule; overlays of a type with a `lint_skip` (the watermark: `contrast`) are not checked by those rules |
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
    overlay_overlap: {min_overlap: 0.05}    # fraction of the scene object's box
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
matched against the object's `name`, `path`, `text` and icon name (for a pair, either object); `beat`
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
the files under `assets/`, and vidgen's own rendering code; with [overlays](#overlays), also
every scene's beats, MP3s and type, which place the scene in the video), and a scene whose
fingerprint changed is rendered again. So `vidgen storyboard` right after `vidgen render --preview
--frames` renders nothing, and after an edit it renders only the edited scenes. Files a scene
reads from outside `assets/` are not tracked: use `--force`. The storyboard does not join the
video; `vidgen render` does. It dispatches `post_scene` for the scenes it renders, not
`pre_render`/`post_render`.

## JSON output (`--json`)

`vidgen validate`, `vidgen list-scenes`, `vidgen list-themes`, `vidgen list-icons`, `vidgen render`, `vidgen schema`, `vidgen storyboard` and `vidgen lint` accept `--json`: stdout then holds
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
| `command` | str \| null | `validate`, `list-scenes`, `list-themes`, `list-icons`, `render`, `schema`, `storyboard`, `lint` (`null` if the command line could not be parsed) |
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

`warnings` include the theme contrast warnings (`theme contrast: ...`, prefixed `[variant] `
for a variant's own; they do not make `ok` false). When there are problems, `error` is
`{"kind": "error", "message": "video.yaml: invalid project ...", "problems": [same list],
"details": {}}`. Problem `message`s are the text after
the location in the human output (`scenes[1].type: unknown scene type 'titel'; did you mean
'title'? ...` → `location` `scenes[1].type`).

### `vidgen list-scenes --json`

| key | type | |
|---|---|---|
| `project` | str \| null | the project whose extensions were loaded (`null`: built-ins only) |
| `scene_types` | list | sorted by name, as below |
| `actions` | list | the [beat actions](#beat-actions) (built-in and the project's), sorted by name, as below |
| `overlays` | list | the [overlay types](#overlays) (built-in and the project's), sorted by name, as below |

Each scene type: `name`; `origin` (`builtin`, or the extension file relative to the project);
`builtin` (bool); `overrides_builtin` (bool, an extension registered with `override=True`);
`doc` (the class docstring, else its module's, or `null`); `beats` (`null` = any number, else
`{min, max, text}` with `max` `null` for no upper limit, e.g. `{"min": 2, "max": 2, "text":
"exactly 2 beats"}`); `params` (`null` = free-form params, else a list of fields); `targets`
(the forms of its [action targets](#beat-actions), e.g. `["heading", "item<N>",
"item:<text>"]`; `[]` = none).
Each field: `name` (as written in `video.yaml`: an alias such as `from` when the field has one); `type` (readable type as in the human listing: `str`, `list[str]`,
`color`, `size`, `'all' | 'per_beat'`, ...); `required` (bool); `default` (JSON value, `null`
when required); `doc` (the docstring under the field or its `Field(description=...)`, or
`null`); `nested` (fields of `SceneParams` models used in the type, as `{model, fields}`);
`aliases` (other names the field accepts, e.g. `["title"]` for `heading`; `[]` = none).
Each action: `name`, `origin`, `builtin`, `overrides_builtin`, `doc` (as for scene types);
`run_time` (default seconds); `reversible` (bool: `until` allowed); `temporary` (bool: undone
by the end of its beat, like `zoom`); `until_next_beat` (bool: without `until`, undone when the
next beat starts, like `callout`); `needs_target` (bool); `target_options` (options whose
values are target names, e.g. `["into"]`); `options` (fields like `params`; `[]` = none).
Each overlay type: `name`, `origin`, `builtin`, `overrides_builtin`, `doc` (as above); `layer`
(drawing order among overlays); `lint_skip` (lint rules not applied to its objects, e.g.
`["contrast"]`); `options` (fields like `params`).

### `vidgen list-themes --json`

| key | type | |
|---|---|---|
| `project` | str \| null | the project whose presets and registered defaults were used (`null`: built-ins only) |
| `orientation` | str | `landscape`, `portrait` or `square`: the project's `format` (decides `auto`) |
| `current` | object | the project's choice: `{preset, scale, scale_resolved}` (`preset` `null` without one) |
| `presets` | list | every preset, built-in first, as below |
| `type_scales` | object | `{scales: {name: {title, subtitle, heading, body, caption, small}}, auto: {orientation: scale}}` |
| `swatches` | str \| null | the PNG written with `--swatches` |

Each preset: `name`, `origin` (`builtin` or the extension file), `base`, `description`,
`selected` (bool: the project's preset), and what selecting it gives in this project:
`background`, `font`, `font_serif`, `font_mono`, `fonts` (the roles the preset and config
set: role → token or family), `font_roles` (the family of every built-in role: `body`,
`heading`, `quote`, `quote_mark`, `code`), `code_style`, `scale` (as set, e.g. `auto`),
`scale_resolved`, `colors`, `palette`, `sizes`; `contrast` `{ok, min_text_ratio,
min_graphic_ratio, failures}` (`failures`: messages like the validate warnings) and
`palette_distinctness` `{normal, protanopia, deuteranopia, tritanopia}` (smallest CIEDE2000
difference between two palette colours).

### `vidgen list-icons --json`

| key | type | |
|---|---|---|
| `project` | str \| null | the project folder whose `assets/icons` were included (`null`: built-ins only) |
| `search`, `category` | str \| null | the filters given |
| `sources` | object | the built-in set: `{lucide: {package, version, license, license_file, homepage}}` |
| `categories` | list | `{name, description, count}` for every category (built-in ones first, then project categories); `count` over all icons, not only the listed ones |
| `count` | int | number of listed icons |
| `icons` | list | the listed icons, best matches first: `{name, category, tags, aliases, source, origin, overrides, path}` (`origin` `builtin` or `project`; `overrides`: a project icon replacing a built-in; `path` the SVG) |
| `sheets` | list | the PNG files written with `--sheet` |

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
`{id, kind, class, name, path, text, icon, bbox}` as in the [layout dump](#layout-dump-buildlayoutscenejson)
(`text` `null` for shapes, `icon` the icon name for kind `icon`, else `null`); `similar` (further objects with the same problem, reported with
this one, e.g. the other tick labels); `bbox` (the region to look at in the still, px:
the object, the overlap of a pair, or all counted texts); `message`; `value` and `limit` (the
measured number and the threshold it broke: a fraction of the shorter side for sizes, a ratio
for contrast, px for `off_frame`/`safe_area`, a word count, words per second for
`narration_speed`, seconds for the other timing rules); `beats` (every beat end where the
same problem was seen, the first is `beat`); `still` (the PNG at `beat`'s end; `null` if the
scene has none). Timing findings have `bbox` `null` and `time`/`scene_time` where the problem
starts (the beat's start, the start of the still stretch, the narration's end, the first
rushed animation).
