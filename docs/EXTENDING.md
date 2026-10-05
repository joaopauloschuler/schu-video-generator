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
loads the project (`validate`, `list-scenes`, `render`). Check your work with:

```
vidgen validate          # unknown types, bad params, import errors (with file + traceback)
vidgen list-scenes       # every scene type, where it comes from, its params
```

Import everything from **`vidgen.api`** only: it re-exports all of `from manim import *` plus the
vidgen names. Anything else in vidgen is internal.

## 1. A new scene type

```python
# extensions/big_number.py
from vidgen.api import *


@scene("big_number")                      # the name used as `type:` in video.yaml
class BigNumber(NarratedScene):
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

Inside `construct()` you have `self.spec` (the scene's config), `self.params` (a `Params`
instance, or a plain dict without a `Params` class), `self.beats`, `self.theme`, `self.project`
(`self.project.asset("assets/logo.png")` resolves files).

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

## 2. Helpers shared across modules

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
`dense_pairs`, `grouped_pairs`, `counter` (text redrawn from a `ValueTracker`), `resolve_color`.
Sizes and colors take theme token names (`"body"`, `"accent"`) or literals (`32`, `"#FF0000"`).

## 3. Theme tokens

```python
# extensions/tokens.py
from vidgen.api import *

register_theme_defaults({"k2": "#F2A541", "k3": "#83C167"}, sizes={"huge": 96})
C_K2 = current_theme().color("k2")        # module-level theme access is fine
```

Then `self.text("x", color="k2")`, `T("x", "huge", "k3")`. Values in `video.yaml`
(`theme.colors.k2: ...`) always win over registered defaults, which win over vidgen's built-ins.

## 4. Hooks

```python
from vidgen.api import *

@hook("post_render")          # pre_tts, post_tts, pre_render, post_scene, post_render
def announce(ctx):            # ctx.project, ctx.event, ctx.data (dict; may be modified)
    print("rendered", ctx.project.output_path())
```

Hooks run in registration order. If a hook raises, the command stops with an error naming the
hook and its file.

Event data (see DESIGN.md §6.2):

| event         | `ctx.data` keys |
|---------------|-----------------|
| `pre_tts`     | `beats` (list of beat ids about to be generated; remove ids to skip them), `audio_dir`, `force`, `dry_run` |
| `post_tts`    | `generated` (beat ids written, in order), `audio_dir` |
| `pre_render`  | `scenes` (scene ids about to be rendered, config order; remove ids to reuse their existing render), `preview`, `variant`, `no_audio`, `render_dir` |
| `post_scene`  | `scene_id`, `video` (the scene's MP4, before audio padding), `timings` (the scene's timings dict), `preview`, `variant` |
| `post_render` | `output` (final MP4), `srt`, `timings` (combined timings dict), `timings_file`, `preview`, `variant` |

Render hooks run in the `vidgen render` process (not in the per-scene worker processes);
`post_scene` runs once per scene rendered in this run (not for reused renders).

```python
@hook("pre_tts")
def never_regenerate_intro(ctx):
    if "intro_b1" in ctx.data["beats"]:
        ctx.data["beats"].remove("intro_b1")
```

## 5. Overriding a built-in

```python
@scene("title", override=True)   # replaces the built-in "title" for this project only
class MyTitle(NarratedScene): ...
```

Without `override=True` a name clash with a built-in is an error; two extension files using the
same name is always an error. `vidgen list-scenes` marks overrides.

## 6. Promoting an extension into the core

Built-in scenes use exactly the same API. To promote `extensions/big_number.py`:
1. copy it to `src/vidgen/scenes/big_number.py` (turn relative imports of your helpers into
   imports from a core module, or move the helpers along),
2. add it to the import list in `src/vidgen/scenes/__init__.py`,
3. add tests; delete the project copy (or keep it with `override=True`).

It is now listed as `builtin` by `vidgen list-scenes`.
