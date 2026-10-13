# Extending vidgen from your project

Every project can add its own **scene types**, **helpers**, **theme tokens**, **hooks**,
**per-beat actions** and **overlays** in its `extensions/` folder. Nothing in vidgen has to change, and a finished extension can later be
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
vidgen names. Anything else in vidgen is internal. (`vidgen` is the Python package of the
schu-video-generator distribution; installing it gives both the package and the `vidgen`
command.)

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

A list param that may also be written as one item (`highlight: Lint` for `[Lint]`) is typed
`one_or_many(str)` (any item type): the validated value is always a list, and the schema and
`list-scenes` show both forms. Unknown keys are reported with the closest field names
(`unknown parameter 'colour'; did you mean 'color'?`). A field named `heading` also accepts
`title` (and the reverse, with `_size` / `_color`) when the model has only one of them, like
the built-ins' header band; set `header_synonyms = False` on a `Params` class whose `title` is
something else.

An icon param is typed `IconName` (`icon: IconName = "cpu"`, or `IconName | None`): `vidgen
validate` checks the name against the built-in and the project's icons (suggesting close names
and icons tagged like it), `vidgen list-scenes` shows its type as `icon`, and `vidgen schema`
gives it an `enum` of the icon names.

A character param is typed `CharacterName` (`who: CharacterName`, or `CharacterName | None`):
`vidgen validate` checks the name against the video's [`characters:`](CONFIG.md#characters-characters)
and suggests close names. In `construct`, `character(name, height=..., facing="right")` builds
that character as a `Character`: a `VGroup` of named parts (`PART_NAMES`: `body`, `legs` or
`leg_left` / `leg_right`, `arm_left`, `arm_right`, `head`, `eyes`, `brows`, `mouth`, `accessory`,
`tail`, `antenna`, `cape`; arms and single legs may have a lower segment, `arm_left_lower`, `leg_left_lower`, ...), drawn from its `look:`
(body shape, hair, accessories, outfit, species...; every generated look has the same part and shape names,
except the optional `accessory` part, an animal's `tail` (`look.species`; a frog and a robot have none), a
robot's `antenna` (shapes `default` and `dim`), a `cape` (the accessory) and a `dress` or `coat`
body's second shape `seated`, which `Character.seated` and the `sitting` pose show), the
feet at the origin (`feet()`). A character drawn from an SVG file (`look: {svg: ...}`, CONFIG.md
"Characters from SVG files") may lack parts and has its own shape names: check `has_part("arm_left")`
and `shape_names("mouth")` before posing it; its outline width follows `height`. `vidgen character NAME --png` shows
one still of it. Pose a part about its pivot with `set_part(part, angle=..., scale=..., shift=...,
shape=...)` (degrees counterclockwise as drawn facing right; its child parts follow, e.g. the
head carries the eyes), swap a shape with `swap("mouth", "open")`, mirror the whole character
with `face("left")` / `turn()`, show a generated character's front view with `face("front")`
(`has_front_view`; an SVG character keeps its side; `PoseChange(hero, facing="front")` turns to
it, DESIGN.md §69.44), and snapshot or restore a pose with `state()` / `set_state()`.
Move and scale the character with Manim's own `move_to` / `shift` / `scale`; poses set afterwards
land where it is. Named poses (`stand`, `pointing`, `waving`, `thinking`, `shrug`,
`arms_crossed`, `sitting`) and expressions (`neutral`, `happy`, `sad`, `angry`, `surprised`,
`worried`, `thinking`, `laughing`, `blushing`, `tongue_out`, `crying`, `dizzy`, `frightened`), plus the character's own (`names("pose")`, `names("expression")`), are
set at once with `set_pose(name)` / `set_expression(name)`, or animated part by part with
`self.play(PoseChange(hero, pose="waving", expression="happy"), run_time=0.8)` (each part eases
about its pivot, body first; `state=` takes any `CharacterState`). For a single part, call
`set_part` from an updater (`UpdateFromAlphaFunc(hero, lambda m, a: m.set_part("arm_left",
angle=120 * a))`), not `.animate` (that would move points along straight lines). Bend an arm so
its hand is on a point with `hero.reach("left", point)` (the elbow bends naturally; `bend=-1` the
other way) and a leg with `hero.plant("right", point)` (knee forward; needs `leg_left` /
`leg_right`); `hand_point("left")` / `foot_point("right")` say where the hand or sole is now. An arm
drawn in one piece (an older SVG) shows its elbow folded, so `reach` and the poses work on it
too (DESIGN.md §69.26). Lip sync:
inside `with self.narrate(0) as d:`, `self.speak(hero)` makes the mouth follow the beat's
`VisemeTrack`, timed from the beat's start by the scene's clock (`hero.lip_sync(self.beat_visemes(0),
clock=self.beat_clock())`), so it stays in step through a `PoseChange`; `stop_lip_sync()` ends it
(the mouth shows its pose's shape again; after the beat, `self.end_lip_sync(hero, track)` ends
it now or, when the next beat `overlap`s this line, once that beat ends, DESIGN.md §69.34); `show_viseme("O")` shows one of `VISEMES` at once; a
character without a mouth is left alone. `Walk(hero, x)` walks it along the ground to `x`
(`speed=`, units per second; `start_x=` / `park_x=` for an entrance or exit; `fade_in=` /
`fade_out=` seconds to appear or vanish on the way, as through a door, `passage_fade`; `depth=`
with `feet_y=` (the ground line's y at a depth) walks towards or away from the camera too,
growing or shrinking, from `hero.stage_depth`, DESIGN.md §69.44; `carried=` the props it holds,
which grow and fade with it; `opens_door=True` tells foley it opened a closed door: a creak), `Gesture(hero,
"wave")` (`point`, `wave`, `shrug`, `nod`, `shake_head`) and `Jump(hero, 0.4)` play a motion and
end in the pose; all three keep lip sync in step, and their timing is the pure functions
`walk_seconds`, `enter_path`, `exit_path`, `offstage_x` (no manim). These four animations add
the animation principles (anticipation, squash and stretch, overshoot and settle,
follow-through) by the character's `cartoon_motion` setting, `hero.motion` (`lively`, `calm`,
`none`; `character(name, motion=...)` passes a scene's setting, the character's own wins), or
their own `motion=` keyword; `Walk` and `Jump` then last longer by a wind-up and settle
(`walk_motion_seconds(walk_seconds(d), strength)`, `jump_motion_seconds(JUMP_SECONDS, strength)`
with `MOTION_LEVELS[setting]`). `hero.set_squash(x, y)` scales the whole figure about its feet
(not part of its state). For a part of your own that should lag and wobble (an antenna, a tail, a
hanging sign), `Spring.tuned(frequency_hz, damping_ratio)` (or `Spring(stiffness, damping)`) is
the damped spring the built-in follow-through uses: `spring.follow(x_of, seconds)` is where a
part on it is while it follows `x_of(seconds)` (pure, the same at any frame rate), so an updater
can turn the part by `k * (spring.follow(x_of, t) - x_of(t))`; `step_response`, `overshoot()` and
`settle_seconds()` help tune it (a damping ratio of 1 never overshoots). The built-in acting and moving
actions (`say`, `look_at`, `turn`, `emote`, `pose`, `react`, `effect`, `walk_to`, `enter`, `exit`,
`gesture`, `jump`) work on every target that is a `Character`, so register your characters as
targets (`self.target(name, hero)`) to let a video's beats act on them.
`KeyedMotion(mob, values_at, part=None)` moves any mobject (feet `x`, `y` on screen, `rotate`
degrees and `scale` about its feet) or, with `part=`, a `Character`'s part (its pose's shift,
angle and size) through the channel values `values_at(share)` returns; the pure helpers
`keyed_values(start, keys, seconds)` (with `Key(seconds, values, ease)`, eases named as Manim's
rate functions in `EASE_NAMES`), `MotionPath(points, smooth).at(share)` and `path_length` give
them. The built-in `keyframes` and `move_along` actions (`src/vidgen/scenes/keyframes_action.py`)
act on a `stage`'s characters, props and part targets `<character>.<part>`; a scene of your own
can register part targets the same way (`self.target("hero.arm_left", hero.parts["arm_left"])`)
and set `target_patterns` to include `"<character>"` to accept those actions.
The prop actions (`pick_up`, `hold`, `put_down`, `give`, `throw`, `open`, `close`, `blow_away`; `src/vidgen/scenes/handling.py`)
need `"<prop>"` in `target_patterns` and `Prop` targets. Their pieces are exported:
`ArmMove(character, [(share, {part: PartPose}), ...])` eases some parts through keys;
`PropMove(prop, to=, follow=, leave=, arrive=, height=, rise=, turns=, path=)` carries a prop from a hand
(`follow`, read every frame) to a point or another hand, on an arc with spin when `rise` > 0, or
along `path(u, start, end) -> (x, y, degrees)` (`blow_away` passes `blown_point`);
`character.reached_parts(hand, point)` gives the arm poses `reach` would set, and
`hold_point(character.shoulder_point(hand), character.character_height, character.facing)` where
a held prop sits. To keep a prop in a hand, give it an updater (`prop.add_updater(lambda m:
m.shift(hero.hand_point("left") - m.grip_point()))`); never add it to the `Character` (its parts
must not change). `prop.grip_point()` is where a hand holds it (a basket's handle, an open
umbrella's shaft; else its middle), and `PropMove` moves a prop by that point. A prop with
shapes (`prop.shapes`, a door's or an umbrella's `closed` / `open`) switches with `prop.show_shape(name)` or
the animation `PropReshape(prop, shape, at=, height=, follow=)` (the `open` / `close` actions);
`overhead_point(feet, height, facing)` is where a hand holds an open umbrella overhead.
A room of your own (DESIGN.md §69.42): `room_geometry(...)`, `window_parts(...)` and
`window_sky(light)` give the shapes and the sky outside (no manim), and `draw_room(geometry,
room_colors(wall, floor), wallpaper=, flooring=, windows=[WindowLook(parts, frame, curtains)],
sky=, short_side=, frame_area=)` draws them (its `views.show(sky)` recolours the windows'
sky); mark the room lit (`mark_lit`) but not its `WindowViews`. On a `stage`, `Stage.door(name)`
is a room's door prop. Furniture (§69.43) is `draw_prop` with a `FURNITURE` kind; a sofa's or a
bed's places are `prop.seat_places` (`prop.seat_point(k)` on screen), and `PROP_HANGS` says how
high a picture or a clock hangs (`StageItem(..., hang=)` places it with `stage_layout`).
The `effect` action (`src/vidgen/scenes/effect_action.py`) works on every `Character` target. Its
symbol is an `EffectSymbol(kind, color=, character_height=)` (kinds `EFFECT_KINDS`; the colour of
`effect_color(kind, None, theme.color)` by default): `symbol.follow(hero, avoid=[boxes])` gives it
an updater that keeps it on the head (`head_box(hero)`, spot chosen by `effect_spot`, clear of
`avoid`) and moves it with its own clock (`pop_scale`, `piece_pose`); add it to the scene yourself
(never to the `Character`), and set `symbol.leaving = symbol.age` to shrink it away.
The sitting actions (`sit_on`, `lean_on`, `stand_up`; `src/vidgen/scenes/sitting.py`) build on
`character.seated(state, seat)` (the hips on a seat `seat` character units high, the legs bent
by the solver), `character.leaning(state)`, `character.lowered(state, drop, stoop=)` (a crouch,
the feet kept) and `character.planted(state, soles)` (each leg's sole put at a point), all states
not drawn; `BodyMove(character, keys, x=, facing=, soles=)` plays one (an `ArmMove` that also
moves the feet's x and keeps the soles on the ground; `y=` eases the feet's y too). A `Prop`'s
`seat_point()` and `lean_edges()` say where to sit and lean (`None` when it has none).
The riding actions (`get_in`, `ride_to`, `get_out`; `src/vidgen/scenes/riding.py`) work on the
vehicle props (`VEHICLE_KINDS`, geometry in `VEHICLES`): `RiderSeat(rider, vehicle, place,
ratio)` with `place_rider(seat)` puts a rider on its seat where the vehicle is now (call it from
an updater on the rider, never add the rider to the vehicle), `riding_state(rider, vehicle,
place, state)` seats it (on a bicycle: leaning, feet on the pedals, hands on the handlebar), and
`Ride(vehicle, x, seats=, speed=, depth=, feet_y=)` drives the vehicle with its riders, wheels
turning (`Prop.turn_wheels`); `vehicle.prop_point(x, y)` maps the vehicle's prop units to the
screen. A boat, a hot-air balloon and a toy rocket (`medium(kind)`: `water` / `air`) fly a
`Course` instead (`Ride(..., rise=, drift=, away_y=, seed=)`; its pure points are
`balloon_point` and `rocket_point`); `Prop.pose_at(x, y, degrees)` sets a vehicle's place and
turn afresh, and `StageWater` draws a stage's water and bobs the boats on it (`boat_bob`).
Props that move by themselves (DESIGN.md §69.54): `draw_prop("clock" | "tv" | "lamp", ...,
living=True)` adds their moving parts, and `LivingProp(prop, start=, speed=, on=, seed=)` sets
them for a scene time (`update(t)`, from a scene updater; `switch(on, time)`); its `glow` (a
`PropGlow`, or `None`) is a mobject of its own to add right before the prop. The maths is pure:
`hand_angles(seconds)`, `parse_clock_time("21:45")`, `tv_picture(t, seed)`, `glow_box`, and
`redrawn_members(boxes, regions)` says which members drawn after a moving part must be redrawn
with it. The `switch_on` / `switch_off` actions call `Stage.switch_props(patterns, on, time)`,
the `knock` action `Stage.knock_on(patterns, time)` (any scene type with a `knock_on` method
takes it).
A `fireplace` and a `kettle` drawn `living` burn and steam the same way (`flame_shapes(t, seed,
lean)`, `steam_puffs(t, seed, lean)`; `LivingProp(..., wind=)` takes the felt wind force at a
time, its `steam` is a `PropSteam` to add right after the prop); `on_spans` gives when one is on.
Nature (DESIGN.md §69.55): `draw_prop("tree", ..., fruit=True)` tags each fruit's members with
`FRUIT_INDEX`; `Stage.drop_fruit(tree, onto)` returns a `FruitDrop` (a `PropMove` of a
`FallenFruit` along `drop_point`, its `lands_at` the thud); `Stage.add_flock(settings, start)`
puts a `Flock` (`flock_plan`, `bird_place`) in the sky.
Small props (DESIGN.md §69.56): `SMALL_PROPS`; a `phone` drawn `living` rings while on
(`LivingProp` redraws its whole drawing turned by `ring_shake(t, on_since(...))`; `ring_bursts`
gives the times of the `phone` sounds). Balloons float with `PropMove(..., path=lambda u, a, b:
float_point(u, a, b, seed=s))` to `float_end(start, top, force)`; a watering can pours with
`Pouring(prop, follow=, spout=)` and `WaterFlow(WaterDrops(name=...), spout=, direction=, ground=,
height=)` (`pour_tilt`, `pour_drops`; `prop.prop_point(*WATERING_SPOUT)` is the spout).
`character(name)` breathes, sways its head and blinks on its own (unless `idle: false`):
`stop_idle()` / `start_idle(seed=None)` turn that off and on; a blink never shows during a
`PoseChange`. Before drawing your own scene for characters on a set, check whether the built-in
`stage` type (CONFIG.md, a background, ground line, marks and depth; its characters are action
targets) already does it. Its geometry is exported for your own scenes: `stage_layout(items,
ground=, size=, frame_width=, frame_height=, marks=None)` places `StageItem(name, kind, at,
depth, scale)`s (`at`: a name of `MARKS` or an x from 0 to 1) and returns `StagePlacement`s
(`feet`, `height`) from the back to the front; `pose_name_problem(project.config, who, "pose",
name)` in `validate_project` reports a pose or expression the character does not know
(`stage_width=` places marks across a stage wider than the frame). For parallax in your own
scene, `layer_transform(factor, camera_center, zoom)` gives the `(scale, (dx, dy))` that shows a
layer drawn for the home view moved by `factor` of a camera move, and `layer_half_extent(...)`
how large to draw it. Props: `draw_prop(kind, height=, theme=, main=, detail=, facing=)` draws one
of `PROP_KINDS` (`table`, `tree`, `house`, ...) and `svg_prop(path, height=, name=)` an SVG file
(through `load_vector`), both a `Prop` with `feet()` like a character's, so a `StageItem(name,
"prop", at, depth, PROP_HEIGHTS[kind], lift)` places it; the layout dump reports it as kind `prop`.
Particles: `particle_field(self, "snow", ParticleSettings(density=2))` builds a `ParticleField`
for your scene (fewer at preview quality, `self.is_preview`) that moves on its own once added
(`self.add(field)`) and fades out with `self.play(fade_out(field))`; `particle_states(particle_seeds(kind,
count, seed), t)` gives the seeded positions without drawing anything.
Light: `StageLight(self.camera, light_grade("night"))` grades, as the camera draws, whatever you
pass to `mark_lit(...)` (leave text and bubbles unmarked: they keep their contrast);
`.change(grade, start, seconds)` and `.update(scene_time)` fade it (redraw everything while it
fades: return every mobject from `get_moving_mobjects`, as `stage` does). The maths is pure:
`light_grade`, `tint_grade`, `blend_grades`, `light_at`, `grade_rgbas`, `grade_pixels`;
`StageShadows([ShadowCaster(mob, ground_y, width, size)])` draws soft shadows (`follow()` in an
updater for things that move), `StarField(night_stars(area_share), box, short_side)` stars.
Wind: `Wind(0.6, seed=1)` is a pure, seeded wind (`.level(t)`, `.force(t, delay)`, `.change(level,
start, seconds)`, `.blown(start, t)`); `sway_degrees(kind, force, t)` and `bent_points(points,
degrees, foot_y, height)` bend a prop about its base, `trail_degrees(wind, t)` follows it on a
spring for `Character.set_wind(degrees)` (turns the pieces a generated look marks with
`TRAIL_ATTRIBUTE`: scarf end, long hair, bun, floppy / pointy ears, hat). `StageWind(wind,
[SwayingProp(prop, kind, x_share)], characters, x_share)` does both for a scene time (`update`);
a `ParticleField(..., wind=)` drifts with it. `felt_force(force)` is the force the swaying and
trailing use (strong wind more than in proportion); `blown_point(share, start, end, rise=, seed=)`
is a blown prop's seeded, gusty, tumbling path (`gusty_progress`, `blow_seconds(distance,
level)`, `LIGHT_PROPS`), and `Holdings.drop(prop)` takes a prop out of whoever holds it.
DESIGN.md §69 has the model, §69.3 the poses, §69.4 lip sync, §69.5 idle motion, §69.6 the
stage, §69.7 layers and the camera, §69.8 props, §69.9 particles, §69.31 light and shadows, §69.32 wind.

Params can nest: use another `SceneParams` class as a field type (also in lists). Theme tokens
are checked inside nested models too, and `vidgen list-scenes` prints the nested fields. A nested
model that also takes a shorthand (the built-in `bullets` items are a string or `{text, icon}`:
a `model_validator(mode="before")` turns the string into `{text: ...}`) sets `also_accepts =
(str,)` on the class, so `list-scenes` shows `list[str | BulletItem]`.

**Text to translate.** A param shown on screen as text is typed `TranslatableStr` (`title:
TranslatableStr = ""`, `labels: list[TranslatableStr]`, `TranslatableStr | None`, or as a mapping
key: `dict[TranslatableStr, list[float]]`): `vidgen translate-template` lists it and a
translation file replaces it (docs/CONFIG.md "Languages and translations"); ids, paths, colours,
number formats, code and LaTeX stay `str`. A param that names such a text (a `highlight` by
label) is typed `TextRef`: it follows the text's translation, as do action targets
`kind:<text>`. A nested model's shorthand that holds text says so with the class attribute
`text_shorthand`, keyed by the raw value's type: `{str: "text"}` (the string is the text, like a
bullet item), `{str: ("field", "id")}` plus `text_defaults = {"label": "id"}` (a diagram node:
the string is the id and the label defaults to it), `{str: ("after", ":")}` (the text follows
the first `:`), `{list: ("fields", ("x", "y", "label"))}` (by position), `{list: ("field",
"callouts")}`, `{dict: ("model", Other)}`. A `Params` model without these markers still works;
its texts are just not offered for translation. Action and overlay `Options` use the same types.

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

Checks that need the beats' actions in order (what happened in an earlier beat) go in the
classmethod `action_sequence_problems(spec, params, uses)`: `uses` are the scene's valid action
uses (`use.beat`, `use.location` such as `beats[1].actions[0]`, `use.config`); return
`(location, message)` pairs (`("beats[1].actions[0].to", "...")`). It runs in `vidgen validate`
and before a render, once every action is valid; `current_project()` is the active project. The
built-in `stage` replays its prop actions with `holding_problems` (a prop picked up from too far
away, given to someone not next to the giver, a seat taken, a walk of a character that sits).

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
  `check_format(fmt)` — chart axes and labels without LaTeX (the chart helpers below build on
  them).

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

**Charts.** The built-in charts are made of public helpers, so a project chart looks and
scales like them (docs/CONFIG.md "Charts: common to all chart types"):
- `chart_title(text, size="heading", color="text")` — bold, `heading` font role, fitted and
  centred in the `header` region (1.3x in portrait); continue with `body =
  self.safe_area.below(title, gap=0.45)`. `chart_caption(text, area)` sits at the bottom of
  `area` (then `area.above(caption, gap=0.3)`).
- `value_axis(values, lo=None, hi=None, max_ticks=6, log=False, fmt=None, unit="", title="",
  include_zero=False)` → a `ChartAxis(lo, hi, ticks, labels, log, title)` with round ticks
  (`axis_ticks(lo, hi, max_ticks, log=)`; decades on a log axis) and their labels
  (`tick_texts(ticks, fmt, unit, log=)`: shared decimals, `20k` / `3.4M` from 10 000 on,
  `short_number(v)`). Build a `ChartAxis` yourself for other ticks (categories: positions 0..n-1
  with their names as labels).
- `chart_axes(area, x, y, size="caption", grid="y"|"x"|"both"|"none", lines="x"|"xy",
  right=0, top=0)` → `ChartAxes`: tick labels left and below, axis titles, dashed gridlines,
  axis lines, colliding labels thinned; `axes.plot` (the data `Region`), `axes.point(x, y)`,
  `x_pos`, `y_pos`, `axes.group` (everything, not yet added) and its parts (`lines`, `grid`,
  `x_labels`, `y_labels`, `x_title`, `y_title`). `right` / `top` keep room for end labels or a
  legend.
- `chart_label_size(size)` — points for a size token, never below `readable_size()`.
- `chart_legend(entries, max_width, stack=False)` with entries `(name, color, swatch)` (`line`,
  `box` or a marker shape); `auto_legend(entries, axes.plot, points, max_width)` puts it in a
  plot corner that covers none of `points` (frame points: markers, `sample_path(polyline)`)
  and returns `(legend, centre)`, or `(legend, None)` when you must put it above the plot.
  `legend_spot(size, plot, points)` is the corner search alone.
- `chart_marker(kind, radius, color)` (`CHART_MARKERS`: circle, square, triangle, diamond) and
  `linear_fit(xs, ys)` → `LinearFit(slope, intercept, r2)` (callable; `.equation()`).
- `color_scale(values, kind="sequential"|"diverging", color="primary", low_color="primary",
  high_color="accent", center=0, lo=None, hi=None)` → a `ColorScale`: `scale(v)` is the hex
  colour of a value (interpolated in OKLab between theme colours; sequential from a faint tint
  of `color` to `color`, diverging symmetric around `center`), `scale.at(fraction)`,
  `scale.fraction(v)`. `color_bar(scale, length, vertical=True, title="", fmt=None, unit="")`
  draws it as a legend (gradient, round ticks, labels at a readable size). Write text on a
  filled shape with `text_color_on(fill)` (the theme's text or background colour, whichever
  reaches 4.5:1; else white / black) and predict a faded fill with `mix_colors(fill,
  theme.background, opacity)`.

```python
@scene("growth")
class Growth(NarratedScene):
    outro = 0.5

    def construct(self):
        title = chart_title("Users per month")
        body = self.safe_area.below(title, gap=0.45)
        months, users = [1, 2, 3, 4, 5, 6], [120, 340, 900, 2100, 5200, 12800]
        axes = chart_axes(body, value_axis(months, title="month"), value_axis(users, log=True, title="users"), grid="both")
        line = VMobject(stroke_color=self.theme.color("primary"), stroke_width=4)
        line.set_points_as_corners([axes.point(m, u) for m, u in zip(months, users)])
        self.reveal([[FadeIn(title), FadeIn(axes.group)], Create(line)])
        self.finish()
```

**Callouts.** The marks of the `screenshot` scene work on anything: a mobject, a `Region`, or
coordinates `[x, y]` / `[x, y, w, h]` (top-left corner and size) relative to `within=` (an image or
any mobject, a region; default: the frame), as fractions 0–1 or, with `units="px"`, pixels of an
image (`callout_area(area, within, units=)` does the conversion and returns a `Region`):
- `callout_box(area, label="")`, `callout_circle(area, label="")` — a rounded frame / an ellipse
  around the area (`padding`), the label as a tag on its edge.
- `callout_arrow(area, label="", curved=False, prefer_off=None)` — the label placed away from the
  area (`label_spot`: eight directions, inside `bounds`, clear of `avoid`, preferably off
  `prefer_off`; also `clearance=` (soft room from `avoid`), `rivals=` (boxes it must not stand
  clearly nearer than the area, e.g. a neighbour's value) and `straight=True` (above / below /
  beside first); a `side` gives way when no spot on it is clear) and an arrow from it to the
  area's edge.
- `callout_magnifier(area, label="", image=img, zoom=2.0, source=None)` — an inset of the image's
  area, `zoom` times larger (less when there is no room), cut from the image's pixels (or from
  `source`, a sharper file of the same picture) with Pillow; two lines join it to the area.
- `callout_spotlight(area, label="", cover=None, opacity=0.62)` — a shade over `cover` (default
  `within`, else the frame) with a hole at the area.
- `callout_label(text, color="highlight", size="caption")` — bold text on a plate of `color`,
  written in the theme colour that reads best on it, never below the readable size.
- `callout(kind, area, label, **options)` picks the helper by name (`CALLOUT_KINDS`).

All take `color` (theme token), `label_size`, `side` (`auto`, `top`, `bottom`, `left`, `right`),
`bounds` (default: the safe area), `avoid` (regions to keep labels off: pass the `extent()` of the
callouts already placed) and `scale` (build smaller for a camera zoomed in by `1 / scale`). Each
returns a `Callout` (a `Group`: `.mark`, `.tag`, `.area`, `.kind`); `callout.draw()` gives the
animations that bring it on screen (mark, then label), to play together.

```python
@scene("annotated")
class Annotated(NarratedScene):
    outro = 0.5

    def construct(self):
        boxes = VGroup(*[Square(1.2).set_fill(self.theme.color("primary"), 0.6) for _ in range(3)]).arrange(RIGHT, buff=0.8)
        place(boxes, self.region("body"), fit="none")
        middle = callout_box(boxes[1], "The middle one")
        corner = callout_arrow([0.85, 0.8], "A point of the frame", avoid=[middle.extent()])
        self.reveal([FadeIn(boxes), middle.draw(), corner.draw()])
        self.finish()
```

**Video clips.** `ClipMobject(path, timing)` is an image whose picture is a video file's frame at
the scene's current time (the `video_clip` scene uses it). `ClipTiming(start, end, speed=1.0,
loop=False)` says which seconds of the file play and how (`probe_clip(path)` gives a
`ClipInfo`: size, fps, duration, audio; `fit_speed(span, window)` a speed that fits a span into a
window). Size it like any mobject — `fit_box(width, height, "contain" | "cover")` fits or fills a
box (cover crops the picture, `clip.crop`) — call `set_resolution(scale)` when the camera will
zoom in, then `play(self)` to start it on the scene's clock (it runs through plays and waits; a
held last frame or the loop follow the timing). Fades, `dim` / `highlight` actions and
`set_opacity` work on the moving picture. Close it in `tear_down`. `clip_audio(path, wav, timing,
length=..., volume=...)` writes the clip's sound as it plays, for `self.add_sound(wav)`.

```python
@scene("clip_and_note")
class ClipAndNote(NarratedScene):
    outro = 0.5

    def construct(self):
        box = self.region("left")
        self.clip = ClipMobject(self.project.asset("assets/clip.mp4"), ClipTiming(0, 2, loop=True))
        self.clip.fit_box(box.width, box.height).move_to(box.center)
        self.clip.set_resolution().play(self)
        note = fit_text("Two seconds, looping", self.region("right").width, size="heading")
        place(note, self.region("right"), fit="none")
        self.reveal([FadeIn(self.clip), Write(note)])
        self.finish()

    def tear_down(self):
        self.clip.close()
        super().tear_down()
```

**Maps.** The bundled world map (Natural Earth 1:110m countries, the data behind the `map`
scene) is open to project scenes. `find_country(name)` looks a country up by ISO code, name or
alias and returns a `Country` (`a3`, `a2`, `name`, `label` point and `main` box in lon/lat,
`polygons`); `world_countries()` lists all 177. `MapView(box, area)` shows a lon/lat box
(`view_box("europe")`, `view_box([lon_min, lat_min, lon_max, lat_max])`, or `fit_view(points)`
around some places) in a scene `Region` with the Equal Earth projection (`equal_earth(lon, lat,
lon0)` is the projection itself): `view.region` is where the map lands, `view.point(lon, lat)` a
scene point and `view.polygons(country)` the country's polygons in scene points, clipped to the
view (each a list of rings, the outer ring first). `MAP_VIEWS` holds the named regions.

```python
@scene("capital")
class Capital(NarratedScene):
    outro = 0.5

    def construct(self):
        view = MapView(view_box("europe"), self.region("body"))
        land = VGroup(*[
            Polygon(*rings[0], fill_color=self.theme.color("dim"), fill_opacity=0.35,
                    stroke_color=self.theme.background, stroke_width=0.8)
            for country in world_countries(antarctica=False) for rings in view.polygons(country)
        ])
        paris = Dot(view.point(2.35, 48.86), radius=0.09, color=self.theme.color("highlight"))
        name = self.text("Paris", size="caption").next_to(paris, RIGHT, buff=0.12)
        self.reveal([FadeIn(land), [FadeIn(paris, scale=0.5), FadeIn(name)]])
        self.finish()
```

**Generated pictures** (docs/CONFIG.md "Generated images"). A param typed
`GenerateImage | None` (a top-level field of `Params`) is a `generate:` like the `image` scene's:
`vidgen imagegen` finds it in any scene type, `vidgen validate` warns about it, and
`self.generated_picture(params.generate)` returns the file to show — the stored picture once it
is made, else a placeholder card with the prompt. Rendering never calls the provider. A scene
type that sets the class attribute `uses_cartoon_style = True` (like `stage`) gets the video's
`cartoon_style` words added to its prompts, by `vidgen imagegen` and by `generated_picture` alike
(`generated_image(project, generate, theme, cartoon=True)` outside a scene).

```python
@scene("backdrop_title")
class BackdropTitle(NarratedScene):
    outro = 0.5

    class Params(SceneParams):
        title: TranslatableStr
        generate: GenerateImage

    def construct(self):
        picture = ImageMobject(str(self.generated_picture(self.params.generate)))
        picture.scale_to_fit_width(self.frame_width).set_opacity(0.45)
        title = fit_text(self.params.title, self.safe_width, size="title")
        self.reveal([[FadeIn(picture), Write(title)]])
        self.finish()
```

A `generate:` with `format: svg` (a vector picture) is stored as an `.svg`: `generated_picture`
returns that path once it is made (still a PNG placeholder before). Draw it as shapes with
`load_vector(path, *, height=1.0, recolor="none" | "theme", theme=None, simplify=False)`, which
sanitises the SVG first (no scripts, filters, rasters or text; gradients flattened; shapes and
points capped — docs/CONFIG.md "Vector (SVG) pictures") and returns a `VectorPicture` (a
`VGroup`: an invisible box spanning the `viewBox`, then the parts; strokes scale with it, the
layout dump reports it as one object of kind `vector`). `DrawBorderThenFill(picture)` traces then
fills it.

**Sound effects** (docs/CONFIG.md "Sound effects"). `self.sfx(sound, at=None, *, gain=0.0,
pan=0.0, align="start", **params)` plays a built-in sound (`vidgen list-sfx`) or the project's
`assets/sfx/<sound>.wav` at scene time `at` (seconds; default now, so it lands with the next
`play`); `params` are `duration`, `pitch` (semitones) and `intensity` (0–1). It takes no time and
draws nothing: the sound is recorded in `self.sfx_log` (`SfxEvent`s, written to the scene's
timings) and mixed into the video by `vidgen render`, sample-exact (not with `--no-audio`).
Unknown sounds and bad values raise `VidgenError`. `self.sting(sting, time)` plays a music sting
(`"reveal"`, `"comic"`, `"sad"` or a `StingCue(kind, gain=)`) at scene time `time`, ducked under the
narration like a beat's `sting:` (the `card` scene's `sting` param uses it). `self.sounds` is the scene's `SoundLibrary`
(`names()`, `knows(name)`); `synthesize(name, duration, pitch, intensity)` returns a built-in
sound's samples (48 kHz mono float32) if you want to analyse or mix one yourself. A scene type
that should make a sound when it starts with `sfx: {auto: true}` sets the class attribute
`entrance_sfx = ("whoosh", -3.0)` (sound, gain in dB), as `chapter` does. A scene type that
wants sounds tied to the beat actions overrides `action_foley(self, action, options, animations,
start, seconds)`: the action runner calls it for each built-in action as it starts playing, with
its scene start time and the seconds it plays (after any shortening); the base class does
nothing, `stage` plays its foley through the pure `foley_cues(PlayedAction(...))` (docs/CONFIG.md
"Foley and music stings"; `PlayedAction(prop=, through_door=, opens_door=, pours=)` for a door's
creak and a watering can's splash, `wet_steps(cues, wet_from)` adds splashes under the steps on
wet ground). A scene type's timings may name ambience beds (`ambience: [{bed, start, end}]`,
scene seconds; the beds of `vidgen.ambience.AMBIENCE_BEDS`): `stage` picks its set's with the pure
`set_ambience(setting, room=, lights=, rain=, end=)` (`SET_BEDS`; docs/CONFIG.md "Ambience and
door sounds"). Right after it the runner calls `action_motion_effects` with the same
arguments (nothing by default): `stage` turns each animation into `motion_effect_cues(...)` and
adds a `MotionEffect(cue, mover, delay=, seed=motion_seed(...))` per cue (dust, speed lines,
impact stars, a whoosh; docs/CONFIG.md "Motion effects"); `Walk(..., gait=RUNNING)` runs.
`particles_started(self, field, settings)` hears of every particle
field `particle_field` builds for the scene (before it is added; nothing by default): `stage`
grows `Puddles` under rain and plays the rain sound bed. A scene with a method `rain_ground()`
returning a `RainGround` (`rain_ground(ground, top, frame_height, shelters)` with `ShelterBox`es)
gets rain that ends there with splashes (docs/CONFIG.md "Rain on the ground"); one with
`snow_ground()` (the same, its shelters may also be `TopLine`s: a prop's upper edge) gets snow
with `settle: true` that lands there (flakes lie a moment, `flake_floors`, `rest_flakes`). `stage`
then grows a `SettledSnow` (a `SnowBlanket` and `SnowCap`s from `prop_top_line`, in
`settle_amount(settled_seconds(...))` steps) and draws its `fog` as `StageFog` bands
(`band_opacities`, `fog_cover`; docs/CONFIG.md "Snow that settles", "Fog"). Rain with
`lightning` (`storm_every(settings)`) gets a `RainStorm` of seeded `Strike`s (`storm_strikes`) on
the stage's `StageLight` (`strikes`, `storms`; `flash_grade`, `flash_level`), which also takes the
`lightning` action's strikes (`Stage.strike_lightning`), with a `LightningBolt` (`bolt_paths`) and
the `thunder` sound (`thunder_cue`, `thunder_delay`, `thunder_pan`); the `rainbow` action adds a
`StageRainbow` (`Rainbow`, `rainbow_level`), and a `light` action with `move_sun` moves the
stage's sun and moon as `SkyBody`s along the sky's path (`PathMove`, `path_point`, `place_for`),
the `StageShadows` cast away from them (`shadow_cast`, `set_cast`; docs/CONFIG.md "Lightning and
thunder", "Rainbows", "Light and shadows").
A scene type that adds beat actions of its own (automatic directing) overrides the class method
`auto_actions(cls, project, spec, params)` and returns `DirectedBeat(beat, actions)` items, each
action made with `ActionConfig.automatic({...})`; they are appended after each beat's written
actions before the actions are planned, and `vidgen direct` and the storyboard list them. The
base class adds none; `stage` returns `stage_directions(project, spec, characters,
params.auto_direct, stage_frame(project, params))` (its geometry, for the lint check of
gestures and close-ups; docs/CONFIG.md "Automatic directing").

```python
@scene("countdown")
class Countdown(NarratedScene):
    outro = 0.5

    def construct(self):
        dots = VGroup(*[Dot(radius=0.2) for _ in range(4)]).arrange(RIGHT, buff=0.6)
        for i, d in self.timeline():
            if i == 0:
                self.sfx("whoosh", duration=0.5)            # now: with the next play
                self.play(FadeIn(dots[0], shift=RIGHT), run_time=0.5)
                for k, dot in enumerate(dots[1:], start=1):
                    self.sfx("tick", pitch=2 * k)           # rising ticks, one per dot
                    self.play(FadeIn(dot, scale=0.5), run_time=0.3)
                self.sfx("success", at=self.renderer.time + 0.2, gain=-3)
        self.finish()
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
- When the next beat has `overlap` or `interrupt` (DESIGN.md §69.34), `narrate` yields the time
  until that beat starts instead of `d`, and nothing is waited after it: call the next
  `narrate` right after the block. `self.beat_window(i)` gives `body` (what is yielded),
  `window` (until the next beat), `heard` (seconds of the voice) and the voice's `shape`.
- `self.finish()` fades everything out over `self.outro` seconds (class attribute, default 0;
  the built-ins use 0.5). Set `outro` on your class and call `finish()` at the end of
  `construct()`; silent scenes then fade out within their `duration`. It fades vector
  mobjects with `Fade` (`Fade(group, shift=UP * 0.1)` in, `Fade(group, out=True)` /
  `fade_out(m)` out): Manim's `FadeIn` / `FadeOut` copy the whole mobject twice when they
  begin, which takes seconds for big groups (a long code listing); `Fade` animates only the
  colours (and `shift`), so prefer it for anything large.
- Transitions (docs/CONFIG.md "Transitions"): when a crossfade, colour fade, push or wipe leads
  to the next scene, `finish()` holds the picture for `outro` instead of fading it (the transition takes it
  away), and the scene is held longer at its end when its silent tail is too short; both happen
  for you. `self.transition_in` / `self.transition_out` are the planned transitions
  (`TransitionSlot(type, seconds, color, overlap, fade_out, fade_in, hold)`, frames; `None`
  when the video has none). A scene that fades itself out with `clear_all` still works: the
  crossfade then blends its faded picture. Keep to the timing contract (beats + `outro`) so the
  overlaps land where planned. A `push` / `wipe` into your scene moves its first
  `transition_in.overlap` frames: the worker renders them without overlays (they are drawn once
  over the moving pictures at the join), which needs nothing from your code.
- Continuity (`carry:`, docs/CONFIG.md "Continuity"): targets you register (`self.target(...)`)
  are what other scenes carry. When the next scene carries some, `finish()` keeps them on screen
  while the rest fades (`self.clear_all(run_time, keep=[mobjects])` does the same for your own
  ending; `self.carry_out` lists the names) and their look is recorded after `tear_down`. When
  your scene carries objects in, they are on screen from its first frame; `self.entrance(target)`
  moves a waiting copy into the target instead of its own entrance, so a scene that brings its
  targets in with `entrance()` needs nothing more. To animate the copy yourself, take it with
  `copy = self.carry_in("heading")` (by destination or source name; `None` when nothing was
  carried) and e.g. `self.play(carry_move(copy, my_heading))` (`vidgen.api.carry_move`: shape by
  shape when the shape counts match, else a stretched cross-fade) or `Fade(copy, out=True)`.
  Only vector shapes are carried.
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
| `post_render` | `output` (final MP4), `srt`, `timings` (combined timings dict), `timings_file`, `frames_index` (`frames/index.json` with `--frames`, else `None`), `chapters` (the YouTube chapter list `<output>_chapters.txt`, `None` without chapters or with `chapters: {youtube: false}`), `thumbnail` (`<output>_thumbnail.png` when a `thumbnail:` config wrote one, else `None`; the hook runs after it), `preview`, `variant` |

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
- `self.target(names, mobject, entrance=None, outline=None, on_fill=()) -> Target` in `construct()`, before
  the beat whose actions use it and while it has its full look (`dim`/`highlight` take its
  opacity at that moment as "full"): `names` is one name or a list (`["item3", "item:Render
  it"]`; a name is `word`, `word3`, a dotted `word2.part3` (a part of a part, as `col2.item3`)
  or `kind:any label`; several targets may share a name: a
  plain name then selects the ones on screen); `mobject` may be a group that is never added
  itself (e.g. a bar plus its labels); `entrance` returns the animations that bring it on
  screen (default `FadeIn`; `lambda: []` for a part that cannot appear alone); `outline` is
  what a `highlight` box or fill surrounds (default `mobject`; boxes follow it when the scene
  moves it later); `on_fill` lists `(text, shape)` pairs of text written on a filled shape of
  the target (a value on a cell, a label on a plate): `dim` and `highlight` then give the text
  the colour that reads on the shape's new look instead of fading or painting it with the
  shape. Give backdrops (cards,
  stripes) a negative `z_index`, and keep them out of the target's `mobject`, so a `fill`
  highlight lies between them and the text and a `color` highlight does not paint them. When
  your scene dims a target on its own (as `bullets`' `dim_previous`), set `target.scene_dim =
  factor` (its share of full opacity), so undoing a `dim` action (`until`) keeps that dimming.
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
playing at once and starts the action before the others due with it; `after_camera = True` (the built-in `callout`) plays after a camera move due at
the same moment, so it is built for the new view; `target_options = ("into",)` names options whose values are target names
(checked by `vidgen validate` like `target`; look them up with `scene.find_targets(name)`).
`until_next_beat = True` (with `reversible`) undoes the action when the next beat starts unless
the use gives `until` (the built-in `callout`); override `default_until(later)` (the ids of the
beats after the action's own) to choose per use, e.g. by an option. `problems()` returns
`(key, message)` pairs for checks that need more than the options (the target, `until`), and
`provides()` the target names the use registers when applied (`scene.target(name, mob)` in
`apply`), which later actions of the scene may then use — `vidgen validate` checks both.
`scene_problems(scene_cls, params)` returns the problems that depend on the scene (the built-in
`pan` checks its `to` with `scene_cls.camera_place(params, to)`).
`character_needs()` names the entry of `vidgen.cartoon.cast.ACTION_NEEDS` (`"say"`, `"look_at"`,
`"emote"`, ...) the use needs of the characters it targets; `vidgen validate` then warns when one
lacks those parts (the built-in acting actions in `src/vidgen/scenes/acting.py`).
`run_time_for(scene, targets)` returns the run time the use needs for its targets as they are
when it falls due (the built-in `walk_to`: the distance over its speed), or `None` for the class's
`run_time`; a `run_time:` in the config wins. `alters_targets = False` says the action only reads
its targets (the built-in `pan` and `follow`), so it plays together with another action on them
that falls due at the same moment instead of before or after it.
A scene type that lists action type names in its class attribute `mid_still_actions` (the
built-in `stage`: `walk_to`, `enter`, `exit`, `gesture`, `jump`, `keyframes`, `move_along`,
`pick_up`, `put_down`, `give`, `throw`, `sit_on`, `lean_on`, `stand_up`, `blow_away`, `get_in`, `ride_to`, `get_out`) gets a
still half-way through each use of them whenever stills are taken (`vidgen storyboard`,
`render --frames`), besides the beat ends (docs/CONFIG.md "Frame stills").
The built-in `callout` action (`src/vidgen/scenes/callout_action.py`) is an example of all
three, built on the callout helpers below. An action that draws nothing sets `animates = False`
and implements `cue(self, scene, time)` instead of `apply`: the runner calls it when the beat
starts with the scene time the use is due (`at`, on a frame), whatever the scene animates then;
with `scene_targets = False` its `target` names something other than a scene target (checked by
your `problems()`, not against the scene's targets). The built-in `sfx` action
(`src/vidgen/scenes/sfx_action.py`) is both: `- sfx: pop` cues `scene.sfx("pop", time)`; so is
the `light` action (`- light: night` cues the stage's `change_light`), and so are `lightning` and
`rainbow` (`strike_lightning`, `show_rainbow`). The
built-in `particles` action (`src/vidgen/scenes/particles_action.py`) also has `scene_targets =
False` (`- particles: snow`), but animates: its `apply` adds a mobject that moves on its own and
returns no animation.

**The camera.** `NarratedScene` is a Manim `MovingCameraScene`: `self.camera.frame` can be
moved and scaled (`self.camera.frame.animate.set_width(4).move_to(dot)`). Every scene starts
with it on the whole frame; the layout dump and `vidgen lint` take a moved camera into account
(`camera.zoom` in the layout dump). The `zoom`, `pan` and `follow` actions use it and keep the
view inside `scene.camera_bounds()` (`(left, right, bottom, top)`; the frame, unless the scene
type overrides it, as a wide `stage` does; clamp your own views with `view_center_within(bounds,
center, width, height)`). A scene type that names places for `pan: {to: ...}` overrides the
classmethod `camera_place(params, place)` (an x from 0 to 1 of the bounds' width). `follow_with_camera(x_of)`
keeps the camera on the x a callable gives on every frame (`None` stops), and
`add_camera_listener(callback)` calls `callback()` on every frame after the camera moved (the
stage moves its parallax layers so); both run as one scene updater after every animation. A
listener must place things from the camera alone: it also runs before each animation, and while
the camera neither follows nor animates, Manim draws what comes before the first moving mobject
once into a static image for that animation.
`zoom` comes back to the view it started from. A beat's `shot:` (DESIGN.md §69.29) works on a
scene type with a `shot_framing(kind, names)` method returning `(ShotView, Shot)` (the built-in
`stage`; the framing maths is `frame_shot` / `shot_figures` / `shot_view`); while a shot is on,
`scene.camera_shot` holds what the layout dump records and `scene.shot_home` the view the next
beat goes back to. On a stage wider than the frame the stage adds automatic `pan`s that keep
the speaker in view (`reframe`, §69.30; `reframe_path` is the pure path). Animate the parts that are in the
scene (`scene.on_screen_parts(t)`), not a group of them that was never added: Manim would add
that group and draw its parts twice. New mobjects (like the marks above) are simply added by
their animation. `vidgen list-scenes` lists your action with its options; `vidgen schema`
includes them.

## 9. Overlays: custom overlay types

An overlay (docs/CONFIG.md "Overlays") is drawn on top of every scene it applies to, fixed to
the screen: the scene's camera and fades never touch it. A project adds overlay types the way it
adds actions: a class registered with `@overlay("name")`, its `Options` (an `OverlayOptions`
model) being the extra keys of the `overlays:` entry. The built-ins are in
`src/vidgen/scenes/overlays.py` (`lower_third`, `watermark`), `src/vidgen/scenes/progress.py`
(`progress_bar`, `chapter_indicator`) and `src/vidgen/scenes/captions.py` (`captions`).

```python
# extensions/badge.py
from vidgen.api import *


@overlay("badge")
class Badge(Overlay):
    """A "LIVE" badge in the top left corner that blinks every other second."""

    class Options(OverlayOptions):
        label: str = "LIVE"
        """The badge text."""
        color: ThemeColor = "accent"
        """Plate colour."""

    def build(self):                       # once per scene render: the full look, in place
        text = T(self.options.label, "caption", text_color_on(resolve_color(self.options.color)), weight=BOLD)
        plate = SurroundingRectangle(text, buff=0.12, corner_radius=0.08)
        plate.set_fill(resolve_color(self.options.color), opacity=1).set_stroke(width=0)
        badge = VGroup(plate, text)
        place(badge, safe_area(), fit="none", align="top_left")
        return badge

    def state(self, t):                    # t: seconds in the video
        return "on" if int(t) % 2 == 0 else None    # None hides it

    timed = True                           # its look depends on where the scene is in the video
```

```yaml
overlays:
  - {type: badge, label: "ON AIR", scenes: [interview]}
```

**What an overlay is.**
- `build()` returns the mobject at its full look, placed on the whole frame (`safe_area()`,
  `region(...)`, `place(...)`, `frame_region()` work as in scenes; the frame is never moved by the
  scene's camera). It is called once per scene render.
- `state(t)` says how it looks at **video** time `t` (inside its `from`/`to` span and its
  `window()`): any hashable value, `None` to hide it. It must be a pure function of `t`, so the
  overlay looks the same at the end of one scene and the start of the next. Frames with equal
  states are drawn once and cached; return a coarse value (`round(p, 3)`) rather than `t` itself.
- `pose(mobject, state)` returns the mobject to draw for a state (a copy: `with_opacity(mob, p)`
  fades one, `.shift(...)` moves it); `settled(state)` says whether it is the full look (lint
  checks only settled overlays).
- `window()` narrows where it is shown (video seconds `(start, end)`; default the whole span);
  `self.interval()` is the span and window combined, `self.transition(t, start, end, enter,
  exit)` an eased 0..1 progress for slides and fades.
- Set `timed = True` when `state` depends on the video time without a `window()` or `from`/`to`
  (a progress bar): the scene's position in the video is then computed (it costs reading every
  beat's MP3 length).
- `self.context` (`OverlayContext`): `scene` (this scene's planned `SceneSlot`: `id`, `index`,
  `start` and `duration` in the video, `beats` with `start`/`end` from the scene's start and
  `text`, `chapter`: the chapter's title; with crossfades `overlap_in` / `overlap_out` in seconds
  and `cut`, where the next scene starts: the scene's overlays are drawn until `cut`, the next
  scene's from then on, also inside this scene's render), `scenes`, `duration` (the whole video), `chapters`
  (the video's chapters, see below), `chapter` (this scene's `Chapter`, `None` before the first),
  `fps`, `video_time(scene_time)`, `scene_start(id)`, `project`, `theme`, `plan`. Times are *planned* (docs/CONFIG.md "Overlays", Timing).
  `self.options`, `self.config` (the entry), `self.id`, `self.scenes` (ids of the scenes it is
  drawn on), `self.span` (`from`/`to` in video seconds, `math.inf` without an end).
- `shown_in(start, end)` (only asked of timed overlays): `False` when it stays hidden all the
  way through a scene's slot, which leaves it out of that scene's render: nothing drawn, nothing
  reserved (the chapter indicator on chapter cards). Default `True`.
- classmethod `validate_project(options, project, scenes) -> list[str]`: checks `vidgen
  validate` runs (a file exists, a beat id exists), one `"option: message"` per problem.
- Class attributes: `layer` (drawing order between overlays, default 0), `lint_skip` (rules not
  applied to its objects, e.g. `("contrast",)` for something faint on purpose), `yields`
  (default `False`; `True`: built after the scene's other overlays, with `self.clear_of` = the
  boxes of those that reserve room; in `build`, `free = self.clear_area(area, mobject)` gives the
  area without the boxes the placed mobject comes near — place it again there, as the built-in
  `lower_third` does to move above bottom captions).
- `default_reserve()`: whether scenes keep clear of it when the entry gives no `reserve`
  (default `False`; the built-in `captions` say `True` at the top or bottom); `self.reserves` is
  the answer for this entry and scene.

Overlays are composited into each frame as the scene renders, so stills, the layout dump
(objects with `overlay: <id>`) and `vidgen lint` (`overlay_overlap`) see them; a reserving
entry shrinks `self.safe_area` of the scenes it is drawn on (and so `self.region(...)`), which
scene types that lay out in the safe area follow automatically. `vidgen list-scenes` lists your
overlay type with its options; `vidgen schema` includes them. Overlays are drawn with a camera
cropped to their box, so a thin or small overlay costs little per state.

**Chapters.** `video_chapters(project, fps=None, intro=False)` returns the video's chapters (docs/CONFIG.md
"Chapters": `chapter` scenes and scenes with a `chapter:` key) as `Chapter` records: `title`,
`number` (as written, or `None`), `label` (the number, else the position), `scene` (where it
starts), `start` / `end` / `duration` in the video (planned, at `fps`, default the final
format's), `index` (1-based), `count`, `card` (starts with a `chapter` scene), `intro`. An
overlay gets the same list as `self.context.chapters`. `intro=True` gives the list as the render
publishes it in the MP4 and the YouTube list (docs/CONFIG.md "Chapters in the outputs"): it
starts at 0:00 — with a chapter titled `chapters.intro` (`intro=True` on that record, `scene` the
first scene) before a later first chapter, or that chapter moved to 0:00 with `intro: false` —
and `index` / `count` are positions in that list.

**Narration text and word times** (what the `captions` overlay is built from, for an overlay or a
scene that shows the narration its own way):
- `beat_word_times(audio_dir, beat_id, text, start, end) -> [WordTime(text, start, end)]`: when
  each word of a beat is spoken, `start`..`end` being its narration (e.g. a `BeatSlot`'s, from
  `self.context.scene.beats`; audio folder `self.context.project.audio_dir`): from the stored
  ElevenLabs alignment (`voice.timestamps`), else estimated within the MP3's speech, else over the
  beat. `estimate_word_times(words, start, end)` is the estimate alone (by `syllables(word)`,
  with pauses after punctuation); `speech_bounds(path)` finds the speech in an audio file;
  `spoken_words(text)` counts spoken words (numbers, acronyms).
  With a project `pronunciation:` (docs/CONFIG.md "Pronunciation") or voice sounds (`[laugh]`,
  docs/CONFIG.md "Voice sounds") the MP3 says something else than the written text: pass
  `spoken=project.spoken(beat)` (a `Spoken`: `text`, `spoken`, `replacements`, `word_groups()`;
  `project.pronunciation.apply(text)` for a text without sounds) as the last argument to get the
  written words timed by their spoken form (`map_word_times(spoken, times)` does that mapping for
  times of the spoken words). `project.spoken_texts()` gives what the TTS says per beat;
  `beat.voice_sounds` lists a beat's sounds (their markers are not in `beat.text`).
- `caption_cues(text, start, end, *, words=None, widths=None, space=1, max_width=42,
  max_lines=2, max_words=None, until=None, prefix="", prefix_width=None) -> [CaptionCue(start,
  end, lines, words, prefix)]`: the text cut at phrase boundaries into cues (`segment_cues`, costs
  by `phrase_break_cost`), each timed from its first word to the next cue — the same cutting as
  the SRT (widths in characters there, measured with `measure_text` in `captions`). `prefix` (a
  speaker tag) starts the first cue, glued to the first word, and is not one of its `words`.
- **Language** (docs/CONFIG.md "Languages and translations"): pass `language=
  project.config.language` to `caption_cues`, `segment_cues`, `phrase_break_cost`,
  `beat_word_times`, `estimate_word_times` and `syllables(word, language)` to cut and time a
  text by its language's rules; `language_rules(tag)` gives them (`LanguageRules`: word lists,
  `abbreviations` whose period does not end a sentence, `words_per_second` range, `iso639_2`,
  `known`). `None` means the English rules.
- **Speakers** (docs/CONFIG.md "Multiple voices"): `project.voice_names()` (beat id → voice name,
  `None` for the base voice), `project.beat_voice(beat_id)` (its effective `VoiceConfig`),
  `project.speaker_tags(mode)` (beat id → label where the speaker changes; empty for `off`);
  `speaker_label(config, name)`, `speaker_color(config, name, theme)` (hex) and
  `speaker_prefix(label)` (`"Ana:"`) are what `captions` uses.
- `plate_contrast(color, plate, opacity)`: the contrast text keeps on a translucent plate over
  anything (the worse of the plate over black and over white).
