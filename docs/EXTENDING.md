# Extending vidgen from your project

Every project can add its own **scene types**, **helpers**, **theme tokens**, **hooks** and
**per-beat actions** in its `extensions/` folder. Nothing in vidgen has to change, and a finished extension can later be
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
`palette_color(i)`, `font`, `font_serif`, `font_mono`, `font_for(role)`, `background`) and `self.project` (`root` folder, `config`,
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

An icon param is typed `IconName` (`icon: IconName = "cpu"`, or `IconName | None`): `vidgen
validate` checks the name against the built-in and the project's icons (suggesting close names
and icons tagged like it), `vidgen list-scenes` shows its type as `icon`, and `vidgen schema`
gives it an `enum` of the icon names.

Params can nest: use another `SceneParams` class as a field type (also in lists). Theme tokens
are checked inside nested models too, and `vidgen list-scenes` prints the nested fields. A nested
model that also takes a shorthand (the built-in `bullets` items are a string or `{text, icon}`:
a `model_validator(mode="before")` turns the string into `{text: ...}`) sets `also_accepts =
(str,)` on the class, so `list-scenes` shows `list[str | BulletItem]`.

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
- `self.region(name)` (or `region(name, area=None)`; `area` is a `Region` or another region's
  name, e.g. `region("left", "body")`) — named parts of the safe area:

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
- `grid_shape(n, aspect=None, cell_aspect=1.0, max_cols=None)` — `(rows, cols)` for `n` items
  in an area of that aspect (width / height; a number, a region name or a `Region`; default
  the safe area): the shape whose cells, kept at `cell_aspect` (width / height of one item),
  come out largest; near-ties (3 %) go to fewer empty cells, then fewer rows. So 3 items in a
  16:9 body make one row and in 9:16 three rows; 6 items 2 x 3 and 3 x 2. Combine it with
  `grid`: `rows, cols = grid_shape(len(items), body)`, `cells = body.grid(rows, cols)`. The
  built-in `icon_grid` tries a few `cell_aspect`s and keeps the layout with the largest text
  and icons.
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
- `place()` and `shrink_to_fit()` scale icons inside a group with the group, strokes included
  (a plain `group.scale()` leaves stroke widths alone).

**Icons.** `icon(name, size="body", color="text", stroke_width=None, *, height=None)` returns
an `Icon` (a `VGroup`) drawn from the built-in set or the project's `assets/icons/<name>.svg`
(docs/CONFIG.md "Icons", the catalogue docs/ICONS.md; `vidgen list-icons --search TEXT
--sheet icons.png` to choose one). `name` may be an alias (`icon("home")` draws `house`).
- `size` is a theme size token or a number of points, like text: the icon suits text of that
  size (its box is 1.5 em high: `ICON_UNITS_PER_POINT` = 0.0208 units per point, a `body` icon
  is 0.67 units). `height=` gives the box height in Manim units instead (a hero icon:
  `icon("brain", height=3)`, or `place(icon("brain"), self.region("hero"))`).
- The box is the SVG's whole `viewBox` (Lucide: 24 x 24 including ~2 units of padding), so icons
  of one size align and centre alike; it is an invisible first part (`mob.box`, drawn parts:
  `mob.parts`). The layout dump and lint measure what is drawn.
- `color` is a theme token, `#hex` or Manim colour for every visible stroke and fill; `None`
  keeps the colours written in a project SVG (only `currentColor` becomes `text`).
- Strokes are converted from SVG units (Lucide: 2 of 24) to Manim's stroke width for the size,
  and `Icon.scale()` scales them too (`scale_stroke=True` by default, unlike other mobjects), so
  `place()`, `.scale()`, `.animate.scale()` and `GrowFromCenter` keep the drawing's
  proportions at any size and resolution. `stroke_width=1.5` (SVG units) draws lighter lines,
  `2.5` bolder.
