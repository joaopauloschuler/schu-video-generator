# Extending vidgen from your project

Every project can add its own **scene types**, **helpers**, **theme tokens** and **hooks** in its
`extensions/` folder. Nothing in vidgen has to change, and a finished extension can later be
promoted into the core library unchanged.

```
my_video/
  video.yaml
  extensions/
    common.py        # helpers shared by your scenes
    charts.py        # @scene("loss_panel") ...
    tools/           # sub-packages work too (needs __init__.py)
    _scratch.py      # names starting with "_" are NOT imported
```

vidgen imports every `*.py` file and every package in `extensions/` (sorted by name) whenever it
loads the project (`validate`, `list-scenes`, `tts`, `render`). Check your work with:

```
vidgen validate          # unknown types, bad params, import errors (with file + traceback)
vidgen list-scenes       # every scene type, where it comes from, its params
```

Import everything from **`vidgen.api`** only: it re-exports all of `from manim import *` plus the
vidgen names. Anything else in vidgen is internal.

Two complete examples: [examples/custom_scene](../examples/custom_scene) (a small video with one
custom scene type, a helper module, a vertical variant and a hook) and
[examples/kphi3](../examples/kphi3) (a 4-minute paper video made only of custom scenes).

**How your code runs.** Extension modules are imported as a private package (`vidgen_ext_<project
folder>`), not from `sys.path`, so any file name works — even `json.py` or `manim.py` does not
shadow the real library. Every command imports all of them again, and `vidgen render` renders
**each scene in its own Python process**, which imports every extension module once more:
keep module-level code light (no downloads or heavy computation at import), and do not count on
module-level state being shared between scenes or with hooks. `print()` inside a scene is only
shown when the render fails (or with `--jobs 1` in a terminal); log warnings with
`logging.getLogger(__name__).warning(...)` — they are always shown as `warning: ...`. Raise
`VidgenError("...")` for problems the user must fix: it is printed without a traceback.

## 1. A new scene type

```python
# extensions/big_number.py
from vidgen.api import *


@scene("big_number")                      # the name used as `type:` in video.yaml
class BigNumber(NarratedScene):
    beat_count = 2                        # narrates beats 0 and 1 (see "Fixed beats" below)

    class Params(SceneParams):            # optional; validated by `vidgen validate`
        value: str
        label: str = ""

    def construct(self):
        number = self.text(self.params.value, size=96, color="highlight")
        label = self.text(self.params.label, size="caption", color="dim").next_to(number, DOWN)
        with self.narrate(0) as d:        # beat 0; d = length of its audio in seconds
            self.play(FadeIn(number), run_time=0.4 * d)
            self.play(FadeIn(label))
        with self.narrate(1):             # or by id: self.narrate("intro_b2")
            self.play(Indicate(number))
```

```yaml
# video.yaml
scenes:
  - id: intro
    type: big_number
    params: {value: "77%", label: "fewer parameters"}
    beats:
      - text: "Seventy-seven percent of the parameters can go."
      - text: "And the model still learns."
```

Inside `construct()` you have `self.spec` (the scene's config: `id`, `type`, `params`, `beats`,
`duration`), `self.params` (a `Params` instance, or a plain dict without a `Params` class),
`self.beats` (each with `id` and `text`), `self.theme` (`color(name)`, `size(name)`,
`palette_color(i)`, `font`, `background`) and `self.project` (`root` folder, `config`,
`variant` name or `None`, `asset("assets/logo.png")` → absolute path, error if missing).

Timing rules:
- `with self.narrate(beat) as d:` starts the beat's audio, and when the block ends waits until
  `d + narration.pad` seconds have passed. If your animations take longer, nothing is cut.
- `for beat, d in self.narrate_all():` narrates every beat in order.
- Without audio (before `vidgen tts`), `d` is estimated from the word count.
- A **silent scene** (no beats, `duration: 3` in the config) is held to its duration
  automatically; `self.hold()` holds earlier.
- If you override `tear_down`, call `super().tear_down()`.

