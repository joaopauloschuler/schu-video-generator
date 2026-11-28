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

**Another font.** Put the font's `.ttf`, `.otf` or `.woff` file (and its licence) in the project's
`fonts/` folder and name its family: `theme: {font: "Space Grotesk"}` (or one role: `fonts:
{heading: "Space Grotesk"}`). Every scene, the captions and `web` pages then use it; the steps
are under "Using another font" in `vidgen guide web`.

**Colour roles.** Use the theme's tokens, not hex values, in params: `text` / `dim` for text,
`primary` for the main element, `highlight` for "look here" (one thing per frame), `accent`
for warnings and bad news, `tertiary` for good news, `surface` for panels, `palette` for
series. Meaning never rides on colour alone: `comparison` adds check / cross markers, charts
label their series, `stat` chips carry an arrow. Every preset passes WCAG AA and has a
colour-blind-safe palette (except `dark_tech`'s blue and purple for deuteranopes: pick another
preset if that matters).

**One colour per concept.** Give the few concepts an explainer keeps coming back to a colour of
their own, once, at the top of `video.yaml`; schu-video-generator then draws those words in that colour
wherever they are written (titles, bullets, cards, chart and diagram labels, captions, a
callout naming one, a `line_chart` series named after one) and their TeX parts in equations:

```yaml
terms:
  loss: tertiary
  gradient: "#E07A5F"
  learning rate: {color: secondary, tex: '\eta'}   # also η in equation scenes
```

Whole words, any case, plurals too. At most about 5 colours, each readable on the background
(lint `concept_colors` checks both). Do not colour the same word otherwise in a scene (a
title's `highlight_color`, a series' `color`, an `equation_derivation`'s `colors`, a plotted
function's or area's `color`, a callout's `color`): lint warns. `terms: false` on a scene turns it off there (a recap in plain colours).
Prefer colours the scenes do not use for something else: `accent` is also the default of
tangent lines, number-line jumps, angle marks and the terminal's prompt, and `highlight` is the
spoken word in karaoke captions and the code highlight; `examples/gradient-descent` uses
`primary`, `secondary` and `tertiary`.

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