- `FadeIn`, `Create`, `Write`, `GrowFromCenter`, `Transform` work as on any `VGroup`. Unknown
  names raise `VidgenError` with suggestions. In the layout dump an icon is one object of kind
  `icon` with its name (`icon: "cpu"`); `lint_ignore` `object:` patterns match the icon name.

```python
row = VGroup(*[
    VGroup(icon(name, "heading", "primary"), self.text(label, size="caption")).arrange(DOWN, buff=0.15)
    for name, label in [("database", "Store"), ("cpu", "Compute"), ("chart-line", "Report")]
]).arrange(RIGHT, buff=1.0)
place(row, self.region("hero"), max_scale=1.0)
```

The built-in `bullets` (items `{text, icon}`), `title`, `end_card` and `icon_grid` take
`IconName` params (docs/CONFIG.md "Built-in scenes"); their code is a worked example. Animate an icon that belongs to a group with the whole
group, or add the group to the scene first (`self.add(group)`): an introducing animation of a
part alone (`FadeIn(group[0])`) adds that part by itself and dissolves the group in the scene.

**Text and numbers.**
- `fit_text(text, max_width, max_height=None, size="body", color="text", weight=NORMAL,
  align="center", highlights={"77%": "highlight"}, squeeze=1.0, font=None, ...)` — wraps by
  measured width, lowers the font size (down to `min_size`) until the block fits `max_height`,
  then scales down if still needed. Returns a Manim `Paragraph` (one submobject per line).
  `font` defaults to the theme font; pass `role="heading"` (or any font role; the same as
  `font=self.theme.font_for("heading")`) so your scene follows the theme's font roles like the
  built-ins (docs/CONFIG.md "Fonts"). `self.text`, `self.markup`, `T`, `MT` and
  `readable_text` take `role=` too; an explicit `font=` wins. The
  bundled families (Inter, Source Serif 4, JetBrains Mono NL) are registered before any scene
  code runs, so `self.text("x", font="Source Serif 4")` works without an installed font.
  `balance=True` evens out wrapped lines (the narrowest width with as many lines: no lone last
  word), as the `timeline` scene's event texts do.
- `measure_text(text, max_width, size=..., weight=..., role=..., balance=False)` — how
  `fit_text` would wrap the text, without building it: `TextMeasure(lines, width, height,
  fits)` (`fits` is false when a word is wider than the width). Cheap, so a layout can try many
  sizes or widths and build only the one it keeps; estimates are a few percent short, so
  measure a little narrower (x0.97) and check the built result.
- `shrink_to_fit(mobject, max_width, max_height)` — scale down only, never up.
- `wrap_lines(text, max_chars)`, `normalize_text(text)` — pure helpers.
- `nice_ticks(lo, hi, max_ticks)`, `auto_format(values)`, `format_value(v, fmt, unit)`,
  `check_format(fmt)` — chart axes and labels without LaTeX.

**Graphs.** `layered_layout(nodes, edges, direction="LR", layer_gap=1.0, node_gap=0.5,
routing="straight")` places a directed graph in layers (what the `diagram` scene draws with):
`nodes` are ids or `GraphNode(id, width, height, shape)` (`shape` `box`, `ellipse`,
`diamond` or `stadium`: the outline edges are clipped to), `edges` are `(source, target)` pairs
or `GraphEdge(source, target, label=(w, h))` (room for a label is kept in the gap next to the
source). It returns a `GraphLayout`: `nodes[id]` → `NodePlace(x, y, width, height, layer,
order)` centred on the origin (y up), `edges` → `EdgeRoute(source, target, points, reversed,
label_at)` in input order (`points` run from the source's outline to the target's; `reversed`
marks an edge that closes a cycle and runs backwards), `layers`, `width`, `height` and
`crossings`. `direction="TB"` stacks the layers top to bottom; `routing="orthogonal"` gives
right-angled routes. Pure Python and deterministic; unknown ids and self-loops raise
`VidgenError`. Draw the routes however your scene likes:

