"""``stage``: a cartoon set (a picture, a generated picture or a colour / gradient) with a ground
line, named marks and the video's characters standing on them (DESIGN.md §69.6), parallax
layers that move by their factor when the camera moves (§69.7), props (§69.8), particles
(§69.9), its light and shadows (§69.31), its wind (§69.32) or a room instead of the sky (§69.42)."""

import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Annotated, Any, ClassVar, Literal

import numpy as np

from vidgen.api import *

from .image import check_image, is_vector, load_image

#: Ground band colour on a colour background when ``ground_color`` is not given.
DEFAULT_GROUND_COLOR = "surface"
#: Corners drawn per hill of a ``hills`` layer shape.
HILL_POINTS = 16

IDENTIFIER_PATTERN = r"^[A-Za-z0-9_]+$"
Identifier = Annotated[str, Field(pattern=IDENTIFIER_PATTERN)]


class StageCharacter(SceneParams):
    """A character of ``characters:`` on the stage. A plain string is the name."""

    also_accepts: ClassVar[tuple[type, ...]] = (str,)

    name: CharacterName
    """A character of the video's characters: list."""
    at: str | float = "centre"
    """Where it stands: a mark (far_left, left, centre, right, far_right, or the stage's own marks) or an x position from 0 (left edge) to 1 (right edge)."""
    depth: float = Field(0.0, ge=0.0, le=1.0)
    """0 = on the ground line at full size; up to 1 = at the back of the stage, higher up and 0.55 x the size; deeper characters are drawn behind."""
    scale: float = Field(1.0, gt=0.0, le=3.0)
    """Its size relative to the stage's size (e.g. 0.8 for a child)."""
    facing: Literal["auto", "right", "left", "front"] = "auto"
    """Which way it looks; auto: towards the middle of the stage (right on the left half, left on the right half); front: at the viewer (its front view; an SVG character keeps its side)."""
    pose: str | None = None
    """The pose it starts in (stand, pointing, waving, thinking, shrug, arms_crossed, sitting, or its own); none: at rest."""
    expression: str | None = None
    """The expression it starts with (neutral, happy, sad, angry, surprised, worried, thinking, or its own); none: at rest."""

    @model_validator(mode="before")
    @classmethod
    def _name_only(cls, data: Any) -> Any:
        return {"name": data} if isinstance(data, str) else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A plain string is also a character (JSON Schema ``anyOf`` name | object)."""
        return {"anyOf": [{"type": "string", "pattern": IDENTIFIER_PATTERN}, handler(core_schema)]}


class StageProp(SceneParams):
    """A prop on the stage: a built-in one (``prop``) or an SVG file (``svg``). A plain string is
    a built-in prop's name."""

    also_accepts: ClassVar[tuple[type, ...]] = (str,)

    prop: Literal[PROP_KINDS] | None = None  # type: ignore[valid-type]
    """A built-in prop: table, chair, tree, bush, house, door, lamp, sign, box, ball, cloud, sun, moon, rock, plant, laptop, cup, basket, umbrella, napkin; furniture: sofa, armchair, bed, bookshelf, counter, fridge, picture, rug, houseplant, clock, tv, desk."""
    svg: str | None = None
    """Instead of prop: an SVG file relative to the project folder (sanitised like any SVG), standing on the bottom edge of its viewBox."""
    name: Identifier | None = None
    """Its name for actions and the layout dump; default: the prop's name (an SVG: the file name), then _2, _3..."""
    at: str | float = "centre"
    """Where it stands: a mark or an x position from 0 (left edge) to 1 (right edge) of the stage."""
    depth: float = Field(0.0, ge=0.0, le=1.0)
    """0 = on the ground line at full size; up to 1 = at the back, higher up and smaller; at the same depth characters are drawn in front of props."""
    scale: float = Field(1.0, gt=0.0, le=5.0)
    """Its size relative to its usual size next to a character (a tree is 1.7 characters tall, a cup 0.09; an SVG 0.5)."""
    lift: float | None = Field(None, ge=0.0, le=1.0)
    """How far above the ground line it hangs, as a fraction of the frame height; default 0.5 for cloud, sun and moon, else 0 (on the ground)."""
    facing: Literal["right", "left"] = "right"
    """left: mirrored."""
    color: ThemeColor | None = None
    """Its main colour (a theme token or #hex); default per prop (a tree's leaves tertiary, a chair accent...)."""
    detail: ThemeColor | None = None
    """Its second colour (a tree's trunk, a house's roof, a laptop's screen...); default per prop."""
    recolor: Literal["none", "theme"] = "none"
    """With svg: theme maps the picture's colours to the nearest theme colours; none keeps them."""
    open: bool = False
    """An umbrella or a door: true starts it open (the open / close actions change it later)."""
    against: Literal["wall"] | None = None
    """wall: it stands with its back to the room's wall, at the wall's depth unless depth is given (a room only); a picture or a clock in a room hangs on the wall without it."""

    @model_validator(mode="before")
    @classmethod
    def _kind_only(cls, data: Any) -> Any:
        return {"prop": data} if isinstance(data, str) else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A built-in prop's name alone is also a prop (JSON Schema ``anyOf`` name | object)."""
        return {"anyOf": [{"enum": list(PROP_KINDS)}, handler(core_schema)]}

    @model_validator(mode="after")
    def _one_source(self) -> "StageProp":
        if (self.prop is None) == (self.svg is None):
            raise ValueError("a prop is either prop (a built-in prop) or svg (a file), one of the two")
        if self.svg is not None:
            if not self.svg.lower().endswith(".svg"):
                raise ValueError(f"svg: {self.svg!r} is not an .svg file")
            if self.color is not None or self.detail is not None:
                raise ValueError("color and detail are for built-in props; an SVG keeps its colours (or recolor: theme)")
        elif self.recolor != "none":
            raise ValueError("recolor is for svg props; a built-in prop takes color and detail")
        if self.open and "open" not in PROP_SHAPES.get(self.prop or "", ()):
            able = ", ".join(kind for kind, shapes in PROP_SHAPES.items() if "open" in shapes)
            raise ValueError(f"open is for props that open ({able}), not {self.prop or 'an svg prop'}")
        return self

    def default_name(self) -> str:
        """The prop's name (``tree``), or the SVG's file name made an identifier (``old_well``)."""
        return prop_default_name(self.prop, self.svg)

    def height_factor(self) -> float:
        """Its height relative to a character's: the prop's usual height times ``scale``."""
        usual = PROP_HEIGHTS[self.prop] if self.prop is not None else SVG_PROP_HEIGHT
        return usual * self.scale

    def resolved_lift(self) -> float:
        """``lift``, else the prop's default (:data:`PROP_LIFTS`, 0 for the others)."""
        if self.lift is not None:
            return self.lift
        return PROP_LIFTS.get(self.prop or "", 0.0)

    def resolved_hang(self) -> float:
        """How far up a wall it hangs, in a character's heights (:data:`PROP_HANGS`, else 0)."""
        return PROP_HANGS.get(self.prop or "", 0.0)

    def on_wall(self) -> bool:
        """Whether, in a room, it takes the wall's depth: ``against: wall``, or a prop that hangs
        on a wall, without a ``depth`` of its own."""
        wall = self.against == "wall" or (self.against is None and self.resolved_hang() > 0)
        return wall and "depth" not in self.model_fields_set

    def item(self, name: str) -> StageItem:
        """It as a stage item (:func:`~vidgen.cartoon.stage.stage_layout`)."""
        return StageItem(name, "prop", self.at, self.depth, self.height_factor(), self.resolved_lift(), self.resolved_hang())


class StageParticles(ParticleSettings, SceneParams):
    """Particles over the whole scene (rain, snow...). A plain string is the kind."""

    also_accepts: ClassVar[tuple[type, ...]] = (str,)

    kind: ParticleKindName
    """rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves or streaks (wind lines, seen only in wind)."""

    @model_validator(mode="before")
    @classmethod
    def _kind_only(cls, data: Any) -> Any:
        return {"kind": data} if isinstance(data, str) else data

    @model_validator(mode="after")
    def _puddles_in_rain(self) -> "StageParticles":
        if self.puddles and self.kind != "rain":
            raise ValueError(f"puddles grow under rain only, not {self.kind}")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A kind alone is also a particle setting (JSON Schema ``anyOf`` kind | object)."""
        return {"anyOf": [{"enum": list(PARTICLE_KINDS)}, handler(core_schema)]}


class LayerShape(SceneParams):
    """A filled shape of a layer, placed as the layer is seen with the camera at its start."""

    shape: Literal["rect", "ellipse", "triangle", "hills"]
    """rect, ellipse, triangle, or hills: a row of rounded hills across the whole layer (x is not used)."""
    x: float = Field(0.5, ge=0.0, le=1.0)
    """Its middle: an x from 0 (left edge) to 1 (right edge) of the stage."""
    y: float = Field(0.0, ge=0.0, le=1.0)
    """Its bottom, as a fraction of the frame height above the bottom edge (hills: their foot; they are filled down from there)."""
    width: float = Field(0.3, gt=0.0, le=4.0)
    """Its width as a fraction of the frame's shorter side (hills: the width of one hill)."""
    height: float = Field(0.2, gt=0.0, le=2.0)
    """Its height as a fraction of the frame's shorter side."""
    color: ThemeColor = "secondary"
    """Fill colour (a theme token or #hex)."""


