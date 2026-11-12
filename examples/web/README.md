# Where rain comes from — scenes written as web pages

Three short `web` scenes (about 50 s with Kokoro narration), each written a different way, to copy
from. The how-to is `vidgen guide web`; every detail is in [docs/CONFIG.md](../../docs/CONFIG.md#web).

| scene | file | what it shows |
|---|---|---|
| `cycle` | [extensions/cycle.html](extensions/cycle.html) + [cycle.css](extensions/cycle.css) | HTML and CSS only, no JavaScript: three cards that come in on their narration beats (`body[data-beat-index]` and a CSS transition), pictures in inline SVG moved by CSS `@keyframes`, every colour, font and text size a theme variable (`var(--vidgen-primary)`, `var(--vidgen-size-body)`), `region: body` under a vidgen title; a row in 16:9, a column in 9:16 (`[data-orientation="portrait"]`) |
| `rain` | [extensions/rain.js](extensions/rain.js) | a `script:` drawing a rain gauge on the canvas from `t` alone; the rain starts on the spoken word "shower" (`ctx.beats[1].words`), the third line comes in on the third beat, the amounts come from `data:` (`ctx.data`), and the text drawn on the canvas is declared to lint with `layout(t, ctx)` (boxes measured with `measureText`); gauge beside the reading in 16:9, above it in 9:16 |
| `globe` | [extensions/globe.js](extensions/globe.js) | three.js written by hand (`import * as THREE from "three"`, served by vidgen): a low-poly planet in theme colours, lit by a sun, turning, with clouds; the camera rises over the pole on the second beat and comes back on the third; transparent (`alpha: true`), full frame with a title on a plate (`region: bleed`) |

```
vidgen validate examples/web
vidgen lint examples/web                       # 0 findings at 16:9
vidgen lint examples/web --variant vertical    # and at 9:16
vidgen storyboard examples/web --variant vertical
vidgen tts examples/web                        # Kokoro: local and free
vidgen render examples/web --preview [--variant vertical]
```

Needs Chromium once: `python -m playwright install chromium` (Windows: `py -m playwright install
chromium`). No audio is committed: before `vidgen tts` beats are timed from their word count.

**Render cost** (1 CPU, drawing the pages' frames only, Chromium start included): at 1920x1080 and
30 fps, `cycle` 13.6 s, `rain` 9.7 s and `globe` 16.5 s per second of video (453, 325 and
550 ms per frame); a whole `--preview` render at 480x270, 12 fps, about 2 s per second. A `web` scene is a screenshot per frame, so keep it short and work at `--preview`.