Frame size and vertical videos: vidgen makes the **shorter side of the frame 8 Manim units**
(square pixels). A 16:9 render is 14.22 x 8 units (Manim's default); a 9:16 variant such as
`format: {width: 1080, height: 1920}` is 8 x 14.22. Lay out with `self.frame_width`,
`self.frame_height` (same as Manim's `config.frame_width` / `config.frame_height`) and
`self.is_portrait` instead of hard-coded coordinates, e.g.

```python
row = VGroup(*items).arrange(DOWN if self.is_portrait else RIGHT, buff=0.5)
row.scale_to_fit_width(min(row.width, self.frame_width * 0.9))
```

Theme sizes are in Manim font points, so text has the same size relative to the short side in
both orientations; wide content needs to wrap, stack or scale in portrait.

Params errors are reported with their config path, e.g.
`scenes[2].params.values.x: Input should be a valid number`. Unknown keys are errors.
`@scene` always takes the name in parentheses: `@scene("big_number")`.

## 2. Building blocks: params, layout, timing, validation

The built-in scene types (`src/vidgen/scenes/*.py`) are written with nothing but
`from vidgen.api import *`, so they double as examples for everything below.

**Params.** `vidgen.api` re-exports pydantic's `Field`, `field_validator` and `model_validator`.
Use `ThemeColor` / `ThemeSize` for colors and sizes: they accept a theme token or a literal
(`#hex` / points) and `vidgen validate` reports unknown tokens (it checks them against the
project's theme, including your `register_theme_defaults` and `theme.colors`).

A docstring under a field documents it: `vidgen list-scenes --json` shows it as the field's
`doc` (so does `Field(description=...)`), and `vidgen schema` as its `description`. The
exported JSON Schema comes from your `Params` model (types, defaults, `Field` constraints,
`Literal`s, nested models; `ThemeColor`/`ThemeSize` accept the project's token names) and
from `beat_count`; validators written in Python are only run by `vidgen validate`.

```python
class Params(SceneParams):
    items: list[str] = Field(min_length=1)
    """The list items; item i appears at beat i."""
    color: ThemeColor = "text"
    size: ThemeSize = "body"

    @model_validator(mode="after")
    def _check(self):
        if len(self.items) > 12:
            raise ValueError("at most 12 items")
        return self
```

Params can nest: use another `SceneParams` class as a field type (also in lists). Theme tokens
are checked inside nested models too, and `vidgen list-scenes` prints the nested fields.

```python
class Ring(SceneParams):
    teeth: int = Field(ge=8, le=60)
    color: ThemeColor = "primary"

class Params(SceneParams):        # inside the scene class
    front: Ring
    rear: Ring
    extra: list[Ring] = []
```

```yaml
params:
  front: {teeth: 44, color: secondary}
  rear: {teeth: 16}
```

**Project-aware checks.** Override the classmethod `validate_project(params, project)` for
checks a `Params` model cannot do (a file exists, a data file parses...). It runs in `vidgen
validate` after the params validated; return one message per problem, starting with the param
name. Messages are reported as `scenes[i].params.<message>` (in `vidgen validate --json`, the
part before the first `: ` becomes the problem's `location`, e.g. `scenes[2].params.data`). Log warnings with `logging` (they
are printed as `warning: ...`). Repeat the check in `construct()` if rendering cannot work
without it.

```python
@classmethod
def validate_project(cls, params, project):
    problems = super().validate_project(params, project)
    if not (project.root / params.data).is_file():
        problems.append(f"data: file not found: {params.data}")
    return problems
```

**Layout regions.** Lay out in regions rather than raw coordinates, so one scene works at
16:9, 1:1 and 9:16 (the frame's shorter side is always 8 units; 16:9 is 14.22 x 8, 9:16 is
8 x 14.22). A `Region` is a rectangle in Manim units (`x0, y0, x1, y1`; `width`, `height`,
`center`, `point("top_left")`, `contains(m)`).
- `self.safe_area` — the frame minus the scene's `margin_x` / `margin_y` (0.6 / 0.5 units). It
  is the rectangle the layout dump records and `vidgen lint`'s `safe_area` rule checks.
  `self.safe_width` / `self.safe_height` are its size. Without a scene: `safe_area()`;
  `frame_region()` is the whole frame.
- `self.region(name)` (or `region(name, area=None)`) — named parts of the safe area:

  | name | landscape / square | portrait (9:16) |
  |---|---|---|
  | `full` | the safe area | same |
  | `header` | top band, 16 % of the height (15 % square) | 12 % |
  | `caption` | bottom band, 12 % (11 % square) | 9 % |
  | `body` | below `header` | same |
  | `hero` | between `header` and `caption` | same |
  | `top`, `bottom` | upper / lower half | same |
  | `left`, `right` | left / right half | **upper / lower half** |
  | `center` | centered 72 % x 72 % (86 % x 72 % square) | full width x 60 % |

  Neighbouring regions are `gap` (0.3 units) apart. `left`/`right` turn into rows in a vertical
  frame so a two-column layout stays readable; for literal halves use `area.columns(2)`.
- `Region.rows(n | weights, gap)`, `.columns(...)`, `.split(...)` (columns in landscape/square,
  rows in portrait), `.grid(rows, cols, gap, gap_y)` (cells row-major; also
  `grid(rows, cols, area="full")`), `.inset(x, y)`, `.below(mobject_or_y, gap)` / `.above(...)`
  (the rest of a region under a title you placed), `.to_rectangle()` (outline, for debugging).
  `orientation()` is `"landscape"`, `"portrait"` or `"square"`.
- `place(mobject, region, fit="contain", align="center", max_scale=None, buff=0)` — scales and
  moves a mobject into a region (a name or a `Region`): `contain` fits both ways (up or down),
  `width` / `height` match one side, `none` only moves. `max_scale=1` never enlarges. `align`
  (`"top"`, `"bottom_left"`, ... or a direction such as `UL`) puts that edge or corner of the
  mobject on the same edge or corner of the region.
- `readable_size(font=None)` — the smallest font size (points) `vidgen lint`'s `min_font` rule
  accepts in the current frame (the project's `lint.rules.min_font.min_size`, default 2.5 % of
  the shorter side as cap height, plus 5 %): about 21 points for Inter at any resolution.
  `readable_text(text, region, size="body", min_size=None, **fit_text_args)` wraps text into a
  region like `fit_text` but never below that size (it wraps onto more lines instead; if it
  still does not fit, it is scaled down and a warning is logged). It does not move the text:
  `place(t, region, fit="none", align=...)` does.

**Text and numbers.**
- `fit_text(text, max_width, max_height=None, size="body", color="text", weight=NORMAL,
  align="center", highlights={"77%": "highlight"}, squeeze=1.0, ...)` — wraps by measured width,
  lowers the font size (down to `min_size`) until the block fits `max_height`, then scales down
  if still needed. Returns a Manim `Paragraph` (one submobject per line).
- `shrink_to_fit(mobject, max_width, max_height)` — scale down only, never up.
- `wrap_lines(text, max_chars)`, `normalize_text(text)` — pure helpers.
- `nice_ticks(lo, hi, max_ticks)`, `auto_format(values)`, `format_value(v, fmt, unit)`,
  `check_format(fmt)` — chart axes and labels without LaTeX.

**Timing.** Beat-driven reveals without arithmetic:
- `self.reveal(steps)` narrates the whole scene: step *i* at beat *i*; more steps than beats are
  spread evenly (`distribute(n_steps, n_beats)` gives the plan), extra beats hold. A step is an
  animation, a list of animations played together, or a callable returning them (built when it
  plays — use this when a step depends on what happened before).
- `self.play_steps(d, steps, fraction=0.7, cap=1.2)` spreads steps over `d` seconds; each
  animation lasts `min(cap, fraction * slot)`, so a beat is never stretched by its animations.
- `self.timeline()` is `narrate_all()` that also works for silent scenes (yields `(index, d)`;
  a silent scene yields one step of its `duration`).
- `self.finish()` fades everything out over `self.outro` seconds (class attribute, default 0;
  the built-ins use 0.5). Set `outro` on your class and call `finish()` at the end of
  `construct()`; silent scenes then fade out within their `duration`.
- Stills (`vidgen render --frames`) are taken on the last frame of each beat, i.e. when the
  `with self.narrate(...)` block has ended (or, for a silent scene, at `duration - outro`), so
  a scene reads best in stills when each beat ends showing what it explained. Capturing only
  observes the frames written; it never changes timing. `self.capture` is the active
  capture object, or `None` (internal: vidgen's own tools attach to it). Check your scene
  with `vidgen storyboard --scene ID` (add `--variant vertical` for 9:16): it shows those
  stills with their narration. Its reuse of stills tracks the `.py` files of your extension
  folders and `assets/`; if your scene reads other files, use `--force` after changing them.
- The same frames are described in `build/.../layout/<scene>.json` (docs/CONFIG.md "Layout
  dump"), the input of `vidgen lint --scene ID` (docs/CONFIG.md "Lint"): run it on new scene
  types at 16:9 and `--variant vertical`. It checks the end of each beat, so a beat should end
  in a settled state. Text measured against the safe area uses the scene's `margin_x` /
  `margin_y`; a background or band meant to bleed should run from edge to edge; a shape meant
  to sit on top of text (a strike-through) should use the text's colour. Mobjects you keep as
  attributes (`self.title = ...`) or give a `name` appear under that name there, which also
  makes `lint_ignore` entries (`object: title`) stable. A `Text` updated with `m.become(new)` keeps its
  old string as its `text`; set `m.original_text = new.original_text` if it matters.
- `vidgen lint` also checks timing (docs/CONFIG.md "Activity file"): every `self.play` /
  `self.wait` is recorded with the beat being narrated (`self.play_log`), and how long each
  `narrate` block's own code took (`self.beat_busy`). Animations inside a beat that take longer
  than its narration plus `narration.pad` are reported as `animation_overrun` (the next beat
  starts late): derive run times from the `d` that `narrate` yields, or use `play_steps` /
  `reveal`, which never take longer than `d` (when they have to shorten animations below
  0.5 s, `rushed_animation` says the beat is too short for its steps). Nothing changing on
  screen for more than 6 s is `dead_air`: reveal, highlight or move something during long
  beats.

```python
@scene("checklist")
class Checklist(NarratedScene):
    outro = 0.5

    class Params(SceneParams):
        items: list[str] = Field(min_length=1)

    def construct(self):
        body = self.region("body")
        rows = VGroup(*[readable_text(f"✓ {t}", body, align="left") for t in self.params.items])
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.3)
        place(rows, body, fit="contain", max_scale=1.0, align="top_left")
        self.reveal([FadeIn(r, shift=RIGHT * 0.2) for r in rows])
        self.finish()
```

**Fixed beats.** A scene that narrates beats by index (`self.narrate(0)`, `self.narrate(1)`)
should say how many it needs, so `vidgen validate` catches a missing or extra beat before
rendering (`list-scenes` shows it too):

```python
@scene("kphi_title")
class KphiTitle(NarratedScene):
    beat_count = 2            # exactly 2; or (1, None): at least one; (2, 4): two to four
```

**LaTeX.** `latex_available()` and `require_latex("scene 'x'")` (raises a `VidgenError` with
install hints, e.g. MiKTeX on Windows) let a scene that uses `Tex`/`MathTex` fail clearly on
machines without LaTeX.

## 3. Helpers shared across modules

Extension modules form one private package, so use **relative imports**:

```python
# extensions/common.py
from vidgen.api import *

def network(n, color="primary"):
    a, b = column(n, -3, 0.6), column(n, 3, 0.6)
    return VGroup(a, b, edges(a, b, dense_pairs(n, n), color=color))
```

```python
# extensions/charts.py
from vidgen.api import *
from .common import network
```

Your project folder is not put on `sys.path`; `import common` does not work, `from .common
import ...` does.

Ready-made helpers in `vidgen.api`: `T(s, size, color, weight)` / `MT(...)` (text / Pango markup
in the theme font — the function forms of `self.text` / `self.markup`), `column`, `edges`,
`dense_pairs`, `grouped_pairs`, `counter` (text redrawn from a `ValueTracker`), `resolve_color`,
and the layout/timing helpers of section 2 (`fit_text`, `distribute`, `nice_ticks`, ...).
Sizes and colors take theme token names (`"body"`, `"accent"`) or literals (`32`, `"#FF0000"`).

A complete real-world example is [examples/kphi3](../examples/kphi3): eight bespoke animated
scenes of a paper video, each an extension scene type, with shared helpers in
`extensions/common.py` and the on-screen text in `params`.

## 4. Theme tokens

```python
# extensions/tokens.py
from vidgen.api import *

register_theme_defaults({"k2": "#F2A541", "k3": "#83C167"}, sizes={"huge": 96})
C_K2 = current_theme().color("k2")        # module-level theme access is fine
```

Then `self.text("x", color="k2")`, `T("x", "huge", "k3")`. Values in `video.yaml`
(`theme.colors.k2: ...`) always win over registered defaults, which win over vidgen's built-ins.

**Theme presets** (docs/CONFIG.md "Theme presets"). A project can add its own preset, e.g. a
brand look, and select it in `video.yaml` with `theme: {preset: acme}`:

```python
# extensions/_brand.py is skipped (leading _), so use a name that sorts first: extensions/a_brand.py
from vidgen.api import *

register_theme_preset(
    "acme",
    base="light_academic",                  # optional: values not given here come from it
    colors={"primary": "#0B5FFF", "accent": "#E4002B", "brand": "#0B5FFF"},
    palette=["#0B5FFF", "#E4002B", "#9D2F8F", "#15803D"],
    scale="auto",                           # optional type scale: compact, standard, large, auto
    description="ACME corporate look",
)
```

Arguments (all optional except the name): `base`, `background`, `font`, `colors`, `palette`,
`sizes`, `code_style` (a Pygments style), `scale` (type scale, docs/CONFIG.md "Type scales";
applied below the preset's own `sizes`), `fonts` (font family per role, e.g. `{"heading":
"Source Serif 4", "mono": "JetBrains Mono"}`), `description`. Font roles are a hook for scenes:
`current_theme().font_for("heading")` returns the preset's family for the role, else the
theme `font` (a `font` written in `video.yaml` wins over every role); built-in scenes do not
read roles yet (planned with bundled fonts). Names must not clash with a built-in
or another project preset. Full precedence, highest first: `video.yaml` `theme:` values > the
selected preset (then its `base`) > `register_theme_defaults` > built-in defaults. So a preset
chosen in the config overrides tokens an extension registered as defaults, but never what the
config writes itself. Presets are resolved whenever a theme value is read, so register a preset
before any module reads the theme at import time (extensions are imported in sorted file
order) — otherwise that read fails with "unknown theme preset". Check a preset's contrast with
`vidgen list-themes` (contrast and colour-blind distinctness of every preset, `--swatches` for a
picture), `vidgen lint` on a render, or in a test: `vidgen.lint.color.theme_contrast(theme)`
lists every text/dim/accent/palette pair with its WCAG ratio (`[c for c in ... if not c.ok]`)
and `vidgen.lint.color.palette_distinctness(palette)` the smallest CIEDE2000 difference per
vision (normal, protanopia, deuteranopia, tritanopia; aim for 7.5 or more).

## 5. Hooks

```python
from vidgen.api import *

@hook("post_render")          # pre_tts, post_tts, pre_render, post_scene, post_render
def announce(ctx):            # ctx.project, ctx.event, ctx.data (dict; may be modified)
    print("rendered", ctx.data["output"])      # the MP4 just written (preview/variant aware)
```

Hooks run in registration order (each project's hooks only for that project). If a hook raises,
the command stops with an error naming the hook and its file. Paths in `ctx.data` are
`pathlib.Path` objects; `ctx.project.variant` tells which variant is being rendered.

Event data (see DESIGN.md §6.2):

| event         | `ctx.data` keys |
|---------------|-----------------|
| `pre_tts`     | `beats` (list of beat ids about to be generated; remove ids to skip them), `audio_dir`, `force`, `dry_run` |
| `post_tts`    | `generated` (beat ids written, in order), `audio_dir` |
| `pre_render`  | `scenes` (scene ids about to be rendered, config order; remove ids to reuse their existing render), `preview`, `variant`, `no_audio`, `render_dir` |
| `post_scene`  | `scene_id`, `video` (the scene's MP4, before audio padding), `timings` (the scene's timings dict), `frames` (folder of the scene's stills with `--frames`, else `None`), `preview`, `variant` |
| `post_render` | `output` (final MP4), `srt`, `timings` (combined timings dict), `timings_file`, `frames_index` (`frames/index.json` with `--frames`, else `None`), `preview`, `variant` |

Render hooks run in the `vidgen render` process (not in the per-scene worker processes);
`post_scene` runs once per scene rendered in this run (not for reused renders).
`vidgen storyboard` dispatches `post_scene` for the scenes it renders, but not `pre_render` or
`post_render` (it does not make a video).

```python
@hook("pre_tts")
def never_regenerate_intro(ctx):
    if "intro_b1" in ctx.data["beats"]:
        ctx.data["beats"].remove("intro_b1")
```

## 6. Overriding a built-in

```python
@scene("title", override=True)   # replaces the built-in "title" for this project only
class MyTitle(NarratedScene): ...
```

Without `override=True` a name clash with a built-in is an error; two extension files using the
same name is always an error. `vidgen list-scenes` marks overrides.

## 7. Promoting an extension into the core

Built-in scenes use exactly the same API. To promote `extensions/big_number.py`:
1. copy it to `src/vidgen/scenes/big_number.py` (turn relative imports of your helpers into
   imports from a core module, or move the helpers along),
2. add it to the import list in `src/vidgen/scenes/__init__.py`,
3. add tests; delete the project copy (or keep it with `override=True`).

It is now listed as `builtin` by `vidgen list-scenes`.