class StageLayer(SceneParams):
    """A picture or shapes drawn behind the ground (background, middle) or in front of the
    characters (foreground), moving by its parallax factor when the camera moves."""

    name: Identifier | None = None
    """Its name in the layout dump; default <place>_layer (then _2, _3...)."""
    place: Literal["background", "middle", "foreground"] = "background"
    """background and middle are drawn behind the ground band (in that order), foreground in front of the characters."""
    factor: float | None = Field(None, ge=0.0, le=3.0)
    """How far it moves for a camera move of one unit: 1 = with the stage and its characters, 0 = fixed on screen; default background 0.3, middle 0.6, foreground 1.4."""
    image: str | None = None
    """A picture relative to the project folder (a PNG with transparency, or an SVG), as wide as the layer, standing on bottom."""
    bottom: float = Field(0.0, ge=0.0, le=1.0)
    """With image: the height of its bottom edge above the frame's bottom edge, as a fraction of the frame height."""
    shapes: list[LayerShape] = []
    """Instead of image: filled shapes, e.g. [{shape: hills, y: 0.2, height: 0.15, color: secondary}]."""

    @model_validator(mode="after")
    def _one_kind(self) -> "StageLayer":
        if (self.image is None) == (not self.shapes):
            raise ValueError("a layer has either image (a file) or shapes, one of the two")
        return self

    def resolved_factor(self) -> float:
        """``factor``, else the default of its place (:data:`DEFAULT_FACTORS`)."""
        return DEFAULT_FACTORS[self.place] if self.factor is None else self.factor


class RoomWindow(SceneParams):
    """A window on a room's wall. A plain string or number is where it is (``at``)."""

    also_accepts: ClassVar[tuple[type, ...]] = (str, float)

    at: str | float = "centre"
    """Its middle: a mark or an x position from 0 (left edge) to 1 (right edge) of the stage."""
    width: float = Field(WINDOW_WIDTH, gt=0.0, le=4.0)
    """Its width in the heights of a character standing at the wall."""
    height: float = Field(WINDOW_HEIGHT, gt=0.0, le=2.0)
    """Its height in the heights of a character standing at the wall."""
    sill: float = Field(WINDOW_SILL, ge=0.0, le=1.5)
    """How high its bottom is above the floor, in the heights of a character standing at the wall."""
    frame: ThemeColor = WINDOW_FRAME
    """Colour of its frame, bars and sill (a theme token or #hex)."""
    curtains: ThemeColor | bool = True
    """Curtains on both sides: true (accent), a colour, or false for none."""

    @model_validator(mode="before")
    @classmethod
    def _at_only(cls, data: Any) -> Any:
        return {"at": data} if isinstance(data, (str, int, float)) and not isinstance(data, bool) else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A mark or an x alone is also a window (JSON Schema ``anyOf`` mark | x | object)."""
        return {"anyOf": [{"type": "string"}, {"type": "number", "minimum": 0, "maximum": 1}, handler(core_schema)]}


class RoomDoor(SceneParams):
    """A door in a room's wall: a ``door`` prop standing at the wall, closed or open, whose name is
    also a mark (enter / exit through it). A plain string or number is where it is (``at``)."""

    also_accepts: ClassVar[tuple[type, ...]] = (str, float)

    name: Identifier | None = None
    """Its name for actions, the layout dump and its mark; default door (then door_2, ...)."""
    at: str | float = "right"
    """Where it is: a mark or an x position from 0 (left edge) to 1 (right edge) of the stage."""
    open: bool = False
    """true: it starts open (the open / close actions change it; a character entering or leaving through it opens it)."""
    facing: Literal["right", "left"] = "right"
    """Its hinges: right swings the open door to the left; left mirrors it."""
    scale: float = Field(DOOR_SCALE, gt=0.0, le=3.0)
    """Its height in the heights of a character standing at the wall."""
    color: ThemeColor | None = None
    """The door's colour (a theme token or #hex); default accent."""
    detail: ThemeColor | None = None
    """Its knob's colour; default highlight."""

    @model_validator(mode="before")
    @classmethod
    def _at_only(cls, data: Any) -> Any:
        return {"at": data} if isinstance(data, (str, int, float)) and not isinstance(data, bool) else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A mark or an x alone is also a door (JSON Schema ``anyOf`` mark | x | object)."""
        return {"anyOf": [{"type": "string"}, {"type": "number", "minimum": 0, "maximum": 1}, handler(core_schema)]}


class StageRoom(SceneParams):
    """An indoor set instead of the sky and the ground band: a back wall, a floor, a skirting
    board where they meet, an optional ceiling, windows and doors. ``true`` is a room with the
    defaults."""

    also_accepts: ClassVar[tuple[type, ...]] = (bool,)

    wall: ThemeColor = DEFAULT_WALL
    """The wall's colour (a theme token or #hex)."""
    wallpaper: Literal[WALLPAPERS] = "plain"  # type: ignore[valid-type]
    """The wall's pattern: plain, stripes or dots (a shade of the wall's colour)."""
    floor: ThemeColor = DEFAULT_FLOOR
    """The floor's colour (a theme token or #hex)."""
    flooring: Literal[FLOORINGS] = "boards"  # type: ignore[valid-type]
    """The floor's pattern: boards, tiles or plain."""
    skirting: ThemeColor | None = None
    """The skirting board's colour; default the floor's, darker."""
    ceiling: ThemeColor | bool = False
    """A ceiling band at the top: true (the wall's colour, lighter), a colour, or false for none."""
    depth: float | None = Field(None, ge=0.0, le=1.0)
    """How far back the wall stands (the depth of characters and props, 0..1): the floor ends there; default 0.4, or the depth of the deepest thing standing on the floor when that is further back."""
    windows: list[RoomWindow] = []
    """Windows on the wall: a mark or an x, or {at, width, height, sill, frame, curtains}; their sky follows the stage's light."""
    doors: list[RoomDoor] = []
    """Doors in the wall: a mark or an x, or {name, at, open, facing, scale, color, detail}; each is a door prop and a mark of its name."""

    @model_validator(mode="before")
    @classmethod
    def _plain(cls, data: Any) -> Any:
        return {} if data is True else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """``true`` is also a room (JSON Schema ``anyOf`` true | object)."""
        return {"anyOf": [{"const": True}, handler(core_schema)]}


@dataclass
class _Parallax:
    """A layer on screen: its mobject, factor and every member's points at the camera's home."""

    mobject: Mobject
    factor: float
    home: list[tuple[Mobject, np.ndarray]]