```python
layout = layered_layout([GraphNode(n, 1.6, 0.7) for n in ("in", "mid", "out")], [("in", "mid"), ("mid", "out")])
for e in layout.edges:
    self.add(Arrow(*[np.array([x, y, 0]) for x, y in (e.points[0], e.points[-1])], buff=0))
for name, at in layout.nodes.items():
    self.add(RoundedRectangle(width=at.width, height=at.height, corner_radius=0.15).move_to([at.x, at.y, 0]))
```

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

Ready-made helpers in `vidgen.api`: `T(s, size, color, weight, *, role=None)` / `MT(...)` (text /
Pango markup in the theme font, or the family of a font `role` — the function forms of
`self.text` / `self.markup`), `column` (a layer of dots; `horizontal=True` for a row,
`skip=k` leaves slot k empty for an ellipsis), `edges` (lines between two layers; `colors=` one
colour per pair, `shorten=` starts them at the rim of the dots), `dense_pairs`, `grouped_pairs(n,
groups, m=None)` (blocks connected block to block, also between layers of different sizes),
`sparse_pairs(n, m, ratio, seed)` (a reproducible share of the pairs, every unit keeping one),
`group_bounds`, `counter` (text redrawn from a `ValueTracker`), `resolve_color`,
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

Arguments (all optional except the name): `base`, `background`, `font` (sans), `font_serif`,
`font_mono`, `colors`, `palette`, `sizes`, `code_style` (a Pygments style), `scale` (type scale,
docs/CONFIG.md "Type scales"; applied below the preset's own `sizes`), `fonts` (font per role:
a token `sans` / `serif` / `mono` or a family name, e.g. `{"heading": "serif", "quote":
"Lora"}`), `description`. `current_theme().font_for(role)` resolves a role: `video.yaml`
`fonts`, else the preset chain, else the built-in default (`code` → `mono`, `quote_mark` →
`serif`, anything else `sans`); tokens resolve to the theme's `font` / `font_serif` /
`font_mono` (docs/CONFIG.md "Fonts"). Names must not clash with a built-in
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

## 8. Per-beat actions: targets and custom actions

A beat's `actions:` (docs/CONFIG.md "Beat actions") act on named **targets** of the scene. A
scene type opts in by naming its parts; an action type is a small class. Both use the same API
as the built-ins (every built-in scene type, e.g. `bullets`/`bar_chart`, and
`src/vidgen/scenes/actions.py`).

**Targets in your scene type.**
- `target_patterns = ("item<N>", ...)` (class attribute): the forms of your names, shown by
  `vidgen list-scenes` and in error messages.
- classmethod `target_names(params) -> list[str]`: every name the scene will register for these
  params. `vidgen validate` checks each action's `target` against it (no rendering needed), so
  it must match what `construct()` registers.
- `self.target(names, mobject, entrance=None, outline=None) -> Target` in `construct()`, before
  the beat whose actions use it and while it has its full look (`dim`/`highlight` take its
  opacity at that moment as "full"): `names` is one name or a list (`["item3", "item:Render
  it"]`; a name is `word`, `word3`, a dotted `word2.part3` (a part of a part, as `col2.item3`)
  or `kind:any label`; several targets may share a name: a
  plain name then selects the ones on screen); `mobject` may be a group that is never added
  itself (e.g. a bar plus its labels); `entrance` returns the animations that bring it on
  screen (default `FadeIn`; `lambda: []` for a part that cannot appear alone); `outline` is
  what a `highlight` box or fill surrounds (default `mobject`). Give backdrops (cards,
  stripes) a negative `z_index`, and keep them out of the target's `mobject`, so a `fill`
  highlight lies between them and the text and a `color` highlight does not paint them.