@scene("stage")
class Stage(NarratedScene):
    """A cartoon set: a background (``image`` file, ``generate:`` picture, or a theme colour or
    gradient), a ground line and the video's characters standing on named marks.

    Beat 1 fades the set and the characters in; later beats hold the picture while the characters
    breathe and blink (``idle: false`` keeps them still). Characters further back (``depth``) are
    smaller, higher up and drawn behind the ones in front. ``layers`` (pictures or shapes) move
    by their parallax factor when the camera moves (the ``zoom``, ``pan`` and ``follow``
    actions); ``width`` makes the stage wider than the frame, for the camera to pan across.
    ``props`` (a table, a tree, a house... or an SVG file) stand on marks like the characters and
    sort with them by depth.
    ``particles`` (rain, snow, confetti...) move over the whole scene. ``light`` (``morning``,
    ``sunset``, ``night``, ``indoor`` or a tint) grades the set and the characters, never the
    speech bubbles or text (the ``light`` action fades it); soft shadows lie under whatever
    stands on the ground (``shadows: false``: none). ``wind`` (0 calm .. 1 a gale; negative
    blows to the left) sways trees, bushes, plants, signs and lamps, makes scarves, long hair,
    floppy ears and hats trail and particles drift (the ``wind`` action fades it; ``leaves`` and
    ``streaks`` particles show it more); ``blow_away`` blows a light prop off the stage or to a
    mark, out of a hand too. ``room`` makes it an indoor set: a wall, a floor, windows showing
    the sky of the light, and doors (door props whose names are marks; ``enter`` and ``exit``
    through them); no wind or weather inside. Furniture (a sofa, a bed, a kitchen counter, a
    picture...) stands ``against: wall`` at the wall's depth; a picture and a clock hang on it.

    A beat is spoken by the characters whose voice says it (their mouths move with it), or by
    the ones its ``say`` action names; the acting actions (``say``, ``look_at``, ``turn``,
    ``emote``, ``pose``, ``react``) change the characters during the beats, and the moving ones
    (``walk_to``, ``run_to``, ``enter``, ``exit``, ``gesture``, ``jump``) move them; ``effect``
    puts a symbol over a head (an idea bulb, a sweat drop, a question mark...). A character with an
    ``enter`` action waits off stage until it enters. Walks, entrances, exits, jumps, a
    surprised face and most symbols make their own sounds (foley; ``foley: false`` turns them off);
    runs and jumps raise dust, fast moves leave speed lines (motion effects; ``motion_effects:
    false`` turns them off). With
    ``auto_direct``, listeners look at whoever speaks and react after lines on their own. A
    beat's ``shot:`` frames characters for that beat (``closeup kit``, ``two_shot``,
    ``over_shoulder kit pip``...): a cut, and back at the next beat without one. On a stage wider
    than the frame (a 9:16 variant crops the landscape stage) the camera keeps whoever speaks
    in view (``reframe``).

    The ``keyframes`` and ``move_along`` actions move a character, a prop or a character's part
    by keys or along a path. Characters handle props with ``pick_up``, ``hold``, ``put_down``,
    ``give`` and ``throw``: a held prop goes along with its holder's hand (they crouch for a low
    one). They sit on a chair, a rock, a box, a sofa, an armchair, a bed or at a desk with
    ``sit_on``, lean on a tree, a door, a sign or a counter with ``lean_on``, and get up with
    ``stand_up``.

    Action targets: each character and each prop by its name; each part of a character as
    ``<character>.<part>`` (``kit.arm_left``).
    """

    outro = 0.5
    target_patterns = ("<character>", "<prop>", "<character>.<part>")
    uses_cartoon_style = True
    #: Storyboard stills also show these actions half-way through (DESIGN.md §69.16).
    mid_still_actions = frozenset({
        "walk_to", "run_to", "enter", "exit", "gesture", "jump", "keyframes", "move_along", "pick_up", "put_down", "give", "throw",
        "sit_on", "lean_on", "stand_up", "blow_away",
    })

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """The names of the characters, then of the props, on the stage, then the characters'
        parts (``kit.arm_left``; only with an active project, which knows the parts)."""
        names = [c.name for c in params.characters]
        return names + params.prop_names() + part_target_names(names)

    class Params(SceneParams):
        image: str | None = None
        """Background picture relative to the project folder, e.g. assets/park.png (fills the frame, cropped)."""
        generate: GenerateImage | None = None
        """A generated background instead of a file: {prompt, negative, style, aspect, seed, format} or the prompt (the video's cartoon_style is added); made by `vidgen imagegen`, a placeholder until then."""
        background: ThemeColor | list[ThemeColor] | None = None
        """Without a picture: a colour, or a list of colours for a gradient from the top down; none: the theme's background."""
        ground: float = Field(0.2, ge=0.0, le=0.6)
        """Height of the ground line (where the characters' feet are) above the bottom edge, as a fraction of the frame height."""
        ground_color: ThemeColor | Literal[False] | None = None
        """Fill below the ground line, up to where the deepest character or prop on the ground stands; none: surface on a colour background, nothing on a picture; false: nothing."""
        marks: dict[Annotated[str, Field(pattern=r"^[A-Za-z0-9_]+$")], Annotated[float, Field(ge=0.0, le=1.0)]] = {}
        """Own marks: name -> x from 0 (left edge) to 1 (right edge), besides far_left 0.1, left 0.25, centre 0.5, right 0.75, far_right 0.9 (and a room's doors, each a mark of its name)."""
        characters: list[StageCharacter] = []
        """The characters on the stage: a name, or {name, at, depth, scale, facing, pose, expression}."""
        size: float = Field(0.45, gt=0.0, le=1.0)
        """Height of a character at depth 0, as a fraction of the frame's shorter side."""
        idle: bool = True
        """false: the characters do not breathe, sway or blink in this scene."""
        foley: bool | None = None
        """Sounds for the characters' actions (footsteps, whoosh on enter / exit, boing on jump, pop on a surprised face, a sound with most effect symbols): false for none in this scene; default: the video's foley (on)."""
        auto_direct: AutoDirectSetting | None = None
        """Automatic directing in this scene: listeners look at whoever speaks and react after lines, speakers gesture on stressed words, short punchy lines get a close-up (true, false or {looks, reactions, gestures, closeups, effects}); a beat's own setting wins; default: the video's (off). Actions written in a beat always win."""
        cartoon_motion: MotionSetting | None = None
        """Animation principles for the characters in this scene (anticipation, squash and stretch, overshoot and settle, follow-through): lively, calm or none; a character's own setting wins; default: the video's (lively)."""
        motion_effects: bool | None = None
        """Dust where a run sets off and stops and where a jump lands, speed lines behind runs, fast walks and thrown or blown props, impact stars on a hard landing, a whoosh arc on a big gesture, while a character's cartoon_motion is not none: false for none in this scene; default: the video's motion_effects (on)."""
        width: float = Field(1.0, ge=1.0, le=4.0)
        """Width of the stage in frame widths (marks and x positions are fractions of it; while it reframes in a frame narrower than 16:9, in 16:9 frame widths); wider than 1: the camera pans across it (pan, follow)."""
        camera_at: str | Annotated[float, Field(ge=0.0, le=1.0)] = "centre"
        """Where the camera looks at the start, on a stage wider than the frame: a mark or an x from 0 to 1 of the stage."""
        reframe: ReframeSetting | None = None
        """On a stage wider than the frame: speaker moves the camera to whoever speaks (easing between speakers, holding during short replies; a 9:16 frame then crops the stage laid out as wide as the 16:9 one); none: only the beats' own pan / follow / zoom / shot move it; default: the video's, else speaker when the characters do not fit in one view."""
        layers: list[StageLayer] = []
        """Parallax layers: {place: background | middle | foreground, factor, image | shapes}."""
        props: list[StageProp] = []
        """Props: a built-in prop's name, or {prop | svg, name, at, depth, scale, lift, facing, color, detail, recolor, open, against}."""
        particles: list[StageParticles] = []
        """Particles over the whole scene, in front of everything: a kind (rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves, streaks) or {kind, density, area, color, seed, puddles}; rain ends on the ground with splashes, not under an open umbrella or a tree, and plays a rain sound with foley; for one beat use the particles action."""
        light: LightSetting = "day"
        """The light on the set: day (as drawn), morning, sunset, night (dark blue, with stars on a colour background) or indoor, or {tint, strength}: a colour grade of the background, layers, props and characters (never of speech bubbles, captions or other text); the light action changes it during the scene."""
        shadows: bool = True
        """Soft shadows on the ground under the characters and the props standing on it (smaller when they jump, none under a held prop); false: none."""
        wind: WindSetting = 0.0
        """Wind from the start, in gusts: 0 calm (nothing moves) .. 1 a gale blowing to the right (negative: to the left), or calm, breeze (0.3), windy (0.6), gale (1); trees, bushes, plants, signs and lamps sway, scarves, long hair, floppy or pointy ears and hats trail (clearly from windy on), particles drift (add leaves or streaks to show it more); the wind action changes it during the scene, blow_away blows a light prop away."""
        room: StageRoom | None = None
        """An indoor set instead of the sky and the ground: true, or {wall, wallpaper (plain, stripes, dots), floor, flooring (boards, tiles, plain), skirting, ceiling, depth, windows, doors}; windows show the sky of the stage's light, doors are door props whose names are marks (enter / exit through them); no wind, rain, snow, leaves or streaks inside."""

        @model_validator(mode="after")
        def _check(self) -> SceneParams:
            if self.image is not None and self.generate is not None:
                raise ValueError("give either image (a file) or generate (a picture to generate), not both")
            if (self.image is not None or self.generate is not None) and self.background is not None:
                raise ValueError("background (a colour) is for stages without a picture; remove it or the image / generate")
            if isinstance(self.background, list) and len(self.background) < 2:
                raise ValueError("a background gradient needs at least two colours (or give one colour)")
            if self.room is not None:
                self._check_room_places()
            marks = self.stage_marks()
            seen: set[str] = set()
            for k, member in enumerate(self.characters):
                if member.name in seen:
                    raise ValueError(f"character '{member.name}' is on the stage twice (characters[{k}])")
                seen.add(member.name)
                try:
                    mark_x(member.at, marks)
                except ValueError as exc:
                    raise ValueError(f"characters[{k}].at: {exc}") from None
            try:
                mark_x(self.camera_at, marks)
            except ValueError as exc:
                raise ValueError(f"camera_at: {exc}") from None
            names = self.layer_names()
            for k, name in enumerate(names):
                if name in names[:k]:
                    raise ValueError(f"layer name '{name}' is used twice (layers[{k}])")
            prop_names = self.prop_names()
            for k, (prop, name) in enumerate(zip(self.props, prop_names)):
                if name in seen:
                    raise ValueError(f"props[{k}]: '{name}' is also a character on the stage; give the prop another name")
                if name in prop_names[:k]:
                    raise ValueError(f"prop name '{name}' is used twice (props[{k}])")
                try:
                    mark_x(prop.at, marks)
                except ValueError as exc:
                    raise ValueError(f"props[{k}].at: {exc}") from None
                if prop.against == "wall" and self.room is None:
                    raise ValueError(f"props[{k}]: against: wall needs a room (room: true) to stand against")
            if self.room is not None:
                self._check_room()
            return self

        def _check_room_places(self) -> None:
            """The room's windows and doors stand on the stage's own marks or at an x."""
            assert self.room is not None
            for kind, entries in (("windows", self.room.windows), ("doors", self.room.doors)):
                for k, entry in enumerate(entries):
                    try:
                        mark_x(entry.at, self.marks)
                    except ValueError as exc:
                        raise ValueError(f"room.{kind}[{k}].at: {exc}") from None

        def _check_room(self) -> None:
            """A room draws its own wall and floor, keeps the weather out, and stands behind
            everything on its floor; its doors' names are marks."""
            assert self.room is not None
            given = [key for key in ("image", "generate", "background", "ground_color") if getattr(self, key) is not None]
            if given:
                raise ValueError(f"a room draws its own wall and floor: remove {', '.join(given)} (or the room)")
            if wind_level(self.wind) != 0.0:
                raise ValueError("there is no wind in a room: remove wind (or the room)")
            for k, item in enumerate(self.particles):
                if item.kind in OUTDOOR_PARTICLES:
                    raise ValueError(f"particles[{k}]: {item.kind} stays outdoors; a room has none inside (sparkles, dust, confetti, smoke and bubbles work)")
            if self.room.depth is not None:
                for item in self._floor_items():
                    if item.lift == 0 and item.depth > self.room.depth:
                        raise ValueError(f"'{item.name}' stands at depth {item.depth}, behind the room's wall (room.depth {self.room.depth}): "
                                         "move it forward or the wall back")
            names = self.prop_names()
            characters = {c.name for c in self.characters}
            for k, name in enumerate(self.door_names()):
                if name in {**MARKS, **self.marks}:
                    raise ValueError(f"room.doors[{k}]: '{name}' is also a mark; a door's name is its mark, give the door another name")
                if name in characters or names.count(name) > 1:
                    raise ValueError(f"room.doors[{k}]: '{name}' is also the name of a character or another prop; give the door another name")

        def _floor_items(self) -> list[StageItem]:
            """The props (without the room's doors and the props that take the wall's depth) and
            the characters, as stage items."""
            names = numbered_names([(p.name, p.default_name()) for p in self.props])
            props = [prop.item(name) for prop, name in zip(self.props, names) if not prop.on_wall()]
            return props + [StageItem(c.name, "character", c.at, c.depth, c.scale) for c in self.characters]

        def wall_depth(self) -> float | None:
            """How far back the room's wall stands (``None``: no room; :func:`wall_depth`)."""
            return None if self.room is None else wall_depth(self._floor_items(), self.room.depth)

        def stage_props(self) -> list[StageProp]:
            """The props (in a room, those against its wall at its depth, DESIGN.md §69.43), then
            the room's doors as ``door`` props standing at its wall."""
            if self.room is None:
                return list(self.props)
            depth = self.wall_depth()
            return [*(p.model_copy(update={"depth": depth}) if p.on_wall() else p for p in self.props), *(
                StageProp(prop="door", name=door.name, at=door.at, depth=depth, scale=door.scale, facing=door.facing,
                          color=door.color, detail=door.detail, open=door.open)
                for door in self.room.doors
            )]

        def door_names(self) -> list[str]:
            """The names of the room's doors (none without a room)."""
            return self.prop_names()[len(self.props):]

        def stage_marks(self) -> dict[str, float]:
            """The stage's own marks, plus a mark at each of its room's doors (named after it)."""
            if self.room is None or not self.room.doors:
                return dict(self.marks)
            doors = {name: mark_x(door.at, self.marks) for name, door in zip(self.door_names(), self.room.doors)}
            return {**self.marks, **doors}

        def prop_names(self) -> list[str]:
            """Each prop's name (the room's doors last): its own, else its default name numbered
            from the second prop of that name on (``tree``, ``tree_2``)."""
            return numbered_names([(prop.name, prop.default_name()) for prop in self.stage_props()])

        def layer_names(self) -> list[str]:
            """Each layer's name: its own, else ``<place>_layer`` numbered from the second
            unnamed layer of a place on (``middle_layer``, ``middle_layer_2``)."""
            return numbered_names([(layer.name, f"{layer.place}_layer") for layer in self.layers])

        def has_picture(self) -> bool:
            """Whether the background is a picture (``image`` or ``generate``)."""
            return self.image is not None or self.generate is not None

        def items(self) -> list[StageItem]:
            """The props, then the characters, as stage items (for
            :func:`~vidgen.cartoon.stage.stage_layout`; at the same depth a character is drawn in
            front of a prop)."""
            props = [prop.item(name) for prop, name in zip(self.stage_props(), self.prop_names())]
            return props + [StageItem(c.name, "character", c.at, c.depth, c.scale) for c in self.characters]

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        problems = super().validate_project(params, project)
        if params.image is not None:
            problems += check_image(project, params.image, "image")
        for k, layer in enumerate(params.layers):
            if layer.image is not None:
                problems += check_image(project, layer.image, f"layers[{k}].image")
        for k, prop in enumerate(params.props):
            if prop.svg is not None:
                problems += check_image(project, prop.svg, f"props[{k}].svg")
        for k, member in enumerate(params.characters):
            for kind in ("pose", "expression"):
                name = getattr(member, kind)
                problem = None if name is None else pose_name_problem(project.config, member.name, kind, name)
                if problem is not None:
                    problems.append(f"characters[{k}].{kind}: {problem}")
        return problems

    @classmethod
    def auto_actions(cls, project: Any, spec: Any, params: Any) -> list[DirectedBeat]:
        """With ``auto_direct`` (beat, scene, video; nearest wins): listeners look at whoever
        speaks, the speaker at the one it talks to, listeners react after lines, speakers
        gesture on stressed words and short punchy lines get a close-up, each checked against
        the stage's geometry (:func:`stage_directions`, DESIGN.md §69.23, §69.24). When the stage
        reframes (:func:`stage_reframes`), pans keep the speaker in view (§69.30). Always: a
        speaker's face for the voice sounds of its line (§69.33)."""
        names = [c.name for c in params.characters]
        frame = stage_frame(project, params)
        return stage_directions(project, spec, names, params.auto_direct, frame, reframe=stage_reframes(project, params))

    @classmethod
    def action_sequence_problems(cls, spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """The prop actions replayed in order with the stage's geometry (DESIGN.md §69.27,
        §69.28, :func:`holding_problems`): a prop held by someone else, a full hand, nothing to put
        down, a prop or spot too far without a walk, giving to someone not next to the giver, a
        seat taken, a walk of a character that sits or leans. Needs the active project (the
        video's frame); none without one."""
        try:
            project = current_project()
        except VidgenError:
            return []
        if not any(u.config.action in HANDLING_ACTIONS | POSTURE_ACTIONS for u in uses):
            return []
        frame = stage_frame(project, params)
        names = [c.name for c in params.characters] + params.prop_names()
        beats = [b.id for b in spec.beats]

        def matched(use: Any) -> tuple[str, ...]:
            return tuple(n for n in names if any(fnmatchcase(n, p) for p in use.config.targets()))

        ordered = [u for _, u in sorted(enumerate(uses), key=lambda iu: (beats.index(iu[1].beat), iu[1].config.at, iu[0]))]
        steps = [HandlingStep(u.location, u.config.action, matched(u), u.config.options) for u in ordered]
        left = -frame.stage_width / 2
        problems = holding_problems(
            steps,
            characters={name: (place.x, place.height) for name, place in frame.places.items()},
            props=dict(frame.props),
            place_x=frame.place_x,
            to_fraction=lambda x: min(max((x - left) / frame.stage_width, 0.0), 1.0),
            entering=[n for u in uses if u.config.action == "enter" for n in matched(u)],
            seat_places=frame.seat_places,
            depths=frame.depths,
        )
        return problems + cls._calm_blow_problems(params, ordered)

    @staticmethod
    def _calm_blow_problems(params: Any, ordered: list[Any]) -> list[tuple[str, str]]:
        """A ``blow_away`` without ``to`` while the stage's wind is calm (its ``wind`` and the
        ``wind`` actions before it, DESIGN.md §69.32): nothing would blow the prop off stage."""
        level = wind_level(params.wind)
        problems: list[tuple[str, str]] = []
        for use in ordered:
            if use.config.action == "wind":
                level = use.action.level()
            elif use.config.action == "blow_away" and use.config.options.get("to") is None and level == 0.0:
                problems.append((f"{use.location}.target", "the wind is calm then, so nothing blows it off stage: add a wind action before it "
                                 "(- wind: windy) or the stage's wind:, or give to: a mark"))
        return problems

    @contextmanager
    def narrate(self, beat: Any) -> Iterator[float]:
        """Narrate a beat; the characters on the stage whose voice says it speak (lip sync from
        the beat's start to its end; on under the next beat while it overlaps this one, DESIGN.md
        §69.34), unless the beat has a ``say`` action, which picks who speaks (§69.11)."""
        b = self.beat(beat)
        voiced = [] if "say" in self.beat_action_names(b) else speaking_characters(self.project.config, beat_voice(self.spec, b), self.cast)
        said = [p for act in b.actions if act.action == "say" for p in act.targets()]
        #: who says the beat being narrated (a shot's default framing reads it, DESIGN.md §69.29)
        self.beat_speakers = voiced or [n for n in self.cast if any(fnmatchcase(n, p) for p in said)]
        speakers: list[tuple[Character, Any]] = []
        with super().narrate(b) as d:
            for name in voiced:
                self.speak(self.cast[name])
                speakers.append((self.cast[name], self.cast[name].lip_sync_track))
            yield d
        for figure, track in speakers:
            self.end_lip_sync(figure, track)

    def action_foley(self, action: str, options: Any, animations: Any, start: float, seconds: float) -> None:
        """The sounds of a character's action as it plays (DESIGN.md §69.19): footsteps on
        walks, a whoosh on enter / exit, a boing on jump, a thud where a thrown prop lands, a pop
        on a surprised face, a sound for an effect symbol (unless its ``sound: false``)
        (:func:`foley_cues`); none with ``foley: false`` (the stage's, else the video's). A
        project file with a sound's name plays as it is (without the cue's params)."""
        if not self._foley_on():
            return
        for anim in animations:
            for cue in foley_cues(_played(action, options, anim, start, seconds)):
                params = {} if self.sounds.file(cue.sound) is not None else cue.params
                self.sfx(cue.sound, max(cue.time, 0.0), gain=cue.gain, align=cue.align, **params)

    def _foley_on(self) -> bool:
        """Whether this stage plays its sounds: its ``foley``, else the video's."""
        return self.params.foley if self.params.foley is not None else self.project.config.foley

    # ----- motion effects (DESIGN.md §69.41) ------------------------------------------------------

    def action_motion_effects(self, action: str, options: Any, animations: Any, start: float, seconds: float) -> None:
        """The motion effects of a character's action as it plays (:func:`motion_effect_cues`):
        dust, speed lines and impact stars of walks, runs and jumps, speed lines behind a thrown
        or blown prop, a whoosh arc on a ``big`` gesture; none with ``motion_effects: false``
        (the stage's, else the video's) or for a character whose ``cartoon_motion`` is none.
        Each is a :class:`MotionEffect` of its own, drawn right in front of its mover (speed
        lines right behind it), not graded by the light, and taken off the scene when its cue is
        over."""
        on = self.params.motion_effects if self.params.motion_effects is not None else self.project.config.motion_effects
        if not on:
            return
        movers = {id(m): name for name, m in [*self.cast.items(), *self.props.items()]}
        figure = next((a.mobject for a in animations if isinstance(a.mobject, Character)), None)
        for anim in animations:
            mover = anim.mobject
            strength = getattr(anim, "strength", None)
            if strength is None:   # a prop's move: its thrower's cartoon_motion, else the scene's
                setting = figure.motion if figure is not None else resolve_motion(self.params.cartoon_motion, self.project.config.cartoon_motion)
                strength = motion_strength(setting)
            name = movers.get(id(mover))
            for cue in motion_effect_cues(_played(action, options, anim, start, seconds), strength):
                effect = MotionEffect(
                    cue, mover, delay=cue.time - start, seed=motion_seed(self.spec.id, name, cue.kind, round(cue.time, 3), cue.arm),
                    scale=effect_scale(strength), star_color=self.theme.color("highlight"), effect_of=name,
                )
                self._add_motion_effect(effect, mover, behind=cue.kind == "speed_lines")

    def _add_motion_effect(self, effect: MotionEffect, mover: Mobject, *, behind: bool) -> None:
        """Put ``effect`` right in front of ``mover`` and the props it holds (``behind``: right
        behind it) in the scene (on top when the mover is not in it; a held prop stays right after
        its holder, §69.27), and start the sweep that takes it off when it is done."""
        effect.set_z_index(mover.z_index)
        k = next((i for i, m in enumerate(self.mobjects) if m is mover), None)
        if k is None:
            self.add(effect)
        elif behind:
            self.mobjects.insert(k, effect)
        else:
            held = getattr(mover, "name", None)
            while held is not None and k + 1 < len(self.mobjects) and getattr(self.mobjects[k + 1], "held_by", None) == held:
                k += 1
            self.mobjects.insert(k + 1, effect)
        self.motion_effects.append(effect)
        if not any(f is self._motion_sweep for f in self.updaters):
            self.add_updater(self._motion_sweep)

    def _sweep_motion_effects(self, dt: float) -> None:
        """Scene updater while motion effects are on: takes the ones whose cue is over off the
        scene, and itself once none is left (an updater makes Manim redraw every frame)."""
        done = [e for e in self.motion_effects if e.done]
        if done:
            self.remove(*done)
            self.motion_effects = [e for e in self.motion_effects if not e.done]
        if not self.motion_effects:
            self.remove_updater(self._motion_sweep)

    # ----- walking in depth, the front view (DESIGN.md §69.44) -------------------------------------

    def feet_y_at(self, depth: float) -> float:
        """The y (Manim units) of the ground line at ``depth``: where feet stand there."""
        return feet_point(0.5, depth, self.params.ground, self.frame_width, self.frame_height)[1]

    def walk_in_depth(self, character: Character, walk: Walk) -> None:
        """``character`` walks in depth with ``walk``: its place in the draw order follows its
        depth on every frame (:meth:`_keep_depth_order`), and the ground line under it is its
        new depth's once it stops (the ``keyframes`` y 0)."""
        self.grounds[character.name] = self.feet_y_at(walk.to_depth)
        self._depth_walks.append((character, walk))
        self._watch_draw_order()

    def _start_depth_order(self) -> None:
        """Watch the draw order from the start when a walk in depth or a turn to the front may
        change it (a character facing front, or a turn to it, :meth:`_watch_draw_order`)."""
        #: the walks in depth under way: (character, walk)
        self._depth_walks: list[tuple[Character, Walk]] = []
        #: each character's :attr:`Character.order_changes` when last looked at
        self._part_orders = {name: c.order_changes for name, c in self.cast.items()}
        #: the scene updater keeping the draw order, kept: Manim removes an updater by identity
        self._order_updater = self._draw_order_step
        fronts = any(c.facing == "front" for c in self.params.characters) or any(u.options.to == "front" for u in self.action_uses("turn"))
        if fronts:
            self._watch_draw_order()

    def _watch_draw_order(self) -> None:
        if not any(f is self._order_updater for f in self.updaters):
            self.add_updater(self._order_updater)

    def _draw_order_step(self, dt: float) -> None:
        """Scene updater: each walker in depth goes behind or in front of the others as its depth
        passes theirs, and what Manim draws during the animation playing now follows a changed
        order (a walker's, or a character's parts' after a turn between its side and its front)."""
        changed = False
        for character, walk in self._depth_walks:
            changed |= self._keep_depth_order(character)
        self._depth_walks = [(c, w) for c, w in self._depth_walks if abs(c.stage_depth - w.to_depth) > SAME_DEPTH]
        for name, figure in self.cast.items():
            if self._part_orders.get(name) != figure.order_changes:
                self._part_orders[name] = figure.order_changes
                changed = True
        if changed and getattr(self, "animations", None):
            # Manim lists what it draws when an animation begins; keep that list in the new order
            self.moving_mobjects = self.get_moving_and_static_mobjects(self.animations)[0]

    def _keep_depth_order(self, walker: Character) -> bool:
        """Move ``walker`` (with the props it holds) to its place among the characters and props
        for its depth now (:func:`depth_slot`), the moving shadows before the first thing whose
        shadow they draw; whether it moved."""
        things = {id(m) for m in [*self.cast.values(), *self.props.values()] if getattr(m, "held_by", None) is None}
        block_at = next((k for k, m in enumerate(self.mobjects) if m is walker), None)
        if block_at is None:
            return False
        end = block_at + 1
        while end < len(self.mobjects) and getattr(self.mobjects[end], "held_by", None) == walker.name:
            end += 1
        block = self.mobjects[block_at:end]
        rest = self.mobjects[:block_at] + self.mobjects[end:]
        others = [m for m in rest if id(m) in things]
        current = sum(1 for m in self.mobjects[:block_at] if id(m) in things)
        slot = depth_slot(walker.stage_depth, [(float(getattr(m, "stage_depth", 0.0)), isinstance(m, Character)) for m in others], current)
        if slot == current:
            return False
        at = rest.index(others[slot]) if slot < len(others) else len(rest)
        self.mobjects[:] = rest[:at] + block + rest[at:]
        self._shadows_first()
        return True

    def _shadows_first(self) -> None:
        """Keep the shadows of the things that move drawn before all of them (they lie on the
        ground under everyone)."""
        moving = getattr(self, "_moving_shadows", None)
        if moving is None or moving not in self.mobjects:
            return
        casters = {id(c.mobject) for c in moving.casters}
        first = next((k for k, m in enumerate(self.mobjects) if id(m) in casters), None)
        if first is not None and self.mobjects.index(moving) > first:
            self.mobjects.remove(moving)
            self.mobjects.insert(first, moving)

    def _depth_crossers(self, animations: tuple[Animation, ...]) -> set[int]:
        """The ids of the family members of the walkers in depth among ``animations`` and of
        every character and prop whose depth they pass (Manim must redraw all of them on every
        frame, since their order changes)."""
        found: set[int] = set()
        things = [*self.cast.values(), *self.props.values()]
        for anim in animations:
            if not isinstance(anim, Walk) or anim.to_depth is None:
                continue
            low, high = sorted((float(anim.mobject.stage_depth), anim.to_depth))
            for thing in [anim.mobject, *(t for t in things if low - SAME_DEPTH <= float(getattr(t, "stage_depth", 0.0)) <= high + SAME_DEPTH)]:
                found |= {id(m) for m in thing.get_family()}
        return found

    # ----- rain on the ground (DESIGN.md §69.39) --------------------------------------------------

    def rain_ground(self) -> RainGround:
        """Where rain ends now: the landing band from the ground line up to the top of the ground
        area, and the shelters (open umbrellas, held or standing, and trees) where they are."""
        shelters: list[ShelterBox] = []
        for prop in self.props.values():
            if prop.kind not in SHELTER_PROPS:
                continue
            holder = self.cast.get(prop.held_by) if prop.held_by is not None else None
            feet = float((holder.feet() if holder is not None else prop.feet())[1])
            box = (float(prop.get_left()[0]), float(prop.get_right()[0]), float(prop.get_top()[1]))
            shelter = prop_shelter(prop.kind, prop.shape, box, feet)
            if shelter is not None:
                shelters.append(shelter)
        top = ground_top(self.params.ground, self.params.items())
        return rain_ground(self.params.ground, top, self.frame_height, shelters)

    def particles_started(self, field: Any, settings: Any) -> None:
        """A rain field: its sound bed plays while it lasts (with foley), and, with ``puddles:
        true``, puddles grow on the ground under it (drawn over the ground band, under the
        shadows, characters and props)."""
        if field.seeds.kind != "rain":
            return
        if self._foley_on():
            self._rain_fields.append(field)
        if not settings.puddles:
            return
        left, right = self.camera_bounds()[:2]
        spots = puddle_spots(
            puddle_count(self.stage_width / self.frame_width), settings.seed, left, right, self.rain_ground(),
            min(self.frame_width, self.frame_height),
        )
        puddles = Puddles(spots, start=field.start, ended=lambda: field.ended, clock=lambda: float(self.renderer.time))
        mark_lit(puddles)
        self.puddles.append(puddles)
        self._lay_on_ground(puddles)

    def _lay_on_ground(self, mobject: Mobject) -> None:
        """Put ``mobject`` right in front of the set behind the characters (before the shadows):
        into the backdrop while it has not come on screen yet (it fades in with it), else into
        the scene."""
        behind = [m for m in self._backdrop if not isinstance(m, StageShadows)]
        ids = {id(m) for m in behind}
        shown = [k for k, m in enumerate(self.mobjects) if id(m) in ids]
        if shown:
            self.mobjects.insert(max(shown) + 1, mobject)
        elif any(m in self.mobjects for m in [*self.cast.values(), *self.props.values()]):
            self.mobjects.insert(0, mobject)
        else:
            self._backdrop.insert(len(behind), mobject)

    def timings(self) -> dict[str, Any]:
        """The scene's timings, plus ``ambience``: the rain sound bed from each rain field's start
        to its end (the scene's end while it lasts), scene seconds (DESIGN.md §69.39)."""
        data = super().timings()
        end = float(self.renderer.time)
        spans = [(f.start, end if f.ended is None else min(f.ended, end)) for f in getattr(self, "_rain_fields", [])]
        beds = [{"bed": "rain", "start": round(a, 6), "end": round(b, 6)} for a, b in spans if b > a]
        if beds:
            data["ambience"] = beds
        return data

    def shot_framing(self, kind: str, names: list[str]) -> tuple[ShotView, Shot]:
        """The camera view of a ``kind`` shot of the characters ``names`` (filled in by
        :func:`shot_figures`) where the characters on the stage stand now (DESIGN.md §69.29)."""
        left, right = self.camera_bounds()[:2]
        present: dict[str, ShotFigure] = {}
        for name, figure in self.cast.items():
            x = float(figure.feet()[0])
            if not left <= x <= right:
                continue  # waiting to enter, or gone
            tops = [figure.parts[part].get_top()[1] for part in ("head", "accessory") if figure.has_part(part)]   # a hat too
            top = max(tops) if tops else figure.get_top()[1]
            present[name] = ShotFigure(name, x, float(figure.feet()[1]), figure.standing_height, figure.facing, float(top))
        looked = {name: figure.looked_at for name, figure in self.cast.items()}
        shot = shot_figures(kind, names, present, speakers=getattr(self, "beat_speakers", []), looked_at=looked)
        view = shot_view(shot, present, frame_width=self.frame_width, frame_height=self.frame_height, bounds=self.camera_bounds())
        return view, shot

    @classmethod
    def camera_place(cls, params: Any, place: str | float) -> float:
        """A mark of the stage (its own and its room's doors too) or an x from 0 to 1."""
        return mark_x(place, params.stage_marks())

    def camera_bounds(self) -> tuple[float, float, float, float]:
        """The stage: ``width`` frames wide, the frame's height."""
        half = self.stage_width / 2
        return (-half, half, -self.frame_height / 2, self.frame_height / 2)

    @property
    def stage_width(self) -> float:
        """The stage's width in Manim units: ``width`` frames, or, when reframing in a frame
        narrower than a landscape one, ``width`` 16:9 frames (DESIGN.md §69.30)."""
        if not hasattr(self, "_reframes"):
            self._reframes = stage_reframes(self.project, self.params)
        return self.params.width * stage_base_width(self.frame_width, self.frame_height, self._reframes)

    def construct(self) -> None:
        p = self.params
        frame = self.camera.frame
        start_x = (mark_x(p.camera_at, p.stage_marks()) - 0.5) * self.stage_width
        frame.move_to([*view_center_within(self.camera_bounds(), (start_x, 0.0), frame.width, frame.height), 0.0])
        self._start_light()
        layers = self._layers()
        #: the layers by name, in the order given (DESIGN.md §69.7)
        self.layers: dict[str, Mobject] = dict(zip(p.layer_names(), layers))
        behind = [m for layer, m in zip(p.layers, layers) if layer.place != "foreground"]
        in_front = [m for layer, m in zip(p.layers, layers) if layer.place == "foreground"]
        placements = stage_layout(
            p.items(),
            marks=p.stage_marks(),
            ground=p.ground,
            size=p.size,
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            stage_width=self.stage_width,
        )
        heads = [place.feet[1] + place.height for place in placements if place.kind == "character"]
        backdrop = self._backdrop(behind, max(heads, default=None))
        members = {m.name: m for m in p.characters}
        props = dict(zip(p.prop_names(), p.stage_props()))
        # the characters and the props on the stage by name, back to front (DESIGN.md §69.6, §69.8)
        self.cast: dict[str, Character] = {}
        self.props: dict[str, Prop] = {}
        #: who holds which prop (the prop actions, DESIGN.md §69.27)
        self.holdings = Holdings()
        #: each character's mark (its ``at``) as an x in Manim units, where ``enter`` walks it to
        self.homes: dict[str, float] = {}
        #: the y of the ground line at each character's and prop's depth (``keyframes`` y 0, §69.14)
        self.grounds: dict[str, float] = {}
        entering = self._entering()
        left, right = self.camera_bounds()[:2]
        on_stage: list[tuple[str, Mobject]] = []
        for place_at in placements:
            self.grounds[place_at.name] = feet_point(
                place_at.x_fraction, place_at.depth, p.ground, self.frame_width, self.frame_height,
            )[1]
            if place_at.kind == "prop":
                item = self._prop(place_at.name, props[place_at.name], place_at.height)
                item.height_factor = props[place_at.name].height_factor()
                item.shift(np.array([*place_at.feet, 0.0]) - item.feet())
                item.stage_depth = place_at.depth   # its place in the draw order (walks in depth, §69.44)
                self.props[place_at.name] = item
                on_stage.append((place_at.name, item))
                continue
            member = members[place_at.name]
            facing = facing_towards_centre(place_at.x_fraction) if member.facing in ("auto", "front") else member.facing
            figure = character(member.name, height=place_at.height, facing=facing, motion=p.cartoon_motion)
            if member.facing == "front":
                figure.face("front")   # an SVG character keeps its side, towards the middle (§69.44)
            figure.stage_depth, figure.ground_y = place_at.depth, self.grounds[place_at.name]
            if member.pose is not None:
                figure.set_pose(member.pose)
            if member.expression is not None:
                figure.set_expression(member.expression)
            if not p.idle:
                figure.stop_idle()
            figure.shift(np.array([*place_at.feet, 0.0]) - figure.feet())
            self.homes[member.name] = place_at.feet[0]
            if member.name in entering:  # waits beyond the stage's edge until its enter (§69.12)
                side = entering[member.name] or nearer_side(place_at.feet[0], left, right)
                figure.shift([offstage_x(side, left, right, figure.width / 2) - place_at.feet[0], 0.0, 0.0])
            self.cast[member.name] = figure
            on_stage.append((member.name, figure))
        for prop_name, holder in self._held_before_entering(entering).items():   # waits off stage with its holder
            item, figure = self.props[prop_name], self.cast[holder]
            item.shift([float(figure.feet()[0] - item.feet()[0]), 0.0, 0.0])
        # the light grades the set, not the stars, shadows, bubbles or text (DESIGN.md §69.31)
        mark_lit(*[m for m in backdrop if not isinstance(m, (StarField, WindowViews))], *in_front, *(mob for _, mob in on_stage))
        still, moving = self._shadows(placements)
        backdrop += [still] if still is not None else []
        # register back to front, so the fade-ins add them (and draw them) in that order
        targets = [self.target(name, mob) for name, mob in on_stage]
        for whole in targets:  # parts come on screen with their character (§69.14)
            if isinstance(whole.mobject, Character):
                for part in whole.mobject.parts:
                    self.target(f"{whole.name}.{part}", whole.mobject.parts[part], entrance=lambda t=whole: self.entrance(t))
        cast_by = {id(c.mobject) for c in (moving.casters if moving is not None else [])}
        first_moving = next((k for k, t in enumerate(targets) if id(t.mobject) in cast_by), None)

        def entrance() -> list:
            items: list = []
            for k, t in enumerate(targets):  # moving things' shadows: drawn just before the first of them
                items += [FadeIn(moving)] if k == first_moving else []
                items += self.entrance(t)
            return [FadeIn(part) for part in backdrop] + items + [FadeIn(m) for m in in_front]

        self._start_wind(placements)
        self._start_depth_order()
        #: the set behind the characters (puddles go in it, DESIGN.md §69.39)
        self._backdrop = backdrop
        #: the rain fields whose sound bed plays (foley on)
        self._rain_fields: list[ParticleField] = []
        #: the puddles under the rain fields with ``puddles: true``
        self.puddles: list[Puddles] = []
        #: the motion effects on the scene now (DESIGN.md §69.41), and the scene updater that
        #: takes finished ones off, kept: Manim removes an updater by identity
        self.motion_effects: list[MotionEffect] = []
        self._motion_sweep = self._sweep_motion_effects
        #: the particle fields over the stage, in the order given (DESIGN.md §69.9)
        self.particles: list[ParticleField] = [particle_field(self, item.kind, item) for item in p.particles]
        self.add(*self.particles)
        if self.light is not None:
            self.light.on_change(self._show_light)
        self.reveal([entrance], fraction=0.6, cap=1.0)
        self.finish()

    # ----- light and shadows (DESIGN.md §69.31) ---------------------------------------------------

    def _start_light(self) -> None:
        """The light at the start (``light``) and, when it grades anything or a ``light`` action
        changes it, the :class:`StageLight` that grades the set as the camera draws it."""
        #: the light from the start, and whether any light of the scene has stars
        self.base_light = resolve_light(self.params.light, self.theme)
        changes = [resolve_light(use.setting(), self.theme) for use in self.action_uses("light")]
        self._starry = max([self.base_light.stars, *(g.stars for g in changes)]) > 0
        #: the stage's light (``None``: the set as drawn, nothing changes it)
        self.light: StageLight | None = StageLight(self.renderer.camera, self.base_light) if self.base_light.changes_colors or changes else None
        self.stars: StarField | None = None
        self.window_views: WindowViews | None = None
        self.shadows: list[StageShadows] = []
        #: the scene updater while the light changes, kept: Manim removes an updater by identity,
        #: and each ``self._light_step`` is a new bound method
        self._light_updater = self._light_step

    def change_light(self, setting: str | CustomLight, start: float, seconds: float) -> None:
        """Fade the light to ``setting`` (a preset or a tint) from scene time ``start`` over
        ``seconds`` (the ``light`` action); everything is redrawn on every frame meanwhile."""
        if self.window_views is not None:   # the sky outside fades with it (§69.42)
            self._sky_changes.append(SkyChange(float(start), max(float(seconds), 0.0), window_sky(self._light_key(setting))))
        if self.light is None:
            self.light = StageLight(self.renderer.camera, self.base_light)
            self.light.on_change(self._show_light)
        self.light.change(resolve_light(setting, self.theme), start, seconds)
        if not any(f is self._light_updater for f in self.updaters):
            self.add_updater(self._light_updater)

    def _light_step(self, dt: float) -> None:
        """Scene updater while the light changes: the grade for the scene time now; it removes
        itself once every change is over (a scene updater makes Manim redraw every frame)."""
        now = float(self.renderer.time)
        if self.light is not None:
            self.light.update(now)
        if self.light is None or self.light.settled(now):
            self.remove_updater(self._light_updater)

    def _show_light(self, grade: LightGrade) -> None:
        """The stars' brightness and the shadows' darkness for ``grade``, and the sky outside a
        room's windows for the light now."""
        if self.stars is not None:
            self.stars.set_level(grade.stars)
        if self.window_views is not None:
            self.window_views.show(sky_at(self._sky_base, self._sky_changes, float(self.renderer.time)))
        for group in self.shadows:
            group.set_strength(grade.shadow)

    def get_moving_mobjects(self, *animations: Animation) -> list[Mobject]:
        """Manim's moving mobjects, or every mobject while the light changes during this
        animation (the grade then changes on every frame, so nothing can stay in the static
        image), or, while the wind may move something, everything from the first swaying prop or
        trailing character on (DESIGN.md §69.32; the set behind it stays in the static image), and,
        while a character walks in depth, everything from the first thing whose depth it passes
        on (its place in the draw order changes, §69.44)."""
        moving = super().get_moving_mobjects(*animations)
        now = float(self.renderer.time)
        duration = getattr(self, "duration", None)
        end = now + (math.inf if duration is None else float(duration))
        light = getattr(self, "light", None)
        if light is not None:
            light.update(now)
            if light.changing(now, end):
                return [*self.mobjects, *(m for m in moving if m not in self.mobjects)]
        redrawn = self._depth_crossers(animations) if hasattr(self, "_depth_walks") else set()
        blowing = getattr(self, "blowing", None)
        if blowing is not None:
            blowing.update(now)
            if blowing.moving(now, end):
                redrawn |= {id(m) for mob in blowing.mobjects() for m in mob.get_family()}
            elif not blowing.moving(now, math.inf):
                self.remove_updater(self._wind_updater)
        if not redrawn:
            return moving
        family = self.get_mobject_family_members()
        first = next((k for k, m in enumerate(family) if id(m) in redrawn), len(family))
        return list_update(family[first:], moving)

    # ----- wind (DESIGN.md §69.32) ----------------------------------------------------------------

    def _start_wind(self, placements: list[StagePlacement]) -> None:
        """The wind from the start (``wind``) and, when it or a ``wind`` action blows, the
        :class:`StageWind` that sways the props and turns the characters' trailing pieces, with
        a scene updater; nothing at all on a calm stage (it renders as without wind)."""
        base = wind_level(self.params.wind)
        later = [use.level() for use in self.action_uses("wind")]
        #: the stage's wind and what it moves (``None``: calm all along, nothing installed)
        self.blowing: StageWind | None = None
        #: the particles' drift (``vidgen.particle_field``; ``None``: none)
        self.particle_wind: ParticleWind | None = None
        if base == 0.0 and not any(later):
            return
        wind = Wind(base, seed=wind_seed(self.spec.id))
        lifts = {item.name: item.lift for item in self.params.items()}
        still = set(self.props) - self._movable_props() - self._posture_props()
        swaying = [
            SwayingProp(self.props[place.name], self.props[place.name].kind, place.x_fraction)
            for place in placements
            if place.kind == "prop" and place.name in still and lifts[place.name] == 0 and self.props[place.name].kind in SWAYS
        ]
        left = -self.stage_width / 2
        self.blowing = StageWind(wind, swaying, self.cast, lambda x: (x - left) / self.stage_width)
        self.particle_wind = self.blowing.particle_push
        self.blowing.update(float(self.renderer.time))
        #: the scene updater, kept: Manim removes an updater by identity, and each
        #: ``self._wind_step`` is a new bound method
        self._wind_updater = self._wind_step
        self.add_updater(self._wind_updater)

    def _posture_props(self) -> set[str]:
        """The props a ``sit_on`` or ``lean_on`` names (they do not sway under a character)."""
        return {use.options.to for kind in ("sit_on", "lean_on") for use in self.action_uses(kind)}

    def change_wind(self, level: float, start: float, seconds: float) -> None:
        """Fade the wind to the signed ``level`` from scene time ``start`` over ``seconds`` (the
        ``wind`` action)."""
        if self.blowing is None:
            return  # every level of the scene is 0: nothing to move
        self.blowing.wind.change(level, start, seconds)
        if not any(f is self._wind_updater for f in self.updaters):
            self.add_updater(self._wind_updater)

    def _wind_step(self, dt: float) -> None:
        """Scene updater while the wind may move something: props and trailing pieces for now;
        it removes itself once nothing can move any more (a scene updater makes Manim redraw
        every frame), also inside a wait."""
        now = float(self.renderer.time)
        if self.blowing is not None:
            self.blowing.update(now)
        if self.blowing is None or not self.blowing.moving(now, math.inf):
            self.remove_updater(self._wind_updater)

    def _shadows(self, placements: list[StagePlacement]) -> tuple[StageShadows | None, StageShadows | None]:
        """The shadows (``shadows: true``): of the props on the ground that stay put (drawn
        with the backdrop, so they stay in Manim's static image), and of the characters and the
        props an action may move (placed under them on every frame)."""
        if not self.params.shadows:
            return None, None
        lifts = {item.name: item.lift + item.hang for item in self.params.items()}
        movable = self._movable_props()
        doors = set(self.params.door_names())
        still: list[ShadowCaster] = []
        moving: list[ShadowCaster] = []
        for place_at in placements:
            name = place_at.name
            if place_at.kind == "prop":
                if lifts[name] > 0 or name in doors or self.props[name].kind in FLAT_PROPS:
                    continue  # hangs in the sky or on a wall, is part of the room's wall, or lies flat
                prop = self.props[name]
                widths = {shape: prop.shape_width(shape) * PROP_SHADOW_WIDTH for shape in prop.shapes}
                caster = ShadowCaster(prop, self.grounds[name], prop.width * PROP_SHADOW_WIDTH, prop.height, widths)
                (moving if name in movable else still).append(caster)
            else:
                figure = self.cast[name]
                moving.append(ShadowCaster(figure, self.grounds[name], SHADOW_WIDTH * figure.standing_height, figure.standing_height, grows=True))
        strength = self.base_light.shadow
        groups = [StageShadows(casters, strength) if casters else None for casters in (still, moving)]
        if groups[1] is not None:
            groups[1].add_updater(lambda m: m.follow())
        self.shadows = [g for g in groups if g is not None]
        #: the shadows of the things that may move (kept drawn before them, §69.44)
        self._moving_shadows = groups[1]
        return groups[0], groups[1]

    def _movable_props(self) -> set[str]:
        """The props an action may move or reshape: picked up or held (then put down, given or
        thrown), moved by ``keyframes`` / ``move_along``, opened or closed, blown away."""
        moved = {use.options.to for kind in ("pick_up", "hold") for use in self.action_uses(kind)}
        for kind in ("keyframes", "move_along", "open", "close", "blow_away"):
            for use in self.action_uses(kind):
                moved |= {name for name in self.props for pattern in use.config.targets() if fnmatchcase(name, pattern)}
        return moved & set(self.props)

    def _entering(self) -> dict[str, str | None]:
        """The characters an ``enter`` action brings in, with the side of the first one naming
        each (``None``: the edge nearer its mark)."""
        names = [c.name for c in self.params.characters]
        entering: dict[str, str | None] = {}
        for use in self.action_uses("enter"):
            for pattern in use.config.targets():
                for name in names:
                    if fnmatchcase(name, pattern):
                        entering.setdefault(name, use.options.side)
        return entering

    def _held_before_entering(self, entering: dict[str, str | None]) -> dict[str, str]:
        """The props a ``hold`` gives to a character of ``entering`` before its first ``enter``
        (prop name -> holder): they wait off stage with it instead of flying there in view."""
        held: dict[str, str] = {}
        entered: set[str] = set()
        for use in self._actions.uses if self._actions is not None else []:
            if use.kind.name not in ("hold", "enter"):
                continue
            names = [name for name in entering if any(fnmatchcase(name, p) for p in use.config.targets())]
            if use.kind.name == "enter":
                entered.update(names)
            elif names and names[0] not in entered and use.action.options.to in self.props:
                held.setdefault(use.action.options.to, names[0])
        return held

    def _prop(self, name: str, prop: StageProp, height: float) -> Prop:
        """The prop ``name`` drawn ``height`` units tall, its feet at the origin; outlines as wide
        as a character's at its depth."""
        if prop.svg is not None:
            problems = check_image(self.project, prop.svg, "svg")
            if problems:
                raise VidgenError(f"scene '{self.spec.id}': prop '{name}': {problems[0]}")
            return svg_prop(
                self.project.asset(prop.svg), height=height, name=name, theme=self.theme, recolor=prop.recolor,
                facing=prop.facing, where=f"scene '{self.spec.id}' ({prop.svg})",
            )
        return draw_prop(
            prop.prop, height=height, theme=self.theme, name=name, main=prop.color, detail=prop.detail,
            facing=prop.facing, character_height=height / prop.height_factor(), shape="open" if prop.open else None,
        )

    def _backdrop(self, layers: list[Mobject], heads: float | None = None) -> list[Mobject]:
        """The set behind the characters, back to front: the picture (cover) or the colour /
        gradient (named ``background``), the night's stars (above ``heads``, the highest head top
        at the start, y in Manim units), the background and middle ``layers``, then the ground
        band (``ground``). Empty when the stage shows the theme's background, no layers and no
        ground band."""
        p = self.params
        fw, fh = self.stage_width, self.frame_height
        if p.room is not None:  # the room's wall and floor instead of the sky and the ground (§69.42)
            return [*self._room().mobjects(), *layers]
        parts: list[Mobject] = []
        top = ground_top(p.ground, p.items())  # up to the deepest thing standing on it (§69.6)
        if p.has_picture():
            parts.append(self._picture())
        elif p.background is not None or self.light is not None:   # a lit stage grades the theme's background too
            colors = p.background if isinstance(p.background, list) else [p.background or self.theme.background]
            sky = Rectangle(width=fw, height=fh, stroke_width=0)
            sky.set_fill([resolve_color(c, self.theme) for c in colors], opacity=1.0)
            sky.set_sheen_direction(DOWN)  # a gradient runs from the first colour at the top
            sky.name = "background"
            parts.append(sky)
        if self._starry and not p.has_picture():  # in the sky, behind the layers (§69.31)
            sky_share = STAR_SKY * (1.0 - top)
            if heads is not None:   # not beside the characters' heads
                sky_share = min(sky_share, max(fh / 2 - heads - STAR_HEAD_ROOM * fh, 0.0) / fh)
            stars = night_stars(fw / self.frame_width * sky_share, preview=self.is_preview)
            box = (-fw / 2, fh / 2 - sky_share * fh, fw / 2, fh / 2)
            self.stars = StarField(stars, box, min(self.frame_width, self.frame_height))
            parts.append(self.stars)
        parts += layers
        ground_color = p.ground_color
        if ground_color is None and not p.has_picture():
            ground_color = DEFAULT_GROUND_COLOR
        if ground_color and top > 0:
            band_height = top * fh
            band = Rectangle(width=fw, height=band_height, stroke_width=0)
            band.set_fill(resolve_color(ground_color, self.theme), opacity=1.0)
            band.move_to([0.0, -fh / 2 + band_height / 2, 0.0])
            band.name = "ground"
            parts.append(band)
        return parts

    # ----- rooms (DESIGN.md §69.42) -------------------------------------------------------------

    def _room(self) -> RoomDrawing:
        """The room: its wall and floor, the sky outside its windows (for the light at the start;
        :meth:`_show_light` keeps it in step) and its window frames and curtains."""
        p = self.params
        room = p.room
        assert room is not None
        depth = p.wall_depth()
        geometry = room_geometry(
            ground=p.ground, depth=depth, size=p.size, frame_width=self.frame_width, frame_height=self.frame_height,
            stage_width=self.stage_width, ceiling=room.ceiling is not False,
        )
        left = -self.stage_width / 2
        theme = self.theme
        windows = [
            WindowLook(
                window_parts(left + mark_x(w.at, p.marks) * self.stage_width, geometry.wall_line, geometry.unit,
                             width=w.width, height=w.height, sill=w.sill, curtains=w.curtains is not False),
                resolve_color(w.frame, theme),
                None if w.curtains is False else resolve_color("accent" if w.curtains is True else w.curtains, theme),
            )
            for w in room.windows
        ]
        colors = room_colors(
            resolve_color(room.wall, theme), resolve_color(room.floor, theme),
            skirting=resolve_color(room.skirting, theme) if room.skirting is not None else None,
            ceiling=room.ceiling if isinstance(room.ceiling, bool) else resolve_color(room.ceiling, theme),
        )
        #: the sky outside the windows at the start and the light actions' changes of it
        self._sky_base = window_sky(self._light_key(p.light))
        self._sky_changes: list[SkyChange] = []
        drawing = draw_room(
            geometry, colors, wallpaper=room.wallpaper, flooring=room.flooring, windows=windows, sky=self._sky_base,
            short_side=min(self.frame_width, self.frame_height), frame_area=self.frame_width * self.frame_height,
            preview=self.is_preview,
        )
        #: what the room's windows show (``None``: not a room)
        self.window_views = drawing.views
        return drawing

    def _light_key(self, setting: str | CustomLight) -> str | tuple[str, float]:
        """A light setting as :func:`window_sky` takes it: a preset name, or (#hex tint, strength)."""
        if isinstance(setting, CustomLight):
            return (resolve_color(setting.tint, self.theme), setting.strength)
        return setting

    def door(self, name: str) -> Prop:
        """The room's door ``name`` (a :class:`VidgenError` when the room has no such door)."""
        if name not in self.params.door_names():
            known = ", ".join(self.params.door_names()) or "none"
            raise VidgenError(f"scene '{self.spec.id}': no door '{name}' (the room's doors: {known})")
        return self.props[name]

    def _picture(self) -> Mobject:
        """The background picture, scaled to cover the stage and centred."""
        p = self.params
        if p.generate is not None:  # the stored picture, or a placeholder card until it is made
            source = self.generated_picture(p.generate)
            picture = self._load_picture(source)
        else:
            picture = self._file_picture(p.image, "image")
        aspect = picture.width / picture.height
        picture.scale_to_fit_width(max(self.stage_width, self.frame_height * aspect)).move_to(ORIGIN)
        picture.name = "background"
        return picture

    def _file_picture(self, path: str, key: str) -> Mobject:
        """The picture file ``path`` of the param ``key`` (raster or SVG), unscaled."""
        problems = check_image(self.project, path, key)
        if problems:
            raise VidgenError(f"scene '{self.spec.id}': {problems[0]}")
        return self._load_picture(self.project.asset(path))

    def _load_picture(self, source: Any) -> Mobject:
        if is_vector(source):
            return load_vector(source, theme=self.theme, where=f"scene '{self.spec.id}' ({source.name})")
        return load_image(source)

    # ----- parallax layers (DESIGN.md §69.7) -----------------------------------------------------

    def _layers(self) -> list[Mobject]:
        """Each layer's mobject (named after it), drawn for the camera's home view (the stage's
        centre, zoom 1) and moved for the camera as it is now; a listener moves the layers whose
        factor is not 1 on every frame."""
        p = self.params
        made: list[Mobject] = []
        moving: list[_Parallax] = []
        for k, (layer, name) in enumerate(zip(p.layers, p.layer_names())):
            factor = layer.resolved_factor()
            half_w, half_h = layer_half_extent(factor, stage_width=self.stage_width, frame_width=self.frame_width, frame_height=self.frame_height)
            mob = self._layer_picture(layer, k, half_w) if layer.image is not None else self._layer_shapes(layer, half_w, half_h)
            mob.name = name
            made.append(mob)
            if abs(factor - 1.0) > 1e-9:
                moving.append(_Parallax(mob, factor, [(m, m.points.copy()) for m in mob.get_family() if len(m.points)]))
        if moving:
            self._parallax = moving
            self._move_layers()
            self.add_camera_listener(self._move_layers)
        return made

    def _move_layers(self) -> None:
        """Put every moving layer where its factor shows it for the camera now (from its points at
        the camera's home, so animations of the layer, e.g. its fade-in, cannot shift it)."""
        frame = self.camera.frame
        center = frame.get_center()[:2]
        zoom = self.frame_width / frame.width
        for layer in self._parallax:
            scale, (dx, dy) = layer_transform(layer.factor, center, zoom)
            shift = np.array([dx, dy, 0.0])
            for member, home in layer.home:
                member.points = home * scale + shift

    def _layer_picture(self, layer: StageLayer, k: int, half_width: float) -> Mobject:
        """A layer's picture: as wide as the layer, its bottom edge at ``bottom``."""
        picture = self._file_picture(layer.image, f"layers[{k}].image")
        picture.scale_to_fit_width(2 * half_width)
        picture.move_to([0.0, (layer.bottom - 0.5) * self.frame_height + picture.height / 2, 0.0])
        return picture

    def _layer_shapes(self, layer: StageLayer, half_width: float, half_height: float) -> Mobject:
        """A layer's shapes (``hills`` run across the whole layer, filled down to its bottom)."""
        short_side = min(self.frame_width, self.frame_height)
        shapes = VGroup()
        for item in layer.shapes:
            width, height = item.width * short_side, item.height * short_side
            x = (item.x - 0.5) * self.stage_width
            bottom = (item.y - 0.5) * self.frame_height
            if item.shape == "hills":
                mob: VMobject = Polygon(*hill_outline(half_width, bottom, -half_height, width, height), stroke_width=0)
            elif item.shape == "rect":
                mob = Rectangle(width=width, height=height, stroke_width=0).move_to([x, bottom + height / 2, 0.0])
            elif item.shape == "ellipse":
                mob = Ellipse(width=width, height=height, stroke_width=0).move_to([x, bottom + height / 2, 0.0])
            else:
                mob = Polygon([x - width / 2, bottom, 0.0], [x + width / 2, bottom, 0.0], [x, bottom + height, 0.0], stroke_width=0)
            mob.set_fill(resolve_color(item.color, self.theme), opacity=1.0)
            shapes.add(mob)
        return shapes


def _played(action: str, options: Any, anim: Animation, start: float, seconds: float) -> PlayedAction:
    """One animation of a built-in ``action`` (its ``options``) as it plays from scene time
    ``start`` for ``seconds``, for foley and motion effects."""
    if isinstance(anim, Walk):
        return PlayedAction(action, start, seconds, heights=anim.heights, phases=anim.phases, step_length=anim.step_length)
    if isinstance(anim, Jump):
        return PlayedAction(action, start, seconds, phases=anim.phases, lift=anim.lift)
    if isinstance(anim, PropMove):
        flies = anim.rise > 0 or anim.path is not None
        return PlayedAction(action, start, seconds, lands=anim.lands_at, flight=(anim.leave, anim.arrive) if flies else None)
    if isinstance(anim, Gesture):
        return PlayedAction(action, start, seconds, gesture=anim.kind, big=bool(getattr(options, "big", False)))
    expression = options.to if action == "emote" else getattr(options, "expression", None) if action == "react" else None
    effect = options.to if action == "effect" and options.sound else None
    return PlayedAction(action, start, seconds, expression=expression, effect=effect)


def hill_outline(half_width: float, foot: float, low: float, hill_width: float, hill_height: float) -> list[list[float]]:
    """Corners of a row of rounded hills from ``-half_width`` to ``half_width``: each hill
    ``hill_width`` wide and ``hill_height`` above ``foot``, the row filled down to ``low``."""
    count = max(1, math.ceil(2 * half_width / hill_width))
    span = 2 * half_width / count
    corners = [[-half_width, min(low, foot), 0.0]]
    for i in range(count * HILL_POINTS + 1):
        u = i / HILL_POINTS
        corners.append([-half_width + u * span, foot + hill_height * math.sin(math.pi * (u % 1.0)), 0.0])
    corners.append([half_width, min(low, foot), 0.0])
    return corners