- Build your own reveal steps with `self.entrance(target)`: it returns `[]` when the target is
  already on screen, so an item a `reveal` action showed early is not revealed twice. Also:
  `self.is_shown(t)`, `self.find_targets("bar:*")`, `self.on_screen_parts(t)` (the target's
  largest parts that are in the scene), `self.targets`.
- Actions run inside the scene's **waits** (`self.reveal`, `self.play_steps`, `self.wait`,
  `self.wait_seconds` and the end of `narrate`): leave time in each beat. A beat that animates
  until its very end gets its actions applied without animation (and a warning).

**A custom action** subclasses `Action` and is registered with `@action("name")` (a name clash
with a built-in needs `override=True`, as for scene types). `Options` (an `ActionOptions`
model: `ThemeColor`, `Field` constraints, docstrings) are the extra keys in the config. `apply`
returns the animations (played together, in the beat's remaining time); one instance is made
per use in the config, so it can keep what `revert` (for `until:`) needs.

```python
# extensions/checklist.py
from vidgen.api import *


@action("tick")
class Tick(Action):
    """Put a check mark right of each target; `until:` removes it."""

    class Options(ActionOptions):
        color: ThemeColor = "tertiary"
        """Colour of the mark."""

    run_time = 0.5           # default seconds (`run_time:` in the config overrides it)
    reversible = True        # `until:` allowed: implement revert()

    def apply(self, scene, targets):
        self.marks = [
            icon("check", size="heading", color=self.options.color).next_to(t.mobject, RIGHT, buff=0.3)
            for t in targets
        ]
        return [FadeIn(m, scale=0.6) for m in self.marks]

    def revert(self, scene, targets):
        return [FadeOut(m) for m in self.marks]


@scene("checklist")
class Checklist(NarratedScene):
    outro = 0.5
    target_patterns = ("item<N>",)

    class Params(SceneParams):
        items: list[str] = Field(min_length=1)

    @classmethod
    def target_names(cls, params):
        return [f"item{i}" for i in range(1, len(params.items) + 1)]

    def construct(self):
        body = self.region("body")
        rows = VGroup(*[readable_text(t, body.inset(0.8, 0), align="left") for t in self.params.items])
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.4)
        place(rows, body.inset(0.8, 0), fit="contain", max_scale=1.0, align="left")
        items = [self.target(f"item{i}", row) for i, row in enumerate(rows, start=1)]
        self.reveal([lambda t=t: self.entrance(t) for t in items])
        self.finish()
```

```yaml
- id: plan
  type: checklist
  params: {items: ["Write the beats", "Storyboard", "Lint"]}
  beats:
    - text: "Three steps."
    - text: "The first one is done."
      actions:
        - tick: item1
        - {action: highlight, target: item2, until: plan_b3}   # built-in actions work too
    - text: "And so is the storyboard."
      actions: [{tick: item2, color: accent}]
```

`needs_visible = True` (default) first reveals targets that are not on screen yet;
`needs_target = False` allows an action without `target`. `temporary = True` (with
`reversible`) has the runner play `revert` so that it ends with the beat (or, with `until:`,
with the beat before that one), like `zoom`; `moves_camera = True` keeps two such actions from
playing at once; `target_options = ("into",)` names options whose values are target names
(checked by `vidgen validate` like `target`; look them up with `scene.find_targets(name)`).

**The camera.** `NarratedScene` is a Manim `MovingCameraScene`: `self.camera.frame` can be
moved and scaled (`self.camera.frame.animate.set_width(4).move_to(dot)`). Every scene starts
with it on the whole frame; the layout dump and `vidgen lint` take a moved camera into account
(`camera.zoom` in the layout dump). The `zoom` action uses it. Animate the parts that are in the
scene (`scene.on_screen_parts(t)`), not a group of them that was never added: Manim would add
that group and draw its parts twice. New mobjects (like the marks above) are simply added by
their animation. `vidgen list-scenes` lists your action with its options; `vidgen schema`
includes them.
